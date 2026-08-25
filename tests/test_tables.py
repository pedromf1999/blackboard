from beeref.items import BeeTextItem


def note_with_table(view):
    """A note being written in, with the cursor inside a fresh table."""

    item = BeeTextItem('hello')
    view.scene.addItem(item)
    item.setSelected(True)
    item.enter_edit_mode()
    view.on_action_insert_table()
    return item


def test_insert_table_is_offered_under_insert(view):
    """The right-click Insert list is where a new thing is looked for."""

    menu = [m for m in view.toplevel_menus if m.title() == '&Insert'][0]
    entry = [a for a in menu.actions() if a.text() == 'Insert Ta&ble']
    assert len(entry) == 1
    # The menu says how to do it without the menu
    assert entry[0].shortcut().toString() == 'Ctrl+Shift+T'


def test_the_top_bar_can_insert_one(view):
    view.draw_toolbar.insert_table.click()
    item = view.scene.item_with_table()
    assert item is not None
    assert item.current_table().rows() == item.TABLE_ROWS


def test_the_bar_appears_with_the_table_and_goes_with_it(view):
    item = note_with_table(view)
    assert view.table_toolbar.isHidden() is False
    item.exit_edit_mode()
    view.update_table_toolbar()
    assert view.table_toolbar.isHidden() is True


def test_the_two_bars_stack_instead_of_overlapping(view):
    """A note holding a table has both bars; one must not cover the other."""

    note_with_table(view)
    view.update_pinned_toolbars()
    assert not view.text_toolbar.geometry().intersects(
        view.table_toolbar.geometry())


def test_a_row_can_be_added_above_as_well_as_below(view):
    item = note_with_table(view)
    rows = item.current_table().rows()
    view.on_action_table_row_insert_above()
    assert item.current_table().rows() == rows + 1
    view.on_action_table_row_insert()
    assert item.current_table().rows() == rows + 2


def test_headers_go_on_and_off(view):
    item = note_with_table(view)
    table = item.current_table()
    assert item.has_header(table) is False
    assert item.has_header(table, column=True) is False

    view.on_action_table_header_top()
    view.on_action_table_header_left()
    table = item.current_table()
    assert item.has_header(table) is True
    assert item.has_header(table, column=True) is True
    # Qt's own notion of a header row, for anything the table is
    # carried into
    assert table.format().headerRowCount() == 1

    view.on_action_table_header_top()
    table = item.current_table()
    assert item.has_header(table) is False
    assert item.has_header(table, column=True) is True
    assert table.format().headerRowCount() == 0


def test_a_header_survives_being_saved_and_read_back(view):
    """The shading is the header, and shading is what a file keeps.

    Bold looked like the better marker until empty cells proved they
    keep no formatting at all across the round trip.
    """

    item = note_with_table(view)
    view.on_action_table_header_top()
    view.on_action_table_header_left()

    reloaded = BeeTextItem(html=item.toHtml())
    table = reloaded.tables()[0]
    assert reloaded.has_header(table) is True
    assert reloaded.has_header(table, column=True) is True


def test_the_header_buttons_show_which_headers_are_on(view):
    note_with_table(view)
    assert view.table_toolbar.header_top.isChecked() is False
    view.on_action_table_header_top()
    assert view.table_toolbar.header_top.isChecked() is True
    assert view.table_toolbar.header_left.isChecked() is False


def test_the_header_shade_follows_the_note_it_is_on(view):
    """A fixed grey would vanish on a note of about that colour."""

    item = note_with_table(view)
    dark = item.header_shade()
    item.box_color = item.box_color.__class__(240, 240, 240, 255)
    assert item.header_shade() != dark


def test_a_single_column_table_can_still_have_a_left_header(view):
    """With no neighbouring column, the shading alone has to decide."""

    item = note_with_table(view)
    view.on_action_table_column_remove()
    view.on_action_table_column_remove()
    table = item.current_table()
    assert table.columns() == 1
    item.set_header(table, True, column=True)
    assert item.has_header(table, column=True) is True


def test_the_table_commands_wake_up_when_the_cursor_enters_a_table(view):
    """They act on the cell in hand, so a click into one has to count."""

    item = note_with_table(view)
    cursor = item.textCursor()
    cursor.setPosition(0)
    item.setTextCursor(cursor)
    item.cursor_may_have_moved()
    assert view.table_toolbar.isHidden() is True

    table = item.tables()[0]
    item.setTextCursor(table.cellAt(1, 1).firstCursorPosition())
    item.cursor_may_have_moved()
    assert view.table_toolbar.isHidden() is False
