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


def test_only_the_word_is_repainted(qapp):
    """The icon is left as drawn; only the word beside it turns white.

    The artwork has the word in black, for a light background, while
    the icon is already a dark tile with a light B.
    """

    assets = BeeAssets()
    plain = assets.wordmark(400)
    lit = assets.wordmark(400, light_word=True)

    assert plain is not None
    assert plain.width() == 400
    assert lit.size() == plain.size()

    split = round(400 * assets.WORDMARK_SPLIT)

    # The icon is untouched
    for x in range(0, split, 5):
        for y in range(0, plain.height(), 5):
            assert lit.pixelColor(x, y) == plain.pixelColor(x, y)

    # The word is white wherever it has ink
    inked = 0
    for x in range(split, 400, 5):
        for y in range(0, plain.height(), 5):
            pixel = lit.pixelColor(x, y)
            if pixel.alpha() > 200:
                inked += 1
                assert (pixel.red(), pixel.green(), pixel.blue()) == (
                    255, 255, 255)
    assert inked > 0, 'the word has to be there'


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


def test_background_is_black(view):
    """Pure black, not the canvas colour."""

    overlay = view.loading_overlay
    overlay.start()
    image = overlay.grab().toImage()
    assert image.pixelColor(3, 3) == QtGui.QColor(0, 0, 0)


def test_progress_bar_sits_below_the_wordmark(view):
    """Centred, it would cover the very thing it is shown over."""

    from beeref.widgets import BeeProgressDialog
    from unittest.mock import MagicMock

    dialog = BeeProgressDialog('Loading', worker=MagicMock(), parent=view)
    dialog.move_below_center()

    middle = view.mapToGlobal(view.rect().center()).y()
    assert dialog.y() > middle
    dialog.deleteLater()
