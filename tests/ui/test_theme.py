"""Sub-project D -- Light/Dark theme (#9): pure palette + apply_theme."""
import pytest
from PySide6.QtCore import Qt
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
    variants coexist, so neither toggle direction evicts or reloads the other's
    QSS.

    The KEY changed with FQ-260812021716, and deliberately: it was the `light`
    bool, which cannot tell two dark themes apart, so an edited or duplicated
    theme would have been served the other one's stylesheet. It is now
    `_qss_key(theme)` — the qdarkstyle base plus the 16 chrome colours, i.e.
    exactly the inputs the sheet is a function of."""
    from pgtp_editor.ui import theme as theme_mod
    from pgtp_editor.ui.theme_model import theme_for

    apply_theme(qapp, False)
    apply_theme(qapp, True)

    dark_key = theme_mod._qss_key(theme_for(False))
    light_key = theme_mod._qss_key(theme_for(True))
    assert dark_key != light_key
    assert {dark_key, light_key} <= set(theme_mod._qss_cache)
    assert theme_mod._qss_cache[dark_key] and theme_mod._qss_cache[light_key]
    assert theme_mod._qss_cache[dark_key] != theme_mod._qss_cache[light_key]


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


# -- BUG-260812002838: keyboard focus must be VISIBLE on buttons -------------
# These sample `grab().toImage()` rather than asserting on the stylesheet text,
# for the reason `tests/ui/test_sql_results_panel.py` records at length: a
# stylesheet assertion proves the string, not the paint, and that is the class
# of false green that let BUG-260811021804 ship. A `"QPushButton:focus" in
# app.styleSheet()` test would pass just as happily against a rule Qt silently
# refuses to apply -- and while writing this fix the rule DID render while a
# naive whole-image colour count read as "nothing changed", because the ring
# colour and the button label are the same colour. Sample the ring.
#
# BUG-260812004649 extends the same block to QTabBar, and the sampling trap
# above bit a second time there in the opposite direction: the tab-bar ring and
# the tab LABEL are both COLOR_TEXT_1, so a whole-image count of that colour
# moved 27 -> 132 on focus -- a number that reads as a pass, driven mostly by
# the label being repainted. Sample the specific pane-facing edge pixel of a
# specific tab (`tabRect(i).bottom() - 1`), inset from the 4px corner radius.


def _ring_pixel(button) -> str:
    """The colour Qt actually paints at the middle of `button`'s top edge --
    where the 2px focus border lives when the button has focus, and where the
    plain button background is when it does not. Lower-case `#rrggbb`, the way
    `QImage.pixelColor().name()` spells it (the qdarkstyle palette literals are
    UPPER case, so a raw comparison against them never matches)."""
    image = button.grab().toImage()
    return image.pixelColor(button.width() // 2, 0).name()


def _focus_ring_colour(light: bool) -> str:
    """What the ring is *supposed* to be, read from the same qdarkstyle palette
    the implementation reads -- not a second copy of the literal."""
    from qdarkstyle.dark.palette import DarkPalette
    from qdarkstyle.light.palette import LightPalette

    return QColor((LightPalette if light else DarkPalette).COLOR_TEXT_1).name()


def _contrast(one: str, two: str) -> float:
    """WCAG 2.x relative-luminance contrast ratio between two `#rrggbb`."""

    def luminance(hex_colour: str) -> float:
        colour = QColor(hex_colour)
        channels = []
        for raw in (colour.redF(), colour.greenF(), colour.blueF()):
            channels.append(
                raw / 12.92 if raw <= 0.03928 else ((raw + 0.055) / 1.055) ** 2.4
            )
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    high, low = sorted((luminance(one), luminance(two)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.fixture
def focus_row(qtbot, qapp, _reset_app_palette):
    """Two shown QPushButtons under a real theme. Showing is not optional: an
    unshown widget's grab is not evidence, the app-wide QSS is only resolved
    once the widget is polished, and `hasFocus()` needs a top level that has
    been `show()`n."""
    from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

    def build(light: bool):
        apply_theme(qapp, light)
        host = QWidget()
        qtbot.addWidget(host)
        row = QHBoxLayout(host)
        first, second = QPushButton("Find Next"), QPushButton("Find All")
        row.addWidget(first)
        row.addWidget(second)
        host.show()
        qapp.processEvents()
        return host, first, second

    return build


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_a_focused_button_paints_a_visible_ring(focus_row, qapp, light):
    """The report itself: Tab onto a button and nothing happens. qdarkstyle
    styles `QPushButton:hover` but ships no `:focus` rule, and its
    `outline: none` kills Qt's native focus rectangle."""
    _host, first, _second = focus_row(light)
    first.setFocus()
    qapp.processEvents()
    assert first.hasFocus()
    assert _ring_pixel(first) == _focus_ring_colour(light)


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_an_unfocused_button_paints_no_ring(focus_row, qapp, light):
    """The absence half -- anchored by the presence half in the SAME sampler
    and the SAME render, so it cannot pass by the probe being blind: `first`
    below proves the ring colour is reachable at this pixel at this moment."""
    _host, first, second = focus_row(light)
    first.setFocus()
    qapp.processEvents()
    assert _ring_pixel(first) == _focus_ring_colour(light)  # the anchor
    assert not second.hasFocus()
    assert _ring_pixel(second) != _focus_ring_colour(light)


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_ring_follows_focus_from_one_button_to_the_next(focus_row, qapp, light):
    """Tabbing on: exactly one button wears the ring at a time."""
    _host, first, second = focus_row(light)
    ring = _focus_ring_colour(light)

    first.setFocus()
    qapp.processEvents()
    assert _ring_pixel(first) == ring
    assert _ring_pixel(second) != ring

    second.setFocus()
    qapp.processEvents()
    assert _ring_pixel(second) == ring
    assert _ring_pixel(first) != ring


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_focus_does_not_move_the_button(focus_row, qapp, light):
    """The base rule is `padding: 2px; border: none` and the focus rule is
    `padding: 0px; border: 2px` -- 2px of box either way, so gaining focus
    cannot resize the button or jitter the row it sits in."""
    _host, first, _second = focus_row(light)
    resting = first.size()
    first.setFocus()
    qapp.processEvents()
    assert first.size() == resting


