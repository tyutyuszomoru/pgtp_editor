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

# pgtp_editor/ui/ddl_object_editor.py
"""DdlObjectEditorPanel: the EDITABLE single-object DDL tab (spec §18.5).

The editable counterpart of §18.1's read-only `ddl_editor_panel.py::EditorPanel`
-- same `ui/code_editor.py::CodeEditor` in `language="sql"` mode (so the gutter,
bookmarks, folding, 4-character tab stop and SQL highlighting are inherited from
`ui/editor_gutter.py::GutterBookmarkFoldMixin`, never reimplemented here), same
per-tab `FindReplaceBar` routing precedent, same zero-margin layout -- except
this one is EDITABLE. `EditorPanel` stays read-only permanently.

**v1 is project-decoupled.** This module knows nothing about `.pgtp` projects,
`db/ddl_project.py`, a `ddl/` folder, a `deployed.json` manifest or `*`/`!`
state markers: all of those are §18.2 concepts and none is a prerequisite for
editing one routine. `resolve_save_path` is the ENTIRE §18.2 seam -- the panel
persists through an injected `Callable[[], Path | None]`, so §18.2's whole
change is that callable returning `project.ddl_dir / <the §18.2 filename>`
instead of a Save-As-picked path. No restructure, no new branch in the panel.

**The panel never talks to a database.** It does not import `db/introspect.py`,
`db/apply.py`, `db/sandbox.py` or `db/ddl_check.py`, never opens a connection,
holds no connection parameters and owns no session; the buffer is handed to it
as text. Every DB-touching step of Apply is an INJECTED CALLABLE the host
supplies (the sandbox controller's operations) -- see "the apply seams" on
`__init__` below. Following §18.5 carve-out 2's no-dead-controls posture, an
affordance whose seam is unwired is **absent**, never shown disabled: with no
sandbox seam there is no sandbox button and no sandbox row at all.

**Apply is never bound to a keyboard shortcut** -- neither Apply to Sandbox,
nor Apply to Target, nor "Deploy this edit…": *an irreversible outward effect
must not be one keystroke away* (§18.5). Every apply is confirm-gated behind a
confirmation naming **both the object and the database** it will hit.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.sql.caret_context import DOTTED_PATH, ROW_VARIABLE, resolve_caret_context
from pgtp_editor.sql.formatter import format_selection as _format_selection_text
from pgtp_editor.ui.code_editor import CodeEditor
from pgtp_editor.ui.completion_popup import _CompletionPopup
from pgtp_editor.ui.find_replace_bar import FindReplaceBar

if TYPE_CHECKING:  # pragma: no cover -- import-cycle/Qt-purity avoidance only
    from pgtp_editor.db.schema_index import SchemaIndex


#: The Audit-panel prefix reserved for SQL/plpgsql check results (§7/§18.5).
#: Deliberately NOT `[Lint]` (reserved for PHP, §22) and NOT `[SQL]` (reserved
#: for formatter refusals, §18.4): several linter-shaped features feed one
#: Audit panel and none may annex another's prefix. The panel bakes the prefix
#: into the lines it emits on `check_reported` so the reservation lives with
#: the feature that owns it; the host appends the lines verbatim and must not
#: re-prefix them.
CHECK_PREFIX = "[Check] "

#: The three per-edit destinations of "Deploy this edit…" (§18.5, §18.2). The
#: command is a picker in FRONT of the three existing gestures, never a fourth
#: thing that writes DDL or files on its own.
DEST_SANDBOX = "sandbox"
DEST_SAVE = "save"
DEST_TARGET = "target"

DESTINATION_LABELS = {
    DEST_SANDBOX: "Apply to Sandbox",
    DEST_SAVE: "Save (for a future batch deploy)",
    DEST_TARGET: "Apply to Target",
}


@dataclass(frozen=True)
class DdlObjectRef:
    """The stable per-object identity of an editable DDL tab (§18.5).

    Derived from a `db/ddl_buffer.py::DdlObjectSpan` by the caller (the tab is
    keyed on identity, never on a remembered `CenterStage` index, so closing or
    reordering tabs cannot make the key stale).

    `disambiguate` is set by the CALLER, which is the only party that can see
    the sibling set: a routine renders as its bare `name` when it is the sole
    holder of its `schema.name`, and only an OVERLOADED routine renders its
    signature. The panel cannot infer this, and unconditionally rendering `()`
    would turn a no-argument `recalc` into `recalc()`.
    """

    kind: str  # "function" | "procedure" | "trigger"
    schema: str
    name: str
    table: str | None = None  # triggers only -- the table the trigger fires on
    arg_types: tuple[str, ...] = ()  # routines only; always () for a trigger
    # Declared last, with a default: caller-supplied overload disambiguation.
    disambiguate: bool = False

    @property
    def is_trigger(self) -> bool:
        return self.kind == "trigger"

    @property
    def signature(self) -> str:
        """`(integer, text)` / `()` -- the routine's argument-type list."""
        return "(" + ", ".join(self.arg_types) + ")"

    @property
    def key(self) -> tuple:
        """The hashable, stable identity used as the `CenterStage` tab-map key.

        Includes the argument types (PostgreSQL allows overloading
        `schema.name`) and the table (a trigger name is unique only per table).
        Deliberately EXCLUDES `disambiguate`, which is presentation only: the
        same object must map to the same tab whether or not a sibling exists.
        """
        return (self.kind, self.schema, self.name, self.table, self.arg_types)

    @property
    def short_title(self) -> str:
        """The tab label: the object's SHORT identity (§18.5).

        `recalc` for a sole-holder routine, `fmt(integer)` for an overloaded
        one, `orders.trg_audit` for a trigger.
        """
        if self.is_trigger:
            return f"{self.table}.{self.name}"
        if self.disambiguate:
            return f"{self.name}{self.signature}"
        return self.name

    @property
    def qualified(self) -> str:
        """The tab tooltip: the FULL source identity -- schema-qualified, with
        the signature for a routine and the table for a trigger."""
        if self.is_trigger:
            return f"{self.schema}.{self.table}.{self.name}"
        return f"{self.schema}.{self.name}{self.signature}"

    @property
    def default_file_name(self) -> str:
        """The Save As… prefill: the sole-holder form of §18.2's file scheme,
        so the file a v1 user saves is already shaped like the checked-out one
        §18.2 will manage."""
        if self.is_trigger:
            return f"{self.schema}.{self.table}.{self.name}.sql"
        return f"{self.schema}.{self.name}.sql"


