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
