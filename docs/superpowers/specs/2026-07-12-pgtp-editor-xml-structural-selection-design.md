# PGTP Editor — XML Structural Selection (XML Editor Sub-project D/5) Design Specification

**Date:** 2026-07-12
**Status:** Approved for planning
**Depends on:** [2026-07-12-pgtp-editor-xml-editor-foundation-design.md](2026-07-12-pgtp-editor-xml-editor-foundation-design.md) (XML Editor sub-project A — `pgtp_editor/ui/xml_structure.py`'s `TagSpan`/`scan()`/`find_enclosing_open_tag()`/`nesting_depth_at()`, and `pgtp_editor/ui/xml_editor.py`'s `XmlEditor(QPlainTextEdit)` widget, its gutter/folding/`_fold_state`, and its existing `setExtraSelections` usage for current-line highlighting). Sub-project A is still being implemented in a sibling worktree at the time this document is written — its code does not exist in this worktree — so this document designs against sub-project A's **spec**, not its shipped implementation. [2026-07-11-pgtp-editor-design.md](2026-07-11-pgtp-editor-design.md) (original shell design — §6.2 "Move / Copy," now obsolete, and §6.5 "Client (read-only) page generation," also obsolete, both superseded by this sub-project per the persistent project memory note described in §1.2 below).

## 0. A note on how this document was produced

This document was **not** produced from an interactive brainstorming transcript. It was assigned directly as a scoped follow-on task with an explicit list of design questions to resolve, in the same spirit as the Annotate Schema Values UI spec and the Diff/Merge Write-Back spec (see either document's own §0): "make and document every necessary design decision yourself, with clear justification, rather than leaving anything as an open question." Nothing below is a placeholder or an "open question for later" — every judgment call the task called out (the two new `xml_structure` query functions and their algorithms, Ctrl+Shift+B's exact selection boundaries including self-closing tags and ambiguous-whitespace cursor positions, Ctrl+Shift+A's no-parent and stateless-invocation behavior, matching-tag-highlighting mechanics and its coexistence with current-line highlighting in `setExtraSelections`, the folded-copy/paste correctness guarantee and its test, and the keyboard-shortcut wiring mechanism) is made explicitly here, with reasoning, and all of them are collected again in §11 ("Summary of decisions") exactly as if a human had been asked each question in turn and had answered it.

One piece of this task is a **hard, explicitly-flagged correctness requirement**, not an ordinary judgment call: copying or cutting a folded/collapsed block must yield its full underlying text, not the visually-collapsed placeholder. The user's own words, preserved in this project's persistent memory (`pgtp_move_copy_obsolete.md`): "IF!!! I can also copy/cut a folded structure and paste it! that's important." §7 of this document treats that requirement as load-bearing and designs, and specifies a test for, exactly why the chosen approach satisfies it — this is not treated as "probably fine" anywhere below.

## 1. Context and scope

### 1.1 This is sub-project D of 5

XML Editor sub-project A's own §1 laid out a 5-part feature, sequenced by dependency:

1. **Editor foundation** (sub-project A, in progress in a sibling worktree, not yet merged) — the `XmlEditor` widget itself and the `xml_structure` tag-position scanner.
2. **Bookmarks** (sub-project B, not designed) — gutter-click bookmark set/clear, `Ctrl+Alt+Up`/`Down` navigation.
3. **Search & Replace** (sub-project C, not designed) — `Ctrl+F`/`Ctrl+R`, selection pre-fill.
4. **XML structural selection** (**this document**, sub-project D) — `Ctrl+Shift+B`/`Ctrl+Shift+A` block and parent-block selection, plus matching-tag highlighting.
5. **Schema integration** (sub-project E, not designed) — XSD-driven "Add new..." context menu, schema-aware hover tooltips, advisory inline validation.

Sub-project A's own §3.1 explicitly anticipated this document: "the future XML structural-selection sub-project... is expected to need 'the `TagSpan` enclosing position N' and 'the `TagSpan` one level up from a given `TagSpan`' — both are direct consequences of the stack-based `scan()` output and require no new scanning logic, only a new query function over the existing `list[TagSpan]`." §3 of this document is exactly that anticipated pair of query functions, and confirms sub-project A's prediction: no change to `scan()` itself is needed.

### 1.2 Why this sub-project is load-bearing for two originally-planned features, not just a selection convenience

The original design spec's §6.2 ("Move / Copy") specified a dedicated in-tool feature for moving/copying `Detail` subtrees (and copying `Page` subtrees) via a tree-UI clipboard mechanism, complete with FK-mapping audit flags and cross-file paste conflict handling. Its §6.5 ("Client (read-only) page generation") specified cloning a `Page` subtree in-place and rewriting its ability attributes to read-only codes.

Per this project's persistent memory (`pgtp_move_copy_obsolete.md`, recorded during brainstorming for the overall XML Editor feature): **the user decided both of those features are superseded by exactly this sub-project's capability** — select a structural block via keyboard, copy or cut it with the OS's own clipboard mechanism, and paste it by hand wherever it belongs (same file, a different tab, or even a different application). §6.2's dedicated Move/Copy dialog/menu feature and §6.5's in-tool page-cloning feature are both therefore **obsolete and not built as separate features**; this document's Ctrl+Shift+B/A selection plus ordinary `Ctrl+C`/`Ctrl+X`/`Ctrl+V` is the entire replacement. This reframes the stakes of getting this document right: an implementation bug here (most acutely, the folded-copy truncation risk in §7) would not just be an inconvenience in a nice-to-have selection shortcut — it would silently break the *only* remaining path to two originally-planned, real workflows (moving/copying `Detail` blocks; producing read-only client-page clones by hand). This document treats §7 accordingly, as the single most important section here.

Note what this reframing does **not** do: it does not resurrect any of §6.2/§6.5's own scope (FK-mapping audit flags, automatic ability-code rewriting, fileName-uniqueness paste prompts, cross-file-tab clipboard sharing UI). Those were features built *around* a copy/paste primitive that the vendor GUI lacked; now that the primitive itself (structural select + the OS clipboard) is available directly to the user, the surrounding bespoke tooling is simply no longer needed — a developer doing a Detail move now does it by hand, the same way they'd move a paragraph in a text editor. Nothing in this document reimplements FK-mapping awareness or ability-code rewriting; those remain genuinely dropped scope, not silently relocated into this document.

## 2. Scope

### 2.1 In scope

- Two new query functions in `pgtp_editor/ui/xml_structure.py`, built on the existing `TagSpan`/`scan()` output with no changes to `scan()` itself (§3):
  - `enclosing_tag_span(text, position) -> TagSpan | None`
  - `parent_tag_span(spans, span) -> TagSpan | None`
- `XmlEditor.select_enclosing_block()` (`Ctrl+Shift+B`) and `XmlEditor.select_parent_block()` (`Ctrl+Shift+A`) (§4, §5).
- Matching-tag highlighting: when the cursor is on/in an opening or closing tag, highlighting both that tag and its structural counterpart via `setExtraSelections`, coexisting correctly with sub-project A's current-line highlighting (§6).
- The folded-copy/paste correctness guarantee: precise design of how the block-select `QTextCursor` is constructed, and a test proving folded content survives copy/cut/paste undamaged (§7).
- `QShortcut` wiring for both new commands on `XmlEditor` (§8).
- Unit tests for the two new `xml_structure` functions and `pytest-qt` tests for the editor-level behavior (§9).

### 2.2 Explicitly out of scope

- **Bookmarks** (sub-project B), **Search & Replace** (sub-project C), **schema integration** (sub-project E) — not this document.
- Any change to sub-project A's already-specified syntax highlighting, gutter, folding (`_toggle_fold`, `_fold_state`), line-wrap, current-line highlighting, auto-indent, or auto-close behavior. This document only **adds** new capability that consumes `xml_structure`'s primitives and `XmlEditor`'s existing structure; it does not modify anything sub-project A already defined. Where this document's new matching-tag highlighting needs to coexist with sub-project A's current-line highlighting inside the single `setExtraSelections` list, §6 designs that coexistence as an addition, not a rewrite, of sub-project A's `_highlight_current_line`.
- Any change to `pgtp_editor.model` (the `lxml`-based `ProjectModel`/tree). This is purely a raw-text-editor-level feature operating on `XmlEditor`'s plain text content — it has no awareness of, and makes no changes to, the parsed model layer.
- Re-implementing or resurrecting any part of the original design's obsolete §6.2 (Move/Copy dialog, FK-mapping audit flags, cross-file paste-conflict prompts) or §6.5 (client-page cloning, ability-code rewriting) — see §1.2. This document's job ends at "select a block correctly, and don't corrupt copy/cut/paste of a folded one." What a developer subsequently does with that selection (paste it into a `Details` list by hand, rewrite an ability attribute by hand) is manual editing work with the tools this document provides, not a feature this document automates.
- Multi-cursor or multi-selection support of any kind — `Ctrl+Shift+B`/`Ctrl+Shift+A` always operate on the single active cursor position, matching every other command `XmlEditor` already implements (single-cursor throughout).
- Any visual "breadcrumb" or path indicator showing the current nesting chain (e.g. a status-bar `Page > Details > Detail > Page` trail). This would be a natural companion feature but was not requested, and does not follow as a consequence of anything requested here (it would need its own design for placement, update timing, and interaction with folding) — not designed here.

## 3. `xml_structure.py` additions

### 3.1 Design question: how does a caller find "the enclosing block" and "one level up" without re-scanning or a naive walk?

`scan()` already produces a `list[TagSpan]` in the order spans are *emitted* — which, per sub-project A's stack-based algorithm (§3.1 of that document), is not the same as document order or depth order: a `TagSpan` is emitted either when its closing tag is found (innermost spans close before outer ones do, so `scan()`'s output is essentially **emission-order**, which for well-formed nesting is "closing tag encountered" order) or, for self-closing tags, immediately in document order, or, for anything left open at end-of-input, in stack order at EOF. This matters because it rules out the tempting shortcut "just take the span immediately before/after this one in the list" — adjacency in `scan()`'s output list has no reliable structural meaning.

