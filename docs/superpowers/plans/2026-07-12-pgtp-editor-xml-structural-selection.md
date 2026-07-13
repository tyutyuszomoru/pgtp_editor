# XML Structural Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add keyboard-driven structural selection to `XmlEditor` — `Ctrl+Shift+B` (select the block the cursor is in), `Ctrl+Shift+A` (select the parent block, stateless), and matching open/close-tag highlighting — with the load-bearing guarantee that copying/cutting a *folded* block yields its full underlying text, not the visually-collapsed placeholder.

**Architecture:** Two new pure-Python query functions in `pgtp_editor/ui/xml_structure.py` (`enclosing_tag_span`, `parent_tag_span`) built on the existing `scan()`/`TagSpan` output with no change to `scan()`. On `XmlEditor`, a behavior-preserving refactor first funnels all extra-selection sources through one shared `_refresh_extra_selections()` combiner; then matching-tag highlighting, `select_enclosing_block`, `select_parent_block`, and `QShortcut` wiring are added on top. All selection is built purely from `TagSpan` character offsets (`QTextCursor.setPosition`), which addresses the document's real character stream and is therefore immune to folding's `QTextBlock.setVisible(False)` hiding.

**Tech Stack:** Python 3, PySide6 (`QTextCursor`, `QTextEdit.ExtraSelection`, `QShortcut`, `QKeySequence`, `QApplication.clipboard`), `pytest` + `pytest-qt`.

---

## Before you start

- Work in this worktree: `C:\Users\BotondZalai-RuzsicsP\docs\Software development\pgtp_editor\.claude\worktrees\pgtp-editor-structural-impl`, branch `worktree-pgtp-editor-structural-impl` (already checked out).
- Run tests with `python -m pytest <path> -v` from the worktree root.
- Commit after every task (not every step) unless a step says otherwise — each task's final step is "commit."
- The authoritative design document is `docs/superpowers/specs/2026-07-12-pgtp-editor-xml-structural-selection-design.md` — consult it if a step references "per the spec."
- **Grounding facts about the real shipped foundation code (verified against `pgtp_editor/ui/xml_structure.py`, `pgtp_editor/ui/xml_editor.py`, and their tests on this branch):**
  - `TagSpan` fields are exactly: `name`, `open_start`, `open_end`, `close_end` (`int | None`), `depth`, `self_closing`. There is **no** stored close-tag start offset — Task 4 derives it locally.
  - `scan(text) -> list[TagSpan]` exists; `find_enclosing_open_tag(text, position) -> str | None` and `nesting_depth_at(text, position) -> int` exist. Do not modify any of these.
  - `XmlEditor.__init__` connects `self.cursorPositionChanged.connect(self._highlight_current_line)`. `_highlight_current_line` (real code, ~line 272) builds one `QTextEdit.ExtraSelection` and calls `self.setExtraSelections([selection])` **directly**.
  - `_scroll_and_highlight_whole_line` (~291, used by `highlight_error_line` and `navigate_to_line`) and `select_range_on_line` (~309) **also** call `self.setExtraSelections([selection])` directly. Task 2 reroutes all four call sites through one combiner **without changing their observable behavior** — the existing tests in `tests/ui/test_xml_editor.py` (listed below) lock that behavior and must stay green.
  - Folding is `_toggle_fold(block)` where `block` is a `QTextBlock` (obtained via `self.document().findBlockByNumber(n)` or `findBlock(pos)`); it calls `contained_block.setVisible(False/True)`. It never deletes text.
  - Existing `keyPressEvent` handles Enter/`<`/quote/`>` and does **not** use any `QShortcut`. Task 6 adds `QShortcut`s in `__init__`, leaving `keyPressEvent` untouched.
