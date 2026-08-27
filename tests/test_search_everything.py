from PyQt6 import QtGui

from beeref.items import BeeGroupItem, BeePixmapItem, BeeTextItem


def image(view, caption=''):
    img = QtGui.QImage(200, 120, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor('red'))
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    item.caption = caption
    return item


def group(view, title=''):
    item = group_box(view)
    item.title = title
    return item


def group_box(view):
    img = QtGui.QImage(200, 120, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor('blue'))
    grp = BeeGroupItem()
    view.scene.addItem(grp)
    child = BeePixmapItem(img)
    child.setParentItem(grp)
    grp.fit_to_children()
    return grp


def find(view, query):
    view.text_search_query = query
    return view.get_text_search_matches()


def test_a_group_title_is_found(view):
    """It is writing on the board like any other."""

    titled = group(view, 'Lid Latch')
    group(view, 'Something else')

    assert find(view, 'lid latch') == [titled]


def test_an_image_caption_is_found(view):
    captioned = image(view, 'Top view')
    image(view, 'Side view')

    assert find(view, 'top view') == [captioned]


def test_a_note_is_still_found(view):
    note = BeeTextItem('find me')
    view.scene.addItem(note)
    assert find(view, 'find me') == [note]


def test_words_in_a_table_are_found(view):
    """A note's plain text runs its cells in with the rest of it."""

    note = BeeTextItem('hello')
    view.scene.addItem(note)
    note.setSelected(True)
    note.enter_edit_mode()
    view.on_action_insert_table()
    note.current_table().cellAt(1, 1).firstCursorPosition().insertText(
        'Parafuso')
    note.exit_edit_mode()

    assert find(view, 'parafuso') == [note]


def test_all_three_come_back_together(view):
    note = BeeTextItem('shared word')
    view.scene.addItem(note)
    titled = group(view, 'shared word')
    captioned = image(view, 'shared word')

    assert set(find(view, 'shared')) == {note, titled, captioned}


def test_an_untitled_group_matches_nothing(view):
    group(view, '')
    assert find(view, '') != []
    assert find(view, 'anything') == []


def test_a_match_is_gone_to(view):
    """A title has no letters laid out to measure, so the band it is."""

    titled = group(view, 'Lid Latch')
    rect = titled.search_rect('Latch')

    assert rect is not None
    assert rect.isEmpty() is False
    expected = titled.mapToScene(titled.header_rect()).boundingRect()
    assert rect == expected


def test_a_caption_match_is_gone_to(view):
    captioned = image(view, 'Top view')
    rect = captioned.search_rect('view')

    assert rect == captioned.mapToScene(
        captioned.caption_rect()).boundingRect()


def test_cycling_takes_in_all_of_them(view):
    BeeTextItem('shared')
    note = BeeTextItem('shared')
    view.scene.addItem(note)
    group(view, 'shared')
    image(view, 'shared')

    view.text_search_query = 'shared'
    view.text_search_index = -1
    seen = []
    for _ in range(3):
        view.find_next_text_match()
        seen.append(view.text_search_index)
    assert seen == [0, 1, 2]


def test_the_word_in_a_note_is_still_zoomed_to(view):
    """Not the whole note: a word late in a long note is far from
    the middle of it."""

    note = BeeTextItem('aaaa bbbb cccc dddd target')
    view.scene.addItem(note)
    rect = note.search_rect('target')

    assert note.sceneBoundingRect().contains(rect)
    assert rect.left() > note.sceneBoundingRect().center().x()
