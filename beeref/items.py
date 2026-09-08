# This file is part of BeeRef.
#
# BeeRef is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BeeRef is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BeeRef.  If not, see <https://www.gnu.org/licenses/>.

"""Classes for items that are added to the scene by the user (images,
text).
"""

from collections import defaultdict
import datetime
from functools import cached_property
import logging
import math
import os.path
import re

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref import commands
from beeref.assets import BeeAssets
from beeref.config import BeeSettings
from beeref.constants import COLORS, CORNER_RADIUS
from beeref.selection import SelectableMixin
from beeref.utils import blend_over, readable_grey


logger = logging.getLogger(__name__)

item_registry = {}


def register_item(cls):
    item_registry[cls.TYPE] = cls
    return cls


def sort_by_filename(items):
    """Order items by filename.

    Items with a filename (ordered by filename) first, then items
    without a filename but with a save_id follow (ordered by
    save_id), then remaining items in the order that they have
    been inserted into the scene.
    """

    items_by_filename = []
    items_by_save_id = []
    items_remaining = []

    for item in items:
        if getattr(item, 'filename', None):
            items_by_filename.append(item)
        elif getattr(item, 'save_id', None):
            items_by_save_id.append(item)
        else:
            items_remaining.append(item)

    items_by_filename.sort(key=lambda x: x.filename)
    items_by_save_id.sort(key=lambda x: x.save_id)
    return items_by_filename + items_by_save_id + items_remaining


# A picture with fewer see-through pixels than this is treated as
# having none. Antialiasing along an edge leaves a few; a picture that
# really is cut out leaves a great many.
OPAQUE_ENOUGH = 0.995


def half_rounded_path(rect, radius, top):
    """A rectangle with two of its corners taken off.

    The other two stay square, because that end meets something: a
    title band meets the note under it, a caption band the picture
    above it, and rounding both sides of a join leaves the canvas
    showing through it.
    """

    path = QtGui.QPainterPath()
    radius = min(radius, rect.height(), rect.width() / 2)
    if radius <= 0:
        path.addRect(rect)
        return path
    if top:
        path.moveTo(rect.left(), rect.bottom())
        path.lineTo(rect.left(), rect.top() + radius)
        path.quadTo(rect.topLeft(),
                    QtCore.QPointF(rect.left() + radius, rect.top()))
        path.lineTo(rect.right() - radius, rect.top())
        path.quadTo(rect.topRight(),
                    QtCore.QPointF(rect.right(), rect.top() + radius))
        path.lineTo(rect.right(), rect.bottom())
    else:
        path.moveTo(rect.topLeft())
        path.lineTo(rect.topRight())
        path.lineTo(rect.right(), rect.bottom() - radius)
        path.quadTo(rect.bottomRight(),
                    QtCore.QPointF(rect.right() - radius, rect.bottom()))
        path.lineTo(rect.left() + radius, rect.bottom())
        path.quadTo(rect.bottomLeft(),
                    QtCore.QPointF(rect.left(), rect.bottom() - radius))
    path.closeSubpath()
    return path


def without_pointless_alpha(image):
    """The picture with its alpha channel dropped when nothing uses it.

    A screenshot arrives with an alpha channel whether or not anything
    in it is see-through, and the storage format is chosen by whether
    that channel is there. A handful of half-transparent pixels along
    an antialiased edge was enough to have a ten-megapixel screenshot
    kept as PNG: on a board of them that came to three and a quarter
    gigabytes where JPEG would have taken thirty megabytes, and the
    pictures measured 99.97% opaque.

    A picture that really does use transparency keeps it, and so does
    every picture when the storage format has been asked for by name
    rather than left to be chosen.
    """

    if image.isNull() or not image.hasAlphaChannel():
        return image
    if BeeSettings().valueOrDefault('Items/image_storage_format') != 'best':
        return image

    alpha = image.convertToFormat(QtGui.QImage.Format.Format_Alpha8)
    data = alpha.constBits()
    data.setsize(alpha.sizeInBytes())
    values = bytes(data)
    width, height, line = alpha.width(), alpha.height(), alpha.bytesPerLine()
    if not width or not height:
        return image
    # Row by row: a row is padded out to a multiple of four bytes, and
    # counting the padding would make a narrow picture look see-through
    opaque = sum(values[y * line:y * line + width].count(255)
                 for y in range(height))
    if opaque / (width * height) < OPAQUE_ENOUGH:
        return image
    logger.debug('Dropping an alpha channel that nothing uses')
    return image.convertToFormat(QtGui.QImage.Format.Format_RGB32)


class BeeItemMixin(SelectableMixin):
    """Base for all items added by the user."""

    # A name given by the user, shown in the layers panel. Items fall
    # back to a description of their contents when this isn't set.
    name = None

    def even_stroke(self, painter):
        """Move the painter to a space whose axes scale alike.

        Dragging an edge stretches an item, and a stretch is a scale
        that differs by axis, so everything the item paints is stretched
        with it -- a line included. A circle pulled three times wider
        came out with a line three times thicker down its sides than
        across its top.

        Undoing the stretch on the painter and putting it on the
        geometry instead leaves the shape distorted, which is what was
        asked for, and the line even, which is what a line should be.
        Returns the factors the geometry has to be scaled by, or None
        when there is nothing to correct -- in which case the painter is
        untouched and must not be restored.
        """

        across, down = self.stretch
        if across <= 0 or down <= 0 or abs(across - down) < 1e-9:
            return None
        painter.save()
        painter.scale(1 / across, 1 / down)
        return across, down

    def get_display_name(self):
        """The name to show for this item in the layers panel."""

        return self.name or self.get_default_name()

    def get_default_name(self):
        return 'Item'

    def set_pos_center(self, pos):
        """Sets the position using the item's center as the origin point."""

        self.setPos(pos - self.center_scene_coords)

    def has_selection_outline(self):
        return self.isSelected()

    def has_selection_handles(self):
        return (self.isSelected()
                and self.scene()
                and self.scene().has_single_selection())

    def selection_action_items(self):
        """The items affected by selection actions like scaling and rotating.
        """
        return [self]

    def get_save_data(self):
        """The item's data for saving, including its group membership."""

        data = self.get_extra_save_data()
        if self.name:
            data['name'] = self.name
        stretch = self.stretch
        if stretch != (1, 1):
            # Only written when the item has been stretched, so files
            # without it are unaffected
            data['stretch'] = list(stretch)
        parent = self.parentItem()
        # Any item that is saved can hold another: a group holds what
        # was grouped, and a picture holds what was sketched on it
        if getattr(parent, 'save_id', None) is not None:
            data['parent_group'] = parent.save_id
        return data

    def update_from_data(self, **kwargs):
        self.save_id = kwargs.get('save_id', self.save_id)
        self.name = kwargs.get('data', {}).get('name', self.name)
        self.setPos(kwargs.get('x', self.pos().x()),
                    kwargs.get('y', self.pos().y()))
        self.setZValue(kwargs.get('z', self.zValue()))
        self.setScale(kwargs.get('scale', self.scale()))
        self.setRotation(kwargs.get('rotation', self.rotation()))
        if kwargs.get('flip', 1) != self.flip():
            self.do_flip()
        stretch = kwargs.get('data', {}).get('stretch')
        if stretch:
            self.set_stretch(*stretch)


