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

**Mode terminology is §7's, and FQ-032 adds the ONE further meaning of "mode"
this vocabulary will ever take -- admitted deliberately, not smuggled.** The rule
is restated rather than broken: **the word `mode` is never used bare**, and each
of the three named dimensions is written with its adjective everywhere.

* **Major mode** = the SESSION workflow mode FQ-027's launcher sets:
  Standalone / Project / Maintenance, read from `MainWindow.workflow_mode`.
  It is in-memory and session-only — there is no QSettings key and this module
  introduces none.
* **Minor mode** = an active editor SUB-STATE, and only when there is one:
  Caption (§13), Compare/Merge (§12/FQ-021), Edit XSD (§11). "Editing" is the
  absence of a minor mode, not a fourth one.
* **Editing mode** (FQ-032, §8) = which keyboard vocabulary the FOCUSED editor is
  listening in: **Edit mode** (ordinary Windows-style typing) or **Command mode**
  (the `Esc`-entered vim command state). It is **per editor** and **orthogonal**
  to both rows above -- never winner-take-all -- and its source of truth is the
  editor itself, not this module and not `MainWindow`.

**The editing mode is a THIRD SEGMENT and it is TEXT, for the reason the minor
mode is.** `mode_colors` gains **no key**: three majors x four sub-states was
already twelve colours, and a colour per editing mode makes it twenty-four -- a
vocabulary nobody recognises at a glance is not an indicator.

**There are THREE surfaces since `DEC-260810193639`**, not two: the toolbar panel,
the status bar, and `CodeEditorDialog`'s own chrome. The third is the first
outside the main window and the first NOT driven by
`MainWindow._refresh_mode_indicator()`, which a dialog cannot reach. It renders
the **editing-mode segment only** (`editing_only=True`), never major/minor,
because the dialog is not a workflow surface. **That applies §7's one-source-of-
truth rule rather than excepting it:** the single `MainWindow` accessor owns
*major and minor*, while the editing mode's source of truth is the editor, so a
local render of a local fact cannot drift from anything. That chrome is
**load-bearing** -- the indicator plus its exit hint is the entire guard the owner
attached to giving the dialog Command mode.

**Passive only.** No click handler, no context menu, no way to change mode from
either surface (owner ruling). Mode changes stay with the launcher pick and
`File ▸ New Session`.

**Theme-aware.** `mode_colors(light)` mirrors `theme.py`'s pure
`light_palette()`/`dark_palette()` split — it builds and returns, touching no
application state — and is re-consulted whenever `apply_theme` flips, so the
chip is never the DEBUG chip's hardcoded red that reads wrong in one theme.

