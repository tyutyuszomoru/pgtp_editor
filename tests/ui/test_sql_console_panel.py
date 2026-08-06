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

# tests/ui/test_sql_console_panel.py
"""Tests for the Sandbox SQL Console panel (§18.5 D4).

The execution seam (`run_query`) and the off-thread seam (`run_async`) are both
injected, so nothing here opens a connection, hits a server or reaches a modal.
The "session" is an opaque sentinel: the panel must hand it straight to
`run_query` and never inspect it, which is exactly the structural
sandbox-only boundary (a `SandboxSession`, never `ConnectionParams`).
"""
import pytest
from PySide6.QtWidgets import QSpinBox, QSplitter

from pgtp_editor.db.sandbox_query import QueryOutcome, QueryResult
from pgtp_editor.ui.code_editor import CodeEditor
from pgtp_editor.ui.sql_console_panel import (
    DEFAULT_ROW_LIMIT,
    MAX_ROW_LIMIT,
    MIN_ROW_LIMIT,
    NO_SESSION_TEXT,
    SqlConsolePanel,
)
from pgtp_editor.ui.sql_results_panel import SqlResultsPanel

SESSION = object()  # stands in for a SandboxSession; never inspected


def sync_run_async(fn, on_result, on_error=None, **_kwargs):
    """A synchronous stand-in for `ui/async_task.py::run_async`, the
    SandboxController convention -- the GUI thread is never actually left, and
    the test never waits on a worker."""
    try:
        value = fn()
    except BaseException as exc:  # noqa: BLE001 -- mirrors run_async's contract
        if on_error is not None:
            on_error(exc)
        return None
    on_result(value)
    return None


class RecordingQuery:
    """A `run_sandbox_query` stand-in: records its arguments and returns a
    canned `QueryResult`."""

    def __init__(self, result: QueryResult | None = None) -> None:
        self.result = result if result is not None else rows_result()
        self.calls: list[tuple[object, str, int]] = []

    def __call__(self, session, sql, *, max_rows):
        self.calls.append((session, sql, max_rows))
        return self.result


def rows_result(**kwargs) -> QueryResult:
    base = dict(
        outcome=QueryOutcome.ROWS,
        sql="SELECT id, name FROM t",
        columns=("id", "name"),
        rows=((1, "alpha"), (2, "beta")),
        elapsed_ms=7.0,
    )
    base.update(kwargs)
    return QueryResult(**base)


def make_console(qtbot, query: RecordingQuery | None = None, *, session=SESSION):
    query = query if query is not None else RecordingQuery()
    console = SqlConsolePanel(
        session_provider=lambda: session,
        run_query=query,
        run_async=sync_run_async,
    )
    qtbot.addWidget(console)
    return console, query


# -- composition -----------------------------------------------------------


def test_splitter_holds_the_sql_editor_above_the_results_panel(qtbot):
    console, _query = make_console(qtbot)

    assert isinstance(console.splitter, QSplitter)
    assert console.splitter.count() == 2
    assert console.splitter.widget(0) is console.editor
    assert console.splitter.widget(1) is console.results
    assert isinstance(console.editor, CodeEditor)
    assert isinstance(console.results, SqlResultsPanel)


def test_the_editor_is_the_single_source_of_the_statement_text(qtbot):
    """The results panel is given a `sql_provider`, so it hides its own editor
    rather than becoming a second, contradicting source."""
    console, _query = make_console(qtbot)

    assert console.results.sql_edit.isVisibleTo(console.results) is False
    console.set_sql("SELECT 1")
    assert console.results.sql_text == "SELECT 1"


def test_there_is_no_target_database_affordance_anywhere(qtbot):
    """§18.5 D4's boundary: not even a disabled "run against target" control."""
    console, _query = make_console(qtbot)

    labels = [
        child.text().lower()
        for child in console.findChildren(object)
        if hasattr(child, "text") and isinstance(getattr(child, "text")(), str)
    ]
    assert not any("target" in label for label in labels)
    assert not any("production" in label for label in labels)


# -- the row cap -----------------------------------------------------------


def test_row_limit_spin_box_default_and_bounds(qtbot):
    console, _query = make_console(qtbot)

    assert isinstance(console.row_limit_spin, QSpinBox)
    assert DEFAULT_ROW_LIMIT == 1000
    assert console.row_limit() == DEFAULT_ROW_LIMIT
    assert console.row_limit_spin.minimum() == MIN_ROW_LIMIT
    assert console.row_limit_spin.maximum() == MAX_ROW_LIMIT == 100_000


