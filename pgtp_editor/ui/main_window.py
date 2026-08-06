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

import copy
import logging
import os
import re
import shutil
from pathlib import Path

from lxml import etree
from PySide6.QtCore import Qt, QSettings, QSignalBlocker, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor import debuglog
from pgtp_editor.diff.apply import apply_differences
from pgtp_editor.generation.config import (
    generator_config_path,
    load_executable_path,
    load_re_phpgen_root,
    save_executable_path,
    save_re_phpgen_root,
)
from pgtp_editor.generation.runner import GeneratorRunner, build_generate_command
from pgtp_editor.generation.re_runner import (
    PANGEN_SUBFOLDER,
    build_analyze_command,
    build_pangen_command,
    resolve_re_phpgen_python,
    validate_re_phpgen_root,
)
from pgtp_editor.generation.gap_summary import summarize_gap_json
from pgtp_editor.generation import from_table as table_gen
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
from pgtp_editor.schema_learning.storage import (
    CURATED_BUNDLED_VERSION,
    bundled_curated_xsd_text,
    curated_xsd_path,
    learned_xsd_path,
    schema_model_path,
)
from pgtp_editor.schema_learning.xsd_gen import generate_curated_xsd, generate_xsd
from pgtp_editor.schema_learning.xsd_load import XsdLoadError, load_curated
from pgtp_editor.schema_learning.xsd_verify import verify_curated
from pgtp_editor.validation.tier2 import validate_project
from pgtp_editor.ui._stub_action import add_stub_action
from pgtp_editor.ui.about import show_about_dialog
from pgtp_editor.ui.caption_find_replace_dialog import CaptionFindReplaceDialog
from pgtp_editor.ui.busy import busy_status, format_size
from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui import modals
from pgtp_editor.ui.manual_panel import (
    ManualContentsPanel,
    load_manual_text,
    parse_chapters,
)
from pgtp_editor.db.config import load_connection, save_connection, seed_params
from pgtp_editor.db.coherence import build_coherence_tree
from pgtp_editor.db.ddl_buffer import build_ddl_text
from pgtp_editor.db.migration_gen import connection_summary
from pgtp_editor.db.ddl_project import (
    DeployedObject,
    PgtpLink,
    ProjectSettings,
    compute_drift_markers,
    content_hash,
    is_project_dir,
    load_settings,
    routine_ddl_paths,
    save_settings,
    trigger_ddl_path,
)
from pgtp_editor.db.introspect import RoutineInfo, fetch_routines_and_triggers
from pgtp_editor.db.introspect import fetch_schema as db_fetch_schema
from pgtp_editor.db.introspect import test_connection as db_test_connection
from pgtp_editor.db.rename import rename_field, rename_table
from pgtp_editor.db.schema_index import SchemaIndex
from pgtp_editor.db.sandbox import (
    ProjectCapabilityStatus,
    SandboxCapabilities,
    SandboxMode,
    determine_project_tier,
    probe as sandbox_probe,
)
from pgtp_editor.ui.async_task import run_async
from pgtp_editor.ui.connection_setup_dialog import ConnectionSetupDialog
from pgtp_editor.ui.new_project_dialog import NewProjectDialog
from pgtp_editor.db.apply import ApplyOutcome
from pgtp_editor.db.ddl_check import CheckRequest
from pgtp_editor.ui.ddl_object_editor import CHECK_PREFIX, DdlObjectRef
from pgtp_editor.ui.sandbox_controller import SandboxController, SandboxOperation
from pgtp_editor.ui.new_routine_dialog import NewRoutineDialog
from pgtp_editor.ui.new_trigger_dialog import NewTriggerDialog
from pgtp_editor.ui.project_status_model import build_diagram, quality_state
from pgtp_editor.ui.project_status_panel import ProjectStatusPanel
from pgtp_editor.ui.project_settings_dialog import ProjectSettingsDialog
from pgtp_editor.ui.coherence_panel import CoherencePanel
from pgtp_editor.ui.ddl_buffer_panel import BrowserPanel
from pgtp_editor.ui.code_editor import CodeEditorDialog
from pgtp_editor.ui.history import SnapshotHistory
from pgtp_editor.ui.toolbar_controller import ToolbarController
from pgtp_editor.ui.ui_shell import UiShell
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
from pgtp_editor.ui.theme import apply_theme

_log = logging.getLogger(__name__)

_FIND_RESULT_PREFIX = "[Find] "

_VALIDATION_PREFIX = "[Validate] "

_GENERATOR_OUTPUT_PREFIX = "[PHP] "

#: Format Selection refusals (§18.4/§18.5). Not clickable, no line role
#: (carve-out 6) -- the offending span is already underlined in the tab.
_SQL_REFUSAL_PREFIX = "[SQL] "

#: §18.5 D3a: the Audit `SEVERITY` token for a finding's severity string.
#: **A vocabulary CASE translation only** -- `validation/tier2.py`'s
#: `ValidationIssue.severity` values (`"error"`/`"warning"`, plus
#: `db/ddl_check.py`'s third value `"notice"`, which the Audit panel shows as
#: `INFO`) mapped onto their rendered token. The `level -> severity` DECISION
#: has exactly one home -- `db/ddl_check.py::severity_for_level` -- and must
#: never be re-decided here; an unknown severity renders `WARNING`, never
#: `INFO` (D3a's "never silently mapped to INFO").
_CHECK_SEVERITY_TOKENS = {"error": "ERROR", "warning": "WARNING", "notice": "INFO"}

#: `SandboxController` operation outcomes (§18.5 D2). Never `[Check]` -- that
#: prefix belongs to the validation ladder, whose lines the panel owns.
_SANDBOX_PREFIX = "[Sandbox] "

_FIND_ALL_BATCH = 200

# Placeholder shown in the Edit-XSD tab when its backing file does not exist yet.
_EMPTY_XSD_SKELETON = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
    'elementFormDefault="qualified">\n</xs:schema>\n'
)

_SCHEMA_REPORT_TEMPLATES = {
    "new_element": "[Schema] NEW ELEMENT: {path} (first seen in {source})",
    "new_attribute": "[Schema] NEW ATTRIBUTE: {path}@{attr} (first seen in {source})",
    "new_value": '[Schema] NEW ATTR VALUE: {path}@{attr} += "{value}" (from {source})',
    "enum_overflow": "[Schema] ENUM OVERFLOWED: {path}@{attr} now free-form string (from {source})",
    "now_optional": "[Schema] NOW OPTIONAL: {path}@{attr} (previously required, from {source})",
}


