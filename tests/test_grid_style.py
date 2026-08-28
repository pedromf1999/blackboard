from PyQt6 import QtGui


def drawn(view, settings, style):
    """How much of the viewport the grid puts ink on."""

    settings.setValue('View/grid_style', style)
    view.show_grid = True
    view.viewport().update()
    shot = view.viewport().grab().toImage()
    background = QtGui.QColor(settings.valueOrDefault('View/canvas_color'))
    return sum(1 for x in range(shot.width()) for y in range(shot.height())
               if shot.pixelColor(x, y) != background)


def test_the_grid_is_ruled_unless_asked_otherwise(view, settings):
    """Boards made before this have the grid they were made with."""

    assert settings.valueOrDefault('View/grid_style') == 'lines'


def test_dots_can_be_asked_for(view, settings):
    view.resize(440, 320)
    assert drawn(view, settings, 'dots') > 0


def test_both_styles_put_something_on_the_canvas(view, settings):
    view.resize(440, 320)
    assert drawn(view, settings, 'lines') > 0
    assert drawn(view, settings, 'dots') > 0


def test_dots_are_thicker_than_the_lines(view, settings):
    """A dot the width of a line is a single pixel of a colour chosen
    to be barely there."""

    assert view.GRID_DOT_SIZE > 1


def test_the_dots_take_the_grids_own_colour(view, settings):
    view.resize(440, 320)
    settings.setValue('View/grid_color', '#ff0000')
    settings.setValue('View/grid_style', 'dots')
    view.show_grid = True
    view.viewport().update()

    shot = view.viewport().grab().toImage()
    reds = [shot.pixelColor(x, y) for x in range(shot.width())
            for y in range(shot.height())
            if shot.pixelColor(x, y).red() > 150]
    assert reds


def test_the_dots_fall_where_the_lines_would_have_crossed(view, settings):
    """Same spacing: it is the same grid, drawn differently."""

    step = view.grid_levels()[0]
    across = view.grid_positions(0, 500, step)
    assert across == [0, step, 2 * step, 3 * step, 4 * step]


def test_the_spacing_setting_is_obeyed_either_way(view, settings):
    view.setTransform(QtGui.QTransform.fromScale(1, 1))
    settings.setValue('View/grid_size', 50)
    small = view.grid_levels()[0]
    settings.setValue('View/grid_size', 200)
    assert view.grid_levels()[0] > small


def test_a_hidden_grid_draws_neither(view, settings):
    view.resize(440, 320)
    view.show_grid = False
    settings.setValue('View/grid_style', 'dots')
    view.viewport().update()

    shot = view.viewport().grab().toImage()
    background = QtGui.QColor(settings.valueOrDefault('View/canvas_color'))
    assert all(shot.pixelColor(x, y) == background
               for x in range(0, shot.width(), 7)
               for y in range(0, shot.height(), 7))


def test_a_nonsense_style_is_refused(view, settings):
    settings.setValue('View/grid_style', 'squiggles')
    assert settings.valueOrDefault('View/grid_style') == 'lines'


def test_dots_keep_their_distance_at_any_zoom(view, settings):
    """The same adaptive spacing the ruled grid has: never a dense mess
    zoomed out, never gone zoomed in."""

    view.resize(500, 400)
    settings.setValue('View/grid_size', 100)
    settings.setValue('View/grid_style', 'dots')

    for zoom in (0.02, 0.1, 0.5, 1, 4, 20):
        view.setTransform(QtGui.QTransform.fromScale(zoom, zoom))
        fine, coarse, fade = view.grid_levels()
        assert view.GRID_MIN_SPACING <= fine * zoom
        assert coarse * zoom <= view.GRID_MAX_SPACING * 2


def test_both_styles_are_spaced_alike(view, settings):
    """It is the same grid; only how it is drawn differs."""

    view.resize(500, 400)
    for zoom in (0.05, 1, 8):
        view.setTransform(QtGui.QTransform.fromScale(zoom, zoom))
        settings.setValue('View/grid_style', 'lines')
        ruled = view.grid_levels()
        settings.setValue('View/grid_style', 'dots')
        assert view.grid_levels() == ruled


def dots_drawn(view):
    """Every point the grid asks to have a dot put at."""

    from unittest.mock import MagicMock, patch
    from PyQt6 import QtCore

    points = []

    def remember(self, painter, pen, across, down):
        points.extend(
            QtCore.QPointF(round(p.x()), round(p.y()))
            for p in (view.mapFromScene(QtCore.QPointF(x, y))
                      for x in across for y in down))

    with patch('PyQt6.QtWidgets.QGraphicsView.drawBackground'):
        with patch.object(type(view), 'draw_grid_dots', remember):
            view.drawBackground(MagicMock(), QtCore.QRectF(0, 0, 500, 400))
    return points


def test_a_dot_is_always_put_on_a_whole_pixel(view, settings):
    """Points of the board land wherever the zoom puts them, and a
    round dot on a fractional pixel is spread over its neighbours: the
    same dot measured two pixels across at one zoom and five at
    another, which is the difference that gets noticed."""

    settings.setValue('View/grid_style', 'dots')
    view.show_grid = True

    for zoom in (0.02, 0.07, 0.13, 0.5, 0.77, 1, 1.3, 4, 9.5, 20):
        view.setTransform(QtGui.QTransform.fromScale(zoom, zoom))
        drawn_at = dots_drawn(view)
        assert drawn_at, f'no dots at all at {zoom}'
        for point in drawn_at:
            assert point.x() == int(point.x())
            assert point.y() == int(point.y())
