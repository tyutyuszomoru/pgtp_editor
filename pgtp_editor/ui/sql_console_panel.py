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

# pgtp_editor/ui/sql_console_panel.py
"""`SqlConsolePanel`: the Sandbox SQL Console (§18.5 D4) -- one center tab where
the user types ad-hoc SQL, presses Run, and reads what the **sandbox** said.

**The safety boundary, restated because it is the whole design** (§18.5 D4's
"read this first"): ad-hoc execution is sandbox-only and can never target the
production/target database -- not behind a confirmation, not behind a
preference. The boundary is *structural*: this panel never builds
`ConnectionParams` and never opens a connection; it hands SQL to
`db/sandbox_query.py::run_sandbox_query`, whose first parameter is a
`SandboxSession` (creatable only through `db/sandbox.py::open_sandbox`, the
single ownership gate). The session itself is not held here either -- it is
fetched, at Run time, from the injected `session_provider` seam, which the host
(`ui/sandbox_controller.py`) backs with its own live session. **There is
deliberately no "run against target" affordance anywhere in this file, not even
a disabled one.** Adding one requires a spec change and a Supersession Ledger
row.

**What it is made of, all reuse:** a vertical `QSplitter` with
`ui/code_editor.py::CodeEditor(language="sql")` on top (the same SQL
highlighter over `sql/keywords.py`'s single dialect source, the same gutter
mixin) and `ui/sql_results_panel.py::SqlResultsPanel` at the bottom (the grid
plus its one-line status strip). The results panel is constructed with a
`sql_provider`, which is exactly how it is told *"your text comes from
elsewhere"* -- so its built-in editor hides itself and this console's
`CodeEditor` is the single source of the statement text. §18.6's `SchemaIndex`
is injected via `set_schema_index`, the same way an object tab receives it, so
Ctrl+Space works here; §18.4's Format Selection (`Ctrl+Alt+F`) is available on
the same selection-only terms, through the same `sql/formatter.py` function.

**Truncation is a fact, never a guess.** The row cap lives in this console's
own spin box (`DEFAULT_ROW_LIMIT`, bounded by `MAX_ROW_LIMIT`, with no
"unlimited" option) and is passed down as `max_rows`; whether the result *was*
cut off is read from `QueryResult.truncated`, which `run_sandbox_query`
establishes by fetching one row past the cap. A result sitting exactly on the
cap and a result that was cut off therefore stay distinguishable -- reporting a
truncated set as complete is the silent-wrong-result class this project
refuses.

**A Run is split into statements first, and every one of them reports.** The
buffer (or selection) goes through the pure `sql/statements.py::split_statements`
-- built on §18.4's tokenizer, so a `;` inside a string, a comment or a
`$$ … $$` routine body never splits anything -- and each statement is executed
in order through the **same** `run_query` seam. Each carries its own command
status into the status strip (`SELECT 100`, `UPDATE 3`, `CREATE FUNCTION`), the
grid shows the last row-returning statement, and a failure is attributed to the
statement that produced it: **its index and its buffer line**, via
`Statement.line_offset + db/apply.py::line_of_position` -- the one
implementation of that rule.

**Transaction discipline, stated because it diverges from the spec's wording.**
§18.5 D4 asks for all statements of a Run in *one* transaction that commits.
The sanctioned seam is `db/sandbox.py::SandboxExecutor.fetch`, which is
documented as *"run **one** statement … commits on success"* and opens one
connection per call, so **each statement of a Run is its own committing
transaction**. The seam that does span statements atomically (`execute`) returns
no rows and no status message, so it cannot answer D4's own requirements (a
grid, plus each statement's command status). Rather than reach into `db/` from
the UI, the console runs statement-by-statement, **stops at the first failure**,
and *says* what already committed -- the one thing D4 forbids is leaving partial
application unmentioned.

**Object-changing statements ask first.** When any statement classifies as
`ddl` or `unknown` (`sql/statements.py::CHANGES_OBJECTS`, the single home of
"unknown is treated as ddl"), the Run is gated behind the injected
`confirm(title, text)` seam -- exactly the Apply gestures' seam, so no test can
reach a modal (§30) -- naming that the sandbox's applied working set may no
longer match what the open tabs believe, and that Reset Sandbox re-establishes a
known state. The prompt says the classifier *could not tell* for `unknown`
rather than asserting DDL. Answering with `remember` set suppresses the question
**for that sandbox session only**: a new session asks again.

**Nothing blocks the GUI thread and nothing here reaches a modal.** The query
goes out through the injected `run_async` seam (`ui/async_task.py::run_async`
by default, a synchronous stub in tests), Run is disabled while a run is in
flight, and a failure comes back as a `QueryResult` carrying the database's own
message -- never an empty grid.

**Still missing from D4, deliberately, and reported rather than faked:** the
mandatory per-statement timeout. `SandboxExecutor.fetch(params, sql, *,
max_rows)` has no timeout parameter, so there is nowhere for the UI to pass one;
inventing a channel here would change the `db/` contract from the UI. There is
likewise no Cancel button (D4's own stated gap).
"""
from __future__ import annotations

