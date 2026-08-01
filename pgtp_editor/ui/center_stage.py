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
from pgtp_editor.ui.diff_merge_panel import DiffMergePanel
from pgtp_editor.ui.find_replace_bar import FindReplaceBar
from pgtp_editor.ui.manual_panel import ManualPanel
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

    def __init__(self, parent=None):
        super().__init__(parent)
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
