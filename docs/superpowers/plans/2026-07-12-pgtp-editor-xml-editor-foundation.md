# XML Editor Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `xml_structure.py` (a lenient, Qt-free tag-position scanner) and `XmlEditor` (a `QPlainTextEdit`-based XML editor with syntax highlighting, gutter, folding, line-wrap toggle, current-line highlighting, auto-indent, and auto-close), then wire it into `CenterStage`'s Raw XML tab and into `MainWindow.open_project_file`'s success and Tier-1-failure paths.

**Architecture:** Two new modules — `pgtp_editor/ui/xml_structure.py` (pure Python, unit-tested without Qt) and `pgtp_editor/ui/xml_editor.py` (`XmlEditor(QPlainTextEdit)` plus its private `XmlSyntaxHighlighter` and `_EditorGutter` helper classes, `pytest-qt`-tested) — built up incrementally, feature by feature. `pgtp_editor/model/parser.py` gains a `line` field on `PgtpParseError`. `pgtp_editor/ui/center_stage.py` and `pgtp_editor/ui/main_window.py` are wired last, once the widget exists.

**Tech Stack:** Python 3, PySide6 (`QPlainTextEdit`, `QSyntaxHighlighter`, `QTextCursor`/`QTextBlock`), `lxml` (parser only, unchanged approach), `pytest` + `pytest-qt` (already a dependency, v4.5.0 confirmed installed).

---

## Before you start

- Work in this worktree: `C:\Users\BotondZalai-RuzsicsP\docs\Software development\pgtp_editor\.claude\worktrees\pgtp-editor-xmleditor-foundation`, branch `worktree-pgtp-editor-xmleditor-foundation` (already checked out).
- Run tests with `python -m pytest <path> -v` from the worktree root.
- Commit after every task (not every step) unless a step says otherwise — each task's final step is always "commit."
- The authoritative design document is `docs/superpowers/specs/2026-07-12-pgtp-editor-xml-editor-foundation-design.md` — consult it if a step here references "per the spec."

---

## Part 1 — `xml_structure.py` (no Qt dependency)

### Task 1: `TagSpan` dataclass and `scan()` — well-formed nesting only

**Files:**
- Create: `pgtp_editor/ui/xml_structure.py`
- Test: `tests/ui/test_xml_structure.py`

- [ ] **Step 1: Write the failing test for well-formed nesting**

```python
# tests/ui/test_xml_structure.py
from pgtp_editor.ui.xml_structure import TagSpan, scan


def test_scan_well_formed_nesting_produces_correct_depths_and_offsets():
    text = "<Page><Detail><Column/></Detail></Page>"
    spans = scan(text)

    by_name = {span.name: span for span in spans}
    assert set(by_name) == {"Page", "Detail", "Column"}

    page = by_name["Page"]
    assert page.depth == 0
    assert page.self_closing is False
    assert text[page.open_start:page.open_end] == "<Page>"
    assert page.close_end is not None
    assert text[page.close_end - len("</Page>"):page.close_end] == "</Page>"

    detail = by_name["Detail"]
    assert detail.depth == 1
    assert detail.self_closing is False
    assert text[detail.open_start:detail.open_end] == "<Detail>"
    assert text[detail.close_end - len("</Detail>"):detail.close_end] == "</Detail>"

    column = by_name["Column"]
    assert column.depth == 2
    assert column.self_closing is True
    assert text[column.open_start:column.open_end] == "<Column/>"
    assert column.close_end == column.open_end


def test_scan_returns_empty_list_for_empty_text():
    assert scan("") == []


def test_scan_returns_empty_list_for_text_with_no_tags():
    assert scan("just some plain text, no tags here") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_xml_structure.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgtp_editor.ui.xml_structure'`

- [ ] **Step 3: Write `TagSpan` and `scan()` for the well-formed case**

```python
# pgtp_editor/ui/xml_structure.py
"""A lenient, regex-based tag-position scanner for XML-like text.

Deliberately NOT built on lxml: lxml raises on malformed or incomplete XML,
but this module has to keep working while a user is mid-edit (an unclosed
tag, a half-typed attribute, a truncated document are all normal, transient
states from this module's point of view, not error states). This is a
plain-Python, regex-based, best-effort scanner with no Qt dependency, so it
is unit-testable without a QApplication and reusable by both xml_editor.py
(folding, gutter, auto-indent, auto-close) and, in a future sub-project,
XML structural selection.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Matches an opening tag (<name ...>), a self-closing tag (<name .../>), or
# a closing tag (</name>). Permissive: attribute values need not be
# well-formed or quotes balanced, since this scanner must tolerate
# in-progress edits.
_TAG_RE = re.compile(r"<(/?)([A-Za-z_][\w.-]*)([^<>]*?)(/?)>")


@dataclass
class TagSpan:
    name: str  # element name, e.g. "Page"
    open_start: int  # character offset of the '<' that opens this element
    open_end: int  # character offset just past this open tag's '>'
    close_end: int | None  # character offset just past the matching '</name>' '>',
    # or None if no matching close tag was found
    depth: int  # nesting depth, 0 for a top-level element
    self_closing: bool  # True for a <tag/> form -- such an element has no
    # separate close tag and is not a foldable region


def scan(text: str) -> list[TagSpan]:
    """Scan `text` for tag positions. Never raises, regardless of how
    malformed or incomplete `text` is."""
    spans: list[TagSpan] = []
    stack: list[TagSpan] = []

    for match in _TAG_RE.finditer(text):
        is_closing = match.group(1) == "/"
        name = match.group(2)
        is_self_closing = match.group(4) == "/"
        open_start = match.start()
        open_end = match.end()

        if is_closing:
            # Find the nearest still-open span with a matching name.
            match_index = None
            for i in range(len(stack) - 1, -1, -1):
                if stack[i].name == name:
                    match_index = i
                    break
            if match_index is None:
                # Stray closing tag matching nothing on the stack: ignore.
                continue
            # Any spans above the matched one were opened but never validly
            # closed before this closing tag: emit as-is with close_end=None.
            for i in range(len(stack) - 1, match_index, -1):
                spans.append(stack.pop(i))
            matched_span = stack.pop(match_index)
            matched_span.close_end = open_end
            spans.append(matched_span)
        elif is_self_closing:
            spans.append(
                TagSpan(
                    name=name,
                    open_start=open_start,
                    open_end=open_end,
                    close_end=open_end,
                    depth=len(stack),
                    self_closing=True,
                )
            )
        else:
            stack.append(
                TagSpan(
                    name=name,
                    open_start=open_start,
                    open_end=open_end,
                    close_end=None,
                    depth=len(stack),
                    self_closing=False,
                )
            )

    # Anything still on the stack at end of input: truncated or genuinely
    # unclosed -- emit as-is with close_end=None.
    spans.extend(stack)
    return spans
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_structure.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_structure.py tests/ui/test_xml_structure.py
git commit -m "feat(xml-editor): add TagSpan and scan() for well-formed nesting"
```

---

### Task 2: `scan()` tolerance — unclosed, mismatched, truncated input

**Files:**
- Modify: `pgtp_editor/ui/xml_structure.py` (no change expected — this task proves the existing algorithm already tolerates these cases; see step 3)
- Test: `tests/ui/test_xml_structure.py`

- [ ] **Step 1: Write the failing tests for tolerance cases**

