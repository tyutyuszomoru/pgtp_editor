# tests/ui/test_ddl_schema_index_wiring.py
"""MainWindow wiring for schema-aware Ctrl+Space completion's injection seam
(spec §18.6): the DDL Explorer fetch builds a `db/schema_index.py::SchemaIndex`
from the same (now widened) `DatabaseSchema` and hands it to every
`DdlObjectEditorPanel` -- newly opened ones (both entry points: Edit… and
Check Out for Versioning) and already-open ones (refreshed on every re-fetch,
mirroring how the tree and read-only buffer refresh)."""
from lxml import etree
from PySide6.QtCore import QSettings

from pgtp_editor.db.introspect import (
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    TableInfo,
    TriggerInfo,
)
from pgtp_editor.db.schema_index import SchemaIndex
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef
from pgtp_editor.ui.main_window import MainWindow

_REF = DdlObjectRef(kind="function", schema="pr", name="recalc")


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


def _schema_with_tables():
    return DatabaseSchema(
        tables={
            "pr.equipment": TableInfo(
                name="pr.equipment", kind="table",
                columns=[
                    ColumnInfo(name="id", data_type="integer", is_pk=True, is_fk=False, is_nullable=False, default=None),
                ],
            ),
        },
        routines={
            "pr.calc_total(integer)": RoutineInfo(
                schema="pr", name="calc_total", arg_types=["integer"],
                return_type="numeric", language="plpgsql", source="...",
                kind="function",
            ),
        },
        triggers={
            "pr.equipment.trg_audit": TriggerInfo(
                schema="pr", table="equipment", name="trg_audit", timing="after",
                events=["insert"], function_name="audit_log", definition="...",
            ),
        },
    )


def _sync_run(fn, on_result, on_error=None):
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001
        (on_error or (lambda _e: None))(exc)


def _empty_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def _window(qtbot, tmp_path):
    window = MainWindow(settings=_empty_settings(tmp_path))
    qtbot.addWidget(window)
    window._current_project = _project_with_connection()
    window._fetch_ddl_schema = lambda params: _schema_with_tables()
    window._run_async = _sync_run
    return window


def test_no_schema_index_before_any_ddl_explorer_fetch(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window._ddl_schema_index is None


def test_ddl_explorer_fetch_builds_a_schema_index(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._open_ddl_explorer()
    assert isinstance(window._ddl_schema_index, SchemaIndex)
    assert window._ddl_schema_index.known_tables("pr") == ["equipment"]


def test_edit_requested_injects_the_current_schema_index(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._open_ddl_explorer()  # populates window._ddl_schema_index first

    window._on_ddl_edit_requested(_REF, "CREATE FUNCTION pr.recalc() ...")

    panel = window.center_stage.ddl_object_tab(_REF.key)
    assert panel.schema_index() is window._ddl_schema_index


def test_edit_requested_before_any_fetch_injects_none(qtbot, tmp_path):
    """No DDL Explorer fetch has happened yet -- the panel gets None, which
    disables completion entirely rather than erroring."""
    window = _window(qtbot, tmp_path)

    window._on_ddl_edit_requested(_REF, "CREATE FUNCTION pr.recalc() ...")

    panel = window.center_stage.ddl_object_tab(_REF.key)
    assert panel.schema_index() is None


def test_reopening_ddl_explorer_refreshes_already_open_object_tabs(qtbot, tmp_path):
    """A later re-fetch (e.g. Database ▸ DDL Explorer run again) pushes the
    freshly rebuilt index into tabs that were already open -- so a tab opened
    before the first successful connect still gains completion once the
    schema becomes available, without the user having to reopen it."""
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "CREATE FUNCTION pr.recalc() ...")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    assert panel.schema_index() is None

    window._open_ddl_explorer()

    assert panel.schema_index() is window._ddl_schema_index
    assert isinstance(panel.schema_index(), SchemaIndex)
