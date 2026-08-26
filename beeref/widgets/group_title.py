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

"""Asking for a group's title and the colour of its band."""

import logging

from PyQt6 import QtGui, QtWidgets

from beeref.utils import readable_grey
from beeref.widgets.color_dialog import simplify_color_dialog


logger = logging.getLogger(__name__)


class GroupTitleDialog(QtWidgets.QDialog):
    """The words of a group's title, and the colour they sit on.

    The two are asked for together because they belong together: a
    title's colour is only meaningful once there are words in it.
    Leaving the field empty is how a title is taken off again, so the
    same dialog puts one on and removes it.
    """

    def __init__(self, parent, title='', header_color=None, box_color=None):
        super().__init__(parent)
        self.setWindowTitle('Group Title')
        self.header_color = header_color
        self.box_color = box_color or QtGui.QColor(60, 60, 60)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(QtWidgets.QLabel(
            'Title, in bold. Leave it empty for no title at all.'))

        self.edit = QtWidgets.QLineEdit(title)
        self.edit.setPlaceholderText('No title')
        layout.addWidget(self.edit)

        self.color_button = QtWidgets.QPushButton()
        self.color_button.clicked.connect(self.on_pick_color)
        layout.addWidget(self.color_button)
        self.update_color_button()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self.edit.setFocus()

    def shown_color(self):
        """A band with no colour of its own shows the group's."""

        return self.header_color or self.box_color

    def update_color_button(self):
        color = self.shown_color()
        text = ('Band colour: same as the group' if self.header_color is None
                else f'Band colour: {color.name()}')
        self.color_button.setText(text)
        self.color_button.setStyleSheet(
            f'background-color: {color.name()};'
            f' color: {readable_grey(color).name()};')

    def on_pick_color(self):
        dialog = QtWidgets.QColorDialog(self.shown_color(), self)
        dialog.setWindowTitle('Choose Band Colour')
        simplify_color_dialog(dialog)
        if dialog.exec() and dialog.currentColor().isValid():
            self.header_color = dialog.currentColor()
            self.update_color_button()

    def get_answer(self):
        """The title and the band colour, as the dialog was left."""

        return self.edit.text().strip(), self.header_color
