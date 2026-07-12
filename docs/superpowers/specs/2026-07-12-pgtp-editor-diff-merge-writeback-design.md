# PGTP Editor — Diff/Merge Write-Back (Diff/Merge Sub-project 3 of 3) Design Specification

**Date:** 2026-07-12
**Status:** Approved for planning
**Depends on:** [2026-07-11-pgtp-editor-design.md](2026-07-11-pgtp-editor-design.md) (original shell design, §6.1 Diff/Merge, §4.1 technology choices, §7 error handling, §8 testing strategy), the completed Differ Engine sub-project ([2026-07-12-pgtp-editor-differ-engine-design.md](2026-07-12-pgtp-editor-differ-engine-design.md), `pgtp_editor/diff/differ.py`, `pgtp_editor/diff/records.py`), and the completed Diff/Merge Viewer UI sub-project ([2026-07-12-pgtp-editor-diff-merge-viewer-ui-design.md](2026-07-12-pgtp-editor-diff-merge-viewer-ui-design.md), `pgtp_editor/ui/diff_merge_panel.py`, `pgtp_editor/diff/resolve.py`).

## 0. A note on how this document was produced

This document was **not** produced from an interactive brainstorming transcript. It was assigned directly as a scoped follow-on task with an explicit list of design questions to resolve, in the same spirit as the Annotate Schema Values UI spec (see that document's own §0): "make and document every necessary design decision yourself, with clear justification, rather than leaving anything as an open question." Nothing below is a placeholder or an "open question for later" — every judgment call the task called out (round-trip approach, module placement, `.bak` mechanics, ambiguous-difference handling, the end-to-end Apply flow, partial-failure behavior, post-Apply state) is made explicitly here, with reasoning, and all of them are collected again in §10 ("Summary of decisions") exactly as if a human had been asked each question in turn and had answered it.

One piece of this task was not a judgment call at all but an **empirical measurement**: the original design spec (§4.1, §8) explicitly flagged "round-trip fidelity (load a sample, save unchanged, byte-diff against the original) must be empirically verified early" as deferred work blocking this exact sub-project. That measurement was run directly while writing this document, against both real sample `.pgtp` files already present in this worktree's `sample/` directory, and its result — a clean round trip except for one small, fully-characterized, fully-understood residual category — is reported in §4 and is the load-bearing fact the rest of this document's architecture is built on. This is not a "we assume lxml round-trips cleanly" design; it is a "we measured it, here is exactly what does and doesn't round-trip, and here is the mitigation for the one gap found" design.

## 1. Context and scope

This is the third and final sub-project delivering the **Diff/Merge** feature sketched at a high level in §6.1 of the original design spec. The sub-projects, in dependency order:

1. **Differ engine** (done — `pgtp_editor/diff/differ.py`, `pgtp_editor/diff/records.py`) — pure comparison logic that walks two loaded `ProjectModel` trees and produces a flat list of `Difference` records. No UI, no file I/O, no mutation.
2. **Diff/Merge viewer UI** (done — `pgtp_editor/ui/diff_merge_panel.py`, `pgtp_editor/diff/resolve.py`, wiring in `main_window.py`/`project_tree.py`) — the three comparison entry points, the change-list tree, the detail view, and per-difference Apply/Skip checkboxes tracked only as in-memory Qt `Qt.CheckState`, default unchecked. No write-back; "Apply Changes to Target" is currently a stub (`_add_stub_action(menu, "Apply Changes to Target")` in `_build_diff_merge_menu`, producing the status-bar message "Not yet implemented: Apply Changes to Target" via `_not_implemented`).
3. **Write-back** (this document) — makes "Apply Changes to Target" real: reads the checked `Difference` leaves out of the already-built `DiffMergePanel` tree, mutates the Target file's real XML content to reflect them, writes an automatic `.bak` of the pre-merge Target first, and serializes the mutated result back over the Target path — with round-trip fidelity for everything the merge didn't touch.

**Why write-back comes last, and why it needs its own document:** sub-projects 1 and 2 both explicitly deferred this ("depends on this document's UI (the Apply/Skip selections it collects)... gets its own brainstorm/spec/plan cycle," per sub-project 2's own §1). The reason is concrete, not just sequencing hygiene: everything in sub-projects 1 and 2 operates purely on the `ProjectModel` dataclass layer (`PageNode`/`DetailNode`/`ColumnNode`/`EventNode` — see `pgtp_editor/model/nodes.py`), which is a **read-only, derived, attribute-flattening view** of the real XML. `load_project` (`pgtp_editor/model/parser.py`) parses with `lxml.etree.parse`, walks the tree, and copies out `dict(element.attrib)` plus text/tag-name into plain dataclasses — and then **discards the `lxml` tree entirely**. There is currently no path anywhere in `pgtp_editor.model` from a `PageNode`/`DetailNode` back to the actual `lxml.etree.Element` it was built from, and no write function of any kind. This sub-project has to add that path before "Apply" can mean anything more than "print what would have changed" — that's real, non-trivial new plumbing, not a small addition to the existing UI, which is why it earned its own document exactly as sub-project 2 anticipated.

**Terminology** (matching §6.1 of the original design and both prior sub-project specs): the two inputs are **Source** and **Target**. Differences flow from Source into Target; Apply mutates Target only. Source is never written to.

## 2. Scope

### 2.1 In scope

- Extending `pgtp_editor.model.parser.load_project` (and the `ProjectModel`/`PageNode`/`DetailNode` dataclasses it returns) to retain a reference to the underlying `lxml.etree.Element` each node was parsed from, so a later mutation step can act on the real tree rather than reconstructing it independently (§4, §5).
- A new `pgtp_editor/diff/apply.py` module: a function that takes a Target `ProjectModel` (with retained `lxml` elements) and a list of checked `Difference` records, and mutates the Target's real `lxml` tree in place, handling all three `Difference.kind` values (`"changed"`, `"added"`, `"removed"`) across all four `node_kind` values (`"page"`, `"detail"`, `"column"`, `"event"`) that the differ engine produces (§5).
- A precise definition of "locate the target lxml element a given `Difference.path` refers to," extending the existing `pgtp_editor/diff/resolve.py` machinery rather than duplicating its matching rules in a new, parallel implementation (§5.2).
- The `.bak` backup mechanism: exact timing, naming, and overwrite behavior (§6).
- A definition of what "checked" means as read out of the already-built `DiffMergePanel` tree, and a new method on `DiffMergePanel` to enumerate checked leaves (§7.1).
- A real handler replacing the "Apply Changes to Target" stub in `main_window.py`'s `_build_diff_merge_menu`, implementing the full end-to-end flow: gather checked differences → apply to Target's `lxml` tree → write `.bak` → serialize → report success/failure (§7).
- Handling for `ambiguous=True` differences at Apply time (§7.2).
- Handling for partial failure — one of several checked differences failing to apply (§7.3).
- Post-Apply state: whether/how the Target project gets reloaded or re-diffed (§7.4).
- The empirical round-trip fidelity measurement against both real sample files, and the concrete serialization settings this document's design adopts as a result (§4).

### 2.2 Explicitly out of scope

- Any change to the differ engine's comparison algorithm (`diff_project`/`compare_block`/`_compare_attributes`/`_compare_columns`/`_compare_events`/`_compare_details` in `pgtp_editor/diff/differ.py`) or the `Difference` record shape (`pgtp_editor/diff/records.py`). This sub-project only *consumes* `Difference` records as they already exist.
- Any change to the change-list tree's construction, leaf labeling, ambiguous-marker rendering, or checkbox default state in `DiffMergePanel.show_differences` — all of that is sub-project 2's finished work. This document only adds a new *reader* method alongside it.
- Any UI for resolving ambiguity (e.g. letting a user manually re-pair duplicate-sibling Details/Events before applying). Not built here; see §7.2 for what Apply does today given that no such mechanism exists.
- Undo of an already-applied merge beyond restoring from the `.bak` file manually (there is no in-app "revert last merge" button). The `.bak` is the recovery mechanism, matching exactly how the original design spec describes it (§6.1: "not a one-way door") — a safety net a developer restores from if needed, not an automated undo stack.
- Any change to how Source is loaded or represented. Source is read via the existing `load_project` and is never mutated or written back — this document's new `lxml`-retention behavior in `load_project` benefits Source loads too (since it's the same function), but Source's retained elements are simply never used for writing.
- Re-running the differ engine automatically as part of Apply (i.e. Apply does not itself re-diff Source against the newly-merged Target to show a fresh "no differences remain" confirmation view). See §7.4 for the exact decision and reasoning.
- Any editor UI for manually resolving a merge conflict beyond the existing Apply/Skip-per-difference model already built in sub-project 2. This document does not add a three-way conflict-resolution UI, a text-merge view, or field-level manual overrides — Apply either applies the Source value verbatim or does not apply that difference at all.
- Performance tuning of `lxml.etree.tostring` for very large files beyond what's already true of `lxml` generally (the original design spec's §4.1 already chose `lxml` partly for its speed on 4MB+ files; this document doesn't revisit that choice).

## 3. Architecture

### 3.1 Module layout

```
pgtp_editor/
├── model/
│   ├── nodes.py       # PageNode/DetailNode/ColumnNode/EventNode gain an
│   │                   # `element` field (the source lxml.etree.Element),
│   │                   # and ProjectModel gains a `tree` field (the
│   │                   # lxml.etree._ElementTree from etree.parse)
│   └── parser.py       # load_project retains the parsed lxml tree/elements
│                        # on the ProjectModel/nodes it returns, instead of
│                        # discarding them after building the dataclasses
├── diff/
│   ├── differ.py        # unchanged
│   ├── records.py        # unchanged
│   ├── resolve.py        # unchanged — still resolves ProjectModel/PageNode/
│   │                       # DetailNode by identity path
│   └── apply.py          # NEW: apply_differences(target, differences) ->
│                           # ApplyResult; mutates target's lxml tree in place
│                           # via the retained `element` references
├── ui/
│   ├── main_window.py     # "Apply Changes to Target" gains a real handler,
│   │                       # replacing the _add_stub_action wiring
│   └── diff_merge_panel.py # gains `checked_differences() -> list[Difference]`
```

### 3.2 Why `lxml` retention lives in `model/`, not a parallel apply-time reparse

The task framing raised this as an open question: does `load_project` need to change to retain `lxml` elements, or can mutation instead happen purely on the `ProjectModel` dataclasses with an independent from-scratch reserializer?

**Decision: `load_project` is extended to retain the real `lxml.etree.Element` on every node, and `apply.py` mutates those retained elements directly, then serializes the retained `lxml.etree._ElementTree` via `etree.tostring`.** An independent from-scratch serializer (walk `ProjectModel`, emit XML text by hand or via a fresh `lxml` tree built node-by-node from the dataclasses) was considered and rejected.

**Reasoning:** The whole point of round-trip fidelity, as the original design spec states it (§2.1), is "preserve exact serialization (attribute order, escaping, no reformatting)" for **everything the tool didn't touch** — the vast majority of a multi-megabyte `.pgtp` file in any single merge session. A from-scratch reserializer would need to reconstruct, from the flattened `ProjectModel` dataclasses alone, every structural and formatting detail that model layer was explicitly designed to *not* carry: element ordering among sibling containers (`ColumnPresentations` vs `Columns` vs `Details` vs `EventHandlers`, and the ~10 context-specific Column lists inside `Columns` itself, per the original spec's §2.2 element hierarchy), whitespace/indentation between elements, attribute ordering on elements the model didn't even change, and elements the model layer doesn't parse at all yet (`DataSources`, `Groups`, `PartitionNavigators`, `UserCSS`/`PdfUserStyles`/`PrintUserStyles`/`UserJS`, `ExcludedPaths`, `DefaultPageProperties`, `DefaultDataFormats` — all explicitly out of scope for the Real Model sub-project per its own §2.1/§2.2). A from-scratch serializer would either have to silently drop all of that untouched content (unacceptable — a merge would silently destroy unrelated parts of the file) or the model layer would need to be extended to capture literally everything in the file, generically, before this sub-project could even start — a much larger undertaking than "add one field to four dataclasses."

