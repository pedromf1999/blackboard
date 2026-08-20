from unittest.mock import patch

from PyQt6 import QtCore, QtGui, QtWidgets

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


def color_dialog(color, accept=True):
    """Drive a real colour dialog without showing it.

    setCurrentColor emits currentColorChanged, so the preview runs as it
    would while the user drags around the picker. A plain function, not
    a mock: assigned to the class it binds as a method, so the dialog
    arrives as self.
    """

    def fake_exec(dialog):
        dialog.setCurrentColor(color)
        if accept:
            return QtWidgets.QDialog.DialogCode.Accepted.value
        return QtWidgets.QDialog.DialogCode.Rejected.value

    return patch.object(QtWidgets.QColorDialog, 'exec', fake_exec)


def test_colour_button_sets_the_colour(view):
    with color_dialog(QtGui.QColor(200, 100, 50)):
        view.on_action_draw_color()
    assert view.draw_color == QtGui.QColor(200, 100, 50)


def test_colour_button_recolours_selected_drawings(view):
    item = BeeDrawItem(points=[[0, 0], [10, 10]], kind=BeeDrawItem.LINE)
    view.scene.addItem(item)
    item.setSelected(True)

    with color_dialog(QtGui.QColor(200, 100, 50)):
        view.on_action_draw_color()
    assert item.color == QtGui.QColor(200, 100, 50)
    assert len(view.undo_stack) == 1
    view.undo_stack.undo()
    assert item.color != QtGui.QColor(200, 100, 50)


def test_colour_previews_on_the_selected_drawing(view):
    """The line changes as the colour changes, before OK is pressed."""

    item = BeeDrawItem(points=[[0, 0], [10, 10]], kind=BeeDrawItem.LINE)
    view.scene.addItem(item)
    item.setSelected(True)
    seen = []

    def fake_exec(dialog):
        dialog.setCurrentColor(QtGui.QColor(200, 100, 50))
        seen.append(QtGui.QColor(item.color))
        return QtWidgets.QDialog.DialogCode.Accepted.value

    with patch.object(QtWidgets.QColorDialog, 'exec', fake_exec):
        view.on_action_draw_color()
    assert seen == [QtGui.QColor(200, 100, 50)]


def test_cancelling_the_colour_dialog(view):
    item = BeeDrawItem(points=[[0, 0], [10, 10]], kind=BeeDrawItem.LINE)
    view.scene.addItem(item)
    item.setSelected(True)
    before_default = QtGui.QColor(view.draw_color)
    before_item = QtGui.QColor(item.color)

    with color_dialog(QtGui.QColor(200, 100, 50), accept=False):
        view.on_action_draw_color()
    assert view.draw_color == before_default
    assert item.color == before_item
    assert len(view.undo_stack) == 0


def test_the_corner_bar_has_no_colour_button(view):
    """It moved to the bar that follows the selected drawing."""

    assert hasattr(view.draw_toolbar, 'color_button') is False


def test_drawing_bar_shows_only_with_a_drawing_selected(view):
    item = BeeDrawItem(points=[[0, 0], [10, 10]], kind=BeeDrawItem.LINE)
    view.scene.addItem(item)
    assert view.draw_item_toolbar.isVisible() is False

    item.setSelected(True)
    view.on_selection_changed()
    assert view.draw_item_toolbar.isVisible() is True

    item.setSelected(False)
    view.on_selection_changed()
    assert view.draw_item_toolbar.isVisible() is False


def test_drawing_bar_follows_the_drawing(view):
    view.resize(900, 700)
    item = BeeDrawItem(points=[[0, 0], [80, 40]], kind=BeeDrawItem.LINE)
    view.scene.addItem(item)
    item.setSelected(True)
    # Fix the view once and move the item within it. Re-centring the
    # view on the item would leave it in the same place on screen, which
    # proves nothing about the bar following it.
    view.centerOn(QtCore.QPointF(0, 0))
    view.update_pinned_toolbars()
    before = view.draw_item_toolbar.pos()

    item.setPos(150, 100)
    view.update_pinned_toolbars()
    on_view = view.mapFromScene(item.sceneBoundingRect()).boundingRect()
    assert view.draw_item_toolbar.pos() != before
    assert abs(view.draw_item_toolbar.geometry().center().x()
               - on_view.center().x()) <= 2
