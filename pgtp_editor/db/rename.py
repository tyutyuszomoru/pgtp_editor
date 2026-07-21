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

# pgtp_editor/db/rename.py
"""Targeted-attribute rename over the Raw XML buffer text (pure, Qt-free).

Reconciliation renames replace the literal attribute token
``fieldName="{old}"`` / ``tableName="{old}"`` everywhere in the file — a global
per-attribute replace by design (the rename prompt states this). Matching is on
the exact quoted token so a same-valued *other* attribute, or an unrelated
substring, is never touched, and a longer name sharing the prefix is safe
because the closing quote is part of the token.
"""
from __future__ import annotations


def _rename_attribute(text: str, attr: str, old: str, new: str) -> tuple[str, int]:
    token = f'{attr}="{old}"'
    replacement = f'{attr}="{new}"'
    count = text.count(token)
    if count == 0:
        return text, 0
    return text.replace(token, replacement), count


def rename_field(text: str, old: str, new: str) -> tuple[str, int]:
    """Replace ``fieldName="{old}"`` with ``fieldName="{new}"``; return the count."""
    return _rename_attribute(text, "fieldName", old, new)


def rename_table(text: str, old: str, new: str) -> tuple[str, int]:
    """Replace ``tableName="{old}"`` with ``tableName="{new}"``; return the count."""
    return _rename_attribute(text, "tableName", old, new)
