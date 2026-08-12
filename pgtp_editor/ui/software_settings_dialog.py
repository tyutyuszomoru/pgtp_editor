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

# pgtp_editor/ui/software_settings_dialog.py
"""`Settings ▸ Software settings…` (FQ-260812002827) — the app's ONE settings
home: a category list on the left, the selected category's real settings widget
on the right.

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
---------------------------------------------
It is a **host**, not a settings implementation. Every pane is the existing,
already-tested dialog for that area, embedded as a widget:

==========================  ===================================================
Snippets                    ``edit_snippets_dialog.EditSnippetsDialog``
                            (built and wired by ``SnippetController``)
Toolbar                     ``customize_toolbar_dialog.CustomizeToolbarDialog``
                            (built and wired by ``ToolbarController``)
Autoformatter               ``autoformat_settings_dialog.AutoformatSettingsDialog``
Keyboard shortcuts          ``customize_shortcuts_dialog.CustomizeShortcutsDialog``
                            (built and wired by ``MainWindow``)
Themes                      :class:`ThemesPane` — defined in this module,
                            because it had no prior dialog to embed
                            (FQ-260812021716)
External tools              :class:`ExternalToolsPane` — likewise new
                            (FQ-260812025705); the three `Locate …` items it
                            absorbed were menu commands, not dialogs
==========================  ===================================================

Nothing here re-implements a control, re-reads a store, or re-derives a command
list. The four pre-existing surfaces keep their widgets, their controllers,
their persistence and their tests; only their **host** changed. The two panes
written here are the exception that proves the rule — they are new, so they are
written here, and each still owns its own apply contract rather than borrowing
one from the host. `ExternalToolsPane` in particular re-implements none of the
three stores it edits: each Browse button calls the owning lane's existing
locate method.

RELOCATION, NOT DUPLICATION (owner-settled)
-------------------------------------------
The commands this dialog absorbs are **gone from their old menus** —
``View ▸ Customize Toolbar…``, ``View ▸ Customize Shortcuts…``,
``Settings ▸ Edit Snippets…``, ``Settings ▸ Autoformatter settings…`` and (with
FQ-260812025705) ``Generation ▸ Locate PHP Generator Executable…``,
``Generation ▸ Locate panGen Runtime…`` and ``Tools ▸ Locate PHP Linter…`` no
longer exist. This dialog is their sole entry point, `Settings` holds exactly one
entry, and the command is the Maintenance launcher column's third button.

The consequence, taken deliberately: **toolbar and shortcut customization are
now Maintenance-mode gestures**, where before they were reachable at any time
from `View`. That is consistent with FQ-027's design that the app is
*configured* in Maintenance mode — which is why the `Settings` menu was
Maintenance-only in the first place — and it is what makes one launcher button
able to stand for the whole of "settings". (DEC-260812004358 is the owner's
confirmation of that trade; this is what ships until it is answered otherwise.)

THE APPLY CONTRACT — the hardest question here, answered explicitly
-------------------------------------------------------------------
**Each pane keeps exactly the apply/OK contract it already had, and the host
adds none of its own.** The host's only button is `Close`.

* A pane's own **OK** applies and persists precisely what it applies today: the
  snippets pane writes ``snippets.json`` through ``SnippetController.save``, the
  autoformatter pane writes its own ``QSettings`` keys, the toolbar pane calls
  ``ToolbarController.apply_and_save``, the shortcuts pane calls
  ``MainWindow.apply_and_save_shortcut_overrides``.
* A pane's own **Cancel** discards precisely what it discards today. The
  snippets dialog in particular edits a **scratch copy** and "Cancel undoes
  everything" is pinned by a test; that is preserved literally, because it is
  the same dialog doing the same thing.

The alternative — one host-level OK/Cancel buffering all four panes — was
rejected on two counts. It would have to invent a fifth apply semantics on top
of four that already exist and disagree (the autoformatter owns its persistence;
the shortcuts dialog's host owns its; the snippets controller owns its), and it
would give a **non-modal** window a body of unsaved state, which is exactly the
thing that gets silently discarded when the user closes it or when a change
lands from elsewhere mid-edit.

Because a pane is a real ``QDialog`` embedded as a plain widget,
``accept()``/``reject()`` still call ``done()``, which hides it. The host watches
``finished`` and **rebuilds that pane from the now-current state**. So OK leaves
the pane showing what was just saved, Cancel leaves it showing what is stored,
and a pane is never a stale scratch copy of a store something else has moved on
from. That is what makes this dialog safe to leave open indefinitely, which
non-modality requires (DEC-260812004359 — non-modal is what ships, preserving the
shortcuts pane's live behaviour; the host is **single-instance**, so re-opening
raises the one window rather than growing a second).

Closing the host is therefore never a save and never a loss beyond one pane's
uncommitted edits — identical to closing any one of these four dialogs today.

ADDING A PANE IS A DATA CHANGE
------------------------------
:data:`SETTINGS_PANES` is the whole list: one :class:`SettingsPane` row of
``key``, ``title``, ``blurb`` and a ``build(window, parent) -> QDialog``
callable.

The fifth row, **Themes** (FQ-260812021716), is the proof of that claim and the
answer to DEC-260812004400. It arrived as ONE pane where two were reserved:
pane 5 (syntax highlight colors, FQ-260812002828) and pane 6 (color scheme,
FQ-260812002829) are **SUPERSEDED**, because syntax highlighting is part of the
theme by owner ruling — two panes editing one `Theme` could be edited into a
mismatch, and one cannot mismatch itself. It is `_themes_pane` below, and it
cost exactly one row here.

The sixth, **External tools** (FQ-260812025705), cost one row too — and that is
the whole evidence for the claim. It also has the consequence FQ-027/DEC-006
attaches to everything in here: **setting an external binary is now a
Maintenance-mode gesture**, while the operations that use it run in
Project/Standalone mode. The same trade already accepted for toolbar, shortcut
and theme customization; the greyed operation plus its tooltip is what tells a
user in Project mode where to go.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.ui import theme_model
from pgtp_editor.ui.autoformat_settings_dialog import build_autoformat_settings_pane
from pgtp_editor.ui.status_colours import (
    STATUS_ERROR,
    STATUS_OK,
    STATUS_WARNING,
    StatusLabel,
)
from pgtp_editor.ui.theme_model import SyntaxRole, Theme, ThemeError

#: The `Settings` menu's label for this command, and therefore the id the menu
#: walk derives from it (`settings.software-settings` — see
#: `toolbar_registry.command_id_for`). Kept here, imported by `main_window.py`
#: and by `launcher_dialog.py`'s Maintenance tuple, so the menu row, the derived
#: id and the launcher button cannot drift apart — the same arrangement
#: `autoformat_settings_dialog.MENU_LABEL` established.
MENU_LABEL = "Software settings…"

#: The command id `MENU_LABEL` produces under the `Settings` menu. Written out
#: rather than computed so `launcher_dialog.LAUNCHER_GROUPS` stays a table of
#: literal ids like every other row in it; a test derives it and compares.
COMMAND_ID = "settings.software-settings"

#: How the rest of the app SPELLS the External-tools pane's address, for the
#: notices that used to point at the three `Locate …` menu items this pane
#: absorbed (FQ-260812025705). Kept here, imported by `generation_controller.py`
#: and `lint_controller.py`, for the same reason `MENU_LABEL` is: three lanes
#: naming a menu path in their own words is how a moved surface becomes
#: unfindable. `lint/findings.py` cannot import a UI module and carries the
#: literal instead — a test pins the two together.
EXTERNAL_TOOLS_SETTINGS_PATH = "Settings ▸ Software settings… ▸ External tools"


@dataclass(frozen=True)
class SettingsPane:
    """One row of the category list, and how to build its widget.

    `build` takes the host window and the parent widget and returns a wired,
    **not yet shown** ``QDialog``. It is called again every time the pane's
    dialog finishes, so it must be safe to call repeatedly and must read
    current state each time rather than closing over a snapshot.
    """

    key: str
    title: str
    blurb: str
    build: Callable[[object, QWidget], QDialog]


def _snippets_pane(window, parent) -> QDialog:
    return window._snippet_ui.build_editor(parent)


def _toolbar_pane(window, parent) -> QDialog:
    return window._toolbar_ui.build_customize_pane(parent)


def _autoformat_pane(window, parent) -> QDialog:
    return build_autoformat_settings_pane(parent, settings=window._settings)


def _shortcuts_pane(window, parent) -> QDialog:
    return window.build_customize_shortcuts_pane(parent)


def _themes_pane(window, parent) -> QDialog:
    return ThemesPane(window, parent)


def _external_tools_pane(window, parent) -> QDialog:
    return ExternalToolsPane(window, parent)


#: The colour sections a theme file carries, in the order the pane lays them out:
#: `(section key, group heading, the keys in it)`. Read straight off
#: `theme_model`'s own tuples rather than re-listed, so a colour added to the
#: model appears in the editor with no change here — the alternative is a second
#: list of colour names, which is the same mistake as a second list of colours.
_FLAT_SECTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("chrome", "Chrome (menus, buttons, tabs, docks, scrollbars)", theme_model.CHROME_KEYS),
    ("palette", "Widget palette", theme_model.PALETTE_ROLES),
    ("palette_disabled", "Widget palette — disabled", theme_model.DISABLED_ROLES),
    ("accents", "Accents", theme_model.ACCENT_KEYS),
    ("decorations", "Editor decorations", theme_model.DECORATION_KEYS),
)

#: The two halves of a mode chip, in `Theme.modes`' pair order.
_MODE_PARTS: tuple[str, ...] = ("background", "foreground")

#: The three weight flags a syntax role carries beside its colour.
_SYNTAX_FLAGS: tuple[str, ...] = ("bold", "italic", "underline")


class _ColorButton(QPushButton):
    """One editable colour: a swatch that opens `QColorDialog` and remembers the
    chosen `#rrggbb`.

    The value is held as TEXT, not as a `QColor`, because that is what a theme
    file holds and what `Theme.from_json` validates — round-tripping through
    `QColor` would quietly normalise (or accept) notations the loader refuses.
    """

    def __init__(self, value: str, parent=None):
        super().__init__(parent)
        self._value = ""
        self.setFlat(False)
        self.setAutoDefault(False)
        self.set_value(value)
        self.clicked.connect(self._pick)

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        self._value = str(value)
        self.setText(self._value)
        colour = QColor(self._value)
        # Label contrast is computed, not chosen: a fixed label colour would be
        # unreadable on half the swatches, and a literal here would be a second
        # colour source (the AST guard in tests/ui/test_theme_model.py forbids
        # exactly that). `QColor.lightness()` picks black or white by luminance.
        ink = QColor(Qt.GlobalColor.black if colour.lightness() > 127 else Qt.GlobalColor.white)
        self.setStyleSheet(
            f"background-color: {colour.name()}; color: {ink.name()};"
            " border: 1px solid palette(mid); padding: 3px;"
        )

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._value), self, "Pick a colour")
        if chosen.isValid():
            self.set_value(chosen.name())


class ThemesPane(QDialog):
    """`Software settings ▸ Themes` (FQ-260812021716) — browse, select,
    duplicate and edit the file-based themes FQ-260812021715 introduced.

    WHAT EACH GESTURE MEANS
    -----------------------
    * **Browse** — the list is `theme_model.available_themes()`, rescanned on
      every refresh, so a theme file dropped into the user themes directory
      shows up without a restart. That is the foundation feature's headline
      requirement, and this pane simply does not cache around it.
    * **Use this theme** — applies AND persists immediately, through
      `MainWindow.apply_theme_named`. Not on OK: the owner's ruling is that a
      theme is marked selected and is app-wide and durable from that moment.
      Selection is therefore deliberately NOT part of the pane's edit buffer.
    * **Duplicate…** — the create path. "New = copy an existing one", so a new
      theme is a valid `Theme` from the first keystroke and there is no
      half-defined-theme state to guard against. It is written into the USER
      themes directory, which is also what makes it editable.
    * **OK (Save)** — writes the edited colours back to the theme's user file,
      and RE-APPLIES it if it is the theme in use, which is what makes the edit
      visible. **Cancel** discards the edits, exactly like every other pane
      here; the host then rebuilds this pane from what is now on disk.

    BUNDLED THEMES ARE READ-ONLY, AND THAT IS THE DESIGN
    ----------------------------------------------------
    An install directory is not reliably writable, an upgrade would overwrite
    the edit anyway, and duplicate-then-edit already exists — so editing a
    bundled theme is refused with the reason stated on screen rather than
    silently failing at write time. A duplicate of a bundled theme SHADOWS it if
    given the same name (`theme_model.theme_search_path`), so "edit the theme I
    am using" is reachable without touching the install.

    LIVE PREVIEW, HONESTLY SCOPED
    -----------------------------
    Apply-on-save, not apply-per-keystroke. A `QColorDialog` interaction would
    otherwise re-apply the whole app stylesheet on every slider move, and a theme
    flip fires `PaletteChange` four times — the first two reporting the OLD
    lightness. Every colour re-read in this app is idempotent and last-write-wins
    for that reason, and multiplying the flips buys nothing a Save does not.
    """

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Themes")
        self._window = window
        self._theme: Theme | None = None
        self._color_buttons: dict[tuple[str, str], _ColorButton] = {}
        self._syntax_flags: dict[tuple[str, str], QCheckBox] = {}

        layout = QVBoxLayout(self)
        body = QHBoxLayout()
        layout.addLayout(body, 1)

        # -- left: the theme list and the two theme-level gestures ------------
        left = QVBoxLayout()
        self.theme_list = QListWidget(self)
        self.theme_list.setMaximumWidth(220)
        left.addWidget(self.theme_list, 1)
        self.use_button = QPushButton("Use this theme", self)
        self.use_button.setAutoDefault(False)
        self.use_button.clicked.connect(self.use_selected)
        left.addWidget(self.use_button)
        self.duplicate_button = QPushButton("Duplicate…", self)
        self.duplicate_button.setAutoDefault(False)
        self.duplicate_button.clicked.connect(self._prompt_duplicate)
        left.addWidget(self.duplicate_button)
        body.addLayout(left)

        # -- right: the colour editor -----------------------------------------
        right = QVBoxLayout()
        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        right.addWidget(self.status_label)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        right.addWidget(self.scroll, 1)
        body.addLayout(right, 1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Save")
        self.button_box.accepted.connect(self._on_save)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.refresh_themes()
        self.theme_list.currentRowChanged.connect(lambda _row: self._load_selected())

    # -- browsing -------------------------------------------------------------

    def refresh_themes(self, select: str | None = None) -> None:
        """Rescan the search path and rebuild the list.

        `select` is the name to land on; by default the previously selected one,
        falling back to the theme in use. The scan is `available_themes()`, which
        walks the directories on every call — deliberately uncached, so a file
        written a moment ago (by Duplicate, or by hand) is simply there.
        """
        wanted = select or self.selected_theme_name() or self.active_theme_name()
        self._names = sorted(theme_model.available_themes())
        blocked = self.theme_list.blockSignals(True)
        self.theme_list.clear()
        active = self.active_theme_name()
        for name in self._names:
            self.theme_list.addItem(f"{name} — in use" if name == active else name)
        self.theme_list.blockSignals(blocked)
        row = self._names.index(wanted) if wanted in self._names else 0
        if self._names:
            self.theme_list.setCurrentRow(row)
        self._load_selected()

    def theme_names(self) -> list[str]:
        """The theme names on offer, in list order."""
        return list(self._names)

    def active_theme_name(self) -> str:
        """The theme the app is currently painted in, as persisted."""
        return self._window.theme_name()

    def selected_theme_name(self) -> str | None:
        row = self.theme_list.currentRow()
        if not 0 <= row < len(getattr(self, "_names", ())):
            return None
        return self._names[row]

    def select_theme(self, name: str) -> bool:
        """Highlight `name` in the list (browsing only — this does not apply it)."""
        if name not in self._names:
            return False
        self.theme_list.setCurrentRow(self._names.index(name))
        return True

    # -- selection (applies and persists immediately) -------------------------

    def use_selected(self) -> str | None:
        """Mark the highlighted theme as the app's theme: apply it and persist it.

        Immediate on purpose — see the class docstring. Returns the name actually
        applied, which `MainWindow.apply_theme_named` may downgrade to the
        bundled dark theme if the file has become unloadable since the scan.
        """
        name = self.selected_theme_name()
        if name is None:
            return None
        applied = self._window.apply_theme_named(name)
        self.refresh_themes(select=applied)
        return applied

    # -- duplication (the create path) ----------------------------------------

    def duplicate_selected(self, display_name: str) -> str:
        """Write a copy of the highlighted theme under `display_name`, and land
        on it. Returns the new theme's NAME (its file stem).

        The copy is a full `Theme`, not a delta on the original: a theme file
        that inherits from another would make "delete the file it inherits from"
        a way to break a working theme, and the whole model is that one file is
        one complete theme.
        """
        source = self._theme
        if source is None:
            raise ThemeError("no theme is selected to duplicate")
        stem = theme_model.theme_stem(display_name)
        if stem in self._names:
            raise ThemeError(f"a theme named {stem!r} already exists")
        theme_model.save_theme(theme_model.duplicate(source, str(display_name).strip()), stem)
        self.refresh_themes(select=stem)
        return stem

    def _prompt_duplicate(self) -> None:
        source = self.selected_theme_name()
        if source is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Duplicate theme", "Name for the copy:", text=f"{source} copy"
        )
        if not accepted:
            return
        try:
            self.duplicate_selected(name)
        except ThemeError as error:
            QMessageBox.warning(self, "Duplicate theme", str(error))

    # -- editing --------------------------------------------------------------

    def _load_selected(self) -> None:
        """Rebuild the colour editor from the highlighted theme's file."""
        name = self.selected_theme_name()
        self._color_buttons = {}
        self._syntax_flags = {}
        if name is None:
            self._theme = None
            self.status_label.setText("No themes were found.")
            self.scroll.setWidget(QWidget(self))
            self._set_editable(False)
            return
        try:
            self._theme = theme_model.load_theme(name)
        except ThemeError as error:
            self._theme = None
            self.status_label.setText(str(error))
            self.scroll.setWidget(QWidget(self))
            self._set_editable(False)
            return
        self.scroll.setWidget(self._build_editor(self._theme))
        editable = not theme_model.is_bundled(self._theme)
        self.status_label.setText(
            f"<b>{self._theme.name}</b>"
            if editable
            else f"<b>{self._theme.name}</b> is a bundled theme and is read-only — "
            "use <i>Duplicate…</i> to make an editable copy."
        )
        self._set_editable(editable)

    def _set_editable(self, editable: bool) -> None:
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(editable)
        for widget in list(self._color_buttons.values()) + list(self._syntax_flags.values()):
            widget.setEnabled(editable)

    def _build_editor(self, theme: Theme) -> QWidget:
        host = QWidget(self)
        column = QVBoxLayout(host)
        for section, heading, keys in _FLAT_SECTIONS:
            values = getattr(theme, section)
            column.addWidget(
                self._colour_group(host, heading, [
                    (section, key, key, values[key]) for key in keys
                ])
            )
        column.addWidget(
            self._colour_group(host, "Mode indicator chips", [
                ("modes", f"{mode}.{part}", f"{mode} ({part})",
                 theme.modes[mode][index])
                for mode in theme_model.MODE_KEYS
                for index, part in enumerate(_MODE_PARTS)
            ])
        )
        column.addWidget(self._syntax_group(host, theme))
        column.addStretch(1)
        return host

    def _colour_group(self, parent, heading: str, rows) -> QGroupBox:
        group = QGroupBox(heading, parent)
        grid = QGridLayout(group)
        for row, (section, key, label, value) in enumerate(rows):
            grid.addWidget(QLabel(label, group), row, 0)
            button = _ColorButton(value, group)
            self._color_buttons[(section, key)] = button
            grid.addWidget(button, row, 1)
        grid.setColumnStretch(1, 1)
        return group

    def _syntax_group(self, parent, theme: Theme) -> QGroupBox:
        """The 8 syntax roles: a colour plus bold/italic/underline each.

        Syntax lives HERE, in the same pane as the chrome, because it is part of
        the theme (owner ruling) — which is what makes a light-syntax-on-dark-
        chrome mismatch unrepresentable rather than merely discouraged.
        """
        group = QGroupBox("Syntax highlighting", parent)
        grid = QGridLayout(group)
        for column, flag in enumerate(_SYNTAX_FLAGS):
            grid.addWidget(QLabel(flag.title(), group), 0, 2 + column)
        for row, key in enumerate(theme_model.SYNTAX_ROLES, start=1):
            role = theme.syntax[key]
            grid.addWidget(QLabel(key, group), row, 0)
            button = _ColorButton(role.color, group)
            self._color_buttons[("syntax", key)] = button
            grid.addWidget(button, row, 1)
            for column, flag in enumerate(_SYNTAX_FLAGS):
                box = QCheckBox(group)
                box.setChecked(bool(getattr(role, flag)))
                self._syntax_flags[(key, flag)] = box
                grid.addWidget(box, row, 2 + column)
        grid.setColumnStretch(1, 1)
        return group

    # -- the editor's programmatic surface (also the test seam) ---------------

    def color_value(self, section: str, key: str) -> str:
        return self._color_buttons[(section, key)].value()

    def set_color_value(self, section: str, key: str, value: str) -> None:
        self._color_buttons[(section, key)].set_value(value)

    def syntax_flag(self, role: str, flag: str) -> bool:
        return self._syntax_flags[(role, flag)].isChecked()

    def set_syntax_flag(self, role: str, flag: str, value: bool) -> None:
        self._syntax_flags[(role, flag)].setChecked(bool(value))

    def edited_theme(self) -> Theme:
        """The `Theme` the editor currently describes.

        Built by round-tripping through `Theme.from_json`, so the edits are
        VALIDATED by the same loader a file goes through — an editor that
        constructed the dataclass directly could produce a theme that cannot be
        loaded back, which is the worst possible time to find out.
        """
        if self._theme is None:
            raise ThemeError("no theme is selected")
        data = self._theme.to_json()
        for (section, key), button in self._color_buttons.items():
            if section == "syntax":
                data["syntax"][key]["color"] = button.value()
            elif section == "modes":
                mode, part = key.split(".")
                data["modes"][mode][_MODE_PARTS.index(part)] = button.value()
            else:
                data[section][key] = button.value()
        for (role, flag), box in self._syntax_flags.items():
            data["syntax"][role][flag] = box.isChecked()
        return Theme.from_json(data, source=self._theme.source)

    def save_edits(self) -> Theme:
        """Write the edited theme to its user file, re-applying it if it is in
        use. Returns the saved `Theme`."""
        theme = self.edited_theme()
        name = self.selected_theme_name()
        if name is None:  # pragma: no cover - `edited_theme` raised already
            raise ThemeError("no theme is selected")
        if self._theme is not None and theme_model.is_bundled(self._theme):
            raise ThemeError(
                f"{self._theme.name} is a bundled theme and cannot be edited in "
                "place -- duplicate it first"
            )
        theme_model.save_theme(theme, name)
        if name == self.active_theme_name():
            # Re-apply so the edit is VISIBLE. `apply_theme_named` re-reads the
            # file, and `load_theme_file`'s cache is keyed on the file's stat, so
            # it picks up the write just made rather than the parse from before.
            self._window.apply_theme_named(name)
        return theme

    def _on_save(self) -> None:
        try:
            self.save_edits()
        except ThemeError as error:
            QMessageBox.warning(self, "Save theme", str(error))
            return
        self.accept()


