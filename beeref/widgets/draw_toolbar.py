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

"""The bar of drawing tools."""

import logging

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref.assets import BeeAssets
from beeref.items import BeeDrawItem


logger = logging.getLogger(__name__)


class DrawToolBar(QtWidgets.QWidget):
    """Buttons for picking a drawing tool and its colour."""

    MARGIN = 20
    BUTTON_SIZE = 34
    ICON_SIZE = 20

    # The tools, in the order they appear
    TOOLS = (
        (None, 'select', 'Select and move items'),
        (BeeDrawItem.SKETCH, 'sketch', 'Sketch freehand'),
        (BeeDrawItem.LINE, 'line', 'Draw a straight line'),
        (BeeDrawItem.SPLINE, 'spline', 'Draw a curve'),
        (BeeDrawItem.ARROW, 'arrow', 'Draw a straight arrow'),
        (BeeDrawItem.SPLINE_ARROW, 'spline_arrow', 'Draw a curved arrow'),
    )

    def __init__(self, parent, view):
        super().__init__(parent)
        self.view = view
        self.setObjectName('DrawToolBar')
        self.buttons = {}

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        for kind, icon, tooltip in self.TOOLS:
            button = QtWidgets.QToolButton(self)
            button.setCheckable(True)
            button.setToolTip(tooltip)
            button.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
            button.setIconSize(QtCore.QSize(self.ICON_SIZE, self.ICON_SIZE))
            button.setIcon(BeeAssets().tool_icon(icon))
            button.clicked.connect(
                lambda checked, kind=kind: self.view.set_draw_tool(kind))
            layout.addWidget(button)
            self.buttons[kind] = button

        self.color_button = QtWidgets.QToolButton(self)
        self.color_button.setToolTip('Drawing colour')
        self.color_button.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
        self.color_button.clicked.connect(self.view.on_action_draw_color)
        layout.addWidget(self.color_button)

        self.setLayout(layout)
        self.update_color(self.view.draw_color)
        self.update_checked(None)
        self.adjustSize()

    def update_checked(self, kind):
        """Show which tool is in use."""

        for tool, button in self.buttons.items():
            button.setChecked(tool == kind)

    def update_color(self, color):
        """Show the colour new drawings will use."""

        pixmap = QtGui.QPixmap(self.ICON_SIZE, self.ICON_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor(120, 120, 120)))
        painter.setBrush(QtGui.QBrush(color))
        painter.drawEllipse(1, 1, self.ICON_SIZE - 2, self.ICON_SIZE - 2)
        painter.end()
        self.color_button.setIcon(QtGui.QIcon(pixmap))
        self.color_button.setIconSize(
            QtCore.QSize(self.ICON_SIZE, self.ICON_SIZE))

    def reposition(self):
        """Sit in the top left corner of the view."""

        self.move(self.MARGIN, self.MARGIN)