**Decision:** both new functions operate over the **full `list[TagSpan]`** sub-project A's `scan()` already returns, doing a **single linear pass** over it — no re-scanning of the text, and no new stack machinery. This is a deliberate "simplicity over premature optimization" choice, explicitly weighed against the realistic document size this tool operates on: the original design spec's own reference file (`docs/schema.xsd`, cited elsewhere in this project's specs at "16,600+ lines") is the upper bound of structural complexity anyone here deals with, and even a `.pgtp` project file with hundreds of `Page`/`Detail`/`ColumnPresentation` elements yields a `TagSpan` list in the hundreds-to-low-thousands, not millions — a linear scan over that list on every Ctrl+Shift+B/A keypress (an explicit user action, not a per-keystroke hot path like folding's re-scan) is imperceptible. Building a secondary indexed structure (an interval tree, a parent-pointer map maintained incrementally) would be real, nontrivial machinery to maintain in sync with `scan()`'s own re-runs, for a performance problem that does not exist at this document's realistic scale. If a future profiling pass on a pathological file ever shows otherwise, that is a reason to revisit — not a reason to build the more complex version now.

### 3.2 `enclosing_tag_span(text, position) -> TagSpan | None`

```python
def enclosing_tag_span(text: str, position: int) -> TagSpan | None:
    """Return the innermost TagSpan that structurally contains `position`,
    i.e. the block Ctrl+Shift+B would select if the cursor were at `position`.

    A TagSpan is a candidate if position falls anywhere within its full
    span, `[open_start, close_end)` for a span with a known close, or
    `[open_start, open_end)` for a self-closing span (whose "content" is
    empty) -- and, for a span with `close_end is None` (never closed, e.g.
    a truncated document or a genuinely unclosed tag), `position >=
    open_start` (there is no upper bound to test against, since the tag's
    true extent in the document is unknown; it is still the best available
    candidate for "what am I inside of").

    Among all candidates, the one with the greatest `depth` is returned
    (the innermost one -- the same "deepest containing element" rule
    `find_enclosing_open_tag` already uses). Ties in depth cannot occur
    for well-formed sibling spans (siblings never both contain the same
    position), so no further tie-break is needed.
    """
    best: TagSpan | None = None
    for span in scan(text):
        end = span.close_end if span.close_end is not None else (
            len(text) if span.self_closing is False else span.open_end
        )
        if span.open_start <= position < end or (
            span.close_end is None and not span.self_closing and position >= span.open_start
        ):
            if best is None or span.depth > best.depth:
                best = span
    return best
```

(The two overlapping conditions above are written out separately in the sketch for clarity of the two cases they cover — a real implementation collapses them into one cleaner boundary check; the important, load-bearing part is the *rule*, not this exact expression.)

**Why re-derive containment rather than calling `find_enclosing_open_tag` and looking it back up:** `find_enclosing_open_tag(text, position) -> str | None` (sub-project A) returns only a **name**, not a `TagSpan` — and a name is not enough to disambiguate when multiple same-named elements are nested or sibling at the same document (e.g. nested `Page` elements are not a real `.pgtp` shape, but nested same-named elements are not ruled out in general, and this function must be correct regardless of the specific schema in use, since `xml_structure` is schema-agnostic by design per sub-project A §3.1). `enclosing_tag_span` therefore does its own containment test directly against `TagSpan` offsets rather than layering on top of a name-returning helper and hoping the name is unique enough to look the right span back up — this avoids a subtle correctness gap that would otherwise exist only in edge cases involving repeated element names.

### 3.3 `parent_tag_span(spans, span) -> TagSpan | None`

```python
def parent_tag_span(spans: list[TagSpan], span: TagSpan) -> TagSpan | None:
    """Return the TagSpan exactly one nesting level up from `span` -- the
    block Ctrl+Shift+A selects, given the TagSpan Ctrl+Shift+B would have
    selected.

    The parent is the TagSpan with depth == span.depth - 1 whose span
    structurally contains `span` (open_start <= span.open_start and
    (its own close_end is None, or close_end >= span's own end)).
    Returns None if span.depth == 0 (no parent -- span is top-level).
    """
    if span.depth == 0:
        return None
    candidates = [s for s in spans if s.depth == span.depth - 1]
    for s in candidates:
        s_end = s.close_end if s.close_end is not None else len(spans and spans[-1].close_end or 0)
        if s.open_start <= span.open_start and (s.close_end is None or s.close_end >= (
            span.close_end if span.close_end is not None else span.open_end
        )):
            return s
    return None
```

