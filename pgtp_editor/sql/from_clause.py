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

# pgtp_editor/sql/from_clause.py
"""FROM-clause / alias scope analysis for schema-aware completion (§18.6).

Pure and Qt-free like the rest of `pgtp_editor/sql/` (§5's dependency rule):
given editor text and a caret offset it answers **which tables are in scope at
the caret, and what each alias refers to** -- so `FROM hr.jobcard jc` ... `jc.`
resolves to `hr.jobcard`. It knows nothing about a live schema, a
`DatabaseSchema` or `db/schema_index.py`; the caller pairs a resolved
`TableRef` with `SchemaIndex.known_columns()`.

REUSE, NOT A SECOND SCANNER
---------------------------
Two existing modules do the parts that would otherwise be re-derived here, and
both are reached through their own API rather than re-implemented:

- **`sql/tokenizer.py`** owns opaque regions. A `FROM` inside a `'...'`
  literal, a `--` line comment, a nestable `/* ... */` block comment, a
  `"quoted identifier"` or a `$$ ... $$` / `$tag$ ... $tag$` routine body is
  not a token in this module's view at all, so it can never be mistaken for a
  FROM clause. Nothing here scans characters.
- **`sql/statements.py`** owns statement boundaries *and* the policy for which
  statement a caret belongs to (`statement_at`). Scope is per statement, and a
  buffer holds many; the caret's statement is *asked for* rather than re-cut
  here -- the same call `sql/routine_scope.py` makes, so the two analyzers can
  never disagree about which statement the caret is in.

WHAT IS SUPPORTED, AND WHAT IS DELIBERATELY NOT
-----------------------------------------------
Supported:

- `FROM t`, `FROM t alias`, `FROM t AS alias`, schema-qualified (`FROM hr.t`)
  and bare (`FROM t`); `"quoted"` identifiers in either position.
- Comma-separated FROM lists, and every `JOIN` spelling -- the scan keys on the
  `JOIN` keyword itself, so `LEFT`/`RIGHT`/`FULL`/`INNER`/`CROSS`/`NATURAL`/
  `LATERAL` variants and any `ON` / `USING` clause need no special handling.
- `UPDATE hr.jobcard jc SET ...` -- the same alias shape, same resolution.
- Per-scope nesting: a subquery, a CTE body or a parenthesised join is its own
  scope. A ref is visible at the caret only when the ref's paren nesting is an
  ancestor of the caret's, so statement 1 never leaks into statement 3, an
  inner subquery's alias never leaks outward, and an outer alias *is* visible
  inside its subquery (correct SQL scoping).
- The caret may sit anywhere in its scope, before or after the FROM clause --
  `SELECT j.<caret> FROM hr.jobcard j` resolves, which is the whole point.
- Caret inside a `$$ ... $$` body: the body is analyzed as its own text, so a
  routine body's own FROM clauses resolve for a caret inside it (while staying
  invisible to the enclosing statement).

Deliberately NOT supported -- a partial answer that knows it is partial:

- **A CTE's column list is not resolved.** `WITH x AS (...) SELECT * FROM x`
  yields a `TableRef` named `x` with no schema; nothing here knows that `x` is
  a CTE rather than a table, and its columns come from a query, not a catalog.
- **Derived tables / set-returning function calls** (`FROM (SELECT ...) y`,
  `FROM generate_series(1,10) g`) are recorded with `is_derived=True`: the name
  is known to be *taken* (which is what alias-collision avoidance needs) but no
  catalog table backs it.
- **`INSERT INTO t (...)`** introduces no alias worth resolving and is ignored.
- Search-path resolution: a bare `FROM jobcard` yields `schema=None`. Choosing
  a schema is the caller's job -- guessing one here would be inventing a fact.

TWO ENTRY POINTS, ONE SCAN
--------------------------
`analyze_from_scope` answers *"what does this alias mean?"* -- the completion
question, which needs names only. `analyze_from_items` answers *"where exactly
in the buffer is that FROM item written?"* -- the **rewriting** question
(`sql/expand_select.py`), which needs character spans.

They are two shapes over **one** scan: `analyze_from_scope` is a thin
projection of `analyze_from_items`. The spans live on the new `FromItem`
wrapper and deliberately **not** on `TableRef`: `TableRef` is compared by value
all over the completion tests, and offsets would make two identical references
written in two places unequal for no benefit to the question `TableRef`
answers.

A rewriter must reproduce what the user typed rather than re-render it from the
parsed parts -- `hr.jobcard`, `"HR".jobcard` and `hr . jobcard` all parse to
the same `TableRef` but are three different strings. That is why `FromItem`
carries `name_start`/`name_end`: `text[item.name_start:item.name_end]` is the
verbatim table reference, so the typed schema is preserved structurally rather
than by a rule someone has to remember.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .statements import statement_at
from .tokenizer import (
    BLOCK_COMMENT,
    LINE_COMMENT,
    NEWLINE,
    PUNCT,
    QUOTED_IDENT,
    WHITESPACE,
    WORD,
    Token,
    dollar_body_at,
    tokenize,
)

#: Token kinds carrying no code: trivia plus both comment forms. Dropped before
#: the scan so `FROM /* note */ hr.jobcard jc` reads as `FROM hr.jobcard jc`.
_SKIPPABLE = frozenset({WHITESPACE, NEWLINE, LINE_COMMENT, BLOCK_COMMENT})

#: Keywords that introduce a table reference. `join` takes exactly one item;
#: `from`/`update` take a comma-separated list.
_SINGLE_ITEM_INTRODUCERS = frozenset({"join"})
_LIST_INTRODUCERS = frozenset({"from", "update"})
_INTRODUCERS = _SINGLE_ITEM_INTRODUCERS | _LIST_INTRODUCERS

#: Noise words that may sit *before* a table name and must be stepped over.
_LEADING_NOISE = frozenset({"only", "lateral"})

#: Words that can never be an alias even though `sql/keywords.py` does not list
#: them. This is NOT a second dialect table -- `Token.is_keyword` (the shared
#: `SQL_KEYWORDS` view) is still the primary test; these are the handful of
#: FROM-clause join/sampling noise words that set is missing, and treating one
#: as an alias would silently mis-name a table reference.
_NEVER_AN_ALIAS = frozenset(
    {
        "natural",
        "lateral",
        "only",
        "outer",
        "full",
        "right",
        "left",
        "inner",
        "cross",
        "window",
        "tablesample",
        "ordinality",
        "union",
        "intersect",
        "except",
        "returning",
        "fetch",
        "offset",
        "limit",
    }
)

#: Functions whose argument list spells `FROM` as a separator rather than as a
#: clause (`EXTRACT(YEAR FROM d)`, `SUBSTRING(s FROM 2)`). Without this the
#: token after that `FROM` would be recorded as a table reference.
_FROM_AS_ARGUMENT_SEPARATOR = frozenset(
    {"extract", "substring", "trim", "overlay", "position"}
)

#: How many nested dollar-quoted bodies the caret may be descended into. A
#: bound rather than trust: malformed nesting must not recurse forever.
_MAX_BODY_DEPTH = 5

#: Clause-leading keywords whose position a rewriter needs in order to know
#: where one clause ends and the next begins (`sql/expand_select.py` needs the
#: `SELECT` a column list follows and whether a `WHERE` is already written).
#: Recorded as spans, never interpreted here -- this module still parses only
#: FROM items.
_CLAUSE_WORDS = frozenset(
    {
        "select",
        "where",
        "group",
        "having",
        "order",
        "limit",
        "offset",
        "window",
        "fetch",
        "returning",
        "union",
        "intersect",
        "except",
        "into",
        "set",
        "values",
    }
)


@dataclass(frozen=True)
class TableRef:
    """One table reference in scope, exactly as it was written.

    `name` is what the user types before the dot -- the alias when one was
    written, otherwise the (bare) table name. `schema` is `None` for an
    unqualified table: this module never guesses a search path.

    `is_derived` marks a reference whose name is in scope but which no catalog
    table backs: a subquery (`FROM (SELECT ...) y`), a parenthesised join, or a
    set-returning function call. Callers that resolve columns should skip
    those; callers picking a fresh alias must still treat the name as taken.
    """

    #: Schema as written, or None when the table was written bare.
    schema: str | None
    #: Bare table name as written, or None for a derived table / subquery.
    table: str | None
    #: Alias as written, or None when no alias was given.
    alias: str | None
    #: What the user writes before the dot: `alias or table`.
    name: str
    #: True for a subquery / parenthesised join / function call (see above).
    is_derived: bool = False

    @property
    def qualified(self) -> str | None:
        """`"schema.table"` -- the key `SchemaIndex.known_columns()` expects --
        or None when either half is unknown (bare or derived table)."""
        if self.schema and self.table:
            return f"{self.schema}.{self.table}"
        return None


@dataclass(frozen=True)
class FromScope:
    """The table references visible at one caret position, in source order."""

    refs: tuple[TableRef, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.refs)

    def __len__(self) -> int:
        return len(self.refs)

    @property
    def names(self) -> tuple[str, ...]:
        """Every in-scope reference name (alias, or table when unaliased)."""
        return tuple(ref.name for ref in self.refs)

    def resolve(self, name: str) -> TableRef | None:
        """The reference `name` denotes, or None if nothing in scope does.

        Matched case-insensitively: an unquoted identifier folds to lower case
        in PostgreSQL, and the completion popup's whole convention (§18.6) is
        case-insensitive matching. A `"Quoted"` alias therefore also matches a
        differently-cased spelling -- deliberately lenient, because offering
        the right columns for a mis-cased alias beats offering nothing.
        """
        if not name:
            return None
        wanted = name.lower()
        for ref in self.refs:
            if ref.name.lower() == wanted:
                return ref
        return None


@dataclass(frozen=True)
class FromItem:
    """One `TableRef` **plus where it is written** in the original buffer.

    Every offset is 0-based and absolute in the text handed to
    `analyze_from_items` -- including for a caret inside a `$$ ... $$` body,
    whose inner offsets are rebased on the way out, so a caller may always
    slice the buffer it passed in and never has to know a descent happened.

    Spans, from outermost in:

    - `start`/`end` -- the whole item, from the first character of the table
      name (leading `ONLY`/`LATERAL` noise excluded) through the alias and any
      column-alias list. Replacing `text[start:end]` replaces the item.
    - `name_start`/`name_end` -- the dotted name alone, `hr.jobcard`, without
      the alias. `text[name_start:name_end]` is the **verbatim** reference:
      quoting, casing and any spaces around the dot exactly as typed.
    - `introducer_start`/`introducer_end` -- the `FROM` / `JOIN` / `UPDATE`
      keyword that introduced this item, verbatim too, so a generated clause
      can follow the user's own casing instead of imposing one.

    For a derived item (`is_derived` on `ref`) the name span covers the
    parenthesised group or function call -- there is no catalog name to slice,
    and pointing the span at nothing would be worse than pointing it at what
    stands in that position.
    """

    ref: TableRef
    start: int
    end: int
    name_start: int
    name_end: int
    introducer: str
    introducer_start: int
    introducer_end: int

    def name_text(self, text: str) -> str:
        """The verbatim dotted name, sliced out of the buffer it came from."""
        return text[self.name_start : self.name_end]

    def _shifted(self, delta: int) -> "FromItem":
        if not delta:
            return self
        return replace(
            self,
            start=self.start + delta,
            end=self.end + delta,
            name_start=self.name_start + delta,
            name_end=self.name_end + delta,
            introducer_start=self.introducer_start + delta,
            introducer_end=self.introducer_end + delta,
        )


@dataclass(frozen=True)
class ClauseKeyword:
    """A clause-leading keyword in the caret's scope, with its span.

    `word` is lowercased for comparison; `text` is verbatim, because a
    generated `WHERE` should match the case of the `SELECT`/`FROM` beside it.
    """

    word: str
    text: str
    start: int
    end: int

    def _shifted(self, delta: int) -> "ClauseKeyword":
        if not delta:
            return self
        return replace(self, start=self.start + delta, end=self.end + delta)


@dataclass(frozen=True)
class FromItems:
    """Every located FROM item in scope at a caret, plus the clause landmarks.

    Empty -- never `None`, never an exception -- when nothing is in scope, for
    the same reason `FromScope` is: an editor calls this from a key handler.
    """

    items: tuple[FromItem, ...] = ()
    clauses: tuple[ClauseKeyword, ...] = ()
    #: Span of the statement the caret belongs to, absolute. Equal (0, 0) when
    #: there is no statement at all.
    statement_start: int = 0
    statement_end: int = 0

    def __bool__(self) -> bool:
        return bool(self.items)

    def __len__(self) -> int:
        return len(self.items)

    @property
    def scope(self) -> FromScope:
        """The name-only view -- exactly what `analyze_from_scope` returns."""
        return FromScope(tuple(_dedupe([item.ref for item in self.items])))

    def clause(self, word: str) -> ClauseKeyword | None:
        """The first in-scope occurrence of clause keyword `word`, or None."""
        wanted = word.lower()
        for clause in self.clauses:
            if clause.word == wanted:
                return clause
        return None

    def clause_after(self, pos: int, word: str) -> ClauseKeyword | None:
        """The first in-scope `word` starting at or after `pos`, or None."""
        wanted = word.lower()
        for clause in self.clauses:
            if clause.word == wanted and clause.start >= pos:
                return clause
        return None


def analyze_from_items(text: str, pos: int) -> FromItems:
    """The FROM items in scope at `pos`, each with its span in `text`.

    The span-carrying sibling of `analyze_from_scope`, for callers that must
    **rewrite** a FROM item rather than merely resolve an alias. Same scoping
    rules, same tokenizer, same statement policy -- one scan, two shapes (see
    the module docstring).

    Returns an empty `FromItems` for anything unreadable; it never raises.
    """
    try:
        return _analyze(text, pos, depth=0, base=0)
    except Exception:  # pragma: no cover - defensive: never raise at a keystroke
        return FromItems()


def analyze_from_scope(text: str, pos: int) -> FromScope:
    """Table references in scope at 0-based character offset `pos` in `text`.

    Returns an empty `FromScope` -- never `None`, never an exception -- when
    there is nothing in scope: a caret before the first statement, a statement
    with no FROM clause, or SQL too malformed to read. An editor calls this on
    a keystroke, so "no scope" is the only failure mode it may have.

    `pos` is the same 0-based offset convention `sql/tokenizer.py`,
    `sql/caret_context.py` and `sql/formatter.py` use throughout.
    """
    return analyze_from_items(text, pos).scope


# --- internals -------------------------------------------------------------


def _analyze(text: str, pos: int, *, depth: int, base: int) -> FromItems:
    if not text:
        return FromItems()
    pos = max(0, min(pos, len(text)))

    statement = statement_at(text, pos)
    if statement is None:
        return FromItems()
    local = max(0, min(pos - statement.start, len(statement.text)))

    tokens = tokenize(statement.text)

    body = dollar_body_at(tokens, local)
    if body is not None:
        if depth >= _MAX_BODY_DEPTH:
            return FromItems()
        body_text, body_offset = body
        return _analyze(
            body_text,
            local - body_offset,
            depth=depth + 1,
            base=base + statement.start + body_offset,
        )

    delta = base + statement.start
    code = [tok for tok in tokens if tok.kind not in _SKIPPABLE]
    if not code:
        return FromItems(statement_start=delta, statement_end=delta)

    # `_paren_paths` is computed once and shared: items and clauses are two
    # readings of the same scan, and the caret path is a keystroke-frequency
    # code path that must not grow a second pass over the token stream.
    paths = _paren_paths(code)
    caret_path = _caret_paren_path(code, local)

    def in_scope(path: tuple[int, ...]) -> bool:
        return path == caret_path[: len(path)]

    items = tuple(
        item._shifted(delta)
        for path, item in _collect_items(code, paths)
        if in_scope(path)
    )
    clauses = tuple(
        clause._shifted(delta)
        for path, clause in _collect_clauses(code, paths)
        if in_scope(path)
    )
    return FromItems(
        items=items,
        clauses=clauses,
        statement_start=delta,
        statement_end=delta + len(statement.text),
    )


def _caret_paren_path(code: list[Token], pos: int) -> tuple[int, ...]:
    """The stack of open-paren token indices enclosing `pos`.

    Identifies the caret's scope: a subquery, CTE body or parenthesised join
    is a paren group, so two positions share a scope exactly when they share
    this path.
    """
    stack: list[int] = []
    for index, tok in enumerate(code):
        if tok.start >= pos:
            break
        if tok.kind == PUNCT and tok.text == "(":
            stack.append(index)
        elif tok.kind == PUNCT and tok.text == ")" and stack:
            stack.pop()
    return tuple(stack)


def _paren_paths(code: list[Token]) -> list[tuple[int, ...]]:
    """The enclosing paren path of every token, by index."""
    paths: list[tuple[int, ...]] = []
    stack: list[int] = []
    for index, tok in enumerate(code):
        if tok.kind == PUNCT and tok.text == ")" and stack:
            stack.pop()
            paths.append(tuple(stack))
            continue
        paths.append(tuple(stack))
        if tok.kind == PUNCT and tok.text == "(":
            stack.append(index)
    return paths


def _collect_clauses(
    code: list[Token], paths: list[tuple[int, ...]]
) -> list[tuple[tuple[int, ...], ClauseKeyword]]:
    """Every `(scope_path, ClauseKeyword)` landmark the token stream declares."""
    return [
        (
            paths[index],
            ClauseKeyword(tok.lowered, tok.text, tok.start, tok.end),
        )
        for index, tok in enumerate(code)
        if tok.kind == WORD and tok.lowered in _CLAUSE_WORDS
    ]


def _collect_items(
    code: list[Token], paths: list[tuple[int, ...]]
) -> list[tuple[tuple[int, ...], FromItem]]:
    """Every `(scope_path, FromItem)` the token stream declares.

    The scan visits *every* index rather than skipping over what an item
    consumed, so a `FROM` nested inside a subquery that a preceding item
    swallowed is still found -- each introducer is parsed independently and
    tagged with its own paren path.
    """
    found: list[tuple[tuple[int, ...], FromItem]] = []
    for index, tok in enumerate(code):
        if tok.kind != WORD:
            continue
        leader = tok.lowered
        if leader not in _INTRODUCERS:
            continue
        path = paths[index]
        if _is_function_argument_from(code, path, leader):
            continue
        cursor = index + 1
        while cursor < len(code):
            item, cursor = _parse_item(code, cursor, tok)
            if item is not None:
                found.append((path, item))
            if (
                leader in _LIST_INTRODUCERS
                and cursor < len(code)
                and code[cursor].kind == PUNCT
                and code[cursor].text == ","
            ):
                cursor += 1
                continue
            break
    return found


def _is_function_argument_from(
    code: list[Token], path: tuple[int, ...], leader: str
) -> bool:
    """Whether this `FROM` is `EXTRACT(YEAR FROM d)`-style argument syntax."""
    if leader != "from" or not path:
        return False
    open_index = path[-1]
    callee = open_index - 1
    return (
        callee >= 0
        and code[callee].kind == WORD
        and code[callee].lowered in _FROM_AS_ARGUMENT_SEPARATOR
    )


def _parse_item(
    code: list[Token], i: int, introducer: Token
) -> tuple[FromItem | None, int]:
    """Parse one FROM-list item at `i`; return it and the next index.

    Spans come straight off the tokens consumed, so they are exact by
    construction rather than re-found by searching the text for a name.
    """
    n = len(code)

    def built(
        ref: TableRef, first: int, last: int, name_first: int, name_last: int
    ) -> FromItem:
        return FromItem(
            ref=ref,
            start=code[first].start,
            end=code[last].end,
            name_start=code[name_first].start,
            name_end=code[name_last].end,
            introducer=introducer.lowered,
            introducer_start=introducer.start,
            introducer_end=introducer.end,
        )

    while i < n and code[i].kind == WORD and code[i].lowered in _LEADING_NOISE:
        i += 1
    if i >= n:
        return None, i

    first_index = i
    tok = code[i]

    # `FROM (SELECT ...) y` / `FROM (a JOIN b) c` -- a derived scope. The group
    # is stepped over here; its own contents are found by the outer scan.
    if tok.kind == PUNCT and tok.text == "(":
        after = _skip_group(code, i)
        group_last = max(first_index, after - 1)
        alias, after = _parse_alias(code, after)
        if alias is None:
            return None, after
        ref = TableRef(None, None, alias, alias, is_derived=True)
        return built(ref, first_index, after - 1, first_index, group_last), after

    if tok.kind not in (WORD, QUOTED_IDENT):
        return None, i
    if tok.kind == WORD and tok.is_keyword:
        return None, i  # `FROM WHERE ...` -- malformed, not a table name

    segments = [_identifier(tok)]
    i += 1
    while (
        i + 1 < n
        and code[i].kind == PUNCT
        and code[i].text == "."
        and code[i + 1].kind in (WORD, QUOTED_IDENT)
    ):
        segments.append(_identifier(code[i + 1]))
        i += 2

    name_last = i - 1

    # A dangling dot (`FROM pr.<caret>`) is a name still being typed, not a
    # finished reference -- recording `pr` here would make a half-typed schema
    # masquerade as an in-scope table for the very keystroke that types it.
    if i < n and code[i].kind == PUNCT and code[i].text == ".":
        return None, i + 1

    # `FROM generate_series(1, 10) g` -- a set-returning function, not a table.
    if i < n and code[i].kind == PUNCT and code[i].text == "(":
        i = _skip_group(code, i)
        call_last = max(name_last, i - 1)
        alias, i = _parse_alias(code, i)
        name = alias or segments[-1]
        ref = TableRef(None, None, alias, name, is_derived=True)
        return built(ref, first_index, i - 1, first_index, call_last), i

    alias, i = _parse_alias(code, i)
    # A column-alias list (`AS t(a, b)`) follows the alias; step over it.
    if alias is not None and i < n and code[i].kind == PUNCT and code[i].text == "(":
        i = _skip_group(code, i)

    table = segments[-1]
    schema = segments[-2] if len(segments) >= 2 else None
    ref = TableRef(schema, table, alias, alias or table)
    return built(ref, first_index, i - 1, first_index, name_last), i


def _parse_alias(code: list[Token], i: int) -> tuple[str | None, int]:
    """Parse an optional `[AS] alias` at `i`; return it and the next index."""
    n = len(code)
    if i < n and code[i].kind == WORD and code[i].lowered == "as":
        if i + 1 < n and code[i + 1].kind in (WORD, QUOTED_IDENT):
            return _identifier(code[i + 1]), i + 2
        return None, i + 1
    if i < n and code[i].kind == QUOTED_IDENT:
        return _identifier(code[i]), i + 1
    if (
        i < n
        and code[i].kind == WORD
        and not code[i].is_keyword
        and code[i].lowered not in _NEVER_AN_ALIAS
        and not code[i].text[0].isdigit()
    ):
        return code[i].text, i + 1
    return None, i


def _skip_group(code: list[Token], i: int) -> int:
    """Index just past the `(` group opening at `i` (end of input if unclosed)."""
    depth = 0
    n = len(code)
    while i < n:
        tok = code[i]
        if tok.kind == PUNCT and tok.text == "(":
            depth += 1
        elif tok.kind == PUNCT and tok.text == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _identifier(tok: Token) -> str:
    """A name token's identifier text: `"Quoted"` unwrapped, else verbatim."""
    if tok.kind == QUOTED_IDENT and len(tok.text) >= 2 and tok.text.startswith('"'):
        inner = tok.text[1:-1] if tok.text.endswith('"') else tok.text[1:]
        return inner.replace('""', '"')
    return tok.text


def _dedupe(refs: list[TableRef]) -> list[TableRef]:
    """Drop later references repeating a name already in scope, keeping order."""
    seen: set[str] = set()
    unique: list[TableRef] = []
    for ref in refs:
        key = ref.name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique
