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

class PlasmaAdvancedLogic(PlasmaModifierProperties):
    pl_id = "advanced_logic"

    bl_category = "Logic"
    bl_label = "Advanced"
    bl_description = "Plasma Logic Nodes"
    bl_icon = "NODETREE"

    tree_name = StringProperty(name="Node Tree", description="Plasma Logic Nodes")

    def created(self, obj):
        self.display_name = "Advanced Logic"

    def export(self, exporter, bo, so):
        tree = bpy.data.node_groups[self.tree_name]
        tree.export(exporter, bo, so)

    @property
    def requires_actor(self):
        tree = bpy.data.node_groups[self.tree_name]
        return tree.requires_actor


class PlasmaSpawnPoint(PlasmaModifierProperties):
    pl_id = "spawnpoint"

    bl_category = "Logic"
    bl_label = "Spawn Point"
    bl_description = "Point at which avatars link into the Age"

    def created(self, obj):
        self.display_name = obj.name

    def export(self, exporter, bo, so):
        # Not much to this modifier... It's basically a flag that tells the engine, "hey, this is a
        # place the avatar can show up." Nice to have a simple one to get started with.
        spawn = exporter.mgr.add_object(pl=plSpawnModifier, so=so, name=self.display_name)

    @property
    def requires_actor(self):
        return True

class PlasmaMaintainersMarker(PlasmaModifierProperties):
    pl_id = "maintainersmarker"

    bl_category = "Logic"
    bl_label = "Maintainer's Marker"
    bl_description = "Designates an object as the D'ni coordinate origin point of the Age."
    bl_icon = "OUTLINER_DATA_EMPTY"

    calibration = EnumProperty(name="Calibration",
                               description="State of repair for the Marker",
                               items=[
                                  ("kBroken", "Broken",
                                   "A marker which reports scrambled coordinates to the KI."),
                                  ("kRepaired", "Repaired",
                                   "A marker which reports blank coordinates to the KI."),
                                  ("kCalibrated", "Calibrated",
                                   "A marker which reports accurate coordinates to the KI.")
                               ])

    def created(self, obj):
        self.display_name = obj.name

    def export(self, exporter, bo, so):
        maintmark = exporter.mgr.add_object(pl=plMaintainersMarkerModifier, so=so, name=self.display_name)
        maintmark.calibration = getattr(plMaintainersMarkerModifier, self.calibration)

    @property
    def requires_actor(self):
        return True
