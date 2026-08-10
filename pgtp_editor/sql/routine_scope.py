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

# pgtp_editor/sql/routine_scope.py
"""plpgsql routine scope analysis for local-symbol completion (§18.6, FQ-030
slice 3).

Pure and Qt-free like the rest of `pgtp_editor/sql/` (§5's dependency rule):
given editor text and a caret offset it answers **which local names exist at
the caret and what each one was declared as** -- the routine's own parameters,
its `DECLARE` variables, `%ROWTYPE` / `%TYPE` references, `ALIAS FOR` names,
cursor variables and `FOR`-loop variables -- plus whether the routine is a
trigger function (so `NEW` / `OLD` / `TG_*` are in play).

It knows nothing about a live schema, a `DatabaseSchema` or
`db/schema_index.py`: it reports what the *text* declares. A caller pairs
`LocalSymbol.rowtype_qualified` with `SchemaIndex.known_columns()` to turn
`rec hr.jobcard%ROWTYPE` ... `rec.` into that table's columns, exactly as it
pairs `sql/from_clause.py::TableRef.qualified` with the same call.

REUSE, NOT A SECOND SCANNER
---------------------------
Nothing here scans characters, and nothing here re-derives what another module
already owns:

- **`sql/tokenizer.py`** owns opaque regions and the dollar-quoted body. A
  `DECLARE` inside a `'...'` literal, a `--` line comment, a `/* ... */` block
  comment or a `"quoted identifier"` is not a token in this module's view at
  all, so it can never be mistaken for a declaration. The caret's routine body
  is located with the shared `dollar_body_at()`, the same locator
  `sql/caret_context.py` and `sql/from_clause.py` descend through.
- **`sql/statements.py::statement_at`** owns which statement the caret is in --
  the same call `sql/from_clause.py` makes, so the two analyzers can never
  disagree about the caret's statement.
- **`sql/keywords.py`** stays the single dialect source; the small plpgsql
  declaration-syntax word sets below are reached only through
  `Token.kind` / `Token.lowered`, never through a second lexer.

WHAT IS SUPPORTED, AND WHAT IS DELIBERATELY NOT
-----------------------------------------------
Supported:

- The routine header: `CREATE [OR REPLACE] FUNCTION|PROCEDURE [sch.]name(...)
  RETURNS ...`, its named parameters (with `IN`/`OUT`/`INOUT`/`VARIADIC` modes
  and `DEFAULT`/`=` defaults stepped over) and its return type. `RETURNS
  trigger` / `RETURNS event_trigger` sets `is_trigger`.
- `DECLARE` sections inside the body: `v int`, `v CONSTANT int := 1`,
  `v hr.jobcard%ROWTYPE`, `v hr.jobcard.id%TYPE`, `v ALIAS FOR $1`,
  `c CURSOR (a int) FOR SELECT ...`, `v text := 'x'` (initialisers, `NOT
  NULL`, `COLLATE` and `DEFAULT` clauses are stepped over, not parsed).
- `FOR rec IN ... LOOP` / `FOREACH x IN ARRAY ...` loop variables: the **name**
  is reported (kind `LOOP_VARIABLE`) so it completes; its columns are not
  resolved (see below).
- A bare `DO $$ DECLARE ... BEGIN ... END $$` block, and a buffer that *is*
  just a body with no `CREATE` header at all.
- Nested `DECLARE ... BEGIN ... END` blocks, per the scope rule below.

Deliberately NOT supported -- a partial answer that knows it is partial:

- **A loop variable's fields are not resolved.** `FOR rec IN SELECT * FROM
  hr.jobcard LOOP` would need the query's result shape; the name is offered,
  `rec.` is not expanded. Same ruling as `sql/from_clause.py`'s CTE columns.
- **`%TYPE` is reported, not dereferenced.** `v hr.jobcard.id%TYPE` records the
  path `hr.jobcard.id`; resolving it to `int4` is a catalog question, and the
  catalog is the caller's (`SchemaIndex`'s) half of the job.
- **A composite / domain type's fields are not expanded here.** `v hr.money_t`
  records the type text verbatim; whether that type is composite is again a
  catalog question.
- **Unnamed parameters** (`FUNCTION f(int, text)`) declare no local *name* --
  they are reachable only as `$1`/`$2` -- and are skipped rather than invented.
- **`RECORD` / `refcursor` / `%ROWTYPE` on a one-segment path** yield a symbol
  with no `rowtype_qualified`: a bare `jobcard%ROWTYPE` has no schema, and
  guessing a search path would be inventing a fact (`sql/from_clause.py`'s
  ruling for bare table names, applied unchanged).

THE NESTED-SCOPE BOUNDARY (stated outright)
-------------------------------------------
A `DECLARE` section's symbols are visible at the caret when **the caret is at
or after the `DECLARE` keyword AND at or before the matching `END` of the
`BEGIN` block that section opens**. Block matching walks `BEGIN` / `CASE` /
`IF` / `LOOP` openers and their `END` / `END CASE` / `END IF` / `END LOOP`
closers, so an inner block's variables stop being offered after that block has
closed, while an outer block's stay visible inside it.

When the matching `END` cannot be found -- which is the *normal* state while a
body is being typed, and the state of any malformed input -- the section
degrades to "visible from its `DECLARE` onward" rather than disappearing. That
direction is deliberate: offering a name that has just gone out of scope is a
small annoyance, offering nothing while the author types the block is the
feature not working.
"""
from __future__ import annotations