- **Existing `XmlEditor` tests that MUST remain green after Task 2's refactor** (from `tests/ui/test_xml_editor.py`): `test_current_line_highlight_is_single_extra_selection`, `test_current_line_highlight_moves_with_cursor`, `test_highlight_error_line_scrolls_and_highlights`, `test_highlight_error_line_overrides_current_line_highlight`, `test_navigate_to_line_scrolls_and_highlights_with_navigation_color`, `test_select_range_on_line_selects_exact_substring`. Each asserts `len(editor.extraSelections()) == 1` in its scenario. Task 2 preserves exactly that.
- **U+2029 note (a spec correction):** `QTextCursor.selectedText()` and `QApplication.clipboard().text()` differ in newline representation. `selectedText()` replaces line breaks with U+2029 (PARAGRAPH SEPARATOR, `" "`); the system clipboard text uses ordinary `"\n"`. The spec's §7.4 sketch wrote `.replace(" ", "\n")` (replacing a *space*) — that is a typo in the sketch. This plan uses `.replace(" ", "\n")` for `selectedText()` and **no** replacement for clipboard text. This is called out as a judgment call in the final report.

---

## Part 1 — `xml_structure.py` query functions (no Qt dependency)

### Task 1: `enclosing_tag_span` and `parent_tag_span`

**Files:**
- Modify: `pgtp_editor/ui/xml_structure.py` (append two functions after `nesting_depth_at`)
- Test: `tests/ui/test_xml_structure.py` (append)

- [ ] **Step 1: Write the failing tests for `enclosing_tag_span`**

Append to `tests/ui/test_xml_structure.py`:

```python
from pgtp_editor.ui.xml_structure import enclosing_tag_span, parent_tag_span


def test_enclosing_tag_span_inside_text_content_returns_innermost():
    text = "<Page><Detail>text</Detail></Page>"
    span = enclosing_tag_span(text, text.index("text"))
    assert span is not None
    assert span.name == "Detail"
    assert span.depth == 1


def test_enclosing_tag_span_inside_open_tag_delimiters_returns_that_span():
    text = "<Page><Detail>text</Detail></Page>"
    # Position between '<' and '>' of the <Detail> open tag.
    position = text.index("<Detail>") + 1
    span = enclosing_tag_span(text, position)
    assert span is not None
    assert span.name == "Detail"


def test_enclosing_tag_span_at_open_start_boundary_is_included():
    text = "<Page><Detail>text</Detail></Page>"
    position = text.index("<Detail>")  # exactly at Detail's open_start
    span = enclosing_tag_span(text, position)
    assert span is not None
    assert span.name == "Detail"


def test_enclosing_tag_span_in_intersibling_whitespace_returns_parent():
    text = "<Page>\n  <Detail></Detail>\n  <Detail></Detail>\n</Page>"
    # Position on the blank spot between the two </Detail> and <Detail>.
    first_close_end = text.index("</Detail>") + len("</Detail>")
    span = enclosing_tag_span(text, first_close_end + 1)  # in the "\n  " gap
    assert span is not None
    assert span.name == "Page"
    assert span.depth == 0


def test_enclosing_tag_span_outside_every_element_returns_none():
    text = "  <Page></Page>  "
    assert enclosing_tag_span(text, 0) is None  # leading whitespace
    assert enclosing_tag_span(text, len(text)) is None  # trailing whitespace


def test_enclosing_tag_span_self_closing_returns_that_span():
    text = "<Page><Column/></Page>"
    position = text.index("<Column/>") + 2  # inside the self-closing token
    span = enclosing_tag_span(text, position)
    assert span is not None
    assert span.name == "Column"
    assert span.self_closing is True
    assert text[span.open_start:span.close_end] == "<Column/>"


def test_enclosing_tag_span_repeated_sibling_names_returns_correct_instance():
    text = "<Root><Item>A</Item><Item>B</Item></Root>"
    span = enclosing_tag_span(text, text.index("B"))
    assert span is not None
    assert span.name == "Item"
    # The correct instance is the SECOND <Item>, identified by open_start.
    assert span.open_start == text.rindex("<Item>")


def test_enclosing_tag_span_tolerates_unclosed_tag():
    text = "<Page><Detail>"
    span = enclosing_tag_span(text, len(text))
    assert span is not None
    assert span.name == "Detail"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/ui/test_xml_structure.py -v -k enclosing_tag_span`
Expected: FAIL with `ImportError: cannot import name 'enclosing_tag_span'`

- [ ] **Step 3: Implement `enclosing_tag_span`**

