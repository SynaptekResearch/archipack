# -*- coding:utf-8 -*-

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110- 1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

# ----------------------------------------------------------
# Author: Stephen Leger (s-leger)
#
# ----------------------------------------------------------
# noinspection PyUnresolvedReferences
import bpy
# noinspection PyUnresolvedReferences
from bpy.types import Operator, PropertyGroup, Mesh, Panel
from bpy.props import (
    FloatProperty, BoolProperty, IntProperty,
    StringProperty, EnumProperty,
    CollectionProperty
    )
import bmesh
from mathutils import Vector, Matrix
from mathutils.geometry import interpolate_bezier
from math import sin, cos, pi, atan2
from .archipack_manipulator import Manipulable, archipack_manipulator
from .archipack_object import ArchipackCreateTool, ArchipackObject
from .archipack_2d import Line, Arc


class Slab():

    def __init__(self):
        pass

    def straight_slab(self, a0, length):
        s = self.straight(length).rotate(a0)
        return StraightSlab(s.p, s.v)

    def curved_slab(self, a0, da, radius):
        n = self.normal(1).rotate(a0).scale(radius)
        if da < 0:
            n.v = -n.v
        a0 = n.angle
        c = n.p - n.v
        return CurvedSlab(c, radius, a0, da)


class StraightSlab(Slab, Line):

    def __init__(self, p, v):
        Slab.__init__(self)
        Line.__init__(self, p, v)


class CurvedSlab(Slab, Arc):

    def __init__(self, c, radius, a0, da):
        Slab.__init__(self)
        Arc.__init__(self, c, radius, a0, da)


class SlabGenerator():

    def __init__(self, parts):
        self.parts = parts
        self.segs = []

    def add_part(self, type, radius, a0, da, length, offset):

        if len(self.segs) < 1:
            s = None
        else:
            s = self.segs[-1]

        # start a new slab
        if s is None:
            if type == 'S_SEG':
                p = Vector((0, 0))
                v = length * Vector((cos(a0), sin(a0)))
                s = StraightSlab(p, v)
            elif type == 'C_SEG':
                c = -radius * Vector((cos(a0), sin(a0)))
                s = CurvedSlab(c, radius, a0, da)
        else:
            if type == 'S_SEG':
                s = s.straight_slab(a0, length)
            elif type == 'C_SEG':
                s = s.curved_slab(a0, da, radius)

        self.segs.append(s)
        self.last_type = type

    def close(self, closed):
        # Make last segment implicit closing one
        if closed:
            part = self.parts[-1]
            w = self.segs[-1]
            dp = self.segs[0].p0 - self.segs[-1].p0
            if "C_" in part.type:
                dw = (w.p1 - w.p0)
                w.r = part.radius / dw.length * dp.length
                # angle pt - p0        - angle p0 p1
                da = atan2(dp.y, dp.x) - atan2(dw.y, dw.x)
                a0 = w.a0 + da
                if a0 > pi:
                    a0 -= 2 * pi
                if a0 < -pi:
                    a0 += 2 * pi
                w.a0 = a0
            else:
                w.v = dp

    def locate_manipulators(self):
        """
            setup manipulators
        """
        for i, f in enumerate(self.segs):

            manipulators = self.parts[i].manipulators
            p0 = f.p0.to_3d()
            p1 = f.p1.to_3d()
            # angle from last to current segment
            if i > 0:
                v0 = self.segs[i - 1].straight(-1, 1).v.to_3d()
                v1 = f.straight(1, 0).v.to_3d()
                manipulators[0].set_pts([p0, v0, v1])

            if type(f).__name__ == "StraightSlab":
                # segment length
                manipulators[1].type_key = 'SIZE'
                manipulators[1].prop1_name = "length"
                manipulators[1].set_pts([p0, p1, (1, 0, 0)])
            else:
                # segment radius + angle
                v0 = (f.p0 - f.c).to_3d()
                v1 = (f.p1 - f.c).to_3d()
                manipulators[1].type_key = 'ARC_ANGLE_RADIUS'
                manipulators[1].prop1_name = "da"
                manipulators[1].prop2_name = "radius"
                manipulators[1].set_pts([f.c.to_3d(), v0, v1])

            # snap manipulator, dont change index !
            manipulators[2].set_pts([p0, p1, (1, 0, 0)])
            # dumb segment id
            manipulators[3].set_pts([p0, p1, (1, 0, 0)])

    def get_verts(self, verts):
        for slab in self.segs:
            if "Curved" in type(slab).__name__:
                for i in range(16):
                    x, y = slab.lerp(i / 16)
                    verts.append((x, y, 0))
            else:
                x, y = slab.p0
                verts.append((x, y, 0))
            """
            for i in range(33):
                x, y = slab.line.lerp(i / 32)
                verts.append((x, y, 0))
            """


