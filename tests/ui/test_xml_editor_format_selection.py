"""Format Selection on an XML surface (spec §18.4 part C).

One gesture, two engines, **dispatched by host surface**: an `XmlEditor` wires
`xmlfmt` and can never reach the SQL engine, because a text-sniffing dispatcher
would eventually guess wrong on a selection that looks like both
(`<x>select 1</x>`).
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from pgtp_editor.ui import format_settings
from pgtp_editor.ui.xml_editor import XmlEditor
from pgtp_editor.xmlfmt import XmlFormatConfig

MESSY = '<Root>\n<Page name="a">\n<Field name="x"/>\n</Page>\n</Root>\n'


@pytest.fixture
def editor(qtbot):
    widget = XmlEditor()
    qtbot.addWidget(widget)
    widget.show()
    return widget


def _select(editor, start, end):
    cursor = editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def _select_all(editor):
    _select(editor, 0, len(editor.toPlainText()))


def test_it_reindents_the_selection_by_element_depth(editor):
    editor.setPlainText(MESSY)
    _select_all(editor)

    assert editor.format_selection() is True

    assert editor.toPlainText() == (
        '<Root>\n  <Page name="a">\n    <Field name="x"/>\n  </Page>\n</Root>\n'
    )


def test_reformatting_is_one_undo_step(editor):
    editor.setPlainText(MESSY)
    _select_all(editor)

    editor.format_selection()
    editor.undo()

    assert editor.toPlainText() == MESSY


def test_it_is_idempotent(editor):
    editor.setPlainText(MESSY)
    _select_all(editor)
    editor.format_selection()
    once = editor.toPlainText()

    _select_all(editor)
    editor.format_selection()

    assert editor.toPlainText() == once


def test_the_base_depth_comes_from_the_selections_position_in_the_document(editor):
    # Only the inner element is selected; its indentation must follow its
    # ancestors in the document, not its own first line (the one place the XML
    # engine deliberately diverges from the SQL engine).
    editor.setPlainText(MESSY)
    # From the line break before the inner element (a selection that starts mid
    # line keeps its first tag where it sits -- the engine only re-cuts a
    # whitespace run that already contains a break, which is what makes the
    # gesture idempotent).
    start = MESSY.index("<Field") - 1
    _select(editor, start, start + len('\n<Field name="x"/>'))

    editor.format_selection()

    assert '    <Field name="x"/>' in editor.toPlainText()


def test_an_opening_tag_is_never_broken_and_element_text_is_never_touched(editor):
    # §2's two consumers: line-anchored edits rely on one-line opening tags, and
    # event-handler bodies are entity-escaped text inside elements.
    text = '<Root>\n<OnClick a="1" b="2" c="3">if (x) { y(); }</OnClick>\n</Root>\n'
    editor.setPlainText(text)
    _select_all(editor)

    editor.format_selection()

    assert '<OnClick a="1" b="2" c="3">if (x) { y(); }</OnClick>' in editor.toPlainText()


def test_it_honours_the_configured_indent_width(editor, tmp_path):
    store = QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat)
    format_settings.save_configs(
        format_settings.load_sql_config(store), XmlFormatConfig(indent_unit="    "), store
    )
    format_settings.use_settings(store)
    try:
        editor.setPlainText(MESSY)
        _select_all(editor)
        editor.format_selection()
    finally:
        format_settings.use_settings(None)

    assert '    <Page name="a">' in editor.toPlainText()


def test_a_refusal_leaves_the_buffer_byte_for_byte_unchanged(editor, qtbot):
    mis_nested = "<a>\n<b>\n</a>\n</b>\n"
    editor.setPlainText(mis_nested)
    _select_all(editor)

    with qtbot.waitSignal(editor.format_refused, timeout=200) as caught:
        assert editor.format_selection() is False

    assert editor.toPlainText() == mis_nested
    issues = caught.args[0]
    assert issues and all(issue.fatal for issue in issues)


def test_a_refusal_underlines_the_offending_span(editor):
    editor.setPlainText("<a>\n<b>\n</a>\n</b>\n")
    _select_all(editor)

    editor.format_selection()

    assert len(editor.extraSelections()) == 1


def test_a_read_only_buffer_reuses_the_existing_hint_and_emits_no_xml_row(editor, qtbot):
    editor.setPlainText(MESSY)
    _select_all(editor)
    editor.setReadOnly(True)
    refusals = []
    editor.format_refused.connect(refusals.append)

    with qtbot.waitSignal(editor.read_only_edit_attempted, timeout=200):
        assert editor.format_selection() is False

    assert editor.toPlainText() == MESSY
    assert refusals == []  # no `[XML]` row: FQ-021 already lists the reasons


def test_without_a_selection_the_gesture_is_a_silent_no_op(editor, qtbot):
    editor.setPlainText(MESSY)
    refusals = []
    editor.format_refused.connect(refusals.append)

    assert editor.format_selection() is False

    assert editor.toPlainText() == MESSY
    assert refusals == []


def test_the_shortcut_is_enabled_only_with_a_selection(editor):
    editor.setPlainText(MESSY)
    assert editor._format_shortcut.isEnabled() is False
    _select_all(editor)
    assert editor._format_shortcut.isEnabled() is True


def test_ctrl_alt_f_triggers_it(editor):
    editor.setPlainText(MESSY)
    _select_all(editor)
    editor.setFocus()

    QTest.keyClick(
        editor,
        Qt.Key.Key_F,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )

    assert editor.toPlainText() != MESSY


def test_the_context_menu_carries_the_command_form(editor):
    editor.setPlainText(MESSY)
    _select_all(editor)

    labels = [action.text() for action in editor._build_context_menu().actions()]

    assert "Format Selection" in labels


def test_the_context_menu_entry_is_disabled_without_a_selection(editor):
    editor.setPlainText(MESSY)
    action = next(
        a for a in editor._build_context_menu().actions() if a.text() == "Format Selection"
    )
    assert action.isEnabled() is False


def test_the_context_menu_entry_carries_no_shortcut_of_its_own(editor):
    # The panel-local QShortcut is the single keyboard host (DEC-004/BUG-046: two
    # hosts make Qt fire neither).
    editor.setPlainText(MESSY)
    _select_all(editor)
    action = next(
        a for a in editor._build_context_menu().actions() if a.text() == "Format Selection"
    )
    assert action.shortcut().isEmpty()
