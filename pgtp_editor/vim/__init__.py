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

# pgtp_editor/vim/__init__.py
"""The Command-mode command grammar and the word-motion character classes
(FQ-032, §8) -- a PURE core beside `sql/` and `xmlfmt/`.

It imports neither `ui/` nor `sql/`, and `tests/vim/test_package_purity.py`
pins that. The `sql/` half of the rule is not incidental tidiness: **no v1
motion may consume `sql/block_spans.py::structure_chain`.** `w` / `b` / `e` are
defined by **character class**, and this layer serves XML, PHP and JS buffers as
well as SQL -- four of the six editing surfaces have no SQL to tokenize, so a
motion that consulted a SQL span model would be wrong on most of them. That
chain's FQ-032 caller is the deferred text objects (`ciw`, `di"`, `ci(`), which
are out of v1 scope.
"""
from pgtp_editor.vim.grammar import (
    CHAR_MOTIONS,
    INCLUSIVE_MOTIONS,
    INSERT_ENTRY_ACTIONS,
    LINEWISE,
    OPERATORS,
    REDO_KEY,
    SIMPLE_MOTIONS,
    Command,
    VimGrammar,
)
from pgtp_editor.vim.words import (
    CLASS_KEYWORD,
    CLASS_PUNCTUATION,
    CLASS_WHITESPACE,
    char_class,
    word_backward,
    word_end,
    word_forward,
)

__all__ = [
    "CHAR_MOTIONS",
    "CLASS_KEYWORD",
    "CLASS_PUNCTUATION",
    "CLASS_WHITESPACE",
    "Command",
    "INCLUSIVE_MOTIONS",
    "INSERT_ENTRY_ACTIONS",
    "LINEWISE",
    "OPERATORS",
    "REDO_KEY",
    "SIMPLE_MOTIONS",
    "VimGrammar",
    "char_class",
    "word_backward",
    "word_end",
    "word_forward",
]
