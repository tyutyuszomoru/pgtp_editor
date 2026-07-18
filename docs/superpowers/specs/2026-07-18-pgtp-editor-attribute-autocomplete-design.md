# Ctrl+Space Attribute Autocomplete (with value chaining) — Design

**Date:** 2026-07-18
**Component:** Raw XML editor (`pgtp_editor/ui/xml_editor.py`), schema query
helpers (`pgtp_editor/schema_learning/settings_index.py`)

## Goal

In the Raw XML editor, pressing **Ctrl+Space** while the caret is inside an
opening tag pops up the attributes the schema knows for that element (minus the
ones already present). The user navigates with ↑/↓ and inserts the chosen one
with Tab/Enter as `name=""`, caret between the quotes. If that attribute has a
known set of values in the schema, a second popup immediately chains in to pick
the value too.

"The source must be the XSD": the XSD is generated from the in-memory schema
`Model`, so the completion reads that same model
(`model.paths[chain]["attributes"]`). No XSD file is parsed at runtime.

## Non-goals

- Element/tag-name completion (attributes only).
- Inline, as-you-type completion. Ctrl+Space is a discrete "show me the
  attributes" action; filter text is typed **into the popup**, never spliced
  into the document as a partial token (this sidesteps orphaned-prefix editing
  and keeps insertion identical to the existing `insert_attribute` behavior).
- Editing/curating the value set, multi-caret, or completion in Caption Mode
  (the editor is read-only there).

## Data source — pure helpers (`settings_index.py`)

Both are Qt-free and unit-tested against a synthetic model dict. They read the
same entry shape the rest of the module uses:
`{type, values, overflowed, attr_seen_count, labels, [kind]}`.

```python
def known_attributes(model, tag_chain, present_attrs) -> list[str]:
    """Sorted attribute names the schema records at ``tag_chain`` that the
    element does not already carry. Unlike ``unused_setting_attributes`` this is
    NOT filtered by kind — every attribute the model has seen for the element is
    offered (this is the broad list the XSD would show). ``present_attrs`` is a
    collection of names already on the tag. Unknown ``tag_chain`` -> []."""
```

- Implementation: `attributes = model.paths.get(tag_chain, {}).get("attributes", {})`;
  return `sorted(name for name in attributes if name not in set(present_attrs))`.

```python
def known_values(model, tag_chain, attr) -> list[tuple[str, str | None]]:
    """Sorted ``(value, label)`` pairs for an attribute's known value set at
    ``tag_chain`` — the same values ``enum_hint`` renders. ``label`` is
    ``labels.get(value)`` or ``None``. Returns [] when the attribute is unknown,
    ``overflowed`` is true, or ``values`` is absent/empty (nothing reliable to
    offer). Not kind-filtered: any enumerated attribute chains into the value
    picker, matching the user's ``editAbilityMode -> 0/2/3`` example."""
```

- Implementation: fetch entry; if `None`, `entry["overflowed"]`, or not
  `entry.get("values")` → `[]`; else `labels = entry.get("labels") or {}`;
  return `[(v, labels.get(v)) for v in sorted(entry["values"])]`.

## Resolver (reuses existing machinery)

`enclosing_open_tag(text, pos)` already returns
`(tag_chain, present_attrs, insert_pos)` for a caret inside an opening tag, or
`None` otherwise — exactly what both the trigger guard and the insertion need.
No new resolver is required; the popup filters by text typed into it, so there
is no partial-token scan of the document.

## UI — completion popup in `XmlEditor`

A single small frameless list widget class, `_CompletionPopup(QListWidget)`,
serves both stages (attribute list, then value list). It is a child of the
editor's viewport, shown non-modally with `show()` (never `exec()`), positioned
at the caret via `cursorRect()`. While visible it holds keyboard focus and
handles its own keys, emitting signals; the editor stays otherwise idle.

