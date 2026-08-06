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
"""The find / replace / bookmarks / validate lane.

What it owns
------------
Everything about *searching the open documents and reporting findings into the
Audit panel*, plus the two menus that are nothing but that:

* the **per-tab find-bar routing** (:meth:`active_find_bar`) and the matching
  **per-tab bookmark-editor routing** (:meth:`active_bookmark_editor`) — the two
  dispatches that make Ctrl+F, F3, Ctrl+F2 and friends follow whichever editor
  tab is active (Raw XML / Edit XSD / DDL Explorer / an editable DDL object /
  a §21 PHP tab);
* the **Bookmarks menu** — a menu owned outright by one collaborator moves with
  it, so this lane builds it (:meth:`build_bookmarks_menu`);
* the **Edit-menu Find… / Replace… actions**, handed over by the host after the
  Edit menu is built (:meth:`set_find_actions`), because the rest of that menu
  (undo/redo/history/selection) belongs elsewhere. Caption Mode gates them
  through :meth:`set_find_actions_enabled`;
* the **whole streaming Find-All run**: the batch timer, the match iterator, the
  stop flag, the running count, the term and the target tab — see below;
* the **Tier-2 project validation** run (:meth:`validate_project`) and the two
  prefix-scoped Audit cleanups (:meth:`clear_find_results` /
  :meth:`clear_validation_results`) that keep ``[Find]`` and ``[Validate]`` rows
  from clearing each other.

The Find-All iteration state is DIRECTLY REACHABLE, on purpose
-------------------------------------------------------------
:meth:`find_all` does not search synchronously: it hands the work to a 0ms
``QTimer`` that appends one ``_FIND_ALL_BATCH`` of matches per tick, yielding to
the event loop in between so the UI stays responsive and Stop takes effect
promptly. A test cannot assert on that by pumping the event loop (a fast machine
finishes the whole run in one spin, a slow one in ten), so the suite drives the
loop by hand instead: stop the timer, call :meth:`_find_all_step` once, read the
partial :attr:`find_all_count`, flip the stop flag, step again.

That makes the iteration state part of this lane's *tested* surface, so it is
exposed as it is written:

* the six pieces of state live as plain ``self._find_all_*`` attributes, which is
  where every write in this module lands;
* :attr:`find_all_timer`, :attr:`find_all_iter`, :attr:`find_all_count`,
  :attr:`find_all_term` and :attr:`find_all_target` are read-only properties that
  return **those very objects** — not copies, not snapshots. A test that does
  ``controller.find_all_timer.stop()`` must stop the timer this module will next
  observe as ``self._find_all_timer``, and a test that re-triggers a run and
  asserts the new timer ``is not`` the previous one must see real object
  identity. Never route these through a value copy, a signal or a
  recomputed-on-read expression.

Read-only is correct here (unlike ``GenerationController.is_generating``): the
suite *reads* this state and drives the loop through
:meth:`_find_all_step` / :meth:`stop_find_all`, and every write is this module's
own. Should a future test need to assign one, add a setter — do not widen the
whole thing to public attributes.

Two find-all entry points, deliberately named apart
---------------------------------------------------
:meth:`find_all` is the *streaming run* — ``(term, target)`` in, Audit rows out.
It is what a ``FindReplaceBar``'s Find-All button ultimately reaches (the host
wires it as each bar's ``set_on_find_all``) and what
``CoherenceController`` is injected with to list a DB node's occurrences.
:meth:`find_all_in_active_bar` is the *Edit ▸ Find All menu action* — it asks the
active tab's bar to run its own find-all, which then comes back round through
:meth:`find_all`. Same lineage as :meth:`show_find` / :meth:`find_next` /
:meth:`replace_all`, which are all "act on the active bar".

Needs
-----
A ``UiShell`` covers the stage, the Audit panel, the status bar and the reveal of
the Raw XML tab. Validation additionally needs the open document, which is not
reachable through the shell, so it arrives as two injected **providers**
(``project`` / ``project_path``) exactly as in ``generation_controller.py``. When
``PgtpDocumentController`` lands, only those two host wiring lines move.

Shape
-----
A ``QObject`` following ``ui/xsd_controller.py``: it takes a
:class:`~pgtp_editor.ui.ui_shell.UiShell`, constructs headless, and never
dereferences ``shell.window``.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import QListWidgetItem

from pgtp_editor.ui import search
from pgtp_editor.ui.busy import busy_status
from pgtp_editor.ui.ui_shell import UiShell
from pgtp_editor.validation import tier2

#: Audit prefix every streaming Find-All row carries, so `clear_find_results`
#: can drop this run's rows without touching [Validate]/[Schema]/[PHP] ones.
_FIND_RESULT_PREFIX = "[Find] "

#: Audit prefix every Tier-2 validation row carries, for the same reason.
_VALIDATION_PREFIX = "[Validate] "

#: Matches appended per timer tick. Small enough that Stop feels immediate,
#: large enough that a big document does not spend all its time in the event loop.
_FIND_ALL_BATCH = 200


class _StatusBarProxy:
    """The `.showMessage(...)` object `ui/busy.py::busy_status` expects, backed by
    the shell's plain `status` callable.

    `busy_status` predates the decomposition and takes a status *bar*; the shell
    deliberately exposes only the one call (`status`), never the widget. This
    adapter bridges the two without giving the lane a window reference, and it
    forwards at CALL time so a test that patches `window.statusBar().showMessage`
    after construction is still honoured.
    """

    def __init__(self, status: Callable[..., None]):
        self._status = status

    def showMessage(self, *args, **kwargs) -> None:  # noqa: N802 - Qt's spelling
        self._status(*args, **kwargs)


class FindValidateController(QObject):
    """Owns find/replace routing, the Bookmarks menu, the streaming Find-All run
    and Tier-2 project validation."""

    def __init__(
        self,
        shell: UiShell,
        parent: QObject | None = None,
        *,
        project: Callable[[], object | None],
        project_path: Callable[[], str | None],
    ):
        super().__init__(parent)
        self._shell = shell
        #: Document-state providers -- see the module docstring.
        self._project = project
        self._project_path = project_path

        #: The Edit-menu Find… / Replace… actions, handed over by
        #: `set_find_actions` once the Edit menu is built. None until then.
        self._find_action = None
        self._replace_action = None

        #: The streaming Find-All run's whole state. PLAIN ATTRIBUTES, read back
        #: through the identity-preserving properties below -- see the module
        #: docstring, "The Find-All iteration state is DIRECTLY REACHABLE".
        self._find_all_timer = None
        self._find_all_iter = None
        self._find_all_stop = False
        self._find_all_count = 0
        self._find_all_term = ""
        self._find_all_target = "raw"

    # -- read-only surface ---------------------------------------------------
    # Each returns the LIVE object/value this module writes, so a test may stop
    # the timer, exhaust the iterator or compare timer identity across runs.

    @property
    def find_all_timer(self):
        """The in-flight batch ``QTimer``, or None between runs."""
        return self._find_all_timer

    @property
    def find_all_iter(self):
        """The in-flight match generator, or None between runs."""
        return self._find_all_iter

    @property
    def find_all_count(self) -> int:
        """Matches appended so far by the current/last run."""
        return self._find_all_count

    @property
    def find_all_term(self) -> str:
        """The term the current/last run searched for."""
        return self._find_all_term

    @property
    def find_all_target(self) -> str:
        """Which editor the current/last run searched: ``"raw"`` or ``"xsd"``."""
        return self._find_all_target

    @property
    def find_action(self):
        """The Edit ▸ Find… ``QAction`` (None before :meth:`set_find_actions`)."""
        return self._find_action

    @property
    def replace_action(self):
        """The Edit ▸ Replace… ``QAction`` (None before :meth:`set_find_actions`)."""
        return self._replace_action

    # -- construction --------------------------------------------------------

    def build_bookmarks_menu(self, menu_bar) -> None:
        """Add the Bookmarks menu to `menu_bar`.

        Each action resolves the target editor at TRIGGER time via
        `active_bookmark_editor`, not at build time -- the shared gutter base
        (§8) puts the same bookmark API on the Raw XML, Edit XSD and DDL
        Explorer editors, so the menu follows whichever is active instead of
        being bound to Raw XML forever.
        """
        menu = menu_bar.addMenu("Bookmarks")

        toggle_action = menu.addAction("Toggle Bookmark")
        toggle_action.setShortcut("Ctrl+F2")
        toggle_action.triggered.connect(
            lambda: self.active_bookmark_editor().toggle_bookmark_at_cursor()
        )

        next_action = menu.addAction("Next Bookmark")
        next_action.setShortcut("F2")
        next_action.triggered.connect(
            lambda: self.active_bookmark_editor().goto_next_bookmark()
        )

        prev_action = menu.addAction("Previous Bookmark")
        prev_action.setShortcut("Shift+F2")
        prev_action.triggered.connect(
            lambda: self.active_bookmark_editor().goto_prev_bookmark()
        )

        menu.addSeparator()
        clear_action = menu.addAction("Clear All Bookmarks")
        clear_action.triggered.connect(
            lambda: self.active_bookmark_editor().clear_bookmarks()
        )

    def set_find_actions(self, find_action, replace_action) -> None:
        """Adopt the Edit-menu Find… / Replace… actions.

        The host builds the Edit menu (most of it belongs to other lanes) and
        hands these two over, mirroring how `CoherenceController` receives the
        Database-menu toggle it owns.
        """
        self._find_action = find_action
        self._replace_action = replace_action

    def set_find_actions_enabled(self, enabled: bool) -> None:
        """Enable/disable the Edit-menu Find… / Replace… actions.

        Caption Mode is authoritative about Ctrl+F / Ctrl+R: while it is active
        those keys drive the caption Filter / Replace dialogs, so these two
        actions are disabled (disabling a QAction disables its shortcut, so
        there is no ambiguous-shortcut conflict) and restored on the way out.
        """
        if self._find_action is not None:
            self._find_action.setEnabled(enabled)
        if self._replace_action is not None:
            self._replace_action.setEnabled(enabled)

    # -- per-tab routing -----------------------------------------------------

    def active_find_bar(self):
        """The FindReplaceBar of the active editor tab; defaults to the Raw
        XML bar (revealing that tab) when no editor tab is active."""
        stage = self._shell.stage
        if stage.currentIndex() == stage.xsd_tab_index:
            return stage.xsd_find_replace_bar
        if stage.currentIndex() == stage.ddl_tab_index:
            # The DDL Explorer buffer has its own bar (spec §18.1, per-tab
            # document routing) -- without this branch Ctrl+F on the DDL tab
            # used to bounce the user back to Raw XML.
            return stage.ddl_editor_panel.find_replace_bar
        panel = stage.active_ddl_object_panel()
        if panel is not None:
            # The editable object tab's own bar (spec §18.5) -- Replace is
            # LIVE here, unlike the read-only DDL Explorer above.
            return panel.find_replace_bar
        php_tab = stage.active_php_file_tab()
        if php_tab is not None:
            # §21: the PHP tab owns its own FindReplaceBar. Without this branch
            # Ctrl+F on a PHP tab yanked the user over to Raw XML (the fallback
            # below REVEALS that tab) and searched the wrong document.
            return php_tab.find_replace_bar
        self._shell.reveal_raw_xml()
        return stage.find_replace_bar

    def active_bookmark_editor(self):
        """The editor the Bookmarks menu/shortcuts act on: whichever editor
        tab is active (§8). Every editor carries the same bookmark API from
        the shared gutter base (`ui/editor_gutter.py`), so this dispatch is
        the only thing needed to make the menu follow focus -- it mirrors
        `active_find_bar`'s per-tab routing.

        Unlike `active_find_bar` this deliberately does NOT reveal the Raw
        XML tab as a side effect: toggling a bookmark must never yank the
        user to a different tab. Any non-editor tab falls back to the Raw XML
        editor, where bookmarks lived before the DDL Explorer existed.
        """
        stage = self._shell.stage
        if stage.currentIndex() == stage.xsd_tab_index:
            return stage.xsd_editor
        if stage.currentIndex() == stage.ddl_tab_index:
            return stage.ddl_editor_panel.editor
        panel = stage.active_ddl_object_panel()
        if panel is not None:
            return panel.editor
        php_tab = stage.active_php_file_tab()
        if php_tab is not None:
            # §21: its `CodeEditor` carries the same gutter bookmark API (§8),
            # so the Bookmarks menu follows a PHP tab like any other editor.
            return php_tab.editor
        return stage.xml_editor

    # -- the Edit-menu gestures (act on the active bar) -----------------------

    def show_find(self) -> None:
        self.active_find_bar().show_find()

    def show_replace(self) -> None:
        self.active_find_bar().show_replace()

    def find_next(self) -> None:
        self.active_find_bar().find_next()

    def find_all_in_active_bar(self) -> None:
        """Edit ▸ Find All: ask the active tab's bar to run its find-all, which
        comes back round through :meth:`find_all`. Named apart from that method
        on purpose -- see the module docstring."""
        self.active_find_bar().find_all()

    def replace_all(self) -> None:
        self.active_find_bar().replace_all()

    def on_find_selected_text(self, text: str) -> None:
        """Editor right-click "Find": reveal the Raw XML tab, prefill the find
        bar with the selection, and run Find Next -- the same path Edit ->
        Find/Find Next drives."""
        self._shell.reveal_raw_xml()
        bar = self._shell.stage.find_replace_bar
        bar.show_find()
        bar.set_find_text(text)
        bar.find_next()

    # -- the streaming Find All ----------------------------------------------

    def find_all(self, term: str, target: str = "raw") -> None:
        """Start a streaming Find All: results are appended to the Audit panel
        a batch at a time on a 0ms QTimer, yielding to the event loop between
        batches so the UI stays responsive and Stop takes effect promptly.

        `target` selects which editor tab the search runs over -- "raw" (the
        Raw XML tab, the default) or "xsd" (the Edit XSD tab) -- and is
        stashed with each result so clicking it navigates the right editor.
        """
        self._cancel_find_all_timer()
        self.clear_find_results()
        self._find_all_term = term
        self._find_all_target = target
        self._find_all_count = 0
        self._find_all_stop = False
        stage = self._shell.stage
        editor = stage.xsd_editor if target == "xsd" else stage.xml_editor
        bar = stage.xsd_find_replace_bar if target == "xsd" else stage.find_replace_bar
        text = editor.toPlainText()
        self._find_all_iter = search.iter_matches(text, term)
        bar.set_find_all_running(True)
        self._shell.status(f'Finding "{term}"…')
        self._find_all_timer = QTimer(self)
        self._find_all_timer.timeout.connect(self._find_all_step)
        self._find_all_timer.start(0)

    def _find_all_step(self) -> None:
        if self._find_all_stop:
            self._finish_find_all(stopped=True)
            return
        for _ in range(_FIND_ALL_BATCH):
            try:
                match = next(self._find_all_iter)
            except StopIteration:
                self._finish_find_all(stopped=False)
                return
            item = QListWidgetItem(f"{_FIND_RESULT_PREFIX}line {match.line}: {match.preview}")
            item.setData(Qt.ItemDataRole.UserRole, match.line)
            item.setData(Qt.ItemDataRole.UserRole + 1, self._find_all_target)
            self._shell.audit.addItem(item)
            self._find_all_count += 1
        self._shell.status(
            f'Finding "{self._find_all_term}"… found {self._find_all_count}'
        )

    def _finish_find_all(self, stopped: bool) -> None:
        self._cancel_find_all_timer()
        summary = QListWidgetItem(
            f'{_FIND_RESULT_PREFIX}{self._find_all_count} match(es) for "{self._find_all_term}"'
        )
        self._shell.audit.addItem(summary)  # no line data -> clicking is a no-op
        stage = self._shell.stage
        bar = (
            stage.xsd_find_replace_bar
            if self._find_all_target == "xsd"
            else stage.find_replace_bar
        )
        bar.set_find_all_running(False)
        if stopped:
            self._shell.status(
                f"Find All stopped — found {self._find_all_count} item(s)"
            )
        else:
            self._shell.status(f"Found {self._find_all_count} item(s)")

    def stop_find_all(self) -> None:
        """Request that an in-flight streaming Find All stop; the next
        _find_all_step tick finishes the run, keeping results found so far."""
        self._find_all_stop = True

    def _cancel_find_all_timer(self) -> None:
        if self._find_all_timer is not None:
            self._find_all_timer.stop()
            # deleteLater the C++ QTimer so repeated Find All runs don't
            # accumulate stopped timer children on this controller.
            self._find_all_timer.deleteLater()
            self._find_all_timer = None
        # Drop the (possibly large) generator so we don't hold its closure
        # over the snapshotted document text between runs.
        self._find_all_iter = None

    # -- Audit cleanups + Tier-2 validation ----------------------------------

    def clear_find_results(self) -> None:
        """Remove only prior [Find]-prefixed entries, leaving schema-learning
        / validation entries intact. Iterates from the bottom so removals
        don't shift not-yet-visited indices."""
        audit = self._shell.audit
        for row in range(audit.count() - 1, -1, -1):
            item = audit.item(row)
            if item.text().startswith(_FIND_RESULT_PREFIX):
                audit.takeItem(row)

    def clear_validation_results(self) -> None:
        """Remove only prior [Validate]-prefixed audit entries, leaving find /
        schema-learning entries intact. Iterates from the bottom so removals
        don't shift not-yet-visited indices."""
        audit = self._shell.audit
        for row in range(audit.count() - 1, -1, -1):
            item = audit.item(row)
            if item.text().startswith(_VALIDATION_PREFIX):
                audit.takeItem(row)

    def validate_project(self) -> None:
        """Run the Tier-2 structural-sanity checks and report into the Audit
        panel; each issue is click-to-navigable via its source line."""
        project = self._project()
        if project is None:
            self._shell.status("Open a project to validate.", 5000)
            return
        project_path = self._project_path()
        name = Path(project_path).name if project_path else "project"
        self.clear_validation_results()
        audit = self._shell.audit
        with busy_status(_StatusBarProxy(self._shell.status), f"Validating {name}…"):
            issues = tier2.validate_project(project)
            n_err = 0
            n_warn = 0
            for issue in issues:
                if issue.severity == "error":
                    n_err += 1
                else:
                    n_warn += 1
                if issue.line is None:
                    text = f"{_VALIDATION_PREFIX}{issue.severity.upper()}: {issue.message}"
                else:
                    text = (
                        f"{_VALIDATION_PREFIX}{issue.severity.upper()} "
                        f"line {issue.line}: {issue.message}"
                    )
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, issue.line)
                audit.addItem(item)
        if issues:
            self._shell.status(
                f"Validation: {n_err} error(s), {n_warn} warning(s)", 5000
            )
        else:
            self._shell.status("Validation passed — no issues.", 5000)
