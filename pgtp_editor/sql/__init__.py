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

"""SQL/plpgsql selection formatter core (spec §18.4).

Pure and Qt-free (§5's dependency rule): no PySide6, no database, no I/O. The
public entry point is `format_selection(text) -> FormatResult`, which reindents
an editor selection (whitespace and line breaks only) or refuses and returns the
selection untouched with fatal `Issue`s carrying precise spans.

Per §18.4 this is the **core only**: it has no UI consumer, no keyboard
shortcut, and -- by explicit design decision -- no auto-format mode.
"""
from __future__ import annotations

from .formatter import FormatResult, format_selection
from .issues import Issue
from .keywords import SQL_KEYWORDS

__all__ = ["format_selection", "FormatResult", "Issue", "SQL_KEYWORDS"]