Append to `pgtp_editor/ui/xml_structure.py` (after `nesting_depth_at`):

```python
def enclosing_tag_span(text: str, position: int) -> TagSpan | None:
    """Return the innermost TagSpan that structurally contains `position`
    -- the block Ctrl+Shift+B would select if the cursor were at `position`.

    A span is a candidate if `position` falls within its full extent:
      * `[open_start, close_end)` for a span with a known close_end
        (this includes self-closing spans, whose close_end == open_end,
        and covers the open-tag delimiters, the content, and the close tag);
      * `[open_start, len(text))` for a span never closed (close_end is None),
        since its true extent is unknown and it is still the best available
        "what am I inside of" answer.
    Among all candidates the one with the greatest `depth` (innermost) wins.
    Returns None when `position` is outside every element.
    """
    best: TagSpan | None = None
    for span in scan(text):
        if span.close_end is not None:
            contains = span.open_start <= position < span.close_end
        else:
            contains = span.open_start <= position < len(text) or position == span.open_start
        if contains and (best is None or span.depth > best.depth):
            best = span
    return best
```

- [ ] **Step 4: Run to verify `enclosing_tag_span` tests pass**

Run: `python -m pytest tests/ui/test_xml_structure.py -v -k enclosing_tag_span`
Expected: PASS (8 tests)

- [ ] **Step 5: Write the failing tests for `parent_tag_span`**

Append to `tests/ui/test_xml_structure.py`:

```python
def test_parent_tag_span_of_leaf_returns_immediate_parent():
    text = "<Page><Detail><Column/></Detail></Page>"
    spans = scan(text)
    column = next(s for s in spans if s.name == "Column")
    parent = parent_tag_span(spans, column)
    assert parent is not None
    assert parent.name == "Detail"
    assert parent.depth == 1


def test_parent_tag_span_of_mid_level_returns_one_up():
    text = "<Page><Detail><Column/></Detail></Page>"
    spans = scan(text)
    detail = next(s for s in spans if s.name == "Detail")
    parent = parent_tag_span(spans, detail)
    assert parent is not None
    assert parent.name == "Page"
    assert parent.depth == 0


def test_parent_tag_span_of_top_level_returns_none():
    text = "<Page><Detail></Detail></Page>"
    spans = scan(text)
    page = next(s for s in spans if s.name == "Page")
    assert parent_tag_span(spans, page) is None


def test_parent_tag_span_repeated_sibling_names_finds_correct_single_parent():
    text = "<Root><Group><Item>A</Item></Group><Group><Item>B</Item></Group></Root>"
    spans = scan(text)
    # The <Item> containing "B" -- identified by open_start, not name.
    item_b = next(
        s for s in spans if s.name == "Item" and s.open_start == text.rindex("<Item>")
    )
    parent = parent_tag_span(spans, item_b)
    assert parent is not None
    assert parent.name == "Group"
    # It must be the SECOND Group (the one that actually contains item_b),
    # not the first Group with the same name.
    assert parent.open_start == text.rindex("<Group>")
```

- [ ] **Step 6: Run to verify they fail**

Run: `python -m pytest tests/ui/test_xml_structure.py -v -k parent_tag_span`
Expected: FAIL with `ImportError: cannot import name 'parent_tag_span'`

- [ ] **Step 7: Implement `parent_tag_span`**

Append to `pgtp_editor/ui/xml_structure.py` (after `enclosing_tag_span`):

```python
def parent_tag_span(spans: list[TagSpan], span: TagSpan) -> TagSpan | None:
    """Return the TagSpan exactly one nesting level up from `span` -- the
    block Ctrl+Shift+A selects, given the TagSpan Ctrl+Shift+B would select.

    The parent is the span at depth == span.depth - 1 whose extent
    structurally contains `span`'s extent. Returns None when span.depth == 0
    (a top-level element has no parent). Operates over the caller's already
    computed `scan()` result to avoid a redundant re-scan. The containment
    check is defensive against malformed input (mismatched tags can leave
    spans with close_end=None at unexpected depths); for well-formed XML the
    depth==span.depth-1 candidate is already unique.
    """
    if span.depth == 0:
        return None
    span_end = span.close_end if span.close_end is not None else span.open_end
    for candidate in spans:
        if candidate.depth != span.depth - 1:
            continue
        if candidate.open_start <= span.open_start and (
            candidate.close_end is None or candidate.close_end >= span_end
        ):
            return candidate
    return None
```

