# PGTP Editor — XML Editor Foundation (XML Editor Sub-project A/5) Design Specification

**Date:** 2026-07-12
**Status:** Approved for planning
**Depends on:** [2026-07-11-pgtp-editor-design.md](2026-07-11-pgtp-editor-design.md) (original shell design — §4.3 "Code editor widget", §6.7 "Validation", §9 "Licensing and credits"), `pgtp_editor/ui/center_stage.py`, `pgtp_editor/ui/main_window.py`, `pgtp_editor/model/parser.py`

## 1. Context and scope

The original design spec sketched a single "code editor widget" in §4.3: syntax highlighting with unclosed-quote propagation, auto bracket/quote closing, and auto-closing-tag insertion, built as a PySide6 port of [QCodeEditor](https://github.com/luchko/QCodeEditor) (MIT). Brainstorming this widget in detail — beyond the one-paragraph sketch in §4.3 — surfaced a much richer set of requirements than originally scoped: line-number and fold-marker gutters, code folding driven by a lenient structural scanner, line-wrap toggling, current-line highlighting, auto-indent on Enter, and a real wiring path from "user opens a project" and "a parse fails" through to this widget actually showing real content. That expanded scope is now organized as a 5-part **"XML Editor" feature**, sequenced by dependency:

1. **Editor foundation** (this document) — the `XmlEditor` widget itself: syntax highlighting, gutter (line numbers + fold markers), code folding, line-wrap toggle, current-line highlighting, unclosed-quote propagation, auto bracket/quote/tag closing, auto-indent on Enter. Also wires the editor to the app shell so it displays the currently-open project's real file content on open and on Tier-1 parse failure.
2. **Bookmarks** (future) — gutter click to set/clear a bookmark, `Ctrl+Alt+Up`/`Ctrl+Alt+Down` navigation between them. Not designed here.
3. **Search & Replace** (future) — `Ctrl+F`/`Ctrl+R` with selection pre-fill. Not designed here.
4. **XML structural selection** (future) — `Ctrl+Shift+B`/`Ctrl+Shift+A` block and parent-block selection, plus matching-tag highlighting. Will depend on this document's `xml_structure` tag-position scanner, but the selection/highlighting behavior itself is not designed here.
5. **Schema integration** (future) — XSD-driven "Add new..." context menu, schema-aware hover tooltips, advisory inline validation against a learned schema. Not designed here.

This document covers only sub-project A: the editor foundation.

**Why this absorbs the never-started "Real Raw XML display" work:** the original design's Properties area was going to get a second sub-project, tentatively called "Real Raw XML display," to show a project's actual file text somewhere in the UI. That sub-project was never started. Once the `XmlEditor` widget exists and is wired to `open_project_file` (§4.4 below), it *is* the real raw XML display — a separate, simpler "just show the text" widget would be redundant with a widget that already renders XML text with syntax highlighting. That planned sub-project is therefore superseded by, and folded into, this one; it should not be scheduled as separate future work.

**Relationship to §6.7 of the original design:** §6.7 states plainly that on a Tier-1 (well-formedness) parse failure, "the app automatically opens the raw file in the text-editor fallback view... with the parse error highlighted at its exact line/column" — this widget is described there as "the mandatory fallback UI for Tier 1 validation failures," not an optional power-user view. Today, `MainWindow.open_project_file`'s failure path is only a `QMessageBox.critical` dialog; the Raw XML tab is an empty `QWidget()` that is never populated or shown on failure. §4.4 of this document makes that fallback real for the first time.

## 2. Scope

### 2.1 In scope

- `pgtp_editor/ui/xml_structure.py` — a lenient, regex-based tag-position scanner (§3.1).
- `pgtp_editor/ui/xml_editor.py` — the `XmlEditor(QPlainTextEdit)` widget (§3.2–§3.7):
  - `QSyntaxHighlighter` subclass for tag/attribute-name/attribute-value/text-content coloring, with unclosed-quote propagation via Qt block state.
  - A line-number + fold-marker gutter widget.
  - Code folding (collapse/expand one region per element).
  - `set_line_wrap_enabled(bool)` plus a `View` menu checkable action.
  - Current-line highlighting.
  - Auto-indent on Enter.
  - Auto-closing of `<...>`, quote pairs after `=`, and completed opening tags' matching `</tag>`.
- Wiring `CenterStage`'s Raw XML tab placeholder to a real `XmlEditor` instance (§4.1).
- Wiring `open_project_file`'s success path to populate the editor with the real file's raw text (§4.2).
- Wiring `open_project_file`'s failure path (Tier-1 fallback) to populate the editor, make the Raw XML tab visible and current, and highlight the parse error's line (§4.3–§4.5).
- Confirming/adding the QCodeEditor OSS credit in `about.py` (§4.6).
- Unit tests for `xml_structure` and `pytest-qt` tests for `XmlEditor` and the wiring (§5).

### 2.2 Explicitly out of scope

- **Bookmarks** (sub-project B): gutter-click bookmark set/clear, `Ctrl+Alt+Up`/`Down` navigation.
- **Search & Replace** (sub-project C): `Ctrl+F`/`Ctrl+R`, selection pre-fill.
- **XML structural selection** (sub-project D): `Ctrl+Shift+B`/`Ctrl+Shift+A` block/parent-block selection, matching-tag highlighting. This document's `xml_structure` scanner is designed to be reusable by that future sub-project (§3.1 notes which primitives it is expected to need), but no selection or highlighting behavior for it is implemented here.
- **Schema integration** (sub-project E): XSD-driven "Add new..." menu, hover tooltips, inline schema validation.
- Any editing of the editor's content back into the `ProjectModel`/tree — this widget edits raw text only; nothing here parses edited text back into a `ProjectModel` or writes it to disk. (The original design's §6.7 Tier 1 reparse-on-edit requirement — "(b) the optional Raw XML text-editor panel... where a developer edits a node's text directly" triggering a live reparse — is not implemented in this sub-project. This sub-project only gets real content *into* the editor and *displays* a parse error's location; reparsing an in-progress manual edit and feeding a corrected tree back into the app is a distinct, larger concern left for a future sub-project once this foundation exists.)
- Tier 2 (structural sanity) validation and any Audit-panel wiring — unrelated to this widget.
- Deep referential-integrity checks — unrelated, already deferred in the original design.

## 3. `XmlEditor` and `xml_structure`

### 3.1 `pgtp_editor/ui/xml_structure.py` — the tag-position scanner

This module is deliberately **not** built on `lxml`. `lxml` raises on malformed or incomplete XML, but the scanner has to keep working on exactly that kind of input, since it runs continuously while a user is mid-edit (an unclosed tag, a half-typed attribute, a truncated document are all normal, transient states, not error states, from this module's point of view). It is a plain-Python, regex-based, best-effort scanner with no Qt dependency, so it is unit-testable without a `QApplication`.

**Core data shape:**

```python
@dataclass
class TagSpan:
    name: str                 # element name, e.g. "Page"
    open_start: int            # character offset of the '<' that opens this element
    open_end: int               # character offset just past this open tag's '>'
    close_end: int | None        # character offset just past the matching '</name>' '>',
                                   # or None if no matching close tag was found
    depth: int                  # nesting depth, 0 for a top-level element
    self_closing: bool           # True for a <tag/> form — such an element has no
                                   # separate close tag and is not a foldable region (§3.4)
```

**Algorithm:** a single forward regex pass over the text finds every tag-like token — opening tags (`<name ...>`), self-closing tags (`<name .../>`), and closing tags (`</name>`) — using a permissive pattern that does not require attribute values to be well-formed or quotes to be balanced (e.g. `<(/?)([A-Za-z_][\w.-]*)([^<>]*?)(/?)>`). The scanner walks the token stream maintaining an explicit stack of open `TagSpan`s:

- An opening tag pushes a new `TagSpan` (with `close_end=None` for now) onto the stack.
- A self-closing tag emits a complete `TagSpan` immediately (`self_closing=True`, `close_end=open_end`) without touching the stack.
- A closing tag `</name>` pops the stack looking for the nearest still-open `TagSpan` with a matching `name`. If found, that span's `close_end` is set and it is emitted; any *other* still-open spans between the matched one and the top of the stack (i.e. tags that were opened but never validly closed before this closing tag appeared) are emitted as-is with `close_end=None` and discarded — this is the "mismatched tag" tolerance case. If no open span with that name exists anywhere on the stack, the stray closing tag is ignored (it matches nothing and is not itself an error the scanner reports — reporting malformed-XML errors is Tier-1's job via `lxml`, not this scanner's).
- At end of input, any `TagSpan`s still on the stack (truncated document, or a genuinely unclosed tag) are emitted as-is with `close_end=None`.

This means `scan(text) -> list[TagSpan]` **never raises**, regardless of how malformed or incomplete `text` is — the worst case is a `TagSpan` with `close_end=None`, which is exactly the signal both folding (§3.4, an unclosed element simply isn't foldable yet) and auto-tag-closing (§3.6) need to detect "this tag has no close yet."

**Primitives the module exposes**, each built on top of one `scan()` call (callers are not expected to call `scan()` directly for these common queries):

- `find_enclosing_open_tag(text, position) -> str | None` — "find the nearest open tag name before position N" (the exact primitive named in the original §4.3 description for auto-closing-tag insertion, §3.6 below). Implemented by scanning and returning the innermost `TagSpan` whose `open_start <= position` and which has no `close_end`, or whose `close_end > position` (i.e. `position` falls strictly inside that element's content span) and has no descendant span also containing `position` — in other words, the deepest element that contains `position` and is not yet known to be closed before it, matching how a user mid-typing between an opening and (possibly not-yet-typed) closing tag would expect "what tag am I inside of" to behave.
- `nesting_depth_at(text, position) -> int` — depth of `find_enclosing_open_tag`'s result, or `0` if none.
- `indent_unit_for(project) -> str` — not part of this scanner; auto-indent (§3.7) uses a fixed two-space unit, see that section.

**Reuse note for sub-project D:** the future XML structural-selection sub-project (Ctrl+Shift+B/A block and parent-block selection, matching-tag highlighting) is expected to need "the `TagSpan` enclosing position N" and "the `TagSpan` one level up from a given `TagSpan`" — both are direct consequences of the stack-based `scan()` output and require no new scanning logic, only a new query function over the existing `list[TagSpan]`. This document does not implement those query functions, since sub-project D is not in scope here, but the data shape above was chosen specifically so that sub-project can be built as pure additions to `xml_structure.py` rather than a rework of `scan()`.

### 3.2 `XmlEditor(QPlainTextEdit)` — overview

```python
class XmlEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = XmlSyntaxHighlighter(self.document())
        self._gutter = _EditorGutter(self)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter_on_scroll)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_gutter_width(0)
        self._highlight_current_line()

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
        # Folding state is per-document-instance; a fresh setPlainText call
        # (a new file loaded into this editor) starts fully unfolded.
        self._fold_state = {}
```

The widget owns three cooperating pieces, each in its own class within `xml_editor.py`: `XmlSyntaxHighlighter` (§3.3), `_EditorGutter` (§3.4, private — no external code needs to touch it directly, matching the plain `QWidget`-side-widget pattern from the Qt "Code Editor Example"), and the folding/auto-indent/auto-close behavior implemented directly as methods on `XmlEditor` itself (§3.4–§3.6), since those behaviors need direct access to `QTextCursor`/`QTextBlock` state that has no reason to live in a separate class.

### 3.3 Syntax highlighting and unclosed-quote propagation

`XmlSyntaxHighlighter(QSyntaxHighlighter)` colors four categories via `QTextCharFormat`s set up once in `__init__` (exact colors are a presentation detail left to implementation, not specified numerically here — the requirement is that the four categories are visually distinct):

- **Tag delimiters and names** (`<`, `>`, `/`, the element name) — one format.
- **Attribute names** — a second format.
- **Attribute values** (the quoted string, including its quotes) — a third format, the same format used for the unclosed-quote propagation case below.
- **Text content** (everything outside tags) — a fourth format, or left as the default/unformatted text color.

`highlightBlock(text)` is called by Qt once per line (`QTextBlock`). The unclosed-quote requirement — "everything after an unterminated `\"` renders as string-colored until the next quote or EOF" — is implemented with the standard Qt multi-line-highlighting technique, using `previousBlockState()`/`setCurrentBlockState()` to carry "am I still inside an unclosed quote from a previous line" state across block boundaries:

```python
STATE_NORMAL = 0
STATE_IN_UNCLOSED_STRING = 1

def highlightBlock(self, text: str) -> None:
    start = 0
    if self.previousBlockState() == STATE_IN_UNCLOSED_STRING:
        # Carry the string format from the end of the previous line until
        # the next quote in this line, or to EOL if there isn't one.
        close_at = text.find('"')
        if close_at == -1:
            self.setFormat(0, len(text), self._string_format)
            self.setCurrentBlockState(STATE_IN_UNCLOSED_STRING)
            return
        self.setFormat(0, close_at + 1, self._string_format)
        start = close_at + 1

    # Normal per-line tag/attribute/value/text tokenizing from `start` onward,
    # using the same permissive regex family as xml_structure.scan(), applying
    # the tag/attribute-name/text formats as each token is found.
    ...
    # If this line ends with an odd number of quotes from `start` onward, the
    # last quote opened a string that is not closed on this line:
    if _has_unterminated_quote(text, start):
        self.setCurrentBlockState(STATE_IN_UNCLOSED_STRING)
    else:
        self.setCurrentBlockState(STATE_NORMAL)
```

This is exactly the mechanism named in the original §4.3 ("Qt's `QSyntaxHighlighter` block-state mechanism... the standard technique Qt-based editors use for multi-line strings/comments") — a well-trodden pattern, not a novel one. Qt automatically re-invokes `highlightBlock` for a block whenever its `previousBlockState()` input changes (e.g. typing a `"` on an earlier line causes every subsequent line to be reformatted), so no manual "re-highlight everything below" logic is needed.

### 3.4 Gutter: line numbers and fold markers

`_EditorGutter(QWidget)` is the standard `QPlainTextEdit` side-widget pattern (the well-documented Qt "Code Editor Example," ported here rather than hand-waved):

- **Sizing:** `XmlEditor.setViewportMargins(gutter_width, 0, 0, 0)` reserves horizontal space for the gutter; `gutter_width` is recomputed in `_update_gutter_width` (connected to `blockCountChanged`) as a function of `len(str(self.blockCount()))` (so the gutter widens as line numbers grow from 2 to 3 to 4 digits) plus a fixed allowance for the fold-triangle glyph.
- **Positioning:** `_EditorGutter` is a child widget of `XmlEditor` whose `geometry()` is kept in sync with the editor's `contentsRect()` in an overridden `resizeEvent`, so it always occupies the left margin reserved above.
- **Painting:** `_EditorGutter.paintEvent` iterates visible `QTextBlock`s (starting from `self._editor.firstVisibleBlock()`, using `blockBoundingGeometry`/`blockBoundingRect` to compute each block's vertical position, the same traversal the Qt example uses) and, for each visible block, draws: (a) the 1-based line number, right-aligned; (b) if that block is the `open_start` line of some `TagSpan` with a non-`None` `close_end` spanning more than one line (i.e. a foldable region, §3.4 continued below), a small triangle glyph — pointing down if currently expanded, right if currently collapsed.
- **Sync signals:** repainting is triggered by `updateRequest` (fires on scroll and on any viewport update) and `blockCountChanged` (fires when lines are added/removed, which also changes the required gutter width) — both connected in `XmlEditor.__init__`, matching the Qt example's documented signal set exactly.
- **Click handling:** `_EditorGutter.mousePressEvent` hit-tests the click's y-coordinate against each visible foldable block's fold-triangle glyph rectangle; a hit calls back into `XmlEditor._toggle_fold(block)`.

### 3.5 Code folding

Folding is driven by `xml_structure.scan()` (§3.1), re-run whenever the document's text changes (connected to `QPlainTextEdit.textChanged`, debounced is not required at this stage — re-scanning even a large `.pgtp` file's text with a single regex pass is expected to be fast enough to run synchronously on every keystroke; this should be revisited if profiling later shows otherwise, but is not a concern this document treats as an open question requiring a different design).

One foldable region per **non-self-closing** `TagSpan` with a non-`None` `close_end` whose `open_start` line differs from its `close_end` line (a single-line element has nothing useful to fold). The region is "its open tag through its matching close tag" — i.e. the `QTextBlock`s strictly between the line containing `open_end` and the line containing `close_end` (the open tag's own line and the close tag's own line always stay visible; only the contained lines fold away), which is the standard Qt folding definition and keeps a collapsed region visually anchored by its own opening and closing tags.

- **Collapse:** `_toggle_fold(block)` — given the `QTextBlock` at a foldable region's start, calls `.setVisible(False)` on every contained `QTextBlock` (the standard Qt technique named in the requirements), then calls `self.document().markContentsDirty(...)` over that range and `self.viewport().update()` so the view re-lays-out immediately without the hidden blocks taking vertical space.
- **Expand:** the reverse — `.setVisible(True)` on the same block range.
- **Nested folds:** collapsing an outer region while an inner region is already independently collapsed is handled correctly for free by `QTextBlock.setVisible`, since Qt tracks visibility per block; re-expanding the outer region does not implicitly re-expand an already-collapsed inner region, matching ordinary code-editor expectations (an editor's own fold-state dict, `self._fold_state: dict[int, bool]` keyed by the block's `blockNumber()` at fold time, records which regions are currently collapsed so the gutter (§3.4) knows which triangle glyph orientation to draw and so folds survive a `_update_gutter_width`-triggered repaint without needing to be recomputed from scratch).
- **Interaction with editing:** if a user edits inside or around a currently-collapsed region such that the underlying `TagSpan` structure changes, the simplest correct behavior — and the one this document specifies — is that the next `xml_structure.scan()` re-run (on `textChanged`) simply stops treating stale block numbers as foldable if their span no longer qualifies; no attempt is made to "re-map" a fold across a structural edit. This is a deliberate simplification: precise fold-tracking across arbitrary concurrent edits is a well-known hard problem in every code editor, and nothing in the brainstormed requirements asked for more than "clicking a gutter fold triangle collapses/expands that region."

### 3.6 Line-wrap toggle

```python
def set_line_wrap_enabled(self, enabled: bool) -> None:
    self.setLineWrapMode(
        QPlainTextEdit.LineWrapMode.WidgetWidth
        if enabled
        else QPlainTextEdit.LineWrapMode.NoWrap
    )
```

Wired to a new checkable `View` menu action in `main_window.py`, following **exactly** the existing pattern used for the other `View` menu checkable actions (`_build_view_menu`, e.g. the existing "Raw XML Panel" action):

```python
line_wrap_action = menu.addAction("Wrap Raw XML Lines")
line_wrap_action.setCheckable(True)
line_wrap_action.setChecked(False)   # NoWrap is QPlainTextEdit's own default
line_wrap_action.toggled.connect(self.center_stage.xml_editor.set_line_wrap_enabled)
```

Placed in the existing `View` menu alongside "Raw XML Panel" (both concern the same tab), added after that action, before the "Expand All"/"Collapse All" separator.

### 3.7 Current-line highlighting

```python
def _highlight_current_line(self) -> None:
    selection = QTextEdit.ExtraSelection()
    selection.format.setBackground(self._current_line_color)
    selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
    selection.cursor = self.textCursor()
    selection.cursor.clearSelection()
    self.setExtraSelections([selection])
```

Connected to `cursorPositionChanged`. `setExtraSelections` **replaces** the editor's extra-selection list wholesale each call with a list containing exactly this one selection — so this method is the single owner of `XmlEditor`'s extra-selections in this sub-project (there is no other feature in scope here that also wants an extra selection at the same time; the Tier-1 fallback's error-line highlighting, §4.5, is a distinct, one-shot use of `setExtraSelections` invoked right after `setPlainText` on load, not a persistent one competing with this per-keystroke one — see §4.5 for how the two interact).

### 3.8 Auto-indent on Enter

Intercepted in `keyPressEvent` for `Qt.Key.Key_Return`/`Qt.Key.Key_Enter`:

```python
def keyPressEvent(self, event: QKeyEvent) -> None:
    if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        self._insert_newline_with_indent()
        return
    ...  # §3.9 auto-close handling, then super().keyPressEvent(event) fallthrough

def _insert_newline_with_indent(self) -> None:
    cursor = self.textCursor()
    current_line = cursor.block().text()
    leading_ws = current_line[: len(current_line) - len(current_line.lstrip())]
    position = cursor.position() - cursor.block().position()
    enclosing = xml_structure.find_enclosing_open_tag(self.toPlainText(), position)
    extra_indent = ""
    if enclosing is not None and _cursor_immediately_after_open_tag(current_line, position, enclosing):
        extra_indent = "  "  # one level deeper, two-space unit
    cursor.insertText("\n" + leading_ws + extra_indent)
```

Two cases, both stated in the requirements:

- **Plain-inherit:** the new line starts with exactly the same leading whitespace as the line Enter was pressed on.
- **After an opening tag:** if the cursor is immediately after an opening tag's `>` (detected via `xml_structure.find_enclosing_open_tag` confirming the enclosing element's open tag ends exactly at the cursor position, i.e. there is no content yet between the open tag and the cursor), the new line gets one additional indent level (a fixed two-space unit) beyond the inherited whitespace.

The two-space unit is a fixed constant for this sub-project (matching `.pgtp`'s own on-disk indentation convention observed in the sample files) rather than a user preference — no preferences UI exists yet for this widget, and none was requested for indent width specifically.

### 3.9 Auto-closing: brackets, quotes, tags

Also intercepted in `keyPressEvent`, before the Enter handling's fallthrough to `super()`:

- **Typing `<`:** insert `<>` and leave the cursor positioned between them (i.e. insert the matching `>` "immediately after the cursor," per the requirement, without moving the cursor past it) — `cursor.insertText("<>"); cursor.movePosition(QTextCursor.MoveOperation.Left)`. If the very next character already typed is going to be `/` (closing-tag start) this still applies uniformly; there is no special-case suppression, matching the "everything typed goes through the same auto-close path" simplicity of the requirement as stated.
- **Typing a quote (`"` or `'`) immediately after `=`:** insert the pair (`""` or `''`) with the cursor placed between them, mirroring the `<`/`>` case. Detected by checking the character immediately before the cursor (before the quote is inserted) is `=`.
- **Completing an opening tag** (typing the closing `>` of a tag that is not self-closing, i.e. does not end in `/>`): after inserting the `>` itself (which may itself have been auto-inserted per the first bullet — typing `>` when the character immediately after the cursor is already the auto-inserted `>` should simply move the cursor past it rather than inserting a second one, the standard "type-through" behavior for auto-closed pairs), backward-scan the text up to the cursor for the nearest unclosed tag name via `xml_structure.find_enclosing_open_tag(text, cursor_position)` and insert `</name>` immediately after the cursor, again without moving the cursor past it. This is the exact mechanism named in the original §4.3 ("backward-scanning for the nearest unclosed tag name") — implemented here by delegating the scan itself to `xml_structure`, not re-implementing backward-scanning logic inside `xml_editor.py`.

All three behaviors call `super().keyPressEvent` only for the underlying character insertion path when no special handling applies; when a special case fires, the method performs its own `QTextCursor` edits and returns without calling `super()` for that key event, consistent with the standard Qt `keyPressEvent`-interception pattern for auto-closing editors.

## 4. Wiring

### 4.1 `CenterStage`: replacing the Raw XML placeholder

Mirrors exactly how the Diff/Merge viewer sub-project replaced `diff_merge_tab_index`'s placeholder with a real `DiffMergePanel` instance (`pgtp_editor/ui/center_stage.py`, current `diff_merge_panel` construction). Today:

```python
self.raw_xml_tab_index = self.addTab(QWidget(), "Raw XML")
```

becomes:

```python
from pgtp_editor.ui.xml_editor import XmlEditor
...
self.xml_editor = XmlEditor()
self.raw_xml_tab_index = self.addTab(self.xml_editor, "Raw XML")
```

`set_raw_xml_tab_visible` is unchanged — it already operates purely on tab visibility by index and does not need to know what widget occupies that tab.

### 4.2 Populating the editor on successful open

`MainWindow.open_project_file`'s success path currently ends at `self.statusBar().showMessage(...)` after populating the project tree. This sub-project adds one line reading the file's raw text (a plain file read — **not** through `lxml`, since the editor should show the file exactly as it is on disk, byte-for-byte, independent of anything the parser does or doesn't preserve) and pushing it into the editor:

```python
def open_project_file(self, path):
    try:
        project = load_project(path)
    except PgtpParseError as exc:
        self._handle_parse_failure(path, exc)   # §4.3
        return
    self.project_tree.populate_from_project(project)
    self._current_project = project
    self._current_project_path = path
    with open(path, "r", encoding="utf-8") as f:
        raw_text = f.read()
    self.center_stage.xml_editor.setPlainText(raw_text)
    self.statusBar().showMessage(f"Opened: {path}", 5000)
```

Reading as UTF-8 matches the format's own documented encoding (original design spec §2.1: "UTF-8, no XML declaration, no BOM, LF line endings"). Note the `except Exception` in the current code is narrowed to `except PgtpParseError` here specifically so the Tier-1 fallback path (§4.3) is reachable only for the case it is meant for — a genuine parse failure — while any other unexpected exception (e.g. a permissions error on the file) still surfaces distinctly rather than being funneled into the "let's show the raw-XML fallback" flow, which would be a confusing response to a problem that has nothing to do with XML well-formedness. See §4.4 for the full justification of this change.

### 4.3 What `PgtpParseError` actually carries today, and what this means for the fallback design

Read directly from `pgtp_editor/model/parser.py`:

```python
class PgtpParseError(Exception):
    """Raised when a .pgtp file cannot be parsed into a ProjectModel."""
```

`PgtpParseError` is a bare `Exception` subclass with **no structured fields at all** — no `lineno`, no `offset`, nothing beyond whatever string was passed to its constructor. `load_project` raises it in two places:

```python
except (etree.XMLSyntaxError, OSError) as exc:
    raise PgtpParseError(f"Could not parse '{path}': {exc}") from exc
...
except Exception as exc:  # defensive: any unexpected structural surprise
    raise PgtpParseError(f"Could not parse '{path}': {exc}") from exc
```

Two consequences follow directly from this, and this document designs around them rather than inventing data that isn't there:

1. **The underlying `lxml.etree.XMLSyntaxError` genuinely does carry `.lineno`/`.offset`** (confirmed: this is a standard, always-populated attribute pair on that exception type), and it is chained via Python's `raise ... from exc` — so it is reachable today as `PgtpParseError.__cause__`, but only when the failure came from the first `except` clause (an actual XML syntax error). It is **not** reachable when the failure came from the second, broader `except Exception` clause (a structurally-unexpected-but-well-formed document — e.g. a `Detail` element with no nested `Page`, which `_parse_detail` raises as a plain `ValueError`) — that path's `__cause__` is whatever the deeper exception was (a `ValueError`, `AttributeError`, etc.), which has no `.lineno`/`.offset` at all. `PageNode`/`DetailNode`/etc. do carry a `sourceline` (from `page_el.sourceline`), but that is only available if a node was successfully constructed — which by definition didn't happen for whatever failed.
2. **This sub-project adds a `line: int | None` field to `PgtpParseError` rather than leaving callers to reach into `__cause__` and type-check it.** `PgtpParseError.__init__` is changed to accept an optional `line: int | None = None` keyword, and `load_project`'s first `except` clause is changed to pass `line=exc.lineno` (from the caught `XMLSyntaxError`, whose `.lineno` is always populated) through to the raised `PgtpParseError`. The second, broader `except Exception` clause continues to raise with `line=None` — there is no reliable line number available for a structural-surprise failure that isn't itself an XML syntax error, and this document does not invent one. Column (`.offset`) is deliberately **not** plumbed through: the brainstormed requirement says "highlighted at its exact line/column" but qualifies it "if available," and a column offset is materially less useful than a line number for this widget's fallback purpose (the whole line gets highlighted, per §4.5 below, not a sub-span within it) — adding an unused field would be speculative scope, so it is left out. If a future sub-project finds a concrete use for column-level highlighting, `exc.offset` remains available via `__cause__` for that work to add at that time.

This is a small, targeted, justified change to `parser.py` — the only change to that file this sub-project makes:

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
```

```python
    try:
        tree = etree.parse(str(path))
    except (etree.XMLSyntaxError, OSError) as exc:
        line = exc.lineno if isinstance(exc, etree.XMLSyntaxError) else None
        raise PgtpParseError(f"Could not parse '{path}': {exc}", line=line) from exc
```

(The second `except Exception` clause in `load_project`, around the page-tree-walking code, is unchanged — it continues to raise `PgtpParseError(f"Could not parse '{path}': {exc}") from exc"`, i.e. with `line=None` via the new default.)

### 4.4 Tier-1 fallback: what happens on a parse failure

**Decision: the `QMessageBox.critical` dialog is kept, and the raw-XML fallback happens in addition to it, not instead of it.** Justification: the dialog is the only thing that tells the user *why* the open failed (the exception's message text) — the raw-XML view, on its own, shows *where* the problem is but not a plain-language explanation of what's wrong, especially in the structural-surprise case (§4.3's second failure path) where there may be no single "line" to point at. Removing the dialog would mean a user occasionally lands in a wall of raw text with only a highlighted line and no explanation. Keeping both means: dialog explains, raw-XML view lets you fix. This matches §6.7's own framing that the raw-XML view is where "the fix happens," not where the problem is first reported.

```python
def open_project_file(self, path):
    try:
        project = load_project(path)
    except PgtpParseError as exc:
        self._handle_parse_failure(path, exc)
        return
    ...  # success path, §4.2

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
        # The file itself is unreadable (e.g. it was deleted between the
        # earlier parse attempt and this read, or a permissions error) --
        # nothing to show in the fallback view in that case; the dialog
        # above has already reported the failure and there is no raw text
        # to fall back to, so this method simply returns without touching
        # the Raw XML tab at all (never a blank/misleading fallback).
        return
    self.center_stage.xml_editor.setPlainText(raw_text)
    if exc.line is not None:
        self.center_stage.xml_editor.highlight_error_line(exc.line)
    self.center_stage.set_raw_xml_tab_visible(True)
    self._raw_xml_panel_action.setChecked(True)
    self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)
```

Note this method does **not** update `self._current_project`/`self._current_project_path` or call `self.project_tree.populate_from_project` — the currently-tracked project and tree are left exactly as they were before the failed open attempt, per `open_project_file`'s own existing documented contract ("leaves the currently-displayed tree... untouched"). The Raw XML tab now shows the *failed* file's raw text, which is intentionally decoupled from "what project is currently loaded" — opening a second, different, successfully-parsing file afterward will overwrite the Raw XML tab's content via §4.2's normal success path, exactly as viewing any other file's raw text would.

**Why the file is re-read here rather than plumbed through from `load_project`:** `load_project` operates on `lxml`'s own parse, which does not hand back the original raw text on failure (it only raises). Re-reading the file directly (the same plain UTF-8 read used in §4.2) is simple, and the failure mode of that second read (§ `except OSError` above) is itself informative — if the file can't even be read as plain text, that's a different, rarer problem than an XML syntax error, and is handled by simply not populating the fallback view rather than crashing or showing corrupted content.

**The View menu's "Raw XML Panel" checkbox state:** yes, it must flip to checked when this fallback triggers. Justification: that checkbox is the single source of truth the user has for "is the Raw XML tab visible," and `set_raw_xml_tab_visible(True)` above changes the tab's actual visibility without going through the checkbox's own `toggled` signal (calling the dock/tab visibility setter directly, not clicking the menu item) — if the checkbox were left unchecked while the tab was actually visible, the user would see a visible tab whose own menu toggle claims it's hidden, and clicking the checkbox to "show" it would instead hide it (since `toggled` fires with whatever the new checked state becomes, and an already-unchecked box being clicked goes to checked, which is *coincidentally* consistent in this one case — but if the user later manually unchecks and rechecks it, the desync becomes visible). `MainWindow` therefore keeps a direct handle to the action, `self._raw_xml_panel_action`, captured when the `View` menu is built (currently a local variable `raw_xml_action` inside `_build_view_menu`; this sub-project promotes it to a `self.` attribute so `_handle_parse_failure` can set its checked state), and sets `.setChecked(True)` on it directly. `QAction.setChecked` does still emit `toggled`, so `set_raw_xml_tab_visible(True)` would in fact be called a second time via that signal — harmlessly idempotent (setting an already-visible tab visible again is a no-op), so no guard against double-invocation is needed.

### 4.5 Highlighting the parse-error line

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
    self._error_line_selection = selection
    self.setExtraSelections([selection])
```

This both **scrolls the cursor there** (`setTextCursor` + `centerCursor()`, so the error line is immediately visible without the user needing to scroll and search) and **highlights it** (via `setExtraSelections`, in a color distinct from the current-line-highlight color used by §3.7, so a user can tell "this line has a parse error" apart from "this is just where my cursor happens to be").

**Interaction with §3.7's current-line highlighting:** both features use `setExtraSelections`, which replaces the whole list on every call. Since `cursorPositionChanged` (§3.7's trigger) fires as a side effect of the `setTextCursor` call inside `highlight_error_line` itself, the ordering matters: `_highlight_current_line` (§3.7) runs *first* (as an immediate, synchronous slot invocation triggered by `setTextCursor`), setting the extra-selections list to just the current-line selection; then `highlight_error_line`'s own explicit `self.setExtraSelections([selection])` call runs *after*, overwriting that list with just the error-line selection. Net effect on load: only the error-line highlight is visible immediately after `highlight_error_line` returns, which is the desired behavior (the error line, not incidentally wherever the cursor started, is what should be emphasized right after a failed open). As soon as the user moves the cursor at all afterward, §3.7's handler fires again and reverts to showing only the current-line highlight — the error-line highlight is a **one-shot indicator for the moment of the fallback**, not a persistent marker that survives cursor movement. Nothing in the brainstormed requirements asked for a persistent error marker independent of cursor position (that would start to overlap with sub-project B's future bookmarks), so this document does not add one.

### 4.6 OSS credit for QCodeEditor

Checked `pgtp_editor/ui/about.py`'s current `ABOUT_TEXT` directly: the QCodeEditor credit **already exists**, added by the original 12-task shell plan before this widget was actually built:

```
<li><a href="https://github.com/luchko/QCodeEditor">QCodeEditor</a>
(luchko, MIT License) &mdash; the code-editor widget is a PySide6 port
of this project's approach.</li>
```

This satisfies §9's MIT-attribution requirement already, and `tests/ui/test_about.py::test_credits_mention_all_three_projects` already asserts `"QCodeEditor" in ABOUT_TEXT`. **This sub-project makes no changes to `about.py`** — the credit text's own description ("the code-editor widget is a PySide6 port of this project's approach") remains accurate now that the widget is actually built along exactly those lines (line numbers, current-line highlighting, the `QSyntaxHighlighter` hook pattern — all present in this design), so no wording update is needed either.

## 5. Testing strategy

### 5.1 Unit tests for `xml_structure` (no Qt dependency)

- **Well-formed nesting:** a small synthetic multi-level XML fragment produces `TagSpan`s with correct `depth` at each level, correct `open_start`/`open_end`/`close_end` offsets (verified by slicing the source text at those offsets and checking the substrings are exactly the expected tag text), and `self_closing=True` only for actual `<tag/>` forms.
- **Tolerance — unclosed tag:** a fragment ending mid-element (e.g. `<Page><Detail>` with no closes at all) does not raise, and returns `TagSpan`s for both elements with `close_end=None`.
- **Tolerance — mismatched tag:** a fragment like `<Page><Detail></Page>` (closing the outer before the inner) does not raise; `Page` is emitted with `close_end` set correctly at its own close, and `Detail` is emitted with `close_end=None` — matching the "any other still-open spans... are emitted as-is with `close_end=None`" rule in §3.1.
- **Tolerance — truncated document:** a fragment cut off mid-attribute (e.g. `<Page fileName="foo`) does not raise and returns a best-effort partial structure (at minimum, an empty list or a `TagSpan` for any element that did complete its own `>` before the truncation — the exact boundary behavior is that the regex simply doesn't match an incomplete tag token, so nothing crashes and nothing incorrect is fabricated).
- **`find_enclosing_open_tag`:** given a handful of positions in a small nested fragment, asserts the correct enclosing tag name at each — including a position inside an unclosed tag (no matching close anywhere in the text) and a position after all tags have properly closed (expected result: `None`).

### 5.2 `pytest-qt` tests for `XmlEditor`

- **Syntax-highlighting block-state propagation:** set text containing an unterminated `"` on one line followed by a second line of ordinary content; assert (via `QSyntaxHighlighter`'s block user-data or by inspecting the format at specific character positions using `QTextBlock.layout().formats()` / the document's own format-at-position query) that characters on the second line render with the string format, and that a subsequent edit adding the missing closing `"` causes the second line's format to revert to normal — confirming the propagation is live, not a one-time computation.
- **Fold/unfold:** build a small multi-line nested fragment, call `_toggle_fold` on the outer element's `QTextBlock`, and assert exactly the contained `QTextBlock`s (not the open/close tag lines themselves) report `isVisible() is False`; call it again and assert all are back to `True`. A nested-fold case: collapse an inner region, then collapse and re-expand its outer region, and assert the inner region's blocks remain hidden throughout (per §3.5's nested-fold note).
- **Auto-indent, plain-inherit case:** set text ending in a line with some leading whitespace and no trailing open tag, position the cursor at end-of-line, simulate `Qt.Key.Key_Return` via `qtbot.keyClick`, and assert the new line's leading whitespace exactly matches the previous line's.
- **Auto-indent, after-opening-tag case:** position the cursor immediately after an opening tag's `>` with nothing else on that line, simulate Enter, and assert the new line's leading whitespace is the previous line's plus one two-space unit.
- **Auto-close `<`:** simulate typing `<` via `qtbot.keyClicks`, assert the document text now contains `<>` with the cursor positioned between them (`textCursor().position()` is one past the `<`).
- **Auto-close quote after `=`:** position the cursor immediately after a typed `=`, simulate typing `"`, assert `""` appears with the cursor between the quotes.
- **Auto-close completed opening tag:** type a full opening tag ending in the closing `>` (not self-closing), assert `</name>` is auto-inserted immediately after the cursor and the cursor itself does not move past it.
- **Line-wrap toggle:** call `set_line_wrap_enabled(True)`, assert `lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth`; call it with `False`, assert it reverts to `NoWrap`.
- **Current-line highlighting is exclusive:** move the cursor via `qtbot`, assert `len(editor.extraSelections()) == 1` after each move — never zero, never more than one — confirming §3.7's "single owner of extra-selections" design holds in practice for ordinary cursor movement (i.e. outside the one-shot error-line-highlight interaction covered separately below).

### 5.3 Wiring tests

- **Successful open populates the editor byte-for-byte:** using one of the real sample files already present in this worktree's `sample/` directory (e.g. `sample/dev_Ferrara.pgtp`), call `MainWindow.open_project_file(path)` and assert `window.center_stage.xml_editor.toPlainText()` equals the file's own raw text read directly (`open(path, encoding="utf-8").read()`), asserting byte-for-byte (character-for-character, given both sides go through the same UTF-8 decode) equality — confirming §4.2's read path shows the file exactly as it is on disk.
- **Tier-1 fallback:** construct a deliberately malformed `.pgtp` fixture (e.g. a file with a genuinely unclosed tag, written to a temp path via `tmp_path` — not one of the real sample files, which are known-valid) and call `open_project_file` against it. Assert: the Raw XML tab is both visible (`center_stage.isTabVisible(raw_xml_tab_index)`) and current (`center_stage.currentIndex() == raw_xml_tab_index`); `xml_editor.toPlainText()` equals that fixture file's raw text; the View menu's Raw XML Panel action (`window._raw_xml_panel_action.isChecked()`) is `True`; and the extra-selection present after the call corresponds to the expected error line (cross-checked against the `lxml.etree.XMLSyntaxError.lineno` the fixture is known to trigger, established by first confirming what line `lxml` itself reports for the deliberately-broken fixture, rather than hard-coding an assumed line number).

## 6. Summary of decisions from brainstorming

- The XML Editor feature grew from the original design's one-paragraph §4.3 sketch into a 5-part feature (Editor foundation / Bookmarks / Search & Replace / Structural selection / Schema integration) once the editor widget was brainstormed in real detail — this document is sub-project A, the foundation the other four depend on.
- This sub-project **supersedes and folds in** the never-started "Properties sub-project 2: Real Raw XML display" — once `XmlEditor` is wired to `open_project_file`, it already is the real raw-XML display; a separate simpler widget for that purpose would be redundant and is not built.
- `xml_structure.py` is deliberately **not** `lxml`-based — it must tolerate malformed/incomplete XML that a user is actively mid-editing, which `lxml` cannot do (it raises). It is a plain-Python, regex-based, stack-driven scanner with no Qt dependency, kept separate from `xml_editor.py` so it stays independently unit-testable and reusable by the future structural-selection sub-project (D) without pulling in Qt.
- Folding, gutter painting, and auto-indent's "am I right after an opening tag" check all reuse the same `xml_structure.scan()`/`find_enclosing_open_tag` primitives rather than each re-deriving their own tag-position logic — one scanner, several consumers.
- `PgtpParseError` gains a new `line: int | None` field, populated from `lxml.etree.XMLSyntaxError.lineno` when the failure is a genuine XML syntax error, and left `None` for the separate, broader "structurally unexpected but well-formed" failure path in `load_project` — this document does not invent a line number where lxml/the parser genuinely has none. Column offset (`.offset`) is deliberately not plumbed through, since this sub-project's fallback highlights a whole line, not a sub-span, and no concrete need for column precision was identified.
- On a Tier-1 parse failure, the existing `QMessageBox.critical` dialog is **kept**, not replaced — the raw-XML-view fallback (populate + make visible + make current + highlight the error line, when a line is known) happens **in addition to** the dialog, on the reasoning that the dialog is the only thing that explains *why*, while the editor view is *where the fix happens*, per §6.7's own framing.
- The View menu's "Raw XML Panel" checkbox is kept in sync with the tab's actual visibility during this fallback by holding a direct `self._raw_xml_panel_action` reference and calling `.setChecked(True)` on it, rather than leaving it out of sync with a tab that was made visible through a different code path.
- The QCodeEditor OSS credit in `about.py` was checked and found to **already exist** (added ahead of the widget itself by the original 12-task shell plan) — this sub-project makes no changes to `about.py`.
- Reparsing a manually-edited raw-XML document back into a live `ProjectModel` (the other half of §6.7 Tier 1's "(b) the optional Raw XML text-editor panel... where a developer edits a node's text directly") is explicitly **out of scope** for this sub-project — this document only gets real content *into* the editor (on open, and on parse failure) and displays where a known error is; feeding a corrected edit back into the app's live model is left for a future sub-project once this foundation exists.