from dataclasses import dataclass

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

#: Token kinds carrying no code: trivia plus both comment forms.
_SKIPPABLE = frozenset({WHITESPACE, NEWLINE, LINE_COMMENT, BLOCK_COMMENT})

#: Kinds that can spell an identifier.
_NAME_KINDS = frozenset({WORD, QUOTED_IDENT})

#: How many nested dollar-quoted bodies the caret may be descended into --
#: mirrors `from_clause._MAX_BODY_DEPTH` / `caret_context._MAX_BODY_DEPTH`.
_MAX_BODY_DEPTH = 5

# --- symbol kinds ----------------------------------------------------------
PARAMETER = "parameter"  # a routine argument with a name
VARIABLE = "variable"  # a plain DECLARE variable
CURSOR = "cursor"  # `c CURSOR [(args)] FOR ...`
ALIAS = "alias"  # `v ALIAS FOR $1` / `ALIAS FOR NEW`
LOOP_VARIABLE = "loop_variable"  # `FOR rec IN ... LOOP` / `FOREACH x IN ARRAY`

#: The variables PostgreSQL creates inside a `RETURNS trigger` function, with
#: their declared types -- a fact about plpgsql, not about any database, which
#: is why the table lives in this pure module. Order is the order a completion
#: popup should offer them in: the two row variables first, then `TG_*`.
TRIGGER_VARIABLES: tuple[tuple[str, str], ...] = (
    ("NEW", "record"),
    ("OLD", "record"),
    ("TG_OP", "text"),
    ("TG_NAME", "name"),
    ("TG_WHEN", "text"),
    ("TG_LEVEL", "text"),
    ("TG_RELID", "oid"),
    ("TG_RELNAME", "name"),
    ("TG_TABLE_NAME", "name"),
    ("TG_TABLE_SCHEMA", "name"),
    ("TG_NARGS", "integer"),
    ("TG_ARGV", "text[]"),
)

#: Return types that make a routine a trigger function.
_TRIGGER_RETURNS = frozenset({"trigger", "event_trigger"})

#: Parameter modes that may precede a parameter's name.
_PARAM_MODES = frozenset({"in", "out", "inout", "variadic"})

#: Words that open a multi-word *type* name, so a parameter starting with one
#: is unnamed (`f(character varying)` is a type, not `name type`).
_TYPE_LEAD_WORDS = frozenset(
    {
        "character",
        "double",
        "national",
        "time",
        "timestamp",
        "bit",
        "interval",
        "with",
        "without",
        "setof",
    }
)

#: Words that end the `RETURNS ...` clause of a routine header.
_HEADER_TAIL_WORDS = frozenset(
    {
        "as",
        "language",
        "immutable",
        "stable",
        "volatile",
        "strict",
        "called",
        "security",
        "cost",
        "rows",
        "support",
        "set",
        "window",
        "parallel",
        "leakproof",
        "transform",
        "begin",
    }
)

#: Words that end a declaration's *type* text: what follows is an initialiser
#: or a constraint, not part of the type.
_TYPE_TAIL_WORDS = frozenset({"default", "not", "null", "collate"})

