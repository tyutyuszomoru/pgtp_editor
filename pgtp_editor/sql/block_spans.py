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

# pgtp_editor/sql/block_spans.py
"""The structural SPAN model over plpgsql text -- Qt-free (§8, FQ-034).

`structure_chain(text, pos)` returns every structural span containing `pos`,
**smallest first**, as `StructureSpan`s carrying both an `inner` (delimiters
excluded) and an `outer` (delimiters included) range.

**Why a CHAIN and not a `next_larger(selection)` step function.** §8's
expand/shrink ladder is one caller and only needs "the next bigger thing", but
FQ-032's deferred vim text objects need two things a step function cannot give:
*"the span of kind K at the caret"*, and vim's `i` / `a` distinction (`i(` vs
`a(`), which is exactly the `inner` / `outer` pair. Both are derivable from a
chain; neither is derivable from `next_larger`. Shaping the model for the ladder
alone is how the second caller ends up with a second walk -- so the chain is the
published entry point and the ladder is a *filter* over it
(`ladder_candidates` / `expand_target` / `shrink_target` below).

**Nothing here scans characters.** Tokens and opacity come from
`sql/tokenizer.py`, statement boundaries from `sql/statements.py`, clause
starters from `sql/format_config.py`, and the block-balance rules and their six
false-positive guards from `sql/blocks.py`. That is the whole point of the
module split: the ladder's paren rung is **token-level**, so a `(` inside a
string literal or a comment is not a bracket (which is exactly where it differs
from `ui/code_editor.py::enclosing_bracket_span`, the character-level scan
`Ctrl+Shift+B` still uses because it also serves PHP and JS tabs).

**A `$$` body is DESCENDED INTO; a string or a comment is ONE rung.** That is
`sql/caret_context.py`'s existing rule (BUG-041) adopted rather than
re-decided: a routine body is plpgsql and is the entire point of the feature,
while a literal or a comment has no structure to climb.

**It never raises and never guesses.** Unreadable or unbalanced text yields the
spans it *could* close and nothing more: an unclosed `BEGIN` contributes no
span, so the ladder tops out one rung lower instead of selecting a range whose
end was invented. Empty or structure-less input yields `()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from . import blocks
from .format_config import CLAUSE_STARTERS
from .statements import statement_at
from .tokenizer import (
    DOLLAR_STRING,
    PUNCT,
    Token,
    dollar_body_at,
    tokenize,
)

#: The `kind` values `structure_chain` can emit. Strings rather than an enum,
#: matching the codebase's existing `kind: str` convention (`db/ddl_buffer.py`).
SPAN_KINDS = (
    "word",
    "paren",
    "bracket",
    "clause",
    "statement",
    "when",
    "case",
    "if",
    "loop",
    "begin",
    "declare",
    "exception",
    "dollar_body",
)

#: The kinds whose `inner` is a rung of its own, so the ladder stops there
#: *before* taking the delimited whole -- §8's rung 2, "inner first, then outer
#: (two presses)". Every other kind contributes its `outer` only: `BEGIN`'s
#: keywords are part of what a reader means by "the block", whereas the
#: parentheses around an argument list are not part of the argument list.
_TWO_RUNG_KINDS = frozenset({"paren", "bracket", "dollar_body"})

#: Bracket punctuation, opener -> (closer, frame kind).
_BRACKETS = {"(": (")", "paren"), "[": ("]", "bracket")}


@dataclass(frozen=True)
class StructureSpan:
    """One structural unit containing the caret.

    `outer` includes the delimiters / keywords (`BEGIN`...`END`, `(`...`)`,
    `WHEN`...); `inner` excludes them and equals `outer` for the kinds that have
    no delimiters (`word`, `clause`, `statement`). Both are `(start, end)`
    half-open character offsets in the coordinates of the `text` passed in.

    `depth` is the span's nesting depth *along this chain*: 0 for the outermost
    member, one more per level inward. It is derived from the chain, never from
    the walker's frame stack, so a chain that skipped an unclosed block does not
    leave a hole in the numbering.
    """

    kind: str
    outer: tuple[int, int]
    inner: tuple[int, int]
    depth: int


# --------------------------------------------------------------------------
# the walk
# --------------------------------------------------------------------------


@dataclass
class _OpenFrame:
    kind: str
    opener: Token
    index: int
    in_exception: bool = False


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    """`(start, end)` with surrounding whitespace dropped.

    A span that ends where its next sibling begins (a `WHEN` branch, a `DECLARE`
    section) would otherwise carry the newline and indentation in front of that
    sibling, and a selection with a trailing blank line reads as a mistake.
    """
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _when_here(block: "_OpenFrame | None") -> bool:
    """`blocks.when_opens_branch` asked about an open frame rather than facts."""
    return blocks.when_opens_branch(
        block.kind if block is not None else None,
        in_exception=bool(block is not None and block.in_exception),
    )


def _frame_spans(text: str, items: Sequence[tuple[Token, int]]) -> list[tuple[str, tuple[int, int], tuple[int, int]]]:
    """Every *closed* frame in `items`, as `(kind, outer, inner)`.

    A single pass with the same frame stack `formatter.py::_Reindenter` keeps,
    reading the same tables and the same guards out of `blocks.py` -- the two
    walks are verified to agree on nesting by `tests/sql/test_block_spans.py`
    against §18.4's adversarial corpus, which is what keeps one rule set from
    becoming two.

    An unclosed frame contributes NOTHING: it has no end that is not invented.
    """
    spans: list[tuple[str, tuple[int, int], tuple[int, int]]] = []
    stack: list[_OpenFrame] = []
    prev_keyword: str | None = None

    def close(frame: _OpenFrame, outer_end: int, inner_end: int) -> None:
        outer = _trim(text, frame.opener.start, outer_end)
        inner = _trim(text, frame.opener.end, inner_end)
        if outer[1] > outer[0]:
            spans.append((frame.kind, outer, inner))

    def enclosing_block() -> _OpenFrame | None:
        for frame in reversed(stack):
            if frame.kind in blocks.BLOCK_FRAMES:
                return frame
        return None

    def in_if_context() -> bool:
        block = enclosing_block()
        if block is None:
            return False
        return block.kind == "if" or (block.kind == "begin" and block.in_exception)

    def pop_soft(boundary: int) -> None:
        """Close every soft frame on top of the stack at `boundary`.

        Mirrors `_Reindenter._pop_soft`, which also pops the whole run: a
        `WHEN` branch inside an `EXCEPTION` part inside a `BEGIN` puts two soft
        frames above the block frame the `END` has to reach.
        """
        while stack and stack[-1].kind in blocks.SOFT_FRAMES:
            close(stack.pop(), boundary, boundary)

    def pop_when(boundary: int) -> None:
        if stack and stack[-1].kind == "when":
            close(stack.pop(), boundary, boundary)

    for index, (tok, _newlines) in enumerate(items):
        keyword = tok.keyword

        # --- closers, before the opener half of the same token is considered --
        if tok.kind == PUNCT and tok.text in (")", "]"):
            expected = "paren" if tok.text == ")" else "bracket"
            pop_soft(tok.start)
            if stack and stack[-1].kind == expected:
                frame = stack.pop()
                close(frame, tok.end, tok.start)
        elif keyword == "end":
            pop_soft(tok.start)
            follower = blocks.next_token(items, index)
            closes = blocks.end_closes(blocks.next_keyword(items, index))
            outer_end = follower.end if closes and follower is not None else tok.end
            if stack and stack[-1].kind in blocks.BLOCK_FRAMES:
                frame = stack[-1]
                if closes is None:
                    # A bare END closes a BEGIN or a CASE *expression*; against
                    # an IF or a LOOP it is unbalanced text, and the frame is
                    # dropped without a span rather than guessed shut.
                    stack.pop()
                    if frame.kind in ("begin", "case"):
                        close(frame, outer_end, tok.start)
                elif closes == frame.kind:
                    stack.pop()
                    close(frame, outer_end, tok.start)
                else:
                    stack.pop()  # `END LOOP` against an open IF: unbalanced
        elif keyword == "when" and _when_here(enclosing_block()):
            pop_when(tok.start)
        elif keyword in ("else", "elsif", "elseif"):
            if not in_if_context():
                pop_when(tok.start)  # a CASE expression's ELSE ends the branch
        elif keyword == "exception":
            block = enclosing_block()
            if block is not None and block.kind == "begin":
                block.in_exception = True
        elif keyword == "begin" and stack and stack[-1].kind == "declare":
            close(stack.pop(), tok.start, tok.start)  # the DECLARE section ends

        # --- openers ------------------------------------------------------
        if tok.kind == PUNCT and tok.text in _BRACKETS:
            stack.append(_OpenFrame(kind=_BRACKETS[tok.text][1], opener=tok, index=index))
        elif keyword is not None and prev_keyword != "end":
            block = enclosing_block()
            if keyword == "begin":
                if not blocks.begin_is_transaction(items, index):
                    stack.append(_OpenFrame(kind="begin", opener=tok, index=index))
            elif keyword == "if":
                if not blocks.if_is_modifier(items, index):
                    stack.append(_OpenFrame(kind="if", opener=tok, index=index))
            elif keyword == "loop":
                if blocks.loop_opens_block(items, index, prev_keyword):
                    stack.append(_OpenFrame(kind="loop", opener=tok, index=index))
            elif keyword == "case":
                stack.append(_OpenFrame(kind="case", opener=tok, index=index))
            elif keyword == "declare":
                if not blocks.declare_is_cursor(items, index):
                    stack.append(_OpenFrame(kind="declare", opener=tok, index=index))
            elif keyword == "exception":
                # NOT a frame in the reindenter (there it only dedents and marks
                # the BEGIN), but the exception part IS a structural unit a
                # reader means to select, so the span model gives it a soft
                # frame. Soft, so it can never change a balance verdict.
                stack.append(_OpenFrame(kind="exception", opener=tok, index=index))
            elif keyword == "when" and _when_here(block):
                stack.append(_OpenFrame(kind="when", opener=tok, index=index))
            elif keyword == "else" and not in_if_context() and block is not None:
                stack.append(_OpenFrame(kind="when", opener=tok, index=index))

        prev_keyword = keyword

    return spans


def _word_span(items: Sequence[tuple[Token, int]], pos: int) -> tuple[int, int] | None:
    """The token under `pos`, or None where `pos` sits on punctuation only.

    A token strictly containing `pos` wins; failing that the token *ending* at
    `pos` (the caret just after a word one has finished typing), then the token
    starting there. Punctuation is never a rung -- selecting a lone `,` is not a
    structural unit, and the paren rung already covers the brackets.
    """
    ending: tuple[int, int] | None = None
    starting: tuple[int, int] | None = None
    for tok, _newlines in items:
        if tok.kind == PUNCT:
            continue
        if tok.start < pos < tok.end:
            return tok.start, tok.end
        if tok.end == pos:
            ending = (tok.start, tok.end)
        elif tok.start == pos and starting is None:
            starting = (tok.start, tok.end)
    return ending or starting


def _clip(span: tuple[int, int], bounds: tuple[int, int] | None) -> tuple[int, int]:
    if bounds is None:
        return span
    return max(span[0], bounds[0]), min(span[1], bounds[1])


def _depth_zero(
    items: Sequence[tuple[Token, int]], start: int, end: int
) -> list[Token]:
    """The tokens of `items` inside `[start, end)` at bracket depth 0.

    Depth matters for both callers: a `WHERE` inside a subselect belongs to that
    subselect, and a `THEN` inside a `CASE` *expression* in an argument list is
    not a statement boundary of the statement around it.
    """
    depth = 0
    result: list[Token] = []
    for tok, _newlines in items:
        if tok.end <= start or tok.start >= end:
            continue
        if tok.kind == PUNCT and tok.text in _BRACKETS:
            depth += 1
        elif tok.kind == PUNCT and tok.text in (")", "]"):
            depth = max(depth - 1, 0)
        elif depth == 0:
            result.append(tok)
    return result


def _boundary_bounds(
    items: Sequence[tuple[Token, int]], pos: int, region: tuple[int, int]
) -> tuple[int, int]:
    """`region` narrowed to the nearest statement boundary on either side of `pos`.

    See `blocks.STATEMENT_BOUNDARY_KEYWORDS` for why this exists: `THEN`, `LOOP`,
    `BEGIN` and friends end a statement without a `;`, and `sql/statements.py`
    deliberately does not know that. Without the narrowing the statement rung
    inside a `FOR ... LOOP` would swallow the loop header together with the first
    body statement -- a rung that is not the unit a reader means.
    """
    low, high = region
    for tok in _depth_zero(items, low, high):
        if tok.keyword not in blocks.STATEMENT_BOUNDARY_KEYWORDS:
            continue
        if tok.end <= pos:
            low = max(low, tok.end)
        elif tok.start >= pos:
            high = min(high, tok.start)
            break
    return low, high


def _statement_and_clause(
    text: str,
    items: Sequence[tuple[Token, int]],
    pos: int,
    bounds: tuple[int, int] | None,
    *,
    include_statement: bool = True,
) -> list[tuple[str, tuple[int, int], tuple[int, int]]]:
    """The statement rung and -- only where a clause starter exists -- the clause.

    **The clause rung is SPARSE, by owner ruling (`DEC-260810164602`): a rung may
    be ABSENT but never PRESENT-AND-EMPTY.** In `RAISE NOTICE '...', x;` or a bare
    assignment there is no `SELECT`/`FROM`/`WHERE` to anchor on, so no clause span
    is emitted at all and the press that would have taken it goes straight to the
    statement. A press that fires and changes nothing is worse than one rung fewer.

    `bounds` is the innermost enclosing block's inner range. Clipping to it is
    what keeps the rung honest inside a routine body: `split_statements` splits on
    a top-level `;` and knows nothing about `BEGIN`, so in `BEGIN x := 1; ... END`
    the first "statement" would otherwise start at `BEGIN`.
    """
    found: list[tuple[str, tuple[int, int], tuple[int, int]]] = []
    statement = statement_at(text, pos)
    if statement is None or not statement.start <= pos <= statement.end:
        return found
    start, end = _clip((statement.start, statement.end), bounds)
    start, end = _clip((start, end), _boundary_bounds(items, pos, (start, end)))
    start, end = _trim(text, start, end)
    if not start <= pos <= end or end <= start:
        return found
    if include_statement:
        found.append(("statement", (start, end), (start, end)))

    # Clause starters at bracket depth 0 inside the statement -- a `WHERE`
    # inside a subselect belongs to that subselect, not to this clause.
    starters = [
        tok for tok in _depth_zero(items, start, end) if tok.keyword in CLAUSE_STARTERS
    ]
    current = None
    following = None
    for tok in starters:
        if tok.start <= pos:
            current = tok
        elif following is None:
            following = tok
    if current is None:
        return found  # sparse: no anchor, no rung
    clause = _trim(text, current.start, following.start if following else end)
    if clause[0] <= pos <= clause[1] and clause[1] > clause[0]:
        found.append(("clause", clause, clause))
    return found


def structure_chain(text: str, pos: int) -> tuple[StructureSpan, ...]:
    """Every structural span containing `pos`, smallest first (see module docs).

    `pos` is a 0-based character offset and is clamped into `text`, so a caller
    holding a stale caret gets a chain rather than an exception.
    """
    if not text:
        return ()
    pos = max(0, min(pos, len(text)))
    tokens = tokenize(text)
    candidates: list[tuple[str, tuple[int, int], tuple[int, int]]] = []

    # --- descend into a `$$ ... $$` routine body first (BUG-041's rule) ----
    body = dollar_body_at(tokens, pos)
    if body is not None:
        body_text, body_start = body
        for span in structure_chain(body_text, pos - body_start):
            candidates.append(
                (
                    span.kind,
                    (span.outer[0] + body_start, span.outer[1] + body_start),
                    (span.inner[0] + body_start, span.inner[1] + body_start),
                )
            )
        for tok in tokens:
            if tok.kind == DOLLAR_STRING and tok.start <= pos <= tok.end:
                candidates.append(
                    (
                        "dollar_body",
                        (tok.start, tok.end),
                        _trim(text, body_start, body_start + len(body_text)),
                    )
                )
                break

    items = blocks.significant_tokens(tokens)
    if body is None:
        word = _word_span(items, pos)
        if word is not None:
            candidates.append(("word", word, word))

    frames = [
        (kind, outer, inner)
        for kind, outer, inner in _frame_spans(text, items)
        if outer[0] <= pos <= outer[1]
    ]
    candidates.extend(frames)

    # The statement/clause rungs are resolved once per enclosing SCOPE, and there
    # are two kinds:
    #
    # * the innermost enclosing BLOCK -- so `BEGIN x := 1; ... END` does not make
    #   the first statement start at `BEGIN` (`sql/statements.py` splits on a
    #   top-level `;` and knows nothing about blocks, which is right for a console
    #   Run and too coarse here);
    # * the innermost enclosing BRACKET -- so a subselect's own `WHERE` is a rung.
    #   Without it the only clause in reach would be the *outer* statement's,
    #   which is a rung the caret is not in the scope of.
    #
    # Both are asked, and `_as_chain` nests and de-duplicates the answers -- so a
    # subselect whose statement rung coincides with the bracket's own inner range
    # is one press, not two.
    def innermost(kinds):
        scope = min(
            (f for f in frames if f[0] in kinds),
            key=lambda f: f[1][1] - f[1][0],
            default=None,
        )
        return scope[2] if scope is not None else None

    bracket_scope = innermost(("paren", "bracket"))
    if bracket_scope is not None:
        # Clause only: a bracket's contents are not a statement, and the "whole
        # contents" rung is already the bracket's own `inner`.
        candidates.extend(
            _statement_and_clause(
                text, items, pos, bracket_scope, include_statement=False
            )
        )
    candidates.extend(
        _statement_and_clause(
            text,
            items,
            pos,
            innermost(("begin", "if", "loop", "case", "when", "declare", "exception")),
        )
    )

    return _as_chain(candidates)


def _as_chain(
    candidates: Sequence[tuple[str, tuple[int, int], tuple[int, int]]]
) -> tuple[StructureSpan, ...]:
    """Sort candidates smallest-first and keep only a strictly nested chain.

    Two candidates with the same `outer` are one rung, and the first one wins --
    which is why `_statement_and_clause` appends the statement before the clause:
    where a statement *is* one clause (`select 1`), the chain says `statement`.
    Anything not nested inside the next member is dropped rather than reordered:
    the ladder's contract is that every press contains the last one.
    """
    ordered = sorted(candidates, key=lambda c: (c[1][1] - c[1][0], c[1][0]))
    kept: list[tuple[str, tuple[int, int], tuple[int, int]]] = []
    for kind, outer, inner in ordered:
        if outer[1] <= outer[0]:
            continue
        if kept:
            previous = kept[-1][1]
            if outer == previous:
                continue
            if not (outer[0] <= previous[0] and outer[1] >= previous[1]):
                continue
        kept.append((kind, outer, inner))
    total = len(kept)
    return tuple(
        StructureSpan(kind=kind, outer=outer, inner=inner, depth=total - 1 - index)
        for index, (kind, outer, inner) in enumerate(kept)
    )


# --------------------------------------------------------------------------
# the ladder -- a filter over the chain, never a second walk
# --------------------------------------------------------------------------


def ladder_candidates(
    chain: Sequence[StructureSpan],
) -> tuple[tuple[int, int], ...]:
    """The chain flattened into the ranges one press each selects, smallest first.

    Two rules, both from §8's rung table:

    * a bracketed group and a `$$` body contribute **two** rungs -- `inner`
      first, then `outer` -- because "the argument list" and "the parenthesised
      argument list" are both things a reader means;
    * every other kind contributes `outer` only, because a block's keywords are
      part of the block.

    Duplicates and any range that does not strictly contain the previous one are
    dropped, so a press always widens: **a rung may be absent, never
    present-and-empty** (`DEC-260810164602`).
    """
    result: list[tuple[int, int]] = []
    for span in chain:
        options = (
            (span.inner, span.outer)
            if span.kind in _TWO_RUNG_KINDS
            else (span.outer,)
        )
        for candidate in options:
            if candidate[1] <= candidate[0]:
                continue
            if result and not _strictly_contains(candidate, result[-1]):
                continue
            result.append(candidate)
    return tuple(result)


def _strictly_contains(outer: tuple[int, int], inner: tuple[int, int]) -> bool:
    return outer[0] <= inner[0] and outer[1] >= inner[1] and outer != inner


def expand_target(
    chain: Sequence[StructureSpan], selection: tuple[int, int]
) -> tuple[int, int] | None:
    """The smallest ladder rung strictly containing `selection`, or None.

    None means "nothing larger left", and the caller's answer to that is a
    **no-op, never a refusal** (§8): selecting mutates nothing, so a report per
    keypress at the top of the ladder would be noise rather than information.
    """
    for candidate in ladder_candidates(chain):
        if _strictly_contains(candidate, selection):
            return candidate
    return None


def shrink_target(
    chain: Sequence[StructureSpan], selection: tuple[int, int]
) -> tuple[int, int] | None:
    """The largest ladder rung lying STRICTLY INSIDE `selection`, or None.

    This is what `Shrink Selection` does when it has **no expansion stack** --
    after a mouse drag, after any edit, on a first press (owner,
    `DEC-260810164601`). It was chosen because it **subsumes** the conservative
    alternative: at the innermost span nothing lies strictly inside the
    selection, so this *is* a no-op there, with no special case to write. Where
    the selection is a superset of no span at all, None -- deriving is not
    licence to jump somewhere the selection does not contain.
    """
    best: tuple[int, int] | None = None
    for candidate in ladder_candidates(chain):
        if _strictly_contains(selection, candidate):
            if best is None or candidate[1] - candidate[0] > best[1] - best[0]:
                best = candidate
    return best
