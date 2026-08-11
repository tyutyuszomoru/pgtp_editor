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
==========================  ===================================================

Nothing here re-implements a control, re-reads a store, or re-derives a command
list. The four surfaces keep their widgets, their controllers, their persistence
and their tests; only their **host** changed.

RELOCATION, NOT DUPLICATION (owner-settled)
-------------------------------------------
The four commands this dialog absorbs are **gone from their old menus** —
``View ▸ Customize Toolbar…``, ``View ▸ Customize Shortcuts…``,
``Settings ▸ Edit Snippets…`` and ``Settings ▸ Autoformatter settings…`` no
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
callable. Pane 5 (syntax highlight colors, FQ-260812002828) and pane 6 (color
scheme, FQ-260812002829) are **absent, not stubbed** — both are
``QUEUED — BLOCKED: DO NOT IMPLEMENT`` pending an owner description
(DEC-260812004400), and a greyed "coming soon" row is a promise this code is in
no position to make. When they land they are two more rows here.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.ui.autoformat_settings_dialog import build_autoformat_settings_pane

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


#: The panes, in list order. FOUR, not six — see the module docstring.
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