def test_row_limit_clamps_and_offers_no_unlimited_setting(qtbot):
    console, _query = make_console(qtbot)

    console.set_row_limit(0)
    assert console.row_limit() == MIN_ROW_LIMIT
    console.set_row_limit(10_000_000)
    assert console.row_limit() == MAX_ROW_LIMIT


def test_the_row_limit_in_force_is_the_one_passed_down(qtbot):
    console, query = make_console(qtbot)
    console.set_row_limit(25)
    console.set_sql("SELECT 1")

    console.run()

    assert query.calls == [(SESSION, "SELECT 1", 25)]


# -- running ---------------------------------------------------------------


def test_successful_query_renders_columns_and_rows(qtbot):
    console, query = make_console(qtbot)
    console.set_sql("SELECT id, name FROM t")

    console.run()

    table = console.results.table
    assert table.columnCount() == 2
    assert table.rowCount() == 2
    assert table.horizontalHeaderItem(0).text() == "id"
    assert table.item(0, 1).text() == "alpha"
    assert console.result is query.result
    assert console.is_running is False


def test_the_run_gesture_sends_the_selection_when_there_is_one(qtbot):
    console, query = make_console(qtbot)
    console.set_sql("SELECT 1;\nSELECT 2;")
    cursor = console.editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(len("SELECT 1;"), cursor.MoveMode.KeepAnchor)
    console.editor.setTextCursor(cursor)

    console.run()

    assert query.calls[0][1] == "SELECT 1;"


def test_an_error_renders_as_an_error_not_an_empty_grid(qtbot):
    failure = QueryResult.failed(
        "SELECT * FROM nope", 'relation "nope" does not exist'
    )
    console, _query = make_console(qtbot, RecordingQuery(failure))
    console.set_sql("SELECT * FROM nope")

    console.run()

    assert console.result is failure
    assert console.results.table.isVisibleTo(console.results) is False
    assert 'relation "nope" does not exist' in console.results.status_label.text()
    assert console.results.status_label.text().lower().startswith("error")


def test_a_no_rows_statement_reports_its_command_status(qtbot):
    """PostgreSQL's own tag, so a statement returning no result set still says
    WHAT IT DID instead of showing an empty grid."""
    completed = QueryResult(
        outcome=QueryOutcome.NO_ROWS,
        sql="UPDATE t SET x = 1",
        status="UPDATE 3",
        affected=3,
        elapsed_ms=4.0,
    )
    console, _query = make_console(qtbot, RecordingQuery(completed))
    console.set_sql("UPDATE t SET x = 1")

    console.run()

    text = console.results.status_label.text()
    assert "UPDATE 3" in text
    assert "3 rows affected" in text
    assert console.results.table.isVisibleTo(console.results) is False


def test_a_seam_level_exception_still_arrives_as_an_error_result(qtbot):
    def boom(session, sql, *, max_rows):
        raise RuntimeError("thread pool exploded")

    console = SqlConsolePanel(
        session_provider=lambda: SESSION,
        run_query=boom,
        run_async=sync_run_async,
    )
    qtbot.addWidget(console)
    console.set_sql("SELECT 1")

    console.run()

    assert console.result is not None
    assert console.result.outcome is QueryOutcome.ERROR
    assert "thread pool exploded" in console.result.error
    assert console.is_running is False


# -- truncation ------------------------------------------------------------


def test_truncation_is_reported_from_the_truncated_field(qtbot):
    truncated = rows_result(
        rows=tuple((n,) for n in range(3)),
        columns=("n",),
        truncated=True,
        max_rows=3,
    )
    console, _query = make_console(qtbot, RecordingQuery(truncated))
    console.set_sql("SELECT n FROM big")

    console.run()

    assert "TRUNCATED" in console.results.status_label.text()


def test_a_result_exactly_at_the_cap_is_not_reported_as_truncated(qtbot):
    """The whole reason `truncated` is a first-class field: `len(rows) ==
    max_rows` must NEVER be read as "there was more"."""
    exactly_at_cap = rows_result(
        rows=tuple((n,) for n in range(3)),
        columns=("n",),
        truncated=False,
        max_rows=3,
    )
    console, _query = make_console(qtbot, RecordingQuery(exactly_at_cap))
    console.set_sql("SELECT n FROM big LIMIT 3")

    console.run()

    text = console.results.status_label.text()
    assert "TRUNCATED" not in text
    assert "3 rows" in text
    assert console.results.table.rowCount() == 3


