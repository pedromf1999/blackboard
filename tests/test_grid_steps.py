import math

from PyQt6 import QtGui


def sweep(view, settings, size, lowest=0.005, highest=50, by=1.03):
    """What the grid does across the zooms, level by level."""

    settings.setValue('View/grid_size', size)
    seen = []
    zoom = lowest
    while zoom < highest:
        view.setTransform(QtGui.QTransform.fromScale(zoom, zoom))
        fine, coarse, fade = view.grid_levels()
        seen.append((zoom, fine, coarse, fade))
        zoom *= by
    return seen


def test_the_two_levels_are_an_octave_apart(view, settings):
    """Every second line of the finer grid is a line of the coarser
    one, so nothing moves: lines only come in and go out between the
    ones that stay."""

    for zoom, fine, coarse, fade in sweep(view, settings, 100):
        assert coarse == fine * 2


def test_the_finer_level_fades_rather_than_arriving(view, settings):
    """What was noticed was not the change but its suddenness."""

    fades = [fade for _, _, _, fade in sweep(view, settings, 100)]
    assert min(fades) < 0.05
    assert max(fades) > 0.95
    assert 0.4 < sum(fades) / len(fades) < 0.6


def test_the_fade_moves_a_little_at_a_time(view, settings):
    """A turn of the wheel must not bring a whole set of lines with it."""

    seen = sweep(view, settings, 100, by=1.03)
    for (_, _, _, before), (_, _, _, after) in zip(seen, seen[1:]):
        # Wrapping round from nothing to everything is where one level
        # hands over to the next, and there the lines are already gone
        assert abs(after - before) < 0.1 or min(before, after) < 0.1


def test_the_grid_keeps_much_the_same_distance_at_any_zoom(view, settings):
    """It used to step by five: the distance on screen swung between
    twenty-six and a hundred and twenty-five pixels, so a little zoom
    either way changed the number of lines fivefold."""

    on_screen = [fine * zoom for zoom, fine, _, _ in
                 sweep(view, settings, 100)]
    assert max(on_screen) / min(on_screen) <= 2.01


def test_it_holds_for_any_spacing_that_was_asked_for(view, settings):
    for size in (25, 50, 100, 200):
        seen = sweep(view, settings, size)
        on_screen = [fine * zoom for zoom, fine, _, _ in seen]
        assert max(on_screen) / min(on_screen) <= 2.01


def test_at_the_boards_own_size_it_is_the_spacing_asked_for(view, settings):
    """Which is what the setting says it is."""

    view.setTransform(QtGui.QTransform.fromScale(1, 1))
    for size in (25, 50, 100, 200):
        settings.setValue('View/grid_size', size)
        fine, coarse, fade = view.grid_levels()
        assert fine == size
        assert fade == 1


def test_a_spacing_too_wide_to_be_useful_is_reined_in(view, settings):
    """A grid nobody can see two lines of at once is not a grid."""

    view.setTransform(QtGui.QTransform.fromScale(1, 1))
    settings.setValue('View/grid_size', 5000)
    fine, _, _ = view.grid_levels()
    assert fine <= view.GRID_MAX_SPACING


def test_a_spacing_too_close_to_be_useful_is_opened_out(view, settings):
    view.setTransform(QtGui.QTransform.fromScale(1, 1))
    settings.setValue('View/grid_size', 5)
    fine, _, _ = view.grid_levels()
    assert fine * 2 >= view.GRID_MIN_SPACING


def test_it_stays_sensible_at_the_far_ends(view, settings):
    """A board is worked on from a thousandth to a thousand times."""

    settings.setValue('View/grid_size', 100)
    for zoom in (0.001, 0.01, 1, 100, 1000):
        view.setTransform(QtGui.QTransform.fromScale(zoom, zoom))
        fine, coarse, _ = view.grid_levels()
        assert view.GRID_MIN_SPACING <= fine * zoom
        assert coarse * zoom <= view.GRID_MAX_SPACING * 2


def test_the_spacings_stay_whole_halves_of_each_other(view, settings):
    """Powers of two of the spacing asked for, so a line that is there
    at one zoom is in the same place at the next."""

    settings.setValue('View/grid_size', 100)
    for zoom, fine, _, _ in sweep(view, settings, 100):
        octaves = math.log2(fine / 100)
        assert abs(octaves - round(octaves)) < 1e-9


def test_no_zoom_at_all_is_survived(view, settings):
    view.setTransform(QtGui.QTransform.fromScale(0, 0))
    fine, coarse, fade = view.grid_levels()
    assert fine > 0 and coarse > fine
