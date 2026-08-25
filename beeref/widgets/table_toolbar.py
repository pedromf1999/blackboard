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

"""The buttons for the table being edited."""

import logging

from beeref.widgets.pinned_toolbar import PinnedToolBar


logger = logging.getLogger(__name__)


class TableToolBar(PinnedToolBar):
    """Rows, columns, headers and cell colour for the table in hand.

    Shown while the cursor is inside a table rather than while a note is
    selected: these commands act on the cell being worked in, so they
    only make sense once there is one.
    """

    def __init__(self, parent, view):
        super().__init__(parent, view)

        self.row_above = self.add_button(
            'table_row_above', 'Insert a row above',
            view.on_action_table_row_insert_above)
        self.row_below = self.add_button(
            'table_row_below', 'Insert a row below',
            view.on_action_table_row_insert)
        self.row_delete = self.add_button(
            'table_row_delete', 'Delete this row',
            view.on_action_table_row_remove)
        self.column_insert = self.add_button(
            'table_column_insert', 'Insert a column to the right',
            view.on_action_table_column_insert)
        self.column_delete = self.add_button(
            'table_column_delete', 'Delete this column',
            view.on_action_table_column_remove)
        # The two headers stay pressed while they are on, so the bar
        # says which of them the table already has
        self.header_top = self.add_button(
            'table_header_top', 'Top header row',
            view.on_action_table_header_top)
        self.header_top.setCheckable(True)
        self.header_left = self.add_button(
            'table_header_left', 'Left header column',
            view.on_action_table_header_left)
        self.header_left.setCheckable(True)
        self.cell_color = self.add_button(
            'color', 'Cell colour', view.on_action_table_cell_color,
            keep_colors=True)

        self.adjustSize()

    def update_headers(self, item):
        """Show which headers the table being edited already has."""

        table = item.current_table()
        if table is None:
            return
        self.header_top.setChecked(item.has_header(table))
        self.header_left.setChecked(item.has_header(table, column=True))
