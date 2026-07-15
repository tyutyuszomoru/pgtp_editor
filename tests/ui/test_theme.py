"""Sub-project D -- Light/Dark theme (#9): pure palette + apply_theme."""
import pytest
from PySide6.QtGui import QColor, QPalette
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
    """Restore the app's original style + palette after a test that mutates
    either, so app-global theme changes cannot leak into later tests (e.g. a
    default-size or default-palette assertion elsewhere)."""
    original_style = qapp.style().objectName()
    original_palette = QPalette(qapp.palette())
    try:
        yield
    finally:
        qapp.setStyle(original_style)
        qapp.setPalette(original_palette)


def test_apply_theme_true_then_false_round_trip(qapp, _reset_app_palette):
    app = qapp
    apply_theme(app, True)
    window = app.palette().color(QPalette.ColorRole.Window)
    assert window.lightness() > 200

    apply_theme(app, False)
    restored = app.palette().color(QPalette.ColorRole.Window)
    default = app.style().standardPalette().color(QPalette.ColorRole.Window)
    assert restored.rgb() == default.rgb()


def test_light_palette_link_is_navy():
    """The About-box hyperlink color (Link role) is a dark navy blue, not the
    dark-theme cyan -- blue channel dominant and dark enough to read on white."""
    link = light_palette().color(QPalette.ColorRole.Link)
    assert link.lightness() < 128
    assert link.blue() > link.red()
    assert link.blue() > link.green()


def test_light_palette_sets_highlight_and_disabled_text():
    palette = light_palette()
    # A highlight color is set (non-default; a visible selection band).
    assert palette.color(QPalette.ColorRole.Highlight).isValid()
    # Disabled text is a mid-gray, distinct from the enabled dark text.
    disabled_text = palette.color(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text
    )
    assert 96 < disabled_text.lightness() < 200


def test_apply_theme_uses_fusion_and_light_palette(qapp, _reset_app_palette):
    app = qapp
    apply_theme(app, True)
    assert app.style().objectName().lower() == "fusion"
    assert app.palette().color(QPalette.ColorRole.Window).lightness() > 200


def test_apply_theme_false_restores_captured_palette_exactly(qapp, _reset_app_palette):
    """With a captured default palette + style provided, light=False restores
    THAT palette exactly rather than falling back to standardPalette."""
    app = qapp
    captured = QPalette(app.palette())
    captured.setColor(QPalette.ColorRole.Window, QColor(0x11, 0x22, 0x33))
    captured.setColor(QPalette.ColorRole.WindowText, QColor(0xAA, 0xBB, 0xCC))

    apply_theme(app, True)
    apply_theme(app, False, default_palette=captured, default_style="fusion")

    assert app.palette().color(QPalette.ColorRole.Window).rgb() == QColor(
        0x11, 0x22, 0x33
    ).rgb()
    assert app.palette().color(QPalette.ColorRole.WindowText).rgb() == QColor(
        0xAA, 0xBB, 0xCC
    ).rgb()
    # Prove it did NOT fall back to the style's generic standard palette.
    standard_window = app.style().standardPalette().color(QPalette.ColorRole.Window)
    assert app.palette().color(QPalette.ColorRole.Window).rgb() != standard_window.rgb()
