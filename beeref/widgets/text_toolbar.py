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

"""The buttons for resizing text."""

import logging

from PyQt6 import QtWidgets


logger = logging.getLogger(__name__)


class TextToolBar(QtWidgets.QWidget):
    """Minus and plus buttons for scaling the selected text.

    Each click scales by a percentage rather than by a number of points,
    so the steps stay proportional however big the text already is. Shown
    only while text is selected, and sits under the drawing tools.
    """

    MARGIN = 20
    # Space between this bar and the one above it
    GAP = 8
    BUTTON_SIZE = 34

    def __init__(self, parent, view):
        super().__init__(parent)
        self.view = view
        self.setObjectName('TextToolBar')

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # A real minus sign, which lines up with the plus better than a hyphen
        self.smaller = self.add_button(
            layout, '−', 'Make the text smaller',
            view.on_action_text_size_decrease)
        self.bigger = self.add_button(
            layout, '+', 'Make the text bigger',
            view.on_action_text_size_increase)

        self.setLayout(layout)
        self.adjustSize()

    def add_button(self, layout, label, tooltip, callback):
        button = QtWidgets.QToolButton(self)
        button.setText(label)
        button.setToolTip(tooltip)
        button.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
        button.clicked.connect(callback)
        # Holding the button keeps scaling, so going a long way is one
        # press rather than twenty clicks
        button.setAutoRepeat(True)
        button.setAutoRepeatDelay(400)
        button.setAutoRepeatInterval(120)
        layout.addWidget(button)
        return button

    def reposition(self, below=None):
        """Sit under the given widget, or in the top left corner."""

        top = self.MARGIN
        if below is not None:
            top = below.y() + below.height() + self.GAP
        self.move(self.MARGIN, top)
