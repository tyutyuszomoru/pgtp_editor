"""MainWindow Light/Dark theme toggle: switches the app to Fusion + an
explicit light or dark palette either way (BUG-004: both states are real,
tested QPalettes -- there is no third "native/OS passthrough" state), keeping
the toolbar icons legible either way."""
import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.theme import dark_palette


@pytest.fixture
def _reset_app_theme():
    """Restore the app's original style + palette after each test so an
    app-global theme change here cannot leak into other tests."""
    app = QApplication.instance()
    original_style = app.style().objectName()
    original_palette = QPalette(app.palette())
    try:
        yield
    finally:
        app.setStyle(original_style)
        app.setPalette(original_palette)


def test_toggle_light_switches_to_fusion_and_keeps_icons(qtbot, _reset_app_theme):
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_light_theme_toggled(True)

    app = QApplication.instance()
    assert app.style().objectName().lower() == "fusion"
    assert app.palette().color(QPalette.ColorRole.Window).lightness() > 200
    icons = [action.icon() for action in window._toolbar.actions()]
    assert icons and all(not icon.isNull() for icon in icons)


def test_toggle_light_off_applies_real_dark_palette(qtbot, _reset_app_theme):
    """BUG-004: toggling off applies the app's own explicit dark_palette(),
    not whatever the native/OS style happened to render before Light Theme
    was ever turned on."""
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_light_theme_toggled(True)
    window._on_light_theme_toggled(False)

    app = QApplication.instance()
    assert app.style().objectName().lower() == "fusion"
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.WindowText):
        assert app.palette().color(role).rgb() == dark_palette().color(role).rgb()


def test_fresh_window_defaults_to_explicit_dark_palette(qtbot, _reset_app_theme):
    """A fresh install (no saved 'lightTheme' setting, default False) must
    start on the real dark_palette() too, not whatever the native style
    happened to already be rendering (BUG-004) -- _restore_theme applies the
    theme unconditionally now, for both True and False."""
    window = MainWindow()
    qtbot.addWidget(window)

    app = QApplication.instance()
    assert window._light_theme_action.isChecked() is False
    assert app.style().objectName().lower() == "fusion"
    assert app.palette().color(QPalette.ColorRole.Window).rgb() == dark_palette().color(
        QPalette.ColorRole.Window
    ).rgb()
