"""MainWindow Light/Dark theme toggle: switches the app to Fusion + light
palette on, and restores the captured original style + palette on off, keeping
the toolbar icons legible either way."""
import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.main_window import MainWindow


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


def test_toggle_light_off_restores_captured_style_and_palette(
    qtbot, _reset_app_theme
):
    window = MainWindow()
    qtbot.addWidget(window)
    captured_palette = window._default_palette
    captured_style = window._default_style_key

    window._on_light_theme_toggled(True)
    window._on_light_theme_toggled(False)

    app = QApplication.instance()
    assert app.style().objectName() == captured_style
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.WindowText):
        assert app.palette().color(role).rgb() == captured_palette.color(role).rgb()
