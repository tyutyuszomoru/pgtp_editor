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

"""Qt-free helpers for locating and rewriting event-handler code bodies in
the raw .pgtp XML buffer.

Event-handler bodies are stored as **XML-escaped plain text** (NOT CDATA)
between an ``<OnXxx ...>`` open tag and its ``</OnXxx>`` close tag, e.g.::

    <OnPreparePage enabled="true">
    $this-&gt;dataset-&gt;AddDistinct('id');    </OnPreparePage>

so ``>`` is stored as ``&gt;``, ``<`` as ``&lt;`` and ``&`` as ``&amp;``.
The closing ``</OnXxx>`` may sit on its own line or on the same line as the
last code line (with trailing indentation); bodies may be single- or
multi-line.

These helpers share one source of truth (``event_body_line_ranges``) between
the XmlEditor's distinct code-region styling and the "which handler is under
the cursor" lookup that drives the "Edit code..." affordance. All functions
are Qt-free and unit-tested independently of any widget.
"""
from __future__ import annotations

import bisect
import re

from pgtp_editor.model.event_handlers import EVENT_HANDLERS
from pgtp_editor.model.nodes import classify_event_side
from pgtp_editor.ui import xml_structure

# The set of known event-handler tag names (client + server). Only spans whose
# open tag names one of these are treated as an event-handler body.
_KNOWN_HANDLER_TAGS = frozenset(tag for tag, _side in EVENT_HANDLERS)

# An open tag for a known handler: <Tag ...> or <Tag>, NOT self-closing (no
# trailing '/>'). The tag name is captured; attributes (if any) are ignored
# here -- they are preserved byte-for-byte by replace_event_body.
_OPEN_TAG_RE = re.compile(r"<([A-Za-z_][\w.-]*)(\s[^<>]*?)?>")


def xml_escape_body(code: str) -> str:
    """XML-escape event-handler code for storage between the tags: ``&`` must
    be escaped first (so the ``&`` introduced by the ``<``/``>`` escapes is not
    double-escaped), then ``<`` and ``>``."""
    return code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def xml_unescape_body(text: str) -> str:
    """Reverse of :func:`xml_escape_body` for display: unescape ``&lt;`` and
    ``&gt;`` first, then ``&amp;`` last (mirror order of escaping)."""
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _iter_handler_spans(text: str):
    """Yield ``(start_line, end_line, tag, inner_start, inner_end)`` for each
    known event-handler element in ``text``.

    ``start_line``/``end_line`` are 1-based line numbers of the open- and
    close-tag lines. ``inner_start``/``inner_end`` are character offsets into
    ``text`` delimiting the raw (still-escaped) inner content strictly between
    the open tag's ``>`` and the close tag's ``<``.

    Scans linearly; when a known handler open tag is found, searches forward
    for its matching ``</Tag>`` (no nesting: handler bodies are plain text, so
    the first following close tag with the same name is the match).
    """
    # Precompute line-number lookup: char offset -> 1-based line.
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    def line_of(offset: int) -> int:
        # 1-based line number of the character at `offset` (bisect handles
        # large buffers efficiently).
        return bisect.bisect_right(line_starts, offset)

    pos = 0
    length = len(text)
    while pos < length:
        m = _OPEN_TAG_RE.search(text, pos)
        if m is None:
            return
        tag = m.group(1)
        if tag not in _KNOWN_HANDLER_TAGS:
            pos = m.end()
            continue
        # Self-closing open tags (matched attrs ending in '/') carry no body;
        # the regex forbids '>' inside attrs but a trailing '/' is possible.
        open_tag_text = m.group(0)
        if open_tag_text.rstrip().endswith("/>"):
            pos = m.end()
            continue
        close_token = f"</{tag}>"
        close_at = text.find(close_token, m.end())
        if close_at == -1:
            # Unterminated handler: skip past this open tag and continue.
            pos = m.end()
            continue
        inner_start = m.end()
        inner_end = close_at
        start_line = line_of(m.start())
        end_line = line_of(close_at)
        yield (start_line, end_line, tag, inner_start, inner_end)
        pos = close_at + len(close_token)


def event_body_line_ranges(text: str) -> list[dict]:
    """Return one dict per known event-handler element in ``text``.

    Each dict has:

    - ``start_line`` -- 1-based line of the ``<OnXxx ...>`` open tag.
    - ``end_line`` -- 1-based line of the ``</OnXxx>`` close tag.
    - ``tag`` -- the handler tag name.
    - ``side`` -- ``"C"`` or ``"S"`` (``classify_event_side(tag)``).
    - ``body`` -- the current inner body text, XML-**unescaped** for display.

    The scan handles multi-line bodies and the close-tag-on-the-same-line case
    (the last code line and ``</OnXxx>`` sharing a line).
    """
    ranges: list[dict] = []
    for start_line, end_line, tag, inner_start, inner_end in _iter_handler_spans(text):
        raw_body = text[inner_start:inner_end]
        ranges.append(
            {
                "start_line": start_line,
                "end_line": end_line,
                "tag": tag,
                "side": classify_event_side(tag),
                "body": xml_unescape_body(raw_body),
            }
        )
    return ranges


def extract_event_body(text: str, start_line: int) -> tuple[str, str, str]:
    """Find the event-handler element at/after 1-based ``start_line`` and
    return ``(tag, side, body_unescaped)``.

    Raises ``ValueError`` if no known handler element begins on or after
    ``start_line``.
    """
    for range_ in event_body_line_ranges(text):
        if range_["start_line"] >= start_line:
            return (range_["tag"], range_["side"], range_["body"])
    raise ValueError(f"no event handler found at or after line {start_line}")