- [ ] **Step 8: Run the full `xml_structure` suite (new + pre-existing)**

Run: `python -m pytest tests/ui/test_xml_structure.py -v`
Expected: PASS — all new tests plus every pre-existing `scan`/`find_enclosing_open_tag`/`nesting_depth_at` test still green.

- [ ] **Step 9: Commit**

```bash
git add pgtp_editor/ui/xml_structure.py tests/ui/test_xml_structure.py
git commit -m "feat(xml_structure): add enclosing_tag_span and parent_tag_span queries"
```

---

## Part 2 — `XmlEditor` extra-selections refactor (behavior-preserving)

### Task 2: Route all extra-selections through a shared `_refresh_extra_selections`

This is a pure refactor. It introduces three named contribution attributes and one combiner, then rewrites the four existing `setExtraSelections([...])` call sites to update their own contribution and call the combiner. **No observable behavior changes** — the six existing tests listed in "Before you start" must stay green.

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py` (`__init__`, `_highlight_current_line`, `_scroll_and_highlight_whole_line`, `select_range_on_line`)
- Test: `tests/ui/test_xml_editor.py` (append two guard tests)

- [ ] **Step 1: Write guard tests that lock the combiner's existence and neutrality**

Append to `tests/ui/test_xml_editor.py`:

```python
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
    assert editor._error_line_selection is None


def test_refresh_extra_selections_current_line_uses_named_list(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    assert len(editor._current_line_selections) == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/ui/test_xml_editor.py -v -k refresh_extra_selections`
Expected: FAIL with `AttributeError: 'XmlEditor' object has no attribute '_matching_tag_selections'`

- [ ] **Step 3: Add the named contribution attributes in `__init__`**

In `pgtp_editor/ui/xml_editor.py`, inside `XmlEditor.__init__`, add these three attributes immediately after `self._navigation_highlight_color = QColor("#264f78")` (before the `self.setLineWrapMode(...)` line):

```python
        self._matching_tag_color = QColor("#3a5f3a")
        self._current_line_selections: list[QTextEdit.ExtraSelection] = []
        self._matching_tag_selections: list[QTextEdit.ExtraSelection] = []
        self._error_line_selection: QTextEdit.ExtraSelection | None = None
```

- [ ] **Step 4: Add the combiner method**

Add this method to `XmlEditor` (place it directly above `_highlight_current_line`):

```python
    def _refresh_extra_selections(self) -> None:
        """The single place XmlEditor calls setExtraSelections. Combines
        every named selection source in a fixed layering order (current-line
        band underneath, matching-tag spans above it, one-shot navigation/
        error line on top) and pushes the combined list to Qt in one call.
        Individual features update their own named attribute and call this;
        they never call setExtraSelections directly."""
        selections: list[QTextEdit.ExtraSelection] = []
        selections.extend(self._current_line_selections)
        selections.extend(self._matching_tag_selections)
        if self._error_line_selection is not None:
            selections.append(self._error_line_selection)
        self.setExtraSelections(selections)
```

- [ ] **Step 5: Rewrite `_highlight_current_line` to use the combiner**

Replace the body of `_highlight_current_line` with:

```python
    def _highlight_current_line(self) -> None:
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(self._current_line_color)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self._current_line_selections = [selection]
        self._refresh_extra_selections()
```

- [ ] **Step 6: Rewrite `_scroll_and_highlight_whole_line` to use the combiner**

The existing method ends by building a full-width selection and calling `self.setExtraSelections([selection])`. It is used by both `highlight_error_line` (error color) and `navigate_to_line` (navigation color), and the existing tests assert exactly ONE selection results, overriding the current-line highlight. Preserve that by clearing the other contributions and routing the single selection through the combiner. Replace the method with:

```python
    def _scroll_and_highlight_whole_line(self, line: int, color: QColor) -> None:
        block = self.document().findBlockByNumber(max(0, line - 1))  # 1-based -> 0-based
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()

        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(color)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = cursor
        selection.cursor.clearSelection()
        # This whole-line indicator is a one-shot that intentionally overrides
        # both the current-line band and any matching-tag highlight, matching
        # the pre-refactor behavior (setTextCursor above fires the current-line
        # slot first; we then clear it so only this indicator remains).
        self._current_line_selections = []
        self._matching_tag_selections = []
        self._error_line_selection = selection
        self._refresh_extra_selections()
```

> Rationale for keeping this override: `test_highlight_error_line_overrides_current_line_highlight` and the single-selection assertions in `test_highlight_error_line_scrolls_and_highlights` / `test_navigate_to_line_scrolls_and_highlights_with_navigation_color` require exactly one selection here. Storing it as `_error_line_selection` and clearing the others reproduces the pre-refactor "replaces the whole list" semantics for this path exactly.

- [ ] **Step 7: Rewrite `select_range_on_line` to use the combiner**

The existing method builds a (non-full-width) navigation-colored selection with a real anchor..position range and calls `setExtraSelections([selection])`; `test_select_range_on_line_selects_exact_substring` asserts exactly one selection whose `cursor.selectedText()` equals the substring. Reproduce via the same one-shot `_error_line_selection` slot (it is the generic "single overriding indicator" slot):

```python
    def select_range_on_line(self, line: int, start: int, end: int) -> None:
        """Select and highlight the character range [start, end) within
        `line` (1-based) -- the column-precise refinement the Properties
        panel uses after `navigate_to_line` has already scrolled there."""
        block = self.document().findBlockByNumber(max(0, line - 1))
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + start)
        cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.centerCursor()

        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(self._navigation_highlight_color)
        selection.cursor = cursor
        self._current_line_selections = []
        self._matching_tag_selections = []
        self._error_line_selection = selection
        self._refresh_extra_selections()
