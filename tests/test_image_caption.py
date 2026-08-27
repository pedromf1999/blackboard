from unittest.mock import patch

from PyQt6 import QtCore, QtGui

from beeref import commands
from beeref.items import BeePixmapItem


def image(view, width=300, height=200):
    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor('red'))
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    item.setSelected(True)
    return item


def test_a_picture_starts_with_no_caption(view):
    item = image(view)
    assert item.caption == ''
    assert item.caption_height() == 0


def test_the_caption_is_written_on_the_picture(view):
    item = image(view)
    view.on_action_image_caption()

    assert item.caption_editing is True
    assert view.scene.caption_item is item
    # The band is there to type into, before the first letter
    assert item.shows_caption() is True
    assert item.caption_height() > 0


def test_what_is_typed_becomes_the_caption(view):
    item = image(view)
    view.on_action_image_caption()
    item.caption_editor.setPlainText('Top view')
    item.exit_caption_edit_mode()

    assert item.caption == 'Top view'
    assert item.caption_editing is False
    assert view.scene.caption_item is None


def test_writing_nothing_leaves_no_band(view):
    item = image(view)
    view.on_action_image_caption()
    item.exit_caption_edit_mode()

    assert item.caption == ''
    assert item.shows_caption() is False


def test_escaping_throws_the_change_away(view):
    item = image(view)
    item.caption = 'Top view'
    view.on_action_image_caption()
    item.caption_editor.setPlainText('Something else')
    item.exit_caption_edit_mode(commit=False)

    assert item.caption == 'Top view'


def test_the_caption_can_be_undone(view):
    item = image(view)
    view.on_action_image_caption()
    item.caption_editor.setPlainText('Top view')
    item.exit_caption_edit_mode()

    view.undo_stack.undo()
    assert item.caption == ''


def test_the_band_hangs_under_the_picture(view):
    """Over it, a caption would cover the very thing it describes."""

    item = image(view)
    item.caption = 'Top view'
    band = item.caption_rect()

    assert band.top() == item.crop.bottom()
    assert band.width() == item.crop.width()


def test_the_picture_keeps_its_own_rectangle(view):
    """So the handles and a joined line do not move because of a
    caption."""

    item = image(view)
    logical = item.bounding_rect_unselected()
    painted = item.boundingRect()
    item.caption = 'Top view'

    assert item.bounding_rect_unselected() == logical
    assert item.boundingRect().height() > painted.height()


def test_the_band_can_be_clicked(view):
    """It is part of the picture as far as the mouse is concerned."""

    item = image(view)
    item.caption = 'Top view'
    assert item.shape().contains(item.caption_rect().center()) is True


def test_the_caption_follows_a_crop(view):
    """A picture cut down to a corner takes its caption with it."""

    item = image(view, 400, 300)
    item.caption = 'Top view'
    item.crop = QtCore.QRectF(50, 20, 100, 60)
    band = item.caption_rect()

    assert band.left() == 50
    assert band.width() == 100
    assert band.top() == 80


def test_the_letters_are_measured_against_what_is_left(view):
    """Not against the file it came from, or a crop would be shouted."""

    item = image(view, 400, 300)
    item.caption = 'Top view'
    whole = item.caption_size()
    item.crop = QtCore.QRectF(0, 0, 100, 60)

    assert item.caption_size() < whole


def test_the_caption_is_bold_and_in_the_bundled_face(view):
    from beeref.assets import BeeAssets

    item = image(view)
    item.caption = 'Top view'
    font = item.caption_font()

    assert font.bold() is True
    assert font.family() == BeeAssets().font_family


def test_the_band_can_have_its_own_colour(view):
    item = image(view)
    item.caption = 'Top view'
    chosen = QtGui.QColor('#e8a33d')

    with patch.object(view, 'pick_color_live', return_value=chosen):
        view.on_action_image_caption_color()
    assert item.caption_color == chosen


def test_the_colour_button_colours_the_caption_while_one_is_written(view):
    image(view)
    view.update_image_toolbar()
    assert view.image_toolbar.writing_caption is False

    view.on_action_image_caption()
    view.update_image_toolbar()
    assert view.image_toolbar.writing_caption is True
    assert view.image_toolbar.color.toolTip() == 'Caption colour'

    with patch.object(view, 'on_action_image_caption_color') as called:
        view.image_toolbar.on_color()
    assert called.called


def test_the_colour_button_colours_the_outline_the_rest_of_the_time(view):
    image(view)
    view.on_action_image_outline()
    view.update_image_toolbar()

    with patch.object(view, 'on_action_image_outline_color') as called:
        view.image_toolbar.on_color()
    assert called.called


def test_double_clicking_the_band_opens_it(view):
    item = image(view)
    item.caption = 'Top view'

    assert view.scene.caption_double_clicked(
        item, item.mapToScene(item.caption_rect().center())) is True
    assert item.caption_editing is True


def test_double_clicking_the_picture_does_not(view):
    item = image(view)
    item.caption = 'Top view'

    assert view.scene.caption_double_clicked(
        item, item.mapToScene(item.crop.center())) is False


def test_the_caption_is_saved_and_read_back(view):
    item = image(view)
    item.caption = 'Top view'
    item.caption_color = QtGui.QColor('#e8a33d')

    clone = BeePixmapItem(QtGui.QImage(
        300, 200, QtGui.QImage.Format.Format_ARGB32))
    BeePixmapItem.create_from_data(item=clone,
                                   data=item.get_extra_save_data())
    assert clone.caption == 'Top view'
    assert clone.caption_color == QtGui.QColor('#e8a33d')


def test_a_board_written_before_captions_existed_opens_without_one(view):
    item = BeePixmapItem(QtGui.QImage(
        10, 10, QtGui.QImage.Format.Format_ARGB32))
    BeePixmapItem.create_from_data(item=item, data={'filename': 'old.png'})

    assert item.caption == ''
    assert item.shows_caption() is False


def test_the_command_sets_both_at_once(view):
    item = image(view)
    view.undo_stack.push(commands.ChangeCaption(
        [item], 'Top view', QtGui.QColor('#e8a33d')))

    assert item.caption == 'Top view'
    assert item.caption_color == QtGui.QColor('#e8a33d')

    view.undo_stack.undo()
    assert item.caption == ''
