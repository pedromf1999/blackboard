from unittest.mock import patch

import pytest
from PyQt6 import QtGui

from beeref import commands
from beeref.assets import BeeAssets
from beeref.items import BeeGroupItem, BeePixmapItem
from beeref.utils import readable_grey
from beeref.widgets.group_title import GroupTitleDialog


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


def test_the_dialog_puts_a_title_on(view):
    group = group_with_image(view)

    def answer(self):
        self.edit.setText('Lid Latch')
        self.header_color = QtGui.QColor('#e8a33d')
        return True

    with patch.object(GroupTitleDialog, 'exec', answer):
        view.on_action_group_title()

    assert group.title == 'Lid Latch'
    assert group.header_color == QtGui.QColor('#e8a33d')


def test_emptying_the_field_takes_the_title_off(view):
    """The same dialog puts one on and removes it."""

    group = group_with_image(view)
    group.title = 'Lid Latch'

    def answer(self):
        self.edit.setText('   ')
        return True

    with patch.object(GroupTitleDialog, 'exec', answer):
        view.on_action_group_title()

    assert group.title == ''
    assert group.header_height() == 0


def test_cancelling_leaves_the_group_alone(view):
    group = group_with_image(view)
    group.title = 'Lid Latch'

    with patch.object(GroupTitleDialog, 'exec', lambda self: 0):
        view.on_action_group_title()
    assert group.title == 'Lid Latch'


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


def test_the_board_shows_a_colour_while_it_is_being_picked(view):
    """Judging a colour against the dialog's own swatch is no judgement."""

    group = group_with_image(view)
    seen = []

    def answer(self):
        self.edit.setText('Lid Latch')
        self.header_color = QtGui.QColor('#e8a33d')
        self.show_preview()
        seen.append((group.title, QtGui.QColor(group.header_color)))
        return True

    with patch.object(GroupTitleDialog, 'exec', answer):
        view.on_action_group_title()

    # The band was on the board, words and all, before OK was pressed
    assert seen == [('Lid Latch', QtGui.QColor('#e8a33d'))]


def test_what_is_recorded_is_what_was_there_before_the_preview(view):
    group = group_with_image(view)

    def answer(self):
        self.edit.setText('Lid Latch')
        self.header_color = QtGui.QColor('#e8a33d')
        self.show_preview()
        return True

    with patch.object(GroupTitleDialog, 'exec', answer):
        view.on_action_group_title()
    assert group.title == 'Lid Latch'

    view.undo_stack.undo()
    assert group.title == ''
    assert group.header_color is None


def test_a_cancelled_dialog_takes_the_preview_back_off(view):
    group = group_with_image(view)

    def answer(self):
        self.edit.setText('Lid Latch')
        self.header_color = QtGui.QColor('#e8a33d')
        self.show_preview()
        return False

    with patch.object(GroupTitleDialog, 'exec', answer):
        view.on_action_group_title()

    assert group.title == ''
    assert group.header_color is None


def test_dropping_out_of_the_colour_dialog_keeps_the_colour_it_had(view):
    """Cancelling a colour must not leave the preview behind."""

    dialog = GroupTitleDialog(None, title='Lid Latch',
                              header_color=QtGui.QColor('#112233'))
    with patch('PyQt6.QtWidgets.QColorDialog.exec', return_value=0):
        dialog.on_pick_color()
    assert dialog.header_color == QtGui.QColor('#112233')
