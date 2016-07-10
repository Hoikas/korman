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

def fademod(modifier, layout, context):
    layout.prop(modifier, "fader_type")

    if modifier.fader_type == "DistOpacity":
        col = layout.column(align=True)
        col.prop(modifier, "near_trans")
        col.prop(modifier, "near_opaq")
        col.prop(modifier, "far_opaq")
        col.prop(modifier, "far_trans")
    elif modifier.fader_type == "FadeOpacity":
        col = layout.column(align=True)
        col.prop(modifier, "fade_in_time")
        col.prop(modifier, "fade_out_time")
        col.separator()
        col.prop(modifier, "bounds_center")
    elif modifier.fader_type == "SimpleDist":
        col = layout.column(align=True)
        col.prop(modifier, "far_opaq")
        col.prop(modifier, "far_trans")

    if not (modifier.near_trans <= modifier.near_opaq <= modifier.far_opaq <= modifier.far_trans):
        # Warn the user that the values are not recommended.
        layout.label("Distance values must be equal or increasing!", icon="ERROR")

def followmod(modifier, layout, context):
    layout.row().prop(modifier, "follow_mode", expand=True)
    layout.prop(modifier, "leader_type")
    if modifier.leader_type == "kFollowObject":
        layout.prop_search(modifier, "leader_object", bpy.data, "objects", icon="OUTLINER_OB_MESH")

def lighting(modifier, layout, context):
    split = layout.split()
    col = split.column()
    col.prop(modifier, "force_rt_lights")
    col = split.column()
    col.active = modifier.allow_preshade
    col.prop(modifier, "force_preshade")
    layout.separator()

    lightmap = modifier.id_data.plasma_modifiers.lightmap
    is_aomapped = lightmap.enabled and lightmap.bake_aomap
    is_lightmapped = lightmap.enabled and lightmap.bake_lightmap
    have_static_lights = lightmap.enabled or modifier.preshade

    col = layout.column(align=True)
    col.label("Plasma Lighting Summary:")
    if modifier.rt_lights and have_static_lights:
        col.label(" You have unleashed Satan!", icon="GHOST_ENABLED")
    else:
        col.label(" Satan remains ensconced deep in the abyss...", icon="GHOST_ENABLED")
    col.label("Animated lights will be cast at runtime.", icon="LAYER_USED")
    col.label("Projection lights will be cast at runtime.", icon="LAYER_USED")
    col.label("Specular lights will be cast to specular materials at runtime.", icon="LAYER_USED")
    col.label("Other Plasma lights {} be cast at runtime.".format("will" if modifier.rt_lights else "will NOT"),
              icon="LAYER_USED")

    if is_aomapped:
        col.label("Ambient lighting will be baked into an AOmap", icon="LAYER_USED")
    else:
        col.label("Ambient lighting will NOT be baked into an AOmap", icon="LAYER_USED")

    if is_lightmapped and lightmap.light_group:
            col.label("All '{}' lights will be baked to a lightmap".format(lightmap.light_group),
                      icon="LAYER_USED")
    elif have_static_lights:
        light_type = "Blender-only" if modifier.rt_lights else "unanimated"
        map_type = "a lightmap" if is_lightmapped else "vertex colors"
        col.label("Other {} lights will be baked to {}.".format(light_type, map_type), icon="LAYER_USED")
    else:
        col.label("No static lights will be baked.", icon="LAYER_USED")

def lightmap(modifier, layout, context):
    split = layout.split()
    col = split.column()
    col.prop(modifier, "bake_lightmap")
    col.prop(modifier, "bake_aomap")
    col = split.column()
    col.label("Quality:")
    col.prop(modifier, "quality", text="")
    layout.separator()

    col = layout.column()
    col.active = modifier.bake_lightmap or modifier.bake_aomap
    col.prop(modifier, "render_layers", text="Active Render Layers")
    col.separator()
    col.separator()

    row = col.row()
    row.active = modifier.bake_lightmap
    row.prop_search(modifier, "light_group", bpy.data, "groups", icon="GROUP")
    col.prop_search(modifier, "uv_map", context.active_object.data, "uv_textures")
    operator = layout.operator("object.plasma_lightmap_preview", "Preview Lightmap", icon="RENDER_STILL")

    # Kind of clever stuff to show the user a preview...
    # We can't show images, so we make a hidden ImageTexture called LIGHTMAPGEN_PREVIEW. We check
    # the backing image name to see if it's for this lightmap. If so, you have a preview. If not,
    # well... It was nice knowing you!
    def _show_preview(layout, context, preview_type):
        tex = bpy.data.textures.get("{}_PREVIEW".format(preview_type))
        print(tex.name)
        if tex is not None and tex.image is not None:
            im_name = "{}_{}.png".format(context.active_object.name, preview_type)
            if tex.image.name == im_name:
                row.template_preview(tex, show_buttons=False)

    row = layout.row(align=True)
    _show_preview(row, context, "LIGHTMAPGEN")
    _show_preview(row, context, "AOMAPGEN")


def viewfacemod(modifier, layout, context):
    layout.prop(modifier, "preset_options")

    if modifier.preset_options == "Custom":
        layout.row().prop(modifier, "follow_mode")
        if modifier.follow_mode == "kFaceObj":
            layout.prop_search(modifier, "target_object", bpy.data, "objects", icon="OUTLINER_OB_MESH")
            layout.separator()

        layout.prop(modifier, "pivot_on_y")
        layout.separator()

        split = layout.split()
        col = split.column()
        col.prop(modifier, "offset")
        row = col.row()
        row.enabled = modifier.offset
        row.prop(modifier, "offset_local")

        col = split.column()
        col.enabled = modifier.offset
        col.prop(modifier, "offset_coord")

class VisRegionListUI(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index=0, flt_flag=0):
        myIcon = "ERROR" if bpy.data.objects.get(item.region_name, None) is None else "OBJECT_DATA"
        label = item.region_name if item.region_name else "[No Object Specified]"
        layout.label(label, icon=myIcon)
        layout.prop(item, "enabled", text="")


def visibility(modifier, layout, context):
    row = layout.row()
    row.template_list("VisRegionListUI", "regions", modifier, "regions", modifier, "active_region_index",
                      rows=2, maxrows=3)
    col = row.column(align=True)
    op = col.operator("object.plasma_modifier_collection_add", icon="ZOOMIN", text="")
    op.modifier = modifier.pl_id
    op.collection = "regions"
    op = col.operator("object.plasma_modifier_collection_remove", icon="ZOOMOUT", text="")
    op.modifier = modifier.pl_id
    op.collection = "regions"
    op.index = modifier.active_region_index

    if modifier.regions:
        layout.prop_search(modifier.regions[modifier.active_region_index], "region_name", bpy.data, "objects")

def visregion(modifier, layout, context):
    layout.prop(modifier, "mode")

    # Only allow SoftVolume spec if this is not an FX and this object is not an SV itself
    sv = modifier.id_data.plasma_modifiers.softvolume
    if modifier.mode != "fx" and not sv.enabled:
        layout.prop_search(modifier, "softvolume", bpy.data, "objects")

    # Other settings
    layout.prop(modifier, "replace_normal")
