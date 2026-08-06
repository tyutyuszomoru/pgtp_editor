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

# tests/ui/test_sql_results_panel.py
"""Rendering tests for the ad-hoc SQL results panel.

Hand-built ``QueryResult``s only -- the panel owns no session and opens no
connection, so nothing here needs a database, a MainWindow or a modal.
"""
import pytest

from pgtp_editor.db.sandbox_query import QueryOutcome, QueryResult
from pgtp_editor.ui.sql_results_panel import (
    EMPTY_SQL_TEXT,
    IDLE_TEXT,
    NULL_TEXT,
    RunReport,
    SqlResultsPanel,
    StatementRun,
    render_value,
    run_status_lines,
    statement_status,
)


@pytest.fixture
def panel(qtbot):
    calls: list[str] = []
    widget = SqlResultsPanel(on_execute=calls.append)
    qtbot.addWidget(widget)
    widget.executed = calls
    return widget


def rows_result(**kwargs) -> QueryResult:
    base = dict(
        outcome=QueryOutcome.ROWS,
        sql="SELECT id, name FROM t",
        columns=("id", "name"),
        rows=((1, "alpha"), (2, None)),
        elapsed_ms=12.0,
    )
    base.update(kwargs)
    return QueryResult(**base)


# -- the grid --------------------------------------------------------------


def test_grid_renders_columns_and_rows(panel):
    panel.show_result(rows_result())

    assert panel.table.isVisible() or panel.table.isVisibleTo(panel)
    assert panel.table.columnCount() == 2
    assert panel.table.rowCount() == 2
    assert panel.table.horizontalHeaderItem(0).text() == "id"
    assert panel.table.horizontalHeaderItem(1).text() == "name"
    assert panel.table.item(0, 0).text() == "1"
    assert panel.table.item(0, 1).text() == "alpha"


def test_null_renders_distinctly_from_the_empty_string(panel):
    panel.show_result(
        rows_result(rows=((1, None), (2, ""), (3, "NULL")))
    )
    null_item = panel.table.item(0, 1)
    empty_item = panel.table.item(1, 1)
    literal_item = panel.table.item(2, 1)

    assert null_item.text() == NULL_TEXT
    assert empty_item.text() == ""
    assert null_item.text() != empty_item.text()
    # A NULL is also italic and dimmed, so it is distinguishable from the
    # four-character string 'NULL' too.
    assert null_item.font().italic() is True
    assert literal_item.font().italic() is False
    assert null_item.foreground().color() != literal_item.foreground().color()


def test_render_value_is_pure():
    assert render_value(None) == NULL_TEXT
    assert render_value("") == ""
    assert render_value(0) == "0"
    assert render_value(False) == "False"


def test_ragged_row_does_not_raise(panel):
    panel.show_result(rows_result(rows=((1,),)))
    assert panel.table.item(0, 1).text() == NULL_TEXT


# -- the three status-line states -----------------------------------------


def test_idle_status_before_anything_runs(qtbot):
    widget = SqlResultsPanel()
    qtbot.addWidget(widget)
    assert widget.status_label.text() == IDLE_TEXT
    assert widget.result is None


def test_status_line_for_rows(panel):
    panel.show_result(rows_result())
    text = panel.status_label.text()
    assert "2 rows" in text
    assert "12 ms" in text
    assert "TRUNCATED" not in text


def test_status_line_for_no_result_set(panel):
    panel.show_result(
        QueryResult(
            outcome=QueryOutcome.NO_ROWS,
            sql="UPDATE t SET x = 1",
            affected=3,
            status="UPDATE 3",
            elapsed_ms=4.0,
        )
    )
    text = panel.status_label.text()
    assert "UPDATE 3" in text
    assert "no result set" in text
    # Grid stays hidden: "no result set" must not look like "zero rows".
    assert not panel.table.isVisibleTo(panel)
    assert panel.table.rowCount() == 0


