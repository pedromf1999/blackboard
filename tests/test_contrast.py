import pytest

from PyQt6 import QtGui

from beeref.utils import (
    blend_over,
    contrast_ratio,
    readable_grey,
    relative_luminance,
    TEXT_CONTRAST,
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


@pytest.mark.parametrize(
    'rgb',
    [(0, 0, 0), (52, 52, 52), (200, 200, 200), (255, 255, 255),
     (140, 20, 20), (245, 225, 90), (25, 40, 90)])
def test_readable_grey_keeps_contrast(rgb):
    background = QtGui.QColor(*rgb)
    assert ratio_against(readable_grey(background), background) >= 8


def test_readable_grey_tracks_the_background():
    """The grey shifts with the background rather than being fixed."""

    darker = readable_grey(QtGui.QColor(0, 0, 0))
    lighter = readable_grey(QtGui.QColor(60, 60, 60))
    assert lighter.lightness() > darker.lightness()


def test_readable_grey_flips_for_light_backgrounds():
    on_dark = readable_grey(QtGui.QColor(20, 20, 20))
    on_light = readable_grey(QtGui.QColor(240, 240, 240))
    assert on_dark.lightness() > 127
    assert on_light.lightness() < 127


def test_readable_grey_falls_back_for_mid_tones():
    """Mid greys can't reach the target, so contrast is maximised."""

    background = QtGui.QColor(128, 128, 128)
    grey = readable_grey(background)
    assert ratio_against(grey, background) >= 4.5
    assert grey in (QtGui.QColor(0, 0, 0), QtGui.QColor(255, 255, 255))


def test_readable_grey_target_is_configurable():
    background = QtGui.QColor(0, 0, 0)
    soft = readable_grey(background, 5)
    strong = readable_grey(background, TEXT_CONTRAST)
    assert strong.lightness() > soft.lightness()


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
