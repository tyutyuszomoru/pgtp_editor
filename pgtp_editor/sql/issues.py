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

# pgtp_editor/sql/issues.py
"""The formatter's refusal `Issue` (§18.4).

Mirrors -- and deliberately *extends* -- the `Issue{line, message, fatal}`
shape of `schema_learning/xsd_verify.py` (§11): same `message`/`fatal`
framing, so an audit consumer can render either the same way, plus a
**precise span** (0-based character offsets into the input text and 1-based
line/column start+end) because this feature must underline the exact
offending construct -- the unmatched `BEGIN`, the opening quote of a
half-selected literal -- not just flag a line.

This is a pattern extension, not a shared class: `xsd_verify.Issue` is
untouched by §18.4, and this is a distinct type living in the pure `sql/`
package. `line` is kept as an alias of `start_line` so the shape reads as a
strict superset of `xsd_verify.Issue`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    """One refusal reason with the precise span of the offending construct."""

    message: str
    start: int  # 0-based character offset into the input text, inclusive
    end: int  # 0-based character offset, exclusive
    start_line: int  # 1-based
    start_col: int  # 1-based
    end_line: int  # 1-based
    end_col: int  # 1-based, exclusive (one past the last character)
    fatal: bool = True  # refusals are always fatal; field kept for xsd_verify parity

    @property
    def line(self) -> int:
        """`xsd_verify.Issue.line` parity: the 1-based line the span starts on."""
        return self.start_line
