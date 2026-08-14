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


def test_text_items_use_the_application_font(qapp):
    from beeref.items import BeeTextItem

    font = QtWidgets.QApplication.instance().font()
    item = BeeTextItem('foo')
    assert item.font().family() == font.family()


def test_stored_text_gets_the_application_font(qapp):
    """Text written before the font changed is brought up to date."""

    from beeref.items import BeeTextItem

    old_html = (
        '<html><head><meta name="qrichtext" content="1" /></head>'
        '<body style=" font-family:\'Some Old Font\'; font-size:9pt;">'
        '<p>an old note</p></body></html>')
    item = BeeTextItem(html=old_html)

    cursor = item.textCursor()
    cursor.select(QtGui.QTextCursor.SelectionType.Document)
    expected = QtWidgets.QApplication.instance().font().family()
    assert cursor.charFormat().font().family() == expected
    assert item.toPlainText() == 'an old note'
