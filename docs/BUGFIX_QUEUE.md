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

**Status:** OPEN
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

**Status:** OPEN
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

**Status:** OPEN
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