def test_the_ring_survives_a_theme_flip(focus_row, qapp):
    """A flip re-applies the whole app stylesheet, so the ring must come back
    in the NEW theme's colour -- and the rule must not be appended twice.
    (`apply_theme` builds the combined text once per theme and caches it; an
    implementation that concatenated the tail on every call would compound,
    and the four PaletteChange events a flip fires would make that worse.)"""
    _host, first, _second = focus_row(False)
    first.setFocus()
    qapp.processEvents()
    assert _ring_pixel(first) == _focus_ring_colour(False)

    apply_theme(qapp, True)
    apply_theme(qapp, False)
    apply_theme(qapp, True)
    qapp.processEvents()
    assert _ring_pixel(first) == _focus_ring_colour(True)
    assert qapp.styleSheet().count("QPushButton:focus") == 1


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_ring_clears_3_to_1_against_the_button_in_both_themes(light):
    """Two hardcoded status colours in this app previously measured 2.96:1 and
    2.74:1, each failing 3:1 in exactly one theme -- so the indicator is
    measured, not eyeballed, against BOTH the resting and the hover button
    background.

    This is why the ring is NOT `COLOR_ACCENT_3`, which the bug entry proposed
    so it would match qdarkstyle's own `QLineEdit:focus` border: that accent is
    picked to read against an *input* background and against a *button* it
    measures 1.56:1 dark / 1.06:1 light -- invisible, i.e. the same bug with
    extra steps."""
    from qdarkstyle.dark.palette import DarkPalette
    from qdarkstyle.light.palette import LightPalette

    palette = LightPalette if light else DarkPalette
    ring = _focus_ring_colour(light)
    resting = QColor(palette.COLOR_BACKGROUND_4).name()  # QPushButton background
    hovered = QColor(palette.COLOR_BACKGROUND_5).name()  # QPushButton:hover
    assert _contrast(ring, resting) >= 3.0
    assert _contrast(ring, hovered) >= 3.0
    # ... and the rejected accent really does fail, so this test is not vacuous.
    assert _contrast(QColor(palette.COLOR_ACCENT_3).name(), resting) < 3.0


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_tool_buttons_get_the_same_ring(qtbot, qapp, _reset_app_palette, light):
    """QToolButton carries the identical defect from the identical qdarkstyle
    shape (`padding: 2px; outline: none; border: none`, a `:hover` rule, no
    `:focus`), so it rides the same single rule rather than a second one."""
    from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

    apply_theme(qapp, light)
    host = QWidget()
    qtbot.addWidget(host)
    row = QHBoxLayout(host)
    first, second = QToolButton(), QToolButton()
    first.setText("Run")
    second.setText("Stop")
    for button in (first, second):
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        row.addWidget(button)
    host.show()
    qapp.processEvents()

    first.setFocus()
    qapp.processEvents()
    assert _ring_pixel(first) == _focus_ring_colour(light)
    assert _ring_pixel(second) != _focus_ring_colour(light)