@register_item
class BeeDrawItem(BeeItemMixin, QtWidgets.QGraphicsItem):
    """Something drawn by hand: a sketch, a line, a curve or an arrow."""

    TYPE = 'draw'

    SKETCH = 'sketch'
    LINE = 'line'
    SPLINE = 'spline'
    ARROW = 'arrow'
    SPLINE_ARROW = 'spline_arrow'
    CIRCLE = 'circle'
    SQUARE = 'square'
    TRIANGLE = 'triangle'
    PENTAGON = 'pentagon'
    HEXAGON = 'hexagon'
    # Drawn by dragging out a box rather than by following the hand,
    # and closed, so they have no ends to fasten to anything
    SHAPES = (CIRCLE, SQUARE, TRIANGLE, PENTAGON, HEXAGON)
    # The drawings that fasten themselves to what they are drawn
    # against. A sketch follows the hand rather than being aimed from
    # one thing to another, so it stays free of everything.
    FASTENING = (LINE, SPLINE, ARROW, SPLINE_ARROW)
    # How many sides each of them has; a circle has none
    SHAPE_SIDES = {TRIANGLE: 3, SQUARE: 4, PENTAGON: 5, HEXAGON: 6}
    KINDS = (SKETCH, LINE, SPLINE, ARROW, SPLINE_ARROW) + SHAPES

    NAMES = {
        SKETCH: 'Sketch',
        LINE: 'Line',
        SPLINE: 'Curve',
        ARROW: 'Arrow',
        SPLINE_ARROW: 'Curved Arrow',
        CIRCLE: 'Circle',
        SQUARE: 'Square',
        TRIANGLE: 'Triangle',
        PENTAGON: 'Pentagon',
        HEXAGON: 'Hexagon',
    }

    DEFAULT_COLOR = (235, 235, 235, 255)
    DEFAULT_WIDTH = 4
    # A line thinner than this disappears. The upper limit is a
    # floor for short drawings; see max_line_width.
    MIN_WIDTH = 0.5
    MAX_WIDTH = 400
    # Length of the arrow head, as a multiple of the line width
    ARROW_SIZE = 4

    def __init__(self, points=None, kind=SKETCH, color=None,
                 width=None, ends=None, **kwargs):
        super().__init__()
        self.save_id = None
        self.is_image = False
        self.init_selectable()
        self.is_editable = False
        self.kind = kind if kind in self.KINDS else self.SKETCH
        self.color = QtGui.QColor(*(color or self.DEFAULT_COLOR))
        self.line_width = width or self.DEFAULT_WIDTH
        # Ends fastened to other items; see attach_end
        self.ends = {}
        self.pending_ends = ends or {}
        self.set_points(points or [])
        logger.debug(f'Initialized {self}')

    def __str__(self):
        return f'{self.NAMES[self.kind]} ({len(self.points)} points)'

    def get_default_name(self):
        return self.NAMES[self.kind]

    def fastens(self):
        """Whether this drawing takes hold of what it is drawn against."""

        return self.kind in self.FASTENING

    def max_line_width(self):
        """The thickest this drawing may be drawn.

        A fixed number used to be the whole of it, but the thickness is
        in item coordinates and a stroke is created relative to the
        zoom it was drawn at: on a board zoomed well out, a line
        reached the limit while it was still twenty pixels on screen.
        A line is a blob once it is thicker than it is long, so the
        drawing's own reach is what decides.
        """

        reach = self.path.boundingRect()
        return max(self.MAX_WIDTH, reach.width(), reach.height())

    def set_line_width(self, width):
        """Set how thick the line is drawn, in item coordinates."""

        self.prepareGeometryChange()
        self.line_width = min(self.max_line_width(),
                              max(self.MIN_WIDTH, width))
        self.update()

    @classmethod
    def create_from_data(cls, **kwargs):
        return cls(**kwargs.get('data', {}))

    def set_points(self, points):
        """Set the points the drawing runs through, in item coordinates."""

        self.prepareGeometryChange()
        self.points = [QtCore.QPointF(x, y) for x, y in points]
        self.path = self.build_path()

    def build_path(self):
        """The line itself, which depends on the kind of drawing."""

        path = QtGui.QPainterPath()
        if not self.points:
            return path
        if self.kind in self.SHAPES:
            return self.build_shape_path()

        path.moveTo(self.points[0])
        if self.kind == self.SKETCH:
            for point in self.points[1:]:
                path.lineTo(point)
        elif self.kind in (self.LINE, self.ARROW):
            path.lineTo(self.points[-1])
        else:
            # A curve bending towards the middle of the drawn path, so
            # it follows the direction the hand moved in
            start = self.points[0]
            end = self.points[-1]
            middle = self.points[len(self.points) // 2]
            control = middle * 2 - (start + end) / 2
            path.quadTo(control, end)
        return path

    def shape_rect(self):
        """The box a shape was dragged out in."""

        return QtCore.QRectF(self.points[0], self.points[-1]).normalized()

    def build_shape_path(self):
        """A closed shape drawn inside the box that was dragged.

        Inscribed in the box rather than held square, so a wide box
        gives a wide shape: forcing them regular would leave no way to
        draw an oval or an oblong at all.
        """

        path = QtGui.QPainterPath()
        rect = self.shape_rect()
        if self.kind == self.CIRCLE:
            path.addEllipse(rect)
            return path

        sides = self.SHAPE_SIDES[self.kind]
        if sides == 4:
            # A square drawn as a polygon would stand on a corner
            path.addRect(rect)
            return path

        center = rect.center()
        across, down = rect.width() / 2, rect.height() / 2
        for i in range(sides):
            # Starting at the top, so a triangle points upwards
            angle = math.radians(-90 + i * 360 / sides)
            point = QtCore.QPointF(center.x() + across * math.cos(angle),
                                   center.y() + down * math.sin(angle))
            if i == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()
        return path

    def arrow_head(self, path=None):
        """The arrow head at the end, as a triangle.

        Built against a given path when there is one, so that a
        stretched arrow gets a head that sits on the line as drawn
        while keeping its own proportions.
        """

        if self.kind not in (self.ARROW, self.SPLINE_ARROW):
            return None
        if len(self.points) < 2:
            return None

        path = self.path if path is None else path
        if path.isEmpty():
            return None
        end = path.pointAtPercent(1)
        # Point the head along the last bit of the line
        percent = path.percentAtLength(max(path.length() - 1, 0))
        angle = math.radians(path.angleAtPercent(percent))
        size = self.line_width * self.ARROW_SIZE
        direction = QtCore.QPointF(math.cos(angle), -math.sin(angle))
        across = QtCore.QPointF(-direction.y(), direction.x())
        base = end - direction * size
        return QtGui.QPolygonF([
            end,
            base + across * size / 2.5,
            base - across * size / 2.5])

    def bounding_rect_unselected(self):
        # A stroke reaches half its width beyond the path it follows,
        # round caps included. An arrow head is drawn separately from
        # that path, so where there is one its own outline is taken in
        # as well.
        #
        # Allowing every side a whole head-length instead -- the head
        # can point any way, so it looked like the safe thing -- grew
        # the box four times faster than the arrow: a line 400 long at
        # sixty thick came out in a box 880 by 480.
        margin = self.line_width / 2
        rect = self.path.boundingRect().adjusted(
            -margin, -margin, margin, margin)
        head = self.arrow_head()
        if head is not None:
            rect = rect.united(head.boundingRect().adjusted(
                -margin, -margin, margin, margin))
        return rect

    def boundingRect(self):
        if not self.has_selection_outline():
            return self.bounding_rect_unselected()
        margin = self.select_resize_size / 2 + self.select_rotate_size
        return self.bounding_rect_unselected().marginsAdded(
            QtCore.QMarginsF(margin, margin, margin, margin))

    def shape(self):
        if self.has_selection_handles():
            return super().shape()
        # Only the line itself is clickable, so items behind a long
        # diagonal stroke stay reachable
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(max(self.line_width * 3, 12))
        return stroker.createStroke(self.path)

    def paint(self, painter, option, widget):
        # A stretched drawing keeps an even line; see even_stroke
        stretch = self.even_stroke(painter)
        path = self.path
        if stretch is not None:
            path = QtGui.QTransform.fromScale(*stretch).map(path)

        pen = QtGui.QPen(self.color)
        pen.setWidthF(self.line_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QtGui.QBrush())
        painter.drawPath(path)

        head = self.arrow_head(path)
        if head is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QBrush(self.color))
            painter.drawPolygon(head)

        if stretch is not None:
            painter.restore()
        self.paint_selectable(painter, option, widget)

    # How close to an item an end has to be dropped to catch on it.
    SNAP_DISTANCE = 24

    # How close to an end the cursor has to be to take hold of it, in
    # screen pixels so it does not change with the zoom.
    END_GRIP = 10
    END_MODE = 10

    def end_at(self, pos):
        """Which end the cursor is on, if any: 'start', 'end' or None."""

        if len(self.points) < 2 or not self.has_selection_handles():
            return None
        if self.kind in self.SHAPES:
            # A shape is closed. Its two points are opposite corners of
            # the box it was drawn in, and dragging one about would
            # bend the shape rather than move an end of it.
            return None
        grip = self.fixed_length_for_viewport(self.END_GRIP)
        for which, index in (('start', 0), ('end', -1)):
            gap = pos - self.points[index]
            if gap.x() ** 2 + gap.y() ** 2 <= grip ** 2:
                return which
        return None

    def end_index(self, which):
        return 0 if which == 'start' else -1

    def show_end_marker(self, which):
        """Mark the end under the cursor, the way snapping does."""

        view = self.scene().views()[0] if self.scene() else None
        if view is None:
            return
        point = (None if which is None
                 else self.mapToScene(self.points[self.end_index(which)]))
        view.show_marker(point)

    def move_end_to(self, which, scene_pos):
        """Put one end of the line where the cursor is."""

        index = self.end_index(which)
        self.prepareGeometryChange()
        self.points[index] = self.mapFromScene(scene_pos)
        self.path = self.build_path()
        self.update()

    def attach_end(self, which, item, scene_pos=None):
        """Fasten one end of this drawing to a note or a group.

        ``which`` is 'start' or 'end'. Only what it holds is
        remembered: where on the edge it meets is worked out from
        where the line comes from, every time either of them moves.
        """

        self.ends[which] = {'item': item}
        logger.debug(f'Attached {which} of {self} to {item}')

    @staticmethod
    def edge_point_towards(rect, point):
        """Where a line from the middle of the box towards ``point``
        crosses the box's edge.

        This is what keeps a line from lying across the thing it is
        joined to: the end always meets the side the line comes from.
        """

        centre = rect.center()
        dx = point.x() - centre.x()
        dy = point.y() - centre.y()
        half_width = rect.width() / 2
        half_height = rect.height() / 2
        if (not dx and not dy) or not half_width or not half_height:
            return centre
        steps = []
        if dx:
            steps.append(half_width / abs(dx))
        if dy:
            steps.append(half_height / abs(dy))
        step = min(steps)
        return QtCore.QPointF(centre.x() + dx * step,
                              centre.y() + dy * step)

    def approach_from(self, which, rect):
        """Where this end should look towards to find its side.

        When the other end holds something too, that item's middle is
        what counts, not the line's own far point: the far point is
        itself being worked out, and using it means whichever end is
        recalculated first decides from where the other one used to be.
        """

        other = 'end' if which == 'start' else 'start'
        held = self.ends.get(other)
        if held is not None and held['item'].scene() is not None:
            return held['item'].attach_rect().center()
        return self.approach_point(which, rect)

    def approach_point(self, which, rect):
        """Where the line comes from, as seen by one of its ends.

        The nearest point along the line that is outside the box, so a
        curve doubling back inside it does not decide the direction.
        """

        order = (range(1, len(self.points)) if which == 'start'
                 else range(len(self.points) - 2, -1, -1))
        far = None
        for index in order:
            scene_point = self.mapToScene(self.points[index])
            far = scene_point
            if not rect.contains(scene_point):
                return scene_point
        return far

    def detach_end(self, which):
        self.ends.pop(which, None)

    def attached_items(self):
        return [end['item'] for end in self.ends.values()]

    def follow_attachments(self):
        """Move the fastened ends to where the items they hold have gone."""

        if not self.ends or len(self.points) < 2:
            return
        moved = False
        for which, index in (('start', 0), ('end', -1)):
            end = self.ends.get(which)
            if end is None:
                continue
            target = end['item']
            if target.scene() is None:
                # Whatever it held has gone; the line stays where it is
                self.detach_end(which)
                continue
            rect = target.attach_rect()
            approach = self.approach_from(which, rect)
            if approach is None:
                continue
            wanted = self.mapFromScene(
                self.edge_point_towards(rect, approach))
            if wanted != self.points[index]:
                self.points[index] = wanted
                moved = True
        if moved:
            self.prepareGeometryChange()
            self.path = self.build_path()
            self.update()

    def hoverMoveEvent(self, event):
        which = self.end_at(event.pos())
        self.show_end_marker(which)
        if which is not None:
            self.set_cursor(Qt.CursorShape.SizeAllCursor)
            return
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.show_end_marker(None)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        which = (self.end_at(event.pos())
                 if event.button() == Qt.MouseButton.LeftButton else None)
        if which is not None:
            self.active_mode = self.END_MODE
            self.dragged_end = which
            self.end_orig_points = [QtCore.QPointF(p) for p in self.points]
            self.end_orig_ends = dict(self.ends)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.active_mode == self.END_MODE:
            self.move_end_to(self.dragged_end, event.scenePos())
            view = self.scene().views()[0] if self.scene() else None
            if view is not None:
                view.show_snap_preview(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.active_mode == self.END_MODE:
            self.active_mode = None
            view = self.scene().views()[0] if self.scene() else None
            self.detach_end(self.dragged_end)
            if view is not None:
                view.snap_end(self, self.dragged_end, event.scenePos())
                view.show_marker(None)
            points = [[p.x(), p.y()] for p in self.points]
            if points != [[p.x(), p.y()] for p in self.end_orig_points]:
                self.scene().undo_stack.push(commands.ChangeDrawPoints(
                    self, points, self.end_orig_points, self.ends,
                    self.end_orig_ends))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def get_extra_save_data(self):
        data = {'kind': self.kind,
                'color': self.color.getRgb(),
                'width': self.line_width,
                'points': [[p.x(), p.y()] for p in self.points]}
        # Fastened ends, named by the save id of what they hold. An
        # older version ignores this and the line simply stays put.
        ends = {}
        for which, end in self.ends.items():
            if end['item'].save_id is not None:
                ends[which] = {'item': end['item'].save_id}
        if ends:
            data['ends'] = ends
        return data

    def create_copy(self):
        item = BeeDrawItem(
            points=[[p.x(), p.y()] for p in self.points],
            kind=self.kind,
            color=self.color.getRgb(),
            width=self.line_width)
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        item.set_stretch(*self.stretch)
        if self.flip() == -1:
            item.do_flip()
        return item

    def add_to_mimedata(self, mimedata):
        # Nothing sensible to hand to other applications
        pass


class TitleBandMixin:
    """A band across the top of an item, holding a title.

    Groups and notes both have one, and it behaves the same on either:
    empty means no band at all, the band can take a colour of its own,
    and the words are typed straight onto the item. What differs is how
    big the letters are and where the band sits, which is left to the
    item to say.
    """

    # Room above and below the letters, as a fraction of their size
    TITLE_PADDING_FRACTION = 0.35
    TITLE_MIN_SIZE = 7
    # Qt's font engine overflows somewhere above ten thousand point:
    # the metrics come back negative, the band works out to nothing and
    # the title is nowhere to be seen. A title is sized from the item,
    # and one on a real board reaches hundreds of thousands of units
    # across, which asked for twenty-five thousand point.
    TITLE_MAX_SIZE = 8000

    # Where the title sits in its band
    TITLE_CENTER = 'center'
    TITLE_LEFT = 'left'
    TITLE_ALIGNMENTS = (TITLE_CENTER, TITLE_LEFT)

    def init_title(self, title=None, header_color=None, title_align=None):
        """Start with no band, or with the one a file remembered."""

        self._title = title or ''
        # None means the band takes the item's own colour, so it keeps
        # following it when the item is recoloured
        self.header_color = (QtGui.QColor(*header_color)
                             if header_color else None)
        # Centred is what titles did before there was a choice, so a
        # board written then opens looking the way it did
        self.title_align = (title_align if title_align in
                            self.TITLE_ALIGNMENTS else self.TITLE_CENTER)
        # The line being typed into, while a title is being written
        self.title_editor = None
        self.title_editing = False

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value or ''
        self.on_title_changed()

    def on_title_changed(self):
        """Take account of a band that has just come or gone."""

        self.update()

    def title_save_data(self):
        """The three things a band is made of, for the file."""

        return {'title': self.title,
                'title_align': self.title_align,
                'header_color': (self.header_color.getRgb()
                                 if self.header_color else None)}

    def stored_title_size(self):
        """A size the item holds on to for its title, if it holds one.

        A group's title is measured from its box every time, so there
        is nothing to keep. A note's is not.
        """

        return None

    def shows_header(self):
        """Whether there is a band to draw.

        A title being written counts, even before the first letter: the
        band has to be there to type into.
        """

        return bool(self._title) or self.title_editing

    def title_size(self):
        """How big the title's letters are. Up to the item."""

        raise NotImplementedError

    def title_font_of_size(self, size):
        """Bold, and in the bundled face -- a title is not a note.

        Falls back to the interface font on the rare install where the
        bundled one could not be loaded, which is better than no title.
        """

        family = BeeAssets().font_family
        font = QtGui.QFont(family) if family else QtWidgets.QApplication.font()
        font.setBold(True)
        font.setPointSizeF(size)
        return font

    def title_font(self):
        return self.title_font_of_size(self.title_size())

    def line_height_for(self, size):
        """The height of one line of letters this size."""

        line = QtGui.QFontMetricsF(self.title_font_of_size(size)).height()
        if line > 0:
            return line
        # Whatever the font engine made of it, a band still has to have
        # a height, or the title is simply not there
        return size * 1.8

    def band_height_for(self, size):
        """The band that letters of this size need, editor included."""

        line = self.line_height_for(size)
        room = line * self.TITLE_PADDING_FRACTION
        if self.title_editor is not None:
            # Ask the editor rather than measuring a line a second way:
            # the band has to hold exactly what it lays out
            line = max(self.title_editor.boundingRect().height(), line)
        return line + 2 * room

    def header_height(self):
        if not self.shows_header():
            return 0
        return self.band_height_for(self.title_size())

    def title_inset(self):
        """The gap kept between the words and the ends of the band."""

        return self.header_height() * self.TITLE_PADDING_FRACTION

    def header_rect(self):
        """The band itself, in item coordinates. Up to the item."""

        raise NotImplementedError

    def title_alignment(self):
        """Where the title sits in its band, as Qt wants it."""

        if self.title_align == self.TITLE_LEFT:
            return (Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter)
        return Qt.AlignmentFlag.AlignCenter

    def title_text_alignment(self):
        """The same, for a document, which only knows across."""

        if self.title_align == self.TITLE_LEFT:
            return Qt.AlignmentFlag.AlignLeft
        return Qt.AlignmentFlag.AlignHCenter

    def default_header_color(self):
        """The colour a band with none of its own takes."""

        raise NotImplementedError

    def visible_header_color(self):
        """The colour the band actually appears in.

        A translucent band lets the canvas through, and that is what
        the title has to stay readable against.
        """

        canvas = QtGui.QColor(
            self.settings.valueOrDefault('View/canvas_color'))
        return blend_over(self.header_color or self.default_header_color(),
                          canvas)

    def paint_title_text(self, painter):
        """Draw the words in the band, or nothing while they are typed."""

        if self.title_editing:
            # The words are the editor's while it is open, and drawing
            # them here as well would double them up
            return
        band = self.header_rect()
        inset = self.title_inset()
        room = band.adjusted(inset, 0, -inset, 0)
        font = self.title_font()
        painter.setFont(font)
        painter.setPen(QtGui.QPen(readable_grey(self.visible_header_color())))
        metrics = QtGui.QFontMetricsF(font)
        painter.drawText(
            room, int(self.title_alignment()),
            metrics.elidedText(self._title, Qt.TextElideMode.ElideRight,
                               room.width()))

    def title_search_rect(self):
        """Where the title sits on the board, for Find to go to.

        The band rather than the word in it: the words are drawn
        straight onto the item rather than laid out in a document, so
        there is no letter to measure against, and a band is small
        enough to be worth going to whole.
        """

        return self.mapToScene(self.header_rect()).boundingRect()

    def enter_title_edit_mode(self):
        """Open the title for writing, on the item itself."""

        if self.title_editor is not None:
            self.title_editor.setFocus()
            return
        logger.debug(f'Writing the title of {self}')
        self.title_editing = True
        self.on_title_changed()
        self.title_editor = TitleEditor(self)
        self.title_editor.setFocus()
        scene = self.scene()
        if scene is not None:
            scene.title_item = self
            for view in scene.views():
                view.reveal(self.mapRectToScene(self.header_rect()))
        self.update()

    def exit_title_edit_mode(self, commit=True):
        """Take the words out of the editor and put the editor away."""

        editor = self.title_editor
        if editor is None:
            return
        logger.debug(f'Finished the title of {self}')
        text = editor.toPlainText().strip()
        self.title_editor = None
        scene = self.scene()
        if scene is not None:
            if scene.title_item is self:
                scene.title_item = None
            scene.removeItem(editor)
        self.title_editing = False

        if commit and text != self._title and scene is not None:
            scene.undo_stack.push(commands.ChangeTitle(
                [self], text, self.header_color, self.title_align,
                self.stored_title_size()))
        else:
            # Nothing to record, but the band still has to go if the
            # title was left empty
            self.on_title_changed()
            self.update()

    def refresh_title_editor(self):
        """Follow a change of colour or alignment while writing."""

        if self.title_editor is not None:
            self.title_editor.refresh()


@register_item
class BeeGroupItem(TitleBandMixin, BeeItemMixin,
                   QtWidgets.QGraphicsRectItem):
    """A coloured box holding a group of items.

    The items are real children of this item, so moving, scaling or
    rotating the group moves its contents with it. The box itself is
    drawn behind the children and grows to fit them.
    """

    TYPE = 'group'

    DEFAULT_BOX_COLOR = (52, 52, 52, 255)
    # Smallest space between the box edge and the items inside it
    PADDING = 20
    # ...and the same space as a fraction of the contents' shorter side,
    # so the margin stays visible around large contents instead of
    # thinning to a hairline that looks like the box is touching them
    PADDING_FRACTION = 0.05
    # Width of the border shown when the group is a drop target
    DROP_BORDER_SIZE = 4
    # The box's rounded corners, as a fraction of its shorter side. A
    # fixed radius does not read as the same shape at different sizes: on
    # a large box it looks almost square, on a small one like a lozenge.
    # A fraction makes every group look like the same box, scaled.
    CORNER_RADIUS_FRACTION = 0.04

    # The title band across the top. Sized from the box's width, which
    # the band does not change -- taking it from the shorter side would
    # be circular, since the band is added to the height.
    TITLE_FRACTION = 0.04

    def __init__(self, box_color=None, locked=False,
                 created=None, modified=None, title=None,
                 header_color=None, title_align=None, **kwargs):
        super().__init__()
        self.save_id = None
        self.is_image = False
        self.settings = BeeSettings()
        self.init_selectable()
        self.is_editable = False
        self.box_color = QtGui.QColor(*(box_color or self.DEFAULT_BOX_COLOR))
        # An empty title means no band at all; the group looks exactly
        # as it did before there were titles
        self.init_title(title, header_color, title_align)
        # A locked group can't be opened up to edit the items inside it
        self.locked = locked
        self._drop_target = False
        # Groups loaded from a file keep their dates; new ones start now
        now = datetime.datetime.now().isoformat(timespec='seconds')
        self.created = created or now
        self.modified = modified or self.created
        logger.debug(f'Initialized {self}')

    def touch(self):
        """Record that the group has just been changed."""

        self.modified = datetime.datetime.now().isoformat(timespec='seconds')

    @staticmethod
    def format_date(value):
        """A stored date as something readable, for the layers panel."""

        if not value:
            return 'unknown'
        try:
            return datetime.datetime.fromisoformat(value).strftime(
                '%d %b %Y, %H:%M')
        except ValueError:
            return value

    def get_details(self):
        """The group's dates, shown in the layers panel."""

        return (f'Created: {self.format_date(self.created)}\n'
                f'Last edited: {self.format_date(self.modified)}')

    @property
    def drop_target(self):
        """Whether items dragged right now would land in this group."""

        return self._drop_target

    @drop_target.setter
    def drop_target(self, value):
        if value != self._drop_target:
            self._drop_target = value
            self.update()

    @classmethod
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data', {})
        return cls(**data)

    def __str__(self):
        return f'Group ({len(self.childItems())} items)'

    def get_default_name(self):
        return f'Group ({len(self.bee_children())})'

    @property
    def box_color(self):
        return self._box_color

    @box_color.setter
    def box_color(self, value):
        logger.debug(f'Setting box colour for {self} to {value.name()}')
        self._box_color = value
        self.update()

    def on_title_changed(self):
        # The band is added above the items, never over them, so the
        # box has to be re-measured when a title comes or goes
        self.fit_to_children()
        self.update()

    def get_extra_save_data(self):
        data = {'box_color': self.box_color.getRgb(),
                'locked': self.locked,
                'created': self.created,
                'modified': self.modified}
        data.update(self.title_save_data())
        return data

    def bee_children(self):
        """The items grouped inside this one."""

        return [item for item in self.childItems()
                if hasattr(item, 'save_id')]

    def padding_for(self, rect):
        """The margin to leave around contents of the given size.

        Proportional to the shorter side, with ``PADDING`` as a floor, so
        a group of small items keeps a sensible margin and a group of
        large ones gets a margin in proportion rather than a hairline.
        """

        shorter = min(rect.width(), rect.height())
        return max(self.PADDING, shorter * self.PADDING_FRACTION)

    def get_edge_bounds(self):
        """Groups scale from the corners only, never from an edge.

        Dragging an edge stretches an item out of proportion, which on
        a group squashes everything inside it. A group is a container
        rather than a picture: there is nothing of its own to distort,
        only other people's work.
        """

        return []

    def fit_to_children(self):
        """Grow the box so that it contains all its items, with padding.

        A title takes its band from above the padding rather than out
        of it, so the words never come down over somebody's work.
        """

        children = self.bee_children()
        if not children:
            return
        # The grouped items only. ``childrenBoundingRect`` would take in
        # the line being typed into as well, and the box would then
        # chase the words being written into it.
        rect = QtCore.QRectF()
        for child in children:
            rect = rect.united(child.mapRectToParent(child.boundingRect()))
        padding = self.padding_for(rect)
        box = rect.adjusted(-padding, -padding, padding, padding)
        self.prepareGeometryChange()
        header = self.header_height_for(box.width())
        self.setRect(box.adjusted(0, -header, 0, 0))

    def title_size_for(self, width):
        """How big the title's letters are, for a box this wide.

        Measured from the width because the band is added to the height:
        taking it from the shorter side would have the size depend on
        the band and the band depend on the size.
        """

        return min(self.TITLE_MAX_SIZE,
                   max(self.TITLE_MIN_SIZE, width * self.TITLE_FRACTION))

    def title_size(self):
        return self.title_size_for(self.rect().width())

    def search_text(self):
        """What Find looks through: the title across the top."""

        return self.title

    def search_rect(self, query):
        """Where a match sits on the board, for Find to go to.

        The band rather than the word in it: the words are drawn
        straight onto the box rather than laid out in a document, so
        there is no letter to measure against, and a band is small
        enough to be worth going to whole.
        """

        return self.title_search_rect()

    def header_height_for(self, width):
        """The height of the title band, or nothing without a title.

        Takes the width because the box is measured before it is set:
        ``fit_to_children`` has to know how tall the band will be on a
        box it has not given itself yet.
        """

        if not self.shows_header():
            return 0
        return self.band_height_for(self.title_size_for(width))

    def header_rect(self):
        """The band across the top of the box."""

        rect = self.rect()
        return QtCore.QRectF(rect.x(), rect.y(),
                             rect.width(), self.header_height())

    def default_header_color(self):
        """A band with no colour of its own is the group's colour."""

        return self.box_color

    def paint_header(self, painter):
        """Draw the title band and the title in it."""

        if not self.shows_header():
            return
        band = self.header_rect()
        radius = self.corner_radius()

        # Clipped to the box so the band takes the box's rounded top
        # corners without having to be built out of arcs
        path = QtGui.QPainterPath()
        path.addRoundedRect(self.rect(), radius, radius)
        painter.save()
        painter.setClipPath(path)
        color = self.header_color or self.box_color
        painter.fillRect(band, QtGui.QBrush(color))
        self.paint_title_text(painter)
        painter.restore()

    def set_children_interactive(self, value):
        """Whether the items inside the group can be clicked individually.

        When switched off, mouse events fall through to the group
        itself, so that clicking any item selects and moves the whole
        group.
        """

        for item in self.bee_children():
            item.setFlag(
                QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
                value)
            item.setFlag(
                QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                value)
            if not value:
                item.setSelected(False)

    def contains_scene_pos(self, pos):
        """Whether the given scene position falls inside the box."""

        return self.rect().contains(self.mapFromScene(pos))

    def corner_radius(self):
        """The corner radius to draw the box with at its current size.

        Proportional to the shorter side, so the corners keep their
        weight relative to the box however big it grows, with
        ``CORNER_RADIUS`` as a floor for very small groups.
        """

        rect = self.rect()
        shorter = min(rect.width(), rect.height())
        return max(CORNER_RADIUS, shorter * self.CORNER_RADIUS_FRACTION)

    def selection_corner_radius(self):
        """Match the box the group draws."""

        return self.corner_radius()

    def paint(self, painter, option, widget):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(self.box_color))
        radius = self.corner_radius()
        painter.drawRoundedRect(self.rect(), radius, radius)
        self.paint_header(painter)
        if self.drop_target:
            self.paint_drop_target(painter)
        self.paint_selectable(painter, option, widget)

    def paint_drop_target(self, painter):
        """Show that dropping here will add the item to this group."""

        color = QtGui.QColor(*COLORS['Scene:Selection'])
        fill = QtGui.QColor(color)
        fill.setAlpha(40)
        painter.setBrush(QtGui.QBrush(fill))
        pen = QtGui.QPen(color)
        pen.setWidth(
            int(self.fixed_length_for_viewport(self.DROP_BORDER_SIZE)))
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        # Inset by half the pen width so the border stays inside the box.
        # The radius shrinks by the same amount, so the border stays
        # concentric with the corner it sits inside.
        inset = pen.width() / 2
        radius = max(0, self.corner_radius() - inset)
        painter.drawRoundedRect(
            self.rect().adjusted(inset, inset, -inset, -inset),
            radius, radius)

    def create_copy(self):
        item = BeeGroupItem(
            box_color=self.box_color.getRgb(),
            locked=self.locked,
            title=self.title,
            title_align=self.title_align,
            header_color=(self.header_color.getRgb()
                          if self.header_color else None))
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        if self.flip() == -1:
            item.do_flip()
        for child in self.bee_children():
            copy = child.create_copy()
            copy.setParentItem(item)
        item.fit_to_children()
        # The copy has to behave like a group, not like loose items
        item.set_children_interactive(False)
        return item

    def add_to_mimedata(self, mimedata):
        # Nothing sensible to hand to other applications
        pass


