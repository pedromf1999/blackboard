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

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref import commands
from beeref.utils import readable_grey


logger = logging.getLogger(__name__)

ITEM_ROLE = Qt.ItemDataRole.UserRole

# Qt's "no maximum", for undoing a fixed height
QWIDGETSIZE_MAX = (1 << 24) - 1


class LayersDelegate(QtWidgets.QStyledItemDelegate):
    """Draws entries in their own colours, never as selected.

    The entries are painted here rather than by the platform's style,
    which paints selected rows and their text in its own colours and
    would override the colour each item is meant to have. Selection is
    shown by the marker in front of the name instead.
    """

    # Space around the marker and the name
    PADDING = 4

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # Belt and braces: nothing should paint these anyway
        option.state &= ~QtWidgets.QStyle.StateFlag.State_Selected
        option.state &= ~QtWidgets.QStyle.StateFlag.State_MouseOver

    def paint(self, painter, option, index):
        option = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(option, index)

        background = index.data(Qt.ItemDataRole.BackgroundRole)
        if background is None:
            text_color = option.palette.text().color()
        else:
            text_color = readable_grey(background.color())

        painter.save()
        if background is not None:
            painter.fillRect(option.rect, background)

        rect = option.rect.adjusted(self.PADDING, 0, -self.PADDING, 0)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon is not None and not icon.isNull():
            size = option.decorationSize
            icon.paint(painter, QtCore.QRect(
                rect.left(),
                option.rect.center().y() - size.height() // 2 + 1,
                size.width(), size.height()))
            rect.setLeft(rect.left() + size.width() + self.PADDING)

        painter.setPen(text_color)
        painter.setFont(option.font)
        painter.drawText(
            rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            option.fontMetrics.elidedText(
                index.data(Qt.ItemDataRole.DisplayRole) or '',
                Qt.TextElideMode.ElideRight, rect.width()))
        painter.restore()


class LayersTree(QtWidgets.QTreeWidget):
    """The tree of items shown in the layers panel."""

    # Size of the circle marking whether an item is selected
    MARKER_SIZE = 14

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
        self.setItemDelegate(LayersDelegate(self))

        # Guards against reacting to changes we made ourselves
        self.updating = False
        self.signature = None

        self.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.itemChanged.connect(self.on_tree_item_changed)
        self.scene.changed.connect(self.schedule_refresh)
        self.scene.selectionChanged.connect(self.update_selection)
        self.refresh_pending = False

    def drawRow(self, painter, option, index):
        """Draw rows as if nothing were selected.

        The row background and the expand arrow are painted by the view
        rather than the delegate, and on some platforms the style paints
        a selected row in its own colour, which would cover the item's.
        """

        option = QtWidgets.QStyleOptionViewItem(option)
        option.state &= ~QtWidgets.QStyle.StateFlag.State_Selected
        option.state &= ~QtWidgets.QStyle.StateFlag.State_MouseOver
        super().drawRow(painter, option, index)

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
                box_color = getattr(item, 'box_color', None)
                yield (id(item), depth, item.zValue(),
                       item.get_display_name(),
                       # So the dates shown for groups stay current
                       getattr(item, 'modified', None),
                       # ... and so does the colour of the entry
                       box_color.name() if box_color else None)
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
            if hasattr(item, 'get_details'):
                entry.setToolTip(0, item.get_details())
            entry.setFlags(entry.flags()
                           | Qt.ItemFlag.ItemIsEditable
                           | Qt.ItemFlag.ItemIsDragEnabled)
            self.set_entry_colors(entry, item)
            self.set_entry_marker(entry, item)
            if getattr(item, 'TYPE', None) == 'group':
                entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsDropEnabled)
                self.build_items(entry, self.get_items(item), expanded)
                entry.setExpanded(id(item) in expanded)
            else:
                entry.setFlags(entry.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)

    def marker_icon(self, color, selected):
        """A filled circle for a selected item, an outline for the rest."""

        size = self.MARKER_SIZE
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QtGui.QBrush(color) if selected
                         else QtGui.QBrush(Qt.BrushStyle.NoBrush))
        inset = 3
        painter.drawEllipse(inset, inset,
                            size - 2 * inset, size - 2 * inset)
        painter.end()
        return QtGui.QIcon(pixmap)

    def set_entry_marker(self, entry, item):
        """Show whether the item is selected on the canvas."""

        background = entry.background(0)
        if background.style() == Qt.BrushStyle.NoBrush:
            color = self.palette().text().color()
        else:
            color = readable_grey(background.color())
        entry.setIcon(0, self.marker_icon(color, item.isSelected()))

    def set_entry_colors(self, entry, item):
        """Show the item's own box colour on its entry.

        Groups and text items both have a coloured box, so the panel
        shows the same colours that are on the canvas.
        """

        if not hasattr(item, 'box_color'):
            return
        # Translucent boxes show the canvas through them, so use the
        # colour they actually appear as
        if hasattr(item, 'visible_box_color'):
            color = item.visible_box_color()
        else:
            color = item.box_color
        entry.setBackground(0, QtGui.QBrush(color))
        # Keep the name readable whatever colour has been chosen
        entry.setForeground(0, QtGui.QBrush(readable_grey(color)))

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
            item = entry.data(0, ITEM_ROLE)
            entry.setSelected(id(item) in selected)
            if item is not None:
                self.set_entry_marker(entry, item)
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
    """Title bar for the layers panel: an arrow, and a name beside it.

    There is no close button. Collapsing leaves nothing but the arrow,
    which is a small enough thing to leave on screen that being able to
    banish it altogether would only be a way to lose it.
    """

    def __init__(self, dock):
        super().__init__(dock)
        self.dock = dock

        self.collapse_button = QtWidgets.QToolButton(self)
        self.collapse_button.setAutoRaise(True)
        self.collapse_button.clicked.connect(self.dock.toggle_collapsed)

        self.label = QtWidgets.QLabel(dock.windowTitle(), self)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self.collapse_button)
        layout.addWidget(self.label)
        layout.addStretch(100)
        self.setLayout(layout)
        self.update_collapse_button(False)

    def update_collapse_button(self, collapsed):
        # Collapsed, the arrow points into the canvas, which is the way
        # the panel opens. Expanded it points down, over what it opened.
        self.collapse_button.setArrowType(
            Qt.ArrowType.LeftArrow if collapsed else Qt.ArrowType.DownArrow)
        self.collapse_button.setToolTip('Expand' if collapsed else 'Collapse')
        self.label.setVisible(not collapsed)


