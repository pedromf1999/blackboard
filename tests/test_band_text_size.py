import os

from PyQt6 import QtGui

from beeref import commands, fileio
from beeref.items import BeeGroupItem, BeePixmapItem, BeeTextItem


def picture(view, width=3000, height=2000):
    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(60, 60, 60))
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    return item


def titled_group(view, title='Enclosure'):
    item = picture(view)
    # Cleared first, or a group already selected is swallowed by the
    # new one and both names end up meaning the same group
    view.scene.clearSelection()
    item.setSelected(True)
    view.on_action_group_items()
    group = item.parentItem()
    group.title = title
    return group


def captioned(view, caption='A caption'):
    item = picture(view)
    item.caption = caption
    return item


def test_a_title_starts_at_the_size_the_box_gives_it(view):
    """Which is what every board written before this had."""

    group = titled_group(view)

    assert group.band_scale == 1
    assert group.title_size() == group.title_size_for(group.rect().width())


def test_the_title_can_be_made_bigger(view):
    group = titled_group(view)
    group.setSelected(True)
    before = group.title_size()
    band = group.header_height()

    view.on_action_size_increase()

    assert group.title_size() > before
    assert group.header_height() > band


def test_and_smaller_again(view):
    group = titled_group(view)
    group.setSelected(True)
    before = group.title_size()

    view.on_action_size_increase()
    view.on_action_size_decrease()

    assert round(group.title_size(), 6) == round(before, 6)


def test_the_title_size_has_a_floor_and_a_ceiling(view):
    from beeref.items import BAND_SCALE_MAX, BAND_SCALE_MIN

    group = titled_group(view)
    group.setSelected(True)

    for _ in range(40):
        view.on_action_size_decrease()
    assert group.band_scale == BAND_SCALE_MIN

    for _ in range(80):
        view.on_action_size_increase()
    assert group.band_scale == BAND_SCALE_MAX


def test_it_is_a_share_of_the_box_rather_than_a_size(view):
    """So a group that grows still grows its title, which is what made
    a title on a very large group readable at all."""

    group = titled_group(view)
    group.setSelected(True)
    view.on_action_size_increase()
    asked = group.band_scale

    wide = group.title_size_for(group.rect().width())
    wider = group.title_size_for(group.rect().width() * 2)

    assert wider > wide
    assert group.band_scale == asked


def test_making_it_bigger_is_one_step_to_undo(view):
    group = titled_group(view)
    group.setSelected(True)
    before = group.band_scale
    depth = view.undo_stack.index()

    view.on_action_size_increase()
    assert view.undo_stack.index() == depth + 1

    view.undo_stack.undo()
    assert group.band_scale == before


def test_the_size_is_saved_with_the_group(view, tmpdir):
    group = titled_group(view)
    group.setSelected(True)
    view.on_action_size_increase()
    asked = group.band_scale

    path = os.path.join(tmpdir, 'sized.blk')
    fileio.save_bee(path, view.scene, create_new=True)
    view.scene.clear()
    fileio.load_bee(path, view.scene)
    view.scene.add_queued_items()

    back = list(view.scene.items_by_type('group'))[0]
    assert round(back.band_scale, 6) == round(asked, 6)


def test_a_title_left_alone_saves_exactly_as_it_did(view):
    """Additive: a board written before there was a choice reads and
    writes the same either way."""

    group = titled_group(view)

    assert 'band_scale' not in group.get_extra_save_data()


def test_a_group_from_an_older_file_is_at_its_natural_size(view):
    group = BeeGroupItem.create_from_data(
        data={'title': 'Enclosure', 'box_color': (1, 2, 3, 255)})

    assert group.band_scale == 1


def test_a_copy_of_the_group_keeps_it(view):
    group = titled_group(view)
    group.setSelected(True)
    view.on_action_size_increase()
    copy = group.create_copy()

    assert copy.band_scale == group.band_scale


def test_a_caption_is_sized_while_it_is_being_written(view):
    """The buttons act on the words on screen, and while a caption is
    open those are the caption's."""

    item = captioned(view)
    item.setSelected(True)
    item.enter_caption_edit_mode()
    before = item.caption_size()
    band = item.caption_height()

    view.on_action_size_increase()

    assert item.caption_size() > before
    assert item.caption_height() > band


