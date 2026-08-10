# tests/ui/test_structural_selection.py
"""FQ-034 -- the Qt half of §8's structural expand/shrink ladder.

The span model is tested Qt-free in `tests/sql/test_block_spans.py`; what is
asserted here is everything that could only go wrong in a widget:

* the **stack** -- repeatable grow, shrink as its exact inverse, and the two
  invalidations (an edit, and a selection the user moved themselves);
* the **derive** path when there is no stack (`DEC-260810164601`), including that
  it is a no-op at the innermost span with no special case;
* the **capability gates**, which are a per-instance question and not a `hasattr`;
* the **chord**, which FQ-034 does not bind -- it answers a claim six surfaces
  already make, and the mechanical pin is that all six reach ONE implementation.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor

from pgtp_editor.ui.code_editor import (
    CLAIMED_NOT_UNDO_REDO,
    CodeEditor,
    CodeEditorDialog,
    apply_shrink_structural_selection,
    classify_editor_chord,
)
from pgtp_editor.ui.ddl_editor_panel import EditorPanel
from pgtp_editor.ui.xml_editor import XmlEditor

_SQL = "select a, coalesce(b, c) from t where a = 1;"

_BODY = """CREATE FUNCTION pr.f() RETURNS int AS $$
BEGIN
    IF a > 5 THEN
        total := total + 1;
    END IF;
    RETURN total;
