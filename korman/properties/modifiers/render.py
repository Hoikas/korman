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
from bpy.props import *
from PyHSPlasma import *

from .base import PlasmaModifierProperties
from ...exporter.etlight import _NUM_RENDER_LAYERS
from ...exporter import utils
from ...exporter.explosions import ExportError


class PlasmaFadeMod(PlasmaModifierProperties):
    pl_id = "fademod"

    bl_category = "Render"
    bl_label = "Opacity Fader"
    bl_description = "Fades an object based on distance or line-of-sight"

    fader_type = EnumProperty(name="Fader Type",
                              description="Type of opacity fade",
                              items=[("DistOpacity", "Distance", "Fade based on distance to object"),
                                     ("FadeOpacity", "Line-of-Sight", "Fade based on line-of-sight to object"),
                                     ("SimpleDist",  "Simple Distance", "Fade for use as Great Zero Markers")],
                              default="SimpleDist")

    fade_in_time = FloatProperty(name="Fade In Time",
                                 description="Number of seconds before the object is fully visible",
                                 min=0.0, max=5.0, default=0.5, subtype="TIME", unit="TIME")
    fade_out_time = FloatProperty(name="Fade Out Time",
                                  description="Number of seconds before the object is fully invisible",
                                  min=0.0, max=5.0, default=0.5, subtype="TIME", unit="TIME")
    bounds_center = BoolProperty(name="Use Mesh Midpoint",
                                 description="Use mesh's midpoint to calculate LOS instead of object origin",
                                 default=False)

    near_trans = FloatProperty(name="Near Transparent",
                               description="Nearest distance at which the object is fully transparent",
                               min=0.0, default=0.0, subtype="DISTANCE", unit="LENGTH")
    near_opaq = FloatProperty(name="Near Opaque",
                              description="Nearest distance at which the object is fully opaque",
                              min=0.0, default=0.0, subtype="DISTANCE", unit="LENGTH")
    far_opaq = FloatProperty(name="Far Opaque",
                             description="Farthest distance at which the object is fully opaque",
                             min=0.0, default=15.0, subtype="DISTANCE", unit="LENGTH")
    far_trans = FloatProperty(name="Far Transparent",
                              description="Farthest distance at which the object is fully transparent",
                              min=0.0, default=20.0, subtype="DISTANCE", unit="LENGTH")

    def export(self, exporter, bo, so):
        if self.fader_type == "DistOpacity":
            mod = exporter.mgr.find_create_object(plDistOpacityMod, so=so, name=self.key_name)
            mod.nearTrans = self.near_trans
            mod.nearOpaq = self.near_opaq
            mod.farOpaq = self.far_opaq
            mod.farTrans = self.far_trans
        elif self.fader_type == "FadeOpacity":
            mod = exporter.mgr.find_create_object(plFadeOpacityMod, so=so, name=self.key_name)
            mod.fadeUp = self.fade_in_time
            mod.fadeDown = self.fade_out_time
            mod.boundsCenter = self.bounds_center
        elif self.fader_type == "SimpleDist":
            mod = exporter.mgr.find_create_object(plDistOpacityMod, so=so, name=self.key_name)
            mod.nearTrans = 0.0
            mod.nearOpaq = 0.0
            mod.farOpaq = self.far_opaq
            mod.farTrans = self.far_trans


class PlasmaFollowMod(PlasmaModifierProperties):
    pl_id = "followmod"

    bl_category = "Render"
    bl_label = "Follow"
    bl_description = "Follow the movement of the camera, player, or another object"

    follow_mode = EnumProperty(name="Mode",
                               description="Leader's movement to follow",
                               items=[
                                      ("kPositionX", "X Axis", "Follow the leader's X movements"),
                                      ("kPositionY", "Y Axis", "Follow the leader's Y movements"),
                                      ("kPositionZ", "Z Axis", "Follow the leader's Z movements"),
                                      ("kRotate", "Rotation", "Follow the leader's rotation movements"),
                                ],
                               default={"kPositionX", "kPositionY", "kPositionZ"},
                               options={"ENUM_FLAG"})

    leader_type = EnumProperty(name="Leader Type",
                               description="Leader to follow",
                               items=[
                                      ("kFollowCamera", "Camera", "Follow the camera"),
                                      ("kFollowListener", "Listener", "Follow listeners"),
                                      ("kFollowPlayer", "Player", "Follow the local player"),
                                      ("kFollowObject", "Object", "Follow an object"),
                                ])

    leader_object = StringProperty(name="Leader Object",
                                   description="Object to follow")

    def export(self, exporter, bo, so):
        fm = exporter.mgr.find_create_object(plFollowMod, so=so, name=self.key_name)

        fm.mode = 0
        for flag in (getattr(plFollowMod, mode) for mode in self.follow_mode):
            fm.mode |= flag

        fm.leaderType = getattr(plFollowMod, self.leader_type)
        if self.leader_type == "kFollowObject":
            # If this object is following another object, make sure that the
            # leader has been selected and is a valid SO.
            if self.leader_object:
                leader_obj = bpy.data.objects.get(self.leader_object, None)
                if leader_obj is None:
                    raise ExportError("'{}': Follow's leader object is invalid".format(self.key_name))
                else:
                    fm.leader = exporter.mgr.find_create_key(plSceneObject, bl=leader_obj)
            else:
                raise ExportError("'{}': Follow's leader object must be selected".format(self.key_name))

    @property
    def requires_actor(self):
        return True


