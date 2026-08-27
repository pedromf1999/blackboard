from unittest.mock import patch

import pytest
from PyQt6 import QtCore, QtGui

from beeref import commands
from beeref.assets import BeeAssets
from beeref.items import BeeGroupItem, BeePixmapItem
from beeref.utils import readable_grey


def group_with_image(view, width=300, height=200):
    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor(70, 120, 190))
    group = BeeGroupItem()
    view.scene.addItem(group)
    child = BeePixmapItem(img)
    child.setParentItem(group)
    group.fit_to_children()
    group.setSelected(True)
    return group


def test_a_group_starts_with_no_title(view):
    group = group_with_image(view)
    assert group.title == ''
    assert group.header_height() == 0


def test_an_untitled_group_is_the_box_it_always_was(view):
    """Nothing visible, and no room taken for nothing."""

    group = group_with_image(view)
    before = group.rect()
    group.title = ''
    assert group.rect() == before


def test_a_title_takes_its_band_from_above_the_items(view):
    """The words must never come down over somebody's work."""

    group = group_with_image(view)
    before = group.rect()
    group.title = 'Lid Latch'

    assert group.rect().top() < before.top()
    assert group.rect().bottom() == pytest.approx(before.bottom())
    assert group.rect().height() == pytest.approx(
        before.height() + group.header_height())


def test_the_title_can_be_taken_off_again(view):
    group = group_with_image(view)
    before = group.rect()
    group.title = 'Lid Latch'
    group.title = ''

    assert group.header_height() == 0
    assert group.rect().height() == pytest.approx(before.height())
    assert group.rect().top() == pytest.approx(before.top())


def test_the_title_is_bold_and_in_the_bundled_face(view):
    """A title is not a note; it does not get to be either of those."""

    group = group_with_image(view)
    group.title = 'Lid Latch'
    font = group.title_font()

    assert font.bold() is True
    assert font.family() == BeeAssets().font_family


