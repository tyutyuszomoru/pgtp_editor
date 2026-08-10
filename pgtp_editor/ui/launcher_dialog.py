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

"""The startup launcher (FQ-010, reshaped by FQ-027): the app's THREE major
modes, in one row, on one modal.

Why it exists
-------------
Opening the app used to present no guidance at all — an empty Raw XML tab and an
empty Project Tree, with five workflows hidden behind five different menus. The
launcher names the groups those workflows collapse into and dispatches each
one to the **existing** menu ``QAction``, so there is never a second
implementation of an open/new/generate gesture.

FQ-027: three columns, not four groups
--------------------------------------
The four FQ-010 groups became **Standalone | Project | Maintenance** — the
app's own vocabulary for its three major modes — laid out as one 1×3 row.
FQ-010's *Open a pgtp for editing* and *Open other files* merged into
**Standalone**; the §20 re_phpgen/panGen entries left the launcher entirely.

Picking a column ALSO records that column's mode on the window
(:func:`show_launcher` calls ``window.set_workflow_mode(...)``), which is what
makes **Maintenance** trim the menu bar. The mode is **session-only** — there is
no QSettings key for it and it cannot survive a restart, which is precisely why
it is safe: a menu-less app can never be inherited from a previous run.

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
* **Picking a mode is OBLIGATORY when there is no mode yet (BUG-059).** Owner
  ruling, verbatim: *"do not permit to close the launcher without having chosen a
  mode. If launcher is opened with a mode already chosen (new session), let it be
  closed, otherwise make choice obligatory. this means that also window close
  button must be disabled"* — because ``MainWindow._workflow_mode`` starts as
  ``None`` and is never read from settings (FQ-027), a dismissable startup
  launcher left the app in the invalid *No Mode* state.

  So the launcher has TWO regimes, chosen by :func:`show_launcher` from the
  window's current mode, and the undismissable one is the DEFAULT:

  - **No mode yet (startup)** → ``dismissable=False``: no ``Close`` button, no
    native ✕ (``WindowCloseButtonHint`` stripped *and* ``closeEvent`` ignored,
    which is the authoritative barrier — the hint is only advisory on some
    window managers and does not cover ``Alt+F4``), ``reject()`` neutralised,
    Escape swallowed, :meth:`LauncherDialog.cancel` inert, and
    :meth:`LauncherDialog.choose` refuses a column that names no mode. Every
    exit from the dialog therefore carries a mode: *No Mode* is not merely
    unlikely, it is unreachable.
  - **A mode already chosen (``File ▸ New Session``)** → ``dismissable=True``:
    it closes as it always did, and dismissal **retains** the mode the session
    is already in (``new_session`` no longer clears it — that clear was the only
    other production path back to ``None``).
* **Cancelling still NEVER quits.** Where dismissal is allowed it lands in the
  app exactly as before (FQ-010: quitting would make the launcher a gate on
  running the app at all) — :func:`show_launcher` simply returns ``None`` and
  leaves the current mode standing.
* **NOT suppressible (FQ-027).** FQ-010's "Don't show this again" checkbox, its
  ``launcherSuppressed`` QSettings key and the ``force=`` bypass that existed
  only to override it are **deleted**. The launcher is the single starting gate
  where a mode is picked, so it must always appear: with the mode session-only
  and ``File ▸ New Session`` re-entering the launcher on demand, a persisted
  "skip the launcher forever" toggle was both redundant and a trap.
* The chosen action is triggered **after** the modal is down, so an action that
  itself opens a ``QFileDialog`` is not stacked on top of the launcher.

Test seam
---------
Mirrors ``CustomizeToolbarDialog``/``IconPickerDialog``: tests drive
:meth:`LauncherDialog.entry_ids`, :meth:`LauncherDialog.choose` and
:meth:`LauncherDialog.cancel` directly, and pass ``exec_dialog=`` to
:func:`show_launcher`. **No test ever calls ``.exec()``.**
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

#: The three major workflow modes (FQ-027). Plain strings, not an enum, because
#: they cross a lazy import boundary (`MainWindow` imports this module only
#: inside the two methods that need it) and are compared, never arithmetic.
#:
#: **These are SESSION values.** There is deliberately no QSettings key here:
#: FQ-027 supersedes FQ-011's persisted-mode design precisely so a filtered menu
#: bar can never be inherited from a previous run.
MODE_STANDALONE = "standalone"
MODE_PROJECT = "project"
MODE_MAINTENANCE = "maintenance"

#: The three columns, as (title, ordered command ids), left to right. The ids are
#: the toolbar registry's menu-path ids (`toolbar_registry.command_id_for`), so
#: this table never holds a label, a slot or a duplicate of any menu wiring.
#:
#: FQ-027 reshaped FQ-010's four groups into these three:
#: * **Standalone** merges FQ-010's *Open a pgtp for editing* and *Open other
#:   files* — both are "open something without a project".
#: * **Project** is FQ-010's project group, unchanged.
#: * **Maintenance** is **Edit XSD + Import XSD** only. The owner's verbatim
#:   "Open XSD" does NOT map to a live command — the read-only
#:   `SchemaViewerWindow` / `Schema ▸ Open XSD` was deleted 2026-07-24 in favour
#:   of the editable Edit XSD tab — and the §20 re_phpgen/panGen entries that
#:   FQ-010 put in this group LEFT the launcher: they are a generation loop, not
#:   an administrative task on the app's own schema.
LAUNCHER_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Standalone",
        ("file.open", "file.open-php-file"),
    ),
    (
        "Project",
        ("file.new-project", "file.open-project"),
    ),
    (
        "Maintenance",
        ("schema.edit-xsd", "schema.import-xsd"),
    ),
)

#: Column title -> the workflow mode picking it enters. Kept beside
#: `LAUNCHER_GROUPS` rather than folded into it as a third tuple element so the
#: `(title, ids)` shape stays what `groups=` callers (and every test that passes
#: an ad-hoc group) construct — exactly how `_GROUP_HINTS` is keyed.
GROUP_MODES: dict[str, str] = {
    "Standalone": MODE_STANDALONE,
    "Project": MODE_PROJECT,
    "Maintenance": MODE_MAINTENANCE,
}

#: Short "what is this mode" lines under each column title. Deliberately
#: descriptive of behaviour that already exists — the UX review's naming rulings
#: are a later step, so no new vocabulary is coined here.
_GROUP_HINTS: dict[str, str] = {
    "Standalone": (
        "Edit a .pgtp with the XML tooling, or a custom PHP file beside it. "
        "No project, no sandbox."
    ),
    "Project": (
        "Work on the quality database through a local sandbox, or converge a "
        "deployable .pgtp by diff/merge."
    ),
    "Maintenance": (
        "One-off administrative work on the app's own schema. Trims the menu "
        "bar to Schema, Help and a short File menu for this session."
    ),
}


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
    """The three-column launcher. Holds no behaviour beyond "which entry was
    picked, in which column" — the picked entry's own ``QAction`` does the
    work, and the column decides the session's workflow mode."""

    def __init__(
        self,
        entries: dict,
        *,
        groups: Sequence[tuple[str, Sequence[str]]] = LAUNCHER_GROUPS,
        dismissable: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("PGTP Editor")
        self.setModal(True)
        #: BUG-059: whether this launcher may be left without a pick. FALSE by
        #: default -- the safe regime is the one that cannot produce an invalid
        #: state, so a caller must ASK for dismissability rather than forget to
        #: forbid it. `show_launcher` derives it from the window's current mode.
        self._dismissable = bool(dismissable)
        if not self._dismissable:
            # Advisory only (some WMs draw the ✕ regardless, and neither hint
            # touches Alt+F4) -- `closeEvent` below is the real barrier. Kept
            # anyway so the frame doesn't offer a button that does nothing.
            self.setWindowFlags(
                self.windowFlags()
                & ~Qt.WindowType.WindowCloseButtonHint
                & ~Qt.WindowType.WindowContextHelpButtonHint
            )
        self._entries = entries
        self._chosen_command_id: str | None = None
        #: command_id -> the QPushButton standing for it (test seam).
        self._buttons: dict[str, QPushButton] = {}
        #: command_id -> its column's title, so a pick can name its mode.
        self._group_of: dict[str, str] = {}

        layout = QVBoxLayout(self)
        intro = QLabel("What would you like to do?", self)
        intro.setStyleSheet("font-weight: bold;")
        layout.addWidget(intro)

        grid = QGridLayout()
        layout.addLayout(grid)
        # ONE ROW (FQ-027): `(0, index)`, not FQ-010's `(index // 2, index % 2)`
        # 2x2 wrap. The three columns ARE the app's three major modes, and a
        # mode taxonomy read as a grid stops looking like a taxonomy.
        for index, (title, command_ids) in enumerate(groups):
            box = self._build_group(title, command_ids)
            if box is None:
                # Every id in the group is missing from the menu bar (a menu
                # renamed out from under the table): show nothing rather than an
                # empty frame. Never a crash -- the launcher must not be able to
                # stop the app from starting.
                continue
            grid.addWidget(box, 0, index)

        # BUG-059: no `Close` button at all in the undismissable regime -- an
        # empty box rather than no box, so `button_box` is always present for the
        # test seam and the layout is identical in both regimes. Where the button
        # DOES exist, cancel/Escape/close lands in the app exactly as before --
        # it NEVER quits (FQ-010: quitting would make the launcher a gate on
        # running the app at all).
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
            if self._dismissable
            else QDialogButtonBox.StandardButton.NoButton,
            self,
        )
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
            self._group_of[command_id] = title
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
    def chosen_group_title(self) -> str | None:
        """The title of the column the pick came from, or None."""
        return self._group_of.get(self._chosen_command_id or "")

    @property
    def chosen_workflow_mode(self) -> str | None:
        """The workflow mode the picked column enters (FQ-027), or None — for
        no pick, and for an ad-hoc `groups=` column that names no mode."""
        return GROUP_MODES.get(self.chosen_group_title or "")

    @property
    def dismissable(self) -> bool:
        """Whether this launcher may be left without a pick (BUG-059)."""
        return self._dismissable

    def choose(self, command_id: str) -> None:
        """Record a pick and accept. Does NOT trigger the action — that happens
        in :func:`show_launcher`, once the modal is down, so an action that opens
        its own file dialog is never stacked on top of this one."""
        if command_id not in self._entries:
            return
        # BUG-059: in the undismissable regime a pick must NAME a mode, or it is
        # refused. That is what makes "left the launcher with no mode"
        # structurally impossible rather than merely improbable -- the only way
        # out of an undismissable launcher is an `accept()` that carries a mode.
        # Only an ad-hoc `groups=` column can fail this (all three real columns
        # are in `GROUP_MODES`), and such a column belongs to the test/caller
        # seam, which must ask for `dismissable=True` to use it.
        if not self._dismissable:
            if GROUP_MODES.get(self._group_of.get(command_id) or "") is None:
                return
        self._chosen_command_id = command_id
        self.accept()

    def cancel(self) -> None:
        """What Escape / the window close button do: no pick, reject.

        Inert when undismissable (BUG-059) — there is nothing to cancel INTO."""
        if not self._dismissable:
            return
        self._chosen_command_id = None
        self.reject()

    def reject(self) -> None:
        # Neutralised when undismissable, and this is the funnel that matters
        # most: `QDialogButtonBox.rejected`, `QDialog`'s own Escape handling and
        # any programmatic `reject()` all pass through here.
        if not self._dismissable:
            return
        super().reject()

    def closeEvent(self, event):
        # THE authoritative barrier (BUG-059): `WindowCloseButtonHint` is only
        # advisory and covers neither `Alt+F4` nor a window-manager close, both
        # of which arrive here. Refusing the event is what actually keeps the
        # modal up.
        if not self._dismissable:
            event.ignore()
            return
        super().closeEvent(event)

    def keyPressEvent(self, event):
        # Explicit so both rules are visible here rather than inherited:
        # dismissable -> "Escape never quits, it just lands in the app" (QDialog
        # would already reject; this only makes sure the pick stays cleared);
        # undismissable -> Escape is SWALLOWED, so it never reaches QDialog's
        # default reject at all.
        if event.key() == Qt.Key.Key_Escape:
            if self._dismissable:
                self.cancel()
            return
        super().keyPressEvent(event)