```

- [ ] **Step 8: Run the FULL `XmlEditor` suite — the pre-existing tests must still pass**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS — including `test_current_line_highlight_is_single_extra_selection`, `test_current_line_highlight_moves_with_cursor`, `test_highlight_error_line_scrolls_and_highlights`, `test_highlight_error_line_overrides_current_line_highlight`, `test_navigate_to_line_scrolls_and_highlights_with_navigation_color`, `test_select_range_on_line_selects_exact_substring`, and the two new guard tests.

- [ ] **Step 9: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "refactor(xml_editor): route all extra-selections through shared _refresh_extra_selections"
```

---

## Part 3 — Matching-tag highlighting

### Task 3: `_closing_tag_start` helper + `_update_matching_tag_highlight` and `_make_span_cursor`

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py` (module-level helper `_closing_tag_start`; `XmlEditor` methods `_make_span_cursor`, `_update_matching_tag_highlight`; connect in `__init__`)
- Test: `tests/ui/test_xml_editor.py` (append)

- [ ] **Step 1: Write failing tests for matching-tag highlighting**

Append to `tests/ui/test_xml_editor.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/ui/test_xml_editor.py -v -k matching_tag`
Expected: FAIL — matching-tag color never appears (no highlighter yet), so counts are 0 where 2 is expected.

- [ ] **Step 3: Add the module-level `_closing_tag_start` helper**

In `pgtp_editor/ui/xml_editor.py`, add this near the other module-level helpers (e.g. after `_cursor_immediately_after_open_tag`). Import `TagSpan` for the annotation by adding it to the existing `from pgtp_editor.ui import xml_structure` usage — reference it as `xml_structure.TagSpan` to avoid a second import line:

```python
def _closing_tag_start(text: str, span: xml_structure.TagSpan) -> int | None:
    """Given a TagSpan with a known close_end, find where its own '</name>'
    token begins. Returns None if the span is self-closing or has no
    close_end. rfind over [open_end, close_end) is exact: the close tag's
    '</name>' is the last such occurrence before close_end, and the open
    tag's own '<' is a strictly earlier, distinct position."""
    if span.close_end is None or span.self_closing:
        return None
    close_tag_prefix = "</" + span.name
    start = text.rfind(close_tag_prefix, span.open_end, span.close_end)
    return start if start != -1 else None
