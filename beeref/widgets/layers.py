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

"""A panel listing the scene's items in stacking order."""

import logging

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from beeref import commands


logger = logging.getLogger(__name__)

ITEM_ROLE = Qt.ItemDataRole.UserRole

# Qt's "no maximum", for undoing a fixed height
QWIDGETSIZE_MAX = (1 << 24) - 1


class LayersTree(QtWidgets.QTreeWidget):
    """The tree of items shown in the layers panel."""

    def __init__(self, parent, view):
        super().__init__(parent)
        self.view = view
        self.scene = view.scene
        self.setHeaderHidden(True)
        self.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(
            QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked
            | QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed)

        # Guards against reacting to changes we made ourselves
        self.updating = False
        self.signature = None

        self.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.itemChanged.connect(self.on_tree_item_changed)
        self.scene.changed.connect(self.schedule_refresh)
        self.scene.selectionChanged.connect(self.update_selection)
        self.refresh_pending = False

    # Building the tree

    def get_items(self, parent=None):
        """The items to list under the given parent, topmost first."""

        if parent is None:
            items = [item for item in self.scene.items()
                     if hasattr(item, 'save_id') and item.parentItem() is None]
        else:
            items = parent.bee_children()
        return sorted(items, key=lambda item: item.zValue(), reverse=True)

    def get_signature(self):
        """A cheap summary of what the tree should show.

        Rebuilding on every scene change would be wasteful, so the tree
        is only rebuilt when this changes.
        """

        def describe(items, depth=0):
            for item in items:
                yield (id(item), depth, item.zValue(),
                       item.get_display_name())
                if getattr(item, 'TYPE', None) == 'group':
                    yield from describe(self.get_items(item), depth + 1)

        return tuple(describe(self.get_items()))

    def schedule_refresh(self, *args):
        """Refresh once the current batch of scene changes is done."""

        if self.refresh_pending:
            return
        self.refresh_pending = True
        QtCore.QTimer.singleShot(0, self.refresh)

    def refresh(self):
        self.refresh_pending = False
        signature = self.get_signature()
        if signature == self.signature:
            return
        self.signature = signature
        logger.trace('Rebuilding layers tree')

        expanded = self.get_expanded_items()
        self.updating = True
        self.clear()
        self.build_items(self, self.get_items(), expanded)
        self.updating = False
        self.update_selection()

    def get_expanded_items(self):
        """The scene items whose groups are currently expanded."""

        expanded = set()
        iterator = QtWidgets.QTreeWidgetItemIterator(self)
        while iterator.value():
            entry = iterator.value()
            if entry.isExpanded():
                expanded.add(id(entry.data(0, ITEM_ROLE)))
            iterator += 1
        return expanded

    def build_items(self, parent, items, expanded):
        for item in items:
            entry = QtWidgets.QTreeWidgetItem(parent)
            entry.setText(0, item.get_display_name())
            entry.setData(0, ITEM_ROLE, item)
            entry.setFlags(entry.flags()
                           | Qt.ItemFlag.ItemIsEditable
                           | Qt.ItemFlag.ItemIsDragEnabled)
            if getattr(item, 'TYPE', None) == 'group':
                entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsDropEnabled)
                self.build_items(entry, self.get_items(item), expanded)
                entry.setExpanded(id(item) in expanded)
            else:
                entry.setFlags(entry.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)

    # Keeping selection in sync

    def update_selection(self):
        """Show the canvas selection in the tree."""

        if self.updating:
            return
        selected = set(id(item)
                       for item in self.scene.selectedItems(user_only=True))
        self.updating = True
        iterator = QtWidgets.QTreeWidgetItemIterator(self)
        while iterator.value():
            entry = iterator.value()
            entry.setSelected(id(entry.data(0, ITEM_ROLE)) in selected)
            iterator += 1
        self.updating = False

    def on_tree_selection_changed(self):
        """Apply the tree selection to the canvas."""

        if self.updating:
            return
        items = [entry.data(0, ITEM_ROLE) for entry in self.selectedItems()]
        items = [item for item in items if item is not None]
        self.updating = True
        self.scene.deselect_all_items()
        for item in items:
            group = self.scene.get_group_ancestor(item)
            if group is not None:
                # Items inside a group can only be selected on the
                # canvas while the group is open
                self.scene.enter_group(group)
            item.setSelected(True)
        self.updating = False

    def on_tree_item_changed(self, entry, column):
        """Rename the item when its entry is edited."""

        if self.updating:
            return
        item = entry.data(0, ITEM_ROLE)
        if item is None:
            return
        name = entry.text(0).strip()
        if name == item.get_display_name():
            return
        self.view.undo_stack.push(commands.RenameItem(item, name))
        self.schedule_refresh()

    # Reordering by dragging

    def dropEvent(self, event):
        target = self.itemAt(event.position().toPoint())
        dragged = [entry.data(0, ITEM_ROLE) for entry in self.selectedItems()]
        dragged = [item for item in dragged if item is not None]
        super().dropEvent(event)
        self.apply_order(dragged, target)

    def get_plan(self, entry=None, group=None):
        """Where the tree says each item should end up.

        Yields (item, group, z) for every entry, walking into groups so
        that items inside them are ordered too.
        """

        if entry is None:
            count = self.topLevelItemCount()
            children = [self.topLevelItem(i) for i in range(count)]
        else:
            children = [entry.child(i) for i in range(entry.childCount())]

        step = self.scene.Z_STEP
        for index, child in enumerate(children):
            item = child.data(0, ITEM_ROLE)
            if item is None:
                continue
            # The tree lists the topmost item first
            yield (item, group, (len(children) - 1 - index) * step)
            if getattr(item, 'TYPE', None) == 'group':
                yield from self.get_plan(child, item)

    def apply_order(self, dragged, target):
        """Write the tree order back to the items.

        Entries moved into or out of a group node change the item's
        group as well as its z value.
        """

        plan = list(self.get_plan())
        if not plan:
            return

        moves = []
        for item, group, z in plan:
            current = self.scene.get_group_ancestor(item)
            if current is group:
                continue
            if group is not None and item.isAncestorOf(group):
                # Refuse to put a group inside itself
                continue
            moves.append((item, group))

        self.view.undo_stack.beginMacro('Reorder items')
        for item, group in moves:
            self.view.undo_stack.push(
                commands.MoveToGroup(self.scene, [item], group))
        items = [item for item, group, z in plan]
        self.view.undo_stack.push(
            commands.ReorderItems(items, [z for item, group, z in plan]))
        self.view.undo_stack.endMacro()

        self.signature = None
        self.schedule_refresh()


