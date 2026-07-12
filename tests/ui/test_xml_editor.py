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


from pgtp_editor.ui.xml_editor import _EditorGutter


def test_editor_has_a_gutter(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    assert isinstance(editor._gutter, _EditorGutter)


def test_gutter_width_grows_with_more_digits_in_line_count(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line\n" * 5)  # single-digit line count
    narrow_margin = editor.viewportMargins().left()

    editor.setPlainText("line\n" * 200)  # triple-digit line count
    wide_margin = editor.viewportMargins().left()

    assert wide_margin > narrow_margin


def test_gutter_geometry_matches_editor_contents_rect_height(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.resize(400, 300)
    editor.show()
    assert editor._gutter.height() == editor.contentsRect().height()


def test_toggle_fold_hides_only_contained_blocks(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail>\n    content\n  </Detail>\n</Page>"
    editor.setPlainText(text)

    outer_block = editor.document().findBlockByNumber(0)  # "<Page>"
    editor._toggle_fold(outer_block)

    # Lines 1-3 (Detail open, content, Detail close) are hidden; lines 0 and
    # 4 (Page open/close) stay visible.
    assert editor.document().findBlockByNumber(0).isVisible() is True
    assert editor.document().findBlockByNumber(1).isVisible() is False
    assert editor.document().findBlockByNumber(2).isVisible() is False
    assert editor.document().findBlockByNumber(3).isVisible() is False
    assert editor.document().findBlockByNumber(4).isVisible() is True


def test_toggle_fold_again_reveals_hidden_blocks(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail>\n    content\n  </Detail>\n</Page>"
    editor.setPlainText(text)

    outer_block = editor.document().findBlockByNumber(0)
    editor._toggle_fold(outer_block)
    editor._toggle_fold(outer_block)

    for i in range(5):
        assert editor.document().findBlockByNumber(i).isVisible() is True


def test_nested_fold_survives_outer_collapse_and_reexpand(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = (
        "<Page>\n"
        "  <Detail>\n"
        "    <Column>\n"
        "      x\n"
        "    </Column>\n"
        "  </Detail>\n"
        "</Page>"
    )
    editor.setPlainText(text)

    detail_block = editor.document().findBlockByNumber(1)  # "  <Detail>"
    editor._toggle_fold(detail_block)  # collapse inner Column region first
    assert editor.document().findBlockByNumber(3).isVisible() is False  # "x"

    page_block = editor.document().findBlockByNumber(0)
    editor._toggle_fold(page_block)  # collapse outer Page region
    editor._toggle_fold(page_block)  # re-expand outer Page region

    # Inner Column region remains collapsed even after the outer round-trip.
    assert editor.document().findBlockByNumber(3).isVisible() is False


def test_single_line_element_has_no_foldable_region(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Page></Page>")

    only_block = editor.document().findBlockByNumber(0)
    foldable = editor._foldable_region_starting_at(only_block)
    assert foldable is None