def show_launcher(
    window,
    settings=None,
    *,
    groups: Sequence[tuple[str, Sequence[str]]] = LAUNCHER_GROUPS,
    dismissable: bool | None = None,
    resolve_entries: Callable[[object], dict] | None = None,
    exec_dialog: Callable[[QDialog], int] | None = None,
) -> str | None:
    """Show the launcher over `window` and run the picked entry's action.

    Returns the picked ``command_id``, or ``None`` when the launcher was closed
    without a pick — which BUG-059 makes possible **only** when the window is
    already in a mode. **Never quits the app** on any path, and — since FQ-027
    deleted the suppression flag — it is never skipped either.

    `dismissable` defaults to *"is there already a mode to fall back into?"*,
    read straight off ``window.workflow_mode``: at startup there is none, so the
    launcher is undismissable and a choice is obligatory; from
    ``File ▸ New Session`` there is one, so it closes and that mode stands. This
    is the ONE place the regime is decided, so no caller can accidentally open a
    dismissable launcher over a mode-less window. Pass it explicitly only to
    exercise a regime directly (the test seam).

    `settings` no longer has anything to read or write here (the only key this
    module ever owned was ``launcherSuppressed``); it is kept as a positional
    parameter because it is part of `main.py`'s ``launcher=`` seam contract,
    which every stub in the suite is written against.

    `resolve_entries` and `exec_dialog` are the injectable seams: tests drive
    the dialog's methods and never enter a real modal loop.
    """
    resolve = resolve_entries if resolve_entries is not None else resolve_menu_entries
    entries = resolve(window)
    if dismissable is None:
        dismissable = getattr(window, "workflow_mode", None) is not None
    dialog = LauncherDialog(
        entries, groups=groups, dismissable=dismissable, parent=window
    )
    runner = exec_dialog if exec_dialog is not None else (lambda dlg: dlg.exec())
    runner(dialog)

    command_id = dialog.chosen_command_id
    if command_id is None:
        return None
    entry = entries.get(command_id)
    if entry is None:
        return None
    # The picked COLUMN is what enters the session workflow mode (FQ-027) --
    # set BEFORE the action runs, so e.g. `Edit XSD` opens into an already
    # trimmed menu bar rather than flashing the full one. Guarded by `hasattr`
    # because the window is a test double on most call sites here.
    mode = dialog.chosen_workflow_mode
    if mode is not None and hasattr(window, "set_workflow_mode"):
        window.set_workflow_mode(mode)
    _label, action = entry
    action.trigger()
    return command_id
