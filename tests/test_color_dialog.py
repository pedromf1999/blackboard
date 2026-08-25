from unittest.mock import patch

from PyQt6 import QtGui, QtWidgets

from beeref.widgets.color_dialog import simplify_color_dialog


def parts(dialog):
    return [child for child in dialog.children()
            if isinstance(child, QtWidgets.QWidget)]


def screen_button(dialog):
    for child in parts(dialog):
        if (isinstance(child, QtWidgets.QPushButton)
                and child.icon().isNull() is False):
            return child
    return None


def make_dialog(qapp):
    dialog = QtWidgets.QColorDialog(QtGui.QColor('#e06666'))
    dialog.setOption(
        QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel)
    return dialog


def test_only_the_swatches_and_the_eyedropper_are_left(qapp):
    """Colours here come from the palette, not from a gradient."""

    dialog = make_dialog(qapp)
    simplify_color_dialog(dialog)

    showing = [child for child in parts(dialog) if not child.isHidden()]
    # The grid, its label, the eyedropper and the OK/Cancel box
    assert len(showing) == 4
    assert any(isinstance(c, QtWidgets.QDialogButtonBox) for c in showing)
    assert screen_button(dialog) in showing

    # Nothing to type a colour into, and no custom slots to fill
    assert [c for c in showing if isinstance(c, QtWidgets.QLineEdit)] == []
    assert [c for c in showing if isinstance(c, QtWidgets.QSpinBox)] == []


def test_the_basic_grid_is_the_one_that_stays(qapp):
    """Two unnamed grids look alike; the labels are what tell them apart."""

    dialog = make_dialog(qapp)
    labels = [c for c in parts(dialog)
              if isinstance(c, QtWidgets.QLabel) and c.buddy()]
    basic, custom = labels[0].buddy(), labels[1].buddy()
    simplify_color_dialog(dialog)

    assert basic.isHidden() is False
    assert custom.isHidden() is True


def test_the_eyedropper_says_it_with_a_picture(qapp):
    dialog = make_dialog(qapp)
    simplify_color_dialog(dialog)

    button = screen_button(dialog)
    assert button is not None
    assert button.text() == ''
    assert button.toolTip() != ''


def test_the_dialog_shrinks_to_what_is_left(qapp):
    dialog = make_dialog(qapp)
    before = dialog.sizeHint()
    simplify_color_dialog(dialog)
    after = dialog.sizeHint()

    assert after.width() < before.width()
    assert after.height() < before.height()


def test_a_dialog_qt_has_renamed_is_left_alone(qapp):
    """Recognising parts by their text must fail safe, not fail loudly."""

    dialog = make_dialog(qapp)
    for child in parts(dialog):
        if isinstance(child, QtWidgets.QPushButton):
            child.setText('unrecognisable')
    simplify_color_dialog(dialog)

    assert screen_button(dialog) is None


def test_the_board_colour_picker_uses_it(view):
    seen = {}

    def remember(dialog):
        seen['parts'] = len([c for c in parts(dialog) if not c.isHidden()])
        dialog.reject()

    with patch('PyQt6.QtWidgets.QColorDialog.exec', return_value=0):
        with patch('beeref.widgets.color_dialog.simplify_color_dialog',
                   side_effect=remember) as simplify:
            view.pick_color_live('Choose', QtGui.QColor('red'), lambda c: None)
    assert simplify.called


def test_the_settings_colour_picker_uses_it_too(qapp):
    """The one place that still went through Qt's own getColor()."""

    from beeref.widgets.settings import CanvasColorWidget

    widget = CanvasColorWidget()
    with patch('beeref.widgets.settings.simplify_color_dialog') as simplify:
        with patch('PyQt6.QtWidgets.QColorDialog.exec', return_value=0):
            widget.on_button_clicked()
    assert simplify.called
