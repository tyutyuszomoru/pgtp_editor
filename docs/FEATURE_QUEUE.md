# Feature Queue

Working queue of triaged feature ideas for PGTP Editor, filled by the `feature-triage` agent
(`.claude/agents/feature-triage.md`) so idea capture can happen while other implementation work is in
progress in the main session. Each entry is a challenged, well-placed proposal — `feature-triage` never
folds it into the spec or implements it itself. Entries are appended at the end as ideas come in.

When picking one up: dispatch `spec-maintainer` (JOB 1) to fold it into `CONSOLIDATED_SPEC.md`,
implement it, run the feature-tester / manual-maintainer policy from CLAUDE.md as usual, then flip the
entry's `Status` line to `PROCESSED (<commit or spec §>)` in place — do not delete entries; they're the
record of what was proposed and why it was shaped the way it was.

---

## FQ-001: Test button for both connections in Project Settings' Connections tab
**Status:** PROCESSED (§18.2)
**Requested:** 2026-08-05
**Idea (verbatim/summarized):** "in Project settings Connection tab I want a Test button for both settable connections"

**Problem:** `ProjectSettingsDialog`'s "Connections" tab (`pgtp_editor/ui/project_settings_dialog.py`,
tab built at lines 150–154) shows two `QGroupBox` sections — "Target connection" (line 76) and "Sandbox
connection" (line 85), each with host/port/database/user/password fields backed by `ConnectionParams`
(`pgtp_editor/db/config.py:36-42`) — but neither has a Test button. A user editing an existing project's
saved connection details (e.g. after a DB move or credential rotation) has no way to verify the new
values work without leaving the dialog, saving blind, and finding out the hard way on next use.

**Proposed approach:** Add one "Test" button + inline status label per connection group, reusing the
two test flavors that already exist elsewhere rather than inventing a third:
- **Target connection Test** → generic connectivity check, same as `ConnectionSetupDialog.test()`
  (`pgtp_editor/ui/connection_setup_dialog.py:115-140`): runs `db.introspect.test_connection()` off the
  GUI thread, colored status label ("Testing connection…" → green/red result message).
- **Sandbox connection Test** → superuser-specific probe, same as `NewProjectDialog.test_sandbox()`
  (`pgtp_editor/ui/new_project_dialog.py:228-278`): runs `db.sandbox.probe()` off the GUI thread and
  reports via `_apply_sandbox_probe_result`-equivalent logic — not just "can connect," but is-superuser
  plus `pg_dump`/`pg_restore` availability, since sandbox provisioning needs `CREATE EXTENSION` (§18.5
  D2). A plain connectivity check would give a false green light for a connection that connects but
  can't actually provision a sandbox.
- Both buttons test the values **currently typed in the dialog's fields** (not the last-saved
  `ProjectSettings.target`/`.sandbox`), matching how both source dialogs test before commit — building
  a fresh `ConnectionParams`/params object from the live field widgets the same way `params()` /
  `sandbox_params()` do in the existing dialogs.
- Reuse the existing async-off-GUI-thread + colored-status-label pattern (`_run_async`, "Testing…" /
  green "Connected…" / red error text) verbatim rather than a new modal or toast, for UI consistency
  with the two existing Test buttons.

**Alternatives considered:** A single shared "generic connectivity" test for both connections was
considered and rejected (confirmed with the requester 2026-08-05) — it would silently pass a
non-superuser sandbox connection that looks fine but fails later at actual sandbox provisioning time,
reintroducing exactly the failure mode the New Project dialog's superuser probe exists to catch.

**Suggested placement:** EXTEND §18.2 ("Projects, checkout & state markers") in
`CONSOLIDATED_SPEC.md`, which already documents the Project Settings dialog's four-tab layout and the
Connections tab's Target/Sandbox groups (spec lines ~2118–2133) but has no Test-button behavior for
that dialog — only for `NewProjectDialog` (§18.2, referenced near lines 1880-1881, 4328, 4466) and the
standalone `ConnectionSetupDialog`. No new section warranted; this is a direct capability gap in an
already-specified dialog, closed by reusing both existing tester functions verbatim.

**Open questions:** none.

---

## FQ-002: Create new trigger / function / procedure from the DDL Explorer
**Status:** PROCESSED (§18.1 / §18.5 D1; 9f7c7c2, 11d230d, 849d4ae, 484ef64)
**Requested:** 2026-08-05
**Idea (verbatim/summarized):** "from ddl explorer I would like to be able to add a new trigger (on
right click on a table), or add a new procedure/function. For triggers I'd like a dialogue: name,
before/after, insert/update/delete, for each row / for each statement (confirmed with requester —
Postgres has no transaction-level trigger), trigger function chooser (existing trigger functions only —
confirmed with requester; inline create-new-function is out of scope for v1). For function/procedure
creation the dialogue should be function/procedure, returning datatype. In both cases it should open in
a new tab with the skeleton already pasted into the editor window."

