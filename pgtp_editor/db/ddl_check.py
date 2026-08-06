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

# pgtp_editor/db/ddl_check.py
"""The validation ladder's driver: `CheckRequest` -> findings (§18.5 D3).

**This module actually RUNS `plpgsql_check` against the sandbox and returns
what it found.** That distinction is the whole point: `db/sandbox.py` can
already say whether the extension is *installed*
(`SandboxCapabilities.plpgsql_check_state`), and an installation marker is not
a lint result. Until something calls the extension and parses its rows, the
DDL object editor's Audit panel has nothing to show but capability trivia.

**The failure this module exists to prevent is a green result that was never
earned.** A check that cannot run and returns an empty finding list is read by
every user as "clean" — which is worse than one that refuses, because the user
acts on it. So every path out of here is *distinguishable*: the extension
absent, available-but-not-installed, unprobed, the routine missing from the
sandbox (it never compiled), the executor raising, the extension returning
output we could not parse, and a genuine clean run each produce a different
`TierOutcome` with its own reason string. `passed` is emitted in exactly one
situation: the extension ran, we parsed its result, and there were no rows.

**Scope of this pass — tier 3 only, stated rather than implied.** D3's ladder
has four tiers; tiers 0–2 all hang off the write seam `db/apply.py::apply_ddl`
(tier 1 needs its notice channel, tier 2 *is* the apply), and that module does
not exist yet. Rather than omit them from the report — which would let the UI
render a tier-3-only report as a complete one — `CheckReport` carries tiers
0–2 as explicit `unavailable` outcomes naming the missing seam. The report
therefore composes, unchanged, with the panel that already reads it:
`ui/ddl_object_editor.py` reads `CheckReport{tier0..tier3, findings, caveats}`
and `TierOutcome{status, reason, detail}` duck-typed and treats
`unavailable`/`errored` as "could not check" — never as OK.

**Read-only.** This module runs a *read-only analysis function*; it applies no
DDL, writes nothing, and alters nothing (§18.3's never-auto-execute posture).
Applying an edit to the sandbox is `SandboxSession.apply`'s job and stays
there. Consequently this module reaches the database only through the
session's `query` side, never `execute` — a fact the caller can rely on.

Qt-free and, like `db/introspect.py` and `db/sandbox.py`, opens no connection
except through an injectable seam: every entry point takes `query=`
(defaulting to the session's executor), so the whole test suite runs with
psycopg absent and never touches a real database.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .config import ConnectionParams
from .sandbox import SandboxCapabilities, UnsafeIdentifierError, install_gate, quote_ident

#: Injectable read seam, mirroring `db/introspect.py::Runner` and
#: `db/sandbox.py::SandboxExecutor.query`: one SQL string in, rows out. The
#: default is the session's own executor; tests pass a canned callable.
Query = Callable[[ConnectionParams, str], "list[tuple]"]


class CheckSession(Protocol):
    """The slice of `db/sandbox.py::SandboxSession` this module needs — its
    connection params and its executor. Declared structurally so a test can
    hand in a two-attribute stub, and so this module never has to construct
    (or bypass) `open_sandbox`'s ownership gate itself."""

    params: ConnectionParams
    executor: Any


# ---------------------------------------------------------------------------
# Outcome vocabulary — the exact strings `ui/ddl_object_editor.py` reads
# ---------------------------------------------------------------------------

#: The four `TierOutcome.status` values §18.5 D3 pins. `ui/ddl_object_editor.py`
#: matches `"found_issues"` (a hard, non-overridable Apply-to-Target blocker)
#: and `("unavailable", "errored")` (its `_UNVERIFIED_STATUSES`, which drive the
#: named override) by these literal strings, so they are constants here rather
#: than an Enum whose `str()` would not compare equal.
STATUS_PASSED = "passed"
STATUS_FOUND_ISSUES = "found_issues"
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERRORED = "errored"

#: Reason text for a tier that is specified but not built in this pass. Named
#: so the UI's "what was NOT checked" enumeration says something actionable
#: instead of "unavailable ()".
REASON_TIER_NOT_BUILT = (
    "not built yet: tiers 0-2 run through the write seam db/apply.py, which "
    "does not exist yet -- nothing about this DDL was verified by this tier."
)

#: `plpgsql_check_state == "installable"`. Deliberately NOT `install_gate`'s
#: text (which is about whether to offer the install BUTTON); this one is
#: about why the check did not run.
REASON_NOT_INSTALLED = (
    "plpgsql_check is available on this server but is not installed in the "
    "sandbox database -- install it from Sandbox Setup; until then this "
    "routine has NOT been linted."
)

