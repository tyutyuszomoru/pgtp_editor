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

# pgtp_editor/mcp/__init__.py
"""§23's optional embedded MCP server — off by default, opt-in, read-only.

The server exposes project data to any connected MCP client, so §23 is
explicit that it "must not be silent or default-on". That is a structural
property of this package, not a setting: **importing anything here starts
nothing** — no server, no thread, no socket, no database connection. A session
begins only when a caller explicitly runs `serve_stdio` (headless `--mcp`) or
`start_server_thread` (Tools ▸ "Start MCP Server").

Layout:

* `tools.py` — the six §23 tools and their registry. A thin adapter over the
  Qt-free pure layers (`model/`, `diff/`, `analysis/`, `db/`) with no new
  business logic, and no knowledge of any wire protocol.
* `serialize.py` — pure data → JSON translation. Never renders a password.
* `providers.py` — where a tool's `ProjectModel` comes from: the GUI's open
  in-memory model, or a `.pgtp` path when headless.
* `server.py` — the stdio JSON-RPC transport, isolated so the adapter above
  stays protocol-agnostic (the `mcp` SDK is not a project dependency; see that
  module's docstring).

Wiring, one line each::

    # main.py, for `--mcp` (headless, file-path-driven):
    from pgtp_editor.mcp import serve_stdio; serve_stdio()

    # MainWindow, for Tools ▸ "Start MCP Server" (shares the open model):
    from pgtp_editor.mcp import LiveProjectProvider, start_server_thread
    self._mcp = start_server_thread(LiveProjectProvider(
        lambda: (self._current_project_path, self._current_project)))

Everything exposed is read-only: there is no tool that executes SQL, deploys,
or writes a file (§18.3's never-auto-execute posture), and connection identity
is only ever rendered password-free via `db/migration_gen.py`.
"""
from __future__ import annotations

from pgtp_editor.mcp.providers import (
    FileProjectProvider,
    LiveProjectProvider,
    ProjectUnavailableError,
    ResolvedProject,
)
from pgtp_editor.mcp.server import (
    PROTOCOL_VERSION,
    StdioServer,
    sdk_available,
    serve_stdio,
    start_server_thread,
)
from pgtp_editor.mcp.tools import (
    ToolArgumentError,
    ToolRegistry,
    UnknownToolError,
    build_registry,
)

__all__ = [
    "PROTOCOL_VERSION",
    "FileProjectProvider",
    "LiveProjectProvider",
    "ProjectUnavailableError",
    "ResolvedProject",
    "StdioServer",
    "ToolArgumentError",
    "ToolRegistry",
    "UnknownToolError",
    "build_registry",
    "sdk_available",
    "serve_stdio",
    "start_server_thread",
]
