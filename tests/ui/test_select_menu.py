# tests/ui/test_select_menu.py
"""FQ-015 — the `Select` menu on the Editor menu bar, and the bug its move fixes.

The load-bearing tests here are the **wrong-document** ones. Before FQ-015 the two
block-selection commands were connected at menu-BUILD time to
`center_stage.xml_editor`'s bound methods, so Ctrl+Shift+B / Ctrl+Shift+A pressed
on a PHP tab, a DDL object tab or an FQ-006 draft tab moved the selection inside
the **Raw XML** document — a document the user was not even looking at. Every
"…acts on the active tab, and Raw XML is untouched" test below is the assertion
that would have caught that, and it is written as a pair: the active editor's
selection changed AND the Raw XML editor's cursor did not move.
"""
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.ui.code_editor import CodeEditor
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef
from pgtp_editor.ui.main_window import MainWindow
from tests.ui._menu_helpers import action_labels, editor_menu_titles, find_action

_RAW_XML = (
    "<Project>\n"
    "  <Presentation><Pages>\n"
    '    <Page fileName="existing" tableName="pr.existing">\n'
    "      <ColumnPresentations/>\n"
    "    </Page>\n"
    "  </Pages></Presentation>\n"
    "</Project>\n"
)

_REF = DdlObjectRef(kind="function", schema="pr", name="recalc")
_SQL = "CREATE FUNCTION pr.recalc(a int) RETURNS int AS $$ SELECT (a + 1); $$;"
_PHP = "<?php echo strtoupper('shout');"


def _window(qtbot, tmp_path=None):
    settings = (
        QSettings(str(tmp_path / "w.ini"), QSettings.Format.IniFormat)
        if tmp_path is not None
        else None
    )
    window = MainWindow(settings=settings) if settings else MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_RAW_XML)
    return window


def _select_menu(window):
    menu = None
    for bar_menu in window.editor_menu_bar.findChildren(type(window._select_menu)):
        if bar_menu.title() == "Select":
            menu = bar_menu
    assert menu is not None
    return menu


def _raw_xml_state(window):
    """What must not change when a command acts on another tab: the Raw XML
    cursor position, anchor and text."""
    cursor = window.center_stage.xml_editor.textCursor()
    return (
        cursor.position(),
        cursor.anchor(),
        window.center_stage.xml_editor.toPlainText(),
    )


def _put_caret(editor, offset):
    cursor = editor.textCursor()
    cursor.setPosition(offset)
    editor.setTextCursor(cursor)


def _php_tab(window, tmp_path, text=_PHP):
    path = tmp_path / "thing.php"
    path.write_text(text, encoding="utf-8")
    return window._php_tabs.open_path(path)


def _ddl_object_tab(window, text=_SQL):
    window._on_ddl_edit_requested(_REF, text)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    assert panel is not None
    return panel


def _draft_tab(window):
    equipment = TableInfo(
        name="pr.equipment",
        kind="table",
        columns=[
            ColumnInfo("id", "integer", True, False, False, None),
            ColumnInfo("tag", "varchar(30)", False, False, True, None),
        ],
    )
    window._db_ui.last_schema = DatabaseSchema(tables={equipment.name: equipment})
    window._db_ui.on_create_requested("page", "pr.equipment")
    draft = window.center_stage.active_draft_fragment_tab()
    assert draft is not None
    return draft


# -- the menu itself ----------------------------------------------------------


def test_select_menu_sits_on_the_editor_bar_between_history_and_parsing(qtbot):
    window = _window(qtbot)
    titles = editor_menu_titles(window)
    # `Deployment` joined the bar as its fifth menu with FQ-020; `Select`'s
    # position between History and Parsing is what this test is about.
    assert titles == ["History", "Select", "Parsing", "Navigation", "Deployment"]
    # It is on the EDITOR bar, never the window bar.
    assert "Select" not in [
        menu.title() for menu in window.menuBar().findChildren(type(window._select_menu))
    ]


def test_select_menu_contents_and_order(qtbot):
    window = _window(qtbot)
    assert action_labels(_select_menu(window)) == [
        "Select All",
        "―",
        "Select Enclosing Block",
        "Select Parent Block",
    ]


