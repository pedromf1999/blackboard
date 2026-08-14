import pytest

from PyQt6 import QtGui

from beeref.utils import (
    blend_over,
    contrast_ratio,
    readable_grey,
    relative_luminance,
)


def ratio_against(color, background):
    return contrast_ratio(relative_luminance(color),
                          relative_luminance(background))


def test_relative_luminance_range():
    assert relative_luminance(QtGui.QColor(0, 0, 0)) == 0
    assert relative_luminance(QtGui.QColor(255, 255, 255)) == 1


def test_relative_luminance_weights_green_most():
    green = relative_luminance(QtGui.QColor(0, 255, 0))
    red = relative_luminance(QtGui.QColor(255, 0, 0))
    blue = relative_luminance(QtGui.QColor(0, 0, 255))
    assert green > red > blue


def test_contrast_ratio_bounds():
    black = relative_luminance(QtGui.QColor(0, 0, 0))
    white = relative_luminance(QtGui.QColor(255, 255, 255))
    assert contrast_ratio(black, white) == pytest.approx(21)
    assert contrast_ratio(black, black) == 1


@pytest.mark.parametrize(
    'rgb',
    [(0, 0, 0), (52, 52, 52), (128, 128, 128), (200, 200, 200),
     (255, 255, 255), (140, 20, 20), (245, 225, 90), (25, 40, 90)])
def test_readable_grey_is_grey(rgb):
    grey = readable_grey(QtGui.QColor(*rgb))
    assert grey.red() == grey.green() == grey.blue()


def test_readable_grey_on_white_is_black():
    assert readable_grey(QtGui.QColor(255, 255, 255)) == QtGui.QColor(0, 0, 0)


def test_readable_grey_on_black_is_white():
    assert readable_grey(QtGui.QColor(0, 0, 0)) == QtGui.QColor(
        255, 255, 255)


@pytest.mark.parametrize(
    'rgb',
    [(0, 0, 0), (52, 52, 52), (128, 128, 128), (200, 200, 200),
     (255, 255, 255), (140, 20, 20), (245, 225, 90), (25, 40, 90)])
def test_readable_grey_picks_the_best_contrast(rgb):
    """Whichever of black or white stands out more is the one used."""

    background = QtGui.QColor(*rgb)
    chosen = readable_grey(background)
    other = (QtGui.QColor(0, 0, 0) if chosen.lightness() > 127
             else QtGui.QColor(255, 255, 255))
    assert ratio_against(chosen, background) >= ratio_against(
        other, background)


def test_readable_grey_flips_for_light_backgrounds():
    assert readable_grey(QtGui.QColor(20, 20, 20)).lightness() > 127
    assert readable_grey(QtGui.QColor(240, 240, 240)).lightness() < 127


def test_blend_over_opaque_colour_is_unchanged():
    color = QtGui.QColor(10, 20, 30)
    assert blend_over(color, QtGui.QColor(200, 200, 200)) == color


def test_blend_over_translucent_colour():
    half = QtGui.QColor(0, 0, 0, 128)
    result = blend_over(half, QtGui.QColor(255, 255, 255))
    assert 120 <= result.red() <= 135
    assert result.alpha() == 255


def test_blend_over_fully_transparent_shows_background():
    clear = QtGui.QColor(255, 0, 0, 0)
    assert blend_over(clear, QtGui.QColor(39, 39, 39)) == QtGui.QColor(
        39, 39, 39)
