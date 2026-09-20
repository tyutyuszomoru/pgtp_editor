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
    # The fold zone now sits right of the bookmark strip, so the click x is
    # offset past _BOOKMARK_STRIP_WIDTH into the fold glyph column.
    from pgtp_editor.ui.xml_editor import _BOOKMARK_STRIP_WIDTH as _BSW
    glyph_point = QPoint(_BSW + 4, int(top) + 2)

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


def test_readonly_ctrl_a_selects_all_instead_of_emitting_the_hint(qtbot):
    """FQ-015: a Ctrl chord is a COMMAND, never typing. `QKeyEvent.text()` for
    Ctrl+A is the bare letter on some platforms (and under `QTest.keyClick`), and
    classifying that as an edit attempt made a read-only editor swallow Ctrl+A —
    so `Select All` did nothing in Caption Mode while the "read-only" hint
    flashed. Ctrl+V keeps its hint (see the paste test above): that IS an edit."""
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Page/>")
    editor.setReadOnly(True)
    emitted = []
    editor.read_only_edit_attempted.connect(lambda: emitted.append(True))

    _send_key(editor, _Qt2.Key.Key_A, "a", _Qt2.KeyboardModifier.ControlModifier)

    assert emitted == []
    assert editor.textCursor().selectedText() == "<Page/>"
    assert editor.toPlainText() == "<Page/>"


def test_readonly_paste_hint_uses_the_apps_own_chords_not_qts_table(qtbot):
    """BUG-260810140553 Part 1 / DEC-015. The test used to be
    `event.matches(QKeySequence.StandardKey.Paste)`, which answers Qt's
    per-scheme table: the hint fired for `Ctrl+Shift+Ins` and `F18` on Linux and
    for neither on Windows. It now goes through `code_editor.is_paste_chord` and
    `shortcut_registry.EDITOR_PASTE_CHORDS`, so the set is the app's own and is
    identical on both platforms.

    Asserted through the app's handler and never against
    `QKeySequence.keyBindings(...)`: the offscreen platform reports Qt's Windows
    scheme, so a comparison with Qt's own answer would be meaningless here.
    """
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Page/>")
    editor.setReadOnly(True)
    emitted = []
    editor.read_only_edit_attempted.connect(lambda: emitted.append(True))

    # Every chord in the app-owned set raises the hint...
    _send_key(editor, _Qt2.Key.Key_V, "v", _Qt2.KeyboardModifier.ControlModifier)
    _send_key(editor, _Qt2.Key.Key_Insert, "", _Qt2.KeyboardModifier.ShiftModifier)
    _send_key(editor, _Qt2.Key.Key_Paste)
    assert len(emitted) == 3

    # ...and `Ctrl+Shift+Insert` is now one of them, on both platforms. The owner
    # ruled (2026-08-10) that the app BINDS that chord as paste rather than
    # inheriting or suppressing it -- it is live on Linux, so suppressing would
    # have removed a working gesture -- so it joined `EDITOR_PASTE_CHORDS` and a
    # read-only buffer owes it the same hint as `Ctrl+V`. (This assertion used to
    # say the opposite, while the direction was an open ruling.)
    emitted.clear()
    _send_key(
        editor,
        _Qt2.Key.Key_Insert,
        "",
        _Qt2.KeyboardModifier.ControlModifier | _Qt2.KeyboardModifier.ShiftModifier,
    )
    assert emitted == [True]
    assert editor.toPlainText() == "<Page/>"


def test_the_x11_only_editing_chords_are_answered_by_the_xml_editor(qtbot):
    """The owner's 2026-08-10 ruling at this surface. `Ctrl+D`/`Ctrl+K`/`Ctrl+U`
    are implemented by the app on both platforms, and this editor is one of the
    six surfaces that answers them. Qt binds them on the Linux/KDE scheme only and
    the offscreen platform runs Qt's **Windows** scheme, so what is asserted is
    the app's handler — the only thing that exists on the platform the suite can
    see, and the whole reason the ruling was worth implementing."""
    def editor_at(text, position):
        editor = XmlEditor()
        qtbot.addWidget(editor)
        editor.setPlainText(text)
        cursor = editor.textCursor()
        cursor.setPosition(position)
        editor.setTextCursor(cursor)
        return editor

    ctrl = _Qt2.KeyboardModifier.ControlModifier

    deleted_char = editor_at("<A/>\n<B/>", 0)
    _send_key(deleted_char, _Qt2.Key.Key_D, "", ctrl)
    assert deleted_char.toPlainText() == "A/>\n<B/>"

    to_eol = editor_at("<A/>\n<B/>", 1)
    _send_key(to_eol, _Qt2.Key.Key_K, "", ctrl)
    assert to_eol.toPlainText() == "<\n<B/>"

    whole_line = editor_at("<A/>\n<B/>", 1)
    _send_key(whole_line, _Qt2.Key.Key_U, "", ctrl)
    assert whole_line.toPlainText() == "<B/>"