#: `plpgsql_check_state == "unknown"` -- a failed probe. Never collapsed into
#: "absent" (see `SandboxCapabilities.plpgsql_check_state`).
REASON_UNKNOWN_CAPABILITY = (
    "could not determine whether plpgsql_check is installed (the sandbox "
    "probe failed) -- this routine has NOT been linted."
)

#: The object is not in the sandbox at all. The overwhelmingly common cause is
#: that it failed to compile when applied, which is precisely the case that
#: must not read as "clean".
REASON_OBJECT_ABSENT = (
    "the object was not found in the sandbox -- it was never applied, or it "
    "failed to compile there. Apply it to the sandbox first; nothing was "
    "linted."
)

REASON_RELATION_ABSENT = (
    "the table this trigger fires on was not found in the sandbox, and "
    "plpgsql_check requires it (relid) to check a trigger function -- nothing "
    "was linted."
)

REASON_TRIGGER_FUNCTION_UNKNOWN = (
    "the function this trigger calls is unknown, and tier 3 checks functions, "
    "not CREATE TRIGGER statements -- nothing was linted."
)

#: §18.5 D3: "Known blind spots ... must be stated in the UI's 'what was
#: checked' text". Emitted as caveats on every report that actually ran, so a
#: clean result is never mistaken for a total one.
BLIND_SPOT_CAVEATS = (
    "plpgsql_check does not analyse dynamic EXECUTE statements.",
    "plpgsql_check does not analyse a refcursor fetched into a record.",
    "plpgsql_check does not analyse temp tables created at runtime.",
)

#: Emitted when at least one finding's `prosrc` line could not be mapped onto a
#: buffer line. Rendering it without a line is the honest degradation (§18.5
#: D3: "never guess"); saying so is the other half of being honest about it.
CAVEAT_UNMAPPED_LINES = (
    "one or more findings are shown without a line number: the body's opening "
    "dollar-quote could not be located in this buffer, and a guessed line "
    "would point at the wrong statement."
)


@dataclass(frozen=True)
class TierOutcome:
    """One ladder tier's result (§18.5 D3), read duck-typed by
    `ui/ddl_object_editor.py::tier_outcomes`/`_status`/`_reason`.

    `status` is one of the four `STATUS_*` constants. `reason` is the sentence
    the Audit panel prints after the status — mandatory for every status
    except `passed`, because "unavailable ()" tells the user nothing about
    what went unchecked.
    """

    status: str
    reason: str = ""
    detail: str = ""

    @property
    def verified(self) -> bool:
        """True only for a tier that actually ran. `unavailable`/`errored`
        verified nothing and must never be collapsed into an OK state."""
        return self.status in (STATUS_PASSED, STATUS_FOUND_ISSUES)


#: The single shared "tiers 0-2 are not built" outcome (see the module
#: docstring) -- one object, so the reason text lives in one place.
TIER_NOT_BUILT = TierOutcome(status=STATUS_UNAVAILABLE, reason=REASON_TIER_NOT_BUILT)


@dataclass(frozen=True)
class CheckFinding:
    """One `plpgsql_check_function_tb` row (§18.5 D3's findings type).

    **Mirrors and extends** `validation/tier2.py::ValidationIssue`'s
    `{severity, message, line}` — the same pattern-extension precedent §18.4
    set with `xsd_verify.Issue`. `ValidationIssue` itself is deliberately NOT
    widened: its three fields are asserted by existing tests and it belongs to
    `.pgtp` structural validation, a different domain.

    **`lineno` and `line` are both the BUFFER line, and `source_lineno` is the
    raw one.** This is not redundancy, it is a trap being closed:
    `ui/ddl_object_editor.py::_result_lines` renders
    `getattr(finding, "lineno", None) or getattr(finding, "line", None)` —
    `lineno` *wins*. `plpgsql_check` counts lines from `prosrc` (the
    dollar-quoted body) while the tab's buffer is `pg_get_functiondef` output
    (header + body), so exposing the raw number under the name the panel
    prefers would silently point every finding at the wrong statement. The raw
    value stays available as `source_lineno` for diagnostics.

    A finding whose line could not be mapped carries `line is None` and is
    rendered with no line at all — never a guess (§18.5 D3).
    """

    #: "error" | "warning" | "notice" -- `ValidationIssue`'s vocabulary.
    severity: str
    message: str
    #: The buffer line, or None when it could not be mapped honestly.
    line: int | None = None
    #: plpgsql_check's raw level string ("error", "warning extra",
    #: "warning performance", "warning security", "compatibility", ...), kept
    #: verbatim per §18.5 D3.
    level: str = ""
    sqlstate: str = ""
    statement: str = ""
    detail: str = ""
    hint: str = ""
    context: str = ""
    query: str = ""
    #: Character offset within the statement, as reported. Not turned into a
    #: line here: it indexes the statement plpgsql_check echoes back, not the
    #: buffer (tier 2's `position`, which does index the buffer, is a
    #: different number owned by `db/apply.py`).
    position: int | None = None
    #: The raw, `prosrc`-relative line number. See the class docstring.
    source_lineno: int | None = None
    #: `schema.name(argtypes)` of the object checked -- so a finding stays
    #: attributable after being merged into one Audit panel with others.
    identity: str = ""

    @property
    def lineno(self) -> int | None:
        """Alias of `line`, for the Audit renderer that prefers this name.
        Deliberately NOT the raw `prosrc` line -- see the class docstring."""
        return self.line


