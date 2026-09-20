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

# pgtp_editor/db/pg_dump_ddl.py
"""The **full**-mode DDL layer (`FQ-260812022749` Part 3): one whole-database
`pg_dump --schema-only`, split into statements, each statement attributed to
the relation it belongs to.

Two halves, deliberately separated by a seam:

* **`fetch_schema_dump`** -- the ONE subprocess. Shaped exactly like
  `db/sandbox.py::clone_data`'s `pg_dump` call (the injectable `ProcessRunner`,
  `_pg_env`'s *password in `PGPASSWORD`, never in argv* discipline, a named
  refusal rather than a silent fallback), because a second spawning style is
  how two different sets of rules about credentials come to exist.
* **`parse_pg_dump`** -- **pure and Qt-free**, like `db/table_ddl.py` and
  `db/ddl_buffer.py`: dump text in, classified statements out. Every branch is
  therefore testable against canned fixture text with **no server and no
  subprocess**, which is the suite's standing discipline.

**ONE whole-database dump per Explorer build, never per-table `-t`.** This is
recorded as a trap, not an option: `-t` costs one subprocess *and* one server
connection per table against a buffer §18.1 settled as having **no cache** (300
tables = 300 spawns per refresh), and `-t` does **not** dump the objects the
table depends on, so a `SERIAL` column's owned sequence can go missing -- the
very case the feature's request opened with. Nobody may reach for `-t` without
re-reading this paragraph.

**Why statement boundaries recover the spans.** A whole-database
`pg_dump --schema-only` is dependency-ordered globally rather than grouped per
object, so *a table's DDL is not contiguous* -- but **each individual statement
is**: `CREATE TABLE … );`, `ALTER TABLE ONLY … ADD CONSTRAINT …;` and
`CREATE INDEX …;` are each one contiguous run of lines. So parsing statement
boundaries yields contiguous regions that fit the **existing** `DdlObjectSpan`
with at most a new `kind` value, and §18.1's trap 1 (one dataclass, one `kind`
field -- a sibling span type forks both span walks and the second one written
misses a case) is respected.

**The residual risk, stated rather than hidden: this module depends on
`pg_dump`'s TEXT LAYOUT, which is not a documented contract** (`pg_catalog`
is). That inverts the *"pg_dump is correct so we needn't be"* argument for
exactly the code that parses it, and the mitigation is structural: the parse
either attributes **every** relation the introspection found or the caller
degrades to restricted mode with a named `[DDL]` row (`db/ddl_buffer.py::
build_ddl_buffer`). A half-parsed buffer whose spans point at the wrong lines
is the worst outcome available here -- worse than restricted DDL -- so it is
not reachable: this module reports what it could not attribute, and refusing is
the caller's single, visible decision.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

from .config import ConnectionParams
from .sandbox import ProcessRunner, _pg_env

#: The invocation. `--schema-only` because the buffer is DDL; `--no-owner` /
#: `--no-privileges` because `ALTER TABLE … OWNER TO` and `GRANT` are
#: deployment scaffolding that says nothing about an object's shape and would
#: bury the statements that do.
#:
#: **`--no-comments` is deliberately NOT passed.** It would drop the
#: `COMMENT ON` statements that the *restricted* renderer emits today
#: (`table_ddl._comment_lines`), which would make full mode less complete than
#: restricted mode in one respect -- the one regression this feature must not
#: ship.
PG_DUMP_SCHEMA_ONLY_ARGS: tuple[str, ...] = (
    "--schema-only",
    "--no-owner",
    "--no-privileges",
)

#: Seconds before the schema dump is abandoned. Unlike `--version` this one
#: connects and reads the whole catalog, so the budget is far larger -- but it
#: is bounded, because an expiry must degrade to restricted mode with a named
#: row rather than wedge an Explorer open.
PG_DUMP_SCHEMA_TIMEOUT_S = 120


class SchemaDumpError(Exception):
    """`pg_dump --schema-only` could not be run, or refused.

    A **named** failure in the shape `db/sandbox.py::CloneDataError` set
    ("never silently falls back"). The caller's response is still to fall
    back -- to *restricted* mode -- but only after saying so out loud, which
    is the opposite of silence.
    """

    def __init__(self, step: str, returncode: int, stderr: str) -> None:
        self.step = step
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"{step} failed (exit {returncode}): {stderr.strip() or '(no stderr output)'}"
        )


def fetch_schema_dump(
    params: ConnectionParams,
    pg_dump_path: str,
    *,
    run: ProcessRunner = subprocess.run,
    timeout: int = PG_DUMP_SCHEMA_TIMEOUT_S,
) -> str:
    """One whole-database `pg_dump --schema-only`, decoded to text.

    Raises `SchemaDumpError` on a non-zero exit, a timeout, or a spawn that
    fails outright. **Never** returns a partial dump as if it were whole: a
    truncated dump would parse into a buffer missing objects, which is the
    silent wrong result this feature exists to avoid.

    `run` is the same injectable `ProcessRunner` seam `clone_data` uses, so no
    test in this suite ever spawns a process or reaches a server.
    """
    argv = [
        pg_dump_path,
        *PG_DUMP_SCHEMA_ONLY_ARGS,
        "--host", params.host,
        "--port", str(params.port),
        "--username", params.user,
        "--dbname", params.database,
    ]
    try:
        result = run(argv, env=_pg_env(params), capture_output=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 -- every spawn failure is one shape
        raise SchemaDumpError("pg_dump --schema-only", -1, str(exc)) from exc
    returncode = getattr(result, "returncode", 0) or 0
    if returncode != 0:
        stderr = _decode(getattr(result, "stderr", b""))
        raise SchemaDumpError("pg_dump --schema-only", returncode, stderr)
    return _decode(getattr(result, "stdout", b""))


def _decode(payload) -> str:
    if isinstance(payload, str):
        return payload
    return bytes(payload or b"").decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# The pure parser
# ---------------------------------------------------------------------------

#: Statement kinds. These are the parser's vocabulary, NOT span kinds -- the
#: two overlap on purpose where they mean the same thing (`table`, `view`,
#: `matview`, `constraint`, `index`) and diverge where they do not.
KIND_TABLE = "table"
KIND_VIEW = "view"
KIND_MATVIEW = "matview"
KIND_CONSTRAINT = "constraint"
KIND_INDEX = "index"
#: Any other statement that names one relation: `ALTER TABLE … ALTER COLUMN …
#: SET DEFAULT nextval(…)`, `ATTACH PARTITION`, `ENABLE ROW LEVEL SECURITY`,
#: `CREATE RULE … ON …`, `COMMENT ON TABLE/COLUMN/VIEW …`.
KIND_RELATION_EXTRA = "relation_extra"
#: `CREATE FUNCTION` / `CREATE PROCEDURE` / `CREATE TRIGGER` and their
#: `ALTER`/`COMMENT ON` companions. **Recognised so they can be left out of
#: the buffer**, because the routines and triggers section is rendered from the
#: catalog in BOTH modes -- see `db/ddl_buffer.py` for why that is not a
#: shortcut but a requirement (routine identity is `RoutineInfo.signature`, and
#: recovering it from a `CREATE FUNCTION` header would mean re-rendering it).
KIND_ROUTINE = "routine"
#: Everything else, verbatim and never dropped: the `SET` preamble,
#: `CREATE SCHEMA`, `CREATE EXTENSION`, `CREATE TYPE`, `CREATE DOMAIN`,
#: `CREATE SEQUENCE`, `ALTER SEQUENCE … OWNED BY`, and any statement a future
#: PostgreSQL emits that this parser has never seen.
KIND_OTHER = "other"

#: The relation kinds that own a `CREATE` statement of their own.
RELATION_KINDS = frozenset({KIND_TABLE, KIND_VIEW, KIND_MATVIEW})

_IDENT = r'(?:"(?:[^"]|"")*"|[A-Za-z_\u0080-\uffff][A-Za-z0-9_$\u0080-\uffff]*)'
_QUAL = rf"({_IDENT})\.({_IDENT})"

# Anchored at the statement's start, always: a literal further along the
# statement (`COMMENT ON TABLE t IS 'CREATE TABLE decoy'`) must never be able
# to look like a statement head.
_RE_TABLE = re.compile(
    rf"\A\s*CREATE\s+(?:UNLOGGED\s+|GLOBAL\s+|LOCAL\s+|TEMP\s+|TEMPORARY\s+)*TABLE\s+"
    rf"(?:IF\s+NOT\s+EXISTS\s+)?{_QUAL}",
    re.IGNORECASE,
)
_RE_MATVIEW = re.compile(
    rf"\A\s*CREATE\s+MATERIALIZED\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?{_QUAL}",
    re.IGNORECASE,
)
_RE_VIEW = re.compile(
    rf"\A\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP\s+|TEMPORARY\s+|RECURSIVE\s+)*VIEW\s+"
    rf"{_QUAL}",
    re.IGNORECASE,
)
_RE_INDEX = re.compile(
    rf"\A\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?"
    rf"(?:IF\s+NOT\s+EXISTS\s+)?({_IDENT})\s+ON\s+(?:ONLY\s+)?{_QUAL}",
    re.IGNORECASE,
)
_RE_ADD_CONSTRAINT = re.compile(
    rf"\A\s*ALTER\s+TABLE\s+(?:ONLY\s+)?{_QUAL}\s+ADD\s+CONSTRAINT\s+({_IDENT})",
    re.IGNORECASE,
)
_RE_ALTER_RELATION = re.compile(
    rf"\A\s*ALTER\s+(?:TABLE|VIEW|MATERIALIZED\s+VIEW|FOREIGN\s+TABLE)\s+"
    rf"(?:ONLY\s+)?{_QUAL}",
    re.IGNORECASE,
)
_RE_COMMENT_COLUMN = re.compile(
    rf"\A\s*COMMENT\s+ON\s+COLUMN\s+{_QUAL}\.{_IDENT}", re.IGNORECASE
)
_RE_COMMENT_RELATION = re.compile(
    rf"\A\s*COMMENT\s+ON\s+(?:TABLE|VIEW|MATERIALIZED\s+VIEW|FOREIGN\s+TABLE)\s+{_QUAL}",
    re.IGNORECASE,
)
_RE_COMMENT_ON_RELATION_SUFFIX = re.compile(
    rf"\A\s*COMMENT\s+ON\s+(?:CONSTRAINT|TRIGGER|RULE|POLICY)\s+{_IDENT}\s+ON\s+"
    rf"(?:TABLE\s+)?{_QUAL}",
    re.IGNORECASE,
)
_RE_RULE = re.compile(
    rf"\A\s*CREATE\s+(?:OR\s+REPLACE\s+)?RULE\s+{_IDENT}\s+AS\s+ON\s+\w+\s+TO\s+{_QUAL}",
    re.IGNORECASE,
)
_RE_POLICY = re.compile(
    rf"\A\s*CREATE\s+POLICY\s+{_IDENT}\s+ON\s+{_QUAL}", re.IGNORECASE
)
_RE_TRIGGER = re.compile(
    rf"\A\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:CONSTRAINT\s+)?TRIGGER\s+{_IDENT}",
    re.IGNORECASE,
)
_RE_ROUTINE = re.compile(
    r"\A\s*(?:CREATE|ALTER)\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s",
    re.IGNORECASE,
)
_RE_COMMENT_ROUTINE = re.compile(
    r"\A\s*COMMENT\s+ON\s+(?:FUNCTION|PROCEDURE|TRIGGER)\s", re.IGNORECASE
)

#: A line inside a `CREATE TABLE` body that starts a **constraint** entry
#: rather than a column. Checked before a line's first token is taken as a
#: column name, because `CONSTRAINT`/`PRIMARY`/`CHECK` are perfectly legal
#: column names when quoted -- and the quoted spelling is what distinguishes
#: them, which is why the test is on the RAW first token.
_TABLE_BODY_CONSTRAINT_WORDS = frozenset(
    {"CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK", "FOREIGN", "EXCLUDE", "LIKE"}
)


def unquote_ident(token: str) -> str:
    """`"Order Lines"` -> `Order Lines`, `orders` -> `orders`.

    Span identities are **catalog** names (`DatabaseSchema.tables`' keys,
    `ColumnInfo.name`), which are unquoted, while `pg_dump` writes the quoted
    SQL spelling. This is the one place the two are reconciled; a second
    unquoting is how a table called `"Orders"` comes to match in one walk and
    not in the other.
    """
    text = (token or "").strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text[1:-1].replace('""', '"')
    return text


@dataclass
class _LexState:
    """Where the lexer is between two lines of one dump.

    `pg_dump` writes function bodies as dollar-quoted strings that span many
    lines, and a `;` inside one of them is not a statement terminator. Nothing
    else in this module needs to know that, which is why the knowledge lives
    in one 40-line lexer instead of in every regex.
    """

    in_string: bool = False
    in_quoted_ident: bool = False
    dollar_tag: str | None = None
    in_block_comment: bool = False

    @property
    def clean(self) -> bool:
        return not (
            self.in_string
            or self.in_quoted_ident
            or self.dollar_tag is not None
            or self.in_block_comment
        )


_DOLLAR_TAG = re.compile(r"\$([A-Za-z_\u0080-\uffff][A-Za-z0-9_\u0080-\uffff]*)?\$")


def _mask_line(line: str, state: _LexState) -> str:
    """`line` with every non-structural character blanked out, advancing
    `state`.

    Blanked: single-quoted literals, dollar-quoted bodies, `--` line comments,
    `/* */` block comments, and the *contents* of double-quoted identifiers (so
    a table named `"a;b"` cannot terminate a statement). The result is used
    ONLY for structure -- statement ends, paren depth, entry commas. Identities
    are read from the original text, anchored at the statement head, so nothing
    depends on the mask preserving names.
    """
    out: list[str] = []
    index = 0
    length = len(line)
    while index < length:
        char = line[index]
        if state.in_block_comment:
            if line.startswith("*/", index):
                state.in_block_comment = False
                out.append("  ")
                index += 2
                continue
            out.append(" ")
            index += 1
            continue
        if state.dollar_tag is not None:
            if line.startswith(state.dollar_tag, index):
                width = len(state.dollar_tag)
                state.dollar_tag = None
                out.append(" " * width)
                index += width
                continue
            out.append(" ")
            index += 1
            continue
        if state.in_string:
            if char == "'":
                if line.startswith("''", index):
                    out.append("  ")
                    index += 2
                    continue
                state.in_string = False
            out.append(" ")
            index += 1
            continue
        if state.in_quoted_ident:
            if char == '"':
                if line.startswith('""', index):
                    out.append("  ")
                    index += 2
                    continue
                state.in_quoted_ident = False
                out.append('"')
                index += 1
                continue
            out.append(" ")
            index += 1
            continue
        # -- outside every quoting construct ---------------------------------
        if line.startswith("--", index):
            out.append(" " * (length - index))
            break
        if line.startswith("/*", index):
            state.in_block_comment = True
            out.append("  ")
            index += 2
            continue
        if char == "'":
            state.in_string = True
            out.append(" ")
            index += 1
            continue
        if char == '"':
            state.in_quoted_ident = True
            out.append('"')
            index += 1
            continue
        if char == "$":
            match = _DOLLAR_TAG.match(line, index)
            if match is not None:
                state.dollar_tag = match.group(0)
                out.append(" " * len(match.group(0)))
                index += len(match.group(0))
                continue
        out.append(char)
        index += 1
    return "".join(out)


@dataclass(frozen=True)
class DumpStatement:
    """One contiguous statement out of the dump, with what it is about.

    `lines` is the statement's text **verbatim** -- this module never
    re-renders SQL. That is the whole point of full mode: `pg_dump` is the
    reference implementation, and *"educated developer centered"* text is its
    output, not our paraphrase of it.
    """

    kind: str
    #: The relation's schema, for the kinds that name one; `""` otherwise.
    schema: str = ""
    #: The object's own name: the relation for a `CREATE TABLE`, the constraint
    #: name for an `ADD CONSTRAINT`, the index name for a `CREATE INDEX`.
    name: str = ""
    #: `schema.name` of the relation this statement belongs to, or None.
    relation: str | None = None
    lines: tuple[str, ...] = ()
    #: Tables only: column name -> 0-based offset into `lines`. Populated for
    #: whatever the body's entries spell; the caller intersects it with the
    #: columns the catalog reported, so an entry this parser misread cannot
    #: become a span pointing at the wrong line.
    column_offsets: dict[str, int] = field(default_factory=dict)
    #: Tables only: the offsets of the constraints `pg_dump` renders **INLINE**
    #: in the `CREATE TABLE` body, i.e. `CONSTRAINT <name> CHECK (...)`.
    #:
    #: This is not symmetry for its own sake. `pg_dump` splits a table's
    #: constraints across two shapes -- `CHECK` (and `NOT NULL`) stay inside the
    #: `CREATE TABLE`, while `PRIMARY KEY` / `UNIQUE` / `FOREIGN KEY` come out
    #: later as `ALTER TABLE ONLY … ADD CONSTRAINT`. A parser that only handled
    #: the `ALTER` shape would leave every CHECK constraint's tree row with no
    #: span and no navigation, which is the shape of half-working nobody
    #: notices until a user clicks one.
    constraint_offsets: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDump:
    """Every statement, plus the two indexes a buffer build needs.

    `creates` and `attachments` are keyed by the **catalog** spelling of the
    relation (`schema.name`, unquoted), which is exactly
    `DatabaseSchema.tables`' key -- so attributing a relation is a dict lookup
    and never a second name-rendering.
    """

    statements: tuple[DumpStatement, ...]
    creates: dict[str, DumpStatement]
    attachments: dict[str, tuple[DumpStatement, ...]]
    #: Statements that name no relation, in dump order, verbatim. Emitted by
    #: the buffer rather than dropped: `CREATE EXTENSION`, `CREATE TYPE` and
    #: `CREATE SEQUENCE` are exactly what a clone of a table would otherwise
    #: silently need.
    other: tuple[DumpStatement, ...]

    @property
    def empty(self) -> bool:
        return not self.statements


def split_statements(text: str) -> list[list[str]]:
    """The dump's text as a list of statements, each a list of its lines.

    Comment-only and blank runs between statements are **dropped** -- they are
    `pg_dump`'s `-- Name: orders; Type: TABLE; …` headers plus the
    `-- Dumped by pg_dump version …` banner. Dropping them is deliberate twice
    over: `db/ddl_buffer.py` writes its own banner per object (the buffer's
    established convention, which the tree navigates by), and the *"Dumped
    by"* lines are the single most version-volatile text in the file, so
    keeping them would make the buffer differ across a client upgrade for no
    reader's benefit. A comment *inside* a statement stays where it is.
    """
    state = _LexState()
    statements: list[list[str]] = []
    current: list[str] = []
    for line in (text or "").splitlines():
        masked = _mask_line(line, state)
        if not current and not masked.strip():
            # Between statements: a blank line, or a line that masked away to
            # nothing (i.e. it was pure comment).
            continue
        current.append(line)
        if state.clean and ";" in masked:
            statements.append(current)
            current = []
    if current:
        # An unterminated tail (a truncated dump). Kept rather than discarded:
        # the caller's attribution check is what decides whether this dump is
        # trustworthy, and silently swallowing the evidence would help nobody.
        statements.append(current)
    return statements


def _classify(lines: list[str]) -> DumpStatement:
    """One statement -> what it is about. Pure, and the only place the dump's
    text layout is interpreted."""
    text = "\n".join(lines)
    tup = tuple(lines)

    match = _RE_TABLE.match(text)
    if match is not None:
        schema, name = unquote_ident(match.group(1)), unquote_ident(match.group(2))
        columns, constraints = _body_offsets(lines)
        return DumpStatement(
            kind=KIND_TABLE,
            schema=schema,
            name=name,
            relation=f"{schema}.{name}",
            lines=tup,
            column_offsets=columns,
            constraint_offsets=constraints,
        )

    for pattern, kind in ((_RE_MATVIEW, KIND_MATVIEW), (_RE_VIEW, KIND_VIEW)):
        match = pattern.match(text)
        if match is not None:
            schema, name = unquote_ident(match.group(1)), unquote_ident(match.group(2))
            return DumpStatement(
                kind=kind,
                schema=schema,
                name=name,
                relation=f"{schema}.{name}",
                lines=tup,
            )

    match = _RE_INDEX.match(text)
    if match is not None:
        index_name = unquote_ident(match.group(1))
        schema, name = unquote_ident(match.group(2)), unquote_ident(match.group(3))
        return DumpStatement(
            kind=KIND_INDEX,
            schema=schema,
            name=index_name,
            relation=f"{schema}.{name}",
            lines=tup,
        )

    match = _RE_ADD_CONSTRAINT.match(text)
    if match is not None:
        schema, name = unquote_ident(match.group(1)), unquote_ident(match.group(2))
        return DumpStatement(
            kind=KIND_CONSTRAINT,
            schema=schema,
            name=unquote_ident(match.group(3)),
            relation=f"{schema}.{name}",
            lines=tup,
        )

    # Routines and triggers are recognised only to be LEFT OUT of the buffer.
    if (
        _RE_ROUTINE.match(text)
        or _RE_TRIGGER.match(text)
        or _RE_COMMENT_ROUTINE.match(text)
    ):
        return DumpStatement(kind=KIND_ROUTINE, lines=tup)

    for pattern, groups in (
        (_RE_ALTER_RELATION, (1, 2)),
        (_RE_COMMENT_COLUMN, (1, 2)),
        (_RE_COMMENT_RELATION, (1, 2)),
        (_RE_COMMENT_ON_RELATION_SUFFIX, (1, 2)),
        (_RE_RULE, (1, 2)),
        (_RE_POLICY, (1, 2)),
    ):
        match = pattern.match(text)
        if match is not None:
            schema = unquote_ident(match.group(groups[0]))
            name = unquote_ident(match.group(groups[1]))
            return DumpStatement(
                kind=KIND_RELATION_EXTRA,
                schema=schema,
                name=name,
                relation=f"{schema}.{name}",
                lines=tup,
            )

    return DumpStatement(kind=KIND_OTHER, lines=tup)


def _body_offsets(lines: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    """`(column_offsets, constraint_offsets)` **inside** one `CREATE TABLE`.

    Walks the top-level parenthesised body with the same lexer the statement
    splitter uses, and reads the first token of each depth-1 entry that begins
    on its own line: `CONSTRAINT <name> …` records a constraint, anything else
    that starts with an identifier records a column.

    Nothing is guessed. An entry that does not begin with an identifier, or one
    that starts mid-line after another entry, is simply not recorded -- and the
    caller intersects what IS recorded with the catalog's own column/constraint
    names, so the only reachable failure is a *missing* span, never a span on
    the wrong line.
    """
    state = _LexState()
    columns: dict[str, int] = {}
    constraints: dict[str, int] = {}
    depth = 0
    started = False
    expect_entry = False
    for offset, line in enumerate(lines):
        masked = _mask_line(line, state)
        position = 0
        while position < len(masked):
            char = masked[position]
            if char == "(":
                depth += 1
                if depth == 1 and not started:
                    started = True
                    expect_entry = True
            elif char == ")":
                depth -= 1
                if depth == 0 and started:
                    return columns, constraints
            elif char == "," and depth == 1:
                expect_entry = True
            elif expect_entry and depth == 1 and not char.isspace():
                # The entry starts HERE. Only an entry whose first character is
                # on this line names an object at this offset.
                expect_entry = False
                remainder = line[position:]
                token = _leading_ident(remainder)
                if token is None:
                    position += 1
                    continue
                # A QUOTED token is always a name, never a keyword: a column
                # really can be called `"CONSTRAINT"`, and the quotes are the
                # only thing that distinguishes it from the keyword.
                quoted = token.startswith('"')
                if not quoted and token.upper() == "CONSTRAINT":
                    named = _leading_ident(remainder[len(token):])
                    if named is not None:
                        constraints.setdefault(unquote_ident(named), offset)
                elif quoted or token.upper() not in _TABLE_BODY_CONSTRAINT_WORDS:
                    columns.setdefault(unquote_ident(token), offset)
            position += 1
    return columns, constraints


_LEADING_IDENT = re.compile(rf"\A\s*({_IDENT})(?=\s|\(|,|$)")


def _leading_ident(text: str) -> str | None:
    match = _LEADING_IDENT.match(text)
    return match.group(1) if match is not None else None


def parse_pg_dump(text: str) -> ParsedDump:
    """Dump text -> classified statements plus the relation indexes.

    **Pure**: the same text in always gives the same statements, in the same
    order, with the same offsets. That property is pinned directly by a test,
    because it is what full mode has instead of restricted mode's proven
    end-to-end determinism (`pg_dump`'s own output varies with the client's
    version, which no test of ours can make untrue).
    """
    statements = tuple(_classify(lines) for lines in split_statements(text))
    creates: dict[str, DumpStatement] = {}
    attachments: dict[str, list[DumpStatement]] = {}
    other: list[DumpStatement] = []
    for statement in statements:
        if statement.kind in RELATION_KINDS and statement.relation:
            # First wins. A second `CREATE TABLE` for one relation cannot come
            # out of one dump, so this only ever guards a parse that misread
            # something -- and the caller's attribution check reports that.
            creates.setdefault(statement.relation, statement)
        elif statement.kind in (KIND_CONSTRAINT, KIND_INDEX, KIND_RELATION_EXTRA):
            attachments.setdefault(statement.relation or "", []).append(statement)
        elif statement.kind == KIND_ROUTINE:
            continue  # rendered from the catalog instead -- see the module doc
        else:
            other.append(statement)
    return ParsedDump(
        statements=statements,
        creates=creates,
        attachments={key: tuple(value) for key, value in attachments.items()},
        other=tuple(other),
    )
