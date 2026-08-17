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
from itertools import cycle
import logging
import os
import os.path

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref.actions import ActionsMixin, actions
from beeref import commands
from beeref.config import (
    CommandlineArgs, BeeSettings, KeyboardSettings, settings_events)
from beeref import constants
from beeref import fileio
from beeref.fileio.errors import IMG_LOADING_ERROR_MSG
from beeref.fileio.export import exporter_registry, ImagesToDirectoryExporter
from beeref import widgets
from beeref.items import (
    BeeDrawItem, BeeGroupItem, BeePixmapItem, BeeTextItem)
from beeref.main_controls import MainControlsMixin
from beeref.scene import BeeGraphicsScene
from beeref.utils import get_file_extension_from_format, qcolor_to_hex


commandline_args = CommandlineArgs()
logger = logging.getLogger(__name__)


class BeeGraphicsView(MainControlsMixin,
                      QtWidgets.QGraphicsView,
                      ActionsMixin):

    PAN_MODE = 1
    ZOOM_MODE = 2
    SAMPLE_COLOR_MODE = 3

    # On-screen bounds in pixels between which the grid spacing is kept
    GRID_MIN_SPACING = 25
    GRID_MAX_SPACING = 250

    # Range offered when changing the size of text
    TEXT_SIZE_MIN = 4
    TEXT_SIZE_MAX = 400

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.parent = parent
        self.settings = BeeSettings()
        self.keyboard_settings = KeyboardSettings()
        self.welcome_overlay = widgets.welcome_overlay.WelcomeOverlay(self)
        # Built early: a resize can arrive before the end of setup
        self.shortcuts_hint = widgets.shortcuts_hint.ShortcutsHint(self)

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

        # Context menu and actions
        self.build_menu_and_actions()
        self.control_target = self
        self.init_main_controls(main_window=parent)

        # Load files given via command line
        if commandline_args.filenames:
            fn = commandline_args.filenames[0]
            if os.path.splitext(fn)[1] == '.bee':
                self.open_from_file(fn)
            else:
                self.do_insert_images(commandline_args.filenames)

        self.update_window_title()

        # The drawing tools, in the top left corner
        self.draw_toolbar = widgets.draw_toolbar.DrawToolBar(self, self)
        self.draw_toolbar.reposition()
        self.draw_toolbar.show()

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
        clean = self.undo_stack.isClean()
        if clean and not self.filename:
            title = constants.APPNAME
        else:
            name = os.path.basename(self.filename or '[Untitled]')
            clean = '' if clean else '*'
            title = f'{name}{clean} - {constants.APPNAME}'
        self.parent.setWindowTitle(title)

    def on_canvas_color_changed(self, color):
        logger.debug(f'Canvas colour changed to: {color}')
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(color)))

    def on_action_show_layers(self, checked):
        self.layers_dock.setVisible(checked)
        if checked:
            self.layers_dock.tree.refresh()

    def on_layers_dock_closed(self):
        """Untick the menu entry when the panel is closed by its button."""

        actions.actions['show_layers'].qaction.setChecked(False)

    def set_draw_tool(self, kind):
        """Pick a drawing tool, or ``None`` to go back to selecting."""

        logger.debug(f'Drawing tool: {kind}')
        self.draw_tool = kind
        if kind is None:
            self.viewport().unsetCursor()
        else:
            self.cancel_active_modes()
            self.scene.deselect_all_items()
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        if hasattr(self, 'draw_toolbar'):
            self.draw_toolbar.update_checked(kind)

    def start_drawing(self, pos):
        """Begin a new drawing at the given scene position."""

        self.drawing_points = [pos]
        self.drawing_item = BeeDrawItem(
            points=[[pos.x(), pos.y()]],
            kind=self.draw_tool,
            color=self.draw_color.getRgb(),
            width=self.draw_width)
        self.scene.addItem(self.drawing_item)
        self.drawing_item.bring_to_front()

    def continue_drawing(self, pos):
        self.drawing_points.append(pos)
        self.drawing_item.set_points(
            [[p.x(), p.y()] for p in self.drawing_points])

    def finish_drawing(self):
        """Turn the drawing into a real item, or drop it if it's a dot."""

        item = self.drawing_item
        points = self.drawing_points
        self.drawing_item = None
        self.drawing_points = []
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
        self.undo_stack.push(commands.InsertItems(self.scene, [item]))

    def on_action_draw_color(self):
        """Set the colour for new drawings, and for any selected ones."""

        color = QtWidgets.QColorDialog.getColor(
            self.draw_color, self, 'Choose Drawing Colour')
        if not color.isValid():
            return
        self.draw_color = color
        if hasattr(self, 'draw_toolbar'):
            self.draw_toolbar.update_color(color)

        items = [item for item in self.scene.selectedItems(user_only=True)
                 if item.TYPE == BeeDrawItem.TYPE]
        if items:
            self.undo_stack.push(commands.ChangeDrawColor(items, color))

    def on_action_show_grid(self, checked):
        self.show_grid = checked
        self.viewport().update()

    def on_grid_changed(self):
        self.viewport().update()

    def get_grid_step(self):
        """The grid spacing in scene coordinates.

        The base spacing from the settings is scaled up or down so that
        the grid keeps a sensible distance on screen at any zoom level:
        it never turns into a dense mess when zoomed out, and never
        disappears when zoomed in.
        """

        zoom = self.get_scale()
        step = self.settings.valueOrDefault('View/grid_size')
        # Alternating factors give a 10/50/100/500 style sequence
        factors = cycle((5, 2))
        while step * zoom < self.GRID_MIN_SPACING:
            step *= next(factors)
        factors = cycle((2, 5))
        while step * zoom > self.GRID_MAX_SPACING:
            step /= next(factors)
        return step

    def drawBackground(self, painter, rect):
        """Draws the canvas background, and the grid on top of it.

        The grid lives on the view rather than the scene so that it
        never ends up in exported images, which render the scene.
        """

        super().drawBackground(painter, rect)
        if not self.show_grid:
            return

        step = self.get_grid_step()
        pen = QtGui.QPen(
            QtGui.QColor(self.settings.valueOrDefault('View/grid_color')))
        # Keep lines one pixel wide whatever the zoom level
        pen.setCosmetic(True)
        painter.setPen(pen)

        lines = []
        start_x = rect.left() - (rect.left() % step)
        x = start_x
        while x < rect.right():
            lines.append(QtCore.QLineF(x, rect.top(), x, rect.bottom()))
            x += step
        start_y = rect.top() - (rect.top() % step)
        y = start_y
        while y < rect.bottom():
            lines.append(QtCore.QLineF(rect.left(), y, rect.right(), y))
            y += step
        painter.drawLines(lines)

    def on_scene_changed(self, region):
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
            self.text_context_menu.exec(self.mapToGlobal(point))
            return

        # An item inside a group offers its own actions, such as crop
        # and the transforms, with the group opened up so they apply.
        # The full menu still holds the group's own actions.
        item = self.get_item_at(point)
        group = self.scene.get_group_ancestor(item) if item else None
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
        confirm = self.settings.valueOrDefault('Save/confirm_close_unsaved')
        if confirm and not self.undo_stack.isClean():
            answer = QtWidgets.QMessageBox.question(
                self,
                'Discard unsaved changes?',
                msg,
                QtWidgets.QMessageBox.StandardButton.Yes |
                QtWidgets.QMessageBox.StandardButton.Cancel)
            return answer == QtWidgets.QMessageBox.StandardButton.Yes

        return True

    def on_action_new_scene(self):
        confirm = self.get_confirmation_unsaved_changes(
            'There are unsaved changes. '
            'Are you sure you want to open a new scene?')
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

    def on_action_group_box_color(self):
        groups = [item for item in self.scene.selectedItems(user_only=True)
                  if item.TYPE == BeeGroupItem.TYPE]
        if not groups:
            widgets.BeeNotification(self, 'No group selected')
            return
        color = QtWidgets.QColorDialog.getColor(
            groups[0].box_color,
            self,
            'Choose Group Colour',
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self.undo_stack.push(
                commands.ChangeGroupBoxColor(groups, color))

    def on_action_find_text(self):
        query, ok = QtWidgets.QInputDialog.getText(
            self, 'Find Text', 'Find:', text=self.text_search_query)
        if not ok or not query:
            return
        self.text_search_query = query
        self.text_search_index = -1
        self.find_next_text_match()

    def on_action_find_next(self):
        if self.text_search_query:
            self.find_next_text_match()
        else:
            self.on_action_find_text()

    def get_text_search_matches(self):
        """The text items containing the current search query, ordered
        top to bottom so that cycling through them is predictable."""

        query = self.text_search_query.lower()
        matches = [item for item in self.scene.items_by_type('text')
                   if query in item.toPlainText().lower()]
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
        self.centerOn(item.sceneBoundingRect().center())
        widgets.BeeNotification(
            self,
            f'Match {self.text_search_index + 1} of {len(matches)}'
            f' for "{self.text_search_query}"')

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

    def text_is_bold(self, item):
        cursor = item.textCursor()
        if not cursor.hasSelection():
            cursor.select(QtGui.QTextCursor.SelectionType.Document)
        return cursor.charFormat().fontWeight() > QtGui.QFont.Weight.Normal

    def on_action_text_size(self):
        """Change the size of the selected words, or the whole text."""

        items = self.scene.selected_text_items()
        if not items:
            return
        size, ok = QtWidgets.QInputDialog.getInt(
            self, 'Text Size', 'Size:', self.get_text_size(items[0]),
            self.TEXT_SIZE_MIN, self.TEXT_SIZE_MAX)
        if not ok:
            return
        charformat = QtGui.QTextCharFormat()
        charformat.setFontPointSize(size)
        self.apply_text_char_format(items, charformat)

    def get_text_size(self, item):
        cursor = item.textCursor()
        if not cursor.hasSelection():
            cursor.select(QtGui.QTextCursor.SelectionType.Document)
        size = cursor.charFormat().fontPointSize()
        # Text that has never been sized reports zero
        return int(size) or int(item.font().pointSize())

    def apply_text_char_format(self, items, charformat):
        """Apply the format to the given items, as one undo step."""

        old_htmls = [item.toHtml() for item in items]
        for item in items:
            item.apply_char_format(charformat)
        new_htmls = [item.toHtml() for item in items]
        self.undo_stack.push(
            commands.ChangeTextFormat(items, new_htmls, old_htmls))

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
        color = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(), self, 'Choose Highlight Colour')
        if not color.isValid():
            return

        charformat = QtGui.QTextCharFormat()
        charformat.setBackground(color)
        self.apply_text_char_format(items, charformat)

    def on_action_text_box_color(self):
        items = self.scene.selected_text_items()
        if not items:
            return
        color = QtWidgets.QColorDialog.getColor(
            items[0].box_color,
            self,
            'Choose Box Colour',
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
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
        if errors:
            QtWidgets.QMessageBox.warning(
                self,
                'Problem loading file',
                ('<p>Problem loading file %s</p>'
                 '<p>Not accessible or not a proper bee file</p>') % filename)
        else:
            self.filename = filename
            self.scene.add_queued_items()
            self.on_action_fit_scene()

    def on_action_open_recent_file(self, filename):
        confirm = self.get_confirmation_unsaved_changes(
            'There are unsaved changes. '
            'Are you sure you want to open a new scene?')
        if confirm:
            self.open_from_file(filename)

    def open_from_file(self, filename):
        logger.info(f'Opening file {filename}')
        self.clear_scene()
        self.worker = fileio.ThreadedIO(
            fileio.load_bee, filename, self.scene)
        self.worker.progress.connect(self.on_items_loaded)
        self.worker.finished.connect(self.on_loading_finished)
        self.progress = widgets.BeeProgressDialog(
            f'Loading {filename}',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_action_open(self):
        confirm = self.get_confirmation_unsaved_changes(
            'There are unsaved changes. '
            'Are you sure you want to open a new scene?')
        if not confirm:
            return

        self.cancel_active_modes()
        filename, f = QtWidgets.QFileDialog.getOpenFileName(
            parent=self,
            caption='Open file',
            filter=f'{constants.APPNAME} File (*.bee)')
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

    def do_save(self, filename, create_new):
        if not fileio.is_bee_file(filename):
            filename = f'{filename}.bee'
        self.worker = fileio.ThreadedIO(
            fileio.save_bee, filename, self.scene, create_new=create_new)
        self.worker.finished.connect(self.on_saving_finished)
        self.progress = widgets.BeeProgressDialog(
            f'Saving {filename}',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_action_save_as(self):
        self.cancel_active_modes()
        directory = os.path.dirname(self.filename) if self.filename else None
        filename, f = QtWidgets.QFileDialog.getSaveFileName(
            parent=self,
            caption='Save file',
            directory=directory,
            filter=f'{constants.APPNAME} File (*.bee)')
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
            caption='Export Scene to Image',
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
            'There are unsaved changes. Are you sure you want to quit?')
        if confirm:
            logger.info('User quit. Exiting...')
            self.app.quit()

    def on_action_settings(self):
        widgets.settings.SettingsDialog(self)

    def on_action_keyboard_settings(self):
        widgets.controls.ControlsDialog(self)

    def on_action_help(self):
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
            self.scene)
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

        # At the moment, we can only copy one image to the global
        # clipboard. (Later, we might create an image of the whole
        # selection for external copying.)
        items[0].copy_to_clipboard(clipboard)

        # However, we can copy all items to the internal clipboard:
        self.scene.copy_selection_to_internal_clipboard()

        # We set a marker for ourselves in the global clipboard so
        # that we know to look up the internal clipboard when pasting:
        clipboard.mimeData().setData(
            'beeref/items', QtCore.QByteArray.number(len(items)))

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
            item = BeePixmapItem(img)
            self.undo_stack.push(commands.InsertItems(self.scene, [item], pos))
            if len(self.scene.items()) == 1:
                # This is the first image in the scene
                self.on_action_fit_scene()
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
        self.actiongroup_set_enabled('active_when_text_selection',
                                     self.scene.has_text_selection())

        if self.scene.has_selection():
            item = self.scene.selectedItems(user_only=True)[0]
            grayscale = getattr(item, 'grayscale', False)
            actions.actions['grayscale'].qaction.setChecked(grayscale)
            actions.actions['lock_group'].qaction.setChecked(
                getattr(item, 'locked', False))
        self.viewport().repaint()

    def on_cursor_changed(self, cursor):
        if self.active_mode is None:
            self.viewport().setCursor(cursor)

    def on_cursor_cleared(self):
        if self.active_mode is None:
            self.viewport().unsetCursor()

    def recalc_scene_rect(self):
        """Resize the scene rectangle so that it is always one view width
        wider than all items' bounding box at each side and one view
        width higher on top and bottom. This gives the impression of
        an infinite canvas."""

        if self.previous_transform:
            return
        logger.trace('Recalculating scene rectangle...')
        try:
            topleft = self.mapFromScene(
                self.scene.itemsBoundingRect().topLeft())
            topleft = self.mapToScene(QtCore.QPoint(
                topleft.x() - self.size().width(),
                topleft.y() - self.size().height()))
            bottomright = self.mapFromScene(
                self.scene.itemsBoundingRect().bottomRight())
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

        topleft = self.mapFromScene(
            self.scene.itemsBoundingRect().topLeft())
        bottomright = self.mapFromScene(
            self.scene.itemsBoundingRect().bottomRight())
        return func(bottomright.x() - topleft.x(),
                    bottomright.y() - topleft.y())

    def scale(self, *args, **kwargs):
        super().scale(*args, **kwargs)
        self.scene.on_view_scale_change()
        self.recalc_scene_rect()

    def get_scale(self):
        return self.transform().m11()

    def pan(self, delta):
        if not self.scene.items():
            logger.debug('No items in scene; ignore pan')
            return

        hscroll = self.horizontalScrollBar()
        hscroll.setValue(int(hscroll.value() + delta.x()))
        vscroll = self.verticalScrollBar()
        vscroll.setValue(int(vscroll.value() + delta.y()))

    def zoom(self, delta, anchor):
        if not self.scene.items():
            logger.debug('No items in scene; ignore zoom')
            return

        # We calculate where the anchor is before and after the zoom
        # and then move the view accordingly to keep the anchor fixed
        # We can't use QGraphicsView's AnchorUnderMouse since it
        # uses the current cursor position while we need the initial mouse
        # press position for zooming with Ctrl + Middle Drag
        anchor = QtCore.QPoint(round(anchor.x()),
                               round(anchor.y()))
        ref_point = self.mapToScene(anchor)
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

        self.pan(self.mapFromScene(ref_point) - anchor)
        self.reset_previous_transform()

    def wheelEvent(self, event):
        action, inverted\
            = self.keyboard_settings.mousewheel_action_for_event(event)

        delta = event.angleDelta().y()
        if inverted:
            delta = delta * -1

        if action == 'zoom':
            self.zoom(delta, event.position())
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
            self.continue_drawing(self.mapToScene(event.pos()))
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
        self.welcome_overlay.resize(self.size())
        if self.shortcuts_hint.isVisible():
            self.shortcuts_hint.reposition()

    def keyPressEvent(self, event):
        if self.keyPressEventMainControls(event):
            return
        if self.active_mode == self.SAMPLE_COLOR_MODE:
            self.cancel_sample_color_mode()
            event.accept()
            return
        super().keyPressEvent(event)
