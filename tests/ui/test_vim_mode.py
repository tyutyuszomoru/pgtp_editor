"""FQ-032's editing-mode layer: **Edit mode** and **Command mode** (§8).

The two labels are the owner's and the whole vocabulary. The word *"normal"* is
never written -- it collides with vim's own NORMAL and would make every sentence
ambiguous about which vocabulary it speaks.

The file is organised around what actually breaks in this class of feature:

* **the way out.** Six exit triggers, all funnelling into one reset path, and
  `test_every_one_of_the_six_exit_triggers_restores_replace_focus` is the test the
  spec requires by name -- because since `DEC-260810193638` a mode left set is a
  **silently broken `Ctrl+R`**;
* **`Esc` precedence**, which now has six legitimate answers;
* **the three freed chords' decline**, asserted to live in ONE place;
* **the mode indicator**, including `CodeEditorDialog`'s chrome, which is a
  precondition of the ruling rather than a nicety.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from pgtp_editor.ui import vim_mode
from pgtp_editor.ui.code_editor import (
    DELETE_CHARACTER,
    DELETE_LINE,
    DELETE_TO_END_OF_LINE,
    PASTE,
    CodeEditor,
    CodeEditorDialog,
    apply_editor_operation,
)
from pgtp_editor.ui.find_replace_bar import FindReplaceBar, install_focus_shortcuts
from pgtp_editor.ui.mode_indicator import (
    EDITING_COMMAND,
    EDITING_EDIT,
    ModeIndicator,
    mode_text,
)
from pgtp_editor.ui.vim_mode import (
    NO_BACKWARD_SEARCH,
    PALETTE_UNAVAILABLE,
    palette_matches,
)
from pgtp_editor.ui.xml_editor import XmlEditor
from pgtp_editor.vim import REDO_KEY


# ---------------------------------------------------------------------------
# Fixtures: the two families, and a host that owns an editor plus its Find bar
# (the shape `install_focus_shortcuts` requires, and therefore the shape the
# `Ctrl+R` assertions need).
# ---------------------------------------------------------------------------

TEXT = "alpha beta gamma\n    second line here\n\nfourth line\n"


class _Host(QWidget):
    """A tab container owning an editor and its `FindReplaceBar` -- exactly what
    the six real surfaces are, from `Ctrl+F`/`Ctrl+R`'s point of view."""

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        editor.setParent(self)
        self.find_replace_bar = FindReplaceBar(editor)
        layout = QVBoxLayout(self)
        layout.addWidget(editor)
        layout.addWidget(self.find_replace_bar)
        self._shortcuts = install_focus_shortcuts(self, self.find_replace_bar)


@pytest.fixture
def code(qtbot):
    editor = CodeEditor("sql")
    qtbot.addWidget(editor)
    editor.setPlainText(TEXT)
    editor.show()
    return editor


@pytest.fixture
def xml(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(TEXT)
    editor.show()
    return editor


@pytest.fixture(params=["code", "xml"])
def editor(request, qtbot):
    """Both families, because the whole design is ONE engine for both."""
    made = CodeEditor("sql") if request.param == "code" else XmlEditor()
    qtbot.addWidget(made)
    made.setPlainText(TEXT)
    made.show()
    return made


@pytest.fixture
def hosted(qtbot, editor):
    """The editor inside a host that owns its Find bar, shown so `QShortcut`s
    actually fire (offscreen they do -- the requirement is that the top level has
    been `show()`n)."""
    host = _Host(editor)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    editor.setFocus()
    QApplication.processEvents()
    return host


def press(editor, text):
    """Send `text` to `editor` one bare key at a time, as the user would."""
    for character in text:
        QTest.keyClicks(editor, character)


def escape(editor):
    QTest.keyClick(editor, Qt.Key.Key_Escape)


def caret(editor) -> int:
    return editor.textCursor().position()


def place(editor, position: int) -> None:
    cursor = editor.textCursor()
    cursor.setPosition(position)
    editor.setTextCursor(cursor)


# ---------------------------------------------------------------------------
# The mode model
# ---------------------------------------------------------------------------

def test_every_editor_starts_in_edit_mode(editor):
    """No setting is read, nothing is restored, and there is no map of which
    editor was in Command mode."""
    assert not editor.in_command_mode
    assert editor.editing_mode_label() == EDITING_EDIT


def test_escape_in_an_editable_editor_enters_command_mode(editor):
    escape(editor)
    assert editor.in_command_mode
    assert editor.editing_mode_label() == EDITING_COMMAND


def test_in_command_mode_letters_no_longer_type(editor):
    escape(editor)
    before = editor.toPlainText()
    press(editor, "hjkl")
    assert editor.toPlainText() == before


def test_the_plain_edit_mode_editor_GAINS_NOTHING(editor):
    """The sentence that makes this a specification rather than an addition: every
    advanced operation lives only in Command mode, so no invented parallel keymap
    ever appears in Edit mode."""
    place(editor, 0)
    press(editor, "dd")
    assert editor.toPlainText().startswith("dd")


def test_the_layer_is_inactive_ENTIRELY_on_a_read_only_editor(editor):
    """`Esc` does nothing at all -- no hint, no journal line, no refusal. That
    deletes the whole motion-vs-mutation-in-a-read-only-buffer problem."""
    editor.setReadOnly(True)
    hints = []
    editor.hint_shown.connect(hints.append)
    escape(editor)
    assert not editor.in_command_mode
    assert hints == []


def test_the_read_only_predicate_is_asked_at_the_KEYSTROKE(editor):
    """Never cached at construction, because Caption Mode and Compare/Merge flip
    `setReadOnly` at runtime."""
    escape(editor)
    assert editor.in_command_mode
    editor.setReadOnly(False)
    editor.setReadOnly(True)
    escape(editor)
    assert not editor.in_command_mode


def test_the_indicator_segment_is_ABSENT_on_a_read_only_editor(editor):
    editor.setReadOnly(True)
    assert editor.editing_mode_label() is None


def test_the_mouse_never_changes_the_editing_mode(editor):
    """A click that moved the mode would make the indicator lie about a state the
    user did not ask to leave."""
    escape(editor)
    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton)
    assert editor.in_command_mode


def test_command_mode_is_PER_EDITOR_and_two_editors_are_independent(qtbot):
    first, second = CodeEditor("sql"), CodeEditor("sql")
    qtbot.addWidget(first)
    qtbot.addWidget(second)
    first.show()
    second.show()
    escape(first)
    assert first.in_command_mode
    assert not second.in_command_mode


def test_nothing_about_the_mode_is_persisted(qtbot):
    """No QSettings key, no toggle, no menu entry, no toolbar button -- there is
    nothing to pin and nothing to persist."""
    editor = CodeEditor("sql")
    qtbot.addWidget(editor)
    escape(editor)
    replacement = CodeEditor("sql")
    qtbot.addWidget(replacement)
    assert not replacement.in_command_mode


# ---------------------------------------------------------------------------
# THE WAY OUT -- six triggers, one reset path
# ---------------------------------------------------------------------------

EXIT_TRIGGERS = {
    # 1. an insert-entry command
    "insert-entry": lambda editor: press(editor, "i"),
    # 2. a `c{motion}` operator, which lands in Edit mode by definition
    "change-operator": lambda editor: press(editor, "cw"),
    # 3. focus loss
    "focus-loss": lambda editor: editor.clearFocus(),
    # 4. the editor becoming read-only under a Command-mode caret
    "becomes-read-only": lambda editor: editor.setReadOnly(True),
    # 5. a document swap
    "document-swap": lambda editor: editor.setPlainText("replaced\n"),
    # 6. a `:` command that changes focus (mechanically 3, and asserted anyway)
    "palette-focus-change": lambda editor: (
        editor._vim_open_palette(),
        editor._vim_palette_accepted("?nothing"),
        editor.clearFocus(),
    ),
}


@pytest.mark.parametrize("trigger", sorted(EXIT_TRIGGERS))
def test_every_one_of_the_six_exit_triggers_leaves_command_mode(editor, trigger):
    escape(editor)
    assert editor.in_command_mode
    EXIT_TRIGGERS[trigger](editor)
    assert not editor.in_command_mode, trigger