# --- Apply-to-target precondition 1: the buffer's own identity ------------
#
# PostgreSQL identifies a routine by `(schema, name, argtypes)`, so editing
# `calc_total(integer)` into `calc_total(bigint)` and applying makes
# `CREATE OR REPLACE` create a SECOND function and leave the old one live --
# a silent wrong result no confirmation gate can catch (§18.5 precondition 1).
# Detecting it needs the identity the BUFFER declares, which is why this
# parser exists. Pure text, no database.

_CREATE_ROUTINE_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?P<kind>FUNCTION|PROCEDURE)\s+"
    r"(?P<name>(?:\"[^\"]+\"|[^\s(.\"]+)(?:\s*\.\s*(?:\"[^\"]+\"|[^\s(.\"]+))?)\s*\(",
    re.IGNORECASE,
)
_CREATE_TRIGGER_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:CONSTRAINT\s+)?TRIGGER\s+"
    r"(?P<name>\"[^\"]+\"|[^\s(.\"]+)\b(?P<rest>.*?)\bON\s+"
    r"(?P<table>(?:\"[^\"]+\"|[^\s(.\"]+)(?:\s*\.\s*(?:\"[^\"]+\"|[^\s(.\"]+))?)",
    re.IGNORECASE | re.DOTALL,
)
_ARG_MODES = {"in", "out", "inout", "variadic"}
#: Words that legitimately OPEN a multi-word type name. Everything else in
#: first position is an argument NAME and is dropped (`p_id integer` →
#: `integer`, but `double precision` stays whole).
_TYPE_LEAD_WORDS = {
    "bit",
    "character",
    "double",
    "interval",
    "national",
    "time",
    "timestamp",
    "with",
    "without",
}


def _sha1(text: str) -> str:
    """The buffer hash, matching the sandbox's `applied.text_sha1` column."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _unquote_ident(raw: str) -> str:
    """`"Mixed"` → `Mixed`; a bare identifier folds to lower case, exactly as
    PostgreSQL folds it."""
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1]
    return raw.lower()


def _split_qualified_name(raw: str) -> tuple[str | None, str]:
    parts: list[str] = []
    buf = ""
    in_quote = False
    for char in raw:
        if char == '"':
            in_quote = not in_quote
            buf += char
        elif char == "." and not in_quote:
            parts.append(buf)
            buf = ""
        else:
            buf += char
    parts.append(buf)
    names = [_unquote_ident(p) for p in parts if p.strip()]
    if len(names) >= 2:
        return names[-2], names[-1]
    return None, names[-1] if names else ""


def _matching_paren(text: str, open_index: int) -> int | None:
    depth = 0
    in_single = False
    in_double = False
    for index in range(open_index, len(text)):
        char = text[index]
        if in_single:
            in_single = char != "'"
            continue
        if in_double:
            in_double = char != '"'
            continue
        if char == "'":
            in_single = True
        elif char == '"':
            in_double = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    in_single = False
    in_double = False
    buf = ""
    for char in text:
        if in_single:
            buf += char
            in_single = char != "'"
            continue
        if in_double:
            buf += char
            in_double = char != '"'
            continue
        if char == "'":
            in_single = True
        elif char == '"':
            in_double = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(buf)
            buf = ""
            continue
        buf += char
    if buf.strip():
        parts.append(buf)
    return [p for p in parts if p.strip()]


def normalize_arg_type(raw: str) -> str:
    """Lower-cased, whitespace-collapsed type text, for comparing a buffer's
    argument list against the catalog's `RoutineInfo.arg_types`."""
    return re.sub(r"\s+", " ", raw.strip().lower()).replace("( ", "(").replace(" )", ")")


def _argument_type(raw: str) -> str | None:
    """The IDENTITY-bearing type of one argument declaration, or None for an
    `OUT` argument (which PostgreSQL excludes from a routine's identity)."""
    text = re.split(r"\bDEFAULT\b", raw, maxsplit=1, flags=re.IGNORECASE)[0]
    text = text.split("=")[0].strip()
    if not text:
        return None
    tokens = text.split()
    mode = tokens[0].lower()
    if mode in _ARG_MODES:
        tokens = tokens[1:]
        if mode == "out":
            return None
    if not tokens:
        return None
    if len(tokens) > 1 and tokens[0].lower() not in _TYPE_LEAD_WORDS:
        # `p_id integer` -- the leading token is the argument NAME.
        tokens = tokens[1:]
    return normalize_arg_type(" ".join(tokens)) or None


def parse_buffer_identity(text: str, fallback: DdlObjectRef) -> DdlObjectRef | None:
    """The identity the BUFFER declares, or None when it cannot be determined.

    `fallback` supplies only the schema when the buffer's own name is
    unqualified -- never the name, the argument types or the table, which are
    exactly what precondition 1 exists to compare. Returning None is a REFUSAL
    signal for the caller (never a pass): an unparseable buffer must not be
    applied to a target database on the assumption that it matches.
    """
    trigger_match = _CREATE_TRIGGER_RE.search(text)
    routine_match = _CREATE_ROUTINE_RE.search(text)
    if trigger_match is not None and (
        routine_match is None or trigger_match.start() < routine_match.start()
    ):
        schema, table = _split_qualified_name(trigger_match.group("table"))
        _, name = _split_qualified_name(trigger_match.group("name"))
        return DdlObjectRef(
            kind="trigger",
            schema=schema or fallback.schema,
            name=name,
            table=table,
        )
    if routine_match is None:
        return None
    open_index = routine_match.end() - 1
    close_index = _matching_paren(text, open_index)
    if close_index is None:
        return None
    schema, name = _split_qualified_name(routine_match.group("name"))
    declarations = _split_top_level(text[open_index + 1 : close_index])
    arg_types = tuple(
        arg for arg in (_argument_type(part) for part in declarations) if arg is not None
    )
    return DdlObjectRef(
        kind=routine_match.group("kind").lower(),
        schema=schema or fallback.schema,
        name=name,
        arg_types=arg_types,
    )


