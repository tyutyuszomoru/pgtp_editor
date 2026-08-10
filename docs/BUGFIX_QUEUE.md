# Bug Fix Queue

Working queue of triaged bug reports for PGTP Editor, filled by the `bug-triager` agent
(`.claude/agents/bug-triager.md`) so bug analysis can happen in the background while other
implementation work is in progress in the main session. Each entry is a root-caused, ready-to-implement
proposal — `bug-triager` never edits source itself. Entries are appended at the end as reports come in.

When resolving: implement the fix, run the feature-tester / manual-maintainer / spec-maintainer policy
from CLAUDE.md as usual, then flip the entry's `Status` line to `RESOLVED (<commit>)` in place — do not
delete entries; they're the record of what was reported and why the fix was shaped the way it was.

---

## BUG-001: Edit XSD tab has no close affordance once revealed

**Status:** RESOLVED (b605314)
**Reported:** 2026-08-01
**Report (verbatim):** "there's no way to close a tab in editor pane. Opened XSD and now can't close it :-)"

**Root cause:** `pgtp_editor/ui/center_stage.py`, `CenterStage.__init__` (lines 75–83). `setTabsClosable(True)`
is set on the whole `QTabWidget`, but the loop right after it strips the ✕ button
(`bar.setTabButton(index, QTabBar.ButtonPosition.RightSide/LeftSide, None)`) from every tab **except**
`self.manual_tab_index` — comment: "Only the Manual tab is closable ... The other tabs are structural, so
strip their close buttons." `self.xsd_tab_index` (the "Edit XSD" / "Edit AutoXSD" tab, added at line 61,
revealed by `show_edit_xsd()` at line 92–94) is treated as one of those "structural" tabs and gets no ✕.

`_on_tab_close_requested` (lines 85–87) only special-cases `index == self.manual_tab_index` and calls
`hide_manual()`; there is no `hide_edit_xsd()`/equivalent method on `CenterStage` at all, and no
`_on_tab_close_requested` branch for `self.xsd_tab_index`.

Confirming this is a known, not-yet-closed gap: `pgtp_editor/ui/main_window.py`, `MainWindow.closeEvent`
(around line 817–821) has the comment "Edit XSD tab (spec §11): unsaved XSD edits get their own
save/discard/cancel prompt, distinct from the project's (File > Close handles that one) **since the XSD
tab has no Close command**." So once `Schema ▸ Edit XSD` or `Schema ▸ Edit AutoXSD` reveals the tab
(`_open_edit_xsd`/`_open_edit_auto_xsd` → `_open_xsd(mode)` → `stage.show_edit_xsd()`, lines 533–582), the
only way back to another tab is manually clicking a different visible tab (e.g. Raw XML) — the tab itself
never re-hides, unlike Manual which has a full show/hide toggle (`_show_manual` at line 2971, wired to F1).

**Proposed fix:**
1. In `pgtp_editor/ui/center_stage.py`:
   - Give the Edit XSD tab a ✕ too: in the `__init__` loop (lines 79–82), stop excluding
     `self.xsd_tab_index` from the close-button strip (only strip tabs that should stay uncloseable —
     Diff/Merge, Caption Management, Raw XML remain structural/no-✕ since they are toggled by their own
     entry points, not by this tab-close mechanism).
   - Add a `hide_edit_xsd()` method mirroring `hide_manual()` (lines 101–106): hide `self.xsd_tab_index`
     via `setTabVisible(self.xsd_tab_index, False)`, and if it's the current tab, fall back to
     `self.raw_xml_tab_index` (same target `hide_manual` uses). No visibility-changed signal is needed
     here (nothing outside `center_stage` currently mirrors XSD-tab visibility the way `left_tabs`
     mirrors Manual's Contents tab), but keep the method name/shape consistent with `hide_manual` for
     future symmetry.
   - Extend `_on_tab_close_requested` (lines 85–87) with an `elif index == self.xsd_tab_index:` branch.
     This branch must **not** call `hide_edit_xsd()` directly — closing must go through
     `MainWindow`'s dirty-check first (see next point), so this should emit a new signal, e.g.
     `xsd_close_requested = Signal()` (declared alongside `manual_visibility_changed` near line 29), and
     `CenterStage._on_tab_close_requested` emits it instead of acting immediately for that index.
2. In `pgtp_editor/ui/main_window.py`:
   - Connect `self.center_stage.xsd_close_requested` to a new `_on_xsd_close_requested` handler (place it
     near `_confirm_close_xsd`, `_open_xsd`, and `_save_xsd` in the "Edit XSD tab (spec §11)" section
     starting at line 505).
   - `_on_xsd_close_requested` must reuse the **existing** `_confirm_close_xsd()` save/discard/cancel
     flow (lines 776–793) when `self._xsd_dirty` is true — the same pattern already used in `_open_xsd`
     (lines 548–560) and `closeEvent` (lines 821–831): if `cancel`, do nothing (leave tab open/dirty); if
     `save`, call `self._save_xsd()` and bail without closing if the save left `self._xsd_dirty` true
     (disk error); if `discard` (or not dirty at all), call `self.center_stage.hide_edit_xsd()`.
   - Do **not** invent a new confirmation dialog — `_confirm_close_xsd` is explicitly documented as split
     out "so tests can monkeypatch it instead of ever driving a real modal"; reuse it verbatim.
   - No change needed to `_open_xsd`/`_save_xsd`/`closeEvent` themselves; they already read `_xsd_dirty`
     and `_xsd_mode` correctly and will keep working once the tab can be hidden and re-shown.

**Test impact:** `tests/ui/test_edit_xsd_tab.py` already covers the dirty-prompt pattern for this tab
(`test_close_event_xsd_dirty_discard_closes`, `test_close_event_xsd_dirty_cancel_ignores`,
`test_close_event_xsd_dirty_save_writes_and_closes`, lines 115–148) — extend this file rather than adding
a new one. New cases needed: (a) clicking ✕ on the Edit XSD tab with no unsaved changes hides it and
switches to Raw XML directly (no prompt); (b) clicking ✕ while dirty and choosing discard hides the tab
without saving; (c) choosing save writes the file and hides the tab; (d) choosing cancel leaves the tab
open, visible, and still marked dirty (title still has the " *" suffix set by `_set_xsd_dirty`); (e) a
save failure during the close-time save keeps the tab open. Also worth a `tests/ui/test_center_stage.py`
(or wherever `CenterStage` itself is unit-tested, if such a file exists — check first) case that
`xsd_tab_index` now has a visible tab-bar close button while Diff/Merge, Caption Management, and Raw XML
still do not.

**Spec impact:** `docs/superpowers/CONSOLIDATED_SPEC.md` §11 ("Schema: curated XSD, learning & completion")
describes the Edit XSD/Edit AutoXSD tab's save/verify/import/export behavior in detail but does not
mention any close affordance one way or the other — the current no-close behavior was not a documented
intentional decision, just an omission. After the fix lands, flag `spec-maintainer` to add a short note to
§11 (or wherever tab lifecycle is described) that the Edit XSD tab is closable via the tab-bar ✕, routes
through the same `_confirm_close_xsd` prompt as mode-switching and app close, and returns to Raw XML.

---

## BUG-002: viewAbilityMode/editAbilityMode enum labels don't resolve in Properties panel

**Status:** RESOLVED (b605314)
**Reported:** 2026-08-01
**Report (verbatim):** "In the XSD I can find ViewAbilityMode and EditAbilityMode, but in the properties
window it doesn't show up. Others are picked up fine, but there's an exception here. in the xsd I can
clearly see on line 793:
    &lt;xs:attribute name="viewAbilityMode" use="optional"&gt;
      &lt;xs:simpleType&gt;
        &lt;xs:restriction base="xs:integer"&gt;
          &lt;xs:enumeration value="0" label="Disable"/&gt;
          &lt;xs:enumeration value="1" label="Separated page"/&gt;
          &lt;xs:enumeration value="2" label="Inline mode"/&gt;
          &lt;xs:enumeration value="3" label="Modal window"/&gt;
        &lt;/xs:restriction&gt;
      &lt;/xs:simpleType&gt;
    &lt;/xs:attribute&gt;"
Additional context relayed from a screenshot of the Properties panel for the same `<Page>` element: rows
for `NavigatorPosition`, `insertAbilityMode`, `deleteAbilityMode`, `deleteSelectedAbilityMode` all show
`"raw — label"` (e.g. `insertAbilityMode: "3 — Modal window"`), but `viewAbilityMode` and
`editAbilityMode` show only the bare raw number (`"3"`, no label suffix).

**Root cause:** Two distinct bugs bundled in one symptom, confirmed by tracing the full pipeline
(`pgtp_editor/ui/xml_editor.py::attribute_at_position` → `pgtp_editor/schema_learning/xsd_load.py::load_curated`
→ `pgtp_editor/schema_learning/settings_index.py::value_label` → `pgtp_editor/ui/properties_panel.py::_display_value`,
line 222) against both the repo's bundled `pgtp_editor/resources/curated.xsd` and the sample
`tests/sample/ERP_i01-r02_italian.pgtp`, plus reading `pgtp_editor/ui/main_window.py:451-486`:

1. **`editAbilityMode` is genuinely absent from `curated.xsd` entirely** — `grep -n editAbilityMode
   pgtp_editor/resources/curated.xsd` returns zero matches (only `viewAbilityMode`, `insertAbilityMode`,
   `deleteAbilityMode`, `copyAbilityMode`, `deleteSelectedAbilityMode` exist, at lines 270, 278, 334, 530,
   540, 548, 658, 794, 1498, 1506, 1579). Yet `editAbilityMode` is a real, frequently-emitted PHP
   Generator `<Page>`/`<OnTheFlyInsertPage>` attribute — it appears on essentially every `<Page>` element
   in `tests/sample/ERP_i01-r02_italian.pgtp` (e.g. line 97), right next to `viewAbilityMode`, with the
   same `0/1/2/3` = Disable/Separated page/Inline mode/Modal window enumeration `insertAbilityMode` and
   `viewAbilityMode` use. It's simply a coverage gap in curated.xsd (confirmed by loading the bundled file
   with `load_curated()` — `model.paths["Project/Presentation/Pages/Page"]["attributes"].get("editAbilityMode")`
   is `None` while the sibling `*AbilityMode` names all resolve). `settings_index.value_label()` (line
   134-139) correctly returns `None` for an unknown attribute, so the panel falls back to the bare value —
   working as designed, just with a missing curated entry. `pgtp_editor/generation/type_map.py:76`
   (`PAGE_DEFAULTS`) already lists `("editAbilityMode", "3")` as a known page default for the *generation*
   side, confirming the attribute is real and just never got added to `curated.xsd`'s dialect on the
   schema-learning side.
2. **`viewAbilityMode` resolves correctly against the bundled `curated.xsd` in every step I could
   reproduce** (`value_label(model, "Project/Presentation/Pages/Page", "viewAbilityMode", "3")` returns
   `"Modal window"`; `attribute_at_position()` on the real sample line correctly resolves to
   `("Project/Presentation/Pages/Page", "viewAbilityMode")`). But **`curated.xsd` is not a fixed asset —
   it is the user's own hand-owned, hand-edited file** in the app-data dir (`pgtp_editor/schema_learning/storage.py`,
   `curated_xsd_path()`; seeded once from the bundled resource by `main_window.py::_seed_curated_xsd_if_absent`
   around line 467-486, "never overwrites an existing file (curated.xsd is hand-owned, spec §11)"). The
   user's bug report itself is looking at *their own* copy, not necessarily the repo's bundled one. The
   mechanism that most plausibly explains a labeled block that looks completely correct in isolation
   (as quoted in the report) still failing to resolve is a **silent duplicate-attribute overwrite**:
   `xsd_load.py::_Collector.end()` (lines 133-137) does
   `self._current_type["attributes"][attr["name"]] = attr` unconditionally on every `</xs:attribute>` —
   if the user's `curated.xsd` has *two* `<xs:attribute name="viewAbilityMode">` blocks inside the same
   `xs:complexType` (e.g. from copy-pasting a similarly-shaped `*AbilityMode` block to add a new
   attribute and forgetting to finish editing it, or a stray unlabeled duplicate left over from editing),
   the later one silently wins — dropping the labels if the second copy is blank/unlabeled — with **no
   diagnostic at all**: `pgtp_editor/schema_learning/xsd_verify.py::_Checker` (the entire "Verify XSD"
   dialect check, confirmed against `CONSOLIDATED_SPEC.md` §11 lines 623-632, which enumerates every
   check Verify performs) checks duplicate **enumeration values** within one attribute and duplicate
   **complexType names**, but has **no check for a duplicate `xs:attribute name="…"` within the same
   complexType**. So a user could have exactly this malformed file, run Verify, see "no issues found,"
   and still get silently-dropped labels for that one attribute — which matches the report's description
   of only 2 of ~6 sibling `*AbilityMode` attributes failing, both by name, with no error surfaced
   anywhere. (This is a hypothesis pinned down by ruling out every other candidate mechanism — code-path
   tracing found no bug in the resolution pipeline itself against the bundled file; the duplicate-XSD-
   attribute gap in Verify is the one confirmed, reproducible gap in the app's own validation that would
   produce exactly this symptom in the user's actual file, which I cannot read directly.)

**Proposed fix:**
1. Add `editAbilityMode` to `pgtp_editor/resources/curated.xsd`, as a sibling `<xs:attribute
   name="editAbilityMode" use="optional">` block immediately after (or before) `viewAbilityMode` (line
   794) in the `Project_Presentation_Pages_Page_Type` complexType, with the identical
   0/1/2/3 = Disable/Separated page/Inline mode/Modal window enumeration `viewAbilityMode` and
   `insertAbilityMode` already use (same shape as lines 794-801). Cross-check against
   `tests/sample/ERP_i01-r02_italian.pgtp` for every element type that carries `editAbilityMode`
   (`<Page>` at minimum; also check `<OnTheFlyInsertPage>`, e.g. sample line 1096, which appears to be a
   *different* complexType — confirm with `grep -n editAbilityMode` on the sample and cross-reference
   which `xs:complexType` each hit's containing `<Page>`/`<OnTheFlyInsertPage>` element maps to via
   `curated.xsd`'s existing `insertAbilityMode`/`viewAbilityMode` entries at the same nesting depth) so
   the new attribute is added everywhere its `*AbilityMode` siblings already are, not just once. This
   file is user-facing sample/bundled data, not `pgtp_editor/` source code in the strict sense used by
   this agent's write-restriction — but per this agent's own rules the actual edit still belongs to the
   main session/resolver, not to this triage pass.
2. Close the Verify gap so this class of bug becomes visible instead of silent: in
   `pgtp_editor/schema_learning/xsd_verify.py::_Checker`, track per-open-`xs:complexType` the set of
   `xs:attribute name=` values seen so far (mirroring the existing `self._type_names` duplicate-type-name
   check at lines 66-72, and the existing per-attribute `self._enum_values_seen` pattern at lines 79-84 /
   89-94) and emit an `Issue(line, f"duplicate attribute name '{name}' in this complexType")` on the
   second and later occurrence. Needs a new per-complexType-frame stack (parallel to `_type_stack` in
   `xsd_load.py`, since `_Checker` doesn't currently track complexType nesting/frames at all — it only
   tracks a flat `_type_names` dict of type name → definition line) since complexTypes can be nested only
   via separate top-level records, not literally nested tags, in this dialect; a simple "reset the seen-
   names set on `complexType` start, nothing to pop" is sufficient because the dialect's `complexType`
   elements never nest (confirmed by `xsd_verify.py`'s existing flat `_type_names` bookkeeping and by
   `xsd_load.py`'s `_type_stack` handling of the *inline/anonymous* case only).
3. Optionally (flag for the resolving session to decide, not required for the report's specific
   symptom): consider whether `xsd_load.py::_Collector.end()` should itself warn/log on overwrite instead
   of purely relying on Verify catching it beforehand — but Verify catching it at edit/save/import time
   (per `CONSOLIDATED_SPEC.md` §11, Verify "auto-runs report-only on every Edit-XSD-tab save and on
   import") is probably sufficient and matches the existing duplicate-type-name precedent, which also
   only warns via Verify rather than refusing the load.

**Test impact:** `tests/schema_learning/test_xsd_verify.py` already covers duplicate-enumeration-value
and duplicate-type-name detection — extend with a new case: two `<xs:attribute name="X">` blocks inside
one `<xs:complexType>` produces the new "duplicate attribute name" Issue at the second block's line.
`tests/schema_learning/test_xsd_load.py` should get a case confirming current (to-be-kept) overwrite
behavior — last-one-wins — is at least deterministic, so a future change to warn-on-overwrite doesn't
silently change load semantics without a matching test update. `tests/schema_learning/test_settings_index.py`
and/or `tests/ui/test_properties_panel.py` should get a regression case for `editAbilityMode` once it's
added to `curated.xsd`: `value_label(model, "Project/Presentation/Pages/Page", "editAbilityMode", "3")`
resolves to `"Modal window"` the same way `insertAbilityMode` already does in that suite.

**Spec impact:** `docs/superpowers/CONSOLIDATED_SPEC.md` §11 (lines ~623-632) enumerates every Verify
dialect check as shipped; a new duplicate-attribute-name check is a genuine new rule, not a fix to
existing documented behavior — flag `spec-maintainer` to add it to that enumerated list once implemented.
No other spec divergence: the missing `editAbilityMode` entry is bundled *data* (curated.xsd content),
not a documented behavior, so no spec change is needed for that half of the fix.

---

## BUG-003: Table references panel click is slow; editor sluggish right after jump

**Status:** RESOLVED (649fffd)
**Reported:** 2026-08-01
**Report (verbatim):** "the Table references window is extremely slow when I click on a page. Feels
like it's not caching but reparsing when I click on a page, it also slows down the XMLEditor, after
doubleclicking on the table, it takes me there, but for a second even the scrolling is slow"

**Root cause:** Both symptoms trace to the same single hot spot —
`pgtp_editor/ui/properties_panel.py::PropertiesPanel._display_value` (lines 201-223) — reached via
`show_node` → `_populate_table` (lines 188-194, 229-235), which calls `_display_value` once per
`RowSpec` row every time Properties is repopulated:

```python
def _display_value(self, spec: RowSpec) -> str:
    ...
    resolved = attribute_at_position(
        self._xml_editor.toPlainText(), block.position() + index + 1
    )
```

`self._xml_editor.toPlainText()` (line 217) copies the **entire document text** into a fresh Python
string, and the module-level `attribute_at_position()` it feeds
(`pgtp_editor/ui/xml_editor.py:81`, delegating to `attribute_value_at_position` at line 91) calls
`xml_structure.scan(text)` (`pgtp_editor/ui/xml_structure.py:51`) — a full regex pass over the whole
document (`_TAG_RE.finditer`, one match per tag in the file) — plus an O(depth)-but-still-O(n)-per-call
`xml_structure.parent_tag_span` walk (line 140, inside `attribute_value_at_position`'s ancestor-chain
loop at lines 137-144) for every row. So Properties population cost is
**O(rows_in_panel × document_size)**, with a full `toPlainText()` document copy on top of that,
*for every row*, on *every* selection change — not once per document load.

Critically, `XmlEditor` already has exactly the cache this should be using and simply isn't:
`self._spans` / `self._spans_text` / `self._spans_revision` (`xml_editor.py:639-641`), built once by
`_rescan_structure()` (line 757-760) on `textChanged`, and consulted everywhere else in the file with a
"only rescan if `document().revision() != self._spans_revision`" guard (see `_update_matching_tag_highlight`,
lines 967-979, and `mousePressEvent`, lines 1572-1573, both of which explicitly comment that this avoids
"re-copy[ing] the whole multi-MB document" per interaction). `_display_value` bypasses this cache
entirely and calls the free-function `attribute_at_position(text, pos)` (which internally always calls
`xml_structure.scan(text)` fresh, with no cache parameter at all) directly on a brand-new
`toPlainText()` copy instead. This is the exact same class of bug as the O(n²) `build_parent_map` fix
noted in `docs/TEST_LOG.md` (2026-07-24) and the debug-tracer-flood fix — a per-interaction full-document
recompute where a cached/incremental one already exists elsewhere in the same file and just isn't wired
up here. (Note: `XmlEditor._hint_for_help_pos`, line 1530-1542, used by the attribute-value hover
tooltip, has this identical uncached pattern — same bypass of `_spans`/`_spans_text` — but that was not
part of this report; flagging it here as a second, related instance worth fixing in the same pass since
it's the same mechanism, not filing it separately.)

This single root cause explains both symptoms the report describes as if distinct:
1. **"extremely slow when I click on a page"** — `TableReferencesPanel._on_current_changed`
   (`pgtp_editor/ui/table_references_panel.py:60-65`) emits `selection_changed`, wired in
   `main_window.py:255` to `_on_table_ref_selection` (`main_window.py:1051-1052`), which calls
   `self.properties_panel.show_node(node, kind)` synchronously on the UI thread — this is the exact
   `_display_value`-per-row loop above, run on every single click, not cached across clicks the way the
   user suspected it should be (there is no keying on document revision or on the previously-resolved
   node/attribute at all — `_display_value` has no cache of any kind, so identical repeated clicks on the
   same row redo the same full scan).
2. **"slows down the XMLEditor... after doubleclicking... for a second even the scrolling is slow"** —
   double-clicking an unselected tree row in a `QTreeWidget` first fires `currentItemChanged` (Qt sets
   "current" on mouse press, before the double-click gesture is recognized) and *then*
   `itemDoubleClicked` (`table_references_panel.py:44`). So the same expensive Properties-panel
   `show_node` call from symptom 1 fires synchronously immediately before `jump_requested` →
   `_tree_jump_to_line` (`main_window.py:1073-1080`) → `XmlEditor.navigate_to_line`
   (`xml_editor.py:1089-1095`, itself cheap — `findBlockByNumber` + `centerCursor`, no document rescan).
   The felt "sluggish scrolling for a second" immediately after the jump is this synchronous
   full-document work finishing on the UI thread right as the view lands and the user starts
   interacting with the editor — not a separate bug in `navigate_to_line`, `_update_matching_tag_highlight`,
   or the syntax highlighter, all of which were checked and correctly use the `_spans` cache already.

**Proposed fix:**
1. Give `XmlEditor` a cache-aware public entry point that `PropertiesPanel` can call instead of the
   free function directly — e.g. `XmlEditor.attribute_at_position(self, pos: int)` (or
   `resolve_attribute_at(pos)`) that internally does the same "rescan only if
   `document().revision() != self._spans_revision`" guard already used by `_update_matching_tag_highlight`
   / `mousePressEvent`, then delegates to `xml_structure`'s position-resolution helpers using the cached
   `self._spans` / `self._spans_text` instead of a fresh `toPlainText()` + `scan()`. This likely means
   refactoring `attribute_value_at_position` in `xml_editor.py` (lines 91-146) to accept an optional
   pre-computed `spans` list (mirroring how `enclosing_tag_span_from_spans` in `xml_structure.py` already
   takes a `spans` parameter to avoid a redundant scan, lines 147-174) rather than always scanning
   `text` itself — keep the existing `attribute_at_position(text, pos)` free function working as a
   scan-from-scratch convenience wrapper for callers without a cached editor (if any remain) but make the
   cached path the one `XmlEditor` and `PropertiesPanel` use.
2. Change `pgtp_editor/ui/properties_panel.py::_display_value` (lines 216-218) to call the new
   cache-aware method on `self._xml_editor` instead of `attribute_at_position(self._xml_editor.toPlainText(), ...)`.
   Gotcha: `PropertiesPanel` is deliberately tested against a minimal duck-typed stub
   (`_RecordingXmlEditorStub` in `tests/ui/test_properties_panel.py:8-27`, exposing only
   `navigate_to_line` / `line_text` / `select_range_on_line`) — adding a new required method to that
   contract means updating the stub too (or making `_display_value` degrade gracefully via
   `getattr(self._xml_editor, "attribute_at_position", None)` and falling back to the current
   toPlainText()-based path only for stubs that don't implement it, so existing narrow test doubles don't
   break). Prefer extending the stub explicitly over silent fallback, to keep the contract obvious.
3. Apply the same fix to `_hint_for_help_pos` (`xml_editor.py:1530-1542`) since it's the same editor and
   the same cache is already sitting right there — trivial once the cache-aware resolver from step 1
   exists, just call it instead of `attribute_at_position(self.toPlainText(), char_pos)`.
4. No change needed to `navigate_to_line`, `_scroll_and_highlight_whole_line`, `_update_matching_tag_highlight`,
   or the syntax highlighter — confirmed these already use the `_spans` cache correctly and are not
   contributing to either symptom.

**Test impact:** `tests/ui/test_properties_panel.py` already builds `PropertiesPanel` against a real
`XmlEditor` for the label-resolution path (`test_attribute_row_shows_curated_label`,
`test_attribute_row_plain_without_model`, lines 235-279) — extend this file with a case asserting the
cache is actually used, e.g. monkeypatch `xml_structure.scan` (or `XmlEditor._rescan_structure`) to count
calls, populate the same node twice via `show_node`, and assert `scan`/rescan is not called a second time
when the document hasn't changed (only the one rescan from `setPlainText` at setup, none from
`show_node`). Also extend `_RecordingXmlEditorStub` (`test_properties_panel.py:8-27`) with the new
`attribute_at_position`/`resolve_attribute_at` method so existing stub-based tests keep passing once
`_display_value` is changed to call it. `tests/ui/test_xml_structure.py` may need a new case if
`attribute_value_at_position`/`enclosing_tag_span`-style helpers gain a `spans`-parameter overload
(mirroring existing `..._from_spans` coverage patterns already in that file, e.g.
`test_enclosing_tag_span_*` vs a hypothetical `..._from_spans` counterpart). `tests/ui/test_table_references_wiring.py`
already has `test_selection_drives_properties_panel` (line 71) and
`test_double_click_jumps_editor_to_lookup_line` (line 87) covering the exact two interactions from this
report — no new wiring test needed there, but worth confirming both still pass unmodified after the fix
(they test behavior, not call counts, so they shouldn't need changes).

**Spec impact:** none — `docs/superpowers/CONSOLIDATED_SPEC.md` does not document Properties-panel
value-label resolution as re-scanning the document per click; this is a straightforward performance bug,
not a divergence from a documented design decision.

---

## BUG-004: Light/Dark theme toggle has almost no visible effect app-wide

**Status:** RESOLVED (e2a8c14)
**Reported:** 2026-08-01
**Report (verbatim):** "light mode / dark mode doesn't work at all"

**Root cause:** There is no "dark mode" as a distinct, selectable option — only a single checkable
`View ▸ "Light Theme"` toggle (`pgtp_editor/ui/main_window.py:2009-2012`,
`_light_theme_action`, wired to `_on_light_theme_toggled` at line 855). "Dark" is not a theme the app
constructs at all; it is simply whatever the OS/native Qt style renders by default, left completely
untouched. This is explicit in the code's own comment at `main_window.py:424-429`: the app captures
`self._default_palette`/`self._default_style_key` at startup as "the app's ORIGINAL style + palette
(**its real OS-dark look**)" — i.e. the feature was built and tested on a platform (Windows, per the
`"windowsvista"` style-key example in the same comment block and the Windows-specific "Edit with PGTP
Editor" verb referenced in `main.py:36-38`) whose native/default Qt style happens to render dark. On a
system whose native Qt style does **not** default to dark (many Linux desktop environments, or Windows
without OS dark mode engaged), turning `Light Theme` off does not restore "dark" — it restores
`app.style().standardPalette()`/native rendering, which may look close to indistinguishable from what
`Light Theme` on shows, because most of the app's widgets never had a hardcoded dark appearance to begin
with; they were always following native Qt rendering.

Tracing what `apply_theme()` (`pgtp_editor/ui/theme.py:63-85`) actually changes: `app.setStyle("Fusion")`
+ `app.setPalette(light_palette())` when toggled on, restoring the captured native style/palette when
toggled off. This is a real, correctly-implemented **QPalette** flip (confirmed working by
`tests/ui/test_main_window_theme.py`) and toolbar icons are explicitly re-tinted
(`_refresh_toolbar_icons`, `main_window.py:934-940`) to track it. But only **two widgets in the entire
app** have any custom-painted, hardcoded-color appearance that responds to this: `XmlEditor` (Raw XML
pane) and (per the "Edit XSD" mode) `XsdEditor`, both via `apply_theme_colors`
(`pgtp_editor/ui/xml_editor.py:694-742`) which self-triggers off `changeEvent`'s
`ApplicationPaletteChange`/`PaletteChange` (lines 744-755) by reading its **own** palette's `Base`
lightness — not by receiving an explicit argument from `MainWindow`. Every other panel/dock/dialog in the
app (Properties, Table References, Caption Management, DB Check, Audit, Find bar, menus, toolbars sans
icon color, dialogs) has **no theme-awareness of any kind** — confirmed by `grep -rn
"apply_theme\|is_applying_theme\|ApplicationPaletteChange" pgtp_editor/ui/*.py` matching only
`xml_editor.py` (definition site) and `main_window.py` (the two `is_applying_theme()` dirty-tracking
guard call sites, unrelated to visual theming). They render however Qt's native style happens to draw a
`QPalette`-driven widget, which for many native styles (especially non-Fusion ones, and even Fusion with
only default-role colors set) produces very little visible change between "native" and
`light_palette()`, because `light_palette()` sets far more roles explicitly than most native styles key
off of, and non-Fusion native styles frequently ignore `QPalette` roles they don't need (this exact
tradeoff is called out in `theme.py`'s own docstring: "The native Windows style largely ignores QPalette,
so a light palette barely takes effect under it. Light mode therefore switches to the Fusion style...").
So the mechanism is not broken so much as **narrowly scoped**: it was designed/tested against one
platform's native-dark baseline and one style-switch trick, and never extended to cover the panels/tables
that make up most of the app's screen area. To a user on a different platform baseline, or simply looking
at any panel other than the Raw XML/Edit XSD editor, the toggle can appear to do nothing at all — which
matches the report's phrasing exactly.

**Proposed fix:** This is a scope gap, not a one-line fix; recommend the resolving session treat it as a
small design task rather than a pure bug patch:
1. Confirm with the user (or infer from the screenshot in BUG-005 below, which independently shows this
   exact failure mode inside Caption Management) which OS/Qt-style baseline they're on, to scope how much
   of "doesn't work at all" is the missing dark identity vs. genuinely-unstyled panels.
2. Give the app an explicit, symmetric **Dark** palette (mirroring `light_palette()` in
   `pgtp_editor/ui/theme.py`) instead of relying on "whatever native style happens to render" as the dark
   state — i.e. add a `dark_palette()` function and make `apply_theme(app, light, ...)` (or a renamed
   3-way `apply_theme(app, mode, ...)`) explicitly apply it for the "dark" case too, rather than restoring
   `default_palette`/`default_style`. This makes dark a real, tested, platform-independent state instead
   of "whatever the OS gave us at boot," directly fixing the "doesn't work on my platform" symptom. Gotcha:
   `_restore_theme`/`_on_light_theme_toggled`/`closeEvent`'s persistence key `"lightTheme"` is a bool
   today (`main_window.py:820, 862`); if this becomes a real tri-state or explicit dark/light choice, the
   QSettings key and `tests/ui/test_main_window_theme.py`'s round-trip assertions need updating together.
3. Extend theme-awareness to the panels this report and BUG-005 identify as unstyled: at minimum
   `CaptionManagementPanel` (see BUG-005, which is the concrete instance) and ideally every `QTableView`/
   `QTreeWidget`-based panel that sets any hardcoded `QColor` (grep `pgtp_editor/ui/*.py` for `QColor("#`
   outside `xml_editor.py`/`theme.py` to enumerate them — `caption_management_panel.py` is the one
   confirmed instance, others should be audited during implementation, not assumed absent). The
   `XmlEditor.apply_theme_colors` / `is_applying_theme` pattern (self-detecting `changeEvent` +
   light/dark constant swap) is the established precedent to extend to any other widget with hardcoded
   colors, rather than inventing a new mechanism.
4. Do **not** invent a second toggle/menu action for "Dark Theme" unless the resolving session decides a
   tri-state (native/light/dark) is the right shape — the minimal fix that satisfies "light/dark mode
   doesn't work" is making the existing single toggle's OFF state a real, tested dark palette rather than
   an unpredictable OS passthrough.

**Test impact:** `tests/ui/test_theme.py` (pure `light_palette()`/`apply_theme()` unit tests) and
`tests/ui/test_main_window_theme.py` (toggle wiring, style/palette assertions, icon legibility) are the
existing coverage to extend — add equivalent assertions for a new `dark_palette()` if step 2 is
implemented (currently `test_toggle_light_off_restores_captured_style_and_palette` only asserts equality
with whatever was captured at test-window construction time, which is exactly the "restores native, not a
real dark state" behavior this bug is about — that assertion will need to change in shape, not just
value, if dark becomes an explicit palette). `tests/ui/test_xml_editor_theme.py` stays as-is (that half
already works correctly and is not part of this bug). New coverage needed for whichever additional panels
get wired in per step 3 — see BUG-005's test-impact note for the Caption Management instance
specifically.

**Spec impact:** `docs/superpowers/CONSOLIDATED_SPEC.md` (~line 335-336) documents the feature exactly as
narrowly as it was built: "View ▸ 'Light Theme' checkable toggles default vs `light_palette()` on the
app." This is technically accurate to the current code, so the *current* (buggy-feeling) behavior is not
a documented intentional decision so much as a spec that describes a narrower feature than the "light
mode / dark mode" framing users bring to it. Flag `spec-maintainer` after a fix lands to update this
section to reflect whatever shape is chosen (explicit dark palette vs. native passthrough; which panels
are theme-aware) — the current one-line spec entry under-describes the feature's actual (narrow) scope
and should be expanded regardless of which fix direction is taken.

---

## BUG-005: Caption Management row-tint colors leave black text unreadable on dark row backgrounds

**Status:** RESOLVED (649fffd)
**Reported:** 2026-08-01
**Report (verbatim):** "also in light mode caption management there's no contrast between backgrounds
and text (see screenshot) dark brown and dark blue bg with black text..." (screenshot: Caption Management
grid with Breadcrumb/Element/Anchor/Attribute/Value/New-Value-style columns; several rows rendered with a
dark maroon/brown background and other rows with a dark navy background, all with black cell text)

**Root cause:** `pgtp_editor/ui/caption_management_panel.py`, `_CaptionTableModel.data()` (lines 211-243).
Two hardcoded, theme-independent background colors are defined at module scope:
```python
_INCONSISTENT_BACKGROUND = QColor("#3a2f1d")  # warm/dark-brown tint, line 89
_CHANGED_BACKGROUND = QColor("#26343a")       # cool/dark-navy tint, line 91
```
and returned from `data()`'s `Qt.ItemDataRole.BackgroundRole` branch (lines 238-242) for any row whose
`(anchor, attribute)` group is inconsistent, or whose New Value is non-empty (changed wins over
inconsistency) — exactly the two row states the screenshot shows (dark brown = inconsistent-value group,
dark navy = changed/edited row). Critically, **`data()` never returns anything for
`Qt.ItemDataRole.ForegroundRole`** for these rows (the only `ForegroundRole` handling in the whole model
is the unrelated filtered-column-header case, `headerData()` lines 207-208, using
`_FILTER_HEADER_FOREGROUND`). With no explicit foreground set, Qt/the view falls back to the
palette's default text role, which under the app's default (OS-native/"dark," see BUG-004) palette is
light-colored text — readable against these dark tints — but under `Light Theme`
(`pgtp_editor/ui/theme.py::light_palette()`, `role.Text = QColor(0x1E, 0x1E, 0x1E)`, near-black, line 45)
becomes near-black text on a `#3a2f1d`/`#26343a` background: exactly the "dark brown and dark blue bg
with black text" the report describes. This is a genuine, theme-independent defect in the row-tint
design, separate from BUG-004's "toggle barely does anything" — this table's colors are the one place in
the app that actively fights the Light Theme palette rather than simply ignoring it, because the
background halves of these two colors were tuned to work only against dark/light-foreground text and were
never paired with an explicit matching foreground.

**Proposed fix:** In `pgtp_editor/ui/caption_management_panel.py`:
1. Add matching `Qt.ItemDataRole.ForegroundRole` colors alongside `_INCONSISTENT_BACKGROUND` and
   `_CHANGED_BACKGROUND` (e.g. `_INCONSISTENT_FOREGROUND`/`_CHANGED_FOREGROUND`, near-white, chosen for
   contrast against each specific dark background — following the same "define a foreground alongside a
   background instead of relying on palette fallback" pattern already used for
   `_FILTER_HEADER_FOREGROUND`/filtered-header styling at lines 86, 207-208) and return them from
   `data()`'s `ForegroundRole` branch (extend the existing `if role == Qt.ItemDataRole.BackgroundRole:`
   block at line 238 with a parallel `if role == Qt.ItemDataRole.ForegroundRole:` block using the same
   `if self._new_values[row]: ... elif self._is_inconsistent(row): ...` precedence). This makes the two
   tinted states correct under **either** theme, independent of whether BUG-004 is fixed — a fixed
   explicit foreground on a fixed background is theme-proof by construction, which is simpler and more
   robust than trying to make these two colors theme-aware (no `apply_theme_colors`-style swap needed).
2. `set_new_values()` (lines 148-169) and `_emit_row_changed()` (lines 261-270) already include
   `Qt.ItemDataRole.BackgroundRole` in their `dataChanged.emit(..., [roles])` role lists when background
   can change — both must also add `Qt.ItemDataRole.ForegroundRole` to those same role lists once
   `data()` starts returning it, or a row that transitions into/out of the changed/inconsistent state via
   a batched update won't repaint its now-stale foreground until some unrelated repaint trigger fires.
3. Do not touch `_FILTER_HEADER_FOREGROUND`/header coloring (lines 86, 192-209) — unrelated to this
   report, already has its own explicit foreground, not implicated.

**Test impact:** `tests/ui/test_caption_management_panel.py` already has a `_background(panel, row)`
helper (line 160) and asserts `BackgroundRole` for both tint states (lines 168, 181, 184-185, 197-198,
996) — add a parallel `_foreground(panel, row)` helper and equivalent assertions
(`_foreground(panel, 0) == _CHANGED_FOREGROUND` / `== _INCONSISTENT_FOREGROUND` at the same rows/states
already exercised) so the fix is regression-locked the same way the background colors are. Also extend
whichever test currently exercises `set_new_values`'s batched `dataChanged` role list (search for
`dataChanged` or `set_new_values` in the same file) to assert `ForegroundRole` is included alongside
`BackgroundRole` once step 2 lands.

**Spec impact:** none found — `docs/superpowers/CONSOLIDATED_SPEC.md` documents Caption Management's
inconsistency/changed-row tinting behavior (search the spec for "inconsistent"/"Changed" column
semantics) as a background-color-only design; there's no mention of foreground/contrast handling one way
or the other, so this is an omission being fixed, not a documented intentional decision. No spec update
needed unless the resolving session wants to explicitly document "tinted rows always pair an explicit
foreground with their background" as a stated convention, which would be a `spec-maintainer` nice-to-have,
not a requirement.

---

## BUG-006: Calculated columns (`isCalculated="true"`) are flagged as mismatches in XML→Database check
**Status:** RESOLVED (44a2bbe)
**Reported:** 2026-08-01
**Report (verbatim):** "when a calculated column is created in the xml (<ColumnPresentation fieldName="**" isCalculated="true" it should not show up as mismatch, but with a different symbol, orange and not as mismatch."

**Root cause:** `isCalculated` is parsed and available but never read anywhere in the codebase —
confirmed by `grep -rln "isCalculated\|is_calculated" pgtp_editor/` returning empty. The raw attribute
*is* present in the parsed model: `pgtp_editor/model/parser.py::_parse_columns` (around line 252) does
`attrib=dict(col_el.attrib)`, so every `<ColumnPresentation>` attribute including `isCalculated="true"`
lands in `ColumnNode.attrib`, but `pgtp_editor/model/nodes.py::ColumnNode` (lines 93-107) only exposes a
typed `field_name` property — no `is_calculated` property exists to read it back out. The value is then
lost entirely one layer up: `pgtp_editor/db/compare.py::xml_table_columns` (lines 54-82) collapses each
table's `list[ColumnNode]` down to a bare `set[str]` of field names (`bucket.add(field_name)` at line 70),
discarding the `ColumnNode` (and with it `isCalculated`) before `check_xml_against_db` (lines 90-115) ever
runs. `check_xml_against_db` then builds `ColumnCheck(name=col, ok=schema.column(table_name, col) is not
None, ...)` for every name in that set (lines 98-105) — a calculated column's `fieldName` legitimately
has no matching physical DB column, so `schema.column(...)` returns `None` and `ok` is unconditionally
`False`, i.e. it is indistinguishable from a genuinely missing/renamed column. Rendering then follows
`ColumnCheck.ok` mechanically: `pgtp_editor/ui/db_check_panel.py::_make_column_item` (lines 132-151) picks
`marker = "✓" if column.ok else "✗"` and `item.setForeground(0, QBrush(_OK_COLOR if column.ok else
_BAD_COLOR))` (using `_OK_COLOR`/`_BAD_COLOR` at lines 43-44) — there is only a binary ok/not-ok state
today, no third category. `_mismatch_count` (lines 91-97) and the "Show only mismatches" filter in
`_rebuild` (lines 107-119) both key off the same `column.ok` bool, so a calculated column also inflates
the header's mismatch count and appears when "Show only mismatches" is checked. Note: `check_db_against_xml`
(the DB→XML direction, lines 118-144) is unaffected by this bug — it iterates real DB columns and only
uses `xml_table_columns` for membership testing (`column.name in xml_columns`), so a calculated XML column
with no DB counterpart simply never appears as a DB row there; nothing to fix on that side.

**Proposed fix:**
1. `pgtp_editor/model/nodes.py::ColumnNode` — add an `is_calculated` property mirroring the existing
   `field_name` property (line 105-107): `return self.attrib.get("isCalculated", "").lower() == "true"`
   (match whatever case/bool-string convention other boolean XML attributes in this codebase already use —
   check how `visible="false"` is parsed in `_build_representation_index`/`RepresentationVisibility` in
   `pgtp_editor/model/parser.py` for the established true/false string convention and reuse it verbatim
   rather than inventing a new parsing rule).
2. `pgtp_editor/db/compare.py::xml_table_columns` — this function's return type (`dict[str, set[str]]`)
   is too lossy to carry the flag through; either (a) change its return shape to
   `dict[str, dict[str, bool]]` (field_name → is_calculated) and update its two call sites
   (`check_xml_against_db` and `check_db_against_xml`) plus its docstring, or (b) keep
   `xml_table_columns` as-is for the DB→XML membership-test use case and add a small sibling helper (e.g.
   `xml_calculated_columns(project) -> dict[str, set[str]]`, table → set of calculated field names) used
   only by `check_xml_against_db`. Prefer (a) for a single source of truth, but either is acceptable as
   long as `check_db_against_xml` keeps working unchanged (it only needs name membership, not the flag).
   Watch the union semantics already documented in the docstring (pages/details bound to the same table
   union their columns) — if two representations disagree on `isCalculated` for the same fieldName
   (shouldn't happen per one `<ColumnPresentation>` per fieldName within one page, but unioned across
   pages/details it's structurally possible), OR them (a field is "calculated" if calculated anywhere it
   appears) rather than picking one arbitrarily.
3. `pgtp_editor/db/compare.py::ColumnCheck` (lines 38-42) — add a field to carry the new state, e.g.
   `is_calculated: bool = False`, defaulted so `check_db_against_xml`'s `ColumnCheck` construction (line
   127-133, which has no notion of calculated columns) doesn't need to change.
4. `check_xml_against_db` (lines 90-115) — when building each table's `column_checks`, look up
   `is_calculated` for the field name and: keep `ok=schema.column(...) is not None` computed as before
   (still useful/harmless if it happens to exist), but pass `is_calculated=<flag>` into `ColumnCheck`. The
   panel is what decides how to *render* the three-way state (match/calculated/mismatch), not this pure
   layer — `compare.py` should stay Qt-free and just expose the flag (per its own module docstring, "Qt-free").
5. `pgtp_editor/ui/db_check_panel.py`:
   - Add an `_CALC_COLOR = QColor("#d08a1a")` (orange, matching the file's existing pattern of one
     `QColor` constant per semantic state alongside `_OK_COLOR`/`_BAD_COLOR` at lines 43-44) and a
     distinct marker glyph — reuse the "different symbol" the report explicitly asks for, e.g. `"∼"` or
     `"⚙"` (avoid `"✓"`/`"✗"` reuse; pick something that reads clearly in a monospace-ish tree at small
     size — `"~"` is a safe, universally-renderable fallback if a fancier glyph risks missing-font boxes).
   - `_make_column_item` (lines 132-151): branch three ways instead of two —
     `if column.is_calculated: marker, color = "~", _CALC_COLOR elif column.ok: ... else: ...` (adjust
     exact structure to taste) for both the marker and `setForeground`. A calculated column's `ok` will
     still technically be `False` from step 4 unless step 4 is changed to force `ok=True` for calculated
     columns — **decide explicitly and document the choice**: the cleanest approach is to keep `ok` as
     "does a matching DB column literally exist" (informational, e.g. still useful if someone made a
     calculated column that coincidentally shadows a real one) and have the panel/`_mismatch_count`
     treat `is_calculated` as an override that takes precedence over `ok` for both display and counting —
     i.e. calculated columns are never counted as mismatches and never show the ✗ marker, regardless of
     the underlying `ok` value.
   - `_mismatch_count` (lines 91-97): the `sum(1 for column in table.columns if not column.ok)` term must
     exclude calculated columns — change to `if not column.ok and not column.is_calculated`. Otherwise the
     header count and this fix's own visual change disagree with each other.
   - `_rebuild`'s "Show only mismatches" filter (lines 107-119): `mismatch_columns = [c for c in
     table.columns if not c.ok]` (line 111) needs the same `and not c.is_calculated` exclusion, otherwise
     calculated columns still appear (as orange, but present) when the user has asked to see only
     mismatches, which contradicts "should not show up as mismatch" from the report. Decide whether
     calculated columns should be hidden entirely under the filter (mismatch-only view stays purely
     red/mismatch) or still shown as a non-filtered informational passthrough — hiding them (excluding
     from `mismatch_columns` entirely) matches the report's intent most directly.
   - `contextual_rename` (lines 162-172) and the context-menu "Rename … in XML…" action (lines 219-228)
     currently gate only on `if ok: return` — must also gate on `is_calculated` (a calculated column has
     no DB-side name to reconcile via rename; offering "Rename in XML…" for it would be nonsensical/wrong).
   - The `Qt.ItemDataRole.UserRole` tuple stored on each column item (`("column", column.name, column.ok)`
     at line 146) is read back by `contextual_rename` and `_on_context_menu` as `(kind, name, ok)` — if
     `ok` itself is *not* changed to `True` for calculated columns (per the recommended approach above),
     those two call sites must independently know about `is_calculated`, e.g. by storing a 4-tuple
     `(kind, name, ok, is_calculated)` and updating every unpacking site (`_on_double_click` line 156-160,
     `contextual_rename` line 166-172, `_on_context_menu` line 219-228) — grep all three for the 3-tuple
     unpack `kind, name, ok = data` / `kind, _name, ok = data` and update consistently, since a partial
     update will crash on unpack-count mismatch.

**Test impact:** `tests/db/test_compare.py` — extend `_col()`/`_make_project()` (or add a new
calculated-column fixture) to set `isCalculated="true"` on a `ColumnNode.attrib`, then add cases
alongside `test_check_xml_against_db_directions` asserting the resulting `ColumnCheck.is_calculated is
True` and (depending on the chosen `ok` semantics from step 4) whatever `ok` value was decided; also a
`xml_table_columns`/new-helper unit test asserting the calculated flag survives the union-across-pages
case with an OR precedence test (one page marks a field calculated, another page references the same
field without the attribute → still calculated). `tests/ui/test_db_check_panel.py` — extend `_checks()`
with a `ColumnCheck(..., is_calculated=True)` fixture and add cases asserting: the marker is the new
glyph (not `✓`/`✗`), the foreground is `_CALC_COLOR`, the column is excluded from `_mismatch_count`
(extend `test_header_shows_direction_connection_and_mismatch_count`), the column is excluded when "Show
only mismatches" is checked (extend `test_show_only_mismatches_filters`), and no rename context-menu
action is offered for it (extend `test_rename_requested_only_for_not_found_xml_to_db`). Also check
`tests/ui/test_db_check_wiring.py` for any end-to-end assertion that constructs `ColumnCheck` positionally
(if `is_calculated` is added as a new dataclass field, any positional-args construction elsewhere in that
file or `test_compare.py` needs updating to keep passing, or the field must be keyword-only/defaulted to
avoid breaking existing positional calls like `ColumnCheck("gone", False, None)` in
`tests/ui/test_db_check_panel.py` line 29 — confirmed safe since `info` already defaults via
`field(default=None)`-style annotation, so append `is_calculated: bool = False` last to preserve all
existing positional call sites).

**Spec impact:** `docs/superpowers/CONSOLIDATED_SPEC.md` §17 (Database) documents `TableCheck`/
`ColumnCheck` shape and the panel's `✓`/`✗` glyph convention (lines 881-891) with no mention of
`isCalculated` or a third/calculated state — this is a genuine capability gap, not a documented
intentional decision (`isCalculated` isn't referenced anywhere in the spec or codebase today). After the
fix lands, dispatch `spec-maintainer` to add the `is_calculated` field to the `ColumnCheck` shape
description and the new orange/`~`-marker calculated state to the `DbCheckPanel` glyph/color convention
in §17.

---

## BUG-007: View-menu dock checkboxes don't uncheck when the dock is closed via its own title-bar ✕
**Status:** RESOLVED (44a2bbe)
**Reported:** 2026-08-01
**Report (verbatim):** "when I close the BrowserPane, in the View the checkbox is not changing (appears
to be still open). Closing the BrowserPane must set all BrowserPane panels checkbox not checked"

**Root cause:** The report's "BrowserPane" cannot literally be `ui/ddl_buffer_panel.py::BrowserPanel` —
grepped case-insensitively for `BrowserPane`/`BrowserPanel` across the repo and confirmed via
`docs/TEST_LOG.md` (2026-08-01 entry) and `CONSOLIDATED_SPEC.md:921` ("no `EditorPanel`, no SQL
highlighter mode, no `main_window.py` wiring yet") that `BrowserPanel` is implemented and tested in
isolation but is **not yet instantiated anywhere in `pgtp_editor/ui/main_window.py`** — there is no dock,
no tab, and no View-menu action for it at all today, so the reported symptom cannot reproduce against
that class. Treating "BrowserPane" as the user's loose/mistaken name for one of the window's real
dockable panels instead: `pgtp_editor/ui/main_window.py::_build_view_menu` (lines 1952-1997) wires three
real `QDockWidget`s this way —
- `tree_dock` ("Project Tree", line 229) ← `tree_action.toggled.connect(self.tree_dock.setVisible)` (line 1958)
- `properties_dock` ("Properties", line 358) ← `properties_action.toggled.connect(self.properties_dock.setVisible)` (line 1963)
- `audit_dock` ("Audit / Problems", line 261) ← `audit_action.toggled.connect(self.audit_dock.setVisible)` (line 1974)

None of the three docks has `setFeatures()` called anywhere in `main_window.py`, so each keeps Qt's
default `QDockWidget.DockWidgetFeature` flags, including `DockWidgetClosable` — i.e. each genuinely has
its own native ✕ close button on its title bar (this is very plausibly what the user actually clicked,
mistaking one of these left/right dock panels for a "BrowserPane"). The wiring above is **one-directional
only**: the checkable `QAction.toggled` signal drives `dock.setVisible`, but nothing connects back from
the dock to the action. Closing a dock via its own ✕ calls `QDockWidget.closeEvent`, which hides the dock
and emits `visibilityChanged(False)` — but no slot listens to that signal for these three docks, so the
corresponding View-menu `QAction.isChecked()` stays `True` even though the dock is now hidden. Confirmed
by reading `tests/ui/test_menus.py` (`test_toggling_project_tree_hides_dock` /
`test_toggling_audit_panel_hides_dock` / `test_toggling_properties_panel_hides_dock`, lines 178-205):
every existing test only drives the action→dock direction (`find_action(...).trigger()` then asserts
`dock.isVisible()`); none drives dock-close→action direction. This is a distinct, existing pattern gap
from the *tab*-visibility sync that already works correctly elsewhere in the same file — e.g.
`center_stage.manual_visibility_changed` (`ui/center_stage.py:29,110,117`) is a genuine bidirectional
`Signal(bool)` that `MainWindow._on_manual_visibility_changed` (line 2982) consumes to keep the Contents
tab in lockstep with the Manual tab — but that pattern applies to `CenterStage` *tabs*, not the
`QDockWidget`s at issue here, and was never extended to the three real docks. The fourth View-menu row,
"Find table reference" (`table_refs_action`, line 1965), is a **tab** inside `left_tabs` (not a
`QDockWidget` of its own — it lives inside `tree_dock`'s tab widget, see line 250-254), so it has no
independent title-bar ✕ and is not part of this bug; likewise "Raw XML Panel" is also a `CenterStage` tab,
not a dock. So exactly three docks (`tree_dock`, `properties_dock`, `audit_dock`) are affected — this
matches the report's plural "all BrowserPane panels" if the user is bundling multiple left/right docks
under one remembered name, though it's equally likely they only interacted with one and used "panels"
loosely; the fix should cover all three regardless since the root cause is identical and shared.

**Proposed fix:** In `pgtp_editor/ui/main_window.py::_build_view_menu`, after each `toggled.connect(...)`
call for `tree_action`, `properties_action`, and `audit_action`, add the reverse connection: e.g.
`self.tree_dock.visibilityChanged.connect(tree_action.setChecked)`, and similarly
`self.properties_dock.visibilityChanged.connect(properties_action.setChecked)` and
`self.audit_dock.visibilityChanged.connect(audit_action.setChecked)`. Store the three actions as
`self._tree_action` / `self._properties_action` / `self._audit_action` (currently only
`table_refs_action`/`_raw_xml_panel_action` are kept as attributes; the other three are local variables in
`_build_view_menu` — promote them to `self.` attributes so the `visibilityChanged` connection can
reference them, and so tests can look them up directly instead of via `find_action(view_menu, ...)` if
convenient). Re-entrancy check: `QAction.setChecked(bool)` does not itself emit `toggled` if the value is
unchanged, and Qt's `QAction.toggled` only fires on an actual state change, so
`action.setChecked(dock.isVisible())` in response to `visibilityChanged` will not re-trigger
`dock.setVisible` in a loop under normal use — but double check empirically once implemented (the existing
`center_stage.py` Manual pattern avoids a hand-rolled recursion guard entirely by relying on this same Qt
signal-coalescing behavior, so no extra guard is expected to be needed here either; if a loop is observed,
follow that file's approach rather than inventing a new guard mechanism). Also note `QDockWidget.
visibilityChanged` fires not just on user-close but also on programmatic `setVisible`/tabify/float changes
— this is *desired* here (it's exactly what keeps the checkbox honest in all cases, not just the ✕ click),
so no filtering of the signal is needed beyond the direct connect.

**Test impact:** `tests/ui/test_menus.py` — extend the existing
`test_toggling_project_tree_hides_dock` / `test_toggling_audit_panel_hides_dock` /
`test_toggling_properties_panel_hides_dock` (lines 178-205), or add three sibling tests, that instead
close the dock directly (`window.tree_dock.close()` / `.hide()`, mirroring how a title-bar ✕ click
hides the dock) and assert the corresponding View-menu action's `isChecked()` is now `False` — e.g.
`window.tree_dock.close(); assert find_action(view_menu, "Project Tree").isChecked() is False`. Also add
the inverse case (re-show the dock via `.show()` and confirm the action re-checks) since
`visibilityChanged` fires both ways. `BrowserPanel` itself needs no test changes — it remains unwired and
out of scope per the DDL Explorer follow-up increment noted in `docs/TEST_LOG.md`.

**Spec impact:** none — `docs/superpowers/CONSOLIDATED_SPEC.md` does not document dock-close/View-menu
sync behavior anywhere (grepped for "View menu", "QDockWidget", "toggleViewAction", "close button"); this
is an undocumented implementation gap, not a divergence from a stated design decision. No spec-maintainer
follow-up needed unless the fix introduces new user-facing behavior worth calling out (unlikely — this
just makes existing documented checkboxes accurate).

---

## BUG-008: Project-tree selection → Properties panel is very slow on large projects
**Status:** RESOLVED (75b4052)
**Reported:** 2026-08-01
**Report (verbatim):** "Project tree selection to property showing is very slow"

**Root cause:** The slow step is building the Properties panel value cells, not the tree signal itself.
Selecting a tree node fires `ProjectTreePanel._on_current_item_changed`
(`pgtp_editor/ui/project_tree.py:74`) → `MainWindow._on_tree_selection_changed`
(`pgtp_editor/ui/main_window.py:1045`) → `PropertiesPanel.show_node`
(`pgtp_editor/ui/properties_panel.py:187`) → `_populate_table` (line 226), which calls
`_display_value(row_spec)` (line 231) **once per attribute row**.

`PropertiesPanel._display_value` (`properties_panel.py:200`) — only when a curated schema model has been
injected via `set_schema_model` (wired at `main_window.py:454` after schema load; when the model is
`None` the whole label path is skipped and selection is fast) — does, per row:
`self._xml_editor.resolve_attribute_at(...)` (line 215). `XmlEditor.resolve_attribute_at`
(`pgtp_editor/ui/xml_editor.py:1142`) delegates to the module-level
`attribute_value_at_position(text, pos, spans)` (`xml_editor.py:91`). Even though the `spans` list is
cached and revision-guarded (so `scan()` is not re-run), `attribute_value_at_position` itself is O(N) in
the number of spans **per call**:
- a full linear pass over every span computing `_opening_tag_end` (char-by-char text scan) to find the
  containing span (`xml_editor.py:125-133`), then
- an ancestor walk that calls `xml_structure.parent_tag_span` repeatedly (`xml_editor.py:143-149`);
  `parent_tag_span` (`xml_structure.py:188`) is itself an O(N) linear scan over all spans per step.

So one node selection costs roughly O(rows × N × avg_tag_len). On a large `.pgtp` (the codebase already
cites `dev_Ferrara` at ~37k tags in the `build_parent_map` docstring at `xml_structure.py:213-224`) this
is the same O(n²)-per-operation hazard that `build_parent_map` was introduced to kill — but the
Properties-label path never adopted it and re-derives the containing span and full ancestor chain from
scratch for every attribute row. This is a direct sibling of BUG-003 (Table-references click slowness):
same cause family (per-item full-document structural re-derivation), same fix direction (reuse a cached,
precomputed structure).

**Proposed fix:** Make the per-row attribute resolution reuse precomputed structure instead of
re-scanning all spans per row. Concrete shape:
- In `XmlEditor` (`pgtp_editor/ui/xml_editor.py`), build a parent map alongside the existing `_spans`
  cache: extend `_rescan_structure` (line 762) to also store
  `self._spans_parent_map = xml_structure.build_parent_map(self._spans)` (helper already exists at
  `xml_structure.py:213`, O(n log n) single pass). Keep it under the same `_spans_revision` guard so it
  invalidates with the spans.
- Rework `attribute_value_at_position` / the `resolve_attribute_at` path so the ancestor walk uses the
  parent map (`parent_map[id(span)]`) instead of calling `parent_tag_span` per level. The containing-span
  lookup at `xml_editor.py:125-133` should reuse the same containing-span logic the cached cursor path
  already uses (`enclosing_tag_span_from_spans`, `xml_structure.py:147`) rather than its own O(N) loop —
  note the quirk in the current loop that recomputes the real `>` via `_opening_tag_end` to be robust to
  `>` inside quoted values; preserve that robustness (either fold it into the shared helper or keep a
  quote-aware containing lookup) so behavior does not regress on tags with `>` in attribute values.
- Alternatively/additionally, memoize per `show_node` call: within one `_populate_table`, all attribute
  rows of a Page/Column resolve to the **same** element (same `target_line`/tag), so the
  `(tag_chain)` ancestor resolution can be computed once per distinct `target_line` and reused across that
  node's rows instead of once per row. This alone removes most of the cost even before the parent-map
  change and is the lowest-risk first step.
- Gotchas: (1) the label path only runs when `set_schema_model` has been given a non-`None` model, so any
  perf test must inject a schema model to reproduce — otherwise `_display_value` short-circuits at
  `properties_panel.py:201` and looks fast. (2) `resolve_attribute_at` must keep its revision guard so a
  parent map isn't served stale after an edit. (3) Do not change the displayed strings — this is a pure
  performance fix; `value_label` output and navigate-on-click behavior must be identical.

**Test impact:** Existing coverage: `tests/ui/test_properties_panel.py` and
`tests/ui/test_properties_panel_rows.py` (Properties row-building + display, including label decoration);
`tests/ui/test_xml_editor_nav_perf.py` (the established "no rescan / no full-document copy per operation"
regression pattern — extend, don't duplicate); `tests/ui/test_xml_structure.py` (spans / `parent_tag_span`
/ `build_parent_map`). New cases needed: (a) a perf regression test in the `nav_perf` style asserting that
`PropertiesPanel.show_node` on a node with many attribute rows, **with a schema model injected**, does not
call `xml_structure.scan` and does not perform O(rows) full-span ancestor walks (e.g. count
`parent_tag_span`/`scan` calls, or assert calls are bounded by distinct target lines rather than row
count); (b) an equivalence test that the parent-map-backed `resolve_attribute_at` returns exactly the same
`(tag_chain, attr)` as the from-scratch `attribute_at_position(text, pos)` for representative positions,
including a tag with a `>` inside a quoted attribute value.

**Spec impact:** none — `CONSOLIDATED_SPEC.md` §10 (Properties panel) and §11 (curated-label display)
specify the label decoration as "display-only" with unchanged navigate-on-click behavior; this is purely a
performance fix within that contract. No divergence from a stated decision, so no spec-maintainer
follow-up unless the fix changes user-visible behavior (it should not).

---

## BUG-009: Linux/KDE shows a generic "W" placeholder icon instead of the app icon (taskbar + title-bar)
**Status:** RESOLVED (2508d2a)
**Reported:** 2026-08-01
**Report (verbatim):** "application icon in linux kde is a W instead of the application's own icon both in the taskbar and in the window's corner"

**Root cause:** The application never sets a window/application icon and never establishes a
desktop-file/WM_CLASS identity, so on KDE (Wayland and X11) the window falls back to the compositor's
generic placeholder (the "W" glyph). Concretely:
- `pgtp_editor/main.py`, `main()` (lines ~43-88): creates `QApplication(sys.argv)` (line 67) and shows
  `MainWindow` but never calls `QApplication.setWindowIcon(...)`, `QApplication.setApplicationName(...)`,
  `QApplication.setApplicationDisplayName(...)`, `QApplication.setOrganizationName(...)`, or
  `QApplication.setDesktopFileName(...)`. (The `QSettings` on lines 53-58 uses "MDS"/"PGTP Editor" but
  that never propagates to the `QApplication` identity.)
- `pgtp_editor/ui/main_window.py` sets `setWindowTitle("PGTP Editor")` (line 211) but never
  `setWindowIcon(...)`. A grep across `pgtp_editor/` confirms there is **no** `setWindowIcon` /
  `setDesktopFileName` / `setApplicationName` call anywhere.
- No brand icon ships inside the importable package. The only app icon in the repo is
  `docs/pgtpeditor.ico` (MS Windows .ico, 16x16 + 32x32), which lives **outside** `pgtp_editor/` and is
  **not** listed in `pyproject.toml`'s package data (line 29 ships only `resources/*.md`, `resources/*.xsd`,
  `resources/icons/breeze/*`), so it is not available at runtime from an installed wheel. There is no
  PNG/SVG app icon under `pgtp_editor/resources/` and no `.desktop` file anywhere in the repo.

On KDE, the taskbar icon is resolved by matching the window's WM_CLASS / `desktopFileName` against an
installed `.desktop` file; with neither a `setWindowIcon` (which drives the in-window/title-bar corner
icon and is also used as the taskbar fallback) nor a `desktopFileName`, KDE has nothing to match and shows
the generic placeholder.

**Proposed fix:** Two coordinated parts.
1. **Ship a real brand icon inside the package and set it at startup.** Add an app icon under
   `pgtp_editor/resources/` — prefer a scalable `app_icon.svg` plus/or a multi-size `pgtpeditor.png`
   (256x256 recommended; can be rendered from the existing `docs/pgtpeditor.ico`). Add its glob to the
   `[tool.setuptools.package-data]` `"pgtp_editor"` list in `pyproject.toml` (line 29) so it ships in the
   wheel (e.g. add `"resources/app_icon.svg"` / `"resources/*.png"`). In `pgtp_editor/main.py` `main()`,
   right after `app = QApplication(sys.argv)` (line 67) and **before** `MainWindow(...)`/`window.show()`,
   set the application identity and icon:
   - `QApplication.setApplicationName("PGTP Editor")` and
     `QApplication.setOrganizationName("MDS")` (match the existing `QSettings` "MDS"/"PGTP Editor" scope on
     lines 53-58 for consistency), plus `QApplication.setApplicationDisplayName("PGTP Editor")`.
   - `QApplication.setDesktopFileName("pgtp-editor")` (must match the `.desktop` file's basename from part
     2 — this is what KDE/Wayland keys the taskbar icon off; getting the name wrong silently reverts to the
     placeholder).
   - Build the icon via a resource-path helper. Use `importlib.resources`
     (`importlib.resources.files("pgtp_editor.resources") / "app_icon.svg"`) or a
     `Path(__file__).parent / "resources" / "app_icon.svg"` lookup, wrap it in `QIcon`, and call
     `app.setWindowIcon(icon)`. Follow the existing resource-loading convention in
     `pgtp_editor/ui/icons.py` (which already loads vendored SVGs from `resources/icons/breeze/`) rather
     than inventing a new path scheme. Guard against a missing file (skip silently if the icon can't be
     loaded) so startup never crashes on a partial install.
   - Optionally also call `window.setWindowIcon(icon)` in `MainWindow.__init__` (near the
     `setWindowTitle("PGTP Editor")` on line 211) as a belt-and-braces fallback, but the `QApplication`-level
     call is normally sufficient and is the primary fix.
2. **Ship a Linux `.desktop` file so KDE can associate the taskbar icon.** Add a
   `pgtp-editor.desktop` (basename must equal the `setDesktopFileName` argument, i.e. `pgtp-editor`) with
   at minimum `Exec=`, `Icon=pgtp-editor`, `Name=PGTP Editor`, `Type=Application`, and a `Categories=`
   line. Install the icon into the hicolor theme (e.g.
   `share/icons/hicolor/scalable/apps/pgtp-editor.svg` and/or `.../256x256/apps/pgtp-editor.png`) so the
   `Icon=pgtp-editor` name resolves. Decide where this lives (a `packaging/linux/` dir plus install notes,
   or `data_files` in `pyproject.toml`); a pip install alone won't place a `.desktop` in
   `~/.local/share/applications`, so document/automate the install step. Gotchas: the `.desktop` basename,
   the `setDesktopFileName` string, and the `Icon=` name must all agree; on Wayland specifically the
   `desktopFileName`↔`.desktop` match is what fixes the taskbar (the in-window corner icon comes from
   `setWindowIcon`).

**Test impact:** No existing test covers app-icon / desktop identity (this is startup wiring in
`pgtp_editor/main.py`, which is largely untested; there is no `tests/test_main.py`). New case(s) needed: a
small unit test (e.g. `tests/test_main_icon.py`, or a new `tests/ui/` test) that, under
`QT_QPA_PLATFORM=offscreen`, invokes the startup wiring and asserts (a)
`QApplication.instance().windowIcon()` is non-null (`isNull()` is False) and (b)
`QApplication.applicationName()` / `QApplication.desktopFileName()` are set to the expected values. If the
icon-setting logic is factored into a helper (e.g. `apply_app_identity(app)` in `main.py`), test that
helper directly to avoid running the full event loop. Also add a packaging sanity check that the icon
resource is included in `package-data` (can be asserted by importing it via `importlib.resources`).

**Spec impact:** none found — `CONSOLIDATED_SPEC.md` describes the PySide6/Qt6 desktop app (§ around line
55) but has no section on application-icon / desktop-file / branding behavior, so the current absence is an
omission rather than a documented decision. After the fix lands, flag `spec-maintainer` to add a short
note recording the app-icon + `.desktop`/`desktopFileName` identity convention (icon resource location,
`setDesktopFileName("pgtp-editor")`, and the KDE taskbar association) so it isn't accidentally dropped in
future packaging changes.

---

## BUG-010: Dark-theme View-menu checkable indicators are invisible (dark box on dark menu)
**Status:** RESOLVED (cb9fdc8) — resolved via QDarkStyleSheet adoption (user's chosen direction), not the entry's option A/B
**Reported:** 2026-08-01
**Report (verbatim):** "in dark theme the checkbox borders are dark so it's invisible"

**Root cause:** `pgtp_editor/ui/theme.py`, `dark_palette()` / `apply_theme()` (lines 63-110). The
theme is **palette-only under the Fusion style** — there is no QSS anywhere in the app that styles menu
checkable indicators (`grep` for `setStyleSheet` in `ui/main_window.py` finds only an unrelated
`_debug_label` at line 348; `theme.py` sets no stylesheet). The View menu's checkable actions are
plain `QAction.setCheckable(True)` items built in `MainWindow._build_view_menu()`
(`pgtp_editor/ui/main_window.py:1952-2006`: "Project Tree", "Properties Panel", "Find table reference",
"Audit/Problems Panel", "Raw XML Panel", "Light Theme"). Under Fusion, a checkable menu action that has
**no icon** is drawn as a small framed checkbox-style indicator; Fusion derives that indicator's frame
outline from the `Window`/`Button` palette roles darkened (the Fusion `CE_MenuItem` /
`PE_IndicatorCheckBox` path outlines with `palette.window()/button()` darkened toward black). In the
dark palette `Window` is `#2B2B2B` and `Button` is `#3A3A3A`, so the darkened outline is essentially
black on the ~`#2B2B2B` dark menu background → the empty (unchecked) indicator box is invisible. The
dark palette sets no role (e.g. `Mid`/`Dark`/`Light`) that would push the indicator outline lighter, so
there is currently no lever to make it visible. Light theme is unaffected because its `Window`/`Button`
are light, so the darkened outline reads fine. This is purely a dark-theme rendering gap, not a bug in
the menu/toggle logic (the actions themselves are correct and their checked/unchecked state is honest —
see BUG-007).

**Proposed fix:** Give the dark theme a visible menu-indicator outline. Two viable shapes; prefer (A)
for surgical scope, keep it inside `theme.py` so `apply_theme()` stays the single mutation point:

- **(A) Targeted QSS applied alongside the dark palette (recommended).** In
  `pgtp_editor/ui/theme.py`, extend `apply_theme(app, light)` so that after `app.setPalette(...)` it
  also sets an app-level stylesheet that styles the menu indicator for the dark case and clears it for
  light:
  - Add a small module constant, e.g. `_DARK_MENU_QSS`, styling
    `QMenu::indicator { border: 1px solid #8A8A8A; }` (a mid-grey border that reads on `#2B2B2B`),
    plus `QMenu::indicator:checked` giving a visible checked fill/glyph background (e.g.
    `background-color: #6CB6FF;` — reuse the dark `Link`/highlight-ish blue already in the palette so
    checked vs. unchecked is unambiguous), and matching `:unchecked` with a transparent/base fill so the
    box outline shows. Keep radius/size defaults; do NOT restyle text/background colors of the menu
    (leave those to the palette) to avoid regressing the rest of the dark theme.
  - In `apply_theme`: `app.setStyleSheet(_DARK_MENU_QSS if not light else "")`. Gotcha: use
    `app.setStyleSheet` (application-global) so it covers every `QMenu`, and **always assign both
    branches** (set empty string in light mode) so toggling light↔dark doesn't leave stale dark QSS
    applied — mirror the symmetric-by-construction intent of the BUG-004 palette code. Second gotcha: a
    non-empty app stylesheet can suppress some Fusion palette rendering; keep the QSS scoped to
    `QMenu::indicator` (and `QMenu::indicator` sub-states) only — do not add bare `QMenu {...}` rules.
  - Note `apply_theme` is called from `MainWindow._restore_theme` (main_window.py:812) and
    `_on_light_theme_toggled` (main_window.py:842); both go through `apply_theme`, so no caller changes
    are needed — the fix lands centrally.

- **(B) Palette-only alternative (no QSS).** If the maintainer wants to keep the theme strictly
  palette-driven, set the Fusion-consulted frame roles in `dark_palette()` to lighter values —
  `palette.setColor(role.Mid, QColor(0x5A,0x5A,0x5A))`, `role.Dark`, and `role.Light` — tuned so the
  indicator outline lifts off the background. This is harder to get pixel-right across Fusion's many
  uses of those roles (they also affect frames/grooves elsewhere), so (A) is preferred; mention (B) only
  as fallback if the QSS approach regresses other menu rendering.

**Test impact:** Existing coverage: `tests/ui/test_theme.py` (pure `light_palette()`/`dark_palette()` +
`apply_theme` style/palette assertions) and `tests/ui/test_main_window_theme.py`. Extend
`tests/ui/test_theme.py` rather than adding a new file. New case(s):
(1) after `apply_theme(app, False)`, assert the app has a non-empty stylesheet that mentions
`QMenu::indicator` (and, if approach A, an explicit border color) — e.g.
`assert "QMenu::indicator" in app.stylesheet()`;
(2) after `apply_theme(app, True)`, assert the menu-indicator QSS is cleared
(`assert "QMenu::indicator" not in app.styleSheet()`), proving the light↔dark round-trip leaves no stale
dark QSS. Reuse the existing `_reset_app_palette` fixture and extend it to also save/restore
`app.styleSheet()` so the app-global stylesheet can't leak into later UI tests (important: several
`tests/ui/` tests assert default rendering). If approach B is chosen instead, add palette-role
assertions on `dark_palette()` (`Mid`/`Dark`/`Light` lighter than `Window`) rather than stylesheet
assertions.

**Spec impact:** Diverges in spirit from `CONSOLIDATED_SPEC.md` §Theme (`ui/theme.py`, around line 337)
which currently describes the theme as **two explicit palettes under Fusion** with no mention of any
stylesheet. If approach (A) is taken, the theme is no longer strictly palette-only, so flag
`spec-maintainer` after the fix lands to note that the dark theme additionally applies a minimal
`QMenu::indicator` stylesheet (and that it is cleared in light mode) so menu checkable indicators stay
visible on dark backgrounds. If approach (B) is taken, update the §Theme role list to include the
`Mid`/`Dark`/`Light` roles the dark palette now sets. Not a pre-existing intentional decision — the
invisible indicator is an unnoticed side effect of the BUG-004 dark-palette work, not a documented
choice.

---

## BUG-011: Database Check tab (XML→DB / DB→XML) stays open after the .pgtp project is closed
**Status:** RESOLVED (28203d8)
**Reported:** 2026-08-01
**Report (verbatim):** "when I close a pgpt file the database check windows (both xml->db and db->xml) should also close"

**Root cause:** `pgtp_editor/ui/main_window.py`, `MainWindow._close_project()` (starts line 1790). The
Database Check surface is NOT a separate window/dialog — both directions share a single hidden tab in the
left tab bar. `self.db_check_panel = DbCheckPanel()` is added to `self.left_tabs` at `db_check_tab_index`
(lines 243-247), created hidden and revealed by `_reveal_db_check_tab()` (line 2385:
`self.left_tabs.setTabVisible(self.db_check_tab_index, True)`). A run via `_run_db_check(direction)`
(line 2400) populates the panel and caches three project-tied attributes on the window:
`_last_db_check_direction` (lines 203, 2433), `_last_db_schema` (lines 207, 2434), and
`_last_db_summary` (line 208). `_close_project()` clears the editor, project tree, `_current_project`,
`_current_project_path`, and `_history` (lines 1816-1827) but never touches the db-check tab or its
caches. So after closing the file the Database Check tab stays visible showing stale results from the
now-closed project, and the caches still point at the old project — `_refresh_db_check_if_open()`
(line 1550) and the rename re-run at line 2539 would then operate on the closed project's stale state.

**Proposed fix:** In `MainWindow._close_project()`, on the committed-close path only — after
`self._set_dirty(False)` (line 1827) and before the `_log.info("file: close ...")` at line 1828, which
is below the `cancel`/cancelled-save early `return`s at lines 1805-1814 — hide the tab and reset the
caches:
- `self.left_tabs.setTabVisible(self.db_check_tab_index, False)` — mirror the hide used at construction
  (line 247) and by other project-tied left-tabs closed elsewhere (`table_refs_tab_index` at line 1083,
  `ddl_browser_tab_index` at line 2511). Hiding the tab is the established "close this project-tied
  left-tab surface" gesture; this is the pattern to reuse, not a new window-close path.
- Reset the three caches so a later reparse/rename can't act on the closed project:
  `self._last_db_check_direction = None`, `self._last_db_schema = None`, `self._last_db_summary = None`
  (matching their initial values at lines 203-208).
- Panel contents: `DbCheckPanel` (`pgtp_editor/ui/db_check_panel.py`) exposes
  `set_result(direction, table_checks, connection_summary)` (line 88) but no `clear()`. Hiding the tab
  plus nulling the caches is sufficient for the reported symptom, so do NOT reach into the panel's
  widgets from the window; if a clean-slate is wanted, add a small `clear()` method to `DbCheckPanel`
  and call it. Gotchas: place the teardown strictly on the committed-close path so cancelling a close
  does not wipe the still-open project's tab; and leave `_revert_project()` (line 1830) alone — it keeps
  the project loaded and should NOT hide the tab.

**Test impact:** `tests/ui/test_db_check_wiring.py` already drives `_run_db_check` synchronously via a
`run_async` stand-in (`test_run_db_check_xml_to_db_populates_and_reveals`, line 77, asserts
`window.left_tabs.isTabVisible(window.db_check_tab_index)` and `window._last_db_check_direction`). Add a
case there (or in `tests/ui/test_main_window.py` beside the existing close-project tests): run a db check
so the tab is visible, call `window._close_project(confirm="discard")` (or on a clean buffer), then
assert `not window.left_tabs.isTabVisible(window.db_check_tab_index)` and that
`_last_db_check_direction` / `_last_db_schema` / `_last_db_summary` are all `None`. Add a guard case that
a CANCELLED close (`confirm="cancel"` on a dirty buffer) leaves the tab visible and caches intact.
Monkeypatch the close-confirm prompt per the modal-call policy.

**Spec impact:** none found — the Database Check section of `docs/superpowers/CONSOLIDATED_SPEC.md` does
not specify the db-check tab as intentionally persistent across project close, so this is a plain
omission rather than an intentional decision being overridden. If the resolver adds a spec line stating
the tab is torn down on project close, flag it for spec-maintainer after the fix lands.

---

## BUG-012: test_run_async_delivers_result_via_real_pool flakes under pytest-xdist `-n 10` (connect-after-emit race in the test itself)
**Status:** RESOLVED (cb9fdc8)
**Reported:** 2026-08-01
**Report (verbatim):** "tests/ui/test_async_task.py::test_run_async_delivers_result_via_real_pool is flaky under parallel pytest (-n 10 via pytest-xdist): it fails intermittently in full-suite parallel runs but passes serially and in isolation. Reproduced on the committed baseline (commit c19d0b2) with `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q -n 10` — so it is NOT caused by any working-tree change. The same parallel runs occasionally also fail tests/ui/test_main_window.py caption-mode selection tests (e.g. test_enter_caption_mode_for_field_selects_row, empty selectedRows() under load) — possibly the same load-dependent class. The failing set varies run to run. This flake was also noted in older docs/TEST_LOG.md entries as a pre-existing single-run flake even in serial full-suite runs. Context: the project just adopted `-n 10` as the standard commit-time gate, so a load-sensitive test now fails gates regularly and needs a real fix (deflake the test properly — e.g. generous qtbot.waitUntil deadlines instead of tight timing assumptions, or serializing the real-threadpool test — NOT blind retries)."

**Root cause:** `tests/ui/test_async_task.py::test_run_async_delivers_result_via_real_pool`
(lines 34–42) — the test's own structure, NOT the production code in
`pgtp_editor/ui/async_task.py` (which is correct: `run_async` connects `on_result` and the
`_INFLIGHT` release slot BEFORE `pool.start(task)` at `async_task.py:90–104`, so the production
delivery path has no race).

The test does:

```python
task = run_async(lambda: 21 * 2, on_result=results.append)   # line 39: pool.start() already ran
with qtbot.waitSignal(task.signals.result, timeout=3000):    # line 40: spy connects HERE
    pass
```

`qtbot.waitSignal(...)` connects its spy slot when the `SignalBlocker` is constructed — i.e.
**after** `run_async()` has already started the worker on the global `QThreadPool`. The worker's
callable is trivial (`21 * 2`), so the worker frequently finishes and emits
`task.signals.result` on the worker thread within microseconds of `start()`. Qt signal emission
delivers only to connections that exist at emit time — a queued connection made *after* the emit
receives nothing. So whenever the pytest process's main thread is descheduled between line 39
returning and line 40 connecting the spy (rare when the machine is idle, routine when `-n 10`
xdist floods all cores), the worker emits into a connection set that does not yet include the
spy: `results.append` (connected inside `run_async`, before start) still fires — but the spy
never does, and `waitSignal` times out after 3000 ms and raises `TimeoutError` (pytest-qt default
`raising=True`). That exactly matches every observed symptom: passes serially/in isolation,
fails intermittently under `-n 10` load, was already noted as an occasional single-run flake in
older `docs/TEST_LOG.md` entries (the race window exists even without xdist, just far smaller).

**Reproduced deterministically** during triage with a scratch script that mimics the test but
inserts a 50 ms sleep between `run_async()` returning and the spy connecting (simulating the GUI
thread being descheduled under load): `results == [42]` (before-start connection delivered) while
the after-emit spy connection received nothing — i.e. `waitSignal` would time out. One clean
full-suite `-n 10` run during triage also confirmed the failure is intermittent, not constant.

The sibling tests in the same file are already race-free by construction:
`test_run_async_delivers_even_without_caller_reference` (line 45) and
`test_inflight_set_is_empty_after_delivery` (line 57) use
`qtbot.waitUntil(lambda: results == [...], timeout=3000)`, which polls a condition fed by the
connection `run_async` itself made before `start()` — immune to this race by design.

**Proposed fix:** In `tests/ui/test_async_task.py`, rewrite
`test_run_async_delivers_result_via_real_pool` (lines 34–42) to stop connecting anything to the
task's signals after the pool has started — use the same `waitUntil` pattern its two sibling
real-pool tests already use:

```python
def test_run_async_delivers_result_via_real_pool(qtbot):
    results = []
    run_async(lambda: 21 * 2, on_result=results.append)
    qtbot.waitUntil(lambda: results == [42], timeout=5000)
```

Details and gotchas:
- `qtbot.waitUntil` spins the event loop while polling, so the queued `results.append` delivery
  (whose connection predates `pool.start`) is processed; there is no window in which anything can
  be missed. A generous 5000 ms deadline is fine — it is an upper bound, not a sleep; the test
  still completes in milliseconds normally.
- Do NOT keep the `with qtbot.waitSignal(task.signals.result, ...)` form, and do not "fix" it by
  constructing the blocker before calling `run_async` — the signal lives on the `_Task` that
  `run_async` creates, so the spy cannot be connected before the pool starts without
  restructuring (e.g. building a `_Task` manually, connecting, then `pool.start(task)` yourself),
  which would no longer exercise `run_async` end to end. `waitUntil` on `results` is both simpler
  and exercises the real production delivery path (`on_result` connected inside `run_async`).
- Holding the returned `task` reference is no longer needed for GC safety — `_INFLIGHT`
  (`async_task.py:49, 102`) retains the task until delivery, and
  `test_run_async_delivers_even_without_caller_reference` explicitly proves that. Dropping the
  variable also removes the now-obsolete comment at lines 36–38; update the module docstring
  (lines 5–8: "waiting on the signal and holding the returned task") to match the new shape.
- No production code change: `pgtp_editor/ui/async_task.py` is correct as-is. Do not add retries,
  and do not serialize/isolate the test via xdist grouping — the fix above removes the race
  outright, which is strictly better than scheduling around it.

Secondary observation — the caption-mode failures mentioned in the report
(`tests/ui/test_main_window.py::test_enter_caption_mode_for_field_selects_row`, empty
`selectedRows()`) are explicitly NOT root-caused by this entry, and I could not find the code
path that would make them load-sensitive: that test's entire path is synchronous with no event
processing between action and assertion (`MainWindow.enter_caption_mode_for_field`
(`main_window.py:2210`) → `_enter_caption_mode` (line 2171, synchronous `scan_captions` +
`load_entries`) → `CaptionManagementPanel.filter_to_field` → `_select_first_visible_row`
(`caption_management_panel.py:948–955`, plain `QSortFilterProxyModel` predicate +
`QTableView.selectRow`) — no timers, no threadpool, no queued signals). A purely synchronous test
cannot flake on thread timing, so it is most likely a different failure class: candidates are an
xdist **worker crash** (xdist reports whatever tests the crashed worker was running as failures,
producing a varying failing set — check the failure output for "worker gwN crashed" vs. a real
assertion traceback) or cross-test in-process interference from whatever else that worker ran
first (ordering varies per run under xdist). Recommendation for the resolver: fix the async test
per above, then re-run the `-n 10` full suite several times; if caption-mode failures persist,
capture the exact failure output (assertion vs. worker crash, plus `PYTEST_XDIST_WORKER` test
schedule) and file a separate bug report with it rather than guessing here.

**Test impact:** The fix IS a test change — `tests/ui/test_async_task.py` only (rewrite one test,
touch the module docstring/comments as noted). No production code changes, so no other test files
are affected; `pgtp_editor/ui/async_task.py`'s behavior is already fully covered by the other
four tests in the same file, which need no changes. After the fix, validate by running the full
suite with `-n 10` several times (the triage repro command:
`QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q -n 10`) and confirm this test no longer
appears in any failing set.

**Spec impact:** none — `docs/superpowers/CONSOLIDATED_SPEC.md` does not document test-suite
timing strategy; `async_task.py`'s documented behavior is unchanged. (The module docstring inside
`tests/ui/test_async_task.py` describing the waitSignal approach should be updated as part of the
fix, but that is a test file, not the spec.)

---

## BUG-013: Theme toggle hangs the UI for ~1s+ on each switch
**Status:** RESOLVED (1c2a6b6, 06f8859) — resolved via proposed option (C): two-step theme change (app
colors flip instantly, document rehighlight follows) plus batching the rehighlight sweep so large
documents don't freeze the UI
**Reported:** 2026-08-01
**Report (verbatim):** "the theme change is very slow and hangs the app for a second or more"

**Root cause:** `pgtp_editor/ui/theme.py`, `apply_theme(app, light)` (lines 121-136). The freeze is the
combined synchronous cost of the three app-wide mutations in this function plus the per-editor rehighlight
they trigger, all on the UI thread:

1. **App-wide QSS re-parse + full re-polish (dominant, repeatable cost).** `app.setStyleSheet(_dark_stylesheet())`
   (line 136) hands Qt the ~54 KB QDarkStyleSheet string. Setting a stylesheet on the `QApplication` forces
   Qt to re-parse the entire QSS and then unpolish/re-polish **every widget in the whole application tree**
   synchronously. On a populated main window (tree view, properties dock, two code editors, toolbar, menus,
   docks) this is the O(widgets) × O(QSS-rules) step that stalls the event loop. This happens on *every*
   toggle, in both directions (dark→ applies the 54 KB sheet; light→ sets `""`, which still triggers a
   full app-wide re-polish to strip the old sheet). The QSS *text* itself is already cached
   (`_dark_qss_cache` in `_dark_stylesheet()`, lines 100-118 — verified: first `qdarkstyle.load_stylesheet`
   is ~107 ms, subsequent calls ~0.3 ms), so re-reading from disk is **not** the cause; the cost is Qt
   applying the sheet, not building the string.
2. **`app.setPalette(...)` (line 135)** also emits `ApplicationPaletteChange` to every widget — a second
   full-tree walk.
3. **Two full-document rehighlights.** The palette change delivers `ApplicationPaletteChange` to **both**
   `XmlEditor` instances (`center_stage.xml_editor` and `center_stage.xsd_editor`, created at
   `pgtp_editor/ui/center_stage.py:54,66`). Each editor's `changeEvent`
   (`pgtp_editor/ui/xml_editor.py:781-792`) calls `apply_theme_colors(light)`, which runs
   `self._highlighter.rehighlight()` over the **entire document** (`xml_editor.py:771`) plus rebuilds all
   extra-selection layers. For a large `.pgtp` XML document this whole-document reformat is itself a
   noticeable synchronous cost, paid twice, on every toggle. `_refresh_toolbar_icons()`
   (`main_window.py:839,867`) re-tints toolbar icons on top of that but is comparatively minor.

**Proposed fix:** Reduce the per-toggle work; the string cache is fine, the *application* of it is the
problem. Concrete options for the resolver, in preference order:

- **(A) Stop swapping the whole 54 KB app stylesheet on every toggle; scope the dark-only styling to the
  small piece that actually needs QSS.** BUG-010 adopted the full QDarkStyleSheet only to fix dark
  checkable-menu indicators (see that entry and `_dark_stylesheet()`'s docstring, `theme.py:105-118`). If
  the sole widget class that Fusion+palette renders wrong in dark mode is the menu indicator, replace the
  54 KB app-wide sheet with a tiny targeted `QMenu::indicator` QSS (a few hundred bytes) applied via
  `app.setStyleSheet(...)`. A tiny sheet still forces a re-polish but parses instantly and matches far
  fewer widgets. **This directly overlaps BUG-010's proposed fix — coordinate: BUG-010 and BUG-013 should
  be resolved together, since both rewrite the `app.setStyleSheet` line in `apply_theme()`. The ideal
  combined outcome is one small `QMenu::indicator` sheet that satisfies BUG-010 without the multi-hundred-ms
  cost of the full QDarkStyleSheet.** If the resolver decides the full QDarkStyleSheet is genuinely needed
  for broader dark-mode fidelity, this option is off the table and (B)/(C) apply instead.
- **(B) Avoid the redundant re-polish when the theme is unchanged.** Track the currently-applied theme
  (e.g. a module-level `_current_light: bool | None` in `theme.py`, or a flag on the app) and early-return
  from `apply_theme` when `light` already matches the applied state, so `_restore_theme` at startup and any
  redundant toggle don't pay the cost. (Guard against the first call where nothing is applied yet.)
- **(C) Cut the double whole-document rehighlight.** The two `XmlEditor`s each rehighlight the full
  document from `changeEvent`. Consider limiting rehighlight to the visible viewport, or skipping
  rehighlight for the editor whose tab is not currently visible and deferring it until that tab is shown.
  Gotcha: `apply_theme_colors` must still run so the editor's cached colors update; only the
  `self._highlighter.rehighlight()` call (xml_editor.py:771) is the expensive part that can be deferred.
  Preserve the `_applying_theme` guard (`xml_editor.py:769-773`) exactly — it is what stops a theme toggle
  from spuriously dirtying a clean document (`is_applying_theme()` is consulted in
  `main_window.py:519,976`); do not regress that (spec §note at CONSOLIDATED_SPEC.md:313-316).

Whatever combination is chosen, keep `apply_theme()` as the single mutation point (per its docstring and
CONSOLIDATED_SPEC §Theme, lines 342-352) and keep the light↔dark round-trip leaving no stale QSS behind.

**Test impact:** Existing coverage — `tests/ui/test_theme.py` (pure `light_palette()`/`dark_palette()`/
`apply_theme()` unit tests, style/palette/stylesheet assertions), `tests/ui/test_main_window_theme.py`
(toggle wiring), `tests/ui/test_xml_editor_theme.py` (`apply_theme_colors`/`changeEvent`/rehighlight
behavior). Extend, don't duplicate. New cases needed depending on the chosen fix: if (A), assert the dark
stylesheet is now small/targeted (contains `QMenu::indicator`, does not contain full-QDarkStyleSheet
markers) and light clears it — this must be reconciled with BUG-010's proposed assertions so the two don't
contradict. If (B), assert a second `apply_theme(app, light)` with the same `light` is a no-op (e.g. does
not re-emit / does not re-set the stylesheet) and that startup `_restore_theme` still applies exactly once.
If (C), assert the non-visible editor defers its rehighlight and that both editors end in the correct
color state after their tab is shown, and re-assert the clean-document-stays-clean invariant across a
toggle for both editors.

**Spec impact:** The full-QDarkStyleSheet dark QSS is an intentional, spec-documented decision
(CONSOLIDATED_SPEC.md §7 dependency table line 165: "Dark theme QSS | QDarkStyleSheet via `qdarkstyle` …",
and §Theme lines 342-352). If the fix takes option (A) and replaces the full QDarkStyleSheet with a small
targeted menu-indicator sheet, that diverges from the documented dependency/behavior — flag for
`spec-maintainer` after the fix lands (and coordinate with BUG-010, which touches the same spec area).
If only (B)/(C) are taken (full QDarkStyleSheet retained), no spec change is needed.

---
## BUG-014: Unparented `QTimer.singleShot` in `apply_theme_colors` fires on a deleted `XmlEditor` — 7 Find-All tests fail with "Internal C++ object (XmlEditor) already deleted"

**Status:** RESOLVED (5b84144) — kickoff switched to a `QTimer(self)`-parented single-shot timer (`_theme_kickoff_timer`); ~QWidget cancels a pending tick. Regression test `test_deferred_theme_rehighlight_does_not_fire_on_deleted_editor`; full suite 1809 passed.
**Reported:** 2026-08-01
**Report (verbatim):** "7 tests fail in `tests/ui/test_main_window.py`, all in the Find-All group:
`test_find_all_restart_does_not_leak_a_second_timer`,
`test_find_all_populates_audit_panel_with_line_items_and_summary`,
`test_find_all_clears_only_prior_find_entries`, `test_clicking_find_result_navigates_editor_to_line`,
`test_clicking_summary_line_is_a_noop`, `test_find_all_via_menu_populates_audit_panel`,
`test_find_all_streaming_completes_and_reports_final_count`. Each fails with pytest-qt's `CALL ERROR:
Exceptions caught in Qt event loop`, repeated many times, always the same traceback:
`File "pgtp_editor/ui/xml_editor.py", line 658, in _rehighlight_for_theme / block =
self.firstVisibleBlock() / RuntimeError: libshiboken: Internal C++ object (XmlEditor) already deleted.`
Reproduce: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q -n 10`. A serial run dies instead
with a pytest-timeout 60s `Timeout` in the same code path, in `tests/ui/conftest.py`'s
`_reset_app_style_and_palette` teardown at `qapp.setStyle(...)`. Verified pre-existing at clean HEAD
(687c4b1): 7 failed / 1717 passed with the DDL work stashed, same 7 with it applied — not caused by the
in-flight DDL Explorer work."

**Root cause:** Confirmed as reported, with the scheduling site pinned down more precisely.

`pgtp_editor/ui/xml_editor.py:629-631` (end of `XmlEditor.apply_theme_colors`, added by the BUG-013 fix
`1c2a6b6`):

```python
if not self._theme_rehighlight_pending:
    self._theme_rehighlight_pending = True
    QTimer.singleShot(0, self._rehighlight_for_theme)
```

`QTimer.singleShot(msec, callable)` creates an **unparented, internally-owned** single-shot timer held by
Qt's global timer machinery; the bound method `self._rehighlight_for_theme` keeps only the *Python*
wrapper alive, which does nothing to keep the underlying C++ `XmlEditor` alive and does nothing to cancel
the timer when the C++ object is destroyed. This is exactly the parenting that
`self._theme_sweep_timer = QTimer(self)` (`xml_editor.py:673-677`) *does* have: that timer is a child of
the editor, so `~QWidget` destroys it and its pending 0ms tick with it. The `singleShot` escapes that
lifetime binding. Same escape as `main_window.py:1339`'s `self._find_all_timer = QTimer(self)` avoids by
parenting.

Firing path, end to end:

1. Every `MainWindow()` construction runs `_restore_theme` (`main_window.py:446` → `831-839`), which calls
   `apply_theme(QApplication.instance(), light)` **unconditionally** (BUG-004). That posts
   `ApplicationPaletteChange` to every live widget.
2. Each live `XmlEditor` — there are two per window, `center_stage.xml_editor` and
   `center_stage.xsd_editor` (`pgtp_editor/ui/center_stage.py:54,66`) — handles it in `changeEvent`
   (`xml_editor.py:696-707`) and calls `apply_theme_colors`, which schedules the `singleShot`.
3. The overwhelming majority of `tests/ui` tests never spin a Qt event loop, so the 0ms singleShot never
   gets a chance to fire during the test. `qtbot`'s teardown deletes the `MainWindow` (and with it the C++
   `XmlEditor`s). The queued singleShot survives — it is not a child of anything that was deleted.
4. The next test that *does* spin the event loop drains that queue. `_rehighlight_for_theme`
   (`xml_editor.py:639`) runs against a `self` whose C++ side is gone, and the first attribute touch,
   `self.firstVisibleBlock()` at line 658, raises `RuntimeError: Internal C++ object (XmlEditor) already
   deleted`. pytest-qt attributes any exception raised inside the event loop to whichever test's loop is
   spinning, so the exception is charged to the *innocent* test.

**The Find-All tests are victims, not the cause — confirmed by reading the tests.** The 7 failing tests
are precisely the Find-All tests that call `qtbot.waitUntil(..., timeout=5000)`
(`tests/ui/test_main_window.py:377, 398, 417, 449, 469, 498, 562`) or otherwise spin the loop — i.e. the
only tests in the file that give the stale queue a chance to drain. The Find-All tests in the same group
that drive the streaming timer *manually* without spinning the loop —
`test_find_all_stop_keeps_partial_results` (`:511`, calls `window._find_all_timer.stop()` then
`window._find_all_step()` directly) and `test_find_all_live_count_status_after_a_batch` (`:538`, same
pattern) — **pass**. That split is the fingerprint of a victim, not a culprit: nothing in
`_populate_find_all_results` / `_find_all_step` / `_finish_find_all` (`main_window.py:1319-1394`) touches
theming or schedules a rehighlight. Under `-n 10` the exact victim set is a scheduling artifact of which
worker happens to run a loop-spinning test after a loop-less one; it is stable here only because the
Find-All tests are the loop-spinning cluster in this file.

**`tests/ui/conftest.py`'s autouse `_reset_app_style_and_palette` is a contributor but not the bug, and
must not be weakened.** Its `qapp.setStyle(original_style)` / `setPalette(original_palette)` teardown does
deliver palette/style change events, and any `XmlEditor` still alive at that moment schedules another
`singleShot` — same leak, one more source. But the fixture is legitimate and load-bearing (its docstring
explains it exists to stop BUG-004's app-global theme mutation leaking into `test_menus.py`); the leak is
production-side. Note also that fixture teardown ordering makes this a *secondary* source: the autouse
fixture is set up before `qtbot`, so it is finalized after `qtbot` has already deleted the test's widgets
— in a well-behaved test the editors are gone by then. The dominant source is step 1-3 above (construction
schedules, test never spins, teardown deletes).

**Serial-run 60s timeout at `qapp.setStyle(...)`:** same defect compounding, not a separate one. Serially
all tests share one process, so the queue of orphaned singleShots (plus, for editors that *are* alive,
their 0ms `_theme_sweep_timer` repeat ticks) grows monotonically; a `setStyle` re-polish inside a teardown
processes/queues that backlog and blows the 60s pytest-timeout. Treat as expected-to-resolve-with-the-fix
and re-verify serially after the fix rather than as an independent item.

**`_theme_sweep_tick` has the same class of exposure but is already protected**, because
`_theme_sweep_timer` is `QTimer(self)` (parented, `xml_editor.py:674`) — destroyed with the editor, so its
`timeout` can never fire post-mortem. It is the *only* other deferred callback added by the BUG-013
commits (`1c2a6b6`, `06f8859`). Verified: `QTimer.singleShot` appears exactly once in the whole
`pgtp_editor/` package — `xml_editor.py:631`. Every other `QTimer` in production is parented
(`main_window.py:397` `_snapshot_timer = QTimer(self)`, `main_window.py:1339` `_find_all_timer =
QTimer(self)`, `xml_editor.py:674` `_theme_sweep_timer = QTimer(self)`). So the codebase's **existing,
consistent convention is a parented `QTimer`**, and line 631 is the single deviation.

**Proposed fix:** Replace the unparented `singleShot` with a parented single-shot `QTimer`, matching the
convention already used three times in this codebase (including twice in the same method chain). In
`pgtp_editor/ui/xml_editor.py`:

1. In `XmlEditor.__init__`, next to the existing BUG-013 state at lines ~500-507, add
   `self._theme_rehighlight_timer: QTimer | None = None` alongside `_theme_rehighlight_pending` /
   `_theme_sweep_timer` (created lazily on first use, exactly like `_theme_sweep_timer` is at
   `xml_editor.py:673-677` — keep the two consistent).
2. In `apply_theme_colors` (lines 629-631) replace the `QTimer.singleShot(0, ...)` call with:

   ```python
   if not self._theme_rehighlight_pending:
       self._theme_rehighlight_pending = True
       if self._theme_rehighlight_timer is None:
           self._theme_rehighlight_timer = QTimer(self)   # parented: dies with the editor
           self._theme_rehighlight_timer.setSingleShot(True)
           self._theme_rehighlight_timer.setInterval(0)
           self._theme_rehighlight_timer.timeout.connect(self._rehighlight_for_theme)
       self._theme_rehighlight_timer.start()
   ```

   Update the BUG-013 comment block above it (lines 622-628) to say why the timer is parented, so the next
   reader does not "simplify" it back into a `singleShot`.

Why this option over the alternatives (state the reason in the code comment):

- **Parented `QTimer` (chosen).** Zero-cost, matches `_theme_sweep_timer` five lines away and
  `_find_all_timer`; the timer is destroyed by `~QWidget` so the callback provably cannot run
  post-destruction. Also fixes the leak at the source rather than catching its symptom, which is what the
  serial-run timeout needs.
- **`shiboken6.isValid(self)` guard at the top of `_rehighlight_for_theme`.** Rejected as the primary fix:
  it silences the traceback but the orphaned timers still queue and still get drained, so the serial-run
  backlog/timeout is not addressed; and `shiboken6` is not currently imported anywhere in `pgtp_editor/`
  (only mentioned in a comment in `tests/ui/_menu_helpers.py:20`), so it would introduce a new
  convention. Acceptable only as belt-and-braces on top of (1), not instead of it.
- **`destroyed` disconnect.** More machinery than parenting, and parenting is what `destroyed`-based
  cleanup is trying to emulate. Reject.

Gotchas for the implementer:

- **Keep the coalescing semantics exactly as they are.** `_theme_rehighlight_pending` is cleared at the
  top of `_rehighlight_for_theme` (`xml_editor.py:654`); with a restartable single-shot timer, calling
  `.start()` on an already-running timer restarts it, but the `_theme_rehighlight_pending` guard means
  `.start()` is only reached when no rehighlight is queued — preserve that guard, don't drop it as
  "redundant."
- **Do not change the two-step behavior itself.** BUG-013's whole point is that step 1 (app coloring)
  paints before step 2 (document rehighlight); the deferral must stay a real deferral (interval 0,
  single-shot) — do not make it synchronous.
- **Preserve the `_applying_theme` guard** (`xml_editor.py:656-667`, `679-694`, consulted via
  `is_applying_theme()` at `main_window.py:519,976` and in `_rescan_structure` /
  `_refresh_code_region_selections`) untouched — regressing it would spuriously dirty clean documents on a
  theme toggle.
- **Do not "fix" this in `tests/ui/conftest.py`** by weakening or removing the autouse style/palette reset;
  see the analysis above.

**Test impact:** Existing coverage to extend, not duplicate:

- `tests/ui/test_xml_editor_theme.py` — the natural home. It already covers
  `apply_theme_colors` / `changeEvent` / the BUG-013 deferred rehighlight. Add: (a) a test that
  constructs an `XmlEditor` (or a `MainWindow`), triggers a theme apply so a rehighlight is queued, deletes
  the widget **without** spinning the loop (`widget.deleteLater()` + `sip`/shiboken-safe teardown, or
  `qtbot`-owned widget torn down explicitly), then spins the loop (`qtbot.wait(10)` /
  `QApplication.processEvents()`) and asserts **no exception reaches the event loop** — with the bug, this
  reproduces the `RuntimeError` directly and attributes it to the right test; (b) a structural assertion
  that the rehighlight timer is a child of the editor (`timer.parent() is editor`), which is what makes the
  behavior true by construction and guards against a regression back to `singleShot`.
- `tests/ui/test_main_window.py` — the 7 failing Find-All tests should simply go green again; they need
  **no changes**, and no new Find-All test should be added for this, since Find-All is not implicated.
  `test_find_all_restart_does_not_leak_a_second_timer` (`:550`) is about `_find_all_timer` identity across
  restarts (`main_window.py:1339` / `_cancel_find_all_timer`, `:1385`) — a genuinely different timer and a
  different concern; **do not** graft the theme-timer assertion onto it. Its structural sibling for the
  theme timer belongs in `tests/ui/test_xml_editor_theme.py` per (b) above.
- Verification runs the resolver should do: the reported repro `QT_QPA_PLATFORM=offscreen
  ./venv/bin/python -m pytest -q -n 10` (expect the 7 to go green) **and** a serial `QT_QPA_PLATFORM=offscreen
  ./venv/bin/python -m pytest -q` to confirm the 60s teardown timeout at `qapp.setStyle(...)` is gone. Use
  `./venv/bin/python` on this Linux box, not bare `python`.

**Spec impact:** None expected. The deferred two-step + batched-sweep theme rehighlight is BUG-013's
documented behavior (CONSOLIDATED_SPEC §Theme, and the clean-document-stays-clean note at
CONSOLIDATED_SPEC.md:313-316); this fix changes only the *ownership* of the timer that carries out step 2,
not any user-visible behavior or design decision, so nothing in the spec is contradicted. Nothing in
CONSOLIDATED_SPEC.md documents `singleShot` or timer parenting as an intentional choice — this is an
implementation defect, not a spec'd behavior. No `spec-maintainer` follow-up needed unless the resolver
deviates from the parented-timer plan above.

---

## BUG-015: Typing in the Raw XML editor is painfully slow — every keystroke/newline runs a full-document rescan synchronously
**Status:** RESOLVED (bd788f0) — user-verified. Debounced both `textChanged` handlers behind a parented single-shot timer, PLUS stopped `_update_matching_tag_highlight` (on `cursorPositionChanged`, which fires per keystroke since typing moves the caret) from rescanning when it finds the cache stale — without that second half the scan simply moved to the cursor path and the debounce would have achieved nothing. Guards: `setPlainText` rescans synchronously; `_toggle_fold` flushes first (NOT `_foldable_region_starting_at`, which the gutter paints through). Measured 216.1 → 2.0 ms/char plain typing on a 1 MB document. Residual unterminated-quote cost split out as BUG-016.
**Reported:** 2026-08-01
**Report (verbatim):** "xml editing is painfully slow. every time I hit enter, or I enter a character, it just waits and waits.... something should be separated from automatically running on each keystroke or new line... this is horrible"

**Root cause:** `pgtp_editor/ui/xml_editor.py`, in `XmlEditor.__init__` (lines 562-563), the editor wires **two** O(document) handlers directly to its own `textChanged` signal, both of which run **inline and synchronously on every keystroke** with no debounce:

- `self.textChanged.connect(self._rescan_structure)` (line 562). `_rescan_structure` (lines 721-731) calls `self.toPlainText()` — a full copy of the entire multi-MB document (line 728) — then `xml_structure.scan(self._spans_text)` (line 729), which regex-`finditer`s over the whole document (`xml_structure.py:51-57`, `_TAG_RE.finditer(text)`). On a ~37k-tag `.pgtp` file this is a full document copy + full-document regex pass **per character typed and per Enter**. This is exactly the same class of O(document) per-edit cost that BUG-003 and BUG-008 removed from the cursor-move / properties paths, but it remains on the text-*edit* path.
- `self.textChanged.connect(self._refresh_code_region_selections)` (line 563). `_refresh_code_region_selections` (lines 775-806) **also** calls `self.toPlainText()` (line 787, a second full-document copy) then `event_body_line_ranges(text)` (`event_body.py:121-147`, which walks the whole document via `_iter_handler_spans`), then builds one `QTextEdit.ExtraSelection` per line of every event-handler body and pushes them all via `_refresh_extra_selections` (line 806). Two full-document scans + a full selection rebuild, again per keystroke.

Both handlers already correctly skip the format-only theme-sweep case via the `self._applying_theme` guard (lines 726, 785), so that path is fine — the cost is purely on genuine user edits. The `QSyntaxHighlighter` (`XmlSyntaxHighlighter`, line 294) is **not** the culprit: Qt re-highlights only the changed block(s) on edit via `highlightBlock` (line 314), not the whole document. The `MainWindow._on_editor_text_changed` handler (`main_window.py:989-1002`) is also **not** the culprit: it is already debounced (`self._snapshot_timer.start()`) and otherwise only flips a dirty flag. The entire per-keystroke stall is the two un-debounced `XmlEditor` handlers above.

**Proposed fix:** Debounce both heavy `textChanged` handlers behind a short single-shot `QTimer` that restarts on each edit, so the full-document rescan + code-region rebuild run only once after the user pauses typing (~150-300 ms), instead of on every keystroke. Concretely, in `pgtp_editor/ui/xml_editor.py`:

1. In `__init__`, create a parented single-shot timer (follow the codebase convention — `QTimer(self)`, `setSingleShot(True)`, `setInterval(...)` — exactly like `MainWindow._snapshot_timer` at `main_window.py:397` and the `_theme_sweep_timer` at `xml_editor.py:674`; do **not** use unparented `QTimer.singleShot`, that was BUG-014). Name it e.g. `self._rescan_timer`.
2. Replace the two direct connections at lines 562-563 with a single slot connected to `textChanged` that (a) still respects the `_applying_theme` guard and simply `return`s during theme sweeps, and (b) otherwise calls `self._rescan_timer.start()`. Connect the timer's `timeout` to a new `_rescan_now` slot that calls `self._rescan_structure()` then `self._refresh_code_region_selections()` in that order (structure first, since `_refresh_code_region_selections` and downstream consumers rely on fresh `_spans`).
3. **Gotcha — cache staleness within the debounce window (critical).** `_spans` / `_spans_text` / `_spans_revision` will now be momentarily stale between an edit and the timer firing. Consumers already have a revision guard for exactly this: `_update_matching_tag_highlight` (line ~847) and `resolve_attribute_at` (line ~1025) both call `self._rescan_structure()` on demand when `self._spans_revision != self.document().revision()`. **Verify every reader of `_spans` either goes through that revision-guarded lazy rescan or tolerates a stale cache for a few hundred ms.** `_foldable_region_starting_at` (line 733) reads `self._spans` with no guard — folding a region the instant after an edit could use stale spans; either add the same revision-guarded lazy rescan there, or accept that folding right after an edit may lag by the debounce interval (folding is a deliberate user action, so a lazy rescan-on-demand is the safer choice).
4. **Gotcha — the initial-load path must stay synchronous.** The `__init__` tail (lines 589-591) calls `_rescan_structure()` / `_refresh_code_region_selections()` directly; keep those direct calls so a freshly loaded document has correct spans and code-region styling immediately (do not route the initial population through the debounce timer). Same for any programmatic `setPlainText` path (e.g. revert/undo apply) that expects spans to be fresh synchronously — if such a caller exists, have it call `_rescan_now()` (or the two methods) directly rather than waiting on the timer.
5. **Gotcha — flush on focus-out / before consumers that must be exact.** If any feature reads code-region selections or spans in a way that must never be stale (e.g. "Edit code..." via `event_body_start_line_at_cursor`, line 808, which independently re-derives from `toPlainText()` so is self-sufficient; double-check), consider flushing the pending timer (`if self._rescan_timer.isActive(): self._rescan_timer.stop(); self._rescan_now()`) at that entry point. `event_body_start_line_at_cursor` already recomputes from scratch, so it is safe as-is; this note is for any future consumer.

**Test impact:** Existing coverage: `tests/ui/test_xml_editor_nav_perf.py` is the closest sibling — its `test_cursor_navigation_does_not_rescan_document` / `_does_not_copy_document_text` (lines 56-147) count `xml_structure.scan` / `toPlainText` calls on the **cursor-move** path and must stay green (this fix does not touch cursor moves). Extend this file (do not duplicate) with the edit-path analogue: a test that types several characters in quick succession without spinning the debounce timer to fire, asserts `scan` is called **0 or 1** times (not once per keystroke), then fires the timer (or `qtbot.wait`s past the interval) and asserts exactly one rescan ran. Add a companion asserting `_spans` is refreshed after the timer fires and that the revision-guarded lazy path in `_update_matching_tag_highlight` still returns correct results *during* the stale window (cursor move between edit and timer-fire must not show a wrong matching-tag highlight). `tests/ui/test_xml_editor.py` (folding, structure) and `tests/ui/test_xml_editor_annotate.py` / `test_xml_editor_add_attribute.py` (which mutate text and then read spans/selections) may need a `_rescan_now()`/timer-flush call inserted after their programmatic edits if they currently rely on spans being fresh synchronously post-`textChanged`; audit those for the stale-cache assumption when implementing. The structural test (timer is `QTimer(self)`, single-shot, parented to the editor — guarding against a regression to unparented `singleShot`, cf. BUG-014) belongs alongside the perf test.

**Spec impact:** Diverges from CONSOLIDATED_SPEC §"Lenient scanner"/"Folding" (CONSOLIDATED_SPEC.md:392-404), which currently documents folding as "driven by `scan()` re-run on `textChanged`" (line 401) and the dirty-tracking/history debounce at :342 — i.e. the spec presently describes the rescan as running *on* `textChanged`, synchronously. After the fix it runs on a debounced timer keyed off `textChanged`. Flag for `spec-maintainer` after the fix lands so §Folding/§Scanner note the debounce (mirroring the existing "`textChanged` is debounced (~400 ms QTimer)" wording already used for the snapshot history at :342 and the auto-parse timer at :599-600). Do not edit the spec as part of this fix.

---

## BUG-016: Every parity-flipping `"` keystroke in the Raw XML editor re-highlights the whole document (unbounded block-state cascade)
**Status:** RESOLVED (77e12d4) — user-verified. Verified first that BUG-015's debounce had NOT already addressed it (one `"` still cost 5,972 `highlightBlock` calls / 45.5 ms — a separate mechanism). Replaced the odd-quote-parity rule with a tag-aware four-state machine (`_end_state`, `_STATE_CHARS_RE`): quotes delimit only inside a tag, so quotes/apostrophes in text content (PHP event-handler bodies) never change state. Plus the `<` resync rule that actually bounds the cascade — tag-awareness alone was confirmed insufficient for an unterminated in-tag quote. Formatting regexes untouched; both pre-existing multi-line-attribute tests pass unmodified. 45.5 → 2.3 ms/char, 5,972 → 1 block. Spec §8 + two §28 ledger rows.
**Reported:** 2026-08-01
**Report (verbatim):** "Typing inside an unterminated/unclosed double quote in the Raw XML editor is still slow on large documents — about 123 ms per keystroke on a ~1 MB / 21,000-line .pgtp, versus ~2 ms/char for plain typing. Discovered while fixing BUG-015 (which debounced the O(document) structure rescan and code-region rebuild; that fix is in place and verified, taking plain typing from 216 ms/char to 2.0 ms/char). This residual is a DIFFERENT root cause and was explicitly mis-attributed in BUG-015's triage, which claimed 'The QSyntaxHighlighter is NOT the culprit: Qt re-highlights only the changed block(s) on edit'. Profiling after the BUG-015 fix shows otherwise: XmlSyntaxHighlighter.highlightBlock ran 41,927 times for 25 keystrokes (~1,677 blocks re-highlighted per character), dominating the remaining profile (cumtime 0.87s of a ~1.0s run), with 260,616 setFormat calls and 155,732 regex finditer calls. [...] Hypothesis to verify: the highlighter tracks an unterminated-quote/string state across blocks via setCurrentBlockState/previousBlockState [...] Investigate whether the cascade is genuinely required for correct XML highlighting [...] and whether the cross-block state can be bounded [...] Assess the visual-correctness risk of any change to the block-state semantics and note which existing tests cover multi-line attribute values and string highlighting."

**Root cause:** Confirmed — the report's hypothesis is correct, and the mechanism is now measured, not assumed.

`pgtp_editor/ui/xml_editor.py:314-341`, `XmlSyntaxHighlighter.highlightBlock` + the module-level helper
`_has_unterminated_quote` (`:340-341`). The cross-block state is decided by a **pure double-quote parity
count over the line**:

```python
def _has_unterminated_quote(text: str, start: int) -> bool:
    return text.count('"', start) % 2 == 1
```

`highlightBlock` sets `STATE_IN_UNCLOSED_STRING` (=1, `:74`) whenever that parity is odd (`:334-337`), and
when the *previous* block carried that state it consumes text up to the next `"` as string, re-setting the
state if none is found (`:316-323`).

Why that is O(document) per keystroke: Qt's `QSyntaxHighlighterPrivate::reformatBlocks` keeps a
`forceHighlightOfNextBlock` flag and continues past the edited block **for as long as each block's
`userState()` differs from what it was before**. With parity semantics, flipping the parity of one line
flips the computed state of *every* following line (a line with zero quotes that starts in state 1 stays in
state 1, where it previously was 0; a line with two quotes starting in state 1 ends in state 1 as well —
parity never re-synchronises). So one `"` keystroke cascades to EOF, and typing the closing `"` cascades to
EOF a second time.

Measured on this repo (synthetic 12,000-block document, `QT_QPA_PLATFORM=offscreen`, `venv/bin/python`,
`app.processEvents()` per char, `highlightBlock` call-counted):

| action | ms/char | `highlightBlock` calls/char |
|---|---|---|
| plain chars in text content | 0.3 | 1 |
| typing one `"` in text content (opens the state) | **187.4** | **11,999** (= whole document) |
| plain chars typed while the quote is left open | 0.3 | 1 |
| `ab"cd` typed inside an attribute value (parity toggles twice) | 17.8 | 1,201 |

So the per-character average the reporter measured (123 ms) is the amortised cost of the full-document
cascades triggered by the parity-flipping characters, exactly as hypothesised.

Two further findings that shape the fix:

1. **The cascade is not required for correct XML highlighting — the current semantics are actually
   *wrong*.** In XML a `"` delimits an attribute value **only inside a tag**; in text content it is an
   ordinary character. In `.pgtp` files event-handler bodies are stored as XML-escaped **plain text
   content** (`pgtp_editor/ui/event_body.py:19-27` — "NOT CDATA", `<`/`>` stored as `&lt;`/`&gt;`), i.e.
   PHP source full of `"` characters that today are treated as attribute-value delimiters. A single
   odd-quoted PHP line would today paint the entire rest of the document as a string.
2. **Real documents never carry the state at rest**, so this is purely a mid-typing cost, not a rendering
   defect users see at rest: over `tests/sample/ERP_i01-r02_italian.pgtp` (42,504 lines, 2.5 MB) there are
   **0** odd-quoted lines and 0 lines that end carrying `STATE_IN_UNCLOSED_STRING`. The state only ever
   goes non-zero while the user is mid-way through typing an attribute value — which is precisely the
   reported scenario.

Also relevant, and *not* the cause: `pgtp_editor/ui/code_editor.py:194-206` (`_STATE_IN_BLOCK_COMMENT`)
uses the same cross-block-state pattern but is naturally bounded, because `*/` re-synchronises the state
and unterminated `/*` is rare — so it is a fine sibling precedent for *having* a block state, just not for
parity-based state.

**Proposed fix:** Replace the parity heuristic in `XmlSyntaxHighlighter.highlightBlock` with a small,
XML-aware, single-pass character state machine whose state re-synchronises within a line or two, so Qt's
cascade terminates almost immediately. All in `pgtp_editor/ui/xml_editor.py`.

1. Replace the two-value state (`STATE_NORMAL`/`STATE_IN_UNCLOSED_STRING`, `:73-74`) with four:
   `OUT` (text content) `= 0`, `IN_TAG` `= 1`, `IN_DQ` (inside a double-quoted attribute value) `= 2`,
   `IN_SQ` (single-quoted value) `= 3`. Keep `STATE_NORMAL = 0` as the name for `OUT` if you prefer minimal
   churn, but do **not** keep `STATE_IN_UNCLOSED_STRING = 1` meaning "in string" — value 1 must become
   `IN_TAG` or the semantics get confusing. Normalise `previousBlockState() == -1` (first block / Qt's
   "no state") to `OUT`.
2. Rewrite `highlightBlock` as one left-to-right pass over `text` carrying that state:
   - `OUT`: only `<` matters → `IN_TAG`. **Quotes in text content are ignored for state purposes.**
   - `IN_TAG`: `"` → `IN_DQ` (record string start), `'` → `IN_SQ`, `>` → `OUT`, `<` → **resync** (stay
     `IN_TAG`, restart the tag here).
   - `IN_DQ`/`IN_SQ`: matching quote → `IN_TAG` (emit `_string_format` over the run); `<` → **resync** to
     `IN_TAG` (drop the string).
   - At end of line, if a string run is open, format to end of line and carry the state.
3. **The `<` resync rule is what bounds the cascade** and it is XML-legal: a raw `<` can never occur inside
   a tag or inside an attribute value (it must be `&lt;`), so encountering one proves the carried state is
   bogus. In a `.pgtp` the next raw `<` is at most a line or two away, so the state returns to its previous
   value and Qt stops. Prototype measured in this repo on the same 12,000-block document:
   quote in text content **1** block re-highlighted (was 11,999), `ab"cd` inside an attribute value **1**
   block/char (was 1,201), single `"` inside a tag **3** blocks (was 11,999) — 0.2-0.4 ms/char across the
   board. Do not skip the resync rule; without it the tag-aware machine alone still cascades to EOF
   (verified: an unterminated attribute quote followed by PHP lines with balanced quotes keeps flipping
   state forever, exactly like parity).
4. **Optional hardening (recommended, cheap):** even with the resync, a carried `IN_DQ` can run to the end
   of a very long handler body that contains no raw `<` (bodies escape `<` as `&lt;`). If you want a hard
   bound, cap propagation at N blocks (e.g. 500) by encoding a countdown in the block state
   (`state | (remaining << 4)`) and forcing `OUT` at 0. Only add this if you also add a test for it —
   otherwise the resync rule is sufficient for the reported document shapes.
5. **Keep the tag/attribute-name colouring.** The prototype above only proved the state machine; the real
   implementation must still apply `_tag_format` to `<name`/`</name`/`>` /`/>` and `_attr_name_format` to
   `name=` tokens. Easiest low-risk shape: use the state machine to determine the state *and* the
   `[start, end)` spans that are inside tags, then run the existing `_TAG_OPEN_RE` / `_TAG_CLOSE_RE` /
   `_ATTR_NAME_RE` (`:76-79`) **within the in-tag spans only**, instead of over the whole line.
6. **Visual-correctness decision to make explicitly (call it out in the commit message):** under the new
   semantics, quoted runs in *text content* (PHP string literals in event bodies) are no longer painted
   with `_string_format`. If preserving today's look matters, keep a purely **line-local**
   `_ATTR_VALUE_RE` (`:79`, `"[^"]*"`) pass over the `OUT` portions of the line — line-local means no block
   state is set from it, so it cannot cascade. This is the recommended compromise: identical appearance at
   rest, no cross-block cost. (Note that event-handler bodies also get their own background styling via
   `_refresh_code_region_selections`, so the loss would be modest either way.)
7. Delete `_has_unterminated_quote` (`:340-341`) once unused — grep confirms it has no other caller in
   `pgtp_editor/` and no test references it.
8. **Gotcha — `--debug` tracing.** `pgtp_editor/debuglog.py:284` silences the hot path with the prefix pair
   `("ui.xml_editor", "XmlSyntaxHighlighter.")`, which is a **qualname prefix**: new helpers must be
   **methods on `XmlSyntaxHighlighter`** to stay excluded. A new module-level helper function (as
   `_has_unterminated_quote` is today — it is *not* covered by that exclusion) would flood the debug log on
   every block. `tests/test_debuglog.py:205-215` asserts `XmlSyntaxHighlighter.highlightBlock` is excluded,
   so keep the class and method names.
9. **Out of scope for this entry:** the reporter's other residuals (newlines 14.1 ms/char, attribute-with-
   quotes 28.6 ms/char) are only partly explained by this cascade; re-measure after the fix and file
   separately if anything remains.

**Test impact:** Existing coverage lives in `tests/ui/test_xml_editor.py` — extend it, do not duplicate:

- `test_highlighter_is_attached_to_document` (`:47`), `test_tag_name_and_attribute_name_get_distinct_formats`
  (`:54`) — must stay green; they pin tag vs. attr-name vs. attr-value colours via the `_format_at` helper
  (`:31-43`), which is the tool to reuse for any new assertion.
- `test_unclosed_quote_propagates_string_format_to_next_line` (`:69-77`) and
  `test_closing_the_quote_reverts_second_line_format` (`:80-95`) are **the** multi-line-attribute-value
  tests, and they are the behavioural contract for the block state. Both use
  `'<Page fileName="unterminated\nsecond line ordinary text'` — i.e. the unterminated quote is **inside an
  open tag**, so both still pass under the proposed machine (verified by inspection of the state
  transitions: line 2 starts `IN_DQ`, has no `"` and no `<`, so it stays string-formatted). Do not weaken
  them.
- New cases needed: (a) a quote in **text content** does *not* propagate string format to the next line
  (the semantics change — this is the new contract, and it is the case that used to cost 12k re-highlights);
  (b) a `<` on a following line **resyncs** the state — given `<A x="\n<B/>\ntail text`, `tail text` must
  *not* be string-formatted; (c) a perf/structural regression test in the spirit of
  `tests/ui/test_xml_editor_nav_perf.py` (BUG-015's home for edit-path counting): build a document of a few
  thousand blocks, monkeypatch/count `XmlSyntaxHighlighter.highlightBlock` (patch the **class attribute
  before constructing the editor** — patching after construction does not take effect for the already-bound
  PySide6 virtual, which cost time during this triage), type a single `"`, and assert the call count is a
  small constant (say `< 50`) rather than ~`blockCount()`. That test fails loudly today (11,999) and is the
  durable guard.
- Run with `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest tests/ui/test_xml_editor.py -q` while
  iterating (system `python` has no pytest on this box), then the full suite with `-n 10` at commit time.

**Spec impact:** Diverges from CONSOLIDATED_SPEC §8 "Raw XML editor", `CONSOLIDATED_SPEC.md:398-399`, which
documents the current design verbatim: "**Highlighting:** four categories (delimiters/names, attribute
names, values, text); unclosed-quote state propagated across blocks via Qt block state." That sentence
describes the buggy parity propagation as intended behavior, so it must be rewritten after the fix lands
(new wording along the lines of: tag-aware block state — `OUT`/`IN_TAG`/`IN_DQ`/`IN_SQ` — with a raw `<`
forcing a resync so cross-block propagation is bounded; quotes in text content are not attribute
delimiters). Flag for `spec-maintainer` **after** the fix lands; do not edit the spec as part of the fix.

---
## BUG-017: Parallel-only suite flake (and hard segfaults): monkeypatching the virtual `XmlSyntaxHighlighter.highlightBlock` on the class leaves a dangling PySide override that BUG-013's theme sweep later calls in unrelated tests
**Status:** RESOLVED (4783f84)
**Reported:** 2026-08-02
**Report (verbatim):** "Under the full-suite parallel gate (`QT_QPA_PLATFORM=offscreen venv/bin/python -m
pytest -q -n 10`), roughly 2 runs in 3 produce: `FAILED
tests/ui/test_xml_editor_theme.py::test_app_wide_apply_theme_flips_editor_both_ways` +
`ERROR tests/ui/test_xml_structure.py::<varying test>` (1 failed, 2407 passed, 32 skipped, 2 errors). The
FAILED test is stable across runs; the ERRORed `test_xml_structure.py` tests VARY between runs. Runs clean
in isolation and does not reproduce serially. The captured traceback points at
`pgtp_editor/ui/xml_editor.py` in `_theme_sweep_tick`, at the `self._highlighter.rehighlightBlock(block)`
call, raising a masked `TypeError: Error calling Python override of
QSyntaxHighlighter::highlightBlock()`. The real underlying exception is hidden — recovering it is
valuable. Suspected: a BUG-013 theme sweep started by the theme test is still pending when that test ends
and later fires during another test, plausibly triggered by conftest's autouse `qapp.setStyle()`
teardown."

**Root cause:** Two independent facts combine; **only the first is a defect**, the second is what fires it.

**(1) The defect — a dangling PySide virtual-override pointer, created by a TEST.**
`tests/ui/test_xml_editor.py:1629-1642`, `_count_highlight_calls()`, does
`monkeypatch.setattr(module.XmlSyntaxHighlighter, "highlightBlock", counting)` — it replaces a **virtual
method on a Shiboken (PySide6) class**. PySide6 binds the Python override **per instance, at construction
time**, not per call. Verified directly (probe, PySide6 6.11): an `XmlEditor` built *before* the patch
counts 0 calls through `counting`; one built *during* the patch counts every call. When
`monkeypatch.undo()` runs at teardown and the `counting` closure is garbage-collected, every highlighter
instance constructed while the patch was live keeps pointing at the **freed function object**. The next
`rehighlight()`/`rehighlightBlock()` on such an instance calls through that dangling pointer:
  * if the freed memory now holds some other 0-argument callable, PySide reports exactly the masked error
    from the report — the real exception is `<that callable>() takes 0 positional arguments but 2 were
    given` (`self`, `text`). **Recovered verbatim from a repro run:**
    `TypeError: Error calling Python override of QSyntaxHighlighter::highlightBlock():
    pytest_timeout_set_timer.<locals>.cancel() takes 0 positional arguments but 2 were given`
    (an unrelated pytest-timeout closure that happened to land in the freed slot; a standalone probe that
    churns the allocator produced `<lambda>() takes 0 positional arguments but 2 were given` instead —
    the name is whatever occupies the freed memory, which is why it looks nonsensical);
  * if it holds something that is not a callable at all, the process **segfaults** —
    `Fatal Python error: Segmentation fault` with a native stack through
    `QSyntaxHighlighter::rehighlightBlock` ← `QTimer::timeout`. Reproduced repeatably (exit 139).
  The traceback frame Qt/pytest-qt reports for this error is arbitrary (seen at
  `xml_editor.py:820` in `_theme_sweep_tick`, and at `editor_gutter.py:380` in
  `_update_gutter_on_scroll`) — it is the frame the interpreter happened to be in, not the culprit. Do not
  chase `editor_gutter.py` or `xml_structure`.

**(2) The amplifier — theme sweeps keep running on leaked editors, in other tests.** Not a defect, but it
is why a dormant dangling pointer fires in unrelated tests and why the victims shift:
  * pytest-qt's teardown (`qtbot.py:_close_widgets` → `w.close(); w.deleteLater()` +
    `plugin.py:_process_events`) does **not** actually destroy the C++ widget: `processEvents()` at loop
    level 0 does not deliver `DeferredDelete`. Verified by probe — after
    `close()+deleteLater()+processEvents()`, `shiboken6.isValid(editor)` is still `True`. Editors from
    earlier tests stay alive for a long time.
  * `tests/ui/conftest.py`'s autouse `_reset_app_style_and_palette` teardown (`qapp.setStyle` /
    `setPalette` / `setStyleSheet`) delivers `ApplicationPaletteChange` to every one of those leaked
    editors → `XmlEditor.changeEvent` (`xml_editor.py:830-841`) → `apply_theme_colors` →
    `_theme_kickoff_timer` → `_rehighlight_for_theme` (`xml_editor.py:773-811`) → `_theme_sweep_timer` →
    `_theme_sweep_tick` (`xml_editor.py:813-828`), 400 blocks per event-loop turn, spilling into whatever
    test's `processEvents()` spins next. Measured with an instrumented full-suite run: **10,731 sweep
    ticks whose sweep was started in a different test than the one it ticked in.**
  The stable victim is `test_app_wide_apply_theme_flips_editor_both_ways` because it is the one test that
  explicitly calls `qapp.processEvents()` twice (`tests/ui/test_xml_editor_theme.py:58,63`); the varying
  `test_xml_structure.py` victims are simply whichever fast, neighbouring tests' SETUP/TEARDOWN
  `_process_events()` spun the loop next in that xdist worker — hence "shifting victim set" and the
  parallel-only, ~2-in-3 flakiness (which reused memory lands in the freed slot is chance).

**Confirmed reproduction — deterministic, no `-n` needed** (the report's "does not reproduce serially" was
a file-selection artifact, not a parallelism requirement):
```
QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/ui/test_xml_editor.py \
    tests/ui/test_xml_editor_theme.py -q
# -> 1 failed, 107 passed, 2 errors  (exactly the reported shape)
QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/ui/test_xml_editor.py \
    tests/ui/test_xml_editor_nav_perf.py tests/ui/test_xml_editor_theme.py \
    tests/ui/test_xml_structure.py -q
# -> Fatal Python error: Segmentation fault (exit 139), 3/3 runs
```
Deselecting only the two BUG-016 tests that call `_count_highlight_calls`
(`test_quote_in_text_content_does_not_rehighlight_the_document`,
`test_unterminated_quote_inside_a_tag_resyncs_at_the_next_tag`) makes the first command green
(108 passed) — proving those two tests are the source.

**User impact: NONE — this is strictly a test artifact, with evidence.** Nothing in `pgtp_editor/` ever
reassigns `highlightBlock`; the dangling override can only be created by that test helper. The candidate
production paths in the report were probed explicitly and are all safe: with a sweep in flight
(`_theme_sweep_block == 400` of a 3000-line document), each of `setPlainText(shorter text)`, `clear()`,
`close()+deleteLater()`, and `shiboken6.delete(editor)` completes with **no exception** — a shorter
document just makes `findBlockByNumber` return an invalid block and `_theme_sweep_tick` stops the timer
(`xml_editor.py:825-828`), and the parented timers die with the editor (BUG-014's fix). So "theme toggled
while a document is replaced" and "project closed mid-sweep" are **not** user-facing failures. Priority is
therefore "unblock the parallel gate", not "urgent user-facing crash".

**Proposed fix:**

1. **(Required — this is the actual fix.)** In `tests/ui/test_xml_editor.py`, rewrite
   `_count_highlight_calls(monkeypatch)` (lines 1629-1642) so it **never sets an attribute on the
   Shiboken class**. Patch the *module name* the editor constructs from instead, with a real Python
   subclass:
   ```python
   def _count_highlight_calls(monkeypatch):
       import pgtp_editor.ui.xml_editor as module
       calls = {"n": 0}

       class _CountingHighlighter(module.XmlSyntaxHighlighter):
           def highlightBlock(self, text):
               calls["n"] += 1
               super().highlightBlock(text)

       monkeypatch.setattr(module, "XmlSyntaxHighlighter", _CountingHighlighter)
       return calls
   ```
   `XmlEditor.__init__` builds its highlighter via `XmlSyntaxHighlighter(self.document())`
   (`xml_editor.py:536`), a module-global lookup, so editors created inside the test get the subclass and
   editors created outside are untouched. The override lives in the subclass's own `__dict__` and the
   instance keeps its type alive, so undoing the patch cannot leave a dangling pointer. **Gotchas:** the
   helper must still be called *before* the editor is constructed (keep that docstring note — it is now
   load-bearing for a different reason: the module lookup happens in `__init__`); use
   `super().highlightBlock(text)`, not a captured `real(self, text)`; and the two call sites' assertions
   (`calls["n"] <= 2` / `<= 4`) stay as-is.
2. **(Strongly recommended, cheap.)** Add a positive assertion to both BUG-016 tests that the counter
   actually observed *something* (e.g. `calls["n"] >= 1` measured over the initial `setPlainText`, before
   the counter is reset to 0) — the current `<=` assertions pass vacuously if the patch ever stops taking
   effect, which is exactly how a broken counting hook could hide.
3. **(Optional, defense in depth, production code.)** The cross-test sweep storm is legitimate waste even
   without the dangling pointer (10k+ ticks per suite run). Consider, in `pgtp_editor/ui/xml_editor.py`:
   stop `_theme_sweep_timer` and reset `_theme_sweep_block` at the top of `setPlainText` (line 693) before
   `super().setPlainText(text)` — the document being swept no longer exists in any meaningful sense — and
   optionally skip the sweep for an editor that `not self.isVisible()`, restarting it from `showEvent`.
   **Gotcha:** an `isVisible()` guard would break
   `tests/ui/test_xml_editor_theme.py::test_deferred_theme_rehighlight_does_not_fire_on_deleted_editor`,
   which asserts `_theme_rehighlight_pending is True` on a never-shown editor, and would change
   BUG-013's documented two-stage behavior — if it is taken, it needs its own spec pass (see below). The
   flake is fixed by (1) alone; do not let (3) block it.
4. **Do NOT** "fix" this by suppressing the symptom (try/except around `rehighlightBlock`, or stopping the
   sweep on error) — the underlying condition is a use-after-free that also segfaults.

**Test impact:** The change is in `tests/ui/test_xml_editor.py` itself (the BUG-016 group, lines
1626-1689) — extend it, do not add a parallel file. Verify with the two deterministic commands above
(expect `108 passed` and no segfault) and then the full parallel gate,
`QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q -n 10`, run **at least three times** since the
original failure was ~2-in-3. Related existing files that must stay green and need no change:
`tests/ui/test_xml_editor_theme.py` (the stable victim; its 6 tests already cover the two-stage sweep and
BUG-014's parented kickoff), `tests/ui/test_xml_structure.py` (innocent victims),
`tests/ui/test_xml_editor_nav_perf.py` (patches `xml_structure.scan` — a plain module attribute, which is
safe; leave it alone). New case worth adding to `tests/ui/test_xml_editor.py`: a guard that the counting
helper does not touch the Shiboken class, e.g. capture `orig = module.XmlSyntaxHighlighter.highlightBlock`
before calling the helper and assert it is unchanged afterwards **and** that
`type(editor._highlighter) is not module.XmlSyntaxHighlighter` (i.e. counting really goes through a
subclass). If fix (3) is taken, add to `tests/ui/test_xml_editor_theme.py`: after starting a sweep,
`editor.setPlainText("<a/>")` leaves `editor._theme_sweep_timer.isActive() is False` and
`_theme_sweep_block == 0`.

**Spec impact:** None for fixes (1)/(2) — CONSOLIDATED_SPEC §"Document state" (lines 337-351) describes
the two-stage theme rehighlight exactly as implemented, and nothing there is contradicted; the bug is a
test-harness use-after-free. If optional fix (3) is taken (sweep stopped on `setPlainText`, and/or
deferred while the editor is hidden), that **does** diverge from those lines and from the Supersession
Ledger row dated 2026-08-01 for BUG-013 (line 2182) — flag for `spec-maintainer` after the fix lands; do
not edit the spec as part of the fix.

---

## BUG-018: Caption-mode "select the matching row" silently selects nothing whenever Shift is held (`QTableView.selectRow` + stale global modifier state) — the real cause of the parallel-gate caption flake
**Status:** RESOLVED (2508d2a)
**Reported:** 2026-08-02
**Report (verbatim):** "Triage a load-dependent test failure on branch `ddl-editing` (HEAD 9412317). Follow-up BUG-012 asked for: with BUG-017's segfaults gone, I captured full tracebacks over 7 clean-signal `-n 10` gate runs. The failure still occurs, roughly 2 in 7, and it is a genuine AssertionError with a clean traceback — no crash, no segfault:
```
tests/ui/test_main_window.py::test_enter_caption_mode_for_field_selects_row
        assert _visible_values(panel) == ["WBS"]     # <-- PASSES
        selected = panel._table.selectionModel().selectedRows()
>       assert len(selected) == 1
E       assert 0 == 1
E        +  where 0 = len([])
tests/ui/test_main_window.py:1129: AssertionError
```
The critical discriminator: the assertion on the preceding line passes… only the SELECTION is missing. Also observed: the failing test VARIES between runs within this same small family — `test_see_column_in_caption_filters_and_selects_row` in one run, `test_enter_caption_mode_for_field_selects_row` in another. Both tests pass 5/5 in isolation."

**Root cause:** `pgtp_editor/ui/caption_management_panel.py:948–954`,
`CaptionManagementPanel._select_first_visible_row`, specifically line 953
`self._table.selectRow(first.row())`.

`QTableView.selectRow()` is **not** an unconditional "select this row" API. Internally
(`QTableViewPrivate::selectRow`) it asks `QAbstractItemView::selectionCommand()` what kind of
selection a *user gesture* on that row would mean, and for the default `ExtendedSelection` mode
that answer is read from the process-global keyboard state,
`QGuiApplication::keyboardModifiers()`:

- No modifier → `ClearAndSelect` → the row is selected (the normal, passing case).
- **Shift held → `SelectCurrent`**, which carries the `Current` flag. Because of that flag
  `QTableViewPrivate::selectRow` does **not** update its `rowSectionAnchor` (it treats the call as
  "extend the existing shift-anchor"), so the anchor keeps its initial value `-1`, and the range it
  then builds is `index(min(-1, 0) = -1, 0) … index(0, columnCount-1)` — an **invalid** top-left.
  `QItemSelectionModel::select()` on that range selects nothing at all. `scrollTo` still runs, the
  current index is still set to (0,0), and the proxy is completely unaffected — which is exactly the
  reported discriminator: the filter assertion passes, `selectedRows()` is `[]`.

**Directly proven during triage, not inferred.** An instrumented full-suite `-n 10` run (a scratch
pytest plugin wrapping `_select_first_visible_row` and dumping view/header/selection state on any
call that did not end with exactly one selected row) caught the failure on run 2 and logged:

```
{"nodeid": "tests/ui/test_main_window.py::test_enter_caption_mode_for_field_selects_row",
 "worker": "gw8",
 "before": {"rows": 1, "hcount": 8, "hlen": 800, "hoffset": 0, "logical0": 0, "rtl": false,
            "vpw": 616, "vph": 387, "selmode": "SelectionMode.ExtendedSelection",
            "selbehav": "SelectionBehavior.SelectItems", "visible": false,
            "mods": 33554432, "state": "State.NoState", "hidden_cols": []},
 "after": {"selrows": 0, "selidx": 0, "cur": [0, 0], "rows_after": 1, "src_rows": 5}}
```

`mods: 33554432` is `Qt.KeyboardModifier.ShiftModifier` (0x02000000). Everything else about the view
is healthy: 1 proxy row before *and* after, 8 header sections, header length 800, `logicalIndexAt(0)
== 0`, LTR, `ExtendedSelection`, no hidden columns, no crash. The only anomaly is the latched Shift.

Confirmed by a standalone deterministic repro (no xdist, no load): latch Shift with
`QTest.keyClick(w, Key_A, ShiftModifier)`, then call `panel.filter_to_field("wbs_id")` →
`selectedRows() == []` and `selectedIndexes() == []`, every time. Full modifier matrix measured
against the *current* code and against the proposed fix:

| latched global modifier | `selectRow` (current) | selection-model approach (proposed) |
|---|---|---|
| none | 1 row | 1 row |
| **Shift** | **0 rows** | 1 row |
| Ctrl | 1 row | 1 row |
| **Ctrl+Shift** (QTest leaves Shift latched) | **0 rows** | 1 row |
| Alt | 1 row | 1 row |

**Where the latched Shift comes from (the load dependence).** `QGuiApplication::keyboardModifiers()`
is process-global and is updated by `QTest`-synthesised key/mouse events; under `offscreen` nothing
ever clears it again, so it stays latched for the **rest of that worker process**. Three existing
tests leave it non-zero (measured with a teardown probe printing every transition):

- `tests/ui/test_code_editor.py::test_ctrl_shift_b_selects_bracket_span_caret_at_start` (line 179,
  `qtbot.keyClick(editor, Key_B, ControlModifier | ShiftModifier)`) → leaves **Shift** (33554432)
- `tests/ui/test_history_wiring.py::test_ctrl_shift_z_in_editor_triggers_snapshot_redo` (line ~231,
  `QTest.keyClick(editor, Key_Z, ControlModifier | ShiftModifier)`) → leaves **Shift**
- (harmless but same class: `test_code_editor.py::test_dialog_ctrl_s_saves`,
  `test_history_wiring.py::test_ctrl_z_in_editor_fires_undo_exactly_once`,
  `tests/ui/test_xml_editor_click_nav.py` Ctrl/Alt click tests → leave Ctrl / Alt, which do not break
  `selectRow`)

So the "load dependence" is **not** thread timing and there is no asynchrony in the caption path
(BUG-012's reading of the code path was correct). It is **pytest-xdist `--dist load` scheduling**:
which tests land in which of the 10 worker *processes*, and in what order, is decided dynamically by
timing, so a Shift-latching test precedes a caption test in the same process only in some runs.
That fully explains every observed property — ~2 in 7 runs, the failing member of the family varying
run to run, always a clean `AssertionError` (never a crash), and 5/5 green in isolation.

**Production defect or test artifact: it is a real (low-frequency) production defect**, and the test
flake is only its most visible symptom. In the running app `keyboardModifiers()` reflects the actual
keyboard, so any user who happens to hold **Shift** while triggering the caption-jump actions — tree
context menu ▸ "See column in caption" (`MainWindow._on_tree_see_column_in_caption`,
`main_window.py:1205` → `enter_caption_mode_for_field`, `main_window.py:2250`), or the equivalent
menu/keyboard route — lands in Caption Mode with the grid correctly filtered to one row but **no row
selected and nothing highlighted**, which also breaks the follow-on selection-dependent actions
(Ctrl+G go-to-line, Copy, Insert NULL) until they click a row. Shift+click on a menu item is a
perfectly ordinary thing for a user to do by accident. Priority is therefore "real bug, low
frequency, but the fix is small and also buys back the gate" — not "test-only cosmetics".

**Proposed fix:** two parts; part 1 is the actual fix, part 2 stops this whole class of
cross-test contamination from recurring.

1. **Production (`pgtp_editor/ui/caption_management_panel.py`, `_select_first_visible_row`, lines
   948–954).** Stop routing a *programmatic* selection through the *gesture-interpreting*
   `QTableView.selectRow`, and drive the selection model explicitly (verified to give exactly one
   selected row under every modifier state in the matrix above):

   ```python
   def _select_first_visible_row(self) -> None:
       """Select and scroll to the first row visible through the proxy."""
       if self._proxy.rowCount() == 0:
           return
       first = self._proxy.index(0, 0)
       last = self._proxy.index(0, self._proxy.columnCount() - 1)
       selection_model = self._table.selectionModel()
       selection_model.setCurrentIndex(
           first, QItemSelectionModel.SelectionFlag.NoUpdate
       )
       selection_model.select(
           QItemSelection(first, last),
           QItemSelectionModel.SelectionFlag.ClearAndSelect
           | QItemSelectionModel.SelectionFlag.Rows,
       )
       self._table.scrollTo(first)
   ```

   Gotchas:
   - Imports: `QItemSelection` and `QItemSelectionModel` come from `PySide6.QtCore` (the module
     currently imports neither; `QModelIndex`, `Qt` etc. are already imported there).
   - Keep `setCurrentIndex(..., NoUpdate)` **before** `select(...)` and keep it `NoUpdate`, so the
     current index does not itself re-issue a selection command. Ctrl+G / `go_to_line_current` and
     the context-menu actions read the current index and/or `selectedRows()`, so both must be set.
   - `ClearAndSelect | Rows` (with a full-width `first..last` range) is required for
     `QItemSelectionModel.selectedRows()` to report the row: the table's
     `SelectionBehavior.SelectItems` (line 632) means a partial-width range would not count as a
     selected *row*. Do **not** "fix" this by switching the table to `SelectRows` — the grid is
     cell-selectable on purpose (copy/paste TSV of arbitrary cell rectangles, `Insert NULL` on
     selected New Value cells).
   - Do not add retries, `qtbot.wait`, `processEvents`, or xdist grouping anywhere — none of them
     are relevant; the path is synchronous and the fix above makes it modifier-independent.
   - `selectRow` at line 953 is the only `selectRow`/`selectColumn` call in `pgtp_editor/`, so there
     is no sibling site to fix.

2. **Test hygiene (`tests/ui/conftest.py`, or `tests/conftest.py` if the leaking tests are not all
   under `tests/ui/`).** Add an autouse teardown fixture that clears the process-global modifier
   state after every test, so one test's `Ctrl+Shift+…` can never again change another test's
   behavior:

   ```python
   @pytest.fixture(autouse=True)
   def _reset_keyboard_modifiers():
       yield
       if QGuiApplication.instance() is not None and QGuiApplication.keyboardModifiers():
           QTest.keyClick(QWidget(), Qt.Key.Key_Shift, Qt.KeyboardModifier.NoModifier)
   ```

   Verified during triage: a `QTest.keyClick(..., NoModifier)` on a throwaway, never-shown `QWidget`
   resets `QGuiApplication.keyboardModifiers()` from Shift back to 0. Guard on
   `QGuiApplication.instance()` so non-Qt tests (and xdist workers that never built a QApplication)
   are unaffected, and keep the temporary widget local so nothing is added to the qtbot registry.

**Test impact:** existing coverage of this exact path, extend rather than duplicate:
- `tests/ui/test_caption_management_panel.py::test_filter_to_field_shows_and_selects_matching_row`
  (~line 1435) — panel-level, the natural home for the new regression case.
- `tests/ui/test_main_window.py::test_enter_caption_mode_for_field_selects_row` (line 1116) and
  `::test_see_column_in_caption_filters_and_selects_row` (line 1260) — the two window-level tests
  that actually flake; leave their assertions as they are (they are correct), they become stable
  once the production fix lands.
- New case (panel-level, deterministic, no xdist needed): latch Shift with
  `QTest.keyClick(<some widget>, Qt.Key.Key_A, Qt.KeyboardModifier.ShiftModifier)`, then
  `panel.filter_to_field("wbs_id")`, and assert exactly one selected row mapping back to the
  `wbs_id` entry — i.e. "the caption jump selects its row regardless of held modifiers". This test
  fails on today's code and passes with the fix. If fix (2) lands, the fixture will clear the latch
  afterwards; if not, clear it in the test itself.
- Validation: `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q -n 10` several times (the
  failure was ~2 in 7 before; one instrumented run out of two caught it during triage), plus the
  targeted files above.

**Spec impact:** none. `docs/superpowers/CONSOLIDATED_SPEC.md` §13 (Caption Mode, line 1129) does not
describe the preset-filter row-selection mechanics, and the fix restores the already-intended
behavior ("filter to the field, then select + scroll to the first matching row", the docstring at
`caption_management_panel.py:936–939`) rather than changing it. Nothing for `spec-maintainer`.

---

## BUG-019: Overloaded functions are silently lost -- `fetch_routines_and_triggers` keys the routines dict by `schema.name`, so the second overload overwrites the first

**Renumbered from BUG-018 (2026-08-03):** assigned in parallel with the unrelated caption-mode BUG-018
above by a different worktree session before the two branches merged; renumbered to BUG-019 on merge
to resolve the ID collision, no content change.

**Status:** RESOLVED (b021b3d)
**Reported:** 2026-08-02
**Report (verbatim):** "`pgtp_editor/db/introspect.py:403` in `fetch_routines_and_triggers` keys the
routines dict by `f\"{schema_name}.{name}\"`. PostgreSQL identifies functions by `(schema, name, argument
types)`, so overloads are distinct objects that legitimately share `schema.name`. A database containing
both `public.fmt(integer)` and `public.fmt(text)` produces two rows from the catalog query, both of which
land on the same dict key — the second silently overwrites the first. Every consumer downstream sees only
one overload and has no way to know another existed. Note the triggers dict two lines below
(`introspect.py:417`) IS correctly keyed, `f\"{schema_name}.{table_name}.{name}\"`. So this is specifically
the routines key, and the correct-key pattern is already present right next to it. `RoutineInfo` itself
carries `arg_types: list[str]` (introspect.py:70), so the disambiguating data is fetched and retained — it
just is not used in the key. […] Propose the fix. The obvious candidate is keying on the rendered
signature `schema.name(argtypes)`, matching what `db/ddl_buffer.py`'s banner comment already renders and
what the new `db/schema_diff.py::routine_identity` computes. There is a strong argument for extracting one
shared identity helper rather than a third independent implementation of the same string."

**Root cause:** Confirmed by reading the whole path.

1. **The catalog query does not deduplicate.** `pgtp_editor/db/introspect.py:176-202` (`_ROUTINES_SQL`) is
   a plain `SELECT … FROM pg_catalog.pg_proc p JOIN pg_namespace JOIN pg_language WHERE p.prokind IN
   ('f','p') AND …` — no `DISTINCT`, no `GROUP BY` at the outer level (the two `array_agg` subqueries are
   correlated per-row over `p.proargtypes` / `proallargtypes`). `pg_proc` holds **one row per overload**,
   so `public.fmt(integer)` and `public.fmt(text)` arrive as two distinct rows, each with its own
   `arg_types`. The loss happens purely in Python.
2. **The dict assignment collapses them.** `pgtp_editor/db/introspect.py:390-412`,
   `fetch_routines_and_triggers`: the row loop ends at line 403 with
   `routines[f"{schema_name}.{name}"] = RoutineInfo(…)`. Second row wins; the first `RoutineInfo` — a
   fully-populated, correct object — is discarded before any consumer sees it. Nothing logs or counts the
   loss; `_log.info(… routines=%d …)` at `:428-433` reports the *post-collapse* `len(routines)`, so even
   the debug log under-reports.
3. **The sibling key two lines down is correct.** `introspect.py:417` keys triggers
   `f"{schema_name}.{table_name}.{name}"` — the report is right that the "key by everything that makes the
   object unique" pattern already exists in the same function, five lines away.

**Second, independent collision in the same feature (must be fixed together or overload support stays
broken):** `pgtp_editor/ui/ddl_buffer_panel.py:74-80`, `BrowserPanel.set_schema`, builds
`span_by_routine[(span.schema, span.name)] = span` — keyed on `(schema, name)` with no argument types,
and `DdlObjectSpan` (`db/ddl_buffer.py:36-43`) carries no argument types to key on. The lookup at
`ddl_buffer_panel.py:119` (`span_by_routine.get((routine.schema, routine.name))`) therefore hands **both**
overloads the *same* (last-wins) span. Fixing only `introspect.py` would make two tree items appear and
then navigate to the same body — a new, more confusing bug. `db/ddl_buffer.py::build_ddl_text` itself is
fine (it iterates `schema.routines.values()` at `:62` and emits one banner+span per routine).

**Blast radius — every read of `DatabaseSchema.routines`** (grepped across `pgtp_editor/` and `tests/`):

| Site | How it reads | Affected by the key change? |
|---|---|---|
| `db/ddl_buffer.py:62` `build_ddl_text` | `.values()` | No — but see sort note below |
| `ui/ddl_buffer_panel.py:109` `_build_routines_branch` | `.values()` | No (but the span map above is) |
| `ui/main_window.py:2524` DDL Explorer status message | `len(schema.routines)` | Behavior **improves** — the count stops under-reporting |
| `db/schema_diff.py:112-113` `diff_schemas` | `.values()` + own `routine_identity` | No — `_by_identity` (`:91-95`) deliberately ignores the dict key and its comment even names this bug |
| `tests/db/test_introspect.py:416,422,460` | **by key** (`"pr.calc_total"`, `"pr.do_thing"`, `"pr.split_name"`) | **Yes — the only production-path key-format dependency in the repo** |
| `tests/db/test_ddl_buffer.py:7-27,51`, `tests/ui/test_ddl_buffer_panel.py`, `tests/ui/test_ddl_explorer_wiring.py:36-55,343-348`, `tests/ui/test_ddl_editor_panel.py:81` | build their *own* fixture dicts and only iterate / re-key them | No (self-consistent fixtures; updating them to signature keys is cosmetic, do it for realism) |

No serialization, QSettings value, on-disk snapshot or `.pgtp` content embeds these keys today
(`db/schema_snapshot.py` does not exist yet), so the change is in-memory only — no migration of stored
data is required.

**Proposed fix**

*1. One shared identity helper, in `db/introspect.py`.*

> **Settled 2026-08-02 by the two sessions that own the consumers (§18.2/§18.5 and deployment SQL):
> make it a `@property` on `RoutineInfo`, not a module-level function.**
>
> ```python
> @property
> def signature(self) -> str:      # "public.fmt(integer, text)"
>     return f"{self.schema}.{self.name}({', '.join(self.arg_types)})"
> ```
>
> Preferred over a free function because **it travels with the data**: you cannot hold a `RoutineInfo`
> and accidentally not have its identity, whereas a free function can be forgotten and silently
> reimplemented — which is how this bug arose in the first place. It also matches how §18.2 treats
> `content_hash` (one implementation, consumed everywhere) without adding a second such rule.
>
> **Pin the zero-argument spelling explicitly: `public.f()` — empty parens, never bare `public.f`.**
> This is the divergence most likely to slip through, because zero-arg routines are the common case,
> so a mismatch there would be everywhere and invisible. Rendering is `", ".join(arg_types)` —
> comma-space, and `arg_types` (types only), **not** `args` (name/type pairs).
>
> Division of labour once it exists: `ddl_buffer`'s banner, `schema_diff.routine_identity` and the
> dict key all use `signature` **verbatim**. `db/ddl_project.py` derives filenames by *sanitizing*
> `signature` (Windows-illegal characters) rather than re-rendering it — the
> disambiguate-only-when-needed decision still needs the overload set, so
> `object_relpath(obj, overloaded=...)` stays, but the qualified form is `signature` put through
> sanitization, never a second rendering.
>
> The §18.5 owner will fold the single-source rule into the spec once this fix lands, so it is a
> stated invariant rather than a convention two sessions happen to remember.

The original triage proposed a module-level function at the same location, which remains a valid
fallback if a property turns out to be awkward:

```python
def routine_signature(routine: RoutineInfo) -> str:
    """`schema.name(argtype, argtype)` — PostgreSQL's real identity for a function."""
    return f"{routine.schema}.{routine.name}({', '.join(routine.arg_types)})"
```

Either way `introspect.py` is the right home and the *only* possible one of the three candidates:
`db/schema_diff.py` and `db/ddl_buffer.py` (and the target-design `db/ddl_project.py`) all already import
**from** `introspect`, so putting the helper in any of them and importing it back into `introspect` is a
circular import. Placing it at the bottom of the dependency chain lets all three consumers converge on it.

*2. Use it as the dict key.* `introspect.py:403` becomes (build the `RoutineInfo` first, then key off it, so
the string is computed by the helper and never re-inlined):

```python
routine = RoutineInfo(...)
routines[routine_signature(routine)] = routine
```

*3. Collapse the duplicate implementations onto it:*
- `db/schema_diff.py:73-83` — make `routine_identity` a one-line delegate
  (`return routine_signature(routine)`). **Keep the name and the whole docstring**: §18.3's plan names
  `routine_identity` explicitly and the docstring carries the R14 rationale ("never degrade this to
  `schema.name`"); tests and the migration generator import it. Do not delete it in favour of the new name.
- `db/ddl_buffer.py:46-51` — `_banner` currently formats `f"-- {label} {schema}.{name}({args}) --"` from
  loose `schema`/`name`/`arg_types` arguments. Either pass the `RoutineInfo` through and use
  `routine_signature`, or leave `_banner` alone and add a comment pointing at the helper. **The joined
  string must stay byte-identical** — the spec (§18.2, other worktree) states `<argtypes>` in the `ddl/`
  filename is "the same list `build_ddl_text`'s banner comment already prints", so banner, key, diff
  identity and future filename must not drift apart.
- The **joiner is `", "` (comma + space)**, matching both existing implementations. Do not "tidy" it to
  `","`: it would silently change `db/ddl_project.py`'s future `ddl/public.fmt(integer, text).sql`
  filenames and desynchronize the banner.

*4. Fix the BrowserPanel span map (same change set).* In `db/ddl_buffer.py`, add a trailing **optional**
field to `DdlObjectSpan` — e.g. `arg_types: tuple[str, ...] | None = None` (tuple, so the frozen dataclass
stays hashable) or `signature: str | None = None` — populated in `build_ddl_text:82-91` for routines and
left `None` for triggers. A **trailing field with a default** keeps the existing positional/keyword
constructions in `tests/ui/test_ddl_editor_panel.py:211-229` and `tests/db/test_ddl_buffer.py:81` valid.
Then in `ui/ddl_buffer_panel.py`: key `span_by_routine` on the signature string (`:74-80`) and look it up
with `routine_signature(routine)` (`:119`). `DdlObjectSpan` is constructed nowhere else in `pgtp_editor/`
(verified by grep — only `ddl_buffer.py:83`).

*5. Deterministic ordering for overloads.* `db/ddl_buffer.py:65` sorts by
`(schema, 0 if routine else 1, name)`. Two overloads tie on that key, so Python's stable sort falls back to
catalog row order — i.e. `pg_proc` physical order, which is not stable across servers or after a
`CREATE OR REPLACE`. Add `arg_types` (as a tuple, or the signature string) as the final tiebreak so the
buffer, the spans and therefore any future diff of the buffer are reproducible. The docstring at `:58-59`
("Deterministic order: schema, then kind …, then name") needs the extra clause.

*Gotchas*
- **Do not add a field to `RoutineInfo`.** `tests/db/test_introspect.py:416-421` asserts equality against a
  fully-spelled `RoutineInfo(...)`; a new dataclass field would break that assertion and every other
  fixture. A module-level function (preferred) or a `@property` is equality-neutral.
- Zero-argument routines key as `pr.do_thing()` — trailing empty parens. That is intentional and matches the
  banner and `routine_identity` today; it is what distinguishes `f()` from `f(integer)`.
- `ui/ddl_buffer_panel.py:100-137` also builds `triggers_by_function` keyed `(schema, function_name)` from
  `pg_trigger`, which only knows the function *name*. With overloads sharing a name, calling triggers will
  nest under **every** overload. Leave as-is — a trigger function takes no arguments and is not realistically
  overloaded — but do not "fix" it by feeding it signatures; `TriggerInfo.function_name` has none to give.
- **UI ambiguity, deliberately out of scope:** `ddl_buffer_panel.py:111-117` renders a routine's top line as
  bare `schema.name [F]` (no parens) when it has arguments — a 2026-08-01 Supersession Ledger decision. Two
  overloads therefore render two identically-labelled tree items distinguished only by their argument child
  leaves. Do **not** unilaterally change the label format in this fix; flag it for `spec-maintainer`
  (see Spec impact).

**Test impact**

Existing coverage to **extend, not duplicate**:
- `tests/db/test_introspect.py` — `_canned_routine_trigger_runner` (`:379-403`) is the canned-row fixture to
  reuse. `test_fetch_routines_and_triggers_builds_routines_keyed_by_schema_name` (`:412-422`) must be
  **renamed** (…`_keyed_by_signature`) and its lookups updated to `"pr.calc_total(integer)"` /
  `"pr.do_thing()"`; `test_fetch_routines_and_triggers_correlates_out_args_end_to_end` (`:443-463`) updates
  `"pr.split_name"` → `"pr.split_name(text)"` (note: `arg_types` is IN-only, so the key uses `(text)`, not
  the three `all_arg_types`). These two edits are the entire migration cost.
- `tests/db/test_ddl_buffer.py`, `tests/ui/test_ddl_buffer_panel.py`, `tests/ui/test_ddl_explorer_wiring.py`
  — local `_schema()` fixtures; update their dict keys to signature form for realism (no behavior depends
  on it).
- `tests/db/test_schema_diff.py:49-54` — `_schema()` keys routines `f"{r.schema}.{r.name}#{i}"` with a
  comment saying the diff must not rely on the dict key. **Keep that deliberate mismatch** — it is the
  regression guard for `_by_identity`; only refresh the comment, which currently states as fact that
  "`fetch_routines_and_triggers` keys routines by `schema.name`".

New cases needed (each fails today):
- `tests/db/test_introspect.py`: two catalog rows `("public","fmt",…,["integer"],…)` and
  `("public","fmt",…,["text"],…)` → `len(schema.routines) == 2`, keys exactly
  `{"public.fmt(integer)", "public.fmt(text)"}`, and each `RoutineInfo.source` is its own. Plus a unit test
  for `routine_signature` covering the zero-arg (`pr.f()`) and multi-arg (`pr.f(integer, text)`,
  comma-space) forms.
- `tests/db/test_ddl_buffer.py`: a schema with two overloads yields **two** banners
  (`-- FUNCTION public.fmt(integer) --` and `-- FUNCTION public.fmt(text) --`) and two non-overlapping
  spans; and a determinism test that reversing the input dict's insertion order produces identical text.
- `tests/ui/test_ddl_buffer_panel.py`: two overloads → two items under "Functions & Procedures", each
  carrying a **different** `DdlObjectSpan.start_line` (this is the `span_by_routine` regression, and it is
  the one that still fails if only `introspect.py` is fixed).
- `tests/db/test_schema_diff.py`: an end-to-end-ish case where the source schema is built the way
  `fetch_routines_and_triggers` now builds it (signature keys) and one overload differs — asserting the
  other overload is untouched.
- Optional but cheap: `tests/ui/test_ddl_explorer_wiring.py` — the status-message routine count reflects
  both overloads.

Run while iterating: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest tests/db/test_introspect.py
tests/db/test_ddl_buffer.py tests/db/test_schema_diff.py tests/ui/test_ddl_buffer_panel.py -q` (the repo
`venv` is the interpreter with pytest on this box); full suite with `-n 10` at commit time.

**Spec impact:** Flag for `spec-maintainer` **after** the fix lands — do not edit the spec as part of the fix.
- §18.1 (`CONSOLIDATED_SPEC.md:1261-1300`) describes `RoutineInfo`/`DatabaseSchema.routines` in detail but
  **never states the routines dict key**, so the current behavior was not an intentional documented
  decision — it is an omission the code filled in wrongly. §18.1 should gain an explicit sentence: routines
  are keyed by the full signature `schema.name(argtypes)` (contrast §17's tables, which the spec *does*
  pin as schema-qualified at `:1146`), and a pointer to the new shared `introspect.routine_signature` as
  the single producer of that string for the buffer banner (§18.1), the diff identity (§18.3,
  `schema_diff.routine_identity`) and the `ddl/` filename (§18.2, `db/ddl_project.py`).
- **Cross-worktree note:** §18.2's overload-disambiguating `ddl/` filename scheme and its
  `2026-08-02` Supersession Ledger row exist in the *other* worktree
  (`/home/zrb/Projects/pgtp_editor/.claude/worktrees/silly-booth-10fb09/docs/superpowers/CONSOLIDATED_SPEC.md`,
  §18.2 "File naming — disambiguate only when needed", ledger row at `:3213`), **not** in this branch's
  spec yet. That scheme is unimplementable until this bug is fixed — it can only disambiguate overloads
  introspection actually delivers. Whichever session merges last should make sure the §18.1 keying sentence
  and the §18.2 filename table land together and name the same helper.
- No ledger *override* row is needed for the key itself (nothing prior specified it); one **is** warranted
  if the BrowserPanel label format changes to disambiguate overloads visually, since the bare-`schema.name`
  top line is pinned by the 2026-08-01 ledger row at `CONSOLIDATED_SPEC.md:2035`.

---

## BUG-020: "See column in caption mode" applies an invisible preset filter — the grid is narrowed but no filter widget/header shows which column (or how) is filtered
**Status:** RESOLVED (2508d2a)
**Reported:** 2026-08-05
**Report (verbatim):** "When I come to Caption Management from BrowserPane (show column in caption mode), there's a filter applied. I can't see which columns are filtered and how. The applied filters should be just as visible as if they were applied manually"

**Root cause:** The Browser/tree "See column in caption mode" action funnels through
`main_window.py::MainWindow._on_tree_see_column_in_caption` (line 1291) →
`enter_caption_mode_for_field` (line 2387) →
`CaptionManagementPanel.filter_to_field(field_name, table_name)`
(`caption_management_panel.py:936`). `filter_to_field` (and its siblings
`filter_to_table` line 924 / `filter_to_table_details` line 928, reachable via
`enter_caption_mode_for_table_details`) apply the filter by calling
`self._proxy.set_row_predicate(lambda e: ...)` — the Phase C.2 preset **row-predicate**
mechanism on `_CaptionFilterProxyModel` (`caption_management_panel.py:336`,
`_row_predicate` / `filterAcceptsRow` at 449).

The row-predicate is a *third*, entirely invisible filter mechanism. The two
user-facing filters both have a visible representation:
  * **Header value filters** (`set_value_filter`, 364) notify the source model via
    `_notify_filtered_columns` → `_CaptionTableModel.set_filtered_columns` (189), which
    repaints the affected column header with the `_FILTER_INDICATOR` " ▼" marker plus
    bold font + accent foreground (`headerData`, 199–216).
  * **Whole-row find filter** (`set_regex_filter`, 348) is set through the shared
    Find/Filter/Replace modal and its pattern is retrievable via
    `current_filter_pattern()` (782) to pre-load the Replace dialog.

The preset **row-predicate** has none of that: `set_row_predicate` only calls
`self.invalidate()` (343) — it does not touch `set_filtered_columns`, has no header
marker, no status text, and no field the user can inspect. So on entry from the Browser
Pane the grid silently collapses to (e.g.) one `field_name` with zero on-screen
explanation of what was filtered or how. There is no inline filter QLineEdit/combo in the
panel at all (the old inline per-column filter row was removed — see spec §13), so a
lambda predicate is genuinely opaque.

Note there is also no single "manual" setter to funnel through here: unlike value/find
filters, a preset predicate is a semantic narrowing ("field = wbs_id") that no manual
gesture produces, so the fix must *add* a visible representation for it, not just reroute
to an existing widget.

**Proposed fix:** Give the preset row-predicate a visible, human-readable representation,
mirroring how value filters surface via `set_filtered_columns`. Concretely:

1. In `_CaptionFilterProxyModel` (`caption_management_panel.py:336`), change
   `set_row_predicate` to accept an optional human-readable **label** alongside the
   predicate, e.g. `set_row_predicate(predicate, label: str = "")`, and store
   `self._row_predicate_label`. Add a `row_predicate_label()` getter. Keep the existing
   single-arg call sites (`clear_all_filters` passes `None` → label `""`) working.
2. In the three preset entry points, pass a descriptive label built from the same
   arguments used for the predicate, so proxy + label stay in sync in one call:
     * `filter_to_field` (936): e.g. `Field = wbs_id` (or `Field = wbs_id  ·  Table = pr.equip`
       when `table_name` is given).
     * `filter_to_table` (924): `Table = pr.equip`.
     * `filter_to_table_details` (928): `Table = pr.att  (Detail embeds)`.
3. Surface the label in the panel UI. Add a small **active-filter banner** — a `QLabel`
   (styled like the changed/inconsistency accents already used, `_FILTER_HEADER_FOREGROUND`)
   inserted into the panel's `QVBoxLayout` (built at 654–656) **above** `self._table`,
   plus a compact "Clear" `QPushButton` wired to the existing
   `clear_all_filters()` (968). Show the banner (with text like
   `Filtered: Field = wbs_id — showing 3 of 214 rows`) whenever a preset predicate is
   active; hide it when the predicate is cleared. Update its visibility/text from the
   preset setters and from `clear_all_filters`. The row count can come from
   `self._proxy.rowCount()` / `self._model.rowCount()`.
4. Do NOT try to reuse the header ▼ indicator for the predicate — the predicate is not
   per-column (it keys on `field_name`/`table_name`, which map to the Anchor/Breadcrumb
   columns only loosely), so a banner is the correct surface; the header markers stay
   exclusive to `set_value_filter`.

Gotchas:
  * `clear_all_filters` (968) already calls `set_row_predicate(None)`; it must also hide
    the new banner. Keep it the single clear path.
  * `filter_to_field` calls `_select_first_visible_row()` after setting the predicate;
    compute/refresh the banner's row count *after* the proxy has been invalidated so the
    "showing N of M" count is correct.
  * Keep the label construction next to the predicate lambda in each of the three
    methods so the two never drift (the report's core complaint is exactly that the
    predicate and its visible description were out of sync — here, absent).

**Test impact:** `tests/ui/test_caption_management_panel.py` already covers the preset
predicates: `test_filter_to_table_shows_only_that_table` (1417),
`test_filter_to_table_details_shows_only_detail_rows` (1425),
`test_filter_to_field_shows_and_selects_matching_row` (1435),
`test_clear_all_filters_resets_everything` (1452), and the raw
`test_set_row_predicate_*` (1377–1416). Extend these (don't duplicate): after each
`filter_to_*` call assert the new banner is visible and its label/text reflects the
field/table, and after `clear_all_filters` assert the banner is hidden and
`row_predicate_label()` is `""`. If `set_row_predicate` gains a `label` param, update the
direct-call tests at 1381/1389/1400/1458 (they can keep passing just a predicate since
`label` defaults to `""`). In `tests/ui/test_main_window.py`,
`test_see_column_in_caption_filters_and_selects_row` (1290) should additionally assert the
panel's banner shows the field after `_on_tree_see_column_in_caption`.

**Spec impact:** Diverges from `CONSOLIDATED_SPEC.md` §13 "Grid" (lines 1114–1124), which
documents only the header value filter and the regex find filter as the panel's filtering
mechanisms — the Phase C.2 preset **row-predicate** (`set_row_predicate`) and its
Browser-Pane "See column in caption mode" entry path are not described there at all, and
the section explicitly notes the inline per-column filter row was removed. Flag for
spec-maintainer after the fix lands: document the preset row-predicate as a third filter
mechanism and its new visible active-filter banner in §13.

---

## BUG-021: Opening a project doesn't auto-open its linked `.pgtp` into the editor
**Status:** RESOLVED (704f87f) — the 2508d2a fix did not work; root cause was `QAction.triggered`'s `checked: bool` binding to `on_ready`, so `on_ready=False` passed the `is not None` guard and called `False()`. Fixed by lambda-wrapping both project actions and hardening the guards to `callable(on_ready)`; regression tests now drive the real signal via `action.trigger()`. Previously: REOPENED 2026-08-05, RESOLVED (2508d2a).
**Reported:** 2026-08-05
**Report (verbatim):** "at opening the project the pgtp should automatically open"

**Re-triage 2026-08-05 (post-2508d2a):** the fix landed but is dead code on the real menu path — see updated Root cause / Proposed fix / Test impact below. (Original triage line numbers were pre-merge; symbols were re-verified against current source this pass.)

**Root cause:** 2508d2a DID add the intended machinery — `MainWindow._auto_open_linked_pgtp` (`pgtp_editor/ui/main_window.py:2650-2680`) reads `settings.pgtp.working_copy_path`, calls the existing `open_project_file` loader, and handles the zero/one/multiple scope cases correctly — and `_open_ddl_project` (`main_window.py:2613-2648`) does call it. That code is correct in isolation and its unit test passes. **But it never runs from the real UI.** The bug is a Qt signal-argument mismatch in the menu wiring: `open_project_action.triggered.connect(self._open_ddl_project)` (`main_window.py:2064`). `QAction.triggered` emits a `checked: bool` argument, so when the user clicks **File → Open Project…**, Qt invokes `_open_ddl_project(False)` — i.e. `on_ready=False`, not `on_ready=None`. Inside `_open_ddl_project` (`main_window.py:2638-2648`) the guard is `if on_ready is not None:` — and `False is not None` is **True**, so control takes the `on_ready()` branch and calls `False()` (a `TypeError`), never reaching the `else:` branch that calls `_auto_open_linked_pgtp`. Net effect for the user: the project opens (active project set, drift reported, status bar message) but the linked `.pgtp` is never loaded into the editor — exactly the reported symptom. (`_new_ddl_project` at `main_window.py:2062` is wired the same way, `new_project_action.triggered.connect(self._new_ddl_project)`, and has the same latent `on_ready=False` defect, though its on_ready branch only affects the New Project → open-.pgtp chaining.)

**Proposed fix:** Stop letting the `QAction.triggered` boolean bleed into `on_ready`. Two acceptable shapes (pick one, apply consistently):
 1. **Wrap the connections** so the signal's `checked` arg is swallowed: `open_project_action.triggered.connect(lambda: self._open_ddl_project())` and `new_project_action.triggered.connect(lambda: self._new_ddl_project())` (`main_window.py:2062,2064`). This is the smallest change and keeps the `on_ready` default semantics intact.
 2. **Harden the guard** so a falsy non-callable can never be treated as a callback: change the signature to accept the stray positional (`def _open_ddl_project(self, _checked=False, on_ready=None)`) OR change the branch test from `if on_ready is not None:` to `if callable(on_ready):` at `main_window.py:2638`. Do the same for `_new_ddl_project`.
Prefer option 1 (lambda-wrap the connections) as the primary fix because it fixes the real defect at the source and matches how other argument-less action slots should be wired; optionally also apply the `callable(on_ready)` hardening at `main_window.py:2638` as defence in depth so a future direct/misconnected call can't silently swallow the auto-open again. Do NOT re-touch `_auto_open_linked_pgtp` — its zero/one/multiple logic is already correct.

**Test impact:** `tests/ui/test_ddl_project_wiring.py` — the existing `test_open_ddl_project_auto_opens_the_linked_working_copy` (line 217) is a **false positive**: it calls `window._open_ddl_project()` directly with no positional arg, so `on_ready=None` and auto-open fires; it never exercises the `QAction.triggered` signal path that passes `checked=False`, so it green-lit code that is dead in the app. Strengthen it (or add a sibling case) to invoke through the actual signal — e.g. locate the Open Project action and call `action.trigger()` (or `action.triggered.emit(False)`) with `getExistingDirectory` monkeypatched, then assert `window._current_project_path == str(working_copy)`. Add the equivalent signal-path case for New Project (`_new_ddl_project`) to lock in the parallel fix. `tests/ui/test_open_project.py` needs no change (it drives `open_project_file` directly and is unaffected).

**Spec impact:** §18.2 — clarify that opening a project auto-opens its linked working copy; flag for spec-maintainer after the fix lands.

---

## BUG-022: "Open Project" folder chooser shows files and accepts any folder as an (empty) project
**Status:** RESOLVED (2508d2a)
**Reported:** 2026-08-05
**Report (verbatim):** "when I choose a folder to open as a project, there's no project file, the entire folder is the project. so the Open dialogue should be a folder chooser dialoge not showing any files, just the folders. also Open should only be pressable if the folder is really a project folder"

*(Reconstructed from a background-triage report that was lost when a §18.3 merge from another worktree overwrote the working-tree queue file before this entry was committed. Line numbers are pre-merge and may have shifted — re-grep the named symbols.)*

**Root cause:** `MainWindow._open_ddl_project` (`pgtp_editor/ui/main_window.py`, ~2570) already uses `getExistingDirectory` (so it *is* a directory chooser), but without the `ShowDirsOnly` option (so files are shown) and with **no validity gate** — it calls `load_settings` unconditionally, which silently returns a default `ProjectSettings()` for any non-project folder. Note: the reporter's premise "there's no project file" is slightly off — a project folder *does* carry a marker (`.ddlproject/settings.json`); that marker is exactly what the Open gate should check.

**Proposed fix:** (1) Pass `QFileDialog.Option.ShowDirsOnly` to the picker so only folders show. (2) Add an `is_project_dir(path)` predicate in `pgtp_editor/db/ddl_project.py` that checks for the `.ddlproject/settings.json` marker, and after the pick reject folders lacking it (message + re-prompt/abort) instead of loading defaults. Note `getExistingDirectory` can't natively disable the accept button per-selection, so validate-after-pick is the pragmatic path.

**Test impact:** `test_open_ddl_project_on_a_brand_new_folder_gets_default_settings` (`tests/ui/test_ddl_project_wiring.py`, ~147) encodes the current buggy behavior and must be flipped to assert rejection of a non-project folder. Add a case for a valid project folder proceeding.

**Spec impact:** §18.2 — mechanism unchanged; optional one-line clarification that Open requires a valid project folder. Flag for spec-maintainer after the fix lands.

---

## BUG-023: Caption-mode "Unify: set all inconsistent siblings" gives no filtered-vs-project-wide scope choice when a filter is active
**Status:** RESOLVED (2508d2a)
**Reported:** 2026-08-05
**Report (verbatim):** "in caption mode when a filter is applied, and I select \"Unify: set all inconsistent siblings\" there should be a popup so I can decide if only apply to the filtered data or project-wide."

*(Reconstructed from a background-triage report that was lost when a §18.3 merge from another worktree overwrote the working-tree queue file before this entry was committed. Line numbers are pre-merge and may have shifted — re-grep the named symbols.)*

**Root cause:** `CaptionManagementPanel.unify_from_row` (`pgtp_editor/ui/caption_management_panel.py`, ~843-867) unconditionally iterates `self._model.entries()` (the whole project) and never consults `self._proxy`, so Unify **always** runs project-wide and there is currently no scope choice at all. The report's premise is slightly inverted: the requested popup is a new opt-in to *restrict* Unify to the visible/filtered rows, not a fix to a wrongly-scoped operation.

**Proposed fix:** In `unify_current`, when a filter is currently active, show a three-way prompt — **Filtered rows only / Entire project / Cancel** — mirroring the existing string-returning modal pattern `_confirm_close_xsd` (`main_window.py`, ~900-917). Add a `restrict_to` parameter to `unify_from_row` so it can iterate only the visible rows (via the proxy / `_visible_source_rows`) when the user picks "Filtered rows only". When no filter is active, keep current behavior (no prompt). IMPORTANT: the new modal must be monkeypatched in tests — never let a test reach an un-patched `QMessageBox`/`QDialog.exec`.

**Test impact:** `tests/ui/test_caption_management_panel.py` — extend the existing unify tests with filter-active cases for both scope choices and cancel (with the prompt patched).

**Spec impact:** `CONSOLIDATED_SPEC.md` §13 Grid/Unify (~line 1123) — document the new scope prompt. Flag for spec-maintainer after the fix lands.

---

## BUG-024: Standalone "Connection Setup…" is redundant/meaningless when a §18.2 project is open — should be projectless-mode only
**Status:** RESOLVED (2508d2a)
**Reported:** 2026-08-05
**Report (verbatim):** "database connection setup is obsolete as it's being defined in Project settings. It should only be visible when in projectless mode, otherwise the setup is meaningless"

**Root cause:** There are two independent connection stores. The standalone **Database ▸ Connection Setup…** action opens `ConnectionSetupDialog` (`pgtp_editor/ui/connection_setup_dialog.py`) via `MainWindow._open_connection_setup` (`pgtp_editor/ui/main_window.py:2529-2541`), which persists app-level QSettings through `save_connection(self._settings, dialog.params())` (single host/port/database/user/password profile). Separately, a §18.2 local project stores **its own** connection in `ProjectSettings` — a `target: ConnectionParams` and a `sandbox: ConnectionParams` (`pgtp_editor/db/ddl_project.py:115-116`), edited via `ProjectSettingsDialog` ("Target connection" / "Sandbox connection" groups, `pgtp_editor/ui/project_settings_dialog.py:75-91`). The `Connection Setup…` action is built unconditionally in `_build_database_menu` (`main_window.py:2511-2514`) as a plain local `setup_action` — it is **never stored on `self` and never enable/disable-gated on project state**, so it stays fully live even while a project is open. That makes it redundant with, and a silent shadow of, the project's own connection. It is meaningful only in Tier-1 standalone mode (spec §18 modes table, `CONSOLIDATED_SPEC.md:1455`), where Database Check / DDL Explorer read the app-level profile via `seed_params(tree, self._settings)` because there is no project. The app already tracks whether a §18.2 project is open via `self._ddl_project_folder` (set in `_set_active_ddl_project`, `main_window.py:2603-2608`; cleared in `_close_ddl_project`, `main_window.py:2682-2695`) — `_ddl_project_folder is None` is exactly "projectless mode".

**Proposed fix:** Gate the standalone connection action's enabled state on projectless mode, following the existing `_close_ddl_project_action` project-dependent-enablement pattern (which does the inverse: enabled while a project is open).
- In `_build_database_menu` (`main_window.py:2511`), stop discarding the action into a local `setup_action`; store it as `self._connection_setup_action = menu.addAction("Connection Setup…")`, keep the `.triggered.connect(self._open_connection_setup)` wiring, and set its initial enabled state to `self._ddl_project_folder is None` (True at startup, since no project is open then).
- Add a small central helper, e.g. `_refresh_project_dependent_actions()`, that sets `self._connection_setup_action.setEnabled(self._ddl_project_folder is None)`, and call it from **both** `_set_active_ddl_project` (right where `self._close_ddl_project_action.setEnabled(True)` is set, `main_window.py:2606`) and `_close_ddl_project` (alongside `self._close_ddl_project_action.setEnabled(False)`, `main_window.py:2693`). Optionally fold the existing `_close_ddl_project_action` toggles into the same helper so all project-state menu enablement lives in one place — but at minimum the connection action must flip in both transitions.
- Defensive guard in `_open_connection_setup` (`main_window.py:2529`): early-return (no dialog) when `self._ddl_project_folder is not None`, ideally with a status-bar hint like "Connection is defined in Project Settings while a project is open." This covers the two **internal** callers that auto-open the dialog on a missing connection — `_run_db_check` (`main_window.py:2900`) and `_open_ddl_explorer` (`main_window.py:2957`); with a project open those flows should point the user at Project Settings instead of the standalone dialog rather than opening a meaningless app-level setup. Gotcha: those two call sites currently expect `_open_connection_setup()` to do something visible on a missing host — reroute them (e.g. status-bar message directing to Project Settings, or open `_open_ddl_project_settings`) rather than silently no-opping, so the user isn't left with a dead "set one up first" message and no dialog.
- Decide (and document in the queue-resolution commit) the intended relationship, which this fix encodes: **in project mode the connection comes from `ProjectSettings` only** (`target`/`sandbox`); the app-level `save_connection`/`seed_params` profile is the standalone-mode store and is not touched while a project is open. Note that `_run_db_check`/`_open_ddl_explorer` still seed from `self._settings` today even in project mode — if the broader intent is that project-mode checks use the project's `target` connection, that is a larger change; this bug is scoped to hiding/disabling the redundant *setup UI*, so keep the seed-source change out of scope unless the resolver deliberately expands it (flag it if so).

**Test impact:** `tests/ui/test_database_menu.py` already covers the action's existence and `_open_connection_setup` (`test_database_menu_exists_with_connection_setup`, `test_open_connection_setup_seeds_from_project_and_holds_dialog`, `test_open_connection_setup_with_no_project`, `test_accepting_dialog_saves_connection`) — extend it with: (a) action enabled when no project is open; (b) action disabled after `_set_active_ddl_project(...)`; (c) re-enabled after `_close_ddl_project()`; (d) `_open_connection_setup()` no-ops / does not create `self._connection_dialog` while a project is active. Reuse the `_menu_helpers.find_action`/`find_top_menu` helpers. `tests/ui/test_ddl_project_wiring.py` already exercises `_set_active_ddl_project`/`_close_ddl_project` enablement (`test_new_ddl_project_becomes_the_active_project`, `test_close_ddl_project_clears_state_and_disables_action`) — the new central helper's calls slot naturally there; add connection-action assertions to those transitions rather than new fixtures. Keep the internal-caller reroutes covered where `test_ddl_explorer_wiring.py` / any db-check test drives the missing-connection branch. As always, patch any modal so a test never reaches a live `QDialog.exec`.

**Spec impact:** The §18 three-modes table (`CONSOLIDATED_SPEC.md:1455`, Tier 1 "A configured DB connection only") and the Database-menu descriptions (`CONSOLIDATED_SPEC.md:1297`, `:4160`) currently list "Connection Setup…" unconditionally and do **not** state that it is standalone/projectless-only — the always-available behavior appears to be incidental, not a documented intentional decision. This fix introduces a real behavioral rule (connection setup is projectless-only; in project mode the connection lives in Project Settings' `target`/`sandbox`). Diverges from the current unconditional-menu prose — flag for spec-maintainer after the fix lands to record the mode gating in §18 and the Database-menu section.

---

## BUG-025: Project Settings dialog is a single tall single-column stack — window is narrow and long, many fields unreadable
**Status:** RESOLVED (2508d2a)
**Reported:** 2026-08-05
**Report (verbatim):** "Project settings' window is narrow and long, many fields aren't readable. Project settings should be tabbed, each settings in its place."

**Root cause:** `ProjectSettingsDialog.__init__` (`pgtp_editor/ui/project_settings_dialog.py:56-150`) builds one top-level `QVBoxLayout` (line 141) and stacks every field group into it vertically (lines 142-148): the identity `QFormLayout`, then five `QGroupBox`es — `pgtp_group` (.pgtp link), `target_group` (Target connection, 5 rows), `sandbox_group` (Sandbox connection, 5 rows + a sandbox-mode radio sub-form), `git_group` (3 rows), and `deployed_group` (a `QTableWidget` + two buttons). Because this dialog deliberately exposes the ENTIRE project JSON (module docstring, lines 17-28), that is ~20 rows plus a table all in a single column with no width demand, so Qt sizes the window narrow (widest single label/field) and very tall (sum of all groups), pushing lower groups off-screen. There is no `QTabWidget`, no `resize()`/default size, and no grouping across columns/tabs — the single-column stack IS the bug. No spec section mandated this layout (see Spec impact), so it is an incidental layout choice, not an intentional decision.

**Proposed fix:** Introduce a `QTabWidget` in `__init__` and distribute the already-built groups across tabs; keep every widget object and its get/set wiring untouched (they are only reparented into tab pages). Concretely:
- Build the field-group widgets exactly as today (do not change `_build_connection_form`, `set_settings`, `settings`, `_set_connection_fields`, `_connection_from_fields`, or the deploy-manifest table methods — they reference widgets by `self._…` attribute, which survives reparenting).
- Create `tabs = QTabWidget(self)` and add four tabs (proposed names follow the real groupings):
  - **"General"** — the identity form (Name, Description) + `pgtp_group` (.pgtp link). Wrap the identity `QFormLayout` and `pgtp_group` in a `QWidget` page with a `QVBoxLayout`.
  - **"Connections"** — `target_group` and `sandbox_group` (the two `QGroupBox`es) on one page; these are the two 5-field connection profiles. Note `sandbox_group` already carries the sandbox-mode radios sub-form (lines 98-109) — it moves with the group intact.
  - **"Git"** — `git_group`.
  - **"Deploy manifest"** — `deployed_group` (the table + Add/Remove buttons); the table wants width, so it benefits most from its own tab.
- Replace the six `layout.addWidget/addLayout(...)` group lines (142-147) with a single `layout.addWidget(tabs)`, then keep `layout.addWidget(buttons)` (146→148) so the OK/Cancel `QDialogButtonBox` stays OUTSIDE the tab widget, below it.
- Add a sane default size at the end of `__init__`, e.g. `self.resize(560, 480)` (dialog stays resizable — do not use `setFixedSize`).

Gotchas: (1) OK/Cancel button box must remain a direct child of the top-level `QVBoxLayout`, not inside any tab. (2) There is currently NO cross-tab validation in this dialog (`accepted` just calls `self.accept`, line 138) — do not add any; but if a future field validation is added it must run on `accept` regardless of which tab is active, since a hidden tab's widgets still hold values. (3) All widgets are accessed by attribute (`self._name_edit`, `self._deployed_table`, etc.), so reparenting into tab pages does not break any external reference or the round-trip logic. (4) A `QGroupBox` already has a layout set in its constructor (e.g. line 70, 160); do not re-parent by re-assigning a layout — just `page_layout.addWidget(group)`.

**Test impact:** `tests/ui/test_project_settings_dialog.py` — every existing test reaches widgets purely by `self._…` attribute (e.g. `_name_edit`, `_target_host_edit`, `_deployed_table`, `_sandbox_mode_with_data_radio`) and the round-trip via `settings()`/`set_settings()`; none inspect the layout or assume a specific parent, so reparenting into tabs must keep them all green with no change. If any assertion ever calls `widget.isVisible()` (none do today), it would fail for a widget on a non-current tab — grep for `isVisible`/`isVisibleTo` before running and switch the active tab if needed. New case to add: assert `dialog.findChild(QTabWidget)` exists and exposes the four expected tab titles ("General", "Connections", "Git", "Deploy manifest"), and that a field on a non-default tab (e.g. `_git_server_edit`) is still populated by `set_settings` while that tab is not current.

**Spec impact:** §18.2 (project-settings dialog; the dialog is described at `CONSOLIDATED_SPEC.md` around the §18.2 "full JSON exposed for editing" framing, ~line 1414 / 1435) specifies WHAT the dialog exposes (the entire project JSON, all fields editable) but does NOT prescribe a layout (single-column vs tabbed). This is a pure UI-layout change that preserves the "whole JSON, nothing hidden" contract. Flag for spec-maintainer to add a one-line note that the dialog groups fields into tabs (General / Connections / Git / Deploy manifest) after the fix lands — no behavioral divergence.

---

## BUG-026: Database→XML flags lookup-only tables as red mismatches; per-table count should split into P/D/L roles
**Status:** RESOLVED (704f87f)
**Reported:** 2026-08-05
**Report (verbatim):** "in the Database->XML window those database tables that have multiple mentions but only as lookup tables are with red and counted as mismatch. The counter besides the table name should be separated in categories P for page, D for detail, and L for lookup. eg: (P3 D1 L2). Mismatches in red are only those tables that have all categories 0."

**Root cause:** Both reported symptoms trace to `check_db_against_xml` in `pgtp_editor/db/compare.py:127-153` and how it derives `TableCheck.ok` vs `TableCheck.invocations` from two DIFFERENT reference collectors that disagree about lookups:
- `ok` is computed as `table_name in columns_by_table` (line 147), where `columns_by_table = xml_table_columns(project)` (line 129). `xml_table_columns` (`compare.py:59-90`) walks ONLY page `table_name`s and (recursively) detail `table_name`s via its inner `add()` helper — it NEVER visits column-lookup targets (`column.lookup.attrib["tableName"]`). So a DB table referenced *only* as a lookup target is absent from `columns_by_table`, giving `ok=False`.
- `invocations` is computed from `xml_table_invocations` → `collect_table_usages` (`pgtp_editor/analysis/reused_tables.py:83-128`), which DOES record lookup references (see `visit_columns`, lines 96-106: each `column.lookup` with a `tableName` produces a `TableReference` of `kind="column"`, `ref_type in {"lookup","lookup with insert"}`). So the same lookup-only table gets `invocations >= 1`.
- Net effect: a lookup-only table renders red `✗` (because `ok=False`) yet shows a nonzero `(×N)` count — exactly the "multiple mentions but red / counted as mismatch" contradiction the report describes. In the UI, `DbCheckPanel._make_table_item` (`pgtp_editor/ui/db_check_panel.py:134-144`) picks the marker/color solely from `table.ok` (line 135, 139), and `_mismatch_count` (lines 95-104) counts `not table.ok` — so both the red styling and the header mismatch count inherit the wrong `ok`.

Second half of the report (role-split count) is a display gap, not a bug in isolation: `invocations` is a single aggregate `int` (`TableCheck.invocations`, `compare.py:55`), rendered as `(×N)` in `_make_table_item` line 137. The per-role data to split it (P/D/L) already exists — `collect_table_usages` returns per-reference `kind` ("page"/"detail"/"column") and `ref_type` — it is simply collapsed to `len(usage.breadcrumbs)` by `xml_table_invocations` (`compare.py:93-95`).

**Proposed fix:** Two coordinated changes — the compare model (roles + corrected `ok`) and the panel render.

1. `pgtp_editor/db/compare.py`:
   - Add a role-split count helper alongside `xml_table_invocations`, e.g. `xml_table_role_counts(project) -> dict[str, dict[str, int]]` mapping `tableName` → `{"page": n, "detail": n, "lookup": n}`. Derive it from `collect_table_usages`: for each `TableUsage`, tally its `references` by `ref.kind` — `kind=="page"` → page bucket, `kind=="detail"` → detail bucket, `kind=="column"` → lookup bucket (a column reference is by construction a lookup; `visit_columns` only emits column refs for `column.lookup is not None`). Keep the aggregate `xml_table_invocations` for back-compat (its own test still asserts it).
   - Add three fields to `TableCheck` (`compare.py:50-56`): `page_count: int = 0`, `detail_count: int = 0`, `lookup_count: int = 0` (defaulted so `check_xml_against_db` need not be touched unless desired). Populate them in `check_db_against_xml` from the new helper (fall back to zeros when the table has no usage). `invocations` may stay as-is (aggregate) or be dropped in favor of the sum — prefer keeping it to avoid churn; the panel will stop displaying it.
   - Fix the mismatch semantics: in `check_db_against_xml`, a DB table is a genuine mismatch ONLY when it is referenced in NO role. Change `ok=table_name in columns_by_table` (line 147) to `ok = (page_count + detail_count + lookup_count) > 0`. This makes lookup-only tables `ok=True` (no longer red), page/detail tables stay `ok=True`, and truly-unreferenced tables stay `ok=False`. GOTCHA: `ok` here is also read by `_make_column_item`/child logic? No — column `ok` is separate (`column.name in xml_columns`); leave `columns_by_table`/`xml_table_columns` untouched, they still correctly drive per-column present/absent (a lookup-only table legitimately has all-absent columns on the XML side, which is fine and informational). Only the TABLE-level `ok` changes.
2. `pgtp_editor/ui/db_check_panel.py`:
   - In `_make_table_item` (line 137) replace the `(×{table.invocations})` suffix with a role-split string `(P{page_count} D{detail_count} L{lookup_count})` — matching the report's `(P3 D1 L2)` shape (no `×`). Build from the new `TableCheck` fields. Consider showing the suffix only in the `db_to_xml` direction if `check_xml_against_db` does not populate the role fields; simplest is to always render and let XML→DB show `(P0 D0 L0)` — but confirm whether XML→DB should show role counts at all (it currently shows `(×N)`); to be safe, keep the existing `(×N)` for `xml_to_db` and use the P/D/L form only when `self._direction == "db_to_xml"`.
   - The red/mismatch styling in `_make_table_item` (line 139) and the header count in `_mismatch_count` (line 98) both key off `table.ok`, so once `compare.py` sets `ok` correctly they need NO further change — the report's "red only when all categories 0" falls out automatically. Verify this rather than adding a second condition in the panel (avoid two sources of truth for "is this a mismatch").
   - GOTCHA: the UserRole 4-tuple `("table", name, ok, False)` (line 143) drives the "Show only mismatches" filter and the create-menu; leaving `ok` as the single mismatch signal keeps all of that consistent — do NOT introduce a separate "role counts" mismatch flag.

**Test impact:** `tests/db/test_compare.py` — `test_check_db_against_xml_directions` (line 228) currently asserts `v.ok is False` / `v.invocations == 0` for an unreferenced view; add a case where a table is referenced ONLY via a column lookup and assert `ok is True` with `lookup_count >= 1` and `page_count == detail_count == 0` (this is the regression the report describes). `test_xml_table_invocations_counts_references` (line 86) covers the aggregate; add a sibling for the new `xml_table_role_counts` asserting the P/D/L split against a project mixing a page, a detail, and a lookup on the same table. `tests/ui/test_db_check_panel.py` — `test_table_row_shows_kind_and_invocation_count` (asserts `"(×2)"`, line ~58) must change to assert the new `(P… D… L…)` text for `db_to_xml`; `test_show_only_mismatches_filters` (line 111) and `test_header_shows_direction_connection_and_mismatch_count` (line 97) should gain a lookup-only `TableCheck` fixture (`ok=True`, `lookup_count>0`) and assert it is NOT red / NOT in the mismatch count. Any test constructing `TableCheck(...)` directly (e.g. the `_checks()` helper) may need the new count kwargs — they are defaulted, so only tests asserting the new display must set them.

**Spec impact:** Diverges from CONSOLIDATED_SPEC §26 Database-check description (~lines 1305-1316 and 1333-1335). Two documented facts change: (1) `db/compare.py` line ~1306 lists `TableCheck{name, ok, kind, invocations, columns}` — gains `page_count`/`detail_count`/`lookup_count`, and `check_db_against_xml`'s table-level `ok` semantics change from "table name appears among page/detail bindings" to "referenced in any role (page, detail OR lookup)". (2) The UI line ~1334 says the tree shows "`(×N)` invocation counts" — becomes role-split `(P# D# L#)` in the DB→XML direction, and the red-mismatch rule for DB tables is redefined as "no reference in any role." Flag for spec-maintainer AFTER the fix lands; do not edit the spec here.

---

## BUG-027: Customize Toolbar offers only 7 hardcoded commands, not all menu items
**Status:** RESOLVED (704f87f)
**Reported:** 2026-08-05
**Report (verbatim):** "customize toolbar is unfinished, the choice should be all menu items, but it's very limited to a few items."

**Root cause:** The Customize Toolbar dialog's "Available" list is sourced from a hardcoded 7-entry list, not from the app's menus. `pgtp_editor/ui/toolbar_registry.py:24` defines `AVAILABLE_COMMANDS = [("open","Open"),("save","Save"),("undo","Undo"),("redo","Redo"),("find","Find"),("validate","Validate"),("generate","Generate")]`. `MainWindow._open_customize_toolbar` (`pgtp_editor/ui/main_window.py:1056`) passes that exact list into `CustomizeToolbarDialog(AVAILABLE_COMMANDS, self._toolbar_ids, self)`, and `MainWindow._build_toolbar` (`main_window.py:972`) wires each id to a slot via the hardcoded `self._toolbar_slots` dict (lines 983-991) with `_apply_toolbar_ids` (line 1009) building a fresh `QAction(label_for(command_id), self)` and connecting `self._toolbar_slots[command_id]`. So the toolbar system is a closed 7-command universe that has nothing to do with the actual menus. Meanwhile every real command is created independently in the `_build_*_menu` methods (`_build_file_menu` line 2051, `_build_edit_menu` 2090, `_build_view_menu` 2151, `_build_schema_menu` 2495, `_build_database_menu` 2516, `_build_tools_menu` 3458, `_build_bookmarks_menu` 3480, `_build_generation_menu` 3512, `_build_help_menu` 3867) as local `menu.addAction("…")` QActions connected directly to slots — these are never registered anywhere the toolbar can see them. Result: the dialog physically cannot offer them. This matches the "Sub-project E" design (the registry docstring and CONSOLIDATED_SPEC §7 both describe a fixed registry), so the limitation is intentional-but-incomplete, not an accidental regression.

**Proposed fix:** Make the available-actions set the full menu action set instead of the static registry.
- **Enumerate menu actions.** Add a `MainWindow` method (e.g. `_all_menu_commands()`) that walks `self.menuBar().actions()`, and for each top-level action recurses into `action.menu()` submenus, collecting every leaf QAction where `not act.isSeparator()` and `act.menu() is None` (skip separators and submenu placeholders). Build the menu-path label from the ancestor menu titles (e.g. `"File › Save As..."` or `"Edit › Find..."`), stripping the `&` mnemonic markers and trailing `…`/`...`. This must run AFTER all `_build_*_menu` calls in `__init__` (menus must already exist). NOTE the current build order populates the toolbar in `_build_toolbar`; ensure `_build_toolbar`'s restore path still works when the available set is menu-derived (see identity note below) — either build the toolbar after the menus, or defer the available-set computation to `_open_customize_toolbar` (dialog open is the only place it's needed for display; the restore path only needs id->action resolution).
- **Stable identity for persist/restore.** The saved config is an ordered id list in QSettings key `toolbarIds` (written by `_save_toolbar_ids` line 1046, read by `_restore_toolbar_ids` line 995). Menu QActions currently have NO `objectName` (they're created as locals like `save_action = menu.addAction("Save")`), so there is no stable key to persist. Fix: give each command a stable id and a way to resolve id->QAction. Two viable shapes — pick one and apply consistently:
  1. Set `objectName` on every menu QAction at creation in the `_build_*_menu` methods (e.g. `save_action.setObjectName("file.save")`), then enumerate/persist by `objectName`; `_apply_toolbar_ids` resolves id->action by scanning the collected menu actions and calls `toolbar.addAction(existing_action)` (reuse the real QAction so the toolbar button triggers the SAME slot and reflects enabled-state, instead of building a parallel QAction + slot lookup). This is the cleanest and lets the toolbar button inherit each action's icon/enabled state automatically.
  2. If touching every `_build_*` method is too invasive for one pass, derive a synthetic stable id from the menu path + action text (e.g. `"file/save-as"`), keep an id->QAction dict rebuilt on each enumeration, and persist those synthetic ids. GOTCHA: synthetic ids break if a menu label is later renamed; `objectName` (option 1) is more durable — prefer it.
- **Back-compat with saved configs.** Existing installs have `toolbarIds` = subset of the OLD ids (`open,save,undo,...`). `_restore_toolbar_ids`/`valid_ids` (`toolbar_registry.py:50`) currently drop unknown ids. Keep the 7 legacy ids resolvable: map the old registry ids to the corresponding new action ids (e.g. `open`->`file.open`, `save`->`file.save`, `undo`->`edit.undo`, `redo`->`edit.redo`, `find`->`edit.find` [note: menu label is "Find..." and slot `_show_find_bar`], `validate`->the Validate action, `generate`->the Generate action). Do this with an alias table applied in `_restore_toolbar_ids` so old saved toolbars survive the widening; otherwise every existing user's toolbar silently empties to the default on first launch.
- **Icons.** `_set_action_icon`/`icons.ACTION_ICON_FILES` (`pgtp_editor/ui/icons.py:32`) only has SVGs for the 7 legacy ids. If reusing real QActions (option 1) the toolbar button shows whatever icon the action already has (mostly none) — that is acceptable (text-beside-icon style already tolerates missing icons; `_set_action_icon` swallows misses). Do NOT require a new icon per command — keep icons optional so ALL menu commands can be added regardless of icon availability.
- **Exclusions to call out.** Skip: separators; submenu placeholder actions (`act.menu() is not None`), including the dynamic "Open Recent" submenu (`_build_file_menu` line 2056) — its per-file children are transient/session-specific and must NOT be offered on the toolbar; and the "Customize Toolbar…" action itself is harmless to include but is naturally already reachable. Checkable View-menu dock toggles (Project Tree, Properties Panel, Audit/Problems, Raw XML Panel — `_build_view_menu` lines 2161-2193) CAN be offered (they're real toggle actions) and reusing the real QAction (option 1) keeps their checked-state in sync on the toolbar. Window-level actions not in any menu (e.g. `_goto_xsd_action` added via `self.addAction`, `main_window.py:2513`) are optional — they won't appear via `menuBar()` enumeration; leave them out unless trivially added, and note that "all MENU items" (the report's words) is satisfied by the menuBar walk.
- Update `CustomizeToolbarDialog` (`pgtp_editor/ui/customize_toolbar_dialog.py:36`) — no structural change needed; it already takes `available` as `(id,label)` pairs and shows all of them in registry/passed order with on-toolbar ones disabled (`set_ids`, line 85). Just pass the full menu-derived pair list instead of `AVAILABLE_COMMANDS`. Consider grouping/labeling by menu path in the label text (the dialog shows the label verbatim) so the long list stays scannable.

**Test impact:** `tests/ui/test_toolbar_registry.py` — `test_available_commands_content_and_order` (line 11) hardcodes the 7-tuple and WILL fail once the set widens; it must be rewritten (or the registry repurposed/removed if the source moves to a `MainWindow._all_menu_commands()` method — if so, delete registry-content assertions and add a `MainWindow`-level test that enumerating menus yields >7 commands including e.g. "Save As...", "Replace...", "Edit XSD"). `tests/ui/test_customize_toolbar_dialog.py` — exercises the dialog against a passed available list; extend with a case proving a large (menu-derived) list renders and add/remove/reorder still works; keep using the `selected_ids()`/`set_ids()` seams, never `.exec()`. `tests/ui/test_toolbar.py` — covers `_apply_toolbar_ids`/`_restore_toolbar_ids`/`_save_toolbar_ids` persistence; add: (a) a back-compat case where QSettings holds an OLD legacy id list and asserts the toolbar still populates the corresponding actions after the alias mapping; (b) a case adding a previously-unavailable menu command (e.g. "Save As...") and asserting it appears on the toolbar and triggers the right slot. Monkeypatch any modal calls per CLAUDE.md.

**Spec impact:** Diverges from CONSOLIDATED_SPEC §7 (~lines 512-516): "a `QToolBar` driven by a stable action-id registry (`toolbar_registry.py`). Default set: Open, Save, Undo, Redo, Find, Validate, Generate ... The Available list shows all registry commands in registry order." The available set becomes "all menu commands" rather than "all registry commands," and the id source moves from the static registry to a menuBar walk (registry may be reduced to a default-set + legacy-alias definition, or removed). Also touches §7's Supersession Ledger row dated 2026-07-20 ("Toolbar Available = registry-minus-present"/"Available = all commands, present ones disabled"). Flag for spec-maintainer AFTER the fix lands; do not edit the spec here.

---

## BUG-028: Caption-mode Find filter isn't shown in the active-filter banner — user can't see the find text or which columns it applies to
**Status:** RESOLVED (704f87f)
**Reported:** 2026-08-05
**Report (verbatim):** "Caption mode when filtered using Find doesn't show which columns have been the filter applied to. The same mechanism as when coming from Browser pane should be applied."

**Root cause:** The caption panel has three ANDed filter mechanisms on `_CaptionFilterProxyModel` (`pgtp_editor/ui/caption_management_panel.py:314`): (1) per-column header **value filters** (`set_value_filter`, 384) which DO paint a visible " ▼" header marker via `_notify_filtered_columns` → `_CaptionTableModel.set_filtered_columns`; (2) the whole-row **find filter** (`set_regex_filter`, 368, applied through the public `apply_find_filter`, 831, from the shared Find/Filter/Replace modal); and (3) the preset **row-predicate** (`set_row_predicate`, 344), the Browser-Pane "See column in caption mode" entry path.

BUG-020 (RESOLVED 2508d2a) added an active-filter **banner** — the `QLabel` `self._filter_banner_label` inside the `QWidget` `self._filter_banner` (built at 693–708), with a "Clear" button wired to `clear_all_filters` — refreshed by `_refresh_filter_banner` (1097). But that banner is keyed *only* on the preset row-predicate: `_refresh_filter_banner` reads `self._proxy.row_predicate_label()` (1105) and hides the banner whenever that label is empty (1106–1108). It never consults the find filter. Two concrete gaps result:

  * `apply_find_filter` (831) calls `self._proxy.set_regex_filter(...)` and returns — it never calls `_refresh_filter_banner`, so applying a find filter shows nothing in the banner even though `set_regex_filter` narrows the grid.
  * Even if it did refresh, `_refresh_filter_banner` has no branch that renders a find description. So the user gets a narrowed grid with no on-screen statement of the find text, its search mode/case, or its scope.

Scope, for the banner text: the find filter is **whole-row** — `_passes_find_filter` (421) accepts a row iff `matches()` is true for ANY column across `range(model.columnCount())` (427–438), under one of the three `caption_scan.SEARCH_MODES` ("normal" / "extended" / "regular", `caption_scan.py:244`) plus a case flag. So it targets *all displayed columns*, not a subset — the honest banner statement is "searches all columns" (the report's mental model of "which columns" resolves to "every column" for this filter, which is itself the useful thing to surface). The proxy already exposes `find_pattern()` (381); `_find_mode`/`_find_case` are stored (333–334) but have no public getters yet.

**Proposed fix:** Extend BUG-020's *existing* banner to also represent an active find filter — do NOT add a parallel indicator. This builds directly on the shipped BUG-020 banner infrastructure (`self._filter_banner`, `_filter_banner_label`, `_refresh_filter_banner`, `clear_all_filters`); no ordering dependency remains since BUG-020 is already RESOLVED (2508d2a). Concretely:

1. Make `apply_find_filter` (`caption_management_panel.py:831`) call `self._refresh_filter_banner()` after `set_regex_filter` succeeds, so applying/clearing a find filter drives the banner the same way the preset setters already do (they each call `_refresh_filter_banner`, e.g. 1033/1043/1059).
2. Rework `_refresh_filter_banner` (1097) to build its text from BOTH sources and show the banner if EITHER is active:
   * preset label via `self._proxy.row_predicate_label()` (as today);
   * find description when `self._proxy.find_pattern()` is non-empty, e.g. `Find "ord" (all columns)` — include mode/case when not the default, e.g. `Find /^Ord$/ (regex, case-sensitive, all columns)`. To get mode/case, add small getters on `_CaptionFilterProxyModel` mirroring `find_pattern()` (381): `find_mode()` / `find_case()` returning `self._find_mode` / `self._find_case` (don't read the private attrs from the panel).
   * When both a preset predicate AND a find filter are active, join the two descriptors (e.g. `Field = wbs_id  ·  Find "ord" (all columns)`) using the same `·` separator style `filter_to_field` already uses for its combined label (see BUG-020 label format `Field = wbs_id  ·  Table = pr.equip`).
   * Keep the trailing `— showing {visible} of {total} rows` count (1111–1113); `visible = self._proxy.rowCount()`, `total = self._model.rowCount()` still hold with find active.
   * Hide the banner only when NEITHER the preset label NOR a find pattern is present.
3. `clear_all_filters` (1118) already clears the find filter (`set_regex_filter("", …)`, 1122) and then calls `_refresh_filter_banner` (1126), so once step 2 makes the banner find-aware, the existing single clear path (and the "Clear" button / "Clear all filters" context action at 1173) correctly hides it for find filters too. No change needed there beyond step 2. Do NOT introduce a second clear path.

Gotchas:
  * The find filter is whole-row — do not try to paint a per-column header ▼ marker for it (that surface stays exclusive to `set_value_filter`, exactly as BUG-020 decided for the predicate). The banner is the correct and only surface for "which columns": state "all columns".
  * Header **value filters** (mechanism 1) are still deliberately NOT represented in the banner (they have their own header marker); this fix only adds the find filter, matching the report. Leave value-filter banner behavior unchanged.
  * `set_regex_filter` validates the regex and can raise `ValueError`; only call `_refresh_filter_banner` after it returns normally (put the refresh in `apply_find_filter` after the proxy call, not inside a `try` that swallows).

**Test impact:** `tests/ui/test_caption_management_panel.py`. Existing find-filter tests to extend (don't duplicate): `apply_find_filter` cases around lines 446/459/472–473/904/935/943/1263 and the raw `set_regex_filter` cases (577/1370/1508). Add assertions that after `apply_find_filter("ord", "normal", False)` the banner is visible (`panel._filter_banner.isVisibleTo(panel)`) and `panel._filter_banner_label.text()` states the find text + "all columns" (and mode/case for the regex/case-sensitive variant at 459); that clearing the pattern (`apply_find_filter("", …)`, cf. 473) hides the banner when no preset predicate is active; and a combined case: apply a preset (`filter_to_field`) AND a find filter, assert the banner shows both descriptors, then `clear_all_filters` hides it. Extend `test_clear_all_filters_resets_everything` (1599) — it already sets a regex filter (1603) and asserts the banner hides (1617) — to also assert the banner was visible *because of the find filter* before clearing (currently it's visible only due to the preset it also sets). If getters `find_mode()`/`find_case()` are added, add trivial getter tests near the existing `find_pattern` usage.

**Spec impact:** Same section BUG-020 flagged — CONSOLIDATED_SPEC §13 "Grid" (~lines 1114–1124). BUG-020's spec follow-up documents the preset row-predicate + banner as a filter surface; this extends that surface to also represent the whole-row find filter (find text, mode/case, "all columns" scope). Flag for spec-maintainer AFTER the fix lands, folded into the same §13 banner description; do not edit the spec here.

---

## BUG-031: Project Status window cannot be reopened after being closed — menu silently does nothing
**Status:** RESOLVED (ec03946) — reuse branch now calls `show()` + unminimizes before `raise_()`/`activateWindow()`. The reuse-path re-probe proved load-bearing (`showEvent` probes only on first show), so a reopened window would otherwise show stale state; now covered.
**Reported:** 2026-08-06
**Report (verbatim):** "once the window is closed it cannot be opened again, clicking the menu silently does nothing."

**Root cause:** Cached-singleton + missing re-`show()` on the reuse path — a lifecycle bug in `pgtp_editor/ui/main_window.py::MainWindow._open_project_status` (lines 3382–3427), the handler for the **Database ▸ "Project Status…"** menu action (built at `main_window.py:2683–2684`, `project_status_action = menu.addAction("Project Status…")` wired to `lambda: self._open_project_status()`). The window instance is a `ProjectStatusPanel` (`pgtp_editor/ui/project_status_panel.py:421`, `class ProjectStatusPanel(QWidget)`) cached on `self._project_status_window` (declared `= None` at `main_window.py:256–258`, comment: "kept so re-invoking the menu entry ...").

First open (lines 3399–3427): `existing = self._project_status_window` is `None`, so a fresh `ProjectStatusPanel` is constructed, made a top-level window (`panel.setWindowFlag(Qt.WindowType.Window, True)`, line 3423), and shown (`panel.show()`, line 3427). Two things are wired that are meant to make it single-instance-and-reopenable:
  * line 3425: `panel.destroyed.connect(lambda: setattr(self, "_project_status_window", None))` — intended to reset the cache when the window goes away.
  * lines 3391–3397, the reuse branch: `if existing is not None:` re-probe, `existing.set_diagram(...)`, `existing.raise_()`, `existing.activateWindow()`, `return`.

The defect is that closing the window (OS window-frame ✕) **hides but does not destroy** the panel, so the two mechanisms above never engage:
  1. `ProjectStatusPanel.__init__` (`project_status_panel.py:456–544`) never sets `WA_DeleteOnClose`, and Qt's default for a top-level widget is `WA_DeleteOnClose = False`. (The one `setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)` in this file, `project_status_panel.py:360`, is on the *inner* `NodeWindow` click-through dialog, **not** on the panel — a red herring.) There is no `closeEvent` override on `ProjectStatusPanel`. So a close just hides the widget; the C++/Python object stays alive.
  2. Because it is not destroyed, `QWidget.destroyed` never fires, so the line-3425 lambda never runs and `self._project_status_window` **stays pointing at the still-alive, now-hidden panel** — it is never reset to `None`.
  3. Next menu click: `existing is not None` is `True` (it's the hidden panel), so the reuse branch runs `refresh()` / `set_diagram()` / `raise_()` / `activateWindow()` and returns — but **never calls `show()`/`setVisible(True)`**. `raise_()`/`activateWindow()` on a hidden window are no-ops with no visible effect and no error. Result: the menu silently does nothing, for the rest of the session. (This is the classic cached-instance + never-reset-on-close variant, not a GC / dangling-deleted-object variant: the object is very much alive, just hidden and never re-shown.)

The spec's stated intent (see Spec impact) is "single-instance (re-invoking raises the existing one)" — so keeping the instance and re-raising is *by design*; the bug is purely the missing re-show for the closed/hidden case. `_open_project_status` is the only cached-singleton reopenable window in `main_window.py`; every other `.show()` there (e.g. lines 1217, 2400, 3092, 3451) constructs a fresh local `dialog` each call and has no reuse branch, so there is no in-app sibling pattern to copy — the fix is self-contained to this handler.

**Proposed fix:** In `pgtp_editor/ui/main_window.py::_open_project_status`, make the reuse branch (lines 3391–3397) actually bring a hidden window back on screen, keeping the documented single-instance behavior. Minimal, robust change — add `show()` and (defensively) unminimize before raise/activate:
```python
existing = self._project_status_window
if existing is not None:
    self.refresh_project_capability_status()
    existing.set_diagram(self._build_project_status_diagram())
    existing.show()                                   # NEW: re-show if it was closed/hidden
    existing.setWindowState(
        existing.windowState() & ~Qt.WindowState.WindowMinimized
    )                                                  # NEW: restore if minimized
    existing.raise_()
    existing.activateWindow()
    return
```
`show()` on an already-visible window is harmless (Qt no-ops), so this also covers the "re-invoke while still open" case the spec describes. Gotchas / things easy to get wrong:
  * Do **not** "fix" this by adding `WA_DeleteOnClose = True` to the panel and relying solely on the destroyed→None reset to force a fresh window each time. That is a valid *alternative* shape, but it (a) discards the re-probe-and-reuse design the spec explicitly documents ("raises the existing one"), (b) would make the line-3425 `destroyed` lambda the load-bearing reset and must be verified to fire under the offscreen test platform, and (c) changes the identity semantics the existing `on_refresh`/`_refreshed_on_show` seam (`project_status_panel.py:625–630`) relies on. Prefer the re-`show()` fix above; it is the smaller, intent-preserving change.
  * Keep the existing re-probe (`refresh_project_capability_status()` + `set_diagram(...)`) in the reuse branch — a window reopened after the sandbox died must reflect current state (that is the whole point of the docstring at lines 3383–3389). Note `ProjectStatusPanel.showEvent` only re-probes on the *first* show (`_refreshed_on_show` guard, `project_status_panel.py:628`), so the explicit reuse-branch re-probe is still required on every reopen and must not be removed.
  * The line-3425 `destroyed` reset stays as-is — it is still correct for the real teardown path (app close / parent destruction), just not exercised by an ordinary window close.

**Test impact:** No existing test covers the open→close→reopen lifecycle. `tests/ui/test_ddl_creation_wiring.py::test_database_menu_offers_new_function_procedure_and_project_status` (line 153) only asserts the menu entry exists; `tests/ui/test_project_capability_wiring.py` covers the capability probe, not the window; `tests/ui/test_project_status_panel.py` unit-tests `ProjectStatusPanel` in isolation (no MainWindow reuse path). Add a new lifecycle case, most naturally in `tests/ui/test_ddl_creation_wiring.py` (it already builds a MainWindow and reaches `_open_project_status`) or a new `tests/ui/test_project_status_wiring.py`: call `win._open_project_status()`, assert `win._project_status_window is not None` and `.isVisible()`; call `win._project_status_window.close()` and assert it is hidden but the attribute is still non-None (documents that close does not destroy); call `win._open_project_status()` again and assert the **same** panel instance is back and `.isVisible()` is `True` again (the regression lock — this is what silently fails today). Keep any `QMessageBox`/`QDialog.exec` off the path (the panel is non-modal `show()`, so no modal patching needed, but the re-probe seam `on_refresh` may touch the sandbox probe — reuse whatever probe stub `test_project_capability_wiring.py` already injects rather than hitting a real DB).

**Spec impact:** CONSOLIDATED_SPEC §18.8 ("The Project Status window", line 4721; status block line 4729–4731) explicitly documents the intended behavior: "the window is non-modal and single-instance (re-invoking raises the existing one)". The shipped code diverges from this — re-invoking after a close does **not** re-raise, it silently no-ops. This is a code-vs-spec bug (implementation fails to meet the documented design), not a design change, so no new design decision is needed. After the fix lands, flag `spec-maintainer` only if §18.8's wording should be sharpened to state that a **closed** (not just backgrounded) window reopens/re-shows — the current "raises the existing one" phrasing is arguably already satisfied by the fix and may not need editing.

---

## BUG-029: Project Status window PNGs are clipped and blurry ("cut and very low resolution")
**Status:** RESOLVED (acb813f) — root cause was BOTH halves the entry named. Blur: the pipeline MAGNIFIED small rasters (2x at dpr 1.0, 4x on HiDPI), which cannot add detail. Now rendered from the owner-supplied SVGs through `QSvgRenderer` into a `QImage` sized `logical x dpr`. Logical size is `defaultSize() * 2.133`, not `defaultSize()` raw — Qt reads these SVGs' millimetre dims at 90 dpi while the deleted PNGs were 96 dpi exports of the same drawing, so the 96/90 correction keeps every size within 1-2 px of the old layout. Clipping: pad is now `box.expandedTo(icon)` with the `max(0, ...)` clamps removed, ONE dpr threaded `_rebuild`->`_make_node`->`_boxed_pixmap`, connector labels ceil-sized with AlignCenter, and a `devicePixelRatioChanged`/`screenChanged` rebuild. The 1px drift class is gone as a clipping cause (`_logical_size` ceils). Packaging verified: pyproject's `resources/status/*` glob is extension-agnostic, so SVGs ship.

**Remaining ASSET issue, needs the owner (no code fix will follow):** `resources/status/sandbox_offline.svg` is not an SVG — it is a 40x34 PNG saved under an `.svg` name. `QSvgRenderer` rejects it, which would have left the offline sandbox node a blank gap, so `_scaled_pixmap` falls back to raster loading at 2x for non-SVG content. That one state therefore renders SOFT while its `_drk` counterpart (a real SVG) is crisp. Re-export it as true SVG and it becomes crisp with no code change. Cosmetic aside: `sandbox_not_set_up.svg` is 41x31 vs its dark twin's 37x32, so the light icon is ~10% wider; alignment is unaffected.
**Reported:** 2026-08-06
**Report (verbatim):** "PNGs are cut and very low resolution."

**Root cause:** Two compounding problems, both in `pgtp_editor/ui/project_status_panel.py` feeding off the bundled raster assets under `pgtp_editor/resources/status/`.

1. **Low resolution (blurry) — the assets are tiny rasters that get *upscaled*.** The bundled PNGs are exported at very small pixel sizes (verified on disk): Quality nodes 36×72, App nodes 48×38, Sandbox 40×35, Sandbox1 20×20, Sandbox2 29×27, connectors as small as 23×5 / 36×5. `_scaled_pixmap()` (lines 171–192) loads the source with `QPixmap(str(path))`, then unconditionally *magnifies* it to `source.size() * ASSET_SCALE (=2.0) * dpr` via `QPixmap.scaled(..., SmoothTransformation)` (lines 182–190). Even at `dpr=1.0` that is a 2× upscale of a ~36px raster; on a HiDPI screen (`dpr=2.0`) it is a 4× upscale. Smooth-scaling a small raster past its native size cannot add detail — the result is inherently soft/blurry. This is the "very low resolution" symptom and it is a **source-asset problem**, not just a code bug: `ASSET_SCALE = 2.0` (line 104) exists precisely because "the bundled art is small (20–72 px tall)". A crisp render needs the art supplied at (or rendered to) the actual displayed pixel size. The repo already carries the vector master `pgtp_editor/resources/status/000source.svg` (a full-page 210×297mm Inkscape drawing the individual PNGs were sliced from), so higher-fidelity output is achievable without new art from the owner.

2. **Clipping ("cut") — the centering box can be smaller than the boxed pixmap, and `_boxed_pixmap` hard-clamps the paint offset to `max(0, …)`.** `_boxed_pixmap()` (lines 203–225) paints the scaled icon into a transparent pad of size `box` at offset `(max(0,(box.w - size.w)//2), max(0,(box.h - size.h)//2))`. When the scaled icon is *larger* than `box` in either axis, the offset is clamped to 0 and the overflow past `box.width()/height()` is silently cut off (the `QPainter` clips to the pad pixmap). `box` is built in `_make_node()` (line 762) as `QSize(NODE_WIDTH - 8, box_h)` = `QSize(108, box_h)`. Two ways the icon exceeds that box:
   - **Height axis:** `box_h` is the *logical* height of the tallest icon in the row (`chain_box_h`/`branch_box_h`, lines 668–674, from `_logical_size`). But `_logical_size` (195–200) divides device pixels by DPR, while `_scaled_pixmap`'s target uses `round(source.h * ASSET_SCALE * dpr)` — the two roundings do not always invert cleanly, so a pixmap's logical height can come out 1px taller than `box_h`, shaving the icon's bottom/top edge.
   - **DPR mismatch between build and paint:** `_scaled_pixmap` builds every pixmap at `dpr = self.devicePixelRatioF()` captured in `_rebuild` (line 656), but `_boxed_pixmap` re-reads `dpr = pixmap.devicePixelRatio()` in `_make_node` (line 761). If the panel is moved to a screen with a different DPR after `_rebuild` (or the two disagree at construction before the widget is shown), the pad is sized for one ratio and the icon for another, so the icon overflows the pad and is clipped. The narrow connectors (e.g. `connector_quality-app` 36×5) are also `setFixedSize(_logical_size(pixmap))` in `_make_connector` (770–771) with no headroom, so any rounding drift crops them too.

**Proposed fix:** All in `pgtp_editor/ui/project_status_panel.py` — do not touch the model.
- *Fix the clipping first (pure code, no new assets):* In `_boxed_pixmap` (203–225), grow the pad to fit when the icon exceeds `box` — use `box = box.expandedTo(_logical_size(pixmap))` (or paint into a pad sized `max(box, icon)`) so the centering offset never has to clamp, and clip nothing. Make the DPR single-sourced: pass the same `dpr` used by `_scaled_pixmap` down through `_make_node`→`_boxed_pixmap` instead of re-reading `pixmap.devicePixelRatio()` at line 761, so pad and icon always share one ratio. Give `_make_connector` (768–773) the same expandedTo treatment (don't pin the label to an exact rounded logical size). Re-render on DPR change by overriding a `screen change`/`devicePixelRatio` hook (or calling `_rebuild()` when the top-level window's `QWindow.devicePixelRatioChanged` fires) so a screen move rebuilds pixmaps at the new ratio.
- *Fix the resolution:* preferred — render the node/connector art from the vector master `000source.svg` at the exact target device size instead of upscaling the small PNGs. That means loading via `QSvgRenderer` (Qt SVG, already an available Qt module) and painting each slice into a `QImage`/`QPixmap` at `logical_size * dpr`, then `setDevicePixelRatio(dpr)` — crisp at any scale, no `ASSET_SCALE` upscale. Because the individual node/connector slices are not currently separate SVG files, this needs either (a) the owner to export per-node SVGs (name them on the existing `[stem]`/`[stem]_drk` convention `asset_filename`/`asset_path` already resolve, in `project_status_model.py`), or (b) a slicing step. If per-slice SVGs are out of scope for this fix, the minimal alternative is to **re-export the PNGs at the displayed pixel size** (roughly `native × ASSET_SCALE × maxDPR`, e.g. 3–4×) and drop `ASSET_SCALE` to 1.0 so `_scaled_pixmap` only ever *downscales* (which stays crisp), never upscales. **Gotcha:** keep `asset_filename`/`asset_path` and the `_drk` light/dark convention (`project_status_model.py`, lines 302–318) unchanged — both theme variants must be re-supplied together, and `all_asset_stems()`'s on-disk existence test (321+) must still pass. Do not change the model, the state→stem tables, or the alignment math in `_rebuild` beyond the DPR/box-sizing corrections above.
- **Note for the resolver:** if you can only fix the code (no new/re-exported assets land in this pass), the *clipping* half is fully fixable in code now; the *resolution* half is asset-bound — say so in the commit and leave a follow-up, rather than claiming "PNGs low-res" is resolved by code alone.

**Test impact:** `tests/ui/test_project_status_panel.py` is the existing coverage. `test_chain_icon_boxes_share_one_height` (~line 109) already asserts icon-box height equality — extend it, don't duplicate. New cases: (1) for every node family in a full diagram, assert the icon-label pixmap's *logical* size is not clipped relative to its source — i.e. `_boxed_pixmap` output contains the whole scaled icon (assert pad logical size >= scaled-icon logical size in both axes, so the `max(0,…)` clamp never truncates); (2) a DPR-mismatch case — build the panel/pixmaps at one `devicePixelRatioF` and assert no icon overflows its box (monkeypatch/screen-stub the ratio); (3) a connector case asserting `_make_connector`'s label is at least the pixmap's logical size. If the resolution fix switches to SVG rendering, add a case asserting a node pixmap's device width equals `logical × dpr` (crisp, not the old `native × 2` upscale). `pgtp_editor/ui/project_status_model.py`'s on-disk asset test already guards both variants existing — extend it if assets are re-exported/renamed, don't add a parallel one.

**Spec impact:** CONSOLIDATED_SPEC §18.8 ("Image asset convention", ~lines 4777–4796) explicitly defers the asset pipeline as "an **implementation task**, not a further design decision — this subsection specifies the states each family must be able to render, not the asset pipeline," and records that the owner "already saved these assets in a local images folder." So the buggy render is **not** an intentional spec decision — no divergence to flag. However, if the fix formalizes a resolution/DPI or SVG-source rule (e.g. "assets are rendered from the vector master at device size," or "PNGs must be supplied at Nx"), that new pipeline rule should be folded into §18.8's asset-convention paragraph — flag for spec-maintainer AFTER the fix lands. Do not edit the spec here.

---
## BUG-030: Quality node status taxonomy — it never really probes (green = "configured", not "reachable"), the "not configured" state is unreachable, and click-through shows phantom details
**Status:** RESOLVED — facet (b)/never-probes in `ec03946`, facets (a) + (b)'s residual in `1c1a2c1`. All three taxonomy states are now reachable and every one is derived from a verified fact: NOT_SET_UP from the config (`_target_is_configured` = `target is not None and bool(target.host)`, matching the sandbox side's convention — `ProjectSettings.target` is `field(default_factory=ConnectionParams)` and so never None, which is why `is not None` was constantly True), OFFLINE and CONNECTION_OK from the off-thread `db_test_connection` probe. The click-through's phantom details are fixed too: `_connection_summary_for` routes through the same predicate, so a host-less profile reports "Not configured." instead of a degenerate `@:/` line, with a companion test proving real connections are not silenced. Facet (b)'s residual green-on-recheck is closed by the same predicate, since an unconfigured target skips the probe and now loses to NOT_SET_UP rather than falling through to green. Both corrections recorded in the earlier note stand: the `connect_timeout` gotcha was stale (10s is already set), and the blank-host hole was the real remaining defect.
**Reported:** 2026-08-06
**Report (verbatim):** "quality server in green although the connection is offline (confirmed by ddl explorer error message)."

**Two MORE facets reported 2026-08-06 (same quality-node status defect) — folded in here:**
- (a) "no setup" state, verbatim: *"clicking on quality server status is connected, but no details are given (probably this is connected to the previous bug, and those information would come from project settings) it should be 'quality no setup'."* When the target connection is NOT configured (empty `ProjectSettings.target` — see the closely-related BUG-034, where the `.pgtp` connection is never imported into `.target` so the quality fields stay empty) the node currently reads CONNECTED/green and its click-through window shows no real details. Expected: a distinct **"quality no setup"** state (not green/connected), and correctly no connection details on click because nothing is configured.
- (b) "offline" state, verbatim: *"quality database remains green even on recheck when there's no connection (it should turn to 1. quality offline)."* Even on Re-check the node stayed green despite an unreachable DB; expected a distinct **"quality offline"** state. This is the same never-probes root cause; the `ec03946` fix now re-probes on Re-check, but see facet (b) note below for the residual case where it can still stay green.

**Desired quality-node status TAXONOMY (three distinct states):**
1. target NOT configured (empty `ProjectSettings.target`, i.e. no `.host`) → `quality_connection_not_set_up` ("quality no setup", locked/gray, NOT green); click-through offers no connection details. Depends on / relates to BUG-034 populating `ProjectSettings.target` from the `.pgtp`.
2. configured but unreachable (probe fails), including on Re-check → `quality_offline` ("quality offline", red, NOT green).
3. configured AND reachable (probe succeeds) → `quality_connection_ok` (green), with connection details available on click.

**Root cause:** `pgtp_editor/ui/main_window.py`, `MainWindow._build_project_status_diagram()` (around line 3363):

```python
quality = quality_state(configured=target is not None, probe_error=None)
```

`probe_error` is **hardcoded to `None`**. `project_status_model.quality_state(configured, probe_error)` (`pgtp_editor/ui/project_status_model.py:218`) returns `QualityState.CONNECTION_OK` (green, caption "Connected") whenever `configured` is true and `probe_error is None`, `QualityState.OFFLINE` (red, "Unreachable") only when `probe_error is not None`, and `NOT_SET_UP` only when unconfigured. Because the caller never passes a real error, the Quality node reports green for *any* configured target connection — this is root-cause option (a): green means "a target profile exists" (`target is not None`), NOT "the target is reachable." No connection is ever attempted for this node. Unlike the Sandbox node, whose state is derived from a real off-thread probe (`refresh_project_capability_status()` → `_run_async(do_probe, …)`, `main_window.py:2865`/`2908`), the Quality node has no probe at all — `refresh_project_capability_status()` only probes the *sandbox* (`ProjectCapabilityStatus` "models the sandbox side only" per the method's own docstring at 3352), so re-checking never touches the target.

The DDL Explorer / Database-XML Coherence path the user saw the error from *does* open a real connection to the same target profile and surfaces the failure: `test_connection(params, runner=run_queries)` at `pgtp_editor/db/introspect.py:696` runs `SELECT 1` and returns `(False, <error text>)` on any driver/connection failure (never raises); the coherence run opens the connection off-thread via the same `params` and reports the error. So the status window and the DDL Explorer read the same target profile but the status window never tested it — hence the false-positive green.

**Expanded root cause for the folded facets (verified against the shipped, post-`ec03946` code):**

*The state enum is already correct and complete — the caller was (and for facet a still is) wrong.* `project_status_model.quality_state(configured, probe_error)` (`pgtp_editor/ui/project_status_model.py:221`) already distinguishes all three states the taxonomy wants: `not configured → QualityState.NOT_SET_UP` (rendered `quality_connection_not_set_up`, caption "Not configured"), `probe_error is not None → QualityState.OFFLINE` ("Unreachable"), else `CONNECTION_OK` ("Connected"). Nothing is missing from the model; the enum matches CONSOLIDATED_SPEC §18.8's line-4974 not_set_up/offline/connection_ok trio exactly. The captions live in `project_status_panel.py:150` `_STATE_CAPTIONS` (`quality_connection_not_set_up`→"Not configured", `quality_offline`→"Unreachable", `quality_connection_ok`→"Connected"). So the fix is purely in what the *caller* feeds `quality_state`, plus the click-through detail text — not in the model.

*Facet (a) — "quality no setup" is unreachable.* `MainWindow._build_project_status_diagram()` (`main_window.py:2629`, post-fix line) computes `quality = quality_state(configured=target is not None, probe_error=self._ddl_target_probe_error)` at `main_window.py:2641`. `target` comes from `_project_status_target()` (`main_window.py:2618`): `settings.target if settings is not None else load_connection(self._settings)`. With a project open, `settings.target` is a `ConnectionParams` **dataclass instance that is never None** (`ProjectSettings.target: ConnectionParams = field(default_factory=ConnectionParams)`, `db/ddl_project.py:115`), so `configured=target is not None` is **always True** and `NOT_SET_UP` can never be selected for an open project — an empty/unconfigured target renders green "Connected". The `_refresh_target_connection_status()` probe (`main_window.py:2233`) already guards on `target.host` (`if target is None or not target.host: self._ddl_target_probe_error = None; return`, `main_window.py:2247`), so for an empty target it *skips the probe and clears the error* — leaving `probe_error=None` and `configured=True`, which `quality_state` reads as `CONNECTION_OK`. That is exactly the reported "connected but no details" symptom: the node is green precisely because the empty target is never probed AND is counted as configured.

*Facet (a) — phantom click-through details.* The Quality click-through is `ProjectStatusPanel._quality_window()` (`project_status_panel.py:993`). It emits `window.add_line(self._state_line(...))` then `window.add_line(self._quality_summary or "No connection details available.")`. `_quality_summary` is fed at open time by `_open_project_status()` (`main_window.py:2705`) via `quality_summary=self._connection_summary_for(self._project_status_target())`, and `_connection_summary_for` (`main_window.py:2653`) returns `connection_summary(params)` for any non-None params — including an all-empty `ConnectionParams()`, which yields a meaningless `user@host:port/db`-shaped line rather than the "Not configured." branch (that branch only triggers when `params is None`, which never happens for an open project). So in the no-setup case the window shows a green "Connected" status line plus a hollow/degenerate connection summary — "connected, but no real details," matching the report.

*Facet (b) — the Re-check path.* CONFIRMED: after `ec03946`, the Re-check button and the on-open seam both funnel through `refresh_project_capability_status()` (`main_window.py:2182`), whose first line is `self._refresh_target_connection_status()` (`main_window.py:2203`) — so a *configured* target IS re-probed on Re-check and correctly flips to `quality_offline`. The residual "green even on recheck" is the facet-(a) mechanism, not a missing re-probe: when the target has no `.host`, `_refresh_target_connection_status()` returns early without probing (`main_window.py:2247`) and `configured=True` keeps it green. So facets (a) and (b) share one fix — make `configured` mean "has a real host," which simultaneously (i) makes an unconfigured target read as `NOT_SET_UP` instead of green, and (ii) stops an unconfigured target from masquerading as reachable-green on Re-check. A genuinely configured-but-down target is already handled correctly by the shipped probe.

**Proposed fix:** Make the Quality node's state come from a real connectivity probe of the target profile, using the existing `db_test_connection` (already imported at `main_window.py:118` as `test_connection as db_test_connection`) — the same `SELECT 1` check the Explorer path relies on — instead of `probe_error=None`.

Concrete shape:
- Add a stored field for the last target probe result, e.g. `self._ddl_target_probe_error: str | None` (mirroring how `self._ddl_project_capability_status` caches the sandbox probe). Initialize it to a sentinel meaning "not probed yet" and treat unprobed as OFFLINE-unknown is NOT desired — see gotcha below.
- Add a target probe that runs **off the GUI thread**, mirroring `refresh_project_capability_status()`'s `_run_async(do_probe, on_result=…, on_error=…)` pattern (`main_window.py:2889`–2908). `do_probe` calls `db_test_connection(target)` → `(ok, message)`; `on_result` stores `None` when `ok` else `message`, then re-renders the open Project Status window via `set_diagram(self._build_project_status_diagram())` if `self._project_status_window is not None`. Do NOT block the GUI synchronously in `_build_project_status_diagram()` — a dead host would freeze the window (the whole reason the sandbox probe is already async; see the "Runs off the GUI thread so an unreachable sandbox host can't freeze the window" note at 2878).
- Wire it into the same trigger points the sandbox probe uses so "opening the window is a fresh probe" (§18.8) holds for Quality too: the panel's `on_refresh` seam (`_open_project_status`'s `on_refresh` at 3399, and the reuse path's explicit `refresh_project_capability_status()` at 3393) and the Re-check button already funnel through `refresh_project_capability_status` — either extend that method to also probe the target, or add a sibling `refresh_target_connection_status()` and call it from the same three spots (3393, 3400, and `_set_active_ddl_project`'s probe call at 2854). Prefer extending the existing method so there is one "re-probe everything the window shows" entry point.
- In `_build_project_status_diagram()`, pass the stored result: `quality = quality_state(configured=target is not None, probe_error=self._ddl_target_probe_error)`.

Gotchas:
- **Configured-but-not-yet-probed vs. offline.** Do not render red before the async probe has returned, or a healthy connection flashes red on every open. Two acceptable shapes: (1) render the last-known state and let the async result push a corrected diagram via `set_diagram` (matches how the sandbox side already works — first paint uses the cached `_ddl_project_capability_status`, the probe refreshes it), or (2) if no probe has run yet, keep the current green until the first result lands. Pick (1) for consistency with the sandbox node; initialize `_ddl_target_probe_error` from the *previous* probe, and have the diagram builder read whatever is currently stored.
- **Same `target` selection as today.** Keep the BUG-024 target selection exactly: `settings.target if settings is not None else load_connection(self._settings)` (project's own profile when a project is open, app-level saved connection otherwise). The probe must test the *same* `ConnectionParams` object the summary line and the Explorer use, or you reintroduce root-cause option (d).
- **`test_connection` never raises** — it returns `(False, msg)`. So `on_error` in the `_run_async` wrapper is only for a broken injected seam (as the sandbox probe's `on_error` comment at 2900 notes); the real failure arrives as `ok=False` in `on_result`. Store `message` (not the exception) as `probe_error` so the Quality window's status line and any future detail match what the Explorer shows.
- **Timeout.** `db_test_connection` → `run_queries` → `psycopg.connect` (`introspect.py:425`). A dead host can hang on TCP connect for the OS default; because the probe is off-thread the GUI won't freeze, but the window's green→red correction can lag. `introspect.py::run_queries` already declares `connect_timeout: int = 10`, so this is bounded at ~10s — no change needed (the original entry's "add a connect_timeout" note was stale).

**REMAINING FIX for facets (a)/(b) — the three-state taxonomy (this is what is STILL OPEN):**

The OFFLINE-on-probe half shipped in `ec03946`; the below closes the "quality no setup" gap and the phantom-details gap. All changes are in the *caller* + the click-through detail text — the `quality_state` model function needs no change.

1. **Make `configured` mean "has a real target host," so `NOT_SET_UP` becomes reachable.** In `_build_project_status_diagram()` (`main_window.py:2641`) change `configured=target is not None` to `configured=target is not None and bool(target.host)`. This is the single line that makes an empty/unconfigured target render `quality_connection_not_set_up` ("quality no setup", state 1) instead of green. It also fixes facet (b)'s residual "green even on recheck": an unconfigured target already skips the probe (leaving `probe_error=None`), so before this change it fell through to `CONNECTION_OK`; after it, `configured` is False and `NOT_SET_UP` wins regardless of `probe_error`. Note `quality_state` already prioritises not-configured over any stale error (`project_status_model.py:229`), so ordering is safe. The already-shipped `_refresh_target_connection_status()` early-return on `not target.host` (`main_window.py:2247`) is consistent with this and needs no change — a host-less profile stays unprobed and now reads NOT_SET_UP rather than green.
2. **Suppress phantom click-through details in the no-setup state.** The Quality window (`ProjectStatusPanel._quality_window()`, `project_status_panel.py:993`) shows `self._quality_summary or "No connection details available."`. Today `_quality_summary` is `_connection_summary_for(self._project_status_target())` (`main_window.py:2705`), and `_connection_summary_for` (`main_window.py:2653`) only returns "Not configured." when `params is None` — never for an empty `ConnectionParams()`. Fix at the caller: make `_connection_summary_for` (or the `quality_summary=` argument at `main_window.py:2705`) treat a host-less target the same as None, e.g. `params if (params is not None and params.host) else None → "Not configured."`. Then the no-setup window correctly reads "Status: Not configured" + "Not configured." with no phantom `user@host:port/db` line, and (since `on_reconnect_quality` is still wired) the Reconnect action stays available to let the user go configure it. Keep this in the caller — `_connection_summary_for` is the one place that already owns the None→"Not configured." branch; do not add a second host-emptiness check inside `project_status_panel.py` (the panel "reads no connection profile itself", per its module docstring).
3. **No change to the OFFLINE (state 2) or CONNECTION_OK (state 3) paths** — the shipped `_refresh_target_connection_status()` probe already delivers both correctly for a configured target, on both initial open and Re-check (`refresh_project_capability_status()` → `_refresh_target_connection_status()`, `main_window.py:2203`, is the single re-probe entry point wired to `on_refresh` and the reuse path).

Gotcha: BUG-034 is the *source* of a populated `ProjectSettings.target` — until it lands, a real project's target will legitimately be empty and this fix correctly shows "quality no setup" for it (which is the honest state). Do not make this fix depend on BUG-034; they are independent and this one is correct on its own. When BUG-034 later populates `.target` from the `.pgtp`, the same node will transition to OFFLINE/CONNECTION_OK via the existing probe with no further change here.

**Test impact:** `tests/ui/test_project_capability_wiring.py` is the wiring-level home (it already exercises `quality_state`/`probe_error` for the sandbox-degradation cases at lines 97/104/207 and builds diagrams through the MainWindow seams) — extend it, don't duplicate. New cases: (1) target profile configured + `db_test_connection` monkeypatched to return `(False, "could not connect to server")` → `_build_project_status_diagram()`'s Quality node is `QualityState.OFFLINE`/`quality_offline` (red), not `CONNECTION_OK`; (2) configured + `(True, "Connected.")` → `CONNECTION_OK`; (3) no target configured → still `NOT_SET_UP` (unchanged); (4) the async path: after the probe result lands, an already-open `_project_status_window` gets a re-rendered diagram with the corrected Quality state (patch `_run_async` to run synchronously the way the existing sandbox-probe wiring tests do). Also assert `db_test_connection` is called with the *same* `target` params the summary uses. `tests/ui/test_project_status_model.py` and `tests/ui/test_project_status_panel.py` already cover the pure `quality_state`/panel-render layer and need no change (the model function is already correct; only the caller was wrong) — do not touch them beyond a possible added `quality_state(configured=True, probe_error="…")` assertion if not already present.

*Added cases for the facet (a)/(b) taxonomy fix (extend `tests/ui/test_project_capability_wiring.py`, the same wiring home):* (5) a project whose `ProjectSettings.target` is the default all-empty `ConnectionParams()` → `_build_project_status_diagram()`'s Quality node is `QualityState.NOT_SET_UP` (`quality_connection_not_set_up`), NOT `CONNECTION_OK` — this is the regression this fix targets and today would (wrongly) be green; (6) with an empty target, `db_test_connection` is **not** called at all (the probe early-returns on `not target.host`, `main_window.py:2247`) — assert the monkeypatched probe records zero calls, and that the state is still `NOT_SET_UP` after a `refresh_project_capability_status()` Re-check (facet b's "green even on recheck" pinned); (7) a target with a host but a failing probe → `OFFLINE` even after Re-check (guards that Re-check re-probes — patch `_run_async` synchronous). For the click-through / phantom-details fix, `tests/ui/test_project_status_panel.py` (or the wiring test that opens the real panel) gets: (8) opening the Quality window with an empty target shows the "Not configured." detail line and NO `user@host:port/db`-shaped summary — assert `_connection_summary_for(ConnectionParams())`/the `quality_summary=` value is "Not configured.", and that the opened `NodeWindow.body_text` contains "Not configured" and not a host string. Reuse the existing panel-open fixtures; do not hand-roll a `NodeWindow`.

**Spec impact:** Diverges from CONSOLIDATED_SPEC §18.8 — but restores conformance rather than changing policy; **not** an intentional decision. The spec's per-node source table (line 4932) states the Quality node's source is the target profile's **"reachability, not yet further broken into states beyond connected/not."** The state enumeration (line 4974) is already explicit that the three states are exactly the taxonomy this entry wants: `quality_connection_not_set_up` ("the quality/target connection is simply **not configured yet**, the same semantic category as the Sandbox node's `sandbox_not_set_up`"), `quality_offline` ("red — connection attempted but failed/unreachable"), `quality_connection_ok` ("green — connected, healthy") — and it spells out the intended "not_set_up (never configured) / offline (configured but unreachable) / connection_ok (configured and healthy)" trio verbatim. So the model already matches the spec; the OFFLINE half was an implementation bug (fixed `ec03946`) and the NOT_SET_UP half is a second implementation bug against the same settled design — no spec change is required for the fix to be correct. **Cross-reference:** the "configured vs not configured" distinction only becomes *useful* once `ProjectSettings.target` is actually populated from the `.pgtp`, which is **BUG-034** (§18.2/§17, the `.pgtp` `<ConnectionOptions>` → `.target` import); this entry and BUG-034 are independent fixes that meet at `ProjectSettings.target`. Optional, low priority: after this lands, flag `spec-maintainer` to note in §18.8 (and/or §18's probe-timing paragraph ~line 1850, which today describes only the sandbox capability probe being re-run on window open) that the target-connection reachability probe runs on the same on-open/Re-check triggers as the sandbox probe, and that `configured` is defined as "the target profile has a host." Do not edit the spec here.

---

## BUG-032: Database/XML coherence lookup-table handling — (A) double-click on a "Tables and Views" relation row always says "not found in the buffer" (wrong search token), and (B) KeyError: 'lookup' crash selecting a lookup reference

**Status:** RESOLVED — facet B (ec03946), facet A (596f109). Facet A's real cause was a `kind` string mismatch, NOT the rejected reset/working-set hypothesis: `_on_db_jump_requested` tested `kind == "table"` (written for the removed `DbCheckPanel`) while `CoherencePanel` emits `kind="relation"`, so relation rows searched for `fieldName=` instead of `tableName=` and always missed. Fixed at both ends via a single `_HOST_KIND` mapping plus slot hardening; a genuine miss now names the token actually searched. Also restored Properties for `kind="reference"` rows (an unreported sibling crash facet B exposed) by carrying `TableReference.kind` through `_reference_node` as `CoherenceNode.node_kind`. The two tests that pinned the bug are flipped and the real slot body is now driven unpatched end to end.
**Re-triaged:** 2026-08-06 — **Facet A's root cause was replaced** (the original sandbox-reset diagnosis was tested against the reporter's account and rejected; see "Rejected hypothesis" under Facet A). Facet B unchanged and already implemented.
**Reported:** 2026-08-06
**Report (verbatim):** "Database/XML coherence database table lookup stops working after a while. at first it finds the database tables in the reference, then after a few tests it says not found in the buffer."

Per the coordinator (relaying the user), a second symptom is **the same bug, filed under one id** — a `KeyError: 'lookup'` crash when a lookup-table reference is selected. Both are about lookup-table handling in the coherence surface; this entry covers both and relates them below. They are **two distinct code defects that share a theme** (the merged coherence view of FQ-003 wiring node kinds into slots that were written for the panels it replaced), not one shared root cause — fix both, in this one entry.

---

### Facet B (crash — fix this one first; it is small, certain, and independently reproducible)

> **Facet B status: IMPLEMENTED / FIXED this session.** The analysis below is kept verbatim as the record
> of why the fix was shaped this way; do not re-implement it. Only Facet A remains open, which is why the
> entry's `Status` line is still `OPEN`.

**Root cause:** `pgtp_editor/ui/properties_panel.py:244`, `PropertiesPanel.show_node()`:
`rows_fn, header_fn = _ROW_BUILDERS[kind]`. `_ROW_BUILDERS` (lines 181–189) has keys
`page`, `detail`, `column`, `event`, `ddl_table` — there is **no `"lookup"` key**. The coherence
tree's Pages branch mints lookup rows with `kind="lookup"` and `node=<the owning ColumnNode>`
(`pgtp_editor/db/coherence.py`, `lookup_nodes()` at lines 337–362, node built at ~351–360 with
`node=column`). `CoherencePanel._on_current_changed` (`pgtp_editor/ui/coherence_panel.py:361`) emits
`selection_changed.emit(node.node, node.kind)` → wired at `main_window.py:306` to
`_on_table_ref_selection` (`main_window.py:1333–1334`) → `properties_panel.show_node(node, "lookup")`
→ `_ROW_BUILDERS["lookup"]` → `KeyError: 'lookup'`. Selecting any lookup row in the coherence tree
crashes. This regressed with FQ-003's merged coherence view / BUG-026's page/detail/**lookup** role
modeling, which introduced the `"lookup"` kind on the reference side (`_XML_KINDS` in
`coherence_panel.py:90` explicitly includes `"lookup"`) without adding the matching
`_ROW_BUILDERS["lookup"]` mapping in the Properties panel.

**Proposed fix (two parts, both in `pgtp_editor/ui/properties_panel.py`):**
1. Add a `"lookup"` entry to `_ROW_BUILDERS` (after the `"column"` entry, ~line 184) that **reuses the
   existing column builder** — a lookup node's `.node` is a `ColumnNode`, so `_rows_for_column` is
   exactly right:
   `"lookup": (_rows_for_column, lambda n: f"Column: {n.field_name}"),`
   Keep the header identical to `"column"` (the underlying node is the column that carries the
   `<Lookup>`); do not invent a new `_rows_for_lookup`.
2. Make `show_node` **degrade gracefully on an unknown kind** so a future missing mapping can never
   crash again. Replace `_ROW_BUILDERS[kind]` with a `.get(kind)` guarded lookup: on a miss, fall back
   to the empty state (`self._show_empty_state(); return`) rather than raising — mirroring the existing
   `node is None or kind is None → _show_empty_state()` guard two lines above. (An empty panel is the
   safe, non-crashing degradation consistent with §17/§10; a hard `KeyError` reaching the Qt signal
   slot is not.) Gotcha: `_populate_table(..., paired=(kind == "ddl_table"))` on line 246 must stay
   reachable only when a builder was found — put the fallback `return` before it.

**Test impact (Facet B):** `tests/ui/test_properties_panel.py` already covers `show_node` for the
existing kinds — extend it, don't duplicate: (1) `show_node(column_node, "lookup")` renders the same
rows as `show_node(column_node, "column")` and does **not** raise; (2) `show_node(anything, "bogus")`
falls back to the empty state instead of raising. `tests/ui/test_coherence_wiring.py` (the
`selection_changed → _on_table_ref_selection → properties_panel.show_node` wiring) is the integration
home: add a case that builds a coherence tree containing a lookup row (a `<Column>` with a
`<Lookup tableName="…">`), selects it, and asserts no exception and a populated Properties panel. Fixture
material for a lookup-bearing project already exists under `tests/analysis/test_reused_tables.py` /
`tests/db/test_coherence.py` — reuse a sample with a lookup column rather than hand-rolling XML.

---

### Facet A (the reported "not found in the buffer" failure) — RE-TRIAGED 2026-08-06, root cause replaced

**Rejected hypothesis (do not re-chase it).** The first triage of this facet blamed the **stateful
sandbox**: `SandboxSession.reset()` (`db/sandbox.py`) dropping every app schema and re-provisioning only
from the baseline, wiping objects `apply()`'d afterwards while their `applied` bookkeeping rows survive,
so a later tier-3 Check's `to_regprocedure`/`to_regclass` resolve returns NULL and `run_plpgsql_check`
emits `REASON_OBJECT_ABSENT` / `REASON_RELATION_ABSENT`. **That mechanism requires a destructive gesture
between the working Check runs and the failing ones, and the reporter has explicitly confirmed there was
none** — no reset, no re-provision, no data clone; they only ran Check repeatedly. Independently
verified in code: the only callers of `reset_session` / `provision` / `run_data_clone` are explicit user
gestures in `pgtp_editor/ui/sandbox_controller.py`, and `db/sandbox.py` is the sole definition site, so
nothing on the Check path can trigger the drop. The hypothesis is therefore **rejected on the evidence**,
not merely deprioritised. Two further nails: the sandbox messages say "not found in the **sandbox**"
(`db/ddl_check.py:126`, `:132`), never "buffer"; and the report names the **Database/XML Coherence**
surface, which has no sandbox involvement at all. The whole sandbox/`ddl_text`-persistence fix direction
that was pre-approved *conditional on that diagnosis* is consequently **not applicable to this bug** — if
a durable-working-set feature is still wanted on its own merits, it belongs in `docs/FEATURE_QUEUE.md`,
not here.

**Root cause (actual): the wrong search token is built for the coherence view's relation rows.**
`pgtp_editor/ui/main_window.py:3770-3779`, `MainWindow._on_db_jump_requested(kind, name)`:

```python
token = f'tableName="{name}"' if kind == "table" else f'fieldName="{name}"'
editor = self.center_stage.xml_editor
if token not in editor.toPlainText():
    self.statusBar().showMessage(f"{name} not found in the buffer.", 5000)
    return
```

`main_window.py:3778` is the **only** place in the codebase that produces the reported wording
(`grep -rn "not found in the buffer" pgtp_editor/` returns just this line and `main_window.py:2471`, the
unrelated "Could not insert `<tag>`: page not found in the buffer." from the tree's Add-Event-Handler
write-back). So the failing lookup is the coherence view's **double-click → find this DB relation's name
in the Raw XML** navigation, not anything sandbox-side.

The kind vocabulary changed under this slot and the slot was never updated:

* The slot's `kind == "table"` test was written for the old `DbCheckPanel`, whose relation rows stored
  the 4-tuple `("table", table.name, ok, False)` (`pgtp_editor/ui/db_check_panel.py:156`) and emitted it
  verbatim (`db_check_panel.py:194-199`). With `kind == "table"` the token is `tableName="…"` — correct.
* FQ-003's merged view replaced that panel. `CoherencePanel` rows carry `CoherenceNode.kind`, and a
  DB-side relation's kind is **`"relation"`**, not `"table"` (`pgtp_editor/db/coherence.py:286`, with
  `table_name=check.name` at `:293`). `CoherencePanel._on_double_click`
  (`pgtp_editor/ui/coherence_panel.py:363-371`) emits
  `name_jump_requested.emit(node.kind, node.table_name or node.label)` → `("relation", "pr.v")`.
* Commit `113fbfa` ("wire FQ-003's merged view") only **re-pointed the connection** —
  `- self.db_check_panel.jump_requested.connect(self._on_db_jump_requested)` /
  `+ self.coherence_panel.name_jump_requested.connect(self._on_db_jump_requested)`
  (`main_window.py:303`) — and left `_on_db_jump_requested`'s body untouched (verified with
  `git show 113fbfa -- pgtp_editor/ui/main_window.py`).

Consequence: for every relation row in the **Tables and Views** branch, `kind == "relation"` falls into
the `else`, so the app searches the XML for `fieldName="<table name>"`. Table names in these projects are
schema-qualified (`pr.a`, `pr.v`) and are never field names, so the search **always** misses and the user
always gets "`pr.v` not found in the buffer." Column rows still work (`kind == "column"` →
`fieldName="…"`, correct), and Pages-branch page/detail/lookup rows and the per-relation **References**
group rows never reach this slot at all — they take the other signal, `jump_requested(line)` →
`_tree_jump_to_line` (`main_window.py:304`; `_XML_KINDS` at `coherence_panel.py:90` is
`{page, detail, lookup, reference}`). Note that `CoherencePanel._make_item` also stores the raw
`node.kind` into the carried-over `_ROW_ROLE` 4-tuple (`coherence_panel.py:248-262`), so the same
`"relation"`-vs-`"table"` vocabulary mismatch is latent for any future consumer of that role.

**On the "after a while / after a few tests" wording — the defect is deterministic, not degrading.**
The most likely reading, which fits the report line by line: the reporter's early successful navigations
were the rows that *do* work — "at first it finds the database tables **in the reference**" maps exactly
onto the **References** group under a relation (`kind == "reference"`, jumps by line, works) and onto
column rows; then double-clicking the relation row itself always yields "not found in the buffer."
Alternatively "at first" refers to the pre-FQ-003 build, where `DbCheckPanel` emitted `"table"` and the
same gesture worked — i.e. this is a regression the reporter experienced across versions rather than
within one session. Either way there is **no time- or count-dependent mechanism in this code path**, and
the previous entry's "nothing in the coherence path caches or evicts" audit still holds and is still
worth keeping: `build_coherence_tree` is rebuilt from a fresh `fetch_schema` per run, `SchemaIndex` is
read-only, `DatabaseSchema.tables` is never mutated, and `run_queries` (`db/introspect.py:408-441`) opens
and closes one connection per call — no LRU/TTL/size cap anywhere. Nothing rewrites `xml_editor`'s text
behind the user's back either (Caption Mode snapshots and re-writes it only on explicit Apply,
`main_window.py:2490-2546`), so the buffer cannot silently lose the token.

**If the reporter insists a relation-row double-click genuinely worked earlier in the same session on
the same build,** then something above is incomplete and these facts are needed before implementing:
(1) the exact row double-clicked (branch + level: a relation under "Tables and Views", vs a row under its
"References" group, vs a Page/Detail/Lookup under "Pages"); (2) the literal status-bar text including the
name it printed (an unqualified vs `schema.`-qualified name distinguishes token-shape problems from
name-mismatch ones); (3) how many Check runs, and whether the app or DB was restarted in between;
(4) whether the row carried an "unreferenced" badge. Ask before widening the fix beyond the token bug.

<details>
<summary>Superseded first-pass root cause (sandbox reset) — retained for the record only</summary>

**Root cause (buffer lifecycle):** The "buffer" the report describes is the **stateful sandbox** — the
app-owned sandbox database that accumulates applied DDL objects (§18.5 D2). The table LOOKUP that
"works at first, then reports not found" is the tier-3 Check driver resolving the object/relation oid
in that sandbox: `pgtp_editor/db/ddl_check.py::run_plpgsql_check` (lines 691–787) issues
`build_resolve_sql` (lines 514–529) which does `to_regprocedure(...)` / `to_regclass(...)` against the
sandbox; when the lookup returns NULL it emits **`REASON_OBJECT_ABSENT`** (`ddl_check.py:125–129`,
"the object was not found in the sandbox …") or **`REASON_RELATION_ABSENT`** (`ddl_check.py:131–135`,
"the table this trigger fires on was not found in the sandbox …"). Those are the literal
"not found in the … buffer" messages the user is seeing (the sandbox working set is the buffer).

The "works at first, fails after a few tests" mechanism is that the sandbox buffer gets **dropped and
only partially repopulated** by a destructive operation between checks:
`pgtp_editor/db/sandbox.py::SandboxSession.reset()` (lines 914–939) runs
`DROP SCHEMA <each app schema> CASCADE` for every `self.schema_names` and then re-provisions **only**
from `self.baseline` (`build_baseline_sql` against the recorded snapshot for a `SCHEMA_ONLY` sandbox,
or a fresh `clone_data` for `WITH_DATA`). Anything the user `apply()`'d **after** provisioning (each
edited function/trigger they applied via §18.5's `apply_and_check`,
`ui/ddl_object_editor.py::apply_to_sandbox`, lines 851–887) is wiped and **not** re-applied — the
bookkeeping row survives in `applied` but the object itself is gone from the catalog. So the next
Check's `to_regprocedure`/`to_regclass` lookup finds nothing → `REASON_OBJECT_ABSENT` /
`REASON_RELATION_ABSENT`. `reset()` is reachable from
`ui/sandbox_controller.py::reset_session` (lines 595–619, a `DESTRUCTIVE_OPERATIONS` member) and the
same "drop-and-recreate-from-baseline" happens on `provision` (lines 432–495) and
`run_data_clone` (lines 497–547) — each drops the accumulated working set. The reference (the live
target DB / the introspected schema) is **fine**; it is the sandbox *buffer layer* that loses the
objects, exactly as the report frames it ("finds them in the reference … not found in the buffer").

Note what is NOT the cause, so the resolver does not chase it: the `Database/XML Coherence` view proper
(`db/coherence.py::build_coherence_tree`, called from `main_window.py::_run_db_check`/`_populate_db_check`,
lines 3150–3207 / 3124–3130) rebuilds a **fresh** tree from a **fresh** `fetch_schema` every run and
holds no evicting cache — `SchemaIndex` (`db/schema_index.py`) is read-only, `DatabaseSchema.tables`
is never `.pop()`'d, and `run_queries` (`db/introspect.py:408–441`) opens and closes one connection per
call. There is no LRU/TTL/size-cap eviction anywhere in this path. The degradation is specifically the
sandbox working set being reset-without-reapply, not a coherence-view cache.

**Proposed fix (SUPERSEDED — do not implement) — pick per the resolver's read of §18.5 D2's intended
semantics; option 1 is recommended:**
1. **Re-apply the recorded working set after a reset/reprovision.** In
   `SandboxSession.reset()` (`db/sandbox.py:914–939`), after the drop + baseline/clone re-provision,
   re-`apply()` every object still recorded in the `applied` bookkeeping table so the buffer that was
   "just refreshed" still contains what the user put there. Gotcha: `apply()` stores only a
   `text_sha1` fingerprint, **not** the DDL text (lines 880–891), so `reset()` cannot replay the text
   from bookkeeping alone. Two sub-options: (a) widen the `applied` table / `apply()` to persist the
   `ddl_text` so `reset()` can replay it; or (b) have the **controller** (`SandboxController.reset_session`,
   `sandbox_controller.py:595–619`) capture the working set the host still has open in DDL tabs and
   re-apply after the reset completes. Prefer (a) — it keeps `reset()` self-contained and correct for
   any caller — but it is a schema/contract change to the bookkeeping table, so it needs a
   `spec-maintainer` §18.5 D2 note (see Spec impact).
2. **If reset-drops-the-working-set is the intended, documented behavior** (D2a's "refreshing means
   destroying and recreating the sandbox" — `sandbox_controller.py:110–133` warnings literally say
   "Anything already applied to the sandbox is lost"), then the bug is a **UX/messaging** one: the
   Check's `REASON_OBJECT_ABSENT` after a reset reads to the user as a malfunction ("stops working"),
   when the object genuinely needs re-applying. Fix by making the DDL editor's Check surface an
   actionable line when a prior-applied object comes back absent — reuse the existing "changed since
   last applied" divergence signal (`ui/ddl_object_editor.py`, `applied_sha1` at line 552, the
   diverged-buffer `[Check]` caveat referenced at lines 548–551): if `applied_sha1` is set but the
   sandbox lookup now returns absent, emit a `[Check]` line telling the user to Apply to Sandbox again
   rather than presenting a bare "not found in the sandbox." This is the smaller change and does not
   touch the bookkeeping contract.

   **Decision guidance for the resolver:** read §18.5 D2/D2a in `CONSOLIDATED_SPEC.md` first. If the
   working set is meant to be *durable* across a mere Check cycle (the user's mental model — "it found
   it before"), option 1 is the real fix. If reset is only triggered by an explicit destructive
   gesture the user consciously took, option 2 (honest, actionable messaging) may be sufficient. Do
   **not** implement both blindly; the buffer-lifecycle question is a design call for the spec, not an
   invented behavior.

</details>

**Proposed fix (Facet A) — one small, certain change plus two cheap hardenings. No design decision is
required; this is a plain regression against the behavior `DbCheckPanel` already had.**

1. **Normalize the relation kind where the signal is emitted** — `pgtp_editor/ui/coherence_panel.py`,
   `CoherencePanel._on_double_click` (lines 363-371). Emit the MainWindow-facing kind vocabulary, not the
   internal node kind:
   `self.name_jump_requested.emit("table" if node.kind == "relation" else node.kind, node.table_name or node.label)`
   — or cleaner, a module-level `_JUMP_KIND = {"relation": "table", "column": "column"}` and
   `self.name_jump_requested.emit(_JUMP_KIND.get(node.kind, node.kind), …)`.
   **This is the established pattern in this very file, not an invention:** `contextual_rename`
   (`coherence_panel.py:391-399`) already maps a relation row to the host-facing `"table"` kind
   (`self.rename_requested.emit("table", node.table_name)`) precisely because `MainWindow._on_db_rename_requested`
   (`main_window.py:3748`) also tests `kind == "table"`. The jump signal simply never got the same
   normalization. Doing it here keeps `CoherenceNode.kind` (`"relation"`) untouched for the tree's own
   rendering/filtering logic, and matches CONSOLIDATED_SPEC §17's binding "carried over from
   `DbCheckPanel` unchanged … `jump_requested(kind, name)`" (spec line ~1548).
2. **Harden the slot so a future kind rename cannot silently reintroduce a wrong-token search** —
   `main_window.py:3775`. Replace the single-value test with an explicit set and an explicit fallback,
   e.g. `token = f'tableName="{name}"' if kind in ("table", "relation") else f'fieldName="{name}"'`.
   Belt-and-braces with (1) on purpose: (1) fixes the contract, (2) makes the slot correct even if some
   other caller passes the internal kind. Do **not** implement (2) alone and skip (1) — the `_ROW_ROLE`
   4-tuple (`coherence_panel.py:248-262`) still ships `"relation"` where §17 says the carried-over shape
   holds `"table"`, and leaving that inconsistent is what caused this bug. If (1)'s normalization is
   applied, feed the same normalized kind into `_ROW_ROLE` too so both host-facing surfaces agree.
3. **Make the failure message honest and actionable when the token legitimately misses.** With (1) in
   place, a relation with the `"unreferenced"` badge (`BADGE_UNREFERENCED`, `db/coherence.py:84`; the DB
   relation the XML references in no role — settled §17 behavior, spec line ~1531) will *correctly* find
   no `tableName="…"` occurrence. "`pr.v` not found in the buffer." reads as a malfunction for that case.
   In `_on_db_jump_requested`, when the token misses, print the token that was searched and, if the row
   is a relation, say the relation is not referenced in the XML — e.g.
   `f'No {token} in the buffer — the XML does not reference {name}.'` Keep it a status-bar message
   (`self.statusBar().showMessage(..., 5000)`); do **not** escalate to a dialog. This is the only part of
   the fix that touches wording; keep it minimal so the existing status-message tests stay meaningful.

**Gotchas.** (i) `_on_db_jump_requested` does more than jump: it reveals the Raw XML tab, seeds the Find
bar with the token and runs Find All into the Audit panel (`main_window.py:3780-3795`). Fixing the token
turns all of that on for relation rows for the first time — expect the Audit dock to become visible on a
relation double-click, which is the intended pre-FQ-003 behavior. (ii) With Caption Mode active the Raw
XML tab is present but read-only; the jump still works and needs no gating (no change here). (iii) Line
numbers cited are as of this re-triage on branch `bugfix-021-026-027-028`; re-grep
`not found in the buffer` and `name_jump_requested` if they have drifted.

**Relationship between the two facets:** they are **grouped by theme, not by a single root cause**.
after the re-triage they turn out to be **the same class of defect, twice**: FQ-003's merged coherence
view feeds `CoherenceNode.kind` values into MainWindow/panel slots that were written for the surfaces it
replaced. Facet B: the new `"lookup"` kind reached `PropertiesPanel._ROW_BUILDERS`, which has no such key
→ `KeyError`. Facet A: the new `"relation"` kind reached `MainWindow._on_db_jump_requested`, which only
recognises the old `"table"` → wrong search token. Neither fix subsumes the other (different files,
different tests), but a resolver should take the shared lesson: **audit every remaining consumer of a
`CoherenceNode.kind` for the old `DbCheckPanel`/`TableReferencesPanel` vocabulary.** Known consumers to
check while here: `main_window.py:300-306`'s five connections (`rename_requested` → `_on_db_rename_requested`
tests `kind == "table"` and *is* fed a normalized `"table"`, OK; `create_requested` → `_on_db_create_requested`
takes a `what`, not a node kind, OK; `selection_changed` → `_on_table_ref_selection` → Facet B) plus the
`_ROW_ROLE` 4-tuple.

**Test impact (Facet A):** the sandbox tests named in the superseded analysis are **not** relevant — do
not add anything to `tests/db/test_sandbox.py` or `tests/db/test_ddl_check.py` for this bug.
* `tests/ui/test_db_check_wiring.py` is the existing home of the slot's tests (lines ~446-640) — extend,
  don't duplicate. **Note that these tests are exactly why the bug escaped:** every one of them calls
  `window._on_db_jump_requested("table", "pr.a")` / `("column", "id")`, i.e. the *legacy* kinds the
  coherence panel no longer emits. Add cases driving the kind the panel actually sends: (1)
  `_on_db_jump_requested("relation", "pr.a")` finds `tableName="pr.a"`, reveals the Raw XML tab, seeds the
  Find bar with `tableName="pr.a"` and populates Find All — i.e. identical outcome to the `"table"` case;
  (2) a relation the XML does not reference produces the new, honest status message (assert on the token
  appearing in the text, not on the exact sentence).
* `tests/ui/test_coherence_panel.py:314-319`
  (`test_double_click_on_a_relation_emits_the_name_signal`) currently pins `blocker.args ==
  ["relation", "pr.v"]` — this assertion **pins the bug in place** and must be updated to
  `["table", "pr.v"]` when fix (1) lands. Same for `tests/ui/test_coherence_wiring.py:190-208`
  (`test_double_click_on_a_relation_row_goes_through_the_name_jump`), which asserts `kind == "relation"`
  on the patched slot. Both should additionally assert the *effect* (the token searched / the Find bar
  seeded), not just the string that crosses the signal — asserting only the kind string is what let a
  wrong kind pass as "wired correctly".
* If `_ROW_ROLE` is normalized too, re-check any test reading that role (grep `_ROW_ROLE` /
  `Qt.ItemDataRole.UserRole` in `tests/ui/test_coherence_panel.py`).
No live PostgreSQL is needed anywhere for Facet A; the existing `_window(qtbot, tmp_path)` fixture and the
monkeypatched schema fetch in the coherence wiring tests are sufficient.

**Spec impact:** Facet B is a plain implementation bug against §17/§10 — the coherence view's `"lookup"`
kind is settled design (§17, FQ-003; the Pages-branch lookup rows and the `_XML_KINDS` set including
`"lookup"`), and the Properties panel simply failed to render it; **no design change, no spec edit.**
Facet A is likewise an implementation bug against settled §17 design, **not** an intentional decision:
§17's "Reuse mandate" paragraph (CONSOLIDATED_SPEC line ~1544-1550) states as binding that, carried over
from `DbCheckPanel` unchanged, are "the uniform 4-tuple UserRole payload `(kind, name, ok, is_calculated)`
on relation and column items" and "the signals … `jump_requested(kind, name)` / `jump_requested(line)`
(double-click → reveal Raw XML + `navigate_to_line`)". Emitting `"relation"` where the carried-over
contract says `"table"` is the divergence, so fixing it *restores* spec-conformance. **No `spec-maintainer`
dispatch is required for the fix itself.** Optional, low priority, after it lands: a one-line §17 note
making the host-facing kind vocabulary explicit ("`CoherenceNode.kind` is internal; the `rename_requested`
/ `name_jump_requested` / `_ROW_ROLE` surfaces use the carried-over `table`/`column` vocabulary") so the
next kind added to the tree cannot repeat this. **§18.5 D2/D2a is no longer implicated at all** — the
rejected sandbox hypothesis was the only reason it was cited. Do not edit `CONSOLIDATED_SPEC.md` here.

---

## BUG-033: Editing a function's DDL shows no "*" changed marker in the DDL Objects tree
**Status:** RESOLVED (4bc73b6) — THREE causes, and the third was decisive: (a) `dirty_changed` was wired only to the tab title, so `BrowserPanel` had no dirty channel; (b) `_save_ddl_object_editor` never recomputed markers — but a refresh alone would have changed NOTHING, because (c) `_checkout_and_edit` registered no `DeployedObject` and `compute_drift_markers` iterates `settings.deployed` alone, leaving the marker inert regardless. Checkout now registers `content_hash(live_source)`, NOT FQ-002's never-deployed sentinel `""` — the sentinel would make every fresh checkout read as `*` the instant it happened. An existing entry is never overwritten, since a real deploy reference outranks this inference. The two markers collapse in one place: dirty + drift `*` → `*`, drift `!` + dirty → `*!`, never `**`; keyed on `DdlObjectRef.key` so it survives `set_schema` rebuilds, and a trigger's two leaves both mark. The unsaved marker works PROJECTLESS by design — it is a property of the editor buffer, not of the project's deploy state.
**Reported:** 2026-08-06
**Report (verbatim):** "I modified a ddl of a function, but in the DDL Objects window I can't see the * that it was changed"

**Root cause:** The "DDL Objects" window is the left-dock tree `pgtp_editor/ui/ddl_buffer_panel.py::BrowserPanel` (`ddl_browser_panel`, dock titled "DDL Objects" at `main_window.py:312`). Its object-row labels get a `*` (or `!`) suffix ONLY from the §18.2 project *drift* markers: `BrowserPanel._build_routines_branch` (ddl_buffer_panel.py:260-262) and `_add_trigger_leaf` (ddl_buffer_panel.py:294-298) append `drift.marker_text` when a `DriftMarkers` entry exists for the object's `ddl/*.sql` path. Those markers come from `db/ddl_project.py::compute_drift_markers`, which compares each **checked-out `ddl/*.sql` file on disk** against the last-deployed reference (`locally_edited` → `*`). They say nothing about an open editor tab's in-memory buffer.

The editable tab is `pgtp_editor/ui/ddl_object_editor.py::DdlObjectEditorPanel`. Its dirty state is real and correctly tracked — `is_dirty()` reads `editor.document().isModified()`, and `dirty_changed` (Signal, emitted on clean↔dirty transitions via `document().modificationChanged`, ddl_object_editor.py:593) fires on edit. But in the host, `MainWindow._on_ddl_edit_requested` (main_window.py:3401-3403) wires `dirty_changed` ONLY to `center_stage.update_ddl_object_tab(ref)`, which repaints the **CenterStage tab title's** `" *"` (`CenterStage.update_ddl_object_tab` → `panel.tab_title()`, center_stage.py:266/338; marker built in `DdlObjectEditorPanel.tab_title`, ddl_object_editor.py:625-628). Nothing tells `BrowserPanel` that an object now has unsaved edits, so the tree row is never repainted.

So the reported symptom has two layers, both real:
- (a) An unsaved in-editor edit is per-tab dirty state that the tree has no channel to hear about — `dirty_changed` is not connected to any browser refresh. This is a missing capability, not a broken wire.
- (b) Even after the user SAVES the edit, `MainWindow._save_ddl_object_editor` (main_window.py:3681-3700) writes the `ddl/*.sql` file and calls `center_stage.update_ddl_object_tab` but does NOT recompute drift markers or call `BrowserPanel.set_schema` again — so the file-level `*` (which `compute_drift_markers` would now produce) also does not appear in the tree until the DDL Explorer is manually refreshed. And the `*` marker exists at all only when a DDL project is open (`drift_markers` is `None`/empty projectless — ddl_buffer_panel.py:186), so in projectless mode there is no `*` channel whatsoever.

**Proposed fix:** Two independent pieces; do both, and reuse the existing marker/refresh plumbing rather than inventing a parallel one.

1. Live in-editor dirty marker on the tree (the direct reading of the report). Give `BrowserPanel` a way to overlay an "open tab is dirty" marker keyed by object identity, then feed it from the panel's existing `dirty_changed`:
   - In `ddl_buffer_panel.py::BrowserPanel`, add a stored set/dict of dirty object keys (use `DdlObjectRef.key`-shaped tuples — the same `(kind, schema, name, table, arg_types)` identity `CenterStage` keys tabs on) and a public `set_object_dirty(ref, dirty: bool)` (or `set_dirty_objects(keys)`). When it changes, re-run the label build for the affected rows (simplest correct approach: re-call the existing `set_schema(self._schema, <spans>, drift_markers=…)` path, or refresh labels in place) so the row label gains/loses the marker. To match rows to keys, note the routine rows currently carry only a `_SPAN_ROLE` `DdlObjectSpan`; either store the `DdlObjectRef.key` on each object row via a new `UserRole` (e.g. `_OBJKEY_ROLE = Qt.ItemDataRole.UserRole + 3`) at build time in `_build_routines_branch`/`_add_trigger_leaf`, or resolve span→ref through the retained `self._schema` with `resolve_edit_target`. The former is simpler and avoids re-deriving overload disambiguation.
   - Reuse the app's established dirty glyph: the tab title uses `" *"` (ddl_object_editor.py:628, per §11/§18.5). Use the SAME `*` so the tree and the tab agree, and make it combine cleanly with the §18.2 `*`/`!` drift `marker_text` already appended on the same label (do not emit two `*`s — if the drift marker already shows `*`, the in-editor dirty state is subsumed; only add a marker when the drift path did not already add one).
   - In `main_window.py::_on_ddl_edit_requested` (the existing `dirty_changed` connection at 3401-3403), extend the same lambda (or add a second connection) to also call `self.ddl_browser_panel.set_object_dirty(ref, dirty)`. Clear it on save (`_save_ddl_object_editor`, after `panel.mark_clean()`) and on tab close/discard so a discarded edit drops the marker. There is one `dirty_changed` wiring site per open-tab path — note there are TWO panel-open sites: `_on_ddl_edit_requested` (main_window.py:3401) and the checkout path around main_window.py:3660 (`panel.dirty_changed.connect` at 3660); wire both, or better, factor the connection into one helper both call.

2. Refresh the file-level drift marker after a save (layer b). In `main_window.py::_save_ddl_object_editor`, after `panel.mark_clean()` and the existing `update_ddl_object_tab` call, recompute drift and rebuild the tree the same way the DDL Explorer refresh already does — reuse the exact `schema = getattr(self.ddl_browser_panel, "_schema", None)` + `compute_drift_markers(self._ddl_project_folder, self._ddl_project_settings, schema)` + `self.ddl_browser_panel.set_schema(schema, spans, drift_markers=…)` pattern used at main_window.py:3303-3308 (guard on a project being open and a schema being loaded, exactly as `_remind_pending_ddl_deploys_on_close` at 3018-3021 does). This makes the `*` the user expects appear immediately after Save, not only after a manual Explorer refresh. Gotcha: `set_schema` needs the `spans` list; confirm where the refresh path (main_window.py ~3300) obtains its `spans` and reuse that same source, do not re-synthesize a second time.

Gotchas: (i) `drift_markers` is `None`/empty projectless (ddl_buffer_panel.py:186) — piece 1 must still show the in-editor `*` projectless, since the report is about an edit not yet (or never to be) saved to a project file. (ii) Do not confuse the two `*` meanings: §18.2's `*` = "checked-out file differs from last-deployed" (`DriftMarkers.locally_edited`); the new one = "an open editor tab has unsaved changes for this object." Decide (and note in the row/tooltip if practical) that they collapse to one `*` glyph rather than stacking. (iii) Keep the dirty set keyed on `DdlObjectRef.key`, never a tree index — the tree is rebuilt wholesale on every `set_schema`, so any index-based tracking would go stale immediately.

**Test impact:** `tests/ui/test_ddl_buffer_panel.py` already covers `BrowserPanel` label building and the drift `marker_text` rendering — extend it with a case that `set_object_dirty(ref, True)` adds `*` to the matching routine/trigger row and `False` removes it, and that it does not double-mark a row that already carries a drift `*`. `tests/ui/test_ddl_object_editor_wiring.py` / `tests/ui/test_ddl_explorer_wiring.py` cover the MainWindow↔panel↔browser signal wiring — add a case that editing an open `DdlObjectEditorPanel` (drive `document().setModified(True)` or type text) propagates through `dirty_changed` to `ddl_browser_panel` and marks the row, and that saving via `_save_ddl_object_editor` rebuilds the tree so the file-level drift `*` appears (monkeypatch `compute_drift_markers` and the save path — the file write and any `QFileDialog`/`QMessageBox` must be patched, per the testing policy). `tests/ui/test_ddl_object_editor.py` already covers `tab_title`/`is_dirty`; no change needed there.

**Spec impact:** Diverges from / underspecified in `CONSOLIDATED_SPEC.md` §18.1 (BrowserPanel row markers) and §18.2 (`*`/`!` drift markers, `compute_drift_markers`, §18.2 lines ~2256, 2413-2418) and §18.5 (the editable tab's dirty state, ~3246-3268). The spec today defines the tree `*` strictly as the §18.2 **file-vs-last-deployed** drift marker and defines the editable tab's dirty `*` strictly as a **tab-title** marker; it does NOT say an unsaved in-editor edit should surface on the DDL Objects tree, nor that a save should refresh the tree. Whether to (a) show a live in-editor `*` on the tree at all and (b) how it relates to the §18.2 drift `*` is a design decision — flag for `spec-maintainer` after the fix lands so §18.1/§18.2/§18.5 state the combined marker semantics. Do not edit the spec here.

---

## BUG-034: Project Settings never imports the .pgtp's connection (quality fields empty) yet the app still connects from a different source
**Status:** RESOLVED (4bc73b6) — both halves confirmed: nothing ever WROTE `ProjectSettings.target`, and two of the three consumers never READ it (`_open_ddl_explorer` and `CoherenceController.run_check` each called `seed_params(tree, self._settings)` privately), so the app could genuinely connect with credentials the dialog was not showing. One source of truth now: `active_target_params(tree=None)` — project open ⇒ `ProjectSettings.target`, projectless ⇒ `seed_params` — which every consumer asks, the coherence lane by INJECTION rather than duplicating the selection. The `.pgtp` connection imports on open via the existing `connection_from_tree` (saved wins; the sandbox is never seeded). The password is prompted LAZILY at first connect, so opening a project raises no modal and a project you never connect from never asks for a secret; cancelling stores nothing and lets the connection fail visibly rather than substituting another credential. A fresh no-target project (FQ-007) shows blank and "Not configured.", explicitly NOT backfilled from app QSettings — silent backfilling is what made this invisible. DRIVE-BY of the same class: `_link_pgtp_to_project_if_needed` and `_deploy_pgtp` rebuilt `ProjectSettings` field-by-field and silently DROPPED `sandbox_mode`, quietly turning a "with data" project schema-only; both now use `dataclasses.replace`.
**Reported:** 2026-08-06
**Report (verbatim):** "the Project Settings is not picking up the database connection from the pgtp: the strange situation is that in Project settings I have quality fields empty yet it's connecting to the database. the expected behaviour is that opening the pgtp picks up database name, port, user, and password is requested, then saved in the json."

**Root cause:** Two independent facts combine into the reported "strange situation." Both verified in the code.

1. **Nothing ever populates `ProjectSettings.target` from the `.pgtp`, so the Project Settings "Target connection" fields render empty.** The `.pgtp` carries its design-time connection as a single `<ConnectionOptions ... host= port= login= database= password=/>` element (spec §17 line 1477; the parser for it is `pgtp_editor/db/config.py::connection_from_tree`, config.py:45-69, which maps `host`/`port`/`database` directly, `login`→`user`, and deliberately forces `password=""`). The `ProjectSettings` dataclass has `target: ConnectionParams` and `sandbox: ConnectionParams` fields (`pgtp_editor/db/ddl_project.py:115-116`), persisted to/from `.ddlproject/settings.json` by `save_settings`/`load_settings` (ddl_project.py:148/138). But neither project-entry path writes `.target`:
   - `MainWindow._create_ddl_project` (`pgtp_editor/ui/main_window.py:2058-2070`) builds `ProjectSettings(name=…, description=…, sandbox=dialog.sandbox_params(), sandbox_mode=…, git=…)` — no `target=` at all (and `NewProjectDialog` only exposes `sandbox_params()`, new_project_dialog.py:203, never a target), so `.target` stays at its `ConnectionParams()` default (all-empty).
   - `MainWindow._open_ddl_project` (main_window.py:2072-2107) and its `_auto_open_linked_pgtp` (main_window.py:2109-2139) just `load_settings(folder)` and open the linked `.pgtp` into the editor; nothing copies the `.pgtp`'s `<ConnectionOptions>` into `.target`.
   The Project Settings dialog then prefills its Target fields straight from `settings.target` (`ProjectSettingsDialog.set_settings` → `_set_connection_fields(settings.target, self._target_host_edit, …)`, project_settings_dialog.py:331-337), so with an all-empty `.target` the user sees empty quality fields — exactly the report.

2. **The live "yet it's connecting" path does NOT read `ProjectSettings.target` — it reads the app-level QSettings + the `.pgtp` tree via `seed_params`.** The two connect gestures both bypass `.target`:
   - DDL Explorer: `MainWindow._open_ddl_explorer` (main_window.py:2494-2503) computes `params = seed_params(tree, self._settings)` and fetches with that.
   - Coherence/DB check: `CoherenceController.run_check` (`pgtp_editor/ui/coherence_controller.py:256`) likewise does `params = seed_params(project.tree, self._settings)`.
   `seed_params` (config.py:95-120) merges the app-level saved QSettings connection (`load_connection`, the `_GROUP="db"` group — the same standalone "Connection Setup…" store from BUG-024) with the `.pgtp`'s `<ConnectionOptions>` (`connection_from_tree`), saved values winning. So the app connects using host/port/database/user pulled from the `.pgtp` (and/or a previously-saved app-level QSettings connection), never from `ProjectSettings.target`. `ProjectSettings.target` is in fact consulted by exactly **one** place — `_project_status_target` (main_window.py:2618-2627, the §18.8 Project Status window's Quality node) — and nowhere on the actual fetch path. That is why the fields are empty *and* the DB still connects: two competing connection sources, and Project Settings owns neither the population nor the live use.

This directly contradicts the shipped spec's own stated design: §17/§18.2 (CONSOLIDATED_SPEC.md:1547-1557, plus §18 line 1548) say that while a §18.2 project is open "its own `ProjectSettings` (`target`/`sandbox`) is the connection store" and the standalone Connection Setup dialog is disabled precisely because it "would be a redundant, silently-live shadow of it." In reality `ProjectSettings.target` is the thing that is dead, and the app-level `seed_params` path is the silently-live shadow. So the fix *restores* the spec's intent; it does not invent new policy.

**Proposed fix:** Make opening/entering a project import the `.pgtp` connection into `ProjectSettings.target`, prompt for the password once, persist to `settings.json`, and unify the connect path on `.target`. Concrete plan:

1. **Import `<ConnectionOptions>` into `.target` on project entry (host/port/database/user).** Add a single helper on `MainWindow` (e.g. `_import_pgtp_connection_into_target(self, settings, tree) -> ProjectSettings`) that: parses the `.pgtp` tree with the existing `connection_from_tree` (config.py:45 — reuse it, do NOT write a second `<ConnectionOptions>` parser); if it returns non-None and `settings.target.host` is empty (first import; do not clobber a target the user has already edited), builds an updated `ProjectSettings` (the file rebuilds this frozen-style dataclass via the `ProjectSettings(...)` copy pattern seen at main_window.py:2404-2412 and 2440-2448 — copy every field, set `target=<imported, with the prompted password>`), `save_settings(folder, updated)`, and stores it back on `self._ddl_project_settings`. Call this from the project-open path where the `.pgtp` tree becomes available: `_auto_open_linked_pgtp`/`open_project_file` already loads the `.pgtp` (the model exposes `.tree`, consumed the same way at main_window.py:2494-2498 and coherence_controller.py:256). The `.pgtp` tree, not the folder, is the source — so import must run after the working copy is parsed. Wire it for all three entry points that end in an active project + loaded `.pgtp`: plain `_open_ddl_project` (via `_auto_open_linked_pgtp`), the `_require_ddl_project` Open/Create → `on_ready` path, and `_create_ddl_project` when a `.pgtp` is linked at creation.

2. **Prompt for the password once, since the `.pgtp` never carries a usable one** (`connection_from_tree` forces `password=""`, by design — §17 line 1478 "password is never read from XML"). There is **no existing reusable password-only prompt** in the codebase (grep for `QInputDialog`/`getText` returns nothing; the only password entry is the full `ConnectionSetupDialog`/`ProjectSettingsDialog` forms). Two acceptable shapes, pick per the resolver's judgment: (a) a `modals.QInputDialog.getText(self, "Database Password", f"Password for {user}@{host}:{port}/{database}:", QLineEdit.EchoMode.Password)` prompt (smallest change; must be routed through `pgtp_editor/ui/modals.py` so tests can monkeypatch it, per the testing policy — confirm/extend `modals.py` to expose `QInputDialog` the way it already wraps `QFileDialog`/`QMessageBox`), or (b) reuse the full `ProjectSettingsDialog` pre-seeded with the imported host/port/db/user and let the user fill the password + Test before Save. Given the report explicitly says "password is requested, then saved in the json," (a) matches the ask most literally. Store the entered password into the imported `ConnectionParams` before `save_settings` — note `settings.json` stores passwords **plaintext** (§17 line 1478-1479; `_connection_to_dict` in ddl_project.py already serializes the password field), consistent with the existing target/sandbox storage, so no new caveat is needed beyond the one Project Settings already shows.

3. **Unify the connect path on `ProjectSettings.target` when a project is open.** Change `_open_ddl_explorer` (main_window.py:2499) and `CoherenceController.run_check` (coherence_controller.py:256) so that, when a project is active, they use `self._ddl_project_settings.target` (the store the spec designates authoritative) instead of `seed_params(tree, self._settings)`; fall back to `seed_params`/`load_connection` only in projectless mode. The cleanest form is to reuse the existing single selector `_project_status_target` (main_window.py:2618-2627: `settings.target if settings is not None else load_connection(self._settings)`) — promote it (or a sibling) into the one place both fetch paths ask for "the connection to use," so the Quality node, the reachability probe, and the actual DDL/coherence fetch can never diverge again. `CoherenceController` gets `self._settings` injected today; give it access to the active `ProjectSettings.target` the same way (it already holds a shell/host reference — thread the target through, do not duplicate the selection logic). Gotcha: the `if not params.host` guard that currently triggers `_prompt_missing_connection()` (main_window.py:2500-2502, coherence_controller.py:257-259) must keep working — with a project open and an empty `.target`, that guard should now route to Project Settings (it already does via `_prompt_missing_connection`, main_window.py:2006-2012), and step 1's import is what makes `.target` non-empty in the normal case.

Gotchas to not get wrong: (i) do the import only when `settings.target.host` is empty so reopening a project (or one where the user corrected the host in Project Settings) never silently reverts to the `.pgtp`'s value — same "saved wins" precedence `seed_params` already encodes. (ii) The sandbox must NOT be seeded from `<ConnectionOptions>` (spec §17 line 1503-1506 — that element is the *target*; seeding the sandbox from it is how someone points the sandbox at production). Only `.target` is imported. (iii) Rebuild `ProjectSettings` by copying all fields (name/description/pgtp/sandbox/sandbox_mode/git/deployed) — the two existing rebuild sites at main_window.py:2404 and 2440 are the template; dropping a field silently wipes it from `settings.json`.

**Test impact:** `tests/ui/test_ddl_project_wiring.py` already covers `_create_ddl_project`/`_open_ddl_project`/`_auto_open_linked_pgtp` (tests around lines 59-415) — extend it with: opening a project whose linked `.pgtp` has a `<ConnectionOptions host= port= login= database=/>` imports host/port/database/user into `ProjectSettings.target`, prompts for the password (monkeypatch the `modals` password prompt), and persists it to `settings.json` (assert via a fresh `load_settings`); and that a project with a non-empty existing `.target` is NOT clobbered on reopen. `tests/db/test_config.py` already covers `connection_from_tree` (password-always-blank, test at line 27) and `seed_params` — no change to those, but the new import helper's mapping should assert it reuses `connection_from_tree` (same `login`→`user`, blank password). `tests/ui/test_project_settings_dialog.py` covers `set_settings`/`target_params` — add a case that a `ProjectSettings` with an imported `.target` renders those fields populated in the dialog (guards the "empty fields" symptom). New wiring test for the unified connect path: with a project open, `_open_ddl_explorer` (and `CoherenceController.run_check`) fetches using `ProjectSettings.target`, not `seed_params` — monkeypatch the schema fetch and assert the `ConnectionParams` it receives equals `.target`, not the QSettings/`.pgtp`-seeded value. All modal calls (`QInputDialog`, `QFileDialog`, `QMessageBox`) must be monkeypatched per the testing policy.

**Spec impact:** This is a **divergence from CONSOLIDATED_SPEC §17/§18.2/§18** (lines 1547-1557, 1548), which already declares `ProjectSettings.target`/`sandbox` the authoritative connection store while a project is open — the code never populates or reads `.target` on the live path, so the fix restores conformance rather than changing policy. However, the spec does **not** currently define the `.pgtp`→`ProjectSettings.target` **import semantics** on project open (parse `<ConnectionOptions>` → `.target`, one-time password prompt, "saved wins so no clobber on reopen", sandbox-not-seeded). After the fix lands, flag for `spec-maintainer` to add that import-on-open contract to §18.2 (and to make §17/§18.2 explicit that the DDL Explorer / Coherence fetch paths source their connection from `ProjectSettings.target` when a project is open, not from `seed_params`). Do not edit the spec here.

---

## BUG-035: Project Status Sandbox1 node says "Schema only" when there is no schema — only a connection (tier over-reported from configured mode, never verified against the sandbox DB)
**Status:** RESOLVED (1c1a2c1) — `sandbox_mode` is now STRUCTURALLY unreachable from this derivation: `sandbox1_state` takes no mode and `data_clone_done = (sandbox_mode is WITH_DATA)` is gone. State comes from a tri-state `SandboxFact(UNKNOWN|ABSENT|PRESENT)` measured off the real sandbox — schema counted over `pg_class`/`pg_proc` excluding system/bookkeeping schemas and extension-owned objects (so a bare-but-owned sandbox and a `plpgsql_check` install both read as NOT provisioned), data by a per-table existence test. `reltuples` was rejected because `pg_restore` leaves it at -1, which would read a fresh clone as empty. Unknown data resolves DOWNWARD to "Schema only", never to "Data cloned". **ARTWORK OWED:** `sandbox1_unknown[_drk].svg` and `sandbox1_not_provisioned[_drk].svg` do not exist; both states alias onto `sandbox1_empty`'s SVG, so their captions are truthful but they look identical to "Schema only" until the art lands. A guard test fails loudly if an alias is removed without adding art.
**Reported:** 2026-08-06
**Report (verbatim):** "sandbox says schema only, but there's no schema, just a connection"

**Root cause:** The "Schema only" label is the **Sandbox1** node's caption (`pgtp_editor/ui/project_status_panel.py:160`, `_STATE_CAPTIONS["sandbox1_empty"] = "Schema only"`), rendered whenever the Sandbox1 node's state resolves to `Sandbox1State.EMPTY`. That state is computed **purely from the project's configured sandbox mode and a config-derived clone flag — it never verifies that the baseline schema/DDL was actually provisioned into the sandbox DB.** The chain, all verified in the code:

1. `sandbox1_state(mode, data_clone_done)` (`pgtp_editor/ui/project_status_model.py:270-283`) returns `FILLED` only for `WITH_DATA` **and** `data_clone_done`; **everything else — including every `SCHEMA_ONLY` project — returns `EMPTY`**, unconditionally. There is no schema-presence input to this function at all; its only inputs are the mode enum and a bool.
2. The bool is a **pure config derivation, not a DB fact.** `MainWindow._build_project_status_diagram` (`pgtp_editor/ui/main_window.py:2645-2650`) calls `build_diagram(..., sandbox_mode=sandbox_mode, data_clone_done=sandbox_mode is SandboxMode.WITH_DATA, ...)` where `sandbox_mode = settings.sandbox_mode` (main_window.py:2644) — i.e. `data_clone_done` is just "is the recorded mode WITH_DATA", never a check of what is really in the sandbox. So for a `SCHEMA_ONLY` project, Sandbox1 is `EMPTY` → "Schema only" the instant the project is opened, before anything is provisioned.
3. The Sandbox1 trio renders at all only when the sandbox is **tier DEVELOPMENT** (`build_diagram`, project_status_model.py:450-466 gates on `degradation is not NOT_CONFIGURED`, and `sandbox_state` project_status_model.py:257 maps `ProjectTier.DEVELOPMENT` → CONNECTED). But `determine_project_tier` (`pgtp_editor/db/sandbox.py:409-457`) grants DEVELOPMENT purely from **connectivity + config**: sandbox configured, `probe.probe_error is None`, and (WITH_DATA only) clone tools on PATH. **It never introspects for schema objects.** So a sandbox that is merely reachable — freshly `create_sandbox_database`'d but not yet provisioned, or **reset** (`SandboxSession.reset()`, sandbox.py:1047-1064, `DROP SCHEMA … CASCADE` per BUG-032 facet A, before re-provisioning) — is tier DEVELOPMENT, renders the Sandbox1 node, and is captioned "Schema only" although no app schema exists.
4. Nothing in the probe would even carry schema presence. `probe`/`SandboxCapabilities` (sandbox.py:88-198) query only `server_version_num`, `is_superuser`, installed/available extensions, `current_database()`, and the `pg_database` COMMENT `owner_marker`. The `owner_marker` is stamped at **DB-creation** time by `create_sandbox_database` (sandbox.py:680-685) — *before* provisioning — so `is_app_owned` (sandbox.py:623-636) being true tells you the DB is ours, **not** that the schema was ever installed. There is no provisioning marker/version, and the probe does not run any `pg_namespace`/`pg_class` count against the sandbox schemas.

Net: "Schema only" is asserted from the *configured mode alone*. It means "this project is a schema-only-mode project," when the user reads it (correctly) as "the schema is present, only data is missing." The true state — reachable/owned but unprovisioned — has no representation; it is silently mislabelled as the higher "schema present" state.

**Proposed fix:** Make the Sandbox1 state reflect *verified schema presence in the sandbox DB*, and give the honest lower state a caption. Concrete plan:

1. **Add a schema-presence signal to the probe (the one round trip that already runs on open and on Project Status open).** Extend `PROBE_SQL` (`pgtp_editor/db/sandbox.py:88-95`) with one more query counting app schema objects — e.g. user schemas excluding the reserved `BOOKKEEPING_SCHEMA` (`pgtp_editor_sandbox`, sandbox.py:620) and the PG system schemas the way `db/introspect.py::SCHEMA_SQL` already filters (`n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'`, introspect.py:184-206) — and surface the result as a new `SandboxCapabilities` field (e.g. `schema_provisioned: bool` or `provisioned_object_count: int`, default False/0 so a probe error stays "unknown/not provisioned", matching the never-degrade-to-absent posture of `plpgsql_check_state`, sandbox.py:130-146). Read it in `probe` alongside the existing rows (sandbox.py:176-194). Keep it one connection / one round trip — do NOT open a second probe. (Alternative, weaker: a provisioning marker/version written by `provision_sandbox`; but a real object count is authoritative and survives a hand-edited marker, and directly catches the reset case.)
2. **Feed that fact into `sandbox1_state` and add the honest lower state.** Add a third `Sandbox1State` member for reachable-but-not-provisioned (e.g. `NOT_PROVISIONED = "sandbox1_not_provisioned"`) with its own caption in `_STATE_CAPTIONS` (project_status_panel.py:150-164) — something like `"Not provisioned"` / `"Connected — no schema yet"` (final wording is the resolver's call, but it MUST NOT say "schema"). Change `sandbox1_state(project_status_model.py:270-283)` to take the schema-presence fact and return: `FILLED` (WITH_DATA + data actually present), the new NOT_PROVISIONED when the schema is absent, and `EMPTY`/"Schema only" **only when the schema is genuinely present but no data is** (SCHEMA_ONLY provisioned, or WITH_DATA whose clone hasn't landed). Note a new `.svg` asset (`sandbox1_not_provisioned[_drk].svg`) is required in `pgtp_editor/resources/status/`, guarded by `all_asset_stems()`/the asset-existence test — a missing asset ships as a silently blank node (per §18.8's stated pipeline), so the asset must land with the enum value. If producing the art is out of scope for this fix, reuse `sandbox1_empty`'s icon for the new stem's `asset_filename` **only as an explicit interim**, but still change the caption so the *text* stops lying.
3. **Wire the new input through `build_diagram` and the caller.** `build_diagram` (project_status_model.py:400-466) already has `status.capabilities` in scope (used for `sandbox2_state`, line 453) — pass the schema-presence fact from `status.capabilities` into `sandbox1_state` there, and correspondingly stop deriving fill purely from mode. `MainWindow._build_project_status_diagram` (main_window.py:2645-2650) then no longer needs the fake `data_clone_done=sandbox_mode is SandboxMode.WITH_DATA`; the real data/schema facts come from the probe result it already holds (`self._ddl_project_capability_status`).

Gotchas: (i) A probe error must resolve to the *lower* state (not-provisioned/unknown), never "Schema only" — mirror `plpgsql_check_state`'s "unknown, never absent" discipline so a transient outage doesn't flip the label the wrong way. (ii) Exclude `BOOKKEEPING_SCHEMA` from the object count or a bare-but-owned sandbox (which always has the bookkeeping schema) would read as provisioned. (iii) This interacts with BUG-032 facet A: after `reset()` drops schemas and before re-provision completes, the count is 0 → NOT_PROVISIONED, which is the correct honest state; ensure the fix doesn't assume reset always immediately re-provisions. (iv) Relates to FQ-007 (eager provisioning): if/when provisioning becomes eager on sandbox creation, the DEVELOPMENT-tier window in which the sandbox is reachable-but-unprovisioned shrinks but does not vanish (reset, failed provision) — the verified check is still required.

**Test impact:** `tests/ui/test_project_status_model.py` covers `sandbox1_state`/`build_diagram`/the state enums — extend it: `sandbox1_state` returns the new NOT_PROVISIONED when schema-presence is false (both SCHEMA_ONLY and WITH_DATA), returns EMPTY only when schema present + data absent, and FILLED only when WITH_DATA + data present; and `build_diagram` threads `status.capabilities`' schema-presence fact into the Sandbox1 node's asset/state. `tests/ui/test_project_status_panel.py` covers `_STATE_CAPTIONS` and node captions — add a case asserting the not-provisioned caption text (and that no caption for a schema-absent sandbox contains "Schema"). `tests/db/test_sandbox.py` covers `probe`/`SandboxCapabilities`/`determine_project_tier` — add a case that `probe` populates the new schema-presence field from the extra `PROBE_SQL` row (via the injected `runner` fake — extend its recorded rows to include the new query), True when app schema objects exist, False when only `BOOKKEEPING_SCHEMA`/system schemas do, and False on `probe_error`. Confirm `all_asset_stems()`'s asset-existence test now expects the new `sandbox1_not_provisioned[_drk].svg` stem. Add the new stem to whichever fixture enumerates expected assets. All Qt modals stay monkeypatched per the testing policy; these are mostly pure-model tests and need none.

**Spec impact:** **Divergence from CONSOLIDATED_SPEC §18.8**, not an intentional decision — the spec's Sandbox1 row (CONSOLIDATED_SPEC.md:4935) already states the node represents "the sandbox's **data-fill** status … **and whether that provisioning succeeded**", backed by "D2a's clone outcome / … `sandbox_mode` … **plus success/failure of the last provisioning run**." The shipped code implements only the mode half and drops the "provisioning succeeded" half, so the fix restores the spec's stated intent. However §18.8 enumerates only two Sandbox1 states (`sandbox1_empty`/`sandbox1_filled`) and §18's tier taxonomy (top of §18; §18.5 D2/D2a) treats a reachable configured sandbox as tier-3 DEVELOPMENT without a "reachable-but-unprovisioned" rung. After the fix lands, flag for `spec-maintainer` to: (a) add the third Sandbox1 state (not-provisioned) and its asset to §18.8's state table and asset-convention note; and (b) decide/record whether "reachable but unprovisioned" is a distinct sub-state of tier-3 in the §18/§18.5 taxonomy or stays a Sandbox1-only distinction (the Sandbox node itself can remain CONNECTED). Do not edit the spec here.

---

## BUG-036: Six windows/dialogs need specific default sizes (batch UI-sizing pass)
**Status:** RESOLVED (b799f21 + owner ruling 2026-08-09) — four of six applied with `resize()`, every window's minimum kept strictly below its opening size so all stay freely resizable: Project Settings 560x760, Sandbox Setup 660x1000, Project Status 720x440, New Function/Procedure 560x200. The acceptance criterion was verified rather than assumed — each window built offscreen at target and checked for children escaping their parent, children below their own minimumSizeHint, and wrapping labels needing more height than they have. **#4 Caption Filter is MOOT** — that dialog was deleted by FQ-017 (02e47e0). **#6 Open / Save As: the 720x440 requirement is DROPPED by owner ruling (2026-08-09) — no size was applied and none is expected.** These two stay **native** `QFileDialog` static calls whose geometry the OS owns; the owner explicitly accepts that they open at whatever size the OS gives them. Option (b) — switching every file picker to `DontUseNativeDialog` instances so they could be sized — was offered plainly and **declined**: keeping recent places, cloud locations and the OS-native look in every file picker (including §18.2's project chooser and BUG-022's directory picker) is worth more than a consistent opening size for two of them. **A future reader must not read this as a size that was applied and later lost — none was ever applied to #6, by decision.** Across the four that did get sizes: deliberately NOT clamped to screen height (would make the opening size environment-dependent and untestable) and no QScrollArea added (nothing clips).
**Reported:** 2026-08-06
**Report (verbatim):** "Specific default window dimensions (width x height, pixels) for six windows/dialogs: 1. Project Settings window → 560x760; 2. Sandbox Setup → 660x1000; 3. Project Status → 720x440; 4. Caption filter → 360x290; 5. New function / procedure → 560x200; 6. Open, Save As dialogs → 720x440."

**CONFIRMED by user:** all six dimensions are the **OPENING (initial) size, then freely user-RESIZABLE**. Use `self.resize(W, H)` for all six — NOT `setFixedSize` (would lock the window) and NOT a `setMinimumSize` at these values (would prevent shrinking). Any existing minimum must stay strictly *smaller* than the opening size so the window is still shrinkable. Sizes are logical pixels; on HiDPI Qt scales them by the device pixel ratio automatically — do not pre-multiply.

**ACCEPTANCE CRITERION (user, mandatory — this is a requirement on the fix, not just a size assignment):** "at open it should show all information correctly." At the specified opening size, **every field, label, and control must be fully visible and readable — nothing clipped, cut off, hidden, or scrolled-out** — while the window remains freely resizable afterward. So for each window the fix must actually *make the content fit* at the opening size, not merely call `resize()` and leave content truncated. If a layout would clip at the requested size, the fix must correct it — via a proper `sizeHint`/`minimumSizeHint`, wrapping overflow-prone content in a `QScrollArea`, or fixing the layout — OR the requested number must be flagged back to the user as too small (see per-window content-fit notes). The resolver's acceptance test: open each window at its specified size and confirm no truncation / no cut-off panels / no hidden buttons, then confirm it still resizes freely.

**Root cause / current state per window** (each is "size never set" or "set to a different value", not a broken mechanism — this is an incidental-defaults pass, not a regression fix):

| # | Window / dialog | Class | File | Where size is / should be set | Target WxH | Current |
|---|---|---|---|---|---|---|
| 1 | Project Settings | `ProjectSettingsDialog` | `pgtp_editor/ui/project_settings_dialog.py` | `__init__`, line **210** (`self.resize(560, 480)`) | 560x760 | `resize(560, 480)` — width already 560, only height wrong |
| 2 | Sandbox Setup | `SandboxSetupDialog` | `pgtp_editor/ui/sandbox_setup_dialog.py` | `__init__` (class line 178, ctor line 202, title line 214) — **no** resize/min/fixed anywhere; add at end of `__init__` | 660x1000 | unset (Qt auto-sizes to layout) |
| 3 | Project Status | `ProjectStatusPanel` (a `QWidget` shown as top-level window) | `pgtp_editor/ui/project_status_panel.py` (+ open site in `main_window.py`) | ctor has `self.setMinimumSize(QSize(420, 320))` at **line 656**; add `self.resize(720, 440)` after it (or set on the panel at the `main_window.py:3372` open site, just before `panel.show()`) | 720x440 | only minimum 420x320; no default size |
| 4 | Caption Filter | `CaptionFindReplaceDialog` (title "Caption Filter" when `replace_enabled=False`) | `pgtp_editor/ui/caption_find_replace_dialog.py` (class line 64, ctor line 65, title line 77) | `__init__`, at end — **no** sizing today | 360x290 | unset |
| 5 | New Function/Procedure | `NewRoutineDialog` (title "New Function/Procedure") | `pgtp_editor/ui/new_routine_dialog.py` (class line 103, ctor line 104, title line 106) | `__init__`, at end — **no** sizing today | 560x200 | unset |
| 6 | Open / Save As | native `QFileDialog` static calls (`modals.QFileDialog`) | `pgtp_editor/ui/pgtp_document_controller.py` (Open `open_dialog` line 352-357 `getOpenFileName`; Save As `save_as` line 588-593 `getSaveFileName`) — mirrored in `main_window.py` (`_open_project` line 1132, `_save_project_as` line 1464) | see caveat — **not directly sizable while native** | 720x440 | native OS dialog, size OS-controlled |

**Proposed fix (per window):**

1. **Project Settings (560x760) — resizable default.** The tabbed layout from BUG-025 has **already landed on this branch** (`QTabWidget` built at line 182, four tabs added lines 188-204, `self.resize(560, 480)` at line 210) — so this is a one-token change: edit line 210 to `self.resize(560, 760)`. **Coordinate with BUG-025:** if BUG-025 is re-worked/re-resolved, the 560x760 default belongs *with* that same `resize()` call, not a second one. Keep it a `resize()` (BUG-025 explicitly rejected `setFixedSize`). **Content fit:** the tabbed refactor moved the field groups onto four tabs, so any single tab shows only its own group — 560x760 should comfortably clear the tallest tab (Connections: ~5 rows + sandbox-mode sub-form; Deploy manifest: a `QTableWidget` + two buttons). Verify the Deploy-manifest table and the Connections tab both fully show at 560x760 with the OK/Cancel box (below the tabs) visible; the extra height over the old 480 is exactly to satisfy "show all information."

2. **Sandbox Setup (660x1000) — resizable default.** Add `self.resize(660, 1000)` at the end of `SandboxSetupDialog.__init__` (after the layout is fully built, so it wins over layout size hints). **Caveat to honor but flag:** 1000px tall exceeds many laptop/short screens — resizable-default handles this (user can shrink it); still prefer `resize()` over `setFixedSize`/`setMinimumSize`, and consider clamping to available height, e.g. `h = min(1000, self.screen().availableGeometry().height())` then `self.resize(660, h)` (guard `self.screen()` for None on an unparented dialog under offscreen). Honor 660x1000 as the *default* per the request. **Content fit:** this is the densest dialog (~15 `addRow`/`addWidget` groups) — that density is exactly why 1000px was requested, so at 660x1000 all rows should show. BUT because the clamp above may reduce the height on short screens, the "show all information" requirement is at risk there: if the dialog's natural content is taller than the clamped height, wrap its body in a `QScrollArea` so nothing is cut off on short screens while the default stays 660x1000 on tall ones. Verify at 660x1000 every row/field/button is visible. **Coordinate with FQ-007** (New-Project sandbox step CREATE+provision rework, still QUEUED): if FQ-007 restructures this dialog, apply the size and the scroll-area content-fit within that effort.

3. **Project Status (720x440) — resizable default.** Add `self.resize(720, 440)` in `ProjectStatusPanel.__init__` right after `self.setMinimumSize(QSize(420, 320))` (line 656) — the existing 420x320 minimum is < 720x440 so it stays shrinkable. Alternatively set it at the open site in `main_window.py` (line ~3372, before `panel.show()` alongside `panel.setWindowFlag(...)`/`setWindowTitle(...)`); prefer the ctor so any future opener inherits it. **Content fit (dense — check carefully):** this window renders the node diagram (a horizontal row of fixed-size `_DiagramNode` frames, each `setFixedSize` at line 396) plus captions; the row's natural width can exceed 720 depending on node count/DPI. If the diagram is wider/taller than 720x440 at normal DPI, nodes will be clipped at the opening size — that violates the acceptance criterion. Verify the full node row + captions fit at 720x440; if not, either the diagram already lives in a scroll area (confirm) or the fix must ensure it does, so nothing is cut off at the opening size while still resizable. **Coordinate with BUG-029/030/031/035** (all touch this window): 029 (clipped/blurry PNGs) and 035 (Sandbox1 taxonomy) change diagram *content* and may grow the natural size — apply the 720x440 default within/after those and re-verify content-fit against the changed diagram; if the diagram's own content genuinely needs more than 720x440, flag back rather than clipping (720x440 is the requested default, not a hard cap). 031 (reopen bug) is orthogonal but shares the open site.

4. **Caption Filter (360x290) — resizable default.** Add `self.resize(360, 290)` at the end of `CaptionFindReplaceDialog.__init__`. Note this class is dual-purpose: `replace_enabled=True` → "Caption Replace", `False` → "Caption Filter". The request names only the Filter variant (360x290). Decision for resolver: either size only when `not replace_enabled`, or size both (the Replace variant adds a "Replace with:" row + a Replace All button and may want to be taller). Simplest honoring of the literal request: `self.resize(360, 290)` for the Filter variant; guard with `if not replace_enabled` so the taller Replace variant isn't forced into 290px. **Content fit:** the Filter variant packs "Find what:" row, a Search-Mode box (multiple radios), a "Match case" checkbox, a scope box (In selection / Global radios), an error label, and Filter/Close buttons — moderately dense. 360x290 is plausible but not generous; verify at 360x290 that the scope box and both buttons are fully visible and no radio label is clipped horizontally at 360 wide. If it clips, widen the layout's tolerance or flag 360x290 as slightly small; do NOT leave any control cut off.

5. **New Function/Procedure (560x200) — resizable default.** Add `self.resize(560, 200)` at the end of `NewRoutineDialog.__init__` (after the button box wiring around lines 133-185). **Content fit (SHORTEST size — check for conflict):** the content is compact — a 3-row `QFormLayout` ("Name:" `QLineEdit`, "Kind:" `QComboBox`, "Returns:" `QComboBox`), an error `QLabel`, and the OK/Cancel `QDialogButtonBox` (lines ~104-186). 560 wide is ample; 200 tall is tight but plausible for 3 rows + label + buttons at normal DPI. **Flag:** 200px is the smallest requested opening height — verify the error label (which grows when a validation message appears) does not push the OK/Cancel buttons out of view at 200px. Because the dialog is resizable, a user can grow it, but the acceptance criterion applies at the *opening* size: if a populated error message clips the buttons at 560x200, the layout must accommodate it (e.g. let the error label wrap/reserve a line) or the height be revisited with the user. Confirm all three rows + buttons are visible at 560x200 both with and without an error message shown.

6. **Open / Save As (720x440) — DECISION REQUIRED, do not silently switch.** Every Open/Save As is a **native** static `QFileDialog` call (`getOpenFileName`/`getSaveFileName`, no `DontUseNativeDialog` option anywhere in the tree). **Native dialog size is OS-controlled and generally cannot be forced** — `resize()`/`setFixedSize` have no effect on a native dialog. To honor 720x440 you must switch these to the **non-native** Qt dialog: construct a `QFileDialog` instance with `options=QFileDialog.Option.DontUseNativeDialog` (or `dlg.setOption(...)`), `dlg.resize(720, 440)`, then `dlg.exec()` and read `selectedFiles()`. This **changes look-and-feel and behavior on every platform** and loses OS niceties (recent-places, cloud locations). It affects the shared file-dialog surface, including the §18.2 Open-Project folder chooser and directory pickers touched by **BUG-022**. **Recommendation:** either (a) accept native and *drop the 720x440 request for these two* (lowest risk, recommended), or (b) do a deliberate app-wide switch to non-native dialogs and size them — but that is a cross-cutting change the user should confirm, not a side effect of this sizing pass. Flag for the user/resolver to choose before touching any `QFileDialog` call site.

   **OWNER RULING (2026-08-09) — option (a). Requirement DROPPED, closed, do not revisit as a bug.** `Open` and `Save As` stay **native** static `QFileDialog` calls; the 720x440 target for #6 is withdrawn and these two dialogs open at whatever size the OS gives them. Reasoning recorded by the owner: users keep recent places, cloud locations and the OS-native look in **every** file picker in the app, and that is worth more than a consistent opening size for two of them. Option (b) was presented plainly — with its cost (constructing `QFileDialog` instances with `DontUseNativeDialog` across every file picker, including §18.2's project chooser and BUG-022's directory picker) — and **declined**. Consequences for anyone reading this later: **no `resize()`, no `DontUseNativeDialog`, and no `QFileDialog` instance construction was introduced for #6, and none should be added.** If a future report again asks for a fixed Open/Save As size, it is a re-litigation of this ruling, not a regression — nothing was implemented and then lost.

**Gotchas:** call `resize()` *after* the dialog's layout is fully built (end of `__init__`) so it overrides layout size hints. Under `QT_QPA_PLATFORM=offscreen` (tests) `self.screen()` may be None on an unparented dialog — guard the sandbox screen-height clamp. Do NOT use `setFixedSize` and do NOT raise any `setMinimumSize` to these values — all six must stay freely resizable after opening (user-confirmed). The "show all information at opening size" acceptance criterion means a bare `resize()` is NOT sufficient where content would clip: the shortest requests (New Function/Procedure 560x200) and the densest (Sandbox Setup 660x1000 under short-screen clamp; Project Status 720x440 with a wide node row) are the ones to actually open and eyeball / add a `QScrollArea` for, per their per-window notes above.

**Test impact:** Sizing is essentially **not unit-tested today** — grep confirms no test asserts window `size()`/`width()`/`height()` for any of these dialogs. Note the "show all information at opening size" acceptance criterion is primarily a **manual/visual** check (open each window at its size, confirm nothing clipped, then confirm it resizes) — hard to assert meaningfully in a headless offscreen test; per project policy, ask the user to verify manually after the automated tests pass. If any window needs a `QScrollArea` or layout change to fit content (New Function/Procedure, Sandbox Setup short-screen, Project Status wide diagram), THAT structural change *is* testable — assert the scroll area exists / the content widget's `minimumSizeHint` fits, and any existing content-visibility test for that dialog stays green. The size hits in `tests/ui/test_project_status_panel.py` (lines 127-161) assert *icon/pad* geometry, not window size, and are unaffected. Existing per-dialog test files exist and stay green with no change: `tests/ui/test_project_settings_dialog.py`, `tests/ui/test_sandbox_setup_dialog.py` (+ `test_sandbox_setup_wiring.py`), `tests/ui/test_project_status_panel.py` (+ `test_project_status_model.py`), `tests/ui/test_caption_find_replace_dialog.py`, `tests/ui/test_new_routine_dialog.py`. New cases are optional and low-value (asserting a `resize()` default that Qt/WM may adjust is brittle); if the resolver wants regression coverage, assert the *requested default* immediately post-construction before any show, e.g. `assert dlg.size() == QSize(560, 760)` — and skip window #6 entirely (native dialogs can't be size-asserted; only test it if option (b) non-native switch is chosen, then assert `dlg.size()` on the constructed instance). All Qt modals stay monkeypatched per the testing policy; note that asserting sizes on `QFileDialog` requires patching to *return the instance*, not just a path.

**Spec impact:** None of §18.2, §18.8, the caption sections, or the sandbox sections currently specify pixel dimensions for these windows (grep found no size numbers there), so setting defaults introduces no divergence and needs no spec change for windows 1-5. **Exception:** window #6 — if the resolver chooses option (b) (switch Open/Save As to non-native Qt dialogs), that is a user-visible behavior/look change to the app-wide file-dialog surface (touches §18.2's Open-Project chooser and BUG-022's directory picker); flag for `spec-maintainer` to record the native→non-native decision after it lands. Option (a) (keep native, drop the size for #6) needs no spec change. **SETTLED (owner ruling 2026-08-09): option (a) was chosen — the file-dialog surface stays native and the 720x440 requirement for #6 is dropped. Nothing changed in the app's file-dialog behavior, so there is no divergence and NOTHING for `spec-maintainer` to fold in for this entry.**

---

## BUG-037: Raw XML tab gives no visual clue it is read-only in Caption Mode — its title should change to "Raw XML (read only in caption mode)"
**Status:** RESOLVED (75e2cdb) — **already fixed before this entry was picked up**, by FQ-021a's
"read-only is a set of reasons" refactor rather than by the two-`setTabText`-calls fix proposed here.
The title is computed in ONE place, `CenterStage._set_raw_xml_read_only`, from a SET of active reasons:
`RAW_XML_TAB_TITLE` plus `" (read only in " + " + ".join(sorted(reasons)) + ")"`, with
`RAW_XML_READ_ONLY_CAPTION_MODE == "caption mode"`. Caption mode alone therefore renders exactly the
reported string, `"Raw XML (read only in caption mode)"`. That shape is strictly better than the one
proposed: it was driven by Compare/Merge becoming a second read-only holder, so a user locked out by
BOTH modes is told there are two to leave rather than one, the reasons are sorted for a deterministic
title, and `leave_caption_mode` discards only its own reason instead of resetting the whole set — the
bug the proposal's plain "restore the plain title" restore path would have introduced. Verified by the
owner in the running app 2026-08-09.
**Reported:** 2026-08-07
**Report (verbatim):** "When I enter caption mode, Raw XML becomes read only for technical reasons, but there's no visual clue for that. The title of the tab should change to \"Raw XML (read only in caption mode)\", to avoid confusion."

**Root cause:** `pgtp_editor/ui/center_stage.py`, `CenterStage.enter_caption_mode` (lines 312-318) and `CenterStage.leave_caption_mode` (lines 320-326). Entering caption mode makes the editor read-only via `self.xml_editor.setReadOnly(True)` (line 316) while keeping the Raw XML tab visible (Phase 1 change — Raw XML is no longer hidden during caption mode, per the method docstrings), but neither method touches the tab's title. The Raw XML tab text is set once, statically, to the literal `"Raw XML"` at construction time (`center_stage.py:173`, `self.raw_xml_tab_index = self.addTab(self.raw_xml_tab, "Raw XML")`) and never updated thereafter, so the read-only state has no on-tab affordance. There IS a separate status-bar indicator — `MainWindow._enter_caption_mode` sets `self._mode_label.setText("Caption Mode (XML read-only)")` (`main_window.py:2049`) and `_close_caption_mode` restores `"Editing Mode"` (`main_window.py:2104`) — but that is a global mode label at the bottom of the window, not on the tab the user is confused about. The tab-title symptom is real and unaddressed.

**Proposed fix:** Update the Raw XML tab title inside the two existing CenterStage methods, mirroring the pattern already used elsewhere in this file for dynamic tab titles (`self.setTabText(index, ...)` at `center_stage.py:379` and `:577`, and the dirty-marker retitle in `xsd_controller.py:337`).
- In `CenterStage.enter_caption_mode` (after line 316's `setReadOnly(True)`), add `self.setTabText(self.raw_xml_tab_index, "Raw XML (read only in caption mode)")`.
- In `CenterStage.leave_caption_mode` (alongside line 323's `setReadOnly(False)`), add `self.setTabText(self.raw_xml_tab_index, "Raw XML")` to restore the plain title.
- Define the two strings as module-/class-level constants (e.g. `RAW_XML_TAB_TITLE = "Raw XML"` and `RAW_XML_TAB_TITLE_CAPTION_MODE = "Raw XML (read only in caption mode)"`) and reuse the plain constant at the construction site (`center_stage.py:173`) so the "normal" title lives in exactly one place — the restore path and the initial `addTab` must never drift apart.
- Gotchas: (1) Put both changes in `CenterStage`, NOT in `MainWindow._enter_caption_mode`/`_close_caption_mode` — the read-only toggle itself already lives in `CenterStage`, so the title (which is a pure function of that same state) belongs beside it and stays correct for every entry path (`enter_caption_mode_for_table` / `_table_details` / `_field` all route through `MainWindow._enter_caption_mode` → `CenterStage.enter_caption_mode`, and the panel Close button routes through `_close_caption_mode` → `CenterStage.leave_caption_mode`, so both sides are covered by the two CenterStage methods alone). (2) Do NOT strip the Raw XML tab's close button or otherwise touch the tab-close wiring at lines 213-220 — the retitle must not change the tab's structural (non-closable) status. (3) Leave `MainWindow._mode_label` exactly as is; the tab title is an addition, not a replacement — both cues should be present.

**Test impact:** `tests/ui/test_center_stage.py` already covers both transitions and is the right place to extend, not duplicate: `test_enter_caption_mode_keeps_raw_visible_readonly_shows_caption` (line 167) already asserts the read-only + visibility state on enter — add `assert stage.tabText(stage.raw_xml_tab_index) == "Raw XML (read only in caption mode)"`; `test_leave_caption_mode_restores_raw` (line 178) already asserts restore-on-leave — add `assert stage.tabText(stage.raw_xml_tab_index) == "Raw XML"`. The initial-title assertion at line 16 (`assert stage.tabText(2) == "Raw XML"`) stays green if the constant equals the current literal, and should be left as a guard that construction still uses the plain title. No new test file is needed.

**Spec impact:** None. §13 (Captions) and §6.1's tab-visibility notes describe Caption Mode's "Raw XML stays visible but read-only" Phase 1 behavior but do not specify the Raw XML tab's title text, so adding a read-only title suffix introduces no divergence from CONSOLIDATED_SPEC. (If the spec-maintainer later wants the read-only tab-title cue recorded as intended behavior alongside the existing `_mode_label` "Caption Mode (XML read-only)" cue, that is a nice-to-have, not a required spec reconciliation.)

---

## BUG-038: Checking a trigger FUNCTION tab in the sandbox errors "missing trigger relation" — relid never plumbed through for a `kind=="function"`/`return_type=="trigger"` routine

**Status:** RESOLVED (4828e3d; spec §18.5 D3a/§18.6, open item in §29) — triage option **(b)**, as the entry
recommended: `CheckRequest` gains a `relation_schema`/`relation_table` pair rather than widening `table`,
which is trigger-only by contract and is read by `working_set_ref` (the `applied` PRIMARY KEY) and
`trigger_drop_target` — widening it would have changed the bookkeeping key of every such object and could
have emitted a `DROP TRIGGER` for a function. `regclass_text` is the single point where the two shapes
meet, so `build_resolve_sql` / `build_check_sql` / `build_guarded_check_sql` (the last being
`apply_and_check`'s one-transaction shape, i.e. the reported Apply gesture) needed no change at all.
`MainWindow._trigger_relation_for` is the mirror of `_trigger_function_for` and takes **two facts from the
two authorities that own them**: that the routine returns `trigger` is read off the BUFFER (the same
principle as the `EXECUTE` clause — an edit that turns a plain function into a trigger function counts
immediately), and WHICH relation from `SchemaIndex.trigger_for_function`, the reverse lookup NEW./OLD.
completion already uses, so "which trigger owns this function" has one answer in the app. Gotcha 3 landed
as predicted: a relation absent from the sandbox now degrades to `REASON_RELATION_ABSENT` (a clean
`unavailable`) instead of erroring. **Gotcha 5 is moot** — `TriggerInfo` carries no
`tgoldtable`/`tgnewtable`, so there are no transition tables to thread through; introspection would have
to capture them first. **Gotcha 4's nice-to-have was NOT implemented and is now an open question in spec
§29:** an unattached trigger function still surfaces the raw server *"missing trigger relation"* rather
than a stated `unavailable` reason — the one place in the app where a raw PostgreSQL string reaches the
user, awaiting an owner ruling.
**Reported:** 2026-08-08
**Report (verbatim):** "When I run a trigger function on sandbox, it errors with '[Check] tier3: errored -- plpgsql_check could not be run: missing trigger relation / HINT: Trigger relation oid must be valid'. When I run a trigger function on sandbox, it must carry the information on which relation we're running it. That relationship is already set up in the DDL explorer."

**Root cause:** The gesture runs on a *trigger-function* tab — a `CREATE [OR REPLACE] FUNCTION ... RETURNS trigger` — whose `DdlObjectRef.kind` is `"function"`, NOT `"trigger"` (per CONSOLIDATED_SPEC line 3000: a trigger function is `kind == "function"` and `return_type == "trigger"`; a `CREATE TRIGGER` tab is the only thing that carries `kind == "trigger"`). tier 3 checks the function directly, and `plpgsql_check_function_tb` requires `relid => <table oid>` for ANY function whose return type is `trigger` — omitting it raises the server error `"missing trigger relation / HINT: Trigger relation oid must be valid"` verbatim.
  The entire relid plumbing in `pgtp_editor/db/ddl_check.py` is gated on `is_trigger` (`kind == "trigger"`):
  - `CheckRequest.regclass_text` (`ddl_check.py:579-585`) returns None unless `self.is_trigger and self.table`, so for a `kind=="function"` request it is always None.
  - Because `regclass_text` is None, `build_resolve_sql` (`ddl_check.py:668`), `build_check_sql` (`ddl_check.py:718`) and `build_guarded_check_sql` (`ddl_check.py:728`, `relid_expr` stays None at line 756) all omit `relid`, so `_check_call` (`ddl_check.py:706-708`) emits `plpgsql_check_function_tb(funcoid => ..., fatal_errors => false, all_warnings => true)` with no `relid`.
  - The server then errors, surfacing through the two identical STATUS_ERRORED paths: the ladder path `_tier3_outcome` at `ddl_check.py:1636-1645` (Apply / Check-Without-Applying, which is the reported `[Check] tier3: errored`) and the recheck path `recheck` at `ddl_check.py:1281-1289`. Both format `f"plpgsql_check could not be run: {outcome.message}"` / `{exc}`, which is exactly the reported string.
  The `CheckRequest` is built in `pgtp_editor/ui/main_window.py` at two sites — `apply_to_sandbox`-side at `main_window.py:4549` and `_run_ladder_on_active_ddl_object` at `main_window.py:4645`, both `CheckRequest.from_ref(ref, text, **self._trigger_function_for(ref, text))`. `_trigger_function_for` (`main_window.py:4668-4691`) returns `{}` for any ref where `ref.is_trigger` is False — so for a trigger-function tab it contributes nothing, and `from_ref` (`ddl_check.py:479-508`) copies `table=getattr(ref, "table", None)`, which is None for a `kind=="function"` ref. Net: nothing ever tells the request which relation to bind, so `relid` is never sent. The relation IS known to the app: `SchemaIndex.trigger_for_function(schema, name, arg_types)` (`db/schema_index.py:85-103`) is the existing reverse lookup that returns the `TriggerInfo` whose `function_name` matches this routine, and `TriggerInfo.table` (`db/introspect.py:112-121`) is the relation the trigger fires on. That same lookup is already used for NEW./OLD. completion at `ddl_object_editor.py:1511`, and `main_window` already holds the index as `self._ddl_schema_index` (`main_window.py:241`, populated at `2745`).

**Proposed fix:**
  1. In `pgtp_editor/ui/main_window.py`, extend `_trigger_function_for(self, ref, text)` (or add a sibling helper it merges in) so that when `ref` is a trigger FUNCTION (i.e. NOT `ref.is_trigger`, but the routine returns `trigger`), it looks up the owning relation and returns `schema`/`table`/`function_schema`/`function_name` kwargs that let tier 3 bind `relid`. Concretely: if `self._ddl_schema_index is not None`, call `self._ddl_schema_index.trigger_for_function(ref.schema, ref.name, getattr(ref, "arg_types", ()))`; if it returns a `TriggerInfo t`, contribute the relation. The existing branch (buffer is a `CREATE TRIGGER`, `ref.is_trigger` True) must keep working unchanged.
  2. Because the whole relid path in `db/ddl_check.py` keys off `is_trigger`/`kind`, the cleanest shape is to make `CheckRequest` able to carry a relation for a `kind=="function"` trigger-function request too. Two viable shapes — pick one and apply it consistently across `regclass_text`, `build_resolve_sql`, `build_check_sql`, `build_guarded_check_sql`, `_tier3_outcome`, and `recheck`:
     - (a) Populate `CheckRequest.table` (and `schema`) from the `TriggerInfo` for the function-kind request, and widen `regclass_text` (`ddl_check.py:583`) so it returns the lookup string whenever `self.table` is set (not only when `is_trigger`). For a trigger-function request `checked_schema`/`checked_name` already resolve to `schema`/`name` (the non-trigger branch), so `regprocedure_text` stays correct; only relid needs the widening. Verify `checked_arg_types` still yields `()` for a trigger function — a trigger function is zero-argument, so `ref.arg_types` should already be empty, but if a stray signature is carried, the resolve/check must use `()` (mirror `is_trigger`'s existing `checked_arg_types` special-case, or clear arg_types when binding a relation).
     - (b) Add an explicit `relation_schema`/`relation_table` pair (or reuse `table`) that `regclass_text` honors regardless of `kind`. This keeps `is_trigger` semantics untouched for the `CREATE TRIGGER` tab and is less likely to perturb `working_set_ref`/`trigger_drop_target`, which also read `table`. Prefer (b) if (a) is found to disturb those `is_trigger`-gated properties.
  3. Gotcha — distinguish "relation genuinely absent in sandbox" from "relation known but not plumbed through." Once a relation IS bound, `regclass_text` becomes non-None, so the EXISTING graceful path takes over: `to_regclass(...) IS NOT NULL` guard in the resolve SQL yields `relid IS NULL` when the table is not in the sandbox, and `_tier3_outcome` (`ddl_check.py:1662-1667`) / `recheck` (`ddl_check.py:1276-1279`) already convert that into `REASON_RELATION_ABSENT` (a clean `unavailable`, NOT `errored`). So the fix converts today's hard `errored` into either a real check run (relation present) or a graceful `unavailable` (relation absent) — desired. Do NOT hand a raw table oid or interpolate the table name; keep everything flowing through `to_regclass`/`quote_ident` as the existing trigger path does.
  4. Gotcha — a trigger function with no `TriggerInfo` yet (unattached, §18.6): the lookup returns None. Do NOT guess a relation. Leave the request relation-less; tier 3 will still error on such a function because plpgsql_check genuinely needs a relation. Consider surfacing this as an `unavailable` with a reason like "this trigger function is not attached to any trigger, so plpgsql_check has no relation to check it against" rather than the raw server error — but that is a nice-to-have; the core fix is the plumbing for the attached (already-set-up-in-the-DDL-explorer) case the report describes. If a new reason is added, follow the `REASON_*` constant + `__all__` convention (`ddl_check.py:1944-1960`).
  5. Also apply the `oldtable`/`newtable` transition-table pass-through consistently if the `TriggerInfo` exposes them (the trigger path already threads `oldtable`/`newtable` through `from_ref`); a trigger function checked via its trigger should honor the same transition tables the `CREATE TRIGGER` tab would.

**Test impact:**
  - `tests/db/test_ddl_check.py` is the primary home. `test_trigger_check_targets_the_function_and_passes_relid` (line 362) and `test_non_trigger_check_sends_no_relid` (line 386) currently assert the `kind`-gated behavior; add a NEW case for a `kind=="function"` request that carries a bound relation and asserts `"relid => "` IS present in the check SQL (the current design would omit it). Add a companion case asserting the graceful `REASON_RELATION_ABSENT` (not `errored`) when the resolve returns `relid=None` for a relation-bound function request (mirror the resolved/relid helpers at lines 129-130). Guard against regression of the existing plain-function case (no relation bound → no relid → still fine, because a plain function does not return `trigger`).
  - `tests/db/test_schema_index.py` already covers `trigger_for_function`; if the helper signature/behavior is touched, extend there, do not duplicate.
  - `tests/ui/test_main_window.py` (and/or `tests/ui/test_db_check_wiring.py`, which drives the real Database-menu Check actions) should get a wiring case: with a stub `_ddl_schema_index` returning a `TriggerInfo`, run the Check gesture on a trigger-function tab and assert the built `CheckRequest` carries the relation (schema/table) so `relid` will be emitted. Reuse `tests/ui/_sandbox_stubs.py`.
  - `tests/ui/test_ddl_object_editor.py` already exercises the trigger/function ref parsing; no change expected there unless `DdlObjectRef` gains fields.

**Spec impact:** Diverges from CONSOLIDATED_SPEC §18.5 D3a. The spec's trigger tier-3 design (lines 5287, 5778, 5788, 5892 and Supersession row 7079) describes relid-binding ONLY for the `CREATE TRIGGER` tab ("tier 2 is the `CREATE TRIGGER` itself; tier 3 checks the *referenced function* with `relid` set"), and never addresses running tier 3 DIRECTLY on a trigger-FUNCTION tab (`kind=="function"`, `return_type=="trigger"`, marker `[T]` per line 3000) — yet that tab is a first-class, checkable object. This is a spec gap, not a deliberate exclusion. After the fix lands, flag for spec-maintainer to record that tier 3 binds `relid` for a trigger-function tab via the `TriggerInfo` reverse lookup (`trigger_for_function` → `TriggerInfo.table`), and that an unattached trigger function reports `unavailable` (relation unknown) rather than the raw server error. Do not edit the spec here.

---

## BUG-039: When editing DDL, the Parsing menu should surface the sandbox DDL-check gestures and drop the XML-parse items
**Status:** RESOLVED (4828e3d; spec §7/§26/§18.5 D3a + a §28 ledger row) — with the two owner decisions this
entry left open both answered the AGGRESSIVE way. **(1) Parsing only:** the two check gestures were
REMOVED from the Database menu rather than mirrored on both, so one gesture has one home and one name.
**(2) The default-toolbar-button blink is accepted:** `Validate Project` and `Auto Parse XML` genuinely
disappear on a DDL object tab, and because a toolbar button IS the menu's QAction, the default Validate
button leaves the toolbar there too — the exact cost §7 had cited as its reason for leaving Parsing
ungated, now overridden by ledger row. Built once and `setVisible`-toggled per the entry's own warning.
The composed gate is `_refresh_parsing_menu_affordances`, called from BOTH refreshers (a tab change and a
sandbox/project change each move one of its two inputs); `_sandbox_check_present()` was extracted so
"is there a session?" is never read a second, independent way, and it stays CONFIGURED-not-`has_session`
per FQ-023. Consequence worth knowing: on a DDL tab in a project with no sandbox, Parsing is legitimately
EMPTY. `RENAMED_ID_ALIASES` gained both `database.* → parsing.*` rows so a toolbar saved before the move
keeps its buttons. Verified by the owner in the running app 2026-08-09.
**Reported:** 2026-08-08
**Report (verbatim):** "Parsing menu in editor pane when editing ddl should contain all linting of the ddl (check on sandbox without applying, check on sandbox). And should not have the points of XML parsing verification, etc."

**Root cause:** This is a *missing capability* (menu-membership gating never exercised), not a broken one. The "Parsing" menu is on the Editor menu bar and is built by `MainWindow._build_parsing_menu` (`pgtp_editor/ui/main_window.py:1722-1766`). It contains exactly two, XML-oriented, members, both created unconditionally and *ungated*: `Auto Parse XML` (checkable, `main_window.py:1758-1762`) and `Validate Project` (`main_window.py:1764-1766`, wired to `self._find_ui.validate_project`). No branch of the menu is aware of the active tab kind — the menu shows the same two items whether a Raw XML tab or a DDL object editor tab is in front.

The two DDL sandbox-check gestures the report wants ("check on sandbox" = **Check Object in Sandbox**; "check on sandbox without applying" = **Check Object Without Applying**) already exist as fully-wired QActions — but they live on the **Database** menu, built in `_build_database_menu`: `self._sandbox_check_action = menu.addAction("Check Object in Sandbox")` (`main_window.py:2416-2420`, → `self._check_active_ddl_object()` at `main_window.py:4567`) and `self._sandbox_probe_check_action = menu.addAction("Check Object Without Applying")` (`main_window.py:2427-2433`, → `self._probe_check_active_ddl_object()` at `main_window.py:4579`). Both handlers ultimately run `db/ddl_check.py`'s ladder (`recheck` / `probe_check` / `apply_and_check`) via `_run_ladder_on_active_ddl_object`. Their visibility is bound in `_refresh_sandbox_affordances` (`main_window.py:3815-3824`) by the `check_present` predicate (a sandbox is *configured*), NOT by which tab is active.

The Editor-bar's per-tab-kind gating entry point is `MainWindow._refresh_editor_menu_affordances` (`main_window.py:1892-1935`, connected to `center_stage.currentChanged`), which today does three things (whole-bar hide on Caption/Manual; `Select ▸ Select Parent Block` capability hide; `Deployment` per-tab flip). The Parsing menu is deliberately excluded from it — CONSOLIDATED_SPEC §7 (spec lines 1064-1070) records that `Parsing`'s gating is "still deliberately NOT exercised" because `Validate Project` is one of the **default toolbar buttons**, and a toolbar button IS the menu's own QAction, so hiding it per tab would blink a default toolbar button in and out. That same spec bullet names §18.5 D3a's check members (predicate: *"a DDL object editor tab is active"*) as "the next candidate" to be hosted here. So this report is asking for exactly the design move the spec already anticipated.

**Proposed fix:** Make the Parsing menu context-sensitive to the active tab kind, reusing the existing build-once-and-`setVisible`-toggle pattern (never rebuild the menu per tab — see the build-once rule in `_build_deployment_menu`'s docstring, `main_window.py:1777-1787`, and spec §7 lines 1032-1038: destroying actions per tab breaks `ToolbarController._walk_menu_actions` / Customize Toolbar enumeration and drops saved `toolbarIds`).

  1. In `_build_parsing_menu` (`main_window.py:1722`), add the two DDL check members to the Parsing menu as *new QActions built once here* and record them for gating. Do NOT move/reparent the existing `self._sandbox_check_action` / `self._sandbox_probe_check_action` off the Database menu unless the owner also wants them gone from Database — the safe, minimal shape is to add Parsing-menu actions that delegate to the SAME handlers (`lambda: self._check_active_ddl_object()` and `lambda: self._probe_check_active_ddl_object()`), so there is one check code path and one confirmation mechanism. Label them identically to the Database entries ("Check Object in Sandbox", "Check Object Without Applying") OR to the report's phrasing — pick one and keep it consistent with the Database labels to avoid two names for one gesture. Give them a leading `menu.addSeparator()` to group them below the XML items when both are shown. Decide (owner-facing note) whether they also belong on Database still or should be Parsing-only; the spec's §26 currently assigns them to Database, so keep both unless told otherwise.

  2. Gate membership in `_refresh_editor_menu_affordances` (`main_window.py:1892`) as a FOURTH thing it does, on the active tab kind. Reuse the exact predicate already computed for `Deployment`: `self._active_deployment_group() == "ddl-object"` (`main_window.py:1869-1890`) is the canonical "a DDL object editor tab is active" test (it asks `stage.active_ddl_object_panel() is not None`). When the DDL-object group is active: show the two check actions and HIDE the XML members (`self._auto_parse_action`, `self._validate_project_action`); otherwise: hide the check actions and show the XML members. Keep everything `setVisible`, never enabled-state (spec §7 line 1040 / the docstring's "VISIBILITY, never enabled-state").

  3. Compose the tab-kind gate with the sandbox-configured gate, do not replace it. The two check actions must be BOTH (a) on a DDL object tab AND (b) applicable per the sandbox-configured `check_present` predicate that `_refresh_sandbox_affordances` already computes (`main_window.py:3815-3816`, `controller.can_check or self._configured_sandbox_params() is not None`). Note FQ-023 (spec §18.5 carve-out 2, spec lines 4581-4599): when a sandbox is *configured but no session is open* the check gestures are PRESENT AND REPORTING (they state the reason and offer to open a session), NOT absent — so gate their Parsing-menu visibility on the same `check_present`, not on `has_session`. Simplest robust wiring: have BOTH refresh methods drive the final visibility (e.g. store the tab-kind fact and the sandbox fact and compute `visible = ddl_tab_active and check_present` in a small shared helper both call), so a `center_stage.currentChanged` and a sandbox-state change can each keep the Parsing check items correct. Do not read "is there a session?" a second, independent way — reuse `check_present`.

  Gotchas:
  - The XML members must genuinely disappear on a DDL tab per the report ("should not have the points of XML parsing verification"). `Validate Project` being a *default toolbar button* is the exact reason §7 said Parsing was left ungated — hiding its QAction will make that pinned/default toolbar button blink out on DDL tabs. This is the same accepted trade-off already taken for `Select ▸ Select Parent Block` (spec §7 lines 1047-1053) and the `Deployment` members; the report is an explicit owner instruction to accept it here too. Flag it for spec-maintainer (below) because it overrides the recorded "deliberately NOT exercised / because it is a default toolbar button" decision.
  - Build all four Parsing members once at construction; only `setVisible`-toggle them.
  - The check gestures no-op / refuse when no DDL object tab is active because `_check_active_ddl_object` resolves the active panel; gating them to the DDL-tab kind means they are only ever shown when they can act.

**Test impact:**
  - `tests/ui/test_menus.py` — `test_parsing_menu_contents` (line 182) currently asserts `action_labels(menu) == ["Auto Parse XML", "―", "Validate Project"]`; it will need updating to reflect the new membership AND a per-tab-kind assertion (XML items visible + check items hidden on a Raw XML tab; check items visible + XML items hidden on a DDL object tab). `test_parsing_menu_validate_project` (around line 605) triggers `Validate Project` — keep, but ensure it runs with a Raw-XML-active fixture so the action is visible.
  - `tests/ui/test_auto_parse_xml.py` (line 47 resolves `Auto Parse XML` from the Parsing menu) — assert it stays present on a Raw XML tab; add/adjust so the toggle test does not run under a DDL-active tab where the action is now hidden.
  - `tests/ui/test_sandbox_check_console_wiring.py` — the authoritative home for the two check gestures' visibility/wiring (asserts on `window._sandbox_check_action` / `window._sandbox_probe_check_action` and the emitted lines, e.g. lines 512-538, 675-697, 961-976, 997-1012). Extend here (do NOT duplicate) with cases for the NEW Parsing-menu check actions: visible only when a DDL object tab is active AND a sandbox is configured; hidden on Raw XML / no-DDL-tab; present-and-reporting (FQ-023) when configured-but-no-session; and that triggering the Parsing action reaches the same `_check_active_ddl_object` / `_probe_check_active_ddl_object` handler as the Database entry.
  - `tests/ui/test_database_menu.py` — if the Database-menu check entries are kept, assert they are unchanged; if the owner elects to remove them from Database, update here.
  - Reuse the sandbox stubs / helpers those wiring tests already use (`tests/ui/_menu_helpers.py`, and the sandbox stub fixtures in `test_sandbox_check_console_wiring.py`); do not introduce a parallel stub.

**Spec impact:** Diverges from CONSOLIDATED_SPEC §7 and §26. §7 (spec lines 1064-1070) records that `Parsing`'s per-tab membership gating is *"deliberately NOT exercised"* and that §18.5 D3a's check members are only *"the next candidate"* — this fix promotes that candidate to shipped, and additionally hides `Validate Project`/`Auto Parse XML` on DDL tabs, which the same bullet argued against precisely because `Validate Project` is a default toolbar button. §26 (spec lines 1008-1009, 6811-6814) enumerates Parsing as exactly `Auto Parse XML` / separator / `Validate Project`, and §26/§18.5 D3a assign `Check Object in Sandbox` / `Check Object Without Applying` to the **Database** menu. After the fix lands, flag for spec-maintainer to: (1) record that Parsing is now tab-kind-gated (XML members on non-DDL tabs, the two check members on DDL object tabs), with the default-toolbar-button trade-off accepted; (2) update the Parsing enumeration in §26/§7; (3) reconcile the check gestures' menu home (Parsing vs Database vs both) in §26/§18.5 D3a; and add a Supersession Ledger row for the override of the "deliberately ungated" decision. Do not edit the spec here.

---

## BUG-040: In a project the sandbox session should be connected automatically on open (and apply/check "just work"); the explicit Open/Close/Setup Sandbox actions belong only to the projectless case
**Status:** RESOLVED (4828e3d for the auto-open + the `Open`/`Close Sandbox Session` deletion; **4e36162** for the
third leg, `Sandbox Setup…` projectless-only; **e79626c** for the follow-through that closed the gap `4e36162`
opened — the provisioning gestures moved into Project Settings ▸ Connections and `Database ▸ Sandbox Setup…`
deleted; spec §18.5 carve-out 2 rewritten + a §28 ledger row; spec harmonization swept in `0e0a943`).
**FULLY CLOSED — the "CONSEQUENCE: project mode has lost provisioning" recorded below is no longer open;
it was closed by `e79626c`.** Read the entry in this order, because it carries a premise, a correction, and a
resolution and they contradict each other by design: (1) the third leg shipped on a premise this entry stated
as owner-confirmed — *"in project mode all sandbox configuration already lives in Project Settings"* — which
was **FALSE** when written; (2) the CORRECTION under Spec impact establishes it was false; (3) the owner then
ruled to make the premise TRUE rather than revert the hiding, and `e79626c` did exactly that. So the premise is
false for any statement dated before `e79626c` and true for anything after it. The entry was right
that this reverses a recorded owner decision, and the owner reversed it explicitly, taking the
**aggressive** reading of the sub-question the entry refused to guess: the manual lifecycle actions are
GONE in project mode, not kept as recovery. Spec moved first, as the entry demanded. What shipped:
`_bind_sandbox_controller_to_project` opens the session after `set_project`, routed through
`_open_sandbox_session()` (never `controller.open_session` directly) so the ownership gate and the
Audit-panel routing stay shared — best-effort, async, never modal, an unreachable sandbox simply leaving
today's no-session state with its reason reported. `Open Sandbox Session` / `Close Sandbox Session` are
**DELETED, not hidden**: a hidden QAction stays enumerable by `_walk_menu_actions` and therefore pinnable,
and a toolbar button bypasses menu visibility entirely, so hiding would have left a live button for a
gesture the app no longer offers. No `RENAMED_ID_ALIASES` row — a deletion is not a move, and the id
degrades through `resolve_ids` the FQ-020 `file.save` way. There is now **no explicit close at all**;
`set_project`/`clear_project` on a project transition is the only closing mechanism. **One defect the
entry did not foresee, found by the feature-tester and fixed here:** `New Project` binds the controller
BEFORE `_provision_sandbox` chooses the database name, so a host-only guard dialled `database=""` on every
project creation — libpq falls back to its default database, `open_sandbox`'s ownership check rejects it,
and the user got a "not a PGTP-created database" line in the Audit panel one step before the project
provisioned correctly. The auto-open guard therefore requires a NAMED database; `_configured_sandbox_params`
itself was left alone, since it is the shared "is a sandbox configured" reading §18.7's Explorer gate also
asks. Both docstrings the entry flagged (`SandboxController.set_project`, `_bind_sandbox_controller_to_project`)
were reconciled, and `DESTINATION_UNAVAILABLE_REASONS[DEST_SANDBOX]` reworded off the deleted menu path.
Verified by the owner in the running app 2026-08-09.
**Reported:** 2026-08-08
**Report (verbatim):** "sandbox setup, open sandbox/close sandbox has only meaning in standalone mode. in project mode the standalone should be connected since opening, and seamlessly apply, check etc."

**Terminology note (read first — the report's labels are inverted vs. the codebase).** In this codebase "Standalone" is **Tier 1 = projectless** (`ui/project_status_model.py:114` `AppState.STANDALONE = "app_standalone"`; §18.2 tier table, spec line 2788: *"No project open … read-only, permanently … Connection Setup… available only in this mode"*). A projectless session has **no sandbox at all** — the sandbox is a per-project artifact (`ProjectSettings.sandbox`). So taken literally the report is impossible (projectless has no sandbox to open/close). The load-bearing intent, confirmed by "in project mode the sandbox should be connected since opening, and seamlessly apply, check": **when a project with a configured sandbox is opened, the sandbox session should come up automatically, and Apply/Check should not require the user to first run `Database ▸ Open Sandbox Session`.** The report's "standalone mode" = "the manual open/close ritual"; the request is to make that ritual go away in project mode. This entry is triaged on that intent.

**Root cause (this is a deliberate design decision, not a code defect).** There is no broken code path — the current behavior is intentional and enforced in three coordinated places:
- `ui/sandbox_controller.py::set_project` (lines 505-532) is explicit: *"Opens nothing and provisions nothing -- no destructive operation and no connection attempt happens as a side effect of a project opening."* It records params/mode/`configured` and calls `close_session()`, but never `open_session()`.
- `ui/main_window.py::_bind_sandbox_controller_to_project` (lines 3952-3974) — the one project-transition entry point — calls `set_project(...)` then `_refresh_sandbox_affordances()`. It never opens a session.
- `ui/main_window.py::_build_database_menu` (lines 2395-2409) creates `Open Sandbox Session` / `Close Sandbox Session` menu items whose comment (lines 2395-2399) states the rationale: *"acquiring/releasing the one `SandboxSession`. Deliberately a user act rather than a side effect of opening a project."* `_refresh_sandbox_affordances` (lines 3825-3830) shows `Open` when `not has_session and configured`, `Close` when `has_session`.
- Because no session exists, Apply/Check refuse: `run_check`/`run_apply` short-circuit on `self._session is None` with `_NO_SESSION_REASON` (sandbox_controller.py:1074-1080, 1156-1159), and the host surfaces the FQ-023 "Open a session now?" prompt via `_refuse_sandbox_gesture` (main_window.py:3885-3940).

The behavior the report calls a bug is the shipped resolution of **FQ-023** (see Spec impact). The one genuine latent inconsistency it correctly senses is recorded in the spec itself (spec lines 4618-4624): `set_project`'s *"opens nothing"* docstring is already contradicted by `ui/ddl_project_controller.py::refresh_capability_status` (called from `set_active_project`), which **does** open a real sandbox connection at project-open time to probe capabilities — so a connection to the sandbox already happens on project open; only the *session* (the accumulating, stateful `SandboxSession` used by Apply/Check) is withheld.

**Proposed fix (design change — must go through spec-maintainer before implementation; see Spec impact).** The change is small in code but reverses an owner decision, so the spec must move first. Assuming the auto-connect direction is approved, the concrete shape:
- **Auto-open on project bind.** In `ui/main_window.py::_bind_sandbox_controller_to_project` (line 3963-3968), after `set_project(...)` and when `_configured_sandbox_params() is not None`, call `self.sandbox_controller.open_session()` (the existing async ownership gate — do NOT bypass `open_sandbox`). Reuse `_open_sandbox_session()` (main_window.py:3976-3988) rather than calling the controller directly, so the "no sandbox configured" guard and the Audit-panel outcome routing (`_on_sandbox_operation_finished`) are shared. Note `open_session` is async via `_run_async`; `session_changed` → `_on_sandbox_session_changed` → `_refresh_sandbox_affordances` already repaints affordances when it lands, so no extra wiring is needed.
- **Failure posture.** `open_session` already reports every distinguishable refusal (unreachable / not superuser / tools missing / foreign DB) through `SandboxOperationResult` to the Audit panel and simply leaves `has_session` False. So a sandbox that cannot connect at project-open time degrades to exactly today's no-session state (Apply/Check still refuse with a stated reason) — no new error handling required; the auto-open is best-effort.
- **Hide the manual lifecycle actions entirely in project mode (owner decision, 2026-08-08).** The connection is fully implicit once a project opens: in project mode there is **no manual sandbox lifecycle surface at all**. Concretely, gate all three explicit lifecycle actions on projectless-vs-project so they are absent whenever a project is open:
  - `_open_sandbox_session_action` / `_close_sandbox_session_action` in `_refresh_sandbox_affordances` (main_window.py:3825-3830): both hidden whenever `self._ddl_project_folder is not None` (project mode), regardless of `has_session`. No "Open as recovery after a failed auto-open" path — the owner explicitly rejected keeping them as a recovery affordance. (Recovery, if a sandbox is unreachable at open, is handled the same way as any other capability problem — via Project Settings / re-probe — not via a manual Open button.)
  - `_sandbox_setup_action` (`Sandbox Setup…`, main_window.py:2452-2455) is created always-visible today (deliberately, so it can *create* a sandbox). Per the owner decision it too is hidden in project mode. **No capability is lost by this (owner-confirmed, 2026-08-08):** in project mode all sandbox configuration — provisioning, re-provisioning, and sandbox-mode change — already lives in **Project Settings** (`ui/project_settings_dialog.py`, the tabbed Connections/Sandbox surface), which stays available. Like `Open`/`Close Sandbox Session`, the `Sandbox Setup…` menu action is only meaningful in projectless (standalone) mode — where it exists for standalone-mode checks/lints, since there is no project whose settings could hold the sandbox config. So hiding all three in project mode leaves the mode complete: implicit connection on open, and config through Project Settings.
  - **SHIPPED as `4e36162` (third leg).** `MainWindow._refresh_sandbox_affordances` now carries
    `self._sandbox_setup_action.setVisible(self._ddl_project_folder is None)`, and the build site's comment in
    `_build_database_menu` was rewritten to point at the refresher as the owner of that visibility. The action is
    **HIDDEN, not deleted** — a deliberate divergence from `Open`/`Close Sandbox Session`, which this entry deleted
    outright. The reason for the asymmetry: those two had no mode left in which they meant anything, whereas
    `Sandbox Setup…` projectless is the ONLY way to get a sandbox at all. It also stays ungated on a live session
    and on a sandbox already existing, because it is the one gesture that can CREATE one. A dead `has_session` local
    left over in `_refresh_sandbox_affordances` by the deletion of the two lifecycle actions was removed with it.
    Full suite green: 4870 passed, 45 skipped.
  - The **projectless case keeps its current actions untouched** — though note projectless mode has no configured sandbox, so `_configured_sandbox_params()` is None and these actions are already hidden there today by their existing predicates; the net effect is that the Open/Close/Setup lifecycle surface effectively disappears from normal use, which is the intended outcome.
- **Do NOT invent a new connect path.** `open_session` / `open_sandbox` is the single ownership chokepoint (D2); the fix wires an existing call to fire on project bind, it adds no new session-acquisition mechanism.
- **Gotcha:** `_adopt_sandbox_setup_settings` (main_window.py:4025-4051) deliberately does NOT go through `_bind_sandbox_controller_to_project` (to avoid dropping the session the Setup dialog just provisioned). If auto-open moves into `_bind_...`, verify the Setup-dialog path still ends with a live session (it provisions its own) and does not double-open.
- **Gotcha:** projectless mode must be untouched — `_configured_sandbox_params()` returns None there, so the auto-open guard is a no-op projectless by construction; confirm no auto-open fires when `_ddl_project_folder is None`.

**CONSEQUENCE — RULED AND NOW CLOSED by `e79626c` (see the ruling note at the end of this section): between
`4e36162` and `e79626c`, hiding `Sandbox Setup…` left project mode with no way to provision, re-provision or
reset a sandbox.** Everything in this section describes the state of the tree in that window only; it is history,
not a description of the code today. The bullet above justifies the hiding with a claim marked *owner-confirmed*: that in project mode
*"all sandbox configuration — provisioning, re-provisioning, and sandbox-mode change — already lives in Project
Settings … so hiding all three in project mode leaves the mode complete."* **That claim is false for provisioning.**
Verified 2026-08-09 by reading both dialogs end to end:
- `ui/project_settings_dialog.py` (440 lines) carries the sandbox **connection fields**, a **Test**-connection row
  (`_add_test_row` / `test_sandbox`, feeding `_apply_sandbox_probe_result`), and the recorded **sandbox MODE**
  radios (`_sandbox_mode_without_data_radio` / `_with_data_radio`, lines 134-150) — whose own inline note says
  *"Changing this does not re-clone the sandbox — it takes effect the next time the sandbox is reset/recreated."*
  Its only other buttons are `Add Row` / `Remove Selected Row` for the deployed-objects table. There is **no
  Provision, no Reset, and no "create a sandbox database for me"** anywhere in the file.
- Those three live **only** in `ui/sandbox_setup_dialog.py`: `Provision sandbox` (`_provision_button`, line 458 →
  `provision()` line 593 → `_provision(create_database=…)` line 604), `Reset sandbox` (`_reset_button`, line 414 →
  `reset_sandbox()` line 652), and `Create a sandbox database for me` (`_create_button`, line 469).
- Net effect: **a project-mode user now has no path to provision, re-provision or reset an existing project's
  sandbox.** Project Settings can change the recorded mode but, by its own note, that only takes effect at a
  reset/recreate the user can no longer trigger. New projects are unaffected — provisioning still runs on the create
  path via `MainWindow._provision_new_project_sandbox` (main_window.py:2567), wired into `NewProjectDialog` at
  main_window.py:723.

This is recorded as a **consequence, not a defect to revert**: the owner directed the hiding after being warned the
premise was unverified, and was then told the premise is false.

**OWNER RULING ON THE CONSEQUENCE (2026-08-09) — LANDED as `e79626c`.** The owner ruled in the direction this entry
suggested — give project mode its own provisioning home rather than un-hide `Sandbox Setup…`: the provisioning actions
move **into Project Settings**, and `Database ▸ Sandbox Setup…` is **deleted** (not merely hidden, as `4e36162` left
it). This makes the premise true after the fact instead of reverting `4e36162`. **What `e79626c` actually shipped:**
- The three provisioning gestures — `Provision sandbox`, `Reset sandbox`, `Create a sandbox database for me` — now
  live in **Project Settings ▸ Connections**, in a `Sandbox provisioning` group placed under the sandbox-mode radios.
- `Database ▸ Sandbox Setup…` is **DELETED, not hidden** — deliberately, on this entry's own argument: a hidden QAction
  stays enumerable by `ToolbarController._walk_menu_actions` and a toolbar button bypasses menu visibility entirely,
  so hiding would have left a live clickable button for a gesture the menu no longer offers. This retires the
  hidden-vs-deleted asymmetry `4e36162` introduced.
- `pgtp_editor/ui/sandbox_setup_dialog.py` and its test file were **deleted outright**. Its state group and
  working-set table were duplicating §18.8's Project Status window, so nothing was worth preserving.
- **Carve-out 2 travelled with the gestures:** the provisioning group is rebuilt wholesale, so an inapplicable action
  is **absent with a stated reason**, never greyed out. Each destructive gesture still confirms exactly once, using
  the controller's own warning text (not a new prompt).
- **A quietly false promise was fixed with it:** the mode radios' note said a change *"takes effect the next time the
  sandbox is reset/recreated"*, but `SandboxSession.reset()` re-runs the mode the sandbox was **created** with — so
  Reset could never honour a just-changed radio. The note now says **Provision**.
- Full suite green at the time: **5653 passed, 45 skipped**.

The design record for this was routed through the spec, and the stale "Project Settings does not provision" claims
were swept out of the spec in `0e0a943` (~25 sites across §7, §18.2, §18.5, §18.7, §18.8, §26 and the header).

**Test impact:** Existing coverage to extend, not duplicate:
- `tests/ui/test_sandbox_check_console_wiring.py` and `tests/ui/test_mainwindow_surface.py` — the `_refresh_sandbox_affordances` / Open-Close-Session menu-visibility and `_refuse_sandbox_gesture` wiring; these encode today's manual-session posture and will need updating to the auto-open expectations.
- `tests/ui/test_sandbox_controller.py` — `set_project`/`open_session`/`close_session` behavior; add/adjust a case asserting a project bind with a configured sandbox triggers `open_session` (with the async runner stubbed synchronously as the suite already does).
- `tests/ui/test_ddl_object_editor.py` — currently asserts the "Open Sandbox Session" refusal text; revisit if the manual actions change.
- New cases needed: (1) opening a project with a configured, reachable sandbox ends with `has_session` True and no user click; (2) opening a project whose sandbox is unreachable/non-superuser leaves `has_session` False and surfaces the stated reason (no crash, Apply/Check still refuse); (3) projectless mode opens no session; (4) with a project open, the `Open Sandbox Session` / `Close Sandbox Session` / `Sandbox Setup…` actions are all hidden (owner decision — no manual lifecycle surface in project mode), including the case where the auto-open failed and `has_session` is False. Reuse the sandbox stubs in `tests/ui/_sandbox_stubs.py`.

**Test impact — what the third leg (`4e36162`) actually landed:** three new cases in
`tests/ui/test_sandbox_check_console_wiring.py` — `Sandbox Setup…` offered projectless; hidden once a project opens;
and **back again when the project closes**. The third one is not redundant: the visibility is driven from
`_refresh_sandbox_affordances`, so a project transition has to reach that refresher in *both* directions, and only a
close-side case pins that down. `tests/ui/test_sandbox_setup_wiring.py::test_the_database_menu_carries_a_sandbox_setup_entry`
was updated to assert existence-and-hidden rather than visible. **Gotcha for the next implementer touching these:**
that test's `isEnabled()` assertion had to be dropped, because Qt folds visibility into `QAction.isEnabled()` — a
hidden action reports `isEnabled() == False`, so the assertion would have read like it guarded an enabled-state
posture while in fact guarding nothing. Assert `isVisible()` explicitly; never use `isEnabled()` to characterize an
action whose visibility is also under test.

**Test impact — what `e79626c` (the provisioning move) landed:** `tests/ui/test_sandbox_setup_wiring.py`'s
`Sandbox Setup…` menu-existence assertions and the whole `sandbox_setup_dialog` test file were **deleted** along
with the dialog; the provisioning coverage moved onto the Project Settings dialog's tests (the `Sandbox
provisioning` group's presence/absence-with-a-reason rebuild, and the single confirmation on each destructive
gesture). The three `4e36162` visibility cases in `tests/ui/test_sandbox_check_console_wiring.py` described above
went with the deleted action. Anyone re-reading those paragraphs should not expect to find those tests in the tree.

**Spec impact:** **Directly reverses a recorded owner decision — must go to spec-maintainer BEFORE any implementation, not after.** CONSOLIDATED_SPEC §18.5 (FQ-023 carve-out, spec lines 4590-4624) records the explicit ruling: *"Lazy session opening is REJECTED by the owner: 'Don't open lazily, it needs to be an explicit decision.'"* and *"`Database ▸ Open Sandbox Session` stays an explicit menu item."* Auto-connecting on project open is exactly the lazy/implicit open that decision rejected — so this is a genuine design change, requiring a Supersession Ledger row (§28) overriding the FQ-023 manual-session stance for project mode. Note the report's own strongest argument is already in the spec (lines 4618-4624): the *"opens nothing"* principle is a *"leftover rather than a stance"* since `refresh_capability_status` already connects at project-open time — spec-maintainer should reconcile `set_project`'s docstring, the D2 ownership narrative, and the §18.5 auto-vs-manual-session decision in one pass. **The Open/Close-menu sub-question is now settled by owner decision (2026-08-08): in project mode the explicit `Open Sandbox Session` / `Close Sandbox Session` / `Sandbox Setup…` actions are hidden entirely — no manual sandbox lifecycle surface in project mode; the connection is fully implicit on project open. The projectless case is unchanged.** This further supersedes FQ-023's *"`Database ▸ Open Sandbox Session` stays an explicit menu item"* clause, so the Supersession Ledger row must cover both the auto-open and the removal of the manual lifecycle actions. **No re-provisioning home needs to move (owner-confirmed, 2026-08-08):** project sandbox configuration — provisioning, re-provisioning, and sandbox-mode change — already lives in Project Settings, so hiding `Sandbox Setup…` in project mode loses no capability; spec-maintainer should record that the three lifecycle menu actions are projectless-only and that Project Settings is the sole sandbox-config surface in project mode. Do not edit the spec here; flag for spec-maintainer. **CORRECTION (2026-08-09, verified — supersedes the
"No re-provisioning home needs to move" sentence immediately above):** that sentence was wrong **when written**.
Project Settings was NOT a provisioning surface — see "Consequence" in the Proposed fix for the file-and-line
evidence. Worse than the entry first framed it: the three capabilities were unreachable in **every** mode, not just
project mode. `Sandbox Setup…` was hidden in project mode by `4e36162`, and projectless the dialog rendered only
refusal notes and built no controls at all — so `Provision sandbox` / `Reset sandbox` / `Create a sandbox database
for me` had no live home anywhere in the app between `4e36162` and `e79626c`.

**RESOLUTION OF THAT CORRECTION (2026-08-09, `e79626c`) — READ THIS BEFORE ACTING ON THE PARAGRAPH ABOVE.** The owner
did not revert the hiding; he made the premise **true**. As of `e79626c`, **Project Settings ▸ Connections DOES cover
provisioning** — it carries the `Sandbox provisioning` group with `Provision sandbox`, `Reset sandbox` and `Create a
sandbox database for me` — and `Database ▸ Sandbox Setup…` no longer exists. Therefore:

- **Instruction to any future `spec-maintainer` (this replaces the earlier, now-inverted instruction that said not to
  repeat the claim):** the accurate present-tense statement to fold in and to harmonize toward is that **Project
  Settings ▸ Connections is the sole sandbox surface in project mode and covers connection params, connection test,
  recorded sandbox mode, AND provisioning/reset/create-database**, with `Database ▸ Sandbox Setup…` deleted and the
  three lifecycle menu actions gone. **Do NOT re-introduce the "Project Settings cannot provision" wording** — that
  ghost was already swept out of ~25 spec sites in `0e0a943`, and reinstating it would undo that pass.
- **Dating rule for a reader who finds a conflicting old sentence:** the premise *"Project Settings covers
  provisioning"* is **FALSE for anything describing the tree before `e79626c`** and **TRUE for anything after it**.
  A spec sentence, comment or queue line asserting the gap is stale history from the `4e36162`→`e79626c` window;
  correct it forward rather than treating it as a live contradiction.
- The gap is no longer an open owner question — it was ruled on and closed.

---

## BUG-041: §18.6 completion (including `NEW.`/`OLD.`) is dead inside a `$$ … $$` routine body — the one place a plpgsql author types
**Status:** RESOLVED (8d0701c) — Option A + D, as recommended
**Reported:** 2026-08-10
**Report (verbatim):** "§18.6's schema-aware completion — including the shipped `NEW.`/`OLD.` row-variable completion — cannot fire inside a `$$ … $$` routine body, which is precisely where a plpgsql author types. So a feature documented as working in the DDL object editor is, in its main use case, dead. Mechanism, as reported by the agent that found it while building FQ-030's scope analyzer: `sql/caret_context.py::_caret_inside_opaque_token` returns `None` for a caret inside ANY opaque token, and a dollar-quoted body is one such token. The DDL object editor feeds `resolve_caret_context` the whole buffer, and `db/ddl_buffer.py` builds that buffer from `pg_get_functiondef` output — so the entire routine body is a single `DOLLAR_STRING`. The current behaviour is deliberate and tested (`tests/sql/test_caret_context.py::test_caret_inside_dollar_quoted_body_is_unresolvable`). Work out and record what the honest options are rather than asserting one. Note the analyzer's own half already handles this: `analyze_from_scope` descends into a dollar-quoted body when the caret is inside it."

**Root cause:** `pgtp_editor/sql/caret_context.py:94-95` in `resolve_caret_context`, via
`_caret_inside_opaque_token` (same file, :168-172), which returns True for **any** token with
`Token.is_opaque` — and `sql/tokenizer.py:112-131` puts `DOLLAR_STRING` in that set alongside strings,
quoted identifiers and comments. A `$$ … $$` routine body is therefore one single opaque token, and every
caret strictly inside it resolves to `None` before any of the three §18.6 contexts is even considered.

Reproduced, not inferred — `QT_QPA_PLATFORM=offscreen venv/bin/python` with a
`CREATE FUNCTION pr.f() RETURNS trigger AS $$ … NEW.<caret> … $$` buffer prints `None` from
`resolve_caret_context`, and `analyze_from_scope` on the same offset returns `FromScope(refs=())` for the
same structural reason at the *statement* level (its own body descent only fires for FROM-clause analysis).

Why the whole buffer is one body in practice: `pgtp_editor/db/ddl_buffer.py::build_ddl_text` (:98) fills the
buffer from `RoutineInfo.source`, which is `pg_get_functiondef` output
(`pgtp_editor/db/introspect.py:414`) — header + `AS $function$ … $function$`. The DDL object tab feeds that
text in unmodified: `pgtp_editor/ui/ddl_object_editor.py:1483` (`_show_completions`) and `:1583`
(`_complete_identifier`) both call `resolve_caret_context(self.editor.toPlainText(), …)`. So for a routine
tab, *nearly the entire editable buffer* is inside the opaque token — only the `CREATE FUNCTION …` header
line and the trailing `LANGUAGE plpgsql;` are outside it. §18.6's rows 2 and 3 (`NEW.`/`OLD.` "inside a
routine's body") are structurally unreachable from the UI; only row 1 (dotted path) can fire, and only on
the header line.

**Scope of the damage (established, not assumed).** `resolve_caret_context` has exactly two consumers:
- `ui/ddl_object_editor.py` — `_show_completions` (:1474-1489) dispatches `ROW_VARIABLE` and `DOTTED_PATH`;
  both are inert inside a body. `_complete_identifier` (:1575-1594) also calls it, only to measure
  `len(context.prefix)`; with `None` it falls back to `prefix_len = 0`, so *if* a popup ever did open inside
  a body the accepted item would be inserted **without** replacing the typed prefix — a latent second defect
  that the fix removes rather than introduces.
- `ui/sql_console_panel.py` — `show_completions` (:806-840) and `_complete_identifier` (:847-867).
  **Verified: the console is not affected the same way.** Its buffer is whatever ad-hoc SQL the user types,
  not a `pg_get_functiondef` wrapper, so the common case has no `$$` at all. It is affected by the *same
  rule* only when a user pastes a routine definition into the console — the same fix cures both at once,
  because both go through the one resolver.
- Not affected: `sql/formatter.py` and `db/ddl_check.py` do not use `resolve_caret_context`; opacity there is
  a separate, correct rule (the formatter must not reindent body content, §18.4 / spec ~line 5245).

**Adjacent fact worth knowing before implementing:** `ALIAS_REF` is produced by `caret_context.py:140-148`
but **no UI dispatches it yet** — `_show_completions` branches only on `ROW_VARIABLE`/`DOTTED_PATH`
(:1486-1489), and the console rejects anything that is not `DOTTED_PATH` (:819). So FQ-030 slice 1's alias
completion is currently invisible *everywhere*, not only in bodies. Fixing BUG-041 is necessary but not
sufficient for alias completion in a body; the missing `ALIAS_REF` branch is FQ-030's own remaining work and
should not be silently folded in here beyond noting it.

**Proposed fix — the options, honestly.** All four were checked against the code; the recommendation is A(+D),
but the trade-offs are recorded so the implementer can overrule with eyes open.

**Option A (recommended) — descend into the body inside `resolve_caret_context`, mirroring
`from_clause._analyze`.** Before the `_caret_inside_opaque_token` check at `caret_context.py:94`, detect a
caret inside a `DOLLAR_STRING` and re-enter `resolve_caret_context` on the *body's own text* with the offset
rebased (`pos - body_start`), bounded by a recursion depth like `from_clause._MAX_BODY_DEPTH` (:143). This is
exactly the precedent the report points at: `sql/from_clause.py:247-252` + `_dollar_body_at` (:284-303),
which already handles the tag length, the unterminated body (a user mid-typing), and a caret sitting inside
the closing tag itself. **Verified to work**: driving `_dollar_body_at` + `resolve_caret_context` by hand on
a body containing `NEW.` and `SELECT jc.  FROM hr.jobcard jc` yields
`CaretContext(kind='row_variable', row_variable='NEW')` and
`CaretContext(kind='alias_ref', table_ref=TableRef(schema='hr', table='jobcard', …))` respectively — so the
one change lights up both today's `NEW.`/`OLD.` row and FQ-030's alias resolution (once the UI dispatches
`ALIAS_REF`). Because the body text is re-tokenized, strings/comments/quoted identifiers **inside** the body
stay opaque, which is the property that must not be lost. Cost: strings/positions returned are body-relative
— today harmless (only `prefix`, a length, escapes the function), but any future field carrying an offset
must be rebased at the recursion boundary. Flag that in the docstring.

**Option D (recommended together with A) — put the descent helper in one place.** `_dollar_body_at` is
private to `from_clause.py` and its natural home is `sql/tokenizer.py` (it is pure token/tag arithmetic and
the tokenizer already owns tag length and `unterminated`). Promote it to a public
`tokenizer.dollar_body_at(tokens, pos) -> tuple[str, int] | None` and have both `from_clause._analyze` and
`caret_context.resolve_caret_context` call it. Do **not** copy the function into `caret_context.py`: the repo
already carries a *third*, independent body locator — `db/ddl_check.py::body_line_offset` (:661-673, regex,
line-based, for `plpgsql_check` line mapping) — and a fourth copy is how the tag-length/unterminated edge
cases drift apart. (Leaving `ddl_check`'s line-based one alone is fine; it answers a different question.)

**Option B (rejected, recorded so it is not re-proposed) — just drop `DOLLAR_STRING` from the opacity test.**
Cheapest diff, and actively wrong: without the offset descent the token stream is still the *outer* one, in
which the whole body is a single non-WORD token. The backward walk at `caret_context.py:116-124` then finds
no `.`/WORD pair, so every caret anywhere in a body returns `DOTTED_PATH(parts=(), prefix="")` — an
undifferentiated "offer all schema names", with `NEW.`/`OLD.` still undetected and the typed prefix lost.
It converts a silent no-op into a wrong popup.

**Option C — have the editor pass only the body.** `ddl_object_editor` computes the body span and calls
`resolve_caret_context(body_text, pos - body_start)`. Keeps `sql/` untouched, but: it must be repeated at all
four call sites (two in `ddl_object_editor.py`, two in `sql_console_panel.py`), it re-derives body-span
knowledge that `from_clause` already owns (a fifth copy, see D), it forces every caller to map offsets back
for any insertion-position feature (FQ-030 slice 1's expand-SELECT, slice 2's tab-stops), and it makes the
console's behaviour diverge from the tab's. Choose it only if there is a reason the pure layer must not
change — there is not.

**Files to touch under A+D:** `pgtp_editor/sql/tokenizer.py` (promote `dollar_body_at`),
`pgtp_editor/sql/from_clause.py` (call it instead of the private copy; keep `_MAX_BODY_DEPTH` semantics),
`pgtp_editor/sql/caret_context.py` (the descent + docstring: the module docstring at :17-40 currently says
nothing about bodies, and the `resolve_caret_context` docstring at :83-91 explicitly lists "inside a
string/comment/quoted identifier" as unresolvable — update that sentence, it is about to become the precise
statement of the new rule). **No UI change is required for the reported symptom** — `_show_completions`
already handles `ROW_VARIABLE` the moment a context comes back non-`None`.

**Gotchas:** (1) the recursion must run *before* the opaque check, not instead of it — strings and comments
inside the body must still return `None`; (2) bound the depth (nested `$a$ … $b$ … $b$ … $a$`) exactly as
`from_clause` does; (3) an unterminated body is the normal state while typing — `_dollar_body_at`'s
`tok.unterminated` branch already covers it, do not reimplement; (4) do not change opacity for
`sql/formatter.py`'s consumers: the fix belongs to caret resolution only.

**Test impact:** Existing coverage to extend, not duplicate:
- `tests/sql/test_caret_context.py` — **this is the reconciliation point.**
  `test_caret_inside_dollar_quoted_body_is_unresolvable` (:98-101) asserts today's behaviour *on purpose*.
  It must be **repurposed, not deleted**: replace it with (a) a case asserting the body **is** resolved
  (`$$ … NEW.<caret> … $$` → `ROW_VARIABLE`), and (b) a case preserving the rule it was really protecting —
  a caret inside a **string literal or comment nested inside** a `$$` body is still `None`. Keep the
  neighbouring `test_caret_inside_string_literal_is_unresolvable` / `…_line_comment_…` (:92-107) untouched.
  Add: a full `pg_get_functiondef`-shaped buffer (`CREATE FUNCTION … AS $function$ … $function$ LANGUAGE
  plpgsql;`) resolving `NEW.` and a dotted path inside the body; a tagged body (`$function$`, not just `$$`);
  an unterminated body; a nested-body depth bound; and a caret inside the closing tag.
- `tests/sql/test_from_clause.py` — already covers the body descent (`analyze_from_scope` inside `$$`); if
  `_dollar_body_at` moves to the tokenizer, these must stay green unchanged, which is the regression signal
  that the move was behaviour-preserving.
- `tests/sql/test_tokenizer.py` — home for the promoted `dollar_body_at` unit cases (tag length, unterminated,
  caret in the tag).
- `tests/ui/test_ddl_object_editor_completion.py` — the UI-level proof the report is about: a tab whose buffer
  is a full trigger-function definition, caret after `NEW.` **inside the body**, Ctrl+Space offers the
  triggering table's columns. Check whether the existing cases quietly use body-less buffers; if so, that is
  why the suite was green while the feature was dead, and at least one case should be converted.
- `tests/ui/test_sql_console_completion*.py` / `tests/ui/test_sandbox_check_console_wiring.py` — verify the
  console path is unchanged for ordinary ad-hoc SQL (no regression), and optionally add the pasted-routine case.

**Spec impact:** **The shipped code diverges from the spec; the spec is on the bug's side.** `CONSOLIDATED_SPEC`
§18.6 (~line 7214 ff.) is marked *"implemented and shipped"* and its context table specifies rows 2 and 3 as
`NEW.`/`OLD.` *"inside a routine's body"* — i.e. the spec already promises what does not work. Nothing in the
spec records the opacity-inside-completion decision; the only place that decision exists is the test named
above. So this is a fix-toward-spec, not a design change, and it needs **no** Supersession Ledger row for the
behaviour itself. After the fix lands, flag `spec-maintainer` to record two small clarifications: (1) §18.6 /
§5's `caret_context.py` line (~:480-484) should state that caret resolution **descends into** a dollar-quoted
body while the tokenizer keeps it opaque for every other consumer — the two halves of one rule, the same
sentence `from_clause.py`'s docstring already carries (:56-59); and (2) if `dollar_body_at` is promoted, §5's
`sql/` tree should name it on `tokenizer.py`. Also worth a line in §18.6's status block: the FQ-030 slice-1
`ALIAS_REF` kind exists in the pure layer with **no UI consumer yet** (see "Adjacent fact" above) — a status
accuracy point, not a design one. Do not edit the spec here.

**Resolution (8d0701c) — what actually shipped, and where this entry was wrong.**
Option A + D were taken; Option B stays rejected for the reason recorded above (without the rebase it turns a
silent no-op into a *wrong* popup). Verified in the shipped tree:
- `pgtp_editor/sql/caret_context.py` — the descent lives in `_resolve` (:167-177), **before** the
  `_caret_inside_opaque_token` call (:179), and only for `DOLLAR_STRING`: it locates the body, rebases to
  `pos - body_start` and recurses on the body text, bounded by a local `_MAX_BODY_DEPTH = 5` (:69) mirroring
  `from_clause`'s. Because the body text is re-tokenized, anything opaque *nested inside* it still returns
  `None` — gotcha (1) honoured.
- `pgtp_editor/sql/tokenizer.py` — the locator was **promoted**, not copied: public
  `dollar_body_at(tokens, pos) -> tuple[str, int] | None` (:394), consumed by both `caret_context.py:172` and
  `from_clause.py:425`. No third locator was created; `db/ddl_check.py::body_line_offset` was deliberately
  left alone (line-based, answers a different question, and FQ-031 — since shipped — depends on it).
- **One behaviour fix beyond this entry's plan.** The locator's bounds test was `start < pos < end`, which
  excluded a caret at the **end of an unterminated body** — exactly where the caret sits while typing a new
  routine, i.e. the commonest real case. `tokenizer.py:422` now reads
  `tok.start < pos < tok.end or (tok.unterminated and pos == tok.end)`.

**Two corrections to this entry's analysis, recorded so nobody re-hunts them:**
1. **The "latent second defect" in `_complete_identifier` was not real.** This entry claimed the `prefix_len = 0`
   fallback on a `None` context would insert without replacing the typed prefix. It does not:
   `_complete_identifier` re-resolves the *same* caret with the *same* resolver, so inside a body it now gets a
   context and replaces the prefix correctly, and the `None` fallback is only reachable where no popup can be
   open in the first place. There is no residual symptom to chase.
2. **The console assessment holds, and is now verified both ways.** With no `$$` in the buffer the code path is
   byte-identical to before (ordinary ad-hoc SQL is unaffected), and a pasted routine definition gets the
   *same* cure, since both surfaces go through the one resolver.

**Tests as shipped** (`tests/sql/test_caret_context.py`, `tests/sql/test_tokenizer.py`): the deliberate test was
**repurposed, not deleted** — `test_caret_inside_dollar_quoted_body_is_unresolvable` became
`…_resolves_against_the_body` (:99), and what it was really protecting is now four tests: a string literal, a
line comment, a block comment and a quoted identifier **nested inside** a body each still yield `None`
(:283-302). Plus `pg_get_functiondef`-shaped `NEW.` / alias / dotted-path cases, prefix coordinates, header and
trailing-`LANGUAGE` lines, an unterminated body, and a depth bound. `dollar_body_at` has its own unit block in
`tests/sql/test_tokenizer.py` (:429 ff.), including the end-of-unterminated-body case.

**Knock-on: this unblocked queued work immediately.** FQ-030's alias completion and its whole slice-3
local-scope analyzer (`DECLARE` variables, `%ROWTYPE`, cursors) target symbols that exist *only* inside bodies
and were structurally unreachable before this; `resolve_caret_context` now layers `LOCAL_REF` on top of the
descent (`caret_context.py:150-164`), and the UI consumers were wired in `6142d73` — so the path is live end to
end. The "Adjacent fact" note above (`ALIAS_REF` had no UI dispatcher) is therefore also closed by `6142d73`,
not by this commit.

**Still outstanding for `spec-maintainer`** (unchanged by this resolution): the two §18.6 / §5 clarifications
described in *Spec impact* above — caret resolution descends into a body while the tokenizer keeps it opaque
for every other consumer, and `dollar_body_at` should be named on `tokenizer.py` in §5's `sql/` tree.

---

## BUG-042: `[Project]` narration emitted *during* a project close is journalled but never seen — the transition that triggers the line also wipes the panel
**Status:** RESOLVED (b9d1359) — **option C**, shipped 2026-08-10 as a **run-state flag**, not as a prefix move
and not as a content marker. See *Resolution* at the end of this entry: it records what actually shipped and
closes the sub-decision that the *Owner ruling* section below left open. Read the *Owner ruling*,
*Proposed fix* and *Test impact* sections as the state of knowledge **before** the fix; where they conflict
with *Resolution*, *Resolution* wins.
**Reported:** 2026-08-10
**Report (verbatim):** "FQ-019's Activity Log replaces its display buffer on a project transition (`open_project`/`close_project` on the core, driven from `_on_activity_project_changed`). `[Project]` lines narrated *during* a close — the example given is *'N DDL object(s) have local edits pending a batch deploy'* — reach the closing project's `activity.jsonl` correctly, but vanish from the panel immediately, because the transition that triggered them also clears what the panel shows. So a user is told something at exactly the moment they can no longer read it."

**Owner ruling (2026-08-10) — option C, and the naming correction that made it the obvious one**

Close-time `[Project]` narration is routed to the **Messages** tab: the surface that accumulates and survives a
project transition, which is exactly the reason `[Sandbox]` already routes there. Options A/B/D/E below stand
as recorded and are all ruled out.

**Read the cost recorded against option C as stale.** It reads *"a timing-based split of one prefix across two
surfaces, which is what FQ-028's table was built to end"* — but that objection was mostly about the **label**,
not the mechanism. FQ-028's bottom-dock tab was called **Results**, so filing a *message* there looked like a
category error. The owner has since ruled that the name was simply wrong: *"These two panels only bear the same
name… Change name of new Result window to Messages, keep Sandbox's result window."* Two unrelated surfaces had
been sharing one word:

- FQ-028's **bottom-dock tab**, which accumulates `[Check]` / `[Validate]` / `[Lint]` / `[Sandbox]` narration —
  a **message log**. Renamed **Messages**.
- `pgtp_editor/ui/sql_results_panel.py::SqlResultsPanel`, the Sandbox SQL Console's actual **query-result
  grid**. Unchanged, keeps the name "Results".

**No code was ever mis-built by this ambiguity, and that is worth recording plainly.** `SqlResultsPanel` is
constructed in exactly one place, inside the console tab, and was never rerouted; FQ-028 rerouted only
Audit/Problems content, which is what the owner intended throughout. It was a purely ambiguous *label* — which
is also why it produced confusion rather than a defect, and why it survived implementation, spec and manual
passes unnoticed. With the tab named Messages the ruling is not a compromise: a message goes to Messages, and
it joins `[Sandbox]`, which is already there for the same timing reason.

**What does NOT change — this is the constraint that ruled the other options out.** The line is *already*
written correctly to the closing project's `activity.jsonl`, and the core's no-migration rule (entries never
move between stores; `db/activity_log.py:554-573`) stays untouched. This ruling changes only **which panel
renders** the line, never **which store persists** it. Any implementation that starts moving entries between
stores has misread the ruling.

**Sub-decision — SETTLED by the implementation, see *Resolution*; do not re-open.** It was recorded here as
open, and the answer turned out to be *neither of the two shapes below*: a run-state flag
(`AuditRouter.project_closing`) targets the close-time window directly, so no `[Project]` emitter and no
prefix mapping had to move. The two shapes are kept below only as the alternatives that were considered.
`audit_router.DESTINATIONS` routes by **prefix**, so the two shapes were:

1. move the whole `[Project]` prefix to the Messages tab (`PROJECT_PREFIX: TO_RESULTS`), or
2. move only the close-time lines, via a **content marker** — the mechanism `[Schema]` already uses with
   `SCHEMA_VERIFY_MARKER` (`audit_router.py:117`, consumed in `classify` at :141).

The sibling implementing this was told to decide by **reading the actual `[Project]` emitters** rather than
guessing which lines exist. It did, found seven of the eight already correct, and therefore moved neither the
prefix nor any emitter — non-close `[Project]` narration (the checkout-drift path included) is **unchanged**
and still journal-only. Recorded in *Resolution*.

**Implementation state observed in the working tree while writing this entry (uncommitted) — historical
snapshot, superseded by *Resolution*; all of it has since landed in `b9d1359`:**

- The **rename is partly in flight**: `pgtp_editor/ui/findings_panel.py:52-59` already defines
  `RESULTS_TAB_TITLE = "Messages"` with the collision rationale, `main_window.py:3010-3015` adds the view
  action as "Messages", and `audit_router.py`'s module docstring/table and `ui_shell.py:97` are reworded to
  "Messages tab". The identifier `TO_RESULTS` (`audit_router.py:95`) **deliberately keeps its spelling** —
  documented at :90-94 as "a label is not a schema", since every producer test names it.
- The **routing change itself is NOT yet in the tree**: `audit_router.py:109` still reads
  `PROJECT_PREFIX: TO_ACTIVITY`, and no `[Project]` content marker exists.
- `pgtp_editor/ui/sql_results_panel.py` is **untouched**, as intended.
- Nothing here is committed. Do not cite a commit that has not been verified.

**Root cause:** Verified end to end; the reported mechanism is exact.

`DdlProjectController.close_project` (`pgtp_editor/ui/ddl_project_controller.py:440-464`) runs its two
reminder emitters **before** it broadcasts the transition:

```
446    self.offer_pgtp_deploy_on_close()
447    self.remind_pending_deploys_on_close()
...
463    self.project_changed.emit(None, None)
```

`remind_pending_deploys_on_close` (`ddl_project_controller.py:466-483`) is the source of the example line —
it calls `self._shell.audit.addItem(QListWidgetItem(f"[Project] {pending} DDL object(s) have local edits
pending a batch deploy."))` while `self._folder` and `self._settings` are still set (it needs them:
`compute_drift_markers(self._folder, self._settings, schema)` at :476).

The row then travels: `AuditRouter.addItem` (`ui/audit_router.py:176-189`) classifies `[Project]` as
`TO_ACTIVITY` and calls the activity sink → `MainWindow._record_audit_notice`
(`ui/main_window.py:2021-2037`) → `_record_notice` (:2039-2059) → `record_activity` (:1690-1702), which does
`self.activity_log.record(...)` **and** `self.activity_panel.append(entry)`. Because `_folder` is still set,
`_file_activity_source()` (:1676-1688) returns `SOURCE_PROJECT_FILES`, so the entry is persistable into the
closing project's store.

A moment later `project_changed.emit(None, None)` reaches `MainWindow._on_activity_project_changed`
(`ui/main_window.py:1722-1736`), the **first** connected subscriber (`main_window.py:1251-1253`, with the
FQ-028 comment at :1243-1250 explaining why it is first). With `folder is None` it calls
`ActivityLog.close_project` (`pgtp_editor/db/activity_log.py:567-573`):

```
570    self.flush()          # the line DOES reach the closing project's activity.jsonl
571    self._project_dir = None
572    self._entries = []    # <- the display buffer is replaced
573    self._pending = []
```

and then `self.activity_panel.set_entries(self.activity_log.entries)` (`main_window.py:1736`) repaints the
panel from the now-empty buffer. Net effect: **persisted correctly, on screen for microseconds.**

The FQ-028 connection-order mitigation is real but only fixes the **open** direction: on an open, the journal
has already swapped to the new project's store before any later subscriber narrates, so the narration lands in
the store the panel is now showing. On a **close** the narration happens *before* the signal is emitted at all,
so no connection ordering can help it — the emitters run inside `close_project`'s body, upstream of every
subscriber.

Note the wipe is a two-sided loss for a close: the line is gone from the panel *and* the panel is now the
empty standalone buffer, so there is no surface at all in the session that carries it. The only way to read it
is to reopen the project (the entry is in that project's `activity.jsonl`).

**Proposed fix:** Options only — **do not pick one without an owner call**; each trades against a rule the core
imposes deliberately.

The hard constraint to respect in every option: `ActivityLog.open_project`/`close_project`
(`db/activity_log.py:554-573`) exist precisely so entries **never migrate between stores** — a standalone entry
must not leak into a project's `activity.jsonl` and vice versa. Any option that carries lines *across* the swap
is arguing with that rule, and the docstrings at :554-561 and :466-470 state why it exists. It is not an
accident to be patched around.

- **(A) Emit earlier / emit before the transition is even started.** No change: this is already the case — the
  emitters at `ddl_project_controller.py:446-447` run before `project_changed.emit`. The lateness is not in the
  emit, it is in the *panel repaint*, so "emit sooner" cannot help. Record this as ruled out, so nobody
  re-derives it.
- **(B) Swap the display buffer later / carry a tail across the swap.** `_on_activity_project_changed` would
  re-append the last N entries recorded during the transition after `set_entries`. This is the option that
  fights the no-migration rule head-on: those rows belong to the closed project's store, and showing them in the
  standalone buffer means the panel is displaying rows that `flush()` will never own again — a display-only
  divergence from `ActivityLog.entries` that every other part of FQ-019 assumes cannot happen (the panel is a
  pure render of `entries`). Cheap to write, expensive in invariants.
- **(C) Route close-time narration to a surface that survives the transition.** This is what the shipped
  `[Sandbox]` prefix already does: `audit_router.DESTINATIONS` maps `SANDBOX_PREFIX → TO_RESULTS` for exactly
  this reason, documented in CONSOLIDATED_SPEC's routing table (*"a `[Sandbox]` line is emitted during a project
  transition … Results accumulates and survives the transition"*). The close-time `[Project]` reminders are, in
  substance, the outcome of an operation the user asked for (they asked to close), which is the same argument
  that put `[Sandbox]` on Results. Cost: `[Project]` would then be split across two surfaces by *timing*, which
  is exactly the kind of per-line special-casing FQ-028's one-prefix-one-destination table was built to end —
  unless the split is made principled (e.g. a distinct prefix for close-time reminders, or `remind_pending_
  deploys_on_close` reporting through a Results-bound channel by construction rather than by prefix lookup).
  **↑ CHOSEN, 2026-08-10 — and read this bullet's stated cost as superseded: the "Results" tab is now named
  Messages, so the objection (a message filed under Results) was a label problem, not a mechanism problem. See
  *Owner ruling* at the top of this entry.**
- **(D) Hold the reminder as a modal/status affordance instead of a log line.** `close_project` already has a
  precedent one line above: `offer_pgtp_deploy_on_close` (`ddl_project_controller.py:485+`) asks a
  `QMessageBox.question`. §18.3's rule is *"closing is a reminder point, never a forcing point"* — a modal for
  the pending-deploy count would be a forcing point and is probably wrong; a non-modal status-bar line is a
  weaker surface than the one it already fails to reach. Recorded for completeness, weakest option.
- **(E) Accept and make the acceptance honest.** Keep the behaviour but stop pretending the line was
  delivered — e.g. have the close-time reminder say where it went (*"…recorded in this project's activity
  log"*), or drop the reminder entirely on the grounds that a line nobody can read is worse than no line. This is
  the only option that costs nothing structurally.

Whichever is picked, the change site is small and well-bounded: `remind_pending_deploys_on_close`
(`ddl_project_controller.py:466-483`) is the emitter, `MainWindow._on_activity_project_changed`
(`main_window.py:1722-1736`) is the swap, and `ui/audit_router.py`'s `DESTINATIONS`/`classify` is the routing
table. Gotcha for option C: producers call `audit.addItem(...)` and see nothing else (the router deliberately
quacks like the `QListWidget` they were written against) — a per-call destination override does not exist and
adding one reopens the design FQ-028 closed.

**Test impact:** *(pre-fix assessment; ADDRESSED in `b9d1359` — see the test paragraph in *Resolution* for
what was actually kept, corrected and added.)* **⚠ `tests/ui/test_ddl_project_wiring.py` currently ASSERTS THIS DEFECT AS INTENDED
BEHAVIOUR — comment and all — and must be REWRITTEN, NOT EXTENDED.** The close-time assertion (the
`window._ddl_project_ui.close_project()` case, ~:1203-1212) is followed by a comment that spells the bug out as
if it were the design (*"this particular line is emitted DURING the close -- after which FQ-019's project
transition replaces the on-screen buffer … So the reminder is asserted where it durably landed"*) and then
asserts only against the journal file. Under option C the reminder must be asserted on the **Messages** tab as
well; the comment must go, because it is exactly the kind of test prose that makes a bug read like a decision
and is why this behaviour survived review. Keep the `activity_path(project_dir)` journal assertion — the store
side is correct today and is the regression guard for the no-migration rule. Everything below stands as
originally triaged:

`tests/ui/test_ddl_project_wiring.py` already covers this exact area — the test at ~:1184
opens a project with a stale `deployed` hash, calls `window._ddl_project_ui.close_project()` and its trailing
comment literally documents the current (buggy) outcome: *"this particular line is emitted DURING the close --
after which FQ-019's [journal replaces its buffer]"*. That test must be **rewritten, not extended**, whichever
option lands, because it currently asserts the defect as intended behaviour. Also touched:
`tests/ui/test_ddl_project_wiring.py`'s `[Project]`/`activity_panel.row_texts()` assertions around :770-810
(the checkout-drift narration path, same sink, not close-time — should keep passing untouched and is the
regression guard that the open direction was not broken). Core-level coverage lives in
`tests/db/test_activity_log.py` (the `open_project`/`close_project` buffer-replacement contract) — if option B
is chosen it needs a new case pinning whatever "panel may show rows the core does not own" means; options C/D/E
need no core change at all. New cases needed either way: (1) a close with pending deploys leaves the reminder
*readable somewhere* (name the surface), and (2) the closing project's `activity.jsonl` still contains the line
(that part works today and must not regress).

**Spec impact:** **Diverges from an explicitly recorded decision — this is a deliberate, documented caveat, not
an unnoticed bug.** `docs/superpowers/CONSOLIDATED_SPEC.md` (the FQ-028 routing table, ~:813-889) carries a
blockquote titled *"A live, accepted caveat that falls out of the same mechanism — recorded, not fixed"* which
describes this exact close-direction behaviour, states the open direction was mitigated by connection order,
and ends: *"If this ever needs to change it is a new entry, not a quiet patch."* This queue entry is that new
entry. Whichever option is chosen (including E), `spec-maintainer` must be dispatched afterwards to replace
that blockquote and, for option C, to add a row/qualification to the prefix→destination table (which currently
maps `[Project]` → Activity Log unconditionally) plus a Supersession Ledger row. Do not edit the spec here.

**Ruling makes this concrete:** option C is chosen, so after the fix lands `spec-maintainer` must (1) replace
the *"recorded, not fixed"* blockquote with the ruling, (2) amend the prefix→destination table for `[Project]`
— in whichever of the two shapes actually shipped (whole prefix vs. content marker; see *Owner ruling*), (3)
sweep the **Results → Messages** tab rename through the FQ-028 sections, and (4) state the distinction the
rename encodes: the bottom-dock **Messages** tab (a message log) is *not* the Sandbox SQL Console's **Results**
grid (`ui/sql_results_panel.py`), which keeps its name. `manual-maintainer` is also implicated by the rename
(the tab is named in the manual and in the View menu). Still: do not edit the spec or manual from this entry.

**Resolution — `b9d1359`, verified against the tree, 2026-08-10.** Option C, in a third shape that the entry
did not list. Full suite at the time of the fix: 6190 passed, 45 skipped.

*Shape that shipped — a run-state flag, so neither sub-decision option was needed.* `AuditRouter` gains
`self.project_closing = False` (`ui/audit_router.py:217`), read by `addItem` (:227-229) and honoured in
`classify(text, *, schema_verify=False, project_closing=False)` at :175-177:

```
176    if prefix == PROJECT_PREFIX and project_closing:
177        return TO_ACTIVITY_AND_RESULTS
```

`DESTINATIONS[PROJECT_PREFIX]` is **still `TO_ACTIVITY`** (:109), and no `[Project]` content marker exists.
The flag is set around the two close-time emitters in `DdlProjectController.close_project`
(`ui/ddl_project_controller.py:456-463`) in a `try/finally` that restores the previous value, so a modal that
raises inside `offer_pgtp_deploy_on_close` cannot leave later `[Project]` lines mis-routed. This is the same
run-state mechanism `schema_run` already used for `[Schema]` verify rows — the precedent the entry cited for
shape 2, applied at the run level rather than at the text level. "Was this emitted during a close?" is a fact
about the run, and no wording test can answer it.

*Why the prefix was not moved.* All eight `[Project]` emit sites were read: `ddl_project_controller.py:390`
(multiple `.pgtp` found), `:497` (the pending-deploy reminder), `:570` and `:609` (async capability/target
probe failures), the `:626/631/634/638` source-`.pgtp` checksum group, `main_window.py:4249` (sandbox content
inspection) and `:4842` (live-definition drift). Seven are already readable: FQ-019's store-switch-first
ordering puts the open-time ones **after** `project_changed.emit`, and the probe failures are off-transition
entirely. Only `remind_pending_deploys_on_close` emits upstream of a transition. Relocating seven correct
journal lines to fix one is not a fix — which is the concrete answer to the sub-decision above.

*Destination is BOTH, not either.* `TO_ACTIVITY_AND_RESULTS = "activity+results"` (:101-103) is a pairing of
two existing destinations, not a fourth surface. `addItem` (:231-237) calls the activity sink **and**
`_route_results` for that row: the `activity.jsonl` write is unchanged because the line remains part of the
closing project's history, and Messages additionally renders it. This is the only two-destination row type in
the router, and the core's no-migration rule (`db/activity_log.py:554-573`) was not touched — nothing moves
between stores.

*Rename.* `RESULTS_TAB_TITLE = "Messages"` (`ui/findings_panel.py:59`); internals keep the "results" spelling
(`TO_RESULTS`, `results_panel`, `results_tab_index`) on purpose — a label is not a schema. The dock title and
its View-menu toggle were renamed with it (each with a `RENAMED_ID_ALIASES` row in `ui/toolbar_registry.py`),
since both named the tab and would otherwise point at nothing. `ui/sql_results_panel.py` is untouched and
keeps the name "Results".

*Test outcome — the warning below was acted on, with one honest qualification.* No surviving assertion encodes
the defect. `tests/ui/test_ddl_project_wiring.py::test_close_project_reminds_about_pending_ddl_deploys` still
asserts the journal write (`activity_path(project_dir)`), which is **correct and deliberate** under the
two-destination outcome; what was removed is its misleading prose (*"So the reminder is asserted where it
durably landed"*, which read the loss as the design) — replaced with *"The journal write is unchanged and
still the durable record"*. To be precise about the phrasing used in the commit message: the old test's
**comment** was rewritten, its assertion was kept as the no-migration guard, and the corrected behaviour
arrived as two **new** tests immediately after it (~:1217 onward):
`test_the_close_time_reminder_is_still_readable_after_the_close` (project gone, `activity_panel` no longer
shows the line, `results_panel` does) and
`test_ordinary_project_narration_still_goes_only_to_the_journal` (an open-time `[Project]` row stays
journal-only and is **not** duplicated onto Messages — the guard on the seven untouched emitters). The new
coverage was verified to fail with the flag forced off. Re-verified green at triage time: 3 passed.

*Left for `spec-maintainer`* — the four items listed above still apply, with item (2) now concrete: the
prefix→destination table keeps `[Project] → Activity Log` as its default and gains the close-time
`project_closing` qualification plus the `TO_ACTIVITY_AND_RESULTS` pairing; the *"recorded, not fixed"*
blockquote must be replaced, and the manual carries the Messages rename.

---

## BUG-043: sandbox `run_async` workers outlive their `MainWindow` and emit on a deleted C++ object — a rotating, misattributed teardown ERROR that has trained the suite's red output to be ignored
**Status:** OPEN
**Reported:** 2026-08-10
**Report (verbatim):** "`tests/ui/test_deployment_menu.py` reports a failure or a setup/teardown ERROR on roughly one full-suite run in two, and the test named changes between runs — `test_a_projectless_quality_apply_runs_and_reports_under_check`, `test_the_sandbox_confirmation_also_names_the_host_now`, and others in that file. It passes when the file is run alone. Other files have shown the same shape (`test_ddl_explorer_sandbox.py`, `test_database_menu.py`, `test_theme.py`), which suggests the mechanism is not confined to one file. TEARDOWN ERROR: Exceptions caught in Qt event loop: File `pgtp_editor/ui/sandbox_controller.py`, line 1358, in handle / line 1380, in _finish / RuntimeError: Signal source has been deleted. A `run_async` worker started by an earlier test completes after its `MainWindow` has been torn down, and `SandboxController._finish` emits `operation_finished` on a deleted C++ object."

**Root cause:** Verified against the code; the reported mechanism is exact, and the culprit test is identifiable.

The emitting frames are literal:

- `pgtp_editor/ui/sandbox_controller.py:1357-1358` — `_error_handler`'s inner `def handle(exc)` calls
  `self._finish(operation, False, str(exc) or exc.__class__.__name__, on_done)`.
- `pgtp_editor/ui/sandbox_controller.py:1362-1380` — `_finish` ends with `self.operation_finished.emit(result)`.
  `SandboxController` is a `QObject` (`sandbox_controller.py:414`) constructed with the window as parent
  (`main_window.py:1027-1033`, `SandboxController(self, …)`), so when the `MainWindow` is destroyed at test
  teardown the controller's C++ side goes with it and the `emit` raises `RuntimeError: Signal source has been
  deleted`. `handle` runs as a queued slot on the GUI thread, so pytest-qt catches it out of the event loop and
  attributes it to whichever test is running when it lands — which is exactly why the test name rotates.

The delivery path that outlives teardown is `ui/async_task.py::run_async` (:71-105). It is correct by its own
lights and that is what makes this leak durable: `_INFLIGHT` (:44-49) **deliberately holds every task alive
until its result/error has been delivered on the GUI thread**, precisely so a callback can never be dropped.
There is no cancellation seam, no owner check, and nothing ties a task's lifetime to the widget that started
it.

**The concrete culprit is `tests/ui/test_deployment_menu.py::test_the_sandbox_confirmation_also_names_the_host_now`
(:532-555).** It saves a `ProjectSettings(sandbox=ConnectionParams(host="localhost", port="5433",
database="sbox"))` and calls `window._ddl_project_ui.set_active_project(project_dir, settings)`. That reaches
`DdlProjectController.set_active_project` → `self._bind_sandbox()` (`ddl_project_controller.py:425`) →
`MainWindow._bind_sandbox_controller_to_project` (`main_window.py:5590-5654`), whose BUG-040 branch at :5641
(`if settings is not None and params is not None and params.database:`) is **true** here (`database="sbox"`) and
calls `self._open_sandbox_session()` → `SandboxController.open_session`. Inside `open_session`
(`sandbox_controller.py:667-722`) the worker body is:

```
696    def work():
697        caps = self._prober(params)
698        reason = self._blocking_reason(caps)
699        if reason is not None: return None, caps, reason
700        session = self._opener(params, mode=..., schema_names=..., baseline=..., target_params=...)
```

The test stubs `probe_sandbox_capabilities` to return `SandboxCapabilities(is_superuser=True)` (so `_prober`
is safe and `_blocking_reason` at :1251-1266 returns None — configured, no `probe_error`, superuser), and then
`self._opener` is the **real `db/sandbox.py::open_sandbox`**, which really dials `localhost:5433/sbox` on a
threadpool worker. That connection attempt fails (nothing is listening), raising into `run_async`'s error
channel → `handle` → `_finish` → emit. The failure can take as long as the OS TCP path takes, which is why it
lands in a *later* test, and why it is load-dependent (hence "one run in two", and why the file passes alone).

**The test already knows about the hazard and fixes the wrong seam.** Its comment at :544-547 says exactly
this — *"Opening a project starts an off-thread capability probe. Stubbed and made synchronous so its result
cannot land after this window is destroyed"* — and it stubs `window._ddl_project_ui._run_async` (:548-550).
That covers `DdlProjectController`'s two probes only. It does **not** cover `SandboxController`, because the two
controllers get their runner from different places:

- `DdlProjectController._run_async = shell.run_async` (`ddl_project_controller.py:160`), and `UiShell.run_async`
  is `MainWindow._shell_run_async` (`main_window.py:1157`, :1952-1958) — a **trampoline that re-reads
  `self._run_async` at call time**, specifically so the suite can inject a synchronous stand-in by assigning
  `window._run_async`.
- `SandboxController._run_async = run_async` (`sandbox_controller.py:482`) — **the module-level function,
  captured in `__init__`, bypassing the trampoline entirely.**

So `window._run_async = sync` — the project's documented convention, asserted as a seam in
`tests/ui/test_mainwindow_surface.py:284` — silently does **not** make the sandbox lane synchronous. That
asymmetry is the real defect; the flaky test names are the symptom.

Blast radius beyond this one test: `refresh_capability_status` (`ddl_project_controller.py:507-557`) and
`refresh_target_connection_status` (:559-596) *also* fire an async task on every `set_active_project`, and the
latter runs a real `db_test_connection(target)` whenever a target host is configured. Those go through the
trampoline, so `window._run_async` fixes them — but their result slots (`capability_status_changed.emit`,
`self._refresh_status_window()`) are the same deleted-object hazard for any test that stubs neither. There are
**58 `set_active_project` call sites across 12 files under `tests/ui/`**; the ones with **no** `sync_run` and no
`_run_async` stub at all are `test_database_menu.py`, `test_ddl_object_editor_wiring.py`,
`test_ddl_project_wiring.py`, `test_deployment_menu.py` and `test_generation.py`. Of those, only
`test_deployment_menu.py:532` currently configures a sandbox `database`, so it is the one that reaches the
*sandbox* leak today — the others are latent (they leak only fast, harmless tasks now, and become real leaks the
moment someone adds a host/target to their settings).

**Proposed fix:** Three levels; they are complementary rather than exclusive, and the recommendation is to take
the per-controller one as the actual fix and the per-test one as cleanup, with the per-fixture one only if the
first two prove insufficient.

- **Per-controller (recommended as the fix — closes the class of bug, not the instance).** Two sub-parts:
  1. **Route `SandboxController`'s runner through the same trampoline everything else uses.** In
     `MainWindow.__init__`, right after the `SandboxController(...)` construction at `main_window.py:1027-1033`,
     assign `self.sandbox_controller._run_async = self._shell_run_async` (do **not** pass `run_async` as a
     constructor kwarg captured at build time — the whole point of `_shell_run_async` is the call-time read, see
     its docstring at :1952-1958). After this, the existing, documented `window._run_async = sync_run`
     convention covers the sandbox lane too, and ~5 test files stop being able to leak by omission.
     Gotcha: `sandbox_controller.py:481-482`'s comment claims the attribute follows "the
     ConnectionSetupDialog/NewProjectDialog convention" — that comment becomes wrong and must be updated in the
     same change, or the next reader will re-break it.
  2. **Make `_finish` survive a dead receiver.** Guard the emit at `sandbox_controller.py:1380` — e.g. wrap in
     `try/except RuntimeError` with a `debuglog` note, or test `shiboken6.Shiboken.isValid(self)` before
     emitting. Prefer the `try/except` (no new import, and it also covers the `on_done` callback at :1378-1379,
     which can equally be a bound method of a deleted panel — note `on_done` runs *before* the emit, so a guard
     on the emit alone does not cover it; wrap both). This is defence in depth for production too: nothing
     in the app cancels an in-flight sandbox operation when a project closes or the window is destroyed, so the
     same `RuntimeError` is reachable by a user who closes the app mid-probe.
  3. Optionally, the deeper version: give `run_async` an owner/cancel seam (`ui/async_task.py:71-105`) so a task
     can be dropped when its owner dies. Bigger change, touches the `_INFLIGHT` invariant documented at :44-49
     (which exists to stop *silently dropped* callbacks — the exact opposite failure), so do not do this
     casually; the guard in (2) buys most of the benefit for none of the risk.
- **Per-test (cleanup, not sufficient alone).** Fix `test_deployment_menu.py:532-555` to stub
  `window.sandbox_controller._run_async` (or `window._run_async` once fix 1 lands) rather than only
  `window._ddl_project_ui._run_async`, and audit the five no-stub files above. `tests/ui/_sandbox_stubs.py::sync_run`
  (:21-27) is the established stub and should be the one used — 18 files already import it. This alone is
  insufficient because nothing prevents the next test from omitting it; the omission is invisible until it
  poisons someone else's run weeks later.
- **Per-fixture (safety net; consider alongside, not instead).** An autouse fixture in `tests/ui/conftest.py`
  (which already hosts two autouse leak-guards with the same rationale — the app-style/palette reset and
  `_isolated_qsettings`, both added because process-wide state leaked between tests) that after each test
  drains `QThreadPool.globalInstance().waitForDone(timeout)` **before** widgets are destroyed, and/or fails the
  test that leaves a task in `async_task._INFLIGHT`. The failing-loudly variant is the valuable one: it
  attributes the leak to the test that *caused* it instead of the one that was running when it landed, which is
  the whole complaint here. Gotcha: qtbot destroys widgets at its own teardown, so ordering against
  `qtbot.addWidget`'s cleanup matters — a drain that runs after widget destruction is too late and just makes
  the crash deterministic instead of preventing it.

**Test impact:** Existing coverage of the seam: `tests/ui/test_async_task.py` (the real threadpool path, the one
test that deliberately does *not* stub), `tests/ui/test_sandbox_controller.py:213` (`controller._run_async =
runner`, the controller-level injection), `tests/ui/test_mainwindow_surface.py:284,314` (asserts `_run_async`
and `_shell_run_async` exist as seams — **this is where a new assertion belongs** that
`window.sandbox_controller._run_async` is the trampoline, i.e. that stubbing `window._run_async` reaches the
sandbox lane), and `tests/ui/_sandbox_stubs.py::sync_run` (the shared stub, used by 18 files). The file to fix
is `tests/ui/test_deployment_menu.py` (:532-555). New cases needed: (1) `SandboxController._finish` does not
raise when its receiver has been deleted (construct a controller, delete the parent, invoke `_finish`, assert no
`RuntimeError` — also covers the `on_done` callback), (2) assigning `window._run_async` makes a
`_bind_sandbox_controller_to_project`-triggered `open_session` synchronous, and (3) if the conftest guard is
adopted, a self-test that a leaked in-flight task fails its own test. **Verification note carried over from the
report: the failure reproduces on stashed, untouched code, confirmed three times — it is not a regression from
any recent work, so do not go looking for one.**

**Spec impact:** None for the behaviour itself. `CONSOLIDATED_SPEC.md` §30's test-environment section describes
the parallel-suite convention but records no rule about async-seam stubbing; if the per-fixture guard or the
trampoline change lands, it is worth one sentence there — *"every off-GUI-thread seam is reachable from
`window._run_async`"* — as a testability invariant. Flag `spec-maintainer` after the fix lands; do not edit the
spec here. Note also that `sandbox_controller.py:481-482`'s in-code comment about the injection convention is
documentation that will be falsified by the recommended fix and must be corrected with it.

---
## BUG-044: every ALTER on one table shares ONE `applied` bookkeeping row and silently overwrites it, so `Check Object in Sandbox` gives a WRONG verdict about which statement the sandbox holds

**Status:** OPEN
**Reported:** 2026-08-10
**Report (verbatim):** "Investigate a suspected defect in applied-DDL bookkeeping. The claim: all alter operations on a single table share one bookkeeping row and overwrite each other. […] If the chain holds, `REASON_ALREADY_APPLIED` can compare a buffer's sha1 against a row that describes a *different statement* on the same table. That is not a missing answer, it is a **wrong** answer."

**Verdict: the defect is REAL, and every link in the reported chain is confirmed.** It is reachable through
ordinary use (two Alter Table ▸ … generations on one table, each committed to the sandbox), not through any
unusual sequence.

**Root cause:** the `applied` bookkeeping table is keyed by an OBJECT identity, and an ALTER buffer carries no
object identity to put in it, so all ALTERs on a table collapse onto one row.

1. **The key.** `pgtp_editor/db/sandbox.py:735-746` — `PRIMARY KEY (kind, schema_name, object_name,
   table_name)`; spelled once as `CheckRequest.working_set_ref` (`pgtp_editor/db/ddl_check.py:594-601`,
   `return (self.kind, self.schema, self.name, self.table or "")`).
2. **`AlterDdlRef.name` is `""` and is never set — confirmed.** `pgtp_editor/ui/main_window.py:487` declares the
   default; there is exactly **one** construction site in the whole tree, `MainWindow._open_generated_alter_ddl`
   (`main_window.py:4645-4655`), and it passes `schema`, `table`, `operation`, `serial`, `statement`, `subject`
   — never `name`. `grep -rn "AlterDdlRef(" pgtp_editor tests` returns that single line. There is no second
   construction site that would change the picture.
   **This emptiness is deliberate and load-bearing** (`main_window.py:435-440`): `CheckRequest.checked_name`
   derives from `name`, and `build_ladder` (`ddl_check.py:971-977`) adds tier 3's `plpgsql_check` statements
   only `if request.checked_name`. An ALTER creates no function to lint, so an empty name is what keeps tier 3
   honestly off. `tests/ui/test_ddl_creation_wiring.py:507` pins `ref.name == ""` with that reason. **This is
   the fix's central gotcha — see below.**
3. **`subject` never reaches the key — confirmed.** `CheckRequest.from_ref` (`ddl_check.py:528-541`) reads
   `kind`, `schema`, `name`, `arg_types`, `table` and nothing else; `subject` (the one field that distinguishes
   `DROP INDEX pr.idx_a` from `DROP INDEX pr.idx_b`, `main_window.py:471-481`) is read only by
   `qualified_subject` / `short_title` / `qualified`, i.e. by tab titles and confirmation text. `CheckRequest`
   has no field for it at all.
4. **The recording path is reached.** `MainWindow._apply_ddl_object_to_sandbox` (`main_window.py:6290`) builds
   the request from the alter ref and calls `SandboxController.run_apply` → `ddl_check.apply_and_check`
   (`ddl_check.py:1393`, `record_applied=True` at :1429) → `build_ladder` :965-968 →
   `applied_upsert_sql(request.working_set_ref, ddl_text)`. Nothing anywhere gates on `kind == "alter"`
   (`grep '"alter"'` in `ddl_check.py` and `ddl_object_editor.py`: no hits), so alter tabs take exactly the
   object path.
5. **The collision is silent.** `applied_upsert_sql` (`sandbox.py:790-798`) ends
   `ON CONFLICT (kind, schema_name, object_name, table_name) DO UPDATE SET applied_at = EXCLUDED.applied_at,
   text_sha1 = EXCLUDED.text_sha1` — the second ALTER overwrites the first's row in place, no error, no trace.

So **every** ALTER buffer on `pr.invoice` writes the key `("alter", "pr", "", "invoice")`.

**How many operations actually collide: seventeen, not sixteen.** From `pgtp_editor/ui/ddl_buffer_panel.py`:
8 column ops (`ALTER_TABLE_COLUMN_ACTIONS`, :144-153: add/drop/rename column, change type, set/drop NOT NULL,
set/drop DEFAULT) + 4 constraint ops (:155-160: add constraint, add foreign key, drop/rename constraint) +
2 index ops (:162-165: create/drop index) + 2 comment ops (:174-180: table comment from the table node, column
comment from a column leaf) + `Drop Table…` (:188-190) = the **sixteen** of `ALTER_TABLE_ALL_ACTIONS` (:231-234,
whose own comment says "all sixteen"). **Plus `OP_CREATE_TABLE`** (:135), which is not on the submenu but
produces an `AlterDdlRef` through the same `_open_generated_alter_ddl` with `table=` *the table being created* —
so a `CREATE TABLE pr.invoice` row and every later ALTER on `pr.invoice` collide too. **Seventeen.**
Worse, the collision is not only across operations: two `Drop Column…` generations on the same table (different
columns) are two different statements with the same key, so even a single operation collides with itself.

**Concrete reproduction of the WRONG verdict** (sandbox session open, table `pr.invoice`):

*A — a false "does NOT match", on a buffer that was applied verbatim and never edited:*
1. Right-click `pr.invoice` ▸ Alter Table ▸ **Add Column…**, column `note text` → tab A holds
   `ALTER TABLE pr.invoice ADD COLUMN note text;`. `Deployment ▸ Check and commit to sandbox` → commits; row
   `("alter","pr","","invoice")` written with `sha1(A)`.
2. Right-click `pr.invoice` ▸ Alter Table ▸ **Drop Column…**, column `legacy` → tab B holds
   `ALTER TABLE pr.invoice DROP COLUMN legacy;`. `Check and commit to sandbox` → commits; **the same row is
   UPDATEd** to `sha1(B)`. Tab A's record is gone.
3. Focus **tab A** (untouched since step 1), `Parsing ▸ Check Object in Sandbox`. `_recheck_tier2`
   (`ddl_check.py:1837-1849`) finds the row, `sha1(A) != sha1(B)` → `CAVEAT_STALE_BUFFER` →
   `sandbox_comparison` (`main_window.py:401-407`) → modal: **"ALTER TABLE pr.invoice does NOT match what the
   sandbox holds."** plus *"this buffer has changed since it was last applied"*. Both sentences are false: the
   buffer never changed and the sandbox does hold its effect.

*B — a false "already applied", on a buffer that was NEVER applied:*
1. Apply tab A as above (row written).
2. Generate tab B (Drop Column) and **do not apply it**. Focus it, `Parsing ▸ Check Object in Sandbox`.
3. The row for the key exists, so `_recheck_tier2` returns `STATUS_PASSED` with
   `REASON_ALREADY_APPLIED` — *"the sandbox already holds this object, applied &lt;when&gt;"* — for a statement
   the sandbox has never seen. The honest answer is `REASON_NOT_IN_WORKING_SET` (*"apply it to the sandbox
   first"*). The stale caveat downgrades only the *modal* to DIFFERS; **tier 2's status is `passed`, and
   `_tier0_outcome` (`ddl_check.py:1658-1666`) mirrors tier 2 — so tier 0 reads `passed` too**, and the report
   is recorded for Apply-to-Target's precondition 2 via `panel.record_check_report`
   (`main_window.py:6437`, `ddl_object_editor.py:1104-1109`).

Two consequences worth recording alongside:
- **The working-set sweep sees one ALTER per table, whichever was applied last.** `check_working_set`
  (`ddl_check.py:1920`) keys its result dict by `applied_ref(row)`, and `request_from_applied` (:1889-1917)
  rebuilds `CheckRequest(kind="alter", schema, name="", table)` — a request that cannot describe *any*
  statement. When the deployment generator (named the table's ONLY remaining reader, `sandbox.py:1026-1032`)
  is built, N-1 of every N ALTERs applied to a table will be invisible to it.
- **`SandboxSession.reset()` deliberately spares `BOOKKEEPING_SCHEMA`** (`sandbox.py:1050-1067`), so these rows
  outlive a sandbox reset: after a reset the surviving `("alter","pr","","invoice")` row still answers
  "already applied" for a sandbox that no longer holds the change at all.

**Proposed fix.**

*The shape.* Give an ALTER buffer a bookkeeping identity of its own and put it in `object_name` — **without**
touching `AlterDdlRef.name`.

1. `pgtp_editor/db/ddl_check.py`, `CheckRequest`: add a field
   `working_set_name: str | None = None` (documented as *"the `object_name` slot of the `applied` key when it
   is NOT the checked routine's name — an ALTER has no routine name and must never be given one, because
   `checked_name`/`build_ladder` would then switch tier 3 on"*), and change `working_set_ref` (:594-601) to
   `return (self.kind, self.schema, self.working_set_name if self.working_set_name is not None else self.name,
   self.table or "")`. **Do not** widen `name`, and **do not** derive `checked_name` from the new field —
   `tests/ui/test_ddl_creation_wiring.py:507` and `main_window.py:435-440` exist precisely to stop that.
2. `CheckRequest.from_ref` (:528-541): populate it from the ref, e.g.
   `working_set_name=str(getattr(ref, "working_set_name", "") or "") or None`, and add a
   `working_set_name` property to `AlterDdlRef` (`main_window.py:420-534`, beside `qualified_subject`) that
   returns the per-statement identity. Keeping the derivation on the ref — the thing every consumer already
   reads — matches how `statement`/`subject` were placed there in FQ-025 and keeps `from_ref` free of
   `kind`-specific branching.
3. **What that identity should be** — the recommendation is `db/sandbox.py::text_sha1(buffer_text)` of the
   statement itself (reuse the existing helper; do not hash independently — its docstring says why). It is the
   only value that is genuinely per-statement: `operation` alone collides across two Drop Column generations,
   and `operation + subject` still collides for two different columns because `subject` is `""` for every
   `ALTER TABLE` flavour. Note this means `from_ref` must take the identity from `buffer_text`, which it
   already receives.
   With it: re-applying the identical text upserts in place (idempotent, correct); two different ALTERs write
   two rows; and `recheck` on an edited alter buffer finds **no** row and says `REASON_NOT_IN_WORKING_SET`
   rather than a false `passed`. A side effect to state in the docstring rather than discover later:
   `CAVEAT_STALE_BUFFER` becomes structurally unreachable for `kind == "alter"`, which is right — an edited
   ALTER is a *different statement*, not a stale version of one object.
4. Consider improving `sandbox_comparison`'s `COMPARISON_ABSENT` headline for alters (*"The sandbox does not
   hold ALTER TABLE pr.invoice at all."* reads oddly for a mutation; *"this statement has not been applied to
   the sandbox"* is the honest sentence). Optional, and separable from the correctness fix.

*Gotchas.*
- **No DDL migration is needed, and that is the main argument for reusing `object_name` over adding a fifth key
  column.** `_CREATE_BOOKKEEPING_SQL` is `CREATE TABLE IF NOT EXISTS` only (`sandbox.py:735-746`) with no
  migration mechanism anywhere, and `reset()` never drops the bookkeeping schema — so an existing sandbox's
  `applied` table would silently keep a 4-column PK forever if a new column were added.
- Nothing else may start reading `working_set_name`: `identity`, `regprocedure_text`, `trigger_drop_target` and
  `checked_arg_types` must all keep deriving from `name`.

*The one design choice inside the fix — I judge this the OWNER's, not mine.* Two questions, both about what
`applied` MEANS rather than about code shape:
- **(i) State vs. event log.** Keying alter rows by statement text turns the alter part of `applied` into an
  append-only event log (one row per distinct ALTER ever applied, unbounded), while the object part stays a
  desired-state table (one row per object). That is arguably exactly right — an ALTER *is* an event — but it
  changes the table's meaning for the not-yet-built deployment generator, which is its only remaining reader,
  and the spec presents `applied` as state. The alternatives are `operation+subject` keying (bounded rows, but
  still gives a wrong answer for two different columns) or **not recording alter buffers at all**
  (`record_applied=False` for `kind == "alter"`, with a stated *"an ALTER is not an object; the working set
  records objects"* tier-2 reason — correct-by-construction, but the deployment generator then never sees an
  ALTER).
- **(ii) The rows already written.** Existing `("alter", schema, "", table)` rows will match no request after
  the fix and become inert orphans that read as "not in working set" — honest, since they cannot be attributed
  to any statement, but they linger through resets. Leave them, or issue a one-time
  `DELETE FROM pgtp_editor_sandbox.applied WHERE kind = 'alter' AND object_name = ''` at session open?
Please file these with `owner-decision`; I have not written to `docs/DECISION_QUEUE.md`.

**Test impact.** Existing coverage to EXTEND, not duplicate:
- `tests/db/test_ddl_check.py` — `:1353` `test_apply_and_check_commits_and_writes_the_working_set_row`,
  `:1456` `test_recheck_tier2_reports_the_applied_timestamp`, `:1467`
  `test_recheck_warns_when_the_buffer_differs_from_what_was_applied`, `:1475`
  `test_recheck_tier2_is_unavailable_for_an_object_not_in_the_working_set`, `:825`
  `test_request_from_applied_degrades_honestly_rather_than_guessing`, `:1255` `test_tier0_collapses_into_tier2`.
- `tests/db/test_sandbox.py` — `:883` `test_sandbox_session_apply_upsert_carries_ref_fields_and_a_sha1_hash`,
  `:1246` `test_applied_upsert_sql_is_one_statement_carrying_the_ref_and_the_hash`.
- `tests/ui/test_ddl_creation_wiring.py` — `:493`
  `test_the_alter_tab_identifies_itself_as_an_alter_not_an_object` (**must keep asserting `ref.name == ""`** and
  gain the `working_set_name` assertion beside it), `:510`
  `test_two_generations_get_two_tabs_never_one_silently_reused`.
- `tests/ui/test_sandbox_check_console_wiring.py` and `tests/ui/test_mainwindow_surface.py` cover the check
  gestures and `sandbox_comparison`.

New cases needed: (1) two different `AlterDdlRef`s on one table produce **different** `working_set_ref`s
(the direct regression test); (2) `CREATE TABLE pr.invoice`'s ref and a later `ALTER TABLE pr.invoice` ref do
not collide; (3) two `Drop Column…` generations on the same table with different columns do not collide;
(4) `_recheck_tier2` returns `REASON_NOT_IN_WORKING_SET` (not `REASON_ALREADY_APPLIED`) for an alter buffer
whose statement was never applied while a *different* alter on the same table was — reproduction B above, the
false-`passed` case; (5) reproduction A end-to-end at the `sandbox_comparison` level: tab A applied, tab B
applied, tab A rechecked → `COMPARISON_MATCHES`, not `COMPARISON_DIFFERS`; (6) `build_ladder` still emits **no**
tier-3 statements for an alter request that now carries a `working_set_name` — the guard against the fix
switching `plpgsql_check` on for ALTERs.

**Spec impact:** `CONSOLIDATED_SPEC.md` §18.5 D2's working-set section (lines ~6906-6931) states the `applied`
table verbatim as `primary key (kind, schema_name, object_name, table_name)` and describes it purely in terms
of *objects* — it predates FQ-025's ALTER buffers and **nowhere considers a buffer that is a mutation rather
than an object**, so the current behaviour is an unnoticed gap, not a recorded decision. The fix diverges from
that spelling and must be folded in: flag `spec-maintainer` after it lands, to state (a) what an ALTER's
bookkeeping identity is and why it is not the object identity, (b) whichever answer the owner gives to design
choice (i), and (c) the consequence for `text_sha1`'s stale-buffer role on alter buffers.
**Related, do NOT treat as guidance:** `docs/DECISION_QUEUE.md` DEC-005 asks about `DROP INDEX` bookkeeping on
an inverted premise (it claims the *table* is missing; the table is present and the *index name* is absent) and
carries an owner answer given against that false premise, plus a CAUTION block saying so. Read it for
background only. Its answer — *"a schema-qualified index name is a unique identity on its own"* — is about a
question this bug supersedes: the actual `DROP INDEX` row today carries **neither** the index name **nor** any
distinguishing value, and is one of the seventeen colliders above. Do not write to `DECISION_QUEUE.md`.

---
## BUG-045: `SchemaIndex` publishes no `ColumnInfo` list and no routine accessor — `ui/schema_gesture_seam.py` reaches into the private `_schema`, and `sql/join_fk.py`'s docstring describes a caller that cannot be written
**Status:** OPEN
**Reported:** 2026-08-10
**Report (verbatim):** "`db/schema_index.py::SchemaIndex` publishes no `ColumnInfo` list and no routine accessor, so FQ-030's schema gestures reach around it into a private attribute — and `sql/join_fk.py`'s docstring describes a caller that cannot be written. (1) `SchemaIndex`'s entire public surface is `known_schemas` / `known_tables` / `known_columns` (names only) / `column_entries` (pre-rendered display strings) / `trigger_for_function`; the underlying `DatabaseSchema` is the private `self._schema`, there is no `schema()` accessor, no accessor returning `ColumnInfo` objects, and nothing that touches `schema.routines` at all. (2) Consequence A — a docstring that describes an impossible caller: `foreign_keys_from_targets`' docstring says the caller 'is a one-liner over its `ColumnInfo` list', which cannot be written against `SchemaIndex`'s public API. (3) Consequence B — `ui/schema_gesture_seam.py::_database_schema` probes for a public `schema()` and falls back to `index._schema`. §5's dependency posture exists to keep `ui/` off other packages' internals; the docstring is actively false; and it silently pins `SchemaIndex.__init__`'s attribute name. Behaviour today is correct — this is a structural/encapsulation defect plus a false docstring. Note `known_columns`/`column_entries` are relied on by §18.6 completion and must stay exactly as they are — this is a widening, not a change. Also note `known_tables` and `trigger_for_function` both take a *parameter* named `schema`."

**Root cause:** Confirmed in the tree at HEAD (2026-08-10). Three files, one missing accessor pair.

1. `pgtp_editor/db/schema_index.py:45-143` — `SchemaIndex`'s public surface is exactly `known_schemas` (:76), `known_tables` (:81), `known_columns` (:91, `[column.name for column in info.columns]` — names only), `column_entries` (:99, `(key, display)` pairs built once in `__init__` at :70-73) and `trigger_for_function` (:125). The `DatabaseSchema` is stored as the private `self._schema` at :49 and is read only from inside the class. **`ColumnInfo.fk_target` and `DatabaseSchema.routines` are therefore unreachable through the public API** — `known_columns` flattens columns to names, `column_entries` flattens them to display strings, and nothing anywhere on the class touches `.routines`.

2. `pgtp_editor/ui/schema_gesture_seam.py:75-85` — `_database_schema(index)` works around (1):
```python
getter = getattr(index, "schema", None)
if callable(getter):
    try:
        return getter()
    except TypeError:  # pragma: no cover - a stub with a different arity
        return None
return getattr(index, "_schema", None)
```
   Its two consumers are `table_columns` (:88-93, reads `schema.tables[qualified].columns` to get the `ColumnInfo` list `foreign_keys_for` at :96-114 needs for `fk_target`) and `routine_signatures` (:133-150, reads `schema.routines.values()` for `args`/`return_type`/`kind`). Both are fully duck-typed with empty defaults, so a keystroke path cannot raise — the fallback is honest and commented (module docstring :34-45, "READING FACTS `SchemaIndex` DOES NOT PUBLISH"), but it is `ui/` reading a `db/` object's private attribute on a path that runs from a keystroke, and it silently pins the name `_schema`: renaming that attribute would break `Ctrl+Alt+J` and `Ctrl+Shift+Space` with **no test failing at the `db/` end** (`tests/db/test_schema_index.py` never touches it).

3. `pgtp_editor/sql/join_fk.py:339-344` — `foreign_keys_from_targets`' docstring: *"This is the one place that string's shape is known, so the caller is a one-liner over its `ColumnInfo` list and `sql/` still never sees a schema."* That one-liner cannot be written against `SchemaIndex` today; the actual caller (`schema_gesture_seam.foreign_keys_for`) gets its `ColumnInfo` list from the private-attribute reach. The docstring is actively false, and it is the docstring of the module that owns the `"schema.table.column"` shape — the first place a future reader looks to learn how to call it.

Nothing is user-visibly broken: both gestures work correctly today (24 tests in `tests/ui/test_schema_gestures.py`). Rank this as structural debt, not a user-facing defect.

**Proposed fix:** A **widening** of `SchemaIndex` plus a seam rewire and a docstring correction. `known_columns` and `column_entries` are **not touched** — §18.6 completion and the `hr.employee.` cascade depend on their exact shapes.

**(a) `pgtp_editor/db/schema_index.py` — two new accessors, next to the existing column accessors.** Suggested names and contracts (avoid `schema()`: `known_tables` and `trigger_for_function` both take a parameter spelled `schema`, and `_column_display`/`__init__` use the name locally — a method called `schema` would read as a shadow at every call site even though Python would not actually break):

```python
def column_infos(self, table: str) -> list[ColumnInfo]:
    """`table`'s `ColumnInfo` objects (the schema-qualified `"schema.table"`
    key `known_columns` uses), or `[]` when the fetch never saw it."""
    info = self._schema.tables.get(table)
    return list(info.columns) if info is not None else []

def routines(self) -> tuple[RoutineInfo, ...]:
    """Every fetched routine, in `DatabaseSchema.routines` order.
    Overloads are separate entries (that dict is keyed by
    `RoutineInfo.signature` — name PLUS argument types, §18.1)."""
    return tuple(self._schema.routines.values())
```
- `column_infos` must return a **new list**, not `info.columns` itself, so a caller cannot mutate the fetch.
- `routines()` must preserve `dict.values()` order — `routine_signatures` feeds `signature_help`, which ranks overloads by arity fit and is otherwise order-stable; reordering here could reshuffle equally-ranked overloads and break `tests/ui/test_schema_gestures.py`'s signature assertions.
- `RoutineInfo` must be added to the `from .introspect import ...` line at `schema_index.py:35` (`ColumnInfo`, `DatabaseSchema`, `TriggerInfo` are already there).
- **Do NOT import anything from `sql/` into `db/schema_index.py`** — the `RoutineSignature` adaptation stays in the seam. `db/` returning its own `RoutineInfo` keeps `sql/`'s "never sees a schema" property intact.

**(b) `pgtp_editor/ui/schema_gesture_seam.py` — delete `_database_schema` (:74-85) and point both consumers at the new accessors.** Keep the duck-typed tolerance (a stub index, an index that predates the accessors, a table the fetch never saw must all yield "nothing to offer", never an exception — this runs off a keystroke):
```python
def table_columns(index, qualified: str) -> list:
    getter = getattr(index, "column_infos", None)
    if not callable(getter):
        return []
    try:
        return list(getter(qualified) or ())
    except Exception:      # pragma: no cover - defensive at a keypress
        return []
```
and the same shape in `routine_signatures` over `getattr(index, "routines", None)`. `foreign_keys_for` (:96-114) and `signature_help_at` (:153-160) need no change.
- **GOTCHA — do not add a `db.introspect` import to this module.** `tests/ui/test_schema_gestures.py::test_signature_help_reads_no_database` reads the module source and asserts `"db.introspect" not in source`. Keep reading `column.name` / `column.fk_target` / `routine.args` duck-typed via `getattr` exactly as today (:110-111, :144-147); no `ColumnInfo`/`RoutineInfo` type annotations or `TYPE_CHECKING` import.
- Rewrite the module docstring's "READING FACTS `SchemaIndex` DOES NOT PUBLISH" block (:34-45) — after the fix it publishes them; the paragraph should instead say the two gestures read `column_infos`/`routines` and that everything stays tolerant of absence because this runs off a keystroke.

**(c) `pgtp_editor/sql/join_fk.py:339-344` — correct the docstring** so it names the caller that now exists, e.g. *"…so the caller is a one-liner over `SchemaIndex.column_infos(table)` — `[(c.name, c.fk_target) for c in index.column_infos(qualified)]` — and `sql/` still never sees a schema."* Docstring only; `foreign_keys_from_targets`' behaviour is unchanged.

**(d) Optional, only if the resolver wants it enforced:** `tests/ui/test_collaborator_boundaries.py` polices `ui/*_controller.py` modules by source inspection; a "no `ui/` module reaches a `_`-prefixed attribute on an injected `db/` object" rule is **out of scope for this fix** — do not widen that test here.

**Test impact:**
- `tests/db/test_schema_index.py` (235 lines, 21 tests) — **extend, do not create a new file.** New cases, following the existing fixture style: `column_infos` returns real `ColumnInfo` objects carrying `fk_target`/`is_pk`/`default` (not names, not display strings); `column_infos` on an unknown table is `[]`; mutating the returned list does not disturb `known_columns`/`column_entries` (the copy guarantee); `routines()` returns every fetched routine with two overloads of the same name as two entries; `routines()` is `()` for a tables-only `DatabaseSchema` (`fetch_schema`'s shape). The existing `test_known_columns_is_unchanged_by_the_richer_accessor` (:187) is the precedent for a "the widening changed nothing" test — add its sibling for `column_infos`.
- `tests/ui/test_schema_gestures.py` (24 tests) — the **regression guard**: every one must stay green *unchanged*, since behaviour is identical. Add one source-inspection test in the style of the existing `test_signature_help_reads_no_database` asserting the seam no longer reaches the private attribute. **GOTCHA:** a naive `assert "_schema" not in source` will FALSE-POSITIVE — `SchemaGestureHostMixin` legitimately reads `self._schema_index` (:218, :264) and the docstring mentions it (:191). Assert on the reach itself: `"_database_schema" not in source` and `'"_schema"' not in source` (the `getattr` string literal).
- `tests/sql/test_join_fk.py` — docstring-only change, no test needed.
- No new test file. `tests/sql/test_package_purity.py` stays satisfied (nothing new is imported into `sql/`).

**Spec impact:** **Three places in `CONSOLIDATED_SPEC.md` must be updated by `spec-maintainer` after the fix lands — this is a spec-recorded debt being paid, so the record must be retired or it becomes a dead assertion.** (1) §18.9's blockquote "⚠ A DEBT THE SEAM PAYS FOR, RECORDED SO IT IS NOT MISTAKEN FOR THE INTENDED SHAPE" (~lines 8742-8754) describes the private-attribute fallback and the false `join_fk.py` docstring as current state and says the fix was *"filed to `bug-triager` on 2026-08-10 rather than fixed here"* — retire or rewrite it once resolved. (2) §18.6's `SchemaIndex` member table (~lines 8040-8046) lists the public surface and must gain rows for `column_infos` and `routines`. (3) The repository-map line for `schema_index.py` (~line 615, *"SchemaIndex — known_schemas/known_tables/known_columns/trigger_for_function"*) needs the new members. Also note the 2026-08-10 Supersession Ledger row (~line 9764) ends with *"One debt recorded, not hidden … dispatched to `bug-triager`, not fixed here"* — a follow-up ledger row should record that it was paid. **The current behaviour was never an intentional design decision** — the spec explicitly calls it debt, not the intended shape, so the fix needs no design reversal. `bug-triager` does not edit the spec; flag for `spec-maintainer`.

---
## BUG-046: `Ctrl+Shift+B` is hosted twice — a `QAction` *and* a `CodeEditor.keyPressEvent` branch — on a premise ("QShortcut is unreliable offscreen") that is measurably FALSE
**Status:** OPEN
**Reported:** 2026-08-10
**Report (verbatim):** "Ctrl+Shift+B must be handled the same way as other keyboard shortcuts: a QShortcut/QAction in the normal run, with direct key-press handling used only in testing. A test-environment constraint should not shape the production path."

This is an owner **ruling to implement**, not a question to re-open. The design it reverses is
recorded in `CONSOLIDATED_SPEC.md` §8 as *"measured, then KEPT"* — see **Spec impact**.

### Root cause

The chord has two live hosts:

1. `pgtp_editor/ui/main_window.py:2415-2418` (`MainWindow._build_select_menu`) —
   `Select ▸ Select Enclosing Block`, `setShortcut("Ctrl+Shift+B")`, dispatching by capability in
   `_select_enclosing_block` (`main_window.py:2429-2460`).
2. `pgtp_editor/ui/code_editor.py:740-746` (`CodeEditor.keyPressEvent`) — an unconditional
   `Ctrl+Shift+B → self.select_enclosing_brackets()` branch, ahead of everything else in the handler.

The comment at `code_editor.py:736-739` justifies (2) with two claims, and the docstring at
`main_window.py:2444-2453` repeats them:

- **Claim A** — it is the only host in the menu-less `CodeEditorDialog`. **TRUE.**
  `CodeEditorDialog` (`code_editor.py:871-938`) is a bare `QDialog` holding one `CodeEditor` plus a
  `QDialogButtonBox`; it deliberately installs **no** `QShortcut` at all (the `Ctrl+S`/`Ctrl+W`
  carve-out was removed by the 2026-08-09 owner decision, `code_editor.py:902-912`). Removing the
  `keyPressEvent` branch naively kills bracket-select in that dialog — which is reachable from
  `MainWindow._open_code_editor_dialog` (`main_window.py:3183-3195`, the Editor "Edit code…"
  gesture) **and** from `ActivityPanel.open_viewer` (`activity_panel.py:255-279`).
- **Claim B** — *"QShortcut activation is not guaranteed under the offscreen platform."*
  **FALSE, and it is the actual root cause of the duplication.** Measured on this checkout
  (PySide6 6.11.1, `QT_QPA_PLATFORM=offscreen`, scratch tests, not committed):

  | driving idiom | menu `QAction` shortcut | dialog `QShortcut` | `WidgetWithChildrenShortcut` |
  |---|---|---|---|
  | `w.show()`; `QApplication.processEvents()`; `editor.setFocus()`; `qtbot.keyClick(editor, …)` | **fires** | **fires** | **fires** |
  | `QTest.keyClick(top.windowHandle(), …)` after `show()` | **fires** | **fires** | **fires** |
  | widget never `show()`n (no `windowHandle()`) | does not fire | does not fire | does not fire |

  The real rule is not "offscreen breaks shortcuts". It is that `QTest`/`qtbot` key delivery only
  reaches Qt's shortcut map when the widget's **top level has been created** (i.e. `show()` was
  called, so `windowHandle()` exists); otherwise the event is posted straight at the widget and the
  shortcut map is bypassed. Every "unreliable offscreen" comment in the repo traces to tests that
  build a bare widget without `show()`. Prototype proof that the proposed fix works offscreen: a
  `QShortcut(QKeySequence("Ctrl+Shift+B"), dialog)` added to a real `CodeEditorDialog` and driven by
  `qtbot.keyClick(dlg._editor, …)` after `show()` selects the bracket span correctly.

**Two consequences worth recording, because they invalidate existing evidence:**

- `tests/ui/test_select_menu.py::test_ctrl_shift_b_on_a_focused_code_editor_is_handled_once`
  (lines 488-524) claims to prove *"the menu action WINS; Qt's shortcut map consumes the key before
  it reaches the focused widget"* by counting calls. It does `window.show()` + `setFocus()`, so the
  `QAction` genuinely does fire and the count of 1 is real — but the test cannot distinguish
  *which* of the two handlers produced the single call, because it counts
  `tab.editor.select_enclosing_brackets` which **both** paths land on. The "measured" claim in the
  spec rests on a test that measures the total, not the winner.
- `Ctrl+Shift+A` (`Select Parent Block`, `main_window.py:2419-2421`, `QAction`-only) **works today**
  and its coverage is sound:
  `tests/ui/test_select_menu.py::test_the_ctrl_shift_a_chord_itself_is_live_on_xml_and_dead_on_a_php_tab`
  (lines 390-432) uses exactly the `show()` + `processEvents()` + `setFocus()` idiom the table above
  shows does reach the shortcut map, and asserts the action fired. It also correctly asserts the
  chord goes dead when the action is hidden — matching the measured "hidden action does not fire"
  result. No related breakage there. (Verified green individually on this checkout; note the working
  tree is mid-merge — `tests/ui/test_select_menu.py` and `pgtp_editor/ui/main_window.py` are `UU` in
  `git status` — and the *whole file* run currently fails with unrelated cross-test contamination.
  Re-baseline after the merge resolves; do not attribute that to this bug.)

### Proposed fix

Three edits, all small; the whole risk is in step 2.

1. **`pgtp_editor/ui/code_editor.py` — delete the `Ctrl+Shift+B` branch** at lines 740-746 of
   `CodeEditor.keyPressEvent`, and the comment at 736-739 with it. Do **not** touch the
   `Ctrl+Alt+E` / `Ctrl+Alt+C` branch at 780-788 (see **Scope**, below — that is a separate,
   undecided question). `select_enclosing_brackets` itself (`code_editor.py:413`) stays exactly as
   it is; it becomes purely a slot.

2. **`pgtp_editor/ui/code_editor.py` — give `CodeEditorDialog` its own `QShortcut`.** In
   `CodeEditorDialog.__init__`, after `self._editor` is created (`code_editor.py:889`), add roughly:

   ```python
   self._select_enclosing_shortcut = QShortcut(QKeySequence("Ctrl+Shift+B"), self)
   self._select_enclosing_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
   self._select_enclosing_shortcut.activated.connect(self._editor.select_enclosing_brackets)
   ```

   Gotchas:
   - `QShortcut` and `QKeySequence` are already imported in this module (`code_editor.py:46`); `Qt`
     is too. No new imports needed.
   - **Keep the reference on `self`.** A `QShortcut` whose Python reference is dropped is garbage
     collected and stops working — the same reason `find_replace_bar.install_focus_shortcuts`
     (`find_replace_bar.py:248-256`) returns its two shortcuts for the caller to retain. This is the
     single easiest thing to get wrong here.
   - `WindowShortcut` (the default) is correct and sufficient — the dialog is the window. Do not use
     `ApplicationShortcut` (it would fight the `MainWindow` action).
   - Put it **next to** the existing `Ctrl+S`/`Ctrl+W` comment block (lines 902-912) so the "what
     keys does this dialog own" story stays in one place, and replace that block's implicit "this
     dialog owns no shortcuts" reading.

3. **`pgtp_editor/ui/main_window.py` — rewrite the `_select_enclosing_block` docstring**
   (lines 2444-2453). The whole "**The duplicate Ctrl+Shift+B handler, resolved (FQ-015 trap)**"
   paragraph becomes wrong: there is no duplicate, the action is the sole host on every tab, and the
   `CodeEditorDialog` hosts its own `QShortcut`. State the measured fact that replaces the retired
   claim (shortcuts DO activate offscreen; what breaks is key delivery to a never-shown widget), so
   the false premise is not re-derived by the next reader. The capability-dispatch paragraph
   (2429-2443) is unaffected and stays.

**Do NOT** add a `Ctrl+Shift+B` row to `shortcut_registry.RESERVED_SEQUENCES`. It is a menu command
and must stay rebindable — that is the point of the ruling. (`Ctrl+Shift+B` is correctly absent from
that dict today; `shortcut_registry.py:204-260`.)

**Known limitation, deliberate, please state it in the code comment rather than fixing it silently:**
the dialog's `QShortcut` is a literal `"Ctrl+Shift+B"` and does **not** follow a user rebinding of
`Select ▸ Select Enclosing Block` (`MainWindow._apply_shortcut_bindings`, `main_window.py:3103-3131`,
only walks `self._toolbar_ui.menu_commands` `QAction`s). Making it follow would mean passing the
resolved sequence into the `CodeEditorDialog` constructor at both construction sites
(`main_window.py:3195` and `activity_panel.py:266`) — the latter has no `MainWindow` to ask, so it
would need a default. That is a real improvement but a **larger** change than the ruling asks for;
if the implementer does not do it, the manual caveat shrinks rather than disappears (see below).

### Scope beyond `Ctrl+Shift+B` — REPORTED, NOT DECIDED

The same false premise is load-bearing for a family, all citing "offscreen" verbatim:

| chord | where handled | has a menu entry? |
|---|---|---|
| `Ctrl+Alt+E`, `Ctrl+Alt+C` | `CodeEditor.keyPressEvent` (`code_editor.py:773-788`) | no |
| `Ctrl+Alt+F` | `DdlObjectEditorPanel`: a real `QShortcut` (`ddl_object_editor.py:781-789`) **plus** a redundant `eventFilter` branch (`ddl_object_editor.py:887-896`) | no |
| `Ctrl+Space` | `DdlObjectEditorPanel.eventFilter` (`ddl_object_editor.py:897-899`) | no |
| `Ctrl+Alt+J`, `Ctrl+Alt+F`, `Ctrl+Space`, `Ctrl+Shift+Space` | `SqlConsolePanel`: already `QShortcut`s (`sql_console_panel.py:507-533`) | no |

Cost if the owner extends the ruling: **small and mechanical** — roughly delete two branches in
`code_editor.py` and add two `WidgetWithChildrenShortcut` `QShortcut`s to whatever hosts the editor,
plus delete the two redundant `ddl_object_editor.eventFilter` branches (that panel already carries
the working `QShortcut`, so those two branches are pure dead weight and are the cheapest, lowest-risk
part of the family). Measured: `WidgetWithChildrenShortcut` fires correctly offscreen.

But **correctness is a real question, not just cost**: unlike `Ctrl+Shift+B`, none of these has a
menu entry, so none of them is "handled twice" — a gesture that belongs to the editor widget and to
no command may legitimately live in the widget's own key handling, which is exactly the argument
`shortcut_registry.RESERVED_SEQUENCES` already codifies for them (`Ctrl+Alt+F` at
`shortcut_registry.py:233-238`, the FQ-030 four at 239-249: *"a menu command retargeted onto one of
these keys would fight a widget that already answers to it"*). Those rows stay valid either way; if
the family converts to `QShortcut`s the rows' **reason text** needs a light edit (they would become
widget-scoped `QShortcut`s, still not menu-walk-enumerable). **Leave this family alone in this fix
unless the owner rules it in.**

### Test impact

Existing coverage, all of it to be extended rather than duplicated:

- `tests/ui/test_code_editor.py:171-180`
  (`test_ctrl_shift_b_selects_bracket_span_caret_at_start`) — **will break.** It builds a bare
  `CodeEditor("js")` with **no `show()` and no host**, so after step 1 there is nothing to answer the
  chord. Re-point it at a `CodeEditorDialog` (`dlg.show()`, `processEvents()`,
  `dlg._editor.setFocus()`, then `qtbot.keyClick(dlg._editor, …)`) — measured to pass. Keep a
  separate direct-call test of `select_enclosing_brackets` for the pure span logic.
- `tests/ui/test_select_menu.py:527-545`
  (`test_the_editor_side_ctrl_shift_b_handler_is_retained_for_menuless_hosts`) — **delete or invert.**
  Its whole subject (the retained widget handler) is gone. Replace with
  *"the `CodeEditorDialog` answers `Ctrl+Shift+B` through its own `QShortcut`"* driven by a real key
  press on a shown dialog.
- `tests/ui/test_select_menu.py:488-524`
  (`test_ctrl_shift_b_on_a_focused_code_editor_is_handled_once`) — **keep, but rewrite the docstring
  and strengthen it.** It should now prove the `QAction` is the *only* host: connect a counter to
  `window._select_enclosing_action.triggered` **as well as** wrapping
  `tab.editor.select_enclosing_brackets`, and assert both are 1 — that distinguishes the winner,
  which the current version cannot.
- `tests/ui/test_select_menu.py:390-432` (`Ctrl+Shift+A`) — no change; it is the model idiom.

New cases the fix needs:

1. `CodeEditorDialog` answers `Ctrl+Shift+B` by real key press after `show()` (the Claim-A regression
   guard — the one thing a naive removal silently kills).
2. The dialog's shortcut object is retained on the dialog (e.g. `hasattr(dlg, "_select_enclosing_shortcut")`
   / non-`None`), guarding the GC failure mode.
3. A negative: a bare `CodeEditor` with no dialog and no window action no longer answers the chord —
   pinning that the widget branch is really gone and cannot silently come back.
4. Optionally, in `tests/ui/test_customize_shortcuts_dialog.py` or `tests/ui/test_shortcut_registry.py`:
   assert `Ctrl+Shift+B` is **not** reserved and remains an assignable target, i.e. the chord is now
   genuinely rebindable on the menu command.

Note for whoever writes these: prefer the `show()` + `QApplication.processEvents()` + `setFocus()`
idiom over `qtbot.waitExposed(...)` called without `with` — the latter does not actually wait, and
was itself a source of the "shortcuts don't work offscreen" folklore.

### Manual impact (flag for `manual-maintainer`, do not edit `manual.md` here)

Two passages state the dual hosting as deliberate and become **wrong**:

- `pgtp_editor/resources/manual.md:3705-3717` — the blockquote *"One caveat: Ctrl+Shift+B is handled
  in two places"*, which tells the user that rebinding **Select ▸ Select Enclosing Block** does not
  change the editors' behaviour. After the fix, rebinding **does** move the chord everywhere the
  menu command acts. If the dialog keeps a literal `Ctrl+Shift+B` (see the known limitation above),
  the caveat **shrinks to the Edit code… dialog only** rather than disappearing.
- `pgtp_editor/resources/manual.md:957-961` — the Edit code… dialog bullet, which says the key
  *"cannot be changed by rebinding"*; and the shortcut-table row at `manual.md:3539`
  (*"Ctrl+Shift+B | Code Editor dialog | Bracket-select (the dialog has no menu bar)"*), whose
  parenthetical reason changes from "handled by the widget" to "hosted by the dialog's own shortcut".
- `manual.md:3728-3729`'s "keys with no menu entry" table rows are about the `Ctrl+Alt+*` family and
  are **unaffected** unless the owner extends the scope.

**Spec impact:** **Diverges from `CONSOLIDATED_SPEC.md` §8 — flag for `spec-maintainer` after the fix
lands.** The current behaviour *was* an intentional, recorded decision: the blockquote at
CONSOLIDATED_SPEC.md ~lines 2415-2421, **"The duplicate Ctrl+Shift+B handler: measured, then KEPT"**
(*"it remains the reliable path under the offscreen test platform where QShortcut activation is not
guaranteed"*), which explicitly closed a §29 open question. That blockquote must be rewritten, not
merely deleted, and the retired premise named so it is not re-derived. Echo sites to sweep: the
FQ-015 fold-in paragraph in the §28 header narrative (~line 350, *"`CodeEditor.keyPressEvent`'s
duplicate `Ctrl+Shift+B` is **kept** (measured: the QAction wins where it exists; the handler is the
only host in the menu-less `CodeEditorDialog`)"*), §27's `Ctrl+Shift+B` row (~line 2364), the §21
PHP-tab reuse table row (~line 6163, *"bracket-select (Ctrl+Shift+B) | `CodeEditor.keyPressEvent`"*),
~line 2733, and ~line 6183. A Supersession Ledger row is warranted: the 2026-08-07 FQ-015 decision is
being reversed by owner ruling on 2026-08-10, on the grounds that its measurement premise was wrong.
`bug-triager` does not edit the spec.

---

## BUG-047: the Activity Log still journals `Apply to Sandbox` / `Apply to Target` — two dead names FQ-026 renamed everywhere else, so the user's own history uses a vocabulary the app no longer speaks
**Status:** OPEN
**Reported:** 2026-08-10
**Report (verbatim):** "`pgtp_editor/db/activity_log.py:140-142` still emits the verbs `"Apply to Sandbox"` and `"Apply to Target"` into the Activity Log, and they are live — reportedly reached from `pgtp_editor/ui/main_window.py:6139`, `:6151`, `:6171` and `:6359`. FQ-026 was a deduplication of vocabulary, and it states its own invariant in code at `pgtp_editor/ui/ddl_object_editor.py:116-118`: *"one name per operation, used identically across the menu label, the confirmation-dialog title, the Audit `[Check]` line, the status bar and the manual"*. If the Activity Log prints a name that no menu, dialog or manual page uses, the feature has not achieved the thing it exists to achieve — a user reading their own history sees a verb they cannot find anywhere in the app."

**Verdict: CONFIRMED — this is a real defect, not a cosmetic leftover.** Verified independently
against the working tree (line numbers below are current; the reporter's were a few lines off because
`main_window.py` has moved under concurrent edits — locate by *function name*, not by line).

**Root cause**

`pgtp_editor/db/activity_log.py:140-144` defines the two verb constants as **its own string literals**:

```python
VERB_APPLY_SANDBOX = "Apply to Sandbox"
VERB_APPLY_TARGET = "Apply to Target"
DB_VERBS = (VERB_RAN, VERB_LINTED, VERB_APPLY_SANDBOX, VERB_APPLY_TARGET)
```

These are exactly two of the eight pre-FQ-026 names the spec's §28 FQ-026 section lists under
*"Was, before FQ-026"*. FQ-026 renamed every other surface and **missed this one**, because the
Activity Log is a surface `GESTURE_LABELS`' own docstring does not enumerate (it names menu label,
confirmation title, `[Check]` line, status bar, manual — not the journal). So this is a genuine gap in
FQ-026's sweep, not a decision.

**They are live, and reachable through ordinary use.** All four emitters are in `ui/main_window.py`
and all four are on the success/failure legs of *real* user gestures:

| Emitter | Enclosing method | Gesture that reaches it | Correct current name |
|---|---|---|---|
| `main_window.py:6159-6161` (`on_result`, committed leg) | `_apply_ddl_object_to_target` | `Deployment ▸ Apply to quality` → `_run_active_ddl_object_on_quality` (`:6261-6277`) → `panel.apply_to_target()` → the injected `apply_to_target` seam wired at `:5940` | **`Apply to quality`** (`GESTURE_LABELS[GESTURE_APPLY_TO_QUALITY]`) |
| `main_window.py:6171-6173` (`on_result`, did-not-commit leg) | same | same | same |
| `main_window.py:6190-6195` (`on_error`, seam blew up) | same | same | same |
| `main_window.py:6378-6383` (`on_done`) | `_apply_ddl_object_to_sandbox` | `Deployment ▸ Check and commit to sandbox` → `_run_active_ddl_object_on_sandbox` (`:6249-6259`) → `panel.apply_to_sandbox()` → the injected `apply_to_sandbox` seam wired at `:5935` | **`Check and commit to sandbox`** (`GESTURE_LABELS[GESTURE_CHECK_AND_COMMIT]`) |

Traced through the seam wiring rather than pattern-matched on the string: `_wire_ddl_object_apply_seams`
(`:5925-5949`) is the only place these two callables are installed, and after FQ-026 deleted the button
row and the context-menu apply entries, `panel.apply_to_sandbox()` / `panel.apply_to_target()` have
**exactly one caller each** (grep confirms: `main_window.py:6259` and `:6277`), both the `Deployment`
menu handlers. So the mapping above is one-to-one and unambiguous.

The rendered result the user sees is `render_row` (`activity_log.py:335-357`) joining the verb verbatim:
`2026-08-10 14:32 - Sandbox DB Apply to Sandbox CREATE OR REPLACE FU… success` — literally the example
at `pgtp_editor/resources/manual.md:498`.

**Why the fix cannot be a one-line constant edit (the important gotcha).** `db/activity_log.py` is
**deliberately Qt-free** (its module docstring: *"Qt-free on purpose … all of it is unit-testable
without a widget"*), and `GESTURE_LABELS` lives in `ui/ddl_object_editor.py`, which imports PySide6 at
module level. **`db/` must not import `ui/`.** Re-pointing the constants at the new strings *in
`activity_log.py`* would therefore re-create the exact defect FQ-026 exists to end: a second literal
copy of a gesture name, free to drift again. The names must be read from `GESTURE_LABELS` at the
**call site**, which is in `ui/`.

**Proposed fix**

1. **`pgtp_editor/ui/main_window.py` — pass the label, not the constant.** At the four emit sites in
   the table above, replace `VERB_APPLY_TARGET` with `GESTURE_LABELS[GESTURE_APPLY_TO_QUALITY]` and
   `VERB_APPLY_SANDBOX` with `GESTURE_LABELS[GESTURE_CHECK_AND_COMMIT]`. **No new imports are needed** —
   `main_window.py` already imports `GESTURE_LABELS`, `GESTURE_APPLY_TO_QUALITY` and
   `GESTURE_CHECK_AND_COMMIT` (lines 105-109). Drop the now-unused
   `VERB_APPLY_SANDBOX`/`VERB_APPLY_TARGET` from the `db.activity_log` import block (lines 70-71).
2. **`pgtp_editor/db/activity_log.py` — delete the two constants and leave a tombstone.** Remove
   `VERB_APPLY_SANDBOX` / `VERB_APPLY_TARGET` (`:139-142`) and reduce `DB_VERBS` to
   `(VERB_RAN, VERB_LINTED)` — `DB_VERBS` has **zero consumers anywhere in `pgtp_editor/` or `tests/`**
   (verified by grep; it is documentation, not a validation gate), so nothing gates on the shrunk tuple.
   Add a tombstone comment in the FQ-026 house style stating *why* the apply verbs are not defined here:
   they are gesture NAMES, owned by `ui/ddl_object_editor.py::GESTURE_LABELS`, and a copy in the
   Qt-free `db/` layer is precisely the drift FQ-026 forbids. Without that comment the next reader
   "helpfully" restores them.
   - Keep `VERB_RAN` / `VERB_LINTED` where they are. They are **not** gesture names — they are lowercase
     descriptions of what happened (`"ran"` for the Sandbox SQL Console at `:5194`, `"linted"` for both
     check gestures at `:6499-6503`) — so the invariant does not reach them and `db/` may own them.
3. **Do not touch `_activity_error_for_report`, `record_activity`, the entry shape, the JSONL store or
   `ui/activity_panel.py`.** The panel has no verb-value-specific logic — it only tests `entry.verb`
   for truthiness to pick the viewer language (`activity_panel.py:320`) and concatenates it at `:325`.
   Nothing switches on which verb it is.

**Secondary finding, deliberately OUT of scope — do not widen the fix without an owner ruling.** Both
check gestures journal the single verb `"linted"` (`main_window.py:6499-6503`, one call site shared by
`Check and rollback` and `Check Object in Sandbox`), so the journal cannot tell those two gestures
apart, and `"linted"`/`"ran"` are likewise names no menu uses. That is arguably the same complaint one
level down, but fixing it would *change what the journal records* (one verb becomes two), not merely
what it calls things. Recorded here so it is not mistaken for an oversight in this fix.

**Consequence for existing journals — analysed, with one owner call**

Facts established by reading the store, not assumed:

- **Nothing breaks.** `ActivityEntry.from_json_dict` (`activity_log.py:281-309`) validates `source`
  against `SOURCES` and `status` against `STATUSES`, but passes `verb` through `_text_or_none`, which
  accepts **any** non-empty string. A row holding `"Apply to Sandbox"` loads, renders and is previewed
  exactly as before after the rename. No migration is *required*.
- **Nothing filters on the verb set** — `DB_VERBS` is unreferenced, so shrinking it cannot orphan a row.
- Therefore the rename is **write-time by default**: rows written after the fix carry the new names,
  rows already in `.ddlproject/activity.jsonl` keep the old ones, and a long-lived project's journal
  holds **two vocabularies** with a visible changeover date.

Three ways to land it:

1. **Write-time rename, no migration (RECOMMENDED default).** The old rows keep saying what the app
   said at the time the user clicked. A journal is a record of the past; re-labelling a 2026-08-08 apply
   with a name that did not exist until 2026-08-10 is a small lie about history, and the changeover is
   self-explaining next to a timestamp.
2. **Display-time aliasing** — a `LEGACY_VERB_ALIASES` map applied in `render_row` (and in the panel's
   full-text viewer) so old rows *read* in today's vocabulary while the file is untouched. Costs a
   second mapping and a rule about which layer owns it; gains a history with one vocabulary.
3. **Rewrite the file** via the existing `save_activity` full-rewrite path. **Recommended against,
   explicitly.** The module's own contract is *"reads never raise, and loading never rewrites"* and
   *"writes are append-only on the happy path"*; `VERB_APPLY_TARGET` is described at its definition as
   *"the irreversible production write — the single most audit-worthy action"*. Rewriting the audit
   record of production writes to fix a label is the worst available trade, and a crash mid-rewrite
   costs the whole journal where an append costs one line.

**Option 1 vs option 2 is a judgement call about what a journal is for, not a technical one — that is
the owner's call, not mine.** The caller said they would file it; `bug-triager` does not write to
`docs/DECISION_QUEUE.md`. **If no ruling arrives, implement option 1** — it is the smaller change, it
is reversible (option 2 can be layered on later; the reverse is not true of option 3), and it needs no
new mapping to maintain.

**Test impact**

Existing coverage to EXTEND, never duplicate:

- **`tests/ui/test_ddl_object_editor_wiring.py`** — the two assertions that pin the defect and must
  flip: `:620` `assert entry.verb == "Apply to Sandbox"` → `"Check and commit to sandbox"`, and `:710`
  `assert entry.verb == "Apply to Target"` → `"Apply to quality"`. `:679`'s `assert entry.verb ==
  "linted"` is unaffected and should stay untouched (see the out-of-scope note).
- **`tests/ui/test_activity_log_wiring.py`** (`:46`) and **`tests/db/test_activity_log.py`** (`:26`,
  `:152`, `:345`, `:386`) and **`tests/ui/test_activity_panel.py`** (`:25-26`, `:52`, `:69`) import
  `VERB_APPLY_SANDBOX`/`VERB_APPLY_TARGET` **purely as fixture payloads** — none asserts on their
  values. If step 2 deletes the constants, these five files need their imports repointed (to a local
  literal or to `GESTURE_LABELS`); the assertions themselves do not change.

New case(s) the fix needs:

- **A regression guard for the invariant itself**, in `tests/ui/test_ddl_object_editor_wiring.py`
  beside the two flipped assertions: assert the journalled verb **equals
  `GESTURE_LABELS[GESTURE_CHECK_AND_COMMIT]` / `[GESTURE_APPLY_TO_QUALITY]`** rather than a re-typed
  literal, so a future rename of the label moves the test with it instead of leaving a stale string.
  This is the assertion shape that would have caught the bug.
- **A cheap structural guard in `tests/db/test_activity_log.py`**: no verb constant in
  `db/activity_log.py` names a DDL-object gesture (equivalently: `db/activity_log.py` defines no string
  appearing in `GESTURE_LABELS.values()`), mirroring
  `tests/ui/test_ddl_object_editor.py::test_the_picker_and_its_whole_api_are_deleted`, FQ-026's existing
  deletion guard.
- **A backward-compat read test** (option 1's honest consequence, stated as a test rather than left
  implicit): a seeded `activity.jsonl` line carrying the historical `"Apply to Target"` still loads via
  `load_activity` and still renders through `render_row`. This is what makes "no migration" a *decision*
  rather than an untested assumption.

**Spec impact**

**No spec change needed for the fix's substance — but one status correction is owed, so flag it for
`spec-maintainer` after the fix lands.**

- The current behaviour is **not** an intentional recorded decision. `CONSOLIDATED_SPEC.md` never
  specifies the Activity Log's verb vocabulary at all: FQ-019's fold-in pins the entry shape, source
  taxonomy, JSONL store and session-only rule (see the 2026-08-10 ledger row on the Activity Log's
  repositioning, ~line 9763) and the verb strings are a code-only detail. Nothing to override.
- The §28 **FQ-026 section (~lines 6471-6540)** claims every one of the eight old names is retired, and
  lists `Apply to Sandbox` / `Apply to Target` under *"Was, before FQ-026"*. That claim was **false at
  the time it was written** — the Activity Log kept both — and becomes true only when this lands. It
  should say so, and `GESTURE_LABELS`' surface enumeration (the invariant sentence at
  `ui/ddl_object_editor.py:116-118`, quoted verbatim into the spec as *"menu label, confirmation-dialog
  title, `[Check]` Audit line and status message*) should gain the **Activity Log verb** as a sixth
  surface, so the next gesture rename knows to sweep it.
- Echo sites carrying the retired names that a spec sweep should catch: ~line 386 (the §18.5 TOC
  blurb), ~line 3976-3977 (the project-tier table's *"Apply to Target"* / *"Apply to Sandbox"*), and
  ~line 5433 (*"(A) = §18.5's Apply to Sandbox; (C) = §18.5's Apply to Target"*). `bug-triager` does
  not edit the spec.

**Manual impact**

`pgtp_editor/resources/manual.md:498` deliberately still shows
`2026-08-10 14:32 - Sandbox DB Apply to Sandbox CREATE OR REPLACE FU… success`, because that is what
the app prints **today** — correct as written, wrong the moment this fix lands. **Dispatch
`manual-maintainer` with the fix** to update that sample row to `Check and commit to sandbox`, and (if
option 1 is chosen) to say in one sentence that rows written before this build carry the older names.
`bug-triager` does not edit the manual.

---

## BUG-048: `Ctrl+Z` on the read-only DDL Explorer tab silently reverts the **Raw XML project buffer** — the exact hazard §18.5 carve-out 1 pinned, at the sibling site nobody filtered
**Status:** OPEN
**Reported:** 2026-08-10
**Report (verbatim):** "`pgtp_editor/ui/ddl_editor_panel.py` installs no undo filter. The open question the manual agent could not settle without running code: does Qt's read-only `QPlainTextEdit` let the **window-level `Ctrl+Z` `QShortcut`** through? If it does, the consequence is bad: pressing `Ctrl+Z` in a read-only DDL Explorer tab would run **project snapshot undo on the Raw XML buffer** — a mutation of a different document than the one the user is looking at, triggered from a tab that is supposed to be read-only."

**Answer to the open question: YES, and it is confirmed end-to-end in the real `MainWindow`.**
A scratch pytest-qt run (not committed) built `MainWindow(generator_config_dir=tmp_path)`, `show()`ed
it, pushed two snapshots onto the Raw XML history, called `center_stage.show_ddl_explorer()`, focused
`panel.editor`, and delivered the key at the **window** level
(`QTest.keyClick(w.windowHandle(), Qt.Key.Key_Z, ControlModifier)` — which is what a real key press
does; `qtbot.keyClick(widget, …)` sends straight to the widget and bypasses `QShortcutMap` entirely,
so it can never observe this and must not be used to "prove" the opposite):

```
current tab: DDL Explorer (Quality)   focus: CodeEditor
RAW XML before: '<root><a/><b/></root>'
RAW XML after : '<root><a/></root>'      MUTATED: True
```

An isolated probe pins the Qt rule behind it (window-level delivery, `show()`n window, offscreen):

| focused widget | window `Ctrl+Z` `QShortcut` fires? |
| --- | --- |
| `QLabel` (control) | **yes** |
| `CodeEditor`, editable | no — the editor's native undo takes it |
| `CodeEditor`, `setReadOnly(True)` | **yes** |
| `XmlEditor`, editable | no — `keyPressEvent` emits `undo_requested` |
| `XmlEditor`, `setReadOnly(True)` | **yes** — `keyPressEvent` is never even reached |

**Root cause:** A read-only `QPlainTextEdit` does **not** accept the `ShortcutOverride` event for
`QKeySequence.StandardKey.Undo`/`Redo` (it has no undo to offer), so Qt falls through to the
window-scoped `QShortcut(QKeySequence("Ctrl+Z"), self)` created at `pgtp_editor/ui/main_window.py:1138`
and wired to `MainWindow._undo` (`main_window.py:1907`). `_undo` is **unscoped**: it calls
`self._history.undo()` and `_apply_history_text` (`main_window.py:1899`), which does
`self.center_stage.xml_editor.setPlainText(text)` — a `QTextCursor`-level write that
`setReadOnly(True)` does not stop — with no check of which tab is current and no check of whether the
Raw XML editor is read-only. `pgtp_editor/ui/ddl_editor_panel.py:55-113` (`EditorPanel.__init__`)
sets `self.editor.setReadOnly(True)` at line 88 and *does* `installEventFilter(self)` at line 97, but
its `eventFilter` (`ddl_editor_panel.py:144-149`) handles **only** `QEvent.Type.ContextMenu` — the
undo chords are not claimed.

`DdlObjectEditorPanel` has exactly this filter and this is not a coincidence:
`pgtp_editor/ui/ddl_object_editor.py:870-886` accepts `ShortcutOverride` for `Ctrl+Z`/`Ctrl+Y` and
routes `KeyPress` to `editor.undo()`/`redo()`, under the comment *"no double-undo, no leak into the
Raw XML buffer"*. `CONSOLIDATED_SPEC.md` §18.5 carve-out 1 (~line 6191-6208) and its 2026-08-02
Supersession Ledger row (~line 9694) state the hazard verbatim — *"Ctrl+Z would silently revert the
Raw XML project buffer while the user is looking at SQL"* — and pin a mandatory regression test for
it. **The carve-out was applied to the object *editor* tab only; the read-only DDL Explorer tab
(both roles, Quality and Sandbox) is the sibling that was never filtered.**

**Second affected site, same root cause, found while verifying:** Raw XML **while itself held
read-only** — Caption Mode or Compare/Merge Mode (`center_stage._set_raw_xml_read_only`,
`center_stage.py:532`). Probe with `RAW_XML_READ_ONLY_DIFF_MERGE_MODE` active and `xml_editor`
focused: `'<root><a/><b/></root>'` → `'<root><a/></root>'`, **MUTATED: True**. `XmlEditor`'s own
`keyPressEvent` re-emission (`xml_editor.py:1166-1168`) never runs, because the read-only editor does
not claim the `ShortcutOverride`. So `Ctrl+Z` walks straight through the read-only lock that FQ-021
installed **as a data-loss guard** for Compare/Merge and rewrites the buffer mid-merge. Same class:
`_undo` is unscoped. Any other focused read-only `QPlainTextEdit` is in the same boat —
`schema_compare_panel.py:90` (`_monospace`), `diff_merge_panel.py:122` (`event_diff_text`) — as is any
non-editor focus (project tree, findings dock), which is arguably wanted for the tree but is the same
unguarded path.

**Proposed fix:** Two layers. Do **both** — the second alone leaves the user with a dead key and no
reason, the first alone leaves the docks unguarded.

1. **Central scope guard (closes the whole class), `pgtp_editor/ui/main_window.py`.** Do **not**
   disable or delete the window `QShortcut` — the spec's ledger row explicitly forbids that shape
   (*"never by disabling the window shortcut"*), and it would break Ctrl+Z for the ordinary Raw XML
   case. Instead insert a scope check on the **shortcut path only**: connect `self._undo_shortcut` /
   `self._redo_shortcut` (lines 1138-1141) to new `_undo_from_shortcut` / `_redo_from_shortcut`
   wrappers that return early unless the Raw XML tab is the current tab **and**
   `center_stage.xml_editor.isReadOnly()` is False, delegating to `_undo`/`_redo` otherwise.
   **Gotcha — leave `_undo`/`_redo` themselves unguarded**: the History menu's `Undo`/`Redo`
   `QAction`s (`main_window.py:2395-2401`) connect straight to them, and those are explicit,
   deliberate clicks; guarding the shared method would silently kill the menu entries too. If the
   implementer wants the menu to stay honest, grey them via `setEnabled` on tab change rather than
   making them no-op. There is already a `currentChanged` consumer on `center_stage` to hang that
   off; find it rather than adding a second connection.
2. **A stated reason at the DDL Explorer, `pgtp_editor/ui/ddl_editor_panel.py`.** Extend the existing
   `EditorPanel.eventFilter` (line 144) with an undo/redo branch **copied in shape from
   `ddl_object_editor.py:870-886`**: for `obj is self.editor` and `event.type()` in
   `(ShortcutOverride, KeyPress)`, match `Ctrl+Z`, `Ctrl+Y` **and `Ctrl+Shift+Z`** (see BUG-050) —
   on `ShortcutOverride` call `event.accept()` (this is the part that stops the window shortcut; it is
   easy to write only the `KeyPress` half and see no change), on `KeyPress` call
   `self.editor.report_refusal("this buffer is read only — there is nothing to undo here")`
   (`code_editor.py:596`, the FQ-023 "state the reason, never nothing" channel) — and `return True`.
   Note the existing `eventFilter` ends in `return super().eventFilter(obj, event)`; keep that as the
   fallthrough. `EditorPanel` is constructed twice (Quality + Sandbox roles) from one class, so one
   branch covers both.

Do not "fix" this by making the DDL Explorer editable, and do not route its Ctrl+Z into
`CodeEditor.undo()`: the buffer is synthesized by `build_ddl_text` and read-only by design (§18.1), so
a working undo stack there would be undoing text the user never typed.

**Test impact:**
- `tests/ui/test_history_wiring.py` — owns the snapshot-undo wiring (line 280+ already asserts
  `undo_requested`/`redo_requested` drive it). Extend, do not duplicate: add a case that `show()`s the
  window, makes the DDL Explorer current, focuses `panel.editor`, delivers Ctrl+Z at
  `window.windowHandle()`, and asserts the Raw XML text is **byte-identical** — the same assertion
  shape §18.5's pinned object-tab test uses. Add the twin for read-only Raw XML under
  `RAW_XML_READ_ONLY_DIFF_MERGE_MODE`.
- `tests/ui/test_ddl_editor_panel.py` — owns `EditorPanel`; add the refusal-message case (assert
  `report_refusal` was reached, patched, rather than driving a real tooltip).
- `tests/ui/test_ddl_object_editor.py` / `test_ddl_object_editor_wiring.py` already carry the
  `Key_Z` object-tab carve-out tests — read them first for the established assertion idiom.
- **Test-writing gotcha, established today (BUG-046, re-confirmed here):** `QShortcut` **does**
  activate under `QT_QPA_PLATFORM=offscreen`. Two conditions are non-negotiable: the window must be
  `show()`n, and the key must be delivered to `window.windowHandle()`, not to the widget. Several
  comments in the repo (`code_editor.py:743-745,779-783`, `ddl_object_editor.py:898`) assert
  QShortcut is unreliable offscreen; that premise is false and it is what let this bug hide.

**Spec impact:** No design reversal — this is code failing an invariant the spec already states.
`CONSOLIDATED_SPEC.md` §18.5 carve-out 1 (~6191-6208), §27's `Ctrl+Z`/`Ctrl+Y` row (~9473) and the
2026-08-02 ledger row (~9694) all describe the carve-out as covering *the Edit XSD tab and the DDL
object editor tab* only. After the fix lands, dispatch `spec-maintainer` to widen the statement from
"two carved-out tabs" to the actual rule — **project-history Ctrl+Z acts only when Raw XML is the
current tab and is writable; everywhere else it is refused with a reason** — and to record that the
read-only Compare/Merge lock was previously bypassable by Ctrl+Z (FQ-021's guard, §27). `bug-triager`
does not edit the spec.

---

## BUG-049: `Ctrl+Z` in an FQ-006 draft fragment tab is a dead key — `XmlEditor` consumes it, emits `undo_requested` to nobody, and suppresses the native undo it replaced
**Status:** OPEN
**Reported:** 2026-08-10
**Report (verbatim):** "`XmlEditor.undo_requested` / `redo_requested` are reportedly connected only for `xml_editor` and `xsd_editor` (`pgtp_editor/ui/main_window.py:1131-1140`). A draft fragment tab's editor consumes `Ctrl+Z` / `Ctrl+Y` / `Ctrl+Shift+Z` and emits to nobody — so the keystroke is swallowed and nothing happens, with no indication why."

**Confirmed.** `XmlEditor` is instantiated at exactly three sites (`grep "XmlEditor("`):
`center_stage.py:248` (`xml_editor`), `center_stage.py:267` (`xsd_editor`) and
`center_stage.py:58` (`DraftFragmentTab.editor`). Only the first two have their signals connected —
`main_window.py:1148-1149` (Raw XML → `self._undo`/`self._redo`) and `main_window.py:1156-1157`
(XSD → `stage.xsd_editor.undo`/`.redo`). The draft's editor has no connection at all.

**Root cause:** `pgtp_editor/ui/xml_editor.py:1165-1174`. `keyPressEvent` matches `Ctrl+Z`
(→ `undo_requested.emit()`), and `Ctrl+Y` / `Ctrl+Shift+Z` (→ `redo_requested.emit()`), then calls
`event.accept()` and `return`s **without** `super().keyPressEvent(event)`. In
`DraftFragmentTab` (`pgtp_editor/ui/center_stage.py:41-84`) the signals have no receiver, so the
emit is a no-op — and because the key was consumed, `QPlainTextEdit`'s own undo stack, which would
otherwise have handled it perfectly well, never sees it either. The window-level `QShortcut` does not
fire, so nothing else happens either (verified by probe: editable `XmlEditor` focused, window-level
Ctrl+Z → `undo_requested` emitted, window shortcut **not** fired). Net user experience: **type into a
draft, press Ctrl+Z, nothing happens, forever — with no message.** The refactor that gave `XmlEditor`
a routed undo silently took the built-in one away from every future instance; the draft tab (FQ-006)
is the instance that arrived after and was never wired.

Note this is strictly a **dead key**, not the wrong-document mutation of BUG-048 — the draft tab's
editor is editable, so it claims the `ShortcutOverride` and the Raw XML buffer is never touched. It is
the milder half of the same design smell: `XmlEditor` unconditionally delegates undo to a host that
may not exist.

**Proposed fix:** Wire it in `DraftFragmentTab.__init__`
(`pgtp_editor/ui/center_stage.py:58-60`), immediately after `self.editor = XmlEditor()`:

```python
self.editor.undo_requested.connect(self.editor.undo)
self.editor.redo_requested.connect(self.editor.redo)
```

This is the **Edit XSD tab's precedent verbatim** (`main_window.py:1155-1157`, whose comment already
explains the shape: a tab with no snapshot history routes its re-emission straight back into the
editor). Put it in the tab, not in `MainWindow`: drafts are created dynamically and multiply
(`center_stage.open_draft_fragment_tab`, line 724, called from `coherence_controller.py:438`), so
`MainWindow` has no single construction site to hook, and a self-contained tab cannot be forgotten by
the next caller.

**Gotchas.** (a) A draft has no snapshot history and explicitly no save path or dirty concept
(`DraftFragmentTab`'s docstring) — do **not** route it to `MainWindow._undo`; native per-keystroke
undo is the right and only semantics here. (b) Consider whether `XmlEditor` should fall back to
`super().keyPressEvent(event)` when the signal has no receivers, so the next unwired instance
degrades to native undo instead of to nothing; `Signal.receivers()`-style introspection is awkward in
PySide6, so the cheap durable alternative is a one-line class docstring note at
`xml_editor.py:433-434` stating that an `XmlEditor` host **must** connect both signals. Either is
acceptable; the connect above is the required part.

**Test impact:**
- `tests/ui/test_center_stage.py` — already covers `DraftFragmentTab` / `open_draft_fragment_tab`
  (grep `draft`). Extend it: open a draft, `insertPlainText` into `tab.editor`, drive Ctrl+Z through
  `keyPressEvent`, assert the text reverted. `tests/ui/test_create_from_table_wiring.py` covers the
  route that opens drafts and is the wrong place for this.
- `tests/ui/test_history_wiring.py` should keep asserting the Raw XML buffer is untouched by the
  draft's Ctrl+Z (the negative half), so this fix and BUG-048 cannot regress into each other.

**Spec impact:** `CONSOLIDATED_SPEC.md` §27's `Ctrl+Z`/`Ctrl+Y` row (~9473) enumerates the carve-outs
as *"the Edit XSD tab or a DDL object editor tab"* and says nothing about draft fragment tabs; the
FQ-006 draft-tab section describes the tab as *"a plain `XmlEditor` + `FindReplaceBar` (syntax
highlighting and find/replace for free)"*, which reads as a promise that the editor's own affordances
work. Nothing states the current behavior was intended, so this is a plain defect — but after the fix
dispatch `spec-maintainer` to add the draft tab to §27's carve-out list, so the enumeration matches
the three `XmlEditor` sites. `bug-triager` does not edit the spec.

---

## BUG-050: `Ctrl+Shift+Z` is missing from `RESERVED_SEQUENCES`, so Customize Shortcuts… will hand it to a menu command that then works only when no XML editor has focus
**Status:** OPEN
**Reported:** 2026-08-10
**Report (verbatim):** "`pgtp_editor/ui/xml_editor.py:1170-1171` makes `Ctrl+Shift+Z` a second redo in every XML editor and consumes it (`event.accept()`), but `shortcut_registry.RESERVED_SEQUENCES` (`shortcut_registry.py:204-260`) reserves only `Ctrl+Z` / `Ctrl+Y`. So Customize Shortcuts… would let a user assign a menu command to `Ctrl+Shift+Z`, and the two would then fight — with the editor's handler consuming the event."

**Confirmed, and the user-visible symptom is FOCUS-DEPENDENT, which is worse than a clean loss.**
`pgtp_editor/ui/xml_editor.py:1170-1174` accepts `Ctrl+Shift+Z` as redo and `event.accept()`s it;
`RESERVED_SEQUENCES` (`pgtp_editor/ui/shortcut_registry.py:204-260`) lists `Ctrl+Z` and `Ctrl+Y` with
the reason *"project history Undo/Redo — a window-scoped shortcut, not a menu action (§27)"* and
**does not list `Ctrl+Shift+Z`**. A scratch probe (window with a menu `QAction` on `Ctrl+Shift+Z`
plus an `XmlEditor`, `show()`n, key delivered at `windowHandle()`):

```
XmlEditor FOCUSED  -> menu: []            editor: ['redo_requested']
NON-EDITOR FOCUSED -> menu: ['menu-cmd']  editor: []
```

So the retargeted menu command **silently never fires while Raw XML, Edit XSD or a draft tab has
focus**, and fires normally the moment focus is anywhere else — no ambiguity warning, no status
message, nothing in the Customize dialog to hint at it. This is precisely the failure mode
`RESERVED_SEQUENCES` exists to prevent, and precisely why the registry's own header distinguishes
*"a key that may never be the TARGET of a rebinding, because something the dialog does not own already
answers to it"* — a widget `keyPressEvent` is the canonical case (the header says so, in the
`Ctrl+Alt+E`/`Ctrl+Alt+C` comment block at lines 236-241).

**Root cause:** an omission in a hand-transcribed table. `Ctrl+Shift+Z` was added to
`XmlEditor.keyPressEvent` as a second redo but never transcribed into §27 or into
`RESERVED_SEQUENCES`, so `assign_shortcut`'s refuse-a-non-menu-occupant rule has no row to refuse on.

**Proposed fix:** One registry row in `pgtp_editor/ui/shortcut_registry.py`, beside the existing
`Ctrl+Z`/`Ctrl+Y` pair (lines ~215-219), in the same voice:

```python
"Ctrl+Shift+Z": "project history Redo (the second chord) — consumed inside "
                "every XML editor's key handling, not a menu action (§27)",
```

That is the whole fix: `RESERVED_SEQUENCES` is already read by the conflict rule and rendered as a
greyed read-only row in the dialog (`ReservedBinding`, FQ-012 decision 1: *"the user gets to SEE that
the key exists and why it is locked"*), so no dialog change is needed. **Gotcha:** the reason string
is user-facing text in that greyed row, so write it as an explanation, not a code note; and put it
adjacent to `Ctrl+Z`/`Ctrl+Y` rather than at the end of the dict — the dict's grouping-by-rationale
is load-bearing for the reader.

**Secondary finding, judged in-scope but NOT a functional defect — the `Ctrl+Alt+F` reason string.**
Its reason reads *"Format Selection — a context-menu command, not a menu-bar action (§27)"*. Verified
against the code: `Ctrl+Alt+F` is additionally a real `QShortcut` in **two** panels
(`sql_console_panel.py:531`, `ddl_object_editor.py:786`) **and** an `eventFilter` branch
(`ddl_object_editor.py:887-895`). The row's **behaviour is correct** — the key is reserved, which is
the outcome that matters, and the row cannot be reached by the menu walk either way. Only the stated
*why* is incomplete, and it is shown to the user. Treat it as a copy fix riding along with the row
above, not as a separate bug: reword to something like *"Format Selection — a context-menu command
plus a `QShortcut` in the SQL Console and DDL object tabs; no menu-bar action to move (§27)"*.
Nothing else in `RESERVED_SEQUENCES` diverged on a re-check of the remaining rows against the code
(`Ctrl+S`/`Ctrl+Shift+S`, `Ctrl+F`/`Ctrl+R`, `Escape`, `F3`, `Ctrl+L`, `Ctrl+Alt+E`/`C`/`J`,
`Ctrl+Shift+Space`, `Ctrl+Return`, `Ctrl+Space`, `Ctrl+G`, `Ctrl+C`/`X`/`V`, `F1`) — the one real
gap is `Ctrl+Shift+Z`.

**Test impact:** `tests/ui/test_shortcut_registry.py` is the owner (it already iterates
`RESERVED_SEQUENCES` at lines 130-146 and asserts every reason is non-empty). Extend it: assert
`"Ctrl+Shift+Z" in RESERVED_SEQUENCES`, and add an `assign_shortcut` case proving the chord is
**refused, not stolen** (the non-menu-occupant branch), mirroring the existing `Ctrl+Z` case rather
than writing a new idiom. `tests/ui/test_customize_shortcuts_dialog.py` should get the greyed-row
assertion if it already has one for another reserved key. No new Qt-driven key test is needed — the
registry is Qt-free and the fix is data.

**Spec impact:** **Diverges from `CONSOLIDATED_SPEC.md` §27.** §27's consolidated shortcut table and
its 2026-08-09 FQ-012 ledger row (~9755) both enumerate what is unrebindable and list only
`Ctrl+Z`/`Ctrl+Y` for the history pair; `Ctrl+Shift+Z` appears nowhere in the spec (grep confirms:
only `Ctrl+Z`/`Ctrl+Y` hits). The registry's header says it is *"Transcribed from §27"*, so the code
row and the spec row must land together. After the fix, dispatch `spec-maintainer` to add
`Ctrl+Shift+Z` to §27's table as a second redo chord consumed inside `XmlEditor`, to the FQ-012
ledger row's unrebindable list, and to correct §27's `Ctrl+Alt+F` characterization to mention the two
`QShortcut` hosts. `bug-triager` does not edit the spec.

---
