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


class PlasmaRenderEngine(bpy.types.RenderEngine):

    bl_idname = "PLASMA_GAME"
    bl_label = "Korman"

    pass


# Explicitly whitelist compatible Blender panels...
from bl_ui import properties_material
properties_material.MATERIAL_PT_context_material.COMPAT_ENGINES.add("PLASMA_GAME")
properties_material.MATERIAL_PT_diffuse.COMPAT_ENGINES.add("PLASMA_GAME")
properties_material.MATERIAL_PT_shading.COMPAT_ENGINES.add("PLASMA_GAME")
properties_material.MATERIAL_PT_specular.COMPAT_ENGINES.add("PLASMA_GAME")
properties_material.MATERIAL_PT_options.COMPAT_ENGINES.add("PLASMA_GAME")
properties_material.MATERIAL_PT_preview.COMPAT_ENGINES.add("PLASMA_GAME")
del properties_material

from bl_ui import properties_data_mesh
properties_data_mesh.DATA_PT_uv_texture.COMPAT_ENGINES.add("PLASMA_GAME")
properties_data_mesh.DATA_PT_vertex_colors.COMPAT_ENGINES.add("PLASMA_GAME")
del properties_data_mesh

def _whitelist_all(mod):
    for i in dir(mod):
        attr = getattr(mod, i)
        if hasattr(attr, "COMPAT_ENGINES"):
            getattr(attr, "COMPAT_ENGINES").add("PLASMA_GAME")

from bl_ui import properties_data_lamp
_whitelist_all(properties_data_lamp)
del properties_data_lamp

from bl_ui import properties_render
_whitelist_all(properties_render)
del properties_render

from bl_ui import properties_texture
_whitelist_all(properties_texture)
del properties_texture

@classmethod
def _new_poll(cls, context):
    """Nifty replacement for naughty built-in Blender poll()s"""
    if context.scene.render.engine == "PLASMA_GAME":
        return False
    else:
        # Dear god you better save the old poll...
        return cls._old_poll(cls, context)


def _swap_poll(cls):
    cls._old_poll = cls.poll
    cls.poll = _new_poll

# This is where we claim the physics context for our own nefarious purposes...
# Hmm... Physics panels don't respect the supported engine thing.
#        Metaprogramming to the rescue!
from bl_ui import properties_physics_common
_swap_poll(properties_physics_common.PhysicButtonsPanel)
del properties_physics_common
