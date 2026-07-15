# tests/ui/test_database_menu.py
"""Tests for the Database menu + Connection Setup wiring in MainWindow.

No modal/exec (the dialog is shown non-modally); no live DB. The dialog is
patched or driven by method to keep the run headless and fast.
"""
from unittest.mock import MagicMock, patch

from lxml import etree
from PySide6.QtCore import QSettings

from pgtp_editor.db.config import ConnectionParams, load_connection
from pgtp_editor.ui.main_window import MainWindow

from ._menu_helpers import find_action, find_top_menu


class _FakeProject:
    def __init__(self, tree):
        self.tree = tree


def _project_with_connection():
    tree = etree.ElementTree(
        etree.fromstring(
            b'<Project><ConnectionOptions host="th" port="2222" login="tu" '
            b'password="XXX" database="td"/></Project>'
        )
    )
    return _FakeProject(tree)


def test_database_menu_exists_with_connection_setup(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Database")
    assert menu is not None
    assert find_action(menu, "Connection Setup…") is not None


def test_open_connection_setup_seeds_from_project_and_holds_dialog(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project = _project_with_connection()

    window._open_connection_setup()

    dialog = window._connection_dialog
    assert dialog is not None
    params = dialog.params()
    assert params.host == "th"
    assert params.port == "2222"
    assert params.user == "tu"
    assert params.database == "td"
    assert params.password == ""  # never seeded from XML


def test_open_connection_setup_with_no_project(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._current_project is None

    window._open_connection_setup()  # must not crash

    assert window._connection_dialog is not None


def test_accepting_dialog_saves_connection(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)

    window._open_connection_setup()
    dialog = window._connection_dialog
    dialog.set_params(
        ConnectionParams(
            host="saved", port="5432", database="db", user="u", password="pw"
        )
    )
    dialog.accept()

    saved = load_connection(settings)
    assert saved == ConnectionParams(
        host="saved", port="5432", database="db", user="u", password="pw"
    )


def test_connection_dialog_initialised_to_none(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._connection_dialog is None
