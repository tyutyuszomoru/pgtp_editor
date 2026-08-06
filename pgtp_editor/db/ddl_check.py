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

**All four tiers now run, and the ladder is ONE call.** Tiers 0-2 hang off the
write seam `db/apply.py::apply_ddl`, and they cannot be separate round trips:
`SET plpgsql.extra_*` is session-scoped, and the `plpgsql_check_function_tb`
SELECT must see the object the DDL just created — in a `probe_check` that object
exists only inside the uncommitted transaction. So `apply_and_check`/
`probe_check` **compose one statement list**, hand it to `apply_ddl`, and read
the tiers back off it:

| Tier | Where its answer comes from |
|---|---|
| 0 | collapses into tier 2 — PostgreSQL's own parser is the syntax checker, so no `pglast`/GPL grammar dependency is taken (§18.5 D3's licensing note) |
| 1 | `ApplyOutcome.notices` — the `SET plpgsql.extra_warnings = 'all'` lint returns **no rows**, so its findings exist only on the notice channel; **`notices_captured is False` means `unavailable`, never `passed`** |
| 2 | whether the DDL statement itself ran, by `ApplyOutcome.statement_index` |
| 3 | the check SELECT's rows, read off `ApplyOutcome.result_at(check_index)` |

**`statement_index` is the whole reason this is safe.** Run as one call, a naive
"it raised" report would show a failure *in the check call* as *"your DDL is
broken"*. Every tier here is attributed by the index this module itself chose
for that tier's statement, so each failure lands on the tier that actually
produced it and no other tier is reported as verified because of it.

**Two gestures write, one does not, and that difference is user-visible.**
`apply_and_check` commits (the DDL *and* the `applied` bookkeeping row, in the
same transaction); `probe_check` runs the identical list with
`apply_ddl(..., commit=False)` — the **one** narrow place rollback survives
(§18.5 D2: a convenience for *"what would this do?"*, not a safety mechanism),
which is why it is a `commit` boolean rather than a second code path that could
validate something other than what Apply will run. `recheck` writes nothing at
all: it reads the sandbox as it currently stands.

