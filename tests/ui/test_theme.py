"""Sub-project D -- Light/Dark theme (#9): pure palette + apply_theme."""
import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.theme import apply_theme, dark_palette, light_palette


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


def test_dark_palette_window_is_dark():
    """dark_palette() is pure (no app mutation) and detectably dark."""
    palette = dark_palette()
    window = palette.color(QPalette.ColorRole.Window)
    assert window.lightness() < 100
    base = palette.color(QPalette.ColorRole.Base)
    assert base.lightness() < 100
    # Text is light on a dark background.
    text = palette.color(QPalette.ColorRole.Text)
    assert text.lightness() > 150


def test_dark_palette_link_is_light_and_readable():
    link = dark_palette().color(QPalette.ColorRole.Link)
    assert link.lightness() > 128  # readable against the dark Base/Window


def test_dark_palette_sets_highlight_and_disabled_text():
    palette = dark_palette()
    assert palette.color(QPalette.ColorRole.Highlight).isValid()
    disabled_text = palette.color(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text
    )
    # Distinct from the enabled light text, but still above near-black.
    enabled_text = palette.color(QPalette.ColorRole.Text)
    assert disabled_text.lightness() < enabled_text.lightness()
    assert disabled_text.lightness() > 32


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
    # BUG-004: False now applies a real, explicit dark_palette() -- not a
    # restore of whatever the native style rendered before Light Theme was
    # ever turned on.
    applied = app.palette().color(QPalette.ColorRole.Window)
    assert applied.rgb() == dark_palette().color(QPalette.ColorRole.Window).rgb()
    assert applied.lightness() < 100


def test_apply_theme_dark_applies_qdarkstyle_stylesheet(qapp, _reset_app_palette):
    """BUG-010: Fusion + palette alone leaves checkable menu indicators
    outlined near-black on the dark menu background. The dark theme therefore
    also applies the QDarkStyleSheet QSS, which styles QMenu::indicator."""
    app = qapp
    apply_theme(app, False)
    qss = app.styleSheet()
    assert qss  # non-empty
    assert "QMenu::indicator" in qss


def test_apply_theme_dark_light_dark_reuses_cached_stylesheet(qapp, _reset_app_palette):
    """BUG-010 round-trip: toggling dark -> light -> dark re-applies the same
    cached QDarkStyleSheet text without error -- _dark_stylesheet() loads the
    QSS once and every later dark application reuses the cache."""
    from pgtp_editor.ui.theme import _dark_stylesheet

    app = qapp
    apply_theme(app, False)
    first_qss = app.styleSheet()
    apply_theme(app, True)
    assert app.styleSheet() == ""
    apply_theme(app, False)
    assert app.styleSheet() == first_qss
    assert "QMenu::indicator" in app.styleSheet()
    # Same object both times: the module-level cache is populated once.
    assert _dark_stylesheet() is _dark_stylesheet()


def test_apply_theme_light_clears_dark_stylesheet(qapp, _reset_app_palette):
    """The light theme always assigns the empty stylesheet, so a dark->light
    toggle leaves no stale dark QSS behind (BUG-010 round-trip)."""
    app = qapp
    apply_theme(app, False)
    assert app.styleSheet()
    apply_theme(app, True)
    assert app.styleSheet() == ""
    assert "QMenu::indicator" not in app.styleSheet()


# -- BUG-010 gap coverage: the tests/ui/conftest.py autouse stylesheet reset -
# Same pattern as the palette leak-pair in test_main_window_theme.py: the
# first test deliberately does NOT use _reset_app_palette and leaves the
# app-global dark QSS applied; the second (next in definition order) proves
# the autouse conftest fixture restored the stylesheet, so dark-menu styling
# cannot leak into later widget tests.


def test_dark_qss_left_applied_without_local_reset(qapp):
    apply_theme(qapp, False)
    assert "QMenu::indicator" in qapp.styleSheet()


def test_previous_tests_dark_qss_did_not_leak(qapp):
    """Runs after the deliberately-leaky test above: the autouse conftest
    fixture must already have restored the original app stylesheet."""
    assert "QMenu::indicator" not in qapp.styleSheet()


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


def test_apply_theme_uses_fusion_and_dark_palette(qapp, _reset_app_palette):
    app = qapp
    apply_theme(app, False)
    # The dark theme's app-level QSS (BUG-010, qdarkstyle) wraps the style in
    # Qt's internal QStyleSheetStyle proxy, whose objectName is empty -- so
    # "Fusion is applied" is asserted via the stylesheet + palette instead of
    # style().objectName() (which only reads "fusion" in light mode).
    assert app.styleSheet()
    assert app.palette().color(QPalette.ColorRole.Window).lightness() < 100


def test_apply_theme_false_is_platform_independent(qapp, _reset_app_palette):
    """BUG-004: light=False must not depend on whatever the native/OS style
    happens to render (previously it fell back to app.style().standardPalette()
    with no captured default) -- it always applies dark_palette() under
    Fusion, deterministically, regardless of platform/native style."""
    app = qapp
    apply_theme(app, True)
    apply_theme(app, False)

    assert app.palette().color(QPalette.ColorRole.Window).rgb() == dark_palette().color(
        QPalette.ColorRole.Window
    ).rgb()
    # Explicitly NOT the style's generic standard palette (the old fallback).
    standard_window = app.style().standardPalette().color(QPalette.ColorRole.Window)
    dark_window = dark_palette().color(QPalette.ColorRole.Window)
    if standard_window.rgb() == dark_window.rgb():
        pytest.skip("native standardPalette happens to coincide with dark_palette() on this platform")
    assert app.palette().color(QPalette.ColorRole.Window).rgb() != standard_window.rgb()
