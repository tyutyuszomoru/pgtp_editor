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
        self._build_edit_menu()
        self._build_view_menu()

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

    def _build_edit_menu(self):
        menu = self.menuBar().addMenu("Edit")
        self._add_stub_action(menu, "Undo")
        self._add_stub_action(menu, "Redo")
        menu.addSeparator()
        self._add_stub_action(menu, "Cut")
        self._add_stub_action(menu, "Copy")
        self._add_stub_action(menu, "Paste")
        self._add_stub_action(menu, "Delete")
        menu.addSeparator()
        self._add_stub_action(menu, "Find...")
        find_replace = self._add_stub_action(menu, "Find & Replace...")
        find_replace.setShortcut("Ctrl+H")
        menu.addSeparator()
        self._add_stub_action(menu, "Preferences...")

    def _build_view_menu(self):
        menu = self.menuBar().addMenu("View")

        tree_action = menu.addAction("Project Tree")
        tree_action.setCheckable(True)
        tree_action.setChecked(True)
        tree_action.toggled.connect(self.tree_dock.setVisible)

        properties_action = menu.addAction("Properties Panel")
        properties_action.setCheckable(True)
        properties_action.setChecked(True)
        properties_action.toggled.connect(self.center_stage.set_properties_tab_visible)

        audit_action = menu.addAction("Audit/Problems Panel")
        audit_action.setCheckable(True)
        audit_action.setChecked(True)
        audit_action.toggled.connect(self.audit_dock.setVisible)

        raw_xml_action = menu.addAction("Raw XML Panel")
        raw_xml_action.setCheckable(True)
        raw_xml_action.setChecked(False)
        raw_xml_action.toggled.connect(self.center_stage.set_raw_xml_tab_visible)

        menu.addSeparator()
        self._add_stub_action(menu, "Expand All")
        self._add_stub_action(menu, "Collapse All")

    def _add_stub_action(self, menu, label):
        return add_stub_action(menu, label, self._not_implemented)