@dataclass(frozen=True)
class ExternalTool:
    """One app-wide external binary the `External tools` pane can locate.

    Every callable takes the host window and delegates to the LANE that owns the
    store, so this module holds no path, no config key and no validation rule of
    its own:

    * `locate` — the lane's existing write path (its old `Locate …` menu item's
      slot). It persists immediately and re-gates its own menus.
    * `value` — what is stored now, or None.
    * `resolves` — whether that stored value is still usable. Different per tool
      on purpose: an executable is a file, the panGen runtime is a repo root
      (`validate_re_phpgen_root`), and NOTHING here re-derives either.
    """

    key: str
    title: str
    dependents: str
    locate: Callable[[object], None]
    value: Callable[[object], str | None]
    resolves: Callable[[object], bool]
    broken_note: str


def _is_file(path: str | None) -> bool:
    if not path:
        return False
    try:
        return Path(path).is_file()
    except OSError:  # pragma: no cover - a path the OS refuses to even stat
        return False


#: The three tools, as data. Adding a fourth is one row — the same property
#: `SETTINGS_PANES` has, one level down, and the reason this pane is ONE pane
#: rather than three (all three are app-wide locators over a single
#: `generator_config.json`; three panes would fragment a grouped concept).
EXTERNAL_TOOLS: tuple[ExternalTool, ...] = (
    ExternalTool(
        key="php_generator",
        title="PHP Generator executable",
        dependents="Generation ▸ Generate PHP",
        locate=lambda window: window._gen_ui.locate_generator(),
        value=lambda window: window._gen_ui.generator_executable_path(),
        resolves=lambda window: _is_file(window._gen_ui.generator_executable_path()),
        broken_note=(
            "that file is gone or is not a file any more — Generate PHP will "
            "fail at run time until it is set again"
        ),
    ),
    ExternalTool(
        key="pangen_runtime",
        title="panGen runtime (re_phpgen repo root)",
        dependents="Generation ▸ panGen, rePHPgen and Save reJSON",
        locate=lambda window: window._gen_ui.locate_pangen_runtime(),
        value=lambda window: window._gen_ui.pangen_runtime_root(),
        resolves=lambda window: window._gen_ui.pangen_runtime_is_valid(),
        broken_note=(
            "that folder does not look like the re_phpgen repo (no src/re_phpgen) "
            "— panGen, rePHPgen and Save reJSON stay unavailable"
        ),
    ),
    ExternalTool(
        key="php_linter",
        title="PHP linter (`php` executable)",
        dependents="Tools ▸ Lint Current File and Lint on Save",
        locate=lambda window: window._lint_ui.locate_linter(),
        value=lambda window: window._lint_ui.linter_executable_path(),
        resolves=lambda window: _is_file(window._lint_ui.linter_executable_path()),
        broken_note=(
            "that file is gone or is not a file any more — a lint run will "
            "report it rather than pass silently"
        ),
    ),
)