```

- [ ] **Step 4: Add `_make_span_cursor` and `_update_matching_tag_highlight` to `XmlEditor`**

Add both methods to `XmlEditor` (place them directly below `_refresh_extra_selections`):

```python
    def _make_span_cursor(self, start: int, end: int) -> QTextCursor:
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        return cursor

    def _update_matching_tag_highlight(self) -> None:
        text = self.toPlainText()
        position = self.textCursor().position()
        span = xml_structure.enclosing_tag_span(text, position)
        self._matching_tag_selections = []
        if span is None or span.self_closing:
            self._refresh_extra_selections()
            return

        on_open_tag = span.open_start <= position < span.open_end
        close_start = _closing_tag_start(text, span)
        on_close_tag = (
            close_start is not None
            and span.close_end is not None
            and close_start <= position < span.close_end
        )
        if not (on_open_tag or on_close_tag):
            self._refresh_extra_selections()
            return

        open_selection = QTextEdit.ExtraSelection()
        open_selection.format.setBackground(self._matching_tag_color)
        open_selection.cursor = self._make_span_cursor(span.open_start, span.open_end)
        selections = [open_selection]

        if close_start is not None and span.close_end is not None:
            close_selection = QTextEdit.ExtraSelection()
            close_selection.format.setBackground(self._matching_tag_color)
            close_selection.cursor = self._make_span_cursor(close_start, span.close_end)
            selections.append(close_selection)

        self._matching_tag_selections = selections
        self._refresh_extra_selections()
```

- [ ] **Step 5: Connect `_update_matching_tag_highlight` to `cursorPositionChanged`**

In `XmlEditor.__init__`, immediately after the existing line `self.cursorPositionChanged.connect(self._highlight_current_line)`, add:

```python
        self.cursorPositionChanged.connect(self._update_matching_tag_highlight)
```

- [ ] **Step 6: Run the matching-tag tests**

Run: `python -m pytest tests/ui/test_xml_editor.py -v -k matching_tag`
Expected: PASS (6 tests)

- [ ] **Step 7: Run the full `XmlEditor` suite (regression check)**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS — all matching-tag tests plus every pre-existing test (the current-line/error/navigation/select-range tests still see exactly one selection in their scenarios, because those set the cursor into content or via `_scroll_and_highlight_whole_line`, which clears `_matching_tag_selections`).

- [ ] **Step 8: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml_editor): matching open/close-tag highlighting via shared extra-selections"
```

---

## Part 4 — `Ctrl+Shift+B`: select enclosing block (with folded-copy correctness)

### Task 4: `select_enclosing_block` and the folded-copy proof test

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py` (`XmlEditor.select_enclosing_block`)
- Test: `tests/ui/test_xml_editor.py` (append)

- [ ] **Step 1: Write failing tests for `select_enclosing_block`**

Append to `tests/ui/test_xml_editor.py`. Add this import at the top of the file if not already present (it is not, on this branch): `from PySide6.QtWidgets import QApplication` — place it beside the existing `from PySide6.QtWidgets import QPlainTextEdit` import.

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/ui/test_xml_editor.py -v -k "select_enclosing_block or copy_folded or copy_nested"`
Expected: FAIL with `AttributeError: 'XmlEditor' object has no attribute 'select_enclosing_block'`

- [ ] **Step 3: Implement `select_enclosing_block`**

Add this method to `XmlEditor` (place it below `_update_matching_tag_highlight`):

```python
    def select_enclosing_block(self) -> None:
        """Ctrl+Shift+B: select the innermost element containing the cursor,
        from its opening '<' through its closing '>'. Selection is built
        purely from TagSpan character offsets, so it captures the full
        underlying text even when intervening blocks are folded (hidden via
        setVisible(False)); QTextCursor addresses the document's character
        stream, not what is currently painted. No-op when the cursor is
        outside every element."""
        text = self.toPlainText()
        position = self.textCursor().position()
        span = xml_structure.enclosing_tag_span(text, position)
        if span is None:
            return
        end = span.close_end if span.close_end is not None else span.open_end
        cursor = self.textCursor()
        cursor.setPosition(span.open_start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
```

