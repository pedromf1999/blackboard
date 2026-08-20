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

"""The buttons for formatting the selected text."""

import logging

from beeref.widgets.pinned_toolbar import PinnedToolBar


logger = logging.getLogger(__name__)


class TextToolBar(PinnedToolBar):
    """Bold, size, highlight and box colour for the selected text.

    The same commands as the Text menu, within reach of the text being
    worked on. Sizing scales by a percentage rather than by a number of
    points, so the steps stay proportional however big the text already
    is.
    """

    def __init__(self, parent, view):
        super().__init__(parent, view)

        self.bold = self.add_button(
            'bold', 'Bold', view.on_action_text_bold)
        # Only the size buttons repeat while held: pressing and holding
        # bold or a colour has nothing sensible to keep doing
        self.smaller = self.add_button(
            'smaller', 'Make the text smaller',
            view.on_action_size_decrease, repeat=True)
        self.bigger = self.add_button(
            'bigger', 'Make the text bigger',
            view.on_action_size_increase, repeat=True)
        self.highlight = self.add_button(
            'highlight', 'Highlight colour',
            view.on_action_text_highlight_color)
        self.box_color = self.add_button(
            'box_color', 'Box colour', view.on_action_text_box_color)

        self.adjustSize()
