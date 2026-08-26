from unittest.mock import patch

from PyQt6 import QtCore, QtGui

from beeref import commands
from beeref.items import BeePixmapItem


def image(view, width=200, height=100):
    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor('red'))
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    item.setSelected(True)
    return item


def test_the_bar_follows_a_selected_image(view):
    """Cropping used to be a menu away from the picture it was aimed at."""

    item = image(view)
    assert view.image_toolbar.isHidden() is False
    item.setSelected(False)
    view.update_image_toolbar()
    assert view.image_toolbar.isHidden() is True


def test_cropping_is_offered_for_one_image_at_a_time(view):
    """Crop mode has handles, and they belong to a single picture."""

    image(view)
    view.update_image_toolbar()
    assert view.image_toolbar.crop.isEnabled() is True

    image(view)
    view.update_image_toolbar()
    assert view.image_toolbar.crop.isEnabled() is False


def test_an_image_starts_with_no_contour(view):
    item = image(view)
    assert item.has_outline() is False
    assert view.image_toolbar.outline.isChecked() is False
    assert view.image_toolbar.thicker.isEnabled() is False


def test_the_contour_goes_on_and_off(view):
    item = image(view)
    view.on_action_image_outline()
    assert item.has_outline() is True
    assert view.image_toolbar.outline.isChecked() is True

    view.on_action_image_outline()
    assert item.has_outline() is False


def test_a_second_press_takes_it_off_all_of_them(view):
    """Otherwise a mixed selection flips one image at a time forever."""

    first, second = image(view), image(view)
    view.on_action_image_outline()
    assert (first.has_outline(), second.has_outline()) == (True, True)
    view.on_action_image_outline()
    assert (first.has_outline(), second.has_outline()) == (False, False)


def test_a_mixed_selection_gets_a_contour_rather_than_losing_one(view):
    first, second = image(view), image(view)
    first.set_outline_width(first.default_outline_width())
    view.on_action_image_outline()
    assert (first.has_outline(), second.has_outline()) == (True, True)


def test_the_contour_starts_proportional_to_the_picture(view):
    """A fixed number of pixels is a hairline on one image and a frame
    on another."""

    small = image(view, 100, 100)
    big = image(view, 1000, 1000)
    assert big.default_outline_width() > small.default_outline_width() * 5


def test_the_size_buttons_change_the_contour(view):
    item = image(view)
    view.on_action_image_outline()
    before = item.outline_width
    view.on_action_size_increase()
    assert item.outline_width > before
    view.on_action_size_decrease()
    assert item.outline_width == before


def test_an_image_without_a_contour_is_left_alone(view):
    """The size buttons change a contour; they do not put one on."""

    item = image(view)
    view.on_action_size_increase()
    assert item.has_outline() is False


def test_the_contour_stops_before_it_eats_the_picture(view):
    item = image(view, 200, 100)
    view.on_action_image_outline()
    for _ in range(50):
        view.on_action_size_increase()
    assert item.outline_width == item.max_outline_width()


def test_holding_at_the_limit_records_nothing_to_undo(view):
    """Otherwise the stack fills with steps that changed nothing."""

    item = image(view)
    view.on_action_image_outline()
    for _ in range(50):
        view.on_action_size_increase()
    depth = view.undo_stack.index()
    view.on_action_size_increase()
    assert view.undo_stack.index() == depth

    view.undo_stack.undo()
    assert item.outline_width < item.max_outline_width()


def test_the_picture_keeps_its_own_rectangle(view):
    """The contour must not push the handles or a joined line outward."""

    item = image(view)
    logical = item.bounding_rect_unselected()
    painted = item.boundingRect()
    view.on_action_image_outline()

    assert item.bounding_rect_unselected() == logical
    # But there is room to paint it in
    assert item.boundingRect().width() > painted.width()


def test_the_contour_is_saved_and_read_back(view):
    item = image(view)
    view.on_action_image_outline()
    data = item.get_extra_save_data()

    clone = BeePixmapItem(QtGui.QImage(200, 100,
                                       QtGui.QImage.Format.Format_ARGB32))
    BeePixmapItem.create_from_data(item=clone, data=data)
    assert clone.outline_width == item.outline_width
    assert clone.outline_color == item.outline_color


def test_a_file_written_before_contours_existed_still_opens(view):
    """The keys are simply absent, and absent has to mean no contour."""

    item = BeePixmapItem(QtGui.QImage(10, 10,
                                      QtGui.QImage.Format.Format_ARGB32))
    BeePixmapItem.create_from_data(item=item, data={'filename': 'old.png'})
    assert item.has_outline() is False


