from unittest.mock import patch

from PyQt6 import QtCore, QtGui

from beeref.items import BeePixmapItem, without_pointless_alpha


def screenshot(width=800, height=600, see_through=0):
    """A picture with an alpha channel that nothing much uses.

    Which is what a screenshot is: opaque all over, with an alpha
    channel because that is how it was captured.
    """

    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor(90, 140, 190))
    for i in range(see_through):
        img.setPixelColor(i % width, i // width, QtGui.QColor(0, 0, 0, 0))
    return img


def cut_out():
    """A picture that really is see-through, and must stay that way."""

    img = QtGui.QImage(800, 600, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor(0, 0, 0, 0))
    painter = QtGui.QPainter(img)
    painter.fillRect(QtCore.QRect(100, 100, 300, 200), QtGui.QColor('red'))
    painter.end()
    return img


def test_a_screenshot_loses_an_alpha_channel_nothing_uses(view):
    """A handful of half-transparent pixels along an edge was enough to
    have a ten-megapixel screenshot kept as PNG."""

    assert screenshot().hasAlphaChannel() is True
    assert without_pointless_alpha(screenshot()).hasAlphaChannel() is False


def test_a_few_antialiased_pixels_do_not_save_it(view):
    """Which is all a screenshot of a drawing ever has."""

    img = screenshot(see_through=100)
    assert without_pointless_alpha(img).hasAlphaChannel() is False


def test_a_picture_that_is_really_cut_out_keeps_its_transparency(view):
    assert without_pointless_alpha(cut_out()).hasAlphaChannel() is True


def test_a_picture_with_no_alpha_channel_is_left_alone(view):
    img = QtGui.QImage(800, 600, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor('red'))
    assert without_pointless_alpha(img) is img


def test_nothing_is_dropped_when_a_format_was_asked_for_by_name(view,
                                                                settings):
    """Dropping the channel changes the picture, not just how it is
    stored, so it waits to be invited."""

    settings.setValue('Items/image_storage_format', 'png')
    assert without_pointless_alpha(screenshot()).hasAlphaChannel() is True


def test_the_padding_at_the_end_of_a_row_does_not_fool_it(view):
    """A row is padded out to a multiple of four bytes, and counting
    the padding would make a narrow picture look see-through."""

    assert without_pointless_alpha(
        screenshot(601, 600)).hasAlphaChannel() is False


def test_such_a_picture_is_then_stored_as_jpeg(view):
    """Which is the whole point: a board of screenshots came to three
    and a quarter gigabytes as PNG."""

    item = BeePixmapItem(without_pointless_alpha(screenshot()))
    data, formt = item.pixmap_to_bytes()
    assert formt == 'jpg'

    kept = BeePixmapItem(without_pointless_alpha(cut_out()))
    assert kept.pixmap_to_bytes()[1] == 'png'


def test_it_is_a_great_deal_smaller(view):
    """Measured on a real board: 1094 MB of screenshots came to 15."""

    img = screenshot(2000, 1500, see_through=100)
    painter = QtGui.QPainter(img)
    for i in range(0, 2000, 7):
        painter.setPen(QtGui.QColor(i % 255, (i * 3) % 255, 90))
        painter.drawLine(i, 0, 2000 - i, 1500)
    painter.end()

    as_png = BeePixmapItem(img).pixmap_to_bytes()
    as_jpg = BeePixmapItem(without_pointless_alpha(img)).pixmap_to_bytes()
    assert as_png[1] == 'png'
    assert as_jpg[1] == 'jpg'
    assert len(as_jpg[0]) < len(as_png[0]) / 2


def test_a_pasted_picture_goes_through_it(view):
    """Paste is where a screenshot arrives."""

    clipboard = QtGui.QGuiApplication.clipboard()
    with patch.object(type(clipboard), 'image', return_value=screenshot()):
        with patch.object(type(clipboard), 'mimeData',
                          return_value=QtCore.QMimeData()):
            view.on_action_paste()

    images = list(view.scene.items_by_type('pixmap'))
    assert len(images) == 1
    assert images[0].pixmap().hasAlphaChannel() is False
