# Caption Management — Design

**Date:** 2026-07-13

Supersedes the original §6.3 "Caption Management (unified coherence audit + translation)" of `docs/superpowers/specs/2026-07-11-pgtp-editor-design.md` with a simpler, line-anchored model. Translation (Claude) is explicitly deferred to a follow-up.

## 1. Purpose

Give the user a fast way to review and edit every user-facing caption-like string in the active project in one place — an Excel-style, filterable grid — without hunting through the raw XML. The key simplification: while Caption Management is active, the Raw XML is **frozen** (hidden, not editable), so every string's **line number stays valid for the whole session** and edits can be written back to exact lines with no re-scan and no anchor ambiguity.

## 2. Scope

**In scope**
- A pure, Qt-free scan/apply core: `scan_captions(text) -> list[CaptionEntry]` and `apply_caption_edits(text, edits) -> str`.
- A filterable, Excel-like grid panel (`CaptionManagementPanel`) hosted in the reserved "Caption Management" center-stage tab.
- Mutually-exclusive editing surfaces: Raw XML is the default working tab; entering Caption Management hides Raw XML and freezes its text; Apply/exit restores Raw XML with the edited text.
- Apply writes edits **in memory only** — into the Raw XML editor buffer. No disk write, no `.bak` (persistence is the user's existing File→Save/Save As or Generate's Save, built elsewhere).

**Out of scope (deferred / not built here)**
- **Translate via Claude** (bulk LLM translation) — a follow-up sub-project that will reuse this grid + line-anchored apply.
- Grouped coherence view / "pick one canonical value" (the original §6.3 grouped UI). This cut is a flat editable grid; anchors are shown and inconsistent groups are *highlighted*, but nothing forces grouping.
- Disk persistence, `.bak`, cross-file scanning.
- Auto-reparsing the tree after Apply (the user can use the existing Tools → Reparse Raw XML into Tree).

## 3. Caption-like attributes

The scan collects these attributes wherever they appear on any element (the §6.3 set):
`caption`, `shortCaption`, `headerHint`, `insertFormCaption`, `groupName`.

(These occur on `Page`, `Detail`, `OnTheFlyInsertPage`, `ColumnPresentation`, `Value`, and menu/group elements. The scan is attribute-driven, not element-whitelisted, so any element carrying one of these attributes contributes rows.)

## 4. Pure core — `pgtp_editor/ui/caption_scan.py` (Qt-free, unit-tested)

