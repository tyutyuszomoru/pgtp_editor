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

# pgtp_editor/db/ddl_buffer.py
"""Synthesize one browsable text buffer from a `DatabaseSchema`'s routines and
triggers, with a structural span index over it (§18.1 DDL Explorer).

Plays the same role for the DDL buffer that `TagSpan` (`ui/xml_structure.py`,
§8) plays for the Raw XML buffer: one shared text document plus a line-indexed
span per object, so a tree (`ui/ddl_buffer_panel.py::BrowserPanel`) can
navigate into a single `CodeEditor` (`ui/ddl_editor_panel.py::EditorPanel`) by
line number instead of opening a bespoke viewer per routine/trigger.

Pure and Qt-free: no I/O, no database access -- this module only formats
already-introspected `RoutineInfo`/`TriggerInfo` rows into text + spans.
"""
from __future__ import annotations

from dataclasses import dataclass

from .introspect import DatabaseSchema, RoutineInfo, TriggerInfo


@dataclass(frozen=True)
class DdlObjectSpan:
    kind: str  # "function" | "procedure" | "trigger"
    schema: str
    name: str
    table: str | None  # triggers only -- the table the trigger fires on
    start_line: int  # 1-based; the banner comment line
    end_line: int  # 1-based, inclusive; the source text's last line


def _banner(kind: str, schema: str, name: str, *, table: str | None, arg_types: list[str] | None) -> str:
    if kind == "trigger":
        return f"-- TRIGGER {schema}.{name} ON {table} --"
    label = "FUNCTION" if kind == "function" else "PROCEDURE"
    args = ", ".join(arg_types or [])
    return f"-- {label} {schema}.{name}({args}) --"


def build_ddl_text(schema: DatabaseSchema) -> tuple[str, list[DdlObjectSpan]]:
    """Synthesize one text buffer concatenating every routine + trigger
    definition, each preceded by a banner comment anchoring its span.

    Deterministic order: schema, then kind (functions/procedures before
    triggers within a schema), then name.
    """
    items: list[tuple[str, RoutineInfo | TriggerInfo]] = [
        ("routine", routine) for routine in schema.routines.values()
    ]
    items += [("trigger", trigger) for trigger in schema.triggers.values()]
    items.sort(key=lambda item: (item[1].schema, 0 if item[0] == "routine" else 1, item[1].name))

    lines: list[str] = []
    spans: list[DdlObjectSpan] = []
    for tag, obj in items:
        is_trigger = tag == "trigger"
        kind = "trigger" if is_trigger else obj.kind
        table = obj.table if is_trigger else None
        arg_types = None if is_trigger else obj.arg_types
        source = obj.definition if is_trigger else obj.source

        lines.append(_banner(kind, obj.schema, obj.name, table=table, arg_types=arg_types))
        start_line = len(lines)
        lines.extend(source.splitlines() or [""])
        end_line = len(lines)
        lines.append("")  # blank separator before the next object

        spans.append(
            DdlObjectSpan(
                kind=kind,
                schema=obj.schema,
                name=obj.name,
                table=table,
                start_line=start_line,
                end_line=end_line,
            )
        )

    return "\n".join(lines), spans
