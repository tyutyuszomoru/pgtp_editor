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
"""FQ-019 — the Activity Log, WIRED.

The Qt-free core is covered by `tests/db/test_activity_log.py` and the widget by
`tests/ui/test_activity_panel.py`; this module covers the hookup, which is where
the remaining decisions live:

* the journal is its own **`QDockWidget` beside** Audit / Problems, not a tab
  inside it and not a fifth Audit prefix, with the View-menu toggle and the
  `windowState` `objectName` its three sibling docks get;
* the host owns exactly one `ActivityLog` and drives its lifecycle -- a project
  transition loads that project's persisted history, a close drops back to an
  empty standalone buffer;
* **standalone entries never migrate into a project's file**: the transfer is
  the core's `open_project`/`close_project`, never hand-rolled here;
* writes are coarse -- a debounce after a `record(...)`, plus a synchronous
  flush on project transition and in `closeEvent` -- never inside the gesture;
* a failed action is recorded AS failed, with its full error text retained for
  the click-through viewer;
* and the call sites really fire: driving a real gesture end to end produces a
  row, rather than a test calling `record(...)` itself.
"""
from datetime import datetime

from pgtp_editor.db.activity_log import (
    FILE_VERB_OPENED,
    FILE_VERB_SAVED,
    SOURCE_PROJECT_FILES,
    SOURCE_QUALITY_DB,
    SOURCE_QUALITY_FILES,
    SOURCE_SANDBOX_DB,
    STATUS_ERROR,
    ActivityEntry,
    activity_path,
    load_activity,
)
from pgtp_editor.ui.activity_panel import ActivityPanel
from pgtp_editor.ui.ddl_object_editor import (
    GESTURE_APPLY_TO_QUALITY,
    GESTURE_LABELS,
)
from pgtp_editor.ui.main_window import MainWindow

from ._menu_helpers import action_labels, find_top_menu

_MINIMAL_PGTP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Project fileName="demo">\n'
    '  <Page fileName="p1" tableName="pr.equipment" caption="Equipment"/>\n'
    "</Project>\n"
)


def _window(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path / "gen")
    qtbot.addWidget(window)
    return window


def _project(tmp_path, name="project"):
    folder = tmp_path / name
    (folder / ".ddlproject").mkdir(parents=True)
    return folder


def _open_project(window, folder):
    """The real transition: the §18.2 lane announces the new project and the
    host's `_on_activity_project_changed` is what reacts."""
    window._ddl_project_ui.folder = folder
    window._ddl_project_ui.project_changed.emit(folder, None)


def _close_project(window):
    window._ddl_project_ui.folder = None
    window._ddl_project_ui.project_changed.emit(None, None)


def _seed_history(folder, *rows):
    activity_path(folder).parent.mkdir(parents=True, exist_ok=True)
    activity_path(folder).write_text(
        "".join(entry.to_json_line() + "\n" for entry in rows), encoding="utf-8"
    )


def _entry(stamp, source=SOURCE_PROJECT_FILES, **kwargs):
    return ActivityEntry(
        timestamp=datetime.fromisoformat(stamp), source=source, **kwargs
    )


# --- The dock ---------------------------------------------------------------


def test_the_activity_log_is_a_tab_of_the_one_bottom_dock(qtbot, tmp_path):
    """FQ-028 REPOSITIONED it: the journal that shipped an hour earlier as its
    own dock beside Audit / Problems is now the FIRST TAB of the single bottom
    dock, whose second tab is Results. There is no `activity_dock` any more --
    a third bottom surface is exactly what the split was meant to avoid."""
    window = _window(qtbot, tmp_path)

    assert isinstance(window.activity_panel, ActivityPanel)
    assert not hasattr(window, "activity_dock")
    assert window.audit_dock.widget() is window.bottom_tabs
    assert window.bottom_tabs.widget(window.activity_tab_index) is window.activity_panel
    assert window.bottom_tabs.tabText(window.activity_tab_index) == "Activity Log"

    from PySide6.QtCore import Qt

    assert (
        window.dockWidgetArea(window.audit_dock)
        == Qt.DockWidgetArea.BottomDockWidgetArea
    )


