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

from functools import partial
import logging
import math
import os
import os.path
import time

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref.assets import BeeAssets
from beeref.actions import ActionsMixin, actions
from beeref import commands
from beeref.config import (
    CommandlineArgs, BeeSettings, KeyboardSettings, settings_events)
from beeref import constants
from beeref import tables
from beeref import fileio
from beeref.fileio.errors import IMG_LOADING_ERROR_MSG
from beeref.fileio.export import exporter_registry, ImagesToDirectoryExporter
from beeref import widgets
from beeref.items import (
    BeeDrawItem, BeeGroupItem, BeePixmapItem, BeeTextItem,
    without_pointless_alpha)
from beeref.main_controls import MainControlsMixin
from beeref.scene import BeeGraphicsScene
from beeref.utils import get_file_extension_from_format, qcolor_to_hex


commandline_args = CommandlineArgs()
logger = logging.getLogger(__name__)


def save_dialog_filter():
    """What the save dialog offers: our own files only."""

    return f'{constants.APPNAME} File (*{constants.FILE_EXT})'


def open_dialog_filter():
    """What the open dialog offers.

    Our own files, and separately the ones BeeRef writes, so older
    boards can still be opened without cluttering the usual case.
    """

    return (f'{constants.APPNAME} Files (*{constants.FILE_EXT});;'
            f'{constants.UPSTREAM_NAME} Files '
            f'(*{constants.LEGACY_FILE_EXT});;'
            'All Files (*)')