def paint_extent(item):
    """Where the contour actually lands, in item coordinates."""

    box = item.crop.adjusted(-200, -200, 200, 200)
    canvas = QtGui.QImage(int(box.width()), int(box.height()),
                          QtGui.QImage.Format.Format_ARGB32)
    canvas.fill(QtGui.QColor(0, 0, 0, 0))
    painter = QtGui.QPainter(canvas)
    painter.translate(-box.topLeft())
    item.paint_outline(painter)
    painter.end()
    drawn = [(x, y) for x in range(canvas.width())
             for y in range(canvas.height())
             if canvas.pixelColor(x, y).alpha() > 20]
    xs = [x for x, _ in drawn]
    ys = [y for _, y in drawn]
    return QtCore.QRectF(min(xs) + box.x(), min(ys) + box.y(),
                         max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def test_the_contour_frames_what_is_left_after_a_crop(view):
    item = image(view, 400, 300)
    view.on_action_image_outline()
    item.crop = QtCore.QRectF(150, 120, 60, 40)

    drawn = paint_extent(item)
    assert drawn.center().x() == item.crop.center().x()
    assert drawn.center().y() == item.crop.center().y()
    assert drawn.width() < item.crop.width() * 2


def test_cropping_small_thins_a_contour_that_no_longer_fits(view):
    """A frame is measured against the picture it frames.

    Cropping a photograph down to a stamp used to leave the frame at
    its old thickness, ten times wider than what was left of the image.
    """

    item = image(view, 400, 300)
    view.on_action_image_outline()
    for _ in range(20):
        view.on_action_size_increase()
    thick = item.outline_width

    item.crop = QtCore.QRectF(150, 120, 40, 30)
    assert item.outline_width < thick
    assert item.outline_width <= item.max_outline_width()


def test_undoing_a_crop_gives_the_frame_back_too(view):
    item = image(view, 400, 300)
    view.on_action_image_outline()
    for _ in range(20):
        view.on_action_size_increase()
    thick = item.outline_width

    view.undo_stack.push(
        commands.CropItem(item, QtCore.QRectF(150, 120, 40, 30)))
    assert item.outline_width < thick

    view.undo_stack.undo()
    assert item.outline_width == thick


def test_an_image_can_be_built_before_its_crop_is_known(view):
    """The crop setter reads the contour, so the contour has to come first."""

    item = BeePixmapItem(QtGui.QImage(10, 10,
                                      QtGui.QImage.Format.Format_ARGB32))
    assert item.outline_width == 0


def test_the_contour_colour_can_be_chosen(view):
    item = image(view)
    view.on_action_image_outline()
    chosen = QtGui.QColor('#ff8800')

    with patch.object(view, 'pick_color_live', return_value=chosen):
        view.on_action_image_outline_color()
    assert item.outline_color == chosen


def test_a_cancelled_colour_dialog_leaves_the_contour_alone(view):
    item = image(view)
    view.on_action_image_outline()
    before = item.outline_color

    with patch.object(view, 'pick_color_live', return_value=None):
        view.on_action_image_outline_color()
    assert item.outline_color == before


def test_the_preview_is_not_what_gets_recorded(view):
    """The undo command must find the colour from before the preview."""

    item = image(view)
    view.on_action_image_outline()
    original = QtGui.QColor(item.outline_color)

    def picked(title, initial, preview, **kwargs):
        preview(QtGui.QColor('#00ff00'))
        return QtGui.QColor('#0000ff')

    with patch.object(view, 'pick_color_live', side_effect=picked):
        view.on_action_image_outline_color()
    assert item.outline_color == QtGui.QColor('#0000ff')

    view.undo_stack.undo()
    assert item.outline_color == original


def test_the_colour_button_waits_for_a_contour(view):
    image(view)
    view.update_image_toolbar()
    assert view.image_toolbar.color.isEnabled() is False
    view.on_action_image_outline()
    assert view.image_toolbar.color.isEnabled() is True


def test_the_contour_colour_is_saved_and_read_back(view):
    item = image(view)
    view.on_action_image_outline()
    item.outline_color = QtGui.QColor('#ff8800')

    clone = BeePixmapItem(QtGui.QImage(200, 100,
                                       QtGui.QImage.Format.Format_ARGB32))
    BeePixmapItem.create_from_data(item=clone,
                                   data=item.get_extra_save_data())
    assert clone.outline_color == QtGui.QColor('#ff8800')
