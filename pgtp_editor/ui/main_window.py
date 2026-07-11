from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QListWidget, QMainWindow

from pgtp_editor.ui._stub_action import add_stub_action
from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.project_tree import ProjectTreePanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PGTP Editor")
        self.resize(1400, 900)

        self.project_tree = ProjectTreePanel(on_stub_action=self._not_implemented)
        self.tree_dock = QDockWidget("Project Tree", self)
        self.tree_dock.setObjectName("tree_dock")
        self.tree_dock.setWidget(self.project_tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tree_dock)

        self.audit_panel = QListWidget()
        self.audit_dock = QDockWidget("Audit / Problems", self)
        self.audit_dock.setObjectName("audit_dock")
        self.audit_dock.setWidget(self.audit_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.audit_dock)

        self.center_stage = CenterStage()
        self.setCentralWidget(self.center_stage)

        self._build_menu_bar()

    def _not_implemented(self, label):
        self.statusBar().showMessage(f"Not yet implemented: {label}", 5000)

    def _build_menu_bar(self):
        self._build_file_menu()

    def _build_file_menu(self):
        menu = self.menuBar().addMenu("File")
        self._add_stub_action(menu, "New Project")
        self._add_stub_action(menu, "Open...")
        menu.addMenu("Open Recent")
        self._add_stub_action(menu, "Save")
        self._add_stub_action(menu, "Save As...")
        self._add_stub_action(menu, "Close")
        menu.addSeparator()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

    def _add_stub_action(self, menu, label):
        return add_stub_action(menu, label, self._not_implemented)
