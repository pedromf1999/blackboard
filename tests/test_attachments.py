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


def left_middle(item):
    rect = item.sceneBoundingRect()
    return (round(rect.left()), round(rect.center().y()))


def test_an_end_dropped_near_a_note_catches_on_it(view):
    note = a_note(view)
    rect = note.sceneBoundingRect()
    line = draw_to(view, QtCore.QPointF(rect.left() - 8, rect.center().y()))

    assert 'end' in line.ends
    assert 'start' not in line.ends, 'the far end was over nothing'
    # Pulled onto the edge rather than left short of it
    assert tip(line) == left_middle(note)


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

    assert tip(line) == left_middle(note)
    assert tip(line) != start_before
    # The other end stays where it was put
    assert round(line.mapToScene(line.points[0]).x()) == 50


def test_the_line_follows_the_note_being_scaled(view):
    note = a_note(view)
    rect = note.sceneBoundingRect()
    line = draw_to(view, QtCore.QPointF(rect.left() - 8, rect.center().y()))

    note.setScale(3)

    assert tip(line) == left_middle(note)


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
    assert tip(line) == left_middle(group)


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
    assert tip(line) == left_middle(loaded_note)


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
    assert (round(view.snap_preview.x()),
            round(view.snap_preview.y())) == left_middle(note)


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
