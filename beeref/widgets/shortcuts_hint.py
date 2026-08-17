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

"""A reminder of the main shortcuts, shown when the app starts."""

import logging

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt

from beeref import constants
from beeref.config import BeeSettings


logger = logging.getLogger(__name__)


class ShortcutsHint(QtWidgets.QWidget):
    """A small card in the corner listing what the shortcuts do."""

    SETTINGS_KEY = 'View/show_shortcuts_hint'
    MARGIN = 20

    SHORTCUTS = (
        ('Ctrl + J', 'Show or hide the layers panel'),
        ('Ctrl + T', 'Add a text note, ready to type'),
        ('Ctrl + G', 'Group the selected items'),
        ('Ctrl + Shift + G', 'Ungroup'),
        ('Ctrl + F  /  F3', 'Find text, and jump to the next match'),
        ('Alt + drag', 'Take an item out of its group'),
        ('Ctrl + click', 'Open a link in a text note'),
    )

    def __init__(self, parent):
        super().__init__(parent)
        self.settings = BeeSettings()
        self.setObjectName('ShortcutsHint')
        color = constants.COLORS['Active:Window']
        self.setStyleSheet(
            f'#ShortcutsHint {{ background-color: rgba('
            f'{color[0]}, {color[1]}, {color[2]}, 0.95);'
            'border-radius: 8px; }')

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setHorizontalSpacing(14)

        title = QtWidgets.QLabel(f'<b>{constants.APPNAME} shortcuts</b>')
        layout.addWidget(title, 0, 0, 1, 2)

        close = QtWidgets.QToolButton(self)
        close.setAutoRaise(True)
        close.setText('✕')
        close.setToolTip('Close')
        close.clicked.connect(self.on_close_clicked)
        layout.addWidget(close, 0, 2, Qt.AlignmentFlag.AlignRight)

        for row, (keys, what) in enumerate(self.SHORTCUTS, start=1):
            layout.addWidget(QtWidgets.QLabel(f'<b>{keys}</b>'), row, 0)
            layout.addWidget(QtWidgets.QLabel(what), row, 1, 1, 2)

        hide = QtWidgets.QCheckBox("Don't show this again", self)
        hide.stateChanged.connect(self.on_hide_changed)
        layout.addWidget(hide, len(self.SHORTCUTS) + 1, 0, 1, 3)

        self.setLayout(layout)
        self.adjustSize()

    def on_close_clicked(self):
        logger.debug('Closing the shortcuts hint')
        self.hide()

    def on_hide_changed(self, state):
        wanted = state != Qt.CheckState.Checked.value
        logger.debug(f'Show shortcuts on startup: {wanted}')
        self.settings.setValue(self.SETTINGS_KEY, wanted)

    def wanted_on_startup(self):
        return self.settings.value(
            self.SETTINGS_KEY, True, type=bool)

    def reposition(self):
        """Sit in the bottom left corner of the view."""

        parent = self.parentWidget()
        self.move(self.MARGIN,
                  parent.height() - self.height() - self.MARGIN)

    def show_if_wanted(self):
        if not self.wanted_on_startup():
            logger.debug('Shortcuts hint switched off')
            return
        self.reposition()
        self.show()
        self.raise_()
