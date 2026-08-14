# This file is part of BeeRef.
#
# BeeRef is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BeeRef is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BeeRef.  If not, see <https://www.gnu.org/licenses/>.

from collections import OrderedDict
import re

from PyQt6 import QtCore, QtGui


def create_palette_from_dict(conf):
    """Create a palette from a config dictionary. Keys are a string of
    'ColourGroup:ColorRole' and values are a (r, g, b) tuple. E.g:
    {
        'Active:WindowText': (80, 100, 0),
        ...
    }

    Colors from the Active group will automatically be applied to the
    Inactive group as well. Unknown color groups will be ignored.
    """

    palette = QtGui.QPalette()
    for key, value in conf.items():
        group, role = key.split(':')
        if hasattr(QtGui.QPalette.ColorGroup, group):
            palette.setColor(
                getattr(QtGui.QPalette.ColorGroup, group),
                getattr(QtGui.QPalette.ColorRole, role),
                QtGui.QColor(*value))
            if group == 'Active':
                # Also set the Inactive colour group.
                palette.setColor(
                    QtGui.QPalette.ColorGroup.Inactive,
                    getattr(QtGui.QPalette.ColorRole, role),
                    QtGui.QColor(*value))

    return palette


def get_rect_from_points(point1, point2):
    """Constructs a QRectF from the given QPointF. The points can be *any*
    two opposing corners of the rectangle."""

    topleft = QtCore.QPointF(
        min(point1.x(), point2.x()),
        min(point1.y(), point2.y()))
    bottomright = QtCore.QPointF(
        max(point1.x(), point2.x()),
        max(point1.y(), point2.y()))
    return QtCore.QRectF(topleft, bottomright)


def round_to(number, base):
    """Rounds to the given base.

    E.g. with ``base=5`` round to the nearest number divisible by 5.
    """

    return base * round(number / base)


def get_file_extension_from_format(formatstr):
    """Extracts the first file extension from a Qt file dialog format,
    e.g. 'JPEG (*.jpg *.jpeg)' yields 'jpg'.
    """

    extensions = re.match(r'.* \((.*)\)', formatstr).groups()[0]
    ext = extensions.split()[0]
    return ext.removeprefix('*.')


def qcolor_to_hex(color):
    """Returns the QColor as a hex represenation string:
    #RRGGBBAA if the color has transparencey, otherwise #RRGGBB.
    """

    if color.alpha() == 255:
        return color.name()

    # The name method can only do HexRgb and HexArgb, not HexRgba, so
    # we have to do this ourselves:
    rgb = color.name()
    alpha = hex(color.alpha()).removeprefix('0x')
    return f'{rgb}{alpha}'


def relative_luminance(color):
    """How bright a colour appears, on a scale of 0 to 1.

    This is the sRGB formula used for contrast ratios, which weights
    the channels by how bright the eye perceives them.
    """

    def channel(value):
        value = value / 255
        if value <= 0.03928:
            return value / 12.92
        return ((value + 0.055) / 1.055) ** 2.4

    return (0.2126 * channel(color.red())
            + 0.7152 * channel(color.green())
            + 0.0722 * channel(color.blue()))


def contrast_ratio(lum1, lum2):
    """The contrast between two luminance values, from 1 to 21."""

    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


def blend_over(color, background):
    """The colour that a translucent colour appears as over a background."""

    alpha = color.alphaF()
    if alpha >= 1:
        return QtGui.QColor(color.red(), color.green(), color.blue())
    return QtGui.QColor(
        round(color.red() * alpha + background.red() * (1 - alpha)),
        round(color.green() * alpha + background.green() * (1 - alpha)),
        round(color.blue() * alpha + background.blue() * (1 - alpha)))


def readable_grey(background):
    """The shade that contrasts most with the given background colour.

    Black or white, whichever stands out more, so text is always as
    readable as it can be on whatever colour it sits on.
    """

    bg_lum = relative_luminance(background)
    white = QtGui.QColor(255, 255, 255)
    black = QtGui.QColor(0, 0, 0)
    if (contrast_ratio(relative_luminance(white), bg_lum)
            >= contrast_ratio(relative_luminance(black), bg_lum)):
        return white
    return black


class ActionList(OrderedDict):

    def __init__(self, actions):
        super().__init__()
        for action in actions:
            self[action.id] = action

    def __getitem__(self, key):
        if isinstance(key, int):
            key = list(self.keys())[key]
        return super().__getitem__(key)
