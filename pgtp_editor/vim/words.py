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

# pgtp_editor/vim/words.py
"""`w` / `b` / `e` -- **vim's own character-class rule**, on plain text (FQ-032).

**This must never become a tokenizer call, and that is a boundary rule rather
than a preference.** `sql/tokenizer.py` exists and `sql/block_spans.py` exists,
but a vim word is not a SQL token, and the editing-mode layer serves **XML, PHP
and JS** buffers as well as SQL -- four of the six editing surfaces have no SQL
to tokenize. A `w` that consulted a SQL model would therefore be wrong on most
of them.

Vim's rule, exactly: a *word* is a maximal run of **keyword** characters
(alphanumerics and `_`) **or** a maximal run of **punctuation** characters;
whitespace separates but is never a word. `w` goes to the start of the next
word, `b` to the start of the previous one, `e` to the last character of the
current or next word.

Every function takes and returns a **caret offset** into `text` (0-based,
between characters) and never raises: an offset at either end of the document is
answered with the nearest legal position, because a motion at a boundary is a
no-op, not an error.
"""
from __future__ import annotations

#: The three character classes, spelled as constants so a caller never compares
#: against a bare integer.
CLASS_WHITESPACE = 0
CLASS_KEYWORD = 1
CLASS_PUNCTUATION = 2


def char_class(char: str) -> int:
    """Vim's class of one character: whitespace, keyword, or punctuation."""
    if not char or char.isspace():
        return CLASS_WHITESPACE
    if char.isalnum() or char == "_":
        return CLASS_KEYWORD
    return CLASS_PUNCTUATION


def _line_bounds(text: str, pos: int) -> tuple[int, int]:
    """The `[start, end)` offsets of the LINE containing `pos`, newline excluded."""
    index = max(0, min(pos, len(text)))
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    return start, len(text) if end < 0 else end


def _line_runs(text: str, start: int, end: int) -> list[tuple[int, int, int]]:
    """The line's maximal same-class runs, as `(start, end, class)` triples."""
    runs: list[tuple[int, int, int]] = []
    index = start
    while index < end:
        run_class = char_class(text[index])
        probe = index
        while probe < end and char_class(text[probe]) == run_class:
            probe += 1
        runs.append((index, probe, run_class))
        index = probe
    return runs


def _run_index(runs, pos: int) -> int:
    for number, (start, end, _class) in enumerate(runs):
        if start <= pos < end:
            return number
    return len(runs) - 1


def inner_word_span(text: str, pos: int, count: int = 1) -> tuple[int, int] | None:
    """`iw`: the run under the caret, and `count - 1` runs after it.

    Vim's own quirk is kept: a run of WHITESPACE is an "inner word" too, so
    `diw` on a gap deletes the gap. `2iw` therefore takes the word *and* the
    whitespace after it, `3iw` the next word as well -- runs, not words.

    Returns `None` when there is nothing to take (an empty line) or when `count`
    OVERSHOOTS the line. Overshoot is refused rather than clamped, which is this
    project's established answer for counts (`42j` on a 4-line file refuses).

    Never crosses a line boundary: vim's word text objects are line-local, and a
    `daw` that swallowed the newline would silently join two lines.
    """
    line_start, line_end = _line_bounds(text, pos)
    if line_start >= line_end:
        return None
    runs = _line_runs(text, line_start, line_end)
    first = _run_index(runs, max(line_start, min(pos, line_end - 1)))
    last = first + max(1, count) - 1
    if last >= len(runs):
        return None
    return runs[first][0], runs[last][1]


def a_word_span(text: str, pos: int, count: int = 1) -> tuple[int, int] | None:
    """`aw`: the word under the caret **plus its trailing whitespace**.

    The pair's whole point is this difference from `iw`. Vim's rules, kept
    exactly: with no trailing whitespace (the last word on the line) the
    **preceding** whitespace is taken instead; and with the caret on whitespace,
    `aw` is that whitespace *plus the word after it*.

    `count` takes that many words with their whitespace, and OVERSHOOT returns
    `None` rather than clamping. Line-local, for the reason
    :func:`inner_word_span` states.
    """
    line_start, line_end = _line_bounds(text, pos)
    if line_start >= line_end:
        return None
    runs = _line_runs(text, line_start, line_end)
    first = _run_index(runs, max(line_start, min(pos, line_end - 1)))
    wanted = max(1, count)

    if runs[first][2] == CLASS_WHITESPACE:
        # whitespace + word, `count` times over
        index = first
        for _ in range(wanted):
            if index + 1 >= len(runs) or runs[index + 1][2] == CLASS_WHITESPACE:
                return None
            index += 2
        return runs[first][0], runs[index - 1][1]

    index = first
    for number in range(wanted):
        if index >= len(runs) or runs[index][2] == CLASS_WHITESPACE:
            return None
        end = runs[index][1]
        index += 1
        if number < wanted - 1 and index < len(runs) and runs[index][2] == CLASS_WHITESPACE:
            end = runs[index][1]
            index += 1
    start = runs[first][0]
    if index < len(runs) and runs[index][2] == CLASS_WHITESPACE:
        end = runs[index][1]  # trailing whitespace
    elif first > 0 and runs[first - 1][2] == CLASS_WHITESPACE:
        start = runs[first - 1][0]  # none to trail: take the leading run instead
    return start, end


def word_forward(text: str, pos: int) -> int:
    """`w`: the start of the next word, or the end of `text` if there is none."""
    length = len(text)
    if pos >= length:
        return length
    start_class = char_class(text[pos])
    index = pos
    if start_class != CLASS_WHITESPACE:
        while index < length and char_class(text[index]) == start_class:
            index += 1
    while index < length and char_class(text[index]) == CLASS_WHITESPACE:
        index += 1
    return index


def word_backward(text: str, pos: int) -> int:
    """`b`: the start of the word before `pos`, or 0 if there is none."""
    index = min(pos, len(text)) - 1
    while index >= 0 and char_class(text[index]) == CLASS_WHITESPACE:
        index -= 1
    if index < 0:
        return 0
    run_class = char_class(text[index])
    while index >= 0 and char_class(text[index]) == run_class:
        index -= 1
    return index + 1


def word_end(text: str, pos: int) -> int:
    """`e`: the offset of the LAST character of the current or next word.

    Returned as the character's own offset (not one past it), which is what
    makes `e` vim's inclusive motion: an operator consuming it adds the one.
    """
    length = len(text)
    if length == 0:
        return 0
    index = min(pos, length - 1) + 1
    while index < length and char_class(text[index]) == CLASS_WHITESPACE:
        index += 1
    if index >= length:
        return length - 1
    run_class = char_class(text[index])
    while index + 1 < length and char_class(text[index + 1]) == run_class:
        index += 1
    return index
