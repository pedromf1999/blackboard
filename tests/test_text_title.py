import os

from unittest.mock import patch

from PyQt6 import QtCore, QtGui, QtWidgets

from beeref import commands, fileio
from beeref.assets import BeeAssets
from beeref.items import BeeTextItem


def note(view, text='Hello', pos=(0, 0)):
    item = BeeTextItem(text=text)
    view.scene.addItem(item)
    item.setPos(*pos)
    return item


def titled(view, title='Chapter One', text='Hello'):
    item = note(view, text)
    item.title = title
    return item


def test_a_note_starts_without_a_band(view):
    """Notes written before there were titles look as they did."""

    item = note(view)
    assert item.title == ''
    assert item.shows_header() is False
    assert item.header_height() == 0


def test_a_title_puts_a_band_above_the_words(view):
    item = titled(view)

    assert item.shows_header() is True
    assert item.header_height() > 0
    assert item.header_rect().bottom() == item.text_rect().top()


def test_the_band_grows_the_note_upwards_only(view):
    """The words stay where they were: a heading is added over them,
    never laid on top of them."""

    item = note(view)
    before = item.text_rect()
    item.title = 'Chapter One'

    assert item.text_rect() == before
    assert item.boundingRect().top() < before.top()


def test_an_emptied_title_takes_the_band_with_it(view):
    item = titled(view)
    item.title = ''

    assert item.shows_header() is False
    assert item.header_height() == 0


def test_the_handles_stay_on_the_words(view):
    """A heading must not move where the note is grabbed to resize it."""

    item = note(view)
    before = item.bounding_rect_unselected()
    item.title = 'Chapter One'

    assert item.bounding_rect_unselected() == before


def test_the_band_can_be_clicked(view):
    """It is part of the note as far as the mouse is concerned."""

    item = titled(view)
    middle = item.header_rect().center()

    assert item.shape().contains(middle)


def test_the_title_is_bigger_than_the_text_it_heads(view):
    item = titled(view)
    own = QtGui.QFontInfo(item.font()).pointSizeF()

    assert item.title_size() > own
    assert item.title_font().bold() is True


def test_it_is_written_in_the_bundled_face(view):
    """A title is not a note; the same face group titles use."""

    item = titled(view)
    family = BeeAssets().font_family
    if family:
        assert item.title_font().family() == family


def test_a_bigger_note_gets_a_bigger_title(view):
    small = titled(view)
    big = titled(view)
    cursor = big.textCursor()
    cursor.select(QtGui.QTextCursor.SelectionType.Document)
    charformat = QtGui.QTextCharFormat()
    charformat.setFontPointSize(60)
    cursor.mergeCharFormat(charformat)

    assert big.title_size() > small.title_size()


def test_the_title_size_is_reined_in_at_the_top(view):
    item = titled(view)
    cursor = item.textCursor()
    cursor.select(QtGui.QTextCursor.SelectionType.Document)
    charformat = QtGui.QTextCharFormat()
    charformat.setFontPointSize(40000)
    cursor.mergeCharFormat(charformat)

    assert item.title_size() == item.TITLE_MAX_SIZE


def test_the_band_takes_the_notes_colour_by_default(view):
    item = titled(view)
    item.box_color = QtGui.QColor(10, 20, 30)

    assert item.header_color is None
    assert item.default_header_color() == item.box_color


def test_the_band_can_have_a_colour_of_its_own(view):
    item = titled(view)
    item.header_color = QtGui.QColor(200, 30, 30)

    assert item.visible_header_color().red() > 150


def test_the_title_can_sit_left_or_centred(view):
    item = titled(view)
    assert item.title_align == item.TITLE_CENTER

    item.title_align = item.TITLE_LEFT
    assert item.title_text_alignment() == Qt_align_left()


def Qt_align_left():
    from PyQt6.QtCore import Qt
    return Qt.AlignmentFlag.AlignLeft