`_CompletionPopup` behavior:
- Holds the full candidate list plus a running filter string (starts empty).
- ↑/↓ move the selection (wrapping optional; no-wrap is fine).
- **Enter/Tab** → emit `chosen(str)` with the selected item's key.
- **Esc** (and focus-out) → emit `cancelled` and hide.
- Printable character → append to filter; **Backspace** → trim it; re-filter
  the list case-insensitively by prefix and re-render. Empty filtered list is
  allowed (popup shows nothing selectable; Esc closes).
- Mouse click on a row → same as choosing it.

`XmlEditor` additions:
- `keyPressEvent`: intercept **Ctrl+Space**. Guard: not `isReadOnly()`,
  `self._schema_model is not None`, and `enclosing_open_tag(...)` at the caret
  is not `None`. Then call `_show_attribute_completions()`. Anything failing the
  guard falls through to the base handler (Ctrl+Space is not a native binding).
- `_show_attribute_completions()` (seam, testable without real keys): resolve
  `enclosing_open_tag`; `items = known_attributes(model, tag_chain, present)`;
  if empty, brief status message and return; else populate the popup, preselect
  row 0, position at the caret, connect `chosen` → `_complete_attribute(name)`.
- `_complete_attribute(name)`: reuse the exact `_insert_attribute` splice —
  recompute `enclosing_open_tag` from the live buffer, insert ` name=""` at
  `insert_pos` in one `beginEditBlock`/`endEditBlock`, caret between the quotes.
  Then `values = known_values(model, tag_chain, name)`; if non-empty call
  `_show_value_completions(values)`, else leave the caret between the quotes.
- `_show_value_completions(pairs)` (seam): populate the popup with a display
  string per pair (`value` or `f"{value} = {label}"`) but carry the bare
  `value` as the chosen key; preselect row 0; position at the caret; connect
  `chosen` → `_complete_value(value)`.
- `_complete_value(value)`: insert `value` at the caret (which sits between the
  quotes) as one undoable edit; move the caret to just after the closing quote.
  Esc here leaves the value empty with the caret between the quotes.

Only one popup is live at a time; opening the value popup reuses the same widget
after the attribute stage closes.

## Model injection

Reuse the existing `set_schema_model(model)` / `self._schema_model` that already
feeds the hover tooltips. No new wiring in `MainWindow`.

## Testing

**Pure (`tests/.../test_settings_index*.py`):**
- `known_attributes`: returns all seen names minus present, sorted; unknown path
  → []; present set fully subtracted.
- `known_values`: `(value, label)` pairs sorted by value; label `None` when
  unlabeled; [] on unknown attr / `overflowed` / empty `values`.

**Widget (`tests/.../test_xml_editor*.py`, offscreen Qt, no modals):**
- Ctrl+Space with an injected synthetic model inside an opening tag opens the
  attribute popup with the expected (unused, sorted) items — driven with a real
  `QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)`.
- Guards: no model, read-only (Caption Mode), or caret in text/close-tag → no
  popup (assert popup not visible).
- Typing filters the attribute list; Backspace restores.
- ↓ then Tab (or `chosen` emission) inserts `name=""` at tag close, caret
  between quotes, single undo step (one Ctrl+Z reverts the whole splice).
- Chaining: completing an attribute that `known_values` covers opens the value
  popup; choosing a value inserts it between the quotes with caret after the
  closing quote; completing an attribute with no known values leaves the caret
  between quotes and opens no second popup.
- Esc dismisses each stage without mutating the buffer beyond what was already
  inserted.

All popup behavior is exercised through the `_show_*` seams and signal
emissions plus one real Ctrl+Space keypress; no `QDialog.exec()`/`QMessageBox`.

## Delivery

Single feature branch in a worktree off `main` (HEAD has the schema model,
`enclosing_open_tag`, `insert_attribute`, and `set_schema_model`). TDD, then the
two-stage review, then `git merge --no-ff`. Not pushed unless requested.