def test_the_band_follows_the_group_when_it_has_no_colour_of_its_own(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    assert group.header_color is None

    group.box_color = QtGui.QColor('#804020')
    assert group.visible_header_color() == QtGui.QColor('#804020')


def test_the_band_can_have_a_colour_apart_from_the_group(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    group.header_color = QtGui.QColor('#e8a33d')

    assert group.visible_header_color() == QtGui.QColor('#e8a33d')
    assert group.box_color != group.header_color


def test_the_title_reacts_to_the_colour_it_sits_on(view):
    """Dark letters on a light band, light letters on a dark one."""

    group = group_with_image(view)
    group.title = 'Lid Latch'

    group.header_color = QtGui.QColor('#e8a33d')
    assert readable_grey(group.visible_header_color()) == QtGui.QColor(
        'black')
    group.header_color = QtGui.QColor('#2f6f4f')
    assert readable_grey(group.visible_header_color()) == QtGui.QColor(
        'white')


def test_the_title_grows_with_the_group(view):
    """A fixed size is a shout on a small group and a whisper on a big one."""

    small = group_with_image(view, 200, 150)
    big = group_with_image(view, 2000, 1500)
    small.title = big.title = 'Lid Latch'

    assert (big.title_font().pointSizeF()
            > small.title_font().pointSizeF() * 5)


def test_the_title_and_its_colour_are_saved_and_read_back(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    group.header_color = QtGui.QColor('#e8a33d')

    clone = BeeGroupItem.create_from_data(
        data=group.get_extra_save_data())
    assert clone.title == 'Lid Latch'
    assert clone.header_color == QtGui.QColor('#e8a33d')


def test_a_band_with_no_colour_of_its_own_stays_that_way(view):
    """Saved as nothing, so it goes on following the group."""

    group = group_with_image(view)
    group.title = 'Lid Latch'
    data = group.get_extra_save_data()
    assert data['header_color'] is None

    clone = BeeGroupItem.create_from_data(data=data)
    assert clone.header_color is None


def test_a_board_written_before_titles_existed_still_opens(view):
    group = BeeGroupItem.create_from_data(
        data={'box_color': (1, 2, 3, 255), 'locked': False})
    assert group.title == ''
    assert group.header_color is None


def test_a_copied_group_keeps_its_title(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    group.header_color = QtGui.QColor('#e8a33d')

    copy = group.create_copy()
    assert copy.title == 'Lid Latch'
    assert copy.header_color == QtGui.QColor('#e8a33d')


def test_the_title_can_be_undone(view):
    group = group_with_image(view)
    view.undo_stack.push(commands.ChangeGroupTitle(
        [group], 'Lid Latch', QtGui.QColor('#e8a33d')))
    assert group.title == 'Lid Latch'

    view.undo_stack.undo()
    assert group.title == ''
    assert group.header_color is None


def test_the_command_says_so_when_nothing_is_a_group(view):
    img = QtGui.QImage(10, 10, QtGui.QImage.Format.Format_ARGB32)
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    item.setSelected(True)

    with patch('beeref.widgets.BeeNotification') as notification:
        view.on_action_group_title()
    assert notification.called


def test_a_title_is_centred_unless_told_otherwise(view):
    """What titles did before there was a choice."""

    group = group_with_image(view)
    group.title = 'Lid Latch'
    assert group.title_align == BeeGroupItem.TITLE_CENTER


def test_a_title_can_sit_on_the_left(view):
    from PyQt6.QtCore import Qt

    group = group_with_image(view)
    group.title_align = BeeGroupItem.TITLE_LEFT
    assert group.title_alignment() & Qt.AlignmentFlag.AlignLeft
    assert group.title_alignment() & Qt.AlignmentFlag.AlignVCenter


def test_a_nonsense_alignment_falls_back_to_centred(view):
    group = BeeGroupItem(title='x', title_align='sideways')
    assert group.title_align == BeeGroupItem.TITLE_CENTER


def test_the_alignment_is_saved_and_read_back(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    group.title_align = BeeGroupItem.TITLE_LEFT

    clone = BeeGroupItem.create_from_data(data=group.get_extra_save_data())
    assert clone.title_align == BeeGroupItem.TITLE_LEFT


def test_a_board_written_before_alignment_existed_is_centred(view):
    group = BeeGroupItem.create_from_data(
        data={'box_color': (1, 2, 3, 255), 'title': 'Lid Latch'})
    assert group.title_align == BeeGroupItem.TITLE_CENTER


def test_a_copied_group_keeps_its_alignment(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    group.title_align = BeeGroupItem.TITLE_LEFT
    assert group.create_copy().title_align == BeeGroupItem.TITLE_LEFT


def test_the_alignment_can_be_undone(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    view.undo_stack.push(commands.ChangeGroupTitle(
        [group], 'Lid Latch', None, BeeGroupItem.TITLE_LEFT))
    assert group.title_align == BeeGroupItem.TITLE_LEFT

    view.undo_stack.undo()
    assert group.title_align == BeeGroupItem.TITLE_CENTER


def type_title(group, text):
    """What the user typing into the band amounts to."""

    group.title_editor.setPlainText(text)


def test_the_title_is_written_on_the_group_itself(view):
    """No dialog: the band opens where the title is going to be."""

    group = group_with_image(view)
    group.setSelected(True)
    view.on_action_group_title()

    assert group.title_editing is True
    assert group.title_editor is not None
    assert view.scene.title_group is group
    # The band is there to type into, before the first letter
    assert group.shows_header() is True
    assert group.header_height() > 0


def test_what_is_typed_becomes_the_title(view):
    group = group_with_image(view)
    group.setSelected(True)
    view.on_action_group_title()
    type_title(group, 'Lid Latch')
    group.exit_title_edit_mode()

    assert group.title == 'Lid Latch'
    assert group.title_editing is False
    assert group.title_editor is None
    assert view.scene.title_group is None


def test_writing_nothing_leaves_the_group_without_a_header(view):
    group = group_with_image(view)
    before = group.rect()
    group.setSelected(True)
    view.on_action_group_title()
    group.exit_title_edit_mode()

    assert group.title == ''
    assert group.shows_header() is False
    assert group.rect().height() == pytest.approx(before.height())


def test_escaping_throws_the_change_away(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    group.setSelected(True)
    view.on_action_group_title()
    type_title(group, 'Something else')
    group.exit_title_edit_mode(commit=False)

    assert group.title == 'Lid Latch'


def test_the_written_title_can_be_undone(view):
    group = group_with_image(view)
    group.setSelected(True)
    view.on_action_group_title()
    type_title(group, 'Lid Latch')
    group.exit_title_edit_mode()

    view.undo_stack.undo()
    assert group.title == ''


def test_the_box_does_not_chase_the_words_being_typed(view):
    """The editor is parented to the group, so it must not be measured
    as one of the group's items."""

    group = group_with_image(view)
    group.setSelected(True)
    view.on_action_group_title()
    with_band = group.rect()
    type_title(group, 'A title that is really quite long indeed')
    group.fit_to_children()

    assert group.rect().width() == pytest.approx(with_band.width())


def test_the_colour_button_colours_the_title_while_one_is_written(view):
    """The same button, doing whatever the colour on screen is at
    that moment."""

    group = group_with_image(view)
    group.setSelected(True)
    view.update_group_toolbar()
    assert view.group_toolbar.writing_title is False

    view.on_action_group_title()
    view.update_group_toolbar()
    assert view.group_toolbar.writing_title is True
    assert view.group_toolbar.color.toolTip() == 'Title colour'

    with patch.object(view, 'on_action_group_title_color') as titled:
        view.group_toolbar.on_color()
    assert titled.called


def test_the_colour_button_colours_the_group_the_rest_of_the_time(view):
    group = group_with_image(view)
    group.setSelected(True)
    view.update_group_toolbar()

    with patch.object(view, 'on_action_group_box_color') as boxed:
        view.group_toolbar.on_color()
    assert boxed.called


def test_the_title_colour_shows_on_the_board_as_it_is_picked(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    group.setSelected(True)
    seen = []

    def picked(title, initial, preview, **kwargs):
        preview(QtGui.QColor('#e8a33d'))
        seen.append(QtGui.QColor(group.header_color))
        return QtGui.QColor('#e8a33d')

    with patch.object(view, 'pick_color_live', side_effect=picked):
        view.on_action_group_title_color()

    assert seen == [QtGui.QColor('#e8a33d')]
    assert group.header_color == QtGui.QColor('#e8a33d')


def test_the_alignment_buttons_show_which_way_the_title_sits(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    group.setSelected(True)
    view.update_group_toolbar()

    assert view.group_toolbar.align_center.isChecked() is True
    assert view.group_toolbar.align_left.isChecked() is False

    view.on_action_group_title_align_left()
    assert group.title_align == BeeGroupItem.TITLE_LEFT
    assert view.group_toolbar.align_left.isChecked() is True


def test_alignment_waits_until_there_is_a_title_to_align(view):
    group = group_with_image(view)
    group.setSelected(True)
    view.update_group_toolbar()
    assert view.group_toolbar.align_left.isEnabled() is False

    group.title = 'Lid Latch'
    view.update_group_toolbar()
    assert view.group_toolbar.align_left.isEnabled() is True


def test_aligning_mid_writing_records_nothing_yet(view):
    """The title is still in the editor; it goes on the stack when done."""

    group = group_with_image(view)
    group.setSelected(True)
    view.on_action_group_title()
    depth = view.undo_stack.index()

    view.on_action_group_title_align_left()
    assert group.title_align == BeeGroupItem.TITLE_LEFT
    assert view.undo_stack.index() == depth


def test_the_text_tool_opens_a_title_instead_of_covering_it(view):
    """A group's title is text too, and the tool is for reaching text."""

    group = group_with_image(view)
    group.title = 'Lid Latch'
    point = view.mapFromScene(
        group.mapToScene(group.header_rect().center()))

    assert view.group_header_at(point) is group
    view.write_note_at(point)
    assert group.title_editing is True
    # And no note was laid over the band
    assert view.scene.selected_text_items() == []


def test_the_text_tool_still_writes_a_note_below_the_band(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    inside = group.rect().center()
    point = view.mapFromScene(group.mapToScene(inside))

    assert view.group_header_at(point) is None


def test_an_untitled_group_has_no_band_for_the_tool_to_find(view):
    group = group_with_image(view)
    point = view.mapFromScene(group.mapToScene(group.rect().topLeft()))
    assert view.group_header_at(point) is None


def test_a_locked_group_keeps_its_title_to_itself(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    group.locked = True
    point = view.mapFromScene(
        group.mapToScene(group.header_rect().center()))

    view.write_note_at(point)
    assert group.title_editing is False


def test_clicking_away_finishes_the_title(view):
    group = group_with_image(view)
    group.setSelected(True)
    view.on_action_group_title()
    type_title(group, 'Lid Latch')

    view.scene.title_group.exit_title_edit_mode()
    assert group.title == 'Lid Latch'
    assert view.scene.title_group is None


def double_click(view, group, point):
    """A double click on the group, at a point in its own coordinates."""

    return view.scene.title_double_clicked(
        group, group.mapToScene(point))


def test_double_clicking_the_band_opens_the_title(view):
    """Words are opened by double-clicking them everywhere else."""

    group = group_with_image(view)
    group.title = 'Lid Latch'

    assert double_click(view, group, group.header_rect().center()) is True
    assert group.title_editing is True
    assert group.isSelected() is True


def test_double_clicking_the_rest_of_the_box_does_not(view):
    """That still zooms to the group, as it always did."""

    group = group_with_image(view)
    group.title = 'Lid Latch'

    assert double_click(view, group, group.rect().center()) is False
    assert group.title_editing is False


def test_a_group_with_no_band_has_nothing_to_open(view):
    group = group_with_image(view)
    assert double_click(view, group, group.rect().topLeft()) is False


def test_a_locked_group_keeps_its_title_shut(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'
    group.locked = True

    assert double_click(view, group, group.header_rect().center()) is False
    assert group.title_editing is False


def test_an_image_is_not_a_group(view):
    from beeref.items import BeePixmapItem
    item = BeePixmapItem(QtGui.QImage(
        10, 10, QtGui.QImage.Format.Format_ARGB32))
    view.scene.addItem(item)

    assert view.scene.title_double_clicked(item, QtCore.QPointF(0, 0)) is False