def update(self, context):
    self.update(context)


def update_manipulators(self, context):
    self.update(context, manipulable_refresh=True)


def update_path(self, context):
    self.update_path(context)


materials_enum = (
            ('0', 'Ceiling', '', 0),
            ('1', 'White', '', 1),
            ('2', 'Concrete', '', 2),
            ('3', 'Wood', '', 3),
            ('4', 'Metal', '', 4),
            ('5', 'Glass', '', 5)
            )


class archipack_slab_material(PropertyGroup):
    index = EnumProperty(
        items=materials_enum,
        default='4',
        update=update
        )

    def find_in_selection(self, context):
        """
            find witch selected object this instance belongs to
            provide support for "copy to selected"
        """
        selected = [o for o in context.selected_objects]
        for o in selected:
            props = archipack_slab.datablock(o)
            if props:
                for part in props.rail_mat:
                    if part == self:
                        return props
        return None

    def update(self, context):
        props = self.find_in_selection(context)
        if props is not None:
            props.update(context)


class archipack_slab_child(PropertyGroup):
    """
        Store child fences to be able to sync
    """
    child_name = StringProperty()
    idx = IntProperty()

    def get_child(self, context):
        d = None
        child = context.scene.objects.get(self.child_name)
        if child is not None and child.data is not None:
            if 'archipack_fence' in child.data:
                d = child.data.archipack_fence[0]
        return child, d


def update_type(self, context):

    d = self.find_in_selection(context)

    if d is not None and d.auto_update:

        d.auto_update = False
        # find part index
        idx = 0
        for i, part in enumerate(d.parts):
            if part == self:
                idx = i
                break
        part = d.parts[idx]
        a0 = 0
        if idx > 0:
            g = d.get_generator()
            w0 = g.segs[idx - 1]
            a0 = w0.straight(1).angle
            if "C_" in self.type:
                w = w0.straight_slab(part.a0, part.length)
            else:
                w = w0.curved_slab(part.a0, part.da, part.radius)
        else:
            g = SlabGenerator(None)
            if "C_" in self.type:
                g.add_part("S_SEG", self.radius, self.a0, self.da, self.length, 0)
            else:
                g.add_part("C_SEG", self.radius, self.a0, self.da, self.length, 0)
            w = g.segs[0]

        # w0 - w - w1
        dp = w.p1 - w.p0
        if "C_" in self.type:
            part.radius = 0.5 * dp.length
            part.da = pi
            a0 = atan2(dp.y, dp.x) - pi / 2 - a0
        else:
            part.length = dp.length
            a0 = atan2(dp.y, dp.x) - a0

        if a0 > pi:
            a0 -= 2 * pi
        if a0 < -pi:
            a0 += 2 * pi
        part.a0 = a0

        if idx + 1 < d.n_parts:
            # adjust rotation of next part
            part1 = d.parts[idx + 1]
            if "C_" in part.type:
                a0 = part1.a0 - pi / 2
            else:
                a0 = part1.a0 + w.straight(1).angle - atan2(dp.y, dp.x)

            if a0 > pi:
                a0 -= 2 * pi
            if a0 < -pi:
                a0 += 2 * pi
            part1.a0 = a0

        d.auto_update = True


class ArchipackSegment():
    """
        A single manipulable polyline like segment
        polyline like segment line or arc based
        @TODO: share this base class with
        stair, wall, fence, slab
    """
    type = EnumProperty(
            items=(
                ('S_SEG', 'Straight', '', 0),
                ('C_SEG', 'Curved', '', 1),
                ),
            default='S_SEG',
            update=update_type
            )
    length = FloatProperty(
            name="length",
            min=0.01,
            default=2.0,
            update=update
            )
    radius = FloatProperty(
            name="radius",
            min=0.5,
            default=0.7,
            update=update
            )
    da = FloatProperty(
            name="angle",
            min=-pi,
            max=pi,
            default=pi / 2,
            subtype='ANGLE', unit='ROTATION',
            update=update
            )
    a0 = FloatProperty(
            name="start angle",
            min=-2 * pi,
            max=2 * pi,
            default=0,
            subtype='ANGLE', unit='ROTATION',
            update=update
            )
    manipulators = CollectionProperty(type=archipack_manipulator)

    def find_in_selection(self, context):
        raise NotImplementedError

    def update(self, context, manipulable_refresh=False):
        props = self.find_in_selection(context)
        if props is not None:
            props.update(context, manipulable_refresh)

    def draw_insert(self, context, layout, index):
        """
            May implement draw for insert / remove segment operators
        """
        pass

    def draw(self, context, layout, index):
        box = layout.box()
        row = box.row()
        row.prop(self, "type", text=str(index + 1))
        self.draw_insert(context, box, index)
        if self.type in ['C_SEG']:
            row = box.row()
            row.prop(self, "radius")
            row = box.row()
            row.prop(self, "da")
        else:
            row = box.row()
            row.prop(self, "length")
        row = box.row()
        row.prop(self, "a0")