def test_select_menu_shortcuts_are_the_three_unchanged_chords(qtbot):
    """§27: nothing is rebound. Ctrl+A is new to the MENU only — the widgets
    have always implemented it."""
    window = _window(qtbot)
    menu = _select_menu(window)
    assert find_action(menu, "Select All").shortcut().toString() == "Ctrl+A"
    assert (
        find_action(menu, "Select Enclosing Block").shortcut().toString()
        == "Ctrl+Shift+B"
    )
    assert (
        find_action(menu, "Select Parent Block").shortcut().toString() == "Ctrl+Shift+A"
    )
    assert find_action(menu, "Select All") is window._select_all_action
    assert find_action(menu, "Select Enclosing Block") is window._select_enclosing_action
    assert find_action(menu, "Select Parent Block") is window._select_parent_action


# -- Select All ---------------------------------------------------------------


def test_select_all_action_selects_the_whole_active_document(qtbot):
    window = _window(qtbot)
    window._select_all_action.trigger()
    assert (
        window.center_stage.xml_editor.textCursor().selectedText().replace(" ", "\n")
        == _RAW_XML
    )


def test_select_all_action_follows_a_php_tab_and_leaves_raw_xml_alone(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    tab = _php_tab(window, tmp_path)
    before = _raw_xml_state(window)

    window._select_all_action.trigger()

    assert tab.editor.textCursor().selectedText() == _PHP
    assert _raw_xml_state(window) == before
    assert window.center_stage.xml_editor.textCursor().hasSelection() is False


def test_ctrl_a_really_selects_all_in_a_read_only_editor_of_either_family(qtbot):
    """FQ-015 open question 1, ANSWERED BY TEST rather than assumed.

    `setReadOnly(True)` keeps Qt's text-selectable interaction flag, so the
    widget's built-in Ctrl+A still selects — asserted as a REAL key press on a
    real read-only editor of each family (`XmlEditor` for Raw XML in Caption
    Mode, `CodeEditor` for the DDL Explorer buffer), shown and focused, which is
    the situation a user is in.

    Focus is load-bearing in the harness: a read-only `QPlainTextEdit` that never
    had focus ignores a synthesized Ctrl+A, while an editable one handles it
    either way. That is a Qt/QTest detail, not a property of the feature — hence
    show + setFocus rather than a weaker assertion."""
    from pgtp_editor.ui.xml_editor import XmlEditor

    for editor in (XmlEditor(), CodeEditor(language="sql")):
        qtbot.addWidget(editor)
        editor.setPlainText("alpha beta\ngamma")
        editor.setReadOnly(True)
        editor.show()
        QApplication.processEvents()
        editor.setFocus()
        QApplication.processEvents()

        qtbot.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)

        assert editor.textCursor().selectedText().replace(" ", "\n") == (
            "alpha beta\ngamma"
        ), type(editor).__name__


def test_select_all_reaches_the_read_only_ddl_explorer_buffer(qtbot, tmp_path):
    """The same answer at the app level for the DDL Explorer (§18.1: read-only by
    design). Not gated: the entry is live and selects the whole buffer."""
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    panel = stage.ddl_editor_panel
    panel.editor.setPlainText(_SQL)
    assert panel.editor.isReadOnly() is True
    stage.setTabVisible(stage.ddl_tab_index, True)
    stage.setCurrentIndex(stage.ddl_tab_index)
    assert window._find_ui.active_selection_editor() is panel.editor

    assert window._select_all_action.isEnabled() is True
    window._select_all_action.trigger()

    assert panel.editor.textCursor().selectedText() == _SQL


def test_ctrl_a_selects_all_in_raw_xml_while_caption_mode_holds_it_read_only(qtbot):
    """The second read-only editor from the same open question. Select All is
    deliberately NOT gated in Caption Mode (unlike Find/Replace, which that mode
    owns): selecting text mutates nothing."""
    window = _window(qtbot)
    window.center_stage.enter_caption_mode()
    # Caption Mode keeps Raw XML VISIBLE (it only makes it read-only), so the
    # user can click back into it -- which is where Ctrl+A has to keep working.
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)
    editor = window.center_stage.xml_editor
    assert editor.isReadOnly() is True
    window.show()
    QApplication.processEvents()
    editor.setFocus()
    QApplication.processEvents()

    qtbot.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)

    assert editor.textCursor().selectedText().replace(" ", "\n") == _RAW_XML
    # ...and the menu entry is live too, not disabled behind the mode.
    assert window._select_all_action.isEnabled() is True


