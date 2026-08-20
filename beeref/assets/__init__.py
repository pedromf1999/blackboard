#!/usr/bin/env python3

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

from importlib.resources import files as rsc_files
import logging

from PyQt6 import QtCore, QtGui, QtSvg, QtWidgets


logger = logging.getLogger(__name__)


class BeeAssets:
    _instance = None
    PATH = rsc_files('beeref.assets')

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
            cls._instance.on_new()
        return cls._instance

    PALETTE_FILE = 'jehkoba64.hex'

    def on_new(self):
        logger.debug(f'Assets path: {self.PATH}')

        self._tool_icons = {}
        self._wordmarks = {}
        self.palette = self.load_palette()
        self.font_family = self.load_fonts()
        self.logo = QtGui.QIcon(str(self.PATH.joinpath('logo.png')))
        assert self.logo.isNull() is False
        self.cursor_rotate = self.cursor_from_image(
            'cursor_rotate.png', (20, 20))
        self.cursor_flip_h = self.cursor_from_image(
            'cursor_flip_h.png', (20, 20))
        self.cursor_flip_v = self.cursor_from_image(
            'cursor_flip_v.png', (20, 20))

    def load_fonts(self):
        """Load the bundled fonts, so that they work without being
        installed on the system.

        Returns the font family to use, or ``None`` when the fonts
        can't be loaded, in which case the default font is kept.
        """

        families = set()
        fontdir = self.PATH.joinpath('fonts')
        for filename in sorted(fontdir.iterdir()):
            if filename.suffix.lower() not in ('.otf', '.ttf'):
                continue
            font_id = QtGui.QFontDatabase.addApplicationFont(str(filename))
            if font_id == -1:
                logger.warning(f'Could not load font: {filename.name}')
                continue
            families.update(
                QtGui.QFontDatabase.applicationFontFamilies(font_id))

        if not families:
            logger.warning('No bundled fonts loaded; using the default font')
            return None
        logger.debug(f'Loaded font families: {sorted(families)}')
        return sorted(families)[0]

    ICON_COLOR = (220, 220, 220)
    ICON_SIZE = 64

    def tool_icon(self, name):
        """A toolbar icon, drawn in a colour that suits a dark interface.

        The icons are black line art, so they are recoloured rather than
        used as they are.
        """

        if name in self._tool_icons:
            return self._tool_icons[name]

        path = self.PATH.joinpath('icons', f'{name}.svg')
        image = QtGui.QImage(
            self.ICON_SIZE, self.ICON_SIZE,
            QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        renderer = QtSvg.QSvgRenderer(str(path))
        if renderer.isValid():
            renderer.render(painter)
            # Keep the shape, replace the colour
            painter.setCompositionMode(
                QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(image.rect(), QtGui.QColor(*self.ICON_COLOR))
        else:
            logger.warning(f'Could not load icon: {path}')
        painter.end()

        icon = QtGui.QIcon(QtGui.QPixmap.fromImage(image))
        self._tool_icons[name] = icon
        return icon

    def wordmark(self, width, inverted=False):
        """The Blackboard wordmark, drawn at the given width.

        The artwork is dark on nothing, meant for a light background.
        Inverting it gives a version for a dark one: the word turns
        white and the tile turns pale with a dark B, which is the same
        lockup rather than a recolouring of it. Returns ``None`` when
        the artwork cannot be loaded.
        """

        key = (round(width), inverted)
        if key in self._wordmarks:
            return self._wordmarks[key]

        path = self.PATH.joinpath('wordmark.svg')
        renderer = QtSvg.QSvgRenderer(str(path))
        if not renderer.isValid():
            logger.warning(f'Could not load wordmark: {path}')
            self._wordmarks[key] = None
            return None

        size = renderer.defaultSize()
        height = round(width * size.height() / size.width())
        image = QtGui.QImage(
            round(width), height, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        if inverted:
            image.invertPixels(QtGui.QImage.InvertMode.InvertRgb)

        self._wordmarks[key] = image
        return image

    def load_palette(self):
        """The colours offered by the colour pickers.

        One hex value per line, as palette files are usually written, so
        the file can be replaced with any other palette without touching
        code. Anything unreadable is skipped rather than bringing the
        application down over a colour swatch.
        """

        colors = []
        path = self.PATH.joinpath(self.PALETTE_FILE)
        try:
            text = path.read_text(encoding='utf-8')
        except OSError:
            logger.exception(f'Could not read palette {path}')
            return colors

        for line in text.splitlines():
            line = line.strip().lstrip('#')
            if not line:
                continue
            color = QtGui.QColor(f'#{line}')
            if color.isValid():
                colors.append(color)
            else:
                logger.warning(f'Skipping unreadable palette entry: {line}')
        logger.debug(f'Loaded {len(colors)} palette colours')
        return colors

    def cursor_from_image(self, filename, hotspot):
        app = QtWidgets.QApplication.instance()
        scaling = app.primaryScreen().devicePixelRatio()
        img = QtGui.QImage(str(self.PATH.joinpath(filename)))
        assert img.isNull() is False
        pixmap = QtGui.QPixmap.fromImage(img)
        pixmap.setDevicePixelRatio(scaling)
        return QtGui.QCursor(
            pixmap, int(hotspot[0]/scaling), int(hotspot[1]/scaling))
