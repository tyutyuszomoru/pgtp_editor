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
from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo, TriggerInfo
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
        "pr.calc_total": RoutineInfo(
            schema="pr", name="calc_total", arg_types=["integer"],
            return_type="numeric", language="plpgsql",
            source="CREATE FUNCTION pr.calc_total(a integer) ...", kind="function",
        ),
        "pr.audit_log": RoutineInfo(
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
    return DatabaseSchema(routines=routines, triggers=triggers)


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
