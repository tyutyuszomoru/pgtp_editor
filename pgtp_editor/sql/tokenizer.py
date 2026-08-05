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

# pgtp_editor/sql/tokenizer.py
"""Hand-built SQL/plpgsql tokenizer for the selection formatter (§18.4).

Lexical only -- no grammar, no statement parsing. It exists so the reindenter
can walk a token stream instead of raw characters, and so opaque regions
(strings, quoted identifiers, comments, dollar-quoted bodies) are recognized
as single indivisible tokens that are never rewritten internally.

Token text is preserved **verbatim**: the tokenizer never changes casing or
content. `is_keyword` is a *view* over the verbatim text via the shared
`SQL_KEYWORDS` set (case-insensitive), not a rewrite.

Unterminated opaque regions are not an exception -- they become a token
carrying `unterminated=True` spanning from its opener to the end of the input,
so the formatter can refuse with that exact span (the selection boundary split
the construct in half).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .keywords import SQL_KEYWORDS

# Token kinds. Strings rather than an enum, matching the codebase's existing
# `kind: str  # "function" | "procedure" | "trigger"` convention (db/ddl_buffer.py).
WHITESPACE = "whitespace"
NEWLINE = "newline"
LINE_COMMENT = "line_comment"
BLOCK_COMMENT = "block_comment"
STRING = "string"  # single-quoted literal, '' escape
QUOTED_IDENT = "quoted_ident"  # double-quoted identifier, "" escape
DOLLAR_STRING = "dollar_string"  # $$...$$ / $tag$...$tag$
NUMBER = "number"
WORD = "word"  # identifier or keyword
PUNCT = "punct"  # punctuation / operator

#: Kinds whose content is opaque -- never reindented or line-broken internally.
OPAQUE_KINDS = frozenset({LINE_COMMENT, BLOCK_COMMENT, STRING, QUOTED_IDENT, DOLLAR_STRING})

#: Kinds that carry no code and no content of their own.
_TRIVIA_KINDS = frozenset({WHITESPACE, NEWLINE})

_DIGITS = set("0123456789")

#: Unicode general categories of combining marks (non-spacing / spacing).
_COMBINING_CATEGORIES = frozenset({"Mn", "Mc"})


def _is_combining_mark(ch: str) -> bool:
    """Whether `ch` is a Unicode combining mark (`á` written as `a` + U+0301).

    Decomposed (NFD) text is what a macOS clipboard or a PDF copy hands over,
    and a combining mark is neither `isalpha()` nor `isalnum()` -- so without
    this the accented identifier it belongs to would be split apart.
    """
    return unicodedata.category(ch) in _COMBINING_CATEGORIES


def _is_word_start(ch: str) -> bool:
    """Whether `ch` may start an unquoted identifier (Postgres' rule).

    Any Unicode letter or `_` -- accented identifiers (`tábla`) are ordinary
    identifiers in Postgres, and splitting one into fragments would let the
    reindenter insert spaces inside it, corrupting the SQL. A combining mark
    is deliberately *not* a start character: it only ever continues the letter
    in front of it.
    """
    return ch == "_" or ch.isalpha()


def _is_word_char(ch: str) -> bool:
    """Whether `ch` may continue an unquoted identifier.

    Letters, digits, `_`, `$` -- plus combining marks, so a decomposed (NFD)
    identifier such as `ta` + U+0301 + `bla` stays one word token.
    """
    return ch in "_$" or ch.isalnum() or _is_combining_mark(ch)

# Multi-character operators kept as ONE punct token (longest match first). The
# formatter inserts spaces between tokens, so `::` / `<=` / `:=` must not be
# split -- gluing them back together from single characters would be guesswork
# and `a :: text` / `a : = 1` is not the same text the user wrote.
_OPERATORS = (
    "->>", "#>>", "||/", "!~*", "!~~", "~~*",
    "::", ":=", "<=", ">=", "<>", "!=", "||", "->", "#>", "<<", ">>", "..",
    "**", "!!", "@>", "<@", "&&", "|/", "~*", "!~", "^@",
)

# String literal prefixes Postgres attaches to the opening quote: E'..' escape
# strings, B'..'/X'..' bit strings, U&'..' unicode. Splitting the prefix off
# would let a space be inserted between it and the quote, which changes meaning.
_STRING_PREFIXES = ("u&", "U&", "e", "E", "b", "B", "x", "X")


@dataclass(frozen=True)
class Token:
    kind: str
    text: str  # verbatim slice of the input -- never rewritten
    start: int  # 0-based character offset, inclusive
    end: int  # 0-based character offset, exclusive
    start_line: int  # 1-based
    start_col: int  # 1-based
    end_line: int  # 1-based
    end_col: int  # 1-based, exclusive
    unterminated: bool = False  # opaque region cut off by the end of the input
    tag: str | None = None  # dollar-quote tag ("" for bare $$), else None

    @property
    def is_trivia(self) -> bool:
        """Whitespace/newline -- the only thing the formatter may rewrite."""
        return self.kind in _TRIVIA_KINDS

    @property
    def is_opaque(self) -> bool:
        return self.kind in OPAQUE_KINDS

    @property
    def keyword(self) -> str | None:
        """Lowercased text when this word token is a dialect keyword, else None."""
        if self.kind != WORD:
            return None
        lowered = self.text.lower()
        return lowered if lowered in SQL_KEYWORDS else None

    @property
    def is_keyword(self) -> bool:
        return self.keyword is not None

    @property
    def lowered(self) -> str:
        """Lowercased text -- a comparison view only; `text` stays verbatim."""
        return self.text.lower()


class _Cursor:
    """Offset + line/col bookkeeping over the input text."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.line = 1
        self.col = 1

    def advance_to(self, new_pos: int) -> None:
        """Consume up to `new_pos`, tracking line/column across line breaks.

        All three line endings count as exactly one break: `\\r\\n` (one, not
        two), a lone `\\n`, and a lone `\\r` (classic-Mac text still turns up in
        pasted DDL). Getting this wrong would freeze line/column in CR-only
        text, so every later Issue span would point at the wrong line.
        """
        chunk = self.text[self.pos : new_pos]
        breaks = chunk.count("\n") + chunk.count("\r") - chunk.count("\r\n")
        if chunk.startswith("\n") and self.pos > 0 and self.text[self.pos - 1] == "\r":
            breaks -= 1  # trailing half of a `\r\n` split across two chunks
        last_break = max(chunk.rfind("\n"), chunk.rfind("\r"))
        if last_break >= 0:
            self.line += breaks
            self.col = len(chunk) - last_break
        else:
            self.col += len(chunk)
        self.pos = new_pos


def _scan_quoted(text: str, i: int, quote: str, *, backslash_escapes: bool = False) -> tuple[int, bool]:
    """Scan a `quote`-delimited run starting at the opening quote `i`.

    Returns `(end_offset_exclusive, terminated)`; a doubled quote (`''` / `""`)
    is an escape, not the terminator. `backslash_escapes` additionally honors
    `\\'` -- true only for `E'...'` escape-string literals.
    """
    j = i + 1
    n = len(text)
    while j < n:
        if backslash_escapes and text[j] == "\\" and j + 1 < n:
            j += 2
            continue
        if text[j] == quote:
            if text.startswith(quote * 2, j):
                j += 2
                continue
            return j + 1, True
        j += 1
    return n, False


def _dollar_tag_at(text: str, i: int) -> str | None:
    """Return the dollar-quote tag at `i` (`""` for a bare `$$`), or None.

    A dollar-quote opener is `$` + an optional identifier tag + `$`. `$1`
    (a parameter placeholder) and a bare `$` are not openers. The tag follows
    the unquoted-identifier rule, so a decomposed (NFD) `$tág$` is a tag while
    `$1$` is not.
    """
    if text[i] != "$":
        return None
    j = i + 1
    while j < len(text) and text[j] != "$" and _is_word_char(text[j]):
        # Tags are identifiers: the first character must be able to start one
        # (no digits, no combining mark).
        if j == i + 1 and not _is_word_start(text[j]):
            return None
        j += 1
    if j < len(text) and text[j] == "$":
        return text[i + 1 : j]
    return None


def tokenize(text: str) -> list[Token]:
    """Split `text` into a verbatim token list (see module docstring).

    Never raises on malformed input: an unterminated string / quoted
    identifier / dollar-quote / block comment yields one token with
    `unterminated=True` running to the end of the text.
    """
    cur = _Cursor(text)
    tokens: list[Token] = []
    n = len(text)

    def emit(kind: str, end_pos: int, *, unterminated: bool = False, tag: str | None = None) -> None:
        start, start_line, start_col = cur.pos, cur.line, cur.col
        cur.advance_to(end_pos)
        tokens.append(
            Token(
                kind=kind,
                text=text[start:end_pos],
                start=start,
                end=end_pos,
                start_line=start_line,
                start_col=start_col,
                end_line=cur.line,
                end_col=cur.col,
                unterminated=unterminated,
                tag=tag,
            )
        )

    while cur.pos < n:
        i = cur.pos
        ch = text[i]

        # Newlines are their own kind so the formatter can count/rewrite them;
        # \r\n stays one token so line-ending detection is trivial.
        if ch == "\n":
            emit(NEWLINE, i + 1)
            continue
        if ch == "\r":
            emit(NEWLINE, i + 2 if text.startswith("\r\n", i) else i + 1)
            continue

        if ch in " \t\f\v":
            j = i
            while j < n and text[j] in " \t\f\v":
                j += 1
            emit(WHITESPACE, j)
            continue

        # -- line comment: runs to (not including) the line terminator.
        if text.startswith("--", i):
            j = i
            while j < n and text[j] not in "\r\n":
                j += 1
            emit(LINE_COMMENT, j)
            continue

        # /* ... */ block comment, nestable per Postgres.
        if text.startswith("/*", i):
            depth = 0
            j = i
            while j < n:
                if text.startswith("/*", j):
                    depth += 1
                    j += 2
                elif text.startswith("*/", j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        break
                else:
                    j += 1
            else:
                emit(BLOCK_COMMENT, n, unterminated=True)
                continue
            if depth != 0:  # ran off the end mid-nesting
                emit(BLOCK_COMMENT, n, unterminated=True)
                continue
            emit(BLOCK_COMMENT, j)
            continue

        # Single-quoted string, '' escape -- optionally with an E/B/X/U& prefix
        # glued to the opening quote (see _STRING_PREFIXES).
        prefix_len = 0
        if ch == "'":
            prefix_len = 0
        else:
            for prefix in _STRING_PREFIXES:
                if text.startswith(prefix, i) and text.startswith("'", i + len(prefix)):
                    prefix_len = len(prefix)
                    break
        if ch == "'" or prefix_len:
            escapes = prefix_len == 1 and ch in "eE"
            end, terminated = _scan_quoted(text, i + prefix_len, "'", backslash_escapes=escapes)
            emit(STRING, end, unterminated=not terminated)
            continue

        # Double-quoted identifier, "" escape.
        if ch == '"':
            end, terminated = _scan_quoted(text, i, '"')
            emit(QUOTED_IDENT, end, unterminated=not terminated)
            continue

        # Dollar-quoted string: $$...$$ or $tag$...$tag$ (no escapes inside).
        tag = _dollar_tag_at(text, i)
        if tag is not None:
            opener = f"${tag}$"
            close_at = text.find(opener, i + len(opener))
            if close_at == -1:
                emit(DOLLAR_STRING, n, unterminated=True, tag=tag)
                continue
            emit(DOLLAR_STRING, close_at + len(opener), tag=tag)
            continue

        # `$1` positional parameter -- one token, because `$ 1` is not valid SQL.
        if ch == "$" and i + 1 < n and text[i + 1] in _DIGITS:
            j = i + 1
            while j < n and text[j] in _DIGITS:
                j += 1
            emit(WORD, j)
            continue

        # Number: digits with optional fraction/exponent. A leading '.' only
        # counts when a digit follows, so `a.b` stays punctuation + word.
        if ch in _DIGITS or (ch == "." and i + 1 < n and text[i + 1] in _DIGITS):
            j = i
            while j < n and text[j] in _DIGITS:
                j += 1
            # `1..10` is a plpgsql range: the `..` is an operator, not a
            # fractional point, so only consume a lone `.`.
            if j < n and text[j] == "." and not text.startswith("..", j):
                j += 1
                while j < n and text[j] in _DIGITS:
                    j += 1
            if j < n and text[j] in "eE":
                k = j + 1
                if k < n and text[k] in "+-":
                    k += 1
                if k < n and text[k] in _DIGITS:
                    j = k
                    while j < n and text[j] in _DIGITS:
                        j += 1
            emit(NUMBER, j)
            continue

        # Word: identifier or keyword. `$` is allowed inside (pg identifiers)
        # but a `$` that opens a dollar-quote was handled above.
        if _is_word_start(ch):
            j = i
            while j < n and _is_word_char(text[j]):
                if text[j] == "$" and _dollar_tag_at(text, j) is not None:
                    break
                j += 1
            emit(WORD, j)
            continue

        # Punctuation / operator: longest known multi-character operator first,
        # otherwise a single character.
        for op in _OPERATORS:
            if text.startswith(op, i):
                emit(PUNCT, i + len(op))
                break
        else:
            emit(PUNCT, i + 1)
        continue

    return tokens
