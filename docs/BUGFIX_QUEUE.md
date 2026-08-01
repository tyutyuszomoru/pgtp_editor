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
**Status:** OPEN
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
**Status:** OPEN
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
**Status:** OPEN
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
