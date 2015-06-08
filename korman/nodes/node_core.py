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

class PlasmaNodeBase:
    def find_input(self, key, idname=None):
        for i in self.inputs:
            if i.identifier == key:
                if i.links:
                    node = i.links[0].from_node
                    if idname is not None and idname != node.bl_idname:
                        return None
                    return node
                else:
                    return None
        raise KeyError(key)

    def find_input_socket(self, key):
        for i in self.inputs:
            if i.identifier == key:
                return i
        raise KeyError(key)

    def find_outputs(self, key, idname=None):
        for i in self.outputs:
            if i.identifier == key:
                for j in i.links:
                    node = j.to_node
                    if idname is not None and idname != node.bl_idname:
                        continue
                    yield node

    def find_output_socket(self, key):
        for i in self.outputs:
            if i.identifier == key:
                return i
        raise KeyError(key)

    def link_input(self, tree, node, out_key, in_key):
        """Links a given Node's output socket to a given input socket on this Node"""
        in_socket = self.find_input_socket(in_key)
        out_socket = node.find_output_socket(out_key)
        link = tree.links.new(in_socket, out_socket)

    def link_output(self, tree, node, out_key, in_key):
        """Links a given Node's input socket to a given output socket on this Node"""
        in_socket = node.find_input_socket(in_key)
        out_socket = self.find_output_socket(out_key)
        link = tree.links.new(in_socket, out_socket)

    @classmethod
    def poll(cls, context):
        return (context.bl_idname == "PlasmaNodeTree")


class PlasmaNodeSocketBase:
    def draw(self, context, layout, node, text):
        layout.label(text)

    def draw_color(self, context, node):
        # It's so tempting to just do RGB sometimes... Let's be nice.
        if len(self.bl_color) == 3:
            return tuple(self.bl_color[0], self.bl_color[1], self.bl_color[2], 1.0)
        return self.bl_color


class PlasmaNodeTree(bpy.types.NodeTree):
    bl_idname = "PlasmaNodeTree"
    bl_label = "Plasma"
    bl_icon = "NODETREE"

    @classmethod
    def poll(cls, context):
        return (context.scene.render.engine == "PLASMA_GAME")
