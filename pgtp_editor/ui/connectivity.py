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
  shown as a defined fact — a hollow circle in a legible neutral, with a tooltip
  that says so — rather than as a blank or as a stale green.

  The instinct is to render "provisional" as *dim*; BUG-260812103144 is what
  that costs. The provisional cue lives entirely in the HOLLOW GLYPH, and the
  colour is a neutral that clears 4.5:1 — the old `#9E9E9E` scored 2.93:1 on the
  dark status bar and 1.53:1 on the light one.

**Every colour here is per-theme, and measured against the STATUS BAR, not the
window.** qdarkstyle draws `QStatusBar { background: COLOR_BACKGROUND_4 }` and
leaves `QStatusBar QLabel` transparent, so the pixels behind a dot are the
mid-tone `#455364` / `#C0C4C8` — not `COLOR_BACKGROUND_1`. Measuring against the
window chrome is what let a 1.46:1 offline dot read as 2.96:1. And the threshold
is **4.5:1, text**, not 3:1 graphical: `_render` colours the whole label, so the
word "Quality"/"Sandbox" is painted in the state colour too.

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

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from .project_status_model import QualityState, SandboxState
from .status_colours import StatusLabel
from .theme_model import theme_for

#: The glyphs — **one shape per state, because colour is not a channel every
#: user has** (BUG-260812103144). Until this fix `NOT_SET_UP`, `OFFLINE` and
#: `REACHABLE` all drew the same filled `●` and were told apart by hue alone,
#: and the pair carrying the most meaning was red-vs-green: the single most
#: common colour-vision confusion. The tooltip disambiguated, but only on hover,
#: which defeats the whole point of an at-a-glance indicator.
#:
#: All four come from Unicode's Geometric Shapes block, which DejaVu Sans and
#: Segoe UI both cover — a glyph that renders as a tofu box is worse than the
#: colour-only design it replaced. The mapping reads as a sentence: a filled
#: circle is a live connection, a triangle is the universal "something is
#: wrong", a hollow square is an empty slot (nothing configured), and a hollow
#: circle is the open question (not checked yet).
DOT = "●"
DOT_UNKNOWN = "○"
DOT_OFFLINE = "▲"
DOT_NOT_SET_UP = "□"

#: The extra state that is this module's own (see the docstring).
UNKNOWN = "unknown"

#: Node labels, matching §18.8's node names so the two surfaces read alike.
QUALITY_LABEL = "Quality"
SANDBOX_LABEL = "Sandbox"

#: state -> (accent KEY, glyph, tooltip). The theme-independent half of the
#: rendering: which colour to ask the live theme for, which shape to draw, and
#: what to say on hover.
#:
#: **The key, not the value** (BUG-260812103144). These four accents used to be
#: read once at import through `theme_model.shared_accent`, which returns a value
#: only while every bundled theme agrees on it — the right reader for a
#: theme-BLIND consumer, and exactly the wrong one here, because the dots must
#: now differ per theme to be legible at all. Resolving at import also froze
#: them: nothing re-read the table, so a runtime theme flip left the dots
#: painting whichever theme happened to be loaded first. Naming the key and
#: resolving on demand fixes both.
_RENDERING = {
    UNKNOWN: ("connectivity_unknown", DOT_UNKNOWN, "not checked yet"),
    QualityState.NOT_SET_UP: (
        "connectivity_not_set_up", DOT_NOT_SET_UP, "no connection configured",
    ),
    QualityState.OFFLINE: ("connectivity_offline", DOT_OFFLINE, "offline"),
    QualityState.CONNECTION_OK: ("connectivity_reachable", DOT, "reachable"),
    SandboxState.NOT_SET_UP: (
        "connectivity_not_set_up", DOT_NOT_SET_UP, "no sandbox configured",
    ),
    SandboxState.OFFLINE: ("connectivity_offline", DOT_OFFLINE, "offline"),
    SandboxState.CONNECTED: ("connectivity_reachable", DOT, "reachable"),
}


