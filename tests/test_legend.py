import os
from unittest.mock import patch

from PyQt6 import QtGui

from beeref import commands, fileio
from beeref.items import BeePixmapItem
from beeref.utils import relative_luminance


def panel(view):
    return view.legend_dock.panel


def test_the_legend_starts_empty_and_out_of_the_way(view):
    """Like the layers panel: a handle until it is wanted."""

    assert view.scene.legend == []
    assert view.legend_dock.collapsed is True
    assert view.legend_handle.isHidden() is False


def test_the_handle_sits_clear_of_the_layers_one(view):
    """Both live at the top of the same edge."""

    view.layers_handle.reposition()
    view.legend_handle.reposition()
    assert view.legend_handle.y() > view.layers_handle.y()
    assert view.legend_handle.x() == view.layers_handle.x()


def test_opening_the_panel_puts_the_handle_away(view):
    view.legend_dock.set_collapsed(False)
    assert view.legend_handle.isHidden() is True

    view.legend_dock.set_collapsed(True)
    assert view.legend_handle.isHidden() is False


def test_lines_can_be_added(view):
    panel(view).on_add()
    panel(view).on_add()

    assert len(view.scene.legend) == 2
    assert len(panel(view).rows) == 2


def test_a_new_line_gets_a_colour_that_shows(view):
    """The first colour of the palette is black, which on a dark panel
    is a hole rather than a colour."""

    for _ in range(4):
        panel(view).on_add()
    for entry in view.scene.legend:
        assert relative_luminance(
            QtGui.QColor(*entry['color'])) > panel(view).DARKEST


def test_successive_lines_start_out_telling_apart(view):
    panel(view).on_add()
    panel(view).on_add()
    colors = [entry['color'] for entry in view.scene.legend]
    assert colors[0] != colors[1]


def test_a_line_can_be_described(view):
    panel(view).on_add()
    panel(view).rows[0].edit.setText('Approved')
    panel(view).commit()

    assert view.scene.legend[0]['text'] == 'Approved'


def test_a_line_can_be_recoloured(view):
    panel(view).on_add()
    row = panel(view).rows[0]

    with patch('PyQt6.QtWidgets.QColorDialog.exec', return_value=1):
        with patch('PyQt6.QtWidgets.QColorDialog.currentColor',
                   return_value=QtGui.QColor('#ff8800')):
            row.on_pick_color()

    assert view.scene.legend[0]['color'] == QtGui.QColor(
        '#ff8800').getRgb()


def test_a_cancelled_colour_leaves_the_line_alone(view):
    panel(view).on_add()
    before = view.scene.legend[0]['color']

    with patch('PyQt6.QtWidgets.QColorDialog.exec', return_value=0):
        panel(view).rows[0].on_pick_color()
    assert view.scene.legend[0]['color'] == before


def test_a_line_can_be_removed(view):
    panel(view).on_add()
    panel(view).on_add()
    panel(view).rows[0].edit.setText('first')
    panel(view).commit()

    panel(view).remove_row(panel(view).rows[0])
    assert len(view.scene.legend) == 1
    assert view.scene.legend[0]['text'] == ''


def test_changing_the_legend_marks_the_board_unsaved(view):
    """Otherwise a legend written and then closed would be lost in
    silence."""

    view.undo_stack.setClean()
    assert view.undo_stack.isClean() is True

    panel(view).on_add()
    assert view.undo_stack.isClean() is False


def test_the_legend_can_be_undone_and_redone(view):
    panel(view).on_add()
    panel(view).rows[0].edit.setText('Approved')
    panel(view).commit()

    view.undo_stack.undo()
    assert view.scene.legend[0]['text'] == ''
    assert panel(view).rows[0].edit.text() == ''

    view.undo_stack.redo()
    assert view.scene.legend[0]['text'] == 'Approved'
    assert panel(view).rows[0].edit.text() == 'Approved'


def test_typing_a_word_is_one_step_to_undo(view):
    """Recorded when the line is left, not on every letter."""

    panel(view).on_add()
    depth = view.undo_stack.index()
    row = panel(view).rows[0]
    for text in ('A', 'Ap', 'App', 'Appr'):
        row.edit.setText(text)
    panel(view).commit()

    assert view.undo_stack.index() == depth + 1


def test_committing_nothing_new_records_nothing(view):
    panel(view).on_add()
    depth = view.undo_stack.index()
    panel(view).commit()
    assert view.undo_stack.index() == depth


