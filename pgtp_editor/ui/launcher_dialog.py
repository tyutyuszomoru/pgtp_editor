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

"""The startup launcher (FQ-010): the four ways into the app, on one modal.

Why it exists
-------------
Opening the app used to present no guidance at all — an empty Raw XML tab and an
empty Project Tree, with five workflows hidden behind five different menus. The
launcher names the four groups those workflows collapse into and dispatches each
one to the **existing** menu ``QAction``, so there is never a second
implementation of an open/new/generate gesture.

Two hard constraints, both structural
-------------------------------------
1. **It is NOT shown from ``MainWindow.__init__``.** 49 test files construct a
   ``MainWindow``; a modal there would hang every one of them, and ``CLAUDE.md``
   forbids a test reaching an un-patched modal Qt call. The one automatic show
   lives in ``pgtp_editor/main.py``, after ``window.show()``, behind the
   ``launcher=`` seam that file documents.
2. **``--mcp`` must remain structurally unable to reach it.** ``main.py`` returns
   for ``--mcp`` *before any Qt import*, so nothing in this module is even
   imported in headless mode. That invariant is stated at the return itself —
   stdio is the MCP transport and a GUI contending for stdout would corrupt
   every session.

Reuse, not reimplementation
---------------------------
Every entry is resolved out of :class:`~pgtp_editor.ui.toolbar_controller.
ToolbarController`'s menu-bar walk — the same ``command_id -> QAction`` map the
customizable toolbar hosts buttons from (§7's "the toolbar hosts the menus' OWN
QActions"). So an entry shares its menu item's slot, enabled state and shortcut
for free and can never drift from it, and the button labels are the walk's own
``File › Open``-style paths rather than new vocabulary.

Behaviour
---------
* **Escape / window-close lands in the app exactly as before, and NEVER quits.**
  Quitting on cancel would turn the launcher into a gate on running the app at
  all. :func:`show_launcher` simply returns ``None``.
* **Suppressible**: a "Don't show this again" checkbox persisted as the
  :data:`LAUNCHER_SUPPRESSED_SETTINGS_KEY` bool, alongside ``lightTheme`` /
  ``windowState`` / ``toolbarIds`` / ``toolbarIconIds`` in the same
  ``QSettings``. It is read on **every** exit path (chosen entry or cancel), and
  ``File ▸ Show Launcher…`` re-opens the launcher unconditionally so the flag is
  never a one-way door.
* The chosen action is triggered **after** the modal is down, so an action that
  itself opens a ``QFileDialog`` is not stacked on top of the launcher.

Test seam
---------
Mirrors ``CustomizeToolbarDialog``/``IconPickerDialog``: tests drive
:meth:`LauncherDialog.entry_ids`, :meth:`LauncherDialog.choose`,
:meth:`LauncherDialog.cancel` and :meth:`LauncherDialog.set_suppressed`
directly, and pass ``exec_dialog=`` to :func:`show_launcher`. **No test ever
calls ``.exec()``.**
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

#: QSettings key for the persisted "Don't show this again" choice. A plain bool
#: in the SAME store as `lightTheme`/`windowState`/`toolbarIds`, read with
#: `type=bool` because the ini backend hands booleans back as the strings
#: "true"/"false" (see `lint_controller.py`'s note on the same trap).
LAUNCHER_SUPPRESSED_SETTINGS_KEY = "launcherSuppressed"

#: The four groups, as (title, ordered command ids). The ids are the toolbar
#: registry's menu-path ids (`toolbar_registry.command_id_for`), so this table
#: never holds a label, a slot or a duplicate of any menu wiring.
#:
#: Group 4's membership is deliberately **open** (FQ-010, the owner's "for now"):
#: the §11 XSD actions plus §20's re_phpgen/panGen entries only. §19's vendor
#: PHP-generation entries (`generation.locate-php-generator-executable`,
#: `generation.generate-php`, `generation.open-output-folder`) are OUT — they are
#: used in ordinary development, not in maintaining the app. `Help ▸ Open Log
#: Folder`, `View ▸ Customize Toolbar…`, `Tools ▸ Locate PHP Linter…` and
#: `Tools ▸ Start MCP Server` were raised as candidates and neither included nor
#: ruled out; adding one is a one-line change here.
LAUNCHER_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Open a pgtp for editing",
        ("file.open",),
    ),
    (
        "New Project / Open Project",
        ("file.new-project", "file.open-project"),
    ),
    (
        "Open other files",
        ("file.open-php-file",),
    ),
    (
        "Maintenance mode",
        (
            "schema.edit-xsd",
            "schema.edit-autoxsd",
            "schema.verify-xsd",
            "schema.export-xsd",
            "schema.import-xsd",
            "generation.locate-pangen-runtime",
            "generation.pangen-generate-own-php",
            "generation.rephpgen-analyze-gap",
            "generation.save-rejson",
        ),
    ),
)

#: Short "what is this workflow" lines under each group title. Deliberately
#: descriptive of behaviour that already exists — the UX review's naming rulings
#: are a later step, so no new vocabulary is coined here.
_GROUP_HINTS: dict[str, str] = {
    "Open a pgtp for editing": (
        "Edit a .pgtp with the XML tooling and compare it against its quality "
        "database. No project, no sandbox."
    ),
    "New Project / Open Project": (
        "Work on the quality database through a local sandbox, or converge a "
        "deployable .pgtp by diff/merge."
    ),
    "Open other files": "Edit the custom PHP files that sit beside a project.",
    "Maintenance mode": "Maintain the app itself: the XSD and the re_phpgen loop.",
}


def launcher_suppressed(settings) -> bool:
    """Whether the user ticked "Don't show this again"."""
    return bool(settings.value(LAUNCHER_SUPPRESSED_SETTINGS_KEY, False, type=bool))


def set_launcher_suppressed(settings, suppressed: bool) -> None:
    """Persist the "Don't show this again" choice."""
    settings.setValue(LAUNCHER_SUPPRESSED_SETTINGS_KEY, bool(suppressed))


def resolve_menu_entries(window) -> dict:
    """``command_id -> (menu-path label, QAction)`` for every menu command.

    Straight off `ToolbarController`'s walk of the live menu bar — the launcher
    holds no action registry of its own, so an entry can never drift from the
    menu item it stands for. Re-walked on each call (`collect_menu_commands` is
    designed to be re-callable) so a menu built after startup is still found.
    """
    toolbar = window._toolbar_ui
    labels = dict(toolbar.collect_menu_commands())
    return {
        command_id: (labels.get(command_id, action.text()), action)
        for command_id, action in toolbar.menu_commands.items()
    }


class LauncherDialog(QDialog):
    """The four-group launcher. Holds no behaviour beyond "which entry was
    picked" — the picked entry's own ``QAction`` does the work."""

    def __init__(
        self,
        entries: dict,
        *,
        groups: Sequence[tuple[str, Sequence[str]]] = LAUNCHER_GROUPS,
        suppressed: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("PGTP Editor")
        self.setModal(True)
        self._entries = entries
        self._chosen_command_id: str | None = None
        #: command_id -> the QPushButton standing for it (test seam).
        self._buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(self)
        intro = QLabel("What would you like to do?", self)
        intro.setStyleSheet("font-weight: bold;")
        layout.addWidget(intro)

        grid = QGridLayout()
        layout.addLayout(grid)
        for index, (title, command_ids) in enumerate(groups):
            box = self._build_group(title, command_ids)
            if box is None:
                # Every id in the group is missing from the menu bar (a menu
                # renamed out from under the table): show nothing rather than an
                # empty frame. Never a crash -- the launcher must not be able to
                # stop the app from starting.
                continue
            grid.addWidget(box, index // 2, index % 2)

        self.suppress_checkbox = QCheckBox("Don't show this again", self)
        self.suppress_checkbox.setChecked(bool(suppressed))
        layout.addWidget(self.suppress_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        # Cancel/Escape/close lands in the app exactly as before -- it NEVER
        # quits (FQ-010: quitting would make the launcher a gate on running the
        # app at all).
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.button_box = buttons

    def _build_group(self, title: str, command_ids: Sequence[str]):
        box = QGroupBox(title, self)
        box_layout = QVBoxLayout(box)
        hint = _GROUP_HINTS.get(title)
        if hint:
            label = QLabel(hint, box)
            label.setWordWrap(True)
            box_layout.addWidget(label)
        found = False
        for command_id in command_ids:
            entry = self._entries.get(command_id)
            if entry is None:
                continue
            found = True
            label, action = entry
            button = QPushButton(label, box)
            button.setToolTip(f"Runs {label}")
            # Mirror the menu item's enabled state: `Generation ▸ Save reJSON…`
            # starts disabled (there is no gap JSON yet), and a button that looks
            # clickable but silently does nothing is worse than a greyed one.
            # Read once — the launcher is short-lived and modal, so nothing can
            # change the answer while it is up.
            button.setEnabled(action.isEnabled())
            # Default-argument binding, not a closure over the loop variable.
            button.clicked.connect(
                lambda _checked=False, cid=command_id: self.choose(cid)
            )
            box_layout.addWidget(button)
            self._buttons[command_id] = button
        box_layout.addStretch(1)
        if not found:
            box.deleteLater()
            return None
        return box

    # -- test seam -----------------------------------------------------------

    def entry_ids(self) -> list[str]:
        """The command ids the launcher actually offers, in display order."""
        return list(self._buttons)

    def button_for(self, command_id: str):
        """The ``QPushButton`` standing for `command_id`, or None."""
        return self._buttons.get(command_id)

    @property
    def chosen_command_id(self) -> str | None:
        """The picked entry's command id, or None if the launcher was closed."""
        return self._chosen_command_id

    @property
    def suppress_requested(self) -> bool:
        """Whether "Don't show this again" is ticked."""
        return self.suppress_checkbox.isChecked()

    def set_suppressed(self, suppressed: bool) -> None:
        self.suppress_checkbox.setChecked(bool(suppressed))

    def choose(self, command_id: str) -> None:
        """Record a pick and accept. Does NOT trigger the action — that happens
        in :func:`show_launcher`, once the modal is down, so an action that opens
        its own file dialog is never stacked on top of this one."""
        if command_id not in self._entries:
            return
        self._chosen_command_id = command_id
        self.accept()

    def cancel(self) -> None:
        """What Escape / the window close button do: no pick, reject."""
        self._chosen_command_id = None
        self.reject()

    def keyPressEvent(self, event):
        # Explicit so the "Escape never quits, it just lands in the app" rule is
        # visible here rather than inherited: QDialog's default already rejects,
        # this only makes sure the pick stays cleared.
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            return
        super().keyPressEvent(event)


def show_launcher(
    window,
    settings,
    *,
    groups: Sequence[tuple[str, Sequence[str]]] = LAUNCHER_GROUPS,
    resolve_entries: Callable[[object], dict] | None = None,
    exec_dialog: Callable[[QDialog], int] | None = None,
    force: bool = False,
) -> str | None:
    """Show the launcher over `window` and run the picked entry's action.

    Returns the picked ``command_id``, or ``None`` when the launcher was
    suppressed or closed without a pick. **Never quits the app** on any path.

    `force=True` bypasses the persisted "Don't show this again" — that is what
    ``File ▸ Show Launcher…`` passes, so the flag is never irreversible.
    `resolve_entries` and `exec_dialog` are the injectable seams: tests drive
    the dialog's methods and never enter a real modal loop.
    """
    if not force and launcher_suppressed(settings):
        return None

    resolve = resolve_entries if resolve_entries is not None else resolve_menu_entries
    entries = resolve(window)
    dialog = LauncherDialog(entries, groups=groups, parent=window)
    runner = exec_dialog if exec_dialog is not None else (lambda dlg: dlg.exec())
    runner(dialog)

    # Read on EVERY exit path: ticking the box and then picking an entry must
    # persist just as ticking it and closing does.
    set_launcher_suppressed(settings, dialog.suppress_requested)

    command_id = dialog.chosen_command_id
    if command_id is None:
        return None
    entry = entries.get(command_id)
    if entry is None:
        return None
    _label, action = entry
    action.trigger()
    return command_id
