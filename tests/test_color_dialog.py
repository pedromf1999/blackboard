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
    # The grid, the eyedropper and the OK/Cancel box, and no headings
    assert len(showing) == 3
    assert [c for c in showing if isinstance(c, QtWidgets.QLabel)] == []
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

    def remember(dialog, legend=None):
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


LEGEND = [{'color': (33, 118, 255, 255), 'text': 'Approved'},
          {'color': (0, 207, 45, 255), 'text': 'In progress'}]


def legend_widget(dialog):
    from beeref.widgets.color_dialog import LegendColors
    found = dialog.findChildren(LegendColors)
    return found[0] if found else None


def swatches(widget):
    return widget.findChildren(QtWidgets.QToolButton)


def labels(widget):
    return [label.text() for label in widget.findChildren(QtWidgets.QLabel)]


def test_the_legend_is_offered_with_its_own_words(qapp):
    """A colour that already means something is picked by its meaning."""

    dialog = make_dialog(qapp)
    simplify_color_dialog(dialog, LEGEND)

    widget = legend_widget(dialog)
    assert widget is not None
    assert 'Approved' in labels(widget)
    assert 'In progress' in labels(widget)


def test_picking_one_sets_the_colour(qapp):
    dialog = make_dialog(qapp)
    simplify_color_dialog(dialog, LEGEND)

    swatches(legend_widget(dialog))[0].click()
    assert dialog.currentColor() == QtGui.QColor(33, 118, 255)


def test_a_line_with_no_words_goes_by_its_colour(qapp):
    """Still worth offering; it just has nothing to be called."""

    dialog = make_dialog(qapp)
    simplify_color_dialog(dialog, [{'color': (239, 0, 0, 255), 'text': ''}])

    assert '#ef0000' in labels(legend_widget(dialog))


def test_a_board_with_no_legend_gets_no_extra_space(qapp):
    dialog = make_dialog(qapp)
    plain = dialog.sizeHint()
    simplify_color_dialog(dialog, [])

    assert legend_widget(dialog) is None
    assert dialog.sizeHint().height() <= plain.height()


def test_the_legend_is_only_there_to_pick_from(qapp):
    """It is edited in its own panel, where the words are."""

    dialog = make_dialog(qapp)
    simplify_color_dialog(dialog, LEGEND)
    widget = legend_widget(dialog)

    assert widget.findChildren(QtWidgets.QLineEdit) == []
    for button in swatches(widget):
        assert button.isCheckable() is False


def test_it_sits_where_the_custom_slots_used_to(qapp):
    """Under the swatches, which is where a second set belongs."""

    dialog = make_dialog(qapp)
    labelled = [c for c in parts(dialog)
                if isinstance(c, QtWidgets.QLabel) and c.buddy()]
    grid = labelled[0].buddy()
    simplify_color_dialog(dialog, LEGEND)

    from beeref.widgets.color_dialog import layout_holding
    column, index = layout_holding(dialog.layout(), grid)
    assert column.itemAt(index + 1).widget() is legend_widget(dialog)


def test_the_board_picker_hands_the_legend_over(view):
    from unittest.mock import ANY
    view.scene.set_legend(LEGEND)

    with patch('beeref.widgets.color_dialog.simplify_color_dialog') as call:
        with patch('PyQt6.QtWidgets.QColorDialog.exec', return_value=0):
            view.pick_color_live('Choose', QtGui.QColor('red'),
                                 lambda c: None)
    call.assert_called_once_with(ANY, LEGEND)