@dataclass(frozen=True)
class CheckReport:
    """§18.5 D3's `CheckReport{tier0..tier3, findings, caveats}`.

    Consumed duck-typed by `ui/ddl_object_editor.py` (`tier_outcomes`,
    `report_blockers`, `report_unverified`, `_result_lines`) and recorded on
    the tab via `record_check_report`, where it gates Apply-to-Target's
    precondition 2. Tiers 0-2 default to `TIER_NOT_BUILT` rather than `None`
    so the panel enumerates them as unverified instead of omitting them — an
    omitted tier reads as a complete report.
    """

    tier3: TierOutcome
    tier0: TierOutcome = TIER_NOT_BUILT
    tier1: TierOutcome = TIER_NOT_BUILT
    tier2: TierOutcome = TIER_NOT_BUILT
    findings: tuple[CheckFinding, ...] = ()
    caveats: tuple[str, ...] = ()

    @property
    def ran(self) -> bool:
        """Whether tier 3 actually executed. `not ran` means "could not
        check" -- never "clean"."""
        return self.tier3.verified


class MalformedCheckOutputError(RuntimeError):
    """`plpgsql_check_function_tb` returned rows we could not read as its
    documented 11 columns. Raised by `parse_findings` and turned into an
    `errored` tier by the driver -- never swallowed into an empty (i.e.
    apparently clean) finding list."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(
            f"plpgsql_check returned output this build cannot read ({detail}); "
            "reporting it as unchecked rather than as clean"
        )


# ---------------------------------------------------------------------------
# What to check
# ---------------------------------------------------------------------------

#: Argument/return type names are not identifiers -- `character varying`,
#: `integer[]`, `pr.money_t` and `numeric(10,2)` are all legal -- so they get
#: their own conservative allowlist rather than `quote_ident`. Anything else is
#: refused (`UnsafeIdentifierError`), never interpolated.
_SAFE_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_ .,()\[\]]*$")


def _validate_type(name: str) -> str:
    if not _SAFE_TYPE_RE.match(name.strip()):
        raise UnsafeIdentifierError(name)
    return name.strip()


def _sql_literal(text: str) -> str:
    """A single-quoted SQL string literal with embedded quotes doubled --
    used only for VALUES (the `regprocedure`/`regclass` lookup strings);
    identifiers inside them still go through `quote_ident`."""
    return "'" + text.replace("'", "''") + "'"


@dataclass(frozen=True)
class CheckRequest:
    """What to check, and in which buffer its lines are counted.

    Mirrors `ui/ddl_object_editor.py::DdlObjectRef`'s fields without importing
    it — that type lives in `ui/` and this module is Qt-free (§5). Build one
    from a ref with `from_ref`.

    **A trigger is the awkward case and is modelled explicitly.** The tab holds
    a `CREATE TRIGGER` statement, but tier 3 checks *functions*: so a trigger
    request names the referenced function (`function_schema`/`function_name`)
    AND the relation it fires on (`schema`/`table`), because
    `plpgsql_check_function_tb` errors with "missing trigger relation" if
    `relid` is omitted for a trigger function.
    """

    kind: str  # "function" | "procedure" | "trigger"
    schema: str
    name: str
    arg_types: tuple[str, ...] = ()
    #: Triggers only -- the table the trigger fires on, in `schema`.
    table: str | None = None
    #: Triggers only -- the function the trigger calls (what tier 3 checks).
    function_schema: str | None = None
    function_name: str | None = None
    #: The tab's text, used ONLY to map `prosrc` line numbers onto buffer
    #: lines. Empty means findings are reported with no line rather than a
    #: wrong one.
    buffer_text: str = ""
    #: Transition-table names, when the trigger declares them
    #: (`tgoldtable`/`tgnewtable`); passed through to plpgsql_check.
    oldtable: str | None = None
    newtable: str | None = None

    @classmethod
    def from_ref(
        cls,
        ref: Any,
        buffer_text: str = "",
        *,
        function_schema: str | None = None,
        function_name: str | None = None,
        oldtable: str | None = None,
        newtable: str | None = None,
    ) -> "CheckRequest":
        """Build a request from a duck-typed `DdlObjectRef`.

        For a trigger ref the caller must supply the referenced function
        (`function_schema`/`function_name`); a ref alone does not carry it, and
        guessing "the function is named like the trigger" is exactly the kind
        of 80%-right assumption §18.5 warns about for trigger tabs.
        """
        return cls(
            kind=str(getattr(ref, "kind", "function")),
            schema=str(getattr(ref, "schema", "")),
            name=str(getattr(ref, "name", "")),
            arg_types=tuple(getattr(ref, "arg_types", ()) or ()),
            table=getattr(ref, "table", None),
            function_schema=function_schema,
            function_name=function_name,
            buffer_text=buffer_text,
            oldtable=oldtable,
            newtable=newtable,
        )

    @property
    def is_trigger(self) -> bool:
        return self.kind == "trigger"

    @property
    def checked_schema(self) -> str | None:
        """The schema of the function tier 3 actually checks."""
        if self.is_trigger:
            return self.function_schema
        return self.schema

    @property
    def checked_name(self) -> str | None:
        """The name of the function tier 3 actually checks."""
        if self.is_trigger:
            return self.function_name
        return self.name

    @property
    def checked_arg_types(self) -> tuple[str, ...]:
        """A trigger function takes no declared arguments -- its signature is
        always `()`, whatever the trigger's own ref carried."""
        return () if self.is_trigger else self.arg_types

    @property
    def identity(self) -> str:
        """`schema.name(argtypes)` of the function being checked, for
        attribution on each finding."""
        schema, name = self.checked_schema, self.checked_name
        if not schema or not name:
            return ""
        return f"{schema}.{name}({', '.join(self.checked_arg_types)})"

    @property
    def regprocedure_text(self) -> str | None:
        """The `to_regprocedure` lookup string, e.g. `"pr"."f"(integer)`.

        **Why a qualified signature and not an oid:** the caller has a ref, not
        an oid, and asking the catalog for the oid is the lookup we are doing
        anyway. `to_regprocedure` is used rather than a bare `::regprocedure`
        cast because the cast RAISES for a function that does not exist, while
        `to_regprocedure` returns NULL — and "the routine is not in the
        sandbox" is a first-class outcome here (`REASON_OBJECT_ABSENT`), not an
        error to be re-parsed out of an exception message.
        """
        schema, name = self.checked_schema, self.checked_name
        if not schema or not name:
            return None
        args = ", ".join(_validate_type(arg) for arg in self.checked_arg_types)
        return f"{quote_ident(schema)}.{quote_ident(name)}({args})"

    @property
    def regclass_text(self) -> str | None:
        """The `to_regclass` lookup string for a trigger's relation, or None
        when this request needs no relation."""
        if not self.is_trigger or not self.table:
            return None
        return f"{quote_ident(self.schema)}.{quote_ident(self.table)}"


