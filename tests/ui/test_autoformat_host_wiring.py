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


# --------------------------------------------------------------------------
# The host table itself: FIVE surfaces have the gesture, and the rest do not
# --------------------------------------------------------------------------

MESSY_XML = "<Root>\n<Page name=\"a\">\n<Field name=\"x\"/>\n</Page>\n</Root>\n"
TIDY_XML = (
    "<Root>\n  <Page name=\"a\">\n    <Field name=\"x\"/>\n  </Page>\n</Root>\n"
)


def _xml_editors_of_a_center_stage(stage):
    """The THREE `XmlEditor` instances §18.4 C insists on counting correctly.

    FQ-033's queue entry said "both `XmlEditor`" and was wrong: the FQ-006 draft
    fragment tab is the third, and it is included on purpose -- its whole point
    is review-and-copy-out, which is exactly when reindenting a fragment helps.
    """
    draft = stage.open_draft_fragment_tab("page", "pr.customers", MESSY_XML)
    return {
        "raw xml": stage.xml_editor,
        "edit xsd": stage.xsd_editor,
        "draft fragment": draft.editor,
    }


def test_all_three_xml_editor_surfaces_carry_the_gesture(qtbot, store):
    stage_module = pytest.importorskip("pgtp_editor.ui.center_stage")
    stage = stage_module.CenterStage()
    qtbot.addWidget(stage)

    editors = _xml_editors_of_a_center_stage(stage)
    assert len(editors) == 3

    for label, editor in editors.items():
        editor.setPlainText(MESSY_XML)
        _select_all(editor)
        assert editor.format_selection() is True, label
        assert editor.toPlainText() == TIDY_XML, label


def test_all_three_xml_editor_surfaces_read_the_saved_xml_width(qtbot, store):
    # Four spaces, not a tab: the XML domain is 1-8 SPACES (§18.4 B's table), so
    # the width -- and only the width -- is what a surface can be asked to change.
    _save(store, xml_config=XmlFormatConfig(indent_unit="    "))
    stage_module = pytest.importorskip("pgtp_editor.ui.center_stage")
    stage = stage_module.CenterStage()
    qtbot.addWidget(stage)

    for label, editor in _xml_editors_of_a_center_stage(stage).items():
        editor.setPlainText(MESSY_XML)
        _select_all(editor)
        editor.format_selection()
        assert "    <Page" in editor.toPlainText(), label


def test_each_of_the_three_surfaces_hosts_the_chord_and_the_context_menu_item(qtbot, store):
    """Both command forms come from `XmlEditor` itself, which is *why* all three
    surfaces have them -- pinned so a future per-surface flag cannot silently
    take the gesture away from one of them."""
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QApplication

    stage_module = pytest.importorskip("pgtp_editor.ui.center_stage")
    stage = stage_module.CenterStage()
    qtbot.addWidget(stage)

    for label, editor in _xml_editors_of_a_center_stage(stage).items():
        editor.setPlainText(MESSY_XML)
        _select_all(editor)
        chords = [
            shortcut.key().toString()
            for shortcut in editor.findChildren(type(editor._format_shortcut))
        ]
        assert QKeySequence("Ctrl+Alt+F").toString() in chords, label
        menu = editor._build_context_menu()
        entries = [action for action in menu.actions() if action.text() == "Format Selection"]
        assert len(entries) == 1, label
        assert entries[0].isEnabled() is True, label
        # The QShortcut stays the single keyboard host (DEC-004/BUG-046).
        assert entries[0].shortcut().isEmpty(), label
        menu.deleteLater()
    QApplication.processEvents()


def test_the_gesture_is_ABSENT_not_refusing_on_a_php_tab(qtbot, tmp_path, store):
    """§18.4 C's last host-table row: PHP tabs, the `CodeEditorDialog` and the
    Explorer buffer are neither XML nor a SQL authoring surface, so the gesture
    does not exist there -- §18.9's precedent (a refusal is right when a
    capability is one click from applicable, wrong when the surface could never
    qualify)."""
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QWidget

    from pgtp_editor.ui.code_editor import CodeEditorDialog
    from pgtp_editor.ui.php_file_tab import PhpFileTab

    path = tmp_path / "page.php"
    path.write_text("<?php\n$x = 1;\n", encoding="utf-8")
    php_tab = PhpFileTab(str(path))
    qtbot.addWidget(php_tab)
    dialog = CodeEditorDialog("php")
    qtbot.addWidget(dialog)

    for surface in (php_tab, dialog):
        assert not hasattr(surface, "format_selection"), type(surface).__name__
        for editor in surface.findChildren(QWidget):
            assert not hasattr(editor, "format_selection"), type(editor).__name__
        from PySide6.QtGui import QShortcut

        chords = [
            shortcut.key().toString() for shortcut in surface.findChildren(QShortcut)
        ]
        assert QKeySequence("Ctrl+Alt+F").toString() not in chords, type(surface).__name__


# --------------------------------------------------------------------------
# The two seams that are PENDING `main_window.py` (owned by a concurrent
# worktree at FQ-033's merge). These are NOT failures of the feature: they are
# the wiring the main session will add. Delete the xfail marker when it lands.
# --------------------------------------------------------------------------


def test_the_settings_menu_reaches_the_autoformatter_dialog(qtbot, tmp_path):
    from PySide6.QtCore import QSettings as _QSettings

    from pgtp_editor.ui.main_window import MainWindow

    settings = _QSettings(str(tmp_path / "app.ini"), _QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    labels = [
        action.text()
        for action in window._settings_menu.actions()
        if not action.isSeparator()
    ]
    assert "Autoformatter settings…" in labels


def test_an_xml_refusal_reaches_the_xml_activity_log_prefix(qtbot, tmp_path):
    from PySide6.QtCore import QSettings as _QSettings

    from pgtp_editor.ui.main_window import MainWindow

    settings = _QSettings(str(tmp_path / "app.ini"), _QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    editor = window.center_stage.xml_editor
    editor.setPlainText("<a><b></a></b>")
    _select_all(editor)

    editor.format_selection()

    # `row_texts()` is the Activity Panel's read API -- the 36-use convention
    # across tests/ui. The pending-wiring version guessed `lines()`, which does
    # not exist, and asserted `startswith` -- but the Activity Log renders each
    # row with a timestamp and a source ("... - Quality files [XML] line 1: ..."),
    # so the prefix is CONTAINED, never leading. Containment is the convention
    # the shipped `[SQL]` assertions already use.
    rows = window.activity_panel.row_texts()
    assert any("[XML] " in str(row) for row in rows), rows
