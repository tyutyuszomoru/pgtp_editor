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

# pgtp_editor/mcp/tools.py
"""The six §23 MCP tools and the registry that dispatches them.

This is the part of §23 that carries the meaning: a **thin adapter** over the
already-Qt-free pure layers, with **no new business logic**. Every handler
below does exactly three things — resolve its inputs, make one call into
`model/`, `diff/`, `analysis/` or `db/`, and hand the result to
`serialize.py`. If a future tool needs to *compute* something, that
computation belongs in the pure layer, not here.

The six, all read-only:

===========================  ====================================================
`read_project(path)`         `model.parser.load_project` + `analysis.reused_tables`
`list_pages(path)`           the resolved model's `.pages`
`get_node(path, identity)`   an identity lookup over that same model
`diff_projects(source,       `diff.differ.diff_project`
  target)`
`list_db_tables(connection)` `db.introspect.fetch_routines_and_triggers` → `.tables`
`list_db_routines(...)`      the same fetch → `.routines` / `.triggers`
===========================  ====================================================

**Nothing here writes.** There is deliberately no tool that runs arbitrary SQL,
deploys, or touches a file — §18.3's never-auto-execute posture holds for the
whole project, and an MCP client is exactly the kind of caller it exists to
guard against. **Nothing here handles a password** beyond passing the caller's
own connection dict straight to `db/introspect.py`; every rendering of a
connection goes through `serialize.connection_identity`.

Both database tools take an injectable `introspector=` — the same seam
`db/introspect.py` offers with `runner=`, one level up — so tests drive canned
`DatabaseSchema` objects and no live database (or psycopg, or Qt) is needed.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pgtp_editor.analysis.reused_tables import collect_table_usages
from pgtp_editor.diff.differ import diff_project
from pgtp_editor.mcp import serialize
from pgtp_editor.mcp.providers import FileProjectProvider

_CONNECTION_FIELDS = ("host", "port", "database", "user", "password")


class UnknownToolError(Exception):
    """The client asked for a tool name this registry does not serve."""


class ToolArgumentError(Exception):
    """The client's arguments were missing, unexpected, or the wrong shape."""


# ---------------------------------------------------------------------------
# connection handling
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Connection:
    """A duck-typed stand-in for `db.config.ConnectionParams`.

    Declared here rather than imported because `db/config.py` imports
    `PySide6.QtCore.QSettings`, and the headless `--mcp` mode must not drag Qt
    in. `db/introspect.py` only ever reads the five attribute names, so a plain
    dataclass is interchangeable — the same duck-typing
    `db/migration_gen.py::connection_summary` already relies on.

    `repr` is suppressed on `password` so the field cannot reach a log line,
    an exception message, or a traceback frame dump by accident.
    """

    host: str = ""
    port: str = ""
    database: str = ""
    user: str = ""
    password: str = field(default="", repr=False)


def _connection_from(arguments: Any) -> _Connection:
    if not isinstance(arguments, dict):
        raise ToolArgumentError("'connection' must be an object")
    unexpected = sorted(set(arguments) - set(_CONNECTION_FIELDS))
    if unexpected:
        raise ToolArgumentError(
            f"unexpected connection field(s): {', '.join(unexpected)}"
        )
    values = {}
    for name in _CONNECTION_FIELDS:
        value = arguments.get(name, "")
        if value is None:
            value = ""
        if not isinstance(value, (str, int)):
            raise ToolArgumentError(f"connection.{name} must be a string")
        values[name] = str(value)
    return _Connection(**values)


def _default_introspector(params):
    """Lazy real introspection — imported inside the call so importing this
    package costs neither psycopg nor (via `db/config.py`) Qt."""
    from pgtp_editor.db.introspect import (  # noqa: PLC0415 — lazy on purpose
        fetch_routines_and_triggers,
    )

    return fetch_routines_and_triggers(params)


# ---------------------------------------------------------------------------
# identity lookup
# ---------------------------------------------------------------------------

def _walk(project):
    """Yield `(identity, node, kind)` for every node in document order.

    Traversal only — the identities are the ones `model/parser.py` already
    assigned at parse time; nothing is derived or recomputed here.
    """

    def visit_container(node, kind):
        yield node.identity, node, kind
        for column in node.columns:
            yield column.identity, column, "column"
        for event in node.events:
            yield event.identity, event, "event"
        for detail in node.details:
            yield from visit_container(detail, "detail")

    for page in project.pages:
        yield from visit_container(page, "page")