class ExternalToolsPane(QDialog):
    """`Software settings ▸ External tools` (FQ-260812025705) — the three
    app-wide external binaries: the vendor PHP Generator, the panGen runtime and
    the PHP linter.

    RELOCATION, NOT DUPLICATION
    ---------------------------
    `Generation ▸ Locate PHP Generator Executable…`,
    `Generation ▸ Locate panGen Runtime…` and `Tools ▸ Locate PHP Linter…` are
    **gone**. This pane is their sole home, exactly as this dialog is the sole
    home of the four surfaces it absorbed first. All three stores are app-wide
    (`generator_config.json` in the app data dir), which is what puts them here
    rather than in per-project settings — the sibling per-project PostgreSQL
    binaries (`FQ-260812025353`) stay in Project settings for the mirror-image
    reason, and the two must not be unified.

    NOTHING HERE RE-IMPLEMENTS A STORE
    ----------------------------------
    Each row's Browse button calls the owning lane's existing locate method, so
    the file dialog, the validation, the `generator_config.json` write that
    preserves its sibling keys, and the status-bar line are all the shipped,
    already-tested code. This pane reads back through the lanes' read-only
    accessors and never learns where `config_dir` points.

    `resolve_tool` (the per-project PostgreSQL locator's helper) is deliberately
    NOT reused: it is keyed on a FOLDER holding a known binary name, and two of
    these three store a full executable PATH. The reusable parts of that feature
    are its `Which`-shaped seam and its warn-don't-block status line — not its
    folder semantics.

    THE APPLY CONTRACT — immediate, and that is the pane's own contract
    ------------------------------------------------------------------
    **Browse persists immediately**, so this pane has no OK/Cancel and adds none
    to the host, whose only button stays `Close`. That is not a gap in the
    dialog's contract, it is the same shape as `ThemesPane`'s *Use this theme*:
    a single-value pick through a file dialog is already a confirmed gesture, and
    the picker IS the OK. Buffering it would invent a fifth apply semantics and
    give a non-modal window a body of unsaved state — the two grounds on which a
    host-level buffer was rejected in the first place.

    Because nothing is buffered, nothing can go stale: each pick refreshes this
    pane's status lines, and the lane re-gates its own menu entries in the same
    call. There is also no `finished` for the host to rebuild on, which is
    correct — a pane holding no edit buffer has nothing to rebuild from.

    WARN, DO NOT BLOCK
    ------------------
    A stored path that no longer resolves is stated in the status line rather
    than erased or refused. For the panGen runtime the operations really are
    greyed (an invalid root cannot run), but for the two executables the
    operation stays reachable and reports the failure itself — §22's lint run in
    particular diagnoses a missing binary better than this pane can guess.
    """

    def __init__(self, window, parent=None, *, tools=EXTERNAL_TOOLS):
        super().__init__(parent)
        self.setWindowTitle("External tools")
        self._window = window
        self._tools = tuple(tools)
        #: tool key -> its status line. `StatusLabel`, never a hand-rolled
        #: `setStyleSheet("color: …")`: it remembers the KIND and re-derives the
        #: colour on a theme flip, which a stored colour cannot (and this dialog
        #: can be open across a flip, since the Themes pane is one click away).
        self._status_labels: dict[str, StatusLabel] = {}
        self._value_labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        for tool in self._tools:
            layout.addWidget(self._build_group(tool))
        layout.addStretch(1)
        self.refresh()

    def _build_group(self, tool: ExternalTool) -> QGroupBox:
        group = QGroupBox(tool.title, self)
        rows = QVBoxLayout(group)
        needs = QLabel(f"Needed by: {tool.dependents}.", group)
        needs.setWordWrap(True)
        rows.addWidget(needs)

        line = QHBoxLayout()
        value = QLabel("", group)
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._value_labels[tool.key] = value
        line.addWidget(value, 1)
        browse = QPushButton("Browse…", group)
        browse.setAutoDefault(False)
        browse.clicked.connect(lambda _checked=False, key=tool.key: self.locate(key))
        line.addWidget(browse)
        rows.addLayout(line)

        status = StatusLabel("", group)
        status.setWordWrap(True)
        self._status_labels[tool.key] = status
        rows.addWidget(status)
        return group

    # -- gestures --------------------------------------------------------------

    def locate(self, key: str) -> None:
        """Run `key`'s locate gesture, then restate what is stored.

        The lane persists and re-gates its own menu entries; this only re-reads.
        A cancelled file dialog is a no-op in the lane, so the refresh simply
        redraws the same thing.
        """
        tool = self.tool_for(key)
        if tool is None:
            return
        tool.locate(self._window)
        self.refresh()

    def refresh(self) -> None:
        """Re-read all three stores and repaint every row."""
        for tool in self._tools:
            stored = tool.value(self._window)
            label = self._value_labels[tool.key]
            status = self._status_labels[tool.key]
            if not stored:
                label.setText("<i>Not set</i>")
                status.set_status(
                    f"Not set — {tool.dependents} stay unavailable until it is.",
                    STATUS_WARNING,
                )
                continue
            label.setText(str(stored))
            if tool.resolves(self._window):
                status.set_status("Found.", STATUS_OK)
            else:
                status.set_status(tool.broken_note.capitalize() + ".", STATUS_ERROR)

    # -- read-only surface / test seam -----------------------------------------

    def tool_keys(self) -> list[str]:
        return [tool.key for tool in self._tools]

    def tool_for(self, key: str) -> ExternalTool | None:
        for tool in self._tools:
            if tool.key == key:
                return tool
        return None

    def stored_value(self, key: str) -> str:
        """What the row DISPLAYS for `key` — the assertable form of the store."""
        return self._value_labels[key].text()

    def status_kind(self, key: str) -> str | None:
        return self._status_labels[key].status_kind()

    def status_text(self, key: str) -> str:
        return self._status_labels[key].text()