class ImageCaptionEditor(QtWidgets.QGraphicsTextItem):
    """The line an image's caption is typed into, on the picture itself.

    The same idea as the one a group's title is written in; kept apart
    because the band it sits in is measured differently.
    """

    def __init__(self, item):
        super().__init__(item.caption, item)
        self.item = item
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction)
        # No margin of its own: the band is measured to the width the
        # words are given, and Qt's four units on each side would have
        # them wrapping narrower than that and standing taller than the
        # band that was made for them
        self.document().setDocumentMargin(0)
        self.settling = False
        self.refresh()
        cursor = self.textCursor()
        cursor.select(QtGui.QTextCursor.SelectionType.Document)
        self.setTextCursor(cursor)
        # The band grows under the words as they are typed
        self.document().contentsChanged.connect(self.on_text_changed)

    def on_text_changed(self):
        if self.settling:
            return
        self.settling = True
        self.item.prepareGeometryChange()
        self.refresh()
        self.item.update()
        self.settling = False

    def refresh(self):
        item = self.item
        band = item.caption_rect()
        inset = item.caption_inset()
        self.setFont(item.caption_font())
        self.setDefaultTextColor(
            readable_grey(item.visible_caption_color()))
        self.setTextWidth(max(1.0, band.width() - 2 * inset))
        option = self.document().defaultTextOption()
        option.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        # Between words, like the drawn caption. Qt's own default for a
        # document breaks inside a word when it has to, which had a
        # long one looking right while it was typed and losing its
        # beginning the moment the writing finished.
        option.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
        self.document().setDefaultTextOption(option)
        # From the top of the band, not centred on it: the band is
        # built to fit these words, so there is nothing to centre in
        self.setPos(band.x() + inset, band.y() + inset)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.item.exit_caption_edit_mode()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.item.exit_caption_edit_mode(commit=False)
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.item.exit_caption_edit_mode()


