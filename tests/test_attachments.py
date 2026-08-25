import os

from PyQt6 import QtCore

from beeref import commands
from beeref.fileio.sql import SQLiteIO
from beeref.items import BeeDrawItem, BeeGroupItem, BeeTextItem


def draw_to(view, scene_pos, kind=BeeDrawItem.LINE):
    """Draw a line ending at the given point, the way the mouse does."""

    view.set_draw_tool(kind)
    view.start_drawing(QtCore.QPointF(50, 50))
    view.continue_drawing(scene_pos)
    view.finish_drawing()
    return [d for d in view.scene.items_by_type('draw') if d.kind == kind][0]


def a_note(view, pos=(300, 200)):
    note = BeeTextItem('target')
    view.scene.addItem(note)
    note.setPos(*pos)
    return note


def tip(line):
    point = line.mapToScene(line.points[-1])
    return (round(point.x()), round(point.y()))


def on_edge(line, item, index=-1):
    """Whether the line's end sits on the item's edge."""

    rect = item.sceneBoundingRect()
    point = line.mapToScene(line.points[index])
    return (abs(point.x() - rect.left()) < 0.6
            or abs(point.x() - rect.right()) < 0.6
            or abs(point.y() - rect.top()) < 0.6
            or abs(point.y() - rect.bottom()) < 0.6)


def crosses(line, item):
    """Whether the line lies across the item it is joined to."""

    rect = item.sceneBoundingRect()
    start = line.mapToScene(line.points[0])
    end = line.mapToScene(line.points[-1])
    for step in range(1, 100):
        along = step / 100
        point = QtCore.QPointF(
            start.x() + (end.x() - start.x()) * along,
            start.y() + (end.y() - start.y()) * along)
        if rect.contains(point):
            return True
    return False


def test_an_end_dropped_near_a_note_catches_on_it(view):
    note = a_note(view)
    rect = note.sceneBoundingRect()
    line = draw_to(view, QtCore.QPointF(rect.left() - 8, rect.center().y()))

    assert 'end' in line.ends
    assert 'start' not in line.ends, 'the far end was over nothing'
    # Pulled onto the edge rather than left short of it
    assert on_edge(line, note)
    assert crosses(line, note) is False


def test_an_end_dropped_in_open_space_catches_nothing(view):
    a_note(view)
    line = draw_to(view, QtCore.QPointF(800, 600))
    assert line.ends == {}


def test_the_line_follows_the_note(view):
    note = a_note(view)
    rect = note.sceneBoundingRect()
    line = draw_to(view, QtCore.QPointF(rect.left() - 8, rect.center().y()))
    start_before = tip(line)

    note.setPos(note.pos() + QtCore.QPointF(150, 90))

    assert on_edge(line, note)
    assert tip(line) != start_before
    # The other end stays where it was put
    assert round(line.mapToScene(line.points[0]).x()) == 50


def test_the_line_follows_the_note_being_scaled(view):
    note = a_note(view)
    rect = note.sceneBoundingRect()
    line = draw_to(view, QtCore.QPointF(rect.left() - 8, rect.center().y()))

    note.setScale(3)

    assert on_edge(line, note)
    assert crosses(line, note) is False


def test_a_group_can_hold_an_end_too(view):
    items = []
    for n in range(2):
        item = BeeTextItem(f'note {n}')
        view.scene.addItem(item)
        item.setPos(600, 100 + n * 60)
        items.append(item)
    group = BeeGroupItem(box_color=(10, 20, 30, 200))
    commands.GroupItems(view.scene, items, group).redo()
    view.scene.deselect_all_items()

    rect = group.sceneBoundingRect()
    line = draw_to(view, QtCore.QPointF(rect.left() - 6, rect.center().y()))
    assert 'end' in line.ends

    group.setPos(group.pos() + QtCore.QPointF(-120, 40))
    assert on_edge(line, group)
    assert crosses(line, group) is False


def test_losing_the_note_leaves_the_line_where_it_is(view):
    note = a_note(view)
    rect = note.sceneBoundingRect()
    line = draw_to(view, QtCore.QPointF(rect.left() - 8, rect.center().y()))
    before = tip(line)

    view.scene.removeItem(note)
    line.follow_attachments()

    assert line.ends == {}
    assert tip(line) == before


