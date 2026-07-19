# Ctrl+click / Alt+click tag navigation — Design

**Date:** 2026-07-19
**Component:** `pgtp_editor/ui/xml_editor.py` (new `mousePressEvent` override),
`pgtp_editor/ui/xml_structure.py` (two pure target-resolver helpers).

## Goal

Two mouse shortcuts in the Raw XML editor for structural navigation:

- **Ctrl + left-click** on a tag jumps the caret to its **matching tag** — click
  an opening tag to jump to its closing tag, or a closing tag to jump to its
  opening tag.
- **Alt + left-click** jumps the caret to the **start of the parent element's
  opening tag**.

"Jump" means: place the text caret at the target and scroll it into view
(`ensureCursorVisible`). No selection is made. After a jump the project tree stays
in sync (the editor emits its existing `line_clicked` signal for the new line).

The existing keyboard commands are unchanged: **Ctrl+Shift+B** still selects the
enclosing element and **Ctrl+Shift+A** still climbs to the parent (repeatable).
These clicks are the pointer-driven counterparts to that navigation.

## Non-goals (YAGNI)

- No modifier-hover affordance (link cursor / underline on Ctrl-hover).
- No right-click menu entries (the Edit menu already carries keyboard equivalents
  for block/parent selection).
- No change to `Ctrl+Shift+B` / `Ctrl+Shift+A` or to selection behavior.
- No multi-caret; QPlainTextEdit doesn't support it and we don't add it.

## Behavior

### Event handling — `XmlEditor.mousePressEvent` (new override)

On a **left-button** press whose modifiers are exactly **Ctrl** or exactly **Alt**:

1. Map the click point to a document offset with `cursorForPosition(pos)`
   (`pos` in viewport coordinates, as Qt delivers to this handler — the same
   coordinate space the existing `mouseReleaseEvent`/hover paths use).
2. Compute the target offset (below). If `None`, **fall through** to
   `super().mousePressEvent(event)` (normal click).
3. If there is a target: set the caret to it, `ensureCursorVisible()`, emit
   `line_clicked` with the target's 1-based line, and **`event.accept()`**.

Accepting the press is essential for **Alt**: Qt's default Alt+drag begins a
**column (block) selection**; consuming the press prevents that and guarantees no
stray selection is left at the destination. For consistency Ctrl is handled the
same way. Any other modifier combination (e.g. Ctrl+Alt, Ctrl+Shift) and the
plain unmodified click fall through to `super()` untouched, preserving the current
click-to-place-caret + `line_clicked` behavior implemented in
`mouseReleaseEvent`.

**Release side.** When a modifier-jump is performed, the handler sets a one-shot
flag (`self._nav_click_handled = True`). `mouseReleaseEvent` checks it first: if
set, it clears the flag, `event.accept()`s, and returns **without** calling
`super().mouseReleaseEvent` — otherwise Qt's release handling would reposition the
caret to the click point and undo the jump (and would re-emit `line_clicked` for
the wrong line). Ordinary releases (flag unset) keep today's behavior exactly:
`super()` then `line_clicked` for the clicked line.

Read-only (Caption Mode) is unaffected — moving the caret in a read-only
`QPlainTextEdit` is allowed; this is navigation, not editing.

### Target resolution (pure, reuses the cached spans)

Both targets are computed from the editor's cached structure
(`self._spans` / `self._spans_text`, kept fresh by `_rescan_structure` on
`textChanged` and revision-guarded exactly as `_update_matching_tag_highlight`
does) — no full re-scan on click. The `mousePressEvent` handler applies the same
staleness guard (`if document().revision() != self._spans_revision:
self._rescan_structure()`) before reading the cache, then calls two new Qt-free
functions in `xml_structure.py`:

