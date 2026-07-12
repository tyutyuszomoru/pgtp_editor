from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from pgtp_editor.diff.differ import compare_block, diff_project
from pgtp_editor.diff.resolve import ResolutionError, resolve_path
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

        self.project_tree = ProjectTreePanel(
            on_stub_action=self._not_implemented,
            on_compare_page=self._compare_page_with,
            on_compare_detail=self._compare_detail_with,
        )
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

    def _compare_merge_two_files(self):
        source = self._current_project
        if source is None:
            source_path, _filter = QFileDialog.getOpenFileName(
                self, "Select Source Project", "", "PGTP files (*.pgtp)"
            )
            if not source_path:
                return
            try:
                source = load_project(source_path)
            except Exception as exc:
                QMessageBox.critical(
                    self, "Failed to Open Source Project", f"Could not open '{source_path}':\n\n{exc}"
                )
                return

        target_path, _filter = QFileDialog.getOpenFileName(
            self, "Select Target Project", "", "PGTP files (*.pgtp)"
        )
        if not target_path:
            return
        try:
            target = load_project(target_path)
        except Exception as exc:
            QMessageBox.critical(
                self, "Failed to Open Target Project", f"Could not open '{target_path}':\n\n{exc}"
            )
            return

        differences = diff_project(source, target)
        self.center_stage.diff_merge_panel.show_differences(differences)
        self.center_stage.setCurrentIndex(self.center_stage.diff_merge_tab_index)

    def _compare_page_with(self, page_node):
        target_path, _filter = QFileDialog.getOpenFileName(
            self, "Select Target Project", "", "PGTP files (*.pgtp)"
        )
        if not target_path:
            return
        try:
            target = load_project(target_path)
        except Exception as exc:
            QMessageBox.critical(
                self, "Failed to Open Target Project", f"Could not open '{target_path}':\n\n{exc}"
            )
            return

        target_page = next((p for p in target.pages if p.file_name == page_node.file_name), None)
        if target_page is None:
            QMessageBox.critical(
                self,
                "Page Not Found",
                f"No Page with fileName '{page_node.file_name}' exists in '{target_path}'.",
            )
            return

        differences = compare_block(page_node, target_page, path=[page_node.file_name], node_kind="page")
        self.center_stage.diff_merge_panel.show_differences(differences)
        self.center_stage.setCurrentIndex(self.center_stage.diff_merge_tab_index)

    def _compare_detail_with(self, detail_node, source_path):
        target_path_str, _filter = QFileDialog.getOpenFileName(
            self, "Select Target Project", "", "PGTP files (*.pgtp)"
        )
        if not target_path_str:
            return
        try:
            target = load_project(target_path_str)
        except Exception as exc:
            QMessageBox.critical(
                self, "Failed to Open Target Project", f"Could not open '{target_path_str}':\n\n{exc}"
            )
            return

        result = resolve_path(target, source_path)
        if isinstance(result, ResolutionError):
            QMessageBox.critical(self, "Detail Not Found", result.message)
            return

        differences = compare_block(detail_node, result, path=source_path, node_kind="detail")
        self.center_stage.diff_merge_panel.show_differences(differences)
        self.center_stage.setCurrentIndex(self.center_stage.diff_merge_tab_index)

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

        self._raw_xml_panel_action = menu.addAction("Raw XML Panel")
        self._raw_xml_panel_action.setCheckable(True)
        self._raw_xml_panel_action.setChecked(False)
        self._raw_xml_panel_action.toggled.connect(self.center_stage.set_raw_xml_tab_visible)

        line_wrap_action = menu.addAction("Wrap Raw XML Lines")
        line_wrap_action.setCheckable(True)
        line_wrap_action.setChecked(False)
        line_wrap_action.toggled.connect(self.center_stage.xml_editor.set_line_wrap_enabled)

        menu.addSeparator()
        self._add_stub_action(menu, "Expand All")
        self._add_stub_action(menu, "Collapse All")

    def _add_stub_action(self, menu, label):
        return add_stub_action(menu, label, self._not_implemented)

    def _build_diff_merge_menu(self):
        menu = self.menuBar().addMenu("Diff / Merge")
        compare_action = menu.addAction("Compare / Merge Two Files...")
        compare_action.triggered.connect(self._compare_merge_two_files)
        menu.addSeparator()
        next_action = menu.addAction("Next Difference")
        next_action.triggered.connect(self.center_stage.diff_merge_panel.select_next_difference)
        prev_action = menu.addAction("Prev Difference")
        prev_action.triggered.connect(self.center_stage.diff_merge_panel.select_previous_difference)
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