# -- BUG-260812004649: keyboard focus must be VISIBLE on tab bars too --------
# Same defect class, same file, same colour precedent as the buttons above --
# qdarkstyle ships no `:focus` selector for `QTabBar::tab` at all, so a focused
# tab bar and an unfocused one paint identically and nothing tells the user the
# arrow keys are now live. `focusNextPrevChild` lands on a QTabBar three times
# per traversal cycle on a real MainWindow, so this is the plain Tab key.
#
# The ORIGINAL report asked for a "focused but unselected tab" cue. There is no
# such state: QTabBar takes focus as a whole widget and Qt sets State_HasFocus
# on the CURRENT tab's style option only. `test_focus_never_reaches_an_...`
# below pins that, because it is the reason the rule is `:selected:focus` --
# which is also the only form specific enough to beat qdarkstyle's
# `:top:selected`. A bare `QTabBar::tab:focus` paints 0px here while passing any
# stylesheet-string test.


def _tab_edge_colours(bar, index: int) -> list[str]:
    """The colours painted along the pane-facing (bottom) edge of tab `index`
    of a `RoundedNorth` bar -- the 3px border qdarkstyle's `:selected` rule
    draws in its accent and the focus rule recolours.

    Sampled at `tabRect().bottom() - 1`, inset 8px from either end so the 4px
    corner radius is never in the sample. Deliberately NOT a whole-image colour
    count -- see the block comment at the top of this section.

    The row is CLAMPED to the render, and that is not defensive padding.
    `QTabBar` recomputes its tab layout one pass behind its own widget geometry
    after a stylesheet change (qdarkstyle's light tabs are 27px tall against
    dark's 25px), and the two never re-converge -- forcing a relayout merely
    alternates which of them is stale. Painting follows `tabRect`, so after a
    theme flip the border is either clipped off the bottom of the render or sits
    a couple of rows above it; clamping lands inside the 3px border in both
    cases as well as in the aligned one."""
    image = bar.grab().toImage()
    rect = bar.tabRect(index)
    y = min(rect.bottom() - 1, image.height() - 1)
    return [
        image.pixelColor(x, y).name()
        for x in range(rect.left() + 8, rect.right() - 8)
    ]


def _selected_tab_background(light: bool) -> str:
    """qdarkstyle's `QTabBar::tab:selected` background -- what the ring has to
    read against where it is actually drawn."""
    from qdarkstyle.dark.palette import DarkPalette
    from qdarkstyle.light.palette import LightPalette

    return QColor((LightPalette if light else DarkPalette).COLOR_BACKGROUND_5).name()


def _tab_selection_accent(light: bool) -> str:
    """qdarkstyle's own selected-tab border accent -- the colour the edge wears
    when the bar is NOT focused. Used as the presence anchor: it proves the
    sampler is looking at the border at all."""
    from qdarkstyle.dark.palette import DarkPalette
    from qdarkstyle.light.palette import LightPalette

    return QColor((LightPalette if light else DarkPalette).COLOR_ACCENT_4).name()