class PlasmaLightMapGen(PlasmaModifierProperties):
    pl_id = "lightmap"

    bl_category = "Render"
    bl_label = "Bake Lighting"
    bl_description = "Auto-Bake Lightmap and/or AO"

    quality = EnumProperty(name="Quality",
                           description="Resolution of lightmap",
                           items=[("64", "64px", "64x64 pixels"),
                                  ("128", "128px", "128x128 pixels"),
                                  ("256", "256px", "256x256 pixels"),
                                  ("512", "512px", "512x512 pixels"),
                                  ("1024", "1024px", "1024x1024 pixels"),
                                  ("2048", "2048px", "2048x2048 pixels"),
                            ])

    render_layers = BoolVectorProperty(name="Layers",
                                       description="Render layers to use for baking",
                                       options=set(),
                                       subtype="LAYER",
                                       size=_NUM_RENDER_LAYERS,
                                       default=((True,) * _NUM_RENDER_LAYERS))

    light_group = StringProperty(name="Light Group",
                                 description="Group that defines the collection of lights to bake")

    uv_map = StringProperty(name="UV Texture",
                            description="UV Texture used as the basis for the lightmap")

    bake_lightmap = BoolProperty(name="Bake Lightmap",
                                 description="Bake lights to a lightmap texture",
                                 default=True,
                                 options=set())
    bake_aomap = BoolProperty(name="Bake Ambient Occlusion",
                              description="Bake ambient occlusion to a texture",
                              default=False,
                              options=set())

    def export(self, exporter, bo, so):
        aomap_im = bpy.data.images.get("{}_AOMAPGEN.png".format(bo.name))
        lightmap_im = bpy.data.images.get("{}_LIGHTMAPGEN.png".format(bo.name))
        materials = exporter.mesh.material.get_materials(bo)

        # Find the stupid UVTex
        uvw_src = 0
        for i, uvtex in enumerate(bo.data.tessface_uv_textures):
            if uvtex.name == "LIGHTMAPGEN":
                uvw_src = i
                break
        else:
            # TODO: raise exception
            pass

        # Export prepared layers
        aomap_key = self._export_light_layer(exporter, so, uvw_src, aomap_im, "AOMAPGEN")
        lightmap_key = self._export_light_layer(exporter, so, uvw_src, lightmap_im, "LIGHTMAPGEN")

        for matKey in materials:
            material = matKey.object
            if lightmap_key is not None:
                material.addPiggyBack(lightmap_key)
            if aomap_key is not None:
                material.addPiggyBack(aomap_key)

    def _export_light_layer(self, exporter, so, uvw_src, image, suffix):
        if image is None:
            return None

        layer = exporter.mgr.add_object(plLayer, name="{}_{}".format(so.key.name, suffix), so=so)
        layer.UVWSrc = uvw_src

        # Colors science'd from PRPs
        layer.ambient = hsColorRGBA(1.0, 1.0, 1.0)
        layer.preshade = hsColorRGBA(0.5, 0.5, 0.5)
        layer.runtime = hsColorRGBA(0.5, 0.5, 0.5)

        # GMatState
        gstate = layer.state
        gstate.blendFlags |= hsGMatState.kBlendMult
        gstate.clampFlags |= (hsGMatState.kClampTextureU | hsGMatState.kClampTextureV)
        gstate.ZFlags |= hsGMatState.kZNoZWrite
        gstate.miscFlags |= hsGMatState.kMiscLightMap

        # Mmm... cheating
        exporter.mesh.material.export_prepared_layer(layer, image)
        return layer.key

    @property
    def key_name(self):
        return "{}_LIGHTMAPGEN".format(self.id_data.name)

    @property
    def resolution(self):
        return int(self.quality)


