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
from PySide6.QtGui import QKeySequence, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.ui.code_editor import CodeEditor, CodeEditorDialog
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
        "Expand Selection",
        "Shrink Selection",
        "―",
        "Sticky Selection",
        "Line Selection",
    ]


def test_select_menu_shortcuts_are_the_three_unchanged_chords(qtbot):
    """§27: nothing is rebound. Ctrl+A is new to the MENU only — the widgets
    have always implemented it.

    FQ-034 added a fourth entry and still rebound nothing: `Expand Selection`
    keeps `Select Parent Block`'s `Ctrl+Shift+A`, and `Shrink Selection` carries
    **no shortcut at all** (see the next test for why that is the design).
    """
    window = _window(qtbot)
    menu = _select_menu(window)
    assert find_action(menu, "Select All").shortcut().toString() == "Ctrl+A"
    assert (
        find_action(menu, "Select Enclosing Block").shortcut().toString()
        == "Ctrl+Shift+B"
    )
    assert (
        find_action(menu, "Expand Selection").shortcut().toString() == "Ctrl+Shift+A"
    )
    assert find_action(menu, "Select All") is window._select_all_action
    assert find_action(menu, "Select Enclosing Block") is window._select_enclosing_action
    assert find_action(menu, "Expand Selection") is window._expand_selection_action
    assert find_action(menu, "Shrink Selection") is window._shrink_selection_action


def test_shrink_selection_action_carries_no_shortcut_at_all(qtbot):
    """FQ-034's DEC-012 reconciliation, pinned.

    `Ctrl+Shift+Z` is claimed by all six editing surfaces
    (`CLAIMED_NOT_UNDO_REDO`), which accept its `ShortcutOverride` so Qt's native
    redo cannot fire — a suppression DEC-014 mandates. A window `QAction` bound to
    the same chord would be starved by exactly that override, so shrink's keyboard
    host is the per-surface claim and the action is the command form only. The
    chord must also stay RESERVED, so `Customize Shortcuts…` cannot hand it to
    anything else.
    """
    from pgtp_editor.ui.shortcut_registry import (
        CLAIMED_NOT_UNDO_REDO,
        EDITOR_CHORDS,
        RESERVED_SEQUENCES,
    )

    window = _window(qtbot)
    assert window._shrink_selection_action.shortcut().isEmpty()
    assert EDITOR_CHORDS["Ctrl+Shift+Z"] == CLAIMED_NOT_UNDO_REDO
    assert "Ctrl+Shift+Z" in RESERVED_SEQUENCES


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


# -- Expand / Shrink Selection: present where there is structure to climb -----


def test_expand_selection_in_raw_xml_walks_one_level_up(qtbot):
    """The XML family's grow is UNCHANGED by FQ-034 -- `select_parent_block` is
    already one structural level per press, so the rename is all that reached it."""
    window = _window(qtbot)
    editor = window.center_stage.xml_editor
    _put_caret(editor, _RAW_XML.index("<ColumnPresentations/>") + 2)

    window._expand_selection_action.trigger()

    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected.startswith("<Page ") and selected.endswith("</Page>")


def test_expand_selection_is_absent_only_where_there_is_no_structure(qtbot, tmp_path):
    """FQ-034 rescoped this gate: before, the entry was hidden on EVERY
    `CodeEditor` tab; now it is present wherever the editor answers
    `supports_structural_expansion()` -- every SQL editor and every XML editor --
    and hidden on PHP/JS, which have no plpgsql structure to climb. Hidden, never
    greyed, which is also what drops Ctrl+Shift+A there.
    """
    window = _window(qtbot, tmp_path)
    assert window._expand_selection_action.isVisible() is True

    panel = _ddl_object_tab(window)
    assert window.center_stage.currentWidget() is panel
    assert window._expand_selection_action.isVisible() is True

    tab = _php_tab(window, tmp_path)
    assert window.center_stage.currentWidget() is tab
    assert window._expand_selection_action.isVisible() is False

    stage = window.center_stage
    stage.setCurrentIndex(stage.ddl_tab_index)
    assert window._expand_selection_action.isVisible() is True

    stage.setCurrentIndex(stage.raw_xml_tab_index)
    assert window._expand_selection_action.isVisible() is True


