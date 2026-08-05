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

# pgtp_editor/sql/keywords.py
"""The single SQL/plpgsql dialect source shared by the highlighter and the
selection formatter (§18.4).

Stored **lowercase**; all matching is case-insensitive (`pg_get_functiondef`
emits uppercase `CREATE OR REPLACE FUNCTION...`, hand-written bodies vary).

WHY THE SET LIVES HERE, not in `ui/code_editor.py`
--------------------------------------------------
§18.4 says the formatter must reuse `_SQL_KEYWORDS` from `ui/code_editor.py`
as the shared dialect source, so the highlighter and the formatter never
disagree on what counts as a keyword. But §5's dependency rule requires
`pgtp_editor/sql/` to be Qt-free, and `ui/code_editor.py` imports PySide6 --
so importing the set from there would drag Qt into the pure core (ui -> core
is the allowed direction, never core -> ui).

The set is therefore *relocated* to this Qt-free module and
`ui/code_editor.py` now does `from ..sql.keywords import SQL_KEYWORDS as
_SQL_KEYWORDS`. Same single source of truth, same object identity (existing
tests assert `_highlighter._keywords is _SQL_KEYWORDS`), correct dependency
direction. Extend the dialect here and both consumers see it.
"""
from __future__ import annotations

# The highlighter's original §18.1 set, plus the plpgsql block/control keywords
# the formatter's tokenizer and block tracker need (`elseif`, `elsif`, `while`,
# `exit`, `continue`, `foreach`, `reverse`, `end`, `then`, `loop`, ...).
SQL_KEYWORDS = frozenset(
    """
    add all alter and any array as asc begin between by call cascade case cast
    check column commit constraint create cross declare default delete
    desc distinct do drop else elseif elsif end except execute exists exception
    exit fetch for foreach foreign from full function grant group having if
    immutable in index inner insert instead intersect into is join key language
    leakproof left like limit loop not null of offset on or order out outer
    perform primary procedure raise references replace restrict return
    returning returns reverse revoke right rollback row rows security select
    sequence set stable strict table then to trigger truncate union unique
    update using values view volatile when where while with
    continue
    true false
    """.split()
)
