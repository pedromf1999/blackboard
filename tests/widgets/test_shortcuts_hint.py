from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt

from beeref import constants
from beeref.widgets.shortcuts_hint import ShortcutsHint


def test_shown_on_startup(view):
    assert view.shortcuts_hint.isVisible() is True


def test_lists_the_shortcuts(view):
    keys = [keys for keys, what in ShortcutsHint.SHORTCUTS]
    assert 'Ctrl + J' in keys
    assert 'Ctrl + T' in keys
    assert 'Ctrl + G' in keys
    assert 'Alt + drag' in keys
    # Every shortcut says what it does
    assert all(what for keys, what in ShortcutsHint.SHORTCUTS)


def test_closing_hides_it(view):
    hint = view.shortcuts_hint
    hint.on_close_clicked()
    assert hint.isVisible() is False


def test_closing_does_not_stop_it_returning(view, settings):
    """Closing is for now; the checkbox is for good."""

    hint = view.shortcuts_hint
    hint.on_close_clicked()
    assert hint.wanted_on_startup() is True


def test_dont_show_again(view, settings):
    hint = view.shortcuts_hint
    hint.on_hide_changed(Qt.CheckState.Checked.value)
    assert hint.wanted_on_startup() is False

    hint.on_hide_changed(Qt.CheckState.Unchecked.value)
    assert hint.wanted_on_startup() is True


def test_not_shown_when_switched_off(view, settings):
    settings.setValue(ShortcutsHint.SETTINGS_KEY, False)
    hint = ShortcutsHint(view)
    hint.show_if_wanted()
    assert hint.isVisible() is False


def test_sits_in_the_bottom_left(view):
    view.resize(800, 600)
    hint = view.shortcuts_hint
    hint.reposition()
    assert hint.x() == hint.MARGIN
    assert hint.y() + hint.height() + hint.MARGIN == view.height()


def test_shows_the_version(view):
    """Which build this is has to be readable without opening a dialog."""

    labels = view.shortcuts_hint.findChildren(QtWidgets.QLabel)
    assert any(constants.VERSION in label.text() for label in labels)
