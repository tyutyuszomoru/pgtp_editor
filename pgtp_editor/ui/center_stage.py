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
from pgtp_editor.ui.find_replace_bar import FindReplaceBar
from pgtp_editor.ui.manual_panel import ManualPanel
from pgtp_editor.ui.php_file_tab import PhpFileTab, php_tab_key
from pgtp_editor.ui.xml_editor import XmlEditor


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
        self._ddl_object_tabs: dict[tuple, DdlObjectEditorPanel] = {}
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
        self.raw_xml_tab_index = self.addTab(self.raw_xml_tab, "Raw XML")

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

    def enter_caption_mode(self):
        """Keep Raw XML visible but read-only, and reveal + switch to Caption
        Management (Phase 1: Raw XML is no longer hidden during caption mode)."""
        self.setTabVisible(self.raw_xml_tab_index, True)
        self.xml_editor.setReadOnly(True)
        self.setTabVisible(self.caption_management_tab_index, True)
        self.setCurrentIndex(self.caption_management_tab_index)

    def leave_caption_mode(self):
        """Re-enable editing on Raw XML, hide Caption Management, and switch
        back to Raw XML."""
        self.xml_editor.setReadOnly(False)
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
        `XmlEditor.set_schema_model` (§11)."""
        return list(self._ddl_object_tabs.values())

    # --- Dynamic custom-PHP file tabs (spec §21) ---------------------------
    def php_file_tab(self, key):
        """The open `PhpFileTab` for `key`, or None."""
        return self._php_file_tabs.get(key)

    def open_php_file_tab(self, path=None, text="", resolve_save_path=None, writer=None):
        """Focus the tab already open for `path` if there is one; otherwise
        create it, append it (always AFTER the fixed set), and focus that.

        `path` may be None for a text-only buffer, which gets a minted
        `"untitled:N"` key instead. Reading the file is the CALLER's job (§21:
        the tab never touches the filesystem behind the caller's back) -- the
        already-read `text` is handed in, and `resolve_save_path`/`writer` are
        the injected save seams, exactly as for `open_ddl_object_tab`."""
        if path is not None:
            key = php_tab_key(path)
            existing = self._php_file_tabs.get(key)
            if existing is not None:
                self.setCurrentWidget(existing)
                return existing
        else:
            self._untitled_php_counter += 1
            key = f"untitled:{self._untitled_php_counter}"

        tab = PhpFileTab(path, text, resolve_save_path=resolve_save_path, writer=writer)
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
