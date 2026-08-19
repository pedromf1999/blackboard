import pathlib
from unittest.mock import patch

from PyQt6 import QtGui

from beeref.assets import BeeAssets


def test_singleton(view):
    assert BeeAssets() is BeeAssets()
    assert BeeAssets().logo is BeeAssets().logo


def test_has_logo(view):
    assert isinstance(BeeAssets().logo, QtGui.QIcon)


def test_palette_is_loaded(qapp):
    palette = BeeAssets().palette
    assert len(palette) == 64
    assert all(color.isValid() for color in palette)
    assert palette[0] == QtGui.QColor('#000000')


def test_palette_skips_what_it_cannot_read(qapp, tmpdir):
    """A bad line in a palette file must not bring the app down."""

    path = pathlib.Path(tmpdir) / 'test.hex'
    path.write_text('ff0000\n\n  00ff00  \nnot a colour\n#0000ff\n')
    assets = BeeAssets()
    with patch.object(BeeAssets, 'PATH', pathlib.Path(tmpdir)):
        with patch.object(BeeAssets, 'PALETTE_FILE', 'test.hex'):
            colors = assets.load_palette()
    assert [c.name() for c in colors] == ['#ff0000', '#00ff00', '#0000ff']


def test_palette_missing_file_is_not_fatal(qapp, tmpdir):
    assets = BeeAssets()
    with patch.object(BeeAssets, 'PATH', pathlib.Path(tmpdir)):
        with patch.object(BeeAssets, 'PALETTE_FILE', 'nothing_here.hex'):
            assert assets.load_palette() == []
