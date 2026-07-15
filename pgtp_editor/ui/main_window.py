import copy
import shutil
from pathlib import Path

from lxml import etree
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QWidget,
)

from pgtp_editor.diff.apply import apply_differences
from pgtp_editor.generation.config import load_executable_path, save_executable_path
from pgtp_editor.generation.runner import GeneratorRunner, build_generate_command
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
from pgtp_editor.validation.tier2 import validate_project
from pgtp_editor.ui._stub_action import add_stub_action
from pgtp_editor.ui.about import show_about_dialog
from pgtp_editor.ui.annotate_schema_values_dialog import AnnotateSchemaValuesDialog
from pgtp_editor.ui.caption_find_replace_dialog import CaptionFindReplaceDialog
from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.manual_panel import (
    ManualContentsPanel,
    load_manual_text,
    parse_chapters,
)
from pgtp_editor.ui.code_editor import CodeEditorDialog
from pgtp_editor.ui.event_body import (
    extract_event_body,
    insert_event_handler,
    replace_event_body,
)
from pgtp_editor.model.nodes import classify_event_side
from pgtp_editor.model.event_handlers import language_for_side
from pgtp_editor.ui import caption_scan
from pgtp_editor.ui import search
from pgtp_editor.ui.project_tree import ProjectTreePanel
from pgtp_editor.ui.properties_panel import PropertiesPanel
from pgtp_editor.ui.schema_viewer import SchemaViewerWindow
from pgtp_editor.ui.schema_viewer_data import open_labels_text, open_xsd_text


_FIND_RESULT_PREFIX = "[Find] "

_VALIDATION_PREFIX = "[Validate] "

_GENERATOR_OUTPUT_PREFIX = "[PHP] "

_FIND_ALL_BATCH = 200

_SCHEMA_REPORT_TEMPLATES = {
    "new_element": "[Schema] NEW ELEMENT: {path} (first seen in {source})",
    "new_attribute": "[Schema] NEW ATTRIBUTE: {path}@{attr} (first seen in {source})",
    "new_value": '[Schema] NEW ATTR VALUE: {path}@{attr} += "{value}" (from {source})',
    "enum_overflow": "[Schema] ENUM OVERFLOWED: {path}@{attr} now free-form string (from {source})",
    "now_optional": "[Schema] NOW OPTIONAL: {path}@{attr} (previously required, from {source})",
}