def test_status_line_for_an_error(panel):
    panel.show_result(
        QueryResult.failed("SELECT * FROM nope", 'ERROR: relation "nope" does not exist')
    )
    text = panel.status_label.text()
    assert 'relation "nope" does not exist' in text
    assert not panel.table.isVisibleTo(panel)


def test_error_after_rows_clears_the_stale_grid(panel):
    panel.show_result(rows_result())
    panel.show_result(QueryResult.failed("boom", "ERROR: boom"))
    assert panel.table.rowCount() == 0
    assert panel.table.columnCount() == 0


def test_truncation_is_visible(panel):
    panel.show_result(rows_result(truncated=True, max_rows=1, rows=((1, "alpha"),)))
    text = panel.status_label.text()
    assert "TRUNCATED" in text
    assert "1" in text


def test_truncation_is_coloured_differently_from_a_plain_result(panel):
    panel.show_result(rows_result())
    plain = panel.status_label.palette().color(panel.status_label.foregroundRole())
    panel.show_result(rows_result(truncated=True))
    warned = panel.status_label.palette().color(panel.status_label.foregroundRole())
    assert plain != warned


# -- the execute seam ------------------------------------------------------


def test_execute_seam_receives_the_typed_sql(panel, qtbot):
    panel.sql_edit.setPlainText("  SELECT 1;  ")
    with qtbot.waitSignal(panel.execute_requested) as blocker:
        panel.run_button.click()
    assert panel.executed == ["SELECT 1;"]
    assert blocker.args == ["SELECT 1;"]


def test_empty_sql_is_refused_before_the_seam(panel):
    panel.sql_edit.setPlainText("   ")
    panel.run()
    assert panel.executed == []
    assert panel.status_label.text() == EMPTY_SQL_TEXT


def test_injected_sql_provider_wins_and_hides_the_editor(qtbot):
    calls: list[str] = []
    widget = SqlResultsPanel(on_execute=calls.append, sql_provider=lambda: "SELECT 42")
    qtbot.addWidget(widget)
    widget.sql_edit.setPlainText("ignored")
    widget.run()
    assert calls == ["SELECT 42"]
    assert not widget.sql_edit.isVisibleTo(widget)


def test_without_an_execute_seam_the_panel_cannot_run(qtbot):
    widget = SqlResultsPanel()
    qtbot.addWidget(widget)
    assert widget.run_button.isEnabled() is False
    widget.sql_edit.setPlainText("SELECT 1")
    widget.run()  # states a reason rather than doing nothing
    assert widget.status_label.text() != IDLE_TEXT


def test_set_enabled_gates_run_and_states_a_reason(panel):
    panel.set_enabled(False, "no sandbox session is open")
    assert panel.run_button.isEnabled() is False
    assert panel.status_label.text() == "no sandbox session is open"
    panel.set_enabled(True)
    assert panel.run_button.isEnabled() is True


def test_clear_returns_to_idle_but_keeps_the_typed_sql(panel):
    panel.sql_edit.setPlainText("SELECT 1")
    panel.show_result(rows_result())
    panel.clear()
    assert panel.result is None
    assert panel.status_label.text() == IDLE_TEXT
    assert panel.table.rowCount() == 0
    assert panel.sql_edit.toPlainText() == "SELECT 1"


def test_panel_imports_nothing_that_can_open_a_connection(panel):
    """The panel's whole safety story: it cannot target anything itself. It
    knows the result model and nothing about sessions, params or executors."""
    import pgtp_editor.ui.sql_results_panel as module

    exported = vars(module)
    for name in ("SandboxSession", "ConnectionParams", "open_sandbox", "psycopg"):
        assert name not in exported
    assert not hasattr(panel, "session")
    assert not hasattr(panel, "params")


# -- a whole Run: RunReport rendering (§18.5 D4) ----------------------------


def make_run(index, sql, result, *, start_line=1, error_line=None, kind="read"):
    return StatementRun(
        index=index,
        sql=sql,
        classification=kind,
        result=result,
        start_line=start_line,
        error_line=error_line,
    )


def no_rows(status, **kwargs) -> QueryResult:
    base = dict(outcome=QueryOutcome.NO_ROWS, sql="", status=status, elapsed_ms=1.0)
    base.update(kwargs)
    return QueryResult(**base)


