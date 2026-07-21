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

"""The `Difference` record shape emitted by `pgtp_editor.diff.differ`.

Pure data holder, no logic. Mirrors the model layer's own `@dataclass`
style (see `pgtp_editor/model/nodes.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Difference:
    kind: str  # "added" | "removed" | "changed"
    path: list[str]
    node_kind: str  # "page" | "detail" | "column" | "event"
    #                | "format" | "lookup" | "view_properties" | "edit_properties"
    attribute: str | None
    old_value: Any
    new_value: Any
    ambiguous: bool = False
