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
"""The customizable Main Toolbar lane (Sub-project E, BUG-027, FQ-004).

What it owns
------------
Everything about the icon bar and nothing else: the ``QToolBar`` itself, the
ordered command-id list on it, the per-command icon assignments, the enumerated
menu-command universe those ids resolve against, the GC pins that enumeration
needs, and the non-modal Customize Toolbar dialog.

Why this lane was extracted first
---------------------------------
It is the cleanest cut in ``main_window.py``: it holds **no document state** and
consumes only the menu bar, ``QSettings`` and the application palette. Nothing
about an open ``.pgtp``, a DDL project, a sandbox session or the center stage
reaches in here, so it is the cheapest place to prove the collaborator pattern
before the expensive lanes follow it.

The menu bar *is* the command universe
--------------------------------------
BUG-027: rather than a static registry of seven commands, the offerable set is
derived by walking the live menu bar, and a toolbar button is the menu's **own
``QAction``** — so it shares the menu item's slot, enabled state, checked state
and shortcut for free and can never drift from it. Two consequences are
load-bearing and easy to undo by accident:

* ``QToolBar.clear()`` would *delete* those shared actions in PySide, taking the
  live menu item down with it. :meth:`apply_ids` uses ``removeAction``.
* ``QAction.menu()`` hands the returned ``QMenu``'s ownership to Python, so
  letting the wrapper go out of scope destroys the real menu and every action in
  it. Every submenu the walk descends into is pinned in :attr:`menu_keepalive`
  for the controller's lifetime, and that list is **never cleared** — releasing
  the last reference is precisely what destroys the menus. This is why the pin
  list moved *with* this controller instead of being left behind as a local in
  the host.

Shape
-----
A ``QObject`` following ``ui/sandbox_controller.py``: it takes a
:class:`~pgtp_editor.ui.ui_shell.UiShell`, constructs headless, and holds no
reference to ``MainWindow`` beyond the shell's dialog-parent ``window`` — which
appears here exactly once, as ``CustomizeToolbarDialog``'s parent. It emits no
signals because nothing outside the lane needs to observe it; the host drives it
(``refresh_icons()`` after a theme flip) and the View menu triggers
``open_customize_dialog()``.

Construction is two-phase on purpose: ``__init__`` is inert and :meth:`build`
must be called **after the menu bar is finished**, because it walks it.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.customize_toolbar_dialog import CustomizeToolbarDialog
from pgtp_editor.ui.icons import catalog_ids as icon_catalog_ids, themed_icon
from pgtp_editor.ui.toolbar_registry import (
    DEFAULT_TOOLBAR_IDS,
    ICON_ASSIGNMENTS_SETTINGS_KEY,
    command_id_for,
    icon_id_for,
    menu_path_label,
    parse_icon_assignments,
    resolve_ids,
    resolve_icon_assignments,
    serialize_icon_assignments,
)
from pgtp_editor.ui.ui_shell import UiShell

#: QSettings key holding the ordered toolbar command ids.
TOOLBAR_IDS_SETTINGS_KEY = "toolbarIds"


class ToolbarController(QObject):
    """Owns the Main Toolbar: its command set, its icons, its persistence."""

    def __init__(self, shell: UiShell, parent: QObject | None = None):
        super().__init__(parent)
        self._shell = shell
        self._settings = shell.settings
        #: The live menu bar, set by `build` -- the command universe is re-read
        #: from it on every walk, so commands the app grows after startup are
        #: picked up without a restart.
        self._menu_bar = None
        self._toolbar = None
        self._toolbar_ids: list[str] = []
        self._toolbar_icon_ids: dict[str, str] = {}
        self._menu_commands: dict[str, object] = {}
        self._menu_command_pairs: list[tuple[str, str]] = []
        # Strong refs to every QMenu (and the QAction owning it) the walk
        # descends into -- see the module docstring; without these PySide
        # destroys them. NEVER cleared.
        self._menu_keepalive: list[object] = []
        self._menu_keepalive_seen: set[int] = set()
        # Held so the non-modal Customize Toolbar dialog is not GC'd while shown.
        self._customize_toolbar_dialog: CustomizeToolbarDialog | None = None

    # -- construction --------------------------------------------------------

    def build(self, menu_bar, add_toolbar: Callable[[str], object]) -> None:
        """Create the Main Toolbar and restore its command set from settings.

        `menu_bar` is the finished ``QMenuBar`` (the command universe);
        `add_toolbar` is the host's ``addToolBar`` — the ``QMainWindow``
        gesture stays on the host, this lane only receives the result.
        """
        self._menu_bar = menu_bar
        self._toolbar = add_toolbar("Main Toolbar")
        # objectName so the window's saveState()/restoreState() persists this
        # toolbar's position along with the docks.
        self._toolbar.setObjectName("main_toolbar")
        # Icon + label: each command carries a Breeze icon beside its text.
        self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # BUG-027: the toolbar's command universe IS the menu bar. Built here
        # (after the menu bar exists) rather than from a static registry, so
        # every command the app has -- present and future -- is offerable in
        # Customize Toolbar with no bookkeeping.
        self._menu_commands = {}
        self._menu_command_pairs = []
        self.collect_menu_commands()
        self._toolbar_ids = []
        # FQ-004: command_id -> chosen icon id. Restored before the first
        # apply_ids so the very first paint already honours the user's choices
        # rather than flashing the defaults.
        self._toolbar_icon_ids = self._restore_icon_ids()
        self.apply_ids(self._restore_ids())

    # -- read-only surface ---------------------------------------------------

    @property
    def toolbar(self):
        """The ``QToolBar`` (None before :meth:`build`)."""
        return self._toolbar

    @property
    def command_ids(self) -> list[str]:
        """The ordered command ids currently on the toolbar."""
        return self._toolbar_ids

    @property
    def icon_ids(self) -> dict[str, str]:
        """FQ-004 per-command icon assignments (command_id -> icon id)."""
        return self._toolbar_icon_ids

    @property
    def menu_commands(self) -> dict:
        """command_id -> the menu's own ``QAction``, from the last walk."""
        return self._menu_commands

    @property
    def menu_keepalive(self) -> list:
        """The GC pins for every walked submenu — see the module docstring."""
        return self._menu_keepalive

    @property
    def customize_dialog(self) -> CustomizeToolbarDialog | None:
        """The live Customize Toolbar dialog, if one has been opened."""
        return self._customize_toolbar_dialog

    # -- the menu-bar walk ---------------------------------------------------

    def collect_menu_commands(self) -> list[tuple[str, str]]:
        """Refresh `menu_commands` (id -> QAction) and the ordered (id, label)
        pairs from the live menu bar, and return the pairs."""
        self._menu_command_pairs = self.all_menu_commands()
        self._menu_commands = {
            command_id: action
            for command_id, _label, action in self._walk_menu_actions()
        }
        return self._menu_command_pairs

    def all_menu_commands(self) -> list[tuple[str, str]]:
        """Ordered (id, label) pairs for every menu command -- what the
        Customize Toolbar dialog offers in its Available list."""
        return [
            (command_id, label)
            for command_id, label, _action in self._walk_menu_actions()
        ]

    def _walk_menu_actions(self, menu=None, path=(), seen=None):
        """Depth-first walk of the menu bar yielding (id, label, QAction) for
        every *leaf* command.

        Skips separators and submenu placeholders (an action that opens a
        submenu is not itself a command). The dynamic "Open Recent" submenu is
        skipped wholesale -- its children are transient per-session file
        entries and must never be pinned to the toolbar. Duplicate ids (two
        identically-labelled actions in one menu) get a numeric suffix so an
        id always resolves to exactly one action.

        CAUTION: `QAction.menu()` hands the returned QMenu's ownership to
        Python, so letting that wrapper go out of scope DESTROYS the real menu
        and every action in it (this crashed startup with "Internal C++ object
        (QAction) already deleted" the moment `_restore_theme` touched the
        View menu). Every submenu we descend into is therefore pinned in
        `_menu_keepalive` for the controller's lifetime."""
        if seen is None:
            seen = {}
        actions = self._menu_bar.actions() if menu is None else menu.actions()
        for action in actions:
            if action.isSeparator():
                continue
            label = action.text()
            submenu = action.menu()
            if submenu is not None:
                # Pin BOTH the submenu and the action that owns it: dropping
                # either one takes the whole branch's actions down with it.
                # Never CLEAR this list to re-pin -- releasing the last ref is
                # exactly what destroys the menus.
                for obj in (action, submenu):
                    if id(obj) not in self._menu_keepalive_seen:
                        self._menu_keepalive_seen.add(id(obj))
                        self._menu_keepalive.append(obj)
                if "recent" in menu_path_label([label]).lower():
                    continue
                yield from self._walk_menu_actions(submenu, path + (label,), seen)
                continue
            full_path = path + (label,)
            command_id = command_id_for(full_path)
            if not command_id:
                continue
            seen[command_id] = seen.get(command_id, 0) + 1
            if seen[command_id] > 1:
                command_id = f"{command_id}-{seen[command_id]}"
            yield command_id, menu_path_label(full_path), action

    # -- persistence ---------------------------------------------------------

    def _restore_ids(self) -> list[str]:
        """Read the stored toolbar ids, tolerant of the backend returning a
        list, a comma-separated string, or None; fall back to the default set
        when nothing valid is stored.

        BUG-027: goes through `resolve_ids`, which maps the pre-BUG-027 legacy
        ids (`save`, `undo`, ...) onto their menu-path ids -- without that,
        every existing user's saved toolbar would be dropped as unknown."""
        stored = self._settings.value(TOOLBAR_IDS_SETTINGS_KEY)
        if stored is None:
            ids = DEFAULT_TOOLBAR_IDS
        elif isinstance(stored, str):
            ids = stored.split(",")
        else:
            ids = list(stored)
        known = self._menu_commands
        ids = resolve_ids(ids, known)
        return ids if ids else resolve_ids(DEFAULT_TOOLBAR_IDS, known)

    def _save_ids(self) -> None:
        """Persist the current toolbar ids (stored as a list)."""
        self._settings.setValue(TOOLBAR_IDS_SETTINGS_KEY, self._toolbar_ids)

    def _restore_icon_ids(self) -> dict[str, str]:
        """Read the stored per-command icon assignments (FQ-004).

        Pruned through `resolve_icon_assignments` against the live menu
        commands and the vendored catalog, so an assignment naming a command
        or an icon that no longer exists is dropped rather than raising later
        -- the same self-healing `resolve_ids` already applies to the id list.
        """
        stored = parse_icon_assignments(
            self._settings.value(ICON_ASSIGNMENTS_SETTINGS_KEY)
        )
        if not stored:
            return {}
        self.collect_menu_commands()
        return resolve_icon_assignments(stored, self._menu_commands, icon_catalog_ids())

    def _save_icon_ids(self) -> None:
        self._settings.setValue(
            ICON_ASSIGNMENTS_SETTINGS_KEY,
            serialize_icon_assignments(self._toolbar_icon_ids),
        )

    # -- painting ------------------------------------------------------------

    def apply_ids(self, ids) -> None:
        """Clear and repopulate the toolbar from an ordered id list (unknown
        and duplicate ids are dropped).

        BUG-027: adds the **real menu QAction**, not a lookalike wired to a
        slot table. The button therefore shares the menu item's enabled state,
        checked state and shortcut for free, and can never drift from what the
        menu does."""
        ids = resolve_ids(ids, self._menu_commands)
        # NOT `self._toolbar.clear()`: PySide's clear() DELETES the underlying
        # QActions, which since BUG-027 are the menus' own actions -- that
        # destroyed live menu items (and crashed the next `setChecked` on one).
        # removeAction detaches without taking ownership.
        for existing in list(self._toolbar.actions()):
            self._toolbar.removeAction(existing)
        color = self._icon_color()
        for command_id in ids:
            action = self._menu_commands[command_id]
            self._set_action_icon(action, command_id, color)
            self._toolbar.addAction(action)
        self._toolbar_ids = ids

    def apply_and_save(self, ids, icon_assignments=None) -> None:
        """Apply an id list to the toolbar and persist it (test seam / the
        Customize dialog's OK path).

        `icon_assignments` (FQ-004) is applied first so the rebuild below
        already paints the chosen icons; None leaves the current assignments
        untouched, keeping every existing caller working unchanged.
        """
        if icon_assignments is not None:
            self._toolbar_icon_ids = dict(icon_assignments)
            self._save_icon_ids()
        self.apply_ids(ids)
        self._save_ids()

    def _icon_color(self):
        """The current palette's window-text color -- what the toolbar icons
        are tinted to so they stay legible against either theme. Reads the
        APP palette (not the window's) so it reflects the just-applied theme
        even in the window whose toggle triggered the change."""
        return QApplication.instance().palette().color(QPalette.ColorRole.WindowText)

    def _set_action_icon(self, action, command_id, color) -> None:
        """Tint and assign the Breeze icon for `command_id` to `action`.

        BUG-027: only the legacy seven have a vendored SVG, and the toolbar now
        hosts real menu QActions -- so an id with no icon is the normal case,
        not an error, and is left icon-less (text-beside-icon copes). The icon
        is hidden in menus so decorating a shared action for the toolbar does
        not change how the menu looks.

        FQ-004: a user-chosen icon (Customize Toolbar ▸ Choose Icon…) wins over
        the legacy default, so any button can be decorated or re-decorated from
        the vendored Breeze catalog. With no assignment stored the lookup falls
        straight through to `ICON_ID_BY_COMMAND` and behavior is unchanged."""
        icon_id = icon_id_for(command_id, self._toolbar_icon_ids)
        if icon_id is None:
            return
        try:
            action.setIcon(themed_icon(icon_id, color))
            action.setIconVisibleInMenu(False)
        except Exception:  # pragma: no cover - vendored set is always present
            pass

    def refresh_icons(self) -> None:
        """Re-tint every current toolbar action's icon to the current palette
        color, without rebuilding the toolbar. Called after a theme change so
        the icons recolor to stay legible when the palette flips."""
        color = self._icon_color()
        for action, command_id in zip(self._toolbar.actions(), self._toolbar_ids):
            self._set_action_icon(action, command_id, color)

    # -- the Customize dialog ------------------------------------------------

    def open_customize_dialog(self) -> None:
        """Open the (non-modal) Customize Toolbar dialog; on OK, apply and
        persist the chosen ordered id list."""
        # BUG-027: offer every menu command, re-enumerated at open time so
        # anything the menus gained since startup is included.
        dialog = CustomizeToolbarDialog(
            self.collect_menu_commands(),
            self._toolbar_ids,
            # The ONE sanctioned use of shell.window: a dialog parent.
            self._shell.window,
            self._toolbar_icon_ids,
        )
        dialog.accepted.connect(
            lambda: self.apply_and_save(
                dialog.result_ids(), dialog.result_icon_assignments()
            )
        )
        self._customize_toolbar_dialog = dialog
        dialog.show()