def test_statement_status_leads_with_postgresqls_own_command_tag():
    """A row-returning statement's tag is not in `status_line`, so it is added;
    a no-result-set statement already carries it and must not get it twice."""
    with_rows = make_run(1, "SELECT id FROM t", rows_result(status="SELECT 2"))
    assert statement_status(with_rows).startswith("1. SELECT 2 — 2 rows")

    updated = make_run(2, "UPDATE t SET x = 1", no_rows("UPDATE 3", affected=3))
    line = statement_status(updated)
    assert line.startswith("2. UPDATE 3")
    assert line.count("UPDATE 3") == 1


def test_run_status_lines_list_every_statement_when_all_succeed():
    report = RunReport(
        runs=(
            make_run(1, "SELECT id FROM t", rows_result(status="SELECT 2")),
            make_run(2, "UPDATE t SET x = 1", no_rows("UPDATE 3", affected=3)),
            make_run(3, "CREATE INDEX i ON t (x)", no_rows("CREATE INDEX")),
        ),
        total=3,
    )

    lines = run_status_lines(report)

    assert len(lines) == 3
    assert "SELECT 2" in lines[0]
    assert "UPDATE 3" in lines[1]
    assert "CREATE INDEX" in lines[2]
    assert report.failure is None


def test_run_status_lines_attribute_the_failure_and_state_what_committed():
    failing = QueryResult.failed("UPDATE t SET x = 1/0", "division by zero")
    report = RunReport(
        runs=(
            make_run(1, "SELECT 1", no_rows("SELECT 1")),
            make_run(2, "UPDATE t SET x = 1/0", failing, start_line=2, error_line=3),
        ),
        total=4,
    )

    lines = run_status_lines(report)
    joined = "\n".join(lines)

    assert "division by zero" in joined
    assert "Statement 2 of 4 FAILED — buffer line 3" in joined
    assert "UPDATE t SET x = 1/0" in joined  # identifiable
    assert "COMMITTED" in joined
    assert "remaining 2 statements were not run" in joined
    # The failing statement is described once, not also as a command status.
    assert not any(line.startswith("2. ") for line in lines)


def test_show_run_fills_the_grid_from_the_last_row_returning_statement(panel):
    last_rows = rows_result(columns=("n",), rows=((7,),), status="SELECT 1")
    report = RunReport(
        runs=(
            make_run(1, "SELECT id, name FROM t", rows_result(status="SELECT 2")),
            make_run(2, "SELECT n FROM u", last_rows),
            make_run(3, "UPDATE t SET x = 1", no_rows("UPDATE 3", affected=3)),
        ),
        total=3,
    )

    panel.show_run(report)

    assert panel.run_report is report
    assert panel.result is last_rows
    assert panel.table.isVisibleTo(panel) is True
    assert panel.table.columnCount() == 1
    assert panel.table.item(0, 0).text() == "7"
    assert "UPDATE 3" in panel.status_label.text()


def test_show_run_hides_the_grid_when_no_statement_returned_rows(panel):
    report = RunReport(
        runs=(make_run(1, "CREATE TABLE t (id int)", no_rows("CREATE TABLE")),),
        total=1,
    )

    panel.show_run(report)

    assert panel.table.isVisibleTo(panel) is False
    assert "CREATE TABLE" in panel.status_label.text()


def test_report_notice_clears_any_previous_result(panel):
    panel.show_result(rows_result())
    assert panel.result is not None

    panel.report_notice("Run cancelled — nothing was executed.")

    assert panel.result is None
    assert panel.run_report is None
    assert panel.table.isVisibleTo(panel) is False
    assert panel.status_label.text().startswith("Run cancelled")


def test_show_result_clears_a_previous_run_report(panel):
    panel.show_run(
        RunReport(runs=(make_run(1, "SELECT 1", rows_result()),), total=1)
    )
    assert panel.run_report is not None

    panel.show_result(rows_result())

    assert panel.run_report is None
