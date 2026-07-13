import copy
import shutil
from pathlib import Path

from lxml import etree
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from pgtp_editor.diff.apply import apply_differences
from pgtp_editor.diff.differ import compare_block, diff_project
from pgtp_editor.diff.resolve import ResolutionError, resolve_path
from pgtp_editor.model.encoding import read_pgtp_text
from pgtp_editor.model.line_index import node_at_line
from pgtp_editor.model.parser import (
    PgtpParseError,
    _build_project_model,
    load_project,
    load_project_from_text,
)
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.parser import walk_document
from pgtp_editor.schema_learning.storage import schema_model_path, schema_xsd_path
from pgtp_editor.schema_learning.xsd_gen import generate_xsd
from pgtp_editor.ui._stub_action import add_stub_action
from pgtp_editor.ui.about import show_about_dialog
from pgtp_editor.ui.annotate_schema_values_dialog import AnnotateSchemaValuesDialog
from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.project_tree import ProjectTreePanel
from pgtp_editor.ui.properties_panel import PropertiesPanel


_SCHEMA_REPORT_TEMPLATES = {
    "new_element": "[Schema] NEW ELEMENT: {path} (first seen in {source})",
    "new_attribute": "[Schema] NEW ATTRIBUTE: {path}@{attr} (first seen in {source})",
    "new_value": '[Schema] NEW ATTR VALUE: {path}@{attr} += "{value}" (from {source})',
    "enum_overflow": "[Schema] ENUM OVERFLOWED: {path}@{attr} now free-form string (from {source})",
    "now_optional": "[Schema] NOW OPTIONAL: {path}@{attr} (previously required, from {source})",
}


