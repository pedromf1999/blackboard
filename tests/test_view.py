import os.path
from pathlib import Path
import shutil
import sqlite3
from unittest.mock import MagicMock, patch, mock_open

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
import pytest

from beeref import commands, constants, fileio, widgets
from beeref.actions import actions
from beeref.config import logfile_name, settings_events
from beeref.fileio.sql import SQLiteIO
from beeref.items import (
    BeePixmapItem, BeeTextItem, BeeGroupItem, BeeDrawItem)
from beeref.view import BeeGraphicsView

APP_TITLE = f'{constants.APPNAME} {constants.VERSION}'


def test_inits_menu(qapp):
    parent = QtWidgets.QMainWindow()
    view = BeeGraphicsView(qapp, parent)
    assert isinstance(view.context_menu, QtWidgets.QMenu)
    assert len(view.actions()) > 0
    assert view.actions()
    assert view.bee_actiongroups


@patch('beeref.view.BeeGraphicsView.open_from_file')
def test_init_without_filenames(open_file_mock, qapp, commandline_args):
    commandline_args.filenames = None
    parent = QtWidgets.QMainWindow()
    view = BeeGraphicsView(qapp, parent)
    open_file_mock.assert_not_called()
    assert view.parent.windowTitle() == APP_TITLE
    del view


def test_init_uses_canvas_color_from_settings(qapp, settings):
    settings.setValue('View/canvas_color', '#ff0000')
    parent = QtWidgets.QMainWindow()
    view = BeeGraphicsView(qapp, parent)
    assert view.backgroundBrush().color().name() == '#ff0000'
    del view


def test_canvas_color_setting_updates_view(qapp, settings, view):
    settings.setValue('View/canvas_color', '#ff0000')
    assert view.backgroundBrush().color().name() == '#ff0000'


@patch('beeref.view.BeeGraphicsView.open_from_file')
def test_init_with_filenames_beefile(open_file_mock, qapp, commandline_args):
    commandline_args.filenames = ['test.bee']
    parent = QtWidgets.QMainWindow()
    view = BeeGraphicsView(qapp, parent)
    open_file_mock.assert_called_once_with('test.bee')
    del view


@patch('beeref.view.BeeGraphicsView.do_insert_images')
def test_init_with_filenames_images(insert_img_mock, qapp, commandline_args):
    commandline_args.filenames = ['/foo/bar.png', '/foo/baz.jpg']
    parent = QtWidgets.QMainWindow()
    view = BeeGraphicsView(qapp, parent)
    insert_img_mock.assert_called_once_with(['/foo/bar.png', '/foo/baz.jpg'])
    del view


@patch('beeref.widgets.welcome_overlay.WelcomeOverlay.hide')
def test_on_scene_changed_when_items(hide_mock, view):
    item = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(item)
    view.scale(2, 2)
    with patch('beeref.view.BeeGraphicsView.recalc_scene_rect') as r:
        view.on_scene_changed(None)
        r.assert_called_once_with()
        hide_mock.assert_called_once_with()
        assert view.get_scale() == 2


@patch('beeref.widgets.welcome_overlay.WelcomeOverlay.show')
def test_on_scene_changed_when_no_items(show_mock, view):
    view.scale(2, 2)
    with patch('beeref.view.BeeGraphicsView.recalc_scene_rect') as r:
        view.on_scene_changed(None)
        r.assert_called()
        show_mock.assert_called_once_with()
        assert view.get_scale() == 1


def test_get_supported_image_formats_for_reading(view):
    formats = view.get_supported_image_formats(QtGui.QImageReader)
    assert '*.png' in formats
    assert '*.jpg' in formats


def test_clear_scene(view, item):
    view.scene.addItem(item)
    view.scene.internal_clipboard.append(item)
    view.scale(2, 2)
    view.translate(123, 456)
    view.filename = 'test.bee'
    view.undo_stack = MagicMock()

    view.clear_scene()
    assert not view.scene.items()
    assert view.scene.internal_clipboard == []
    assert view.transform().isIdentity()
    assert view.filename is None
    view.undo_stack.clear.assert_called_once_with()
    assert view.parent.windowTitle() == APP_TITLE


def test_reset_previous_transform_when_other_item(view):
    item1 = MagicMock()
    item2 = MagicMock()
    view.previous_transform = {
        'transform': 'foo',
        'toggle_item': item1,
    }
    view.reset_previous_transform(toggle_item=item2)
    assert view.previous_transform is None


def test_reset_previous_transform_when_same_item(view):
    item = MagicMock()
    view.previous_transform = {
        'transform': 'foo',
        'toggle_item': item,
    }
    view.reset_previous_transform(toggle_item=item)
    assert view.previous_transform == {
        'transform': 'foo',
        'toggle_item': item,
    }


@patch('beeref.view.BeeGraphicsView.fitInView')
def test_fit_rect_no_toggle(fit_mock, view):
    rect = QtCore.QRectF(30, 40, 100, 80)
    view.previous_transform = {'toggle_item': MagicMock()}
    view.fit_rect(rect)
    fit_mock.assert_called_with(rect, Qt.AspectRatioMode.KeepAspectRatio)
    assert view.previous_transform is None


@patch('beeref.view.BeeGraphicsView.fitInView')
def test_fit_rect_toggle_when_no_previous(fit_mock, view):
    item = MagicMock()
    view.previous_transform = None
    view.setSceneRect(QtCore.QRectF(-2000, -2000, 4000, 4000))
    rect = QtCore.QRectF(30, 40, 100, 80)
    view.scale(2, 2)
    view.horizontalScrollBar().setValue(-40)
    view.verticalScrollBar().setValue(-50)
    view.fit_rect(rect, toggle_item=item)
    fit_mock.assert_called_with(rect, Qt.AspectRatioMode.KeepAspectRatio)
    assert view.previous_transform['toggle_item'] == item
    assert view.previous_transform['transform'].m11() == 2
    assert isinstance(view.previous_transform['center'], QtCore.QPointF)


@patch('beeref.view.BeeGraphicsView.fitInView')
@patch('beeref.view.BeeGraphicsView.centerOn')
def test_fit_rect_toggle_when_previous(center_mock, fit_mock, view):
    item = MagicMock()
    view.previous_transform = {
        'toggle_item': item,
        'transform': QtGui.QTransform.fromScale(2, 2),
        'center': QtCore.QPointF(30, 40)
    }
    view.setSceneRect(QtCore.QRectF(-2000, -2000, 4000, 4000))
    rect = QtCore.QRectF(30, 40, 100, 80)
    view.fit_rect(rect, toggle_item=item)
    fit_mock.assert_not_called()
    center_mock.assert_called_once_with(QtCore.QPointF(30, 40))
    assert view.get_scale() == 2


@patch('PyQt6.QtWidgets.QMessageBox.question')
def test_get_confirmation_unsaved_changes_when_no_changes(
        dlg_mock, settings, view, item):
    view.scene.addItem(item)
    assert view.undo_stack.isClean()
    assert view.get_confirmation_unsaved_changes('foo') is True
    dlg_mock.assert_not_called()


@patch('PyQt6.QtWidgets.QMessageBox.question')
def test_get_confirmation_unsaved_changes_when_changes_confirmation_disabled(
        dlg_mock, settings, view, item):
    settings.setValue('Save/confirm_close_unsaved', False)
    view.undo_stack.push(
        commands.InsertItems(view.scene, [item], QtCore.QPointF(0, 0)))
    assert view.undo_stack.isClean() is False
    assert view.get_confirmation_unsaved_changes('foo') is True
    dlg_mock.assert_not_called()


@patch('PyQt6.QtWidgets.QMessageBox.question',
       return_value=QtWidgets.QMessageBox.StandardButton.Yes)
def test_get_confirmation_unsaved_changes_when_changes_confirmed(
        dlg_mock, settings, view, item):
    view.undo_stack.push(
        commands.InsertItems(view.scene, [item], QtCore.QPointF(0, 0)))
    assert view.undo_stack.isClean() is False
    assert view.get_confirmation_unsaved_changes('foo') is True
    dlg_mock.assert_called_once()


@patch('PyQt6.QtWidgets.QMessageBox.question',
       return_value=QtWidgets.QMessageBox.StandardButton.Cancel)
def test_get_confirmation_unsaved_changes_when_changes_not_confirmed(
        dlg_mock, settings, view, item):
    view.undo_stack.push(
        commands.InsertItems(view.scene, [item], QtCore.QPointF(0, 0)))
    assert view.undo_stack.isClean() is False
    assert view.get_confirmation_unsaved_changes('foo') is False
    dlg_mock.assert_called_once()


@patch('beeref.view.BeeGraphicsView.get_confirmation_unsaved_changes',
       return_value=False)
def test_on_action_new_scene_when_unsaved_changes_not_confirmed(
        confirm_mock, view):
    view.clear_scene = MagicMock()
    view.on_action_new_scene()
    confirm_mock.assert_called_once()
    view.clear_scene.assert_not_called()


@patch('beeref.view.BeeGraphicsView.get_confirmation_unsaved_changes',
       return_value=True)
def test_on_action_new_scene_when_unsaved_changes_confirmed(
        confirm_mock, view):
    view.clear_scene = MagicMock()
    view.on_action_new_scene()
    confirm_mock.assert_called_once()
    view.clear_scene.assert_called_once_with()


@patch('beeref.view.BeeGraphicsView.get_confirmation_unsaved_changes',
       return_value=False)
def test_on_action_open_recent_file_when_unsaved_changes_not_confirmed(
        confirm_mock, view):
    view.open_from_file = MagicMock()
    view.on_action_open_recent_file('foo.bee')
    confirm_mock.assert_called_once()
    view.open_from_file.assert_not_called()


@patch('beeref.view.BeeGraphicsView.get_confirmation_unsaved_changes',
       return_value=True)
def test_on_action_open_recent_file_when_unsaved_changes_confirmed(
        confirm_mock, view):
    view.open_from_file = MagicMock()
    view.on_action_open_recent_file('foo.bee')
    confirm_mock.assert_called_once()
    view.open_from_file.assert_called_once_with('foo.bee')


@patch('beeref.view.BeeGraphicsView.clear_scene')
def test_open_from_file(clear_mock, view, qtbot):
    root = os.path.dirname(__file__)
    filename = os.path.join(root, 'assets', 'test1item.bee')
    view.on_loading_finished = MagicMock()
    view.open_from_file(filename)
    view.worker.wait()
    qtbot.waitUntil(lambda: view.on_loading_finished.called is True)
    assert len(view.scene.items()) == 1
    item = view.scene.items()[0]
    assert item.isSelected() is False
    assert item.pixmap()
    clear_mock.assert_called_once_with()
    view.on_loading_finished.assert_called_once_with(filename, [])


def test_open_from_file_when_error(view, qtbot):
    view.on_loading_finished = MagicMock()
    view.open_from_file('uieauiae')
    view.worker.wait()
    qtbot.waitUntil(lambda: view.on_loading_finished.called is True)
    assert list(view.scene.items()) == []
    view.on_loading_finished.assert_called_once_with(
        'uieauiae', ['unable to open database file'])


@patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName')
def test_on_action_open(dialog_mock, view, qtbot):
    # FIXME: #1
    # Can't check signal handling currently
    root = os.path.dirname(__file__)
    filename = os.path.join(root, 'assets', 'test1item.bee')
    dialog_mock.return_value = (filename, None)
    view.on_loading_finished = MagicMock()
    view.cancel_active_modes = MagicMock()

    view.on_action_open()
    qtbot.waitUntil(lambda: view.on_loading_finished.called is True)
    assert len(view.scene.items()) == 1
    item = view.scene.items()[0]
    assert item.isSelected() is False
    assert item.pixmap()
    view.on_loading_finished.assert_called_once_with(filename, [])
    view.cancel_active_modes.assert_called_with()


@patch('beeref.view.BeeGraphicsView.get_confirmation_unsaved_changes',
       return_value=False)
@patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName')
def test_on_action_open_when_unsaved_changes_not_confirmed(
        dialog_mock, confirm_mock, view):
    view.cancel_active_modes = MagicMock()
    view.open_from_file = MagicMock()
    view.on_action_open()
    view.cancel_active_modes.assert_not_called()
    dialog_mock.assert_not_called()
    view.open_from_file.assert_not_called()


@patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName')
@patch('beeref.view.BeeGraphicsView.open_from_file')
def test_on_action_open_when_no_filename(open_mock, dialog_mock, view):
    dialog_mock.return_value = (None, None)
    view.cancel_active_modes = MagicMock()
    view.on_action_open()
    open_mock.assert_not_called()
    view.cancel_active_modes.assert_called_once_with()


@patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName')
def test_on_action_save_as(dialog_mock, view, imgfilename3x3, tmpdir):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    view.cancel_active_modes = MagicMock()
    filename = os.path.join(tmpdir, 'test.bee')
    assert os.path.exists(filename) is False
    dialog_mock.return_value = (filename, None)
    view.on_action_save_as()
    view.worker.wait()
    assert os.path.exists(filename) is True
    view.cancel_active_modes.assert_called_once_with()


@patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName')
@patch('beeref.view.BeeGraphicsView.do_save')
def test_on_action_save_as_when_no_filename(
        save_mock, dialog_mock, view, imgfilename3x3):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    view.cancel_active_modes = MagicMock()
    dialog_mock.return_value = (None, None)
    view.on_action_save_as()
    save_mock.assert_not_called()
    view.cancel_active_modes.assert_called_once_with()


@patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName')
def test_on_action_save_as_filename_without_extension(
        dialog_mock, view, qtbot, imgfilename3x3, tmpdir):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    view.cancel_active_modes = MagicMock()
    view.on_saving_finished = MagicMock()
    filename = os.path.join(tmpdir, 'test')
    assert os.path.exists(filename) is False
    dialog_mock.return_value = (filename, None)
    view.on_action_save_as()
    qtbot.waitUntil(lambda: view.on_saving_finished.called is True)
    saved = f'{filename}{constants.FILE_EXT}'
    assert os.path.exists(saved) is True
    view.on_saving_finished.assert_called_once_with(saved, [])
    view.cancel_active_modes.assert_called_once_with()


@patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName')
@patch('beeref.fileio.sql.SQLiteIO.write_data')
def test_on_action_save_as_when_error(
        save_mock, dialog_mock, view, qtbot, imgfilename3x3, tmpdir):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    view.on_saving_finished = MagicMock()
    view.cancel_active_modes = MagicMock()
    filename = os.path.join(tmpdir, 'test.bee')
    dialog_mock.return_value = (filename, None)
    save_mock.side_effect = sqlite3.Error('foo')
    view.on_action_save_as()
    qtbot.waitUntil(lambda: view.on_saving_finished.called is True)
    view.on_saving_finished.assert_called_once_with(filename, ['foo'])
    view.cancel_active_modes.assert_called_once_with()


def test_on_action_save(view, qtbot, imgfilename3x3, tmpdir):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    view.cancel_active_modes = MagicMock()
    view.filename = os.path.join(tmpdir, 'test.bee')
    root = os.path.dirname(__file__)
    shutil.copyfile(os.path.join(root, 'assets', 'test1item.bee'),
                    view.filename)
    view.on_saving_finished = MagicMock()
    view.on_action_save()
    qtbot.waitUntil(lambda: view.on_saving_finished.called is True)
    assert os.path.exists(view.filename) is True
    view.on_saving_finished.assert_called_once_with(view.filename, [])
    view.cancel_active_modes.assert_called_once_with()


@patch('beeref.view.BeeGraphicsView.on_action_save_as')
def test_on_action_save_when_no_filename(save_as_mock, view, imgfilename3x3):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    view.cancel_active_modes = MagicMock()
    view.filename = None
    view.on_action_save()
    save_as_mock.assert_called_once_with()
    view.cancel_active_modes.assert_called_once_with()


@patch('beeref.widgets.SceneToPixmapExporterDialog.exec')
@patch('beeref.widgets.SceneToPixmapExporterDialog.value')
@patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName')
def test_on_action_export_scene(
        file_mock, value_mock, exec_mock, view, tmpdir, qtbot):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    filename = os.path.join(tmpdir, 'test.png')
    assert os.path.exists(filename) is False
    file_mock.return_value = (filename, None)
    exec_mock.return_value = 1
    value_mock.return_value = QtCore.QSize(100, 100)
    view.on_export_finished = MagicMock()

    view.on_action_export_scene()
    qtbot.waitUntil(lambda: view.on_export_finished.called is True)
    view.on_export_finished.assert_called_once_with(filename, [])
    img = QtGui.QImage(filename)
    assert img.size() == QtCore.QSize(100, 100)


@patch('beeref.widgets.SceneToPixmapExporterDialog.exec')
@patch('beeref.widgets.SceneToPixmapExporterDialog.value')
@patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName')
def test_on_action_export_scene_no_file_extension(
        file_mock, value_mock, exec_mock, view, tmpdir, qtbot):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    filename = os.path.join(tmpdir, 'test')
    assert os.path.exists(filename) is False
    file_mock.return_value = (filename, 'PNG (*.png)')
    exec_mock.return_value = 1
    value_mock.return_value = QtCore.QSize(100, 100)
    view.on_export_finished = MagicMock()

    view.on_action_export_scene()
    qtbot.waitUntil(lambda: view.on_export_finished.called is True)
    view.on_export_finished.assert_called_once_with(f'{filename}.png', [])
    img = QtGui.QImage(f'{filename}.png')
    assert img.size() == QtCore.QSize(100, 100)


@patch('beeref.widgets.SceneToPixmapExporterDialog.exec')
@patch('beeref.widgets.SceneToPixmapExporterDialog.value')
@patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName')
def test_on_action_export_scene_no_filename(
        file_mock, value_mock, exec_mock, view):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    file_mock.return_value = (None, None)
    view.on_export_finished = MagicMock()

    view.on_action_export_scene()
    exec_mock.assert_not_called()
    value_mock.assert_not_called()
    view.on_export_finished.assert_not_called()


@patch('beeref.widgets.SceneToPixmapExporterDialog.exec')
@patch('beeref.widgets.SceneToPixmapExporterDialog.value')
@patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName')
def test_on_action_export_scene_settings_input_canceled(
        file_mock, value_mock, exec_mock, view, tmpdir):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    filename = os.path.join(tmpdir, 'test.png')
    assert os.path.exists(filename) is False
    file_mock.return_value = (filename, None)
    exec_mock.return_value = 0
    view.on_action_export_scene()
    value_mock.assert_not_called()
    assert os.path.exists(filename) is False


@patch('PyQt6.QtWidgets.QFileDialog.getExistingDirectory')
def test_on_action_export_images(
        dir_mock, view, tmpdir, qtbot, imgfilename3x3):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    dir_mock.return_value = tmpdir
    view.on_export_finished = MagicMock()

    view.on_action_export_images()
    qtbot.waitUntil(lambda: view.on_export_finished.called is True)
    view.on_export_finished.assert_called_once_with(tmpdir, [])
    assert os.path.exists(os.path.join(tmpdir, '0001.png'))


@patch('PyQt6.QtWidgets.QFileDialog.getExistingDirectory')
def test_on_action_export_images_no_dirname(
        dir_mock, view, tmpdir, qtbot, imgfilename3x3):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    dir_mock.return_value = None
    view.on_export_finished = MagicMock()

    view.on_action_export_images()
    view.on_export_finished.assert_not_called()
    assert os.path.exists(os.path.join(tmpdir, '0001.png')) is False


@patch('beeref.widgets.ExportImagesFileExistsDialog.exec',
       return_value=QtWidgets.QDialog.DialogCode.Accepted)
@patch('beeref.widgets.ExportImagesFileExistsDialog.get_answer',
       return_value='overwrite')
@patch('PyQt6.QtWidgets.QFileDialog.getExistingDirectory')
def test_on_action_export_images_file_exists_overwrite(
        dir_mock, answer_mock, exec_mock, view, tmpdir, qtbot, imgfilename3x3):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    dir_mock.return_value = tmpdir
    view.on_export_finished = MagicMock()

    imgfilename = Path(tmpdir) / '0001.png'
    imgfilename.write_text('foo')

    view.on_action_export_images()
    qtbot.waitUntil(lambda: view.on_export_finished.called is True)
    view.on_export_finished.assert_called_once_with(tmpdir, [])
    answer_mock.assert_called_once_with()
    exec_mock.assert_called_once_with()
    imgfilename.read_bytes().startswith(b'\x89PNG')


@patch('beeref.widgets.ExportImagesFileExistsDialog.exec',
       return_value=QtWidgets.QDialog.DialogCode.Accepted)
@patch('beeref.widgets.ExportImagesFileExistsDialog.get_answer',
       return_value='skip')
@patch('PyQt6.QtWidgets.QFileDialog.getExistingDirectory')
def test_on_action_export_images_file_exists_skip(
        dir_mock, answer_mock, exec_mock, view, tmpdir, qtbot, imgfilename3x3):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    dir_mock.return_value = tmpdir
    view.on_export_finished = MagicMock()
    imgfilename = Path(tmpdir) / '0001.png'
    imgfilename.write_text('foo')

    view.on_action_export_images()
    qtbot.waitUntil(lambda: view.on_export_finished.called is True)
    view.on_export_finished.assert_called_once_with(tmpdir, [])
    answer_mock.assert_called_once_with()
    exec_mock.assert_called_once_with()
    imgfilename.read_text() == 'foo'


@patch('beeref.widgets.ExportImagesFileExistsDialog.exec',
       return_value=QtWidgets.QDialog.DialogCode.Rejected)
@patch('beeref.widgets.ExportImagesFileExistsDialog.get_answer',
       return_value='skip')
@patch('PyQt6.QtWidgets.QFileDialog.getExistingDirectory')
def test_on_action_export_images_file_exists_canceled(
        dir_mock, answer_mock, exec_mock, view, tmpdir, qtbot, imgfilename3x3):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    dir_mock.return_value = tmpdir
    view.on_export_finished = MagicMock()
    imgfilename = Path(tmpdir) / '0001.png'
    imgfilename.write_text('foo')

    view.on_action_export_images()
    qtbot.waitUntil(lambda: exec_mock.called is True)
    view.on_export_finished.assert_not_called()
    answer_mock.assert_not_called()
    imgfilename.read_text() == 'foo'


@patch('beeref.view.BeeGraphicsView.get_confirmation_unsaved_changes',
       return_value=False)
@patch('beeref.__main__.BeeRefApplication.quit')
def test_on_action_quit_when_unsaved_changes_not_confirmed(
        quit_mock, confirm_mock, view):
    view.on_action_quit()
    confirm_mock.assert_called_once()
    quit_mock.assert_not_called()


@patch('beeref.view.BeeGraphicsView.get_confirmation_unsaved_changes',
       return_value=True)
@patch('beeref.__main__.BeeRefApplication.quit')
def test_on_action_quit_when_unsaved_changes_confirmed(
        quit_mock, confirm_mock, view):
    view.on_action_quit()
    confirm_mock.assert_called_once()
    quit_mock.assert_called_once_with()


@patch('beeref.widgets.settings.SettingsDialog.show')
def test_on_action_settings(show_mock, view):
    view.on_action_settings()
    show_mock.assert_called_once()


@patch('beeref.widgets.controls.ControlsDialog.show')
def test_on_action_keyboard_settings(show_mock, view):
    view.on_action_keyboard_settings()
    show_mock.assert_called_once()


@patch('beeref.widgets.HelpDialog.show')
def test_on_action_help(show_mock, view):
    view.on_action_help()
    show_mock.assert_called_once()


@patch('beeref.widgets.DebugLogDialog.show')
def test_on_action_debuglog(show_mock, view):
    with patch('builtins.open', mock_open(read_data='log')) as open_mock:
        view.on_action_debuglog()
        show_mock.assert_called_once()
        open_mock.assert_called_once_with(logfile_name())


@patch('beeref.scene.BeeGraphicsScene.clearSelection')
@patch('PyQt6.QtWidgets.QFileDialog.getOpenFileNames')
def test_on_action_insert_images_new_scene(
        dialog_mock, clear_mock, view, imgfilename3x3, qtbot):
    dialog_mock.return_value = ([imgfilename3x3], None)
    view.on_insert_images_finished = MagicMock()
    view.cancel_active_modes = MagicMock()
    view.on_action_insert_images()
    qtbot.waitUntil(lambda: view.on_insert_images_finished.called is True)
    assert len(view.scene.items()) == 1
    item = view.scene.items()[0]
    assert item.isSelected() is True
    assert item.pixmap()
    clear_mock.assert_called_once_with()
    view.on_insert_images_finished.assert_called_once_with(True, '', [])
    view.cancel_active_modes.assert_called_once_with()


@patch('beeref.scene.BeeGraphicsScene.clearSelection')
@patch('PyQt6.QtWidgets.QFileDialog.getOpenFileNames')
def test_on_action_insert_images_existing_scene(
        dialog_mock, clear_mock, view, imgfilename3x3, qtbot, item):
    view.scene.addItem(item)
    dialog_mock.return_value = ([imgfilename3x3], None)
    view.on_insert_images_finished = MagicMock()
    view.cancel_active_modes = MagicMock()
    view.on_action_insert_images()
    qtbot.waitUntil(lambda: view.on_insert_images_finished.called is True)
    assert len(view.scene.items()) == 2
    item = view.scene.items()[0]
    assert item.isSelected() is True
    assert item.pixmap()
    clear_mock.assert_called_once_with()
    view.on_insert_images_finished.assert_called_once_with(False, '', [])
    view.cancel_active_modes.assert_called_once_with()


@patch('beeref.scene.BeeGraphicsScene.clearSelection')
@patch('PyQt6.QtWidgets.QFileDialog.getOpenFileNames')
def test_on_action_insert_images_when_error(
        dialog_mock, clear_mock, view, imgfilename3x3, qtbot):
    dialog_mock.return_value = ([imgfilename3x3, 'iaeiae', 'trntrn'], None)
    view.on_insert_images_finished = MagicMock()
    view.cancel_active_modes = MagicMock()
    view.on_action_insert_images()
    qtbot.waitUntil(lambda: view.on_insert_images_finished.called is True)
    assert len(view.scene.items()) == 1
    item = view.scene.items()[0]
    assert item.isSelected() is True
    assert item.pixmap()
    clear_mock.assert_called_once_with()
    view.on_insert_images_finished.assert_called_once_with(
        True, '', ['iaeiae', 'trntrn'])
    view.cancel_active_modes.assert_called_once_with()


@patch('beeref.scene.BeeGraphicsScene.clearSelection')
def test_on_action_insert_text(clear_mock, view):
    view.cancel_active_modes = MagicMock()
    view.on_action_insert_text()
    clear_mock.assert_called_once_with()
    assert len(view.scene.items()) == 1
    item = view.scene.items()[0]
    assert item.toPlainText() == 'Text'
    assert item.isSelected() is True
    view.cancel_active_modes.assert_called_once_with()
    # Ready to type straight away, with the placeholder selected
    assert item.edit_mode is True
    assert view.scene.edit_item is item
    assert view.scene.focusItem() is item
    assert item.textCursor().hasSelection() is True
    assert item.textCursor().selectedText() == 'Text'


@patch('PyQt6.QtWidgets.QApplication.clipboard')
def test_on_action_copy_image(clipboard_mock, view, imgfilename3x3):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    view.cancel_active_modes = MagicMock()
    item.setSelected(True)
    view.on_action_copy()

    # Everything is handed over in one QMimeData: the image for other
    # applications and the marker for us
    clipboard_mock.return_value.setMimeData.assert_called_once()
    mimedata = clipboard_mock.return_value.setMimeData.call_args[0][0]
    assert mimedata.hasImage() is True
    view.scene.internal_clipboard == [item]
    assert mimedata.data('beeref/items') == b'1'
    view.cancel_active_modes.assert_called_once_with()


