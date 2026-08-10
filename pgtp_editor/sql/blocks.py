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

# pgtp_editor/sql/blocks.py
"""The plpgsql BLOCK-BALANCE RULES, and nothing else (§8, FQ-034).

**Why this module exists: to prevent one fork.** `sql/formatter.py::_Reindenter`
already contained a correct block-balance walk, with the false-positive guards
that keep ordinary DDL from reading as unbalanced plpgsql -- but its frame stack
is *throwaway*: it drives indentation and the refusal verdict and exposes no
spans, so §8's structural-selection ladder could not consume it. The mandate was
therefore to **lift the rule tables, not to re-derive them**: the tables and the
guards live here, `formatter.py` re-aliases the lifted names to the *same*
objects (`_BLOCK_STARTERS = BLOCK_STARTERS`) exactly as it did when
`CLAUSE_STARTERS` moved to `format_config.py` (FQ-033), and `block_spans.py`
consumes them for the span model.

**A rules module must not import the engine it configures**, so nothing here
imports `formatter.py`. The dependency runs the other way.

**Two consumers, one rule set, checked rather than commented.** The anti-fork
guard is a test (`tests/sql/test_block_spans.py`), which feeds §18.4's
adversarial corpus through both consumers and asserts they agree on the block
nesting. A comment saying *"keep these in sync"* would not have.

Everything here is a pure function of a token list -- no Qt, no grammar, no
statement parsing.
"""
from __future__ import annotations

from typing import Sequence

from .tokenizer import NEWLINE, PUNCT, WHITESPACE, Token

# --------------------------------------------------------------------------
# The rule tables. All lowercase; matching goes through `Token.keyword`, which
# is case-insensitive, so a keyword's *classification* lives here while its
# text stays verbatim in the token.
# --------------------------------------------------------------------------

#: Block keywords that start a new line (plpgsql block structure). Wider than
#: `BLOCK_OPENERS`: `else`/`elsif`/`end`/`when` are *not* openers, they are
#: continuations and closers, but they all begin a line.
BLOCK_STARTERS = frozenset(
    {"begin", "declare", "exception", "else", "elsif", "elseif", "end", "when"}
)

#: The four keywords that open a balance-relevant plpgsql block -- the frames an
#: `END` has to close. `declare` and `when` open *soft* frames instead (below):
#: they indent, they can be spanned, and they never make text unbalanced.
BLOCK_OPENERS = frozenset({"begin", "if", "loop", "case"})

#: Soft frame kinds -- indent-only, popped by the next sibling or by the closer
#: of the block they sit in, never a source of an unbalanced-text verdict.
SOFT_FRAMES = frozenset({"declare", "when", "exception"})

#: Balance-relevant frame kinds. Named separately from `BLOCK_OPENERS` because a
#: frame kind is not always spelled like its opener (`case` is opened by `case`,
#: but a `when` frame is opened by `when`).
BLOCK_FRAMES = frozenset({"begin", "if", "loop", "case"})

#: The one keyword that closes a block.
BLOCK_CLOSERS = frozenset({"end"})

#: The closers that are TWO tokens: `END IF` / `END LOOP` / `END CASE`. A bare
#: `END` closes a `BEGIN` or a `CASE` *expression*; anything else is unbalanced.
TWO_TOKEN_CLOSERS = frozenset({"if", "loop", "case"})

#: Tokens after which a bare `LOOP` opens a loop rather than closing a header.
LOOP_STARTERS = frozenset({"then", "begin", "else", "exception", "loop", "declare"})

#: `IF` here is a modifier (`DROP ... IF EXISTS`), not a block opener.
IF_NOT_BLOCK_FOLLOWERS = frozenset({"exists"})

#: `BEGIN` here is transaction control, not a plpgsql block.
BEGIN_NOT_BLOCK_FOLLOWERS = frozenset({"transaction", "work", "isolation"})

#: Per-frame hint for the "you never closed this" refusal message.
UNMATCHED_BLOCK_HINT = {
    "begin": "no matching END",
    "if": "no matching END IF",
    "loop": "no matching END LOOP",
    "case": "no matching END",
}

#: Keywords that end one plpgsql statement and begin the next *without* a `;`.
#: `sql/statements.py` splits on a top-level `;` alone and knows nothing about
#: blocks, which is right for a console Run but too coarse for a span model:
#: inside `BEGIN x := 1; ... END` the first "statement" would start at `BEGIN`,
#: and inside `FOR ... LOOP body` the header and the first body statement would
#: be one. `block_spans.py` clips the statement rung between the nearest of
#: these on either side of the caret.
STATEMENT_BOUNDARY_KEYWORDS = frozenset(
    {
        "begin",
        "declare",
        "exception",
        "then",
        "loop",
        "else",
        "elsif",
        "elseif",
        "when",
        "end",
        "do",
    }
)

