from unittest.mock import patch

import pytest
from PyQt6 import QtCore, QtGui

from beeref.items import BeeDrawItem, BeeTextItem


def drag(view, kind, start=(0, 0), through=(80, 10), end=(120, 90)):
    """Draw a shape the way the mouse does: press, move, release."""

    view.set_draw_tool(kind)
    view.start_drawing(QtCore.QPointF(*start))
    for point in (through, end):
        view.continue_drawing(QtCore.QPointF(*point))
    view.finish_drawing()
    return list(view.scene.items_by_type('draw'))[-1]


def test_every_shape_is_on_the_top_bar(view):
    for kind in BeeDrawItem.SHAPES:
        assert kind in view.draw_toolbar.buttons


def test_a_shape_is_drawn_by_dragging_out_a_box(view):
    item = drag(view, BeeDrawItem.CIRCLE)
    assert item.kind == BeeDrawItem.CIRCLE
    assert item.path.isEmpty() is False


def test_a_shape_is_its_two_corners_and_not_the_wander_between(view):
    """Sketches keep every point; a shape only has corners."""

    item = drag(view, BeeDrawItem.SQUARE, start=(0, 0),
                through=(500, 500), end=(100, 60))
    assert len(item.points) == 2
    rect = item.shape_rect()
    assert rect.width() == 100
    assert rect.height() == 60


def test_a_sketch_still_keeps_every_point(view):
    item = drag(view, BeeDrawItem.SKETCH)
    assert len(item.points) > 2


def test_each_shape_has_the_sides_it_says(view):
    corners = {BeeDrawItem.TRIANGLE: 3, BeeDrawItem.SQUARE: 4,
               BeeDrawItem.PENTAGON: 5, BeeDrawItem.HEXAGON: 6}
    for kind, sides in corners.items():
        item = BeeDrawItem(points=[[0, 0], [100, 100]], kind=kind)
        # Each side is one element of the path, plus the closing one
        assert item.path.elementCount() == sides + 1


def test_a_circle_is_round_rather_than_a_polygon(view):
    item = BeeDrawItem(points=[[0, 0], [100, 100]], kind=BeeDrawItem.CIRCLE)
    assert item.path.elementCount() > 8


def test_a_shape_fills_the_box_it_was_dragged_in(view):
    """Held square there would be no way to draw an oval or an oblong."""

    item = BeeDrawItem(points=[[0, 0], [200, 50]],
                       kind=BeeDrawItem.CIRCLE, width=0.5)
    bounds = item.path.boundingRect()
    assert bounds.width() == 200
    assert bounds.height() == 50


def test_a_shape_takes_the_drawing_colour_and_thickness(view):
    view.draw_color = QtGui.QColor('#ff8800')
    item = drag(view, BeeDrawItem.HEXAGON)
    assert item.color == QtGui.QColor('#ff8800')

    before = item.line_width
    item.setSelected(True)
    view.on_action_size_increase()
    assert item.line_width > before


def test_a_shape_can_be_recoloured_like_a_sketch(view):
    item = drag(view, BeeDrawItem.PENTAGON)
    item.setSelected(True)
    with patch.object(view, 'pick_color_live',
                      return_value=QtGui.QColor('#00ff00')):
        view.on_action_draw_color()
    assert item.color == QtGui.QColor('#00ff00')


def test_a_shape_has_corners_rather_than_ends(view):
    """Dragging one about would bend the shape, not move an end of it."""

    item = drag(view, BeeDrawItem.TRIANGLE)
    item.setSelected(True)
    assert item.end_at(item.points[0]) is None
    assert item.arrow_head() is None


def test_a_shape_does_not_fasten_itself_to_anything(view):
    note = BeeTextItem('note')
    view.scene.addItem(note)
    note.setPos(100, 100)

    item = drag(view, BeeDrawItem.SQUARE, start=(100, 100),
                through=(110, 110), end=(180, 160))
    assert item.ends == {}


def test_a_shape_is_saved_and_read_back(view):
    item = drag(view, BeeDrawItem.PENTAGON)
    data = item.get_extra_save_data()
    assert data['kind'] == BeeDrawItem.PENTAGON

    clone = BeeDrawItem.create_from_data(data=data)
    assert clone.kind == BeeDrawItem.PENTAGON
    assert clone.path.isEmpty() is False


def test_an_unknown_kind_falls_back_to_a_sketch(view):
    """A board from a version that knows shapes we do not."""

    item = BeeDrawItem(points=[[0, 0], [1, 1]], kind='dodecahedron')
    assert item.kind == BeeDrawItem.SKETCH


def test_the_search_button_is_on_the_top_bar(view):
    assert view.draw_toolbar.find_text is not None
    assert 'F3' in view.draw_toolbar.find_text.toolTip()

    with patch('PyQt6.QtWidgets.QInputDialog.getText',
               return_value=('', False)) as dialog:
        view.draw_toolbar.find_text.click()
    assert dialog.called


def test_the_dialog_says_how_to_cycle(view):
    with patch('PyQt6.QtWidgets.QInputDialog.getText',
               return_value=('', False)) as dialog:
        view.on_action_find_text()
    label = dialog.call_args[0][2]
    assert 'F3 to cycle through' in label


def test_the_notification_says_it_too(view):
    item = BeeTextItem('the quick brown fox')
    view.scene.addItem(item)
    view.text_search_query = 'brown'
    view.text_search_index = -1

    with patch('beeref.widgets.BeeNotification') as notification:
        view.find_next_text_match()
    assert 'F3 to cycle through' in notification.call_args[0][1]


def test_the_found_word_is_brought_up_to_a_readable_size(view):
    """Centring on the note left the word too small to read."""

    item = BeeTextItem('the quick brown fox jumps over the lazy dog')
    view.scene.addItem(item)
    view.text_search_query = 'brown'
    view.text_search_index = -1
    view.find_next_text_match()

    word = view.word_rect(item, 'brown')
    seen = view.mapToScene(view.viewport().rect()).boundingRect()
    assert word.width() / seen.width() == pytest.approx(
        view.MATCH_SHARE, abs=0.05)


def test_the_word_is_found_where_it_actually_sits(view):
    """Not the whole note: a word late in a long note is far from
    the middle of it."""

    item = BeeTextItem('aaaa bbbb cccc dddd target')
    view.scene.addItem(item)
    word = view.word_rect(item, 'target')

    assert word is not None
    assert item.sceneBoundingRect().contains(word)
    assert word.left() > item.sceneBoundingRect().center().x()


def test_a_word_that_is_not_there_gives_nothing(view):
    item = BeeTextItem('nothing here')
    view.scene.addItem(item)
    assert view.word_rect(item, 'elsewhere') is None


def test_a_match_with_no_measurable_word_still_goes_to_the_note(view):
    """Whatever the layout says, the search must not come up empty."""

    item = BeeTextItem('brown')
    view.scene.addItem(item)
    item.setPos(500, 500)
    view.text_search_query = 'brown'
    view.text_search_index = -1

    with patch.object(view, 'word_rect', return_value=None):
        with patch.object(view, 'centerOn') as centered:
            view.find_next_text_match()
    assert centered.call_args[0][0] == item.sceneBoundingRect().center()