Qt-free and, like `db/introspect.py` and `db/sandbox.py`, opens no connection
except through an injectable seam: the read entry points take `query=`
(defaulting to the session's executor) and the writing ones take `applier=`
(defaulting to `apply_ddl`), so the whole test suite runs with psycopg absent
and never touches a real database.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .apply import ApplyOutcome, apply_ddl
from .config import ConnectionParams
from .sandbox import (
    SandboxCapabilities,
    UnsafeIdentifierError,
    applied_upsert_sql,
    install_gate,
    quote_ident,
    text_sha1,
)

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

#: Reason text for a tier that no gesture on this path can produce. `recheck`
#: applies nothing, so tiers 0-2 -- which are *about* applying -- have no answer
#: for it beyond the bookkeeping table (see `recheck`). Named so the UI's "what
#: was NOT checked" enumeration says something actionable instead of
#: "unavailable ()".
REASON_TIER_NOT_BUILT = (
    "nothing was applied in this run, so this tier had nothing to compile: the "
    "compile check runs on Apply to Sandbox and on Check-without-applying."
)

#: Tier 1 exists only on the notice channel (§18.5 D3). A runner that cannot
#: capture notices yields an empty finding list that is indistinguishable from a
#: clean routine -- so it must report `unavailable`, never `passed`.
REASON_NO_NOTICE_CHANNEL = (
    "the extra-warnings lint reports through PostgreSQL's asynchronous NOTICE "
    "channel and this run had no notice capture, so nothing it said was "
    "received -- this routine has NOT been lint-checked."
)

#: The transaction stopped at an earlier statement, so this tier's statement was
#: never reached. Formatted with the failing statement's index and message.
REASON_NOT_REACHED = (
    "the transaction stopped at statement {index} before this tier's statement "
    "ran ({message}) -- nothing was verified by this tier."
)

#: Tier 0's reason whenever tier 2 ran: D3's *"tier 0 collapses into tier 2 when
#: a sandbox is available"*. Stated rather than left blank so the always-printed
#: tier-0 line says which parser actually judged the syntax.
REASON_TIER0_COLLAPSED = (
    "syntax was checked by PostgreSQL's own parser as part of tier 2 (the "
    "offline grammar option, pglast, is GPL-only and is deliberately not a "
    "dependency)."
)

#: Tier 0 when tier 2 could not run: there is no separate offline checker to
#: fall back to, which is the honest statement of the same design decision.
REASON_TIER0_NO_SANDBOX = (
    "there is no offline syntax checker: tier 0 is PostgreSQL's own parser via "
    "tier 2, and tier 2 did not run."
)

#: Tier 2 has no DDL to compile -- an empty buffer. Refused rather than reported
#: as a clean compile of nothing.
REASON_NO_DDL_TEXT = (
    "there is no DDL text to apply, so nothing was compiled or checked."
)

#: The whole ladder was rolled back. Emitted as a caveat, because a user who
#: pressed **Apply** must never be left believing it landed.
CAVEAT_ROLLED_BACK = (
    "NOTHING WAS APPLIED: the transaction was rolled back, so the sandbox is "
    "unchanged by this run."
)

#: `probe_check`'s standing caveat -- the probe is explicitly rolled back, which
#: is not a failure but must still be said out loud.
CAVEAT_PROBE_ONLY = (
    "this was a check WITHOUT applying: the DDL was compiled inside a "
    "transaction that was then rolled back, so the sandbox still holds the "
    "previously applied version."
)

#: `recheck`'s stale-buffer warning (§18.5 D3): the sandbox holds a different
#: text than the caller's buffer, so the findings are about the OLD version.
CAVEAT_STALE_BUFFER = (
    "this buffer has changed since it was last applied to the sandbox: these "
    "findings describe the version applied at {applied_at}, not what you are "
    "looking at. Apply it again to check the current text."
)

#: `plpgsql_check_state == "installable"`, first sentence: why the check did not
#: run. Deliberately NOT `install_gate`'s text (which is about whether to offer
#: the install BUTTON).
REASON_NOT_INSTALLED_BASE = (
    "plpgsql_check is available on this server but is not installed in the "
    "sandbox database -- this routine has NOT been linted."
)

#: §18.5 D3a requires the `installable` case to *name the one-click install and
#: where it lives*, verbatim -- an "it is not installed" message the user cannot
#: act on is the same dead end as no message.
REASON_INSTALL_LOCATIONS = (
    "Install it from Database ▸ Sandbox Setup…, or the Project Status "
    "window's plpgsql_check node."
)

#: The full `installable` reason when the install really is one click away.
#: When it is not -- `install_gate` refusing because the connection is not a
#: superuser -- `not_installed_reason` substitutes `install_gate`'s own
#: sentence, which is never re-typed here (§18.5 D3a).
REASON_NOT_INSTALLED = f"{REASON_NOT_INSTALLED_BASE} {REASON_INSTALL_LOCATIONS}"

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

    #: "error" | "warning" | "notice" -- `ValidationIssue`'s two values plus
    #: `"notice"`, which the Audit renderer shows as `INFO` (§18.5 D3a maps
    #: `compatibility` there). `ValidationIssue` itself only ever emits
    #: "error"/"warning"; the third value is this type's extension, and adding
    #: it here rather than widening `ValidationIssue` is deliberate.
    severity: str
    #: The finding's message. An unrecognised raw `level` is appended in
    #: parentheses (§18.5 D3a) -- see `message_for_level`.
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
    #: Which ladder tier produced this finding (§18.5 D3a's "the source tier").
    #: Defaults to 3 because `plpgsql_check` was the only source until tiers 0-2
    #: were wired; tier 1's notice-derived findings and tier 2's compile failure
    #: set it explicitly. Kept on the finding rather than inferred from its shape
    #: so a report that mixes tiers can still say which check spoke.
    tier: int = 3

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
    #: Whether the ladder's transaction committed. **False for a `probe_check`
    #: (by design), for every failed apply, and for a `recheck` (which applies
    #: nothing)** -- stated as a fact rather than inferred, because "it compiled
    #: but was rolled back on purpose" and "it compiled and is now in the
    #: sandbox" are the two things a user most needs told apart (§18.5 D2's
    #: retraction of the always-rollback model).
    committed: bool = False

    @property
    def ran(self) -> bool:
        """Whether tier 3 actually executed. `not ran` means "could not
        check" -- never "clean"."""
        return self.tier3.verified

    @property
    def tiers(self) -> tuple[TierOutcome, ...]:
        """The four tiers in order -- `(tier0, tier1, tier2, tier3)`."""
        return (self.tier0, self.tier1, self.tier2, self.tier3)

    @property
    def green(self) -> bool:
        """Whether **every** tier ran and none of them found anything.

        The strict reading §18.5 D3's hard rule requires: an `unavailable` or
        `errored` tier makes the report not-green, so "green" can never mean
        "the tiers that happened to run were happy". Apply-to-Target's
        precondition 2 gates on exactly this, with its named override for what
        `report_unverified` enumerates."""
        return all(tier.status == STATUS_PASSED for tier in self.tiers)


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
    def working_set_ref(self) -> tuple[str, str, str, str]:
        """This object's `(kind, schema_name, object_name, table_name)` key --
        the `applied` bookkeeping table's PRIMARY KEY, and what
        `db/sandbox.py::applied_upsert_sql` and `applied_ref` both use. One
        spelling of the key, so `apply_and_check`'s row and a later sweep's
        lookup cannot miss each other."""
        return (self.kind, self.schema, self.name, self.table or "")

    @property
    def trigger_drop_target(self) -> tuple[str, str, str] | None:
        """`(trigger, schema, table)` for a trigger whose `CREATE` may need a
        `DROP TRIGGER IF EXISTS` in front of it, or None. See
        `needs_trigger_drop`."""
        if not self.is_trigger or not self.table or not self.name:
            return None
        return (self.name, self.schema, self.table)

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


def _check_call(
    request: CheckRequest, funcoid_expr: str, relid_expr: str | None
) -> str:
    """The `plpgsql_check_function_tb(...)` call itself, from SQL *expressions*
    for its oids -- shared by the pre-resolved (`build_check_sql`) and the
    in-transaction (`build_guarded_check_sql`) shapes so the call-shape rules
    below exist once.

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
    arguments = [f"funcoid => {funcoid_expr}"]
    if relid_expr is not None:
        arguments.append(f"relid => {relid_expr}")
        if request.oldtable:
            arguments.append(f"oldtable => {_sql_literal(request.oldtable)}")
        if request.newtable:
            arguments.append(f"newtable => {_sql_literal(request.newtable)}")
    arguments.append("fatal_errors => false")
    arguments.append("all_warnings => true")
    return f"{_CHECK_FUNCTION}({', '.join(arguments)})"


def build_check_sql(request: CheckRequest, funcoid: int, relid: int | None = None) -> str:
    """The `plpgsql_check_function_tb` SELECT for one **already-resolved** oid --
    `recheck`'s shape, where a preceding round trip established that the object
    exists (and reported `REASON_OBJECT_ABSENT` if it did not)."""
    return (
        f"SELECT {', '.join(CHECK_COLUMNS)} FROM "
        f"{_check_call(request, str(int(funcoid)), None if relid is None else str(int(relid)))}"
    )


def build_guarded_check_sql(request: CheckRequest) -> str:
    """The `plpgsql_check_function_tb` SELECT for the **one-transaction ladder**,
    where the oid cannot be resolved in advance: the object may not exist until
    the DDL statement two positions earlier in the same list has run.

    **The oid guard is structural, and it has to be.** `to_regprocedure` yields
    NULL rather than raising for a missing object, but handing a NULL `funcoid`
    to `plpgsql_check_function_tb` is not defined to be harmless — and if it
    raised, the *whole* transaction would abort, which for `apply_and_check`
    would throw away a DDL statement that applied perfectly well. So the oids are
    resolved in a subquery whose `WHERE` makes it return **zero rows** when
    either is absent; a `LATERAL` join over an empty left side never evaluates
    the function at all. The absent-object case then arrives as an empty result
    set instead of an aborted transaction, and is told apart from a genuinely
    clean run by the resolve statement's own row (which is why the ladder sends
    both).

    **Needs live-server confirmation** alongside the rest of §30's env-gated
    facts: that the LATERAL form binds `r.funcoid` as expected and that the
    empty-left-side case really does not invoke the SRF.
    """
    proc = request.regprocedure_text
    if proc is None:
        raise ValueError("CheckRequest names no function to check")
    relation = request.regclass_text
    columns = ", ".join(f"c.{column}" for column in CHECK_COLUMNS)
    guards = [f"to_regprocedure({_sql_literal(proc)}) IS NOT NULL"]
    selected = [f"to_regprocedure({_sql_literal(proc)})::oid AS funcoid"]
    relid_expr = None
    if relation is not None:
        guards.append(f"to_regclass({_sql_literal(relation)}) IS NOT NULL")
        selected.append(f"to_regclass({_sql_literal(relation)})::oid AS relid")
        relid_expr = "r.relid"
    return (
        f"SELECT {columns} FROM "
        f"(SELECT {', '.join(selected)} WHERE {' AND '.join(guards)}) r, "
        f"LATERAL {_check_call(request, 'r.funcoid', relid_expr)} c"
    )


# ---------------------------------------------------------------------------
# The statement list -- one transaction, one call, tiers attributed by index
# ---------------------------------------------------------------------------

#: Tier 1 (§18.5 D3). `'all'` turns on `shadowed_variables`,
#: `strict_multi_assignment` and `too_many_rows`, which report as asynchronous
#: `WARNING` notices while `CREATE FUNCTION` compiles the body.
#:
#: **`plpgsql.extra_errors` is deliberately NOT set.** D3 lists it in
#: parentheses but flags it as unpinned, and setting it to `'all'` would convert
#: every one of those lints into a hard `ERROR` — which would fail the DDL
#: statement and, in `apply_and_check`, refuse an apply because of a *warning*.
#: Tier 1's job is to report warnings, not to redefine what compiles. Revisit
#: only with the live-server confirmation D3 asks for.
TIER1_SET_SQL = "SET plpgsql.extra_warnings = 'all'"

#: `CREATE OR REPLACE TRIGGER` exists only on **PG 14+** (§18.5's plpgsql_check
#: integration specifics). Below it, re-applying a trigger needs an explicit
#: `DROP TRIGGER IF EXISTS` first or the `CREATE` fails with *"already
#: exists"* — which would be reported as tier 2 finding the user's DDL broken
#: when in fact the server is just old.
TRIGGER_REPLACE_MIN_MAJOR = 14


def needs_trigger_drop(request: CheckRequest, caps: SandboxCapabilities) -> bool:
    """Whether the statement list must be preceded by `DROP TRIGGER IF EXISTS`.

    §18.5's rule is *"`CREATE OR REPLACE TRIGGER` exists only on PG 14+: below
    that the statement list must be preceded by a `DROP TRIGGER IF EXISTS`,
    gated on `caps.server_version`"*. The version comes from
    `SandboxCapabilities.server_version` — `probe`'s decoded
    `current_setting('server_version_num')`, an actual server capability — never
    from a guess or from parsing the buffer.

    **An unknown version (an empty `server_version`, i.e. the probe failed)
    emits the DROP.** The two errors are not symmetric: omitting it on PG 13
    makes a legitimate re-apply fail and blames the user's DDL, while an extra
    `DROP TRIGGER IF EXISTS` on PG 14+ is a no-op inside the same transaction
    that immediately recreates the trigger. The recoverable direction wins.
    """
    if request.trigger_drop_target is None:
        return False
    version = caps.server_version
    if not version:
        return True
    return int(version[0]) < TRIGGER_REPLACE_MIN_MAJOR


def build_trigger_drop_sql(request: CheckRequest) -> str | None:
    """`DROP TRIGGER IF EXISTS <trigger> ON <schema>.<table>`, or None when this
    request is not a trigger with a known table. Every identifier goes through
    `quote_ident`'s strict allowlist (§18.5 D2) — an adversarial name is refused,
    never interpolated."""
    target = request.trigger_drop_target
    if target is None:
        return None
    trigger, schema, table = target
    return (
        f"DROP TRIGGER IF EXISTS {quote_ident(trigger)} ON "
        f"{quote_ident(schema)}.{quote_ident(table)}"
    )


@dataclass(frozen=True)
class LadderPlan:
    """The ladder's statement list **plus the index of each tier's statement**.

    The indices are the whole point: `db/apply.py::ApplyOutcome.statement_index`
    says which statement failed, and this record is what turns that number back
    into *which tier*. Without it a failure in the `plpgsql_check` SELECT would
    be reported as *"your DDL is broken"* — the exact misattribution the write
    seam exists to prevent (§18.5 D3a).

    An index is None when that statement is not in the list at all: no lint SET
    on a run that cannot capture notices, no bookkeeping row on a probe, no check
    SELECT when tier 3 is unavailable. `None` therefore reads as *"this tier was
    never going to run"*, which is a different fact from *"it ran and passed"*.
    """

    statements: tuple[str, ...] = ()
    lint_index: int | None = None
    trigger_drop_index: int | None = None
    ddl_index: int | None = None
    bookkeeping_index: int | None = None
    resolve_index: int | None = None
    check_index: int | None = None


def build_ladder(
    request: CheckRequest,
    caps: SandboxCapabilities,
    ddl_text: str,
    *,
    record_applied: bool,
) -> LadderPlan:
    """Compose the one statement list D3's ladder runs as a single transaction.

    Order is load-bearing, not stylistic:

    1. `SET plpgsql.extra_warnings` — must precede the DDL, since it changes how
       the DDL's body is compiled (tier 1);
    2. `DROP TRIGGER IF EXISTS` — only for a trigger on a server without
       `CREATE OR REPLACE TRIGGER` (see `needs_trigger_drop`);
    3. the DDL itself (tier 2, and tier 0 by collapse);
    4. the `applied` bookkeeping upsert — **only** when this is an apply, and in
       this same transaction so the row can never exist without the DDL or vice
       versa (§18.5 D2's *"one committing, atomic call"*);
    5. the oid resolve SELECT — so *"the object is not there"* is a reportable
       outcome rather than something inferred from an empty check result;
    6. the `plpgsql_check_function_tb` SELECT (tier 3) — after the object exists,
       in the same transaction, which is what makes catalog-based checking work
       on an uncommitted `probe_check`.

    Statements 5 and 6 are omitted entirely when `caps` say tier 3 cannot run:
    sending them would fail the transaction (and so the apply) over a missing
    extension, and D3 is explicit that losing tier 3 costs the semantic analysis,
    not the compile check.
    """
    statements: list[str] = []
    indices: dict[str, int | None] = {
        "lint_index": None,
        "trigger_drop_index": None,
        "ddl_index": None,
        "bookkeeping_index": None,
        "resolve_index": None,
        "check_index": None,
    }

    def add(key: str, sql: str) -> None:
        indices[key] = len(statements)
        statements.append(sql)

    add("lint_index", TIER1_SET_SQL)

    if needs_trigger_drop(request, caps):
        drop_sql = build_trigger_drop_sql(request)
        if drop_sql is not None:
            add("trigger_drop_index", drop_sql)

    if ddl_text.strip():
        add("ddl_index", ddl_text)
        if record_applied:
            add(
                "bookkeeping_index",
                applied_upsert_sql(request.working_set_ref, ddl_text),
            )

    if (
        capability_outcome(caps) is None
        and request.checked_schema
        and request.checked_name
    ):
        add("resolve_index", build_resolve_sql(request))
        add("check_index", build_guarded_check_sql(request))

    return LadderPlan(statements=tuple(statements), **indices)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

#: The exact `level` values §18.5 D3a's mapping table knows, normalized. A
#: level outside this set is mapped by `severity_for_level`'s prefix rules AND
#: has its raw string appended to the message by `parse_findings` -- see
#: `is_known_level`.
KNOWN_LEVELS = frozenset(
    {
        "error",
        "warning",
        "warning extra",
        "warning performance",
        "warning security",
        "compatibility",
    }
)


def is_known_level(level: str) -> bool:
    """Whether `level` is one of the six values §18.5 D3a's table names.

    **`warning <unknown-suffix>` is deliberately NOT known.** The prefix rule
    in `severity_for_level` still maps it to `"warning"`, so the *severity* is
    right — but the table lists exactly four warning variants, and a future
    `warning something-new` is a warning *class* this build has never heard of.
    D3a's rule for a level the table does not know is "`WARNING`, and the raw
    `level` is appended to the message in parentheses -- **never dropped, never
    silently mapped to `INFO`**". Getting the severity right by luck of the
    prefix is not the same as not swallowing the level: the Audit renderer shows
    `SEVERITY`, line and message, and nothing else, so the parenthetical is the
    only place a new class becomes visible at all. Treating it as known would
    make it exactly as invisible as `warning extra`, which is the silent
    swallowing the spec forbids.

    An empty/blank level is reported as known: there is no raw text to preserve,
    and appending a bare "()" to the message would be noise, not information.
    """
    normalized = (level or "").strip().lower()
    return not normalized or normalized in KNOWN_LEVELS


def severity_for_level(level: str) -> str:
    """Map plpgsql_check's raw `level` onto the lowercase severity vocabulary
    `CheckFinding` shares with `ValidationIssue` (`"error"`/`"warning"`, plus
    `"notice"` for the Audit `INFO` token). The raw string is kept on the
    finding regardless (§18.5 D3) -- this is for the Audit panel's `SEVERITY`
    token only, and it is §18.5 D3a's **single** home for the level->severity
    decision. Do not add a second mapping in the renderer.

    Total by construction (§18.5 D3a): every input returns one of the three
    values, and an unrecognised level maps to `"warning"`, never to `"notice"`
    -- guessing downwards would quietly demote something the extension thought
    worth saying. `compatibility`, by contrast, is mapped down *deliberately*:
    D3a pins it to `INFO`.
    """
    normalized = (level or "").strip().lower()
    if normalized.startswith("error"):
        return "error"
    if normalized == "compatibility":
        # D3a: `compatibility` -> INFO. `"notice"` is the lowercase value the
        # Audit renderer turns into the `INFO` token.
        return "notice"
    if normalized.startswith("warning"):
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


def message_for_level(message: str, level: str) -> str:
    """The finding's message, with an unknown `level` appended in parentheses.

    §18.5 D3a: a level the mapping table does not know maps to `WARNING` **and**
    has its raw `level` appended to the message -- "never dropped". The append
    has to happen here, where the message is composed: `severity_for_level`
    returns a severity and structurally cannot carry text, and doing it in the
    Audit renderer would put `plpgsql_check` level knowledge in the UI and
    create the second mapping D3a forbids. The raw value also stays on
    `CheckFinding.level`, so "map it once" and "never drop the raw level" hold
    together.
    """
    if is_known_level(level):
        return message
    raw = (level or "").strip()
    return f"{message} ({raw})" if message else f"({raw})"


def parse_findings(rows: Sequence[Any], request: CheckRequest) -> list[CheckFinding]:
    """Turn `plpgsql_check_function_tb` rows into `CheckFinding`s.

    Raises `MalformedCheckOutputError` for a row that is not the documented
    11 columns. Dropping such a row would shrink the finding list, and a
    shorter finding list is indistinguishable from a cleaner routine — the one
    lie this module exists to prevent.

    The severity comes from `severity_for_level` (the single mapping) and the
    message from `message_for_level`, which appends an *unknown* raw level in
    parentheses so a level this build never heard of is never swallowed
    (§18.5 D3a).
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
                message=message_for_level(_as_text(message), _as_text(level)),
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
# Tier 1 -- findings parsed out of the notice channel (§18.5 D3)
# ---------------------------------------------------------------------------

#: PostgreSQL's `CONTEXT` for an extra-warning raised while a body compiles:
#: `compilation of PL/pgSQL function "f" near line 3`. The line number exists
#: **nowhere else** for tier 1 -- there are no rows to read it off.
_NOTICE_LINE_RE = re.compile(r"near line (\d+)")

#: Notice severities that are tier-1 *findings*. Deliberately narrow: a plain
#: `NOTICE` is chatter the ladder itself provokes -- `DROP TRIGGER IF EXISTS`
#: emits *"trigger ... does not exist, skipping"* on every first apply -- and
#: rendering that as a lint finding would train the user to ignore the channel
#: that carries the real warnings. Anything at WARNING or above is kept.
NOTICE_FINDING_SEVERITIES = frozenset({"WARNING", "ERROR", "FATAL", "PANIC", "EXCEPTION"})


def notice_line(notice: Any) -> int | None:
    """The `prosrc`-relative line a notice's `CONTEXT` names, or None.

    None is a real answer: a notice with no `near line N` (or a `context` the
    driver never populated) is rendered with no line rather than line 1.
    """
    match = _NOTICE_LINE_RE.search(str(getattr(notice, "context", "") or ""))
    if match is None:
        return None
    return int(match.group(1))


def is_finding_notice(notice: Any) -> bool:
    """Whether this notice is a tier-1 finding rather than ladder chatter --
    see `NOTICE_FINDING_SEVERITIES`."""
    severity = str(getattr(notice, "severity", "") or "").strip().upper()
    return severity in NOTICE_FINDING_SEVERITIES


def findings_from_notices(
    notices: Sequence[Any], request: CheckRequest
) -> list[CheckFinding]:
    """Tier 1's findings: the captured notices, mapped onto `CheckFinding`s.

    The line goes through the **same** `map_lineno` tier 3 uses, because the
    number in `near line N` is likewise `prosrc`-relative while the buffer is
    `pg_get_functiondef` output — one offset rule, one implementation, and a
    `None` (rendered with no line) whenever the dollar-quote opener cannot be
    located (§18.5 D3's "never guess").
    """
    findings: list[CheckFinding] = []
    for notice in notices:
        if not is_finding_notice(notice):
            continue
        raw_level = str(getattr(notice, "severity", "") or "")
        source_lineno = notice_line(notice)
        findings.append(
            CheckFinding(
                severity=severity_for_level(raw_level),
                message=_as_text(getattr(notice, "message", "")),
                line=map_lineno(request.buffer_text, source_lineno),
                level=raw_level,
                sqlstate=_as_text(getattr(notice, "sqlstate", "")),
                detail=_as_text(getattr(notice, "detail", "")),
                hint=_as_text(getattr(notice, "hint", "")),
                context=_as_text(getattr(notice, "context", "")),
                source_lineno=source_lineno,
                identity=request.identity,
                tier=1,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# The capability gate -- never a silent no-op
# ---------------------------------------------------------------------------

def not_installed_reason(caps: SandboxCapabilities) -> str:
    """The `installable` reason, with the actionable second sentence chosen by
    `install_gate` rather than guessed here (§18.5 D3a).

    - install offered -> name the one-click install and both places it lives;
    - install refused (the connection is not a superuser) -> `install_gate`'s
      **own** `CREATE EXTENSION requires superuser` sentence, taken from the
      gate so the wording exists in exactly one place. Telling a non-superuser
      to "install it from Sandbox Setup" would point at a button that is not
      offered to them.
    """
    offered, gate_reason = install_gate(caps)
    if offered or not gate_reason:
        return REASON_NOT_INSTALLED
    return f"{REASON_NOT_INSTALLED_BASE} {gate_reason}"


def capability_outcome(caps: SandboxCapabilities) -> TierOutcome | None:
    """None when tier 3 can run; otherwise the `unavailable` outcome
    explaining why it cannot, one distinct reason per
    `SandboxCapabilities.plpgsql_check_state` value.

    All three non-runnable states are `unavailable` rather than `errored`
    (nothing went wrong — the check simply could not happen), but they are
    **not interchangeable**: "the DBA never installed the library",
    "it is installable, click the button", and "we could not even ask" call
    for three different user actions. The `absent` text is `install_gate`'s
    own, and so is the `installable`-but-not-superuser half of
    `not_installed_reason`, so both wordings live in exactly one place.
    """
    state = caps.plpgsql_check_state
    if state == "installed":
        return None
    if state == "installable":
        return TierOutcome(status=STATUS_UNAVAILABLE, reason=not_installed_reason(caps))
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


# ---------------------------------------------------------------------------
# The one-call ladder -- tiers 0-2 (and 3) through db/apply.py::apply_ddl
# ---------------------------------------------------------------------------

#: The write seam, as an injected callable: `(target, statements, *, commit) ->
#: ApplyOutcome`. Defaults to `db/apply.py::apply_ddl`; every test passes its
#: own, so no test can open a connection or execute DDL.
Applier = Callable[..., ApplyOutcome]


def apply_and_check(
    session: CheckSession,
    request: CheckRequest,
    caps: SandboxCapabilities,
    *,
    ddl_text: str | None = None,
    applier: Applier = apply_ddl,
) -> CheckReport:
    """§18.5 D3's **"Apply to Sandbox"** gesture: apply this object's DDL to the
    sandbox and run the whole ladder over it, **committing**.

    One `apply_ddl` call, one transaction: the `SET`, the DDL, the `applied`
    bookkeeping row and the `plpgsql_check` SELECT together. Tier 2's outcome
    **is** the apply's outcome, and the working-set row is written in the same
    transaction — so the sandbox can never hold the DDL without the bookkeeping
    row that records what is in it, nor the row without the DDL.

    `ddl_text` defaults to `request.buffer_text` (the tab's text, which is what
    the user is applying); it is a separate parameter only so a caller that
    formats or normalizes before applying can say so explicitly rather than
    mutate the request.

    **Never raises for a database problem.** A rejected statement leaves the
    sandbox untouched (the transaction rolls back) and is reported as the tier
    that produced it, with `CAVEAT_ROLLED_BACK` stating out loud that nothing
    was applied — a user who pressed Apply must never be left believing it
    landed.
    """
    return _run_ladder(
        session,
        request,
        caps,
        ddl_text=ddl_text,
        applier=applier,
        commit=True,
        record_applied=True,
    )


def probe_check(
    session: CheckSession,
    request: CheckRequest,
    caps: SandboxCapabilities,
    *,
    ddl_text: str | None = None,
    applier: Applier = apply_ddl,
) -> CheckReport:
    """§18.5 D3's **"Check without applying"** probe: the identical ladder, run
    with `apply_ddl(..., commit=False)`.

    **This is the one narrow place rollback survives** (§18.5 D2): a convenience
    for *"what would this do?"*, not a safety mechanism, and not threaded through
    the rest of the code — the sandbox's real safety property is the ownership
    guard, and the sandbox is *meant* to accumulate applied edits.

    It differs from `apply_and_check` in exactly two things — `commit=False` and
    no bookkeeping row — and shares everything else *by construction*, because a
    probe that diverged from the real apply would validate something the user is
    not about to run. Both leave the reported tiers identical; only `committed`
    and the caveats differ.
    """
    return _run_ladder(
        session,
        request,
        caps,
        ddl_text=ddl_text,
        applier=applier,
        commit=False,
        record_applied=False,
    )


def _run_ladder(
    session: CheckSession,
    request: CheckRequest,
    caps: SandboxCapabilities,
    *,
    ddl_text: str | None,
    applier: Applier,
    commit: bool,
    record_applied: bool,
) -> CheckReport:
    """`apply_and_check`/`probe_check`'s shared body -- one composed statement
    list, one `apply_ddl` call, one report assembled by statement index."""
    text = request.buffer_text if ddl_text is None else ddl_text
    plan = build_ladder(request, caps, text, record_applied=record_applied)

    try:
        outcome = applier(session, plan.statements, commit=commit)
    except UnsafeIdentifierError:
        # A hostile identifier is a programming/allowlist failure, not a check
        # result, and must not be laundered into "could not check".
        raise
    except Exception as exc:  # noqa: BLE001 -- the seam failing is "errored", never "clean"
        reason = f"the sandbox write seam raised instead of reporting: {exc}"
        errored = TierOutcome(status=STATUS_ERRORED, reason=reason)
        return CheckReport(
            tier0=errored,
            tier1=errored,
            tier2=errored,
            tier3=errored,
            caveats=(CAVEAT_ROLLED_BACK,) if commit else (CAVEAT_PROBE_ONLY,),
        )

    return _report_from_outcome(
        request, caps, outcome, plan, commit=commit, ddl_text=text
    )


def _report_from_outcome(
    request: CheckRequest,
    caps: SandboxCapabilities,
    outcome: ApplyOutcome,
    plan: LadderPlan,
    *,
    commit: bool,
    ddl_text: str,
) -> CheckReport:
    """Turn one `ApplyOutcome` into a four-tier `CheckReport`.

    **Every tier is attributed by the index this module chose for it.** Nothing
    is inferred from `outcome.ok`: a run that failed in the check SELECT has a
    perfectly good tier 2, and a run that failed in the DDL has a tier 3 that
    never happened. Reading `ok` alone would collapse both into one wrong story.
    """
    findings: list[CheckFinding] = []
    caveats: list[str] = []

    tier1, tier1_findings = _tier1_outcome(outcome, plan, request)
    findings.extend(tier1_findings)

    tier2, tier2_findings = _tier2_outcome(outcome, plan, ddl_text, request)
    findings.extend(tier2_findings)

    tier0 = _tier0_outcome(tier2)

    tier3, tier3_findings, tier3_caveats = _tier3_outcome(outcome, plan, caps, request)
    findings.extend(tier3_findings)
    caveats.extend(tier3_caveats)

    if any(f.line is None and f.source_lineno for f in findings):
        caveats.append(CAVEAT_UNMAPPED_LINES)

    committed = bool(outcome.committed)
    if commit and not committed:
        caveats.append(CAVEAT_ROLLED_BACK)
    elif not commit:
        caveats.append(CAVEAT_PROBE_ONLY)

    return CheckReport(
        tier0=tier0,
        tier1=tier1,
        tier2=tier2,
        tier3=tier3,
        findings=tuple(findings),
        caveats=tuple(caveats),
        committed=committed,
    )


def _not_reached_reason(outcome: ApplyOutcome) -> str:
    """Why a statement never ran: the earlier failure, quoted."""
    return REASON_NOT_REACHED.format(
        index="?" if outcome.statement_index is None else outcome.statement_index,
        message=outcome.message or "no message",
    )


def _tier1_outcome(
    outcome: ApplyOutcome, plan: LadderPlan, request: CheckRequest
) -> tuple[TierOutcome, list[CheckFinding]]:
    """Tier 1 -- the extra-warnings lint, whose entire output is the notice
    channel. `unavailable` whenever that channel was not live, because an empty
    notice list from a runner that cannot capture notices is indistinguishable
    from a clean routine (§18.5 D3)."""
    if not outcome.notices_captured:
        return TierOutcome(status=STATUS_UNAVAILABLE, reason=REASON_NO_NOTICE_CHANNEL), []
    if plan.lint_index is not None and outcome.statement_index == plan.lint_index:
        return (
            TierOutcome(
                status=STATUS_ERRORED,
                reason=(
                    "the extra-warnings lint could not be switched on "
                    f"({outcome.message}) -- nothing was lint-checked."
                ),
                detail=outcome.sqlstate,
            ),
            [],
        )
    if not outcome.reached(plan.ddl_index):
        # The lint is only ever observed while the DDL compiles; if the DDL
        # never ran there is nothing to have warned about.
        return (
            TierOutcome(status=STATUS_UNAVAILABLE, reason=_not_reached_reason(outcome)),
            [],
        )
    findings = findings_from_notices(outcome.notices, request)
    if findings:
        return (
            TierOutcome(
                status=STATUS_FOUND_ISSUES,
                reason=f"the extra-warnings lint reported {len(findings)} warning(s)",
            ),
            findings,
        )
    return (
        TierOutcome(
            status=STATUS_PASSED,
            reason="the extra-warnings lint reported nothing",
        ),
        [],
    )


def _tier2_outcome(
    outcome: ApplyOutcome, plan: LadderPlan, ddl_text: str, request: CheckRequest
) -> tuple[TierOutcome, list[CheckFinding]]:
    """Tier 2 -- did the DDL apply at all (parse + `check_function_bodies` +
    dependency resolution).

    A rejected statement is `found_issues`, not `errored`: the check worked
    perfectly and the answer is *"this DDL does not apply"*, which is a real
    finding and a hard, non-overridable Apply-to-Target blocker. `errored` is
    reserved for the check machinery itself failing.
    """
    if plan.ddl_index is None:
        return TierOutcome(status=STATUS_UNAVAILABLE, reason=REASON_NO_DDL_TEXT), []
    if outcome.statement_index == plan.ddl_index:
        finding = CheckFinding(
            severity="error",
            message=outcome.message,
            line=outcome.line,
            level="error",
            sqlstate=outcome.sqlstate,
            statement=outcome.statement,
            detail=outcome.detail,
            hint=outcome.hint,
            position=outcome.position,
            identity=request.identity,
            tier=2,
        )
        return (
            TierOutcome(
                status=STATUS_FOUND_ISSUES,
                reason=f"the DDL was rejected by the sandbox: {outcome.message}",
                detail=outcome.sqlstate,
            ),
            [finding],
        )
    if outcome.reached(plan.ddl_index):
        return (
            TierOutcome(
                status=STATUS_PASSED,
                reason="the DDL applied to the sandbox",
            ),
            [],
        )
    return (
        TierOutcome(status=STATUS_ERRORED, reason=_not_reached_reason(outcome)),
        [],
    )


def _tier0_outcome(tier2: TierOutcome) -> TierOutcome:
    """Tier 0 -- **collapsed into tier 2** (§18.5 D3's licensing caveat): the
    syntax check is PostgreSQL's own parser, reached by executing the DDL, so
    there is no separate offline checker and no GPL-only grammar dependency. It
    therefore mirrors tier 2's status exactly, with a reason that says which
    parser judged the syntax -- never a silently-passing extra line."""
    if tier2.verified:
        return TierOutcome(status=tier2.status, reason=REASON_TIER0_COLLAPSED)
    return TierOutcome(status=STATUS_UNAVAILABLE, reason=REASON_TIER0_NO_SANDBOX)


def _tier3_outcome(
    outcome: ApplyOutcome,
    plan: LadderPlan,
    caps: SandboxCapabilities,
    request: CheckRequest,
) -> tuple[TierOutcome, list[CheckFinding], list[str]]:
    """Tier 3 -- `plpgsql_check`'s rows, read off the check statement's result.

    The capability gate comes first and is `capability_outcome`'s, never a bare
    `try/except` (§18.5 D3a). After that, "the check statement never ran" and
    "it ran and returned nothing" are kept apart by `ApplyOutcome.result_at`,
    and "it returned nothing because the object is not there" by the resolve
    statement's own row.
    """
    unavailable = capability_outcome(caps)
    if unavailable is not None:
        return unavailable, [], []
    if plan.check_index is None:
        return (
            TierOutcome(
                status=STATUS_UNAVAILABLE, reason=REASON_TRIGGER_FUNCTION_UNKNOWN
            ),
            [],
            [],
        )
    if outcome.statement_index == plan.check_index:
        return (
            TierOutcome(
                status=STATUS_ERRORED,
                reason=f"plpgsql_check could not be run: {outcome.message}",
                detail=outcome.sqlstate,
            ),
            [],
            [],
        )
    result = outcome.result_at(plan.check_index)
    if result is None:
        return (
            TierOutcome(status=STATUS_UNAVAILABLE, reason=_not_reached_reason(outcome)),
            [],
            [],
        )

    resolved = outcome.result_at(plan.resolve_index)
    funcoid, relid = _read_resolution(() if resolved is None else resolved.rows)
    if funcoid is None:
        return (
            TierOutcome(status=STATUS_UNAVAILABLE, reason=REASON_OBJECT_ABSENT),
            [],
            [],
        )
    if request.regclass_text is not None and relid is None:
        return (
            TierOutcome(status=STATUS_UNAVAILABLE, reason=REASON_RELATION_ABSENT),
            [],
            [],
        )

    try:
        findings = parse_findings(list(result.rows), request)
    except MalformedCheckOutputError as exc:
        return (
            TierOutcome(status=STATUS_ERRORED, reason=str(exc), detail=exc.detail),
            [],
            [],
        )

    caveats = list(BLIND_SPOT_CAVEATS)
    if findings:
        return (
            TierOutcome(
                status=STATUS_FOUND_ISSUES,
                reason=f"plpgsql_check reported {len(findings)} finding(s)",
            ),
            findings,
            caveats,
        )
    return (
        TierOutcome(
            status=STATUS_PASSED,
            reason=f"plpgsql_check found nothing in {request.identity}",
        ),
        [],
        caveats,
    )


def recheck(
    session: CheckSession,
    request: CheckRequest,
    caps: SandboxCapabilities,
    *,
    query: Query | None = None,
) -> CheckReport:
    """§18.5 D3's **"Check"** gesture: run the ladder against the sandbox **as
    it currently stands**, applying nothing.

    Nothing new is applied, so **tiers 0-2 have nothing to compile in this run**
    and say so: they are *about* applying, and reporting them as `passed` because
    an earlier apply once succeeded would be exactly the never-report-clean-when-
    unchecked violation D3 forbids. What tier 2 *can* honestly report is the
    bookkeeping fact — *"applied &lt;timestamp&gt;"* from the `applied` table —
    which `_recheck_tier2` reads when the session can supply it, together with
    D3's mandatory **stale-buffer caveat** when the caller's buffer hash differs
    from `applied.text_sha1`. Applying is `apply_and_check`; checking without
    applying is `probe_check`; this gesture writes nothing, deliberately.
    """
    report = run_plpgsql_check(session, request, caps, query=query)
    tier2, caveats = _recheck_tier2(session, request)
    return CheckReport(
        tier0=_tier0_outcome(tier2),
        tier1=report.tier1,
        tier2=tier2,
        tier3=report.tier3,
        findings=report.findings,
        caveats=report.caveats + tuple(caveats),
        committed=False,
    )


#: `recheck`'s tier 2: the object is in the sandbox and the bookkeeping table
#: says when it got there. `passed` is honest here -- it *did* compile, at that
#: timestamp -- and the stale-buffer caveat carries the rest of the truth.
REASON_ALREADY_APPLIED = (
    "not re-compiled in this run; the sandbox already holds this object, "
    "applied {applied_at}."
)

#: The bookkeeping table has no row for this object, so nothing can be said
#: about when (or whether) it compiled.
REASON_NOT_IN_WORKING_SET = (
    "this object is not in the sandbox's working set, so nothing is recorded "
    "about it ever having compiled there -- apply it to the sandbox first."
)

#: The working-set table could not be read, so even the "applied when?" fact is
#: unknown. Never degraded to "not applied" -- see `SandboxCapabilities`.
REASON_WORKING_SET_UNREADABLE = (
    "the sandbox's working-set table could not be read ({error}), so it is "
    "unknown whether or when this object was applied."
)


def _recheck_tier2(
    session: Any, request: CheckRequest
) -> tuple[TierOutcome, list[str]]:
    """`recheck`'s tier 2 and its caveats, from the `applied` bookkeeping table.

    Read duck-typed (`session.applied()` may not exist on a stub, and this
    module's `CheckSession` protocol deliberately requires only `params` and
    `executor`), and every failure lands on a *stated* outcome: a missing row,
    an unreadable table and a stale hash are three different facts and none of
    them is "clean".
    """
    applied = getattr(session, "applied", None)
    if not callable(applied):
        return TierOutcome(status=STATUS_UNAVAILABLE, reason=REASON_TIER_NOT_BUILT), []
    try:
        rows = list(applied() or [])
    except Exception as exc:  # noqa: BLE001 -- unreadable is not "not applied"
        return (
            TierOutcome(
                status=STATUS_UNAVAILABLE,
                reason=REASON_WORKING_SET_UNREADABLE.format(error=exc),
            ),
            [],
        )

    wanted = request.working_set_ref
    row = next((r for r in rows if applied_ref(r) == wanted), None)
    if row is None:
        return (
            TierOutcome(status=STATUS_UNAVAILABLE, reason=REASON_NOT_IN_WORKING_SET),
            [],
        )

    applied_at = str(getattr(row, "applied_at", "") or "an unknown time")
    caveats: list[str] = []
    recorded = str(getattr(row, "text_sha1", "") or "")
    if request.buffer_text and recorded and recorded != text_sha1(request.buffer_text):
        caveats.append(CAVEAT_STALE_BUFFER.format(applied_at=applied_at))
    return (
        TierOutcome(
            status=STATUS_PASSED,
            reason=REASON_ALREADY_APPLIED.format(applied_at=applied_at),
        ),
        caveats,
    )


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
    "CAVEAT_PROBE_ONLY",
    "CAVEAT_ROLLED_BACK",
    "CAVEAT_STALE_BUFFER",
    "CAVEAT_UNMAPPED_LINES",
    "CHECK_COLUMNS",
    "NOTICE_FINDING_SEVERITIES",
    "TIER1_SET_SQL",
    "TRIGGER_REPLACE_MIN_MAJOR",
    "Applier",
    "LadderPlan",
    "CheckFinding",
    "CheckReport",
    "CheckRequest",
    "CheckSession",
    "KNOWN_LEVELS",
    "MalformedCheckOutputError",
    "Query",
    "REASON_ALREADY_APPLIED",
    "REASON_INSTALL_LOCATIONS",
    "REASON_NOT_INSTALLED",
    "REASON_NOT_INSTALLED_BASE",
    "REASON_NOT_IN_WORKING_SET",
    "REASON_NOT_REACHED",
    "REASON_NO_DDL_TEXT",
    "REASON_NO_NOTICE_CHANNEL",
    "REASON_OBJECT_ABSENT",
    "REASON_RELATION_ABSENT",
    "REASON_SWEEP_ROW_ERRORED",
    "REASON_TIER0_COLLAPSED",
    "REASON_TIER0_NO_SANDBOX",
    "REASON_TIER_NOT_BUILT",
    "REASON_TRIGGER_FUNCTION_UNKNOWN",
    "REASON_UNKNOWN_CAPABILITY",
    "REASON_WORKING_SET_UNREADABLE",
    "STATUS_ERRORED",
    "STATUS_FOUND_ISSUES",
    "STATUS_PASSED",
    "STATUS_UNAVAILABLE",
    "TIER_NOT_BUILT",
    "TierOutcome",
    "WorkingSetRef",
    "apply_and_check",
    "applied_ref",
    "blind_spots",
    "body_line_offset",
    "build_check_sql",
    "build_guarded_check_sql",
    "build_ladder",
    "build_resolve_sql",
    "build_trigger_drop_sql",
    "capability_outcome",
    "check_working_set",
    "findings_from_notices",
    "is_finding_notice",
    "is_known_level",
    "map_lineno",
    "message_for_level",
    "needs_trigger_drop",
    "not_installed_reason",
    "notice_line",
    "parse_findings",
    "probe_check",
    "recheck",
    "request_from_applied",
    "run_plpgsql_check",
    "severity_for_level",
]
