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
**Status:** QUEUED
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
**Status:** QUEUED
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
**Status:** PROCESSED (uncommitted — implemented directly this session, not via the normal QUEUED wait)
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
