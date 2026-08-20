from unittest.mock import patch

from PyQt6 import QtGui

from beeref.assets import BeeAssets


def test_hidden_until_a_board_is_opened(view):
    assert view.loading_overlay.isVisible() is False


def test_shown_while_opening_and_hidden_after(view, tmpdir):
    """A board arrives item by item; the wordmark covers that up."""

    overlay = view.loading_overlay
    with patch('beeref.fileio.ThreadedIO'), \
         patch('beeref.widgets.BeeProgressDialog'):
        view.open_from_file(str(tmpdir.join('board.blk')))
    assert overlay.isVisible() is True
    assert overlay.size() == view.size()

    # Reporting a failure opens a message box, which would wait for
    # somebody to click it
    with patch('PyQt6.QtWidgets.QMessageBox.warning'):
        view.on_loading_finished('', ['could not read'])
    assert overlay.isVisible() is False


def test_wordmark_is_inverted_for_a_dark_canvas(qapp):
    """The artwork is dark, meant for a light background."""

    plain = BeeAssets().wordmark(400)
    inverted = BeeAssets().wordmark(400, inverted=True)

    assert plain is not None
    assert plain.width() == 400
    assert inverted.size() == plain.size()

    # Somewhere in the word, the two are opposites of each other
    differences = 0
    for x in range(0, plain.width(), 7):
        for y in range(0, plain.height(), 7):
            one = plain.pixelColor(x, y)
            other = inverted.pixelColor(x, y)
            if one.alpha() > 200 and one.red() + other.red() == 255:
                differences += 1
    assert differences > 0


def test_wordmark_is_shipped():
    assert BeeAssets.PATH.joinpath('wordmark.svg').exists()


def test_overlay_paints_the_wordmark(view):
    overlay = view.loading_overlay
    overlay.start()
    image = overlay.grab().toImage()

    background = image.pixelColor(2, 2)
    middle = image.pixelColor(image.width() // 2, image.height() // 2)
    assert middle != background, 'the wordmark has to be visible on it'
    assert QtGui.QColor(middle).lightness() > QtGui.QColor(
        background).lightness()