def test_shrink_selection_is_hidden_on_xml_and_php_and_shown_on_sql(qtbot, tmp_path):
    """Shrink is SQL-only, and XML's absence is a scope decision with a reason
    (§8): XML's grow is stateless and re-derivable, so shrink there would mean
    giving `XmlEditor` the expansion stack too. So the gate is `hasattr` (a class
    fact -- `XmlEditor` has no such method) AND the per-instance language
    predicate, which is what keeps it hidden on a PHP `CodeEditor` that DOES have
    the method.
    """
    window = _window(qtbot, tmp_path)
    assert not hasattr(window.center_stage.xml_editor, "shrink_structural_selection")
    assert window._shrink_selection_action.isVisible() is False

    panel = _ddl_object_tab(window)
    assert hasattr(panel.editor, "shrink_structural_selection")
    assert window._shrink_selection_action.isVisible() is True

    tab = _php_tab(window, tmp_path)
    assert hasattr(tab.editor, "shrink_structural_selection")  # the method exists...
    assert tab.editor.supports_structural_expansion() is False  # ...the language does not
    assert window._shrink_selection_action.isVisible() is False

    stage = window.center_stage
    stage.setCurrentIndex(stage.ddl_tab_index)  # the read-only DDL Explorer buffer
    assert window._shrink_selection_action.isVisible() is True


def test_the_sql_ladder_is_repeatable_and_shrink_walks_back_down(qtbot, tmp_path):
    """The whole feature end to end on a real tab: press grow four times, then
    shrink three times, landing back exactly where each press came from."""
    window = _window(qtbot, tmp_path)
    panel = _ddl_object_tab(window)
    editor = panel.editor
    editor.setPlainText("select a, coalesce(b, c) from t where a = 1;")
    _put_caret(editor, editor.toPlainText().index("b,"))

    grown = []
    for _ in range(4):
        window._expand_selection_action.trigger()
        grown.append(editor.textCursor().selectedText())
    assert grown == ["b", "b, c", "(b, c)", "select a, coalesce(b, c)"]

    for expected in reversed(grown[:-1]):
        window._shrink_selection_action.trigger()
        assert editor.textCursor().selectedText() == expected


def test_expand_selection_triggered_on_a_php_tab_is_a_no_op_not_raw_xml(
    qtbot, tmp_path
):
    """Second belt behind the visibility gate: a hidden action can still be
    triggered programmatically (or pinned to the toolbar), and when it is it must
    do NOTHING rather than reach into the Raw XML document."""
    window = _window(qtbot, tmp_path)
    tab = _php_tab(window, tmp_path)
    _put_caret(tab.editor, _PHP.index("'shout'"))
    before = _raw_xml_state(window)

    window._expand_selection_action.trigger()
    window._shrink_selection_action.trigger()

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
    window._expand_selection_action.triggered.connect(lambda: fired.append(1))
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


# -- Ctrl+Shift+B has ONE host per window (BUG-046) --------------------------
#
# The chord used to be handled twice: this menu QAction *and* an unconditional
# branch in `CodeEditor.keyPressEvent`, justified by "QShortcut activation is not
# guaranteed under the offscreen platform". That premise is false — what fails is
# key delivery to a widget whose top level was never `show()`n, and
# `qtbot.keyClick(widget, …)`, which posts straight at the widget. Every test
# below therefore `show()`s its window and delivers the key at
# `window.windowHandle()`, which is what a real key press does.


