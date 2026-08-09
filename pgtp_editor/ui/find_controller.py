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
* the **Navigation menu** (titled `Bookmarks` before FQ-021) — a menu owned
  outright by one collaborator moves with it, so this lane builds it
  (:meth:`build_navigation_menu`), gates its **bookmark group** during
  Caption Mode (:meth:`set_bookmarks_enabled`, §8/§13) and shows/hides its three
  Compare/Merge-**mode** members (:meth:`set_diff_mode_members_visible`,
  FQ-021) — including
  **List All Bookmarks** (:meth:`list_all_bookmarks`, FQ-014), which writes the
  active editor's bookmarks into the Audit panel as ``[Bookmark]`` rows and, being
  a snapshot, sweeps them again when a document load wipes the bookmark set it
  described (:meth:`_on_editor_bookmarks_changed`);
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
The second entry point, ``find_all_in_active_bar`` (*Edit ▸ Find All*), is
**gone** with the Edit menu (FQ-016): Find All is started from the permanently
visible bar's own button, which reaches :meth:`find_all` directly. The only
"act on the active bar" method left here is :meth:`find_next`, F3's host.

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

from pgtp_editor.lint.findings import LINT_AUDIT_TARGET
from pgtp_editor.ui import search
from pgtp_editor.ui.busy import busy_status
from pgtp_editor.ui.center_stage import DDL_EXPLORER_SANDBOX
from pgtp_editor.ui.editor_gutter import BOOKMARKS_RESET, add_bookmark_observer
from pgtp_editor.ui.ui_shell import UiShell
from pgtp_editor.validation import tier2

#: Audit prefix every streaming Find-All row carries, so `clear_find_results`
#: can drop this run's rows without touching [Validate]/[Schema]/[PHP] ones.
_FIND_RESULT_PREFIX = "[Find] "

#: Audit prefix every Tier-2 validation row carries, for the same reason.
_VALIDATION_PREFIX = "[Validate] "

#: Audit prefix every `List All Bookmarks` row carries (FQ-014, §7's prefix
#: table). A CONSTANT, never the literal typed at the call sites -- the
#: `[Project]` prefix was typed inline in ten places and that is recorded as a
#: mistake not to repeat. Deliberately NOT a reuse of `[Find]`: the two would
#: clear each other, and `[Find]`'s `"raw"|"xsd"` target vocabulary cannot carry
#: a DDL-object or PHP-tab payload under one prefix.
_BOOKMARK_PREFIX = "[Bookmark] "

