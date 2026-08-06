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

# pgtp_editor/mcp/providers.py
"""Where a tool call's `ProjectModel` comes from (§23).

§23 requires the same six tools to work in two modes: "when the GUI is running
it shares the currently-open in-memory model; running headless it operates
file-path-driven instead". Rather than branch on that inside every tool, the
model source is a *provider* injected into the registry — `FileProjectProvider`
headless, `LiveProjectProvider` under the GUI.

Both satisfy one method::

    resolve(path: str | None) -> ResolvedProject(path, project)

`LiveProjectProvider` answers from the open editor when `path` is omitted or
names the open file, and otherwise falls back to loading from disk — so an MCP
client can still diff the open project against some other file. Neither
provider imports Qt: the GUI one is handed a plain zero-argument callable, and
`MainWindow` supplies it in one line (see this package's `__init__`).
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from pgtp_editor.model.parser import load_project


class ProjectUnavailableError(Exception):
    """No project could be resolved for a tool call — no path was given and no
    project is open, or the path does not exist. Surfaced to the client as a
    tool error, never as a crash.
    """


@dataclass(frozen=True)
class ResolvedProject:
    """A parsed project plus the path it came from (`None` for an unsaved
    in-memory project shared by the GUI)."""

    path: str | None
    project: object


def _same_file(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
        os.path.abspath(right)
    )


class FileProjectProvider:
    """Headless mode: every tool call names a `.pgtp` path, which is parsed
    with the same `model.parser.load_project` the GUI uses.

    No caching — a `.pgtp` is small, an MCP client may be watching a file that
    another process is editing, and a stale cache would be its own bug class.
    """

    def resolve(self, path: str | None) -> ResolvedProject:
        if not path:
            raise ProjectUnavailableError(
                "a 'path' to a .pgtp file is required when no project is open"
            )
        if not os.path.isfile(path):
            raise ProjectUnavailableError(f"no such .pgtp file: {path}")
        return ResolvedProject(path=str(path), project=load_project(path))


class LiveProjectProvider:
    """GUI mode: shares the currently-open in-memory model.

    `getter` is any zero-argument callable returning `(path, project)` — for
    `MainWindow` that is
    `lambda: (window._current_project_path, window._current_project)`. A
    `(None, None)`/`(path, None)` answer means nothing is open, in which case
    this behaves exactly like `FileProjectProvider` (a path-driven call still
    works, a path-less one is an error).
    """

    def __init__(self, getter: Callable[[], tuple[str | None, object | None]]):
        self._getter = getter
        self._fallback = FileProjectProvider()

    def resolve(self, path: str | None) -> ResolvedProject:
        open_path, open_project = self._getter()
        if open_project is not None and (not path or _same_file(path, open_path)):
            return ResolvedProject(path=open_path, project=open_project)
        return self._fallback.resolve(path)
