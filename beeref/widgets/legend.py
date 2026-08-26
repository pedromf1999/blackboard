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

"""The board's legend: a colour and a word, on as many lines as wanted."""

import logging

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref import commands, constants
from beeref.assets import BeeAssets
from beeref.utils import readable_grey, relative_luminance
from beeref.widgets.color_dialog import simplify_color_dialog


logger = logging.getLogger(__name__)


class LegendRow(QtWidgets.QWidget):
    """One line: a square of colour, what it means, and a way to drop it."""

    SWATCH = 22

    def __init__(self, panel, color, text):
        super().__init__(panel)
        self.panel = panel
        self.color = QtGui.QColor(*color)

        self.swatch = QtWidgets.QToolButton(self)
        self.swatch.setFixedSize(self.SWATCH, self.SWATCH)
        self.swatch.setToolTip('Change this colour')
        self.swatch.clicked.connect(self.on_pick_color)
        self.update_swatch()

        self.edit = QtWidgets.QLineEdit(text, self)
        self.edit.setPlaceholderText('What it means')
        # Recorded when the line is left rather than on every letter, so
        # a typed word is one step to undo and not twenty
        self.edit.editingFinished.connect(self.panel.commit)

        self.remove = QtWidgets.QToolButton(self)
        self.remove.setFixedSize(self.SWATCH, self.SWATCH)
        self.remove.setText('×')
        self.remove.setToolTip('Remove this line')
        self.remove.clicked.connect(self.on_remove)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.swatch)
        layout.addWidget(self.edit)
        layout.addWidget(self.remove)
        self.setLayout(layout)

    def update_swatch(self):
        self.swatch.setStyleSheet(
            f'background-color: {self.color.name()};'
            f' color: {readable_grey(self.color).name()};'
            ' border: 1px solid #555; border-radius: 3px;')

    def on_pick_color(self):
        dialog = QtWidgets.QColorDialog(self.color, self)
        dialog.setWindowTitle('Choose Legend Colour')
        simplify_color_dialog(dialog)
        if dialog.exec() and dialog.currentColor().isValid():
            self.color = dialog.currentColor()
            self.update_swatch()
            self.panel.commit()

    def on_remove(self):
        self.panel.remove_row(self)

    def as_data(self):
        return {'color': self.color.getRgb(),
                'text': self.edit.text()}


class LegendPanel(QtWidgets.QWidget):
    """The lines themselves, with a button to add another.

    Kept in step with the board's own list rather than holding the
    legend itself: undo and redo change that list, and the panel is
    built again from it.
    """

    # A swatch darker than this is a hole in a dark panel, not a colour
    DARKEST = 0.03

    def __init__(self, parent, view):
        super().__init__(parent)
        self.view = view
        self.rows = []
        self.building = False

        self.lines = QtWidgets.QVBoxLayout()
        self.lines.setContentsMargins(0, 0, 0, 0)
        self.lines.setSpacing(4)

        holder = QtWidgets.QWidget()
        holder.setLayout(self.lines)
        area = QtWidgets.QScrollArea(self)
        area.setWidget(holder)
        area.setWidgetResizable(True)
        area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.add_button = QtWidgets.QPushButton('Add a line', self)
        self.add_button.clicked.connect(self.on_add)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(area)
        layout.addWidget(self.add_button)
        self.setLayout(layout)

    def refresh(self):
        """Build the lines again from the board's legend."""

        if self.building:
            return
        wanted = self.view.scene.legend
        if [row.as_data() for row in self.rows] == wanted:
            return
        self.building = True
        while self.lines.count():
            entry = self.lines.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.rows = []
        for entry in wanted:
            row = LegendRow(self, entry['color'], entry['text'])
            self.lines.addWidget(row)
            self.rows.append(row)
        self.lines.addStretch(100)
        self.building = False

    def commit(self):
        """Put what the panel now shows onto the undo stack."""

        if self.building:
            return
        rows = [row.as_data() for row in self.rows]
        if rows == self.view.scene.legend:
            return
        self.view.undo_stack.push(
            commands.ChangeLegend(self.view.scene, rows))

    def on_add(self):
        """A new line, in the next colour along rather than white again."""

        rows = [row.as_data() for row in self.rows]
        rows.append({'color': self.next_color(rows), 'text': ''})
        self.view.undo_stack.push(
            commands.ChangeLegend(self.view.scene, rows))
        if self.rows:
            self.rows[-1].edit.setFocus()

    def next_color(self, rows):
        """Step through the palette, so lines start out telling apart."""

        palette = [color for color in BeeAssets().palette
                   if relative_luminance(color) > self.DARKEST]
        if not palette:
            return (255, 255, 255, 255)
        return palette[len(rows) % len(palette)].getRgb()

    def remove_row(self, row):
        rows = [other.as_data() for other in self.rows if other is not row]
        self.view.undo_stack.push(
            commands.ChangeLegend(self.view.scene, rows))