class BeeGraphicsView(MainControlsMixin,
                      QtWidgets.QGraphicsView,
                      ActionsMixin):

    PAN_MODE = 1
    ZOOM_MODE = 2

    # How much of the window an image takes when it arrives. Images
    # used to come in at their own pixel size, so a small one landed
    # too small to see and had to be scaled up by hand every time.
    NEW_IMAGE_SHARE = 0.5

    # How wide the picture saved with a board is. Small enough to sit
    # in the file without being noticed, big enough to recognise a
    # board by in the recent files list.
    THUMBNAIL_WIDTH = 320

    # Smoothing the wheel zoom: how often a step is taken, how much of
    # what is left each step covers, and how little is worth another
    # step. Dragging to zoom is left alone -- it already follows the
    # mouse, and easing it would only add lag.
    ZOOM_INTERVAL = 16
    ZOOM_SMOOTHING = 0.3
    ZOOM_REMAINDER = 1
    # The most a single late frame may make up for. Without it, coming
    # back to a window that was buried would finish the zoom in one jump
    ZOOM_MAX_CATCHUP = 6
    SAMPLE_COLOR_MODE = 3

    # On-screen bounds in pixels between which the grid spacing is kept
    # The closest and furthest apart the grid is allowed to look on
    # screen, whatever spacing the settings ask for.
    GRID_MIN_SPACING = 25
    GRID_MAX_SPACING = 250

    # Range offered when changing the size of text
    TEXT_SIZE_MIN = 4
    TEXT_SIZE_MAX = 400
    # How much one press of the bigger/smaller buttons changes the text.
    # A factor, not a number of points, so the step stays proportional:
    # 10% of a heading is a lot more than 10% of a caption, which is what
    # keeps them looking related as they are scaled.
    TEXT_SIZE_STEP = 1.1
    # Lines are small numbers, so they need a bigger step than text to
    # get anywhere in a few presses
    LINE_WIDTH_STEP = 1.25

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.parent = parent
        self.settings = BeeSettings()
        self.keyboard_settings = KeyboardSettings()
        self.welcome_overlay = widgets.welcome_overlay.WelcomeOverlay(self)
        # Built early: a resize can arrive before the end of setup
        self.shortcuts_hint = widgets.shortcuts_hint.ShortcutsHint(self)
        self.loading_overlay = (
            widgets.loading_overlay.LoadingOverlay(self))
        self.layers_handle = widgets.layers.LayersHandle(self, self)
        self.legend_handle = widgets.legend.LegendHandle(self, self)

        # Set before the actions are built, since the grid toggle acts
        # on it as soon as it is restored from the settings
        self.show_grid = False
        self.on_canvas_color_changed(
            self.settings.valueOrDefault('View/canvas_color'))
        settings_events.canvas_color_changed.connect(
            self.on_canvas_color_changed)
        settings_events.grid_changed.connect(self.on_grid_changed)
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # Without this, text on the canvas is left to whatever the
        # painter defaults to, which reads poorly at small sizes
        self.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.undo_stack = QtGui.QUndoStack(self)
        self.undo_stack.setUndoLimit(100)
        self.undo_stack.canRedoChanged.connect(self.on_can_redo_changed)
        self.undo_stack.canUndoChanged.connect(self.on_can_undo_changed)
        self.undo_stack.cleanChanged.connect(self.on_undo_clean_changed)

        self.filename = None
        self.previous_transform = None
        self.active_mode = None
        # Wheel zooming is spread over a few frames: a notch of the
        # wheel is a change of about twelve percent, and arriving there
        # in one jump is what makes zooming feel steppy
        self.pending_zoom = 0
        self.zoom_anchor = None
        self.last_zoom_step = None
        # Where a line being drawn would fasten itself, if it were let
        # go now; see show_snap_preview
        self.snap_preview = None
        # What a pan could not spend, kept for the next one
        self.pan_remainder = QtCore.QPointF(0, 0)
        self.zoom_timer = QtCore.QTimer(self)
        self.zoom_timer.setInterval(self.ZOOM_INTERVAL)
        self.zoom_timer.timeout.connect(self.step_zoom)
        self.text_search_query = ''
        self.text_search_index = -1

        # Drawing tools
        self.draw_tool = None
        self.drawing_item = None
        self.drawing_points = []
        self.draw_color = QtGui.QColor(*BeeDrawItem.DEFAULT_COLOR)
        self.draw_width = BeeDrawItem.DEFAULT_WIDTH

        self.scene = BeeGraphicsScene(self.undo_stack)
        self.scene.changed.connect(self.on_scene_changed)
        self.scene.selectionChanged.connect(self.on_selection_changed)
        self.scene.cursor_changed.connect(self.on_cursor_changed)
        self.scene.cursor_cleared.connect(self.on_cursor_cleared)
        self.setScene(self.scene)

        # Built before the actions, since the toggle acts on it as soon
        # as it is restored from the settings
        self.layers_dock = widgets.layers.LayersDock(parent, self)
        self.update_layers_handle()
        self.legend_dock = widgets.legend.LegendDock(parent, self)
        self.update_legend_handle()

        # Context menu and actions
        self.build_menu_and_actions()
        self.control_target = self
        self.init_main_controls(main_window=parent)

        # Load files given via command line
        if commandline_args.filenames:
            fn = commandline_args.filenames[0]
            if fileio.is_bee_file(fn):
                self.open_from_file(fn)
            else:
                self.do_insert_images(commandline_args.filenames)

        self.update_window_title()

        # The drawing tools, in the top left corner
        self.draw_toolbar = widgets.draw_toolbar.DrawToolBar(self, self)
        self.draw_toolbar.reposition()
        self.draw_toolbar.show()

        # These follow what is selected; see update_pinned_toolbars
        self.text_toolbar = widgets.text_toolbar.TextToolBar(self, self)
        self.text_toolbar.hide()
        self.draw_item_toolbar = widgets.draw_item_toolbar.DrawItemToolBar(
            self, self)
        self.draw_item_toolbar.hide()
        self.group_toolbar = widgets.group_toolbar.GroupToolBar(self, self)
        self.group_toolbar.hide()
        self.image_toolbar = widgets.image_toolbar.ImageToolBar(self, self)
        self.image_toolbar.hide()
        self.table_toolbar = widgets.table_toolbar.TableToolBar(self, self)
        self.table_toolbar.hide()

        self.apply_palette_to_color_dialogs()

        # A reminder of the shortcuts, until the user dismisses it
        self.shortcuts_hint.show_if_wanted()

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, value):
        self._filename = value
        self.update_window_title()
        if value:
            self.settings.update_recent_files(value)
            self.update_menu_and_actions()

    def cancel_active_modes(self):
        self.scene.cancel_active_modes()
        self.cancel_sample_color_mode()
        self.active_mode = None

    def cancel_sample_color_mode(self):
        logger.debug('Cancel sample color mode')
        self.active_mode = None
        self.viewport().unsetCursor()
        if hasattr(self, 'sample_color_widget'):
            self.sample_color_widget.hide()
            del self.sample_color_widget
        if self.scene.has_multi_selection():
            self.scene.multi_select_item.bring_to_front()

    def update_window_title(self):
        # The version goes in the title because two computers run this,
        # and the only way to tell which build a window belongs to used
        # to be opening Help - About
        app = f'{constants.APPNAME} {constants.VERSION}'
        clean = self.undo_stack.isClean()
        if clean and not self.filename:
            title = app
        else:
            name = os.path.basename(self.filename or '[Untitled]')
            clean = '' if clean else '*'
            title = f'{name}{clean} - {app}'
        self.parent.setWindowTitle(title)

    def on_canvas_color_changed(self, color):
        logger.debug(f'Canvas colour changed to: {color}')
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(color)))

    def on_action_show_layers(self, checked):
        """Open the layers panel, or put it away behind its handle."""

        self.layers_dock.set_collapsed(not checked)
        if checked:
            self.layers_dock.tree.refresh()

    def toggle_layers_panel(self):
        """Open or put away the panel, from wherever it was asked for.

        Everything goes through the menu entry: ticking it runs the
        callback and stores the setting, so the panel, the menu and what
        is remembered for next time cannot drift apart.
        """

        qaction = actions.actions['show_layers'].qaction
        qaction.setChecked(not qaction.isChecked())

    def update_layers_handle(self):
        """Show the handle only while the panel itself is away."""

        dock = getattr(self, 'layers_dock', None)
        if dock is None:
            # The panel settles its own state while it is being built,
            # before the view has a name for it. The view puts the
            # handle right as soon as it does.
            return
        if dock.collapsed:
            self.layers_handle.set_side(
                self.parent.dockWidgetArea(dock))
            self.layers_handle.reposition()
            self.layers_handle.show()
            self.layers_handle.raise_()
        else:
            self.layers_handle.hide()

    def on_action_show_legend(self, checked):
        """Open the legend, or put it away behind its handle."""

        self.legend_dock.set_collapsed(not checked)

    def toggle_legend_panel(self):
        """Open or put away the legend, from wherever it was asked for."""

        qaction = actions.actions['show_legend'].qaction
        qaction.setChecked(not qaction.isChecked())

    def update_legend_handle(self):
        """Show the handle only while the panel itself is away."""

        dock = getattr(self, 'legend_dock', None)
        if dock is None:
            return
        if dock.collapsed:
            self.legend_handle.set_side(self.parent.dockWidgetArea(dock))
            self.legend_handle.reposition()
            self.legend_handle.show()
            self.legend_handle.raise_()
        else:
            self.legend_handle.hide()

    def refresh_legend(self):
        """Follow the board's legend, however it came to change."""

        dock = getattr(self, 'legend_dock', None)
        if dock is not None:
            dock.panel.refresh()

    def set_draw_tool(self, kind):
        """Pick a drawing tool, or ``None`` to go back to selecting."""

        logger.debug(f'Drawing tool: {kind}')
        self.draw_tool = kind
        if kind is None:
            self.viewport().unsetCursor()
        else:
            self.cancel_active_modes()
            self.scene.deselect_all_items()
            self.viewport().setCursor(self.tool_cursor())
        if hasattr(self, 'draw_toolbar'):
            self.draw_toolbar.update_checked(kind)

    def on_action_text_tool(self):
        """Switch to writing notes: T, then click where one goes."""

        self.set_draw_tool(constants.TEXT_TOOL)

    def write_note_at(self, point):
        """Write where the text tool was clicked.

        A note already there is opened for writing, wherever it lives:
        that is the point of the tool, reaching a note inside a group
        without opening the group or double-clicking anything. Only
        where there is no note does it make one, and a note made on a
        group goes inside it.

        Either way the tool then steps aside: what follows is typing,
        and a T over the words being written would only be in the way.
        """

        scene_pos = self.mapToScene(point)
        titled = self.title_band_at(point)
        if titled is not None and not getattr(titled, 'locked', False):
            # A title is text too, and clicking one with the tool should
            # open it rather than lay a note over it
            self.set_draw_tool(None)
            titled.setSelected(True)
            titled.enter_title_edit_mode()
            self.update_group_toolbar()
            self.update_text_toolbar()
            return

        caption = self.image_caption_at(point)
        if caption is not None:
            # A picture's caption is text too, and clicking it with the
            # tool should open it rather than lay a note over it
            self.set_draw_tool(None)
            caption.setSelected(True)
            caption.enter_caption_edit_mode()
            self.update_image_toolbar()
            return

        existing = self.get_text_item_at(point)
        if existing is not None:
            group = self.scene.get_group_ancestor(existing)
            if group is None or not group.locked:
                self.edit_note(existing, scene_pos, group)
                return
            # A locked group keeps its contents to itself, so this
            # falls through and writes a new note on the board

        item = BeeTextItem()
        item.setScale(1 / self.get_scale())
        group = self.group_to_write_in(point, scene_pos)
        self.undo_stack.beginMacro('Write note')
        self.undo_stack.push(
            commands.InsertItems(self.scene, [item], scene_pos))
        if group is not None and not group.locked:
            self.undo_stack.push(
                commands.MoveToGroup(self.scene, [item], group))
        self.undo_stack.endMacro()

        self.set_draw_tool(None)
        item.enter_edit_mode()
        cursor = item.textCursor()
        cursor.select(QtGui.QTextCursor.SelectionType.Document)
        item.setTextCursor(cursor)

    def title_band_at(self, point):
        """An item whose title band lies under the given viewport point.

        Groups and notes both have one, and the band belongs to
        whichever of them is drawn on top.
        """

        scene_pos = self.mapToScene(point)
        for item in self.scene.items(scene_pos):
            if not hasattr(item, 'shows_header') or not item.shows_header():
                continue
            if item.header_rect().contains(item.mapFromScene(scene_pos)):
                return item
        return None

    def image_caption_at(self, point):
        """A picture whose caption band lies under the given point."""

        scene_pos = self.mapToScene(point)
        for item in self.scene.items(scene_pos):
            if getattr(item, 'TYPE', None) != BeePixmapItem.TYPE:
                continue
            if not item.shows_caption():
                continue
            if item.caption_rect().contains(item.mapFromScene(scene_pos)):
                return item
        return None

    def group_to_write_in(self, point, scene_pos):
        """The group a new note clicked here should go into, if any."""

        item_at = self.scene.itemAt(scene_pos, self.transform())
        if getattr(item_at, 'TYPE', None) == BeeGroupItem.TYPE:
            return item_at
        under = self.get_item_at(point)
        if under is not None:
            return self.scene.get_group_ancestor(under)
        return None

    def edit_note(self, item, scene_pos, group):
        """Open a note that is already there, at the word clicked on."""

        if group is not None:
            # Its contents have to be reachable before one can be edited
            self.scene.enter_group(group, item)
        self.set_draw_tool(None)
        item.setSelected(True)
        item.enter_edit_mode()
        item.put_cursor_at(item.mapFromScene(scene_pos))

    def start_drawing(self, pos):
        """Begin a new drawing at the given scene position."""

        self.drawing_points = [pos]
        # draw_width is how thick the line should look on screen, so the
        # width the item is given has to allow for the zoom: at 25% a
        # four unit line is one pixel of hairline, and at 400% it is a
        # slab. The stroke then scales with the scene like everything
        # else, keeping its size relative to what it was drawn over.
        self.drawing_item = BeeDrawItem(
            points=[[pos.x(), pos.y()]],
            kind=self.draw_tool,
            color=self.draw_color.getRgb(),
            width=self.draw_width / self.get_scale())
        self.scene.addItem(self.drawing_item)
        self.drawing_item.bring_to_front()

    def continue_drawing(self, pos, proportional=False):
        if self.draw_tool in BeeDrawItem.SHAPES:
            # A shape is the box between where the drag began and where
            # it is now; the wandering in between is not part of it
            start = self.drawing_points[0]
            if proportional:
                pos = self.square_corner(start, pos)
            self.drawing_points = [start, pos]
        else:
            self.drawing_points.append(pos)
        self.drawing_item.set_points(
            [[p.x(), p.y()] for p in self.drawing_points])
        if self.draw_tool in BeeDrawItem.FASTENING:
            # Only what can fasten promises to; a shape has no ends and
            # a sketch is not aimed at anything
            self.show_snap_preview(pos)

    @staticmethod
    def square_corner(start, pos):
        """The corner that makes the drag box square.

        Shapes fill the box they are dragged in, which is what lets one
        be drawn as an oval or an oblong. Holding Shift squares the box
        instead, so a circle comes out round and a hexagon regular.

        The side is the longer of the two the drag covered, so the shape
        reaches as far as the hand went rather than stopping short.
        """

        across = pos.x() - start.x()
        down = pos.y() - start.y()
        side = max(abs(across), abs(down))
        return QtCore.QPointF(
            start.x() + math.copysign(side, across or 1),
            start.y() + math.copysign(side, down or 1))

    def show_snap_preview(self, pos):
        """Mark the spot this end would catch on, if it would catch.

        Drawn while a line is being drawn or an end dragged, so it is
        clear that letting go here fastens it -- and to what.
        """

        target = self.snap_target_at(pos)
        self.show_marker(
            None if target is None else self.nearest_edge_point(target, pos))

    def show_marker(self, point):
        """Put the round mark at a point on the board, or take it away."""

        if point != self.snap_preview:
            self.snap_preview = point
            self.viewport().update()

    def snap_end(self, item, which, scene_pos):
        """Fasten one end of an existing drawing, if it landed on something."""

        if not item.fastens():
            return
        target = self.snap_target_at(scene_pos)
        if target is None or target is item:
            return
        item.attach_end(which, target)
        self.scene.uses_attachments = True
        item.follow_attachments()

    def finish_drawing(self):
        """Turn the drawing into a real item, or drop it if it's a dot."""

        item = self.drawing_item
        points = self.drawing_points
        self.drawing_item = None
        self.drawing_points = []
        self.snap_preview = None
        self.viewport().update()
        self.scene.removeItem(item)

        if len(points) < 2:
            logger.debug('Drawing too short, dropping it')
            return

        # Points are kept relative to the item, so it can be moved,
        # scaled and rotated like anything else
        origin = QtCore.QPointF(
            min(p.x() for p in points), min(p.y() for p in points))
        item.set_points([[p.x() - origin.x(), p.y() - origin.y()]
                         for p in points])
        item.setPos(origin)
        if item.fastens():
            self.snap_ends(item, points[0], points[-1])

        host = self.image_drawn_on(item)
        if host is None:
            self.undo_stack.push(commands.InsertItems(self.scene, [item]))
            return
        # One step to undo, not two: drawing on a picture is one act
        self.undo_stack.beginMacro('Sketch on image')
        self.undo_stack.push(commands.InsertItems(self.scene, [item]))
        self.undo_stack.push(commands.DrawOnItem(self.scene, item, host))
        self.undo_stack.endMacro()

    def image_drawn_on(self, item):
        """The picture a sketch was drawn inside, if it was drawn in one.

        Sketches only. A line is aimed from one thing to another and
        fastens its ends instead, and a shape is a shape wherever it is
        put. Decided by where the middle of the sketch fell, which is
        the same rule that decides which group something is dropped
        into.
        """

        if item.kind != BeeDrawItem.SKETCH:
            return None
        center = item.mapToScene(item.center)
        for candidate in self.scene.items(center):
            if getattr(candidate, 'TYPE', None) == BeePixmapItem.TYPE:
                return candidate
        return None

    def snap_ends(self, item, start, end):
        """Fasten either end of a new drawing to whatever it landed on.

        Notes, groups and images can all be held on to: they are the
        things a line is drawn between. The end is pulled to the
        nearest point on the item's edge, so it meets the box rather
        than stopping short of it or burying itself inside.
        """

        for which, scene_pos in (('start', start), ('end', end)):
            target = self.snap_target_at(scene_pos)
            if target is None:
                continue
            item.attach_end(which, target)
            self.scene.uses_attachments = True
        item.follow_attachments()

    # What a line can take hold of: the things a line is drawn between.
    # Not other drawings -- a line held by a line has nothing to meet
    # the edge of, and joining two of them says nothing.
    SNAP_TYPES = ('text', 'group', 'pixmap')

    def snap_target_at(self, scene_pos):
        """The item near enough to this point to catch an end."""

        best = None
        best_distance = None
        for target in self.scene.items():
            if getattr(target, 'TYPE', None) not in self.SNAP_TYPES:
                continue
            rect = target.attach_rect()
            distance = 0 if rect.contains(scene_pos) else min(
                abs(scene_pos.x() - rect.left()),
                abs(scene_pos.x() - rect.right()),
                abs(scene_pos.y() - rect.top()),
                abs(scene_pos.y() - rect.bottom()))
            if not rect.adjusted(
                    -BeeDrawItem.SNAP_DISTANCE, -BeeDrawItem.SNAP_DISTANCE,
                    BeeDrawItem.SNAP_DISTANCE,
                    BeeDrawItem.SNAP_DISTANCE).contains(scene_pos):
                continue
            if best_distance is None or distance < best_distance:
                best, best_distance = target, distance
        return best

    @staticmethod
    def nearest_edge_point(target, scene_pos):
        """The closest point on the item's edge, in scene coordinates."""

        rect = target.attach_rect()
        x = min(max(scene_pos.x(), rect.left()), rect.right())
        y = min(max(scene_pos.y(), rect.top()), rect.bottom())
        # Push out to whichever side is nearest, so it sits on the edge
        # rather than floating inside the box
        gaps = ((x - rect.left(), QtCore.QPointF(rect.left(), y)),
                (rect.right() - x, QtCore.QPointF(rect.right(), y)),
                (y - rect.top(), QtCore.QPointF(x, rect.top())),
                (rect.bottom() - y, QtCore.QPointF(x, rect.bottom())))
        return min(gaps, key=lambda gap: gap[0])[1]

    def on_action_draw_color(self):
        """Set the colour for new drawings, and for any selected ones."""

        items = self.scene.selected_draw_items()
        originals = [item.color for item in items]

        def preview(color):
            for item in items:
                item.color = color
                item.update()

        color = self.pick_color_live(
            'Choose Drawing Colour', self.draw_color, preview)

        # Back to the colours they had, so the undo command records what
        # was there before rather than the last thing previewed
        for item, original in zip(items, originals):
            item.color = original
            item.update()
        if color is None:
            return
        self.draw_color = color
        if items:
            self.undo_stack.push(commands.ChangeDrawColor(items, color))

    def on_action_show_grid(self, checked):
        self.show_grid = checked
        self.viewport().update()

    def on_grid_changed(self):
        self.viewport().update()

    # How wide a dot of the dotted grid is drawn, in screen pixels
    GRID_DOT_SIZE = 4

    # How big the mark showing where a line would fasten is drawn, on
    # screen rather than on the board, so it stays the same at any zoom.
    SNAP_MARKER_SIZE = 7

    def drawForeground(self, painter, rect):
        """The dot showing where a line being drawn would fasten."""

        super().drawForeground(painter, rect)
        if self.snap_preview is None:
            return
        radius = self.SNAP_MARKER_SIZE / self.get_scale()
        color = QtGui.QColor(*constants.COLORS['Scene:Selection'])
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(color)
        pen.setWidthF(radius / 3)
        painter.setPen(pen)
        painter.setBrush(QtGui.QBrush(QtGui.QColor(
            color.red(), color.green(), color.blue(), 110)))
        painter.drawEllipse(self.snap_preview, radius, radius)

    def drawBackground(self, painter, rect):
        """Draws the canvas background, and the grid on top of it.

        The grid lives on the view rather than the scene so that it
        never ends up in exported images, which render the scene.
        """

        super().drawBackground(painter, rect)
        if not self.show_grid:
            return

        fine, coarse, fade = self.grid_levels()
        dots = self.settings.valueOrDefault('View/grid_style') == 'dots'
        # The finer level first and faded, the coarser one over it at
        # full strength. Every second line of the fine grid is a coarse
        # line, so what this actually does is bring the lines in
        # between in and out.
        if fade > 0.02:
            self.draw_grid(painter, rect, fine, fade, dots)
        self.draw_grid(painter, rect, coarse, 1, dots)

    def grid_levels(self):
        """The two spacings to draw, and how far the finer one is in.

        A grid tied to the board has to change spacing somewhere, or it
        turns into a wall zoomed out and vanishes zoomed in. What was
        being noticed was not the change itself but its suddenness: a
        whole set of lines arriving between one turn of the wheel and
        the next.

        So two are drawn at once, an octave apart, and the finer of
        them fades in as it is approached and out again as it gets too
        close. Every second line of the finer grid is a line of the
        coarser one, so nothing ever moves: lines only come in and go
        out between the ones that stay.
        """

        zoom = self.get_scale()
        base = self.settings.valueOrDefault('View/grid_size')
        if zoom <= 0 or base <= 0:
            return base, base * 2, 0

        # What the grid looks like at the board's own size is what the
        # settings ask for, reined in so it is never a mess or a pair
        # of lines
        on_screen = min(self.GRID_MAX_SPACING,
                        max(self.GRID_MIN_SPACING, base))
        octaves = math.log2(on_screen / zoom / base)
        whole = math.floor(octaves)
        fine = base * 2 ** whole
        return fine, fine * 2, 1 - (octaves - whole)

    def draw_grid(self, painter, rect, step, fade, dots):
        """One level of the grid, at the given strength."""

        color = QtGui.QColor(
            self.settings.valueOrDefault('View/grid_color'))
        color.setAlphaF(color.alphaF() * fade)
        pen = QtGui.QPen(color)
        # Keep lines one pixel wide whatever the zoom level
        pen.setCosmetic(True)

        across = self.grid_positions(rect.left(), rect.right(), step)
        down = self.grid_positions(rect.top(), rect.bottom(), step)
        if dots:
            self.draw_grid_dots(painter, pen, across, down)
            return

        self.draw_grid_lines(painter, pen, across, down)

    def draw_grid_lines(self, painter, pen, across, down):
        """The ruled grid, drawn on the screen rather than on the board.

        In device coordinates, like the dots, and for the same two
        reasons. A line landing on a fractional pixel is spread over
        its neighbours, so a one-pixel line came out two pixels of
        half-strength at some zooms; and drawing through the board's
        transform with a cosmetic pen was, on a real board, most of
        what a zoom frame cost -- more than every picture on it put
        together. Antialiasing goes off with it: these are upright and
        across and a pixel wide, so it has nothing to smooth.
        """

        view = self.viewport().rect()
        columns = sorted({round(self.mapFromScene(QtCore.QPointF(x, 0)).x())
                          for x in across})
        rows = sorted({round(self.mapFromScene(QtCore.QPointF(0, y)).y())
                       for y in down})

        painter.save()
        painter.setTransform(QtGui.QTransform())
        painter.setRenderHint(painter.RenderHint.Antialiasing, False)
        # Filled rectangles a pixel wide rather than drawn lines. On
        # whole pixels the two come out identical, and the line
        # rasteriser is the slower of the two by half again -- which on
        # a board being zoomed is worth more than it sounds, since a
        # single turn of the wheel is eased out over a dozen frames.
        brush = QtGui.QBrush(pen.color())
        height = view.height()
        width = view.width()
        for x in columns:
            painter.fillRect(QtCore.QRect(x, 0, 1, height), brush)
        for y in rows:
            painter.fillRect(QtCore.QRect(0, y, width, 1), brush)
        painter.restore()

    def draw_grid_dots(self, painter, pen, across, down):
        """A dot where the lines would have crossed.

        Drawn on whole screen pixels rather than at the point of the
        board the dot belongs to. Those points land wherever the zoom
        puts them, and a round dot on a fractional pixel is spread over
        its neighbours: the same dot measured two pixels across at one
        zoom and five at another, which is the difference that gets
        noticed.

        Wider than the lines because it has to be. The grid colour is
        chosen to be barely there, and a dot the width of a line is one
        pixel of it: against the ruled grid on the same screen that
        came to twelve pixels of ink where the lines came to five
        thousand.
        """

        pen.setWidth(self.GRID_DOT_SIZE)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        painter.save()
        painter.setTransform(QtGui.QTransform())
        painter.setPen(pen)
        painter.drawPoints([
            QtCore.QPointF(round(point.x()), round(point.y()))
            for point in (self.mapFromScene(QtCore.QPointF(x, y))
                          for x in across for y in down)])
        painter.restore()

    @staticmethod
    def grid_positions(start, end, step):
        """Where the grid falls between the two, in scene coordinates."""

        positions = []
        at = start - (start % step)
        while at < end:
            positions.append(at)
            at += step
        return positions

    def on_scene_changed(self, region):
        # Anything that moves or resizes an item lands here, which is
        # what keeps the bars stuck to what they act on
        self.update_pinned_toolbars()
        if not self.scene.items():
            logger.debug('No items in scene')
            self.setTransform(QtGui.QTransform())
            self.welcome_overlay.setFocus()
            self.clearFocus()
            self.welcome_overlay.show()
            self.actiongroup_set_enabled('active_when_items_in_scene', False)
        else:
            self.setFocus()
            self.welcome_overlay.clearFocus()
            self.welcome_overlay.hide()
            self.actiongroup_set_enabled('active_when_items_in_scene', True)
        self.recalc_scene_rect()

    def on_can_redo_changed(self, can_redo):
        self.actiongroup_set_enabled('active_when_can_redo', can_redo)

    def on_can_undo_changed(self, can_undo):
        self.actiongroup_set_enabled('active_when_can_undo', can_undo)

    def on_undo_clean_changed(self, clean):
        self.update_window_title()

    def get_text_item_at(self, point):
        """The topmost text item at the given view position, if any."""

        for item in self.scene.items(self.mapToScene(point)):
            # Not every item in the scene is a user item (e.g. the
            # multi-select rectangle), so TYPE may be missing
            if getattr(item, 'TYPE', None) == 'text':
                return item

    def get_item_at(self, point):
        """The topmost item at the given view position, if any.

        Groups themselves are skipped, so this finds what is inside
        them rather than the group.
        """

        for item in self.scene.items(self.mapToScene(point)):
            if not hasattr(item, 'save_id'):
                continue
            if getattr(item, 'TYPE', None) == BeeGroupItem.TYPE:
                continue
            return item

    def get_group_at(self, point):
        """The group at the given view position, if any.

        Items inside a group count as the group itself, unless the group
        has been opened up for editing.
        """

        for item in self.scene.items(self.mapToScene(point)):
            group = self.scene.get_group_ancestor(item)
            if group is not None and group is not self.scene.active_group:
                return group
            if getattr(item, 'TYPE', None) == BeeGroupItem.TYPE:
                return item
        return None

    def on_context_menu(self, point):
        # Text items offer the text options, even inside a group, so
        # that their colours stay reachable
        item = self.get_text_item_at(point)
        group = self.scene.get_group_ancestor(item) if item else None
        if item is not None and not (group is not None and group.locked):
            if group is not None:
                # The item has to be reachable for the options to apply
                self.scene.enter_group(group, item)
            elif not item.isSelected():
                self.scene.deselect_all_items()
                item.setSelected(True)
            # Work the table commands from the cell that was clicked
            item.put_cursor_at(item.mapFromScene(self.mapToScene(point)))
            self.update_table_actions()
            self.text_context_menu.exec(self.mapToGlobal(point))
            return

        # Images offer their own options the same way, so that cropping
        # and the stacking order are a click away rather than buried in
        # the long menu
        item = self.get_item_at(point)
        group = self.scene.get_group_ancestor(item) if item else None
        if (item is not None
                and getattr(item, 'TYPE', None) == BeePixmapItem.TYPE
                and not (group is not None and group.locked)):
            if group is not None:
                self.scene.enter_group(group, item)
            elif not item.isSelected():
                self.scene.deselect_all_items()
                item.setSelected(True)
            self.image_context_menu.exec(self.mapToGlobal(point))
            return

        # Anything else inside a group offers its own actions, with the
        # group opened up so they apply. The full menu still holds the
        # group's own actions.
        if item is not None and group is not None and not group.locked:
            self.scene.enter_group(group, item)
            self.context_menu.exec(self.mapToGlobal(point))
            return

        group = self.get_group_at(point)
        if group is not None:
            if not group.isSelected():
                self.scene.deselect_all_items()
                group.setSelected(True)
            actions.actions['lock_group'].qaction.setChecked(group.locked)
            self.group_context_menu.exec(self.mapToGlobal(point))
            return

        self.context_menu.exec(self.mapToGlobal(point))

    def get_supported_image_formats(self, cls):
        formats = []

        for f in cls.supportedImageFormats():
            string = f'*.{f.data().decode()}'
            formats.extend((string, string.upper()))
        return ' '.join(formats)

    def get_view_center(self):
        return QtCore.QPoint(round(self.size().width() / 2),
                             round(self.size().height() / 2))

    def clear_scene(self):
        logging.debug('Clearing scene...')
        self.cancel_active_modes()
        self.scene.clear()
        self.undo_stack.clear()
        self.filename = None
        self.setTransform(QtGui.QTransform())

    def reset_previous_transform(self, toggle_item=None):
        if (self.previous_transform
                and self.previous_transform['toggle_item'] != toggle_item):
            self.previous_transform = None

    def fit_rect(self, rect, toggle_item=None):
        if toggle_item and self.previous_transform:
            logger.debug('Fit view: Reset to previous')
            self.setTransform(self.previous_transform['transform'])
            self.centerOn(self.previous_transform['center'])
            self.previous_transform = None
            return
        if toggle_item:
            self.previous_transform = {
                'toggle_item': toggle_item,
                'transform': QtGui.QTransform(self.transform()),
                'center': self.mapToScene(self.get_view_center()),
            }
        else:
            self.previous_transform = None

        logger.debug(f'Fit view: {rect}')
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.recalc_scene_rect()
        # It seems to be more reliable when we fit a second time
        # Sometimes a changing scene rect can mess up the fitting
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        logger.trace('Fit view done')

    def get_confirmation_unsaved_changes(self, msg):
        """Ask what to do with changes that are not on disk yet.

        The board is about to be thrown away, so the chance to keep it
        is offered here rather than left to be remembered: saving is
        the third answer, not something to go and do first.
        """

        confirm = self.settings.valueOrDefault('Save/confirm_close_unsaved')
        if not confirm or self.undo_stack.isClean():
            return True

        button = QtWidgets.QMessageBox.StandardButton
        answer = QtWidgets.QMessageBox.question(
            self,
            'Save your changes?',
            msg,
            button.Save | button.Discard | button.Cancel,
            button.Save)
        if answer == button.Save:
            return self.save_and_wait()
        return answer == button.Discard

    def save_and_wait(self):
        """Save the board and say whether it is safely on disk.

        Saving runs in a thread of its own behind a progress bar, and
        what asked for it is about to close the board, so it has to
        wait for the answer instead of taking the save on trust.
        """

        started_with = getattr(self, 'worker', None)
        self.on_action_save()
        worker = getattr(self, 'worker', None)
        if worker is None or worker is started_with:
            # Save As was needed and the file dialog was dismissed
            return False

        waiting = QtCore.QEventLoop()
        worker.finished.connect(waiting.quit)
        if worker.isRunning():
            waiting.exec()
        # Saving marks the undo stack clean; a failed save does not
        return self.undo_stack.isClean()

    def on_action_new_scene(self):
        confirm = self.get_confirmation_unsaved_changes(
            'This board has changes that are not saved. '
            'Save them before opening another board?')
        if confirm:
            self.clear_scene()

    def on_action_fit_scene(self):
        self.fit_rect(self.scene.itemsBoundingRect())

    def on_action_fit_selection(self):
        self.fit_rect(self.scene.itemsBoundingRect(selection_only=True))

    def on_action_fullscreen(self, checked):
        if checked:
            self.parent.showFullScreen()
        else:
            self.parent.showNormal()

    def on_action_always_on_top(self, checked):
        self.parent.setWindowFlag(
            Qt.WindowType.WindowStaysOnTopHint, on=checked)
        self.parent.destroy()
        self.parent.create()
        self.parent.show()

    def on_action_show_scrollbars(self, checked):
        if checked:
            self.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def on_action_show_menubar(self, checked):
        if checked:
            self.parent.setMenuBar(self.create_menubar())
        else:
            self.parent.setMenuBar(None)

    def on_action_show_titlebar(self, checked):
        self.parent.setWindowFlag(
            Qt.WindowType.FramelessWindowHint, on=not checked)
        self.parent.destroy()
        self.parent.create()
        self.parent.show()

    def on_action_move_window(self):
        if self.welcome_overlay.isHidden():
            self.on_action_movewin_mode()
        else:
            self.welcome_overlay.on_action_movewin_mode()

    def on_action_undo(self):
        logger.debug('Undo: %s' % self.undo_stack.undoText())
        self.cancel_active_modes()
        self.undo_stack.undo()

    def on_action_redo(self):
        logger.debug('Redo: %s' % self.undo_stack.redoText())
        self.cancel_active_modes()
        self.undo_stack.redo()

    def on_action_select_all(self):
        self.scene.select_all_items()

    def on_action_deselect_all(self):
        self.scene.deselect_all_items()

    def on_action_delete_items(self):
        logger.debug('Deleting items...')
        self.cancel_active_modes()
        self.undo_stack.push(
            commands.DeleteItems(
                self.scene, self.scene.selectedItems(user_only=True)))

    def on_action_cut(self):
        logger.debug('Cutting items...')
        self.on_action_copy()
        self.undo_stack.push(
            commands.DeleteItems(
                self.scene, self.scene.selectedItems(user_only=True)))

    def on_action_raise_to_top(self):
        self.scene.raise_to_top()

    def on_action_lower_to_bottom(self):
        self.scene.lower_to_bottom()

    def on_action_normalize_height(self):
        self.scene.normalize_height()

    def on_action_normalize_width(self):
        self.scene.normalize_width()

    def on_action_normalize_size(self):
        self.scene.normalize_size()

    def on_action_arrange_horizontal(self):
        self.scene.arrange()

    def on_action_arrange_vertical(self):
        self.scene.arrange(vertical=True)

    def on_action_arrange_optimal(self):
        self.scene.arrange_optimal()

    def on_action_arrange_square(self):
        self.scene.arrange_square()

    def on_action_change_opacity(self):
        images = list(filter(
            lambda item: item.is_image,
            self.scene.selectedItems(user_only=True)))
        widgets.ChangeOpacityDialog(self, images, self.undo_stack)

    def on_action_grayscale(self, checked):
        images = list(filter(
            lambda item: item.is_image,
            self.scene.selectedItems(user_only=True)))
        if images:
            self.undo_stack.push(
                commands.ToggleGrayscale(images, checked))

    def on_action_group_items(self):
        items = self.scene.selectedItems(user_only=True)
        if not items:
            return
        logger.debug(f'Grouping {len(items)} items')
        self.undo_stack.push(
            commands.GroupItems(self.scene, items, BeeGroupItem()))

    def on_action_ungroup_items(self):
        groups = [item for item in self.scene.selectedItems(user_only=True)
                  if item.TYPE == BeeGroupItem.TYPE]
        if not groups:
            widgets.BeeNotification(self, 'No group selected')
            return
        logger.debug(f'Ungrouping {len(groups)} groups')
        self.undo_stack.push(commands.UngroupItems(self.scene, groups))

    def on_action_lock_group(self, checked):
        groups = [item for item in self.scene.selectedItems(user_only=True)
                  if item.TYPE == BeeGroupItem.TYPE]
        for group in groups:
            logger.debug(f'Setting locked for {group} to {checked}')
            group.locked = checked
            group.touch()
            if checked and self.scene.active_group is group:
                self.scene.exit_group()

    # Space left between the picker and what it is recolouring
    DIALOG_GAP = 16

    def move_dialog_beside_selection(self, dialog):
        """Put a dialog next to the selection instead of over it.

        Previewing a colour is pointless if the picker is covering the
        thing being coloured, and dialogs open centred on their parent,
        which is exactly where the selection usually is. Prefers the
        right of the selection, falls back to its left, and stays on the
        screen either way.
        """

        items = self.scene.selectedItems(user_only=True)
        if not items:
            return
        dialog.adjustSize()
        size = dialog.sizeHint()

        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        on_view = self.mapFromScene(rect).boundingRect()
        topleft = self.viewport().mapToGlobal(on_view.topLeft())
        topright = self.viewport().mapToGlobal(on_view.topRight())

        screen = self.screen().availableGeometry()
        x = topright.x() + self.DIALOG_GAP
        if x + size.width() > screen.right():
            x = topleft.x() - self.DIALOG_GAP - size.width()
        x = max(screen.left(), min(x, screen.right() - size.width()))
        y = max(screen.top(),
                min(topleft.y(), screen.bottom() - size.height()))
        dialog.move(x, y)

    @staticmethod
    def apply_palette_to_color_dialogs():
        """Put our palette in the colour picker's swatches.

        The grid holds 48, and the palette leads with black -- which is
        also the first of the greys offered under the grid, so it would
        be there twice. Skipping it leaves room for one more colour
        rather than a gap.

        The setters are static, so this reaches every colour dialog the
        application opens, including the ones in the settings.
        """

        colors = [color for color in BeeAssets().palette
                  if color != QtGui.QColor(0, 0, 0)]
        for i, color in enumerate(colors[:48]):
            QtWidgets.QColorDialog.setStandardColor(i, color)

    def pick_color_live(self, title, initial, preview, alpha=True):
        """Ask for a colour, showing each choice on the board as it is made.

        ``QColorDialog.getColor()`` reports nothing until OK is pressed,
        so a colour can only be judged against the dialog's own swatch
        rather than against the board it will sit on. Driving the dialog
        directly gives ``currentColorChanged``, which fires on every
        change.

        Returns the chosen colour, or None if the dialog was cancelled.
        The preview writes straight to the items and deliberately does
        not touch the undo stack, so the caller has to put the original
        colours back afterwards -- see the callers below for why that
        matters even when the dialog was accepted.
        """

        dialog = QtWidgets.QColorDialog(initial, self)
        dialog.setWindowTitle(title)
        if alpha:
            dialog.setOption(
                QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel)
        dialog.currentColorChanged.connect(preview)
        widgets.color_dialog.simplify_color_dialog(
            dialog, self.scene.legend)
        # After simplifying, so the dialog is placed at the size it
        # ends up being rather than the size Qt built it at
        self.move_dialog_beside_selection(dialog)
        accepted = dialog.exec()
        color = dialog.currentColor()
        if accepted and color.isValid():
            return color
        return None

    def on_action_group_title(self):
        """Write the title on the group itself."""

        groups = self.scene.selected_groups()
        if not groups:
            widgets.BeeNotification(self, 'No group selected')
            return
        self.set_draw_tool(None)
        groups[0].enter_title_edit_mode()
        self.update_group_toolbar()

    def reveal(self, rect):
        """Scroll until the given part of the board is in sight.

        A band that has just been opened for writing can be off the
        edge of the window: it is added above a group or below a
        picture, and on a big one it is thousands of units of it, so it
        opens somewhere nothing can be seen of it and the writing goes
        on blind.
        """

        self.ensureVisible(rect, self.REVEAL_MARGIN, self.REVEAL_MARGIN)

    def item_being_titled(self, kind=None):
        """The item whose title is being written, if one is.

        A kind narrows it to groups or to notes, so that the colour
        button on one bar cannot act on what the other bar is writing.
        """

        item = self.scene.title_item
        if item is None:
            return None
        if kind is not None and getattr(item, 'TYPE', None) != kind:
            return None
        return item

    def group_being_titled(self):
        """The group whose title is being written, if one is."""

        return self.item_being_titled(BeeGroupItem.TYPE)

    def titled_items(self, kind, selected):
        """What a title command acts on, and whether there is anything.

        While a title is being written it is that one item, whatever
        else happens to be selected.
        """

        writing = self.item_being_titled(kind)
        return [writing] if writing is not None else selected

    def pick_title_color(self, items):
        """Ask for a colour for the title band, showing it as it is picked.

        The band is only visible once there are words in it, so this is
        offered where the words are: the same button that colours an
        item colours its title while the title is being written.
        """

        originals = [item.header_color for item in items]

        def preview(color):
            for item in items:
                item.header_color = color
                item.refresh_title_editor()
                item.update()

        color = self.pick_color_live(
            'Choose Title Colour',
            items[0].header_color or items[0].default_header_color(),
            preview)

        for item, original in zip(items, originals):
            item.header_color = original
            item.refresh_title_editor()
            item.update()
        if color is None:
            return
        self.undo_stack.push(commands.ChangeTitle(
            items, items[0].title, color, items[0].title_align))
        for item in items:
            item.refresh_title_editor()

    def set_title_align(self, kind, items, align):
        """Put the title of the given items left or centred."""

        if self.item_being_titled(kind) is not None:
            # Mid-writing there is nothing to record yet; the title is
            # still in the editor and goes on the stack when it is done
            for item in items:
                item.title_align = align
                item.refresh_title_editor()
                item.update()
        else:
            self.undo_stack.push(commands.ChangeTitle(
                items, items[0].title, items[0].header_color, align))

    def on_action_group_title_color(self):
        groups = self.titled_items(
            BeeGroupItem.TYPE, self.scene.selected_groups())
        if not groups:
            widgets.BeeNotification(self, 'No group selected')
            return
        self.pick_title_color(groups)

    def set_group_title_align(self, align):
        """Put the title of the selected groups left or centred."""

        groups = self.titled_items(
            BeeGroupItem.TYPE, self.scene.selected_groups())
        if not groups:
            widgets.BeeNotification(self, 'No group selected')
            return
        self.set_title_align(BeeGroupItem.TYPE, groups, align)
        self.update_group_toolbar()

    def on_action_group_title_align_left(self):
        self.set_group_title_align(BeeGroupItem.TITLE_LEFT)

    def on_action_group_title_align_center(self):
        self.set_group_title_align(BeeGroupItem.TITLE_CENTER)

    def on_action_text_title(self):
        """Write the title on the note itself."""

        items = self.scene.selected_text_items()
        if not items:
            widgets.BeeNotification(self, 'No text selected')
            return
        self.set_draw_tool(None)
        items[0].enter_title_edit_mode()
        self.update_text_toolbar()

    def on_action_text_title_color(self):
        items = self.titled_items(
            BeeTextItem.TYPE, self.scene.selected_text_items())
        if not items:
            widgets.BeeNotification(self, 'No text selected')
            return
        self.pick_title_color(items)

    def set_text_title_align(self, align):
        """Put the title of the selected notes left or centred."""

        items = self.titled_items(
            BeeTextItem.TYPE, self.scene.selected_text_items())
        if not items:
            widgets.BeeNotification(self, 'No text selected')
            return
        self.set_title_align(BeeTextItem.TYPE, items, align)
        self.update_text_toolbar()

    def on_action_text_title_align_left(self):
        self.set_text_title_align(BeeTextItem.TITLE_LEFT)

    def on_action_text_title_align_center(self):
        self.set_text_title_align(BeeTextItem.TITLE_CENTER)

    def on_action_group_box_color(self):
        groups = [item for item in self.scene.selectedItems(user_only=True)
                  if item.TYPE == BeeGroupItem.TYPE]
        if not groups:
            widgets.BeeNotification(self, 'No group selected')
            return
        originals = [group.box_color for group in groups]

        def preview(color):
            for group in groups:
                group.box_color = color

        color = self.pick_color_live(
            'Choose Group Colour', groups[0].box_color, preview)

        # Put the originals back whichever way the dialog went. Cancelling
        # has to undo the preview; accepting has to as well, because the
        # undo command records the colours it finds at the moment it is
        # built, and those must be the ones from before the preview.
        for group, original in zip(groups, originals):
            group.box_color = original
        if color is not None:
            self.undo_stack.push(
                commands.ChangeGroupBoxColor(groups, color))

    def on_action_image_caption(self):
        """Write the caption on the picture itself."""

        items = self.scene.selected_images()
        if not items:
            widgets.BeeNotification(self, 'No image selected')
            return
        self.set_draw_tool(None)
        items[0].enter_caption_edit_mode()
        self.update_image_toolbar()

    def image_being_captioned(self):
        return self.scene.caption_item

    def on_action_image_caption_color(self):
        """Ask for a colour for the caption band, showing it as picked."""

        item = self.image_being_captioned()
        items = [item] if item is not None else self.scene.selected_images()
        if not items:
            widgets.BeeNotification(self, 'No image selected')
            return
        originals = [each.caption_color for each in items]

        def preview(color):
            for each in items:
                each.caption_color = color
                each.refresh_caption_editor()
                each.update()

        color = self.pick_color_live(
            'Choose Caption Colour', items[0].caption_color, preview)

        for each, original in zip(items, originals):
            each.caption_color = original
            each.refresh_caption_editor()
            each.update()
        if color is None:
            return
        self.undo_stack.push(commands.ChangeCaption(
            items, items[0].caption, color))
        for each in items:
            each.refresh_caption_editor()

    def on_action_image_outline_color(self):
        """Ask for a contour colour, showing it on the board as picked."""

        items = self.scene.selected_images()
        if not items:
            widgets.BeeNotification(self, 'No image selected')
            return
        originals = [item.outline_color for item in items]

        def preview(color):
            for item in items:
                item.outline_color = color
                item.update()

        color = self.pick_color_live(
            'Choose Outline Colour', items[0].outline_color, preview)

        # The originals go back whichever way the dialog went: the undo
        # command records what it finds when it is built, and that has
        # to be the colour from before the preview
        for item, original in zip(items, originals):
            item.outline_color = original
            item.update()
        if color is not None:
            self.undo_stack.push(commands.ChangeOutlineColor(items, color))

    def on_action_find_text(self):
        query, ok = QtWidgets.QInputDialog.getText(
            self, 'Find Text', 'Find:' + chr(10) + 'F3 to cycle through',
            text=self.text_search_query)
        if not ok or not query:
            return
        self.text_search_query = query
        self.text_search_index = -1
        self.find_next_text_match()

    # Room left round something scrolled into sight
    REVEAL_MARGIN = 40

    # How much of the window's width a found word is brought up to.
    # A third filled the window with the word and little else; half
    # that reads as easily and keeps far more of what surrounds it.
    MATCH_SHARE = 0.15

    def on_action_find_next(self):
        if self.text_search_query:
            self.find_next_text_match()
        else:
            self.on_action_find_text()

    def get_text_search_matches(self):
        """Everything carrying the current search query.

        Notes, tables inside them, the titles of groups and the
        captions on pictures: all of it is writing on the board, so all
        of it is looked through. Ordered top to bottom so that cycling
        through them is predictable.
        """

        query = self.text_search_query.lower()
        matches = [item for item in self.scene.items()
                   if hasattr(item, 'search_text')
                   and query in item.search_text().lower()]
        return sorted(
            matches,
            key=lambda item: (item.sceneBoundingRect().top(),
                              item.sceneBoundingRect().left()))

    def find_next_text_match(self):
        """Select the next match and centre the view on it."""

        matches = self.get_text_search_matches()
        if not matches:
            self.text_search_index = -1
            widgets.BeeNotification(
                self, f'No text matching "{self.text_search_query}"')
            return

        self.text_search_index = (self.text_search_index + 1) % len(matches)
        item = matches[self.text_search_index]
        logger.debug(f'Text search match {self.text_search_index}: {item}')
        self.scene.deselect_all_items()
        item.setSelected(True)
        self.zoom_to_match(item)
        widgets.BeeNotification(
            self,
            f'Match {self.text_search_index + 1} of {len(matches)}'
            f' for "{self.text_search_query}" -- F3 to cycle through')

    def zoom_to_match(self, item):
        """Go to the word itself, not merely to the note holding it.

        Centring on the note left a word on a large board still too
        small to read. This brings the word up to a readable size while
        keeping what surrounds it in sight; see MATCH_SHARE.
        """

        word = item.search_rect(self.text_search_query)
        if word is None or word.isEmpty():
            self.centerOn(item.sceneBoundingRect().center())
            return

        view = self.viewport().rect()
        if view.isEmpty():
            return
        width = word.width() / self.MATCH_SHARE
        # Given the viewport's own proportions, so fitting the box puts
        # the word at exactly that share of the width
        height = width * view.height() / view.width()
        box = QtCore.QRectF(0, 0, width, height)
        box.moveCenter(word.center())
        self.fit_rect(box)

    def on_action_text_bold(self):
        """Toggle bold on the selected words, or the whole text."""

        items = self.scene.selected_text_items()
        if not items:
            return
        charformat = QtGui.QTextCharFormat()
        # Toggle based on what the first item currently is, so that a
        # second press turns it off again
        weight = (QtGui.QFont.Weight.Normal if self.text_is_bold(items[0])
                  else QtGui.QFont.Weight.Bold)
        charformat.setFontWeight(weight)
        self.apply_text_char_format(items, charformat)

    def on_action_text_font(self):
        """Switch the selected words between the two fonts.

        The interface font is what text is written in; the bundled
        Ranade is the alternative. Toggling from what the first item
        currently uses means a second press puts it back.
        """

        items = self.scene.selected_text_items()
        if not items:
            return
        interface, bundled = items[0].font_families()
        if not bundled:
            logger.debug('Bundled font not available; nothing to switch to')
            return
        family = interface if items[0].uses_bundled_font() else bundled
        charformat = QtGui.QTextCharFormat()
        charformat.setFontFamilies([family])
        self.apply_text_char_format(items, charformat)

    def text_is_bold(self, item):
        cursor = item.textCursor()
        if not cursor.hasSelection():
            cursor.select(QtGui.QTextCursor.SelectionType.Document)
        return cursor.charFormat().fontWeight() > QtGui.QFont.Weight.Normal

    def scale_selected_text(self, factor):
        """Scale the selected words, or the whole text, by a factor."""

        items = self.scene.selected_text_items()
        if not items:
            return
        old_htmls = [item.toHtml() for item in items]
        for item in items:
            item.scale_font_size(
                factor, self.TEXT_SIZE_MIN, self.TEXT_SIZE_MAX)
        new_htmls = [item.toHtml() for item in items]
        self.undo_stack.push(
            commands.ChangeTextFormat(items, new_htmls, old_htmls))

    def scale_selected_drawings(self, factor):
        """Make the selected sketches, lines and arrows thicker or thinner."""

        items = self.scene.selected_draw_items()
        if not items:
            return
        self.undo_stack.push(commands.ChangeLineWidth(items, factor))

    def scale_selected_outlines(self, factor):
        """Make the contours of the selected images thicker or thinner.

        Images without one are left alone: the size buttons are for
        changing a contour, not for putting one on.
        """

        items = [item for item in self.scene.selected_images()
                 if item.has_outline()]
        widths = [item.outline_width * factor for item in items]
        # Held at the limit, every further press would record a step
        # that changes nothing and then has to be undone one by one
        wanted = [min(item.max_outline_width(),
                      max(item.OUTLINE_MIN_WIDTH, width))
                  for item, width in zip(items, widths)]
        if wanted == [item.outline_width for item in items]:
            return
        self.undo_stack.push(commands.ChangeOutline(items, widths))

    def on_action_size_increase(self):
        """Make whatever is selected bigger: text, line, title or contour."""

        self.scale_by(self.TEXT_SIZE_STEP, self.LINE_WIDTH_STEP)

    def on_action_size_decrease(self):
        self.scale_by(1 / self.TEXT_SIZE_STEP, 1 / self.LINE_WIDTH_STEP)

    def scale_by(self, text_factor, line_factor):
        """Size whatever the buttons are pointing at.

        The words being written win, wherever they are: while a title
        or a caption is open, that is what is on screen and that is
        what a press is asking about. A group has only its title to
        size, so it needs no such rule.
        """

        if self.scale_band_being_written(text_factor):
            return
        self.scale_selected_text(text_factor)
        self.scale_selected_drawings(line_factor)
        self.scale_selected_outlines(line_factor)
        self.scale_selected_titles(text_factor)

    def scale_band_being_written(self, factor):
        """Size the title or caption that is open for writing.

        Not recorded, the way an alignment picked while writing is not:
        the title is still in the editor, and what goes on the stack is
        the whole of it when the writing is done.
        """

        item = self.scene.title_item
        if item is None:
            item = self.scene.caption_item
        if item is None:
            return False
        if getattr(item, 'TYPE', None) == BeeTextItem.TYPE:
            # A note's heading keeps a size of its own rather than a
            # share of the note, so that making the note's own words
            # bigger leaves the heading where it was
            item.set_title_size(item.title_size() * factor)
        else:
            item.grow_band_text(factor)
        return True

    def scale_selected_titles(self, factor):
        """Size the title across the top of the selected groups."""

        groups = self.scene.selected_groups()
        if groups:
            self.undo_stack.push(
                commands.ChangeBandTextScale(groups, factor))

    def on_action_image_outline(self):
        """Put a contour on the selected images, or take it off.

        Off when every one of them already has a contour, so a second
        press undoes what the first did rather than leaving a mixed
        selection flipping one image at a time.
        """

        items = self.scene.selected_images()
        if not items:
            widgets.BeeNotification(self, 'No image selected')
            return
        turn_off = all(item.has_outline() for item in items)
        self.undo_stack.push(commands.ChangeOutline(
            items,
            [0 if turn_off else item.default_outline_width()
             for item in items]))
        self.update_image_toolbar()

    def apply_text_char_format(self, items, charformat):
        """Apply the format to the given items, as one undo step."""

        old_htmls = [item.toHtml() for item in items]
        for item in items:
            item.apply_char_format(charformat)
        new_htmls = [item.toHtml() for item in items]
        self.undo_stack.push(
            commands.ChangeTextFormat(items, new_htmls, old_htmls))

    def update_table_actions(self):
        """Enable the table commands when there is a table to work on.

        Separate from the selection handler because right-clicking a
        cell also decides this: it moves the cursor into the cell, and
        the menu about to open has to reflect that.
        """

        self.actiongroup_set_enabled('active_when_table',
                                     self.scene.has_table_selection())

    def on_action_insert_table(self):
        """Put a table where the text cursor is, or in a new note."""

        item = self.scene.edit_item
        if item is None or getattr(item, 'TYPE', None) != 'text':
            # Nothing being written in, so give the table a note to live
            # in, empty rather than holding the placeholder word
            self.on_action_insert_text()
            item = self.scene.edit_item
            item.textCursor().removeSelectedText()
        self.change_table(item, lambda: item.insert_table())

    def change_table(self, item, change):
        """Run a change to a table, recording it as one undoable step."""

        old_html = item.toHtml()
        change()
        self.undo_stack.push(commands.ChangeTextFormat(
            [item], [item.toHtml()], [old_html]))
        # A table that has just appeared, grown or shrunk changes what
        # the buttons and the menu should offer
        self.update_table_actions()
        self.update_table_toolbar()

    def table_command(self, change):
        """Run a change on whichever table is being edited."""

        item = self.scene.item_with_table()
        if item is None:
            return
        self.change_table(item, change)

    def on_action_table_row_insert(self):
        self.table_command(
            lambda: self.scene.item_with_table().insert_table_row())

    def on_action_table_row_insert_above(self):
        self.table_command(
            lambda: self.scene.item_with_table().insert_table_row(
                below=False))

    def on_action_table_row_remove(self):
        self.table_command(
            lambda: self.scene.item_with_table().remove_table_row())

    def on_action_table_column_insert(self):
        self.table_command(
            lambda: self.scene.item_with_table().insert_table_column())

    def on_action_table_column_remove(self):
        self.table_command(
            lambda: self.scene.item_with_table().remove_table_column())

    def on_action_table_header_top(self):
        """Set the first row apart as a heading, or put it back."""

        self.table_command(
            lambda: self.scene.item_with_table().toggle_header())

    def on_action_table_header_left(self):
        """The same for the first column."""

        self.table_command(
            lambda: self.scene.item_with_table().toggle_header(column=True))

    def on_action_table_cell_color(self):
        """Colour the cells the cursor or the selection covers."""

        item = self.scene.item_with_table()
        if item is None:
            return
        old_html = item.toHtml()

        def preview(color):
            item.apply_cell_color(color)

        color = self.pick_color_live(
            'Choose Cell Colour', QtGui.QColor(), preview)
        # As elsewhere, the preview is the result and the original goes
        # back so the undo command records what was there before
        new_html = item.toHtml()
        item.setHtml(old_html)
        if color is not None:
            self.undo_stack.push(
                commands.ChangeTextFormat([item], [new_html], [old_html]))

    def on_action_text_highlight_color(self):
        """Ask for a highlight colour and apply it to the selected text.

        While editing an item, this applies to the selected words only;
        otherwise it applies to the whole text of each selected item.
        The text colour itself comes from the box colour, so there is
        nothing to pick for it.
        """

        items = self.scene.selected_text_items()
        if not items:
            return
        old_htmls = [item.toHtml() for item in items]

        def preview(color):
            for item in items:
                item.apply_highlight(color)

        color = self.pick_color_live(
            'Choose Highlight Colour', QtGui.QColor(), preview)
        # Whatever the last preview left behind is the chosen result;
        # the originals go back so the undo command records the text as
        # it was before any of this
        new_htmls = [item.toHtml() for item in items]
        for item, html in zip(items, old_htmls):
            item.setHtml(html)
        if color is not None:
            self.undo_stack.push(
                commands.ChangeTextFormat(items, new_htmls, old_htmls))

    def on_action_text_box_color(self):
        items = self.scene.selected_text_items()
        if not items:
            return
        originals = [item.box_color for item in items]

        def preview(color):
            for item in items:
                commands.ChangeTextBoxColor.set_color(item, color)

        color = self.pick_color_live(
            'Choose Box Colour', items[0].box_color, preview)

        # See on_action_group_box_color for why the originals go back even
        # when the dialog was accepted
        for item, original in zip(items, originals):
            commands.ChangeTextBoxColor.set_color(item, original)
        if color is not None:
            self.undo_stack.push(
                commands.ChangeTextBoxColor(items, color))

    def on_action_crop(self):
        self.scene.crop_items()

    def on_action_flip_horizontally(self):
        self.scene.flip_items(vertical=False)

    def on_action_flip_vertically(self):
        self.scene.flip_items(vertical=True)

    def on_action_reset_scale(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetScale(
            self.scene.selectedItems(user_only=True)))

    def on_action_reset_rotation(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetRotation(
            self.scene.selectedItems(user_only=True)))

    def on_action_reset_flip(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetFlip(
            self.scene.selectedItems(user_only=True)))

    def on_action_reset_crop(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetCrop(
            self.scene.selectedItems(user_only=True)))

    def on_action_reset_transforms(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetTransforms(
            self.scene.selectedItems(user_only=True)))

    def on_action_show_color_gamut(self):
        widgets.color_gamut.GamutDialog(self, self.scene.selectedItems()[0])

    def on_action_sample_color(self):
        self.cancel_active_modes()
        logger.debug('Entering sample color mode')
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.active_mode = self.SAMPLE_COLOR_MODE

        if self.scene.has_multi_selection():
            # We don't want to sample the multi select item, so
            # temporarily send it to the back:
            self.scene.multi_select_item.lower_behind_selection()

        pos = self.mapFromGlobal(self.cursor().pos())
        self.sample_color_widget = widgets.SampleColorWidget(
            self,
            pos,
            self.scene.sample_color_at(self.mapToScene(pos)))

    def on_items_loaded(self, value):
        logger.debug('On items loaded: add queued items')
        self.scene.add_queued_items()

    def on_loading_finished(self, filename, errors):
        self.loading_overlay.hide()
        if errors:
            QtWidgets.QMessageBox.warning(
                self,
                'Problem loading file',
                ('<p>Problem loading file %s</p>'
                 '<p>Not accessible or not a proper bee file</p>') % filename)
        else:
            self.filename = filename
            self.scene.add_queued_items()
            if self.scene.items_awaiting_group:
                # Only reachable if a file names a group it does not
                # contain; the items stay where they are, loose
                logger.warning(
                    f'{len(self.scene.items_awaiting_group)} items name a '
                    'group that is not in this file')
                self.scene.items_awaiting_group = []
            # Loading adds images before everything else, which reverses
            # items that share a z value; put them back as they were
            self.scene.restack_as_saved()
            self.on_action_fit_scene()

    def on_action_open_recent_file(self, filename):
        confirm = self.get_confirmation_unsaved_changes(
            'This board has changes that are not saved. '
            'Save them before opening another board?')
        if confirm:
            self.open_from_file(filename)

    def open_from_file(self, filename):
        logger.info(f'Opening file {filename}')
        self.clear_scene()
        # A board arrives item by item, and the view is looking at
        # wherever it was left; cover that up until it is whole
        self.loading_overlay.start()
        self.worker = fileio.ThreadedIO(
            fileio.load_bee, filename, self.scene)
        self.worker.progress.connect(self.on_items_loaded)
        self.worker.finished.connect(self.on_loading_finished)
        self.progress = widgets.BeeProgressDialog(
            f'Loading {filename}',
            worker=self.worker,
            parent=self)
        # Out of the way of the wordmark behind it
        self.progress.move_below_center()
        self.worker.start()

    def on_action_open(self):
        confirm = self.get_confirmation_unsaved_changes(
            'This board has changes that are not saved. '
            'Save them before opening another board?')
        if not confirm:
            return

        self.cancel_active_modes()
        filename, f = QtWidgets.QFileDialog.getOpenFileName(
            parent=self,
            caption='Open file',
            filter=open_dialog_filter())
        if filename:
            filename = os.path.normpath(filename)
            self.open_from_file(filename)
            self.filename = filename

    def on_saving_finished(self, filename, errors):
        if errors:
            QtWidgets.QMessageBox.warning(
                self,
                'Problem saving file',
                ('<p>Problem saving file %s</p>'
                 '<p>File/directory not accessible</p>') % filename)
        else:
            self.filename = filename
            self.undo_stack.setClean()

    def thumbnail(self):
        """A picture of the board as it is being looked at right now.

        Saved with the file so that a board can be recognised in the
        recent files list without opening it.
        """

        if not self.scene.items():
            return None

        # The scene as this view frames it, drawn rather than grabbed:
        # grabbing takes the toolbars and the shortcuts card with it,
        # and those are not what a board is recognised by
        shot = QtGui.QImage(self.viewport().size(),
                            QtGui.QImage.Format.Format_ARGB32)
        shot.fill(QtGui.QColor(
            self.settings.valueOrDefault('View/canvas_color')))
        painter = QtGui.QPainter(shot)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.scene.render(
            painter,
            QtCore.QRectF(shot.rect()),
            self.mapToScene(self.viewport().rect()).boundingRect())
        painter.end()

        image = shot.scaledToWidth(
            self.THUMBNAIL_WIDTH,
            Qt.TransformationMode.SmoothTransformation)
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, 'PNG')
        buffer.close()
        return bytes(data)

    def do_save(self, filename, create_new):
        if not fileio.is_bee_file(filename):
            filename = f'{filename}{constants.FILE_EXT}'
        self.worker = fileio.ThreadedIO(
            fileio.save_bee, filename, self.scene, create_new=create_new,
            thumbnail=self.thumbnail(),
            legend=self.scene.legend)
        self.worker.finished.connect(self.on_saving_finished)
        self.progress = widgets.BeeProgressDialog(
            f'Saving {filename}',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_action_compact_file(self):
        """Give back the disk space deleted items left behind.

        Saving stopped doing this: it rewrites the whole file, which on
        a big board takes far longer than the save itself. The space is
        reused by whatever is added next either way, so this only
        matters when a board has lost a lot and is not going to gain it
        back.
        """

        if not self.filename:
            self.on_action_save_as()
            return
        if not self.undo_stack.isClean():
            QtWidgets.QMessageBox.information(
                self,
                'Save first',
                'Save your changes before compacting the file.')
            return

        self.worker = fileio.ThreadedIO(
            fileio.compact_bee, self.filename, self.scene)
        self.worker.finished.connect(self.on_compacting_finished)
        self.progress = widgets.BeeProgressDialog(
            f'Compacting {self.filename}',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_compacting_finished(self, filename, errors):
        self.progress.deleteLater()
        if errors:
            QtWidgets.QMessageBox.warning(
                self, 'Compacting failed', errors[0])

    def on_action_shrink_images(self):
        """Store the pictures kept losslessly as photographs instead.

        A screenshot arrives with an alpha channel whether or not
        anything in it is see-through, and that alone had it kept as
        PNG. Boards written before that was noticed carry it: one in
        use came to three and a quarter gigabytes, of which the
        pictures were 3.28 and measured 99.97 per cent opaque.

        Asked for rather than done while saving, because it cannot be
        taken back.
        """

        if not self.filename:
            self.on_action_save_as()
            return
        if not self.undo_stack.isClean():
            QtWidgets.QMessageBox.information(
                self,
                'Save first',
                'Save your changes before shrinking the images.')
            return

        answer = QtWidgets.QMessageBox.warning(
            self,
            'Shrink the images?',
            'The pictures on this board that are stored losslessly will '
            'be stored as photographs instead, at ninety per cent '
            'quality.' + chr(10) * 2 +
            'On a board of screenshots this makes the file dozens of '
            'times smaller. It cannot be undone: the pictures are '
            'written again and what the encoding leaves out is gone. '
            'Pictures that really use transparency are left alone.'
            + chr(10) * 2 +
            'Copy the file first if you want to keep what it looks like '
            'now.',
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Cancel)
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        self.before_shrinking = os.path.getsize(self.filename)
        self.worker = fileio.ThreadedIO(
            fileio.shrink_images_bee, self.filename, self.scene)
        self.worker.finished.connect(self.on_shrinking_finished)
        self.progress = widgets.BeeProgressDialog(
            f'Shrinking the images in {self.filename}',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_shrinking_finished(self, filename, errors):
        self.progress.deleteLater()
        if errors:
            QtWidgets.QMessageBox.warning(
                self, 'Shrinking failed', errors[0])
            return
        after = os.path.getsize(self.filename)
        QtWidgets.QMessageBox.information(
            self,
            'Images shrunk',
            f'{self.human_size(self.before_shrinking)} became '
            f'{self.human_size(after)}.' + chr(10) * 2 +
            'Open the board again to see the pictures as they are now '
            'stored.')

    @staticmethod
    def human_size(size):
        for unit in ('bytes', 'KB', 'MB'):
            if size < 1024:
                return f'{size:.0f} {unit}'
            size /= 1024
        return f'{size:.1f} GB'

    def on_action_save_as(self):
        self.cancel_active_modes()
        directory = os.path.dirname(self.filename) if self.filename else None
        filename, f = QtWidgets.QFileDialog.getSaveFileName(
            parent=self,
            caption='Save file',
            directory=directory,
            filter=save_dialog_filter())
        if filename:
            self.do_save(filename, create_new=True)

    def on_action_save(self):
        self.cancel_active_modes()
        if not self.filename:
            self.on_action_save_as()
        else:
            self.do_save(self.filename, create_new=False)

    def on_action_export_scene(self):
        directory = os.path.dirname(self.filename) if self.filename else None
        filename, formatstr = QtWidgets.QFileDialog.getSaveFileName(
            parent=self,
            caption='Export Board to Image',
            directory=directory,
            filter=';;'.join(('Image Files (*.png *.jpg *.jpeg *.svg)',
                              'PNG (*.png)',
                              'JPEG (*.jpg *.jpeg)',
                              'SVG (*.svg)')))

        if not filename:
            return

        name, ext = os.path.splitext(filename)
        if not ext:
            ext = get_file_extension_from_format(formatstr)
            filename = f'{filename}.{ext}'
        logger.debug(f'Got export filename {filename}')

        exporter_cls = exporter_registry[ext]
        exporter = exporter_cls(self.scene)
        if not exporter.get_user_input(self):
            return

        self.worker = fileio.ThreadedIO(exporter.export, filename)
        self.worker.finished.connect(self.on_export_finished)
        self.progress = widgets.BeeProgressDialog(
            f'Exporting {filename}',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_export_finished(self, filename, errors):
        if errors:
            err_msg = '</br>'.join(str(errors))
            QtWidgets.QMessageBox.warning(
                self,
                'Problem writing file',
                f'<p>Problem writing file {filename}</p><p>{err_msg}</p>')

    def on_action_export_images(self):
        directory = os.path.dirname(self.filename) if self.filename else None
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            parent=self,
            caption='Export Images',
            directory=directory)

        if not directory:
            return

        logger.debug(f'Got export directory {directory}')
        self.exporter = ImagesToDirectoryExporter(self.scene, directory)
        self.worker = fileio.ThreadedIO(self.exporter.export)
        self.worker.user_input_required.connect(
            self.on_export_images_file_exists)
        self.worker.finished.connect(self.on_export_finished)
        self.progress = widgets.BeeProgressDialog(
            f'Exporting to {directory}',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_export_images_file_exists(self, filename):
        dlg = widgets.ExportImagesFileExistsDialog(self, filename)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.exporter.handle_existing = dlg.get_answer()
            directory = self.exporter.dirname
            self.progress = widgets.BeeProgressDialog(
                f'Exporting to {directory}',
                worker=self.worker,
                parent=self)
            self.worker.start()

    def on_action_quit(self):
        confirm = self.get_confirmation_unsaved_changes(
            'This board has changes that are not saved. '
            'Save them before quitting?')
        if confirm:
            logger.info('User quit. Exiting...')
            self.app.quit()

    def on_action_settings(self):
        widgets.settings.SettingsDialog(self)

    def on_action_keyboard_settings(self):
        widgets.controls.ControlsDialog(self)

    def on_action_help(self):
        # Bring back the shortcuts card too. It is the quickest answer
        # to "what were the shortcuts again", and closing it once should
        # not put it out of reach.
        self.shortcuts_hint.show_again()
        widgets.HelpDialog(self)

    def on_action_about(self):
        QtWidgets.QMessageBox.about(
            self,
            f'About {constants.APPNAME}',
            (f'<h2>{constants.APPNAME} {constants.VERSION}</h2>'
             f'<p>{constants.APPNAME_FULL}</p>'
             f'<p>Based on {constants.UPSTREAM_NAME}</p>'
             f'<p>{constants.COPYRIGHT}</p>'
             f'<p><a href="{constants.WEBSITE}">'
             f'Visit the {constants.UPSTREAM_NAME} website</a></p>'))

    def on_action_debuglog(self):
        widgets.DebugLogDialog(self)

    def on_insert_images_finished(self, new_scene, filename, errors):
        """Callback for when loading of images is finished.

        :param new_scene: True if the scene was empty before, else False
        :param filename: Not used, for compatibility only
        :param errors: List of filenames that couldn't be loaded
        """

        logger.debug('Insert images finished')
        if errors:
            errornames = [
                f'<li>{fn}</li>' for fn in errors]
            errornames = '<ul>%s</ul>' % '\n'.join(errornames)
            num = len(errors)
            msg = f'{num} image(s) could not be opened.<br/>'
            QtWidgets.QMessageBox.warning(
                self,
                'Problem loading images',
                msg + IMG_LOADING_ERROR_MSG + errornames)
        self.scene.add_queued_items()
        self.scene.arrange_default()
        self.undo_stack.endMacro()
        if new_scene:
            self.on_action_fit_scene()

    def do_insert_images(self, filenames, pos=None):
        if not pos:
            pos = self.get_view_center()
        self.scene.deselect_all_items()
        self.undo_stack.beginMacro('Insert Images')
        self.worker = fileio.ThreadedIO(
            fileio.load_images,
            filenames,
            self.mapToScene(pos),
            self.scene,
            fit_size=self.new_image_size())
        self.worker.progress.connect(self.on_items_loaded)
        self.worker.finished.connect(
            partial(self.on_insert_images_finished,
                    not self.scene.items()))
        self.progress = widgets.BeeProgressDialog(
            'Loading images',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_action_insert_images(self):
        self.cancel_active_modes()
        formats = self.get_supported_image_formats(QtGui.QImageReader)
        logger.debug(f'Supported image types for reading: {formats}')
        filenames, f = QtWidgets.QFileDialog.getOpenFileNames(
            parent=self,
            caption='Select one or more images to open',
            filter=f'Images ({formats})')
        self.do_insert_images(filenames)

    def on_action_insert_text(self):
        self.cancel_active_modes()
        item = BeeTextItem()
        pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos()))
        item.setScale(1 / self.get_scale())
        self.undo_stack.push(commands.InsertItems(self.scene, [item], pos))
        # Start editing straight away, with the placeholder selected so
        # that typing replaces it
        item.enter_edit_mode()
        cursor = item.textCursor()
        cursor.select(QtGui.QTextCursor.SelectionType.Document)
        item.setTextCursor(cursor)

    def on_action_copy(self):
        logger.debug('Copying to clipboard...')
        self.cancel_active_modes()
        clipboard = QtWidgets.QApplication.clipboard()
        items = self.scene.selectedItems(user_only=True)

        # Everything goes onto the clipboard in one go. The marker and
        # whatever other applications can use have to be set together:
        # the QMimeData returned by clipboard.mimeData() belongs to the
        # clipboard, and changing it in place is not supported. Doing
        # that lost the marker, and then pasting fell back to whatever
        # was on the clipboard from before -- which is why copying a
        # group, which offers other applications nothing, pasted the
        # image copied before it.
        mimedata = QtCore.QMimeData()

        # At the moment, we can only copy one image to the global
        # clipboard. (Later, we might create an image of the whole
        # selection for external copying.)
        items[0].add_to_mimedata(mimedata)

        # The marker tells us to look up the internal clipboard when
        # pasting, which is where all of the items are kept
        mimedata.setData(
            'beeref/items', QtCore.QByteArray.number(len(items)))
        clipboard.setMimeData(mimedata)

        self.scene.copy_selection_to_internal_clipboard()

    def on_action_paste(self):
        self.cancel_active_modes()
        logger.debug('Pasting from clipboard...')
        clipboard = QtWidgets.QApplication.clipboard()
        pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos()))

        # See if we need to look up the internal clipboard:
        data = clipboard.mimeData().data('beeref/items')
        logger.debug(f'Custom data in clipboard: {data}')
        if data and self.scene.internal_clipboard:
            # Checking that internal clipboard exists since the user
            # may have opened a new scene since copying.
            self.scene.paste_from_internal_clipboard(pos)
            return

        img = clipboard.image()
        if not img.isNull():
            item = BeePixmapItem(without_pointless_alpha(img))
            item.setScale(item.fit_scale_to(self.new_image_size()))
            self.undo_stack.push(commands.InsertItems(self.scene, [item], pos))
            if len(self.scene.items()) == 1:
                # This is the first image in the scene
                self.on_action_fit_scene()
            return
        rows = tables.table_from_mimedata(clipboard.mimeData())
        if rows:
            self.paste_table(rows, pos)
            return

        text = clipboard.text()
        if text:
            item = BeeTextItem(text)
            item.setScale(1 / self.get_scale())
            self.undo_stack.push(commands.InsertItems(self.scene, [item], pos))
            return

        msg = 'No image data or text in clipboard or image too big'
        logger.info(msg)
        widgets.BeeNotification(self, msg)

    def paste_table(self, rows, pos):
        """Put a table copied from another application on the board.

        Only its shape and its words: a table here has no colours,
        merged cells or column widths to give the rest to.
        """

        item = BeeTextItem()
        item.setPlainText('')
        table = item.insert_table(len(rows), len(rows[0]))
        # Merged before anything is written: what a merge covers is
        # empty, so nothing is run together by joining the cells
        for row, column, down, across in getattr(rows, 'merges', ()):
            table.mergeCells(row, column, down, across)
        for r, row in enumerate(rows):
            for c, words in enumerate(row):
                if words:
                    table.cellAt(r, c).firstCursorPosition().insertText(words)
        item.setScale(1 / self.get_scale())
        self.undo_stack.push(commands.InsertItems(self.scene, [item], pos))
        logger.info(f'Pasted a table of {len(rows)} rows '
                    f'and {len(rows[0])} columns')

    def on_action_open_settings_dir(self):
        dirname = os.path.dirname(self.settings.fileName())
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(dirname))

    def on_selection_changed(self):
        logger.debug('Currently selected items: %s',
                     len(self.scene.selectedItems(user_only=True)))
        self.actiongroup_set_enabled('active_when_selection',
                                     self.scene.has_selection())
        self.actiongroup_set_enabled('active_when_single_image',
                                     self.scene.has_single_image_selection())
        self.actiongroup_set_enabled('active_when_image_selection',
                                     self.scene.has_image_selection())
        self.actiongroup_set_enabled('active_when_text_selection',
                                     self.scene.has_text_selection())
        self.update_table_actions()
        self.actiongroup_set_enabled('active_when_sizeable_selection',
                                     self.scene.has_sizeable_selection())
        self.update_pinned_toolbars()

        if self.scene.has_selection():
            item = self.scene.selectedItems(user_only=True)[0]
            grayscale = getattr(item, 'grayscale', False)
            actions.actions['grayscale'].qaction.setChecked(grayscale)
            actions.actions['lock_group'].qaction.setChecked(
                getattr(item, 'locked', False))
        self.viewport().repaint()

    def tool_cursor(self):
        """The cursor the tool in use wants, or None for the plain arrow."""

        if self.draw_tool is None:
            return None
        if self.draw_tool == constants.TEXT_TOOL:
            return BeeAssets().cursor_text()
        return Qt.CursorShape.CrossCursor

    def on_cursor_changed(self, cursor):
        """An item under the mouse asks for a cursor of its own.

        Ignored while a tool is in use. Items ask as the mouse passes
        over them, which took the T away from the text tool -- and the
        cross from the drawing tools -- without anything having been
        put away.
        """

        if self.active_mode is None and self.draw_tool is None:
            self.viewport().setCursor(cursor)

    def on_cursor_cleared(self):
        if self.active_mode is not None:
            return
        tool = self.tool_cursor()
        if tool is None:
            self.viewport().unsetCursor()
        else:
            # Back to the tool's own cursor, not to the arrow
            self.viewport().setCursor(tool)

    def recalc_scene_rect(self):
        """Resize the scene rectangle so that it is always one view width
        wider than all items' bounding box at each side and one view
        width higher on top and bottom. This gives the impression of
        an infinite canvas."""

        if self.previous_transform:
            return
        logger.trace('Recalculating scene rectangle...')
        try:
            items = self.scene.itemsBoundingRect()
            topleft = self.mapFromScene(items.topLeft())
            topleft = self.mapToScene(QtCore.QPoint(
                topleft.x() - self.size().width(),
                topleft.y() - self.size().height()))
            bottomright = self.mapFromScene(items.bottomRight())
            bottomright = self.mapToScene(QtCore.QPoint(
                bottomright.x() + self.size().width(),
                bottomright.y() + self.size().height()))
            self.setSceneRect(QtCore.QRectF(topleft, bottomright))
        except OverflowError:
            logger.info('Maximum scene size reached')
        logger.trace('Done recalculating scene rectangle')

    def get_zoom_size(self, func):
        """Calculates the size of all items' bounding box in the view's
        coordinates.

        This helps ensure that we never zoom out too much (scene
        becomes so tiny that items become invisible) or zoom in too
        much (causing overflow errors).

        :param func: Function which takes the width and height as
            arguments and turns it into a number, for ex. ``min`` or ``max``.
        """

        # Asked for once: it walks every item on the board, and a
        # smooth zoom lands here on every frame of every step
        items = self.scene.itemsBoundingRect()
        topleft = self.mapFromScene(items.topLeft())
        bottomright = self.mapFromScene(items.bottomRight())
        return func(bottomright.x() - topleft.x(),
                    bottomright.y() - topleft.y())

    def scale(self, *args, **kwargs):
        super().scale(*args, **kwargs)
        self.scene.on_view_scale_change()
        self.recalc_scene_rect()
        self.update_pinned_toolbars()

    def get_scale(self):
        return self.transform().m11()

    def pan(self, delta):
        if not self.scene.items():
            logger.debug('No items in scene; ignore pan')
            return

        # Scroll bars only hold whole numbers, and a smooth zoom asks
        # for many small movements. Throwing away the fraction each
        # time leaves the view shuffling back and forth by a pixel,
        # which reads as everything trembling -- text worst of all, its
        # letters landing on a different pixel from one frame to the
        # next. What is left over is carried into the next move.
        wanted = QtCore.QPointF(delta) + self.pan_remainder
        x = round(wanted.x())
        y = round(wanted.y())
        self.pan_remainder = QtCore.QPointF(wanted.x() - x, wanted.y() - y)

        hscroll = self.horizontalScrollBar()
        hscroll.setValue(hscroll.value() + x)
        vscroll = self.verticalScrollBar()
        vscroll.setValue(vscroll.value() + y)

    def zoom(self, delta, anchor):
        if not self.scene.items():
            logger.debug('No items in scene; ignore zoom')
            return

        # We calculate where the anchor is before and after the zoom
        # and then move the view accordingly to keep the anchor fixed
        # We can't use QGraphicsView's AnchorUnderMouse since it
        # uses the current cursor position while we need the initial mouse
        # press position for zooming with Ctrl + Middle Drag
        # Worked out in fractions of a pixel rather than whole ones.
        # Rounding the anchor, and the correction that follows it, on
        # every step of a smooth zoom is what made the canvas tremble.
        anchor = QtCore.QPointF(anchor)
        to_scene, _ = self.viewportTransform().inverted()
        ref_point = to_scene.map(anchor)
        if delta == 0:
            return
        factor = 1 + abs(delta / 1000)
        if delta > 0:
            if self.get_zoom_size(max) < 10000000:
                self.scale(factor, factor)
            else:
                logger.debug('Maximum zoom size reached')
                return
        else:
            if self.get_zoom_size(min) > 50:
                self.scale(1/factor, 1/factor)
            else:
                logger.debug('Minimum zoom size reached')
                return

        self.pan(self.viewportTransform().map(ref_point) - anchor)
        self.reset_previous_transform()

    def new_image_size(self):
        """How big an image arriving on the board should be.

        In scene coordinates, so it comes out the same share of the
        window whatever the board is zoomed to.
        """

        scale = self.get_scale()
        return QtCore.QSizeF(
            self.width() * self.NEW_IMAGE_SHARE / scale,
            self.height() * self.NEW_IMAGE_SHARE / scale)

    def smooth_zoom(self, delta, anchor):
        """Zoom towards the anchor over the next few frames.

        Turns of the wheel add up rather than replacing each other, so
        spinning it quickly still arrives where it should.
        """

        self.pending_zoom += delta
        self.zoom_anchor = anchor
        if not self.zoom_timer.isActive():
            self.last_zoom_step = time.monotonic()
            self.zoom_timer.start()

    def step_zoom(self):
        """One frame of a smoothed zoom, by the clock.

        Each step used to take a fixed share of what was left, so a
        zoom took as many frames as it took. On a board where a frame
        costs three times what the timer asks for -- which is what a
        few hundred items zoomed out to fit the window comes to -- a
        turn of the wheel then took three times as long to arrive, and
        the board seemed to drift to a halt rather than stop.

        Taking the share from the time that has actually passed instead
        settles the zoom in the same moment however long the frames
        take: fewer, larger steps when the board is busy.
        """

        now = time.monotonic()
        # Explicitly against None: a clock can read zero, and treating
        # that as "not started yet" left the zoom never moving at all
        started = now if self.last_zoom_step is None else self.last_zoom_step
        elapsed = now - started
        self.last_zoom_step = now

        if abs(self.pending_zoom) <= self.ZOOM_REMAINDER:
            step = self.pending_zoom
            self.pending_zoom = 0
            self.zoom_timer.stop()
        else:
            step = self.pending_zoom * self.zoom_share(elapsed)
            self.pending_zoom -= step
        if step:
            self.zoom(step, self.zoom_anchor)

    def zoom_share(self, elapsed):
        """How much of what is left a step covers, for this long a frame.

        ``ZOOM_SMOOTHING`` per ``ZOOM_INTERVAL``, so a frame arriving on
        time behaves exactly as it always did, and a late one catches up
        by as much as it is late.
        """

        intervals = min(elapsed * 1000 / self.ZOOM_INTERVAL,
                        self.ZOOM_MAX_CATCHUP)
        if intervals <= 0:
            return 0
        return 1 - (1 - self.ZOOM_SMOOTHING) ** intervals

    def wheelEvent(self, event):
        action, inverted\
            = self.keyboard_settings.mousewheel_action_for_event(event)

        delta = event.angleDelta().y()
        if inverted:
            delta = delta * -1

        if action == 'zoom':
            self.smooth_zoom(delta, event.position())
            event.accept()
            return
        if action == 'pan_horizontal':
            self.pan(QtCore.QPointF(0, 0.5 * delta))
            event.accept()
            return
        if action == 'pan_vertical':
            self.pan(QtCore.QPointF(0.5 * delta, 0))
            event.accept()
            return

    def mousePressEvent(self, event):
        if self.mousePressEventMainControls(event):
            return

        if (self.draw_tool and event.button() == Qt.MouseButton.LeftButton):
            if self.draw_tool == constants.TEXT_TOOL:
                self.write_note_at(event.pos())
            else:
                self.start_drawing(self.mapToScene(event.pos()))
            event.accept()
            return

        if self.active_mode == self.SAMPLE_COLOR_MODE:
            if (event.button() == Qt.MouseButton.LeftButton):
                color = self.scene.sample_color_at(
                    self.mapToScene(event.pos()))
                if color:
                    name = qcolor_to_hex(color)
                    clipboard = QtWidgets.QApplication.clipboard()
                    clipboard.setText(name)
                    self.scene.internal_clipboard = []
                    msg = f'Copied color to clipboard: {name}'
                    logger.debug(msg)
                    widgets.BeeNotification(self, msg)
                else:
                    logger.debug('No color found')
            self.cancel_sample_color_mode()
            event.accept()
            return

        action, inverted = self.keyboard_settings.mouse_action_for_event(event)

        if action == 'zoom':
            self.active_mode = self.ZOOM_MODE
            self.event_start = event.position()
            self.event_anchor = event.position()
            self.event_inverted = inverted
            event.accept()
            return

        if action == 'pan':
            logger.trace('Begin pan')
            self.active_mode = self.PAN_MODE
            self.event_start = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            # ClosedHandCursor and OpenHandCursor don't work, but I
            # don't know if that's only on my system or a general
            # problem. It works with other cursors.
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drawing_item is not None:
            self.continue_drawing(
                self.mapToScene(event.pos()),
                proportional=bool(event.modifiers()
                                  & Qt.KeyboardModifier.ShiftModifier))
            event.accept()
            return

        if self.active_mode == self.PAN_MODE:
            self.reset_previous_transform()
            pos = event.position()
            self.pan(self.event_start - pos)
            self.event_start = pos
            event.accept()
            return

        if self.active_mode == self.ZOOM_MODE:
            self.reset_previous_transform()
            pos = event.position()
            delta = (self.event_start - pos).y()
            if self.event_inverted:
                delta *= -1
            self.event_start = pos
            self.zoom(delta * 20, self.event_anchor)
            event.accept()
            return

        if self.active_mode == self.SAMPLE_COLOR_MODE:
            self.sample_color_widget.update(
                event.position(),
                self.scene.sample_color_at(self.mapToScene(event.pos())))
            event.accept()
            return

        if self.mouseMoveEventMainControls(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drawing_item is not None:
            self.finish_drawing()
            event.accept()
            return

        if self.active_mode == self.PAN_MODE:
            logger.trace('End pan')
            self.viewport().unsetCursor()
            self.active_mode = None
            event.accept()
            return
        if self.active_mode == self.ZOOM_MODE:
            self.active_mode = None
            event.accept()
            return
        if self.mouseReleaseEventMainControls(event):
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.recalc_scene_rect()
        self.update_pinned_toolbars()
        self.welcome_overlay.resize(self.size())
        if self.loading_overlay.isVisible():
            self.loading_overlay.resize(self.size())
        if self.shortcuts_hint.isVisible():
            self.shortcuts_hint.reposition()
        if self.layers_handle.isVisible():
            self.layers_handle.reposition()
        if self.legend_handle.isVisible():
            self.legend_handle.reposition()

    def pin_toolbar_to(self, toolbar, items, avoid=None):
        """Put a bar over the given items, or hide it if there are none.

        A bar given something to ``avoid`` goes above that bar as well,
        so two of them stack instead of covering each other.
        """

        if toolbar is None:
            return
        if not items:
            toolbar.hide()
            return
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        toolbar.pin_to(self.mapFromScene(rect).boundingRect(), avoid=avoid)
        toolbar.show()

    def update_text_toolbar(self):
        """Show the text buttons over the selected text, or not at all."""

        toolbar = getattr(self, 'text_toolbar', None)
        items = self.scene.selected_text_items()
        if toolbar is not None and items:
            toolbar.update_title(items[0])
        self.pin_toolbar_to(toolbar, items)

    def update_draw_item_toolbar(self):
        """Show the drawing buttons over the selected drawings."""

        self.pin_toolbar_to(getattr(self, 'draw_item_toolbar', None),
                            self.scene.selected_draw_items())

    def update_group_toolbar(self):
        """Show the group buttons over the selected groups."""

        toolbar = getattr(self, 'group_toolbar', None)
        groups = self.scene.selected_groups()
        if toolbar is not None and groups:
            toolbar.update_lock(groups[0].locked)
            toolbar.update_title(groups[0])
        self.pin_toolbar_to(toolbar, groups)

    def update_image_toolbar(self):
        """Show the crop and contour buttons over the selected images."""

        toolbar = getattr(self, 'image_toolbar', None)
        images = self.scene.selected_images()
        if toolbar is not None and images:
            toolbar.update_state(images)
        self.pin_toolbar_to(toolbar, images)

    def update_table_toolbar(self):
        """Show the table buttons while the cursor is inside a table.

        Placed above the text bar rather than on top of it: a note
        holding a table has both, and they would otherwise land in the
        same spot.
        """

        toolbar = getattr(self, 'table_toolbar', None)
        item = self.scene.item_with_table()
        if toolbar is None:
            return
        if item is None:
            toolbar.hide()
            return
        toolbar.update_headers(item)
        self.pin_toolbar_to(toolbar, [item],
                            avoid=getattr(self, 'text_toolbar', None))

    def update_pinned_toolbars(self):
        """Keep the bars over what they act on.

        Called whenever anything could have moved an item on screen: the
        selection changing, an item being dragged, zooming, panning, or
        the window being resized.
        """

        self.update_text_toolbar()
        self.update_draw_item_toolbar()
        self.update_group_toolbar()
        self.update_image_toolbar()
        self.update_table_toolbar()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        # Panning moves items under bars that would otherwise stay put
        self.update_pinned_toolbars()

    def escape(self):
        """Back to the mouse, with nothing selected.

        One key to get out of whatever is going on: put the drawing tool
        away, drop any half-finished mode, and clear the selection.
        """

        self.cancel_active_modes()
        if self.draw_tool is not None:
            self.set_draw_tool(None)
        self.scene.deselect_all_items()

    def keyPressEvent(self, event):
        if self.keyPressEventMainControls(event):
            return
        if self.active_mode == self.SAMPLE_COLOR_MODE:
            self.cancel_sample_color_mode()
            event.accept()
            return
        if (event.key() == Qt.Key.Key_Escape
                and self.scene.edit_item is None
                and self.scene.crop_item is None):
            # Text being edited and images being cropped answer Escape
            # themselves, by throwing the change away, so leave those to
            # the item and only take over when nothing is mid-edit
            self.escape()
            event.accept()
            return
        super().keyPressEvent(event)
