# pgtp_editor/ui/search.py
"""Pure, Qt-free case-insensitive substring search over plain text.

Serves the FindReplaceBar UI widget (pgtp_editor/ui/find_replace_bar.py) but
has no Qt dependency itself, so it is unit-testable without a QApplication.
Matching is always plain case-insensitive substring: no case/word/regex
options exist anywhere in this sub-project.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    """One case-insensitive substring match found by find_all_matches.

    start:   0-based character index of the match within the full text.
    line:    1-based line number the match starts on (matching the
             XmlEditor.navigate_to_line / line_text 1-based convention).
    preview: the whitespace-trimmed text of that whole line.
    """

    start: int
    line: int
    preview: str


def find_next(text: str, term: str, from_pos: int, *, wrap: bool = True) -> int | None:
    """Return the 0-based index of the next case-insensitive occurrence of
    `term` at or after `from_pos`. If none is found at/after `from_pos` and
    `wrap` is True, wrap around and search from the start. Returns None if
    `term` is empty or does not occur in `text` at all.
    """
    if not term:
        return None
    lowered_text = text.lower()
    lowered_term = term.lower()
    start = max(0, from_pos)
    found = lowered_text.find(lowered_term, start)
    if found != -1:
        return found
    if wrap:
        found = lowered_text.find(lowered_term, 0)
        if found != -1:
            return found
    return None


def iter_matches(text: str, term: str):
    """Yield every non-overlapping case-insensitive match of `term` lazily,
    left-to-right, advancing by len(term) after each hit. Empty term/text
    yields nothing. This is the single scan implementation; find_all_matches
    is list(iter_matches(...))."""
    if not term:
        return
    lowered_text = text.lower()
    lowered_term = term.lower()
    term_len = len(term)
    pos = 0
    while True:
        found = lowered_text.find(lowered_term, pos)
        if found == -1:
            break
        line = text.count("\n", 0, found) + 1
        yield Match(start=found, line=line, preview=_line_preview(text, found))
        pos = found + term_len


def find_all_matches(text: str, term: str) -> list[Match]:
    """Return every non-overlapping case-insensitive match of `term`
    (list form of iter_matches). Empty `term` -> []."""
    return list(iter_matches(text, term))


def _line_preview(text: str, index: int) -> str:
    """The whitespace-trimmed text of the line that character `index`
    falls on."""
    line_start = text.rfind("\n", 0, index) + 1  # -1 -> 0 for the first line
    line_end = text.find("\n", index)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].strip()