class archipack_slab_part(ArchipackSegment, PropertyGroup):

    def draw_insert(self, context, layout, index):
        row = layout.row(align=True)
        row.operator("archipack.slab_insert", text="Split").index = index
        row.operator("archipack.slab_balcony", text="Balcony").index = index
        row.operator("archipack.slab_remove", text="Remove").index = index

    def find_in_selection(self, context):
        """
            find witch selected object this instance belongs to
            provide support for "copy to selected"
        """
        selected = [o for o in context.selected_objects]
        for o in selected:
            props = archipack_slab.datablock(o)
            if props:
                for part in props.parts:
                    if part == self:
                        return props
        return None


class archipack_slab(ArchipackObject, Manipulable, PropertyGroup):
    # boundary
    n_parts = IntProperty(
            name="parts",
            min=1,
            default=1, update=update_manipulators
            )
    parts = CollectionProperty(type=archipack_slab_part)
    closed = BoolProperty(
            default=False,
            name="Close",
            update=update_manipulators
            )
    # UI layout related
    parts_expand = BoolProperty(
            options={'SKIP_SAVE'},
            default=False
            )

    x_offset = FloatProperty(
            name="x offset",
            min=-1000, max=1000,
            default=0.0, precision=2, step=1,
            unit='LENGTH', subtype='DISTANCE',
            update=update
            )
    z = FloatProperty(
            name="z",
            default=0.3, precision=2, step=1,
            unit='LENGTH', subtype='DISTANCE',
            update=update
            )
    childs = CollectionProperty(type=archipack_slab_child)
    # Flag to prevent mesh update while making bulk changes over variables
    # use :
    # .auto_update = False
    # bulk changes
    # .auto_update = True
    auto_update = BoolProperty(
            options={'SKIP_SAVE'},
            default=True,
            update=update_manipulators
            )

    def get_generator(self):
        g = SlabGenerator(self.parts)
        for part in self.parts:
            # type, radius, da, length
            g.add_part(part.type, part.radius, part.a0, part.da, part.length, 0)

        g.close(self.closed)
        g.locate_manipulators()
        return g

    def insert_part(self, context, where):
        self.manipulable_disable(context)
        self.auto_update = False
        # the part we do split
        part_0 = self.parts[where]
        part_0.length /= 2
        part_0.da /= 2
        self.parts.add()
        part_1 = self.parts[len(self.parts) - 1]
        part_1.type = part_0.type
        part_1.length = part_0.length
        part_1.da = part_0.da
        part_1.a0 = 0
        # move after current one
        self.parts.move(len(self.parts) - 1, where + 1)
        self.n_parts += 1
        for c in self.childs:
            if c.idx > where:
                c.idx += 1
        self.setup_manipulators()
        self.auto_update = True

    def insert_balcony(self, context, where):
        self.manipulable_disable(context)
        self.auto_update = False

        # the part we do split
        part_0 = self.parts[where]
        part_0.length /= 3
        part_0.da /= 3

        # 1st part 90deg
        self.parts.add()
        part_1 = self.parts[len(self.parts) - 1]
        part_1.type = "S_SEG"
        part_1.length = 1.5
        part_1.da = part_0.da
        part_1.a0 = -pi / 2
        # move after current one
        self.parts.move(len(self.parts) - 1, where + 1)

        # 2nd part -90deg
        self.parts.add()
        part_1 = self.parts[len(self.parts) - 1]
        part_1.type = part_0.type
        part_1.length = part_0.length
        part_1.radius = part_0.radius + 1.5
        part_1.da = part_0.da
        part_1.a0 = pi / 2
        # move after current one
        self.parts.move(len(self.parts) - 1, where + 2)

        # 3nd part -90deg
        self.parts.add()
        part_1 = self.parts[len(self.parts) - 1]
        part_1.type = "S_SEG"
        part_1.length = 1.5
        part_1.da = part_0.da
        part_1.a0 = pi / 2
        # move after current one
        self.parts.move(len(self.parts) - 1, where + 3)

        # 4nd part -90deg
        self.parts.add()
        part_1 = self.parts[len(self.parts) - 1]
        part_1.type = part_0.type
        part_1.length = part_0.length
        part_1.radius = part_0.radius
        part_1.da = part_0.da
        part_1.a0 = -pi / 2
        # move after current one
        self.parts.move(len(self.parts) - 1, where + 4)

        self.n_parts += 4
        self.setup_manipulators()

        for c in self.childs:
            if c.idx > where:
                c.idx += 4

        self.auto_update = True
        g = self.get_generator()

        o = context.active_object
        bpy.ops.archipack.fence(auto_manipulate=False)
        c = context.active_object
        c.select = True
        c.data.archipack_fence[0].n_parts = 3
        c.select = False
        # link to o
        c.location = Vector((0, 0, 0))
        c.parent = o
        c.location = g.segs[where + 1].p0.to_3d()
        self.add_child(c.name, where + 1)
        # c.matrix_world.translation = g.segs[where].p1.to_3d()
        o.select = True
        context.scene.objects.active = o
        self.relocate_childs(context, o, g)

    def add_part(self, context, length):
        self.manipulable_disable(context)
        self.auto_update = False
        p = self.parts.add()
        p.length = length
        self.n_parts += 1
        self.setup_manipulators()
        self.auto_update = True
        return p

    def add_child(self, name, idx):
        c = self.childs.add()
        c.child_name = name
        c.idx = idx

    def setup_childs(self, o, g):
        """
            Store childs
            call after a boolean oop
        """
        # print("setup_childs")
        self.childs.clear()
        if o.parent is not None:
            otM = o.parent.matrix_world
        else:
            otM = Matrix()
        itM = o.matrix_world.inverted() * otM

        dmax = 0.2
        for c in o.children:
            if (c.data and 'archipack_fence' in c.data):
                pt = (itM * c.matrix_world.translation).to_2d()
                for idx, seg in enumerate(g.segs):
                    # may be optimized with a bound check
                    res, d, t = seg.point_sur_segment(pt)
                    #  p1
                    #  |-- x
                    #  p0
                    dist = abs(t) * seg.length
                    if dist < dmax and abs(d) < dmax:
                        print("%s %s %s %s" % (idx, dist, d, c.name))
                        self.add_child(c.name, idx)

    def relocate_childs(self, context, o, g):
        """
            Move and resize childs after edition
        """
        # print("relocate_childs")

        tM = o.matrix_world

        for child in self.childs:
            c, d = child.get_child(context)
            if c is None:
                print("c is None")
                continue

            a = g.segs[child.idx].angle
            x, y = g.segs[child.idx].p0
            sa = sin(a)
            ca = cos(a)

            if d is not None:
                c.select = True
                d.auto_update = False
                for i, part in enumerate(d.parts):
                    if "C_" in self.parts[i + child.idx].type:
                        part.type = "C_FENCE"
                    else:
                        part.type = "S_FENCE"
                    part.a0 = self.parts[i + child.idx].a0
                    part.da = self.parts[i + child.idx].da
                    part.length = self.parts[i + child.idx].length
                    part.radius = self.parts[i + child.idx].radius
                d.parts[0].a0 = pi / 2
                d.auto_update = True
                c.select = False

                context.scene.objects.active = o
                # preTranslate
                c.matrix_world = tM * Matrix([
                    [sa, ca, 0, x],
                    [-ca, sa, 0, y],
                    [0, 0, 1, 0],
                    [0, 0, 0, 1]
                ])

    def remove_part(self, context, where):
        self.manipulable_disable(context)
        self.auto_update = False

        # preserve shape
        # using generator
        if where > 0:

            g = self.get_generator()
            w = g.segs[where - 1]
            dp = g.segs[where].p1 - w.p0
            if where + 1 < self.n_parts:
                a0 = g.segs[where + 1].straight(1).angle - atan2(dp.y, dp.x)
                part = self.parts[where + 1]
                if a0 > pi:
                    a0 -= 2 * pi
                if a0 < -pi:
                    a0 += 2 * pi
                part.a0 = a0
            part = self.parts[where - 1]
            # adjust radius from distance between points..
            # use p0-p1 distance as reference
            if "C_" in part.type:
                dw = (w.p1 - w.p0)
                part.radius = part.radius / dw.length * dp.length
                # angle pt - p0        - angle p0 p1
                da = atan2(dp.y, dp.x) - atan2(dw.y, dw.x)
            else:
                part.length = dp.length
                da = atan2(dp.y, dp.x) - w.straight(1).angle
            a0 = part.a0 + da
            if a0 > pi:
                a0 -= 2 * pi
            if a0 < -pi:
                a0 += 2 * pi
            # print("a0:%.4f part.a0:%.4f da:%.4f" % (a0, part.a0, da))
            part.a0 = a0
        for c in self.childs:
            if c.idx >= where:
                c.idx -= 1
        self.parts.remove(where)
        self.n_parts -= 1
        # fix snap manipulators index
        self.setup_manipulators()
        self.auto_update = True

    def update_parts(self, o, update_childs=False):
        # print("update_parts")
        # remove rows
        # NOTE:
        # n_parts+1
        # as last one is end point of last segment or closing one
        row_change = False
        for i in range(len(self.parts), self.n_parts, -1):
            row_change = True
            self.parts.remove(i - 1)

        # add rows
        for i in range(len(self.parts), self.n_parts):
            row_change = True
            self.parts.add()

        self.setup_manipulators()

        g = self.get_generator()

        if o is not None and (row_change or update_childs):
            self.setup_childs(o, g)

        return g

    def setup_manipulators(self):

        if len(self.manipulators) < 1:
            s = self.manipulators.add()
            s.type_key = "SIZE"
            s.prop1_name = "z"
            s.normal = Vector((0, 1, 0))

        for i in range(self.n_parts):
            p = self.parts[i]
            n_manips = len(p.manipulators)
            if n_manips < 1:
                s = p.manipulators.add()
                s.type_key = "ANGLE"
                s.prop1_name = "a0"
            if n_manips < 2:
                s = p.manipulators.add()
                s.type_key = "SIZE"
                s.prop1_name = "length"
            if n_manips < 3:
                s = p.manipulators.add()
                s.type_key = 'WALL_SNAP'
                s.prop1_name = str(i)
                s.prop2_name = 'z'
            if n_manips < 4:
                s = p.manipulators.add()
                s.type_key = 'DUMB_STRING'
                s.prop1_name = str(i + 1)
            p.manipulators[2].prop1_name = str(i)
            p.manipulators[3].prop1_name = str(i + 1)

        self.parts[-1].manipulators[0].type_key = 'DUMB_ANGLE'

    def is_cw(self, pts):
        p0 = pts[0]
        d = 0
        for p in pts[1:]:
            d += (p.x * p0.y - p.y * p0.x)
            p0 = p
        return d > 0

    def interpolate_bezier(self, pts, wM, p0, p1, resolution):
        # straight segment, worth testing here
        # since this can lower points count by a resolution factor
        # use normalized to handle non linear t
        if resolution == 0:
            pts.append(wM * p0.co.to_3d())
        else:
            v = (p1.co - p0.co).normalized()
            d1 = (p0.handle_right - p0.co).normalized()
            d2 = (p1.co - p1.handle_left).normalized()
            if d1 == v and d2 == v:
                pts.append(wM * p0.co.to_3d())
            else:
                seg = interpolate_bezier(wM * p0.co,
                    wM * p0.handle_right,
                    wM * p1.handle_left,
                    wM * p1.co,
                    resolution + 1)
                for i in range(resolution):
                    pts.append(seg[i].to_3d())

    def from_spline(self, wM, resolution, spline):
        pts = []
        if spline.type == 'POLY':
            pts = [wM * p.co.to_3d() for p in spline.points]
            if spline.use_cyclic_u:
                pts.append(pts[0])
        elif spline.type == 'BEZIER':
            points = spline.bezier_points
            for i in range(1, len(points)):
                p0 = points[i - 1]
                p1 = points[i]
                self.interpolate_bezier(pts, wM, p0, p1, resolution)
            pts.append(wM * points[-1].co)
            if spline.use_cyclic_u:
                p0 = points[-1]
                p1 = points[0]
                self.interpolate_bezier(pts, wM, p0, p1, resolution)
                pts.append(pts[0])

        if self.is_cw(pts):
            pts = list(reversed(pts))

        self.auto_update = False

        self.n_parts = len(pts) - 1
        self.update_parts(None)

        p0 = pts.pop(0)
        a0 = 0
        for i, p1 in enumerate(pts):
            dp = p1 - p0
            da = atan2(dp.y, dp.x) - a0
            if da > pi:
                da -= 2 * pi
            if da < -pi:
                da += 2 * pi
            p = self.parts[i]
            p.length = dp.to_2d().length
            p.dz = dp.z
            p.a0 = da
            a0 += da
            p0 = p1
        self.closed = True
        self.auto_update = True

    def make_surface(self, o, verts):
        bm = bmesh.new()
        for v in verts:
            bm.verts.new(v)
        bm.verts.ensure_lookup_table()
        for i in range(1, len(verts)):
            bm.edges.new((bm.verts[i - 1], bm.verts[i]))
        bm.edges.new((bm.verts[-1], bm.verts[0]))
        bm.edges.ensure_lookup_table()
        bmesh.ops.contextual_create(bm, geom=bm.edges)
        bm.to_mesh(o.data)
        bm.free()

    def unwrap_uv(self, o):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        for face in bm.faces:
            face.select = face.material_index > 0
        bm.to_mesh(o.data)
        bpy.ops.uv.cube_project(scale_to_bounds=False, correct_aspect=True)

        for face in bm.faces:
            face.select = face.material_index < 1
        bm.to_mesh(o.data)
        bpy.ops.uv.smart_project(use_aspect=True, stretch_to_bounds=False)
        bm.free()

    def update(self, context, manipulable_refresh=False, update_childs=False):

        active, selected, o = self.find_in_selection(context)

        if o is None or not self.auto_update:
            return

        # clean up manipulators before any data model change
        if manipulable_refresh:
            self.manipulable_disable(context)

        g = self.update_parts(o, update_childs)

        verts = []

        g.get_verts(verts)
        if len(verts) > 2:
            self.make_surface(o, verts)

        modif = o.modifiers.get('Slab')
        if modif is None:
            modif = o.modifiers.new('Slab', 'SOLIDIFY')
            modif.use_quality_normals = True
            modif.use_even_offset = True
            modif.material_offset_rim = 2
            modif.material_offset = 1

        modif.thickness = self.z
        modif.offset = 1.0

        # Height
        self.manipulators[0].set_pts([
            (0, 0, 0),
            (0, 0, -self.z),
            (-1, 0, 0)
            ], normal=g.segs[0].straight(-1, 0).v.to_3d())

        self.relocate_childs(context, o, g)

        # enable manipulators rebuild
        if manipulable_refresh:
            self.manipulable_refresh = True

        # restore context
        try:
            for o in selected:
                o.select = True
        except:
            pass

        active.select = True
        context.scene.objects.active = active

    def manipulable_setup(self, context):
        """
            TODO: Implement the setup part as per parent object basis

            self.manipulable_disable(context)
            o = context.active_object
            for m in self.manipulators:
                self.manip_stack.append(m.setup(context, o, self))

        """
        self.manipulable_disable(context)
        o = context.active_object
        d = self

        self.setup_manipulators()

        for i, part in enumerate(d.parts):
            if i >= d.n_parts:
                break

            if i > 0:
                # start angle
                self.manip_stack.append(part.manipulators[0].setup(context, o, part))

            # length / radius + angle
            self.manip_stack.append(part.manipulators[1].setup(context, o, part))

            # snap point
            self.manip_stack.append(part.manipulators[2].setup(context, o, d))
            # index
            self.manip_stack.append(part.manipulators[3].setup(context, o, d))

        for m in self.manipulators:
            self.manip_stack.append(m.setup(context, o, self))

    def manipulable_invoke(self, context):
        """
            call this in operator invoke()
        """
        # print("manipulable_invoke")
        if self.manipulate_mode:
            self.manipulable_disable(context)
            self.manipulate_mode = False
            return False

        self.manip_stack = []
        o = context.active_object
        g = self.get_generator()
        # setup childs manipulators
        self.setup_childs(o, g)
        self.manipulable_setup(context)
        self.manipulate_mode = True

        self._manipulable_invoke(context)

        return True