@patch('PyQt6.QtWidgets.QApplication.clipboard')
def test_on_action_copy_text(clipboard_mock, view, imgfilename3x3):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    view.cancel_active_modes = MagicMock()
    item.setSelected(True)
    view.on_action_copy()

    clipboard_mock.return_value.setMimeData.assert_called_once()
    mimedata = clipboard_mock.return_value.setMimeData.call_args[0][0]
    assert mimedata.text() == 'foo bar'
    view.scene.internal_clipboard == [item]
    assert mimedata.data('beeref/items') == b'1'
    view.cancel_active_modes.assert_called_once_with()


@patch('beeref.view.BeeGraphicsView.on_action_fit_scene')
@patch('beeref.scene.BeeGraphicsScene.clearSelection')
@patch('PyQt6.QtGui.QClipboard.image')
def test_on_action_paste_external_new_scene(
        clipboard_mock, clear_mock, fit_mock, view, imgfilename3x3):
    clipboard_mock.return_value = QtGui.QImage(imgfilename3x3)
    view.cancel_active_modes = MagicMock()
    view.on_action_paste()
    assert len(view.scene.items()) == 1
    assert view.scene.items()[0].isSelected() is True
    fit_mock.assert_called_once_with()
    view.cancel_active_modes.assert_called_once_with()


@patch('beeref.view.BeeGraphicsView.on_action_fit_scene')
@patch('beeref.scene.BeeGraphicsScene.clearSelection')
@patch('PyQt6.QtGui.QClipboard.image')
def test_on_action_paste_external_existing_scene(
        clipboard_mock, clear_mock, fit_mock, view, item, imgfilename3x3):
    view.scene.addItem(item)
    view.cancel_active_modes = MagicMock()
    clipboard_mock.return_value = QtGui.QImage(imgfilename3x3)
    view.on_action_paste()
    assert len(view.scene.items()) == 2
    assert view.scene.items()[0].isSelected() is True
    assert view.scene.items()[1].isSelected() is False
    fit_mock.assert_not_called()
    view.cancel_active_modes.assert_called_once_with()


@patch('beeref.scene.BeeGraphicsScene.clearSelection')
@patch('PyQt6.QtGui.QClipboard.mimeData')
def test_on_action_paste_internal(mimedata_mock, clear_mock, view):
    mimedata = QtCore.QMimeData()
    mimedata.setData('beeref/items', QtCore.QByteArray.number(1))
    mimedata_mock.return_value = mimedata
    item = BeePixmapItem(QtGui.QImage())
    view.scene.internal_clipboard = [item]
    view.cancel_active_modes = MagicMock()
    view.on_action_paste()
    assert len(view.scene.items()) == 1
    assert view.scene.items()[0].isSelected() is True
    clear_mock.assert_called_once_with()
    view.cancel_active_modes.assert_called()


@patch('beeref.scene.BeeGraphicsScene.clearSelection')
@patch('PyQt6.QtGui.QClipboard.text')
@patch('PyQt6.QtGui.QClipboard.image')
def test_on_action_paste_when_text(img_mock, text_mock, clear_mock, view):
    img_mock.return_value = QtGui.QImage()
    text_mock.return_value = 'foo bar'
    view.cancel_active_modes = MagicMock()
    view.on_action_paste()
    assert len(view.scene.items()) == 1
    assert view.scene.items()[0].isSelected() is True
    assert view.scene.items()[0].toPlainText() == 'foo bar'
    clear_mock.assert_called_once_with()
    view.cancel_active_modes.assert_called_once_with()


@patch('beeref.scene.BeeGraphicsScene.clearSelection')
@patch('PyQt6.QtGui.QClipboard.text')
@patch('PyQt6.QtGui.QClipboard.image')
@patch('beeref.widgets.BeeNotification')
def test_on_action_paste_when_empty(
        notification_mock, img_mock, text_mock, clear_mock, view):
    view.cancel_active_modes = MagicMock()
    img_mock.return_value = QtGui.QImage()
    text_mock.return_value = ''
    view.on_action_paste()
    assert len(view.scene.items()) == 0
    notification_mock.assert_called()
    assert notification_mock.call_args[0][0] == view
    assert notification_mock.call_args[0][1].startswith('No image data')
    clear_mock.assert_not_called()
    view.cancel_active_modes.assert_called_once_with()


@patch('beeref.view.BeeGraphicsView.on_action_copy')
def test_on_action_cut(copy_mock, view, item):
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_cut()
    copy_mock.assert_called_once_with()
    assert view.scene.items() == []
    assert view.undo_stack.isClean() is False


def test_on_selection_changed_updates_grayscale_action(view):
    item = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(item)
    item.grayscale = True
    actions.actions['grayscale'].qaction.setChecked(False)
    item.setSelected(True)
    assert actions.actions['grayscale'].qaction.isChecked() is True


def test_on_selection_changed_grayscale_action_ignores_textitem(view):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    actions.actions['grayscale'].qaction.setChecked(True)
    item.setSelected(True)
    assert actions.actions['grayscale'].qaction.isChecked() is False


def test_on_action_reset_scale(view, item):
    view.scene.addItem(item)
    item.setScale(2)
    item.setSelected(True)
    view.on_action_reset_scale()
    assert item.scale() == 1


def test_on_action_reset_rotation(view, item):
    view.scene.addItem(item)
    item.setRotation(90)
    item.setSelected(True)
    view.on_action_reset_rotation()
    assert item.rotation() == 0


def test_on_action_reset_flip(view, item):
    view.scene.addItem(item)
    item.do_flip()
    item.setSelected(True)
    view.on_action_reset_flip()
    assert item.flip() == 1


def test_on_action_reset_crop(view, item):
    view.scene.addItem(item)
    item.crop = QtCore.QRectF(2, 2, 10, 10)
    assert item.crop == QtCore.QRectF(2, 2, 10, 10)
    item.setSelected(True)
    view.on_action_reset_crop()
    assert item.crop == QtCore.QRectF(0, 0, 10, 10)


def test_on_action_reset_transforms(view, item):
    view.scene.addItem(item)
    item.crop = QtCore.QRectF(2, 2, 10, 10)
    item.do_flip()
    item.setRotation(90)
    item.setScale(2)
    assert item.crop == QtCore.QRectF(2, 2, 10, 10)
    item.setSelected(True)
    view.on_action_reset_transforms()
    assert item.crop == QtCore.QRectF(0, 0, 10, 10)
    assert item.flip() == 1
    assert item.rotation() == 0
    assert item.scale() == 1


def test_on_action_sample_color(view):
    view.cancel_active_modes = MagicMock()
    view.on_action_sample_color()
    assert view.active_mode == view.SAMPLE_COLOR_MODE
    assert isinstance(view.sample_color_widget, widgets.SampleColorWidget)
    assert view.viewport().cursor() == Qt.CursorShape.CrossCursor
    view.cancel_active_modes.assert_called_once_with()


def test_on_action_sample_color_when_multi_selection(view, item):
    view.scene.addItem(item)
    item.setSelected(True)
    item2 = BeeTextItem('foo')
    view.scene.addItem(item2)
    item2.setSelected(True)

    view.cancel_active_modes = MagicMock()
    view.scene.multi_select_item.lower_behind_selection = MagicMock()
    view.on_action_sample_color()
    assert view.active_mode == view.SAMPLE_COLOR_MODE
    assert isinstance(view.sample_color_widget, widgets.SampleColorWidget)
    assert view.viewport().cursor() == Qt.CursorShape.CrossCursor
    view.cancel_active_modes.assert_called_once_with()
    view.scene.multi_select_item.lower_behind_selection\
                                .assert_called_once_with()


@patch('PyQt6.QtWidgets.QWidget.create')
@patch('PyQt6.QtWidgets.QWidget.destroy')
@patch('PyQt6.QtWidgets.QWidget.show')
def test_on_action_always_on_top_checked(
        show_mock, destroy_mock, create_mock, view):
    view.on_action_always_on_top(True)
    assert view.parent.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    show_mock.assert_called_once()
    destroy_mock.assert_called_once()
    create_mock.assert_called_once()


@patch('PyQt6.QtWidgets.QWidget.create')
@patch('PyQt6.QtWidgets.QWidget.destroy')
@patch('PyQt6.QtWidgets.QWidget.show')
def test_on_action_always_on_top_unchecked(
        show_mock, destroy_mock, create_mock, view):
    view.on_action_always_on_top(False)
    assert not (view.parent.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    show_mock.assert_called_once()
    destroy_mock.assert_called_once()
    create_mock.assert_called_once()


def test_on_action_show_menubar(view):
    view.toplevel_menus = [QtWidgets.QMenu('Foo')]
    view.on_action_show_menubar(True)
    assert len(view.parent.menuBar().actions()) == 1
    view.on_action_show_menubar(False)
    assert view.parent.menuBar().actions() == []


@patch('PyQt6.QtWidgets.QWidget.create')
@patch('PyQt6.QtWidgets.QWidget.destroy')
@patch('PyQt6.QtWidgets.QWidget.show')
def test_on_action_show_titlebar_checked(
        show_mock, destroy_mock, create_mock, view):
    view.on_action_show_titlebar(True)
    assert not (view.parent.windowFlags() & Qt.WindowType.FramelessWindowHint)
    show_mock.assert_called_once()
    destroy_mock.assert_called_once()
    create_mock.assert_called_once()


@patch('PyQt6.QtWidgets.QWidget.create')
@patch('PyQt6.QtWidgets.QWidget.destroy')
@patch('PyQt6.QtWidgets.QWidget.show')
def test_on_action_show_titlebar_unchecked(
        show_mock, destroy_mock, create_mock, view):
    view.on_action_show_titlebar(False)
    assert view.parent.windowFlags() & Qt.WindowType.FramelessWindowHint
    show_mock.assert_called_once()
    destroy_mock.assert_called_once()
    create_mock.assert_called_once()


@patch('beeref.widgets.welcome_overlay.WelcomeOverlay.cursor')
def test_on_action_move_window_when_welcome_overlay(cursor_mock, view):
    cursor_mock.return_value = MagicMock(
        pos=MagicMock(return_value=QtCore.QPointF(10.0, 20.0)))
    view.on_action_move_window()
    assert view.welcome_overlay.movewin_active is True
    assert view.welcome_overlay.event_start == QtCore.QPointF(10.0, 20.0)


def test_on_action_move_window_when_already_active(view):
    view.welcome_overlay.event_start = QtCore.QPointF(10.0, 20.0)
    view.welcome_overlay.movewin_active = True
    view.on_action_move_window()
    assert view.welcome_overlay.movewin_active is False
    assert view.welcome_overlay.event_start == QtCore.QPointF(10.0, 20.0)


@patch('beeref.view.BeeGraphicsView.cursor')
def test_on_action_move_window_when_scene(cursor_mock, view):
    cursor_mock.return_value = MagicMock(
        pos=MagicMock(return_value=QtCore.QPointF(10.0, 20.0)))
    view.welcome_overlay.hide()
    view.on_action_move_window()
    assert view.movewin_active is True
    assert view.event_start == QtCore.QPointF(10.0, 20.0)


def test_on_action_select_all(view, item):
    view.scene.addItem(item)
    item.setSelected(False)
    view.on_action_select_all()
    assert item.isSelected() is True


def test_on_action_deselect_all(view, item):
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_deselect_all()
    assert item.isSelected() is False


def test_on_action_delete_items(view, item):
    view.cancel_active_modes = MagicMock()
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_delete_items()
    assert view.scene.items() == []
    assert view.undo_stack.isClean() is False
    view.cancel_active_modes.assert_called_once()


@patch('beeref.scene.BeeGraphicsScene.arrange')
def test_on_action_arrange_horizontal(arrange_mock, view):
    view.on_action_arrange_horizontal()
    arrange_mock.assert_called_once_with()


@patch('beeref.scene.BeeGraphicsScene.arrange')
def test_on_action_arrange_vertical(arrange_mock, view):
    view.on_action_arrange_vertical()
    arrange_mock.assert_called_once_with(vertical=True)


@patch('beeref.scene.BeeGraphicsScene.arrange_optimal')
def test_on_action_arrange_optimal(arrange_mock, view):
    view.on_action_arrange_optimal()
    arrange_mock.assert_called_once_with()


@patch('beeref.scene.BeeGraphicsScene.arrange_square')
def test_on_action_arrange_square(arrange_mock, view):
    view.on_action_arrange_square()
    arrange_mock.assert_called_once_with()


@patch('beeref.widgets.ChangeOpacityDialog.__init__',
       return_value=None)
def test_on_action_change_opacity(dialog_mock, view):
    pixmapitem1 = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(pixmapitem1)
    pixmapitem1.setSelected(True)

    pixmapitem2 = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(pixmapitem2)
    pixmapitem2.setSelected(False)

    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)

    view.on_action_change_opacity()
    dialog_mock.assert_called_once_with(view, [pixmapitem1], view.undo_stack)


def test_on_action_grayscale(view):
    pixmapitem1 = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(pixmapitem1)
    pixmapitem1.setSelected(True)

    pixmapitem2 = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(pixmapitem2)
    pixmapitem2.setSelected(False)

    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)

    view.on_action_grayscale(True)
    assert len(view.undo_stack) == 1
    assert pixmapitem1.grayscale is True
    assert pixmapitem2.grayscale is False


def char_format_at(item, pos):
    cursor = item.textCursor()
    cursor.setPosition(pos)
    return cursor.charFormat()


def test_on_action_text_bold(view):
    textitem = BeeTextItem('make this bold')
    view.scene.addItem(textitem)
    textitem.setSelected(True)

    view.on_action_text_bold()
    assert char_format_at(textitem, 3).fontWeight() == QtGui.QFont.Weight.Bold
    assert len(view.undo_stack) == 1

    view.undo_stack.undo()
    assert char_format_at(textitem, 3).fontWeight() != QtGui.QFont.Weight.Bold


def test_on_action_text_bold_toggles_off(view):
    textitem = BeeTextItem('make this bold')
    view.scene.addItem(textitem)
    textitem.setSelected(True)

    view.on_action_text_bold()
    view.on_action_text_bold()
    assert char_format_at(textitem, 3).fontWeight() == (
        QtGui.QFont.Weight.Normal)


