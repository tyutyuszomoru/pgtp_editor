# Ctrl+click / Alt+click Tag Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the Raw XML editor, **Ctrl+left-click** on a tag jumps the caret to its matching open/close tag; **Alt+left-click** jumps the caret to the parent element's opening-tag start. Jump = move caret + scroll into view, no selection.

**Architecture:** Two pure Qt-free resolvers in `xml_structure.py` (`matching_tag_target`, `parent_tag_target`) reuse the same span primitives as the matching-tag highlight, plus a promoted-public `closing_tag_start`. A thin `XmlEditor.mousePressEvent` override maps the click, reuses the cached `_spans`, calls a resolver, and moves the caret; `mouseReleaseEvent` gains a one-shot guard so the release can't drag the caret back. No new editor state beyond one bool flag.

**Tech Stack:** Python 3.13, PySide6 (Qt6). Tests: pytest + pytest-qt, offscreen. Spec: `docs/superpowers/specs/2026-07-19-pgtp-editor-click-tag-navigation-design.md`. Unchanged: `Ctrl+Shift+B` / `Ctrl+Shift+A`.

---

### Task 1: Pure resolvers in `xml_structure.py`

**Files:**
- Modify: `pgtp_editor/ui/xml_structure.py`
- Modify: `pgtp_editor/ui/xml_editor.py` (make `_closing_tag_start` delegate — DRY, no behavior change)
- Test: `tests/ui/test_xml_structure.py`

Facts (verified): `TagSpan` fields are `name, open_start, open_end, close_end, depth, self_closing` — there is **no** `close_start` field; the closing tag's start is computed by `_closing_tag_start(text, span)` (currently in `xml_editor.py:301`). `enclosing_tag_span_from_spans(spans, position)` and `parent_tag_span(spans, span)` already exist in `xml_structure.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_xml_structure.py` (import the three new names at the top of the file's existing `from pgtp_editor.ui.xml_structure import ...` — or add an import line):

```python
from pgtp_editor.ui.xml_structure import (
    closing_tag_start,
    matching_tag_target,
    parent_tag_target,
    scan,
)


_DOC = "<root>\n  <page>\n    <col/>\n  </page>\n</root>\n"


def test_closing_tag_start_finds_close_token():
    spans = scan(_DOC)
    page = next(s for s in spans if s.name == "page")
    assert closing_tag_start(_DOC, page) == _DOC.index("</page>")


def test_closing_tag_start_none_for_self_closing():
    spans = scan(_DOC)
    col = next(s for s in spans if s.name == "col")
    assert closing_tag_start(_DOC, col) is None


def test_matching_tag_target_open_to_close():
    spans = scan(_DOC)
    pos = _DOC.index("<page>") + 2  # inside the opening <page> tag
    assert matching_tag_target(spans, _DOC, pos) == _DOC.index("</page>")


def test_matching_tag_target_close_to_open():
    spans = scan(_DOC)
    pos = _DOC.index("</page>") + 2  # inside the closing </page> tag
    assert matching_tag_target(spans, _DOC, pos) == _DOC.index("<page>")


def test_matching_tag_target_self_closing_is_none():
    spans = scan(_DOC)
    pos = _DOC.index("<col/>") + 2
    assert matching_tag_target(spans, _DOC, pos) is None


def test_matching_tag_target_in_text_content_is_none():
    # position on the whitespace/text between <page> and <col/>, not on a tag
    spans = scan(_DOC)
    pos = _DOC.index("<page>") + len("<page>")  # just past '>' , in content
    assert matching_tag_target(spans, _DOC, pos) is None


def test_matching_tag_target_nested_resolves_own_partner():
    doc = "<a><b>x</b></a>"
    spans = scan(doc)
    pos = doc.index("<b>") + 1
    assert matching_tag_target(spans, doc, pos) == doc.index("</b>")


def test_parent_tag_target_nested_returns_parent_open_start():
    spans = scan(_DOC)
    pos = _DOC.index("<col/>") + 2      # enclosing = col, parent = page
    assert parent_tag_target(spans, pos) == _DOC.index("<page>")


def test_parent_tag_target_top_level_is_none():
    spans = scan(_DOC)
    pos = _DOC.index("<root>") + 2      # enclosing = root (top-level)
    assert parent_tag_target(spans, pos) is None


def test_parent_tag_target_outside_any_element_is_none():
    spans = scan(_DOC)
    assert parent_tag_target(spans, len(_DOC)) is None  # trailing newline, outside root
```