class ARCHIPACK_PT_slab(Panel):
    """Archipack Slab"""
    bl_idname = "ARCHIPACK_PT_slab"
    bl_label = "Slab"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # bl_context = 'object'
    bl_category = 'ArchiPack'

    @classmethod
    def poll(cls, context):
        return archipack_slab.filter(context.active_object)

    def draw(self, context):
        prop = archipack_slab.datablock(context.active_object)
        if prop is None:
            return
        layout = self.layout
        row = layout.row(align=True)
        # self.set_context_3dview(context, row)
        row.operator('archipack.slab_manipulate', icon='HAND')
        box = layout.box()
        box.prop(prop, 'z')
        box = layout.box()
        row = box.row()
        if prop.parts_expand:
            row.prop(prop, 'parts_expand', icon="TRIA_DOWN", icon_only=True, text="Parts", emboss=False)
            box.prop(prop, 'n_parts')
            # box.prop(prop, 'closed')
            for i, part in enumerate(prop.parts):
                part.draw(context, layout, i)
        else:
            row.prop(prop, 'parts_expand', icon="TRIA_RIGHT", icon_only=True, text="Parts", emboss=False)


# ------------------------------------------------------------------
# Define operator class to create object
# ------------------------------------------------------------------


class ARCHIPACK_OT_slab_insert(Operator):
    bl_idname = "archipack.slab_insert"
    bl_label = "Insert"
    bl_description = "Insert part"
    bl_category = 'Archipack'
    bl_options = {'REGISTER', 'UNDO'}
    index = IntProperty(default=0)

    def execute(self, context):
        if context.mode == "OBJECT":
            d = archipack_slab.datablock(context.active_object)
            if d is None:
                return {'CANCELLED'}
            d.insert_part(context, self.index)
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Archipack: Option only valid in Object mode")
            return {'CANCELLED'}