def test_on_action_text_bold_applies_to_selection_only(view):
    textitem = BeeTextItem('bold words plain words')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    cursor = textitem.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(10, QtGui.QTextCursor.MoveMode.KeepAnchor)
    textitem.setTextCursor(cursor)

    view.on_action_text_bold()
    assert char_format_at(textitem, 3).fontWeight() == QtGui.QFont.Weight.Bold
    assert char_format_at(textitem, 15).fontWeight() != (
        QtGui.QFont.Weight.Bold)


def test_on_action_text_bold_without_text_selected(view):
    pixmapitem = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(pixmapitem)
    pixmapitem.setSelected(True)
    view.on_action_text_bold()
    assert len(view.undo_stack) == 0


def test_on_action_size_increase(view):
    textitem = BeeTextItem('bigger please')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    before = char_format_at(textitem, 3).fontPointSize() or float(
        textitem.font().pointSize())

    view.on_action_size_increase()
    after = char_format_at(textitem, 3).fontPointSize()
    assert after > before
    assert len(view.undo_stack) == 1

    view.undo_stack.undo()
    assert char_format_at(textitem, 3).fontPointSize() != after


def test_on_action_size_decrease(view):
    textitem = BeeTextItem('smaller please')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    view.on_action_size_increase()
    bigger = char_format_at(textitem, 3).fontPointSize()

    view.on_action_size_decrease()
    assert char_format_at(textitem, 3).fontPointSize() < bigger


def test_text_size_steps_are_proportional(view):
    """Each press multiplies, so the step grows with the text."""

    textitem = BeeTextItem('scale me')
    view.scene.addItem(textitem)
    textitem.setSelected(True)

    view.on_action_size_increase()
    first = char_format_at(textitem, 3).fontPointSize()
    view.on_action_size_increase()
    second = char_format_at(textitem, 3).fontPointSize()

    # Every press multiplies by the same factor, so the second press adds
    # more points than the first one did
    assert second / first == pytest.approx(view.TEXT_SIZE_STEP)
    assert second - first > first - (first / view.TEXT_SIZE_STEP)


def test_text_size_keeps_relative_sizes_within_one_item(view):
    """A heading must stay bigger than the body text next to it."""

    textitem = BeeTextItem('heading body')
    view.scene.addItem(textitem)
    textitem.setSelected(True)

    cursor = textitem.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(7, QtGui.QTextCursor.MoveMode.KeepAnchor)
    charformat = QtGui.QTextCharFormat()
    charformat.setFontPointSize(40)
    cursor.mergeCharFormat(charformat)
    cursor.setPosition(8)
    cursor.setPosition(12, QtGui.QTextCursor.MoveMode.KeepAnchor)
    charformat = QtGui.QTextCharFormat()
    charformat.setFontPointSize(10)
    cursor.mergeCharFormat(charformat)

    view.on_action_size_increase()
    assert char_format_at(textitem, 3).fontPointSize() == 44
    assert char_format_at(textitem, 10).fontPointSize() == 11


def test_text_size_does_not_grow_past_the_maximum(view):
    textitem = BeeTextItem('big')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    for _ in range(200):
        view.on_action_size_increase()
    assert char_format_at(textitem, 1).fontPointSize() == view.TEXT_SIZE_MAX


def test_text_size_does_not_shrink_past_the_minimum(view):
    textitem = BeeTextItem('small')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    for _ in range(200):
        view.on_action_size_decrease()
    assert char_format_at(textitem, 1).fontPointSize() == view.TEXT_SIZE_MIN


def test_text_toolbar_shows_only_with_text_selected(view):
    textitem = BeeTextItem('some text')
    view.scene.addItem(textitem)
    assert view.text_toolbar.isVisible() is False

    textitem.setSelected(True)
    view.on_selection_changed()
    assert view.text_toolbar.isVisible() is True

    textitem.setSelected(False)
    view.on_selection_changed()
    assert view.text_toolbar.isVisible() is False


def test_text_toolbar_buttons_scale_the_text(view):
    textitem = BeeTextItem('click me')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    before = char_format_at(textitem, 3).fontPointSize() or float(
        textitem.font().pointSize())

    view.text_toolbar.bigger.click()
    assert char_format_at(textitem, 3).fontPointSize() > before


def test_on_action_text_highlight_color(view):
    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)

    with color_dialog(QtGui.QColor(255, 255, 0)):
        view.on_action_text_highlight_color()
    assert len(view.undo_stack) == 1
    cursor = textitem.textCursor()
    cursor.select(QtGui.QTextCursor.SelectionType.Document)
    assert cursor.charFormat().background().color() == QtGui.QColor(
        255, 255, 0)


def test_highlight_previews_while_picking(view):
    """The words change as the colour changes, before OK is pressed."""

    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    seen = []

    def fake_exec(dialog):
        dialog.setCurrentColor(QtGui.QColor(255, 255, 0))
        seen.append(char_format_at(textitem, 1).background().color())
        return QtWidgets.QDialog.DialogCode.Accepted.value

    with patch.object(QtWidgets.QColorDialog, 'exec', fake_exec):
        view.on_action_text_highlight_color()

    assert seen == [QtGui.QColor(255, 255, 0)]


def test_highlight_cancelled_puts_the_text_back(view):
    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    before = textitem.toHtml()

    with color_dialog(QtGui.QColor(255, 255, 0), accept=False):
        view.on_action_text_highlight_color()
    assert textitem.toHtml() == before
    assert len(view.undo_stack) == 0


def test_highlight_undo_restores_the_text_from_before(view):
    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    before = textitem.toHtml()

    with color_dialog(QtGui.QColor(255, 255, 0)):
        view.on_action_text_highlight_color()
    view.undo_stack.undo()
    assert textitem.toHtml() == before


@pytest.mark.parametrize('highlight,expected', [
    ((255, 255, 0), (0, 0, 0)),
    ((10, 10, 60), (255, 255, 255))])
def test_highlighted_words_take_their_colour_from_the_highlight(
        view, highlight, expected):
    """Not from the box: the words sit on the highlight."""

    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)

    with color_dialog(QtGui.QColor(*highlight)):
        view.on_action_text_highlight_color()
    assert char_format_at(textitem, 1).foreground().color() == QtGui.QColor(
        *expected)


def test_changing_the_box_colour_keeps_a_highlight_readable(view):
    """The box recolours its text, and must not flatten highlights."""

    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    with color_dialog(QtGui.QColor(255, 255, 0)):
        view.on_action_text_highlight_color()
    on_highlight = char_format_at(textitem, 1).foreground().color()

    with color_dialog(QtGui.QColor(0, 0, 0, 255)):
        view.on_action_text_box_color()

    assert char_format_at(textitem, 1).background().color() == QtGui.QColor(
        255, 255, 0)
    assert char_format_at(textitem, 1).foreground().color() == on_highlight


def color_dialog(color, accept=True):
    """Drive a real colour dialog without showing it.

    setCurrentColor emits currentColorChanged, so the preview runs
    exactly as it would while the user drags around the picker.
    """

    def fake_exec(dialog):
        dialog.setCurrentColor(color)
        if accept:
            return QtWidgets.QDialog.DialogCode.Accepted.value
        return QtWidgets.QDialog.DialogCode.Rejected.value

    # A plain function, not a mock: assigned to the class it binds as a
    # method, so the dialog arrives as self. autospec does not manage
    # that for sip methods.
    return patch.object(QtWidgets.QColorDialog, 'exec', fake_exec)


def test_on_action_text_box_color(view):
    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)

    with color_dialog(QtGui.QColor(0, 0, 255, 100)):
        view.on_action_text_box_color()
    assert len(view.undo_stack) == 1
    assert textitem.box_color == QtGui.QColor(0, 0, 255, 100)


def test_text_box_color_previews_while_picking(view):
    """The board updates as the colour changes, before OK is pressed."""

    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    seen = []

    def fake_exec(dialog):
        dialog.setCurrentColor(QtGui.QColor(10, 20, 30, 255))
        # What the item looks like while the dialog is still open
        seen.append(QtGui.QColor(textitem.box_color))
        return QtWidgets.QDialog.DialogCode.Accepted.value

    with patch.object(QtWidgets.QColorDialog, 'exec', fake_exec):
        view.on_action_text_box_color()

    assert seen == [QtGui.QColor(10, 20, 30, 255)]


def test_text_box_color_undo_restores_the_colour_from_before(view):
    """Undo must not restore a previewed colour."""

    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    before = QtGui.QColor(textitem.box_color)

    with color_dialog(QtGui.QColor(0, 0, 255, 100)):
        view.on_action_text_box_color()
    view.undo_stack.undo()
    assert textitem.box_color == before


def test_text_box_color_cancelled_puts_the_colour_back(view):
    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    before = QtGui.QColor(textitem.box_color)

    with color_dialog(QtGui.QColor(0, 0, 255, 100), accept=False):
        view.on_action_text_box_color()
    assert textitem.box_color == before
    assert len(view.undo_stack) == 0


def test_on_action_group_items(view):
    item1 = BeeTextItem('one')
    view.scene.addItem(item1)
    item1.setSelected(True)
    item2 = BeeTextItem('two')
    view.scene.addItem(item2)
    item2.setSelected(True)

    view.on_action_group_items()
    assert len(view.undo_stack) == 1
    groups = list(view.scene.items_by_type('group'))
    assert len(groups) == 1
    # Qt does not guarantee the order of selectedItems()
    assert set(groups[0].bee_children()) == {item1, item2}


def test_on_action_group_items_without_selection(view):
    item = BeeTextItem('one')
    view.scene.addItem(item)
    item.setSelected(False)
    view.on_action_group_items()
    assert len(view.undo_stack) == 0


def test_on_action_ungroup_items(view):
    item = BeeTextItem('one')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_group_items()
    view.on_action_ungroup_items()
    assert len(view.undo_stack) == 2
    assert list(view.scene.items_by_type('group')) == []
    assert item.parentItem() is None


def test_on_action_ungroup_items_when_no_group_selected(view):
    item = BeeTextItem('one')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_ungroup_items()
    assert len(view.undo_stack) == 0


def test_on_action_group_box_color(view):
    item = BeeTextItem('one')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_group_items()

    with color_dialog(QtGui.QColor(1, 2, 3, 200)):
        view.on_action_group_box_color()
    group = list(view.scene.items_by_type('group'))[0]
    assert group.box_color == QtGui.QColor(1, 2, 3, 200)
    assert len(view.undo_stack) == 2


def test_group_box_color_cancelled_puts_the_colour_back(view):
    item = BeeTextItem('one')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]
    before = QtGui.QColor(group.box_color)

    with color_dialog(QtGui.QColor(1, 2, 3, 200), accept=False):
        view.on_action_group_box_color()
    assert group.box_color == before
    assert len(view.undo_stack) == 1


def test_on_action_lock_group(view):
    item = BeeTextItem('one')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]

    view.on_action_lock_group(True)
    assert group.locked is True
    view.on_action_lock_group(False)
    assert group.locked is False


def test_on_action_lock_group_closes_open_group(view):
    item = BeeTextItem('one')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]
    view.scene.enter_group(group, item)
    group.setSelected(True)

    view.on_action_lock_group(True)
    assert view.scene.active_group is None


@patch('PyQt6.QtWidgets.QMenu.exec')
def test_on_context_menu_over_group(exec_mock, view):
    item = BeeTextItem('one')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]

    with patch.object(view, 'get_group_at', return_value=group):
        view.on_context_menu(QtCore.QPoint(0, 0))
    assert group.isSelected() is True
    exec_mock.assert_called_once()


def test_get_group_at_returns_group_for_child(view):
    item = BeeTextItem('one')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]

    with patch.object(view.scene, 'items', return_value=[item, group]):
        assert view.get_group_at(QtCore.QPoint(0, 0)) is group


def test_get_group_at_ignores_open_group(view):
    item = BeeTextItem('one')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]
    view.scene.enter_group(group, item)

    with patch.object(view.scene, 'items', return_value=[item]):
        assert view.get_group_at(QtCore.QPoint(0, 0)) is None


@patch.object(QtWidgets.QColorDialog, 'exec')
def test_on_action_group_box_color_when_no_group(exec_mock, view):
    item = BeeTextItem('one')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_group_box_color()
    exec_mock.assert_not_called()
    assert len(view.undo_stack) == 0


def add_text_items(view, *texts):
    items = []
    for i, text in enumerate(texts):
        item = BeeTextItem(text)
        view.scene.addItem(item)
        item.setPos(0, i * 100)
        items.append(item)
    return items


def test_get_text_search_matches_is_case_insensitive(view):
    item1, item2, item3 = add_text_items(
        view, 'Hello World', 'nothing here', 'hello again')
    view.text_search_query = 'HELLO'
    assert view.get_text_search_matches() == [item1, item3]


def test_get_text_search_matches_ordered_top_to_bottom(view):
    item1, item2 = add_text_items(view, 'match one', 'match two')
    item1.setPos(0, 500)
    item2.setPos(0, 100)
    view.text_search_query = 'match'
    assert view.get_text_search_matches() == [item2, item1]


def test_find_next_text_match_selects_and_centres(view):
    item1, item2 = add_text_items(view, 'find me', 'other')
    view.text_search_query = 'find me'
    with patch.object(view, 'centerOn') as center_mock:
        view.find_next_text_match()
    assert item1.isSelected() is True
    assert item2.isSelected() is False
    center_mock.assert_called_once()


def test_find_next_text_match_cycles(view):
    item1, item2 = add_text_items(view, 'match one', 'match two')
    view.text_search_query = 'match'
    with patch.object(view, 'centerOn'):
        view.find_next_text_match()
        assert item1.isSelected() is True
        view.find_next_text_match()
        assert item2.isSelected() is True
        assert item1.isSelected() is False
        # Wraps around to the first match again
        view.find_next_text_match()
        assert item1.isSelected() is True


def test_find_next_text_match_when_no_matches(view):
    add_text_items(view, 'nothing here')
    view.text_search_query = 'absent'
    with patch.object(view, 'centerOn') as center_mock:
        view.find_next_text_match()
    center_mock.assert_not_called()
    assert view.text_search_index == -1


@patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('me', True))
def test_on_action_find_text(dialog_mock, view):
    item1, item2 = add_text_items(view, 'find me', 'other')
    with patch.object(view, 'centerOn'):
        view.on_action_find_text()
    assert view.text_search_query == 'me'
    assert item1.isSelected() is True


@patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('', False))
def test_on_action_find_text_when_cancelled(dialog_mock, view):
    add_text_items(view, 'find me')
    view.text_search_query = 'previous'
    view.on_action_find_text()
    assert view.text_search_query == 'previous'


@patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('me', True))
def test_on_action_find_next_asks_for_query_when_none_yet(dialog_mock, view):
    add_text_items(view, 'find me')
    with patch.object(view, 'centerOn'):
        view.on_action_find_next()
    dialog_mock.assert_called_once()
    assert view.text_search_query == 'me'


@patch('PyQt6.QtWidgets.QInputDialog.getText')
def test_on_action_find_next_reuses_existing_query(dialog_mock, view):
    item1, _ = add_text_items(view, 'find me', 'other')
    view.text_search_query = 'find'
    with patch.object(view, 'centerOn'):
        view.on_action_find_next()
    dialog_mock.assert_not_called()
    assert item1.isSelected() is True


@pytest.mark.parametrize('zoom', [0.01, 0.05, 0.1, 0.5, 1, 2, 5, 20, 100])
def test_get_grid_step_stays_in_sensible_range(view, zoom):
    view.setTransform(QtGui.QTransform.fromScale(zoom, zoom))
    onscreen = view.get_grid_step() * zoom
    assert view.GRID_MIN_SPACING <= onscreen <= view.GRID_MAX_SPACING


def test_get_grid_step_uses_setting_when_zoom_neutral(view, settings):
    settings.setValue('View/grid_size', 50)
    view.setTransform(QtGui.QTransform.fromScale(1, 1))
    assert view.get_grid_step() == 50


def test_on_action_show_grid(view):
    view.on_action_show_grid(True)
    assert view.show_grid is True
    view.on_action_show_grid(False)
    assert view.show_grid is False


@patch('PyQt6.QtWidgets.QGraphicsView.drawBackground')
def test_draw_background_draws_grid_when_enabled(super_mock, view):
    view.show_grid = True
    painter = MagicMock()
    view.drawBackground(painter, QtCore.QRectF(0, 0, 500, 500))
    super_mock.assert_called_once()
    painter.drawLines.assert_called_once()
    lines = painter.drawLines.call_args[0][0]
    # 500x500 at the default spacing of 100: lines at 0, 100 ... 400
    assert len(lines) == 10


@patch('PyQt6.QtWidgets.QGraphicsView.drawBackground')
def test_draw_background_skips_grid_when_disabled(super_mock, view):
    view.show_grid = False
    painter = MagicMock()
    view.drawBackground(painter, QtCore.QRectF(0, 0, 500, 500))
    super_mock.assert_called_once()
    painter.drawLines.assert_not_called()


def test_grid_setting_change_emits_grid_changed(settings):
    callback = MagicMock()
    settings_events.grid_changed.connect(callback)
    try:
        settings.setValue('View/grid_color', '#ff0000')
        callback.assert_called_once()
    finally:
        settings_events.grid_changed.disconnect(callback)


def test_on_grid_changed_repaints_viewport(view):
    with patch.object(view.viewport(), 'update') as update_mock:
        view.on_grid_changed()
        update_mock.assert_called_once()


@patch('PyQt6.QtWidgets.QMenu.exec')
def test_on_context_menu_over_text_item(exec_mock, view):
    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    with patch.object(view, 'get_text_item_at', return_value=textitem):
        view.on_context_menu(QtCore.QPoint(0, 0))
    # The clicked item gets selected so the options apply to it
    assert textitem.isSelected() is True
    exec_mock.assert_called_once()


@patch('PyQt6.QtWidgets.QMenu.exec')
def test_on_context_menu_over_text_item_keeps_existing_selection(
        exec_mock, view):
    textitem1 = BeeTextItem('foo')
    view.scene.addItem(textitem1)
    textitem1.setSelected(True)
    textitem2 = BeeTextItem('bar')
    view.scene.addItem(textitem2)
    textitem2.setSelected(True)

    with patch.object(view, 'get_text_item_at', return_value=textitem2):
        view.on_context_menu(QtCore.QPoint(0, 0))
    assert textitem1.isSelected() is True
    assert textitem2.isSelected() is True


@patch('PyQt6.QtWidgets.QMenu.exec')
def test_on_context_menu_not_over_text_item(exec_mock, view):
    with patch.object(view, 'get_text_item_at', return_value=None):
        view.on_context_menu(QtCore.QPoint(0, 0))
    exec_mock.assert_called_once()


def test_on_context_menu_over_text_inside_group(view):
    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]
    view.text_context_menu = MagicMock()
    view.group_context_menu = MagicMock()

    with patch.object(view, 'get_text_item_at', return_value=textitem):
        view.on_context_menu(QtCore.QPoint(0, 0))

    # The text options stay reachable inside a group
    view.text_context_menu.exec.assert_called_once()
    view.group_context_menu.exec.assert_not_called()
    assert textitem.isSelected() is True
    assert view.scene.active_group is group


def test_on_context_menu_over_text_inside_locked_group(view):
    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]
    group.locked = True
    view.text_context_menu = MagicMock()
    view.group_context_menu = MagicMock()

    with patch.object(view, 'get_text_item_at', return_value=textitem), \
            patch.object(view, 'get_group_at', return_value=group):
        view.on_context_menu(QtCore.QPoint(0, 0))

    view.text_context_menu.exec.assert_not_called()
    view.group_context_menu.exec.assert_called_once()
    assert view.scene.active_group is None


def test_on_context_menu_over_image_inside_group(view):
    """The image's own actions must be reachable inside a group."""

    pixmapitem = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(pixmapitem)
    pixmapitem.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]
    view.context_menu = MagicMock()
    view.group_context_menu = MagicMock()

    with patch.object(view, 'get_item_at', return_value=pixmapitem):
        view.on_context_menu(QtCore.QPoint(0, 0))

    view.context_menu.exec.assert_called_once()
    view.group_context_menu.exec.assert_not_called()
    assert view.scene.active_group is group
    assert pixmapitem.isSelected() is True
    # The image's own actions now apply to it
    assert view.scene.has_single_image_selection() is True


def test_on_context_menu_over_image_inside_locked_group(view):
    pixmapitem = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(pixmapitem)
    pixmapitem.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]
    group.locked = True
    view.context_menu = MagicMock()
    view.group_context_menu = MagicMock()

    with patch.object(view, 'get_item_at', return_value=pixmapitem), \
            patch.object(view, 'get_group_at', return_value=group):
        view.on_context_menu(QtCore.QPoint(0, 0))

    view.group_context_menu.exec.assert_called_once()
    view.context_menu.exec.assert_not_called()
    assert view.scene.active_group is None


def test_on_context_menu_over_the_group_box(view):
    """Clicking the box itself still offers the group's actions."""

    pixmapitem = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(pixmapitem)
    pixmapitem.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]
    view.context_menu = MagicMock()
    view.group_context_menu = MagicMock()

    with patch.object(view, 'get_item_at', return_value=None), \
            patch.object(view, 'get_group_at', return_value=group):
        view.on_context_menu(QtCore.QPoint(0, 0))

    view.group_context_menu.exec.assert_called_once()


def test_get_item_at_skips_groups(view):
    pixmapitem = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(pixmapitem)
    pixmapitem.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]

    with patch.object(view.scene, 'items',
                      return_value=[pixmapitem, group]):
        assert view.get_item_at(QtCore.QPoint(0, 0)) is pixmapitem
    with patch.object(view.scene, 'items', return_value=[group]):
        assert view.get_item_at(QtCore.QPoint(0, 0)) is None


def test_image_inside_group_can_be_cropped(view):
    pixmapitem = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(pixmapitem)
    pixmapitem.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]

    view.scene.enter_group(group, pixmapitem)
    view.on_action_crop()
    assert view.scene.crop_item is pixmapitem
    assert pixmapitem.parentItem() is group


def test_get_text_item_at_ignores_non_text_items(view):
    pixmapitem = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(pixmapitem)
    with patch.object(view.scene, 'items', return_value=[pixmapitem]):
        assert view.get_text_item_at(QtCore.QPoint(0, 0)) is None


def test_get_text_item_at_finds_text_below_other_items(view):
    textitem = BeeTextItem('foo')
    view.scene.addItem(textitem)
    pixmapitem = BeePixmapItem(QtGui.QImage())
    view.scene.addItem(pixmapitem)
    # A multi select item has no TYPE at all and must not blow up
    with patch.object(view.scene, 'items',
                      return_value=[view.scene.multi_select_item,
                                    textitem]):
        assert view.get_text_item_at(QtCore.QPoint(0, 0)) == textitem


def test_cancel_active_modes_when_sample_color_mode(view):
    view.active_mode = view.SAMPLE_COLOR_MODE
    view.sample_color_widget = widgets.SampleColorWidget(
        view, MagicMock(), MagicMock())
    view.viewport().setCursor(Qt.CursorShape.CrossCursor)
    view.cancel_active_modes()

    assert view.active_mode is None
    assert hasattr(view, 'sample_color_widget') is False
    assert view.viewport().cursor() == Qt.CursorShape.ArrowCursor


def test_cancel_sample_color_mode_when_multi_selection(view, item):
    view.scene.addItem(item)
    item.setSelected(True)
    item2 = BeeTextItem('foo')
    view.scene.addItem(item2)
    item2.setSelected(True)

    view.scene.multi_select_item.bring_to_front = MagicMock()
    view.active_mode = view.SAMPLE_COLOR_MODE
    view.sample_color_widget = widgets.SampleColorWidget(
        view, MagicMock(), MagicMock())
    view.viewport().setCursor(Qt.CursorShape.CrossCursor)
    view.cancel_active_modes()

    assert view.active_mode is None
    assert hasattr(view, 'sample_color_widget') is False
    assert view.viewport().cursor() == Qt.CursorShape.ArrowCursor
    view.scene.multi_select_item.bring_to_front.assert_called_once()


def test_window_title_shows_the_version(view):
    """Two computers run this, so a window has to name its own build."""

    view.update_window_title()
    assert constants.VERSION in view.parent.windowTitle()


@patch('PyQt6.QtGui.QUndoStack.isClean', return_value=True)
def test_update_window_title_no_changes_no_filename(clear_mock, view):
    view.filename = None
    view.update_window_title()
    assert view.parent.windowTitle() == APP_TITLE


@patch('PyQt6.QtGui.QUndoStack.isClean', return_value=False)
def test_update_window_title_changes_no_filename(clear_mock, view):
    view.filename = None
    view.update_window_title()
    assert view.parent.windowTitle() == f'[Untitled]* - {APP_TITLE}'


@patch('PyQt6.QtGui.QUndoStack.isClean', return_value=True)
def test_update_window_title_no_changes_filename(clear_mock, view):
    view.filename = 'test.bee'
    view.update_window_title()
    assert view.parent.windowTitle() == f'test.bee - {APP_TITLE}'


@patch('PyQt6.QtGui.QUndoStack.isClean', return_value=False)
def test_update_window_title_changes_filename(clear_mock, view):
    view.filename = 'test.bee'
    view.update_window_title()
    assert view.parent.windowTitle() == f'test.bee* - {APP_TITLE}'


@patch('beeref.view.BeeGraphicsView.recalc_scene_rect')
@patch('beeref.scene.BeeGraphicsScene.on_view_scale_change')
def test_scale(view_scale_mock, recalc_mock, view):
    view.scale(3.3, 3.3)
    view_scale_mock.assert_called_once_with()
    recalc_mock.assert_called_once_with()
    assert view.get_scale() == 3.3


@patch('PyQt6.QtWidgets.QScrollBar.setValue')
def test_pan(scroll_value_mock, view, item):
    view.scene.addItem(item)
    view.pan(QtCore.QPointF(5.0, 10.0))
    assert scroll_value_mock.call_count == 2


@patch('PyQt6.QtWidgets.QScrollBar.setValue')
def test_pan_when_no_items(scroll_value_mock, view):
    view.pan(QtCore.QPointF(5.0, 10.0))
    scroll_value_mock.assert_not_called()


@patch('beeref.view.BeeGraphicsView.reset_previous_transform')
@patch('beeref.view.BeeGraphicsView.pan')
def test_zoom_in(pan_mock, reset_mock, view, imgfilename3x3):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    view.zoom(40, QtCore.QPointF(10.0, 10.0))
    assert view.get_scale() == 1.04
    reset_mock.assert_called_once_with()
    pan_mock.assert_called_once()


@patch('beeref.view.BeeGraphicsView.reset_previous_transform')
@patch('beeref.view.BeeGraphicsView.pan')
def test_zoom_in_max_zoom_size(pan_mock, reset_mock, view, imgfilename3x3):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scale(10000000, 10000000)
    view.scene.addItem(item)
    view.zoom(40, QtCore.QPointF(10.0, 10.0))
    assert view.get_scale() == 10000000
    reset_mock.assert_not_called()
    pan_mock.assert_not_called()


@patch('beeref.view.BeeGraphicsView.reset_previous_transform')
@patch('beeref.view.BeeGraphicsView.pan')
def test_zoom_out(pan_mock, reset_mock, view, imgfilename3x3):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scale(100, 100)
    view.scene.addItem(item)
    view.zoom(-40, QtCore.QPointF(10.0, 10.0))
    assert view.get_scale() == 100 / 1.04
    reset_mock.assert_called_once_with()
    pan_mock.assert_called_once()


@patch('beeref.view.BeeGraphicsView.reset_previous_transform')
@patch('beeref.view.BeeGraphicsView.pan')
def test_zoom_out_min_zoom_size(pan_mock, reset_mock, view, item):
    view.scene.addItem(item)
    view.zoom(-40, QtCore.QPointF(10.0, 10.0))
    assert view.get_scale() == 1
    reset_mock.assert_not_called()
    pan_mock.assert_not_called()


