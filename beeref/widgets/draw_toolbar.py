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

from PyQt6 import QtCore, QtWidgets

from beeref import constants
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
        (constants.TEXT_TOOL, 'text', 'Write a note (T)'),
        (BeeDrawItem.SKETCH, 'sketch', 'Sketch freehand'),
        (BeeDrawItem.LINE, 'line', 'Draw a straight line'),
        (BeeDrawItem.SPLINE, 'spline', 'Draw a curve'),
        (BeeDrawItem.ARROW, 'arrow', 'Draw a straight arrow'),
        (BeeDrawItem.SPLINE_ARROW, 'spline_arrow', 'Draw a curved arrow'),
    )

    # Kept behind one button rather than laid out beside the rest:
    # five more buttons on the bar crowded out everything else
    SHAPE_TOOLS = (
        (BeeDrawItem.CIRCLE, 'shape_circle', 'Draw a circle'),
        (BeeDrawItem.SQUARE, 'shape_square', 'Draw a square'),
        (BeeDrawItem.TRIANGLE, 'shape_triangle', 'Draw a triangle'),
        (BeeDrawItem.PENTAGON, 'shape_pentagon', 'Draw a pentagon'),
        (BeeDrawItem.HEXAGON, 'shape_hexagon', 'Draw a hexagon'),
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
            layout.addWidget(self.tool_button(kind, icon, tooltip))

        # The shapes live on their own strip, opened by this button
        self.shape_bar = ShapeToolBar(parent, view, self)
        self.shape_bar.hide()
        self.shapes = QtWidgets.QToolButton(self)
        self.shapes.setCheckable(True)
        self.shapes.setToolTip('Shapes')
        self.shapes.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
        self.shapes.setIconSize(
            QtCore.QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.shapes.setIcon(BeeAssets().tool_icon('shapes'))
        self.shapes.clicked.connect(self.on_shapes_clicked)
        layout.addWidget(self.shapes)

        # Neither of these is a tool to work in, so they do not stay
        # pressed the way the tools above do
        self.find_text = QtWidgets.QToolButton(self)
        self.find_text.setToolTip(
            'Find text (Ctrl+F), then F3 to cycle through')
        self.find_text.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
        self.find_text.setIconSize(
            QtCore.QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.find_text.setIcon(BeeAssets().tool_icon('search'))
        self.find_text.clicked.connect(self.view.on_action_find_text)
        layout.addSpacing(6)
        layout.addWidget(self.find_text)

        self.insert_table = QtWidgets.QToolButton(self)
        self.insert_table.setToolTip('Insert a table (Ctrl+Shift+T)')
        self.insert_table.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
        self.insert_table.setIconSize(
            QtCore.QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.insert_table.setIcon(BeeAssets().tool_icon('table'))
        self.insert_table.clicked.connect(self.view.on_action_insert_table)
        layout.addWidget(self.insert_table)

        # The colour lives on the bar that follows a selected drawing,
        # where it is next to the line it recolours
        self.setLayout(layout)
        self.update_checked(None)
        self.adjustSize()

    def tool_button(self, kind, icon, tooltip, parent=None):
        """One tool button, wherever it is going to sit."""

        button = QtWidgets.QToolButton(parent or self)
        button.setCheckable(True)
        button.setToolTip(tooltip)
        button.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
        button.setIconSize(QtCore.QSize(self.ICON_SIZE, self.ICON_SIZE))
        button.setIcon(BeeAssets().tool_icon(icon))
        button.clicked.connect(
            lambda checked, kind=kind: self.view.set_draw_tool(kind))
        self.buttons[kind] = button
        return button

    def on_shapes_clicked(self):
        self.set_shapes_open(not self.shape_bar.isVisible())

    def set_shapes_open(self, open_):
        """Show or hide the strip of shapes."""

        self.shapes.setChecked(open_)
        if open_:
            self.shape_bar.reposition()
            self.shape_bar.show()
            self.shape_bar.raise_()
        else:
            self.shape_bar.hide()

    def update_checked(self, kind):
        """Show which tool is in use."""

        for tool, button in self.buttons.items():
            button.setChecked(tool == kind)
        if kind in BeeDrawItem.SHAPES:
            # Picking one shape leaves the strip up, so the next one is
            # a single click away
            self.shapes.setChecked(True)
        else:
            self.set_shapes_open(False)

    def reposition(self):
        """Sit in the top left corner of the view."""

        self.move(self.MARGIN, self.MARGIN)
        if self.shape_bar.isVisible():
            self.shape_bar.reposition()


class ShapeToolBar(QtWidgets.QWidget):
    """The shapes, on a strip under the tool bar.

    A sibling of the tool bar rather than a child of it: a child drawn
    outside its parent is simply clipped away.
    """

    GAP = 6

    def __init__(self, parent, view, toolbar):
        super().__init__(parent)
        self.view = view
        self.toolbar = toolbar
        self.setObjectName('DrawToolBar')

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        for kind, icon, tooltip in toolbar.SHAPE_TOOLS:
            layout.addWidget(toolbar.tool_button(kind, icon, tooltip, self))
        self.setLayout(layout)
        self.adjustSize()

    def reposition(self):
        """Sit under the button that opened it."""

        self.adjustSize()
        bar = self.toolbar
        # Lined up with the Shapes button, but never off the left edge
        left = bar.x() + bar.shapes.x() + bar.shapes.width() - self.width()
        self.move(max(bar.x(), left), bar.y() + bar.height() + self.GAP)
