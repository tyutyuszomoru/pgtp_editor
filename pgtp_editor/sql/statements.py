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

# pgtp_editor/sql/statements.py
"""Statement splitting and leading-keyword classification (spec §18.5 D4).

Two pure functions, Qt-free and connection-free like the rest of
`pgtp_editor/sql/` (§5's dependency rule):

- `split_statements(text)` -- cut a console buffer into the individual
  statements one Run executes, in order, each carrying its offset and line in
  the buffer so a failure can be attributed back to what the user typed.
- `classify_statement(sql)` -- `"read" | "write" | "ddl" | "unknown"`, the gate
  for §18.5 D4's one confirmation ("this Run changes objects in the sandbox").

**WIRED, and depended on by three other analyzers.** `ui/sql_console_panel.py`
splits every Run through `split_statements` and gates §18.5 D4's confirmation on
`classify_statement`/`CHANGES_OBJECTS`; `sql/from_clause.py` and
`sql/routine_scope.py` both build on `statement_at` for statement scoping, and
so -- through them -- do `sql/caret_context.py`, `sql/join_fk.py` and
`sql/signature_help.py`. The module stays standalone and side-effect free, but
it is no longer a spare part: a change to a boundary rule here is felt by every
caret-context gesture, not just by the console's Run.

REUSE, NOT A SECOND SCANNER
---------------------------
§18.5 D4 requires the splitter to be built on §18.4's existing
`sql/tokenizer.py`, and it is: `tokenize()` already recognizes single-quoted
strings (including the `E'...'` backslash-escape form), double-quoted
identifiers, `--` line comments, nestable `/* ... */` block comments and
dollar-quoted bodies (bare `$$` and tagged `$tag$`) as **single opaque
tokens**. So a `;` inside any of them is not a token in this module's view at
all, and a routine body full of semicolons can never be split. There is no
character scanning here, and no duplicate of the tokenizer's rules.

`sql/keywords.py` is the single dialect source, but it is a flat, uncategorized
keyword set: it carries no read/write/DDL grouping to reuse, so the small
classification tables below live here. They are reached only through
`Token.kind`/`Token.lowered`, i.e. via the tokenizer's own view of the text --
no second lexer, no re-implemented casing rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .tokenizer import (
    BLOCK_COMMENT,
    LINE_COMMENT,
    NEWLINE,
    PUNCT,
    WHITESPACE,
    WORD,
    Token,
    tokenize,
)

#: Token kinds that carry no statement of their own: trivia plus both comment
#: forms. Skipped when looking for a statement's first meaningful token.
_SKIPPABLE = frozenset({WHITESPACE, NEWLINE, LINE_COMMENT, BLOCK_COMMENT})

#: Kinds that make a fragment worth sending. A fragment of only whitespace
#: and/or comments is dropped: PostgreSQL answers an empty query with a bare
#: "can't execute an empty query" and it would occupy a statement index for
#: nothing, mis-attributing every later failure.
_TRIVIAL = _SKIPPABLE


@dataclass(frozen=True)
class Statement:
    """One statement of a Run, plus where it came from in the buffer.

    `text` is the **verbatim** buffer slice, with the terminating `;` and the
    surrounding whitespace removed but every internal character (comments,
    string contents, dollar-quoted body) untouched -- it is exactly what the
    caller sends, which is what makes `db/apply.py::line_of_position` exact:
    PostgreSQL's error `position` indexes the statement we sent.

    Composing with `db/apply.py`:

    - `apply_ddl(target, [s.text for s in split_statements(buf)])` -- its
      `statements` parameter is a `Sequence[str]`, so the plain texts feed it
      unchanged.
    - `ApplyOutcome.statement_index` is a 0-based index into that same
      sequence, so `statements[outcome.statement_index]` is the `Statement` the
      failure belongs to -- text for the report, `start`/`start_line` for
      pointing the editor at it.
    - `line_of_position(s.text, position)` gives the line **within** the
      statement; `s.line_offset + line_of_position(...)` gives the line in the
      buffer. `line_offset` is the only thing the caller cannot recompute
      itself, and it is why this is a dataclass rather than a bare `str`
      (see the `split_statements` docstring).
    """

    #: Verbatim statement text, no terminating `;`, no surrounding whitespace.
    text: str
    #: 0-based character offset of `text[0]` in the original buffer.
    start: int
    #: 0-based exclusive end offset of `text` in the original buffer.
    end: int
    #: 1-based line of `text[0]` in the original buffer.
    start_line: int
    #: 1-based column of `text[0]` in the original buffer.
    start_col: int
    #: Whether a `;` actually terminated this statement. False for the last
    #: statement of an unterminated buffer -- stated as a fact rather than
    #: inferred from being last, because a buffer may legitimately end with
    #: `;` and the console's echo of "what ran" should not invent one.
    terminated: bool

    @property
    def line_offset(self) -> int:
        """Add to a line number inside `text` to get the buffer's line.

        `self.start_line - 1`; see the class docstring's `line_of_position`
        composition.
        """
        return self.start_line - 1


Classification = Literal["read", "write", "ddl", "unknown"]

READ: Classification = "read"
WRITE: Classification = "write"
DDL: Classification = "ddl"
UNKNOWN: Classification = "unknown"

#: The classifications that must gate §18.5 D4's confirmation. `unknown` is in
#: here because the spec is explicit: "an unclassifiable statement is never
#: waved through as harmless".
CHANGES_OBJECTS: frozenset[str] = frozenset({DDL, UNKNOWN})

#: Leading keywords that only read. `explain` is here **conditionally** -- see
#: `_explain_executes`.
_READ_LEADERS = frozenset({"select", "values", "table", "show", "explain"})

#: Leading keywords that change rows but not object definitions.
#:
#: `truncate` is deliberately a WRITE, not a DDL: the confirmation `ddl` gates
#: says the sandbox's *applied working set* (what the open tabs believe is
#: applied) may no longer match, and `TRUNCATE` removes rows while leaving
#: every object definition in place -- so raising that particular prompt for it
#: would state something untrue. It is destructive, but destructive-to-data in
#: a database whose whole premise (§18.5 D4) is that it is disposable and
#: `Reset Sandbox`-able.
_WRITE_LEADERS = frozenset({"insert", "update", "delete", "merge", "truncate"})

#: Leading keywords that change objects. Kept to statements that really alter
#: the catalog -- anything merely *stateful* (`vacuum`, `analyze`, `cluster`,
#: `lock`, `set`, `copy`, ...) is left to `unknown` rather than being asserted
#: to be one of the three known kinds.
_DDL_LEADERS = frozenset(
    {
        "create",
        "alter",
        "drop",
        "grant",
        "revoke",
        "comment",
        "security",  # SECURITY LABEL
        "refresh",  # REFRESH MATERIALIZED VIEW
        "import",  # IMPORT FOREIGN SCHEMA
    }
)

#: Write keywords whose presence anywhere inside a `WITH` statement makes the
#: whole thing a write -- a data-modifying CTE (`WITH x AS (DELETE ...) SELECT`)
#: is not a read, and neither is `WITH x AS (...) DELETE ...`.
_WITH_WRITE_KEYWORDS = frozenset({"insert", "update", "delete", "merge"})

#: Spellings of `ANALYZE` accepted by PostgreSQL, both of which turn an
#: `EXPLAIN` into a statement that actually runs the query underneath.
_ANALYZE_SPELLINGS = frozenset({"analyze", "analyse"})


def split_statements(text: str) -> list[Statement]:
    """Split a console buffer into the statements one Run executes.

    Splitting happens only on a top-level `;` **token**, which -- because the
    scan is over `sql/tokenizer.py`'s token stream -- means a `;` inside a
    single-quoted string, an `E'...'` escape string, a double-quoted
    identifier, a `--` line comment, a (nestable) `/* ... */` block comment or
    a dollar-quoted body (`$$ ... $$`, `$tag$ ... $tag$`, and a differently
    tagged dollar quote nested inside another) is never a split point. A
    plpgsql routine body therefore stays exactly one statement no matter how
    many semicolons it contains.

    A trailing statement without a terminating `;` is returned with
    `terminated=False`; fragments that are only whitespace and/or comments are
    dropped, so a buffer's trailing `-- done` comment does not become a
    statement. An unterminated opaque region (the tokenizer's
    `unterminated=True` case) is left as part of one statement running to the
    end of the buffer -- never split in half on a `;` that is actually inside
    it.

    WHY A DATACLASS AND NOT `list[str]`
    -----------------------------------
    Text alone cannot be located in the buffer: two identical statements are
    indistinguishable, and `str.find` would attribute a failure to the wrong
    one. `db/apply.py` attributes a failure by **statement index** plus
    `line_of_position`, which yields a line *within the statement*; turning
    that into the buffer line the console must highlight needs the statement's
    own offset/line, which only the splitter knows. `Statement` carries exactly
    that and nothing else, and `[s.text for s in split_statements(buf)]` is the
    one-expression adapter to `apply_ddl`'s `Sequence[str]`.
    """
    if not text:
        return []

    statements: list[Statement] = []
    current: list[Token] = []

    for token in tokenize(text):
        if token.kind == PUNCT and token.text == ";":
            statements.extend(_finish(text, current, terminated=True))
            current = []
            continue
        current.append(token)

    statements.extend(_finish(text, current, terminated=False))
    return statements


def _finish(text: str, tokens: list[Token], *, terminated: bool) -> list[Statement]:
    """Build the 0-or-1 `Statement` a fragment's tokens amount to.

    Returns an empty list for a fragment carrying no code, so the caller can
    `extend` unconditionally.
    """
    meaningful = [tok for tok in tokens if tok.kind not in _TRIVIAL]
    if not meaningful:
        return []
    # Span from the first non-trivia token (a leading comment is kept: it is
    # part of what the user asked to run and PostgreSQL accepts it) to the last
    # one, dropping only surrounding whitespace and the `;`.
    lead = next(tok for tok in tokens if tok.kind not in {WHITESPACE, NEWLINE})
    tail = next(tok for tok in reversed(tokens) if tok.kind not in {WHITESPACE, NEWLINE})
    return [
        Statement(
            text=text[lead.start : tail.end],
            start=lead.start,
            end=tail.end,
            start_line=lead.start_line,
            start_col=lead.start_col,
            terminated=terminated,
        )
    ]


def statement_at(text: str, pos: int) -> Statement | None:
    """The `Statement` whose scope a caret at 0-based offset `pos` belongs to.

    The last statement starting at or before `pos` -- **not** the one whose
    span *contains* `pos`, because `split_statements` trims trailing
    whitespace and a caret one space past `... where jc. ` would then belong
    to no statement at all. A caret before the first statement belongs to
    none, and gets None.

    Statement selection is a *policy*, not a lookup, which is why it lives
    here beside the splitter rather than being re-derived by each caret-aware
    analyzer (`sql/from_clause.py`, `sql/routine_scope.py`): if the policy
    ever changes, the analyzers must not disagree about which statement the
    caret is in.
    """
    chosen: Statement | None = None
    for statement in split_statements(text):
        if statement.start <= pos:
            chosen = statement
        else:
            break
    return chosen


def classify_statement(sql: str) -> Classification:
    """Classify one statement by its leading keyword, conservatively.

    Returns `"read"`, `"write"`, `"ddl"` or `"unknown"`. Leading whitespace and
    comments are skipped before the keyword is looked at.

    Every uncertain case is biased to `"unknown"` -- never to `"read"` --
    because §18.5 D4 treats `unknown` as `ddl` for its confirmation, and the
    whole point of the gate is that an unclassifiable statement is not waved
    through as harmless. `DO` blocks, `CALL`, `COPY`, `VACUUM`, `ANALYZE`, a
    statement opening with `(`, and empty input are all `"unknown"`.

    Two rulings worth stating outright:

    - **`EXPLAIN` is `read`, `EXPLAIN ANALYZE` is `unknown`.** Plain `EXPLAIN`
      only plans. With `ANALYZE` (bare or inside the option list, and in either
      spelling) it *executes* the statement underneath, which may be a
      `DELETE` or a `CREATE TABLE AS` -- so it is not a read, and the
      classifier refuses to guess which of the other kinds it is.
    - **`WITH` follows its body.** If any of `INSERT`/`UPDATE`/`DELETE`/`MERGE`
      appears anywhere in the statement, it is a `write` (a data-modifying CTE,
      or a `WITH ... DELETE`); otherwise it is a `read`. Bare identifiers that
      happen to spell a write keyword can only push the answer *toward* write,
      which is the safe direction.
    """
    tokens = tokenize(sql)
    code = [tok for tok in tokens if tok.kind not in _SKIPPABLE]
    if not code:
        return UNKNOWN

    head = code[0]
    if head.kind != WORD:
        return UNKNOWN

    leader = head.lowered
    if leader == "with":
        return _classify_with(code)
    if leader == "explain":
        return UNKNOWN if _explain_executes(code) else READ
    if leader in _READ_LEADERS:
        return READ
    if leader in _WRITE_LEADERS:
        return WRITE
    if leader in _DDL_LEADERS:
        return DDL
    return UNKNOWN


def _classify_with(code: list[Token]) -> Classification:
    """`WITH ...` -- write if it modifies data anywhere, else read."""
    for tok in code[1:]:
        if tok.kind == WORD and tok.lowered in _WITH_WRITE_KEYWORDS:
            return WRITE
    return READ


def _explain_executes(code: list[Token]) -> bool:
    """Whether an `EXPLAIN` carries `ANALYZE` and therefore actually runs."""
    return any(tok.kind == WORD and tok.lowered in _ANALYZE_SPELLINGS for tok in code[1:])
