import os
from unittest.mock import patch

from PyQt6 import QtCore, QtGui, QtWidgets

from beeref import fileio
from beeref.items import BeePixmapItem


def screenshot(width=1200, height=900, see_through=50):
    """A picture with an alpha channel that nothing much uses."""

    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
    painter = QtGui.QPainter(img)
    painter.fillRect(img.rect(), QtGui.QColor(90, 140, 190))
    for i in range(0, width, 5):
        painter.setPen(QtGui.QColor(i % 255, (i * 3) % 255, 90))
        painter.drawLine(i, 0, width - i, height)
    painter.end()
    for i in range(see_through):
        img.setPixelColor(i % width, i // width, QtGui.QColor(0, 0, 0, 0))
    return img


def cut_out():
    img = QtGui.QImage(600, 400, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor(0, 0, 0, 0))
    painter = QtGui.QPainter(img)
    painter.fillRect(QtCore.QRect(50, 50, 200, 150), QtGui.QColor('red'))
    painter.end()
    return img


def board_with(view, tmpdir, images):
    for img in images:
        view.scene.addItem(BeePixmapItem(img))
    path = os.path.join(tmpdir, 'board.blk')
    fileio.save_bee(path, view.scene, create_new=True)
    return path


def stored(path):
    """What each picture in the file is stored as."""

    import sqlite3
    con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    rows = con.execute('SELECT name, sz FROM sqlar ORDER BY name').fetchall()
    con.close()
    return rows


def test_a_screenshot_is_stored_again_as_a_photograph(view, tmpdir):
    """Boards written before this was noticed are full of them."""

    path = board_with(view, tmpdir, [screenshot()])
    assert stored(path)[0][0].endswith('.png')

    fileio.shrink_images_bee(path, view.scene)
    assert stored(path)[0][0].endswith('.jpg')


def test_it_is_a_great_deal_smaller(view, tmpdir):
    path = board_with(view, tmpdir, [screenshot()])
    before = stored(path)[0][1]

    fileio.shrink_images_bee(path, view.scene)
    assert stored(path)[0][1] < before / 3


def test_a_damaged_picture_does_not_stop_the_rest(view, tmpdir):
    """One unreadable row must not leave the others as they were."""

    path = board_with(view, tmpdir, [screenshot(), screenshot()])
    import sqlite3
    con = sqlite3.connect(path)
    row = con.execute('SELECT item_id FROM sqlar LIMIT 1').fetchone()
    con.execute('UPDATE sqlar SET data=? WHERE item_id=?',
                (b'not a picture', row[0]))
    con.commit()
    con.close()

    fileio.shrink_images_bee(path, view.scene)
    names = [name for name, size in stored(path)]
    assert sum(1 for name in names if name.endswith('.jpg')) == 1


def test_a_picture_that_really_is_cut_out_is_left_alone(view, tmpdir):
    path = board_with(view, tmpdir, [cut_out()])
    before = stored(path)

    fileio.shrink_images_bee(path, view.scene)
    assert stored(path) == before


def test_a_photograph_is_left_alone(view, tmpdir):
    """Already stored the way this would store it."""

    img = QtGui.QImage(1200, 900, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(90, 140, 190))
    path = board_with(view, tmpdir, [img])
    assert stored(path)[0][0].endswith('.jpg')
    before = stored(path)

    fileio.shrink_images_bee(path, view.scene)
    assert stored(path) == before


def test_the_board_still_opens_with_its_pictures(view, tmpdir):
    path = board_with(view, tmpdir, [screenshot(), cut_out()])
    fileio.shrink_images_bee(path, view.scene)

    view.scene.clear()
    fileio.load_bee(path, view.scene)
    view.scene.add_queued_items()
    images = list(view.scene.items_by_type('pixmap'))
    assert len(images) == 2
    for item in images:
        assert item.pixmap().isNull() is False


def test_the_file_itself_gets_smaller(view, tmpdir):
    """Not only the rows: the space they held is given back too."""

    path = board_with(view, tmpdir, [screenshot(), screenshot()])
    before = os.path.getsize(path)

    fileio.shrink_images_bee(path, view.scene)
    assert os.path.getsize(path) < before / 2


def test_nothing_happens_without_saying_yes(view, tmpdir):
    """It cannot be taken back, so it is asked for twice over."""

    view.filename = board_with(view, tmpdir, [screenshot()])
    view.undo_stack.setClean()
    before = stored(view.filename)

    with patch.object(
            QtWidgets.QMessageBox, 'warning',
            return_value=QtWidgets.QMessageBox.StandardButton.Cancel):
        view.on_action_shrink_images()
    assert stored(view.filename) == before


def test_unsaved_changes_are_asked_for_first(view, tmpdir):
    view.filename = board_with(view, tmpdir, [screenshot()])
    view.scene.addItem(BeePixmapItem(cut_out()))
    view.undo_stack.resetClean()

    with patch.object(QtWidgets.QMessageBox, 'information') as told:
        with patch.object(QtWidgets.QMessageBox, 'warning') as warned:
            view.on_action_shrink_images()
    assert told.called
    assert warned.called is False


def test_sizes_are_said_in_words_people_read(view):
    assert view.human_size(512) == '512 bytes'
    assert view.human_size(2048) == '2 KB'
    assert view.human_size(5 * 1024 * 1024) == '5 MB'
    assert view.human_size(3 * 1024 ** 3) == '3.0 GB'
