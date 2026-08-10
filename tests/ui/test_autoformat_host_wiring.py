"""Every Format Selection host reads the SAVED ruleset (spec §18.4 A+B+C+D).

The point of these tests is the seam, not the engines (those are covered in
`tests/sql/` and `tests/xmlfmt/`): a config saved by the Autoformatter settings
dialog must reach all five host surfaces -- and it must reach them **at gesture
time**, so a save applies to the next `Ctrl+Alt+F` in an already-open tab without
any notification plumbing.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QTextCursor

from pgtp_editor.sql import FormatConfig
from pgtp_editor.sql.format_config import ClauseRule, KeywordCase
from pgtp_editor.ui import format_settings
from pgtp_editor.ui.ddl_object_editor import DdlObjectEditorPanel, DdlObjectRef
from pgtp_editor.ui.sql_console_panel import SqlConsolePanel
from pgtp_editor.ui.xml_editor import XmlEditor
from pgtp_editor.xmlfmt import XmlFormatConfig

_REF = DdlObjectRef(kind="function", schema="pr", name="recalc")
_SQL = "select a,b from t where a=1"


@pytest.fixture
def store(tmp_path):
    settings = QSettings(str(tmp_path / "autoformat.ini"), QSettings.Format.IniFormat)
    format_settings.use_settings(settings)
    yield settings
    format_settings.use_settings(None)


def _select_all(editor) -> None:
    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)


def _save(store, sql_config=None, xml_config=None) -> None:
    format_settings.save_configs(
        sql_config if sql_config is not None else format_settings.load_sql_config(store),
        xml_config if xml_config is not None else format_settings.load_xml_config(store),
        store,
    )


def test_the_ddl_object_tab_uses_the_saved_config(qtbot, store):
    _save(store, FormatConfig(indent_unit="  ", keyword_case=KeywordCase.UPPER))
    panel = DdlObjectEditorPanel(_REF, "begin x:=1; end;")
    qtbot.addWidget(panel)
    _select_all(panel.editor)

    panel.format_selection()

    assert panel.text() == "BEGIN\n  x := 1;\nEND;"


def test_the_sandbox_console_uses_the_saved_config(qtbot, store):
    _save(store, FormatConfig(keyword_case=KeywordCase.UPPER))
    console = SqlConsolePanel()
    qtbot.addWidget(console)
    console.editor.setPlainText(_SQL)
    _select_all(console.editor)

    console.format_selection()

    assert console.editor.toPlainText() == "SELECT a, b\nFROM t\nWHERE a = 1"


def test_an_untouched_install_formats_exactly_as_before(qtbot, store):
    # The default config is byte-identical to the pre-FQ-033 engine: nobody's
    # formatting changes until they ask for it.
    panel = DdlObjectEditorPanel(_REF, _SQL)
    qtbot.addWidget(panel)
    _select_all(panel.editor)

    panel.format_selection()

    assert panel.text() == "select a, b\nfrom t\nwhere a = 1"


def test_a_saved_change_reaches_an_ALREADY_OPEN_tab(qtbot, store):
    panel = DdlObjectEditorPanel(_REF, _SQL)
    qtbot.addWidget(panel)
    # ...the dialog saves AFTER the tab was constructed...
    _save(store, FormatConfig(keyword_case=KeywordCase.UPPER))
    _select_all(panel.editor)

    panel.format_selection()

    assert panel.text().startswith("SELECT")


def test_the_per_clause_grid_reaches_the_hosts(qtbot, store):
    _save(
        store,
        FormatConfig(
            clause_rules={
                "from": ClauseRule(indent_levels=1),
                "where": ClauseRule(break_before=False),
            }
        ),
    )
    panel = DdlObjectEditorPanel(_REF, _SQL)
    qtbot.addWidget(panel)
    _select_all(panel.editor)

    panel.format_selection()

    assert panel.text() == "select a, b\n    from t where a = 1"


def test_an_xml_surface_uses_the_xml_config_and_never_the_sql_engine(qtbot, store):
    # Which engine answers is decided by the HOST SURFACE, statically. A SQL-ish
    # XML selection must still be treated as XML.
    _save(store, FormatConfig(keyword_case=KeywordCase.UPPER), XmlFormatConfig(indent_unit=" "))
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Root>\n<Query>select 1</Query>\n</Root>\n")
    _select_all(editor)

    editor.format_selection()

    # Indented by the XML width, and the SQL inside the element text untouched.
    assert editor.toPlainText() == "<Root>\n <Query>select 1</Query>\n</Root>\n"