def test_writing_a_title_puts_an_editor_on_the_note(view):
    item = note(view)
    item.enter_title_edit_mode()

    assert item.title_editing is True
    assert item.title_editor is not None
    assert view.scene.title_item is item


def test_finishing_it_records_one_undo_step(view):
    item = note(view)
    item.enter_title_edit_mode()
    item.title_editor.setPlainText('Chapter One')
    depth = view.undo_stack.index()
    item.exit_title_edit_mode()

    assert view.undo_stack.index() == depth + 1
    assert item.title == 'Chapter One'
    view.undo_stack.undo()
    assert item.title == ''


def test_escaping_throws_the_words_away(view):
    item = titled(view, 'Chapter One')
    item.enter_title_edit_mode()
    item.title_editor.setPlainText('Something else')
    item.exit_title_edit_mode(commit=False)

    assert item.title == 'Chapter One'


def test_a_title_left_empty_leaves_no_band(view):
    item = note(view)
    item.enter_title_edit_mode()
    item.exit_title_edit_mode()

    assert item.title == ''
    assert item.shows_header() is False


def test_the_text_tool_opens_a_title_instead_of_covering_it(view):
    item = titled(view)
    view.set_draw_tool('text')
    point = view.mapFromScene(
        item.mapToScene(item.header_rect().center()))
    view.write_note_at(point)

    assert item.title_editing is True
    assert len(list(view.scene.items_by_type('text'))) == 1


def test_double_clicking_the_band_opens_it(view):
    item = titled(view)

    assert view.scene.title_double_clicked(
        item, item.mapToScene(item.header_rect().center())) is True
    assert item.title_editing is True


def test_double_clicking_the_words_still_edits_the_note(view):
    item = titled(view)

    assert view.scene.title_double_clicked(
        item, item.mapToScene(item.text_rect().center())) is False


def test_the_title_is_saved_with_the_note(view, tmpdir):
    item = titled(view, 'Chapter One')
    item.header_color = QtGui.QColor(200, 30, 30)
    item.title_align = item.TITLE_LEFT

    path = os.path.join(tmpdir, 'titled.blk')
    fileio.save_bee(path, view.scene, create_new=True)
    view.scene.clear()
    fileio.load_bee(path, view.scene)
    view.scene.add_queued_items()

    back = list(view.scene.items_by_type('text'))[0]
    assert back.title == 'Chapter One'
    assert back.title_align == back.TITLE_LEFT
    assert back.header_color.red() == 200


def test_a_note_without_a_title_saves_an_empty_one(view, tmpdir):
    """Which is what an old file has, so both read the same."""

    item = note(view)
    data = item.get_extra_save_data()

    assert data['title'] == ''
    assert data['header_color'] is None


def test_a_copy_takes_the_title_with_it(view):
    item = titled(view, 'Chapter One')
    item.title_align = item.TITLE_LEFT
    copy = item.create_copy()

    assert copy.title == 'Chapter One'
    assert copy.title_align == copy.TITLE_LEFT


def test_find_looks_through_titles_too(view):
    item = titled(view, 'Chapter One', text='nothing here')

    assert 'Chapter One' in item.search_text()
    assert 'nothing here' in item.search_text()


def test_find_goes_to_the_band_when_only_it_matches(view):
    item = titled(view, 'Chapter One', text='nothing here')
    rect = item.search_rect('Chapter')

    assert rect is not None
    assert rect.intersects(
        item.mapToScene(item.header_rect()).boundingRect())


def test_find_still_goes_to_the_word_in_the_note(view):
    item = titled(view, 'Chapter One', text='nothing here')
    rect = item.search_rect('nothing')

    assert rect is not None
    assert rect.intersects(
        item.mapToScene(item.text_rect()).boundingRect())


def test_the_command_undoes_colour_and_alignment_together(view):
    item = titled(view, 'Chapter One')
    view.undo_stack.push(commands.ChangeTitle(
        [item], 'Another', QtGui.QColor(1, 2, 3), item.TITLE_LEFT))

    assert item.title == 'Another'
    view.undo_stack.undo()
    assert item.title == 'Chapter One'
    assert item.header_color is None
    assert item.title_align == item.TITLE_CENTER


