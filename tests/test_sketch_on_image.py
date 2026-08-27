import os

from PyQt6 import QtCore, QtGui

from beeref import fileio
from beeref.items import BeeDrawItem, BeeGroupItem, BeePixmapItem


def picture(view, x=100, y=100, width=200, height=150):
    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor(70, 120, 190))
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    item.setPos(x, y)
    return item


def sketch(view, points, kind=BeeDrawItem.SKETCH):
    view.set_draw_tool(kind)
    view.start_drawing(QtCore.QPointF(*points[0]))
    for point in points[1:]:
        view.continue_drawing(QtCore.QPointF(*point))
    view.finish_drawing()
    return list(view.scene.items_by_type('draw'))[-1]


def test_a_sketch_drawn_on_a_picture_belongs_to_it(view):
    pic = picture(view)
    drawn = sketch(view, [(140, 140), (180, 170), (200, 180)])

    assert drawn.parentItem() is pic


def test_it_keeps_where_it_was_drawn(view):
    picture(view)
    drawn = sketch(view, [(140, 140), (180, 170)])

    assert drawn.scenePos() == QtCore.QPointF(140, 140)


def test_the_picture_carries_it(view):
    pic = picture(view)
    drawn = sketch(view, [(140, 140), (180, 170)])

    pic.setPos(500, 300)
    assert drawn.scenePos() == QtCore.QPointF(540, 340)


def test_the_picture_scales_it_too(view):
    """What is drawn on a picture is part of it, not laid beside it."""

    pic = picture(view)
    drawn = sketch(view, [(140, 140), (180, 170)])
    pic.setScale(2)

    assert drawn.sceneTransform().m11() == 2


def test_a_sketch_drawn_elsewhere_belongs_to_nobody(view):
    picture(view)
    drawn = sketch(view, [(600, 600), (640, 630)])

    assert drawn.parentItem() is None


def test_only_sketches_are_taken_in(view):
    """A line is aimed from one thing to another and fastens its ends
    instead; a shape is a shape wherever it is put."""

    picture(view)
    for kind in (BeeDrawItem.LINE, BeeDrawItem.SPLINE, BeeDrawItem.ARROW,
                 BeeDrawItem.CIRCLE, BeeDrawItem.SQUARE):
        drawn = sketch(view, [(140, 140), (180, 170)], kind)
        assert drawn.parentItem() is None


def test_the_topmost_picture_takes_it(view):
    under = picture(view, 100, 100)
    over = picture(view, 110, 110)
    drawn = sketch(view, [(150, 150), (180, 170)])

    assert drawn.parentItem() is over
    assert under.scene() is view.scene


def test_drawing_it_is_one_step_to_undo(view):
    """Adding it and giving it to the picture is one act."""

    picture(view)
    depth = view.undo_stack.index()
    drawn = sketch(view, [(140, 140), (180, 170)])
    assert view.undo_stack.index() == depth + 1

    view.undo_stack.undo()
    assert drawn.scene() is None


def test_undoing_and_redoing_puts_it_back_on_the_picture(view):
    pic = picture(view)
    drawn = sketch(view, [(140, 140), (180, 170)])

    view.undo_stack.undo()
    view.undo_stack.redo()
    assert drawn.parentItem() is pic
    assert drawn.scenePos() == QtCore.QPointF(140, 140)


def test_it_is_saved_with_the_picture_it_belongs_to(view, tmpdir):
    picture(view)
    sketch(view, [(140, 140), (180, 170)])

    path = os.path.join(tmpdir, 'sketch.blk')
    fileio.save_bee(path, view.scene, create_new=True)
    view.scene.clear()
    fileio.load_bee(path, view.scene)
    view.scene.add_queued_items()

    pictures = list(view.scene.items_by_type('pixmap'))
    drawings = list(view.scene.items_by_type('draw'))
    assert len(pictures) == 1 and len(drawings) == 1
    assert drawings[0].parentItem() is pictures[0]


def test_the_sketch_comes_back_where_it_was_drawn(view, tmpdir):
    picture(view)
    sketch(view, [(140, 140), (180, 170)])

    path = os.path.join(tmpdir, 'sketch.blk')
    fileio.save_bee(path, view.scene, create_new=True)
    view.scene.clear()
    fileio.load_bee(path, view.scene)
    view.scene.add_queued_items()

    drawn = list(view.scene.items_by_type('draw'))[0]
    assert drawn.scenePos() == QtCore.QPointF(140, 140)


def test_grouping_still_works_the_way_it_did(view, tmpdir):
    """Groups hold their items by the same key, so they must not have
    been disturbed by pictures learning to."""

    pic = picture(view)
    pic.setSelected(True)
    view.on_action_group_items()

    path = os.path.join(tmpdir, 'grouped.blk')
    fileio.save_bee(path, view.scene, create_new=True)
    view.scene.clear()
    fileio.load_bee(path, view.scene)
    view.scene.add_queued_items()

    groups = list(view.scene.items_by_type('group'))
    pictures = list(view.scene.items_by_type('pixmap'))
    assert len(groups) == 1
    assert pictures[0].parentItem() is groups[0]


def test_a_sketch_on_a_picture_inside_a_group_knows_both(view):
    pic = picture(view)
    pic.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]
    drawn = sketch(view, [(140, 140), (180, 170)])

    assert drawn.parentItem() is pic
    assert view.scene.get_group_ancestor(drawn) is group
    assert isinstance(group, BeeGroupItem)
