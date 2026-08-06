# tests/ui/test_ddl_explorer_wiring.py
"""MainWindow wiring for the DDL Explorer (spec §18.1): the Database-menu
toggle, _open_ddl_explorer's fetch → populate → reveal path, the left "DDL
Objects" tab / menu-checkbox lockstep (bidirectional, BUG-007 lesson), and
the BrowserPanel → EditorPanel navigation jump.

No live DB (patched `_fetch_ddl_schema` seam, mirroring `_fetch_db_schema` in
test_db_check_wiring.py) and no modal calls (the Connection Setup dialog is
shown non-modally)."""
from lxml import etree
from PySide6.QtCore import QSettings

from pgtp_editor.db.config import ConnectionParams, save_connection
from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, RoutineInfo, TableInfo, TriggerInfo
from pgtp_editor.ui.main_window import MainWindow

from ._menu_helpers import action_labels, find_action, find_top_menu


class _FakeProject:
    def __init__(self, tree):
        self.tree = tree


def _project_with_connection():
    tree = etree.ElementTree(
        etree.fromstring(
            b'<Project><ConnectionOptions host="h" port="5432" login="u" '
            b'database="d"/></Project>'
        )
    )
    return _FakeProject(tree)


def _schema():
    routines = {
        "pr.calc_total(integer)": RoutineInfo(
            schema="pr", name="calc_total", arg_types=["integer"],
            return_type="numeric", language="plpgsql",
            source="CREATE FUNCTION pr.calc_total(a integer) ...", kind="function",
        ),
        "pr.audit_log()": RoutineInfo(
            schema="pr", name="audit_log", arg_types=[], return_type="trigger",
            language="plpgsql", source="CREATE FUNCTION pr.audit_log() ...",
            kind="function",
        ),
    }
    triggers = {
        "pr.equipment.trg_audit": TriggerInfo(
            schema="pr", table="equipment", name="trg_audit", timing="after",
            events=["insert"], function_name="audit_log",
            definition="CREATE TRIGGER trg_audit ...",
        ),
    }
    tables = {
        "pr.equipment": TableInfo(
            name="pr.equipment", kind="table",
            columns=[
                ColumnInfo(
                    name="id", data_type="integer", is_pk=True, is_fk=False,
                    is_nullable=False, default=None,
                ),
            ],
        ),
    }
    return DatabaseSchema(routines=routines, triggers=triggers, tables=tables)


def _sync_run(fn, on_result, on_error=None):
    """Synchronous stand-in for run_async (same seam style as
    test_db_check_wiring.py)."""
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001
        (on_error or (lambda _e: None))(exc)


def _empty_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def _window(qtbot, tmp_path, with_project=True):
    window = MainWindow(settings=_empty_settings(tmp_path))
    qtbot.addWidget(window)
    if with_project:
        window._current_project = _project_with_connection()
    window._fetch_ddl_schema = lambda params: _schema()
    window._run_async = _sync_run
    return window


# ---------------------------------------------------------------------------
# Database menu.
# ---------------------------------------------------------------------------

def test_database_menu_has_checkable_ddl_explorer_after_separator(qtbot, tmp_path):
    window = MainWindow(settings=_empty_settings(tmp_path))
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Database")
    action = find_action(menu, "DDL Explorer")
    assert action is not None
    assert action.isCheckable() is True
    assert action.isChecked() is False
    labels = action_labels(menu)
    assert labels[labels.index("DDL Explorer") - 1] == "―"  # after a separator


# ---------------------------------------------------------------------------
# Toggle on: fetch → populate → reveal.
# ---------------------------------------------------------------------------