def test_the_legend_is_saved_with_the_board(view, tmpdir):
    panel(view).on_add()
    panel(view).rows[0].edit.setText('Approved')
    panel(view).commit()
    view.scene.addItem(BeePixmapItem(
        QtGui.QImage(4, 4, QtGui.QImage.Format.Format_ARGB32)))

    path = os.path.join(tmpdir, 'legend.blk')
    fileio.save_bee(path, view.scene, create_new=True,
                    legend=view.scene.legend)
    saved = list(view.scene.legend)

    view.scene.set_legend([])
    fileio.load_bee(path, view.scene)
    assert view.scene.legend == saved


def test_an_emptied_legend_is_saved_as_empty(view, tmpdir):
    """Not written at all, the old lines would come back on reopening."""

    panel(view).on_add()
    view.scene.addItem(BeePixmapItem(
        QtGui.QImage(4, 4, QtGui.QImage.Format.Format_ARGB32)))
    path = os.path.join(tmpdir, 'legend.blk')
    fileio.save_bee(path, view.scene, create_new=True,
                    legend=view.scene.legend)

    view.scene.set_legend([])
    fileio.save_bee(path, view.scene, legend=view.scene.legend)
    fileio.load_bee(path, view.scene)
    assert view.scene.legend == []


def test_a_board_written_before_legends_existed_opens_without_one(
        view, tmpdir):
    view.scene.addItem(BeePixmapItem(
        QtGui.QImage(4, 4, QtGui.QImage.Format.Format_ARGB32)))
    path = os.path.join(tmpdir, 'old.blk')
    fileio.save_bee(path, view.scene, create_new=True)

    view.scene.set_legend([{'color': (1, 2, 3, 255), 'text': 'stale'}])
    fileio.load_bee(path, view.scene)
    assert view.scene.legend == []


def test_a_legend_that_will_not_parse_is_ignored(view, tmpdir):
    """A damaged entry must not stop the board from opening."""

    view.scene.addItem(BeePixmapItem(
        QtGui.QImage(4, 4, QtGui.QImage.Format.Format_ARGB32)))
    path = os.path.join(tmpdir, 'broken.blk')
    fileio.save_bee(path, view.scene, create_new=True, legend=[])

    import sqlite3
    connection = sqlite3.connect(path)
    connection.execute(
        'INSERT OR REPLACE INTO blackboard_meta (key, value) '
        'VALUES (?, ?)', ('legend', 'not json at all'))
    connection.commit()
    connection.close()

    fileio.load_bee(path, view.scene)
    assert view.scene.legend == []


def test_a_new_board_starts_without_the_old_legend(view):
    panel(view).on_add()
    view.scene.clear()
    assert view.scene.legend == []


def test_a_new_board_clears_the_panel_too(view):
    """Not just the list behind it: the old lines stayed on show."""

    panel(view).on_add()
    view.clear_scene()
    assert panel(view).rows == []


def test_a_board_opened_from_disk_shows_its_legend(view, tmpdir, qtbot):
    """A board is read on a thread of its own, and lines built from
    there never reach the panel: the colour dialog offered them, the
    panel stayed empty."""

    rows = [{'color': (25, 91, 166, 255), 'text': 'Ideas'},
            {'color': (230, 155, 34, 255), 'text': 'To do'}]
    view.scene.addItem(BeePixmapItem(
        QtGui.QImage(4, 4, QtGui.QImage.Format.Format_ARGB32)))
    path = os.path.join(tmpdir, 'legend.blk')
    # Written straight to the file, so the panel has never shown them
    fileio.save_bee(path, view.scene, create_new=True, legend=rows)

    with patch.object(view, 'on_loading_finished',
                      side_effect=view.on_loading_finished) as finished:
        view.open_from_file(path)
        view.worker.wait()
        qtbot.waitUntil(lambda: finished.called is True)
    view.legend_dock.set_collapsed(False)

    assert [row.edit.text() for row in panel(view).rows] == [
        'Ideas', 'To do']
    gui = QtGui.QGuiApplication.instance().thread()
    for row in panel(view).rows:
        assert row.thread() == gui
        assert panel(view).isAncestorOf(row)


def test_the_menu_entry_opens_and_closes_it(view):
    view.on_action_show_legend(True)
    assert view.legend_dock.collapsed is False

    view.on_action_show_legend(False)
    assert view.legend_dock.collapsed is True


def test_the_command_replaces_the_whole_legend(view):
    rows = [{'color': (1, 2, 3, 255), 'text': 'one'}]
    view.undo_stack.push(commands.ChangeLegend(view.scene, rows))
    assert view.scene.legend == rows

    view.undo_stack.undo()
    assert view.scene.legend == []
