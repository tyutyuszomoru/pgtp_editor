# Schema Settings Labeling + Editor Integration (Design)

## Goal

Turn the learned schema model into a practical aid for editing `.pgtp` files:
a person (an "intern") labels the generic PHP-Generator settings once
(`1 = modal`, `2 = new page`, …), and the Raw XML editor then surfaces those
labels on hover and offers settings-attributes that a given element doesn't yet
have. File-specific content (captions, names, hints) is kept out of the labeling
tool.

## Background (current state)

- `pgtp_editor/schema_learning/model.py` — `Model.paths[path]` where `path` is the
  slash-joined **tag chain** from the document root (e.g.
  `PGTPProject/Pages/Page/Editor`), no indices (confirmed in `parser.py`). Each
  path has `attributes[name] = {type, values:[...]|None, overflowed, attr_seen_count, labels:{}}`.
- Enum candidacy: an attribute is a labelable enum when `overflowed is False` and
  `values` is a non-empty list. `boolean`-typed attributes are excluded from
  labeling (true/false needs no label).
- `pgtp_editor/ui/annotate_schema_values_dialog.py` — current labeler; a flat
  table of every `(path, attribute, value)` enum triple. Problem: it mixes generic
  settings with file-specific content, so the list is noisy and off-purpose.
- `pgtp_editor/schema_learning/xsd_gen.py::generate_xsd(model) -> str`.
- `pgtp_editor/schema_learning/storage.py::schema_model_path()/schema_xsd_path()`.
- Schema menu (`main_window._build_schema_menu`) currently has only
  "Annotate Schema Values…".

## Shared foundation: the `kind` field

Add one field to each attribute entry: **`kind`** ∈ `"setting" | "content" | None`
(unclassified, the default). It is persisted in `schema_model.json`.

- The labeler is the **only writer** of `kind` and `labels`. The Schema Learning
  Engine (`model.py`) continues to own `type`/`values`/`overflowed`/
  `attr_seen_count` and must not write `kind`. New attributes are created without a
  `kind` key (treated as unclassified); readers use `entry.get("kind")`.