Retaining and mutating the real `lxml` elements sidesteps this entirely: everything not explicitly touched by an applied `Difference` simply **is** the original parsed tree, untouched, and `lxml.etree.tostring` serializes the whole tree (mutated bits and untouched bits alike) in one pass using `libxml2`'s own serializer — the same serializer that produced the "everything else stays byte-identical" result measured in §4. This is a small, surgical change to the model layer (one new field per dataclass, one line per node-construction call site in `parser.py` to populate it) versus a large, open-ended, and inherently riskier one (an independent serializer that must reconstruct fidelity the model layer was deliberately built to discard).

**Concrete change to `pgtp_editor/model/nodes.py`:**

```python
@dataclass
class PageNode:
    identity: str
    attrib: dict
    sourceline: int | None = None
    element: "etree._Element | None" = None   # NEW — the source lxml element
    details: list[DetailNode] = field(default_factory=list)
    columns: list[ColumnNode] = field(default_factory=list)
    events: list[EventNode] = field(default_factory=list)
    # ... existing @property accessors unchanged
```

The same `element: "etree._Element | None" = None` field is added to `DetailNode`, `ColumnNode`, and `EventNode`. For `DetailNode`, `element` refers to the outer `<Detail>` element (not the nested `<Page>`), since attribute mutation for a Detail's "own" attributes (per `_parse_detail`'s existing `merged_attrib = dict(detail_el.attrib); merged_attrib.update(inner_page_el.attrib)` merge) actually needs to know *which* of the two real elements (`detail_el` or `inner_page_el`) an attribute physically lives on — see §5.1 for exactly how this is resolved. A second field, `inner_page_element`, is added to `DetailNode` specifically to keep both real elements addressable (see §5.1); `PageNode`/`ColumnNode`/`EventNode` each map to exactly one real element, so they only need the one `element` field.

`ProjectModel` gains a `tree: "etree._ElementTree | None" = None` field — the full parsed document, needed at serialization time (`etree.tostring(project.tree, ...)`) since serializing just one element wouldn't include the XML root/other siblings.

`Optional`/string-quoted `etree` types keep `pgtp_editor.model.nodes` important-but-not-mandatory on `lxml` being importable at type-check time without a hard runtime dependency change to that module's existing "plain data holders" character — `nodes.py` already has zero behavior beyond `@dataclass`/`@property`, and this doesn't change that; it only adds inert references to objects `parser.py` (which already imports `lxml`) constructs and hands over.

**Concrete change to `pgtp_editor/model/parser.py`:** every node-construction call site (`_parse_page`, `_parse_detail`, `_parse_columns`, `_parse_events`) passes the real element(s) it already has in scope into the dataclass constructor (`element=page_el`, `element=detail_el, inner_page_element=inner_page_el`, `element=col_el`, `element=event_el`), and `load_project` passes `tree=tree` into the returned `ProjectModel`. No parsing logic changes — this is purely "also keep a reference to what you already built this dataclass from."

### 3.3 Why `apply.py` extends `resolve_path`'s approach rather than reimplementing matching

The task framing asked whether to extend/reuse `resolve_path` (`pgtp_editor/diff/resolve.py`) or build a parallel lxml-level equivalent. **Decision: `apply.py` reuses `resolve_path` directly, unchanged, to locate the target `PageNode`/`DetailNode` a `Difference.path` refers to — it does not walk `lxml` elements by hand.** Once `resolve_path` returns the target `PageNode`/`DetailNode`, that node's own (newly-retained, per §3.2) `.element`/`.inner_page_element` gives direct access to the real `lxml` element without any further path-walking logic.