class PlasmaLightingMod(PlasmaModifierProperties):
    pl_id = "lighting"

    bl_category = "Render"
    bl_label = "Lighting"
    bl_description = "Fine tune Plasma lighting settings"

    force_rt_lights = BoolProperty(name="Force RT Lighting",
                                   description="Unleashes satan by forcing the engine to dynamically light this object",
                                   default=False,
                                   options=set())
    force_preshade = BoolProperty(name="Force Vertex Shading",
                                  description="Ensures vertex lights are baked, even if illogical",
                                  default=False,
                                  options=set())

    @property
    def allow_preshade(self):
        bo = self.id_data
        if bo.plasma_modifiers.water_basic.enabled:
            return False
        if bo.plasma_modifiers.lightmap.enabled:
            return False
        return True

    def export(self, exporter, bo, so):
        # Exposes no new keyed objects, mostly a hint to the ET light code
        pass

    @property
    def preshade(self):
        bo = self.id_data
        if self.allow_preshade:
            if self.force_preshade:
                return True
            # RT lights means no preshading unless requested
            if self.rt_lights:
                return False
            if not bo.plasma_object.has_transform_animation:
                return True
        return False

    @property
    def rt_lights(self):
        """Are RT lights forcibly enabled or do we otherwise want them?"""
        return (self.enabled and self.force_rt_lights) or self.want_rt_lights

    @property
    def want_rt_lights(self):
        """Gets whether or not this object ought to be lit dynamically"""
        bo = self.id_data
        if bo.plasma_modifiers.lightmap.enabled:
            return False
        if bo.plasma_modifiers.water_basic.enabled:
            return True
        if bo.plasma_object.has_transform_animation:
            return True
        return False


class PlasmaViewFaceMod(PlasmaModifierProperties):
    pl_id = "viewfacemod"

    bl_category = "Render"
    bl_label = "Swivel"
    bl_description = "Swivel object to face the camera, player, or another object"

    preset_options = EnumProperty(name="Type",
                                  description="Type of Facing",
                                  items=[
                                         ("Billboard", "Billboard", "Face the camera (Y Axis only)"),
                                         ("Sprite", "Sprite", "Face the camera (All Axis)"),
                                         ("Custom", "Custom", "Custom Swivel"),
                                   ])

    follow_mode = EnumProperty(name="Target Type",
                               description="Target of the swivel",
                               items=[
                                      ("kFaceCam", "Camera", "Face the camera"),
                                      ("kFaceList", "Listener", "Face listeners"),
                                      ("kFacePlay", "Player", "Face the local player"),
                                      ("kFaceObj", "Object", "Face an object"),
                                ])
    target_object = StringProperty(name="Target Object",
                                   description="Object to face")

    pivot_on_y = BoolProperty(name="Pivot on local Y",
                              description="Swivel only around the local Y axis",
                              default=False)

    offset = BoolProperty(name="Offset", description="Use offset vector", default=False)
    offset_local = BoolProperty(name="Local", description="Use local coordinates", default=False)
    offset_coord = FloatVectorProperty(name="", subtype="XYZ")

    def export(self, exporter, bo, so):
        vfm = exporter.mgr.find_create_object(plViewFaceModifier, so=so, name=self.key_name)

        # Set a default scaling (libHSPlasma will set this to 0 otherwise).
        vfm.scale = hsVector3(1,1,1)
        l2p = utils.matrix44(bo.matrix_local)
        vfm.localToParent = l2p
        vfm.parentToLocal = l2p.inverse()

        # Cyan has these as separate components, but they're really just preset
        # options for common swivels.  We've consolidated them both here, along
        # with the fully-customizable swivel as a third option.
        if self.preset_options == "Billboard":
            vfm.setFlag(plViewFaceModifier.kFaceCam, True)
            vfm.setFlag(plViewFaceModifier.kPivotY, True)
        elif self.preset_options == "Sprite":
            vfm.setFlag(plViewFaceModifier.kFaceCam, True)
            vfm.setFlag(plViewFaceModifier.kPivotFace, True)
        elif self.preset_options == "Custom":
            # For the discerning artist, full control over their swivel options!
            vfm.setFlag(getattr(plViewFaceModifier, self.follow_mode), True)

            if self.follow_mode == "kFaceObj":
                # If this swivel is following an object, make sure that the
                # target has been selected and is a valid SO.
                if self.target_object:
                    target_obj = bpy.data.objects.get(self.target_object, None)
                    if target_obj is None:
                        raise ExportError("'{}': Swivel's target object is invalid".format(self.key_name))
                    else:
                        vfm.faceObj = exporter.mgr.find_create_key(plSceneObject, bl=target_obj)
                else:
                    raise ExportError("'{}': Swivel's target object must be selected".format(self.key_name))

            if self.pivot_on_y:
                vfm.setFlag(plViewFaceModifier.kPivotY, True)
            else:
                vfm.setFlag(plViewFaceModifier.kPivotFace, True)

            if self.offset:
                vfm.offset = hsVector3(*self.offset_coord)
                if self.offset_local:
                    vfm.setFlag(plViewFaceModifier.kOffsetLocal, True)

    @property
    def requires_actor(self):
        return True


