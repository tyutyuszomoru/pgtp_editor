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

import logging
import os
import re
import shutil
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer
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
from pgtp_editor.model.encoding import read_pgtp_text
from pgtp_editor.model.line_index import node_at_line
from pgtp_editor.model.parser import (
    PgtpParseError,
    load_project,
    load_project_from_text,
)
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
from pgtp_editor.db.introspect import test_connection as db_test_connection
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
from pgtp_editor.ui.sandbox_setup_dialog import SandboxSetupDialog
from pgtp_editor.ui.new_routine_dialog import NewRoutineDialog
from pgtp_editor.ui.new_trigger_dialog import NewTriggerDialog
from pgtp_editor.ui.project_status_model import SandboxFact, build_diagram, quality_state
from pgtp_editor.ui.project_status_panel import ProjectStatusPanel
from pgtp_editor.ui.project_settings_dialog import ProjectSettingsDialog
from pgtp_editor.ui.coherence_controller import CoherenceController
from pgtp_editor.ui.coherence_panel import CoherencePanel
from pgtp_editor.ui.diff_merge_controller import DiffMergeController
from pgtp_editor.ui.find_controller import FindValidateController
from pgtp_editor.ui.ddl_buffer_panel import BrowserPanel
from pgtp_editor.ui.code_editor import CodeEditorDialog
from pgtp_editor.ui.history import SnapshotHistory
# §21/§22: the custom-PHP editing lane and the PHP lint lane. `LINT_AUDIT_TARGET`
# is the `UserRole + 1` tag a `[Lint]` Audit row carries, read by
# `_on_audit_item_clicked` to route the click to a PHP tab.
from pgtp_editor.lint.findings import LINT_AUDIT_TARGET
from pgtp_editor.ui.generation_controller import GenerationController
from pgtp_editor.ui.lint_controller import LintController
from pgtp_editor.ui.php_tab_controller import PhpTabController
from pgtp_editor.ui.toolbar_controller import ToolbarController
from pgtp_editor.ui.ui_shell import UiShell
from pgtp_editor.ui.xsd_controller import XsdController
from pgtp_editor.ui.event_body import (
    extract_event_body,
    insert_event_handler,
    replace_event_body,
)
from pgtp_editor.model.nodes import classify_event_side
from pgtp_editor.model.event_handlers import language_for_side
from pgtp_editor.ui import caption_scan
from pgtp_editor.ui.project_tree import ProjectTreePanel
from pgtp_editor.ui.properties_panel import PropertiesPanel
from pgtp_editor.ui.theme import apply_theme

