import os.path

from beeref.actions.actions import actions
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref import commands
from beeref.utils import contrast_ratio, relative_luminance
from beeref.items import BeeGroupItem, BeePixmapItem, BeeTextItem


ITEM_ROLE = Qt.ItemDataRole.UserRole


def ratio_against(color, background):
    return contrast_ratio(relative_luminance(color),
                          relative_luminance(background))


def add_text(view, text, z):
    item = BeeTextItem(text)
    view.scene.addItem(item)
    item.setZValue(z)
    return item


def tree_of(view):
    tree = view.layers_dock.tree
    tree.refresh()
    return tree


def entries(tree):
    """The tree contents as (depth, label) tuples."""

    result = []
    iterator = QtWidgets.QTreeWidgetItemIterator(tree)
    while iterator.value():
        entry = iterator.value()
        depth = 0
        parent = entry.parent()
        while parent is not None:
            depth += 1
            parent = parent.parent()
        result.append((depth, entry.text(0)))
        iterator += 1
    return result


def open_layers(view):
    """Open the panel the way the application does, through the menu."""

    actions['show_layers'].qaction.setChecked(True)


def test_dock_starts_collapsed(view):
    """On screen from the start, but only as its strip."""

    dock = view.layers_dock
    assert dock.collapsed is True
    assert dock.tree.isVisible() is False


def test_dock_cannot_be_closed(view):
    """Collapsed it costs almost nothing, so closing would only lose it."""

    features = view.layers_dock.features()
    closable = QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
    assert bool(features & closable) is False


def test_dock_can_be_collapsed(view):
    open_layers(view)
    dock = view.layers_dock
    assert dock.collapsed is False

    dock.toggle_collapsed()
    assert dock.collapsed is True
    # The panel leaves the window entirely. A dock widget fills the
    # height of the side it is docked to, so shrinking it could only
    # leave a full height strip standing there for no reason.
    assert dock.isVisible() is False


def test_handle_stands_in_for_the_collapsed_panel(view):
    """Put away, the panel leaves one small square behind."""

    view.on_action_show_layers(False)
    handle = view.layers_handle
    assert handle.isVisible() is True
    assert handle.width() == handle.SIZE
    assert handle.height() == handle.SIZE

    view.on_action_show_layers(True)
    assert handle.isVisible() is False


def test_handle_sits_on_the_side_the_panel_docks_to(view):
    view.on_action_show_layers(False)
    handle = view.layers_handle

    handle.set_side(Qt.DockWidgetArea.RightDockWidgetArea)
    handle.reposition()
    assert handle.x() > view.width() / 2
    assert handle.arrowType() == Qt.ArrowType.LeftArrow

    handle.set_side(Qt.DockWidgetArea.LeftDockWidgetArea)
    handle.reposition()
    assert handle.x() < view.width() / 2
    assert handle.arrowType() == Qt.ArrowType.RightArrow


def test_dock_can_be_expanded_again(view):
    open_layers(view)
    dock = view.layers_dock
    dock.toggle_collapsed()
    dock.toggle_collapsed()
    assert dock.collapsed is False
    assert dock.tree.isVisible() is True
    assert dock.isVisible() is True


def test_collapsing_from_the_arrow_keeps_the_menu_in_step(view):
    """The panel, the menu entry and the stored setting are one thing."""

    qaction = actions['show_layers'].qaction
    open_layers(view)

    view.layers_dock.toggle_collapsed()
    assert view.layers_dock.collapsed is True
    assert qaction.isChecked() is False


def test_shortcut_opens_and_collapses(view):
    """Ctrl+J opens it fully, and puts it away again."""

    dock = view.layers_dock
    view.on_action_show_layers(True)
    assert dock.collapsed is False
    assert dock.tree.isVisible() is True

    view.on_action_show_layers(False)
    assert dock.collapsed is True
    assert dock.tree.isVisible() is False


def test_collapse_button_arrow_follows_state(view):
    dock = view.layers_dock
    open_layers(view)
    button = dock.titlebar.collapse_button
    assert button.arrowType() == Qt.ArrowType.DownArrow
    dock.toggle_collapsed()
    assert button.arrowType() == Qt.ArrowType.LeftArrow


def test_lists_items_topmost_first(view):
    add_text(view, 'bottom', 0)
    add_text(view, 'middle', 1)
    add_text(view, 'top', 2)
    tree = tree_of(view)
    assert entries(tree) == [(0, 'top'), (0, 'middle'), (0, 'bottom')]


