import os.path

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref import commands
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


def test_lists_items_topmost_first(view):
    add_text(view, 'bottom', 0)
    add_text(view, 'middle', 1)
    add_text(view, 'top', 2)
    tree = tree_of(view)
    assert entries(tree) == [(0, 'top'), (0, 'middle'), (0, 'bottom')]


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
