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

# pgtp_editor/ui/sql_results_panel.py
"""SqlResultsPanel: type one ad-hoc statement, run it **against the sandbox**,
and read what came back (§18.5's disposable sandbox; §29's "seeing a function's
results" open question).

The panel is the surface only. It **owns no connection and no
`SandboxSession`** and imports nothing from `db/sandbox.py`: the SQL text comes
from its editor (or an injected `sql_provider`), the run goes out through the
injected `on_execute(sql)` seam, and the answer comes back in as one
`db/sandbox_query.py::QueryResult` handed to `show_result`. That host --
`ui/sandbox_controller.py` and its off-GUI-thread `_run_async` -- is what holds
the session, which is what keeps execution sandbox-targeted; nothing here can
point a statement anywhere. Consequently there is deliberately **no
target/production affordance** on this panel at all.

**Three states, three different-looking answers,** taken from
`QueryOutcome` and never inferred from "is the grid empty?": rows (the grid,
plus a count), no result set (the driver's own `"UPDATE 3"`-style status, grid
hidden), and an error (the database's own message, in the error colour, grid
hidden). A `SELECT` that matched nothing therefore reads differently from an
`UPDATE`, because they are different answers.

**A Run is a sequence of statements, and the report says so** (§18.5 D4's
"every statement's `command_status` is listed in the status strip"). `show_run`
renders a `RunReport`: one status line per executed statement carrying **its
own** command status, the grid filled from the **last row-returning**
statement, and -- on a failure -- which statement failed, at which **buffer**
line, plus what did and did not run. `show_result` (one `QueryResult`) is still
the single-statement entry point and is unchanged.

**Truncation is shouted, not whispered.** When `QueryResult.truncated`, the
status line says so in the warning colour and names the cap -- a silently short
result set is a wrong answer, which is this project's worst failure class.

**NULL is not an empty string.** A NULL cell renders as an italic, dimmed
`NULL` (from the palette's `placeholderText` role); an empty string renders as
an empty cell. Getting these two to look alike is the classic grid bug, and it
makes the reader draw the wrong conclusion about their data.

Values are monospaced (digits and identifiers line up column-wise), every
colour is palette-derived so both the dark QSS and the light theme work, and no
`.exec()` is reachable from any path a test drives.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..db.sandbox_query import QueryOutcome, QueryResult, error_text, status_line

#: How a NULL prints. Upper-case, and additionally italic + dimmed below, so it
#: can never be mistaken for the four-character string `'NULL'` either.
NULL_TEXT = "NULL"

#: Shown before anything has been run. Names where the statement will go --
#: the sandbox, and only ever the sandbox.
IDLE_TEXT = "Nothing run yet — statements run against this project's sandbox database."

#: Refused before the seam is even called: an empty statement is a mistake, not
#: a query, and sending it would produce a confusing driver-level error.
EMPTY_SQL_TEXT = "Nothing to run — type a statement first."

#: The DbCheckPanel/CoherencePanel palette, kept verbatim so a failure looks the
#: same everywhere in the app. Foregrounds chosen to read against both themes;
#: every other colour here comes from `self.palette()`.
_ERROR_COLOR = QColor("#d02020")
_WARN_COLOR = QColor("#d08a1a")

#: No column is allowed to hog the panel just because one cell holds a 4 kB
#: `text` value -- content-sized up to here, then clamped (the full value stays
#: readable in the cell's tooltip).
_MAX_COLUMN_WIDTH = 320


#: How much of a statement is echoed when naming it in the status strip. Long
#: enough to recognise, short enough not to turn the strip into a second editor.
_ECHO_CHARS = 72


@dataclass(frozen=True)
class StatementRun:
    """One statement of a Run, and what the sandbox said about **it**.

    Pure data, so every sentence the status strip shows is assertable without a
    widget. Built by the console (`ui/sql_console_panel.py`) from a
    `sql/statements.py::Statement` plus the `QueryResult` that statement
    produced -- this panel never splits, classifies or executes anything.
    """

    #: 1-based position in the Run, as shown ("Statement 2 of 3").
    index: int
    #: The statement text exactly as it was sent.
    sql: str
    #: `sql/statements.py::classify_statement`'s verdict for `sql`.
    classification: str
    #: What came back.
    result: QueryResult
    #: 1-based line of the statement's first character **in the buffer**.
    start_line: int = 1
    #: 1-based line of the failure **in the buffer** -- `Statement.line_offset`
    #: plus `db/apply.py::line_of_position`, computed by the console because
    #: only the splitter knows the offset. None when the statement succeeded or
    #: the server reported no position: never a guessed line.
    error_line: int | None = None

    @property
    def ok(self) -> bool:
        return self.result.ok

    @property
    def echo(self) -> str:
        """The statement's first line, clipped -- what makes the statement the
        strip is talking about identifiable at a glance."""
        first = self.sql.strip().splitlines()[0] if self.sql.strip() else ""
        if len(first) > _ECHO_CHARS:
            return f"{first[:_ECHO_CHARS].rstrip()}…"
        return first


@dataclass(frozen=True)
class RunReport:
    """One Run gesture's complete answer: the statements that **executed**, in
    order, plus how many the Run contained.

    `total` is deliberately separate from `len(runs)`: a Run that aborted at
    statement 2 of 5 executed two statements and left three unrun, and both
    halves of that sentence have to be sayable.
    """

    runs: tuple[StatementRun, ...] = ()
    total: int = 0

    @property
    def failure(self) -> StatementRun | None:
        """The statement that failed, or None. At most one: a Run stops at the
        first failure, so a failure is never attributed to a later statement."""
        for run in self.runs:
            if not run.ok:
                return run
        return None

    @property
    def grid_run(self) -> StatementRun | None:
        """Whose rows the grid shows: the **last row-returning** statement
        (§18.5 D4). None when no statement in the Run returned a result set --
        in which case the grid stays hidden rather than showing a stale one."""
        for run in reversed(self.runs):
            if run.result.returns_rows:
                return run
        return None

    @property
    def committed(self) -> tuple[StatementRun, ...]:
        """The statements that ran successfully -- and, because each statement
        of a Run is its own committing `SandboxExecutor.fetch` call, therefore
        **committed**. Named for what actually happened, so the failure report
        can say what is still in the sandbox."""
        return tuple(run for run in self.runs if run.ok)

    @property
    def unrun(self) -> int:
        """How many statements the Run never reached (a failure aborts it)."""
        return max(self.total - len(self.runs), 0)


def statement_status(run: StatementRun) -> str:
    """One executed statement's line in the status strip.

    Always leads with **PostgreSQL's own command tag** when there is one, so a
    statement that returned no rows still says *what it did* (§18.5 D4:
    `SELECT 100`, `UPDATE 3`, `CREATE FUNCTION`) instead of contributing an
    empty grid. `db/sandbox_query.py::status_line` supplies the rest verbatim --
    one wording, not a second copy of it.
    """
    body = status_line(run.result)
    tag = (run.result.status or "").strip()
    if tag and run.result.outcome is QueryOutcome.ROWS:
        # NO_ROWS already carries the tag through `status_line`; ROWS does not.
        body = f"{tag} — {body}"
    return f"{run.index}. {body}"


def run_status_lines(report: RunReport) -> list[str]:
    """The whole status strip for one Run, as lines -- **pure**, so the exact
    sentences are testable without a widget.

    A failure produces three things, none of them optional: which statement
    failed (index **and** buffer line **and** an echo of the statement), the
    server's own message, and an honest statement of what is now in the
    sandbox. §18.5 D4 forbids leaving partial application of a multi-statement
    Run unmentioned, and each statement here really did commit on its own (see
    `RunReport.committed`).
    """
    if not report.runs:
        return []
    # Only the statements that RAN get a command-status line; the one that
    # failed is described by the attribution block instead, so its message is
    # not printed twice.
    lines = [statement_status(run) for run in report.runs if run.ok]
    failure = report.failure
    if failure is None:
        return lines
    where = (
        f"buffer line {failure.error_line}"
        if failure.error_line is not None
        else f"starting at buffer line {failure.start_line}"
    )
    lines.append(f"Error: {error_text(failure.result.error)}")
    lines.append(
        f"Statement {failure.index} of {report.total} FAILED — {where}"
        + (f" — {failure.echo}" if failure.echo else "")
    )
    done = len(report.committed)
    if done:
        noun = "statement" if done == 1 else "statements"
        lines.append(
            f"{done} earlier {noun} already ran and COMMITTED (each statement "
            "of a Run is its own transaction). Reset Sandbox re-establishes a "
            "known state."
        )
    if report.unrun:
        noun = "statement was" if report.unrun == 1 else "statements were"
        lines.append(f"The remaining {report.unrun} {noun} not run.")
    return lines


def render_value(value: Any) -> str:
    """How one cell prints. `None` -> `"NULL"`; everything else -> `str(value)`,
    including `""`, which prints as an empty cell. Pure, so the NULL-vs-empty
    distinction is assertable without a widget."""
    return NULL_TEXT if value is None else str(value)


def _monospace_font() -> QFont:
    font = QFont("Monospace")
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


class SqlResultsPanel(QWidget):
    """Editor + grid + status line for one ad-hoc sandbox statement.

    Constructor seams (all optional, all keyword-only):

    * `on_execute(sql) -> None` -- what Run calls. The host runs it off the GUI
      thread against its `SandboxSession` and calls `show_result` when done.
      **None (the default) means the panel cannot run anything**: Run is
      disabled, exactly like `SandboxController`'s missing confirmation seam
      refuses every destructive operation.
    * `sql_provider() -> str` -- where the statement text comes from, when it
      is not this panel's own editor (e.g. the active DDL tab's selection).
      Supplying it hides the built-in editor.

    Wiring surface: `run`, `show_result`, `clear`, `set_enabled`, the read-only
    `result`/`sql_text`, and `execute_requested`.
    """

    #: Emitted with the SQL actually being run, alongside calling `on_execute`
    #: -- so a host can mirror it in a status bar or log without displacing the
    #: callback seam.
    execute_requested = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        on_execute: Callable[[str], None] | None = None,
        sql_provider: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_execute = on_execute
        self._sql_provider = sql_provider
        self._result: QueryResult | None = None
        self._run_report: RunReport | None = None

        self.sql_edit = QPlainTextEdit()
        self.sql_edit.setPlaceholderText("SELECT … — runs against the sandbox")
        self.sql_edit.setFont(_monospace_font())
        self.sql_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # Only meaningful when this panel supplies the text; with a provider the
        # editor would be a second, contradicting source of truth.
        self.sql_edit.setVisible(sql_provider is None)

        self.run_button = QPushButton("Run")
        self.run_button.setToolTip(
            "Run the statement against this project's sandbox database. The "
            "sandbox is disposable — reset it to undo anything a statement did."
        )
        self.run_button.setEnabled(on_execute is not None)
        self.run_button.clicked.connect(lambda _checked=False: self.run())

        self.status_label = QLabel(IDLE_TEXT)
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.table = QTableWidget(0, 0)
        self.table.setFont(_monospace_font())
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.verticalHeader().setDefaultSectionSize(
            self.fontMetrics().height() + 6
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(True)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self.run_button)
        controls.addStretch(1)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(self.sql_edit, 1)
        top_layout.addLayout(controls)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addWidget(self.table, 1)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(top)
        self.splitter.addWidget(bottom)
        self.splitter.setStretchFactor(1, 3)

        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter, 1)

        self.clear()

    # -- state ---------------------------------------------------------------

    @property
    def result(self) -> QueryResult | None:
        """The result currently shown, or None before the first run."""
        return self._result

    @property
    def run_report(self) -> RunReport | None:
        """The multi-statement report currently shown, or None (before the
        first Run, or after a single-`QueryResult` `show_result`)."""
        return self._run_report

    @property
    def sql_text(self) -> str:
        """The statement Run would send: the injected provider's text, or this
        panel's editor. Stripped -- trailing whitespace is not a statement."""
        if self._sql_provider is not None:
            return self._sql_provider().strip()
        return self.sql_edit.toPlainText().strip()

    def set_enabled(self, enabled: bool, reason: str = "") -> None:
        """Enable/disable Run -- the host calls this from
        `SandboxController.session_changed`, since without a live session there
        is nothing to run against. A `reason` (which the host has, and this
        panel does not) replaces the status line, so a greyed-out button is
        never unexplained."""
        self.run_button.setEnabled(enabled and self._on_execute is not None)
        if reason:
            self._set_status(reason, _WARN_COLOR if not enabled else None)

    # -- running -------------------------------------------------------------

    def run(self) -> None:
        """Hand `sql_text` to the execute seam. Refuses an empty statement and
        a missing seam with a stated reason rather than doing nothing visible;
        never blocks and never touches a database itself."""
        if self._on_execute is None:
            self._set_status(
                "This panel has no sandbox to run against.", _WARN_COLOR
            )
            return
        sql = self.sql_text
        if not sql:
            self._set_status(EMPTY_SQL_TEXT, _WARN_COLOR)
            return
        self._set_status("Running…")
        self.execute_requested.emit(sql)
        self._on_execute(sql)

    # -- rendering -----------------------------------------------------------

    def show_result(self, result: QueryResult) -> None:
        """Render one `QueryResult` -- the single entry point for all three
        outcomes. The grid is shown only for a statement that returned a result
        set, so "no rows came back" and "no result set exists" stay visibly
        different answers."""
        self._result = result
        self._run_report = None
        if result.outcome is QueryOutcome.ERROR:
            self._clear_table()
            self.table.setVisible(False)
            self._set_status(status_line(result), _ERROR_COLOR)
            return
        if result.outcome is QueryOutcome.NO_ROWS:
            self._clear_table()
            self.table.setVisible(False)
            self._set_status(status_line(result))
            return

        self._fill_table(result)
        self.table.setVisible(True)
        self._set_status(
            status_line(result), _WARN_COLOR if result.truncated else None
        )

    def show_run(self, report: RunReport) -> None:
        """Render one whole Run (§18.5 D4): every executed statement's own
        command status in the strip, the **last row-returning** statement's rows
        in the grid, and -- on a failure -- which statement failed, where in the
        buffer, and what is nonetheless committed.

        The grid is filled from the row-returning statement even when a *later*
        statement failed, because those rows are a true answer to a statement
        that really ran; the failure sits above them in the strip, in the error
        colour, so it cannot be missed.
        """
        self._run_report = report
        grid_run = report.grid_run
        self._result = grid_run.result if grid_run is not None else (
            report.runs[-1].result if report.runs else None
        )
        text = "\n".join(run_status_lines(report)) or EMPTY_SQL_TEXT
        failure = report.failure
        if grid_run is None:
            self._clear_table()
            self.table.setVisible(False)
        else:
            self._fill_table(grid_run.result)
            self.table.setVisible(True)
        colour = None
        if failure is not None:
            colour = _ERROR_COLOR
        elif grid_run is not None and grid_run.result.truncated:
            colour = _WARN_COLOR
        self._set_status(text, colour)

    def report_notice(self, text: str, *, warning: bool = True) -> None:
        """Show one stated sentence with **no** result -- a refusal (a declined
        confirmation, a buffer holding nothing executable). The grid is cleared
        rather than left showing an older Run's rows, which would read as if
        this Run had produced them."""
        self._result = None
        self._run_report = None
        self._clear_table()
        self.table.setVisible(False)
        self._set_status(text, _WARN_COLOR if warning else None)

    def clear(self) -> None:
        """Back to the "nothing run yet" state (project closed, sandbox
        released). Leaves the typed SQL alone -- losing someone's statement
        because a session dropped would be its own bug."""
        self._result = None
        self._run_report = None
        self._clear_table()
        self.table.setVisible(False)
        self._set_status(IDLE_TEXT)

    def _clear_table(self) -> None:
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _fill_table(self, result: QueryResult) -> None:
        self._clear_table()
        self.table.setColumnCount(len(result.columns))
        self.table.setHorizontalHeaderLabels(list(result.columns))
        self.table.setRowCount(len(result.rows))
        null_brush = QBrush(self.palette().placeholderText().color())
        for row_index, row in enumerate(result.rows):
            for column_index in range(len(result.columns)):
                value = row[column_index] if column_index < len(row) else None
                self.table.setItem(
                    row_index,
                    column_index,
                    self._make_item(value, null_brush),
                )
        self._size_columns()

    def _make_item(self, value: Any, null_brush: QBrush) -> QTableWidgetItem:
        item = QTableWidgetItem(render_value(value))
        item.setToolTip(item.text())
        if value is None:
            # Three signals at once (word, italic, dimmed) so NULL can never be
            # confused with the empty string or with the literal text 'NULL'.
            item.setForeground(null_brush)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
        elif isinstance(value, bool) or isinstance(value, (int, float)):
            # Numbers read as numbers when their digits line up on the right.
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        return item

    def _size_columns(self) -> None:
        self.table.resizeColumnsToContents()
        for index in range(self.table.columnCount()):
            if self.table.columnWidth(index) > _MAX_COLUMN_WIDTH:
                self.table.setColumnWidth(index, _MAX_COLUMN_WIDTH)

    def _set_status(self, text: str, colour: QColor | None = None) -> None:
        self.status_label.setText(text)
        palette = self.status_label.palette()
        palette.setColor(
            self.status_label.foregroundRole(),
            colour if colour is not None else self.palette().windowText().color(),
        )
        self.status_label.setPalette(palette)
