from PyQt6 import QtCore, QtGui, QtWidgets

from beeref.items import BeeGroupItem, BeeTextItem, item_registry


def make_group(view, *positions):
    """A group holding a text item at each of the given positions."""

    items = []
    for x, y in positions:
        item = BeeTextItem('foo')
        view.scene.addItem(item)
        item.setPos(x, y)
        items.append(item)
    group = BeeGroupItem()
    view.scene.addItem(group)
    for item in items:
        item.setParentItem(group)
    group.fit_to_children()
    return group, items


def test_in_items_registry():
    assert item_registry['group'] == BeeGroupItem


def test_init(qapp):
    group = BeeGroupItem()
    assert group.save_id is None
    assert group.is_image is False
    assert group.is_editable is False
    assert group.box_color == QtGui.QColor(52, 52, 52, 255)


def test_init_with_box_color(qapp):
    group = BeeGroupItem(box_color=(255, 0, 0, 100))
    assert group.box_color == QtGui.QColor(255, 0, 0, 100)


def test_get_extra_save_data(qapp):
    group = BeeGroupItem(box_color=(255, 0, 0, 100), locked=True)
    assert group.get_extra_save_data() == {
        'box_color': (255, 0, 0, 100), 'locked': True}


def test_init_locked_defaults_to_false(qapp):
    assert BeeGroupItem().locked is False


def test_bee_children(view):
    group, items = make_group(view, (0, 0), (0, 80))
    assert group.bee_children() == items


def test_fit_to_children_includes_padding(view):
    group, items = make_group(view, (0, 0))
    child_rect = items[0].boundingRect()
    assert group.rect().width() >= child_rect.width() + 2 * group.PADDING
    assert group.rect().height() >= child_rect.height() + 2 * group.PADDING


def test_fit_to_children_without_children(qapp):
    group = BeeGroupItem()
    group.fit_to_children()
    assert group.rect() == QtCore.QRectF()


def test_set_children_interactive(view):
    group, items = make_group(view, (0, 0), (0, 80))
    flag = QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable

    group.set_children_interactive(False)
    assert all(not bool(item.flags() & flag) for item in items)
    group.set_children_interactive(True)
    assert all(bool(item.flags() & flag) for item in items)


def test_set_children_interactive_deselects(view):
    group, items = make_group(view, (0, 0))
    items[0].setSelected(True)
    group.set_children_interactive(False)
    assert items[0].isSelected() is False


def test_contains_scene_pos(view):
    group, items = make_group(view, (0, 0))
    inside = group.mapToScene(group.rect().center())
    assert group.contains_scene_pos(inside) is True
    outside = group.mapToScene(
        group.rect().bottomRight() + QtCore.QPointF(50, 50))
    assert group.contains_scene_pos(outside) is False


def test_moving_group_moves_children(view):
    group, items = make_group(view, (10, 10))
    before = items[0].scenePos()
    group.setPos(100, 50)
    assert items[0].scenePos() == before + QtCore.QPointF(100, 50)


def test_create_copy(view):
    group, items = make_group(view, (0, 0), (0, 80))
    group.box_color = QtGui.QColor(255, 0, 0, 100)
    group.locked = True
    group.setPos(20, 30)

    copy = group.create_copy()
    assert copy.box_color == QtGui.QColor(255, 0, 0, 100)
    assert copy.locked is True
    assert copy.pos() == QtCore.QPointF(20, 30)
    assert len(copy.bee_children()) == 2
    assert copy.bee_children()[0] is not items[0]


def test_get_save_data_includes_parent_group(view):
    group, items = make_group(view, (0, 0))
    group.save_id = 7
    assert items[0].get_save_data()['parent_group'] == 7


def test_get_save_data_without_group(view):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    assert 'parent_group' not in item.get_save_data()