def test_group_entry_uses_the_group_colour(view):
    item = add_text(view, 'one', 0)
    group = BeeGroupItem(box_color=(150, 60, 60, 255))
    commands.GroupItems(view.scene, [item], group).redo()
    tree = tree_of(view)

    entry = tree.topLevelItem(0)
    assert entry.background(0).color() == QtGui.QColor(150, 60, 60, 255)


def test_group_entry_text_stays_readable(view):
    item = add_text(view, 'one', 0)
    group = BeeGroupItem(box_color=(240, 220, 120, 255))
    commands.GroupItems(view.scene, [item], group).redo()
    tree = tree_of(view)

    # A light group gets dark text
    on_light = tree.topLevelItem(0).foreground(0).color()
    assert on_light.lightness() < 127
    assert ratio_against(on_light, group.box_color) >= 8

    group.box_color = QtGui.QColor(40, 40, 60, 255)
    tree.refresh()
    # ... and a dark one gets light text
    on_dark = tree.topLevelItem(0).foreground(0).color()
    assert on_dark.lightness() > 127
    assert ratio_against(on_dark, group.box_color) >= 8


def test_group_entry_colour_follows_changes(view):
    item = add_text(view, 'one', 0)
    group = BeeGroupItem()
    commands.GroupItems(view.scene, [item], group).redo()
    tree = tree_of(view)

    group.box_color = QtGui.QColor(10, 120, 30, 255)
    tree.refresh()
    assert tree.topLevelItem(0).background(0).color() == QtGui.QColor(
        10, 120, 30, 255)


def style_option(tree, row, selected=False):
    """What the delegate would paint for the given row."""

    index = tree.indexFromItem(tree.topLevelItem(row))
    option = QtWidgets.QStyleOptionViewItem()
    option.initFrom(tree)
    if selected:
        option.state |= QtWidgets.QStyle.StateFlag.State_Selected
    tree.itemDelegate().initStyleOption(option, index)
    return option


def paint_row(tree, row, selected=False):
    """Paint an entry and hand back the pixels.

    Checking the colours stored on the entry isn't enough: the platform
    style can paint something else entirely.
    """

    width, height = 220, 20
    pixmap = QtGui.QPixmap(width, height)
    # A colour that is never used, so anything left over is visible
    pixmap.fill(QtGui.QColor(0, 255, 0))
    painter = QtGui.QPainter(pixmap)
    option = QtWidgets.QStyleOptionViewItem()
    option.initFrom(tree)
    option.rect = QtCore.QRect(0, 0, width, height)
    option.decorationSize = QtCore.QSize(tree.MARKER_SIZE, tree.MARKER_SIZE)
    if selected:
        option.state |= QtWidgets.QStyle.StateFlag.State_Selected
    index = tree.indexFromItem(tree.topLevelItem(row))
    tree.itemDelegate().paint(painter, option, index)
    painter.end()
    return pixmap.toImage()


def painted_colors(image):
    return [image.pixelColor(x, y)
            for x in range(image.width())
            for y in range(image.height())]


def test_name_is_painted_dark_on_a_light_row(view):
    item = add_text(view, 'my note', 0)
    item.box_color = QtGui.QColor(250, 230, 90, 255)
    tree = tree_of(view)

    colors = painted_colors(paint_row(tree, 0))
    assert min(c.lightness() for c in colors) < 60


def test_name_is_painted_light_on_a_dark_row(view):
    item = add_text(view, 'my note', 0)
    item.box_color = QtGui.QColor(20, 20, 20, 255)
    tree = tree_of(view)

    colors = painted_colors(paint_row(tree, 0))
    assert max(c.lightness() for c in colors) > 200


def test_row_is_painted_in_its_own_colour(view):
    item = add_text(view, 'my note', 0)
    item.box_color = QtGui.QColor(250, 230, 90, 255)
    tree = tree_of(view)

    image = paint_row(tree, 0)
    # The far right of the row is past the name, so it shows the box
    assert image.pixelColor(image.width() - 3, 10) == QtGui.QColor(
        250, 230, 90)


def test_selected_row_is_painted_the_same(view):
    item = add_text(view, 'my note', 0)
    item.box_color = QtGui.QColor(250, 230, 90, 255)
    tree = tree_of(view)

    normal = paint_row(tree, 0, selected=False)
    chosen = paint_row(tree, 0, selected=True)
    assert normal.pixelColor(normal.width() - 3, 10) == chosen.pixelColor(
        chosen.width() - 3, 10)