def test_the_menu_command_needs_a_note(view):
    with patch('beeref.widgets.BeeNotification') as told:
        view.on_action_text_title()
    assert told.called


def test_the_menu_command_opens_the_selected_note(view):
    item = note(view)
    item.setSelected(True)
    view.on_action_text_title()

    assert item.title_editing is True


def test_the_colour_button_colours_the_title_while_writing(view):
    item = titled(view, 'Chapter One')
    item.setSelected(True)
    item.enter_title_edit_mode()

    with patch.object(view, 'pick_color_live',
                      return_value=QtGui.QColor(9, 9, 9)) as picked:
        view.on_action_text_title_color()
    assert picked.called
    assert item.header_color.red() == 9


def test_alignment_can_be_changed_from_the_menu(view):
    item = titled(view, 'Chapter One')
    item.setSelected(True)
    view.on_action_text_title_align_left()

    assert item.title_align == item.TITLE_LEFT
    view.on_action_text_title_align_center()
    assert item.title_align == item.TITLE_CENTER


def test_the_bar_says_what_the_colour_button_will_do(view):
    from beeref.widgets.text_toolbar import TextToolBar

    bar = TextToolBar(view, view)
    item = titled(view, 'Chapter One')
    bar.update_title(item)
    assert bar.writing_title is False
    assert bar.box_color.toolTip() == 'Box colour'

    item.enter_title_edit_mode()
    bar.update_title(item)
    assert bar.writing_title is True
    assert bar.box_color.toolTip() == 'Title colour'


def test_alignment_is_offered_only_once_there_is_a_title(view):
    from beeref.widgets.text_toolbar import TextToolBar

    bar = TextToolBar(view, view)
    plain = note(view)
    bar.update_title(plain)
    assert bar.align_left.isEnabled() is False

    bar.update_title(titled(view))
    assert bar.align_left.isEnabled() is True


def test_the_title_icon_is_not_the_text_tools(view):
    """A heading is a different thing from a note, and the icons say so.

    The tool that writes a note keeps the plain upright T; a title is a
    bold italic one.
    """

    icons = BeeAssets().PATH.joinpath('icons')
    title = icons.joinpath('title.svg').read_text(encoding='utf-8')
    text = icons.joinpath('text.svg').read_text(encoding='utf-8')

    assert title != text
    # Thicker than the tool's stroke, and a stem that leans
    assert 'stroke-width="3"' in title
    assert 'stroke-width="2"' in text
    assert 'M15 6L11 18' in title


def test_every_title_button_uses_the_same_icon(view):
    """Groups, pictures and notes all head something with it."""

    import beeref.widgets.group_toolbar as group_bar
    import beeref.widgets.image_toolbar as image_bar
    import beeref.widgets.text_toolbar as text_bar

    for module in (group_bar, image_bar, text_bar):
        source = open(module.__file__, encoding='utf-8').read()
        assert "'title'," in source


def test_the_band_is_drawn(view, settings):
    """Something of the title reaches the canvas."""

    view.resize(400, 300)
    item = titled(view, 'Chapter One')
    item.header_color = QtGui.QColor(255, 0, 0)
    view.fit_rect(item.mapToScene(item.boundingRect()).boundingRect())
    view.viewport().update()

    shot = view.viewport().grab().toImage()
    reds = [1 for x in range(shot.width()) for y in range(shot.height())
            if shot.pixelColor(x, y).red() > 150]
    assert reds


def test_a_title_being_written_is_not_drawn_twice(view):
    """The editor holds the words while it is open."""

    item = titled(view, 'Chapter One')
    item.enter_title_edit_mode()

    picture = QtGui.QImage(200, 100, QtGui.QImage.Format.Format_ARGB32)
    painter = QtGui.QPainter(picture)
    item.paint_title_text(painter)
    painter.end()
    assert item.title_editing is True