def test_attachments_survive_the_file(view, tmpdir):
    note = a_note(view)
    rect = note.sceneBoundingRect()
    draw_to(view, QtCore.QPointF(rect.left() - 8, rect.center().y()))

    path = os.path.join(tmpdir, 'joined.blk')
    SQLiteIO(path, view.scene, create_new=True).write()
    for item in list(view.scene.items_for_save()):
        if item.parentItem() is None:
            view.scene.removeItem(item)
    SQLiteIO(path, view.scene, readonly=True).read()
    view.scene.add_queued_items()

    line = list(view.scene.items_by_type('draw'))[0]
    loaded_note = list(view.scene.items_by_type('text'))[0]
    assert 'end' in line.ends

    loaded_note.setPos(loaded_note.pos() + QtCore.QPointF(200, 100))
    assert on_edge(line, loaded_note)


def test_a_board_with_nothing_fastened_says_so(view):
    """Every item reports every move; that must cost nothing normally."""

    a_note(view)
    draw_to(view, QtCore.QPointF(800, 600))
    assert view.scene.uses_attachments is False


def test_a_dot_shows_where_an_end_would_catch(view):
    """Drawing towards a note has to say that letting go would fasten."""

    note = a_note(view)
    rect = note.sceneBoundingRect()

    view.set_draw_tool(BeeDrawItem.LINE)
    view.start_drawing(QtCore.QPointF(50, 50))
    assert view.snap_preview is None

    view.continue_drawing(QtCore.QPointF(150, 150))
    assert view.snap_preview is None, 'nothing to catch on out here'

    view.continue_drawing(
        QtCore.QPointF(rect.left() - 8, rect.center().y()))
    assert view.snap_preview is not None
    # On the edge, where the end would end up
    rect = note.sceneBoundingRect()
    assert abs(view.snap_preview.x() - rect.left()) < 0.6


def test_the_dot_goes_away_when_the_line_is_finished(view):
    note = a_note(view)
    rect = note.sceneBoundingRect()

    view.set_draw_tool(BeeDrawItem.LINE)
    view.start_drawing(QtCore.QPointF(50, 50))
    view.continue_drawing(
        QtCore.QPointF(rect.left() - 8, rect.center().y()))
    assert view.snap_preview is not None

    view.finish_drawing()
    assert view.snap_preview is None


def test_the_dot_is_painted(view):
    """Not just remembered: it has to reach the screen."""

    from PyQt6 import QtGui

    note = a_note(view)
    rect = note.sceneBoundingRect()
    view.set_draw_tool(BeeDrawItem.LINE)
    view.start_drawing(QtCore.QPointF(rect.left() - 120, rect.center().y()))

    def painted():
        image = QtGui.QImage(view.viewport().size(),
                             QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor(0, 0, 0))
        painter = QtGui.QPainter(image)
        view.drawForeground(painter, QtCore.QRectF(view.sceneRect()))
        painter.end()
        return any(image.pixelColor(x, y) != QtGui.QColor(0, 0, 0)
                   for x in range(0, image.width(), 3)
                   for y in range(0, image.height(), 3))

    assert painted() is False, 'nothing to show yet'

    view.continue_drawing(
        QtCore.QPointF(rect.left() - 8, rect.center().y()))
    assert painted() is True


def a_line(view, points=((0, 0), (200, 0)), pos=(100, 100)):
    line = BeeDrawItem(points=list(points), kind=BeeDrawItem.LINE)
    view.scene.addItem(line)
    line.setPos(*pos)
    line.setSelected(True)
    return line


def test_the_ends_can_be_taken_hold_of(view):
    line = a_line(view)

    assert line.end_at(QtCore.QPointF(0, 0)) == 'start'
    assert line.end_at(QtCore.QPointF(200, 0)) == 'end'
    assert line.end_at(QtCore.QPointF(100, 0)) is None, 'the middle is not'


def test_an_unselected_line_offers_no_ends(view):
    """Its ends are only there to be grabbed once it is picked out."""

    line = a_line(view)
    line.setSelected(False)
    assert line.end_at(QtCore.QPointF(0, 0)) is None


def test_dragging_an_end_moves_only_that_end(view):
    line = a_line(view)
    start_before = tip_of(line, 0)

    line.move_end_to('end', QtCore.QPointF(400, 250))

    assert tip_of(line, -1) == (400, 250)
    assert tip_of(line, 0) == start_before
    # The line as a whole stays where it is
    assert (round(line.pos().x()), round(line.pos().y())) == (100, 100)


def test_an_end_dragged_onto_a_note_takes_hold_of_it(view):
    line = a_line(view)
    note = a_note(view, pos=(600, 400))
    rect = note.sceneBoundingRect()
    near = QtCore.QPointF(rect.left() - 6, rect.center().y())

    line.move_end_to('end', near)
    view.snap_end(line, 'end', near)

    assert 'end' in line.ends
    assert on_edge(line, note)