class ARCHIPACK_OT_slab_balcony(Operator):
    bl_idname = "archipack.slab_balcony"
    bl_label = "Insert"
    bl_description = "Insert part"
    bl_category = 'Archipack'
    bl_options = {'REGISTER', 'UNDO'}
    index = IntProperty(default=0)

    def execute(self, context):
        if context.mode == "OBJECT":
            d = archipack_slab.datablock(context.active_object)
            if d is None:
                return {'CANCELLED'}
            d.insert_balcony(context, self.index)
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Archipack: Option only valid in Object mode")
            return {'CANCELLED'}


class ARCHIPACK_OT_slab_remove(Operator):
    bl_idname = "archipack.slab_remove"
    bl_label = "Remove"
    bl_description = "Remove part"
    bl_category = 'Archipack'
    bl_options = {'REGISTER', 'UNDO'}
    index = IntProperty(default=0)

    def execute(self, context):
        if context.mode == "OBJECT":
            d = archipack_slab.datablock(context.active_object)
            if d is None:
                return {'CANCELLED'}
            d.remove_part(context, self.index)
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Archipack: Option only valid in Object mode")
            return {'CANCELLED'}


# ------------------------------------------------------------------
# Define operator class to create object
# ------------------------------------------------------------------


class ARCHIPACK_OT_slab(ArchipackCreateTool, Operator):
    bl_idname = "archipack.slab"
    bl_label = "Slab"
    bl_description = "Slab"
    bl_category = 'Archipack'
    bl_options = {'REGISTER', 'UNDO'}

    def create(self, context):
        m = bpy.data.meshes.new("Slab")
        o = bpy.data.objects.new("Slab", m)
        d = m.archipack_slab.add()
        # make manipulators selectable
        d.manipulable_selectable = True
        context.scene.objects.link(o)
        o.select = True
        context.scene.objects.active = o
        self.load_preset(d)
        self.add_material(o)
        return o

    # -----------------------------------------------------
    # Execute
    # -----------------------------------------------------
    def execute(self, context):
        if context.mode == "OBJECT":
            bpy.ops.object.select_all(action="DESELECT")
            o = self.create(context)
            o.location = bpy.context.scene.cursor_location
            o.select = True
            context.scene.objects.active = o
            self.manipulate()
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Archipack: Option only valid in Object mode")
            return {'CANCELLED'}


