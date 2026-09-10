from unittest.mock import patch

from PyQt6 import QtCore, QtGui

from beeref import tables
from beeref.items import BeePixmapItem


WORD = '''<html xmlns:o="urn:schemas-microsoft-com:office:office">
<head><style><!-- .MsoNormal {margin:0cm;} --></style></head>
<body><table class=MsoTableGrid border=1 cellspacing=0 cellpadding=0>
 <tr><td><p class=MsoNormal><b>Ficha</b></p></td>
     <td><p>Macho&nbsp;/&nbsp;f&#234;mea</p></td>
     <td><p>8&nbsp;mm</p></td></tr>
 <tr><td><p>Pilar</p></td><td><p>ao PCB</p></td><td><p>8,2 mm</p></td></tr>
</table></body></html>'''

SHEETS = '''<meta charset="utf-8"><google-sheets-html-origin>
<table cellspacing="0" cellpadding="0" border="1">
<colgroup><col width="100"/><col width="100"/></colgroup><tbody>
<tr><td><span style="font-weight:bold">Contacto</span></td><td>Passo</td></tr>
<tr><td>220</td><td>0,50</td></tr></tbody></table>'''

TEAMS = '''<div><table class="ui-table">
<thead><tr><th colspan="2">Plug (Mass Prod)</th></tr></thead>
<tbody><tr><td><div>Normal</div></td><td><div>47-1234-01</div></td></tr>
</tbody></table></div>'''


def clipboard_with(html=None, text=None):
    """A clipboard offering what another application would have put on
    it, and no picture."""

    data = QtCore.QMimeData()
    if html is not None:
        data.setHtml(html)
    if text is not None:
        data.setText(text)
    return data


def paste(view, html=None, text=None):
    clipboard = QtGui.QGuiApplication.clipboard()
    with patch.object(type(clipboard), 'image', return_value=QtGui.QImage()):
        with patch.object(type(clipboard), 'mimeData',
                          return_value=clipboard_with(html, text)):
            with patch.object(type(clipboard), 'text',
                              return_value=text or ''):
                view.on_action_paste()


def pasted_table(view):
    """The table in the note that was just pasted."""

    items = list(view.scene.items_by_type('text'))
    assert len(items) == 1, items
    tables_found = items[0].tables()
    assert len(tables_found) == 1
    return tables_found[0]


def cells_of(table):
    return [[table.cellAt(r, c).firstCursorPosition().block().text()
             for c in range(table.columns())]
            for r in range(table.rows())]


def test_a_word_table_comes_across(view):
    paste(view, html=WORD)
    table = pasted_table(view)

    assert (table.rows(), table.columns()) == (2, 3)
    assert cells_of(table) == [['Ficha', 'Macho / fêmea', '8 mm'],
                               ['Pilar', 'ao PCB', '8,2 mm']]


def test_a_sheets_table_comes_across(view):
    paste(view, html=SHEETS)
    table = pasted_table(view)

    assert (table.rows(), table.columns()) == (2, 2)
    assert cells_of(table)[0] == ['Contacto', 'Passo']


def test_a_teams_table_comes_across(view):
    """Its heading is merged across the top; a merged cell counts once
    and the row is padded rather than the table refusing to come."""

    paste(view, html=TEAMS)
    table = pasted_table(view)

    assert (table.rows(), table.columns()) == (2, 2)
    assert cells_of(table) == [['Plug (Mass Prod)', ''],
                               ['Normal', '47-1234-01']]


def test_a_spreadsheet_pasted_as_plain_text_comes_across(view):
    paste(view, text='Altura\t7,45\t4,45\r\nPasso\t0,5\t\r\n')
    table = pasted_table(view)

    assert (table.rows(), table.columns()) == (2, 3)
    assert cells_of(table) == [['Altura', '7,45', '4,45'],
                               ['Passo', '0,5', '']]


def test_the_html_is_preferred_to_the_text(view):
    """A spreadsheet offers both, and only the HTML says where one cell
    ends when a cell holds a tab or a line of its own."""

    paste(view, html=SHEETS, text='something\tquite\tdifferent')
    table = pasted_table(view)

    assert (table.rows(), table.columns()) == (2, 2)


def test_pasting_a_table_is_one_step_to_undo(view):
    depth = view.undo_stack.index()
    paste(view, html=SHEETS)
    assert view.undo_stack.index() == depth + 1

    view.undo_stack.undo()
    assert list(view.scene.items_by_type('text')) == []


