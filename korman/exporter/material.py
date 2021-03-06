#    This file is part of Korman.
#
#    Korman is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Korman is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Korman.  If not, see <http://www.gnu.org/licenses/>.

import bpy
import bgl
import math
import os.path
from PyHSPlasma import *
import weakref

from . import explosions
from .. import helpers
from . import utils

# BGL doesn't know about this as of Blender 2.74
bgl.GL_GENERATE_MIPMAP = 0x8191
bgl.GL_BGRA = 0x80E1

class _GLTexture:
    def __init__(self, blimg):
        self._ownit = (blimg.bindcode == 0)
        if self._ownit:
            if blimg.gl_load() != 0:
                raise explosions.GLLoadError(blimg)
        self._blimg = blimg

    def __del__(self):
        if self._ownit:
            self._blimg.gl_free()

    def __enter__(self):
        """Sets the Blender Image as the active OpenGL texture"""
        self._previous_texture = self._get_integer(bgl.GL_TEXTURE_BINDING_2D)
        self._changed_state = (self._previous_texture != self._blimg.bindcode)
        if self._changed_state:
            bgl.glBindTexture(bgl.GL_TEXTURE_2D, self._blimg.bindcode)
        return self

    def __exit__(self, type, value, traceback):
        mipmap_state = getattr(self, "_mipmap_state", None)
        if mipmap_state is not None:
            bgl.glTexParameteri(bgl.GL_TEXTURE_2D, bgl.GL_GENERATE_MIPMAP, mipmap_state)

        if self._changed_state:
            bgl.glBindTexture(bgl.GL_TEXTURE_2D, self._previous_texture)

    def generate_mipmap(self):
        """Generates all mip levels for this texture"""
        self._mipmap_state = self._get_tex_param(bgl.GL_GENERATE_MIPMAP)

        # Note that this is a very old feature from OpenGL 1.x -- it's new enough that Windows (and
        # Blender apparently) don't support it natively and yet old enough that it was thrown away
        # in OpenGL 3.0. The new way is glGenerateMipmap, but Blender likes oldgl, so we don't have that
        # function available to us in BGL. I don't want to deal with loading the GL dll in ctypes on
        # many platforms right now (or context headaches). If someone wants to fix this, be my guest!
        # It will simplify our state tracking a bit.
        bgl.glTexParameteri(bgl.GL_TEXTURE_2D, bgl.GL_GENERATE_MIPMAP, 1)

    def get_level_data(self, level=0, calc_alpha=False, bgra=False, quiet=False):
        """Gets the uncompressed pixel data for a requested mip level, optionally calculating the alpha
           channel from the image color data
        """
        width = self._get_tex_param(bgl.GL_TEXTURE_WIDTH, level)
        height = self._get_tex_param(bgl.GL_TEXTURE_HEIGHT, level)
        if not quiet:
            print("        Level #{}: {}x{}".format(level, width, height))

        # Grab the image data
        size = width * height * 4
        buf = bgl.Buffer(bgl.GL_BYTE, size)
        fmt = bgl.GL_BGRA if bgra else bgl.GL_RGBA
        bgl.glGetTexImage(bgl.GL_TEXTURE_2D, level, fmt, bgl.GL_UNSIGNED_BYTE, buf);

        # Calculate le alphas
        # NOTE: the variable names are correct for GL_RGBA. We'll still get the right values for
        # BGRA, obviously, but red will suddenly be... blue. Yeah.
        if calc_alpha:
            for i in range(0, size, 4):
                r, g, b = buf[i:i+3]
                buf[i+3] = int((r + g + b) / 3)
        return bytes(buf)

    def _get_integer(self, arg):
        buf = bgl.Buffer(bgl.GL_INT, 1)
        bgl.glGetIntegerv(arg, buf)
        return int(buf[0])

    def _get_tex_param(self, param, level=None):
        buf = bgl.Buffer(bgl.GL_INT, 1)
        if level is None:
            bgl.glGetTexParameteriv(bgl.GL_TEXTURE_2D, param, buf)
        else:
            bgl.glGetTexLevelParameteriv(bgl.GL_TEXTURE_2D, level, param, buf)
        return int(buf[0])