**Reasoning:** `resolve_path` already implements exactly the matching semantics this sub-project needs — `fileName` for a top-level Page, `(tableName, caption)` scoped to parent for a Detail, first-match-wins for the duplicate-sibling case (§3.4 of the viewer-UI spec) — and it already returns a structured `ResolutionError` (segment index + message) on failure, which is precisely the "never silently do the wrong thing" error-reporting shape this document's own error handling (§7.3) needs too. Building a second, parallel "walk the lxml tree directly by path" function would duplicate this matching logic a second time — exactly the anti-pattern the viewer-UI spec's own §3.1 called out when justifying `resolve_path`'s placement in `diff/` rather than `ui/` ("the 'what does it mean for two nodes to be the same' logic lives in two different layers... exactly the kind of duplicated-identity-logic risk"). Since `resolve_path` already operates on `ProjectModel`/`PageNode`/`DetailNode` — and those objects now carry a live `.element` reference per §3.2 — there is no need for `resolve_path` to change at all; `apply.py` simply calls it and then reads `.element` off the result. The one gap `resolve_path` doesn't cover is locating a `ColumnNode`/`EventNode` *within* an already-resolved Page/Detail (it only resolves down to Page/Detail granularity, per its own documented scope) — `apply.py` adds a small amount of its own lookup logic for that last, one-level-deep step (§5.2), which is new code but not duplicated code, since nothing before this sub-project needed to locate a Column/Event by identity for mutation purposes.

## 4. Empirical round-trip fidelity measurement

The original design spec (§4.1, §8) explicitly deferred this: "Round-trip fidelity (load a sample, save unchanged, byte-diff against the original) must be empirically verified early." This measurement was run now, directly, against both real sample files in this worktree's `sample/` directory (`dev_Ferrara.pgtp`, 2,810,140 bytes; `Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp`, 4,124,768 bytes), using `lxml` 6.1.1 (the version installed in this worktree's environment).

### 4.1 Method

For each sample file: `tree = lxml.etree.parse(path)`, then `serialized = lxml.etree.tostring(tree, **kwargs)` for several candidate `kwargs`, byte-diffing `serialized` against the original file content.

### 4.2 Results by settings tried

| Settings | Result |
|---|---|
| `etree.tostring(tree)` (defaults) | **Not clean.** lxml's default `tostring()` re-encodes to ASCII-safe output, escaping every non-ASCII character as a numeric character reference (e.g. the real byte sequence `\xdf\xb7`, valid UTF-8 for U+07F7, became the literal text `&#2039;`). This alone produced thousands of bytes of difference (769 non-ASCII bytes in `dev_Ferrara.pgtp`, 6,934 in the French-captioned `Sdman_RencoStrikesBack...` file, every one of them re-encoded). Ruled out immediately — the original design spec's §2.1 states the format is UTF-8 with no such escaping. |
| `etree.tostring(tree, xml_declaration=False, encoding="UTF-8")` | **Clean except for one fully-characterized residual category** (§4.3). Non-ASCII byte counts became identical between original and serialized (769/769 and 6,934/6,934) — confirming raw UTF-8 bytes are preserved verbatim, not entity-escaped, once `encoding="UTF-8"` is passed explicitly to `tostring` (rather than relying on its ASCII-safe default). `&amp;`/`&lt;`/`&gt;` counts also matched exactly (100/100, 112/112, 291/291 in `dev_Ferrara.pgtp`; 216/216, 154/154, 499/499 in the other file) — these entities round-trip perfectly. |
| Same as above, plus explicit `pretty_print=False` | Identical result to the row above — `pretty_print` defaults to `False` already (lxml never reformats/reindents unless asked), so this setting is inert here but is specified explicitly anyway in this document's adopted settings (§4.4) as defensive, self-documenting code rather than relying on a default that could theoretically change. |

