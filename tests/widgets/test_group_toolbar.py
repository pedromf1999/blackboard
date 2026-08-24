from unittest.mock import patch

from PyQt6 import QtGui

from beeref import commands
from beeref.items import BeeGroupItem, BeeTextItem


def a_group(view):
    items = []
    for n in range(2):
        item = BeeTextItem(f'note {n}')
        view.scene.addItem(item)
        item.setPos(0, n * 60)
        items.append(item)
    group = BeeGroupItem(box_color=(10, 20, 30, 200))
    commands.GroupItems(view.scene, items, group).redo()
    view.scene.deselect_all_items()
    view.update_pinned_toolbars()
    return items, group


def test_hidden_until_a_group_is_selected(view):
    items, group = a_group(view)
    assert view.group_toolbar.isVisible() is False

    group.setSelected(True)
    view.update_pinned_toolbars()
    assert view.group_toolbar.isVisible() is True


def test_offers_the_group_colour(view):
    items, group = a_group(view)
    group.setSelected(True)
    view.update_pinned_toolbars()

    assert view.group_toolbar.color.icon().isNull() is False
    assert 'colour' in view.group_toolbar.color.toolTip().lower()

    chosen = QtGui.QColor(30, 160, 220)
    with patch.object(type(view), 'pick_color_live', return_value=chosen):
        view.group_toolbar.color.click()

    assert group.box_color == chosen


def test_a_note_inside_the_group_gets_the_text_bar_instead(view):
    items, group = a_group(view)
    view.scene.enter_group(group, items[0])
    items[0].setSelected(True)
    view.update_pinned_toolbars()

    assert view.group_toolbar.isVisible() is False
    assert view.text_toolbar.isVisible() is True


def test_offers_lock_and_ungroup(view):
    items, group = a_group(view)
    group.setSelected(True)
    view.update_pinned_toolbars()
    bar = view.group_toolbar

    for button in (bar.color, bar.lock, bar.ungroup):
        assert button.icon().isNull() is False


def test_the_lock_button_locks_and_unlocks(view):
    items, group = a_group(view)
    group.setSelected(True)
    view.update_pinned_toolbars()
    bar = view.group_toolbar

    assert group.locked is False
    assert bar.lock.toolTip() == 'Lock group'
    locked_icon = bar.lock.icon().cacheKey()

    bar.lock.click()
    assert group.locked is True
    view.update_pinned_toolbars()
    # The button says what pressing it would do next
    assert bar.lock.toolTip() == 'Unlock group'
    assert bar.lock.icon().cacheKey() != locked_icon

    bar.lock.click()
    assert group.locked is False
    view.update_pinned_toolbars()
    assert bar.lock.toolTip() == 'Lock group'


def test_locking_from_the_button_keeps_the_menu_in_step(view):
    from beeref.actions.actions import actions as all_actions

    items, group = a_group(view)
    group.setSelected(True)
    view.update_pinned_toolbars()

    view.group_toolbar.lock.click()
    assert all_actions['lock_group'].qaction.isChecked() is True


def test_the_ungroup_button_ungroups(view):
    items, group = a_group(view)
    group.setSelected(True)
    view.update_pinned_toolbars()

    view.group_toolbar.ungroup.click()

    assert list(view.scene.items_by_type('group')) == []
    loose = [i for i in view.scene.items_by_type('text')
             if i.parentItem() is None]
    assert len(loose) == 2
