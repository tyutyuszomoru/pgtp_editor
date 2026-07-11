# PGTP Editor — Diff Engine (Diff/Merge Sub-project 1 of 2+) Design Specification

**Date:** 2026-07-12
**Status:** Approved for planning
**Depends on:** [2026-07-11-pgtp-editor-design.md](2026-07-11-pgtp-editor-design.md) (original shell design, §6.1 Diff/Merge and §4.4 Identity keys), the completed Real Model sub-project (`pgtp_editor/model/nodes.py`, `pgtp_editor/model/parser.py`).

## 1. Context and scope

This is the first of at least two sub-projects that together deliver the **Diff/Merge** feature sketched at a high level in §6.1 of the original design spec. The sub-projects, in dependency order:

1. **Differ engine** (this document) — pure comparison logic that walks two loaded `ProjectModel` trees and produces a flat list of differences. No UI, no file I/O.
2. **Diff/Merge menu/panel UI** — the actual "Compare / Merge Two Files..." menu item, the change-list panel, side-by-side detail view, and the Apply step that patches Target. Depends on this document's engine. Gets its own brainstorm/spec/plan cycle once this one is built and merged.

This document covers only sub-project 1.

**Why the engine comes first:** the original design spec described Diff/Merge's *behavior* (§6.1) but not its algorithm. Before any UI can be built, the engine needs a concrete, testable definition of what counts as "the same node across two files" and what a difference record looks like — exactly the kind of groundwork the Real Model sub-project did for parsing before Properties could be built on top of it. This sub-project produces that groundwork for Diff/Merge: a `Difference` record shape and a recursive comparison algorithm, both fully unit-testable against synthetic `ProjectModel` graphs without needing any Qt code or real files.

**Terminology** (matching §6.1 of the original design): the two inputs being compared are **Source** and **Target**. The differ produces a flat list of `Difference` records describing what Source has that Target doesn't, and vice versa — this is what a future "Apply" step would use to patch Target from Source.

## 2. Scope

### 2.1 In scope

- A new `pgtp_editor/diff/` package: `differ.py` (the comparison algorithm) and `records.py` (the `Difference` data shape).
- A recursive, top-down comparison of two already-loaded `ProjectModel` trees (as produced by `pgtp_editor.model.parser.load_project`), covering all four node kinds the model layer produces: `PageNode`, `DetailNode`, `ColumnNode`, `EventNode`.
- Page matching by `fileName`, globally across the whole project (mirroring the vendor's own uniqueness rule for `fileName`, and the identity-key scheme from §4.4 of the original spec).
- Attribute-level, Column-level, and EventHandler-level comparison scoped within each matched parent pair.
- Detail matching scoped to its parent pair only, keyed by `(tableName, caption)` — not by any project-wide identity (see §4.2 for why).
- The pathological-duplicate case (two or more sibling Details sharing the same `(tableName, caption)` under one parent) — positional pairing plus an `ambiguous` flag on the resulting records, per the duplicate-identity case already flagged in §4.4 of the original spec.
- Reuse of the model layer's existing event-name normalization (`classify_event_side` / the suffix-stripping rule) for matching EventHandlers by base name — not a second implementation of that rule.

### 2.2 Explicitly out of scope (this sub-project)

- Any UI — the Diff/Merge menu item, change-list panel, side-by-side detail view. All of that is sub-project 2.
- The "Apply" step that patches Target from a chosen set of `Difference` records. This sub-project only produces the list; it never mutates a `ProjectModel` or writes a file.
- Computing a line-based display diff of EventHandler text content. The engine reports old/new text verbatim in a `Changed` record; rendering a readable diff of that text (as described in §6.1 of the original spec) is the future UI's job.
- The reused-table coherence feature (§6.4 of the original design spec). It's expected to reuse this same engine at Detail-subtree scope later, but wiring that up is not part of this sub-project.
- Any file I/O. The engine operates only on already-loaded `ProjectModel` instances; it never calls `load_project` or touches a path itself.
- Cross-parent "moved" detection — see §4.2 for the full rationale; this is a deliberate narrowing of what the original spec's `moved` difference kind (§6.1) covers.

## 3. Architecture

### 3.1 Module layout

```
pgtp_editor/
├── diff/
│   ├── __init__.py
│   ├── differ.py     # diff_project(source, target) -> list[Difference]
│   │                  # recursive compare_block() walks Pages -> Details -> Columns/Events
│   └── records.py     # Difference dataclass
```

Same layering discipline as `model/`: `diff/` depends on `model/` (it consumes `ProjectModel`/`PageNode`/`DetailNode`/`ColumnNode`/`EventNode` and the `classify_event_side` normalization helper) but nothing in `model/` or `ui/` depends on `diff/`. No Qt import appears anywhere in this package.

### 3.2 Algorithm

Top-level entry point walks Pages, matched globally by `fileName`:

```
diff_project(source, target) -> list[Difference]:
    for each source Page (matched by fileName — globally unique per the vendor's own validation rule):
        if target has a Page with the same fileName -> compare_block(source_page, target_page, path=[fileName])
        else -> emit Added(path=[fileName], node=source_page)
    for each target Page whose fileName has no match in source -> emit Removed(path=[fileName], node=target_page)
```

Each matched pair (whether two Pages or two Details) is compared the same way, via a shared recursive helper:

```
compare_block(source_node, target_node, path):
    for each attribute present on either source_node.attrib or target_node.attrib:
        if values differ -> emit Changed(path, node_kind, attribute=name, old_value=target's value, new_value=source's value)
    diff Columns (children), matched by fieldName, scoped to this parent pair only:
        matched -> Changed record per differing attribute (columns have no further children)
        source-only -> Added(subtree)
        target-only -> Removed(subtree)
    diff EventHandlers (children), matched by base handler name (after suffix normalization, same normalization the model layer already applies for client/server classification — reuse it, do not reimplement), scoped to this parent pair only:
        matched, text differs -> Changed(path, node_kind="event", attribute=None, old_value=target's raw text, new_value=source's raw text)
        source-only -> Added(subtree)
        target-only -> Removed(subtree)
    diff child Details, matched by the pair (tableName, caption), scoped to this parent pair only:
        matched -> recurse compare_block(child_source, child_target, path + [detail identity])
        source-only -> Added(subtree)
        target-only -> Removed(subtree)
        SPECIAL CASE: if more than one sibling Detail shares the same (tableName, caption) pair on either side, pair the extras positionally (1st extra with 1st extra, 2nd with 2nd, etc.) and mark every Difference record produced from that group with ambiguous=True, so it surfaces for manual review later (e.g. in a future Audit panel) rather than being silently trusted.
```

`compare_block` is applied uniformly to a matched Page pair and to every matched Detail pair — a Detail's nested Page carries the same attribute/Column/EventHandler/child-Detail shape as a top-level Page (per the model layer's own merged-attribute representation in `DetailNode`), so no separate comparison routine is needed for Details versus Pages. The `node_kind` recorded on emitted `Difference` records (`"page"` vs `"detail"`) is the caller's responsibility to set based on which level of the recursion it's in, since `compare_block` itself is shape-agnostic.