_log = logging.getLogger(__name__)

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
        # Injectable root of the schema artifacts (curated.xsd / learned.xsd /
        # schema_model.json). Stays a HOST constructor seam -- it is a
        # constructor parameter the whole suite reads off the finished window --
        # and is handed to `XsdController`, which owns everything under it.
        self._schema_storage_dir = schema_storage_dir
        # Injectable root of the generator/linter config. Stays a HOST
        # constructor seam (like `_schema_storage_dir`) because TWO lanes read
        # the same directory -- `GenerationController` and `LintController`.
        self._generator_config_dir = generator_config_dir
        # `generator_runner` is NOT stored here: it is handed straight to
        # `GenerationController` below (the local stays in scope), which owns the
        # runner outright -- nothing else on the host touches it.
        # Connection Setup dialog, held so it is not GC'd while shown non-modally.
        self._connection_dialog = None
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
        #: §23's embedded MCP server, OFF BY DEFAULT: the `(server, thread)`
        #: pair `mcp.start_server_thread` returns while a session is running,
        #: None otherwise. Nothing here imports `pgtp_editor.mcp` at startup --
        #: the import happens inside the menu handler, so the GUI never pays for
        #: a feature nobody opted into.
        self._mcp_session = None
        #: Injectable stand-in for `mcp.start_server_thread`; None means "resolve
        #: the real one lazily". Tests assign it so no suite ever enters a real
        #: stdio loop (`serve` would block on stdin).
        self._mcp_start = None
        #: The Tools ▸ Start MCP Server checkable action, assigned by
        #: `_build_tools_menu`.
        self._mcp_action = None
        # Off-thread executor seam. The coherence-check schema fetch opens a
        # connection; running it here would freeze the window on a slow/dead
        # host. Default marshals it to a threadpool worker; tests inject a
        # synchronous stub so the result path stays deterministic.
        self._run_async = run_async
        self.setWindowTitle("PGTP Editor")
        self.resize(1400, 900)

        self.project_tree = ProjectTreePanel(
            on_stub_action=self._not_implemented,
            # Lambdas: the Compare/Merge lane (`_diff_ui`) is constructed after
            # this panel, because it needs the `UiShell` built further down.
            on_compare_page=lambda node: self._diff_ui.compare_page_with(node),
            on_compare_detail=(
                lambda node, source_path: self._diff_ui.compare_detail_with(
                    node, source_path
                )
            ),
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
        # Two jump signals because Qt cannot overload one name: DB-sourced rows
        # carry a (kind, name) pair, XML-sourced rows a 1-based line number.
        # The (kind, name) half -- plus rename and create -- belongs to
        # `CoherenceController` and is wired where that lane is constructed,
        # below; the line-based jump and the Properties feed are the host's.
        self.coherence_panel.jump_requested.connect(self._tree_jump_to_line)
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
        # Lambdas: the find/validate lane (`_find_ui`) owns the whole streaming
        # Find-All run but is constructed after the `UiShell` further down.
        self.center_stage.find_replace_bar.set_on_find_all(
            lambda term: self._find_ui.find_all(term)
        )
        self.center_stage.find_replace_bar.set_on_stop_find_all(
            lambda: self._find_ui.stop_find_all()
        )
        self.center_stage.find_replace_bar.set_on_status(self.statusBar().showMessage)
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
            lambda text: self._find_ui.on_find_selected_text(text)
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
        # Injectable seam (mirrors `CoherenceController.fetch_schema`) -- tests
        # patch this to a canned SandboxCapabilities so no real connection
        # is ever opened.
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
        #: §18.5 D3's "Check without applying" probe, gated on the same
        #: `can_check` as Check itself.
        self._sandbox_probe_check_action = None
        self._open_sandbox_session_action = None
        self._close_sandbox_session_action = None
        #: Database ▸ Sandbox Setup… -- always present (see `_build_database_menu`
        #: for why it is not session-gated), so unlike the four above it needs no
        #: visibility management. Kept on `self` only so the non-modal dialog it
        #: opens outlives the handler's stack frame (the same keep-alive pattern
        #: `_project_settings_dialog` uses).
        self._sandbox_setup_action = None
        self._sandbox_setup_dialog = None

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

        # §9 auto-parse. OFF by default and IN-MEMORY ONLY (no QSettings key --
        # it always starts unchecked, deliberately): a background reparse is a
        # convenience, not a mode to inherit silently from a previous session.
        # The checkable Edit-menu action is created later by `_build_edit_menu`,
        # so the attribute exists as None first -- `blockCountChanged` is
        # connected here and could in principle fire before the menu exists.
        # 400 ms mirrors `_snapshot_timer` above, and the timer RESTARTS on each
        # firing so a burst of edits triggers one reparse after it settles.
        self._auto_parse_action = None
        self._auto_parse_timer = QTimer(self)
        self._auto_parse_timer.setSingleShot(True)
        self._auto_parse_timer.setInterval(400)
        self._auto_parse_timer.timeout.connect(self._auto_parse_now)
        # `blockCountChanged`, not `textChanged`: it fires once when the line
        # count changes (Enter, a multi-line paste, a join) rather than on every
        # keystroke, which is the cheapest signal that correlates with the XML
        # structure having plausibly changed.
        self.center_stage.xml_editor.blockCountChanged.connect(
            self._on_editor_block_count_changed
        )

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

        # Edit XSD tab (spec §11): its own undo/redo routing. The XSD tab has
        # no snapshot history -- it relies solely on the editor's native undo,
        # so its Ctrl+Z/Ctrl+Y re-emission is routed straight back into the
        # editor rather than through _undo/_redo.
        stage = self.center_stage
        stage.xsd_editor.undo_requested.connect(stage.xsd_editor.undo)
        stage.xsd_editor.redo_requested.connect(stage.xsd_editor.redo)
        stage.xsd_find_replace_bar.set_on_status(self.statusBar().showMessage)
        stage.xsd_find_replace_bar.set_on_find_all(
            lambda term: self._find_ui.find_all(term, target="xsd")
        )
        stage.xsd_find_replace_bar.set_on_stop_find_all(
            lambda: self._find_ui.stop_find_all()
        )

        #: The narrow contract every collaborator object gets instead of this
        #: window (see `ui/ui_shell.py`). Built BEFORE the menu bar, because a
        #: collaborator that owns a menu outright builds it (see `_xsd_ui`
        #: below) and so must exist first. Every field is late-bound anyway:
        #: they are bound methods that resolve host state at CALL time, which
        #: is what keeps post-construction seam injection
        #: (`window._run_async = ...`) working for collaborators too -- and is
        #: why `is_light_theme` may be handed over before `_light_theme_action`
        #: exists.
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

        #: The §11 schema lane (`ui/xsd_controller.py`): the Schema menu, the
        #: Edit-XSD tab and the curated-schema feed. The Properties panel is
        #: not a §11 surface, so its schema feed is injected rather than grown
        #: as a `UiShell` field.
        self._xsd_ui = XsdController(
            self._shell,
            self._schema_storage_dir,
            parent=self,
            feed_properties_schema=self.properties_panel.set_schema_model,
        )

        #: The generation lane (`ui/generation_controller.py`): the Generation
        #: menu, the vendor PHP Generator run and panGen/rePHPgen. Built before
        #: the menu bar because it owns its menu outright.
        #:
        #: The FIRST lane that consumes document state, so it does so through
        #: PROVIDERS rather than a reference to whoever holds it: `project` /
        #: `project_path` read the host's current model and path at call time,
        #: and `ensure_saved` runs the project's own Save / Save As (the
        #: generator reads the `.pgtp` from disk, so every run saves first).
        #: When `PgtpDocumentController` lands in a later wave, only these four
        #: lines are repointed -- the collaborator does not change.
        self._gen_ui = GenerationController(
            self._shell,
            self._generator_config_dir,
            parent=self,
            runner=generator_runner,
            project=lambda: self._current_project,
            project_path=lambda: self._current_project_path,
            ensure_saved=self._ensure_project_saved,
            default_output_dir=self._dialog_default_dir,
        )

        #: The find / replace / bookmarks / validate lane
        #: (`ui/find_controller.py`): the per-tab find-bar and bookmark-editor
        #: routing, the Bookmarks menu (owned outright, so it builds it), the
        #: Edit-menu Find…/Replace… actions, the whole streaming Find-All run and
        #: Tier-2 validation. Built before the menu bar because
        #: `_build_menu_bar` calls `build_bookmarks_menu` and `_build_edit_menu`
        #: hands it the two actions it owns. Validation reads the open document
        #: through the same two providers `_gen_ui` uses.
        self._find_ui = FindValidateController(
            self._shell,
            parent=self,
            project=lambda: self._current_project,
            project_path=lambda: self._current_project_path,
        )

        #: The §7 Compare/Merge lane (`ui/diff_merge_controller.py`): the three
        #: comparison entry points, the comparison target they set, and Apply
        #: Changes to Target. `reload` re-opens the file Apply just wrote and
        #: points at the host's public `open_project_file` (which `main.py` also
        #: calls); when `PgtpDocumentController` lands only that line moves.
        self._diff_ui = DiffMergeController(
            self._shell,
            parent=self,
            project=lambda: self._current_project,
            # A lambda, not the bound method: resolved at CALL time so a test (or
            # a later wave) that replaces `open_project_file` on the finished
            # window is honoured.
            reload=lambda path: self.open_project_file(path),
        )

        #: The §17/FQ-003 coherence lane (`ui/coherence_controller.py`): the
        #: Database/XML Coherence view, its cached schema and the SP3
        #: create-from-table gestures. Built before the menu bar because
        #: `_build_database_menu` hands it the toggle action it owns.
        #:
        #: `find_all` is the find lane's streaming Find-All entry point (this is
        #: the one wiring line the find extraction repointed).
        #: `prompt_missing_connection` is the BUG-024 reroute shared with the
        #: DDL Explorer, which moves with that lane. The three dock/tab
        #: callables are gestures `UiShell` has no field for.
        self._db_ui = CoherenceController(
            self._shell,
            self.coherence_panel,
            parent=self,
            find_all=self._find_ui.find_all,
            prompt_missing_connection=self._prompt_missing_connection,
            show_left_dock=self._show_left_dock,
            show_audit_dock=self._show_audit_dock,
            panel_visible=self._coherence_tab_visible,
        )
        self.coherence_panel.rename_requested.connect(self._db_ui.on_rename_requested)
        self.coherence_panel.name_jump_requested.connect(self._db_ui.on_jump_requested)
        self.coherence_panel.create_requested.connect(self._db_ui.on_create_requested)

        self._build_menu_bar()

        # §21 custom-PHP editing + §22 PHP lint. Two lanes, deliberately
        # separate objects, wired to each other only HERE: the lint lane hands
        # the §21 lane a `(service, lint_on_save)` pair to pass into
        # `open_php_file_tab`, and the §21 lane announces each new tab so the
        # lint lane can connect `lint_reported` to the Audit panel. Neither
        # imports the other (see tests/ui/test_collaborator_boundaries.py).
        self._lint_ui = LintController(
            self._shell, parent=self, config_dir=self._generator_config_dir
        )
        self._php_tabs = PhpTabController(self._shell, parent=self)
        self._php_tabs.lint_settings = self._lint_ui.tab_lint_settings
        # A dropped `.pgtp` is a PROJECT open, not a text open -- it must go
        # through §18.2's New Project / Open Project / Edit Standalone chooser.
        self._php_tabs.open_pgtp = self._open_pgtp_path
        self._php_tabs.tab_opened.connect(self._lint_ui.attach_tab)
        # Previously emitted into the void: the ✕ on a PHP tab did nothing.
        self.center_stage.php_file_close_requested.connect(
            self._php_tabs.on_close_requested
        )
        # Reflect the persisted §22 toggle on the menu item built above.
        self._lint_on_save_action.setChecked(self._lint_ui.lint_on_save)
        # §21: files can be dropped onto the window (handled by dragEnterEvent /
        # dropEvent below, which delegate the classification to `_php_tabs`).
        self.setAcceptDrops(True)

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
        self._xsd_ui.ensure_bootstrap()
        self._xsd_ui.load_curated()

    def _save_active_tab(self) -> None:
        """Ctrl+S / File ▸ Save routes to the active center-stage tab."""
        stage = self.center_stage
        if stage.currentIndex() == stage.xsd_tab_index:
            self._xsd_ui.save()
            return
        panel = stage.active_ddl_object_panel()
        if panel is not None:
            self._save_ddl_object_editor(panel)
            return
        if stage.active_php_file_tab() is not None:
            # §21: without this branch Ctrl+S on a focused PHP tab saved the
            # PROJECT -- the tab's own event filter only claims the key while
            # the caret is inside its editor, and File ▸ Save never was.
            self._php_tabs.save_active_tab()
            return
        self._save_project()

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

    # -- §21 drag-and-drop ---------------------------------------------------
    # `QMainWindow` gestures, so they stay on the host; every decision about
    # WHAT a dropped path means belongs to `_php_tabs` (a `.pgtp` routes back
    # to `_open_pgtp_path`, a binary or a folder is refused out loud).

    def dragEnterEvent(self, event):
        """Accept a drag carrying at least one existing file (§21).

        Deliberately a cheap existence test: this fires while the mouse is
        still moving, so the text/UTF-8 classification waits for the drop,
        where a refusal can be explained instead of silently showing a no-drop
        cursor."""
        paths = self._php_tabs.dropped_paths(event.mimeData())
        if self._php_tabs.can_accept_drop(paths):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        """Open every dropped file (§21), routing each by kind."""
        paths = self._php_tabs.dropped_paths(event.mimeData())
        if not self._php_tabs.can_accept_drop(paths):
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        self._php_tabs.handle_dropped_paths(paths)

    def closeEvent(self, event):
        # Edit XSD tab (spec §11): unsaved XSD edits get their own
        # save/discard/cancel prompt, distinct from the project's (File >
        # Close handles that one) since the XSD tab has no Close command.
        # The §11 lane answers its own half; False = abort the close.
        if not self._xsd_ui.confirm_close_for_exit():
            event.ignore()
            return
        # Persist window geometry/dock state on close (Sub-project D). No modal
        # prompt here -- File > Close handles the unsaved-changes prompt.
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())
        self._settings.sync()
        # §23: end an MCP session with the window that opted into it. The thread
        # is a daemon so it would not hold the process open, but a client
        # deserves a clean EOF rather than a half-dead peer.
        if self._mcp_session is not None and self._mcp_action is not None:
            self._mcp_action.setChecked(False)
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

    # Three dock/tab gestures `UiShell` has no field for, injected into
    # `CoherenceController` instead: the docks themselves are host furniture,
    # and exactly one lane needs each of these.

    def _show_left_dock(self) -> None:
        """Un-hide the left dock. Revealing a left-dock TAB is not enough if a
        prior action hid the dock that carries it."""
        self.tree_dock.setVisible(True)

    def _show_audit_dock(self) -> None:
        """Un-hide the bottom Audit dock, so results just listed are visible."""
        self.audit_dock.setVisible(True)

    def _coherence_tab_visible(self) -> bool:
        """Whether the Database/XML Coherence tab is currently visible -- what
        gates the reparse-driven refresh of an already-open view."""
        return self.left_tabs.isTabVisible(self.coherence_tab_index)

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
        self._open_pgtp_path(path)

    def _open_pgtp_path(self, path) -> None:
        """Open a `.pgtp` the way File ▸ Open… does, given a path that came
        from somewhere other than that dialog (§21's drag-and-drop drops one
        here). Split out so the drop path cannot fork the §18.2 decision."""
        if self._ddl_project_folder is None:
            self._prompt_pgtp_open_mode(str(path))
        else:
            # A project is already active -- the user already committed to
            # project mode; just open (existing linking logic applies
            # silently, exactly as it does for any subsequent open).
            self.open_project_file(str(path))

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
                self._xsd_ui.enrich_from_file(path)

        # Cursor restored here (busy_status __exit__), BEFORE any dialog.
        if parse_error is not None:
            self._handle_parse_failure(path, parse_error)
            return
        # §26 Open Recent + §7 Revert gating: both keyed off the file that just
        # became the open project. Only on the SUCCESS path -- a file that would
        # not parse is not something to offer re-opening from a menu.
        self._remember_recent_file(path)
        self._refresh_revert_action()
        self.statusBar().showMessage(f"Opened: {path}", 5000)

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
            self._xsd_ui.reveal_line(line, item.data(Qt.ItemDataRole.UserRole + 2))
            return
        if target == LINT_AUDIT_TARGET:
            # §22: a `[Lint]` finding carries the PHP tab's CenterStage key on
            # UserRole+2 (the slot Verify XSD uses for its mode, read only on
            # the "xsd" branch above, so the two never collide). Same "does
            # nothing if that tab is gone" rule as `[Check]` below.
            self._php_tabs.navigate_to(item.data(Qt.ItemDataRole.UserRole + 2), line)
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

    # -- §9 auto-parse -------------------------------------------------------

    def _auto_parse_enabled(self) -> bool:
        """Whether Edit ▸ Auto Parse XML is currently checked. The action is the
        single source of truth (None before the Edit menu is built)."""
        return (
            self._auto_parse_action is not None
            and self._auto_parse_action.isChecked()
        )

    def _on_auto_parse_toggled(self, checked: bool) -> None:
        """Turning the toggle off must also cancel a reparse already in flight,
        otherwise one more parse lands after the user opted out."""
        if not checked:
            self._auto_parse_timer.stop()

    def _on_editor_block_count_changed(self, _new_count=0) -> None:
        """Raw XML line count changed: (re)start the auto-parse debounce.

        No-ops when the toggle is off or while `_loading`/`_restoring` -- the
        same two guard flags that gate snapshot-history capture -- so a
        programmatic `setPlainText` (file open, revert, undo/redo restore) never
        triggers a reparse of text the user did not type. No Caption Mode gating
        is needed: the Raw XML editor is read-only in that mode, so the signal
        cannot come from typing there.
        """
        if self._loading or self._restoring or not self._auto_parse_enabled():
            return
        self._auto_parse_timer.start()

    def _auto_parse_now(self) -> None:
        """Fire-time handler for the debounce timer (called directly in tests).
        Re-checks the same guards, since the toggle can flip or a load can start
        during the 400 ms window."""
        if self._loading or self._restoring or not self._auto_parse_enabled():
            return
        self._reparse_raw_xml(silent=True)

    def _reparse_raw_xml(self, *, silent: bool = False):
        """Reparse the Raw XML buffer into the tree/model.

        `silent` is KEYWORD-ONLY and defaults to False, so every pre-existing
        caller -- Tools ▸ "Reparse Raw XML into Tree" (whose `triggered` signal
        passes no positional argument to a callable with no positional
        parameters), the coherence rename path and the tests -- keeps exactly
        today's behavior, modal failure dialog included. Only §9's auto-parse
        passes `silent=True`, which downgrades a `PgtpParseError` to a transient
        status-bar line: it fires while the user is mid-edit, where a modal (or a
        cursor jump) would be an interruption, and half-typed XML is expected to
        be malformed. Either way the last-good model and tree survive.
        """
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
            if silent:
                # §9: NO modal and NO cursor jump while auto-parsing -- the user
                # is typing. A transient status-bar line only; the tree keeps its
                # last-good state (nothing above touched it on this path).
                self.statusBar().showMessage(
                    "Auto-parse: XML not well-formed yet — tree not updated", 5000
                )
                return
            self._handle_reparse_failure(parse_error)
            return
        if silent:
            self.statusBar().showMessage("Auto-parsed raw XML into tree", 3000)
        else:
            self.statusBar().showMessage("Reparsed raw XML into tree", 5000)
        self._db_ui.refresh_if_open(project)

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
        # The save just wrote `<path>.bak` (unless this is a §18.2 working
        # copy), so Revert's availability may have flipped.
        self._refresh_revert_action()
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
        self._remember_recent_file(path)
        self._refresh_revert_action()
        self.statusBar().showMessage(f"Saved as {Path(path).name}", 5000)

    def _ensure_project_saved(self, save_as: bool = False) -> bool:
        """`GenerationController`'s save seam: run the project's own Save (or
        Save As) and answer whether the project now exists on disk.

        The generation lane must not know *how* a project is saved -- it only
        needs "is the editor's content on disk now?", because the generator
        reads the `.pgtp` from there. False means there is nothing to generate
        from (Save As was cancelled). This is the single line a later wave
        repoints at `PgtpDocumentController`.
        """
        if save_as:
            self._save_project_as()
        else:
            self._save_project()
        return bool(self._current_project_path)

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
        # No project, no `.bak` to revert to (§7).
        self._refresh_revert_action()
        # Coherence results are project-tied (BUG-011, §17). Only here on the
        # committed-close path -- a cancelled close (returns above) must leave
        # the still-open project's tab alone, and _revert_project keeps the
        # project loaded so it doesn't tear down.
        self._db_ui.teardown_for_project_close()
        _log.info("file: close outcome=%s", outcome)

    def _backup_path(self) -> "str | None":
        """The `<current>.bak` path Revert would read, or None when no project
        is open. ONE definition, shared by `_revert_project` and the enable
        gate below so the menu item can never disagree with what Revert does."""
        if not self._current_project_path:
            return None
        return str(self._current_project_path) + ".bak"

    def _refresh_revert_action(self) -> None:
        """Gate File ▸ Revert on the `.bak` actually existing (§7).

        Called from every point that can change the answer -- open, save, save
        as, revert, close -- rather than from `_set_dirty`, which fires on every
        keystroke and would turn this `exists()` into a per-keystroke `stat`
        (the `.pgtp` may live on an sshfs mount, §18.2). Guarded on the action
        existing because the refresh runs during `_build_file_menu` itself.
        """
        action = getattr(self, "_revert_action", None)
        if action is None:
            return
        bak_path = self._backup_path()
        action.setEnabled(bak_path is not None and Path(bak_path).exists())

    # -- Open Recent (§26) ---------------------------------------------------

    #: QSettings key holding the recent-projects list, and its cap. Persisted
    #: through the SAME injectable `self._settings` store the window already
    #: uses for geometry/theme, so a test pointed at a temp ini gets a private
    #: MRU list for free.
    _RECENT_FILES_KEY = "recentFiles"
    _RECENT_FILES_MAX = 10

    def _recent_files(self) -> list:
        """The persisted MRU list, most-recent first, pruned of entries whose
        file no longer exists and capped. Reading prunes but does not write --
        `_remember_recent_file` is the only writer."""
        stored = self._settings.value(self._RECENT_FILES_KEY, [])
        if isinstance(stored, str):
            # A single-element QStringList round-trips through the ini format
            # as a bare string.
            stored = [stored]
        elif stored is None:
            stored = []
        paths = []
        for entry in stored:
            path = str(entry)
            if path in paths or not Path(path).is_file():
                continue
            paths.append(path)
        return paths[: self._RECENT_FILES_MAX]

    def _remember_recent_file(self, path) -> None:
        """Push `path` to the head of the MRU list and persist it."""
        path = str(path)
        paths = [p for p in self._recent_files() if p != path]
        paths.insert(0, path)
        self._settings.setValue(
            self._RECENT_FILES_KEY, paths[: self._RECENT_FILES_MAX]
        )

    def _rebuild_recent_menu(self) -> None:
        """Repopulate the Open Recent submenu from the pruned MRU list.

        Every entry goes through the ONE project-open path (`open_project_file`
        via `_open_pgtp_path`, so §18.2's New/Open/Edit-Standalone chooser still
        applies) -- never a second loader. An empty list shows a single disabled
        placeholder rather than an empty menu that looks broken.
        """
        menu = getattr(self, "_recent_menu", None)
        if menu is None:
            return
        menu.clear()
        paths = self._recent_files()
        if not paths:
            placeholder = menu.addAction("(no recent files)")
            placeholder.setEnabled(False)
            return
        for path in paths:
            action = menu.addAction(Path(path).name)
            action.setToolTip(path)
            # Default-argument binding, not a closure over the loop variable.
            action.triggered.connect(
                lambda _checked=False, target=path: self._open_pgtp_path(target)
            )

    def _revert_project(self) -> None:
        """Reload the project from its `<path>.bak` backup, if one exists.

        Restores the .bak content into the editor and rebuilds the tree from
        it while keeping `_current_project_path` pointing at the real file.
        The buffer then differs from the on-disk file, so the document is
        marked dirty.
        """
        bak_path = self._backup_path()
        if bak_path is None or not Path(bak_path).exists():
            # Still defended at runtime even though the menu item is now gated
            # on the same condition: the toolbar mirrors the action, and the
            # `.bak` can vanish between the last refresh and the click.
            self.statusBar().showMessage("Nothing to revert to.", 5000)
            self._refresh_revert_action()
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
        self._refresh_revert_action()
        self.statusBar().showMessage(
            f"Reverted to {Path(bak_path).name}", 5000
        )

    def _build_menu_bar(self):
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        # The Schema menu is owned outright by the §11 lane, so it builds it
        # (and registers its own window-level Ctrl+L action through the host's
        # `addAction`) -- called from here so the menu keeps its position in
        # the bar.
        self._xsd_ui.build_menu(self.menuBar(), self.addAction)
        self._build_database_menu()
        self._build_tools_menu()
        # The Bookmarks menu is owned outright by the find/validate lane, so it
        # builds it -- called from here so the menu keeps its position in the bar.
        self._find_ui.build_bookmarks_menu(self.menuBar())
        # The Generation menu is owned outright by the generation lane, so it
        # builds it -- called from here so the menu keeps its position in the bar.
        self._gen_ui.build_menu(self.menuBar())
        self._build_help_menu()

    def _build_file_menu(self):
        menu = self.menuBar().addMenu("File")
        open_action = menu.addAction("Open...")
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_project)
        # §26 File ▸ Open Recent. The submenu itself is built once and kept
        # (`QMenu.addMenu` returns a wrapper Python then owns -- see
        # `toolbar_controller.py`'s keepalive note), and its CHILDREN are rebuilt
        # from the persisted MRU list every time it is about to be shown, so an
        # entry whose file was deleted meanwhile disappears instead of
        # misfiring. It is skipped wholesale by the toolbar's menu walk (§7).
        self._recent_menu = menu.addMenu("Open Recent")
        self._recent_menu.aboutToShow.connect(self._rebuild_recent_menu)
        self._rebuild_recent_menu()
        # §21: the standalone custom-PHP editor's entry point. Sits beside
        # "Open..." because it IS an open gesture, and deliberately ABOVE the
        # project separator: a `.php` file has no structural tie to a `.pgtp`
        # and opens whether or not a project is loaded. Connected through a
        # lambda because the collaborator is constructed after the menu bar.
        open_php_action = menu.addAction("Open PHP File…")
        open_php_action.triggered.connect(lambda: self._php_tabs.open_php_file_dialog())
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
        # §7: "enabled only when `<current>.bak` exists". Starts disabled (no
        # project is open yet) and is refreshed by `_refresh_revert_action` at
        # every point the answer can change: open, save, save-as, revert, close.
        self._refresh_revert_action()
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

        # The five find/replace entries belong to the find/validate lane; the
        # Find… / Replace… pair is handed over to it below because Caption Mode
        # gates their enabled state.
        find_action = menu.addAction("Find...")
        find_action.setShortcut("Ctrl+F")
        find_action.triggered.connect(self._find_ui.show_find)

        find_next_action = menu.addAction("Find Next")
        find_next_action.setShortcut("F3")
        find_next_action.triggered.connect(self._find_ui.find_next)

        find_all_action = menu.addAction("Find All")
        find_all_action.setShortcut("Ctrl+Shift+F")
        find_all_action.triggered.connect(self._find_ui.find_all_in_active_bar)

        replace_action = menu.addAction("Replace...")
        replace_action.setShortcut("Ctrl+R")
        replace_action.triggered.connect(self._find_ui.show_replace)

        replace_all_action = menu.addAction("Replace All")
        replace_all_action.setShortcut("Ctrl+Alt+Return")
        replace_all_action.triggered.connect(self._find_ui.replace_all)

        self._find_ui.set_find_actions(find_action, replace_action)

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
        # §9 Edit ▸ Auto Parse XML: checkable, unchecked at every launch (the
        # state is in-memory only -- see the timer setup in __init__). The
        # action IS the toggle's storage; nothing else records it.
        auto_parse_action = menu.addAction("Auto Parse XML")
        auto_parse_action.setCheckable(True)
        auto_parse_action.setChecked(False)
        auto_parse_action.toggled.connect(self._on_auto_parse_toggled)
        self._auto_parse_action = auto_parse_action

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
        self._find_ui.set_find_actions_enabled(False)
        # §8/§13: the Raw XML editor is read-only in Caption Mode, so the
        # Bookmarks menu and its four shortcuts go with it. The lane that owns
        # the menu disables the menu AND every child action (a disabled QMenu
        # alone would leave Ctrl+F2 / F2 / Shift+F2 live). Gutter bookmark
        # toggling stays usable, deliberately.
        self._find_ui.set_bookmarks_enabled(False)
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
        self._find_ui.set_find_actions_enabled(True)
        self._find_ui.set_bookmarks_enabled(True)

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
        # Created here (this is the Database menu) but OWNED by
        # `CoherenceController`, which connects it and un-checks it on a failed
        # or refused run.
        coherence_action = menu.addAction("Database/XML Coherence")
        coherence_action.setCheckable(True)
        coherence_action.setChecked(False)
        self._db_ui.set_toggle_action(coherence_action)
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
        # §18.5 D3's *"Check without applying"* -- the rolled-back probe
        # (`db/ddl_check.py::probe_check`, `commit=False`), which is the ONE
        # narrow place rollback survives. It sits directly next to Check because
        # the two answer neighbouring questions ("what does the sandbox say about
        # what is in it?" vs. "what would this buffer do if I applied it?"), and
        # it shares Check's visibility gate for the same carve-out-2 reason.
        self._sandbox_probe_check_action = menu.addAction(
            "Check Object Without Applying"
        )
        self._sandbox_probe_check_action.setVisible(False)
        self._sandbox_probe_check_action.triggered.connect(
            lambda: self._probe_check_active_ddl_object()
        )
        menu.addSeparator()
        # §18.5 D2/D2a's provisioning surface. Deliberately NOT gated on a
        # session or even on an open project: this is the ONE entry point that
        # can CREATE a sandbox, so hiding it whenever there is no sandbox would
        # make it unreachable exactly when it is needed. The dialog itself
        # applies carve-out 2 internally -- every control whose operation cannot
        # run is absent, with the reason stated in its place.
        self._sandbox_setup_action = menu.addAction("Sandbox Setup…")
        self._sandbox_setup_action.triggered.connect(
            lambda: self._open_sandbox_setup()
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
        `CoherenceController.run_check` and _open_ddl_explorer, the two internal
        callers that
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
        # callers (`CoherenceController.run_check`, _open_ddl_explorer) also
        # invoke this method
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
        # FQ-007: the sandbox step CREATES and provisions the sandbox database
        # now, rather than recording a name the user typed. Last, so a failed
        # sandbox never costs the user the project (§18's tier-2 degrade).
        self._provision_new_project_sandbox(dialog)

    def _provision_new_project_sandbox(self, dialog: NewProjectDialog) -> None:
        """Create + provision + `plpgsql_check`-install this project's sandbox
        database, off the GUI thread, through the one `SandboxController`
        (FQ-007, §18.2/§18.5 D2).

        The user supplies only the **server** connection and the with-data /
        without-data choice; the database itself is created here with an
        auto-generated `pgtp_sandbox_*` name (`dialog.sandbox_database_names()`),
        against the maintenance database (`dialog.sandbox_admin_params()`) since
        `CREATE DATABASE` cannot run inside the database being created.

        No-op when the sandbox group was left blank -- a project with no sandbox
        is a perfectly good tier-2 "quality project", not an error, and nothing
        may connect anywhere as a side effect of creating one.
        """
        settings = self._ddl_project_settings
        if settings is None or not settings.sandbox.host:
            return
        candidates = dialog.sandbox_database_names()
        self.sandbox_controller.provision_new_database(
            self._on_new_project_sandbox_provisioned,
            admin_params=dialog.sandbox_admin_params(),
            name_candidates=candidates,
        )

    def _on_new_project_sandbox_provisioned(self, result) -> None:
        """Record what the sandbox provisioning ACTUALLY did (FQ-007).

        On success the created database name is written into
        `ProjectSettings.sandbox` so a later Sandbox Setup…/`reset()` re-opens the
        same database. The recorded `sandbox_mode` is **not** rewritten -- D2a's
        mode is the user's one-time choice; when a run could not honor it (a
        "with data" sandbox with no target to clone from) the result's reason says
        so rather than the project quietly becoming a different kind of sandbox.

        On failure **nothing is recorded**: the project keeps its sandbox
        *server* details (so the user can retry) but claims no sandbox database,
        which is what makes the reported capability tier honest rather than
        derived from what was asked for. Either way the reason string rides the
        ordinary `operation_finished` path into the Audit panel, never swallowed.
        """
        settings = self._ddl_project_settings
        folder = self._ddl_project_folder
        if settings is None or folder is None:
            return
        database = (getattr(result, "database_name", "") or "").strip()
        if getattr(result, "ok", False) and database:
            updated = replace(
                settings, sandbox=replace(settings.sandbox, database=database)
            )
            save_settings(folder, updated)
            self._ddl_project_settings = updated
            self.statusBar().showMessage(
                f"Created and provisioned sandbox database: {database}", 5000
            )
        # Re-probe either way: the stored tier/capability status must describe the
        # sandbox that now exists (or the one that does not), never the intent.
        self.refresh_project_capability_status()

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

    # -- DDL Explorer (spec §18.1) --------------------------------------------

    def _fetch_ddl_schema(self, params):
        """Introspect routines & triggers. Injectable seam — tests patch this
        to return a canned `DatabaseSchema` (mirrors
        `CoherenceController.fetch_schema`)."""
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
    #: BUG-035: the last sandbox *contents* inspection, as
    #: `(sandbox ConnectionParams, schema fact, data fact)`, or None when the
    #: sandbox has never been inspected. The params are stored alongside the
    #: facts on purpose: a result is only used for the very connection it was
    #: measured against, so switching or closing a project cannot leave a
    #: previous sandbox's facts describing the current one. Class-level default
    #: so no instance ever reads it before the first inspection.
    _ddl_sandbox_content_facts = None

    def _project_status_target(self):
        """The target `ConnectionParams` the Quality node speaks for, or None.

        One place for BUG-024's selection -- with a project open its own
        target profile is authoritative; projectless, the app-level saved
        connection is -- so the diagram, the summary line and the
        reachability probe can never drift onto different connections.
        """
        settings = self._ddl_project_settings
        return settings.target if settings is not None else load_connection(self._settings)

    @staticmethod
    def _target_is_configured(target) -> bool:
        """Whether `target` is a real, usable target profile (BUG-030 facet a).

        `ProjectSettings.target` is `field(default_factory=ConnectionParams)`,
        so with a project open it is **never None** -- an `is not None` test
        answers "does the dataclass exist", which is always yes, and made
        `QualityState.NOT_SET_UP` unreachable while a brand-new project's
        blank target rendered green "Connected". Configured therefore means
        "has a host", the same convention the sandbox side already uses
        (`sandbox_configured = bool(sandbox_params.host)`). One place, because
        the diagram's state and the click-through's details must agree about
        it.
        """
        return target is not None and bool(target.host)

    def _project_status_sandbox_facts(self):
        """The verified `(schema, data)` facts for the CURRENT sandbox.

        `(UNKNOWN, UNKNOWN)` whenever no project is open, no sandbox is
        configured, or the stored inspection belongs to a different sandbox
        connection -- never a definite answer inherited from elsewhere.
        """
        settings = self._ddl_project_settings
        facts = self._ddl_sandbox_content_facts
        if settings is None or not settings.sandbox.host or facts is None:
            return SandboxFact.UNKNOWN, SandboxFact.UNKNOWN
        params, schema_fact, data_fact = facts
        if params != settings.sandbox:
            return SandboxFact.UNKNOWN, SandboxFact.UNKNOWN
        return schema_fact, data_fact

    def _build_project_status_diagram(self):
        """Current `ProjectStatusDiagram`, or None when nothing to show.

        Quality has no backing field on `ProjectCapabilityStatus` (which
        models the sandbox side only), so it is assembled here from whether a
        target connection is really configured (`_target_is_configured`, not
        "the dataclass exists" -- BUG-030 facet a) plus the last reachability
        probe's result (BUG-030: green must mean "reachable", not merely
        "a profile exists") -- §18.8's not_set_up / error / connection_ok
        trio, mirroring the Sandbox node's own pattern.

        Sandbox1 is fed the two VERIFIED facts from
        `_refresh_sandbox_provisioning_status`, never the recorded
        `sandbox_mode` (BUG-035): the mode is a radio button, and reading it
        back as "the schema is provisioned" is what made an empty sandbox
        report "Schema only". Un-inspected stays `UNKNOWN`.
        """
        target = self._project_status_target()
        quality = quality_state(
            configured=self._target_is_configured(target),
            probe_error=self._ddl_target_probe_error,
        )
        schema_fact, data_fact = self._project_status_sandbox_facts()
        return build_diagram(
            status=self._ddl_project_capability_status,
            quality=quality,
            sandbox_schema_present=schema_fact,
            sandbox_data_present=data_fact,
            dark=not self._light_theme_action.isChecked(),
        )

    def _inspect_sandbox_provisioning(self, params):
        """Ask the sandbox database what it actually contains (BUG-035).

        Returns `(schema fact, data fact)`. **Never raises** -- every failure
        becomes `SandboxFact.UNKNOWN`, mirroring `db/sandbox.py::probe`'s
        never-raises contract, because "could not check" must never be
        reported as "genuinely not there".

        Two facts, one connection:

        1. *Schema presence* counts relations + routines living outside the
           system schemas and outside the reserved bookkeeping schema (which a
           bare-but-owned sandbox always has, so counting it would make every
           unprovisioned sandbox look provisioned). Extension-owned objects are
           excluded via `pg_depend`, so installing `plpgsql_check` cannot pass
           for provisioning.
        2. *Data presence* asks each of those base tables for one row via
           `query_to_xml` -- `LIMIT 1`, so it is an existence test rather than
           a full count, and exact rather than a guess off `reltuples` (which
           `pg_restore` leaves at -1 and which would therefore read a freshly
           cloned database as empty).

        The data query needs XML support in the server build; if it fails, the
        schema question is re-asked on its own so a missing `query_to_xml`
        costs only the data fact, never the schema fact this bug was about.

        This is the injectable seam for tests: replace it on the instance
        (`window._inspect_sandbox_provisioning = fake`) exactly like
        `_probe_sandbox_capabilities`.
        """
        from pgtp_editor.db.introspect import run_queries  # noqa: PLC0415 -- lazy driver
        from pgtp_editor.db.sandbox import BOOKKEEPING_SCHEMA  # noqa: PLC0415

        # A fixed, validated identifier constant -- not user input; quoted as a
        # SQL string literal because it is compared as a NAME, not spelled as one.
        reserved = "'" + BOOKKEEPING_SCHEMA.replace("'", "''") + "'"
        app_schema = f"n.nspname <> {reserved} AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'"
        schema_sql = f"""
            SELECT count(*) FROM (
                SELECT c.oid FROM pg_class c
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f') AND {app_schema}
                   AND NOT EXISTS (
                       SELECT 1 FROM pg_depend d
                        WHERE d.objid = c.oid AND d.classid = 'pg_class'::regclass
                          AND d.deptype = 'e')
                UNION ALL
                SELECT p.oid FROM pg_proc p
                  JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE {app_schema}
                   AND NOT EXISTS (
                       SELECT 1 FROM pg_depend d
                        WHERE d.objid = p.oid AND d.classid = 'pg_proc'::regclass
                          AND d.deptype = 'e')
            ) app_objects
        """
        data_sql = f"""
            SELECT count(*) FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind IN ('r', 'p') AND {app_schema}
               AND NOT EXISTS (
                   SELECT 1 FROM pg_depend d
                    WHERE d.objid = c.oid AND d.classid = 'pg_class'::regclass
                      AND d.deptype = 'e')
               AND (xpath('/row/present/text()', query_to_xml(
                       format('SELECT count(*) AS present FROM '
                              '(SELECT 1 FROM %I.%I LIMIT 1) probe',
                              n.nspname, c.relname),
                       false, true, '')))[1]::text::bigint > 0
        """

        def fact(rows) -> SandboxFact:
            return SandboxFact.PRESENT if int(rows[0][0]) > 0 else SandboxFact.ABSENT

        try:
            schema_rows, data_rows = run_queries(params, [schema_sql, data_sql])
        except Exception:  # noqa: BLE001 -- unknown, never a definite absence
            try:
                (schema_rows,) = run_queries(params, [schema_sql])
            except Exception:  # noqa: BLE001
                return SandboxFact.UNKNOWN, SandboxFact.UNKNOWN
            return fact(schema_rows), SandboxFact.UNKNOWN
        return fact(schema_rows), fact(data_rows)

    def _refresh_sandbox_provisioning_status(self) -> None:
        """Re-inspect what the sandbox database actually holds (BUG-035).

        The Sandbox1 node's own probe, deliberately separate from the sandbox
        *capability* probe: that one answers "can we reach it and what can it
        do", this one answers "what is in it". Runs off the GUI thread for the
        same reason, and clears the stored facts to nothing (rather than to a
        default) whenever there is no sandbox to ask.
        """
        settings = self._ddl_project_settings
        if settings is None or not settings.sandbox.host:
            self._ddl_sandbox_content_facts = None
            return
        sandbox_params = settings.sandbox

        def do_inspect():
            return self._inspect_sandbox_provisioning(sandbox_params)

        def on_result(facts) -> None:
            schema_fact, data_fact = facts
            self._ddl_sandbox_content_facts = (sandbox_params, schema_fact, data_fact)
            window = self._project_status_window
            if window is not None:
                window.set_diagram(self._build_project_status_diagram())

        def on_error(exc: BaseException) -> None:
            # `_inspect_sandbox_provisioning` never raises, so this only guards
            # a broken injected seam -- surfaced, never silently swallowed, and
            # the facts stay UNKNOWN rather than degrading to "absent".
            self._ddl_sandbox_content_facts = None
            self.audit_panel.addItem(
                QListWidgetItem(f"[Project] Sandbox content inspection failed: {exc}")
            )

        self._run_async(do_inspect, on_result=on_result, on_error=on_error)

    def _connection_summary_for(self, params) -> str:
        """`user@host:port/db` for a status window, or a plain "not
        configured" line. Routed through `connection_summary` so no password
        can reach the window text.

        BUG-030 facet a: a host-less `ConnectionParams` is *not* a connection,
        so it gets the "Not configured." line too. Without this the Quality
        click-through printed a degenerate `@:/`-shaped summary -- phantom
        details for a connection that does not exist -- next to a status line
        that (also wrongly) said "Connected".
        """
        if not self._target_is_configured(params):
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
            self._refresh_sandbox_provisioning_status()
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
            # BUG-035: Sandbox1's facts are re-inspected on the same trigger as
            # everything else the window shows, so "opening the window is a
            # fresh probe" (§18.8) holds for the node's contents too.
            self._refresh_sandbox_provisioning_status()
            return self._build_project_status_diagram()

        # Sandbox1's "run data clone" and Sandbox2's "install plpgsql_check" go
        # to the controller's zero-argument §18.8 adapters -- but only while a
        # live `SandboxSession` exists, because that is what both operations run
        # through. `_refresh_project_status_sandbox_actions` keeps this answer
        # current for the rest of the window's life (it is cached and re-shown,
        # not rebuilt), and the destructive one keeps the controller's own
        # `confirm_destructive` prompt: no second dialog is opened here.
        settings = self._ddl_project_settings
        alive = self.sandbox_controller.has_session
        panel = ProjectStatusPanel(
            diagram=self._build_project_status_diagram(),
            on_refresh=on_refresh,
            on_reconnect_quality=on_refresh,
            on_run_data_clone=(
                self.sandbox_controller.on_run_data_clone if alive else None
            ),
            on_install_plpgsql_check=(
                self.sandbox_controller.on_install_plpgsql_check if alive else None
            ),
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
        `_confirm_close` and `XsdController.confirm_close`, so tests can
        monkeypatch this instead of ever driving a real modal)."""
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
                # Points at the two gestures that can actually produce a session
                # (Project Status… only ever reported on one). Both really exist
                # in the Database menu.
                "No sandbox session — open one with Database ▸ Open Sandbox "
                "Session, or provision the sandbox from Database ▸ Sandbox "
                "Setup… first.",
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
        if self._sandbox_probe_check_action is not None:
            # The probe is the same ladder against the same session, so it earns
            # exactly the same gate -- one predicate, never a second reading of
            # "is there a session?".
            self._sandbox_probe_check_action.setVisible(controller.can_check)
        if self._open_sandbox_session_action is not None:
            self._open_sandbox_session_action.setVisible(
                not has_session and bool(self._configured_sandbox_params())
            )
        if self._close_sandbox_session_action is not None:
            self._close_sandbox_session_action.setVisible(has_session)
        for panel in self.center_stage.ddl_object_panels():
            self._wire_ddl_object_apply_seams(panel)
        self._refresh_sandbox_console_affordances()
        self._refresh_project_status_sandbox_actions()

    def _refresh_project_status_sandbox_actions(self) -> None:
        """Keep §18.8's two session-dependent node actions (Sandbox1's "run data
        clone", Sandbox2's "install plpgsql_check") wired to the controller's
        zero-argument adapters exactly while a session exists.

        Both operations go through the live `SandboxSession`, so without one they
        are ABSENT rather than refusing (carve-out 2) -- and the panel already
        renders a `None` callback as no button at all, which is why this hands it
        `None` instead of a wrapper that would state a refusal after the click.
        The destructive one keeps the controller's own `confirm_destructive`
        gate: `on_run_data_clone` -> `run_data_clone` -> `_confirmed(CLONE_DATA)`
        -> `_confirm_destructive_sandbox_operation`, so the warning text is the
        controller's and no second dialog is opened here.
        """
        window = self._project_status_window
        if window is None:
            return
        controller = self.sandbox_controller
        alive = controller.has_session
        window.set_sandbox_actions(
            on_run_data_clone=controller.on_run_data_clone if alive else None,
            on_install_plpgsql_check=(
                controller.on_install_plpgsql_check if alive else None
            ),
        )

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

    def _open_sandbox_setup(self):
        """Database ▸ Sandbox Setup… -- §18.5 D2/D2a's provisioning surface, and
        the ONE re-provisioning entry point in the app (§18.2's New Project step
        provisions once, at creation time, and has no way back).

        Non-modal (`show()`, never `exec()`), like every other dialog here, so
        the long-running provisioning it kicks off does not block the window.

        **`confirm=None` on purpose: the CONTROLLER owns the single destructive
        prompt.** The dialog's two-mode contract means passing `confirm=` here as
        well would ask the user twice for one Provision/Re-clone/Reset, and the
        controller's gate is the one that must exist anyway -- a controller built
        without `confirm_destructive` refuses every destructive operation, and
        this window has always supplied `_confirm_destructive_sandbox_operation`
        for exactly that. A decline still surfaces in the dialog, as the
        controller's own stated "cancelled -- this operation was not confirmed."
        result.
        """
        dialog = SandboxSetupDialog(
            self.sandbox_controller,
            self,
            settings=self._ddl_project_settings,
            project_dir=self._ddl_project_folder,
            confirm=None,
        )
        # A provisioning gesture may record a new `sandbox_mode` or a
        # newly created sandbox database name; adopt the dialog's OWN
        # `ProjectSettings` rather than re-reading the file it just wrote.
        dialog.finished.connect(
            lambda _result, dlg=dialog: self._adopt_sandbox_setup_settings(dlg)
        )
        self._sandbox_setup_dialog = dialog
        dialog.show()
        return dialog

    def _adopt_sandbox_setup_settings(self, dialog=None) -> None:
        """Take over whatever the Sandbox Setup dialog recorded in the project's
        `ProjectSettings` (D2a's `sandbox_mode`, and the database name a
        "create one for me" gesture chose).

        Adoption is deliberately NOT `_bind_sandbox_controller_to_project()`:
        that calls `set_project`, which drops the live session -- and the session
        this would drop is the one the dialog just provisioned. The dialog has
        already pointed the controller at the right sandbox (`set_project` before
        provisioning) and already persisted the settings through its
        `settings_saver`, so the host's remaining job is only to stop describing
        the previous sandbox.
        """
        dialog = self._sandbox_setup_dialog if dialog is None else dialog
        if dialog is None or self._ddl_project_settings is None:
            return
        settings = dialog.settings()
        if settings is None or settings == self._ddl_project_settings:
            return
        self._ddl_project_settings = settings
        self._refresh_project_status_window()

    def _refresh_project_status_window(self) -> None:
        """Re-render the §18.8 status window, if one is open, from the settings
        as they now stand. No probe of its own -- the callers that change what a
        node reports trigger their own."""
        window = self._project_status_window
        if window is not None:
            window.set_diagram(self._build_project_status_diagram())

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

        `CHECK` and `APPLY` are the two operations whose outcome is reported
        elsewhere (the invoking panel renders `result.report` over both Audit
        channels), so only a run that produced NO report is reported here -- a
        refused or crashed ladder must never read as a clean one, and must not
        be double-reported either."""
        operation = getattr(result, "operation", None)
        reason = (getattr(result, "reason", "") or "").strip()
        if operation in (SandboxOperation.CHECK, SandboxOperation.APPLY):
            if getattr(result, "report", None) is None:
                label = "check" if operation is SandboxOperation.CHECK else "apply"
                self.audit_panel.addItem(
                    QListWidgetItem(
                        f"{CHECK_PREFIX}{label} did not run"
                        + (f": {reason}" if reason else ".")
                    )
                )
            return
        if operation is SandboxOperation.PROVISION:
            # A provisioning run may have recorded a new mode or a newly created
            # database name in the Sandbox Setup dialog's settings; adopt them
            # now rather than only when the (non-modal, possibly long-lived)
            # dialog is closed.
            self._adopt_sandbox_setup_settings()
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

        Goes through `SandboxController.run_apply`, i.e.
        `db/ddl_check.py::apply_and_check`: the DDL, the `applied` working-set
        bookkeeping row and the whole validation ladder in **one transaction**,
        committing. That is the difference from the bare `SandboxSession.apply`
        this used to call: an apply now COMPILE-CHECKS the object (tier 2), lints
        it (tier 1) and runs `plpgsql_check` over it (tier 3), and a rejected
        statement rolls the whole thing back with the tier that produced it
        named. A bare `apply` reported nothing but "no exception", which is how
        tiers 0-2 came to have never run on a user gesture.

        **Returns None -- asynchronously by design.** `run_apply` marshals the
        work off the GUI thread through the controller's `_run_async` seam, so
        there is no report to hand back at return time. `apply_to_sandbox()`'s
        seam contract was widened for exactly this (see its docstring): `None`
        means *"the result will arrive later"*, and it arrives through
        `DdlObjectEditorPanel.record_apply_result`, the panel method that owns
        both halves (recording the report for precondition 2, and rendering it
        over the two Audit channels). The alternative -- keeping the seam
        synchronous -- would mean blocking the event loop on a `CREATE OR
        REPLACE` plus a `plpgsql_check` SELECT, which is exactly what
        `_run_async` exists to prevent.

        The `CheckRequest` is built HERE for the same reason `_check_active_ddl_
        object` builds it here: a trigger's referenced function is knowledge the
        ref alone does not carry, and the controller must not guess it.
        """
        if self.sandbox_controller.session is None:
            # Unreachable through the wiring (the seam is only wired while a
            # session exists), but a stated outcome beats a crash -- and a
            # synchronous return here is honest, because nothing was started.
            return ApplyOutcome.failed(
                "no sandbox session is open -- nothing was applied"
            )
        request = CheckRequest.from_ref(
            ref, text, **self._trigger_function_for(ref, text)
        )
        panel = self.center_stage.ddl_object_tab(getattr(ref, "key", None))

        def on_done(result, panel=panel, text=text) -> None:
            report = getattr(result, "report", None)
            if report is None or panel is None:
                # The refusal's own reason is reported by
                # `_on_sandbox_operation_finished`; an absent report is never
                # shown as a successful apply.
                return
            panel.record_apply_result(report, text)

        self.sandbox_controller.run_apply(request, on_done, ddl_text=text)
        return None

    # --- §18.5 D3/D3a: the two check gestures --------------------------------
    def _check_active_ddl_object(self) -> None:
        """Database ▸ Check Object in Sandbox -- D3a's `recheck`, run over the
        ACTIVE object tab's buffer.

        **Applies nothing**, which is what it costs: tiers 0-2 are *about*
        applying, so `recheck` reports tier 1 as unavailable and tier 2 as the
        bookkeeping fact ("the sandbox already holds this, applied <when>") plus
        the stale-buffer caveat. The gesture that actually compiles this buffer
        is Check Object Without Applying (or Apply to Sandbox).
        """
        self._run_ladder_on_active_ddl_object(probe=False)

    def _probe_check_active_ddl_object(self) -> None:
        """Database ▸ Check Object Without Applying -- §18.5 D3's rolled-back
        probe (`db/ddl_check.py::probe_check`, `apply_ddl(..., commit=False)`).

        The **whole** ladder runs, on this buffer, exactly as Apply to Sandbox
        would run it -- tier 2 really compiles the DDL, tier 1 really lints it,
        tier 3 really calls `plpgsql_check` -- and then the transaction is rolled
        back, so the sandbox is unchanged and no working-set row is written.
        This is the one narrow place rollback survives in §18 (D2), and it is
        the gesture that answers *"would this compile?"* without committing.

        The result is recorded for Apply-to-Target's precondition 2, because it
        IS a green-for-this-buffer ladder run; what it deliberately does not
        touch is `applied_sha1`, since nothing was applied.
        """
        self._run_ladder_on_active_ddl_object(probe=True)

    def _run_ladder_on_active_ddl_object(self, *, probe: bool) -> None:
        """The shared body of the two Database-menu check gestures. Exactly one
        object per run (D3a): there is no implicit multi-object sweep.

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

        if probe:
            self.sandbox_controller.run_apply(
                request, on_done, ddl_text=text, probe=True
            )
        else:
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

    def _build_tools_menu(self):
        menu = self.menuBar().addMenu("Tools")
        manage_captions_action = menu.addAction("Manage Captions...")
        manage_captions_action.triggered.connect(self._enter_caption_mode)
        caption_filter_action = menu.addAction("Caption Filter…")
        caption_filter_action.triggered.connect(self._open_caption_filter_dialog)
        menu.addSeparator()
        validate_action = menu.addAction("Validate Project")
        validate_action.triggered.connect(self._find_ui.validate_project)
        menu.addSeparator()
        # §22 PHP lint. Directly under Validate Project because it is the same
        # kind of gesture one tier down (this file, not the project), and all
        # three feed the one Audit panel -- `[Lint]`, never `[Validate]`'s or
        # §18.5's `[Check]` prefix. Lambdas: `_lint_ui` is built after the menu.
        lint_action = menu.addAction("Lint Current File")
        lint_action.triggered.connect(lambda: self._lint_ui.lint_active_file())
        self._lint_on_save_action = menu.addAction("Lint on Save")
        self._lint_on_save_action.setCheckable(True)
        self._lint_on_save_action.toggled.connect(
            lambda checked: self._lint_ui.set_lint_on_save(checked)
        )
        locate_linter_action = menu.addAction("Locate PHP Linter…")
        locate_linter_action.triggered.connect(lambda: self._lint_ui.locate_linter())
        menu.addSeparator()
        reparse_action = menu.addAction("Reparse Raw XML into Tree")
        reparse_action.triggered.connect(self._reparse_raw_xml)
        menu.addSeparator()
        compare_action = menu.addAction("Compare / Merge Two Files...")
        compare_action.triggered.connect(self._diff_ui.compare_two_files)
        next_action = menu.addAction("Next Difference")
        next_action.triggered.connect(self.center_stage.diff_merge_panel.select_next_difference)
        prev_action = menu.addAction("Prev Difference")
        prev_action.triggered.connect(self.center_stage.diff_merge_panel.select_previous_difference)
        apply_action = menu.addAction("Apply Changes to Target")
        apply_action.triggered.connect(self._diff_ui.apply_changes_to_target)
        menu.addSeparator()
        # §23 Tools ▸ Start MCP Server. CHECKABLE and unchecked at startup:
        # §23's "off by default … must not be silent or default-on" needs the
        # running/not-running state to be visible, and unchecking is the stop
        # gesture (`server.stop()`), so one menu entry covers both directions
        # rather than a Start/Stop pair the spec does not list.
        #
        # §23 words the opt-in as living "in Preferences", but Preferences is
        # still a stub (`_add_stub_action` -> "Not yet implemented"), so there is
        # nowhere to opt in FROM. This menu action is the honest interim: it is
        # the explicit, per-session opt-in gesture, and no persisted preference
        # can start the server behind the user's back. When a real Preferences
        # dialog lands it should gain a matching entry, not replace this one.
        mcp_action = menu.addAction("Start MCP Server")
        mcp_action.setCheckable(True)
        mcp_action.setChecked(False)
        mcp_action.toggled.connect(self._on_mcp_server_toggled)
        self._mcp_action = mcp_action

    # -- §23 MCP server ------------------------------------------------------

    def _on_mcp_server_toggled(self, checked: bool) -> None:
        """Start or stop §23's embedded MCP server from Tools ▸ Start MCP Server.

        Starting hands `start_server_thread` a `LiveProjectProvider` reading the
        host's open document at CALL time, which is the whole point of the in-app
        server: §23's "when the GUI is running it shares the currently-open
        in-memory model". The provider is a plain zero-argument callable, so the
        `mcp` package stays Qt-free, and a path-less tool call answers from the
        editor's live model -- including unsaved edits already reparsed into it --
        while a call naming some other `.pgtp` still falls back to loading it
        from disk.

        The server runs on a DAEMON thread (`start_server_thread`) because
        `serve` blocks on stdin and the GUI thread must not. Unchecking calls
        `server.stop()`; the thread finishes after the message in flight.
        A failure to start is reported and the checkbox snapped back, never left
        claiming a session that does not exist.
        """
        if checked:
            if self._mcp_session is not None:
                return
            # Imported here, not at module scope: importing the package starts
            # nothing (§23), but a feature nobody enabled should not cost the
            # GUI an import either. The PROVIDER is always the real one -- only
            # the thread-starting call is injectable, so a test still exercises
            # the live-model sharing without entering a stdio loop.
            from pgtp_editor.mcp import LiveProjectProvider, start_server_thread

            starter = self._mcp_start if self._mcp_start is not None else start_server_thread
            try:
                provider = LiveProjectProvider(
                    lambda: (self._current_project_path, self._current_project)
                )
                self._mcp_session = starter(provider)
            except Exception as exc:  # pragma: no cover - defensive
                _log.warning("mcp: start failed: %s", exc)
                self.statusBar().showMessage(
                    f"Could not start the MCP server: {exc}", 5000
                )
                if self._mcp_action is not None:
                    self._mcp_action.setChecked(False)
                return
            _log.info("mcp: server started")
            self.statusBar().showMessage("MCP server running on stdio.", 5000)
            return

        session = self._mcp_session
        self._mcp_session = None
        if session is None:
            return
        server = session[0]
        try:
            server.stop()
        except Exception as exc:  # pragma: no cover - defensive
            _log.warning("mcp: stop failed: %s", exc)
        _log.info("mcp: server stopped")
        self.statusBar().showMessage("MCP server stopped.", 5000)

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