```python
def matching_tag_target(spans, text, position) -> int | None:
    """Offset of the tag matching the one at `position`, or None.

    Resolve the enclosing element span. If `position` is within its opening-tag
    region (open_start <= position < open_end) return the closing tag's start
    (the '<' of '</name>', i.e. _closing_tag_start). If within its closing-tag
    region (close_start <= position < close_end) return span.open_start. Return
    None when the span is self-closing, has no closing tag, or `position` is not
    on either tag region (e.g. in text content or on an attribute value)."""

def parent_tag_target(spans, position) -> int | None:
    """open_start of the parent of the element enclosing `position`, or None
    when there is no enclosing element or it is top-level (no parent)."""
```

- `matching_tag_target` uses `enclosing_tag_span_from_spans(spans, position)`,
  the open/close-region test from `_update_matching_tag_highlight`, and the
  existing module-level `_closing_tag_start(text, span)` helper (promote it to a
  public `closing_tag_start` in `xml_structure`, or import it — implementer's
  choice; it currently lives in `xml_editor.py`). The pair it returns is exactly
  the pair the matching-tag highlight shows, so Ctrl+click and the highlight
  always agree.
- `parent_tag_target` uses `enclosing_tag_span_from_spans` then
  `parent_tag_span(spans, enclosing)` and returns `parent.open_start` — the same
  derivation as `select_parent_block`, minus the selection.

Both accept precomputed `spans` so the widget passes its cache and tests can pass
a freshly `scan()`-ed list. `matching_tag_target` also takes `text` because
locating the closing tag start needs the document string; `parent_tag_target`
needs only spans.

## Module boundaries

- **`xml_structure.py`** gains the two pure resolvers (and, if chosen, a public
  `closing_tag_start`). Qt-free, unit-tested in isolation — consistent with the
  existing `enclosing_tag_span` / `parent_tag_span` living there.
- **`xml_editor.py`** gains only the thin `mousePressEvent` override that maps the
  click, guards the cache, calls a resolver, and moves the caret. No new state.

## Testing

**Pure (`tests/ui/test_xml_structure.py`):**
- `matching_tag_target`: click in open tag → closing-tag start; click in close tag
  → open_start; self-closing → None; position in text content → None; position on
  an attribute value → None; nested element resolves to its own partner (not an
  ancestor's).
- `parent_tag_target`: nested element → parent `open_start`; deeper nesting → the
  immediate parent; top-level element → None; position outside any element → None.

**Widget (`tests/ui/test_xml_editor_click_nav.py`, offscreen Qt):**
- Load a small nested document; use
  `QTest.mouseClick(editor.viewport(), Qt.LeftButton, modifier, pos)` where `pos`
  is derived from `cursorRect()` of a known offset (so the hit point is
  deterministic). Assert the caret lands at the expected offset for Ctrl (open↔
  close) and Alt (parent start).
- **Alt+click leaves no selection** (`editor.textCursor().hasSelection()` is
  False) — proves the column-select default was suppressed.
- Plain left-click (no modifier) still positions the caret and emits
  `line_clicked` (existing behavior intact) — confirms the release-side flag does
  not disturb ordinary clicks.
- After a modifier-jump the caret stays at the target (a regression guard for the
  press/release interaction: the release must not drag the caret back to the
  click point).
- Ctrl+click in text content / on a self-closing tag is a no-op that falls through
  (caret goes where a normal click would; no crash).
- A `line_clicked` signal fires with the destination line on a successful jump
  (drive via `qtbot.waitSignal`).

No modals; all interactions are real synthetic mouse events or direct resolver
calls.

## Docs

Add one line to the manual's *The Raw XML Editor* section and two rows to the
*Keyboard Shortcuts* table (labelled as mouse shortcuts): Ctrl+click → jump to
matching tag; Alt+click → jump to parent tag.

## Delivery

One feature branch in a worktree off `main`; TDD; feature-tester run at completion
with a `docs/TEST_LOG.md` entry (per the testing policy); two-stage review;
`--no-ff` merge, then merge `main` into `re-phpgen`. Not pushed.
