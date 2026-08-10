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
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QStatusBar

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import ProjectSettings
from pgtp_editor.ui.busy import busy_status
from pgtp_editor.ui.connectivity import UNKNOWN, ConnectivityIndicator, dot_rendering
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.project_status_model import QualityState, SandboxState
from pgtp_editor.ui.status_bar import IDLE_TEXT, StaticStatusBar, busy_text


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


def test_an_unknown_state_still_states_something(qtbot):
    """A slot always shows a defined fact -- "not checked yet" is one, and it is
    visibly different from a claim of reachability."""
    indicator = ConnectivityIndicator("Quality")
    qtbot.addWidget(indicator)

    assert indicator.state is UNKNOWN
    assert indicator.text().strip() != "Quality"
    assert "not checked yet" in indicator.toolTip()
    assert dot_rendering(UNKNOWN) != dot_rendering(QualityState.CONNECTION_OK)


def test_the_three_states_are_told_apart_by_colour():
    colours = {
        dot_rendering(QualityState.NOT_SET_UP)[0],
        dot_rendering(QualityState.OFFLINE)[0],
        dot_rendering(QualityState.CONNECTION_OK)[0],
    }
    assert len(colours) == 3


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
