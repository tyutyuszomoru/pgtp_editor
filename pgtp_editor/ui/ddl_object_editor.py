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

**Apply is never bound to a keyboard shortcut** -- neither `Check and commit
to sandbox` nor `Apply to quality`: *an irreversible outward effect must not be
one keystroke away* (§18.5). Every apply is confirm-gated behind a confirmation
naming **both the object and the database** it will hit.

**One name per operation** (FQ-026). `GESTURE_LABELS` below is the single source
for every user-visible string naming a gesture -- menu label, confirmation title,
Audit `[Check]` line, status bar. The panel offers no apply affordance of its
own: the button row and the context-menu apply entries are deleted, and the
gestures live on the Editor bar's `Deployment` / `Parsing` menus, which call
these methods.

**Findings no longer travel on `check_reported`** -- §18.5 D3a splits the Audit
report into two channels and explicitly overrides §28's shipped behavior (which
folded findings into the narrative lines as `"  finding: …"` strings): the
narrative channel `check_reported` stays unclickable, while findings go out as
OBJECTS on `check_findings`, because a pre-formatted string cannot carry the
`UserRole` line and `UserRole+1` object key that click-to-navigate needs. A
future reader looking for the `finding:` lines should read §18.5 D3a, not §28.
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
    QInputDialog,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.sql.caret_context import (
    ALIAS_REF,
    DOTTED_PATH,
    LOCAL_REF,
    ROW_VARIABLE,
    resolve_caret_context,
)
from pgtp_editor.sql.formatter import format_selection as _format_selection_text
from pgtp_editor.ui.code_editor import (
    CLAIMED_NOT_UNDO_REDO,
    REDO,
    UNDO,
    CodeEditor,
    apply_editor_operation,
    apply_shrink_structural_selection,
    classify_editor_chord,
    is_mutating_editor_operation,
)
from pgtp_editor.ui.format_settings import current_sql_config
from pgtp_editor.ui.completion_popup import CompletionPopupHostMixin
from pgtp_editor.ui.expand_select_seam import expand_select_expansion
from pgtp_editor.ui.schema_gesture_seam import SchemaGestureHostMixin
from pgtp_editor.ui.find_replace_bar import FindReplaceBar, install_focus_shortcuts

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

#: **The four gestures, and the ONE name each of them has** (FQ-026).
#:
#: Eight user-visible names denoted four operations until FQ-026: `Apply to
#: Sandbox` (button), `Run on sandbox` (menu), `Deploy this edit… → sandbox`
#: (picker) and the confirmation titled `Apply to Sandbox` were all one path,
#: and the menu label had already DRIFTED from the confirmation title because
#: they were separate string literals. That drift is what produced the reported
#: confusion, so the invariant this table exists to hold is:
#:
#:   **one name per operation, used identically across the menu label, the
#:   confirmation-dialog title, the Audit `[Check]` line, the status bar and
#:   the manual.**
#:
#: Every one of those surfaces reads THIS mapping. Re-typing a label at a call
#: site is the bug; if a name changes it changes here, once. (This is the role
#: the deleted `DESTINATION_LABELS` argued for in its own docstring -- *"they
#: must come from one place or the UI and the manual disagree"* -- re-homed
#: rather than dropped when its picker went away, and widened from the three
#: destinations to all five gestures a DDL object tab offers.)
#:
#: The ids are the SLUGS of the labels, i.e. the last segment of the menu-path
#: command id `toolbar_registry.command_id_for` derives -- so a renamed label is
#: visibly a renamed id, which is what `RENAMED_ID_ALIASES` has to carry a row
#: for.
GESTURE_CHECK_AND_COMMIT = "check-and-commit-to-sandbox"
GESTURE_CHECK_AND_ROLLBACK = "check-and-rollback"
GESTURE_APPLY_TO_QUALITY = "apply-to-quality"
GESTURE_CHECK_IN_SANDBOX = "check-object-in-sandbox"
GESTURE_SAVE_IN_PROJECT = "save-in-project"

GESTURE_LABELS = {
    # `apply_and_check` -- the whole ladder, `commit=True`, a bookkeeping row.
    # The name says both halves: it CHECKS, and unlike its neighbour it KEEPS
    # the result. Was `Apply to Sandbox` / `Run on sandbox` / a picker entry.
    GESTURE_CHECK_AND_COMMIT: "Check and commit to sandbox",
    # `probe_check` -- the identical ladder with `commit=False`. Named for the
    # single thing that distinguishes it from the entry above, which its old
    # name (`Check Object Without Applying`) buried in a negation.
    GESTURE_CHECK_AND_ROLLBACK: "Check and rollback",
    # `apply_to_target` and its four hard preconditions. Was `Apply to Target`
    # (button + confirmation title) AND `Run on quality` (menu) -- two names,
    # one gesture, which is the drift in its purest form.
    GESTURE_APPLY_TO_QUALITY: "Apply to quality",
    # `recheck`. KEEPS its name and its home on `Parsing`: FQ-026 changes only
    # how its result is surfaced, not what it runs, so it is still a genuine
    # check and still the odd one out that applies nothing.
    GESTURE_CHECK_IN_SANDBOX: "Check Object in Sandbox",
    # The plain Save. Touches no database; named by FQ-020 and unchanged.
    GESTURE_SAVE_IN_PROJECT: "Save in Project",
}

