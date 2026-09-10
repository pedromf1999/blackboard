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

"""Reading a table off the clipboard.

Word, Excel, Sheets and Teams all put an HTML copy of what was copied
onto the clipboard, and the spreadsheets put a tab separated copy there
as well. Only the shape and the words are taken from either: a
Blackboard table has no colours, borders, fonts or merged cells to give
the rest to.
"""

import logging
import re

from html.parser import HTMLParser


logger = logging.getLogger(__name__)


# What one paste may bring in. A spreadsheet will hand over as much as
# it is asked for, and a table of thousands of cells is not a thing to
# put on a board by accident.
MAX_ROWS = 200
MAX_COLUMNS = 50

# Tags whose text belongs to the page rather than to the table
IGNORED = {'style', 'script', 'head', 'title'}


def tidy(text):
    """One line of words, however the other application spaced them."""

    return re.sub(r'\s+', ' ', text).strip()


class TableReader(HTMLParser):
    """The rows and cells of the first table in a piece of HTML.

    Only the outermost table is read. A table nested inside a cell --
    which is how Word lays out a good deal of what it copies -- has its
    words added to the cell holding it rather than becoming a table of
    its own.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None
        self.depth = 0
        self.ignoring = 0
        self.finished = False

    def handle_starttag(self, tag, attrs):
        if tag in IGNORED:
            self.ignoring += 1
            return
        if self.finished:
            return
        if tag == 'table':
            self.depth += 1
            return
        if self.depth != 1:
            # Inside a table within a cell: its words count, its shape
            # does not
            return
        if tag == 'tr':
            self.close_row()
            self.row = []
        elif tag in ('td', 'th'):
            self.close_cell()
            self.cell = []
        elif tag == 'br' and self.cell is not None:
            self.cell.append(' ')

    def handle_endtag(self, tag):
        if tag in IGNORED:
            self.ignoring = max(0, self.ignoring - 1)
            return
        if self.finished:
            return
        if tag == 'table':
            self.depth -= 1
            if self.depth == 0:
                self.close_row()
                self.finished = True
            return
        if self.depth != 1:
            return
        if tag in ('td', 'th'):
            self.close_cell()
        elif tag == 'tr':
            self.close_row()

    def handle_data(self, data):
        if self.ignoring or self.finished or self.cell is None:
            return
        self.cell.append(data)

    def close_cell(self):
        if self.cell is None:
            return
        if self.row is None:
            # A cell outside any row: give it one, rather than losing it
            self.row = []
        self.row.append(tidy(''.join(self.cell)))
        self.cell = None

    def close_row(self):
        self.close_cell()
        if self.row:
            self.rows.append(self.row)
        self.row = None


def squared_off(rows):
    """Every row the same length, so the result is a grid.

    A merged cell counts once and leaves its row short; the row is
    padded rather than the table refusing to come across.
    """

    rows = [row[:MAX_COLUMNS] for row in rows[:MAX_ROWS]]
    if not rows:
        return None
    columns = max(len(row) for row in rows)
    if not columns:
        return None
    return [row + [''] * (columns - len(row)) for row in rows]


def table_from_html(html):
    """The first table in this HTML as rows of words, or None."""

    reader = TableReader()
    try:
        reader.feed(html)
        reader.close()
    except Exception:
        # Whatever the other application produced, a paste that cannot
        # be read as a table is not an error: it is simply not a table
        logger.debug('Could not read a table out of the pasted HTML',
                     exc_info=True)
        return None
    reader.close_row()
    return squared_off(reader.rows)


def table_from_text(text):
    """A tab separated table as rows of words, or None.

    Held to a stricter test than the HTML, because plain text arrives
    from everywhere: every line has to be split the same number of
    times, and there has to be something to split.
    """

    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return None
    rows = [line.split('\t') for line in lines]
    columns = len(rows[0])
    if columns < 2 or any(len(row) != columns for row in rows):
        return None
    return squared_off([[tidy(cell) for cell in row] for row in rows])


def table_from_mimedata(mimedata):
    """Whatever table the clipboard is offering, or None.

    The HTML first: a spreadsheet offers both, and only the HTML says
    where one cell ends and the next begins when a cell holds a tab or
    a line of its own.
    """

    if mimedata is None:
        return None
    if mimedata.hasHtml():
        rows = table_from_html(mimedata.html())
        if rows:
            return rows
    if mimedata.hasText():
        return table_from_text(mimedata.text())
    return None