**Problem:** The DDL Explorer (`BrowserPanel`, `pgtp_editor/ui/ddl_buffer_panel.py:101-312`) only
supports browsing and editing objects that already exist in the connected database — right-click on a
routine/trigger row offers "Edit…" and "Check Out for Versioning" (`_on_context_menu`, lines 292-311),
and table nodes have **no context menu at all** today, by explicit design (§18.1 spec, line ~1912:
"click-only, no context menu... since a whole table has no single `DdlObjectSpan`/source text to hand
those entry points"). There is no way to originate a brand-new trigger, function, or procedure from the
Explorer — the user has to write `CREATE TRIGGER`/`CREATE FUNCTION` by hand elsewhere and there is no
skeleton/template helper anywhere in the codebase for any of these object kinds.

**Proposed approach:**
- **Add Trigger** — new right-click entry on a table node (this is new context-menu wiring for table
  nodes specifically for *creation*, not existing-object editing; the "no context menu" invariant at
  spec line ~1912 was written for the edit/checkout case, which needs a source span a not-yet-created
  object doesn't have — a "Create" action doesn't run into that limitation and needs its own menu
  entry). Opens a dialog with: name; timing (BEFORE / AFTER / INSTEAD OF); events (INSERT / UPDATE /
  DELETE, multi-select — Postgres allows combining these with OR); level (FOR EACH ROW / FOR EACH
  STATEMENT — corrected from the original "for each transaction," which isn't a Postgres trigger level);
  and a trigger-function chooser listing only existing functions whose return type is `trigger` in the
  connected DB (introspected the same way `pgtp_editor/db/introspect.py` already reads routines) — no
  inline "create new function" shortcut in this dialog for v1.
- **Add Function/Procedure** — reachable from **both** a right-click on the "Functions & Procedures"
  tree branch (`_build_routines_branch`, `ddl_buffer_panel.py:211-261`) **and** a menu action: a single
  **"New Function/Procedure…" entry in the Database menu** (`main_window.py`, menu built ~line 2611),
  placed after the existing "DDL Explorer" action with a separator — that menu already owns Connection
  Setup, the XML↔DB check actions, and DDL Explorer itself, so it's the existing home for DDL-Explorer-
  adjacent actions; one action opens the one dialog (kind is a field inside it, not two separate menu
  entries), since unlike a trigger it isn't scoped to a specific table. Dialog: name; kind (Function / Procedure); return
  datatype — **function-only**, since `CREATE PROCEDURE` has no `RETURNS` clause in Postgres at all
  (procedures use OUT parameters or return nothing) — the dialog must hide/disable the return-datatype
  field when Procedure is selected, not just leave it optional.
- **Both flows open a new tab via the existing `CenterStage.open_ddl_object_tab`**
  (`pgtp_editor/ui/center_stage.py:202-222`), reusing `DdlObjectEditorPanel`
  (`pgtp_editor/ui/ddl_object_editor.py:135-548`) — already SQL-editable with §18.6 schema-aware Ctrl+Space
  completion and already modeling `kind ∈ {"function","procedure","trigger"}` via `DdlObjectRef`
  (lines 61-133), so the tab class itself needs no new capability, just a `DdlObjectRef` for an
  object that doesn't exist in the DB yet plus skeleton text instead of introspected source. The panel
  already has an "unattached trigger function" table-picker (lines 191, 479-490, 502-526) for the
  reverse case (trigger function with no linked trigger) — worth reusing that picker's UI pattern for
  the new trigger dialog's function chooser rather than building a new widget from scratch.
- **Skeleton generation is genuinely new code** — no `CREATE TRIGGER`/`CREATE FUNCTION`/`CREATE PROCEDURE`
  templating exists anywhere (`generation/` is PHP generation from `.pgtp`, unrelated). New skeleton text
  should default `LANGUAGE plpgsql` (no language picker in v1, matching this project's plpgsql-IDE focus)
  and paste a minimal valid stub (e.g. `CREATE OR REPLACE FUNCTION ... RETURNS trigger AS $$ BEGIN ... END;
  $$;` / `CREATE PROCEDURE ...($$ BEGIN ... END; $$)`) built from the dialog's fields.
- **Getting the new object into the deploy pipeline needs its own path — it is NOT automatic today**
  (resolved 2026-08-06, verified against code rather than left open). `db/migration_gen.py:105-117`
  already collects `schema_diff.py`'s `kind="added"` differences (`target_object is None`, line 217-218)
  and correctly emits a bare `CREATE` for routines and a `DROP TRIGGER IF EXISTS` + `CREATE` for triggers
  — **do not write new CREATE-statement-emission logic, that part already exists and already works.**
  But that "added" path only fires when comparing two already-introspected `DatabaseSchema` snapshots
  (the §18.5 sandbox-vs-production flow); the separate local-file-vs-DB deploy pipeline (§18.3/§18.4)
  tracks objects purely through `ProjectSettings.deployed` (`db/ddl_project.py:127-143`), which is only
  ever populated by checking out an object that already exists in the DB — "file absent → seed from the
  live introspected definition... that write **is** the checkout" (`CONSOLIDATED_SPEC.md:2256-2258`) —
  and `compute_drift_markers()` (`ddl_project.py:506-544`) iterates only over `settings.deployed.items()`.
  A hand-written new `ddl/*.sql` file with no prior checkout is invisible to that pipeline: it would
  parse fine (`parse_checked_out_header()`, `ddl_project.py:317-341`, recovers identity from the file's
  own header, not from the manifest) but never surface as a pending change. **Whoever implements this
  must add the newly-created object to `ProjectSettings.deployed`/the drift-tracking manifest at creation
  time** (as a "local exists, no last-deployed reference yet" entry) so the existing §18.3/§18.4 deploy UI
  picks it up through its normal drift/apply flow — not invent a second, parallel "new object" deploy
  path alongside the existing checkout-based one.

**Alternatives considered:** A single unified "Add DDL object" dialog covering all three kinds was
considered and rejected — trigger, function, and procedure have different required fields (a trigger
needs timing/events/level/table/function; a function needs a return type a procedure must not have),
and the existing `DdlObjectRef.kind` split already treats them as distinct — one dialog per kind is
more consistent with that model and avoids a field set that's mostly irrelevant no matter which kind is
picked.

**Suggested placement:** EXTEND §18.1 (DDL Explorer tree + context menus) and §18.5 (the
`DdlObjectEditorPanel` tab, "explicitly designed to host" trigger/function editing per existing code
comments) in `CONSOLIDATED_SPEC.md` — reusing the tree, the tab-opening path, and the editor panel
wholesale. This is NOT covered by any existing §18 subsection today (§18.1-§18.2 are browsing/checkout
of *existing* objects only; §18.3-§18.8 are deploy/apply/sandbox/completion/status, all post-creation).
Whoever folds this in should also explicitly amend the table-node "no context menu" statement at spec
line ~1912 to carve out the new "Add Trigger" creation entry, so the invariant and the shipped behavior
don't silently diverge.

**Open questions:** none — both resolved 2026-08-06 against actual code (see the deploy-pipeline and
menu-location details folded into "Proposed approach" above) before this entry was picked up.

---

## FQ-003: Unify DB Check (both directions) + Table References into one "Database/XML Coherence" view
**Status:** PROCESSED (113fbfa) — the merged Database/XML Coherence view shipped; this entry was never flipped at the time.
**Requested:** 2026-08-06
**Idea (verbatim/summarized):** "Unite the Database→XML check, XML→Database check, and Table References
panel into a single 'Database/XML Coherence' view. Our truth is always the db. The xml represents the
interface. So anything in the xml that's not in the db is an error (or renamed table, or something else
to address, otherwise the app won't work). Finding where that db table plays in the xml is important."
This idea has already been through a full brainstorming session (product-brainstorming skill +
spec-maintainer JOB2 placement gate + two rounds of code verification) and is fully converged; this entry
records the settled design, not an open elaboration.

**Problem:** Today there are **three separate left-dock surfaces** presenting overlapping information
about the same underlying question (does the XML interface match the live DB truth), all built on top of
the **same already-shared analyzer**: `pgtp_editor/analysis/reused_tables.py::collect_table_usages` (pure,
Qt-free) is called directly by both `pgtp_editor/db/compare.py::check_xml_against_db` and
`check_db_against_xml` (via `xml_table_invocations`/`xml_table_role_counts`, BUG-026), and consumed a
third time by `pgtp_editor/ui/table_references_panel.py::TableReferencesPanel`. Despite sharing one data
layer, the **presentation** is triplicated: two separate Database-menu items ("Check: XML → Database" /
"Check: Database → XML", `pgtp_editor/ui/main_window.py:2622-2625`) driving one `DbCheckPanel` class
(`pgtp_editor/ui/db_check_panel.py`) added to `left_tabs` as its own hidden tab
(`db_check_tab_index`, `main_window.py:275-277`), plus a wholly separate "Table references" hidden tab
(`table_refs_tab_index`, `main_window.py:307`) toggled from the View menu (§15,
`CONSOLIDATED_SPEC.md:1302-1304`). The user has to know which of three surfaces answers which question,
and the "direction" framing of the two DB-check menu items is itself an artifact of showing only one
side's state at a time rather than DB-state and XML-state together per table.

**Proposed approach:** Two top-level branches sharing one data source
(`analysis/reused_tables.py` + `db/compare.py`'s DB-augmented layer), replacing all three current surfaces
(2 DB-Check-direction menu items/tab + 1 Table References menu item/tab) with one panel/tab and one
Database-menu toggle:

1. **"Tables and Views" branch** — rooted in the live DB relation list (tables **and** views, identical
   treatment — `db/introspect.py` already fetches both the same way, `relkind IN ('r','p','v','m')` per
   §17, and neither `compare.py` nor `reused_tables.py` apply kind-based filtering, so no new
   special-casing is needed for views). Per table/view, two sub-sections:
   - **Database columns** — today's column-check list (DB type/nullable/PK/FK/etc., per §17's
     `ColumnCheck`). Calculated columns (`ColumnCheck.is_calculated`, `db/compare.py`, BUG-006) are shown
     but **excluded from mismatch flagging** — they are intentionally DB-less by design, not an error.
   - **References** — today's Table-References content for that table, badge-summarized using the
     **existing** `TableCheck.page_count`/`.detail_count`/`.lookup_count` rollup fields (§17, BUG-026;
     `db/compare.py` lines ~50-62) rather than computing new counts, expandable into the full breadcrumb
     list currently shown by `TableReferencesPanel`.
   - The **direction toggle** from today's two separate DB-check menu items is **eliminated**, not merged:
     once DB state and XML state are shown together per table, there is no remaining framing choice about
     which side is "ground truth for display" — the DB is always ground truth (per the requester's core
     framing) and the XML is always the thing being checked against it.

2. **"Pages" branch** — a **recursive tree mirroring the real XML structure**, not a fixed depth. Each
   Page node shows its own bound table (if any) and its own lookup columns (with a **"lookup with
   insert"** badge wherever `TableReference.ref_type == "lookup with insert"` applies — fired when a
   `<Lookup>` has a child `<OnTheFlyInsertPage>`, `reused_tables.py:73-80` — this distinction is shown
   today in the Table References breadcrumbs and must be preserved as a badge, not flattened into a
   generic "lookup" label), then nests child Details the same way: each Detail has its own bound table +
   its own lookup columns + further nested child Details, recursing to whatever depth the XML actually
   has. This is exactly the shape `visit_detail`'s existing recursion in `reused_tables.py:108-116`
   already walks (a Detail can contain child Details at unlimited depth) — the UI must mirror that
   recursion, not flatten it to an assumed "Page > Details > Detail > Lookups" 2-level shape.

3. **Mismatch toggle** (global, filters both branches down to only problem nodes) — settled semantics,
   confirmed directly with the requester:
   - **In the Pages branch:** a Page/Detail/Lookup node whose target table/view name does not exist in
     the live DB at all is flagged red **at that exact reference point** — this is where a "renamed
     table" error must surface, *not* as a synthetic phantom entry under "Tables and Views," which stays
     purely DB-sourced (a table that doesn't exist in the DB has no row to attach a phantom entry to in
     that branch).
   - **In the Tables-and-Views branch:** a real DB table/view with `page_count == detail_count ==
     lookup_count == 0` (referenced nowhere in the XML at all) **is** flagged by the toggle too —
     confirmed directly with the requester ("if neither Page, nor Detail nor Lookup is there, flag it.
     Probably needs attention."). This is the reverse-direction case and is explicitly wanted, not
     excluded, even though an unreferenced table is not itself a coherence *error* in the same sense as a
     dangling XML reference — the toggle is deliberately "things needing attention," not strictly
     "things that are broken."
   - Column-level mismatches (existing `ColumnCheck.ok == False` cases) also fold into the toggle,
     excluding `is_calculated` columns as above.
   - No mismatch-type enum exists anywhere today; mismatches are currently derived ad hoc from `ok`
     (bool) + `kind` (`None` = missing in DB) + role counts. The new toggle needs its own filter predicate
     spanning both branches per the rules above, since nothing pre-packaged does this today.

**Alternatives considered:**
- A fully separate "connection-optional" hybrid that kept Table References as an independent panel with
  just a cross-navigation link into DB Check was considered (this was the facilitating assistant's
  first-pass recommendation during brainstorming) and superseded once the requester clarified the core
  motivation is architectural — three near-duplicate presentations of what is fundamentally one
  DB-truth-vs-XML-interface question — not just a UI convenience link. The full merge was chosen instead.
- The §18.3 precedent of explicitly **rejecting** a unified Compare/Deploy screen
  (`CONSOLIDATED_SPEC.md:2512-2514`: "a single unified Compare/Deploy screen... would either overload the
  simple compare tool with project/git machinery it doesn't need, or dilute the deploy workflow's
  guardrails into a generic diff viewer") was raised as a caution during brainstorming but explicitly
  distinguished, not silently re-decided: that precedent turned on **risk asymmetry** (Compare is
  read-only, Deploy is destructive/write, and merging them would dilute Deploy's guardrails). DB Check
  and Table References are both **read-only diagnostic** surfaces with no write path — the risk asymmetry
  that drove §18.3's rejection does not exist here, so it does not block this merge. Recorded so whoever
  implements this does not have to re-litigate the §18.3 reasoning from scratch.

**Suggested placement:** EXTEND §17 (Database, `CONSOLIDATED_SPEC.md` lines ~1327-1454) as the primary
landing section — it already owns `db/compare.py`, `DbCheckPanel`, and the Database-menu check actions
that this design replaces. §15 (Search, Find All & Table References, lines ~1261-1306) should have its
"Table References tab" subsection **folded into §17** rather than kept as a cross-referenced sibling: the
settled design makes table-references a sub-branch (the "References" section under "Tables and Views,"
and the whole "Pages" branch) of one coherence view, not an independently toggleable panel — the View
menu's "Find table reference" checkable and the `table_refs_tab_index` hidden tab both go away as
standalone entry points once §17's Database menu toggle covers the merged view. Whoever picks this up
must reuse `analysis/reused_tables.py::collect_table_usages` wholesale (do not reimplement the
page/detail/lookup walk) and the existing `TableCheck`/`ColumnCheck` rollup fields (`page_count`/
`detail_count`/`lookup_count`/`is_calculated`) rather than introducing parallel counting logic.

**Open questions:** none — the design converged through direct requester decisions on both the Pages-vs-
Tables-and-Views mismatch semantics and the recursive (not fixed-depth) Pages tree shape; see "Proposed
approach" above for the exact resolutions. Implementation-level questions (exact tree-widget structure,
whether "Tables and Views" and "Pages" are two sub-tabs vs. two top-level tree roots in one widget, menu
action naming/shortcut) are left to whoever designs this into §17's spec text and implements it.

---

## FQ-004: Choose a Breeze icon for any toolbar button in Customize Toolbar
**Status:** PROCESSED (a12b522)
**Requested:** 2026-08-06
**Idea (verbatim/summarized):** "the menu points I'm adding with customize toolbar have no icons. there
should be an option to add icons. I'm already referencing an icon pack, let's offer from that pack to
choose icons for my toolbar buttons"

**Problem:** Since BUG-027 (shipped on this branch, `toolbar_registry.py` + `MainWindow._walk_menu_actions`),
Customize Toolbar can add **any** menu command to the toolbar, but only the legacy seven commands carry a
vendored icon (`ICON_ID_BY_COMMAND` maps a menu-path id → one of the 7 keys in
`icons.py::ACTION_ICON_FILES`). Every other command is icon-less by design — `_set_action_icon`
(`main_window.py:1108-1123`) returns early when there is no mapping — so a user-added button renders
text-only. The toolbar uses `ToolButtonTextBesideIcon` (`main_window.py:980-982`), so an icon-less button
shows just a label, visually inconsistent with the decorated legacy seven and giving the user no way to
make a compact, icon-first toolbar. The user wants to pick an icon for such buttons "from the pack I
already reference."

**Key finding (drove the shape of this entry):** the "pack already referenced" is **not** an enumerable
catalog today — it is exactly **7 vendored Breeze SVGs** in
`pgtp_editor/resources/icons/breeze/` (`document-open`, `document-save`, `edit-undo`, `edit-redo`,
`edit-find`, `dialog-ok-apply`, `run-build`), hardcoded one-per-legacy-command in the 7-entry
`ACTION_ICON_FILES` dict. There is no directory scan, no manifest, no qtawesome, and no `QIcon.fromTheme`
usage anywhere. A picker "over the pack" would today offer 7 icons, most already spoken for. This feature
therefore requires **vendoring a larger Breeze subset** as a prerequisite (decided with the requester
2026-08-06, see below), not just a new dialog widget.

**Proposed approach** (all four sub-decisions confirmed with the requester 2026-08-06):
- **Icon source — vendor a curated Breeze subset (~50–100 common-action SVGs)** from the same upstream
  Breeze set the current 7 came from. **Not** the full Breeze `actions/` category (bundle-size), **not**
  OS Qt theme icons (`QIcon.fromTheme` is unpopulated on Windows, which the project targets per CLAUDE.md).
  - **License/attribution:** Breeze SVGs are LGPL-3.0; the vendored subset must ship its
    `ATTRIBUTION.md` + `LICENSE-LGPL-3.0.txt` (both already present in `resources/icons/breeze/`) covering
    the expanded set, and the About box / credits should reflect the widened bundle if it names the icon
    source.
  - **Bundle-size implication:** ~50–100 additional SVGs (Breeze action SVGs are ~1–3 KB each) is a small
    but non-zero addition to the packaged app — flagged for the implementer, acceptable per requester.
  - **Rendering:** every offered icon must flow through the **existing `icons.themed_icon()` pipeline**
    (`recolor_svg`: `currentColor` + `#232629` → palette WindowText color; rendered at 22px + 44px hi-dpi),
    so newly-choosable icons tint and size identically to the current 7 and re-tint on theme change via the
    existing `_refresh_toolbar_icons`.
  - **Enumerable catalog needed (implementation note):** `icons.py` today has only the hardcoded 7-entry
    `ACTION_ICON_FILES` dict. The picker needs an enumerable catalog/manifest over the vendored subset —
    either a directory scan of `resources/icons/breeze/` at load time or a generated manifest listing
    `(icon_id, filename, human_name)` — so the picker can list and (ideally) search/filter the set. Keep
    the Qt-free/pure split `icons.py` already observes (catalog building should stay Qt-light; only
    rendering touches Qt).
- **Assignment scope — any toolbar button.** Allow assigning or **overriding** the icon on **any** button
  currently on the toolbar, including the legacy seven that already have a default icon. Not restricted to
  icon-less user-added buttons.
- **Menu propagation — toolbar-only.** Preserve the existing deliberate `setIconVisibleInMenu(False)`
  behavior (`main_window.py:1121`): a chosen icon appears **only** on the toolbar button; menu items stay
  text-only. Do not propagate the chosen icon to the menu.
- **Custom icons — bundled pack only for v1.** No user-supplied SVG/PNG files this round. (Own-file icons
  are noted as a possible future extension, explicitly out of scope for this entry.)
- **Persistence** — key each per-action icon assignment to the **stable menu-path command id**
  (`toolbar_registry.command_id_for`, e.g. `file.save-as`), the same identity already used for `toolbarIds`.
  Store the mapping (`command_id → chosen icon_id`) in QSettings alongside the existing `toolbarIds` key
  (a sibling key, e.g. `toolbarIconIds`), so it is **back-compatible**: an existing saved toolbar with no
  assignments simply keeps each button's default icon (legacy seven) or none (everything else).
  `_set_action_icon` gains a lookup — assigned icon_id wins over the `ICON_ID_BY_COMMAND` default — and an
  assignment for a command id no longer present is dropped on load the way `resolve_ids` already drops
  unknown ids.
- **UI shape** — an icon column/button per row in the On-Toolbar list of `CustomizeToolbarDialog`
  (`customize_toolbar_dialog.py`), opening an icon-picker grid (searchable/filterable over the vendored
  catalog, plus a "no icon" / "reset to default" choice). The dialog's existing test seams
  (`selected_ids()`/`set_ids()`, never `.exec()` in tests) should be mirrored by a parallel accessor for
  the id→icon assignment map so the assignment is unit-testable the same headless way.

**Alternatives considered:**
- **Pick only from the 7 we already ship** — rejected: near-useless, since most are already the legacy
  commands' own icons, and it would not solve the icon-less-added-button problem the user actually has.
- **Use OS Qt theme icons (`QIcon.fromTheme`)** — rejected: unpopulated on Windows (a first-class target
  per CLAUDE.md), so it would work on Linux only and silently give Windows users an empty picker.
- **Vendor the full Breeze `actions/` category** — rejected in favor of a curated ~50–100 subset to keep
  the bundle small and the picker scannable.
- **Allow arbitrary user SVG/PNG files in v1** — deferred: larger surface (file dialog, validation,
  recolor/sizing of arbitrary art through a pipeline built for Breeze's `currentColor` convention); noted
  as a future extension, out of scope here.

**Suggested placement:** EXTEND **§7 Customize Toolbar** in `CONSOLIDATED_SPEC.md` (lines 512–559), which
already specifies the toolbar's menu-command universe, the `ICON_ID_BY_COMMAND`/`themed_icon` icon
pipeline, "Icons are optional" (lines 544–548), the `setIconVisibleInMenu(False)` menu-stays-text-only
rule, the two-list Customize dialog, and the `toolbarIds` QSettings persistence with `resolve_ids`
back-compat. This is a direct capability addition to an already-specified feature — no new section
warranted. Whoever folds this in must (a) amend "Icons are optional / only the legacy seven have vendored
SVGs" to reflect the widened choosable catalog while keeping the "icon is never a precondition for adding a
command" invariant, (b) reuse `themed_icon`/`recolor_svg` and `_refresh_toolbar_icons` verbatim rather than
a second render path, and (c) key the new persistence to `command_id_for` alongside `toolbarIds`.

**Open questions:** none blocking — the four load-bearing decisions (icon source, assignment scope, menu
propagation, custom icons) are resolved above. Implementation-level details left to the implementer:
exact size of the curated subset and which specific Breeze icons to vendor; whether the catalog is a
runtime directory scan vs. a checked-in generated manifest; the precise QSettings key name and serialized
shape for the assignment map; and the exact picker-grid widget layout (columns, search box, "no icon"
affordance).

---

## FQ-005: Give the light theme the same professional QSS polish as the dark theme
**Status:** PROCESSED (e8f853f — spec §7/§4 + 2026-08-06 ledger row; user-verified in the running app)
— implemented directly, not via the normal QUEUED wait
**Requested:** 2026-08-06
**Idea (verbatim/summarized):** Started as a `/product-brainstorming` request to evaluate adopting a
third-party Qt stylesheet library (`Qt-Advanced-Stylesheets` / its PySide6 port `qtass-pyside6`) so the
light theme would look as polished as the dark theme. That library was investigated and explicitly
rejected (license-less PyPI package, `python<3.14` incompatible with the installed 3.14.6 interpreter,
one-person two-month project then a year of silence). The real want, once separated from the proposed
vehicle: "the same professional look in light theme that the dark theme gives me... In dark theme the
look is professional, but in light it's... so basic, standard." Resolved with zero new dependencies.

**Problem:** `pgtp_editor/ui/theme.py`'s `apply_theme(app, light)` gave the dark theme a real QSS layer
(`qdarkstyle.load_stylesheet(qt_api="pyside6")`, adopted for BUG-010's `QMenu::indicator` fix) on top of
`dark_palette()`, but the light theme got `app.setStyleSheet("")` unconditionally — Fusion + palette only,
no QSS. That asymmetry is exactly the "basic, standard" look the requester noticed.

**Resolution actually implemented:** `qdarkstyle` was already a pinned dependency (`pyproject.toml`,
`qdarkstyle>=3.2`; installed `3.2.3`) and ships `qdarkstyle.light.palette.LightPalette` alongside
`qdarkstyle.dark.palette.DarkPalette` — verified live that
`qdarkstyle.load_stylesheet(qt_api="pyside6", palette=LightPalette)` returns a real, non-empty QSS. In
`pgtp_editor/ui/theme.py`: `_dark_stylesheet()` (single `_dark_qss_cache: str | None` global) was renamed
to `_qdarkstyle_stylesheet(light: bool)`, caching both variants in `_qss_cache: dict[bool, str]`, passing
`palette=LightPalette if light else DarkPalette` explicitly (dark previously relied on qdarkstyle's
implicit default). `apply_theme` now calls `app.setStyleSheet(_qdarkstyle_stylesheet(light))`
unconditionally for both branches instead of `"" if light else _dark_stylesheet()`. `light_palette()`/
`dark_palette()` are unchanged — the QPalette source stays hand-rolled for both themes (so
`XmlEditor.apply_theme_colors`, which keys off palette Base lightness directly, is unaffected); only the
QSS *source* changed.

**Verified side-finding, not a regression:** applying either theme's non-empty QSS via
`QApplication.setStyleSheet()` makes Qt wrap the requested style in an internal `QStyleSheetStyle` proxy
whose `objectName()` reports `''`, not `"fusion"` — confirmed this already silently happened for the dark
theme before this change too (`app.style().objectName()` was already `''` post-dark-toggle; no test had
ever asserted this for dark, so it went unnoticed). Fusion is still genuinely requested via
`app.setStyle("Fusion")` and still governs anything the QSS doesn't override — this is a test-assertion
gap the light-only precondition previously masked, not a functional break. Handed to `feature-tester` to
fix the now-symmetric assertions properly (spy on `setStyle` rather than reading back `objectName()` after
a stylesheet is applied) rather than patched around in the main session.

**Alternatives considered:** Adopting `qtass-pyside6` (rejected: no license, `requires-python<3.14`
incompatible with the installed interpreter, near-zero adoption/maintenance signal). Adopting `qt-material`
(UN-GCPDS) instead — the mature, 2,857-star, BSD-2-Clause-licensed project `qtass`'s own README credits as
its inspiration/stylesheet source — was raised as the honest fallback if a real dependency were needed, but
made moot once the already-installed `qdarkstyle` was confirmed to ship the same capability for free.

**Suggested placement:** EXTEND §7 (App shell, `CONSOLIDATED_SPEC.md` theme subsection, lines ~479-507).
The documented invariant "the light case ALWAYS assigns the empty stylesheet so a light<->dark round-trip
never leaves stale dark QSS behind" (spec line ~492) is now false and needs updating, plus a Supersession
Ledger row — hand to `spec-maintainer` (JOB 1) directly; this entry documents that it should happen, it
does not do it.

**Open questions:** none — implemented, tested, and being folded into the spec as part of this same
session's work; this entry exists purely as the queue's documentation of what happened, per explicit
request, so no future queue-processing pass re-proposes it.

---

## FQ-006: Create Page/Detail/Lookup should open a new draft tab, not splice/copy-to-clipboard
**Status:** PROCESSED (f1ec13c) — all three kinds open a draft tab; the `</Pages>` splice, the clipboard copy and `_dedupe_file_name` are DELETED, and the duplicate check is now a non-blocking status note.
**Requested:** 2026-08-06
**Idea (verbatim/summarized):** "when a new page, new detail is created from database view, that new
page and detail should land in a new tab editor window. not on clipboard and not in the main xml editor,
but a separate editor window for that piece of code. then the user can edit it, finalize it, and copy
paste into the code when they wish. or never. the current method is to be changed." Converged through
three rounds of direct clarifying Q&A with the requester plus a full code-verification pass (see below);
this entry records the settled design, not an open elaboration.

**Problem:** The three "Create from DB table" actions — right-click on a table/view row in
`pgtp_editor/ui/db_check_panel.py`'s `_CREATE_ACTIONS` menu (lines ~216-220: "Create new page from this
table" / "Create new detail from this table…" / "Create new lookup from this table…"), emitting
`create_requested = Signal(str, str)` (`db_check_panel.py:61`), routed through
`ui/main_window.py::_on_db_create_requested` (lines 3737-3815) — currently land generated fragments in
two inconsistent, unwanted places:
- **Page** (lines 3767-3789): scans the raw XML buffer for an existing `<Page tableName="...">` or a
  colliding derived `fileName` (line 3772); if found, shows a **blocking** confirmation dialog
  (`_confirm_duplicate_page`) and on confirm auto-renames the fileName via `_dedupe_file_name`
  (appending `_2`, `_3`, ..., lines 3792-3798); then **splices the serialized fragment directly into the
  live buffer** immediately before the last `</Pages>` (`_insert_page_before_pages_close`, lines
  3791/3805-3813, string-level splice matching `</Pages>`'s indentation), calls `setPlainText()` on the
  main Raw XML editor, switches to the Raw XML tab, and jumps to/selects the new block.
- **Detail** and **Lookup** (lines 3749-3754): both just call `_copy_fragment_to_clipboard()` (lines
  3758-3765, `serialize(element, indent=0)` → `QApplication.clipboard().setText()`), with a status
  message "copied to clipboard — paste it into the target page." No buffer modification at all.

Neither destination is what the user wants: silently mutating the live, possibly-unsaved project buffer
(Page's path) is a surprising side effect for something the user hasn't reviewed yet, and the clipboard
(Detail/Lookup's path) is a single, unlabeled, easily-clobbered slot with nowhere to review or edit the
fragment before use. Both destinations also foreclose the "edit it, finalize it, or never use it" workflow
the requester wants — there's no persistent, inspectable place to leave a generated draft.

**Proposed approach:** Replace all three of `_on_db_create_requested`'s branches with one unified
draft-tab path, reusing existing infrastructure wholesale rather than inventing new mechanism:
- Generation is **unchanged**: `generation/from_table.py`'s `build_page()`, `build_detail()`,
  `build_lookup()` (lines 132-173) and `serialize(element, indent=0)` (lines 210-219) are untouched —
  only what happens to the serialized text changes, not how it's produced. This preserves the
  PHP-Generator-parity logic (`type_map` single source of truth, `PAGE_DEFAULTS`, FK inference, the
  reproduced vendor misspelling `foreginColumnName`) verbatim.
- All three kinds now open a **new tab** in `CenterStage`, pre-populated with the serialized fragment,
  instead of Page's buffer-splice or Detail/Lookup's clipboard-copy. Reuse the exact dynamic per-identity
  tab lifecycle `ui/center_stage.py::open_ddl_object_tab(ref, text, resolve_save_path=None, key=None)` /
  `close_ddl_object_tab(key)` (lines 209-241) already established for DDL trigger/function skeleton tabs
  — either by extending that method or adding a parallel sibling that hosts a plain
  `ui/xml_editor.py::XmlEditor` instance instead of `ui/ddl_object_editor.py::DdlObjectEditorPanel`.
  `XmlEditor` is already proven not-coupled-to-"the one project buffer": the app already runs two fully
  independent instances today (Raw XML editor + Edit XSD editor, both constructed in `center_stage.py`,
  e.g. lines 69/81) via plain `setPlainText()`/`toPlainText()`, and gets syntax highlighting +
  find/replace (`FindReplaceBar`) for free with no schema model required (`_schema_model` defaults to
  `None` and schema-aware hover/completion just no-ops without one).
- **Every creation opens its own new tab — never a shared/reused scratch tab.** Creating a Page from
  table A then a Detail from table B must result in two separate open draft tabs (per-identity keying,
  mirroring the DDL object tab's `key` parameter), not one tab silently overwritten by the next creation
  (which would clobber an in-progress edit). Tab title identifies both kind and source table, e.g.
  `"New Page: customers"` / `"New Detail: orders"` / `"New Lookup: customers"`.
  Confirmed with requester: "New tab each time."
- **No `resolve_save_path`** — these drafts never save anywhere on their own; the user's own copy/paste
  out of the tab (via the reused, find/replace-equipped `XmlEditor`'s normal text selection) is the
  entire "finalize" mechanism. Nothing programmatic pastes the draft back into the project.
- **Closable without a dirty-check prompt.** Follow the Manual tab's precedent (`hide_manual()`, no
  prompt) rather than Edit XSD/DDL-object tabs' unsaved-changes check — a draft tab was never "saved"
  anywhere and the real source of truth (the DB table) is untouched by closing it, so there is nothing to
  lose a warning would protect. Confirmed with requester: "or never" — nothing is lost either way.
- **The duplicate-fileName/tableName check survives, demoted from a blocking gate to a non-blocking
  heads-up.** Since nothing auto-inserts into the real XML anymore, a collision only matters at the
  moment the user manually pastes the draft in later, which the app cannot observe — so the existing
  `_confirm_duplicate_page`-style modal-before-insert no longer makes sense as a gate. Instead: still run
  the existing buffer-scan for an existing `<Page tableName="...">`/matching `fileName` at generation
  time, but surface it as a status-bar (or similar non-modal) note, e.g. `"Note: a Page for 'customers'
  already exists in the project"`, shown alongside opening the tab — informational only, never blocks the
  tab from opening. Confirmed with requester: "Keep as a non-blocking heads-up."
- **Drop `_dedupe_file_name`'s auto-rename entirely** (lines 3792-3798) — it was tied to the now-removed
  auto-insert path. The draft keeps whatever `fileName` `build_page`/`build_detail`/`build_lookup`
  naturally produced; the heads-up is purely informational and the user decides what to do about a
  collision themselves when reviewing the draft, rather than the app silently renaming it.
- **All three kinds move, not just Page and Detail.** Lookup creation is currently byte-for-byte the same
  clipboard-copy code path as Detail; leaving Lookup on clipboard while Detail moves to a tab would be an
  inconsistent half-measure of the same underlying change. Confirmed with requester: "Yes, all three."

**Alternatives considered:** Keeping Page's direct-insert path for Page only (arguably the more
"finished" case, since it already carries full PHP-Generator-parity logic) while changing only
Detail/Lookup was implicitly rejected — both by the requester's own framing ("the current method is to
be changed," naming Page explicitly alongside Detail/Lookup rather than singling one out) and by the
consistency argument above. Recorded so whoever implements this doesn't second-guess and revert Page's
behavior specifically while doing Detail/Lookup.

**Suggested placement:** EXTEND §17.5 ("Create Page/Detail/Lookup from a DB table,"
`CONSOLIDATED_SPEC.md` lines 1532-1541, currently reading "create page (insert before `</Pages>`, jump +
select), create detail (copy `<Detail>` to clipboard), create lookup (copy `<Lookup/>` to clipboard)") —
only the destination-and-presentation half of this section changes (the "insert before `</Pages>`" /
"copy to clipboard" ×2 clause), not the generation-parity half (`type_map`, `PAGE_DEFAULTS`, FK
inference, the `foreginColumnName` misspelling), which must be preserved verbatim. Reuse
`ui/center_stage.py`'s existing dynamic-tab lifecycle (`open_ddl_object_tab`/`close_ddl_object_tab`,
lines 209-241) and `ui/xml_editor.py::XmlEditor` wholesale — do not build a new text-editing widget or a
new tab-management mechanism. Note for whoever implements: §17.5's current text already says "right-click
a table/view node in the coherence view's **Tables and Views** branch," anticipating FQ-003's not-yet-
implemented merged coherence view (still `QUEUED` as of this writing) — the actual entry point today is
still `db_check_panel.py::DbCheckPanel`'s `_CREATE_ACTIONS` context menu (wired to `main_window.py`'s
`coherence_panel`). If FQ-003 lands first, wire this into whatever the merged view's Tables-and-Views
branch context menu becomes instead; if this lands first, wire it into the current `DbCheckPanel` menu
and FQ-003's implementer inherits the already-updated destination behavior for free.

**Open questions:** none — all three (scope: all three kinds vs. Page-only; tab-sharing: new tab each
time vs. shared scratch tab; duplicate-check: blocking vs. non-blocking) were resolved directly with the
requester and are folded into "Proposed approach" above. Implementation-level details left to whoever
picks this up: exact `open_ddl_object_tab` signature extension vs. new sibling method; exact status-bar
message wording/duration for the non-blocking duplicate heads-up; whether draft tabs persist across
project close/reopen (current XML/DDL tabs' behavior on project close should be the default assumption
unless code review says otherwise).

---

## FQ-007: New Project sandbox step should CREATE + provision the sandbox DB (auto-named), not ask for an existing one
**Status:** PROCESSED (1c1a2c1) — New Project takes a server connection only and creates + provisions the auto-named database itself. NOTE two honest limits: a fresh project has no target, so the sandbox is provisioned EMPTY (usable, but an object referencing target tables fails until a target is set and the sandbox re-provisioned); and the retry/collision logic lives in `ui/sandbox_controller.py` rather than `db/sandbox.py` as the entry proposed. Spec fold-in for §18.2 / §18.5 D2 still owed.
**Requested:** 2026-08-06
**Idea (verbatim/summarized):** "Project creation: sandbox setup asks for database name, and checks for
existence. instead it should create the database and use it as sandbox (installing also plpgsql_check
extension)." Converged through one round of direct clarifying Q&A with the requester (Q1–Q5 below); this
entry records the settled design.

**Problem:** The New Project dialog's local-sandbox step (`pgtp_editor/ui/new_project_dialog.py`) today
collects host/port/**Database**/user/password (lines 102-113) plus a superuser **Test** button, and
`MainWindow._create_ddl_project` (`pgtp_editor/ui/main_window.py:2744-2756`) merely records those values
into `ProjectSettings.sandbox` (`pgtp_editor/db/ddl_project.py:116-120`) and **does nothing else** — no
`CREATE DATABASE`, no baseline provisioning, no `CREATE EXTENSION`, not even the existence check the
requester's phrasing implies. So "sandbox setup" at project-creation time is effectively "type a DB name,
we save the string"; all real provisioning is deferred to the separate Sandbox Setup… lane later. The
requester wants project creation to actually stand up a working sandbox then and there. **Key tension
that shaped this entry:** the requester's original framing ("asks for a database name / create *that*
one") collides head-on with the settled, non-negotiable §18.5 D2 **ownership convention**
(`CONSOLIDATED_SPEC.md` ~3760-3774): the app owns its sandboxes *by naming convention*, `CREATE DATABASE`
goes only through `db/sandbox.py::create_sandbox_database`, which **validates (not sanitizes)** the name
against `^pgtp_sandbox_[a-z0-9_]{1,40}$` and stamps a `pgtp-editor-sandbox:<uuid>:<iso8601>` comment
marker; `open_sandbox` **refuses** any DB lacking that marker. A free-text user-typed name cannot be the
name we CREATE. The Q&A below resolves that tension in favor of the convention.

**Proposed approach** (all five decisions confirmed with the requester 2026-08-06). This is largely a
**wiring gap closure** — the create/provision/install machinery already exists and is spec'd; almost
nothing new needs building in `db/`:
- **Auto-generate the sandbox DB name; drop the free-text field (Q1).** Remove the "Database:" line edit
  from the New Project sandbox step (`new_project_dialog.py:104,111` and its `sandbox_params()` getter's
  `database=` at line 207). The app **derives** a valid `pgtp_sandbox_*` name automatically — it must
  satisfy the existing `_SANDBOX_DB_NAME_RE = ^pgtp_sandbox_[a-z0-9_]{1,40}$` (`db/sandbox.py:616`) and
  get the ownership-marker comment `create_sandbox_database` already writes. The user never types a
  sandbox DB name. (The Sandbox connection's other fields — host/port/user/password — stay.)
- **On collision, pick a NEW random name and retry (Q2).** If the generated `pgtp_sandbox_*` name already
  exists on the server, generate a *different* random `pgtp_sandbox_*` name and retry (up to a small
  bound, e.g. a handful of attempts), then CREATE the first free one. Every project creation therefore
  ends with a brand-new, uniquely-named sandbox DB. **The reuse-if-app-owned and drop+recreate paths are
  intentionally NOT used** — noted explicitly so the resolver does not add them. Surface a clear error
  only in the (pathological) case that no free name is found within the retry bound. Note: today
  `create_sandbox_database` takes a caller-supplied `name` and does a single `CREATE DATABASE` with no
  existence probe or retry loop — the generate-random-and-retry-on-collision logic is the one genuinely
  new bit of `db/`-layer behavior (probe `pg_database` for the candidate name, or catch the duplicate-DB
  error and retry), and should live beside `create_sandbox_database` in `db/sandbox.py`, keeping name
  generation pure/testable and the collision probe behind the existing injectable runner seams.
- **Create against the `postgres` maintenance DB using the sandbox creds (Q3).** `CREATE DATABASE` cannot
  run inside the target DB, so derive `admin_params` from the Sandbox connection params with the database
  pointed at `postgres` (implicit maintenance DB) — **no separate admin-connection field**. This matches
  the existing `SandboxController.provision(admin_params=..., database_name=...)` signature
  (`ui/sandbox_controller.py:432-495`), which already runs `self._database_creator(admin_params,
  database_name)` then snapshots the target and provisions.
- **Eagerly create + provision + install at creation time, off the GUI thread (Q5).** Wire
  `MainWindow._create_ddl_project` to actually run the full path: `create_sandbox_database` (auto-named,
  against maintenance DB) → `provision_sandbox` (baseline from the **target** profile via
  `snapshot_for_baseline`, or a `WITH_DATA` clone per the already-chosen `sandbox_mode`) →
  `install_plpgsql_check(session)`. Reuse `SandboxController.provision` rather than re-implementing the
  sequence. Run it via the existing `_run_async` off-GUI-thread pattern (same one
  `NewProjectDialog.test_sandbox` already uses at lines 246-250) so a slow/dead server can't freeze
  project creation. The chosen `pgtp_sandbox_*` name lands in `ProjectSettings.sandbox.database` so later
  Sandbox Setup…/reset re-opens the same DB.
- **On failure, create the project and degrade to the "quality" tier — never block (Q4).** If
  `CREATE DATABASE` or `CREATE EXTENSION plpgsql_check` fails (not superuser, `plpgsql_check` C-library
  absent on the server, unreachable host, etc.), still create the project; mark the sandbox unavailable
  and surface the **exact reason string** the existing pure gate already produces
  (`db/sandbox.py::install_gate` / `REASON_REQUIRES_SUPERUSER` / the platform-absent text, lines
  1046-1083) rather than a bare stack trace. This is exactly the §18 three-tier graceful-degradation
  posture: a project with no working sandbox is a **"quality project"** (tier 2), not an error
  (`determine_project_tier`, `db/sandbox.py:409-457`, already models this). Do NOT abort project creation
  on sandbox failure.
- **The superuser Test button (`test_sandbox`) stays** as the up-front pre-flight — `CREATE EXTENSION`
  needs superuser, and the button already checks exactly that plus `pg_dump`/`pg_restore` for a
  `WITH_DATA` sandbox. It complements, not replaces, the eager provisioning (Test warns early; the Q4
  degrade path is the real backstop if the user proceeds anyway or conditions change).

**Alternatives considered:**
- **Keep the free-text DB-name field and CREATE *that* name (the requester's literal first phrasing)** —
  rejected because it would require either abandoning or overriding the §18.5 D2 ownership convention
  (`pgtp_sandbox_*` prefix + marker comment, "validated not sanitized"), which is stated verbatim as
  settled and non-negotiable and is the *only* safety property the stateful sandbox has left. Auto-naming
  keeps that guarantee intact. Confirmed with requester (Q1).
- **On name collision, reuse the existing DB if app-owned (else error), or offer drop+recreate** — both
  rejected in favor of random-retry (Q2). Reuse risks silently inheriting a stale/foreign sandbox; drop
  is destructive. Random unique naming sidesteps both. Recorded so the resolver does not reintroduce a
  reuse/drop branch.
- **Leave New Project as-is and rely on the existing Sandbox Setup… lane to provision later** — rejected
  (Q5): that *is* today's behavior, and it is exactly what the requester is complaining about ("sandbox
  setup" that sets nothing up). The point is to make the New Project step do real work.
- **A separate admin/maintenance-connection field for CREATE DATABASE** — rejected (Q3) as needless UI:
  the sandbox creds pointed at `postgres` are sufficient, matching `SandboxController.provision`'s
  existing `admin_params` shape.
- **Block project creation on provisioning failure** — rejected (Q4) as hostile to the offline/managed-
  server case the tier taxonomy exists precisely to handle gracefully.

**Suggested placement:** EXTEND §18.2 (New Project dialog's local-sandbox step) **and** §18.5 D2 in
`CONSOLIDATED_SPEC.md` — not a new section. This reuses `create_sandbox_database` / `provision_sandbox` /
`install_plpgsql_check` / `install_gate` / `SandboxController.provision(admin_params, database_name)`
wholesale and mostly closes the wiring gap in `MainWindow._create_ddl_project`. It **must respect, not
override,** the §18.5 D2 ownership convention (auto-generated names still satisfy
`^pgtp_sandbox_[a-z0-9_]{1,40}$` and carry the marker comment). **New specifics for `spec-maintainer` to
fold in once this lands, since the current spec does not yet describe them:** (a) the **auto-generate +
random-retry-on-collision** naming policy (§18.5 D2 today specifies `create_sandbox_database(admin_params,
name)` with a caller-supplied name and no collision handling — the New Project flow now generates the name
and retries; §18.5 D2's "create a sandbox database for me" mitigation, spec ~3776-3784, is the closest
existing hook); (b) the **eager create-+-provision-+-install at New-Project time** (D2a's note at spec
~3805-3811 says the with-data/without-data choice is presented "at that same step" but does not commit to
provisioning eagerly at creation — this makes it explicit); (c) that on failure the New Project flow
**degrades to the tier-2 quality project** rather than aborting. Whoever picks this up should reuse
`_run_async` and `SandboxController` rather than a second provisioning path.

**Open questions:** none — Q1 (auto-generate, drop the field), Q2 (random-retry, no reuse/drop), Q3
(sandbox creds against `postgres`), Q4 (create-project-and-degrade, never block), Q5 (eager
provision-at-creation, off-GUI-thread) all resolved directly with the requester and folded into "Proposed
approach" above. Implementation-level details left to whoever picks this up: the exact name-generation
scheme (e.g. `pgtp_sandbox_` + short random suffix within the 40-char/`[a-z0-9_]` budget) and retry bound;
whether collision detection probes `pg_database` up front or catches the duplicate-database error and
retries; exact off-thread progress/status affordance in the dialog vs. the main window during eager
provisioning; and precise degrade-reason wording surfaced to the user beyond `install_gate`'s existing
strings.

---

## FQ-008: Composable P>1/D>1/L>1 checkboxes in the Database/XML Coherence view
**Status:** PROCESSED (eb7aa50) — three AND-composing role checkboxes with the panel's own filter banner. Composition with the mismatch toggle is scope-then-select, NOT a per-row AND, because a per-row AND silently hides flagged column/reference rows under a qualifying relation. Spec note owed: §17's line saying the mismatch toggle "needs its own filter predicate … nothing pre-packaged covers it" is now stale.
**Requested:** 2026-08-06
**Idea (verbatim/summarized):** "in the Database coherence window I'd like to have filter for P>1 D>1
L>1, also in combination" — checkboxes to filter the coherence view down to tables/views used on more
than one Page, more than one Detail, and/or more than one Lookup, combinable. Converged through three
rounds of direct clarifying Q&A with the requester plus a code-verification pass; this entry records the
settled design, not an open elaboration.

**Problem:** The merged "Database/XML Coherence" view (shipped from FQ-003) in
`pgtp_editor/ui/coherence_panel.py` has exactly one existing filter mechanism today: a plain `QCheckBox`
labeled "Show only mismatches" (`self.filter_checkbox`, line 136), wired to `_rebuild()` (line 141).
`_rebuild()` (lines 209-233) is a **binary, non-composable** rebuild: `only_mismatches =
self.filter_checkbox.isChecked()` then `shown = self._tree.filtered() if only_mismatches else
self._tree` (lines 215-216) — either the full tree or the one hardcoded filtered tree, never a
composition of independent predicates. `CoherenceTree.filtered()` (`pgtp_editor/db/coherence.py`, lines
149-158) builds a pruned tree via `_prune_branch` (line 189) calling `filter_flagged` (line 174), which
recursively keeps only flagged nodes and their ancestors, applied to both the "Tables and Views" branch
and the "Pages" branch — the precedent for "a filter spans both branches," which the requester wants
matched. The "(P# D# L#)" badge is already rendered per relation-level row
(`coherence_panel.py::_badge_text()`, line 325), reading directly from `db/compare.py`'s
`TableCheck.page_count`/`.detail_count`/`.lookup_count` — the exact three numbers the new filter tests.
This data is already computed and already displayed; the filter needs no new data source, only a new
predicate over data that already exists on every row.

**Proposed approach:** Add three `QCheckBox`es ("P>1"/"D>1"/"L>1") next to the existing "Show only
mismatches" checkbox in `coherence_panel.py`, all wired to the same `_rebuild()` path. Generalize
`CoherenceTree.filtered()`/`filter_flagged` (`db/coherence.py`) to accept an injected predicate function
over a `TableCheck`-bearing node (rather than the current hardcoded "is this node flagged" check), so
`_rebuild()` builds one combined predicate — `is_mismatch_flagged` (only if that checkbox is on) AND
`page_count > 1` (only if P>1 is checked) AND `detail_count > 1` (only if D>1 is checked) AND
`lookup_count > 1` (only if L>1 is checked) — and passes that single predicate through the existing
both-branches pruning machinery unchanged. No new data source needed (`page_count`/`detail_count`/
`lookup_count` already exist on every `TableCheck`); this is purely a predicate-composition and
small-UI change, not new plumbing. Three settled decisions from direct Q&A with the requester:
1. **The three P/D/L checkboxes combine with AND, not OR.** Checking more than one narrows the result
   further — a table must satisfy every checked condition, matching how checkbox filters normally
   stack. Confirmed: "ALL checked must hold (AND)."
2. **Composes with the existing "Show only mismatches" toggle — both can be active simultaneously.**
   E.g. "Show only mismatches" + "P>1" together shows only mismatched tables that are also used on more
   than one page. This requires reworking `_rebuild()`'s current binary `only_mismatches` bool into a
   composable predicate — build one combined predicate function (mismatch-flagged AND
   all-checked-P/D/L-conditions) and pass it into a generalized `CoherenceTree.filtered(predicate)`
   rather than the current hardcoded `filter_flagged`. Confirmed: "Yes, compose."
3. **The filter prunes both branches — "Tables and Views" and "Pages" — matching the mismatch toggle's
   existing precedent.** A table hidden by the P/D/L filter also disappears from the "Pages" tree's
   Page/Detail/Lookup reference nodes that point at it, keeping the two branches consistent with each
   other while the filter is active. Confirmed: "Both branches."

**Alternatives considered:** An OR-combination reading ("any of the checked conditions") was considered
and rejected — confirmed with the requester (AND is what "in combination" means here), since OR would
answer a different question ("find any kind of heavy reuse") than what was asked ("narrow down by
combined criteria"). A `QSortFilterProxyModel`-based approach mirroring the Caption Management panel's
heavier multi-filter apparatus (`pgtp_editor/ui/caption_management_panel.py`'s preset predicate +
find/regex + per-column checkbox dropdowns + active-filter banner + `_CaptionFilterProxyModel`, roughly
lines 324-500) was considered as a UI-consistency option and rejected as over-scoped for three fixed
boolean conditions — the coherence panel's existing plain-`QCheckBox` style (matching the current
mismatch toggle) is the right-sized fit, not a proxy-model/banner-based approach. Noted explicitly so
whoever implements this doesn't over-build.

**Suggested placement:** EXTEND §17 (Database/XML Coherence view) in `CONSOLIDATED_SPEC.md`, in the same
subsection that documents the mismatch toggle ("3. Mismatch toggle...", spec lines ~1618-1631) — this is
a direct sibling of that toggle, not a new section. Whoever implements this should generalize the
mismatch predicate into the same composable-predicate mechanism the P/D/L checkboxes use, so the spec
text currently reading "the toggle needs its own filter predicate spanning both branches — nothing
pre-packaged covers it" (spec lines ~1629-1631) gets updated to describe the resulting general
composable-predicate design instead of the current one-off. Verified still accurate against code at
triage time: `pgtp_editor/ui/coherence_panel.py` (`filter_checkbox` line 136, `_rebuild` lines 209-233,
`_badge_text` line 325) and `pgtp_editor/db/coherence.py` (`CoherenceTree` line 134, `filtered()` line
149, `filter_flagged` line 174, `_prune_branch` line 189).

**Open questions:** none — all three (AND vs. OR combination, composability with the mismatch toggle,
both-branches pruning) were resolved directly with the requester and are folded into "Proposed approach"
above. Implementation-level details left to whoever picks this up: exact checkbox layout/ordering
relative to the existing "Show only mismatches" checkbox; exact predicate-injection signature for
`CoherenceTree.filtered()`/`filter_flagged` (e.g. `Callable[[CoherenceNode], bool]` vs. a small predicate
object); and whether "P>1" etc. should be full words in a tooltip (e.g. "more than one Page") given the
existing "(P# D# L#)" badge already establishes the P/D/L abbreviation convention in this same view.

---

## FQ-009: Offer "run on sandbox / run on quality" when deploying a DDL object edit
**Status:** QUEUED — discoverability half PROCESSED (4bc73b6); the quality leg is APPROVED and pending implementation.

**OWNER DECISION 2026-08-06: accept precondition 2 as specified and wire the leg.** The concern was put to the owner explicitly — with Apply-to-Target live, `_precondition_validation` treats "the ladder never ran over this buffer" as overridable and only hard-blocks tiers that ran AND found issues, so a user with no sandbox reaches an irreversible production write in two clicks and one Yes, and Apply-to-Target has no revert snapshot. The owner's decision is that the enumerated `report_unverified` confirmation (which names exactly which tiers went unverified and why) is sufficient protection, and that the blast radius is theirs to accept. Recorded here so the reasoning is not re-litigated: precondition 2 is NOT to be narrowed, and no spec change is needed.

**Implementation dependency:** the leg's target provider is `MainWindow.active_target_params(tree=None)` (BUG-034, 4bc73b6), which is being MOVED into `DdlProjectController` by the §18-spine extraction wave. Wire `live_identity` against it in its settled home rather than the host method, which is mid-move. The `_precondition_signature` hardening already landed: the seam must RAISE when it cannot read the catalog, never return None, because None means "object absent, so applying creates it" and would turn an unreachable database into a passed signature check.

**The "run on quality" leg is deliberately NOT wired, pending an owner decision.** With it live, the guard chain ends in an override reachable with NOTHING verified: `_precondition_validation` treats "the ladder never ran over this buffer" as overridable and only hard-blocks tiers that ran AND found issues, so a user with no sandbox at all could reach an irreversible production write in two clicks and one Yes. That is §18.5 precondition 2 exactly as specified, so nothing was changed — but shipping a prominent picker and that path together would widen the blast radius as a side effect of a UX fix, and Apply-to-Target has no revert snapshot. It also depends on BUG-034's target profile (now fixed, 4bc73b6) and BUG-030's probe (fixed). **Decision needed:** is a zero-verification override acceptable for a production write, or should the override require at least one successful ladder run over the current buffer first (a spec change to precondition 2)? Hardening already landed ahead of the seam: `live_identity` returning None means "absent, so applying creates it", which CLEARS precondition 1 — so a host reporting a connection failure as None would turn an unreachable database into a passed signature check; `_precondition_signature` now refuses on any exception, naming it.
**Requested:** 2026-08-06
**Idea (verbatim/summarized):** "DDL explorer: neither checkout nor edit has the option to save to the
database. There should be on Ctrl+S after saving the option to run on sandbox or run on quality node."

**Problem:** The requester correctly observes that saving a DDL object in the editable DDL object tab
(`pgtp_editor/ui/ddl_object_editor.py`, opened from the DDL Explorer via checkout or edit) only persists
LOCALLY. `MainWindow._save_ddl_object_editor` (`pgtp_editor/ui/main_window.py:2893`) writes the buffer to
a `.sql` path and "Never touches a database" — there is no save-time affordance to apply the DDL to an
actual database. What the requester is asking for — a post-save choice to run the edited DDL against the
SANDBOX or the QUALITY (target) node — is **already a settled, named design** in the spec: the
**"Deploy this edit…"** picker (§18.5, settled 2026-08-05, `CONSOLIDATED_SPEC.md` lines ~3612-3650),
which presents the three coexisting per-edit destinations (Apply to Sandbox / Save for a future batch
deploy / Apply to Target) and delegates to each gesture's existing wiring. So this is NOT a missing
feature at the design level; it is (a) a discoverability gap — the affordance exists but the requester
didn't find it — and (b) a partially-built lane, since only Apply to Sandbox is wired today and Apply to
Target ("quality node") is deliberately unwired pending its preconditions. The requester has confirmed
(2026-08-06) that the resolution is exactly this: keep the picker, make it discoverable, and wire the
quality leg — NOT a save-time prompt (see Proposed approach / Open questions for the settled decisions).

Concretely, what already exists in code vs. what is missing:
- **"Deploy this edit…" picker** — BUILT in the panel: context-menu item at
  `ddl_object_editor.py:777` (`menu.addAction("Deploy this edit…", self.deploy_this_edit)`), the
  `deploy_this_edit()` method (line ~1102), and the three-destination enum (line ~94). Also surfaced as a
  Database-menu entry (spec lines ~5421-5435). The exact picker UI (modal vs. QMenu fly-out) is still an
  open spec question (lines ~5809-5812).
- **Apply to Sandbox** — BUILT and WIRED: `_apply_ddl_object_to_sandbox`
  (`main_window.py:3263`) through `SandboxSession.apply`, confirm-gated by `_confirm_sandbox_apply`
  (line 3249), wired via `_wire_ddl_object_apply_seams` (line 3216) only while a live sandbox session
  exists. Requires a provisioned sandbox (FQ-007 / §18.5 D2).
- **Apply to Target ("run on quality node")** — DESIGNED in the panel (`has_target_apply`,
  `set_apply_seams(apply_to_target=…)`, `ddl_object_editor.py:870`) but **deliberately NOT wired**:
  `_wire_ddl_object_apply_seams` (line 3219) states Apply to Target "needs the live-identity seam its
  precondition 1 cannot be enforced without" and an unenforceable precondition must remove the gesture.
  Blocked on the target connection actually being populated — see BUG-034 (`.pgtp` target never imported
  into `ProjectSettings.target`) and BUG-030 (quality node status). Its four hard preconditions are
  spec'd at lines ~3639-3642.

**Proposed approach (settled 2026-08-06 with the requester):** Keep Ctrl+S EXACTLY as it is today — a
plain local file save that never touches a database. The §18.5 safety invariant (lines ~3614/3626)
stays intact; do NOT add a post-save run prompt and do NOT add a Ctrl+S variant, and no
`spec-maintainer` reconciliation of that invariant is needed. The work is two parts, both extensions of
the already-settled "Deploy this edit…" lane:
1. **DISCOVERABILITY — surface the existing "Deploy this edit…" picker so users find it.** The picker
   (`ddl_object_editor.py:777`, `deploy_this_edit()` ~line 1102) is exactly what the requester wanted
   but could not find. Make the affordance clearly visible from the DDL object editor / checkout flow —
   a visible button or prominent menu item, not a buried context-menu entry. Implementer's choice among
   the still-open picker-UI decision (spec lines ~5809-5812), a clearer action label/tooltip, and a
   toolbar surface (explicitly allowed by spec line 3627). This is the crux of the requester's complaint.
2. **Wire the Apply-to-Target ("run on quality") leg** that is currently designed-but-deliberately-
   unwired. Scope: **routines first** — functions / stored routines / triggers, via CREATE OR REPLACE,
   matching §18.3's current routine-only reach. Table DDL (ALTER-vs-CREATE diffing) is **explicitly OUT
   OF SCOPE** for this entry (possible future extension). Route it through the existing `apply_to_target`
   seam and its four hard preconditions (signature-change refusal, green-sandbox-validation gate with
   named override, the no-revert-snapshot transactional caveat, and the confirmation naming object AND
   database), reusing `db/apply.py` — no new write path, per the spec's explicit "No new write path"
   clause (line 3643). Apply to Target is a real, possibly production-facing write, so it MUST go through
   a confirmation gate and should reuse the run-results surfacing already built for the sandbox run path
   (the Audit `[Check]` channel and the sandbox results view). Apply-to-Sandbox stays as-is
   (`main_window.py:3263`, already wired).

**Dependencies (state prominently, this leg is ordered-after them):** Wiring Apply-to-Target requires the
quality/target connection to actually be populated and reachable, so it is BLOCKED ON / ordered-after
**BUG-034** (import the `.pgtp` connection into `ProjectSettings.target`) and **BUG-030** (the quality
node status must be a real reachability probe, not "configured"). Until BUG-034 lands, the live-identity
seam Apply-to-Target's precondition 1 needs cannot be supplied, and the gesture correctly stays absent.
The discoverability work (part 1) has no such dependency and can land independently.

**Alternatives considered:**
- **Auto-prompt after every Ctrl+S (the requester's literal phrasing: "on Ctrl+S after saving the option
  to run on sandbox or run on quality node").** REJECTED — and the requester confirmed the rejection on
  2026-08-06. It directly contradicts a stated safety invariant: the spec insists "Ctrl+S remains exactly
  what it is today — a plain file save that never touches a database" (line 3614) and "an irreversible
  outward effect must not be one keystroke away" (line 3626), which is exactly why Apply and "Deploy this
  edit…" carry no shortcut. An always-shown post-save prompt also becomes intrusive on every save. The
  requester was surfacing a discoverability gap, not asking to reopen the invariant; the resolution is
  the picker + discoverability + wiring the quality leg, with the Ctrl+S invariant left untouched.
- **A brand-new "Apply to DB" action separate from "Deploy this edit…".** REJECTED — it would duplicate
  the picker that already exists and re-introduce the "which of three gestures do I want" problem the
  picker was created to solve (spec lines 3617-3619).
- **Raw ad-hoc exec of the CREATE OR REPLACE text against quality.** REJECTED for the target/quality
  path — the spec routes target applies through `db/apply.py` with its four preconditions and Audit
  `[Check]` reporting; a bare exec would bypass the signature-change refusal and the green-sandbox gate.
  (For the sandbox, `SandboxSession.apply` is already the sanctioned committing call.)

**Suggested placement:** EXTEND §18.5 (the editable DDL object tab and its Save/Apply gestures) in
`CONSOLIDATED_SPEC.md`, specifically the "Deploy this edit…" subsection (lines ~3612-3650) and the
Apply-to-Target wiring — this is finishing an already-specified lane, NOT a new section. No change to
the Ctrl+S invariant (it stays exactly as today). Nothing new is being invented; the write seam
(`db/apply.py`), the picker (`deploy_this_edit()`), and the sandbox apply already exist and must be
reused, not forked. Cross-references: **BUG-034** and **BUG-030** (target/quality must be populated and
probed before Apply-to-Target can be wired — this leg is ordered after both), FQ-007 (sandbox must be
provisioned for Apply-to-Sandbox to have a session).

**Open questions:** None blocking — both prior questions were resolved with the requester on 2026-08-06:
(1) keep the existing separate "Deploy this edit…" picker, make it discoverable, and wire the quality
leg — NO save-time prompt, Ctrl+S invariant untouched; (2) scope Apply-to-Target to functions / stored
routines / triggers first (CREATE OR REPLACE), with table DDL explicitly out of scope. Settled
constraints folded into "Proposed approach": Apply-to-Target must be confirm-gated and must reuse the
sandbox run-results surfacing (Audit `[Check]` channel + sandbox results view; consistent with spec line
3642, "target apply still reports to the Audit panel under `[Check]`"). Implementation-level details left
to whoever picks this up: the exact discoverability surface for the picker (visible button vs. prominent
menu item vs. toolbar) and the still-open picker-UI idiom (modal dialog vs. QMenu fly-out, spec lines
~5809-5812); whether Apply-to-Target runs plpgsql_check after applying (spec implies yes for the sandbox
validation gate that precedes a target apply).

---

## FQ-010: Launch modal presenting the four ways into the app (and the removal of Open Recent + double-click open)
**Status:** PROCESSED (02e47e0) — `ui/launcher_dialog.py`, shown from `main.py` after `window.show()` behind an injectable seam, never from `MainWindow.__init__` (49 test files construct one). Suppression persists as `launcherSuppressed`; Escape lands in the empty app and never quits. Open Recent and the whole `recentFiles` store are gone, along with the toolbar's "recent" label heuristic. The GUI no longer opens an argv file, but `args.file` SURVIVES for `--mcp`'s default project. The `.desktop` file's `%f` removed; it never had a MimeType line, so no association dangles.
**Requested:** 2026-08-07
**Idea (verbatim/summarized):** "When I start the software I should have this options clear." · "Let's do a
modal." Four groups on launch: (1) **Open a pgtp for editing**, (2) **New Project / Open Project**,
(3) **Open other files**, (4) **Maintenance mode**. Separately, and folded in here because it removes the
only resumability the launcher could otherwise have offered: "Let's delete Open recent, and I don't want
the app to open on doubleclick. These features were good for a standalone pgtp editor but we've already
left that." Converged through one round of direct Q&A with the owner (Q1–Q6 below) plus a code-verification
pass. **This is step 1 of a deliberate, slow UX review** (`docs/UX_REVIEW.md` holds the wider dossier) —
the entry is deliberately fenced to the modal and what it presents. FQ-011 owns what a mode *does*.

**Problem:** Opening the app presents **no guidance whatsoever**. `pgtp_editor/main.py::main()` constructs
`MainWindow`, calls `window.show()`, then optionally opens a `.pgtp` from `argv` — nothing else. The user
lands in an empty Raw XML tab with an empty Project Tree and must already know which of five workflows
this app supports and which menu starts it. `CONSOLIDATED_SPEC.md` line 393 states the condition plainly:
`startup tree is genuinely empty — no placeholder project`. **There is no launcher, welcome screen or
start page anywhere in the spec** (verified by grepping `launch|startup|Welcome|start page` across all
~5,8xx lines): §7's only startup statements are `**Startup file:** main() opens a .pgtp passed as argv[1]`
(line 547), the unconditional `_restore_theme` (lines 593–596) and `Window-state persistence` (598–599).

Two aggravating facts, both verified:
- **`windowState` IS restored** (`closeEvent` saves `saveGeometry()`/`saveState()`, restored on
  construction). The app returns with the user's docks, tab layout and toolbar exactly as left — while
  holding **no document, no project and no connection**. The restored layout is a *false signal of
  continuity*: it looks like a resumed session and is not one. Any launcher design has to be read against
  that backdrop.
- **After the Open-Recent deletion below there is no resumability at all.** `recentFiles` is the only
  launch-time memory of prior work that exists (`recentProjects`/`lastProject` do not exist — grepped),
  and it is being deleted. PHP files were never recorded either. So the launcher presents *actions*, not
  a resume list, and it does so knowingly.

**The five workflows the four groups collapse** (the owner's own taxonomy, recorded so the grouping is not
re-derived later):
- **Group 1 ← open a `.pgtp`, edit it with the XML tooling, compare it against its quality database (the
  Database/XML Coherence view, §17), and generate. No project, no sandbox.** Verified this genuinely works
  today: the coherence view needs only a non-empty editor buffer, and the connection comes from the
  projectless-only `Database ▸ Connection Setup…` (disabled while a project is open, BUG-024, §26 line 5389).
- **Group 2 ← both project workflows:** (a) working on the quality database via a local sandbox for
  linting/testing with per-object checkout (§18.2/§18.5), and (b) `.pgtp` diff/merge versioning to converge
  on a deployable file (§12/§18.3).
- **Group 3 ← editing other files, currently PHP** (§21, `File ▸ Open PHP File…`).
- **Group 4 ← maintaining the app itself.** See Q3 for its exact, verified contents.

**Proposed approach** (Q1–Q6 all answered by the owner 2026-08-07):
- **A modal shown from `main.py`, after `window.show()`, behind an injectable seam.** Two hard constraints,
  both non-negotiable:
  1. **It must NOT live in `MainWindow.__init__`.** **49 test files construct a `MainWindow`**; a modal
     there would hang every one of them, and CLAUDE.md forbids a test ever reaching an un-patched modal Qt
     call (`QDialog.exec`, `QMessageBox.*`, `QFileDialog.*`). It belongs in `main.py` after
     `window.show()`, behind an injectable seam like every other confirmation in this codebase (the
     `confirm=` test-seam pattern §7 already uses for `_confirm_close()`).
  2. **`--mcp` must remain structurally unable to reach it.** `main.py:197` (`if args.mcp: return
     run_mcp_server(args.file)`) returns **before any Qt import** — stdio is the JSON-RPC transport and a
     GUI contending for stdout would corrupt every session. State this as an invariant in the spec so
     nobody later moves the launcher above that early return.
- **Four groups, exactly as the owner named them:** (1) Open a pgtp for editing · (2) New Project / Open
  Project · (3) Open other files · (4) Maintenance mode. Each group's entries dispatch to the **existing**
  menu actions — `File ▸ Open…`, `File ▸ New Project…` / `Open Project…`, `File ▸ Open PHP File…`, the
  §11 XSD actions and the §20 Generation actions — never a second implementation of any of them.
- **A group choice sets a PERSISTED MODE (Q1).** The owner chose mode-and-menu-filtering over the
  navigation-shortcut reading. **This entry owns only the modal, the four groups, the suppression
  checkbox and the cancel behaviour. FQ-011 owns the persisted mode concept and what it does to the menu
  bar** — see "Suggested placement" for why the split is not cosmetic. FQ-010 is ordered **first**;
  FQ-011 is named as its dependent, not its dependency.
- **Group 4 = XSD + §20 only (Q3).** Owner's words: *"For now XSD only and the menu points of Generation
  that belong to the development of re_phpgen."* Verified in `ui/generation_controller.py::build_menu` —
  the split lands **exactly on an existing spec boundary**, which is why the grouping is defensible rather
  than arbitrary:
  - **IN (§20 — re_phpgen, own generator + gap loop):** `Locate panGen Runtime...` (:210),
    `panGen (Generate Own PHP)` (:212), `rePHPgen (Analyze Gap)` (:214), `Save reJSON...` (:216).
  - **OUT (§19 — vendor PHP generation, used in ordinary development):** `Locate PHP Generator
    Executable...` (:201), `Generate PHP...` (:204), `Open Output Folder` (:207).
  - Plus the §11 XSD actions (`Schema ▸ Edit XSD` / `Edit AutoXSD` / `Verify XSD` / `Export XSD` /
    `Import XSD`; note `Go To XSD` is Ctrl+L with **no menu entry**, `xsd_controller.py:209-213`, so it
    cannot be presented by path — `docs/UX_REVIEW.md` §A9).
  - The **label survives triage**: with §20 in it, "Maintenance mode" really is *maintain the app* rather
    than *use the app*, so the name is honest. **"For now" is the owner's word — do NOT spec this
    membership as closed**; the log folder (`Help ▸ Open Log Folder`), `View ▸ Customize Toolbar…`,
    `Tools ▸ Locate PHP Linter…` and `Tools ▸ Start MCP Server` were raised as candidates and neither
    included nor ruled out.
- **Suppressible and escapable (Q4).** A persisted **"don't show this again"** checkbox — a new QSettings
  bool alongside the existing `lightTheme` / `windowState` / `toolbarIds` / `toolbarIconIds` keys in
  `QSettings("MDS","PGTP Editor")` — and **Escape / window-close lands in the empty app exactly as today,
  never quits.** Quitting on close would turn the modal into a gate on running the app at all.
- **No recents in any group (Q5).** Group 1 *could* have listed `.pgtp` recents today, but `recentFiles`
  is being deleted (below). Groups 2 and 3 never had a store. **A `recentProjects` store is the right
  memory for a project-centric app** (unlike recent *files*) and is recorded as a **separate, later entry
  that FQ-010 does NOT depend on**; `db/ddl_project.py::is_project_dir` already exists to validate that a
  remembered folder really is a project, so whoever builds it has its validator. The launcher ships
  recent-less and gains a resume list later without a redesign.
- **DELETE `File ▸ Open Recent` and the `recentFiles` store** (owner instruction, folded in here because
  it is what makes the launcher recent-less). Verified surface to remove:
  `ui/pgtp_document_controller.py` — `_RECENT_FILES_KEY = "recentFiles"` (:145),
  `_RECENT_FILES_MAX = 10` (:146), the `aboutToShow` wiring + initial rebuild (:280-281), the
  `recent_files` reader (:745-762), `remember_recent_file` (:764-770) and `rebuild_recent_menu` (:773);
  its **two and only two writers**, `open_file` (:444) and `save_as` (:606); the File-menu submenu itself;
  and **`tests/ui/test_open_recent.py` (12 tests, verified count)**.
- **DELETE the GUI's `args.file` open branch (double-click removal) — but KEEP `args.file` itself.**
  `main.py:198` passes `args.file` to `run_mcp_server(args.file)` as the **headless MCP server's default
  project** (`_DefaultPathProvider`, §23). So this removes **only** the GUI branch at `main.py:232-238`,
  not the argument, not the parser entry. The `file` argument's own help text (`main.py:110-115`) currently
  advertises the Windows verb and must be reworded to describe only the `--mcp` default-project use.
- **`packaging/linux/pgtp-editor.desktop` — drop the now-meaningless `%f`.** Verified: it has
  `Exec=pgtp-editor %f` and **no `MimeType=` line**, so **nothing in the repo ever registered a `.pgtp`
  association**. Nothing dangles on Linux. If the owner wired the Windows "Edit with PGTP Editor" verb by
  hand it will stop working — the repo never created it, so that is outside what this change can clean up,
  but it should be stated rather than discovered.

**Alternatives considered:**
- **A non-modal "Start" tab in `CenterStage` instead of a modal** — the honest alternative, **rejected by
  the owner ("Let's do a modal"), recorded because it is the best argument on that side.** It fits the
  existing fixed-tab pattern (§7's `raw_xml_tab_index`/`xsd_tab_index` set, with the append-only /
  tail-only-removal invariant untouched), needs **no `main.py` seam and carries no test-hanging risk at
  all** across the 49 `MainWindow`-constructing test files, and can stay open beside real work. The
  specific reason it is attractive: because `windowState` **is** restored, a modal lands on top of a fully
  restored dock/tab/toolbar layout that is a *false signal of continuity*, whereas a Start tab sits
  *inside* that layout and reads as part of it. The modal's real and decisive advantage is that it is
  unmissable — which is exactly the owner's complaint. Do not silently re-decide this either way.
- **A navigation-shortcut launcher with no persisted mode and no menu filtering** — proposed at triage and
  **overridden by the owner (Q1)**. Recorded because it is the smaller-surface reading: it needs no new
  persisted concept and touches no menu. Its rejection is what created FQ-011.
- **Keeping `Open Recent` and showing `.pgtp` recents in group 1** — rejected by the owner: recent *files*
  belong to the standalone-pgtp-editor era the project has left; recent *projects* is the memory a
  project-centric app should have, and gets its own entry.
- **Quitting the app when the modal is cancelled** — rejected (Q4): it would make the modal a gate on
  running the app, hostile to the "I just want the window open" case.

**Suggested placement:** **EXTEND §7 (App shell)** in `CONSOLIDATED_SPEC.md` — a new startup-launcher
subsection placed beside the existing `**Startup file:**` bullet (line 547), which this change rewrites.
No new top-level section: the launcher is shell behaviour, and §7 already owns startup (`_restore_theme`,
window-state restore), the `main.py` seam conventions and the QSettings key inventory this adds a key to.
**No §26 change belongs in THIS entry** — §26 changes are FQ-011's, with two exceptions that are pure
deletions of things this entry removes:
- **§26 line 5349** lists `Open Recent` in the File menu — must be struck when the submenu goes.
- **§7 lines 617-621** state the toolbar enumeration *"Skipped: … the dynamic **Open Recent** submenu
  wholesale — its children are transient per-session file entries and must never be pinnable."* That skip
  rule becomes **stale/dead** once the submenu is deleted; whoever folds this in must remove it rather than
  leave a rule guarding a menu that no longer exists.
- **§7 line 547's `**Startup file:**` statement becomes false** (the GUI no longer opens `argv[1]`) and
  needs a **Supersession Ledger row**, not a silent edit — as does the removal of Open Recent, which is a
  documented capability being withdrawn.
Reuse, do not rebuild: the launcher must dispatch to the **existing** `File`/`Schema`/`Generation` QActions
(the same actions the toolbar hosts directly per §7's "the toolbar hosts the menus' OWN QActions"), and its
modal must follow the injectable-seam + never-`.exec()`-in-tests convention every other confirmation and
dialog in this codebase already observes.

**Open questions:** Group 4's membership is explicitly **open** — the owner said *"for now"* XSD + §20, and
`Help ▸ Open Log Folder` / `View ▸ Customize Toolbar…` / `Tools ▸ Locate PHP Linter…` /
`Tools ▸ Start MCP Server` were neither included nor ruled out. Implementation-level details left to
whoever picks this up: the modal's visual shape (four labelled sections vs. four large buttons vs. a
list); the exact new QSettings key name for the suppression flag; how a suppressed launcher can be
re-invoked (a `Help ▸`-or-`File ▸` entry to reopen it was not discussed and is worth offering, since a
persisted "don't show again" is otherwise irreversible without editing settings); whether the modal is
shown before or after the persisted `windowState` is visibly restored; and the exact wording of each
group's entries (the review's naming rulings — `docs/UX_REVIEW.md` "Decide these first" — are a **later
step and explicitly out of scope here**, so avoid inventing new vocabulary the rulings will have to
re-settle).

---

## FQ-011: Persisted launch mode that filters the menu bar to the chosen workflow
**Status:** QUEUED
**Requested:** 2026-08-07
**Idea (verbatim/summarized):** "Also I don't want to see menus I can't use (eg. if I work on Path2, I
don't need generate)." The owner's answer to FQ-010's Q1 was that a launcher group choice is **a persisted
mode that filters the menu bar**, not a one-shot navigation shortcut. **Split out of FQ-010 deliberately,
at triage's recommendation and with the owner's agreement**, because the launcher can be specified
coherently on its own while "what a mode does to the menu bar" cannot be — it is the menu-reorganisation
work the owner's own scope fence for step 1 excluded. **FQ-010 is ordered FIRST; this entry depends on it**
(there is no mode to persist until something sets one).

**Problem:** With FQ-010's launcher, the user has told the app which of four workflows they are in. Nothing
consumes that. The owner wants the menu bar to stop showing commands the chosen workflow does not need,
naming `Generate` in the project workflow as the example.

**Proposed approach:** A persisted "current mode" (the FQ-010 group, stored in the same
`QSettings("MDS","PGTP Editor")` scope as `lightTheme`/`windowState`/`toolbarIds`), consumed by a single
refresh entry point that binds **visibility** of menu actions per mode. Follow the one existing precedent
exactly rather than inventing a second mechanism: `MainWindow._refresh_sandbox_affordances`
(`pgtp_editor/ui/main_window.py:3050-3075`) is *"the single 'make every X-dependent affordance match the
actual state' entry point"* and its docstring states **"Everything here binds VISIBILITY, never
enabled-state (§18.5 carve-out 2: with no live session the control is ABSENT, not greyed out)."** A
mode-filter must be one such function, called on mode change, not per-menu ad-hoc `setVisible` calls
scattered through the nine `_build_*_menu` methods.

**THE OBJECTION, RECORDED VERBATIM AND DELIBERATELY NOT SOFTENED.** Raised at triage, **overridden by the
owner — which is their call** — and preserved here because it is the strongest argument any future reader
will have against this design. Do not re-litigate it from scratch; do not treat its presence as a reason
to quietly not build the feature:
> Today the app hides on **real capability**, never on **user intent**. `_refresh_sandbox_affordances`
> binds visibility gating on `has_session` / `_configured_sandbox_params()` — facts about what the app
> *can* do. §26 states the same rule per-feature (Sandbox SQL Console is *"absent, not disabled, until the
> active project has a sandbox"*, line 5430; §18.7's sandbox DDL Explorer sibling is *"absent entirely when
> no sandbox exists (no dead controls)"*, line 5410). **Generate genuinely works in a project.** Hiding it
> because the user picked "project mode" is the app deciding the user did not mean it — a different rule
> from hiding what is unusable, and the first time this codebase would apply it. Furthermore, per
> `docs/UX_REVIEW.md` §D6, the app currently has **too little** capability-based hiding, not too much:
> seven "Not yet implemented" stubs (`Edit ▸ Cut/Copy/Paste/Delete`, `Edit ▸ Preferences...`, tree
> `Compare Selected` / `Copy Selected to...`) violate its own absent-not-disabled rule, and fixing those
> is a **cheaper win** at the same complaint ("I don't want to see menus I can't use") than building an
> intent-filter.

**An escape hatch is required, and the owner may not have weighed this.** Flagged prominently because it
is the difference between a helpful default and a trap:
- A mode is **persisted**, so a user who picks "Path 2" once loses `Generate` on **every subsequent
  launch**, with the launcher itself possibly suppressed (FQ-010's "don't show again"). There must be an
  always-reachable way to change or clear the mode from **inside** the app — not only by re-answering a
  modal that may never appear again.
- Strongly consider making the filter a **default emphasis rather than a lock**: e.g. a persistent
  "showing: Project mode — show all commands" affordance, or a "Show all commands" toggle that survives
  in the mode itself. A hidden-and-only-recoverable-through-settings command is worse than a visible one
  the user ignores.
- **`Help ▸ Manual` (F1), and whatever surface reveals/clears the mode, must never be filtered out of any
  mode** — otherwise the app can hide the only documentation explaining why commands are missing.

**Load-bearing constraints the implementer must not trip over** (verified; `docs/UX_REVIEW.md` §L is the
fuller list):
- **Hiding is safe for toolbar identity; MOVING or RENAMING is not.** `toolbar_registry.command_id_for`
  derives ids from menu label **and** menu location (`["File","Save As..."] → "file.save-as"`, §7 lines
  601-612). Merely calling `setVisible(False)` on an action changes no id — but note that `MainWindow.
  _walk_menu_actions` walks `menuBar().actions()` and a hidden action is **still enumerated**, so
  Customize Toolbar would offer commands the current mode hides. **Decide explicitly** whether the
  Available list filters by mode (and what happens to an already-pinned toolbar button whose command the
  current mode hides — the toolbar hosts the menus' OWN QActions, §7 line 627, so hiding the menu action
  affects the button directly). This interaction is the single most likely source of surprise.
- **`LEGACY_ID_ALIASES` pins two ids** — `"validate" → "tools.validate-project"` and `"generate" →
  "generation.generate-php"` — which define `DEFAULT_TOOLBAR_IDS` and key `ICON_ID_BY_COMMAND` → the
  vendored SVGs (§7 lines 661-665). `Generate PHP...` is **one of the seven default toolbar buttons**, and
  it is the owner's own example of a command to hide in project mode. So mode-filtering `Generate` hides a
  **default toolbar button** by default, on a fresh install, in the app's primary mode. Resolve this
  deliberately.
- **Do not fold this into the naming/menu-reorganisation rulings.** `docs/UX_REVIEW.md` §A2/§A3 propose
  *moving* commands between menus (Tools is a grab-bag; lint spans two menus) — every such move **breaks
  saved toolbar ids** (§L2). Mode-filtering is visibility-only and must stay independent of those moves, so
  the two can land in either order.

**Alternatives considered:**
- **Capability-based hiding only, no intent mode** (i.e. do not build this; instead fix `docs/UX_REVIEW.md`
  §D6's seven stubs so the menus stop showing commands that genuinely do nothing). **This is the
  alternative the objection above argues for, and it is the smaller, cheaper, precedent-consistent
  change.** Rejected by the owner in favour of the mode. Recorded so a future reader sees it was weighed,
  not missed — and note the two are **not mutually exclusive**: fixing the stubs is worth doing whichever
  way this entry goes.
- **Disable (grey out) rather than hide** — rejected on precedent: §18.5 carve-out 2 and
  `_refresh_sandbox_affordances` both state *absent, not disabled*. If mode-filtering greyed things out it
  would introduce a **third** posture (visible-enabled / visible-disabled / absent) into an app that has
  deliberately kept two. If the owner wants discoverability of what a mode hides, the answer is the
  "show all commands" escape hatch above, not a menu full of grey.
- **Filter by mode at launch only, without persisting** — rejected implicitly by the owner's Q1 answer
  ("persisted mode"), but noted: it would remove the trap the escape hatch exists to cover, at the cost of
  re-answering the launcher every session.

**Suggested placement:** **EXTEND §26 (Consolidated menu bar)** in `CONSOLIDATED_SPEC.md` (lines
5342-5465) as the primary home — §26 is the one place that enumerates every menu and already carries
per-entry visibility rules, so a **global** mode-filter rule belongs there, stated once, rather than
sprinkled across ten feature sections. **Also EXTEND §7** for (a) the new mode QSettings key, listed
beside `lightTheme`/`windowState`/`toolbarIds`/`toolbarIconIds`, (b) the single
`_refresh_*_affordances`-style entry point that applies it, and (c) the Customize Toolbar interaction
(§7 lines 601-683 own `_walk_menu_actions` / `_all_menu_commands` / the Available list). **CREATE nothing
new.** Whoever folds this in must reuse `_refresh_sandbox_affordances`'s shape and its
visibility-never-enabled-state rule verbatim, and must **explicitly reconcile** §26's existing
capability-based absent-not-disabled statements with the new intent-based hiding so the spec states two
distinct rules deliberately instead of appearing to contradict itself.
**Dependency: ordered AFTER FQ-010** — there is no mode until the launcher sets one.

**Open questions:** (1) **The escape hatch** — what it is and where it lives; unresolved and flagged above
as required. (2) **Per-mode menu membership** — nobody has enumerated which commands each of the four
modes shows; only `Generate` in project mode was named. That enumeration is the bulk of this entry's
design work and needs the owner, command by command or by a stated rule. (3) **Customize Toolbar
interaction** — does the Available list filter by mode, and what happens to a pinned button the current
mode hides? (4) **`Generate PHP...` is a default toolbar button** (`LEGACY_ID_ALIASES`/
`DEFAULT_TOOLBAR_IDS`) — is hiding it in project mode acceptable given it empties a default button on a
fresh install? (5) Whether the mode also affects anything **beyond** the menu bar (docks, the left-dock
tabs, the toolbar) — this entry assumes **menu bar only** and should be widened only on an explicit
decision.

---

## FQ-013: Bookmark persistence — project mode only, session-only otherwise
**Status:** PARTIALLY PROCESSED (adf9bfb) — the pure storage layer is built and deliberately UNWIRED: `db/bookmark_store.py`, `<project>/.ddlproject/bookmarks.json`, a SIBLING of settings.json rather than a `ProjectSettings` key (that struct feeds the deploy manifest, so a corrupt bookmark file can never cost the user their settings). Keys are project-relative POSIX paths with both sides resolved, so a moved or copied project resolves identically. Load NEVER rewrites, so lines beyond a temporarily shortened document return when it grows. An empty set removes its key rather than storing `[]`. Every malformed input degrades to "no bookmarks" instead of raising into a gutter click. 29 tests. **STILL TO DO:** the gutter hookup and the project-open gate, which need `main_window.py`.
**Requested:** 2026-08-07
**Note on numbering/position:** this entry and the two below it (FQ-014, FQ-015) sit **above** FQ-012 in
this file. A concurrent session appended its own FQ-012 ("Customize Shortcuts dialog") while these three
were being written; they were renumbered 013–015 to keep ids unique rather than rewrite another session's
entry. Ids are authoritative; file position here is not.
**Idea (verbatim/summarized):** The owner's ruling — *"Persistence only when in project mode, otherwise
dies with the session."* **Not the owner's original request.** This entry exists because triage of the
`List All Bookmarks` idea (now FQ-014) objected that listing bookmarks is a modest win while they
evaporate on every document load; the owner accepted that framing and split persistence out ahead of it.
**FQ-013 is ordered FIRST; FQ-014 depends on it** — listing is what persistence makes worth having.

**Problem:** Bookmarks today are **session-only AND document-scoped**, and the second half is the sharper
loss. `GutterBookmarkFoldMixin._init_gutter_bookmarks_folding` holds `self._bookmarks: set[int]` of block
numbers (`pgtp_editor/ui/editor_gutter.py:241`), and the fold-state lifecycle **resets it to an empty set
on every `setPlainText`** (`editor_gutter.py:255-257`: *"Bookmarks share the fold-state lifecycle: a new
document starts with no bookmarks"*). So a user loses every bookmark in an editor on: reopening a project,
reverting, an XSD mode switch, re-checking-out a DDL object, or simply restarting the app. Every editor in
the app is affected — the Raw XML editor, Edit XSD / Edit AutoXSD, the read-only DDL Explorer buffer, each
DDL object tab, each PHP file tab, each FQ-006 draft tab, and the `Edit code…` dialog all mix in the same
one gutter implementation. §8 of `CONSOLIDATED_SPEC.md` (line 873) states this as settled design: **"No
persistence, no list panel, no names."**

**Proposed approach:**
- **Two-tier behaviour, gated on whether a project is open.** With a §18.2 project open, bookmarks survive
  document reload **and** app restart. With no project open, behaviour is **exactly unchanged** — session
  only, wiped by `setPlainText`, no store, no file written anywhere. The projectless path must not regress
  or acquire a new store; it is the status quo by explicit decision.
- **The store already exists — do not invent one.** `<project>/.ddlproject/` is the project's own private
  directory (`ddl_project.py:57` `SETTINGS_DIRNAME = ".ddlproject"`), and
  `db/ddl_project.py::_ensure_gitignored(project_dir, entry)` (line 241 — idempotent, exact-line or
  directory-form match, never duplicates, never touches unrelated lines) is the established mechanism for
  keeping project-local private state out of git; `save_settings` calls it with `".ddlproject/"` on every
  write (line 157). Bookmarks are **personal, not shared**, so they belong inside that already-gitignored
  directory, alongside `settings.json` — a sibling file (e.g. `.ddlproject/bookmarks.json`), **not** a new
  key inside `ProjectSettings`. Keeping them out of `settings.json` matters: `ProjectSettings` is the
  project's shared configuration (connections, deploy manifest, git settings) and is read/written by
  several controllers; personal caret furniture does not belong in that schema, and mixing them means every
  bookmark toggle dirties the same file the deploy pipeline depends on.
- **Key by project-relative path.** Absolute paths do not survive a project being moved, cloned, or opened
  from a different mount (the project is explicitly expected to live on an sshfs-mounted share per §18.3),
  so the store must key each editor's bookmark set by a **path relative to the project folder** —
  the same discipline `routine_ddl_paths` already follows (`ddl_project.py:264-269`: paths are *"computed
  fresh from the whole set every time, never stored, so the numbering is always recomputable"*, POSIX-style
  `/` separators). Use POSIX separators in the stored keys so a project is portable between the Windows and
  Linux checkouts the project targets.
- **Stale line numbers must be handled explicitly, not hoped away.** A stored bookmark is a bare block
  number; if the file changed underneath (edited outside the app, pulled from git, redeployed), line N is
  now a different line or does not exist. Recommended policy, to be confirmed: **restore leniently and
  drop silently** — restore every stored line that is still within the document's block count, discard the
  out-of-range ones on load (matching the mixin's existing posture, spec §8 line 872: *"Out-of-range block
  numbers are ignored defensively"*), and do **not** attempt content-anchoring (storing the line's text and
  re-finding it) in v1. Content-anchoring is a real feature with real ambiguity (duplicate lines, moved
  blocks) and should be its own decision, not smuggled in here.
- **Which editors persist?** Only editors with a stable, project-relative identity can. Concretely: DDL
  object tabs and PHP file tabs have real files under the project; the Raw XML editor has the working-copy
  `.pgtp` path (`ProjectSettings.pgtp.working_copy_path`, `ddl_project_controller.py:266-268`); Edit XSD /
  Edit AutoXSD have their schema files. The **read-only DDL Explorer buffer** and **FQ-006 draft fragment
  tabs** have no persistent file at all (a draft is explicitly a scratch buffer with no save path), and the
  **`Edit code…` `CodeEditorDialog`** is a modal over an event body inside the XML, not a file. Those three
  should stay session-only even in project mode — flagged as an open question below rather than assumed.
- **Write timing.** Prefer writing on a **quiet, coarse trigger** (project close / app close, or a debounce)
  over writing on every `toggle_bookmark` — the mixin's toggle is a hot, single-click gutter gesture
  (`editor_gutter.py:202`, plus the double-click target at `:221`), and syncing a file write into it makes a
  UI gesture do disk I/O.

**Alternatives considered:**
- **Persist unconditionally, project or not** (e.g. in the `QSettings("MDS","PGTP Editor")` scope that
  already holds `lightTheme`/`windowState`/`toolbarIds`) — rejected by the owner's ruling. Worth recording
  *why the ruling is defensible* so it is not re-litigated: without a project there is no defined root to
  key paths against, so a global store would have to key absolute paths and would accumulate entries for
  arbitrary files the app was pointed at once, forever, with no owner and no cleanup rule.
- **A new key inside `ProjectSettings`/`settings.json`** — rejected above (shared config vs. personal state;
  dirtying the deploy pipeline's file on a caret gesture).
- **Content-anchored bookmarks** (store the line text, re-find on load) — deferred, not rejected: it is the
  right answer to the stale-line problem eventually, but it introduces duplicate-match ambiguity that needs
  its own decision. v1 restores by line number and drops out-of-range entries.

**Suggested placement:** EXTEND **§8** (`CONSOLIDATED_SPEC.md` lines 848-873, which owns the bookmark
state, its `setPlainText` reset and the Bookmarks menu) as the primary landing section, with a **secondary
note in §18.2** for the new `.ddlproject/` sibling file and its `_ensure_gitignored` registration. No new
section: this is a storage-lifecycle change to an already-fully-specified feature, reusing
`_ensure_gitignored` and the `.ddlproject/` directory verbatim. **Required surgical amendment:** §8's
closing sentence *"No persistence, no list panel, no names."* (line 873) becomes conditionally false in its
first clause — persistence exists **in project mode only**; "no names" stays true, and "no list panel"
stays true until FQ-014 lands. Amend the clause, do not delete the sentence, and add a Supersession Ledger
row (the "session-only, per-document" wording is stated as settled design in §8, at line 848, at line 1715
and in the §26 shortcut table at line 5480 — all four sites need to agree afterwards).

**Dependency / ordering:** ordered **before FQ-014**. **One correction to the dispatch brief, recorded so
it is not implemented wrong:** the brief called this "a dependent of FQ-010's mode concept." As designed
above it is **not** — the gate is *"is a §18.2 project open"*, a capability fact available today
(`MainWindow._ddl_project_folder` / `_ddl_project_settings`, `DdlProjectController._folder`/`._settings`),
and it needs neither FQ-010's launcher nor FQ-011's persisted launcher mode to exist. If the owner meant
the **launcher** mode ("the user picked Path 2 in the launch modal") rather than "a project is open", then
this entry does depend on FQ-010/FQ-011 and the gate is user intent rather than capability — which would
also put it on the wrong side of the app's own absent-on-capability-not-intent rule that FQ-011's recorded
objection is about. **See open question (1).**

**Open questions:**
1. **Which reading of "project mode"** — *a §18.2 project is open* (this entry's assumption; no dependency
   on FQ-010/FQ-011) or *the FQ-010 launcher mode is "project"*? These are different gates with different
   dependencies. Confirm before implementing.
2. **Do the three identity-less editors persist?** The DDL Explorer read-only buffer, FQ-006 draft fragment
   tabs, and the `Edit code…` dialog have no project-relative file to key against; this entry assumes they
   stay session-only.
3. **Write timing** — on project/app close, on a debounce, or on every toggle.
4. **Stale-line policy** — this entry recommends restore-in-range / drop-out-of-range with no content
   anchoring; confirm.
5. Whether the stored set should be **pruned** when a keyed file no longer exists in the project (the way
   `resolve_ids` drops unknown toolbar ids, §7).

---

## FQ-014: `List All Bookmarks` — the active editor's bookmarks as clickable Audit rows
**Status:** QUEUED
**Requested:** 2026-08-07
**Idea (verbatim/summarized):** *"And bookmarks as is now should go in a Bookmarks menu (invoke feature
triage, because I'd like a **List all bookmarks**, that inserts the list of all bookmarks into
audit/problems clickable)."* Raised while the owner was designing an **Editor menu bar** (a second, fixed
menu bar above the central pane holding per-tab editing commands) onto which the existing Bookmarks menu
moves largely as-is. **This entry is scoped to the new command and its Audit rows only** — the Editor menu
bar itself, moving Bookmarks onto it, and the wider menu reorganisation (FQ-010/FQ-011) are all out of
scope here. **Ordered AFTER FQ-013** (bookmark persistence): triage argued, and the owner accepted, that persistence is what makes
listing worth having.

**Problem:** Bookmarks today are only reachable **sequentially** — F2 / Shift+F2 step through them one at a
time (`next_bookmark`/`prev_bookmark`, wrap-around) and the only overview is the gutter tags, which are
visible for the currently scrolled viewport only. In a several-thousand-line Raw XML buffer the user cannot
see how many bookmarks exist, what is at them, or jump to the fourth one directly. The Bookmarks menu
(`FindValidateController.build_bookmarks_menu`, `pgtp_editor/ui/find_controller.py:231-277`) has exactly
four entries — Toggle (Ctrl+F2), Next (F2), Previous (Shift+F2), Clear All (no shortcut, deliberately) —
and no overview command. §8 records the absence as design: *"No persistence, no list panel, no names"*
(`CONSOLIDATED_SPEC.md:873`).

**Proposed approach.** All of the below was argued from the code and **accepted by the owner** on
2026-08-07; treat it as settled, not as suggestion:
- **Scope: the ACTIVE editor only.** Not every open editor. Reasons, in order of weight: (a) every other
  bookmark command already resolves exactly one document via
  `FindValidateController.active_bookmark_editor()` (`find_controller.py:352-381`), so a one-editor list is
  the consistent sibling; (b) **`MainWindow._on_audit_item_clicked` (`main_window.py:1228-1256`) has no
  click route today for the DDL Explorer read-only buffer tab, for an FQ-006 draft fragment tab, or (of
  necessity) for the `Edit code…` modal** — it routes on the single `UserRole+1` value (`"xsd"` →
  `_xsd_ui.reveal_line`; `LINT_AUDIT_TARGET` → `_php_tabs.navigate_to`; a **tuple** → `_navigate_to_ddl_object`;
  **anything else → Raw XML**), so a cross-editor list would need three new routing targets and its fallback
  would silently navigate the *wrong document*, the exact failure the `[Check]` branch's comment warns
  against; (c) a modal dialog's bookmarks cannot be navigated to at all once it closes.
- **Payload: Find All's two-role shape, unchanged.** Line on `Qt.ItemDataRole.UserRole`, the existing
  target discriminator on `UserRole+1` (`find_controller.py:452-453`). **Note the dispatch brief was wrong
  and this was verified:** `[Find]`'s `UserRole+1` is the **string `"raw"` or `"xsd"`**, not a
  `DdlObjectRef.key`. Since scope is the active editor, this command reuses the *same* discriminator
  vocabulary the click router already understands for whichever editor is active — no new routes, no
  `UserRole+2`, no per-row editor label.
- **A new `[Bookmark] ` prefix — as a MODULE CONSTANT.** Not a reuse of `[Find]`: the two would clear each
  other (`clear_find_results`, `find_controller.py:498-506`), and `[Find]`'s `UserRole+1` vocabulary is
  "raw|xsd" only, so bookmark rows from a DDL object or PHP tab would carry an incompatible payload under
  one prefix — precisely the overloading §7's prefix reservation exists to prevent. §7's rule (`:481-485`)
  forbids a fourth **SQL-ish** prefix; `[Bookmark]` is not SQL-ish, so it is not blocked. Per
  `docs/UX_REVIEW.md` §C1 it must be a named constant beside `_FIND_RESULT_PREFIX` / `_VALIDATION_PREFIX`
  — **do not repeat `[Project]`'s mistake of typing the literal inline in ten places**.
- **Row grammar: Find All's, verbatim.** `f"{_BOOKMARK_PREFIX}line {line}: {preview}"`, mirroring
  `find_controller.py:451`; a blank/whitespace-only line renders as just `line N`. `UX_REVIEW` §C2 is
  already pushing the nine prefixes toward one grammar — do not add a tenth variant.
- **Clears its own rows first,** exactly as `find_all` calls `clear_find_results()` before streaming
  (`find_controller.py:425`), via a `startswith(_BOOKMARK_PREFIX)` bottom-up sweep in the same shape as
  `clear_find_results`/`clear_validation_results` (`:498`, `:508`). Repeat invocations replace, never stack.
- **Trailing count summary row, roles-less** — `[Bookmark] 7 bookmark(s)`, matching `_finish_find_all`'s
  summary (`find_controller.py:462-465`, appended with *"no line data -> clicking is a no-op"*).
  Consistency with Find All was judged to beat saving one row.
- **Empty case: a roles-less row, not silence** — e.g. `[Bookmark] no bookmarks in <editor>`, plus a status
  message. Find All always emits its summary even at zero, so a command that produced literally nothing
  would be the odd one out and would read as a broken command.
- **No shortcut,** matching `Clear All Bookmarks`. This command produces a report; F2/Shift+F2 already own
  stepping.
- **Reveals the Audit dock.** On the one precedent that speaks to it: `coherence_controller.py:387-390`
  calls `self._find_all(token)` then `self._show_audit_dock()`, commented *"reveal the panel in case a prior
  DB check left it hidden"*. `MainWindow._show_audit_dock` already exists as an injected callback
  (`main_window.py:1084-1086`, injected into `CoherenceController` at `:725`) — inject it the same way
  rather than reaching for `self.audit_dock` from a controller. Without this the command is a silent no-op
  whenever the dock is hidden.
- **Snapshot, not a live view.** Listing is strictly on demand; toggling a bookmark afterwards does not
  re-sync the rows.
- **Hook the existing bookmark reset to sweep stale `[Bookmark]` rows.** `editor_gutter.py:255-257` empties
  `self._bookmarks` on every `setPlainText`; without a sweep the Audit rows outlive the bookmarks they
  describe and point at line numbers that may no longer mean anything. **This stays necessary even after
  FQ-013**, because projectless editors still wipe on reload and FQ-013's restore is in-range-only. Note the
  gutter mixin is deliberately Qt-widget-level and knows nothing about the Audit panel — do not give it a
  reference to one; expose this as a signal/callback the controller that owns the rows subscribes to, the
  same injected-callback decoupling the rest of the app uses.

**Alternatives considered:**
- **All open editors rather than the active one** — rejected on the three grounds above (three missing click
  routes, a wrong-document fallback, an unnavigable modal), and because per-row editor labels would force
  the `[Lint]` three-role pattern where the two-role one suffices.
- **Reuse the `[Find]` prefix** instead of adding a tenth — rejected: mutual clearing plus an incompatible
  `UserRole+1` vocabulary under one prefix.
- **A dedicated bookmarks list panel / left-dock tab** instead of Audit rows — not proposed by the owner and
  not recommended (recorded so it is not re-proposed): the Audit dock already *is* the app's list-of-locations surface with a working click
  router, three precedents (`[Find]`, `[Check]`, `[Lint]`) and a clear-scope convention. A new panel would
  duplicate all of that for one command.
- **Doing this WITHOUT persistence** (the original request) — superseded: triage objected that a list of
  things that evaporate on document load is a modest win, the owner agreed, and persistence became FQ-013
  and was ordered first.

**Suggested placement:** EXTEND **§8** (`CONSOLIDATED_SPEC.md:848-873` — the Bookmarks menu and its four
actions) for the command itself, **and §7's Audit-prefix table** (`:470-485`) for the new `[Bookmark]`
prefix, which must be added to that table with owner/meaning/state like the three reserved ones. No new
section. **Required surgical amendment:** §8's closing *"No persistence, no list panel, no names."* (line
873) — this entry makes **"no list panel" false**; FQ-013 makes "no persistence" conditionally false;
**"no names" stays true.** Amend the clause, do not delete the sentence. Also update the §26 consolidated
menu listing (`:5377-5378`, which enumerates the Bookmarks menu's four actions) and the §26 shortcut table
(`:5480`) so the menu's membership does not silently diverge. Reuse `find_all`'s row construction, the
`clear_*_results` sweep shape, `active_bookmark_editor()` and the injected `_show_audit_dock` verbatim —
build no new mechanism.

**Open questions:** none blocking; every decision above was resolved with the owner. Left to the
implementer: the exact wording of the empty-case and summary rows; whether the command lives on the
Editor menu bar's Bookmarks menu (its intended home) or the current main-menu-bar Bookmarks menu if that
menu bar has not landed yet — it must work in either host, since this entry is deliberately independent of
that reorganisation; and how the stale-row sweep is plumbed (signal vs. injected callback) without giving
the gutter mixin knowledge of the Audit panel.

---

## FQ-015: A `Select` menu on the Editor menu bar, with `Select All` (Ctrl+A) as a discoverable entry
**Status:** QUEUED
**Requested:** 2026-08-07
**Idea (verbatim/summarized):** The owner wants a **Select menu** on the new Editor menu bar, prompted by:
*"actually... select all is quite important Ctrl+A should do that."* Contents: `Select All` (Ctrl+A) plus
the two existing block-selection commands moved off the Edit menu. Unrelated to the bookmark work
(FQ-013/FQ-014) beyond sharing the same Editor-menu-bar review; queued as its own entry because it is
small and independently implementable.

**Problem — this is a discoverability gap, not a missing behaviour.** Verified: **nothing in the app binds
or steals Ctrl+A.** The only `Ctrl+Shift+A` binding is `Select Parent Block` (`main_window.py:1443-1444`)
and there is no clash, so `QPlainTextEdit`'s built-in select-all already works in every editor today. What
is missing is the **menu entry** — a user scanning the menus finds `Select Enclosing Block` and `Select
Parent Block` but no `Select All`, and the two that do exist are buried in the Edit menu below Find /
Replace / Replace All with no grouping.

**A REAL BUG THIS SURFACES — the most valuable finding in this entry.** Both existing selection actions are
**hard-wired to the Raw XML editor at menu-build time**, unlike every other per-tab command:

    select_enclosing_action.triggered.connect(self.center_stage.xml_editor.select_enclosing_block)
    select_parent_action.triggered.connect(self.center_stage.xml_editor.select_parent_block)
    # main_window.py:1437-1447 — bound to the widget, not resolved at trigger time

Contrast `build_bookmarks_menu`, whose docstring makes the rule explicit: *"Each action resolves the target
editor at TRIGGER time via `active_bookmark_editor`, not at build time"* (`find_controller.py:231-244`), and
`active_find_bar` (`:320`), which dispatches the same way. So **Ctrl+Shift+B / Ctrl+Shift+A from a PHP tab,
a DDL object tab or a draft tab act on the Raw XML document**, not on the tab the user is looking at.
`CodeEditor` has its own `select_enclosing_brackets` (`code_editor.py:372-387`) and additionally handles
Ctrl+Shift+B **in its own `keyPressEvent`** (`:389-399`, with the comment that this is *"in addition to the
QShortcut"* so the behaviour is reachable when the key event goes straight to the editor) — meaning there
are **two competing handlers for one chord**, one tab-correct and one not. Moving these actions onto a
per-tab Editor menu bar makes the mismatch structural and it should be fixed as part of this work, by the
established pattern: an `active_selection_editor()`-style trigger-time dispatch mirroring
`active_bookmark_editor()`. Note `select_enclosing_block` (XML tag spans, `xml_editor.py:920`) and
`select_enclosing_brackets` (bracket pairs, `code_editor.py:372`) are **different methods with different
semantics** on the two editor families, so the dispatch must map to each editor's own method rather than
assume one name.

**Proposed approach:**
- **`Select All`** — a new menu entry for behaviour that already works. Prefer wiring it to the active
  editor's own `selectAll()` through the same trigger-time dispatch as the two block commands (rather than
  relying solely on the widget's built-in binding) so that the menu entry and the chord act on the same
  document, and so the action can be gated if a mode ever needs to.
- **Move `Select Enclosing Block` (Ctrl+Shift+B) and `Select Parent Block` (Ctrl+Shift+A)** from the Edit
  menu into the new Select menu, **and fix their build-time binding to trigger-time dispatch** as above.
- **Do not change any shortcut.** All three chords keep exactly their current keys (Ctrl+A is new but
  matches the platform default the widget already implements).

**Alternatives considered:**
- **Add `Select All` to the existing Edit menu and skip the Select menu** — the smaller change, and worth
  putting to the owner if the Editor menu bar slips: it closes the actual discoverability gap on its own.
  Rejected as the primary proposal because the owner is explicitly grouping per-tab editing commands onto
  the Editor menu bar, and a three-item Select menu is exactly that grouping.
- **Leave the two block commands on the Edit menu and put only `Select All` on the Select menu** — rejected
  as the worst of both: two selection commands in two different menu bars.
- **Fix the build-time-binding bug as a separate BUGFIX_QUEUE item** — deliberately not proposed here;
  triage does not touch that queue. It is recorded in this entry because moving these actions is what makes
  the mismatch structural, and whoever moves them will be editing exactly those lines.

**Suggested placement:** EXTEND **§8** (which owns `XmlEditor`'s selection commands and the shared editor
behaviours) plus the **§26 consolidated menu + shortcut tables** (`CONSOLIDATED_SPEC.md:5377-5378` area and
the shortcut table at `:5480`), whose Edit-menu membership and the `Ctrl+Shift+B` / `Ctrl+Shift+A` rows
(`manual.md:2112-2113` mirrors them) both change. **The spec's per-tab-dispatch rule already exists** —
§8's "the menu follows the active editor tab" and the `_active_bookmark_editor` precedent — so the fix is
an application of a stated rule, not a new one; whoever folds this in should note that the two selection
actions were **never** covered by it. No new section. The Editor menu bar as a container is out of scope
for this entry — if it has not landed, the Select menu's three actions can be built on the existing menu
bar and moved later, since the trigger-time dispatch is what makes them host-independent.

**Open questions:**
1. **Ctrl+A in the read-only editors must be confirmed in the running app before it is spec'd as
   universal.** The DDL Explorer buffer (`ddl_editor_panel.py:71`) and Raw XML in Caption Mode
   (`center_stage.py:301`) are read-only via `setReadOnly(True)`, which in Qt keeps the selectable text
   interaction flags — so select-all is *expected* to work — but this entry deliberately does not assert it.
   Verify (and add a test) rather than documenting an assumption.
2. **Does the Select menu get anything else?** Only these three are named. If more selection commands are
   wanted (select line, expand/shrink selection), that is a separate decision.
3. **Is `Select All` gated in Caption Mode?** The precedent is split: bookmarks are deliberately **not**
   gated (a UI overlay), while Find/Replace **are** (Caption Mode owns Ctrl+F/Ctrl+R). Selecting text in a
   read-only editor harms nothing, so the recommendation is **not gated** — confirm.
4. Whether fixing the build-time binding should also **retire `CodeEditor.keyPressEvent`'s duplicate
   Ctrl+Shift+B handler**, or keep it (it exists because QShortcut activation is unreliable under the
   offscreen test platform, so removing it may break tests — check before touching).

---

## FQ-012: Customize Shortcuts dialog — list every menu command and rebind its keyboard shortcut
**Status:** QUEUED
**Requested:** 2026-08-07
**Idea (verbatim/summarized):** "I would like to have a keyboard shortcut setting screen, where I can
decide which action under which keyboard goes. List all menupoints and already defined shortcuts and let
me rewire them." Converged through direct conversation with the requester (three clarifying questions
asked and answered) plus a code-verification pass; this entry records the settled design, not an open
elaboration.

**Problem:** There is no way to rebind any keyboard shortcut. Shortcuts are defined **inline as literal
strings at each action's construction site** — there is NO central registry and no customization UI.
~16 menu-action shortcuts are set via `.setShortcut()` scattered through the `_build_*` methods, e.g.
Open `Ctrl+O` (`pgtp_editor/ui/main_window.py:1331`), Save `Ctrl+S` (:1369), Save As `Ctrl+Shift+S`
(:1372), Close `Ctrl+W` (:1381), Find… `Ctrl+F` (:1414), Find Next `F3` (:1418), Find All `Ctrl+Shift+F`
(:1422), Replace… `Ctrl+R` (:1426), Replace All `Ctrl+Alt+Return` (:1430), Select Enclosing Block
`Ctrl+Shift+B` (:1438), Select Parent Block `Ctrl+Shift+A` (:1444), Manual `F1` (:3627); plus Go To XSD
`Ctrl+L` (`pgtp_editor/ui/xsd_controller.py:210`), Toggle Bookmark `Ctrl+F2` / Next Bookmark `F2` /
Previous Bookmark `Shift+F2` (`pgtp_editor/ui/find_controller.py:249/255/261`). All literal strings, no
`QKeySequence.StandardKey`. The user wants a screen listing all menu points with their current shortcuts,
letting them rewire the bindings — a facility that does not exist in any form today.

**Key finding (drives the reuse story):** the "list all menu points and their shortcuts" enumeration the
request needs **already exists and must not be rebuilt.** `pgtp_editor/ui/toolbar_controller.py::
collect_menu_commands()` (~line 178) + `_walk_menu_actions()` (~line 196) do a depth-first walk of the
menu bar yielding `(command_id, label, QAction)` for every LEAF command, producing `_menu_command_pairs:
list[tuple[str,str]]` (id, label) and `_menu_commands: dict[str, QAction]`. Stable ids come from
`toolbar_registry.py::command_id_for()` (~line 76) via `slugify()` on the menu path (`["File","Save
As..."]` → `"file.save-as"`); display labels from `menu_path_label()` (~line 78, → `"File › Save As"`).
Each QAction's current binding is readable directly via `.shortcut()`/`.shortcuts()`. This is exactly the
enumeration the request needs, built for the Customize Toolbar / BUG-027 work ("the toolbar's command
universe IS the menu bar").

**Four shortcuts are NOT menu actions — window-scoped `QShortcut` objects, and are handled specially
(see settled decision 1):** Ctrl+Z project-history undo (`main_window.py:517`), Ctrl+Y redo (:519), and
the DUAL-PURPOSE Ctrl+F caption-filter (:386) / Ctrl+R caption-replace (:390) which are mode-gated — they
mean Find/Replace normally but are repurposed in Caption mode (§13). `find_controller.py:311` documents
the current conflict-avoidance approach ("disabling a QAction disables its shortcut, so there is no
ambiguous-shortcut conflict") — Caption mode temporarily disables the Edit-menu Find/Replace actions
(`find_controller.py:313-316`) so the caption-filter QShortcuts win. There is **NO general
duplicate-shortcut detection anywhere in the codebase** — decision 2 requires building it from scratch.

**Proposed approach:**
- **Architectural core (the real work — flag this prominently).** Shortcuts are currently set inline at
  construction with no central source of truth, so rebinding requires INVERTING that model:
  (a) capture each editable command's DEFAULT shortcut (read `.shortcut()` off the enumerated QActions
  right after menus are built, before any override); (b) load a user-override map from QSettings; (c)
  apply overrides in a CENTRAL pass AFTER all menus/controllers are built — calling `QAction.setShortcut()`
  for each overridden command. The dialog is the easy half; this central default-capture + override-apply
  pass is the load-bearing change and the main implementation risk. A pure, Qt-free resolve/serialize
  helper (like `resolve_icon_assignments`) should hold the map logic so it is testable without widgets.
- **Persistence — mirror the FQ-004 icon-assignments shape exactly.** The Customize Toolbar feature
  persists `"toolbarIds"` (`toolbar_controller.py:87`, list/comma-string tolerant, `_restore_ids()`:245 /
  `_save_ids()`:264), and FQ-004 persists a per-command-id map `"toolbarIconIds"` as `"command_id=icon_id"`
  strings (`toolbar_registry.py:137`, `serialize_icon_assignments()`:142 / `parse_icon_assignments()`:152 /
  `resolve_icon_assignments()`:173 — the latter pruning against known commands). A shortcut-override map
  keyed by command_id (new key e.g. `"shortcutOverrides"`, `"command_id=Ctrl+G"` strings, pruned against
  known command ids on load the way `resolve_icon_assignments` prunes) mirrors that serialize/parse/
  resolve-and-prune structure exactly. Back-compat: a saved settings file with no overrides simply keeps
  each command's captured default.
- **The dialog** — "Customize Shortcuts…", under the **View** menu, sibling to the existing "Customize
  Toolbar…". A table (one row per editable command) rendering the `menu_path_label()` "File › Save As"
  labels from the existing `_menu_command_pairs`, each row showing the current binding + an editable
  key-capture widget (a `QKeySequenceEdit`-style capture). Include per-row "reset to default" and a global
  "restore all defaults" — trivial once the captured defaults from (a) exist. Reuse
  `pgtp_editor/ui/customize_toolbar_dialog.py`'s (~line 48) label-rendering and headless test-seam
  architecture (`set_ids()`, `result_ids()`, `selected_ids()`, `assign_icon()` — programmatic
  setters/getters that avoid modal pickers) so tests never reach a modal (§30). Add a parallel accessor
  for the id→shortcut override map so the assignment is unit-testable the same headless way.
- **Reuse, do not rebuild:** `collect_menu_commands()` / `_menu_command_pairs` / `command_id_for()` /
  `menu_path_label()` for enumeration and stable ids; the FQ-004 icon-assignments QSettings pattern for the
  override map; `customize_toolbar_dialog.py`'s two-list/label/test-seam shape for the dialog.

**Three settled decisions (all three open questions resolved directly with the requester):**
1. **The 4 non-menu / context-gated shortcuts appear as read-only, greyed "reserved" rows.** Ctrl+Z/Y
   history and the dual-purpose Ctrl+F/R caption-mode keys are shown in the list with a "reserved —
   context-dependent" note so the user can SEE they exist and why they cannot be rebound, but the editor
   does not attempt to rewire a dual-meaning key in v1. Only the ~16 enumerable single-purpose menu-action
   shortcuts are editable. Confirmed: "Show as read-only 'reserved' rows."
2. **Conflict policy: warn + reassign (steal), user's choice.** When the user assigns a key already bound
   to another action, the editor flags it inline ("Ctrl+S is already bound to Save") with a visible
   conflict indicator BEFORE commit; if the user proceeds, the other action's binding is cleared and the
   key moves — never a silent double-binding (the ambiguous-Qt-behavior / silent-wrong class this project
   refuses). This requires building duplicate-shortcut detection from scratch (none exists today).
   Confirmed: "Warn + reassign (steal), your choice."
3. **Placement: a standalone "Customize Shortcuts…" dialog under the View menu, sibling to the existing
   "Customize Toolbar…"** — NOT the `Edit ▸ Preferences…` stub. That stub is currently dead, wired to
   `_not_implemented` (`main_window.py:1460`), and stays dead for now; the requester explicitly chose
   "Under View." This parallels the existing customization surface rather than starting a general
   Preferences container. Note for whoever implements: keep this a second single-purpose customization
   dialog under View, NOT a general settings container. Confirmed: "Under View."

**Alternatives considered:**
- **Making the 4 context-gated/window-scoped shortcuts (esp. the dual-purpose Ctrl+F/R) rebindable in
  v1** — rejected by the requester as read-only-reserved instead, because a key that means two different
  things by context (Find vs caption-filter) cannot be represented in a one-command-one-key table without
  its own design; deferred rather than half-built.
- **Hiding those 4 entirely** — rejected: showing them read-only tells the user they exist and why they
  are locked, which is more honest than a silently-incomplete list.
- **Blocking conflicting bindings outright, or allowing silent duplicates** — both rejected in favor of
  warn+steal (block = too many clicks to reshuffle; allow-duplicate = ambiguous Qt behavior, the exact
  silent-wrong class the project refuses).
- **Implementing the `Edit ▸ Preferences…` stub as an app-global Preferences container hosting this** —
  considered (the stub exists and is the "natural" home) but the requester chose a focused standalone
  dialog under View instead, sibling to Customize Toolbar; the Preferences… stub stays dead for now.

**Suggested placement:** EXTEND **§27 (Consolidated keyboard shortcuts, `CONSOLIDATED_SPEC.md` line
~5469)** — which currently documents every shortcut as a FIXED binding (the master 16+ binding table) —
to describe user-rebindable shortcuts, the override-map persistence, the central default-capture/apply
pass, and the reserved-rows carve-out for the 4 non-menu/context-gated shortcuts. **AND EXTEND §26
(Consolidated menu bar, line ~5342)** to add the new View-menu "Customize Shortcuts…" entry beside
"Customize Toolbar…" (§26's View menu currently ends `☐ Light Theme, — , Customize Toolbar…`, spec line
~5372). A **Supersession Ledger row is warranted** since §27 presently presents shortcuts as fixed
bindings and this overturns that. Not a new top-level section — it extends the existing menu/shortcut
sections. Verified greenfield: no customization/rebinding feature is mentioned, planned, or deferred
anywhere in §26/§27, and (verified) no concurrent-session implementation or committed files exist for it.
Reuse `collect_menu_commands()`/`command_id_for()`/`menu_path_label()`, the FQ-004
`toolbarIconIds` serialize/parse/resolve-and-prune pattern, and `customize_toolbar_dialog.py`'s test-seam
shape rather than building parallel mechanism.

**Open questions:** none blocking — the three load-bearing decisions (reserved-row scope, conflict policy,
placement) are resolved above. Implementation-level details left to whoever designs/builds it: the exact
QSettings key name and serialized shape (recommend mirroring `toolbarIconIds` — `"command_id=Ctrl+G"`
strings under e.g. `"shortcutOverrides"`); the precise key-capture widget; and whether the reserved rows
also display their (fixed) bindings for reference.

---

## FQ-016: A second, fixed **Editor menu bar** above the central pane — and the dissolution of the Edit menu
**Status:** QUEUED
**Requested:** 2026-08-07
**Scope note (read first):** this is the largest item of the slow UX review (`docs/UX_REVIEW.md`). It was
**deliberately split in two at triage**: this entry owns the Editor menu bar, the Edit-menu dissolution, the
always-visible `FindReplaceBar`, and the toolbar/shortcut fallout. **FQ-017 owns the Caption Management
half** (deleting the caption modal, the permanent caption bar and its new buttons) — see that entry's
rationale for why the caption work is a genuinely separable unit and not a sub-bullet here.
**Related, already-queued parts of the same design — reference, do not re-specify:** **FQ-015** (the
`Select` menu and the build-time-vs-trigger-time selection-binding bug), **FQ-014** (`List All Bookmarks`),
**FQ-013** (bookmark persistence). **FQ-017** is a hard dependency for one ruling below (it deletes the two
caption-mode `Ctrl+F`/`Ctrl+R` `QShortcut`s that today collide with the Edit-menu bindings).

**Idea (verbatim/summarized):** The owner settled, over several rounds, that per-tab editing commands
belong on a **second, fixed menu bar directly above the central pane** — *"that's not a toolbar, that's a
menubar. Toolbar is just a collection of favourite commands."* Fixed = the app decides its contents; it is
not user-composable. Its menus: **History** (`History…`, `Undo`, `Redo`, in that order — *"everyone uses
Ctrl+Z/Ctrl+Y anyway"*), **Select** (FQ-015), **Parsing** (`Auto Parse XML` plus mode-dependent checking —
*"if I'm editing a DDL, Parsing should have menu for plpgsql check, or php lint, or validate xml"*),
**Bookmarks** (the existing four plus FQ-014's `List All Bookmarks`). Correspondingly, commands are
**evicted from the window's Edit menu**: the whole Find/Replace family (*"Find unpinnable is fine"*),
`Cut`/`Copy`/`Paste`/`Delete` (*"I don't know anyone who uses menu for Ctrl+C/V/X so that can also go"*)
and `Preferences...` (*"Preferences can go"*). And the Find/Replace bar becomes **permanently visible in
its expanded form** in every editor — *"That section must be always visible… not the results, just the
fields. no new feature."* — with `Ctrl+F`/`Ctrl+R` demoted to **focus** actions and **Escape returning
focus to the editor** instead of hiding the bar. Accepted cost, in the owner's words: *"this takes up a bit
of space, but more natural to use."*
**These are rulings, not proposals.** Triage challenged only where a ruling collides with the code; every
such collision is recorded below under its own heading and none of them contradicts the owner's intent —
they are consequences that need one more decision each.

**Problem:** Two distinct complaints, one structural cause.
1. **The window menu bar mixes window-global and per-tab commands with no visible boundary.** `Edit` today
   holds project-history `Undo`/`Redo`/`History…` (which act on the **project snapshot** stack), four
   dead stubs, the per-tab Find/Replace family (routed by `FindValidateController.active_find_bar()`,
   `find_controller.py:320-350`), two selection commands that are **wrongly** window-global (FQ-015), and a
   §9 parsing toggle. Nothing on screen tells the user which of those follow the tab they are looking at.
   `Bookmarks` is a correct per-tab menu (`find_controller.py:231-244`: *"Each action resolves the target
   editor at TRIGGER time via `active_bookmark_editor`"*) sitting in the window bar next to window-global
   menus. A user cannot tell the two classes apart because the container does not distinguish them.
2. **Find/Replace is modal-feeling and its state is invisible.** `FindReplaceBar` hides itself on
   construction (`find_replace_bar.py:81`), `show_find()` hides the replace row while `show_replace()`
   shows it (`:100-112`), and `Escape` hides the whole bar (`:126-131`). So the user cannot see whether a
   search term is still armed, `Ctrl+F` and `Ctrl+R` are two different reveal gestures onto one widget, and
   the replace row's existence is a mode the user has to remember they are in.
3. **Seven "Not yet implemented" stub actions** (`_add_stub_action`) violate the app's own
   absent-not-disabled rule (`docs/UX_REVIEW.md` §D6); five of them are on `Edit`
   (`Cut`/`Copy`/`Paste`/`Delete` at `main_window.py:1404-1407`, `Preferences...` at `:1460`). Deleting them
   is deletion of dead UI, not un-wiring of working commands.

**Proposed approach**

**(a) The container.** A `QMenuBar` **inside a container widget** that becomes the central widget, with
`CenterStage` below it. A `QMainWindow` toolbar/menubar *area* spans the full window width including above
the docks, so a bar that must sit **strictly** above the central pane cannot use that area. Verified this
is cheap: `setCentralWidget(self.center_stage)` is **one line** (`main_window.py:319`), and all **534** test
references are to the `window.center_stage` **attribute**, which keeps pointing at the `CenterStage`.
**Exactly one** test asserts the coupling — `tests/ui/test_main_window.py:43`,
`assert window.centralWidget() is window.center_stage` — and it is the only test that must change.
- **Platform split, stated so it is not discovered later:** macOS absorbs the *window* menu bar into the
  system menu bar while a **child** `QMenuBar` renders inline. So on macOS the two bars will not look like
  siblings. Not a styling detail — a structural difference the spec should name.

**(b) Membership, and why `Parsing` is specifiable NOW.** The owner's *"if I'm editing a DDL"* is **not**
FQ-011's persisted launch mode. It is the **active center-stage tab's kind**, which this app already
resolves at trigger time in four places (`active_find_bar`, `active_bookmark_editor`,
`stage.active_ddl_object_panel()`, `_save_active_tab`), and which §26 already uses as a gating predicate
(`Check DDL Object` … *"disabled unless a DDL object editor tab is active, kept in sync on
`center_stage.currentChanged`"*, spec line 5435). **This is capability gating, not intent gating** — the
exact distinction FQ-011's recorded objection turns on — so it does **not** inherit FQ-011's dependency and
must not be folded into FQ-011's per-mode membership work. Triage's recommendation, offered as the answer
to the question the owner most wanted judged: **specify `Parsing` here, now, keyed to tab kind.**
- **Never call this a "mode" in the spec or the code.** The word is already carrying four meanings:
  FQ-010/FQ-011's launch mode, Caption Mode (§13), `_xsd_mode` (§11) and `DdlObjectRef.kind`. Use
  **"active tab kind"**. If FQ-011 later lands, the two filters **compose** (intent hides menus, tab kind
  hides entries within `Parsing`) and neither may be built as the other.
- **Build every `Parsing` member once and gate by `setVisible`, never create/destroy per tab.**
  `ToolbarController.collect_menu_commands()` is re-walked when Customize Toolbar opens
  (`toolbar_controller.py:281,373`), so a menu whose actions are *destroyed* per tab kind would make the
  Available list vary with the active tab and would leave `_menu_commands` holding dead QActions. Visibility
  gating keeps ids stable and matches the one existing precedent verbatim:
  `MainWindow._refresh_sandbox_affordances` (`main_window.py:3050-3075`) — *"Everything here binds
  VISIBILITY, never enabled-state."* A sibling `_refresh_editor_menu_affordances()` on
  `center_stage.currentChanged` is the shape to copy.
- **What `Parsing` actually contains, verified command by command:**
  - `Auto Parse XML` — exists, checkable, in-memory-only (`main_window.py:1450-1457`). Moves cleanly; it
    carries no legacy toolbar id.
  - `Validate Project` — exists on **Tools** (`main_window.py:3517`). **This is the owner's "validate
    xml".** ⚠️ **A FOURTH legacy id the brief did not list:** `tools.validate-project` is pinned in
    `LEGACY_ID_ALIASES` as `"validate"` (`toolbar_registry.py:61`), which makes it one of the **seven
    default toolbar buttons** *and* the key of its vendored `dialog-ok-apply` SVG via the inverse
    `ICON_ID_BY_COMMAND`. Moving it to `Parsing` changes its id to `parsing.validate-project`, so **a
    default toolbar button ships empty and iconless** unless `LEGACY_ID_ALIASES` is updated in the same
    commit — identical in kind to the `edit.undo`/`edit.redo` hazard the owner already accepted, but it was
    not on the list.
  - `Lint Current File` — exists on **Tools** (`main_window.py:3524`), with `Lint on Save` (`:3526`) and
    `Locate PHP Linter…` (`:3531`) beside it. Not legacy-pinned, so no default button breaks, but any
    **user-saved** toolbar containing `tools.lint-current-file` silently loses that button (§7's id
    derivation). **Decide explicitly whether `Lint on Save` and `Locate PHP Linter…` follow it** — leaving
    them on Tools splits lint across two bars, which is exactly the `docs/UX_REVIEW.md` §A3 complaint.
  - **plpgsql check — DOES NOT EXIST YET, and this, not FQ-011, is `Parsing`'s real dependency.** §18.5
    D3a's `Check DDL Object` / `Check without applying` are **target design**; §26 states plainly that
    *"none of them exists in `_build_database_menu` today"* (spec line 5407) and §27 that *"the **Check**
    gestures wait on `db/ddl_check.py` (D3a)"* (spec line 5486). The DDL object tab's only check path today
    is the `CheckReport` that `Apply to Sandbox` returns (`ddl_object_editor.py:538`). So: **ship `Parsing`
    with `Auto Parse XML` + the validate/lint members, and let the plpgsql-check member land with D3a.**
    ⚠️ **Spec conflict `spec-maintainer` must reconcile deliberately:** §26 assigns the two Check gestures
    to the **Database** menu. If they land on `Parsing` instead, §26's placement is overridden (ledger row
    warranted). Triage's recommendation is that they belong on `Parsing` and the Database-menu twins should
    be dropped rather than duplicated — the gestures are per-tab and the Editor bar is the per-tab bar — but
    that is an owner call, not triage's.
- **`History` mixes classes, and the owner may not have weighed it.** `History…` opens the **project
  snapshot** history navigator (`_open_history_jump_list`, `main_window.py:1400-1402`); `Undo`/`Redo` are
  the window's project-snapshot actions **except** on the Edit XSD and DDL object tabs, where §27's pinned
  carve-out 1 routes `Ctrl+Z`/`Ctrl+Y` to that editor's **own native stack** via an event filter. So a
  *project-global* command and a *conditionally per-tab* pair land on a bar the owner described as holding
  per-tab commands. Either accept the mixture and describe the bar as **"editing commands"** rather than
  "per-tab commands", or move `History…` back to a window menu. Recommend the former — renaming the concept
  is cheaper than a fourth relocation — but state it, because §26 will otherwise read as if the Editor bar
  is strictly per-tab.
- **The `Caption Management` tab is a center-stage tab, not a dock** (`center_stage.py:148-150`), so this
  bar sits above it too — where `History`, `Select`, `Parsing` and `Bookmarks` are all meaningless (§13's
  target design already disables the Bookmarks menu in Caption Mode). **Decide what the Editor menu bar
  shows on the Caption Management tab** — recommend the whole bar is hidden there, which the visibility
  refresh in (b) gives for free.

**(c) The Edit menu dissolves — with one consequence the brief did not cover.** After the moves and
deletions, `Edit` (built at `main_window.py:1390-1460`) has **no members left**: `Undo`/`Redo`/`History…` →
`History`; `Cut`/`Copy`/`Paste`/`Delete` + `Preferences...` → deleted stubs; the five Find/Replace entries
→ the permanent bar; the two selection commands → FQ-015's `Select`; `Auto Parse XML` → `Parsing`. The menu
is removed, not left empty.
- ⚠️ **DELETING THE FIVE FIND/REPLACE QActions TAKES THEIR SHORTCUTS WITH THEM.** `Ctrl+F` (`:1414`), `F3`
  (`:1418`), `Ctrl+Shift+F` (`:1422`), `Ctrl+R` (`:1426`) and `Ctrl+Alt+Return` (`:1430`) are set **only**
  on those QActions, and the permanent bar has **buttons, not shortcuts** — so the bar owning the *commands*
  does not make it own the *keys*. **Owner ruling, per key (2026-08-07), recorded per key because the three
  cases differ:**
  - **`Ctrl+F` / `Ctrl+R` survive as the focus actions** described in this entry's Idea section.
  - **`F3` SURVIVES, rebound — it must keep meaning Find Next.** *"why does F3 die? it should find next."*
    It becomes a **window-level** `QShortcut`/action routed to `active_find_bar().find_next()` — the exact
    dispatch the deleted Edit QAction already used (`find_controller.py:391-392`). **This is not a novel
    construct:** the established precedent is **`Go To XSD`, a window-level `Ctrl+L` action with no menu
    entry**, routed to the active surface (`xsd_controller.py:209-213`; §27 line 5482 records it as a
    window-level QAction, *"also in the Raw XML editor context menu"*). F3 joins that existing category of
    shortcut-without-menu-entry commands.
    - **Window-level, NOT bar-local.** The whole point of F3 is that it works while the caret is in the
      **editor**; a `keyPressEvent` on the bar would only fire once the bar already has focus, which defeats
      the purpose. Do not implement it on `FindReplaceBar`.
    - **Consequence for the toolbar walk, accepted:** a shortcut with no menu entry is **invisible to
      `_walk_menu_actions`** and therefore to Customize Toolbar. Three commands are already in that
      situation today (`Ctrl+L` Go To XSD, `Ctrl+Alt+F` Format Selection, `Ctrl+Return` Run — §27), so F3
      joins a known category rather than creating a new problem; it does mean **F3 can never be pinned**,
      alongside Find itself, which the owner has accepted (*"Find unpinnable is fine"*).
  - **`Ctrl+Shift+F` (Find All) is DELETED.** Find All writes `[Find]` rows into the Audit panel — a
    deliberate, occasional act with a visible button on the now-permanent bar; a chord earns little.
  - **`Ctrl+Alt+Return` (Replace All) is DELETED, and losing the keystroke is arguably a GAIN.** Replace All
    is a bulk edit, and it now sits immediately beside a **scope dropdown** (`"in filtered results"` /
    `"in all project"` — FQ-017) that a keystroke would bypass entirely. The project's own stated principle
    is that a broad, hard-to-inspect effect must not be one chord away (§27's irreversible-outward-effect
    rule; §18.5's same reasoning for withholding shortcuts from the Apply gestures).
  - **This also decides FQ-012's fate for them:** FQ-012's Customize Shortcuts dialog enumerates **menu**
    QActions via `collect_menu_commands()`, so **`F3` — a bare window-level shortcut with no menu entry —
    drops out of FQ-012's rebindable list and into its "reserved rows" carve-out**, exactly like `Ctrl+L`.
    Cross-reference both ways.
- `FindValidateController.set_find_actions(find_action, replace_action)` (`main_window.py:1433`,
  `find_controller.py:302-316`) exists **solely** so Caption Mode can disable those two QActions and let its
  own `QShortcut`s win. With the actions gone that seam is dead — and it is dead anyway once **FQ-017**
  deletes the caption shortcuts. Remove both together; **FQ-017 should land first or in the same commit**,
  otherwise there is a window in which nothing owns `Ctrl+F`.
- **This resolves `docs/UX_REVIEW.md` dossier E1 for free.** Today `Ctrl+R` is both `Edit ▸ Replace...`
  (whose menu row *advertises* `Ctrl+R`) and a caption-mode `QShortcut` (`main_window.py:390`); same for
  `Ctrl+F` at `:379`. The menu advertises one behaviour while the key does another. Both halves disappear.

**(d) The permanent, expanded `FindReplaceBar`.** **Nine** instances across six files (`ddl_editor_panel`,
`php_file_tab`, `ddl_object_editor`, `center_stage` ×2, plus the class) all become permanent. Four hide/show
sites change and should be **deleted, not left inert**:
- `self.hide()` at `find_replace_bar.py:81` — goes.
- `show_find()` / `show_replace()` (`:100-112`) collapse into one **focus** operation; the
  `_replace_row_widget.hide()/.show()` machinery becomes dead code (the row is always shown).
- `keyPressEvent`'s `Escape → self.hide()` (`:126-131`) becomes `Escape → self._editor.setFocus()` only.
- ⚠️ **`_prefill_from_selection` loses its home.** It runs from **both** `show_find` and `show_replace`
  (`:102`/`:109`); with no show, "select a word, press `Ctrl+F`" stops prefilling unless prefill is moved
  onto the focus path. Note it must stay distinct from `set_find_text` (`:114-119`), which the editor's
  right-click Find path uses and which prefills *unconditionally*.
- ⚠️ **`active_find_bar()` reveals the Raw XML tab as a fallback side effect** (`find_controller.py:349`).
  Revealing another tab was defensible when `Ctrl+F` *showed* a bar; as a pure **focus** gesture, focusing a
  bar by yanking the user to a different document is surprising. Decide: keep the reveal, or make focus a
  no-op on tabs with no bar (the Manual tab).

**(e) The favourites toolbar must walk BOTH bars.** `ToolbarController.build(self.menuBar(),
self.addToolBar)` (`main_window.py:766`) stores a single `self._menu_bar` and `_walk_menu_actions` roots at
`self._menu_bar.actions()` (`toolbar_controller.py:215`). Everything downstream — Customize Toolbar's
Available list, command ids, FQ-004 icon assignments, and FQ-012's shortcut list — flows from that one
walk. **Extend `build`/the walk to cover both bars (a sequence of roots, not a second mechanism)**, or every
command on the Editor menu bar becomes unpinnable and invisible to FQ-004/FQ-012. Ordering is already fine:
the container is built at `main_window.py:318`, the walk at `:766`.
- **Id changes, cumulative list** (ids derive from label **and** menu path; case-only and `...`↔`…` changes
  are safe because `normalize_label` strips ellipsis and `slugify` lowercases): `edit.undo`→`history.undo`
  and `edit.redo`→`history.redo` (**both `LEGACY_ID_ALIASES`-pinned — update in the same commit or two
  default buttons ship empty and iconless**); `tools.validate-project`→`parsing.validate-project` (**also
  pinned — see (b)**); `edit.find` loses its menu home entirely (**accepted by the owner: "Find unpinnable
  is fine"** — which means the `"find"` legacy alias and its `edit-find` SVG also go stale and should be
  handled deliberately, not left dangling); plus non-pinned moves (`edit.auto-parse-xml`,
  `tools.lint-current-file`, `edit.history`, `edit.select-*`) that silently drop off **user-saved**
  toolbars. `resolve_ids` already prunes unknown ids, so nothing crashes — buttons just vanish.

**Alternatives considered**
- **A toolbar instead of a second menu bar** — **rejected by the owner, verbatim and unambiguously**
  (*"that's not a toolbar, that's a menubar. Toolbar is just a collection of favourite commands"*). Recorded
  because a `QToolBar` would have needed no container widget and no change to `setCentralWidget`; the
  owner's distinction is a deliberate conceptual one (fixed/app-decided vs. user-curated favourites) and the
  existing customizable toolbar already occupies the other role. Do not re-decide this.
- **Keep `Edit` as a thin shell** (e.g. `Undo`/`Redo` only) so no saved toolbar id changes and `edit.find`
  survives — the smaller-blast-radius option, **rejected**: it defeats the point (the owner wants editing
  commands off the window bar) and leaves the window bar with a menu whose only members duplicate the
  Editor bar's `History`.
- **Leave the Find/Replace bar hideable and merely default it to visible** — considered, and worth naming
  because it would preserve `Escape`-to-hide, keep `edit.find` pinnable and cost nothing. **Rejected by the
  owner's explicit double-clarification** that the section is *always* visible and `Escape` returns focus.
  The honest argument on its side is screen space, which the owner already weighed and accepted.
- **Fix the seven `_add_stub_action` stubs (absent-not-disabled) as a standalone change instead** — this is
  `docs/UX_REVIEW.md` §D6 and FQ-011's recorded counter-proposal. **Not an alternative to this entry**, but
  note five of the seven die here as a side effect, so §D6's remaining surface after this lands is only the
  two tree stubs (`Compare Selected`, `Copy Selected to...`).
- **One entry covering the caption work too** — rejected; see FQ-017's opening rationale.

**Suggested placement:** **EXTEND §7 (App shell)** as the primary home for the *container* — §7 owns
`setCentralWidget`/`CenterStage`, the toolbar's menu-walk command universe (spec lines ~601-683) and the
id-derivation rules, all three of which change. **EXTEND §26 (Consolidated menu bar, lines 5342-5465)** for
the inventory: it must now describe **two** menu bars, **delete the `Edit` bullet entirely** (lines
5365-5369), move `Bookmarks` (5377-5384) and add `History`/`Select`/`Parsing`, and reconcile §26's
Database-menu placement of the D3a Check gestures against `Parsing` (see (b)). **EXTEND §27 (shortcuts,
lines 5469-5497)** for: the `Ctrl+F`/`Ctrl+R` rows becoming **focus** gestures (5475-5476); **`F3` moving out
of those rows into its own row as a window-level shortcut with no menu entry**, routed to
`active_find_bar().find_next()` — it should be described **beside `Ctrl+L` Go To XSD (5482)**, whose shape it
copies, and listed with `Ctrl+L`/`Ctrl+Alt+F`/`Ctrl+Return` as commands invisible to Customize Toolbar;
the **removal of `Ctrl+Shift+F` and `Ctrl+Alt+Return`** from the table entirely (Find All and Replace All
become button-only, each for its own recorded reason — see (c)); the `Escape` ruling; and the deletion of the
`Ctrl+F`/`Ctrl+R` Caption-Mode override row (5477 — jointly with FQ-017). Note §27's existing 5475/5476 rows
also carry the per-tab routing narrative for `Find`/`Replace`, which must be preserved and re-pointed at
`F3`'s new host rather than deleted with the Edit menu. **EXTEND §8** for the always-visible
bar as a shared editor behaviour, and §15 for the Find All routing note. **CREATE no new section** — every
piece of this lands in an existing one. A **Supersession Ledger row is warranted** for the Edit menu's
removal and for §27's `Ctrl+F`/`Ctrl+R`-as-show→focus change. Whoever folds this in must reuse
`_refresh_sandbox_affordances`'s visibility-never-enabled-state shape, `active_find_bar`/
`active_bookmark_editor`'s trigger-time dispatch, and the single `_walk_menu_actions` (widened, not
duplicated).

**Open questions**
1. **Does `Parsing` host D3a's `Check DDL Object` / `Check without applying`, overriding §26's
   Database-menu placement, or do those stay on Database and `Parsing` gets a third thing?** Triage
   recommends the former with no Database-menu twins. Owner call.
2. **Do `Lint on Save` and `Locate PHP Linter…` follow `Lint Current File` onto `Parsing`,** or does lint
   stay split across two bars?
3. **`tools.validate-project` is a pinned default toolbar button with a vendored SVG** — confirm the
   `LEGACY_ID_ALIASES` update (same treatment the owner already accepted for undo/redo), and decide what
   happens to the now-homeless `"find"` alias and its `edit-find` SVG.
4. ~~Where do the five Find/Replace shortcuts live once the Edit QActions are deleted?~~ **RESOLVED by owner
   ruling 2026-08-07 — see (c):** `Ctrl+F`/`Ctrl+R` become focus actions; **`F3` survives** as a
   window-level shortcut with no menu entry, routed to `active_find_bar().find_next()` on the `Ctrl+L`
   precedent (and therefore moves to FQ-012's reserved rows, and can never be pinned); `Ctrl+Shift+F` and
   `Ctrl+Alt+Return` are deleted.
5. **What does the Editor menu bar show on the Caption Management tab** (recommend: nothing — hide the bar)
   and on the Manual tab?
6. **Is `History…` acceptable on a bar otherwise made of per-tab commands** (recommend: yes, and describe
   the bar as "editing commands"), and does `active_find_bar`'s Raw-XML reveal survive `Ctrl+F` becoming a
   focus gesture?

---

## FQ-017: Delete the Caption Filter modal; make the caption Find/Replace bar permanent, with a scope dropdown
**Status:** PROCESSED (02e47e0) — modal, menu entry and both mode-gated shortcuts deleted (34 raw references across 13 symbols, not the 16 estimated); `MODE_LABELS` moved to its surviving consumer. The bar is permanent: find/mode/case/Filter/Clear filter over replace/scope/Replace All/status/error, `Close` gone. **The delegated "active" ruling was WRONG as stated and was corrected with proof:** clearing only the baseline left the Find field reading active, so the next re-run overwrote a hand edit with the baseline already forgotten — permanently. Implemented as `is_active()` = non-empty Find AND not `_committed`, a successful Replace All sets the flag, and any user-driven live re-run clears it to re-arm a reversible preview. Extended mode, the active-filter banner and `_confirm_unify_scope` are untouched (zero diff lines).
**Requested:** 2026-08-07
**Why this is its own entry (not a bullet in FQ-016):** the owner settled it in the same session and framed
it as *"the same logic as in editor window"*, but the coupling is a **principle, not a mechanism**. The
caption bar is a **different class** (`CaptionFindReplaceBar`, `caption_management_panel.py:649`), over a
**grid** not a text document, with a **live** replace `FindReplaceBar` does not have, its own tests, and its
own semantic decisions (below) that have nothing to do with the Editor menu bar. Splitting keeps FQ-016
implementable without dragging in the caption panel's live-preview lifecycle. **One hard interlock:** this
entry deletes the two caption-mode `Ctrl+F`/`Ctrl+R` `QShortcut`s, which FQ-016's `Ctrl+F`-as-focus ruling
needs gone. **Land this first, or in the same commit as FQ-016.**

**Idea (verbatim/summarized):** *"forget totally caption filter: delete totally the modal and the menu, keep
the find and replace bar as is now, always visible, with the same logic as in editor window."* Plus, because
deleting the modal would strand capability, the bar gains **`Replace All`**, **`Clear filter`**, and a
**scope dropdown immediately before `Replace All`** offering *"in filtered results"* / *"in all project"*,
**defaulting to filtered results** — and loses **`Close`**, meaningless once the bar is permanent.
**Two things the owner explicitly ruled OUT of scope, recorded so they are not "improved" by an
implementer:**
- **`Unify` is untouched.** Triage argued for converting `_confirm_unify_scope`
  (`caption_management_panel.py:1284`) to the same dropdown for one-idiom consistency and **was corrected
  by the owner, who is right:** *"unify is independent and important filling the fields with the same value
  as in the other. Replace replaces parts of words."* Whole-value propagation and substring editing are
  different operations, so a shared idiom is not owed. **`_confirm_unify_scope` stays exactly as it is.**
- **The active-filter banner STAYS** (`caption_management_panel.py:1474`, `"Filtered: {label} — showing
  {visible} of {total} rows"`). Not because of text filters — the permanent bar shows those plainly — but
  because it also describes **row-predicate** filters set by tree gestures (e.g. *"Field = wbs_id"*, via
  `filter_to_table` / `filter_to_table_details` / `filter_to_field`, `main_window.py:1670-1690`), which a
  text field cannot express. Retiring it would **re-create BUG-020**.

**Problem:** §13's caption find/replace exists **twice**, and the split is both a duplication and a live
shortcut bug.
- The **modal** `ui/caption_find_replace_dialog.py` is reached from `Tools ▸ Caption Filter…`
  (`main_window.py:3514`, no shortcut on the item) **and** from two window-scoped `QShortcut`s enabled only
  while Caption Mode is active (`main_window.py:379`/`:390`). Those two keys are `Ctrl+F` and `Ctrl+R` —
  **the same chords the Edit menu advertises for `Find…`/`Replace...`** — and the only thing preventing an
  ambiguous-shortcut clash is Caption Mode disabling the two Edit QActions
  (`find_controller.py:305-316`). So today **the menu advertises one behaviour while the key does another**
  (`docs/UX_REVIEW.md` dossier E1).
- The **bar** already lives inside the Caption Management tab (`caption_management_panel.py:946`) and is
  reached from a context-menu entry `"Find / Replace bar"` (`:1538`) or `show_find_replace_bar()` (`:1120`).
  Two surfaces, one job, and the user must know which one a given gesture opens.

**Proposed approach**

**(a) Delete the modal outright.** Verified surface: the module `ui/caption_find_replace_dialog.py`; its
test file `tests/ui/test_caption_find_replace_dialog.py`; **16 references in `main_window.py`**
(`_make_caption_find_replace_dialog`, `_open_caption_filter_dialog`, `_open_caption_replace_dialog`,
`_caption_shortcut_open_filter`, `_caption_shortcut_open_replace`, the two `QShortcut`s at `:379`/`:390`,
the `Tools ▸ Caption Filter…` entry at `:3514`, and the `on_open_filter`/`on_open_replace` injections at
`:371-374`); **9 references in `tests/ui/test_main_window.py`**; **6 in `tests/ui/test_mainwindow_surface.py`**.
`set_regex_filter` (`caption_management_panel.py:378`) **STAYS** — it is the panel's own internal filter
path, not the modal's. Deleting the two `QShortcut`s also lets
`FindValidateController.set_find_actions`/`set_find_actions_enabled` (`find_controller.py:302-316`) and its
`main_window.py:1433` call site go — coordinate with FQ-016, which deletes the two QActions they gate.

**(b) The bar becomes permanent.** Drop `self.hide()` (`:738`); `show_bar()` (`:765-773`) collapses to a
**focus** operation; the context-menu entry `"Find / Replace bar"` (`:1538`) becomes *focus the bar* (or is
removed). `Escape` (`:791-795`) currently calls `close_bar()` — per the owner's editor ruling it must
instead **return focus to the grid** without hiding. Note `show_bar` today seeds the Find field from
`current_filter_pattern()`; with no show, that seeding needs a home or must be dropped deliberately.

**(c) ⚠️ THE PREMISE OF THE `Replace All` RULING IS WRONG IN THE CODE — and the correction makes the
owner's design better, not worse.** The brief states the bar has a `replace_field` with *"no button able to
act on it"*. **It is fully wired, and live:** `replace_field.textChanged → run_live_replace`
(`caption_management_panel.py:732`) → the injected `live_replace_preview` (`:1126-1174`), which on **every
keystroke** rolls back the previous proposal from `_live_replace_baseline` and writes a fresh one into the
grid's **New Value** column for the **currently-visible (filtered) rows**. The placeholder text is literally
`"Replace with (live)"` (`:700`) and the class docstring says *"there is no Replace All button… 'Live' is
the one thing that separates it from the modal"* (`:652-661`). So:
- **A `Replace All` button is NOT restoring a stranded capability for the filtered scope** — that scope is
  already covered, continuously. What is genuinely missing is the **project-wide** scope, which
  `replace_all_find(..., in_selection=False)` (`:1093-1116`) already implements and which **only the modal
  could reach**.
- **The panel's own docstring already argues for exactly the owner's dropdown**: *"The modal keeps the
  Global option — going project-wide stays an explicit, button-pressed gesture rather than something a
  keystroke can do"* (`:1141-1143`). So the coherent reading, and triage's recommendation, is:
  **`"in filtered results"` (the default) keeps today's live behaviour; `"in all project"` is inert until
  `Replace All` is pressed** — the dropdown selects the scope, and the button is what authorizes a
  project-wide write. This honours the ruling *and* preserves the existing deliberate rule.
  **The alternative — letting the dropdown drive the live preview directly — must be rejected explicitly**,
  because it would make a single keystroke rewrite every caption in the project.
- **Record as an intentional semantic change, not a port:** the modal's signature was
  `on_replace_all(find, replacement, mode, case, in_selection)` — **selection**-scoped. The new dropdown is
  **filter**-scoped. Selection-scoped replace is being **dropped**, on purpose.

**(d) ⚠️ DELETING `Close` DELETES THE ONLY COMMIT GESTURE — the sharpest collision in this entry.** The bar
is constructed with `on_close=self.commit_live_replace` (`caption_management_panel.py:931`), and
`commit_live_replace` (`:1176-1180`) *"stop[s] tracking the live preview: whatever it proposed becomes an
ordinary, hand-editable New Value… it only forgets the rollback baseline."* `close_bar` (`:775-784`) is the
handoff from *reversible preview* to *ordinary proposal*. With the bar permanent, `close_bar` never fires,
so `_live_replace_baseline` is **never released** and every previewed row stays owned by the preview — which
means a **hand edit of a previewed row's New Value is silently reverted by the next re-run**, and
`_refresh_live_replace`'s guard `if not is_active() and not baseline: return` (`:1188`) plus `is_active()`
itself (`:786-789`, *"True between show_bar and close_bar"*) both lose their meaning. This needs a ruling:
- Redefine **"active"** as *the Find field is non-empty* rather than *between show and close* (the natural
  reading once the bar is permanent).
- Make **`Replace All` commit** the baseline (an explicit, deliberate write is exactly the right handoff
  point), and note that **emptying the Find field already rolls everything back cleanly** (`:1153-1157`), so
  the reversibility contract survives without `Close`.
- Triage's recommendation is those two together; an owner decision is still needed because it changes when a
  proposal stops being reversible.

**(e) `Clear filter` has an existing implementation to bind to** — `clear_all_filters()`
(`caption_management_panel.py:1480-1490`), which already calls `_refresh_live_replace()` afterwards. Do not
write a new clear path. Confirm whether the button clears **only** the text filter or **all** filters
including the tree-set row predicates the retained banner describes — the existing method does the latter,
and the label `"Clear filter"` (singular) suggests the former. Naming matters here because the banner is the
only surface that shows the predicate filters.

**(f) ⚠️ `mode_combo` has THREE modes, and the owner named two.** `MODE_LABELS` gives `Normal (plain
string)` / `Extended (\n \t \0 \xNN)` / `Regular expression` (`caption_management_panel.py:702-704`, mirrored
in the deleted modal). The owner mentioned only normal and regexp. **Dropping `Extended` is a capability
removal** — `apply_find_replace`/`matches` implement it and the grid is the only place escape sequences in
caption text can be matched. Recommend keeping all three; **confirm before removing.**

**(g) Layout after the change.** Today: `[find_field] [mode_combo] [match_case] [Filter] [Close]` over
`[replace_field] [status_label] [error_label]` (`:714-729`). `Match case` and a status label already exist —
do not add second ones. Target: `Close` removed, `Clear filter` added, and `[scope dropdown] [Replace All]`
immediately before/after the replace field per the owner's *"immediately before Replace All"* ordering.
Keep the inline `error_label` as the **only** invalid-regex channel (never a modal) — that rule
(`:672-674`, `:802-805`) is unchanged and load-bearing.

**Alternatives considered**
- **Keep the modal for the project-wide scope only** (bar = filtered/live, modal = global) — the minimal
  change, and it is what the code was designed around (`:1141-1143`). **Rejected by the owner, verbatim and
  totally** (*"forget totally caption filter: delete totally the modal and the menu"*). Recorded because it
  is the only alternative that needs no new lifecycle decision at all; the dropdown-plus-button design in
  (c) is what replaces it, and it preserves the same safety property.
- **Convert `_confirm_unify_scope` to the same dropdown for idiom consistency** — proposed at triage,
  **corrected by the owner, and triage accepts the correction** (see the Idea section). Recorded verbatim so
  nobody "harmonises" the two later.
- **Retire the active-filter banner now that the bar is always visible** — **rejected: it would re-create
  BUG-020**, because the banner also reports row-predicate filters no text field can express.
- **Adding `Replace All` as a straight port of the modal's selection-scoped call** — rejected in favour of
  filter-scoped (see (c)); a straight port would keep a `in_selection` parameter whose meaning no longer
  matches any control on screen.

**Suggested placement:** **EXTEND §13 (Captions)** as the primary home — it owns the caption grid, the New
Value / Apply staging discipline (which is *why* the dropdown is sufficient protection without a modal: a
caption edit is staged into New Value and only an explicit **Apply** touches the XML), the live bar and the
modal being deleted. **EXTEND §26** to delete `Tools ▸ Caption Filter…` from the Tools inventory (spec line
5457). **EXTEND §27** to delete the `Ctrl+F` / `Ctrl+R` **Caption Mode override** row (spec line 5477)
jointly with FQ-016 — that row is the written form of dossier E1 and both halves of the conflict disappear
together. **CREATE nothing.** A **Supersession Ledger row is warranted**: §13/§27 currently specify the
modal and its two mode-gated shortcuts as settled design. Reuse `clear_all_filters()`,
`replace_all_find(..., in_selection=False)`, `live_replace_preview`, `set_regex_filter` and the existing
`error_label`/`status_label` channels rather than new mechanism.

**Open questions**
1. **Does `Extended` survive in `mode_combo`?** Three modes exist; two were named. Dropping it removes a
   real capability — confirm. (f)
2. **What commits the live preview now that `Close` is gone,** and what does `is_active()` mean on a
   permanent bar? Triage recommends: `Replace All` commits; "active" = non-empty Find field. (d)
3. **Does `"in all project"` drive the live preview, or only `Replace All`?** Triage strongly recommends
   only `Replace All`, per the existing rule that project-wide must be button-pressed. (c)
4. **Does `Clear filter` clear only the text filter, or all filters** including the tree-set row predicates
   the retained banner describes? (e)
5. Does the context-menu entry `"Find / Replace bar"` (`:1538`) become a focus action or disappear, and does
   the `current_filter_pattern()` seeding that `show_bar` performed survive anywhere? (b)

---