def test_toggle_on_populates_editor_and_browser_and_reveals_both_tabs(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window._ddl_explorer_action.setChecked(True)

    # Center: the synthesized buffer landed in the sql EditorPanel and the
    # DDL Explorer tab is revealed + current.
    text = window.center_stage.ddl_editor_panel.editor.toPlainText()
    assert "-- FUNCTION pr.calc_total(integer) --" in text
    assert "-- TRIGGER pr.trg_audit ON equipment --" in text
    assert window.center_stage.isTabVisible(window.center_stage.ddl_tab_index)
    assert window.center_stage.currentIndex() == window.center_stage.ddl_tab_index
    # Left: the DDL Objects tree is populated, revealed and current.
    assert window.ddl_browser_panel.tree.topLevelItemCount() == 2
    assert window.left_tabs.isTabVisible(window.ddl_browser_tab_index)
    assert window.left_tabs.currentWidget() is window.ddl_browser_panel
    # Menu toggle stays checked; status reports the counts.
    assert window._ddl_explorer_action.isChecked() is True
    assert "2 routine(s)" in window.statusBar().currentMessage()
    assert "1 trigger(s)" in window.statusBar().currentMessage()


def test_open_works_standalone_without_a_project(qtbot, tmp_path):
    """Standalone mode (§18): no .pgtp loaded -- the connection comes from the
    saved settings alone."""
    settings = _empty_settings(tmp_path)
    save_connection(settings, ConnectionParams(
        host="sh", port="5432", database="sd", user="su", password="sp"
    ))
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert window._current_project is None
    window._fetch_ddl_schema = lambda params: _schema()
    window._run_async = _sync_run

    window._ddl_explorer_action.setChecked(True)

    assert window.center_stage.isTabVisible(window.center_stage.ddl_tab_index)
    assert window.center_stage.ddl_editor_panel.editor.toPlainText() != ""


def test_toggle_on_without_connection_unchecks_and_opens_setup(qtbot, tmp_path):
    window = _window(qtbot, tmp_path, with_project=False)  # no project, empty settings
    fetches = []
    window._fetch_ddl_schema = lambda params: fetches.append(1) or _schema()

    window._ddl_explorer_action.setChecked(True)

    assert "No database connection configured" in window.statusBar().currentMessage()
    assert window._ddl_explorer_action.isChecked() is False  # rolled back
    assert window._connection_dialog is not None  # Connection Setup opened
    assert fetches == []  # never tried to fetch
    assert not window.center_stage.isTabVisible(window.center_stage.ddl_tab_index)
    assert not window.left_tabs.isTabVisible(window.ddl_browser_tab_index)


def test_toggle_on_without_connection_and_project_open_reroutes_to_project_settings(qtbot, tmp_path):
    """BUG-024: with a §18.2 project open, a missing connection must point
    the user at Project Settings, not the meaningless standalone Connection
    Setup dialog."""
    from pgtp_editor.db.ddl_project import ProjectSettings

    window = _window(qtbot, tmp_path, with_project=False)  # no .pgtp, empty settings
    window._set_active_ddl_project(tmp_path / "proj", ProjectSettings())
    fetches = []
    window._fetch_ddl_schema = lambda params: fetches.append(1) or _schema()

    window._ddl_explorer_action.setChecked(True)

    assert window._ddl_explorer_action.isChecked() is False  # rolled back
    assert window._connection_dialog is None  # Connection Setup NOT opened
    assert window._project_settings_dialog is not None  # Project Settings opened instead
    assert fetches == []  # never tried to fetch


def test_fetch_error_unchecks_and_shows_status(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    def _boom(params):
        raise RuntimeError("no route to host")

    window._fetch_ddl_schema = _boom

    window._ddl_explorer_action.setChecked(True)  # must not crash

    assert "DDL Explorer failed" in window.statusBar().currentMessage()
    assert "no route to host" in window.statusBar().currentMessage()
    assert window._ddl_explorer_action.isChecked() is False
    assert not window.center_stage.isTabVisible(window.center_stage.ddl_tab_index)
    assert not window.left_tabs.isTabVisible(window.ddl_browser_tab_index)


def test_toggle_shows_busy_status_then_populates_on_result(qtbot, tmp_path):
    """With a deferred runner nothing is revealed until the schema is
    delivered back on the GUI thread (mirrors the db-check busy test)."""
    window = _window(qtbot, tmp_path)
    captured = {}

    def deferred(fn, on_result, on_error=None):
        captured["fn"] = fn
        captured["on_result"] = on_result

    window._run_async = deferred
    window._ddl_explorer_action.setChecked(True)

    assert "Loading routines & triggers" in window.statusBar().currentMessage()
    assert not window.center_stage.isTabVisible(window.center_stage.ddl_tab_index)
    assert window.center_stage.ddl_editor_panel.editor.toPlainText() == ""

    captured["on_result"](captured["fn"]())

    assert window.center_stage.isTabVisible(window.center_stage.ddl_tab_index)
    assert window.left_tabs.isTabVisible(window.ddl_browser_tab_index)
    assert window.center_stage.ddl_editor_panel.editor.toPlainText() != ""


# ---------------------------------------------------------------------------
# Navigation: BrowserPanel leaf → center editor line.
# ---------------------------------------------------------------------------

def test_browser_navigate_requested_jumps_center_editor_to_line(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._ddl_explorer_action.setChecked(True)
    # Switch away to prove the jump re-activates the DDL tab.
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)

    window.ddl_browser_panel.navigate_requested.emit(3)

    assert window.center_stage.currentIndex() == window.center_stage.ddl_tab_index
    cursor = window.center_stage.ddl_editor_panel.editor.textCursor()
    assert cursor.blockNumber() == 2  # 1-based line 3


def test_clicking_a_tree_leaf_navigates_to_its_span_start(qtbot, tmp_path):
    """End-to-end through the real BrowserPanel click handler: the caret lands
    on the clicked object's banner line."""
    window = _window(qtbot, tmp_path)
    window._ddl_explorer_action.setChecked(True)
    panel = window.ddl_browser_panel
    routines_root = panel.tree.topLevelItem(1)
    calc_total_item = next(
        routines_root.child(i) for i in range(routines_root.childCount())
        if "calc_total" in routines_root.child(i).text(0)
    )

    panel._on_item_clicked(calc_total_item, 0)

    editor = window.center_stage.ddl_editor_panel.editor
    line_text = editor.textCursor().block().text()
    assert line_text == "-- FUNCTION pr.calc_total(integer) --"


# ---------------------------------------------------------------------------
# Click-to-Properties: BrowserPanel table node → PropertiesPanel (§18.1,
# 2026-08-05).
# ---------------------------------------------------------------------------

def test_clicking_a_table_node_populates_properties_panel(qtbot, tmp_path):
    """End-to-end through the real BrowserPanel click handler, mirroring how
    the XML/XSD tree's own node-click already drives the same Properties
    panel instance (_on_tree_selection_changed)."""
    window = _window(qtbot, tmp_path)
    window._ddl_explorer_action.setChecked(True)
    panel = window.ddl_browser_panel
    table_item = panel.tree.topLevelItem(0).child(0)  # pr.equipment

    panel._on_item_clicked(table_item, 0)

    assert window.properties_panel.is_showing_empty_state() is False
    assert window.properties_panel.header_text() == "Table: pr.equipment"


def test_clicking_a_table_node_does_not_jump_the_center_editor(qtbot, tmp_path):
    """A table node has no DdlObjectSpan -- unlike a routine/trigger leaf
    click, it must never move the center editor's caret."""
    window = _window(qtbot, tmp_path)
    window._ddl_explorer_action.setChecked(True)
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)
    panel = window.ddl_browser_panel
    table_item = panel.tree.topLevelItem(0).child(0)

    panel._on_item_clicked(table_item, 0)

    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index


# ---------------------------------------------------------------------------
# Lockstep: center tab ✕ / menu toggle / left tab (bidirectional, BUG-007).
# ---------------------------------------------------------------------------

def test_tab_close_button_hides_left_tab_and_unchecks_menu(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._ddl_explorer_action.setChecked(True)
    assert window.left_tabs.isTabVisible(window.ddl_browser_tab_index)

    window.center_stage.tabCloseRequested.emit(window.center_stage.ddl_tab_index)

    assert not window.center_stage.isTabVisible(window.center_stage.ddl_tab_index)
    assert not window.left_tabs.isTabVisible(window.ddl_browser_tab_index)
    assert window._ddl_explorer_action.isChecked() is False


def test_unchecking_menu_hides_center_and_left_tabs(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._ddl_explorer_action.setChecked(True)

    window._ddl_explorer_action.setChecked(False)

    assert not window.center_stage.isTabVisible(window.center_stage.ddl_tab_index)
    assert not window.left_tabs.isTabVisible(window.ddl_browser_tab_index)
    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index


def test_show_ddl_explorer_directly_checks_menu_and_reveals_left_tab(qtbot, tmp_path):
    """The other direction of the lockstep: revealing the center tab (however
    that happens) drags the menu checkbox and left tab along."""
    window = _window(qtbot, tmp_path)

    window.center_stage.show_ddl_explorer()

    assert window._ddl_explorer_action.isChecked() is True
    assert window.left_tabs.isTabVisible(window.ddl_browser_tab_index)
    assert window.left_tabs.currentWidget() is window.ddl_browser_panel
    assert window.tree_dock.isHidden() is False


def test_reopen_after_close_refetches_and_repopulates(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    fetches = []
    window._fetch_ddl_schema = lambda params: fetches.append(1) or _schema()

    window._ddl_explorer_action.setChecked(True)
    window.center_stage.tabCloseRequested.emit(window.center_stage.ddl_tab_index)
    window._ddl_explorer_action.setChecked(True)

    assert fetches == [1, 1]  # a fresh live fetch per reveal
    assert window.center_stage.isTabVisible(window.center_stage.ddl_tab_index)
    assert window.left_tabs.isTabVisible(window.ddl_browser_tab_index)


# ---------------------------------------------------------------------------
# Fold regions ride along with the buffer (§18.1 shared fold base).
# ---------------------------------------------------------------------------

def test_opening_installs_one_fold_region_per_object_in_the_editor(qtbot, tmp_path):
    """MainWindow passes build_ddl_text's spans to set_ddl_text, so every
    object in the freshly-fetched buffer is foldable under its banner."""
    from pgtp_editor.db.ddl_buffer import build_ddl_text

    window = _window(qtbot, tmp_path)
    window._ddl_explorer_action.setChecked(True)

    _text, spans = build_ddl_text(_schema())
    editor = window.center_stage.ddl_editor_panel.editor
    document = editor.document()
    foldable = {
        block
        for block in range(document.blockCount())
        if editor._foldable_region_starting_at(document.findBlockByNumber(block))
        is not None
    }
    assert foldable == {span.start_line - 1 for span in spans}
    assert len(foldable) == 3  # 2 routines + 1 trigger


def test_reopening_reinstalls_fold_regions_for_the_new_buffer(qtbot, tmp_path):
    """A re-fetch replaces the buffer; stale fold state/regions from the
    previous buffer must not survive into the new one."""
    window = _window(qtbot, tmp_path)
    window._ddl_explorer_action.setChecked(True)
    editor = window.center_stage.ddl_editor_panel.editor
    first_banner = editor.document().findBlockByNumber(0)
    editor._toggle_fold(first_banner)
    assert editor._fold_state

    window.center_stage.tabCloseRequested.emit(window.center_stage.ddl_tab_index)
    window._ddl_explorer_action.setChecked(True)

    editor = window.center_stage.ddl_editor_panel.editor
    assert editor._fold_state == {}
    document = editor.document()
    assert all(document.findBlockByNumber(i).isVisible() for i in range(document.blockCount()))
    assert editor._foldable_region_starting_at(document.findBlockByNumber(0)) is not None


def test_clicking_a_leaf_scrolls_that_banner_to_the_top(qtbot, tmp_path):
    """The BrowserPanel → EditorPanel jump is top-aligned (§18.1), not
    centered: the clicked object's banner is the first visible line."""
    window = _window(qtbot, tmp_path)
    # Long bodies, so the buffer actually overflows the viewport and the
    # scroll target is not clamped to the top of the document.
    from dataclasses import replace

    base = _schema()
    long_schema = DatabaseSchema(
        routines={
            key: replace(
                routine,
                source="\n".join(f"  -- {routine.name} line {i}" for i in range(60)),
            )
            for key, routine in base.routines.items()
        },
        triggers=base.triggers,
    )
    window._fetch_ddl_schema = lambda params: long_schema
    window._ddl_explorer_action.setChecked(True)
    editor = window.center_stage.ddl_editor_panel.editor
    editor.resize(400, 60)
    window.show()
    qtbot.waitExposed(window)

    panel = window.ddl_browser_panel
    routines_root = panel.tree.topLevelItem(1)
    calc_total_item = next(
        routines_root.child(i) for i in range(routines_root.childCount())
        if "calc_total" in routines_root.child(i).text(0)
    )
    panel._on_item_clicked(calc_total_item, 0)

    assert editor.firstVisibleBlock().text() == "-- FUNCTION pr.calc_total(integer) --"


# --- */! drift markers wired into the DDL Explorer fetch (§18.2) ------------
def test_toggle_on_with_a_project_open_renders_drift_markers(qtbot, tmp_path):
    from pgtp_editor.db.ddl_project import DeployedObject, ProjectSettings, content_hash, save_settings

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    settings = ProjectSettings(
        # BUG-034: with a project open, its own `target` is what connects --
        # the fetch no longer falls back to the app-level/`.pgtp`-seeded
        # `seed_params` result, so a project with a blank target reaches
        # Project Settings instead of the database.
        target=ConnectionParams(
            host="h", port="5432", database="d", user="u", password="p"
        ),
        deployed={
            "ddl/pr.calc_total.sql": DeployedObject(content_hash="stale-hash"),
        },
    )
    save_settings(project_dir, settings)
    window._set_active_ddl_project(project_dir, settings)

    window._ddl_explorer_action.setChecked(True)

    panel = window.ddl_browser_panel
    routines_root = panel.tree.topLevelItem(1)
    calc_total_item = next(
        routines_root.child(i) for i in range(routines_root.childCount())
        if "calc_total" in routines_root.child(i).text(0)
    )
    assert calc_total_item.text(0).endswith("!")  # live def differs from stale-hash


def test_toggle_on_with_no_project_open_renders_no_markers(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window._ddl_explorer_action.setChecked(True)

    panel = window.ddl_browser_panel
    routines_root = panel.tree.topLevelItem(1)
    calc_total_item = next(
        routines_root.child(i) for i in range(routines_root.childCount())
        if "calc_total" in routines_root.child(i).text(0)
    )
    assert calc_total_item.text(0) == "pr.calc_total() [F]"


# --- BUG-034: the fetch connects with the PROJECT's target -------------------
def test_explorer_with_a_project_open_connects_with_the_project_target(qtbot, tmp_path):
    """One source of truth: the app must not connect with app-level QSettings
    credentials while Project Settings displays the project profile."""
    from pgtp_editor.db.ddl_project import ProjectSettings

    settings = _empty_settings(tmp_path)
    save_connection(settings, ConnectionParams(
        host="app-level", port="1", database="a", user="a", password="a"
    ))
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window._current_project = _project_with_connection()  # host="h" in the XML
    window._run_async = _sync_run
    used = []
    window._fetch_ddl_schema = lambda params: used.append(params) or _schema()
    window._set_active_ddl_project(
        tmp_path / "proj",
        ProjectSettings(target=ConnectionParams(
            host="project-host", port="5433", database="pdb", user="pu", password="pp"
        )),
    )

    window._ddl_explorer_action.setChecked(True)

    assert [p.host for p in used] == ["project-host"]


def test_explorer_prompts_once_for_a_password_the_pgtp_could_not_supply(qtbot, tmp_path):
    """An imported target arrives password-less (§17: never read from the XML).
    The prompt is raised at the first gesture that actually connects, and the
    answer rides into the fetch."""
    from pgtp_editor.db.ddl_project import ProjectSettings, load_settings, save_settings

    window = _window(qtbot, tmp_path, with_project=False)
    project_dir = tmp_path / "proj"
    project_settings = ProjectSettings(
        target=ConnectionParams(host="dbhost", port="5433", database="erpdb", user="erp")
    )
    save_settings(project_dir, project_settings)
    window._set_active_ddl_project(project_dir, project_settings)
    used = []
    window._fetch_ddl_schema = lambda params: used.append(params) or _schema()
    window._prompt_target_password = lambda params: "s3cret"

    window._ddl_explorer_action.setChecked(True)

    assert used and used[0].password == "s3cret"
    assert load_settings(project_dir).target.password == "s3cret"
