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

from PyQt6 import QtGui, QtWidgets


logger = logging.getLogger(__name__)


class BeeAssets:
    _instance = None
    PATH = rsc_files('beeref.assets')

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
            cls._instance.on_new()
        return cls._instance

    def on_new(self):
        logger.debug(f'Assets path: {self.PATH}')

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

    def cursor_from_image(self, filename, hotspot):
        app = QtWidgets.QApplication.instance()
        scaling = app.primaryScreen().devicePixelRatio()
        img = QtGui.QImage(str(self.PATH.joinpath(filename)))
        assert img.isNull() is False
        pixmap = QtGui.QPixmap.fromImage(img)
        pixmap.setDevicePixelRatio(scaling)
        return QtGui.QCursor(
            pixmap, int(hotspot[0]/scaling), int(hotspot[1]/scaling))
