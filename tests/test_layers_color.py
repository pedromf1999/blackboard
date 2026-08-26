from PyQt6 import QtGui

from beeref.items import BeeGroupItem, BeePixmapItem, BeeTextItem


def tree(view):
    return view.layers_dock.tree


def group_with_image(view):
    img = QtGui.QImage(60, 40, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor('red'))
    group = BeeGroupItem()
    view.scene.addItem(group)
    child = BeePixmapItem(img)
    child.setParentItem(group)
    group.fit_to_children()
    return group


def test_an_untitled_group_goes_by_its_box(view):
    group = group_with_image(view)
    group.box_color = QtGui.QColor('#334455')

    assert tree(view).entry_color(group) == QtGui.QColor('#334455')


def test_a_titled_group_goes_by_its_title_band(view):
    """The band is what is read on the canvas."""

    group = group_with_image(view)
    group.box_color = QtGui.QColor('#334455')
    group.title = 'Lid Latch'
    group.header_color = QtGui.QColor('#e8a33d')

    assert tree(view).entry_color(group) == QtGui.QColor('#e8a33d')


def test_a_title_with_no_colour_of_its_own_still_goes_by_the_group(view):
    """The band takes the group's colour, so nothing changes."""

    group = group_with_image(view)
    group.box_color = QtGui.QColor('#334455')
    group.title = 'Lid Latch'

    assert tree(view).entry_color(group) == QtGui.QColor('#334455')


def test_taking_the_title_off_goes_back_to_the_box(view):
    group = group_with_image(view)
    group.box_color = QtGui.QColor('#334455')
    group.header_color = QtGui.QColor('#e8a33d')
    group.title = 'Lid Latch'
    group.title = ''

    assert tree(view).entry_color(group) == QtGui.QColor('#334455')


def test_a_note_still_goes_by_its_own_box(view):
    note = BeeTextItem('hello')
    view.scene.addItem(note)
    note.box_color = QtGui.QColor('#204080')

    assert tree(view).entry_color(note) == note.visible_box_color()


def test_an_image_has_no_colour_to_show(view):
    img = QtGui.QImage(4, 4, QtGui.QImage.Format.Format_ARGB32)
    item = BeePixmapItem(img)
    view.scene.addItem(item)

    assert tree(view).entry_color(item) is None


def test_the_panel_notices_the_title_colour_changing(view):
    """Otherwise the entry would keep the colour it was built with."""

    group = group_with_image(view)
    group.title = 'Lid Latch'
    group.header_color = QtGui.QColor('#e8a33d')
    before = tree(view).get_signature()

    group.header_color = QtGui.QColor('#2f6f4f')
    assert tree(view).get_signature() != before


def test_the_entry_is_painted_in_that_colour(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    group.header_color = QtGui.QColor('#e8a33d')
    tree(view).refresh()

    entry = tree(view).topLevelItem(0)
    assert entry.background(0).color() == QtGui.QColor('#e8a33d')