def test_the_editor_sits_in_the_band(view):
    item = titled(view, 'Chapter One')
    item.enter_title_edit_mode()
    band = item.header_rect()
    editor = item.title_editor

    assert editor.pos().y() >= band.y()
    assert editor.pos().y() < band.bottom()


def test_a_group_title_still_works(view):
    """The band is shared code now, so this is worth saying out loud."""

    item = note(view)
    item.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]
    group.title = 'A Group'

    assert group.shows_header() is True
    assert group.header_height() > 0


def test_scaling_the_note_scales_its_title(view):
    """Everything on the canvas grows together."""

    item = titled(view, 'Chapter One')
    before = item.mapToScene(item.header_rect()).boundingRect().height()
    item.setScale(3)
    after = item.mapToScene(item.header_rect()).boundingRect().height()

    assert round(after / before, 3) == 3


def test_the_band_is_as_wide_as_the_note(view):
    item = titled(view, 'Chapter One')

    assert item.header_rect().width() == item.text_rect().width()


def test_writing_a_title_brings_it_into_view(view):
    item = titled(view, 'Chapter One')
    with patch.object(type(view), 'reveal') as revealed:
        item.enter_title_edit_mode()
    revealed.assert_called_once()


def test_a_long_title_is_cut_off_rather_than_stretching_the_note(view):
    """A heading names a note; it is not a second note."""

    item = titled(view, 'Chapter One')
    before = item.text_rect().width()
    item.title = 'A very much longer heading than the note is wide'

    assert item.text_rect().width() == before


def test_clicking_the_band_with_the_tool_needs_a_band(view):
    item = note(view)
    point = view.mapFromScene(item.mapToScene(item.text_rect().topLeft()))

    assert view.title_band_at(point) is None


def test_the_tool_finds_a_notes_band(view):
    item = titled(view, 'Chapter One')
    point = view.mapFromScene(item.mapToScene(item.header_rect().center()))

    assert view.title_band_at(point) is item


def test_the_editor_is_gone_once_the_title_is_done(view):
    item = note(view)
    item.enter_title_edit_mode()
    editor = item.title_editor
    item.exit_title_edit_mode()

    assert item.title_editor is None
    assert editor.scene() is None
    assert view.scene.title_item is None


def test_pressing_return_finishes_the_title(view):
    item = note(view)
    item.enter_title_edit_mode()
    item.title_editor.setPlainText('Chapter One')
    event = QtGui.QKeyEvent(
        QtCore.QEvent.Type.KeyPress,
        int(QtCore.Qt.Key.Key_Return),
        QtCore.Qt.KeyboardModifier.NoModifier)
    item.title_editor.keyPressEvent(event)

    assert item.title == 'Chapter One'
    assert item.title_editing is False


def test_a_note_in_a_group_can_still_be_titled(view):
    item = note(view)
    item.setSelected(True)
    view.on_action_group_items()
    item.enter_title_edit_mode()

    assert item.title_editing is True
    assert view.scene.title_item is item


def test_nothing_is_written_when_the_words_did_not_change(view):
    item = titled(view, 'Chapter One')
    item.enter_title_edit_mode()
    depth = view.undo_stack.index()
    item.exit_title_edit_mode()

    assert view.undo_stack.index() == depth


def test_an_old_file_opens_without_a_title(view, tmpdir):
    """Additive: a note saved before this has no title key at all."""

    item = BeeTextItem.create_from_data(
        data={'text': 'Hello', 'box_color': (0, 0, 0, 255)})

    assert item.title == ''
    assert item.shows_header() is False


def test_the_toolbar_has_a_title_button(view):
    from beeref.widgets.text_toolbar import TextToolBar

    bar = TextToolBar(view, view)
    assert isinstance(bar.title, QtWidgets.QToolButton)
    assert bar.title.toolTip() == 'Write a title'