class TitleEditor(QtWidgets.QGraphicsTextItem):
    """The line a title is typed into, on the item it belongs to.

    Not saved and not selectable: it exists only while a title is being
    written, and what it is for is handing its words to the item.
    """

    def __init__(self, item):
        super().__init__(item.title, item)
        self.item = item
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction)
        # No margin of its own: the band is measured to the width the
        # words are given, and Qt's four units on each side would have
        # them wrapping narrower and standing taller than the band
        self.document().setDocumentMargin(0)
        self.refresh()
        cursor = self.textCursor()
        cursor.select(QtGui.QTextCursor.SelectionType.Document)
        self.setTextCursor(cursor)

    def refresh(self):
        """Sit in the band, in the band's own font and colour."""

        item = self.item
        band = item.header_rect()
        inset = item.title_inset()
        self.setFont(item.title_font())
        self.setDefaultTextColor(
            readable_grey(item.visible_header_color()))
        self.setTextWidth(max(1.0, band.width() - 2 * inset))
        option = self.document().defaultTextOption()
        option.setAlignment(item.title_text_alignment())
        self.document().setDefaultTextOption(option)
        # From the top of the band, not centred in it: the band is
        # built to fit these words, so there is nothing to centre
        self.setPos(band.x() + inset, band.y() + inset)

    def keyPressEvent(self, event):
        # A title is one line: Enter finishes it rather than starting a
        # second one. Escape throws the change away.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.item.exit_title_edit_mode()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.item.exit_title_edit_mode(commit=False)
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        # Clicking away finishes the title, the way clicking away from
        # a note finishes the note
        self.item.exit_title_edit_mode()