class PlasmaVisControl(PlasmaModifierProperties):
    pl_id = "visregion"

    bl_category = "Render"
    bl_label = "Visibility Control"
    bl_description = "Controls object visibility using VisRegions"

    mode = EnumProperty(name="Mode",
                        description="Purpose of the VisRegion",
                        items=[("normal", "Normal", "Objects are only visible when the camera is inside this region"),
                               ("exclude", "Exclude", "Objects are only visible when the camera is outside this region"),
                               ("fx", "Special FX", "This is a list of objects used for special effects only")])
    softvolume = StringProperty(name="Region",
                                description="Object defining the SoftVolume for this VisRegion")
    replace_normal = BoolProperty(name="Hide Drawables",
                                  description="Hides drawables attached to this region",
                                  default=True)

    def export(self, exporter, bo, so):
        rgn = exporter.mgr.find_create_object(plVisRegion, bl=bo, so=so)
        rgn.setProperty(plVisRegion.kReplaceNormal, self.replace_normal)

        if self.mode == "fx":
            rgn.setProperty(plVisRegion.kDisable, True)
        else:
            this_sv = bo.plasma_modifiers.softvolume
            if this_sv.enabled:
                print("    [VisRegion] I'm a SoftVolume myself :)")
                rgn.region = this_sv.get_key(exporter, so)
            else:
                print("    [VisRegion] SoftVolume '{}'".format(self.softvolume))
                sv_bo = bpy.data.objects.get(self.softvolume, None)
                if sv_bo is None:
                    raise ExportError("'{}': Invalid object '{}' for VisControl soft volume".format(bo.name, self.softvolume))
                sv = sv_bo.plasma_modifiers.softvolume
                if not sv.enabled:
                    raise ExportError("'{}': '{}' is not a SoftVolume".format(bo.name, self.softvolume))
                rgn.region = sv.get_key(exporter)
            rgn.setProperty(plVisRegion.kIsNot, self.mode == "exclude")


class VisRegion(bpy.types.PropertyGroup):
    enabled = BoolProperty(default=True)
    region_name = StringProperty(name="Control",
                                 description="Object defining a Plasma Visibility Control")


class PlasmaVisibilitySet(PlasmaModifierProperties):
    pl_id = "visibility"

    bl_category = "Render"
    bl_label = "Visibility Set"
    bl_description = "Defines areas where this object is visible"

    regions = CollectionProperty(name="Visibility Regions",
                                 type=VisRegion)
    active_region_index = IntProperty(options={"HIDDEN"})

    def export(self, exporter, bo, so):
        if not self.regions:
            # TODO: Log message about how this modifier is totally worthless
            return

        # Currently, this modifier is valid for meshes and lamps
        if bo.type == "MESH":
            diface = exporter.mgr.find_create_object(plDrawInterface, bl=bo, so=so)
            addRegion = diface.addRegion
        elif bo.type == "LAMP":
            light = exporter.light.get_light_key(bo, bo.data, so)
            addRegion = light.object.addVisRegion

        for region in self.regions:
            if not region.enabled:
                continue
            rgn_bo = bpy.data.objects.get(region.region_name, None)
            if rgn_bo is None:
                raise ExportError("{}: Invalid VisControl '{}' in VisSet modifier".format(bo.name, region.region_name))
            addRegion(exporter.mgr.find_create_key(plVisRegion, bl=rgn_bo))
