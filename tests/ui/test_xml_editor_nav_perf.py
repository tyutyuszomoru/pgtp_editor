"""Regression coverage for the per-keystroke O(n) rescan bug: XmlEditor's
matching-tag highlight (_update_matching_tag_highlight, wired to
cursorPositionChanged) used to call xml_structure.enclosing_tag_span(text,
pos), which re-runs a full-document scan() on every cursor move. On a large
document this made every arrow key / mouse click lag noticeably. The fix
reuses the editor's already-maintained `_spans` cache (refreshed on
textChanged by _rescan_structure) via the new
xml_structure.enclosing_tag_span_from_spans(spans, pos) helper, so cursor
moves no longer trigger a rescan at all.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor

from pgtp_editor.ui import xml_editor as xml_editor_module
from pgtp_editor.ui import xml_structure
from pgtp_editor.ui.xml_editor import XmlEditor
from pgtp_editor.ui.xml_structure import (
    enclosing_tag_span,
    enclosing_tag_span_from_spans,
    scan,
)


NESTED_TEXT = (
    "<Page>\n"
    "  <Detail>\n"
    "    <Column name=\"a\">value</Column>\n"
    "    <Column name=\"b\"/>\n"
    "  </Detail>\n"
    "  text after\n"
    "</Page>"
)


def test_enclosing_tag_span_from_spans_matches_enclosing_tag_span_for_various_positions():
    """Pure-equivalence: the cached-spans path must select exactly the same
    TagSpan as the from-scratch path, for every kind of position (inside an
    open tag, in text content, inside a nested child, inside a self-closing
    tag, outside every element)."""
    positions = [
        NESTED_TEXT.index("<Page>") + 1,  # inside the open tag
        NESTED_TEXT.index("value"),  # in text content
        NESTED_TEXT.index("<Column name=\"a\">") + 2,  # inside a nested child's open tag
        NESTED_TEXT.index("<Column name=\"b\"/>") + 2,  # inside a self-closing tag
        NESTED_TEXT.index("text after"),  # in text content directly under the root
        0,  # very start of the document
        len(NESTED_TEXT),  # very end of the document
    ]
    spans = scan(NESTED_TEXT)
    for position in positions:
        expected = enclosing_tag_span(NESTED_TEXT, position)
        actual = enclosing_tag_span_from_spans(spans, position)
        assert actual == expected, f"mismatch at position {position}"


def test_cursor_navigation_does_not_rescan_document(qtbot, monkeypatch):
    """THE regression test. Before the fix, every cursor move called
    xml_structure.scan() again (via enclosing_tag_span) from
    _update_matching_tag_highlight. Moving the cursor around must not
    trigger any additional scan() calls; only an actual text edit
    (textChanged -> _rescan_structure) should."""
    calls = {"n": 0}
    real_scan = xml_structure.scan

    def counting_scan(text):
        calls["n"] += 1
        return real_scan(text)

    # Patch the module attribute xml_editor.py actually calls through
    # (`xml_structure.scan(...)`, via `from pgtp_editor.ui import
    # xml_structure` -- a module import, so patching the xml_structure
    # module object's `scan` name is visible to both callers).
    monkeypatch.setattr(xml_editor_module.xml_structure, "scan", counting_scan)

    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n" + "\n".join(f"  <Row{i}>x</Row{i}>" for i in range(20)) + "\n</Page>"
    editor.setPlainText(text)  # triggers textChanged -> _rescan_structure

    baseline = calls["n"]
    assert baseline > 0  # sanity: loading the document did scan at least once

    # Ten cursor moves via arrow-key navigation and direct cursor placement.
    for _ in range(5):
        qtbot.keyClick(editor, Qt.Key.Key_Down)
    for offset in (5, 10, 15, 20, 25):
        cursor = editor.textCursor()
        cursor.setPosition(offset)
        editor.setTextCursor(cursor)

    assert calls["n"] == baseline, (
        "cursor navigation triggered a rescan -- the matching-tag highlight "
        "must use the cached spans, not re-scan on every cursor move"
    )

    # A real edit (textChanged) is expected to trigger at least one rescan
    # (exactly how many depends on other textChanged-driven features, e.g.
    # auto-indent/auto-close, which is out of scope for this fix).
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    qtbot.keyClick(editor, Qt.Key.Key_X)
    after_edit = calls["n"]
    assert after_edit > baseline

    # Subsequent navigation still must not rescan.
    for offset in (2, 4, 6):
        cursor = editor.textCursor()
        cursor.setPosition(offset)
        editor.setTextCursor(cursor)
    assert calls["n"] == after_edit


def test_cursor_navigation_does_not_copy_document_text(qtbot):
    """Companion regression: even with the spans cached,
    _update_matching_tag_highlight used to call self.toPlainText() on every
    cursor move -- a full copy of the document's text (several ms per
    keystroke on a multi-MB document). The document text is now cached
    alongside the spans (self._spans_text, same revision guard), so pure
    cursor navigation must not call toPlainText() at all."""
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>\n" + "\n".join(f"  <Row{i}>x</Row{i}>" for i in range(20)) + "\n</Page>"
    editor.setPlainText(text)

    calls = {"n": 0}
    real_to_plain_text = editor.toPlainText

    def counting_to_plain_text():
        calls["n"] += 1
        return real_to_plain_text()

    # Instance-level patch AFTER load: only navigation-time calls count.
    editor.toPlainText = counting_to_plain_text

    for _ in range(5):
        qtbot.keyClick(editor, Qt.Key.Key_Down)
    for offset in (5, 10, 15, 20, 25):
        cursor = editor.textCursor()
        cursor.setPosition(offset)
        editor.setTextCursor(cursor)

    assert calls["n"] == 0, (
        "cursor navigation called toPlainText() -- the matching-tag "
        "highlight must reuse the cached document text, not re-copy the "
        "whole document on every cursor move"
    )
