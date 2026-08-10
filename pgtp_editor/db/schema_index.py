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

from .introspect import ColumnInfo, DatabaseSchema, RoutineInfo, TriggerInfo

#: How much of a free-text column attribute (its DEFAULT expression, its
#: COMMENT) may reach a completion row before it is elided. A popup row is a
#: single line next to a caret, not a properties panel -- an unbounded
#: `nextval('...'::regclass)` or a paragraph-long comment would push the
#: useful part (name, type) off the visible width.
_ATTRIBUTE_ELIDE_AT = 40


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
        # "schema.table" -> the popup-ready (key, display) pairs of its columns,
        # rendered once here rather than per keystroke: completion is on the
        # typing path (§18.6), so column_entries must stay a dict lookup plus a
        # prefix filter, never a re-render of every column's attributes.
        self._column_entries: dict[str, list[tuple[str, str]]] = {
            table_key: [(column.name, _column_display(column)) for column in info.columns]
            for table_key, info in schema.tables.items()
        }

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

    def column_entries(self, table: str, prefix: str = "") -> list[tuple[str, str]]:
        """`table`'s columns as the shared completion popup's ``(key, display)``
        pairs (§18.6 / FQ-030 slice 0), prefix-filtered like `known_tables`.

        The *key* is the bare column name -- exactly what `known_columns`
        returns and exactly what gets inserted into the buffer -- so this is a
        drop-in widening of the `[(c, c) for c in known_columns(...)]` shape
        both completion hosts build today. The *display* adds what a picker
        needs to tell `id integer` from `id text`: the type, then PK / FK
        target / NOT NULL / DEFAULT / COMMENT when the column carries them
        (see `_column_display`).

        `known_columns` is deliberately left alone -- callers that want plain
        names (expand-SELECT, `%ROWTYPE` field lists) must not be forced to
        unpack pairs, and the display text must not leak into generated SQL.

        Never raises: an unknown `table`, or a `prefix` no column matches,
        yields an empty list."""
        prefix_lower = prefix.lower()
        return [
            entry
            for entry in self._column_entries.get(table, ())
            if entry[0].lower().startswith(prefix_lower)
        ]

    def column_infos(self, table: str) -> list[ColumnInfo]:
        """`table`'s `ColumnInfo` objects -- the whole column facts, not the
        names `known_columns` returns nor the popup rows `column_entries` does.

        `table` is the schema-qualified `"schema.table"` key both of those use;
        a table the fetch never saw yields `[]`, never raises. The list is a
        fresh copy, so a caller that sorts or trims it cannot disturb the fetch
        (`known_columns`/`column_entries` read the same `TableInfo`).

        This is what the FQ-030 join gesture reads for `ColumnInfo.fk_target`;
        it exists so no caller has to reach behind the index for it.
        """
        info = self._schema.tables.get(table)
        if info is None:
            return []
        return list(info.columns)

    # --- Routines -----------------------------------------------------------
    def routines(self) -> tuple[RoutineInfo, ...]:
        """Every fetched routine, in `DatabaseSchema.routines` order.

        Overloads are separate entries: that dict is keyed by
        `RoutineInfo.signature` -- the name PLUS its argument types (§18.1) --
        so `f(int)` and `f(text)` are two routines here. Order is preserved
        because signature help ranks equally-fitting overloads stably.

        `RoutineInfo` is returned as-is: `db/` publishes its own type and the
        `sql/` adaptation stays in the caller, so `sql/` still never sees a
        schema object.
        """
        return tuple(self._schema.routines.values())

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


def _elide(text: str) -> str:
    """`text` shortened to one popup row's worth, with an ellipsis when cut."""
    text = " ".join(text.split())
    if len(text) <= _ATTRIBUTE_ELIDE_AT:
        return text
    return text[: _ATTRIBUTE_ELIDE_AT - 1].rstrip() + "…"


def _column_display(column: ColumnInfo) -> str:
    """One completion row for `column`: its name, then the attributes it
    actually carries, ``·``-separated -- e.g.
    ``dept_id  integer · NOT NULL · -> hr.dept.id``.

    Everything here is already on `ColumnInfo` (§18.1's widened introspection);
    nothing is fetched. Attributes are omitted rather than negated: a nullable
    column says nothing, only a NOT NULL one does, so the common row stays
    short and the unusual one stands out.
    """
    parts = [column.data_type]
    if column.is_pk:
        parts.append("PK")
    if column.fk_target:
        parts.append(f"→ {column.fk_target}")
    elif column.is_fk:
        parts.append("FK")
    if not column.is_nullable:
        parts.append("NOT NULL")
    if column.default:
        parts.append(f"default {_elide(column.default)}")
    if column.comment:
        parts.append(_elide(column.comment))
    detail = " · ".join(part for part in parts if part)
    return f"{column.name}  {detail}" if detail else column.name
