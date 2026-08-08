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
import re
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
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenuBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor import debuglog
from pgtp_editor.model.line_index import node_at_line
from pgtp_editor.ui._stub_action import add_stub_action
from pgtp_editor.ui.about import show_about_dialog
from pgtp_editor.ui.center_stage import (
    DDL_EXPLORER_ROLES,
    DDL_EXPLORER_SANDBOX,
    DDL_EXPLORER_TARGET,
    CenterStage,
)
from pgtp_editor.ui import modals
from pgtp_editor.ui.manual_panel import (
    ManualContentsPanel,
    load_manual_text,
    parse_chapters,
)
from pgtp_editor.db.config import (
    connection_from_tree,
    save_connection,
    seed_params,
)
from pgtp_editor.db.bookmark_store import (
    load_editor_bookmarks,
    store_editor_bookmarks,
)
from pgtp_editor.db.ddl_buffer import build_ddl_text
from pgtp_editor.db.migration_gen import connection_summary
from pgtp_editor.db.ddl_project import (
    DeployedObject,
    compute_drift_markers,
    content_hash,
    routine_ddl_paths,
    save_settings,
    trigger_ddl_path,
)
from pgtp_editor.db.introspect import RoutineInfo, fetch_routines_and_triggers
from pgtp_editor.db.introspect import test_connection as db_test_connection
from pgtp_editor.db.schema_index import SchemaIndex
from pgtp_editor.db.sandbox import SandboxMode
from pgtp_editor.ui.async_task import run_async
from pgtp_editor.ui.connection_setup_dialog import ConnectionSetupDialog
from pgtp_editor.ui.new_project_dialog import NewProjectDialog
from pgtp_editor.db.apply import ApplyOutcome
from pgtp_editor.db.ddl_check import CheckRequest
from pgtp_editor.ui.ddl_object_editor import (
    CHECK_PREFIX,
    DEST_SANDBOX,
    DESTINATION_UNAVAILABLE_REASONS,
    DdlObjectRef,
)
from pgtp_editor.ui.sandbox_controller import SandboxController, SandboxOperation
from pgtp_editor.ui.sandbox_setup_dialog import SandboxSetupDialog
from pgtp_editor.ui.new_routine_dialog import NewRoutineDialog
from pgtp_editor.ui.new_trigger_dialog import NewTriggerDialog
from pgtp_editor.ui.project_status_model import SandboxFact, build_diagram, quality_state
from pgtp_editor.ui.project_status_panel import ProjectStatusPanel
from pgtp_editor.ui.coherence_controller import CoherenceController
from pgtp_editor.ui.coherence_panel import CoherencePanel
from pgtp_editor.ui.ddl_project_controller import DdlProjectController
from pgtp_editor.ui.diff_merge_controller import DiffMergeController
from pgtp_editor.ui.find_controller import FindValidateController
from pgtp_editor.ui.ddl_buffer_panel import BrowserPanel
from pgtp_editor.ui.code_editor import CodeEditorDialog
# FQ-013: the shared gutter mixin publishes bookmark changes; the host
# subscribes and decides what they mean (the mixin knows nothing about projects).
from pgtp_editor.ui.editor_gutter import (
    BOOKMARKS_RESET,
    add_bookmark_observer,
    remove_bookmark_observer,
)
from pgtp_editor.ui.history import SnapshotHistory
# §21/§22: the custom-PHP editing lane and the PHP lint lane. `LINT_AUDIT_TARGET`
# is the `UserRole + 1` tag a `[Lint]` Audit row carries, read by
# `_on_audit_item_clicked` to route the click to a PHP tab.
from pgtp_editor.lint.findings import LINT_AUDIT_TARGET
from pgtp_editor.ui.generation_controller import GenerationController
from pgtp_editor.ui.lint_controller import LintController
from pgtp_editor.ui.pgtp_document_controller import PgtpDocumentController
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