class MainWindow(QMainWindow):
    #: The ONE sanctioned bridge while a lane is mid-extraction: legacy host
    #: attribute name -> dotted path to resolve on the host instead
    #: (e.g. ``{"_toolbar": "_toolbar_ui.toolbar"}``). Served by the single
    #: ``__getattr__`` below — **never** by hand-written delegating methods,
    #: which are invisible to review and never get removed.
    #:
    #: It must be EMPTY at every wave boundary: a decomposition wave that ends
    #: with entries here has not finished moving its callers, and
    #: ``tests/ui/test_mainwindow_surface.py`` fails on a non-empty dict.
    _LEGACY_DELEGATES: dict[str, str] = {}

    def __getattr__(self, name):
        """Resolve a `_LEGACY_DELEGATES` entry, else behave like any attribute
        error. Python only calls this when normal lookup has already failed, so
        it costs nothing on the hot path and cannot shadow a real attribute."""
        target = type(self)._LEGACY_DELEGATES.get(name)
        if target is None:
            raise AttributeError(
                f"{type(self).__name__!r} object has no attribute {name!r}"
            )
        obj = self
        for part in target.split("."):
            obj = getattr(obj, part)
        return obj

    def __init__(
        self,
        schema_storage_dir: Path | None = None,
        generator_config_dir: Path | None = None,
        generator_runner=None,
        settings=None,
        *,
        debug_log_path: Path | None = None,
    ):
        super().__init__()
        self._debug_log_path = debug_log_path
        self._debug_label = None
        # Injectable so tests point at a temp QSettings ini instead of the real
        # user registry (Sub-project D).
        # IniFormat (not the platform-native registry) so the location is a
        # plain file under UserScope -- portable, inspectable, and redirectable
        # by tests via QSettings.setPath (Sub-project D).
        self._settings = (
            settings
            if settings is not None
            else QSettings(
                QSettings.Format.IniFormat,
                QSettings.Scope.UserScope,
                "MDS",
                "PGTP Editor",
            )
        )
        self._schema_storage_dir = schema_storage_dir
        # The parsed curated.xsd (spec §11) — the sole schema source feeding
        # completion/hover. None until _load_curated_schema succeeds at least
        # once (loaded after self.audit_panel exists, near the end of __init__).
        self._curated_schema = None
        self._generator_config_dir = generator_config_dir
        self._generator_runner = generator_runner if generator_runner is not None else GeneratorRunner()
        self._current_output_folder = None
        self._is_generating = False
        self._last_gap_json: Path | None = None
        # Connection Setup dialog, held so it is not GC'd while shown non-modally.
        self._connection_dialog = None
        # The Database ▸ "Database/XML Coherence" checkable toggle (§17/§26).
        # Held on self so the project-close teardown can un-check it; None
        # until _build_database_menu runs later in __init__.
        self._coherence_action = None
        # Cached schema + connection summary from the last coherence run:
        # a reparse refreshes the panel without re-querying, and a right-click
        # "create from table" reuses the column metadata without re-querying.
        self._last_db_schema = None
        self._last_db_summary = None
        # Schema-aware Ctrl+Space completion (§18.6): the Qt-free lookup index
        # built once per DDL Explorer connect/refresh from the (now widened,
        # §18.6) fetch's `DatabaseSchema`, and handed to every open/newly
        # opened `DdlObjectEditorPanel` by injection (`set_schema_index`,
        # mirroring `XmlEditor.set_schema_model`). None until the DDL Explorer
        # has fetched at least once.
        self._ddl_schema_index: SchemaIndex | None = None
        #: The raw `DatabaseSchema` behind `_ddl_schema_index` (FQ-002).
        self._ddl_schema = None
        #: The §18.8 Project Status window, kept so re-invoking the menu entry
        #: raises the existing one instead of stacking duplicates.
        self._project_status_window = None
        # Off-thread executor seam. The coherence-check schema fetch opens a
        # connection; running it here would freeze the window on a slow/dead
        # host. Default marshals it to a threadpool worker; tests inject a
        # synchronous stub so the result path stays deterministic.
        self._run_async = run_async
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
        # The merged Database/XML Coherence view (§17, FQ-003) rides in its own
        # hidden tab, revealed and focused when the check runs (mirrors the
        # Contents tab pattern). It replaced three surfaces: the two DB-check
        # directions and the standalone "Table references" tab.
        self.coherence_panel = CoherencePanel()
        self.coherence_tab_index = self.left_tabs.addTab(
            self.coherence_panel, "Database/XML Coherence"
        )
        self.left_tabs.setTabVisible(self.coherence_tab_index, False)
        self.coherence_panel.rename_requested.connect(self._on_db_rename_requested)
        # Two jump signals because Qt cannot overload one name: DB-sourced rows
        # carry a (kind, name) pair, XML-sourced rows a 1-based line number.
        self.coherence_panel.name_jump_requested.connect(self._on_db_jump_requested)
        self.coherence_panel.jump_requested.connect(self._tree_jump_to_line)
        self.coherence_panel.create_requested.connect(self._on_db_create_requested)
        self.coherence_panel.selection_changed.connect(self._on_table_ref_selection)
        # The DDL Explorer's object tree rides in its own hidden tab (spec
        # §18.1), revealed together with the center DDL Explorer tab by the
        # Database > "DDL Explorer" toggle (mirrors the coherence tab).
        self.ddl_browser_panel = BrowserPanel()
        self.ddl_browser_tab_index = self.left_tabs.addTab(
            self.ddl_browser_panel, "DDL Objects"
        )
        self.left_tabs.setTabVisible(self.ddl_browser_tab_index, False)
        self.ddl_browser_panel.navigate_requested.connect(
            self._on_ddl_navigate_requested
        )
        # Right-click ▸ Edit… opens/focuses the editable DDL object tab
        # (spec §18.5, D1 entry point 1).
        self.ddl_browser_panel.edit_requested.connect(self._on_ddl_edit_requested)
        # Right-click ▸ Check Out for Versioning -- the project-aware second
        # variant of the same gesture (spec §18.2).
        self.ddl_browser_panel.checkout_requested.connect(self._on_ddl_checkout_requested)
        # Click on a Tables-branch table node populates the shared Properties
        # panel (spec §18.1, 2026-08-05) -- the same panel instance the
        # XML/XSD tree's own node-click already drives (_on_tree_selection_changed).
        self.ddl_browser_panel.table_selected.connect(self._on_ddl_table_selected)
        self.ddl_browser_panel.add_trigger_requested.connect(
            self._on_ddl_add_trigger_requested
        )
        self.ddl_browser_panel.new_routine_requested.connect(
            self._on_ddl_new_routine_requested
        )
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
        self.center_stage.xsd_close_requested.connect(self._on_xsd_close_requested)
        self.center_stage.ddl_explorer_visibility_changed.connect(
            self._on_ddl_explorer_visibility_changed
        )
        self.center_stage.ddl_object_close_requested.connect(
            self._on_ddl_object_close_requested
        )
        # DDL Explorer's read-only buffer's own right-click ▸ Edit… (spec
        # §18.5, D1 entry point 2) -- same target handler as BrowserPanel's
        # tree entry point.
        self.center_stage.ddl_editor_panel.edit_requested.connect(
            self._on_ddl_edit_requested
        )
        self.center_stage.ddl_editor_panel.checkout_requested.connect(
            self._on_ddl_checkout_requested
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
        self._find_all_target = "raw"
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
        self.center_stage.xml_editor.goto_xsd_requested.connect(self._goto_xsd)
        # The live CodeEditorDialog (kept referenced so it is not GC'd while
        # shown). MainWindow owns its lifecycle + the write-back.
        self._code_editor_dialog: CodeEditorDialog | None = None

        # Permanent status-bar mode indicator (Editing vs Caption Mode).
        self._mode_label = QLabel("Editing Mode")
        self.statusBar().addPermanentWidget(self._mode_label)

        if self._debug_log_path is not None:
            self._debug_label = QLabel("DEBUG")
            self._debug_label.setStyleSheet(
                "QLabel { color: white; background: #b33; padding: 1px 6px;"
                " border-radius: 3px; font-weight: bold; }"
            )
            self.statusBar().addPermanentWidget(self._debug_label)
            self.statusBar().showMessage(
                f"Debug logging: {self._debug_log_path}", 10000
            )

        self.properties_panel = PropertiesPanel(xml_editor=self.center_stage.xml_editor)
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setObjectName("properties_dock")
        self.properties_dock.setWidget(self.properties_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

        self._current_project = None
        self._current_project_path = None
        self._current_diff_target_project = None
        self._current_diff_target_path = None

        # Local DDL-versioning project state (spec §18.2) -- deliberately
        # separate from _current_project (the open .pgtp): a project here is
        # a plain chosen FOLDER, not necessarily related to any .pgtp at all.
        self._ddl_project_folder: Path | None = None
        self._ddl_project_settings: ProjectSettings | None = None
        # Top-of-§18 tier/capability probe result -- refreshed automatically
        # whenever a project is opened/created, and (later) on demand by the
        # not-yet-built Project Status screen via refresh_project_capability_status().
        # None until the first probe completes for the currently-open project.
        self._ddl_project_capability_status: ProjectCapabilityStatus | None = None
        # BUG-030: last target-connection reachability probe result -- None
        # means "the last probe succeeded" (or nothing to probe / not probed
        # yet), a string is the failure text `test_connection` reported. The
        # Quality node in §18.8's diagram reads this instead of assuming a
        # configured profile is a reachable one. Deliberately optimistic
        # before the first result lands so a healthy target never flashes red.
        self._ddl_target_probe_error: str | None = None
        # Injectable seam (mirrors _fetch_db_schema) -- tests patch this to a
        # canned SandboxCapabilities so no real connection is ever opened.
        self._probe_sandbox_capabilities = sandbox_probe
        #: §18.5 D2/D3a/D4: the one owner of at most one `SandboxSession` for
        #: the open project. Every `db/sandbox.py` entry point on it is an
        #: injected seam, kept at production defaults here EXCEPT `prober`,
        #: which is routed through this window's own already-injectable
        #: `_probe_sandbox_capabilities` so the whole window probes through one
        #: seam. Public attribute so tests can replace its seams (and its
        #: `_run_async`) wholesale.
        self.sandbox_controller = SandboxController(
            self,
            confirm_destructive=self._confirm_destructive_sandbox_operation,
            prober=lambda params: self._probe_sandbox_capabilities(params),
        )
        self.sandbox_controller.session_changed.connect(self._on_sandbox_session_changed)
        self.sandbox_controller.operation_finished.connect(
            self._on_sandbox_operation_finished
        )
        #: §18.5 D4: `() -> SandboxSession | None`. The ONE attribute the
        #: sandbox lane repoints -- aimed at the controller's `session`
        #: accessor, so "is there a session?" has exactly one answer.
        #: Everything console-related asks `_sandbox_console_available()`,
        #: which asks this. None (or a None return) means the console is
        #: ABSENT -- never present-but-refusing.
        self._sandbox_session_provider = lambda: self.sandbox_controller.session
        #: Database ▸ Sandbox SQL Console… -- created hidden, shown ONLY by
        #: `_refresh_sandbox_console_affordances`. Initialised here because
        #: `_build_database_menu` (called from `_build_menu_bar` below) assigns
        #: it, and the refresh may run before that on an early call path.
        self._sandbox_console_action = None
        #: The §18.5 D3a Check gesture and the two session gestures, all
        #: VISIBILITY-managed (carve-out 2: absent, never disabled). Same
        #: before-`_build_menu_bar` initialisation reason as above.
        self._sandbox_check_action = None
        self._open_sandbox_session_action = None
        self._close_sandbox_session_action = None

        # Document dirty-state tracking. `_loading` guards programmatic
        # setPlainText calls (load/revert/close) so they don't spuriously
        # mark the buffer dirty.
        self._dirty = False
        self._loading = False
        self.center_stage.xml_editor.textChanged.connect(self._on_editor_text_changed)

        # Document-level snapshot history (Sub-project C), independent of the
        # editor's per-keystroke undo. `_restoring` guards the guarded setter
        # so an undo/redo/jump restore is never recorded as a new snapshot.
        self._history = SnapshotHistory(10)
        self._restoring = False
        self._snapshot_timer = QTimer(self)
        self._snapshot_timer.setSingleShot(True)
        self._snapshot_timer.setInterval(400)
        self._snapshot_timer.timeout.connect(self._capture_snapshot_now)
        self._undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self._undo_shortcut.activated.connect(self._undo)
        self._redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        self._redo_shortcut.activated.connect(self._redo)
        # When the Raw XML editor has focus its native undo would shadow the
        # window shortcuts; the editor consumes Ctrl+Z/Ctrl+Y in keyPressEvent
        # and routes them here instead. Both paths call the same _undo/_redo,
        # and the focused editor consumes the key so the window shortcut does
        # not also fire (no double-undo). (Sub-project C, C1.)
        self.center_stage.xml_editor.undo_requested.connect(self._undo)
        self.center_stage.xml_editor.redo_requested.connect(self._redo)

        # Edit XSD tab (spec §11): dirty tracking + its own undo/redo routing.
        # The XSD tab has no snapshot history -- it relies solely on the
        # editor's native undo, so its Ctrl+Z/Ctrl+Y re-emission is routed
        # straight back into the editor rather than through _undo/_redo.
        self._xsd_dirty = False
        self._xsd_loading = False
        # Which schema the shared Edit-XSD tab currently holds: "curated"
        # (Schema ▸ Edit XSD) or "learned" (Schema ▸ Edit AutoXSD). Save /
        # Verify / Export / Import all act on the active mode (spec §11).
        self._xsd_mode = "curated"
        stage = self.center_stage
        stage.xsd_editor.textChanged.connect(self._on_xsd_text_changed)
        stage.xsd_editor.undo_requested.connect(stage.xsd_editor.undo)
        stage.xsd_editor.redo_requested.connect(stage.xsd_editor.redo)
        stage.xsd_find_replace_bar.set_on_status(self.statusBar().showMessage)
        stage.xsd_find_replace_bar.set_on_find_all(
            lambda term: self._populate_find_all_results(term, target="xsd")
        )
        stage.xsd_find_replace_bar.set_on_stop_find_all(self._stop_find_all)

        self._build_menu_bar()

        #: The narrow contract every collaborator object gets instead of this
        #: window (see `ui/ui_shell.py`). Built after the menu bar so
        #: `_light_theme_action` exists, but every field is late-bound anyway:
        #: they are bound methods that resolve host state at CALL time, which
        #: is what keeps post-construction seam injection
        #: (`window._run_async = ...`) working for collaborators too.
        self._shell = UiShell(
            window=self,
            stage=self.center_stage,
            audit=self.audit_panel,
            status=self._shell_status,
            settings=self._settings,
            run_async=self._shell_run_async,
            default_dir=self._dialog_default_dir,
            reveal_left_panel=self._reveal_left_panel,
            set_left_panel_visible=self._set_left_panel_visible,
            reveal_raw_xml=self._reveal_raw_xml_tab,
            is_light_theme=self._is_light_theme,
        )

        # Customizable icon bar (Sub-project E), owned by ToolbarController.
        # Constructed LAST of the collaborators and built here because `build`
        # walks the FINISHED menu bar to derive the command universe (BUG-027).
        self._toolbar_ui = ToolbarController(self._shell, parent=self)
        self._toolbar_ui.build(self.menuBar(), self.addToolBar)

        # Restore persisted window geometry/dock state and theme (Sub-project D).
        # Done after docks/toolbars/menus exist so restoreState can match dock
        # object names and the theme action can be checked. A fresh settings
        # store has no keys, so the default resize(1400, 900) stands.
        self._restore_window_state()
        self._restore_theme()

        # Curated-XSD feed (spec §11): bootstrap once if curated.xsd is
        # absent but the learning engine has state, then load whatever
        # curated.xsd now exists into the editor's completion/hover model.
        # Runs last so self.audit_panel already exists.
        self._ensure_curated_bootstrap()
        self._load_curated_schema()

    def _load_curated_schema(self) -> bool:
        """Parse curated.xsd and feed completion/hover from it — the SOLE
        schema source (spec §11). On parse failure the last good in-memory
        schema stays live; returns False. Missing file → False, silent."""
        path = curated_xsd_path(self._schema_storage_dir)
        if not path.exists():
            return False
        try:
            schema = load_curated(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, XsdLoadError) as exc:
            self.audit_panel.addItem(
                f"[Schema] Curated XSD has XML errors: {exc} — keeping last good schema"
            )
            return False
        self._curated_schema = schema
        self.center_stage.xml_editor.set_schema_model(schema.model)
        self.properties_panel.set_schema_model(schema.model)
        return True

    def _ensure_curated_bootstrap(self) -> None:
        """One-time seed of the user's curated.xsd when it is absent — never
        overwrites an existing file (curated.xsd is hand-owned, spec §11).
        Prefers copying the schema bundled with the app (Curated v1.2); falls
        back to generating one from the learning engine's state only when no
        bundled resource is present."""
        curated = curated_xsd_path(self._schema_storage_dir)
        if curated.exists():
            return

        bundled = bundled_curated_xsd_text()
        if bundled is not None:
            try:
                curated.parent.mkdir(parents=True, exist_ok=True)
                curated.write_text(bundled, encoding="utf-8")
            except OSError as exc:
                self.audit_panel.addItem(f"[Schema] Could not seed curated.xsd: {exc}")
                return
            self.audit_panel.addItem(
                f"[Schema] Seeded curated.xsd from the bundled schema "
                f"(v{CURATED_BUNDLED_VERSION})"
            )
            return

        # Fallback: no bundled resource — generate from the learned model.
        model_path = schema_model_path(self._schema_storage_dir)
        if not model_path.exists():
            return
        try:
            model = Model.load(model_path)
            curated.parent.mkdir(parents=True, exist_ok=True)
            curated.write_text(generate_curated_xsd(model), encoding="utf-8")
        except Exception as exc:
            self.audit_panel.addItem(f"[Schema] Could not bootstrap curated.xsd: {exc}")
            return
        self.audit_panel.addItem(
            "[Schema] Bootstrapped curated.xsd from the learned schema (labels preserved)"
        )

    # -- Edit XSD tab (spec §11) ---------------------------------------------

    def _on_xsd_text_changed(self) -> None:
        # A theme toggle's rehighlight() also fires textChanged with no text
        # actually changed; ignored via is_applying_theme() (see
        # XmlEditor.apply_theme_colors).
        if self._xsd_loading or self.center_stage.xsd_editor.is_applying_theme():
            return
        self._set_xsd_dirty(True)

    def _set_xsd_dirty(self, dirty: bool) -> None:
        self._xsd_dirty = dirty
        stage = self.center_stage
        base = self._xsd_tab_label(self._xsd_mode)
        stage.setTabText(stage.xsd_tab_index, f"{base} *" if dirty else base)

    @staticmethod
    def _xsd_tab_label(mode: str) -> str:
        """Tab title for the Edit-XSD tab in each mode (spec §11)."""
        return "Edit AutoXSD" if mode == "learned" else "Edit XSD"

    def _xsd_path_for_mode(self, mode: str) -> Path:
        """The on-disk file backing each Edit-XSD mode: the hand-curated
        schema, or the auto-learned discovery artifact (spec §11)."""
        if mode == "learned":
            return learned_xsd_path(self._schema_storage_dir)
        return curated_xsd_path(self._schema_storage_dir)

    def _open_edit_xsd(self) -> None:
        """Schema ▸ Edit XSD: open the hand-curated schema in the XSD tab."""
        self._open_xsd("curated")

    def _open_edit_auto_xsd(self) -> None:
        """Schema ▸ Edit AutoXSD: open the auto-learned schema (learned.xsd)
        in the same tab so it can be analysed against the curated one."""
        self._open_xsd("learned")

    def _open_xsd(self, mode: str) -> None:
        """Load the XSD file for `mode` ("curated" | "learned") into the shared
        Edit-XSD tab and switch to it. Unsaved edits in the current mode are
        preserved when re-opening the same mode; switching to the other mode
        prompts save/discard/cancel first (spec §11)."""
        stage = self.center_stage
        if self._xsd_dirty and mode != self._xsd_mode:
            choice = self._confirm_close_xsd()
            if choice == "cancel":
                return
            if choice == "save":
                self._save_xsd()
                if self._xsd_dirty:
                    # Save failed (e.g. disk error): don't drop the edits.
                    return
        elif self._xsd_dirty and mode == self._xsd_mode:
            # Same schema, unsaved edits: keep them; just reveal the tab.
            stage.show_edit_xsd()
            return

        path = self._xsd_path_for_mode(mode)
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                self.statusBar().showMessage(f"Could not read {path.name}: {exc}", 5000)
                return
        else:
            text = _EMPTY_XSD_SKELETON
            if mode == "learned":
                self.statusBar().showMessage(
                    "No auto-learned schema yet — open a .pgtp to build it.", 5000
                )
        self._xsd_mode = mode
        self._xsd_loading = True
        try:
            stage.xsd_editor.setPlainText(text)
        finally:
            self._xsd_loading = False
        self._set_xsd_dirty(False)
        stage.show_edit_xsd()

    def _on_xsd_close_requested(self) -> None:
        """Edit XSD tab ✕ clicked. Reuses `_confirm_close_xsd`'s save/discard/
        cancel prompt (same pattern as `_open_xsd`/`closeEvent`) when dirty;
        never invents a second confirmation path."""
        if self._xsd_dirty:
            choice = self._confirm_close_xsd()
            if choice == "cancel":
                return
            if choice == "save":
                self._save_xsd()
                if self._xsd_dirty:
                    # Save failed (e.g. disk error): don't drop the edits.
                    return
        self.center_stage.hide_edit_xsd()

    def _goto_xsd_at_cursor(self) -> None:
        """Ctrl+L / context-menu "Go To XSD": resolve the caret in the Raw
        XML editor and jump to its curated XSD definition."""
        editor = self.center_stage.xml_editor
        if editor.schema_model() is None or not editor.request_goto_xsd():
            self.statusBar().showMessage(
                "Place the cursor inside an element in the Raw XML first.", 5000
            )

    def _goto_xsd(self, tag_chain: str, attr: str) -> None:
        """Open the Edit XSD tab and select the attribute's definition;
        fall back to the element's type definition; else status message.
        Lines come from the last successful parse -- navigation targets the
        saved file content."""
        schema = self._curated_schema
        if schema is None:
            self.statusBar().showMessage(
                "No curated XSD loaded yet — Schema ▸ Edit XSD.", 5000
            )
            return
        line = schema.attribute_lines.get((tag_chain, attr))
        if line is None:
            line = schema.element_lines.get(tag_chain)
        if line is None:
            self.statusBar().showMessage(
                f"'{tag_chain}' is not in the curated XSD yet.", 5000
            )
            return
        self._open_edit_xsd()
        self.center_stage.xsd_editor.navigate_to_line(line)

    def _save_xsd(self) -> None:
        """Save the Edit-XSD tab to whichever schema it currently holds
        (curated or auto). The text is ALWAYS written (user text is never
        lost); a malformed file keeps the last good schema live. Saving the
        curated schema re-feeds completion; saving the auto schema does not
        (learned.xsd never feeds completion, spec §11)."""
        mode = self._xsd_mode
        path = self._xsd_path_for_mode(mode)
        text = self.center_stage.xsd_editor.toPlainText()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="")
        except OSError as exc:
            modals.QMessageBox.critical(self, "Save Failed", f"Could not save:\n\n{exc}")
            return
        self._set_xsd_dirty(False)
        self.statusBar().showMessage(f"Saved {path.name}", 5000)
        if mode == "curated":
            self._load_curated_schema()
        self._report_verify_issues(verify_curated(text))

    def _verify_xsd(self) -> None:
        """Schema ▸ Verify XSD: check dialect rules against whatever the user
        is currently looking at -- the Edit-XSD tab's live text when it has
        unsaved edits, otherwise the active mode's saved file on disk."""
        stage = self.center_stage
        if self._xsd_dirty:
            text = stage.xsd_editor.toPlainText()
        else:
            path = self._xsd_path_for_mode(self._xsd_mode)
            if not path.exists():
                self.statusBar().showMessage(
                    f"No {self._xsd_tab_label(self._xsd_mode)} file yet.", 5000
                )
                return
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                self.statusBar().showMessage(f"Could not read {path.name}: {exc}", 5000)
                return
        self._report_verify_issues(verify_curated(text))

    def _export_xsd(self) -> None:
        """Schema ▸ Export XSD: copy the active mode's saved file to a chosen
        destination (curated.xsd or learned.xsd, per the open tab)."""
        mode = self._xsd_mode
        source = self._xsd_path_for_mode(mode)
        if not source.exists():
            self.statusBar().showMessage(
                f"No {self._xsd_tab_label(mode)} file yet.", 5000
            )
            return
        if self._xsd_dirty:
            self.statusBar().showMessage(
                "The XSD tab has unsaved changes — save it first (Ctrl+S).", 5000
            )
            return
        dest, _filter = modals.QFileDialog.getSaveFileName(
            self,
            "Export XSD",
            str(Path(self._dialog_default_dir()) / source.name) if self._dialog_default_dir() else source.name,
            "XSD files (*.xsd)",
        )
        if not dest:
            return
        try:
            shutil.copyfile(source, dest)
        except OSError as exc:
            modals.QMessageBox.critical(self, "Export Failed", f"Could not export:\n\n{exc}")
            return
        self.statusBar().showMessage(f"Exported to {Path(dest).name}", 5000)

    def _import_xsd(self) -> None:
        """Schema ▸ Import XSD: replace the active mode's file with an external
        one -- verify first (hard refuse malformed XML; dialect warnings
        importable), back up, replace, then re-feed completion when the active
        mode is curated (spec §11)."""
        mode = self._xsd_mode
        source, _filter = modals.QFileDialog.getOpenFileName(
            self, "Import XSD", self._dialog_default_dir(), "XSD files (*.xsd);;All files (*)"
        )
        if not source:
            return
        try:
            text = Path(source).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            modals.QMessageBox.critical(self, "Import Failed", f"Could not read:\n\n{exc}")
            return
        issues = verify_curated(text)
        if any(issue.fatal for issue in issues):
            modals.QMessageBox.critical(
                self, "Import Refused",
                "The file is not well-formed XML:\n\n" + issues[0].message,
            )
            return
        if issues:
            answer = modals.QMessageBox.question(
                self, "Import With Warnings",
                f"The file has {len(issues)} dialect warning(s). Import anyway?",
                modals.QMessageBox.StandardButton.Yes | modals.QMessageBox.StandardButton.No,
            )
            if answer != modals.QMessageBox.StandardButton.Yes:
                return
        tab_was_dirty = self._xsd_dirty
        target = self._xsd_path_for_mode(mode)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.copy2(target, str(target) + ".bak")
            target.write_text(text, encoding="utf-8")
        except OSError as exc:
            modals.QMessageBox.critical(self, "Import Failed", f"Could not write:\n\n{exc}")
            return
        self._set_xsd_dirty(False)
        if mode == "curated":
            self._load_curated_schema()
        stage = self.center_stage
        if stage.xsd_editor.toPlainText():
            self._xsd_loading = True
            try:
                stage.xsd_editor.setPlainText(text)
            finally:
                self._xsd_loading = False
        label = self._xsd_tab_label(mode)
        notice = f"[Schema] Imported {label} from {Path(source).name}"
        if tab_was_dirty:
            notice += " (unsaved XSD tab edits were replaced)"
        self.audit_panel.addItem(notice)
        self._report_verify_issues(issues)

    def _report_verify_issues(self, issues) -> None:
        """Append Verify XSD results to the audit panel. Each issue line is
        clickable -- routed through _on_audit_item_clicked's existing
        (line, target) UserRole/UserRole+1 convention (see _find_all_step),
        with target "xsd" so the click opens the Edit XSD tab at that line.
        The active XSD mode is stashed in UserRole+2 so the click re-opens the
        schema the issue was found in (curated vs auto)."""
        if not issues:
            self.audit_panel.addItem("[Schema] VERIFY: no issues found.")
            return
        for issue in issues:
            item = QListWidgetItem(f"[Schema] VERIFY line {issue.line}: {issue.message}")
            item.setData(Qt.ItemDataRole.UserRole, issue.line)
            item.setData(Qt.ItemDataRole.UserRole + 1, "xsd")
            item.setData(Qt.ItemDataRole.UserRole + 2, self._xsd_mode)
            self.audit_panel.addItem(item)

    def _save_active_tab(self) -> None:
        """Ctrl+S / File ▸ Save routes to the active center-stage tab."""
        stage = self.center_stage
        if stage.currentIndex() == stage.xsd_tab_index:
            self._save_xsd()
            return
        panel = stage.active_ddl_object_panel()
        if panel is not None:
            self._save_ddl_object_editor(panel)
            return
        self._save_project()

    def _active_find_bar(self):
        """The FindReplaceBar of the active editor tab; defaults to the Raw
        XML bar (revealing that tab) when no editor tab is active."""
        stage = self.center_stage
        if stage.currentIndex() == stage.xsd_tab_index:
            return stage.xsd_find_replace_bar
        if stage.currentIndex() == stage.ddl_tab_index:
            # The DDL Explorer buffer has its own bar (spec §18.1, per-tab
            # document routing) -- without this branch Ctrl+F on the DDL tab
            # used to bounce the user back to Raw XML.
            return stage.ddl_editor_panel.find_replace_bar
        panel = stage.active_ddl_object_panel()
        if panel is not None:
            # The editable object tab's own bar (spec §18.5) -- Replace is
            # LIVE here, unlike the read-only DDL Explorer above.
            return panel.find_replace_bar
        self._reveal_raw_xml_tab()
        return stage.find_replace_bar

    def _active_bookmark_editor(self):
        """The editor the Bookmarks menu/shortcuts act on: whichever editor
        tab is active (§8). Every editor carries the same bookmark API from
        the shared gutter base (`ui/editor_gutter.py`), so this dispatch is
        the only thing needed to make the menu follow focus -- it mirrors
        `_active_find_bar`'s per-tab routing.

        Unlike `_active_find_bar` this deliberately does NOT reveal the Raw
        XML tab as a side effect: toggling a bookmark must never yank the
        user to a different tab. Any non-editor tab falls back to the Raw XML
        editor, where bookmarks lived before the DDL Explorer existed.
        """
        stage = self.center_stage
        if stage.currentIndex() == stage.xsd_tab_index:
            return stage.xsd_editor
        if stage.currentIndex() == stage.ddl_tab_index:
            return stage.ddl_editor_panel.editor
        panel = stage.active_ddl_object_panel()
        if panel is not None:
            return panel.editor
        return stage.xml_editor

    def _confirm_close_xsd(self) -> str:
        """Ask the user how to resolve unsaved Edit XSD changes before
        closing. Returns "save", "discard", or "cancel". Split out (mirroring
        `_confirm_close`) so tests can monkeypatch it instead of ever driving
        a real modal."""
        result = modals.QMessageBox.question(
            self,
            "Unsaved Changes",
            "The XSD has unsaved changes. Save before closing?",
            modals.QMessageBox.StandardButton.Save
            | modals.QMessageBox.StandardButton.Discard
            | modals.QMessageBox.StandardButton.Cancel,
        )
        if result == modals.QMessageBox.StandardButton.Save:
            return "save"
        if result == modals.QMessageBox.StandardButton.Discard:
            return "discard"
        return "cancel"

    def _restore_window_state(self):
        geometry = self._settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        window_state = self._settings.value("windowState")
        if window_state is not None:
            self.restoreState(window_state)

    def _restore_theme(self):
        light = self._settings.value("lightTheme", False, type=bool)
        self._light_theme_action.setChecked(light)
        apply_theme(QApplication.instance(), light)
        # Toolbar was built under the native/default palette; re-tint its
        # icons to whichever theme was just applied (BUG-004: the "off"
        # state is now a real, explicit dark palette, not a native/OS
        # passthrough) so they stay legible.
        self._toolbar_ui.refresh_icons()

    def closeEvent(self, event):
        # Edit XSD tab (spec §11): unsaved XSD edits get their own
        # save/discard/cancel prompt, distinct from the project's (File >
        # Close handles that one) since the XSD tab has no Close command.
        if self._xsd_dirty:
            confirm = self._confirm_close_xsd()
            if confirm == "cancel":
                event.ignore()
                return
            if confirm == "save":
                self._save_xsd()
                if self._xsd_dirty:
                    # Save failed (e.g. disk error) -- don't discard changes.
                    event.ignore()
                    return
        # Persist window geometry/dock state on close (Sub-project D). No modal
        # prompt here -- File > Close handles the unsaved-changes prompt.
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())
        self._settings.sync()
        super().closeEvent(event)

    def _on_light_theme_toggled(self, checked):
        apply_theme(QApplication.instance(), checked)
        self._settings.setValue("lightTheme", checked)
        # The palette flipped -- re-tint the toolbar icons so they stay legible.
        self._toolbar_ui.refresh_icons()

    def _not_implemented(self, label):
        self.statusBar().showMessage(f"Not yet implemented: {label}", 5000)

    # -- Document state: dirty tracking + window title -----------------------

    def _on_editor_text_changed(self) -> None:
        """Mark the buffer dirty when the user edits the Raw XML editor.
        Programmatic sets (load/revert/close) run under `_loading` and are
        ignored so they don't spuriously flag the document dirty. A theme
        toggle's rehighlight() also fires textChanged with no text actually
        changed; ignored via is_applying_theme()."""
        if self._loading or self.center_stage.xml_editor.is_applying_theme():
            return
        self._set_dirty(True)
        # Debounce a document-level snapshot capture (Sub-project C). We start
        # the timer even during a `_restoring` apply; the fire-time guards
        # (`_restoring`/`_loading` and the head-coalesce check) ensure a restore
        # never records a spurious snapshot.
        self._snapshot_timer.start()

    def _capture_snapshot_now(self) -> None:
        """Fire-time handler for the debounce timer (called directly in tests).
        Push the current editor text as a snapshot unless we're restoring or
        loading, or the text already matches the history head (coalesced)."""
        if self._restoring or self._loading:
            return
        self._history.push(self.center_stage.xml_editor.toPlainText(), "Edit")

    # -- Snapshot history: undo/redo/jump (Sub-project C) --------------------

    def _apply_history_text(self, text: str) -> None:
        """Set the editor to `text` without recording a new snapshot."""
        self._restoring = True
        try:
            self.center_stage.xml_editor.setPlainText(text)
        finally:
            self._restoring = False

    def _undo(self) -> None:
        _log.info("history: undo")
        text = self._history.undo()
        if text is not None:
            self._apply_history_text(text)

    def _redo(self) -> None:
        _log.info("history: redo")
        text = self._history.redo()
        if text is not None:
            self._apply_history_text(text)

    def _history_entries(self):
        """Edit snapshots newest-first, for the jump-list popup (test seam).

        Uses ``edit_entries`` so Open/Revert baselines are not shown -- opening
        a file is not an undoable item; the baseline is only the floor undo
        returns to."""
        return list(reversed(self._history.edit_entries()))

    def _history_jump(self, index) -> None:
        text = self._history.jump_to(index)
        if text is not None:
            self._apply_history_text(text)

    def _open_history_jump_list(self) -> None:
        """Show a small non-modal popup listing snapshots newest-first;
        selecting one jumps to it. Never `.exec()`'d (see the test seam)."""
        dialog = QDialog(self)
        dialog.setWindowTitle("History")
        layout = QVBoxLayout(dialog)
        listw = QListWidget(dialog)
        layout.addWidget(listw)
        entries = self._history_entries()
        if not entries:
            placeholder = QListWidgetItem("(no edits to undo)")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            listw.addItem(placeholder)
        for index, label in entries:
            item = QListWidgetItem(label or f"Snapshot {index}")
            item.setData(Qt.ItemDataRole.UserRole, index)
            listw.addItem(item)

        def _on_activated(item):
            self._history_jump(item.data(Qt.ItemDataRole.UserRole))
            dialog.close()

        listw.itemActivated.connect(_on_activated)
        listw.itemClicked.connect(_on_activated)
        self._history_dialog = dialog
        dialog.show()

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._update_title()

    def _update_title(self) -> None:
        title = "PGTP Editor"
        if self._ddl_project_folder is not None:
            title = f"{title} — Project: {self._ddl_project_folder.name}"
        if self._current_project_path:
            title = f"{title} - {Path(self._current_project_path).name}"
        if self._dirty:
            title = f"{title} *"
        self.setWindowTitle(title)

    def _dialog_default_dir(self) -> str:
        """The directory an Open/Save dialog for a project file (`.pgtp`,
        XSD import/export, a diff/merge comparison target) should default
        to: the active §18.2 local project's folder, or '' (Qt's own
        last-used-directory default) when no project is open."""
        return str(self._ddl_project_folder) if self._ddl_project_folder is not None else ""

    # -- UiShell accessors ---------------------------------------------------
    # The host side of `ui/ui_shell.py`. Each is a thin, late-binding forwarder
    # so a collaborator constructed early in __init__ still observes the
    # finished window -- and, critically, so a seam a test replaces AFTER
    # construction (`window._run_async = _sync_run`) is honoured.

    def _shell_status(self, *args, **kwargs) -> None:
        """`UiShell.status` -- forwards to the status bar, resolved at call
        time rather than captured, matching `showMessage(text[, timeout])`."""
        self.statusBar().showMessage(*args, **kwargs)

    def _shell_run_async(self, *args, **kwargs):
        """`UiShell.run_async` trampoline. Reads `self._run_async` at CALL time,
        which is the whole point: the suite injects a synchronous stand-in by
        assigning `window._run_async` after the window is built, and a shell
        that had captured the original would silently keep using the threadpool
        (hanging the test, or asserting on results that never arrived)."""
        return self._run_async(*args, **kwargs)

    def _reveal_left_panel(self, panel) -> None:
        """`UiShell.reveal_left_panel` -- show a left-dock tab and focus it."""
        index = self.left_tabs.indexOf(panel)
        if index < 0:
            return
        self.left_tabs.setTabVisible(index, True)
        self.left_tabs.setCurrentWidget(panel)

    def _set_left_panel_visible(self, panel, visible: bool) -> None:
        """`UiShell.set_left_panel_visible` -- visibility only, no focus."""
        index = self.left_tabs.indexOf(panel)
        if index < 0:
            return
        self.left_tabs.setTabVisible(index, visible)

    def _is_light_theme(self) -> bool:
        """`UiShell.is_light_theme` -- the View ▸ Light Theme toggle's state."""
        return self._light_theme_action.isChecked()

    def _on_tree_selection_changed(self, node, kind):
        self.properties_panel.show_node(node, kind)

    def _on_table_ref_selection(self, node, kind):
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
        path, _filter = modals.QFileDialog.getOpenFileName(
            self, "Open PGTP Project", self._dialog_default_dir(), "PGTP files (*.pgtp)"
        )
        if not path:
            return
        if self._ddl_project_folder is None:
            self._prompt_pgtp_open_mode(path)
        else:
            # A project is already active -- the user already committed to
            # project mode; just open (existing linking logic applies
            # silently, exactly as it does for any subsequent open).
            self.open_project_file(path)

    def _prompt_pgtp_open_mode(self, path) -> None:
        """The first time a `.pgtp` is opened with no project active, ask how
        to work with it (§18.2): start a **New Project** around it, attach it
        to an existing project via **Open Project**, or **Edit Standalone**
        (today's plain behavior -- no project, no linking, unaffected). If
        the chooser is dismissed without a button (e.g. the window close
        box), defaults to Standalone -- the safe, non-destructive choice."""
        box = modals.QMessageBox(self)
        box.setWindowTitle("Open .pgtp")
        box.setText("How do you want to work with this file?")
        new_button = box.addButton("New Project…", modals.QMessageBox.ButtonRole.ActionRole)
        open_button = box.addButton("Open Project…", modals.QMessageBox.ButtonRole.ActionRole)
        box.addButton("Edit Standalone", modals.QMessageBox.ButtonRole.ActionRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is new_button:
            self._new_ddl_project(on_ready=lambda: self.open_project_file(path))
        elif clicked is open_button:
            self._open_ddl_project(on_ready=lambda: self.open_project_file(path))
        else:
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
        path = self._resolve_pgtp_project_path(path)
        _log.info("file: open %s", path)
        name = Path(path).name
        try:
            message = f"Opening {name} ({format_size(os.path.getsize(path))})…"
        except OSError:
            # Never fail the open over a stat hiccup; just drop the size.
            message = f"Opening {name}…"

        parse_error = None
        with busy_status(self.statusBar(), message):
            try:
                project = load_project(path)
            except PgtpParseError as exc:
                parse_error = exc
            else:
                self.project_tree.populate_from_project(project)
                self._current_project = project
                # Normalize to str so downstream string ops (e.g. the ".bak"
                # path concatenation in _revert_project / _write_project_text)
                # never hit a TypeError when a caller passes a pathlib.Path
                # instead of the QFileDialog string.
                self._current_project_path = str(path)
                self._link_pgtp_to_project_if_needed()
                raw_text = self._read_raw_text(path)
                if raw_text is not None:
                    self._loading = True
                    try:
                        self.center_stage.xml_editor.setPlainText(raw_text)
                    finally:
                        self._loading = False
                self._set_dirty(False)
                # A newly-opened project is a fresh document: drop the previous
                # project's snapshots so undo never crosses between documents,
                # then seed the history with the freshly-loaded text.
                self._history.clear()
                self._history.push(
                    self.center_stage.xml_editor.toPlainText(),
                    f"Opened {name}",
                    baseline=True,
                )
                # Schema enrichment is the slowest part of open; keep it inside
                # the busy block so the hourglass covers it.
                self._enrich_schema_from_file(path)

        # Cursor restored here (busy_status __exit__), BEFORE any dialog.
        if parse_error is not None:
            self._handle_parse_failure(path, parse_error)
            return
        self.statusBar().showMessage(f"Opened: {path}", 5000)

    def _enrich_schema_from_file(self, path):
        try:
            model_path = schema_model_path(self._schema_storage_dir)
            xsd_path = learned_xsd_path(self._schema_storage_dir)
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
            _log.info("schema: enriched %s", path)

            self._ensure_curated_bootstrap()
            if self._curated_schema is None:
                self._load_curated_schema()
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

    def _populate_find_all_results(self, term: str, target: str = "raw") -> None:
        """Start a streaming Find All: results are appended to the Audit panel
        a batch at a time on a 0ms QTimer, yielding to the event loop between
        batches so the UI stays responsive and Stop takes effect promptly.

        `target` selects which editor tab the search runs over -- "raw" (the
        Raw XML tab, the default) or "xsd" (the Edit XSD tab) -- and is
        stashed with each result so clicking it navigates the right editor.
        """
        self._cancel_find_all_timer()
        self._clear_find_results()
        self._find_all_term = term
        self._find_all_target = target
        self._find_all_count = 0
        self._find_all_stop = False
        editor = self.center_stage.xsd_editor if target == "xsd" else self.center_stage.xml_editor
        bar = self.center_stage.xsd_find_replace_bar if target == "xsd" else self.center_stage.find_replace_bar
        text = editor.toPlainText()
        self._find_all_iter = search.iter_matches(text, term)
        bar.set_find_all_running(True)
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
            item.setData(Qt.ItemDataRole.UserRole + 1, self._find_all_target)
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
        bar = (
            self.center_stage.xsd_find_replace_bar
            if self._find_all_target == "xsd"
            else self.center_stage.find_replace_bar
        )
        bar.set_find_all_running(False)
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
        name = (
            Path(self._current_project_path).name
            if self._current_project_path else "project"
        )
        self._clear_validation_results()
        with busy_status(self.statusBar(), f"Validating {name}…"):
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
        target = item.data(Qt.ItemDataRole.UserRole + 1)
        if target == "xsd":
            # Verify XSD lines carry the mode they were found in (UserRole+2);
            # re-open that schema so the line number matches the right file
            # (same load-from-disk-if-clean behavior as Schema > Edit XSD /
            # Edit AutoXSD). Find-All-in-XSD lines have no mode tag -- they
            # target whatever the tab already shows, so just reveal it.
            mode = item.data(Qt.ItemDataRole.UserRole + 2)
            if mode:
                self._open_xsd(mode)
            else:
                self.center_stage.show_edit_xsd()
            self.center_stage.xsd_editor.navigate_to_line(line)
            return
        if isinstance(target, tuple):
            # §18.5 D3a: a `[Check]` finding carries the object's
            # `DdlObjectRef.key` (a tuple) -- focus that tab and place the
            # caret there. Never falls through to Raw XML: that would navigate
            # a different document entirely.
            self._navigate_to_ddl_object(target, line)
            return
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
        modals.QMessageBox.critical(
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
        # Seed the snapshot history with the as-loaded (unparsed) text so undo
        # after fixing the broken file has a base to return to, mirroring a
        # normal open. Pushed after the `_loading` block so it reflects the
        # shown text.
        self._history.push(
            self.center_stage.xml_editor.toPlainText(),
            f"Opened (unparsed) {Path(path).name}",
            baseline=True,
        )
        if exc.line is not None:
            self.center_stage.xml_editor.highlight_error_line(exc.line)
        self.center_stage.set_raw_xml_tab_visible(True)
        self._raw_xml_panel_action.setChecked(True)
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)

    def _reparse_raw_xml(self):
        text = self.center_stage.xml_editor.toPlainText()
        parse_error = None
        with busy_status(self.statusBar(), "Reparsing…"):
            try:
                project = load_project_from_text(text, source_description="<editor>")
            except PgtpParseError as exc:
                parse_error = exc
            else:
                # SUCCESS: rebuild tree + adopt the new model so click-sync realigns.
                self.project_tree.populate_from_project(project)
                self._current_project = project
                # Properties has no valid selection against the freshly rebuilt
                # tree (populate_from_project cleared it); show the empty state
                # until the user clicks again. show_node(None, None) resets it.
                self.properties_panel.show_node(None, None)
        # Cursor restored before any failure dialog.
        if parse_error is not None:
            self._handle_reparse_failure(parse_error)
            return
        self.statusBar().showMessage("Reparsed raw XML into tree", 5000)
        self._refresh_db_check_if_open(project)

    def _refresh_db_check_if_open(self, project) -> None:
        """After a reparse, rebuild the coherence tree against the CACHED
        schema (no re-query) so the open view reflects the edited XML. No-op
        unless the coherence tab is visible and a run already happened.
        `project` is the freshly parsed model from _reparse_raw_xml."""
        if (
            not self.left_tabs.isTabVisible(self.coherence_tab_index)
            or self._last_db_schema is None
        ):
            return
        self._populate_db_check(
            self._last_db_schema,
            project,
            self._last_db_summary or "",
        )
        self.statusBar().showMessage(
            "Database/XML Coherence refreshed against the last database snapshot.",
            4000,
        )

    def _handle_reparse_failure(self, exc: PgtpParseError) -> None:
        # Mirror the Tier-1 open-failure pattern (_handle_parse_failure), but
        # WITHOUT re-reading a file and WITHOUT touching the existing model or
        # tree: the last-good state must survive a failed reparse so the user
        # can fix the XML and try again.
        modals.QMessageBox.critical(
            self,
            "Reparse Failed",
            f"Could not reparse the raw XML:\n\n{exc}",
        )
        if exc.line is not None:
            self.center_stage.xml_editor.highlight_error_line(exc.line)

    def _compare_merge_two_files(self):
        source = self._current_project
        if source is None:
            source_path, _filter = modals.QFileDialog.getOpenFileName(
                self, "Select Source Project", self._dialog_default_dir(), "PGTP files (*.pgtp)"
            )
            if not source_path:
                return
            try:
                source = load_project(source_path)
            except Exception as exc:
                modals.QMessageBox.critical(
                    self, "Failed to Open Source Project", f"Could not open '{source_path}':\n\n{exc}"
                )
                return

        target_path, _filter = modals.QFileDialog.getOpenFileName(
            self, "Select Target Project", self._dialog_default_dir(), "PGTP files (*.pgtp)"
        )
        if not target_path:
            return
        try:
            target = load_project(target_path)
        except Exception as exc:
            modals.QMessageBox.critical(
                self, "Failed to Open Target Project", f"Could not open '{target_path}':\n\n{exc}"
            )
            return

        self._current_diff_target_project = target
        self._current_diff_target_path = target_path
        differences = diff_project(source, target)
        self.center_stage.diff_merge_panel.show_differences(differences)
        self.center_stage.setCurrentIndex(self.center_stage.diff_merge_tab_index)

    def _compare_page_with(self, page_node):
        target_path, _filter = modals.QFileDialog.getOpenFileName(
            self, "Select Target Project", self._dialog_default_dir(), "PGTP files (*.pgtp)"
        )
        if not target_path:
            return
        try:
            target = load_project(target_path)
        except Exception as exc:
            modals.QMessageBox.critical(
                self, "Failed to Open Target Project", f"Could not open '{target_path}':\n\n{exc}"
            )
            return

        target_page = next((p for p in target.pages if p.file_name == page_node.file_name), None)
        if target_page is None:
            modals.QMessageBox.critical(
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
        target_path_str, _filter = modals.QFileDialog.getOpenFileName(
            self, "Select Target Project", self._dialog_default_dir(), "PGTP files (*.pgtp)"
        )
        if not target_path_str:
            return
        try:
            target = load_project(target_path_str)
        except Exception as exc:
            modals.QMessageBox.critical(
                self, "Failed to Open Target Project", f"Could not open '{target_path_str}':\n\n{exc}"
            )
            return

        result = resolve_path(target, source_path)
        if isinstance(result, ResolutionError):
            modals.QMessageBox.critical(self, "Detail Not Found", result.message)
            return

        self._current_diff_target_project = target
        self._current_diff_target_path = target_path_str
        differences = compare_block(detail_node, result, path=source_path, node_kind="detail")
        self.center_stage.diff_merge_panel.show_differences(differences)
        self.center_stage.setCurrentIndex(self.center_stage.diff_merge_tab_index)

    def _apply_changes_to_target(self):
        checked = self.center_stage.diff_merge_panel.checked_differences()
        if not checked:
            modals.QMessageBox.information(
                self, "Apply Changes to Target", "No differences are checked to apply."
            )
            return

        ambiguous = [d for d in checked if d.ambiguous]
        if ambiguous:
            details = "\n".join(
                f"- {'/'.join(d.path)} ({d.node_kind}/{d.attribute}: {d.kind})" for d in ambiguous
            )
            modals.QMessageBox.critical(
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
            modals.QMessageBox.critical(
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

        modals.QMessageBox.information(
            self,
            "Apply Changes to Target",
            f"Applied {len(checked)} change(s) to '{target_path}'.\nBackup saved to '{backup_path}'.",
        )
        self.open_project_file(target_path)

    def _write_project_text(self, path) -> None:
        """Write the Raw XML editor buffer verbatim to `path` as UTF-8. If
        `path` already exists, copy it to `path + '.bak'` first (same .bak
        convention as Apply-to-Target) -- **unless** `path` is a local
        §18.2 project's `.pgtp` working copy, where the working copy itself
        is the safety net and no `.bak` is written, exactly like `ddl/*.sql`
        (§18.2, "the .pgtp file becomes a first-class checked-out
        artifact"). Scoped precisely to that case: no-project-mode saves are
        completely unaffected."""
        _log.info("file: save %s", path)
        if Path(path).exists() and not self._is_ddl_project_pgtp_working_copy(path):
            shutil.copy2(path, str(path) + ".bak")
        Path(path).write_text(
            self.center_stage.xml_editor.toPlainText(), encoding="utf-8", newline=""
        )

    def _is_ddl_project_pgtp_working_copy(self, path) -> bool:
        if self._ddl_project_settings is None:
            return False
        working_copy_path = self._ddl_project_settings.pgtp.working_copy_path
        return working_copy_path is not None and str(path) == working_copy_path

    def _save_project(self) -> None:
        if not self._current_project_path:
            self._save_project_as()
            return
        try:
            self._write_project_text(self._current_project_path)
        except OSError as exc:
            modals.QMessageBox.critical(self, "Save Failed", f"Could not save:\n\n{exc}")
            return
        self._set_dirty(False)
        self.statusBar().showMessage(f"Saved {Path(self._current_project_path).name}", 5000)

    def _save_project_as(self) -> None:
        path, _filter = modals.QFileDialog.getSaveFileName(
            self, "Save Project As", self._dialog_default_dir(), "PGTP files (*.pgtp)"
        )
        if not path:
            return
        try:
            self._write_project_text(path)
        except OSError as exc:
            modals.QMessageBox.critical(self, "Save Failed", f"Could not save:\n\n{exc}")
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
        result = modals.QMessageBox.question(
            self,
            "Unsaved Changes",
            "The project has unsaved changes. Save before closing?",
            modals.QMessageBox.StandardButton.Save
            | modals.QMessageBox.StandardButton.Discard
            | modals.QMessageBox.StandardButton.Cancel,
        )
        if result == modals.QMessageBox.StandardButton.Save:
            return "save"
        if result == modals.QMessageBox.StandardButton.Discard:
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
            outcome = {"save": "saved", "discard": "discarded"}.get(confirm, confirm)
        else:
            confirm = "discard"
            outcome = "clean"

        if confirm == "cancel":
            _log.info("file: close outcome=cancelled")
            return
        if confirm == "save":
            self._save_project()
            if self._dirty:
                # Save was cancelled (e.g. Save-As dialog dismissed) --
                # don't discard the user's changes.
                _log.info("file: close outcome=cancelled")
                return

        self._loading = True
        try:
            self.center_stage.xml_editor.setPlainText("")
        finally:
            self._loading = False
        self.project_tree.clear()
        self._current_project = None
        self._current_project_path = None
        # Drop the closed document's snapshots so a later undo can't restore it
        # into the emptied editor.
        self._history.clear()
        self._set_dirty(False)
        # Coherence results are project-tied (BUG-011, §17): hide the tab,
        # clear the panel and drop the cached schema/summary so a later
        # reparse or rename re-run can't act on the closed project's stale
        # state. Only here on the committed-close path -- a cancelled close
        # (returns above) must leave the still-open project's tab alone, and
        # _revert_project keeps the project loaded so it doesn't tear down.
        self.left_tabs.setTabVisible(self.coherence_tab_index, False)
        self.coherence_panel.clear()
        if self._coherence_action is not None:
            self._coherence_action.setChecked(False)
        self._last_db_schema = None
        self._last_db_summary = None
        _log.info("file: close outcome=%s", outcome)

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
        bak_path = str(self._current_project_path) + ".bak"
        if not Path(bak_path).exists():
            self.statusBar().showMessage("Nothing to revert to.", 5000)
            return

        _log.info("file: revert %s", bak_path)
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
            # Seed the snapshot history with the reverted text so undo/redo
            # semantics after a revert match a normal open.
            self._history.push(
                self.center_stage.xml_editor.toPlainText(),
                f"Reverted {Path(self._current_project_path).name}",
                baseline=True,
            )
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
        self._build_schema_menu()
        self._build_database_menu()
        self._build_tools_menu()
        self._build_bookmarks_menu()
        self._build_generation_menu()
        self._build_help_menu()

    def _build_file_menu(self):
        menu = self.menuBar().addMenu("File")
        open_action = menu.addAction("Open...")
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_project)
        menu.addMenu("Open Recent")
        menu.addSeparator()
        # Local DDL-versioning projects (spec §18.2) -- a distinct concept
        # from `_current_project` (the open .pgtp), tracked separately as
        # `_ddl_project_folder`/`_ddl_project_settings`.
        # BUG-021: wrap in lambdas so `triggered`'s `checked: bool` argument
        # never lands in the `on_ready` parameter -- a bare connect passes
        # `False`, which is not None and so was taken for a callback.
        new_project_action = menu.addAction("New Project…")
        new_project_action.triggered.connect(lambda: self._new_ddl_project())
        open_project_action = menu.addAction("Open Project…")
        open_project_action.triggered.connect(lambda: self._open_ddl_project())
        self._close_ddl_project_action = menu.addAction("Close Project")
        self._close_ddl_project_action.triggered.connect(self._close_ddl_project)
        self._close_ddl_project_action.setEnabled(False)
        project_settings_action = menu.addAction("Project Settings…")
        project_settings_action.triggered.connect(self._open_ddl_project_settings)
        deploy_pgtp_action = menu.addAction("Deploy .pgtp")
        deploy_pgtp_action.triggered.connect(self._deploy_pgtp)
        menu.addSeparator()
        save_action = menu.addAction("Save")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_active_tab)
        save_as_action = menu.addAction("Save As...")
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._save_project_as)
        revert_action = menu.addAction("Revert")
        revert_action.triggered.connect(self._revert_project)
        self._revert_action = revert_action
        close_action = menu.addAction("Close")
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(lambda: self._close_project())
        self._close_action = close_action
        menu.addSeparator()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

    def _build_edit_menu(self):
        menu = self.menuBar().addMenu("Edit")
        # Undo and Redo are distinct single-step actions (Ctrl+Z / Ctrl+Y are
        # wired as QShortcuts + editor key-routing in __init__; the menu items
        # step directly). "History…" opens the non-modal navigator where moving
        # back = undo and forward = redo.
        undo_action = menu.addAction("Undo")
        undo_action.triggered.connect(self._undo)
        self._undo_action = undo_action
        redo_action = menu.addAction("Redo")
        redo_action.triggered.connect(self._redo)
        self._redo_action = redo_action
        history_action = menu.addAction("History…")
        history_action.triggered.connect(self._open_history_jump_list)
        self._history_action = history_action
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

        # The three dock actions are wired BOTH ways (BUG-007): toggled drives
        # dock.setVisible, and the dock's visibilityChanged drives setChecked,
        # so closing a dock via its title-bar ✕ (or any programmatic
        # hide/show) keeps the menu checkbox honest. No recursion guard is
        # needed: QAction.toggled and QDockWidget.visibilityChanged only fire
        # on actual state changes, so the pair settles immediately (same Qt
        # signal-coalescing the Manual tab sync in center_stage relies on).
        tree_action = menu.addAction("Project Tree")
        tree_action.setCheckable(True)
        tree_action.setChecked(True)
        tree_action.toggled.connect(self.tree_dock.setVisible)
        self.tree_dock.visibilityChanged.connect(tree_action.setChecked)
        self._tree_action = tree_action

        properties_action = menu.addAction("Properties Panel")
        properties_action.setCheckable(True)
        properties_action.setChecked(True)
        properties_action.toggled.connect(self.properties_dock.setVisible)
        self.properties_dock.visibilityChanged.connect(properties_action.setChecked)
        self._properties_action = properties_action

        audit_action = menu.addAction("Audit/Problems Panel")
        audit_action.setCheckable(True)
        audit_action.setChecked(True)
        audit_action.toggled.connect(self.audit_dock.setVisible)
        self.audit_dock.visibilityChanged.connect(audit_action.setChecked)
        self._audit_action = audit_action

        self._raw_xml_panel_action = menu.addAction("Raw XML Panel")
        self._raw_xml_panel_action.setCheckable(True)
        # The Raw XML tab is visible by default (see center_stage), so the
        # action starts checked to reflect real visibility.
        self._raw_xml_panel_action.setChecked(True)
        self._raw_xml_panel_action.toggled.connect(self.center_stage.set_raw_xml_tab_visible)

        menu.addSeparator()
        expand_all_action = menu.addAction("Expand All")
        expand_all_action.triggered.connect(self.project_tree.expandAll)
        collapse_all_action = menu.addAction("Collapse All")
        collapse_all_action.triggered.connect(self.project_tree.collapseAll)

        menu.addSeparator()
        self._light_theme_action = menu.addAction("Light Theme")
        self._light_theme_action.setCheckable(True)
        self._light_theme_action.setChecked(False)
        self._light_theme_action.toggled.connect(self._on_light_theme_toggled)

        menu.addSeparator()
        customize_toolbar_action = menu.addAction("Customize Toolbar…")
        customize_toolbar_action.triggered.connect(
            lambda: self._toolbar_ui.open_customize_dialog()
        )

    def _add_stub_action(self, menu, label):
        return add_stub_action(menu, label, self._not_implemented)

    def _reveal_raw_xml_tab(self):
        self.center_stage.set_raw_xml_tab_visible(True)
        self._raw_xml_panel_action.setChecked(True)
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)

    def _show_find_bar(self):
        self._active_find_bar().show_find()

    def _show_replace_bar(self):
        self._active_find_bar().show_replace()

    def _find_next(self):
        self._active_find_bar().find_next()

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
        self._active_find_bar().find_all()

    def _replace_all(self):
        self._active_find_bar().replace_all()

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

    def _build_schema_menu(self):
        menu = self.menuBar().addMenu("Schema")
        edit_action = menu.addAction("Edit XSD")
        edit_action.triggered.connect(self._open_edit_xsd)
        edit_auto_action = menu.addAction("Edit AutoXSD")
        edit_auto_action.triggered.connect(self._open_edit_auto_xsd)
        verify_action = menu.addAction("Verify XSD")
        verify_action.triggered.connect(self._verify_xsd)
        export_action = menu.addAction("Export XSD")
        export_action.triggered.connect(self._export_xsd)
        import_action = menu.addAction("Import XSD")
        import_action.triggered.connect(self._import_xsd)
        # "Go To XSD" (Ctrl+L) lives as a window-level action, not a menu
        # entry -- the Schema menu proper is Edit XSD / Edit AutoXSD / Verify /
        # Export / Import.
        goto_xsd_action = QAction("Go To XSD", self)
        goto_xsd_action.setShortcut(QKeySequence("Ctrl+L"))
        goto_xsd_action.triggered.connect(self._goto_xsd_at_cursor)
        self.addAction(goto_xsd_action)
        self._goto_xsd_action = goto_xsd_action

    def _build_database_menu(self):
        menu = self.menuBar().addMenu("Database")
        # Standalone/projectless-mode only (BUG-024): once a §18.2 project is
        # open, its own ProjectSettings (target/sandbox) is the connection
        # store and this app-level profile would be a redundant shadow of it.
        # Stored on self (not a local) so _refresh_project_dependent_actions
        # can flip its enabled state from _set_active_ddl_project /
        # _close_ddl_project.
        self._connection_setup_action = menu.addAction("Connection Setup…")
        self._connection_setup_action.triggered.connect(self._open_connection_setup)
        self._connection_setup_action.setEnabled(self._ddl_project_folder is None)
        menu.addSeparator()
        # §17/§26 (FQ-003): ONE checkable toggle, no direction control and no
        # shortcut. It replaced the two "Check: XML → Database" / "Check:
        # Database → XML" items and View ▸ "Find table reference".
        self._coherence_action = menu.addAction("Database/XML Coherence")
        self._coherence_action.setCheckable(True)
        self._coherence_action.setChecked(False)
        self._coherence_action.toggled.connect(self._on_coherence_toggled)
        menu.addSeparator()
        # DDL Explorer (spec §18.1): checkable toggle, kept in lockstep with
        # the center tab's real visibility via ddl_explorer_visibility_changed
        # (bidirectional per the BUG-007 lesson — the tab has its own ✕).
        self._ddl_explorer_action = menu.addAction("DDL Explorer")
        self._ddl_explorer_action.setCheckable(True)
        self._ddl_explorer_action.setChecked(False)
        self._ddl_explorer_action.toggled.connect(self._on_ddl_explorer_toggled)
        menu.addSeparator()
        # FQ-002: creating a routine is not scoped to a parent object, so it
        # earns a menu entry as well as the tree's context menu. Its trigger
        # counterpart deliberately does NOT appear here -- a trigger needs a
        # specific table, which only the tree can supply.
        new_routine_action = menu.addAction("New Function/Procedure…")
        new_routine_action.triggered.connect(lambda: self._on_ddl_new_routine_requested())
        menu.addSeparator()
        menu.addSeparator()
        # §18.5 D4: ad-hoc SQL is SANDBOX-ONLY. Created HIDDEN and shown only
        # by `_refresh_sandbox_console_affordances` when a live session exists
        # (absent, not disabled -- carve-out 2). There is deliberately NO "run
        # against target" counterpart here, not even a disabled one: the
        # boundary is structural (`run_sandbox_query` takes a `SandboxSession`,
        # never a `ConnectionParams`) and adding one would need a spec change
        # plus a Supersession Ledger row.
        self._sandbox_console_action = menu.addAction("Sandbox SQL Console…")
        self._sandbox_console_action.setVisible(False)
        self._sandbox_console_action.triggered.connect(
            lambda: self._open_sandbox_sql_console()
        )
        # §18.5 D2: acquiring/releasing the one `SandboxSession`. Deliberately
        # a user act rather than a side effect of opening a project -- a
        # session is a real connection to a real database, and
        # `SandboxController.set_project` is explicit that a project opening
        # "opens nothing and provisions nothing".
        self._open_sandbox_session_action = menu.addAction("Open Sandbox Session")
        self._open_sandbox_session_action.setVisible(False)
        self._open_sandbox_session_action.triggered.connect(
            lambda: self._open_sandbox_session()
        )
        self._close_sandbox_session_action = menu.addAction("Close Sandbox Session")
        self._close_sandbox_session_action.setVisible(False)
        self._close_sandbox_session_action.triggered.connect(
            lambda: self.sandbox_controller.close_session()
        )
        # §18.5 D3a's Check gesture. VISIBILITY follows `can_check` (carve-out
        # 2's "no dead controls"), and is deliberately NOT gated on
        # `plpgsql_check_state`: an unavailable tier 3 is a REPORTED OUTCOME,
        # so the gesture stays present and states what it could not check.
        self._sandbox_check_action = menu.addAction("Check Object in Sandbox")
        self._sandbox_check_action.setVisible(False)
        self._sandbox_check_action.triggered.connect(
            lambda: self._check_active_ddl_object()
        )
        menu.addSeparator()
        # §18.8: opening the window is itself a probe trigger, not a passive
        # read of a cached result -- see _open_project_status.
        project_status_action = menu.addAction("Project Status…")
        project_status_action.triggered.connect(lambda: self._open_project_status())
        # Every sandbox-dependent entry above was created hidden; this is the
        # one place that decides which of them the current state earns.
        self._refresh_sandbox_affordances()

    def _prompt_missing_connection(self) -> None:
        """No configured DB connection: in projectless mode this opens the
        standalone Connection Setup dialog (unchanged behavior); with a
        §18.2 project open, that dialog is meaningless (BUG-024) -- point the
        user at Project Settings (target/sandbox) instead. Shared by
        _run_db_check and _open_ddl_explorer, the two internal callers that
        used to always open Connection Setup on a missing host."""
        if self._ddl_project_folder is not None:
            self.statusBar().showMessage(
                "No database connection configured — set one up in Project Settings.",
                5000,
            )
            self._open_ddl_project_settings()
            return
        self.statusBar().showMessage(
            "No database connection configured — set one up first.", 5000
        )
        self._open_connection_setup()

    def _open_connection_setup(self):
        # Projectless mode only (BUG-024): while a §18.2 project is open, its
        # connection lives in Project Settings (target/sandbox) -- this
        # app-level dialog would be a meaningless, redundant shadow of it.
        # The menu action is already disabled in that state, but internal
        # callers (_run_db_check, _open_ddl_explorer) also invoke this method
        # directly on a missing connection, so guard here too.
        if self._ddl_project_folder is not None:
            self.statusBar().showMessage(
                "Connection is defined in Project Settings while a project is open.",
                5000,
            )
            return
        tree = (
            self._current_project.tree
            if self._current_project is not None
            else None
        )
        dialog = ConnectionSetupDialog(parent=self, tester=db_test_connection)
        dialog.set_params(seed_params(tree, self._settings))
        dialog.accepted.connect(
            lambda: save_connection(self._settings, dialog.params())
        )
        self._connection_dialog = dialog
        dialog.show()

    # -- Local DDL-versioning projects (§18.2) --------------------------------
    def _new_ddl_project(self, on_ready=None) -> None:
        dialog = NewProjectDialog(parent=self)

        def handle() -> None:
            self._create_ddl_project(dialog)
            if callable(on_ready):
                on_ready()

        dialog.accepted.connect(handle)
        self._new_project_dialog = dialog
        dialog.show()

    def _create_ddl_project(self, dialog: NewProjectDialog) -> None:
        folder = Path(dialog.folder())
        folder.mkdir(parents=True, exist_ok=True)
        settings = ProjectSettings(
            name=dialog.name(),
            description=dialog.description(),
            sandbox=dialog.sandbox_params(),
            sandbox_mode=dialog.sandbox_mode(),
            git=dialog.git_config(),
        )
        save_settings(folder, settings)
        self._set_active_ddl_project(folder, settings)
        self.statusBar().showMessage(f"Created project: {folder}", 5000)

    def _open_ddl_project(self, on_ready=None) -> None:
        folder = modals.QFileDialog.getExistingDirectory(
            self, "Open Project Folder", "",
            modals.QFileDialog.Option.ShowDirsOnly,
        )
        if not folder:
            return
        folder_path = Path(folder)
        # BUG-022: Open requires a REAL project folder -- one already
        # carrying the `.ddlproject/settings.json` marker. Loading
        # `load_settings` unconditionally on any folder silently returns a
        # default ProjectSettings() for a folder that was never a project;
        # reject that instead of guessing.
        if not is_project_dir(folder_path):
            modals.QMessageBox.warning(
                self,
                "Not a Project Folder",
                f"{folder_path} is not a PGTP DDL project folder "
                "(no .ddlproject/settings.json marker found).",
            )
            return
        settings = load_settings(folder_path)
        self._set_active_ddl_project(folder_path, settings)
        self._report_ddl_project_drift(folder_path, settings)
        self.statusBar().showMessage(f"Opened project: {folder_path}", 5000)
        if callable(on_ready):
            on_ready()
        else:
            # BUG-021: opening a project should auto-open its linked .pgtp
            # into the editor -- but only on a plain Open Project (on_ready
            # is None). When on_ready IS set, the caller (e.g.
            # _prompt_pgtp_open_mode's "Open Project…" choice, or
            # _require_ddl_project) already has its own specific .pgtp to
            # load; auto-opening the linked working copy here too would be a
            # silent double-load racing against that caller's own load.
            self._auto_open_linked_pgtp(folder_path, settings)

    def _auto_open_linked_pgtp(self, folder_path: Path, settings: ProjectSettings) -> None:
        """BUG-021: a project's linked `.pgtp` should populate the editor the
        moment the project is opened, not require a separate manual File >
        Open. Reuses the existing `open_project_file` loader -- never
        reinvents loading.

        Scope, exactly as triaged: **zero** candidates -> silent no-op (no
        error, nothing to open yet); **one** -> auto-open it; **multiple**
        unlinked candidates -> report via the Audit panel rather than
        guessing which one the user means."""
        working_copy_path = settings.pgtp.working_copy_path
        if working_copy_path:
            if Path(working_copy_path).exists():
                self.open_project_file(working_copy_path)
            return
        # Not yet linked -- fall back to scanning the project folder itself
        # for a `.pgtp` the user may have dropped in directly.
        candidates = sorted(folder_path.glob("*.pgtp"))
        if not candidates:
            return  # zero -- nothing to do
        if len(candidates) == 1:
            self.open_project_file(str(candidates[0]))
            return
        # Multiple unlinked candidates: never guess -- surface via Audit.
        names = ", ".join(path.name for path in candidates)
        self.audit_panel.addItem(
            QListWidgetItem(
                f"[Project] Multiple .pgtp files found in {folder_path} "
                f"({names}) -- open one explicitly via File > Open."
            )
        )

    def _require_ddl_project(self, on_ready) -> None:
        """§18.2: no project-scoped action proceeds silently with none open.
        Offers **Create… / Open… / Cancel**; on Create/Open, `on_ready` runs
        against the newly-active project once it exists. On Cancel, nothing
        happens."""
        if self._ddl_project_folder is not None:
            on_ready()
            return
        box = modals.QMessageBox(self)
        box.setWindowTitle("Project Required")
        box.setText("This action needs an open project.")
        create_button = box.addButton("Create…", modals.QMessageBox.ButtonRole.ActionRole)
        open_button = box.addButton("Open…", modals.QMessageBox.ButtonRole.ActionRole)
        box.addButton("Cancel", modals.QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is create_button:
            self._new_ddl_project(on_ready=on_ready)
        elif clicked is open_button:
            self._open_ddl_project(on_ready=on_ready)

    def _set_active_ddl_project(self, folder: Path, settings: ProjectSettings) -> None:
        self._ddl_project_folder = folder
        self._ddl_project_settings = settings
        self._close_ddl_project_action.setEnabled(True)
        # §18.5 D2: the controller follows the project. `set_project` drops any
        # session that belonged to the previous project and connects to nothing.
        self._bind_sandbox_controller_to_project()
        self._refresh_project_dependent_actions()
        self._update_title()
        self.refresh_project_capability_status()

    def _refresh_project_dependent_actions(self) -> None:
        """Single place for menu-action enablement that depends on whether a
        §18.2 project is open. Currently just the standalone Connection
        Setup… action (BUG-024: projectless-mode only, since a project's own
        connection lives in Project Settings), called from both
        `_set_active_ddl_project` and `_close_ddl_project` so the two
        transitions can never drift apart."""
        self._connection_setup_action.setEnabled(self._ddl_project_folder is None)

    def refresh_project_capability_status(self) -> None:
        """Re-run the top-of-§18 tier/capability probe for the current
        project (reachable local Postgres via `db/sandbox.py::probe`, plus
        -- for a "with data" sandbox -- `pg_dump`/`pg_restore` on `PATH`) and
        store the result on `self._ddl_project_capability_status`.

        **Probe timing, settled 2026-08-05:** runs automatically whenever a
        project is opened/created (called from `_set_active_ddl_project`)
        and is also the entry point the not-yet-designed "Project Status"
        screen will call on demand later -- it is never probed once and
        cached from creation time, so a sandbox that died between sessions
        is correctly detected and degrades the project from tier 3 to tier
        2 for this session. No-op (and clears the stored status) when no
        project is open. Runs off the GUI thread so an unreachable sandbox
        host can't freeze the window.

        **BUG-030:** this is the single "re-probe everything the Project
        Status window shows" entry point, so it also probes the *target*
        connection's reachability (below) -- which happens with or without a
        project open, since projectless mode still has an app-level target.
        """
        self._refresh_target_connection_status()
        if self._ddl_project_folder is None or self._ddl_project_settings is None:
            self._ddl_project_capability_status = None
            return
        settings = self._ddl_project_settings
        sandbox_params = settings.sandbox
        sandbox_mode = settings.sandbox_mode
        sandbox_configured = bool(sandbox_params.host)

        def do_probe() -> ProjectCapabilityStatus:
            if not sandbox_configured:
                return determine_project_tier(
                    SandboxCapabilities(), sandbox_mode, sandbox_configured=False
                )
            caps = self._probe_sandbox_capabilities(sandbox_params)
            return determine_project_tier(caps, sandbox_mode, sandbox_configured=True)

        def on_result(status: ProjectCapabilityStatus) -> None:
            self._ddl_project_capability_status = status

        def on_error(exc: BaseException) -> None:
            # The probe itself never raises (db/sandbox.py::probe's
            # never-raises contract) -- this only guards against a broken
            # injected seam in tests/future callers, never silently swallowed.
            self.audit_panel.addItem(
                QListWidgetItem(f"[Project] Capability probe failed unexpectedly: {exc}")
            )

        self._run_async(do_probe, on_result=on_result, on_error=on_error)

    def _refresh_target_connection_status(self) -> None:
        """Re-probe the *target* connection's reachability (BUG-030).

        §18.8's Quality node means "the target is reachable", not merely "a
        target profile exists", so it needs a real `SELECT 1` -- the same
        check the DDL Explorer / coherence path opens -- against the very
        `ConnectionParams` the summary line uses (BUG-024's selection). Runs
        off the GUI thread for the same reason the sandbox probe does: a dead
        host can hang on TCP connect and must never freeze the window. The
        stored result is only *corrected* when the answer lands, and an
        already-open Project Status window is re-rendered then, so nothing
        ever flashes red while the probe is still in flight.
        """
        target = self._project_status_target()
        if target is None or not target.host:
            # Nothing to reach: `quality_state`'s not-configured branch owns
            # that case, and a host-less profile has not failed -- it has
            # not been tried. Never let a stale error outlive the profile.
            self._ddl_target_probe_error = None
            return

        def do_probe() -> str | None:
            ok, message = db_test_connection(target)
            return None if ok else message

        def on_result(probe_error: str | None) -> None:
            self._ddl_target_probe_error = probe_error
            window = self._project_status_window
            if window is not None:
                window.set_diagram(self._build_project_status_diagram())

        def on_error(exc: BaseException) -> None:
            # `test_connection` never raises (it returns `(False, msg)`), so
            # this only guards a broken injected seam -- surfaced, never
            # silently swallowed.
            self.audit_panel.addItem(
                QListWidgetItem(f"[Project] Target connection probe failed unexpectedly: {exc}")
            )

        self._run_async(do_probe, on_result=on_result, on_error=on_error)

    def _report_ddl_project_drift(self, folder: Path, settings: ProjectSettings) -> None:
        """Opening a project compares the `.pgtp` working copy's checksum
        against the sshfs-mounted source, surfaced (never auto-resolved) via
        the Audit panel -- recomputed fresh on every load, never cached
        (§18.2). The per-object DDL `*`/`!` drift comparison runs alongside
        the DDL Explorer tree it renders onto (§18.2/§18.8, see BrowserPanel)."""
        link = settings.pgtp
        if not link.source_path:
            return  # no .pgtp linked to this project yet -- nothing to compare
        try:
            source_text = Path(link.source_path).read_text(encoding="utf-8")
        except OSError as exc:
            item = QListWidgetItem(f"[Project] Could not read source .pgtp: {exc}")
            self.audit_panel.addItem(item)
            return
        current_checksum = content_hash(source_text)
        if link.last_known_source_checksum is None:
            message = f"[Project] Source .pgtp checksum recorded ({link.source_path})."
        elif current_checksum != link.last_known_source_checksum:
            message = (
                f"[Project] Source .pgtp has changed since this project last saw it "
                f"({link.source_path}) -- surfaced, not auto-resolved."
            )
        else:
            message = f"[Project] Source .pgtp unchanged since last opened ({link.source_path})."
        self.audit_panel.addItem(QListWidgetItem(message))

    def _close_ddl_project(self) -> None:
        """Closing is a reminder point, never a forcing point (§18.3) --
        offers "Deploy .pgtp" if the working copy has unpushed changes, but
        never forces it; closing itself always succeeds."""
        if self._ddl_project_folder is None:
            return
        self._offer_pgtp_deploy_on_close()
        self._remind_pending_ddl_deploys_on_close()
        self._ddl_project_folder = None
        self._ddl_project_settings = None
        self._ddl_project_capability_status = None
        # BUG-030: the target changes with the project (BUG-024's selection),
        # so the project's probe result must not outlive it as a stale error
        # against the app-level connection.
        self._ddl_target_probe_error = None
        # §18.5 D2: no stale session may outlive the project it belonged to --
        # `clear_project` releases it and announces the release, and the
        # refresh inside takes the console and every tab affordance with it.
        self._bind_sandbox_controller_to_project()
        self._close_ddl_project_action.setEnabled(False)
        self._refresh_project_dependent_actions()
        self._update_title()
        self.statusBar().showMessage("Project closed.", 5000)

    def _remind_pending_ddl_deploys_on_close(self) -> None:
        """Reminds about `*`-flagged DDL objects (locally edited, candidates
        for a batch deploy) -- never opens the deploy-bundle flow
        automatically and never forces a decision (§18.3). Only checks
        objects from the currently-loaded DDL Explorer schema, if any --
        this is a reminder at a natural checkpoint, not a forced fresh
        fetch."""
        schema = getattr(self.ddl_browser_panel, "_schema", None)
        if schema is None or self._ddl_project_settings is None:
            return
        markers = compute_drift_markers(self._ddl_project_folder, self._ddl_project_settings, schema)
        pending = sum(1 for marker in markers.values() if marker.locally_edited)
        if pending:
            self.audit_panel.addItem(
                QListWidgetItem(
                    f"[Project] {pending} DDL object(s) have local edits pending a batch deploy."
                )
            )

    def _offer_pgtp_deploy_on_close(self) -> None:
        link = self._ddl_project_settings.pgtp if self._ddl_project_settings else None
        if link is None or not link.working_copy_path or not link.source_path:
            return
        try:
            working_text = Path(link.working_copy_path).read_text(encoding="utf-8")
        except OSError:
            return
        if content_hash(working_text) == link.last_known_source_checksum:
            return  # nothing pending
        choice = modals.QMessageBox.question(
            self,
            "Unpushed .pgtp Changes",
            "This project's .pgtp working copy has changes not yet deployed "
            "to the source. Deploy them now?",
            modals.QMessageBox.StandardButton.Yes | modals.QMessageBox.StandardButton.No,
        )
        if choice == modals.QMessageBox.StandardButton.Yes:
            self._deploy_pgtp()

    def _resolve_pgtp_project_path(self, path) -> str:
        """If `path` is the sshfs-mounted source of an ALREADY-linked §18.2
        project, resolve to the local working copy instead -- **every**
        open of the linked source redirects there, not just the first
        (the working copy is the editable truth once linked, §18.2; without
        this, re-opening the source a second time would silently repoint
        saves back at the source, defeating the whole no-`.bak` model).
        Unlinked / no-project cases pass `path` through unchanged -- this is
        also what makes first-time linking possible at all, since
        `_link_pgtp_to_project_if_needed` needs the ORIGINAL source path."""
        if self._ddl_project_settings is None:
            return str(path)
        link = self._ddl_project_settings.pgtp
        if link.source_path and link.working_copy_path and str(path) == link.source_path:
            return link.working_copy_path
        return str(path)

    def _link_pgtp_to_project_if_needed(self) -> None:
        """When a `.pgtp` is opened while a project is active and not yet
        linked, this `.pgtp` becomes that project's first-class checked-out
        artifact (§18.2): a local working copy inside the project folder,
        distinct from the sshfs-mounted source, tracked in the project's own
        settings. Subsequent saves redirect to the working copy (this method
        repoints `_current_project_path` there). No-op if no project is
        open or one is already linked -- never silently relinked. (Every
        FUTURE open of the linked source is redirected before this method
        even runs -- see `_resolve_pgtp_project_path`.)"""
        if self._ddl_project_folder is None or self._ddl_project_settings is None:
            return
        if self._ddl_project_settings.pgtp.working_copy_path:
            return
        source_path = Path(self._current_project_path)
        working_copy_path = self._ddl_project_folder / source_path.name
        try:
            source_text = source_path.read_text(encoding="utf-8")
        except OSError:
            return  # nothing to link yet -- leave the .pgtp unlinked
        if not working_copy_path.exists():
            working_copy_path.write_text(source_text, encoding="utf-8", newline="")
        settings = self._ddl_project_settings
        updated = ProjectSettings(
            name=settings.name,
            description=settings.description,
            pgtp=PgtpLink(
                source_path=str(source_path),
                working_copy_path=str(working_copy_path),
                last_known_source_checksum=content_hash(source_text),
            ),
            target=settings.target,
            sandbox=settings.sandbox,
            git=settings.git,
            deployed=settings.deployed,
        )
        save_settings(self._ddl_project_folder, updated)
        self._ddl_project_settings = updated
        self._current_project_path = str(working_copy_path)

    def _deploy_pgtp(self) -> None:
        """Push the local `.pgtp` working copy back to the sshfs-mounted
        source -- the explicit gesture that reverses working-copy drift
        (§18.2). Never implied by Save; reachable on-demand (Database menu)
        and offered as a close-time convenience prompt."""
        if self._ddl_project_settings is None:
            self.statusBar().showMessage("No project open.", 5000)
            return
        link = self._ddl_project_settings.pgtp
        if not link.working_copy_path or not link.source_path:
            self.statusBar().showMessage("No .pgtp linked to this project yet.", 5000)
            return
        try:
            working_text = Path(link.working_copy_path).read_text(encoding="utf-8")
            Path(link.source_path).write_text(working_text, encoding="utf-8", newline="")
        except OSError as exc:
            modals.QMessageBox.critical(self, "Deploy Failed", f"Could not deploy .pgtp:\n\n{exc}")
            return
        settings = self._ddl_project_settings
        updated = ProjectSettings(
            name=settings.name,
            description=settings.description,
            pgtp=PgtpLink(
                source_path=link.source_path,
                working_copy_path=link.working_copy_path,
                last_known_source_checksum=content_hash(working_text),
            ),
            target=settings.target,
            sandbox=settings.sandbox,
            git=settings.git,
            deployed=settings.deployed,
        )
        save_settings(self._ddl_project_folder, updated)
        self._ddl_project_settings = updated
        self.statusBar().showMessage(f"Deployed .pgtp to {link.source_path}", 5000)

    def _open_ddl_project_settings(self) -> None:
        self._require_ddl_project(self._show_ddl_project_settings_dialog)

    def _show_ddl_project_settings_dialog(self) -> None:
        dialog = ProjectSettingsDialog(self._ddl_project_settings, parent=self)
        dialog.accepted.connect(lambda: self._save_ddl_project_settings(dialog))
        self._project_settings_dialog = dialog
        dialog.show()

    def _save_ddl_project_settings(self, dialog: ProjectSettingsDialog) -> None:
        settings = dialog.settings()
        save_settings(self._ddl_project_folder, settings)
        self._ddl_project_settings = settings
        # The sandbox/target profiles may have just changed under a live
        # session: rebind (which drops it) rather than keep a session pointed at
        # a database this project no longer calls its sandbox.
        self._bind_sandbox_controller_to_project()
        self.statusBar().showMessage("Project settings saved.", 5000)

    # -- Database/XML Coherence (§17, FQ-003) ---------------------------------

    def _fetch_db_schema(self, params):
        """Introspect the database. Injectable seam — tests patch this to return
        a canned `DatabaseSchema` so no live connection (or psycopg) is needed."""
        return db_fetch_schema(params)

    def _prompt_rename(self, old):
        """Ask for a new name (modal QInputDialog). Test seam — patched in tests
        to bypass the modal. Returns the new name, or None if cancelled."""
        text, ok = modals.QInputDialog.getText(
            self,
            "Rename in XML",
            f"New name for '{old}' — replaces every matching "
            "fieldName/tableName occurrence in the file:",
            text=old,
        )
        return text if ok else None

    def _reveal_db_check_tab(self):
        self.tree_dock.setVisible(True)
        self.left_tabs.setTabVisible(self.coherence_tab_index, True)
        self.left_tabs.setCurrentWidget(self.coherence_panel)

    def _populate_db_check(self, schema, project, summary):
        """Build the coherence tree for `project` against `schema` and show
        it. Shared by the live run (_run_db_check) and the cached-schema
        refresh (_refresh_db_check_if_open)."""
        self.coherence_panel.set_result(
            build_coherence_tree(project, schema), summary
        )

    def _uncheck_coherence_action(self):
        """Un-check the Database-menu toggle after a failed/refused run, so the
        menu never claims a view is open that is not (the BUG-007 lesson)."""
        if self._coherence_action is not None and self._coherence_action.isChecked():
            self._coherence_action.setChecked(False)

    def _on_coherence_toggled(self, checked):
        """Database ▸ "Database/XML Coherence" (checkable, no shortcut).

        On → fetch the schema and reveal the tab; on any failure the action
        un-checks itself so the menu never lies about what is on screen.
        Off → just hide the tab (the cached schema survives, so toggling back
        on is a fresh, honest re-run rather than a stale redisplay)."""
        if checked:
            self._run_db_check()
        else:
            self.left_tabs.setTabVisible(self.coherence_tab_index, False)

    def _run_db_check(self):
        # Compare against a model parsed from the CURRENT buffer, not the
        # last-parsed self._current_project -- so renames (and any manual edit)
        # made since the last load are reflected and the reconcile loop
        # actually resolves. Falls back to no-op with a status message when the
        # buffer is empty or not valid XML.
        text = self.center_stage.xml_editor.toPlainText()
        if not text.strip():
            self.statusBar().showMessage("Open a project first.", 5000)
            self._uncheck_coherence_action()
            return
        try:
            project = load_project_from_text(text, source_description="<editor>")
        except PgtpParseError as exc:
            self.statusBar().showMessage(
                f"Database check needs valid XML: {exc}", 8000
            )
            self._uncheck_coherence_action()
            return
        params = seed_params(project.tree, self._settings)
        if not params.host:
            self._uncheck_coherence_action()
            self._prompt_missing_connection()
            return
        # The schema fetch opens a DB connection -- move ONLY that off the GUI
        # thread. Everything above (buffer parse, seed, guards) is fast and stays
        # here; the compare + panel population happen in on_result, back on the
        # GUI thread, so they may safely touch widgets.
        self.statusBar().showMessage("Checking database…")
        _log.info("db: coherence check started %s", debuglog.redacted(params))

        def on_result(schema):
            summary = f"{params.user}@{params.host}:{params.port}/{params.database}"
            self._last_db_schema = schema
            self._last_db_summary = summary
            self._populate_db_check(schema, project, summary)
            self._reveal_db_check_tab()
            # Sync the menu's checkmark WITHOUT re-entering the toggle slot:
            # a plain setChecked here would fire toggled(True) and start a
            # second fetch (the run can also be entered from the rename
            # re-run, not only from the menu).
            if self._coherence_action is not None:
                blocker = QSignalBlocker(self._coherence_action)
                self._coherence_action.setChecked(True)
                del blocker
            self.statusBar().showMessage("Database/XML Coherence complete.", 3000)
            _log.info("db: coherence check finished")

        def on_error(exc):
            _log.info("db: coherence check failed %s", exc)
            self.statusBar().showMessage(f"Database check failed: {exc}", 8000)
            self._uncheck_coherence_action()

        self._run_async(
            lambda: self._fetch_db_schema(params),
            on_result=on_result,
            on_error=on_error,
        )

    # -- DDL Explorer (spec §18.1) --------------------------------------------

    def _fetch_ddl_schema(self, params):
        """Introspect routines & triggers. Injectable seam — tests patch this
        to return a canned `DatabaseSchema` (mirrors `_fetch_db_schema`)."""
        return fetch_routines_and_triggers(params)

    def _on_ddl_explorer_toggled(self, checked):
        if checked:
            self._open_ddl_explorer()
        else:
            self.center_stage.hide_ddl_explorer()

    def _open_ddl_explorer(self):
        """Fetch routines/triggers and reveal the DDL Explorer (center buffer
        tab + left "DDL Objects" tree). Standalone-mode friendly (§18): no
        `.pgtp` project is required — only a configured connection."""
        tree = (
            self._current_project.tree
            if self._current_project is not None
            else None
        )
        params = seed_params(tree, self._settings)
        if not params.host:
            self._ddl_explorer_action.setChecked(False)
            self._prompt_missing_connection()
            return
        self.statusBar().showMessage("Loading routines & triggers…")
        _log.info("db: ddl explorer load started %s", debuglog.redacted(params))

        def on_result(schema):
            text, spans = build_ddl_text(schema)
            self.center_stage.ddl_editor_panel.set_ddl_text(text, spans, schema=schema)
            # */! drift markers (§18.2): recomputed fresh on every fetch, never
            # cached -- None (no markers) when no project is open, matching the
            # existing project-less rendering exactly.
            drift_markers = (
                compute_drift_markers(self._ddl_project_folder, self._ddl_project_settings, schema)
                if self._ddl_project_folder is not None
                else None
            )
            self.ddl_browser_panel.set_schema(schema, spans, drift_markers=drift_markers)
            self.center_stage.show_ddl_explorer()
            # Schema-aware Ctrl+Space completion (§18.6): rebuild the lookup
            # index from this same fetch (now widened to also carry
            # `.tables`) and push it into every already-open DDL object tab,
            # exactly like the tree and the read-only buffer are refreshed
            # above -- built once per connect/refresh, never per keystroke.
            self._ddl_schema_index = SchemaIndex(schema)
            # Kept alongside the index because FQ-002's creation dialogs need
            # the raw schema (the trigger-function candidate list), and the
            # index exposes only its own query surface.
            self._ddl_schema = schema
            for panel in self.center_stage.ddl_object_panels():
                panel.set_schema_index(self._ddl_schema_index)
            self.statusBar().showMessage(
                f"DDL Explorer: {len(schema.routines)} routine(s), "
                f"{len(schema.triggers)} trigger(s).",
                5000,
            )
            _log.info("db: ddl explorer load finished")

        def on_error(exc):
            _log.info("db: ddl explorer load failed %s", exc)
            self.statusBar().showMessage(f"DDL Explorer failed: {exc}", 8000)
            self._ddl_explorer_action.setChecked(False)

        self._run_async(
            lambda: self._fetch_ddl_schema(params),
            on_result=on_result,
            on_error=on_error,
        )

    def _on_ddl_explorer_visibility_changed(self, visible):
        """Keep the left "DDL Objects" tree tab and the Database-menu toggle
        in lockstep with the center tab (Contents-rides-with-Manual pattern;
        bidirectional per BUG-007 — the tab has its own ✕)."""
        self.left_tabs.setTabVisible(self.ddl_browser_tab_index, visible)
        if visible:
            self.tree_dock.setVisible(True)
            self.left_tabs.setCurrentWidget(self.ddl_browser_panel)
        self._ddl_explorer_action.setChecked(visible)

    def _on_ddl_navigate_requested(self, line):
        """Leaf click in the DDL Objects tree → jump the DDL buffer tab to the
        object's banner line (two tree leaves may share one span, §18.1)."""
        self.center_stage.setCurrentIndex(self.center_stage.ddl_tab_index)
        self.center_stage.ddl_editor_panel.navigate_to_line(line)

    def _on_ddl_table_selected(self, table_info) -> None:
        """Click on a Tables-branch table node (spec §18.1, 2026-08-05) --
        populates the shared Properties panel, mirroring how the XML/XSD
        tree's own selection handler (`_on_tree_selection_changed`) calls
        `show_node` for its four kinds. Click-only, no navigation target:
        `PropertiesPanel` rows built from a `TableInfo` all carry
        `target_line=None`."""
        self.properties_panel.show_node(table_info, "ddl_table")

    def _on_ddl_edit_requested(self, ref, source):
        """Right-click ▸ Edit… on a BrowserPanel object row opens (or
        focuses) the editable DDL object tab for it (spec §18.5, D1 entry
        point 1). Re-invoking Edit on an already-open object focuses the
        existing tab -- never a second tab for the same object."""
        existing = self.center_stage.ddl_object_tab(ref.key)
        if existing is not None:
            self.center_stage.setCurrentWidget(existing)
            return

        # The §18.2 save seam, in concrete v1 form: return the remembered
        # path, or run Save As… (this module owns QFileDialog -- the panel
        # itself must not, so §18.2 can repoint this one callable later
        # without the panel changing at all). `box` exists only so this
        # closure can see the panel that does not exist yet at definition
        # time; it is filled in immediately below, before any save can occur.
        box = {}

        def resolver():
            panel = box["panel"]
            if panel.save_path is not None:
                return panel.save_path
            default_dir = self._dialog_default_dir()
            prefill = str(Path(default_dir) / ref.default_file_name) if default_dir else ref.default_file_name
            path, _filter = modals.QFileDialog.getSaveFileName(
                self, "Save DDL Object", prefill, "SQL files (*.sql)"
            )
            if not path:
                return None
            resolved = Path(path)
            panel.remember_save_path(resolved)
            return resolved

        panel = self.center_stage.open_ddl_object_tab(ref, source, resolve_save_path=resolver)
        box["panel"] = panel
        panel.set_schema_index(self._ddl_schema_index)
        panel.dirty_changed.connect(
            lambda _dirty, ref=ref: self.center_stage.update_ddl_object_tab(ref)
        )
        panel.format_refused.connect(self._report_ddl_format_refusal)
        self._wire_ddl_object_panel_reporting(panel, ref)

    # --- §18.8: the Project Status window ------------------------------------
    def _project_status_target(self):
        """The target `ConnectionParams` the Quality node speaks for, or None.

        One place for BUG-024's selection -- with a project open its own
        target profile is authoritative; projectless, the app-level saved
        connection is -- so the diagram, the summary line and the
        reachability probe can never drift onto different connections.
        """
        settings = self._ddl_project_settings
        return settings.target if settings is not None else load_connection(self._settings)

    def _build_project_status_diagram(self):
        """Current `ProjectStatusDiagram`, or None when nothing to show.

        Quality has no backing field on `ProjectCapabilityStatus` (which
        models the sandbox side only), so it is assembled here from whether a
        target connection is configured at all plus the last reachability
        probe's result (BUG-030: green must mean "reachable", not merely
        "a profile exists") -- §18.8's not_set_up / error / connection_ok
        trio, mirroring the Sandbox node's own pattern.
        """
        settings = self._ddl_project_settings
        target = self._project_status_target()
        quality = quality_state(
            configured=target is not None, probe_error=self._ddl_target_probe_error
        )
        sandbox_mode = settings.sandbox_mode if settings is not None else SandboxMode.SCHEMA_ONLY
        return build_diagram(
            status=self._ddl_project_capability_status,
            quality=quality,
            sandbox_mode=sandbox_mode,
            data_clone_done=sandbox_mode is SandboxMode.WITH_DATA,
            dark=not self._light_theme_action.isChecked(),
        )

    @staticmethod
    def _connection_summary_for(params) -> str:
        """`user@host:port/db` for a status window, or a plain "not
        configured" line. Routed through `connection_summary` so no password
        can reach the window text."""
        if params is None:
            return "Not configured."
        return connection_summary(params)

    def _open_project_status(self) -> None:
        """Database ▸ Project Status… (§18.8).

        Opening the window is itself a probe trigger, not a passive read of a
        cached result -- a sandbox that died since the project was opened must
        show as offline here. A fresh panel probes itself when first shown (its
        `on_refresh` seam), so only the reuse path below re-probes explicitly;
        doing both would probe twice per open.
        """
        existing = self._project_status_window
        if existing is not None:
            self.refresh_project_capability_status()
            existing.set_diagram(self._build_project_status_diagram())
            # BUG-031: closing the window only HIDES it (no WA_DeleteOnClose,
            # so `destroyed` never fires and the cached instance is never
            # reset) -- without an explicit re-show, raise_()/activateWindow()
            # on a hidden window are silent no-ops and the menu entry appears
            # dead for the rest of the session. show() on an already-visible
            # window is harmless, so this covers both re-invoke cases.
            existing.show()
            existing.setWindowState(
                existing.windowState() & ~Qt.WindowState.WindowMinimized
            )
            existing.raise_()
            existing.activateWindow()
            return

        def on_refresh():
            self.refresh_project_capability_status()
            return self._build_project_status_diagram()

        # Sandbox1's "run data clone" and Sandbox2's "install plpgsql_check"
        # are deliberately NOT wired: both need a live `SandboxSession`, which
        # only `open_sandbox` can create and which this window has no way to
        # obtain yet (§18.5 D2's provisioning UI is not built). The panel hides
        # an affordance whose callback is None, so those windows stay
        # status-only rather than offering a button that cannot work.
        settings = self._ddl_project_settings
        panel = ProjectStatusPanel(
            diagram=self._build_project_status_diagram(),
            on_refresh=on_refresh,
            on_reconnect_quality=on_refresh,
            on_show_help=self._show_manual,
            quality_summary=self._connection_summary_for(self._project_status_target()),
            sandbox_summary=self._connection_summary_for(
                settings.sandbox if settings is not None else None
            ),
            parent=self,
        )
        panel.setWindowFlag(Qt.WindowType.Window, True)
        panel.setWindowTitle("Project Status")
        panel.destroyed.connect(lambda: setattr(self, "_project_status_window", None))
        self._project_status_window = panel
        panel.show()

    # --- FQ-002: creating brand-new DDL objects ------------------------------
    def _trigger_function_candidates(self) -> list[str]:
        """Qualified names of every routine returning `trigger` (FQ-002).

        A trigger can only attach to a function that `RETURNS trigger`, so the
        chooser is restricted to those -- read off the schema already fetched
        for the Explorer, never a second round trip.
        """
        if self._ddl_schema is None:
            return []
        return sorted(
            f"{routine.schema}.{routine.name}"
            for routine in self._ddl_schema.routines.values()
            if (routine.return_type or "").strip().lower() == "trigger"
        )

    def _on_ddl_add_trigger_requested(self, table_info) -> None:
        """Right-click ▸ Add Trigger… on a table node (FQ-002)."""
        dialog = NewTriggerDialog(
            table_info.name, self._trigger_function_candidates(), parent=self
        )
        dialog.accepted.connect(lambda: self._open_created_ddl_object(dialog))
        dialog.show()

    def _on_ddl_new_routine_requested(self) -> None:
        """Database ▸ New Function/Procedure… and the tree's routines-branch
        context entry (FQ-002) -- one action, one dialog, kind inside it."""
        dialog = NewRoutineDialog(parent=self)
        dialog.accepted.connect(lambda: self._open_created_ddl_object(dialog))
        dialog.show()

    def _open_created_ddl_object(self, dialog) -> None:
        """Open a newly-created object's editor tab on its generated skeleton.

        Deliberately routed through `_on_ddl_edit_requested`, the same path
        Edit… uses: the tab, its save-path resolver, its completion index and
        its dirty bookkeeping are identical whether the text came from
        introspection or from a skeleton. The only thing creation does
        differently is build the `DdlObjectRef` from dialog fields rather than
        `resolve_edit_target`, which correctly returns None for an object that
        does not exist yet.
        """
        ref = self._ref_for_created_object(dialog)
        if ref is None:
            return
        self._on_ddl_edit_requested(ref, dialog.skeleton())
        self._register_created_object(ref)

    def _ref_for_created_object(self, dialog):
        schema, name = self._split_qualified(
            dialog.trigger_name() if isinstance(dialog, NewTriggerDialog) else dialog.routine_name()
        )
        if isinstance(dialog, NewTriggerDialog):
            table_schema, table_name = self._split_qualified(dialog.table())
            # A trigger's own schema is its table's -- pg_trigger has no
            # separate namespace for it.
            return DdlObjectRef(
                kind="trigger",
                schema=table_schema or schema,
                name=name,
                table=table_name,
            )
        return DdlObjectRef(kind=dialog.kind(), schema=schema, name=name)

    @staticmethod
    def _split_qualified(qualified: str) -> tuple[str, str]:
        """`"pr.recalc"` -> `("pr", "recalc")`; a bare name gets the `public`
        default Postgres itself would apply."""
        schema, _, name = (qualified or "").strip().rpartition(".")
        return (schema or "public"), name

    def _register_created_object(self, ref) -> None:
        """Record the new object in the deploy manifest so the existing §18.3
        drift/deploy flow can see it (FQ-002).

        Without this the object is invisible to versioning: the local-file
        pipeline tracks objects through `ProjectSettings.deployed`, which is
        otherwise only ever populated by checking out something that already
        exists in the DB, and `compute_drift_markers` iterates that mapping
        alone. The sentinel is an empty `content_hash` -- "local exists, no
        last-deployed reference yet" -- which that function already renders as
        `*`-only with no special-casing, since the object is absent from the
        live schema and so cannot read as live-drifted.

        No project open means no manifest to write to, which is not an error:
        creating an object projectless is a supported, unversioned flow.
        """
        if self._ddl_project_folder is None or self._ddl_project_settings is None:
            return
        schema = self._ddl_schema
        if schema is None:
            return
        relpath = self._ddl_checkout_relpath(ref, schema)
        if relpath is None or relpath in self._ddl_project_settings.deployed:
            return
        self._ddl_project_settings.deployed[relpath] = DeployedObject(content_hash="")
        save_settings(self._ddl_project_folder, self._ddl_project_settings)

    def _on_ddl_checkout_requested(self, ref, source) -> None:
        """Right-click ▸ Check Out for Versioning (spec §18.2) -- the
        project-aware second variant of the Edit… gesture. Requires an open
        project (offers Create…/Open…/Cancel if none is), then performs the
        checkout and opens the same editable tab pointed at the checked-out
        file instead of the live definition."""
        self._require_ddl_project(lambda: self._checkout_and_edit(ref, source))

    def _ddl_checkout_relpath(self, ref, schema) -> str:
        """The object's `ddl/*.sql` relative path, computed via
        `db/ddl_project.py`'s naming scheme (§18.2). Routines need the WHOLE
        current routine set for correct overload disambiguation; if `ref`'s
        own signature is missing from `schema` (stale/unavailable), fall
        back to a single-routine set built from `ref`'s own identity so the
        sole-holder case still resolves."""
        if ref.is_trigger:
            return trigger_ddl_path(ref.schema, ref.table, ref.name)
        routines = schema.routines if schema is not None else {}
        signature = f"{ref.schema}.{ref.name}({', '.join(ref.arg_types)})"
        if not any(r.signature == signature for r in routines.values()):
            routines = {
                signature: RoutineInfo(schema=ref.schema, name=ref.name, arg_types=list(ref.arg_types))
            }
        return routine_ddl_paths(routines)[signature]

    def _checkout_and_edit(self, ref, source) -> None:
        schema = getattr(self.ddl_browser_panel, "_schema", None)
        relpath = self._ddl_checkout_relpath(ref, schema)
        ddl_path = (self._ddl_project_folder / relpath).resolve()
        key = str(ddl_path)

        existing = self.center_stage.ddl_object_tab(key)
        if existing is not None:
            self.center_stage.setCurrentWidget(existing)
            return

        if ddl_path.exists():
            # File present -> open from disk. The local file is the
            # editable truth and is never silently overwritten from the DB.
            text = ddl_path.read_text(encoding="utf-8")
        else:
            # File absent -> seed from the live introspected definition.
            # That write IS the checkout (§18.2).
            ddl_path.parent.mkdir(parents=True, exist_ok=True)
            ddl_path.write_text(source, encoding="utf-8")
            text = source

        self._report_ddl_checkout_drift(ref, relpath, source)

        def resolver():
            return ddl_path

        panel = self.center_stage.open_ddl_object_tab(
            ref, text, resolve_save_path=resolver, key=key
        )
        panel.set_schema_index(self._ddl_schema_index)
        panel.dirty_changed.connect(
            lambda _dirty, ref=ref, key=key: self.center_stage.update_ddl_object_tab(ref, key=key)
        )
        panel.format_refused.connect(self._report_ddl_format_refusal)
        self._wire_ddl_object_panel_reporting(panel, ref)

    def _report_ddl_checkout_drift(self, ref, relpath, live_source) -> None:
        """Checkout semantics step 4 (§18.2): if the live DB has drifted from
        the last-deployed reference, surface it -- an Audit line -- but
        never block editing. The `!` marker itself is rendered on
        BrowserPanel's tree (§18.2/§18.8)."""
        entry = self._ddl_project_settings.deployed.get(relpath) if self._ddl_project_settings else None
        if entry is None:
            return
        if content_hash(live_source) != entry.content_hash:
            self.audit_panel.addItem(
                QListWidgetItem(
                    f"[Project] Live DB definition for {ref.qualified} has drifted "
                    f"from the last-deployed reference -- surfaced, not auto-resolved."
                )
            )

    def _save_ddl_object_editor(self, panel) -> bool:
        """Ctrl+S / File ▸ Save for the active DDL object tab (spec §18.5):
        Save As… on the first save, then silent writes to the remembered
        path thereafter. Never touches a database. Returns True on success,
        False if the user cancelled Save As… -- callers (the close-
        confirmation flow) must treat that exactly like Close ▸ Cancel, not
        as a completed save."""
        path = panel.resolve_save_path()
        if path is None:
            return False  # Save As… cancelled: not an error, nothing written
        try:
            path.write_text(panel.text(), encoding="utf-8", newline="")
        except OSError as exc:
            modals.QMessageBox.critical(self, "Save Failed", f"Could not save:\n\n{exc}")
            return False
        panel.remember_save_path(path)
        panel.mark_clean()
        self.center_stage.update_ddl_object_tab(panel.ref)
        self.statusBar().showMessage(f"Saved {path}", 5000)
        return True

    def _confirm_close_ddl_object(self, ref) -> str:
        """Ask the user how to resolve unsaved changes in a DDL object tab
        before closing. Returns "save", "discard", or "cancel" (mirrors
        `_confirm_close`/`_confirm_close_xsd`, so tests can monkeypatch this
        instead of ever driving a real modal)."""
        result = modals.QMessageBox.question(
            self,
            "Unsaved Changes",
            f"{ref.qualified} has unsaved changes. Save before closing?",
            modals.QMessageBox.StandardButton.Save
            | modals.QMessageBox.StandardButton.Discard
            | modals.QMessageBox.StandardButton.Cancel,
        )
        if result == modals.QMessageBox.StandardButton.Save:
            return "save"
        if result == modals.QMessageBox.StandardButton.Discard:
            return "discard"
        return "cancel"

    def _on_ddl_object_close_requested(self, key) -> None:
        """DDL object tab ✕ clicked. Reuses the Edit-XSD save/discard/cancel
        pattern (`_on_xsd_close_requested`) -- and, per §18.5, a Save As…
        cancelled from this prompt ABORTS THE CLOSE exactly like Cancel would,
        so a dismissed file dialog can never silently discard an edit."""
        panel = self.center_stage.ddl_object_tab(key)
        if panel is None:
            return
        if panel.is_dirty():
            choice = self._confirm_close_ddl_object(panel.ref)
            if choice == "cancel":
                return
            if choice == "save":
                if not self._save_ddl_object_editor(panel):
                    return  # Save As… cancelled: stays open and dirty
        self.center_stage.close_ddl_object_tab(key)

    def _report_ddl_format_refusal(self, issues) -> None:
        """Format Selection refusal (§18.4/§18.5): one `[SQL]`-prefixed Audit
        line per Issue -- never clickable, no line role (carve-out 6); the
        offending span is already underlined in the tab itself."""
        for issue in issues:
            item = QListWidgetItem(
                f"{_SQL_REFUSAL_PREFIX}line {issue.start_line}: {issue.message}"
            )
            self.audit_panel.addItem(item)

    # --- §18.5 D3a: the two Audit channels of a Check run -------------------
    def _report_check_lines(self, lines) -> None:
        """The NARRATIVE channel (`DdlObjectEditorPanel.check_reported`).

        The lines arrive ALREADY prefixed with `[Check] ` (the panel owns that
        reservation), so they are appended verbatim -- never re-prefixed -- and
        carry NO roles: narrative lines are unclickable, exactly the treatment
        `[SQL]` refusals and the `[Find]` summary line get (carve-out 6)."""
        for line in lines:
            self.audit_panel.addItem(QListWidgetItem(str(line)))

    def _report_check_findings(self, findings, ref) -> None:
        """The CLICKABLE channel (`DdlObjectEditorPanel.check_findings`).

        One Audit line per duck-typed `db/ddl_check.py::CheckFinding`, with the
        buffer line on `UserRole` and the object's `DdlObjectRef.key` on
        `UserRole+1` so `_on_audit_item_clicked` can focus that object's tab and
        place the caret (§18.5 D3a). `UserRole+2` is left alone -- it is Verify
        XSD's mode slot.

        A finding whose line could not be mapped (`line is None`) is rendered
        with no line and **neither role**, so it is inert rather than navigating
        somewhere wrong."""
        key = getattr(ref, "key", None)
        for finding in findings:
            severity = str(getattr(finding, "severity", "") or "").strip().lower()
            # Unknown severity -> WARNING (D3a: never silently INFO). The
            # level->severity decision itself stays in `severity_for_level`.
            token = _CHECK_SEVERITY_TOKENS.get(severity, "WARNING")
            message = getattr(finding, "message", "") or ""
            # `lineno` is `CheckFinding`'s BUFFER-line alias and wins; `line` is
            # the same fact on a `(severity, line, message)` test stub. The raw
            # `source_lineno` is a prosrc-relative trap and is never read here.
            line = getattr(finding, "lineno", None)
            if line is None:
                line = getattr(finding, "line", None)
            if line is None:
                item = QListWidgetItem(f"{CHECK_PREFIX}{token}: {message}")
                self.audit_panel.addItem(item)
                continue
            item = QListWidgetItem(f"{CHECK_PREFIX}{token} line {line}: {message}")
            item.setData(Qt.ItemDataRole.UserRole, line)
            item.setData(Qt.ItemDataRole.UserRole + 1, key)
            self.audit_panel.addItem(item)

    def _navigate_to_ddl_object(self, key, line) -> None:
        """Focus the DDL object tab whose `ref.key` is `key` and place the
        caret on `line` (§18.5 D3a's click-to-navigate).

        Resolved by **`panel.ref.key` identity** over the open panels, NOT by
        tab key: a checked-out object's tab is keyed on its `ddl/*.sql` path
        (§18.2), so a `ddl_object_tab(key)` lookup would miss exactly that case.

        If no tab is open for the object, this does NOTHING -- falling through
        to Raw XML would navigate a different document, and reopening would
        resurrect a tab the user closed. Neither is an honest answer."""
        for panel in self.center_stage.ddl_object_panels():
            if getattr(getattr(panel, "ref", None), "key", None) == key:
                self.center_stage.setCurrentWidget(panel)
                panel.navigate_to_line(line)
                return

    # --- §18.5 D4: the Sandbox SQL Console ----------------------------------
    def _sandbox_console_available(self) -> bool:
        """Whether a live `SandboxSession` can be had right now.

        The console is **absent, not disabled**, without one (§18.5 D4's safety
        boundary / carve-out 2), so this is what its menu action's VISIBILITY
        and every object tab's bridge seam are gated on."""
        provider = self._sandbox_session_provider
        if provider is None:
            return False
        try:
            return provider() is not None
        except Exception:  # pragma: no cover - a broken injected seam
            return False

    def _open_sandbox_sql_console(self):
        """Database ▸ Sandbox SQL Console… -- open, or focus, the single
        console tab. Returns the panel, or None (creating NOTHING) when there
        is no live session: a console that refuses every Run is worse than no
        console at all."""
        if not self._sandbox_console_available():
            self.statusBar().showMessage(
                "No sandbox session — open the project's sandbox from "
                "Database ▸ Project Status… first.",
                5000,
            )
            return None
        panel = self.center_stage.open_sandbox_sql_tab(
            session_provider=self._sandbox_session_provider
        )
        panel.set_schema_index(self._ddl_schema_index)
        # Idempotent: `open_sandbox_sql_tab` is single-instance, so a re-invoke
        # hands back the SAME panel and must not stack a second connection.
        if not getattr(panel, "_pgtp_refusal_wired", False):
            panel.format_refused.connect(self._report_ddl_format_refusal)
            panel._pgtp_refusal_wired = True
        panel.set_session_available(True)
        panel.focus_editor()
        return panel

    def _run_selection_in_sandbox_console(self, sql: str) -> None:
        """The object tab's "Run in Sandbox Console" bridge (§18.5 D4).

        Copies text and focuses the console -- it **executes nothing**: there is
        exactly one execution surface and pressing Run on it is the user's act,
        not this bridge's. APPENDS rather than replaces, so a second push cannot
        destroy the first."""
        panel = self._open_sandbox_sql_console()
        if panel is None:
            return
        panel.append_sql(sql)
        panel.focus_editor()

    def _refresh_sandbox_console_affordances(self) -> None:
        """Make the console's presence follow the session's (§18.5 D4).

        Shows/hides the menu action, wires/unwires every open object tab's
        bridge seam, and -- if the session died under an already-open console --
        CLOSES it, rather than leaving a console that refuses every Run."""
        available = self._sandbox_console_available()
        if self._sandbox_console_action is not None:
            self._sandbox_console_action.setVisible(available)
        seam = self._run_selection_in_sandbox_console if available else None
        for panel in self.center_stage.ddl_object_panels():
            panel.set_run_in_console(seam)
        if not available and self.center_stage.sandbox_sql_tab() is not None:
            self.center_stage.close_sandbox_sql_tab()

    def _wire_ddl_object_panel_reporting(self, panel, ref) -> None:
        """Connect a freshly opened DDL object tab's §18.5 reporting channels,
        its D4 console bridge and its sandbox apply seams. Shared by both
        tab-open sites (Edit… and Check Out for Versioning) so the two can
        never drift apart."""
        panel.check_reported.connect(self._report_check_lines)
        panel.check_findings.connect(
            lambda findings, ref=ref: self._report_check_findings(findings, ref)
        )
        if self._sandbox_console_available():
            panel.set_run_in_console(self._run_selection_in_sandbox_console)
        self._wire_ddl_object_apply_seams(panel)

    # --- §18.5 D2/D3a: the SandboxController's session and its gestures ------
    def _refresh_sandbox_affordances(self) -> None:
        """The single "make every sandbox-dependent affordance match the
        session's actual state" entry point -- called on every session-state
        change and whenever the project binding changes.

        Everything here binds VISIBILITY, never enabled-state (§18.5 carve-out
        2: with no live session the control is ABSENT, not greyed out)."""
        controller = self.sandbox_controller
        has_session = controller.has_session
        if self._sandbox_check_action is not None:
            self._sandbox_check_action.setVisible(controller.can_check)
        if self._open_sandbox_session_action is not None:
            self._open_sandbox_session_action.setVisible(
                not has_session and bool(self._configured_sandbox_params())
            )
        if self._close_sandbox_session_action is not None:
            self._close_sandbox_session_action.setVisible(has_session)
        for panel in self.center_stage.ddl_object_panels():
            self._wire_ddl_object_apply_seams(panel)
        self._refresh_sandbox_console_affordances()

    def _configured_sandbox_params(self):
        """The open project's sandbox `ConnectionParams`, or None when there is
        no project or its sandbox has no host -- the same "configured means a
        host is set" reading `refresh_project_capability_status` uses, so the
        two can never disagree about whether a sandbox exists."""
        settings = self._ddl_project_settings
        if settings is None or not settings.sandbox.host:
            return None
        return settings.sandbox

    def _bind_sandbox_controller_to_project(self) -> None:
        """Point the controller at the currently-open project (or at nothing).

        `set_project` drops any session belonging to the previous project and
        deliberately opens/provisions nothing, so this is safe on every project
        transition -- no connection happens as a side effect of a project
        opening."""
        settings = self._ddl_project_settings
        if settings is None:
            self.sandbox_controller.clear_project()
        else:
            self.sandbox_controller.set_project(
                sandbox_params=settings.sandbox,
                target_params=settings.target,
                mode=settings.sandbox_mode,
                configured=bool(settings.sandbox.host),
            )
        self._refresh_sandbox_affordances()

    def _open_sandbox_session(self) -> None:
        """Database ▸ Open Sandbox Session -- probe, then open the one session
        through the controller's single ownership gate. The outcome (including
        every distinguishable refusal reason) lands in the Audit panel via
        `_on_sandbox_operation_finished`; nothing is swallowed."""
        if self._configured_sandbox_params() is None:
            self.statusBar().showMessage(
                "No sandbox configured for this project — set one up in "
                "Project Settings.",
                5000,
            )
            return
        self.sandbox_controller.open_session()

    def _confirm_destructive_sandbox_operation(self, warning: str) -> bool:
        """The controller's `confirm_destructive` gate. A controller with no
        gate refuses every destructive operation, so this must exist for
        Reset/data-clone to be possible at all -- and it never guesses: the
        warning text is the controller's own."""
        return (
            modals.QMessageBox.question(
                self,
                "Sandbox Operation",
                warning,
                modals.QMessageBox.StandardButton.Yes | modals.QMessageBox.StandardButton.No,
            )
            == modals.QMessageBox.StandardButton.Yes
        )

    def _on_sandbox_session_changed(self, _available: bool) -> None:
        """The session came up or went away: every sandbox-dependent
        affordance follows it in one place."""
        self._refresh_sandbox_affordances()

    def _on_sandbox_operation_finished(self, result) -> None:
        """Route one `SandboxOperationResult` by its `operation` and SURFACE
        its stated reason -- a failed sandbox operation is never swallowed.

        `CHECK` is the one operation whose success is reported elsewhere (the
        panel renders `result.report` over both Audit channels), so only a
        check that produced NO report is reported here -- a refused or crashed
        check must never read as a clean one, and must not be double-reported
        either."""
        operation = getattr(result, "operation", None)
        reason = (getattr(result, "reason", "") or "").strip()
        if operation is SandboxOperation.CHECK:
            if getattr(result, "report", None) is None:
                self.audit_panel.addItem(
                    QListWidgetItem(
                        f"{CHECK_PREFIX}check did not run"
                        + (f": {reason}" if reason else ".")
                    )
                )
            return
        name = operation.value if operation is not None else "sandbox"
        if result.ok:
            text = f"{_SANDBOX_PREFIX}{name}: " + (reason or "done.")
        else:
            text = f"{_SANDBOX_PREFIX}{name} failed" + (f": {reason}" if reason else ".")
        self.audit_panel.addItem(QListWidgetItem(text))

    # --- §18.5 D3: Apply to Sandbox ------------------------------------------
    def _wire_ddl_object_apply_seams(self, panel) -> None:
        """Wire (or unwire) one object tab's apply lane to the live session.

        Only Apply to Sandbox is wired: Apply to Target needs the live-identity
        seam its precondition 1 cannot be enforced without, and an
        unenforceable precondition must remove the gesture rather than weaken
        it (the panel enforces exactly that via `has_target_apply`).

        `set_apply_seams` replaces the whole set and rebuilds the button row, so
        it is only called when the answer actually changes."""
        wanted = self.sandbox_controller.has_session
        if wanted == panel.has_sandbox_apply:
            return
        if wanted:
            panel.set_apply_seams(
                apply_to_sandbox=self._apply_ddl_object_to_sandbox,
                sandbox_database_label=self._sandbox_database_label,
                confirm=self._confirm_sandbox_apply,
            )
        else:
            # Empty set: the seam that went away takes its affordance with it.
            panel.set_apply_seams()

    def _sandbox_database_label(self) -> str:
        """The sandbox database name an apply confirmation must NAME. Read off
        the live session's own params, never off the project file: the
        confirmation must name the database the write will actually hit."""
        session = self.sandbox_controller.session
        if session is not None:
            return session.params.database or ""
        params = self._configured_sandbox_params()
        return params.database if params is not None else ""

    def _confirm_sandbox_apply(self, title: str, text: str) -> bool:
        """The panel's confirmation gate for the apply gestures. The text is
        the PANEL's (it names the object and the database); this only shows it,
        so no confirmation wording is duplicated here."""
        return (
            modals.QMessageBox.question(
                self,
                title,
                text,
                modals.QMessageBox.StandardButton.Yes | modals.QMessageBox.StandardButton.No,
            )
            == modals.QMessageBox.StandardButton.Yes
        )

    def _apply_ddl_object_to_sandbox(self, ref, text):
        """The panel's `apply_to_sandbox(ref, text)` write seam (§18.5 D3).

        Goes through `SandboxSession.apply`, the ONE committing call that runs
        the DDL and its `applied` working-set bookkeeping in a single
        transaction -- never a bare `apply_ddl` that would leave the working set
        lying about what the sandbox contains. The `ref` it takes is the
        `(kind, schema_name, object_name, table_name)` 4-tuple that IS the
        bookkeeping table's primary key.

        Returns a duck-typed `db/apply.py::ApplyOutcome` because the panel
        reports and RECORDS whatever comes back (precondition 2), so a failure
        must come back as a stated outcome rather than an exception. Synchronous
        by the panel's contract -- `apply_to_sandbox()` consumes the return
        value -- so this is the one sandbox write that is not marshalled off the
        GUI thread.
        """
        session = self.sandbox_controller.session
        if session is None:
            # Unreachable through the wiring (the seam is only wired while a
            # session exists), but a stated outcome beats a crash.
            return ApplyOutcome.failed(
                "no sandbox session is open -- nothing was applied"
            )
        key = (ref.kind, ref.schema, ref.name, ref.table or "")
        try:
            session.apply(key, text)
        except Exception as exc:  # noqa: BLE001 -- the DB's message IS the result
            return ApplyOutcome.failed(str(exc) or exc.__class__.__name__)
        return ApplyOutcome.succeeded((), committed=True)

    # --- §18.5 D3a: the Check gesture ----------------------------------------
    def _check_active_ddl_object(self) -> None:
        """Database ▸ Check Object in Sandbox -- run D3a's ladder over the
        ACTIVE object tab's buffer. Exactly one object per run (D3a): there is
        no implicit multi-object sweep.

        The `CheckRequest` is built HERE, not in the controller, because a
        trigger's referenced function is knowledge the ref alone does not carry
        and the controller must not guess it. When it cannot be supplied, the
        request goes out without it and `db/ddl_check.py` reports its own
        "which function does this trigger call?" outcome -- an unavailable tier
        is a reported fact, never a silent no-op.
        """
        panel = self.center_stage.active_ddl_object_panel()
        if panel is None:
            self.statusBar().showMessage(
                "Check runs on an open DDL object tab — open one first.", 5000
            )
            return
        text = panel.text()
        ref = panel.ref
        request = CheckRequest.from_ref(
            ref, text, **self._trigger_function_for(ref, text)
        )

        def on_done(result, panel=panel, text=text) -> None:
            report = getattr(result, "report", None)
            if report is None:
                # The refusal's own reason is reported by
                # `_on_sandbox_operation_finished`; nothing is derived from it
                # here, and an absent report is never shown as a clean check.
                return
            # Record for precondition 2 AND show it: the panel keeps those two
            # acts separate, so both are asked for explicitly.
            panel.record_check_report(report, text)
            panel.report_check_result(report)

        self.sandbox_controller.run_check(request, on_done)

    def _trigger_function_for(self, ref, text) -> dict:
        """`CheckRequest.from_ref` kwargs naming the function a TRIGGER calls.

        Read off the buffer's own `EXECUTE [PROCEDURE|FUNCTION] fn()` clause --
        the statement in the tab is the authority on what this trigger will
        call. Empty for a non-trigger, and empty (never a guess from the
        trigger's own name) when the clause cannot be read: `db/ddl_check.py`
        then reports tier 3 as unavailable with its own reason.
        """
        if not getattr(ref, "is_trigger", False):
            return {}
        match = re.search(
            r"\bEXECUTE\s+(?:PROCEDURE|FUNCTION)\s+([\w\".]+)", text or "", re.I
        )
        if match is None:
            return {}
        qualified = match.group(1).replace('"', "")
        schema, _, name = qualified.rpartition(".")
        if not name:
            return {}
        return {
            "function_schema": schema or ref.schema,
            "function_name": name,
        }

    def _on_db_rename_requested(self, kind, old):
        new = self._prompt_rename(old)
        if not new or new == old:
            return
        current = self.center_stage.xml_editor.toPlainText()
        if kind == "table":
            updated, count = rename_table(current, old, new)
        else:
            updated, count = rename_field(current, old, new)
        _log.info("db: rename %s -> %s (%d replacements)", old, new, count)
        # Write through the buffer so the change marks the document dirty and
        # pushes a snapshot (the editor's textChanged handler does both).
        self.center_stage.xml_editor.setPlainText(updated)
        self.statusBar().showMessage(
            f"Renamed {kind} '{old}' → '{new}' ({count} occurrence(s)).", 5000
        )
        # Re-run the coherence check so the rename's effect shows immediately.
        # Gated on a prior run: without a cached schema there is nothing the
        # user asked to keep in sync (§17).
        if self._last_db_schema is not None:
            self._run_db_check()

    def _on_db_jump_requested(self, kind, name):
        """Double-click on a DB tree node: list EVERY occurrence of the node's
        attribute token in the Find-all results panel, select the first one, and
        seed the Find bar so Find Next / F3 steps through them (reusing the
        existing Find All + Find Next machinery rather than a one-shot jump)."""
        # `kind` is the host-facing vocabulary DbCheckPanel established and §17
        # carried over: a relation is "table". `CoherencePanel` normalizes
        # "relation" -> "table" on the way out (BUG-032 facet A), and
        # "relation" is accepted here as well so a future caller emitting the
        # internal node kind cannot silently reintroduce a fieldName= search
        # for a table name.
        is_table = kind in ("table", "relation")
        token = f'tableName="{name}"' if is_table else f'fieldName="{name}"'
        editor = self.center_stage.xml_editor
        if token not in editor.toPlainText():
            # A genuine miss is now meaningful (it is what an "unreferenced"
            # relation looks like), so say what was searched and what that
            # means instead of the bare "not found" that the token bug made
            # indistinguishable from a malfunction.
            self.statusBar().showMessage(
                f"No {token} in the buffer — the XML does not reference {name}.", 5000
            )
            return
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)
        # Clear any selection so the first Find Next lands on the first match.
        cursor = editor.textCursor()
        cursor.setPosition(0)
        editor.setTextCursor(cursor)
        # Seed the Find bar so Find Next / F3 step through occurrences of the
        # token. show_find()'s prefill is a no-op now that the selection is clear.
        bar = self.center_stage.find_replace_bar
        bar.set_find_text(token)
        bar.show_find()
        # List every occurrence in the bottom panel (reuses Find All), and
        # reveal the panel in case a prior DB check left it hidden.
        self._populate_find_all_results(token)
        self.audit_dock.setVisible(True)
        # Select the first occurrence; F3 (Find Next) continues from there.
        bar.find_next()
        editor.setFocus()

    # -- Create page/detail/lookup from a DB table (SP3) ---------------------

    def _confirm_duplicate_page(self, table_name):
        """Warn that a page for `table_name` already exists; return True to
        proceed (with a de-duplicated fileName) or False to cancel. Test seam —
        patched to bypass the modal."""
        choice = modals.QMessageBox.question(
            self,
            "Page Already Exists",
            f"A page for '{table_name}' already exists in this project.\n\n"
            "Create another one anyway (with a de-duplicated fileName)?",
            modals.QMessageBox.StandardButton.Yes | modals.QMessageBox.StandardButton.No,
            modals.QMessageBox.StandardButton.No,
        )
        return choice == modals.QMessageBox.StandardButton.Yes

    def _on_db_create_requested(self, what, name):
        """Right-click on a relation node in the coherence view's Tables and
        Views branch: synthesize a page (insert into the buffer) or a
        detail/lookup (copy to clipboard)."""
        schema = self._last_db_schema
        if schema is None or schema.table(name) is None:
            self.statusBar().showMessage(
                f"No schema for '{name}' — run Database/XML Coherence first.", 5000
            )
            return
        try:
            if what == "page":
                self._create_page_from_table(schema, name)
            elif what == "detail":
                element = table_gen.build_detail(schema, name)
                self._copy_fragment_to_clipboard(element, "Detail", name)
            elif what == "lookup":
                element = table_gen.build_lookup(schema, name)
                self._copy_fragment_to_clipboard(element, "Lookup", name)
        except table_gen.GenerationError as exc:
            self.statusBar().showMessage(f"Could not create {what}: {exc}", 8000)

    def _copy_fragment_to_clipboard(self, element, label, name):
        text = table_gen.serialize(element, indent=0)
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(
            f"{label} for '{name}' copied to clipboard — paste it into the "
            "target page.",
            6000,
        )

    def _create_page_from_table(self, schema, name):
        element = table_gen.build_page(schema, name)
        buffer = self.center_stage.xml_editor.toPlainText()

        file_name = element.get("fileName")
        if f'tableName="{name}"' in buffer or f'fileName="{file_name}"' in buffer:
            if not self._confirm_duplicate_page(name):
                self.statusBar().showMessage("Page creation cancelled.", 3000)
                return
            file_name = self._dedupe_file_name(buffer, file_name)
            element.set("fileName", file_name)

        updated, insert_line = self._insert_page_before_pages_close(buffer, element)
        if updated is None:
            self.statusBar().showMessage(
                "Could not find </Pages> to insert the new page.", 8000
            )
            return
        self.center_stage.xml_editor.setPlainText(updated)
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)
        self.center_stage.xml_editor.navigate_to_line(insert_line)
        self.center_stage.xml_editor.select_enclosing_block()
        self.statusBar().showMessage(f"Page for '{name}' added.", 5000)

    @staticmethod
    def _dedupe_file_name(buffer, file_name):
        candidate = file_name
        suffix = 2
        while f'fileName="{candidate}"' in buffer:
            candidate = f"{file_name}_{suffix}"
            suffix += 1
        return candidate

    @staticmethod
    def _insert_page_before_pages_close(buffer, element):
        """Splice a serialized <Page> immediately before </Pages>, indented to
        match the existing <Page> depth. Returns (new_text, page_open_line) or
        (None, 0) if </Pages> is absent."""
        close_index = buffer.rfind("</Pages>")
        if close_index == -1:
            return None, 0
        line_start = buffer.rfind("\n", 0, close_index) + 1
        close_indent = buffer[line_start:close_index]
        indent_depth = close_indent.count("\t") + 1  # one level deeper than </Pages>
        fragment = table_gen.serialize(element, indent=indent_depth)
        new_text = buffer[:line_start] + fragment + "\n" + buffer[line_start:]
        page_open_line = buffer.count("\n", 0, line_start) + 1
        return new_text, page_open_line

    def _build_tools_menu(self):
        menu = self.menuBar().addMenu("Tools")
        manage_captions_action = menu.addAction("Manage Captions...")
        manage_captions_action.triggered.connect(self._enter_caption_mode)
        caption_filter_action = menu.addAction("Caption Filter…")
        caption_filter_action.triggered.connect(self._open_caption_filter_dialog)
        menu.addSeparator()
        validate_action = menu.addAction("Validate Project")
        validate_action.triggered.connect(self._validate_project)
        menu.addSeparator()
        reparse_action = menu.addAction("Reparse Raw XML into Tree")
        reparse_action.triggered.connect(self._reparse_raw_xml)
        menu.addSeparator()
        compare_action = menu.addAction("Compare / Merge Two Files...")
        compare_action.triggered.connect(self._compare_merge_two_files)
        next_action = menu.addAction("Next Difference")
        next_action.triggered.connect(self.center_stage.diff_merge_panel.select_next_difference)
        prev_action = menu.addAction("Prev Difference")
        prev_action.triggered.connect(self.center_stage.diff_merge_panel.select_previous_difference)
        apply_action = menu.addAction("Apply Changes to Target")
        apply_action.triggered.connect(self._apply_changes_to_target)

    def _build_bookmarks_menu(self):
        # Each action resolves the target editor at TRIGGER time via
        # _active_bookmark_editor, not at build time -- the shared gutter base
        # (§8) puts the same bookmark API on the Raw XML, Edit XSD and DDL
        # Explorer editors, so the menu follows whichever is active instead of
        # being bound to Raw XML forever.
        menu = self.menuBar().addMenu("Bookmarks")

        toggle_action = menu.addAction("Toggle Bookmark")
        toggle_action.setShortcut("Ctrl+F2")
        toggle_action.triggered.connect(
            lambda: self._active_bookmark_editor().toggle_bookmark_at_cursor()
        )

        next_action = menu.addAction("Next Bookmark")
        next_action.setShortcut("F2")
        next_action.triggered.connect(
            lambda: self._active_bookmark_editor().goto_next_bookmark()
        )

        prev_action = menu.addAction("Previous Bookmark")
        prev_action.setShortcut("Shift+F2")
        prev_action.triggered.connect(
            lambda: self._active_bookmark_editor().goto_prev_bookmark()
        )

        menu.addSeparator()
        clear_action = menu.addAction("Clear All Bookmarks")
        clear_action.triggered.connect(
            lambda: self._active_bookmark_editor().clear_bookmarks()
        )

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
        menu.addSeparator()
        locate_pangen_action = menu.addAction("Locate panGen Runtime...")
        locate_pangen_action.triggered.connect(self._locate_pangen_runtime)
        pangen_action = menu.addAction("panGen (Generate Own PHP)")
        pangen_action.triggered.connect(self._pangen)
        re_phpgen_action = menu.addAction("rePHPgen (Analyze Gap)")
        re_phpgen_action.triggered.connect(self._re_phpgen_analyze)
        self._save_rejson_action = menu.addAction("Save reJSON...")
        self._save_rejson_action.triggered.connect(self._save_rejson)
        self._save_rejson_action.setEnabled(False)

    def _locate_generator(self) -> None:
        path, _filter = modals.QFileDialog.getOpenFileName(
            self, "Locate PHP Generator Executable", "", "Executables (*.exe);;All files (*)"
        )
        if not path:
            return
        save_executable_path(path, base_dir=self._generator_config_dir)
        self.statusBar().showMessage(f"PHP Generator set: {Path(path).name}", 5000)

    def _project_output_folder_default(self) -> str:
        """Prefill for the output-folder dialog: when a local §18.2 project
        is open, its folder wins ahead of both fallbacks below -- still a
        prefill, not a silent redirect (the picker itself is unchanged, the
        user can always choose differently). Otherwise: the project's
        Project@outputPath if readable, else the directory of the current
        project file, else ''. Inert in no-project mode (§18.2's "no-project
        mode is completely unaffected" principle)."""
        if self._ddl_project_folder is not None:
            return str(self._ddl_project_folder)
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
            modals.QMessageBox.information(
                self,
                "Generate PHP",
                "Locate the PHP Generator executable first (Generation > Locate PHP Generator Executable...).",
            )
            return

        # 3. Save vs Save As vs Cancel so on-disk content matches the editor.
        choice = modals.QMessageBox.question(
            self,
            "Save Before Generating",
            "The generator reads the project from disk. Save the current editor "
            "contents before generating?",
            modals.QMessageBox.StandardButton.Save
            | modals.QMessageBox.StandardButton.SaveAll  # used as the "Save As..." button
            | modals.QMessageBox.StandardButton.Cancel,
        )
        if choice == modals.QMessageBox.StandardButton.Cancel:
            return
        if choice == modals.QMessageBox.StandardButton.SaveAll:
            self._save_project_as()
        else:
            self._save_project()  # delegates to Save As when there's no path yet
        if not self._current_project_path:
            return  # Save As was cancelled -> nothing on disk to generate from

        # 4. Output folder (prefilled).
        output_folder = modals.QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self._project_output_folder_default()
        )
        if not output_folder:
            return

        # 5. Run via the injected runner.
        self._clear_generator_output()
        command = build_generate_command(exe, self._current_project_path, output_folder)
        self._current_output_folder = output_folder
        self._is_generating = True
        self.statusBar().showMessage("Generating PHP…")
        _log.info("generate: started")
        self._generator_runner.run(
            command,
            on_output=self._append_generator_output,
            on_finished=self._on_generation_finished,
        )

    def _append_generator_output(self, line: str) -> None:
        self.audit_panel.addItem(f"{_GENERATOR_OUTPUT_PREFIX}{line}")

    def _on_generation_finished(self, exit_code: int) -> None:
        _log.info("generate: rc=%s", exit_code)
        self._is_generating = False
        self.audit_panel.addItem(f"{_GENERATOR_OUTPUT_PREFIX}Generation finished (exit {exit_code})")
        if exit_code == 0:
            modals.QMessageBox.information(self, "Generate PHP", "Generation succeeded.")
            self.statusBar().showMessage("Generation succeeded", 5000)
        else:
            modals.QMessageBox.critical(
                self,
                "Generate PHP",
                f"Generation failed (exit {exit_code}). See the Audit / Problems panel for the generator log.",
            )
            self.statusBar().showMessage(f"Generation failed (exit {exit_code})", 5000)

    def _open_output_folder(self) -> None:
        if not self._current_output_folder:
            self.statusBar().showMessage("No output folder yet — run Generate PHP first.", 5000)
            return
        modals.QDesktopServices.openUrl(QUrl.fromLocalFile(self._current_output_folder))

    # -- panGen / rePHPgen (own generator + gap analysis) --------------------

    def _gap_json_work_path(self) -> Path:
        """Scratch path for the analyze command's JSON output (next to the
        generator config, out of the user's project tree)."""
        return generator_config_path(self._generator_config_dir).parent / "last_gap.json"

    def _re_phpgen_runtime(self) -> tuple[str, str, dict[str, str]] | None:
        """(python, root, extra_env) or None after showing guidance."""
        root = load_re_phpgen_root(base_dir=self._generator_config_dir)
        if not validate_re_phpgen_root(root):
            modals.QMessageBox.information(
                self,
                "panGen",
                "re_phpgen runtime not found. Set it via "
                "Generation > Locate panGen Runtime...",
            )
            return None
        python = resolve_re_phpgen_python(root)
        # Merge-prepend PYTHONPATH: our src first (wins shadowing), user's
        # pre-existing entries preserved (never clobber their environment).
        src = str(Path(root) / "src")
        existing = os.environ.get("PYTHONPATH", "")
        pythonpath = src + (os.pathsep + existing if existing else "")
        return python, root, {"PYTHONPATH": pythonpath}

    def _prepare_generation_run(self) -> str | None:
        """Shared preamble: in-flight guard, open project, save prompt, output
        folder. Returns the output folder or None. Mirrors _generate_php steps
        (no vendor-exe check)."""
        if self._is_generating:
            self.statusBar().showMessage("A generation is already in progress.", 5000)
            return None
        if self._current_project is None and not self.center_stage.xml_editor.toPlainText().strip():
            self.statusBar().showMessage("Open a project first.", 5000)
            return None
        choice = modals.QMessageBox.question(
            self,
            "Save Before Running",
            "panGen reads the project from disk. Save the current editor contents first?",
            modals.QMessageBox.StandardButton.Save
            | modals.QMessageBox.StandardButton.SaveAll
            | modals.QMessageBox.StandardButton.Cancel,
        )
        if choice == modals.QMessageBox.StandardButton.Cancel:
            return None
        if choice == modals.QMessageBox.StandardButton.SaveAll:
            self._save_project_as()
        else:
            self._save_project()
        if not self._current_project_path:
            return None
        output_folder = modals.QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self._project_output_folder_default()
        )
        return output_folder or None

    def _pangen(self) -> None:
        runtime = self._re_phpgen_runtime()
        if runtime is None:
            return
        python, root, extra_env = runtime
        output_folder = self._prepare_generation_run()
        if output_folder is None:
            return
        self._clear_generator_output()
        self._current_output_folder = output_folder
        self._is_generating = True
        self.statusBar().showMessage("panGen: generating…")
        _log.info("pangen: started")
        self._generator_runner.run(
            build_pangen_command(python, self._current_project_path, output_folder),
            on_output=self._append_generator_output,
            on_finished=self._on_pangen_finished,
            cwd=root,
            extra_env=extra_env,
        )

    def _on_pangen_finished(self, exit_code: int) -> None:
        _log.info("pangen: rc=%s", exit_code)
        self._is_generating = False
        if exit_code == 0:
            self.statusBar().showMessage("panGen finished", 5000)
        else:
            modals.QMessageBox.warning(
                self,
                "panGen",
                f"panGen failed (exit {exit_code}). See the Audit / Problems panel "
                "for the generator log.",
            )
            self.statusBar().showMessage(f"panGen failed (exit {exit_code})", 5000)

    def _re_phpgen_analyze(self) -> None:
        runtime = self._re_phpgen_runtime()
        if runtime is None:
            return
        python, root, extra_env = runtime
        output_folder = self._prepare_generation_run()
        if output_folder is None:
            return
        if Path(output_folder).name == PANGEN_SUBFOLDER:
            modals.QMessageBox.information(
                self, "rePHPgen",
                "This is panGen's own output subfolder — select the folder that "
                "contains the vendor-generated .php files instead.",
            )
            return
        if not any(Path(output_folder).glob("*.php")):
            modals.QMessageBox.information(
                self,
                "rePHPgen",
                "No vendor output found in this folder. Generate the project from "
                "the PHP Generator GUI into this folder first, then run rePHPgen.",
            )
            return

        self._clear_generator_output()
        self._current_output_folder = output_folder
        self._is_generating = True
        self._save_rejson_action.setEnabled(False)
        json_path = self._gap_json_work_path()
        pgtp = self._current_project_path
        pangen_command = build_pangen_command(python, pgtp, output_folder)
        analyze_command = build_analyze_command(python, pgtp, output_folder, str(json_path))
        self.statusBar().showMessage("rePHPgen: generating…")
        _log.info("re_phpgen: pangen started")

        def _on_analyze_finished(exit_code: int) -> None:
            _log.info("re_phpgen: analyze rc=%s", exit_code)
            self._is_generating = False
            if exit_code != 0:
                modals.QMessageBox.warning(
                    self,
                    "rePHPgen",
                    f"Gap analysis failed (exit {exit_code}). See the Audit / "
                    "Problems panel for the log.",
                )
                self.statusBar().showMessage(f"rePHPgen failed (exit {exit_code})", 5000)
                return
            self._last_gap_json = json_path
            self._save_rejson_action.setEnabled(True)
            summary = summarize_gap_json(json_path)
            self._append_generator_output(summary.replace("\n", " | "))
            self.statusBar().showMessage("rePHPgen: gap analysis complete", 5000)
            modals.QMessageBox.information(self, "rePHPgen — Gap Summary", summary)

        def _on_pangen_done(exit_code: int) -> None:
            _log.info("re_phpgen: pangen rc=%s", exit_code)
            if exit_code != 0:
                self._is_generating = False
                modals.QMessageBox.warning(
                    self,
                    "rePHPgen",
                    f"panGen failed (exit {exit_code}). See the Audit / Problems "
                    "panel for the generator log.",
                )
                self.statusBar().showMessage(f"rePHPgen failed (exit {exit_code})", 5000)
                return
            _log.info("re_phpgen: analyze started")
            self._generator_runner.run(
                analyze_command,
                on_output=self._append_generator_output,
                on_finished=_on_analyze_finished,
                cwd=root,
                extra_env=extra_env,
            )

        self._generator_runner.run(
            pangen_command,
            on_output=self._append_generator_output,
            on_finished=_on_pangen_done,
            cwd=root,
            extra_env=extra_env,
        )

    def _save_rejson(self) -> None:
        if self._last_gap_json is None or not Path(self._last_gap_json).is_file():
            self.statusBar().showMessage("No gap JSON yet — run rePHPgen first.", 5000)
            return
        stem = Path(self._current_project_path).stem if self._current_project_path else "project"
        default_dir = self._current_output_folder or ""
        path, _filter = modals.QFileDialog.getSaveFileName(
            self,
            "Save reJSON",
            str(Path(default_dir) / f"{stem}_gap.json"),
            "JSON (*.json)",
        )
        if not path:
            return
        Path(path).write_text(
            Path(self._last_gap_json).read_text(encoding="utf-8"), encoding="utf-8"
        )
        self.statusBar().showMessage(f"Saved reJSON to {Path(path).name}", 5000)

    def _locate_pangen_runtime(self) -> None:
        root = modals.QFileDialog.getExistingDirectory(
            self,
            "Locate panGen Runtime (re_phpgen repo)",
            load_re_phpgen_root(base_dir=self._generator_config_dir),
        )
        if not root:
            return
        if not validate_re_phpgen_root(root):
            modals.QMessageBox.warning(
                self,
                "panGen",
                "That folder does not look like the re_phpgen repo "
                "(missing src\\re_phpgen).",
            )
            return
        save_re_phpgen_root(root, base_dir=self._generator_config_dir)
        self.statusBar().showMessage(f"panGen runtime set: {root}", 5000)

    def _build_help_menu(self):
        menu = self.menuBar().addMenu("Help")
        manual_action = menu.addAction("Manual")
        manual_action.setShortcut("F1")
        manual_action.triggered.connect(self._show_manual)
        logs_action = menu.addAction("Open Log Folder")
        logs_action.triggered.connect(self._open_log_folder)
        about_action = menu.addAction("About")
        about_action.triggered.connect(lambda: show_about_dialog(self))

    def _open_log_folder(self, checked=False, opener=None) -> None:
        """Open the diagnostic log directory in the system file browser.
        ``opener`` is an injectable seam so tests never spawn Explorer."""
        from PySide6.QtCore import QUrl

        from pgtp_editor import debuglog

        target = debuglog.log_dir()
        target.mkdir(parents=True, exist_ok=True)
        open_fn = opener if opener is not None else modals.QDesktopServices.openUrl
        open_fn(QUrl.fromLocalFile(str(target)))

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