class ARCHIPACK_OT_slab_from_curve(Operator):
    bl_idname = "archipack.slab_from_curve"
    bl_label = "Slab curve"
    bl_description = "Create a slab from a curve"
    bl_category = 'Archipack'
    bl_options = {'REGISTER', 'UNDO'}

    auto_manipulate = BoolProperty(default=True)

    @classmethod
    def poll(self, context):
        return context.active_object is not None and context.active_object.type == 'CURVE'
    # -----------------------------------------------------
    # Draw (create UI interface)
    # -----------------------------------------------------
    # noinspection PyUnusedLocal

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.label("Use Properties panel (N) to define parms", icon='INFO')

    def create(self, context):
        curve = context.active_object
        bpy.ops.archipack.slab(auto_manipulate=self.auto_manipulate)
        o = context.scene.objects.active
        d = archipack_slab.datablock(o)
        spline = curve.data.splines[0]
        d.from_spline(curve.matrix_world, 12, spline)
        if spline.type == 'POLY':
            pt = spline.points[0].co
        elif spline.type == 'BEZIER':
            pt = spline.bezier_points[0].co
        else:
            pt = Vector((0, 0, 0))
        # pretranslate
        o.matrix_world = curve.matrix_world * Matrix([
            [1, 0, 0, pt.x],
            [0, 1, 0, pt.y],
            [0, 0, 1, pt.z],
            [0, 0, 0, 1]
            ])
        return o

    # -----------------------------------------------------
    # Execute
    # -----------------------------------------------------
    def execute(self, context):
        if context.mode == "OBJECT":
            bpy.ops.object.select_all(action="DESELECT")
            self.create(context)
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Archipack: Option only valid in Object mode")
            return {'CANCELLED'}