def test_the_editing_chords_raise_the_read_only_hint_instead_of_editing(qtbot):
    """Caption Mode's read-only buffer: the three delete gestures are Ctrl chords,
    so the "a Ctrl chord is a command, never typing" test would have called them
    *not* an edit attempt and left them silently dead — while `Ctrl+U` deletes a
    whole line, the most edit-like keystroke on the list. They get the hint for
    exactly the reason `Ctrl+V` does."""
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Page/>\n<Other/>")
    editor.setReadOnly(True)
    emitted = []
    editor.read_only_edit_attempted.connect(lambda: emitted.append(True))
    ctrl = _Qt2.KeyboardModifier.ControlModifier

    for key in (_Qt2.Key.Key_D, _Qt2.Key.Key_K, _Qt2.Key.Key_U):
        _send_key(editor, key, "", ctrl)

    assert len(emitted) == 3
    assert editor.toPlainText() == "<Page/>\n<Other/>"


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


# --- Editor bookmarks (session-scoped line marks) --------------------------
from PySide6.QtCore import QEvent as _QEvent_bm, QPoint as _QPoint_bm, Qt as _Qt_bm
from PySide6.QtGui import QMouseEvent as _QMouseEvent_bm


def test_toggle_bookmark_adds_then_removes(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc")
    editor.toggle_bookmark(1)
    assert editor.bookmarked_lines() == [1]
    editor.toggle_bookmark(1)
    assert editor.bookmarked_lines() == []


def test_bookmarked_lines_returns_sorted(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc\nd\ne")
    for n in (3, 0, 4, 1):
        editor.toggle_bookmark(n)
    assert editor.bookmarked_lines() == [0, 1, 3, 4]


def test_next_bookmark_returns_smallest_greater(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc\nd\ne")
    for n in (1, 3):
        editor.toggle_bookmark(n)
    assert editor.next_bookmark(0) == 1
    assert editor.next_bookmark(1) == 3


def test_next_bookmark_wraps_to_smallest(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc\nd\ne")
    for n in (1, 3):
        editor.toggle_bookmark(n)
    assert editor.next_bookmark(3) == 1
    assert editor.next_bookmark(4) == 1


def test_prev_bookmark_returns_largest_smaller(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc\nd\ne")
    for n in (1, 3):
        editor.toggle_bookmark(n)
    assert editor.prev_bookmark(4) == 3
    assert editor.prev_bookmark(3) == 1


def test_prev_bookmark_wraps_to_largest(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc\nd\ne")
    for n in (1, 3):
        editor.toggle_bookmark(n)
    assert editor.prev_bookmark(1) == 3
    assert editor.prev_bookmark(0) == 3


def test_next_prev_bookmark_none_when_empty(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc")
    assert editor.next_bookmark(0) is None
    assert editor.prev_bookmark(0) is None


def test_clear_bookmarks_empties(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc")
    editor.toggle_bookmark(0)
    editor.toggle_bookmark(2)
    editor.clear_bookmarks()
    assert editor.bookmarked_lines() == []


def test_bookmarks_reset_on_set_plain_text(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc")
    editor.toggle_bookmark(1)
    assert editor.bookmarked_lines() == [1]
    editor.setPlainText("x\ny\nz\nw")
    assert editor.bookmarked_lines() == []


def test_toggle_bookmark_at_cursor_marks_cursor_line(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc\nd")
    cursor = editor.textCursor()
    cursor.setPosition(editor.document().findBlockByNumber(2).position())
    editor.setTextCursor(cursor)
    editor.toggle_bookmark_at_cursor()
    assert editor.bookmarked_lines() == [2]


def test_goto_next_bookmark_moves_cursor(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc\nd\ne")
    for n in (1, 3):
        editor.toggle_bookmark(n)
    cursor = editor.textCursor()
    cursor.setPosition(editor.document().findBlockByNumber(0).position())
    editor.setTextCursor(cursor)
    editor.goto_next_bookmark()
    assert editor.textCursor().blockNumber() == 1
    editor.goto_next_bookmark()
    assert editor.textCursor().blockNumber() == 3
    # wrap
    editor.goto_next_bookmark()
    assert editor.textCursor().blockNumber() == 1


def test_goto_prev_bookmark_moves_cursor(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc\nd\ne")
    for n in (1, 3):
        editor.toggle_bookmark(n)
    cursor = editor.textCursor()
    cursor.setPosition(editor.document().findBlockByNumber(4).position())
    editor.setTextCursor(cursor)
    editor.goto_prev_bookmark()
    assert editor.textCursor().blockNumber() == 3
    editor.goto_prev_bookmark()
    assert editor.textCursor().blockNumber() == 1


def test_goto_bookmark_no_op_when_empty(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc")
    cursor = editor.textCursor()
    cursor.setPosition(editor.document().findBlockByNumber(1).position())
    editor.setTextCursor(cursor)
    editor.goto_next_bookmark()
    assert editor.textCursor().blockNumber() == 1
    editor.goto_prev_bookmark()
    assert editor.textCursor().blockNumber() == 1


def test_gutter_click_in_bookmark_strip_toggles_bookmark(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.resize(400, 300)
    editor.show()
    editor.setPlainText("<Page>\n  <Detail>\n    content\n  </Detail>\n</Page>")

    block = editor.document().findBlockByNumber(2)
    top = editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top()
    point = _QPoint_bm(2, int(top) + 2)  # x=2 lands in the left bookmark strip
    event = _QMouseEvent_bm(
        _QEvent_bm.Type.MouseButtonPress,
        point,
        _Qt_bm.MouseButton.LeftButton,
        _Qt_bm.MouseButton.LeftButton,
        _Qt_bm.KeyboardModifier.NoModifier,
    )
    editor._gutter.mousePressEvent(event)
    assert editor.bookmarked_lines() == [2]


def test_gutter_click_in_fold_zone_still_toggles_fold(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.resize(400, 300)
    editor.show()
    editor.setPlainText("<Page>\n  <Detail>\n    content\n  </Detail>\n</Page>")

    outer_block = editor.document().findBlockByNumber(0)
    top = editor.blockBoundingGeometry(outer_block).translated(editor.contentOffset()).top()
    # x inside the fold zone (shifted right past the bookmark strip).
    from pgtp_editor.ui.xml_editor import _BOOKMARK_STRIP_WIDTH, _FOLD_GLYPH_WIDTH
    fold_x = _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH // 2
    point = _QPoint_bm(fold_x, int(top) + 2)
    event = _QMouseEvent_bm(
        _QEvent_bm.Type.MouseButtonPress,
        point,
        _Qt_bm.MouseButton.LeftButton,
        _Qt_bm.MouseButton.LeftButton,
        _Qt_bm.KeyboardModifier.NoModifier,
    )
    editor._gutter.mousePressEvent(event)
    assert editor.document().findBlockByNumber(2).isVisible() is False
    assert editor.bookmarked_lines() == []


def _gutter_mouse_event(kind, x, y):
    """A left-button mouse event of ``kind`` at gutter-widget coords (x, y)."""
    return _QMouseEvent_bm(
        kind,
        _QPoint_bm(int(x), int(y)),
        _Qt_bm.MouseButton.LeftButton,
        _Qt_bm.MouseButton.LeftButton,
        _Qt_bm.KeyboardModifier.NoModifier,
    )


def _line_number_zone_x():
    from pgtp_editor.ui.xml_editor import _BOOKMARK_STRIP_WIDTH, _FOLD_GLYPH_WIDTH

    return _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH + 2


def _gutter_editor(qtbot, text="<Page>\n  <Detail>\n    content\n  </Detail>\n</Page>"):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.resize(400, 300)
    editor.show()
    editor.setPlainText(text)
    return editor


def _block_top(editor, block_number):
    block = editor.document().findBlockByNumber(block_number)
    return editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top()


def test_gutter_double_click_on_line_number_toggles_bookmark(qtbot):
    """Spec §8/§27 target design: a double-click in the line-number zone is a
    second, larger click target for the bookmark toggle."""
    editor = _gutter_editor(qtbot)
    y = int(_block_top(editor, 2)) + 2
    x = _line_number_zone_x()

    editor._gutter.mouseDoubleClickEvent(
        _gutter_mouse_event(_QEvent_bm.Type.MouseButtonDblClick, x, y)
    )
    assert editor.bookmarked_lines() == [2]

    # A second double-click on the same line clears it again.
    editor._gutter.mouseDoubleClickEvent(
        _gutter_mouse_event(_QEvent_bm.Type.MouseButtonDblClick, x, y)
    )
    assert editor.bookmarked_lines() == []


def test_gutter_single_click_on_line_number_is_still_a_no_op(qtbot):
    """The 'additive' guarantee: the single click in the line-number zone keeps
    doing nothing, so Qt's press-before-double-click delivery cannot leave the
    user with a fold toggled AND a bookmark set."""
    editor = _gutter_editor(qtbot)
    y = int(_block_top(editor, 2)) + 2

    editor._gutter.mousePressEvent(
        _gutter_mouse_event(_QEvent_bm.Type.MouseButtonPress, _line_number_zone_x(), y)
    )
    assert editor.bookmarked_lines() == []
    assert editor.document().findBlockByNumber(2).isVisible() is True


def test_gutter_full_double_click_gesture_on_line_number_toggles_once(qtbot):
    """Qt delivers press → release → double-click. Replaying the real sequence
    must leave exactly one bookmark, not zero (press undoing it) or two."""
    editor = _gutter_editor(qtbot)
    y = int(_block_top(editor, 1)) + 2
    x = _line_number_zone_x()

    editor._gutter.mousePressEvent(
        _gutter_mouse_event(_QEvent_bm.Type.MouseButtonPress, x, y)
    )
    editor._gutter.mouseReleaseEvent(
        _gutter_mouse_event(_QEvent_bm.Type.MouseButtonRelease, x, y)
    )
    editor._gutter.mouseDoubleClickEvent(
        _gutter_mouse_event(_QEvent_bm.Type.MouseButtonDblClick, x, y)
    )
    assert editor.bookmarked_lines() == [1]


def test_gutter_double_click_in_fold_zone_does_not_toggle_a_bookmark(qtbot):
    """Outside the line-number zone the double-click keeps its old meaning —
    the fold zone folds, and no bookmark appears."""
    editor = _gutter_editor(qtbot)
    from pgtp_editor.ui.xml_editor import _BOOKMARK_STRIP_WIDTH, _FOLD_GLYPH_WIDTH

    y = int(_block_top(editor, 0)) + 2
    editor._gutter.mouseDoubleClickEvent(
        _gutter_mouse_event(
            _QEvent_bm.Type.MouseButtonDblClick,
            _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH // 2,
            y,
        )
    )
    assert editor.bookmarked_lines() == []


def test_gutter_double_click_in_bookmark_strip_gesture_is_unchanged(qtbot):
    """The strip's single click still owns the toggle; the full press +
    double-click gesture there nets out exactly as it did before (Qt's default
    mouseDoubleClickEvent re-dispatches to mousePressEvent)."""
    editor = _gutter_editor(qtbot)
    y = int(_block_top(editor, 3)) + 2

    editor._gutter.mousePressEvent(
        _gutter_mouse_event(_QEvent_bm.Type.MouseButtonPress, 2, y)
    )
    assert editor.bookmarked_lines() == [3]
    editor._gutter.mouseDoubleClickEvent(
        _gutter_mouse_event(_QEvent_bm.Type.MouseButtonDblClick, 2, y)
    )
    assert editor.bookmarked_lines() == []


def test_gutter_double_click_picks_the_right_line_when_scrolled(qtbot):
    """The classic gutter off-by-one: with the view scrolled, the topmost
    painted row must map to the FIRST VISIBLE block, not to block 0."""
    editor = _gutter_editor(qtbot, "\n".join(f"<L{i}/>" for i in range(200)))
    editor.verticalScrollBar().setValue(60)
    first_visible = editor.firstVisibleBlock().blockNumber()
    assert first_visible > 0  # the scroll actually moved the view

    top = editor.blockBoundingGeometry(editor.firstVisibleBlock()).translated(
        editor.contentOffset()
    ).top()
    editor._gutter.mouseDoubleClickEvent(
        _gutter_mouse_event(
            _QEvent_bm.Type.MouseButtonDblClick, _line_number_zone_x(), int(top) + 2
        )
    )
    assert editor.bookmarked_lines() == [first_visible]


def test_gutter_paint_with_bookmarks_does_not_crash(qtbot):
    from PySide6.QtGui import QPixmap
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.resize(400, 300)
    editor.show()
    editor.setPlainText("<Page>\n  <Detail>\n    content\n  </Detail>\n</Page>")
    editor.toggle_bookmark(1)
    # A bookmark past EOF must not crash the paint path.
    editor.toggle_bookmark(999)
    pixmap = QPixmap(editor._gutter.size())
    editor._gutter.render(pixmap)


def test_next_bookmark_ignores_out_of_range_after_edit(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc")
    editor.toggle_bookmark(999)  # points past EOF
    # navigation must not crash even though the block is invalid


# -- resolve_attribute_at (BUG-003) -----------------------------------------


def test_resolve_attribute_at_matches_uncached_free_function(qtbot):
    """The cache-aware entry point must resolve to the same (tag_chain, attr)
    the uncached free function would, for a position that IS on an attribute."""
    from pgtp_editor.ui.xml_editor import attribute_at_position

    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Root>\n  <Page phpDriver="1"/>\n</Root>'
    editor.setPlainText(text)
    pos = text.index('"1"') + 1  # inside the attribute value

    assert editor.resolve_attribute_at(pos) == attribute_at_position(text, pos)
    assert editor.resolve_attribute_at(pos) == ("Root/Page", "phpDriver")


def test_resolve_attribute_at_rescans_after_document_changes(qtbot):
    """BUG-003: resolve_attribute_at must not serve a stale cache when the
    document changed since the last scan -- it should force a rescan (mirrors
    the guard in _update_matching_tag_highlight) rather than only ever
    resolving positions valid at the time of the *first* scan."""
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root>\n  <Page phpDriver="1"/>\n</Root>')
    revision_after_first_scan = editor._spans_revision

    # Prime the cache by resolving once against the original document.
    first_text = editor.toPlainText()
    first_pos = first_text.index('"1"') + 1
    assert editor.resolve_attribute_at(first_pos) == ("Root/Page", "phpDriver")

    # Mutate the document -- this bumps document().revision() but does NOT by
    # itself call _rescan_structure() until textChanged's connected slot runs;
    # resolve_attribute_at must still notice the staleness and rescan rather
    # than resolving against the old cached text/spans.
    editor.setPlainText('<Root>\n  <Detail elementCaption="new"/>\n</Root>')
    assert editor.document().revision() != revision_after_first_scan

    new_text = editor.toPlainText()
    new_pos = new_text.index('"new"') + 1
    resolved = editor.resolve_attribute_at(new_pos)
    assert resolved == ("Root/Detail", "elementCaption")
    # And the stale position from the old document must not accidentally
    # resolve to a leftover span from the previous scan.
    assert editor._spans_text == new_text


def test_resolve_attribute_at_none_when_not_on_attribute(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Root>\n  <Page/>\n</Root>"
    editor.setPlainText(text)
    assert editor.resolve_attribute_at(0) is None


def test_attribute_at_position_default_spans_none_still_scans_from_scratch(qtbot):
    """Every existing caller that omits `spans=` (e.g. request_goto_xsd) must
    keep working exactly as before -- the optional third parameter must not
    change behavior for callers that don't pass it."""
    from pgtp_editor.ui.xml_editor import (
        attribute_at_position,
        attribute_value_at_position,
    )

    text = '<Root>\n  <Page phpDriver="1"/>\n</Root>'
    pos = text.index('"1"') + 1
    assert attribute_at_position(text, pos) == ("Root/Page", "phpDriver")
    assert attribute_value_at_position(text, pos) == ("Root/Page", "phpDriver", "1")


# -- resolve_attribute_at indexed path (BUG-008) -----------------------------
#
# BUG-008 replaced resolve_attribute_at's per-call full-span walk (and its
# per-level parent_tag_span scans) with a lazily built, revision-guarded
# index (bisect over spans sorted by open_start + build_parent_map). These
# tests pin the indexed path to the from-scratch free function: for EVERY
# kind of position the two must return identical results.

_BUG008_TEXT = (
    "<Root>\n"
    "  <Pages>\n"
    '    <Page fileName="dev_equipment" tableName="pr.equipment">\n'
    '      <Editor caption="a > b" raw="x>y" other="z"/>\n'
    "      text content here\n"
    "    </Page>\n"
    '    <Page fileName="second"/>\n'
    "  </Pages>\n"
    "</Root>"
)


def _bug008_editor(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(_BUG008_TEXT)
    return editor


def test_resolve_attribute_at_indexed_matches_free_function_on_attributes(qtbot):
    """Equivalence on positions that ARE on an attribute: name token, quoted
    value, deep nesting, and -- the robustness quirk -- an attribute that sits
    AFTER a '>' inside another attribute's quoted value in the same tag (the
    scanner's regex truncates the opening tag at that '>'; the quote-aware
    _opening_tag_end recompute must keep resolving past it)."""
    from pgtp_editor.ui.xml_editor import attribute_at_position

    editor = _bug008_editor(qtbot)
    text = _BUG008_TEXT
    cases = [
        # (position, expected (tag_chain, attr))
        (text.index("fileName"), ("Root/Pages/Page", "fileName")),  # attr name token
        (text.index('"pr.equipment"') + 3, ("Root/Pages/Page", "tableName")),  # quoted value
        (text.index("caption"), ("Root/Pages/Page/Editor", "caption")),  # deep nesting
        (text.index('"a > b"') + 3, ("Root/Pages/Page/Editor", "caption")),  # value w/ '>'
        (text.index('"x>y"') + 2, ("Root/Pages/Page/Editor", "raw")),  # ON the quoted '>'
        (text.index('other="z"'), ("Root/Pages/Page/Editor", "other")),  # after the '>' value
    ]
    for pos, expected in cases:
        from_scratch = attribute_at_position(text, pos)
        indexed = editor.resolve_attribute_at(pos)
        assert indexed == from_scratch == expected, f"mismatch at position {pos}"


def test_resolve_attribute_at_chain_unpolluted_by_earlier_gt_truncated_span(qtbot):
    """The scanner truncates `<Editor caption="a > b" .../>` at the '>' inside
    the quoted value, so its span is recorded as unclosed (close_end=None).
    The pre-BUG-008 ancestor walk (parent_tag_span, depth-filtered) skipped
    such a bogus span when resolving a LATER sibling element's attribute; the
    indexed path must do the same -- the second <Page>'s tag_chain must not
    inherit the phantom still-open Editor as an ancestor, and must equal the
    from-scratch free function's result."""
    from pgtp_editor.ui.xml_editor import attribute_at_position

    editor = _bug008_editor(qtbot)
    text = _BUG008_TEXT
    pos = text.index('"second"') + 1
    from_scratch = attribute_at_position(text, pos)
    assert from_scratch == ("Root/Pages/Page", "fileName")  # pre-fix behavior
    assert editor.resolve_attribute_at(pos) == from_scratch


def test_resolve_attribute_at_chain_unpolluted_by_multiple_truncated_spans(qtbot):
    """Two CONSECUTIVE '>'-truncated (unclosed) spans inside a properly closed
    element leave TWO bogus ancestors stuck on build_parent_map's stack, at
    depths that no longer line up with the later sibling's walk. The depth
    filter in the indexed chain walk must climb past BOTH in sequence, matching
    the from-scratch free function's parent_tag_span behavior."""
    from pgtp_editor.ui.xml_editor import attribute_at_position

    text = (
        "<Root>\n"
        "  <Pages>\n"
        '    <Page fileName="first">\n'
        '      <E1 caption="a > b" raw="q"/>\n'
        '      <E2 note="c > d" other="w"/>\n'
        "    </Page>\n"
        '    <Page fileName="second"/>\n'
        "  </Pages>\n"
        "</Root>"
    )
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    pos = text.index('"second"') + 1
    from_scratch = attribute_at_position(text, pos)
    assert from_scratch == ("Root/Pages/Page", "fileName")
    assert editor.resolve_attribute_at(pos) == from_scratch


def test_resolve_attribute_at_indexed_matches_free_function_on_non_attributes(qtbot):
    """Equivalence on positions that must resolve to None from BOTH paths:
    tag name, text content, close tag, whitespace between tokens, document
    edges."""
    from pgtp_editor.ui.xml_editor import attribute_at_position

    editor = _bug008_editor(qtbot)
    text = _BUG008_TEXT
    positions = [
        0,  # document start, on '<'
        text.index("Pages"),  # tag name token
        text.index("text content here") + 4,  # text content
        text.index("</Page>") + 3,  # inside a close tag
        text.index(' tableName'),  # whitespace between attributes
        len(text) - 1,  # inside the root close tag
    ]
    for pos in positions:
        assert attribute_at_position(text, pos) is None, f"fixture bug at {pos}"
        assert editor.resolve_attribute_at(pos) is None, f"mismatch at position {pos}"


def test_resolve_attribute_at_index_invalidated_by_edit(qtbot):
    """BUG-008 staleness: resolving builds the lazy index; a subsequent edit
    must invalidate it so the next resolve runs against fresh spans (revision
    guard + _resolution_index reset), returning the NEW document's result and
    still matching the from-scratch free function."""
    from pgtp_editor.ui.xml_editor import attribute_at_position

    editor = _bug008_editor(qtbot)
    pos = _BUG008_TEXT.index("fileName")
    assert editor.resolve_attribute_at(pos) == ("Root/Pages/Page", "fileName")
    assert editor._resolution_index is not None  # index was built lazily

    new_text = '<Root>\n  <Detail elementCaption="new"/>\n</Root>'
    editor.setPlainText(new_text)  # textChanged -> _rescan_structure
    assert editor._resolution_index is None  # spans rebuilt -> index dropped

    new_pos = new_text.index('"new"') + 1
    resolved = editor.resolve_attribute_at(new_pos)
    assert resolved == ("Root/Detail", "elementCaption")
    assert resolved == attribute_at_position(new_text, new_pos)


def test_xml_editor_supplies_its_own_xml_span_fold_provider(qtbot):
    """The shared base (§8) folds nothing by default; XmlEditor plugs in the
    XML-span provider over _spans/TagSpan."""
    from pgtp_editor.ui.editor_gutter import GutterBookmarkFoldMixin
    from pgtp_editor.ui.xml_editor import XmlEditor as _XmlEditor

    assert (
        _XmlEditor._foldable_region_starting_at
        is not GutterBookmarkFoldMixin._foldable_region_starting_at
    )
    editor = _XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Root>\n  <A/>\n</Root>\n")
    region = editor._foldable_region_starting_at(editor.document().findBlockByNumber(0))
    assert region == (1, 1)  # the <A/> line only; open/close lines excluded


def test_xml_editor_reexports_the_shared_gutter_symbols(qtbot):
    """xml_editor re-exports the extracted names so existing importers keep
    working -- and they are the SAME objects, not copies (§8: exactly one
    gutter implementation)."""
    from pgtp_editor.ui import editor_gutter, xml_editor as xml_editor_module

    assert xml_editor_module._EditorGutter is editor_gutter._EditorGutter
    assert xml_editor_module._BOOKMARK_STRIP_WIDTH is editor_gutter._BOOKMARK_STRIP_WIDTH
    assert xml_editor_module._FOLD_GLYPH_WIDTH is editor_gutter._FOLD_GLYPH_WIDTH


def test_xml_editor_gutter_and_bookmark_methods_come_from_the_shared_mixin(qtbot):
    """The extraction moved the implementation out; XmlEditor must not have
    re-declared its own copy of any of it."""
    from pgtp_editor.ui.editor_gutter import GutterBookmarkFoldMixin
    from pgtp_editor.ui.xml_editor import XmlEditor as _XmlEditor

    for name in (
        "toggle_bookmark",
        "bookmarked_lines",
        "next_bookmark",
        "prev_bookmark",
        "clear_bookmarks",
        "_is_line_hidden_by_other_collapsed_fold",
        "_gutter_width",
        "_apply_gutter_theme_colors",
    ):
        assert name not in vars(_XmlEditor), f"{name} re-declared on XmlEditor"
        assert getattr(_XmlEditor, name) is getattr(GutterBookmarkFoldMixin, name)

    # _toggle_fold is the ONE deliberate exception (BUG-015): XmlEditor wraps
    # it to flush the debounced structure rescan first, so folding never acts
    # on stale spans. It must stay a thin wrapper that DELEGATES -- never a
    # re-implementation.
    import inspect

    source = inspect.getsource(_XmlEditor._toggle_fold)
    assert "_flush_pending_rescan" in source
    assert "super()._toggle_fold(block)" in source


def test_folding_right_after_an_edit_flushes_the_debounced_rescan(qtbot):
    """BUG-015 correctness guard: the structure rescan is debounced, but
    folding is a deliberate action that must act on EXACT spans. Folding a
    region created by an edit that the debounce hasn't processed yet must
    still work -- _toggle_fold flushes first."""
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Root>\n</Root>\n")

    # Type a foldable element in; the rescan is still pending afterwards.
    cursor = editor.textCursor()
    cursor.setPosition(len("<Root>\n"))
    editor.setTextCursor(cursor)
    editor.insertPlainText("  <A>\n    x\n  </A>\n")
    assert editor._rescan_timer.isActive()  # debounce pending, spans stale

    # Folding the just-typed <A> must still find its region.
    block = editor.document().findBlockByNumber(1)
    editor._toggle_fold(block)
    assert editor._rescan_timer.isActive() is False  # flushed
    assert editor._fold_state.get(1) is True


def test_xml_editor_folding_still_keeps_the_character_stream_intact(qtbot):
    """§8's hard requirement, re-asserted after the extraction: folding hides
    rendering only -- the text is fully present."""
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n  <Detail>\n    content\n  </Detail>\n</Page>\n"
    editor.setPlainText(text)
    editor._toggle_fold(editor.document().findBlockByNumber(1))
    assert editor.document().findBlockByNumber(2).isVisible() is False
    assert editor.toPlainText() == text


# --- BUG-016: the quote-parity block-state cascade ---------------------------


def _count_highlight_calls(monkeypatch):
    """Swap in a counting SUBCLASS of the highlighter (before any editor is
    built) and return the call counter.

    Must be called BEFORE the editor is constructed: `XmlEditor.__init__` looks
    `XmlSyntaxHighlighter` up as a module global, so only editors built while
    this patch is live get the counting subclass.

    Do NOT go back to `monkeypatch.setattr(module.XmlSyntaxHighlighter,
    "highlightBlock", ...)`. `highlightBlock` is a C++ virtual and PySide6 binds
    Python overrides PER INSTANCE AT CONSTRUCTION, not per call -- so every
    highlighter built under such a patch keeps a raw pointer to the replacement
    function, and `monkeypatch.undo()` frees it. The dangling pointer is then
    called by any later `rehighlight()` (BUG-013's theme sweep reaches leaked
    editors from earlier tests), which either raises a nonsense
    `TypeError: ... takes 0 positional arguments but 2 were given` naming
    whatever object landed in the freed slot, or segfaults outright. That was
    BUG-017. Patching the module NAME instead keeps the override in the
    subclass's own __dict__, and the instance keeps its type alive.
    """
    import pgtp_editor.ui.xml_editor as module

    calls = {"n": 0}

    class _CountingHighlighter(module.XmlSyntaxHighlighter):
        def highlightBlock(self, text):
            calls["n"] += 1
            super().highlightBlock(text)

    monkeypatch.setattr(module, "XmlSyntaxHighlighter", _CountingHighlighter)
    return calls


def test_quote_in_text_content_does_not_rehighlight_the_document(qtbot, monkeypatch):
    """THE BUG-016 regression test. `_has_unterminated_quote` used to flip this
    block's state on ANY odd quote count, so one '"' typed in text content
    flipped every following block's state in turn and Qt cascaded a
    re-highlight to EOF (measured: 5,972 calls / 45ms on a 6k-block file).
    A quote in text content cannot delimit anything in XML, so it must not
    change the state -- only the edited block re-highlights."""
    calls = _count_highlight_calls(monkeypatch)
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(
        "<Root>\n" + "\n".join(f"  <A id='{i}'>text {i}</A>" for i in range(300)) + "\n</Root>"
    )

    assert calls["n"] >= 1, "the counting highlighter never ran -- the <= assertion below would be vacuous"

    cursor = editor.textCursor()
    cursor.setPosition(editor.document().findBlockByNumber(5).position() + 3)
    editor.setTextCursor(cursor)
    calls["n"] = 0
    editor.insertPlainText('"')

    assert calls["n"] <= 2, (
        f"typing one quote re-highlighted {calls['n']} blocks -- the block-state "
        "cascade is unbounded again (BUG-016)"
    )


def test_unterminated_quote_inside_a_tag_resyncs_at_the_next_tag(qtbot, monkeypatch):
    """An unterminated quote INSIDE a tag legitimately continues onto the next
    line, but must not keep flipping state to EOF: the raw '<' that opens the
    next tag resyncs the state (a '<' cannot occur inside a well-formed
    attribute value), so the cascade stops after a block or two."""
    calls = _count_highlight_calls(monkeypatch)
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Root>\n" + "\n".join(f'  <A id="{i}"/>' for i in range(300)) + "\n</Root>"
    editor.setPlainText(text)

    assert calls["n"] >= 1, "the counting highlighter never ran -- the <= assertion below would be vacuous"

    cursor = editor.textCursor()
    cursor.setPosition(text.index('id="0"') + len("id="))
    editor.setTextCursor(cursor)
    calls["n"] = 0
    editor.insertPlainText('"')  # now an unterminated quote inside the tag

    assert calls["n"] <= 4, f"cascade not bounded by the resync: {calls['n']} blocks"


def test_count_highlight_calls_never_patches_the_shiboken_class(qtbot, monkeypatch):
    """BUG-017 guard. The counting hook must reach the editor through a Python
    SUBCLASS, never by setting `highlightBlock` on the Shiboken class itself --
    PySide6 binds virtual overrides per instance at construction, so a class
    patch leaves every highlighter built under it pointing at a function that
    `monkeypatch.undo()` then frees (use-after-free: nonsense TypeErrors in
    unrelated tests, or a segfault). If this test fails, read BUG-017 before
    'fixing' it."""
    import pgtp_editor.ui.xml_editor as module

    original_class = module.XmlSyntaxHighlighter
    original_method = original_class.highlightBlock

    calls = _count_highlight_calls(monkeypatch)
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Root>\n  <A id='1'/>\n</Root>")

    # The counter works...
    assert calls["n"] >= 1
    # ...but the real class was left completely untouched.
    assert module.XmlSyntaxHighlighter is not original_class
    assert original_class.highlightBlock is original_method
    # ...and the editor's highlighter is a subclass instance, not the real class.
    assert type(editor._highlighter) is not original_class
    assert isinstance(editor._highlighter, original_class)


def test_counting_highlighter_override_survives_monkeypatch_undo(qtbot, monkeypatch):
    """BUG-017 guard, lifecycle half. The dangling-pointer crash needed TWO
    steps: build a highlighter under the patch, then UNDO the patch. PySide6
    resolved that instance's `highlightBlock` override once, at construction --
    so once undo drops the last reference to the patched function, the live
    instance calls freed memory (nonsense TypeError, or segfault) on its next
    rehighlight.

    The invariant that makes the subclass approach safe: the override the
    instance was constructed with must STILL be reachable through the
    instance's own type after the patch is undone. Asserted before we touch the
    editor again, so a regression fails loudly here instead of crashing the
    worker."""
    import pgtp_editor.ui.xml_editor as module

    original_class = module.XmlSyntaxHighlighter

    with monkeypatch.context() as m:
        calls = _count_highlight_calls(m)
        editor = XmlEditor()
        qtbot.addWidget(editor)
        editor.setPlainText("<Root>\n  <A id='1'>text</A>\n</Root>")
        assert calls["n"] >= 1
        highlighter_type = type(editor._highlighter)
        bound_override = highlighter_type.highlightBlock

    # The patch is undone; the module global is back to the real class...
    assert module.XmlSyntaxHighlighter is original_class
    # ...but the instance built under the patch still resolves its override
    # through its own type -- nothing it points at has been freed.
    assert type(editor._highlighter) is highlighter_type
    assert highlighter_type.highlightBlock is bound_override

    # And therefore rehighlighting it after the undo is safe (this is the call
    # that used to raise the masked TypeError / segfault).
    before = calls["n"]
    editor._highlighter.rehighlight()
    assert calls["n"] > before


def test_apostrophes_in_event_handler_body_do_not_string_ify_the_rest(qtbot):
    """.pgtp keeps PHP event-handler bodies in TEXT CONTENT, full of quotes and
    apostrophes. Those must not open an attribute value -- before BUG-016 they
    flipped the state and mis-colored everything after them."""
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = (
        "<OnBeforeInsert>\n"
        "$name = 'it\\'s';\n"
        "$sql = \"SELECT 1\";\n"
        "</OnBeforeInsert>\n"
        '<Page id="p"/>'
    )
    editor.setPlainText(text)

    tag_color = editor._highlighter._tag_format.foreground().color()
    assert _format_at(editor, text.index("<Page")).foreground().color() == tag_color


def test_end_state_transitions_are_tag_aware(qtbot):
    """The state machine itself: quotes only delimit inside a tag, and a raw
    '<' inside a quoted value resyncs."""
    from pgtp_editor.ui.xml_editor import (
        STATE_IN_SINGLE_QUOTED,
        STATE_IN_TAG,
        STATE_IN_UNCLOSED_STRING,
        STATE_NORMAL,
    )

    editor = XmlEditor()
    qtbot.addWidget(editor)
    end_state = editor._highlighter._end_state

    # Text content: quotes and apostrophes are ordinary characters.
    assert end_state('say "hi', STATE_NORMAL) == STATE_NORMAL
    assert end_state("it's", STATE_NORMAL) == STATE_NORMAL
    # Inside a tag they open a value; the matching quote closes it.
    assert end_state('<A b="x', STATE_NORMAL) == STATE_IN_UNCLOSED_STRING
    assert end_state("<A b='x", STATE_NORMAL) == STATE_IN_SINGLE_QUOTED
    assert end_state('<A b="x"', STATE_NORMAL) == STATE_IN_TAG
    assert end_state('<A b="x"/>', STATE_NORMAL) == STATE_NORMAL
    # A double quote does not close a single-quoted value, and vice versa.
    assert end_state("\"", STATE_IN_SINGLE_QUOTED) == STATE_IN_SINGLE_QUOTED
    assert end_state("'", STATE_IN_UNCLOSED_STRING) == STATE_IN_UNCLOSED_STRING
    # Resync: a raw '<' cannot be inside a well-formed value.
    assert end_state('  <B c="d"/>', STATE_IN_UNCLOSED_STRING) == STATE_NORMAL
    # A tag left open at end of line keeps quote tracking on the next line.
    assert end_state("<A", STATE_NORMAL) == STATE_IN_TAG