#: The panes, in list order. SIX — see the module docstring.
SETTINGS_PANES: tuple[SettingsPane, ...] = (
    SettingsPane(
        key="snippets",
        title="Snippets",
        blurb=(
            "The trigger words Ctrl+Alt+E expands in a SQL editor, and their "
            "bodies."
        ),
        build=_snippets_pane,
    ),
    SettingsPane(
        key="toolbar",
        title="Toolbar",
        blurb="Which commands sit on the Main Toolbar, in which order, with which icons.",
        build=_toolbar_pane,
    ),
    SettingsPane(
        key="autoformatter",
        title="Autoformatter",
        blurb="How Format Selection rewrites SQL/plpgsql and XML.",
        build=_autoformat_pane,
    ),
    SettingsPane(
        key="shortcuts",
        title="Keyboard shortcuts",
        blurb="The key bound to each menu command, and the keys the app pins.",
        build=_shortcuts_pane,
    ),
    SettingsPane(
        key="themes",
        title="Themes",
        blurb=(
            "Every colour the app paints, as named theme files: pick one, "
            "duplicate it, and edit its chrome, editor and syntax colours."
        ),
        build=_themes_pane,
    ),
    SettingsPane(
        key="external_tools",
        title="External tools",
        blurb=(
            "Where the app-wide external binaries live: the vendor PHP "
            "Generator, the panGen runtime, and the PHP linter."
        ),
        build=_external_tools_pane,
    ),
)


