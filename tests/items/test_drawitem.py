import pytest

from PyQt6 import QtCore, QtGui

from beeref.items import BeeDrawItem, item_registry


ARC = [[0, 0], [20, -20], [40, -25], [60, -20], [80, 0]]


def test_in_items_registry():
    assert item_registry['draw'] == BeeDrawItem


def test_init_defaults(qapp):
    item = BeeDrawItem()
    assert item.save_id is None
    assert item.is_image is False
    assert item.kind == BeeDrawItem.SKETCH
    assert item.color == QtGui.QColor(*BeeDrawItem.DEFAULT_COLOR)
    assert item.line_width == BeeDrawItem.DEFAULT_WIDTH


def test_unknown_kind_falls_back_to_sketch(qapp):
    assert BeeDrawItem(kind='squiggle').kind == BeeDrawItem.SKETCH


@pytest.mark.parametrize('kind', BeeDrawItem.KINDS)
def test_every_kind_draws_something(qapp, kind):
    item = BeeDrawItem(points=ARC, kind=kind)
    assert item.path.elementCount() > 1
    assert item.bounding_rect_unselected().isValid()


def test_sketch_follows_every_point(qapp):
    item = BeeDrawItem(points=ARC, kind=BeeDrawItem.SKETCH)
    # A line to each point after the first
    assert item.path.elementCount() == len(ARC)


def test_line_is_straight(qapp):
    item = BeeDrawItem(points=ARC, kind=BeeDrawItem.LINE)
    # Just a start and an end, whatever the hand did in between
    assert item.path.elementCount() == 2


def test_curve_bends_towards_the_drawn_path(qapp):
    straight = BeeDrawItem(points=ARC, kind=BeeDrawItem.LINE)
    curved = BeeDrawItem(points=ARC, kind=BeeDrawItem.SPLINE)
    # The curve reaches further up than the straight line
    assert (curved.path.boundingRect().top()
            < straight.path.boundingRect().top())


@pytest.mark.parametrize(
    'kind', [BeeDrawItem.ARROW, BeeDrawItem.SPLINE_ARROW])
def test_arrows_have_a_head(qapp, kind):
    item = BeeDrawItem(points=ARC, kind=kind)
    head = item.arrow_head()
    assert head is not None
    assert head.count() == 3


@pytest.mark.parametrize(
    'kind', [BeeDrawItem.SKETCH, BeeDrawItem.LINE, BeeDrawItem.SPLINE])
def test_other_kinds_have_no_head(qapp, kind):
    assert BeeDrawItem(points=ARC, kind=kind).arrow_head() is None


def test_no_head_without_enough_points(qapp):
    item = BeeDrawItem(points=[[0, 0]], kind=BeeDrawItem.ARROW)
    assert item.arrow_head() is None


def test_names_say_what_it_is(qapp):
    assert BeeDrawItem(kind=BeeDrawItem.SKETCH).get_display_name() == 'Sketch'
    assert BeeDrawItem(
        kind=BeeDrawItem.SPLINE_ARROW).get_display_name() == 'Curved Arrow'


def test_save_data(qapp):
    item = BeeDrawItem(points=ARC, kind=BeeDrawItem.ARROW,
                       color=(1, 2, 3, 255), width=7)
    data = item.get_extra_save_data()
    assert data['kind'] == BeeDrawItem.ARROW
    assert data['color'] == (1, 2, 3, 255)
    assert data['width'] == 7
    assert data['points'] == ARC


def test_create_from_data(qapp):
    item = BeeDrawItem.create_from_data(data={
        'kind': BeeDrawItem.SPLINE,
        'color': (1, 2, 3, 255),
        'width': 7,
        'points': ARC})
    assert item.kind == BeeDrawItem.SPLINE
    assert item.color == QtGui.QColor(1, 2, 3, 255)
    assert item.line_width == 7
    assert len(item.points) == len(ARC)


def test_create_copy(qapp):
    item = BeeDrawItem(points=ARC, kind=BeeDrawItem.SPLINE_ARROW,
                       color=(1, 2, 3, 255), width=7)
    item.setPos(30, 40)
    item.setScale(2)

    copy = item.create_copy()
    assert copy.kind == item.kind
    assert copy.color == item.color
    assert copy.line_width == item.line_width
    assert copy.pos() == QtCore.QPointF(30, 40)
    assert copy.scale() == 2
    assert copy.save_id is None


def test_only_the_line_is_clickable(view):
    """A long diagonal stroke must not block what is behind it."""

    item = BeeDrawItem(points=[[0, 0], [200, 200]], kind=BeeDrawItem.LINE)
    view.scene.addItem(item)
    item.setSelected(False)

    shape = item.shape()
    assert shape.contains(QtCore.QPointF(100, 100)) is True
    # The far corner of the bounding box is not on the line
    assert shape.contains(QtCore.QPointF(190, 10)) is False