This takes an explicit `spans: list[TagSpan]` parameter (the caller's already-computed `scan(text)` result) rather than re-taking `text` and re-scanning internally — the expected call pattern (§4) is "compute `enclosing_tag_span` once, then possibly `parent_tag_span` on its result," and there is no reason to force two independent `scan()` passes over the same text within a single user-initiated command when the caller already has the list in hand. `enclosing_tag_span`, by contrast, does take `text` (not a pre-computed list) because it is also usable as a one-shot standalone query (e.g. by a future consumer that doesn't already have a `scan()` result lying around) — this asymmetry mirrors sub-project A's own two exposed primitives, where `find_enclosing_open_tag` and `nesting_depth_at` both take `text` directly as one-shot conveniences, while a caller doing multiple related queries against one parse is expected to call `scan()` once itself. No caller inside `xml_editor.py` calls `parent_tag_span` without first having called `enclosing_tag_span` (or already possessing a `TagSpan`) and a `scan()` list, so the signature costs nothing in practice while avoiding a hidden double-scan.

**Correctness note on the depth-based approach:** since `scan()`'s stack-based construction guarantees `depth` is always exactly "how many open ancestor tags contain this span" (sub-project A §3.1's own algorithm description), "the candidate at `depth - 1` whose range contains this span's range" is guaranteed unique for well-formed XML — there is exactly one ancestor at each depth level above any given span. The containment check in the loop above is a defensive correctness check (protecting against the tolerant/malformed-input cases §3.1 already designs for, e.g. mismatched tags producing spans with `close_end=None` at unexpected depths), not strictly necessary for well-formed input, but kept because `xml_structure` must never assume well-formed input per its own founding design constraint (sub-project A §3.1: "the scanner has to keep working on exactly that kind of input, since it runs continuously while a user is mid-edit").

## 4. `Ctrl+Shift+B` — select enclosing block

### 4.1 Exact selection boundaries

