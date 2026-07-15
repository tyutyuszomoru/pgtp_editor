from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabBar, QTabWidget, QVBoxLayout, QWidget

from pgtp_editor.ui.caption_management_panel import CaptionManagementPanel
from pgtp_editor.ui.diff_merge_panel import DiffMergePanel
from pgtp_editor.ui.find_replace_bar import FindReplaceBar
from pgtp_editor.ui.manual_panel import ManualPanel
from pgtp_editor.ui.xml_editor import XmlEditor


class CenterStage(QTabWidget):
    # Emitted when the Manual tab is revealed (True) or hidden (False), so the
    # main window can keep the left-dock Contents tab in lockstep with it.
    manual_visibility_changed = Signal(bool)

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

        self.manual_panel = ManualPanel()
        self.manual_tab_index = self.addTab(self.manual_panel, "Manual")

        # New default (spec §6.1): Raw XML is the working tab; Diff/Merge and
        # Caption Management are revealed only when their entry points run.
        self.setTabVisible(self.diff_merge_tab_index, False)
        self.setTabVisible(self.caption_management_tab_index, False)
        self.setTabVisible(self.raw_xml_tab_index, True)
        self.setTabVisible(self.manual_tab_index, False)
        self.setCurrentIndex(self.raw_xml_tab_index)

        # Only the Manual tab is closable (a ✕ that hides it again). The other
        # tabs are structural, so strip their close buttons on both sides.
        self.setTabsClosable(True)
        bar = self.tabBar()
        for index in range(self.count()):
            if index != self.manual_tab_index:
                bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, None)
                bar.setTabButton(index, QTabBar.ButtonPosition.LeftSide, None)
        self.tabCloseRequested.connect(self._on_tab_close_requested)

    def _on_tab_close_requested(self, index):
        if index == self.manual_tab_index:
            self.hide_manual()

    def set_raw_xml_tab_visible(self, visible):
        self.setTabVisible(self.raw_xml_tab_index, visible)

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