def test_sizing_the_caption_leaves_the_contour_alone(view):
    item = captioned(view)
    item.setSelected(True)
    view.on_action_image_outline()
    thickness = item.outline_width
    item.enter_caption_edit_mode()

    view.on_action_size_increase()

    assert item.outline_width == thickness
    assert item.band_scale > 1


def test_with_no_caption_open_the_buttons_size_the_contour(view):
    """Which is what they always did, and still do."""

    item = captioned(view)
    item.setSelected(True)
    view.on_action_image_outline()
    thickness = item.outline_width
    caption = item.caption_size()

    view.on_action_size_increase()

    assert item.outline_width > thickness
    assert item.caption_size() == caption


def test_the_caption_size_is_saved_with_the_picture(view, tmpdir):
    item = captioned(view)
    item.setSelected(True)
    item.enter_caption_edit_mode()
    view.on_action_size_increase()
    item.exit_caption_edit_mode()
    asked = item.band_scale

    path = os.path.join(tmpdir, 'caption.blk')
    fileio.save_bee(path, view.scene, create_new=True)
    view.scene.clear()
    fileio.load_bee(path, view.scene)
    view.scene.add_queued_items()

    back = list(view.scene.items_by_type('pixmap'))[0]
    assert round(back.band_scale, 6) == round(asked, 6)


def test_a_caption_left_alone_saves_exactly_as_it_did(view):
    item = captioned(view)

    assert 'band_scale' not in item.get_extra_save_data()


def test_a_notes_heading_keeps_its_own_kind_of_size(view):
    """A note's heading is a size in points rather than a share, so
    that making the note's own words bigger leaves it where it was."""

    note = BeeTextItem(text='Hello')
    view.scene.addItem(note)
    note.title = 'Chapter One'
    note.setSelected(True)
    note.enter_title_edit_mode()
    before = note.title_size()

    view.on_action_size_increase()

    assert note.title_size() > before
    assert note.stored_title_size() is not None


def test_the_group_bar_offers_the_pair(view):
    from beeref.widgets.group_toolbar import GroupToolBar

    bar = GroupToolBar(view, view)
    group = titled_group(view)
    bar.update_title(group)

    assert bar.smaller.isEnabled() is True
    assert bar.bigger.isEnabled() is True


def test_it_offers_them_only_once_there_is_a_title(view):
    from beeref.widgets.group_toolbar import GroupToolBar

    bar = GroupToolBar(view, view)
    group = titled_group(view, title='')
    bar.update_title(group)

    assert bar.smaller.isEnabled() is False
    assert bar.bigger.isEnabled() is False


def test_the_picture_bar_says_which_job_its_pair_is_doing(view):
    from beeref.widgets.image_toolbar import ImageToolBar

    bar = ImageToolBar(view, view)
    item = captioned(view)
    view.scene.clearSelection()
    item.setSelected(True)
    view.on_action_image_outline()

    bar.update_state([item])
    assert bar.thicker.toolTip() == 'Thicker outline'

    item.enter_caption_edit_mode()
    bar.update_state([item])
    assert bar.thicker.toolTip() == 'Bigger caption (Ctrl++)'
    assert bar.thinner.toolTip() == 'Smaller caption (Ctrl+-)'


def test_the_pair_works_on_a_caption_with_no_contour(view):
    """They used to be switched off unless the picture had one."""

    from beeref.widgets.image_toolbar import ImageToolBar

    bar = ImageToolBar(view, view)
    item = captioned(view)
    item.enter_caption_edit_mode()
    bar.update_state([item])

    assert item.has_outline() is False
    assert bar.thicker.isEnabled() is True


def test_a_selected_group_counts_as_something_to_size(view):
    """Or the menu entries, and the shortcuts with them, stay dead."""

    group = titled_group(view)
    view.scene.clearSelection()
    group.setSelected(True)

    assert view.scene.has_sizeable_selection() is True


def test_a_picture_with_nothing_to_size_does_not(view):
    item = picture(view)
    view.scene.clearSelection()
    item.setSelected(True)

    assert item.has_outline() is False
    assert view.scene.has_sizeable_selection() is False


def test_the_command_puts_every_selected_group_back(view):
    one = titled_group(view)
    two = titled_group(view)
    view.undo_stack.push(commands.ChangeBandTextScale([one, two], 1.5))

    assert one.band_scale == 1.5
    assert two.band_scale == 1.5
    view.undo_stack.undo()
    assert one.band_scale == 1
    assert two.band_scale == 1