def test_selection_is_never_painted(view):
    """The row must not be drawn as selected, whatever the style does."""

    item = add_text(view, 'one', 0)
    group = BeeGroupItem(box_color=(255, 255, 255, 255))
    commands.GroupItems(view.scene, [item], group).redo()
    tree = tree_of(view)

    option = style_option(tree, 0, selected=True)
    assert not (option.state & QtWidgets.QStyle.StateFlag.State_Selected)


def test_hover_is_never_painted(view):
    add_text(view, 'one', 0)
    tree = tree_of(view)

    index = tree.indexFromItem(tree.topLevelItem(0))
    option = QtWidgets.QStyleOptionViewItem()
    option.initFrom(tree)
    option.state |= QtWidgets.QStyle.StateFlag.State_MouseOver
    tree.itemDelegate().initStyleOption(option, index)
    assert not (option.state & QtWidgets.QStyle.StateFlag.State_MouseOver)


def test_selected_row_keeps_its_text_colour(view):
    """A selected light row still gets dark text."""

    item = add_text(view, 'one', 0)
    group = BeeGroupItem(box_color=(255, 255, 255, 255))
    commands.GroupItems(view.scene, [item], group).redo()
    tree = tree_of(view)

    option = style_option(tree, 0, selected=True)
    assert option.palette.text().color() == QtGui.QColor(0, 0, 0)


def test_selected_dark_row_keeps_light_text(view):
    item = add_text(view, 'one', 0)
    group = BeeGroupItem(box_color=(30, 30, 40, 255))
    commands.GroupItems(view.scene, [item], group).redo()
    tree = tree_of(view)

    option = style_option(tree, 0, selected=True)
    assert option.palette.text().color() == QtGui.QColor(255, 255, 255)


def test_rows_without_a_colour_keep_the_usual_text(view):
    item = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(item)
    tree = tree_of(view)
    option = style_option(tree, 0, selected=True)
    assert option.palette.text().color() == view.palette().text().color()


def marker_of(tree, row):
    icon = tree.topLevelItem(row).icon(0)
    return icon.pixmap(tree.MARKER_SIZE, tree.MARKER_SIZE).toImage()


def filled_pixels(image):
    """How much of the marker is painted, to tell a disc from a ring."""

    return sum(1 for x in range(image.width())
               for y in range(image.height())
               if image.pixelColor(x, y).alpha() > 0)


def test_every_entry_has_a_marker(view):
    add_text(view, 'one', 0)
    tree = tree_of(view)
    assert not tree.topLevelItem(0).icon(0).isNull()


def test_selected_marker_is_filled(view):
    item = add_text(view, 'one', 0)
    tree = tree_of(view)
    empty = filled_pixels(marker_of(tree, 0))

    item.setSelected(True)
    tree.update_selection()
    full = filled_pixels(marker_of(tree, 0))
    # The filled disc covers more than the outline ring
    assert full > empty


def test_marker_follows_canvas_selection(view):
    item = add_text(view, 'one', 0)
    tree = tree_of(view)

    item.setSelected(True)
    tree.update_selection()
    selected = filled_pixels(marker_of(tree, 0))

    item.setSelected(False)
    tree.update_selection()
    assert filled_pixels(marker_of(tree, 0)) < selected


def test_white_group_gets_black_text(view):
    item = add_text(view, 'one', 0)
    group = BeeGroupItem(box_color=(255, 255, 255, 255))
    commands.GroupItems(view.scene, [item], group).redo()
    tree = tree_of(view)

    entry = tree.topLevelItem(0)
    assert entry.foreground(0).color() == QtGui.QColor(0, 0, 0)


def test_text_items_use_their_box_colour(view):
    item = add_text(view, 'loose', 0)
    item.box_color = QtGui.QColor(255, 255, 255, 255)
    tree = tree_of(view)

    entry = tree.topLevelItem(0)
    assert entry.background(0).color() == QtGui.QColor(255, 255, 255)
    assert entry.foreground(0).color() == QtGui.QColor(0, 0, 0)


