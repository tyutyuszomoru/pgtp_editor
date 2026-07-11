from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from pgtp_editor.model.parser import load_project
from pgtp_editor.ui._stub_action import add_stub_action
from pgtp_editor.ui.about import show_about_dialog
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

        self.properties_panel = QWidget()
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setObjectName("properties_dock")
        self.properties_dock.setWidget(self.properties_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

        self.center_stage = CenterStage()
        self.setCentralWidget(self.center_stage)

        self._current_project = None
        self._current_project_path = None

        self._build_menu_bar()

    def _not_implemented(self, label):
        self.statusBar().showMessage(f"Not yet implemented: {label}", 5000)

    def _open_project(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, "Open PGTP Project", "", "PGTP files (*.pgtp)"
        )
        if not path:
            return
        self.open_project_file(path)

    def open_project_file(self, path):
        """Load and display the .pgtp project at `path`.

        Split out from `_open_project` so tests can drive the load without
        going through the QFileDialog. On parse failure, shows a clear
        error dialog and leaves the currently-displayed tree (and the
        currently-tracked project) untouched (never a crash, never a
        silently-emptied tree or a silently-forgotten project).
        """
        try:
            project = load_project(path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Failed to Open Project",
                f"Could not open '{path}':\n\n{exc}",
            )
            return
        self.project_tree.populate_from_project(project)
        self._current_project = project
        self._current_project_path = path
        self.statusBar().showMessage(f"Opened: {path}", 5000)

    def _build_menu_bar(self):
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_diff_merge_menu()
        self._build_tools_menu()
        self._build_generation_menu()
        self._build_help_menu()

    def _build_file_menu(self):
        menu = self.menuBar().addMenu("File")
        self._add_stub_action(menu, "New Project")
        open_action = menu.addAction("Open...")
        open_action.triggered.connect(self._open_project)
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
        properties_action.toggled.connect(self.properties_dock.setVisible)

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

    def _build_diff_merge_menu(self):
        menu = self.menuBar().addMenu("Diff / Merge")
        self._add_stub_action(menu, "Compare / Merge Two Files...")
        menu.addSeparator()
        self._add_stub_action(menu, "Next Difference")
        self._add_stub_action(menu, "Prev Difference")
        self._add_stub_action(menu, "Apply Changes to Target")

    def _build_tools_menu(self):
        menu = self.menuBar().addMenu("Tools")
        self._add_stub_action(menu, "Create Client (Readonly) Page...")
        self._add_stub_action(menu, "Move/Copy Detail...")
        menu.addSeparator()
        self._add_stub_action(menu, "Manage Captions...")
        menu.addSeparator()
        self._add_stub_action(menu, "Find Reused Tables...")
        menu.addSeparator()
        self._add_stub_action(menu, "Validate Project")

    def _build_generation_menu(self):
        menu = self.menuBar().addMenu("Generation")
        self._add_stub_action(menu, "Locate PHP Generator Executable...")
        menu.addSeparator()
        self._add_stub_action(menu, "Generate PHP...")
        menu.addSeparator()
        self._add_stub_action(menu, "Open Output Folder")

    def _build_help_menu(self):
        menu = self.menuBar().addMenu("Help")
        self._add_stub_action(menu, "Documentation")
        about_action = menu.addAction("About")
        about_action.triggered.connect(lambda: show_about_dialog(self))
