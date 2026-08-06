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

# pgtp_editor/mcp/serialize.py
"""JSON-safe renderings of the model/diff/db data objects (§23).

Pure translation, no logic: every function here takes an object built by
`model/`, `diff/`, `analysis/` or `db/introspect.py` and returns plain
dicts/lists of JSON scalars. Nothing is computed that the source layer does
not already expose — §23's "thin adapter with no new business logic" applies
to this module most literally.

Two deliberate omissions, both structural:

* **lxml elements are never serialized.** Every node carries an `element`
  (and `ProjectModel` a `tree`); those are live parser handles, not data.
  Only `sourceline` crosses the wire, which is what a client needs to point
  a human at the right place in the file.
* **Passwords are never serialized.** Connection identity is rendered
  exclusively through `db/migration_gen.py::connection_summary`
  (`user@host:port/database`), the project's existing "never the password"
  helper. There is no code path here that reads a `password` attribute.
"""
from __future__ import annotations

from typing import Any

from pgtp_editor.db.migration_gen import connection_summary


# --------------------------------------------------------------------------
# model/ -- pages, details, columns, events
# --------------------------------------------------------------------------

def page_summary(page) -> dict:
    """One `PageNode` as a listing entry (no columns/events/details bodies)."""
    return {
        "kind": "page",
        "identity": page.identity,
        "caption": page.attrib.get("caption"),
        "file_name": page.file_name,
        "table_name": page.table_name,
        "sourceline": page.sourceline,
        "column_count": len(page.columns),
        "detail_count": len(page.details),
        "event_count": len(page.events),
    }


def detail_summary(detail) -> dict:
    """One `DetailNode` as a listing entry."""
    return {
        "kind": "detail",
        "identity": detail.identity,
        "caption": detail.attrib.get("caption"),
        "table_name": detail.table_name,
        "sourceline": detail.sourceline,
        "column_count": len(detail.columns),
        "detail_count": len(detail.details),
        "event_count": len(detail.events),
    }


def column_summary(column) -> dict:
    """One `ColumnNode` as a listing entry."""
    return {
        "kind": "column",
        "identity": column.identity,
        "field_name": column.field_name,
        "is_calculated": column.is_calculated,
        "sourceline": column.sourceline,
    }


def event_summary(event) -> dict:
    """One `EventNode` as a listing entry (metadata only, no handler body)."""
    return {
        "kind": "event",
        "identity": event.identity,
        "tag_name": event.tag_name,
        "side": event.side,
        "sourceline": event.sourceline,
    }


def _child_element(child) -> dict | None:
    if child is None:
        return None
    return {"attrib": dict(child.attrib), "sourceline": child.sourceline}


def node_detail(node, kind: str) -> dict:
    """A node rendered in full, for `get_node` — attributes plus one level of
    child summaries. The kind-specific extras mirror the Properties panel's
    view of the same node, and the handler body text is included for events
    (it is the only place a `.pgtp` keeps real code).
    """
    if kind == "page":
        return {
            **page_summary(node),
            "attrib": dict(node.attrib),
            "columns": [column_summary(c) for c in node.columns],
            "details": [detail_summary(d) for d in node.details],
            "events": [event_summary(e) for e in node.events],
        }
    if kind == "detail":
        return {
            **detail_summary(node),
            "attrib": dict(node.attrib),
            "columns": [column_summary(c) for c in node.columns],
            "details": [detail_summary(d) for d in node.details],
            "events": [event_summary(e) for e in node.events],
        }
    if kind == "column":
        return {
            **column_summary(node),
            "attrib": dict(node.attrib),
            "format": _child_element(node.format),
            "lookup": _child_element(node.lookup),
            "view_properties": _child_element(node.view_properties),
            "edit_properties": _child_element(node.edit_properties),
            "representations": [
                {
                    "name": rep.name,
                    "visible": rep.visible,
                    "sourceline": rep.sourceline,
                }
                for rep in node.representations
            ],
        }
    if kind == "event":
        return {**event_summary(node), "text": node.text}
    raise ValueError(f"unknown node kind: {kind}")


# --------------------------------------------------------------------------
# analysis/ -- table usages
# --------------------------------------------------------------------------

def table_usage(usage) -> dict:
    """One `analysis.reused_tables.TableUsage`. The `node` back-reference on
    each `TableReference` is dropped — it is a live model object, and the
    breadcrumb plus line already carry everything a client can act on.
    """
    return {
        "name": usage.name,
        "reference_count": len(usage.references),
        "references": [
            {
                "breadcrumb": ref.breadcrumb,
                "kind": ref.kind,
                "line": ref.line,
                "ref_type": ref.ref_type,
            }
            for ref in usage.references
        ],
    }


# --------------------------------------------------------------------------
# diff/ -- Difference records
# --------------------------------------------------------------------------

def _diff_value(value: Any) -> Any:
    """A `Difference.old_value`/`new_value` as JSON. For an attribute change
    these are plain strings; for an added/removed node they are the model node
    itself, which is rendered as its summary.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    for attribute, renderer in (
        ("file_name", page_summary),
        ("field_name", column_summary),
        ("tag_name", event_summary),
        ("table_name", detail_summary),
    ):
        if hasattr(value, attribute) and hasattr(value, "identity"):
            return renderer(value)
    return str(value)


def difference(diff) -> dict:
    """One `diff.records.Difference`."""
    return {
        "kind": diff.kind,
        "path": list(diff.path),
        "node_kind": diff.node_kind,
        "attribute": diff.attribute,
        "old_value": _diff_value(diff.old_value),
        "new_value": _diff_value(diff.new_value),
        "ambiguous": diff.ambiguous,
    }


# --------------------------------------------------------------------------
# db/ -- introspection results
# --------------------------------------------------------------------------

def connection_identity(params) -> str:
    """`user@host:port/database`, via the project's existing password-free
    renderer. The only way this package ever describes a connection.
    """
    return connection_summary(params)


def column_info(info) -> dict:
    return {
        "name": info.name,
        "data_type": info.data_type,
        "is_pk": info.is_pk,
        "is_fk": info.is_fk,
        "is_nullable": info.is_nullable,
        "default": info.default,
        "fk_target": info.fk_target,
        "comment": info.comment,
    }


def table_info(info) -> dict:
    return {
        "name": info.name,
        "kind": info.kind,
        "column_count": len(info.columns),
        "columns": [column_info(c) for c in info.columns],
        "view_definition": info.view_definition,
    }


def routine_info(info) -> dict:
    return {
        "signature": info.signature,
        "schema": info.schema,
        "name": info.name,
        "kind": info.kind,
        "language": info.language,
        "return_type": info.return_type,
        "arg_types": list(info.arg_types),
        "args": [list(pair) for pair in info.args],
        "source": info.source,
    }


def trigger_info(info) -> dict:
    return {
        "name": info.name,
        "schema": info.schema,
        "table": info.table,
        "timing": info.timing,
        "events": list(info.events),
        "function_name": info.function_name,
        "definition": info.definition,
    }