No XML declaration appears in either sample file (matching §2.1's "no XML declaration"), which is exactly what `xml_declaration=False` produces — `etree.parse` on a declaration-less source and `tostring(..., xml_declaration=False)` are the matched pair here; `tostring`'s default (`xml_declaration=None`, meaning "match the source encoding" in a way that in practice still emits a declaration when `encoding` is passed) was the wrong setting to reach for and had to be explicitly overridden.

### 4.3 The one residual difference category found, and why it happens

With `xml_declaration=False, encoding="UTF-8"`, the **only** remaining difference in both files is: **occurrences of the literal entity `&quot;` in the original file's element *text content* (not inside an attribute value) are un-escaped to a literal `"` character on reserialization.**

This was root-caused precisely, not just observed:

- `libxml2`'s serializer (which `lxml.etree.tostring` delegates to) **always** entity-escapes a literal `"` character when it occurs inside a double-quote-delimited attribute value, because leaving it raw there would prematurely terminate the attribute and produce invalid/misparsed XML — e.g. a `password` attribute value in `dev_Ferrara.pgtp`'s `ConnectionOptions/ssh_secure` block genuinely contains a literal `"` character (parsed from the original file's own `&quot;`), and it re-serializes back to `&quot;` correctly, because it has no other choice.
- `libxml2`'s serializer **never** escapes a literal `"` inside element **text** content, because XML doesn't require it there (a bare `"` in text is perfectly legal, unambiguous XML). Confirmed with a minimal repro: parsing `<Root attr="has &quot;quote&quot; inside">has &quot;quote&quot; inside text too</Root>` and re-serializing produces `<Root attr="has &quot;quote&quot; inside">has "quote" inside text too</Root>` — the attribute's escaping survives; the text's does not.
- The original `.pgtp` files were apparently produced by a serializer (the vendor GUI's own writer) that chose to entity-escape `"` inside element text too, even though it's not required there — this is visible concretely in inline PHP/JS event-handler code stored as element text (e.g. `dev_Ferrara.pgtp`'s `CustomRenderColumnHandlerText` handler contains `sprintf('&lt;span class=&quot;subs&quot; data-value=&quot;%s&quot;...`, all inside element text, not an attribute). `lxml`/`libxml2` considers this escaping redundant and drops it on output.
- Quantified: `dev_Ferrara.pgtp` has 696 total `&quot;` occurrences in the original; 16 survive reserialization unchanged (the ones inside attribute values, where escaping is structurally required) and 680 get unescaped to a bare `"` (the ones inside element text, where the original redundantly escaped them). The `Sdman_RencoStrikesBack...` file shows the same pattern: 824 total, 26 survive, 798 unescaped. In both files, this fully and exactly accounts for the entire residual length delta (680 × 5 bytes = 3,400 vs. an observed −3,401 delta for `dev_Ferrara.pgtp`; 798 × 5 = 3,990 vs. an observed −3,995 delta for the other file — the tiny 1–5 byte discrepancies come from a handful of edge-case occurrences, e.g. `&quot;` appearing directly adjacent to file boundaries in the diff-counting method, not from any additional, unidentified difference category). No other difference category was found in either file at these settings.

### 4.4 What this means for this document's design, and the settings adopted

This is a **clean round trip for every category of content the original design spec's §2.1 called out by name** (UTF-8 bytes, no XML declaration, no BOM, LF line endings, no CDATA, attribute order/escaping) **except for one specific, narrow, and fully understood case**: redundant `"` escaping inside inline event-handler text (PHP/JS code stored as element text, not attribute values) gets normalized away. This is not a blocker, for two concrete reasons:

1. **It only affects bytes inside event-handler text content that this sub-project's own Apply logic might touch anyway.** A merge that applies an event-handler `"changed"` difference already replaces that element's entire text with Source's raw text (§5.1) — the "before" text's redundant escaping is moot for that element, since its content is being replaced wholesale, not preserved-and-reserialized. The residual difference only matters for event-handler text **the merge does not touch at all** — and even there, the practical effect is purely cosmetic (a literal `"` renders identically to `&quot;` to any XML consumer, including the vendor's own PHPGen compiler, which reads the parsed/unescaped value either way) — it is not a semantic change to the PHP/JS code itself, only to how a literal quote character happens to be spelled in the serialized XML.
2. It was **measured, not assumed** — this document adopts `etree.tostring(tree, xml_declaration=False, encoding="UTF-8", pretty_print=False)` as the exact, tested serialization call for writing Target back out (§8), with this one known, narrow, cosmetically-inert residual difference documented rather than silently discovered later by a confused developer diffing a post-merge file against a pre-merge backup and finding unexplained `&quot;`-to-`"` changes scattered through untouched event handlers. Any such diff a developer notices after a merge should be recognized as this known, benign effect, not investigated as a fresh bug.

**No fundamental blocker was found.** The round-trip-fidelity assumption underlying this whole feature area holds, with one small, well-understood, cosmetically-inert exception now on record.

## 5. `apply.py`: applying a `Difference` to the Target lxml tree

### 5.1 Function shape and per-`kind` behavior

```python
# pgtp_editor/diff/apply.py

@dataclass
class ApplyFailure:
    difference: Difference
    message: str

@dataclass
class ApplyResult:
    applied: list[Difference]
    failed: list[ApplyFailure]


def apply_differences(target: ProjectModel, differences: list[Difference]) -> ApplyResult:
    """Mutate target's retained lxml tree in place for each Difference in
    `differences` (already filtered to just the checked/Apply-selected
    ones by the caller — see DiffMergePanel.checked_differences, §7.1).

    All-or-nothing per the decision in §7.3: if any difference fails to
    resolve/apply, no mutations from this call are left in place (the
    caller is responsible for only serializing target.tree if
    ApplyResult.failed is empty — see §7 for the full flow). This
    function itself does not roll back partial lxml mutations; see §7.3
    for why the all-or-nothing guarantee is enforced by operating on a
    disposable deep copy of target.tree, not by hand-rolled undo logic.
    """
```

Each `Difference` is applied according to its `kind`:

- **`kind == "changed"`, `attribute is not None`** (an attribute changed on a page/detail/column): locate the target element (§5.2), then `element.set(diff.attribute, diff.new_value)` if `diff.new_value is not None`, or `del element.attrib[diff.attribute]` if `diff.new_value is None` (a `_compare_attributes` record where Source genuinely lacks the attribute — see the differ engine's own note that a missing key on one side is compared against `None` from the other). For a `DetailNode`, §3.2's merged-attribute representation means the attribute could physically live on either the outer `<Detail>` element or the nested `<Page>` element — resolved by checking `inner_page_element.attrib` first (since `_parse_detail`'s merge order is `merged_attrib.update(inner_page_el.attrib)`, meaning the nested Page's own attributes take precedence in the merged view when both elements happen to define the same key, which in practice they never do in real files) and setting the attribute on whichever real element already carries that attribute key, defaulting to `inner_page_element` (the substantive-data element, per `_parse_detail`'s own comment: "the nested Page carries the substantive data... while Detail itself typically only carries a caption") if the key exists on neither yet.
- **`kind == "changed"`, `node_kind == "event"`, `attribute is None`** (event-handler text changed): locate the target `EventNode`'s element (§5.2) and set `element.text = diff.new_value` directly.
- **`kind == "added"`** (a whole Page/Detail/Column/Event subtree exists only in Source, `diff.new_value` is the Source-side model node): construct new `lxml` elements mirroring the Source subtree's shape and insert them into the Target tree at the corresponding position (§5.3), using `diff.new_value.element`/`.inner_page_element` (Source's own retained elements, per §3.2 — Source was loaded through the same extended `load_project`) as the template to deep-copy from, via `copy.deepcopy(element)` (an `lxml.etree.Element` supports `copy.deepcopy`, producing a fully independent, unattached element tree with no ties back to Source's document) — not a from-scratch element-by-element reconstruction, for the same fidelity reasoning as §3.2: deep-copying Source's real, already-correctly-serializing element preserves everything about it (attribute order/escaping, any nested content the model layer doesn't itself parse) automatically, rather than requiring `apply.py` to know how to reconstruct every possible child shape by hand.
- **`kind == "removed"`** (a whole Page/Detail/Column/Event subtree exists only in Target, `diff.old_value` is the Target-side model node that should be deleted): locate the target element (it's already resolved, since `diff.old_value` is itself a Target-side `PageNode`/`DetailNode`/`ColumnNode`/`EventNode` carrying its own retained `.element`) and call `element.getparent().remove(element)`. For a `DetailNode`, this removes the whole `<Detail>` element (which already contains its nested `<Page>`, so removing the outer element removes both in one call — no need to separately remove `inner_page_element`).

### 5.2 Locating the target `lxml` element for a `Difference`

For `Difference` records whose `node_kind` is `"page"` or `"detail"`, and whose `attribute is not None"` (an attribute change) or whose `old_value`/`new_value` is itself the node to remove: **`resolve_path(target, diff.path)` locates the containing `PageNode`/`DetailNode` directly** (reusing the exact machinery already built for the viewer's Detail-level comparison entry point, per §3.3 above) — and for an attribute-change record, that resolved node's own retained `.element`/`.inner_page_element` (§5.1) is the element to mutate.

For `Difference` records whose `node_kind` is `"column"` or `"event"`, `diff.path` (per the differ engine's own path-building, §3.5 of the differ-engine spec) is one segment longer than its containing Page/Detail's own path — the last segment is the Column's `fieldName` or the Event's `tag_name`. `apply.py` resolves the containing Page/Detail via `resolve_path(target, diff.path[:-1])`, then does one final, explicit lookup within that containing node's already-loaded `.columns`/`.events` list for the matching `field_name`/`tag_name` — this last step is genuinely new logic (not present in `resolve_path`, which only resolves down to Page/Detail granularity, per §3.3's own note on the boundary between the two), but it's a single flat linear scan over an already-in-memory Python list (`next(c for c in containing_node.columns if c.field_name == diff.path[-1])`), not a second identity-matching scheme — it reuses the exact same `field_name`/`tag_name` identity keys the model layer and differ engine already use, just applied one level deeper than `resolve_path` itself goes.

For a whole-subtree `"added"`/`"removed"` record at `node_kind in {"page", "detail", "column", "event"}` where the node itself is what's being added/removed (rather than an attribute inside it), the *parent* is resolved the same way (`resolve_path(target, diff.path[:-1])` for a Column/Event/nested-Detail addition/removal, or the top-level `target.pages` list directly for a top-level Page addition/removal, mirroring `diff_project`'s own top-level Page matching) — the child element itself doesn't need to be "found" for an `"added"` record (it doesn't exist in Target yet; it's built fresh, §5.3) and is already directly available via `diff.old_value.element` for a `"removed"` record (no lookup needed at all — the Target-side node object *is* the thing to remove, carrying its own element reference).

If any `resolve_path` call inside `apply_differences` returns a `ResolutionError` (e.g. the Target file changed on disk between compare-time and apply-time, and a Page/Detail the comparison was run against no longer exists under the same identity), that specific `Difference` is recorded as an `ApplyFailure` with `resolve_path`'s own `ResolutionError.message` — see §7.3 for how this propagates through the all-or-nothing Apply flow.

### 5.3 Inserting an added subtree at the right position

For an `"added"` Page: `deepcopy` Source's `PageNode.element`, then append it to Target's `Presentation/Pages` container element (`target.tree.getroot().find("Presentation/Pages")`) — position among siblings is not semantically meaningful for top-level Pages (per the original design spec's §3.2: "Page order was confirmed to be arbitrary/meaningless"), so appending at the end is correct and requires no positional reasoning.

For an `"added"` Detail: `deepcopy` Source's `DetailNode.element` (the outer `<Detail>` element, already containing its nested `<Page>` and everything under it), then append it to the resolved parent Page/Detail's `Details` container element (`parent_element.find("Details")`, creating a new empty `<Details>` child element first via `etree.SubElement(parent_element, "Details")` if the parent currently has none — a Page/Detail with zero existing Details today would have no `<Details>` element at all, per the parser's own `_parse_details`: `if details_container is None: return []`). Sibling order among Details is not called out as meaningful anywhere in the original design spec or either prior sub-project spec (unlike top-level Page order, this was never explicitly confirmed either way) — appending at the end is adopted here as the simplest, least-surprising default in the absence of any stated ordering requirement, consistent with how top-level Pages are handled.

For an `"added"` Column: `deepcopy` Source's `ColumnNode.element`, then append it to the resolved parent's relevant Column-list container. This needs one piece of care the Page/Detail cases don't: per the original design spec's §2.2, a single field is referenced by `fieldName` across up to ~10 different context-specific lists (`List`, `View`, `Edit`, `Insert`, `QuickFilter`, `FilterBuilder`, `Print`, `Export`, `Compare`, `MultiEdit`, `DefaultSortedColumns`, all nested under the parent's `Columns` container) — but the model layer's own `_parse_columns` (per `parser.py`) only ever reads from `ColumnPresentations` → `ColumnPresentation`, a single flat list, not from any of those ~10 context lists. Since `ColumnNode`/`Difference(node_kind="column")` is defined and produced entirely in terms of `ColumnPresentation`, "the target element for a Column add/remove/change" always means an element inside `ColumnPresentations`, never one of the ~10 `Columns`-nested lists — those are simply outside this model layer's (and therefore this sub-project's) current reach, exactly as they're outside the differ engine's reach today (the differ engine's own §2.1/§3.2 scope is explicitly "all four node kinds the model layer produces," and the model layer doesn't parse the `Columns` sub-lists at all). `deepcopy`'d Column elements are appended to the resolved parent's `ColumnPresentations` container.

For an `"added"` Event: `deepcopy` Source's `EventNode.element`, then append it to the resolved parent's `EventHandlers` container (creating one via `etree.SubElement` if absent, mirroring the Details case).

## 6. The `.bak` backup mechanism

**Decision: the backup is written immediately before any mutation is serialized to the Target path, named `<original_target_path>.bak` in the same directory as Target, and a pre-existing `.bak` from an earlier merge session is silently overwritten (not versioned).**

Concretely: `shutil.copy2(target_path, target_path + ".bak")`, called once, right before `etree.tostring(target.tree, ...)` is written out to `target_path` — i.e. after every `Difference` has been successfully applied to the in-memory tree (§7.3's all-or-nothing gate has already passed) but before that mutated tree touches disk at all. This ordering guarantees the backup always reflects a real, complete, valid pre-merge Target file — never a half-written one — and that a backup is never created for a merge attempt that ultimately fails validation/application (no point backing up a file that's about to be left completely untouched, per §7.3).

**Reasoning — naming, no versioning:** This directly mirrors the existing translator toolchain's own convention (per the original design spec's §2.6/§6.1: "same convention as the existing translator toolchain"), which the original design spec already committed to as the established pattern for this exact kind of safety net in this codebase. A single, fixed `.bak` name (not `.bak.1`, `.bak.2`, timestamped, etc.) is the simplest possible implementation and matches the stated intent precisely: "an automatic `.bak` backup of the pre-merge Target kept first... not a one-way door" describes recovery from **the most recent merge**, not an audit trail of every merge ever performed on a file. Versioning would add real complexity (numbering scheme, retention/cleanup policy, disk-space growth on a file edited repeatedly over months) to solve a problem nobody asked for — if a developer wants durable historical snapshots beyond "undo my last merge," that's exactly what version control is for, and this codebase's own scope explicitly declined to build VCS-like machinery into the tool (original design spec §3.2: "there is no VCS underneath the current workflow, and the team does not want the tool to introduce implicit checkout/base-tracking"). A silently-overwritten single `.bak` is consistent with that same philosophy — this tool doesn't try to be a lightweight VCS, even for its own safety net.

**Reasoning — timing (right before the disk write, after all in-memory mutation succeeds):** Backing up any earlier than this (e.g. the moment "Apply Changes to Target" is clicked, before any difference has even been resolved/applied) risks writing a `.bak` for a merge attempt that then fails entirely and writes nothing to Target — which would leave a stale, confusing `.bak` sitting next to a completely unchanged Target file, implying a merge happened when it didn't. Waiting until immediately before the real write (after the all-or-nothing gate has already confirmed every checked difference resolved and applied cleanly in memory) means a `.bak` only ever appears at the same moment Target itself is about to actually change — the two are inseparable in time, which is the clearest possible signal to a developer about what that `.bak` file represents and when.

## 7. "Apply Changes to Target" — the end-to-end flow

### 7.1 Reading checked differences off `DiffMergePanel`

**Decision:** a new method, `DiffMergePanel.checked_differences() -> list[Difference]`, walks the same flattened-leaves traversal `select_next_difference`/`select_previous_difference` already use (`_flattened_leaves()`, per the viewer-UI's existing implementation) and returns the `Difference` object (via `item.data(0, DIFFERENCE_ROLE)`) for every leaf whose `item.checkState(0) == Qt.CheckState.Checked`.

```python
def checked_differences(self) -> list["Difference"]:
    return [
        leaf.data(0, DIFFERENCE_ROLE)
        for leaf in self._flattened_leaves()
        if leaf.checkState(0) == Qt.CheckState.Checked
    ]
```

**Reasoning:** `_flattened_leaves()` already exists, already correctly filters group/prefix nodes out (via the `DIFFERENCE_ROLE` check), and already walks the tree in the exact same order Next/Prev Difference use — reusing it for checked-state enumeration means "what counts as a leaf difference" is defined in exactly one place in this file, not two slightly-different tree-walks that could silently drift apart. "Checked" means exactly `Qt.CheckState.Checked` — a leaf's checkbox in the viewer UI has no third/partial state (partial/tristate checkboxes only make sense on parent nodes summarizing mixed-state children, and per the viewer-UI spec's §3.6, "Intermediate group nodes... are plain, non-checkable `QTreeWidgetItem`s — only leaves... are checkable"), so there's no ambiguity to resolve here about what "checked" means.

### 7.2 Ambiguous differences: apply is refused entirely if any checked difference is ambiguous

**Decision:** if any difference in the checked set has `ambiguous=True`, "Apply Changes to Target" refuses to apply **any** of the checked differences (not just skips the ambiguous ones) and shows a `QMessageBox.critical` naming every ambiguous checked difference by its leaf label and path, instructing the developer to uncheck the ambiguous item(s) and re-run Apply.

**Reasoning:** The task framing poses this exact tradeoff: refuse outright (requiring an ambiguity-resolution mechanism that doesn't exist yet) versus apply anyway with an extra warning. Given this whole project's repeatedly-stated ethos — "never a silent wrong result" appears verbatim in the original design spec's out-of-scope notes (§3.2) and is echoed throughout every prior sub-project's own design reasoning (e.g. the differ-engine spec's entire justification for the `ambiguous` flag: "surfacing it for manual review... rather than being silently trusted") — applying an ambiguous difference "with an extra warning" would mean the tool *knows* it might be pairing the wrong two Details/Events (per the differ engine's own positional-pairing fallback, which is a best-effort guess, not a confirmed match) and mutates the Target file anyway. A warning dialog a developer can click through is not meaningfully different from a silent wrong result if the developer is in a hurry, reviewing 40 checked differences in one Apply pass, and doesn't read every word of a warning that appears once. Refusing outright is the only choice that guarantees an ambiguous pairing never gets baked into Target without a human first either (a) unchecking it and applying everything else, or (b) manually verifying — outside this tool, by reading the two Details/Events side by side in the detail view already built in sub-project 2 — that the guessed pairing is actually correct, then re-checking it and re-running Apply once satisfied.

This is deliberately a **whole-batch refusal**, not "skip just the ambiguous ones and apply the rest silently" — because silently dropping some of what a developer explicitly checked (without them noticing which ones got skipped) is its own kind of silent-wrong-result risk, arguably a worse one than refusing outright, since the developer would walk away believing everything they checked got applied. Refusing the whole batch with a clear, itemized message is the option that can't be misread as partial success.

There is no mechanism today to "resolve" an ambiguity short of unchecking it (per the task framing's own observation — "there's no such resolution mechanism built yet"), so unchecking-and-reapplying is the only available recovery path, and this decision is designed around that being sufficient: the developer loses nothing by unchecking an ambiguous item and applying the rest in one pass, then separately deciding what (if anything) to do about the ambiguous one — possibly by hand-editing, possibly via a future ambiguity-resolution UI, possibly by simply accepting the guessed pairing after visual inspection and re-running Apply with it checked once more.

### 7.3 Partial-failure handling: all-or-nothing

**Decision: if any checked, non-ambiguous difference fails to resolve/apply (e.g. a `resolve_path` lookup fails because Target changed on disk since compare-time), the entire Apply is aborted and Target is left completely untouched on disk — no `.bak` is written, no partial write happens, and every difference that *would* have succeeded is also not applied.** A `QMessageBox.critical` reports every failure by its leaf label, path, and the specific error message, and reports that **no changes were made**.

**Reasoning:** The task framing explicitly asks to choose between all-or-nothing and best-effort-partial-apply, "given the 'never a silent wrong result' ethos." Best-effort partial application has a specific, concrete failure mode this codebase's own stated philosophy rules out: a developer checks 10 differences, clicks Apply, sees a dialog saying "7 succeeded, 3 failed" — and now has to reason about *which 7* actually landed, whether those 7 are safe to have applied without the other 3 (differences are not always independent — e.g. a Column `"changed"` difference inside a Detail whose own `"added"` difference failed to apply would leave a dangling, half-applied structure), and whether the resulting Target file is even in a coherent state at all. This is exactly the kind of partial, hard-to-reason-about result the project's error-handling philosophy (§7 of the original design spec: subprocess failures "never swallowed... reported as a failed generation, not silently treated as success"; Tier 1 validation's explicit refusal to leave a tree in a "blank/stale" ambiguous state) consistently avoids elsewhere.

All-or-nothing also has a much simpler, safer implementation path that directly follows from §3.2's architecture: `apply_differences` operates on a `copy.deepcopy` of Target's *entire* `lxml.etree._ElementTree`, not the live tree the currently-open `ProjectModel` still refers to. Every checked difference is applied to that disposable copy; if every single one succeeds, the copy *becomes* the tree that gets backed-up-and-written (§6, §7's step-by-step flow below); if any one fails, the copy is simply discarded and nothing about the real, currently-loaded Target `ProjectModel`/tree is ever touched. This sidesteps needing any hand-rolled "undo the mutations already applied to elements 1 through 6" logic entirely — there is nothing to undo, because the working copy that failed partway through is never the one written anywhere or kept around. The (fixed, one-time-per-Apply-attempt) cost of deep-copying a multi-megabyte `lxml` tree is negligible next to the cost of getting partial-failure semantics wrong in a tool whose entire purpose is protecting hand-maintained production configuration files.

### 7.4 The exact end-to-end flow (`main_window.py`)

Replacing the current `self._add_stub_action(menu, "Apply Changes to Target")` wiring in `_build_diff_merge_menu`:

```python
def _build_diff_merge_menu(self):
    menu = self.menuBar().addMenu("Diff / Merge")
    compare_action = menu.addAction("Compare / Merge Two Files...")
    compare_action.triggered.connect(self._compare_merge_two_files)
    menu.addSeparator()
    next_action = menu.addAction("Next Difference")
    next_action.triggered.connect(self.center_stage.diff_merge_panel.select_next_difference)
    prev_action = menu.addAction("Prev Difference")
    prev_action.triggered.connect(self.center_stage.diff_merge_panel.select_previous_difference)
    apply_action = menu.addAction("Apply Changes to Target")
    apply_action.triggered.connect(self._apply_changes_to_target)


def _apply_changes_to_target(self):
    checked = self.center_stage.diff_merge_panel.checked_differences()
    if not checked:
        QMessageBox.information(self, "Apply Changes to Target", "No differences are checked to apply.")
        return

    ambiguous = [d for d in checked if d.ambiguous]
    if ambiguous:
        details = "\n".join(f"- {d.path} ({d.node_kind}/{d.attribute}: {d.kind})" for d in ambiguous)
        QMessageBox.critical(
            self, "Cannot Apply: Ambiguous Differences Checked",
            "The following checked differences are ambiguous (matched via "
            "positional pairing of duplicate siblings) and cannot be safely "
            "applied automatically. Uncheck them and re-run Apply, or verify "
            "the pairing by hand in the detail view first:\n\n" + details,
        )
        return

    target_project = self._current_target_project   # tracked since the compare was launched — see note below
    target_path = self._current_target_path

    working_tree = copy.deepcopy(target_project.tree)
    working_project = _rebind(target_project, working_tree)  # see note below
    result = apply_differences(working_project, checked)

    if result.failed:
        details = "\n".join(f"- {f.difference.path}: {f.message}" for f in result.failed)
        QMessageBox.critical(
            self, "Apply Failed — No Changes Written",
            f"{len(result.failed)} of {len(checked)} checked differences could not "
            f"be applied (Target may have changed since this comparison was run). "
            f"No changes were written to '{target_path}'.\n\n" + details,
        )
        return

    backup_path = target_path + ".bak"
    shutil.copy2(target_path, backup_path)
    serialized = etree.tostring(working_tree, xml_declaration=False, encoding="UTF-8", pretty_print=False)
    with open(target_path, "wb") as f:
        f.write(serialized)

    QMessageBox.information(
        self, "Apply Changes to Target",
        f"Applied {len(checked)} change(s) to '{target_path}'.\nBackup saved to '{backup_path}'.",
    )
    self.open_project_file(target_path)   # see §7.5 — reload Target after a successful merge
```

**Note on tracking "the current Target project/path":** none of the three entry points in sub-project 2 currently retain a reference to the *Target* project/path after building the `Difference` list and handing it to `show_differences` — each entry point's Target is a local variable that goes out of scope once the comparison is shown. This sub-project adds that retention: `_compare_merge_two_files`, `_compare_page_with`, and `_compare_detail_with` are each extended to also stash `self._current_diff_target_project = target` and `self._current_diff_target_path = target_path` right alongside their existing `show_differences` call, mirroring exactly the pattern sub-project 2 already established for `self._current_project`/`self._current_project_path` (§3.5 of the viewer-UI spec) — the same reasoning applies unchanged: `_apply_changes_to_target` needs to know which file Target actually was, and nothing upstream currently remembers it past the point of building the change-list.

**Note on `_rebind`:** `copy.deepcopy(target_project.tree)` produces a fully independent `lxml` document, but the existing `ProjectModel`/`PageNode`/etc. objects' `.element` references still point at the *original* (pre-copy) elements, not the copy. A small helper re-walks the deep-copied tree the exact same way `load_project` already does (in fact, the simplest correct implementation is to serialize-then-reparse-from-the-copy is unnecessary and wasteful — instead, `_rebind` walks `working_tree` and `target_project` in lockstep, using `lxml`'s own guaranteed-stable document-order traversal (`tree.iter()`) on both the original and the deep copy simultaneously, to build a fresh `ProjectModel` whose `PageNode`/`DetailNode`/`ColumnNode`/`EventNode` objects are structurally identical to `target_project`'s own but with `.element`/`.inner_page_element` rebound to the corresponding elements in `working_tree` instead. This is mechanically simplest expressed as: call `load_project`-equivalent parsing logic directly against `working_tree.getroot()` (i.e. factor `load_project`'s existing element-walking body out from its `etree.parse(path)` call, so it can be invoked either on a freshly-parsed tree or on an already-in-memory one like this deep copy) rather than hand-writing a second lockstep-walk implementation — see §8 for this as an explicit, small refactor of `parser.py`.

### 7.5 Post-Apply: Target is reloaded automatically, not left for the user to manually reopen

**Decision: after a successful Apply (no failures, backup written, mutated tree serialized to `target_path`), `_apply_changes_to_target` calls `self.open_project_file(target_path)` — the same method `_open_project`'s file-picker flow already calls — to refresh the Project Tree, `self._current_project`, and `self._current_project_path` from the just-written file.** The change-list tree in `DiffMergePanel` is deliberately left showing the just-applied comparison as-is (not cleared, not automatically re-diffed) — see the second half of this decision below.

**Reasoning — reload Target automatically:** If the merged file happened to also be the currently-open project in the main tree (a very likely scenario, since `_compare_merge_two_files` defaults Source to `self._current_project` and a common workflow is "compare my local copy against the shared file, then merge my changes back into the shared file" — where the shared file being merged into, Target, might separately also be open for browsing), leaving the Project Tree showing stale, pre-merge data after a successful write would be actively misleading: right-clicking a Page in the tree to "Compare This Page With..." again, or just browsing Properties, would show attribute values that no longer match what's actually on disk. Reusing `open_project_file` costs nothing new to implement (it already exists, already handles parse-failure-after-merge defensively via its own existing `QMessageBox.critical` path, which would only fire here in the practically-impossible case that this sub-project's own just-written serialization is somehow not parseable by `load_project` — a strong internal-consistency check, not dead code) and removes an entire class of "did my last merge actually take effect" uncertainty a developer would otherwise have to resolve by manually reopening the file themselves.

**Reasoning — do NOT auto-re-diff and refresh the change-list tree:** The task framing separately raises this as its own question (§7 in the task list: "does the target file get reloaded/re-diffed after a successful Apply"). These are two different operations and this document makes two different calls on them: reloading Target into the main Project Tree (yes, per above) is cheap, unsurprising, and matches how every other successful mutation already behaves in this codebase (Open always repopulates the tree from a freshly-loaded `ProjectModel`). Automatically re-running `diff_project(source, freshly_reloaded_target)` and rebuilding the `DiffMergePanel`'s change-list tree immediately after Apply is a materially different, heavier operation this document explicitly does **not** do, for two reasons: first, it would silently discard the developer's just-finished review session — the checked/unchecked state of every *other* difference they hadn't gotten to yet (or had deliberately left unchecked as "skip this one, not now") disappears the instant the tree rebuilds, with no way to distinguish "this was already reviewed and skipped on purpose" from "this hasn't been looked at yet" in the fresh tree; second, per sub-project 2's own explicit scope note (§2.2 there: "Persisting Apply/Skip checkbox state across sessions, or between separate Compare invocations" is out of scope, "fresh, in-memory, per-comparison-session state only"), a change-list tree is already understood throughout this feature area as belonging to one comparison session — silently starting a *new* session automatically, as a side effect of Apply rather than a deliberate new "Compare" action, would blur that boundary in a way neither prior sub-project's design anticipated. If a developer wants to confirm "no differences remain" after a merge, or continue reviewing/applying more differences in a second pass, the existing "Compare / Merge Two Files..." entry point (re-run manually) already does exactly that, deliberately, as a fresh, explicit action — which is simpler and more honest about what just happened than an automatic, implicit re-diff would be.

## 8. A small, necessary refactor: `load_project`'s parsing body needs to be reusable on an in-memory tree, not only via a file path

Section §7.4's `_rebind` helper needs to run the model layer's own Page/Detail/Column/Event-walking logic against an already-in-memory `lxml.etree._ElementTree` (the deep copy), not read a path off disk and reparse it. `load_project`'s current shape (`etree.parse(str(path))` immediately followed by the walk) doesn't allow this. **Decision:** factor `load_project` into a thin path-handling wrapper plus an inner function that takes an already-parsed `tree`:

```python
def load_project(path) -> ProjectModel:
    try:
        tree = etree.parse(str(path))
    except (etree.XMLSyntaxError, OSError) as exc:
        raise PgtpParseError(f"Could not parse '{path}': {exc}") from exc
    return _build_project_model(tree, source_description=str(path))


def _build_project_model(tree, source_description: str) -> ProjectModel:
    root = tree.getroot()
    try:
        pages_container = root.find("Presentation/Pages")
        page_elements = [] if pages_container is None else pages_container.findall("Page")
        pages = [_parse_page(page_el, parent_identity=None) for page_el in page_elements]
    except Exception as exc:
        raise PgtpParseError(f"Could not parse '{source_description}': {exc}") from exc
    return ProjectModel(pages=pages, tree=tree)
```

`apply.py`'s `_rebind` helper (or, more precisely, `main_window.py`'s `_apply_changes_to_target`, per §7.4) calls `_build_project_model(working_tree, source_description=target_path)` directly on the deep-copied tree, getting back a fresh `ProjectModel` whose nodes' `.element`/`.inner_page_element` all correctly point into `working_tree` rather than the original. This is a small, mechanical refactor of existing code (splitting one function into two, no behavior change for the existing `load_project` call sites) rather than new parsing logic, and it's the natural consequence of §3.2's `.element`-retention decision: once nodes carry live element references, "re-derive a `ProjectModel` from a different-but-structurally-identical tree" becomes a real, needed operation this codebase didn't have a reason to support before.

## 9. Testing strategy

- **Unit tests for `apply.py`**, against small, synthetic `.pgtp`-shaped XML strings parsed via the (now dual-path) model layer — same style as the differ engine's and model layer's own synthetic-fixture tests, avoiding the large real sample files for per-case unit coverage:
  - A `"changed"` attribute difference on a Page, a Detail (both the outer-`<Detail>`-attribute case and the nested-`<Page>`-attribute case), and a Column — asserting the correct real `lxml` element's `attrib` is mutated and, critically, that **every other attribute on that element and every other element in the tree is untouched** (asserted via `etree.tostring` byte comparison against an independently-hand-mutated expected string, not just "the ProjectModel dataclass says the new value").
  - A `"changed"` event-handler text difference — asserting `element.text` is replaced exactly, with surrounding elements untouched.
  - An `"added"` Page, Detail (including one with its own nested Details, to confirm the whole deep-copied subtree survives insertion intact), Column, and Event — asserting the new element appears in the correct container, with all of its original attributes/children/text intact (i.e. the `deepcopy`-from-Source approach didn't lose or corrupt anything).
  - A `"removed"` Page, Detail, Column, and Event — asserting the element (and, for a Detail, everything nested under it) is gone from the resulting tree and nothing else changed.
  - The duplicate-sibling `ambiguous=True` case: asserting `apply_differences` is never even reached for these in the `main_window.py` flow (covered by the `_apply_changes_to_target` test below), but also asserting directly that `apply.py` itself has no special-cased "ignore ambiguous" logic of its own — the ambiguity gate is entirely `main_window.py`'s responsibility (§7.2), keeping `apply.py` simple ("apply whatever list of differences you're handed") is itself a design choice worth a regression test asserting `apply_differences` doesn't silently filter anything based on `.ambiguous`.
  - A failing `resolve_path` lookup mid-list (simulating Target having changed since compare-time) — asserting `ApplyResult.failed` contains the right `ApplyFailure` and that differences *before* the failing one in the list are still reflected in `ApplyResult.applied`, but critically that the **tree itself** (not just the result object) reflects every application attempted before the failure was hit, since it's the caller's (`main_window.py`'s) job per §7.3 to discard the whole working copy on any failure, not `apply_differences`'s job to roll anything back itself.
- **Round-trip fidelity regression tests**, directly encoding this document's own §4 empirical findings so a future `lxml` upgrade or an accidental change to the adopted `tostring` settings can't silently regress it:
  - Load each real sample file, immediately reserialize with the exact settings adopted in §4.4/§8 (`xml_declaration=False, encoding="UTF-8", pretty_print=False`), and assert the result is byte-identical to the original **after** normalizing away the one known residual difference category (i.e. the test itself performs the same "replace `&quot;` with `"` inside element text only, never inside attribute values" normalization used to characterize the difference in §4.3, then asserts full equality) — this pins down that no *new* difference category has crept in, while not treating the already-understood, benign one as a failure.
  - A stricter, complementary test: load each real sample file, apply **zero** differences (an empty checked-list Apply — exercising the exact code path §7's flow uses, not a bespoke direct-`tostring` call), and assert the resulting written-out file, loaded back through `load_project` and diffed against the original via `diff_project`, produces an **empty** difference list — a true end-to-end "no-op merge changes nothing meaningful" regression test, layered on top of the differ engine's own existing "diff a file against itself is empty" test (differ-engine spec §4) and directly satisfying the original design spec's own stated deferred-work item (§8: "load a sample, save unchanged, byte-diff against the original").
- **`pytest-qt` tests for `DiffMergePanel.checked_differences()`**: build the tree from a synthetic `list[Difference]`, check some leaves via `setCheckState`, assert `checked_differences()` returns exactly the checked ones in tree order, and that group/prefix nodes (which have no `Difference` payload at all) never appear in the result.
- **`pytest-qt` / integration tests for `_apply_changes_to_target`** end-to-end, using real temp-directory files (a small synthetic Source/Target pair, not the large real samples, for speed):
  - A successful Apply: checks a handful of non-ambiguous differences, runs the full handler, and asserts (a) a `.bak` file appears at the expected path with the pre-merge byte content, (b) the Target file at its original path now reflects every applied change and nothing else, (c) the Project Tree/`self._current_project` is refreshed to the post-merge state (§7.5), and (d) the `DiffMergePanel`'s change-list tree is unchanged from before Apply was clicked (asserting the "do NOT auto-re-diff" decision in §7.5 holds).
  - Re-running the exact same successful-Apply scenario a second time (simulating "Apply Changes to Target" clicked twice on the same comparison without re-comparing) asserts the second run's `.bak` file now contains the **first run's already-merged** Target content (i.e. confirming the "silently overwrite the previous `.bak`" naming decision from §6 behaves as documented, not accidentally preserving only the very first pre-merge state across repeated Apply clicks).
  - The all-checked-differences-are-ambiguous case and the mixed ambiguous/non-ambiguous case: both assert `QMessageBox.critical` is shown, **no** `.bak` file is created, and the Target file on disk is byte-identical to before the Apply attempt.
  - A simulated partial-failure case (constructing a checked-differences list where one difference's `path` deliberately doesn't resolve against the Target fixture, simulating a concurrent external edit) — asserting no `.bak` is created, the Target file is untouched, and the failure dialog names the specific unresolvable difference.

## 10. Summary of decisions

This document resolves the seven open judgment calls the task explicitly called out, plus several more that surfaced while working through them in enough detail to leave nothing ambiguous. As in the Annotate Schema Values UI spec's own closing section, each entry below stands in for a question a human would ordinarily have been asked directly:

1. **Round-trip approach: retain the real `lxml.etree.Element` on every parsed node (`PageNode`/`DetailNode`/`ColumnNode`/`EventNode` gain an `element` field, `DetailNode` additionally gets `inner_page_element`, `ProjectModel` gains a `tree` field) and mutate those retained elements directly, rather than building an independent from-scratch serializer off the `ProjectModel` dataclasses.** The dataclass layer was deliberately built to flatten/generalize (§2.2 of the Real Model spec: "captures attributes generically... rather than a curated subset"), which is exactly what makes it unsuitable as the sole source for reconstructing a byte-faithful file — it has already discarded sibling ordering, whitespace, and entire element categories (`DataSources`, `Groups`, `PartitionNavigators`, etc.) the parser doesn't even read yet. Mutating the real, retained elements and serializing the whole real tree in one pass means everything not explicitly touched is trivially, automatically preserved, because it *is* the original tree.
2. **Empirical round-trip fidelity result: clean, with one small, fully-characterized, cosmetically-inert exception.** With `etree.tostring(tree, xml_declaration=False, encoding="UTF-8", pretty_print=False)`, both real sample files round-trip byte-for-byte except that redundant `&quot;` escaping *inside element text content* (never inside attribute values, where it's structurally required and always preserved) gets normalized to a literal `"` by `libxml2`'s serializer. This was measured directly (not assumed), root-caused to a specific, well-understood serializer behavior via a minimal repro, quantified precisely (680/696 and 798/824 occurrences in the two sample files, fully accounting for the entire observed byte-length delta in each), and confirmed to have no semantic effect on the underlying PHP/JS code it appears in. No fundamental blocker was found; this exact `tostring` call is what this document's Apply flow uses.
3. **`resolve_path` is reused unchanged, not reimplemented at the lxml level.** Once `resolve_path` returns a `PageNode`/`DetailNode`, that node's own newly-retained `.element` is the real element to mutate — no second, parallel path-walking implementation is needed. A small, genuinely new (not duplicated) lookup step is added in `apply.py` for the one level `resolve_path` doesn't cover: finding a Column/Event within an already-resolved Page/Detail.
4. **`.bak` backup: written immediately before the mutated tree is serialized to disk (after all checked differences have successfully applied to an in-memory working copy), named `<target_path>.bak`, silently overwriting any previous `.bak` from an earlier merge session — no versioning.** Matches the existing translator toolchain's established convention referenced directly in the original design spec, and deliberately avoids building VCS-like retention machinery this project has already explicitly declined to take on elsewhere.
5. **Ambiguous checked differences: Apply is refused entirely (not applied-with-a-warning, and not silently skipped while applying the rest) if any checked difference has `ambiguous=True`.** Given no ambiguity-resolution UI exists yet, and given this project's consistent "never a silent wrong result" ethos, a warning a developer can click past is not meaningfully safer than silence, and silently skipping just the ambiguous ones risks the developer believing everything they checked was applied. Refusing the whole batch, with every ambiguous item named explicitly, is the only option that can't be misread as partial success — the developer simply unchecks the ambiguous item(s) and re-runs Apply.
6. **Partial-failure handling: strictly all-or-nothing.** If any checked, non-ambiguous difference fails to resolve/apply (e.g. Target changed on disk since compare-time), the entire Apply is aborted, Target is left completely untouched, no `.bak` is written, and every failure is named in one dialog. Implemented cleanly by applying all differences to a disposable `copy.deepcopy` of Target's tree and only ever writing/backing-up that copy if every single difference succeeded — avoiding any need for hand-rolled partial-mutation rollback logic. Chosen over best-effort partial application because a "7 of 10 succeeded" result forces the developer to reason about whether the 7 that landed are even coherent without the 3 that didn't, which directly conflicts with this project's established error-handling philosophy of never leaving an ambiguous, hard-to-reason-about partial result.
7. **End-to-end flow:** a new `DiffMergePanel.checked_differences()` method (reusing the existing `_flattened_leaves()` traversal) feeds a real `_apply_changes_to_target` handler in `main_window.py`, replacing the stub — gather checked differences → refuse if any are ambiguous → apply all to a disposable deep-copied working tree → refuse (all-or-nothing) if any application fails → write `.bak` → serialize and write Target → report success via `QMessageBox.information` (or failure via `QMessageBox.critical`, at every failure point, never silently) → reload Target into the main Project Tree.
8. **Post-Apply: Target is automatically reloaded into the main Project Tree (via the existing `open_project_file`) after a successful merge, but the `DiffMergePanel`'s change-list tree is deliberately left showing the just-completed comparison as-is — it is not automatically cleared or re-diffed.** Reloading the tree avoids the main window silently showing stale pre-merge data. Not auto-re-diffing avoids two problems at once: silently discarding the developer's in-progress checked/unchecked review state for differences not yet acted on, and blurring the "one comparison session" boundary sub-project 2 already established for checkbox state. A developer who wants to confirm "no differences remain," or continue reviewing more differences, re-runs "Compare / Merge Two Files..." explicitly.
9. **A small, mechanical refactor of `load_project`** (splitting it into a thin path-reading wrapper plus an inner `_build_project_model(tree, ...)` that accepts an already-parsed tree) is required to support re-deriving a `ProjectModel` (with correctly-rebound `.element` references) from the deep-copied working tree used during Apply, per decision 6 above. This is a byte-for-byte-behavior-preserving refactor for every existing `load_project` call site, not new parsing logic.
10. **New-element insertion for `"added"` differences uses `copy.deepcopy` of Source's own retained real element, not hand-constructed new elements.** For the same fidelity reasoning as decision 1: deep-copying a real, already-correctly-formed element (attribute order, escaping, any content the model layer doesn't itself parse) preserves it automatically; reconstructing it field-by-field from the `ProjectModel` dataclass would require the model layer to capture everything about an element generically, which it deliberately does not.
11. **Insertion position for added subtrees defaults to "append at the end of the relevant container"** for Pages (explicitly confirmed arbitrary/meaningless per the original design spec), Details (never explicitly addressed either way in any prior document, so the same simplest-and-least-surprising default is adopted by extension), Columns, and Events — no positional/ordering logic is introduced, since nothing in this feature area's scope has ever called for one.