import weakref
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..db.apply import line_of_position
from ..db.sandbox_query import (
    DEFAULT_MAX_ROWS,
    QueryResult,
    run_sandbox_query,
)
from ..sql.caret_context import ALIAS_REF, DOTTED_PATH, LOCAL_REF, resolve_caret_context
from ..sql.formatter import format_selection as _format_selection_text
from ..sql.statements import (
    CHANGES_OBJECTS,
    UNKNOWN,
    Statement,
    classify_statement,
    split_statements,
)
from .async_task import run_async
from .code_editor import (
    REDO,
    UNDO,
    CodeEditor,
    apply_editor_operation,
    classify_editor_chord,
    is_mutating_editor_operation,
)
from .completion_popup import CompletionPopupHostMixin
from .expand_select_seam import expand_select_expansion
from .format_settings import current_sql_config
from .schema_gesture_seam import SchemaGestureHostMixin
from .sql_results_panel import RunReport, SqlResultsPanel, StatementRun

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..db.sandbox import SandboxSession
    from ..db.schema_index import SchemaIndex

#: The center-tab key this console is registered under in `CenterStage`'s
#: key -> widget map (§7's append-only/tail-only dynamic tabs). Single-instance:
#: re-invoking the command focuses this tab rather than opening a second console.
CONSOLE_TAB_KEY = ("sandbox-sql",)

#: The tab label.
TAB_TITLE = "Sandbox SQL"

#: The row cap in force when the console opens -- §18.5 D4's stated choice,
#: taken from `db/sandbox_query.py` rather than re-declared, so there is one
#: number and not two that can drift apart.
DEFAULT_ROW_LIMIT = DEFAULT_MAX_ROWS

#: The largest cap the spin box offers. **There is no "unlimited" option**: an
#: unbounded `SELECT *` over a production-sized clone would freeze or OOM the
#: app, and a grid holding a million tuples is unusable anyway.
MAX_ROW_LIMIT = 100_000

#: The smallest cap. One row is a legitimate "just show me the shape" request;
#: zero rows would make every result look truncated and answer nothing.
MIN_ROW_LIMIT = 1

#: Why Run is refused with no live sandbox. Names the way back, the way every
#: other §18.5 degradation does -- never a bare "unavailable".
#:
#: It must name a place the user can actually REACH from here, which is why it
#: no longer says `Database ▸ Sandbox Setup…` -- that entry was DELETED on
#: 2026-08-09 and its gestures moved into Project Settings. The session itself
#: is no longer something to "open" at all (it comes up with the project), so
#: the honest way back is the connection, on the tab that now also carries
#: Provision and Reset.
NO_SESSION_TEXT = (
    "No live sandbox session — the project's sandbox could not be reached; "
    "check its connection in Project Settings. "
    "Ad-hoc SQL runs against the sandbox and nowhere else."
)

#: Shown while a run is in flight (Run is disabled for the duration).
RUNNING_TEXT = "Running against the sandbox…"

#: Refused when the buffer holds no executable statement at all -- e.g. only a
#: comment. Said out loud rather than sending an empty query the server would
#: answer with a confusing driver-level error.
NOTHING_EXECUTABLE_TEXT = (
    "Nothing to run — the buffer holds no SQL statement (only comments or "
    "whitespace)."
)

#: What a declined object-change confirmation reports. **Nothing executed** --
#: not the read statements either: the user declined the Run, not part of it.
DECLINED_TEXT = (
    "Run cancelled — the object-change confirmation was declined. Nothing was "
    "executed."
)

#: The confirmation's title (the injected `confirm(title, text)` seam's first
#: argument).
OBJECT_CHANGE_TITLE = "This Run changes objects in the sandbox"

#: The title when every object-changing statement is merely *unclassifiable*.
#: It must not assert DDL -- the classifier said it could not tell.
UNKNOWN_CHANGE_TITLE = "This Run may change objects in the sandbox"

#: The consequence, §18.5 D4's own sentence, verbatim.
OBJECT_CHANGE_CONSEQUENCE = (
    "The sandbox's applied working set (and what your open tabs believe is "
    "applied) may no longer match. Reset Sandbox re-establishes a known state."
)

#: The checkbox's label. Scoped to the **session**, and the label says so, so
#: nobody reads it as a permanent preference.
REMEMBER_LABEL = "Don't ask again for this sandbox session"


@dataclass(frozen=True)
class ObjectChangeConfirmation:
    """A richer answer than `bool` for the one confirmation that carries a
    checkbox (§18.5 D4's *"don't ask again for this sandbox session"*).

    The seam signature stays the codebase's established
    `confirm(title, text) -> bool`: a host wired to a plain yes/no dialog keeps
    working unchanged and simply never remembers. A host (or test) that offers
    the checkbox returns one of these instead, and `as_confirmation` normalises
    either shape -- so there is one confirmation seam, not a second one invented
    for this feature.
    """

    confirmed: bool
    #: Whether the user asked not to be asked again **for this session**.
    #: Meaningless unless `confirmed` -- a declined Run remembers nothing.
    remember: bool = False