def _comparable(ref: DdlObjectRef) -> tuple:
    """`DdlObjectRef.key` with the argument types normalized, so a buffer's
    `INTEGER` and the catalog's `integer` are the same identity."""
    return (
        ref.kind,
        ref.schema,
        ref.name,
        ref.table,
        tuple(normalize_arg_type(a) for a in ref.arg_types),
    )


# --- Reading a duck-typed CheckReport / ApplyOutcome ----------------------
#
# `db/ddl_check.py` and `db/apply.py` are another lane's modules; this panel
# must not import them (it would drag a DB-facing dependency into a widget).
# It reads the shapes §18.5 D3 pins -- `CheckReport{tier0..tier3, findings,
# caveats}`, `TierOutcome{status, reason, detail}`, `ApplyOutcome{ok, ...}` --
# by attribute, so a report from the real module and a stub in a test are
# read identically.

_TIER_ATTRS = ("tier0", "tier1", "tier2", "tier3")
#: A tier in one of these states did NOT verify anything. Reported as "could
#: not check", never collapsed into the overall OK state (§18.5 D3's hard rule).
_UNVERIFIED_STATUSES = ("unavailable", "errored")


def tier_outcomes(report: Any) -> list[tuple[str, Any]]:
    """`[("tier0", outcome), …]` for the tiers the report actually carries."""
    if report is None:
        return []
    found = []
    for attr in _TIER_ATTRS:
        outcome = getattr(report, attr, None)
        if outcome is not None:
            found.append((attr, outcome))
    return found


def _status(outcome: Any) -> str:
    return str(getattr(outcome, "status", "") or "")


def _reason(outcome: Any) -> str:
    return str(getattr(outcome, "reason", "") or getattr(outcome, "detail", "") or "")


def report_blockers(report: Any) -> list[str]:
    """What makes this report NOT green and cannot be overridden: tiers that
    ran and FOUND something, and the findings themselves (§18.5 precondition 2
    -- the override exists for what could not be CHECKED, never for what was
    checked and failed). Tiers that could not run are `report_unverified`."""
    blockers: list[str] = []
    for name, outcome in tier_outcomes(report):
        if _status(outcome) == "found_issues":
            reason = _reason(outcome)
            blockers.append(f"{name} reported issues" + (f" ({reason})" if reason else ""))
    findings = list(getattr(report, "findings", None) or [])
    if findings:
        blockers.append(f"{len(findings)} finding(s) from the last sandbox validation")
    return blockers


def report_unverified(report: Any) -> list[str]:
    """Exactly what could not be checked, tier by tier, with the reason --
    the enumeration §18.5 precondition 2's override dialog must show instead of
    a generic "proceed anyway"."""
    unverified: list[str] = []
    for name, outcome in tier_outcomes(report):
        if _status(outcome) in _UNVERIFIED_STATUSES:
            reason = _reason(outcome) or "no reason given"
            unverified.append(f"{name}: {_status(outcome)} ({reason})")
    return unverified