def test_text_item_entry_matches_the_canvas(view):
    """The panel shows the colour the box actually appears as."""

    item = add_text(view, 'loose', 0)
    item.box_color = QtGui.QColor(200, 40, 40, 255)
    tree = tree_of(view)

    entry = tree.topLevelItem(0)
    assert entry.background(0).color() == item.visible_box_color()
    assert entry.foreground(0).color() == item.defaultTextColor()


def test_images_are_not_tinted(view):
    item = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(item)
    tree = tree_of(view)
    # An unset background brush has no style
    assert tree.topLevelItem(0).background(0).style() == Qt.BrushStyle.NoBrush


def test_group_entries_show_their_dates(view):
    item = add_text(view, 'one', 0)
    group = BeeGroupItem(created='2026-01-02T03:04:05',
                         modified='2026-02-03T04:05:06')
    commands.GroupItems(view.scene, [item], group).redo()
    tree = tree_of(view)

    tooltip = tree.topLevelItem(0).toolTip(0)
    assert 'Created: 02 Jan 2026, 03:04' in tooltip
    assert 'Last edited: 03 Feb 2026, 04:05' in tooltip


def test_group_entry_dates_are_refreshed(view):
    item = add_text(view, 'one', 0)
    group = BeeGroupItem()
    commands.GroupItems(view.scene, [item], group).redo()
    tree = tree_of(view)

    group.modified = '2026-12-25T09:30:00'
    tree.refresh()
    assert '25 Dec 2026' in tree.topLevelItem(0).toolTip(0)


def test_lists_groups_as_nodes(view):
    item1 = add_text(view, 'one', 0)
    item2 = add_text(view, 'two', 1)
    loose = add_text(view, 'loose', 5)  # noqa: F841
    group = BeeGroupItem()
    commands.GroupItems(view.scene, [item1, item2], group).redo()

    tree = tree_of(view)
    assert entries(tree) == [
        (0, 'loose'),
        (0, 'Group (2)'),
        (1, 'two'),
        (1, 'one'),
    ]


def test_uses_filename_for_images(view):
    item = BeePixmapItem(QtGui.QImage())
    item.filename = os.path.join('some', 'dir', 'photo.png')
    view.scene.addItem(item)
    tree = tree_of(view)
    assert entries(tree) == [(0, 'photo.png')]


def test_falls_back_for_images_without_filename(view):
    item = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(item)
    tree = tree_of(view)
    assert entries(tree) == [(0, 'Image')]


def test_uses_given_name(view):
    item = add_text(view, 'some text', 0)
    item.name = 'My Layer'
    tree = tree_of(view)
    assert entries(tree) == [(0, 'My Layer')]


def test_canvas_selection_shows_in_tree(view):
    item1 = add_text(view, 'one', 0)
    add_text(view, 'two', 1)
    tree = tree_of(view)

    item1.setSelected(True)
    tree.update_selection()
    selected = [e.text(0) for e in tree.selectedItems()]
    assert selected == ['one']


def test_tree_selection_applies_to_canvas(view):
    item1 = add_text(view, 'one', 0)
    item2 = add_text(view, 'two', 1)
    tree = tree_of(view)

    tree.topLevelItem(0).setSelected(True)
    tree.on_tree_selection_changed()
    assert item2.isSelected() is True
    assert item1.isSelected() is False


def test_tree_selection_of_grouped_item_opens_group(view):
    item1 = add_text(view, 'one', 0)
    item2 = add_text(view, 'two', 1)
    group = BeeGroupItem()
    commands.GroupItems(view.scene, [item1, item2], group).redo()
    tree = tree_of(view)

    group_entry = tree.topLevelItem(0)
    child = group_entry.child(0)
    child.setSelected(True)
    tree.on_tree_selection_changed()

    assert view.scene.active_group is group
    assert child.data(0, ITEM_ROLE).isSelected() is True


def test_renaming_in_tree_renames_item(view):
    item = add_text(view, 'one', 0)
    tree = tree_of(view)

    tree.topLevelItem(0).setText(0, 'Renamed')
    assert item.name == 'Renamed'
    assert len(view.undo_stack) == 1
    view.undo_stack.undo()
    assert item.name is None


def test_renaming_to_same_name_does_nothing(view):
    add_text(view, 'one', 0)
    tree = tree_of(view)

    tree.topLevelItem(0).setText(0, 'one')
    assert len(view.undo_stack) == 0


def test_refresh_skipped_when_nothing_changed(view):
    add_text(view, 'one', 0)
    tree = tree_of(view)
    entry = tree.topLevelItem(0)

    tree.refresh()
    # The same widget is kept, rather than being rebuilt
    assert tree.topLevelItem(0) is entry


