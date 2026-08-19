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
from queue import Queue

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtCore import Qt

import rpack

from beeref import commands
from beeref.config import BeeSettings
from beeref.items import item_registry, BeeErrorItem, sort_by_filename
from beeref.selection import MultiSelectItem, RubberbandItem


logger = logging.getLogger(__name__)


class BeeGraphicsScene(QtWidgets.QGraphicsScene):
    cursor_changed = QtCore.pyqtSignal(QtGui.QCursor)
    cursor_cleared = QtCore.pyqtSignal()

    MOVE_MODE = 1
    RUBBERBAND_MODE = 2

    def __init__(self, undo_stack):
        super().__init__()
        self.active_mode = None
        self.undo_stack = undo_stack
        self.max_z = 0
        self.min_z = 0
        self.Z_STEP = 0.001
        self.selectionChanged.connect(self.on_selection_change)
        self.changed.connect(self.on_change)
        self.items_to_add = Queue()
        self.edit_item = None
        self.crop_item = None
        # The group whose items can currently be edited individually
        self.active_group = None
        # The group highlighted as the drop target during a drag
        self.drop_target = None
        # Original z values of the items being dragged
        self.dragged_z = []
        self.settings = BeeSettings()
        self.clear()
        self._clear_ongoing = False

    def clear(self):
        self._clear_ongoing = True
        super().clear()
        self.internal_clipboard = []
        self.rubberband_item = RubberbandItem()
        self.multi_select_item = MultiSelectItem()
        self._clear_ongoing = False

    def addItem(self, item):
        logger.debug(f'Adding item {item}')
        super().addItem(item)

    def removeItem(self, item):
        logger.debug(f'Removing item {item}')
        super().removeItem(item)

    def cancel_active_modes(self):
        """Cancels ongoing crop modes, rubberband modes etc, if there are
        any.
        """
        self.cancel_crop_mode()
        self.end_rubberband_mode()

    def get_group_ancestor(self, item):
        """The nearest group containing the given item, if any."""

        chain = self.group_chain(item)
        return chain[0] if chain else None

    def refit_group(self, group):
        """Refit a group's box and those of the groups containing it."""

        while group is not None:
            if group.scene() is self:
                group.fit_to_children()
            group = self.get_group_ancestor(group)

    def get_drop_group(self, item):
        """The group the given item would land in at its current position.

        Returns ``None`` when the item isn't over any group. Groups the
        item itself contains are skipped, so that a group can't be
        dropped inside itself.
        """

        center = item.mapToScene(item.center)
        candidates = [
            group for group in self.items_by_type('group')
            if group is not item
            and not item.isAncestorOf(group)
            and not group.locked
            and group.contains_scene_pos(center)]
        if not candidates:
            return None
        # Innermost group wins, so dropping into a nested group works
        return max(candidates, key=lambda group: len(self.group_chain(group)))

    def group_chain(self, item):
        """The groups containing the given item, innermost first."""

        chain = []
        parent = item.parentItem()
        while parent is not None:
            if getattr(parent, 'TYPE', None) == 'group':
                chain.append(parent)
            parent = parent.parentItem()
        return chain

    def update_group_membership(self, items, detach=False):
        """Update which group the dragged items belong to.

        Items join the group they were dropped on. Items never leave
        their group just by being dragged outside its box, since that
        would make it impossible to spread items out within a group;
        the box grows instead. Dragging with ``detach`` (the alt key)
        takes an item out of its group.
        """

        for item in items:
            if getattr(item, 'TYPE', None) is None:
                continue
            current = self.get_group_ancestor(item)
            if detach:
                target = None
            else:
                # Falling back to the current group means an item that
                # is dropped over nothing simply stays where it was
                target = self.get_drop_group(item) or current
            if target is current:
                # The box may need to grow around its moved items
                self.refit_group(current)
                if current is not None:
                    current.touch()
                continue
            logger.debug(f'Moving {item} from {current} to {target}')
            self.undo_stack.push(
                commands.MoveToGroup(self, [item], target))

    def enter_group(self, group, item=None):
        """Allow the items inside the given group to be edited individually.

        This is what double-clicking an item inside a group does: the
        group stops behaving like a single object until the user clicks
        somewhere else.
        """

        if self.active_group is not group:
            self.exit_group()
            logger.debug(f'Entering {group}')
            self.active_group = group
            group.set_children_interactive(True)
        if item is not None:
            self.clearSelection()
            item.setSelected(True)

    def exit_group(self):
        """Make the active group behave like a single object again."""

        group = self.active_group
        if group is None:
            return
        logger.debug(f'Leaving {group}')
        # Cleared first: deselecting the items below triggers selection
        # handling that can call this method again
        self.active_group = None
        if group.scene() is self:
            group.set_children_interactive(False)
            # Items may have been moved around inside the group
            self.refit_group(group)

    def end_rubberband_mode(self):
        if self.rubberband_item.scene():
            logger.debug('Ending rubberband selection')
            self.removeItem(self.rubberband_item)
        self.active_mode = None

    def cancel_crop_mode(self):
        """Cancels an ongoing crop mode, if there is any."""
        if self.crop_item:
            self.crop_item.exit_crop_mode(confirm=False)

    def copy_selection_to_internal_clipboard(self):
        self.internal_clipboard = []
        for item in self.selectedItems(user_only=True):
            self.internal_clipboard.append(item)

    def paste_from_internal_clipboard(self, position):
        copies = []
        for item in self.internal_clipboard:
            copy = item.create_copy()
            copies.append(copy)
        self.undo_stack.push(commands.InsertItems(self, copies, position))

    def raise_to_top(self):
        self.cancel_active_modes()
        items = self.selectedItems(user_only=True)
        z_values = map(lambda i: i.zValue(), items)
        delta = self.max_z + self.Z_STEP - min(z_values)
        logger.debug(f'Raise to top, delta: {delta}')
        for item in items:
            item.setZValue(item.zValue() + delta)

    def lower_to_bottom(self):
        self.cancel_active_modes()
        items = self.selectedItems(user_only=True)
        z_values = map(lambda i: i.zValue(), items)
        delta = self.min_z - self.Z_STEP - max(z_values)
        logger.debug(f'Lower to bottom, delta: {delta}')

        for item in items:
            item.setZValue(item.zValue() + delta)

    def normalize_width_or_height(self, mode):
        """Scale the selected images to have the same width or height, as
        specified by ``mode``.

        :param mode: "width" or "height".
        """

        self.cancel_active_modes()
        values = []
        items = self.selectedItems(user_only=True)
        for item in items:
            rect = self.itemsBoundingRect(items=[item])
            values.append(getattr(rect, mode)())
        if len(values) < 2:
            return
        avg = sum(values) / len(values)
        logger.debug(f'Calculated average {mode} {avg}')

        scale_factors = []
        for item in items:
            rect = self.itemsBoundingRect(items=[item])
            scale_factors.append(avg / getattr(rect, mode)())
        self.undo_stack.push(
            commands.NormalizeItems(items, scale_factors))

    def normalize_height(self):
        """Scale selected images to the same height."""
        return self.normalize_width_or_height('height')

    def normalize_width(self):
        """Scale selected images to the same width."""
        return self.normalize_width_or_height('width')

    def normalize_size(self):
        """Scale selected images to the same size.

        Size meaning the area = widh * height.
        """

        self.cancel_active_modes()
        sizes = []
        items = self.selectedItems(user_only=True)
        for item in items:
            rect = self.itemsBoundingRect(items=[item])
            sizes.append(rect.width() * rect.height())

        if len(sizes) < 2:
            return

        avg = sum(sizes) / len(sizes)
        logger.debug(f'Calculated average size {avg}')

        scale_factors = []
        for item in items:
            rect = self.itemsBoundingRect(items=[item])
            scale_factors.append(math.sqrt(avg / rect.width() / rect.height()))
        self.undo_stack.push(
            commands.NormalizeItems(items, scale_factors))

    def arrange_default(self):
        default = self.settings.valueOrDefault('Items/arrange_default')
        MAPPING = {
            'optimal': self.arrange_optimal,
            'horizontal': self.arrange,
            'vertical': partial(self.arrange, vertical=True),
            'square': self.arrange_square,
        }

        MAPPING[default]()

    def arrange(self, vertical=False):
        """Arrange items in a line (horizontally or vertically)."""

        self.cancel_active_modes()

        items = sort_by_filename(self.selectedItems(user_only=True))
        if len(items) < 2:
            return

        gap = self.settings.valueOrDefault('Items/arrange_gap')
        center = self.get_selection_center()
        positions = []
        rects = []
        for item in items:
            rects.append({
                'rect': self.itemsBoundingRect(items=[item]),
                'item': item})

        if vertical:
            rects.sort(key=lambda r: r['rect'].topLeft().y())
            sum_height = sum(map(lambda r: r['rect'].height(), rects))
            y = round(center.y() - sum_height/2)
            for rect in rects:
                positions.append(
                    QtCore.QPointF(
                        round(center.x() - rect['rect'].width()/2), y))
                y += rect['rect'].height() + gap

        else:
            rects.sort(key=lambda r: r['rect'].topLeft().x())
            sum_width = sum(map(lambda r: r['rect'].width(), rects))
            x = round(center.x() - sum_width/2)
            for rect in rects:
                positions.append(
                    QtCore.QPointF(
                        x, round(center.y() - rect['rect'].height()/2)))
                x += rect['rect'].width() + gap

        self.undo_stack.push(
            commands.ArrangeItems(self,
                                  [r['item'] for r in rects],
                                  positions))

    def arrange_optimal(self):
        self.cancel_active_modes()

        items = self.selectedItems(user_only=True)
        if len(items) < 2:
            return

        gap = self.settings.valueOrDefault('Items/arrange_gap')

        sizes = []
        for item in items:
            rect = self.itemsBoundingRect(items=[item])
            sizes.append((round(rect.width() + gap),
                          round(rect.height() + gap)))

        # The minimal area the items need if they could be packed optimally;
        # we use this as a starting shape for the packing algorithm
        min_area = sum(map(lambda s: s[0] * s[1], sizes))
        width = math.ceil(math.sqrt(min_area))

        positions = None
        while not positions:
            try:
                positions = rpack.pack(
                    sizes, max_width=width, max_height=width)
            except rpack.PackingImpossibleError:
                width = math.ceil(width * 1.2)

        # We want the items to center around the selection's center,
        # not (0, 0)
        center = self.get_selection_center()
        bounds = rpack.bbox_size(sizes, positions)
        diff = center - QtCore.QPointF(bounds[0]/2, bounds[1]/2)
        positions = [QtCore.QPointF(*pos) + diff for pos in positions]

        self.undo_stack.push(commands.ArrangeItems(self, items, positions))

    def arrange_square(self):
        self.cancel_active_modes()
        max_width = 0
        max_height = 0
        gap = self.settings.valueOrDefault('Items/arrange_gap')
        items = sort_by_filename(self.selectedItems(user_only=True))

        if len(items) < 2:
            return

        for item in items:
            rect = self.itemsBoundingRect(items=[item])
            max_width = max(max_width, rect.width() + gap)
            max_height = max(max_height, rect.height() + gap)

        # We want the items to center around the selection's center,
        # not (0, 0)
        num_rows = math.ceil(math.sqrt(len(items)))
        center = self.get_selection_center()
        diff = center - num_rows/2 * QtCore.QPointF(max_width, max_height)

        iter_items = iter(items)
        positions = []
        for j in range(num_rows):
            for i in range(num_rows):
                try:
                    item = next(iter_items)
                    rect = self.itemsBoundingRect(items=[item])
                    point = QtCore.QPointF(
                        i * max_width + (max_width - rect.width())/2,
                        j * max_height + (max_height - rect.height())/2)
                    positions.append(point + diff)
                except StopIteration:
                    break

        self.undo_stack.push(commands.ArrangeItems(self, items, positions))

    def flip_items(self, vertical=False):
        """Flip selected items."""
        self.cancel_active_modes()
        self.undo_stack.push(
            commands.FlipItems(self.selectedItems(user_only=True),
                               self.get_selection_center(),
                               vertical=vertical))

    def crop_items(self):
        """Crop selected item."""

        if self.crop_item:
            return
        if self.has_single_image_selection():
            item = self.selectedItems(user_only=True)[0]
            if item.is_image:
                item.enter_crop_mode()

    def sample_color_at(self, position):
        item_at_pos = self.itemAt(position, self.views()[0].transform())
        if item_at_pos:
            return item_at_pos.sample_color_at(position)

    def select_all_items(self):
        self.cancel_active_modes()
        path = QtGui.QPainterPath()
        path.addRect(self.itemsBoundingRect())
        # This is faster than looping through all items and calling setSelected
        self.setSelectionArea(path)

    def deselect_all_items(self):
        self.cancel_active_modes()
        self.exit_group()
        self.clearSelection()

    def has_selection(self):
        """Checks whether there are currently items selected."""

        return bool(self.selectedItems(user_only=True))

    def has_single_selection(self):
        """Checks whether there's currently exactly one item selected."""

        return len(self.selectedItems(user_only=True)) == 1

    def has_multi_selection(self):
        """Checks whether there are currently more than one items selected."""

        return len(self.selectedItems(user_only=True)) > 1

    def has_text_selection(self):
        """Checks whether the current selection contains text items."""

        return bool(self.selected_text_items())

    def selected_text_items(self):
        """The currently selected text items."""

        return [item for item in self.selectedItems(user_only=True)
                if getattr(item, 'TYPE', None) == 'text']

    def selected_draw_items(self):
        """The currently selected sketches, lines, curves and arrows."""

        return [item for item in self.selectedItems(user_only=True)
                if getattr(item, 'TYPE', None) == 'draw']

    def has_sizeable_selection(self):
        """Whether anything selected can be made bigger or smaller.

        Text scales its letters, drawings their line thickness; both are
        driven by the same pair of shortcuts.
        """

        return bool(self.selected_text_items() or self.selected_draw_items())

    def has_single_image_selection(self):
        """Checks whether the current selection is a single image."""

        if self.has_single_selection():
            return self.selectedItems(user_only=True)[0].is_image
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # Right-click invokes the context menu on the
            # GraphicsView. We don't need it here.
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.event_start = event.scenePos()
            item_at_pos = self.itemAt(
                event.scenePos(), self.views()[0].transform())

            if self.edit_item:
                if item_at_pos != self.edit_item:
                    self.edit_item.exit_edit_mode()
                else:
                    super().mousePressEvent(event)
                    return
            if self.crop_item:
                if item_at_pos != self.crop_item:
                    self.cancel_crop_mode()
                else:
                    super().mousePressEvent(event)
                    return
            if self.active_group is not None:
                # Clicking outside the active group makes it behave
                # like a single object again
                if (item_at_pos is None
                        or not (item_at_pos is self.active_group
                                or self.active_group.isAncestorOf(
                                    item_at_pos))):
                    self.exit_group()
            if item_at_pos:
                self.active_mode = self.MOVE_MODE
            elif self.items():
                self.active_mode = self.RUBBERBAND_MODE

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.cancel_active_modes()
        item = self.itemAt(event.scenePos(), self.views()[0].transform())
        if item:
            group = self.get_group_ancestor(item)
            if group is not None and group is not self.active_group:
                if group.locked:
                    # A locked group stays closed, so treat the click as
                    # one on the group itself
                    item = group
                else:
                    # Double-clicking an item inside a group selects that
                    # item so that it can be moved and scaled on its own.
                    # Double-clicking it again edits it, as usual.
                    self.enter_group(group, item)
                    return
            if not item.isSelected():
                item.setSelected(True)
            if item.is_editable:
                item.enter_edit_mode()
                self.mousePressEvent(event)
            else:
                self.views()[0].fit_rect(
                    self.itemsBoundingRect(items=[item]),
                    toggle_item=item)
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self.active_mode == self.RUBBERBAND_MODE:
            if not self.rubberband_item.scene():
                logger.debug('Activating rubberband selection')
                self.addItem(self.rubberband_item)
                self.rubberband_item.bring_to_front()
            self.rubberband_item.fit(self.event_start, event.scenePos())
            self.setSelectionArea(self.rubberband_item.shape())
            self.views()[0].reset_previous_transform()
        if self.active_mode == self.MOVE_MODE:
            items = self.selectedItems(user_only=True)
            self.raise_dragged_items(items)
            self.update_drop_target(
                items,
                detach=bool(event.modifiers()
                            & Qt.KeyboardModifier.AltModifier))
        super().mouseMoveEvent(event)

    def raise_dragged_items(self, items):
        """Draw the items being dragged on top of the others.

        The original z values are put back once the drag is over.
        """

        if self.dragged_z or not items:
            return
        self.dragged_z = [(item, item.zValue()) for item in items]
        for i, item in enumerate(items):
            item.setZValue(self.max_z + (i + 1) * self.Z_STEP)

    def reset_dragged_items(self):
        for item, z in self.dragged_z:
            if item.scene() is self:
                item.setZValue(z)
        self.dragged_z = []

    def update_drop_target(self, items, detach=False):
        """Highlight the group that the dragged items would land in."""

        target = None
        if not detach:
            for item in items:
                group = self.get_drop_group(item)
                if group is not None and group is not (
                        self.get_group_ancestor(item)):
                    target = group
                    break
        if target is self.drop_target:
            return
        for group in self.items_by_type('group'):
            group.drop_target = group is target
        self.drop_target = target

    def clear_drop_target(self):
        self.update_drop_target([])

    def mouseReleaseEvent(self, event):
        if self.active_mode == self.RUBBERBAND_MODE:
            self.end_rubberband_mode()
        self.reset_dragged_items()
        self.clear_drop_target()
        if (self.active_mode == self.MOVE_MODE
                and self.has_selection()
                and self.multi_select_item.active_mode is None
                and self.selectedItems()[0].active_mode is None):
            delta = event.scenePos() - self.event_start
            if not delta.isNull():
                self.undo_stack.beginMacro('Move items')
                self.undo_stack.push(
                    commands.MoveItemsBy(self.selectedItems(),
                                         delta,
                                         ignore_first_redo=True))
                self.update_group_membership(
                    self.selectedItems(user_only=True),
                    detach=bool(event.modifiers()
                                & Qt.KeyboardModifier.AltModifier))
                self.undo_stack.endMacro()
        self.active_mode = None
        super().mouseReleaseEvent(event)

    def selectedItems(self, user_only=False):
        """If ``user_only`` is set to ``True``, only return items added
        by the user (i.e. no multi select outlines and other UI items).

        User items are items that have a ``save_id`` attribute.
        """

        items = super().selectedItems()
        if user_only:
            return list(filter(lambda i: hasattr(i, 'save_id'), items))
        return items

    def items_by_type(self, itype):
        """Returns all items of the given type."""

        return filter(lambda i: getattr(i, 'TYPE', None) == itype,
                      self.items())

    def items_for_save(self):

        """Returns the items that are to be saved.

        Items to be saved are items that have a save_id attribute.
        """

        items = filter(lambda i: hasattr(i, 'save_id'),
                       self.items(order=Qt.SortOrder.AscendingOrder))

        def depth(item):
            value = 0
            parent = item.parentItem()
            while parent is not None:
                value += 1
                parent = parent.parentItem()
            return value

        # Groups have to be saved before the items inside them, so that
        # those items can refer to the group's save id. Sorting by depth
        # handles groups within groups too, and keeps the z ordering
        # within each level.
        return sorted(items, key=depth)

    def clear_save_ids(self):
        for item in self.items_for_save():
            item.save_id = None

    def on_view_scale_change(self):
        for item in self.selectedItems():
            item.on_view_scale_change()

    def itemsBoundingRect(self, selection_only=False, items=None):
        """Returns the bounding rect of the scene's items; either all of them
        or only selected ones, or the items givin in ``items``.

        Re-implemented to not include the items's selection handles.
        """

        def filter_user_items(ilist):
            return list(filter(lambda i: hasattr(i, 'save_id'), ilist))

        if selection_only:
            base = filter_user_items(self.selectedItems())
        elif items:
            base = items
        else:
            base = filter_user_items(self.items())

        if not base:
            return QtCore.QRectF(0, 0, 0, 0)

        x = []
        y = []

        for item in base:
            for corner in item.corners_scene_coords:
                x.append(corner.x())
                y.append(corner.y())

        return QtCore.QRectF(
            QtCore.QPointF(min(x), min(y)),
            QtCore.QPointF(max(x), max(y)))

    def get_selection_center(self):
        rect = self.itemsBoundingRect(selection_only=True)
        return (rect.topLeft() + rect.bottomRight()) / 2

    def on_selection_change(self):
        if self._clear_ongoing:
            # Ignore events while clearing the scene since the
            # multiselect item will get cleared, too
            return
        if self.has_multi_selection():
            self.multi_select_item.fit_selection_area(
                self.itemsBoundingRect(selection_only=True))
        if self.has_multi_selection() and not self.multi_select_item.scene():
            self.addItem(self.multi_select_item)
            self.multi_select_item.bring_to_front()
        if not self.has_multi_selection() and self.multi_select_item.scene():
            self.removeItem(self.multi_select_item)

    def on_change(self, region):
        if self._clear_ongoing:
            # Ignore events while clearing the scene since the
            # multiselect item will get cleared, too
            return
        if (self.multi_select_item.scene()
                and self.multi_select_item.active_mode is None):
            self.multi_select_item.fit_selection_area(
                self.itemsBoundingRect(selection_only=True))

    def add_item_later(self, itemdata, selected=False):
        """Keep an item for adding later via ``add_queued_items``

        :param dict itemdata: Defines the item's data
        :param bool selected: Whether the item is initialised as selected
        """

        self.items_to_add.put((itemdata, selected))

    def add_queued_items(self):
        """Adds items added via ``add_item_later``"""

        grouped = []

        while not self.items_to_add.empty():
            data, selected = self.items_to_add.get()
            typ = data.pop('type')
            cls = item_registry.get(typ)
            if not cls:
                # Just in case we add new item types in future versions
                logger.warning(f'Encountered item of unknown type: {typ}')
                cls = BeeErrorItem
                data['data'] = {'text': f'Item of unknown type: {typ}'}
            item = cls.create_from_data(**data)
            # Set the values common to all item types:
            item.update_from_data(**data)
            self.addItem(item)
            # Force recalculation of min/max z values:
            item.setZValue(item.zValue())
            if selected:
                item.setSelected(True)
                item.bring_to_front()
            parent_group = data.get('data', {}).get('parent_group')
            if parent_group is not None:
                grouped.append((item, parent_group))

        self.restore_groups(grouped)

    def restore_groups(self, grouped):
        """Puts loaded items back into their groups.

        ``grouped`` is a list of (item, group save id) tuples. Positions
        are stored relative to the group, so they can be kept as they
        are once the item is re-parented.
        """

        if not grouped:
            return

        groups = {item.save_id: item
                  for item in self.items_by_type('group')}
        for item, parent_group in grouped:
            group = groups.get(parent_group)
            if group is None:
                logger.warning(f'Group {parent_group} not found for {item}')
                continue
            pos = item.pos()
            item.setParentItem(group)
            item.setPos(pos)

        # Innermost groups first: an outer group's box can only be
        # sized once the groups inside it know their own size
        for group in sorted(groups.values(),
                            key=lambda g: len(self.group_chain(g)),
                            reverse=True):
            group.fit_to_children()
            group.set_children_interactive(False)
