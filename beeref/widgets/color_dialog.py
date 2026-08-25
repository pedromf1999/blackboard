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

from PyQt6 import QtCore, QtWidgets

from beeref.assets import BeeAssets


logger = logging.getLogger(__name__)


def simplify_color_dialog(dialog):
    """Cut Qt's colour dialog down to the swatches and the eyedropper.

    What is left is the grid of palette colours, the button that picks a
    colour off the screen, and OK/Cancel. The gradient square, the
    numeric fields and the custom colour slots are gone: colours here
    come from the palette, not from anywhere on an infinite gradient.

    Qt offers no option for this, so the parts to drop are found among
    the dialog's own children. They are recognised by the text Qt gives
    them, so a future Qt that renames one would leave that part showing
    rather than break anything.
    """

    children = [child for child in dialog.children()
                if isinstance(child, QtWidgets.QWidget)]

    # The swatch grids are what their labels point at. The first is the
    # basic colours, which is the one worth keeping.
    labelled = [child for child in children
                if isinstance(child, QtWidgets.QLabel) and child.buddy()]
    keep = set()
    if labelled:
        keep = {labelled[0], labelled[0].buddy()}

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

    if screen_button is not None:
        # An eyedropper says it better than the sentence did, and the
        # sentence was the widest thing in the dialog
        screen_button.setIcon(BeeAssets().tool_icon('eyedropper'))
        screen_button.setIconSize(QtCore.QSize(20, 20))
        screen_button.setText('')
        screen_button.setToolTip('Pick a colour from anywhere on the screen')
        screen_button.setFixedSize(34, 34)

    dialog.adjustSize()