@pytest.fixture
def focus_tabs(qtbot, qapp, _reset_app_palette):
    """A shown QTabWidget with three tabs under a real theme, current index 1,
    and its bar explicitly UNFOCUSED.

    `clearFocus()` is not tidiness: showing a QTabWidget whose only focusable
    child is its bar hands the bar focus immediately, so an "unfocused"
    baseline taken straight after `show()` is silently a FOCUSED one -- which
    made the first run of these tests report the ring present in both states.
    `show()` is equally mandatory: the app-wide QSS is only resolved on polish
    and an unshown grab is not evidence."""
    from PySide6.QtWidgets import QTabWidget, QWidget

    def build(light: bool):
        apply_theme(qapp, light)
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        for index in range(3):
            tabs.addTab(QWidget(), f"Tab {index}")
        tabs.setCurrentIndex(1)
        tabs.resize(400, 200)
        tabs.show()
        qapp.processEvents()
        bar = tabs.tabBar()
        bar.clearFocus()
        qapp.processEvents()
        assert not bar.hasFocus()
        return tabs, bar

    return build


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_a_focused_tab_bar_paints_a_visible_ring(focus_tabs, qapp, light):
    """The real defect: Tab-traverse into a tab bar and the screen does not
    change, so nothing says the arrow keys now switch tabs."""
    _tabs, bar = focus_tabs(light)
    bar.setFocus()
    qapp.processEvents()
    assert bar.hasFocus()
    assert _focus_ring_colour(light) in _tab_edge_colours(bar, 1)


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_an_unfocused_tab_bar_paints_no_ring(focus_tabs, qapp, light):
    """The absence half, anchored by a presence assertion in the SAME sampler:
    the edge really is being sampled, because qdarkstyle's own selection accent
    is found there. Without that anchor this test would pass just as happily
    against a sampler pointed at empty background."""
    _tabs, bar = focus_tabs(light)
    resting = _tab_edge_colours(bar, 1)
    assert _tab_selection_accent(light) in resting  # the anchor
    assert _focus_ring_colour(light) not in resting


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_focus_never_reaches_an_unselected_tab(focus_tabs, qapp, light):
    """Pins the measured fact that disproved the original report: with the bar
    focused, an UNSELECTED tab's edge carries no ring, because Qt never sets
    State_HasFocus on it. Anchored on tab 1 in the same render."""
    _tabs, bar = focus_tabs(light)
    bar.setFocus()
    qapp.processEvents()
    ring = _focus_ring_colour(light)
    assert ring in _tab_edge_colours(bar, 1)  # the anchor
    assert ring not in _tab_edge_colours(bar, 0)
    assert ring not in _tab_edge_colours(bar, 2)


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_focus_does_not_move_the_tab(focus_tabs, qapp, light):
    """The exclusion ground that kept tabs out of the button fix, and the
    assertion that must never be dropped. The rule recolours the 3px border
    qdarkstyle ALREADY draws rather than adding a box: a naive
    `border: 2px solid` takes tabs from 37px to 41px wide and shifts every
    following tab, and `padding: 0` (the compensation that worked for buttons)
    overshoots to 33px, because tab padding is per-edge and asymmetric."""
    _tabs, bar = focus_tabs(light)
    resting = [bar.tabRect(i) for i in range(3)]
    bar.setFocus()
    qapp.processEvents()
    assert [bar.tabRect(i) for i in range(3)] == resting


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_tab_ring_clears_3_to_1_in_both_themes(light):
    """Measured against the backgrounds the ring is actually drawn between --
    the selected tab it borders and the unselected neighbours beside it -- not
    eyeballed. `COLOR_ACCENT_3` is asserted to FAIL so the colour rejected on
    the buttons cannot be quietly re-proposed here (1.15:1 / 1.08:1)."""
    from qdarkstyle.dark.palette import DarkPalette
    from qdarkstyle.light.palette import LightPalette

    palette = LightPalette if light else DarkPalette
    ring = _focus_ring_colour(light)
    selected = _selected_tab_background(light)
    unselected = QColor(palette.COLOR_BACKGROUND_4).name()
    assert _contrast(ring, selected) >= 3.0
    assert _contrast(ring, unselected) >= 3.0
    assert _contrast(QColor(palette.COLOR_ACCENT_3).name(), selected) < 3.0