@pytest.mark.parametrize("trigger", sorted(EXIT_TRIGGERS))
def test_every_one_of_the_six_exit_triggers_restores_replace_focus(
    qtbot, hosted, editor, trigger
):
    """**The test the spec requires by name.**

    While Command mode holds, `Ctrl+R` is redo and Replace-focus is DEAD on that
    editor. If the mode is ever left set -- a missed `focusOutEvent`, a read-only
    transition that forgot to reset, a document swap -- `Ctrl+R` stays broken with
    nothing on screen saying why except the indicator. The six triggers funnelling
    into `_exit_command_mode()` are what make that unreachable, so every one of
    them is asserted to restore the chord.
    """
    escape(editor)
    assert editor.in_command_mode
    EXIT_TRIGGERS[trigger](editor)
    assert not editor.in_command_mode, trigger

    # With the mode gone, the editor no longer claims `Ctrl+R`'s ShortcutOverride,
    # so the `QShortcut` reaches the bar again.
    assert not _claims_ctrl_r(editor), trigger
    editor.setReadOnly(False)
    editor.setFocus()
    QApplication.processEvents()
    QTest.keyClick(editor, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    focused = QApplication.focusWidget()
    assert focused is not editor, trigger
    assert hosted.find_replace_bar.isAncestorOf(focused), trigger


def _claims_ctrl_r(editor) -> bool:
    """Whether `editor` accepts `Ctrl+R`'s `ShortcutOverride` -- i.e. whether it
    is taking the chord away from the Replace field."""
    event = QKeyEvent(
        QEvent.Type.ShortcutOverride,
        Qt.Key.Key_R,
        Qt.KeyboardModifier.ControlModifier,
    )
    handled = editor.event(event)
    return bool(handled and event.isAccepted())


def test_there_is_exactly_one_reset_path_and_it_is_idempotent(editor):
    escape(editor)
    assert editor._exit_command_mode() is True
    assert editor._exit_command_mode() is False
    assert not editor.in_command_mode


def test_the_reset_path_discards_pending_command_state(editor):
    escape(editor)
    press(editor, "42d")
    assert editor._vim_grammar.is_pending
    editor.clearFocus()
    assert not editor._vim_grammar.is_pending


def test_refocusing_an_editor_NEVER_returns_it_to_command_mode(editor):
    escape(editor)
    editor.clearFocus()
    editor.setFocus()
    assert not editor.in_command_mode


def test_the_completion_popup_taking_focus_is_just_a_focus_loss(xml):
    """One mechanism, not a special case. Reaching the sequence at all requires
    starting from Edit mode (`Ctrl+Space` is not a Command-mode command), where
    there is nothing to drop -- which is exactly why it is harmless."""
    escape(xml)
    popup = xml._ensure_completion_popup()
    popup.show()
    popup.setFocus()
    xml.clearFocus()
    assert not xml.in_command_mode


# ---------------------------------------------------------------------------
# `Esc` precedence -- six meanings, stated once
# ---------------------------------------------------------------------------

def test_tab_stop_mode_beats_command_mode_entry(code):
    """Row 3 before row 4: a template walk in progress owns `Esc`, and Command
    mode must NOT also be entered by the same key press."""
    code.setPlainText("case")
    place(code, 4)
    assert code.expand_snippet_at_caret()
    assert code.in_tab_stop_mode
    escape(code)
    assert not code.in_tab_stop_mode
    assert not code.in_command_mode, "the walk's Esc must not also enter Command mode"
    # And the NEXT Esc, with no walk in progress, does enter Command mode.
    escape(code)
    assert code.in_command_mode


def test_escape_in_command_mode_discards_pending_state_and_STAYS(editor):
    """Row 4': `Esc` never leaves the mode."""
    escape(editor)
    press(editor, "42")
    assert editor._vim_grammar.is_pending
    escape(editor)
    assert editor.in_command_mode
    assert not editor._vim_grammar.is_pending


def test_escape_on_a_read_only_editor_answers_NOTHING(editor):
    editor.setReadOnly(True)
    refusals = []
    editor.expansion_refused.connect(refusals.append)
    escape(editor)
    assert refusals == []
    assert not editor.in_command_mode


def test_escape_is_still_reserved_and_its_reason_names_command_mode_entry():
    from pgtp_editor.ui.shortcut_registry import RESERVED_SEQUENCES

    assert "Escape" in RESERVED_SEQUENCES
    assert "Command-mode entry" in RESERVED_SEQUENCES["Escape"]


def test_ctrl_r_reason_states_BOTH_of_its_meanings():
    """A user refused the chord is owed the true reason, and *"focuses the Replace
    field"* alone is now only half of it."""
    from pgtp_editor.ui.shortcut_registry import RESERVED_SEQUENCES

    reason = RESERVED_SEQUENCES["Ctrl+R"]
    assert "Replace" in reason
    assert "redo" in reason
    assert "Command mode" in reason


def test_the_reserved_set_gains_no_member(qtbot):
    """Every chord this feature claims was ALREADY reserved, so the ledger test's
    set equality does not move."""
    from pgtp_editor.ui.shortcut_registry import RESERVED_SEQUENCES

    for sequence in ("Escape", "Ctrl+R", "Ctrl+D", "Ctrl+K", "Ctrl+U"):
        assert sequence in RESERVED_SEQUENCES


# ---------------------------------------------------------------------------
# `Ctrl+R` -- the app's FIRST mode-conditional chord
# ---------------------------------------------------------------------------

def test_edit_mode_does_not_claim_ctrl_r(editor):
    assert not _claims_ctrl_r(editor)


def test_command_mode_claims_ctrl_r_through_the_shortcut_override_path(editor):
    """The only way Command mode can answer the chord: a `QShortcut` outranks a
    widget's `keyPressEvent`."""
    escape(editor)
    assert _claims_ctrl_r(editor)


def test_ctrl_r_in_edit_mode_still_focuses_the_replace_field(hosted, editor):
    QTest.keyClick(editor, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    focused = QApplication.focusWidget()
    assert hosted.find_replace_bar.isAncestorOf(focused)


def test_ctrl_r_in_command_mode_is_redo_on_the_code_family(code):
    code.setPlainText("")
    QTest.keyClicks(code, "abc")
    code.undo()
    assert "abc" not in code.toPlainText()
    escape(code)
    QTest.keyClick(code, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
    assert "abc" in code.toPlainText()


def test_undo_and_redo_route_to_the_XML_surfaces_OWN_answer(xml):
    """`u` calls the same thing `Ctrl+Z` calls at that surface -- for `XmlEditor`
    the window's snapshot history, never `QPlainTextEdit.undo()` (which is `F14`'s
    recorded defect)."""
    undos, redos = [], []
    xml.undo_requested.connect(lambda: undos.append(1))
    xml.redo_requested.connect(lambda: redos.append(1))
    escape(xml)
    press(xml, "u")
    QTest.keyClick(xml, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
    assert undos == [1]
    assert redos == [1]


def test_u_on_the_code_family_uses_its_own_stack_which_IS_that_surfaces_answer(code):
    code.setPlainText("")
    QTest.keyClicks(code, "abc")
    escape(code)
    press(code, "u")
    assert "abc" not in code.toPlainText()


def test_u_is_a_bare_letter_and_gets_no_chord_row():
    from pgtp_editor.ui.shortcut_registry import EDITOR_CHORDS, RESERVED_SEQUENCES

    assert "U" not in EDITOR_CHORDS
    assert "U" not in RESERVED_SEQUENCES


# ---------------------------------------------------------------------------
# `Ctrl+D` / `Ctrl+K` / `Ctrl+U` -- freed, consumed, inert; declined in ONE place
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "operation", [DELETE_CHARACTER, DELETE_TO_END_OF_LINE, DELETE_LINE]
)
def test_command_mode_declines_the_three_freed_operations(editor, operation):
    escape(editor)
    before = editor.toPlainText()
    assert apply_editor_operation(editor, operation) is False
    assert editor.toPlainText() == before


@pytest.mark.parametrize(
    "operation", [DELETE_CHARACTER, DELETE_TO_END_OF_LINE, DELETE_LINE]
)
def test_EDIT_mode_is_unchanged_for_all_three(editor, operation):
    """They remain bound, reserved and app-implemented at all six surfaces."""
    place(editor, 0)
    assert apply_editor_operation(editor, operation) is True


def test_PASTE_is_NOT_affected_the_ruling_freed_exactly_three(editor):
    QApplication.clipboard().setText("pasted")
    escape(editor)
    place(editor, 0)
    assert apply_editor_operation(editor, PASTE) is True
    assert editor.toPlainText().startswith("pasted")


def test_the_decline_lives_in_apply_editor_operation_and_nowhere_else():
    """Six copies of a mode test is six chances to drift, which is the argument
    that put those chords in one function to begin with. The predicate is one
    module-level helper in `code_editor`, and no surface re-implements it."""
    import inspect
    from pathlib import Path

    from pgtp_editor.ui import code_editor

    source = inspect.getsource(code_editor._command_mode_declines)
    assert "in_command_mode" in source

    ui_dir = Path(code_editor.__file__).parent
    offenders = []
    for path in sorted(ui_dir.glob("*.py")):
        if path.name in ("code_editor.py", "vim_mode.py"):
            continue
        text = path.read_text(encoding="utf-8")
        if "in_command_mode" in text and "DELETE_" in text:
            offenders.append(path.name)
    assert offenders == [], offenders


def test_the_classification_is_NOT_mode_conditional(editor):
    """What became mode-conditional is the APPLICATION, not the classification:
    `EDITOR_CHORDS` keeps giving the same answer at all six surfaces, which is the
    invariant that table exists for."""
    from pgtp_editor.ui.code_editor import classify_editor_chord

    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_U, Qt.KeyboardModifier.ControlModifier
    )
    before = classify_editor_chord(event)
    escape(editor)
    assert classify_editor_chord(event) == before == DELETE_LINE


# ---------------------------------------------------------------------------
# Motions -- family-agnostic character and line arithmetic
# ---------------------------------------------------------------------------

def test_42j_the_motivating_case(editor):
    editor.setPlainText("\n".join(f"line {n}" for n in range(60)))
    place(editor, 0)
    escape(editor)
    press(editor, "42j")
    assert editor.textCursor().blockNumber() == 42


def test_a_count_that_overshoots_is_REFUSED_rather_than_clamped(editor):
    refusals = []
    editor.expansion_refused.connect(refusals.append)
    place(editor, 0)
    escape(editor)
    press(editor, "42j")
    assert editor.textCursor().blockNumber() == 0
    assert refusals and "lines below" in refusals[0]


def test_hjkl(editor):
    place(editor, 0)
    escape(editor)
    press(editor, "lll")
    assert caret(editor) == 3
    press(editor, "h")
    assert caret(editor) == 2
    press(editor, "j")
    assert editor.textCursor().blockNumber() == 1
    press(editor, "k")
    assert editor.textCursor().blockNumber() == 0


def test_zero_caret_and_dollar(editor):
    """`$` lands on the LAST CHARACTER, not past it (BUG-260812001031).

    That is the on-character caret model: in Command mode the caret is *on* a
    glyph -- which is what the block caret paints and what makes `%` match the
    bracket the user sees under it. Edit mode's between-characters caret is
    unchanged and still rests past the last character, which is where `a` and
    `A` put it.
    """
    place(editor, TEXT.index("second") + 2)
    escape(editor)
    press(editor, "0")
    assert caret(editor) == TEXT.index("    second")
    press(editor, "^")
    assert caret(editor) == TEXT.index("second")
    press(editor, "$")
    last_character = TEXT.index("second line here") + len("second line here") - 1
    assert caret(editor) == last_character


def test_gg_and_G_and_NG(editor):
    editor.setPlainText("one\ntwo\nthree\nfour\n")
    place(editor, 0)
    escape(editor)
    press(editor, "G")
    last = editor.document().blockCount() - 1
    assert editor.textCursor().blockNumber() == last
    press(editor, "gg")
    assert editor.textCursor().blockNumber() == 0
    press(editor, "3G")
    assert editor.textCursor().blockNumber() == 2


def test_G_past_the_end_STATES_why(editor):
    refusals = []
    editor.expansion_refused.connect(refusals.append)
    escape(editor)
    press(editor, "999G")
    assert refusals and "lines" in refusals[0]


def test_word_motions_use_the_character_class_rule(editor):
    editor.setPlainText("my_table.column next\n")
    place(editor, 0)
    escape(editor)
    press(editor, "w")
    assert caret(editor) == len("my_table")  # the '.' is its own word
    press(editor, "w")
    assert caret(editor) == len("my_table.")
    press(editor, "b")
    assert caret(editor) == len("my_table")
    place(editor, 0)
    press(editor, "e")
    assert caret(editor) == len("my_table") - 1


def test_word_motions_answer_the_same_way_on_XML_text(xml):
    xml.setPlainText('<Page name="x">\n')
    place(xml, 0)
    escape(xml)
    press(xml, "w")
    assert caret(xml) == 1  # past the '<' punctuation run


def test_f_t_F_T_search_the_current_line(editor):
    editor.setPlainText("abc-def-ghi\n")
    place(editor, 0)
    escape(editor)
    press(editor, "f-")
    assert caret(editor) == 3
    press(editor, "f-")
    assert caret(editor) == 7
    press(editor, "F-")
    assert caret(editor) == 3
    # `t` is "till": it lands on the character BEFORE its target, where `f` lands
    # on the target itself. 'i' is the last character, at index 10.
    press(editor, "t")
    press(editor, "i")
    assert caret(editor) == 9


def test_f_that_finds_nothing_STATES_why(editor):
    refusals = []
    editor.expansion_refused.connect(refusals.append)
    place(editor, 0)
    escape(editor)
    press(editor, "f")
    press(editor, "~")
    assert refusals and "~" in refusals[0]


def test_percent_matches_brackets_at_the_character_level(editor):
    editor.setPlainText("f(a, g(b))\n")
    place(editor, 1)
    escape(editor)
    press(editor, "%")
    assert caret(editor) == editor.toPlainText().rindex(")")


def test_percent_with_no_bracket_on_the_line_STATES_why(editor):
    refusals = []
    editor.expansion_refused.connect(refusals.append)
    editor.setPlainText("plain text\n")
    place(editor, 0)
    escape(editor)
    press(editor, "%")
    assert refusals and "bracket" in refusals[0]


def test_braces_move_by_blank_line(editor):
    editor.setPlainText("a\nb\n\nc\nd\n\ne\n")
    place(editor, 0)
    escape(editor)
    press(editor, "}")
    assert editor.textCursor().blockNumber() == 2
    press(editor, "}")
    assert editor.textCursor().blockNumber() == 5
    press(editor, "{")
    assert editor.textCursor().blockNumber() == 2


def test_no_motion_reaches_into_the_sql_package():
    """A boundary rule, not a sequencing accident: `w`/`b`/`e` are character
    classes and this layer serves XML, PHP and JS buffers too."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(vim_mode.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.startswith("pgtp_editor.sql") for name in imported), imported


# ---------------------------------------------------------------------------
# Operators, and the ONE shared system clipboard
# ---------------------------------------------------------------------------

def test_dw_deletes_a_word_and_writes_the_system_clipboard(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    escape(editor)
    press(editor, "dw")
    assert editor.toPlainText().startswith("beta")
    assert QApplication.clipboard().text() == "alpha "


def test_de_is_INCLUSIVE_of_the_character_it_lands_on(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    escape(editor)
    press(editor, "de")
    assert editor.toPlainText().startswith(" beta")


def test_dd_deletes_the_whole_line_and_CLOBBERS_the_clipboard(editor):
    """Vim's own behaviour, accepted deliberately: the user who wanted their
    clipboard kept has `Ctrl+Z`."""
    QApplication.clipboard().setText("precious")
    editor.setPlainText("one\ntwo\nthree\n")
    place(editor, 0)
    escape(editor)
    press(editor, "dd")
    assert editor.toPlainText().startswith("two")
    assert QApplication.clipboard().text() == "one\n"


def test_a_counted_dd_takes_that_many_lines(editor):
    editor.setPlainText("one\ntwo\nthree\nfour\n")
    place(editor, 0)
    escape(editor)
    press(editor, "2dd")
    assert editor.toPlainText().startswith("three")


def test_yy_yanks_the_line_without_changing_the_buffer(editor):
    editor.setPlainText("one\ntwo\n")
    place(editor, 0)
    escape(editor)
    press(editor, "yy")
    assert editor.toPlainText() == "one\ntwo\n"
    assert QApplication.clipboard().text() == "one\n"


def test_yank_leaves_the_caret_at_the_start_of_the_range(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    escape(editor)
    press(editor, "yw")
    assert caret(editor) == 0


def test_cc_KEEPS_the_line_and_lands_in_edit_mode(editor):
    editor.setPlainText("    body here\nnext\n")
    place(editor, 4)
    escape(editor)
    press(editor, "cc")
    assert not editor.in_command_mode
    assert editor.document().blockCount() == 3  # the line survives, emptied
    assert editor.toPlainText().startswith("\nnext")


def test_cw_lands_in_edit_mode_so_the_next_letters_TYPE(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    escape(editor)
    press(editor, "cw")
    assert not editor.in_command_mode
    press(editor, "X")
    assert editor.toPlainText().startswith("Xbeta")


def test_x_and_X_delete_one_character_each_way(editor):
    editor.setPlainText("abcdef\n")
    place(editor, 3)
    escape(editor)
    press(editor, "x")
    assert editor.toPlainText().startswith("abcef")
    press(editor, "X")
    assert editor.toPlainText().startswith("abef")


def test_D_and_Y_are_the_line_shorthands(editor):
    editor.setPlainText("alpha beta\nsecond\n")
    place(editor, 5)
    escape(editor)
    press(editor, "D")
    assert editor.toPlainText().startswith("alpha\n")
    press(editor, "Y")
    assert QApplication.clipboard().text() == "alpha\n"


def test_r_replaces_the_character_under_the_caret(editor):
    editor.setPlainText("abc\n")
    place(editor, 0)
    escape(editor)
    press(editor, "r")
    press(editor, "Z")
    assert editor.toPlainText().startswith("Zbc")


def test_r_with_too_few_characters_left_STATES_why(editor):
    refusals = []
    editor.expansion_refused.connect(refusals.append)
    editor.setPlainText("ab\n")
    place(editor, 0)
    escape(editor)
    press(editor, "9r")
    press(editor, "Z")
    assert refusals and "characters" in refusals[0]


def test_p_and_P_paste_INLINE_and_there_is_NO_linewise_paste(editor):
    """`yy` followed by `p` inserts inline, not as a new line. A linewise flag is a
    second piece of state travelling with the text -- a parallel register by
    another name -- which is exactly what one system clipboard avoids."""
    editor.setPlainText("one\ntwo\n")
    place(editor, 0)
    escape(editor)
    press(editor, "yy")
    press(editor, "P")
    # The clipboard holds "one\n", and `P` inserts it AT THE CARET -- inline, like
    # `Ctrl+V`. A linewise paste would have put it on a line of its own without
    # splitting the caret's line; this splits it, which is the whole point.
    assert editor.toPlainText().startswith("one\none\ntwo\n")


def test_the_clipboard_interoperates_with_ctrl_c_and_other_applications(editor):
    QApplication.clipboard().setText("from elsewhere")
    editor.setPlainText("x\n")
    place(editor, 0)
    escape(editor)
    press(editor, "P")
    assert editor.toPlainText().startswith("from elsewhere")


def test_there_is_no_register_state_on_the_editor(editor):
    assert not hasattr(editor, "_vim_registers")
    assert not hasattr(editor, "registers")


# ---------------------------------------------------------------------------
# Insert entry, and the absence of a visual mode
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["i", "a", "I", "A", "o", "O", "v", "V"])
def test_every_insert_entry_key_lands_in_edit_mode(editor, key):
    escape(editor)
    press(editor, key)
    assert not editor.in_command_mode


def test_v_and_V_are_aliases_and_add_NO_visual_selection(editor):
    """Selection is a Windows method. The contract consequence, stated because a
    vim user will otherwise hit it as a bug: the select-with-`v`-then-`d` reflex
    does not exist here."""
    place(editor, 0)
    escape(editor)
    press(editor, "v")
    assert not editor.textCursor().hasSelection()
    assert not editor.in_command_mode


def test_a_d_after_a_windows_style_selection_DELETES_IT(editor):
    """**Reversed by FQ-260812000331**, deliberately: `d` used to wait for a
    motion here, because there was no selection notion at all. There still is no
    visual MODE -- what there is now is a selection the operators can see, and it
    does not matter whether the mouse, `Shift`+arrows or sticky selection made
    it. That is the middle ground the owner chose over a real Visual mode.
    """
    editor.setPlainText("alpha beta\n")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, cursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    escape(editor)
    press(editor, "d")
    assert editor.toPlainText() == " beta\n"
    assert not editor._vim_grammar.is_pending


def test_o_and_O_open_a_line_below_and_above(editor):
    editor.setPlainText("    body\n")
    place(editor, 4)
    escape(editor)
    press(editor, "o")
    assert editor.document().blockCount() == 3
    assert editor.textCursor().blockNumber() == 1
    editor.setPlainText("    body\n")
    place(editor, 4)
    escape(editor)
    press(editor, "O")
    assert editor.textCursor().blockNumber() == 0


def test_A_goes_to_the_end_of_the_line_and_I_to_the_first_non_blank(editor):
    editor.setPlainText("    body\n")
    place(editor, 6)
    escape(editor)
    press(editor, "I")
    assert caret(editor) == 4
    escape(editor)
    press(editor, "A")
    assert caret(editor) == len("    body")


# ---------------------------------------------------------------------------
# Text objects -- `aw` / `iw` (BUG-260811234853)
#
# The reported defect was that `caw`/`daw`/`yaw` did *nothing coherent*: `a` was
# an insert-entry key, so the operator was discarded and the `w` ran as a bare
# motion. These assert the whole pair against each operator, because the reason
# the pair exists is the whitespace difference.
# ---------------------------------------------------------------------------

def test_daw_deletes_the_word_AND_its_trailing_whitespace(editor):
    editor.setPlainText("alpha beta gamma\n")
    place(editor, 2)
    escape(editor)
    press(editor, "daw")
    assert editor.toPlainText() == "beta gamma\n"


def test_diw_deletes_ONLY_the_word(editor):
    editor.setPlainText("alpha beta gamma\n")
    place(editor, 2)
    escape(editor)
    press(editor, "diw")
    assert editor.toPlainText() == " beta gamma\n"


def test_yaw_yanks_to_the_ONE_system_clipboard_and_leaves_the_buffer(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 2)
    escape(editor)
    press(editor, "yaw")
    assert editor.toPlainText() == "alpha beta\n"
    assert QApplication.clipboard().text() == "alpha "
    assert caret(editor) == 0  # vim leaves the caret at the start of a yank


def test_yiw_takes_the_word_without_its_whitespace(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 2)
    escape(editor)
    press(editor, "yiw")
    assert QApplication.clipboard().text() == "alpha"


def test_caw_deletes_the_object_and_lands_in_EDIT_mode(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 2)
    escape(editor)
    press(editor, "caw")
    assert editor.toPlainText() == "beta\n"
    assert not editor.in_command_mode


def test_ciw_is_the_change_a_vim_user_reaches_for_most(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 2)
    escape(editor)
    press(editor, "ciw")
    assert editor.toPlainText() == " beta\n"
    assert not editor.in_command_mode
    press(editor, "X")  # Edit mode: the letter types again
    assert editor.toPlainText() == "X beta\n"


def test_caw_on_the_last_word_leaves_the_caret_where_the_text_WAS(editor):
    """`c` lands in Edit mode, where the between-characters caret is correct --
    so the Command-mode on-character clamp must not pull it back over the space
    it just left behind."""
    editor.setPlainText("alpha beta\n")
    place(editor, len("alpha b"))
    escape(editor)
    press(editor, "caw")
    assert editor.toPlainText() == "alpha\n"
    press(editor, "X")
    assert editor.toPlainText() == "alphaX\n"


def test_a_text_object_at_the_END_of_the_line_takes_the_PRECEDING_whitespace(editor):
    """Vim's `aw` rule, and what stops `daw` leaving a dangling space."""
    editor.setPlainText("alpha beta\n")
    place(editor, len("alpha b"))
    escape(editor)
    press(editor, "daw")
    assert editor.toPlainText() == "alpha\n"


def test_a_text_object_ON_WHITESPACE_takes_the_gap_and_the_word_after_it(editor):
    editor.setPlainText("alpha   beta\n")
    place(editor, 6)
    escape(editor)
    press(editor, "daw")
    assert editor.toPlainText() == "alpha\n"


def test_a_text_object_on_a_PUNCTUATION_run_takes_that_run(editor):
    editor.setPlainText("a === b\n")
    place(editor, 3)
    escape(editor)
    press(editor, "diw")
    assert editor.toPlainText() == "a  b\n"


def test_a_counted_text_object_takes_that_many_words(editor):
    editor.setPlainText("one two three four\n")
    place(editor, 0)
    escape(editor)
    press(editor, "d2aw")
    assert editor.toPlainText() == "three four\n"


def test_the_count_may_be_typed_before_the_operator_too(editor):
    editor.setPlainText("one two three four\n")
    place(editor, 0)
    escape(editor)
    press(editor, "2daw")
    assert editor.toPlainText() == "three four\n"


def test_a_text_object_count_that_OVERSHOOTS_is_refused_rather_than_clamped(editor):
    """The same answer `42j` gives on a four-line file: refuse, and say why."""
    refusals = []
    editor.expansion_refused.connect(refusals.append)
    editor.setPlainText("one two\n")
    place(editor, 0)
    escape(editor)
    press(editor, "d9aw")
    assert editor.toPlainText() == "one two\n"
    assert refusals and "word" in refusals[0]


def test_a_text_object_never_joins_two_lines(editor):
    editor.setPlainText("alpha\nbeta\n")
    place(editor, 0)
    escape(editor)
    press(editor, "daw")
    assert editor.toPlainText() == "\nbeta\n"


def test_bare_a_and_i_are_STILL_insert_entry_in_command_mode(editor):
    """The gate the text objects hang on: `a` appends and `i` inserts when no
    operator is pending, which is what makes them the most-used keys here."""
    editor.setPlainText("ab\n")
    place(editor, 0)
    escape(editor)
    press(editor, "a")
    assert not editor.in_command_mode
    assert caret(editor) == 1
    escape(editor)
    press(editor, "i")
    assert not editor.in_command_mode


def test_a_text_object_answers_the_same_way_on_XML_text(xml):
    """Character classes, not a SQL model -- four of the six surfaces have no SQL
    to tokenize."""
    xml.setPlainText('<Page name="x">\n')
    place(xml, 6)  # inside "name"
    escape(xml)
    press(xml, "diw")
    assert xml.toPlainText().startswith('<Page ="x">')


# ---------------------------------------------------------------------------
# Sticky / line selection, and the selection-aware operators
# (FQ-260812000331 -- a middle ground, NOT a vim Visual sub-mode)
# ---------------------------------------------------------------------------

def arrow(editor, key, count=1):
    for _ in range(count):
        QTest.keyClick(editor, key)


def test_v_switches_on_sticky_selection_on_its_way_to_edit_mode(editor):
    """`v` is STILL an insert-entry alias -- there is no visual mode. What it
    gained is a side effect, invoked through the one toggle."""
    place(editor, 0)
    escape(editor)
    press(editor, "v")
    assert not editor.in_command_mode
    assert editor.sticky_selection_mode == vim_mode.STICKY_CHARACTER


def test_V_switches_on_LINE_selection_and_the_two_are_MUTUALLY_EXCLUSIVE(editor):
    place(editor, 0)
    escape(editor)
    press(editor, "V")
    assert editor.sticky_selection_mode == vim_mode.STICKY_LINE
    escape(editor)
    press(editor, "v")
    assert editor.sticky_selection_mode == vim_mode.STICKY_CHARACTER


def test_v_and_the_MENU_COMMAND_share_ONE_toggle(editor):
    """Two paths toggling one state eventually disagree, and the user then sees a
    caret that selects for no reason they can name."""
    import inspect

    from pgtp_editor.ui.vim_mode import VimModeMixin

    source = inspect.getsource(VimModeMixin._vim_run_action)
    assert "set_sticky_selection" in source
    for slot in (VimModeMixin.toggle_sticky_selection, VimModeMixin.toggle_line_selection):
        assert "set_sticky_selection" in inspect.getsource(slot)


def test_ordinary_movement_EXTENDS_the_selection_while_sticky_is_on(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    editor.set_sticky_selection(vim_mode.STICKY_CHARACTER)
    arrow(editor, Qt.Key.Key_Right, 5)
    assert editor.textCursor().selectedText() == "alpha"


def test_line_selection_grows_by_WHOLE_lines(editor):
    editor.setPlainText("one\ntwo\nthree\n")
    place(editor, 1)
    editor.set_sticky_selection(vim_mode.STICKY_LINE)
    assert editor.textCursor().selectedText() == "one"
    arrow(editor, Qt.Key.Key_Down)
    assert editor.textCursor().selectedText().replace(" ", "\n") == "one\ntwo"


def test_the_toggle_starts_a_FRESH_anchor_at_the_caret(editor):
    editor.setPlainText("alpha beta\n")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, cursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    editor.set_sticky_selection(vim_mode.STICKY_CHARACTER)
    assert not editor.textCursor().hasSelection()


@pytest.mark.parametrize("operator,expected", [("d", " beta\n"), ("x", " beta\n")])
def test_d_and_x_act_on_the_selection_when_there_is_one(editor, operator, expected):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    editor.set_sticky_selection(vim_mode.STICKY_CHARACTER)
    arrow(editor, Qt.Key.Key_Right, 5)
    escape(editor)
    press(editor, operator)
    assert editor.toPlainText() == expected


def test_y_copies_the_selection_and_c_deletes_it_and_drops_to_edit_mode(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    editor.set_sticky_selection(vim_mode.STICKY_CHARACTER)
    arrow(editor, Qt.Key.Key_Right, 5)
    escape(editor)
    press(editor, "y")
    assert QApplication.clipboard().text() == "alpha"
    assert editor.toPlainText() == "alpha beta\n"

    editor.set_sticky_selection(vim_mode.STICKY_CHARACTER)
    place(editor, 0)
    editor.set_sticky_selection(vim_mode.STICKY_CHARACTER)
    arrow(editor, Qt.Key.Key_Right, 5)
    escape(editor)
    press(editor, "c")
    assert editor.toPlainText() == " beta\n"
    assert not editor.in_command_mode


def test_an_operator_falls_back_to_the_MOTION_when_nothing_is_selected(editor):
    """Selection-aware, not selection-only: with no selection `d` is still an
    operator waiting for a motion."""
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    escape(editor)
    press(editor, "dw")
    assert editor.toPlainText() == "beta\n"


def test_the_whole_v_extend_ESC_d_flow_including_its_accepted_extra_Esc(editor):
    """The owner's recorded muscle-memory flow, and its ONE structural extra
    `Esc`: operators exist only in Command mode, so you step back into it before
    operating. A true Visual mode was rejected deliberately."""
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    escape(editor)
    press(editor, "v")           # sticky on, Edit mode
    arrow(editor, Qt.Key.Key_Right, 5)
    escape(editor)               # the accepted extra Esc
    press(editor, "d")
    assert editor.toPlainText() == " beta\n"


def test_consuming_the_selection_ENDS_the_sticky_gesture(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    editor.set_sticky_selection(vim_mode.STICKY_CHARACTER)
    arrow(editor, Qt.Key.Key_Right, 5)
    escape(editor)
    press(editor, "d")
    assert editor.sticky_selection_mode is None


def test_typing_a_printable_character_ends_the_sticky_gesture(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    editor.set_sticky_selection(vim_mode.STICKY_CHARACTER)
    arrow(editor, Qt.Key.Key_Right, 5)
    press(editor, "z")
    assert editor.sticky_selection_mode is None
    assert editor.toPlainText() == "z beta\n"


def test_a_mouse_click_ends_the_sticky_gesture_but_not_the_editing_mode(editor):
    from PySide6.QtCore import QPoint

    editor.set_sticky_selection(vim_mode.STICKY_CHARACTER)
    QTest.mouseClick(
        editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(4, 4)
    )
    assert editor.sticky_selection_mode is None
    assert not editor.in_command_mode


def test_focus_loss_ends_the_sticky_gesture_the_way_it_ends_the_mode(editor):
    editor.setFocus()
    editor.set_sticky_selection(vim_mode.STICKY_CHARACTER)
    escape(editor)
    editor.clearFocus()
    assert editor.sticky_selection_mode is None
    assert not editor.in_command_mode


def test_a_read_only_editor_has_NO_sticky_selection_either(editor):
    """The layer is inactive ENTIRELY on a read-only buffer."""
    editor.setReadOnly(True)
    editor.set_sticky_selection(vim_mode.STICKY_CHARACTER)
    place(editor, 0)
    arrow(editor, Qt.Key.Key_Right, 3)
    assert not editor.textCursor().hasSelection()


def test_there_is_still_NO_visual_mode_in_the_indicator(editor):
    """The middle ground adds no third editing mode: the indicator keeps its two
    labels, because sticky selection is a selection state, not a mode."""
    place(editor, 0)
    escape(editor)
    press(editor, "v")
    assert editor.editing_mode_label() == EDITING_EDIT
    assert mode_text("", "", EDITING_EDIT).count("mode") >= 1


# ---------------------------------------------------------------------------
# The on-character caret model and the coloured BLOCK caret
# (BUG-260812001031)
# ---------------------------------------------------------------------------

def block_caret_pixel(editor):
    """The colour actually RENDERED at the caret's top-left character cell.

    Pixels, not a palette read-back: a per-widget `setPalette` is inert under the
    app-level QSS (`BUG-260811021804`), so only what reaches the screen counts.
    """
    QApplication.processEvents()
    image = editor.viewport().grab().toImage()
    rect = editor.cursorRect(editor.textCursor())
    return image.pixelColor(rect.left() + 1, rect.top() + rect.height() // 2)


def test_the_command_mode_caret_is_painted_as_a_COLOURED_BLOCK(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    escape(editor)
    expected, _foreground = editor._vim_block_caret_colors()
    assert block_caret_pixel(editor) == expected


def test_the_block_caret_is_a_WHOLE_CHARACTER_wide(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    escape(editor)
    rect, character = editor._vim_block_caret_rect()
    assert character == "a"
    assert rect.width() == editor.fontMetrics().horizontalAdvance("a")


@pytest.mark.parametrize("light", [True, False])
def test_the_block_caret_FOLLOWS_THE_THEME(editor, light):
    from pgtp_editor.ui.theme import dark_palette, light_palette

    editor.setPalette(light_palette() if light else dark_palette())
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    escape(editor)
    background, foreground = editor._vim_block_caret_colors()
    assert background.lightness() != foreground.lightness()
    assert block_caret_pixel(editor) == background


def test_the_two_themes_do_NOT_paint_the_same_caret(editor):
    from pgtp_editor.ui.theme import dark_palette, light_palette

    editor.setPalette(light_palette())
    light_colour = editor._vim_block_caret_colors()
    editor.setPalette(dark_palette())
    assert editor._vim_block_caret_colors() != light_colour


def test_the_caret_colours_are_SOURCED_FROM_theme_py(editor):
    """`vim_mode` owns the *decision* (which theme this widget is in), never a
    second colour table. Patching `theme.command_caret_colors` must move the
    caret -- if the pair is ever re-declared locally here, this fails."""
    from pgtp_editor.ui import theme

    assert theme.command_caret_colors(True) == editor._vim_block_caret_colors.__globals__[
        "command_caret_colors"
    ](True)

    for light in (True, False):
        expected = theme.command_caret_colors(light)
        editor.setPalette(theme.light_palette() if light else theme.dark_palette())
        background, foreground = editor._vim_block_caret_colors()
        assert (background.name().upper(), foreground.name().upper()) == (
            expected[0].upper(),
            expected[1].upper(),
        )


def test_vim_mode_declares_NO_caret_colours_of_its_own():
    """No second per-theme colour table beside `theme.py`'s -- the failure mode
    `mode_indicator.py`'s docstring records."""
    import inspect
    import re

    from pgtp_editor.ui import vim_mode

    source = inspect.getsource(vim_mode)
    literals = re.findall(r"[\"']#[0-9A-Fa-f]{6}[\"']", source)
    assert literals == [], f"colour literals in vim_mode.py: {literals}"


def test_edit_mode_paints_NO_block_caret(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    background, _foreground = editor._vim_block_caret_colors()
    assert block_caret_pixel(editor) != background


def test_leaving_command_mode_REVERTS_the_caret(editor):
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    escape(editor)
    background, _foreground = editor._vim_block_caret_colors()
    assert block_caret_pixel(editor) == background
    press(editor, "i")  # insert-entry: back to Edit mode
    assert block_caret_pixel(editor) != background


def test_a_READ_ONLY_editor_never_shows_the_block_caret(editor):
    """The rule the caret may not break: a read-only editor has no editing mode
    at all, so it cannot have a Command-mode cue."""
    editor.setPlainText("alpha beta\n")
    place(editor, 0)
    escape(editor)
    background, _foreground = editor._vim_block_caret_colors()
    assert block_caret_pixel(editor) == background
    editor.setReadOnly(True)
    assert not editor.in_command_mode
    assert block_caret_pixel(editor) != background


def test_the_command_mode_caret_cannot_rest_on_the_NEWLINE_offset(editor):
    """The on-character model: `$` and `l` stop on the last real character, so
    the block always covers a glyph."""
    editor.setPlainText("alpha\nbeta\n")
    place(editor, 0)
    escape(editor)
    press(editor, "$")
    assert caret(editor) == len("alpha") - 1
    press(editor, "lll")
    assert caret(editor) == len("alpha") - 1


def test_EDIT_mode_still_rests_past_the_last_character(editor):
    """Command mode and Edit mode do NOT share the clamp: `A` and ordinary typing
    depend on the between-characters caret, which is unchanged."""
    editor.setPlainText("alpha\n")
    place(editor, 0)
    escape(editor)
    press(editor, "A")
    assert not editor.in_command_mode
    assert caret(editor) == len("alpha")


def test_entering_command_mode_pulls_a_caret_off_the_newline_offset(editor):
    editor.setPlainText("alpha\n")
    place(editor, len("alpha"))
    escape(editor)
    assert caret(editor) == len("alpha") - 1


def test_percent_matches_the_bracket_the_caret_is_ON_in_both_directions(editor):
    editor.setPlainText("f(a, g(b))\n")
    text = editor.toPlainText()
    place(editor, 1)
    escape(editor)
    press(editor, "%")
    assert caret(editor) == text.rindex(")")
    press(editor, "%")
    assert caret(editor) == 1


def test_y_percent_yanks_BOTH_brackets_from_either_end(editor):
    """The reported drop: `y%` used to exclude one of the pair, because the caret
    offset was a between-characters position rather than the index of the
    character it sits on."""
    editor.setPlainText("f(a, g(b))\n")
    place(editor, 1)
    escape(editor)
    press(editor, "y%")
    assert QApplication.clipboard().text() == "(a, g(b))"
    place(editor, editor.toPlainText().rindex(")"))
    press(editor, "y%")
    assert QApplication.clipboard().text() == "(a, g(b))"


def test_d_percent_spans_both_brackets(editor):
    editor.setPlainText("f(a, g(b))\n")
    place(editor, 1)
    escape(editor)
    press(editor, "d%")
    assert editor.toPlainText() == "f\n"


def test_d_dollar_still_deletes_the_LAST_character(editor):
    """The clamp is on the CARET, not on the motion: `D` / `d$` must still take
    the character the caret may not rest on."""
    editor.setPlainText("alpha\nbeta\n")
    place(editor, 0)
    escape(editor)
    press(editor, "d$")
    assert editor.toPlainText() == "\nbeta\n"


def test_x_still_deletes_the_LAST_character_of_a_line(editor):
    editor.setPlainText("ab\n")
    place(editor, 0)
    escape(editor)
    press(editor, "$")
    press(editor, "x")
    assert editor.toPlainText() == "a\n"


# ---------------------------------------------------------------------------
# Search -- the app's EXISTING Find bar, no second engine
# ---------------------------------------------------------------------------

def test_slash_focuses_the_apps_existing_find_bar(hosted, editor):
    escape(editor)
    press(editor, "/")
    QApplication.processEvents()
    assert hosted.find_replace_bar.isAncestorOf(QApplication.focusWidget())


def test_slash_focusing_the_bar_drops_command_mode_through_the_one_path(hosted, editor):
    escape(editor)
    press(editor, "/")
    QApplication.processEvents()
    assert not editor.in_command_mode


def test_n_runs_the_bars_own_find_next(hosted, editor):
    editor.setPlainText("beta alpha beta\n")
    hosted.find_replace_bar.set_find_text("beta")
    place(editor, 0)
    escape(editor)
    press(editor, "n")
    assert editor.textCursor().hasSelection()
    assert editor.textCursor().selectedText() == "beta"


def test_N_states_that_there_is_no_backwards_search(hosted, editor):
    """No second search engine: the bar searches forwards only, so `N` says so
    rather than inventing one."""
    refusals = []
    editor.expansion_refused.connect(refusals.append)
    escape(editor)
    press(editor, "N")
    assert refusals == [NO_BACKWARD_SEARCH]


def test_slash_on_a_surface_with_no_find_bar_states_that(editor):
    refusals = []
    editor.expansion_refused.connect(refusals.append)
    escape(editor)
    press(editor, "/")
    assert refusals and "Find bar" in refusals[0]


# ---------------------------------------------------------------------------
# The `:` palette -- the app's own menu tree, derived and never designed
# ---------------------------------------------------------------------------

ENTRIES = [
    ("deployment.apply-to-quality", "Deployment › Apply to quality"),
    ("file.open", "File › Open"),
    ("database.reload-ddl", "Database › Reload DDL"),
]


def test_the_verb_rule_is_the_FULL_menu_path_not_the_leaf():
    """Leaf labels are not unique across two menu bars, and a palette whose verb is
    ambiguous has to invent a disambiguator -- which is a second vocabulary."""
    matched = palette_matches("deployqual", ENTRIES)
    assert matched[0][0] == "deployment.apply-to-quality"
    assert "Deployment" in matched[0][1]


def test_the_palette_matches_as_a_subsequence_so_verbs_are_DISCOVERED():
    assert palette_matches("reload", ENTRIES)[0][0] == "database.reload-ddl"
    assert palette_matches("zzz", ENTRIES) == []


def test_an_empty_query_offers_everything():
    assert len(palette_matches("", ENTRIES)) == len(ENTRIES)


def test_the_palette_is_UNAVAILABLE_in_the_menu_less_dialog_and_SAYS_so(qtbot):
    """Per refuse-don't-guess it states that rather than opening an empty palette
    -- an empty command line is the *"dead control"* posture §7 forbids."""
    dialog = CodeEditorDialog("sql")
    qtbot.addWidget(dialog)
    dialog.show()
    editor = dialog._editor
    refusals = []
    editor.expansion_refused.connect(refusals.append)
    editor.setFocus()
    escape(editor)
    press(editor, ":")
    assert refusals == [PALETTE_UNAVAILABLE]
    assert editor._vim_command_line is None or not editor._vim_command_line.isVisible()


def test_every_other_command_mode_gesture_works_normally_in_the_dialog(qtbot):
    dialog = CodeEditorDialog("sql")
    qtbot.addWidget(dialog)
    dialog.show()
    editor = dialog._editor
    editor.setPlainText("one\ntwo\n")
    place(editor, 0)
    editor.setFocus()
    escape(editor)
    press(editor, "dd")
    assert editor.toPlainText().startswith("two")


def test_the_palette_opens_over_the_editor_when_there_IS_a_namespace(code, qtbot):
    code.set_vim_command_provider(lambda: ENTRIES)
    escape(code)
    press(code, ":")
    line = code._vim_command_line
    assert line is not None and line.isVisible()
    assert line.parentWidget() is code


def test_the_palette_is_not_a_QDialog_and_escape_returns_to_command_mode(code):
    from PySide6.QtWidgets import QDialog

    code.set_vim_command_provider(lambda: ENTRIES)
    escape(code)
    press(code, ":")
    line = code._vim_command_line
    assert not isinstance(line, QDialog)
    QTest.keyClick(line.field, Qt.Key.Key_Escape)
    assert not line.isVisible()
    assert code.in_command_mode


def test_a_palette_verb_triggers_the_REAL_QAction(code, qtbot):
    from PySide6.QtGui import QAction

    fired = []
    action = QAction("Apply to quality", code)
    action.triggered.connect(lambda: fired.append(1))
    code.set_vim_command_provider(lambda: ENTRIES)
    code._vim_action_for = lambda command_id: (
        action if command_id == "deployment.apply-to-quality" else None
    )
    escape(code)
    press(code, ":")
    code._vim_command_line.field.setText("deployqual")
    code._vim_command_line._accept_current()
    assert fired == [1]


def test_a_verb_that_matches_nothing_is_REFUSED_with_the_reason(code):
    refusals = []
    code.expansion_refused.connect(refusals.append)
    code.set_vim_command_provider(lambda: ENTRIES)
    escape(code)
    press(code, ":")
    code._vim_command_line.field.setText("zzzz")
    code._vim_command_line._accept_current()
    assert refusals and "no command matches" in refusals[0]


@pytest.mark.parametrize("option,expected", [("wrap", True), ("nowrap", False)])
def test_set_wrap_and_nowrap_reach_the_option_the_app_ALREADY_has(
    editor, option, expected
):
    editor.set_vim_command_provider(lambda: ENTRIES)
    escape(editor)
    press(editor, ":")
    editor._vim_command_line.field.setText(f"set {option}")
    editor._vim_command_line._accept_current()
    assert editor.is_line_wrap_enabled() is expected


def test_set_number_is_REFUSED_because_it_would_be_a_NEW_capability(editor):
    """The gutter's line-number column is unconditional, so `:set nonumber` would
    be a new capability -- and adding one *through the palette* is exactly the
    smuggling the `:set` rule forbids."""
    refusals = []
    editor.expansion_refused.connect(refusals.append)
    editor.set_vim_command_provider(lambda: ENTRIES)
    escape(editor)
    press(editor, ":")
    editor._vim_command_line.field.setText("set nonumber")
    editor._vim_command_line._accept_current()
    assert refusals and "not an option" in refusals[0]


def test_the_wrap_toggle_is_ONE_implementation_shared_by_both_families(code, xml):
    from pgtp_editor.ui.editor_shared import SharedEditorMixin

    assert type(code).set_line_wrap_enabled is SharedEditorMixin.set_line_wrap_enabled
    assert type(xml).set_line_wrap_enabled is SharedEditorMixin.set_line_wrap_enabled


def test_the_hint_path_is_ONE_implementation_shared_by_both_families(code, xml):
    from pgtp_editor.ui.editor_shared import SharedEditorMixin

    assert type(code).report_refusal is SharedEditorMixin.report_refusal
    assert type(xml).report_refusal is SharedEditorMixin.report_refusal
    assert type(xml).show_hint is SharedEditorMixin.show_hint


def test_no_file_or_buffer_or_window_command_is_HARD_CODED(editor):
    """`:w :q :wq :e :bn :bp`, `Ctrl-W` splits and tab commands are all excluded --
    save/close/tab-switch stay 100% the app's own mechanisms, and a `:w` reflex
    would reinstate by the side door precisely the wrong-target save FQ-020
    deleted. Save is reachable only as the app's own `Deployment ▸` menu action.

    The mechanism that guarantees it: the palette has exactly ONE hard-coded verb
    family (`set`), and everything else must resolve against the menu tree.
    """
    import ast
    from pathlib import Path

    source = Path(vim_mode.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    # (`w` and `e` are deliberately absent from this list: they are MOTIONS. What
    # must not exist is a palette verb, hence the `:`-prefixed spellings and the
    # multi-letter buffer commands.)
    for verb in ("wq", "bn", "bp", "ZZ", ":w", ":q", ":wq", ":e", ":bn", ":bp"):
        assert verb not in literals, verb

    refusals = []
    editor.expansion_refused.connect(refusals.append)
    editor.set_vim_command_provider(lambda: ENTRIES)
    escape(editor)
    press(editor, ":")
    editor._vim_command_line.field.setText("w")
    editor._vim_command_line._accept_current()
    assert refusals and "no command matches" in refusals[0]


# ---------------------------------------------------------------------------
# The mode indicator -- three surfaces, one fact per surface
# ---------------------------------------------------------------------------

def test_mode_text_appends_the_editing_mode_as_a_THIRD_segment():
    assert mode_text("project", "Caption", EDITING_COMMAND).endswith(EDITING_COMMAND)
    assert mode_text("project", None, EDITING_EDIT) == f"Project mode · {EDITING_EDIT}"
    assert mode_text("project") == "Project mode"


def test_mode_colors_gains_NO_key_for_the_editing_mode():
    """A colour per editing mode makes the vocabulary twenty-four, and a vocabulary
    nobody recognises at a glance is not an indicator."""
    from pgtp_editor.ui.mode_indicator import mode_colors

    for light in (True, False):
        keys = set(mode_colors(light))
        assert EDITING_EDIT not in keys
        assert EDITING_COMMAND not in keys


def test_the_command_mode_label_CARRIES_the_exit_hint():
    """The indicator plus this hint is the ONLY guard for a user who enters
    Command mode by accident -- there is no opt-out, no first-time dialog and no
    timeout."""
    assert "press i" in EDITING_COMMAND


def test_an_editing_only_indicator_renders_that_segment_alone(qtbot):
    indicator = ModeIndicator(editing_only=True)
    qtbot.addWidget(indicator)
    indicator.set_editing_mode(EDITING_COMMAND)
    assert indicator.text() == EDITING_COMMAND
    assert "Project" not in indicator.text()
    assert "No Mode" not in indicator.text()


def test_an_editing_only_indicator_paints_the_NEUTRAL_pair(qtbot):
    from pgtp_editor.ui.mode_indicator import mode_colors

    indicator = ModeIndicator(editing_only=True, light=True)
    qtbot.addWidget(indicator)
    assert indicator.colors() == mode_colors(True)[None]


def test_the_dialog_carries_the_third_indicator_surface(qtbot):
    """**Load-bearing, not cosmetic**: shipping Command mode here without the
    indicator ships the version the owner declined."""
    dialog = CodeEditorDialog("sql")
    qtbot.addWidget(dialog)
    assert isinstance(dialog.mode_indicator, ModeIndicator)
    assert dialog.mode_indicator.editing_only
    assert dialog.mode_indicator.text() == EDITING_EDIT


def test_the_dialogs_indicator_follows_ITS_editors_transitions(qtbot):
    dialog = CodeEditorDialog("sql")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._editor.setFocus()
    escape(dialog._editor)
    assert dialog.mode_indicator.text() == EDITING_COMMAND
    press(dialog._editor, "i")
    assert dialog.mode_indicator.text() == EDITING_EDIT


# ---------------------------------------------------------------------------
# The two-press escape -- `CodeEditorDialog` ONLY (owner ruling, 2026-08-10)
# ---------------------------------------------------------------------------

def test_two_presses_of_escape_cancel_the_dialog(qtbot):
    """Command mode took away this modal's ONLY keyboard cancel (`Esc` was it;
    `Ctrl+S`/`Ctrl+W` were deleted here). The owner restored it as a SECOND press:
    the first enters Command mode, the second rejects."""
    dialog = CodeEditorDialog("sql")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._editor.setFocus()

    escape(dialog._editor)
    assert dialog._editor.in_command_mode
    assert dialog.isVisible()

    with qtbot.waitSignal(dialog.cancelled, timeout=1000):
        escape(dialog._editor)
    # `reject()` ran: the modal is down and reports the rejected code.
    assert not dialog.isVisible()
    assert dialog.result() == CodeEditorDialog.DialogCode.Rejected


def test_the_first_escape_does_not_cancel_the_dialog(qtbot):
    """A user reaching for the old one-press cancel must not lose the dialog
    silently either -- and must not keep it either way by accident: press one is
    the mode change and nothing else."""
    dialog = CodeEditorDialog("sql")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._editor.setFocus()
    fired = []
    dialog.cancelled.connect(lambda: fired.append(True))

    escape(dialog._editor)

    assert fired == []
    assert dialog.mode_indicator.text() == EDITING_COMMAND


def test_escape_with_something_PENDING_only_clears_it_and_stays(qtbot):
    """Row 4' still wins in the dialog: clearing a half-typed `42d` must never
    also close the dialog. That is what makes it a TWO-press escape rather than
    "any second Esc"."""
    dialog = CodeEditorDialog("sql")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._editor.setFocus()
    dialog.set_code("one\ntwo\nthree\n")
    fired = []
    dialog.cancelled.connect(lambda: fired.append(True))

    escape(dialog._editor)
    press(dialog._editor, "42d")
    assert dialog._editor._vim_grammar.is_pending

    escape(dialog._editor)
    assert not dialog._editor._vim_grammar.is_pending
    assert dialog._editor.in_command_mode
    assert fired == []

    # The press AFTER the pending state is cleared is the one that cancels.
    with qtbot.waitSignal(dialog.cancelled, timeout=1000):
        escape(dialog._editor)


def test_the_divergence_is_the_DIALOG_ONLY_and_the_other_surfaces_stay(editor):
    """The accepted cost is that `Esc` means something different in that one
    modal. The five in-window surfaces are unchanged: `Esc` in Command mode with
    nothing pending stays in Command mode, as vim does and as shipped."""
    escape(editor)
    assert editor.in_command_mode
    escape(editor)
    escape(editor)
    assert editor.in_command_mode


def test_only_the_dialog_installs_an_escape_fallback(qtbot, editor):
    """Guards the "exactly one caller" rule the mechanism's docstring states."""
    assert getattr(editor, "_vim_escape_fallback", None) is None
    dialog = CodeEditorDialog("sql")
    qtbot.addWidget(dialog)
    assert getattr(dialog._editor, "_vim_escape_fallback", None) is not None


def test_the_escape_fallback_is_held_WEAKLY(qtbot, code):
    """A strong bound-method reference from a child editor back to its parent
    dialog is a reference cycle between a widget and its child, which measurably
    changed teardown order enough to leave a live Python wrapper over a destroyed
    C++ dialog."""
    import weakref

    class Host:
        def cancel(self):  # pragma: no cover - never called here
            pass

    host = Host()
    code.set_command_mode_escape_fallback(host.cancel)
    assert isinstance(code._vim_escape_fallback, weakref.WeakMethod)
    del host
    # A dead fallback must fall back to "stay in Command mode", never raise.
    escape(code)
    escape(code)
    assert code.in_command_mode


def test_an_editing_mode_transition_is_PUBLISHED_to_observers(code):
    """The indicator must follow a transition on ANY editor, including tabs built
    at runtime in three different files -- so the mode PUBLISHES, exactly as
    `editor_gutter` publishes bookmark changes."""
    seen = []

    def note(editor):
        seen.append(editor)

    vim_mode.add_editing_mode_observer(note)
    try:
        escape(code)
        assert seen and seen[-1] is code
    finally:
        vim_mode.remove_editing_mode_observer(note)


def test_the_observer_registry_is_idempotent_per_callback(code):
    seen = []

    class Owner:
        def note(self, editor):
            seen.append(editor)

    owner = Owner()
    vim_mode.add_editing_mode_observer(owner.note)
    vim_mode.add_editing_mode_observer(owner.note)
    try:
        escape(code)
        assert len(seen) == 1
    finally:
        vim_mode.remove_editing_mode_observer(owner.note)


def test_removing_an_observer_is_a_no_op_when_it_was_never_added():
    vim_mode.remove_editing_mode_observer(lambda editor: None)


# ---------------------------------------------------------------------------
# What the layer must NOT become
# ---------------------------------------------------------------------------

def test_the_editing_mode_is_NOT_a_fourth_minor_mode():
    from pgtp_editor.ui.mode_indicator import MINOR_CAPTION, MINOR_DIFF, MINOR_XSD

    assert EDITING_EDIT not in (MINOR_CAPTION, MINOR_DIFF, MINOR_XSD)
    assert EDITING_COMMAND not in (MINOR_CAPTION, MINOR_DIFF, MINOR_XSD)


def test_the_editing_mode_is_ORTHOGONAL_to_the_minor_mode():
    """Folding Edit/Command into the winner-take-all stack would make
    *"Compare/Merge"* and *"Command"* mutually exclusive for no reason. Both are
    reported at once, which is what "orthogonal" means here."""
    from pgtp_editor.ui.mode_indicator import MINOR_DIFF

    text = mode_text("project", MINOR_DIFF, EDITING_COMMAND)
    assert MINOR_DIFF in text and EDITING_COMMAND in text
    assert text == f"Project mode · {MINOR_DIFF} · {EDITING_COMMAND}"


def test_the_vim_keys_are_NOT_enumerated_into_customize_shortcuts():
    """FQ-012's machinery governs MENU-ACTION shortcuts; this is a separate keymap
    inside the editor. Consequence, stated so it is not filed as a bug: the vim
    keys are not rebindable."""
    from pgtp_editor.ui.shortcut_registry import RESERVED_SEQUENCES

    for key in ("H", "J", "K", "L", "W", "B", "E", "G", "P", "Y", "X", "Colon", "Slash"):
        assert key not in RESERVED_SEQUENCES


def test_the_layer_adds_no_dispatcher():
    from pathlib import Path

    source = Path(vim_mode.__file__).read_text(encoding="utf-8")
    assert "active_xml_editor" not in source
    assert "active_code_editor" not in source