class LayersTitleBar(QtWidgets.QWidget):
    """Title bar with buttons for collapsing and closing the panel."""

    def __init__(self, dock):
        super().__init__(dock)
        self.dock = dock

        self.collapse_button = QtWidgets.QToolButton(self)
        self.collapse_button.setAutoRaise(True)
        self.collapse_button.setToolTip('Collapse')
        self.collapse_button.clicked.connect(self.dock.toggle_collapsed)

        close_button = QtWidgets.QToolButton(self)
        close_button.setAutoRaise(True)
        close_button.setToolTip('Close')
        close_button.setIcon(self.style().standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close_button.clicked.connect(self.dock.close)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self.collapse_button)
        layout.addWidget(QtWidgets.QLabel(dock.windowTitle(), self))
        layout.addStretch(100)
        layout.addWidget(close_button)
        self.setLayout(layout)
        self.update_collapse_button(False)

    def update_collapse_button(self, collapsed):
        self.collapse_button.setArrowType(
            Qt.ArrowType.RightArrow if collapsed else Qt.ArrowType.DownArrow)
        self.collapse_button.setToolTip('Expand' if collapsed else 'Collapse')


class LayersDock(QtWidgets.QDockWidget):
    """The dockable panel holding the layers tree."""

    def __init__(self, parent, view):
        super().__init__('Layers', parent)
        self.view = view
        self.setObjectName('LayersDock')
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)
        self.tree = LayersTree(self, view)
        self.setWidget(self.tree)
        self.collapsed = False
        self.titlebar = LayersTitleBar(self)
        self.setTitleBarWidget(self.titlebar)
        parent.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self)
        self.hide()

    def toggle_collapsed(self):
        self.set_collapsed(not self.collapsed)

    def set_collapsed(self, value):
        """Shrink the panel to just its title bar, or restore it."""

        logger.debug(f'Collapsing layers panel: {value}')
        self.collapsed = value
        self.tree.setVisible(not value)
        self.titlebar.update_collapse_button(value)
        if value:
            self.setFixedHeight(self.titlebar.sizeHint().height())
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(QWIDGETSIZE_MAX)

    def closeEvent(self, event):
        # Keep the menu entry in step when closed via the title bar
        self.view.on_layers_dock_closed()
        super().closeEvent(event)
