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
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QSpinBox, QSplitter

from pgtp_editor.db.sandbox_query import QueryError, QueryOutcome, QueryResult
from pgtp_editor.ui.code_editor import CodeEditor
from pgtp_editor.ui.sql_console_panel import (
    DECLINED_TEXT,
    DEFAULT_ROW_LIMIT,
    MAX_ROW_LIMIT,
    MIN_ROW_LIMIT,
    NO_SESSION_TEXT,
    NOTHING_EXECUTABLE_TEXT,
    OBJECT_CHANGE_CONSEQUENCE,
    OBJECT_CHANGE_TITLE,
    UNKNOWN_CHANGE_TITLE,
    ObjectChangeConfirmation,
    SqlConsolePanel,
    as_confirmation,
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


class ScriptedQuery:
    """A `run_sandbox_query` stand-in that answers **per statement**, so a
    multi-statement Run can be asserted statement by statement.

    `answers` maps the statement text to the `QueryResult` it produces;
    anything unlisted comes back as a generic "completed, no result set" with a
    command tag derived from its leading keyword.
    """

    def __init__(self, answers: dict[str, QueryResult] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[tuple[object, str, int]] = []

    def __call__(self, session, sql, *, max_rows):
        self.calls.append((session, sql, max_rows))
        if sql in self.answers:
            return self.answers[sql]
        return QueryResult(
            outcome=QueryOutcome.NO_ROWS,
            sql=sql,
            status=sql.split()[0].upper() if sql.split() else "",
            elapsed_ms=1.0,
        )

    @property
    def statements(self) -> list[str]:
        return [sql for _session, sql, _rows in self.calls]


class RecordingConfirm:
    """The injected `confirm(title, text)` seam. Records every prompt and
    answers with a canned `ObjectChangeConfirmation` -- so no test ever reaches
    a modal (§30)."""

    def __init__(self, *, confirmed: bool = True, remember: bool = False) -> None:
        self.answer = ObjectChangeConfirmation(confirmed=confirmed, remember=remember)
        self.prompts: list[tuple[str, str]] = []

    def __call__(self, title, text):
        self.prompts.append((title, text))
        return self.answer


def make_console(
    qtbot,
    query: RecordingQuery | None = None,
    *,
    session=SESSION,
    confirm=None,
):
    query = query if query is not None else RecordingQuery()
    console = SqlConsolePanel(
        session_provider=lambda: session,
        run_query=query,
        run_async=sync_run_async,
        # Never the real dialog: an unwired seam would fall back to
        # `default_object_change_confirm`, which is a modal.
        confirm=confirm if confirm is not None else RecordingConfirm(),
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

    # The splitter strips the terminating `;` (and only that): what goes on the
    # wire is one statement, not a buffer fragment.
    assert query.calls[0][1] == "SELECT 1"


def test_an_error_renders_as_an_error_not_an_empty_grid(qtbot):
    failure = QueryResult.failed(
        "SELECT * FROM nope", 'relation "nope" does not exist'
    )
    console, _query = make_console(qtbot, RecordingQuery(failure))
    console.set_sql("SELECT * FROM nope")

    console.run()

    assert console.result is failure
    assert console.results.table.isVisibleTo(console.results) is False
    text = console.results.status_label.text()
    assert 'relation "nope" does not exist' in text
    assert text.lower().startswith("error")
    # And it is attributed: one statement, so statement 1 of 1.
    assert "Statement 1 of 1 FAILED" in text


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

    def known_columns(self, table):
        return {"app.invoice": ["amount", "id"], "public.users": ["email"]}.get(table, [])

    def column_entries(self, table, prefix=""):
        # The real `SchemaIndex.column_entries`: bare name as the KEY, the
        # richer one-line description as the DISPLAY.
        rows = {
            "app.invoice": [
                ("amount", "amount  numeric(12,2) · NOT NULL"),
                ("id", "id  integer · PK"),
            ],
            "public.users": [("email", "email  text")],
        }.get(table, [])
        return [row for row in rows if row[0].lower().startswith(prefix.lower())]


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


def _caret_after(console, marker):
    cursor = console.editor.textCursor()
    cursor.setPosition(console.sql_text.index(marker) + len(marker))
    console.editor.setTextCursor(cursor)


def test_ctrl_space_offers_an_aliased_tables_columns(qtbot):
    """FQ-030 slice 1, consumed here too: the console is where a FROM clause
    is most often hand-written, so `FROM app.invoice inv` ... `inv.` offers
    that table's columns."""
    console, _query = make_console(qtbot)
    console.set_schema_index(FakeIndex())
    console.set_sql("SELECT inv. FROM app.invoice inv")
    _caret_after(console, "SELECT inv.")

    console.show_completions()

    popup = console._completion_popup
    assert popup is not None
    # FQ-030 slice 0: the KEY is the bare column name -- what lands in the
    # buffer -- and the DISPLAY carries the type and the column's attributes.
    assert popup.visible_keys() == ["amount", "id"]
    assert [popup.item(i).text() for i in range(popup.count())] == [
        "amount  numeric(12,2) · NOT NULL",
        "id  integer · PK",
    ]


def test_an_alias_with_no_schema_falls_back_to_the_dotted_path_reading(qtbot):
    """`FROM invoice inv` writes no schema and nothing may guess a search
    path, so the refinement resolves to no table. The console must fall back to
    reading `inv` as a schema name (which offers nothing here) rather than
    silently swallow the caret or raise."""
    console, _query = make_console(qtbot)
    console.set_schema_index(FakeIndex())
    console.set_sql("SELECT inv. FROM invoice inv")
    _caret_after(console, "SELECT inv.")

    console.show_completions()

    assert console._completion_popup is None


def test_a_local_in_a_pasted_body_is_not_consumed_but_still_falls_through(qtbot):
    """`LOCAL_REF` is deliberately not a console context -- a console buffer is
    a script being sent, not a routine being edited. `caret_context` does
    descend into a pasted `$$` body, so the kind DOES come back; what is pinned
    here is that the unconsumed refinement degrades to the dotted-path reading
    instead of the guard turning into a dead branch."""
    console, _query = make_console(qtbot)
    console.set_schema_index(FakeIndex())
    console.set_sql(
        "CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $$\n"
        "DECLARE rec app.invoice%ROWTYPE;\n"
        "BEGIN\n"
        "  IF rec. THEN\n"
        "END;\n"
        "$$;\n"
    )
    _caret_after(console, "IF rec.")

    console.show_completions()

    assert console._completion_popup is None


def test_new_dot_is_still_not_a_console_context(qtbot):
    console, _query = make_console(qtbot)
    console.set_schema_index(FakeIndex())
    console.set_sql("SELECT new.")
    _caret_after(console, "new.")

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


# -- BUG-063: Format Selection's click-only command form --------------------


def test_the_context_menu_has_a_format_selection_entry(qtbot):
    """BUG-063: the console had the chord and no command. DEC-012 rests on this
    gesture HAVING a command form — that is why it sits under the one-keyboard-
    host rule rather than in DEC-009's menu-less family — and the console was the
    one surface where the command did not exist.

    `_build_context_menu` is driven directly and never `exec`ed (no test may
    reach a real modal `QMenu.exec`), which is the DDL object tab's shape."""
    console, _query = make_console(qtbot)

    labels = [action.text() for action in console._build_context_menu().actions()]

    assert "Format Selection" in labels
    # Nothing else was added: the console IS the run target, so there is no
    # `Run in Sandbox Console` bridge, and FQ-026 keeps apply gestures off this
    # kind of menu.
    assert "Run in Sandbox Console" not in labels
    assert not [label for label in labels if label.startswith("Apply")]


def test_the_context_menu_entry_follows_the_chords_selection_gate(qtbot):
    console, _query = make_console(qtbot)
    console.set_sql("select 1\nfrom t\n")

    def format_action(menu):
        return next(a for a in menu.actions() if a.text() == "Format Selection")

    assert format_action(console._build_context_menu()).isEnabled() is False

    cursor = console.editor.textCursor()
    cursor.select(cursor.SelectionType.Document)
    console.editor.setTextCursor(cursor)
    action = format_action(console._build_context_menu())

    assert action.isEnabled() is True
    action.trigger()
    assert "select 1" in console.sql_text


def test_the_menu_entry_is_click_only_and_hosts_no_shortcut(qtbot):
    """DEC-012 permits exactly ONE keyboard host per gesture, and the
    `QShortcut` in `__init__` is it. A `setShortcut` on this action would
    re-create the double-hosting the ruling exists to forbid — and it is the
    easiest thing for a later edit to break silently, hence the guard."""
    console, _query = make_console(qtbot)

    action = next(
        a
        for a in console._build_context_menu().actions()
        if a.text() == "Format Selection"
    )

    assert action.shortcut().isEmpty()
    assert console._format_shortcut.key() == QKeySequence("Ctrl+Alt+F")


# -- BUG-056: the undo/redo chords are stated here, not inherited from Qt ----


def _deliver(console, kind, key, mods):
    event = QKeyEvent(kind, key, mods)
    return console.eventFilter(console.editor, event), event


_CTRL = Qt.KeyboardModifier.ControlModifier
_CTRL_SHIFT = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
_ALT = Qt.KeyboardModifier.AltModifier


def test_the_console_claims_the_shortcut_override_for_the_reserved_chords(qtbot):
    """The half that stops the window-level shortcut. Without it `Ctrl+Y` on
    Linux fell through to `MainWindow`'s window `Ctrl+Y`, which returns at once
    because this is not the Raw XML tab (BUG-048's scoping) — no redo, no
    refusal, no journal line, while the same source redid the buffer on
    Windows."""
    console, _query = make_console(qtbot)

    for key, mods in (
        (Qt.Key.Key_Z, _CTRL),
        (Qt.Key.Key_Y, _CTRL),
        (Qt.Key.Key_Z, _CTRL_SHIFT),
        (Qt.Key.Key_Backspace, _ALT),
    ):
        consumed, event = _deliver(console, QEvent.Type.ShortcutOverride, key, mods)
        assert consumed is True, (key, mods)
        assert event.isAccepted() is True


def test_the_console_answers_undo_and_redo_from_its_own_stack(qtbot):
    """The other half: claiming without answering leaves the key dead. The
    console buffer is editable (unlike the DDL Explorer's), so the answer is its
    own undo stack rather than a refusal. Asserted through the FILTER — the
    offscreen platform runs Qt's Windows scheme, where the native path would pass
    for the wrong reason."""
    console, _query = make_console(qtbot)
    console.editor.setPlainText("select 1")
    console.editor.insertPlainText(" -- note")
    typed = console.sql_text

    consumed, _ = _deliver(console, QEvent.Type.KeyPress, Qt.Key.Key_Z, _CTRL)
    assert consumed is True
    assert console.sql_text != typed

    consumed, _ = _deliver(console, QEvent.Type.KeyPress, Qt.Key.Key_Y, _CTRL)
    assert consumed is True
    assert console.sql_text == typed


def test_the_console_claims_the_non_operation_chords_without_redoing(qtbot):
    """`Ctrl+Shift+Z` is no longer redo (DEC-015) and the `Alt+Backspace` pair is
    suppressed so the keyboard is identical on both systems. All three are
    consumed and none of them touches the buffer."""
    console, _query = make_console(qtbot)
    console.editor.setPlainText("select 1")
    console.editor.insertPlainText(" -- note")
    _deliver(console, QEvent.Type.KeyPress, Qt.Key.Key_Z, _CTRL)
    undone = console.sql_text

    for key, mods in (
        (Qt.Key.Key_Z, _CTRL_SHIFT),
        (Qt.Key.Key_Backspace, _ALT),
        (Qt.Key.Key_Backspace, _ALT | Qt.KeyboardModifier.ShiftModifier),
    ):
        consumed, _ = _deliver(console, QEvent.Type.KeyPress, key, mods)
        assert consumed is True, (key, mods)
        assert console.sql_text == undone


def test_the_console_filter_does_not_claim_unrelated_keys(qtbot):
    """The filter must not become a key sink -- the results table and the
    completion popup keep their own keys, and anything else falls through."""
    console, _query = make_console(qtbot)

    for key, mods in (
        (Qt.Key.Key_Z, Qt.KeyboardModifier.NoModifier),
        (Qt.Key.Key_A, _CTRL),
        (Qt.Key.Key_Backspace, Qt.KeyboardModifier.NoModifier),
    ):
        consumed, _ = _deliver(console, QEvent.Type.KeyPress, key, mods)
        assert consumed is False, (key, mods)


# -- §27's Ctrl+Return = Run -----------------------------------------------


def test_ctrl_return_shortcut_exists_and_is_scoped_to_the_panel(qtbot):
    """§27: Ctrl+Return = Run, Sandbox SQL Console tab ONLY. Scoped
    `WidgetWithChildrenShortcut`, the same mechanism (and for the same reason)
    as the panel's Ctrl+Space and Ctrl+Alt+F, so it cannot fire from an
    unrelated tab."""
    console, _query = make_console(qtbot)

    shortcut = console._run_shortcut
    assert shortcut.key() == QKeySequence("Ctrl+Return")
    assert shortcut.context() == Qt.ShortcutContext.WidgetWithChildrenShortcut
    assert shortcut.parent() is console


def test_ctrl_return_runs_once_through_the_same_run_gesture(qtbot):
    """It drives the panel's own `run()` -- the very method the results panel's
    Run button calls -- so there is exactly one execution path, not two."""
    console, query = make_console(qtbot)
    console.set_sql("SELECT 1")

    console._run_shortcut.activated.emit()

    assert query.calls == [(SESSION, "SELECT 1", DEFAULT_ROW_LIMIT)]
    assert console.result is query.result


def test_ctrl_return_is_refused_without_a_session_like_the_run_button(qtbot):
    """The shortcut adds no way around the sandbox-only boundary: with no
    session there is nothing to run against and nothing is sent."""
    console, query = make_console(qtbot, session=None)
    console.set_sql("SELECT 1")

    console._run_shortcut.activated.emit()

    assert query.calls == []
    assert console.results.status_label.text() == NO_SESSION_TEXT


# -- per-statement execution (§18.5 D4) ------------------------------------


def test_a_multi_statement_run_executes_each_statement_and_reports_its_status(qtbot):
    """§18.5 D4: the Run is split first, and **every** statement's own command
    status is listed -- so a statement returning no rows still says what it
    did, instead of contributing an empty grid."""
    selected = QueryResult(
        outcome=QueryOutcome.ROWS,
        sql="SELECT id FROM t",
        columns=("id",),
        rows=((1,), (2,)),
        status="SELECT 2",
        elapsed_ms=3.0,
    )
    query = ScriptedQuery(
        {
            "SELECT id FROM t": selected,
            "UPDATE t SET x = 1": QueryResult(
                outcome=QueryOutcome.NO_ROWS,
                sql="UPDATE t SET x = 1",
                status="UPDATE 3",
                affected=3,
                elapsed_ms=2.0,
            ),
        }
    )
    console, _query = make_console(qtbot, query)
    console.set_sql("SELECT id FROM t;\nUPDATE t SET x = 1;\nCREATE INDEX i ON t (x);")

    console.run()

    # One `run_query` call per statement, in order, terminators stripped.
    assert query.statements == [
        "SELECT id FROM t",
        "UPDATE t SET x = 1",
        "CREATE INDEX i ON t (x)",
    ]
    report = console.run_report
    assert report is not None
    assert report.total == 3
    assert [run.index for run in report.runs] == [1, 2, 3]
    assert report.failure is None

    text = console.results.status_label.text()
    assert "SELECT 2" in text
    assert "UPDATE 3" in text
    assert "3 rows affected" in text
    assert "CREATE" in text
    # The grid shows the last ROW-RETURNING statement's rows.
    assert console.result is selected
    assert console.results.table.rowCount() == 2


def test_a_dollar_quoted_routine_body_stays_one_statement(qtbot):
    """The case a naive splitter breaks: every `;` inside `$$`/`$tag$` belongs
    to the routine body, so this whole buffer is ONE statement."""
    body = (
        "CREATE OR REPLACE FUNCTION app.f() RETURNS int LANGUAGE plpgsql AS $$\n"
        "DECLARE n int;\n"
        "BEGIN\n"
        "  n := 1;\n"
        "  RAISE NOTICE 'a; b';\n"
        "  RETURN n;\n"
        "END;\n"
        "$$;\n"
        "CREATE OR REPLACE FUNCTION app.g() RETURNS int LANGUAGE plpgsql AS $tag$\n"
        "BEGIN RETURN 2; END;\n"
        "$tag$;"
    )
    query = ScriptedQuery()
    console, _query = make_console(qtbot, query)
    console.set_sql(body)

    console.run()

    assert len(query.statements) == 2
    assert query.statements[0].startswith("CREATE OR REPLACE FUNCTION app.f()")
    assert query.statements[0].endswith("$$")
    assert "RAISE NOTICE 'a; b'" in query.statements[0]
    assert query.statements[1].endswith("$tag$")
    assert console.run_report.total == 2


def test_a_failure_is_attributed_to_its_statement_and_its_buffer_line(qtbot):
    """Statement 2 fails; the report says statement **2**, and the line is the
    line in the BUFFER (`Statement.line_offset` + `line_of_position`), not the
    line inside the statement."""
    buffer = "SELECT 1;\nUPDATE t\n   SET x = 1/0;\nSELECT 3;"
    # Statement 2 is "UPDATE t\n   SET x = 1/0": its local line 2 is buffer
    # line 3. Position 13 (1-based) sits in that local line 2.
    failure = QueryResult.failed(
        "UPDATE t\n   SET x = 1/0",
        QueryError(message="division by zero", sqlstate="22012", position=13),
    )
    query = ScriptedQuery({"UPDATE t\n   SET x = 1/0": failure})
    console, _query = make_console(qtbot, query)
    console.set_sql(buffer)

    console.run()

    report = console.run_report
    assert report.total == 3
    # Aborted at the failure: statement 3 was never sent.
    assert query.statements == ["SELECT 1", "UPDATE t\n   SET x = 1/0"]
    assert report.failure.index == 2
    assert report.failure.error_line == 3
    assert report.failure.start_line == 2
    assert len(report.committed) == 1
    assert report.unrun == 1

    text = console.results.status_label.text()
    assert "Statement 2 of 3 FAILED" in text
    assert "buffer line 3" in text
    assert "division by zero" in text
    # The failing statement is identifiable, and the honest partial-commit
    # statement is present.
    assert "SET x = 1/0" in text or "UPDATE t" in text
    assert "COMMITTED" in text
    assert "not run" in text


def test_a_failure_without_a_position_reports_no_guessed_line(qtbot):
    failure = QueryResult.failed("DROP TABLE gone", QueryError(message="no such table"))
    query = ScriptedQuery({"DROP TABLE gone": failure})
    console, _query = make_console(qtbot, query)
    console.set_sql("SELECT 1;\nDROP TABLE gone;")

    console.run()

    run = console.run_report.failure
    assert run.index == 2
    assert run.error_line is None
    assert "starting at buffer line 2" in console.results.status_label.text()


def test_a_buffer_of_only_comments_is_refused_with_a_stated_reason(qtbot):
    console, query = make_console(qtbot)
    console.set_sql("-- nothing here\n/* not this either */")

    console.run()

    assert query.calls == []
    assert console.results.status_label.text() == NOTHING_EXECUTABLE_TEXT


# -- the ddl/unknown confirmation (§18.5 D4) -------------------------------


def test_a_read_only_run_asks_nothing(qtbot):
    confirm = RecordingConfirm()
    console, query = make_console(qtbot, ScriptedQuery(), confirm=confirm)
    console.set_sql("SELECT 1;\nWITH x AS (SELECT 1) SELECT * FROM x;\nEXPLAIN SELECT 1;")

    console.run()

    assert confirm.prompts == []
    assert len(query.statements) == 3


def test_a_write_only_run_asks_nothing(qtbot):
    """`INSERT`/`UPDATE`/`DELETE`/`TRUNCATE` change rows, not object
    definitions, so the object-desync prompt would state something untrue."""
    confirm = RecordingConfirm()
    console, query = make_console(qtbot, ScriptedQuery(), confirm=confirm)
    console.set_sql("INSERT INTO t VALUES (1);\nDELETE FROM t;\nTRUNCATE t;")

    console.run()

    assert confirm.prompts == []
    assert len(query.statements) == 3


def test_a_run_containing_ddl_asks_once_and_names_the_consequence(qtbot):
    confirm = RecordingConfirm()
    console, query = make_console(qtbot, ScriptedQuery(), confirm=confirm)
    console.set_sql("SELECT 1;\nCREATE TABLE t (id int);\nDROP TABLE t;")

    console.run()

    assert len(confirm.prompts) == 1
    title, text = confirm.prompts[0]
    assert title == OBJECT_CHANGE_TITLE
    assert OBJECT_CHANGE_CONSEQUENCE in text
    assert "Reset Sandbox" in text
    # It names WHICH statements, with their buffer lines.
    assert "Statement 2 (line 2" in text
    assert "Statement 3 (line 3" in text
    assert "could not" not in text  # both are genuinely DDL
    assert len(query.statements) == 3  # confirmed, so it all ran


def test_an_unknown_statement_says_the_classifier_could_not_tell(qtbot):
    """§18.5 D4: `unknown` is treated as `ddl`, but the prompt must NOT assert
    the statement is DDL -- it says the classifier could not tell."""
    confirm = RecordingConfirm()
    console, _query = make_console(qtbot, ScriptedQuery(), confirm=confirm)
    console.set_sql("SELECT 1;\nDO $$ BEGIN PERFORM 1; END $$;")

    console.run()

    title, text = confirm.prompts[0]
    assert title == UNKNOWN_CHANGE_TITLE
    assert "could not tell" in text
    assert "could not be classified" in text
    assert "changes objects in the sandbox." not in text
    assert OBJECT_CHANGE_CONSEQUENCE in text


def test_a_declined_confirmation_executes_nothing_at_all(qtbot):
    """Not even the Run's read statements: the user declined the Run."""
    confirm = RecordingConfirm(confirmed=False)
    console, query = make_console(qtbot, ScriptedQuery(), confirm=confirm)
    console.set_sql("SELECT 1;\nDROP TABLE t;")

    console.run()

    assert query.calls == []
    assert console.run_report is None
    assert console.result is None
    assert console.results.status_label.text() == DECLINED_TEXT
    assert console.is_running is False


def test_dont_ask_again_suppresses_the_prompt_for_this_session(qtbot):
    confirm = RecordingConfirm(confirmed=True, remember=True)
    console, query = make_console(qtbot, ScriptedQuery(), confirm=confirm)
    console.set_sql("DROP TABLE t;")

    console.run()
    assert len(confirm.prompts) == 1

    console.run()

    assert len(confirm.prompts) == 1  # asked once, for this session
    assert len(query.statements) == 2  # and both Runs executed


def test_a_new_sandbox_session_asks_again(qtbot):
    """The grant is scoped to ONE session: a different session re-asks."""
    confirm = RecordingConfirm(confirmed=True, remember=True)
    session = {"generation": 1}
    query = ScriptedQuery()
    console = SqlConsolePanel(
        session_provider=lambda: session,
        run_query=query,
        run_async=sync_run_async,
        confirm=confirm,
    )
    qtbot.addWidget(console)
    console.set_sql("DROP TABLE t;")

    console.run()
    assert len(confirm.prompts) == 1

    session = {"generation": 2}  # a new session object
    console.run()

    assert len(confirm.prompts) == 2


def test_losing_the_session_forgets_the_dont_ask_again_grant(qtbot):
    confirm = RecordingConfirm(confirmed=True, remember=True)
    console, _query = make_console(qtbot, ScriptedQuery(), confirm=confirm)
    console.set_sql("DROP TABLE t;")

    console.run()
    assert len(confirm.prompts) == 1

    console.set_session_available(False)
    console.set_session_available(True)
    console.run()

    assert len(confirm.prompts) == 2


def test_a_plain_boolean_confirm_seam_still_works_and_never_remembers(qtbot):
    """The seam signature is the codebase's `confirm(title, text) -> bool`; a
    host that offers no checkbox simply gets asked every time."""
    prompts = []

    def confirm(title, text):
        prompts.append(title)
        return True

    console, query = make_console(qtbot, ScriptedQuery(), confirm=confirm)
    console.set_sql("DROP TABLE t;")

    console.run()
    console.run()

    assert len(prompts) == 2
    assert len(query.statements) == 2


def test_as_confirmation_normalises_both_shapes_and_never_remembers_a_refusal():
    assert as_confirmation(True) == ObjectChangeConfirmation(True, False)
    assert as_confirmation(False) == ObjectChangeConfirmation(False, False)
    assert as_confirmation(
        ObjectChangeConfirmation(True, True)
    ) == ObjectChangeConfirmation(True, True)
    # "No, and don't ask again" must never suppress a refusal forever.
    assert as_confirmation(
        ObjectChangeConfirmation(False, True)
    ) == ObjectChangeConfirmation(False, False)


def test_there_is_no_statement_timeout_control_yet(qtbot):
    """§18.5 D4 asks for one, but `SandboxExecutor.fetch` has no parameter to
    pass it to, so the console does NOT fake one. Asserted so the gap stays
    visible rather than being quietly "implemented" as a no-op control."""
    console, _query = make_console(qtbot)

    assert not hasattr(console, "timeout_spin")
    assert not hasattr(console, "statement_timeout_ms")
