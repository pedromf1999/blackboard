import os.path
import pytest
import uuid

from unittest.mock import MagicMock, patch

from PyQt6 import QtGui, QtWidgets


def pytest_configure(config):
    # Ignore logging configuration for BeeRef during test runs. This
    # avoids logging to the regular log file and spamming test output
    # with debug messages.
    #
    # This needs to be done before the application code is even loaded since
    # logging configuration happens on module level
    import logging.config
    logging.config.dictConfig = MagicMock


@pytest.fixture(autouse=True)
def reset_beeref_actions():
    from beeref.actions.actions import actions
    for key in list(actions.keys()):
        if key.startswith('recent_files_'):
            actions.pop(key)


@pytest.fixture(autouse=True)
def commandline_args():
    config_patcher = patch('beeref.view.commandline_args')
    config_mock = config_patcher.start()
    config_mock.filenames = []
    yield config_mock
    config_patcher.stop()


@pytest.fixture(autouse=True)
def settings(tmpdir):
    from beeref.config import BeeSettings
    dir_patcher = patch('beeref.config.BeeSettings.get_settings_dir',
                        return_value=tmpdir.dirname)
    dir_patcher.start()
    settings = BeeSettings()
    yield settings
    settings.clear()
    dir_patcher.stop()


@pytest.fixture(autouse=True)
def kbsettings(tmpdir):
    from beeref.config import KeyboardSettings
    dir_patcher = patch('beeref.config.BeeSettings.get_settings_dir',
                        return_value=tmpdir.dirname)
    dir_patcher.start()
    kbsettings = KeyboardSettings()
    yield kbsettings
    kbsettings.clear()
    dir_patcher.stop()


def forget_unsaved_changes(window):
    """Let the test's window close without offering to save.

    Closing a board with unsaved changes asks what to do with them, and
    a test has nobody to answer it: the run stops dead on a dialog.

    Answered here rather than by tidying the undo stack. Marking the
    stack clean is not enough on its own -- a test that mocks out what
    ends an undo macro leaves the stack inside one, and Qt ignores
    setClean() there.
    """

    window.view.get_confirmation_unsaved_changes = lambda *args: True


@pytest.fixture
def main_window(qtbot):
    from beeref.__main__ import BeeRefMainWindow
    app = QtWidgets.QApplication.instance()
    main = BeeRefMainWindow(app)
    qtbot.addWidget(main, before_close_func=forget_unsaved_changes)
    yield main


@pytest.fixture
def view(main_window):
    yield main_window.view


@pytest.fixture
def imgfilename3x3():
    root = os.path.dirname(__file__)
    yield os.path.join(root, 'assets', 'test3x3.png')


@pytest.fixture
def imgdata3x3(imgfilename3x3):
    with open(imgfilename3x3, 'rb') as f:
        imgdata3x3 = f.read()
    yield imgdata3x3


@pytest.fixture
def tmpfile(tmpdir):
    yield os.path.join(tmpdir, str(uuid.uuid4()))


@pytest.fixture
def item():
    from beeref.items import BeePixmapItem
    yield BeePixmapItem(QtGui.QImage(10, 10, QtGui.QImage.Format.Format_RGB32))


@pytest.fixture(scope="session")
def qapp():
    from beeref.__main__ import BeeRefApplication
    yield BeeRefApplication([])


@pytest.fixture(autouse=True)
def no_unattended_dialogs():
    """Turn a modal dialog nobody can answer into a plain failure.

    A question box in a test run blocks it for ever: the run sits there
    until somebody notices and clicks. Failing says which test did it,
    and costs nobody a click. A test that means to open one patches it
    itself, and that patch goes on top of this one.
    """

    def refuse(parent, title, *args, **kwargs):
        raise AssertionError(
            f'unattended modal dialog: {title!r}. Patch it in the test, '
            'or leave the board in a state that does not ask.')

    with patch('PyQt6.QtWidgets.QMessageBox.question', refuse):
        yield
