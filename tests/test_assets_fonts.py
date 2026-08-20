from unittest.mock import patch

from PyQt6 import QtGui, QtWidgets

from beeref.assets import BeeAssets


def fresh_assets():
    """A new BeeAssets, bypassing the singleton."""

    BeeAssets._instance = None
    assets = BeeAssets()
    BeeAssets._instance = None
    return assets


def test_bundled_font_is_loaded(qapp):
    assert fresh_assets().font_family == 'Ranade'


def test_bundled_font_is_known_to_qt(qapp):
    family = fresh_assets().font_family
    assert family in QtGui.QFontDatabase.families()


def test_bundled_font_has_the_usual_styles(qapp):
    family = fresh_assets().font_family
    styles = QtGui.QFontDatabase.styles(family)
    for style in ('Regular', 'Bold', 'Italic', 'Bold Italic'):
        assert style in styles


@patch('PyQt6.QtGui.QFontDatabase.addApplicationFont', return_value=-1)
def test_falls_back_when_fonts_cannot_be_loaded(font_mock, qapp):
    # The application keeps working with the default font
    assert fresh_assets().font_family is None


def test_font_files_are_shipped():
    fontdir = BeeAssets.PATH.joinpath('fonts')
    names = {path.name for path in fontdir.iterdir()}
    assert 'Ranade-Regular.otf' in names
    assert 'Ranade-Bold.otf' in names
    assert 'Ranade-Italic.otf' in names
    assert 'Ranade-BoldItalic.otf' in names
    # The font's licence travels with it
    assert 'FFL.txt' in names


def test_text_items_use_the_interface_font(qapp):
    """New notes are written in the interface font.

    Ranade used to be forced on every note. It is one of two choices
    now, reachable from the button beside bold.
    """

    from beeref.items import BeeTextItem

    interface = QtWidgets.QApplication.instance().font().family()
    assert BeeTextItem('foo').font().family() == interface


def test_the_bundled_font_is_still_offered(qapp):
    from beeref.items import BeeTextItem

    interface, bundled = BeeTextItem('foo').font_families()
    assert bundled == 'Ranade'
    assert bundled != interface


def test_interface_keeps_the_system_font(qapp):
    """The menus stay on the system font, which suits small sizes."""

    assert QtWidgets.QApplication.instance().font().family() != 'Ranade'


def test_stored_text_keeps_the_font_it_was_written_in(qapp):
    """Opening a board must not rewrite the fonts chosen in it.

    Every note used to be forced to the canvas font on load,
    which would now throw away a choice of font each time a
    board was reopened.
    """

    from beeref.items import BeeTextItem

    old_html = (
        '<html><head><meta name="qrichtext" content="1" /></head>'
        '<body style=" font-family:\'Some Old Font\'; font-size:9pt;">'
        '<p>an old note</p></body></html>')
    item = BeeTextItem(html=old_html)

    cursor = item.textCursor()
    cursor.select(QtGui.QTextCursor.SelectionType.Document)
    assert cursor.charFormat().font().family() == 'Some Old Font'
    assert item.toPlainText() == 'an old note'


def test_text_items_fall_back_when_font_missing(qapp):
    """Without the bundled font, text items still work."""

    from beeref.items import BeeTextItem

    BeeAssets._instance = None
    with patch('PyQt6.QtGui.QFontDatabase.addApplicationFont',
               return_value=-1):
        BeeAssets()
        item = BeeTextItem('foo')
        assert item.toPlainText() == 'foo'
        assert item.font().family()
    BeeAssets._instance = None