**Minor mode is TEXT, not a second colour** (FQ-028's recommendation, kept):
the background is the MAJOR mode's, and the minor mode is appended after a
middle dot — "Project mode · Caption". Three majors times four editor sub-states
would be a twelve-colour vocabulary, which defeats "easy recognition". The
major mode is the one a colour must answer at a glance.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from .theme_model import theme_for

#: The three major modes, spelled as `launcher_dialog.MODE_*` does. Imported
#: lazily by the host (constructing a window must never pull the launcher in),
#: so they are re-stated here as plain strings rather than imported.
MODE_STANDALONE = "standalone"
MODE_PROJECT = "project"
MODE_MAINTENANCE = "maintenance"

#: What the user reads for each major mode.
#:
#: **Every label says the word "mode" out loud** (`BUG-260810174126`, owner
#: report: *"Mode panel should explicitly say 'Mode' eg. 'Project mode' instead of
#: Project"*). A chip reading a bare "Project" does not tell a reader it is a mode
#: at all — it reads like the name of something. The pre-FQ-028 status label said
#: "Editing Mode" / "Caption Mode"; the FQ-028 rewrite dropped the word and this
#: restores it. Lowercase "mode" follows the report's own wording.
#:
#: `NO_MODE_LABEL` below is deliberately NOT re-cased to match — it already
#: carries the word, and re-wording it was explicitly out of scope.
MAJOR_LABELS = {
    MODE_STANDALONE: "Standalone mode",
    MODE_PROJECT: "Project mode",
    MODE_MAINTENANCE: "Maintenance mode",
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

#: The two editing modes' labels (FQ-032, §8). **The word "normal" is dropped
#: from this feature entirely** (owner-agreed): it collides with vim's own NORMAL
#: and would make every sentence ambiguous about which vocabulary it speaks.
#:
#: The Command-mode label carries the EXIT HINT inside it, and that is the whole
#: of the non-vim-user guard the owner accepted -- `Esc` -> Command mode is on for
#: everyone with no opt-out, no first-time dialog and no timeout, so a user who
#: presses `Esc` by reflex lands somewhere letters no longer type and the
#: indicator is the one thing on screen that says so and says the way out.
#: These say "mode" too, for `BUG-260810174126`'s reason and one more: the
#: `editing_only` rendering (`CodeEditorDialog`'s chrome) shows **this segment and
#: nothing else**, so it is the ONE surface where no major-mode label is present
#: to supply the word. Fixing only `MAJOR_LABELS` would have left that chip
#: reading a bare "Edit" — the exact defect, on the surface FQ-032 made
#: load-bearing.
EDITING_EDIT = "Edit mode"
EDITING_COMMAND = "Command mode — press i to type"

#: The major mode a chip's colour is keyed by, spelled as the theme file spells
#: it. `None` ("no launcher column picked yet") is `"none"` on disk, because
#: JSON has no null-valued object key.
_THEME_MODE_KEYS: dict[str | None, str] = {
    None: "none",
    MODE_STANDALONE: MODE_STANDALONE,
    MODE_PROJECT: MODE_PROJECT,
    MODE_MAINTENANCE: MODE_MAINTENANCE,
}


def mode_colors(light: bool) -> dict[str | None, tuple[str, str]]:
    """The `{major mode: (background, foreground)}` palette for the theme.

    Pure — builds and returns a fresh dict, mutating nothing, exactly as
    `theme.py::light_palette()` does with its QPalette.

    **The pairs live in the theme file, not here** (FQ-260812021715). This
    module's docstring records the exact mistake that made that mandatory: a
    per-theme colour table beside the real one. The table it once held is now
    `modes` in `resources/themes/*.json`, and `theme_model` is the only reader.
    Downstream consumers keep importing THIS function rather than the theme —
    `sql_results_panel.status_colour` and `ddl_buffer_panel.
    danger_selection_colors` both derive the app's one red from
    `MODE_MAINTENANCE`'s foreground (§18.7), and that derivation is the point.
    """
    theme = theme_for(light)
    return {key: theme.mode_pair(name) for key, name in _THEME_MODE_KEYS.items()}


def mode_text(
    major: str | None, minor: str | None = None, editing: str | None = None
) -> str:
    """What every surface reads: the major mode, plus the minor one when there
    is one, plus the focused editor's editing mode when there is one.

    An unknown major-mode string is shown verbatim rather than swallowed — a
    mode the indicator cannot name is a bug worth seeing, not worth hiding.

    `editing` is **absent** (None) exactly when the focused editor is read-only
    or is not an editor at all: FQ-032 makes the editing-mode layer inactive on a
    read-only buffer, and a read-only buffer already names itself in its tab
    title (§8's reason-set seam). Same present/absent posture as the minor mode.
    """
    label = MAJOR_LABELS.get(major, major) if major is not None else NO_MODE_LABEL
    segments = [str(label)]
    if minor:
        segments.append(minor)
    if editing:
        segments.append(editing)
    return MODE_SEPARATOR.join(segments)


def mode_stylesheet(background: str, foreground: str) -> str:
    """The chip's QSS. One spelling for both surfaces."""
    return (
        "QLabel { color: %s; background: %s; padding: 1px 8px;"
        " border-radius: 3px; font-weight: bold; }" % (foreground, background)
    )


class ModeIndicator(QLabel):
    """One rendering of the current mode. THREE exist: the toolbar panel, the
    status-bar mirror, and `CodeEditorDialog`'s chrome.

    The first two are driven by the same `set_mode` call from the host's single
    `_refresh_mode_indicator`. The third passes `editing_only=True` and is driven
    by its own editor's editing-mode changes, because a dialog has no
    `MainWindow` to ask and no workflow mode to report.
    """

    def __init__(
        self, parent=None, *, light: bool = False, editing_only: bool = False
    ) -> None:
        super().__init__(parent)
        self._light = bool(light)
        self._major: str | None = None
        self._minor: str | None = None
        self._editing: str | None = None
        self._editing_only = bool(editing_only)
        self.setObjectName("mode_indicator")
        self._render()

    # -- the surface the host drives ----------------------------------------
    def set_mode(
        self,
        major: str | None,
        minor: str | None = None,
        editing: str | None = None,
    ) -> None:
        """Show `major` (colour + text), `minor` and `editing` (text only)."""
        self._major = major
        self._minor = minor
        self._editing = editing
        self._render()

    def set_editing_mode(self, editing: str | None) -> None:
        """Update only the editing-mode segment.

        What `CodeEditorDialog`'s chrome calls: it has a local fact to render and
        nothing else, so it must not have to restate a major mode it does not
        know.
        """
        self._editing = editing
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

    @property
    def editing(self) -> str | None:
        return self._editing

    @property
    def editing_only(self) -> bool:
        return self._editing_only

    def colors(self) -> tuple[str, str]:
        """The `(background, foreground)` currently painted — what a contrast
        check and a theme test read.

        An `editing_only` surface always paints the NEUTRAL pair: the colour is
        the MAJOR mode's vocabulary, and this surface has no major mode to
        report. `mode_colors` is deliberately not extended with an editing-mode
        key (see the module docstring).
        """
        palette = mode_colors(self._light)
        if self._editing_only:
            return palette[None]
        return palette.get(self._major, palette[None])

    def _render(self) -> None:
        if self._editing_only:
            # The dialog's chrome: the editing-mode segment and nothing else.
            # It is never blank -- this surface only exists on an editable
            # editor, so `Edit` is the honest fallback rather than an empty chip.
            self.setText(self._editing or EDITING_EDIT)
        else:
            self.setText(mode_text(self._major, self._minor, self._editing))
        background, foreground = self.colors()
        self.setStyleSheet(mode_stylesheet(background, foreground))
        self.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        # Every label now spells "mode" itself (`BUG-260810174126`), so the
        # tooltip names the DIMENSION the label belongs to and never repeats the
        # word — "Editing mode: Edit mode" reads like a bug even though it is
        # not.
        if self._editing_only:
            return (
                "Which keyboard vocabulary this editor listens in: "
                f"{self._editing or EDITING_EDIT}"
            )
        parts = []
        if self._minor is None:
            parts.append("Workflow mode (File ▸ New Session to change it)")
        else:
            parts.append(
                f"{mode_text(self._major)} — active editor mode: {self._minor}"
            )
        if self._editing:
            parts.append(f"keyboard: {self._editing}")
        return " — ".join(parts)