def test_the_tab_ring_survives_a_theme_flip(focus_tabs, qapp):
    """Same invariant as the button ring: the tail is folded into the CACHED
    per-theme string, so repeated flips must not compound it -- each of the four
    per-edge selectors appears exactly once."""
    from pgtp_editor.ui.theme import FOCUS_TAB_EDGES, focus_tab_selector

    _tabs, bar = focus_tabs(False)
    bar.setFocus()
    qapp.processEvents()
    assert _focus_ring_colour(False) in _tab_edge_colours(bar, 1)

    apply_theme(qapp, True)
    apply_theme(qapp, False)
    apply_theme(qapp, True)
    qapp.processEvents()
    assert _focus_ring_colour(True) in _tab_edge_colours(bar, 1)
    for edge in FOCUS_TAB_EDGES:
        assert qapp.styleSheet().count(focus_tab_selector(edge)) == 1
    assert qapp.styleSheet().count("QPushButton:focus") == 1


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_a_SOUTH_tab_bars_ring_is_PAINTED_not_merely_declared(qtbot, qapp,
                                                              _reset_app_palette,
                                                              light):
    """The `:bottom` rule, in rendered pixels rather than in the stylesheet text.

    `test_every_edge_gets_a_rule_on_its_pane_facing_side` below checks all four
    edges by reading the QSS string — which is precisely the assertion shape
    that let this bug class ship twice: a bare `QTabBar::tab:focus` paints 0px
    while passing any string test, and a rule Qt silently refuses to apply reads
    identically to one it honours. Only `top` is proven in pixels above, and
    `bottom` is not a hypothetical edge: Qt gives a tabified-QDockWidget bar a
    South shape, which the docstring on `focus_tab_selector` names as the reason
    the rule exists at all.

    A South bar's pane-facing edge is its TOP, so the sampler is the mirror of
    `_tab_edge_colours` — same clamping rationale, opposite side.
    """
    from PySide6.QtWidgets import QTabWidget, QWidget

    apply_theme(qapp, light)
    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    tabs.setTabPosition(QTabWidget.TabPosition.South)
    for index in range(3):
        tabs.addTab(QWidget(), f"Tab {index}")
    tabs.setCurrentIndex(1)
    tabs.resize(400, 200)
    tabs.show()
    qapp.processEvents()
    bar = tabs.tabBar()
    bar.clearFocus()
    qapp.processEvents()
    assert not bar.hasFocus()  # showing hands the only focusable child focus

    def top_edge_colours() -> list[str]:
        image = bar.grab().toImage()
        rect = bar.tabRect(1)
        y = max(rect.top() + 1, 0)
        return [
            image.pixelColor(x, y).name()
            for x in range(rect.left() + 8, rect.right() - 8)
        ]

    ring = _focus_ring_colour(light)
    resting = top_edge_colours()
    resting_rects = [bar.tabRect(i) for i in range(3)]
    assert _tab_selection_accent(light) in resting  # the presence anchor
    assert ring not in resting

    bar.setFocus()
    qapp.processEvents()
    assert bar.hasFocus()
    assert ring in top_edge_colours()
    # ...and the geometry did not move, the exclusion ground for the whole fix.
    assert [bar.tabRect(i) for i in range(3)] == resting_rects


def test_every_edge_gets_a_rule_on_its_pane_facing_side(qapp, _reset_app_palette):
    """All four edges are covered even though the app calls `setTabPosition`
    nowhere: Qt gives a tabified-QDockWidget bar a SOUTH shape, which a user can
    create by dragging docks together, and a future vertical bar would silently
    lose the cue. Each rule sets exactly ONE `border-<side>` -- the side facing
    the pane -- and no `border` shorthand, `padding`, `margin` or `outline`,
    which is what keeps the geometry fixed."""
    from pgtp_editor.ui.theme import FOCUS_TAB_EDGES, focus_tab_selector

    apply_theme(qapp, False)
    sheet = qapp.styleSheet()
    assert set(FOCUS_TAB_EDGES) == {"top", "bottom", "left", "right"}
    for edge, side in FOCUS_TAB_EDGES.items():
        selector = focus_tab_selector(edge)
        assert f"QDockWidget QTabBar::tab:{edge}:selected:focus" in selector
        body = sheet.split(selector, 1)[1].split("}", 1)[0]
        assert f"{side}: 3px solid" in body
        for forbidden in ("padding", "margin", "outline", "border:"):
            assert forbidden not in body


# ---------------------------------------------------------------------------
# The vim Command-mode block caret colours live HERE, not in vim_mode.py
# (BUG-260812001031 follow-up)
# ---------------------------------------------------------------------------

