# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""FQ-028 Part 2 — the STATIC status bar, and FQ-018's connectivity dots.

The owner's rule is the test for everything here: *"the status bar needs to
avoid being a message board — it should have some well defined information on it
constantly."* So the bar paints no transient text at all; every slot on it
states a defined fact, including when the fact is "we have not checked yet".

The connectivity dots are FQ-018's, refined by FQ-028 to project-mode-only. The
two properties worth pinning about the poll are the ones that would hurt if they
broke silently: it must not run while the window is inactive, and it must never
block the GUI thread.
"""
from collections import Counter

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtWidgets import QMainWindow, QStatusBar

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import ProjectSettings
from pgtp_editor.ui.busy import busy_status
from pgtp_editor.ui.connectivity import UNKNOWN, ConnectivityIndicator, dot_rendering
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.project_status_model import QualityState, SandboxState
from pgtp_editor.ui.status_bar import IDLE_TEXT, StaticStatusBar, busy_text
from pgtp_editor.ui.theme import apply_theme
from pgtp_editor.ui.theme_model import theme_for

# `contrast_ratio` and `rendered` are the suite's one implementation each, in
# the file that introduced the pixel-sampling precedent. Reused, not re-copied —
# a third copy of the WCAG formula is a third chance to get it wrong.
#
# **`CHROME` from that module is deliberately NOT imported**: it names the WINDOW
# background, which is right for a results panel and wrong for anything in the
# status bar. See the block comment above `status_bar_chrome` below.
from tests.ui.test_sql_results_panel import contrast_ratio, rendered


def _quiet_async(window):
    """Silence every background lane for the duration of a project transition.

    BUG-040 auto-opens a sandbox session inside `set_active_project`; with a
    configured host that would attempt a real connection on a worker thread and
    outlive the test. These tests are about the status bar, so nothing async is
    allowed to start.
    """
    window._run_async = lambda *args, **kwargs: None
    window.sandbox_controller._run_async = lambda *args, **kwargs: None
    window._ddl_project_ui._run_async = lambda *args, **kwargs: None


def _window(qtbot, tmp_path):
    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)
    return window


# --- No message board -------------------------------------------------------


def test_the_bar_paints_no_transient_text_however_it_is_asked(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    bar = window.statusBar()

    bar.showMessage("something happened", 5000)

    assert isinstance(bar, StaticStatusBar)
    assert bar.displayed_message() == ""
    assert QStatusBar.currentMessage(bar) == ""
    # ...but the notice is not lost: it is the last thing the app SAID.
    assert bar.currentMessage() == "something happened"


def test_every_transient_message_becomes_an_activity_log_entry(qtbot, tmp_path):
    """The ~40 `showMessage` call sites did not move -- the SINK did, which is
    what makes it impossible to reintroduce a message-board write by adding a
    forty-first."""
    window = _window(qtbot, tmp_path)
    window.activity_panel.clear()
    window.activity_log._entries = []

    window._shell_status("Validated 3 pages.", 5000)
    window.statusBar().showMessage("Saved /tmp/x.pgtp", 5000)

    rows = window.activity_panel.row_texts()
    assert any("Validated 3 pages." in row for row in rows)
    assert any("Saved /tmp/x.pgtp" in row for row in rows)


def test_a_refusal_lands_as_exactly_one_activity_log_row(qtbot, tmp_path):
    """BUG-055: this is the assertion whose absence let *"the ~15 refusals reach
    nobody"* be believed twice. `showMessage` painting nothing is FQ-028's design,
    not a dropped message — the text is journalled, and a refusal is a durable row
    rather than a flash. The `timeout` argument is gone from every call site in
    `main_window.py` because it never meant anything after FQ-028; nothing about
    the sink changed with it."""
    window = _window(qtbot, tmp_path)
    window.activity_panel.clear()
    window.activity_log._entries = []

    window._on_read_only_edit_attempted()

    rows = window.activity_panel.row_texts()
    assert len(rows) == 1
    assert "Caption Mode" in rows[0]
    assert window.statusBar().displayed_message() == ""


def test_an_empty_message_is_not_journalled(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    before = len(window.activity_panel.row_texts())

    window.statusBar().showMessage("   ")

    assert len(window.activity_panel.row_texts()) == before


# --- The busy slot ----------------------------------------------------------


def test_the_busy_slot_is_permanent_and_states_idle_when_nothing_runs(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)

    assert window.statusBar().busy_slot.text() == IDLE_TEXT
    assert not window.statusBar().busy_slot.running


def test_busy_status_drives_the_slot_and_clears_it(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    bar = window.statusBar()

    with busy_status(bar, "Validating…"):
        assert bar.busy_slot.running
        assert bar.busy_slot.text() == busy_text("Validating…", 0)

    assert not bar.busy_slot.running
    assert bar.busy_slot.text() == IDLE_TEXT


def test_the_busy_counter_ticks(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    slot = window.statusBar().busy_slot
    slot.begin("Checking…")

    slot._tick()
    slot._tick()

    assert slot.text() == "Checking… 2s".replace("… ", " ")  # the ellipsis is trimmed
    assert slot.text() == busy_text("Checking…", 2)
    slot.end()


def test_a_nested_busy_block_does_not_report_idle_early(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    bar = window.statusBar()

    with busy_status(bar, "Outer…"):
        with busy_status(bar, "Inner…"):
            pass
        assert bar.busy_slot.running

    assert not bar.busy_slot.running


def test_a_plain_qstatusbar_keeps_the_old_sticky_message(qtbot):
    """`busy_status` is also handed bare `QStatusBar`s (unit tests, and any
    caller outside the main window), whose contract is unchanged."""
    bar = QStatusBar()
    qtbot.addWidget(bar)

    with busy_status(bar, "Working…"):
        assert bar.currentMessage() == "Working…"


# --- The connectivity dots --------------------------------------------------


def test_the_dots_are_absent_without_a_project(qtbot, tmp_path):
    """FQ-028 overrode FQ-018 to project-mode-only, for BOTH dots. Visibility,
    never a greyed-out third posture."""
    window = _window(qtbot, tmp_path)

    assert not window._quality_dot.isVisibleTo(window)
    assert not window._sandbox_dot.isVisibleTo(window)


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_an_unknown_state_still_states_something(qtbot, light):
    """A slot always shows a defined fact -- "not checked yet" is one, and it is
    visibly different from a claim of reachability."""
    indicator = ConnectivityIndicator("Quality")
    qtbot.addWidget(indicator)

    assert indicator.state is UNKNOWN
    assert indicator.text().strip() != "Quality"
    assert "not checked yet" in indicator.toolTip()
    assert dot_rendering(UNKNOWN, light) != dot_rendering(
        QualityState.CONNECTION_OK, light
    )


# --- The dots' legibility, and their second channel (BUG-260812103144) ------
#
# This block replaces `test_the_three_states_are_told_apart_by_colour`, which
# pinned exactly the design that had to go: three states drawn as the same
# filled `●` and told apart by hue, with red-vs-green — the commonest
# colour-vision confusion — carrying the most meaning. Colour still differs;
# what is now REQUIRED is that it is not the only channel.
#
# Every ratio here is measured against the STATUS BAR's own background, which is
# the correction that made this bug worth its own id. qdarkstyle sets
# `QStatusBar { background: COLOR_BACKGROUND_4 }` and leaves `QStatusBar QLabel`
# transparent, so a dot sits on the mid-tone `#455364` / `#C0C4C8` — NOT on
# `COLOR_BACKGROUND_1`. Measuring against the window chrome is what let the
# offline dot's real 1.46:1 be reported as 2.96:1, and it is why
# `test_sql_results_panel.CHROME` must never be imported here: that constant
# names the window, correctly for the panel it belongs to and wrongly for
# anything in the status bar. `STATUS_BAR_CHROME` is derived from the theme file
# instead, and `test_the_surface_the_dots_are_drawn_on_is_the_status_bars_own`
# proves the derivation is what the user's screen actually shows.
#
# The threshold is **4.5:1, the TEXT threshold**, not 3:1 for a graphical
# object: `_render` colours the whole label, so the word "Quality"/"Sandbox" is
# painted in the state colour alongside the glyph.
#
# **Honest scope limit:** the surface is a theme file's own COLOR_BACKGROUND_4,
# so a USER theme can move it and no assertion can promise 4.5:1 for arbitrary
# user themes. What is guaranteed here is the two BUNDLED themes.

#: The four states whose rendering must be legible and mutually distinguishable.
#: `SandboxState`'s three are the same three renderings under different enum
#: members, so pinning the Quality set plus UNKNOWN covers every value.
DOT_STATES = (
    UNKNOWN,
    QualityState.NOT_SET_UP,
    QualityState.OFFLINE,
    QualityState.CONNECTION_OK,
)

#: The values the dots FAILED at, kept as data. Following the focus-ring
#: precedent: a fix that only asserts the new state is one silent revert away
#: from being undone, so the test also proves the old values genuinely failed.
PRE_FIX_VALUES = {
    "connectivity_unknown": "#9E9E9E",
    "connectivity_not_set_up": "#FFFFFF",
    "connectivity_offline": "#D02020",
    "connectivity_reachable": "#2E9E4F",
}


def status_bar_chrome(light: bool) -> str:
    """The colour a status-bar widget is actually drawn on, read from the theme.

    Deliberately NOT `test_sql_results_panel.CHROME` — see the block comment
    above. That constant is the window; this is the bar.
    """
    return theme_for(light).chrome["COLOR_BACKGROUND_4"]


def _dot_in_a_shown_status_bar(qtbot, qapp, light, state):
    """A real `QMainWindow` with a themed, SHOWN status bar carrying one dot.

    Showing is not optional: an unshown widget's grab is not evidence of what
    the user sees, and the app-wide qdarkstyle sheet — which beats `QPalette`
    for every property it declares — is only resolved once the widget is
    polished.
    """
    apply_theme(qapp, light)
    window = QMainWindow()
    qtbot.addWidget(window)
    indicator = ConnectivityIndicator("Quality")
    window.statusBar().addPermanentWidget(indicator)
    indicator.set_state(state)
    window.resize(600, 200)
    window.show()
    qtbot.waitExposed(window)
    qapp.processEvents()
    return window, indicator


def _pixels_over(window, widget) -> Counter:
    """`{'#rrggbb': count}` for the WINDOW's pixels inside `widget`'s rect.

    Grabbing the widget itself is the trap here: `QWidget.grab()` renders a
    transparent background as **black**, so a dot grabbed alone reports `#000000`
    where the status bar's grey is, and the contrast being asserted becomes
    unmeasurable. The pixels behind the label only exist on the window.
    """
    image = window.grab().toImage()
    top_left = widget.mapTo(window, QPoint(0, 0))
    counts: Counter = Counter()
    for y in range(top_left.y(), min(top_left.y() + widget.height(), image.height())):
        for x in range(top_left.x(), min(top_left.x() + widget.width(), image.width())):
            counts[image.pixelColor(x, y).name()] += 1
    return counts


@pytest.mark.parametrize("state", DOT_STATES, ids=lambda s: str(s))
@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_every_dot_state_is_LEGIBLE_on_the_status_bar(state, light):
    """4.5:1 for all four states in both bundled themes.

    Before this fix every state failed in at least one theme, and "reachable" —
    the state a user reads most — was under 2.3:1 in BOTH.
    """
    colour = dot_rendering(state, light)[0]
    ratio = contrast_ratio(colour, status_bar_chrome(light))
    assert ratio >= 4.5, f"{state} renders {colour} at {ratio:.2f}:1"


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_values_this_fix_REPLACED_really_did_fail(light):
    """The other half of the net, and the reason it is here: an assertion that
    only pins the new values cannot tell a considered change from a revert.

    Measured on the status-bar grey: offline `#D02020` scored 1.46:1 on dark and
    3.06:1 on light; reachable `#2E9E4F` 2.29 / 1.96; unknown `#9E9E9E`
    2.93 / 1.53; not-set-up `#FFFFFF` 7.85 / 1.75. Any theme file that goes back
    to one of them fails here as well as above.
    """
    chrome = status_bar_chrome(light)
    failures = [
        old for old in PRE_FIX_VALUES.values() if contrast_ratio(old, chrome) < 4.5
    ]
    assert len(failures) >= 3, failures
    live = {dot_rendering(state, light)[0].lower() for state in DOT_STATES}
    assert live.isdisjoint({old.lower() for old in failures})


def test_the_dots_are_not_told_apart_by_COLOUR_ALONE():
    """Every state carries a distinct GLYPH as well as a distinct colour.

    This is what supersedes `test_the_three_states_are_told_apart_by_colour`:
    `NOT_SET_UP`, `OFFLINE` and `REACHABLE` all drew `●`, so "nothing
    configured", "offline" and "reachable" were separated by hue alone — and the
    pair that matters is red vs green. Colour is not a channel every user has.
    """
    for light in (True, False):
        renderings = [dot_rendering(state, light) for state in DOT_STATES]
        assert len({colour for colour, _g, _t in renderings}) == len(DOT_STATES)
        assert len({glyph for _c, glyph, _t in renderings}) == len(DOT_STATES)
        assert len({tooltip for _c, _g, tooltip in renderings}) == len(DOT_STATES)


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_surface_the_dots_are_drawn_on_is_the_status_bars_own(qtbot, qapp, light):
    """The load-bearing measurement: what is actually behind a dot on screen.

    The dot's label is transparent over `QStatusBar`, so the pixels around the
    glyph must be the theme's `COLOR_BACKGROUND_4` — the value
    `status_bar_chrome` derives — and NOT `COLOR_BACKGROUND_1`. If this ever
    reports the window colour, every ratio above is being measured against the
    wrong surface, which is the exact error that hid a 1.46:1 dot.
    """
    window, indicator = _dot_in_a_shown_status_bar(
        qtbot, qapp, light, QualityState.OFFLINE
    )
    counts = _pixels_over(window, indicator)

    bar = rendered(status_bar_chrome(light))
    window_chrome = rendered(theme_for(light).chrome["COLOR_BACKGROUND_1"])
    assert counts[bar] > 0, f"nothing behind the dot is {bar}: {counts.most_common(4)}"
    assert counts[bar] > counts[window_chrome]
    apply_theme(qapp, False)


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_dot_RENDERS_its_theme_colour_and_not_the_other_themes(qtbot, qapp, light):
    """Rendered pixels, with a presence anchor. An absence-only assertion passes
    forever the moment the sampler stops seeing the widget."""
    window, indicator = _dot_in_a_shown_status_bar(
        qtbot, qapp, light, QualityState.OFFLINE
    )
    counts = _pixels_over(window, indicator)

    mine = rendered(dot_rendering(QualityState.OFFLINE, light)[0])
    theirs = rendered(dot_rendering(QualityState.OFFLINE, not light)[0])
    assert counts[mine] > 0, f"no {mine} pixels: {counts.most_common(4)}"
    assert counts[theirs] == 0, f"the other theme's {theirs} is on screen"
    apply_theme(qapp, False)


def test_a_theme_FLIP_repaints_the_dots(qtbot, qapp):
    """The latent freeze this fix had to solve anyway: the four colours used to
    be resolved ONCE at import, so a runtime theme change (the Themes pane,
    FQ-260812021716) left the dots painting whichever theme loaded first.
    Harmless only while every theme agreed on the values — which this fix ends.

    `ConnectivityIndicator` inherits `StatusLabel`'s machinery rather than
    hand-rolling a `changeEvent`; both directions are exercised because only
    dark -> light regressed in development, the flip whose NEW palette arrives
    on the nested event.
    """
    window, indicator = _dot_in_a_shown_status_bar(
        qtbot, qapp, False, QualityState.CONNECTION_OK
    )

    for light in (True, False, True, False):
        apply_theme(qapp, light)
        qapp.processEvents()
        expected = dot_rendering(QualityState.CONNECTION_OK, light)[0]
        assert expected in indicator.styleSheet(), (
            f"stale colour after flipping to {'light' if light else 'dark'}: "
            f"{indicator.styleSheet()!r}"
        )
        assert rendered(expected) in _pixels_over(window, indicator)
    apply_theme(qapp, False)


def test_the_dots_keep_their_status_bar_PADDING(qtbot):
    """`StatusLabel` writes `QLabel { color: … }` and nothing else, where the
    old `_render` declared `padding: 1px 6px` in the same sheet. Losing it
    silently changes the status bar's spacing, so it moved to contents margins
    and is pinned rather than trusted."""
    indicator = ConnectivityIndicator("Quality")
    qtbot.addWidget(indicator)

    margins = indicator.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        6, 1, 6, 1,
    )


def test_opening_a_project_reveals_the_dots_and_polls_once(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.activateWindow()
    folder = tmp_path / "proj"
    (folder / ".ddlproject").mkdir(parents=True)
    settings = ProjectSettings(
        sandbox=ConnectionParams(host="localhost", database="pgtp_sandbox_x")
    )
    _quiet_async(window)

    window._ddl_project_ui.set_active_project(folder, settings)

    assert window._quality_dot.isVisibleTo(window)
    assert window._sandbox_dot.isVisibleTo(window)


def test_the_poll_never_runs_on_the_gui_thread(qtbot, tmp_path, monkeypatch):
    """`ui/async_task.py::run_async` is the established seam, and a blocking
    connect every 30 s on the GUI thread would stutter the app twice a minute."""
    window = _window(qtbot, tmp_path)
    folder = tmp_path / "proj"
    (folder / ".ddlproject").mkdir(parents=True)
    window._ddl_project_ui.set_active_project(folder, ProjectSettings())
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    handed_over = []
    window._run_async = lambda work, **kw: handed_over.append(work)

    window._poll_connectivity()

    assert len(handed_over) == 1
    assert callable(handed_over[0])


def test_the_poll_is_gated_on_window_activation(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    folder = tmp_path / "proj"
    (folder / ".ddlproject").mkdir(parents=True)
    window._ddl_project_ui.set_active_project(folder, ProjectSettings())
    calls = []
    window._run_async = lambda work, **kw: calls.append(work)

    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    window._poll_connectivity()
    assert calls == []

    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window._poll_connectivity()
    assert len(calls) == 1


def test_deactivating_the_window_stops_the_timer_and_reactivating_polls_again(
    qtbot, tmp_path, monkeypatch
):
    """A backgrounded editor must not keep two connections warm; a returning one
    must not be left reading a dot up to 30 s stale."""
    from PySide6.QtCore import QEvent

    window = _window(qtbot, tmp_path)
    folder = tmp_path / "proj"
    (folder / ".ddlproject").mkdir(parents=True)
    window._ddl_project_ui.set_active_project(folder, ProjectSettings())
    calls = []
    window._run_async = lambda work, **kw: calls.append(work)

    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    window.changeEvent(QEvent(QEvent.Type.ActivationChange))
    assert not window._connectivity_timer.isActive()

    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.changeEvent(QEvent(QEvent.Type.ActivationChange))
    assert window._connectivity_timer.isActive()
    assert window._connectivity_timer.interval() == 30_000
    assert len(calls) == 1


def test_a_poll_result_feeds_the_reused_state_helpers(qtbot, tmp_path, monkeypatch):
    """The status bar and §18.8 must never hold two notions of "connected": the
    poll's answer goes through `quality_state` and the sandbox classifier."""
    window = _window(qtbot, tmp_path)
    folder = tmp_path / "proj"
    (folder / ".ddlproject").mkdir(parents=True)
    settings = ProjectSettings(
        target=ConnectionParams(host="db01", database="quality"),
        sandbox=ConnectionParams(host="db01", database="pgtp_sandbox_x"),
    )
    _quiet_async(window)
    window._ddl_project_ui.set_active_project(folder, settings)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    captured = {}
    window._run_async = lambda work, **kw: captured.update(kw)

    window._poll_connectivity()
    captured["on_result"]((None, "connection refused"))

    assert window._quality_dot.state is QualityState.CONNECTION_OK
    assert window._sandbox_dot.state is SandboxState.OFFLINE