### 4.1 `CaptionEntry`
A frozen dataclass:
- `line: int` — 1-based line the attribute sits on (the element's `sourceline`).
- `element_tag: str` — e.g. `"ColumnPresentation"`, `"Page"`, `"Detail"`.
- `anchor: str` — a human-readable context/coherence key: the element's `fieldName` if present (columns), else `fileName`, else `tableName`, else the element tag. Used for the Anchor column and inconsistency highlighting only; it is **not** used for write-back.
- `attribute: str` — one of the caption-like attribute names.
- `value: str` — the **decoded** (unescaped) current attribute value, as lxml returns it.

### 4.2 `scan_captions(text) -> list[CaptionEntry]`
- Parse `text` with lxml (reuse the model layer's tolerant read path if convenient, but a plain `etree.fromstring`/`etree.parse` on the in-memory text is fine here; this operates on the frozen editor text). If the text is not well-formed, return `[]` (Caption Management is only entered on a parsed project; malformed text is handled by the existing parse-failure path, not here).
- Walk **all** elements in document order (`root.iter()`); for each, for each caption-like attribute present (in the fixed §3 order), emit one `CaptionEntry`. Result is ordered by document position then by the fixed attribute order, so a line with `caption`+`shortCaption`+`groupName` yields three consecutive rows.
- `sourceline` is always populated by lxml for parsed elements; skip (do not emit) any element whose `sourceline` is `None` (defensive; not expected).

### 4.3 `apply_caption_edits(text, edits) -> str`
- `edits` is an iterable of `(entry, new_value)` (or an equivalent structure carrying `line`, `attribute`, `new_value`) for **changed** rows only.
- For each edit, operate on the single source line `text.splitlines(keepends=True)[line-1]` and replace that attribute's value:
  - Match with a regex anchored so the attribute name cannot match the tail of a longer name (critical: `caption` must NOT match inside `shortCaption`/`insertFormCaption`). Use a negative-lookbehind on a word char, e.g. `(?<![\w-])<attr>="[^"]*"`, with `re.escape(attr)`, `count=1`.
  - The replacement is `<attr>="<escaped_new_value>"`, where the new value is XML-attribute-escaped for a double-quoted attribute: `&` → `&amp;`, `<` → `&lt;`, `>` → `&gt;`, `"` → `&quot;` (apply `&` first). `.pgtp` attributes use double quotes.
  - If the pattern does not match on that line (defensive — attribute unexpectedly absent), leave the line unchanged (the caller may surface this, but it must not crash or corrupt).
- Reassemble and return the full text. Unedited lines are byte-for-byte unchanged. This relies on the .pgtp convention (verified) that an element's opening tag — and therefore all its attributes — is on a single line (`sourceline`).

## 5. Grid panel — `pgtp_editor/ui/caption_management_panel.py`

- `CaptionManagementPanel(QWidget)` built around a `QTableView` + a `QAbstractTableModel` (or `QStandardItemModel`) fed through a `QSortFilterProxyModel`.
- Columns: **Line · Element · Anchor · Attribute · Value**. Only **Value** is editable (`Qt.ItemIsEditable` on that column only; the rest are read-only). Headers are sortable.
- **Filtering (Excel-like):** a row of `QLineEdit` filter inputs across the top, one per column; typing filters the visible rows (case-insensitive substring) via the proxy. (A multi-column filter proxy: subclass `QSortFilterProxyModel.filterAcceptsRow` to AND all per-column filters.)
- **Inconsistency highlight:** rows sharing the same `(anchor, attribute)` but with differing values are tinted (e.g. a subtle background) so incoherent captions stand out. Purely visual; no grouping behaviour.
- **Dirty tracking:** editing a Value cell marks that row changed (only rows whose value differs from the original are emitted to `apply_caption_edits`).
- **`load_entries(entries)`** populates the model from a scan. **`apply()`** returns the changed edits (or invokes an injected `on_apply(edited_text)` callback with the result of `apply_caption_edits`). Keep the panel decoupled from `MainWindow` via injected callbacks, matching the `FindReplaceBar` pattern.
- Buttons: **Apply** (commit edits to the in-memory Raw XML buffer) and **Close** (leave caption mode, restoring Raw XML). Apply then Close is the normal flow; Close without Apply discards pending edits.

## 6. Mode integration

### 6.1 Default tab visibility (small change from today)
Raw XML becomes the **default-visible** working tab. Diff/Merge and Caption Management tabs are hidden until invoked (Diff/Merge is revealed by the existing Compare/Merge entry points; Caption Management by the Tools action below). Existing `center_stage`/menu tests that assert the old default tab set must be updated accordingly (do not weaken — update to the new intended default).

### 6.2 Entering / leaving caption mode (`MainWindow`, wired to Tools → Manage Captions…)
- **Enter** (`Manage Captions…`, currently a stub): require an open project / non-empty Raw XML (else an info message). Snapshot the current Raw XML text; `scan_captions` it; `load_entries` into the panel; **hide the Raw XML tab**; reveal + switch to the Caption Management tab.
- **Apply:** compute `apply_caption_edits(snapshot, changed_edits)`; set the result as the Raw XML editor's text (in memory). The snapshot for further edits in the same session updates to the applied text (line numbers still valid — the applied text has the same line structure, since only in-line attribute values changed). A status-bar message reports how many captions were updated.
- **Close / leave:** restore Raw XML tab visibility and switch to it; hide the Caption Management tab. If there are unapplied edits, either discard (Close) — a confirm prompt is optional and, if added, MUST be patched in tests to avoid a modal hang.

## 7. Error handling / edge cases
- Malformed frozen text → `scan_captions` returns `[]` (caption mode is only entered from a parsed project; this is defensive).
- A line whose attribute can't be matched at apply time → that edit is skipped, others still apply; never crash or corrupt other lines.
- Values containing `&`, `<`, `>`, `"` → correctly re-escaped on write-back; round-trip a value through decode→edit→encode must preserve non-edited characters.
- Empty edit set → Apply is a no-op producing identical text; status message reports 0.

## 8. Testing
- **`caption_scan.py` (pure, no Qt):**
  - Multi-attribute line yields one row per attribute in fixed order (e.g. a `<Page>` line with `caption`+`shortCaption`+`groupName` → 3 rows, correct lines/values).
  - `caption` is not confused with `shortCaption`/`insertFormCaption` on apply (the lookbehind boundary): editing `caption` on a line that also has `shortCaption` changes only `caption`.
  - XML escaping round-trip: a value edited to include `&`/`<`/`"` is written back escaped and re-parses to the intended string; unedited attributes on the same line are byte-identical.
  - Empty/edit-nothing → identical text; malformed text → `[]`.
  - Anchor resolution (fieldName for columns, fileName/tableName otherwise).
  - Real-sample smoke (skip if `sample/*.pgtp` absent): scan `dev_Ferrara.pgtp`, assert a known caption row exists at its real line; apply a change and re-scan to confirm it took.
- **`CaptionManagementPanel` (pytest-qt):** only Value editable; per-column filter narrows visible rows; sort works; dirty-edit → `apply()` emits exactly the changed rows; inconsistency highlight fires for a divergent `(anchor, attribute)` group.
- **`MainWindow` (pytest-qt):** Manage Captions… enters mode (Raw XML hidden, Caption tab shown, grid populated from the snapshot); Apply writes the edited value into the Raw XML buffer and reports the count; Close restores Raw XML. Default tab visibility (Raw XML shown, others hidden) asserted. Any modal (e.g. an optional discard-confirm) MUST be patched.
- The suite runs headless offscreen with the `--timeout=60` guard; no feature here should reach an unpatched modal.

## 9. Components / isolation
- `caption_scan.py` — pure logic (scan + apply), no Qt. The riskiest correctness lives here and is fully unit-tested.
- `caption_management_panel.py` — the grid widget; depends on the core + Qt; decoupled from MainWindow via injected callbacks.
- `center_stage.py` — hosts the panel in the Caption Management tab; owns the Raw-XML ↔ Caption-Management visibility swap; sets Raw XML as the default-visible tab.
- `main_window.py` — Tools → Manage Captions… action; snapshot/scan/enter, Apply (write-back to editor buffer + status), Close/restore.
