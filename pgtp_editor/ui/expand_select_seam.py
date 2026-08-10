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

# pgtp_editor/ui/expand_select_seam.py
"""The three-line adapter that joins expand-`SELECT`'s two halves (FQ-030).

`sql/expand_select.py` is deliberately split in two so that neither half has
to know what the other does: `find_expand_select_site` is pure text work and
knows no schema, `render_expand_select` takes the column names someone else
looked up. This module is the "someone else" -- the only place the two halves
and a `SchemaIndex` meet.

It is a **function, not a mixin or a method**, and it lives here rather than
being copied into each panel because both SQL surfaces (the DDL object tab and
the Sandbox SQL Console) need exactly the same three lines. Two copies of a
schema lookup is how the second lookup ends up disagreeing with the first.

It is Qt-free, and it holds no index of its own: the caller passes the one
`SchemaIndex` the host already fetched and injected (§18.5 D1 -- the panel
never talks to a database, and §18.6's invariant that nothing here may issue a
lazy per-keystroke query). `index` is duck-typed on `known_columns` alone, so a
test stub is as good as the real thing.
"""
from __future__ import annotations

from ..sql.expand_select import find_expand_select_site, render_expand_select
from ..sql.templates import Expansion


def expand_select_expansion(index, text: str, pos: int) -> Expansion:
    """The `Expansion` for the bare `SELECT` at `pos`, or a stated refusal.

    Never raises and never returns None: an unusable site comes back as a
    falsy `Expansion` carrying the site's own `reason`, which the editor
    surfaces (FQ-023 -- a gesture that cannot run says why instead of
    vanishing).

    With no index injected, or with a table written bare (no schema, and
    nothing may guess a search path here), the columns are simply unknown and
    `render_expand_select` writes `*` -- the honest answer, and still a useful
    expansion: the alias and the `WHERE` are what the gesture is mostly for.
    """
    site = find_expand_select_site(text, pos)
    if not site:
        return Expansion(reason=site.reason)
    columns = ()
    if index is not None and site.qualified:
        columns = index.known_columns(site.qualified)
    return render_expand_select(site, columns)