@register_item
class BeePixmapItem(BeeItemMixin, QtWidgets.QGraphicsPixmapItem):
    """Class for images added by the user."""

    TYPE = 'pixmap'
    CROP_HANDLE_SIZE = 15

    # The contour drawn round the image. Its width is in item
    # coordinates, like a drawing's line width, so it grows and shrinks
    # with the image instead of staying a fixed number of screen pixels.
    # The default and the limit are fractions of the shorter side, so a
    # contour looks the same on a thumbnail and on a photograph.
    DEFAULT_OUTLINE_COLOR = (235, 235, 235, 255)
    OUTLINE_DEFAULT_FRACTION = 0.02
    OUTLINE_MAX_FRACTION = 0.25
    OUTLINE_MIN_WIDTH = 0.5

    # The caption along the bottom edge. Sized from the picture's width,
    # which the band does not change, and measured against the cropped
    # picture rather than the whole file, so a crop takes its caption
    # with it.
    CAPTION_FRACTION = 0.04
    CAPTION_MIN_SIZE = 7
    # As for a group's title: past this the font engine overflows and
    # the band works out to nothing
    CAPTION_MAX_SIZE = 8000
    CAPTION_PADDING_FRACTION = 0.35
    DEFAULT_CAPTION_COLOR = (52, 52, 52, 255)
    # Between words only. A word longer than the band runs off the end
    # of it rather than being taken apart, which is what a caption of
    # ordinary words wants and what one long run of letters gets for
    # asking.
    CAPTION_WRAP = Qt.TextFlag.TextWordWrap

    def __init__(self, image, filename=None, **kwargs):
        super().__init__(QtGui.QPixmap.fromImage(image))
        self.save_id = None
        self.filename = filename
        # Before the crop: setting the crop measures the contour against
        # what is left of the picture, and so needs these to exist
        self.outline_width = 0
        self.outline_color = QtGui.QColor(*self.DEFAULT_OUTLINE_COLOR)
        # An empty caption means no band at all
        self._caption = ''
        self.caption_color = QtGui.QColor(*self.DEFAULT_CAPTION_COLOR)
        self.caption_editing = False
        self.caption_editor = None
        self.reset_crop()
        logger.debug(f'Initialized {self}')
        self.is_image = True
        self.crop_mode = False
        self.init_selectable()
        self.settings = BeeSettings()
        self.grayscale = False

    @classmethod
    def create_from_data(self, **kwargs):
        item = kwargs.pop('item')
        data = kwargs.pop('data', {})
        item.filename = item.filename or data.get('filename')
        if 'crop' in data:
            item.crop = QtCore.QRectF(*data['crop'])
        item.setOpacity(data.get('opacity', 1))
        item.grayscale = data.get('grayscale', False)
        item.outline_width = data.get('outline_width', 0)
        color = data.get('outline_color')
        if color:
            item.outline_color = QtGui.QColor(*color)
        item.caption = data.get('caption', '')
        color = data.get('caption_color')
        if color:
            item.caption_color = QtGui.QColor(*color)
        return item

    def __str__(self):
        size = self.pixmap().size()
        return (f'Image "{self.filename}" {size.width()} x {size.height()}')

    def get_default_name(self):
        if self.filename:
            return os.path.basename(self.filename)
        return 'Image'

    @property
    def crop(self):
        return self._crop

    @crop.setter
    def crop(self, value):
        logger.debug(f'Setting crop for {self} to {value}')
        self.prepareGeometryChange()
        self._crop = value
        # A contour frames the picture, so it is measured against the
        # picture. Cropping a photograph down to a stamp used to leave
        # the frame at its old thickness, which then swallowed what was
        # left of the image.
        if self.outline_width:
            self.outline_width = min(self.outline_width,
                                     self.max_outline_width())
        self.update()

    @property
    def grayscale(self):
        return self._grayscale

    @grayscale.setter
    def grayscale(self, value):
        logger.debug('Setting grayscale for {self} to {value}')
        self._grayscale = value
        if value is True:
            # Using the grayscale image format to convert to grayscale
            # loses an image's tranparency. So the straightworward
            # following method gives us an ugly black replacement:
            # img = img.convertToFormat(QtGui.QImage.Format.Format_Grayscale8)

            # Instead, we will fill the background with the current
            # canvas colour, so the issue is only visible if the image
            # overlaps other images. The way we do it here only works
            # as long as the canvas colour is itself grayscale,
            # though.
            img = QtGui.QImage(
                self.pixmap().size(), QtGui.QImage.Format.Format_Grayscale8)
            img.fill(QtGui.QColor(*COLORS['Scene:Canvas']))
            painter = QtGui.QPainter(img)
            painter.drawPixmap(0, 0, self.pixmap())
            painter.end()
            self._grayscale_pixmap = QtGui.QPixmap.fromImage(img)

            # Alternative methods that have their own issues:
            #
            # 1. Use setAlphaChannel of the resulting grayscale
            # image. How do we get the original alpha channel? Using
            # the whole original image also takes color values into
            # account, not just their alpha values.
            #
            # 2. QtWidgets.QGraphicsColorizeEffect() with black colour
            # on the GraphicsItem. This applys to everything the paint
            # method does, so the selection outline/handles will also
            # be gray. setGraphicsEffect is only available on some
            # widgets, so we can't apply it selectively.
            #
            # 3. Going through every pixel and doing it manually — bad
            # performance.
        else:
            self._grayscale_pixmap = None

        self.update()

    def sample_color_at(self, pos):
        ipos = self.mapFromScene(pos)
        if self.grayscale:
            pm = self._grayscale_pixmap
        else:
            pm = self.pixmap()
        img = pm.toImage()

        color = img.pixelColor(int(ipos.x()), int(ipos.y()))
        if color.alpha():
            return color

    def bounding_rect_unselected(self):
        if self.crop_mode:
            return QtWidgets.QGraphicsPixmapItem.boundingRect(self)
        else:
            return self.crop

    def boundingRect(self):
        """Room for the contour on top of whatever else needs room.

        Only the painting bounds grow. The image's own rectangle stays
        what it was, so the selection box, the handles and the point a
        line fastens to all stay on the edge of the picture rather than
        stepping outward when a contour is put on.
        """

        # The caption hangs below the picture rather than over it, so
        # there has to be room under it to paint in -- and the contour
        # goes round both, so its own margin is added after that
        rect = super().boundingRect().adjusted(
            0, 0, 0, self.caption_height())
        if self.outline_width:
            margin = self.outline_width / 2
            rect = rect.marginsAdded(
                QtCore.QMarginsF(margin, margin, margin, margin))
        return rect

    @property
    def caption(self):
        return self._caption

    @caption.setter
    def caption(self, value):
        self.prepareGeometryChange()
        self._caption = value or ''
        self.update()

    def search_text(self):
        """What Find looks through: the caption along the bottom."""

        return self.caption

    def search_rect(self, query):
        return self.mapToScene(self.caption_rect()).boundingRect()

    def shows_caption(self):
        """Whether there is a band to draw.

        A caption being written counts, even before the first letter:
        the band has to be there to type into.
        """

        return bool(self._caption) or self.caption_editing

    def caption_size(self):
        """How big the caption's letters are, for this picture.

        Measured against the crop, so a picture cut down to a corner
        gets a caption in proportion to what is left of it rather than
        to the file it came from.
        """

        return min(self.CAPTION_MAX_SIZE,
                   max(self.CAPTION_MIN_SIZE,
                       self.crop.width() * self.CAPTION_FRACTION))

    def caption_font(self):
        """The interface font, plain.

        A caption is a note about a picture rather than a heading over
        one, so it does not take the weight or the face a group title
        does.
        """

        font = QtGui.QFont(QtWidgets.QApplication.font())
        font.setPointSizeF(self.caption_size())
        return font

    def caption_draft(self):
        """What the caption says right now, the editor included.

        So the band grows under the words as they are typed rather than
        only once the writing is finished.
        """

        if self.caption_editor is not None:
            return self.caption_editor.toPlainText()
        return self._caption

    def caption_line_height(self):
        line = QtGui.QFontMetricsF(self.caption_font()).height()
        # A band still has to have a height, whatever the font engine
        # made of a very large one
        return line if line > 0 else self.caption_size() * 1.8

    def caption_text_width(self):
        """The room the words have across the picture."""

        return max(1.0, self.crop.width() - 2 * self.caption_inset())

    def caption_text_height(self):
        """How tall the words are once wrapped to that width.

        A caption too long for the picture wraps and the band grows
        down to hold it. Cutting it off with an ellipsis hid the very
        thing the caption was written to say.
        """

        line = self.caption_line_height()
        if self.caption_editor is not None:
            # Ask the editor rather than measuring the same words a
            # second way: the band has to hold exactly what it lays out
            return max(self.caption_editor.boundingRect().height(), line)
        text = self.caption_draft()
        if not text:
            return line
        metrics = QtGui.QFontMetricsF(self.caption_font())
        rect = metrics.boundingRect(
            QtCore.QRectF(0, 0, self.caption_text_width(), 0),
            int(Qt.AlignmentFlag.AlignHCenter | self.CAPTION_WRAP),
            text)
        return max(rect.height(), line)

    def caption_height(self):
        if not self.shows_caption():
            return 0
        return self.caption_text_height() + 2 * self.caption_inset()

    def caption_rect(self):
        """The band along the bottom edge, hanging below the picture."""

        rect = self.crop
        return QtCore.QRectF(rect.x(), rect.bottom(),
                             rect.width(), self.caption_height())

    def caption_inset(self):
        """The gap kept round the words.

        Measured from one line rather than from the band, which now
        depends on how many lines there turn out to be.
        """

        return self.caption_line_height() * self.CAPTION_PADDING_FRACTION

    def caption_radius(self):
        """How round the band's bottom corners are.

        Proportional to the band, so it keeps its weight whatever size
        the picture is, with the usual floor for very small ones.
        """

        band = self.caption_rect()
        # From one line, not from the band: a caption that wrapped onto
        # four lines would otherwise be given corners to match
        return min(max(CORNER_RADIUS, self.caption_line_height() * 0.5),
                   band.height(), band.width() / 2)

    def framed_rect(self):
        """The picture and its caption together."""

        rect = QtCore.QRectF(self.crop)
        rect.setHeight(rect.height() + self.caption_height())
        return rect

    def rounded_bottom_path(self, rect):
        """A rectangle with its two bottom corners taken off.

        The top meets the picture square, the way the band under a
        group's title does at the other end.
        """

        radius = self.caption_radius() if self.shows_caption() else 0
        return half_rounded_path(rect, radius, top=False)

    def visible_caption_color(self):
        """The colour the band actually appears in."""

        canvas = QtGui.QColor(
            self.settings.valueOrDefault('View/canvas_color'))
        return blend_over(self.caption_color, canvas)

    def shape(self):
        """The picture, and the caption band hanging under it.

        So that the band can be clicked and double-clicked like part of
        the picture. Only the shape grows: the picture's own rectangle
        is what the handles, the sizing and a line joined to it all go
        by, and none of those should move because a caption was added.
        """

        path = super().shape()
        if self.shows_caption():
            path.addRect(self.caption_rect())
        return path

    def paint_caption(self, painter):
        """Draw the caption band and the words in it."""

        if not self.shows_caption():
            return
        band = self.caption_rect()
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(self.caption_color))
        painter.drawPath(self.rounded_bottom_path(band))
        if self.caption_editing:
            # The words are the editor's while it is open
            painter.restore()
            return

        painter.setFont(self.caption_font())
        painter.setPen(QtGui.QPen(
            readable_grey(self.visible_caption_color())))
        inset = self.caption_inset()
        room = band.adjusted(inset, inset, -inset, -inset)
        painter.drawText(
            room,
            int(Qt.AlignmentFlag.AlignCenter | self.CAPTION_WRAP),
            self.caption)
        painter.restore()

    def enter_caption_edit_mode(self):
        """Open the caption for writing, on the picture itself."""

        if self.caption_editor is not None:
            self.caption_editor.setFocus()
            return
        logger.debug(f'Writing the caption of {self}')
        self.caption_editing = True
        self.prepareGeometryChange()
        self.caption_editor = ImageCaptionEditor(self)
        self.caption_editor.setFocus()
        scene = self.scene()
        if scene is not None:
            scene.caption_item = self
            for view in scene.views():
                view.reveal(self.mapRectToScene(self.caption_rect()))
        self.update()

    def exit_caption_edit_mode(self, commit=True):
        """Take the words out of the editor and put the editor away."""

        editor = self.caption_editor
        if editor is None:
            return
        text = editor.toPlainText().strip()
        self.caption_editor = None
        scene = self.scene()
        if scene is not None:
            if scene.caption_item is self:
                scene.caption_item = None
            scene.removeItem(editor)
        self.caption_editing = False

        if commit and text != self.caption and scene is not None:
            scene.undo_stack.push(commands.ChangeCaption(
                [self], text, self.caption_color))
        else:
            self.prepareGeometryChange()
            self.update()

    def refresh_caption_editor(self):
        if self.caption_editor is not None:
            self.caption_editor.refresh()

    def default_outline_width(self):
        """How thick a contour starts out, for an image this size."""

        rect = self.crop
        return max(self.OUTLINE_MIN_WIDTH,
                   min(rect.width(), rect.height())
                   * self.OUTLINE_DEFAULT_FRACTION)

    def max_outline_width(self):
        """Past this the contour is eating the picture."""

        rect = self.crop
        return max(self.OUTLINE_MIN_WIDTH,
                   min(rect.width(), rect.height())
                   * self.OUTLINE_MAX_FRACTION)

    def set_outline_width(self, width):
        """Set how thick the contour is, in item coordinates."""

        self.prepareGeometryChange()
        if width <= 0:
            self.outline_width = 0
        else:
            self.outline_width = min(self.max_outline_width(),
                                     max(self.OUTLINE_MIN_WIDTH, width))
        self.update()

    def has_outline(self):
        return bool(self.outline_width)

    def get_extra_save_data(self):
        return {'filename': self.filename,
                'opacity': self.opacity(),
                'grayscale': self.grayscale,
                'outline_width': self.outline_width,
                'outline_color': self.outline_color.getRgb(),
                'caption': self.caption,
                'caption_color': self.caption_color.getRgb(),
                'crop': [self.crop.topLeft().x(),
                         self.crop.topLeft().y(),
                         self.crop.width(),
                         self.crop.height()]}

    def get_filename_for_export(self, imgformat, save_id_default=None):
        save_id = self.save_id or save_id_default
        assert save_id is not None

        if self.filename:
            basename = os.path.splitext(os.path.basename(self.filename))[0]
            return f'{save_id:04}-{basename}.{imgformat}'
        else:
            return f'{save_id:04}.{imgformat}'

    def get_imgformat(self, img):
        """Determines the format for storing this image."""

        formt = self.settings.valueOrDefault('Items/image_storage_format')

        if formt == 'best':
            # Images with alpha channel and small images are stored as png
            if (img.hasAlphaChannel()
                    or (img.height() < 500 and img.width() < 500)):
                formt = 'png'
            else:
                formt = 'jpg'

        logger.debug(f'Found format {formt} for {self}')
        return formt

    def fit_scale_to(self, size):
        """The scale that fits this image inside the given size.

        Used when an image arrives on the board, so that a small one
        does not turn up too small to work with and a large one does
        not take over the window.
        """

        if not self.width or not self.height or size.isEmpty():
            return 1
        return min(size.width() / self.width, size.height() / self.height)

    def pixmap_to_bytes(self, apply_grayscale=False, apply_crop=False):
        """Convert the pixmap data to PNG bytestring."""
        barray = QtCore.QByteArray()
        buffer = QtCore.QBuffer(barray)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        if apply_grayscale and self.grayscale:
            pm = self._grayscale_pixmap
        else:
            pm = self.pixmap()

        if apply_crop:
            pm = pm.copy(self.crop.toRect())

        img = pm.toImage()
        imgformat = self.get_imgformat(img)
        img.save(buffer, imgformat.upper(), quality=90)
        return (barray.data(), imgformat)

    def setPixmap(self, pixmap):
        super().setPixmap(pixmap)
        self.reset_crop()

    def pixmap_from_bytes(self, data):
        """Set image pimap from a bytestring."""
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(data)
        self.setPixmap(pixmap)

    def create_copy(self):
        item = BeePixmapItem(QtGui.QImage(), self.filename)
        item.setPixmap(self.pixmap())
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        item.setOpacity(self.opacity())
        item.grayscale = self.grayscale
        if self.flip() == -1:
            item.do_flip()
        item.crop = self.crop
        return item

    @cached_property
    def color_gamut(self):
        logger.debug(f'Calculating color gamut for {self}')
        gamut = defaultdict(int)
        img = self.pixmap().toImage()
        # Don't evaluate every pixel for larger images:
        step = max(1, int(max(img.width(), img.height()) / 1000))
        logger.debug(f'Considering every {step}. row/column')

        # Not actually faster than solution below :(
        # ptr = img.bits()
        # size = img.sizeInBytes()
        # pixelsize = int(img.sizeInBytes() / img.width() / img.height())
        # ptr.setsize(size)
        # for pixel in batched(ptr, n=pixelsize):
        #     r, g, b, alpha = tuple(map(ord, pixel))
        #     if 5 < alpha and 5 < r < 250 and 5 < g < 250 and 5 < b < 250:
        #         # Only consider pixels that aren't close to
        #         # transparent, white or black
        #         rgb = QtGui.QColor(r, g, b)
        #         gamut[rgb.hue(), rgb.saturation()] += 1

        for i in range(0, img.width(), step):
            for j in range(0, img.height(), step):
                rgb = img.pixelColor(i, j)
                rgbtuple = (rgb.red(), rgb.blue(), rgb.green())
                if (5 < rgb.alpha()
                        and min(rgbtuple) < 250 and max(rgbtuple) > 5):
                    # Only consider pixels that aren't close to
                    # transparent, white or black
                    gamut[rgb.hue(), rgb.saturation()] += 1

        logger.debug(f'Got {len(gamut)} color gamut values')
        return gamut

    def add_to_mimedata(self, mimedata):
        mimedata.setImageData(self.pixmap().toImage())

    def reset_crop(self):
        self.crop = QtCore.QRectF(
            0, 0, self.pixmap().size().width(), self.pixmap().size().height())

    @property
    def crop_handle_size(self):
        return self.fixed_length_for_viewport(self.CROP_HANDLE_SIZE)

    def crop_handle_topleft(self):
        topleft = self.crop_temp.topLeft()
        return QtCore.QRectF(
            topleft.x(),
            topleft.y(),
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_bottomleft(self):
        bottomleft = self.crop_temp.bottomLeft()
        return QtCore.QRectF(
            bottomleft.x(),
            bottomleft.y() - self.crop_handle_size,
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_bottomright(self):
        bottomright = self.crop_temp.bottomRight()
        return QtCore.QRectF(
            bottomright.x() - self.crop_handle_size,
            bottomright.y() - self.crop_handle_size,
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_topright(self):
        topright = self.crop_temp.topRight()
        return QtCore.QRectF(
            topright.x() - self.crop_handle_size,
            topright.y(),
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handles(self):
        return (self.crop_handle_topleft,
                self.crop_handle_bottomleft,
                self.crop_handle_bottomright,
                self.crop_handle_topright)

    def crop_edge_top(self):
        topleft = self.crop_temp.topLeft()
        return QtCore.QRectF(
            topleft.x() + self.crop_handle_size,
            topleft.y(),
            self.crop_temp.width() - 2 * self.crop_handle_size,
            self.crop_handle_size)

    def crop_edge_left(self):
        topleft = self.crop_temp.topLeft()
        return QtCore.QRectF(
            topleft.x(),
            topleft.y() + self.crop_handle_size,
            self.crop_handle_size,
            self.crop_temp.height() - 2 * self.crop_handle_size)

    def crop_edge_bottom(self):
        bottomleft = self.crop_temp.bottomLeft()
        return QtCore.QRectF(
            bottomleft.x() + self.crop_handle_size,
            bottomleft.y() - self.crop_handle_size,
            self.crop_temp.width() - 2 * self.crop_handle_size,
            self.crop_handle_size)

    def crop_edge_right(self):
        topright = self.crop_temp.topRight()
        return QtCore.QRectF(
            topright.x() - self.crop_handle_size,
            topright.y() + self.crop_handle_size,
            self.crop_handle_size,
            self.crop_temp.height() - 2 * self.crop_handle_size)

    def crop_edges(self):
        return (self.crop_edge_top,
                self.crop_edge_left,
                self.crop_edge_bottom,
                self.crop_edge_right)

    def get_crop_handle_cursor(self, handle):
        """Gets the crop cursor for the given handle."""

        is_topleft_or_bottomright = handle in (
            self.crop_handle_topleft, self.crop_handle_bottomright)
        return self.get_diag_cursor(is_topleft_or_bottomright)

    def get_crop_edge_cursor(self, edge):
        """Gets the crop edge cursor for the given edge."""

        top_or_bottom = edge in (
            self.crop_edge_top, self.crop_edge_bottom)
        sideways = (45 < self.rotation() < 135
                    or 225 < self.rotation() < 315)

        if top_or_bottom is sideways:
            return Qt.CursorShape.SizeHorCursor
        else:
            return Qt.CursorShape.SizeVerCursor

    def draw_crop_rect(self, painter, rect):
        """Paint a dotted rectangle for the cropping UI."""
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
        pen.setWidth(2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(rect)
        pen.setColor(QtGui.QColor(0, 0, 0))
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawRect(rect)

    def paint(self, painter, option, widget):
        if abs(painter.combinedTransform().m11()) < 2:
            # We want image smoothing, but only for images where we
            # are not zoomed in a lot. This is to ensure that for
            # example icons and pixel sprites can be viewed correctly.
            painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)

        if self.crop_mode:
            self.paint_debug(painter, option, widget)

            # Darken image outside of cropped area
            painter.drawPixmap(0, 0, self.pixmap())
            path = QtWidgets.QGraphicsPixmapItem.shape(self)
            path.addRect(self.crop_temp)
            color = QtGui.QColor(0, 0, 0)
            color.setAlpha(100)
            painter.setBrush(QtGui.QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)
            painter.setBrush(QtGui.QBrush())

            for handle in self.crop_handles():
                self.draw_crop_rect(painter, handle())
            self.draw_crop_rect(painter, self.crop_temp)
        else:
            pm = self._grayscale_pixmap if self.grayscale else self.pixmap()
            painter.drawPixmap(self.crop, pm, self.crop)
            # The caption first: a contour is centred on the edge it
            # follows, and the band drawn over it swallowed the inner
            # half, leaving the frame half as thick along the caption
            # as it was along the picture
            self.paint_caption(painter)
            self.paint_outline(painter)
            self.paint_selectable(painter, option, widget)

    def paint_outline(self, painter):
        """Draw the contour, sitting astride the edge of the picture.

        Not inset: a thick contour drawn inside would cover the outer
        band of the image, which is the part a frame is meant to set
        off rather than hide.
        """

        if not self.outline_width:
            return
        # A contour goes round the picture and its caption together:
        # a frame that stopped above the words would leave them hanging
        # outside it
        path = self.rounded_bottom_path(self.framed_rect())
        # A stretched picture keeps an even contour; see even_stroke
        stretch = self.even_stroke(painter)
        if stretch is not None:
            path = QtGui.QTransform.fromScale(*stretch).map(path)

        pen = QtGui.QPen(self.outline_color)
        pen.setWidthF(self.outline_width)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(QtGui.QBrush())
        painter.drawPath(path)
        if stretch is not None:
            painter.restore()

    def enter_crop_mode(self):
        logger.debug(f'Entering crop mode on {self}')
        self.prepareGeometryChange()
        self.crop_mode = True
        self.crop_temp = QtCore.QRectF(self.crop)
        self.crop_mode_move = None
        self.crop_mode_event_start = None
        self.grabKeyboard()
        self.update()
        self.scene().crop_item = self

    def exit_crop_mode(self, confirm):
        logger.debug(f'Exiting crop mode with {confirm} on {self}')
        if confirm and self.crop != self.crop_temp:
            self.scene().undo_stack.push(
                commands.CropItem(self, self.crop_temp))
        self.prepareGeometryChange()
        self.crop_mode = False
        self.crop_temp = None
        self.crop_mode_move = None
        self.crop_mode_event_start = None
        self.ungrabKeyboard()
        self.update()
        self.scene().crop_item = None

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.exit_crop_mode(confirm=True)
        elif event.key() == Qt.Key.Key_Escape:
            self.exit_crop_mode(confirm=False)
        else:
            super().keyPressEvent(event)

    def hoverMoveEvent(self, event):
        if not self.crop_mode:
            return super().hoverMoveEvent(event)

        for handle in self.crop_handles():
            if handle().contains(event.pos()):
                self.set_cursor(self.get_crop_handle_cursor(handle))
                return
        for edge in self.crop_edges():
            if edge().contains(event.pos()):
                self.set_cursor(self.get_crop_edge_cursor(edge))
                return
        self.unset_cursor()

    def mousePressEvent(self, event):
        if not self.crop_mode:
            return super().mousePressEvent(event)

        event.accept()
        for handle in self.crop_handles():
            # Click into a handle?
            if handle().contains(event.pos()):
                self.crop_mode_event_start = event.pos()
                self.crop_mode_move = handle
                return
        for edge in self.crop_edges():
            # Click into an edge handle?
            if edge().contains(event.pos()):
                self.crop_mode_event_start = event.pos()
                self.crop_mode_move = edge
                return
        # Click not in handle, end cropping mode:
        self.exit_crop_mode(
            confirm=self.crop_temp.contains(event.pos()))

    def ensure_point_within_crop_bounds(self, point, handle):
        """Returns the point, or the nearest point within the pixmap."""

        if handle == self.crop_handle_topleft:
            topleft = QtCore.QPointF(0, 0)
            bottomright = self.crop_temp.bottomRight()
        if handle == self.crop_handle_bottomleft:
            topleft = QtCore.QPointF(0, self.crop_temp.top())
            bottomright = QtCore.QPointF(
                self.crop_temp.right(), self.pixmap().size().height())
        if handle == self.crop_handle_bottomright:
            topleft = self.crop_temp.topLeft()
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.pixmap().size().height())
        if handle == self.crop_handle_topright:
            topleft = QtCore.QPointF(self.crop_temp.left(), 0)
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.crop_temp.bottom())
        if handle == self.crop_edge_top:
            topleft = QtCore.QPointF(0, 0)
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.crop_temp.bottom())
        if handle == self.crop_edge_bottom:
            topleft = QtCore.QPointF(0, self.crop_temp.top())
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.pixmap().size().height())
        if handle == self.crop_edge_left:
            topleft = QtCore.QPointF(0, 0)
            bottomright = QtCore.QPointF(
                self.crop_temp.right(), self.pixmap().size().height())
        if handle == self.crop_edge_right:
            topleft = QtCore.QPointF(self.crop_temp.left(), 0)
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.pixmap().size().height())

        point.setX(min(bottomright.x(), max(topleft.x(), point.x())))
        point.setY(min(bottomright.y(), max(topleft.y(), point.y())))

        return point

    def mouseMoveEvent(self, event):
        if self.crop_mode and self.crop_mode_event_start:
            diff = event.pos() - self.crop_mode_event_start
            if self.crop_mode_move == self.crop_handle_topleft:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setTopLeft(new)
            if self.crop_mode_move == self.crop_handle_bottomleft:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.bottomLeft() + diff, self.crop_mode_move)
                self.crop_temp.setBottomLeft(new)
            if self.crop_mode_move == self.crop_handle_bottomright:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.bottomRight() + diff, self.crop_mode_move)
                self.crop_temp.setBottomRight(new)
            if self.crop_mode_move == self.crop_handle_topright:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topRight() + diff, self.crop_mode_move)
                self.crop_temp.setTopRight(new)
            if self.crop_mode_move == self.crop_edge_top:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setTop(new.y())
            if self.crop_mode_move == self.crop_edge_left:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setLeft(new.x())
            if self.crop_mode_move == self.crop_edge_bottom:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.bottomLeft() + diff, self.crop_mode_move)
                self.crop_temp.setBottom(new.y())
            if self.crop_mode_move == self.crop_edge_right:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topRight() + diff, self.crop_mode_move)
                self.crop_temp.setRight(new.x())
            self.update()
            self.crop_mode_event_start = event.pos()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.crop_mode:
            self.crop_mode_move = None
            self.crop_mode_event_start = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)


