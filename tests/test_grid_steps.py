from PyQt6 import QtGui


def sweep(view, settings, size, lowest=0.005, highest=50, by=1.05):
    """Every spacing and every change the grid makes across the zooms."""

    settings.setValue('View/grid_size', size)
    spacings = []
    changes = []
    previous = None
    zoom = lowest
    while zoom < highest:
        view.setTransform(QtGui.QTransform.fromScale(zoom, zoom))
        step = view.get_grid_step()
        spacings.append(step * zoom)
        if previous is not None and step != previous:
            changes.append(max(previous / step, step / previous))
        previous = step
        zoom *= by
    return spacings, changes


def test_the_grid_keeps_much_the_same_distance_at_any_zoom(view, settings):
    """It used to alternate steps of five and two: the distance on
    screen swung between twenty-six and a hundred and twenty-five
    pixels, so a little zoom either way changed the number of lines
    fivefold."""

    spacings, _ = sweep(view, settings, 100)
    assert max(spacings) / min(spacings) < 2


def test_no_single_change_doubles_the_grid(view, settings):
    """Which is the change that gets noticed."""

    _, changes = sweep(view, settings, 100)
    assert changes
    assert max(changes) < 2


def test_it_holds_for_any_spacing_that_was_asked_for(view, settings):
    for size in (25, 50, 100, 200):
        spacings, changes = sweep(view, settings, size)
        assert max(spacings) / min(spacings) < 2
        assert max(changes) < 2


def test_at_the_boards_own_size_it_is_the_spacing_asked_for(view, settings):
    """Which is what the setting says it is."""

    view.setTransform(QtGui.QTransform.fromScale(1, 1))
    for size in (25, 50, 100, 200):
        settings.setValue('View/grid_size', size)
        assert view.get_grid_step() == size


def test_a_spacing_too_wide_to_be_useful_is_reined_in(view, settings):
    """A grid nobody can see two lines of at once is not a grid.

    Not held exactly at the limit: the steps are a fixed set, so the
    nearest one to the limit is what is taken.
    """

    view.setTransform(QtGui.QTransform.fromScale(1, 1))
    settings.setValue('View/grid_size', 1000)
    assert view.get_grid_step() < view.GRID_MAX_SPACING * 1.5


def test_a_spacing_too_close_to_be_useful_is_opened_out(view, settings):
    view.setTransform(QtGui.QTransform.fromScale(1, 1))
    settings.setValue('View/grid_size', 5)
    assert view.get_grid_step() >= view.GRID_MIN_SPACING


def test_it_stays_sensible_at_the_far_ends(view, settings):
    """A board is worked on from a fiftieth to twenty times and further."""

    settings.setValue('View/grid_size', 100)
    for zoom in (0.001, 0.01, 1, 100, 1000):
        view.setTransform(QtGui.QTransform.fromScale(zoom, zoom))
        on_screen = view.get_grid_step() * zoom
        assert view.GRID_MIN_SPACING / 2 < on_screen
        assert on_screen < view.GRID_MAX_SPACING * 2


def test_the_steps_it_takes_are_round_enough_to_read(view, settings):
    """A grid is a guide: 150 and 300 are places, 137.4 is not."""

    import math

    settings.setValue('View/grid_size', 100)
    seen = set()
    zoom = 0.01
    while zoom < 20:
        view.setTransform(QtGui.QTransform.fromScale(zoom, zoom))
        seen.add(view.get_grid_step())
        zoom *= 1.1

    assert len(seen) > 5
    for step in seen:
        decade = 10 ** math.floor(math.log10(step))
        assert round(step / decade, 3) in [round(factor, 3)
                                           for factor in view.GRID_STEPS]


def test_no_zoom_at_all_is_survived(view, settings):
    view.setTransform(QtGui.QTransform.fromScale(0, 0))
    assert view.get_grid_step() > 0
