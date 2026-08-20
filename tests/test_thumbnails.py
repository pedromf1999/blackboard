import os

from PyQt6 import QtCore, QtGui

from beeref import fileio
from beeref.fileio.sql import SQLiteIO
from beeref.items import BeePixmapItem
from beeref.widgets.welcome_overlay import RecentFilesModel


def board_with_an_image(view):
    img = QtGui.QImage(300, 200, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(200, 60, 60))
    view.scene.addItem(BeePixmapItem(img))


def test_no_thumbnail_for_an_empty_board(view):
    assert view.thumbnail() is None


def test_thumbnail_is_a_picture_of_the_board(view):
    board_with_an_image(view)
    data = view.thumbnail()

    assert data
    image = QtGui.QImage()
    assert image.loadFromData(data) is True
    assert image.width() == view.THUMBNAIL_WIDTH


def test_thumbnail_survives_the_file(view, tmpdir):
    board_with_an_image(view)
    data = view.thumbnail()
    path = os.path.join(tmpdir, 'board.blk')

    SQLiteIO(path, view.scene, create_new=True, thumbnail=data).write()

    assert fileio.read_thumbnail(path) == data
    # And the board itself still opens
    io = SQLiteIO(path, view.scene, readonly=True)
    assert io.count_rows() == 1


def test_a_board_saved_without_one_reads_as_none(view, tmpdir):
    board_with_an_image(view)
    path = os.path.join(tmpdir, 'plain.blk')
    SQLiteIO(path, view.scene, create_new=True).write()

    assert fileio.read_thumbnail(path) is None


def test_unreadable_file_gives_no_thumbnail(tmpdir):
    """A recent file may have been deleted or replaced with anything."""

    path = os.path.join(tmpdir, 'notaboard.blk')
    with open(path, 'w') as f:
        f.write('hello')

    assert fileio.read_thumbnail(path) is None
    assert fileio.read_thumbnail(os.path.join(tmpdir, 'missing.blk')) is None


def test_recent_files_offer_the_thumbnail(view, tmpdir):
    board_with_an_image(view)
    path = os.path.join(tmpdir, 'board.blk')
    SQLiteIO(path, view.scene, create_new=True,
             thumbnail=view.thumbnail()).write()

    model = RecentFilesModel([path])
    index = model.index(0, 0)
    icon = model.data(index, QtCore.Qt.ItemDataRole.DecorationRole)

    assert icon is not None
    assert icon.isNull() is False
    # The name is still what the entry says
    assert model.data(index, QtCore.Qt.ItemDataRole.DisplayRole) == 'board.blk'