#: How long a bookmark change waits before it is written to
#: `<project>/.ddlproject/bookmarks.json` (FQ-013). Deliberately coarse: a
#: bookmark toggle is a hot single-click gutter gesture and must not do disk I/O,
#: and a user re-tagging several lines in a row produces one write, not five. Any
#: pending write is also flushed on a project transition and on app close, so the
#: debounce can never be the reason a bookmark is lost.
_BOOKMARK_WRITE_DEBOUNCE_MS = 400

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
        # Database ▸ "DDL Explorer (Quality)" toggle (mirrors the coherence tab).
        # This is the TARGET-role instance; §18.7's sandbox one is built right
        # below it.
        self.ddl_browser_panel = BrowserPanel()
        self.ddl_browser_tab_index = self.left_tabs.addTab(
            self.ddl_browser_panel, "DDL Objects (Quality)"
        )
        self.left_tabs.setTabVisible(self.ddl_browser_tab_index, False)
        self.ddl_browser_panel.navigate_requested.connect(
            self._on_ddl_navigate_requested
        )
        # Right-click ▸ Edit DDL opens/focuses the editable DDL object tab
        # (spec §18.5, D1 entry point 1) -- ONE gesture whose behaviour the
        # handler picks from project state (FQ-024), not a pair of entries.
        self.ddl_browser_panel.edit_requested.connect(self._on_ddl_edit_requested)
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
        # §18.7 (FQ-022): the SECOND Explorer instance -- the same `BrowserPanel`
        # class with unchanged internals, fed by the project sandbox's own
        # `ConnectionParams`. `browse_only` because `Edit DDL` from here would
        # take the checkout branch and seed `ddl/*.sql` from the sandbox (see
        # `BrowserPanel.__init__`), so it offers no edit/create gestures at all
        # and there is deliberately no `edit_requested` connection to make.
        #
        # Both dock tabs are LABELLED by role: two identically-named "DDL
        # Objects" trees would be untellable apart in the tab bar.
        self.sandbox_ddl_browser_panel = BrowserPanel(browse_only=True)
        self.sandbox_ddl_browser_tab_index = self.left_tabs.addTab(
            self.sandbox_ddl_browser_panel, "DDL Objects (Sandbox)"
        )
        self.left_tabs.setTabVisible(self.sandbox_ddl_browser_tab_index, False)
        self.sandbox_ddl_browser_panel.navigate_requested.connect(
            lambda line: self._on_ddl_navigate_requested(line, DDL_EXPLORER_SANDBOX)
        )
        # The Properties feed is a pure read of the clicked node, so the sandbox
        # tree drives the same shared panel -- nothing about it writes anywhere.
        self.sandbox_ddl_browser_panel.table_selected.connect(
            self._on_ddl_table_selected
        )
        #: role -> the `BrowserPanel` for that connection (§18.7). The one place
        #: the role->tree mapping lives, so the fetch, the visibility lockstep
        #: and the dock-tab reveal cannot disagree about which tree is which.
        self._ddl_browser_panels = {
            DDL_EXPLORER_TARGET: self.ddl_browser_panel,
            DDL_EXPLORER_SANDBOX: self.sandbox_ddl_browser_panel,
        }
        self._ddl_browser_tab_indexes = {
            DDL_EXPLORER_TARGET: self.ddl_browser_tab_index,
            DDL_EXPLORER_SANDBOX: self.sandbox_ddl_browser_tab_index,
        }
        self.tree_dock.setWidget(self.left_tabs)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tree_dock)

        self.audit_panel = QListWidget()
        self.audit_dock = QDockWidget("Audit / Problems", self)
        self.audit_dock.setObjectName("audit_dock")
        self.audit_dock.setWidget(self.audit_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.audit_dock)

        self.center_stage = CenterStage()

        # §7/§26 (FQ-016): a SECOND, FIXED menu bar directly above the central
        # pane -- "that's not a toolbar, that's a menubar. Toolbar is just a
        # collection of favourite commands." Fixed = the app decides its
        # contents; it is not the user-curated toolbar.
        #
        # It has to be a CHILD QMenuBar inside a container widget that becomes
        # the central widget, because a QMainWindow's own menu-bar/toolbar areas
        # span the full window width INCLUDING above the docks -- and this bar
        # must sit strictly above the central pane. `self.center_stage` still
        # points at the `CenterStage` (which is what every caller and ~534 test
        # references address); only `centralWidget()` changes, and exactly one
        # test asserted that coupling.
        #
        # PLATFORM SPLIT, deliberate and structural rather than cosmetic: on
        # macOS the *window* menu bar is absorbed into the system menu bar while
        # a child QMenuBar renders inline, so the two bars do not look like
        # siblings there. `setNativeMenuBar(False)` states the intent for this
        # one explicitly -- it must never be a candidate for absorption, or the
        # Editor commands would silently merge into the window bar.
        self.editor_menu_bar = QMenuBar()
        self.editor_menu_bar.setNativeMenuBar(False)
        central_container = QWidget(self)
        central_layout = QVBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.editor_menu_bar)
        central_layout.addWidget(self.center_stage)
        self.setCentralWidget(central_container)
        # The Editor menu bar is meaningless on the non-editor tabs, so the whole
        # bar is hidden there (§29's recorded recommendation) -- see
        # `_refresh_editor_menu_affordances`, wired the same way
        # `_refresh_sandbox_affordances` is: one entry point, visibility only.
        self.center_stage.currentChanged.connect(
            lambda _index: self._refresh_editor_menu_affordances()
        )

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
        # DDL Explorer's read-only buffer's own right-click ▸ Edit DDL (spec
        # §18.5, D1 entry point 2) -- same target handler as BrowserPanel's
        # tree entry point.
        self.center_stage.ddl_editor_panel.edit_requested.connect(
            self._on_ddl_edit_requested
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
        # FQ-017: the two window-scoped, mode-gated Ctrl+F / Ctrl+R shortcuts
        # that opened the Caption Filter / Replace modal are GONE along with the
        # modal itself. The caption panel's own permanently visible
        # Find/Replace bar owns those keys now, as panel-scoped focus shortcuts
        # (caption_management_panel: _focus_find_shortcut /
        # _focus_replace_shortcut), so no caption find/replace state lives on
        # the host any more.
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

        # The open `.pgtp` document (`_doc_ui`) and the active §18.2 local
        # project (`_ddl_project_ui`) own their own state; both are constructed
        # after the `UiShell` below, and the six delegating properties just
        # under `__init__` are the CLOSED set of names the rest of the window
        # still reads them through.
        #: §18.5 D2/D3a/D4: the one owner of at most one `SandboxSession` for
        #: the open project. Every `db/sandbox.py` entry point on it is an
        #: injected seam, kept at production defaults here EXCEPT `prober`,
        #: which is routed through the project lane's already-injectable
        #: `probe_sandbox_capabilities` so the whole window probes through one
        #: seam. A lambda, so it resolves the lane at CALL time -- this runs
        #: before `_ddl_project_ui` exists. Public attribute so tests can
        #: replace its seams (and its `_run_async`) wholesale.
        self.sandbox_controller = SandboxController(
            self,
            confirm_destructive=self._confirm_destructive_sandbox_operation,
            prober=lambda params: self._ddl_project_ui.probe_sandbox_capabilities(
                params
            ),
        )
        self.sandbox_controller.session_changed.connect(self._on_sandbox_session_changed)
        self.sandbox_controller.operation_finished.connect(
            self._on_sandbox_operation_finished
        )
        #: §18.5 D4: `() -> SandboxSession | None`. The ONE attribute the
        #: sandbox lane repoints -- aimed at the controller's `session`
        #: accessor, so "is there a session?" has exactly one answer.
        #: Everything console-related asks `_sandbox_console_available()`,
        #: which asks this. None (or a None return) means no console TAB can
        #: exist -- never one that is present-but-refusing. Since FQ-023 it no
        #: longer decides the MENU ENTRY on its own: that follows whether a
        #: sandbox is configured, and reports this answer when asked.
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
        #: §18.5 D3's "Check without applying" probe, gated on exactly the same
        #: predicate as Check itself.
        self._sandbox_probe_check_action = None
        #: §18.7's Database ▸ DDL Explorer (Sandbox) toggle -- created hidden and
        #: shown by `_refresh_ddl_explorer_affordances` while the open project has
        #: a sandbox configured. Same before-`_build_menu_bar` initialisation
        #: reason as the three above, and the same reason for the pair map below.
        self._sandbox_ddl_explorer_action = None
        self._ddl_explorer_actions = {}
        self._open_sandbox_session_action = None
        self._close_sandbox_session_action = None
        #: §18.5's "Deploy this edit…" picker as a menu entry (FQ-009). Always
        #: visible -- no session gate, because its Save destination needs none.
        self._deploy_this_edit_action = None
        #: Database ▸ Sandbox Setup… -- always present (see `_build_database_menu`
        #: for why it is not session-gated), so unlike the four above it needs no
        #: visibility management. Kept on `self` only so the non-modal dialog it
        #: opens outlives the handler's stack frame (the same keep-alive pattern
        #: `DdlProjectController`'s two dialogs use).
        self._sandbox_setup_action = None
        self._sandbox_setup_dialog = None

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
        # The checkable Parsing-menu action is created later by
        # `_build_parsing_menu` (it was on Edit before FQ-016), so the
        # attribute exists as None first -- `blockCountChanged` is
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

        #: The open `.pgtp` document lane (`ui/pgtp_document_controller.py`):
        #: open / reparse / save / close / revert, the §7 Revert gate,
        #: plus the four pieces of document state
        #: (`project`/`project_path`/`dirty`/`loading`) the six delegating
        #: properties below forward to.
        #:
        #: It and `_ddl_project_ui` form a CYCLE -- opening a `.pgtp` consults
        #: the project's link, and opening a project auto-opens its linked
        #: `.pgtp` -- which needs no two-phase construction because every
        #: provider is a callable resolved at CALL time. Hence the lambdas over
        #: `self._ddl_project_ui` here, and `open_pgtp_file` over the host's
        #: public `open_project_file` there.
        self._doc_ui = PgtpDocumentController(
            self._shell,
            parent=self,
            # `busy_status` needs an object with `showMessage`, which
            # `UiShell.status` (a bare callable) is not.
            status_bar=self.statusBar,
            reset_properties=lambda: self.properties_panel.show_node(None, None),
            history_push=lambda *args, **kwargs: self._history.push(*args, **kwargs),
            history_clear=lambda: self._history.clear(),
            enrich_schema=self._xsd_ui.enrich_from_file,
            refresh_coherence=lambda project: self._db_ui.refresh_if_open(project),
            resolve_project_path=lambda path: self._ddl_project_ui.resolve_pgtp_path(
                path
            ),
            link_pgtp=lambda: self._ddl_project_ui.link_pgtp_if_needed(),
            import_pgtp_connection=self._import_pgtp_connection_into_target,
            working_copy_path=lambda: self._ddl_project_ui.pgtp_working_copy_path(),
            has_ddl_project=lambda: self._ddl_project_ui.is_open,
            new_ddl_project=lambda on_ready=None: self._ddl_project_ui.new_project(
                on_ready=on_ready
            ),
            open_ddl_project=lambda on_ready=None: self._ddl_project_ui.open_project(
                on_ready=on_ready
            ),
        )

        #: The §18.2 local-project lane (`ui/ddl_project_controller.py`): New /
        #: Open / Close Project, Project Settings, the `.pgtp` link and deploy,
        #: the top-of-§18 capability probe and BUG-030's target reachability
        #: probe. `open_pgtp_file` deliberately points at the host's PUBLIC
        #: `open_project_file` (which `main.py` also calls), through a lambda so
        #: a test that replaces it on the finished window is honoured.
        self._ddl_project_ui = DdlProjectController(
            self._shell,
            parent=self,
            open_pgtp_file=lambda path: self.open_project_file(path),
            document_path=lambda: self._doc_ui.project_path,
            set_document_path=lambda path: setattr(
                self._doc_ui, "project_path", path
            ),
            bind_sandbox=self._bind_sandbox_controller_to_project,
            provision_sandbox=self._provision_new_project_sandbox,
            target_params=self._project_status_target,
            refresh_status_window=self._refresh_project_status_window,
            explorer_schema=lambda: getattr(self.ddl_browser_panel, "_schema", None),
        )
        # The window title carries both the project folder and the document's
        # name + dirty marker, so both lanes' transitions refresh it.
        self._ddl_project_ui.project_changed.connect(
            lambda _folder, _settings: self._update_title()
        )
        self._doc_ui.dirty_changed.connect(lambda _dirty: self._update_title())
        # The document's tree feed: emitted with the freshly parsed model at the
        # point the tree must be rebuilt from it (open / reparse / revert).
        self._doc_ui.project_changed.connect(self.project_tree.populate_from_project)
        # A COMMITTED project close is a broadcast, never a list of foreign
        # attribute writes inside `_doc_ui.close()` -- that is what stops BUG-011
        # (a coherence tab surviving a close) from coming back. The coherence
        # subscriber is connected where that lane is built, below.
        self._doc_ui.project_closed.connect(self.project_tree.clear)
        self._doc_ui.project_closed.connect(self._history.clear)

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
            project=lambda: self._doc_ui.project,
            project_path=lambda: self._doc_ui.project_path,
            ensure_saved=self._doc_ui.ensure_saved,
            default_output_dir=self._dialog_default_dir,
        )

        #: The find / replace / bookmarks / validate lane
        #: (`ui/find_controller.py`): the per-tab find-bar and bookmark-editor
        #: routing, the Navigation menu (owned outright, so it builds it — onto
        #: the Editor menu bar since FQ-016), the whole streaming Find-All run
        #: and Tier-2 validation. Built before the menu bar because
        #: `_build_menu_bar` calls `build_navigation_menu`, `_build_parsing_menu`
        #: wires its `validate_project` and `_install_find_next_action` routes
        #: F3 at it. Validation reads the open document through the same two
        #: providers `_gen_ui` uses.
        self._find_ui = FindValidateController(
            self._shell,
            parent=self,
            project=lambda: self._doc_ui.project,
            project_path=lambda: self._doc_ui.project_path,
            # FQ-014: `List All Bookmarks` writes nothing but Audit rows, so it
            # reveals the dock -- injected exactly as `CoherenceController`
            # receives it, never reached for through `self.audit_dock`.
            show_audit_dock=self._show_audit_dock,
        )

        #: The §7 Compare/Merge lane (`ui/diff_merge_controller.py`): the three
        #: comparison entry points, the comparison target they set, and Apply
        #: Changes to Target. `reload` re-opens the file Apply just wrote and
        #: points at the host's public `open_project_file` (which `main.py` also
        #: calls); when `PgtpDocumentController` lands only that line moves.
        self._diff_ui = DiffMergeController(
            self._shell,
            parent=self,
            project=lambda: self._doc_ui.project,
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
            # BUG-034: the ONE "which target connection" selector, injected --
            # this lane must not pick its own, or the app connects with one set
            # of credentials while Project Settings shows another.
            target_params=self._target_params_for_fetch,
            show_left_dock=self._show_left_dock,
            show_audit_dock=self._show_audit_dock,
            panel_visible=self._coherence_tab_visible,
        )
        self.coherence_panel.rename_requested.connect(self._db_ui.on_rename_requested)
        self.coherence_panel.name_jump_requested.connect(self._db_ui.on_jump_requested)
        self.coherence_panel.create_requested.connect(self._db_ui.on_create_requested)
        # BUG-011/§17: coherence results are project-tied, so the lane tears
        # itself down on a committed close (see `_doc_ui.project_closed`).
        self._doc_ui.project_closed.connect(self._db_ui.teardown_for_project_close)

        self._build_menu_bar()
        # F3 (Find Next) -- a window-level action with no menu entry, so it is
        # installed rather than built into a menu (§27; see the method).
        self._install_find_next_action()

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
        self._php_tabs.open_pgtp = lambda path: self._doc_ui.open_pgtp_path(path)
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
        # BOTH menu bars are the command universe since FQ-016 -- one walk over
        # a sequence of roots. Without the second root every Editor-bar command
        # would be unpinnable and invisible to Customize Toolbar and FQ-004's
        # icon assignments.
        self._toolbar_ui.build(
            (self.menuBar(), self.editor_menu_bar), self.addToolBar
        )

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

        # FQ-013: project-local bookmark persistence. Subscribed LAST so no
        # notification fired while the window was being assembled reaches the
        # store, and through the gutter's module-level registry rather than a
        # per-editor signal -- most editors (DDL object tabs, PHP tabs, draft
        # tabs) do not exist yet, and the mixin must stay ignorant of projects.
        self._bookmark_writes: dict[tuple[str, str], tuple[int, ...]] = {}
        self._bookmark_write_timer = QTimer(self)
        self._bookmark_write_timer.setSingleShot(True)
        self._bookmark_write_timer.setInterval(_BOOKMARK_WRITE_DEBOUNCE_MS)
        self._bookmark_write_timer.timeout.connect(self._flush_bookmark_writes)
        add_bookmark_observer(self._on_editor_bookmarks_changed)
        # A project transition is a quiet moment: flush anything still pending
        # (each pending entry carries its OWN folder, so a close cannot misroute
        # it), then restore for documents that were already open when the project
        # opened -- the `.pgtp`-first, project-second order.
        self._ddl_project_ui.project_changed.connect(
            self._on_bookmark_project_changed
        )

    # -- the six permanent delegating properties -----------------------------
    # CLOSED LIST -- do not extend. Four pieces of document state and two of
    # §18.2 project state are read (and written) from ~40 places across the
    # still-un-extracted lanes and from ~150 test assertions. Twelve one-line
    # properties buy all of that; a thirteenth would be a compatibility shim,
    # which `_LEGACY_DELEGATES` above exists to make visible instead. Anything
    # else a lane needs from another lane is an injected callable or a signal.

    @property
    def _current_project(self):
        """The open `.pgtp`'s last successfully parsed model, or None."""
        return self._doc_ui.project

    @_current_project.setter
    def _current_project(self, value):
        self._doc_ui.project = value

    @property
    def _current_project_path(self):
        """The file a Save writes to, or None."""
        return self._doc_ui.project_path

    @_current_project_path.setter
    def _current_project_path(self, value):
        self._doc_ui.project_path = value

    @property
    def _dirty(self):
        """Whether the Raw XML buffer differs from what is on disk."""
        return self._doc_ui.dirty

    @_dirty.setter
    def _dirty(self, value):
        self._doc_ui.dirty = value

    @property
    def _loading(self):
        """True while a programmatic buffer replacement is in flight."""
        return self._doc_ui.loading

    @_loading.setter
    def _loading(self, value):
        self._doc_ui.loading = value

    @property
    def _ddl_project_folder(self):
        """The active §18.2 local project's folder, or None."""
        return self._ddl_project_ui.folder

    @_ddl_project_folder.setter
    def _ddl_project_folder(self, value):
        self._ddl_project_ui.folder = value

    @property
    def _ddl_project_settings(self):
        """The active §18.2 local project's `ProjectSettings`, or None."""
        return self._ddl_project_ui.settings

    @_ddl_project_settings.setter
    def _ddl_project_settings(self, value):
        self._ddl_project_ui.settings = value

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
        self._doc_ui.save_project()

    # -- FQ-013: project-local bookmark persistence ---------------------------
    # The gate is the CAPABILITY fact "a §18.2 project is open"
    # (`DdlProjectController.folder`), never the launcher's mode: with no project
    # there is no root to key paths against, and behaviour must stay exactly as
    # it was -- session-only, wiped by `setPlainText`, nothing written anywhere.
    # Every method below short-circuits on a `None` folder, so the projectless
    # path costs one attribute read.
    #
    # WHEN it saves: on a debounce after the user changes a set (toggle / Clear
    # All), plus a synchronous flush on a project transition and on app close.
    # Never inside `toggle_bookmark` -- see `_BOOKMARK_WRITE_DEBOUNCE_MS`.
    # WHEN it restores: at the one moment the set is wiped, i.e. when a document
    # is loaded into an editor (the gutter's RESET notification). That is the same
    # moment for a reopened project, a revert, an XSD-mode switch, a re-checkout
    # and an app restart, so one hook covers all of them; plus a sweep when a
    # project opens, for documents that were already open before it did.

    def _on_editor_bookmarks_changed(self, editor, reason: str) -> None:
        """`ui/editor_gutter.py`'s bookmark notification, host side.

        A RESET (a new document in that editor) is a restore, never a write --
        writing the just-emptied set back would erase what is stored. Any other
        reason is a user-chosen set, so it is scheduled for writing."""
        if reason == BOOKMARKS_RESET:
            self._restore_editor_bookmarks(editor)
            return
        self._schedule_bookmark_write(editor)

    def _bookmark_file_path(self, editor):
        """The file `editor`'s bookmarks are keyed by, or None when it has no
        stable project-relative identity and therefore stays session-only.

        None on purpose for: the **read-only DDL Explorer buffer** and **FQ-006
        draft tabs** (no persistent file at all), the **`Edit code…` dialog** (a
        modal over an event body inside the XML, and not reachable from here),
        and the **Edit XSD / Edit AutoXSD** editors -- their schema files live in
        the app-level schema storage directory, not under any project, so
        `relative_key` could not key them even if they were offered.
        """
        stage = self.center_stage
        if editor is stage.xml_editor:
            # The open document: in project mode that is the working-copy
            # `.pgtp` inside the project. A document outside the project has no
            # key, which `relative_key` answers on its own.
            return self._doc_ui.project_path
        for panel in stage.ddl_object_panels():
            if panel.editor is editor:
                return panel.save_path
        for tab in stage.php_file_tabs().values():
            if tab.editor is editor:
                return tab.path
        return None

    def _bookmark_store_target(self, editor):
        """`(project_folder, file_path)` for `editor`, or None when bookmarks
        cannot be persisted for it (no project open, or no file identity)."""
        folder = self._ddl_project_ui.folder
        if folder is None:
            return None
        path = self._bookmark_file_path(editor)
        if path is None:
            return None
        return folder, Path(path)

    def _restore_editor_bookmarks(self, editor) -> None:
        """Put the stored bookmarks for `editor`'s document back, dropping the
        ones beyond its current length (v1 has no content anchoring).

        The store is NOT rewritten here, so a document that is temporarily
        shorter than it was still has its out-of-range lines on disk when it
        grows back."""
        target = self._bookmark_store_target(editor)
        if target is None:
            return
        folder, path = target
        lines = load_editor_bookmarks(folder, path, editor.blockCount())
        if lines:
            editor.restore_bookmarks(lines)

    def _schedule_bookmark_write(self, editor) -> None:
        """Record `editor`'s current set for the next flush and (re)start the
        debounce.

        The folder, the path and the lines are all resolved NOW, so a pending
        write survives the editor's tab being closed and a project being closed
        underneath it -- and so the flush itself touches no widgets."""
        target = self._bookmark_store_target(editor)
        if target is None:
            return
        folder, path = target
        self._bookmark_writes[(str(folder), str(path))] = tuple(
            editor.bookmarked_lines()
        )
        self._bookmark_write_timer.start()

    def _flush_bookmark_writes(self) -> None:
        """Write every pending bookmark set. Called by the debounce timer, on a
        project transition and on app close; a no-op with nothing pending."""
        pending, self._bookmark_writes = self._bookmark_writes, {}
        self._bookmark_write_timer.stop()
        for (folder, path), lines in pending.items():
            store_editor_bookmarks(folder, path, lines)

    def _on_bookmark_project_changed(self, folder, _settings) -> None:
        """A §18.2 project was opened, created or closed: flush what is pending
        (each entry carries its own folder, so a close cannot misroute it), then
        restore for editors that already hold their document -- the case where
        the `.pgtp` was opened first and the project second."""
        self._flush_bookmark_writes()
        if folder is None:
            return
        stage = self.center_stage
        editors = [stage.xml_editor]
        editors += [panel.editor for panel in stage.ddl_object_panels()]
        editors += [tab.editor for tab in stage.php_file_tabs().values()]
        for editor in editors:
            self._restore_editor_bookmarks(editor)

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
    # to the document lane's `open_pgtp_path`, a binary or a folder is refused
    # out loud).

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
        # FQ-013: the last chance to write bookmarks the debounce has not written
        # yet, and the point this window stops observing gutter notifications --
        # a closed window must not answer a later editor's bookmark change.
        self._flush_bookmark_writes()
        remove_bookmark_observer(self._on_editor_bookmarks_changed)
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
        self._doc_ui.set_dirty(True)
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
        self._doc_ui.reparse(silent=True)

    # -- the one public document entry point ---------------------------------

    def open_project_file(self, path):
        """Load and display the `.pgtp` project at `path` (§1).

        Stays PUBLIC on the host — §21's drag-and-drop and the Compare/Merge
        lane's post-Apply reload both call it, and a test replaces it on the
        finished window — while
        the loading itself belongs to `_doc_ui`. The one method the six
        delegating properties below are not enough for.
        """
        return self._doc_ui.open_file(path)

    def _build_menu_bar(self):
        # The WINDOW menu bar: window-global commands only. There is no `Edit`
        # menu -- FQ-016 DISSOLVED it (it was not emptied): Undo/Redo/History…
        # went to the Editor bar's History, Cut/Copy/Paste/Delete and
        # Preferences… were deleted stubs, the five Find/Replace entries became
        # the permanently visible bar, the two selection commands went to
        # FQ-015's `Select` and `Auto Parse XML` went to Parsing.
        self._build_file_menu()
        self._build_view_menu()
        # The Schema menu is owned outright by the §11 lane, so it builds it
        # (and registers its own window-level Ctrl+L action through the host's
        # `addAction`) -- called from here so the menu keeps its position in
        # the bar.
        self._xsd_ui.build_menu(self.menuBar(), self.addAction)
        self._build_database_menu()
        self._build_tools_menu()
        # The Generation menu is owned outright by the generation lane, so it
        # builds it -- called from here so the menu keeps its position in the bar.
        self._gen_ui.build_menu(self.menuBar())
        self._build_help_menu()
        # ...then the second bar, above the central pane.
        self._build_editor_menu_bar()

    def _build_editor_menu_bar(self):
        """The Editor menu bar's four menus, in order (§7/§26, FQ-016).

        It holds **editing** commands — the deliberate concept name. Calling it
        "per-tab" would be false: `History…` opens the *project snapshot*
        navigator and Undo/Redo are project-snapshot actions except on the Edit
        XSD and DDL object tabs, where §27's pinned carve-out routes Ctrl+Z/Ctrl+Y
        to that editor's own native stack.
        """
        self._build_history_menu()
        self._build_select_menu()
        self._build_parsing_menu()
        # The Navigation menu is owned outright by the find/validate lane, so it
        # builds it -- called from here so the menu lands on THIS bar (it was a
        # top-level window menu between Tools and Generation before FQ-016) and
        # keeps its position on it.
        self._find_ui.build_navigation_menu(self.editor_menu_bar)
        self._refresh_editor_menu_affordances()

    def _build_history_menu(self):
        """History ▸ History… · Undo · Redo — in that order (FQ-016).

        The owner's ordering, verbatim reasoning: *"everyone uses
        Ctrl+Z/Ctrl+Y anyway"*, so the navigator that has no shortcut leads.
        Undo/Redo are the same single-step actions the Ctrl+Z/Ctrl+Y shortcuts
        drive (wired in `__init__`); `History…` opens the non-modal navigator
        where moving back = undo and forward = redo.

        Their command ids become `history.undo` / `history.redo`, both pinned in
        `LEGACY_ID_ALIASES` — updated in the same commit, or two DEFAULT toolbar
        buttons ship empty and iconless (`toolbar_registry`).
        """
        menu = self.editor_menu_bar.addMenu("History")
        history_action = menu.addAction("History…")
        history_action.triggered.connect(self._open_history_jump_list)
        self._history_action = history_action
        undo_action = menu.addAction("Undo")
        undo_action.triggered.connect(self._undo)
        self._undo_action = undo_action
        redo_action = menu.addAction("Redo")
        redo_action.triggered.connect(self._redo)
        self._redo_action = redo_action

    def _build_select_menu(self):
        """Select ▸ Select All · Select Enclosing Block · Select Parent Block
        (FQ-015, §8/§26).

        `Select All` is a NEW entry for behaviour that already worked: nothing in
        the app binds Ctrl+A, so every editor's built-in select-all has always
        functioned — including in the read-only buffers (the DDL Explorer and
        Raw XML in Caption Mode), because `setReadOnly(True)` keeps Qt's
        text-selectable interaction flag. The gap was discoverability, so the
        menu entry is the whole feature. It is deliberately NOT gated in Caption
        Mode (unlike Find/Replace, which that mode owns): selecting text mutates
        nothing.

        The other two MOVED here off the dissolved Edit menu — and are rebuilt,
        not relocated: FQ-016 removed them with the menu, so between it and this
        change Ctrl+Shift+A had no host at all and Ctrl+Shift+B survived only
        through `CodeEditor.keyPressEvent`.

        **All three resolve the editor at TRIGGER time** via
        `FindValidateController.active_selection_editor` — the bug fix that
        rides with the move. They used to be connected straight to
        `center_stage.xml_editor`'s bound methods, so the chords pressed on a PHP
        tab, a DDL object tab or an FQ-006 draft tab selected inside the **Raw
        XML** document. Never re-bind a per-tab command to a widget at build
        time; the Navigation menu's docstring states the same rule.

        Shortcuts are unchanged (§27): no chord is rebound and none is new to the
        app — Ctrl+A is the platform default the widgets already implemented.
        Note what that means for Ctrl+A specifically: a *focused* text widget
        keeps handling it itself (Qt lets a text control claim standard editing
        chords via `ShortcutOverride` before the window action sees them), so
        this action's own shortcut only fires when focus is elsewhere — e.g. in
        the structure tree — where it then acts on the active editor. That is
        also why the action cannot steal Ctrl+A from a `QLineEdit`.
        """
        menu = self.editor_menu_bar.addMenu("Select")
        self._select_menu = menu
        select_all_action = menu.addAction("Select All")
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(self._select_all_in_active_editor)
        self._select_all_action = select_all_action
        menu.addSeparator()
        select_enclosing_action = menu.addAction("Select Enclosing Block")
        select_enclosing_action.setShortcut("Ctrl+Shift+B")
        select_enclosing_action.triggered.connect(self._select_enclosing_block)
        self._select_enclosing_action = select_enclosing_action
        select_parent_action = menu.addAction("Select Parent Block")
        select_parent_action.setShortcut("Ctrl+Shift+A")
        select_parent_action.triggered.connect(self._select_parent_block)
        self._select_parent_action = select_parent_action

    def _select_all_in_active_editor(self) -> None:
        """`Select All` — the one member every editor family supports, since
        `selectAll` comes from `QPlainTextEdit` itself."""
        self._find_ui.active_selection_editor().selectAll()

    def _select_enclosing_block(self) -> None:
        """`Select Enclosing Block` — ONE command, two structural meanings, by
        editor family (FQ-015).

        * `XmlEditor` (Raw XML, Edit XSD, draft fragment tabs):
          `select_enclosing_block` — the innermost XML element, '<' through '>'.
        * `CodeEditor` (DDL Explorer, DDL object tabs, PHP tabs):
          `select_enclosing_brackets` — the innermost balanced `()[]{}` span.
          SQL and PHP have no XML tags to enclose, so the bracket pair is that
          family's equivalent and has always been what Ctrl+Shift+B did there.

        The dispatch must therefore go by capability, never by assuming one
        method name: the two methods are genuinely different, not two
        implementations of one interface.

        **The duplicate Ctrl+Shift+B handler, resolved (FQ-015 trap).**
        `CodeEditor.keyPressEvent` also handles the chord. This action WINS
        wherever it exists: Qt's shortcut map consumes the key event before it
        reaches the focused widget, so a `CodeEditor`-hosting tab does not
        double-handle (verified, not assumed). The editor-side handler is kept
        on purpose — it is the only host for the chord in a `CodeEditorDialog`,
        which has no menu bar, and it remains the reliable path under the
        offscreen test platform where QShortcut activation is not guaranteed.
        Both paths now land on the SAME editor, and the operation is idempotent,
        so even a double delivery would be harmless.
        """
        editor = self._find_ui.active_selection_editor()
        select = getattr(editor, "select_enclosing_block", None) or getattr(
            editor, "select_enclosing_brackets", None
        )
        if select is not None:
            select()

    def _select_parent_block(self) -> None:
        """`Select Parent Block` — XML-only, and ABSENT rather than silently
        wrong where there is no parent element (FQ-015).

        Only `XmlEditor` has `select_parent_block` ("one nesting level up"): a
        bracket pair has no analogous parent walk that means anything to a
        reader of SQL or PHP. So on a `CodeEditor` tab the entry is HIDDEN by
        `_refresh_editor_menu_affordances` — visibility, matching the app's
        two-posture rule (present / absent, never greyed) — which also drops
        Ctrl+Shift+A there, since Qt keeps a shortcut live only while its action
        is both enabled and visible. The capability guard below is the second
        belt: the action can be triggered programmatically.
        """
        editor = self._find_ui.active_selection_editor()
        select = getattr(editor, "select_parent_block", None)
        if select is not None:
            select()

    def _build_parsing_menu(self):
        """Parsing ▸ Auto Parse XML · Validate Project (FQ-016).

        `Validate Project` MOVED here off Tools — it is the owner's *"validate
        xml"*. Its command id therefore changes from `tools.validate-project` to
        `parsing.validate-project`, and its `LEGACY_ID_ALIASES` entry is updated
        in the same commit because it is one of the DEFAULT toolbar buttons AND
        the key of its vendored `dialog-ok-apply` SVG.

        **What is NOT here, and why** — both recorded as open items (§29), so
        neither was decided unilaterally:

        * **plpgsql check** (`Check DDL Object` / `Check without applying`) does
          not exist yet in any menu: §18.5 D3a is target design and §26 currently
          assigns those two gestures to the **Database** menu. They land with
          `db/ddl_check.py`; whether they land here instead is the owner's call.
        * **`Lint Current File`** stays on Tools with `Lint on Save` and
          `Locate PHP Linter…`. Moving only the first of the three would split
          lint across two bars — the exact complaint this work exists to fix —
          and whether all three move is the open question.

        **Membership gating.** §7 asks for `setVisible` gating by *active tab
        kind* (never "mode"), and `_refresh_editor_menu_affordances` is that
        entry point. Neither member is gated today, and that is a considered
        decision, not an omission: a toolbar button IS the menu's own QAction, so
        hiding `Validate Project` per tab would make a DEFAULT toolbar button
        appear and disappear as the user changes tabs. Both members are also
        genuinely applicable whenever a document is open, independent of which
        tab is in front. The seam exists for the check members, whose gate (*"a
        DDL object editor tab is active"*) is a real capability predicate.
        """
        menu = self.editor_menu_bar.addMenu("Parsing")
        self._parsing_menu = menu
        # §9 Auto Parse XML: checkable, unchecked at every launch (the state is
        # in-memory only -- see the timer setup in __init__). The action IS the
        # toggle's storage; nothing else records it.
        auto_parse_action = menu.addAction("Auto Parse XML")
        auto_parse_action.setCheckable(True)
        auto_parse_action.setChecked(False)
        auto_parse_action.toggled.connect(self._on_auto_parse_toggled)
        self._auto_parse_action = auto_parse_action
        menu.addSeparator()
        validate_action = menu.addAction("Validate Project")
        validate_action.triggered.connect(self._find_ui.validate_project)
        self._validate_project_action = validate_action

    def _refresh_editor_menu_affordances(self) -> None:
        """The single "make the Editor menu bar match the active tab" entry
        point, called on every `center_stage.currentChanged` (§7, FQ-016).

        Shaped exactly like `_refresh_sandbox_affordances`: everything here binds
        **VISIBILITY, never enabled-state** — this app has deliberately kept two
        postures (present / absent) and greying out would introduce a third.

        It does two things.

        1. Hide the WHOLE bar on the tabs where all four menus are meaningless —
           **Caption Management** (a center-stage tab, not a dock, where §13
           already wanted bookmarks disabled) and **Manual**. §29 records this as
           the recommendation and it is what the visibility refresh gives for
           free. Note it hides the *bar widget*, not the actions, so a pinned
           toolbar button never blinks out with it.
        2. Hide `Select ▸ Select Parent Block` on tabs whose editor has no
           parent-block concept (FQ-015). This is the seam's first real
           **capability** gate — the kind `_build_parsing_menu`'s docstring says
           it exists for — rather than a taste-based per-tab hide: a `CodeEditor`
           (DDL Explorer, DDL object tab, PHP tab) genuinely has no "one nesting
           level up", so the honest posture is absent, not a menu entry that
           no-ops. Asking the editor itself (`hasattr`) keeps this correct for
           free when a new editor tab kind appears. Unlike case 1 this hides an
           *action*, so a user who pinned this command to the toolbar sees that
           button come and go with the tab — accepted, because the alternative is
           a toolbar button that does nothing.
        """
        stage = self.center_stage
        index = stage.currentIndex()
        hidden_on = (stage.caption_management_tab_index, stage.manual_tab_index)
        self.editor_menu_bar.setVisible(index not in hidden_on)
        editor = self._find_ui.active_selection_editor()
        self._select_parent_action.setVisible(
            hasattr(editor, "select_parent_block")
        )

    def _build_file_menu(self):
        menu = self.menuBar().addMenu("File")
        open_action = menu.addAction("Open...")
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(lambda: self._doc_ui.open_dialog())
        # FQ-010: there is deliberately NO "Open Recent" submenu (and no
        # `recentFiles` store behind it). Recent *files* belonged to the
        # standalone-`.pgtp`-editor era the project has left; a project-centric
        # app's launch-time memory is recent *projects*, which is a separate,
        # later entry. Do not reintroduce an MRU here.
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
        new_project_action.triggered.connect(lambda: self._ddl_project_ui.new_project())
        open_project_action = menu.addAction("Open Project…")
        open_project_action.triggered.connect(lambda: self._ddl_project_ui.open_project())
        # Handed over (it starts disabled and follows every project transition),
        # mirroring `CoherenceController.set_toggle_action`.
        self._ddl_project_ui.set_close_project_action(menu.addAction("Close Project"))
        project_settings_action = menu.addAction("Project Settings…")
        project_settings_action.triggered.connect(
            lambda: self._ddl_project_ui.open_settings()
        )
        deploy_pgtp_action = menu.addAction("Deploy .pgtp")
        deploy_pgtp_action.triggered.connect(lambda: self._ddl_project_ui.deploy_pgtp())
        menu.addSeparator()
        save_action = menu.addAction("Save")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_active_tab)
        save_as_action = menu.addAction("Save As...")
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(lambda: self._doc_ui.save_as())
        revert_action = menu.addAction("Revert")
        revert_action.triggered.connect(lambda: self._doc_ui.revert())
        # §7: "enabled only when `<current>.bak` exists". Handed over to the
        # document lane, which gates it here and at every point the answer can
        # change: open, save, save-as, revert, close.
        self._doc_ui.set_revert_action(revert_action)
        close_action = menu.addAction("Close")
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(lambda: self._doc_ui.close())
        self._close_action = close_action
        menu.addSeparator()
        # FQ-010: re-open the startup launcher on demand. Its "Don't show this
        # again" flag is persisted, so without this entry that tick would be a
        # one-way door only a settings edit could undo. Passes `force=True`,
        # which is exactly what makes it reversible.
        show_launcher_action = menu.addAction("Show Launcher…")
        show_launcher_action.triggered.connect(lambda: self.show_launcher())
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

    def show_launcher(self):
        """Re-open the FQ-010 startup launcher (`File ▸ Show Launcher…`).

        A USER-triggered modal, like every other dialog on the host — the
        automatic startup show lives in `main.py` after `window.show()` and is
        never reached from `__init__`, because 49 test files construct a
        MainWindow and a modal there would hang all of them. Imported lazily so
        constructing a window never pulls the launcher in.
        """
        from pgtp_editor.ui import launcher_dialog

        return launcher_dialog.show_launcher(self, self._settings, force=True)

    def _install_find_next_action(self):
        """**F3 = Find Next** — a window-level ``QAction`` with NO menu entry
        (§27, FQ-016). Owner ruling: *"why does F3 die? it should find next."*

        It survives the Edit menu's dissolution rebound onto the same shape as
        **Ctrl+L Go To XSD** (`xsd_controller.build_menu`): a window action added
        with `addAction`, routed through the exact dispatch the deleted Edit
        QAction used (`FindValidateController.find_next` ->
        `active_find_bar().find_next()`).

        **Window-level, NOT bar-local.** The whole point of F3 is that it works
        while the caret is in the EDITOR; a `keyPressEvent` on `FindReplaceBar`
        would only fire once the bar already had focus. It is window-level rather
        than per-tab (unlike Ctrl+F/Ctrl+R, see `install_focus_shortcuts`) because
        nothing else in the app binds F3, so there is no ambiguity to avoid.

        Accepted consequence: a shortcut with no menu entry is invisible to
        `_walk_menu_actions` and therefore **can never be pinned** to the toolbar
        — F3 joins the existing Ctrl+L / Ctrl+Alt+F / Ctrl+Return category,
        alongside Find itself (*"Find unpinnable is fine"*).
        """
        action = QAction("Find Next", self)
        action.setShortcut(QKeySequence("F3"))
        action.triggered.connect(self._find_ui.find_next)
        self.addAction(action)
        self._find_next_action = action

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
        # No Ctrl+F / Ctrl+R gating is needed any more (FQ-016): the Edit-menu
        # Find…/Replace… QActions this used to disable are gone with the Edit
        # menu, and their replacements are per-editor-tab focus shortcuts scoped
        # to the tab that owns each bar (`install_focus_shortcuts`). The caption
        # panel's own panel-scoped pair (FQ-017) is therefore the ONLY live match
        # while the caption grid has focus, structurally rather than by gating —
        # which is why `set_find_actions`/`set_find_actions_enabled` could be
        # deleted outright instead of re-pointed.
        # §8/§13: the Raw XML editor is read-only in Caption Mode, so the
        # Navigation menu and its four shortcuts go with it. The lane that owns
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
        # Nothing to un-gate: see `_enter_caption_mode`. Both sides' Ctrl+F /
        # Ctrl+R are focus shortcuts scoped to the surface that owns them, so each
        # goes quiet on its own when that surface is not on screen.
        self._find_ui.set_bookmarks_enabled(True)

    def _caption_go_to_line(self, line: int) -> None:
        """Caption panel Go-to-line callback: switch to the Raw XML tab (which
        stays visible but read-only in Caption Mode) and navigate to `line`."""
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)
        self.center_stage.xml_editor.navigate_to_line(line)

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
        # Handed to `_ddl_project_ui`, whose `refresh_project_dependent_actions`
        # flips its enabled state on every project transition.
        connection_setup_action = menu.addAction("Connection Setup…")
        connection_setup_action.triggered.connect(self._open_connection_setup)
        self._ddl_project_ui.set_connection_setup_action(connection_setup_action)
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
        #
        # TWO entries since §18.7/FQ-022, one per connection role. Both are
        # named: leaving this one a bare "DDL Explorer" beside an explicitly
        # sandbox-scoped sibling would make the unlabelled one ambiguous.
        # "Quality" rather than "Target" matches §18.8's node name. The rename
        # changes this command's id (`database.ddl-explorer` ->
        # `database.ddl-explorer-quality`), which is why `toolbar_registry`
        # carries a RENAMED_ID_ALIASES row for it -- a user who pinned the old
        # button keeps it.
        self._ddl_explorer_action = menu.addAction("DDL Explorer (Quality)")
        self._ddl_explorer_action.setCheckable(True)
        self._ddl_explorer_action.setChecked(False)
        self._ddl_explorer_action.toggled.connect(
            lambda checked: self._on_ddl_explorer_toggled(checked, DDL_EXPLORER_TARGET)
        )
        # §18.7's second instance. Created HIDDEN and shown by
        # `_refresh_ddl_explorer_affordances` only while the open project has a
        # sandbox configured (absent, not disabled -- carve-out 2's genuinely
        # inapplicable case). Its gate is `bool(sandbox.host)`, NOT
        # `SandboxController.has_session`: browsing is a pure READ and §18.5 D2
        # gates only writes, so this must never be wired into
        # `_refresh_sandbox_affordances`' session-keyed visibility set.
        self._sandbox_ddl_explorer_action = menu.addAction("DDL Explorer (Sandbox)")
        self._sandbox_ddl_explorer_action.setCheckable(True)
        self._sandbox_ddl_explorer_action.setChecked(False)
        self._sandbox_ddl_explorer_action.setVisible(False)
        self._sandbox_ddl_explorer_action.toggled.connect(
            lambda checked: self._on_ddl_explorer_toggled(checked, DDL_EXPLORER_SANDBOX)
        )
        #: role -> its checkable Database-menu entry (§18.7), so the lockstep
        #: handler resolves the action from the role instead of branching.
        self._ddl_explorer_actions = {
            DDL_EXPLORER_TARGET: self._ddl_explorer_action,
            DDL_EXPLORER_SANDBOX: self._sandbox_ddl_explorer_action,
        }
        menu.addSeparator()
        # FQ-002: creating a routine is not scoped to a parent object, so it
        # earns a menu entry as well as the tree's context menu. Its trigger
        # counterpart deliberately does NOT appear here -- a trigger needs a
        # specific table, which only the tree can supply.
        new_routine_action = menu.addAction("New Function/Procedure…")
        new_routine_action.triggered.connect(lambda: self._on_ddl_new_routine_requested())
        menu.addSeparator()
        menu.addSeparator()
        # §18.5 D4: ad-hoc SQL is SANDBOX-ONLY. Created HIDDEN and shown by
        # `_refresh_sandbox_console_affordances` once the open project has a
        # sandbox CONFIGURED -- absent with no sandbox, present-and-reporting
        # with one but no session (carve-out 2 as narrowed by FQ-023), never
        # disabled. There is deliberately NO "run
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
        # §18.5 D3a's Check gesture. VISIBILITY follows "is a sandbox
        # configured" and the refusal states a missing session (carve-out 2 as
        # narrowed by FQ-023 -- absent only when there is no sandbox at all),
        # and is deliberately NOT gated on
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
        # §18.5's "Deploy this edit…" picker, as a menu entry beside the two
        # check gestures (FQ-009's discoverability half). Unlike them it is
        # ALWAYS visible and needs no sandbox: its Save destination works with
        # no database at all, and when a destination is missing the picker now
        # says which and why instead of leaving a silent gap. Deliberately NO
        # shortcut -- §18.5: "an irreversible outward effect must not be one
        # keystroke away".
        self._deploy_this_edit_action = menu.addAction("Deploy This Edit…")
        self._deploy_this_edit_action.triggered.connect(
            lambda: self._deploy_active_ddl_object_edit()
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
            self._ddl_project_ui.open_settings()
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
        self._ddl_project_ui.refresh_capability_status()

    def _import_pgtp_connection_into_target(self) -> None:
        """Import the open `.pgtp`'s `<ConnectionOptions>` into the project's
        `ProjectSettings.target` (BUG-034).

        The `.pgtp` carries its design-time connection as a single
        `<ConnectionOptions host= port= login= database=/>` element; nothing
        ever copied it into the project's own settings, so Project Settings
        showed empty target fields for a project the app was quite happily
        connecting to (through `seed_params`, a competing source). Reuses
        `db/config.py::connection_from_tree` -- there is exactly one
        `<ConnectionOptions>` parser in this codebase and this is not a second
        one -- so the `login`→`user` mapping and the always-blank password come
        from the same place `seed_params` gets them.

        Runs only when a `.pgtp` is loaded while a project is active, and only
        when `.target.host` is still empty: "saved wins", the same precedence
        `seed_params` already encodes, so a host the user corrected in Project
        Settings is never silently reverted to the XML's value on reopen. The
        password is NOT imported (the XML has none) -- it is prompted for at
        first connect, see `_target_params_for_fetch`.

        The **sandbox** is deliberately not seeded from this element: §17
        defines `<ConnectionOptions>` as the *target*, and seeding a sandbox
        from it is how a sandbox ends up pointed at production.
        """
        folder = self._ddl_project_folder
        settings = self._ddl_project_settings
        if folder is None or settings is None or settings.target.host:
            return
        project = self._current_project
        imported = connection_from_tree(project.tree if project is not None else None)
        if imported is None or not imported.host:
            return
        self._store_project_target(imported)
        self.statusBar().showMessage(
            f"Imported the .pgtp's connection into the project target: "
            f"{imported.user}@{imported.host}:{imported.port}/{imported.database}",
            5000,
        )

    # -- DDL Explorer (spec §18.1) --------------------------------------------

    def _fetch_ddl_schema(self, params):
        """Introspect routines & triggers. Injectable seam — tests patch this
        to return a canned `DatabaseSchema` (mirrors
        `CoherenceController.fetch_schema`)."""
        return fetch_routines_and_triggers(params)

    def _on_ddl_explorer_toggled(self, checked, role=DDL_EXPLORER_TARGET):
        if checked:
            self._open_ddl_explorer(role)
        else:
            self.center_stage.hide_ddl_explorer(role)

    def _ddl_explorer_label(self, role) -> str:
        """What the user-facing messages call `role`'s Explorer -- the same words
        as its menu entry and its tabs, so a status line can be traced back to
        the gesture that produced it."""
        return (
            "DDL Explorer (Sandbox)"
            if role == DDL_EXPLORER_SANDBOX
            else "DDL Explorer (Quality)"
        )

    def _ddl_explorer_params(self, role):
        """The `ConnectionParams` `role`'s Explorer fetches over, or None when
        that role has no configured connection (§18.7).

        `target` goes through `_target_params_for_fetch` -- BUG-034's ONE
        selector, including its one-time password prompt -- and never through a
        private `seed_params` call, so what Project Settings shows is what the
        fetch uses.

        `sandbox` goes through `_configured_sandbox_params`, i.e. the open
        project's `ProjectSettings.sandbox` when it has a host. **PARAMS, not a
        `SandboxSession`:** §18.5 D2 gates only *writes* behind `open_sandbox`
        and says in the same breath that reads -- probing, listing, introspecting
        -- are not gated, and `DdlProjectController.refresh_capability_status`
        already probes the sandbox over a plain connection at project-open time
        with no session at all. Opening this Explorer therefore must not open a
        session, and closing a session must not close this Explorer.
        """
        if role == DDL_EXPLORER_SANDBOX:
            return self._configured_sandbox_params()
        tree = (
            self._current_project.tree
            if self._current_project is not None
            else None
        )
        return self._target_params_for_fetch(tree)

    def _open_ddl_explorer(self, role=DDL_EXPLORER_TARGET):
        """Fetch routines/triggers over `role`'s connection and reveal that
        role's DDL Explorer (center buffer tab + its own left tree tab).

        ONE code path for both instances (§18.7: "parameterized by role rather
        than duplicated"), so the sandbox tree cannot drift from the target one
        in what it fetches, how it reports failure, or how its tab is revealed.

        Standalone-mode friendly for the target role (§18): no `.pgtp` project is
        required — only a configured connection. The sandbox role is inherently
        project-scoped (a sandbox is a project's sandbox), which is why its menu
        entry is absent without one rather than refusing here.
        """
        action = self._ddl_explorer_actions.get(role)
        label = self._ddl_explorer_label(role)
        params = self._ddl_explorer_params(role)
        if params is None or not params.host:
            if action is not None:
                action.setChecked(False)
            if role == DDL_EXPLORER_SANDBOX:
                # Reachable only by a race (the entry is absent without a
                # configured sandbox), so it states the fact rather than opening
                # `_prompt_missing_connection`'s app-level Connection Setup
                # modal, which configures the TARGET and would be the wrong door.
                self.statusBar().showMessage(
                    "No sandbox configured for this project — set one up in "
                    "Project Settings.",
                    5000,
                )
                return
            self._prompt_missing_connection()
            return
        self.statusBar().showMessage(f"{label}: loading routines & triggers…")
        _log.info(
            "db: ddl explorer load started role=%s %s",
            role,
            debuglog.redacted(params),
        )

        def on_result(schema):
            text, spans = build_ddl_text(schema)
            self.center_stage.ddl_explorer_panel(role).set_ddl_text(
                text, spans, schema=schema
            )
            # */! drift markers (§18.2): recomputed fresh on every fetch, never
            # cached -- None (no markers) when no project is open, matching the
            # existing project-less rendering exactly.
            #
            # TARGET ONLY. §18.7 requires markers to be computed per source
            # connection and never borrowed from the other instance, and
            # `compute_drift_markers` compares against `ProjectSettings.deployed`
            # -- a *deployed-to-target* reference point. Handing it the sandbox's
            # introspection would render the target's question about the wrong
            # database, which is exactly the shared-computation mistake §18.7
            # forbids. The sandbox tree therefore renders unmarked until its own
            # per-connection state computation exists (§18.7's `SandboxSession
            # .applied`/`text_sha1` bookkeeping), rather than showing borrowed
            # markers that would be lies.
            drift_markers = (
                compute_drift_markers(
                    self._ddl_project_folder, self._ddl_project_settings, schema
                )
                if role == DDL_EXPLORER_TARGET
                and self._ddl_project_folder is not None
                else None
            )
            self._ddl_browser_panels[role].set_schema(
                schema, spans, drift_markers=drift_markers
            )
            self.center_stage.show_ddl_explorer(role)
            if role == DDL_EXPLORER_TARGET:
                # Schema-aware Ctrl+Space completion (§18.6): rebuild the lookup
                # index from this same fetch (now widened to also carry
                # `.tables`) and push it into every already-open DDL object tab,
                # exactly like the tree and the read-only buffer are refreshed
                # above -- built once per connect/refresh, never per keystroke.
                #
                # TARGET ONLY, for the same reason the markers are: an open
                # object tab's completions (and FQ-002's trigger-function
                # candidate list) describe the lane the edit will be applied to,
                # and a sandbox browse must not silently repoint them at a
                # different database's object set.
                self._ddl_schema_index = SchemaIndex(schema)
                # Kept alongside the index because FQ-002's creation dialogs need
                # the raw schema (the trigger-function candidate list), and the
                # index exposes only its own query surface.
                self._ddl_schema = schema
                for panel in self.center_stage.ddl_object_panels():
                    panel.set_schema_index(self._ddl_schema_index)
            self.statusBar().showMessage(
                f"{label}: {len(schema.routines)} routine(s), "
                f"{len(schema.triggers)} trigger(s).",
                5000,
            )
            _log.info("db: ddl explorer load finished role=%s", role)

        def on_error(exc):
            # The never-raises posture both fetch paths already have: an
            # unreachable database (a sandbox that was destroyed, a host that is
            # down) is REPORTED and the toggle springs back, so the menu entry
            # never lands the user on an empty tree that looks like an empty
            # database.
            _log.info("db: ddl explorer load failed role=%s %s", role, exc)
            self.statusBar().showMessage(f"{label} failed: {exc}", 8000)
            if action is not None:
                action.setChecked(False)

        self._run_async(
            lambda: self._fetch_ddl_schema(params),
            on_result=on_result,
            on_error=on_error,
        )

    def _on_ddl_explorer_visibility_changed(self, role, visible):
        """Keep `role`'s left tree tab and its Database-menu toggle in lockstep
        with its center tab (Contents-rides-with-Manual pattern; bidirectional
        per BUG-007 — the tab has its own ✕).

        Role-parameterized rather than duplicated (§18.7): the two instances are
        independent, so this runs once per role and never touches the other's
        tab.
        """
        self.left_tabs.setTabVisible(self._ddl_browser_tab_indexes[role], visible)
        if visible:
            self.tree_dock.setVisible(True)
            self.left_tabs.setCurrentWidget(self._ddl_browser_panels[role])
        action = self._ddl_explorer_actions.get(role)
        if action is not None:
            action.setChecked(visible)

    def _refresh_ddl_explorer_affordances(self) -> None:
        """Make the sandbox Explorer's presence follow whether the open project
        has a sandbox CONFIGURED (§18.7) -- called on every project transition.

        VISIBILITY, never enabled-state: with no sandbox the entry is ABSENT
        (carve-out 2's genuinely-inapplicable case, which §18.7 names as the one
        place FQ-023's narrowing does not apply).

        The gate is `bool(sandbox.host)` via `_configured_sandbox_params`, NOT
        `SandboxController.has_session` -- see `_ddl_explorer_params`. It
        deliberately lives here rather than in `_refresh_sandbox_affordances`,
        which is the session-keyed refresh: putting it there is the instinctive
        move and would re-introduce exactly the coupling §18.7 forbids.

        If the sandbox went away while its tree was open (a project closed, or a
        different project opened), the tab is hidden with the entry rather than
        left showing a previous project's sandbox -- the same reason
        `_refresh_sandbox_console_affordances` closes an orphaned console.
        """
        available = self._configured_sandbox_params() is not None
        action = self._ddl_explorer_actions.get(DDL_EXPLORER_SANDBOX)
        if action is not None:
            action.setVisible(available)
        if not available and self.center_stage.isTabVisible(
            self.center_stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX)
        ):
            self.center_stage.hide_ddl_explorer(DDL_EXPLORER_SANDBOX)

    def _on_ddl_navigate_requested(self, line, role=DDL_EXPLORER_TARGET):
        """Leaf click in a DDL Objects tree → jump that role's DDL buffer tab to
        the object's banner line (two tree leaves may share one span, §18.1).

        Each tree navigates its OWN buffer: the sandbox tree's line numbers are
        offsets into the sandbox's synthesized text, which the target buffer's
        object set does not share (§18.7's divergence rule).
        """
        stage = self.center_stage
        stage.setCurrentIndex(stage.ddl_explorer_tab_index(role))
        stage.ddl_explorer_panel(role).navigate_to_line(line)

    def _on_ddl_table_selected(self, table_info) -> None:
        """Click on a Tables-branch table node (spec §18.1, 2026-08-05) --
        populates the shared Properties panel, mirroring how the XML/XSD
        tree's own selection handler (`_on_tree_selection_changed`) calls
        `show_node` for its four kinds. Click-only, no navigation target:
        `PropertiesPanel` rows built from a `TableInfo` all carry
        `target_line=None`."""
        self.properties_panel.show_node(table_info, "ddl_table")

    def _on_ddl_edit_requested(self, ref, source):
        """Right-click ▸ Edit DDL, from either entry point (§18.5 D1) -- the
        ONE editing gesture, whose behaviour comes from PROJECT STATE and never
        from which words the user clicked (FQ-024, §18.1).

        With a project open the object is checked out (§18.2) and the tab is
        pointed at its `ddl/*.sql`; projectless the tab holds the live
        introspected definition and saves through Save As…. Deliberately NO
        `require_project` prompt on the projectless side: with one entry that
        Create…/Open…/Cancel modal would fire on every edit, and projectless is
        a first-class supported mode (§18.2).

        Creation (FQ-002) does NOT come through here -- it calls
        `_edit_ddl_live` directly, see `_open_created_ddl_object`.
        """
        if self._ddl_project_folder is not None and self._ddl_project_settings is not None:
            self._edit_ddl_checked_out(ref, source)
            return
        self._edit_ddl_live(ref, source)

    def _edit_ddl_live(self, ref, source):
        """The projectless branch of `Edit DDL`, and the branch *creation*
        always takes: the tab holds `source` as handed in (the live introspected
        definition, or FQ-002's generated skeleton) and Save resolves through
        Save As… on first save.

        Writes no `ddl/*.sql` and touches no deploy manifest -- which is why
        creation selects this branch explicitly rather than falling through the
        project test (§18.1/FQ-024): seeding a checked-out file from a skeleton
        and registering it as deployed would poison the drift baseline for an
        object no database has ever held.
        """
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
        self._wire_ddl_object_dirty(panel, ref)
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

    def active_target_params(self, tree=None):
        """**The** target connection, for every consumer (BUG-034).

        One selector, BUG-024's rule: with a §18.2 project open its own
        `ProjectSettings.target` profile is authoritative -- blank or not --
        and projectless the app-level saved connection (merged with the open
        `.pgtp`'s `<ConnectionOptions>` by `seed_params`) is.

        Before BUG-034 this rule was implemented HERE for the §18.8 Project
        Status window only, while the two gestures that actually open a
        connection (`_open_ddl_explorer`, `CoherenceController.run_check`)
        each called `seed_params` on their own. That is precisely how the app
        could connect with one set of credentials while Project Settings
        displayed another (or nothing): the dialog owned neither the
        population nor the live use of `.target`. Every consumer now asks
        here, so the Quality node, the reachability probe, the DDL Explorer
        fetch and the coherence fetch cannot diverge.

        `tree` is the open `.pgtp`'s XML tree, used only in the projectless
        branch (a project's target is not seeded from XML at call time -- it
        was imported into `settings.json` once, see
        `_import_pgtp_connection_into_target`). Public because the coherence
        lane is injected with it as a seam.

        Never None: an unconfigured target is a host-less `ConnectionParams`,
        which `_target_is_configured` and every `if not params.host` guard
        already read as "not configured".
        """
        settings = self._ddl_project_settings
        if settings is not None:
            return settings.target
        return seed_params(tree, self._settings)

    def _project_status_target(self):
        """The target the §18.8 Quality node speaks for -- `active_target_params`
        with no `.pgtp` tree, kept as its own name because Project Status is a
        passive reader that must never trigger BUG-034's password prompt."""
        return self.active_target_params()

    def _target_params_for_fetch(self, tree=None):
        """`active_target_params`, plus the one-time password prompt (BUG-034).

        The `.pgtp` deliberately never yields a usable password
        (`connection_from_tree` forces `""` -- §17: the password is never read
        from the XML), so an imported target arrives password-less. The prompt
        is raised HERE, at the first gesture that actually needs to connect,
        rather than at project-open time: opening a project must not raise a
        modal, and a project the user never connects from must never ask for a
        secret. Answered once -- the password is persisted into
        `settings.json` (plaintext, as `target`/`sandbox` already are, §18.2)
        so later gestures go straight through.

        Cancelling leaves the password blank and returns the params anyway:
        the connection will fail and be reported the ordinary way, which is
        better than silently substituting some other stored credential --
        exactly the confusion this bug was about.
        """
        params = self.active_target_params(tree)
        if self._ddl_project_settings is None or not params.host or params.password:
            return params
        password = self._prompt_target_password(params)
        if not password:
            return params
        params = replace(params, password=password)
        self._store_project_target(params)
        return params

    def _prompt_target_password(self, params) -> str | None:
        """Ask for the project target's password once (BUG-034). Returns the
        typed text, or None if cancelled.

        Its own method for the same reason `_confirm_close_ddl_object` is:
        tests monkeypatch THIS instead of ever driving a real modal. Routed
        through `modals` so the patch target survives further decomposition.
        """
        text, ok = modals.QInputDialog.getText(
            self,
            "Database Password",
            f"Password for {params.user}@{params.host}:{params.port}/{params.database}:",
            QLineEdit.EchoMode.Password,
        )
        return text if ok else None

    def _store_project_target(self, params) -> None:
        """Persist `params` as the project's target profile (BUG-034) -- the
        one store Project Settings displays and every gesture now reads."""
        settings = self._ddl_project_settings
        if settings is None or self._ddl_project_folder is None:
            return
        updated = replace(settings, target=params)
        save_settings(self._ddl_project_folder, updated)
        self._ddl_project_settings = updated

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
            probe_error=self._ddl_project_ui.target_probe_error,
        )
        schema_fact, data_fact = self._project_status_sandbox_facts()
        return build_diagram(
            status=self._ddl_project_ui.capability_status,
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
            self._ddl_project_ui.refresh_capability_status()
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
            self._ddl_project_ui.refresh_capability_status()
            # BUG-035: Sandbox1's facts are re-inspected on the same trigger as
            # everything else the window shows, so "opening the window is a
            # fresh probe" (§18.8) holds for the node's contents too.
            self._refresh_sandbox_provisioning_status()
            return self._build_project_status_diagram()

        # Sandbox1's "run data clone" and Sandbox2's "install plpgsql_check" are
        # wired by `_refresh_project_status_sandbox_actions` immediately below --
        # constructed as `None` here on purpose, so that ONE method decides which
        # state earns a button and what it does. Deciding it twice is how the
        # freshly-built window and the re-shown one drift apart (this window is
        # cached and re-shown, not rebuilt).
        settings = self._ddl_project_settings
        panel = ProjectStatusPanel(
            diagram=self._build_project_status_diagram(),
            on_refresh=on_refresh,
            on_reconnect_quality=on_refresh,
            on_run_data_clone=None,
            on_install_plpgsql_check=None,
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
        self._refresh_project_status_sandbox_actions()
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

        Deliberately routed through `_edit_ddl_live`, the projectless branch of
        `Edit DDL`: the tab, its save-path resolver, its completion index and
        its dirty bookkeeping are identical whether the text came from
        introspection or from a skeleton. The only thing creation does
        differently is build the `DdlObjectRef` from dialog fields rather than
        `resolve_edit_target`, which correctly returns None for an object that
        does not exist yet.

        It calls that branch DIRECTLY, not `_on_ddl_edit_requested`, so a
        project being open cannot divert creation into the checkout branch
        (FQ-024): checkout would seed `ddl/<obj>.sql` from the SKELETON and hash
        it as the last-deployed reference, claiming a never-created object is
        deployed. Creation's own manifest entry is `_register_created_object`'s
        empty-`content_hash` sentinel -- "local exists, never deployed" -- and
        the two must not be confused.
        """
        ref = self._ref_for_created_object(dialog)
        if ref is None:
            return
        self._edit_ddl_live(ref, dialog.skeleton())
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

    def _edit_ddl_checked_out(self, ref, source) -> None:
        """The project-open branch of `Edit DDL` (§18.2's checkout, FQ-024).

        The checkout semantics live only here -- seed the `ddl/*.sql` from the
        live definition when it is absent (that write IS the checkout), open it
        from disk when it is present, report drift, register the last-deployed
        reference -- and the tab's save destination becomes that file.

        The tab is keyed on `ref.key`, exactly as the projectless branch keys it
        (FQ-024). It used to key on `str(ddl_path)`, a second namespace neither
        branch's existence check consulted, so Check-Out-then-Edit on one object
        opened TWO identically-titled tabs writing to two different files.
        """
        schema = getattr(self.ddl_browser_panel, "_schema", None)
        relpath = self._ddl_checkout_relpath(ref, schema)
        ddl_path = (self._ddl_project_folder / relpath).resolve()

        existing = self.center_stage.ddl_object_tab(ref.key)
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
        # Registered AFTER the drift report, which must see the PREVIOUS
        # last-deployed reference (or its absence), never the one written here.
        self._register_checked_out_object(relpath, source)

        def resolver():
            return ddl_path

        panel = self.center_stage.open_ddl_object_tab(
            ref, text, resolve_save_path=resolver
        )
        panel.set_schema_index(self._ddl_schema_index)
        self._wire_ddl_object_dirty(panel, ref)
        panel.format_refused.connect(self._report_ddl_format_refusal)
        self._wire_ddl_object_panel_reporting(panel, ref)

    def _register_checked_out_object(self, relpath, live_source) -> None:
        """Give a freshly checked-out object its last-deployed reference
        (BUG-033, the cause behind the inert `*`).

        `compute_drift_markers` iterates `ProjectSettings.deployed` ALONE, so an
        object with no entry there gets no markers at all -- no `*` however
        many times the tree is refreshed. Creation (FQ-002,
        `_register_created_object`) already registers its objects; checkout
        wrote the `ddl/*.sql` and registered nothing, which is why editing a
        checked-out function could never light the marker up.

        The reference recorded is the hash of the **live definition the
        checkout was taken from** -- not FQ-002's empty-string never-deployed
        sentinel. The two cases are genuinely different: a created object has
        never been deployed, so `""` correctly makes it read as `*` from birth,
        whereas a checked-out object's live definition IS what is deployed
        right now, so hashing it makes a fresh checkout read as *unmodified*
        (no `*`) and start showing `*` only once the user actually edits and
        saves the file. Using the sentinel here would flag every checkout as
        locally edited the instant it happened.

        Never overwrites an existing entry: a real deploy's reference outranks
        this inference, and a re-checkout must not silently re-baseline drift.
        """
        settings = self._ddl_project_settings
        if self._ddl_project_folder is None or settings is None:
            return
        if relpath in settings.deployed:
            return
        settings.deployed[relpath] = DeployedObject(content_hash=content_hash(live_source))
        save_settings(self._ddl_project_folder, settings)

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
        # BUG-033: the tab is clean again, so the tree's unsaved-edit overlay
        # must go -- and the file on disk has just changed, so the §18.2
        # file-vs-last-deployed `*` must be recomputed. Without both, the
        # marker the user looks for appeared only after a manual DDL Explorer
        # refresh. `mark_clean` does not re-emit `dirty_changed` for an
        # already-clean document, so the overlay is dropped explicitly.
        self.ddl_browser_panel.set_object_dirty(panel.ref, False)
        self._refresh_ddl_drift_markers()
        self.statusBar().showMessage(f"Saved {path}", 5000)
        return True

    def _wire_ddl_object_dirty(self, panel, ref) -> None:
        """The one place an editable DDL tab's dirty state is published
        (BUG-033).

        Two consumers, one wire: the CenterStage tab title's `" *"` (§18.5)
        and -- new -- the DDL Objects tree row's `*` overlay (§18.1/§18.2),
        which previously had no channel to hear about an unsaved edit at all.
        Called from BOTH `Edit DDL` branches (`_edit_ddl_live` and
        `_edit_ddl_checked_out`) so the two can never again wire different sets
        of consumers. No `key` parameter since FQ-024: both branches key the tab
        on `ref.key`, so there is nothing left to override.
        """

        def on_dirty(dirty, ref=ref):
            self.center_stage.update_ddl_object_tab(ref)
            self.ddl_browser_panel.set_object_dirty(ref, dirty)

        panel.dirty_changed.connect(on_dirty)

    def _refresh_ddl_drift_markers(self) -> None:
        """Recompute §18.2's `*`/`!` markers and repaint the DDL Objects tree
        against the schema it is already showing (BUG-033 layer b).

        Reuses the exact fetch-path plumbing -- `compute_drift_markers` +
        `BrowserPanel.set_schema` -- rather than a parallel refresh, and
        re-derives `spans` from the retained schema with the same pure
        `build_ddl_text` the fetch used, so no second span source exists. No
        DB round trip: this is a re-read of local `ddl/*.sql` files plus the
        schema already in hand. No-op when the Explorer has never been loaded
        (nothing to repaint); projectless it repaints with no markers, which
        is what keeps the unsaved-edit overlay working with no project open.
        """
        schema = getattr(self.ddl_browser_panel, "_schema", None)
        if schema is None:
            return
        drift_markers = (
            compute_drift_markers(self._ddl_project_folder, self._ddl_project_settings, schema)
            if self._ddl_project_folder is not None and self._ddl_project_settings is not None
            else None
        )
        _text, spans = build_ddl_text(schema)
        self.ddl_browser_panel.set_schema(schema, spans, drift_markers=drift_markers)

    def _confirm_close_ddl_object(self, ref) -> str:
        """Ask the user how to resolve unsaved changes in a DDL object tab
        before closing. Returns "save", "discard", or "cancel" (mirrors
        `PgtpDocumentController.confirm_close` and `XsdController.confirm_close`,
        so tests can monkeypatch this instead of ever driving a real modal)."""
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
        # BUG-033: a DISCARDED edit must drop the tree's unsaved-edit `*` too
        # -- there is no longer an open tab holding changes for this object.
        # (A saved one was already cleared by `_save_ddl_object_editor`.)
        ref = panel.ref
        self.center_stage.close_ddl_object_tab(key)
        self.ddl_browser_panel.set_object_dirty(ref, False)

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

        Resolved by **`panel.ref.key` identity** over the open panels. Since
        FQ-024 that is the tab key too, so a `ddl_object_tab(key)` lookup would
        now find the same panel -- the scan is kept because it additionally
        type-filters to per-object panels (`ddl_object_panels`), which the
        shared tab map does not.

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

        No console TAB and no bridge button exists without one (§18.5 D4's
        safety boundary / carve-out 2), so this is what every object tab's
        bridge seam, the open-console teardown and the command itself are gated
        on. It is NOT the menu entry's visibility gate any more (FQ-023): the
        entry follows whether a sandbox is configured and reports this."""
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
        console at all.

        Since FQ-023 the entry is present whenever a sandbox is configured, so
        this refusal is a reachable, ordinary outcome rather than a
        can't-happen guard -- it states the missing session and offers to open
        one (`_refuse_sandbox_gesture`), and still creates no console."""
        if not self._sandbox_console_available():
            self._refuse_sandbox_gesture("Sandbox SQL Console…")
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
        CLOSES it, rather than leaving a console that refuses every Run.

        **Two different predicates, deliberately** (FQ-023). The MENU ENTRY
        follows *"is a sandbox configured"*: with one configured but no session
        it is present and states why it cannot open a console. Everything that
        would leave a surface refusing every Run still follows the SESSION --
        the open console tab is closed when the session dies, and the object
        tabs' bridge buttons are unwired -- because a button, unlike a menu
        entry, cannot state a reason (§18.5 D4's rule survives verbatim)."""
        available = self._sandbox_console_available()
        if self._sandbox_console_action is not None:
            self._sandbox_console_action.setVisible(
                available or self._configured_sandbox_params() is not None
            )
        seam = self._run_selection_in_sandbox_console if available else None
        for panel in self.center_stage.ddl_object_panels():
            panel.set_run_in_console(seam)
        if not available and self.center_stage.sandbox_sql_tab() is not None:
            self.center_stage.close_sandbox_sql_tab()

    def _wire_ddl_object_panel_reporting(self, panel, ref) -> None:
        """Connect a freshly opened DDL object tab's §18.5 reporting channels,
        its D4 console bridge and its sandbox apply seams. Shared by both
        `Edit DDL` branches (`_edit_ddl_live` and `_edit_ddl_checked_out`) so
        the two can never drift apart."""
        panel.check_reported.connect(self._report_check_lines)
        panel.check_findings.connect(
            lambda findings, ref=ref: self._report_check_findings(findings, ref)
        )
        # "Deploy this edit…" ▸ Save delegates outward rather than saving itself
        # (§18.5: the picker is "a picker in front of the three gestures, not a
        # fourth thing that writes DDL or files on its own"). Without this
        # connection that destination was a SILENT NO-OP -- the picker returned
        # "save" and nothing was written. Found while making the picker
        # discoverable (FQ-009), which is exactly the kind of dead path a buried
        # affordance hides.
        panel.save_requested.connect(
            lambda panel=panel: self._save_ddl_object_editor(panel)
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
        2, as NARROWED by FQ-023): the two Check gestures are ABSENT while no
        sandbox is CONFIGURED -- genuinely inapplicable -- and PRESENT while one
        is, whether or not a session is open. Present without a session they
        REPORT (`_refuse_sandbox_gesture`), because absence cannot state a
        reason and the reason here is one click away from being fixed. They are
        never greyed out, which would state even less than the refusal."""
        controller = self.sandbox_controller
        has_session = controller.has_session
        # The presence predicate for the two Checks: `can_check` covers the live
        # session, `_configured_sandbox_params()` the FQ-023 present-and-
        # reporting case. Same "a host is set" reading as §18.7's Explorer gate,
        # so the two affordance sets cannot disagree about what "configured"
        # means -- while `can_check` stays the sole authority on whether a run
        # can actually happen.
        check_present = (
            controller.can_check or self._configured_sandbox_params() is not None
        )
        if self._sandbox_check_action is not None:
            self._sandbox_check_action.setVisible(check_present)
        if self._sandbox_probe_check_action is not None:
            # The probe is the same ladder against the same session, so it earns
            # exactly the same gate -- one predicate, never a second reading of
            # "is there a session?".
            self._sandbox_probe_check_action.setVisible(check_present)
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
        """Keep §18.8's two sandbox node actions (Sandbox1's "run data clone",
        Sandbox2's "install plpgsql_check") wired to the controller's
        zero-argument adapters.

        Both operations go through the live `SandboxSession`, but the presence
        predicate is *"is a sandbox configured"*, not `has_session` (§18.8 under
        carve-out 2's FQ-023 narrowing): with no sandbox at all the panel still
        gets `None`, which it renders as no button, and with a sandbox but no
        session the button is there and the wrapper STATES why it cannot run,
        offering `Open Sandbox Session` as an explicit click.

        The session is re-read inside the wrapper rather than captured here: the
        node windows are built on activation, and a session can come or go
        between this refresh and the click.

        The destructive one keeps the controller's own `confirm_destructive`
        gate: `on_run_data_clone` -> `run_data_clone` -> `_confirmed(CLONE_DATA)`
        -> `_confirm_destructive_sandbox_operation`, so the warning text is the
        controller's and no second dialog is opened here.
        """
        window = self._project_status_window
        if window is None:
            return
        controller = self.sandbox_controller
        if self._configured_sandbox_params() is None:
            window.set_sandbox_actions(
                on_run_data_clone=None, on_install_plpgsql_check=None
            )
            return

        def gated(operation, gesture):
            def run() -> None:
                if not controller.has_session:
                    self._refuse_sandbox_gesture(gesture)
                    return
                operation()

            return run

        window.set_sandbox_actions(
            on_run_data_clone=gated(
                controller.on_run_data_clone, "Run the data clone"
            ),
            on_install_plpgsql_check=gated(
                controller.on_install_plpgsql_check, "Install plpgsql_check"
            ),
        )

    def _refuse_sandbox_gesture(self, gesture: str) -> bool:
        """State why `gesture` cannot run right now and, when the only thing
        missing is a session, OFFER to open one as an explicit click. Returns
        True when the user took that offer.

        The one refusal every session-gated sandbox gesture shares (FQ-023,
        carve-out 2's narrowing) -- the two Check gestures, the Sandbox SQL
        Console and §18.8's two node buttons -- so they cannot drift into three
        vocabularies for one fact. The sentence itself is the destination
        picker's (`DESTINATION_UNAVAILABLE_REASONS[DEST_SANDBOX]`, FQ-009), which
        already names `Database ▸ Open Sandbox Session` as the fix; it is
        deliberately reused rather than re-typed here.

        **No connection is attempted without a click whose label says a session
        will be opened** (the owner's line: a session opening as a side effect of
        another gesture is what is forbidden, not one opening because the user
        asked). Hence the `Open` button, immediately under the sentence that says
        what it opens -- and hence nothing is retried afterwards: `open_session`
        is asynchronous and reports through the Audit panel, so the gesture is
        the user's to re-invoke once the session is up rather than something that
        fires later out of nowhere.
        """
        if self._configured_sandbox_params() is None:
            # Not one click away: there is nothing to open a session ON. This is
            # carve-out 2's ABSENT case, so the gesture is normally not even
            # reachable -- but a toolbar button or a shortcut can still arrive
            # here, and an unexplained no-op is what FQ-023 exists to kill.
            self.statusBar().showMessage(
                f"{gesture} needs a sandbox — none is configured for this "
                "project; set one up in Project Settings.",
                5000,
            )
            return False
        reason = DESTINATION_UNAVAILABLE_REASONS[DEST_SANDBOX]
        answer = modals.QMessageBox.question(
            self,
            "No Sandbox Session",
            f"{gesture} needs a live sandbox session: {reason}.\n\n"
            "Open a sandbox session now? Nothing connects until you choose "
            "Open.",
            modals.QMessageBox.StandardButton.Open
            | modals.QMessageBox.StandardButton.Cancel,
        )
        if answer != modals.QMessageBox.StandardButton.Open:
            # Declining still leaves the reason on screen: the user asked a
            # question ("why can't I check?") and it must stay answered after the
            # dialog is gone.
            self.statusBar().showMessage(f"{gesture} — {reason}.", 5000)
            return False
        self._open_sandbox_session()
        self.statusBar().showMessage(
            f"Opening a sandbox session — the outcome is reported in the Audit "
            f"panel; re-run {gesture} once it is open.",
            5000,
        )
        return True

    def _configured_sandbox_params(self):
        """The open project's sandbox `ConnectionParams`, or None when there is
        no project or its sandbox has no host -- the same "configured means a
        host is set" reading `DdlProjectController.refresh_capability_status`
        uses, so the two can never disagree about whether a sandbox exists."""
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
        # §18.7's second Explorer follows the PROJECT (does this project have a
        # sandbox configured?), not the session — so it is refreshed here, at the
        # project-transition entry point, and deliberately not inside
        # `_refresh_sandbox_affordances`, which answers the session question.
        self._refresh_ddl_explorer_affordances()

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
        # §18.7's "or a sandbox added later via Sandbox Setup…" case: a project
        # that had no sandbox now has one, and this is the one transition that
        # does NOT go through `_bind_sandbox_controller_to_project` (see above),
        # so the second Explorer's entry would otherwise stay absent until the
        # next project transition.
        self._refresh_ddl_explorer_affordances()

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

        **FQ-009 deliberately did NOT wire Apply to Target ("run on quality"),
        and this is where that decision lives.** Three separate reasons, none of
        them "the user might be careless":

        1. *The identity seam has no source yet.* `live_identity` needs the
           project's target `ConnectionParams`, and the only place that holds
           them is `SandboxController.target_params` — fed from
           `ProjectSettings.target`, which **BUG-034** says is never populated
           from the `.pgtp` file. Wiring against it today would either offer a
           gesture that cannot resolve a database, or hard-code a second,
           parallel target-resolution path in exactly the file BUG-034 is
           rewriting. When BUG-034 lands, `sandbox_controller.target_params` is
           the one provider to read; nothing else here needs to change.
        2. *Reachability is not yet a fact.* **BUG-030**'s quality-node status
           is "configured", not probed, so "there is a target" is currently an
           unverified claim.
        3. *The asymmetry that makes this different from the sandbox.* Apply to
           Sandbox is undoable (Reset Sandbox) and the sandbox is disposable;
           Apply to Target has **no revert snapshot**. §18.5 precondition 2's
           override is by design reachable with *nothing* verified (an
           un-checked buffer reports as "the ladder has not been run over this
           buffer", which is overridable — see
           `DdlObjectEditorPanel._precondition_validation`), so wiring this leg
           puts an irreversible production write two clicks and one override
           behind a context menu. That may well be the right end state, but it
           is a posture change worth landing on purpose, with the target
           resolution it depends on already trustworthy — not as a side effect
           of a discoverability fix.

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

    def _deploy_active_ddl_object_edit(self) -> str | None:
        """Database ▸ Deploy This Edit… -- §18.5's destination picker run over
        the ACTIVE object tab (FQ-009's discoverability half).

        Adds no gesture and no write path of its own: it calls the panel's
        `deploy_this_edit()`, which delegates to Apply to Sandbox / the host's
        Save / Apply to Target and runs each one's full gate. Returns the chosen
        destination (or None) so a test can assert the delegation without
        reading the panel back."""
        panel = self.center_stage.active_ddl_object_panel()
        if panel is None:
            self.statusBar().showMessage(
                "Deploy This Edit runs on an open DDL object tab — open one first.",
                5000,
            )
            return None
        return panel.deploy_this_edit()

    def _run_ladder_on_active_ddl_object(self, *, probe: bool) -> None:
        """The shared body of the two Database-menu check gestures. Exactly one
        object per run (D3a): there is no implicit multi-object sweep.

        The `CheckRequest` is built HERE, not in the controller, because a
        trigger's referenced function is knowledge the ref alone does not carry
        and the controller must not guess it. When it cannot be supplied, the
        request goes out without it and `db/ddl_check.py` reports its own
        "which function does this trigger call?" outcome -- an unavailable tier
        is a reported fact, never a silent no-op.

        The missing-session refusal comes FIRST, before the "no tab" one: since
        FQ-023 both gestures are present whenever a sandbox is configured, so
        the session is the precondition their new presence is advertising --
        answering with "open a DDL object tab" would send a user who has one
        prerequisite missing off to fix a different one.
        """
        gesture = (
            "Check Object Without Applying" if probe else "Check Object in Sandbox"
        )
        if not self.sandbox_controller.can_check:
            self._refuse_sandbox_gesture(gesture)
            return
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
        # FQ-017: "Caption Filter…" is gone. It opened a modal that duplicated
        # the Caption Management tab's own — now permanently visible —
        # Find/Replace bar, which is the single surface for caption
        # find/filter/replace.
        menu.addSeparator()
        # `Validate Project` MOVED to the Editor bar's Parsing menu (FQ-016) --
        # it is the owner's "validate xml". Its command id changed with it, so
        # `LEGACY_ID_ALIASES` was updated in the same commit (it is one of the
        # default toolbar buttons).
        #
        # §22 PHP lint stays HERE, with `Lint on Save` and `Locate PHP Linter…`:
        # whether all three follow Validate onto Parsing is an open item (§29),
        # and moving only `Lint Current File` would split lint across two bars.
        # All three feed the one Audit panel -- `[Lint]`, never `[Validate]`'s or
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
        reparse_action.triggered.connect(self._doc_ui.reparse)
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
