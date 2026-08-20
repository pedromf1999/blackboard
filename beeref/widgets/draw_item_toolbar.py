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

"""The buttons for the selected sketches, lines and arrows."""

import logging

from beeref.widgets.pinned_toolbar import PinnedToolBar


logger = logging.getLogger(__name__)


class DrawItemToolBar(PinnedToolBar):
    """The colour of the selected drawings, beside the drawings.

    The colour used to live in the tool bar in the corner, where it was
    a long way from the line being recoloured and offered itself even
    when there was nothing to recolour.
    """

    def __init__(self, parent, view):
        super().__init__(parent, view)

        self.color = self.add_button(
            'box_color', 'Drawing colour', view.on_action_draw_color)

        self.adjustSize()