class SoftwareSettingsDialog(QDialog):
    """The two-pane settings host. `panes` is injectable for tests."""

    def __init__(
        self,
        window,
        parent=None,
        *,
        panes: tuple[SettingsPane, ...] = SETTINGS_PANES,
    ):
        super().__init__(parent)
        self.setWindowTitle("Software settings")
        self.resize(960, 640)
        self._window = window
        self._panes = tuple(panes)
        #: pane key -> the live embedded QDialog. Replaced wholesale on every
        #: rebuild, so nothing here is ever a handle on a hidden dialog.
        self._pane_dialogs: dict[str, QDialog] = {}
        self._containers: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        layout.addWidget(splitter, 1)

        self.category_list = QListWidget(splitter)
        self.category_list.setMaximumWidth(220)
        self.stack = QStackedWidget(splitter)
        splitter.addWidget(self.category_list)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)

        for pane in self._panes:
            self.category_list.addItem(pane.title)
            self.stack.addWidget(self._build_container(pane))

        self.category_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        if self._panes:
            self.category_list.setCurrentRow(0)

        # `Close`, and nothing else. There is no host-level OK because there is
        # no host-level state to apply — see the module docstring's apply
        # contract. `rejected` rather than `accepted`, so Escape and this button
        # are the same gesture.
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, parent=self
        )
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    # -- construction --------------------------------------------------------

    def _build_container(self, pane: SettingsPane) -> QWidget:
        container = QWidget(self)
        box = QVBoxLayout(container)
        heading = QLabel(f"<b>{pane.title}</b>", container)
        box.addWidget(heading)
        blurb = QLabel(pane.blurb, container)
        blurb.setWordWrap(True)
        box.addWidget(blurb)
        body = QWidget(container)
        QHBoxLayout(body).setContentsMargins(0, 0, 0, 0)
        box.addWidget(body, 1)
        self._containers[pane.key] = body
        self._install_pane(pane)
        return container

    def _install_pane(self, pane: SettingsPane) -> QDialog:
        """Build `pane`'s dialog and put it in its container as a plain widget.

        `setWindowFlags(Widget)` is what turns a ``QDialog`` into an embeddable
        child: ``QDialog``'s constructor sets ``Qt::Dialog`` even when it is
        given a parent, so without this the pane would pop up as its own window
        the moment it was shown. It is cleared *before* the reparent, while the
        widget is still invisible.
        """
        container = self._containers[pane.key]
        dialog = pane.build(self._window, container)
        dialog.setWindowFlags(Qt.WindowType.Widget)
        container.layout().addWidget(dialog)
        dialog.setVisible(True)
        # Rebuild AFTER the pane's own accept/reject handlers have run: Qt emits
        # `accepted`/`rejected` before `finished`, which is the ordering the
        # snippet controller already depends on.
        dialog.finished.connect(
            lambda _result, key=pane.key: self._on_pane_finished(key)
        )
        self._pane_dialogs[pane.key] = dialog
        return dialog

    def _on_pane_finished(self, key: str) -> None:
        """A pane's OK or Cancel landed: replace it with a fresh one reading the
        now-current state.

        ``done()`` hid the pane, so *something* has to happen here or the user is
        left looking at an empty panel. Rebuilding rather than re-showing is the
        point: after OK the store has moved, and after Cancel the widget holds
        edits that were just discarded — in both cases the honest thing on screen
        is a pane freshly loaded from what is now true.
        """
        pane = self.pane_for(key)
        if pane is None:
            return
        old = self._pane_dialogs.pop(key, None)
        if old is not None:
            container = self._containers[key]
            container.layout().removeWidget(old)
            old.setParent(None)
            # Deferred, never `del`: we are inside the old dialog's own
            # `finished` emission.
            old.deleteLater()
        self._install_pane(pane)

    # -- read-only surface / test seam ---------------------------------------

    def pane_keys(self) -> list[str]:
        """The category keys, in list order."""
        return [pane.key for pane in self._panes]

    def pane_titles(self) -> list[str]:
        return [pane.title for pane in self._panes]

    def pane_for(self, key: str) -> SettingsPane | None:
        for pane in self._panes:
            if pane.key == key:
                return pane
        return None

    def pane_widget(self, key: str) -> QDialog | None:
        """The live embedded dialog for `key` — the real widget, not a copy."""
        return self._pane_dialogs.get(key)

    def current_pane_key(self) -> str | None:
        row = self.category_list.currentRow()
        if not 0 <= row < len(self._panes):
            return None
        return self._panes[row].key

    def select_pane(self, key: str) -> bool:
        """Show `key`'s pane. Returns whether it exists."""
        for row, pane in enumerate(self._panes):
            if pane.key == key:
                self.category_list.setCurrentRow(row)
                return True
        return False