def test_command_caret_colors_are_theme_aware_and_pure():
    """The pair differs per theme and the accessor mutates nothing -- the same
    posture `light_palette()`/`dark_palette()` and `mode_colors()` have."""
    from pgtp_editor.ui.theme import command_caret_colors

    light = command_caret_colors(True)
    dark = command_caret_colors(False)
    assert light != dark
    for background, foreground in (light, dark):
        assert QColor(background).lightness() != QColor(foreground).lightness()
    assert command_caret_colors(True) == light


def test_command_caret_background_is_NOT_the_selection_blue():
    """A second blue beside `Highlight` would be unreadable AS a mode cue while
    a selection sits next to it."""
    from pgtp_editor.ui.theme import command_caret_colors

    for light, palette in ((True, light_palette()), (False, dark_palette())):
        highlight = palette.color(QPalette.ColorRole.Highlight)
        assert QColor(command_caret_colors(light)[0]) != highlight


# -- BUG-260812063745: the status colours must be THEME colours, in pixels ----
# Fourteen sites across seven dialogs painted themselves with the CSS names
# `green`, `darkorange` and `red`. Each is a single value for both themes, so
# each fails contrast in at least one of them -- and plain `red` fails in BOTH
# (3.98:1 dark / 3.83:1 light). They are now `StatusLabel`s carrying a KIND,
# resolved per theme at paint time.
#
# Sampled from `grab().toImage()` for the reason the focus-ring block above
# records: a stylesheet assertion proves the string, not the paint, and the
# app-wide qdarkstyle QSS beats a QPalette for every property it declares --
# measured, the palette faithfully reported `#d02020` while zero red pixels
# were drawn. Every probe below therefore carries a PRESENCE anchor as well as
# the absence assertion: an absence-only test passes forever, including against
# a sampler pointed at nothing, and that has cost this project two false greens
# in a single week.


def _painted_colours(widget) -> set[str]:
    """Every colour `widget` actually paints, as lower-case `#rrggbb` -- the way
    `QImage.pixelColor().name()` spells it, which is why the theme values are
    put through `QColor(...).name()` before comparison: `resources/themes/*.json`
    mixes `#D32F2F` with `#e0a83a`, and a raw string compare against a pixel name
    silently never matches.

    A whole-image set rather than one anchored pixel: a text colour lands
    wherever the glyphs land, and the sampler must not have to know the font
    metrics. The label is given a large bold font at every call site so the
    colour reaches full strength somewhere inside a stroke rather than only in
    antialiased edge pixels."""
    image = widget.grab().toImage()
    return {
        image.pixelColor(x, y).name()
        for y in range(image.height())
        for x in range(image.width())
    }


def _status_name(kind: str, light: bool) -> str:
    """The colour a kind is *supposed* to paint under a theme, read from the
    same `status_colour` the widget reads -- never a second copy of the hex."""
    from pgtp_editor.ui.status_colours import status_colour

    return QColor(status_colour(kind, light)).name()


def _chrome(light: bool) -> str:
    """The live qdarkstyle chrome these labels sit on -- the reference §7 names,
    and the one the bare QPalette does not tell you about. Read from qdarkstyle,
    not retyped: `#FAFAFA` light, `#19232D` dark."""
    from qdarkstyle.dark.palette import DarkPalette
    from qdarkstyle.light.palette import LightPalette

    return QColor((LightPalette if light else DarkPalette).COLOR_BACKGROUND_1).name()


def _status_kinds():
    from pgtp_editor.ui.status_colours import (
        STATUS_ERROR,
        STATUS_OK,
        STATUS_WARNING,
    )

    return {"ok": STATUS_OK, "warning": STATUS_WARNING, "error": STATUS_ERROR}


@pytest.fixture
def status_label(qtbot, qapp, _reset_app_palette):
    """A shown `StatusLabel` in a real theme, big and bold enough that its
    colour covers pixels.

    `show()` is mandatory and not tidiness: the app-wide QSS is only resolved on
    polish, so an unshown grab is not evidence -- the same trap the focus-ring
    fixtures above document."""
    from PySide6.QtGui import QFont

    from pgtp_editor.ui.status_colours import StatusLabel

    def build(light: bool, kind: str):
        apply_theme(qapp, light)
        label = StatusLabel("")
        qtbot.addWidget(label)
        font = QFont()
        font.setPointSize(40)
        font.setBold(True)
        label.setFont(font)
        label.set_status("Connection succeeded", kind)
        label.show()
        qapp.processEvents()
        return label

    return build


