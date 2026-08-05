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
**Status:** RESOLVED (2508d2a)
**Reported:** 2026-08-05
**Report (verbatim):** "at opening the project the pgtp should automatically open"

*(Reconstructed from a background-triage report that was lost when a §18.3 merge from another worktree overwrote the working-tree queue file before this entry was committed. Line numbers are pre-merge and may have shifted — re-grep the named symbols.)*

**Root cause:** `MainWindow._open_ddl_project` (`pgtp_editor/ui/main_window.py`, ~2570-2580) sets the project active and reports drift but never calls the existing loader `open_project_file` (`main_window.py`, ~1356-1415). The project's working-copy path is already recorded in `settings.pgtp.working_copy_path` (`PgtpLink` in `pgtp_editor/db/ddl_project.py`, ~66-77), so the fix reuses the existing load path rather than reinventing loading.

**Proposed fix:** After a project folder is opened/validated, locate the linked `.pgtp` via `settings.pgtp.working_copy_path` and call the existing `open_project_file` automatically so the editor is immediately populated. Handle the scope cases explicitly: **zero** `.pgtp` linked → do nothing (no error); **one** → auto-open + keep the project link; **multiple** candidates → report via the Audit panel rather than guessing. Watch the `on_ready` double-load gotcha (don't trigger a second load through the ready callback).

**Test impact:** `tests/ui/test_ddl_project_wiring.py` and `tests/ui/test_open_project.py` — add a case asserting that opening a project folder with a linked working copy populates the editor.

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
**Status:** OPEN
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
