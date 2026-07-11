from PySide6.QtWidgets import QTabWidget, QWidget


class CenterStage(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.properties_tab_index = self.addTab(QWidget(), "Properties")
        self.diff_merge_tab_index = self.addTab(QWidget(), "Diff / Merge")
        self.caption_management_tab_index = self.addTab(QWidget(), "Caption Management")
        self.raw_xml_tab_index = self.addTab(QWidget(), "Raw XML")
        self.setTabVisible(self.raw_xml_tab_index, False)

    def set_properties_tab_visible(self, visible):
        self.setTabVisible(self.properties_tab_index, visible)

    def set_raw_xml_tab_visible(self, visible):
        self.setTabVisible(self.raw_xml_tab_index, visible)