class LegendHandle(QtWidgets.QToolButton):
    """The square that stands in for the panel while it is put away.

    Sits under the layers handle: both live at the top of the same edge,
    and one over the other would hide it.
    """

    MARGIN = 8
    SIZE = 26
    GAP = 6

    def __init__(self, parent, view):
        super().__init__(parent)
        self.view = view
        self.area = Qt.DockWidgetArea.RightDockWidgetArea
        self.setObjectName('LegendHandle')
        color = constants.COLORS['Active:Window']
        self.setStyleSheet(
            f'#LegendHandle {{ background-color: rgba('
            f'{color[0]}, {color[1]}, {color[2]}, 0.95);'
            'border-radius: 5px; }')
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setToolTip('Show the legend (Ctrl+L)')
        self.clicked.connect(view.toggle_legend_panel)
        self.set_side(self.area)

    def set_side(self, area):
        self.area = area
        self.setArrowType(
            Qt.ArrowType.RightArrow
            if area == Qt.DockWidgetArea.LeftDockWidgetArea
            else Qt.ArrowType.LeftArrow)

    def reposition(self):
        parent = self.parentWidget()
        if self.area == Qt.DockWidgetArea.LeftDockWidgetArea:
            x = self.MARGIN
        else:
            x = parent.width() - self.width() - self.MARGIN
        self.move(x, self.MARGIN + self.SIZE + self.GAP)


class LegendTitleBar(QtWidgets.QWidget):
    """An arrow to put the panel away, and its name beside it."""

    def __init__(self, dock):
        super().__init__(dock)
        self.dock = dock

        self.collapse_button = QtWidgets.QToolButton(self)
        self.collapse_button.setAutoRaise(True)
        self.collapse_button.clicked.connect(self.dock.toggle_collapsed)

        self.label = QtWidgets.QLabel(dock.windowTitle(), self)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self.collapse_button)
        layout.addWidget(self.label)
        layout.addStretch(100)
        self.setLayout(layout)
        self.update_collapse_button(False)

    def update_collapse_button(self, collapsed):
        self.collapse_button.setArrowType(
            Qt.ArrowType.LeftArrow if collapsed else Qt.ArrowType.DownArrow)
        self.collapse_button.setToolTip('Expand' if collapsed else 'Collapse')


class LegendDock(QtWidgets.QDockWidget):
    """The dockable panel holding the legend.

    Built the same way as the layers panel, and for the same reason:
    collapsed it costs no room, so it is put away rather than closed.
    """

    DEFAULT_WIDTH = 240

    def __init__(self, parent, view):
        super().__init__('Legend', parent)
        self.view = view
        self.main_window = parent
        self.setObjectName('LegendDock')
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.panel = LegendPanel(self, view)
        self.setWidget(self.panel)
        self.collapsed = False
        self.expanded_width = self.DEFAULT_WIDTH
        self.titlebar = LegendTitleBar(self)
        self.setTitleBarWidget(self.titlebar)
        parent.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self)
        self.set_collapsed(True)

    def toggle_collapsed(self):
        self.view.toggle_legend_panel()

    def set_collapsed(self, value):
        logger.debug(f'Collapsing legend panel: {value}')
        if value and not self.collapsed:
            self.expanded_width = max(self.width(), self.DEFAULT_WIDTH)
        self.collapsed = value
        self.titlebar.update_collapse_button(value)
        if value:
            self.hide()
        else:
            self.panel.setVisible(True)
            self.panel.refresh()
            self.show()
            self.main_window.resizeDocks(
                [self], [self.expanded_width], Qt.Orientation.Horizontal)
        self.view.update_legend_handle()