- Rationale: the manual mark (user's choice) is the authoritative, per-attribute
  setting-vs-content decision. Once marked `content`, an attribute is hidden from
  labeling and never surfaced by the editor integration.

A tiny reusable helper module keeps the classification/query logic pure and
testable, independent of Qt:

**`pgtp_editor/schema_learning/settings_index.py`** (new)
- `is_enum_candidate(entry) -> bool` — `not entry["overflowed"] and bool(entry["values"]) and entry["type"] != "boolean"`.
- `attribute_kind(entry) -> str` — returns `entry.get("kind") or "unclassified"`.
- `enum_hint(model, tag_chain, attr) -> str | None` — for the editor hover. Returns
  a one-line hint like `editFormMode — 1 = modal · 2 = new page · 3 = inline`
  (values sorted; `value = label` when a label exists, bare `value` otherwise),
  or `None` when the attribute isn't a labeled/labelable **setting** at that path.
  Only returns a hint when `attribute_kind == "setting"` AND (`labels` non-empty OR
  it is still an enum candidate). Never for `content`/`unclassified`.
- `unused_setting_attributes(model, tag_chain, present_attrs) -> list[str]` — for
  "offer keys". Attributes at `tag_chain` whose `kind == "setting"` and whose name
  is not in `present_attrs`, sorted.

The editor maps a cursor position to `tag_chain` by reading the ancestor open-tags
(reusing the tag-scanning already present in `xml_editor.py`).

---

## Phase 1 — Schema viewers (read-only windows)

**Menu:** add to the Schema menu:
- **Open XSD** → shows the XSD. Read from `schema_xsd_path()` if present, else
  generate on the fly via `generate_xsd(Model.load(...))`. If no model exists yet,
  show the friendly empty message instead of a window.
- **Open XSD Labels (JSON)** → shows the pretty-printed contents of
  `schema_model_path()` (the JSON as stored). Empty message if absent.

**Component:** `pgtp_editor/ui/schema_viewer.py`
- `SchemaViewerWindow(QMainWindow)` — a top-level, **non-modal** window hosting a
  read-only `XmlEditor` (reuse the existing widget; `setReadOnly(True)`). Methods:
  `set_content(text)`, window title set to the source label/path. No `.exec()`.
- `main_window` holds a reference to each opened viewer so it isn't garbage
  collected; opening again reuses/refreshes the same window.

**Data flow:** menu action → load-or-generate text → `viewer.set_content(text)` →
`viewer.show()`.

**Testing:** `open_xsd_text(storage_dir) -> str | None` and
`open_labels_text(storage_dir) -> str | None` are pure helpers (return `None` when
absent) so the load/generate logic is unit-tested without a window. A widget test
confirms the viewer is read-only and shows the text.

---

## Phase 2 — Redesigned labeler (the intern's tool)

Rework `AnnotateSchemaValuesDialog` into a two-pane workflow. `_build_rows` /
`_apply_filters` are replaced by attribute-level aggregation.

**Left pane — attributes.** One row per enum-candidate `(path, attribute)`:
- Columns: Element Path · Attribute · **Kind** (a combo: Unclassified / Setting /
  Content) · #values · #labeled.
- A **filter bar**: kind filter (All / Unclassified / Settings / Content) + a text
  box matching path/attribute (case-insensitive). Default view: **Unclassified +
  Settings** (content hidden), so the intern triages what's left.
- Changing the Kind combo writes `entry["kind"]` and re-saves immediately.

**Right pane — values of the selected Setting.** When the selected attribute's kind
is `setting`, show its observed values, each with an editable **Label** field
(pre-filled from `labels`). Editing writes `entry["labels"][value] = text` (or
removes it when cleared) and re-saves. When the selection is not a setting, the
right pane shows a hint ("Mark this attribute as a Setting to label its values").

**Persistence:** every change persists to `schema_model_path` via `Model.save`
(same as today). The module contract note is updated: it now writes `kind` and
`labels` only.

**Empty/malformed states:** unchanged from today (friendly empty message; error
box on malformed JSON). No `QMessageBox.exec` in tests — construction uses the
existing `_for_testing` path against an in-memory `Model`.

**Testing:** aggregation (`_build_attribute_rows(model)`), filtering
(`_filter_attribute_rows`), the kind-combo write-back, and the value-label
write-back are all driven by methods/data — no modal loop.

---

## Phase 3 — Editor value-hover

In `XmlEditor`, hovering over an attribute (name or value) inside an opening tag
shows a `QToolTip` with `enum_hint(model, tag_chain, attr)` when it returns text.

- The editor gets an injected reference to the current `Model` (or `None`). The main
  window passes the freshly-loaded model after each enrich; `None` disables hovers.
- Hover handling: an event filter / `event()` override on `QEvent.ToolTip` computes
  the character position under the cursor, identifies whether it's inside an opening
  tag and which attribute token it's on, derives the `tag_chain` from ancestor
  open-tags, and calls `enum_hint`. Shows `QToolTip.showText` with the hint, or
  hides it.
- Only **settings** produce hints (via `enum_hint`), so content/unclassified
  attributes never trigger a tooltip.

**Testing:** the position→(tag_chain, attr) resolver is a pure function
(`attribute_at_position(text, pos) -> (tag_chain, attr) | None`) tested on XML
strings; `enum_hint` is unit-tested; a light widget test wires a synthetic model
and asserts the resolver+hint path yields the expected string. Tooltips themselves
are not asserted via a real popup.

---

## Phase 4 — Offer unused keys

Right-click inside an element's opening tag in `XmlEditor` → **Add attribute ▸**
submenu listing `unused_setting_attributes(model, tag_chain, present_attrs)`.
Choosing one inserts ` name=""` just before the tag's closing `>` and places the
cursor between the quotes.

- If the model is `None` or the list is empty, the submenu is omitted (or shown
  disabled with a "no known settings" note).
- Insertion is a pure text transform `insert_attribute(text, tag_open_pos, name)
  -> (new_text, caret_pos)` so it's unit-testable; the widget layer applies it and
  sets the cursor.

**Testing:** `present_attrs`/`tag_chain` resolution reuses Phase 3's resolver;
`unused_setting_attributes` and `insert_attribute` are pure and unit-tested; a
widget test drives the context-menu callback (not a live popup) and asserts the
buffer + caret.

---

## Delivery & isolation

Each phase is a separate implementation plan → build → two-stage review → merge, so
it can be tested in the running app after each. Shared foundation
(`settings_index.py` + the `kind` field contract) lands with Phase 2 (Phase 1 needs
neither), but `settings_index.py` is introduced when first needed.

**Cross-cutting constraints**
- Modal-hang guardrail: no test may reach an unpatched `QMessageBox` /
  `QDialog.exec()` / `QFileDialog`. Viewers/labeler are non-modal and method-driven.
- Pure logic (`settings_index`, resolvers, text transforms) is Qt-free and unit
  tested; Qt layers stay thin.
- The Schema Learning Engine's ownership of `values`/`type`/`overflowed` is
  preserved; only the labeler writes `kind`/`labels`.

## Non-goals

- Auto-classification heuristics (user chose manual marking).
- Autocomplete-on-typing (Phase 4 is context-menu only; popup is a future item).
- Editing the xsd/labels from the viewer windows (read-only).
- Labeling boolean or overflowed (free-form) attributes.
