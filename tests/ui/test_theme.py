"""Sub-project D -- Light/Dark theme (#9): pure palette + apply_theme."""
import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.theme import apply_theme, light_palette


def test_light_palette_window_is_light():
    """light_palette() is pure (no app mutation) and detectably light."""
    palette = light_palette()
    window = palette.color(QPalette.ColorRole.Window)
    assert window.lightness() > 200
    base = palette.color(QPalette.ColorRole.Base)
    assert base.lightness() > 200
    # Text is dark on a light background.
    text = palette.color(QPalette.ColorRole.Text)
    assert text.lightness() < 128


@pytest.fixture
def _reset_app_palette(qapp):
    """Restore the default app palette after a test that mutates it."""
    yield
    apply_theme(qapp, False)


def test_apply_theme_true_then_false_round_trip(qapp, _reset_app_palette):
    app = qapp
    apply_theme(app, True)
    window = app.palette().color(QPalette.ColorRole.Window)
    assert window.lightness() > 200

    apply_theme(app, False)
    restored = app.palette().color(QPalette.ColorRole.Window)
    default = app.style().standardPalette().color(QPalette.ColorRole.Window)
    assert restored.rgb() == default.rgb()