@patch('beeref.view.BeeGraphicsView.reset_previous_transform')
@patch('beeref.view.BeeGraphicsView.pan')
def test_no_items(pan_mock, reset_mock, view, item):
    view.zoom(40, QtCore.QPointF(10.0, 10.0))
    assert view.get_scale() == 1
    reset_mock.assert_not_called()
    pan_mock.assert_not_called()


@patch('beeref.view.BeeGraphicsView.reset_previous_transform')
@patch('beeref.view.BeeGraphicsView.pan')
def test_delta_zero(pan_mock, reset_mock, view, item):
    view.scene.addItem(item)
    view.zoom(0, QtCore.QPointF(10.0, 10.0))
    assert view.get_scale() == 1
    reset_mock.assert_not_called()
    pan_mock.assert_not_called()


@patch('beeref.view.BeeGraphicsView.smooth_zoom')
def test_wheel_event_zoom(zoom_mock, view):
    event = MagicMock()
    event.angleDelta.return_value = QtCore.QPointF(0.0, 40.0)
    event.position.return_value = QtCore.QPointF(10.0, 20.0)
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    view.wheelEvent(event)
    zoom_mock.assert_called_once_with(40, QtCore.QPointF(10.0, 20.0))
    event.accept.assert_called_once_with()


@patch('beeref.view.BeeGraphicsView.smooth_zoom')
def test_wheel_event_zoom_custom_inverted(zoom_mock, view, kbsettings):
    kbsettings.MOUSEWHEEL_ACTIONS['zoom2'].set_modifiers(['Alt'])
    kbsettings.MOUSEWHEEL_ACTIONS['zoom2'].set_inverted(True)
    event = MagicMock()
    event.angleDelta.return_value = QtCore.QPointF(0.0, 40.0)
    event.position.return_value = QtCore.QPointF(10.0, 20.0)
    event.modifiers.return_value = Qt.KeyboardModifier.AltModifier
    view.wheelEvent(event)
    zoom_mock.assert_called_once_with(-40, QtCore.QPointF(10.0, 20.0))
    event.accept.assert_called_once_with()


@patch('beeref.view.BeeGraphicsView.pan')
def test_wheel_event_pan_vertically(pan_mock, view):
    event = MagicMock()
    event.angleDelta.return_value = QtCore.QPointF(0.0, 40.0)
    event.position.return_value = QtCore.QPointF(10.0, 20.0)
    event.modifiers.return_value = (Qt.KeyboardModifier.ShiftModifier
                                    | Qt.KeyboardModifier.ControlModifier)
    view.wheelEvent(event)
    pan_mock.assert_called_once_with(QtCore.QPointF(20, 0))
    event.accept.assert_called_once_with()


@patch('beeref.view.BeeGraphicsView.pan')
def test_wheel_event_pan_vertically_custom_inverted(
        pan_mock, view, kbsettings):
    kbsettings.MOUSEWHEEL_ACTIONS['pan_vertical2'].set_modifiers(['Alt'])
    kbsettings.MOUSEWHEEL_ACTIONS['pan_vertical2'].set_inverted(True)
    event = MagicMock()
    event.angleDelta.return_value = QtCore.QPointF(0.0, 40.0)
    event.position.return_value = QtCore.QPointF(10.0, 20.0)
    event.modifiers.return_value = Qt.KeyboardModifier.AltModifier
    view.wheelEvent(event)
    pan_mock.assert_called_once_with(QtCore.QPointF(-20, 0))
    event.accept.assert_called_once_with()


@patch('beeref.view.BeeGraphicsView.pan')
def test_wheel_event_pan_horizontally(pan_mock, view):
    event = MagicMock()
    event.angleDelta.return_value = QtCore.QPointF(0.0, 40.0)
    event.position.return_value = QtCore.QPointF(10.0, 20.0)
    event.modifiers.return_value = Qt.KeyboardModifier.ShiftModifier
    view.wheelEvent(event)
    pan_mock.assert_called_once_with(QtCore.QPointF(0, 20))
    event.accept.assert_called_once_with()