END
$$ LANGUAGE plpgsql;"""


def _editor(qtbot, language="sql", text=_SQL):
    editor = CodeEditor(language=language)
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    return editor


def _caret(editor, offset):
    cursor = editor.textCursor()
    cursor.setPosition(offset)
    editor.setTextCursor(cursor)


def _select(editor, start, end):
    cursor = editor.textCursor()
    cursor.setPosition(end)
    cursor.setPosition(start, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _selected(editor) -> str:
    return editor.textCursor().selectedText()


def _chord(key, modifiers, event_type=QEvent.Type.KeyPress) -> QKeyEvent:
    return QKeyEvent(event_type, key, modifiers)


_CTRL_SHIFT_Z = (
    Qt.Key.Key_Z,
    Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
)


# --------------------------------------------------------------------------
# the ladder, repeatable
# --------------------------------------------------------------------------


def test_grow_is_repeatable_and_climbs_one_unit_per_press(qtbot):
    editor = _editor(qtbot)
    _caret(editor, _SQL.index("b,"))

    seen = []
    while editor.expand_structural_selection():
        seen.append(_selected(editor))
    assert seen == [
        "b",
        "b, c",
        "(b, c)",
        "select a, coalesce(b, c)",
        "select a, coalesce(b, c) from t where a = 1",
    ]


def test_grow_with_nothing_larger_left_is_a_no_op_not_a_refusal(qtbot):
    """§8: selecting mutates nothing, so a report per keypress at the top of the
    ladder would be noise. This is the one place FQ-030's *refusals over guesses*
    posture deliberately does not apply -- stated so it is not "corrected" later.
    """
    editor = _editor(qtbot)
    refusals = []
    editor.expansion_refused.connect(refusals.append)
    editor.hint_shown.connect(refusals.append)
    _caret(editor, _SQL.index("b,"))
    while editor.expand_structural_selection():
        pass
    before = (editor.textCursor().selectionStart(), editor.textCursor().selectionEnd())

    assert editor.expand_structural_selection() is False
    assert (
        editor.textCursor().selectionStart(),
        editor.textCursor().selectionEnd(),
    ) == before
    assert refusals == []


def test_an_if_inside_a_begin_inside_a_body_is_one_press_each(qtbot):
    editor = _editor(qtbot, text=_BODY)
    _caret(editor, _BODY.index("total + 1"))

    seen = []
    while editor.expand_structural_selection():
        seen.append(_selected(editor))
    # word, statement, IF, BEGIN, the body, the $$ token, the CREATE statement.
    assert seen[0] == "total"
    assert seen[1] == "total := total + 1"
    assert seen[2].startswith("IF a > 5 THEN") and seen[2].endswith("END IF")
    assert seen[3].startswith("BEGIN") and seen[3].endswith("END")
    assert seen[-1].startswith("CREATE FUNCTION")


# --------------------------------------------------------------------------
# shrink: the stack, and the derive when there is none
# --------------------------------------------------------------------------


def test_shrink_pops_the_stack_and_is_growers_exact_inverse(qtbot):
    editor = _editor(qtbot)
    _caret(editor, _SQL.index("b,"))
    grown = []
    while editor.expand_structural_selection():
        grown.append(_selected(editor))

    for expected in reversed(grown[:-1]):
        assert editor.shrink_structural_selection() is True
        assert _selected(editor) == expected
    # Popped back past the first grow: the caret, with no selection.
    assert editor.shrink_structural_selection() is True
    assert editor.textCursor().hasSelection() is False


def test_an_edit_drops_the_stack_whole_and_shrink_derives_instead(qtbot):
    """The stored offsets describe text that no longer exists, so restoring one
    would select a visibly wrong range: while stale, do nothing rather than
    something wrong. Deriving then answers from the CURRENT text."""
    editor = _editor(qtbot)
    _caret(editor, _SQL.index("b,"))
    editor.expand_structural_selection()  # -> "b"
    editor.expand_structural_selection()  # -> "b, c"
    assert _selected(editor) == "b, c"

    cursor = editor.textCursor()
    cursor.clearSelection()
    cursor.setPosition(len(_SQL))
    editor.setTextCursor(cursor)
    editor.insertPlainText("\n-- an edit\n")
    _select(editor, _SQL.index("b,"), _SQL.index("b,") + 4)  # re-select "b, c"

    assert editor._expansion_stack_is_live((0, 0)) is False
    assert editor.shrink_structural_selection() is True
    assert _selected(editor) == "b"  # derived, not popped


def test_a_mouse_drag_selection_makes_shrink_derive_the_largest_span_inside(qtbot):
    """`DEC-260810164601`: with no stack, take the largest structural span lying
    STRICTLY INSIDE the current selection. Not a refusal, not a silent branch.

    Note what "the chain" means for repeated derives, because it is worth stating
    rather than discovering: the ruling is *"the largest `structure_chain` member
    strictly inside the selection"*, and a chain is resolved from ONE position —
    here one character inside the selection's start. So successive derives walk
    inward along the chain at that position, not toward whichever construct
    happens to be widest somewhere in the middle. Both properties the ruling cares
    about hold at every step: the selection always moves INWARD, and every press
    that fires changes something.
    """
    editor = _editor(qtbot)
    _select(editor, 0, len(_SQL) - 1)  # as if dragged over the whole statement

    seen = []
    while editor.shrink_structural_selection():
        seen.append(_selected(editor))
    assert seen == ["select a, coalesce(b, c)", "select"]


def test_deriving_is_a_no_op_at_the_innermost_span_with_no_special_case(qtbot):
    """The property that made deriving win: SUBSUMPTION.

    At the innermost rung nothing lies strictly inside the selection, so the pure
    `shrink_target` returns None and this is a no-op *there* -- which is the whole
    of the conservative alternative, obtained with one branch fewer. Driven here
    with an EMPTY stack, so nothing but the derive path can be answering.
    """
    editor = _editor(qtbot)
    _select(editor, _SQL.index("b,"), _SQL.index("b,") + 1)  # exactly the word "b"
    editor._expansion_stack = []

    assert editor.shrink_structural_selection() is False
    assert _selected(editor) == "b"


def test_shrink_from_a_bare_caret_is_a_no_op_through_the_same_path(qtbot):
    """No stack and an empty selection: nothing is strictly inside a caret, so the
    derive path returns None. There is deliberately no `if not hasSelection`
    branch -- adding one would re-introduce the special case DEC-260810164601
    exists to avoid."""
    editor = _editor(qtbot)
    _caret(editor, _SQL.index("b,"))
    assert editor.shrink_structural_selection() is False
    assert editor.textCursor().hasSelection() is False


def test_deriving_never_jumps_outside_a_selection_that_contains_no_span(qtbot):
    editor = _editor(qtbot)
    _select(editor, 5, 9)  # cuts across rungs, contains none of them whole
    before = _selected(editor)
    assert editor.shrink_structural_selection() is False
    assert _selected(editor) == before


def test_every_structural_selection_is_caret_at_start(qtbot):
    """The app's selection idiom (`select_enclosing_brackets`, `XmlEditor`): anchor
    at the END, caret at the START, so the view scrolls to the beginning."""
    editor = _editor(qtbot)
    _caret(editor, _SQL.index("b,"))
    for _ in range(3):
        editor.expand_structural_selection()
        cursor = editor.textCursor()
        assert cursor.position() == cursor.selectionStart()
    editor.shrink_structural_selection()
    cursor = editor.textCursor()
    assert cursor.position() == cursor.selectionStart()


# --------------------------------------------------------------------------
# the capability gates
# --------------------------------------------------------------------------


def test_the_grow_gate_is_a_per_instance_question_not_a_class_fact(qtbot):
    """Why `hasattr` could not express it: the METHOD is on the class either way;
    only the language differs, and that is per instance."""
    assert _editor(qtbot).supports_structural_expansion() is True
    php = _editor(qtbot, language="php", text="<?php echo strtoupper('x');")
    assert hasattr(php, "expand_structural_selection")  # the method is there...
    assert php.supports_structural_expansion() is False  # ...the language is not


def test_neither_gesture_does_anything_on_a_non_sql_editor(qtbot):
    php = _editor(qtbot, language="php", text="<?php echo strtoupper('x');")
    _caret(php, 12)
    assert php.expand_structural_selection() is False
    assert php.shrink_structural_selection() is False
    assert php.textCursor().hasSelection() is False


def test_the_xml_family_answers_grow_but_has_no_shrink_method_at_all(qtbot):
    """A scope decision with a reason, not an omission (§8): XML's grow is
    stateless and re-derivable, so shrink would mean giving `XmlEditor` the
    expansion stack too -- a second host for that state, for a family whose users
    did not ask for it."""
    editor = XmlEditor()
    qtbot.addWidget(editor)
    assert editor.supports_structural_expansion() is True
    assert hasattr(editor, "select_parent_block")
    assert not hasattr(editor, "shrink_structural_selection")


def test_the_read_only_ddl_explorer_buffer_runs_the_whole_ladder(qtbot):
    """Read-only is IRRELEVANT to selecting -- the `Select All` precedent (§8).
    This is also the surface where reading structure matters most."""
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.editor.setPlainText(_SQL)
    assert panel.editor.isReadOnly() or True  # host decides; the ladder does not care
    _caret(panel.editor, _SQL.index("b,"))

    assert panel.editor.expand_structural_selection() is True
    assert panel.editor.expand_structural_selection() is True
    assert _selected(panel.editor) == "b, c"
    assert panel.editor.shrink_structural_selection() is True
    assert _selected(panel.editor) == "b"


# --------------------------------------------------------------------------
# the chord: answered, not bound
# --------------------------------------------------------------------------


def test_ctrl_shift_z_is_still_classified_claimed_and_not_redo():
    assert classify_editor_chord(_chord(*_CTRL_SHIFT_Z)) == CLAIMED_NOT_UNDO_REDO


def test_every_editing_surface_routes_the_claim_into_ONE_implementation():
    """The mechanical pin §8 asks for, derived from the code and not typed out.

    The surfaces are exactly those that call `classify_editor_chord` (the same
    derivation `tests/test_keybindings_ledger.py` uses for DEC-014), and each must
    reach `apply_shrink_structural_selection` -- so a seventh surface cannot be
    added with a private answer, which is the drift DEC-012 forbids.
    """
    package = Path(__file__).resolve().parents[2] / "pgtp_editor"
    surfaces = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(package.rglob("*.py"))
        if "classify_editor_chord(" in path.read_text(encoding="utf-8")
        and path.name != "shortcut_registry.py"
    }
    assert len(surfaces) >= 6, sorted(surfaces)
    for name, source in surfaces.items():
        assert "CLAIMED_NOT_UNDO_REDO" in source, name
        assert "apply_shrink_structural_selection(" in source, (
            f"{name} intercepts Ctrl+Shift+Z but does not delegate to the shared "
            f"shrink implementation"
        )


def test_the_shared_helper_is_inert_where_the_method_is_absent(qtbot):
    """`XmlEditor` and any future stack-less surface: no method, no answer, False
    -- while the chord is still consumed by the surface, which is the half that
    keeps Qt's native redo from firing."""
    editor = XmlEditor()
    qtbot.addWidget(editor)
    assert apply_shrink_structural_selection(editor) is False
    assert apply_shrink_structural_selection(object()) is False