Note on `test_parent_tag_target_outside_any_element_is_none`: the final `\n` is at an offset `>= root.open_start`, and `root` is unclosed-safe only if `close_end` is set — here root IS closed, so `enclosing_tag_span_from_spans` returns None for a position `>= root.close_end`. `len(_DOC)` is past `</root>`'s `>` plus the trailing `\n`, so it is outside root. If this proves not outside (offset lands within root.close_end), change the probe to a position guaranteed outside, e.g. `_DOC.index("\n</root>")+1`... simplest: assert on a doc with trailing content — keep the doc as-is and if the assertion is wrong, the implementer picks an offset strictly `>= root.close_end` and documents it. (The resolver logic is what's under test, not this exact offset.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_xml_structure.py -k "matching_tag_target or parent_tag_target or closing_tag_start" -q`
Expected: FAIL — `ImportError` for the three new names.

- [ ] **Step 3: Implement in `xml_structure.py`**

Add near the other span helpers (after `parent_tag_span`):

```python
def closing_tag_start(text: str, span: TagSpan) -> int | None:
    """Character offset where `span`'s own '</name>' token begins, or None if
    the span is self-closing or has no close_end. rfind over
    [open_end, close_end) is exact: the close tag is the last '</name>' before
    close_end, and the open tag's own '<' is a strictly earlier position."""
    if span.close_end is None or span.self_closing:
        return None
    start = text.rfind("</" + span.name, span.open_end, span.close_end)
    return start if start != -1 else None


def matching_tag_target(
    spans: list[TagSpan], text: str, position: int
) -> int | None:
    """Offset of the tag matching the one at `position`, or None.

    Resolve the enclosing element. If `position` is within its opening-tag
    region (open_start <= position < open_end) return the closing tag's start;
    if within its closing-tag region (close_start <= position < close_end)
    return open_start. None when self-closing, no close tag, or `position` is
    not on either tag region (text content, attribute value, outside all)."""
    span = enclosing_tag_span_from_spans(spans, position)
    if span is None or span.self_closing:
        return None
    if span.open_start <= position < span.open_end:
        return closing_tag_start(text, span)
    close_start = closing_tag_start(text, span)
    if (
        close_start is not None
        and span.close_end is not None
        and close_start <= position < span.close_end
    ):
        return span.open_start
    return None


def parent_tag_target(spans: list[TagSpan], position: int) -> int | None:
    """open_start of the parent of the element enclosing `position`, or None
    when there is no enclosing element or it is top-level (no parent)."""
    enclosing = enclosing_tag_span_from_spans(spans, position)
    if enclosing is None:
        return None
    parent = parent_tag_span(spans, enclosing)
    return None if parent is None else parent.open_start
```

Then DRY the editor copy: in `pgtp_editor/ui/xml_editor.py`, replace the body of the module-level `_closing_tag_start` (line ~301) with a delegation, keeping the name so its existing call site in `_update_matching_tag_highlight` is untouched:

```python
def _closing_tag_start(text: str, span: xml_structure.TagSpan) -> int | None:
    """Delegates to xml_structure.closing_tag_start (kept as a module-local
    name for the highlight call site)."""
    return xml_structure.closing_tag_start(text, span)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_xml_structure.py -q`
Expected: PASS (all, including the pre-existing structure tests).

- [ ] **Step 5: Run the highlight regression + full editor tests**

Run: `python -m pytest tests/ui/test_xml_editor.py tests/ui/test_xml_editor_nav_perf.py -q`
Expected: PASS — proves the `_closing_tag_start` delegation didn't disturb the matching-tag highlight.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/xml_structure.py pgtp_editor/ui/xml_editor.py tests/ui/test_xml_structure.py
git commit -m "feat: pure matching-tag / parent-tag target resolvers in xml_structure"
```

---

### Task 2: `mousePressEvent` / `mouseReleaseEvent` in `XmlEditor`

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor_click_nav.py` (create)

Facts (verified): `mouseReleaseEvent` (line ~1441) calls `super()` then emits `line_clicked` for left clicks. The span cache is `self._spans` / `self._spans_text` / `self._spans_revision`, initialized in `__init__` around line 610 and refreshed by `_rescan_structure` (line ~708). `line_clicked = Signal(int)` (1-based line). `keyPressEvent` uses exact-equality modifier checks (`mods == ctrl`).

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_xml_editor_click_nav.py`:

