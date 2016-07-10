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

from ..exporter.etlight import LightBaker

class _LightingOperator:
    @classmethod
    def poll(cls, context):
        if context.object is not None:
            return context.scene.render.engine == "PLASMA_GAME"


class LightmapAutobakePreviewOperator(_LightingOperator, bpy.types.Operator):
    bl_idname = "object.plasma_lightmap_preview"
    bl_label = "Preview Baked Lighting"
    bl_options = {"INTERNAL"}

    def __init__(self):
        super().__init__()

    def execute(self, context):
        try:
            _layers = tuple(context.scene.layers)
            bake = LightBaker()
            if not bake.bake_static_lighting([context.active_object,]):
                self.report({"INFO"}, "No valid lights found to bake.")
                return {"FINISHED"}
        finally:
            context.scene.layers = _layers

        self._prepare_preview(context, "LIGHTMAPGEN")
        self._prepare_preview(context, "AOMAPGEN")
        return {"FINISHED"}

    def _prepare_preview(self, context, preview_type):
        tex_name = "{}_PREVIEW".format(preview_type)
        tex = bpy.data.textures.get(tex_name)
        if tex is None:
            tex = bpy.data.textures.new(tex_name, "IMAGE")
        tex.extension = "CLIP"
        tex.image = bpy.data.images.get("{}_{}.png".format(context.active_object.name, preview_type))