def _press_ctrl_shift_b(window):
    QTest.keyClick(
        window.windowHandle(),
        Qt.Key.Key_B,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()


def test_ctrl_shift_b_on_a_focused_code_editor_is_handled_once(qtbot, tmp_path):
    """The menu action is the ONLY host, and this counts both candidate hosts to
    prove it: the action's own `triggered` (the winner) and the editor method
    both handlers used to land on (the total). One each — the previous version of
    this test counted only the total, so it could not tell the two apart and
    "proved" the duplicate harmless."""
    window = _window(qtbot, tmp_path)
    tab = _php_tab(window, tmp_path)
    window.show()
    QApplication.processEvents()
    tab.editor.setFocus()
    QApplication.processEvents()
    _put_caret(tab.editor, _PHP.index("'shout'"))

    triggered = []
    window._select_enclosing_action.triggered.connect(lambda: triggered.append(1))
    calls = []
    original = tab.editor.select_enclosing_brackets

    def counted():
        calls.append(1)
        original()

    tab.editor.select_enclosing_brackets = counted

    _press_ctrl_shift_b(window)

    assert triggered == [1]  # the QAction answered
    assert calls == [1]  # exactly once, so no second host ran
    assert tab.editor.textCursor().selectedText() == "'shout'"


def test_the_code_editor_dialog_answers_ctrl_shift_b_through_its_own_shortcut(qtbot):
    """Claim A of the retired justification, kept as a real host: the menu-less
    `CodeEditorDialog` has no Editor menu bar, so it owns the chord itself
    (BUG-046) — driven here by a real key press, not by calling the slot."""
    dialog = CodeEditorDialog("sql", "handler")
    qtbot.addWidget(dialog)
    dialog.set_code(_SQL)
    dialog.show()
    QApplication.processEvents()
    _put_caret(dialog._editor, _SQL.index("a + 1"))
    dialog._editor.setFocus()
    QApplication.processEvents()

    _press_ctrl_shift_b(dialog)

    assert dialog._editor.textCursor().selectedText() == "a + 1"


def test_the_dialogs_shortcut_is_retained_on_the_dialog(qtbot):
    """The GC failure mode, pinned: a QShortcut whose only Python reference is
    dropped is collected and stops working."""
    dialog = CodeEditorDialog("sql", "handler")
    qtbot.addWidget(dialog)

    assert dialog._select_enclosing_shortcut is not None
    assert dialog._select_enclosing_shortcut.key() == QKeySequence("Ctrl+Shift+B")


def test_a_bare_code_editor_no_longer_answers_ctrl_shift_b_itself(qtbot):
    """The negative half: with no dialog and no window action there is nothing
    to answer the chord, because `CodeEditor.keyPressEvent` no longer does. This
    is what pins the deleted branch as deleted."""
    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    editor.setPlainText(_SQL)
    editor.show()
    QApplication.processEvents()
    _put_caret(editor, _SQL.index("a + 1"))
    editor.setFocus()
    QApplication.processEvents()

    _press_ctrl_shift_b(editor)

    assert editor.textCursor().hasSelection() is False
    # The operation itself is untouched — it is purely a slot now.
    editor.select_enclosing_brackets()
    assert editor.textCursor().selectedText() == "a + 1"


def test_ctrl_shift_b_stays_rebindable_because_it_is_a_menu_command(qtbot):
    """The point of the ruling: the chord is hosted like every other shortcut,
    so `Customize Shortcuts…` may move it. It must NOT be reserved."""
    from pgtp_editor.ui.shortcut_registry import RESERVED_SEQUENCES

    assert "Ctrl+Shift+B" not in RESERVED_SEQUENCES


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

    window._expand_selection_action.trigger()
    cursor = editor.textCursor()
    assert cursor.position() == cursor.selectionStart()
    assert isinstance(cursor, QTextCursor)


# -- FQ-260812000331: the two sticky-selection command forms ------------------


def test_the_sticky_entries_carry_NO_shortcut_because_v_and_V_are_the_host(qtbot):
    """DEC-012: a command with a command form has exactly ONE keyboard host, and
    for these two it is the bare `v` / `V` inside the Command-mode grammar. A
    chord here would be a second host, so both actions must be keyless — and
    nothing goes into `RESERVED_SEQUENCES`, because no new chord exists."""
    from pgtp_editor.ui.shortcut_registry import RESERVED_SEQUENCES

    window = _window(qtbot)
    menu = _select_menu(window)
    for label in ("Sticky Selection", "Line Selection"):
        assert find_action(menu, label).shortcut().toString() == ""
    assert "V" not in RESERVED_SEQUENCES


def test_the_sticky_entries_are_checkable_toggles(qtbot):
    window = _window(qtbot)
    assert window._sticky_selection_action.isCheckable()
    assert window._line_selection_action.isCheckable()


def test_sticky_selection_acts_on_the_editor_resolved_at_TRIGGER_time(
    qtbot, tmp_path
):
    """The whole point of this menu's dispatch: a PHP tab in front means the PHP
    editor gets the sticky state and the Raw XML buffer is untouched."""
    from pgtp_editor.ui import vim_mode

    window = _window(qtbot, tmp_path)
    tab = _php_tab(window, tmp_path)
    before = _raw_xml_state(window)

    window._sticky_selection_action.trigger()

    assert tab.editor.sticky_selection_mode == vim_mode.STICKY_CHARACTER
    assert window.center_stage.xml_editor.sticky_selection_mode is None
    assert _raw_xml_state(window) == before


def test_line_selection_acts_on_the_editor_resolved_at_TRIGGER_time(qtbot):
    from pgtp_editor.ui import vim_mode

    window = _window(qtbot)
    panel = _ddl_object_tab(window)
    before = _raw_xml_state(window)

    window._line_selection_action.trigger()

    assert panel.editor.sticky_selection_mode == vim_mode.STICKY_LINE
    assert window.center_stage.xml_editor.sticky_selection_mode is None
    assert _raw_xml_state(window) == before


def test_triggering_twice_toggles_the_state_back_off(qtbot):
    window = _window(qtbot)
    window._sticky_selection_action.trigger()
    assert window.center_stage.xml_editor.sticky_selection_mode is not None
    window._sticky_selection_action.trigger()
    assert window.center_stage.xml_editor.sticky_selection_mode is None


def test_the_menu_command_and_v_share_ONE_state(qtbot):
    """`v` writes the same flag the menu entry does, so the check marks must
    follow a keystroke nothing on the menu knows about."""
    from pgtp_editor.ui import vim_mode

    window = _window(qtbot)
    window.center_stage.xml_editor.set_sticky_selection(vim_mode.STICKY_LINE)

    window._refresh_sticky_selection_actions()

    assert window._line_selection_action.isChecked()
    assert not window._sticky_selection_action.isChecked()


def test_both_entries_are_HIDDEN_on_a_read_only_editor(qtbot):
    """§8: on a read-only editor the whole editing-mode layer is inactive, so
    the sticky key handling refuses to answer. An entry that toggles a flag
    nothing reads is worse than an absent one — hidden, never greyed."""
    window = _window(qtbot)
    window.center_stage.xml_editor.setReadOnly(True)

    window._refresh_sticky_selection_actions()

    assert not window._sticky_selection_action.isVisible()
    assert not window._line_selection_action.isVisible()

    window.center_stage.xml_editor.setReadOnly(False)
    window._refresh_sticky_selection_actions()
    assert window._sticky_selection_action.isVisible()


def test_the_slot_refuses_on_a_read_only_editor_even_when_triggered_directly(
    qtbot,
):
    """The second belt, for a pinned toolbar button or a programmatic trigger
    that never consults `isVisible()`."""
    window = _window(qtbot)
    window.center_stage.xml_editor.setReadOnly(True)

    window._sticky_selection_action.trigger()
    window._line_selection_action.trigger()

    assert window.center_stage.xml_editor.sticky_selection_mode is None
