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

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from beeref.assets import BeeAssets


logger = logging.getLogger(__name__)


class TextToolBar(QtWidgets.QWidget):
    """The buttons for formatting the selected text.

    Bold, smaller and bigger, highlight colour and box colour: the same
    commands as the Text menu, within reach of the text being worked on.
    Sizing scales by a percentage rather than by a number of points, so
    the steps stay proportional however big the text already is. Shown
    only while text is selected, and sits under the drawing tools.
    """

    MARGIN = 20
    # Space left between the bar and the text it belongs to
    GAP = 8
    BUTTON_SIZE = 34
    ICON_SIZE = 20

    def __init__(self, parent, view):
        super().__init__(parent)
        self.view = view
        self.setObjectName('TextToolBar')
        # Never take focus. A text item that is being edited holds the
        # keyboard focus, and taking it away ends the edit and clears the
        # selection -- which hides this bar after a single click, so the
        # buttons cannot be clicked repeatedly.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.bold = self.add_button(
            layout, 'bold', 'Bold', view.on_action_text_bold)
        # Only the size buttons repeat while held: pressing and holding
        # bold or a colour has nothing sensible to keep doing
        self.smaller = self.add_button(
            layout, 'smaller', 'Make the text smaller',
            view.on_action_size_decrease, repeat=True)
        self.bigger = self.add_button(
            layout, 'bigger', 'Make the text bigger',
            view.on_action_size_increase, repeat=True)
        self.highlight = self.add_button(
            layout, 'highlight', 'Highlight colour',
            view.on_action_text_highlight_color)
        self.box_color = self.add_button(
            layout, 'box_color', 'Box colour',
            view.on_action_text_box_color)

        self.setLayout(layout)
        self.adjustSize()

    def add_button(self, layout, icon, tooltip, callback, repeat=False):
        button = QtWidgets.QToolButton(self)
        button.setToolTip(tooltip)
        button.setIcon(BeeAssets().tool_icon(icon))
        button.setIconSize(QtCore.QSize(self.ICON_SIZE, self.ICON_SIZE))
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
        button.clicked.connect(callback)
        if repeat:
            # Holding the button keeps scaling, so going a long way is
            # one press rather than twenty clicks
            button.setAutoRepeat(True)
            button.setAutoRepeatDelay(400)
            button.setAutoRepeatInterval(120)
        layout.addWidget(button)
        return button

    def pin_to(self, rect):
        """Sit just above the given rectangle of the viewport.

        The bar follows the text it belongs to, so the buttons are
        always next to what they act on. When there is no room above --
        the text is near the top of the window -- it goes underneath
        instead, and it never leaves the visible area.
        """

        self.adjustSize()
        size = self.size()
        area = self.parentWidget().rect()

        x = rect.center().x() - size.width() // 2
        x = max(0, min(x, area.width() - size.width()))

        y = rect.top() - size.height() - self.GAP
        if y < 0:
            # No room above the text, so hang underneath it
            y = rect.bottom() + self.GAP
        y = max(0, min(y, area.height() - size.height()))

        self.move(x, y)
