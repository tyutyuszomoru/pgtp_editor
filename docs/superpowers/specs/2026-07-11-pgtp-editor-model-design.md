# PGTP Editor — Real Model (Sub-project 1 of 3) Design Specification

**Date:** 2026-07-11
**Status:** Approved for planning
**Depends on:** [2026-07-11-pgtp-editor-design.md](2026-07-11-pgtp-editor-design.md) (original shell design), the completed shell implementation, and the Canvas/Treeview follow-ups already merged into `worktree-pgtp-editor-combined`.

## 1. Context and scope

This is the first of three sequential sub-projects that together deliver a **Properties panel** (read-only: shows everything phpgen lets you set on the selected object, click a property to jump to where it's set in the raw XML — not an editor). The three sub-projects, in dependency order:

1. **Real model** (this document) — parse a real `.pgtp` file with `lxml`, replacing the placeholder tree data.
2. **Real Raw XML display** — the currently-empty Raw XML tab shows the loaded file's actual text, with scroll-to-line/highlight capability.
3. **Properties panel itself** — depends on both 1 and 2.

This document covers only sub-project 1. Sub-projects 2 and 3 get their own brainstorm/spec/plan cycles once this one is built and merged.

**Why this is more than "add a Properties panel":** building Properties meaningfully requires real data to point at. The shell's tree currently reads from a hardcoded `PLACEHOLDER_PROJECT` dict with a couple of fake fields per node — nowhere near "everything phpgen lets you set." This sub-project replaces that with a real, `lxml`-backed parse of an actual `.pgtp` file, which is exactly the "model" layer the original shell design spec explicitly deferred to a future phase (§4.2 of the original design doc). Two real sample files already exist in `sample/` (`dev_Ferrara.pgtp`, `Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp`) to parse against.

## 2. Scope

### 2.1 In scope

- A new `pgtp_editor/model/` package: `parser.py` (`load_project(path) -> ProjectModel`) and `nodes.py` (data objects for parsed Page/Detail/Column/Event nodes).
- Parsing exactly the four element kinds the tree already displays: `Page`, `Detail` (recursively — a Detail wraps its own nested `Page`), `ColumnPresentation` (→ Column nodes), and `EventHandlers` children (→ Event nodes). `DataSources`, `Groups`, and `Partitions` are explicitly deferred — the tree doesn't show them today, so there's no consumer for that data yet.
- Each parsed node carries: an **identity key** (per the scheme already designed in the original spec — `Page` by `fileName`, `Detail` by parent identity + `tableName`, `ColumnPresentation`/Column by parent identity + `fieldName`), **every attribute on that element** as a plain dict (`dict(element.attrib)` — generic capture, not a curated subset, so "every detail phpgen lets you set" is satisfied without the model needing updates every time a new property needs exposing), and the element's `sourceline` (from `lxml`, free to obtain).
- Event nodes additionally get a classified `side` (`"S"` or `"C"`) using the authoritative event-name list now on record (9 client-side, 31 server-side — see the project's memory for the full list), defaulting to server-side (`"S"`) for any event tag not in the known client-side set.
- `ProjectTreePanel` gains a way to populate itself from a `ProjectModel` (same `(P)`/`(D)`/`(C)`/`(E)` display format already built — only the *data source* changes, not the tree's shape, display logic, or context-menu behavior).
- `File → Open` becomes real: a `QFileDialog` (filtered to `*.pgtp`), calling `load_project`, then repopulating the tree from the result. Every other File menu action stays stubbed.
- `PLACEHOLDER_PROJECT` is deleted from `project_tree.py` — superseded, not kept as a fallback. On startup (nothing opened yet), the tree is genuinely empty.
- Parse-failure handling: a malformed file surfaces a clear error (via the same Tier-1 validation approach from the original design), never a crash or a silently-empty tree.

### 2.2 Explicitly out of scope (this sub-project)

- The Raw XML tab actually showing text, or any scroll-to-line/highlight navigation logic. `sourceline` is captured now because it's free during parsing, but nothing *consumes* it yet — that's sub-project 2's job.
- The Properties panel itself (sub-project 3).
- `DataSources`, `Groups`, `Partitions` parsing.
- Any File menu action other than Open (New Project, Save, Save As, Close all remain stubbed).
- Editing/writing `.pgtp` files — this is a read-only parse.
- Diff/merge, move/copy, caption management, client-page generation, PHP Generator invocation — all still future work per the original design spec's roadmap.

## 3. Architecture

### 3.1 Module layout

```
pgtp_editor/
├── model/
│   ├── __init__.py
│   ├── parser.py    # load_project(path) -> ProjectModel; walks Pages → nested
│   │                 # Details (recursive) → their ColumnPresentations/EventHandlers,
│   │                 # using lxml.etree.parse()
│   └── nodes.py      # PageNode, DetailNode, ColumnNode, EventNode — each holds
│                      # identity key, full attrib dict, sourceline (+ side for Event)
├── ui/
│   └── project_tree.py   # gains a "populate from ProjectModel" path; PLACEHOLDER_PROJECT removed
```

This keeps the module boundary the original design spec called for: `model/` is the only thing that touches `lxml` directly; `ui/project_tree.py` only ever reads from a `ProjectModel`, never parses XML itself.

### 3.2 Node identity and data shape

| Node | Identity key | Data captured |
|---|---|---|
| `PageNode` | `fileName` | full `attrib` dict, `sourceline`, list of child `DetailNode`s, list of child `ColumnNode`s, list of child `EventNode`s |
| `DetailNode` | parent identity + `tableName` | same shape as `PageNode` (it wraps its own nested Page) — **including its own list of child `DetailNode`s**, since the real `.pgtp` format allows arbitrarily deep Detail-within-Detail nesting (confirmed during the original format analysis). The parser must recurse into a Detail's nested `Page/Details/Detail` the same way it recurses into a top-level Page's, not assume a fixed one-level-deep structure. |
| `ColumnNode` | parent identity + `fieldName` | full `attrib` dict, `sourceline` |
| `EventNode` | parent identity + handler tag name | handler tag name, `side` (`"S"`/`"C"`), inline text content (the PHP/JS code), `sourceline` |

### 3.3 Event side classification

Uses the authoritative 9-client/31-server event name list (recorded in project memory, sourced directly from the phpgen GUI). Any event tag name found in the client-side set is classified `"C"`; everything else defaults to `"S"`. Real sample files should be checked during implementation for any naming variants (e.g. a `_SimpleHandler`-suffixed tag observed during earlier format analysis) that might need normalizing before matching against the canonical list.

### 3.4 Source position: captured now, consumed later

`sourceline` (the line where an element starts) is captured on every node because `lxml` provides it for free — but this sub-project does nothing with it yet. The design intent (confirmed during brainstorming): clicking a **tree node** will eventually jump the Raw XML view to that element's line using this exact field; clicking a **property row** in the future Properties panel will then refine within that line/region via a text search for `{attribute_name}="` to find the exact attribute. Both of those consumers are future sub-projects — this one just ensures the data they'll need is already on hand.

### 3.5 File → Open flow

`MainWindow`'s File menu gains a real handler for "Open...": `QFileDialog.getOpenFileName(filter="PGTP files (*.pgtp)")` → `load_project(path)` → repopulate `ProjectTreePanel` from the returned `ProjectModel`. If parsing fails (malformed XML), the failure is surfaced clearly (error dialog or status message — not a crash, not a silently-empty tree), consistent with the Tier-1 validation philosophy already established in the original design spec.

## 4. Testing strategy

- **Unit tests** for `model/parser.py` and `model/nodes.py` use small, synthetic `.pgtp`-shaped XML strings written directly in the test file — fast, deterministic, and able to exercise edge cases (nested Details, multiple event handlers, missing optional attributes) without depending on the large real files.
- **Integration/regression tests** run the real parser against both real sample files in `sample/`, confirming: parsing doesn't crash, produces a sane/expected page count, and the event side-classification matches the authoritative list for whatever event names actually appear in those files. These are slower and stay a small separate suite, not the bulk of coverage — matching the testing philosophy already established for this project.

## 5. Summary of scope decisions from brainstorming

- What started as "add a Properties panel" was explicitly decomposed into 3 sequential sub-projects once it became clear Properties needs real data to be meaningful — this document covers only the first.
- The model captures attributes generically (full `attrib` dict) rather than a curated subset, specifically so "every detail phpgen lets you set" doesn't require ongoing model updates as new properties need exposing later.
- Source-position handling is deliberately split: `sourceline` capture lives in the model (cheap, general-purpose); exact attribute-column lookup is deferred to the navigation code in a later sub-project, keeping `model/` focused on "what does this file contain," not "where exactly in the text."
- Event client/server classification, originally flagged as an assumption needing empirical verification, was resolved definitively via a direct screenshot of the phpgen GUI's own event-type list (recorded in project memory) — no longer an open question.
