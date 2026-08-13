from unittest.mock import patch

from PyQt6 import QtGui, QtWidgets

from beeref.widgets.settings import (
    ArrangeGapWidget,
    CanvasColorWidget,
    ConfirmCloseUnsavedWidget,
    ImageStorageFormatWidget,
    SettingsDialog,
)


def test_image_storage_format_sets_title_when_not_edited(settings, view):
    widget = ImageStorageFormatWidget()
    assert widget.title() == 'Image Storage Format:'


def test_image_storage_format_sets_title_when_edited(settings, view):
    settings.setValue('Items/image_storage_format', 'jpg')
    widget = ImageStorageFormatWidget()
    assert widget.title() == 'Image Storage Format: ✎'


def test_image_storage_format_selects_radiobox(settings, view):
    settings.setValue('Items/image_storage_format', 'jpg')
    widget = ImageStorageFormatWidget()
    assert widget.buttons['best'].isChecked() is False
    assert widget.buttons['png'].isChecked() is False
    assert widget.buttons['jpg'].isChecked() is True


def test_image_storage_format_saves_change(settings, view):
    settings.setValue('Items/image_storage_format', 'best')
    widget = ImageStorageFormatWidget()
    widget.set_value('jpg')
    assert widget.buttons['best'].isChecked() is False
    assert widget.buttons['png'].isChecked() is False
    assert widget.buttons['jpg'].isChecked() is True
    assert settings.valueOrDefault('Items/image_storage_format') == 'jpg'
    assert widget.title() == 'Image Storage Format: ✎'


def test_image_storage_format_on_restore_defaults(settings, view):
    widget = ImageStorageFormatWidget()
    widget.set_value('jpg')
    settings.setValue('Items/image_storage_format', 'best')
    widget.on_restore_defaults()
    assert widget.buttons['best'].isChecked() is True
    assert widget.buttons['png'].isChecked() is False
    assert widget.buttons['jpg'].isChecked() is False
    assert widget.title() == 'Image Storage Format:'


def test_arrange_gap_initialises_input_from_settings(settings, view):
    settings.setValue('Items/arrange_gap', 6)
    widget = ArrangeGapWidget()
    assert widget.input.value() == 6


def test_arrange_gap_sets_title_when_not_edited(settings, view):
    widget = ArrangeGapWidget()
    assert widget.title() == 'Arrange Gap:'


def test_arrange_gap_sets_title_when_edited(settings, view):
    settings.setValue('Items/arrange_gap', 6)
    widget = ArrangeGapWidget()
    assert widget.title() == 'Arrange Gap: ✎'


def test_arrange_gap_saves_change(settings, view):
    settings.setValue('Items/arrange_gap', 6)
    widget = ArrangeGapWidget()
    widget.set_value(8)
    assert settings.valueOrDefault('Items/arrange_gap') == 8
    assert widget.title() == 'Arrange Gap: ✎'


def test_arrange_gap_on_restore_defaults(settings, view):
    widget = ArrangeGapWidget()
    widget.set_value(7)
    settings.setValue('Items/arrange_gap', 0)
    widget.on_restore_defaults()
    assert widget.input.value() == 0
    assert widget.title() == 'Arrange Gap:'


def test_confirm_closed_initialises_input_from_settings(settings, view):
    settings.setValue('Save/confirm_close_unsaved', False)
    widget = ConfirmCloseUnsavedWidget()
    assert widget.input.isChecked() is False


def test_confirm_closed_sets_title_when_not_edited(settings, view):
    widget = ConfirmCloseUnsavedWidget()
    assert widget.title() == 'Confirm when closing an unsaved file:'


def test_confirm_closed_sets_title_when_edited(settings, view):
    settings.setValue('Save/confirm_close_unsaved', False)
    widget = ConfirmCloseUnsavedWidget()
    assert widget.title() == 'Confirm when closing an unsaved file: ✎'


def test_confirm_closed_saves_change(settings, view):
    settings.setValue('Save/confirm_close_unsaved', True)
    widget = ConfirmCloseUnsavedWidget()
    widget.set_value(False)
    assert settings.valueOrDefault('Save/confirm_close_unsaved') is False
    assert widget.title() == 'Confirm when closing an unsaved file: ✎'


def test_confirm_closed_on_restore_defaults(settings, view):
    widget = ConfirmCloseUnsavedWidget()
    widget.set_value(False)
    settings.setValue('Save/confirm_close_unsaved', True)
    widget.on_restore_defaults()
    assert widget.input.isChecked() is True
    assert widget.title() == 'Confirm when closing an unsaved file:'


def test_canvas_color_initialises_input_from_settings(settings, view):
    settings.setValue('View/canvas_color', '#ff0000')
    widget = CanvasColorWidget()
    assert widget.value == '#ff0000'
    assert widget.button.text() == '#ff0000'


def test_canvas_color_sets_title_when_not_edited(settings, view):
    widget = CanvasColorWidget()
    assert widget.title() == 'Canvas Colour:'


def test_canvas_color_sets_title_when_edited(settings, view):
    settings.setValue('View/canvas_color', '#ff0000')
    widget = CanvasColorWidget()
    assert widget.title() == 'Canvas Colour: ✎'


@patch('PyQt6.QtWidgets.QColorDialog.getColor',
       return_value=QtGui.QColor('#ff0000'))
def test_canvas_color_saves_change(color_mock, settings, view):
    widget = CanvasColorWidget()
    widget.on_button_clicked()
    assert settings.valueOrDefault('View/canvas_color') == '#ff0000'
    assert widget.title() == 'Canvas Colour: ✎'


@patch('PyQt6.QtWidgets.QColorDialog.getColor',
       return_value=QtGui.QColor())
def test_canvas_color_ignores_cancelled_dialog(color_mock, settings, view):
    widget = CanvasColorWidget()
    widget.on_button_clicked()
    assert settings.value_changed('View/canvas_color') is False


def test_canvas_color_on_restore_defaults(settings, view):
    widget = CanvasColorWidget()
    widget.set_value('#ff0000')
    settings.remove('View/canvas_color')
    widget.on_restore_defaults()
    assert widget.button.text() == '#272727'
    assert widget.title() == 'Canvas Colour:'


@patch('PyQt6.QtWidgets.QMessageBox.question',
       return_value=QtWidgets.QMessageBox.StandardButton.Yes)
def test_settings_dialog_on_restore_defaults(msg_mock, settings, view):
    dialog = SettingsDialog(view)
    settings.setValue('Items/image_storage_format', 'jpg')
    settings.setValue('Items/arrange_gap', 10)
    settings.setValue('Save/confirm_close_unsaved', False)
    dialog.on_restore_defaults()
    msg_mock.assert_called_once()
    assert settings.valueOrDefault('Items/image_storage_format') == 'best'
    assert settings.valueOrDefault('Items/arrange_gap') == 0
    assert settings.valueOrDefault('Save/confirm_close_unsaved') is True