# -- Select Enclosing Block: the wrong-document bug ---------------------------


def test_select_enclosing_block_in_raw_xml_selects_the_xml_element(qtbot):
    window = _window(qtbot)
    editor = window.center_stage.xml_editor
    _put_caret(editor, _RAW_XML.index("<ColumnPresentations/>") + 2)

    window._select_enclosing_action.trigger()

    assert (
        editor.textCursor().selectedText().replace(" ", "\n")
        == "<ColumnPresentations/>"
    )


def test_select_enclosing_block_on_a_php_tab_never_touches_raw_xml(qtbot, tmp_path):
    """THE regression test for FQ-015's bug: the chord used to select inside the
    Raw XML document while the user looked at a PHP tab."""
    window = _window(qtbot, tmp_path)
    tab = _php_tab(window, tmp_path)
    _put_caret(tab.editor, _PHP.index("'shout'"))
    before = _raw_xml_state(window)

    window._select_enclosing_action.trigger()

    # A CodeEditor's structural equivalent is the innermost bracket pair.
    assert tab.editor.textCursor().selectedText() == "'shout'"
    assert _raw_xml_state(window) == before


def test_select_enclosing_block_on_a_ddl_object_tab_never_touches_raw_xml(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)
    panel = _ddl_object_tab(window)
    _put_caret(panel.editor, _SQL.index("a + 1"))
    before = _raw_xml_state(window)

    window._select_enclosing_action.trigger()

    assert panel.editor.textCursor().selectedText() == "a + 1"
    assert _raw_xml_state(window) == before


def test_select_enclosing_block_on_a_draft_tab_selects_the_drafts_xml(qtbot):
    window = _window(qtbot)
    draft = _draft_tab(window)
    text = draft.toPlainText()
    _put_caret(draft.editor, text.index("<Page") + 2)
    before = _raw_xml_state(window)

    window._select_enclosing_action.trigger()

    assert draft.editor.textCursor().hasSelection() is True
    assert draft.editor.textCursor().selectedText().replace(" ", "\n").startswith(
        "<Page "
    )
    assert _raw_xml_state(window) == before


def test_select_enclosing_block_follows_the_edit_xsd_tab(qtbot):
    window = _window(qtbot)
    stage = window.center_stage
    # Seeding the XSD editor makes that lane dirty, and qtbot's teardown close
    # would then raise a modal "save your XSD?" question (§30: never let a test
    # reach an un-patched modal).
    window._xsd_ui.confirm_close = lambda: "discard"
    stage.xsd_editor.setPlainText("<xs:schema><xs:element/></xs:schema>")
    stage.setCurrentIndex(stage.xsd_tab_index)
    _put_caret(stage.xsd_editor, stage.xsd_editor.toPlainText().index("<xs:element/>") + 2)
    before = _raw_xml_state(window)

    window._select_enclosing_action.trigger()

    assert stage.xsd_editor.textCursor().selectedText() == "<xs:element/>"
    assert _raw_xml_state(window) == before


def test_select_enclosing_block_dispatch_picks_the_method_the_editor_has(qtbot, tmp_path):
    """The two families' methods are genuinely DIFFERENT (XML tag span vs bracket
    pair), so the dispatch resolves by capability, never by one name."""
    window = _window(qtbot, tmp_path)
    assert hasattr(window.center_stage.xml_editor, "select_enclosing_block")
    assert not hasattr(window.center_stage.xml_editor, "select_enclosing_brackets")
    tab = _php_tab(window, tmp_path)
    assert hasattr(tab.editor, "select_enclosing_brackets")
    assert not hasattr(tab.editor, "select_enclosing_block")


# -- Select Parent Block: XML-only, absent where it has no meaning ------------