Attribute comparison reads `source_node.attrib` / `target_node.attrib` directly (the plain dict every model node carries) rather than any derived property, so it naturally covers every attribute the vendor format can carry on a Page/Detail/Column — consistent with the model layer's own "capture everything generically" decision.

### 3.3 Detail matching key: scoped to parent, not global

A Detail's matching key is `(tableName, caption)`, scoped **entirely to its current parent pair** — there is no global/whole-file identity matching for Details. Contrast this directly with Page matching, which **is** global via `fileName`.

**Empirical finding:** in the real sample file `sample/dev_Ferrara.pgtp`, of 91 `Detail` elements, 74 have a blank/empty `fileName` on their nested Page, and among the 17 non-blank ones, `"operation"` appears 4 times and `"checklist_check"` appears 2 times. So `fileName` is neither reliably populated nor unique for nested Detail pages — unlike top-level Pages, where it's the enforced-unique identity key. This rules out reusing the Page identity key for Details, and is why Detail matching uses `(tableName, caption)` scoped to the parent instead.

### 3.4 No cross-parent "moved" detection

This was explicitly discussed and dropped during brainstorming. The original design spec's §6.1 describes a `moved` difference kind (same identity, different parent) as "the core payoff of a domain-aware differ over line-based diff." Two approaches were weighed for this sub-project:

- **Global identity matching for Details** (so a Detail relocated to a different parent Page would still be recognized as "the same Detail, moved" rather than a delete+insert pair) — rejected.
- **Parent-scoped matching only**, treating a relocated Detail as a Removed record under its old parent and an Added record under its new parent — **adopted**.

Rejected because:

1. `tableName` is not unique file-wide (confirmed empirically in §3.3 above — `"operation"` alone appears 4 times across different parents in one real sample file), so there is no reliable project-wide identity key to match Details on in the first place. Any global-matching scheme would need to guess at pairing among same-`tableName` Details scattered across unrelated parents, which is far more ambiguous than the already-flagged same-parent duplicate case.
2. Relocating a Detail to a different parent Page is the job of the separate Move/Copy feature (§6.2 of the original design spec) — a user-driven, explicit operation. It is not something the differ needs to infer automatically from two independently-edited trees.