#: Block openers tracked when matching a `BEGIN` to its `END`.
_BLOCK_OPENERS = frozenset({"begin", "case", "if", "loop"})

#: Words that may follow `END` to name what it closes (`END IF`, `END LOOP`,
#: `END CASE`). A bare `END` closes the innermost open block.
_END_QUALIFIERS = frozenset({"if", "loop", "case"})


@dataclass(frozen=True)
class LocalSymbol:
    """One local name visible at the caret, exactly as it was declared.

    `type_text` is the type **as written** (`"hr.jobcard%ROWTYPE"`,
    `"numeric(12,2)"`, `"text"`), suitable for a completion popup's display
    column; it is never normalized and never resolved against a catalog.
    """

    #: The declared name, verbatim (a `"Quoted Name"` is unwrapped).
    name: str
    #: `PARAMETER` / `VARIABLE` / `CURSOR` / `ALIAS` / `LOOP_VARIABLE`.
    kind: str
    #: Type as written, or None when the declaration carries none.
    type_text: str | None = None
    #: The dotted path before `%ROWTYPE` (`"hr.jobcard"`), else None.
    rowtype: str | None = None
    #: The dotted path before `%TYPE` (`"hr.jobcard.id"`), else None.
    typeof: str | None = None
    #: What an `ALIAS FOR` names (`"$1"`, `"NEW"`), else None.
    alias_for: str | None = None
    #: `"in"` / `"out"` / `"inout"` / `"variadic"` for a parameter, else None.
    mode: str | None = None
    #: Whether the declaration said `CONSTANT`.
    is_constant: bool = False

    @property
    def rowtype_qualified(self) -> str | None:
        """`"schema.table"` -- the key `SchemaIndex.known_columns()` expects --
        for a two-segment `%ROWTYPE`, else None.

        None for a bare `jobcard%ROWTYPE` (no schema was written and none is
        guessed) and for every non-`%ROWTYPE` declaration.
        """
        if self.rowtype and self.rowtype.count(".") == 1:
            return self.rowtype
        return None


@dataclass(frozen=True)
class RoutineScope:
    """The local names visible at one caret position, plus what routine they
    belong to.

    Empty and falsy when the caret is not in a routine at all -- that is an
    answer, not a failure.
    """

    #: Every visible local name, in source order: parameters first, then
    #: declarations/loop variables in the order they were written.
    symbols: tuple[LocalSymbol, ...] = ()
    #: `"function"` / `"procedure"`, or None when no header was found.
    routine_kind: str | None = None
    #: Schema as written in the routine's name, or None when written bare.
    schema: str | None = None
    #: Bare routine name as written, or None when no header was found.
    name: str | None = None
    #: Return type as written, or None (procedures, or no header).
    returns: str | None = None
    #: Whether this is a trigger function (`RETURNS trigger`), i.e. whether
    #: `TRIGGER_VARIABLES` are in play.
    is_trigger: bool = False
    #: Whether the caret sits inside a dollar-quoted routine body.
    in_body: bool = False

    def __bool__(self) -> bool:
        return bool(self.symbols)

    def __len__(self) -> int:
        return len(self.symbols)

    @property
    def names(self) -> tuple[str, ...]:
        """Every visible local name."""
        return tuple(symbol.name for symbol in self.symbols)

    @property
    def parameters(self) -> tuple[LocalSymbol, ...]:
        """Just the routine's own named parameters."""
        return tuple(s for s in self.symbols if s.kind == PARAMETER)

    def resolve(self, name: str) -> LocalSymbol | None:
        """The symbol `name` denotes, or None if no visible local does.

        Matched case-insensitively (an unquoted identifier folds to lower case
        in PostgreSQL, and §18.6's completion matching is case-insensitive
        throughout). When two visible declarations share a name -- an inner
        block shadowing an outer one -- the **last** one wins, which is the
        innermost, i.e. the one plpgsql itself would use.
        """
        if not name:
            return None
        wanted = name.lower()
        found: LocalSymbol | None = None
        for symbol in self.symbols:
            if symbol.name.lower() == wanted:
                found = symbol
        return found