- [ ] **Step 4: Run the Task 4 tests**

Run: `python -m pytest tests/ui/test_xml_editor.py -v -k "select_enclosing_block or copy_folded or copy_nested"`
Expected: PASS (6 tests). In particular `test_copy_folded_block_yields_full_text` and `test_copy_nested_folds_outer_block_yields_full_text` prove both the in-editor selection AND the real `QApplication.clipboard()` content equal the full block text including the folded-away lines — the naive "copy what's visible" approach would fail these by dropping the hidden `ColumnPresentation` lines.

- [ ] **Step 5: Run the full `XmlEditor` suite (regression check)**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS — all tests.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml_editor): Ctrl+Shift+B select enclosing block, folded-copy correct"
```

---

## Part 5 — `Ctrl+Shift+A`: select parent block (stateless)

### Task 5: `select_parent_block`

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py` (`XmlEditor.select_parent_block`)
- Test: `tests/ui/test_xml_editor.py` (append)

- [ ] **Step 1: Write failing tests for `select_parent_block`**

Append to `tests/ui/test_xml_editor.py`. These import `enclosing_tag_span` / `parent_tag_span` to independently compute the expected span rather than re-deriving inline — add near the top: `from pgtp_editor.ui.xml_structure import scan as _scan, enclosing_tag_span as _enc, parent_tag_span as _par`.

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/ui/test_xml_editor.py -v -k select_parent_block`
Expected: FAIL with `AttributeError: 'XmlEditor' object has no attribute 'select_parent_block'`

- [ ] **Step 3: Implement `select_parent_block`**

Add this method to `XmlEditor` (place it below `select_enclosing_block`):

```python
    def select_parent_block(self) -> None:
        """Ctrl+Shift+A: select the block exactly one nesting level up from
        the current position. Stateless -- always re-derived from the current
        selection's START offset (never remembered state), so repeated presses
        walk up one level each time and a manually adjusted selection Just
        Works. Using selectionStart() (== the selected block's open_start
        after a prior press) rather than the cursor's moving-end position
        avoids landing exactly on close_end, which the containment rule
        (open_start <= position < end) would resolve to the FOLLOWING sibling
        instead of this block. No-op when there is no enclosing element, or
        when the enclosing element is top-level (no parent)."""
        text = self.toPlainText()
        cursor = self.textCursor()
        position = cursor.selectionStart() if cursor.hasSelection() else cursor.position()
        spans = xml_structure.scan(text)
        enclosing = xml_structure.enclosing_tag_span(text, position)
        if enclosing is None:
            return
        parent = xml_structure.parent_tag_span(spans, enclosing)
        if parent is None:
            return
        end = parent.close_end if parent.close_end is not None else parent.open_end
        new_cursor = self.textCursor()
        new_cursor.setPosition(parent.open_start)
        new_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(new_cursor)
```

- [ ] **Step 4: Run the Task 5 tests**

Run: `python -m pytest tests/ui/test_xml_editor.py -v -k select_parent_block`
Expected: PASS (4 tests). `test_select_parent_block_repeated_presses_walk_up_levels` confirms the `selectionStart()`-based re-query correctly walks up rather than skipping a level at the `close_end` boundary.

- [ ] **Step 5: Run the full `XmlEditor` suite (regression check)**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: PASS — all tests.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml_editor): Ctrl+Shift+A stateless select parent block"
```

---

## Part 6 — Keyboard shortcut wiring

