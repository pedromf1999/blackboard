import os.path
from unittest.mock import patch

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref import commands
from beeref.actions.actions import actions
from beeref.items import BeeGroupItem, BeePixmapItem, BeeTextItem


ITEM_ROLE = Qt.ItemDataRole.UserRole


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


def test_dock_starts_hidden(view):
    assert view.layers_dock.isVisible() is False


def test_closing_dock_hides_it_and_unticks_the_menu(view):
    view.on_action_show_layers(True)
    action = actions['show_layers'].qaction
    action.setChecked(True)

    view.layers_dock.close()
    assert view.layers_dock.isVisible() is False
    assert action.isChecked() is False


def test_closing_dock_does_not_quit(view):
    view.on_action_show_layers(True)
    with patch('PyQt6.QtWidgets.QApplication.quit') as quit_mock:
        view.layers_dock.close()
    quit_mock.assert_not_called()


def test_dock_can_be_collapsed(view):
    view.on_action_show_layers(True)
    dock = view.layers_dock
    assert dock.collapsed is False

    dock.toggle_collapsed()
    assert dock.collapsed is True
    assert dock.tree.isVisible() is False
    assert dock.maximumHeight() == dock.titlebar.sizeHint().height()


def test_dock_can_be_expanded_again(view):
    view.on_action_show_layers(True)
    dock = view.layers_dock
    dock.toggle_collapsed()
    dock.toggle_collapsed()
    assert dock.collapsed is False
    assert dock.tree.isVisible() is True
    assert dock.maximumHeight() > dock.titlebar.sizeHint().height()


def test_collapse_button_arrow_follows_state(view):
    dock = view.layers_dock
    button = dock.titlebar.collapse_button
    assert button.arrowType() == Qt.ArrowType.DownArrow
    dock.toggle_collapsed()
    assert button.arrowType() == Qt.ArrowType.RightArrow


def test_lists_items_topmost_first(view):
    add_text(view, 'bottom', 0)
    add_text(view, 'middle', 1)
    add_text(view, 'top', 2)
    tree = tree_of(view)
    assert entries(tree) == [(0, 'top'), (0, 'middle'), (0, 'bottom')]


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
