from unittest.mock import patch

from PyQt6 import QtCore, QtGui

from beeref.items import BeeGroupItem, BeePixmapItem, BeeTextItem


def image(view, pos=(0, 0)):
    img = QtGui.QImage(80, 60, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor('red'))
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    item.setPos(*pos)
    return item


def at(view, item):
    return view.mapFromScene(item.sceneBoundingRect().center())


def entries(menu):
    return [action.text() for action in menu.actions()]


def test_the_image_menu_offers_the_stacking_order(view):
    """Buried under Edit in the long menu, and aimed at one picture."""

    assert '&Raise to Top' in entries(view.image_context_menu)
    assert 'Lower to Bottom' in entries(view.image_context_menu)


def test_it_still_offers_what_images_could_already_do(view):
    text = entries(view.image_context_menu)
    for wanted in ('&Crop', '&Outline', '&Grayscale'):
        assert wanted in text


def test_right_clicking_an_image_opens_it(view):
    item = image(view)
    with patch.object(view.image_context_menu, 'exec') as opened:
        view.on_context_menu(at(view, item))
    assert opened.called


def test_right_clicking_an_image_selects_it(view):
    item = image(view)
    with patch.object(view.image_context_menu, 'exec'):
        view.on_context_menu(at(view, item))
    assert item.isSelected() is True


def test_a_note_still_gets_the_text_menu(view):
    note = BeeTextItem('hello')
    view.scene.addItem(note)
    with patch.object(view.text_context_menu, 'exec') as opened:
        view.on_context_menu(at(view, note))
    assert opened.called


def test_empty_canvas_still_gets_the_long_menu(view):
    with patch.object(view.context_menu, 'exec') as opened:
        view.on_context_menu(QtCore.QPoint(5, 5))
    assert opened.called


def test_an_image_inside_a_group_gets_it_too(view):
    """Stacking is decided within the group it sits in."""

    group = BeeGroupItem()
    view.scene.addItem(group)
    item = image(view)
    item.setParentItem(group)
    group.fit_to_children()

    with patch.object(view.image_context_menu, 'exec') as opened:
        view.on_context_menu(at(view, item))
    assert opened.called
    assert view.scene.active_group is group


def test_a_locked_group_keeps_its_pictures_to_itself(view):
    group = BeeGroupItem(locked=True)
    view.scene.addItem(group)
    item = image(view)
    item.setParentItem(group)
    group.fit_to_children()

    with patch.object(view.image_context_menu, 'exec') as opened:
        with patch.object(view.group_context_menu, 'exec'):
            view.on_context_menu(at(view, item))
    assert opened.called is False


def test_raising_an_image_works_from_there(view):
    under = image(view)
    over = image(view)
    over.setZValue(under.zValue() + 1)
    under.setSelected(True)

    view.on_action_raise_to_top()
    assert under.zValue() > over.zValue()

    over.setSelected(True)
    under.setSelected(False)
    view.on_action_lower_to_bottom()
    assert over.zValue() < under.zValue()
