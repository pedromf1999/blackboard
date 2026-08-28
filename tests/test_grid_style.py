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

    step = view.get_grid_step()
    across = view.grid_positions(0, 500, step)
    assert across == [0, step, 2 * step, 3 * step, 4 * step]


def test_the_spacing_setting_is_obeyed_either_way(view, settings):
    settings.setValue('View/grid_size', 50)
    small = view.get_grid_step()
    settings.setValue('View/grid_size', 200)
    assert view.get_grid_step() > small


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
        on_screen = view.get_grid_step() * view.get_scale()
        assert view.GRID_MIN_SPACING <= on_screen <= view.GRID_MAX_SPACING


def test_both_styles_are_spaced_alike(view, settings):
    """It is the same grid; only how it is drawn differs."""

    view.resize(500, 400)
    for zoom in (0.05, 1, 8):
        view.setTransform(QtGui.QTransform.fromScale(zoom, zoom))
        settings.setValue('View/grid_style', 'lines')
        ruled = view.get_grid_step()
        settings.setValue('View/grid_style', 'dots')
        assert view.get_grid_step() == ruled


def test_a_dot_stays_the_same_size_on_screen(view, settings):
    """Like the lines, which are one pixel wide however far in or out
    the board is."""

    view.resize(500, 400)
    settings.setValue('View/grid_style', 'dots')
    view.show_grid = True
    background = QtGui.QColor(settings.valueOrDefault('View/canvas_color'))

    def widest_dot():
        view.viewport().update()
        shot = view.viewport().grab().toImage()
        for y in range(shot.height()):
            run = 0
            for x in range(shot.width()):
                if shot.pixelColor(x, y) != background:
                    run += 1
                elif run:
                    return run
        return 0

    for zoom in (0.02, 1, 20):
        view.setTransform(QtGui.QTransform.fromScale(zoom, zoom))
        assert 1 <= widest_dot() <= view.GRID_DOT_SIZE + 2
