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

# pgtp_editor/ui/mode_indicator.py
"""The colour-coded major/minor mode indicator (FQ-028 Part 2, absorbing
FQ-029).

**One source of truth, two surfaces.** The host answers "what mode am I in?"
exactly once — `MainWindow.current_mode()` — and hands the answer to both a
right-anchored panel pinned into the Main Toolbar and the status bar's
`_mode_label`. Neither surface derives anything; they render what they are
given, through the same `ModeIndicator.set_mode(...)` call. That is what stops
the toolbar and the status bar ever disagreeing.

**Mode terminology is §7's, and gains no fifth meaning.**

* **Major mode** = the SESSION workflow mode FQ-027's launcher sets:
  Standalone / Project / Maintenance, read from `MainWindow.workflow_mode`.
  It is in-memory and session-only — there is no QSettings key and this module
  introduces none.
* **Minor mode** = an active editor SUB-STATE, and only when there is one:
  Caption (§13), Compare/Merge (§12/FQ-021), Edit XSD (§11). "Editing" is the
  absence of a minor mode, not a fourth one.

**Passive only.** No click handler, no context menu, no way to change mode from
either surface (owner ruling). Mode changes stay with the launcher pick and
`File ▸ New Session`.

**Theme-aware.** `mode_colors(light)` mirrors `theme.py`'s pure
`light_palette()`/`dark_palette()` split — it builds and returns, touching no
application state — and is re-consulted whenever `apply_theme` flips, so the
chip is never the DEBUG chip's hardcoded red that reads wrong in one theme.

**Minor mode is TEXT, not a second colour** (FQ-028's recommendation, kept):
the background is the MAJOR mode's, and the minor mode is appended after a
middle dot — "Project · Caption". Three majors times four editor sub-states
would be a twelve-colour vocabulary, which defeats "easy recognition". The
major mode is the one a colour must answer at a glance.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

#: The three major modes, spelled as `launcher_dialog.MODE_*` does. Imported
#: lazily by the host (constructing a window must never pull the launcher in),
#: so they are re-stated here as plain strings rather than imported.
MODE_STANDALONE = "standalone"
MODE_PROJECT = "project"
MODE_MAINTENANCE = "maintenance"

#: What the user reads for each major mode.
MAJOR_LABELS = {
    MODE_STANDALONE: "Standalone",
    MODE_PROJECT: "Project",
    MODE_MAINTENANCE: "Maintenance",
}

#: FQ-028 open question 8, decided: the indicator is NEVER blank. Before a
#: launcher column is picked there is still a defined fact — no workflow mode
#: has been chosen — and the status bar's rule is that a slot always states
#: something. "No Mode" says it, in the neutral palette below.
NO_MODE_LABEL = "No Mode"

#: The minor modes, in the order the host checks them.
MINOR_CAPTION = "Caption"
MINOR_DIFF = "Compare/Merge"
MINOR_XSD = "Edit XSD"

#: The separator between major and minor.
MODE_SEPARATOR = " · "

#: Per-mode (background, foreground), per theme. The starting palette FQ-028
#: proposed, tuned only for the neutral no-mode entry. Keyed by the major mode,
#: with `None` for "no column picked yet".
_LIGHT_COLORS = {
    None: ("#E8E8E8", "#3A3A3A"),
    MODE_STANDALONE: ("#E3F2FD", "#0D3B66"),
    MODE_PROJECT: ("#E6F4EA", "#1B5E20"),
    MODE_MAINTENANCE: ("#FDECEA", "#8B1E1E"),
}

_DARK_COLORS = {
    None: ("#3A3A3A", "#D8D8D8"),
    MODE_STANDALONE: ("#1E3A5F", "#CFE3FF"),
    MODE_PROJECT: ("#1E3A28", "#B6E3C0"),
    MODE_MAINTENANCE: ("#3A2320", "#F2B8AE"),
}


def mode_colors(light: bool) -> dict[str | None, tuple[str, str]]:
    """The `{major mode: (background, foreground)}` palette for the theme.

    Pure — builds and returns a fresh dict, mutating nothing, exactly as
    `theme.py::light_palette()` does with its QPalette.
    """
    source = _LIGHT_COLORS if light else _DARK_COLORS
    return dict(source)


def mode_text(major: str | None, minor: str | None = None) -> str:
    """What both surfaces read: the major mode, plus the minor one when there
    is one.

    An unknown major-mode string is shown verbatim rather than swallowed — a
    mode the indicator cannot name is a bug worth seeing, not worth hiding.
    """
    label = MAJOR_LABELS.get(major, major) if major is not None else NO_MODE_LABEL
    if minor:
        return f"{label}{MODE_SEPARATOR}{minor}"
    return str(label)


def mode_stylesheet(background: str, foreground: str) -> str:
    """The chip's QSS. One spelling for both surfaces."""
    return (
        "QLabel { color: %s; background: %s; padding: 1px 8px;"
        " border-radius: 3px; font-weight: bold; }" % (foreground, background)
    )


class ModeIndicator(QLabel):
    """One rendering of the current mode. Two exist: the toolbar panel and the
    status-bar mirror. Both are driven by the same `set_mode` call from the
    host's single `_refresh_mode_indicator`."""

    def __init__(self, parent=None, *, light: bool = False) -> None:
        super().__init__(parent)
        self._light = bool(light)
        self._major: str | None = None
        self._minor: str | None = None
        self.setObjectName("mode_indicator")
        self._render()

    # -- the surface the host drives ----------------------------------------
    def set_mode(self, major: str | None, minor: str | None = None) -> None:
        """Show `major` (colour + text) and `minor` (text only)."""
        self._major = major
        self._minor = minor
        self._render()

    def set_light_theme(self, light: bool) -> None:
        """Re-render in the other theme's palette."""
        self._light = bool(light)
        self._render()

    @property
    def major(self) -> str | None:
        return self._major

    @property
    def minor(self) -> str | None:
        return self._minor

    def colors(self) -> tuple[str, str]:
        """The `(background, foreground)` currently painted — what a contrast
        check and a theme test read."""
        palette = mode_colors(self._light)
        return palette.get(self._major, palette[None])

    def _render(self) -> None:
        self.setText(mode_text(self._major, self._minor))
        background, foreground = self.colors()
        self.setStyleSheet(mode_stylesheet(background, foreground))
        self.setToolTip(
            "Workflow mode (File ▸ New Session to change it)"
            if self._minor is None
            else f"Workflow mode: {mode_text(self._major)} — active editor mode: {self._minor}"
        )