#: Sentinel for "the active editor has NO route in `_on_audit_item_clicked`"
#: (the read-only DDL Explorer buffer, an FQ-006 draft tab). Its rows are emitted
#: roles-less and inert: the router's fallback branch navigates **Raw XML**, so a
#: row carrying a line would jump to the wrong document -- the exact failure the
#: `[Check]` branch's comment and §7's unmapped-line rule forbid.
_NO_AUDIT_ROUTE = object()

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
    """Owns find/replace routing, the Navigation menu, the streaming Find-All run
    and Tier-2 project validation."""

    def __init__(
        self,
        shell: UiShell,
        parent: QObject | None = None,
        *,
        project: Callable[[], object | None],
        project_path: Callable[[], str | None],
        show_audit_dock: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self._shell = shell
        #: Document-state providers -- see the module docstring.
        self._project = project
        self._project_path = project_path
        #: `MainWindow._show_audit_dock`, injected exactly as `CoherenceController`
        #: receives it (the bottom dock is host furniture, and `UiShell` has no
        #: field for it). `List All Bookmarks` is a silent no-op without it
        #: whenever the dock is hidden, so it is called on every listing.
        #: Optional so a headless test may build the lane without one.
        self._show_audit_dock = show_audit_dock

        # FQ-014: the `[Bookmark]` rows are a SNAPSHOT, so they must not outlive
        # the bookmarks they describe -- every `setPlainText` wipes an editor's
        # bookmark set (§8's fold-state lifecycle). The gutter mixin publishes
        # that event without knowing this panel exists (`ui/editor_gutter.py`);
        # the lane that owns the rows subscribes. Held weakly there, so this
        # controller's lifetime is unaffected.
        add_bookmark_observer(self._on_editor_bookmarks_changed)

        #: The Navigation menu and its five bookmark actions, retained by
        #: `build_navigation_menu` so `set_bookmarks_enabled` can gate **the five
        #: actions individually** during Caption Mode (§8/§13) -- the menu itself
        #: is no longer disabled, see that method. None / empty until the menu is
        #: built.
        self._navigation_menu = None
        self._bookmark_actions: tuple = ()

        #: FQ-021's three MODE-ONLY members of the same menu (`Next Difference`,
        #: `Previous Difference`, `Apply Changes to Target`), hidden outside
        #: Compare/Merge mode by `set_diff_mode_members_visible`. Retained
        #: separately from `_bookmark_actions` because the two groups are gated
        #: by different things and must never move together: Caption Mode gates
        #: the bookmark group only.
        self._diff_actions: tuple = ()

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
    def navigation_menu(self):
        """The Navigation ``QMenu`` (None before :meth:`build_navigation_menu`)."""
        return self._navigation_menu

    @property
    def bookmark_actions(self) -> tuple:
        """The five bookmark ``QAction``s, in menu order (empty before
        :meth:`build_navigation_menu`). The separator is not included."""
        return self._bookmark_actions

    @property
    def diff_actions(self) -> tuple:
        """FQ-021's three Compare/Merge-mode ``QAction``s, in menu order
        (``Next Difference``, ``Previous Difference``,
        ``Apply Changes to Target``); empty before
        :meth:`build_navigation_menu`."""
        return self._diff_actions

    # -- construction --------------------------------------------------------

    def build_navigation_menu(
        self,
        menu_bar,
        *,
        on_next_difference: Callable[[], None] | None = None,
        on_previous_difference: Callable[[], None] | None = None,
        on_apply_changes_to_target: Callable[[], None] | None = None,
    ) -> None:
        """Add the Navigation menu to `menu_bar`.

        Titled `Bookmarks` until FQ-021 renamed it; the five members kept their
        own labels. The rename is not free, because a command id is its whole
        menu path and the first segment is the menu title -- every member went
        from `bookmarks.*` to `navigation.*`, which would drop a pinned toolbar
        button. `toolbar_registry.RENAMED_ID_ALIASES` carries a row per member so
        it survives; that table and NOT `LEGACY_ID_ALIASES`, which
        `ICON_ID_BY_COMMAND` inverts (see its comment for what a row there
        silently breaks).

        Each action resolves the target editor at TRIGGER time via
        `active_bookmark_editor`, not at build time -- the shared gutter base
        (§8) puts the same bookmark API on the Raw XML, Edit XSD and DDL
        Explorer editors, so the menu follows whichever is active instead of
        being bound to Raw XML forever.

        The menu and its five actions are RETAINED (`_navigation_menu` /
        `_bookmark_actions`) so `set_bookmarks_enabled` can gate them together
        while Caption Mode is active (§8/§13) -- disabling only the `QMenu`
        grays out the menu-bar entry but leaves the actions' shortcuts live.

        FQ-021's third leg added THREE MORE members below a separator —
        `Next Difference` and `Previous Difference` **moved off Tools**, plus
        `Apply Changes to Target`, which FQ-020 removed from Tools leaving it
        with no menu home at all (`DiffMergeController.apply_changes_to_target`
        stayed reachable only from tests). They are Compare/Merge-**mode**
        members, `setVisible(False)` outside it (`set_diff_mode_members_visible`),
        while the five bookmark members stay always visible because they are
        per-*editor*, not per-mode — so the menu itself is never hidden.

        The three take their callbacks as arguments rather than reaching for
        `self._shell.stage.diff_merge_panel` / the host's `_diff_ui`: this lane
        owns the menu, not the Compare/Merge lane, and the host is the one place
        that already knows both. Built ONCE here and only ever shown/hidden —
        `ToolbarController._walk_menu_actions` never tests `isVisible()`, so a
        hidden action keeps its stable id and stays in Customize Toolbar's
        Available list; recreating them per mode would break that.
        """
        menu = menu_bar.addMenu("Navigation")
        self._navigation_menu = menu

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

        # FQ-014. No shortcut, matching Clear All Bookmarks: this produces a
        # report, and F2 / Shift+F2 already own stepping.
        list_action = menu.addAction("List All Bookmarks")
        list_action.triggered.connect(self.list_all_bookmarks)

        self._bookmark_actions = (
            toggle_action,
            next_action,
            prev_action,
            clear_action,
            list_action,
        )

        # FQ-021: the Compare/Merge-mode group. Separated from the bookmark
        # group above so the two never read as one list of five-plus-three.
        menu.addSeparator()
        next_diff_action = menu.addAction("Next Difference")
        prev_diff_action = menu.addAction("Previous Difference")
        # Relabelled from Tools' `Prev Difference` (settled 2026-08-08) to match
        # `Previous Bookmark` two entries up. The label IS the id, so the move
        # and the relabel are one id change:
        # `tools.prev-difference` -> `navigation.previous-difference`, carried by
        # `toolbar_registry.RENAMED_ID_ALIASES`.
        apply_action = menu.addAction("Apply Changes to Target")
        for action, callback in (
            (next_diff_action, on_next_difference),
            (prev_diff_action, on_previous_difference),
            (apply_action, on_apply_changes_to_target),
        ):
            if callback is not None:
                action.triggered.connect(lambda _checked=False, cb=callback: cb())
        self._diff_actions = (next_diff_action, prev_diff_action, apply_action)
        # Hidden until a comparison is loaded -- the app does not start in the
        # mode, and the host re-asserts this from `diff_merge_mode_changed`.
        self.set_diff_mode_members_visible(False)

    def set_diff_mode_members_visible(self, visible: bool) -> None:
        """Show/hide the three Compare/Merge-mode members (FQ-021, §26).

        Driven by `CenterStage.diff_merge_mode_changed`, i.e. by the MODE, never
        by which tab is current: the mode outlives a tab switch (the user may
        read Raw XML mid-comparison), and `leave_diff_merge_mode`'s final
        `setCurrentIndex(raw_xml)` emits no `currentChanged` at all when Raw XML
        was already current.

        VISIBILITY, not enabled-state, matching every other per-context gate on
        these bars (§7's two postures: present / absent). FQ-016 declined to hide
        `Parsing`'s members because `Validate Project` is one of the six DEFAULT
        toolbar buttons; none of these three is a default, so the governing
        precedent is FQ-015's `Select ▸ Select Parent Block` — hide the action,
        and accept that a *user-pinned* button comes and goes with the mode.
        """
        for action in self._diff_actions:
            action.setVisible(visible)

    def set_bookmarks_enabled(self, enabled: bool) -> None:
        """Enable/disable **the five bookmark actions** — the bookmark action
        group, and nothing else on the menu (§8/§13).

        Named for BOOKMARKS, not for the menu, and FQ-021's third leg is why
        that distinction became load-bearing. This used to also call
        `QMenu.setEnabled`, which was equivalent to gating the group only while
        every member of the menu WAS a bookmark action. It no longer is: the
        same menu now hosts `Next Difference`, `Previous Difference` and
        `Apply Changes to Target`, which Caption Mode has no reason to touch —
        a comparison loaded while captions are being edited is still navigable.
        So the menu itself is left enabled and the five actions are gated
        individually.

        Called by the host on entering/leaving Caption Mode, where the Raw XML
        editor is read-only. The per-ACTION disable is the half that actually
        matters and always did: disabling the `QMenu` alone grays out the
        menu-bar entry while Ctrl+F2 / F2 / Shift+F2 keep firing (Qt only drops
        a shortcut when the *action* is disabled) -- the Qt rule the deleted
        `set_find_actions_enabled` demonstrated on the Edit-menu Find…/Replace…
        pair (both gone with the Edit menu, FQ-016).
        Gutter bookmark toggling is deliberately NOT gated: bookmarks are a UI
        overlay independent of the editor's read-only state.
        """
        for action in self._bookmark_actions:
            action.setEnabled(enabled)

    # -- per-tab routing -----------------------------------------------------

    def active_find_bar(self):
        """The FindReplaceBar of the active editor tab; defaults to the Raw
        XML bar (revealing that tab) when no editor tab is active."""
        stage = self._shell.stage
        if stage.currentIndex() == stage.xsd_tab_index:
            return stage.xsd_find_replace_bar
        explorer_role = stage.ddl_explorer_role_at(stage.currentIndex())
        if explorer_role is not None:
            # The DDL Explorer buffer has its own bar (spec §18.1, per-tab
            # document routing) -- without this branch Ctrl+F on the DDL tab
            # used to bounce the user back to Raw XML. Asked by ROLE since
            # §18.7 (FQ-022) gave each connection its own Explorer tab, so both
            # search their own buffer rather than the target's.
            return stage.ddl_explorer_panel(explorer_role).find_replace_bar
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
        draft = stage.active_draft_fragment_tab()
        if draft is not None:
            # FQ-006: a draft tab builds its own bar over its own XmlEditor, so
            # searching it must not fall through to Raw XML. Replace is live --
            # a draft is a scratch buffer with no save path, so there is nothing
            # to protect.
            return draft.find_replace_bar
        self._shell.reveal_raw_xml()
        return stage.find_replace_bar

    def active_bookmark_editor(self):
        """The editor the Navigation menu's bookmark actions/shortcuts act on:
        whichever editor
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
        explorer_role = stage.ddl_explorer_role_at(stage.currentIndex())
        if explorer_role is not None:
            # Either Explorer tab (§18.7): bookmarks act on the buffer the user
            # is looking at, not on the target role's by default.
            return stage.ddl_explorer_panel(explorer_role).editor
        panel = stage.active_ddl_object_panel()
        if panel is not None:
            return panel.editor
        php_tab = stage.active_php_file_tab()
        if php_tab is not None:
            # §21: its `CodeEditor` carries the same gutter bookmark API (§8),
            # so the bookmark actions follow a PHP tab like any other editor.
            return php_tab.editor
        draft = stage.active_draft_fragment_tab()
        if draft is not None:
            # FQ-006: its XmlEditor carries the same gutter bookmark API (§8).
            return draft.editor
        return stage.xml_editor

    def active_selection_editor(self):
        """The editor the `Select` menu's three commands act on (FQ-015, §8).

        Resolved at TRIGGER time, exactly like `active_bookmark_editor` -- and
        by delegating to it, because the per-tab routing question ("which
        editor is the user looking at?") has ONE answer and must not fork into
        two dispatches that can drift apart.

        It exists as a separate name rather than the host calling
        `active_bookmark_editor` for a selection command because the two are
        different *contracts*: bookmarks need the shared gutter API
        (`ui/editor_gutter.py`), selection needs `selectAll` plus whatever
        structural-selection method that editor family carries
        (`XmlEditor.select_enclosing_block` / `select_parent_block` vs
        `CodeEditor.select_enclosing_brackets` -- see the host's
        `_build_select_menu`). Should a future non-gutter editor tab appear, it
        belongs in one of these and not necessarily the other.

        Note the two selection commands were, until FQ-015, hard-wired to the
        Raw XML editor at menu-BUILD time, so Ctrl+Shift+B / Ctrl+Shift+A from a
        PHP or DDL object tab edited the selection of a document the user was
        not looking at. This method is that bug's fix.
        """
        return self.active_bookmark_editor()

    # -- the one surviving window-level gesture (acts on the active bar) ------

    def find_next(self) -> None:
        """**F3** — the only Find gesture left with a window-level host (§27).

        FQ-016 dissolved the Edit menu, and with it `show_find`/`show_replace`
        (Ctrl+F/Ctrl+R are now per-tab *focus* shortcuts owned by each bar's host
        widget), `find_all_in_active_bar` and `replace_all` (Find All / Replace
        All are button-only now — Ctrl+Shift+F and Ctrl+Alt+Return are deleted).
        F3 kept its window-level shape because it must fire with the caret in the
        editor and nothing competes for the key: the host installs it as a
        menu-less `QAction` on the `Ctrl+L` Go To XSD precedent, routed here.
        """
        self.active_find_bar().find_next()

    def on_find_selected_text(self, text: str) -> None:
        """Editor right-click "Find": reveal the Raw XML tab, set the find bar's
        term from the selection, and run Find Next.

        `set_find_text` (unconditional) rather than the bar's focus path: this is
        an explicit "search for this", not a "put my cursor there"."""
        self._shell.reveal_raw_xml()
        bar = self._shell.stage.find_replace_bar
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

    # -- FQ-014: List All Bookmarks -------------------------------------------

    def list_all_bookmarks(self) -> None:
        """**Navigation ▸ List All Bookmarks** — write the ACTIVE editor's
        bookmarks into the Audit panel as clickable `[Bookmark]` rows.

        The active editor only, like every other bookmark command (all of which
        resolve one document through `active_bookmark_editor`, and none of which
        switches tabs). Rows follow Find All's grammar verbatim, carry Find All's
        two-role payload (1-based line on `UserRole`, the click router's own
        target discriminator on `UserRole+1`), and a roles-less count row closes
        the listing exactly as `_finish_find_all` does. A **snapshot**: toggling a
        bookmark afterwards does not re-sync the rows (a document load does sweep
        them -- see `_on_editor_bookmarks_changed`).
        """
        editor = self.active_bookmark_editor()
        target, label, extra = self._bookmark_audit_route(editor)
        self.clear_bookmark_results()
        audit = self._shell.audit
        document = editor.document()
        lines = editor.bookmarked_lines()

        for block_number in lines:
            # The gutter's block numbers are 0-based; every Audit consumer
            # (`navigate_to_line`, `reveal_line`) is 1-based, as are `[Find]`'s
            # rows and the gutter's own printed numbers.
            line = block_number + 1
            preview = document.findBlockByNumber(block_number).text().strip()
            body = f"line {line}: {preview}" if preview else f"line {line}"
            item = QListWidgetItem(f"{_BOOKMARK_PREFIX}{body}")
            if target is not _NO_AUDIT_ROUTE:
                item.setData(Qt.ItemDataRole.UserRole, line)
                item.setData(Qt.ItemDataRole.UserRole + 1, target)
                if extra is not None:
                    item.setData(Qt.ItemDataRole.UserRole + 2, extra)
            audit.addItem(item)

        if not lines:
            # Roles-less, so clicking it is a no-op -- and never silence: Find
            # All emits its summary even at zero, so a command that produced
            # literally nothing would read as broken.
            audit.addItem(QListWidgetItem(f"{_BOOKMARK_PREFIX}no bookmarks in {label}"))
            self._shell.status(f"No bookmarks in {label}.")
        else:
            audit.addItem(QListWidgetItem(f"{_BOOKMARK_PREFIX}{len(lines)} bookmark(s)"))
            self._shell.status(f"{len(lines)} bookmark(s) in {label}")
        if self._show_audit_dock is not None:
            # Reveal the dock (the `CoherenceController` precedent): a command
            # whose entire output is Audit rows is a silent no-op while hidden.
            self._show_audit_dock()

    def clear_bookmark_results(self) -> None:
        """Remove only prior [Bookmark]-prefixed entries, leaving find /
        validation / schema rows intact. Bottom-up, like the two sweeps below, so
        removals don't shift not-yet-visited indices."""
        audit = self._shell.audit
        for row in range(audit.count() - 1, -1, -1):
            item = audit.item(row)
            if item.text().startswith(_BOOKMARK_PREFIX):
                audit.takeItem(row)

    def _bookmark_audit_route(self, editor):
        """`(target, label, extra)` for `editor`: the `UserRole+1` discriminator
        `MainWindow._on_audit_item_clicked` already understands for it, a human
        name for the empty-case/status wording, and the `UserRole+2` value that
        route needs (only the PHP one does), or None.

        `_NO_AUDIT_ROUTE` for an editor the click router has no branch for. Its
        fallback branch navigates **Raw XML**, so a row from the read-only DDL
        Explorer buffer or a draft tab would carry the user to a different
        document than the one it describes; §7's unmapped-`[Check]`-line rule
        says such a row must not navigate at all.

        Mirrors `active_bookmark_editor`'s dispatch, keyed on editor IDENTITY
        rather than on the current tab, so the two cannot disagree about which
        editor a route belongs to.
        """
        stage = self._shell.stage
        if editor is stage.xsd_editor:
            return "xsd", "Edit XSD", None
        for role, panel in stage.ddl_explorer_panels().items():
            if editor is panel.editor:
                # A read-only DDL Explorer buffer: no route (see above). Named by
                # role since §18.7 (FQ-022), so the empty-case wording says which
                # of the two trees the rows came from.
                label = (
                    "the DDL Explorer (Sandbox)"
                    if role == DDL_EXPLORER_SANDBOX
                    else "the DDL Explorer (Quality)"
                )
                return _NO_AUDIT_ROUTE, label, None
        for panel in stage.ddl_object_panels():
            if panel.editor is editor:
                # §18.5 D3a's tuple payload: `DdlObjectRef.key`.
                return panel.ref.key, panel.ref.qualified, None
        for key, tab in stage.php_file_tabs().items():
            if tab.editor is editor:
                # §22's payload is a PAIR: the `"php"` discriminator plus the
                # tab's CenterStage key on UserRole+2, which is what
                # `_php_tabs.navigate_to` is given. Reusing "the discriminator
                # the router understands" therefore means both halves here --
                # omitting the key would make every PHP row inert.
                return LINT_AUDIT_TARGET, tab.tab_title(), key
        for tab in stage.draft_fragment_tabs().values():
            if tab.editor is editor:
                # FQ-006 draft fragment: no route (see above).
                return _NO_AUDIT_ROUTE, "the draft fragment", None
        return "raw", "Raw XML", None

    def _on_editor_bookmarks_changed(self, editor, reason: str) -> None:
        """Subscribed to `ui/editor_gutter.py`'s bookmark notifications.

        Only the RESET reason matters here: a `setPlainText` wiped that editor's
        bookmark set, so any `[Bookmark]` listing now describes bookmarks that no
        longer exist. Toggling is deliberately NOT swept -- the listing is a
        snapshot, and re-syncing on every gutter click would make it a live view
        (§8/FQ-014). The rows are cleared wholesale rather than per editor
        because only one editor's listing can be present at a time: every
        listing starts by clearing the previous one.
        """
        if reason == BOOKMARKS_RESET:
            self.clear_bookmark_results()

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
        """Open a NEW validation run.

        It still expresses itself as "remove my prior `[Validate]` rows", which
        is what it literally did while every prefix shared one panel. Since
        FQ-028 `[Validate]` rows live on the accumulating Results tab, where
        validation history is deliberately KEPT across runs, and the router
        reads this sweep as the run boundary it always meant: the rows stay and
        the next one opens under its own dated separator. Iterates from the
        bottom so removals don't shift not-yet-visited indices."""
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
