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

"""A small bar of buttons that follows the item it acts on."""

import logging

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from beeref.assets import BeeAssets


logger = logging.getLogger(__name__)


class PinnedToolBar(QtWidgets.QWidget):
    """Buttons that sit next to whatever is selected.

    Shown only while there is something for them to act on, and moved
    to follow it, so the controls are always beside the work rather
    than in a corner of the window.
    """

    # Space left between the bar and the item it belongs to
    GAP = 8
    BUTTON_SIZE = 34
    ICON_SIZE = 20

    def __init__(self, parent, view):
        super().__init__(parent)
        self.view = view
        # Never take focus: an item being edited holds the keyboard
        # focus, and taking it away ends the edit and clears the
        # selection, which would hide this bar after a single click
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.layout = QtWidgets.QHBoxLayout()
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)
        self.setLayout(self.layout)

    def add_button(self, icon, tooltip, callback, repeat=False):
        button = QtWidgets.QToolButton(self)
        button.setToolTip(tooltip)
        button.setIcon(BeeAssets().tool_icon(icon))
        button.setIconSize(QtCore.QSize(self.ICON_SIZE, self.ICON_SIZE))
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
        button.clicked.connect(callback)
        if repeat:
            # Holding the button keeps going, so a long way is one press
            # rather than twenty clicks
            button.setAutoRepeat(True)
            button.setAutoRepeatDelay(400)
            button.setAutoRepeatInterval(120)
        self.layout.addWidget(button)
        return button

    def pin_to(self, rect):
        """Sit just above the given rectangle of the viewport.

        When there is no room above -- the item is near the top of the
        window -- the bar goes underneath instead, and it never leaves
        the visible area.
        """

        self.adjustSize()
        size = self.size()
        area = self.parentWidget().rect()

        x = rect.center().x() - size.width() // 2
        x = max(0, min(x, area.width() - size.width()))

        y = rect.top() - size.height() - self.GAP
        if y < 0:
            y = rect.bottom() + self.GAP
        y = max(0, min(y, area.height() - size.height()))

        self.move(x, y)
