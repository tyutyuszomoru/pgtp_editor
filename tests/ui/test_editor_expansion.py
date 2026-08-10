# tests/ui/test_editor_expansion.py
"""Template expansion in the editor: the ONE application path (FQ-030 1 & 2).

`sql/templates.py` and `sql/expand_select.py` are pure and already tested; what
is tested here is the editor half -- `CodeEditor.apply_expansion` and the two
gestures that feed it (a keyword snippet, and expand-`SELECT` through the
panels' schema seam), which are ONE mechanism and must stay one.

The two things most easily broken and therefore pinned hardest:

- **one undo** for a whole multi-piece expansion, and
- **Tab unchanged** in every editor that is not mid-walk -- a PHP tab, an
  untouched SQL editor, and a SQL editor that has finished its walk. Taking Tab
  globally would have broken indentation in four surfaces.

No live database: `SchemaIndex` is built from a canned `DatabaseSchema`, the
same style `test_ddl_object_editor_completion.py` uses.
"""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtTest import QTest

from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.db.schema_index import SchemaIndex
from pgtp_editor.sql.templates import (
    DEFAULT_SNIPPETS,
    Expansion,
    Snippet,
    expand_template,
)
from pgtp_editor.ui.code_editor import CodeEditor
from pgtp_editor.ui.ddl_object_editor import DdlObjectEditorPanel, DdlObjectRef
from pgtp_editor.ui.expand_select_seam import expand_select_expansion
from pgtp_editor.ui.php_file_tab import PhpFileTab
from pgtp_editor.ui.sql_console_panel import SqlConsolePanel

CTRL_ALT = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier


# --- helpers ----------------------------------------------------------------


def _editor(qtbot, language="sql", text=""):
    editor = CodeEditor(language)
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    return editor


def _caret(editor, pos):
    cursor = editor.textCursor()
    cursor.setPosition(pos)
    editor.setTextCursor(cursor)


def _caret_after(editor, marker):
    _caret(editor, editor.toPlainText().index(marker) + len(marker))


def _schema():
    tables = {
        "hr.jobcard": TableInfo(
            name="hr.jobcard",
            kind="table",
            columns=[
                ColumnInfo(name="id", data_type="integer", is_pk=True, is_fk=False, is_nullable=False, default=None),
                ColumnInfo(name="job", data_type="text", is_pk=False, is_fk=False, is_nullable=True, default=None),
                ColumnInfo(name="card", data_type="text", is_pk=False, is_fk=False, is_nullable=True, default=None),
            ],
        ),
        "hr.dept": TableInfo(
            name="hr.dept",
            kind="table",
            columns=[
                ColumnInfo(name="id", data_type="integer", is_pk=True, is_fk=False, is_nullable=False, default=None),
            ],
        ),
    }
    return SchemaIndex(DatabaseSchema(tables=tables, routines={}, triggers={}))


def _ddl_panel(qtbot, text="", index=None):
    panel = DdlObjectEditorPanel(
        DdlObjectRef(kind="function", schema="hr", name="f"), text
    )
    qtbot.addWidget(panel)
    if index is not None:
        panel.set_schema_index(index)
    return panel


def _refusals(editor):
    seen = []
    editor.expansion_refused.connect(seen.append)
    return seen


# --- The one application path -----------------------------------------------


def test_apply_expansion_replaces_the_span_and_places_the_caret(qtbot):
    editor = _editor(qtbot, text="one two three")
    applied = editor.apply_expansion(
        Expansion(text="TWO", start=4, end=7, caret=7, ok=True)
    )
    assert applied is True
    assert editor.toPlainText() == "one TWO three"
    assert editor.textCursor().position() == 7


def test_a_whole_expansion_is_a_single_undo(qtbot):
    """The template is assembled from many pieces; the user sees one edit."""
    editor = _editor(qtbot, text="case")
    _caret(editor, 4)
    assert editor.expand_snippet_at_caret() is True
    assert editor.toPlainText().startswith("CASE WHEN")
    editor.undo()
    assert editor.toPlainText() == "case"


def test_apply_expansion_does_not_enter_tab_stop_mode_without_a_walkable_stop(qtbot):
    """`{{0}}` alone is a caret, not a walk: Tab must stay a tab afterwards."""
    editor = _editor(qtbot, text="")
    editor.apply_expansion(expand_template("a {{0}}"))
    assert editor.in_tab_stop_mode is False