# ---------------------------------------------------------------------------
# the tools
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Tool:
    """One MCP tool: its wire descriptor plus the handler to run."""

    name: str
    description: str
    input_schema: dict
    handler: Callable[..., dict]
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()

    def descriptor(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class ToolRegistry:
    """The dispatch table an MCP transport talks to.

    Constructing one starts nothing and connects to nothing — §23's
    "off by default, must not be silent" begins here: the registry is inert
    data until a transport calls `call()`.
    """

    def __init__(self, tools):
        self._tools = {tool.name: tool for tool in tools}

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def descriptors(self) -> list[dict]:
        """The `tools/list` payload."""
        return [tool.descriptor() for tool in self._tools.values()]

    def call(self, name: str, arguments: dict | None = None) -> dict:
        """Run one tool. Raises `UnknownToolError` for an unserved name and
        `ToolArgumentError` for bad arguments; the transport turns both into
        protocol errors rather than letting them escape as crashes.
        """
        tool = self._tools.get(name)
        if tool is None:
            served = ", ".join(sorted(self._tools))
            raise UnknownToolError(f"unknown tool: {name!r} (served: {served})")
        arguments = dict(arguments or {})
        missing = [key for key in tool.required if key not in arguments]
        if missing:
            raise ToolArgumentError(
                f"{name}: missing required argument(s): {', '.join(missing)}"
            )
        allowed = set(tool.required) | set(tool.optional)
        unexpected = sorted(set(arguments) - allowed)
        if unexpected:
            raise ToolArgumentError(
                f"{name}: unexpected argument(s): {', '.join(unexpected)}"
            )
        return tool.handler(**arguments)


def build_registry(provider=None, *, introspector=None) -> ToolRegistry:
    """Assemble the six §23 tools around a model `provider` (see
    `providers.py`) and an `introspector` callable `(params) -> DatabaseSchema`.

    Defaults are the headless ones: file-path-driven projects and real
    `db.introspect.fetch_routines_and_triggers`. The GUI passes a
    `LiveProjectProvider`; tests pass fakes.
    """
    provider = provider if provider is not None else FileProjectProvider()
    introspect = introspector if introspector is not None else _default_introspector

    def read_project(path: str | None = None) -> dict:
        resolved = provider.resolve(path)
        project = resolved.project
        return {
            "path": resolved.path,
            "page_count": len(project.pages),
            "pages": [serialize.page_summary(page) for page in project.pages],
            "tables": [
                serialize.table_usage(usage)
                for usage in collect_table_usages(project)
            ],
        }

    def list_pages(path: str | None = None) -> dict:
        resolved = provider.resolve(path)
        return {
            "path": resolved.path,
            "page_count": len(resolved.project.pages),
            "pages": [serialize.page_summary(p) for p in resolved.project.pages],
        }

    def get_node(identity: str, path: str | None = None) -> dict:
        resolved = provider.resolve(path)
        for node_identity, node, kind in _walk(resolved.project):
            if node_identity == identity:
                return {"path": resolved.path, "node": serialize.node_detail(node, kind)}
        raise ToolArgumentError(f"no node with identity {identity!r}")

    def diff_projects(source: str, target: str) -> dict:
        source_resolved = provider.resolve(source)
        target_resolved = provider.resolve(target)
        differences = diff_project(source_resolved.project, target_resolved.project)
        return {
            "source": source_resolved.path,
            "target": target_resolved.path,
            "difference_count": len(differences),
            "differences": [serialize.difference(d) for d in differences],
        }

    def list_db_tables(connection: dict) -> dict:
        params = _connection_from(connection)
        schema = introspect(params)
        tables = getattr(schema, "tables", {}) or {}
        return {
            "connection": serialize.connection_identity(params),
            "table_count": len(tables),
            "tables": [serialize.table_info(tables[name]) for name in sorted(tables)],
        }

    def list_db_routines(connection: dict) -> dict:
        params = _connection_from(connection)
        schema = introspect(params)
        routines = getattr(schema, "routines", {}) or {}
        triggers = getattr(schema, "triggers", {}) or {}
        return {
            "connection": serialize.connection_identity(params),
            "routine_count": len(routines),
            "routines": [
                serialize.routine_info(routines[key]) for key in sorted(routines)
            ],
            "trigger_count": len(triggers),
            "triggers": [
                serialize.trigger_info(triggers[key]) for key in sorted(triggers)
            ],
        }

    path_property = {
        "type": "string",
        "description": (
            "Path to a .pgtp file. Optional when the editor GUI has a project "
            "open, in which case that in-memory project is used."
        ),
    }
    connection_property = {
        "type": "object",
        "description": (
            "PostgreSQL connection parameters (host, port, database, user, "
            "password). Read-only introspection only; the password is used to "
            "connect and is never echoed back."
        ),
        "properties": {name: {"type": "string"} for name in _CONNECTION_FIELDS},
    }

    return ToolRegistry(
        [
            Tool(
                name="read_project",
                description=(
                    "Parse a .pgtp project and return its pages plus the "
                    "tables/views each one references."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"path": path_property},
                },
                handler=read_project,
                optional=("path",),
            ),
            Tool(
                name="list_pages",
                description="List the pages of a .pgtp project.",
                input_schema={
                    "type": "object",
                    "properties": {"path": path_property},
                },
                handler=list_pages,
                optional=("path",),
            ),
            Tool(
                name="get_node",
                description=(
                    "Return one node (page, detail, column or event) of a "
                    "project by its identity, with its attributes."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": path_property,
                        "identity": {
                            "type": "string",
                            "description": (
                                "Node identity as reported by read_project / "
                                "list_pages / get_node."
                            ),
                        },
                    },
                    "required": ["identity"],
                },
                handler=get_node,
                required=("identity",),
                optional=("path",),
            ),
            Tool(
                name="diff_projects",
                description=(
                    "Compare two .pgtp projects and return the list of "
                    "differences (added / removed / changed)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source .pgtp path."},
                        "target": {"type": "string", "description": "Target .pgtp path."},
                    },
                    "required": ["source", "target"],
                },
                handler=diff_projects,
                required=("source", "target"),
            ),
            Tool(
                name="list_db_tables",
                description=(
                    "Introspect a PostgreSQL database (read-only) and list its "
                    "tables, views and materialized views with their columns."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"connection": connection_property},
                    "required": ["connection"],
                },
                handler=list_db_tables,
                required=("connection",),
            ),
            Tool(
                name="list_db_routines",
                description=(
                    "Introspect a PostgreSQL database (read-only) and list its "
                    "functions, procedures and triggers with their source."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"connection": connection_property},
                    "required": ["connection"],
                },
                handler=list_db_routines,
                required=("connection",),
            ),
        ]
    )