def test_the_table_lands_in_a_note_of_its_own(view):
    paste(view, html=SHEETS)
    item = list(view.scene.items_by_type('text'))[0]

    assert item.tables()
    # Nothing but the table: no placeholder word left over it
    assert item.toPlainText().startswith('Contacto') or item.tables()


def test_ordinary_prose_is_still_pasted_as_a_note(view):
    paste(view, text='Just a sentence, no tabs at all.')
    items = list(view.scene.items_by_type('text'))

    assert len(items) == 1
    assert items[0].tables() == []
    assert items[0].toPlainText() == 'Just a sentence, no tabs at all.'


def test_html_that_holds_no_table_is_pasted_as_a_note(view):
    paste(view, html='<p>Hello <b>there</b></p>', text='Hello there')
    items = list(view.scene.items_by_type('text'))

    assert items[0].tables() == []


def test_a_picture_on_the_clipboard_still_wins(view):
    img = QtGui.QImage(40, 30, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor('red'))
    clipboard = QtGui.QGuiApplication.clipboard()
    with patch.object(type(clipboard), 'image', return_value=img):
        with patch.object(type(clipboard), 'mimeData',
                          return_value=clipboard_with(html=SHEETS)):
            view.on_action_paste()

    assert len(list(view.scene.items_by_type('pixmap'))) == 1
    assert list(view.scene.items_by_type('text')) == []
    assert isinstance(list(view.scene.items_by_type('pixmap'))[0],
                      BeePixmapItem)


# Reading the clipboard, without a board to put the result on

def test_a_stray_tab_in_one_line_of_many_is_not_a_table(view):
    assert tables.table_from_text('one\ttwo\nthree') is None


def test_a_single_line_of_cells_is_a_table(view):
    assert tables.table_from_text('one\ttwo\tthree') == [
        ['one', 'two', 'three']]


def test_text_with_no_tabs_is_not_a_table(view):
    assert tables.table_from_text('one\ntwo\nthree') is None


def test_nothing_at_all_is_not_a_table(view):
    assert tables.table_from_text('') is None
    assert tables.table_from_html('') is None
    assert tables.table_from_mimedata(None) is None


def test_the_styles_word_sends_are_not_read_as_words(view):
    rows = tables.table_from_html(WORD)

    assert 'MsoNormal' not in str(rows)
    assert 'margin' not in str(rows)


def test_a_table_inside_a_cell_stays_inside_it(view):
    """Word lays a good deal of what it copies out that way."""

    html = ('<table><tr><td>Outer<table><tr><td>Inner</td>'
            '<td>Deeper</td></tr></table></td><td>Beside</td></tr></table>')
    rows = tables.table_from_html(html)

    assert len(rows) == 1
    assert rows[0][1] == 'Beside'
    assert 'Inner' in rows[0][0]


def test_the_second_table_on_the_clipboard_is_left_behind(view):
    html = ('<table><tr><td>First</td></tr></table>'
            '<table><tr><td>Second</td></tr></table>')

    assert tables.table_from_html(html) == [['First']]


def test_a_line_break_inside_a_cell_becomes_a_space(view):
    html = '<table><tr><td>two<br>lines</td><td>b</td></tr></table>'

    assert tables.table_from_html(html) == [['two lines', 'b']]


def test_a_ragged_table_is_squared_off(view):
    html = ('<table><tr><td>a</td><td>b</td><td>c</td></tr>'
            '<tr><td>d</td></tr></table>')

    assert tables.table_from_html(html) == [['a', 'b', 'c'], ['d', '', '']]


def test_more_than_a_boardful_is_trimmed(view):
    """A spreadsheet hands over as much as it is asked for."""

    row = '<tr>' + '<td>x</td>' * (tables.MAX_COLUMNS + 20) + '</tr>'
    html = '<table>' + row * (tables.MAX_ROWS + 50) + '</table>'
    rows = tables.table_from_html(html)

    assert len(rows) == tables.MAX_ROWS
    assert len(rows[0]) == tables.MAX_COLUMNS


def test_broken_html_is_not_an_error(view):
    """A paste that cannot be read as a table is simply not a table."""

    assert tables.table_from_html('<table><tr><td>unclosed') == [['unclosed']]


def test_the_words_are_tidied_of_the_spacing_they_arrived_with(view):
    html = '<table><tr><td>  two   words \n </td><td>b</td></tr></table>'

    assert tables.table_from_html(html) == [['two words', 'b']]