# ---------------------------------------------------------------------------
# Line-number honesty (§18.5 D3)
# ---------------------------------------------------------------------------

#: `$$`, `$function$`, `$body$`, ... -- the dollar-quote opener that begins a
#: routine body in `pg_get_functiondef` output.
_DOLLAR_TAG_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def _strip_line_comment(line: str) -> str:
    """Drop a trailing `-- ...` comment so a `$$` written inside one is not
    mistaken for the body opener. Deliberately naive (it does not track string
    literals): a false negative degrades to `None` and a line-less finding,
    which is the safe direction."""
    index = line.find("--")
    return line if index < 0 else line[:index]


def body_line_offset(buffer_text: str) -> int | None:
    """The 1-based line number `L` of the dollar-quote tag that opens the
    routine body, or None when it cannot be located (§18.5 D3).

    None is a real answer, not a failure to try: without `L` no line number
    can be produced honestly, and the finding is rendered with none at all.
    """
    if not buffer_text:
        return None
    for index, line in enumerate(buffer_text.splitlines(), start=1):
        if _DOLLAR_TAG_RE.search(_strip_line_comment(line)):
            return index
    return None


def map_lineno(buffer_text: str, lineno: int | None) -> int | None:
    """Map a `prosrc`-relative `lineno` onto a buffer line: `L + lineno - 1`.

    `prosrc` begins with the newline terminating the `AS $tag$` line, so
    `prosrc` line 1 **is** line `L`. Returns None — never a guess — when the
    opener cannot be located, `lineno` is falsy, or the result falls outside
    the buffer (§18.5 D3).
    """
    if not lineno or lineno < 1:
        return None
    offset = body_line_offset(buffer_text)
    if offset is None:
        return None
    mapped = offset + lineno - 1
    if mapped > len(buffer_text.splitlines()):
        return None
    return mapped