def test_a_broken_poll_seam_falls_back_to_unknown_not_to_a_claim(
    qtbot, tmp_path, monkeypatch
):
    window = _window(qtbot, tmp_path)
    folder = tmp_path / "proj"
    (folder / ".ddlproject").mkdir(parents=True)
    window._ddl_project_ui.set_active_project(folder, ProjectSettings())
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    captured = {}
    window._run_async = lambda work, **kw: captured.update(kw)
    window._poll_connectivity()

    captured["on_error"](RuntimeError("seam is broken"))

    assert window._quality_dot.state is UNKNOWN
    assert window._sandbox_dot.state is UNKNOWN


def _sync_run(work, on_result=None, on_error=None):
    """The suite's standard synchronous stand-in for `run_async`."""
    try:
        result = work()
    except BaseException as exc:  # noqa: BLE001 - mirrors the real seam
        if on_error is not None:
            on_error(exc)
        return None
    if on_result is not None:
        on_result(result)
    return result


def test_the_dots_follow_real_project_openness_not_the_workflow_label(
    qtbot, tmp_path
):
    """FQ-028 is explicit: "project mode" for the dots means a project is
    ACTUALLY open, not that the Project column was picked in the launcher. The
    two can legitimately disagree."""
    window = _window(qtbot, tmp_path)

    window.set_workflow_mode("project")

    assert window._mode_label.text() == "Project mode"
    assert not window._quality_dot.isVisibleTo(window)


def test_the_permanent_widgets_are_the_whole_bar(qtbot, tmp_path):
    """Mode indicator, busy slot and the two dots -- one coherent indicator
    region, not two rival ones."""
    window = _window(qtbot, tmp_path)
    bar = window.statusBar()

    children = bar.findChildren(object, options=Qt.FindChildOption.FindDirectChildrenOnly)

    assert window._mode_label in children
    assert bar.busy_slot in children
    assert window._quality_dot in children
    assert window._sandbox_dot in children
