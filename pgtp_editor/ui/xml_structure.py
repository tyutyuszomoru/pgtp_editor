"""A lenient, regex-based tag-position scanner for XML-like text.

Deliberately NOT built on lxml: lxml raises on malformed or incomplete XML,
but this module has to keep working while a user is mid-edit (an unclosed
tag, a half-typed attribute, a truncated document are all normal, transient
states from this module's point of view, not error states). This is a
plain-Python, regex-based, best-effort scanner with no Qt dependency, so it
is unit-testable without a QApplication and reusable by both xml_editor.py
(folding, gutter, auto-indent, auto-close) and, in a future sub-project,
XML structural selection.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Matches an opening tag (<name ...>), a self-closing tag (<name .../>), or
# a closing tag (</name>). Permissive: attribute values need not be
# well-formed or quotes balanced, since this scanner must tolerate
# in-progress edits.
_TAG_RE = re.compile(r"<(/?)([A-Za-z_][\w.-]*)([^<>]*?)(/?)>")


@dataclass
class TagSpan:
    name: str  # element name, e.g. "Page"
    open_start: int  # character offset of the '<' that opens this element
    open_end: int  # character offset just past this open tag's '>'
    close_end: int | None  # character offset just past the matching '</name>' '>',
    # or None if no matching close tag was found
    depth: int  # nesting depth, 0 for a top-level element
    self_closing: bool  # True for a <tag/> form -- such an element has no
    # separate close tag and is not a foldable region


def scan(text: str) -> list[TagSpan]:
    """Scan `text` for tag positions. Never raises, regardless of how
    malformed or incomplete `text` is."""
    spans: list[TagSpan] = []
    stack: list[TagSpan] = []

    for match in _TAG_RE.finditer(text):
        is_closing = match.group(1) == "/"
        name = match.group(2)
        is_self_closing = match.group(4) == "/"
        open_start = match.start()
        open_end = match.end()

        if is_closing:
            # Find the nearest still-open span with a matching name.
            match_index = None
            for i in range(len(stack) - 1, -1, -1):
                if stack[i].name == name:
                    match_index = i
                    break
            if match_index is None:
                # Stray closing tag matching nothing on the stack: ignore.
                continue
            # Any spans above the matched one were opened but never validly
            # closed before this closing tag: emit as-is with close_end=None.
            for i in range(len(stack) - 1, match_index, -1):
                spans.append(stack.pop(i))
            matched_span = stack.pop(match_index)
            matched_span.close_end = open_end
            spans.append(matched_span)
        elif is_self_closing:
            spans.append(
                TagSpan(
                    name=name,
                    open_start=open_start,
                    open_end=open_end,
                    close_end=open_end,
                    depth=len(stack),
                    self_closing=True,
                )
            )
        else:
            stack.append(
                TagSpan(
                    name=name,
                    open_start=open_start,
                    open_end=open_end,
                    close_end=None,
                    depth=len(stack),
                    self_closing=False,
                )
            )

    # Anything still on the stack at end of input: truncated or genuinely
    # unclosed -- emit as-is with close_end=None.
    spans.extend(stack)
    return spans


def find_enclosing_open_tag(text: str, position: int) -> str | None:
    """Find the name of the innermost element that contains `position` and
    is not yet known to be closed before it.

    A `TagSpan` is a candidate if `open_start < position` (strictly before,
    so a child element beginning exactly at `position` is not considered
    its own enclosing tag) and either `close_end is None` or
    `close_end > position` (i.e. `position` falls strictly inside that
    element's content span). Among candidates, the one with the greatest
    `depth` is the innermost.
    """
    spans = scan(text)
    candidates = [
        span
        for span in spans
        if span.open_start < position and (span.close_end is None or span.close_end > position)
    ]
    if not candidates:
        return None
    innermost = max(candidates, key=lambda span: span.depth)
    return innermost.name


def nesting_depth_at(text: str, position: int) -> int:
    """Depth of find_enclosing_open_tag's result, or 0 if none."""
    spans = scan(text)
    candidates = [
        span
        for span in spans
        if span.open_start < position and (span.close_end is None or span.close_end > position)
    ]
    if not candidates:
        return 0
    innermost = max(candidates, key=lambda span: span.depth)
    return innermost.depth