@pytest.mark.parametrize("kind_id", ["ok", "warning", "error"])
@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_a_status_label_paints_ITS_themes_colour_and_not_the_others(
    status_label, kind_id, light
):
    """The whole bug in one assertion: a status colour is a per-theme value, so
    the label must paint the colour of the theme that is actually applied and
    must never paint the other theme's.

    The presence half is the anchor -- it proves the sampler can see the label
    at all -- and the absence half is what a single theme-blind literal (`green`
    at 3.10:1 on the dark chrome, `darkorange` at 2.23:1 on the light one) would
    fail."""
    kind = _status_kinds()[kind_id]
    painted = _painted_colours(status_label(light, kind))
    assert _status_name(kind, light) in painted  # the anchor
    assert _status_name(kind, not light) not in painted


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_a_REAL_dialogs_error_label_paints_the_themes_red(
    qtbot, qapp, _reset_app_palette, light
):
    """Through a real dialog rather than a bare widget, because the seven
    dialogs are where the defect lived: `NewRoutineDialog._error_label` was
    `setStyleSheet("color: red;")` -- 3.98:1 dark and 3.83:1 light, i.e. below
    4.5:1 in BOTH themes, which is why plain `red` was not grandfathered.

    `NewRoutineDialog` is the dialog chosen here because it constructs with no
    database and opens no modal."""
    from PySide6.QtGui import QFont

    from pgtp_editor.ui.new_routine_dialog import NewRoutineDialog
    from pgtp_editor.ui.status_colours import STATUS_ERROR

    apply_theme(qapp, light)
    dialog = NewRoutineDialog()
    qtbot.addWidget(dialog)
    label = dialog._error_label
    assert label.status_kind() == STATUS_ERROR  # a kind, never a stored colour
    font = QFont()
    font.setPointSize(30)
    font.setBold(True)
    label.setFont(font)
    label.setText("Name is required")
    dialog.show()
    qapp.processEvents()

    painted = _painted_colours(label)
    assert _status_name(STATUS_ERROR, light) in painted  # the anchor
    assert _status_name(STATUS_ERROR, not light) not in painted
    # ...and the literal it replaced is nowhere in the render.
    assert "#ff0000" not in painted


@pytest.mark.parametrize("kind_id", ["ok", "warning", "error"])
@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_every_status_kind_clears_4_5_to_1_on_the_chrome(kind_id, light):
    """Measured, not eyeballed, against the background these labels actually sit
    on. Measured values: ok 11.17 dark / 7.54 light, warning 7.45 / 5.68, error
    9.28 / 8.74 -- every pair clears the 4.5:1 body-text threshold in BOTH
    themes, which is exactly what a single CSS name cannot do."""
    kind = _status_kinds()[kind_id]
    assert _contrast(_status_name(kind, light), _chrome(light)) >= 4.5


def test_the_CSS_names_this_bug_replaced_genuinely_FAIL():
    """The focus-ring precedent: the rejected values are asserted to fail, by
    literal, so the choice cannot be quietly undone by someone reaching for the
    "obvious" colour name again.

    These are the exact measurements BUG-260812063745 replaced, against the live
    qdarkstyle chrome: CSS `green` `#008000` scores 3.10 on the dark chrome,
    `darkorange` `#FF8C00` scores 2.23 on the light chrome, and plain `red`
    `#FF0000` scores 3.98 dark AND 3.83 light -- red is the one that failed in
    both, so `color: red` was never the acceptable status quo it looked like.

    Hardcoding hex here is deliberate and is the opposite of the rule the rest
    of this block follows: these are not the app's colours, they are the values
    that must never come back."""
    assert _contrast("#008000", _chrome(False)) < 4.5   # green, dark: 3.10
    assert _contrast("#FF8C00", _chrome(True)) < 4.5    # darkorange, light: 2.23
    assert _contrast("#FF0000", _chrome(False)) < 4.5   # red, dark: 3.98
    assert _contrast("#FF0000", _chrome(True)) < 4.5    # red, light: 3.83