```python
"""Ctrl+click (matching tag) / Alt+click (parent tag) navigation."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from pgtp_editor.ui.xml_editor import XmlEditor

_DOC = "<root>\n  <page>\n    <col/>\n  </page>\n</root>\n"


def _editor(qtbot, text=_DOC):
    ed = XmlEditor()
    qtbot.addWidget(ed)
    ed.resize(600, 400)
    ed.setPlainText(text)
    return ed


def _click_at_offset(ed, offset, modifier):
    """Click the pixel at `offset`'s cursor rect with `modifier` held."""
    cur = ed.textCursor()
    cur.setPosition(offset)
    pos = ed.cursorRect(cur).center()
    QTest.mouseClick(ed.viewport(), Qt.MouseButton.LeftButton, modifier, pos)


def test_ctrl_click_open_jumps_to_close(qtbot):
    ed = _editor(qtbot)
    _click_at_offset(ed, _DOC.index("<page>") + 2, Qt.KeyboardModifier.ControlModifier)
    assert ed.textCursor().position() == _DOC.index("</page>")
    assert not ed.textCursor().hasSelection()


def test_ctrl_click_close_jumps_to_open(qtbot):
    ed = _editor(qtbot)
    _click_at_offset(ed, _DOC.index("</page>") + 2, Qt.KeyboardModifier.ControlModifier)
    assert ed.textCursor().position() == _DOC.index("<page>")


def test_alt_click_jumps_to_parent_start_no_selection(qtbot):
    ed = _editor(qtbot)
    _click_at_offset(ed, _DOC.index("<col/>") + 2, Qt.KeyboardModifier.AltModifier)
    assert ed.textCursor().position() == _DOC.index("<page>")
    # Alt+click must NOT start a column selection.
    assert not ed.textCursor().hasSelection()


def test_ctrl_click_in_text_content_is_noop_falls_through(qtbot):
    ed = _editor(qtbot)
    # click just past <page>'s '>' (in content, not on a tag) with Ctrl
    offset = _DOC.index("<page>") + len("<page>")
    _click_at_offset(ed, offset, Qt.KeyboardModifier.ControlModifier)
    # No jump: caret is where a normal click landed, near the clicked offset,
    # NOT at a tag boundary. Assert it did not jump to an open/close start.
    assert ed.textCursor().position() not in (
        _DOC.index("<page>"), _DOC.index("</page>"),
    )


def test_plain_click_still_emits_line_clicked(qtbot):
    ed = _editor(qtbot)
    seen = []
    ed.line_clicked.connect(seen.append)
    _click_at_offset(ed, _DOC.index("<col/>") + 2, Qt.KeyboardModifier.NoModifier)
    assert seen and seen[-1] == ed.textCursor().blockNumber() + 1
    assert not ed.textCursor().hasSelection()


def test_ctrl_click_jump_emits_line_clicked_for_target(qtbot):
    ed = _editor(qtbot)
    with qtbot.waitSignal(ed.line_clicked, timeout=500) as sig:
        _click_at_offset(ed, _DOC.index("<page>") + 2, Qt.KeyboardModifier.ControlModifier)
    # target </page> is on its own line
    target_line = _DOC[: _DOC.index("</page>")].count("\n") + 1
    assert sig.args == [target_line]


def test_ctrl_click_caret_stays_after_release(qtbot):
    """Regression: the release must not drag the caret back to the click point."""
    ed = _editor(qtbot)
    _click_at_offset(ed, _DOC.index("<page>") + 2, Qt.KeyboardModifier.ControlModifier)
    assert ed.textCursor().position() == _DOC.index("</page>")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_xml_editor_click_nav.py -q`
Expected: FAIL — jumps don't happen (no `mousePressEvent` override), Alt may column-select.

- [ ] **Step 3: Implement in `xml_editor.py`**

(a) In `__init__`, next to `self._spans` (line ~610), add:

```python
        self._nav_click_handled = False
```

(b) Add the `mousePressEvent` override (place just above `mouseReleaseEvent`):

```python
    def mousePressEvent(self, event) -> None:
        # Ctrl+left-click jumps to the matching open/close tag; Alt+left-click
        # jumps to the parent element's opening tag. Handled at PRESS (not
        # release) so accepting the event suppresses Qt's Alt+drag column
        # selection and leaves no stray selection at the destination.
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl = Qt.KeyboardModifier.ControlModifier
            alt = Qt.KeyboardModifier.AltModifier
            mods = event.modifiers()
            if mods == ctrl or mods == alt:
                click_pos = self.cursorForPosition(
                    event.position().toPoint()
                ).position()
                if self.document().revision() != self._spans_revision:
                    self._rescan_structure()
                if mods == ctrl:
                    target = xml_structure.matching_tag_target(
                        self._spans, self._spans_text, click_pos
                    )
                else:
                    target = xml_structure.parent_tag_target(
                        self._spans, click_pos
                    )
                if target is not None:
                    cursor = self.textCursor()
                    cursor.setPosition(target)
                    self.setTextCursor(cursor)
                    self.ensureCursorVisible()
                    self._nav_click_handled = True
                    self.line_clicked.emit(cursor.blockNumber() + 1)
                    event.accept()
                    return
        super().mousePressEvent(event)
```

(c) Update `mouseReleaseEvent` to honor the one-shot flag (add the guard at the top; keep the rest verbatim):

