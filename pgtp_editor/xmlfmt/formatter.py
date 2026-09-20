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

# pgtp_editor/xmlfmt/formatter.py
"""XML selection reindenter -- element-nesting depth and nothing else (§18.4 part C).

`format_xml_selection(document, start, end)` re-emits `document[start:end]`
with the whitespace *between tags* recomputed from element nesting depth, and
returns a `FormatResult` whose `text` replaces `[start, end)` in the host
buffer. It shares the SQL engine's refusal shape (`FormatResult` / `Issue`
imported from the `pgtp_editor.sql` facade, never re-declared) because the
refusal *shape* belongs to the gesture, not to the dialect: one host renders
one span-underline and one audit row for both engines.

WHY THE WHOLE DOCUMENT IS A PARAMETER, and not just the selected text -- the
one place this engine deliberately diverges from the SQL one. `format_selection`
re-applies the base indentation of the selection's own first content line. The
XML engine cannot: *the reason a user reindents a fragment is that its
indentation is wrong*, so trusting the first line would faithfully preserve the
very defect being fixed. The base depth therefore comes from the selection's
**position in the document** -- `document[:start]` is walked with the same
opacity-aware scanner, so a `<Page/>` living inside a comment does not inflate
the ancestor count.

WHAT IT WILL NOT DO -- part C's three hard rules, each traceable to §2:

1. **Never break inside an opening tag.** §2 guarantees an element's opening
   tag with all its attributes sits on one line, and §13's caption grid plus
   §17's DB-rename path are line-anchored on that. An opening tag is a single
   token here and is emitted as one unit, however long its attribute list.
2. **Never touch element TEXT.** §2 stores inline PHP/JS handler bodies as
   entity-escaped text directly inside elements; reindenting that text would
   rewrite shipped PHP. Concretely, the engine rewrites whitespace *only* at a
   position where the material between two tags is whitespace only, and an
   element with any non-whitespace direct text content is emitted byte for
   byte -- its content **and its own two tags** -- with no break after the open
   tag and none before the close tag.
3. **Comments, CDATA, PIs and DOCTYPEs are opaque**: byte-preserved, never
   scanned for tags. Enforced in `scanner.py`, once.

ISSUE OFFSETS ARE **ABSOLUTE DOCUMENT OFFSETS**, not selection-relative -- and
so are the 1-based line/column pairs. The host underlines spans in the whole
document and prints line numbers the user can find in the gutter, so any other
convention would force every caller to re-base and one of them would forget.
The one asymmetry to remember: `Issue.start`/`end` index `document`, while
`FormatResult.text` replaces `[start, end)`.

Refusal is all-or-nothing, exactly like the SQL engine: `ok=False`, `text` is
the selected slice **verbatim** (so a caller that ignores `ok` still cannot
corrupt anything), and `issues` is non-empty with every entry `fatal=True`,
sorted by `(start, end)`.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..sql import FormatResult, Issue
from .config import DEFAULT_XML_FORMAT_CONFIG, XmlFormatConfig
from .scanner import (
    KIND_LABELS,
    TAG_CLOSE,
    TAG_OPEN,
    TEXT,
    LineIndex,
    XmlToken,
    scan,
)

#: Emitted as one unit at the current depth, with its interior untouched. Not a
#: scanner kind -- a formatter-level grouping for rule 2's "byte for byte".
_VERBATIM = "verbatim"


def format_xml_selection(
    document: str,
    start: int,
    end: int,
    *,
    config: XmlFormatConfig = DEFAULT_XML_FORMAT_CONFIG,
) -> FormatResult:
    """Reindent `document[start:end]` by element depth, or refuse untouched.

    `result.text` replaces `[start, end)`. On refusal it *is* that slice,
    verbatim. `Issue` spans and line/columns are **absolute into `document`**
    (see the module docstring for why). `start`/`end` are clamped into range
    and swapped-order input is tolerated, so a caller cannot make this raise.

    An empty or whitespace-only selection is returned untouched with
    `ok=True`, matching the SQL engine: there is nothing to indent and nothing
    to complain about.
    """
    length = len(document)
    start = max(0, min(start, length))
    end = max(start, min(end, length))
    selection = document[start:end]
    if not selection.strip():
        return FormatResult(ok=True, text=selection, issues=[])

    doc_tokens = scan(document)
    index = LineIndex(document)

    # (1) A selection boundary that cuts a construct in half. Checked first and
    # against the DOCUMENT's tokens, because that is the only vantage point
    # from which it is visible at all: scanning the slice alone, a selection
    # starting in the middle of a comment would read the comment's `<Page/>`
    # as a real element. Mirrors §18.4's half-selected string literal.
    splits = [
        _issue(
            f"The selection boundary splits a {KIND_LABELS[tok.kind]} "
            f"(starts at line {tok.start_line}, column {tok.start_col}).",
            tok,
        )
        for tok in doc_tokens
        if tok.kind != TEXT and (tok.start < start < tok.end or tok.start < end < tok.end)
    ]
    if splits:
        return FormatResult(ok=False, text=selection, issues=_ordered(splits))

    base_depth = _prefix_depth(doc_tokens, start)
    tokens = _clip(doc_tokens, document, start, end, index)

    # (2) An unterminated construct. Reported ALONE and before any depth walk:
    # every depth conclusion drawn past a broken construct is guesswork, so
    # adding a mis-nesting complaint on top would just be noise. (Reaching
    # here means the document itself never closes the construct -- one merely
    # cut by the selection was already refused by (1).)
    unterminated = [
        _issue(
            f"Unterminated {KIND_LABELS[tok.kind]} -- it runs to the end of "
            f"the selection (starts at line {tok.start_line}, column {tok.start_col}).",
            tok,
        )
        for tok in tokens
        if tok.unterminated
    ]
    if unterminated:
        return FormatResult(ok=False, text=selection, issues=_ordered(unterminated))

    # (3) Mis-nesting, and the two nearby cases that are NOT mis-nesting.
    plan, misnesting = _analyze(tokens)
    if misnesting is not None:
        return FormatResult(ok=False, text=selection, issues=[misnesting])

    text = _emit(
        document, tokens, plan, selection=selection, base_depth=base_depth, config=config
    )
    return FormatResult(ok=True, text=text, issues=[])


# ---------------------------------------------------------------------------
# Depth: where the selection sits in the document
# ---------------------------------------------------------------------------


def _prefix_depth(doc_tokens: list[XmlToken], start: int) -> int:
    """Ancestor depth at `start`, from the tokens that end at or before it.

    Lenient in the same way `ui/xml_structure.scan` is -- a close tag pops the
    nearest still-open element of that name, and a close tag matching nothing
    is ignored -- because the *prefix* of a real document is routinely
    ill-formed in ways the user is not asking about (they selected something
    further down). A refusal here would fire on documents the user can see are
    fine, so the prefix walk never refuses; only the selection does.
    """
    stack: list[str] = []
    for tok in doc_tokens:
        if tok.end > start:
            break
        if tok.kind == TAG_OPEN and not tok.unterminated:
            stack.append(tok.name or "")
        elif tok.kind == TAG_CLOSE and not tok.unterminated:
            name = tok.name or ""
            for i in range(len(stack) - 1, -1, -1):
                if stack[i] == name:
                    del stack[i:]
                    break
    return len(stack)


def _clip(
    doc_tokens: list[XmlToken],
    document: str,
    start: int,
    end: int,
    index: LineIndex,
) -> list[XmlToken]:
    """The document's tokens restricted to `[start, end)`, offsets unchanged.

    Reuses the single document scan rather than re-scanning the slice, which
    matters on a 37k-tag `.pgtp`, and is exact: by the time this runs, no
    construct straddles a boundary (step 1 refused those), so the only token
    that can be clipped is TEXT -- and clipping text is just a substring.
    Offsets stay document-absolute so issues and verbatim slices need no
    re-basing anywhere downstream.
    """
    out: list[XmlToken] = []
    for tok in doc_tokens:
        if tok.end <= start or tok.start >= end:
            continue
        lo, hi = max(tok.start, start), min(tok.end, end)
        if lo == tok.start and hi == tok.end:
            out.append(tok)
            continue
        start_line, start_col = index.line_col(lo)
        end_line, end_col = index.line_col(hi)
        out.append(
            XmlToken(
                kind=tok.kind,
                text=document[lo:hi],
                start=lo,
                end=hi,
                start_line=start_line,
                start_col=start_col,
                end_line=end_line,
                end_col=end_col,
                name=tok.name,
                unterminated=tok.unterminated,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Structure analysis: mis-nesting, and which elements must stay byte-for-byte
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Plan:
    """What the emitter needs to know beyond the token list itself.

    `verbatim` maps a token index that opens a text-carrying element to the
    index of its close tag: everything from the first token's `start` to the
    last one's `end` is copied out unchanged, as one atom, honouring rule 2.
    """

    verbatim: dict[int, int]


def _analyze(tokens: list[XmlToken]) -> tuple[_Plan, Issue | None]:
    """One structural pass: find text-carrying elements and mis-nesting.

    The two are found together because both fall out of the same stack of open
    tags, and doing it twice would risk the two walks disagreeing.

    **The mis-nesting rule, stated precisely, because the neighbouring cases
    look identical and must NOT refuse:**

    * a close tag whose name differs from the top of a **non-empty** stack is
      mis-nesting (`<a><b></a></b>`) -- reindenting it would emit a layout
      asserting a structure the document does not have, so: refuse;
    * a close tag arriving with an **empty** stack is an element whose opener
      is simply *outside the selection* -- the XML analogue of §18.4's "a bare
      fragment (`where a = 1`) is a legitimate selection". Accept, and dedent
      (with the total indent clamped at zero);
    * depth that never returns to zero -- an unmatched open tag -- is likewise
      the normal fragment case. Accept.

    Refuse at the *first* mis-nest and report it alone: past that point the
    stack no longer describes the document, so any later complaint is derived
    from a state already known to be wrong.
    """
    stack: list[tuple[int, str, bool]] = []  # (open index, name, saw direct text)
    pairs: list[tuple[int, int]] = []  # (open index, close index) with direct text

    for i, tok in enumerate(tokens):
        if tok.kind == TEXT:
            if stack and tok.text.strip():
                open_index, name, _ = stack[-1]
                stack[-1] = (open_index, name, True)
        elif tok.kind == TAG_OPEN:
            stack.append((i, tok.name or "", False))
        elif tok.kind == TAG_CLOSE:
            if not stack:
                continue  # opener outside the selection -- fine, see docstring
            open_index, name, saw_text = stack.pop()
            if name != (tok.name or ""):
                return _Plan(verbatim={}), _issue(
                    f"Mis-nested tags: </{tok.name}> closes an element opened as "
                    f"<{name}> at line {tokens[open_index].start_line}, column "
                    f"{tokens[open_index].start_col}.",
                    tok,
                )
            if saw_text:
                pairs.append((open_index, i))

    # Keep only the OUTERMOST text-carrying elements: an inner one is already
    # inside a byte-for-byte region, and emitting a range inside a range would
    # duplicate its text.
    verbatim: dict[int, int] = {}
    covered_to = -1
    for open_index, close_index in sorted(pairs):
        if open_index > covered_to:
            verbatim[open_index] = close_index
            covered_to = close_index
    return _Plan(verbatim=verbatim), None


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Atom:
    """A run of bytes emitted unchanged, at a depth the emitter chooses."""

    kind: str
    text: str
    name: str


@dataclass(frozen=True)
class _Gap:
    """Whitespace-only material between two atoms -- the only rewritable thing."""

    text: str


def _nodes(document: str, tokens: list[XmlToken], plan: _Plan) -> list[_Atom | _Gap]:
    """Split the selection into atoms (copied) and gaps (recomputed).

    Every byte of the selection lands in exactly one node, so "apart from
    inter-tag whitespace, the output is the input" is structural rather than
    hoped for. A non-whitespace TEXT token becomes an *atom*, not a gap: it is
    element text, and rule 2 forbids touching it even when its element's own
    tags fall outside the selection.
    """
    out: list[_Atom | _Gap] = []
    i = 0
    total = len(tokens)
    while i < total:
        tok = tokens[i]
        if tok.is_whitespace:
            out.append(_Gap(tok.text))
            i += 1
            continue
        close_index = plan.verbatim.get(i)
        if close_index is not None:
            out.append(
                _Atom(_VERBATIM, document[tok.start : tokens[close_index].end], tok.name or "")
            )
            i = close_index + 1
            continue
        out.append(_Atom(tok.kind, tok.text, tok.name or ""))
        i += 1
    return out


def _emit(
    document: str,
    tokens: list[XmlToken],
    plan: _Plan,
    *,
    selection: str,
    base_depth: int,
    config: XmlFormatConfig,
) -> str:
    """Join the atoms, recomputing every rewritable gap from depth.

    **IDEMPOTENCE, which is a hard requirement, holds by inspection** -- run
    this on its own output over the region that output now occupies and
    nothing changes. Four properties make that true rather than lucky:

    * atoms are copied, so the token structure of pass 2 is the token
      structure of pass 1, hence every depth is the same;
    * `base_depth` reads `document[:start]`, which pass 1 never wrote to, and
      `start` does not move;
    * an interior gap becomes `eol * n + indent(depth)` where `n` is its
      **preserved** line-break count (at least one). Preserving `n` rather
      than collapsing to a single break keeps the user's blank lines *and*
      keeps the dominant-EOL vote stable: rewritten breaks all become the
      winning EOL and no break is deleted, so the winner can only win harder
      on pass 2. Re-reading `eol * n + indent(depth)` yields the same `n` and
      the same depth, so pass 2 writes it back identically;
    * the leading and trailing whitespace runs are handled symmetrically and
      *conditionally*: rewritten only if they already contain a line break,
      copied verbatim otherwise. That is what keeps `  <a/>` from having its
      first tag shifted (the selection began mid-line; the bytes before it are
      not ours to re-indent), and it is stable because rewriting preserves the
      break count, so pass 2 takes the same branch.
    """
    nodes = _nodes(document, tokens, plan)
    eol = _dominant_eol(selection)
    unit = config.indent_unit

    pieces: list[str] = []
    stack: list[str] = []
    closes_from_outside = 0

    def depth() -> int:
        # Clamped: a fragment may close more elements than it opens, and a
        # negative indent is not a thing.
        return max(0, base_depth + len(stack) - closes_from_outside)

    pending: _Gap | None = None
    previous: _Atom | None = None

    for node in nodes:
        if isinstance(node, _Gap):
            pending = node
            continue

        if node.kind == TAG_CLOSE:
            if stack:
                stack.pop()
            else:
                closes_from_outside += 1
        here = depth()
        if node.kind == TAG_OPEN:
            stack.append(node.name)

        if previous is None:
            # Leading run: only rewritten if it already spans lines.
            if pending is not None:
                breaks = _count_breaks(pending.text)
                pieces.append(eol * breaks + unit * here if breaks else pending.text)
        elif node.kind == TEXT or previous.kind == TEXT:
            # Adjacent to element text: this whitespace is part of that mixed
            # content, so it is text too. Copy it (or nothing, if there was
            # none -- gluing `<a>` to its text is rule 2 verbatim).
            pieces.append(pending.text if pending is not None else "")
        else:
            breaks = max(1, _count_breaks(pending.text) if pending is not None else 0)
            pieces.append(eol * breaks + unit * here)

        pieces.append(node.text)
        previous = node
        pending = None

    if pending is not None:
        # Trailing run: the mirror of the leading rule. When it spans lines it
        # is the indentation of whatever follows the selection, and re-cutting
        # it to the closing depth is the useful answer; when it does not, the
        # selection ended mid-line and those bytes are not ours.
        breaks = _count_breaks(pending.text)
        pieces.append(eol * breaks + unit * depth() if breaks else pending.text)

    return "".join(pieces)


def _count_breaks(text: str) -> int:
    """Number of line breaks in `text`, `\\r\\n` counting as one."""
    return text.replace("\r\n", "\n").replace("\r", "\n").count("\n")


def _dominant_eol(text: str) -> str:
    """The line ending the selection mostly uses; ties fall back to `\\n`.

    Deliberately a local copy of the SQL engine's rule rather than an import
    of its private helper: `xmlfmt` depends on `sql`'s *public* refusal types
    only, and a shared private function would make one engine's refactor the
    other engine's problem. Lone `\\r` counts as a line ending in its own
    right, so a classic-Mac selection is reindented rather than silently
    converted to LF.
    """
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    if crlf > lf and crlf > cr:
        return "\r\n"
    if cr > lf and cr > crlf:
        return "\r"
    return "\n"


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def _issue(message: str, tok: XmlToken) -> Issue:
    """A fatal `Issue` spanning `tok`, in absolute document coordinates."""
    return Issue(
        message=message,
        start=tok.start,
        end=tok.end,
        start_line=tok.start_line,
        start_col=tok.start_col,
        end_line=tok.end_line,
        end_col=tok.end_col,
        fatal=True,
    )


def _ordered(issues: list[Issue]) -> list[Issue]:
    """Refusals in document order, so the host's list matches the buffer."""
    return sorted(issues, key=lambda issue: (issue.start, issue.end))


__all__ = ["format_xml_selection"]
