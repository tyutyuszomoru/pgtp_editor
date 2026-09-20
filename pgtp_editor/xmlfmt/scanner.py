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

# pgtp_editor/xmlfmt/scanner.py
"""An **opacity-aware**, never-raising lexer for XML-ish text (§18.4 part C).

Why this exists at all, given the project already has two XML readers:

* `lxml` (a declared dependency) raises on malformed or incomplete input. A
  formatter's input is *normally* a fragment -- that is the entire invocation
  model of "format the selection" -- so the ordinary case is the one `lxml`
  cannot parse. It also normalizes on serialize, which part C's rules 1-3
  forbid outright.
* `ui/xml_structure.py::scan` is Qt-free, lenient and already shared by
  folding, the gutter, auto-indent and structural selection -- but it applies
  `_TAG_RE` to the raw text with **no opacity handling**, so a `<Page/>`
  sitting inside a comment or a CDATA section is reported as a real element.
  For a gutter arrow that phantom costs nothing; for an engine that *rewrites
  text* it would mis-track depth and reindent comment contents -- a silently
  wrong result. Hence a second scanner. This is not a criticism of `scan`,
  whose docstring promises leniency and delivers it, and `scan` must **not**
  be "fixed" into this one: four shipped features depend on its tolerance.

What this scanner guarantees, and what the formatter builds on:

1. **It never raises**, for any input whatsoever -- truncated, mid-edit,
   binary-ish, empty. Broken constructs come back as tokens flagged
   `unterminated`; they are never exceptions and never silently dropped.
2. **The token stream tiles the input exactly.** Concatenating every token's
   `text` in order reproduces the input byte for byte. That is the property
   that lets the formatter promise "apart from inter-tag whitespace, the
   output bytes are the input bytes": anything it does not deliberately
   rewrite it copies.
3. **Opaque constructs are single tokens whose interior is never scanned** --
   comments, CDATA sections, processing instructions and `<!DOCTYPE ...>`
   (internal subset included). Rule 3 of part C is enforced here, once, rather
   than remembered at every call site.

Spans are reported twice over, matching `sql.Issue`'s shape so a token can be
turned into a refusal without conversion work: 0-based `start`/`end`
character offsets, plus 1-based `start_line`/`start_col` and
`end_line`/`end_col` (the end pair is exclusive -- one past the last
character).
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Token kinds. Plain strings rather than an Enum, for parity with
# `sql/tokenizer.py`'s kind constants and so a test can assert readable
# literals.
# ---------------------------------------------------------------------------

TAG_OPEN = "tag_open"  # <name ...>
TAG_CLOSE = "tag_close"  # </name>
TAG_SELF_CLOSING = "tag_self_closing"  # <name .../>
TEXT = "text"  # anything between constructs, entity references included
COMMENT = "comment"  # <!-- ... -->
CDATA = "cdata"  # <![CDATA[ ... ]]>
PI = "pi"  # <? ... ?>
DOCTYPE = "doctype"  # <!DOCTYPE ...> and any other <! ... > declaration

#: Kinds whose interior is opaque: byte-preserved, never scanned for tags.
OPAQUE_KINDS = frozenset({COMMENT, CDATA, PI, DOCTYPE})

#: Kinds that are a tag of some sort -- the only ones that carry a `name`.
TAG_KINDS = frozenset({TAG_OPEN, TAG_CLOSE, TAG_SELF_CLOSING})

#: Human-readable construct names for refusal messages.
KIND_LABELS = {
    TAG_OPEN: "tag",
    TAG_CLOSE: "closing tag",
    TAG_SELF_CLOSING: "tag",
    TEXT: "text",
    COMMENT: "comment",
    CDATA: "CDATA section",
    PI: "processing instruction",
    DOCTYPE: "DOCTYPE declaration",
}

# An XML name, permissive on purpose: the scanner must tolerate whatever a
# user is halfway through typing. Namespace colons and the usual `.-_` are in.
_NAME_RE = re.compile(r"[A-Za-z_:][\w.:-]*")

_QUOTES = frozenset("\"'")


@dataclass(frozen=True)
class XmlToken:
    """One lexical unit, carrying its verbatim text and its exact span.

    `text` is always `source[start:end]` -- verbatim, never normalized, so a
    consumer that copies tokens through cannot alter the input by accident.
    """

    kind: str
    text: str
    start: int  # 0-based offset into the scanned string, inclusive
    end: int  # 0-based offset, exclusive
    start_line: int  # 1-based
    start_col: int  # 1-based
    end_line: int  # 1-based
    end_col: int  # 1-based, exclusive (one past the last character)
    name: str | None = None  # element name, for TAG_KINDS only
    unterminated: bool = False  # ran to end of input without its closer

    @property
    def is_whitespace(self) -> bool:
        """True for a TEXT token holding nothing but whitespace.

        The formatter's central predicate: this is the *only* place it is
        allowed to rewrite anything (part C rule 2 -- "the engine only ever
        adjusts whitespace at a position where the material between two tags
        is whitespace only").
        """
        return self.kind == TEXT and not self.text.strip()


class LineIndex:
    """Offset -> (1-based line, 1-based column) for one string.

    Built once and reused, because refusals need line/column for every issue
    and the naive `text.count("\\n", 0, offset)` per lookup is O(n) each --
    which on a 37k-tag `.pgtp` is measurable. Recognizes all three line
    endings, `\\r\\n` counting as one break, so a CRLF or classic-Mac file
    reports the same line numbers the editor shows.
    """

    def __init__(self, source: str) -> None:
        self._source = source
        starts = [0]
        i = 0
        n = len(source)
        while i < n:
            ch = source[i]
            if ch == "\r":
                i += 2 if source.startswith("\r\n", i) else 1
                starts.append(i)
            elif ch == "\n":
                i += 1
                starts.append(i)
            else:
                i += 1
        self._line_starts = starts

    def line_col(self, offset: int) -> tuple[int, int]:
        """1-based line and column of `offset` (clamped into range)."""
        offset = max(0, min(offset, len(self._source)))
        line = bisect_right(self._line_starts, offset) - 1
        return line + 1, offset - self._line_starts[line] + 1


def scan(source: str) -> list[XmlToken]:
    """Tokenize `source`. Never raises, whatever `source` contains.

    The stream tiles `source` exactly (see the module docstring), so
    `"".join(t.text for t in scan(s)) == s` for every `s`.
    """
    index = LineIndex(source)
    tokens: list[XmlToken] = []
    n = len(source)
    pos = 0

    def emit(kind: str, start: int, end: int, *, name: str | None = None, unterminated: bool = False) -> None:
        start_line, start_col = index.line_col(start)
        end_line, end_col = index.line_col(end)
        tokens.append(
            XmlToken(
                kind=kind,
                text=source[start:end],
                start=start,
                end=end,
                start_line=start_line,
                start_col=start_col,
                end_line=end_line,
                end_col=end_col,
                name=name,
                unterminated=unterminated,
            )
        )

    while pos < n:
        if source[pos] == "<" and _starts_construct(source, pos):
            pos = _scan_construct(source, pos, emit)
            continue
        # Text runs up to the next `<` that really opens a construct. A bare
        # `<` that does not (`a < b`, or a half-typed `<`) stays text -- being
        # lenient here is what keeps mid-edit buffers usable.
        text_start = pos
        pos += 1
        while pos < n:
            if source[pos] == "<" and _starts_construct(source, pos):
                break
            pos += 1
        emit(TEXT, text_start, pos)

    return tokens


def _starts_construct(source: str, i: int) -> bool:
    """Whether the `<` at `i` opens a tag, comment, CDATA, PI or declaration."""
    nxt = source[i + 1 : i + 2]
    if nxt in ("!", "?"):
        return True
    if nxt == "/":
        return bool(_NAME_RE.match(source, i + 2))
    return bool(_NAME_RE.match(source, i + 1))


def _scan_construct(source: str, i: int, emit) -> int:
    """Scan the construct starting at `source[i] == '<'`; return the new pos.

    Dispatch order matters: `<!--` and `<![CDATA[` must be tested before the
    generic `<!` declaration, or a comment would be read as a DOCTYPE and its
    interior would stop being opaque at the first `>` -- which is exactly the
    phantom-tag class of bug this module exists to avoid.
    """
    n = len(source)

    if source.startswith("<!--", i):
        return _scan_delimited(source, i, 4, "-->", COMMENT, emit)
    if source.startswith("<![CDATA[", i):
        return _scan_delimited(source, i, 9, "]]>", CDATA, emit)
    if source.startswith("<?", i):
        return _scan_delimited(source, i, 2, "?>", PI, emit)
    if source.startswith("<!", i):
        return _scan_declaration(source, i, emit)

    # A tag. Attribute values are quote-aware so that a `>` inside
    # `title="a > b"` does not end the tag early.
    j = i + 1
    closing = source.startswith("/", j)
    if closing:
        j += 1
    match = _NAME_RE.match(source, j)
    name = match.group(0) if match else None
    j = match.end() if match else j
    quote: str | None = None
    while j < n:
        ch = source[j]
        if quote is not None:
            if ch == quote:
                quote = None
        elif ch in _QUOTES:
            quote = ch
        elif ch == ">":
            end = j + 1
            if closing:
                emit(TAG_CLOSE, i, end, name=name)
            elif source[i:j].rstrip().endswith("/"):
                emit(TAG_SELF_CLOSING, i, end, name=name)
            else:
                emit(TAG_OPEN, i, end, name=name)
            return end
        elif ch == "<":
            # An unquoted `<` inside a tag cannot be part of it. Stop here
            # rather than swallowing the rest of the document, so the next
            # construct is still seen and the damage stays local.
            emit(TAG_OPEN if not closing else TAG_CLOSE, i, j, name=name, unterminated=True)
            return j
        j += 1
    emit(TAG_CLOSE if closing else TAG_OPEN, i, n, name=name, unterminated=True)
    return n


def _scan_delimited(source: str, i: int, open_len: int, closer: str, kind: str, emit) -> int:
    """Scan an opaque construct that ends at the first literal `closer`.

    Correct for comments, CDATA and PIs precisely because their closers cannot
    be quoted or nested: no interior interpretation is needed, which is the
    whole point of calling them opaque.
    """
    found = source.find(closer, i + open_len)
    if found == -1:
        emit(kind, i, len(source), unterminated=True)
        return len(source)
    end = found + len(closer)
    emit(kind, i, end, unterminated=False)
    return end


def _scan_declaration(source: str, i: int, emit) -> int:
    """Scan `<!DOCTYPE ...>` (or any other `<! ... >` markup declaration).

    Needs more than "find the next `>`" for two reasons a `.xsd` or a DTD-ish
    `.pgtp` can hit: an **internal subset** `[ ... ]` legitimately contains
    `>` characters, and so do quoted system/public identifiers. Both are
    tracked, and an unbalanced one degrades to `unterminated` rather than
    raising.
    """
    n = len(source)
    j = i + 2
    quote: str | None = None
    depth = 0
    while j < n:
        ch = source[j]
        if quote is not None:
            if ch == quote:
                quote = None
        elif ch in _QUOTES:
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(0, depth - 1)
        elif ch == ">" and depth == 0:
            emit(DOCTYPE, i, j + 1)
            return j + 1
        j += 1
    emit(DOCTYPE, i, n, unterminated=True)
    return n


__all__ = [
    "CDATA",
    "COMMENT",
    "DOCTYPE",
    "KIND_LABELS",
    "LineIndex",
    "OPAQUE_KINDS",
    "PI",
    "TAG_CLOSE",
    "TAG_KINDS",
    "TAG_OPEN",
    "TAG_SELF_CLOSING",
    "TEXT",
    "XmlToken",
    "scan",
]