def as_confirmation(answer: Any) -> ObjectChangeConfirmation:
    """Normalise whatever the injected `confirm` seam returned.

    A bare truthy/falsey value is a plain yes/no with no memory; an object
    carrying `confirmed`/`remember` (this module's `ObjectChangeConfirmation`,
    or any duck-typed stand-in) is taken as-is. `remember` is forced off on a
    refusal: "no, and don't ask again" is not a thing this gate may express,
    because it would silently suppress a *refusal* forever.
    """
    if isinstance(answer, ObjectChangeConfirmation):
        confirmed, remember = answer.confirmed, answer.remember
    elif hasattr(answer, "confirmed"):
        confirmed = bool(getattr(answer, "confirmed"))
        remember = bool(getattr(answer, "remember", False))
    else:
        confirmed, remember = bool(answer), False
    return ObjectChangeConfirmation(
        confirmed=bool(confirmed), remember=bool(confirmed and remember)
    )


def object_change_prompt(
    statements: Sequence[Statement], classifications: Sequence[str]
) -> str:
    """The confirmation's body: which statements change objects, what that
    costs, and -- for `unknown` -- an honest *"could not tell"*.

    Pure, so the exact wording is assertable without a dialog. The two variants
    are not cosmetic: telling a user that `DO $$ … $$` "changes objects" would
    be asserting something the classifier explicitly did not establish, and
    §18.5 D4 requires the prompt to say the classifier could not tell instead.
    """
    changing = [
        (index, statement, kind)
        for index, (statement, kind) in enumerate(
            zip(statements, classifications), start=1
        )
        if kind in CHANGES_OBJECTS
    ]
    ddl_count = sum(1 for _i, _s, kind in changing if kind != UNKNOWN)
    unknown_count = len(changing) - ddl_count

    if ddl_count and unknown_count:
        head = (
            f"{ddl_count} statement(s) of this Run change objects in the "
            f"sandbox, and {unknown_count} could not be classified at all."
        )
    elif ddl_count:
        noun = "statement changes" if ddl_count == 1 else "statements change"
        head = f"{ddl_count} {noun} objects in the sandbox."
    else:
        noun = "statement" if unknown_count == 1 else "statements"
        head = (
            f"The classifier could not tell what {unknown_count} {noun} of this "
            "Run does, so it is treated as if it changed objects — an "
            "unclassifiable statement is never assumed harmless."
        )

    lines = [head, "", OBJECT_CHANGE_CONSEQUENCE, ""]
    for index, statement, kind in changing:
        note = (
            "could not be classified"
            if kind == UNKNOWN
            else "changes objects"
        )
        first = statement.text.strip().splitlines()[0] if statement.text.strip() else ""
        if len(first) > 72:
            first = f"{first[:72].rstrip()}…"
        lines.append(
            f"Statement {index} (line {statement.start_line}, {note}): {first}"
        )
    lines.append("")
    lines.append("Run these statements against the sandbox?")
    return "\n".join(lines)


def _statement_run(
    index: int, statement: Statement, classification: str, result: QueryResult
) -> StatementRun:
    """Pair one statement with its result, converting the server's
    statement-local error position into a **buffer** line.

    `Statement.line_offset` is the piece a caller cannot recompute, and
    `db/apply.py::line_of_position` is the one implementation of the
    position -> line rule (§18.5 D4 states it once, deliberately, so the console,
    the apply path and the validation ladder cannot drift). `position` indexes
    the statement we sent, which is exactly `statement.text`, so the sum is
    exact rather than mapped -- and `None` stays `None`: a failure without a
    reported position gets no line at all rather than a guessed one.
    """
    error = result.error
    error_line: int | None = None
    if error is not None:
        local = line_of_position(statement.text, error.position)
        if local is None:
            # `QueryError.line` is itself statement-local (derived by the same
            # rule inside `db/`), so it needs the same offset.
            local = error.line
        if local is not None:
            error_line = statement.line_offset + local
    return StatementRun(
        index=index,
        sql=statement.text,
        classification=classification,
        result=result,
        start_line=statement.start_line,
        error_line=error_line,
    )


def default_object_change_confirm(title: str, text: str) -> ObjectChangeConfirmation:
    """The console's own object-change dialog, used when no host wired a
    `confirm` seam.

    It exists because an unwired seam must not silently *skip* the question --
    which is what would happen with a permissive default -- and must not make
    every DDL Run impossible either, which is what a refusing default would do
    in the shipped app. It is the only modal in this file, it is reached only by
    a Run that really does change objects, and every test injects `confirm`
    instead (§30).
    """
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(title)
    box.setInformativeText(text)
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    box.setDefaultButton(QMessageBox.StandardButton.No)
    checkbox = QCheckBox(REMEMBER_LABEL)
    box.setCheckBox(checkbox)
    confirmed = box.exec() == QMessageBox.StandardButton.Yes
    return ObjectChangeConfirmation(
        confirmed=confirmed, remember=confirmed and checkbox.isChecked()
    )


