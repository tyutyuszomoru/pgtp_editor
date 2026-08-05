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

# pgtp_editor/db/schema_index.py
"""Pure, Qt-free lookup index over a `DatabaseSchema`, built once per DDL
Explorer connect/refresh (spec §18.6).

Mirrors `schema_learning/settings_index.py`'s shape (§11's analogous
query-API module): plain functions/methods over an already-fetched data
structure, no Qt import, no database connection. Built by `ui/main_window.py`
(or wherever the DDL Explorer fetch result already lives) from the
`DatabaseSchema` `db/introspect.py::fetch_routines_and_triggers` now returns
(widened, §18.6, to also populate `.tables`), and handed to each open
`ui/ddl_object_editor.py::DdlObjectEditorPanel` by injection
(`set_schema_index`) -- the same idiom as `XmlEditor.set_schema_model` (§11).

`DdlObjectEditorPanel` never imports this index's *source* (`db/introspect.py`)
or a live connection; it only ever sees the finished `SchemaIndex` object
(§18.5 D1's "the panel never talks to a database" invariant).
"""
from __future__ import annotations

from .introspect import DatabaseSchema, TriggerInfo


class SchemaIndex:
    """Read-only query surface over one fetched `DatabaseSchema`."""

    def __init__(self, schema: DatabaseSchema) -> None:
        self._schema = schema
        # schema name -> sorted table names ("schema.table" -> bare "table"),
        # built once so known_tables' prefix filter never re-scans .tables.
        by_schema: dict[str, list[str]] = {}
        for table_key in schema.tables:
            schema_name, _, table_name = table_key.partition(".")
            by_schema.setdefault(schema_name, []).append(table_name)
        self._tables_by_schema: dict[str, list[str]] = {
            name: sorted(tables) for name, tables in by_schema.items()
        }
        # bare function name -> list of TriggerInfo whose function_name matches,
        # for the reverse lookup (a trigger's function has no schema qualifier
        # in pg_trigger's tgfoid-derived proname, so match on bare name).
        triggers_by_function: dict[str, list[TriggerInfo]] = {}
        for trigger in schema.triggers.values():
            triggers_by_function.setdefault(trigger.function_name, []).append(trigger)
        self._triggers_by_function = triggers_by_function

    # --- Schemas / tables / columns ----------------------------------------
    def known_schemas(self) -> list[str]:
        """Every schema name present in the fetched `DatabaseSchema`, sorted."""
        schemas = {key.partition(".")[0] for key in self._schema.tables}
        return sorted(schemas)

    def known_tables(self, schema: str, prefix: str = "") -> list[str]:
        """Table names in `schema` whose name starts with `prefix`
        (case-insensitive, matching `_CompletionPopup`'s filter convention)."""
        prefix_lower = prefix.lower()
        return [
            name
            for name in self._tables_by_schema.get(schema, [])
            if name.lower().startswith(prefix_lower)
        ]

    def known_columns(self, table: str) -> list[str]:
        """Column names of `table` (a schema-qualified `"schema.table"` key,
        matching `DatabaseSchema.tables`' existing keying, §17)."""
        info = self._schema.tables.get(table)
        if info is None:
            return []
        return [column.name for column in info.columns]

    # --- Trigger/function reverse lookup ------------------------------------
    def trigger_for_function(
        self, schema: str, name: str, arg_types: tuple[str, ...] | list[str] = ()
    ) -> TriggerInfo | None:
        """The `TriggerInfo` whose `function_name` matches this routine, or
        None if the routine is not (yet) any trigger's function.

        `arg_types` is accepted (mirroring `RoutineInfo.signature`'s full
        identity, §18.1) but not required for the match: `pg_trigger` records
        only the bare function name, never its argument types, and a trigger
        function is always zero-argument in practice (Postgres requires it).
        `schema` narrows the match when the same bare name exists in more than
        one schema's triggers.
        """
        del arg_types  # accepted for signature symmetry; unused (see above)
        candidates = self._triggers_by_function.get(name, [])
        for trigger in candidates:
            if trigger.schema == schema:
                return trigger
        return candidates[0] if candidates else None
