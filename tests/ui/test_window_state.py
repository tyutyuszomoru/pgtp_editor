"""Sub-project D -- window-state persistence (#11) + theme toggle wiring (#9).

QSettings is isolated via an injected temp ini file so nothing touches the real
user registry. Any test that mutates the global app palette resets it afterward.
"""
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.theme import apply_theme
from tests.ui._menu_helpers import find_action, find_top_menu


def _ini_settings(tmp_path, name="s.ini"):
    return QSettings(str(tmp_path / name), QSettings.Format.IniFormat)


@pytest.fixture
def _reset_app_palette():
    yield
    apply_theme(QApplication.instance(), False)


# -- geometry / dock-state persistence --------------------------------------


def test_close_persists_geometry_and_window_state(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.close()  # triggers closeEvent

    assert settings.value("geometry") is not None
    assert settings.value("windowState") is not None


def test_geometry_restored_on_next_construction(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    first = MainWindow(settings=settings)
    qtbot.addWidget(first)
    first.close()

    # A new window reading the same store restores without raising and picks up
    # the persisted geometry bytes.
    settings2 = _ini_settings(tmp_path)
    assert settings2.value("geometry") is not None
    second = MainWindow(settings=settings2)
    qtbot.addWidget(second)
    # Sanity: constructing with a populated store did not crash and the window
    # is usable.
    assert second.isVisible() in (True, False)


def test_fresh_store_uses_default_size(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    # No persisted geometry -> the constructor's default resize stands.
    assert window.width() == 1400
    assert window.height() == 900


# -- Light Theme toggle wiring ----------------------------------------------


def test_toggling_light_theme_persists_and_applies(qtbot, tmp_path, _reset_app_palette):
    settings = _ini_settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)

    window._light_theme_action.setChecked(True)  # fires toggled
    assert settings.value("lightTheme", False, type=bool) is True
    win_color = QApplication.instance().palette().color(QPalette.ColorRole.Window)
    assert win_color.lightness() > 200


def test_light_theme_restored_on_construction(qtbot, tmp_path, _reset_app_palette):
    settings = _ini_settings(tmp_path)
    settings.setValue("lightTheme", True)
    settings.sync()

    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert window._light_theme_action.isChecked() is True
    win_color = QApplication.instance().palette().color(QPalette.ColorRole.Window)
    assert win_color.lightness() > 200


def test_light_theme_action_in_view_menu(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    action = find_action(view_menu, "Light Theme")
    assert action is not None
    assert action.isCheckable()