class LayersDock(QtWidgets.QDockWidget):
    """The dockable panel holding the layers tree.

    Always on screen, and either collapsed to a narrow strip carrying
    just its arrow, or open. It cannot be closed: collapsed it costs
    almost no room, so closing would only be a way of losing it.
    """

    # What to open at when there is no earlier width to go back to.
    DEFAULT_WIDTH = 240

    def __init__(self, parent, view):
        super().__init__('Layers', parent)
        self.view = view
        self.main_window = parent
        self.setObjectName('LayersDock')
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)
        # Movable, but not closable: the strip is the way to put it away
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.tree = LayersTree(self, view)
        self.setWidget(self.tree)
        self.collapsed = False
        self.expanded_width = self.DEFAULT_WIDTH
        self.titlebar = LayersTitleBar(self)
        self.setTitleBarWidget(self.titlebar)
        parent.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self)
        self.set_collapsed(True)

    def toggle_collapsed(self):
        self.set_collapsed(not self.collapsed)

    def collapsed_width(self):
        """How wide the strip is: the arrow, and nothing else."""

        return self.titlebar.sizeHint().width()

    def set_collapsed(self, value):
        """Shrink the panel to a strip holding its arrow, or open it.

        Collapsing takes the width away, not the height. The panel is
        docked down one side, so leaving the width behind left a tall
        empty column taking up the room the canvas wants.
        """

        logger.debug(f'Collapsing layers panel: {value}')
        if value and not self.collapsed:
            # Come back to the width it was dragged to
            self.expanded_width = max(self.width(), self.DEFAULT_WIDTH)
        self.collapsed = value
        self.tree.setVisible(not value)
        self.titlebar.update_collapse_button(value)
        if value:
            self.setFixedWidth(self.collapsed_width())
        else:
            self.setMinimumWidth(0)
            self.setMaximumWidth(QWIDGETSIZE_MAX)
            self.main_window.resizeDocks(
                [self], [self.expanded_width], Qt.Orientation.Horizontal)