```python
    def mouseReleaseEvent(self, event) -> None:
        # A modifier-jump handled the matching press; consume the release too so
        # Qt's default release handling doesn't reposition the caret back to the
        # click point (which would undo the jump and misreport line_clicked).
        if self._nav_click_handled:
            self._nav_click_handled = False
            event.accept()
            return
        # Let Qt place the text cursor at the clicked position first, then
        # read the resulting 1-based line and notify listeners. ...
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            line = self.textCursor().blockNumber() + 1  # 0-based -> 1-based
            self.line_clicked.emit(line)
```

(`event.position()` is viewport-local for `QMouseEvent` delivered to this handler, which is the coordinate space `cursorForPosition` expects. `xml_structure` is already imported in this module.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_xml_editor_click_nav.py -q`
Expected: PASS (7 passed). If a click-position test is flaky because `cursorRect().center()` maps a pixel to an adjacent offset, widen the click target by using `+2` into the tag (already done) or assert the caret is within the partner span rather than an exact equality — but the exact-equality assertions should hold because the resolver returns a fixed offset regardless of small pixel rounding, as long as the pixel lands anywhere in the tag region.

- [ ] **Step 5: Editor regression + full suite**

Run: `python -m pytest tests/ui/test_xml_editor.py tests/ui/test_xml_editor_click_nav.py tests/ui/test_xml_structure.py -q`
Then: `python -m pytest -q`
Expected: prior total + the new tests, 0 failures. In particular `test_mouse_release_emits_one_based_line_from_cursor` and `test_right_click_does_not_emit_line_clicked` still pass (release guard doesn't touch ordinary clicks).

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor_click_nav.py
git commit -m "feat: Ctrl+click matching-tag / Alt+click parent-tag caret navigation"
```

---

### Task 3: Manual note + feature-tester gate

**Files:**
- Modify: `pgtp_editor/resources/manual.md`

- [ ] **Step 1: Document the mouse shortcuts**

In `pgtp_editor/resources/manual.md`, add a bullet to *The Raw XML Editor* section:

```markdown
- **Ctrl+click** a tag to jump to its matching open/close tag; **Alt+click** to
  jump to the parent element's opening tag. (The caret moves and scrolls into
  view; nothing is selected.)
```

And add two rows to the *Keyboard Shortcuts* table (they are mouse shortcuts, noted in the Where column):

```markdown
| **Ctrl+click** | Raw XML (mouse) | Jump to matching open/close tag |
| **Alt+click** | Raw XML (mouse) | Jump to parent tag start |
```

Run the manual tests: `python -m pytest tests/ui/test_manual_resource.py tests/ui/test_manual_panel.py -q` — expected PASS (structure-agnostic).

- [ ] **Step 2: Dispatch the feature-tester agent (testing policy)**

Per CLAUDE.md, run the `feature-tester` agent: feature "Ctrl+click / Alt+click tag navigation", spec `docs/superpowers/specs/2026-07-19-pgtp-editor-click-tag-navigation-design.md`, this plan, changed files (`pgtp_editor/ui/xml_structure.py`, `pgtp_editor/ui/xml_editor.py`, `pgtp_editor/resources/manual.md`, the two new test files). It appends a green run to `docs/TEST_LOG.md`; commit that with the feature.

- [ ] **Step 3: Final commit**

```bash
git add pgtp_editor/resources/manual.md docs/TEST_LOG.md
git commit -m "docs: manual note for Ctrl/Alt+click tag navigation; test log entry"
```

---

## Verification (whole plan)

`python -m pytest -q` — baseline plus ~17 new tests (10 pure + 7 widget), 0 failures. Manual smoke: open a real `.pgtp`, Ctrl+click an opening tag (caret jumps to its `</…>`), Ctrl+click the close tag (jumps back), Alt+click inside a nested element (caret lands on the parent's `<…>`), and confirm Alt+click leaves no column selection. Then two-stage review and `--no-ff` merge, then merge `main` into `re-phpgen`.

## Self-review notes

- **Spec coverage:** Ctrl matching-tag → `matching_tag_target` (Task 1) + press handler (Task 2); Alt parent → `parent_tag_target` (Task 1) + handler (Task 2); jump = caret + `ensureCursorVisible`, no selection (Task 2); press consumed for Alt column-select suppression + release guard against caret-drag-back (Task 2, with a dedicated regression test); tree-sync via `line_clicked` (Task 2); cached-span reuse with revision guard (Task 2); docs (Task 3); delivery/testing policy (Task 3 + Verification).
- **Type consistency:** `matching_tag_target(spans, text, position) -> int | None`, `parent_tag_target(spans, position) -> int | None`, `closing_tag_start(text, span) -> int | None` — used identically in resolvers, handler, and tests. `line_clicked` stays `Signal(int)` 1-based.
- **Judgment point for the executor:** the one flagged offset in `test_parent_tag_target_outside_any_element_is_none` — pick an offset strictly outside `root` if `len(_DOC)` doesn't qualify; the resolver behavior is what matters.