class _Texture:
    def __init__(self, texture=None, image=None, use_alpha=None, force_calc_alpha=False):
        assert (texture or image)

        if texture is not None:
            if image is None:
                image = texture.image
            self.calc_alpha = texture.use_calculate_alpha
            self.mipmap = texture.use_mipmap
        else:
            self.calc_alpha = False
            self.mipmap = False

        if force_calc_alpha or self.calc_alpha:
            self.calc_alpha = True
            self.use_alpha  = True
        elif use_alpha is None:
            self.use_alpha = (image.channels == 4 and image.use_alpha)
        else:
            self.use_alpha = use_alpha

        self.image = image

    def __eq__(self, other):
        if not isinstance(other, _Texture):
            return False

        if self.image == other.image:
            if self.calc_alpha == other.calc_alpha:
                self._update(other)
                return True

    def __hash__(self):
        return hash(self.image.name) ^ hash(self.calc_alpha)

    def __str__(self):
        if self.mipmap:
            name = self._change_extension(self.image.name, ".dds")
        else:
            name = self._change_extension(self.image.name, ".bmp")
        if self.calc_alpha:
            name = "ALPHAGEN_{}".format(name)
        return name

    def _change_extension(self, name, newext):
        # Blender likes to add faux extensions such as .001 :(
        if name.find(".") == -1:
            return "{}{}".format(name, newext)
        name, end = os.path.splitext(name)
        return "{}{}".format(name, newext)

    def _update(self, other):
        """Update myself with any props that might be overridable from another copy of myself"""
        if other.use_alpha:
            self.use_alpha = True
        if other.mipmap:
            self.mipmap = True