class MainWindow(QMainWindow):
    def __init__(self, schema_storage_dir: Path | None = None):
        super().__init__()
        self._schema_storage_dir = schema_storage_dir
        self.setWindowTitle("PGTP Editor")
        self.resize(1400, 900)

        self.project_tree = ProjectTreePanel(
            on_stub_action=self._not_implemented,
            on_compare_page=self._compare_page_with,
            on_compare_detail=self._compare_detail_with,
            on_selection_changed=self._on_tree_selection_changed,
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

        self.center_stage = CenterStage()
        self.setCentralWidget(self.center_stage)
        self.center_stage.xml_editor.line_clicked.connect(self._on_editor_line_clicked)

        self.properties_panel = PropertiesPanel(xml_editor=self.center_stage.xml_editor)
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setObjectName("properties_dock")
        self.properties_dock.setWidget(self.properties_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

        self._current_project = None
        self._current_project_path = None
        self._current_diff_target_project = None
        self._current_diff_target_path = None

        self._build_menu_bar()

    def _not_implemented(self, label):
        self.statusBar().showMessage(f"Not yet implemented: {label}", 5000)

    def _on_tree_selection_changed(self, node, kind):
        self.properties_panel.show_node(node, kind)

    def _on_editor_line_clicked(self, line: int) -> None:
        if self._current_project is None:
            return
        node = node_at_line(self._current_project, line)
        if node is None:
            return  # click above first page / uncovered region: no-op
        self.project_tree.select_node(node)  # fires tree -> Properties automatically

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
        error dialog, populates the Raw XML fallback view (see
        `_handle_parse_failure`), and leaves the currently-displayed tree
        (and the currently-tracked project) untouched (never a crash, never
        a silently-emptied tree or a silently-forgotten project).
        """
        try:
            project = load_project(path)
        except PgtpParseError as exc:
            self._handle_parse_failure(path, exc)
            return
        self.project_tree.populate_from_project(project)
        self._current_project = project
        self._current_project_path = path
        raw_text = self._read_raw_text(path)
        if raw_text is not None:
            self.center_stage.xml_editor.setPlainText(raw_text)
        self.statusBar().showMessage(f"Opened: {path}", 5000)
        self._enrich_schema_from_file(path)

    def _enrich_schema_from_file(self, path):
        try:
            model_path = schema_model_path(self._schema_storage_dir)
            xsd_path = schema_xsd_path(self._schema_storage_dir)
            model_path.parent.mkdir(parents=True, exist_ok=True)

            if model_path.exists():
                model = Model.load(model_path)
            else:
                model = Model()

            events = []
            for elem_path, attrib, child_tag_counts, has_text in walk_document(path):
                events.extend(model.merge_element(elem_path, attrib, child_tag_counts, has_text))

            model.save(model_path)
            xsd_path.write_text(generate_xsd(model), encoding="utf-8")

            self._report_schema_events(events, path)
        except Exception as exc:
            self.audit_panel.addItem(f"[Schema] Could not update schema knowledge: {exc}")

    def _report_schema_events(self, events, source_path):
        source_name = Path(source_path).name
        if len(events) > 20:
            self.audit_panel.addItem(f"[Schema] Learned {len(events)} new structural facts from {source_name}")
            return
        for event in events:
            template = _SCHEMA_REPORT_TEMPLATES[event["kind"]]
            self.audit_panel.addItem(template.format(source=source_name, **event))

    @staticmethod
    def _read_raw_text(path) -> "str | None":
        """Read the file at `path` as text, or None if it can't be read.

        Uses the same CESU-8 repair as the model parser (see
        model/encoding.py) so the raw editor shows exactly what the parser
        saw -- including files with emoji that a strict UTF-8 read would
        choke on with UnicodeDecodeError. Guards the TOCTOU race where the
        file is deleted/becomes unreadable between an earlier successful
        step and this raw re-read (OSError), and treats a genuinely
        undecodable file (UnicodeDecodeError even after repair) the same
        way rather than letting it crash the open/fallback flow.
        """
        try:
            return read_pgtp_text(path)
        except (OSError, UnicodeDecodeError):
            return None

    def _handle_parse_failure(self, path, exc: PgtpParseError) -> None:
        QMessageBox.critical(
            self,
            "Failed to Open Project",
            f"Could not open '{path}':\n\n{exc}",
        )
        raw_text = self._read_raw_text(path)
        if raw_text is None:
            # The file itself is unreadable (e.g. deleted between the
            # earlier parse attempt and this read, or a permissions error) --
            # nothing to show in the fallback view in that case; the dialog
            # above already reported the failure.
            return
        self.center_stage.xml_editor.setPlainText(raw_text)
        if exc.line is not None:
            self.center_stage.xml_editor.highlight_error_line(exc.line)
        self.center_stage.set_raw_xml_tab_visible(True)
        self._raw_xml_panel_action.setChecked(True)
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)

    def _reparse_raw_xml(self):
        text = self.center_stage.xml_editor.toPlainText()
        try:
            project = load_project_from_text(text, source_description="<editor>")
        except PgtpParseError as exc:
            self._handle_reparse_failure(exc)
            return
        # SUCCESS: rebuild tree + adopt the new model so click-sync realigns.
        self.project_tree.populate_from_project(project)
        self._current_project = project
        # Properties has no valid selection against the freshly rebuilt tree
        # (populate_from_project cleared it); show the empty state until the
        # user clicks again. show_node(None, None) is the panel's own reset.
        self.properties_panel.show_node(None, None)
        self.statusBar().showMessage("Reparsed raw XML into tree", 5000)

    def _handle_reparse_failure(self, exc: PgtpParseError) -> None:
        # Mirror the Tier-1 open-failure pattern (_handle_parse_failure), but
        # WITHOUT re-reading a file and WITHOUT touching the existing model or
        # tree: the last-good state must survive a failed reparse so the user
        # can fix the XML and try again.
        QMessageBox.critical(
            self,
            "Reparse Failed",
            f"Could not reparse the raw XML:\n\n{exc}",
        )
        if exc.line is not None:
            self.center_stage.xml_editor.highlight_error_line(exc.line)

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

        self._current_diff_target_project = target
        self._current_diff_target_path = target_path
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

        self._current_diff_target_project = target
        self._current_diff_target_path = target_path
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

        self._current_diff_target_project = target
        self._current_diff_target_path = target_path_str
        differences = compare_block(detail_node, result, path=source_path, node_kind="detail")
        self.center_stage.diff_merge_panel.show_differences(differences)
        self.center_stage.setCurrentIndex(self.center_stage.diff_merge_tab_index)

    def _apply_changes_to_target(self):
        checked = self.center_stage.diff_merge_panel.checked_differences()
        if not checked:
            QMessageBox.information(
                self, "Apply Changes to Target", "No differences are checked to apply."
            )
            return

        ambiguous = [d for d in checked if d.ambiguous]
        if ambiguous:
            details = "\n".join(
                f"- {'/'.join(d.path)} ({d.node_kind}/{d.attribute}: {d.kind})" for d in ambiguous
            )
            QMessageBox.critical(
                self,
                "Cannot Apply: Ambiguous Differences Checked",
                "The following checked differences are ambiguous (matched via "
                "positional pairing of duplicate siblings) and cannot be safely "
                "applied automatically. Uncheck them and re-run Apply, or verify "
                "the pairing by hand in the detail view first:\n\n" + details,
            )
            return

        target_project = self._current_diff_target_project
        target_path = self._current_diff_target_path

        working_tree = copy.deepcopy(target_project.tree)
        working_project = _build_project_model(working_tree, source_description=target_path)
        result = apply_differences(working_project, checked)

        if result.failed:
            details = "\n".join(f"- {'/'.join(f.difference.path)}: {f.message}" for f in result.failed)
            QMessageBox.critical(
                self,
                "Apply Failed -- No Changes Written",
                f"{len(result.failed)} of {len(checked)} checked differences could not "
                f"be applied (Target may have changed since this comparison was run). "
                f"No changes were written to '{target_path}'.\n\n" + details,
            )
            return

        backup_path = target_path + ".bak"
        shutil.copy2(target_path, backup_path)
        serialized = etree.tostring(
            working_tree, xml_declaration=False, encoding="UTF-8", pretty_print=False
        )
        with open(target_path, "wb") as f:
            f.write(serialized)

        QMessageBox.information(
            self,
            "Apply Changes to Target",
            f"Applied {len(checked)} change(s) to '{target_path}'.\nBackup saved to '{backup_path}'.",
        )
        self.open_project_file(target_path)

    def _build_menu_bar(self):
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_diff_merge_menu()
        self._build_schema_menu()
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

        find_action = menu.addAction("Find...")
        find_action.setShortcut("Ctrl+F")
        find_action.triggered.connect(self._show_find_bar)

        find_next_action = menu.addAction("Find Next")
        find_next_action.setShortcut("F3")
        find_next_action.triggered.connect(self._find_next)

        find_all_action = menu.addAction("Find All")
        find_all_action.setShortcut("Ctrl+Shift+F")
        find_all_action.triggered.connect(self._find_all)

        replace_action = menu.addAction("Replace...")
        replace_action.setShortcut("Ctrl+R")
        replace_action.triggered.connect(self._show_replace_bar)

        replace_all_action = menu.addAction("Replace All")
        replace_all_action.setShortcut("Ctrl+Alt+Return")
        replace_all_action.triggered.connect(self._replace_all)

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

    def _reveal_raw_xml_tab(self):
        self.center_stage.set_raw_xml_tab_visible(True)
        self._raw_xml_panel_action.setChecked(True)
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)

    def _show_find_bar(self):
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.show_find()

    def _show_replace_bar(self):
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.show_replace()

    def _find_next(self):
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.find_next()

    def _find_all(self):
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.find_all()

    def _replace_all(self):
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.replace_all()

    def _build_diff_merge_menu(self):
        menu = self.menuBar().addMenu("Diff / Merge")
        compare_action = menu.addAction("Compare / Merge Two Files...")
        compare_action.triggered.connect(self._compare_merge_two_files)
        menu.addSeparator()
        next_action = menu.addAction("Next Difference")
        next_action.triggered.connect(self.center_stage.diff_merge_panel.select_next_difference)
        prev_action = menu.addAction("Prev Difference")
        prev_action.triggered.connect(self.center_stage.diff_merge_panel.select_previous_difference)
        apply_action = menu.addAction("Apply Changes to Target")
        apply_action.triggered.connect(self._apply_changes_to_target)

    def _build_schema_menu(self):
        menu = self.menuBar().addMenu("Schema")
        annotate_action = menu.addAction("Annotate Schema Values...")
        annotate_action.triggered.connect(self._open_annotate_schema_values)

    def _open_annotate_schema_values(self):
        dialog = AnnotateSchemaValuesDialog(self, schema_storage_dir=self._schema_storage_dir)
        dialog.exec()

    def _build_tools_menu(self):
        menu = self.menuBar().addMenu("Tools")
        self._add_stub_action(menu, "Manage Captions...")
        menu.addSeparator()
        self._add_stub_action(menu, "Find Reused Tables...")
        menu.addSeparator()
        self._add_stub_action(menu, "Validate Project")
        menu.addSeparator()
        reparse_action = menu.addAction("Reparse Raw XML into Tree")
        reparse_action.triggered.connect(self._reparse_raw_xml)

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
