import os
from unittest.mock import MagicMock, patch

from PyQt6 import QtCore, QtGui, QtWidgets

from beeref import commands
from beeref.items import BeePixmapItem


BUTTON = QtWidgets.QMessageBox.StandardButton


def dirty(view):
    """A board with a change on it that is not on disk."""

    img = QtGui.QImage(40, 30, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor('red'))
    view.undo_stack.push(
        commands.InsertItems(
            view.scene, [BeePixmapItem(img)], QtCore.QPointF(0, 0)))
    assert view.undo_stack.isClean() is False


def test_saving_is_one_of_the_answers(view, settings):
    """Not only discard or cancel: the changes can be kept."""

    dirty(view)
    with patch.object(QtWidgets.QMessageBox, 'question',
                      return_value=BUTTON.Cancel) as asked:
        view.get_confirmation_unsaved_changes('foo')

    offered = asked.call_args[0][3]
    assert offered & BUTTON.Save
    assert offered & BUTTON.Discard
    assert offered & BUTTON.Cancel


def test_saving_is_the_answer_offered_first(view, settings):
    """Whichever button the return key falls on, nothing is lost."""

    dirty(view)
    with patch.object(QtWidgets.QMessageBox, 'question',
                      return_value=BUTTON.Cancel) as asked:
        view.get_confirmation_unsaved_changes('foo')

    assert asked.call_args[0][4] == BUTTON.Save


def test_discarding_lets_the_board_go(view, settings):
    dirty(view)
    with patch.object(QtWidgets.QMessageBox, 'question',
                      return_value=BUTTON.Discard):
        assert view.get_confirmation_unsaved_changes('foo') is True


def test_cancelling_keeps_the_board(view, settings):
    dirty(view)
    with patch.object(QtWidgets.QMessageBox, 'question',
                      return_value=BUTTON.Cancel):
        assert view.get_confirmation_unsaved_changes('foo') is False


def test_saying_save_saves(view, settings, tmpdir):
    dirty(view)
    view.filename = os.path.join(tmpdir, 'board.blk')

    with patch.object(QtWidgets.QMessageBox, 'question',
                      return_value=BUTTON.Save):
        assert view.get_confirmation_unsaved_changes('foo') is True

    assert os.path.exists(view.filename)
    assert view.undo_stack.isClean()


def test_it_waits_for_the_save_to_finish(view, settings, tmpdir):
    """The board is about to be thrown away, so a save that is still
    running is not good enough."""

    dirty(view)
    view.filename = os.path.join(tmpdir, 'board.blk')
    view.save_and_wait()

    assert view.worker.isRunning() is False
    assert os.path.getsize(view.filename) > 0


def test_a_board_with_no_filename_yet_is_asked_where(view, settings, tmpdir):
    dirty(view)
    view.filename = None
    wanted = os.path.join(tmpdir, 'new.blk')

    with patch.object(QtWidgets.QFileDialog, 'getSaveFileName',
                      return_value=(wanted, None)):
        assert view.save_and_wait() is True
    assert os.path.exists(wanted)


def test_dismissing_the_file_dialog_saves_nothing(view, settings):
    """And so must not let the board be closed either."""

    dirty(view)
    view.filename = None

    with patch.object(QtWidgets.QFileDialog, 'getSaveFileName',
                      return_value=('', None)):
        assert view.save_and_wait() is False
    assert view.undo_stack.isClean() is False


def test_a_save_that_failed_does_not_let_the_board_go(view, settings):
    dirty(view)
    view.filename = os.path.join('no', 'such', 'place', 'board.blk')

    with patch.object(QtWidgets.QMessageBox, 'warning'):
        with patch.object(QtWidgets.QMessageBox, 'question',
                          return_value=BUTTON.Save):
            assert view.get_confirmation_unsaved_changes('foo') is False


def test_a_saved_board_is_not_asked_about(view, settings):
    with patch.object(QtWidgets.QMessageBox, 'question') as asked:
        assert view.get_confirmation_unsaved_changes('foo') is True
    assert asked.called is False


def test_the_setting_still_turns_it_off(view, settings):
    dirty(view)
    settings.setValue('Save/confirm_close_unsaved', False)

    with patch.object(QtWidgets.QMessageBox, 'question') as asked:
        assert view.get_confirmation_unsaved_changes('foo') is True
    assert asked.called is False


def test_the_window_button_asks_too(view):
    """It used to close without a word, however much was unsaved."""

    from beeref.__main__ import BeeRefMainWindow

    window = MagicMock()
    window.view = view
    view.get_confirmation_unsaved_changes = MagicMock(return_value=False)
    event = MagicMock()

    BeeRefMainWindow.closeEvent(window, event)

    view.get_confirmation_unsaved_changes.assert_called_once()
    event.ignore.assert_called_once()
    event.accept.assert_not_called()


def test_the_window_closes_once_that_is_answered(view):
    from beeref.__main__ import BeeRefMainWindow

    window = MagicMock()
    window.view = view
    window.saveGeometry.return_value = QtCore.QByteArray()
    view.get_confirmation_unsaved_changes = MagicMock(return_value=True)
    event = MagicMock()

    BeeRefMainWindow.closeEvent(window, event)

    event.accept.assert_called_once()
    window.saveGeometry.assert_called_once()