# -- session availability --------------------------------------------------


def test_without_a_session_provider_run_is_refused_with_a_stated_reason(qtbot):
    console = SqlConsolePanel(run_async=sync_run_async)
    qtbot.addWidget(console)

    assert console.results.run_button.isEnabled() is False
    assert console.results.status_label.text() == NO_SESSION_TEXT


def test_a_provider_returning_none_refuses_the_run_and_says_why(qtbot):
    console, query = make_console(qtbot, session=None)
    console.set_sql("SELECT 1")

    console.run()

    assert query.calls == []
    assert console.results.status_label.text() == NO_SESSION_TEXT
    assert console.results.run_button.isEnabled() is False


def test_set_session_available_toggles_run(qtbot):
    console, _query = make_console(qtbot)

    console.set_session_available(False)
    assert console.results.run_button.isEnabled() is False
    assert console.results.status_label.text() == NO_SESSION_TEXT

    console.set_session_available(True)
    assert console.results.run_button.isEnabled() is True


def test_an_empty_buffer_is_refused_before_the_seam_is_called(qtbot):
    console, query = make_console(qtbot)

    console.run()

    assert query.calls == []


# -- host-facing text plumbing --------------------------------------------


def test_set_sql_replaces_and_append_sql_adds_without_destroying(qtbot):
    """The object tab's "Run in Sandbox Console" bridge pushes text in and
    executes nothing."""
    console, query = make_console(qtbot)

    console.set_sql("SELECT 1;")
    assert console.sql_text == "SELECT 1;"
    console.append_sql("SELECT 2;")
    assert "SELECT 1;" in console.sql_text
    assert "SELECT 2;" in console.sql_text
    assert query.calls == []  # pushing text never runs anything


def test_clear_resets_the_results_but_keeps_the_typed_sql(qtbot):
    console, _query = make_console(qtbot)
    console.set_sql("SELECT 1")
    console.run()
    assert console.result is not None

    console.clear()

    assert console.result is None
    assert console.sql_text == "SELECT 1"


# -- §18.6 completion / §18.4 formatting -----------------------------------


class FakeIndex:
    def known_schemas(self):
        return ["app", "public"]

    def known_tables(self, schema, prefix=""):
        tables = {"app": ["invoice", "item"], "public": ["users"]}.get(schema, [])
        return [t for t in tables if t.lower().startswith(prefix.lower())]


def test_schema_index_is_injected_the_same_way_an_object_tab_gets_it(qtbot):
    console, _query = make_console(qtbot)
    assert console.schema_index() is None

    index = FakeIndex()
    console.set_schema_index(index)
    assert console.schema_index() is index


def test_ctrl_space_offers_schema_qualified_tables(qtbot):
    console, _query = make_console(qtbot)
    console.set_schema_index(FakeIndex())
    console.set_sql("SELECT * FROM app.i")
    cursor = console.editor.textCursor()
    cursor.setPosition(len("SELECT * FROM app.i"))
    console.editor.setTextCursor(cursor)

    console.show_completions()

    popup = console._completion_popup
    assert popup is not None
    # The popup lists the schema-qualified insertion values -- the same
    # (label, value) pairing a DDL object tab passes it.
    assert [popup.item(i).text() for i in range(popup.count())] == [
        "app.invoice",
        "app.item",
    ]


def test_ctrl_space_is_a_no_op_without_a_schema_index(qtbot):
    console, _query = make_console(qtbot)
    console.set_sql("SELECT * FROM app.i")

    console.show_completions()

    assert console._completion_popup is None


def test_format_selection_requires_a_selection_and_reindents_in_place(qtbot):
    console, _query = make_console(qtbot)
    console.set_sql("select 1\nfrom t\n")

    console.format_selection()  # no selection: no-op
    assert console.sql_text == "select 1\nfrom t\n"

    cursor = console.editor.textCursor()
    cursor.select(cursor.SelectionType.Document)
    console.editor.setTextCursor(cursor)
    console.format_selection()

    assert "select 1" in console.sql_text