# -- BUG-260812063745, second half: the status bar's DEBUG chip ---------------
# `color: white; background: #b33`, hardcoded in `main_window.py` -- the last
# chip in the app that did not re-theme, and the one §7 already named as
# forbidden to copy. It is now the `debug_chip_background` / `debug_chip_
# foreground` accent pair, so the colour guard did not have to exempt the
# largest module in the project.


def _debug_chip_label(qapp, light: bool):
    """The chip painted by the REAL `MainWindow._apply_debug_chip_colours`,
    driven with a stand-in host rather than a MainWindow.

    A whole MainWindow is expensive and modal-prone in this suite, and it is not
    what is under test: the method reads `self._theme` (or `theme_for`) and
    `self._debug_label` and nothing else, so calling it unbound over a real
    QLabel exercises the shipped code path exactly, including the theme lookup
    that is the point of the fix."""
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QLabel

    from pgtp_editor.ui.main_window import MainWindow
    from pgtp_editor.ui.theme_model import theme_for

    apply_theme(qapp, light)

    class _Host:
        pass

    host = _Host()
    host._debug_label = QLabel("DEBUG")
    host._theme = theme_for(light)
    MainWindow._apply_debug_chip_colours(host)

    font = QFont()
    font.setPointSize(30)
    font.setBold(True)
    host._debug_label.setFont(font)
    return host._debug_label


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_DEBUG_chip_is_PAINTED_from_the_theme_file(qtbot, qapp,
                                                       _reset_app_palette,
                                                       light):
    """Both chip colours in rendered pixels, and both read from the parsed theme
    rather than retyped -- which is also what proves they are no longer a
    literal: a hardcoded pair cannot equal `#D32F2F` on dark and `#B00020` on
    light, and the two are asserted distinct in the test below.

    The old `#b33` is asserted absent from the render: the guard that was
    supposed to catch it only matched six-digit hex, so it lived there
    invisibly."""
    from pgtp_editor.ui.theme_model import theme_for

    label = _debug_chip_label(qapp, light)
    qtbot.addWidget(label)
    label.show()
    qapp.processEvents()

    theme = theme_for(light)
    painted = _painted_colours(label)
    assert QColor(theme.accent("debug_chip_background")).name() in painted
    assert QColor(theme.accent("debug_chip_foreground")).name() in painted
    assert QColor("#b33").name() not in painted


def test_the_DEBUG_chips_two_themes_are_DIFFERENT_backgrounds(qapp,
                                                              _reset_app_palette):
    """The single assertion a hardcoded `#b33` could never satisfy: the chip's
    background differs between the themes, so it is genuinely re-themed and not
    a literal wearing a theme lookup."""
    from pgtp_editor.ui.theme_model import theme_for

    dark_sheet = _debug_chip_label(qapp, False).styleSheet()
    light_sheet = _debug_chip_label(qapp, True).styleSheet()
    assert dark_sheet != light_sheet
    for light in (True, False):
        theme = theme_for(light)
        sheet = light_sheet if light else dark_sheet
        assert theme.accent("debug_chip_background") in sheet
        assert theme.accent("debug_chip_foreground") in sheet
    assert theme_for(True).accent("debug_chip_background") != theme_for(
        False
    ).accent("debug_chip_background")


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_DEBUG_chips_text_clears_4_5_to_1_on_its_OWN_background(light):
    """A chip is not text on chrome: its label reads against the chip's fill, so
    that is the pair that must clear the body-text threshold. Measured 4.98 dark
    (`#FFFFFF` on `#D32F2F`) and 7.33 light (`#FFFFFF` on `#B00020`). Read from
    the parsed theme, never retyped."""
    from pgtp_editor.ui.theme_model import theme_for

    theme = theme_for(light)
    assert _contrast(
        theme.accent("debug_chip_foreground"),
        theme.accent("debug_chip_background"),
    ) >= 4.5


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_DEBUG_chips_background_clears_3_to_1_on_the_chrome(light):
    """The other half, and a different threshold on purpose: the chip's fill is
    a non-text graphical object against the status bar, so 3:1 is the bar it has
    to clear to be distinguishable at all. Measured 3.20 dark and 7.02 light --
    dark is the tight one, which is why it is asserted rather than assumed."""
    from pgtp_editor.ui.theme_model import theme_for

    assert _contrast(
        theme_for(light).accent("debug_chip_background"), _chrome(light)
    ) >= 3.0