def replace_event_body(text: str, start_line: int, new_code: str) -> str:
    """Return ``text`` with the inner body of the event-handler element
    at/after 1-based ``start_line`` replaced by ``new_code`` (which is
    XML-escaped before insertion).

    The open/close tags and their attributes are preserved exactly, and every
    byte outside the replaced inner span is preserved verbatim. Handles the
    close-tag-on-same-line case and multi-line bodies. An empty ``new_code``
    yields an empty inner body (the tags become adjacent).

    Raises ``ValueError`` if no known handler element begins on or after
    ``start_line``.
    """
    for s_line, _e_line, _tag, inner_start, inner_end in _iter_handler_spans(text):
        if s_line >= start_line:
            escaped = xml_escape_body(new_code)
            return text[:inner_start] + escaped + text[inner_end:]
    raise ValueError(f"no event handler found at or after line {start_line}")


def _line_starts(text: str) -> list[int]:
    """Character offset of the start of each 1-based line (index 0 unused)."""
    starts = [0, 0]  # [_, line 1]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def _leading_indent(text: str, offset: int) -> str:
    """The run of spaces/tabs at the start of the line containing ``offset``."""
    line_start = text.rfind("\n", 0, offset) + 1
    i = line_start
    while i < len(text) and text[i] in " \t":
        i += 1
    return text[line_start:i]


def _find_page_span(text: str, page_start_line: int) -> "xml_structure.TagSpan":
    """Return the ``<Page>`` (or page-like) element span whose open tag begins
    on 1-based ``page_start_line``. Raises ``ValueError`` if none is found.

    Matching is by the open-tag line, not by name, so the same logic works for
    any element the tree treats as a page node (the model's page/detail inner
    <Page> elements all use the ``Page`` tag, but keying on the line keeps this
    robust). Among spans opening on that line, the outermost (smallest depth)
    is chosen -- that is the element the tree node points at.
    """
    starts = _line_starts(text)
    if page_start_line < 1 or page_start_line >= len(starts):
        raise ValueError(f"no page element at line {page_start_line}")
    line_begin = starts[page_start_line]
    line_end = starts[page_start_line + 1] if page_start_line + 1 < len(starts) else len(text)

    candidates = [
        span
        for span in xml_structure.scan(text)
        if not span.self_closing and line_begin <= span.open_start < line_end
    ]
    if not candidates:
        raise ValueError(f"no page element at line {page_start_line}")
    # The element the node points at is the outermost one opening on this line.
    return min(candidates, key=lambda s: s.depth)


def _own_event_handlers_span(
    text: str, page: "xml_structure.TagSpan"
) -> "xml_structure.TagSpan | None":
    """Return the ``<EventHandlers>`` span that is a DIRECT child of ``page``
    (depth == page.depth + 1, within the page's extent), or ``None`` if the
    page has no own EventHandlers. A nested Detail's inner-page EventHandlers
    lives at a deeper depth and is deliberately skipped."""
    page_end = page.close_end if page.close_end is not None else len(text)
    for span in xml_structure.scan(text):
        if (
            span.name == "EventHandlers"
            and span.depth == page.depth + 1
            and page.open_end <= span.open_start < page_end
        ):
            return span
    return None


def insert_event_handler(
    text: str, page_start_line: int, tag: str, code: str
) -> str:
    """Return ``text`` with a new ``<{tag} enabled="true">…</{tag}>`` handler
    inserted into the page element whose open tag is on 1-based
    ``page_start_line``.

    - If that page already has a direct-child ``<EventHandlers>``, the new
      handler is appended just before its ``</EventHandlers>`` close tag.
    - Otherwise a new ``<EventHandlers>…</EventHandlers>`` block is created as
      the first child of the page element (conventional position) and the
      handler placed inside it.

    ``code`` is XML-escaped before insertion. The new handler is always a child
    of the *correct* page's EventHandlers -- a nested Detail's inner-page
    EventHandlers is never targeted. Everything outside the inserted span is
    preserved verbatim and the result re-parses as XML.

    Raises ``ValueError`` if no page element opens on ``page_start_line``.
    """
    page = _find_page_span(text, page_start_line)
    escaped = xml_escape_body(code)
    handlers = _own_event_handlers_span(text, page)

    if handlers is not None and handlers.close_end is not None:
        # Append before </EventHandlers>. Indent one level past the
        # EventHandlers open tag.
        base_indent = _leading_indent(text, handlers.open_start)
        child_indent = base_indent + "  "
        close_start = handlers.close_end - len("</EventHandlers>")
        # The close tag's own indentation begins at the line start before it.
        block = (
            f'{child_indent}<{tag} enabled="true">\n'
            f"{escaped}\n"
            f"{child_indent}</{tag}>\n"
            f"{base_indent}"
        )
        return text[:close_start] + block + text[close_start:]

    # No own EventHandlers: create one as the first child of the page, right
    # after the page's open tag. Indent one level past the page.
    page_indent = _leading_indent(text, page.open_start)
    handlers_indent = page_indent + "  "
    child_indent = handlers_indent + "  "
    block = (
        f"\n{handlers_indent}<EventHandlers>\n"
        f'{child_indent}<{tag} enabled="true">\n'
        f"{escaped}\n"
        f"{child_indent}</{tag}>\n"
        f"{handlers_indent}</EventHandlers>"
    )
    return text[: page.open_end] + block + text[page.open_end:]
