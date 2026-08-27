from PyQt6 import QtCore

from beeref.items import BeeDrawItem, BeeTextItem


def note_at(view, x, y):
    note = BeeTextItem('note')
    view.scene.addItem(note)
    note.setPos(x, y)
    return note


def draw(view, kind, start, end):
    """Draw from one point to another, both on top of something."""

    view.set_draw_tool(kind)
    view.start_drawing(QtCore.QPointF(*start))
    view.continue_drawing(QtCore.QPointF(*end))
    view.finish_drawing()
    return list(view.scene.items_by_type('draw'))[-1]


def test_a_sketch_takes_hold_of_nothing(view):
    """It follows the hand rather than being aimed from one thing to
    another."""

    note_at(view, 0, 0)
    note_at(view, 300, 0)
    item = draw(view, BeeDrawItem.SKETCH, (5, 5), (305, 5))

    assert item.ends == {}
    assert item.fastens() is False


def test_a_line_still_takes_hold(view):
    first = note_at(view, 0, 0)
    second = note_at(view, 300, 0)
    item = draw(view, BeeDrawItem.LINE, (5, 5), (305, 5))

    assert item.fastens() is True
    assert {end['item'] for end in item.ends.values()} == {first, second}


def test_curves_and_arrows_take_hold_too(view):
    for kind in (BeeDrawItem.SPLINE, BeeDrawItem.ARROW,
                 BeeDrawItem.SPLINE_ARROW):
        assert BeeDrawItem(points=[[0, 0], [1, 1]], kind=kind).fastens()


def test_a_shape_takes_hold_of_nothing_either(view):
    for kind in BeeDrawItem.SHAPES:
        assert BeeDrawItem(points=[[0, 0], [1, 1]], kind=kind).fastens() \
            is False


def test_no_dot_is_promised_while_a_sketch_is_drawn(view):
    """Nothing to fasten, so nothing to offer."""

    note_at(view, 0, 0)
    view.set_draw_tool(BeeDrawItem.SKETCH)
    view.start_drawing(QtCore.QPointF(100, 100))
    view.continue_drawing(QtCore.QPointF(5, 5))

    assert view.snap_preview is None
    view.finish_drawing()


def test_a_dot_is_promised_while_a_line_is_drawn(view):
    note_at(view, 0, 0)
    view.set_draw_tool(BeeDrawItem.LINE)
    view.start_drawing(QtCore.QPointF(100, 100))
    view.continue_drawing(QtCore.QPointF(5, 5))

    assert view.snap_preview is not None
    view.finish_drawing()


def test_dragging_a_sketch_end_onto_a_note_does_not_fasten_it(view):
    note = note_at(view, 0, 0)
    item = draw(view, BeeDrawItem.SKETCH, (200, 200), (260, 260))

    view.snap_end(item, 'end', QtCore.QPointF(5, 5))
    assert item.ends == {}
    assert note.scene() is view.scene


def test_dragging_a_line_end_onto_a_note_still_fastens_it(view):
    note = note_at(view, 0, 0)
    item = draw(view, BeeDrawItem.LINE, (200, 200), (260, 260))

    view.snap_end(item, 'end', QtCore.QPointF(5, 5))
    assert item.ends['end']['item'] is note
