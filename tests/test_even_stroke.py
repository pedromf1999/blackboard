from PyQt6 import QtGui

from beeref.items import BeeDrawItem, BeeGroupItem, BeePixmapItem

SIZE = 500


def render(item, paint):
    canvas = QtGui.QImage(SIZE, SIZE, QtGui.QImage.Format.Format_ARGB32)
    canvas.fill(QtGui.QColor(0, 0, 0, 0))
    painter = QtGui.QPainter(canvas)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.translate(SIZE / 2, SIZE / 2)
    painter.setWorldTransform(item.transform(), True)
    paint(painter)
    painter.end()
    return canvas


def first_run(canvas, horizontal, at):
    """How thick the first stretch of ink is along one scan line."""

    count = 0
    for v in range(SIZE):
        x, y = (v, at) if horizontal else (at, v)
        if canvas.pixelColor(x, y).alpha() > 80:
            count += 1
        elif count:
            break
    return count


def stroke_widths(item, offset=0):
    """The line's thickness across and down.

    Measured away from any corner: where two edges meet, the ink of one
    runs into the ink of the other and the pile-up is not the line.
    """

    canvas = render(item, lambda p: item.paint(p, None, None))
    at = SIZE // 2 + offset
    return first_run(canvas, True, at), first_run(canvas, False, at)


def shape(kind, width=8):
    return BeeDrawItem(points=[[-60, -60], [60, 60]], kind=kind, width=width)


def test_a_circle_keeps_its_line_when_pulled_wide(view):
    """Three times wider used to mean three times thicker down the sides."""

    item = shape(BeeDrawItem.CIRCLE)
    assert stroke_widths(item) == (8, 8)

    item.set_stretch(3.0, 1.0)
    assert stroke_widths(item) == (8, 8)


def test_a_circle_keeps_its_line_when_pulled_tall(view):
    item = shape(BeeDrawItem.CIRCLE)
    item.set_stretch(1.0, 4.0)
    assert stroke_widths(item) == (8, 8)


def test_both_axes_at_once_are_no_different(view):
    item = shape(BeeDrawItem.CIRCLE)
    item.set_stretch(3.0, 2.0)
    assert stroke_widths(item) == (8, 8)


def test_a_square_keeps_its_line(view):
    item = shape(BeeDrawItem.SQUARE)
    item.set_stretch(3.0, 1.0)
    assert stroke_widths(item) == (8, 8)


def test_a_polygon_keeps_its_line_along_a_side(view):
    """Measured off the middle, to miss the vertex at the top."""

    item = shape(BeeDrawItem.HEXAGON)
    item.set_stretch(1.0, 4.0)
    across, _ = stroke_widths(item)
    assert across == 8


def test_a_line_keeps_its_thickness(view):
    item = BeeDrawItem(points=[[-60, 0], [60, 0]], kind=BeeDrawItem.LINE,
                       width=8)
    assert stroke_widths(item)[1] == 8
    item.set_stretch(1.0, 3.0)
    assert stroke_widths(item)[1] == 8


def test_a_stretched_shape_is_still_stretched(view):
    """The shape distorts; only the line is spared."""

    item = shape(BeeDrawItem.CIRCLE)
    plain = render(item, lambda p: item.paint(p, None, None))
    item.set_stretch(3.0, 1.0)
    wide = render(item, lambda p: item.paint(p, None, None))

    def reach(canvas, horizontal):
        found = [v for v in range(SIZE)
                 if canvas.pixelColor(*((v, SIZE // 2) if horizontal
                                        else (SIZE // 2, v))).alpha() > 80]
        return max(found) - min(found)

    assert reach(wide, True) > reach(plain, True) * 2.5
    assert reach(wide, False) == reach(plain, False)


def test_an_arrow_head_keeps_its_shape(view):
    item = BeeDrawItem(points=[[-60, 0], [60, 0]], kind=BeeDrawItem.ARROW,
                       width=8)
    plain = item.arrow_head().boundingRect()
    item.set_stretch(4.0, 1.0)
    # Built against the stretched line, so it sits on the line as drawn
    # while keeping its own proportions
    stretched = item.arrow_head(
        QtGui.QTransform.fromScale(4.0, 1.0).map(item.path)).boundingRect()
    assert stretched.height() == plain.height()


def test_an_image_contour_keeps_its_thickness(view):
    img = QtGui.QImage(120, 120, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor(0, 0, 0, 0))
    item = BeePixmapItem(img)
    item.setPos(-60, -60)
    item.set_outline_width(8)
    item.outline_color = QtGui.QColor('white')

    def widths():
        canvas = render(item, lambda p: (p.translate(-60, -60),
                                         item.paint_outline(p)))
        at = SIZE // 2
        return first_run(canvas, True, at), first_run(canvas, False, at)

    assert widths() == (8, 8)
    item.set_stretch(3.0, 1.0)
    assert widths() == (8, 8)


def test_an_unstretched_item_is_painted_as_before(view):
    """Nothing to correct means the painter is left alone."""

    item = shape(BeeDrawItem.CIRCLE)
    assert item.even_stroke(QtGui.QPainter()) is None


def test_a_group_has_no_edges_to_stretch_by(view):
    """Which is why its box needs no correcting."""

    assert BeeGroupItem().get_edge_bounds() == []