def test_apply_expansion_refuses_a_falsy_expansion_with_its_reason(qtbot):
    editor = _editor(qtbot, text="keep me")
    seen = _refusals(editor)
    assert editor.apply_expansion(Expansion(reason="nope")) is False
    assert editor.toPlainText() == "keep me"
    assert seen == ["nope"]


def test_apply_expansion_refuses_on_a_read_only_editor(qtbot):
    """QTextCursor edits bypass setReadOnly -- the §18.1 viewer stays intact."""
    editor = _editor(qtbot, text="viewer")
    editor.setReadOnly(True)
    seen = _refusals(editor)
    assert editor.apply_expansion(expand_template("X", at=0, end=6)) is False
    assert editor.toPlainText() == "viewer"
    assert seen == ["this buffer is read-only"]


# --- Tab-stop mode ----------------------------------------------------------


def test_tab_walks_forward_through_the_stops(qtbot):
    editor = _editor(qtbot, text="")
    editor.apply_expansion(expand_template("a {{1:one}} b {{2:two}} c {{0}}"))
    assert editor.in_tab_stop_mode is True
    assert editor.textCursor().selectedText() == "one"
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.textCursor().selectedText() == "two"
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    # The `{{0}}` final caret: no placeholder to select, still in the walk.
    assert editor.textCursor().selectedText() == ""
    assert editor.in_tab_stop_mode is True


