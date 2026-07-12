# PGTP Editor — Annotate Schema Values UI (Schema Learning Sub-project B of 2) Design Specification

**Date:** 2026-07-12
**Status:** Approved for planning
**Depends on:** [2026-07-11-pgtp-editor-design.md](2026-07-11-pgtp-editor-design.md) (original shell design), and the Schema Learning Engine sub-project (sub-project A of this feature area — vendors `pgtp_analytics/pgtp_schema/model.py` into `pgtp_editor/schema_learning/model.py`, and adds a `labels: dict[str, str]` key to each attribute entry, plus the per-user model file at `QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)/schema_model.json`). This document assumes sub-project A's `Model.load`/`Model.save` and its `labels` field exist exactly as specified there; it does not re-derive or re-justify them.

## 0. A note on how this document was produced

Every other spec in this repo (see e.g. the Diff/Merge Viewer UI spec's own closing section) was written up **after** an interactive brainstorming session where the user answered specific clarifying questions one at a time. This document is an exception: the user handed down the core intent directly —

> "The approach I'd like to have is to use each and every opened pgtp file to enrich the schema xsd. It might never be complete, but let's keep the possibility that one day we'll see a complete file. The goal is to improve the knowledge, therefore there should be a menupoint where users can give values to the enumerations. In July I'll have an intern for 2 weeks, I'll use her to fill in the gaps."

— but was **not** walked through the usual round of "where does this go in the menu / what layout / does it autosave" questions. Every concrete UI/UX decision below was therefore made directly by the implementing agent, exercising the same "reasonable, justified judgment call when unblocked" latitude this codebase's process already grants elsewhere. Nothing here is a guess dressed up as a decision — each choice is stated plainly with its reasoning, and every one of them is also collected in §6 ("Summary of decisions") exactly as if a human had been asked each question and had answered it, so a future reader can tell this was deliberate and reasoned, not an accident of implementation. If any of these calls turn out to be wrong once the intern actually starts using the tool, they are cheap to revisit — none of them lock in file formats or the underlying `labels` schema owned by sub-project A.

## 1. Context and scope

This is the second of two sub-projects that together deliver the **Schema Learning** feature area:

1. **Schema Learning Engine** (sub-project A, being written/implemented in parallel — not authored by this document) — vendors the existing `pgtp_analytics/pgtp_schema/model.py` learning logic into `pgtp_editor/schema_learning/model.py`, wires it to run on every successful `.pgtp` file open/parse (so the shared per-user model at `.../AppData/schema_model.json` accumulates observed paths, attributes, types, and distinct values across every file anyone has ever opened), and adds the `labels: dict[str, str]` key (observed value string → human-readable label string, defaulting to `{}`) to each attribute entry. Sub-project A's ingestion path (`merge_element`) never writes to `labels` — it only ever adds newly observed values to `values`. `labels` is written **only** by the UI this document specifies.
2. **Annotate Schema Values UI** (this document) — the menu point the user explicitly asked for: a dialog where a person browses every learned path/attribute/value combination and attaches a human-readable label to each observed value (e.g. `viewAbilityMode` value `"3"` → `"Modal window"`, matching the numeric-code-to-GUI-label mapping the original design spec's §2.4 flagged as "not yet known, must be derived empirically"). This is the tool the user intends to hand to a two-week summer intern to fill in gaps in the learned schema's labeling.

**Why this is a second, separate sub-project rather than folded into sub-project A:** sub-project A is pure data-model plumbing — it has no UI surface at all, and is fully testable against synthetic `merge_element` calls with no `QApplication` needed. This document is 100% UI and touches zero learning/ingestion logic. Keeping them separate mirrors the same reasoning the Diff/Merge feature area used to split its differ engine from its viewer UI: the engine (or here, the learning/storage layer) needs a settled, stable shape before a UI is designed against it, and UI work pulls in Qt-specific concerns (widget choice, editing mechanics, persistence timing) that have nothing to do with the data layer's own correctness.

**Why this matters now, not later:** the user's stated goal is specifically to have an intern spend two weeks of dedicated time filling in labels in July. That means the UI's actual day-to-day usability for *that* workflow — "find an unlabeled value quickly, type in what it means, move to the next one" — is the dominant design constraint here, more so than polish elsewhere in the app. Every judgment call below is weighed against that workflow first.

## 2. Scope

### 2.1 In scope

- A new dialog, `AnnotateSchemaValuesDialog` (`pgtp_editor/ui/annotate_schema_values_dialog.py`), reachable from a new top-level **Schema** menu (see §3.1) via **"Annotate Schema Values..."**.
- Loading the shared per-user `Model` from `QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)/schema_model.json` via `Model.load(path)` when the dialog is opened.
- A flat, filterable, sortable table view (see §3.2) listing one row per **labelable** (path, attribute, value) triple (see §3.5 for exactly which attributes qualify).
- A first-class **"Show only unlabeled"** checkbox filter, defaulting checked (see §3.2 and §3.3), directly serving the intern's "find the gaps" workflow.
- A free-text filter box that matches against element path and/or attribute name, to let someone jump straight to a known area of the schema (e.g. typing `AbilityMode` to see every `*AbilityMode` attribute across every path at once).
- Inline, in-place editing of the Label column directly in the table (see §3.3).
- Autosave of edits back to `schema_model.json` on every accepted edit (see §3.4) — no separate "Save" button, no explicit "Apply" step.
- A clear empty-state message when `schema_model.json` does not exist yet (see §3.6).
- Being available at all times from the Schema menu, regardless of whether a project is currently open in the main window (see §3.1).

### 2.2 Explicitly out of scope

- Anything in the Schema Learning Engine itself (sub-project A) — ingestion, `merge_element`, when/how the model file gets updated from opened `.pgtp` files, the `values`/`overflowed`/`attr_seen_count` bookkeeping. This document only ever calls `Model.load`/`model.save` and reads/writes the `labels` dict sub-project A defines.
- Any use of the labels once captured — e.g. surfacing them in tooltips elsewhere in the main editor UI, feeding them into a generated `.xsd` with `xs:documentation` annotations, or exporting/importing a labels-only file for sharing between machines. All plausible future features; none are requested or designed here. This dialog's only job is to let a human read and write `labels`.
- Editing anything other than `labels` from this dialog — `values`, `type`, `overflowed`, `attr_seen_count` are read-only context columns/tooltips at most, never editable here (sub-project A owns their correctness).
- Any bulk/multi-select label operations (e.g. "apply this label to all selected rows"). Each row's label is entered independently; see §6 for why this wasn't added preemptively.
- Undo/redo for label edits within this dialog. An edit is either the empty string (unlabeled) or a label string; correcting a mislabeled value is just editing the cell again. A full undo stack is not justified for a dialog whose only mutation is "set one string field."
- Concurrent-editing/multi-user conflict handling for `schema_model.json` (e.g. two people running the dialog on two machines against a shared network path). The model file is per-user/per-machine per sub-project A's design; this is not this document's concern.
- Localization of the labels themselves (e.g. entering the same label in multiple languages). A label is a single free-text string per value.

## 3. Design decisions

### 3.1 Menu placement: a new top-level "Schema" menu, not "Tools"

**Decision:** Add a new top-level menu, **Schema**, between **Diff / Merge** and **Tools** in the menu bar (`_build_menu_bar` in `main_window.py`), containing a single entry for now: **"Annotate Schema Values..."**.

**Reasoning:** Every existing entry in the `Tools` menu (`_build_tools_menu`: "Create Client (Readonly) Page...", "Move/Copy Detail...", "Manage Captions...", "Find Reused Tables...", "Validate Project") operates on **the currently-open project** — they take the loaded `ProjectModel` (or a selected node within it) as their subject. "Annotate Schema Values..." is categorically different: it operates on the **shared, cross-project, per-user learned schema model**, which exists independently of whatever `.pgtp` file (if any) happens to be open right now, and in fact aggregates data from every file anyone has ever opened on this machine, not just the current session's file. Placing it in `Tools` would put a project-independent action next to a list of project-dependent ones — the first time someone opens `Tools` with no project loaded and sees "Annotate Schema Values..." sitting enabled next to five other items that would need a project to make sense, it reads as an inconsistency (why is only one of these six things not greyed out?). A new `Schema` menu keeps that boundary explicit and gives the whole "Schema Learning" feature area a visible, named home in the menu bar for whatever else gets added to it later (e.g. a future "View Learned Schema Summary" or "Export Enriched XSD" entry would obviously belong here too, whereas they'd be awkward under `Tools`).

This also matches the precedent already set by `Diff / Merge` itself: that feature area got its own top-level menu (not folded into `Tools` or `File`) specifically because it's a distinct enough capability with its own multi-item workflow (Compare, Next/Prev Difference, Apply) to deserve a dedicated home, rather than being buried as one more `Tools` entry.

### 3.2 Widget layout: a flat, sortable, filterable table — not a path/attribute tree

**Decision:** Use a `QTableWidget` (or `QTableView` over a small custom model — see implementation note below) with four columns: **Element Path**, **Attribute**, **Value**, **Label**. One row per (path, attribute, value) triple. Above the table: a text filter box and a "Show only unlabeled" checkbox (default checked). All columns are sortable by clicking the header; the table starts sorted by Element Path, then Attribute, then Value (i.e. grouped visually even though it's a flat table, without the overhead of an actual tree).

**Reasoning — table over tree:** The real schema (`docs/schema.xsd`, 16,600+ lines) has hundreds of attributes spread across a deep path hierarchy, and a single attribute can have up to 10 distinct observed values (`ENUM_MAX_VALUES` in `model.py`) before it overflows out of consideration entirely (see §3.5). A tree grouped by path → attribute → value would need three levels of expand/collapse just to reach a single editable cell, and critically, **it would make "show only unlabeled" much harder to use well**: collapsing away everything-labeled while still being able to see which *paths* have remaining gaps means either an filter that hides whole tree branches (fine) or one that leaves oddly-pruned parents with only some children visible (confusing). A flat table sidesteps this entirely — filtering just removes rows, full stop, and the remaining rows are immediately scannable and directly editable without any expand/collapse interaction at all. Given the explicit design priority (intern productivity: find gaps fast, fill them in fast), a tree's main advantage — showing hierarchical structure — is not something the intern's workflow actually needs; she needs a worklist, not a structural map. Sorting by Element Path as the primary sort key still gives de facto grouping (all rows for one path/attribute end up adjacent) without forcing a tree's interaction model.

**Reasoning — "Show only unlabeled" as first-class, on by default:** This is explicitly called out as the core of the intern's job ("fill in the gaps"), so it is not a buried "advanced filter" — it is one checkbox, directly above the table, checked by default the moment the dialog opens. Unchecking it reveals already-labeled rows too, useful for reviewing/correcting previous work, but the default view a person sees the instant they open this dialog is exactly their to-do list.

**Implementation note:** A `QTableWidget` with one `QTableWidgetItem`-per-cell is simplest to get correct for a first version and is consistent with this codebase's stated preference (Diff/Merge Viewer spec, Project Tree) for using the plain widget-based Qt classes rather than introducing a custom `QAbstractTableModel` unless the row count genuinely demands it. Given realistic scale — even a schema with hundreds of attributes times up to 10 values each tops out at a few thousand rows — `QTableWidget` performance is not a concern; a custom model is not justified.

### 3.3 Editing mechanics: inline-editable Label cell, no side panel

**Decision:** The Label column's cells are directly editable in place (`Qt.ItemFlag.ItemIsEditable` on the Label column only; Element Path/Attribute/Value columns are read-only display). Double-click or F2/Enter on a Label cell opens it for text editing, exactly like any standard editable `QTableWidgetItem`; committing the edit (Enter, or clicking away — `itemChanged` firing after `closePersistentEditor`) saves it immediately (§3.4).

**Reasoning:** The alternative — select a row in a tree/table, then edit its label in a separate side-panel `QLineEdit` — adds a click-into-the-side-panel step and a context switch (eyes move from the row to a different part of the screen and back) for every single label entered. For someone doing dozens of these in a row, as the intern's workflow explicitly is, that's dozens of extra clicks and dozens of extra eye movements for zero benefit — there's no additional context a side panel would show that the row itself doesn't already contain (path, attribute, and the raw value are all sitting right there in the same row as the label being typed). Inline editing keeps the interaction to: click cell, type, press Enter/Tab, which also naturally chains into "Tab to move down and keep going," letting someone label a run of rows without ever reaching for the mouse. This is a clear win on the exact metric that matters most here (minimizing clicks/context-switches per label, per the task's own framing), and it is also simpler to implement correctly with Qt than a synchronized selection-to-side-panel wire-up.

Whole-row context (path + attribute + raw value) is not lost with inline editing since it's always visible in the same row, unlike a tree layout where a value's containing attribute/path might be scrolled off-screen.

### 3.4 Persistence timing: autosave on every committed edit, no explicit Save button

**Decision:** Every time a Label cell's edit is committed (the table widget's `itemChanged` signal fires for that cell), the in-memory `Model`'s corresponding `labels[value] = new_label` is updated and `model.save(path)` is called immediately, writing the full `schema_model.json` back to disk right then. There is no "Save"/"Apply" button in this dialog at all — closing the dialog (or the whole app) never risks losing an edit, because every edit is already durable the moment it's typed.

**Reasoning:** This is a data-loss-risk-versus-annoyance tradeoff, and it comes down clearly on the "avoid data loss" side for this specific workflow: the entire point of this sub-project is to support an intern spending two dedicated weeks typing in potentially hundreds of short label strings, one at a time, likely with the dialog left open the whole time across many short sessions (a few labels, switch to check a reference doc, come back, a few more labels...). A crash, an accidental window close, a laptop sleep/wake hiccup, or simply forgetting to click Save before closing would be uniquely painful here — unlike the Diff/Merge viewer's Apply/Skip checkboxes (explicitly *not* persisted, by design, because they're meaningless outside one comparison session), a label is exactly the kind of small, permanent, cumulative fact this whole feature exists to accumulate. Losing a batch of an intern's typed labels because of a missed Save click would directly undermine the stated goal ("improve the knowledge... it might never be complete, but let's keep the possibility that one day we'll see a complete file"): the file is supposed to only ever grow more complete, never regress by accident.

The performance cost is negligible: `schema_model.json` is a JSON document sized to "hundreds of attributes, ≤10 values each," not a multi-megabyte file, so a full rewrite on every single-field edit is effectively instantaneous and not something the person editing will ever perceive as a delay.

### 3.5 Which attributes are shown: enum-candidate attributes only, booleans excluded

**Decision:** A row is only generated for an attribute entry where `overflowed is False` and `values` is a non-empty list (i.e. it is still a genuine enum candidate — see `model.py`'s `merge_element`: `overflowed` flips `True` and `values` becomes `None` once more than `ENUM_MAX_VALUES` (10) distinct values have been observed). Within that filter, attributes with `type == "boolean"` are **excluded entirely** from the dialog — they never generate rows, even though `"true"`/`"false"` are technically two discrete enumerable values.

**Reasoning — excluding overflowed attributes:** An overflowed attribute has no `values` list at all (`None`) — there is nothing concrete to attach a label to, and no realistic way to iterate "all observed values" for it since sub-project A intentionally stopped tracking them once the count passed 10. These are almost certainly free-form fields (captions, file names, SQL fragments) rather than coded enums, which is exactly the case `ENUM_MAX_VALUES` exists to detect and stop collecting. Showing them here would either require inventing a different UI for "attach a label to an attribute with no bounded value set" (out of scope — this dialog is specifically for enumerations, per the user's own framing: "give values to the enumerations") or showing a row with no meaningful Value cell to label, which would only confuse the intern about what she's supposed to be doing.

**Reasoning — excluding booleans:** `"true" → "true"` and `"false" → "false"` is not information — it's a restatement of the raw value with zero interpretive value added, unlike `viewAbilityMode` value `"3"`, where the label `"Modal window"` genuinely decodes an opaque integer into something a human can understand. Including booleans "for completeness" would add real rows to the intern's worklist (every boolean attribute times 2 possible values) that take zero domain knowledge to fill in and add zero value once filled in — pure noise against the stated goal of making good use of two weeks of a dedicated person's time on the *actually opaque* codes. If a future need arises to label booleans with something more meaningful than "true"/"false" (e.g. a domain-specific gloss), that would be a deliberate, separate ask, not something this dialog should default into showing.

### 3.6 Availability without an open project, and empty-state UX

**Decision (availability):** The "Annotate Schema Values..." menu action is **always enabled**, with no dependency on `MainWindow._current_project` being non-`None`. It is reachable identically whether zero, one, or many `.pgtp` files have ever been opened in the current app session.

**Reasoning:** Stated explicitly per the task framing, but worth spelling out rather than leaving implicit: the learned schema model is accumulated across *every* `.pgtp` file ever opened on this machine (via sub-project A's ingestion, which runs as a side effect of `open_project_file`), not tied to whatever happens to be the currently-open project right now. Gating this menu action on "a project is currently open" would be actively wrong — someone should be able to open the app fresh, without opening any file at all, and still review/label everything the model has already learned from *previous* sessions. The only thing that could ever be legitimately empty is the model file itself (see below), not the current session's open/closed state.

**Decision (empty-state UX):** On dialog open, if `Model.load(path)` fails because the file does not exist (`FileNotFoundError`), the dialog shows a single centered message in place of the table — **"No schema data yet. Open a .pgtp file to begin learning the schema, then come back here to annotate it."** — with the filter controls and table hidden (not shown empty/greyed, since an empty table with visible filter controls invites confusion about whether the filter itself is hiding everything). Once at least one `.pgtp` file has been opened in any session, `schema_model.json` will exist (per sub-project A) and this message will never appear again for that user; the dialog is otherwise reusable/re-openable indefinitely as more values get learned and labeled over time.

**Reasoning:** A blank table with column headers and no rows (which is what would happen if the dialog just proceeded with an empty `Model`) reads as broken or as "the filter is hiding everything," not as "this is a fresh install." An explicit, actionable message removes that ambiguity and tells the person exactly what to do next (go open a file first), which matters especially for the intern's very first day using this tool before anyone has necessarily walked her through the whole pipeline.

Any other load failure (e.g. malformed/corrupted JSON) is treated as a hard error via `QMessageBox.critical`, matching the existing `_open_project`/`open_project_file` failure-reporting convention elsewhere in this codebase — never a silent fallback to an empty model, since that could silently mask real data corruption.

## 4. Architecture

### 4.1 Module layout

```
pgtp_editor/
├── schema_learning/
│   ├── __init__.py
│   ├── model.py                        # unchanged in this document — owned by sub-project A
│   └── ...                             # (ingestion wiring, also sub-project A)
├── ui/
│   ├── main_window.py                  # gains _build_schema_menu, a new top-level "Schema" menu
│   │                                    # entry, and _open_annotate_schema_values handler
│   └── annotate_schema_values_dialog.py # NEW: AnnotateSchemaValuesDialog
```

### 4.2 `AnnotateSchemaValuesDialog`

A `QDialog` (non-modal is preferable — see note below — but `QDialog.exec()` modal is also acceptable and is the simpler default; the important behavioral point is that it does not block re-opening the main window's other menus in a way that would stop someone from opening a `.pgtp` file to feed the model while deciding what to look up). For the initial version, a standard modal `QDialog` is sufficient and simplest to implement correctly; non-modal is a low-cost future enhancement if it turns out someone wants to open a file and annotate at the same time, not a requirement now.

**Row construction** (`_build_rows(model)`):

```python
def _build_rows(model):
    rows = []
    for path in sorted(model.paths):
        attributes = model.paths[path]["attributes"]
        for attr_name in sorted(attributes):
            entry = attributes[attr_name]
            if entry["overflowed"] or not entry["values"]:
                continue
            if entry["type"] == "boolean":
                continue
            labels = entry.get("labels", {})
            for value in sorted(entry["values"]):
                rows.append({
                    "path": path,
                    "attribute": attr_name,
                    "value": value,
                    "label": labels.get(value, ""),
                })
    return rows
```

`entry.get("labels", {})` (rather than `entry["labels"]`) is a defensive read, not a design decision of consequence: sub-project A's spec states `labels` defaults to `{}` on every attribute entry, so in practice it will always be present once sub-project A is merged; the `.get(..., {})` guards only against a stale `schema_model.json` written before sub-project A's change landed, and costs nothing.

**Filtering** (`_apply_filters(rows, text_filter, unlabeled_only)`): re-runs on every keystroke in the text filter box and every toggle of the "Show only unlabeled" checkbox. Text filter matches case-insensitively against `path` and `attribute` (not `value` or `label` — someone hunting for "every `*AbilityMode` attribute" is searching by name, not by value, and matching against values too would risk false-positive matches when a value string happens to contain the filter text, e.g. filtering "3" would otherwise match every row whose *value* happens to be "3" in unrelated attributes). `unlabeled_only` keeps rows where `label == ""`.

**Editing and autosave** (`_on_item_changed(item)`): connected to the table's `itemChanged` signal, filtered to the Label column only (checking `item.column() == LABEL_COLUMN`, since `itemChanged` also fires during programmatic table population unless guarded — the standard Qt pattern of temporarily disconnecting the signal during `_build_rows`-driven population, or checking a `self._populating` guard flag, is used to avoid spurious saves while the table is being (re)built):

```python
def _on_item_changed(self, item):
    if self._populating or item.column() != LABEL_COLUMN:
        return
    row = item.row()
    path = self.table.item(row, PATH_COLUMN).text()
    attr = self.table.item(row, ATTRIBUTE_COLUMN).text()
    value = self.table.item(row, VALUE_COLUMN).text()
    new_label = item.text()
    entry = self._model.paths[path]["attributes"][attr]
    entry.setdefault("labels", {})
    if new_label:
        entry["labels"][value] = new_label
    else:
        entry["labels"].pop(value, None)
    self._model.save(self._model_path)
```

Setting a Label cell back to an empty string removes the key from `labels` entirely (rather than storing `""`), so `labels.get(value, "")` and "is this value labeled" stay a simple truthy check everywhere else that ever reads this data (e.g. a future XSD-annotation consumer), matching the same "absence means no value" convention `values`/`overflowed` already use elsewhere in `model.py`.

**Model path resolution:**

```python
from PySide6.QtCore import QStandardPaths
import os

def _schema_model_path():
    app_data_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return os.path.join(app_data_dir, "schema_model.json")
```

This must resolve to the exact same path sub-project A's ingestion writes to, since both sides read/write the same file — this document does not introduce a second, independent path constant; if sub-project A exposes a shared helper for this path (likely, to avoid duplicating the `AppDataLocation` lookup in two places), this dialog uses that helper rather than re-deriving the path itself.

### 4.3 Menu wiring (`main_window.py`)

```python
def _build_schema_menu(self):
    menu = self.menuBar().addMenu("Schema")
    annotate_action = menu.addAction("Annotate Schema Values...")
    annotate_action.triggered.connect(self._open_annotate_schema_values)

def _open_annotate_schema_values(self):
    dialog = AnnotateSchemaValuesDialog(self)
    dialog.exec()
```

Added to `_build_menu_bar` between `_build_diff_merge_menu()` and `_build_tools_menu()`:

```python
def _build_menu_bar(self):
    self._build_file_menu()
    self._build_edit_menu()
    self._build_view_menu()
    self._build_diff_merge_menu()
    self._build_schema_menu()
    self._build_tools_menu()
    self._build_generation_menu()
    self._build_help_menu()
```

No dependency on `self._current_project` anywhere in this wiring, per §3.6 — the action is unconditionally enabled.

## 5. Testing strategy

- **`pytest-qt` tests for `_build_rows`/row-filtering logic**, driven against synthetic `Model` instances built directly in test code (no real `.pgtp` files, no file I/O) — covering:
  - An attribute with `overflowed=True` (or `values=None`) never produces a row.
  - An attribute with `type == "boolean"` never produces a row, even with non-overflowed `values`.
  - An attribute with non-overflowed, non-boolean `values` produces one row per distinct value, each row's `label` reflecting `entry["labels"].get(value, "")`.
  - Text filter matching against path/attribute (case-insensitive), and specifically *not* matching against value/label content.
  - "Show only unlabeled" hides rows where `label != ""` and shows rows where `label == ""`.
- **`pytest-qt` tests for inline editing and autosave**, against a real (temp-directory) `Model.save`/`Model.load` round trip:
  - Editing a Label cell and committing it updates `entry["labels"][value]` in the in-memory model.
  - The same edit triggers a `model.save(path)` call whose written JSON, when reloaded via `Model.load`, reflects the new label (a genuine round-trip check, not a mock assertion that `save` was merely called).
  - Clearing a Label cell back to empty removes the key from `labels` rather than storing an empty string.
  - Programmatic table population (`_build_rows` → populating the table) does not itself trigger a save (the `_populating` guard works).
- **Empty-state test:** constructing the dialog against a `model_path` that does not exist shows the empty-state message and hides the table/filter controls; no exception is raised, no `QMessageBox.critical` is shown (this is the expected/handled case, not an error).
- **Malformed-file test:** constructing the dialog against a `model_path` pointing at a file containing invalid JSON shows `QMessageBox.critical` (matching `open_project_file`'s existing failure-reporting convention) rather than silently falling back to an empty model.
- No test in this suite depends on `pgtp_editor/schema_learning/model.py`'s ingestion logic (`merge_element`) — all fixtures construct `Model` instances (or their `paths` dict) directly, keeping this sub-project's tests independent of sub-project A's own test suite, consistent with the two sub-projects' clean dependency boundary (this document only ever calls `Model.load`/`model.save`, plus reads/writes the `labels` dict).

## 6. Summary of decisions

This document was written without an interactive brainstorming round (see §0); the following is the same "summary of decisions" a normal spec in this repo would carry, except each entry here also stands in for the clarifying question that would ordinarily have been asked and answered:

1. **Menu placement — new top-level "Schema" menu, not folded into "Tools."** Every existing `Tools` entry operates on the currently-open project; this feature operates on the shared, cross-project, per-user learned model instead, and is available with no project open at all. Mixing a project-independent action into `Tools` would read as inconsistent the moment someone opens `Tools` with nothing loaded. A new menu also gives the whole Schema Learning feature area a natural home for anything added to it later.
2. **Layout — flat, sortable, filterable `QTableWidget`, not a path/attribute/value tree.** A tree would force multiple levels of expand/collapse to reach an editable cell and would make the "show only unlabeled" filter behave awkwardly (pruned parents, partially-visible branches). A flat table lets filtering simply remove rows, and default-sorting by Element Path still gives visual grouping without a tree's interaction overhead. Given the priority (an intern working through a worklist, not exploring structure), the table's simplicity wins clearly.
3. **"Show only unlabeled" is a first-class, on-by-default checkbox**, not a buried option — it directly is the intern's job description ("find unlabeled values and fill them in quickly"), so it's the default view the dialog opens to.
4. **Editing — inline, in-place editable Label cells**, not a select-row-then-edit-in-a-side-panel design. A side panel adds a click-in and a context switch per label; inline editing supports a fast Enter/Tab-to-next-row rhythm for someone entering dozens of labels in a row, which is exactly the stated workflow. It's also simpler to implement correctly in Qt (standard editable `QTableWidgetItem` behavior) than wiring a synchronized side panel.
5. **Persistence — autosave on every committed edit, no Save/Apply button.** The workflow this exists for (an intern spending two dedicated weeks typing labels, likely across many short on/off sessions) makes data-loss risk the dominant concern, not the minor overhead of writing a small JSON file on every edit. Losing typed work to a missed Save click would directly undercut the feature's own stated goal of monotonically improving the learned schema's completeness.
6. **Attribute filtering — only non-overflowed enum-candidate attributes are shown, and boolean-typed attributes are excluded entirely**, even though `true`/`false` are technically two discrete values. Overflowed attributes have no bounded value set left to label (`values` is `None`); booleans need no interpretive label (`"true" → "true"` adds nothing) and including them would just add noise to the intern's worklist for zero benefit.
7. **Availability — always enabled, independent of whether a project is currently open.** The learned model is accumulated across every file ever opened on the machine, in any session; gating this menu action on "a project is open right now" would be actively wrong, since the whole point is reviewing/labeling knowledge gathered from *past* sessions too.
8. **Empty-state UX — an explicit, actionable message ("No schema data yet. Open a .pgtp file...") replacing the table entirely** when `schema_model.json` doesn't exist yet, rather than showing a blank table with visible-but-empty rows/filters, which would read as broken rather than "fresh install." Any other load failure (e.g. corrupted JSON) is a hard `QMessageBox.critical` error, matching the existing `open_project_file` convention, never a silent empty-model fallback.
9. **No bulk/multi-row label operations, no undo stack, no cross-machine label export/import, no surfacing of labels elsewhere in the app (e.g. tooltips, generated-XSD annotations) in this sub-project.** All plausible future extensions once the core labeling workflow proves out, but none were requested, and adding them now would be scope creep against a document whose only asked-for job is "a menu point where users can give values to the enumerations."
10. **A `QDialog` (modal is acceptable for the initial version) rather than a dockable panel.** This is a focused, occasional-use tool (most heavily used during the intern's two weeks, then periodically afterward as new files get opened and new values get learned) rather than something that needs to stay visible alongside the main editing surface at all times — a dialog is the simpler, lower-footprint choice, consistent with how other one-off management tasks in this codebase (e.g. the stubbed "Manage Captions..." entry) are expected to be dialog-shaped rather than permanent docked panels.
