from PySide6.QtWidgets import QPlainTextEdit

from pgtp_editor.ui.xml_editor import XmlEditor


def test_xml_editor_is_a_plain_text_edit(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    assert isinstance(editor, QPlainTextEdit)


def test_xml_editor_default_line_wrap_is_off(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    assert editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap


def test_xml_editor_set_plain_text_round_trips(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Page></Page>")
    assert editor.toPlainText() == "<Page></Page>"


from PySide6.QtGui import QTextCharFormat

from pgtp_editor.ui.xml_editor import XmlSyntaxHighlighter


def _format_at(editor, position):
    block = editor.document().findBlock(position)
    layout = block.layout()
    offset_in_block = position - block.position()
    formats = layout.formats()
    for fmt_range in formats:
        if fmt_range.start <= offset_in_block < fmt_range.start + fmt_range.length:
            # Copy-construct: PySide6 frees the underlying C++ object behind
            # fmt_range.format once the temporary `formats` list this came
            # from is garbage-collected, which can happen before the caller
            # is done reading from the returned format. Wrapping it in a new
            # QTextCharFormat forces an eager copy so it outlives `formats`.
            return QTextCharFormat(fmt_range.format)
    return QTextCharFormat()


def test_highlighter_is_attached_to_document(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    assert isinstance(editor._highlighter, XmlSyntaxHighlighter)
    assert editor._highlighter.document() is editor.document()


def test_tag_name_and_attribute_name_get_distinct_formats(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Page fileName="foo">'
    editor.setPlainText(text)

    tag_name_format = _format_at(editor, text.index("Page"))
    attr_name_format = _format_at(editor, text.index("fileName"))
    attr_value_format = _format_at(editor, text.index('"foo"') + 1)

    assert tag_name_format.foreground().color() != attr_name_format.foreground().color()
    assert attr_name_format.foreground().color() != attr_value_format.foreground().color()
    assert tag_name_format.foreground().color() != attr_value_format.foreground().color()


def test_unclosed_quote_propagates_string_format_to_next_line(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Page fileName="unterminated\nsecond line ordinary text'
    editor.setPlainText(text)

    second_line_start = text.index("\n") + 1
    fmt = _format_at(editor, second_line_start + 3)  # inside "second"
    assert fmt.foreground().color() == editor._highlighter._string_format.foreground().color()


def test_closing_the_quote_reverts_second_line_format(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Page fileName="unterminated\nsecond line ordinary text'
    editor.setPlainText(text)

    # Now fix it: add the missing closing quote on line 1.
    cursor = editor.textCursor()
    cursor.setPosition(text.index("unterminated") + len("unterminated"))
    editor.setTextCursor(cursor)
    editor.insertPlainText('"')

    fixed_text = editor.toPlainText()
    second_line_start = fixed_text.index("\n") + 1
    fmt = _format_at(editor, second_line_start + 3)
    assert fmt.foreground().color() != editor._highlighter._string_format.foreground().color()
