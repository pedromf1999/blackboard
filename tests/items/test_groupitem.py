from unittest.mock import MagicMock, patch

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
    data = group.get_extra_save_data()
    assert data['box_color'] == (255, 0, 0, 100)
    assert data['locked'] is True


def test_init_locked_defaults_to_false(qapp):
    assert BeeGroupItem().locked is False


def test_new_group_records_its_creation_date(qapp):
    group = BeeGroupItem()
    assert group.created
    # Nothing has happened to it yet
    assert group.modified == group.created


def test_group_keeps_dates_it_was_given(qapp):
    group = BeeGroupItem(created='2026-01-02T03:04:05',
                         modified='2026-02-03T04:05:06')
    assert group.created == '2026-01-02T03:04:05'
    assert group.modified == '2026-02-03T04:05:06'


def test_touch_updates_only_the_edit_date(qapp):
    group = BeeGroupItem(created='2026-01-02T03:04:05',
                         modified='2026-01-02T03:04:05')
    group.touch()
    assert group.created == '2026-01-02T03:04:05'
    assert group.modified != '2026-01-02T03:04:05'


def test_dates_are_saved(qapp):
    group = BeeGroupItem(created='2026-01-02T03:04:05',
                         modified='2026-02-03T04:05:06')
    data = group.get_extra_save_data()
    assert data['created'] == '2026-01-02T03:04:05'
    assert data['modified'] == '2026-02-03T04:05:06'


def test_details_are_readable(qapp):
    group = BeeGroupItem(created='2026-01-02T03:04:05',
                         modified='2026-02-03T04:05:06')
    assert group.get_details() == (
        'Created: 02 Jan 2026, 03:04\n'
        'Last edited: 03 Feb 2026, 04:05')


def test_details_when_dates_are_missing(qapp):
    """Groups from files written before dates existed."""

    group = BeeGroupItem()
    group.created = None
    group.modified = None
    assert group.get_details() == 'Created: unknown\nLast edited: unknown'


def test_details_when_date_is_unreadable(qapp):
    group = BeeGroupItem(created='not a date', modified='not a date')
    assert 'not a date' in group.get_details()


def test_copy_of_a_group_is_new(qapp, view):
    group, items = make_group(view, (0, 0))
    group.created = '2020-01-01T00:00:00'
    copy = group.create_copy()
    assert copy.created != group.created


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


def test_drop_target_defaults_to_false(qapp):
    assert BeeGroupItem().drop_target is False


def test_drop_target_triggers_repaint(qapp):
    group = BeeGroupItem()
    with patch.object(group, 'update') as update_mock:
        group.drop_target = True
        update_mock.assert_called_once()
        # Setting the same value again does not repaint
        group.drop_target = True
        update_mock.assert_called_once()


@patch('beeref.selection.SelectableMixin.paint_selectable')
def test_paint_draws_drop_target_highlight(selectable_mock, view):
    group, items = make_group(view, (0, 0))
    painter = MagicMock()
    option = MagicMock()

    group.drop_target = False
    group.paint(painter, option, 'widget')
    assert painter.drawRoundedRect.call_count == 1

    painter.reset_mock()
    group.drop_target = True
    group.paint(painter, option, 'widget')
    # The box, plus the highlight border on top of it
    assert painter.drawRoundedRect.call_count == 2


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


def test_create_copy_locks_children_into_the_copy(view):
    group, items = make_group(view, (0, 0), (0, 80))
    group.set_children_interactive(False)

    copy = group.create_copy()
    flag = QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    assert all(not bool(child.flags() & flag)
               for child in copy.bee_children())


def test_create_copy_copies_nested_groups(view):
    outer, items = make_group(view, (0, 0), (0, 80))
    inner, inner_items = make_group(view, (200, 0))
    inner.setParentItem(outer)
    outer.fit_to_children()

    copy = outer.create_copy()
    nested = [child for child in copy.bee_children()
              if getattr(child, 'TYPE', None) == 'group']
    assert len(nested) == 1
    assert nested[0] is not inner
    assert len(nested[0].bee_children()) == 1


def test_create_copy_gives_fresh_save_ids(view):
    group, items = make_group(view, (0, 0))
    group.save_id = 3
    items[0].save_id = 4

    copy = group.create_copy()
    assert copy.save_id is None
    assert copy.bee_children()[0].save_id is None


def test_get_save_data_includes_parent_group(view):
    group, items = make_group(view, (0, 0))
    group.save_id = 7
    assert items[0].get_save_data()['parent_group'] == 7


def test_get_save_data_without_group(view):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    assert 'parent_group' not in item.get_save_data()