def test_select_parent_block_in_raw_xml_walks_one_level_up(qtbot):
    window = _window(qtbot)
    editor = window.center_stage.xml_editor
    _put_caret(editor, _RAW_XML.index("<ColumnPresentations/>") + 2)

    window._select_parent_action.trigger()

    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected.startswith("<Page ") and selected.endswith("</Page>")


def test_select_parent_block_is_absent_on_code_editor_tabs(qtbot, tmp_path):
    """A bracket pair has no "one nesting level up" that means anything in SQL or
    PHP, so the entry is HIDDEN (the app's two-posture rule: present / absent) —
    which also drops Ctrl+Shift+A there, since Qt keeps a shortcut live only
    while its action is enabled AND visible."""
    window = _window(qtbot, tmp_path)
    assert window._select_parent_action.isVisible() is True

    panel = _ddl_object_tab(window)
    assert window.center_stage.currentWidget() is panel
    assert window._select_parent_action.isVisible() is False

    tab = _php_tab(window, tmp_path)
    assert window.center_stage.currentWidget() is tab
    assert window._select_parent_action.isVisible() is False

    stage = window.center_stage
    stage.setCurrentIndex(stage.ddl_tab_index)
    assert window._select_parent_action.isVisible() is False

    # ...and it comes back on an XML editor tab.
    stage.setCurrentIndex(stage.raw_xml_tab_index)
    assert window._select_parent_action.isVisible() is True


def test_select_parent_block_triggered_on_a_php_tab_is_a_no_op_not_raw_xml(
    qtbot, tmp_path
):
    """Second belt behind the visibility gate: a hidden action can still be
    triggered programmatically (or pinned to the toolbar), and when it is it must
    do NOTHING rather than reach into the Raw XML document."""
    window = _window(qtbot, tmp_path)
    tab = _php_tab(window, tmp_path)
    _put_caret(tab.editor, _PHP.index("'shout'"))
    before = _raw_xml_state(window)

    window._select_parent_action.trigger()

    assert tab.editor.textCursor().hasSelection() is False
    assert _raw_xml_state(window) == before