def test_shift_tab_walks_back_and_stops_at_the_first(qtbot):
    editor = _editor(qtbot, text="")
    editor.apply_expansion(expand_template("{{1:one}} {{2:two}} {{0}}"))
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.textCursor().selectedText() == "two"
    QTest.keyClick(editor, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    assert editor.textCursor().selectedText() == "one"
    # At the first stop, back goes nowhere rather than dropping out.
    QTest.keyClick(editor, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    assert editor.textCursor().selectedText() == "one"
    assert editor.in_tab_stop_mode is True


def test_typing_replaces_the_placeholder_and_later_stops_move_with_it(qtbot):
    editor = _editor(qtbot, text="")
    editor.apply_expansion(expand_template("{{1:one}}/{{2:two}}/{{0}}"))
    QTest.keyClicks(editor, "XY")
    assert editor.toPlainText() == "XY/two/"
    # The second stop tracked the shrink -- Tab still selects `two`.
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.textCursor().selectedText() == "two"


def test_walking_past_the_last_stop_exits_and_consumes_that_tab(qtbot):
    editor = _editor(qtbot, text="")
    editor.apply_expansion(expand_template("{{1:one}} {{0}}"))
    QTest.keyClick(editor, Qt.Key.Key_Tab)  # -> the final caret
    QTest.keyClick(editor, Qt.Key.Key_Tab)  # -> out
    assert editor.in_tab_stop_mode is False
    assert "\t" not in editor.toPlainText()
    # ...and Tab is an ordinary tab again the very next press.
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert "\t" in editor.toPlainText()


def test_escape_exits_tab_stop_mode(qtbot):
    editor = _editor(qtbot, text="")
    editor.apply_expansion(expand_template("{{1:one}} {{2:two}} {{0}}"))
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    assert editor.in_tab_stop_mode is False
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert "\t" in editor.toPlainText()


def test_clicking_away_exits_tab_stop_mode(qtbot):
    editor = _editor(qtbot, text="")
    editor.apply_expansion(expand_template("{{1:one}} {{0}}"))
    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton)
    assert editor.in_tab_stop_mode is False


def test_losing_focus_exits_tab_stop_mode(qtbot):
    editor = _editor(qtbot, text="")
    editor.apply_expansion(expand_template("{{1:one}} {{0}}"))
    editor.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
    assert editor.in_tab_stop_mode is False


def test_a_second_expansion_replaces_the_first_walk(qtbot):
    editor = _editor(qtbot, text="")
    editor.apply_expansion(expand_template("{{1:one}} {{2:two}} {{0}}"))
    editor.apply_expansion(expand_template("{{1:solo}} {{0}}", at=0, end=0))
    assert len(editor.tab_stop_spans()) == 2
    assert editor.tab_stop_index == 0


# --- Tab is untouched everywhere else ---------------------------------------


def test_tab_still_inserts_a_tab_in_a_php_tab(qtbot):
    """The regression this feature could most easily have caused."""
    tab = PhpFileTab(None, "<?php\n")
    qtbot.addWidget(tab)
    _caret(tab.editor, len(tab.editor.toPlainText()))
    QTest.keyClick(tab.editor, Qt.Key.Key_Tab)
    assert tab.editor.toPlainText() == "<?php\n\t"
    assert tab.editor.in_tab_stop_mode is False


def test_tab_still_inserts_a_tab_in_an_untouched_sql_editor(qtbot):
    editor = _editor(qtbot, text="select ")
    _caret(editor, 7)
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.toPlainText() == "select \t"


def test_the_expansion_keys_do_nothing_in_a_php_editor(qtbot):
    """The snippet set is plpgsql; a PHP body must never receive it.

    The keys are not swallowed there either -- they keep doing exactly what
    they did before this feature, which on Qt is inserting the character
    (Ctrl+Alt is AltGr, the same reason Ctrl+Alt+F was already a chord this
    codebase was willing to spend).
    """
    editor = _editor(qtbot, language="php", text="case")
    seen = _refusals(editor)
    _caret(editor, 4)
    QTest.keyClick(editor, Qt.Key.Key_E, CTRL_ALT)
    QTest.keyClick(editor, Qt.Key.Key_C, CTRL_ALT)
    assert "IF" not in editor.toPlainText()
    assert editor.toPlainText() == "caseec"
    assert seen == []


# --- Snippets ---------------------------------------------------------------


def test_ctrl_alt_e_expands_a_default_snippet(qtbot):
    editor = _editor(qtbot, text="  if")
    _caret(editor, 4)
    QTest.keyClick(editor, Qt.Key.Key_E, CTRL_ALT)
    assert editor.toPlainText() == "  IF condition THEN\n    \nEND IF;"
    assert editor.textCursor().selectedText() == "condition"


def test_every_shipped_snippet_expands_from_its_prefix(qtbot):
    for snippet in DEFAULT_SNIPPETS:
        editor = _editor(qtbot, text=snippet.prefix)
        _caret(editor, len(snippet.prefix))
        assert editor.expand_snippet_at_caret() is True, snippet.prefix
        assert editor.toPlainText() != snippet.prefix


def test_snippet_prefix_matching_is_case_insensitive(qtbot):
    editor = _editor(qtbot, text="CASE")
    _caret(editor, 4)
    assert editor.expand_snippet_at_caret() is True
    assert editor.toPlainText().startswith("CASE WHEN condition")


def test_a_word_that_is_not_a_snippet_says_so(qtbot):
    editor = _editor(qtbot, text="select")
    seen = _refusals(editor)
    _caret(editor, 6)
    assert editor.expand_snippet_at_caret() is False
    assert seen == ["'select' is not a snippet"]


def test_no_word_before_the_caret_says_so(qtbot):
    editor = _editor(qtbot, text="if ")
    seen = _refusals(editor)
    _caret(editor, 3)
    assert editor.expand_snippet_at_caret() is False
    assert seen == ["there is no word before the caret to expand"]


def test_set_snippets_layers_a_user_store_over_the_defaults(qtbot):
    """The seam a later per-user store plugs into -- no engine fork."""
    editor = _editor(qtbot, text="mine")
    editor.set_snippets([Snippet("mine", "mine", "MINE {{0}}")])
    _caret(editor, 4)
    assert editor.expand_snippet_at_caret() is True
    assert editor.toPlainText() == "MINE "
    # ...and the defaults are then out of the way, as an override should be.
    editor.setPlainText("if")
    _caret(editor, 2)
    assert editor.expand_snippet_at_caret() is False
    editor.set_snippets(None)
    assert editor.snippets() is DEFAULT_SNIPPETS


# --- Expand-SELECT, end to end ----------------------------------------------


def test_expand_select_end_to_end_in_a_ddl_object_tab(qtbot):
    panel = _ddl_panel(qtbot, text="SELECT FROM hr.jobcard", index=_schema())
    _caret_after(panel.editor, "SELECT")
    QTest.keyClick(panel.editor, Qt.Key.Key_C, CTRL_ALT)
    assert panel.editor.toPlainText() == (
        "SELECT j.id, j.job, j.card FROM hr.jobcard j WHERE "
    )
    # The caret is one space after WHERE, and there is no walk to leave.
    assert panel.editor.textCursor().position() == len(panel.editor.toPlainText())
    assert panel.editor.in_tab_stop_mode is False


def test_expand_select_is_one_undo(qtbot):
    panel = _ddl_panel(qtbot, text="SELECT FROM hr.jobcard", index=_schema())
    _caret_after(panel.editor, "SELECT")
    assert panel.expand_select() is True
    panel.editor.undo()
    assert panel.editor.toPlainText() == "SELECT FROM hr.jobcard"


def test_expand_select_keeps_the_typed_schema_and_a_typed_alias(qtbot):
    panel = _ddl_panel(qtbot, text="select from hr.jobcard jc", index=_schema())
    _caret_after(panel.editor, "select")
    panel.expand_select()
    assert panel.editor.toPlainText() == (
        "select jc.id, jc.job, jc.card from hr.jobcard jc where "
    )


def test_expand_select_works_in_the_sql_console(qtbot):
    console = SqlConsolePanel()
    qtbot.addWidget(console)
    console.set_schema_index(_schema())
    console.editor.setPlainText("SELECT FROM hr.jobcard")
    _caret_after(console.editor, "SELECT")
    assert console.expand_select() is True
    assert console.editor.toPlainText().startswith("SELECT j.id, j.job, j.card")


def test_expand_select_without_a_schema_index_writes_a_star(qtbot):
    """Unknown columns are `*` -- honest, valid, and still worth expanding."""
    panel = _ddl_panel(qtbot, text="SELECT FROM hr.jobcard")
    _caret_after(panel.editor, "SELECT")
    assert panel.expand_select() is True
    assert panel.editor.toPlainText() == "SELECT * FROM hr.jobcard j WHERE "


def test_expand_select_states_that_an_editor_with_no_seam_cannot(qtbot):
    editor = _editor(qtbot, text="SELECT FROM hr.jobcard")
    seen = _refusals(editor)
    _caret_after(editor, "SELECT")
    assert editor.expand_select_at_caret() is False
    assert seen and "schema" in seen[0]


def test_expand_select_states_that_a_none_seam_result_has_nothing_to_expand(qtbot):
    editor = _editor(qtbot, text="anything")
    editor.set_dynamic_expander(lambda text, pos: None)
    seen = _refusals(editor)
    assert editor.expand_select_at_caret() is False
    assert seen == ["there is nothing to expand at the caret"]


# --- Every refusal reason reaches the user ----------------------------------


REFUSALS = [
    # (buffer, caret marker, the substring of the reason the user must see)
    ("SELECT id FROM hr.jobcard", "SELECT", "already lists its columns"),
    ("SELECT FROM hr.jobcard, hr.dept", "SELECT", "several tables"),
    ("SELECT FROM (SELECT 1) s", "SELECT", "subquery"),
    ("SELECT 1", "SELECT", "no FROM clause"),
    ("UPDATE hr.jobcard SET id = 1", "UPDATE", "not inside a SELECT"),
]


def test_each_expand_select_refusal_reaches_the_user(qtbot):
    for text, marker, expected in REFUSALS:
        panel = _ddl_panel(qtbot, text=text, index=_schema())
        seen = _refusals(panel.editor)
        _caret_after(panel.editor, marker)
        assert panel.expand_select() is False, text
        assert seen, text
        assert expected in seen[0], (text, seen)
        # A refusal never touches the buffer.
        assert panel.editor.toPlainText() == text


def test_an_empty_buffer_refuses_with_a_reason_rather_than_no_op(qtbot):
    panel = _ddl_panel(qtbot, text="", index=_schema())
    seen = _refusals(panel.editor)
    assert panel.expand_select() is False
    assert seen == ["there is no statement here"]


# --- The seam itself --------------------------------------------------------


def test_the_seam_looks_columns_up_on_the_qualified_key_only_once(qtbot):
    asked = []

    class Index:
        def known_columns(self, table):
            asked.append(table)
            return ["a", "b"]

    expansion = expand_select_expansion(Index(), "SELECT FROM hr.jobcard", 6)
    assert asked == ["hr.jobcard"]
    assert expansion.text == " j.a, j.b FROM hr.jobcard j WHERE "


def test_the_seam_never_asks_for_a_bare_table(qtbot):
    """No schema typed means no `known_columns` key -- nothing may guess one."""
    asked = []

    class Index:
        def known_columns(self, table):
            asked.append(table)
            return []

    expansion = expand_select_expansion(Index(), "SELECT FROM jobcard", 6)
    assert asked == []
    assert expansion.text == " * FROM jobcard j WHERE "


def test_typing_never_resolves_an_expansion(qtbot):
    """§18.6's invariant: these are explicit gestures, not edit-signal work.

    `resolve_caret_context`/`analyze_from_items` cost hundreds of milliseconds
    on a large body, so a keystroke must not reach them.
    """
    calls = []
    panel = _ddl_panel(qtbot, text="", index=_schema())
    panel.editor.set_dynamic_expander(
        lambda text, pos: calls.append(pos) or None
    )
    panel.editor.setFocus()
    QTest.keyClicks(panel.editor, "SELECT FROM hr.jobcard")
    assert calls == []