def analyze_routine_scope(text: str, pos: int) -> RoutineScope:
    """Local plpgsql symbols in scope at 0-based character offset `pos`.

    Returns an empty `RoutineScope` -- never `None`, never an exception -- when
    there is nothing in scope: a caret outside any routine, a routine with no
    declarations, or text too malformed to read. An editor calls this on a
    keystroke, so "no scope" is the only failure mode it may have.

    `pos` is the same 0-based offset convention `sql/tokenizer.py`,
    `sql/caret_context.py` and `sql/from_clause.py` use throughout.
    """
    try:
        return _analyze(text, pos)
    except Exception:  # pragma: no cover - defensive: never raise at a keystroke
        return RoutineScope()


def trigger_variable_names() -> tuple[str, ...]:
    """Just the names from `TRIGGER_VARIABLES`, in the same order."""
    return tuple(name for name, _type in TRIGGER_VARIABLES)


# --- internals -------------------------------------------------------------


def _analyze(text: str, pos: int) -> RoutineScope:
    if not text:
        return RoutineScope()
    pos = max(0, min(pos, len(text)))

    statement = statement_at(text, pos)
    if statement is None:
        return RoutineScope()
    local = max(0, min(pos - statement.start, len(statement.text)))

    tokens = tokenize(statement.text)
    code = [tok for tok in tokens if tok.kind not in _SKIPPABLE]
    header = _parse_header(statement.text, code)

    body_text, body_pos, body_tokens, in_body = _body_at(statement.text, tokens, local)
    symbols = list(header.parameters)
    symbols.extend(_body_symbols(body_text, body_pos, body_tokens))

    return RoutineScope(
        symbols=tuple(symbols),
        routine_kind=header.routine_kind,
        schema=header.schema,
        name=header.name,
        returns=header.returns,
        is_trigger=header.is_trigger,
        in_body=in_body,
    )


def _body_at(
    text: str, tokens: list[Token], pos: int
) -> tuple[str, int, list[Token], bool]:
    """`(body_text, caret_in_body, body_tokens, caret_was_inside_a_dollar_body)`.

    The token list is handed back rather than re-derived by the caller:
    tokenizing a large routine body is the dominant cost of this whole
    analysis, and it runs on every keystroke.

    Descends into the innermost dollar-quoted body containing the caret (the
    shared `dollar_body_at` locator, under the same depth bound the sibling
    analyzers use). When the caret is *not* in one, the statement text itself
    is scanned: a buffer that is nothing but a plpgsql block still has a
    `DECLARE` section worth reading, and any dollar-quoted body elsewhere in
    the statement stays one opaque token, so nothing leaks out of it.
    """
    in_body = False
    for _ in range(_MAX_BODY_DEPTH):
        body = dollar_body_at(tokens, pos)
        if body is None:
            break
        body_text, body_start = body
        text, pos, in_body = body_text, pos - body_start, True
        tokens = tokenize(text)
    return text, pos, tokens, in_body


@dataclass(frozen=True)
class _Header:
    routine_kind: str | None = None
    schema: str | None = None
    name: str | None = None
    returns: str | None = None
    is_trigger: bool = False
    parameters: tuple[LocalSymbol, ...] = ()


def _parse_header(text: str, code: list[Token]) -> _Header:
    """Parse `CREATE ... FUNCTION sch.f(args) RETURNS t` from a statement.

    Returns an empty `_Header` when the statement is not a routine definition
    (a `DO` block, a plain query, a body-only buffer).
    """
    index = _index_of_routine_word(code)
    if index is None:
        return _Header()

    routine_kind = code[index].lowered
    segments, cursor = _dotted_name(code, index + 1)
    parameters: tuple[LocalSymbol, ...] = ()
    if cursor < len(code) and _is_punct(code[cursor], "("):
        close = _matching_paren(code, cursor)
        parameters = _parse_parameters(text, code[cursor + 1 : close])
        cursor = close + 1

    returns = _parse_returns(text, code, cursor)
    return _Header(
        routine_kind=routine_kind,
        schema=segments[-2] if len(segments) >= 2 else None,
        name=segments[-1] if segments else None,
        returns=returns,
        is_trigger=bool(returns) and returns.lower() in _TRIGGER_RETURNS,
        parameters=parameters,
    )