@patch('beeref.view.BeeGraphicsView.pan')
def test_wheel_event_pan_horizontally_custom_inverted(
        pan_mock, view, kbsettings):
    kbsettings.MOUSEWHEEL_ACTIONS['pan_horizontal2'].set_modifiers(['Alt'])
    kbsettings.MOUSEWHEEL_ACTIONS['pan_horizontal2'].set_inverted(True)
    event = MagicMock()
    event.angleDelta.return_value = QtCore.QPointF(0.0, 40.0)
    event.position.return_value = QtCore.QPointF(10.0, 20.0)
    event.modifiers.return_value = Qt.KeyboardModifier.AltModifier
    view.wheelEvent(event)
    pan_mock.assert_called_once_with(QtCore.QPointF(0, -20))
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_mouse_press_zoom(mouse_event_mock, view):
    event = MagicMock()
    event.position.return_value = QtCore.QPointF(10.0, 20.0)
    event.button.return_value = Qt.MouseButton.MiddleButton
    event.modifiers.return_value = Qt.KeyboardModifier.ControlModifier
    view.mousePressEvent(event)
    assert view.active_mode == view.ZOOM_MODE
    assert view.event_start == QtCore.QPointF(10.0, 20.0)
    assert view.event_anchor == QtCore.QPointF(10.0, 20.0)
    assert view.event_inverted is False
    mouse_event_mock.assert_not_called()
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_mouse_press_zoom_custom_inverted(mouse_event_mock, view, kbsettings):
    kbsettings.MOUSE_ACTIONS['zoom1'].set_button('Left')
    kbsettings.MOUSE_ACTIONS['zoom1'].set_modifiers(['Alt', 'Shift'])
    kbsettings.MOUSE_ACTIONS['zoom1'].set_inverted(True)
    event = MagicMock()
    event.position.return_value = QtCore.QPointF(10.0, 20.0)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = (
        Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
    view.mousePressEvent(event)
    assert view.active_mode == view.ZOOM_MODE
    assert view.event_start == QtCore.QPointF(10.0, 20.0)
    assert view.event_anchor == QtCore.QPointF(10.0, 20.0)
    assert view.event_inverted is True
    mouse_event_mock.assert_not_called()
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_mouse_press_pan_middle_drag(mouse_event_mock, view):
    event = MagicMock()
    event.position.return_value = QtCore.QPointF(10.0, 20.0)
    event.button.return_value = Qt.MouseButton.MiddleButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    view.mousePressEvent(event)
    assert view.active_mode == view.PAN_MODE
    assert view.event_start == QtCore.QPointF(10.0, 20.0)
    mouse_event_mock.assert_not_called()
    view.cursor() == Qt.CursorShape.ClosedHandCursor
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_mouse_press_pan_alt_left_drag(mouse_event_mock, view):
    event = MagicMock()
    event.position.return_value = QtCore.QPointF(10.0, 20.0)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.AltModifier
    view.mousePressEvent(event)
    assert view.active_mode == view.PAN_MODE
    assert view.event_start == QtCore.QPointF(10.0, 20.0)
    mouse_event_mock.assert_not_called()
    view.cursor() == Qt.CursorShape.ClosedHandCursor
    event.accept.assert_called_once_with()


@patch('beeref.widgets.BeeNotification')
@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_mouse_press_sample_color_when_color(
        mouse_event_mock, notification_mock, view):
    view.scene.sample_color_at = MagicMock(
        return_value=QtGui.QColor(255, 0, 0, 255))
    view.active_mode = view.SAMPLE_COLOR_MODE
    event = MagicMock()
    event.pos.return_value = QtCore.QPoint(2, 2)
    event.button.return_value = Qt.MouseButton.LeftButton

    view.mousePressEvent(event)
    assert QtWidgets.QApplication.clipboard().text() == '#ff0000'
    notification_mock.assert_called_once_with(
        view, 'Copied color to clipboard: #ff0000')
    assert view.active_mode is None
    view.scene.sample_color_at.assert_called_once()
    mouse_event_mock.assert_not_called()


@patch('beeref.widgets.BeeNotification')
@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_mouse_press_sample_color_when_color_with_alpha(
        mouse_event_mock, notification_mock, view):
    view.scene.sample_color_at = MagicMock(
        return_value=QtGui.QColor(255, 0, 0, 100))
    view.active_mode = view.SAMPLE_COLOR_MODE
    event = MagicMock()
    event.pos.return_value = QtCore.QPoint(2, 2)
    event.button.return_value = Qt.MouseButton.LeftButton

    view.mousePressEvent(event)
    assert QtWidgets.QApplication.clipboard().text() == '#ff000064'
    notification_mock.assert_called_once_with(
        view, 'Copied color to clipboard: #ff000064')
    assert view.active_mode is None
    view.scene.sample_color_at.assert_called_once()
    mouse_event_mock.assert_not_called()


@patch('beeref.widgets.BeeNotification')
@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_mouse_press_sample_color_when_no_color(
        mouse_event_mock, notification_mock, view):
    view.scene.sample_color_at = MagicMock(return_value=None)
    view.active_mode = view.SAMPLE_COLOR_MODE
    event = MagicMock()
    event.pos.return_value = QtCore.QPoint(2, 2)
    event.button.return_value = Qt.MouseButton.LeftButton

    view.mousePressEvent(event)
    notification_mock.assert_not_called()
    assert view.active_mode is None
    view.scene.sample_color_at.assert_called_once()
    mouse_event_mock.assert_not_called()
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
@patch('beeref.view.BeeGraphicsView.cursor')
def test_mouse_press_move_window(cursor_mock, mouse_event_mock, view):
    event = MagicMock()
    cursor_mock.return_value = MagicMock(
        pos=MagicMock(return_value=QtCore.QPointF(10.0, 20.0)))
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = (
        Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier)
    view.mousePressEvent(event)
    assert view.active_mode is None
    assert view.movewin_active is True
    assert view.event_start == view.mapToGlobal(QtCore.QPointF(10.0, 20.0))
    mouse_event_mock.assert_not_called()
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_mouse_press_when_move_window_active(mouse_event_mock, view):
    view.movewin_active = True
    view.mousePressEvent(MagicMock())
    assert view.movewin_active is False
    mouse_event_mock.assert_not_called()


@patch('PyQt6.QtWidgets.QGraphicsView.keyPressEvent')
def test_key_press_when_sample_color_mode(key_event_mock, view):
    view.active_mode = view.SAMPLE_COLOR_MODE
    event = MagicMock()
    view.keyPressEvent(event)
    assert view.active_mode is None
    event.accept.assert_called_once_with()
    key_event_mock.assert_not_called()


@patch('PyQt6.QtWidgets.QGraphicsView.keyPressEvent')
def test_key_press_when_move_window_active(key_event_mock, view):
    view.movewin_active = True
    view.keyPressEvent(MagicMock())
    assert view.movewin_active is False
    key_event_mock.assert_not_called()


@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_mouse_press_unhandled(mouse_event_mock, view):
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = None
    view.mousePressEvent(event)
    assert view.active_mode is None
    mouse_event_mock.assert_called_once_with(event)
    event.accept.assert_not_called()


@patch('PyQt6.QtWidgets.QGraphicsView.mouseMoveEvent')
@patch('beeref.view.BeeGraphicsView.pan')
def test_mouse_move_pan(pan_mock, mouse_event_mock, view):
    view.active_mode = view.PAN_MODE
    view.event_start = QtCore.QPointF(55.0, 66.0)
    event = MagicMock()
    event.position.return_value = QtCore.QPointF(10.0, 20.0)
    view.mouseMoveEvent(event)
    pan_mock.assert_called_once_with(QtCore.QPointF(45.0, 46.0))
    mouse_event_mock.assert_not_called()
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mouseMoveEvent')
@patch('beeref.view.BeeGraphicsView.zoom')
def test_mouse_move_zoom(zoom_mock, mouse_event_mock, view):
    view.active_mode = view.ZOOM_MODE
    view.event_anchor = QtCore.QPointF(55.0, 66.0)
    view.event_start = QtCore.QPointF(10.0, 20.0)
    view.event_inverted = False
    event = MagicMock()
    event.position.return_value = QtCore.QPointF(10.0, 18.0)
    view.mouseMoveEvent(event)
    zoom_mock.assert_called_once_with(40, QtCore.QPointF(55.0, 66.0))
    mouse_event_mock.assert_not_called()
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mouseMoveEvent')
@patch('beeref.view.BeeGraphicsView.zoom')
def test_mouse_move_zoom_inverted(zoom_mock, mouse_event_mock, view):
    view.active_mode = view.ZOOM_MODE
    view.event_anchor = QtCore.QPointF(55.0, 66.0)
    view.event_start = QtCore.QPointF(10.0, 20.0)
    view.event_inverted = True
    event = MagicMock()
    event.position.return_value = QtCore.QPointF(10.0, 18.0)
    view.mouseMoveEvent(event)
    zoom_mock.assert_called_once_with(-40, QtCore.QPointF(55.0, 66.0))
    mouse_event_mock.assert_not_called()
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mouseMoveEvent')
def test_mouse_move_sample_color(mouse_event_mock, view):
    view.active_mode = view.SAMPLE_COLOR_MODE
    view.scene.sample_color_at = MagicMock(
        return_value=QtGui.QColor(255, 0, 0, 255))
    view.sample_color_widget = MagicMock()
    event = MagicMock()
    event.pos.return_value = QtCore.QPoint(2, 2)
    event.position.return_value = QtCore.QPointF(10.0, 18.0)
    view.mouseMoveEvent(event)
    view.scene.sample_color_at.assert_called_once()
    view.sample_color_widget.update.assert_called_once_with(
        QtCore.QPointF(10.0, 18.0),
        QtGui.QColor(255, 0, 0, 255))
    mouse_event_mock.assert_not_called()
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mouseMoveEvent')
@patch('PyQt6.QtWidgets.QWidget.move')
def test_mouse_move_movewin(move_mock, mouse_event_mock, view):
    view.movewin_active = True
    view.event_start = QtCore.QPointF(10.0, 20.0)
    event = MagicMock()
    event.position.return_value = QtCore.QPointF(15.0, 18.0)
    view.mouseMoveEvent(event)
    move_mock.assert_called_once_with(5, -2)
    mouse_event_mock.assert_not_called()
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mouseMoveEvent')
def test_mouse_move_unhandled(mouse_event_mock, view):
    event = MagicMock()
    event.position.return_value = QtCore.QPointF(10.0, 20.0)
    view.mouseMoveEvent(event)
    mouse_event_mock.assert_called_once_with(event)
    event.accept.assert_not_called()


@patch('PyQt6.QtWidgets.QGraphicsView.mouseReleaseEvent')
def test_mouse_release_pan(mouse_event_mock, view):
    event = MagicMock()
    view.active_mode = view.PAN_MODE
    view.setCursor(Qt.CursorShape.ClosedHandCursor)
    view.mouseReleaseEvent(event)
    mouse_event_mock.assert_not_called()
    assert view.active_mode is None
    event.accept.assert_called_once_with()
    view.cursor() == Qt.CursorShape.ArrowCursor


@patch('PyQt6.QtWidgets.QGraphicsView.mouseReleaseEvent')
def test_mouse_release_zoom(mouse_event_mock, view):
    event = MagicMock()
    view.active_mode = view.ZOOM_MODE
    view.mouseReleaseEvent(event)
    mouse_event_mock.assert_not_called()
    assert view.active_mode is None
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mouseReleaseEvent')
def test_mouse_release_movewin(mouse_event_mock, view):
    event = MagicMock()
    view.movewin_active = True
    view.mouseReleaseEvent(event)
    mouse_event_mock.assert_not_called()
    assert view.movewin_active is False
    event.accept.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsView.mouseReleaseEvent')
def test_mouse_release_unhandled(mouse_event_mock, view):
    event = MagicMock()
    view.mouseReleaseEvent(event)
    mouse_event_mock.assert_called_once_with(event)
    event.accept.assert_not_called()


def test_drag_enter_when_url(view, imgfilename3x3):
    url = QtCore.QUrl()
    url.fromLocalFile(imgfilename3x3)
    mimedata = QtCore.QMimeData()
    mimedata.setUrls([url])
    event = MagicMock()
    event.mimeData.return_value = mimedata

    view.dragEnterEvent(event)
    event.acceptProposedAction.assert_called_once()


def test_drag_enter_when_img(view, imgfilename3x3):
    mimedata = QtCore.QMimeData()
    mimedata.setImageData(QtGui.QImage(imgfilename3x3))
    event = MagicMock()
    event.mimeData.return_value = mimedata

    view.dragEnterEvent(event)
    event.acceptProposedAction.assert_called_once()


def test_drag_enter_when_unsupported(view):
    mimedata = QtCore.QMimeData()
    event = MagicMock()
    event.mimeData.return_value = mimedata

    view.dragEnterEvent(event)
    event.acceptProposedAction.assert_not_called()


def test_drag_move(view):
    event = MagicMock()
    view.dragMoveEvent(event)
    event.acceptProposedAction.assert_called_once()


@patch('beeref.view.BeeGraphicsView.do_insert_images')
def test_drop_when_url(insert_mock, view, imgfilename3x3):
    url = QtCore.QUrl.fromLocalFile(imgfilename3x3)
    mimedata = QtCore.QMimeData()
    mimedata.setUrls([url])
    event = MagicMock()
    event.mimeData.return_value = mimedata
    event.position.return_value = QtCore.QPointF(10.0, 20.0)

    view.dropEvent(event)
    insert_mock.assert_called_once_with([url], QtCore.QPoint(10, 20))


@patch('beeref.view.BeeGraphicsView.open_from_file')
def test_drop_when_url_beefile_and_scene_empty(open_mock, view):
    root = os.path.dirname(__file__)
    filename = os.path.join(root, 'assets', 'test1item.bee')
    url = QtCore.QUrl.fromLocalFile(filename)
    mimedata = QtCore.QMimeData()
    mimedata.setUrls([url])
    event = MagicMock()
    event.mimeData.return_value = mimedata
    event.position.return_value = QtCore.QPointF(10.0, 20.0)

    view.dropEvent(event)
    open_mock.assert_called_once_with(filename)


@patch('beeref.view.BeeGraphicsView.do_insert_images')
@patch('beeref.view.BeeGraphicsView.open_from_file')
def test_drop_when_url_beefile_and_scene_not_empty(
        open_mock, insert_mock, view, item):
    view.scene.addItem(item)
    root = os.path.dirname(__file__)
    filename = os.path.join(root, 'assets', 'test1item.bee')
    url = QtCore.QUrl.fromLocalFile(filename)
    mimedata = QtCore.QMimeData()
    mimedata.setUrls([url])
    event = MagicMock()
    event.mimeData.return_value = mimedata
    event.position.return_value = QtCore.QPointF(10.0, 20.0)

    view.dropEvent(event)
    open_mock.assert_not_called()


def test_drop_when_img(view, imgfilename3x3):
    mimedata = QtCore.QMimeData()
    mimedata.setImageData(QtGui.QImage(imgfilename3x3))
    event = MagicMock()
    event.mimeData.return_value = mimedata
    event.position.return_value = QtCore.QPointF(10.0, 20.0)

    view.dropEvent(event)
    assert len(view.scene.items()) == 1
    assert view.scene.items()[0].isSelected() is True


def test_text_toolbar_never_takes_focus(view):
    """Taking focus would end the edit and hide the bar after one click."""

    assert view.text_toolbar.focusPolicy() == Qt.FocusPolicy.NoFocus
    for button in (view.text_toolbar.bigger, view.text_toolbar.smaller):
        assert button.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_text_toolbar_stays_up_when_clicked_repeatedly(view):
    textitem = BeeTextItem('click me twice')
    view.scene.addItem(textitem)
    textitem.setSelected(True)
    view.on_selection_changed()

    sizes = []
    for _ in range(3):
        view.text_toolbar.bigger.click()
        view.on_selection_changed()
        assert view.text_toolbar.isVisible() is True
        sizes.append(char_format_at(textitem, 3).fontPointSize())

    assert sizes == sorted(sizes)
    assert sizes[0] < sizes[-1]


def test_text_size_actions_have_shortcuts():
    assert actions.actions['text_size_increase'].shortcuts
    assert actions.actions['text_size_decrease'].shortcuts


def clipboard_image_item(view, color):
    img = QtGui.QImage(60, 60, QtGui.QImage.Format.Format_RGB32)
    img.fill(color)
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    return item


def grouped_image(view, color):
    inner = clipboard_image_item(view, color)
    group = BeeGroupItem()
    view.scene.addItem(group)
    inner.setParentItem(group)
    group.fit_to_children()
    return group


def fake_clipboard(clipboard_mock):
    """A clipboard that just remembers what it was handed.

    The real one is not dependable here: on Windows the clipboard
    belongs to a window, and the fixtures create and destroy windows
    between tests, so content set in one test can vanish in the next.
    """

    held = {}
    clipboard_mock.return_value.setMimeData.side_effect = (
        lambda mimedata: held.__setitem__('data', mimedata))
    clipboard_mock.return_value.mimeData.side_effect = (
        lambda: held.get('data', QtCore.QMimeData()))
    clipboard_mock.return_value.image.side_effect = (
        lambda: held.get('data', QtCore.QMimeData()).imageData()
        or QtGui.QImage())
    clipboard_mock.return_value.text.side_effect = (
        lambda: held.get('data', QtCore.QMimeData()).text())
    return held


@patch('PyQt6.QtWidgets.QApplication.clipboard')
def test_copying_a_group_clears_the_previously_copied_image(
        clipboard_mock, view):
    """Otherwise a paste can fall back to an image copied long before."""

    fake_clipboard(clipboard_mock)
    loose = clipboard_image_item(view, QtGui.QColor(0, 200, 0))
    group = grouped_image(view, QtGui.QColor(200, 0, 0))

    loose.setSelected(True)
    view.on_action_copy()
    assert clipboard_mock.return_value.mimeData().hasImage() is True

    loose.setSelected(False)
    group.setSelected(True)
    view.on_action_copy()
    assert clipboard_mock.return_value.mimeData().hasImage() is False


@patch('PyQt6.QtWidgets.QApplication.clipboard')
def test_copy_puts_the_marker_on_the_clipboard(clipboard_mock, view):
    """The marker is what sends paste to the internal clipboard."""

    fake_clipboard(clipboard_mock)
    item = clipboard_image_item(view, QtGui.QColor(0, 0, 200))
    item.setSelected(True)
    view.on_action_copy()
    assert clipboard_mock.return_value.mimeData().data(
        'beeref/items') == b'1'


@patch('PyQt6.QtWidgets.QApplication.clipboard')
def test_pasting_after_copying_a_group_gives_a_group(clipboard_mock, view):
    fake_clipboard(clipboard_mock)
    loose = clipboard_image_item(view, QtGui.QColor(0, 200, 0))
    group = grouped_image(view, QtGui.QColor(200, 0, 0))

    loose.setSelected(True)
    view.on_action_copy()
    loose.setSelected(False)
    group.setSelected(True)
    view.on_action_copy()
    view.on_action_paste()

    groups = [item for item in view.scene.items()
              if getattr(item, 'TYPE', None) == 'group']
    assert len(groups) == 2


@pytest.mark.parametrize('zoom,expected', [(1, 4), (0.25, 16), (4, 1)])
def test_new_drawings_stay_visible_at_any_zoom(view, zoom, expected):
    """A stroke drawn zoomed out must not come out as a hairline."""

    view.scale(zoom / view.get_scale(), zoom / view.get_scale())
    view.set_draw_tool(BeeDrawItem.SKETCH)
    view.start_drawing(QtCore.QPointF(0, 0))

    assert view.drawing_item.line_width == pytest.approx(
        expected, rel=0.01)


def draw_item(view, width=None):
    item = BeeDrawItem(points=[[0, 0], [50, 50]], width=width)
    view.scene.addItem(item)
    return item


def test_size_increase_thickens_a_drawing(view):
    item = draw_item(view)
    item.setSelected(True)
    before = item.line_width

    view.on_action_size_increase()
    assert item.line_width > before
    assert item.line_width == pytest.approx(before * view.LINE_WIDTH_STEP)


def test_size_decrease_thins_a_drawing(view):
    item = draw_item(view)
    item.setSelected(True)
    before = item.line_width

    view.on_action_size_decrease()
    assert item.line_width < before


def test_line_width_can_be_undone(view):
    item = draw_item(view)
    item.setSelected(True)
    before = item.line_width

    view.on_action_size_increase()
    view.undo_stack.undo()
    assert item.line_width == before


def test_line_width_stops_at_the_limits(view):
    item = draw_item(view)
    item.setSelected(True)
    for _ in range(100):
        view.on_action_size_increase()
    assert item.line_width == BeeDrawItem.MAX_WIDTH
    for _ in range(200):
        view.on_action_size_decrease()
    assert item.line_width == BeeDrawItem.MIN_WIDTH


def test_size_change_covers_text_and_drawings_together(view):
    drawing = draw_item(view)
    text = BeeTextItem('words')
    view.scene.addItem(text)
    drawing.setSelected(True)
    text.setSelected(True)
    thickness = drawing.line_width
    size = char_format_at(text, 1).fontPointSize() or float(
        text.font().pointSize())

    view.on_action_size_increase()
    assert drawing.line_width > thickness
    assert char_format_at(text, 1).fontPointSize() > size


def test_drawings_count_as_sizeable(view):
    item = draw_item(view)
    assert view.scene.has_sizeable_selection() is False
    item.setSelected(True)
    assert view.scene.has_sizeable_selection() is True


def test_line_width_survives_a_save(tmpfile, view):
    """Thickness is part of the drawing, so it has to be stored."""

    item = draw_item(view)
    item.setSelected(True)
    view.on_action_size_increase()
    width = item.line_width
    SQLiteIO(tmpfile, view.scene, create_new=True).write()

    for existing in list(view.scene.items_for_save()):
        view.scene.removeItem(existing)
    SQLiteIO(tmpfile, view.scene).read()
    view.scene.add_queued_items()

    loaded = list(view.scene.items_by_type('draw'))
    assert len(loaded) == 1
    assert loaded[0].line_width == pytest.approx(width)


def escape_key(view):
    QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)


def test_escape_puts_the_drawing_tool_away(view):
    item = draw_item(view)
    item.setSelected(True)
    view.set_draw_tool(BeeDrawItem.SKETCH)

    escape_key(view)
    assert view.draw_tool is None
    assert view.scene.has_selection() is False


def test_escape_deselects_without_a_drawing_tool(view):
    item = draw_item(view)
    item.setSelected(True)
    assert view.draw_tool is None

    escape_key(view)
    assert view.scene.has_selection() is False


def test_escape_updates_the_toolbar(view):
    view.set_draw_tool(BeeDrawItem.ARROW)
    assert view.draw_toolbar.buttons[BeeDrawItem.ARROW].isChecked() is True

    escape_key(view)
    assert view.draw_toolbar.buttons[None].isChecked() is True


def test_escape_while_editing_text_is_left_to_the_text(view):
    """Escape there discards the edit; it must not also clear the tool."""

    textitem = BeeTextItem('keep me')
    view.scene.addItem(textitem)
    view.set_draw_tool(BeeDrawItem.LINE)
    textitem.enter_edit_mode()

    view.keyPressEvent(QtGui.QKeyEvent(
        QtCore.QEvent.Type.KeyPress, Qt.Key.Key_Escape,
        Qt.KeyboardModifier.NoModifier))
    assert view.draw_tool == BeeDrawItem.LINE


