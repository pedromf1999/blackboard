from PyQt6 import QtGui

from beeref.items import BeeGroupItem, BeePixmapItem


def giant_group(view, spread=200000):
    """A group the size of the ones a real board grows to."""

    group = BeeGroupItem()
    view.scene.addItem(group)
    for x, y in ((0, 0), (spread, spread), (spread // 3, spread // 2)):
        img = QtGui.QImage(4000, 3000, QtGui.QImage.Format.Format_ARGB32)
        img.fill(QtGui.QColor(90, 140, 190))
        child = BeePixmapItem(img)
        child.setParentItem(group)
        child.setPos(x, y)
    group.fit_to_children()
    return group


def looking_at(view):
    return view.mapToScene(view.viewport().rect()).boundingRect()


def fit_to(view, item):
    view.resize(900, 800)
    view.recalc_scene_rect()
    view.fit_rect(item.sceneBoundingRect())


def test_a_title_band_is_brought_into_sight(view):
    """It is added above the group, so on a big one it opens off the
    top of the window and the writing goes on blind."""

    group = giant_group(view)
    fit_to(view, group)
    group.enter_title_edit_mode()

    band = group.mapRectToScene(group.header_rect())
    seen = looking_at(view)
    assert seen.top() <= band.top()
    assert seen.bottom() >= band.bottom()


def test_a_small_group_is_hardly_moved(view):
    """Its band was all but in sight already, so barely a nudge."""

    group = giant_group(view, spread=400)
    fit_to(view, group)
    before = looking_at(view)
    group.enter_title_edit_mode()

    moved = abs(looking_at(view).top() - before.top())
    assert moved < group.header_height() * 2


def test_a_caption_band_is_brought_into_sight_too(view):
    """That one hangs below, so it goes off the bottom instead.

    A band wider than the window cannot be shown whole, so what is
    asked is that all of its height is in sight.
    """

    img = QtGui.QImage(60000, 40000, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor(90, 140, 190))
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    fit_to(view, item)
    item.enter_caption_edit_mode()

    band = item.mapRectToScene(item.caption_rect())
    seen = looking_at(view)
    assert seen.top() <= band.top()
    assert seen.bottom() >= band.bottom()


def test_the_words_land_in_the_band_that_was_opened(view):
    """What is typed has to end up where the band is."""

    group = giant_group(view)
    fit_to(view, group)
    group.enter_title_edit_mode()
    group.title_editor.textCursor().insertText('esfefefe')

    band = group.mapRectToScene(group.header_rect())
    assert band.contains(group.title_editor.sceneBoundingRect())
    assert looking_at(view).intersects(
        group.title_editor.sceneBoundingRect())