@register_item
class BeeTextItem(TitleBandMixin, BeeItemMixin,
                  QtWidgets.QGraphicsTextItem):
    """Class for text added by the user."""

    TYPE = 'text'

    # The box's rounded corners, as a fraction of the height one line of
    # its largest text would give the box. A third is what the corners
    # have always been, so notes look unchanged.
    CORNER_RADIUS_FRACTION = 1 / 3

    # The gap between the text and the edge of its box, as a fraction of
    # the height of a line. Qt's own margin is a fixed four pixels,
    # which is this fraction of a line at the default text size: making
    # the text bigger then left the gap where it was, so the text crept
    # towards the edge. Scaling the item scales the gap by itself, and
    # this makes the toolbar behave the same way.
    TEXT_MARGIN_FRACTION = 4 / 15

    # The box drawn behind text by default: fully opaque, so text stays
    # readable whatever is behind it
    DEFAULT_BOX_COLOR = (0, 0, 0, 255)

    # Plain URL detection for ctrl+click. Trailing punctuation is
    # stripped afterwards, since it is usually sentence punctuation
    # rather than part of the address.
    URL_RE = re.compile(r'(?:https?://|www\.)\S+', re.IGNORECASE)
    URL_TRAILING_CHARS = '.,;:!?)]}\'"'

    # How much larger than the note's own text its title is. A note has
    # a type size of its own, unlike a group, so the heading is measured
    # against that rather than against the width -- a wide one-line note
    # would otherwise be given a heading fit for a poster.
    TITLE_SIZE_FRACTION = 1.15

    def __init__(self, text=None, html=None, box_color=None,
                 text_width=None, title=None, header_color=None,
                 title_align=None, title_size=None, **kwargs):
        super().__init__(text or "Text")
        self.save_id = None
        logger.debug(f'Initialized {self}')
        self.is_image = False
        self.init_selectable()
        # Before anything can ask how big the note is: an empty title
        # means no band, and a note that looks as it always did
        self.init_title(title, header_color, title_align)
        # A heading keeps the size it was given. Measuring it against
        # the words underneath meant that making one of them bigger
        # moved the band as well, which is not what was asked for.
        # None on a note written before this, which then takes the size
        # it used to be drawn at.
        self._title_size = title_size
        self.is_editable = True
        self.edit_mode = False
        self.settings = BeeSettings()
        # Wrap at whole words only. Qt's default also breaks inside a
        # word when one does not fit, which is never what is wanted in a
        # note: a word too long for the box hangs over the edge instead.
        option = self.document().defaultTextOption()
        option.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
        self.document().setDefaultTextOption(option)
        if text_width:
            self.set_wrap_width(text_width)
        # Setting the box colour also picks the text colour to go with it
        self.box_color = QtGui.QColor(*(box_color or self.DEFAULT_BOX_COLOR))
        self.setFont(self.get_text_font())
        self.table_drag = None
        # Whatever changes the text can change how big it is, so the
        # margin is kept up to date from one place rather than from
        # every caller that might resize a word
        self.document().contentsChanged.connect(self.update_document_margin)
        if html:
            # Rich text takes precedence over the plain text version,
            # which is only kept for compatibility with BeeRef
            self.setHtml(html)
            # Stored text carries its own colours, which have to
            # follow the box it now sits in
            self.refresh_text_colors()
        self.update_document_margin()
        if self._title and not self._title_size:
            # A note titled before headings kept a size of their own:
            # fixed here at what it has been being drawn at, so it
            # opens looking the way it did and then stays put
            self._title_size = self.title_size_from_text()

    def get_text_font(self):
        """The font new text is written in: the interface font.

        The bundled Ranade used to be forced on every note. It is one
        of two choices now, so nothing is forced -- including on notes
        written before, which keep whatever they were written in.
        """

        font = self.font()
        # Vertical hinting, not full. Full hinting snaps each letter's
        # width to a whole pixel, and it does not snap them all by the
        # same amount: in "minimum" at 9pt an m gains two thirds of a
        # pixel while an i gains a tenth, so the spacing within a word
        # comes out uneven -- and the canvas then magnifies that as it
        # is zoomed. Hinting only vertically keeps the crispness along
        # the baseline that small text wants, and leaves the widths
        # alone.
        font.setHintingPreference(
            QtGui.QFont.HintingPreference.PreferVerticalHinting)
        return font

    def font_families(self):
        """The two fonts text can be written in.

        The interface font, and the bundled one. The bundled one is
        ``None`` when the font files could not be loaded.
        """

        return QtWidgets.QApplication.font().family(), BeeAssets().font_family

    def uses_bundled_font(self):
        """Whether the selection, or the whole text, is in Ranade."""

        _, bundled = self.font_families()
        if not bundled:
            return False
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QtGui.QTextCursor.SelectionType.Document)
        return cursor.charFormat().font().family() == bundled

    def apply_font_family(self, family):
        charformat = QtGui.QTextCharFormat()
        charformat.setFontFamilies([family])
        self.apply_char_format(charformat)

    @classmethod
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data', {})
        item = cls(**data)
        return item

    def __str__(self):
        txt = self.toPlainText()[:40]
        return (f'Text "{txt}"')

    def get_default_name(self):
        text = self.toPlainText().strip().splitlines()
        if not text:
            return 'Text'
        return text[0][:40]

    @property
    def box_color(self):
        return self._box_color

    @box_color.setter
    def box_color(self, value):
        logger.debug(f'Setting box colour for {self} to {value.name()}')
        self._box_color = value
        self.setDefaultTextColor(readable_grey(self.visible_box_color()))
        self.update()

    def visible_box_color(self):
        """The box colour as it actually appears.

        A translucent box lets the canvas show through, so that is what
        the text has to be readable against.
        """

        canvas = QtGui.QColor(
            self.settings.valueOrDefault('View/canvas_color'))
        return blend_over(self.box_color, canvas)

    def get_extra_save_data(self):
        # 'text' is the plain text version, which BeeRef (and older
        # versions of this fork) will read; 'html' holds the formatting
        # and is ignored by anything that doesn't know about it.
        data = {'text': self.toPlainText(),
                'html': self.toHtml(),
                'box_color': self.box_color.getRgb()}
        data.update(self.title_save_data())
        if self._title_size:
            data['title_size'] = self._title_size
        if self.textWidth() > 0:
            # Only stored once the box has been given a width to wrap
            # at, so untouched text items save exactly as before
            data['text_width'] = self.textWidth()
        return data

    def contains(self, point):
        return self.boundingRect().contains(point)

    def text_line_height(self):
        """The height of a line of the box's largest text.

        In item coordinates, like everything else drawn here, so it
        already carries the item's own scale: text made bigger with the
        toolbar and text made bigger by dragging a corner both end up
        with the same size on the canvas, and so does anything measured
        against this.
        """

        font = QtGui.QFont(self.font())
        largest = self.largest_point_size()
        if largest > 0:
            font.setPointSizeF(largest)
        return QtGui.QFontMetricsF(font).height()

    def largest_point_size(self):
        """The size of the biggest text in the note, in points.

        Zero when nothing was ever sized, which means the note is being
        drawn at its own font's size.
        """

        largest = 0
        block = self.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                it += 1
                if fragment.isValid():
                    largest = max(largest,
                                  fragment.charFormat().fontPointSize())
            block = block.next()
        return largest

    def title_size(self):
        """How big the title's letters are.

        The size the heading was given, or -- on a note that has not
        been given one -- a little more than the words underneath.
        """

        if self._title_size:
            return self._title_size
        return self.title_size_from_text()

    def title_size_from_text(self):
        """What a heading over this note would start out at."""

        size = self.largest_point_size()
        if size <= 0:
            size = QtGui.QFontInfo(self.font()).pointSizeF()
        return min(self.TITLE_MAX_SIZE,
                   max(self.TITLE_MIN_SIZE, size * self.TITLE_SIZE_FRACTION))

    def stored_title_size(self):
        return self._title_size

    def set_title_size(self, size):
        """Make the heading bigger or smaller, band and all."""

        self._title_size = min(self.TITLE_MAX_SIZE,
                               max(self.TITLE_MIN_SIZE, size))
        self.on_title_changed()
        self.refresh_title_editor()

    def default_header_color(self):
        """A band with no colour of its own is the note's own box."""

        return self.box_color

    def text_rect(self):
        """The note without its band: the box the words sit in."""

        return QtWidgets.QGraphicsTextItem.boundingRect(self)

    def header_rect(self):
        """The band sitting on top of the note.

        Above the words rather than over them, so adding a title never
        covers up what was written.
        """

        rect = self.text_rect()
        height = self.header_height()
        return QtCore.QRectF(rect.x(), rect.y() - height,
                             rect.width(), height)

    def on_title_changed(self):
        # The band is added above the words, so the note is a different
        # size once a title comes or goes
        if self._title and not self._title_size:
            # Fixed the moment the band first appears, so that it stops
            # moving when the words under it change
            self._title_size = self.title_size_from_text()
        self.prepareGeometryChange()
        self.update()

    def title_band_path(self):
        """The band, with its top corners taken off."""

        return half_rounded_path(
            self.header_rect(), self.corner_radius(), top=True)

    def text_box_path(self):
        """The box behind the words.

        Square across the top when a band sits on it: the band brings
        the rounded corners, and rounding both sides of the join left
        the canvas showing through it.
        """

        rect = self.text_rect()
        radius = self.corner_radius()
        if not self.shows_header():
            path = QtGui.QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            return path
        return half_rounded_path(rect, radius, top=False)

    def paint_header(self, painter):
        """Draw the title band and the title in it."""

        if not self.shows_header():
            return
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(self.header_color or self.box_color))
        painter.drawPath(self.title_band_path())
        self.paint_title_text(painter)
        painter.restore()

    def boundingRect(self):
        """Room for the title band on top of whatever else needs room.

        Only the painting bounds grow. The note's own rectangle stays
        what it was, so the selection handles and the point a line
        fastens to stay on the words rather than stepping up over a
        heading.
        """

        rect = super().boundingRect()
        if self.shows_header():
            rect = rect.adjusted(0, -self.header_height(), 0, 0)
        return rect

    def shape(self):
        """The note, and the band sitting on top of it.

        So that the band can be clicked and double-clicked like part of
        the note.
        """

        path = super().shape()
        if self.shows_header():
            path.addRect(self.header_rect())
        return path

    def update_document_margin(self):
        """Keep the gap around the text in proportion to the text."""

        self.document().setDocumentMargin(
            self.text_line_height() * self.TEXT_MARGIN_FRACTION)

    def one_line_height(self):
        """The height this box would have if it held a single line."""

        return self.text_line_height() + 2 * self.document().documentMargin()

    def corner_radius(self):
        """The corner radius for the box at its current size.

        A third of the height of one line of text, rather than a third
        of the whole box. Measuring the whole box meant a note with many
        lines got corners far larger than its own line height, and the
        curve then cut into the text sitting in those corners.

        Using the height one line would give -- margins included --
        rather than the bare text keeps the corners at the same third of
        the box they have always been at every text size. Going by the
        bare text made them creep towards half the box as the text grew,
        until the box looked like a capsule.

        The width still counts, so a box only a character or two wide
        does not get rounded away.
        """

        rect = QtWidgets.QGraphicsTextItem.boundingRect(self)
        shorter = min(rect.width(), self.one_line_height())
        return shorter * self.CORNER_RADIUS_FRACTION

    def selection_corner_radius(self):
        """Match the box drawn behind the text.

        The default outline radius is fixed to the screen instead, which
        left the blue line square against rounded corners.
        """

        return self.corner_radius()

    def paint(self, painter, option, widget):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(self.box_color))
        painter.drawPath(self.text_box_path())
        self.paint_header(painter)
        option.state = QtWidgets.QStyle.StateFlag.State_Enabled
        super().paint(painter, option, widget)
        self.paint_selectable(painter, option, widget)

    # How close to a boundary counts as grabbing it, and how small a
    # row or column may be dragged, both in item coordinates.
    TABLE_GRIP = 5
    TABLE_MIN_WIDTH = 20
    TABLE_MIN_EXTRA_HEIGHT = 0

    def cell_rect(self, table, row, column):
        """Where a cell's contents sit, in item coordinates."""

        layout = self.document().documentLayout()
        return layout.blockBoundingRect(
            table.cellAt(row, column).firstCursorPosition().block())

    def table_boundaries(self, table):
        """Where the column and row boundaries are.

        Each entry is the index of the column or row that a drag there
        resizes, paired with its position. Taken from the laid out
        cells rather than added up from the stored widths, so borders
        and padding are already accounted for.
        """

        layout = self.document().documentLayout()
        frame = layout.frameBoundingRect(table)

        columns = []
        for c in range(table.columns() - 1):
            here = self.cell_rect(table, 0, c).right()
            next_one = self.cell_rect(table, 0, c + 1).left()
            columns.append((c, (here + next_one) / 2))
        columns.append((table.columns() - 1, frame.right()))

        rows = []
        for r in range(table.rows() - 1):
            here = self.cell_rect(table, r, 0).bottom()
            next_one = self.cell_rect(table, r + 1, 0).top()
            rows.append((r, (here + next_one) / 2))
        rows.append((table.rows() - 1, frame.bottom()))
        return columns, rows

    def table_grip_at(self, pos):
        """What a press at this point would resize, if anything.

        Returns ``(kind, table number, index)`` -- the kind being
        'column' or 'row' -- or None. The table is named by its number
        in the note rather than handed back: a note can hold more than
        one, and the drag must not end up resizing a different one.
        Only boundaries within the table's own height or width count,
        so the space beside a table does not grab its rows.
        """

        layout = self.document().documentLayout()
        grip = self.TABLE_GRIP
        for number, table in enumerate(self.tables()):
            frame = layout.frameBoundingRect(table)
            columns, rows = self.table_boundaries(table)
            if frame.top() - grip <= pos.y() <= frame.bottom() + grip:
                for index, x in columns:
                    if abs(pos.x() - x) <= grip:
                        return ('column', number, index)
            if frame.left() - grip <= pos.x() <= frame.right() + grip:
                for index, y in rows:
                    if abs(pos.y() - y) <= grip:
                        return ('row', number, index)
        return None

    def row_extra_height(self, table, row):
        """The padding added to a row on top of the table's own."""

        return table.cellAt(row, 0).format().toTableCellFormat(
            ).bottomPadding()

    def set_row_extra_height(self, table, row, extra):
        """Make a row taller by padding its cells underneath.

        Qt sizes rows to their contents and offers no row height, so
        the padding is the only handle there is.
        """

        extra = max(self.TABLE_MIN_EXTRA_HEIGHT, extra)
        for column in range(table.columns()):
            cell = table.cellAt(row, column)
            fmt = cell.format().toTableCellFormat()
            fmt.setBottomPadding(extra)
            cell.setFormat(fmt)

    def put_cursor_at(self, pos):
        """Move the cursor to a point given in item coordinates.

        Right-clicking a cell has to put the cursor in it, or the table
        commands would have no cell to work from and would stay greyed
        out on a note that plainly holds a table.
        """

        layout = self.document().documentLayout()
        cursor_pos = layout.hitTest(pos, Qt.HitTestAccuracy.FuzzyHit)
        if cursor_pos < 0:
            return
        cursor = self.textCursor()
        cursor.setPosition(cursor_pos)
        self.setTextCursor(cursor)

    def get_url_at(self, pos):
        """The URL at the given position in item coordinates, if any."""

        layout = self.document().documentLayout()
        cursor_pos = layout.hitTest(pos, Qt.HitTestAccuracy.ExactHit)
        if cursor_pos < 0:
            return None
        return self.get_url_at_cursor_pos(cursor_pos)

    def get_url_at_cursor_pos(self, cursor_pos):
        """The URL at the given position in the text, if any."""

        block = self.document().findBlock(cursor_pos)
        offset = cursor_pos - block.position()
        for match in self.URL_RE.finditer(block.text()):
            if match.start() <= offset < match.end():
                url = match.group().rstrip(self.URL_TRAILING_CHARS)
                if url.lower().startswith('www.'):
                    url = f'http://{url}'
                return url
        return None

    def hoverMoveEvent(self, event):
        """Show a split cursor over a row or column boundary."""

        grip = self.table_grip_at(event.pos())
        if grip is not None:
            self.set_cursor(Qt.CursorShape.SplitHCursor
                            if grip[0] == 'column'
                            else Qt.CursorShape.SplitVCursor)
            return
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier):
            url = self.get_url_at(event.pos())
            if url:
                logger.debug(f'Opening url: {url}')
                QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
                event.accept()
                return

        if (event.button() == Qt.MouseButton.LeftButton
                and not event.modifiers()):
            grip = self.table_grip_at(event.pos())
            if grip is not None:
                self.start_table_drag(grip, event.pos())
                event.accept()
                return

        super().mousePressEvent(event)

    def start_table_drag(self, grip, pos):
        """Begin dragging a row or column boundary.

        Only numbers are remembered, never the table itself: finishing
        the drag replaces the note's html, which destroys every frame
        in the document and would leave a held table dangling.
        """

        kind, number, index = grip
        table = self.tables()[number]
        if kind == 'column':
            size = self.column_widths(table)[index]
        else:
            size = self.row_extra_height(table, index)
        self.table_drag = {
            'kind': kind,
            'number': number,
            'index': index,
            'start': pos,
            'size': size,
            'html': self.toHtml(),
        }
        logger.debug(f'Started dragging table {kind} {index}')

    def mouseMoveEvent(self, event):
        if getattr(self, 'table_drag', None):
            self.drag_table_boundary(event.pos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def drag_table_boundary(self, pos):
        drag = self.table_drag
        table = self.tables()[drag['number']]
        if drag['kind'] == 'column':
            widths = self.column_widths(table)
            moved = pos.x() - drag['start'].x()
            widths[drag['index']] = max(
                self.TABLE_MIN_WIDTH, drag['size'] + moved)
            self.set_column_widths(table, widths)
        else:
            moved = pos.y() - drag['start'].y()
            self.set_row_extra_height(
                table, drag['index'], drag['size'] + moved)

    def mouseReleaseEvent(self, event):
        drag = getattr(self, 'table_drag', None)
        if drag:
            self.table_drag = None
            self.scene().undo_stack.push(commands.ChangeTextFormat(
                [self], [self.toHtml()], [drag['html']]))
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self.cursor_may_have_moved()

    def search_text(self):
        """What Find looks through: the title and the note under it.

        The plain text of a note runs a table's cells together with the
        rest of it, which is exactly what a search wants.
        """

        if self.title:
            return f'{self.title}\n{self.toPlainText()}'
        return self.toPlainText()

    def search_rect(self, query):
        """Where the first match sits on the board, in scene coordinates."""

        text = self.toPlainText()
        start = text.lower().find(query.lower())
        if start < 0:
            if self.title and query.lower() in self.title.lower():
                # Only the heading matches, and it is drawn straight
                # onto the note rather than laid out in a document, so
                # the band is what there is to go to
                return self.title_search_rect()
            return None
        cursor = QtGui.QTextCursor(self.document())
        cursor.setPosition(start)
        block = cursor.block()
        layout = block.layout()
        if layout is None:
            return None
        offset = start - block.position()
        line = layout.lineForTextPosition(offset)
        if not line.isValid():
            return None
        left = line.cursorToX(offset)[0]
        right = line.cursorToX(min(offset + len(query),
                                   block.length() - 1))[0]
        origin = self.document().documentLayout().blockBoundingRect(
            block).topLeft()
        rect = QtCore.QRectF(origin.x() + min(left, right),
                             origin.y() + line.y(),
                             abs(right - left), line.height())
        return self.mapToScene(rect).boundingRect()

    def selected_range(self):
        """The selected text, or all of it when nothing is selected."""

        cursor = self.textCursor()
        if cursor.hasSelection():
            return cursor.selectionStart(), cursor.selectionEnd()
        return 0, self.document().characterCount() - 1

    def text_runs(self, start, end):
        """Each stretch of text between start and end sharing a format.

        Returns (from, to, format) tuples, collected before anything is
        changed: editing the document while walking it invalidates the
        fragments being walked.
        """

        runs = []
        block = self.document().findBlock(start)
        while block.isValid() and block.position() < end:
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                it += 1
                if not fragment.isValid():
                    continue
                frag_start = fragment.position()
                frag_end = frag_start + fragment.length()
                if frag_end <= start or frag_start >= end:
                    continue
                runs.append((max(frag_start, start), min(frag_end, end),
                             fragment.charFormat()))
            block = block.next()
        return runs

    def apply_to_run(self, start, end, charformat):
        """Merge a format into one stretch of text."""

        cursor = QtGui.QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.mergeCharFormat(charformat)

    def text_color_over(self, background=None):
        """The colour text reads best in where it sits.

        Highlighted words sit on their highlight, everything else on the
        box, and a translucent highlight is judged by what it looks like
        over that box.
        """

        if (background is None or not background.isValid()
                or background.alpha() == 0):
            return QtGui.QColor(self.defaultTextColor())
        return readable_grey(blend_over(background, self.visible_box_color()))

    def run_background(self, charformat):
        """The highlight colour of a run, or None if it has none."""

        brush = charformat.background()
        if brush.style() == Qt.BrushStyle.NoBrush:
            return None
        return brush.color()

    # A new table's shape and spacing, in item coordinates. The column
    # width is a starting point only: dragging a boundary changes it.
    TABLE_ROWS = 3
    TABLE_COLUMNS = 3
    TABLE_COLUMN_WIDTH = 90
    TABLE_PADDING = 4

    def table_format(self):
        """The look of a table: thin borders in the text's own colour."""

        fmt = QtGui.QTextTableFormat()
        fmt.setBorder(1)
        fmt.setBorderStyle(
            QtGui.QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        fmt.setBorderBrush(QtGui.QBrush(self.defaultTextColor()))
        fmt.setCellPadding(self.TABLE_PADDING)
        fmt.setCellSpacing(0)
        return fmt

    def insert_table(self, rows=None, columns=None):
        """Put a table where the cursor is."""

        rows = rows or self.TABLE_ROWS
        columns = columns or self.TABLE_COLUMNS
        fmt = self.table_format()
        fmt.setColumnWidthConstraints([
            QtGui.QTextLength(QtGui.QTextLength.Type.FixedLength,
                              self.TABLE_COLUMN_WIDTH)] * columns)
        table = self.textCursor().insertTable(rows, columns, fmt)
        # Leave the cursor in the first cell, ready to type
        self.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        return table

    def tables(self):
        """Every table in this item, outermost first.

        Only for looking at what a note contains. Use
        ``current_table`` for the one being worked on.
        """

        return [frame for frame in self.document().rootFrame().childFrames()
                if isinstance(frame, QtGui.QTextTable)]

    def current_table(self):
        """The table the cursor is in, or None.

        Asked of the cursor rather than found by walking the document's
        frames. This is called on every selection change, and each walk
        made a fresh handle for every table in the note -- handles onto
        objects the document owns and destroys without warning.
        """

        return self.textCursor().currentTable()

    def current_cell(self):
        table = self.current_table()
        if table is None:
            return None
        return table.cellAt(self.textCursor())

    def insert_table_row(self, below=True):
        cell = self.current_cell()
        if cell is None:
            return
        row = cell.row() + (1 if below else 0)
        self.current_table().insertRows(row, 1)

    def insert_table_column(self, right=True):
        cell = self.current_cell()
        if cell is None:
            return
        table = self.current_table()
        column = cell.column() + (1 if right else 0)
        table.insertColumns(column, 1)
        self.spread_column_widths(table)

    def remove_table_row(self):
        cell = self.current_cell()
        if cell is None:
            return
        table = self.current_table()
        if table.rows() <= 1:
            # The last row is the table; removing it would leave nothing
            return
        row, column = cell.row(), cell.column()
        table.removeRows(row, 1)
        self.put_cursor_in_cell(table, row, column)

    def remove_table_column(self):
        cell = self.current_cell()
        if cell is None:
            return
        table = self.current_table()
        if table.columns() <= 1:
            return
        row, column = cell.row(), cell.column()
        table.removeColumns(column, 1)
        self.spread_column_widths(table)
        self.put_cursor_in_cell(table, row, column)

    def put_cursor_in_cell(self, table, row, column):
        """Keep the cursor in the table after a row or column goes.

        Removing what the cursor was in leaves it outside the table, so
        the next command would find no table to work on -- two rows
        could not be removed one after the other.
        """

        row = min(row, table.rows() - 1)
        column = min(column, table.columns() - 1)
        self.setTextCursor(table.cellAt(row, column).firstCursorPosition())

    def spread_column_widths(self, table):
        """Give every column a width, after their number has changed.

        Qt keeps the old list of widths, which then has the wrong length
        and leaves the new column sized by whatever it holds.
        """

        widths = [w.rawValue() for w in
                  table.format().columnWidthConstraints()]
        default = widths[0] if widths else self.TABLE_COLUMN_WIDTH
        widths = (widths + [default] * table.columns())[:table.columns()]
        self.set_column_widths(table, widths)

    def set_column_widths(self, table, widths):
        fmt = table.format()
        fmt.setColumnWidthConstraints([
            QtGui.QTextLength(QtGui.QTextLength.Type.FixedLength, w)
            for w in widths])
        table.setFormat(fmt)

    def column_widths(self, table):
        return [w.rawValue() for w in table.format().columnWidthConstraints()]

    # How far a header cell's background moves from the box towards the
    # text colour. Enough to read as a heading, not so much that it
    # fights with a cell coloured on purpose.
    HEADER_TINT = 0.18

    def header_shade(self):
        """The background a header row or column is given.

        Worked out from the box the note is drawn on, so a header looks
        right on a black board and on a coloured note alike.
        """

        tint = QtGui.QColor(self.defaultTextColor())
        tint.setAlphaF(self.HEADER_TINT)
        return blend_over(tint, self.visible_box_color())

    def header_cells(self, table, index, column=False):
        """One row of cells, or one column of them."""

        if column:
            return [table.cellAt(row, index) for row in range(table.rows())]
        return [table.cellAt(index, col) for col in range(table.columns())]

    def shared_background(self, cells):
        """The one background these cells share, or None if they differ."""

        shades = set()
        for cell in cells:
            brush = cell.format().background()
            shades.add(None if brush.style() == Qt.BrushStyle.NoBrush
                       else brush.color().rgba())
        return shades.pop() if len(shades) == 1 else None

    def has_header(self, table, column=False):
        """Whether the first row -- or column -- is set apart as a header.

        Read off the shading rather than kept in a flag. The shading is
        what makes a header look like one, and unlike a flag of our own
        it survives being written to a file and read back.
        """

        shade = self.shared_background(self.header_cells(table, 0, column))
        if shade is None:
            return False
        neighbours = table.columns() if column else table.rows()
        if neighbours < 2:
            # Nothing to stand out from, so the shading is the header
            return True
        return shade != self.shared_background(
            self.header_cells(table, 1, column))

    def set_header(self, table, on, column=False):
        """Shade the first row -- or the first column -- or clear it.

        The shading is the whole of it. Bold was the obvious companion,
        but Qt keeps no formatting in a cell with nothing in it, so the
        header cells still empty would come back from a file unbold
        while the filled ones stayed bold.
        """

        shade = self.header_shade()
        # The corner cell belongs to both headers. Asked now, before
        # anything is cleared, because clearing it is what would make
        # the other header stop counting as one.
        corner_stays = not on and self.has_header(table, not column)

        for cell in self.header_cells(table, 0, column):
            fmt = cell.format().toTableCellFormat()
            fmt.setBackground(QtGui.QBrush(shade) if on else QtGui.QBrush())
            cell.setFormat(fmt)
        if corner_stays:
            corner = table.cellAt(0, 0)
            fmt = corner.format().toTableCellFormat()
            fmt.setBackground(QtGui.QBrush(shade))
            corner.setFormat(fmt)
        if not column:
            # Qt's own idea of a header row. It changes nothing on
            # screen, but it is the right thing to record and it is
            # what a table carries into other programs.
            fmt = table.format()
            fmt.setHeaderRowCount(1 if on else 0)
            table.setFormat(fmt)

    def toggle_header(self, column=False):
        """Turn the header of the table being edited on or off."""

        table = self.current_table()
        if table is None:
            return
        self.set_header(table, not self.has_header(table, column), column)

    def apply_cell_color(self, color):
        """Colour the cells the selection touches, or the one cursor is in."""

        cells = self.selected_cells()
        for cell in cells:
            fmt = cell.format().toTableCellFormat()
            fmt.setBackground(color)
            cell.setFormat(fmt)
            # The words in the cell have to stay readable on it
            charformat = QtGui.QTextCharFormat()
            charformat.setForeground(self.text_color_over(color))
            cursor = cell.firstCursorPosition()
            cursor.setPosition(cell.lastCursorPosition().position(),
                               QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(charformat)

    def selected_cells(self):
        """The cells the selection covers, or the single cell cursor is in."""

        table = self.current_table()
        if table is None:
            return []
        cursor = self.textCursor()
        if cursor.hasComplexSelection():
            first_row, rows, first_col, cols = cursor.selectedTableCells()
            return [table.cellAt(first_row + r, first_col + c)
                    for r in range(rows) for c in range(cols)]
        cell = table.cellAt(cursor)
        return [cell] if cell.isValid() else []

    def apply_highlight(self, color):
        """Highlight the selection, in a colour the words can be read on."""

        charformat = QtGui.QTextCharFormat()
        charformat.setBackground(color)
        charformat.setForeground(self.text_color_over(color))
        self.apply_char_format(charformat)

    def refresh_text_colors(self):
        """Recolour every run for the background it sits on.

        Plain text follows the box, highlighted words follow their own
        highlight. One colour across the whole text would make
        highlighted words unreadable whenever the box colour changed.
        """

        for start, end, charformat in self.text_runs(
                0, self.document().characterCount() - 1):
            new_format = QtGui.QTextCharFormat()
            new_format.setForeground(
                self.text_color_over(self.run_background(charformat)))
            self.apply_to_run(start, end, new_format)

    def scale_font_size(self, factor, minimum, maximum):
        """Multiply the size of the selected text, or of all of it.

        Every run of text is scaled by its own size, so differences
        within the selection survive: a heading stays bigger than the
        body text around it. Setting one size for the whole selection,
        as a plain point size does, would flatten them together.
        """

        # Pinned to what it is now, so that bigger words wrap inside
        # the note instead of pushing its edges out and shoving the rest
        # of the board along with them. The note still grows downwards,
        # so nothing written in it is hidden.
        if self.textWidth() <= 0:
            self.set_wrap_width(self.text_rect().width())

        start, end = self.selected_range()
        edits = []
        for run_start, run_end, charformat in self.text_runs(start, end):
            size = charformat.fontPointSize()
            if size <= 0:
                # Text that was never sized reports zero; QFontInfo
                # resolves what it is actually being drawn at
                size = QtGui.QFontInfo(self.font()).pointSize()
            edits.append((run_start, run_end,
                          min(maximum, max(minimum, size * factor))))

        for run_start, run_end, size in edits:
            charformat = QtGui.QTextCharFormat()
            charformat.setFontPointSize(size)
            self.apply_to_run(run_start, run_end, charformat)

    def apply_char_format(self, charformat):
        """Apply the given char format to the current selection, or to the
        whole text if nothing is selected."""

        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QtGui.QTextCursor.SelectionType.Document)
        cursor.mergeCharFormat(charformat)

    # Narrower than this and the text has nowhere to go
    MIN_WRAP_WIDTH = 40

    def reflows_text(self):
        """Dragging an edge rewraps the text rather than stretching it."""

        return True

    def set_wrap_width(self, width):
        """Set the width the text wraps at, in item coordinates."""

        self.prepareGeometryChange()
        self.setTextWidth(max(self.MIN_WRAP_WIDTH, width))
        self.update_document_margin()

    def create_copy(self):
        item = BeeTextItem(html=self.toHtml(),
                           box_color=self.box_color.getRgb(),
                           text_width=(self.textWidth()
                                       if self.textWidth() > 0 else None),
                           title=self.title,
                           title_align=self.title_align,
                           title_size=self._title_size,
                           header_color=(self.header_color.getRgb()
                                         if self.header_color else None))
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        if self.flip() == -1:
            item.do_flip()
        return item

    def enter_edit_mode(self):
        logger.debug(f'Entering edit mode on {self}')
        self.edit_mode = True
        self.old_text = self.toHtml()
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction)
        # Explicit, so that editing also works when edit mode isn't
        # entered by clicking the item
        self.setFocus()
        self.scene().edit_item = self

    def cursor_may_have_moved(self):
        """Keep the table commands in step with the cell being written in.

        Called after the events that move the cursor. The document's own
        ``cursorPositionChanged`` looked like the obvious signal for
        this, but it does not fire when the cursor is only moved -- which
        is exactly the case that matters here.
        """

        scene = self.scene()
        if scene is not None and self.edit_mode:
            scene.text_cursor_moved()

    def exit_edit_mode(self, commit=True):
        logger.debug(f'Exiting edit mode on {self}')
        self.edit_mode = False
        # reset selection:
        self.setTextCursor(QtGui.QTextCursor(self.document()))
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.scene().edit_item = None
        if commit:
            self.scene().undo_stack.push(
                commands.ChangeText(self, self.toHtml(), self.old_text))
            if not self.toPlainText().strip() and not self.tables():
                # A note holding a table is not empty, even before a
                # word is typed into it: an empty table is the whole
                # point of having just made one
                logger.debug('Removing empty text item')
                self.scene().undo_stack.push(
                    commands.DeleteItems(self.scene(), [self]))
        else:
            self.setHtml(self.old_text)

    def has_selection_handles(self):
        return super().has_selection_handles() and not self.edit_mode

    def keyPressEvent(self, event):
        # Enter starts a new paragraph, the way it does when typing
        # anywhere else. Editing ends by clicking outside the item, or
        # with Escape to throw the changes away.
        if (event.key() == Qt.Key.Key_Escape
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            self.exit_edit_mode(commit=False)
            event.accept()
            return
        super().keyPressEvent(event)
        self.cursor_may_have_moved()

    def add_to_mimedata(self, mimedata):
        mimedata.setText(self.toPlainText())


@register_item
class BeeErrorItem(BeeItemMixin, QtWidgets.QGraphicsTextItem):
    """Class for displaying error messages when an item can't be loaded
    from a bee file.

    This item will be displayed instead of the original item. It won't
    save to bee files. The original item will be preserved in the bee
    file, unless this item gets deleted by the user, or a new bee file
    is saved.
    """

    TYPE = 'error'

    def __init__(self, text=None, **kwargs):
        super().__init__(text or "Text")
        self.original_save_id = None
        logger.debug(f'Initialized {self}')
        self.is_image = False
        self.init_selectable()
        self.is_editable = False
        self.setDefaultTextColor(QtGui.QColor(*COLORS['Scene:Text']))

    @classmethod
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data', {})
        item = cls(**data)
        return item

    def __str__(self):
        txt = self.toPlainText()[:40]
        return (f'Error "{txt}"')

    def contains(self, point):
        return self.boundingRect().contains(point)

    def paint(self, painter, option, widget):
        painter.setPen(Qt.PenStyle.NoPen)
        color = QtGui.QColor(200, 0, 0)
        brush = QtGui.QBrush(color)
        painter.setBrush(brush)
        painter.drawRoundedRect(
            QtWidgets.QGraphicsTextItem.boundingRect(self),
            CORNER_RADIUS, CORNER_RADIUS)
        option.state = QtWidgets.QStyle.StateFlag.State_Enabled
        super().paint(painter, option, widget)
        self.paint_selectable(painter, option, widget)

    def update_from_data(self, **kwargs):
        self.original_save_id = kwargs.get('save_id', self.original_save_id)
        self.setPos(kwargs.get('x', self.pos().x()),
                    kwargs.get('y', self.pos().y()))
        self.setZValue(kwargs.get('z', self.zValue()))
        self.setScale(kwargs.get('scale', self.scale()))
        self.setRotation(kwargs.get('rotation', self.rotation()))

    def create_copy(self):
        item = BeeErrorItem(self.toPlainText())
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        return item

    def flip(self, *args, **kwargs):
        """Returns the flip value (1 or -1)"""
        # Never display error messages flipped
        return 1

    def do_flip(self, *args, **kwargs):
        """Flips the item."""
        # Never flip error messages
        pass

    def add_to_mimedata(self, mimedata):
        mimedata.setText(self.toPlainText())