```python
# Append to tests/ui/test_xml_structure.py

def test_scan_tolerates_unclosed_tags_no_closes_at_all():
    text = "<Page><Detail>"
    spans = scan(text)

    assert len(spans) == 2
    by_name = {span.name: span for span in spans}
    assert by_name["Page"].close_end is None
    assert by_name["Detail"].close_end is None


def test_scan_tolerates_mismatched_tag_closing_outer_before_inner():
    text = "<Page><Detail></Page>"
    spans = scan(text)

    by_name = {span.name: span for span in spans}
    assert by_name["Page"].close_end == len(text)
    assert by_name["Detail"].close_end is None


def test_scan_tolerates_truncated_document_mid_attribute():
    text = '<Page fileName="foo'
    spans = scan(text)

    # The regex simply doesn't match an incomplete tag token: nothing
    # crashes, nothing incorrect is fabricated.
    assert spans == []


def test_scan_tolerates_stray_closing_tag_matching_nothing():
    text = "</Orphan><Page></Page>"
    spans = scan(text)

    by_name = {span.name: span for span in spans}
    assert set(by_name) == {"Page"}
    assert by_name["Page"].close_end == len(text)
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python -m pytest tests/ui/test_xml_structure.py -v`
Expected: These four should already PASS given Task 1's implementation — this step is confirming the tolerance behavior described in the spec (§3.1) is a natural consequence of the stack algorithm, not something that needs new code. If any of them FAIL, the fix is described in Step 3.

- [ ] **Step 3: Fix implementation only if Step 2 showed a failure**