class ARCHIPACK_OT_slab_from_wall(Operator):
    bl_idname = "archipack.slab_from_wall"
    bl_label = "Wall -> Slab"
    bl_description = "Create a slab from a wall"
    bl_category = 'Archipack'
    bl_options = {'REGISTER', 'UNDO'}

    auto_manipulate = BoolProperty(default=True)

    @classmethod
    def poll(self, context):
        o = context.active_object
        return o is not None and o.data is not None and 'archipack_wall2' in o.data

    def create(self, context):
        wall = context.active_object
        wd = wall.data.archipack_wall2[0]
        bpy.ops.archipack.slab(auto_manipulate=self.auto_manipulate)
        o = context.scene.objects.active
        d = archipack_slab.datablock(o)
        d.auto_update = False
        d.closed = True
        d.parts.clear()
        d.n_parts = wd.n_parts + 1
        for part in wd.parts:
            p = d.parts.add()
            if "S_" in part.type:
                p.type = "S_SEG"
            else:
                p.type = "C_SEG"
            p.length = part.length
            p.radius = part.radius
            p.da = part.da
            p.a0 = part.a0
        d.auto_update = True
        # pretranslate
        o.matrix_world = wall.matrix_world.copy()
        return o

    # -----------------------------------------------------
    # Execute
    # -----------------------------------------------------
    def execute(self, context):
        if context.mode == "OBJECT":
            bpy.ops.object.select_all(action="DESELECT")
            self.create(context)
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Archipack: Option only valid in Object mode")
            return {'CANCELLED'}