def _index_of_routine_word(code: list[Token]) -> int | None:
    """Index of the `FUNCTION` / `PROCEDURE` word introducing the name.

    Only at paren depth 0 and only when a name-shaped token follows, so
    `DROP FUNCTION`-style text and `RETURNS TABLE(... function ...)` noise
    cannot be mistaken for a definition's header.
    """
    depth = 0
    for index, tok in enumerate(code):
        if tok.kind == PUNCT and tok.text == "(":
            depth += 1
        elif tok.kind == PUNCT and tok.text == ")":
            depth = max(0, depth - 1)
        elif (
            depth == 0
            and tok.kind == WORD
            and tok.lowered in ("function", "procedure")
            and index + 1 < len(code)
            and code[index + 1].kind in _NAME_KINDS
        ):
            return index
    return None


def _parse_returns(text: str, code: list[Token], start: int) -> str | None:
    """The `RETURNS ...` type text of a header, or None when there is none."""
    for index in range(start, len(code)):
        tok = code[index]
        if tok.kind != WORD:
            continue
        if tok.lowered in _HEADER_TAIL_WORDS:
            return None
        if tok.lowered != "returns":
            continue
        end = index + 1
        depth = 0
        while end < len(code):
            item = code[end]
            if _is_punct(item, "("):
                depth += 1
            elif _is_punct(item, ")"):
                depth -= 1
            elif (
                depth == 0
                and item.kind == WORD
                and item.lowered in _HEADER_TAIL_WORDS
            ):
                break
            elif depth == 0 and _is_punct(item, ";"):
                break
            end += 1
        if end <= index + 1:
            return None
        return _slice(text, code[index + 1], code[end - 1])
    return None


def _parse_parameters(text: str, code: list[Token]) -> tuple[LocalSymbol, ...]:
    """Parse a routine's parameter list (the tokens *inside* its parens)."""
    found: list[LocalSymbol] = []
    for item in _split_top_level(code, ","):
        symbol = _parse_parameter(text, item)
        if symbol is not None:
            found.append(symbol)
    return tuple(found)


def _parse_parameter(text: str, code: list[Token]) -> LocalSymbol | None:
    """One `[mode] [name] type [DEFAULT expr]` parameter, or None if unnamed.

    An unnamed parameter (`f(int)`, `f(character varying)`) introduces no local
    name at all -- it is reachable only as `$1` -- so it is skipped rather than
    having its type read as a name.
    """
    mode: str | None = None
    if code and code[0].kind == WORD and code[0].lowered in _PARAM_MODES:
        mode = code[0].lowered
        code = code[1:]
    if not code or code[0].kind not in _NAME_KINDS:
        return None
    if code[0].kind == WORD and code[0].lowered in _TYPE_LEAD_WORDS:
        return None  # `character varying` -- a two-word type, not name + type
    if len(code) < 2 or code[1].kind not in _NAME_KINDS:
        return None  # a lone token, or `int[]` / `sch.type` / `t%TYPE`: no name

    type_tokens = _type_tokens(code[1:])
    return LocalSymbol(
        name=_identifier(code[0]),
        kind=PARAMETER,
        type_text=_slice(text, type_tokens[0], type_tokens[-1]) if type_tokens else None,
        mode=mode,
        **_type_facets(type_tokens),
    )


def _body_symbols(text: str, pos: int, tokens: list[Token]) -> list[LocalSymbol]:
    """Every local symbol a body's text declares that is visible at `pos`.

    `tokens` is `text`'s already-computed token list (see `_body_at`).
    """
    code = [tok for tok in tokens if tok.kind not in _SKIPPABLE]
    if not code:
        return []
    found: list[LocalSymbol] = []
    for index, tok in enumerate(code):
        if tok.kind != WORD:
            continue
        if tok.lowered == "declare":
            found.extend(_declare_section(text, code, index, pos))
        elif tok.lowered in ("for", "foreach"):
            symbol = _loop_variable(code, index, pos)
            if symbol is not None:
                found.append(symbol)
    return found


