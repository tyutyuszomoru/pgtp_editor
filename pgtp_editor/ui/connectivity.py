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

# pgtp_editor/ui/connectivity.py
"""The status bar's two live connectivity dots — Quality and Sandbox
(FQ-018, as refined by FQ-028 Part 2.4).

**It re-derives nothing.** The three states each dot can show are §18.8's, read
straight off `ui/project_status_model.py`'s `QualityState` and `SandboxState`,
so the status bar and the Project Status window can never hold two drifting
notions of "connected". This module owns only the RENDERING and one extra
state the window has no need for:

* `UNKNOWN` — the poll has not answered yet (a project was just opened, the
  window has just regained focus, a probe is in flight). The status bar's rule
  is that a slot always states a defined fact, so "we have not checked yet" is
  shown as a defined fact — a hollow grey dot with a tooltip that says so —
  rather than as a blank or as a stale green.

**Both dots are project-mode only** (FQ-028 overriding FQ-018): they are
present when a project is actually OPEN and absent otherwise — visibility, never
a greyed-out third posture. "Actually open" means `DdlProjectController.is_open`,
NOT the "Project" workflow-mode label: the two can legitimately disagree.

**Green means REACHABLE, not fully capable.** The 30 s poll is a `SELECT 1`
round trip. The heavy `db/sandbox.py::probe()` — superuser, pg_dump/pg_restore
discovery, `degraded_reason` — stays on explicit user action in the Project
Status window, so a dot can be green while that window still reports a
capability degradation.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from .project_status_model import QualityState, SandboxState

#: The glyph. A filled dot for a known state, a hollow one for "not checked".
DOT = "●"
DOT_UNKNOWN = "○"

#: The extra state that is this module's own (see the docstring).
UNKNOWN = "unknown"

#: Node labels, matching §18.8's node names so the two surfaces read alike.
QUALITY_LABEL = "Quality"
SANDBOX_LABEL = "Sandbox"

#: state -> (colour, glyph, tooltip). White = not set up, red = offline,
#: green = reachable, grey hollow = not checked yet.
_RENDERING = {
    UNKNOWN: ("#9E9E9E", DOT_UNKNOWN, "not checked yet"),
    QualityState.NOT_SET_UP: ("#FFFFFF", DOT, "no connection configured"),
    QualityState.OFFLINE: ("#D02020", DOT, "offline"),
    QualityState.CONNECTION_OK: ("#2E9E4F", DOT, "reachable"),
    SandboxState.NOT_SET_UP: ("#FFFFFF", DOT, "no sandbox configured"),
    SandboxState.OFFLINE: ("#D02020", DOT, "offline"),
    SandboxState.CONNECTED: ("#2E9E4F", DOT, "reachable"),
}


def dot_rendering(state) -> tuple[str, str, str]:
    """`(colour, glyph, tooltip)` for `state`; UNKNOWN's for anything else — a
    state this module does not know is not a reason to claim connectivity."""
    return _RENDERING.get(state, _RENDERING[UNKNOWN])


def sandbox_state_for(configured: bool, probe_error: str | None) -> SandboxState:
    """The sandbox's state from the same two facts `quality_state` takes.

    Deliberately shaped like `project_status_model.quality_state` — the sandbox
    node's own classifier there works off `ProjectCapabilityStatus.
    degraded_reason`, which the lightweight 30 s poll does not compute — so the
    poll's two-fact answer maps onto the SAME `SandboxState` enum the window
    renders, instead of inventing a parallel one.
    """
    if not configured:
        return SandboxState.NOT_SET_UP
    if probe_error is not None:
        return SandboxState.OFFLINE
    return SandboxState.CONNECTED


class ConnectivityIndicator(QLabel):
    """One labelled dot — `Quality ●` / `Sandbox ●`."""

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self._label = label
        self._state = UNKNOWN
        self.setObjectName(f"connectivity_{label.lower()}")
        self._render()

    @property
    def state(self):
        return self._state

    def set_state(self, state) -> None:
        self._state = state
        self._render()

    def _render(self) -> None:
        colour, glyph, tooltip = dot_rendering(self._state)
        self.setText(f"{self._label} {glyph}")
        self.setStyleSheet(f"QLabel {{ color: {colour}; padding: 1px 6px; }}")
        self.setToolTip(f"{self._label}: {tooltip}")