# ---------------------------------------------------------------------------
# The call shape (§18.5 D3's "API gotchas" table -- all call-shape
# requirements, not trivia)
# ---------------------------------------------------------------------------

#: The 11 columns `plpgsql_check_function_tb` returns, in its own order.
#: `"position"` MUST stay double-quoted -- it is a reserved word.
CHECK_COLUMNS = (
    "functionid",
    "lineno",
    "statement",
    "sqlstate",
    "message",
    "detail",
    "hint",
    "level",
    '"position"',
    "query",
    "context",
)

#: `_tb`, not the plain `plpgsql_check_function`: the `format` argument
#: (text/json/xml) exists only on the plain variant, which hands back a
#: formatted blob we would have to re-parse. `_tb` returns the same analysis as
#: rows, and rows are what a structured `CheckFinding` wants.
_CHECK_FUNCTION = "plpgsql_check_function_tb"


def build_resolve_sql(request: CheckRequest) -> str:
    """One round trip resolving both oids we may need: the function's, and
    (for a trigger) its relation's. `to_reg*` yields NULL rather than raising
    for a missing object, which is what makes "not in the sandbox" reportable
    as an outcome instead of an exception."""
    proc = request.regprocedure_text
    if proc is None:
        raise ValueError("CheckRequest names no function to check")
    relation = request.regclass_text
    relation_expr = (
        f"to_regclass({_sql_literal(relation)})::oid" if relation is not None else "NULL::oid"
    )
    return (
        f"SELECT to_regprocedure({_sql_literal(proc)})::oid AS funcoid, "
        f"{relation_expr} AS relid"
    )