Net effect: this sub-project's engine never emits a `moved` record. A relocated Detail shows up as one `Removed` (old parent) and one `Added` (new parent) record. Whether a later sub-project revisits this (e.g. layering move-detection on top once real usage shows it's needed) is out of scope here.

### 3.5 `Difference` record shape

Defined in `records.py` as a `@dataclass`, matching the model layer's own dataclass style (`pgtp_editor/model/nodes.py` uses `@dataclass` throughout):

| Field | Type | Meaning |
|---|---|---|
| `kind` | `"added"` \| `"removed"` \| `"changed"` | What happened to this node/attribute between Source and Target. |
| `path` | `list[str]` | Identity strings from the project root down to the differing node (e.g. `["development_equipment", "operation/Maintenance"]`), for later UI grouping/display. Does not need to be globally unique on its own — just descriptive. |
| `node_kind` | `"page"` \| `"detail"` \| `"column"` \| `"event"` | Which kind of node this record describes. |
| `attribute` | `str \| None` | The attribute name, for a `"changed"` record on a page/detail/column. `None` for whole-subtree `added`/`removed` records, and for event text changes (event content isn't an XML attribute). |
| `old_value` | `Any` | For `"changed"`: Target's value of the attribute. For `"removed"`: the whole model node object (`PageNode`/`DetailNode`/`ColumnNode`/`EventNode`) that only exists in Target, so a future UI can render it in full rather than just a label. |
| `new_value` | `Any` | For `"changed"`: Source's value of the attribute. For `"added"`: the whole model node object that only exists in Source. |
| `ambiguous` | `bool` | `True` only for records produced from the duplicate-`(tableName, caption)`-sibling special case (§3.2); `False` otherwise. |

For an event text change, `old_value`/`new_value` hold Target's/Source's raw `EventNode.text` respectively, with `attribute=None` (event content isn't stored as an XML attribute — it's the element's text body).

## 4. Testing strategy

- **Synthetic fixtures**: small `ProjectModel`/node object graphs built directly in test code (no XML parsing needed — this is one layer above the parser), covering:
  - Page added, Page removed, Page attribute changed.
  - Column added, removed, changed.
  - Event added, removed, changed (text).
  - Nested Detail added, removed, changed, at 2+ levels of nesting.
  - The duplicate-`(tableName, caption)`-sibling ambiguous case: assert `ambiguous=True` on the resulting records, and assert correct positional pairing among the extras.
- **Integration/regression tests**: one per real sample file (`sample/dev_Ferrara.pgtp`, `sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp`, both present in the worktree's `sample/` directory, gitignored) — load the same file twice via `load_project` and diff it against itself, asserting the result is an empty list. This is a strong sanity check that the algorithm doesn't spuriously report differences when there are none (e.g. from float-vs-string comparison quirks, dict-ordering assumptions, or unstable duplicate-pairing).

## 5. Summary of decisions from brainstorming

- Diff/Merge, previously described only at a behavioral level in §6.1 of the original design spec, was explicitly decomposed into at least 2 sequential sub-projects once it became clear the engine needed its own concrete algorithm and record shape before any UI could be designed against it — this document covers only the first (the engine).
- Detail matching is scoped strictly to the parent pair, using `(tableName, caption)`, not any project-wide identity key. This was verified empirically against a real sample file (`dev_Ferrara.pgtp`): 74 of 91 Details have a blank nested-Page `fileName`, and non-blank values repeat (`"operation"` ×4, `"checklist_check"` ×2) — ruling out `fileName`, and by extension any single-field global key, as a viable Detail identity.
- Cross-parent "moved" detection (the original spec's `moved` difference kind) was explicitly considered and dropped for this sub-project. A relocated Detail is reported as a plain Removed/Added pair rather than inferred as a move, because (a) there's no reliable project-wide Detail identity to match on, and (b) relocation is already a deliberate, user-driven operation via the separate Move/Copy feature (§6.2), not something the differ should try to auto-recognize.
- The duplicate-sibling case (two-or-more Details sharing a `(tableName, caption)` under one parent — already flagged as pathological in §4.4 of the original spec) is handled by positional pairing plus an `ambiguous=True` flag, surfacing it for manual review rather than silently trusting a guessed pairing or crashing.
- The engine reuses the model layer's existing event-name normalization (`classify_event_side`'s suffix-stripping rule) for matching EventHandlers by base name, rather than reimplementing the same logic a second time.
- Rendering a readable line-based diff of EventHandler text, and the "Apply" step that mutates Target, were both confirmed as UI-layer (sub-project 2) concerns — the engine only ever reports verbatim old/new text and never mutates anything.