class MainWindow(QMainWindow):
    def __init__(
        self,
        schema_storage_dir: Path | None = None,
        generator_config_dir: Path | None = None,
        generator_runner=None,
    ):
        super().__init__()
        self._schema_storage_dir = schema_storage_dir
        self._generator_config_dir = generator_config_dir
        self._generator_runner = generator_runner if generator_runner is not None else GeneratorRunner()
        self._current_output_folder = None
        self._is_generating = False
        # Read-only schema viewer windows (Phase 1). Held on self so they are
        # not garbage-collected while open; reused/refreshed on reopen.
        self._xsd_viewer = None
        self._labels_viewer = None
        self.setWindowTitle("PGTP Editor")
        self.resize(1400, 900)

        self.project_tree = ProjectTreePanel(
            on_stub_action=self._not_implemented,
            on_compare_page=self._compare_page_with,
            on_compare_detail=self._compare_detail_with,
            on_selection_changed=self._on_tree_selection_changed,
            on_activate_node=self._on_tree_activate_node,
            on_jump_to_xml=self._on_tree_jump_to_xml,
            on_select_xml_block=self._on_tree_select_xml_block,
            on_see_table_in_caption=self._on_tree_see_table_in_caption,
            on_see_table_details_in_caption=self._on_tree_see_table_details_in_caption,
            on_jump_to_column_visibility=self._on_tree_jump_to_column_visibility,
            on_see_column_in_caption=self._on_tree_see_column_in_caption,
            on_edit_event_code=self._on_tree_edit_event_code,
            on_add_event_handler=self._on_tree_add_event_handler,
        )
        self.tree_dock = QDockWidget("Project Tree", self)
        self.tree_dock.setObjectName("tree_dock")
        self.left_tabs = QTabWidget()
        self.project_tab_index = self.left_tabs.addTab(self.project_tree, "Project")
        self.manual_contents = ManualContentsPanel()
        self.contents_tab_index = self.left_tabs.addTab(self.manual_contents, "Contents")
        # Contents rides with the Manual: hidden until the Manual is shown, and
        # hidden again when the Manual closes.
        self.left_tabs.setTabVisible(self.contents_tab_index, False)
        self.tree_dock.setWidget(self.left_tabs)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tree_dock)

        self.audit_panel = QListWidget()
        self.audit_dock = QDockWidget("Audit / Problems", self)
        self.audit_dock.setObjectName("audit_dock")
        self.audit_dock.setWidget(self.audit_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.audit_dock)

        self.center_stage = CenterStage()
        self.setCentralWidget(self.center_stage)

        # Populate the (static) manual once, into both the center-stage Manual
        # tab and the left-dock Contents tree. Only the resource load is guarded
        # (a packaging failure degrades gracefully); rendering/parsing and signal
        # wiring run unguarded so a genuine logic bug surfaces instead of being
        # swallowed.
        self.manual_contents.chapter_selected.connect(self._on_manual_chapter_selected)
        self.center_stage.manual_visibility_changed.connect(
            self._on_manual_visibility_changed
        )
        try:
            manual_text = load_manual_text()
        except Exception as exc:  # pragma: no cover - packaging safety net
            manual_text = None
            self.statusBar().showMessage(f"Manual unavailable: {exc}")
        if manual_text is not None:
            self.center_stage.manual_panel.set_markdown(manual_text)
            self.manual_contents.set_chapters(parse_chapters(manual_text))

        self.center_stage.xml_editor.line_clicked.connect(self._on_editor_line_clicked)
        self.center_stage.find_replace_bar.set_on_find_all(self._populate_find_all_results)
        self.center_stage.find_replace_bar.set_on_stop_find_all(self._stop_find_all)
        self.center_stage.find_replace_bar.set_on_status(self.statusBar().showMessage)
        self._find_all_timer = None
        self._find_all_iter = None
        self._find_all_stop = False
        self._find_all_count = 0
        self._find_all_term = ""
        self.audit_panel.itemClicked.connect(self._on_audit_item_clicked)
        self.center_stage.caption_management_panel._on_apply = self._apply_caption_edits
        self.center_stage.caption_management_panel._on_close = self._close_caption_mode
        self.center_stage.caption_management_panel.on_go_to_line = self._caption_go_to_line
        # Ctrl+F / Ctrl+R open the caption Filter / Replace dialogs (issue #1).
        # Wire the panel's callbacks to open the caption dialogs; the panel's
        # open_filter_dialog / open_replace_dialog methods delegate to these.
        self.center_stage.caption_management_panel.on_open_filter = (
            self._open_caption_filter_dialog
        )
        self.center_stage.caption_management_panel.on_open_replace = (
            self._open_caption_replace_dialog
        )
        self._caption_find_replace_dialog = None

        # Window-scoped, mode-gated Ctrl+F / Ctrl+R. While Caption Mode is
        # active these fire anywhere in the window (regardless of which widget
        # has focus — e.g. after Go-to-line moves focus to the read-only Raw XML
        # editor) and route to the caption Filter / Replace dialogs. They are
        # disabled outside Caption Mode; the Edit-menu Find…/Replace… actions
        # drive normal Raw-XML find/replace instead. Toggled in
        # _enter_caption_mode / _close_caption_mode.
        self._caption_filter_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._caption_filter_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._caption_filter_shortcut.activated.connect(self._caption_shortcut_open_filter)
        self._caption_filter_shortcut.setEnabled(False)
        self._caption_replace_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        self._caption_replace_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._caption_replace_shortcut.activated.connect(self._caption_shortcut_open_replace)
        self._caption_replace_shortcut.setEnabled(False)
        self.center_stage.xml_editor.read_only_edit_attempted.connect(
            self._on_read_only_edit_attempted
        )
        self.center_stage.xml_editor.find_selected_text.connect(
            self._on_find_selected_text
        )
        self.center_stage.xml_editor.edit_code_requested.connect(
            self._on_edit_code_requested
        )
        # The live CodeEditorDialog (kept referenced so it is not GC'd while
        # shown). MainWindow owns its lifecycle + the write-back.
        self._code_editor_dialog: CodeEditorDialog | None = None

        # Permanent status-bar mode indicator (Editing vs Caption Mode).
        self._mode_label = QLabel("Editing Mode")
        self.statusBar().addPermanentWidget(self._mode_label)

        self.properties_panel = PropertiesPanel(xml_editor=self.center_stage.xml_editor)
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setObjectName("properties_dock")
        self.properties_dock.setWidget(self.properties_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

        self._current_project = None
        self._current_project_path = None
        self._current_diff_target_project = None
        self._current_diff_target_path = None

        # Document dirty-state tracking. `_loading` guards programmatic
        # setPlainText calls (load/revert/close) so they don't spuriously
        # mark the buffer dirty.
        self._dirty = False
        self._loading = False
        self.center_stage.xml_editor.textChanged.connect(self._on_editor_text_changed)

        self._build_menu_bar()

    def _not_implemented(self, label):
        self.statusBar().showMessage(f"Not yet implemented: {label}", 5000)

    # -- Document state: dirty tracking + window title -----------------------

    def _on_editor_text_changed(self) -> None:
        """Mark the buffer dirty when the user edits the Raw XML editor.
        Programmatic sets (load/revert/close) run under `_loading` and are
        ignored so they don't spuriously flag the document dirty."""
        if self._loading:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._update_title()

    def _update_title(self) -> None:
        title = "PGTP Editor"
        if self._current_project_path:
            title = f"{title} - {Path(self._current_project_path).name}"
        if self._dirty:
            title = f"{title} *"
        self.setWindowTitle(title)

    def _on_tree_selection_changed(self, node, kind):
        self.properties_panel.show_node(node, kind)

    # -- Phase D: tree context-menu + double-click callbacks -----------------

    def _tree_jump_to_line(self, line) -> None:
        """Reveal the Raw XML tab and navigate the editor to `line`. Shared by
        double-click activation and the "Jump to …" menu actions. No-op when
        `line` is None (e.g. a node with no known sourceline)."""
        if line is None:
            return
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)
        self.center_stage.xml_editor.navigate_to_line(line)

    def _on_tree_activate_node(self, node, kind):
        """Double-click a tree item: jump the editor to the node's source line
        (for a Detail, its outer <Detail> open line). Single-click still only
        updates Properties -- the editor jumps ONLY on explicit activation."""
        if node is None:
            return
        self._tree_jump_to_line(getattr(node, "sourceline", None))

    def _on_tree_jump_to_xml(self, node):
        if node is None:
            return
        self._tree_jump_to_line(getattr(node, "sourceline", None))

    def _on_tree_select_xml_block(self, node):
        """Select the whole <Page>/<Detail> element block: navigate to the
        node's open-tag line, move the cursor INTO the opening tag (first '<'
        + 1) so the enclosing element is the node itself, then select it."""
        if node is None:
            return
        line = getattr(node, "sourceline", None)
        if line is None:
            return
        editor = self.center_stage.xml_editor
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)
        editor.navigate_to_line(line)
        self._place_cursor_in_opening_tag(line)
        editor.select_enclosing_block()

    def _place_cursor_in_opening_tag(self, line: int) -> None:
        """Put the editor caret just past the first '<' on `line`, so the
        enclosing element resolved by select_enclosing_block is the element
        whose opening tag starts there (not its parent, which a caret in the
        leading whitespace would resolve to)."""
        from PySide6.QtGui import QTextCursor

        editor = self.center_stage.xml_editor
        text = editor.line_text(line)
        lt = text.find("<")
        column = lt + 1 if lt != -1 else 0
        block = editor.document().findBlockByNumber(max(0, line - 1))
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + column)
        editor.setTextCursor(cursor)

    def _on_tree_see_table_in_caption(self, node):
        if node is None:
            return
        self.enter_caption_mode_for_table(node.table_name or "")

    def _on_tree_see_table_details_in_caption(self, node):
        if node is None:
            return
        self.enter_caption_mode_for_table_details(node.table_name or "")

    def _on_tree_jump_to_column_visibility(self, node):
        """Jump the editor to the owning page/detail's <Columns> element. The
        ColumnNode retains its <ColumnPresentation> lxml element; walk up to the
        ancestor that owns a <Columns> child and use that child's sourceline.
        Falls back to the column's own line if it cannot be resolved."""
        if node is None:
            return
        line = self._columns_block_line(node)
        if line is None:
            line = getattr(node, "sourceline", None)
        self._tree_jump_to_line(line)

    @staticmethod
    def _columns_block_line(node):
        """Resolve the <Columns> block sourceline for a ColumnNode, or None.

        The retained element is the <ColumnPresentation>; its owning page/detail
        element holds both <ColumnPresentations> (presentation) and <Columns>
        (visibility) as siblings. Walk ancestors until one has a <Columns>
        child and return that child's sourceline."""
        element = getattr(node, "element", None)
        if element is None:
            return None
        current = element.getparent()
        while current is not None:
            columns = current.find("Columns")
            if columns is not None:
                return columns.sourceline
            current = current.getparent()
        return None

    def _on_tree_see_column_in_caption(self, node):
        if node is None:
            return
        table_name = self._owning_table_name(node)
        self.enter_caption_mode_for_field(node.field_name or "", table_name)

    @staticmethod
    def _owning_table_name(node):
        """The tableName of the page/detail owning this column, from the
        retained <ColumnPresentation> element -- nearest ancestor with a
        tableName attribute. None if unresolvable (filter then keys on
        fieldName alone)."""
        element = getattr(node, "element", None)
        if element is None:
            return None
        for ancestor in element.iterancestors():
            table_name = ancestor.get("tableName")
            if table_name:
                return table_name
        return None

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
            self._loading = True
            try:
                self.center_stage.xml_editor.setPlainText(raw_text)
            finally:
                self._loading = False
        self._set_dirty(False)
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

            # Hand the freshly-updated in-memory model to the Raw XML editor so
            # value-hover tooltips reflect the latest labels without a per-hover
            # disk reload. If enrichment fails below, the editor keeps whatever
            # model it had (possibly None), which is fine.
            self.center_stage.xml_editor.set_schema_model(model)

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

    def _populate_find_all_results(self, term: str) -> None:
        """Start a streaming Find All: results are appended to the Audit panel
        a batch at a time on a 0ms QTimer, yielding to the event loop between
        batches so the UI stays responsive and Stop takes effect promptly."""
        self._cancel_find_all_timer()
        self._clear_find_results()
        self._find_all_term = term
        self._find_all_count = 0
        self._find_all_stop = False
        text = self.center_stage.xml_editor.toPlainText()
        self._find_all_iter = search.iter_matches(text, term)
        self.center_stage.find_replace_bar.set_find_all_running(True)
        self.statusBar().showMessage(f'Finding "{term}"…')
        self._find_all_timer = QTimer(self)
        self._find_all_timer.timeout.connect(self._find_all_step)
        self._find_all_timer.start(0)

    def _find_all_step(self) -> None:
        if self._find_all_stop:
            self._finish_find_all(stopped=True)
            return
        for _ in range(_FIND_ALL_BATCH):
            try:
                match = next(self._find_all_iter)
            except StopIteration:
                self._finish_find_all(stopped=False)
                return
            item = QListWidgetItem(f"{_FIND_RESULT_PREFIX}line {match.line}: {match.preview}")
            item.setData(Qt.ItemDataRole.UserRole, match.line)
            self.audit_panel.addItem(item)
            self._find_all_count += 1
        self.statusBar().showMessage(
            f'Finding "{self._find_all_term}"… found {self._find_all_count}'
        )

    def _finish_find_all(self, stopped: bool) -> None:
        self._cancel_find_all_timer()
        summary = QListWidgetItem(
            f'{_FIND_RESULT_PREFIX}{self._find_all_count} match(es) for "{self._find_all_term}"'
        )
        self.audit_panel.addItem(summary)  # no line data -> clicking is a no-op
        self.center_stage.find_replace_bar.set_find_all_running(False)
        if stopped:
            self.statusBar().showMessage(
                f"Find All stopped — found {self._find_all_count} item(s)"
            )
        else:
            self.statusBar().showMessage(f"Found {self._find_all_count} item(s)")

    def _stop_find_all(self) -> None:
        """Request that an in-flight streaming Find All stop; the next
        _find_all_step tick finishes the run, keeping results found so far."""
        self._find_all_stop = True

    def _cancel_find_all_timer(self) -> None:
        if self._find_all_timer is not None:
            self._find_all_timer.stop()
            # deleteLater the C++ QTimer so repeated Find All runs don't
            # accumulate stopped timer children on the window.
            self._find_all_timer.deleteLater()
            self._find_all_timer = None
        # Drop the (possibly large) generator so we don't hold its closure
        # over the snapshotted document text between runs.
        self._find_all_iter = None

    def _clear_find_results(self) -> None:
        """Remove only prior [Find]-prefixed entries, leaving schema-learning
        / validation entries intact. Iterates from the bottom so removals
        don't shift not-yet-visited indices."""
        for row in range(self.audit_panel.count() - 1, -1, -1):
            item = self.audit_panel.item(row)
            if item.text().startswith(_FIND_RESULT_PREFIX):
                self.audit_panel.takeItem(row)

    def _clear_validation_results(self) -> None:
        """Remove only prior [Validate]-prefixed audit entries, leaving find /
        schema-learning entries intact. Iterates from the bottom so removals
        don't shift not-yet-visited indices."""
        for row in range(self.audit_panel.count() - 1, -1, -1):
            item = self.audit_panel.item(row)
            if item.text().startswith(_VALIDATION_PREFIX):
                self.audit_panel.takeItem(row)

    def _validate_project(self) -> None:
        """Run the Tier-2 structural-sanity checks and report into the Audit
        panel; each issue is click-to-navigable via its source line."""
        if self._current_project is None:
            self.statusBar().showMessage("Open a project to validate.", 5000)
            return
        self._clear_validation_results()
        issues = validate_project(self._current_project)
        n_err = 0
        n_warn = 0
        for issue in issues:
            if issue.severity == "error":
                n_err += 1
            else:
                n_warn += 1
            if issue.line is None:
                text = f"{_VALIDATION_PREFIX}{issue.severity.upper()}: {issue.message}"
            else:
                text = (
                    f"{_VALIDATION_PREFIX}{issue.severity.upper()} "
                    f"line {issue.line}: {issue.message}"
                )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, issue.line)
            self.audit_panel.addItem(item)
        if issues:
            self.statusBar().showMessage(
                f"Validation: {n_err} error(s), {n_warn} warning(s)", 5000
            )
        else:
            self.statusBar().showMessage("Validation passed — no issues.", 5000)

    def _on_audit_item_clicked(self, item) -> None:
        line = item.data(Qt.ItemDataRole.UserRole)
        if line is None:
            return  # schema entry or the [Find] summary line: no-op
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)
        self.center_stage.xml_editor.navigate_to_line(line)

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
        # The fallback view displays on-disk content of a file that FAILED to
        # open -- it is not a user edit, so it must not mark the document dirty
        # (and must never let a later Save overwrite the still-tracked good
        # project with this broken text). Guard the same way as the load path.
        self._loading = True
        try:
            self.center_stage.xml_editor.setPlainText(raw_text)
        finally:
            self._loading = False
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

    def _write_project_text(self, path) -> None:
        """Write the Raw XML editor buffer verbatim to `path` as UTF-8. If
        `path` already exists, copy it to `path + '.bak'` first (same .bak
        convention as Apply-to-Target)."""
        if Path(path).exists():
            shutil.copy2(path, path + ".bak")
        Path(path).write_text(
            self.center_stage.xml_editor.toPlainText(), encoding="utf-8", newline=""
        )

    def _save_project(self) -> None:
        if not self._current_project_path:
            self._save_project_as()
            return
        try:
            self._write_project_text(self._current_project_path)
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save:\n\n{exc}")
            return
        self._set_dirty(False)
        self.statusBar().showMessage(f"Saved {Path(self._current_project_path).name}", 5000)

    def _save_project_as(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save Project As", "", "PGTP files (*.pgtp)"
        )
        if not path:
            return
        try:
            self._write_project_text(path)
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save:\n\n{exc}")
            return
        self._current_project_path = path
        self._set_dirty(False)
        self.statusBar().showMessage(f"Saved as {Path(path).name}", 5000)

    # -- Close / Revert ------------------------------------------------------

    def _confirm_close(self) -> str:
        """Ask the user how to resolve unsaved changes before closing.

        Returns "save", "discard", or "cancel". Split out from
        `_close_project` so tests can pass `confirm=` directly (or
        monkeypatch this) instead of ever driving a real modal.
        """
        result = QMessageBox.question(
            self,
            "Unsaved Changes",
            "The project has unsaved changes. Save before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if result == QMessageBox.StandardButton.Save:
            return "save"
        if result == QMessageBox.StandardButton.Discard:
            return "discard"
        return "cancel"

    def _close_project(self, confirm=None) -> None:
        """Close the current project, prompting to resolve unsaved changes.

        `confirm` is the test seam: "save"/"discard"/"cancel". When None and
        the buffer is dirty, `_confirm_close()` decides; when None and clean,
        the close proceeds (treated as "discard").
        """
        if self._dirty:
            if confirm is None:
                confirm = self._confirm_close()
        else:
            confirm = "discard"

        if confirm == "cancel":
            return
        if confirm == "save":
            self._save_project()
            if self._dirty:
                # Save was cancelled (e.g. Save-As dialog dismissed) --
                # don't discard the user's changes.
                return

        self._loading = True
        try:
            self.center_stage.xml_editor.setPlainText("")
        finally:
            self._loading = False
        self.project_tree.clear()
        self._current_project = None
        self._current_project_path = None
        self._set_dirty(False)

    def _revert_project(self) -> None:
        """Reload the project from its `<path>.bak` backup, if one exists.

        Restores the .bak content into the editor and rebuilds the tree from
        it while keeping `_current_project_path` pointing at the real file.
        The buffer then differs from the on-disk file, so the document is
        marked dirty.
        """
        if not self._current_project_path:
            self.statusBar().showMessage("Nothing to revert to.", 5000)
            return
        bak_path = self._current_project_path + ".bak"
        if not Path(bak_path).exists():
            self.statusBar().showMessage("Nothing to revert to.", 5000)
            return

        try:
            project = load_project(bak_path)
        except PgtpParseError as exc:
            self._handle_parse_failure(bak_path, exc)
            return

        raw_text = self._read_raw_text(bak_path)
        if raw_text is not None:
            self._loading = True
            try:
                self.center_stage.xml_editor.setPlainText(raw_text)
            finally:
                self._loading = False
        self.project_tree.populate_from_project(project)
        self._current_project = project
        self._set_dirty(True)
        self.statusBar().showMessage(
            f"Reverted to {Path(bak_path).name}", 5000
        )

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
        save_action = menu.addAction("Save")
        save_action.triggered.connect(self._save_project)
        save_as_action = menu.addAction("Save As...")
        save_as_action.triggered.connect(self._save_project_as)
        revert_action = menu.addAction("Revert")
        revert_action.triggered.connect(self._revert_project)
        self._revert_action = revert_action
        close_action = menu.addAction("Close")
        close_action.triggered.connect(lambda: self._close_project())
        self._close_action = close_action
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
        self._editor_find_action = find_action

        find_next_action = menu.addAction("Find Next")
        find_next_action.setShortcut("F3")
        find_next_action.triggered.connect(self._find_next)

        find_all_action = menu.addAction("Find All")
        find_all_action.setShortcut("Ctrl+Shift+F")
        find_all_action.triggered.connect(self._find_all)

        replace_action = menu.addAction("Replace...")
        replace_action.setShortcut("Ctrl+R")
        replace_action.triggered.connect(self._show_replace_bar)
        self._editor_replace_action = replace_action

        replace_all_action = menu.addAction("Replace All")
        replace_all_action.setShortcut("Ctrl+Alt+Return")
        replace_all_action.triggered.connect(self._replace_all)

        menu.addSeparator()

        select_enclosing_action = menu.addAction("Select Enclosing Block")
        select_enclosing_action.setShortcut("Ctrl+Shift+B")
        select_enclosing_action.triggered.connect(
            self.center_stage.xml_editor.select_enclosing_block
        )

        select_parent_action = menu.addAction("Select Parent Block")
        select_parent_action.setShortcut("Ctrl+Shift+A")
        select_parent_action.triggered.connect(
            self.center_stage.xml_editor.select_parent_block
        )

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

    def _on_find_selected_text(self, text: str) -> None:
        """Editor right-click "Find": reveal the Raw XML tab, prefill the find
        bar with the selection, and run Find Next -- the same path Edit ->
        Find/Find Next drives."""
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.show_find()
        self.center_stage.find_replace_bar.set_find_text(text)
        self.center_stage.find_replace_bar.find_next()

    def _on_edit_code_requested(self, start_line: int) -> None:
        """Editor "Edit code…": open the dedicated CodeEditorDialog prefilled
        with the event-handler body at `start_line` (unescaped) in the right
        language, and on save write the (re-escaped) new body back into the Raw
        XML buffer. The write-back goes through the buffer regardless of
        read-only state, so it works in Caption Mode too."""
        buffer_text = self.center_stage.xml_editor.toPlainText()
        try:
            tag, side, body = extract_event_body(buffer_text, start_line)
        except ValueError:
            # The body vanished (e.g. buffer edited between menu build and
            # trigger); nothing to edit.
            return
        dialog = CodeEditorDialog(
            language=language_for_side(side),
            handler_name=tag,
            parent=self,
        )
        dialog.set_code(body)
        self._code_editor_dialog = dialog

        def _write_back(new_code: str) -> None:
            current = self.center_stage.xml_editor.toPlainText()
            try:
                updated = replace_event_body(current, start_line, new_code)
            except ValueError:
                return
            self.center_stage.xml_editor.setPlainText(updated)

        dialog.saved.connect(_write_back)
        # Non-blocking: show() (not exec()) so tests drive save/cancel via the
        # dialog's own slots without a modal event loop.
        dialog.setModal(True)
        dialog.show()

    def _on_tree_edit_event_code(self, node) -> None:
        """Tree event-node "Edit code…": open the CodeEditorDialog prefilled
        with the EventNode's body in the right language; on save, write the
        (re-escaped) body back into the Raw XML buffer at the node's span
        (reusing replace_event_body keyed to node.sourceline). The write-back
        goes through the buffer regardless of read-only state."""
        if node is None:
            return
        start_line = getattr(node, "sourceline", None)
        if start_line is None:
            self.statusBar().showMessage(
                "This event handler has no source line to edit.", 5000
            )
            return
        dialog = CodeEditorDialog(
            language=language_for_side(node.side),
            handler_name=node.tag_name,
            parent=self,
        )
        dialog.set_code(node.text or "")
        self._code_editor_dialog = dialog

        def _write_back(new_code: str) -> None:
            current = self.center_stage.xml_editor.toPlainText()
            try:
                updated = replace_event_body(current, start_line, new_code)
            except ValueError:
                return
            self.center_stage.xml_editor.setPlainText(updated)

        dialog.saved.connect(_write_back)
        dialog.setModal(True)
        dialog.show()

    def _on_tree_add_event_handler(self, node, tag: str) -> None:
        """Tree Page "Add Event Handler ▸ <tag>": open an empty
        CodeEditorDialog in the handler's language; on save, insert a new
        <tag enabled="true"> handler into the page's <EventHandlers> in the Raw
        XML buffer (creating the block if absent), then show a status message.
        The write-back goes through the buffer regardless of read-only state."""
        if node is None:
            return
        page_start_line = getattr(node, "sourceline", None)
        if page_start_line is None:
            self.statusBar().showMessage(
                "This page has no source line to insert into.", 5000
            )
            return
        side = classify_event_side(tag)
        dialog = CodeEditorDialog(
            language=language_for_side(side),
            handler_name=tag,
            parent=self,
        )
        self._code_editor_dialog = dialog

        def _write_back(new_code: str) -> None:
            current = self.center_stage.xml_editor.toPlainText()
            try:
                updated = insert_event_handler(current, page_start_line, tag, new_code)
            except ValueError:
                self.statusBar().showMessage(
                    f"Could not insert {tag}: page not found in the buffer.", 5000
                )
                return
            self.center_stage.xml_editor.setPlainText(updated)
            self.statusBar().showMessage(
                f"Added event handler {tag}. Reparse Raw XML to see it in the tree.",
                5000,
            )

        dialog.saved.connect(_write_back)
        dialog.setModal(True)
        dialog.show()

    def _find_all(self):
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.find_all()

    def _replace_all(self):
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.replace_all()

    def _enter_caption_mode(self) -> bool:
        """Tools -> Manage Captions...: snapshot the frozen Raw XML, scan it,
        load the grid, and enter caption mode (Raw XML hidden). Requires
        non-empty Raw XML; otherwise a status message and no mode change.
        Returns True iff caption mode was entered (False if Raw XML empty)."""
        snapshot = self.center_stage.xml_editor.toPlainText()
        if not snapshot.strip():
            self.statusBar().showMessage(
                "Manage Captions: open a project (Raw XML is empty) first.", 5000
            )
            return False
        entries = caption_scan.scan_captions(snapshot)
        self.center_stage.caption_management_panel.load_entries(entries, snapshot_text=snapshot)
        self.center_stage.enter_caption_mode()
        self._mode_label.setText("Caption Mode (XML read-only)")
        # Caption Mode is authoritative: Ctrl+F / Ctrl+R follow the mode, not
        # focus. Enable the window-scoped caption shortcuts and disable the
        # editor Find…/Replace… actions (disabling a QAction disables its
        # shortcut, so there is no ambiguous-shortcut conflict).
        self._caption_filter_shortcut.setEnabled(True)
        self._caption_replace_shortcut.setEnabled(True)
        self._editor_find_action.setEnabled(False)
        self._editor_replace_action.setEnabled(False)
        return True

    def enter_caption_mode_for_table(self, table_name: str) -> None:
        """Enter caption mode, then filter the grid to `table_name`'s rows
        (Phase C.2). No-op filter if entering failed (empty Raw XML)."""
        if self._enter_caption_mode():
            self.center_stage.caption_management_panel.filter_to_table(table_name)

    def enter_caption_mode_for_table_details(self, table_name: str) -> None:
        """Enter caption mode, then filter to `table_name`'s Detail-embed rows
        (Phase C.2)."""
        if self._enter_caption_mode():
            self.center_stage.caption_management_panel.filter_to_table_details(
                table_name
            )

    def enter_caption_mode_for_field(
        self, field_name: str, table_name: str | None = None
    ) -> None:
        """Enter caption mode, then filter to the column `field_name` (optionally
        also `table_name`) and select/scroll to its row (Phase C.2)."""
        if self._enter_caption_mode():
            self.center_stage.caption_management_panel.filter_to_field(
                field_name, table_name
            )

    def _apply_caption_edits(self, edited_text: str) -> None:
        """Panel Apply callback: count the changed rows, write the edited text
        into the Raw XML editor buffer (in memory only), and refresh the
        panel's snapshot so further edits in the same session stay line-valid."""
        panel = self.center_stage.caption_management_panel
        changed_count = len(panel.changed_edits())
        self.center_stage.xml_editor.setPlainText(edited_text)
        panel.load_entries(caption_scan.scan_captions(edited_text), snapshot_text=edited_text)
        self.statusBar().showMessage(f"Updated {changed_count} caption(s).", 5000)

    def _close_caption_mode(self):
        """Panel Close callback: leave caption mode and restore Raw XML.
        Pending (unapplied) edits are discarded by re-scanning on next enter."""
        self.center_stage.leave_caption_mode()
        self._mode_label.setText("Editing Mode")
        # Reverse the mode gating: disable the caption shortcuts and restore the
        # editor Find…/Replace… actions (and their Ctrl+F / Ctrl+R shortcuts).
        self._caption_filter_shortcut.setEnabled(False)
        self._caption_replace_shortcut.setEnabled(False)
        self._editor_find_action.setEnabled(True)
        self._editor_replace_action.setEnabled(True)

    def _caption_go_to_line(self, line: int) -> None:
        """Caption panel Go-to-line callback: switch to the Raw XML tab (which
        stays visible but read-only in Caption Mode) and navigate to `line`."""
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)
        self.center_stage.xml_editor.navigate_to_line(line)

    def _make_caption_find_replace_dialog(self, replace_enabled: bool):
        """Construct (but do NOT exec) the shared Find/Filter/Replace dialog
        wired to the caption panel. In Replace mode, Find-what is pre-loaded
        with the grid's currently-active filter pattern. Returns the dialog so
        tests can drive it without ``.exec()``."""
        panel = self.center_stage.caption_management_panel
        initial_find = panel.current_filter_pattern() if replace_enabled else ""
        dialog = CaptionFindReplaceDialog(
            on_filter=self._caption_apply_filter,
            on_replace_all=self._caption_replace_all,
            replace_enabled=replace_enabled,
            initial_find=initial_find,
            parent=self,
        )
        # Keep a reference so the non-modal dialog is not garbage-collected.
        self._caption_find_replace_dialog = dialog
        return dialog

    def _caption_shortcut_open_filter(self) -> None:
        """Window-scoped Ctrl+F slot (active only in Caption Mode): route to the
        caption panel's filter dialog regardless of which widget has focus."""
        self.center_stage.caption_management_panel.open_filter_dialog()

    def _caption_shortcut_open_replace(self) -> None:
        """Window-scoped Ctrl+R slot (active only in Caption Mode): route to the
        caption panel's replace dialog regardless of which widget has focus
        (e.g. after Go-to-line moved focus to the read-only Raw XML editor).
        Preserves the pre-load-active-filter behaviour via open_replace_dialog."""
        self.center_stage.caption_management_panel.open_replace_dialog()

    def _open_caption_filter_dialog(self) -> None:
        """Tools -> Caption Filter…: open the shared dialog in filter-only mode
        (non-blocking show)."""
        dialog = self._make_caption_find_replace_dialog(replace_enabled=False)
        dialog.show()

    def _open_caption_replace_dialog(self) -> None:
        """Caption-mode Ctrl+R: open the shared dialog in Replace mode,
        pre-loading the grid's active filter pattern (non-blocking show)."""
        dialog = self._make_caption_find_replace_dialog(replace_enabled=True)
        dialog.show()

    def _caption_apply_filter(self, pattern: str, mode: str, case: bool) -> None:
        """Filter callback: apply the pattern as a whole-row grid filter. Lets
        an invalid-regex ValueError propagate so the dialog shows it inline."""
        self.center_stage.caption_management_panel.apply_find_filter(pattern, mode, case)

    def _caption_replace_all(
        self, find: str, replacement: str, mode: str, case: bool, in_selection: bool
    ) -> None:
        """Replace-All callback: transform each in-scope row's Value into its
        New Value, then report the count. Lets ValueError propagate for the
        dialog's inline error."""
        count = self.center_stage.caption_management_panel.replace_all_find(
            find, replacement, mode, case, in_selection
        )
        self.statusBar().showMessage(f"Replaced in {count} caption(s).", 5000)

    def _on_read_only_edit_attempted(self) -> None:
        """Flash a non-modal hint when the user tries to edit the read-only
        Raw XML editor while in Caption Mode."""
        self.statusBar().showMessage(
            "Raw XML is read-only in Caption Mode — close Caption Mode to edit.", 4000
        )

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
        open_xsd_action = menu.addAction("Open XSD")
        open_xsd_action.triggered.connect(self._open_xsd_viewer)
        open_labels_action = menu.addAction("Open XSD Labels (JSON)")
        open_labels_action.triggered.connect(self._open_labels_viewer)

    def _open_annotate_schema_values(self):
        dialog = AnnotateSchemaValuesDialog(self, schema_storage_dir=self._schema_storage_dir)
        dialog.exec()

    _NO_SCHEMA_MESSAGE = "No schema learned yet — open a .pgtp file first."

    def _open_xsd_viewer(self):
        try:
            text = open_xsd_text(self._schema_storage_dir)
        except Exception as exc:
            self.statusBar().showMessage(f"Could not read schema model: {exc}", 5000)
            return
        if text is None:
            self.statusBar().showMessage(self._NO_SCHEMA_MESSAGE, 5000)
            return
        if self._xsd_viewer is None:
            self._xsd_viewer = SchemaViewerWindow(self)
        self._xsd_viewer.set_title("Schema XSD")
        self._xsd_viewer.set_content(text)
        self._xsd_viewer.show()

    def _open_labels_viewer(self):
        text = open_labels_text(self._schema_storage_dir)
        if text is None:
            self.statusBar().showMessage(self._NO_SCHEMA_MESSAGE, 5000)
            return
        if self._labels_viewer is None:
            self._labels_viewer = SchemaViewerWindow(self)
        self._labels_viewer.set_title("Schema Labels (JSON)")
        self._labels_viewer.set_content(text)
        self._labels_viewer.show()

    def _build_tools_menu(self):
        menu = self.menuBar().addMenu("Tools")
        manage_captions_action = menu.addAction("Manage Captions...")
        manage_captions_action.triggered.connect(self._enter_caption_mode)
        caption_filter_action = menu.addAction("Caption Filter…")
        caption_filter_action.triggered.connect(self._open_caption_filter_dialog)
        menu.addSeparator()
        self._add_stub_action(menu, "Find Reused Tables...")
        menu.addSeparator()
        validate_action = menu.addAction("Validate Project")
        validate_action.triggered.connect(self._validate_project)
        menu.addSeparator()
        reparse_action = menu.addAction("Reparse Raw XML into Tree")
        reparse_action.triggered.connect(self._reparse_raw_xml)

    def _build_generation_menu(self):
        menu = self.menuBar().addMenu("Generation")
        locate_action = menu.addAction("Locate PHP Generator Executable...")
        locate_action.triggered.connect(self._locate_generator)
        menu.addSeparator()
        generate_action = menu.addAction("Generate PHP...")
        generate_action.triggered.connect(self._generate_php)
        menu.addSeparator()
        open_output_action = menu.addAction("Open Output Folder")
        open_output_action.triggered.connect(self._open_output_folder)

    def _locate_generator(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Locate PHP Generator Executable", "", "Executables (*.exe);;All files (*)"
        )
        if not path:
            return
        save_executable_path(path, base_dir=self._generator_config_dir)
        self.statusBar().showMessage(f"PHP Generator set: {Path(path).name}", 5000)

    def _project_output_folder_default(self) -> str:
        """Prefill for the output-folder dialog: the project's Project@outputPath
        if readable, else the directory of the current project file, else ''."""
        project = self._current_project
        if project is not None and project.tree is not None:
            root = project.tree.getroot()
            if root is not None:
                declared = root.get("outputPath")
                if declared:
                    return declared
        if self._current_project_path:
            return str(Path(self._current_project_path).parent)
        return ""

    def _clear_generator_output(self) -> None:
        """Remove only prior [PHP]-prefixed Audit entries (leave [Find]/[Schema])."""
        for row in range(self.audit_panel.count() - 1, -1, -1):
            if self.audit_panel.item(row).text().startswith(_GENERATOR_OUTPUT_PREFIX):
                self.audit_panel.takeItem(row)

    def _generate_php(self) -> None:
        # 0. Reject a second run while one is in flight (avoid overlapping
        # QProcess instances orphaning the first).
        if self._is_generating:
            self.statusBar().showMessage("A generation is already in progress.", 5000)
            return

        # 1. Require an open project (a tracked model or non-empty editor).
        if self._current_project is None and not self.center_stage.xml_editor.toPlainText().strip():
            self.statusBar().showMessage("Open a project before generating.", 5000)
            return

        # 2. Require a configured executable.
        exe = load_executable_path(base_dir=self._generator_config_dir)
        if exe is None:
            QMessageBox.information(
                self,
                "Generate PHP",
                "Locate the PHP Generator executable first (Generation > Locate PHP Generator Executable...).",
            )
            return

        # 3. Save vs Save As vs Cancel so on-disk content matches the editor.
        choice = QMessageBox.question(
            self,
            "Save Before Generating",
            "The generator reads the project from disk. Save the current editor "
            "contents before generating?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.SaveAll  # used as the "Save As..." button
            | QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return
        if choice == QMessageBox.StandardButton.SaveAll:
            self._save_project_as()
        else:
            self._save_project()  # delegates to Save As when there's no path yet
        if not self._current_project_path:
            return  # Save As was cancelled -> nothing on disk to generate from

        # 4. Output folder (prefilled).
        output_folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self._project_output_folder_default()
        )
        if not output_folder:
            return

        # 5. Run via the injected runner.
        self._clear_generator_output()
        command = build_generate_command(exe, self._current_project_path, output_folder)
        self._current_output_folder = output_folder
        self._is_generating = True
        self.statusBar().showMessage("Generating…")
        self._generator_runner.run(
            command,
            on_output=self._append_generator_output,
            on_finished=self._on_generation_finished,
        )

    def _append_generator_output(self, line: str) -> None:
        self.audit_panel.addItem(f"{_GENERATOR_OUTPUT_PREFIX}{line}")

    def _on_generation_finished(self, exit_code: int) -> None:
        self._is_generating = False
        self.audit_panel.addItem(f"{_GENERATOR_OUTPUT_PREFIX}Generation finished (exit {exit_code})")
        if exit_code == 0:
            QMessageBox.information(self, "Generate PHP", "Generation succeeded.")
            self.statusBar().showMessage("Generation succeeded", 5000)
        else:
            QMessageBox.critical(
                self,
                "Generate PHP",
                f"Generation failed (exit {exit_code}). See the Audit / Problems panel for the generator log.",
            )
            self.statusBar().showMessage(f"Generation failed (exit {exit_code})", 5000)

    def _open_output_folder(self) -> None:
        if not self._current_output_folder:
            self.statusBar().showMessage("No output folder yet — run Generate PHP first.", 5000)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._current_output_folder))

    def _build_help_menu(self):
        menu = self.menuBar().addMenu("Help")
        manual_action = menu.addAction("Manual")
        manual_action.setShortcut("F1")
        manual_action.triggered.connect(self._show_manual)
        about_action = menu.addAction("About")
        about_action.triggered.connect(lambda: show_about_dialog(self))

    def _show_manual(self):
        # F1 / Help ▸ Manual toggles: if the Manual tab is already the one in
        # view, hide it; otherwise reveal it. The Contents tab follows via
        # _on_manual_visibility_changed.
        cs = self.center_stage
        if (
            cs.isTabVisible(cs.manual_tab_index)
            and cs.currentIndex() == cs.manual_tab_index
        ):
            cs.hide_manual()
            return
        cs.show_manual()
        self.tree_dock.setVisible(True)

    def _on_manual_visibility_changed(self, visible):
        """Keep the left-dock Contents tab in lockstep with the Manual tab: show
        and focus it when the Manual opens, hide it and fall back to Project when
        the Manual closes."""
        self.left_tabs.setTabVisible(self.contents_tab_index, visible)
        if visible:
            self.left_tabs.setCurrentWidget(self.manual_contents)
        else:
            self.left_tabs.setCurrentIndex(self.project_tab_index)

    def _on_manual_chapter_selected(self, index):
        self.center_stage.show_manual()
        self.center_stage.manual_panel.scroll_to_chapter(index)