If `test_scan_tolerates_mismatched_tag_closing_outer_before_inner` fails because spans are emitted in the wrong order (e.g. discarded still-open spans should come out before the matched span, matching the order they'd naturally be encountered on the stack), adjust the discard loop in `scan()` to append in stack order (bottom to top of the discarded slice) rather than top-to-bottom:

```python
            for i in range(match_index + 1, len(stack)):
                spans.append(stack[i])
            del stack[match_index + 1 :]
            matched_span = stack.pop(match_index)
            matched_span.close_end = open_end
            spans.append(matched_span)
```

(Only apply this edit if Step 2 actually demonstrated a failure — the algorithm from Task 1 is expected to already satisfy all four tests as written, since none of these tests assert on `spans` list order, only on per-name lookups via a dict.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_structure.py -v`
Expected: PASS (7 tests total)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_structure.py tests/ui/test_xml_structure.py
git commit -m "test(xml-editor): confirm scan() tolerance for unclosed/mismatched/truncated XML"
```

---

### Task 3: `find_enclosing_open_tag()` and `nesting_depth_at()`

**Files:**
- Modify: `pgtp_editor/ui/xml_structure.py`
- Test: `tests/ui/test_xml_structure.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/ui/test_xml_structure.py
from pgtp_editor.ui.xml_structure import find_enclosing_open_tag, nesting_depth_at


def test_find_enclosing_open_tag_inside_nested_element():
    text = "<Page><Detail>text</Detail></Page>"
    # Position inside "text", between Detail's open tag and its close tag.
    position = text.index("text")
    assert find_enclosing_open_tag(text, position) == "Detail"


def test_find_enclosing_open_tag_at_top_level_between_children():
    text = "<Page><Detail></Detail><Detail></Detail></Page>"
    position = text.index("><Detail></Detail></Page>") + 1  # just after first </Detail>
    assert find_enclosing_open_tag(text, position) == "Page"


def test_find_enclosing_open_tag_inside_unclosed_tag():
    text = "<Page><Detail>"
    position = len(text)
    assert find_enclosing_open_tag(text, position) == "Detail"


def test_find_enclosing_open_tag_returns_none_after_everything_closed():
    text = "<Page></Page>"
    position = len(text)
    assert find_enclosing_open_tag(text, position) is None


def test_find_enclosing_open_tag_returns_none_for_position_before_any_tag():
    text = "  <Page></Page>"
    assert find_enclosing_open_tag(text, 0) is None


def test_nesting_depth_at_matches_enclosing_tag_depth():
    text = "<Page><Detail><Column/></Detail></Page>"
    position = text.index("<Column/>")
    assert nesting_depth_at(text, position) == 1  # inside Detail, which is depth 1


def test_nesting_depth_at_is_zero_when_no_enclosing_tag():
    text = "<Page></Page>"
    assert nesting_depth_at(text, len(text)) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_xml_structure.py -v`
Expected: FAIL with `ImportError: cannot import name 'find_enclosing_open_tag'`

- [ ] **Step 3: Implement the query primitives**

Append to `pgtp_editor/ui/xml_structure.py`:

```python
def find_enclosing_open_tag(text: str, position: int) -> str | None:
    """Find the name of the innermost element that contains `position` and
    is not yet known to be closed before it.

    A `TagSpan` is a candidate if `open_start <= position` and either
    `close_end is None` or `close_end > position` (i.e. `position` falls
    strictly inside that element's content span). Among candidates, the one
    with the greatest `depth` is the innermost.
    """
    spans = scan(text)
    candidates = [
        span
        for span in spans
        if span.open_start <= position and (span.close_end is None or span.close_end > position)
    ]
    if not candidates:
        return None
    innermost = max(candidates, key=lambda span: span.depth)
    return innermost.name


def nesting_depth_at(text: str, position: int) -> int:
    """Depth of find_enclosing_open_tag's result, or 0 if none."""
    spans = scan(text)
    candidates = [
        span
        for span in spans
        if span.open_start <= position and (span.close_end is None or span.close_end > position)
    ]
    if not candidates:
        return 0
    innermost = max(candidates, key=lambda span: span.depth)
    return innermost.depth
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_structure.py -v`
Expected: PASS (14 tests total)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_structure.py tests/ui/test_xml_structure.py
git commit -m "feat(xml-editor): add find_enclosing_open_tag and nesting_depth_at query primitives"
```

---

## Part 2 — `XmlEditor` widget, built up incrementally

### Task 4: `XmlEditor` basic construction

**Files:**
- Create: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_xml_editor.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgtp_editor.ui.xml_editor'`

- [ ] **Step 3: Write the minimal `XmlEditor`**

```python
# pgtp_editor/ui/xml_editor.py
"""XmlEditor: a QPlainTextEdit-based editor for raw .pgtp XML text.

Built as a PySide6 port of QCodeEditor's approach (see pgtp_editor/ui/about.py
for the OSS credit). Composed of three cooperating pieces: XmlSyntaxHighlighter
(syntax coloring with unclosed-quote propagation), _EditorGutter (line numbers
and fold markers), and folding/auto-indent/auto-close behavior implemented
directly as XmlEditor methods, since those need direct QTextCursor/QTextBlock
access.
"""
from __future__ import annotations

from PySide6.QtWidgets import QPlainTextEdit


class XmlEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml-editor): add basic XmlEditor(QPlainTextEdit) construction"
```

---

### Task 5: `XmlSyntaxHighlighter` — basic tag/attribute/value/text coloring

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/ui/test_xml_editor.py
from PySide6.QtGui import QTextCharFormat

from pgtp_editor.ui.xml_editor import XmlSyntaxHighlighter


def _format_at(editor, position):
    block = editor.document().findBlock(position)
    layout = block.layout()
    offset_in_block = position - block.position()
    for fmt_range in layout.formats():
        if fmt_range.start <= offset_in_block < fmt_range.start + fmt_range.length:
            return fmt_range.format
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: FAIL with `ImportError: cannot import name 'XmlSyntaxHighlighter'`

- [ ] **Step 3: Implement `XmlSyntaxHighlighter` and wire it into `XmlEditor`**

Replace the contents of `pgtp_editor/ui/xml_editor.py`:

```python
# pgtp_editor/ui/xml_editor.py
"""XmlEditor: a QPlainTextEdit-based editor for raw .pgtp XML text.

Built as a PySide6 port of QCodeEditor's approach (see pgtp_editor/ui/about.py
for the OSS credit). Composed of three cooperating pieces: XmlSyntaxHighlighter
(syntax coloring with unclosed-quote propagation), _EditorGutter (line numbers
and fold markers), and folding/auto-indent/auto-close behavior implemented
directly as XmlEditor methods, since those need direct QTextCursor/QTextBlock
access.
"""
from __future__ import annotations

import re

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QPlainTextEdit

STATE_NORMAL = 0
STATE_IN_UNCLOSED_STRING = 1

# One tag-like token per match: opening ("<name"), attribute name+value
# pairs within it, and the closing ">"/"/>"; plus separate patterns for
# closing tags. Kept intentionally simple -- this highlighter tokenizes
# per-line, not via xml_structure.scan() (which returns whole-element spans,
# not per-token positions within a line).
_TAG_OPEN_RE = re.compile(r"</?[A-Za-z_][\w.-]*")
_TAG_CLOSE_RE = re.compile(r"/?>")
_ATTR_NAME_RE = re.compile(r"[A-Za-z_][\w.-]*(?=\s*=)")
_ATTR_VALUE_RE = re.compile(r'"[^"]*"')


class XmlSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)

        self._tag_format = QTextCharFormat()
        self._tag_format.setForeground(QColor("#569cd6"))

        self._attr_name_format = QTextCharFormat()
        self._attr_name_format.setForeground(QColor("#9cdcfe"))

        self._string_format = QTextCharFormat()
        self._string_format.setForeground(QColor("#ce9178"))

    def highlightBlock(self, text: str) -> None:
        start = 0
        if self.previousBlockState() == STATE_IN_UNCLOSED_STRING:
            close_at = text.find('"')
            if close_at == -1:
                self.setFormat(0, len(text), self._string_format)
                self.setCurrentBlockState(STATE_IN_UNCLOSED_STRING)
                return
            self.setFormat(0, close_at + 1, self._string_format)
            start = close_at + 1

        for match in _TAG_OPEN_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._tag_format)
        for match in _TAG_CLOSE_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._tag_format)
        for match in _ATTR_NAME_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._attr_name_format)
        for match in _ATTR_VALUE_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._string_format)

        if _has_unterminated_quote(text, start):
            self.setCurrentBlockState(STATE_IN_UNCLOSED_STRING)
        else:
            self.setCurrentBlockState(STATE_NORMAL)


def _has_unterminated_quote(text: str, start: int) -> bool:
    return text.count('"', start) % 2 == 1


class XmlEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = XmlSyntaxHighlighter(self.document())
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml-editor): add XmlSyntaxHighlighter with tag/attribute/value coloring"
```

---

### Task 6: Unclosed-quote propagation across lines

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py` (no change expected — proving the block-state mechanism from Task 5 already works; see step 3)
- Test: `tests/ui/test_xml_editor.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/ui/test_xml_editor.py

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
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: These should already PASS given Task 5's `previousBlockState()`/`setCurrentBlockState()` implementation, since Qt automatically re-invokes `highlightBlock` for a block whenever its `previousBlockState()` input changes. This step confirms that live propagation works, not a one-time computation.

- [ ] **Step 3: No implementation change needed**

If Step 2 passed, there is nothing to fix. If either test failed, inspect whether `_has_unterminated_quote` and the early-return branch in `highlightBlock` (Task 5) are reached correctly for a line with zero quotes after `start` — the fix, if needed, is only in the existing `highlightBlock` body from Task 5 (e.g. ensure `_TAG_OPEN_RE`/`_TAG_CLOSE_RE`/`_ATTR_NAME_RE` matching isn't accidentally run when `previousBlockState() == STATE_IN_UNCLOSED_STRING` and the line has no closing quote — the early `return` in Task 5's code already prevents this).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS (7 tests total)

- [ ] **Step 5: Commit**

```bash
git add tests/ui/test_xml_editor.py
git commit -m "test(xml-editor): confirm unclosed-quote format propagates and reverts live"
```

---

### Task 7: Gutter — line numbers

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/ui/test_xml_editor.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: FAIL with `ImportError: cannot import name '_EditorGutter'`

- [ ] **Step 3: Implement `_EditorGutter` with line-number painting and sizing**

Replace the contents of `pgtp_editor/ui/xml_editor.py`:

```python
# pgtp_editor/ui/xml_editor.py
"""XmlEditor: a QPlainTextEdit-based editor for raw .pgtp XML text.

Built as a PySide6 port of QCodeEditor's approach (see pgtp_editor/ui/about.py
for the OSS credit). Composed of three cooperating pieces: XmlSyntaxHighlighter
(syntax coloring with unclosed-quote propagation), _EditorGutter (line numbers
and fold markers), and folding/auto-indent/auto-close behavior implemented
directly as XmlEditor methods, since those need direct QTextCursor/QTextBlock
access.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QPlainTextEdit, QWidget

STATE_NORMAL = 0
STATE_IN_UNCLOSED_STRING = 1

_TAG_OPEN_RE = re.compile(r"</?[A-Za-z_][\w.-]*")
_TAG_CLOSE_RE = re.compile(r"/?>")
_ATTR_NAME_RE = re.compile(r"[A-Za-z_][\w.-]*(?=\s*=)")
_ATTR_VALUE_RE = re.compile(r'"[^"]*"')

# Fixed horizontal allowance reserved for the fold-triangle glyph, added on
# top of the digit-count-dependent width for line numbers.
_FOLD_GLYPH_WIDTH = 16


class XmlSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)

        self._tag_format = QTextCharFormat()
        self._tag_format.setForeground(QColor("#569cd6"))

        self._attr_name_format = QTextCharFormat()
        self._attr_name_format.setForeground(QColor("#9cdcfe"))

        self._string_format = QTextCharFormat()
        self._string_format.setForeground(QColor("#ce9178"))

    def highlightBlock(self, text: str) -> None:
        start = 0
        if self.previousBlockState() == STATE_IN_UNCLOSED_STRING:
            close_at = text.find('"')
            if close_at == -1:
                self.setFormat(0, len(text), self._string_format)
                self.setCurrentBlockState(STATE_IN_UNCLOSED_STRING)
                return
            self.setFormat(0, close_at + 1, self._string_format)
            start = close_at + 1

        for match in _TAG_OPEN_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._tag_format)
        for match in _TAG_CLOSE_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._tag_format)
        for match in _ATTR_NAME_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._attr_name_format)
        for match in _ATTR_VALUE_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._string_format)

        if _has_unterminated_quote(text, start):
            self.setCurrentBlockState(STATE_IN_UNCLOSED_STRING)
        else:
            self.setCurrentBlockState(STATE_NORMAL)


def _has_unterminated_quote(text: str, start: int) -> bool:
    return text.count('"', start) % 2 == 1


class _EditorGutter(QWidget):
    """Line-number and fold-marker gutter, the standard QPlainTextEdit
    side-widget pattern (Qt's "Code Editor Example")."""

    def __init__(self, editor: "XmlEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor._gutter_width(), 0)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#2b2b2b"))

        block = self._editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self._editor.blockBoundingGeometry(block).translated(
            self._editor.contentOffset()
        ).top()
        bottom = top + self._editor.blockBoundingRect(block).height()

        digit_width = self._editor.fontMetrics().horizontalAdvance("9")
        line_number_width = self.width() - _FOLD_GLYPH_WIDTH

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number_text = str(block_number + 1)
                painter.setPen(QColor("#858585"))
                painter.drawText(
                    0,
                    int(top),
                    line_number_width,
                    self._editor.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number_text,
                )

            block = block.next()
            top = bottom
            bottom = top + self._editor.blockBoundingRect(block).height()
            block_number += 1


class XmlEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = XmlSyntaxHighlighter(self.document())
        self._gutter = _EditorGutter(self)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter_on_scroll)
        self._update_gutter_width(0)

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)

    def _gutter_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        digit_width = self.fontMetrics().horizontalAdvance("9")
        return digits * digit_width + _FOLD_GLYPH_WIDTH + 6

    def _update_gutter_width(self, _new_block_count: int) -> None:
        self.setViewportMargins(self._gutter_width(), 0, 0, 0)

    def _update_gutter_on_scroll(self, rect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        contents_rect = self.contentsRect()
        self._gutter.setGeometry(
            QRect(contents_rect.left(), contents_rect.top(), self._gutter_width(), contents_rect.height())
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS (10 tests total)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml-editor): add gutter with line-number painting and dynamic width"
```

---

### Task 8: Folding — `_fold_state`, `_toggle_fold`, and fold-triangle gutter glyphs

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/ui/test_xml_editor.py

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: FAIL with `AttributeError: 'XmlEditor' object has no attribute '_toggle_fold'`

- [ ] **Step 3: Implement folding**

Add to `pgtp_editor/ui/xml_editor.py`. First add the import at the top (extend the existing import line):

```python
from pgtp_editor.ui import xml_structure
```

Then extend `XmlEditor.__init__` (replace the existing `__init__` body) and add the new methods:

```python
class XmlEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = XmlSyntaxHighlighter(self.document())
        self._gutter = _EditorGutter(self)
        self._fold_state: dict[int, bool] = {}
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter_on_scroll)
        self.textChanged.connect(self._rescan_structure)
        self._update_gutter_width(0)
        self._rescan_structure()

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
        # Folding state is per-document-instance; a fresh setPlainText call
        # (a new file loaded into this editor) starts fully unfolded.
        self._fold_state = {}

    def _rescan_structure(self) -> None:
        self._spans = xml_structure.scan(self.toPlainText())

    def _foldable_region_starting_at(self, block):
        """Return (first_contained_block_number, last_contained_block_number)
        for the foldable region whose open tag starts on `block`, or None if
        no such region exists (no matching TagSpan, self-closing, or a
        single-line element)."""
        text = self.toPlainText()
        block_start = block.position()
        block_end = block_start + block.length()
        for span in self._spans:
            if span.self_closing or span.close_end is None:
                continue
            if not (block_start <= span.open_start < block_end):
                continue
            open_line = self.document().findBlock(span.open_start).blockNumber()
            close_line = self.document().findBlock(span.close_end - 1).blockNumber()
            if open_line == close_line:
                continue  # single-line element: nothing to fold
            return open_line + 1, close_line - 1
        return None

    def _toggle_fold(self, block) -> None:
        region = self._foldable_region_starting_at(block)
        if region is None:
            return
        first_contained, last_contained = region
        block_number = block.blockNumber()
        currently_collapsed = self._fold_state.get(block_number, False)
        new_visible = currently_collapsed  # if collapsed, expand; else collapse
        for line_number in range(first_contained, last_contained + 1):
            contained_block = self.document().findBlockByNumber(line_number)
            contained_block.setVisible(new_visible)
        self._fold_state[block_number] = not currently_collapsed
        self.document().markContentsDirty(block.position(), self.document().characterCount() - block.position())
        self.viewport().update()
```

Also update `_gutter_width`'s docstring context is unaffected; no other method changes are needed for this task.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS (14 tests total)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml-editor): add code folding via xml_structure.scan() and QTextBlock.setVisible"
```

---

### Task 9: Gutter fold-triangle glyphs and click handling

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/ui/test_xml_editor.py
from PySide6.QtCore import QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import QEvent

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: FAIL (either an `AttributeError` because `mousePressEvent` isn't overridden yet, or the assertion fails since nothing collapsed).

- [ ] **Step 3: Add fold-triangle painting and gutter click handling**

Modify `_EditorGutter.paintEvent` in `pgtp_editor/ui/xml_editor.py` — replace the whole method body to add the fold-triangle drawing:

```python
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#2b2b2b"))

        block = self._editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self._editor.blockBoundingGeometry(block).translated(
            self._editor.contentOffset()
        ).top()
        bottom = top + self._editor.blockBoundingRect(block).height()

        line_number_width = self.width() - _FOLD_GLYPH_WIDTH

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number_text = str(block_number + 1)
                painter.setPen(QColor("#858585"))
                painter.drawText(
                    0,
                    int(top),
                    line_number_width,
                    self._editor.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number_text,
                )

                if self._editor._foldable_region_starting_at(block) is not None:
                    collapsed = self._editor._fold_state.get(block_number, False)
                    self._draw_fold_glyph(painter, int(top), collapsed)

            block = block.next()
            top = bottom
            bottom = top + self._editor.blockBoundingRect(block).height()
            block_number += 1

    def _draw_fold_glyph(self, painter: QPainter, top: int, collapsed: bool) -> None:
        line_height = self._editor.fontMetrics().height()
        glyph_left = self.width() - _FOLD_GLYPH_WIDTH
        glyph_size = min(_FOLD_GLYPH_WIDTH - 4, line_height - 4)
        cx = glyph_left + _FOLD_GLYPH_WIDTH // 2
        cy = top + line_height // 2
        half = glyph_size // 2
        painter.setPen(QColor("#858585"))
        painter.setBrush(QColor("#858585"))
        if collapsed:
            # Right-pointing triangle.
            points = [QPoint(cx - half, cy - half), QPoint(cx - half, cy + half), QPoint(cx + half, cy)]
        else:
            # Down-pointing triangle.
            points = [QPoint(cx - half, cy - half), QPoint(cx + half, cy - half), QPoint(cx, cy + half)]
        painter.drawPolygon(points)

    def mousePressEvent(self, event) -> None:
        glyph_left = self.width() - _FOLD_GLYPH_WIDTH
        if event.position().x() < glyph_left:
            return
        block = self._editor.firstVisibleBlock()
        top = self._editor.blockBoundingGeometry(block).translated(
            self._editor.contentOffset()
        ).top()
        bottom = top + self._editor.blockBoundingRect(block).height()
        click_y = event.position().y()

        while block.isValid() and top <= click_y:
            if block.isVisible() and top <= click_y < bottom:
                self._editor._toggle_fold(block)
                self.update()
                return
            block = block.next()
            top = bottom
            bottom = top + self._editor.blockBoundingRect(block).height()
```

Also add `from PySide6.QtCore import QPoint` to the existing `PySide6.QtCore` import line at the top of the file (change `from PySide6.QtCore import QRect, QSize, Qt` to `from PySide6.QtCore import QPoint, QRect, QSize, Qt`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS (15 tests total)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml-editor): draw fold-triangle glyphs in gutter and handle click-to-toggle"
```

---

### Task 10: Line-wrap toggle

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/ui/test_xml_editor.py

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: FAIL with `AttributeError: 'XmlEditor' object has no attribute 'set_line_wrap_enabled'`

- [ ] **Step 3: Implement `set_line_wrap_enabled`**

Add this method to the `XmlEditor` class in `pgtp_editor/ui/xml_editor.py` (anywhere among the other methods):

```python
    def set_line_wrap_enabled(self, enabled: bool) -> None:
        self.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if enabled
            else QPlainTextEdit.LineWrapMode.NoWrap
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS (17 tests total)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml-editor): add set_line_wrap_enabled toggle"
```

---

### Task 11: Current-line highlighting

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/ui/test_xml_editor.py

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
    first_selection_block = editor.extraSelections()[0].cursor.blockNumber()

    cursor.setPosition(len("line one") + 1)
    editor.setTextCursor(cursor)
    second_selection_block = editor.extraSelections()[0].cursor.blockNumber()

    assert first_selection_block == 0
    assert second_selection_block == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: FAIL — `extraSelections()` is empty (length 0), not 1.

- [ ] **Step 3: Implement current-line highlighting**

Add the import `QColor` is already imported; add `QTextEdit` and `QTextFormat` to the `PySide6.QtWidgets`/`PySide6.QtGui` imports at the top of `pgtp_editor/ui/xml_editor.py`. Change:

```python
from PySide6.QtGui import QColor, QPainter, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QPlainTextEdit, QWidget
```

to:

```python
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget
```

(This replaces the earlier `from PySide6.QtCore import QPoint, QRect, QSize, Qt` line rather than duplicating it — there should be exactly one `PySide6.QtCore` import line in the file.)

Then update `XmlEditor.__init__` to add the `_current_line_color` attribute, connect the signal, and call the handler once at startup — replace the `__init__` method body:

```python
    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = XmlSyntaxHighlighter(self.document())
        self._gutter = _EditorGutter(self)
        self._fold_state: dict[int, bool] = {}
        self._current_line_color = QColor("#2d2d30")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter_on_scroll)
        self.textChanged.connect(self._rescan_structure)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_gutter_width(0)
        self._rescan_structure()
        self._highlight_current_line()
```

And add the new method:

```python
    def _highlight_current_line(self) -> None:
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(self._current_line_color)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS (19 tests total)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml-editor): add current-line highlighting on cursorPositionChanged"
```

---

### Task 12: Auto-indent on Enter

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/ui/test_xml_editor.py
from PySide6.QtCore import Qt as QtCoreQt  # already imported as Qt; alias avoided below


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: FAIL — plain `QPlainTextEdit.keyPressEvent` inserts a bare `"\n"` with no leading whitespace, so `lines[1]` is `""`, not `"  "`.

- [ ] **Step 3: Implement `keyPressEvent` override with auto-indent**

Add the import at the top of `pgtp_editor/ui/xml_editor.py` (extend the existing `from pgtp_editor.ui import xml_structure` line is already present from Task 8; add `QKeyEvent` and `QTextCursor` imports):

```python
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
```

(replacing the previous, shorter `PySide6.QtGui` import line so there is exactly one).

Add these methods to `XmlEditor`:

```python
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._insert_newline_with_indent()
            return
        super().keyPressEvent(event)

    def _insert_newline_with_indent(self) -> None:
        cursor = self.textCursor()
        current_line = cursor.block().text()
        leading_ws = current_line[: len(current_line) - len(current_line.lstrip())]
        position = cursor.position() - cursor.block().position()
        enclosing = xml_structure.find_enclosing_open_tag(self.toPlainText(), cursor.position())
        extra_indent = ""
        if enclosing is not None and _cursor_immediately_after_open_tag(current_line, position, enclosing):
            extra_indent = "  "
        cursor.insertText("\n" + leading_ws + extra_indent)
```

Add this module-level helper function (near the bottom of the file, after the `XmlEditor` class or after `_has_unterminated_quote`):

```python
def _cursor_immediately_after_open_tag(line_text: str, position_in_line: int, tag_name: str) -> bool:
    """True if the text on `line_text` immediately before `position_in_line`
    ends with the enclosing tag's own opening `>` and nothing else (i.e.
    there is no content yet between the open tag and the cursor)."""
    before_cursor = line_text[:position_in_line]
    stripped = before_cursor.rstrip()
    return stripped.endswith(">") and f"<{tag_name}" in stripped and not stripped.endswith("/>")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS (21 tests total)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml-editor): add auto-indent on Enter, inherit and after-opening-tag cases"
```

---

### Task 13: Auto-close `<>` and quote pairs

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/ui/test_xml_editor.py

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: FAIL — typing `<` inserts only `<`, not `<>`; typing `"` after `=` inserts only one quote.

- [ ] **Step 3: Implement bracket and quote auto-closing**

Update `XmlEditor.keyPressEvent` in `pgtp_editor/ui/xml_editor.py` — replace it entirely:

```python
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._insert_newline_with_indent()
            return

        if event.text() == "<":
            cursor = self.textCursor()
            cursor.insertText("<>")
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cursor)
            return

        if event.text() in ('"', "'"):
            cursor = self.textCursor()
            char_before = self._character_before_cursor(cursor)
            if char_before == "=":
                quote = event.text()
                cursor.insertText(quote + quote)
                cursor.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cursor)
                return

        if event.text() == ">":
            if self._type_through_auto_closed_greater_than():
                return
            super().keyPressEvent(event)
            self._maybe_insert_closing_tag()
            return

        super().keyPressEvent(event)

    def _character_before_cursor(self, cursor: QTextCursor) -> str:
        position = cursor.position()
        if position == 0:
            return ""
        probe = QTextCursor(self.document())
        probe.setPosition(position - 1)
        probe.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
        return probe.selectedText()

    def _character_after_cursor(self, cursor: QTextCursor) -> str:
        position = cursor.position()
        probe = QTextCursor(self.document())
        probe.setPosition(position)
        probe.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
        return probe.selectedText()

    def _type_through_auto_closed_greater_than(self) -> bool:
        cursor = self.textCursor()
        if self._character_after_cursor(cursor) == ">":
            cursor.movePosition(QTextCursor.MoveOperation.Right)
            self.setTextCursor(cursor)
            return True
        return False

    def _maybe_insert_closing_tag(self) -> None:
        cursor = self.textCursor()
        text = self.toPlainText()
        position = cursor.position()
        # Only auto-insert a closing tag when the '>' just typed completes a
        # non-self-closing opening tag (does not end in "/>").
        line_start = cursor.block().position()
        text_before_cursor_on_line = text[line_start:position]
        if text_before_cursor_on_line.rstrip().endswith("/>"):
            return
        enclosing = xml_structure.find_enclosing_open_tag(text, position)
        if enclosing is None:
            return
        cursor.insertText(f"</{enclosing}>")
        cursor.setPosition(position)
        self.setTextCursor(cursor)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS (25 tests total)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml-editor): add auto-close for angle brackets and quote pairs after '='"
```

---

### Task 14: Auto-close completed opening tag with matching `</name>`

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py` (no change expected — Task 13 already wired `_maybe_insert_closing_tag`; this task adds direct tests for it)
- Test: `tests/ui/test_xml_editor.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/ui/test_xml_editor.py

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

    qtbot.keyClicks(editor, "<Page")
    # Move past the auto-inserted ">" is not yet needed; type "/" then ">".
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Right)  # skip over auto-closed ">"
    editor.setTextCursor(cursor)
    qtbot.keyClicks(editor, "/")
    # No further ">" needed: cursor now points at "/" inserted right before "<Page>"'s own ">".

    assert editor.toPlainText() in ("<Page/>", "<Page/></Page>".replace("</Page>", ""))
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: `test_completing_opening_tag_auto_inserts_matching_close_tag` should PASS given Task 13's `_maybe_insert_closing_tag` wiring — this confirms the "type-through" plus "insert closing tag" behavior end-to-end. The second test is a loosely-specified probe of the self-closing case's typed sequence and is expected to need adjustment; replace it in Step 3 if it fails, since the exact keystroke sequence for producing `<Page/>` interactively is easy to get wrong in a test and isn't specified precisely by the design doc beyond "does not end in `/>`" being the exemption check already implemented.

- [ ] **Step 3: Tighten the self-closing test to a direct, unambiguous check**

Replace `test_self_closing_tag_does_not_get_a_matching_close_tag` with a version that constructs the "typed so far" state directly via `setPlainText` (bypassing the ambiguous keystroke sequence) and then simulates only the final `>` keypress, which is what `_maybe_insert_closing_tag` actually branches on:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS (27 tests total)

- [ ] **Step 5: Commit**

```bash
git add tests/ui/test_xml_editor.py
git commit -m "test(xml-editor): confirm auto-close inserts matching close tag, skips self-closing tags"
```

---

## Part 3 — `PgtpParseError.line` field

### Task 15: Add `line` field to `PgtpParseError`, populate from `XMLSyntaxError.lineno`

**Files:**
- Modify: `pgtp_editor/model/parser.py:22-37`
- Test: `tests/model/test_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/model/test_parser.py

def test_pgtp_parse_error_carries_line_number_for_xml_syntax_error(tmp_path):
    path = tmp_path / "broken.pgtp"
    # Genuinely malformed XML (mismatched root tag) triggers XMLSyntaxError,
    # not the broader structural except clause.
    path.write_text(
        "<Project>\n<Presentation>\n<Pages>\n<Page>\n</Pages>\n</Presentation>\n</Project>",
        encoding="utf-8",
    )
    with pytest.raises(PgtpParseError) as excinfo:
        load_project(path)
    assert excinfo.value.line is not None
    assert excinfo.value.line > 0


def test_pgtp_parse_error_line_is_none_for_structural_failure(tmp_path):
    path = write_pgtp(tmp_path, DETAIL_MISSING_NESTED_PAGE_PROJECT)
    with pytest.raises(PgtpParseError) as excinfo:
        load_project(path)
    assert excinfo.value.line is None


def test_pgtp_parse_error_line_defaults_to_none():
    exc = PgtpParseError("some message")
    assert exc.line is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/model/test_parser.py -v`
Expected: FAIL with `AttributeError: 'PgtpParseError' object has no attribute 'line'`

- [ ] **Step 3: Add the `line` field to `PgtpParseError` and populate it in `load_project`**

In `pgtp_editor/model/parser.py`, replace lines 22-37 (the `PgtpParseError` class definition and the first `try`/`except` block inside `load_project`):

```python
class PgtpParseError(Exception):
    """Raised when a .pgtp file cannot be parsed into a ProjectModel.

    `line` carries the 1-based line number of the failure when it is known
    (always known for an XML syntax error, via lxml's XMLSyntaxError.lineno;
    never known for a structurally-unexpected-but-well-formed document, since
    there is no single line at fault in that case).
    """

    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.line = line


def load_project(path) -> ProjectModel:
    """Parse the .pgtp file at `path` and return a ProjectModel.

    Raises PgtpParseError on malformed/unexpected XML so callers (e.g. the
    UI's File -> Open handler) can surface a clear error instead of letting
    an lxml exception bubble up uncaught or silently returning an empty
    project.
    """
    try:
        tree = etree.parse(str(path))
    except (etree.XMLSyntaxError, OSError) as exc:
        line = exc.lineno if isinstance(exc, etree.XMLSyntaxError) else None
        raise PgtpParseError(f"Could not parse '{path}': {exc}", line=line) from exc
```

(The rest of `load_project` — the `root = tree.getroot()` line onward, including the second, broader `except Exception` clause — is unchanged; it continues to raise `PgtpParseError(f"Could not parse '{path}': {exc}") from exc`, i.e. with `line=None` via the new default.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/model/test_parser.py -v`
Expected: PASS (all tests, including the 3 new ones)

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `python -m pytest tests/ -v`
Expected: PASS (all prior tests unaffected by this change)

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/model/parser.py tests/model/test_parser.py
git commit -m "feat(parser): add PgtpParseError.line populated from XMLSyntaxError.lineno"
```

---

## Part 4 — Wiring

### Task 16: `CenterStage` — replace Raw XML placeholder with real `XmlEditor`

**Files:**
- Modify: `pgtp_editor/ui/center_stage.py`
- Test: `tests/ui/test_center_stage.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/ui/test_center_stage.py
from pgtp_editor.ui.xml_editor import XmlEditor


def test_raw_xml_tab_holds_a_real_xml_editor(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.xml_editor, XmlEditor)
    assert stage.widget(stage.raw_xml_tab_index) is stage.xml_editor
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_center_stage.py -v`
Expected: FAIL with `AttributeError: 'CenterStage' object has no attribute 'xml_editor'`

- [ ] **Step 3: Wire `XmlEditor` into `CenterStage`**

Replace the full contents of `pgtp_editor/ui/center_stage.py`:

```python
from PySide6.QtWidgets import QTabWidget, QWidget

from pgtp_editor.ui.diff_merge_panel import DiffMergePanel
from pgtp_editor.ui.xml_editor import XmlEditor


class CenterStage(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.diff_merge_panel = DiffMergePanel()
        self.diff_merge_tab_index = self.addTab(self.diff_merge_panel, "Diff / Merge")
        self.caption_management_tab_index = self.addTab(QWidget(), "Caption Management")
        self.xml_editor = XmlEditor()
        self.raw_xml_tab_index = self.addTab(self.xml_editor, "Raw XML")
        self.setTabVisible(self.raw_xml_tab_index, False)

    def set_raw_xml_tab_visible(self, visible):
        self.setTabVisible(self.raw_xml_tab_index, visible)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_center_stage.py -v`
Expected: PASS (all tests, including the new one)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/center_stage.py tests/ui/test_center_stage.py
git commit -m "feat(xml-editor): wire XmlEditor into CenterStage's Raw XML tab"
```

---

### Task 17: Promote the Raw XML Panel action to `self._raw_xml_panel_action`, add "Wrap Raw XML Lines" action

**Files:**
- Modify: `pgtp_editor/ui/main_window.py:211-236` (`_build_view_menu`)
- Test: `tests/ui/test_menus.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/ui/test_menus.py

def test_raw_xml_panel_action_is_accessible_as_attribute(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert window._raw_xml_panel_action is find_action(view_menu, "Raw XML Panel")


def test_view_menu_contains_wrap_raw_xml_lines_action(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert action_labels(view_menu) == [
        "Project Tree", "Properties Panel", "Audit/Problems Panel", "Raw XML Panel",
        "Wrap Raw XML Lines", "―",
        "Expand All", "Collapse All",
    ]


def test_wrap_raw_xml_lines_action_default_unchecked(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert find_action(view_menu, "Wrap Raw XML Lines").isChecked() is False


def test_toggling_wrap_raw_xml_lines_changes_editor_line_wrap_mode(qtbot):
    from PySide6.QtWidgets import QPlainTextEdit

    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Wrap Raw XML Lines").trigger()
    assert window.center_stage.xml_editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_menus.py -v`
Expected: FAIL — `test_view_menu_contains_wrap_raw_xml_lines_action` fails since the action doesn't exist yet; the existing `test_view_menu_contents` (unmodified) will also start failing since the action list now differs from what this new test expects — that's expected and resolved once `_build_view_menu` is updated in Step 3, but note `test_view_menu_contents` (the pre-existing test, listed at line 64-71 of the original file) must also be updated to include the new action, or it will remain broken. Update it now in the same edit as Step 3, changing its expected list to match `test_view_menu_contains_wrap_raw_xml_lines_action`'s list above.

- [ ] **Step 3: Update `_build_view_menu` and the pre-existing `test_view_menu_contents`**

In `pgtp_editor/ui/main_window.py`, replace the `_build_view_menu` method (lines 211-236):

```python
    def _build_view_menu(self):
        menu = self.menuBar().addMenu("View")

        tree_action = menu.addAction("Project Tree")
        tree_action.setCheckable(True)
        tree_action.setChecked(True)
        tree_action.toggled.connect(self.tree_dock.setVisible)

        properties_action = menu.addAction("Properties Panel")
        properties_action.setCheckable(True)
        properties_action.setChecked(True)
        properties_action.toggled.connect(self.properties_dock.setVisible)

        audit_action = menu.addAction("Audit/Problems Panel")
        audit_action.setCheckable(True)
        audit_action.setChecked(True)
        audit_action.toggled.connect(self.audit_dock.setVisible)

        self._raw_xml_panel_action = menu.addAction("Raw XML Panel")
        self._raw_xml_panel_action.setCheckable(True)
        self._raw_xml_panel_action.setChecked(False)
        self._raw_xml_panel_action.toggled.connect(self.center_stage.set_raw_xml_tab_visible)

        line_wrap_action = menu.addAction("Wrap Raw XML Lines")
        line_wrap_action.setCheckable(True)
        line_wrap_action.setChecked(False)
        line_wrap_action.toggled.connect(self.center_stage.xml_editor.set_line_wrap_enabled)

        menu.addSeparator()
        self._add_stub_action(menu, "Expand All")
        self._add_stub_action(menu, "Collapse All")
```

In `tests/ui/test_menus.py`, update the pre-existing `test_view_menu_contents` (originally lines 64-71) to match the new action list:

```python
def test_view_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert action_labels(view_menu) == [
        "Project Tree", "Properties Panel", "Audit/Problems Panel", "Raw XML Panel",
        "Wrap Raw XML Lines", "―",
        "Expand All", "Collapse All",
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_menus.py -v`
Expected: PASS (all tests, including the 4 new ones and the updated `test_view_menu_contents`)

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_menus.py
git commit -m "feat(xml-editor): add Wrap Raw XML Lines action, promote Raw XML Panel action to self attribute"
```

---

### Task 18: Populate the editor on successful open

**Files:**
- Modify: `pgtp_editor/ui/main_window.py:67-88` (`open_project_file`)
- Test: `tests/ui/test_open_project.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/ui/test_open_project.py

def test_open_project_file_populates_xml_editor_with_raw_text(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "valid.pgtp"
    path.write_text(VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(path))

    assert window.center_stage.xml_editor.toPlainText() == VALID_PGTP
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_open_project.py -v`
Expected: FAIL — `xml_editor.toPlainText()` is empty, since `open_project_file` doesn't populate it yet.

- [ ] **Step 3: Update `open_project_file`'s success path**

In `pgtp_editor/ui/main_window.py`, replace `open_project_file` (lines 67-88):

```python
    def open_project_file(self, path):
        """Load and display the .pgtp project at `path`.

        Split out from `_open_project` so tests can drive the load without
        going through the QFileDialog. On parse failure, shows a clear
        error dialog, populates the Raw XML fallback view (see
        `_handle_parse_failure`), and leaves the currently-displayed tree
        (and the currently-tracked project) untouched (never a crash, never
        a silently-emptied tree or a silently-forgotten project).
        """
        try:
            project = load_project(path)
        except PgtpParseError as exc:
            self._handle_parse_failure(path, exc)
            return
        self.project_tree.populate_from_project(project)
        self._current_project = project
        self._current_project_path = path
        with open(path, "r", encoding="utf-8") as f:
            raw_text = f.read()
        self.center_stage.xml_editor.setPlainText(raw_text)
        self.statusBar().showMessage(f"Opened: {path}", 5000)
```

Add the `PgtpParseError` import at the top of `pgtp_editor/ui/main_window.py` — change:

```python
from pgtp_editor.model.parser import load_project
```

to:

```python
from pgtp_editor.model.parser import PgtpParseError, load_project
```

Note: this narrows the caught exception type from `except Exception` to `except PgtpParseError`, per the design spec §4.2 — any other unexpected exception (e.g. a permissions error unrelated to XML well-formedness) will now surface distinctly rather than being funneled into the Tier-1 fallback flow. This is intentional and is exercised further by Task 19's fallback tests.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_open_project.py -v`
Expected: FAIL still — `_handle_parse_failure` doesn't exist yet, so the existing `test_open_project_file_shows_error_dialog_on_malformed_xml` and related tests that rely on `except Exception`/`QMessageBox.critical` inline will break. This is expected; `_handle_parse_failure` is added in Task 19, which this task depends on being done together. Proceed directly to Task 19 before attempting a full green run — do not attempt to make this task pass in isolation, since `PgtpParseError` narrowing requires `_handle_parse_failure` to exist for the malformed-XML test paths to keep working.

- [ ] **Step 5: Commit (staged together with Task 19 — see Task 19 Step 1 for the combined test run before this commit)**

Hold this commit until Task 19's Step 1 test file changes are also written; then run the combined test suite (Task 19 Step 4) and commit both changes together as described in Task 19 Step 6. Do not run `git commit` yet.

---

### Task 19: Tier-1 fallback — `_handle_parse_failure`, error-line highlighting

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (add `_handle_parse_failure`; add `highlight_error_line` to `pgtp_editor/ui/xml_editor.py`)
- Modify: `pgtp_editor/ui/xml_editor.py` (add `highlight_error_line` method)
- Test: `tests/ui/test_open_project.py`, `tests/ui/test_xml_editor.py`

- [ ] **Step 1: Write the failing tests for `highlight_error_line`**

```python
# Append to tests/ui/test_xml_editor.py

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
    assert len(editor.extraSelections()) == 1
    assert editor.extraSelections()[0].cursor.blockNumber() == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: FAIL with `AttributeError: 'XmlEditor' object has no attribute 'highlight_error_line'`

- [ ] **Step 3: Implement `highlight_error_line`**

Add `_error_line_color` to `XmlEditor.__init__` (extend the existing `__init__`, adding one line near `self._current_line_color`):

```python
        self._current_line_color = QColor("#2d2d30")
        self._error_line_color = QColor("#5a1d1d")
```

Add the method:

```python
    def highlight_error_line(self, line: int) -> None:
        block = self.document().findBlockByNumber(max(0, line - 1))  # 1-based -> 0-based
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()

        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(self._error_line_color)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = cursor
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS (all tests, including the 2 new ones)

- [ ] **Step 5: Write the failing wiring tests for `_handle_parse_failure`**

```python
# Append to tests/ui/test_open_project.py

MALFORMED_PGTP_WITH_KNOWN_LINE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<Project>\n"
    "  <Presentation>\n"
    "    <Pages>\n"
    "      <Page>\n"
    "    </Pages>\n"
    "  </Presentation>\n"
    "</Project>\n"
)


def test_parse_failure_populates_and_shows_raw_xml_tab(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "broken.pgtp"
    path.write_text(MALFORMED_PGTP_WITH_KNOWN_LINE, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(path))

    assert window.center_stage.isTabVisible(window.center_stage.raw_xml_tab_index) is True
    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index
    assert window.center_stage.xml_editor.toPlainText() == MALFORMED_PGTP_WITH_KNOWN_LINE


def test_parse_failure_syncs_raw_xml_panel_checkbox(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "broken.pgtp"
    path.write_text(MALFORMED_PGTP_WITH_KNOWN_LINE, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(path))

    assert window._raw_xml_panel_action.isChecked() is True


def test_parse_failure_highlights_the_reported_error_line(qtbot, tmp_path):
    from lxml import etree

    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "broken.pgtp"
    path.write_text(MALFORMED_PGTP_WITH_KNOWN_LINE, encoding="utf-8")

    # Establish, independently of this test's assumptions, what line lxml
    # itself reports for this fixture -- rather than hard-coding a guessed
    # line number.
    try:
        etree.parse(str(path))
        expected_line = None
    except etree.XMLSyntaxError as exc:
        expected_line = exc.lineno
    assert expected_line is not None

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(path))

    selections = window.center_stage.xml_editor.extraSelections()
    assert len(selections) == 1
    assert selections[0].cursor.blockNumber() == expected_line - 1


def test_parse_failure_still_shows_dialog(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "broken.pgtp"
    path.write_text(MALFORMED_PGTP_WITH_KNOWN_LINE, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window.open_project_file(str(path))

    mock_critical.assert_called_once()


def test_parse_failure_does_not_crash_when_file_unreadable_after_initial_parse_attempt(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    missing_path = tmp_path / "does_not_exist.pgtp"

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(missing_path))

    # A missing file raises PgtpParseError via the OSError branch in
    # load_project; _handle_parse_failure's own re-read then also fails with
    # OSError, and must not crash -- it simply leaves the Raw XML tab alone.
    assert window.center_stage.isTabVisible(window.center_stage.raw_xml_tab_index) is False
```

- [ ] **Step 6: Run test to verify it fails**

Run: `python -m pytest tests/ui/test_open_project.py -v`
Expected: FAIL — `_handle_parse_failure` does not exist yet on `MainWindow`; `open_project_file` from Task 18 currently references it in its `except PgtpParseError` branch, so these new tests, plus the earlier existing tests (`test_open_project_file_shows_error_dialog_on_malformed_xml`, etc.), all fail with `AttributeError: 'MainWindow' object has no attribute '_handle_parse_failure'`.

- [ ] **Step 7: Implement `_handle_parse_failure`**

Add this method to `MainWindow` in `pgtp_editor/ui/main_window.py`, directly after `open_project_file`:

```python
    def _handle_parse_failure(self, path, exc: PgtpParseError) -> None:
        QMessageBox.critical(
            self,
            "Failed to Open Project",
            f"Could not open '{path}':\n\n{exc}",
        )
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_text = f.read()
        except OSError:
            # The file itself is unreadable (e.g. deleted between the
            # earlier parse attempt and this read, or a permissions error) --
            # nothing to show in the fallback view in that case; the dialog
            # above already reported the failure.
            return
        self.center_stage.xml_editor.setPlainText(raw_text)
        if exc.line is not None:
            self.center_stage.xml_editor.highlight_error_line(exc.line)
        self.center_stage.set_raw_xml_tab_visible(True)
        self._raw_xml_panel_action.setChecked(True)
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)
```

- [ ] **Step 8: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_open_project.py -v`
Expected: PASS (all tests, including the 5 new ones and all pre-existing ones from Task 18's narrowed exception handling)

- [ ] **Step 9: Run the full test suite to confirm no regressions**

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests across the project)

- [ ] **Step 10: Commit (this commit includes Task 18's held-over changes)**

```bash
git add pgtp_editor/ui/main_window.py pgtp_editor/ui/xml_editor.py tests/ui/test_open_project.py tests/ui/test_xml_editor.py
git commit -m "feat(xml-editor): wire Tier-1 parse-failure fallback to populate, show, and highlight Raw XML tab"
```

---

### Task 20: Verify the QCodeEditor OSS credit (no code change)

**Files:**
- Verify only: `pgtp_editor/ui/about.py`, `tests/ui/test_about.py`

- [ ] **Step 1: Re-confirm the credit already exists and its test already passes**

Run: `python -m pytest tests/ui/test_about.py -v`
Expected: PASS — `test_credits_mention_all_three_projects` already asserts `"QCodeEditor" in ABOUT_TEXT`, and `pgtp_editor/ui/about.py`'s `ABOUT_TEXT` already contains:

```
<li><a href="https://github.com/luchko/QCodeEditor">QCodeEditor</a>
(luchko, MIT License) &mdash; the code-editor widget is a PySide6 port
of this project's approach.</li>
```

No file changes are made in this task — it is a verification step only, per the design spec §4.6, which confirmed this credit was added ahead of the widget by the original 12-task shell plan and remains accurate now that `XmlEditor` is actually built along the described lines (line numbers, current-line highlighting, the `QSyntaxHighlighter` hook pattern).

- [ ] **Step 2: No commit needed**

This task makes no changes to any file, so there is nothing to commit.

---

### Task 21: Wiring test — successful open populates the editor byte-for-byte from a real sample file

**Files:**
- Test: `tests/ui/test_open_project.py`

- [ ] **Step 1: Write the test using a real sample file**

```python
# Append to tests/ui/test_open_project.py
from pathlib import Path

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"


def test_open_real_sample_file_populates_editor_byte_for_byte(qtbot):
    sample_path = SAMPLE_DIR / "dev_Ferrara.pgtp"
    assert sample_path.exists(), f"expected sample fixture at {sample_path}"

    window = MainWindow()
    qtbot.addWidget(window)

    window.open_project_file(str(sample_path))

    expected_text = sample_path.read_text(encoding="utf-8")
    assert window.center_stage.xml_editor.toPlainText() == expected_text
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/ui/test_open_project.py::test_open_real_sample_file_populates_editor_byte_for_byte -v`
Expected: PASS. If it fails because `dev_Ferrara.pgtp` fails to parse via `load_project` (routing into `_handle_parse_failure` instead of the success path, which also populates `xml_editor` — the assertion would still pass either way, since both paths call `setPlainText(raw_text)` with the same file content), the assertion still holds; if it fails for any other reason (e.g. the sample file is missing in this environment), investigate rather than skip — `sample/` is confirmed present in this worktree per the task's Required Reading.

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_open_project.py
git commit -m "test(xml-editor): confirm real sample file opens byte-for-byte into the XML editor"
```

---

## Part 5 — Final full-suite verification

### Task 22: Full test suite run and final review

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `python -m pytest tests/ -v`
Expected: PASS — every test across `tests/diff/`, `tests/model/`, `tests/schema_learning/`, and `tests/ui/` (including all new `tests/ui/test_xml_structure.py` and `tests/ui/test_xml_editor.py` tests, and the updated `tests/ui/test_open_project.py`, `tests/ui/test_menus.py`, `tests/ui/test_center_stage.py`, `tests/model/test_parser.py`).

- [ ] **Step 2: Confirm git log shows all commits from this plan**

Run: `git log --oneline -25`
Expected: one commit per task above (Tasks 1-3, 5-14, 16-19, 21 each produced a commit; Task 4 produced a commit; Task 15 produced a commit; Task 20 produced none; Task 18 held its commit until folded into Task 19's).

- [ ] **Step 3: No further commit needed for this task**

This is a verification-only task.