def test_text_toolbar_has_all_five_buttons(view):
    bar = view.text_toolbar
    buttons = [bar.bold, bar.smaller, bar.bigger, bar.highlight,
               bar.box_color]
    for button in buttons:
        assert button.icon().isNull() is False
        assert button.toolTip()
        assert button.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_text_toolbar_buttons_are_wired_to_the_commands(view):
    textitem = BeeTextItem('format me')
    view.scene.addItem(textitem)
    textitem.setSelected(True)

    view.text_toolbar.bold.click()
    assert char_format_at(textitem, 2).fontWeight() == QtGui.QFont.Weight.Bold

    size = char_format_at(textitem, 2).fontPointSize()
    view.text_toolbar.bigger.click()
    assert char_format_at(textitem, 2).fontPointSize() > size
    view.text_toolbar.smaller.click()
    assert char_format_at(textitem, 2).fontPointSize() == pytest.approx(size)


def test_text_toolbar_box_colour_button_opens_the_picker(view):
    textitem = BeeTextItem('colour me')
    view.scene.addItem(textitem)
    textitem.setSelected(True)

    with color_dialog(QtGui.QColor(1, 2, 3, 255)):
        view.text_toolbar.box_color.click()
    assert textitem.box_color == QtGui.QColor(1, 2, 3, 255)


def test_text_toolbar_highlight_button_opens_the_picker(view):
    textitem = BeeTextItem('colour me')
    view.scene.addItem(textitem)
    textitem.setSelected(True)

    with color_dialog(QtGui.QColor(9, 9, 9, 255)):
        view.text_toolbar.highlight.click()
    assert char_format_at(textitem, 2).background().color() == QtGui.QColor(
        9, 9, 9, 255)


def test_size_buttons_repeat_while_held_but_the_others_do_not(view):
    bar = view.text_toolbar
    assert bar.bigger.autoRepeat() is True
    assert bar.smaller.autoRepeat() is True
    assert bar.bold.autoRepeat() is False
    assert bar.highlight.autoRepeat() is False
    assert bar.box_color.autoRepeat() is False


def dialog_position(view, item_pos):
    """Where the colour picker ends up for an item at the given place."""

    view.resize(900, 700)
    textitem = BeeTextItem('colour me')
    view.scene.addItem(textitem)
    textitem.setPos(*item_pos)
    textitem.setSelected(True)
    seen = {}

    def fake_exec(dialog):
        seen['dialog'] = dialog.geometry()
        seen['size'] = dialog.sizeHint()
        return QtWidgets.QDialog.DialogCode.Rejected.value

    with patch.object(QtWidgets.QColorDialog, 'exec', fake_exec):
        view.on_action_text_box_color()
    return textitem, seen


def test_colour_picker_does_not_sit_on_the_selection(view):
    textitem, seen = dialog_position(view, (0, 0))
    on_view = view.mapFromScene(textitem.sceneBoundingRect()).boundingRect()
    item_rect = QtCore.QRect(
        view.viewport().mapToGlobal(on_view.topLeft()), on_view.size())

    assert seen['dialog'].intersects(item_rect) is False


def test_colour_picker_stays_on_the_screen(view):
    _, seen = dialog_position(view, (0, 0))
    screen = view.screen().availableGeometry()
    assert screen.contains(seen['dialog'].topLeft())
    assert seen['dialog'].left() >= screen.left()
    assert seen['dialog'].left() + seen['size'].width() <= screen.right() + 1


def test_colour_picker_is_left_alone_without_a_selection(view):
    """Nothing to avoid, so Qt's own placement is fine."""

    seen = {}

    def fake_exec(dialog):
        seen['moved'] = dialog.pos()
        return QtWidgets.QDialog.DialogCode.Rejected.value

    with patch.object(QtWidgets.QColorDialog, 'exec', fake_exec):
        view.on_action_group_box_color()
    assert seen == {}


def pinned_bar(view, pos=(0, 0)):
    """A selected text item and the bar that should be stuck to it."""

    view.resize(900, 700)
    textitem = BeeTextItem('follow me')
    view.scene.addItem(textitem)
    textitem.setPos(*pos)
    textitem.setSelected(True)
    view.on_selection_changed()
    return textitem, view.text_toolbar


def item_on_view(view, item):
    return view.mapFromScene(item.sceneBoundingRect()).boundingRect()


def test_text_bar_sits_above_the_text(view):
    textitem, bar = pinned_bar(view, (200, 300))
    rect = item_on_view(view, textitem)

    assert bar.isVisible() is True
    assert bar.geometry().bottom() <= rect.top()
    # and centred on it, give or take rounding
    assert abs(bar.geometry().center().x() - rect.center().x()) <= 2


def test_text_bar_follows_the_text_when_it_moves(view):
    textitem, bar = pinned_bar(view, (0, 300))
    before = bar.pos()

    textitem.setPos(400, 300)
    # Keep the text in the middle of the window, so the bar is placed by
    # where the text is rather than by the edge it would be clamped to
    view.centerOn(textitem.sceneBoundingRect().center())
    view.update_text_toolbar()
    assert bar.pos() != before
    assert abs(bar.geometry().center().x()
               - item_on_view(view, textitem).center().x()) <= 2


def test_text_bar_follows_the_text_when_zooming(view):
    textitem, bar = pinned_bar(view, (0, 300))
    view.centerOn(textitem.sceneBoundingRect().center())
    view.update_text_toolbar()
    before = bar.geometry()

    view.scale(2, 2)
    view.centerOn(textitem.sceneBoundingRect().center())
    view.update_text_toolbar()
    rect = item_on_view(view, textitem)
    # The text is twice the size on screen, so the bar has moved with it
    assert bar.geometry() != before
    assert abs(bar.geometry().center().x() - rect.center().x()) <= 2
    assert bar.geometry().bottom() <= rect.top()


def test_text_bar_hangs_below_when_there_is_no_room_above(view):
    """Text at the very top of the window still gets its buttons."""

    _, bar = pinned_bar(view)
    against_the_top = QtCore.QRect(300, 0, 200, 60)

    bar.pin_to(against_the_top)
    assert bar.geometry().top() >= against_the_top.bottom()
    assert bar.geometry().top() >= 0


def test_text_bar_sits_above_when_there_is_room(view):
    _, bar = pinned_bar(view)
    lower_down = QtCore.QRect(300, 400, 200, 60)

    bar.pin_to(lower_down)
    assert bar.geometry().bottom() <= lower_down.top()


def test_text_bar_stays_inside_the_window(view):
    textitem, bar = pinned_bar(view, (0, 300))
    for pos in ((-5000, 300), (5000, 300), (0, -5000), (0, 5000)):
        textitem.setPos(*pos)
        view.update_text_toolbar()
        assert view.rect().contains(bar.geometry()) is True


def test_text_bar_goes_away_with_the_selection(view):
    textitem, bar = pinned_bar(view)
    assert bar.isVisible() is True

    textitem.setSelected(False)
    view.on_selection_changed()
    assert bar.isVisible() is False


def test_insert_table_starts_a_note_when_nothing_is_being_edited(view):
    """Ctrl+Shift+T on the canvas gives the table a note to live in."""

    view.on_action_insert_table()

    item = view.scene.item_with_table()
    assert item is not None
    assert item.current_table().rows() == item.TABLE_ROWS
    # An empty note, not one holding the placeholder word
    assert item.toPlainText().strip() == ''


def test_insert_table_can_be_undone(view):
    view.on_action_insert_table()
    assert view.scene.item_with_table() is not None

    view.undo_stack.undo()
    assert view.scene.item_with_table() is None

    view.undo_stack.redo()
    assert view.scene.item_with_table() is not None


def table_shape(view):
    """The shape of the table being edited.

    Read and dropped in one go on purpose. Anything that replaces an
    item's html -- every one of these commands, and undo with them --
    destroys the document's frames, so a QTextTable held across one is
    a dangling pointer that crashes Qt whenever it is next collected.
    """

    table = view.scene.item_with_table().current_table()
    return table.rows(), table.columns()


def test_table_row_and_column_commands_are_undoable(view):
    view.on_action_insert_table()
    rows, columns = table_shape(view)

    view.on_action_table_row_insert()
    view.on_action_table_column_insert()
    assert table_shape(view) == (rows + 1, columns + 1)

    view.undo_stack.undo()
    view.undo_stack.undo()
    assert table_shape(view) == (rows, columns)


def test_table_commands_do_nothing_without_a_table(view):
    """The menu entries are greyed out, but nothing may crash regardless."""

    assert view.scene.item_with_table() is None
    view.on_action_table_row_insert()
    view.on_action_table_row_remove()
    view.on_action_table_column_insert()
    view.on_action_table_column_remove()
    view.on_action_table_cell_color()
    assert view.undo_stack.count() == 0


def table_note(view):
    """A note holding a table, no longer being edited."""

    view.on_action_insert_table()
    item = view.scene.item_with_table()
    item.exit_edit_mode()
    item.setPos(0, 0)
    return item


def cell_point(view, item, row, column):
    """The view position of a cell, for right-clicking it."""

    table = item.tables()[0]
    centre = item.document().documentLayout().blockBoundingRect(
        table.cellAt(row, column).firstCursorPosition().block()).center()
    del table
    return view.mapFromScene(item.mapToScene(centre))


def test_a_note_holding_a_table_is_not_empty(view):
    """Clicking away from a fresh table used to delete it.

    An empty note is removed when editing ends, and a table nobody has
    typed into yet has no text at all.
    """

    item = table_note(view)
    assert item.scene() is view.scene
    assert len(item.tables()) == 1


def test_right_click_puts_the_cursor_in_the_cell(view):
    item = table_note(view)
    view.scene.deselect_all_items()

    with patch.object(view.text_context_menu, 'exec'):
        view.on_context_menu(cell_point(view, item, 1, 1))

    cell = item.current_cell()
    assert (cell.row(), cell.column()) == (1, 1)
    # And the commands are reachable, rather than greyed out on a note
    # that plainly holds a table
    assert actions.actions['table_row_insert'].qaction.isEnabled() is True


def test_right_click_then_insert_row(view):
    item = table_note(view)
    with patch.object(view.text_context_menu, 'exec'):
        view.on_context_menu(cell_point(view, item, 0, 0))

    before = table_shape(view)
    view.on_action_table_row_insert()
    assert table_shape(view) == (before[0] + 1, before[1])


def test_text_font_action_switches_and_switches_back(view):
    item = BeeTextItem('hello')
    view.scene.addItem(item)
    item.setSelected(True)
    interface, bundled = item.font_families()

    view.on_action_text_font()
    assert item.uses_bundled_font() is True

    view.on_action_text_font()
    assert item.uses_bundled_font() is False


def test_text_font_action_does_nothing_without_a_selection(view):
    view.scene.deselect_all_items()
    view.on_action_text_font()
    assert view.undo_stack.count() == 0


def test_compact_file_asks_where_to_save_when_untitled(view):
    view.filename = None
    with patch.object(view, 'on_action_save_as') as save_as:
        view.on_action_compact_file()
    save_as.assert_called_once()


def test_compact_file_wants_changes_saved_first(view):
    """Compacting rewrites the file, so it must match what is on screen."""

    view.filename = 'foo.blk'
    view.undo_stack.resetClean()
    with patch('PyQt6.QtWidgets.QMessageBox.information') as message, \
         patch('beeref.fileio.ThreadedIO') as threaded:
        view.on_action_compact_file()
    message.assert_called_once()
    threaded.assert_not_called()


def test_compact_file_runs_in_the_background(view):
    view.filename = 'foo.blk'
    view.undo_stack.setClean()
    with patch('beeref.fileio.ThreadedIO') as threaded, \
         patch('beeref.widgets.BeeProgressDialog'):
        view.on_action_compact_file()
    threaded.assert_called_once()
    assert threaded.call_args.args[0] is fileio.compact_bee


def test_wheel_zoom_is_spread_over_frames(view, imgfilename3x3):
    """A notch of the wheel eases in rather than jumping at once."""

    view.scene.addItem(BeePixmapItem(QtGui.QImage(imgfilename3x3)))
    anchor = QtCore.QPointF(50.0, 50.0)
    before = view.get_scale()

    view.smooth_zoom(120, anchor)
    # Nothing has moved yet; the work is waiting to be done
    assert view.get_scale() == before
    assert view.pending_zoom == 120
    assert view.zoom_timer.isActive() is True

    scales = []
    for _ in range(40):
        view.step_zoom()
        scales.append(view.get_scale())

    assert scales[0] > before, 'the first step has to move'
    assert scales == sorted(scales), 'zooming in never goes backwards'
    # Each step covers less ground than the one before it
    assert scales[1] - scales[0] > scales[5] - scales[4]
    assert view.zoom_timer.isActive() is False
    assert view.pending_zoom == 0


def test_wheel_zoom_adds_up_when_spun_quickly(view, imgfilename3x3):
    view.scene.addItem(BeePixmapItem(QtGui.QImage(imgfilename3x3)))
    anchor = QtCore.QPointF(50.0, 50.0)

    for _ in range(5):
        view.smooth_zoom(120, anchor)

    # Turns add to each other rather than replacing one another
    assert view.pending_zoom == 600


def scrollable_view(view, imgfilename3x3):
    """A view with somewhere to scroll to."""

    for x in (0, 2000, 4000):
        item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
        view.scene.addItem(item)
        item.setPos(x, x)
    view.recalc_scene_rect()
    return view.horizontalScrollBar()


def test_pan_keeps_what_it_could_not_spend(view, imgfilename3x3):
    """Movements smaller than a pixel used to be thrown away.

    A smooth zoom corrects its anchor by a fraction of a pixel each
    frame. Dropping every one of those left the canvas drifting off the
    anchor until a whole pixel had built up and it snapped back, which
    is what made everything tremble.
    """

    hscroll = scrollable_view(view, imgfilename3x3)
    hscroll.setValue((hscroll.minimum() + hscroll.maximum()) // 2)
    start = hscroll.value()

    for _ in range(10):
        view.pan(QtCore.QPointF(0.4, 0.0))

    assert hscroll.value() == start + 4


def test_pan_does_not_drift_on_whole_pixels(view, imgfilename3x3):
    hscroll = scrollable_view(view, imgfilename3x3)
    hscroll.setValue((hscroll.minimum() + hscroll.maximum()) // 2)
    start = hscroll.value()

    for _ in range(10):
        view.pan(QtCore.QPointF(3.0, 0.0))

    assert hscroll.value() == start + 30
    assert view.pan_remainder.x() == 0
