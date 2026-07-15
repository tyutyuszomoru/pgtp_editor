from PySide6.QtWidgets import QApplication, QPlainTextEdit

from pgtp_editor.ui.xml_editor import XmlEditor
from pgtp_editor.ui.xml_structure import scan as _scan, enclosing_tag_span as _enc, parent_tag_span as _par


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


from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QMouseEvent, QTextCursor

def test_gutter_click_on_fold_glyph_toggles_fold(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.resize(400, 300)
    editor.show()
    text = "<Page>\n  <Detail>\n    content\n  </Detail>\n</Page>"
    editor.setPlainText(text)

    outer_block = editor.document().findBlockByNumber(0)
    top = editor.blockBoundingGeometry(outer_block).translated(editor.contentOffset()).top()
    glyph_point = QPoint(4, int(top) + 2)

    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        glyph_point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    editor._gutter.mousePressEvent(event)

    assert editor.document().findBlockByNumber(2).isVisible() is False


def test_set_line_wrap_enabled_true_sets_widget_width_mode(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.set_line_wrap_enabled(True)
    assert editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth


def test_set_line_wrap_enabled_false_reverts_to_no_wrap(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.set_line_wrap_enabled(True)
    editor.set_line_wrap_enabled(False)
    assert editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap


def test_current_line_highlight_is_single_extra_selection(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two\nline three")

    cursor = editor.textCursor()
    cursor.setPosition(len("line one") + 1)  # move onto "line two"
    editor.setTextCursor(cursor)

    assert len(editor.extraSelections()) == 1


def test_current_line_highlight_moves_with_cursor(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two\nline three")

    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    # Hold a reference to the extraSelections() list before indexing into it:
    # PySide6 frees the underlying C++ ExtraSelection/QTextCursor objects
    # once the temporary list itself is garbage-collected, which can happen
    # before a chained `.extraSelections()[0].cursor...` expression finishes
    # reading from it.
    first_selections = editor.extraSelections()
    first_selection_block = first_selections[0].cursor.blockNumber()

    cursor.setPosition(len("line one") + 1)
    editor.setTextCursor(cursor)
    second_selections = editor.extraSelections()
    second_selection_block = second_selections[0].cursor.blockNumber()

    assert first_selection_block == 0
    assert second_selection_block == 1


def test_auto_indent_plain_inherit_case(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("  <Detail>")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    qtbot.keyClick(editor, Qt.Key.Key_Return)

    lines = editor.toPlainText().split("\n")
    assert lines[1] == "  "


def test_auto_indent_after_opening_tag_adds_one_level(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Page>\n  <Detail>")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    qtbot.keyClick(editor, Qt.Key.Key_Return)

    lines = editor.toPlainText().split("\n")
    assert lines[2] == "    "  # "  " inherited + "  " one more level


def test_typing_less_than_auto_closes_with_greater_than(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setFocus()

    qtbot.keyClicks(editor, "<")

    assert editor.toPlainText() == "<>"
    assert editor.textCursor().position() == 1


def test_typing_quote_after_equals_auto_closes(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setFocus()

    qtbot.keyClicks(editor, "fileName=")
    qtbot.keyClicks(editor, '"')

    assert editor.toPlainText() == 'fileName=""'
    assert editor.textCursor().position() == len('fileName="')


def test_typing_apostrophe_after_equals_auto_closes(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setFocus()

    qtbot.keyClicks(editor, "fileName=")
    qtbot.keyClicks(editor, "'")

    assert editor.toPlainText() == "fileName=''"
    assert editor.textCursor().position() == len("fileName='")


def test_typing_quote_not_after_equals_does_not_auto_close(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setFocus()

    qtbot.keyClicks(editor, 'hello"')

    assert editor.toPlainText() == 'hello"'


def test_completing_opening_tag_auto_inserts_matching_close_tag(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setFocus()

    # Type "<Page" then the auto-closed ">" is already present from the "<"
    # auto-close; type through it with ">".
    qtbot.keyClicks(editor, "<Page")
    qtbot.keyClick(editor, Qt.Key.Key_Greater)

    assert editor.toPlainText() == "<Page></Page>"
    assert editor.textCursor().position() == len("<Page>")


def test_self_closing_tag_does_not_get_a_matching_close_tag(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setFocus()
    editor.setPlainText("<Page/")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    qtbot.keyClick(editor, Qt.Key.Key_Greater)

    assert editor.toPlainText() == "<Page/>"


def test_typing_greater_than_types_through_only_the_auto_inserted_one(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setFocus()

    qtbot.keyClicks(editor, "<Tag")
    qtbot.keyClick(editor, Qt.Key.Key_Greater)

    # The auto-inserted '>' from the "<" auto-close is typed through (no
    # duplicate '>', cursor moves past it); _maybe_insert_closing_tag then
    # fires as usual, appending the matching close tag.
    assert editor.toPlainText() == "<Tag></Tag>"
    assert editor.textCursor().position() == len("<Tag>")


def test_typing_greater_than_before_preexisting_greater_than_inserts_literally(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setFocus()

    editor.setPlainText("<Page>")
    cursor = editor.textCursor()
    cursor.setPosition(len("<Page"))  # right before the real, pre-existing '>'
    editor.setTextCursor(cursor)

    qtbot.keyClick(editor, Qt.Key.Key_Greater)

    # This '>' was never auto-inserted by this editor, so typing '>' here
    # must insert literally rather than being swallowed as "type through" --
    # NOT "<Page></Page>" (the bug this test guards against).
    assert editor.toPlainText() == "<Page>>"


def test_deleting_auto_closed_greater_than_then_retyping_it_still_auto_closes(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setFocus()

    qtbot.keyClicks(editor, "<Tag")
    qtbot.keyClick(editor, Qt.Key.Key_Delete)  # deletes the auto-inserted '>'
    qtbot.keyClicks(editor, ">")  # user retypes '>' manually, nothing follows

    # Even though this '>' wasn't "typed through" (there was nothing after
    # the cursor to type through), it's still the '>' that freshly completes
    # this opening tag, so the matching close tag must still be auto-inserted.
    assert editor.toPlainText() == "<Tag></Tag>"


def test_highlight_error_line_scrolls_and_highlights(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two\nline three\nline four")

    editor.highlight_error_line(3)

    assert editor.textCursor().blockNumber() == 2  # 1-based line 3 -> 0-based block 2
    selections = editor.extraSelections()
    assert len(selections) == 1
    assert selections[0].cursor.blockNumber() == 2
    assert selections[0].format.background().color() == editor._error_line_color


def test_highlight_error_line_overrides_current_line_highlight(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two\nline three")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)  # current-line highlight now on line 0

    editor.highlight_error_line(3)

    # Only the error-line selection survives -- current-line highlighting's
    # own handler ran first (as a side effect of setTextCursor inside
    # highlight_error_line) and was then overwritten.
    selections = editor.extraSelections()
    assert len(selections) == 1
    assert selections[0].cursor.blockNumber() == 2


def test_navigate_to_line_scrolls_and_highlights_with_navigation_color(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two\nline three\nline four")

    editor.navigate_to_line(3)

    assert editor.textCursor().blockNumber() == 2  # 1-based line 3 -> 0-based block 2
    selections = editor.extraSelections()
    assert len(selections) == 1
    assert selections[0].cursor.blockNumber() == 2
    assert selections[0].format.background().color() == editor._navigation_highlight_color
    # Distinct from the Tier-1 error color, so a Properties-panel jump is
    # never visually confused with a parse-failure fallback.
    assert editor._navigation_highlight_color != editor._error_line_color


def test_navigation_highlight_cleared_on_next_cursor_move(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two\nline three\nline four")

    editor.navigate_to_line(2)
    # Immediately after navigation, the nav band is the sole overriding
    # selection.
    nav_color = editor._navigation_highlight_color
    after_nav = editor.extraSelections()
    after_nav_colors = [sel.format.background().color() for sel in after_nav]
    assert len(after_nav) == 1
    assert nav_color in after_nav_colors

    # A subsequent independent cursor move to a different line must wipe the
    # navigation band -- it is a one-shot, not a sticky selection.
    cursor = editor.textCursor()
    cursor.setPosition(0)  # move onto line 0
    editor.setTextCursor(cursor)

    after_move_colors = [
        sel.format.background().color() for sel in editor.extraSelections()
    ]
    assert nav_color not in after_move_colors
    assert editor._current_line_color in after_move_colors
    assert editor._oneshot_selection is None


def test_error_highlight_cleared_on_next_cursor_move(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two\nline three\nline four")

    editor.highlight_error_line(2)
    error_color = editor._error_line_color
    after_error = editor.extraSelections()
    after_error_colors = [sel.format.background().color() for sel in after_error]
    assert len(after_error) == 1
    assert error_color in after_error_colors

    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)

    after_move_colors = [
        sel.format.background().color() for sel in editor.extraSelections()
    ]
    assert error_color not in after_move_colors
    assert editor._current_line_color in after_move_colors
    assert editor._oneshot_selection is None


def test_line_text_returns_the_plain_text_of_the_requested_line(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Page fileName="x" caption="Equipment">\nline two')

    assert editor.line_text(1) == '<Page fileName="x" caption="Equipment">'
    assert editor.line_text(2) == "line two"


def test_line_text_out_of_range_returns_empty_string(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("only one line")

    assert editor.line_text(99) == ""


def test_select_range_on_line_selects_exact_substring(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Page fileName="x" caption="Equipment">')
    line = editor.line_text(1)
    start = line.index('caption="Equipment"')
    end = start + len('caption="Equipment"')

    editor.select_range_on_line(1, start, end)

    cursor = editor.textCursor()
    assert cursor.selectedText() == 'caption="Equipment"'
    selections = editor.extraSelections()
    assert len(selections) == 1
    assert selections[0].cursor.selectedText() == 'caption="Equipment"'


def test_refresh_extra_selections_combiner_exists_and_current_line_only(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    # With only the current-line contribution active, exactly one selection.
    assert len(editor.extraSelections()) == 1
    assert editor._matching_tag_selections == []
    assert editor._oneshot_selection is None


def test_refresh_extra_selections_current_line_uses_named_list(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    assert len(editor._current_line_selections) == 1


def _matching_tag_selection_count(editor):
    """Number of extra-selections whose background is the matching-tag color."""
    color = editor._matching_tag_color
    return sum(
        1
        for sel in editor.extraSelections()
        if sel.format.background().color() == color
    )


def test_matching_tag_highlight_on_open_tag_highlights_both(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail>x</Detail>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("<Detail>") + 1)  # inside the open tag
    editor.setTextCursor(cursor)
    assert _matching_tag_selection_count(editor) == 2


def test_matching_tag_highlight_on_close_tag_highlights_both(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail>x</Detail>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("</Detail>") + 1)  # inside the close tag
    editor.setTextCursor(cursor)
    assert _matching_tag_selection_count(editor) == 2


def test_matching_tag_highlight_absent_when_cursor_in_content(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail>content</Detail>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("content"))  # in text content, not on a tag
    editor.setTextCursor(cursor)
    assert _matching_tag_selection_count(editor) == 0
    # Current-line highlight is still present and unaffected.
    assert len(editor._current_line_selections) == 1


def test_matching_tag_highlight_coexists_with_current_line(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail>x</Detail>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("<Detail>") + 1)
    editor.setTextCursor(cursor)
    colors = [sel.format.background().color() for sel in editor.extraSelections()]
    assert editor._current_line_color in colors
    assert editor._matching_tag_color in colors


def test_matching_tag_highlight_cleared_when_cursor_moves_off_tag(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail>content</Detail>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("<Detail>") + 1)
    editor.setTextCursor(cursor)
    assert _matching_tag_selection_count(editor) == 2
    cursor.setPosition(text.index("content"))
    editor.setTextCursor(cursor)
    assert _matching_tag_selection_count(editor) == 0


def test_matching_tag_highlight_none_on_self_closing_tag(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Column/>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("<Column/>") + 2)  # inside the self-closing token
    editor.setTextCursor(cursor)
    # A self-closing tag has no separate counterpart to highlight.
    assert _matching_tag_selection_count(editor) == 0


def test_select_enclosing_block_selects_full_element_including_delimiters(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail>\n    x\n  </Detail>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("x"))  # inside Detail's content
    editor.setTextCursor(cursor)

    editor.select_enclosing_block()

    expected = text[text.index("<Detail>"):text.index("</Detail>") + len("</Detail>")]
    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected == expected
    # A.1: caret sits at the block START (selectionStart) while the whole
    # block stays selected, so the view shows the start of the selection.
    assert editor.textCursor().position() == editor.textCursor().selectionStart()
    assert editor.textCursor().position() == text.index("<Detail>")


def test_select_enclosing_block_on_self_closing_selects_whole_token(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Column/>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("<Column/>") + 2)
    editor.setTextCursor(cursor)

    editor.select_enclosing_block()

    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected == "<Column/>"
    assert editor.textCursor().position() == editor.textCursor().selectionStart()
    assert editor.textCursor().position() == text.index("<Column/>")


def test_select_enclosing_block_in_intersibling_whitespace_selects_parent(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail></Detail>\n  <Detail></Detail>\n</Page>"
    editor.setPlainText(text)
    first_close_end = text.index("</Detail>") + len("</Detail>")
    cursor = editor.textCursor()
    cursor.setPosition(first_close_end + 1)  # in the "\n  " gap between siblings
    editor.setTextCursor(cursor)

    editor.select_enclosing_block()

    expected = text  # the whole <Page>...</Page>
    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected == expected


def test_select_enclosing_block_outside_any_element_is_noop(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "  <Page></Page>  "
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(0)  # leading whitespace, outside every element
    editor.setTextCursor(cursor)

    editor.select_enclosing_block()

    assert editor.textCursor().hasSelection() is False


def test_copy_folded_block_yields_full_text(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(
        '<Page fileName="a">\n'
        '  <Detail tableName="b">\n'
        '    <Page fileName="c">\n'
        '      <ColumnPresentation fieldName="x" caption="X"/>\n'
        '      <ColumnPresentation fieldName="y" caption="Y"/>\n'
        "    </Page>\n"
        "  </Detail>\n"
        "</Page>\n"
    )
    full_text = editor.toPlainText()
    inner_page_open = full_text.index('<Page fileName="c"')
    inner_close_end = full_text.index("</Page>", inner_page_open) + len("</Page>")
    expected_block_text = full_text[inner_page_open:inner_close_end]

    # Fold the inner <Page> region (hides its two ColumnPresentation lines).
    block = editor.document().findBlock(inner_page_open)
    editor._toggle_fold(block)

    # Select the folded block via Ctrl+Shift+B mechanism (offset-based).
    cursor = editor.textCursor()
    cursor.setPosition(inner_page_open)
    editor.setTextCursor(cursor)
    editor.select_enclosing_block()

    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected == expected_block_text, (
        "Selecting a folded block must yield its FULL underlying text, "
        "not the visually-collapsed content."
    )

    editor.copy()
    clipboard_text = QApplication.clipboard().text()  # system clipboard uses '\n'
    assert clipboard_text == expected_block_text


def test_copy_nested_folds_outer_block_yields_full_text(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(
        '<Page fileName="a">\n'
        '  <Detail tableName="b">\n'
        '    <Page fileName="c">\n'
        '      <ColumnPresentation fieldName="x" caption="X"/>\n'
        "    </Page>\n"
        "  </Detail>\n"
        "</Page>\n"
    )
    full_text = editor.toPlainText()
    outer_page_open = full_text.index('<Page fileName="a"')
    outer_close_end = full_text.rindex("</Page>") + len("</Page>")
    expected_block_text = full_text[outer_page_open:outer_close_end]

    # Independently collapse the inner <Page> then the <Detail> region.
    inner_page_open = full_text.index('<Page fileName="c"')
    editor._toggle_fold(editor.document().findBlock(inner_page_open))
    detail_open = full_text.index("<Detail")
    editor._toggle_fold(editor.document().findBlock(detail_open))

    cursor = editor.textCursor()
    cursor.setPosition(outer_page_open)
    editor.setTextCursor(cursor)
    editor.select_enclosing_block()

    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected == expected_block_text

    editor.copy()
    assert QApplication.clipboard().text() == expected_block_text


def test_select_parent_block_from_fresh_cursor_selects_one_level_up(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail>\n    <Column>x</Column>\n  </Detail>\n</Page>"
    editor.setPlainText(text)
    position = text.index("x")  # inside <Column> content
    cursor = editor.textCursor()
    cursor.setPosition(position)
    editor.setTextCursor(cursor)

    editor.select_parent_block()

    # Independently compute the expected parent (Detail) span.
    spans = _scan(text)
    enclosing = _enc(text, position)  # Column
    parent = _par(spans, enclosing)   # Detail
    expected = text[parent.open_start:parent.close_end]
    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected == expected
    assert expected == text[text.index("<Detail>"):text.index("</Detail>") + len("</Detail>")]
    # A.1: parent-block selection also lands caret-at-start.
    assert editor.textCursor().position() == editor.textCursor().selectionStart()
    assert editor.textCursor().position() == parent.open_start


def test_select_parent_block_repeated_presses_walk_up_levels(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail>\n    <Column>x</Column>\n  </Detail>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("x"))
    editor.setTextCursor(cursor)

    editor.select_parent_block()  # -> Detail
    first = editor.textCursor().selectedText().replace(" ", "\n")
    assert first == text[text.index("<Detail>"):text.index("</Detail>") + len("</Detail>")]

    editor.select_parent_block()  # -> Page (the parent of Detail)
    second = editor.textCursor().selectedText().replace(" ", "\n")
    assert second == text  # whole <Page>...</Page>

    editor.select_parent_block()  # Page is top-level: no-op, selection unchanged
    third = editor.textCursor().selectedText().replace(" ", "\n")
    assert third == second


def test_select_parent_block_at_top_level_is_noop_not_select_all(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail>x</Detail>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("<Page>") + 1)  # inside the top-level Page's open tag
    editor.setTextCursor(cursor)

    editor.select_parent_block()

    # Depth-0 element has no parent: no-op. Explicitly NOT "select all".
    assert editor.textCursor().hasSelection() is False
    assert editor.textCursor().selectedText() != text


def test_select_parent_block_outside_any_element_is_noop(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "  <Page></Page>  "
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)

    editor.select_parent_block()

    assert editor.textCursor().hasSelection() is False


from PySide6.QtCore import QPoint as _QPoint, Qt as _Qt  # noqa: E402
from PySide6.QtGui import QTextCursor as _QTextCursor  # noqa: E402
from PySide6.QtTest import QTest as _QTest  # noqa: E402


def test_line_clicked_signal_exists():
    # Class-level Signal is present and typed for one int argument.
    assert hasattr(XmlEditor, "line_clicked")


def test_mouse_release_emits_one_based_line_from_cursor(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two\nline three\nline four")

    # Place the cursor on the 3rd block (0-based blockNumber 2) so the
    # override reads it after super() runs. We drive mouseReleaseEvent
    # directly with a synthetic position on that line's rect.
    block = editor.document().findBlockByNumber(2)
    cursor = _QTextCursor(block)
    editor.setTextCursor(cursor)

    emitted = []
    editor.line_clicked.connect(emitted.append)

    rect = editor.cursorRect(editor.textCursor())
    pos = rect.center()
    _QTest.mouseClick(editor.viewport(), _Qt.MouseButton.LeftButton, _Qt.KeyboardModifier.NoModifier, pos)

    assert emitted, "line_clicked should have fired on a left mouse release"
    # Whatever line the click landed on, it must be reported 1-based and match
    # the post-click cursor's own block number + 1.
    assert emitted[-1] == editor.textCursor().blockNumber() + 1


def test_right_click_does_not_emit_line_clicked(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two")

    emitted = []
    editor.line_clicked.connect(emitted.append)

    rect = editor.cursorRect(editor.textCursor())
    _QTest.mouseClick(
        editor.viewport(), _Qt.MouseButton.RightButton, _Qt.KeyboardModifier.NoModifier, rect.center()
    )
    assert emitted == []


# --- Phase 1: read-only Caption Mode behavior -----------------------------

from PySide6.QtCore import Qt as _Qt2, QEvent as _QEvent
from PySide6.QtGui import QKeyEvent as _QKeyEvent


def _send_key(editor, key, text="", modifiers=_Qt2.KeyboardModifier.NoModifier):
    event = _QKeyEvent(_QEvent.Type.KeyPress, key, modifiers, text)
    editor.keyPressEvent(event)


def test_readonly_text_keypress_emits_signal_and_leaves_text_unchanged(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Page/>")
    editor.setReadOnly(True)
    emitted = []
    editor.read_only_edit_attempted.connect(lambda: emitted.append(True))

    _send_key(editor, _Qt2.Key.Key_A, "a")

    assert emitted == [True]
    assert editor.toPlainText() == "<Page/>"


def test_readonly_backspace_and_paste_emit_signal(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Page/>")
    editor.setReadOnly(True)
    emitted = []
    editor.read_only_edit_attempted.connect(lambda: emitted.append(True))

    _send_key(editor, _Qt2.Key.Key_Backspace)
    _send_key(editor, _Qt2.Key.Key_Delete)
    _send_key(editor, _Qt2.Key.Key_Return)
    _send_key(editor, _Qt2.Key.Key_V, "v", _Qt2.KeyboardModifier.ControlModifier)

    assert len(emitted) == 4
    assert editor.toPlainText() == "<Page/>"


def test_readonly_navigation_key_does_not_emit(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Page/>")
    editor.setReadOnly(True)
    emitted = []
    editor.read_only_edit_attempted.connect(lambda: emitted.append(True))

    _send_key(editor, _Qt2.Key.Key_Right)
    _send_key(editor, _Qt2.Key.Key_Down)

    assert emitted == []


def test_editable_keypress_does_not_emit_and_mutates_text(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("")
    assert editor.isReadOnly() is False
    emitted = []
    editor.read_only_edit_attempted.connect(lambda: emitted.append(True))

    _send_key(editor, _Qt2.Key.Key_A, "a")

    assert emitted == []
    assert editor.toPlainText() == "a"


# --- A.2: right-click "Find" on a selection --------------------------------

def _select_range(editor, start, end):
    cursor = editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, _QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def test_find_selected_text_signal_exists():
    assert hasattr(XmlEditor, "find_selected_text")


def test_context_menu_has_find_action_at_top_when_selection(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>hello</Page>"
    editor.setPlainText(text)
    _select_range(editor, text.index("hello"), text.index("hello") + len("hello"))

    menu = editor._build_context_menu()
    actions = menu.actions()
    assert actions, "menu should not be empty"
    assert actions[0].text() == "Find"


def test_context_menu_has_checkable_wrap_lines_action(qtbot):
    from PySide6.QtWidgets import QPlainTextEdit

    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Page>hello</Page>")

    menu = editor._build_context_menu()
    wrap_action = next((a for a in menu.actions() if a.text() == "Wrap Lines"), None)
    assert wrap_action is not None
    assert wrap_action.isCheckable() is True
    # Default editor has no wrap, so the action reflects unchecked.
    assert wrap_action.isChecked() is False

    wrap_action.trigger()
    assert editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth

    # Rebuilding the menu reflects the now-enabled wrap state.
    menu2 = editor._build_context_menu()
    wrap_action2 = next(a for a in menu2.actions() if a.text() == "Wrap Lines")
    assert wrap_action2.isChecked() is True
    wrap_action2.trigger()
    assert editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap


def test_context_menu_has_no_find_action_without_selection(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Page>hello</Page>")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)

    menu = editor._build_context_menu()
    assert all(a.text() != "Find" for a in menu.actions())


def test_find_action_emits_find_selected_text_with_selection(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>hello</Page>"
    editor.setPlainText(text)
    _select_range(editor, text.index("hello"), text.index("hello") + len("hello"))

    menu = editor._build_context_menu()
    find_action = next(a for a in menu.actions() if a.text() == "Find")

    with qtbot.waitSignal(editor.find_selected_text, timeout=1000) as blocker:
        find_action.trigger()
    assert blocker.args == ["hello"]


def test_find_action_collapses_multiline_paragraph_separators(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  hi\n</Page>"
    editor.setPlainText(text)
    _select_range(editor, 0, len(text))

    menu = editor._build_context_menu()
    find_action = next(a for a in menu.actions() if a.text() == "Find")
    with qtbot.waitSignal(editor.find_selected_text, timeout=1000) as blocker:
        find_action.trigger()
    emitted = blocker.args[0]
    # QTextCursor.selectedText() joins lines with U+2029; the emitted term
    # must contain no paragraph separators (collapsed to spaces).
    assert " " not in emitted