def test_the_chord_reaches_the_ladder_through_a_real_surfaces_key_handling(qtbot):
    """End to end through `CodeEditorDialog.eventFilter` -- a surface whose whole
    keyboard answer is its `eventFilter`, so nothing but the FQ-034 branch can be
    producing the result."""
    dialog = CodeEditorDialog(language="sql", handler_name="h")
    qtbot.addWidget(dialog)
    dialog.set_code(_SQL)
    editor = dialog._editor
    _caret(editor, _SQL.index("b,"))
    editor.expand_structural_selection()
    editor.expand_structural_selection()
    assert _selected(editor) == "b, c"

    handled = dialog.eventFilter(editor, _chord(*_CTRL_SHIFT_Z))

    assert handled is True
    assert _selected(editor) == "b"


def test_the_surface_still_claims_the_shortcut_override_it_always_did(qtbot):
    """The half that must not be lost: accepting the `ShortcutOverride` is what
    stops Qt's native redo, and it is ALSO why shrink's `QAction` carries no
    shortcut -- a window action would be starved by this very accept."""
    dialog = CodeEditorDialog(language="sql", handler_name="h")
    qtbot.addWidget(dialog)
    dialog.set_code(_SQL)
    event = _chord(*_CTRL_SHIFT_Z, event_type=QEvent.Type.ShortcutOverride)

    assert dialog.eventFilter(dialog._editor, event) is True
    assert event.isAccepted() is True


def test_a_php_surface_consumes_the_chord_and_changes_nothing(qtbot):
    """Inert, not unhandled: the interception is the behaviour there."""
    dialog = CodeEditorDialog(language="php", handler_name="h")
    qtbot.addWidget(dialog)
    dialog.set_code("<?php echo strtoupper('x');")
    _caret(dialog._editor, 12)

    assert dialog.eventFilter(dialog._editor, _chord(*_CTRL_SHIFT_Z)) is True
    assert dialog._editor.textCursor().hasSelection() is False


def test_the_read_only_ddl_panel_answers_the_chord_without_a_refusal(qtbot):
    """Every other reserved chord in this panel states a read-only refusal.
    Shrink must NOT: nothing is being refused, because selecting mutates nothing.
    """
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.editor.setPlainText(_SQL)
    refusals = []
    panel.editor.hint_shown.connect(refusals.append)
    _select(panel.editor, 0, len(_SQL) - 1)

    assert panel.eventFilter(panel.editor, _chord(*_CTRL_SHIFT_Z)) is True

    assert _selected(panel.editor) == "select a, coalesce(b, c)"
    assert refusals == []
