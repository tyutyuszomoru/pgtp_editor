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

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabBar, QTabWidget, QVBoxLayout, QWidget

from pgtp_editor.ui.caption_management_panel import CaptionManagementPanel
from pgtp_editor.ui.ddl_editor_panel import EditorPanel
from pgtp_editor.ui.ddl_object_editor import DdlObjectEditorPanel
from pgtp_editor.ui.diff_merge_panel import DiffMergePanel
from pgtp_editor.ui.find_replace_bar import FindReplaceBar, install_focus_shortcuts
from pgtp_editor.ui.manual_panel import ManualPanel
from pgtp_editor.ui.php_file_tab import PhpFileTab, php_tab_key
from pgtp_editor.ui.sql_console_panel import CONSOLE_TAB_KEY, SqlConsolePanel
from pgtp_editor.ui.xml_editor import XmlEditor

#: First element of every generated-fragment draft tab's key (FQ-006). Draft
#: keys are 4-tuples `(DRAFT_TAB_KEY_KIND, kind, table_name, serial)`, which
#: cannot collide with anything else filed in `CenterStage._ddl_object_tabs`:
#: a `DdlObjectRef.key` is a 5-tuple, a checked-out object's override key is a
#: `str` (its resolved path), and the Sandbox SQL Console's key is a 1-tuple.
#: The monotonic `serial` additionally makes every draft distinct from every
#: other draft, because drafts are explicitly MULTI-instance (unlike the
#: console): creating a Page from table A and then another Page from table A
#: must leave two tabs open, never silently overwrite the first.
DRAFT_TAB_KEY_KIND = "draft-fragment"


class DraftFragmentTab(QWidget):
    """A generated-fragment **draft** (FQ-006): the destination for "create
    page / detail / lookup from a DB table".

    Nothing here saves anywhere and nothing pastes the draft back into the
    project — the user reviews/edits the fragment and copies it out (or never
    does). That is why it is a plain `XmlEditor` + `FindReplaceBar` (syntax
    highlighting and find/replace for free, no schema model required) with no
    save path, no `is_dirty()` and no unsaved-changes concept at all.
    """

    def __init__(self, kind, table_name, text, parent=None):
        super().__init__(parent)
        #: "page" / "detail" / "lookup" -- what was generated.
        self.kind = kind
        #: The source DB table/view the fragment was generated from.
        self.table_name = table_name
        self.editor = XmlEditor()
        self.editor.setPlainText(text)
        self.find_replace_bar = FindReplaceBar(self.editor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.editor)
        layout.addWidget(self.find_replace_bar)
        # FQ-016: the bar is permanently visible; Ctrl+F / Ctrl+R focus it,
        # scoped to this draft tab and its children.
        self._focus_find_shortcut, self._focus_replace_shortcut = (
            install_focus_shortcuts(self, self.find_replace_bar)
        )

    def toPlainText(self):
        """The draft's current text (the user may have edited it)."""
        return self.editor.toPlainText()

    def tab_title(self):
        """e.g. ``"New Page: customers"`` -- names both kind and source table
        (FQ-006), so several drafts open at once stay tellable apart."""
        return f"New {self.kind.capitalize()}: {self.table_name}"

    def tab_tooltip(self):
        return (
            f"Generated {self.kind} draft for '{self.table_name}' — edit it and "
            "copy it into your project. Nothing here is saved anywhere."
        )


#: The Raw XML tab's title when the editor is editable. Used at the `addTab`
#: site AND by the restore path (BUG-037), so the two can never drift into
#: showing different text for the same state.
RAW_XML_TAB_TITLE = "Raw XML"

#: BUG-037's suffix for Caption Mode. Phrased as the *reason* rather than a
#: bare "read only" because Raw XML can be locked by more than one mode, and a
#: user who cannot type needs to know which one to leave.
RAW_XML_READ_ONLY_CAPTION_MODE = "read only in caption mode"


