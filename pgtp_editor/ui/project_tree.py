from PySide6.QtWidgets import QTreeWidget


class ProjectTreePanel(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