def _declare_section(
    text: str, code: list[Token], index: int, pos: int
) -> list[LocalSymbol]:
    """The declarations of the `DECLARE` at `index`, if visible at `pos`.

    The section runs from the `DECLARE` to the `BEGIN` that opens its block;
    visibility is the nested-scope boundary stated in the module docstring,
    refined per declaration: a declaration the caret has not reached yet is not
    yet in scope, so completing inside the section itself offers only what is
    already written above the caret.
    """
    begin = _next_word(code, index + 1, "begin")
    end = len(code) if begin is None else begin
    if not _visible(code, code[index], begin, pos):
        return []
    found: list[LocalSymbol] = []
    for item in _split_top_level(code[index + 1 : end], ";"):
        if item[0].start > pos:
            break  # a declaration the caret has not reached yet
        symbol = _parse_declaration(text, item)
        if symbol is not None:
            found.append(symbol)
    return found


def _loop_variable(code: list[Token], index: int, pos: int) -> LocalSymbol | None:
    """The loop variable of a `FOR x IN ...` / `FOREACH x IN ARRAY ...` at
    `index`, if visible at `pos`.

    Only the *name* is reported: what `rec` is a row of comes from the loop's
    query, which this module deliberately does not resolve.
    """
    if index + 2 >= len(code):
        return None
    name_tok, in_tok = code[index + 1], code[index + 2]
    if name_tok.kind not in _NAME_KINDS or name_tok.is_keyword:
        return None
    if in_tok.kind != WORD or in_tok.lowered != "in":
        return None
    loop = _next_word(code, index + 1, "loop")
    if not _visible(code, code[index], loop, pos):
        return None
    return LocalSymbol(name=_identifier(name_tok), kind=LOOP_VARIABLE)


def _visible(
    code: list[Token], opener: Token, block_index: int | None, pos: int
) -> bool:
    """Whether a construct opening at `opener` is in scope at `pos`.

    `block_index` is the index of the `BEGIN` / `LOOP` whose block the
    construct's names live in. See the module docstring's nested-scope
    boundary: in scope from the opener up to that block's matching `END`, and
    -- when the block never closes, the normal state while typing -- from the
    opener onward.
    """
    if pos < opener.start:
        return False
    if block_index is None:
        return True
    end = _matching_end(code, block_index)
    return end is None or pos <= end.end


def _matching_end(code: list[Token], opener_index: int) -> Token | None:
    """The `END` token closing the block opener at `opener_index`, or None.

    Tracks `BEGIN` / `CASE` / `IF` / `LOOP` so an expression `CASE ... END`,
    an `END IF` and an `END LOOP` are not mistaken for the block's own `END`.
    None when the block never closes (an unterminated body, i.e. one still
    being typed).
    """
    depth = 1
    index = opener_index + 1
    while index < len(code):
        tok = code[index]
        if tok.kind == WORD:
            if tok.lowered in _BLOCK_OPENERS:
                depth += 1
            elif tok.lowered == "end":
                nxt = code[index + 1] if index + 1 < len(code) else None
                if nxt is not None and nxt.kind == WORD and nxt.lowered in _END_QUALIFIERS:
                    index += 1  # `END IF` / `END LOOP` / `END CASE`
                depth -= 1
                if depth == 0:
                    return tok
        index += 1
    return None


def _parse_declaration(text: str, code: list[Token]) -> LocalSymbol | None:
    """One `DECLARE`-section declaration, or None when it declares no name."""
    if not code or code[0].kind not in _NAME_KINDS:
        return None
    if code[0].kind == WORD and code[0].is_keyword:
        return None  # not a declaration: stray block/control text
    name = _identifier(code[0])
    rest = code[1:]

    is_constant = bool(rest) and rest[0].kind == WORD and rest[0].lowered == "constant"
    if is_constant:
        rest = rest[1:]

    if rest and rest[0].kind == WORD and rest[0].lowered == "alias":
        target = rest[2:] if len(rest) > 1 and rest[1].lowered == "for" else rest[1:]
        return LocalSymbol(
            name=name,
            kind=ALIAS,
            alias_for=_slice(text, target[0], target[-1]) if target else None,
        )

    if rest and rest[0].kind == WORD and rest[0].lowered == "cursor":
        return LocalSymbol(name=name, kind=CURSOR, type_text="cursor")

    type_tokens = _type_tokens(rest)
    if not type_tokens:
        return None
    return LocalSymbol(
        name=name,
        kind=VARIABLE,
        type_text=_slice(text, type_tokens[0], type_tokens[-1]),
        is_constant=is_constant,
        **_type_facets(type_tokens),
    )