def test_the_bottom_dock_keeps_the_audit_object_name_so_saved_layouts_survive(
    qtbot, tmp_path
):
    """`saveState`/`restoreState` address docks by `objectName`. The bottom dock
    KEPT `audit_dock` through the restructuring on purpose: a user's saved
    bottom-dock geometry and visibility carry straight over onto the two-tab
    panel instead of being discarded."""
    window = _window(qtbot, tmp_path)

    assert window.audit_dock.objectName() == "audit_dock"
    assert "audit_dock".encode("utf-16-be") in bytes(window.saveState())

    # And it really round-trips: a hidden dock comes back hidden.
    window.audit_dock.setVisible(False)
    state = window.saveState()
    window.audit_dock.setVisible(True)
    window.restoreState(state)
    assert not window.audit_dock.isVisibleTo(window)


def test_the_view_menu_focuses_the_activity_tab(qtbot, tmp_path):
    """The entry is no longer a dock toggle -- a tab is either the one in view
    or it is not, so there is nothing to check -- it un-hides the dock and
    brings the journal forward."""
    window = _window(qtbot, tmp_path)
    menu = find_top_menu(window, "View")
    assert "Activity Log" in action_labels(menu)

    window.bottom_tabs.setCurrentWidget(window.results_panel)
    window.audit_dock.setVisible(False)

    window._activity_action.trigger()

    assert window.audit_dock.isVisibleTo(window)
    assert window.bottom_tabs.currentWidget() is window.activity_panel


# --- The lifecycle ----------------------------------------------------------


def test_opening_a_project_loads_that_projects_history_into_the_panel(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)
    folder = _project(tmp_path)
    _seed_history(
        folder,
        _entry("2026-08-01T09:00:00", file_verb=FILE_VERB_SAVED),
        _entry("2026-08-01T09:05:00", file_verb=FILE_VERB_OPENED),
    )

    _open_project(window, folder)

    assert window.activity_log.project_dir == folder
    assert [e.file_verb for e in window.activity_log.entries] == [
        FILE_VERB_SAVED,
        FILE_VERB_OPENED,
    ]
    assert len(window.activity_panel.row_texts()) == 2
    assert "2026-08-01 09:00" in window.activity_panel.row_texts()[0]


