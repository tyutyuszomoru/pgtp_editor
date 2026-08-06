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
    """BUG-010 round-trip, extended for the light QSS: toggling
    dark -> light -> dark re-applies the SAME cached QDarkStyleSheet text for
    each theme without error -- _qdarkstyle_stylesheet(light) loads each
    variant once and every later application of that theme reuses its cache
    entry. Light and dark are symmetric: both are non-empty, both contain
    "QMenu::indicator" (it's a full-widget stylesheet either way, not a
    dark-exclusive rule -- confirmed below by checking the actual QSS text),
    and they are genuinely different QSS strings from each other."""
    from pgtp_editor.ui.theme import _qdarkstyle_stylesheet

    app = qapp
    apply_theme(app, False)
    first_dark_qss = app.styleSheet()
    assert first_dark_qss
    assert "QMenu::indicator" in first_dark_qss

    apply_theme(app, True)
    first_light_qss = app.styleSheet()
    assert first_light_qss
    assert "QMenu::indicator" in first_light_qss
    assert first_light_qss != first_dark_qss

    apply_theme(app, False)
    assert app.styleSheet() == first_dark_qss

    apply_theme(app, True)
    assert app.styleSheet() == first_light_qss

    # Same object every time per theme: the module-level cache dict is
    # populated once per key, not reloaded on every apply_theme() call.
    assert _qdarkstyle_stylesheet(True) is _qdarkstyle_stylesheet(True)
    assert _qdarkstyle_stylesheet(False) is _qdarkstyle_stylesheet(False)
    assert _qdarkstyle_stylesheet(True) is not _qdarkstyle_stylesheet(False)


def test_apply_theme_light_and_dark_get_distinct_qdarkstyle_stylesheets(qapp, _reset_app_palette):
    """Light and dark are now symmetric (no more "light theme has no
    stylesheet" special case): each gets its own real, non-empty QSS, and
    toggling between them replaces one with the other cleanly -- no light QSS
    text leaks into the dark stylesheet or vice versa. Verified via
    palette-specific hex markers baked into each QSS variant
    (qdarkstyle.dark.palette.DarkPalette.COLOR_ACCENT_1 appears only in the
    dark QSS; qdarkstyle.light.palette.LightPalette.COLOR_BACKGROUND_1
    appears only in the light one) rather than mere non-emptiness, to prove
    which palette's stylesheet is actually active."""
    from qdarkstyle.dark.palette import DarkPalette
    from qdarkstyle.light.palette import LightPalette

    app = qapp

    apply_theme(app, False)
    dark_qss = app.styleSheet()
    assert dark_qss
    assert DarkPalette.COLOR_ACCENT_1 in dark_qss
    assert LightPalette.COLOR_BACKGROUND_1 not in dark_qss

    apply_theme(app, True)
    light_qss = app.styleSheet()
    assert light_qss
    assert LightPalette.COLOR_BACKGROUND_1 in light_qss
    assert DarkPalette.COLOR_ACCENT_1 not in light_qss
    assert light_qss != dark_qss

    # Toggle back: the dark-specific marker returns and the light one is gone
    # again -- no cross-contamination from caching both variants.
    apply_theme(app, False)
    assert DarkPalette.COLOR_ACCENT_1 in app.styleSheet()
    assert LightPalette.COLOR_BACKGROUND_1 not in app.styleSheet()


def test_apply_theme_light_keeps_hand_rolled_palette_under_the_qss(qapp, _reset_app_palette):
    """FQ-005 made the light theme carry a qdarkstyle QSS, but the QPalette
    source stays hand-rolled for BOTH themes: applying the light QSS must not
    replace/override light_palette()'s roles, because palette-reading custom
    widgets (XmlEditor.apply_theme_colors keys off its palette's Base
    lightness) would otherwise disagree with the stylesheet's look. Asserted
    by exact rgb, symmetric with the dark-side assertions."""
    app = qapp
    expected = light_palette()
    apply_theme(app, True)

    assert app.styleSheet()  # the light QSS really is applied ...
    for role in (
        QPalette.ColorRole.Window,
        QPalette.ColorRole.Base,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.Link,
    ):
        # ... and the hand-rolled light palette is still what the app reports.
        assert app.palette().color(role).rgb() == expected.color(role).rgb(), role


def test_qss_cache_holds_one_entry_per_theme(qapp, _reset_app_palette):
    """The BUG-010 single-string cache became a per-theme dict (FQ-005): both
    variants coexist, keyed by the `light` bool, so neither toggle direction
    evicts or reloads the other's QSS."""
    from pgtp_editor.ui import theme as theme_mod

    apply_theme(qapp, False)
    apply_theme(qapp, True)

    assert set(theme_mod._qss_cache) == {True, False}
    assert theme_mod._qss_cache[True] and theme_mod._qss_cache[False]
    assert theme_mod._qss_cache[True] != theme_mod._qss_cache[False]


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


def test_apply_theme_uses_fusion_and_light_palette(qapp, _reset_app_palette, monkeypatch):
    """Fusion is genuinely requested via app.setStyle("Fusion") -- but reading
    it back via app.style().objectName() afterwards is unreliable now that
    the light theme also applies a non-empty app-global stylesheet (like dark
    already did): Qt wraps ANY styled app in an internal QStyleSheetStyle
    proxy whose objectName() is "" regardless of the underlying style name.
    Confirmed live: this already happened for the dark theme before this
    change (see test_apply_theme_uses_fusion_and_dark_palette below) -- it
    was simply never asserted for light because light previously carried no
    stylesheet at all. Spy on QApplication.setStyle instead of reading back
    style().objectName() post-stylesheet."""
    app = qapp
    calls = []
    # Patch the CLASS, not the instance: patching an instance attribute on the
    # QApplication singleton (`app.setStyle = ...`) leaves shiboken's method
    # resolution for that PySide6 wrapped slot broken even after monkeypatch
    # deletes the shadowing instance attribute on teardown -- confirmed by
    # reproducing a leak into a later test file (test_main_window_theme.py)
    # when patched this way; class-level patching does not have this problem.
    monkeypatch.setattr(QApplication, "setStyle", lambda self, name: calls.append(name))
    apply_theme(app, True)
    assert calls == ["Fusion"]
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
