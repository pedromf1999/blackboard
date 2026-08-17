from unittest.mock import patch

from PyQt6 import QtCore, QtGui

from beeref.items import BeeDrawItem


def test_toolbar_has_a_button_per_tool(view):
    toolbar = view.draw_toolbar
    for kind, icon, tooltip in toolbar.TOOLS:
        assert kind in toolbar.buttons
        assert not toolbar.buttons[kind].icon().isNull()


def test_starts_on_the_select_tool(view):
    assert view.draw_tool is None
    assert view.draw_toolbar.buttons[None].isChecked() is True


def test_picking_a_tool_checks_its_button(view):
    view.set_draw_tool(BeeDrawItem.LINE)
    assert view.draw_tool == BeeDrawItem.LINE
    assert view.draw_toolbar.buttons[BeeDrawItem.LINE].isChecked() is True
    assert view.draw_toolbar.buttons[None].isChecked() is False

    view.set_draw_tool(None)
    assert view.draw_toolbar.buttons[None].isChecked() is True


def test_drawing_adds_an_item(view):
    view.set_draw_tool(BeeDrawItem.SKETCH)
    view.start_drawing(QtCore.QPointF(0, 0))
    view.continue_drawing(QtCore.QPointF(10, 10))
    view.continue_drawing(QtCore.QPointF(20, 5))
    view.finish_drawing()

    items = list(view.scene.items_by_type('draw'))
    assert len(items) == 1
    assert items[0].kind == BeeDrawItem.SKETCH
    assert len(view.undo_stack) == 1

    view.undo_stack.undo()
    assert list(view.scene.items_by_type('draw')) == []


def test_a_single_click_draws_nothing(view):
    """A click without a drag would leave an invisible dot behind."""

    view.set_draw_tool(BeeDrawItem.SKETCH)
    view.start_drawing(QtCore.QPointF(0, 0))
    view.finish_drawing()
    assert list(view.scene.items_by_type('draw')) == []
    assert len(view.undo_stack) == 0


def test_drawing_uses_the_chosen_colour(view):
    view.draw_color = QtGui.QColor(10, 20, 30)
    view.set_draw_tool(BeeDrawItem.LINE)
    view.start_drawing(QtCore.QPointF(0, 0))
    view.continue_drawing(QtCore.QPointF(50, 0))
    view.finish_drawing()

    item = list(view.scene.items_by_type('draw'))[0]
    assert item.color == QtGui.QColor(10, 20, 30)


@patch('PyQt6.QtWidgets.QColorDialog.getColor',
       return_value=QtGui.QColor(200, 100, 50))
def test_colour_button_sets_the_colour(color_mock, view):
    view.on_action_draw_color()
    assert view.draw_color == QtGui.QColor(200, 100, 50)


@patch('PyQt6.QtWidgets.QColorDialog.getColor',
       return_value=QtGui.QColor(200, 100, 50))
def test_colour_button_recolours_selected_drawings(color_mock, view):
    item = BeeDrawItem(points=[[0, 0], [10, 10]], kind=BeeDrawItem.LINE)
    view.scene.addItem(item)
    item.setSelected(True)

    view.on_action_draw_color()
    assert item.color == QtGui.QColor(200, 100, 50)
    assert len(view.undo_stack) == 1
    view.undo_stack.undo()
    assert item.color != QtGui.QColor(200, 100, 50)


@patch('PyQt6.QtWidgets.QColorDialog.getColor', return_value=QtGui.QColor())
def test_cancelling_the_colour_dialog(color_mock, view):
    before = QtGui.QColor(view.draw_color)
    view.on_action_draw_color()
    assert view.draw_color == before
