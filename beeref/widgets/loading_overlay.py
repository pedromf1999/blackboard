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

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

from beeref.assets import BeeAssets


logger = logging.getLogger(__name__)


class LoadingOverlay(QtWidgets.QWidget):
    """What is shown while a board is being opened.

    A board arrives item by item, and the view is looking at wherever it
    was left, so opening a file used to show a corner of somebody's work
    sliding into place. This covers that up with the wordmark until the
    board is whole and has been fitted to the window.
    """

    # How much of the window's width the wordmark takes, and how wide it
    # is allowed to get on a very large window.
    WIDTH_SHARE = 0.4
    MAX_WIDTH = 640

    def __init__(self, parent):
        super().__init__(parent)
        self.hide()

    def start(self):
        self.resize(self.parentWidget().size())
        self.show()
        self.raise_()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0))

        width = min(self.width() * self.WIDTH_SHARE, self.MAX_WIDTH)
        wordmark = BeeAssets().wordmark(width, light_word=True)
        if wordmark is None:
            return

        painter.drawImage(
            QtCore.QPointF((self.width() - wordmark.width()) / 2,
                           (self.height() - wordmark.height()) / 2),
            wordmark)
        painter.end()