#: How far ahead `declare_is_cursor` looks for the `CURSOR` keyword.
_CURSOR_LOOKAHEAD = 8


# --------------------------------------------------------------------------
# Token-stream helpers. `items` is always the shape both consumers walk:
# `[(token, newlines_before), ...]` with whitespace dropped.
# --------------------------------------------------------------------------


def significant_tokens(tokens: Sequence[Token]) -> list[tuple[Token, int]]:
    """Drop whitespace, keeping how many newlines preceded each real token.

    The newline count is not decoration: `declare_is_cursor` tells a plpgsql
    `DECLARE` section from a `DECLARE ... CURSOR` statement by whether the
    keyword ends its line, so the guards need it as much as the formatter's
    line-break decisions do.
    """
    items: list[tuple[Token, int]] = []
    newlines = 0
    for tok in tokens:
        if tok.kind == NEWLINE:
            newlines += 1
        elif tok.kind == WHITESPACE:
            continue
        else:
            items.append((tok, newlines))
            newlines = 0
    return items


def next_keyword(
    items: Sequence[tuple[Token, int]], index: int, offset: int = 1
) -> str | None:
    """The lowercased dialect keyword `offset` significant tokens after `index`."""
    target = index + offset
    if 0 <= target < len(items):
        return items[target][0].keyword
    return None


def next_token(items: Sequence[tuple[Token, int]], index: int) -> Token | None:
    """The next significant token after `index`, or None at the end."""
    target = index + 1
    return items[target][0] if target < len(items) else None


# --------------------------------------------------------------------------
# The six false-positive guards §18.4 enumerates. Each answers exactly one
# question about one token, so both consumers can ask it at the point they
# reach that token without agreeing on any surrounding state.
# --------------------------------------------------------------------------


def if_is_modifier(items: Sequence[tuple[Token, int]], index: int) -> bool:
    """`IF EXISTS` / `IF NOT EXISTS` is a modifier, not a block opener."""
    follower = next_keyword(items, index)
    if follower in IF_NOT_BLOCK_FOLLOWERS:
        return True
    return follower == "not" and next_keyword(items, index, 2) in IF_NOT_BLOCK_FOLLOWERS


def begin_is_transaction(items: Sequence[tuple[Token, int]], index: int) -> bool:
    """`BEGIN;` / `BEGIN TRANSACTION` is transaction control, not a block.

    Told apart by what follows: a plpgsql `BEGIN` is followed by the body, never
    by `;` and never by `TRANSACTION`/`WORK`/`ISOLATION`.
    """
    follower = next_keyword(items, index)
    if follower in BEGIN_NOT_BLOCK_FOLLOWERS:
        return True
    after = next_token(items, index)
    return after is not None and after.kind == PUNCT and after.text == ";"


def loop_opens_block(
    items: Sequence[tuple[Token, int]], index: int, prev_keyword: str | None
) -> bool:
    """Whether the `LOOP` at `index` opens a loop frame.

    The `loop` in `END LOOP` closes one instead -- that is the whole guard, and
    it is why both consumers pass the *previous* keyword in rather than each
    keeping its own idea of what came before.
    """
    return prev_keyword != "end"


def declare_is_cursor(items: Sequence[tuple[Token, int]], index: int) -> bool:
    """`DECLARE c CURSOR FOR ...` is a statement, not a plpgsql section.

    Told apart by layout: a plpgsql DECLARE section ends its line (its
    declarations follow indented below), while the cursor statement runs on from
    `DECLARE` -- so only an inline `CURSOR` before the next `;` counts.
    """
    if index + 1 >= len(items) or items[index + 1][1] > 0:
        return False  # `DECLARE` ends the line: a plpgsql section
    for offset in range(1, _CURSOR_LOOKAHEAD):
        target = index + offset
        if target >= len(items):
            return False
        tok = items[target][0]
        if tok.kind == PUNCT and tok.text == ";":
            return False
        if tok.lowered == "cursor":
            return True
    return False


def when_opens_branch(enclosing_kind: str | None, *, in_exception: bool) -> bool:
    """`WHEN` opens a branch in a `CASE` or in a `BEGIN`'s `EXCEPTION` part.

    `EXIT WHEN done` / `RAISE ... WHEN` are the false positives this excludes:
    neither sits directly inside a `CASE` or an exception part, so neither gets
    a frame. Takes the *facts* about the enclosing block rather than a frame
    object, so the two consumers can hold their stacks in whatever shape suits
    them.
    """
    if enclosing_kind == "case":
        return True
    return enclosing_kind == "begin" and in_exception


def end_closes(follower_keyword: str | None) -> str | None:
    """Which frame kind an `END` explicitly names, or None for a bare `END`.

    A bare `END` closes a `BEGIN` or a `CASE` expression; `END IF`/`END LOOP`/
    `END CASE` close exactly what they name.
    """
    return follower_keyword if follower_keyword in TWO_TOKEN_CLOSERS else None
