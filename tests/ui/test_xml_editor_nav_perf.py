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


def test_properties_population_uses_indexed_resolution_not_per_row_walks(qtbot, monkeypatch):
    """BUG-008 regression. PropertiesPanel.show_node with a curated schema
    model injected (without one the slow path never runs -- _display_value
    short-circuits) calls XmlEditor.resolve_attribute_at once per attribute
    row. That used to cost, PER ROW, a full pass over every span plus one
    O(n) xml_structure.parent_tag_span scan per ancestor level. The fix
    resolves against a lazy per-revision index (spans sorted by open_start +
    build_parent_map), so populating a many-row node must:
      - never call xml_structure.scan (spans cache already fresh),
      - never call xml_structure.parent_tag_span (parent map instead),
      - call xml_structure.build_parent_map exactly ONCE per document
        revision, no matter how many rows resolve (and reuse it across
        repeated show_node calls on the unchanged document)."""
    from pgtp_editor.schema_learning.model import Model
    from pgtp_editor.ui.properties_panel import PropertiesPanel

    counts = {"scan": 0, "parent_tag_span": 0, "build_parent_map": 0}
    for name in counts:
        real = getattr(xml_structure, name)

        def counting(*args, _real=real, _name=name):
            counts[_name] += 1
            return _real(*args)

        monkeypatch.setattr(xml_structure, name, counting)

    attrs = {f"attr{i:02d}": str(i) for i in range(30)}
    attr_text = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    filler = "\n".join(f"  <Row{i} x=\"{i}\"/>" for i in range(50))
    text = f"<Root>\n  <Page {attr_text}/>\n{filler}\n</Root>"

    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(text)  # textChanged -> _rescan_structure (scans once)

    model = Model()
    model.paths = {"Root/Page": {
        "attributes": {"attr00": {
            "type": "integer", "values": ["0"], "overflowed": False,
            "attr_seen_count": 1, "labels": {"0": "zero"}, "use": "optional",
        }},
        "children": {}, "instance_count": 1, "order": [],
        "order_stable": True, "has_text": False,
    }}
    panel = PropertiesPanel(editor)
    qtbot.addWidget(panel)
    panel.set_schema_model(model)

    class _Node:
        sourceline = 2
        attrib = attrs
        file_name = "x"
        identity = "x"

    counts.update(scan=0, parent_tag_span=0, build_parent_map=0)  # post-load baseline
    panel.show_node(_Node(), "page")

    assert panel.table.rowCount() == 30
    # Labels still resolve correctly through the indexed path (display
    # contract unchanged -- gotcha 3 in the queue entry).
    assert panel.table.item(0, 1).text() == "0 — zero"
    assert panel.table.item(1, 1).text() == "1"

    assert counts["scan"] == 0, "populating Properties re-scanned the document"
    assert counts["parent_tag_span"] == 0, (
        "indexed resolution must use the parent map, not per-level "
        "parent_tag_span scans"
    )
    assert counts["build_parent_map"] == 1, (
        "the resolution index must be built exactly once per revision, "
        "not per attribute row"
    )

    # Re-populating on the SAME unchanged document reuses the index outright.
    panel.show_node(_Node(), "page")
    panel.show_node(_Node(), "page")
    assert counts["scan"] == 0
    assert counts["parent_tag_span"] == 0
    assert counts["build_parent_map"] == 1

    # After an edit the index is rebuilt exactly once for the new revision
    # (a rescan of the changed document is expected and allowed).
    editor.setPlainText(text.replace('attr00="0"', 'attr00="0" extra="e"'))
    panel.show_node(_Node(), "page")
    assert counts["parent_tag_span"] == 0
    assert counts["build_parent_map"] == 2