def test_hovering_an_end_marks_it(view):
    line = a_line(view)

    line.show_end_marker('end')
    assert view.snap_preview is not None
    assert (round(view.snap_preview.x()),
            round(view.snap_preview.y())) == tip_of(line, -1)

    line.show_end_marker(None)
    assert view.snap_preview is None


def tip_of(line, index):
    point = line.mapToScene(line.points[index])
    return (round(point.x()), round(point.y()))


def test_the_end_travels_round_the_box_as_it_moves(view):
    """A line joined to a note must never lie across it.

    The end slides round to the side the line comes from, instead of
    staying on the side it was first dropped on and being crossed over
    when the note goes past.
    """

    import math

    note = a_note(view, pos=(400, 300))
    rect = note.sceneBoundingRect()
    line = draw_to(view, QtCore.QPointF(rect.left() - 6, rect.center().y()))
    free = line.mapToScene(line.points[0])

    seen = set()
    for angle in range(0, 360, 20):
        radians = math.radians(angle)
        note.setPos(QtCore.QPointF(free.x() + 250 * math.cos(radians) - 15,
                                   free.y() + 250 * math.sin(radians) - 12))
        assert crosses(line, note) is False, f'crossed at {angle} degrees'
        assert on_edge(line, note), f'left the edge at {angle} degrees'
        seen.add(which_side(line, note))

    # It really does go round, rather than clinging to one side
    assert len(seen) >= 3


def which_side(line, item):
    rect = item.sceneBoundingRect()
    point = line.mapToScene(line.points[-1])
    if abs(point.x() - rect.left()) < 0.6:
        return 'left'
    if abs(point.x() - rect.right()) < 0.6:
        return 'right'
    if abs(point.y() - rect.top()) < 0.6:
        return 'top'
    return 'bottom'


def over(line, item):
    """Whether the line passes through the item, ends not counting.

    An end sits exactly on the edge, so the point itself is always
    touching; only what goes through the middle matters.
    """

    inner = item.sceneBoundingRect().adjusted(0.5, 0.5, -0.5, -0.5)
    start = line.mapToScene(line.points[0])
    end = line.mapToScene(line.points[-1])
    return any(inner.contains(QtCore.QPointF(
        start.x() + (end.x() - start.x()) * step / 100,
        start.y() + (end.y() - start.y()) * step / 100))
        for step in range(1, 100))


def joined_notes(view):
    """Two notes with a line held by both of them."""

    one = BeeTextItem('Text 1')
    view.scene.addItem(one)
    one.setPos(300, 100)
    two = BeeTextItem('Text 2')
    view.scene.addItem(two)
    two.setPos(300, 500)
    first, second = one.sceneBoundingRect(), two.sceneBoundingRect()

    view.set_draw_tool(BeeDrawItem.LINE)
    view.start_drawing(
        QtCore.QPointF(first.center().x(), first.bottom() + 5))
    view.continue_drawing(
        QtCore.QPointF(second.center().x(), second.top() - 5))
    view.finish_drawing()
    line = [d for d in view.scene.items_by_type('draw')][0]
    return line, one, two


def test_both_ends_can_hold_a_note(view):
    line, one, two = joined_notes(view)
    assert sorted(line.ends) == ['end', 'start']
    assert on_edge(line, one, index=0)
    assert on_edge(line, two, index=-1)


def test_moving_one_note_past_the_other_moves_both_ends(view):
    """Dragging Text 2 above Text 1 must not draw the line over Text 1.

    Each end used to look at where the line's other end happened to be,
    and that other end was itself about to be worked out -- so whichever
    was done first decided from where the other one used to be, and the
    line was left lying across the words.
    """

    line, one, two = joined_notes(view)
    assert over(line, one) is False

    two.setPos(QtCore.QPointF(300, 30))

    assert over(line, one) is False, 'the line lies across Text 1'
    assert over(line, two) is False
    # The end on Text 1 has gone round to the top, where Text 2 now is
    assert on_edge(line, one, index=0)
    assert on_edge(line, two, index=-1)


def test_the_ends_stay_touching_whichever_way_it_is_moved(view):
    import math

    line, one, two = joined_notes(view)
    centre = one.sceneBoundingRect().center()
    for angle in range(0, 360, 30):
        radians = math.radians(angle)
        two.setPos(QtCore.QPointF(centre.x() + 260 * math.cos(radians),
                                  centre.y() + 260 * math.sin(radians)))
        assert on_edge(line, one, index=0), f'left Text 1 at {angle}'
        assert on_edge(line, two, index=-1), f'left Text 2 at {angle}'
        assert over(line, one) is False, f'crossed Text 1 at {angle}'
        assert over(line, two) is False, f'crossed Text 2 at {angle}'