**Decision:** the selection spans from the **first character of the opening tag's `<`** (`TagSpan.open_start`) through the **last character of the closing tag's `>`** (`TagSpan.close_end`, which sub-project A's `TagSpan` dataclass already defines as "character offset just past the matching `</name>`'s `>`" — i.e. `close_end` is already an exclusive end-offset one past that `>`, so the selection is `text[open_start:close_end]`, inclusive of both the opening `<` and the closing `>`). This applies uniformly to both an ordinary open/close pair and, per the case below, a self-closing tag.

**Self-closing tags:** for a `TagSpan` with `self_closing=True`, there is no separate close tag — `TagSpan.close_end` is already defined by sub-project A as equal to `open_end` in that case ("`close_end=open_end`" per §3.1's algorithm description). **Decision:** the selection for a self-closing tag is therefore simply `text[open_start:open_end]` — the entire `<Tag .../>` token, which is already exactly what "the whole block" means for an element with no children and no separate closing tag. No special-case code is needed in `XmlEditor` for this: `select_enclosing_block` always selects `text[span.open_start:span.close_end]` for whatever `TagSpan` `enclosing_tag_span` returns, and the self-closing case is already correct by construction because of how `TagSpan.close_end` is defined for that case. This is worth stating explicitly (rather than leaving it as an implicit consequence) precisely because it means **no conditional branch on `self_closing` is needed in the selection code at all** — a deliberate simplicity win that falls directly out of sub-project A's own `TagSpan` field semantics.

### 4.2 Cursor at a boundary, or in ambiguous whitespace between siblings

Two sub-cases the task calls out explicitly:

**Cursor exactly at a block's boundary** (e.g. immediately before the `<` that opens a block, or immediately after the `>` that closes one): `enclosing_tag_span`'s containment rule (§3.2) is `open_start <= position < end`. A cursor position exactly equal to `open_start` **is** included (selects that block); a cursor position exactly equal to `close_end` is **not** included in that span (it falls just past the block, at the boundary with whatever follows) — it would instead be considered as either inside whatever sibling/parent context comes next, or in the ambiguous-whitespace case below. This follows Qt's own convention for `QTextCursor.position()`, which denotes a position *between* two characters, not a character itself — "the cursor sitting at the boundary right after `</Detail>`'s final `>`" is the natural point where "am I still inside `Detail`" should read as false, matching how a text editor's own cursor-between-characters model already behaves for every other position-sensitive query in this codebase (e.g. `find_enclosing_open_tag`'s own boundary handling, sub-project A §3.1). No special-casing beyond what the containment rule above already produces is needed for this sub-case.

**Cursor in whitespace between sibling blocks at the same nesting level** (the task's own example: cursor sitting between `</Detail>` and the next `<Detail>`, both children of the same parent): at that exact position, there genuinely is **no enclosing `TagSpan`** whose `[open_start, close_end)` range contains it — the position falls in the parent's own "content" but between two child element ranges, so `enclosing_tag_span` correctly returns the **parent** span (the `Details`-list-holding element, or whatever container both sibling `Detail`s live under), not `None` and not either sibling by some fallback guess.

**Decision:** `Ctrl+Shift+B` in this position selects **the parent block** (whatever `enclosing_tag_span` actually returns — which, by the containment rule, is correctly the nearest ancestor whose range does contain that whitespace position, since an ancestor's own range extends across all of its children's whitespace gaps by definition). This is *not* a special "fall back to a nearby sibling" heuristic bolted on for this case — it is simply what `enclosing_tag_span`'s ordinary containment rule already produces, once one remembers that "no enclosing *child* block" is not the same as "no enclosing block at all": the parent's range still contains that position. **Justification for not guessing a nearby sibling instead:** guessing "the previous sibling" or "the next sibling" would require an arbitrary tie-break rule (which sibling? nearer by character distance? always the following one?) for a case that has a perfectly well-defined, unambiguous correct answer already — the parent. Inventing a heuristic to produce a *different* answer than the structurally correct one would be solving a problem that doesn't exist. The only genuine no-enclosing-block case is when the cursor sits **outside the document root entirely** (e.g. in leading/trailing whitespace before the first top-level element or after the last one, if such whitespace exists) — `enclosing_tag_span` correctly returns `None` there, and `Ctrl+Shift+B` is a **no-op** in that position (§4.3).

### 4.3 No-op conditions

`select_enclosing_block()` is a no-op — the existing selection (if any) is left untouched, no error/status message is shown, matching the "quiet no-op for a command that doesn't apply right now" convention already implicit in how sub-project A's auto-close logic silently does nothing when its own preconditions aren't met — when `enclosing_tag_span(text, cursor_position)` returns `None`: the cursor is genuinely outside every element in the document (root-level leading/trailing whitespace, or an empty document).

## 5. `Ctrl+Shift+A` — select parent block

### 5.1 No-parent case

**Decision:** if the cursor is inside a top-level element with no enclosing tag above it (`enclosing_tag_span(text, position)` returns a `TagSpan` with `depth == 0`, so `parent_tag_span` returns `None`), `Ctrl+Shift+A` is a **no-op** — it does *not* fall back to selecting the whole document.

**Justification:** the task explicitly offers "no-op" or "select the whole document" as the two candidate behaviors and asks for a pick. No-op is chosen because "select the whole document" is not actually "one level up from the current block" in any structural sense — it would be a fabricated behavior bolted onto a command whose entire identity is "go up exactly one level of nesting." A user who has just selected a top-level `Page` block via Ctrl+Shift+B (or directly via Ctrl+Shift+A, per §5.2) and presses Ctrl+Shift+A again has, by definition, nowhere structurally left to go — there is no XML element one level up from a top-level element; the document root itself is not a `TagSpan` at all (it's an artifact of "everything at depth 0," not an actual tag). Silently doing nothing communicates "you're already at the top" far more honestly than silently expanding the selection to the entire file, which could easily be mistaken for a successful "go up one level" that happens to have selected a large amount of text, inviting an accidental whole-file cut. `Ctrl+A` (unmodified) already exists as the standard, unambiguous "select all" command in every text widget including this one — there is no need for `Ctrl+Shift+A` to duplicate that meaning as a fallback.

### 5.2 Statelessness: `Ctrl+Shift+A` does not depend on a prior `Ctrl+Shift+B`

**Decision:** `Ctrl+Shift+A`, invoked directly (with no prior Ctrl+Shift+B in the same interaction), behaves identically to "compute the block Ctrl+Shift+B would select at the current cursor position, then select **its** parent" — i.e. it is defined purely as a function of the current cursor position, never of whatever `XmlEditor`'s current selection happens to already be.

```python
def select_parent_block(self) -> None:
    text = self.toPlainText()
    position = self.textCursor().position()
    spans = xml_structure.scan(text)
    enclosing = xml_structure.enclosing_tag_span(text, position)
    if enclosing is None:
        return  # cursor outside every element -- nothing to select, nothing to go up from
    parent = xml_structure.parent_tag_span(spans, enclosing)
    if parent is None:
        return  # already at a top-level element -- no parent, §5.1
    cursor = self.textCursor()
    cursor.setPosition(parent.open_start)
    cursor.setPosition(parent.close_end, QTextCursor.MoveMode.KeepAnchor)
    self.setTextCursor(cursor)
```

**Justification for statelessness over "one level up from whatever is currently selected":** the task itself flags this as "the more robust, stateless design" and asks for justification, so here it is concretely: a selection-state-dependent design (tracking "the last block-select command's result" as separate mutable state on `XmlEditor`, then having Ctrl+Shift+A walk up *from that remembered state* rather than from the cursor) introduces a whole new failure surface that a stateless design simply does not have:

- **What happens if the user manually changes the selection between the two commands** (e.g. Ctrl+Shift+B, then clicks somewhere else, or drags to extend/shrink the selection, then presses Ctrl+Shift+A)? A state-tracking design has to define an answer — does it ignore the manual change and use its remembered `TagSpan`? Does it detect the mismatch and fall back to treating it as a fresh invocation anyway? Every one of these answers is itself a new rule to design, document, and test, and every one of them is surprising in some plausible scenario.
- **What happens after any edit to the text** between the two commands (the remembered `TagSpan`'s offsets are now stale — the document has different content at those offsets)? A state-tracking design needs a staleness-invalidation rule (e.g. clear the remembered state on `textChanged`); a stateless design has no such problem by construction, since it always re-derives the answer fresh from the current cursor position and current text on every invocation.
- **Repeated Ctrl+Shift+A presses still need to "walk up" one level each time** — and the stateless design already delivers this for free: since `select_parent_block` always operates on the *current selection's start* (via the current cursor/selection, which after the first Ctrl+Shift+A press now spans the parent block), each subsequent press computes `enclosing_tag_span` at the (now-parent-block's-start) cursor position, which structurally *is* that parent block, and walks up one further level from there. No separate "repeat" code path or remembered chain is needed — pressing Ctrl+Shift+A repeatedly and pressing it once from a manually-adjusted selection behave identically and correctly, because both are just "compute enclosing block at current position, then its parent," applied fresh each time. This is the concrete payoff of choosing statelessness: the "walk up multiple levels by pressing the shortcut repeatedly" behavior the task implies should feel natural falls out automatically, with zero extra code, specifically *because* there is no separate state to keep synchronized.

One subtlety worth being explicit about: after `select_parent_block` sets the selection to the parent block, the *cursor's own position* (`QTextCursor.position()`, i.e. where the moving end of the selection landed) is at `parent.close_end` per the `setPosition`/`KeepAnchor` construction above — **not** at some point still "inside" the child block. A repeated Ctrl+Shift+A press therefore computes `enclosing_tag_span` at `parent.close_end`, which (per §4.2's boundary rule, `position < end` being false exactly at `close_end`) is **not itself inside `parent`** — it would incorrectly resolve to whatever comes *after* `parent`, not to `parent`'s own parent. **This is a real edge case the stateless design must handle correctly, and does:** `select_parent_block` does not compute `enclosing_tag_span` at "wherever the cursor's moving end landed" — it must use the **start** of the current selection (the anchor, or more precisely `min(cursor.selectionStart(), cursor.selectionEnd())`) as the position to query, not `cursor.position()` blindly. Corrected:

```python
def select_parent_block(self) -> None:
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
    new_cursor = self.textCursor()
    new_cursor.setPosition(parent.open_start)
    new_cursor.setPosition(parent.close_end, QTextCursor.MoveMode.KeepAnchor)
    self.setTextCursor(new_cursor)
```

Using `selectionStart()` (which for a selection built with `setPosition(open_start)` then `setPosition(close_end, KeepAnchor)` is exactly `open_start`, regardless of anchor/cursor ordering conventions) guarantees repeated presses always query a position that is genuinely inside the previously-selected block — specifically at its very first character, which by the containment rule (`open_start <= position < end`) is always included. This is the one piece of genuine subtlety in an otherwise simple design, and is called out explicitly here rather than left as a latent bug for an implementer to discover.

## 6. Matching-tag highlighting

### 6.1 What "cursor is on a tag" means, precisely

**Decision:** the cursor is considered "on" a tag when its position falls anywhere within that tag's own character span — for an opening tag, `[TagSpan.open_start, TagSpan.open_end)`; for a closing tag, the equivalent span for the `</name>` token itself (which `TagSpan` does not store as its own separate offsets — see §6.2 for how this is derived). This is deliberately **not** limited to "only when the cursor is exactly between `<` and `>`" in some narrower sense (e.g. only inside the element name) — the whole tag token, delimiters included, counts, matching how most structural/bracket-matching editors define "on a bracket-like token" (the entire token highlights/matches, not just its innermost character).

### 6.2 Deriving the closing tag's own span

`TagSpan` (sub-project A) stores `close_end` (just past the matching close tag's `>`) but not the close tag's own `start` offset (where its `<` begins) — sub-project A had no need for that offset, since folding only needs "where does the foldable region's last visible line begin" (the *line* containing `close_end`, not the exact `<` offset within it). This document does need the exact start offset, to know precisely when the cursor is "on" the closing tag versus merely past it.

**Decision:** rather than adding a new field to `TagSpan` (which would touch sub-project A's already-specified data shape, explicitly out of scope per §2.2), this document derives the closing tag's start offset **on demand**, locally within `xml_editor.py`, via a small helper that is not part of `xml_structure.py`:

```python
def _closing_tag_start(text: str, span: TagSpan) -> int | None:
    """Given a TagSpan with a known close_end, find where its own '</name>'
    token begins. Returns None if span has no close_end or is self-closing."""
    if span.close_end is None or span.self_closing:
        return None
    # The closing tag's own text is "</" + span.name + (whitespace)* + ">",
    # immediately preceding close_end. rfind is sufficient and exact here
    # because the search window is bounded to just before close_end, and
    # the corresponding open tag's own '<' (span.open_start) is always a
    # strictly earlier, distinct occurrence for any non-degenerate element.
    close_tag_prefix = "</" + span.name
    start = text.rfind(close_tag_prefix, span.open_end, span.close_end)
    return start if start != -1 else None
```

**Why this stays a private helper in `xml_editor.py` and is not promoted into `xml_structure.py`:** it is a narrow, single-purpose derivation used only by the highlighting feature this document adds, not a general-purpose scanning primitive in the spirit of `scan()`/`find_enclosing_open_tag`/`nesting_depth_at`. Adding it to `xml_structure.py` would grow that module's public surface for a need specific to one feature; keeping it local to `xml_editor.py` (where the highlighting logic itself lives) keeps `xml_structure.py`'s public API exactly as sub-project A defined it, satisfying this document's own explicit "no change to sub-project A's already-specified behavior" scope boundary at the data-shape level too, not just the behavioral level.

### 6.3 The highlighting mechanics

```python
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
        close_start is not None and close_start <= position < span.close_end
    )
    if not (on_open_tag or on_close_tag):
        self._refresh_extra_selections()
        return

    open_selection = QTextEdit.ExtraSelection()
    open_selection.format.setBackground(self._matching_tag_color)
    open_selection.cursor = _make_span_cursor(self, span.open_start, span.open_end)

    selections = [open_selection]
    if close_start is not None:
        close_selection = QTextEdit.ExtraSelection()
        close_selection.format.setBackground(self._matching_tag_color)
        close_selection.cursor = _make_span_cursor(self, close_start, span.close_end)
        selections.append(close_selection)

    self._matching_tag_selections = selections
    self._refresh_extra_selections()
```

Connected to `cursorPositionChanged`, the same signal sub-project A's `_highlight_current_line` is already connected to.

**Precision note on `enclosing_tag_span` here:** using `enclosing_tag_span` (this document's own new function, §3.2) rather than sub-project A's `find_enclosing_open_tag` is deliberate and necessary — `find_enclosing_open_tag` returns only a name and is defined in terms of "what element's *content* is the cursor inside," which by construction excludes positions actually inside the tag delimiters themselves (a cursor between `<` and `>` of an opening tag is not "inside the element's content," it's inside the tag token that starts that content). `enclosing_tag_span`'s own containment rule (`open_start <= position < end`) does include the opening tag's own span as part of what it returns for `open_start <= position < open_end`, which is exactly what's needed here. No change to `find_enclosing_open_tag` is made or needed; this document simply uses the more general primitive it already introduced for a purpose it's well-suited to.

### 6.4 Coexistence with current-line highlighting: a combined-selection-list design

Sub-project A's §3.7 states plainly that `_highlight_current_line`'s `self.setExtraSelections([selection])` call is, in that document's own scope, "the single owner of `XmlEditor`'s extra-selections" — true *at the time sub-project A was written*, because nothing else in that document's scope also wanted a persistent extra-selection at the same time (the Tier-1 fallback's error-line highlight is a distinct one-shot case, already reconciled with current-line highlighting in sub-project A §4.5). This document is the second persistent, always-on consumer of `setExtraSelections`, and `setExtraSelections` **replaces the whole list** on every call — so the two features cannot each independently call `self.setExtraSelections([their own selection])` without one clobbering the other on every cursor move (whichever handler's `cursorPositionChanged` slot runs second on a given move would always win, silently discarding the other feature's highlight).

**Decision:** introduce one small piece of shared infrastructure on `XmlEditor` — a combining method that both features' handlers call *instead of* calling `setExtraSelections` directly:

```python
def _refresh_extra_selections(self) -> None:
    """The single place XmlEditor calls QPlainTextEdit.setExtraSelections.
    Combines every named selection source this widget maintains into one
    list, in a fixed layering order, and pushes that combined list to Qt
    in one call. Individual features never call setExtraSelections
    directly; they update their own named attribute and call this."""
    selections: list[QTextEdit.ExtraSelection] = []
    selections.extend(self._current_line_selections)   # sub-project A, §3.7 -- background layer
    selections.extend(self._matching_tag_selections)    # this document, §6.3 -- foreground layer
    if self._error_line_selection is not None:          # sub-project A, §4.5 -- one-shot, on top
        selections.append(self._error_line_selection)
    self.setExtraSelections(selections)
```

Sub-project A's `_highlight_current_line` (§3.7) is adapted, as part of this document's work, to set `self._current_line_selections = [selection]` and call `self._refresh_extra_selections()` instead of calling `self.setExtraSelections([selection])` directly; its own externally-visible behavior (a full-width background highlight following the cursor, replaced on every `cursorPositionChanged`) is completely unchanged — only *which method actually calls into Qt* changes, and only so a second feature can add to the same list without clobbering it. This is the smallest possible change that makes the two features coexist correctly, and it is explicitly **not** a redesign of sub-project A's highlighting behavior — the observable result (what the user sees) for current-line highlighting alone, with no cursor on a tag, is byte-for-byte identical to sub-project A's own spec.

**Why a combining method rather than, say, each feature tracking "is my highlight still wanted" and re-deriving the union differently:** `QTextEdit.ExtraSelection` objects are cheap, plain data (a cursor + a format) with no identity/ownership semantics Qt cares about beyond "this is what's currently in the list" — there is nothing to reconcile or diff between calls. The simplest correct design is exactly "every feature maintains its own small list of zero-or-more current selections; one shared method concatenates them in a fixed order and pushes the result," which is what's specified above. **Layering order** (current-line first/bottom, matching-tag second, one-shot error-line last/top) matters only in the pathological case where two selections would visually overlap at the exact same character range with different colors — Qt paints extra-selections in list order, later entries visually on top where ranges intersect. Current-line highlighting is a full-line background band; matching-tag highlighting is a much narrower span typically inside that band — placing matching-tag selections after current-line in the list means the tag highlight's color is what's visible at the overlap, which is the more useful outcome (the more specific, purposefully-triggered highlight should be the one that's visually legible, not painted over by the more general per-line one). The error-line one-shot indicator (sub-project A §4.5) stays last/topmost, unchanged from that document's own reasoning.

**Distinct colors required:** the matching-tag highlight's color (`self._matching_tag_color`) must be visually distinct from both the current-line color and the error-line color, for the same reason sub-project A gives for its own error-line color choice (§4.5: "a color distinct from the current-line-highlight color... so a user can tell 'this line has a parse error' apart from 'this is just where my cursor happens to be'"). Exact color values are a presentation detail left to implementation, matching how sub-project A itself treats its own highlight colors (§3.3: "exact colors are a presentation detail left to implementation... the requirement is that the categories are visually distinct").

## 7. The folded-copy/paste correctness guarantee

This is, per §1.2, the single most important design decision in this document — an implementation bug here silently breaks the only remaining path to two originally-planned workflows (Detail move/copy, client-page cloning by hand).

### 7.1 How the selection is constructed, precisely

Both `select_enclosing_block` (§4) and `select_parent_block` (§5.2) construct their `QTextCursor` selection **exclusively from character offsets** — `TagSpan.open_start` and `TagSpan.close_end`, both of which are plain integer offsets into `self.toPlainText()` (equivalently, `self.document().toPlainText()` or the underlying `QTextDocument`'s character stream) — via:

```python
cursor = self.textCursor()
cursor.setPosition(span.open_start)
cursor.setPosition(span.close_end, QTextCursor.MoveMode.KeepAnchor)
self.setTextCursor(cursor)
```

**This is the entire design, and it is deliberately the only mechanism used.** There is no mouse-drag, no visual-rectangle hit-testing, no iteration over `QTextBlock`s to "figure out what's visually selected." `QTextCursor.setPosition(int)` addresses a position in the document's underlying **character stream**, which is entirely independent of which `QTextBlock`s are currently marked `setVisible(False)` by folding (§3.5 of sub-project A) — visibility is a **presentation-layer** property Qt's text-layout engine consults when deciding what to *paint*, not a property that removes characters from the document's actual content or from what a `QTextCursor` addresses. A `QTextCursor` spanning `[open_start, close_end)` selects every character in that range **regardless of whether some of the `QTextBlock`s in that range are currently hidden from view** — folding never deletes or truncates document content, it only suppresses its on-screen rendering, and `QTextCursor`/`selectedText()` operate on content, not on rendering.

### 7.2 Why this guarantees correctness (not just "probably works")

The reasoning chain, stated explicitly rather than assumed:

1. `TagSpan.open_start`/`close_end` are offsets computed by `xml_structure.scan()` against `self.toPlainText()` — the document's full, real text content, independent of any Qt rendering/visibility state (sub-project A's `xml_structure.py` has no Qt dependency at all, per that document's own §3.1 design rationale — it cannot know or care about fold state, because it operates on a plain Python string).
2. `QTextCursor.setPosition(offset)` addresses that same character stream by the same offset numbering — Qt's `QTextDocument` character positions are stable, contiguous, and defined over the *actual* text content; a hidden `QTextBlock` still occupies its normal range of character positions in that numbering, it simply isn't laid out/painted. (This is the same fact sub-project A's own folding design already relies on and states directly, §3.5: "`.setVisible(False)` on every contained `QTextBlock`... the standard Qt technique.. does not implicitly re-expand" — visibility is toggled per-block as a display property, never as a content-removal operation.)
3. Therefore a `QTextCursor` built via `setPosition(open_start)` → `setPosition(close_end, KeepAnchor)` selects the **full underlying text** of the block, including the text of every currently-hidden `QTextBlock` within it — `cursor.selectedText()` (and, downstream, whatever Qt's standard Copy/Cut actions place on the clipboard, since both operate on `textCursor().selectedText()`/the equivalent internal selection, not on "what's currently painted") is therefore guaranteed to include the folded-away content, not a truncated/placeholder version of it.
4. A **naive alternative implementation** that this design explicitly avoids — e.g. "get the currently visible bounding rectangle of the block and do a mouse-drag-equivalent visual selection over it," or "iterate visible `QTextBlock`s only and concatenate their text" — would indeed produce exactly the wrong, truncated result the user's requirement warns against, since a visual/visible-blocks-only approach by definition skips whatever is hidden. This document does not use any such approach anywhere; §7.1's offset-only construction is the *only* selection-construction path either command uses, so there is no code path in this design that could accidentally take the naive route.

### 7.3 The paste side: standard `QPlainTextEdit` behavior, confirmed sufficient, nothing special needed

**Decision, stated explicitly per the task's own instruction not to silently assume this:** pasting arbitrary XML text back into the document requires **no special handling beyond Qt's own default `QPlainTextEdit` paste behavior** (`Ctrl+V`, or the standard Edit-menu Paste action, both of which ultimately call the same internal path as `insertPlainText` on the current selection/cursor position). This document adds **no override** of `keyPressEvent` for paste, no custom clipboard-format handling, and no post-paste re-fold/re-scan step beyond what already happens automatically:

- Sub-project A's folding (§3.5) already re-runs `xml_structure.scan()` on every `textChanged` signal, and a paste operation fires `textChanged` exactly like any other edit — so any fold-eligibility implications of the newly-pasted content (e.g. the pasted text itself contains a foldable multi-line element) are picked up automatically by machinery that already exists, with no new code needed here.
- Sub-project A's syntax highlighter re-highlights automatically via Qt's own `QSyntaxHighlighter` re-invocation on changed blocks — again already-existing machinery, not something this document needs to touch.
- There is no requirement anywhere in this task (or in the original design, or in the persistent-memory note) for paste to do anything structurally aware — e.g. "only allow pasting a complete well-formed element," or "auto-indent the pasted content to match its new location." The user's own stated requirement is specifically and only about the **copy/cut side** not truncating folded content; nothing asks for smart/structural paste behavior, and this document does not invent any. A pasted block of XML lands exactly where the cursor/selection was, exactly as typed text would, which is the same behavior every other text editor gives for a raw-text paste.

**Why this is safe to state as "confirmed sufficient" rather than an open question:** the correctness requirement is entirely on the *copy/cut* side — ensuring the clipboard actually contains the full text (§7.2). Once that's true, pasting that text back is bit-for-bit the same problem as pasting any other text into a `QPlainTextEdit`, a solved problem Qt already handles correctly with no customization, and re-solving it here would be scope creep against a requirement that was never about paste mechanics.

### 7.4 The proof-by-test

```python
def test_copy_folded_block_yields_full_text(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(
        "<Page fileName=\"a\">\n"
        "  <Detail tableName=\"b\">\n"
        "    <Page fileName=\"c\">\n"
        "      <ColumnPresentation fieldName=\"x\" caption=\"X\"/>\n"
        "      <ColumnPresentation fieldName=\"y\" caption=\"Y\"/>\n"
        "    </Page>\n"
        "  </Detail>\n"
        "</Page>\n"
    )
    full_text = editor.toPlainText()

    # Position the cursor inside the inner <Page>, fold it.
    inner_page_open = full_text.index('<Page fileName="c"')
    cursor = editor.textCursor()
    cursor.setPosition(inner_page_open)
    editor.setTextCursor(cursor)
    editor.select_enclosing_block()  # selects the inner <Page>...</Page> block

    expected_block_text = full_text[
        full_text.index('<Page fileName="c"') : full_text.index("</Page>", full_text.index('<Page fileName="c"')) + len("</Page>")
    ]

    block = editor.document().findBlock(inner_page_open)
    editor._toggle_fold(block)  # collapse the inner <Page> region (sub-project A mechanism)

    # Re-select after folding -- re-run the same command, now against a
    # document with hidden QTextBlocks in the middle of the target range.
    cursor = editor.textCursor()
    cursor.setPosition(inner_page_open)
    editor.setTextCursor(cursor)
    editor.select_enclosing_block()

    selected = editor.textCursor().selectedText()
    # QTextCursor.selectedText() represents block/paragraph separators as
    # U+2029 rather than "\n" -- normalize before comparing to the plain-text
    # expectation sliced out of toPlainText() above.
    selected_normalized = selected.replace(" ", "\n")

    assert selected_normalized == expected_block_text, (
        "Selecting a folded block must yield its full underlying text, "
        "not a truncated/placeholder version of the visually-collapsed content."
    )

    # Copy, and confirm the clipboard itself -- not just the in-editor
    # selection -- also carries the full text (the actual end-to-end path
    # a user relies on for copy -> paste elsewhere).
    editor.copy()
    clipboard_text = QApplication.clipboard().text().replace(" ", "\n")
    assert clipboard_text == expected_block_text
```

This test is designed specifically to be the kind of test that **would fail** under the naive "copy what's visible" implementation this design explicitly avoids (§7.2 point 4) — folding the inner `Page` hides its two `ColumnPresentation` lines, so a visible-blocks-only implementation would produce a selection/clipboard content missing those two lines entirely, which this assertion would catch immediately (`selected_normalized == expected_block_text` would fail, and the failure would visibly show the missing `ColumnPresentation` lines in a test-runner diff). Additionally testing `QApplication.clipboard().text()` directly (not just `editor.textCursor().selectedText()`) closes the last gap in the chain — confirming Qt's actual `editor.copy()` (the same code path `Ctrl+C` triggers) puts the correct, complete text on the real system clipboard, which is the artifact a subsequent `Ctrl+V` paste elsewhere actually reads from.

A second variant of this same test additionally folds the **outer** `Detail` region (nesting two independent folds, one inside the other) before selecting and copying the *outer* `Page` block via `select_enclosing_block`, confirming the guarantee holds for nested folds too, not just a single fold — exercising the same reasoning chain (§7.2) at a different nesting depth, with two independently-collapsed regions inside the copied range simultaneously.

## 8. Keyboard shortcut wiring

**Decision: `QShortcut`, not `keyPressEvent` interception.** Sub-project A's own key-handling (auto-indent on Enter, §3.8; auto-close on `<`/quote/`>`, §3.9) is implemented via `keyPressEvent` interception specifically because those behaviors need to **conditionally fall through** to Qt's own default character-insertion handling (`super().keyPressEvent(event)`) depending on context — e.g. typing `>` sometimes means "insert a literal `>`" and sometimes means "move past the already-auto-inserted `>`," a decision that has to be made inline, per-keystroke, as part of the normal text-insertion path. `Ctrl+Shift+B`/`Ctrl+Shift+A`, by contrast, are **not** character-insertion events at all — they never have a "sometimes fall through to normal typing" ambiguity (`Ctrl+Shift+B`/`A` are not printable-character input in any context), so there is no reason to route them through the same `keyPressEvent` override that exists specifically to arbitrate character-insertion edge cases. `QShortcut` is the standard, simpler Qt mechanism for exactly this kind of "global-to-this-widget, non-character command key combination," and using it keeps `keyPressEvent` focused only on the character-insertion-arbitration logic sub-project A already put there, rather than growing that method with unrelated `if event.key() == ... and event.modifiers() == ...` branches for commands that have nothing to do with text insertion.

```python
def __init__(self, parent=None):
    super().__init__(parent)
    ...  # sub-project A's existing __init__ body
    self._matching_tag_selections: list[QTextEdit.ExtraSelection] = []
    self._current_line_selections: list[QTextEdit.ExtraSelection] = []

    select_block_shortcut = QShortcut(QKeySequence("Ctrl+Shift+B"), self)
    select_block_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
    select_block_shortcut.activated.connect(self.select_enclosing_block)

    select_parent_shortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
    select_parent_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
    select_parent_shortcut.activated.connect(self.select_parent_block)

    self.cursorPositionChanged.connect(self._update_matching_tag_highlight)
```

**`Qt.ShortcutContext.WidgetShortcut`** is used (not `WindowShortcut` or the application-wide default) so both shortcuts fire only when `XmlEditor` itself has focus, consistent with these being editor-local text-selection commands, not global application menu commands — there is no corresponding `QAction`/menu-bar entry for either command (matching how sub-project A's own Enter/auto-close key handling has no menu equivalent either; these are keyboard-only editing conventions, the same category of feature). This also avoids any conflict with `Ctrl+Shift+B`/`Ctrl+Shift+A` potentially being used for something else in a different, currently-focused widget elsewhere in the app shell — `WidgetShortcut` scoping means the binding is inert whenever focus is anywhere other than this specific editor instance.

`_update_matching_tag_highlight` is connected to `cursorPositionChanged` alongside sub-project A's own `_highlight_current_line` connection to that same signal — both slots fire on every cursor move, each updating its own named selection list and calling the shared `_refresh_extra_selections` (§6.4); Qt does not guarantee slot invocation order across independently-made `connect` calls to the same signal in a way this design needs to rely on, and indeed the design in §6.4 does not depend on ordering between these two slots at all (each only ever appends to its own list and then calls the shared refresher — the last one to run simply causes one extra, harmless `setExtraSelections` call with the same eventual combined content either slot would have produced alone).

## 9. Testing strategy

### 9.1 Unit tests for `xml_structure` additions (no Qt dependency)

- **`enclosing_tag_span`:** given a small nested fragment, assert the correct `TagSpan` (checked by its `name`/`open_start`/`depth`, not just its name, to actually confirm the right *instance* among possibly-repeated element names) is returned at a position inside an element's tag delimiters, at a position inside its text content, at a position inside a nested child, and at a position in inter-sibling whitespace (asserting the *parent* span is returned, per §4.2) — plus `None` for a position outside every element entirely (leading/trailing document whitespace).
- **`enclosing_tag_span`, self-closing case:** a fragment containing a `<Tag/>` — assert a position inside its span returns that `TagSpan` with `self_closing=True`, and that the span's own `open_start`/`close_end` correctly bound exactly that self-closing token.
- **`enclosing_tag_span`, tolerant/malformed cases:** re-using the same tolerance fixtures sub-project A's own test suite already established (unclosed tag, mismatched tag, truncated document) — assert `enclosing_tag_span` returns a sensible best-effort span (matching whatever `scan()` itself already produces for that fixture) and never raises.
- **`parent_tag_span`:** given a `scan()` result for a multi-level nested fragment, assert the correct parent `TagSpan` is returned for a leaf span, for a mid-level span, and `None` for a depth-0 (top-level) span. A case with two same-named siblings at the same depth under the same parent, confirming the correct single parent is found for either sibling (not a mismatch caused by name-based lookup — reinforcing why §3.2/§3.3 deliberately do not rely on element names for containment).

### 9.2 `pytest-qt` tests for `XmlEditor`

- **`Ctrl+Shift+B` selection boundaries:** simulate the shortcut at a cursor position inside a multi-line element; assert `textCursor().selectedText()` (normalized for ` `, per §7.4's note) exactly equals the source text's `<Tag ...>...</Tag>` substring, including the opening `<` and closing `>`.
- **`Ctrl+Shift+B` on a self-closing tag:** assert the selection is exactly the `<Tag .../>` substring, with no separate close-tag search performed (implicitly confirmed by the selection's exact bounds matching `open_start:open_end` for that span).
- **`Ctrl+Shift+B` in inter-sibling whitespace:** position the cursor between two sibling closing/opening tags at the same depth; assert the selection ends up covering the **parent** element's full span, per §4.2.
- **`Ctrl+Shift+B` outside any element:** position the cursor in leading document whitespace before the first top-level tag (if the fixture has any); assert no selection change occurs (no-op, §4.3).
- **`Ctrl+Shift+A` from a fresh cursor position (no prior Ctrl+Shift+B):** position the cursor inside a deeply nested element with no existing selection; invoke `select_parent_block` directly; assert the resulting selection matches "the block one level up from what Ctrl+Shift+B would have selected at that same position" — confirmed by independently computing that expected span via `enclosing_tag_span`/`parent_tag_span` in the test itself and comparing offsets, not just visually re-deriving the same expectation inline.
- **`Ctrl+Shift+A` repeated presses walk up multiple levels:** starting from a leaf-level cursor position in a fragment at least three levels deep, press Ctrl+Shift+A three times in a row (via `qtbot`, dispatching the shortcut's key sequence or calling `select_parent_block()` directly three times in sequence to exercise exactly the "selection becomes the new query position" mechanism from §5.2's corrected implementation); assert each successive selection is exactly one level shallower than the last, and that the third press's target has one fewer level of nesting than the second's, confirming the `selectionStart()`-based re-query (not `cursor.position()`) correctly avoids the boundary bug identified in §5.2.
- **`Ctrl+Shift+A` at a top-level element:** position the cursor inside a top-level (depth-0) element; invoke `select_parent_block`; assert the selection is unchanged (no-op, §5.1) — explicitly also assert it does **not** become "select all"/the whole document, since that was the explicitly-rejected alternative.
- **Matching-tag highlighting, on the opening tag:** position the cursor inside an opening tag's delimiters; assert the combined extra-selections list (`editor.extraSelections()`) contains exactly two matching-tag-colored selections (open + close) in addition to whatever the current-line selection contributes — checked by format/background-color identity, not just list length, to distinguish the matching-tag entries from the current-line entry.
- **Matching-tag highlighting, on the closing tag:** same, cursor inside the closing tag's delimiters instead — assert the same pair of selections results (order-independent check, since both the open-tag and close-tag spans are highlighted together regardless of which one the cursor is literally on).
- **Matching-tag highlighting, cursor elsewhere:** cursor in ordinary text content, not on any tag; assert zero matching-tag-colored selections are present, and that the current-line selection is still present and unaffected — confirming §6.4's combining design doesn't leave stale matching-tag selections behind once the cursor moves off a tag.
- **Matching-tag highlighting coexists with current-line highlighting:** for any cursor position on a tag, assert `len(editor.extraSelections()) == 2` (current-line + open/close-as-one-combined-region, or 3 if open and close are represented as two separate `ExtraSelection` entries per §6.3's sketch) — the exact count is an implementation detail, but the test asserts both categories are simultaneously present by inspecting each selection's format background color against the two known distinct colors, directly verifying §6.4's central claim that neither feature clobbers the other.
- **The folded-copy/paste test from §7.4**, in full, including its nested-fold variant.

### 9.3 What is explicitly not tested, and why

- **Paste mechanics themselves** (§7.3) are not given a dedicated new test beyond confirming the clipboard content is correct after copy (§7.4) — since this document adds no paste-specific code at all, there is nothing paste-specific to unit-test; Qt's own `QPlainTextEdit` paste behavior is exercised by Qt's own test suite, not this project's.
- **Visual color values** for matching-tag highlighting are not asserted to be any specific RGB value, only that they are distinct from the other two highlight colors already in use — matching sub-project A's own stated position on its highlight colors being a presentation detail (§3.3, §4.5).

## 10. Non-goals and boundary confirmation

To close any risk of scope ambiguity: this document adds exactly four pieces of new behavior to `XmlEditor` — `select_enclosing_block`, `select_parent_block`, matching-tag highlighting, and the shared `_refresh_extra_selections` combining infrastructure those first three (plus the pre-existing current-line highlighting) all funnel through — plus two new pure functions in `xml_structure.py`. It does not touch, wrap, or reimplement folding, syntax highlighting, the gutter, auto-indent, or auto-close. It does not add any new menu entries, dialogs, or `ProjectModel`-level behavior. It does not resurrect any part of the original design's obsolete §6.2/§6.5 scope (§1.2, §2.2) — those remain fully retired, not silently relocated here under a new name.

## 11. Summary of decisions

1. **Two new `xml_structure.py` functions, `enclosing_tag_span(text, position)` and `parent_tag_span(spans, span)`, both implemented as a single linear pass over `scan()`'s existing output** — no change to `scan()` itself, no new stack/indexed structure. Simplicity is chosen deliberately over premature optimization given this tool's realistic document sizes (hundreds to low-thousands of `TagSpan`s, and these commands run once per explicit keypress, not per keystroke).
2. **`Ctrl+Shift+B` selects `text[open_start:close_end]` uniformly**, including for self-closing tags (where `close_end == open_end` already, by `TagSpan`'s own field semantics from sub-project A — no conditional branch needed). A cursor exactly at a block's trailing boundary (`position == close_end`) is *not* included in that block, matching Qt's own between-characters cursor-position convention. A cursor in inter-sibling whitespace correctly resolves to selecting the **parent** block (the structurally correct answer `enclosing_tag_span`'s containment rule already produces, not a fallback heuristic), and the command is a genuine no-op only when the cursor is outside every element in the document entirely.
3. **`Ctrl+Shift+A` is a no-op (not "select the whole document") when there is no parent**, and is designed to be **stateless** — always re-derived from the current cursor/selection position, never from remembered state about a prior Ctrl+Shift+B. This avoids a whole class of staleness/manual-selection-change edge cases a state-tracking design would otherwise have to define, and gives "repeated presses walk up multiple levels" for free. One genuine subtlety was found and resolved: the re-query for repeated presses must use the current selection's **start** offset, not the cursor's raw (possibly-past-the-end) position, to avoid landing exactly on a boundary that would incorrectly skip a level.
4. **Matching-tag highlighting** triggers when the cursor is anywhere within an opening or closing tag's own character span (delimiters included), using `enclosing_tag_span` (not `find_enclosing_open_tag`, which by definition excludes tag-delimiter positions) plus a small local (`xml_editor.py`-only, not promoted into `xml_structure.py`) helper to derive the closing tag's own start offset, since `TagSpan` doesn't store it and doesn't need to for sub-project A's own purposes.
5. **Extra-selections coexistence is solved with a shared `_refresh_extra_selections` combining method**, which every persistent highlight source (current-line, from sub-project A; matching-tag, from this document) updates its own named list and calls, rather than any feature calling `setExtraSelections` directly. This is a small, additive adaptation of sub-project A's `_highlight_current_line` (same observable behavior, different internal call target) — not a redesign of it. Layering order places the more specific matching-tag highlight visually on top of the more general current-line band where they overlap.
6. **The folded-copy/paste correctness guarantee is satisfied by construction**: both selection commands build their `QTextCursor` exclusively from `TagSpan` character offsets (`setPosition(open_start)` → `setPosition(close_end, KeepAnchor)`), never from any visual/visible-blocks-only mechanism — and `QTextCursor`/`selectedText()`/clipboard copy all operate on the document's actual character stream, which folding's `QTextBlock.setVisible(False)` never truncates or removes, only hides from rendering. §7.4 specifies an explicit test (including a nested-fold variant) that folds a block, re-selects it via `Ctrl+Shift+B`, copies it, and asserts both the in-editor selection and the **actual system clipboard content** equal the full original text — proving this is not an assumption but a verified guarantee, and one designed specifically to fail loudly under the naive "copy what's visible" implementation it exists to rule out.
7. **Paste needs no new code at all.** Standard `QPlainTextEdit`/Qt paste behavior is confirmed sufficient and used unmodified — folding re-scan and syntax re-highlighting both already happen automatically via existing `textChanged`-driven machinery from sub-project A, and nothing in this task's requirements asks for structurally-aware paste behavior. This is stated explicitly (not silently assumed) per the task's own instruction.
8. **`QShortcut` with `Qt.ShortcutContext.WidgetShortcut`, not `keyPressEvent` interception**, for both new commands — chosen because, unlike sub-project A's Enter/auto-close handling, neither command has a "sometimes fall through to ordinary character insertion" ambiguity that would justify routing through the same `keyPressEvent` override; `QShortcut` is the simpler, standard mechanism for a non-character command binding, and keeps `keyPressEvent` scoped to what sub-project A already put there. No menu entries are added for either shortcut, matching the keyboard-only nature of sub-project A's own Enter/auto-close conventions.
9. **This sub-project's existence is load-bearing, not cosmetic**: per persistent project memory, the user decided this capability (structural select + the OS's own clipboard) supersedes and retires the original design's §6.2 ("Move / Copy") and §6.5 ("Client (read-only) page generation") as separate features entirely. Nothing in those two original sections' scope (FK-mapping audit flags, ability-code rewriting, fileName-uniqueness paste prompts, cross-file clipboard-sharing UI) is resurrected here — this document's job stops at "select correctly, and never truncate a folded selection's copied content."