### Task 6: `QShortcut` bindings for both commands

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py` (imports; `__init__`)
- Test: `tests/ui/test_xml_editor.py` (append)

- [ ] **Step 1: Write failing tests that drive the real shortcuts via qtbot**

Append to `tests/ui/test_xml_editor.py`:

```python
def test_ctrl_shift_b_shortcut_selects_enclosing_block(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.show()
    qtbot.waitExposed(editor)
    text = "<Page>\n  <Detail>\n    x\n  </Detail>\n</Page>"
    editor.setPlainText(text)
    editor.setFocus()
    cursor = editor.textCursor()
    cursor.setPosition(text.index("x"))
    editor.setTextCursor(cursor)

    qtbot.keyClick(editor, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)

    expected = text[text.index("<Detail>"):text.index("</Detail>") + len("</Detail>")]
    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected == expected


def test_ctrl_shift_a_shortcut_selects_parent_block(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.show()
    qtbot.waitExposed(editor)
    text = "<Page>\n  <Detail>\n    <Column>x</Column>\n  </Detail>\n</Page>"
    editor.setPlainText(text)
    editor.setFocus()
    cursor = editor.textCursor()
    cursor.setPosition(text.index("x"))
    editor.setTextCursor(cursor)

    qtbot.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)

    expected = text[text.index("<Detail>"):text.index("</Detail>") + len("</Detail>")]
    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected == expected
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/ui/test_xml_editor.py -v -k "ctrl_shift_b_shortcut or ctrl_shift_a_shortcut"`
Expected: FAIL — the key chord does nothing (no shortcut wired), so no selection results.

- [ ] **Step 3: Add the required imports**

In `pgtp_editor/ui/xml_editor.py`, the `PySide6.QtGui` import block currently imports `QColor, QKeyEvent, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextFormat`. Add `QKeySequence` and `QShortcut` — note `QShortcut` lives in `QtGui` in PySide6. Change that import block to:

```python
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QShortcut,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
```

- [ ] **Step 4: Wire the shortcuts in `__init__`**

In `XmlEditor.__init__`, add the following immediately after the `self.cursorPositionChanged.connect(self._update_matching_tag_highlight)` line added in Task 3:

```python
        select_block_shortcut = QShortcut(QKeySequence("Ctrl+Shift+B"), self)
        select_block_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        select_block_shortcut.activated.connect(self.select_enclosing_block)

        select_parent_shortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
        select_parent_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        select_parent_shortcut.activated.connect(self.select_parent_block)
```

- [ ] **Step 5: Run the Task 6 tests**

Run: `python -m pytest tests/ui/test_xml_editor.py -v -k "ctrl_shift_b_shortcut or ctrl_shift_a_shortcut"`
Expected: PASS (2 tests)

- [ ] **Step 6: Run the complete test suite (final regression check)**

Run: `python -m pytest tests/ui/test_xml_editor.py tests/ui/test_xml_structure.py -v`
Expected: PASS — every test in both files.

- [ ] **Step 7: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat(xml_editor): wire Ctrl+Shift+B / Ctrl+Shift+A QShortcuts (WidgetShortcut)"
```

---

## Done criteria

- `python -m pytest tests/ui/test_xml_editor.py tests/ui/test_xml_structure.py -v` is all-green.
- Every pre-existing foundation test still passes (the Task 2 refactor changed *how* extra-selections reach Qt, not *what* the user sees).
- `Ctrl+Shift+B` selects the enclosing block; on a self-closing tag it selects the whole `<Tag/>`; in inter-sibling whitespace it selects the parent; outside any element it is a no-op.
- `Ctrl+Shift+A` selects the parent block, is stateless (repeated presses walk up levels via `selectionStart()`), and is a no-op at top level (not select-all).
- Matching-tag highlighting shows both open and close tags when the cursor is on either, coexisting with the current-line highlight, and clears when the cursor moves off.
- Copying/cutting a folded block yields the full underlying text on the real system clipboard (proved by `test_copy_folded_block_yields_full_text` and its nested-fold variant). Paste needs no new code — standard `QPlainTextEdit` paste, with folding re-scan and syntax re-highlight already driven by the existing `textChanged` connection.

## Spec §3.3 note (paste)

Per spec §7.3, **no paste code is added**. This is deliberate and confirmed sufficient: the correctness requirement is entirely on the copy/cut side (getting the full text onto the clipboard). Pasting that text back is ordinary `QPlainTextEdit` behavior; `textChanged` already re-runs `xml_structure.scan()` (folding) and `QSyntaxHighlighter` re-highlights automatically. No `keyPressEvent` override for paste, no custom clipboard-format handling, no post-paste re-fold step.