def dot_rendering(state, light: bool) -> tuple[str, str, str]:
    """`(colour, glyph, tooltip)` for `state` under the light/dark theme;
    UNKNOWN's for anything else — a state this module does not know is not a
    reason to claim connectivity.

    Pure and Qt-free, so a test can pin the contrast of all four states in both
    themes without building a widget. `light` is not optional and has no default
    on purpose: a caller that does not know which theme it is painting under
    cannot pick a legible colour, and a default would let one silently ship the
    other theme's value — the very freeze this signature replaced.
    """
    key, glyph, tooltip = _RENDERING.get(state, _RENDERING[UNKNOWN])
    return theme_for(light).accent(key), glyph, tooltip


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


class ConnectivityIndicator(StatusLabel):
    """One labelled dot — `Quality ●` / `Sandbox ▲`.

    **A `StatusLabel`, not a `QLabel`** (BUG-260812103144). The moment the four
    colours became per-theme, this widget needed exactly the machinery
    `ui/status_colours.py` already carries — recompute from the LIVE palette on
    every `changeEvent`, bound the re-entrancy `setStyleSheet` causes by
    re-polishing, and re-apply once more from a timer bound to `self` because on
    dark→light the nested event is the first one carrying the new palette. Each
    of those three was a real, measured failure; hand-rolling a second
    `changeEvent` here would have been the third time. Only the *derivation* is
    ours, through the `_colour_for` hook: a connectivity STATE, not a status
    kind.
    """

    def __init__(self, label: str, parent=None) -> None:
        super().__init__("", parent)
        self._label = label
        self._state = UNKNOWN
        self.setObjectName(f"connectivity_{label.lower()}")
        # `StatusLabel` writes `QLabel { color: … }` and nothing else, where
        # `_render` used to declare `padding: 1px 6px` in the same sheet.
        # Contents margins carry it instead — dropping it silently changes the
        # status bar's spacing.
        self.setContentsMargins(6, 1, 6, 1)
        self._render()

    @property
    def state(self):
        return self._state

    def set_state(self, state) -> None:
        self._state = state
        self._render()

    def _palette_is_light(self) -> bool:
        """The theme's lightness from the APPLICATION palette — the one place
        these dots must diverge from `StatusLabel`, and a measured necessity.

        `StatusLabel` reads `self.palette()`, which is right for a dialog label
        and useless here for two compounding reasons. qdarkstyle declares
        `QStatusBar QLabel { background: transparent }`, so a dot's background
        roles resolve to **`#000000` in BOTH themes** (`Base`, `Window` and
        `Button` all measured black under dark AND light); and the widget-level
        `QLabel { color: … }` this class writes lands in the label's own `Text`/
        `WindowText` roles, so reading them back reports **the colour we just
        painted** rather than the theme — a circular read that froze the dots on
        whichever value was applied first (measured: `#D2D5D8`, dark's neutral,
        under the light theme).

        `QApplication.palette()` is the live palette the theme was applied to, so
        it is still a paint-time read of the real thing and not a cached
        lightness — which is the property that matters (BUG-260811021804).
        """
        app = QApplication.instance()
        palette = app.palette() if app is not None else self.palette()
        return palette.color(QPalette.ColorRole.Base).lightness() > 128

    def _colour_for(self, light: bool) -> str | None:
        """`StatusLabel`'s derivation hook: the state's colour under the theme
        the live palette reports. Read afresh every time — a resolved colour
        kept across a flip is the previous theme's (BUG-260811021804)."""
        return dot_rendering(getattr(self, "_state", UNKNOWN), light)[0]

    def _render(self) -> None:
        """The state's text and tooltip, then the colour through the inherited
        machinery. Only the colour is theme-dependent; the glyph is the state's
        second channel and reads the same under every theme."""
        _colour, glyph, tooltip = dot_rendering(self._state, self._palette_is_light())
        self.setText(f"{self._label} {glyph}")
        self.setToolTip(f"{self._label}: {tooltip}")
        self._apply_status_colour()