class SqlConsolePanel(SchemaGestureHostMixin, CompletionPopupHostMixin, QWidget):
    """Editor + results grid for ad-hoc SQL against this project's sandbox.

    Constructor seams (all keyword-only; nothing here opens a connection):

    ``session_provider() -> SandboxSession | None``
        Where the session comes from **at Run time**, so the console never
        holds one and can never outlive it. `None`, or a provider returning
        `None`, means there is nothing to run against: Run is refused with
        `NO_SESSION_TEXT` rather than doing something invisible. A
        `SandboxSession` is the *only* accepted destination -- there is no
        `ConnectionParams` path in or out of this class.
    ``run_query(session, sql, *, max_rows) -> QueryResult``
        The execution function, defaulting to the real
        `db/sandbox_query.py::run_sandbox_query`. Tests replace it and never
        touch a server. It never raises: every failure arrives as a
        `QueryResult` whose `outcome` is `ERROR`.
    ``run_async(fn, on_result=…, on_error=…)``
        The off-GUI-thread seam, `ui/async_task.py::run_async` by default and a
        synchronous stub in tests -- the `SandboxController` convention.
    ``confirm(title, text) -> bool | ObjectChangeConfirmation``
        The object-change gate, the same `confirm(title, text)` seam the Apply
        gestures use, defaulting to this module's
        `default_object_change_confirm`. Returning an
        `ObjectChangeConfirmation` is how a host reports the
        *"don't ask again for this sandbox session"* checkbox; a plain `bool`
        host keeps working and simply never remembers.

    Wiring surface for the host: `set_schema_index`, `set_session_available`,
    `set_sql`, `append_sql`, `focus_editor`, `run`, `row_limit`,
    `set_row_limit`, `clear`, the read-only
    `sql_text`/`current_sql`/`result`/`run_report`, and the
    `execute_requested` / `result_ready` / `run_finished` / `format_refused`
    signals.
    """

    #: Emitted with the SQL actually being sent, so a host can mirror it in a
    #: status bar or log.
    execute_requested = Signal(str)
    #: Emitted with the finished `QueryResult` (`object`, so the dataclass rides
    #: across as-is), after it has been rendered. For a multi-statement Run this
    #: is the result the grid shows -- `run_finished` carries the whole Run.
    result_ready = Signal(object)
    #: Emitted with the finished `ui/sql_results_panel.py::RunReport` -- every
    #: executed statement, its command status, and any failure's attribution.
    run_finished = Signal(object)
    #: Emitted with `sql/issues.py` issues when Format Selection refuses
    #: (§18.4's contract: the text is left byte-for-byte unchanged).
    format_refused = Signal(list)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        session_provider: Callable[[], "SandboxSession | None"] | None = None,
        run_query: Callable[..., QueryResult] = run_sandbox_query,
        run_async: Callable[..., Any] = run_async,
        confirm: Callable[[str, str], Any] = default_object_change_confirm,
    ) -> None:
        super().__init__(parent)
        self._session_provider = session_provider
        self._run_query = run_query
        # Plain attribute, replaced wholesale by a synchronous stub in tests --
        # the SandboxController/ConnectionSetupDialog convention.
        self._run_async = run_async
        self._confirm = confirm
        self._running = False
        self._session_available = session_provider is not None
        # "Don't ask again" is scoped to ONE sandbox session, so what is
        # remembered is the session it was granted for -- identified by a
        # weakref where the object supports one (never keeping the session
        # alive, which is the reason this panel does not hold one) plus its
        # id() for the objects that do not. A different session, or the same
        # id() after the original died, asks again.
        self._ack_ref: Any = None
        self._ack_id: int | None = None

        # §18.6 completion, injected exactly as into a DDL object tab: None
        # (the default) disables it entirely. This panel never imports
        # `db/introspect.py` and never learns what a connection is.
        self._schema_index: "SchemaIndex | None" = None
        self._init_completion_popup()

        self.editor = CodeEditor(language="sql")
        self.editor.setReadOnly(False)
        # Expand-`SELECT` (FQ-030 slice 1): the one part of the gesture that
        # needs a schema. Read at gesture time, so a later `set_schema_index`
        # is picked up without re-wiring.
        self.editor.set_dynamic_expander(self._expand_select_expansion)
        self.editor.setPlaceholderText(
            "SELECT … — runs against this project's sandbox database, never the target"
        )

        # The results panel supplies Run, the grid and the status strip. Giving
        # it a `sql_provider` is what tells it its text lives elsewhere (it then
        # hides its own editor), so the CodeEditor above is the single source.
        self.results = SqlResultsPanel(
            on_execute=self._execute,
            sql_provider=self.current_sql,
        )

        self.row_limit_spin = QSpinBox()
        self.row_limit_spin.setRange(MIN_ROW_LIMIT, MAX_ROW_LIMIT)
        self.row_limit_spin.setValue(DEFAULT_ROW_LIMIT)
        self.row_limit_spin.setGroupSeparatorShown(True)
        self.row_limit_spin.setToolTip(
            "How many rows one run may bring back. A result cut off at this cap "
            "is reported as truncated, never shown as if it were complete. "
            f"There is no unlimited setting (maximum {MAX_ROW_LIMIT})."
        )
        self.row_limit_label = QLabel("Row limit:")
        self.row_limit_label.setBuddy(self.row_limit_spin)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self.row_limit_label)
        controls.addWidget(self.row_limit_spin)
        controls.addStretch(1)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.editor)
        self.splitter.addWidget(self.results)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self.splitter, 1)

        # This panel answers its own keys, and it answers them in two places
        # with two different rules -- see `eventFilter` below for the undo/redo
        # chord set, which is NOT part of the family described here.
        #
        # Ctrl+Space completion and Ctrl+Alt+F Format Selection are hosted HERE,
        # on the panel, and scoped `WidgetWithChildrenShortcut` -- never at the
        # window. `Ctrl+Space` / `Ctrl+Alt+J` / `Ctrl+Shift+Space` belong to
        # DEC-009's widget-owned family, which has **no menu command at all**:
        # DEC-004's defect was *two hosts for one gesture*, and a gesture with no
        # menu entry has only ever had one host.
        #
        # **`Ctrl+Alt+F` is NOT in that family, and this comment used to claim it
        # was (BUG-063).** Format Selection HAS a command form -- the
        # context-menu action in `_build_context_menu`, on this panel since
        # BUG-063 and on the DDL object tab before it -- which is exactly what
        # puts it under DEC-012 instead: **a gesture with a command form, menu
        # bar or context menu, gets exactly one keyboard host.** That host is
        # this `QShortcut`. The menu item is a click-only command form and
        # carries no `setShortcut`; there is deliberately no `Ctrl+Alt+F` branch
        # in `eventFilter` either.
        #
        # Completion additionally needs the injected `SchemaIndex`, which this
        # panel holds and the `CodeEditor` widget may not (§18.5 D1), and the
        # panel scope is what stops either gesture firing while focus is
        # elsewhere in the window.
        self._completion_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self._completion_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self._completion_shortcut.activated.connect(self.show_completions)

        # FQ-030 slice 3's two schema-fed gestures, wired the same way and for
        # the same reason: both need the injected `SchemaIndex`, which the
        # editor widget may not hold, so neither can live in `CodeEditor`'s own
        # key handling next to Ctrl+Alt+E / Ctrl+Alt+C.
        self._join_shortcut = QShortcut(QKeySequence("Ctrl+Alt+J"), self)
        self._join_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._join_shortcut.activated.connect(self.join_on_fk)

        self._signature_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Space"), self)
        self._signature_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self._signature_shortcut.activated.connect(self.show_signature_help)

        self._format_shortcut = QShortcut(QKeySequence("Ctrl+Alt+F"), self)
        self._format_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self._format_shortcut.activated.connect(self.format_selection)
        self._format_shortcut.setEnabled(False)
        self.editor.selectionChanged.connect(self._update_format_shortcut_enabled)

        # §27's Ctrl+Return = Run, the one execution gesture that carries a
        # shortcut (§18.5 D4: the sandbox is disposable and `reset()`-able, so
        # this does not reopen the "an irreversible outward effect must not be
        # one keystroke away" rule -- and there is no target-database Run to
        # reach with or without a key). Same mechanism as the two shortcuts
        # above -- a `QShortcut` scoped `WidgetWithChildrenShortcut` so it can
        # only fire while focus is inside this console and never from an
        # unrelated tab -- and it calls the SAME `run()` the results panel's Run
        # button calls, so there is exactly one execution path.
        self._run_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._run_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self._run_shortcut.activated.connect(self.run)

        # The panel's own key/menu filter, on the EDITOR and not on the panel:
        # the console also hosts a results table and a completion popup, which
        # must keep their own keys and their own right-click. See `eventFilter`.
        self.editor.installEventFilter(self)

        if not self._session_available:
            self.results.set_enabled(False, NO_SESSION_TEXT)

    # --- the editor's own keys and menu (BUG-056, BUG-063) ------------------

    def eventFilter(self, obj, event) -> bool:
        """The console editor's reserved editor chords and its context menu.

        **Why this exists at all (BUG-056).** This panel had no filter, so all
        three reserved undo/redo chords fell through to `QPlainTextEdit`'s
        `StandardKey` handling -- and that table is **platform-dependent**:
        `Ctrl+Y` is `KB_Win` only. Measured consequence, from one source tree:
        `Ctrl+Y` redid the console buffer on Windows and did **nothing at all**
        on Linux, where the key instead reached `MainWindow`'s window-level
        `Ctrl+Y` shortcut, which returns immediately because this is not the Raw
        XML tab (BUG-048's scoping) -- no redo, no refusal, no journal line.
        DEC-014/DEC-015: the app states its answer, it does not inherit one.

        Both halves are required and neither is optional. Accepting only the
        `ShortcutOverride` leaves the key dead; answering only the `KeyPress`
        lets the window `QShortcut` fire as well.

        The buffer is editable (unlike the DDL Explorer's synthesized one), so
        undo/redo route into the editor's own stack -- no refusal branch here.
        """
        if obj is self.editor and event.type() in (
            QEvent.Type.ShortcutOverride,
            QEvent.Type.KeyPress,
        ):
            operation = classify_editor_chord(event)
            if operation is not None:
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                elif operation == UNDO:
                    self.editor.undo()
                elif operation == REDO:
                    self.editor.redo()
                elif is_mutating_editor_operation(operation):
                    # Paste (`Ctrl+Shift+Insert`) and the three line-editing
                    # gestures (`Ctrl+D`/`Ctrl+K`/`Ctrl+U`): Qt answers them on
                    # the Linux/KDE scheme only, so the app implements them on
                    # both (owner, 2026-08-10). The console buffer is editable.
                    apply_editor_operation(self.editor, operation)
                # else: the answers that run nothing, consumed precisely so Qt
                # cannot answer them instead -- Ctrl+Shift+Z (freed from redo by
                # DEC-015; Qt binds it `KB_Win | KB_X11`) and the suppressed
                # Alt+Backspace pair (Qt binds those `KB_Win` only).
                return True
        if obj is self.editor and event.type() == QEvent.Type.ContextMenu:
            menu = self._build_context_menu()
            menu.exec(event.globalPos())
            return True
        return super().eventFilter(obj, event)

    def _build_context_menu(self):
        """Build (but do not exec) the editor's context menu -- split out so
        tests can inspect it directly instead of ever driving a real modal
        `QMenu.exec` (the `ddl_object_editor.py` precedent this mirrors).

        **Format Selection's second, CLICK-ONLY host (BUG-063).** The console
        had the `Ctrl+Alt+F` shortcut and no menu item, which made it the one
        surface where a gesture with a command form had no command. The action
        carries **no `setShortcut`**: DEC-012 permits exactly one keyboard host
        per gesture and the `QShortcut` in `__init__` is it. Adding a shortcut
        here would re-create the double-hosting DEC-012 exists to forbid.

        The enabled gate is the chord's own (`hasSelection`), so a
        selection-less right-click shows the item **disabled** rather than
        absent -- the same answer the key gives, and the DDL object tab's shape.

        Nothing else belongs on this menu: there is no `Run in Sandbox Console`
        bridge (the console **is** the target) and no apply gestures (FQ-026
        removed those from the object tab's menu for a stated reason).
        """
        menu = self.editor.createStandardContextMenu()
        menu.addSeparator()
        action = menu.addAction("Format Selection", self.format_selection)
        action.setEnabled(self.editor.textCursor().hasSelection())
        return menu

    # --- identity -----------------------------------------------------------

    def tab_title(self) -> str:
        """The `CenterStage` tab label. Fixed -- the console holds no document,
        so there is no dirty marker to carry."""
        return TAB_TITLE

    # --- text ---------------------------------------------------------------

    @property
    def sql_text(self) -> str:
        """The whole buffer, verbatim."""
        return self.editor.toPlainText()

    def current_sql(self) -> str:
        """What Run sends: **the selection if there is one, otherwise the whole
        buffer**, stripped. `QTextCursor.selectedText` joins lines with U+2029
        (paragraph separator) rather than `"\\n"`, so it is converted back --
        sending U+2029 to the server would be a syntax error nobody could
        see."""
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            return cursor.selectedText().replace(" ", "\n").strip()
        return self.editor.toPlainText().strip()

    def set_sql(self, text: str) -> None:
        """Replace the buffer -- what the object tab's **"Run in Sandbox
        Console"** bridge calls with the selected DDL. It **executes nothing**;
        the user still presses Run."""
        self.editor.setPlainText(text)

    def append_sql(self, text: str) -> None:
        """Add `text` after what is already there (separated by a blank line),
        so pushing a second selection over does not destroy the first."""
        existing = self.editor.toPlainText()
        if existing.strip():
            self.editor.setPlainText(f"{existing.rstrip()}\n\n{text}")
        else:
            self.editor.setPlainText(text)

    def focus_editor(self) -> None:
        """Put the caret in the editor -- called after the host focuses the
        tab."""
        self.editor.setFocus()

    # --- row cap ------------------------------------------------------------

    def row_limit(self) -> int:
        """The cap currently in force, as passed to `run_sandbox_query`."""
        return int(self.row_limit_spin.value())

    def set_row_limit(self, rows: int) -> None:
        """Set the cap; the spin box clamps to `MIN_ROW_LIMIT..MAX_ROW_LIMIT`,
        which is the point -- there is no unlimited setting to fall into."""
        self.row_limit_spin.setValue(int(rows))

    # --- session availability ----------------------------------------------

    @property
    def is_running(self) -> bool:
        """Whether a run is in flight (Run is disabled for the duration)."""
        return self._running

    def set_session_available(self, available: bool, reason: str = "") -> None:
        """Told by the host from `SandboxController.session_changed`: without a
        live session there is nothing to run against, so Run is disabled with a
        stated reason instead of failing later."""
        self._session_available = bool(available)
        if available:
            self.results.set_enabled(not self._running)
        else:
            # The session this console was running against is gone, so the
            # "don't ask again for this sandbox session" grant goes with it.
            self._forget_object_change_ack()
            self.results.set_enabled(False, reason or NO_SESSION_TEXT)

    # --- running ------------------------------------------------------------

    def run(self) -> None:
        """The Run gesture (also reachable through the results panel's own Run
        button). Delegates to the panel so the empty-statement refusal and the
        status wording live in exactly one place."""
        self.results.run()

    def _execute(self, sql: str) -> None:
        """The results panel's `on_execute` seam: split the Run into statements,
        gate it on the object-change confirmation, then execute the statements
        in order off the GUI thread and render the whole Run. Never opens a
        connection and never builds `ConnectionParams`."""
        if self._running:
            return
        session = (
            self._session_provider() if self._session_provider is not None else None
        )
        if session is None:
            self.results.set_enabled(False, NO_SESSION_TEXT)
            return

        statements = split_statements(sql)
        if not statements:
            self.results.report_notice(NOTHING_EXECUTABLE_TEXT)
            return
        classifications = [classify_statement(stmt.text) for stmt in statements]

        if not self._object_change_allowed(session, statements, classifications):
            self.results.report_notice(DECLINED_TEXT)
            return

        max_rows = self.row_limit()
        self._running = True
        self.results.set_enabled(False, RUNNING_TEXT)
        self.execute_requested.emit(sql)

        def work() -> RunReport:
            # Statement by statement, **stopping at the first failure**: each
            # `run_query` call is one `SandboxExecutor.fetch`, i.e. its own
            # committing transaction, so continuing past a failure would pile
            # more committed changes on top of a broken Run.
            runs: list[StatementRun] = []
            for index, (statement, kind) in enumerate(
                zip(statements, classifications), start=1
            ):
                result = self._run_query(session, statement.text, max_rows=max_rows)
                runs.append(_statement_run(index, statement, kind, result))
                if not result.ok:
                    break
            return RunReport(runs=tuple(runs), total=len(statements))

        def on_result(report: RunReport) -> None:
            self._finish(report)

        def on_error(exc: BaseException) -> None:
            # `run_sandbox_query` never raises, so this is the seam itself
            # failing (a thread-pool or programming error). Reported as an
            # error result rather than swallowed into an empty grid. It is NOT
            # attributed to any statement: we do not know which one it died on.
            self._finish_result(
                QueryResult.failed(
                    sql, str(exc).strip() or exc.__class__.__name__, max_rows=max_rows
                )
            )

        self._run_async(work, on_result=on_result, on_error=on_error)

    def _finish(self, report: RunReport) -> None:
        self._running = False
        self.results.set_enabled(self._session_available)
        self.results.show_run(report)
        if self.results.result is not None:
            self.result_ready.emit(self.results.result)
        self.run_finished.emit(report)

    def _finish_result(self, result: QueryResult) -> None:
        """The seam-level failure path: one `QueryResult` that belongs to no
        particular statement."""
        self._running = False
        self.results.set_enabled(self._session_available)
        self.results.show_result(result)
        self.result_ready.emit(result)

    # --- the ddl/unknown confirmation (§18.5 D4) ----------------------------

    def _object_change_allowed(
        self,
        session: Any,
        statements: Sequence[Statement],
        classifications: Sequence[str],
    ) -> bool:
        """Whether the Run may proceed: True when nothing in it changes objects,
        when this session already answered *"don't ask again"*, or when the
        confirmation seam says yes. A refusal executes **nothing at all** --
        not even the Run's read statements."""
        if not any(kind in CHANGES_OBJECTS for kind in classifications):
            return True
        if self._object_change_acknowledged(session):
            return True
        title = (
            UNKNOWN_CHANGE_TITLE
            if all(
                kind == UNKNOWN
                for kind in classifications
                if kind in CHANGES_OBJECTS
            )
            else OBJECT_CHANGE_TITLE
        )
        answer = as_confirmation(
            self._confirm(title, object_change_prompt(statements, classifications))
        )
        if not answer.confirmed:
            return False
        if answer.remember:
            self._remember_object_change_ack(session)
        return True

    def _object_change_acknowledged(self, session: Any) -> bool:
        """Whether *this* session already carries the "don't ask again" grant."""
        if self._ack_id is None or self._ack_id != id(session):
            return False
        if self._ack_ref is not None and self._ack_ref() is not session:
            # Same id(), different object: the acknowledged session died and
            # its address was reused. A new session asks again.
            return False
        return True

    def _remember_object_change_ack(self, session: Any) -> None:
        try:
            self._ack_ref = weakref.ref(session)
        except TypeError:  # objects that do not support weak references
            self._ack_ref = None
        self._ack_id = id(session)

    def _forget_object_change_ack(self) -> None:
        """Drop the grant -- the session it was given for is gone, so the next
        one must ask again."""
        self._ack_ref = None
        self._ack_id = None

    @property
    def result(self) -> QueryResult | None:
        """The result currently shown, or None before the first run. For a
        multi-statement Run this is the **last row-returning** statement's
        result (or the last statement's, if none returned rows)."""
        return self.results.result

    @property
    def run_report(self) -> RunReport | None:
        """The whole last Run -- every executed statement, its command status
        and any failure's index/buffer line. None before the first Run."""
        return self.results.run_report

    def clear(self) -> None:
        """Back to "nothing run yet" (project closed, sandbox released).
        Leaves the typed SQL alone -- losing someone's statement because a
        session dropped would be its own bug."""
        self.results.clear()

    # --- Format Selection (§18.4, host set widened to this tab) -------------

    def _update_format_shortcut_enabled(self) -> None:
        self._format_shortcut.setEnabled(self.editor.textCursor().hasSelection())

    def format_selection(self) -> None:
        """Reindent the current selection in place, or -- on refusal -- leave it
        byte-for-byte unchanged and emit `format_refused` with the issues. The
        formatter itself is §18.4's, unchanged."""
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return
        selected = cursor.selectedText().replace(" ", "\n")
        # FQ-033: same as the DDL object tab -- the ruleset is read at gesture
        # time from `ui/format_settings.py`, so both SQL hosts always agree with
        # whatever the Autoformatter settings dialog last saved.
        result = _format_selection_text(selected, config=current_sql_config())
        if result.ok:
            cursor.beginEditBlock()
            cursor.insertText(result.text)
            cursor.endEditBlock()
            return
        self.format_refused.emit(list(result.issues))

    # --- §18.6 Ctrl+Space completion ---------------------------------------

    def set_schema_index(self, index: "SchemaIndex | None") -> None:
        """Inject the current `db/schema_index.py::SchemaIndex` (or None) --
        the same call a DDL object tab gets, made by the same host at the same
        moment. `None` disables completion entirely (the default)."""
        self._schema_index = index

    def schema_index(self):
        """The injected `SchemaIndex`, or None."""
        return self._schema_index

    # --- Expand-`SELECT` (§18.6 / FQ-030 slice 1) --------------------------
    def _expand_select_expansion(self, text: str, pos: int):
        """`CodeEditor.set_dynamic_expander` seam: the buffer in, an
        `Expansion` out (`ui/expand_select_seam.py`, shared verbatim with the
        DDL object tab). Uses the already-injected index; queries nothing."""
        return expand_select_expansion(self._schema_index, text, pos)

    def expand_select(self) -> bool:
        """Ctrl+Alt+C: expand the bare `SELECT` at the caret into its column
        list (FQ-030 slice 1). The console is where a bare `SELECT FROM
        hr.jobcard` is most often typed, so this is its home surface."""
        return self.editor.expand_select_at_caret()

    def show_completions(self) -> None:
        """Ctrl+Space: schema-qualified identifier completion at the caret.

        §18.6's *dotted path* row applies here, and so does FQ-030's
        `ALIAS_REF` refinement of it: a console buffer is where a FROM clause
        is most often hand-written, so `FROM hr.jobcard jc` ... `jc.` offers
        that table's columns exactly as it does in a DDL tab. `NEW.`/`OLD.`
        still does NOT: row variables are meaningful inside a trigger function
        body, and a console buffer is not one, so there is nothing to resolve
        them against.

        `LOCAL_REF` is deliberately NOT consumed. `caret_context` descends into
        a pasted `$$` body here too, so a pasted routine's `rec.` does resolve
        -- but a console buffer is a script being *sent*, not a routine being
        edited, and its declarations are not this panel's subject. What matters
        is that it does not silently swallow the caret either: an unconsumed
        refinement falls through to the `DOTTED_PATH` reading of the same
        context (both kinds keep `parts` populated for exactly that), so the
        old behavior survives instead of the guard turning into a dead branch.

        No-op with no `SchemaIndex` injected or an unresolvable caret."""
        index = self._schema_index
        if index is None:
            return
        context = resolve_caret_context(
            self.editor.toPlainText(), self.editor.textCursor().position()
        )
        if context is None or context.kind not in (DOTTED_PATH, ALIAS_REF, LOCAL_REF):
            return
        if context.kind == ALIAS_REF and context.table_ref is not None:
            table = context.table_ref.qualified
            # `column_entries` filters AND renders: the key stays the bare
            # column name (what gets inserted), the display adds type, PK, FK
            # target, NOT NULL, default and comment. The display must never
            # reach the buffer, which is exactly why it is the pair's tail.
            entries = index.column_entries(table, context.prefix) if table else []
            if entries:
                popup = self._ensure_completion_popup()
                popup.set_items(entries)
                self._rewire_popup(popup, self._complete_identifier)
                self._popup_at_caret(popup)
                return
            # No schema written (`FROM jobcard j`) or the table is not in the
            # fetched schema -- fall through to the DOTTED_PATH reading below.
        if len(context.parts) >= 2:
            # `hr.jobcard.` -- the cascade's third segment, offering that
            # table's columns. Nothing matching shows nothing, the same
            # fallback convention the other two steps follow.
            items = index.column_entries(
                f"{context.parts[0]}.{context.parts[1]}", context.prefix
            )
        elif not context.parts:
            prefix = context.prefix.lower()
            names = [
                name
                for name in index.known_schemas()
                if name.lower().startswith(prefix)
            ]
            items = [(name, name) for name in names]
        else:
            schema = context.parts[0]
            items = [
                (table, f"{schema}.{table}")
                for table in index.known_tables(schema, context.prefix)
            ]
        if not items:
            return
        popup = self._ensure_completion_popup()
        popup.set_items(items)
        self._rewire_popup(popup, self._complete_identifier)
        self._popup_at_caret(popup)

    def _completion_editor(self):
        """CompletionPopupHostMixin hook: this panel wraps its editor rather
        than being one, so caret geometry comes off `self.editor`."""
        return self.editor

    def _complete_identifier(self, name: str) -> None:
        """Insert `name` at the caret, replacing the partial prefix already
        typed, as a single undoable edit."""
        popup = self._completion_popup
        if popup is not None:
            popup.hide()
        cursor = self.editor.textCursor()
        context = resolve_caret_context(
            self.editor.toPlainText(), cursor.position()
        )
        prefix_len = len(context.prefix) if context is not None else 0
        cursor.beginEditBlock()
        if prefix_len:
            cursor.movePosition(
                QTextCursor.MoveOperation.Left,
                QTextCursor.MoveMode.KeepAnchor,
                prefix_len,
            )
        cursor.insertText(name)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