def build_check_sql(request: CheckRequest, funcoid: int, relid: int | None = None) -> str:
    """The `plpgsql_check_function_tb` SELECT for one already-resolved oid.

    **Named notation throughout, never positional** — the shipped signature's
    positional order is `other_warnings, performance_warnings, extra_warnings`,
    which is *not* the README's order, so position is a silent-wrong-argument
    trap.

    - `fatal_errors => false`, because the default (true) stops at the first
      problem and a GUI that shows exactly one finding per routine is useless.
    - `all_warnings => true`, because warnings are off by default and the
      warning classes are most of the value.
    - `relid => <table oid>` for a trigger function; omitting it errors with
      *"missing trigger relation"*.
    """
    arguments = [f"funcoid => {int(funcoid)}"]
    if relid is not None:
        arguments.append(f"relid => {int(relid)}")
        if request.oldtable:
            arguments.append(f"oldtable => {_sql_literal(request.oldtable)}")
        if request.newtable:
            arguments.append(f"newtable => {_sql_literal(request.newtable)}")
    arguments.append("fatal_errors => false")
    arguments.append("all_warnings => true")
    return (
        f"SELECT {', '.join(CHECK_COLUMNS)} FROM {_CHECK_FUNCTION}({', '.join(arguments)})"
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def severity_for_level(level: str) -> str:
    """Map plpgsql_check's raw `level` onto `ValidationIssue`'s three-value
    severity vocabulary. The raw string is kept on the finding regardless
    (§18.5 D3) -- this is for the Audit panel's `SEVERITY` token only.

    An unrecognised level maps to `"warning"`, never to `"notice"`: guessing
    downwards would quietly demote something the extension thought worth
    saying.
    """
    normalized = (level or "").strip().lower()
    if normalized.startswith("error"):
        return "error"
    if normalized.startswith("warning") or normalized == "compatibility":
        return "warning"
    if normalized.startswith("notice") or normalized.startswith("info"):
        return "notice"
    return "warning"


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str:
    return "" if value is None else str(value)


def parse_findings(rows: Sequence[Any], request: CheckRequest) -> list[CheckFinding]:
    """Turn `plpgsql_check_function_tb` rows into `CheckFinding`s.

    Raises `MalformedCheckOutputError` for a row that is not the documented
    11 columns. Dropping such a row would shrink the finding list, and a
    shorter finding list is indistinguishable from a cleaner routine — the one
    lie this module exists to prevent.
    """
    findings: list[CheckFinding] = []
    for index, row in enumerate(rows):
        try:
            values = tuple(row)
        except TypeError as exc:  # not even iterable
            raise MalformedCheckOutputError(f"row {index} is not a row: {row!r}") from exc
        if len(values) != len(CHECK_COLUMNS):
            raise MalformedCheckOutputError(
                f"row {index} has {len(values)} column(s), expected {len(CHECK_COLUMNS)}"
            )
        (
            _functionid,
            raw_lineno,
            statement,
            sqlstate,
            message,
            detail,
            hint,
            level,
            position,
            query,
            context,
        ) = values
        source_lineno = _as_int(raw_lineno)
        findings.append(
            CheckFinding(
                severity=severity_for_level(_as_text(level)),
                message=_as_text(message),
                line=map_lineno(request.buffer_text, source_lineno),
                level=_as_text(level),
                sqlstate=_as_text(sqlstate),
                statement=_as_text(statement),
                detail=_as_text(detail),
                hint=_as_text(hint),
                context=_as_text(context),
                query=_as_text(query),
                position=_as_int(position),
                source_lineno=source_lineno,
                identity=request.identity,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# The capability gate -- never a silent no-op
# ---------------------------------------------------------------------------

def capability_outcome(caps: SandboxCapabilities) -> TierOutcome | None:
    """None when tier 3 can run; otherwise the `unavailable` outcome
    explaining why it cannot, one distinct reason per
    `SandboxCapabilities.plpgsql_check_state` value.

    All three non-runnable states are `unavailable` rather than `errored`
    (nothing went wrong — the check simply could not happen), but they are
    **not interchangeable**: "the DBA never installed the library",
    "it is installable, click the button", and "we could not even ask" call
    for three different user actions. The `absent` text is `install_gate`'s
    own, so the platform-install wording lives in exactly one place.
    """
    state = caps.plpgsql_check_state
    if state == "installed":
        return None
    if state == "installable":
        return TierOutcome(status=STATUS_UNAVAILABLE, reason=REASON_NOT_INSTALLED)
    if state == "unknown":
        return TierOutcome(
            status=STATUS_UNAVAILABLE,
            reason=REASON_UNKNOWN_CAPABILITY,
            detail=caps.probe_error or "",
        )
    _offered, reason = install_gate(caps)
    return TierOutcome(status=STATUS_UNAVAILABLE, reason=reason)


# ---------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------

def _unavailable_report(outcome: TierOutcome) -> CheckReport:
    """A report for a tier 3 that never ran: no findings, no blind-spot
    caveats (nothing was checked, so there is nothing to caveat), and an
    outcome that the panel renders as "could not check"."""
    return CheckReport(tier3=outcome)


def run_plpgsql_check(
    session: CheckSession,
    request: CheckRequest,
    caps: SandboxCapabilities,
    *,
    query: Query | None = None,
) -> CheckReport:
    """Run `plpgsql_check_function_tb` against the sandbox and return what it
    found (§18.5 D3 tier 3).

    Two read-only round trips: resolve the oid(s), then call the extension.
    Nothing is applied, written or altered — if the object is not already in
    the sandbox, this reports that fact rather than putting it there.

    `query` defaults to `session.executor.query`; every test injects it, so no
    test can open a connection.

    Never raises for a runtime problem. Every failure becomes a distinguishable
    outcome:

    | Situation | `tier3.status` |
    |---|---|
    | extension absent / installable / state unknown | `unavailable` (three distinct reasons) |
    | the trigger's function or relation is unknown | `unavailable` |
    | the object is not in the sandbox (e.g. it never compiled) | `unavailable` |
    | the executor raised | `errored` |
    | the extension returned unreadable rows | `errored` |
    | rows returned | `found_issues` |
    | no rows | `passed` |

    A `UnsafeIdentifierError` from a hostile identifier is deliberately NOT
    caught: it is a programming/allowlist failure, not a check result, and
    must not be laundered into "could not check".
    """
    unavailable = capability_outcome(caps)
    if unavailable is not None:
        return _unavailable_report(unavailable)

    if request.checked_schema is None or request.checked_name is None:
        return _unavailable_report(
            TierOutcome(status=STATUS_UNAVAILABLE, reason=REASON_TRIGGER_FUNCTION_UNKNOWN)
        )

    run_query: Query = query if query is not None else session.executor.query

    try:
        resolved = run_query(session.params, build_resolve_sql(request))
    except Exception as exc:  # noqa: BLE001 -- any executor failure is "errored", never "clean"
        return _unavailable_report(
            TierOutcome(
                status=STATUS_ERRORED,
                reason=f"resolving the object in the sandbox failed: {exc}",
            )
        )

    funcoid, relid = _read_resolution(resolved)
    if funcoid is None:
        return _unavailable_report(
            TierOutcome(status=STATUS_UNAVAILABLE, reason=REASON_OBJECT_ABSENT)
        )
    if request.regclass_text is not None and relid is None:
        return _unavailable_report(
            TierOutcome(status=STATUS_UNAVAILABLE, reason=REASON_RELATION_ABSENT)
        )

    try:
        rows = run_query(session.params, build_check_sql(request, funcoid, relid))
    except Exception as exc:  # noqa: BLE001 -- see above
        return _unavailable_report(
            TierOutcome(
                status=STATUS_ERRORED,
                reason=f"plpgsql_check could not be run: {exc}",
            )
        )

    try:
        findings = parse_findings(list(rows or []), request)
    except MalformedCheckOutputError as exc:
        return _unavailable_report(
            TierOutcome(status=STATUS_ERRORED, reason=str(exc), detail=exc.detail)
        )

    caveats = list(BLIND_SPOT_CAVEATS)
    if any(f.line is None and f.source_lineno for f in findings):
        caveats.append(CAVEAT_UNMAPPED_LINES)

    if findings:
        outcome = TierOutcome(
            status=STATUS_FOUND_ISSUES,
            reason=f"plpgsql_check reported {len(findings)} finding(s)",
        )
    else:
        outcome = TierOutcome(
            status=STATUS_PASSED,
            reason=f"plpgsql_check found nothing in {request.identity}",
        )
    return CheckReport(tier3=outcome, findings=tuple(findings), caveats=tuple(caveats))


def _read_resolution(rows: Any) -> tuple[int | None, int | None]:
    """`(funcoid, relid)` from `build_resolve_sql`'s single row. An empty or
    short result yields `(None, None)` -- read as "not in the sandbox", which
    is the honest reading and never as "clean"."""
    try:
        first = list(rows or [])[0]
    except (IndexError, TypeError):
        return (None, None)
    values = list(first) + [None, None]
    return (_as_int(values[0]), _as_int(values[1]))


def recheck(
    session: CheckSession,
    request: CheckRequest,
    caps: SandboxCapabilities,
    *,
    query: Query | None = None,
) -> CheckReport:
    """§18.5 D3's **"Check"** gesture: run the ladder against the sandbox **as
    it currently stands**, applying nothing.

    Today that is exactly tier 3, so this is a thin, named alias of
    `run_plpgsql_check` — named because the gesture is user-visible and the
    panel's Check button wants an entry point to bind to, not because it adds
    behaviour. D3's other two entry points, `apply_and_check` (commits) and
    `probe_check` (rolled back), both need `db/apply.py`'s write seam and are
    therefore not built here; do not "finish" them by making this one write.
    """
    return run_plpgsql_check(session, request, caps, query=query)


# ---------------------------------------------------------------------------
# Working-set sweep -- a loop over `recheck`, deliberately not a mechanism
# ---------------------------------------------------------------------------

#: The key of one working-set row: the `(kind, schema_name, object_name,
#: table_name)` 4-tuple that is the `applied` bookkeeping table's PRIMARY KEY
#: and *already* what `SandboxSession.apply` calls a `ref`. Reused verbatim
#: rather than invented here so the sweep's dict keys join up with the rows the
#: deployment generator reads -- and so nothing has to hash an `AppliedObject`
#: whose `applied_at`/`text_sha1` change on every re-apply.
WorkingSetRef = tuple[str, str, str, str]

#: Reason for a row whose `recheck` raised instead of returning a report. See
#: `check_working_set` for why the sweep catches this rather than propagating.
REASON_SWEEP_ROW_ERRORED = (
    "checking this working-set row raised instead of reporting: {error} -- the "
    "sweep continued with the remaining rows; this one was NOT linted."
)


def applied_ref(row: Any) -> WorkingSetRef:
    """The `WorkingSetRef` of one duck-typed `db/sandbox.py::AppliedObject`."""
    return (
        str(getattr(row, "kind", "")),
        str(getattr(row, "schema_name", "")),
        str(getattr(row, "object_name", "")),
        str(getattr(row, "table_name", "")),
    )


def request_from_applied(row: Any) -> CheckRequest:
    """Adapt one `applied` bookkeeping row into a `CheckRequest`.

    **This is an adapter, not a second request builder.** The bookkeeping table
    records `(kind, schema_name, object_name, table_name, applied_at,
    text_sha1)` and nothing else — notably **no argument types, no buffer text
    and, for a trigger, no referenced function**. So the honest consequences,
    all of which land on paths this module already reports rather than on new
    ones:

    - an overloaded routine resolves as `schema.name()` and, when no zero-arg
      overload exists, comes back `REASON_OBJECT_ABSENT` — unavailable, never
      clean;
    - a trigger row has no `function_schema`/`function_name`, so `recheck`
      returns `REASON_TRIGGER_FUNCTION_UNKNOWN` — again unavailable;
    - `buffer_text` is empty, so every finding's `line` is `None` and is
      rendered without a line (§18.5 D3's "never guess").

    A caller that *has* the tabs (which do carry arg types and buffer text) is
    expected to pass its own `request_for=` to `check_working_set` instead of
    accepting these degradations.
    """
    kind, schema_name, object_name, table_name = applied_ref(row)
    return CheckRequest(
        kind=kind,
        schema=schema_name,
        name=object_name,
        table=table_name or None,
    )


def check_working_set(
    session: Any,
    caps: SandboxCapabilities,
    *,
    recheck: Callable[..., CheckReport] = recheck,
    request_for: Callable[[Any], CheckRequest] = request_from_applied,
    query: Query | None = None,
) -> dict[WorkingSetRef, CheckReport]:
    """Check every object in the sandbox's working set: `{ref: CheckReport}`.

    §18.5 D3a specifies this as a **pure loop, not a second mechanism** — it
    iterates `SandboxSession.applied()` and calls the *same* `recheck` entry
    point once per row. It composes no SQL, knows nothing about tiers or
    findings, and is not a second reporting path: every value in the returned
    dict is whatever `recheck` produced, unmodified. Anything a sweep would
    want to "improve" belongs in `recheck`, where the single-object gesture
    gets it too.

    `recheck` is injected (keyword-only, defaulting to this module's real
    gesture) purely so a test can assert the seam is called once per row
    without a database; `query` is passed straight through to it, per this
    module's "no entry point opens a connection" rule.

    **It exists for Generate Deployment SQL's future "is everything in the
    desired state green?" question and deliberately gets no menu entry, no
    button and no other UI in this pass** — a control for a consumer that does
    not exist yet is a dead control (§18.5 carve-out 2). Do not wire it.

    **A row that fails does not abort the sweep, and does not vanish from the
    result either.** `recheck` is documented never to raise for a runtime
    problem, but it deliberately lets a `UnsafeIdentifierError` through, and an
    injected `recheck` is not bound by that contract at all. Dropping such a
    row would shrink the result, and a shorter result is indistinguishable from
    a smaller working set — the same lie `parse_findings` refuses to tell about
    findings. So the exception becomes that row's own `errored` `CheckReport`
    (`verified` False, `ran` False): the caller sees one entry per applied row,
    and the failed one reads as "could not check", never as green.
    """
    reports: dict[WorkingSetRef, CheckReport] = {}
    for row in session.applied():
        ref = applied_ref(row)
        try:
            reports[ref] = recheck(session, request_for(row), caps, query=query)
        except Exception as exc:  # noqa: BLE001 -- per-row containment; see docstring
            reports[ref] = _unavailable_report(
                TierOutcome(
                    status=STATUS_ERRORED,
                    reason=REASON_SWEEP_ROW_ERRORED.format(error=exc),
                )
            )
    return reports


#: Kept for callers that want the caveat list without running anything (e.g.
#: a "what does Check actually cover?" affordance). A tuple, not a list, so a
#: caller cannot mutate the shared text.
def blind_spots() -> tuple[str, ...]:
    """plpgsql_check's known blind spots, verbatim (§18.5 D3). Stated in the
    UI's "what was checked" text so a clean report is never read as a total
    one."""
    return BLIND_SPOT_CAVEATS


__all__ = [
    "BLIND_SPOT_CAVEATS",
    "CAVEAT_UNMAPPED_LINES",
    "CHECK_COLUMNS",
    "CheckFinding",
    "CheckReport",
    "CheckRequest",
    "CheckSession",
    "MalformedCheckOutputError",
    "Query",
    "REASON_NOT_INSTALLED",
    "REASON_OBJECT_ABSENT",
    "REASON_RELATION_ABSENT",
    "REASON_SWEEP_ROW_ERRORED",
    "REASON_TIER_NOT_BUILT",
    "REASON_TRIGGER_FUNCTION_UNKNOWN",
    "REASON_UNKNOWN_CAPABILITY",
    "STATUS_ERRORED",
    "STATUS_FOUND_ISSUES",
    "STATUS_PASSED",
    "STATUS_UNAVAILABLE",
    "TIER_NOT_BUILT",
    "TierOutcome",
    "WorkingSetRef",
    "applied_ref",
    "blind_spots",
    "body_line_offset",
    "build_check_sql",
    "build_resolve_sql",
    "capability_outcome",
    "check_working_set",
    "map_lineno",
    "parse_findings",
    "recheck",
    "request_from_applied",
    "run_plpgsql_check",
    "severity_for_level",
]