class DdlObjectEditorPanel(QWidget):
    """One editable DDL object, one tab (§18.5).

    Layout mirrors `EditorPanel`: the editor above, its own `FindReplaceBar`
    below, zero margins and zero spacing, plus the apply button row between
    them -- which exists **only** when an apply seam is wired: with no sandbox
    lane there is no row and no button, rather than dead controls (carve-out
    2).
    """

    #: Emitted only on a clean→dirty / dirty→clean TRANSITION, never per
    #: keystroke -- it drives the tab title's `" *"` marker.
    dirty_changed = Signal(bool)

    #: Emitted when Format Selection (§18.4/§18.5 carve-out 4/6) refuses --
    #: never on success. Carries the formatter's `sql.issues.Issue` list, for
    #: the host to report to the Audit panel under the `[SQL]` prefix
    #: (not clickable, no line role -- carve-out 6).
    format_refused = Signal(list)

    #: Emitted with a list of ready-to-append Audit lines, each already
    #: carrying the `[Check]` prefix (§7/§18.5). The host appends them to the
    #: Audit panel verbatim -- the same "report outward, never reach into
    #: MainWindow" precedent as `format_refused`.
    check_reported = Signal(list)

    #: Emitted when "Deploy this edit…" picks the SAVE destination. The panel
    #: does not save: it delegates to the host's existing Save gesture
    #: (`MainWindow._save_ddl_object_editor`) so there is exactly one save path
    #: (§18.5: "a picker in front of the three gestures, not a fourth thing
    #: that writes DDL or files on its own").
    save_requested = Signal()

    def __init__(
        self,
        ref: DdlObjectRef,
        text: str = "",
        resolve_save_path: Callable[[], Path | None] | None = None,
        parent: QWidget | None = None,
        *,
        apply_to_sandbox: Callable[[DdlObjectRef, str], Any] | None = None,
        apply_to_target: Callable[[DdlObjectRef, str], Any] | None = None,
        live_identity: Callable[[DdlObjectRef], DdlObjectRef | None] | None = None,
        sandbox_database_label: Callable[[], str] | None = None,
        target_database_label: Callable[[], str] | None = None,
        confirm: Callable[[str, str], bool] | None = None,
    ) -> None:
        """The apply seams (all optional; an unwired seam means the affordance
        is ABSENT, never a disabled control -- §18.5 carve-out 2):

        ``apply_to_sandbox(ref, ddl_text) -> CheckReport``
            §18.5 D3's `apply_and_check(session, ref, ddl_text, caps)` entry
            point with the session and capabilities already bound by the host
            (the sandbox controller). The panel owns no session and executes
            no SQL. Its return value is recorded as this buffer's validation
            result and drives Apply-to-target's precondition 2.
        ``apply_to_target(ref, ddl_text) -> ApplyOutcome``
            The real-database write, run only after all four hard
            preconditions pass. Wired to `db/apply.py::apply_ddl` behind the
            host's off-thread runner.
        ``live_identity(ref) -> DdlObjectRef | None``
            Re-introspects the live catalog and returns the object's CURRENT
            identity, or None when the target does not have the object yet.
            Precondition 1 compares it against the identity the buffer
            declares; **Apply to Target is absent unless this seam is wired**,
            because an unverifiable signature change is the one failure mode
            no confirmation can catch.
        ``sandbox_database_label() / target_database_label() -> str``
            e.g. ``"prod on db01:5432"`` -- what the confirmation names. A
            confirmation that does not say WHICH DATABASE is not compliant
            (§18.5 precondition 4), so an unlabelled destination is refused.
        ``confirm(title, text) -> bool``
            The confirmation gate itself, supplied by the host (a
            `QMessageBox.question` wrapper in the app). **Mandatory for both
            applies**: with no confirmation gate wired there is no apply
            affordance at all, because the panel has no silent-apply path to
            fall back to. Tests inject their own and never reach a modal.
        """
        super().__init__(parent)
        self._ref = ref
        self._save_path: Path | None = None
        # The §18.2 seam, in full. Default: the remembered path, or None when
        # nothing has been picked yet. Increment B's host supplies a callable
        # that runs Save As…; §18.2's supplies the project's ddl/ path. The
        # panel itself never opens a dialog and never learns what a project is.
        self._resolve_save_path: Callable[[], Path | None] = (
            resolve_save_path if resolve_save_path is not None else self._remembered_save_path
        )

        # --- The apply seams (§18.5). Nothing here touches a database. -----
        self._apply_to_sandbox = apply_to_sandbox
        self._apply_to_target = apply_to_target
        self._live_identity = live_identity
        self._sandbox_database_label = sandbox_database_label
        self._target_database_label = target_database_label
        self._confirm_seam = confirm
        #: The last validation report and the sha1 of the buffer it was run
        #: over. Apply-to-target's precondition 2 gate is "green FOR THIS
        #: BUFFER", so the hash is part of the record -- a report against an
        #: older buffer must never read as this buffer's clearance.
        self._last_check: tuple[str, Any] | None = None

        #: sha1 of the text last applied to the sandbox (§18.5), so the sandbox
        #: lane can render "changed since last applied" and so Check on a
        #: diverged buffer emits a `[Check]` caveat instead of silently
        #: validating a stale version. Written by `apply_to_sandbox`.
        self.applied_sha1: str | None = None

        # Schema-aware Ctrl+Space completion (§18.6). Injected the same way
        # `XmlEditor.set_schema_model` is (§11): None disables it entirely.
        # The panel never imports `db/introspect.py` and never learns what a
        # connection is -- it only ever sees this already-built, Qt-free
        # `SchemaIndex` (§18.5 D1's "never talks to a database" invariant).
        self._schema_index: "SchemaIndex | None" = None
        self._completion_popup: _CompletionPopup | None = None
        self._popup_wired = False
        # Session-only unattached-trigger table association (§18.6): NEVER
        # persisted anywhere -- not settings.json, not a sidecar file next to
        # a checked-out ddl/*.sql. Lives only in this tab's memory and is
        # forgotten on tab close (this panel is destroyed) or app restart.
        # One routine per tab, so a single slot is enough; keyed by nothing
        # more durable than the Python attribute itself.
        self._unattached_trigger_table: str | None = None

        self.editor = CodeEditor(language="sql")
        # EDITABLE -- the behavioral difference from §18.1's EditorPanel. In
        # particular `CodeEditor.replace_current_selection` (FindReplaceBar's
        # Replace) early-returns on a read-only editor; here it applies.
        self.editor.setReadOnly(False)
        self.find_replace_bar = FindReplaceBar(self.editor)

        # The apply row (§18.5). Built from the seams that are actually wired
        # and NOT ADDED AT ALL when none is -- carve-out 2's "no dead controls"
        # posture, the same convention `project_status_panel.py` uses.
        self.apply_row: QWidget | None = None
        self.sandbox_button: QPushButton | None = None
        self.target_button: QPushButton | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.editor)
        self._build_apply_row(layout)
        layout.addWidget(self.find_replace_bar)

        # Dirty state rides on the document's own modified flag, whose
        # modificationChanged signal fires on transitions only.
        self.editor.document().modificationChanged.connect(self.dirty_changed)
        self.set_text(text)

        # Carve-out 1 (§18.5, pinned invariant): CodeEditor neither consumes
        # nor re-emits Ctrl+Z/Ctrl+Y, so with no filter the window-level
        # QShortcut at main_window.py:401 would fire and revert the RAW XML
        # project buffer while this tab is focused. Installed on self.editor
        # (not CodeEditor itself, which the read-only §18.1 EditorPanel also
        # uses and must not gain this behavior) so ONLY this tab's own native
        # undo stack is ever touched. See eventFilter below.
        self.editor.installEventFilter(self)

        # Format Selection (§18.4's consumer, §18.5): Ctrl+Alt+F, enabled only
        # with a selection. The redundant eventFilter branch below handles the
        # key directly too, mirroring CodeEditorDialog's Ctrl+S/Ctrl+W
        # convention -- QShortcut activation is not reliable under the
        # offscreen platform in tests.
        self._format_shortcut = QShortcut(QKeySequence("Ctrl+Alt+F"), self)
        self._format_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._format_shortcut.activated.connect(self.format_selection)
        self._format_shortcut.setEnabled(False)
        self.editor.selectionChanged.connect(self._update_format_shortcut_enabled)
        # Carve-out 4: the refusal underline is transient -- cleared on the
        # next edit, or the next format attempt (format_selection itself
        # clears it before trying again).
        self.editor.textChanged.connect(self._clear_format_underline)

    # --- Identity ---------------------------------------------------------
    @property
    def ref(self) -> DdlObjectRef:
        return self._ref

    def tab_title(self) -> str:
        """The `CenterStage` tab label: the short identity plus the `" *"`
        dirty marker the Edit XSD tab already established (§11)."""
        return self._ref.short_title + (" *" if self.is_dirty() else "")

    def tab_tooltip(self) -> str:
        """The tab tooltip: the full source identity (§18.5)."""
        return self._ref.qualified

    # --- Buffer -----------------------------------------------------------
    def text(self) -> str:
        return self.editor.toPlainText()

    def set_text(self, text: str) -> None:
        """Load the buffer WITHOUT marking it dirty -- this is the injected
        load half, not a user edit."""
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)

    # --- Dirty state ------------------------------------------------------
    def is_dirty(self) -> bool:
        return self.editor.document().isModified()

    def mark_clean(self) -> None:
        """Clear the dirty marker -- what a successful save calls."""
        self.editor.document().setModified(False)

    # --- Navigation -------------------------------------------------------
    def navigate_to_line(self, line: int) -> None:
        """Jump to `line` (1-based), delegating to CodeEditor's shared
        navigation API (§8)."""
        self.editor.navigate_to_line(line)
        self.editor.setFocus()

    # --- The §18.2 save seam ---------------------------------------------
    def resolve_save_path(self) -> Path | None:
        """Where a save should write, or None if it cannot be resolved (in v1:
        the user cancelled Save As…, which cancels the save and is not an
        error). The entire surface §18.2 repoints."""
        return self._resolve_save_path()

    def remember_save_path(self, path: Path) -> None:
        """Remember the path a save resolved to, so every subsequent Ctrl+S
        writes silently to it for the rest of the session (§18.5)."""
        self._save_path = Path(path)

    @property
    def save_path(self) -> Path | None:
        return self._save_path

    def _remembered_save_path(self) -> Path | None:
        return self._save_path

    # --- Ctrl+Z / Ctrl+Y native-undo carve-out (§18.5 carve-out 1) --------
    def eventFilter(self, obj, event) -> bool:
        if obj is self.editor and event.type() in (
            QEvent.Type.ShortcutOverride,
            QEvent.Type.KeyPress,
        ):
            key = event.key()
            is_undo = key == Qt.Key.Key_Z and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            is_redo = key == Qt.Key.Key_Y and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            if is_undo or is_redo:
                if event.type() == QEvent.Type.ShortcutOverride:
                    # Claim the sequence so Qt never also fires the
                    # window-level Ctrl+Z/Ctrl+Y QShortcut for this key press
                    # (no double-undo, no leak into the Raw XML buffer).
                    event.accept()
                else:
                    self.editor.undo() if is_undo else self.editor.redo()
                return True
            if (
                key == Qt.Key.Key_F
                and event.modifiers()
                == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
            ):
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                else:
                    self.format_selection()
                return True
            # Ctrl+Space: schema-aware completion (§18.6). Handled here rather
            # than as a QShortcut for the same reason as Ctrl+Alt+F above --
            # reliable under the offscreen platform in tests.
            if key == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                else:
                    self._show_completions()
                return True
        if obj is self.editor and event.type() == QEvent.Type.ContextMenu:
            menu = self._build_context_menu()
            menu.exec(event.globalPos())
            return True
        return super().eventFilter(obj, event)

    def _build_context_menu(self):
        """Build (but do not exec) the editor's context menu -- split out so
        tests can inspect it directly instead of ever driving a real modal
        `QMenu.exec` (the `xml_editor.py` `_build_context_menu` precedent).
        Adds Format Selection (§18.4/§18.5) alongside the standard entries,
        enabled only with a selection -- same gate as the Ctrl+Alt+F shortcut."""
        menu = self.editor.createStandardContextMenu()
        menu.addSeparator()
        action = menu.addAction("Format Selection", self.format_selection)
        action.setEnabled(self.editor.textCursor().hasSelection())
        # The apply gestures (§18.5). Present only when their seam is wired
        # (carve-out 2) and NONE of them carries a shortcut -- an irreversible
        # outward effect must not be one keystroke away.
        menu.addSeparator()
        if self.has_sandbox_apply:
            menu.addAction("Apply to Sandbox", self.apply_to_sandbox)
        if self.has_target_apply:
            menu.addAction("Apply to Target…", self.apply_to_target)
        menu.addAction("Deploy this edit…", self.deploy_this_edit)
        return menu

    # --- Format Selection (§18.4's consumer, §18.5) ------------------------
    def _update_format_shortcut_enabled(self) -> None:
        self._format_shortcut.setEnabled(self.editor.textCursor().hasSelection())

    def _clear_format_underline(self) -> None:
        self.editor.setExtraSelections([])

    def format_selection(self) -> None:
        """Reindent the current selection in place (§18.4's `format_selection`,
        finally consumed), or -- on refusal -- leave it byte-for-byte
        unchanged, underline each offending span, and emit `format_refused`
        for the host to report under `[SQL]` (carve-outs 4 &amp; 6)."""
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return
        self._clear_format_underline()
        start = cursor.selectionStart()
        # QTextCursor.selectedText() joins lines with U+2029 (paragraph
        # separator), never "\n" -- the tokenizer expects real newlines.
        selected = cursor.selectedText().replace(" ", "\n")
        result = _format_selection_text(selected)
        if result.ok:
            cursor.beginEditBlock()
            cursor.insertText(result.text)
            cursor.endEditBlock()
            return
        selections = []
        for issue in result.issues:
            extra = QTextEdit.ExtraSelection()
            span_cursor = QTextCursor(self.editor.document())
            span_cursor.setPosition(start + issue.start)
            span_cursor.setPosition(start + issue.end, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            fmt.setUnderlineColor(QColor("red"))
            extra.cursor = span_cursor
            extra.format = fmt
            selections.append(extra)
        self.editor.setExtraSelections(selections)
        self.format_refused.emit(result.issues)

    # --- Apply (§18.5) -----------------------------------------------------
    #
    # Three gestures, none of them bound to a key: Apply to Sandbox, Apply to
    # Target, and the "Deploy this edit…" picker in front of them. The panel
    # executes no SQL and owns no session -- every DB-touching step is one of
    # the injected seams above.

    @property
    def has_sandbox_apply(self) -> bool:
        """Whether Apply to Sandbox is offered: the write seam AND the
        confirmation gate must both be wired. Its affordance is absent when
        they are not -- there is no unconfirmed apply path."""
        return self._apply_to_sandbox is not None and self._confirm_seam is not None

    @property
    def has_target_apply(self) -> bool:
        """Whether Apply to Target is offered at all: the write seam, the
        live-identity seam (precondition 1 cannot be enforced without it, and
        an unenforceable precondition must remove the gesture rather than
        weaken it) and the confirmation gate must ALL be wired."""
        return (
            self._apply_to_target is not None
            and self._live_identity is not None
            and self._confirm_seam is not None
        )

    def set_apply_seams(
        self,
        *,
        apply_to_sandbox: Callable[[DdlObjectRef, str], Any] | None = None,
        apply_to_target: Callable[[DdlObjectRef, str], Any] | None = None,
        live_identity: Callable[[DdlObjectRef], DdlObjectRef | None] | None = None,
        sandbox_database_label: Callable[[], str] | None = None,
        target_database_label: Callable[[], str] | None = None,
        confirm: Callable[[str, str], bool] | None = None,
    ) -> None:
        """Wire (or re-wire) the apply seams after construction -- what the
        host calls when the sandbox lane comes up, or when the connection
        profiles change. Replaces the whole set and rebuilds the button row, so
        a seam that goes away takes its affordance with it."""
        self._apply_to_sandbox = apply_to_sandbox
        self._apply_to_target = apply_to_target
        self._live_identity = live_identity
        self._sandbox_database_label = sandbox_database_label
        self._target_database_label = target_database_label
        self._confirm_seam = confirm
        self._build_apply_row(self.layout())

    def last_check_report(self) -> Any | None:
        """The validation report recorded for the CURRENT buffer, or None when
        the buffer has changed since (or was never checked)."""
        if self._last_check is None:
            return None
        digest, report = self._last_check
        return report if digest == self.text_sha1() else None

    def record_check_report(self, report: Any, text: str | None = None) -> None:
        """Record a ladder result the host obtained through another gesture
        (Check / Check without applying) so it counts for precondition 2. The
        hash is the buffer the report was produced from -- defaults to the
        buffer as it stands right now."""
        self._last_check = (_sha1(self.text() if text is None else text), report)

    def text_sha1(self) -> str:
        """sha1 of the current buffer -- the identity the sandbox's
        `applied.text_sha1` bookkeeping and the precondition-2 gate compare."""
        return _sha1(self.text())

    def apply_to_sandbox(self) -> bool:
        """§18.5 D3's `apply_and_check` gesture: commit this buffer to the
        sandbox and run the ladder over it. Confirm-gated behind a
        confirmation naming the object and the sandbox database. Returns True
        when the seam was actually invoked."""
        if not self.has_sandbox_apply:
            return False
        text = self.text()
        if not text.strip():
            self._report(["refused: the buffer is empty; nothing to apply."])
            return False
        database = self._database_label(self._sandbox_database_label)
        if database is None:
            self._report(
                [
                    "refused: no sandbox database is identified, and an apply "
                    "confirmation must name the database it will hit."
                ]
            )
            return False
        if not self._confirm(
            "Apply to Sandbox",
            f"Apply {self._ref.qualified} to sandbox database {database}?\n\n"
            "The sandbox is stateful: this edit is committed there and stays "
            "in its working set.",
        ):
            self._report([f"apply to sandbox of {self._ref.qualified} cancelled; nothing was applied."])
            return False
        report = self._apply_to_sandbox(self._ref, text)
        digest = _sha1(text)
        self.applied_sha1 = digest
        self._last_check = (digest, report)
        self._report(
            [f"applied {self._ref.qualified} to sandbox database {database}."]
            + self._result_lines(report)
        )
        return True

    def apply_to_target(self) -> bool:
        """Execute this buffer against the REAL target database, behind §18.5's
        four hard preconditions, in order:

        1. **Signature-change refusal** -- no override, no consent path.
        2. **Green sandbox validation**, with a *named* override enumerating
           exactly which tiers could not be checked.
        3. **Transactional apply, no revert snapshot** -- stated in the
           confirmation rather than implied.
        4. **A confirmation naming both the object and the database.**

        Plus the outright refusal on an empty buffer. Returns True only when
        the write seam was actually invoked.
        """
        if not self.has_target_apply:
            return False
        text = self.text()
        if not text.strip():
            self._report(["refused: the buffer is empty; nothing to apply to the target."])
            return False
        if not self._precondition_signature(text):
            return False
        database = self._database_label(self._target_database_label)
        if database is None:
            self._report(
                [
                    "refused: no target database is identified, and an apply "
                    "confirmation must name the database it will hit."
                ]
            )
            return False
        if not self._precondition_validation(database):
            return False
        if not self._confirm(
            "Apply to Target",
            f"Apply {self._ref.qualified} to database {database}?\n\n"
            "This executes DDL against the real database. It runs inside a "
            "transaction and rolls back if a statement is rejected, but there "
            "is no revert snapshot: a successful-but-wrong apply cannot be "
            "undone from within the app.",
        ):
            self._report([f"apply to target of {self._ref.qualified} cancelled; nothing was applied."])
            return False
        outcome = self._apply_to_target(self._ref, text)
        self._report(
            [f"applied {self._ref.qualified} to database {database}."] + self._result_lines(outcome)
        )
        return True

    def _precondition_signature(self, text: str) -> bool:
        """Precondition 1 -- refuse a changed signature, naming the mismatch.

        `CREATE OR REPLACE` on a changed `(schema, name, argtypes)` CREATES A
        SECOND FUNCTION and leaves the old one live: the statement succeeds and
        the confirmation was truthful, so no confirm-gate can catch it. Refused
        outright, with no override, and the user is pointed at the reviewable
        deployment-script path (§18.3).
        """
        buffer_ref = parse_buffer_identity(text, self._ref)
        if buffer_ref is None:
            self._report(
                [
                    "refused: could not determine the object's signature from the "
                    "buffer, so a changed signature cannot be ruled out. Use the "
                    "deployment-script path (Database ▸ Compare Schemas…)."
                ]
            )
            return False
        live_ref = self._live_identity(self._ref)
        if live_ref is None:
            self._report(
                [
                    f"{self._ref.qualified} does not exist in the target catalog; "
                    "applying will create it."
                ]
            )
            return True
        if _comparable(buffer_ref) != _comparable(live_ref):
            self._report(
                [
                    "refused: the buffer's signature differs from the live object. "
                    f"Buffer declares {buffer_ref.qualified}; the database has "
                    f"{live_ref.qualified}. PostgreSQL identifies a routine by "
                    "(schema, name, argument types), so applying this would create "
                    "a second object and leave the old one live. Use the "
                    "deployment-script path (Database ▸ Compare Schemas…)."
                ]
            )
            return False
        return True

    def _precondition_validation(self, database: str) -> bool:
        """Precondition 2 -- gate on a green sandbox validation for THIS
        buffer, with a *named* override.

        Findings are a hard block (they were checked, and they failed). What
        could not be checked -- an unavailable sandbox, a missing extension, a
        buffer never run through the ladder -- is overridable, but only through
        a dialog that ENUMERATES exactly what was not verified. Never a generic
        "proceed anyway": refusing silently would be worse than DBeaver;
        applying unvalidated *is* DBeaver.
        """
        report = self.last_check_report()
        blockers = report_blockers(report)
        if blockers:
            self._report(
                ["refused: the last sandbox validation of this buffer was not green."]
                + [f"  blocker: {line}" for line in blockers]
            )
            return False
        if report is None:
            unverified = [
                "the sandbox validation ladder has not been run over this buffer "
                "(no sandbox result, or the buffer changed since the last one)"
            ]
        else:
            unverified = report_unverified(report)
        if not unverified:
            return True
        enumerated = "\n".join(f"  - {line}" for line in unverified)
        if not self._confirm(
            "Apply to Target Without Full Validation",
            f"Apply {self._ref.qualified} to database {database} even though the "
            "following could NOT be checked?\n\n"
            f"{enumerated}\n\n"
            "A green result you did not get is not a green result.",
        ):
            self._report(
                [
                    f"refused: apply to target of {self._ref.qualified} needs a green "
                    "sandbox validation, and the override was declined."
                ]
                + [f"  not checked: {line}" for line in unverified]
            )
            return False
        self._report(
            [f"proceeding without full validation of {self._ref.qualified}:"]
            + [f"  not checked: {line}" for line in unverified]
        )
        return True

    # --- "Deploy this edit…" -- the destination picker (§18.5, 2026-08-05) --
    def deploy_this_edit(self) -> str | None:
        """Ask which of the three coexisting per-edit destinations this edit
        goes to, then DELEGATE to that destination's existing gesture. This
        command writes no DDL and no file of its own, adds no confirmation
        mechanism of its own, and carries **no keyboard shortcut** -- picking
        "Apply to Target" here still runs every one of that gesture's four hard
        preconditions. Returns the chosen destination key, or None when the
        user cancelled."""
        choice = self._prompt_destination()
        if choice is None:
            return None
        if choice == DEST_SANDBOX:
            self.apply_to_sandbox()
        elif choice == DEST_TARGET:
            self.apply_to_target()
        elif choice == DEST_SAVE:
            # The host's existing plain Save -- writes a file, touches no
            # database, exactly as Save always has.
            self.save_requested.emit()
        return choice

    def deploy_destinations(self) -> list[str]:
        """The destinations actually reachable right now. Save is always
        available; the two applies appear only when their seams are wired (no
        dead entries -- carve-out 2)."""
        destinations = []
        if self.has_sandbox_apply:
            destinations.append(DEST_SANDBOX)
        destinations.append(DEST_SAVE)
        if self.has_target_apply:
            destinations.append(DEST_TARGET)
        return destinations

    def _prompt_destination(self) -> str | None:
        """The picker itself -- `QInputDialog.getItem`, the app's existing
        simple-selection idiom (§18.6's unattached-trigger picker). Split out
        so tests drive the delegation without a modal."""
        destinations = self.deploy_destinations()
        labels = [DESTINATION_LABELS[d] for d in destinations]
        choice, ok = QInputDialog.getItem(
            self,
            "Deploy This Edit",
            f"Where should this edit to {self._ref.qualified} go?",
            labels,
            0,
            False,
        )
        if not ok:
            return None
        for destination, label in zip(destinations, labels):
            if label == choice:
                return destination
        return None

    # --- Apply plumbing ----------------------------------------------------
    def _build_apply_row(self, layout) -> None:
        """(Re)build the apply button row. With no seam wired there is no row
        at all -- an affordance whose seam is unwired is ABSENT, not disabled
        (§18.5 carve-out 2)."""
        if self.apply_row is not None:
            layout.removeWidget(self.apply_row)
            self.apply_row.setParent(None)
            self.apply_row.deleteLater()
            self.apply_row = None
        self.sandbox_button = None
        self.target_button = None
        if not (self.has_sandbox_apply or self.has_target_apply):
            return
        row = QWidget(self)
        box = QHBoxLayout(row)
        box.setContentsMargins(6, 3, 6, 3)
        box.setSpacing(6)
        box.addStretch(1)
        if self.has_sandbox_apply:
            self.sandbox_button = QPushButton("Apply to Sandbox", row)
            self.sandbox_button.clicked.connect(lambda: self.apply_to_sandbox())
            box.addWidget(self.sandbox_button)
        if self.has_target_apply:
            self.target_button = QPushButton("Apply to Target…", row)
            self.target_button.clicked.connect(lambda: self.apply_to_target())
            box.addWidget(self.target_button)
        self.apply_row = row
        # Always directly under the editor and above the find bar, whichever
        # order the row was (re)built in.
        layout.insertWidget(1, row)

    def _database_label(self, seam: Callable[[], str] | None) -> str | None:
        """The database name the confirmation must carry, or None when the
        host cannot name one -- in which case the apply is refused rather than
        confirmed with a nameless destination (§18.5 precondition 4)."""
        if seam is None:
            return None
        label = seam()
        label = "" if label is None else str(label).strip()
        return label or None

    def _confirm(self, title: str, text: str) -> bool:
        """The confirmation gate. No seam means NO apply -- never an
        unconfirmed one; the gestures are unreachable in that state anyway."""
        if self._confirm_seam is None:
            return False
        return bool(self._confirm_seam(title, text))

    def _report(self, lines: list[str]) -> None:
        """Emit Audit lines under the `[Check]` prefix (§7/§18.5) -- never
        `[Lint]` (PHP, §22) and never `[SQL]` (formatter refusals, §18.4)."""
        if not lines:
            return
        self.check_reported.emit([CHECK_PREFIX + line for line in lines])

    def _result_lines(self, result: Any) -> list[str]:
        """Render a duck-typed `CheckReport` / `ApplyOutcome` as Audit text:
        one line per tier ALWAYS (an unavailable tier is stated, never
        collapsed into the overall OK state), then findings, then caveats."""
        if result is None:
            return []
        lines = []
        for name, outcome in tier_outcomes(result):
            reason = _reason(outcome)
            status = _status(outcome) or "unknown"
            lines.append(f"  {name}: {status}" + (f" -- {reason}" if reason else ""))
        for finding in list(getattr(result, "findings", None) or []):
            message = str(getattr(finding, "message", finding))
            line_no = getattr(finding, "lineno", None) or getattr(finding, "line", None)
            lines.append(f"  finding: {f'line {line_no}: ' if line_no else ''}{message}")
        for caveat in list(getattr(result, "caveats", None) or []):
            lines.append(f"  caveat: {caveat}")
        ok = getattr(result, "ok", None)
        if ok is False:
            index = getattr(result, "statement_index", None)
            sqlstate = getattr(result, "sqlstate", "") or ""
            message = getattr(result, "message", "") or ""
            where = f" at statement {index}" if index is not None else ""
            lines.append(f"  failed{where}: {sqlstate} {message}".rstrip())
        return lines

    # --- Schema-aware Ctrl+Space completion (§18.6) ------------------------
    def set_schema_index(self, index: "SchemaIndex | None") -> None:
        """Inject the current `db/schema_index.py::SchemaIndex` (or None).
        Built once per DDL Explorer connect/refresh and handed to every open
        tab -- mirrors `XmlEditor.set_schema_model` (§11). `None` disables
        completion entirely (the default, e.g. no connection configured)."""
        self._schema_index = index

    def schema_index(self):
        """The injected `SchemaIndex`, or None. Read-only accessor for tests
        and callers that need to check whether completion is available."""
        return self._schema_index

    def _ensure_completion_popup(self) -> _CompletionPopup:
        if self._completion_popup is None:
            self._completion_popup = _CompletionPopup(self)
        return self._completion_popup

    def _popup_at_caret(self, popup: _CompletionPopup) -> None:
        """Show ``popup`` just below the caret and give it focus."""
        rect = self.editor.cursorRect()
        point = self.editor.viewport().mapToGlobal(rect.bottomLeft())
        popup.move(point)
        popup.show()
        popup.setFocus()

    def _rewire_popup(self, popup: _CompletionPopup, on_chosen) -> None:
        """Point the shared popup's signals at the current completion stage
        (the `xml_editor.py` precedent, §11): only disconnect a previous wiring
        when the popup was actually wired before, so a fresh popup's first use
        never triggers a PySide6 RuntimeWarning."""
        if self._popup_wired:
            popup.chosen.disconnect()
            popup.cancelled.disconnect()
        popup.chosen.connect(on_chosen)
        popup.cancelled.connect(popup.hide)
        self._popup_wired = True

    def _show_completions(self) -> None:
        """Ctrl+Space entry point (§18.6). Resolves the caret context and
        opens the popup for whichever of the three rows applies:
        schema-qualified table reference, NEW./OLD. in an attached trigger
        function, or NEW./OLD. in an unattached one (table-pick prompt
        first). No-op when no `SchemaIndex` is injected or the caret is not
        in a resolvable position."""
        if self._schema_index is None:
            return
        context = resolve_caret_context(self.editor.toPlainText(), self.editor.textCursor().position())
        if context is None:
            return
        if context.kind == ROW_VARIABLE:
            self._show_row_variable_completions(context)
        elif context.kind == DOTTED_PATH:
            self._show_dotted_path_completions(context)

    def _show_dotted_path_completions(self, context) -> None:
        """Schema-qualified table reference (§18.6 row 1): no schema typed
        yet offers schema names; a schema (optionally partial table) offers
        that schema's table names, schema-qualified, prefix-filtered."""
        index = self._schema_index
        if not context.parts:
            names = [n for n in index.known_schemas() if n.lower().startswith(context.prefix.lower())]
            if not names:
                return
            popup = self._ensure_completion_popup()
            popup.set_items([(n, n) for n in names])
            self._rewire_popup(popup, self._complete_identifier)
            self._popup_at_caret(popup)
            return
        schema = context.parts[0]
        tables = index.known_tables(schema, context.prefix)
        if not tables:
            return
        popup = self._ensure_completion_popup()
        popup.set_items([(t, f"{schema}.{t}") for t in tables])
        self._rewire_popup(popup, self._complete_identifier)
        self._popup_at_caret(popup)

    def _show_row_variable_completions(self, context) -> None:
        """NEW./OLD. inside a trigger function body (§18.6 rows 2 &amp; 3).

        Attached: the routine IS some trigger's function (reverse lookup via
        `TriggerInfo.function_name`) -- offer that table's columns directly.
        Unattached: tell the user plainly, then prompt a table pick (a small,
        modal `QInputDialog.getItem` picker -- the existing simple-selection-
        dialog idiom); the pick is session-only (§18.6, never persisted) and
        forgotten the moment this tab closes or the app restarts.
        """
        index = self._schema_index
        ref = self._ref
        table = self._unattached_trigger_table
        if table is None and not ref.is_trigger:
            trigger = index.trigger_for_function(ref.schema, ref.name, ref.arg_types)
            if trigger is not None:
                table = f"{trigger.schema}.{trigger.table}"
        if table is None and ref.is_trigger and ref.table:
            table = f"{ref.schema}.{ref.table}"
        if table is None:
            table = self._prompt_unattached_trigger_table()
            if table is None:
                return  # user cancelled the picker
            self._unattached_trigger_table = table

        columns = index.known_columns(table)
        prefix = context.prefix.lower()
        names = [c for c in columns if c.lower().startswith(prefix)]
        if not names:
            return
        popup = self._ensure_completion_popup()
        popup.set_items([(c, c) for c in names])
        self._rewire_popup(popup, self._complete_identifier)
        self._popup_at_caret(popup)

    def _prompt_unattached_trigger_table(self) -> str | None:
        """No trigger is defined for this function (§18.6): tell the user,
        then let them pick which table it belongs to. Returns the picked
        `"schema.table"` key, or None if there is nothing to pick from or the
        user cancels. A thin, directly-testable wrapper around
        `QInputDialog.getItem` -- the existing simple-selection-dialog idiom
        (mirrors `MainWindow._prompt_rename`'s `QInputDialog.getText` seam)."""
        index = self._schema_index
        options = sorted(
            f"{schema}.{table}"
            for schema in index.known_schemas()
            for table in index.known_tables(schema)
        )
        if not options:
            return None
        choice, ok = QInputDialog.getItem(
            self,
            "No Trigger Defined",
            "No trigger is defined for this function yet. "
            "Which table does it belong to? (This choice is not saved.)",
            options,
            0,
            False,
        )
        return choice if ok else None

    def _complete_identifier(self, name: str) -> None:
        """Insert `name` at the caret, replacing the partial prefix already
        typed (if any), hide the popup, and leave the caret just past the
        inserted text -- a single undoable edit."""
        popup = self._completion_popup
        if popup is not None:
            popup.hide()
        cursor = self.editor.textCursor()
        context = resolve_caret_context(self.editor.toPlainText(), cursor.position())
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
