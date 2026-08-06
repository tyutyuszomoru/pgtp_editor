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

**Nothing blocks the GUI thread and nothing here reaches a modal.** The query
goes out through the injected `run_async` seam (`ui/async_task.py::run_async`
by default, a synchronous stub in tests), Run is disabled while a run is in
flight, and a failure comes back as a `QueryResult` carrying the database's own
message -- never an empty grid.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..db.sandbox_query import (
    DEFAULT_MAX_ROWS,
    QueryResult,
    run_sandbox_query,
)
from ..sql.caret_context import DOTTED_PATH, resolve_caret_context
from ..sql.formatter import format_selection as _format_selection_text
from .async_task import run_async
from .code_editor import CodeEditor
from .completion_popup import _CompletionPopup
from .sql_results_panel import SqlResultsPanel

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
NO_SESSION_TEXT = (
    "No live sandbox session — open one via Database ▸ Sandbox Setup…. "
    "Ad-hoc SQL runs against the sandbox and nowhere else."
)

#: Shown while a run is in flight (Run is disabled for the duration).
RUNNING_TEXT = "Running against the sandbox…"


class SqlConsolePanel(QWidget):
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

    Wiring surface for the host: `set_schema_index`, `set_session_available`,
    `set_sql`, `append_sql`, `focus_editor`, `run`, `row_limit`,
    `set_row_limit`, `clear`, the read-only `sql_text`/`current_sql`/`result`,
    and the `execute_requested` / `result_ready` / `format_refused` signals.
    """

    #: Emitted with the SQL actually being sent, so a host can mirror it in a
    #: status bar or log.
    execute_requested = Signal(str)
    #: Emitted with the finished `QueryResult` (`object`, so the dataclass rides
    #: across as-is), after it has been rendered.
    result_ready = Signal(object)
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
    ) -> None:
        super().__init__(parent)
        self._session_provider = session_provider
        self._run_query = run_query
        # Plain attribute, replaced wholesale by a synchronous stub in tests --
        # the SandboxController/ConnectionSetupDialog convention.
        self._run_async = run_async
        self._running = False
        self._session_available = session_provider is not None

        # §18.6 completion, injected exactly as into a DDL object tab: None
        # (the default) disables it entirely. This panel never imports
        # `db/introspect.py` and never learns what a connection is.
        self._schema_index: "SchemaIndex | None" = None
        self._completion_popup: _CompletionPopup | None = None
        self._popup_wired = False

        self.editor = CodeEditor(language="sql")
        self.editor.setReadOnly(False)
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

        # Ctrl+Space completion and Ctrl+Alt+F Format Selection. Both get the
        # redundant key handling `CodeEditorDialog`/`DdlObjectEditorPanel`
        # established, because QShortcut activation is not reliable under the
        # offscreen platform used by the tests.
        self._completion_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self._completion_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self._completion_shortcut.activated.connect(self.show_completions)

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

        if not self._session_available:
            self.results.set_enabled(False, NO_SESSION_TEXT)

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
            self.results.set_enabled(False, reason or NO_SESSION_TEXT)

    # --- running ------------------------------------------------------------

    def run(self) -> None:
        """The Run gesture (also reachable through the results panel's own Run
        button). Delegates to the panel so the empty-statement refusal and the
        status wording live in exactly one place."""
        self.results.run()

    def _execute(self, sql: str) -> None:
        """The results panel's `on_execute` seam: fetch the session, hand the
        statement to `run_query` off the GUI thread, and render whatever comes
        back. Never opens a connection and never builds `ConnectionParams`."""
        if self._running:
            return
        session = (
            self._session_provider() if self._session_provider is not None else None
        )
        if session is None:
            self.results.set_enabled(False, NO_SESSION_TEXT)
            return

        max_rows = self.row_limit()
        self._running = True
        self.results.set_enabled(False, RUNNING_TEXT)
        self.execute_requested.emit(sql)

        def work() -> QueryResult:
            return self._run_query(session, sql, max_rows=max_rows)

        def on_result(result: QueryResult) -> None:
            self._finish(result)

        def on_error(exc: BaseException) -> None:
            # `run_sandbox_query` never raises, so this is the seam itself
            # failing (a thread-pool or programming error). Reported as an
            # error result rather than swallowed into an empty grid.
            self._finish(
                QueryResult.failed(
                    sql, str(exc).strip() or exc.__class__.__name__, max_rows=max_rows
                )
            )

        self._run_async(work, on_result=on_result, on_error=on_error)

    def _finish(self, result: QueryResult) -> None:
        self._running = False
        self.results.set_enabled(self._session_available)
        self.results.show_result(result)
        self.result_ready.emit(result)

    @property
    def result(self) -> QueryResult | None:
        """The result currently shown, or None before the first run."""
        return self.results.result

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
        result = _format_selection_text(selected)
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

    def show_completions(self) -> None:
        """Ctrl+Space: schema-qualified identifier completion at the caret.

        Only §18.6's *dotted path* row applies here -- `NEW.`/`OLD.` row
        variables are meaningful inside a trigger function body, and a console
        buffer is not one, so there is nothing to resolve them against. No-op
        with no `SchemaIndex` injected or an unresolvable caret."""
        index = self._schema_index
        if index is None:
            return
        context = resolve_caret_context(
            self.editor.toPlainText(), self.editor.textCursor().position()
        )
        if context is None or context.kind != DOTTED_PATH:
            return
        if not context.parts:
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

    def _ensure_completion_popup(self) -> _CompletionPopup:
        if self._completion_popup is None:
            self._completion_popup = _CompletionPopup(self)
        return self._completion_popup

    def _rewire_popup(self, popup: _CompletionPopup, on_chosen) -> None:
        """Point the shared popup's signals at this stage, disconnecting a
        previous wiring only when there was one (a fresh popup's first use must
        not raise a PySide6 RuntimeWarning) -- the `xml_editor.py` precedent."""
        if self._popup_wired:
            popup.chosen.disconnect()
            popup.cancelled.disconnect()
        popup.chosen.connect(on_chosen)
        popup.cancelled.connect(popup.hide)
        self._popup_wired = True

    def _popup_at_caret(self, popup: _CompletionPopup) -> None:
        rect = self.editor.cursorRect()
        point = self.editor.viewport().mapToGlobal(rect.bottomLeft())
        popup.move(point)
        popup.show()
        popup.setFocus()

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
