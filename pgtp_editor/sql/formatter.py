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

# pgtp_editor/sql/formatter.py
"""SQL/plpgsql selection formatter -- layout, plus optional keyword casing (§18.4).

`format_selection(text, config=...)` reindents an arbitrary editor selection (a
whole statement, a bare fragment, or a chunk of plpgsql control flow) using a
nesting-depth walk over `tokenizer.tokenize`'s token stream. It rewrites
**inter-token whitespace and newlines** and -- when `config.keyword_case` asks
for it (FQ-033 part A; the default `AS_IS` is byte-identical to the older
engine) -- **the case of keyword tokens and nothing else**. Identifier casing,
comma placement/style and literal values are never touched. The headline
invariant, in the form §18.4 states it:

    The output's non-whitespace tokens are identical to the input's, in order --
    identical EXCEPT for keyword casing, and only when keyword casing is
    enabled. Under the default (`AS_IS`) the stricter old form still holds
    literally: "".join(out.split()) == "".join(in.split()).

Refusal is the only gate (§18.4: no semantic checks). When the selection cannot
be confidently tokenized (a string / quoted identifier / dollar-quote / block
comment cut in half by the selection boundary) or its parens/brackets/blocks are
unbalanced, the formatter returns `ok=False` with the original text **verbatim**
-- so a caller that ignores `ok` still cannot corrupt the selection -- plus one
fatal `Issue` per problem carrying the precise span of the offending construct.
**No configuration reaches that gate**: there is no setting that makes the
formatter accept unbalanced input.

Which rules are configurable, which are fixed, and why the space is bounded is
documented in `format_config.py` -- read it before adding a knob. There is no
auto-format mode of any kind, by explicit design decision (§18.4).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from .format_config import (
    CLAUSE_STARTERS,
    DEFAULT_FORMAT_CONFIG,
    DEFAULT_INDENT_UNIT,
    ClauseRule,
    FormatConfig,
    KeywordCase,
)
from .issues import Issue
from .tokenizer import (
    BLOCK_COMMENT,
    DOLLAR_STRING,
    LINE_COMMENT,
    NEWLINE,
    PUNCT,
    QUOTED_IDENT,
    STRING,
    WHITESPACE,
    WORD,
    Token,
    tokenize,
)

# --------------------------------------------------------------------------
# Dialect subsets driving the line-break decisions. All lowercase; matching
# goes through Token.keyword (case-insensitive), so a keyword's *classification*
# never depends on how the author spelled it. Rewriting its case is a separate,
# opt-in step that happens at token emit (`_Reindenter._emit_text`) -- the
# tokenizer itself still never changes casing (see `tokenizer.py`).
# --------------------------------------------------------------------------

#: Clause keywords that start a new line (plain-SQL clause structure). Defined
#: in `format_config.py` because the per-clause break/indent grid is keyed by it
#: and the config module must not import the engine it configures. Aliased here
#: under the module's historical private name, which the rules below read.
_CLAUSE_STARTERS = CLAUSE_STARTERS

#: Words that begin a JOIN phrase -- the break goes before them, not before
#: the `join` they lead into (`left outer join` stays one line).
_JOIN_PREFIXES = frozenset({"inner", "left", "right", "full", "cross", "outer", "natural"})

#: Block keywords that start a new line (plpgsql block structure).
_BLOCK_STARTERS = frozenset({"begin", "declare", "exception", "else", "elsif", "elseif", "end", "when"})

#: After these the rest of the header is done -- the body starts on a new line.
_BREAK_AFTER = frozenset({"begin", "declare", "loop", "exception"})

#: Tokens after which a bare `LOOP` opens a loop rather than closing a header.
_LOOP_STARTERS = frozenset({"then", "begin", "else", "exception", "loop", "declare"})

#: `IF` here is a modifier (`DROP ... IF EXISTS`), not a block opener.
_IF_NOT_BLOCK_FOLLOWERS = frozenset({"exists"})

#: `BEGIN` here is transaction control, not a plpgsql block.
_BEGIN_NOT_BLOCK_FOLLOWERS = frozenset({"transaction", "work", "isolation"})

#: Keywords that end a clause context (so the next line is not a continuation).
_CLAUSE_ENDERS = frozenset(
    """
    begin declare exception else elsif elseif end when then loop if case do
    """.split()
)

_NO_SPACE_BEFORE = frozenset({",", ";", ")", "]", ".", "::", "..", "%"})
_NO_SPACE_AFTER = frozenset({"(", "[", ".", "::", ".."})
#: `+`/`-` after one of these is unary -- `= -1`, `(-1)`, `, -1`, `select -1`.
_UNARY_CONTEXT_PUNCT = frozenset(
    {"(", "[", ",", "=", "<", ">", "<=", ">=", "<>", "!=", "+", "-", "*", "/", ":="}
)

# Frame kinds. "paren"/"bracket" and the four block kinds are balance-relevant;
# "declare"/"when" are soft (indent-only) frames that never cause a refusal.
_SOFT_FRAMES = frozenset({"declare", "when"})
_BLOCK_FRAMES = frozenset({"begin", "if", "loop", "case"})

_UNMATCHED_BLOCK_HINT = {
    "begin": "no matching END",
    "if": "no matching END IF",
    "loop": "no matching END LOOP",
    "case": "no matching END",
}

#: Characters Postgres may combine into a single (possibly user-defined)
#: operator name. Two tokens whose texts meet at two of these fuse into one
#: operator for Postgres even where *our* tokenizer still reads two -- `+ +1`
#: written as `++1` is the undefined `++` operator, not two unary signs.
_OPERATOR_CHARS = frozenset("+-*/<>=~!@#%^&|`?")


@lru_cache(maxsize=8192)
def _concatenation_relexes(prev_kind: str, prev_text: str, kind: str, text: str) -> bool:
    """Whether `prev_text + text` still lexes as exactly those two tokens.

    Cached: the spacer asks this only where it was about to glue, and the
    inputs are one or two tokens long, so the same handful of pairs
    (`a` + `.`, `)` + `,`, ...) recurs thousands of times in a large body.
    """
    if prev_text and text and prev_text[-1] in _OPERATOR_CHARS and text[0] in _OPERATOR_CHARS:
        return False  # Postgres reads the run as one operator name
    relexed = tokenize(prev_text + text)
    return (
        len(relexed) == 2
        and (relexed[0].kind, relexed[0].text) == (prev_kind, prev_text)
        and (relexed[1].kind, relexed[1].text) == (kind, text)
    )


def _glue_is_lossless(prev: Token, tok: Token) -> bool:
    """Whether `prev` and `tok` may be written adjacently without fusing.

    The general safety net behind every "no space here" rule: dropping a space
    is only layout when the two tokens still read back as themselves. `-` next
    to `-1` would relex as a `--` line comment that swallows the rest of the
    line, `+` next to `+1` as Postgres' one-token `++` operator, `1` next to
    `.` as the number `1.` -- all silent corruption, so the space stays.
    """
    return _concatenation_relexes(prev.kind, prev.text, tok.kind, tok.text)


_OPAQUE_LABEL = {
    STRING: "single-quoted string literal",
    QUOTED_IDENT: 'double-quoted identifier',
    BLOCK_COMMENT: "block comment (/* ... */)",
}


@dataclass
class FormatResult:
    """Outcome of `format_selection`.

    `ok=False` means *refused*: `text` is then the original input verbatim and
    `issues` is non-empty with every entry `fatal=True`.
    """

    ok: bool
    text: str
    issues: list[Issue] = field(default_factory=list)


@dataclass
class _Frame:
    kind: str
    token: Token | None  # the opener, for the refusal message's span
    in_clause: bool = False  # a clause keyword was seen at this nesting level
    in_exception: bool = False  # `EXCEPTION` seen in this BEGIN block


def _issue(message: str, start: Token, end: Token | None = None) -> Issue:
    """Build a fatal Issue spanning `start` (through `end`, when given)."""
    last = end or start
    return Issue(
        message=message,
        start=start.start,
        end=last.end,
        start_line=start.start_line,
        start_col=start.start_col,
        end_line=last.end_line,
        end_col=last.end_col,
        fatal=True,
    )


def _significant(tokens: list[Token]) -> list[tuple[Token, int]]:
    """Drop whitespace, keeping how many newlines preceded each real token."""
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


def _base_indent(text: str) -> str:
    """The selection's own leading indentation, re-applied to every line.

    Keeps a formatted block sitting where it was in the host document. Uses the
    first line's leading whitespace; when that line is blank, the first line
    that has content (a selection starting with a bare newline would otherwise
    get an absurd indent).
    """
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.lstrip(" \t")
        if stripped:
            return line[: len(line) - len(stripped)]
        if line:  # whitespace-only first line: keep looking for content
            continue
    return ""


def _dominant_eol(text: str) -> str:
    """The line ending the selection mostly uses; ties fall back to `\\n`.

    Lone `\\r` (classic-Mac) counts as a line ending in its own right, so a
    CR-only selection is reindented, not silently converted to LF.
    """
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    if crlf > lf and crlf > cr:
        return "\r\n"
    if cr > lf and cr > crlf:
        return "\r"
    return "\n"


def format_selection(
    text: str, *, config: FormatConfig = DEFAULT_FORMAT_CONFIG
) -> FormatResult:
    """Reindent `text` under `config`, or refuse and hand it back untouched.

    Whitespace, newlines and (opt-in) keyword casing only -- see the module
    docstring for the full contract. Deterministic and idempotent **for every
    reachable config**: formatting an already-formatted selection with the same
    config reproduces it exactly.

    The old `indent_unit=` keyword is GONE rather than kept alongside
    `config.indent_unit`: two ways to set one value is the second-source-of-truth
    defect this project refuses everywhere else (§18.4's public-API table).
    """
    tokens = tokenize(text)
    items = _significant(tokens)
    if not items:
        # Empty / whitespace-only selection: nothing to format, nothing to refuse.
        return FormatResult(ok=True, text=text, issues=[])

    # A construct the selection boundary cut in half makes every later
    # balance conclusion unreliable, so it is reported alone.
    unterminated = [
        _issue(
            f"Unterminated {_opaque_label(tok)} -- the selection splits it "
            f"(starts at line {tok.start_line}, column {tok.start_col}).",
            tok,
        )
        for tok, _ in items
        if tok.unterminated
    ]
    if unterminated:
        return FormatResult(ok=False, text=text, issues=unterminated)

    formatter = _Reindenter(items, config=config)
    lines, issues = formatter.run()
    if issues:
        return FormatResult(ok=False, text=text, issues=issues)

    eol = _dominant_eol(text)
    base = _base_indent(text)
    body = eol.join(base + line if line else "" for line in lines)
    if text.endswith(("\n", "\r")):
        body += eol
    return FormatResult(ok=True, text=body, issues=[])


def _opaque_label(tok: Token) -> str:
    if tok.kind == DOLLAR_STRING:
        tag = tok.tag or ""
        return f"dollar-quoted string (${tag}$)"
    return _OPAQUE_LABEL.get(tok.kind, tok.kind)


class _Reindenter:
    """One pass over the token stream producing indented lines + refusals.

    Line breaks and indentation come from the same frame stack that validates
    balance, so there is a single implementation of "how deep are we". When any
    refusal is recorded the produced lines are discarded by the caller.
    """

    def __init__(self, items: list[tuple[Token, int]], *, config: FormatConfig):
        self._items = items
        self._config = config
        self._indent_unit = config.indent_unit
        self._frames: list[_Frame] = [_Frame(kind="root", token=None)]
        self._issues: list[Issue] = []
        self._lines: list[str] = []
        self._parts: list[str] = []  # tokens on the line being built
        self._line_indent = 0
        self._prev: Token | None = None  # previous significant token
        self._prev_prev: Token | None = None  # the one before that (unary sign test)
        self._force_break = False
        self._saw_transaction_begin = False

    # -- frame helpers ----------------------------------------------------

    @property
    def _top(self) -> _Frame:
        return self._frames[-1]

    def _level(self) -> int:
        return len(self._frames) - 1

    def _pop_soft(self) -> None:
        while len(self._frames) > 1 and self._top.kind in _SOFT_FRAMES:
            self._frames.pop()

    def _enclosing_block(self) -> _Frame | None:
        for frame in reversed(self._frames):
            if frame.kind in _BLOCK_FRAMES:
                return frame
        return None

    def _in_if_context(self) -> bool:
        """True when the nearest block is an IF, or a BEGIN's EXCEPTION part.

        These are *statement* contexts, where `THEN`/`ELSE` end a header and
        the body belongs on the next line. A `CASE` **expression** must not be
        broken that way (`when 1 then 'a'` stays on one line).
        """
        block = self._enclosing_block()
        if block is None:
            return False
        return block.kind == "if" or (block.kind == "begin" and block.in_exception)

    # -- line helpers -----------------------------------------------------

    def _flush(self) -> None:
        if self._parts:
            self._lines.append(self._indent_unit * self._line_indent + "".join(self._parts))
            self._parts = []

    def _start_line(self, level: int, blanks: int) -> None:
        self._flush()
        if self._lines:  # never lead the output with blank lines
            self._lines.extend([""] * blanks)
        self._line_indent = max(level, 0)

    # -- the pass ---------------------------------------------------------

    def run(self) -> tuple[list[str], list[Issue]]:
        for index, (tok, newlines_before) in enumerate(self._items):
            self._handle(index, tok, newlines_before)
        self._flush()
        self._report_unclosed()
        self._issues.sort(key=lambda issue: (issue.start, issue.end))
        return self._lines, self._issues

    def _next_keyword(self, index: int, offset: int = 1) -> str | None:
        target = index + offset
        if target < len(self._items):
            return self._items[target][0].keyword
        return None

    def _next_token(self, index: int) -> Token | None:
        target = index + 1
        return self._items[target][0] if target < len(self._items) else None

    def _handle(self, index: int, tok: Token, newlines_before: int) -> None:
        keyword = tok.keyword
        prev = self._prev
        prev_kw = prev.keyword if prev is not None else None

        # --- closers and dedents, before this line's indent is computed ---
        dedent = 0
        if tok.kind == PUNCT and tok.text in (")", "]"):
            self._close_bracket(tok)
        elif keyword == "end":
            self._close_block(index, tok)
        elif keyword == "when" and self._when_opens_branch():
            self._pop_when_frame()
        elif keyword in ("else", "elsif", "elseif"):
            if self._in_if_context():
                dedent = 1  # ELSE/ELSIF sit at the IF's own level
            else:
                self._pop_when_frame()  # CASE expression: ELSE aligns with WHEN
        elif keyword == "exception":
            block = self._enclosing_block()
            if block is not None and block.kind == "begin":
                block.in_exception = True
            dedent = 1
        elif keyword == "begin" and self._top.kind == "declare":
            self._frames.pop()  # a DECLARE section ends at its BEGIN

        # --- line break decision ---
        structural = self._breaks_before(index, tok, keyword, prev, prev_kw)
        break_before = self._force_break or newlines_before > 0 or structural
        self._force_break = False

        is_continuation = (
            self._top.in_clause
            and keyword not in _CLAUSE_STARTERS
            and keyword not in _BLOCK_STARTERS
            and keyword not in _JOIN_PREFIXES
            and not (tok.kind == PUNCT and tok.text in (")", "]"))
        )
        level = self._level() - dedent + (1 if is_continuation else 0)

        if not self._lines and not self._parts:
            # THE FIRST EMITTED LINE NEVER TAKES A PER-CLAUSE EXTRA INDENT, and
            # that is an idempotence guard rather than a cosmetic choice:
            # `format_selection` re-applies the selection's own first content
            # line indentation to every output line, so indenting the first line
            # here would make pass 2 read that indentation as the new base and
            # push the whole block right again, forever. The first line anchors
            # the block; per-clause indents apply to the lines below it.
            self._line_indent = max(level, 0)
        elif break_before:
            self._start_line(
                level + self._clause_indent(keyword),
                blanks=min(max(newlines_before - 1, 0), 1),
            )

        # --- emit ---
        if self._parts and self._space_before(tok, self._next_token(index)):
            self._parts.append(" ")
        self._parts.append(self._emit_text(tok))

        # --- openers and post-token state, after the text is placed ---
        self._open_frames(index, tok, keyword, prev_kw)
        self._update_clause_state(tok, keyword)
        if tok.kind == LINE_COMMENT:
            self._force_break = True  # anything after it would be commented out
        elif tok.kind == PUNCT and tok.text == ";":
            self._force_break = True
        elif self._breaks_after(keyword, prev_kw):
            self._force_break = True
        elif keyword in ("then", "else") and self._in_if_context():
            self._force_break = True

        self._prev_prev = self._prev
        self._prev = tok

    # -- configuration ----------------------------------------------------

    def _rule(self, keyword: str) -> ClauseRule:
        """The configured (or shipped-default) rule for a clause starter."""
        return self._config.rule_for(keyword)

    def _clause_indent(self, keyword: str | None) -> int:
        """Extra levels for a clause starter that is starting its own line.

        Zero for everything else, including continuation lines: the
        clause-continuation `+1` is a property of the *nesting*, not of the
        keyword, and stays out of the configurable space (§18.4 B).
        """
        if keyword is None or keyword not in _CLAUSE_STARTERS:
            return 0
        return self._rule(keyword).indent_levels

    def _emit_text(self, tok: Token) -> str:
        """The token's text as it goes into the output line.

        The ONE place casing is applied, and only to tokens the tokenizer
        classified as keywords -- `Token.keyword` is non-`None` for `word` tokens
        in `SQL_KEYWORDS` and nothing else, so identifiers, built-in types and
        functions, numbers, and every opaque region (strings, `E'...'`, quoted
        identifiers, `$$...$$` bodies, `--` and `/* */` comments) can never reach
        the rewrite. That boundary is deliberate: the formatter is offline and
        has no schema knowledge, and Postgres quoted identifiers are
        case-sensitive, so recasing anything but a keyword could silently change
        which object a statement names (§18.4 A).

        Idempotent by construction: the result is a function of the token's set
        membership, not of its current spelling.
        """
        if tok.keyword is None or self._config.keyword_case is KeywordCase.AS_IS:
            return tok.text
        return self._config.case_of(tok.text)

    # -- break rules ------------------------------------------------------

    def _breaks_before(
        self, index: int, tok: Token, keyword: str | None, prev: Token | None, prev_kw: str | None
    ) -> bool:
        if keyword is None:
            return False
        if prev_kw == "end":
            return False  # `END IF` / `END LOOP` / `END CASE` are two tokens
        if keyword in _CLAUSE_STARTERS:
            # `left outer join` breaks at most once, and at its first prefix
            # word -- so the `join` itself never breaks after a prefix,
            # whichever way `join_phrase_break` is set.
            if keyword == "join" and prev_kw in _JOIN_PREFIXES:
                return False
            return self._rule(keyword).break_before
        if keyword in _JOIN_PREFIXES:
            # `left outer join` breaks once, before `left`. `join_phrase_break`
            # governs the PHRASE as a whole (§18.4 B: "never per prefix word"):
            # switched off, a prefixed join introduces no break anywhere -- not
            # before `left` and, by the branch above, not before `join` either,
            # so `from a left outer join b` stays on one line instead of
            # breaking in the middle of the phrase. A *bare* `join` keeps
            # following its own clause rule.
            if not self._config.join_phrase_break:
                return False
            return prev_kw not in _JOIN_PREFIXES and self._leads_into_join(index)
        if keyword == "loop":
            # A bare `LOOP` opens a block; `FOR ... LOOP` / `WHILE ... LOOP`
            # ends a header and stays on the header's line.
            return prev is None or (prev.kind == PUNCT and prev.text == ";") or prev_kw in _LOOP_STARTERS
        if keyword == "when":
            # `WHEN` branches of a CASE / EXCEPTION part only; `EXIT WHEN done`
            # and `RAISE ... WHEN` are ordinary statement tails.
            return self._when_opens_branch()
        return keyword in _BLOCK_STARTERS

    def _breaks_after(self, keyword: str | None, prev_kw: str | None) -> bool:
        """Whether the header ends here, so the body starts on a new line.

        Checked *after* `_open_frames`, so "did this keyword actually open a
        block" is simply "is that frame now on top" -- which keeps `BEGIN;`
        (transaction control) and `END LOOP` from forcing a break.
        """
        if keyword not in _BREAK_AFTER:
            return False
        if prev_kw == "end":
            return False  # the `loop` in `END LOOP`
        if keyword in ("begin", "declare", "loop"):
            return self._top.kind == keyword
        return True  # `exception`

    def _leads_into_join(self, index: int) -> bool:
        """`left`/`outer`/... only starts a line when a `join` follows it."""
        for offset in (1, 2, 3):
            keyword = self._next_keyword(index, offset)
            if keyword == "join":
                return True
            if keyword not in _JOIN_PREFIXES:
                return False
        return False

    # -- frame transitions ------------------------------------------------

    def _when_opens_branch(self) -> bool:
        """`WHEN` opens an indented branch in a CASE or an EXCEPTION part.

        (A plain `CASE` expression's `WHEN` does too -- the branch body simply
        usually stays on the same line.)
        """
        block = self._enclosing_block()
        return block is not None and (block.kind == "case" or (block.kind == "begin" and block.in_exception))

    def _pop_when_frame(self) -> None:
        if self._top.kind == "when":
            self._frames.pop()

    def _open_frames(self, index: int, tok: Token, keyword: str | None, prev_kw: str | None) -> None:
        if tok.kind == PUNCT and tok.text in ("(", "["):
            self._frames.append(_Frame(kind="paren" if tok.text == "(" else "bracket", token=tok))
            return
        if keyword is None or prev_kw == "end":
            return
        if keyword == "begin":
            follower = self._next_keyword(index)
            next_tok = self._next_token(index)
            transaction = follower in _BEGIN_NOT_BLOCK_FOLLOWERS or (
                next_tok is not None and next_tok.kind == PUNCT and next_tok.text == ";"
            )
            if transaction:
                self._saw_transaction_begin = True
            else:
                self._frames.append(_Frame(kind="begin", token=tok))
        elif keyword == "if":
            if not self._if_is_modifier(index):
                self._frames.append(_Frame(kind="if", token=tok))
        elif keyword == "loop":
            self._frames.append(_Frame(kind="loop", token=tok))
        elif keyword == "case":
            self._frames.append(_Frame(kind="case", token=tok))
        elif keyword == "declare" and not self._declare_is_cursor(index):
            self._frames.append(_Frame(kind="declare", token=tok))
        elif keyword == "when" and self._when_opens_branch():
            self._frames.append(_Frame(kind="when", token=tok))
        elif keyword == "else" and not self._in_if_context() and self._enclosing_block() is not None:
            self._frames.append(_Frame(kind="when", token=tok))  # CASE's ELSE branch body

    def _if_is_modifier(self, index: int) -> bool:
        """`IF EXISTS` / `IF NOT EXISTS` is a modifier, not a block opener."""
        follower = self._next_keyword(index)
        if follower in _IF_NOT_BLOCK_FOLLOWERS:
            return True
        return follower == "not" and self._next_keyword(index, 2) in _IF_NOT_BLOCK_FOLLOWERS

    def _declare_is_cursor(self, index: int) -> bool:
        """`DECLARE c CURSOR FOR ...` is a statement, not a plpgsql section.

        Told apart by layout: a plpgsql DECLARE section ends its line (its
        declarations follow indented below), while the cursor statement runs on
        from `DECLARE` -- so only an inline `CURSOR` before the next `;` counts.
        """
        if index + 1 >= len(self._items) or self._items[index + 1][1] > 0:
            return False  # `DECLARE` ends the line: a plpgsql section
        for offset in range(1, 8):
            target = index + offset
            if target >= len(self._items):
                return False
            tok = self._items[target][0]
            if tok.kind == PUNCT and tok.text == ";":
                return False
            if tok.lowered == "cursor":
                return True
        return False

    def _close_bracket(self, tok: Token) -> None:
        self._pop_soft()
        expected = "paren" if tok.text == ")" else "bracket"
        if self._top.kind == "root":
            opener = "(" if tok.text == ")" else "["
            self._issues.append(
                _issue(
                    f"Unmatched '{tok.text}' -- no opening '{opener}' in the selection "
                    f"(line {tok.start_line}, column {tok.start_col}).",
                    tok,
                )
            )
            return
        frame = self._frames[-1]
        if frame.kind != expected:
            self._issues.append(self._mismatch_issue(frame, tok))
            return
        self._frames.pop()

    def _mismatch_issue(self, frame: _Frame, tok: Token) -> Issue:
        opener = frame.token
        where = (
            f" at line {opener.start_line}, column {opener.start_col}"
            if opener is not None
            else ""
        )
        name = opener.text if opener is not None else frame.kind
        return _issue(
            f"Unbalanced '{tok.text}' -- it closes nothing: the innermost open construct is "
            f"'{name}'{where} (line {tok.start_line}, column {tok.start_col}).",
            tok,
        )

    def _close_block(self, index: int, tok: Token) -> None:
        """Match an `END` (optionally `END IF` / `END LOOP` / `END CASE`)."""
        self._pop_soft()
        follower_kw = self._next_keyword(index)
        follower = self._next_token(index)
        closes = follower_kw if follower_kw in ("if", "loop", "case") else None
        end_span = follower if closes else None

        frame = self._frames[-1]
        if frame.kind == "root":
            terminator = follower is not None and follower.kind == PUNCT and follower.text == ";"
            if closes is None and terminator and self._saw_transaction_begin:
                return  # `BEGIN; ... END;` transaction control, not a block
            self._issues.append(
                _issue(
                    "Unmatched END -- there is no open block to close "
                    f"(line {tok.start_line}, column {tok.start_col}).",
                    tok,
                    end_span,
                )
            )
            return
        if frame.kind not in _BLOCK_FRAMES:
            self._issues.append(self._mismatch_issue(frame, tok))
            return
        if closes is None:
            # A bare END closes BEGIN, or a CASE *expression*.
            if frame.kind in ("begin", "case"):
                self._frames.pop()
                return
            self._issues.append(self._unclosed_issue(frame, seen=tok))
            self._frames.pop()  # consumed by this END; don't report it twice
            return
        if closes == frame.kind:
            self._frames.pop()
            return
        self._issues.append(self._unclosed_issue(frame, seen=tok, saw=f"END {follower.text}"))
        self._frames.pop()

    def _unclosed_issue(self, frame: _Frame, *, seen: Token, saw: str | None = None) -> Issue:
        opener = frame.token
        assert opener is not None  # only block frames reach here
        hint = _UNMATCHED_BLOCK_HINT[frame.kind]
        tail = f" -- found {saw} instead" if saw else ""
        return _issue(
            f"Unmatched {opener.text.upper()} -- {hint} in the selection"
            f"{tail} (line {opener.start_line}, column {opener.start_col}).",
            opener,
        )

    def _report_unclosed(self) -> None:
        for frame in self._frames:
            if frame.kind in _BLOCK_FRAMES:
                self._issues.append(self._unclosed_issue(frame, seen=frame.token))  # type: ignore[arg-type]
            elif frame.kind in ("paren", "bracket"):
                opener = frame.token
                assert opener is not None
                closer = ")" if frame.kind == "paren" else "]"
                self._issues.append(
                    _issue(
                        f"Unmatched '{opener.text}' -- no closing '{closer}' in the selection "
                        f"(line {opener.start_line}, column {opener.start_col}).",
                        opener,
                    )
                )

    def _update_clause_state(self, tok: Token, keyword: str | None) -> None:
        if tok.kind == PUNCT and tok.text == ";":
            self._top.in_clause = False
        elif keyword in _CLAUSE_STARTERS:
            self._top.in_clause = True
        elif keyword in _CLAUSE_ENDERS:
            self._top.in_clause = False

    # -- spacing ----------------------------------------------------------

    def _space_before(self, tok: Token, next_tok: Token | None) -> bool:
        """Whether a single space separates `tok` from the previous token.

        Every glue decision below is subject to one general safety net: two
        tokens are only written adjacently when the concatenation still lexes
        as those same two tokens (`_glue_is_lossless`). Without it a rule that
        merely *looks* like pure layout can silently change the SQL -- `- -1`
        glued to `--1` turns the rest of the line into a comment.
        """
        prev = self._prev
        if prev is None:
            return False
        if self._wants_glue(tok, next_tok, prev) and _glue_is_lossless(prev, tok):
            return False
        return True

    def _wants_glue(self, tok: Token, next_tok: Token | None, prev: Token) -> bool:
        """Whether a layout rule asks for no space between `prev` and `tok`."""
        if tok.kind == PUNCT:
            if tok.text in _NO_SPACE_BEFORE:
                # `%TYPE` / `%ROWTYPE` glue to the identifier before them.
                if tok.text != "%" or (next_tok is not None and next_tok.lowered in ("type", "rowtype")):
                    return True
            if tok.text == "(" and self._call_paren(prev):
                return True
            if tok.text == "[" and self._subscript_bracket(prev):
                return True
        if prev.kind == PUNCT:
            if prev.text in _NO_SPACE_AFTER:
                return True
            if prev.text == "%" and tok.lowered in ("type", "rowtype"):
                return True  # `col%TYPE`, not the modulo operator
            if prev.text in ("+", "-") and self._unary_minus_before():
                return True
        return False

    def _call_paren(self, prev: Token) -> bool:
        """`count(x)` / `f(1)` -- but `in (1, 2)`, `values (1)` keep the space."""
        if prev.kind == QUOTED_IDENT:
            return True
        if prev.kind == PUNCT and prev.text in (")", "]"):
            return True
        return prev.kind == WORD and prev.keyword is None

    def _subscript_bracket(self, prev: Token) -> bool:
        """`array[1, 2]` / `a[1][2]` -- a subscript always glues to its target."""
        if prev.kind in (WORD, QUOTED_IDENT, STRING):
            return True
        return prev.kind == PUNCT and prev.text in (")", "]")

    def _unary_minus_before(self) -> bool:
        """A `+`/`-` directly after an operator, opener or keyword is unary.

        `self._prev` is the sign itself when this runs, so the deciding token is
        the one before it: `= -1` / `(-1)` / `, -1` / `select -1` are unary,
        `a - 1` / `count(*) - 1` are binary.
        """
        before = self._prev_prev
        if before is None:
            return True
        if before.kind == PUNCT:
            return before.text in _UNARY_CONTEXT_PUNCT
        return before.kind == WORD and before.keyword is not None