#: Why a DB-touching gesture is NOT on offer, stated to the user rather than
#: left as a silent absence (FQ-009: the requester's complaint was "there is no
#: option to save to the database" -- which was true of the *reachable*
#: destinations and invisible as a reason). Carve-out 2 still holds: an
#: unavailable gesture is not a selectable-but-dead entry.
#:
#: **This table OUTLIVED the picker it was written for.** FQ-026 lists it for
#: deletion alongside `DESTINATION_LABELS`, but it has two live non-picker
#: consumers -- `MainWindow._report_destination_unavailable` (the `Deployment`
#: entries' own refusal) and `MainWindow._refuse_sandbox_gesture`, which BUG-040
#: deliberately reuses verbatim so the check gestures and the apply gestures
#: cannot explain one absence two ways. Deleting it would have deleted those
#: sentences, not just the picker's; it is re-keyed onto the gesture ids above
#: instead.
GESTURE_UNAVAILABLE_REASONS = {
    # BUG-040 deleted `Database ▸ Open Sandbox Session`, which this sentence
    # used to name — the session now opens with the project. So the remedy is
    # the `Open` button on the refusal itself (this string is reused verbatim
    # inside that dialog) plus the place the connection can be corrected.
    #
    # That place is **Project Settings**, which since 2026-08-09 is where the
    # whole sandbox lives: the connection, the mode, and the `Provision sandbox`
    # / `Reset sandbox` / `Create a sandbox database for me` group.
    # `Database ▸ Sandbox Setup…` is deleted, so naming it would point at a menu
    # entry that no longer exists.
    #
    # The gap this comment used to record is CLOSED. It said Project Settings
    # could edit a connection but not provision, so "none is set up yet" had no
    # in-project remedy — true while the provisioning gestures lived in the
    # deleted dialog, and the reason the owner moved them. Both halves of this
    # sentence now have a remedy on one tab.
    GESTURE_CHECK_AND_COMMIT: (
        "no sandbox session is open — the project's sandbox could not be "
        "reached, or none is set up yet (check its connection in Project "
        "Settings)"
    ),
    # FQ-020 wired this lane, so the old *"not wired in this build"* wording is
    # retired: with no project the host resolves a quality target and the gesture
    # works, and the reason a destination is missing is now a CONNECTION fact.
    # The project-mode leg is still blocked (BUG-034 never populates
    # `ProjectSettings.target` from the `.pgtp`), which is why the remedy names
    # both places a target can come from.
    GESTURE_APPLY_TO_QUALITY: (
        "no quality target could be resolved with a password — configure it in "
        "Database ▸ Connection Setup… (projectless) or Project Settings ▸ "
        "Connections (with a project open). Precondition 1 re-checks the "
        "object's signature against the live catalog, so it cannot be enforced "
        "without a reachable connection"
    ),
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


class DdlObjectEditorPanel(
    SchemaGestureHostMixin, CompletionPopupHostMixin, QWidget
):
    """One editable DDL object, one tab (§18.5).

    Layout mirrors `EditorPanel` exactly: the editor above, its own
    `FindReplaceBar` below, zero margins and zero spacing. **Nothing between
    them** -- the apply button row that used to sit there is deleted (FQ-026),
    so a DDL object tab is an editor and a find bar, and every gesture that
    reaches a database is named on the Editor menu bar.
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

    #: The CLICKABLE second Audit channel (§18.5 D3a). Carries the duck-typed
    #: `CheckFinding` OBJECTS -- never pre-formatted strings, because a string
    #: cannot carry the `UserRole` line and the `UserRole+1` object key that
    #: click-to-navigate needs. The host (`MainWindow`) renders them
    #: (`"[Check] {SEVERITY} line {N}: {message}"`) and owns those roles; the
    #: panel only emits. Payload objects are read BY ATTRIBUTE only --
    #: `severity`, `message`, `lineno`/`line` -- the same duck-typing
    #: discipline `tier_outcomes`/`report_blockers` already use, so a test
    #: stub is as good as a real `db/ddl_check.py::CheckFinding`. The payload
    #: deliberately carries no `ref`: object identity reaches the host through
    #: the per-panel `lambda findings, ref=ref:` closure at the wiring site,
    #: which keeps the signature literally `check_findings(list)`.
    check_findings = Signal(list)

    #: `save_requested` stood here until FQ-026. It existed so the deleted
    #: "Deploy this edit…" picker's SAVE destination could delegate outward
    #: instead of writing a file itself; the picker was its only emitter, so
    #: with the picker gone the signal was emitted by nothing and connected by
    #: the host to a slot that could never fire. `Deployment ▸ Save in Project`
    #: reaches `MainWindow._save_ddl_object_editor` directly -- still exactly
    #: one save path.

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

        ``apply_to_sandbox(ref, ddl_text) -> CheckReport | None``
            §18.5 D3's `apply_and_check(session, ref, ddl_text, caps)` entry
            point with the session and capabilities already bound by the host
            (the sandbox controller). The panel owns no session and executes
            no SQL. Its return value is recorded as this buffer's validation
            result and drives Apply-to-target's precondition 2.

            **It may return `None`, meaning "the result will arrive later".**
            The real host runs the ladder off the GUI thread
            (`SandboxController.run_apply` through its `_run_async` seam), so
            there is nothing to return at call time; blocking the event loop on
            a `CREATE OR REPLACE` plus a `plpgsql_check` SELECT to keep this
            seam synchronous would defeat the reason that seam exists. A `None`
            return therefore records NOTHING here -- neither
            `applied_sha1` nor a precondition-2 clearance, both of which would
            be claims about an apply whose outcome is still unknown -- and the
            host is expected to land the report through `record_apply_result`
            when the worker finishes. A seam that returns a report keeps the
            fully synchronous behavior.
        ``apply_to_target(ref, ddl_text) -> ApplyOutcome | None``
            The real-database write, run only after all four hard
            preconditions pass. Wired to `db/apply.py::apply_ddl` behind the
            host's off-thread runner — which is why, exactly like
            `apply_to_sandbox`, **`None` is allowed and means "the result will
            arrive later"**: the panel then says the apply is *running* rather
            than claiming it succeeded, and the host reports the real outcome.
        ``live_identity(ref) -> DdlObjectRef | None``
            Re-introspects the live catalog and returns the object's CURRENT
            identity, or None when the target does not have the object yet.
            Precondition 1 compares it against the identity the buffer
            declares; **`Apply to quality` is absent unless this seam is wired**,
            because an unverifiable signature change is the one failure mode
            no confirmation can catch.

            `None` means *"introspection succeeded and the object is not
            there"* — never *"the lookup failed"*, which would silently clear
            precondition 1 on an unreachable database. A host that cannot read
            the catalog must **raise**; the panel turns any exception into a
            stated refusal (see `_precondition_signature`).
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

        #: §18.5 D4's "Run in Sandbox Console" bridge -- a one-way seam that
        #: hands the SELECTION to the console tab (which is the ONE execution
        #: surface) and returns nothing. `Callable[[str], None]`: text in,
        #: nothing out, so there is no result path for a later edit to hook up
        #: and this panel stays non-executable. Context-menu only, no button,
        #: no shortcut; absent (not disabled) while unwired -- carve-out 2: a
        #: bridge to a console that cannot exist is a dead control.
        self._run_in_console: Callable[[str], None] | None = None

        # Schema-aware Ctrl+Space completion (§18.6). Injected the same way
        # `XmlEditor.set_schema_model` is (§11): None disables it entirely.
        # The panel never imports `db/introspect.py` and never learns what a
        # connection is -- it only ever sees this already-built, Qt-free
        # `SchemaIndex` (§18.5 D1's "never talks to a database" invariant).
        self._schema_index: "SchemaIndex | None" = None
        self._init_completion_popup()
        # Session-only unattached-trigger table association (§18.6): NEVER
        # persisted anywhere -- not settings.json, not a sidecar file next to
        # a checked-out ddl/*.sql. Lives only in this tab's memory and is
        # forgotten on tab close (this panel is destroyed) or app restart.
        # One routine per tab, so a single slot is enough; keyed by nothing
        # more durable than the Python attribute itself.
        self._unattached_trigger_table: str | None = None

        self.editor = CodeEditor(language="sql")
        # Expand-`SELECT` (FQ-030 slice 1). The editor owns the ONE insertion
        # path; this seam is the only part that needs a schema, which is why it
        # is wired from here -- `CodeEditor` never learns what a `SchemaIndex`
        # is. Reads `self._schema_index` at gesture time, so a later
        # `set_schema_index` (a reconnect, a refresh) is picked up with no
        # re-wiring.
        self.editor.set_dynamic_expander(self._expand_select_expansion)
        # EDITABLE -- the behavioral difference from §18.1's EditorPanel. In
        # particular `CodeEditor.replace_current_selection` (FindReplaceBar's
        # Replace) early-returns on a read-only editor; here it applies.
        self.editor.setReadOnly(False)
        self.find_replace_bar = FindReplaceBar(self.editor)

        # **There is no apply/deploy button row** (FQ-026). It held three
        # buttons -- `Deploy this edit…`, `Apply to Sandbox`, `Apply to Target…`
        # -- that merely CALLED the gestures the Editor bar's `Deployment` menu
        # already names, so it was three more label strings free to drift from
        # the menu's, which is half of what made eight names denote four
        # operations. Deleting it removed callers, not capability: every gesture
        # is on `Deployment` / `Parsing` by its one canonical name
        # (`GESTURE_LABELS`), and the owner explicitly accepted the consequence
        # that a DDL object tab carries NO in-tab apply affordance -- the same
        # call FQ-020 made for saving.
        #
        # It is DELETED, not disabled: §18.5 carve-out 2 is explicit that an
        # affordance whose seam is unwired is ABSENT, and a permanently-dead
        # row would violate the very section this feature edits.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.editor)
        layout.addWidget(self.find_replace_bar)

        # FQ-016: the bar is permanently visible; Ctrl+F / Ctrl+R focus it,
        # scoped to this tab and its children.
        self._focus_find_shortcut, self._focus_replace_shortcut = (
            install_focus_shortcuts(self, self.find_replace_bar)
        )

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
        # with a selection.
        #
        # THIS QShortcut IS THE GESTURE'S ONLY KEYBOARD HOST (DEC-012,
        # BUG-054). The rule it applies: **any gesture with a command form --
        # menu bar OR context menu -- has exactly one keyboard host.** Format
        # Selection has a command form (the context-menu action in
        # `_build_context_menu`), so it is inside that rule; DEC-009's
        # widget-hosted carve-out is narrower than it reads and covers only
        # gestures with NO command form at all (Ctrl+Alt+E, Ctrl+Alt+C,
        # Ctrl+Alt+J, Ctrl+Space -- the branches below). A context-menu entry
        # is a command, so it does not cover this one.
        #
        # The `eventFilter` branch that used to answer Key_F+Ctrl|Alt as well
        # is DELETED. Both of its stated justifications were dead: "QShortcut
        # activation is not reliable under the offscreen platform" is
        # measurably false (BUG-046 -- shortcuts do activate offscreen; what
        # fails is key delivery to a widget that was never `show()`n, so the
        # test must send the key at the top level's `windowHandle()`), and the
        # `CodeEditorDialog` Ctrl+S/Ctrl+W double-hosting it cited as precedent
        # was itself removed by BUG-046. The sibling `SqlConsolePanel` ships this
        # exact gesture the same way -- one `QShortcut` as the only keyboard
        # host, same scope, same selection gate, and **no `Ctrl+Alt+F` branch in
        # its `eventFilter` either** -- so this is the shape that already works,
        # not a new one. (It also ships a click-only context-menu item, as this
        # tab does, since BUG-063; the point being made here is about the
        # keyboard host, which is single on both surfaces.)
        #
        # A consequence worth stating: the deleted branch was unconditional, so
        # a selection-less Ctrl+Alt+F used to reach `format_selection`. It now
        # does nothing, because the single host is disabled without a
        # selection -- the same answer the context-menu action gives, and the
        # same answer the console gives.
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
        load half, not a user edit.

        Re-arms the gutter's body-relative line column (FQ-031) **after** the
        `setPlainText`, which deliberately clears the anchor: an anchor
        describes one document, and a stale one would misnumber every line of a
        swapped one rather than merely omit the column. Only a routine tab asks
        for it -- a `CREATE TRIGGER` buffer has no body of its own (the body
        lives in the function the trigger calls, which opens as its own
        `function` tab and gets its own anchor). All the arithmetic and every
        bit of dollar-quote knowledge stays behind
        `EditorGutter.set_body_line_anchor_from_text`; a buffer with no
        locatable opener (a `LANGUAGE sql` routine) yields None there and the
        column simply does not appear."""
        self.editor.setPlainText(text)
        if not self._ref.is_trigger:
            self.editor.set_body_line_anchor_from_text(text)
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
        """Remember the path a save resolved to, so every subsequent
        `Deployment ▸ Save in Project` writes silently to it for the rest of the
        session (§18.5; the trigger moved with FQ-020, the mechanism did not)."""
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
            # DEC-014's fixed set, matched by the ONE shared matcher: only the
            # MATCHING is shared, never the answer. The sibling
            # `DdlEditorPanel.eventFilter` matches the same chords and answers
            # differently -- its buffer is synthesized and read-only, so it
            # refuses with a stated reason, whereas this tab is editable and
            # routes undo/redo into its own native stack.
            operation = classify_editor_chord(event)
            if operation is not None:
                if event.type() == QEvent.Type.ShortcutOverride:
                    # Claim the sequence so Qt never also fires the
                    # window-level Ctrl+Z/Ctrl+Y QShortcut for this key press
                    # (no double-undo, no leak into the Raw XML buffer).
                    event.accept()
                elif operation == UNDO:
                    self.editor.undo()
                elif operation == REDO:
                    self.editor.redo()
                elif is_mutating_editor_operation(operation):
                    # Paste (`Ctrl+Shift+Insert`) and the three line-editing
                    # gestures (`Ctrl+D`/`Ctrl+K`/`Ctrl+U`), bound by the app on
                    # both platforms (owner, 2026-08-10) where Qt binds them on
                    # the Linux/KDE scheme only. This tab is editable, so they
                    # run; the sibling `DdlEditorPanel` states a refusal instead,
                    # exactly as it does for undo.
                    apply_editor_operation(self.editor, operation)
                elif operation == CLAIMED_NOT_UNDO_REDO:
                    # `Ctrl+Shift+Z` = Shrink Selection (FQ-034). The claim was
                    # here first and is load-bearing rather than tidiness: Qt
                    # carries the chord as native `StandardKey.Redo` under
                    # `KB_Win | KB_X11`, so letting it fall through would redo on
                    # both platforms and silently defeat DEC-015. This feature
                    # gives that claim an answer instead of binding the chord --
                    # which is why `Select ▸ Shrink Selection` carries no
                    # `setShortcut`, and why every surface routes into the same
                    # `apply_shrink_structural_selection`.
                    apply_shrink_structural_selection(self.editor)
                # else: the one answer that still runs no operation.
                # Alt+Backspace / Alt+Shift+Backspace: Qt binds them `KB_Win`
                # only, so suppressing them here is what keeps the keyboard
                # identical on both systems.
                return True
            # NOTE (BUG-054/DEC-012): there is deliberately NO Ctrl+Alt+F
            # branch here. Format Selection has a context-menu command, so it
            # gets exactly one keyboard host -- the QShortcut in `__init__`.
            # Do not re-add it; see the comment there.
            #
            # Ctrl+Space: schema-aware completion (§18.6). Handled here rather
            # than as a QShortcut because it has no menu command at all, so it
            # is a widget behaviour and not a command with a second host
            # (DEC-009's carve-out proper), and it needs the injected
            # `SchemaIndex` plus this panel's own caret/popup state -- neither
            # of which a `CodeEditor` widget may hold (§18.5 D1: the editor
            # panel never talks to a database). Completion is also
            # intrinsically focus-scoped: a window shortcut would fire it for
            # whichever widget happened to be focused.
            if key == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                else:
                    self._show_completions()
                return True
            # Ctrl+Alt+J: JOIN-on-FK (FQ-030 slice 3), in the `Ctrl+Alt+`
            # editor-gesture family Format Selection established and next to
            # the two expansion gestures `CodeEditor` handles itself. It is
            # handled HERE rather than there because it needs a `SchemaIndex`,
            # which no editor widget may hold (§18.5 D1).
            if (
                key == Qt.Key.Key_J
                and event.modifiers()
                == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
            ):
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                else:
                    self.join_on_fk()
                return True
            # Ctrl+Shift+Space: signature help (FQ-030 slice 3) -- the IDE
            # convention, and one modifier away from the Ctrl+Space completion
            # it is the sibling of. Explicit-trigger only, like everything else
            # on this path: nothing here is connected to `textChanged`.
            if key == Qt.Key.Key_Space and event.modifiers() == (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
            ):
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                else:
                    self.show_signature_help()
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
        # §18.5 D4's console bridge -- placed with Format Selection and BEFORE
        # the separator that opens the apply group, so an execution-adjacent
        # copy gesture is not visually grouped with the irreversible applies.
        # Absent while the seam is unwired (carve-out 2), and -- like Format
        # Selection -- disabled without a selection. No shortcut.
        if self.has_run_in_console:
            console_action = menu.addAction("Run in Sandbox Console", self.run_in_sandbox_console)
            console_action.setEnabled(self.editor.textCursor().hasSelection())
        # **The apply gestures are NOT here** (FQ-026). This menu carried
        # `Apply to Sandbox`, `Apply to Target…` and `Deploy this edit…`, each
        # with its own label string and each merely calling a gesture the
        # `Deployment` menu already names. They went with the button row for
        # the same reason and under the same owner ruling -- a DDL object tab
        # gets no in-tab apply affordance -- so the right-click menu keeps only
        # what is genuinely tab-local: Format Selection and the console bridge,
        # neither of which is an apply and neither of which exists anywhere
        # else.
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
        # FQ-033: the ruleset is read AT GESTURE TIME, so a change made in
        # `Settings ▸ Autoformatter settings…` applies to the very next
        # Ctrl+Alt+F with no notification plumbing between the dialog and every
        # open tab. The default config is byte-identical to the pre-FQ-033
        # behaviour, so an untouched install formats exactly as before.
        result = _format_selection_text(selected, config=current_sql_config())
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
    # TWO gestures, neither bound to a key: `Check and commit to sandbox` and
    # `Apply to quality` (FQ-026 -- the picker that used to sit in front of
    # them is deleted). The panel executes no SQL and owns no session -- every
    # DB-touching step is one of the injected seams above -- and it offers no
    # affordance of its own either: the gestures are reached from the Editor
    # bar's `Deployment` menu, which calls these methods.

    @property
    def has_sandbox_apply(self) -> bool:
        """Whether `Check and commit to sandbox` is offered: the write seam AND the
        confirmation gate must both be wired. Its affordance is absent when
        they are not -- there is no unconfirmed apply path."""
        return self._apply_to_sandbox is not None and self._confirm_seam is not None

    @property
    def has_run_in_console(self) -> bool:
        """Whether "Run in Sandbox Console" is offered (§18.5 D4). True only
        when the seam is wired: with no console there is no entry at all
        rather than a disabled one (carve-out 2). Note this is NOT an apply
        gesture and takes no confirmation -- it executes nothing."""
        return self._run_in_console is not None

    def set_run_in_console(self, seam: Callable[[str], None] | None) -> None:
        """Wire (or unwire) §18.5 D4's console bridge.

        Deliberately NOT folded into `set_apply_seams`: that call replaces the
        whole apply SET, while this affordance is context-menu-only and is not
        an apply -- putting it there would make wiring the apply lane silently
        drop it."""
        self._run_in_console = seam

    def run_in_sandbox_console(self) -> bool:
        """Hand the current SELECTION to the Sandbox SQL Console (§18.5 D4).

        Copies text and nothing else: no apply seam, no session, no SQL, no
        result. Returns False and does nothing when there is no selection or no
        console; True when the seam was handed the text."""
        if self._run_in_console is None:
            return False
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return False
        # QTextCursor.selectedText() joins lines with U+2029 (paragraph
        # separator), never "\n" -- the same conversion `format_selection` does.
        self._run_in_console(cursor.selectedText().replace(" ", "\n"))
        return True

    @property
    def has_target_apply(self) -> bool:
        """Whether `Apply to quality` is offered at all: the write seam, the
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
        profiles change. Replaces the whole SET, so a seam that goes away takes
        its gesture with it: `has_sandbox_apply`/`has_target_apply` go False and
        the host's `Deployment` entries refuse with the reason (carve-out 2, as
        narrowed to present-and-reporting by FQ-023).

        It no longer rebuilds anything -- there is no button row to rebuild
        (FQ-026)."""
        self._apply_to_sandbox = apply_to_sandbox
        self._apply_to_target = apply_to_target
        self._live_identity = live_identity
        self._sandbox_database_label = sandbox_database_label
        self._target_database_label = target_database_label
        self._confirm_seam = confirm

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
        """§18.5 D3's `apply_and_check` gesture -- **`Check and commit to
        sandbox`** (FQ-026): run the whole ladder over this buffer and COMMIT
        it to the sandbox. Confirm-gated behind a confirmation naming the
        object and the sandbox database. Returns True when the seam was
        actually invoked.

        The method keeps its `apply_to_sandbox` name -- it is the seam's name
        and `db/ddl_check.py::apply_and_check`'s caller -- while every
        user-visible string comes from `GESTURE_LABELS`."""
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
        # The confirmation title is the MENU LABEL, from the one table -- it
        # used to be the literal "Apply to Sandbox" while the menu said "Run on
        # sandbox", so a user picking a menu entry answered a modal that named
        # the operation something else (FQ-026's headline symptom).
        gesture = GESTURE_LABELS[GESTURE_CHECK_AND_COMMIT]
        if not self._confirm(
            gesture,
            f"Check {self._ref.qualified} against sandbox database {database} "
            "and COMMIT it there?\n\n"
            "The sandbox is stateful: this edit is committed there and stays "
            "in its working set.",
        ):
            self._report(
                [f"{gesture} of {self._ref.qualified} cancelled; nothing was applied."]
            )
            return False
        report = self._apply_to_sandbox(self._ref, text)
        if report is None:
            # ASYNCHRONOUS seam (see `__init__`): the ladder is running off the
            # GUI thread. Say so, and record nothing -- the outcome lands later
            # through `record_apply_result`.
            self._report(
                [
                    f"applying {self._ref.qualified} to sandbox database "
                    f"{database}…"
                ]
            )
            return True
        digest = _sha1(text)
        self.applied_sha1 = digest
        self._last_check = (digest, report)
        self._report_result(
            [f"applied {self._ref.qualified} to sandbox database {database}."], report
        )
        return True

    def record_apply_result(self, report: Any, text: str | None = None) -> None:
        """Land an **asynchronous** Apply-to-Sandbox outcome (§18.5 D3): record
        it for precondition 2, mark the buffer as applied *only if it actually
        committed*, and render it over both Audit channels.

        The committed check is the whole point of the split: `apply_and_check`
        rolls the transaction back when any statement is rejected, so a report
        that is not `committed` means the sandbox does NOT hold this text -- and
        `applied_sha1` claiming otherwise is precisely the "lying about what the
        sandbox contains" §18.5 forbids. The headline says which of the two
        happened; the tiers, caveats and findings are the report's own.
        """
        applied = self.text() if text is None else text
        self.record_check_report(report, applied)
        database = self._database_label(self._sandbox_database_label) or "the sandbox"
        if bool(getattr(report, "committed", False)):
            self.applied_sha1 = _sha1(applied)
            headline = [f"applied {self._ref.qualified} to sandbox database {database}."]
        else:
            headline = [
                f"{self._ref.qualified} was NOT applied to sandbox database "
                f"{database}; the transaction did not commit."
            ]
        self._report_result(headline, report)

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
            self._report(["refused: the buffer is empty; nothing to apply to quality."])
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
        # As above: title == menu label == Audit vocabulary, from one table.
        # This one carried the sharpest drift -- the button and the
        # confirmation said "Apply to Target" while the menu said "Run on
        # quality" (FQ-026).
        if not self._confirm(
            GESTURE_LABELS[GESTURE_APPLY_TO_QUALITY],
            f"Apply {self._ref.qualified} to quality database {database}?\n\n"
            "This executes DDL against the real database. It runs inside a "
            "transaction and rolls back if a statement is rejected, but there "
            "is no revert snapshot: a successful-but-wrong apply cannot be "
            "undone from within the app.",
        ):
            self._report(
                [
                    f"{GESTURE_LABELS[GESTURE_APPLY_TO_QUALITY]} of "
                    f"{self._ref.qualified} cancelled; nothing was applied."
                ]
            )
            return False
        outcome = self._apply_to_target(self._ref, text)
        if outcome is None:
            # ASYNCHRONOUS seam, the same widening `apply_to_sandbox()` already
            # carries and for the same reason: the real host runs the write off
            # the GUI thread, so there is no outcome at call time. Announcing
            # "applied" here would be a claim about a write whose result is still
            # unknown -- the host reports the real outcome when the worker
            # finishes. A seam that returns an outcome keeps the fully
            # synchronous behaviour.
            self._report(
                [f"applying {self._ref.qualified} to database {database}…"]
            )
            return True
        self._report_result(
            [f"applied {self._ref.qualified} to database {database}."], outcome
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
        # The seam reaches a real catalog, so it can FAIL -- and its `None`
        # already means something else entirely ("the target does not have this
        # object; applying will create it"). A host that reported a connection
        # failure as `None` would turn an unreachable database into a cleared
        # precondition 1, which is the one failure mode no confirmation can
        # catch. So any raise is a REFUSAL naming the error, never a fall-through
        # and never an unhandled exception out of a button click. (FQ-009: this
        # closes the hole before the seam is wired, not after.)
        try:
            live_ref = self._live_identity(self._ref)
        except Exception as exc:  # noqa: BLE001 -- any driver's error, refused alike
            self._report(
                [
                    "refused: could not read the live object's identity from the "
                    f"target ({type(exc).__name__}: {exc}), so a changed "
                    "signature cannot be ruled out. Nothing was applied."
                ]
            )
            return False
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
            # The override dialog is part of `Apply to quality`, so it is
            # titled in that gesture's vocabulary rather than in a fifth one.
            f"{GESTURE_LABELS[GESTURE_APPLY_TO_QUALITY]} without full validation",
            f"Apply {self._ref.qualified} to database {database} even though the "
            "following could NOT be checked?\n\n"
            f"{enumerated}\n\n"
            "A green result you did not get is not a green result.",
        ):
            self._report(
                [
                    f"refused: {GESTURE_LABELS[GESTURE_APPLY_TO_QUALITY]} of "
                    f"{self._ref.qualified} needs a green "
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

    # --- The "Deploy this edit…" picker: DELETED (FQ-026) ------------------
    #
    # `deploy_this_edit`, `deploy_destinations`, `unavailable_destinations`,
    # `deploy_prompt_text` and `_prompt_destination` stood here. The picker was
    # a chooser in FRONT of three gestures -- it wrote no DDL and no file, added
    # no confirmation of its own, and delegated to Save / apply-to-sandbox /
    # apply-to-quality.
    #
    # It is deleted by owner ruling (2026-08-10): *"the picker is not needed if
    # the other menus are explicit of the target"*, and they are -- `Deployment`
    # carries `Save in Project`, `Check and commit to sandbox` and `Apply to
    # quality`, each naming its own destination. FQ-009's discoverability
    # complaint ("there is no option to save to the database") is answered by
    # those three named entries rather than by a fourth gesture asking a
    # question the menu already displays the answer to.
    #
    # **This is a deliberate withdrawal of a live, shipped feature**, not the
    # closing of a spec-vs-code gap: it shipped on three always-present surfaces
    # (the panel button, the tab context menu and `Database ▸ Deploy This
    # Edit…`). All three go, and nothing it could reach became unreachable. A
    # pinned `database.deploy-this-edit` degrades away through `resolve_ids` --
    # a deletion gets NO `RENAMED_ID_ALIASES` row, because a row would point at
    # a command that does not exist.

    # --- Apply plumbing ----------------------------------------------------
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

    def _report_result(self, headline: list[str], result: Any) -> None:
        """Report a ladder result over BOTH Audit channels (§18.5 D3a): the
        narrative lines (`headline` + tiers + caveats + failure) on
        `check_reported`, and the findings -- as objects -- on
        `check_findings`.

        A finding NEVER appears in the narrative channel; `check_findings` is
        not emitted at all when there are none, so the host never renders an
        empty findings batch."""
        self._report(headline + self._result_lines(result))
        findings = list(getattr(result, "findings", None) or [])
        if findings:
            self.check_findings.emit(findings)

    def report_check_result(self, result: Any) -> None:
        """Make a ladder result VISIBLE -- both channels, no headline.

        Deliberately separate from `record_check_report`, which only RECORDS a
        result for precondition 2: recording and showing stay two acts, so a
        host can do either without implying the other."""
        self._report_result([], result)

    def _result_lines(self, result: Any) -> list[str]:
        """Render a duck-typed `CheckReport` / `ApplyOutcome` as NARRATIVE
        Audit text: one line per tier ALWAYS (an unavailable tier is stated,
        never collapsed into the overall OK state), then caveats, then the
        `ok is False` failure line.

        **Findings are NOT here** (§18.5 D3a's ledger override of §28). They go
        out as objects on `check_findings`, because a pre-formatted string
        cannot carry the `UserRole` line and `UserRole+1` object key that the
        host needs to make a finding clickable."""
        if result is None:
            return []
        lines = []
        for name, outcome in tier_outcomes(result):
            reason = _reason(outcome)
            status = _status(outcome) or "unknown"
            lines.append(f"  {name}: {status}" + (f" -- {reason}" if reason else ""))
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

    def _completion_editor(self):
        """CompletionPopupHostMixin hook: this panel wraps its editor rather
        than being one, so caret geometry comes off `self.editor`."""
        return self.editor

    # --- Expand-`SELECT` (§18.6 / FQ-030 slice 1) --------------------------
    def _expand_select_expansion(self, text: str, pos: int):
        """`CodeEditor.set_dynamic_expander` seam: the buffer in, an
        `Expansion` out. Three lines, in `ui/expand_select_seam.py`, shared
        verbatim with the SQL console -- the schema is the already-injected
        index and NOTHING here queries a database (§18.6's invariant)."""
        return expand_select_expansion(self._schema_index, text, pos)

    def expand_select(self) -> bool:
        """Ctrl+Alt+C: expand the bare `SELECT` at the caret (FQ-030 slice 1).

        Delegates to the editor, which applies the resulting `Expansion`
        through the same single-undo path a snippet goes through and states
        the reason when there is nothing to expand."""
        return self.editor.expand_select_at_caret()

    def _show_completions(self) -> None:
        """Ctrl+Space entry point (§18.6). Resolves the caret context and
        opens the popup for whichever row applies: schema-qualified table
        reference, NEW./OLD. in an attached trigger function, NEW./OLD. in an
        unattached one (table-pick prompt first), a FROM-clause `alias.`
        (FQ-030 slice 1) or a declared `local.` (slice 3). No-op when no
        `SchemaIndex` is injected or the caret is not in a resolvable
        position.

        **Explicit-trigger only.** This runs from the Ctrl+Space key press in
        `eventFilter` and nowhere else -- nothing connects it to
        `textChanged`. That is what makes `resolve_caret_context`'s cost
        (it re-tokenizes the buffer for `statement_at` / `from_clause` /
        `routine_scope`) affordable: it is paid once per deliberate keystroke,
        not once per character typed. **Do not connect this to an
        edit signal without first making that path cheap** -- on a 40 KB
        routine body a single resolve is a few hundred milliseconds, which is
        a visible stall if it happens while typing.

        Precedence between the kinds is decided in the pure layer
        (`sql/caret_context.py`): ALIAS_REF beats LOCAL_REF beats DOTTED_PATH
        for a one-segment name. Nothing is re-ranked here."""
        if self._schema_index is None:
            return
        context = resolve_caret_context(self.editor.toPlainText(), self.editor.textCursor().position())
        if context is None:
            return
        if context.kind == ROW_VARIABLE:
            self._show_row_variable_completions(context)
        elif context.kind == ALIAS_REF:
            self._show_alias_ref_completions(context)
        elif context.kind == LOCAL_REF:
            self._show_local_ref_completions(context)
        elif context.kind == DOTTED_PATH:
            self._show_dotted_path_completions(context)

    def _show_alias_ref_completions(self, context) -> None:
        """`alias.` where the caret's own FROM clause binds `alias` to a real
        table (§18.6 / FQ-030 slice 1): offer that table's columns.

        `table_ref.qualified` is the `SchemaIndex.known_columns()` key, and it
        is None when the table was written bare (`FROM jobcard j` -- no schema,
        and nothing here may guess a search path). Then, and whenever the table
        is not in the fetched schema, this degrades to the `DOTTED_PATH`
        reading of the very same context (the refinement keeps `parts`
        populated precisely so that fallback needs no re-resolution)."""
        ref = context.table_ref
        table = ref.qualified if ref is not None else None
        if table is None or not self._show_column_completions(table, context.prefix):
            self._show_dotted_path_completions(context)

    def _show_local_ref_completions(self, context) -> None:
        """`local.` where `local` is declared by the routine the caret is in
        (§18.6 / FQ-030 slice 3): a `rec hr.jobcard%ROWTYPE` offers that
        table's columns.

        `local_symbol.rowtype_qualified` is None for every local whose fields
        cannot be known from the text -- a `record`, a loop variable, a scalar,
        or a bare `jobcard%ROWTYPE` with no schema. There is nothing to offer
        then, so this degrades to the `DOTTED_PATH` reading rather than opening
        an empty popup."""
        symbol = context.local_symbol
        table = symbol.rowtype_qualified if symbol is not None else None
        if table is None or not self._show_column_completions(table, context.prefix):
            self._show_dotted_path_completions(context)

    def _show_column_completions(self, table: str, prefix: str) -> bool:
        """Open the popup on `table`'s columns filtered by `prefix`. Returns
        False (and opens nothing) when the table is unknown or no column
        matches, so a caller can fall back instead of showing an empty list.

        `SchemaIndex.column_entries` does the filtering AND the rendering: the
        popup's *key* stays the bare column name -- exactly what lands in the
        buffer -- while its *display* adds the type and whatever the column
        carries (PK, FK target, NOT NULL, default, comment), which is what
        tells `id integer` from `id text` at the moment of choosing. The
        display text must never reach the buffer, which is why this is a
        `(key, display)` pair and not a widened key."""
        entries = self._schema_index.column_entries(table, prefix)
        if not entries:
            return False
        popup = self._ensure_completion_popup()
        popup.set_items(entries)
        self._rewire_popup(popup, self._complete_identifier)
        self._popup_at_caret(popup)
        return True

    def _show_dotted_path_completions(self, context) -> None:
        """Schema-qualified table reference (§18.6 row 1): no schema typed
        yet offers schema names; a schema (optionally partial table) offers
        that schema's table names, schema-qualified, prefix-filtered; a schema
        AND a table (`hr.jobcard.`) offers that table's columns.

        The third segment is the cascade's last step and needs no new lookup
        idiom: `parts` is already `("hr", "jobcard")` there, and
        `"hr.jobcard"` is the `column_entries` key. Nothing matching shows
        nothing, the same fallback convention the other two steps follow --
        an empty popup would be a worse answer than none."""
        index = self._schema_index
        if len(context.parts) >= 2:
            self._show_column_completions(
                f"{context.parts[0]}.{context.parts[1]}", context.prefix
            )
            return
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

        self._show_column_completions(table, context.prefix)

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
