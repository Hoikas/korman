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

from PyHSPlasma import *
import weakref

from .explosions import *
from . import utils

_BL2PL = {
    "POINT": plOmniLightInfo,
    "SPOT": plSpotLightInfo,
    "SUN": plDirectionalLightInfo,
}

class LightConverter:
    def __init__(self, exporter):
        self._exporter = weakref.ref(exporter)
        self._converter_funcs = {
            "POINT": self._convert_point_lamp,
            "SPOT": self._convert_spot_lamp,
            "SUN": self._convert_sun_lamp,
        }

    def _convert_point_lamp(self, bl, pl):
        print("    [OmniLightInfo '{}']".format(bl.name))
        self._convert_shared_pointspot(bl, pl)

    def _convert_spot_lamp(self, bl, pl):
        print("    [SpotLightInfo '{}']".format(bl.name))
        self._convert_shared_pointspot(bl, pl)

        # Spot lights have a few more things...
        spot_size = bl.spot_size
        pl.spotOuter = spot_size

        blend = max(0.001, bl.spot_blend)
        pl.spotInner = spot_size - (blend*spot_size)

        if bl.use_halo:
            pl.falloff = bl.halo_intensity
        else:
            pl.falloff = 1.0

    def _convert_shared_pointspot(self, bl, pl):
        # So sue me, this was taken from pyprp2...
        dist = bl.distance
        if bl.falloff_type == "LINEAR_QUADRATIC_WEIGHTED":
            print("        Attenuation: Linear Quadratic Weighted")
            pl.attenQuadratic = bl.quadratic_attenuation / dist
            pl.attenLinear = bl.linear_attenuation / dist
            pl.attenConst = 1.0
        elif bl.falloff_type == "CONSTANT":
            print("        Attenuation: Konstant")
            pl.attenQuadratic = 0.0
            pl.attenLinear = 0.0
            pl.attenConst = 1.0
        elif bl.falloff_type == "INVERSE_SQUARE":
            print("        Attenuation: Inverse Square")
            pl.attenQuadratic = bl.quadratic_attenuation / dist
            pl.attenLinear = 0.0
            pl.attenConst = 1.0
        elif bl.falloff_type == "INVERSE_LINEAR":
            print("        Attenuation: Inverse Linear")
            pl.attenQuadratic = 0.0
            pl.attenLinear = bl.quadratic_attenuation / dist
            pl.attenConst = 1.0
        else:
            raise BlenderOptionNotSupportedError(bl.falloff_type)

        if bl.use_sphere:
            print("        Sphere Cutoff: {}".format(dist))
            pl.attenCutoff = dist
        else:
            pl.attenCutoff = dist * 2

    def _convert_sun_lamp(self, bl, pl):
        print("    [DirectionalLightInfo '{}']".format(bl.name))

    def _create_light_key(self, bo, bl_light, so):
        try:
            xlate = _BL2PL[bl_light.type]
            return self.mgr.find_create_key(xlate, bl=bo, so=so)
        except LookupError:
            raise BlenderOptionNotSupported("Object ('{}') lamp type '{}'".format(bo.name, bl_light.type))

    def export_rtlight(self, so, bo):
        bl_light = bo.data

        # The specifics be here...
        pl_light = self._create_light_key(bo, bl_light, so).object
        self._converter_funcs[bl_light.type](bl_light, pl_light)

        # Light color nonsense
        energy = bl_light.energy * 2
        if bl_light.use_negative:
            color = [(0.0 - i) * energy for i in bl_light.color]
        else:
            color = [i * energy for i in bl_light.color]
        color_str = "({:.4f}, {:.4f}, {:.4f})".format(color[0], color[1], color[2])
        color.append(1.0)

        # Apply the colors
        if bl_light.use_diffuse:
            print("        Diffuse: {}".format(color_str))
            pl_light.diffuse = hsColorRGBA(*color)
        else:
            print("        Diffuse: OFF")
            pl_light.diffuse = hsColorRGBA(0.0, 0.0, 0.0, 1.0)
        if bl_light.use_specular:
            print("        Specular: {}".format(color_str))
            pl_light.setProperty(plLightInfo.kLPHasSpecular, True)
            pl_light.specular = hsColorRGBA(*color)
        else:
            print("        Specular: OFF")
            pl_light.specular = hsColorRGBA(0.0, 0.0, 0.0, 1.0)

        # AFAICT ambient lighting is never set in PlasmaMax...
        # If you can think of a compelling reason to support it, be my guest.
        pl_light.ambient = hsColorRGBA(0.0, 0.0, 0.0, 1.0)

        # Now, let's apply the matrices...
        # Science indicates that Plasma RT Lights should *always* have mats, even if there is a CI
        l2w = utils.matrix44(bo.matrix_local)
        pl_light.lightToWorld = l2w
        pl_light.worldToLight = l2w.inverse()

        # *Sigh*
        pl_light.sceneNode = self.mgr.get_scene_node(location=so.key.location)

    def find_material_light_keys(self, bo, bm):
        """Given a blender material, we find the keys of all matching Plasma RT Lights.
           NOTE: We return a tuple of lists: ([permaLights], [permaProjs])"""
        print("    Searching for runtime lights...")
        permaLights = []
        permaProjs = []

        # We're going to inspect the material's light group.
        # If there is no light group, we'll say that there is no runtime lighting...
        # If there is, we will harvest all Blender lamps in that light group that are Plasma Objects
        lg = bm.light_group
        if lg is not None:
            for obj in lg.objects:
                if obj.type != "LAMP":
                    # moronic...
                    continue
                elif not obj.plasma_object.enabled:
                    # who cares?
                    continue
                lamp = obj.data

                # Check to see if they only want this light to work on its layer...
                if lamp.use_own_layer:
                    # Pairs up elements from both layers sequences such that we can compare
                    # to see if the lamp and object are in the same layer.
                    # If you can think of a better way, be my guest.
                    test = zip(bo.layers, obj.layers)
                    for i in test:
                        if i == (True, True):
                            break
                    else:
                        # didn't find a layer where both lamp and object were, skip it.
                        print("        [{}] '{}': not in same layer, skipping...".format(lamp.type, obj.name))
                        continue

                # This is probably where PermaLight vs PermaProj should be sorted out...
                pl_light = self._create_light_key(bo, lamp, None)
                if self._is_projection_lamp(lamp):
                    print("        [{}] PermaProj '{}'".format(lamp.type, obj.name))
                    permaProj.append(pl_light)
                    # TODO: run this through the material exporter...
                    # need to do some work to make the texture slot code not assume it's working with a material
                else:
                    print("        [{}] PermaLight '{}'".format(lamp.type, obj.name))
                    permaLights.append(pl_light)

        return (permaLights, permaProjs)

    def _is_projection_lamp(self, bl_light):
        for tex in bl_light.texture_slots:
            if tex is None or tex.texture is None:
                continue
            return True
        return False

    @property
    def mgr(self):
        return self._exporter().mgr
