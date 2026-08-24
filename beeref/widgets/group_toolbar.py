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

"""The buttons for the selected group."""

import logging

from beeref.widgets.pinned_toolbar import PinnedToolBar


logger = logging.getLogger(__name__)


class GroupToolBar(PinnedToolBar):
    """The colour of the selected group, beside the group.

    The same idea as the bar that follows a note or a drawing: what a
    group can be given is offered where the group is, rather than being
    looked for in a menu.
    """

    def __init__(self, parent, view):
        super().__init__(parent, view)

        self.color = self.add_button(
            'box_color', 'Group colour', view.on_action_group_box_color)

        self.adjustSize()