class CenterStage(QTabWidget):
    # Emitted when the Manual tab is revealed (True) or hidden (False), so the
    # main window can keep the left-dock Contents tab in lockstep with it.
    manual_visibility_changed = Signal(bool)

    # Emitted when the Edit XSD tab's ✕ is clicked. Closing must go through
    # MainWindow's unsaved-changes prompt first (mirrors mode-switching and
    # app-close), so this signals intent rather than hiding the tab directly.
    xsd_close_requested = Signal()

    # Emitted when the DDL Explorer tab is revealed (True) or hidden (False),
    # so the Database-menu toggle stays in lockstep (same pattern as
    # manual_visibility_changed; see BUG-007 for why one-way wiring is not
    # enough). The tab is read-only (spec §18.1), so its ✕ hides directly —
    # no dirty prompt, unlike Edit XSD.
    ddl_explorer_visibility_changed = Signal(bool)

    # Emitted when a DDL object editor tab's ✕ is clicked (spec §18.5).
    # Carries the tab's `DdlObjectRef.key`. Closing an editable, per-object
    # tab must go through MainWindow's unsaved-changes prompt first, exactly
    # like Edit XSD -- so this signals intent rather than closing directly.
    ddl_object_close_requested = Signal(tuple)

    # Emitted when a custom-PHP file tab's ✕ is clicked (spec §21). Carries
    # the tab's key (its resolved absolute path, or a minted "untitled:N").
    # Same reason as the two signals above: an editable tab's close must go
    # through MainWindow's unsaved-changes prompt first.
    php_file_close_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Dynamic per-object tabs (spec §18.5): always appended AFTER the
        # fixed set above, so the stored fixed *_tab_index constants never
        # shift and every existing index comparison in this class and in
        # MainWindow stays correct. Keyed on the object's stable identity
        # (`DdlObjectRef.key`), never on a remembered index -- close/reorder
        # must not be able to make a lookup stale.
        #
        # The Sandbox SQL Console (§18.5 D4) is filed in THIS SAME map under
        # `CONSOLE_TAB_KEY == ("sandbox-sql",)`, exactly as the spec asks
        # ("the same key->widget map the per-object tabs use"). That cannot
        # collide: a `DdlObjectRef.key` is always a 5-tuple
        # `(kind, schema, name, table, arg_types)`, and a checked-out object's
        # override key is a `str` (its resolved path) -- while the console's
        # key is a 1-tuple. Two guards keep the sharing safe:
        # `_on_tab_close_requested` intercepts the console's X before the
        # object loop, and `ddl_object_panels()` filters by type so the
        # console is never handed to a caller expecting `.ref`/`.is_dirty()`.
        #
        # Generated-fragment DRAFT tabs (FQ-006) are filed in the same map for
        # the same reason and behind the same two guards, under 4-tuple keys
        # `(DRAFT_TAB_KEY_KIND, kind, table, serial)` -- see that constant.
        self._ddl_object_tabs: dict[tuple, DdlObjectEditorPanel] = {}
        # Monotonic serial for draft keys: drafts are multi-instance, so each
        # one needs an identity of its own (never a reused/shared scratch tab).
        self._draft_counter = 0
        # Dynamic custom-PHP file tabs (spec §21), appended after the fixed
        # set for exactly the same reason, and keyed on the file's resolved
        # absolute path -- opening the same file twice must focus the tab that
        # is already open, never add a second one.
        self._php_file_tabs: dict[str, PhpFileTab] = {}
        self._untitled_php_counter = 0
        self.diff_merge_panel = DiffMergePanel()
        self.diff_merge_tab_index = self.addTab(self.diff_merge_panel, "Diff / Merge")

        self.caption_management_panel = CaptionManagementPanel()
        self.caption_management_tab_index = self.addTab(
            self.caption_management_panel, "Caption Management"
        )

        self.xml_editor = XmlEditor()
        self.find_replace_bar = FindReplaceBar(self.xml_editor)
        self.raw_xml_tab = QWidget()
        raw_layout = QVBoxLayout(self.raw_xml_tab)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.setSpacing(0)
        raw_layout.addWidget(self.xml_editor)
        raw_layout.addWidget(self.find_replace_bar)
        # FQ-016: Ctrl+F / Ctrl+R focus the permanently visible bar. Installed
        # on the TAB CONTAINER (which owns both the editor and the bar), not on
        # the window -- see `install_focus_shortcuts` for why window-level would
        # collide with the caption panel's own pair.
        self._raw_focus_shortcuts = install_focus_shortcuts(
            self.raw_xml_tab, self.find_replace_bar
        )
        self.raw_xml_tab_index = self.addTab(self.raw_xml_tab, RAW_XML_TAB_TITLE)

        # Edit XSD tab (spec §11): a second, fully-featured editor for the
        # hand-curated schema. Hidden until Schema ▸ Edit XSD reveals it.
        self.xsd_editor = XmlEditor()
        self.xsd_find_replace_bar = FindReplaceBar(self.xsd_editor)
        self.xsd_tab = QWidget()
        xsd_layout = QVBoxLayout(self.xsd_tab)
        xsd_layout.setContentsMargins(0, 0, 0, 0)
        xsd_layout.setSpacing(0)
        xsd_layout.addWidget(self.xsd_editor)
        xsd_layout.addWidget(self.xsd_find_replace_bar)
        self._xsd_focus_shortcuts = install_focus_shortcuts(
            self.xsd_tab, self.xsd_find_replace_bar
        )
        self.xsd_tab_index = self.addTab(self.xsd_tab, "Edit XSD")

        # DDL Explorer tab (spec §18.1): the one synthesized routine/trigger
        # buffer, read-only. Hidden until Database ▸ DDL Explorer reveals it.
        self.ddl_editor_panel = EditorPanel()
        self.ddl_tab_index = self.addTab(self.ddl_editor_panel, "DDL Explorer")

        self.manual_panel = ManualPanel()
        self.manual_tab_index = self.addTab(self.manual_panel, "Manual")

        # New default (spec §6.1): Raw XML is the working tab; Diff/Merge and
        # Caption Management are revealed only when their entry points run.
        self.setTabVisible(self.diff_merge_tab_index, False)
        self.setTabVisible(self.caption_management_tab_index, False)
        self.setTabVisible(self.raw_xml_tab_index, True)
        self.setTabVisible(self.xsd_tab_index, False)
        self.setTabVisible(self.ddl_tab_index, False)
        self.setTabVisible(self.manual_tab_index, False)
        self.setCurrentIndex(self.raw_xml_tab_index)

        # The Manual and Edit XSD tabs are closable (a ✕ that hides them
        # again). The other tabs (Diff/Merge, Caption Management, Raw XML)
        # are structural -- they're toggled by their own entry points, not by
        # this tab-close mechanism -- so strip their close buttons on both
        # sides.
        self.setTabsClosable(True)
        bar = self.tabBar()
        _closable = (self.manual_tab_index, self.xsd_tab_index, self.ddl_tab_index)
        for index in range(self.count()):
            if index not in _closable:
                bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, None)
                bar.setTabButton(index, QTabBar.ButtonPosition.LeftSide, None)
        self.tabCloseRequested.connect(self._on_tab_close_requested)

    def _on_tab_close_requested(self, index):
        if index == self.manual_tab_index:
            self.hide_manual()
        elif index == self.xsd_tab_index:
            self.xsd_close_requested.emit()
        elif index == self.ddl_tab_index:
            # Read-only tab: nothing to prompt for, hide directly (unlike
            # Edit XSD, which routes through MainWindow's dirty check).
            self.hide_ddl_explorer()
        else:
            # Falls through to a dynamic tab -- a DDL object editor (§18.5) or
            # a custom-PHP file (§21). These are never at a fixed index, so
            # the only way to identify one is a map lookup by widget, not by
            # index.
            widget = self.widget(index)
            if widget is self._ddl_object_tabs.get(CONSOLE_TAB_KEY):
                # The Sandbox SQL Console (§18.5 D4) shares the object-tab map
                # but is a scratch surface: it holds no document, has no save
                # path and no dirty concept, so it closes directly here (like
                # the read-only DDL Explorer's X) instead of routing through
                # MainWindow's unsaved-changes prompt, which would need a save
                # gesture that does not exist. Must stay AHEAD of the loop
                # below: emitting `ddl_object_close_requested(("sandbox-sql",))`
                # would land in MainWindow's handler and call `is_dirty()` on
                # the console -- an AttributeError that crashes the app.
                self.close_sandbox_sql_tab()
                return
            if isinstance(widget, DraftFragmentTab):
                # A generated-fragment draft (FQ-006) shares the object-tab map
                # too, and closes directly with NO dirty-check prompt (the
                # Manual tab's precedent, not Edit XSD's): the draft was never
                # saved anywhere and the real source of truth -- the DB table
                # -- is untouched by closing it. Must stay AHEAD of the loop
                # below for the same crash reason as the console: emitting
                # `ddl_object_close_requested` for a draft would reach
                # MainWindow's handler and call `is_dirty()` on a widget that
                # has no such method -- an AttributeError.
                key = self.draft_fragment_tab_key(widget)
                if key is not None:
                    self.close_draft_fragment_tab(key)
                return
            for key, panel in self._ddl_object_tabs.items():
                if panel is widget:
                    self.ddl_object_close_requested.emit(key)
                    return
            for key, tab in self._php_file_tabs.items():
                if tab is widget:
                    self.php_file_close_requested.emit(key)
                    return

    def set_raw_xml_tab_visible(self, visible):
        self.setTabVisible(self.raw_xml_tab_index, visible)

    def show_edit_xsd(self):
        self.setTabVisible(self.xsd_tab_index, True)
        self.setCurrentIndex(self.xsd_tab_index)

    def show_manual(self):
        self.setTabVisible(self.manual_tab_index, True)
        self.setCurrentIndex(self.manual_tab_index)
        self.manual_visibility_changed.emit(True)

    def hide_manual(self):
        """Hide the Manual tab and return to Raw XML (the ✕ close action)."""
        self.setTabVisible(self.manual_tab_index, False)
        if self.currentIndex() == self.manual_tab_index:
            self.setCurrentIndex(self.raw_xml_tab_index)
        self.manual_visibility_changed.emit(False)

    def hide_edit_xsd(self):
        """Hide the Edit XSD tab and return to Raw XML (the ✕ close action),
        mirroring `hide_manual`. Called only after MainWindow has resolved any
        unsaved-changes prompt -- never directly from `_on_tab_close_requested`."""
        self.setTabVisible(self.xsd_tab_index, False)
        if self.currentIndex() == self.xsd_tab_index:
            self.setCurrentIndex(self.raw_xml_tab_index)

    def show_ddl_explorer(self):
        self.setTabVisible(self.ddl_tab_index, True)
        self.setCurrentIndex(self.ddl_tab_index)
        self.ddl_explorer_visibility_changed.emit(True)

    def hide_ddl_explorer(self):
        """Hide the DDL Explorer tab and return to Raw XML (the ✕ close
        action), mirroring `hide_manual`."""
        self.setTabVisible(self.ddl_tab_index, False)
        if self.currentIndex() == self.ddl_tab_index:
            self.setCurrentIndex(self.raw_xml_tab_index)
        self.ddl_explorer_visibility_changed.emit(False)

    def _set_raw_xml_read_only(self, reason: str | None) -> None:
        """Make Raw XML read-only *for a named reason*, or editable again.

        BUG-037: the read-only flag and the tab title are two views of ONE
        fact, and before this they were set in different places -- the flag
        here, the title never. A user in Caption Mode saw an editor that
        silently refused every keystroke with nothing on the tab to say why
        (the `_mode_label` cue is at the far bottom of the window, not on the
        tab they are looking at). Both now move together, through here, so
        they cannot drift.

        `reason` is the suffix shown in parentheses on the tab, or `None` for
        "editable" -- passing the reason rather than a bare `True` is what
        lets a second read-only mode name itself on the tab instead of
        borrowing Caption Mode's wording.
        """
        self.xml_editor.setReadOnly(reason is not None)
        self.setTabText(
            self.raw_xml_tab_index,
            RAW_XML_TAB_TITLE if reason is None else f"{RAW_XML_TAB_TITLE} ({reason})",
        )

    def enter_caption_mode(self):
        """Keep Raw XML visible but read-only, and reveal + switch to Caption
        Management (Phase 1: Raw XML is no longer hidden during caption mode)."""
        self.setTabVisible(self.raw_xml_tab_index, True)
        self._set_raw_xml_read_only(RAW_XML_READ_ONLY_CAPTION_MODE)
        self.setTabVisible(self.caption_management_tab_index, True)
        self.setCurrentIndex(self.caption_management_tab_index)

    def leave_caption_mode(self):
        """Re-enable editing on Raw XML, hide Caption Management, and switch
        back to Raw XML."""
        self._set_raw_xml_read_only(None)
        self.setTabVisible(self.caption_management_tab_index, False)
        self.setTabVisible(self.raw_xml_tab_index, True)
        self.setCurrentIndex(self.raw_xml_tab_index)

    # --- Dynamic DDL object editor tabs (spec §18.5) -----------------------
    def ddl_object_tab(self, key):
        """The open `DdlObjectEditorPanel` for `key`, or None."""
        return self._ddl_object_tabs.get(key)

    def open_ddl_object_tab(self, ref, text, resolve_save_path=None, key=None):
        """Focus the existing tab for `key` (default: `ref.key`) if one is
        already open; otherwise create it, append it (always AFTER the fixed
        set), and focus that.

        `key` is overridable so a **checked-out** object (§18.2) can be keyed
        on its resolved absolute `ddl/*.sql` path instead of `ref.key` --
        re-invoking Edit on a checked-out object must focus the existing tab
        even though the same object project-less would key on identity
        alone. Never opens a second tab for the same object (spec §18.5)."""
        tab_key = ref.key if key is None else key
        existing = self._ddl_object_tabs.get(tab_key)
        if existing is not None:
            self.setCurrentWidget(existing)
            return existing

        panel = DdlObjectEditorPanel(ref, text, resolve_save_path=resolve_save_path)
        self.addTab(panel, panel.tab_title())
        self._ddl_object_tabs[tab_key] = panel
        self.setCurrentWidget(panel)
        return panel

    def close_ddl_object_tab(self, key):
        """Actually remove the tab for `key`. Called only after MainWindow has
        resolved any unsaved-changes prompt -- never directly from
        `_on_tab_close_requested`, mirroring Edit XSD's `hide_edit_xsd`."""
        panel = self._ddl_object_tabs.pop(key, None)
        if panel is None:
            return
        index = self.indexOf(panel)
        if index != -1:
            self.removeTab(index)
        panel.deleteLater()

    def update_ddl_object_tab(self, ref, key=None):
        """Refresh a DDL object tab's title/tooltip from its panel's current
        dirty state -- call after any edit that may have crossed the
        clean/dirty boundary. `key` overrides `ref.key`, mirroring
        `open_ddl_object_tab` (checked-out objects key on their path)."""
        tab_key = ref.key if key is None else key
        panel = self._ddl_object_tabs.get(tab_key)
        if panel is None:
            return
        index = self.indexOf(panel)
        if index == -1:
            return
        self.setTabText(index, panel.tab_title())
        self.setTabToolTip(index, panel.tab_tooltip())

    def active_ddl_object_panel(self):
        """The `DdlObjectEditorPanel` currently active, or None if some other
        tab has focus."""
        widget = self.currentWidget()
        if isinstance(widget, DdlObjectEditorPanel):
            return widget
        return None

    def ddl_object_panels(self):
        """Every currently open `DdlObjectEditorPanel`, in no particular
        order. Used to push a freshly (re)built `db/schema_index.py::SchemaIndex`
        (§18.6) into every already-open tab after a DDL Explorer refresh --
        `set_schema_index` on each, mirroring how a schema refresh updates
        `XmlEditor.set_schema_model` (§11).

        Type-filtered on purpose: the Sandbox SQL Console (§18.5 D4) and the
        generated-fragment draft tabs (FQ-006) live in the same map, and every
        caller of this accessor assumes a per-object panel (`.ref`,
        `.is_dirty()`). Use `sandbox_sql_tab()` / `draft_fragment_tabs()` for
        those."""
        return [
            panel
            for panel in self._ddl_object_tabs.values()
            if isinstance(panel, DdlObjectEditorPanel)
        ]

    # --- Generated-fragment draft tabs (FQ-006) ----------------------------
    def open_draft_fragment_tab(self, kind, table_name, text):
        """Open a NEW draft tab holding the serialized fragment `text`, append
        it (always AFTER the fixed set) and focus it.

        Deliberately NOT single-instance, unlike `open_sandbox_sql_tab`: every
        "create page/detail/lookup from a DB table" gesture gets its own tab
        (FQ-006), so an in-progress edit can never be clobbered by the next
        creation. Nothing is saved and nothing is spliced anywhere -- the
        caller hands over already-serialized text and the user copies it out."""
        self._draft_counter += 1
        key = (DRAFT_TAB_KEY_KIND, kind, table_name, self._draft_counter)
        tab = DraftFragmentTab(kind, table_name, text)
        index = self.addTab(tab, tab.tab_title())
        self.setTabToolTip(index, tab.tab_tooltip())
        self._ddl_object_tabs[key] = tab
        self.setCurrentWidget(tab)
        return tab

    def draft_fragment_tab_key(self, tab):
        """The map key a given `DraftFragmentTab` is filed under, or None."""
        for key, candidate in self._ddl_object_tabs.items():
            if candidate is tab:
                return key
        return None

    def draft_fragment_tabs(self):
        """Every open `DraftFragmentTab`, keyed as `close_draft_fragment_tab`
        expects. The type-safe way to reach drafts -- `ddl_object_panels()`
        filters them out on purpose."""
        return {
            key: tab
            for key, tab in self._ddl_object_tabs.items()
            if isinstance(tab, DraftFragmentTab)
        }

    def close_draft_fragment_tab(self, key):
        """Remove a draft tab. No unsaved-changes prompt, by design (FQ-006):
        a draft was never saved anywhere, so there is nothing a warning would
        protect -- mirrors `close_sandbox_sql_tab`, not `close_ddl_object_tab`."""
        tab = self._ddl_object_tabs.pop(key, None)
        if tab is None:
            return
        index = self.indexOf(tab)
        if index != -1:
            self.removeTab(index)
        tab.deleteLater()

    # --- Sandbox SQL Console tab (spec §18.5 D4) ---------------------------
    def sandbox_sql_tab(self):
        """The open `SqlConsolePanel`, or None. Single-instance by design."""
        panel = self._ddl_object_tabs.get(CONSOLE_TAB_KEY)
        return panel if isinstance(panel, SqlConsolePanel) else None

    def open_sandbox_sql_tab(self, *, session_provider=None, **panel_kwargs):
        """Focus the Sandbox SQL Console if it is already open; otherwise
        create it, append it (always AFTER the fixed set) and focus that.

        Single-instance, exactly `open_ddl_object_tab`'s rule (§18.5 D4:
        "re-invoking the command focuses the existing tab rather than opening a
        second console"). `session_provider` and any further `panel_kwargs`
        (`run_query`, `run_async`) are forwarded to `SqlConsolePanel`
        untouched, so hosts and tests inject the same seams the panel already
        declares."""
        existing = self.sandbox_sql_tab()
        if existing is not None:
            self.setCurrentWidget(existing)
            return existing

        panel = SqlConsolePanel(session_provider=session_provider, **panel_kwargs)
        index = self.addTab(panel, panel.tab_title())
        self.setTabToolTip(
            index,
            "Ad-hoc SQL against this project's sandbox database only — "
            "never the target database (spec §18.5 D4)",
        )
        self._ddl_object_tabs[CONSOLE_TAB_KEY] = panel
        self.setCurrentWidget(panel)
        return panel

    def close_sandbox_sql_tab(self):
        """Remove the Sandbox SQL Console tab. No unsaved-changes prompt: the
        console is a scratch buffer with no save path (mirrors
        `hide_ddl_explorer`'s direct close, not `close_ddl_object_tab`'s
        prompt-first route)."""
        panel = self._ddl_object_tabs.pop(CONSOLE_TAB_KEY, None)
        if panel is None:
            return
        index = self.indexOf(panel)
        if index != -1:
            self.removeTab(index)
        panel.deleteLater()

    # --- Dynamic custom-PHP file tabs (spec §21) ---------------------------
    def php_file_tab(self, key):
        """The open `PhpFileTab` for `key`, or None."""
        return self._php_file_tabs.get(key)

    def open_php_file_tab(
        self,
        path=None,
        text="",
        resolve_save_path=None,
        writer=None,
        lint_service=None,
        lint_on_save: bool = False,
    ):
        """Focus the tab already open for `path` if there is one; otherwise
        create it, append it (always AFTER the fixed set), and focus that.

        `path` may be None for a text-only buffer, which gets a minted
        `"untitled:N"` key instead. Reading the file is the CALLER's job (§21:
        the tab never touches the filesystem behind the caller's back) -- the
        already-read `text` is handed in, and `resolve_save_path`/`writer` are
        the injected save seams, exactly as for `open_ddl_object_tab`.

        `lint_service`/`lint_on_save` are §22's two seams, passed straight
        through to `PhpFileTab` (a `lint/service.py::LintService` and the
        after-save toggle). Both are optional and default exactly as the tab
        defaults them, so a host that does not care about linting -- or an
        existing caller written before §22 -- opens a tab with no linting and
        costs nothing. Without these parameters a host could not physically
        inject the service into a tab it opens."""
        if path is not None:
            key = php_tab_key(path)
            existing = self._php_file_tabs.get(key)
            if existing is not None:
                self.setCurrentWidget(existing)
                return existing
        else:
            self._untitled_php_counter += 1
            key = f"untitled:{self._untitled_php_counter}"

        tab = PhpFileTab(
            path,
            text,
            resolve_save_path=resolve_save_path,
            writer=writer,
            lint_service=lint_service,
            lint_on_save=lint_on_save,
        )
        index = self.addTab(tab, tab.tab_title())
        self.setTabToolTip(index, tab.tab_tooltip())
        self._php_file_tabs[key] = tab
        self.setCurrentWidget(tab)
        return tab

    def close_php_file_tab(self, key):
        """Actually remove the PHP file tab for `key`. Called only after
        MainWindow has resolved any unsaved-changes prompt -- never directly
        from `_on_tab_close_requested`, mirroring `close_ddl_object_tab`."""
        tab = self._php_file_tabs.pop(key, None)
        if tab is None:
            return
        index = self.indexOf(tab)
        if index != -1:
            self.removeTab(index)
        tab.deleteLater()

    def update_php_file_tab(self, key):
        """Refresh a PHP file tab's title/tooltip from its current dirty state
        and path -- call after any edit that may have crossed the clean/dirty
        boundary, and after a Save As… renamed it."""
        tab = self._php_file_tabs.get(key)
        if tab is None:
            return
        index = self.indexOf(tab)
        if index == -1:
            return
        self.setTabText(index, tab.tab_title())
        self.setTabToolTip(index, tab.tab_tooltip())

    def php_file_tab_key(self, tab):
        """The map key a given `PhpFileTab` is filed under, or None. Lets a
        host that holds the widget (e.g. from `active_php_file_tab`) reach the
        key the close/update APIs take, without duplicating the key rule."""
        for key, candidate in self._php_file_tabs.items():
            if candidate is tab:
                return key
        return None

    def active_draft_fragment_tab(self):
        """The `DraftFragmentTab` currently active, or None (mirrors
        `active_php_file_tab`).

        Needed because a draft tab owns a real `XmlEditor` and a real
        `FindReplaceBar`, but is NOT a `DdlObjectEditorPanel` -- so without an
        accessor of its own, `FindValidateController`'s per-tab routing fell
        through to the Raw XML fallback and Ctrl+F searched the wrong document
        while the draft's own bar sat hidden and unreachable (FQ-006).
        """
        widget = self.currentWidget()
        if isinstance(widget, DraftFragmentTab):
            return widget
        return None

    def active_php_file_tab(self):
        """The `PhpFileTab` currently active, or None if some other tab has
        focus (mirrors `active_ddl_object_panel`)."""
        widget = self.currentWidget()
        if isinstance(widget, PhpFileTab):
            return widget
        return None

    def php_file_tabs(self):
        """Every currently open `PhpFileTab`, keyed as the close/update APIs
        expect. Used by the host's app-close flow to prompt for each dirty
        one."""
        return dict(self._php_file_tabs)