class MaterialConverter:
    def __init__(self, exporter):
        self._obj2mat = {}
        self._exporter = weakref.ref(exporter)
        self._pending = {}
        self._alphatest = {}
        self._tex_exporters = {
            "ENVRIONMENT_MAP": self._export_texture_type_environment_map,
            "IMAGE": self._export_texture_type_image,
            "NONE": self._export_texture_type_none,
        }

    def export_material(self, bo, bm):
        """Exports a Blender Material as an hsGMaterial"""
        print("    Exporting Material '{}'".format(bm.name))

        hsgmat = self._mgr.add_object(hsGMaterial, name=bm.name, bl=bo)
        slots = [slot for slot in bm.texture_slots if slot is not None and slot.use and
                 slot.texture is not None and slot.texture.type in self._tex_exporters]

        # Okay, I know this isn't Pythonic... But we're doing it this way because we might actually
        # export many slots in one go. Think stencils.
        i = 0
        while i < len(slots):
            i += self._export_texture_slot(bo, bm, hsgmat, slots, i)

        # Plasma makes several assumptions that every hsGMaterial has at least one layer. If this
        # material had no Textures, we will need to initialize a default layer
        if not hsgmat.layers:
            layer = self._mgr.add_object(plLayer, name="{}_AutoLayer".format(bm.name), bl=bo)
            self._propagate_material_settings(bm, layer)
            hsgmat.addLayer(layer.key)

        # Cache this material for later
        if bo in self._obj2mat:
            self._obj2mat[bo].append(hsgmat.key)
        else:
            self._obj2mat[bo] = [hsgmat.key]

        # Looks like we're done...
        return hsgmat.key

    def _export_texture_slot(self, bo, bm, hsgmat, slots, idx):
        slot = slots[idx]
        num_exported = 1

        name = "{}_{}".format(bm.name, slot.name)
        print("        Exporting Plasma Layer '{}'".format(name))
        layer = self._mgr.add_object(plLayer, name=name, bl=bo)
        self._propagate_material_settings(bm, layer)

        # UVW Channel
        for i, uvchan in enumerate(bo.data.tessface_uv_textures):
            if uvchan.name == slot.uv_layer:
                layer.UVWSrc = i
                print("            Using UV Map #{} '{}'".format(i, name))
                break
        else:
            print("            No UVMap specified... Blindly using the first one, maybe it exists :|")

        state = layer.state
        if slot.use_stencil:
            hsgmat.compFlags |= hsGMaterial.kCompNeedsBlendChannel
            state.blendFlags |= hsGMatState.kBlendAlpha | hsGMatState.kBlendAlphaMult | hsGMatState.kBlendNoTexColor
            state.clampFlags |= hsGMatState.kClampTexture
            state.ZFlags |= hsGMatState.kZNoZWrite
            layer.ambient = hsColorRGBA(1.0, 1.0, 1.0, 1.0)

            # Plasma actually wants the next layer first, so let's export him
            nextIdx = idx + 1
            if len(slots) == nextIdx:
                raise ExportError("Texture Slot '{}' wants to be a stencil, but there are no more TextureSlots.".format(slot.name))
            print("            --- BEGIN STENCIL ---")
            self._export_texture_slot(bo, bm, hsgmat, slots, nextIdx)
            print("            ---  END STENCIL  ---")
            num_exported += 1

            # Now that we've exported the bugger, flag him as binding with this texture
            prev_layer = hsgmat.layers[-1].object
            prev_state = prev_layer.state
            prev_state.miscFlags |= hsGMatState.kMiscBindNext | hsGMatState.kMiscRestartPassHere
            if not prev_state.blendFlags & hsGMatState.kBlendMask:
                prev_state.blendFlags |= hsGMatState.kBlendAlpha
        else:
            # Standard layer flags ahoy
            if slot.blend_type == "ADD":
                state.blendFlags |= hsGMatState.kBlendAdd
            elif slot.blend_type == "MULTIPLY":
                state.blendFlags |= hsGMatState.kBlendMult

        # Apply custom layer properties
        texture = slot.texture
        layer.opacity = texture.plasma_layer.opacity / 100

        # Export the specific texture type
        self._tex_exporters[texture.type](bo, hsgmat, layer, slot)
        hsgmat.addLayer(layer.key)
        return num_exported

    def _export_texture_type_environment_map(self, bo, hsgmat, layer, slot):
        """Exports a Blender EnvironmentMapTexture to a plLayer"""

        texture = slot.texture
        bl_env = texture.environment_map
        if bl_env.source in {"STATIC", "ANIMATED"}:
            if bl_env.mapping == "PLANE" and self._mgr.getVer() >= pvMoul:
                pl_env = plDynamicCamMap
            else:
                pl_env = plDynamicEnvMap
            pl_env = self._export_dynamic_env(bo, hsgmat, layer, bl_env, pl_env)
        else:
            # We should really export a CubicEnvMap here, but we have a good setup for DynamicEnvMaps
            # that create themselves when the explorer links in, so really... who cares about CEMs?
            self._exporter().report.warn("IMAGE EnvironmentMaps are not supported. '{}' will not be exported!".format(layer.key.name))
            pl_env = None
        layer.texture = pl_env

    def _export_dynamic_env(self, bo, hsgmat, layer, bl_env, pl_class):
        # To protect the user from themselves, let's check to make sure that a DEM/DCM matching this
        # viewpoint object has not already been exported...
        viewpt = bl_env.viewpoint_object
        name = "{}_DynEnvMap".format(viewpt.name)
        pl_env = self._mgr.find_key(pl_class, bl=bo, name=name)
        if pl_env is not None:
            print("            EnvMap for viewpoint {} already exported... NOTE: Your settings here will be overridden by the previous object!".format(viewpt.name))
            pl_env_obj = pl_env.object
            if isinstance(pl_env_obj, plDynamicCamMap):
                dcm.addTargetNode(self._mgr.find_key(plSceneObject, bl=bo))
                dcm.addMatLayer(layer.key)
            return pl_env

        # It matters not whether or not the viewpoint object is a Plasma Object, it is exported as at
        # least a SceneObject and CoordInterface so that we can touch it...
        root = self._mgr.find_create_key(plSceneObject, bl=bo, name=viewpt.name)
        self._exporter().export_coordinate_interface(root.object, bl=bo, name=viewpt.name)
        # FIXME: DynamicCamMap Camera

        # Ensure POT
        oRes = bl_env.resolution
        eRes = helpers.ensure_power_of_two(oRes)
        if oRes != eRes:
            print("            Overriding EnvMap size to ({}x{}) -- POT".format(eRes, eRes))

        # And now for the general ho'hum-ness
        pl_env = self._mgr.add_object(pl_class, bl=bo, name=name)
        pl_env.hither = bl_env.clip_start
        pl_env.yon = bl_env.clip_end
        pl_env.refreshRate = 0.01 if bl_env.source == "ANIMATED" else 0.0
        pl_env.incCharacters = True
        pl_env.rootNode = root # FIXME: DCM camera

        # Perhaps the DEM/DCM fog should be separately configurable at some point?
        pl_fog = bpy.context.scene.world.plasma_fni
        pl_env.color = utils.color(pl_fog.fog_color)
        pl_env.fogStart = pl_fog.fog_start

        if isinstance(pl_env, plDynamicCamMap):
            faces = (pl_env,)

            pl_env.addTargetNode(self._mgr.find_key(plSceneObject, bl=bo))
            pl_env.addMatLayer(layer.key)

            # This is really just so we don't raise any eyebrows if anyone is looking at the files.
            # If you're disabling DCMs, then you're obviuously trolling!
            # Cyan generates a single color image, but we'll just set the layer colors and go away.
            fake_layer = self._mgr.add_object(plLayer, bl=bo, name="{}_DisabledDynEnvMap".format(viewpt.name))
            fake_layer.ambient = layer.ambient
            fake_layer.preshade = layer.preshade
            fake_layer.runtime = layer.runtime
            fake_layer.specular = layer.specular
            pl_env.disableTexture = fake_layer.key

            if pl_env.camera is None:
                layer.UVWSrc = plLayerInterface.kUVWPosition
                layer.state.miscFlags |= (hsGMatState.kMiscCam2Screen | hsGMatState.kMiscPerspProjection)
        else:
            faces = pl_env.faces + (pl_env,)

            layer.UVWSrc = plLayerInterface.kUVWReflect
            layer.state.miscFlags |= hsGMatState.kMiscUseRefractionXform

        # Because we might be working with a multi-faced env map. It's even worse than have two faces...
        for i in faces:
            i.setConfig(plBitmap.kRGB8888)
            i.flags |= plBitmap.kIsTexture
            i.flags &= ~plBitmap.kAlphaChannelFlag
            i.width = eRes
            i.height = eRes
            i.proportionalViewport = False
            i.viewportLeft = 0
            i.viewportTop = 0
            i.viewportRight = eRes
            i.viewportBottom = eRes
            i.ZDepth = 24

        return pl_env.key

    def _export_texture_type_image(self, bo, hsgmat, layer, slot):
        """Exports a Blender ImageTexture to a plLayer"""
        texture = slot.texture

        # Does the image have any alpha at all?
        has_alpha = texture.use_calculate_alpha or slot.use_stencil or self._test_image_alpha(texture.image)
        if (texture.image.use_alpha and texture.use_alpha) and not has_alpha:
            warning = "'{}' wants to use alpha, but '{}' is opaque".format(texture.name, texture.image.name)
            self._exporter().report.warn(warning, indent=3)

        # First, let's apply any relevant flags
        state = layer.state
        if not slot.use_stencil:
            # mutually exclusive blend flags
            if texture.use_alpha and has_alpha:
                state.blendFlags |= hsGMatState.kBlendAlpha

            if texture.invert_alpha and has_alpha:
                state.blendFlags |= hsGMatState.kBlendInvertAlpha
        if texture.extension == "CLIP":
            state.clampFlags |= hsGMatState.kClampTexture

        # Now, let's export the plBitmap
        # If the image is None (no image applied in Blender), we assume this is a plDynamicTextMap
        # Otherwise, we toss this layer and some info into our pending texture dict and process it
        #     when the exporter tells us to finalize all our shit
        if texture.image is None:
            bitmap = self.add_object(plDynamicTextMap, name="{}_DynText".format(layer.key.name), bl=bo)
        else:
            key = _Texture(texture=texture, use_alpha=has_alpha, force_calc_alpha=slot.use_stencil)
            if key not in self._pending:
                print("            Stashing '{}' for conversion as '{}'".format(texture.image.name, str(key)))
                self._pending[key] = [layer.key,]
            else:
                print("            Found another user of '{}'".format(texture.image.name))
                self._pending[key].append(layer.key)

    def _export_texture_type_none(self, bo, hsgmat, layer, texture):
        # We'll allow this, just for sanity's sake...
        pass

    def export_prepared_layer(self, layer, image):
        """This exports an externally prepared layer and image"""
        key = _Texture(image=image)
        if key not in self._pending:
            print("        Stashing '{}' for conversion as '{}'".format(image.name, str(key)))
            self._pending[key] = [layer.key,]
        else:
            print("        Found another user of '{}'".format(image.name))
            self._pending[key].append(layer.key)

    def finalize(self):
        for key, layers in self._pending.items():
            name = str(key)
            print("\n[Mipmap '{}']".format(name))

            image = key.image
            oWidth, oHeight = image.size
            eWidth = helpers.ensure_power_of_two(oWidth)
            eHeight = helpers.ensure_power_of_two(oHeight)
            if (eWidth != oWidth) or (eHeight != oHeight):
                print("    Image is not a POT ({}x{}) resizing to {}x{}".format(oWidth, oHeight, eWidth, eHeight))
                self._resize_image(image, eWidth, eHeight)

            # Some basic mipmap settings.
            numLevels = math.floor(math.log(max(eWidth, eHeight), 2)) + 1 if key.mipmap else 1
            compression = plBitmap.kDirectXCompression if key.mipmap else plBitmap.kUncompressed
            dxt = plBitmap.kDXT5 if key.use_alpha or key.calc_alpha else plBitmap.kDXT1

            # Major Workaround Ahoy
            # There is a bug in Cyan's level size algorithm that causes it to not allocate enough memory
            # for the color block in certain mipmaps. I personally have encountered an access violation on
            # 1x1 DXT5 mip levels -- the code only allocates an alpha block and not a color block. Paradox
            # reports that if any dimension is smaller than 4px in a mip level, OpenGL doesn't like Cyan generated
            # data. So, we're going to lop off the last two mip levels, which should be 1px and 2px as the smallest.
            # This bug is basically unfixable without crazy hacks because of the way Plasma reads in texture data.
            #     "<Deledrius> I feel like any texture at a 1x1 level is essentially academic.  I mean, JPEG/DXT
            #                  doesn't even compress that, and what is it?  Just the average color of the whole
            #                  texture in a single pixel?"
            # :)
            if key.mipmap:
                # If your mipmap only has 2 levels (or less), then you deserve to phail...
                numLevels = max(numLevels - 2, 2)

            # Grab the image data from OpenGL and stuff it into the plBitmap
            with _GLTexture(image) as glimage:
                if key.mipmap:
                    print("    Generating mip levels")
                    glimage.generate_mipmap()
                else:
                    print("    Stuffing image data")

                # Uncompressed bitmaps are BGRA
                fmt = compression == plBitmap.kUncompressed

                # Hold the uncompressed level data for now. We may have to make multiple copies of
                # this mipmap for per-page textures :(
                data = []
                for i in range(numLevels):
                    data.append(glimage.get_level_data(i, key.calc_alpha, fmt))

            # Be a good citizen and reset the Blender Image to pre-futzing state
            image.reload()

            # Now we poke our new bitmap into the pending layers. Note that we have to do some funny
            # business to account for per-page textures
            mgr = self._mgr
            pages = {}

            print("    Adding to Layer(s)")
            for layer in layers:
                print("        {}".format(layer.name))
                page = mgr.get_textures_page(layer) # Layer's page or Textures.prp

                # If we haven't created this plMipmap in the page (either layer's page or Textures.prp),
                # then we need to do that and stuff the level data. This is a little tedious, but we
                # need to be careful to manage our resources correctly
                if page not in pages:
                    mipmap = plMipmap(name=name, width=eWidth, height=eHeight, numLevels=numLevels,
                                      compType=compression, format=plBitmap.kRGB8888, dxtLevel=dxt)
                    func = mipmap.CompressImage if compression == plBitmap.kDirectXCompression else mipmap.setLevel
                    for i, level in enumerate(data):
                        func(i, level)
                    mgr.AddObject(page, mipmap)
                    pages[page] = mipmap
                else:
                    mipmap = pages[page]
                layer.object.texture = mipmap.key

    def get_materials(self, bo):
        return self._obj2mat[bo]

    @property
    def _mgr(self):
        return self._exporter().mgr

    def _propagate_material_settings(self, bm, layer):
        """Converts settings from the Blender Material to corresponding plLayer settings"""
        state = layer.state

        # Shade Flags
        if not bm.use_mist:
            state.shadeFlags |= hsGMatState.kShadeNoFog # Dead in CWE
            state.shadeFlags |= hsGMatState.kShadeReallyNoFog

        # Colors
        layer.ambient = utils.color(bpy.context.scene.world.ambient_color)
        layer.preshade = utils.color(bm.diffuse_color)
        layer.runtime = utils.color(bm.diffuse_color)
        layer.specular = utils.color(bm.specular_color)

    def _resize_image(self, image, width, height):
        image.scale(width, height)

        # If the image is already loaded into OpenGL, we need to refresh it to get the scaling.
        if image.bindcode != 0:
            image.gl_free()
            image.gl_load()

    def _test_image_alpha(self, image):
        """Tests to see if this image has any alpha data"""

        # In the interest of speed, let's see if we've already done this one...
        result = self._alphatest.get(image, None)
        if result is not None:
            return result

        if image.channels != 4:
            result = False
        elif not image.use_alpha:
            result = False
        else:
            # Using bpy.types.Image.pixels is VERY VERY VERY slow...
            with _GLTexture(image) as glimage:
                data = glimage.get_level_data(quiet=True)
                for i in range(3, len(data), 4):
                    if data[i] != 255:
                        result = True
                        break
                else:
                    result = False

        self._alphatest[image] = result
        return result