def _type_tokens(code: list[Token]) -> list[Token]:
    """The tokens of a type reference, stopping before any initialiser.

    `:=` / `=` / `DEFAULT` start a value, `NOT NULL` / `COLLATE` a constraint;
    none of them is part of the type.
    """
    depth = 0
    for index, tok in enumerate(code):
        if _is_punct(tok, "("):
            depth += 1
        elif _is_punct(tok, ")"):
            depth -= 1
        elif depth == 0 and tok.kind == PUNCT and tok.text in (":=", "=", ";"):
            return code[:index]
        elif depth == 0 and tok.kind == WORD and tok.lowered in _TYPE_TAIL_WORDS:
            return code[:index]
    return list(code)


def _type_facets(code: list[Token]) -> dict[str, str | None]:
    """`rowtype` / `typeof` for a type reference ending in `%ROWTYPE`/`%TYPE`.

    Both are the dotted path written *before* the `%`, verbatim; neither is
    resolved against a catalog here.
    """
    facets: dict[str, str | None] = {"rowtype": None, "typeof": None}
    if len(code) < 3 or code[-2].kind != PUNCT or code[-2].text != "%":
        return facets
    if code[-1].kind != WORD or code[-1].lowered not in ("rowtype", "type"):
        return facets
    path = _dotted_path(code[:-2])
    if path is None:
        return facets
    facets["rowtype" if code[-1].lowered == "rowtype" else "typeof"] = path
    return facets


def _dotted_path(code: list[Token]) -> str | None:
    """`"a.b.c"` for a dot-separated name run, or None if it is not one."""
    segments: list[str] = []
    for index, tok in enumerate(code):
        if index % 2 == 0:
            if tok.kind not in _NAME_KINDS:
                return None
            segments.append(_identifier(tok))
        elif not _is_punct(tok, "."):
            return None
    return ".".join(segments) if segments else None


def _dotted_name(code: list[Token], index: int) -> tuple[list[str], int]:
    """Parse a dotted identifier at `index`; return its segments and the next
    index."""
    segments: list[str] = []
    if index >= len(code) or code[index].kind not in _NAME_KINDS:
        return segments, index
    segments.append(_identifier(code[index]))
    index += 1
    while (
        index + 1 < len(code)
        and _is_punct(code[index], ".")
        and code[index + 1].kind in _NAME_KINDS
    ):
        segments.append(_identifier(code[index + 1]))
        index += 2
    return segments, index


def _split_top_level(code: list[Token], separator: str) -> list[list[Token]]:
    """Split a token run on a `separator` punctuation token at paren depth 0."""
    parts: list[list[Token]] = []
    current: list[Token] = []
    depth = 0
    for tok in code:
        if _is_punct(tok, "("):
            depth += 1
        elif _is_punct(tok, ")"):
            depth -= 1
        elif depth == 0 and _is_punct(tok, separator):
            parts.append(current)
            current = []
            continue
        current.append(tok)
    parts.append(current)
    return [part for part in parts if part]


def _matching_paren(code: list[Token], index: int) -> int:
    """Index of the `)` closing the `(` at `index` (end of input if unclosed)."""
    depth = 0
    while index < len(code):
        if _is_punct(code[index], "("):
            depth += 1
        elif _is_punct(code[index], ")"):
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return len(code)


def _next_word(code: list[Token], index: int, word: str) -> int | None:
    """Index of the next `word` keyword at or after `index`, else None."""
    for cursor in range(index, len(code)):
        tok = code[cursor]
        if tok.kind == WORD and tok.lowered == word:
            return cursor
    return None


def _is_punct(tok: Token, text: str) -> bool:
    return tok.kind == PUNCT and tok.text == text


def _slice(text: str, first: Token, last: Token) -> str:
    """The verbatim source between two tokens, inclusive."""
    return text[first.start : last.end]


def _identifier(tok: Token) -> str:
    """A name token's identifier text: `"Quoted"` unwrapped, else verbatim."""
    if tok.kind == QUOTED_IDENT and len(tok.text) >= 2 and tok.text.startswith('"'):
        inner = tok.text[1:-1] if tok.text.endswith('"') else tok.text[1:]
        return inner.replace('""', '"')
    return tok.text