def test_the_ctrl_shift_a_chord_itself_is_live_on_xml_and_dead_on_a_php_tab(
    qtbot, tmp_path
):
    """The visibility gate's real consequence, driven by the KEY not the action:
    Qt keeps a shortcut live only while its action is enabled AND visible, so
    hiding the entry on a `CodeEditor` tab is also what makes Ctrl+Shift+A stop
    reaching the wrong document there."""
    window = _window(qtbot, tmp_path)
    editor = window.center_stage.xml_editor
    _put_caret(editor, _RAW_XML.index("<ColumnPresentations/>") + 2)
    fired = []
    window._select_parent_action.triggered.connect(lambda: fired.append(1))
    window.show()
    QApplication.processEvents()
    editor.setFocus()
    QApplication.processEvents()

    qtbot.keyClick(
        editor,
        Qt.Key.Key_A,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()

    assert fired == [1]
    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected.startswith("<Page ") and selected.endswith("</Page>")

    # Now a PHP tab: the entry is hidden, so the chord has no host at all.
    tab = _php_tab(window, tmp_path)
    tab.editor.setFocus()
    QApplication.processEvents()
    fired.clear()
    before = _raw_xml_state(window)

    qtbot.keyClick(
        tab.editor,
        Qt.Key.Key_A,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()

    assert fired == []
    assert _raw_xml_state(window) == before


# -- trigger-time dispatch ----------------------------------------------------


def test_active_selection_editor_matches_the_bookmark_dispatch_on_every_tab(
    qtbot, tmp_path
):
    """One question ("which editor is the user looking at?") must have one
    answer: `active_selection_editor` delegates to `active_bookmark_editor` so
    the two dispatches cannot drift apart."""
    window = _window(qtbot, tmp_path)
    find_ui = window._find_ui
    stage = window.center_stage

    assert find_ui.active_selection_editor() is stage.xml_editor

    stage.setCurrentIndex(stage.xsd_tab_index)
    assert find_ui.active_selection_editor() is stage.xsd_editor

    stage.setCurrentIndex(stage.ddl_tab_index)
    assert find_ui.active_selection_editor() is stage.ddl_editor_panel.editor

    panel = _ddl_object_tab(window)
    assert find_ui.active_selection_editor() is panel.editor

    tab = _php_tab(window, tmp_path)
    assert find_ui.active_selection_editor() is tab.editor

    for stage_index in (stage.raw_xml_tab_index,):
        stage.setCurrentIndex(stage_index)
    assert find_ui.active_selection_editor() is stage.xml_editor
    assert find_ui.active_selection_editor() is find_ui.active_bookmark_editor()


def test_no_selection_action_is_bound_to_a_widget_at_build_time(qtbot, tmp_path):
    """The shape of the original bug, pinned: the actions must not hold a
    reference to any editor's bound method. Switching tabs after the menu was
    built has to change where they act — asserted by acting on a tab that did not
    exist when the menu was built."""
    window = _window(qtbot, tmp_path)
    tab = _php_tab(window, tmp_path)  # created long after _build_select_menu
    _put_caret(tab.editor, _PHP.index("'shout'"))

    window._select_enclosing_action.trigger()
    window._select_all_action.trigger()

    assert tab.editor.textCursor().selectedText() == _PHP
    assert window.center_stage.xml_editor.textCursor().hasSelection() is False


# -- the duplicate Ctrl+Shift+B handler --------------------------------------


def test_ctrl_shift_b_on_a_focused_code_editor_is_handled_once(qtbot, tmp_path):
    """FQ-015 trap 1. `CodeEditor.keyPressEvent` ALSO handles Ctrl+Shift+B, so
    one chord has two handlers. The menu action WINS: Qt's shortcut map consumes
    the key event before it reaches the focused widget, so the editor-side
    handler does not also run. Both paths now resolve to the SAME editor anyway,
    and the operation is idempotent, so a double delivery is harmless — asserted
    below so a future Qt/platform change cannot turn it into a bug."""
    window = _window(qtbot, tmp_path)
    tab = _php_tab(window, tmp_path)
    window.show()
    QApplication.processEvents()
    tab.editor.setFocus()
    QApplication.processEvents()
    _put_caret(tab.editor, _PHP.index("'shout'"))

    calls = []
    original = tab.editor.select_enclosing_brackets

    def counted():
        calls.append(1)
        original()

    tab.editor.select_enclosing_brackets = counted

    qtbot.keyClick(
        tab.editor,
        Qt.Key.Key_B,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()

    assert len(calls) == 1
    assert tab.editor.textCursor().selectedText() == "'shout'"
    # Idempotent: a second application selects the same span, so even if both
    # handlers ever fired the result would be identical.
    original()
    assert tab.editor.textCursor().selectedText() == "'shout'"


def test_the_editor_side_ctrl_shift_b_handler_is_retained_for_menuless_hosts(qtbot):
    """Why the duplicate is KEPT rather than deleted: a bare `CodeEditor` (as in
    `CodeEditorDialog`) has no Editor menu bar, so `keyPressEvent` is the only
    host for the chord there — and it is the reliable path under the offscreen
    test platform, where QShortcut activation is not guaranteed."""
    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    editor.setPlainText(_SQL)
    _put_caret(editor, _SQL.index("a + 1"))

    qtbot.keyClick(
        editor,
        Qt.Key.Key_B,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )

    assert editor.textCursor().selectedText() == "a + 1"


def test_caret_lands_at_the_start_of_every_structural_selection(qtbot):
    """Unchanged contract, re-asserted through the menu: anchor at the END, caret
    at the START, so the view scrolls to the block's beginning and repeated
    Select Parent presses keep walking up."""
    window = _window(qtbot)
    editor = window.center_stage.xml_editor
    _put_caret(editor, _RAW_XML.index("<ColumnPresentations/>") + 2)

    window._select_enclosing_action.trigger()
    cursor = editor.textCursor()
    assert cursor.position() == cursor.selectionStart()

    window._select_parent_action.trigger()
    cursor = editor.textCursor()
    assert cursor.position() == cursor.selectionStart()
    assert isinstance(cursor, QTextCursor)
