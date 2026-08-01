# tests/ui/test_ddl_editor_panel.py
"""EditorPanel: the CenterStage "DDL Explorer" tab (spec §18.1) -- a read-only
sql-mode CodeEditor plus its own FindReplaceBar instance (the same per-tab
routing precedent as the Edit XSD tab)."""
from pgtp_editor.ui.code_editor import CodeEditor, _SQL_KEYWORDS
from pgtp_editor.ui.ddl_editor_panel import EditorPanel
from pgtp_editor.ui.find_replace_bar import FindReplaceBar

_TEXT = (
    "-- FUNCTION pr.calc_total(integer) --\n"
    "CREATE FUNCTION pr.calc_total(a integer) RETURNS numeric AS $$\n"
    "BEGIN\n"
    "  RETURN a * 2;\n"
    "END;\n"
    "$$ LANGUAGE plpgsql;\n"
)


def test_panel_hosts_a_read_only_sql_code_editor(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    assert isinstance(panel.editor, CodeEditor)
    assert panel.editor.isReadOnly() is True
    # sql language mode: the highlighter consumes the SQL keyword set.
    assert panel.editor._highlighter._keywords is _SQL_KEYWORDS


def test_set_ddl_text_replaces_the_buffer(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(_TEXT)
    assert panel.editor.toPlainText() == _TEXT
    # A second load REPLACES (fresh build_ddl_text result), never appends.
    panel.set_ddl_text("-- TRIGGER pr.t ON x --\ndef\n")
    assert panel.editor.toPlainText() == "-- TRIGGER pr.t ON x --\ndef\n"


def test_navigate_to_line_jumps_the_editor(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(_TEXT)
    panel.navigate_to_line(3)
    cursor = panel.editor.textCursor()
    assert cursor.blockNumber() == 2  # 1-based line 3
    assert cursor.block().text() == "BEGIN"


def test_panel_has_its_own_find_replace_bar_wired_to_the_sql_editor(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    assert isinstance(panel.find_replace_bar, FindReplaceBar)
    assert panel.find_replace_bar._editor is panel.editor
    assert panel.find_replace_bar.parent() is panel


def test_find_replace_bar_replace_cannot_edit_the_read_only_buffer(qtbot):
    """The bar's Replace goes through replace_current_selection, whose
    read-only guard is what actually protects the DDL buffer (QTextCursor
    edits bypass setReadOnly)."""
    from PySide6.QtGui import QTextCursor

    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(_TEXT)
    cursor = panel.editor.textCursor()
    cursor.setPosition(0)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
    panel.editor.setTextCursor(cursor)
    panel.editor.replace_current_selection("VANDALIZED")
    assert panel.editor.toPlainText() == _TEXT