# ------------------------------------------------------------------
# Define operator class to manipulate object
# ------------------------------------------------------------------


class ARCHIPACK_OT_slab_manipulate(Operator):
    bl_idname = "archipack.slab_manipulate"
    bl_label = "Manipulate"
    bl_description = "Manipulate"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(self, context):
        return archipack_slab.filter(context.active_object)

    def invoke(self, context, event):
        d = archipack_slab.datablock(context.active_object)
        d.manipulable_invoke(context)
        return {'FINISHED'}


def register():
    bpy.utils.register_class(archipack_slab_material)
    bpy.utils.register_class(archipack_slab_child)
    bpy.utils.register_class(archipack_slab_part)
    bpy.utils.register_class(archipack_slab)
    Mesh.archipack_slab = CollectionProperty(type=archipack_slab)
    bpy.utils.register_class(ARCHIPACK_PT_slab)
    bpy.utils.register_class(ARCHIPACK_OT_slab)
    bpy.utils.register_class(ARCHIPACK_OT_slab_insert)
    bpy.utils.register_class(ARCHIPACK_OT_slab_balcony)
    bpy.utils.register_class(ARCHIPACK_OT_slab_remove)
    # bpy.utils.register_class(ARCHIPACK_OT_slab_manipulate_ctx)
    bpy.utils.register_class(ARCHIPACK_OT_slab_manipulate)
    bpy.utils.register_class(ARCHIPACK_OT_slab_from_curve)
    bpy.utils.register_class(ARCHIPACK_OT_slab_from_wall)


def unregister():
    bpy.utils.unregister_class(archipack_slab_material)
    bpy.utils.unregister_class(archipack_slab_child)
    bpy.utils.unregister_class(archipack_slab_part)
    bpy.utils.unregister_class(archipack_slab)
    del Mesh.archipack_slab
    bpy.utils.unregister_class(ARCHIPACK_PT_slab)
    bpy.utils.unregister_class(ARCHIPACK_OT_slab)
    bpy.utils.unregister_class(ARCHIPACK_OT_slab_insert)
    bpy.utils.unregister_class(ARCHIPACK_OT_slab_balcony)
    bpy.utils.unregister_class(ARCHIPACK_OT_slab_remove)
    # bpy.utils.unregister_class(ARCHIPACK_OT_slab_manipulate_ctx)
    bpy.utils.unregister_class(ARCHIPACK_OT_slab_manipulate)
    bpy.utils.unregister_class(ARCHIPACK_OT_slab_from_curve)
    bpy.utils.unregister_class(ARCHIPACK_OT_slab_from_wall)