def test_closing_a_project_clears_the_panel_and_the_buffer(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    folder = _project(tmp_path)
    _seed_history(folder, _entry("2026-08-01T09:00:00", file_verb=FILE_VERB_SAVED))
    _open_project(window, folder)

    _close_project(window)

    assert window.activity_log.project_dir is None
    assert window.activity_log.entries == ()
    assert window.activity_panel.row_texts() == []


def test_a_second_project_never_shows_the_first_ones_history(qtbot, tmp_path):
    """The journal is per project, so a transition REPLACES the buffer rather
    than accumulating across projects."""
    window = _window(qtbot, tmp_path)
    first = _project(tmp_path, "one")
    second = _project(tmp_path, "two")
    _seed_history(first, _entry("2026-08-01T09:00:00", file_verb=FILE_VERB_SAVED))
    _seed_history(second, _entry("2026-08-02T10:00:00", file_verb=FILE_VERB_OPENED))

    _open_project(window, first)
    _open_project(window, second)

    # FQ-028 routes transient status-bar notices here too, so the FILE entries
    # are what this asserts -- a notice has no `file_verb`.
    assert [
        e.file_verb for e in window.activity_log.entries if e.file_verb
    ] == [FILE_VERB_OPENED]


# --- Standalone entries are session-only ------------------------------------


def test_a_standalone_entry_is_never_written_to_any_project_file(qtbot, tmp_path):
    """The load-bearing rule: an entry recorded with no project open belongs to
    a session that had no project. Opening one afterwards must not adopt it."""
    window = _window(qtbot, tmp_path)
    folder = _project(tmp_path)

    window.record_file_activity(FILE_VERB_SAVED)
    assert window.activity_log.entries[0].source == SOURCE_QUALITY_FILES
    window._flush_activity_writes()
    assert not list(tmp_path.rglob("activity.jsonl"))

    _open_project(window, folder)
    window._flush_activity_writes()

    assert load_activity(folder) == []
    assert window.activity_log.entries == ()


def test_a_quality_files_entry_recorded_with_a_project_open_still_never_persists(
    qtbot, tmp_path
):
    """`Quality files` MEANS standalone, so the core refuses it even if a
    project happens to be open -- the host must not work around that."""
    window = _window(qtbot, tmp_path)
    folder = _project(tmp_path)
    _open_project(window, folder)

    window.record_activity(SOURCE_QUALITY_FILES, file_verb=FILE_VERB_SAVED)
    window._flush_activity_writes()

    assert load_activity(folder) == []
    # Still visible for this session, though -- session-only, not invisible.
    assert len(window.activity_panel.row_texts()) == 1


# --- Writes: debounced, then flushed ---------------------------------------


def test_a_record_is_debounced_and_not_written_inside_the_gesture(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    folder = _project(tmp_path)
    _open_project(window, folder)

    window.record_file_activity(FILE_VERB_SAVED)

    assert window._activity_write_timer.isActive()
    assert not activity_path(folder).exists()

    window._flush_activity_writes()

    assert not window._activity_write_timer.isActive()
    assert [e.file_verb for e in load_activity(folder)] == [FILE_VERB_SAVED]


def test_the_debounced_write_lands_on_its_own_when_the_timer_fires(qtbot, tmp_path):
    """Not merely "a manual flush works": the timer really is connected."""
    window = _window(qtbot, tmp_path)
    folder = _project(tmp_path)
    _open_project(window, folder)

    window.record_file_activity(FILE_VERB_SAVED)
    qtbot.waitUntil(lambda: activity_path(folder).exists(), timeout=3000)

    assert [e.file_verb for e in load_activity(folder)] == [FILE_VERB_SAVED]


def test_close_event_flushes_synchronously(qtbot, tmp_path):
    """The last chance: whatever the debounce still owed must be on disk by the
    time the window is gone."""
    window = _window(qtbot, tmp_path)
    folder = _project(tmp_path)
    _open_project(window, folder)
    window.record_file_activity(FILE_VERB_SAVED)
    assert not activity_path(folder).exists()

    window.close()

    assert [e.file_verb for e in load_activity(folder)] == [FILE_VERB_SAVED]


def test_a_project_transition_flushes_before_it_switches_stores(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    first = _project(tmp_path, "one")
    second = _project(tmp_path, "two")
    _open_project(window, first)
    window.record_file_activity(FILE_VERB_SAVED)

    _open_project(window, second)

    assert [e.file_verb for e in load_activity(first)] == [FILE_VERB_SAVED]
    assert load_activity(second) == []


# --- Failures are recorded as failures --------------------------------------


def test_a_failed_action_is_recorded_as_failed_with_its_full_error(qtbot, tmp_path):
    """`record(..., error=...)` forces `status=error`, and the FULL text is
    retained -- the panel shows 20 characters, the viewer needs the rest."""
    window = _window(qtbot, tmp_path)
    folder = _project(tmp_path)
    _open_project(window, folder)
    long_error = "syntax error at or near \"SELCT\"\n" + "context: " + "x" * 400

    entry = window.record_file_activity(FILE_VERB_SAVED, error=long_error)

    assert entry.status == STATUS_ERROR
    assert entry.failed
    assert entry.error_full == long_error
    assert len(entry.error_preview) < len(long_error)
    window._flush_activity_writes()
    assert load_activity(folder)[0].error_full == long_error


def test_a_caller_cannot_report_a_failure_as_a_success(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    entry = window.record_activity(
        SOURCE_QUALITY_DB,
        GESTURE_LABELS[GESTURE_APPLY_TO_QUALITY],
        ddl="drop table t",
        error="boom",
        status="success",
    )

    assert entry.status == STATUS_ERROR


# --- Real call sites, driven end to end -------------------------------------


def test_opening_a_pgtp_journals_an_opened_entry(qtbot, tmp_path):
    """Call site 1: the document lane's `open_file`, driven through the host's
    public `open_project_file` -- the same path `main.py` and drag-and-drop
    use."""
    window = _window(qtbot, tmp_path)
    document = tmp_path / "app.pgtp"
    document.write_text(_MINIMAL_PGTP, encoding="utf-8")

    window.open_project_file(str(document))

    assert [
        e.file_verb for e in window.activity_log.entries if e.file_verb
    ] == [FILE_VERB_OPENED]
    assert any(
        e.source == SOURCE_QUALITY_FILES and e.file_verb == FILE_VERB_OPENED
        for e in window.activity_log.entries
    )
    assert any(
        row.endswith("Opened success") for row in window.activity_panel.row_texts()
    )


def test_an_unparseable_pgtp_journals_the_open_as_a_failure(qtbot, tmp_path, monkeypatch):
    """The same call site's failure leg: a parse error is an OPEN that
    happened and failed, and its text is what the viewer shows."""
    from pgtp_editor.ui import modals

    monkeypatch.setattr(
        modals.QMessageBox, "critical", staticmethod(lambda *a, **k: None)
    )
    window = _window(qtbot, tmp_path)
    document = tmp_path / "broken.pgtp"
    document.write_text("<Project", encoding="utf-8")

    window.open_project_file(str(document))

    entry = window.activity_log.entries[-1]
    assert entry.file_verb == FILE_VERB_OPENED
    assert entry.status == STATUS_ERROR
    assert entry.error_full


def test_saving_a_pgtp_journals_a_saved_entry_in_the_projects_store(
    qtbot, tmp_path
):
    """Call site 2: `Deployment ▸ Save .pgtp`, with a project open -- so the
    source is `Project files` and the entry reaches that project's JSONL."""
    window = _window(qtbot, tmp_path)
    folder = _project(tmp_path)
    document = folder / "app.pgtp"
    document.write_text(_MINIMAL_PGTP, encoding="utf-8")
    window.open_project_file(str(document))
    _open_project(window, folder)

    window._doc_ui.save_project()
    window._flush_activity_writes()

    stored = load_activity(folder)
    assert [e.file_verb for e in stored if e.file_verb] == [FILE_VERB_SAVED]
    assert stored[0].source == SOURCE_PROJECT_FILES
    # The `Opened` that preceded the project was standalone and did NOT follow
    # the user into the project's file.
    assert all(e.file_verb != FILE_VERB_OPENED for e in stored)


def test_a_sandbox_console_run_journals_the_ran_verb(qtbot, tmp_path):
    """Call site 3: the SQL console's `run_finished`, driven with a real
    `RunReport`."""
    from pgtp_editor.db.sandbox_query import QueryResult
    from pgtp_editor.ui.sql_results_panel import RunReport, StatementRun

    window = _window(qtbot, tmp_path)
    result = QueryResult.failed("select 1", "relation \"nope\" does not exist")
    report = RunReport(
        runs=(StatementRun(
            index=1, sql="select 1", classification="dml", result=result
        ),),
        total=1,
    )

    window._record_sandbox_run(report)

    entry = window.activity_log.entries[-1]
    assert entry.source == SOURCE_SANDBOX_DB
    assert entry.verb == "ran"
    assert entry.status == STATUS_ERROR
    assert "nope" in entry.error_full


def test_saving_a_php_tab_journals_a_saved_entry(qtbot, tmp_path):
    """Call site 4: §21's PHP tabs. Subscribed per tab off
    `PhpTabController.tab_opened`, because the tab is what knows whether its own
    save succeeded."""
    window = _window(qtbot, tmp_path)
    php = tmp_path / "handler.php"
    php.write_text("<?php echo 1;", encoding="utf-8")
    tab = window._php_tabs.open_path(str(php))
    assert tab is not None
    tab.editor.insertPlainText("\n// edited")

    assert tab.save() is True

    entry = window.activity_log.entries[-1]
    assert entry.file_verb == FILE_VERB_SAVED
    assert entry.source == SOURCE_QUALITY_FILES
    assert entry.status != STATUS_ERROR


def test_a_failed_php_save_journals_the_failure(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    php = tmp_path / "handler.php"
    php.write_text("<?php echo 1;", encoding="utf-8")
    tab = window._php_tabs.open_path(str(php))
    tab.editor.insertPlainText("\n// edited")
    from pgtp_editor.ui import modals

    monkeypatch.setattr(
        modals.QMessageBox, "critical", staticmethod(lambda *a, **k: None)
    )
    tab._writer = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))

    assert tab.save() is False

    entry = window.activity_log.entries[-1]
    assert entry.file_verb == FILE_VERB_SAVED
    assert entry.failed
    assert "disk full" in entry.error_full
