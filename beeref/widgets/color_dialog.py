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

"""Trimming Qt's colour dialog down to what this application needs."""

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

from beeref.assets import BeeAssets
from beeref.utils import readable_grey


logger = logging.getLogger(__name__)


class LegendColors(QtWidgets.QWidget):
    """The board's legend, offered in the colour dialog.

    The same colours and the same words as the panel, in the space the
    custom slots used to take, so a colour that already means something
    on this board is picked by its meaning rather than matched by eye.

    They are only to be picked from. A legend is edited in its own
    panel, where the words that go with the colours are.
    """

    SWATCH = 18
    # Past this the list scrolls rather than pushing OK off the screen
    MAX_HEIGHT = 160

    def __init__(self, dialog, legend):
        super().__init__(dialog)
        self.dialog = dialog

        lines = QtWidgets.QVBoxLayout()
        lines.setContentsMargins(0, 0, 0, 0)
        lines.setSpacing(3)
        for entry in legend:
            lines.addWidget(self.build_row(entry))
        lines.addStretch(100)

        holder = QtWidgets.QWidget()
        holder.setLayout(lines)
        area = QtWidgets.QScrollArea(self)
        area.setWidget(holder)
        area.setWidgetResizable(True)
        area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        area.setMaximumHeight(self.MAX_HEIGHT)
        area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(QtWidgets.QLabel('Legend', self))
        layout.addWidget(area)
        self.setLayout(layout)

    def build_row(self, entry):
        color = QtGui.QColor(*entry['color'])
        row = QtWidgets.QWidget(self)
        button = QtWidgets.QToolButton(row)
        button.setFixedSize(self.SWATCH, self.SWATCH)
        button.setStyleSheet(
            f'background-color: {color.name()};'
            f' color: {readable_grey(color).name()};'
            ' border: 1px solid #555; border-radius: 3px;')
        button.clicked.connect(
            lambda checked=False, color=color: self.on_pick(color))

        # A line with nothing written on it is still worth offering, so
        # it goes by its colour instead
        label = QtWidgets.QLabel(entry['text'] or color.name(), row)
        label.setToolTip(entry['text'] or color.name())

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(button)
        layout.addWidget(label, 100)
        row.setLayout(layout)
        return row

    def on_pick(self, color):
        """Choose the colour, the way clicking a swatch does."""

        self.dialog.setCurrentColor(color)


def layout_holding(layout, widget):
    """The layout a widget sits in, and where in it, or None."""

    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is widget:
            return layout, index
        child = item.layout()
        if child is not None:
            found = layout_holding(child, widget)
            if found is not None:
                return found
    return None


def simplify_color_dialog(dialog, legend=None):
    """Cut Qt's colour dialog down to the swatches and the eyedropper.

    What is left is the grid of palette colours, the button that picks a
    colour off the screen, and OK/Cancel. The gradient square, the
    numeric fields and the custom colour slots are gone: colours here
    come from the palette, not from anywhere on an infinite gradient.

    Qt offers no option for this, so the parts to drop are found among
    the dialog's own children. They are recognised by the text Qt gives
    them, so a future Qt that renames one would leave that part showing
    rather than break anything.

    A board's legend, when there is one, goes in where the custom slots
    used to be; see LegendColors.
    """

    children = [child for child in dialog.children()
                if isinstance(child, QtWidgets.QWidget)]

    # The swatch grids are what their labels point at. The first is the
    # basic colours, which is the one worth keeping -- the grid itself,
    # not the label: with nothing else left to tell it apart from, a row
    # of colours needs no heading saying it is a row of colours.
    labelled = [child for child in children
                if isinstance(child, QtWidgets.QLabel) and child.buddy()]
    keep = {labelled[0].buddy()} if labelled else set()

    screen_button = None
    for child in children:
        if (isinstance(child, QtWidgets.QPushButton)
                and 'Pick Screen' in child.text().replace('&', '')):
            screen_button = child
            break

    for child in children:
        if child in keep or child is screen_button:
            continue
        if isinstance(child, QtWidgets.QDialogButtonBox):
            continue
        child.hide()

    if legend and keep:
        # Into the column the swatches are in, right under them, which
        # is where the custom slots used to be
        holder = layout_holding(dialog.layout(), labelled[0].buddy())
        if holder is not None:
            column, index = holder
            column.insertWidget(index + 1, LegendColors(dialog, legend))

    if screen_button is not None:
        # An eyedropper says it better than the sentence did, and the
        # sentence was the widest thing in the dialog
        screen_button.setIcon(BeeAssets().tool_icon('eyedropper'))
        screen_button.setIconSize(QtCore.QSize(20, 20))
        screen_button.setText('')
        screen_button.setToolTip('Pick a colour from anywhere on the screen')
        screen_button.setFixedSize(34, 34)

    dialog.adjustSize()