def test_refresh_rebuilds_when_items_change(view):
    add_text(view, 'one', 0)
    tree = tree_of(view)
    add_text(view, 'two', 1)

    tree.refresh()
    assert len(entries(tree)) == 2


def group_of(view, tree):
    """The tree entry holding the scene's group."""

    group = list(view.scene.items_by_type('group'))[0]
    for i in range(tree.topLevelItemCount()):
        entry = tree.topLevelItem(i)
        if entry.data(0, ITEM_ROLE) is group:
            return entry, group
    raise AssertionError('group not in tree')


def test_reorder_inside_a_group(view):
    item1 = add_text(view, 'one', 0)
    item2 = add_text(view, 'two', 1)
    group = BeeGroupItem()
    commands.GroupItems(view.scene, [item1, item2], group).redo()
    tree = tree_of(view)
    group_entry, group = group_of(view, tree)

    # 'two' is listed first; move 'one' above it
    one_entry = [group_entry.child(i)
                 for i in range(group_entry.childCount())
                 if group_entry.child(i).data(0, ITEM_ROLE) is item1][0]
    group_entry.removeChild(one_entry)
    group_entry.insertChild(0, one_entry)
    tree.apply_order([item1], group_entry)

    assert item1.zValue() > item2.zValue()
    assert item1.parentItem() is group


def test_drag_item_into_a_group(view):
    item1 = add_text(view, 'one', 0)
    group = BeeGroupItem()
    commands.GroupItems(view.scene, [item1], group).redo()
    loose = add_text(view, 'loose', 5)
    tree = tree_of(view)
    group_entry, group = group_of(view, tree)

    loose_entry = [tree.topLevelItem(i)
                   for i in range(tree.topLevelItemCount())
                   if tree.topLevelItem(i).data(0, ITEM_ROLE) is loose][0]
    tree.takeTopLevelItem(tree.indexOfTopLevelItem(loose_entry))
    group_entry.insertChild(0, loose_entry)
    tree.apply_order([loose], group_entry)

    assert loose.parentItem() is group
    assert len(group.bee_children()) == 2


def test_drag_item_out_of_a_group(view):
    item1 = add_text(view, 'one', 0)
    item2 = add_text(view, 'two', 1)
    group = BeeGroupItem()
    commands.GroupItems(view.scene, [item1, item2], group).redo()
    tree = tree_of(view)
    group_entry, group = group_of(view, tree)

    one_entry = [group_entry.child(i)
                 for i in range(group_entry.childCount())
                 if group_entry.child(i).data(0, ITEM_ROLE) is item1][0]
    group_entry.removeChild(one_entry)
    tree.insertTopLevelItem(0, one_entry)
    tree.apply_order([item1], None)

    assert item1.parentItem() is None
    assert item1.scene() is view.scene
    assert len(group.bee_children()) == 1


def test_drag_into_group_can_be_undone(view):
    item1 = add_text(view, 'one', 0)
    group = BeeGroupItem()
    commands.GroupItems(view.scene, [item1], group).redo()
    loose = add_text(view, 'loose', 5)
    tree = tree_of(view)
    group_entry, group = group_of(view, tree)

    loose_entry = [tree.topLevelItem(i)
                   for i in range(tree.topLevelItemCount())
                   if tree.topLevelItem(i).data(0, ITEM_ROLE) is loose][0]
    tree.takeTopLevelItem(tree.indexOfTopLevelItem(loose_entry))
    group_entry.insertChild(0, loose_entry)
    tree.apply_order([loose], group_entry)

    view.undo_stack.undo()
    assert loose.parentItem() is None


def test_reorder_writes_back_z_values(view):
    bottom = add_text(view, 'bottom', 0)
    top = add_text(view, 'top', 1)
    tree = tree_of(view)

    # Pretend the tree was reordered so that 'bottom' is listed first
    tree.clear()
    for item in (bottom, top):
        entry = QtWidgets.QTreeWidgetItem(tree)
        entry.setText(0, item.get_display_name())
        entry.setData(0, ITEM_ROLE, item)

    tree.apply_order([bottom], None)
    assert bottom.zValue() > top.zValue()
    assert len(view.undo_stack) == 1

    view.undo_stack.undo()
    assert bottom.zValue() < top.zValue()
