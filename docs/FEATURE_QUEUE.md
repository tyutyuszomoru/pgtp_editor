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
**Status:** PROCESSED (discoverability half `4bc73b6`; the quality leg shipped inside FQ-020's
`Deployment` menu, `04c3591`) — **both halves are now live.** The owner's 2026-08-06 ruling below
(accept precondition 2 as specified, do not narrow it) was carried out: `Run on quality` is a named
`Deployment` entry wired through `_wire_ddl_object_apply_seams` to `panel.apply_to_target()`, behind all
four §18.5 preconditions, and the `report_unverified` confirmation enumerates exactly which tiers went
unverified. The `Deploy this edit…` picker that FQ-009 shipped as its discoverability half was itself
superseded by those named entries (spec §18.5, 2026-08-08) and is queued for deletion by FQ-026.

**One stale claim in the code, flagged not fixed:** `_wire_ddl_object_apply_seams`' docstring still says
the shipped matrix is *"temporarily projectless-only"* because the project branch is *"blocked on BUG-034's
unpopulated `ProjectSettings.target`"*. BUG-034 is RESOLVED (`4bc73b6`) and `_target_apply_available()`
now reads `active_target_params(tree)`, which returns the populated `ProjectSettings.target` in project
mode — so the gate should be open there too. That was read from the code, **not proven by a test**;
the file was locked by another agent at flip time. Whoever picks this up next should pin project-mode
availability with a test before trusting it.

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
**Status:** SUPERSEDED BY FQ-027 (owner ruling, 2026-08-09) — **wherever the two entries disagree, FQ-027
wins.** The owner's reason is the ordering: FQ-010's launcher shipped, they used it, and FQ-027 is what
they asked for *after* testing it — so it reflects the design as revised by contact with the real thing,
while this entry reflects the design as imagined before.

**Nothing here was ever implemented.** Verified 2026-08-09 against the code: no `launchMode` /
`launch_mode` / `_current_mode` key exists anywhere in `pgtp_editor/`, and no menu filtering is
intent-based (the only visibility gating that ships is capability-based `_refresh_sandbox_affordances` or
tab-kind-based `_refresh_editor_menu_affordances` / `_refresh_parsing_menu_affordances`). What shipped was
**FQ-010** — `ui/launcher_dialog.py` and `LAUNCHER_GROUPS`, four groups of command ids where picking one
simply *triggers that QAction* and records nothing. The spec claimed otherwise (§7 said a launcher choice
*"sets the persisted launch mode"*) until `spec-harmonizer` caught it and corrected §7 to "planned only"
in `eaa0cb5`. So FQ-027 does not layer onto an existing mechanism; it builds the first one.

**The three concrete disagreements, all resolved in FQ-027's favour:**
1. **Persistence.** This entry: persisted across restarts. FQ-027: **session-only**. FQ-027 wins — and it
   is the safer of the two, because the trap this entry's escape hatch was written to cover (pick a mode
   once, lose commands on every future launch, with the launcher possibly suppressed) largely evaporates
   when the mode dies with the session. A session-only mode also needs no QSettings key at all.
2. **Launcher shape.** This entry assumes FQ-010's four groups. FQ-027: **three columns**
   (Standalone | Project | Maintenance), and it deletes the `launcherSuppressed` "don't show again"
   mechanism FQ-010 shipped.
3. **The hard case.** This entry's motivating example was hiding `Generate` in project mode — which empties
   a **default toolbar button** on a fresh install (its own open question 4, never answered). FQ-027
   sidesteps it: *"Project and standalone are OK for now"*, and only Maintenance gets a membership rule.

**What SURVIVES from this entry and must be carried into FQ-027's implementation** — FQ-027 itself cites
all of it and this is the reason not to delete the entry:
- The **mechanism**: one `_refresh_*_affordances`-style entry point, **visibility only, never
  enabled-state**, so the app keeps exactly two postures rather than gaining a third.
- **THE OBJECTION recorded below, which applies to FQ-027 unchanged and is NOT retired by this
  supersession.** Maintenance mode hides menus that genuinely still work, so it remains the first time this
  codebase hides on **user intent** rather than **real capability**. Whoever folds FQ-027 into the spec
  must state those as two deliberate, distinct rules — not let the second quietly overwrite the first.
- The rule that **`Help ▸ Manual` (F1) and the surface that clears the mode must never be filtered out**;
  FQ-027 satisfies it with `File ▸ New Session` plus a trimmed File menu and Help.
- The **`_walk_menu_actions` enumeration fact** (a hidden action is still enumerated, so Customize Toolbar
  keeps offering it and a pinned button keeps working) — which FQ-027 relies on deliberately in its
  menu-bar-only scope, and which is worth re-reading beside BUG-040's opposite conclusion.

Original entry preserved below unchanged.
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
**Status:** PROCESSED (adf9bfb storage + 9146524 wiring) — the storage layer: `db/bookmark_store.py`, `<project>/.ddlproject/bookmarks.json`, a SIBLING of settings.json rather than a `ProjectSettings` key (that struct feeds the deploy manifest, so a corrupt bookmark file can never cost the user their settings). Keys are project-relative POSIX paths with both sides resolved, so a moved or copied project resolves identically. Load NEVER rewrites, so lines beyond a temporarily shortened document return when it grows. An empty set removes its key rather than storing `[]`. Every malformed input degrades to "no bookmarks" instead of raising into a gutter click. 28 store tests (this line previously said 29; the file collects 28).

The gutter hookup and the project-open gate then landed in `9146524`. The gate is the capability fact `DdlProjectController.folder`, NOT FQ-011's launcher mode: with no project open the behaviour is bit-for-bit the status quo — no debounce started, no file written. Writes are a 400 ms debounce plus two synchronous flushes (project transition, `closeEvent`), never inside the hot `toggle_bookmark` gesture. `ui/editor_gutter.py` gained a module-level observer registry (`add_bookmark_observer`, reasons `BOOKMARKS_TOGGLED`/`CLEARED`/`RESET`, `WeakMethod`-held) which publishes and interprets nothing. **Exactly three editors persist** — Raw XML, DDL object tabs, and PHP file tabs whose path is *inside the project folder* (`relative_key` returns `None` outside it, so `File ▸ Open PHP File…` on an outside path is session-only). The Edit XSD editors CANNOT persist: their files live in the app-level `schema_storage_dir`, outside any project. Tests: `tests/db/test_bookmark_store.py` 28, `tests/ui/test_editor_gutter_observers.py` 8, `tests/ui/test_bookmark_persistence.py` 17.
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
**Status:** PROCESSED (9146524; spec §7/§8/§26/§27) — last on the Bookmarks menu, **no shortcut**, active editor only. Writes `[Bookmark] line N: <preview>` rows through a `_BOOKMARK_PREFIX` module constant beside the existing two, 1-based lines, plus roles-less count and empty-case rows. **The payload needed all three roles for PHP, not two:** the Audit click router's `"php"` branch reads the CenterStage tab key from `UserRole+2`, so a row omitting it is inert — which is also why rows for editors with **no** router branch at all (the read-only DDL Explorer buffer, an FQ-006 draft tab) are deliberately listed but inert rather than fabricating a route. Stale rows are swept on `BOOKMARKS_RESET` only. A dedicated bookmarks panel was NOT built: the Audit dock already is the app's list-of-locations surface with a working click router. Tests: `tests/ui/test_list_all_bookmarks.py` 16.
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
**Status:** PROCESSED (9146524; spec §7/§8/§18.5/§27/§28) — four menus on the Editor bar now, `Select` between History and Parsing. All three commands resolve the editor at **trigger** time via `FindValidateController.active_selection_editor()`, which delegates to `active_bookmark_editor()` so "which editor is the user looking at" has exactly one answer. `Select Enclosing Block` dispatches **by capability** (XML element vs. innermost balanced bracket pair); `Select Parent Block` is XML-only and **HIDDEN** on code-editor tabs — **the affordance seam's first real capability gate**, which the spec had credited to §18.5 D3a. `CodeEditor.keyPressEvent`'s duplicate `Ctrl+Shift+B` was measured and KEPT: the QAction wins where it exists, and the handler is the only host in the menu-less `CodeEditorDialog`. **One real defect fixed with it:** `XmlEditor._is_text_modifying_key` treated a Ctrl chord's printable `text()` as typing, so a read-only `XmlEditor` swallowed Ctrl+A and flashed the read-only hint; a Ctrl/Meta chord is now a command, tested **after** `matches(Paste)` so Ctrl+V keeps its hint. Note `Ctrl+A`'s `event.text()` is platform-dependent (the control character on Windows/Linux, the bare letter under `QTest.keyClick`). Tests: `tests/ui/test_select_menu.py` 23, `tests/ui/test_xml_editor.py` 113.
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
**Status:** PROCESSED (`5f53583` registry + dialog, `c4a838d` host wiring; spec §27/§26/§7 + a §28 ledger
row; manual re-framed) — `View ▸ Customize Shortcuts…`, persisted as `shortcutOverrides`, applied without
a restart and surviving one.

**The conflict rule is STEAL for editable commands and REFUSE for anything the dialog does not own**, and
it could not be "warn and allow": a Qt fact already recorded in this codebase (the `Ctrl+F` note in
`find_replace_bar.install_focus_shortcuts`) is that two enabled shortcuts on one chord are **ambiguous and
Qt fires NEITHER** — a duplicate does not degrade to first-wins, it deletes both commands from the
keyboard. So assign clears the loser in the same operation, `resolve_bindings` re-derives the same steal at
load so a hand-edited settings file cannot install an ambiguous pair, and a chord held by a NON-menu
occupant is refused rather than stolen (the dialog owns menu QActions only and cannot clear a
window-scoped `QShortcut`; stealing what you cannot clear produces exactly the ambiguity).

**Two implementation decisions that are load-bearing rather than tidy.** Default capture is
**capture-once**: after an override is installed the QAction no longer knows its built-in key, so
re-reading on a re-walk would enshrine the override AS the default and make *Reset to Default* a permanent
no-op. And applying is **two passes** — clear every action, then set — because one pass can leave a stolen
chord on two enabled actions mid-loop, reintroducing the ambiguity at the last moment.

Reserved bindings are §27 transcribed and are wider than the entry asked for, notably `Ctrl+C`/`X`/`V`: a
window-level shortcut would outrank the editors' built-ins and break copy everywhere.
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
**Status:** PROCESSED (c327c9d + 02e47e0, always-visible bars; `9146524` added the fourth menu — spec §7/§8/§15/§26/§27/§28) — the bar ships above the central pane (`centralWidget()` is now an anonymous container) with History · Select · Parsing · Bookmarks; the Edit menu is dissolved, and Cut/Copy/Paste/Delete and Preferences… went with it as never-implemented stubs (Ctrl+C/X/V remain Qt built-ins). `Validate Project` moved from Tools to Parsing. Toolbar consequences pinned: `LEGACY_ID_ALIASES["validate"] → parsing.validate-project`, the `find` **default** retired from three tables leaving **six** default buttons, while `edit-find.svg` stays user-assignable. Whole-bar hide on Caption Management and Manual hides the **widget**, never the actions — a default toolbar button shares the menu QAction, so gating those per tab would make the button appear/disappear.

**Also FQ-016: every `FindReplaceBar` is permanently visible**, in full form, at all six sites. `Ctrl+F`/`Ctrl+R` became focus gestures and `Escape` returns focus to the editor. **The structural reason they are hosted per tab** (`find_replace_bar.install_focus_shortcuts`) rather than window-level: a window-level `Ctrl+F` would be **ambiguous** against `CaptionManagementPanel`'s panel-scoped pair and Qt fires **neither** — it does not prefer the narrower context. Accepted side effects: `Ctrl+F` is a **no-op on bar-less tabs** (Manual, Diff/Merge, SQL Console) instead of yanking the user to Raw XML, and `active_find_bar()`'s reveal now serves **F3 only** — the one gesture that can still move the user off their tab. `Ctrl+Shift+F` and `Ctrl+Alt+Return` are deleted; `F3` survives as a window-level action on the `Ctrl+L` precedent. Tests: `tests/ui/test_menus.py` 49, `tests/ui/test_main_window.py` 63, `tests/ui/test_find_replace_bar.py` 27.
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

## FQ-018: Status-bar live indicators for Quality and Sandbox connectivity (30s poll, gated on window-active)
**Status:** QUEUED
**Requested:** 2026-08-08
**Idea (verbatim/summarized):** "In the status bar I would like to see with a 30s polling when the window
is active: 1. whether the app is connected to quality 2. whether the app is connected to sandbox."
Fully converged through direct Q&A with the requester (three clarifying questions asked and answered) plus
a code-verification pass; this entry records the settled design, not an open elaboration.

**Terminology (verified — no correction needed):** "quality" = the app's existing **Quality node** / the
**target** DB connection (`ui/main_window.py::_project_status_target()` ~line 2574 returns
`active_target_params()`; the §18.8 Quality node "speaks for" it; `db/sandbox.py::ProjectTier.QUALITY`
~line 388). "sandbox" = the separate sandbox connection (`ProjectSettings.sandbox`,
`db/ddl_project.py:116`). So "connected to quality" = target DB reachable; "connected to sandbox" =
sandbox DB reachable.

**Problem:** There is no always-visible, live signal of whether the two DB connections the app depends on
are actually up. The §18.8 **Project Status window** (`ui/project_status_panel.py` +
pure `ui/project_status_model.py`, shipped 2026-08-06) already computes and displays exactly these two
connection states, each in three states — Quality via the `QualityState` enum
(`project_status_model.py` ~lines 95-108: `NOT_SET_UP` / `OFFLINE` / `CONNECTION_OK`, derived by the pure
`quality_state(configured: bool, probe_error: str | None)` helper) and the Sandbox node's three states
(`sandbox_not_set_up` / `sandbox_connected` / `sandbox_offline`, from a
`ProjectCapabilityStatus.degraded_reason` classification) — but that window is a surface you open,
refreshed statically on open / explicit action, not something the user can glance at while working. The
user wants a condensed, always-visible, auto-refreshing mirror of two of that window's five nodes so they
can see connectivity at a glance without opening anything. This is a genuine difference from §18.8 (always
visible + auto-refreshing vs. open-and-static), NOT a duplicate to reject — but the state-derivation logic
must be REUSED, never re-derived as a second, independently-drifting notion of "connected."

**Proposed approach:**
- **Two permanent status-bar widgets** ("Quality: ●" and "Sandbox: ●", labels matching the §18.8 node
  names) added via `statusBar().addPermanentWidget(...)` alongside the existing Mode label
  (`self._mode_label`, `ui/main_window.py` ~lines 443-444) and conditional Debug label
  (`self._debug_label`, ~lines 446-452) — this follows that exact precedent. Each renders one of **three**
  reused states (grey not-set-up / red offline / green connected), NOT a binary yes/no. The sandbox
  indicator shows a distinct **not-applicable/absent** state when no project is open (hence no sandbox),
  mirroring how §18.8 simply omits the Sandbox node in the projectless/tier-1 case
  (`ui/project_status_panel.py` ~lines 290-302 render only applicable nodes; sandbox exists only with a
  DDL project open, §18.2).
- **A new repeating 30s `QTimer`** — the app's **first repeating-interval timer** (QTimer is used today
  only as single-shot debounces: `_snapshot_timer`/`_auto_parse_timer`/`_bookmark_write_timer`, all 400ms
  one-shot, `main_window.py` ~526/541/838). It fires a **lightweight reachability check** (connect +
  trivial `SELECT 1`-style liveness) for the target and, if a sandbox session is open, the sandbox —
  always **off the GUI thread via the established `run_async` seam** (used by every existing connection
  test and `SandboxController`); a blocking connect every 30s on the GUI thread would freeze the app. The
  result feeds the **reused pure state-derivation** (`quality_state()` + the sandbox-state classifier) so
  the status bar and §18.8 share one notion of state. Existing one-shot testers
  (`db/introspect.py::test_connection(params)` ~line 696; `db/sandbox.py::probe(params)` ~lines 158-198)
  are user-triggered and NOT polling; no periodic health poll exists anywhere today.
  `ui/sandbox_controller.py::session_changed = Signal(bool)` (~line 454, with `.session` property ~547)
  reports whether a session is *open*, not whether the DB is currently *reachable* — so it is a useful
  input (no live session → sandbox indicator is not-applicable) but not sufficient on its own; the poll's
  round-trip is what establishes liveness.
- **Window-active gating (new capability — does not exist in MainWindow today:** no `isActiveWindow()`,
  no `QEvent.WindowActivate/Deactivate`, no `applicationStateChanged`, no activation `changeEvent`
  override). The timer runs only while the main window is active; add activation detection (e.g. a
  `changeEvent`/`WindowActivate`+`WindowDeactivate` handler or an `isActiveWindow()` gate) that
  starts/stops (or skips) the timer. **Recommendation (not blocking):** also poll ONCE immediately on
  regaining activation, since a backgrounded window's displayed state can be up to 30s stale — so a
  returning user doesn't stare at a stale dot.
- **Lightweight reachability, not the full capability probe.** The 30s poll only confirms the DB answers.
  The heavier `probe()` (superuser check, pg_dump/pg_restore discovery, `degraded_reason`) stays on
  explicit user action in the Project Status window. **Consequence to record in the spec:** status-bar
  "connected" (green) means *reachable*, and can be green while §18.8's richer state still flags a
  capability degradation on its next explicit probe — the status bar answers "is it up?", not "is it fully
  capable?".
- **One shared poller feeds BOTH surfaces.** A single 30s poll updates the status-bar indicators and, when
  the §18.8 Project Status window is open, refreshes it too — so the two surfaces can never disagree on
  freshness. **Positive side effect to call out (it changes §18.8's current behavior):** the Project Status
  window becomes live/auto-refreshing while open, which it is NOT today (currently static until reopened /
  explicit action).

**Alternatives considered:**
- **Binary connected/not indicators (the literal request)** — rejected in favor of three states, because
  binary would make a never-configured sandbox indistinguishable from a sandbox whose DB just went
  offline, two situations needing different user responses.
- **Running the full `probe()` every 30s** — rejected as too heavy and mostly redundant between polls;
  lightweight reachability chosen, with the rich capability probe staying on explicit action.
- **A status-bar indicator polling independently of the §18.8 window** — rejected in favor of one shared
  poller, so the two surfaces can never show different freshness of the same connection (and §18.8 gains
  live refresh as a bonus).
- **Re-deriving "connected?" independently instead of reusing §18.8's pure state helpers** — rejected on
  the project's standing anti-duplication principle (a second, drifting notion of connection health is
  exactly the near-duplicate-parallel-functionality trap). This feature MUST consume `quality_state()` and
  the sandbox-state classifier, not fork them.

**Suggested placement:** EXTEND §18.8 (The Project Status window) — its pure state model
(`ui/project_status_model.py`'s `QualityState` / `quality_state()` and the sandbox-state classification)
is the engine this reuses, and the "one shared poller also refreshes the §18.8 window (making it live)"
decision directly changes §18.8's documented static-refresh behavior, so that section must record both the
new status-bar mirror and the window's new live-refresh behavior (**Supersession Ledger row for the
static→live change**). ALSO touch §7 (App shell) for the two new permanent status-bar widgets and the
app's first repeating-interval-timer + window-active-gating convention (§7 owns the status bar /
permanent-widget conventions, e.g. the Mode/Debug labels). Not a new top-level section — it extends the
§18.8 state engine + status surfaces and §7's app-shell conventions. (Verified no concurrent-session
implementation exists for this specific status-bar feature.)

**Open questions:** none blocking — the three load-bearing decisions (three-state vs binary, poll weight,
shared poller) are resolved. Implementation-level details left to whoever builds it: exact widget rendering
(colored dot vs text vs icon); whether the two indicators are one combined widget or two; the precise
activation-detection mechanism (`changeEvent` vs `applicationStateChanged`); and whether "poll immediately
on re-activation" (recommended above) is included in v1.

---

## FQ-019: Activity Log — a timestamped, per-project journal of every file and database action (dock panel + JSONL store)
**Status:** PROCESSED (`bc02d9c` core, `1aefc53` panel + the timestamp ruling, `65a0f1b` dock, lifecycle
and call sites) — the Activity Log ships whole: a dock beside Audit/Problems, per-project persistence, and
eleven gestures recording in **both** their success and failure legs.

**The owner reversed this entry's timestamp design (2026-08-09):** it specified a DYNAMIC format switching
on the log's calendar span, which made the format a property of the SET — one entry arriving after
midnight reshaped every row already on screen, so a panel could never cache a rendered row. A single fixed
`YYYY-MM-DD HH:MM` replaced it, and `TIME_FORMAT_SAME_DAY` was DELETED rather than left unused, since a
second format string is what would invite the behaviour back.

**Two host entry points, so no call site gates on mode:** `record_activity` for DB rows (the caller knows
the connection ROLE as a fact) and `record_file_activity`, whose one helper is the single place
`Project files` vs `Quality files` is decided. Previews are derived, not stored — a persisted second copy
of the text can only drift from it.

**A check is failed only on real BLOCKERS, never on `committed`** — a probe rolls back and a recheck
applies nothing, so judging either on commit would mark every clean check as a failure. An apply IS failed
when it did not commit.

**Three deliberate gaps, stated rather than papered over:** refusals where nothing started (no session, no
target, unavailable destination) get no line, because no action occurred; `Save XSD` fits none of the four
sources, schema files living outside any project — the same reason FQ-013 leaves XSD editors unpersisted;
and **`FILE_VERB_LINTED` has NO producer**, since §22's PHP on-save lint is advisory, fires after the save
it cannot affect, and would double every PHP save row. One settled verb with no call site.

Superseded detail from the partial flip: the **pure Qt-free core ships**: `db/activity_log.py`, the
entry dataclass, JSONL round-trip retaining FULL ddl and error text, and the dynamic timestamp formatter.
46 tests. Two design points settled while building it: previews are **derived, not stored**, because a
persisted second copy of the text can only drift from it; and the timestamp format is a property of the
**SET**, not of an entry, so a single post-midnight record reshapes every row already on screen and the
panel must re-render all of them rather than cache per-row strings. The four source labels double as the
persistence indicator, so callers never gate on mode themselves.

**Still owed: the whole UI half** — the dock panel beside the Audit panel, its click-router opening a
syntax-highlighted viewer for the full DDL/error, the debounce timer and flush-on-transition, and the
`record(...)` calls at each action completion point. The core is deliberately callable unconditionally
from every emit point; the mode decision lives in `project_dir` alone.
**Requested:** 2026-08-08
**Idea (verbatim/summarized):** "logging. I would like to have a log file and also a log panel that
records every file and database action. Format: [timestamp — HH:MM while the log's min and max fall in
one day, else YYYY-MM-DD HH:MM] - [Quality DB / Sandbox DB / Project files / Quality files] [ran/linted]
[DDL: first 20 chars then …, clicking opens a syntax-highlighted viewer; file: Saved / Opened / Reverted
/ Merged / Linted] [success/error — on error the first 20 chars of the error, opening the full error in a
syntax-highlighted window]. Logs saved per project. When no project is open, no log is saved out of the
session (dies with the session)." Fully converged through direct Q&A with the requester (three clarifying
questions asked and answered) plus a code-verification pass; this entry records the settled design, not an
open elaboration.

**Terminology (resolved with the requester — the four source labels encode a MODE/persistence
distinction, not a file-type one):**
- **Quality DB** = the target DB connection (`ProjectSettings.target`; the §18.8 "Quality" node).
- **Sandbox DB** = the sandbox DB connection (`ProjectSettings.sandbox`).
- **Project files** = files saved locally as part of a DDL project via the standard deployment pipeline
  (requester: "Project files implies files saved locally for using the standard deployment pipeline") —
  **persisted** per project.
- **Quality files** = files edited in STANDALONE mode — opening a `.pgtp` or `.php` directly to edit with
  NO DDL project open (requester: "Quality files is meant when the app is used in standalone mode, opening
  to edit a pgtp or a php file") — **session-only, never written to disk**.
- So the source label doubles as the persistence indicator: Quality-files entries are standalone/
  session-only; Project-files + Sandbox-DB entries are project-scoped/persisted; Quality-DB entries occur
  in either mode.

**Problem:** There is no operations journal anywhere. Verified: `CONSOLIDATED_SPEC.md` has zero
"activity log" matches, and the only text-logging that exists is app-global dev output via `debuglog.py`
(e.g. `_log.info("file: save %s")`) — an unstructured, non-persisted developer stream, not a
user-facing, per-project record of what happened to files and databases. The user wants a durable,
glanceable, clickable history of every consequential file and DB action (what, when, on which
connection/mode, succeeded or failed, and the full DDL/error behind each), persisted per project so it
survives across sessions, and — in standalone mode — kept in memory for the current session only.

**Proposed approach:** A Qt-free pure `ActivityLog` core + a thin new "Activity Log" dock panel + a
per-project persistence layer, mirroring the project's existing pure-core / thin-UI split (`history.py`,
`db/bookmark_store.py`). One central `ActivityLog.record(...)` entry point is called at each action
completion point — NOT derived by scraping `debuglog`'s logging stream (fragile string-parsing).
- **Pure core (`ActivityLog`, Qt-free, unit-testable without widgets):** an entry dataclass
  `{timestamp, source, verb, ddl_full|None, ddl_preview, file_verb|None, status, error_full|None,
  error_preview}`; JSONL (de)serialization retaining FULL DDL and FULL error text (the panel shows only
  previews; the viewer needs the full text); and the pure DYNAMIC-timestamp formatter computed over the
  whole displayed log's min/max span.
- **Thin "Activity Log" `QDockWidget`** (a `QListWidget` or a small `QTableWidget`) sitting BESIDE the
  Audit panel, NOT inside it (see placement note). It owns its own click-router opening a read-only
  syntax-highlighted viewer for the full DDL/error text.
- **Per-project persistence mirroring `db/bookmark_store.py`** (which persists `bookmarks.json` as a
  sibling of `settings.json` under `.ddlproject/`, located via `db/ddl_project.py::settings_path()`
  ~line 125 / `is_project_dir()` ~line 130). The structured store lives at
  `<project>/.ddlproject/activity.jsonl`, gated CAPABILITY-based on
  `ui/ddl_project_controller.py::DdlProjectController.folder`/`.is_open` (~lines 201-207/258) —
  consistent with FQ-013's capability-not-mode gating (§8). Debounced disk writes + flush on project
  transition, mirroring the bookmark store. On project open: load and display that project's persisted
  history. No project (standalone): in-memory buffer only, never written, cleared on session end /
  project transition.
- **Settled source taxonomy (4 values, one per entry):** Quality DB · Sandbox DB · Project files ·
  Quality files (mapping above).
- **Settled action set** (the requester's listed set PLUS both DB-write Apply actions — "Add both Apply
  actions"):
  - DB verbs: **ran** (sandbox ad-hoc run), **linted** (`db/ddl_check.py`), **Apply to Sandbox**,
    **Apply to Target** (the last is the irreversible production write — the single most audit-worthy
    action, explicitly included).
  - File verbs: **Saved / Opened / Reverted / Merged / Linted**.
- **Settled on-disk store: structured JSONL only, viewed in-app** (requester: "JSONL only, viewed
  in-app") — one file per project under `.ddlproject/`, no second human-readable `.log`.
- **Settled rendered format:** `[timestamp] - [source] [verb] [payload] [status]` where:
  - **timestamp** uses a DYNAMIC format keyed to the whole displayed log's span: `HH:MM` when min and max
    fall in the SAME calendar day; `YYYY-MM-DD HH:MM` when they span more than one day. Applied uniformly
    to every visible row, recomputed when a new entry extends the span. No seconds (requester wrote
    HH:MM) — two actions in the same minute show identical times, acceptable for a human journal.
  - **payload for DB/DDL actions:** first 20 chars of the DDL/SQL + "…", the row clickable →
    `ui/code_editor.py::CodeEditorDialog(language="sql")` read-only viewer showing the FULL DDL.
  - **payload for file actions:** the verb itself (Saved/Opened/Reverted/Merged/Linted) is the payload;
    no DDL preview.
  - **status:** success or error; on error, append the first 20 chars of the error message, the row (or
    an error affordance on it) clickable → a read-only syntax-highlighted window showing the FULL error
    (`language="sql"` for DB errors, plain text for file/IO errors — implementer's call).
- **Reused infrastructure (verified against code):**
  - **Read-only viewer: `ui/code_editor.py::CodeEditorDialog`** (~line 483), constructor
    `__init__(self, language, handler_name="", title=None, parent=None)`, with `set_code(text)`/`code()`;
    `language ∈ {"js","php","sql"}`; internal `CodeEditor` at `self._editor`. Use it as the DDL/error
    viewer by constructing with `language="sql"`, `set_code(full_text)`, setting the internal editor
    `setReadOnly(True)`, and showing NON-modally with `.show()` — never `.exec()` (the no-un-patched-modal
    test rule, §30). Its `saved`/`cancelled` signals fire harmlessly in read-only use.
  - **Click routing:** mirror the existing `ui/main_window.py::_on_audit_item_clicked` `Qt.UserRole+N`
    data idiom (~line 1420) AS A PATTERN, but the Activity Log dock owns its own router — NOT the Audit
    panel's. A row can carry BOTH a DDL payload and an error payload, so clicking must disambiguate (e.g.
    two affordances, or click-DDL vs click-error regions) — flagged as an implementation detail.
  - **Persistence pattern:** `db/bookmark_store.py` (debounce + flush-on-transition) verbatim.
- **Log-emit points (NO universal signal — each wired separately to `ActivityLog.record(...)`):**
  - File SAVE/OPEN/REVERT: `ui/pgtp_document_controller.py` — `_save_project()` (~551),
    `open_file()`/`open_pgtp_path()` (~346/358), `revert()` (~678).
  - MERGE: `ui/diff_merge_controller.py::apply_changes_to_target()` (~243; disk write ~292-293) — no
    completion signal today, modal feedback only; needs an explicit emit at the post-write point.
  - DB "ran": `db/sandbox_query.py::run_sandbox_query(session, sql)` → `QueryResult{outcome ∈
    ROWS/NO_ROWS/ERROR, error}`; the UI caller (the §18.5 D4 SQL console / Apply tab) is the emit point.
  - DB/file "linted": `db/ddl_check.py` (`apply_and_check`/`probe_check`/`recheck`, ~58-64); UI caller in
    `ui/ddl_object_editor.py` (Check handler) is the emit point.
  - Apply to Sandbox / Apply to Target: `ui/ddl_object_editor.py::apply_to_sandbox()` /
    `apply_to_target()` — the two DB-write emit points.

**Alternatives considered:**
- **Extend the Audit panel with an `[Activity]`/`[Log]` prefix** — rejected. `ui/main_window.py`'s
  `self.audit_panel` is a `QListWidget` (~line 331) governed by §7's closed "no fourth SQL-ish prefix"
  reservation (spec lines ~482-496: "The Audit panel keeps exactly the prefixes in this table"), and the
  Audit panel is scoped to FINDINGS (Check/Find/Validate/Bookmark/Schema/Lint/Sandbox/SQL) — a
  timestamped operations journal with success/error status and DDL/file provenance is a different
  concern. (A non-SQL-ish prefix would not technically breach the reservation, but the findings-vs-
  operations-history scope mismatch is the real reason.) A separate dock keeps both clear.
- **A human-readable plaintext `.log` (previews only) as the store** — rejected: lossy (can't retain the
  full DDL/error for click-to-view); requester chose JSONL-only viewed in-app.
- **Deriving the log by attaching a `logging.Handler` that parses `debuglog`'s `"file: save %s"`-style
  records** — rejected as fragile string-parsing; explicit structured emission at each call site instead.
- **Logging only the originally-listed set (omitting Apply to Sandbox/Target)** — rejected by the
  requester; the DB-write actions, especially Apply to Target, are the most audit-worthy and are included.

**Suggested placement:** CREATE a NEW subsection under §7 (App shell) — §7 owns the dock/panel inventory
(the left_tabs / CenterStage / Audit-Problems panel described at spec lines ~437-498), so the new
"Activity Log" dock belongs beside the Audit panel there. Nothing existing covers it (the §7 Audit panel
is a findings panel, not an operations journal; there is no activity-log concept anywhere in spec or
code). It must still reuse: the per-project `.ddlproject/` storage conventions (cross-reference §18.2),
the capability-gating rule (§8), and `CodeEditorDialog` for the click-to-view viewer. NOTE for whoever
folds it in: §7's Audit-panel prefix-reservation text (spec lines ~482-496) should gain a sentence
clarifying that the Activity Log is a SEPARATE dock and deliberately NOT an Audit prefix, so a future
reader doesn't try to merge them. Confirm exact section numbering against the live spec when writing.

**Open questions:** none blocking — all load-bearing decisions (separate dock; the 4-value source
taxonomy incl. the standalone-vs-project "Quality/Project files" meaning; action set incl. both Apply
actions; JSONL-only structured store; dynamic timestamp format; per-project vs session-only persistence)
are resolved. Implementation-level details left to whoever builds it: exact dock widget (QListWidget vs
small QTableWidget); the row click-disambiguation between DDL-view and error-view affordances; the
debounce interval for disk writes; the error-viewer highlight language; and whether standalone-session
entries are visually marked as non-persisted.

---

## FQ-024: Collapse the DDL Explorer right-click to one `Edit DDL` — checkout stops being a separate gesture
**Status:** PROCESSED (7b8ec7b; spec §18.1/§18.2/§18.5 + ledger §28) — one `Edit DDL`, dispatching on project state. Project open -> checkout (seed-when-absent, open-from-disk-when-present, drift report BEFORE manifest registration); projectless -> live source with a Save-As resolver. No `require_project` prompt on either side, which leaves that prompt exactly one consumer (Project Settings...). Labels differ by surface per §18.5's entry-point table: plain `Edit DDL` on the tree (the row names the object), `Edit DDL: <identity>` in the whole-schema buffer (the click landed in a wall of text). `checkout_requested` withdrawn from both panels.

**The tab key is now `ref.key` ALWAYS** — the real payload of this entry. Checkout used to key on the resolved `ddl/*.sql` path while Edit looked up `ref.key`, so checkout-then-Edit opened TWO tabs for one object, identically titled, with two different save destinations that could only diverge. Proven by restoring the old keying and watching both new regression tests fail with two distinct panel objects. **Two latent bugs fell out of the one-key rule, neither previously known:** `_save_ddl_object_editor` refreshed titles through a keyless `update_ddl_object_tab` so a checked-out tab's title never updated after save, and `_run_apply_to_sandbox_async` looked its panel up by `ref.key` and got `None` for a checked-out tab — an async sandbox-apply outcome had nowhere to land. `ddl_object_close_requested` is also honest again (declared `Signal(tuple)`; the checkout path was pushing a `str`).

The FQ-002 creation path is explicitly routed to the live branch: left to dispatch on project state it would have seeded a `ddl/*.sql` and registered a deploy-manifest entry for an object no database holds.

**One capability regressed, deliberately and recorded rather than papered over:** an already-open projectless tab is no longer promoted to checked-out when a project opens — `Edit DDL` focuses it instead, because the existence check short-circuits first. Pre-FQ-024 the same sequence produced a second, correctly-checked-out tab. There is currently **no gesture that promotes an open tab to versioned**; close and reopen. Pinned by `test_an_already_open_projectless_tab_keeps_its_save_as_resolver`, documented in the manual (3869c6d) as a looks-like-a-bug consequence, and left as this entry's open question.

**Entry-vs-code correction:** the queue and §18.1 both said `_on_ddl_checkout_requested` stays as the project-mode branch while the same paragraph forbade the `require_project` prompt that is its entire body. It was deleted; only the renamed `_edit_ddl_checked_out` survives. Tests: `tests/ui/test_ddl_project_wiring.py` (+5), `tests/ui/test_ddl_creation_wiring.py` (+1), per-panel menu/signal tests. Suite 4743 passed, 45 skipped.
**Requested:** 2026-08-08
**Idea (verbatim/summarized):** "The right-click collapses to one `Edit DDL`. The Edit-vs-Checkout
distinction dies as a *user-facing choice*; what differs is what the opened tab can DO, driven by project
state. Checkout *semantics* — seed-from-live when absent, open-from-disk when present, never overwrite
local from the DB, manifest registration, drift markers — all survive; they just stop being a separate
gesture." Settled in an owner review session; this entry is elaboration + consequence-hunting, not an open
elaboration. **Do not re-open the decision itself.**

**Problem:** The DDL Explorer's object-row context menu offers two entries —
`Edit <obj>…` and `Check Out for Versioning` (`ui/ddl_buffer_panel.py:455-461`, mirrored on
`ui/ddl_editor_panel.py:162`) — that ask the user to choose between two gestures whose real difference is
not intent but **project state**. Both open the same `DdlObjectEditorPanel` tab type; what actually differs
is where Save lands and whether the object joins the §18.2 deploy manifest.

**Verified hazard this must fix (no test covers it, and the code asserts the opposite).** The two paths key
tabs in **different namespaces**:

- `MainWindow._on_ddl_edit_requested` (`main_window.py:2490-2523`) probes and opens on **`ref.key`**, with a
  `resolver()` that runs `QFileDialog.getSaveFileName` on first save and remembers whatever path the user
  picked.
- `MainWindow._checkout_and_edit` (`main_window.py:3024-3056`) probes and opens on
  **`str(ddl_path)`** — the resolved absolute `ddl/*.sql` path — with a `resolver()` that returns that path.

Neither consults the other's namespace, so **Check Out then Edit (or Edit then Check Out) on the same object
opens TWO tabs**, both titled identically (`panel.tab_title()` derives from `ref`, not from the key) and
with **two different save destinations** — one writes an arbitrary Save-As path, the other the checked-out
file. `CenterStage.open_ddl_object_tab`'s own docstring claims *"Never opens a second tab for the same object (spec
§18.5)"*, which is false for the cross-sequence. This is a silent divergent-copies bug, and collapsing to
one entry is what makes one keying rule possible.

> **Line-number caveat for this entry and for FQ-020/FQ-021:** `ui/center_stage.py` was being edited by
> another session while these were triaged, and its line numbers moved mid-pass (`enter_caption_mode` was at
> `:312` and is now at `:345`; `_closable` was at `:215`, now `:226`). **Trust the symbol names cited in these
> three entries, not the line numbers.**

**Proposed approach:**

- **One context-menu entry, `Edit DDL`,** replacing both on `BrowserPanel._menu_for_item`
  (`ddl_buffer_panel.py:440-462`) and `EditorPanel`'s equivalent (`ddl_editor_panel.py:~150-165`).
- **Behaviour is chosen from project state, never from which entry was clicked:**
  - **Project open** → today's `_checkout_and_edit` body in full and unchanged: `ddl/*.sql` absent → seed
    from the live introspected definition (*that write **is** the checkout*, §18.2); present → open from
    disk (the local file is the editable truth and is **never** silently overwritten from the DB);
    `_report_ddl_checkout_drift` **before** `_register_checked_out_object` (the drift report must see the
    *previous* last-deployed reference); resolver returns `ddl_path`.
  - **No project** → today's `_on_ddl_edit_requested` body: live source text, and the Save-As-on-first-save
    resolver. (**Cross-reference:** FQ-020 deletes `Ctrl+S`, so "first save" means the first
    `Deployment ▸ Save in Project` click, not the first keystroke. The `resolver()` closure itself is
    unchanged — only its trigger moves. Whichever of FQ-024/FQ-020 lands second inherits this.)
- **The `require_project` prompt must NOT ride along.** Today `_on_ddl_checkout_requested`
  (`main_window.py:2997-3005`) wraps the checkout in
  `self._ddl_project_ui.require_project(...)`, which offers Create…/Open…/Cancel. With a single entry, that
  modal would fire on **every** `Edit DDL` in projectless mode — a first-class supported mode
  (§18.2: *"Neither browsing nor single-object editing needs a project — only versioning does"*).
  Projectless `Edit DDL` must silently take the non-checkout path with no prompt. Whoever implements this
  must not "helpfully" keep the offer.
- **One keying rule — recommendation: key on object identity (`ref.key`) always,** and let the *save
  destination* be the project-dependent part. `ref.key` is the only value available on both paths, it is
  what the user thinks in, and the path key existed only to give checkout a stable identity across the
  same object opened project-vs-projectless — which one entry makes moot. Consequences:
  - `center_stage.open_ddl_object_tab(..., key=None)`'s `key=` parameter loses its only caller. **Do not
    delete it** — §18.7 (below / FQ-022) needs a caller-supplied key to address the target-vs-sandbox
    Explorer instances by connection role. Leave it, and say in the docstring that it is now §18.7's seam.
  - §18.5 carve-out 9's append-only/tail-only dynamic-tab invariant is untouched.
  - **Mandatory new regression test:** `Edit DDL` on the same object twice, with a project opened between
    the two invocations, yields exactly **one** tab. This is the guard for the hazard above and its absence
    is why the bug shipped.
- **`checkout_requested` is deleted from both panels** — the signal declarations
  (`ddl_buffer_panel.py:141`, `ddl_editor_panel.py:64`) and both `MainWindow` connections
  (`main_window.py:317`, `:396`); verified those are its only consumers. `_on_ddl_checkout_requested` /
  `_checkout_and_edit` are **kept as the project-mode branch** of the one `edit_requested` handler (rename
  to say so, e.g. `_edit_ddl_checked_out`), so checkout semantics keep exactly one implementation rather
  than being re-inlined. Note `tests/ui/test_mainwindow_surface.py` pins method names and will need the
  same-commit update.

**Alternatives considered:**
- **Keep both entries and just fix the keying.** Rejected: it fixes the divergent-tabs bug but leaves the
  user choosing between two gestures whose difference is state — the owner's actual complaint.
- **Make `Check Out for Versioning` a project-only entry, absent projectless** (the §18.5 carve-out 2
  no-dead-controls posture). Rejected: still two entries, and the menu would change shape under the user
  for no gain in expressiveness.
- **Key on the resolved path always** (the inverse of the recommendation). Rejected: projectless there is
  no path until the user picks one in a dialog, so the key would not exist at tab-open time.

**Suggested placement:** EXTEND **§18.1** (the DDL Explorer's context-menu inventory, which names both
entries explicitly), **§18.2** (`#### The external checkout process` / the checkout gesture — the semantics
survive, the gesture does not), and **§18.5 D1** (entry points; carve-out 9's tab-keying invariant). All
three currently describe two distinct gestures and must be rewritten to *"one `Edit DDL`, two behaviours
selected by project state."* **Supersession Ledger row required:** a documented user-facing gesture
(`Check Out for Versioning`) is withdrawn, and `center_stage.open_ddl_object_tab`'s docstring claim about
never opening a second tab goes from false-as-written to true-by-construction.

**Open questions:**
1. **What happens to an already-open tab when a project opens?** With identity keying, a tab opened
   projectless keeps a Save-As resolver even after a project makes checkout possible. Two forks:
   (a) leave it — mirroring §18.5 carve-out 5's *"re-running DDL Explorer leaves open object tabs untouched
   and silent"* — with the honest consequence that the user must close and reopen the tab to get it under
   versioning (triage recommends this: it never re-points a destination under a live edit); or (b) re-resolve
   every open tab's resolver on project open, which silently changes where an in-progress edit will land.
2. Does `Edit DDL` on an object **already open** as a projectless tab, with a project now open, focus the
   existing tab (consistent with (a)) or perform the checkout write and re-point it (consistent with (b))?
   Same fork, stated separately because it is the gesture the user will actually reach for.

---

## FQ-020: A `Deployment` menu on the Editor menu bar — and the deletion of File ▸ Save / Save As
**Status:** PROCESSED (04c3591, merging `7a683e6`) — the Editor bar's fifth menu, contents by ACTIVE TAB
KIND, with `File ▸ Save`/`Save As…` and `Tools ▸ Compare / Merge Two Files…` deleted and re-homed.
**Two rulings diverge from this entry, both deliberate:** (1) **`Ctrl+S` did NOT survive** — the entry
asked that it stay bound to whatever the active tab offers, but the four-way router behind it had an
`else` that fell through to writing the `.pgtp`, so Ctrl+S with the Sandbox SQL Console, a draft fragment
tab, Diff/Merge, Caption Management, either DDL Explorer or the Manual active **silently wrote the
`.pgtp`** — six tab kinds it was never meant to catch, three of them specified as never saving anywhere.
The router is deleted rather than case-patched (a dormant router is what gets re-bound to a key later),
and each of the four surviving save commands is a named menu entry wired to exactly one writer. **No
member of the menu carries a shortcut at all** — §18.5's rule for the two `Run on …` entries, extended to
the saves. (2) Every action is built **once** and only `setVisible`-toggled, never created per tab:
`ToolbarController._walk_menu_actions` never tests `isVisible()`, so a hidden action stays enumerable and
pinnable, while a non-existent one would make Customize Toolbar's list (and queued FQ-012's) depend on
which tab is active and would silently drop saved `toolbarIds`. No separators (only one group is ever
visible). Tab kinds with no save and no destination get **no group at all** — an explicit "none"
classification, which is precisely the `else` the old router lacked. Tests: `tests/ui/test_deployment_menu.py`.
**Requested:** 2026-08-08
**Idea (verbatim/summarized):** "A `Deployment` menu on the Editor menu bar, contents per active tab,
replacing the buried `Deploy this edit…` picker: Raw XML → `Compare/Merge pgtp`, `Save as new pgtp`,
`Deploy .pgtp`; DDL object → `Save in Project`, `Run on sandbox`, `Run on quality`; Edit XSD → `Save XSD`;
PHP file → `Save PHP File`. **File ▸ Save and File ▸ Save As… are DELETED** — the capability moves here
per-tab. **Ctrl+S stays bound to whatever the active tab offers** (the reflex must keep working and must
never write the wrong thing); Ctrl+Shift+S dies. `file.save` gets retired from the default toolbar the
FQ-016 way. Tools loses `Compare / Merge Two Files...` and `Apply Changes to Target`. **File ▸ Revert becomes
`Discard Changes` / reload-from-disk**, gated on the buffer differing from the file on disk, NOT on a `.bak`.
**Owner ruling: `Run on quality` works PROJECTLESS too** — the deliberate 'fast bugfix mode': open a `.pgtp`
with no project, edit an object, push it straight to quality. Matrix: projectless = `Run on quality` only;
project = all three." Settled in an owner review session. **The projectless-quality risk was raised and the
owner reaffirmed it — do not re-argue it.**

> **OWNER RULING, 2026-08-08 (final; supersedes an intermediate coordinator answer that kept Ctrl+S):
> `Ctrl+S` DIES TOO. Every save becomes a deliberate menu click.**
> - **What dies:** `File ▸ Save`, `File ▸ Save As…`, **`Ctrl+S`** and `Ctrl+Shift+S`.
> - **What survives:** the four per-tab named entries on `Deployment` — **`Save pgtp`** (Raw XML),
>   **`Save in Project`** (DDL object), **`Save XSD`**, **`Save PHP File`** — plus `Save as new pgtp`
>   (Save As, no shortcut). **In-place save of the `.pgtp` survives as `Deployment ▸ Save pgtp`**, which
>   matters because §18.2 makes the working copy a first-class checked-out artifact that `Deploy .pgtp` later
>   pushes to the sshfs source, and projectless it is the only way to save at all.
> - **`Discard Changes` therefore keeps its ordinary meaning** (discard edits since the last save): saves
>   still happen in place, just never by keystroke. An earlier worry that it would become "throw away the
>   whole session" is retired.
> - **An intermediate answer proposing a menu-less window-level `Save` action carrying Ctrl+S (on the `F3`
>   precedent) is WITHDRAWN.** Do not resurrect it; item 3 below records what its withdrawal costs.

**Problem:** Two separate defects, both verified.

1. **`Deploy this edit…` is buried.** The three per-edit destinations (`ddl_object_editor.py:97-105`:
   `DEST_SANDBOX` "Apply to Sandbox" / `DEST_SAVE` "Save (for a future batch deploy)" / `DEST_TARGET`
   "Apply to Target") sit behind a context-menu picker on the object tab, mirrored onto the Database menu.
   A user has to already know the picker exists to find any of them.
2. **`File ▸ Save` is a silent dispatcher with a wrong-target fall-through.**
   `MainWindow._save_active_tab` (`main_window.py:913-929`) is a **four-way** dispatcher: Edit XSD →
   `_xsd_ui.save()`; active DDL object panel → `_save_ddl_object_editor`; active PHP tab →
   `_php_tabs.save_active_tab()`; **else → `_doc_ui.save_project()`**. That `else` currently catches
   **every other tab kind** — Diff/Merge, Caption Management, DDL Explorer (read-only), Manual, FQ-006
   **draft fragment tabs** (spec'd as never saving anywhere) and the **§18.5 D4 Sandbox SQL Console**
   (`center_stage.py:151/154/193/196/409/462`). So **Ctrl+S with the SQL console focused writes the
   `.pgtp` today.** That is precisely the "must never write the wrong thing" failure the owner's ruling is
   about, and it exists now, before any of this lands.

**Proposed approach:** the menu exactly as listed, `File ▸ Save`/`Save As…` deleted, Ctrl+S per-tab,
Ctrl+Shift+S deleted, `file.save` retired the FQ-016 way, Tools losing its two Compare/Merge entries. The
load-bearing consequences, in the order an implementer will hit them:

1. **INVARIANT (required work, not advice): build the `Deployment` menu ONCE at startup and gate its members
   with `setVisible` — never create/destroy actions per tab.** Verified constraint, not a preference:
   `ToolbarController._walk_menu_actions` (`toolbar_controller.py:212-268`) enumerates every leaf action of
   both menu bars and **never tests `isVisible()`**. So a hidden action stays enumerated, stays pinnable and
   keeps a stable id — but an action that does not **exist** at enumeration time is invisible to
   `collect_menu_commands()`. Rebuilding the menu per tab would make Customize Toolbar's Available list
   (and queued FQ-012's Customize Shortcuts list, which enumerates the same way) show only the *currently
   active tab's* commands, and would silently drop saved `toolbarIds` for whichever tab was not active at
   restore time. Build all ~8 actions at startup; flip visibility on `center_stage.currentChanged` through
   the §7 `setVisible`-by-active-tab-kind seam. **This invariant also protects queued FQ-012** (Customize
   Shortcuts), which enumerates the same way and would otherwise offer a shortcut list that changes with the
   active tab — state it in the spec as a rule about per-tab menus generally, not as a note about this menu.
2. **A pinned Deployment button will appear and disappear — accept it, with the FQ-015 precedent.**
   FQ-016's recorded reason for *not* gating `Parsing` per tab was specifically that `Validate Project` is
   one of the **six default** toolbar buttons, so gating would make a *default* button blink out on a fresh
   install. None of Deployment's per-tab members is a default, so the governing precedent is
   `Select ▸ Select Parent Block` (FQ-015): hide the **action**, accept that a *user-pinned* button comes
   and goes. Record this explicitly in §7 as the second accepted instance so it is not re-litigated.
3. **`file.save` retires the FQ-016 `find` way — the default toolbar drops six → five and the app ships with
   NO save button.** With Ctrl+S gone there is no tab-following save command left for it to point at, and the
   four per-tab entries are tab-gated (item 2), so pinning one of them by default would ship a button that
   blinks out. Concretely: remove the `("save", "Save")` row from `LEGACY_COMMANDS` and the `"save"` row from
   `LEGACY_ID_ALIASES` (`toolbar_registry.py:51-58`, `:70-77`); `DEFAULT_TOOLBAR_IDS` derives from those two
   (`:81-83`) and shortens by itself. `ICON_ID_BY_COMMAND` is `LEGACY_ID_ALIASES` **inverted** (`:88-90`), so
   the `document-save.svg` **default binding** disappears with the row while the SVG stays **user-assignable
   from the FQ-004 Breeze catalog** — exactly the treatment FQ-016 gave `edit-find.svg`.
   - **What happens to a user who had pinned Save:** `resolve_ids` maps legacy ids through
     `LEGACY_ID_ALIASES` and then filters against the live command set (`toolbar_registry.py:123-140`), so a
     saved `"save"` or `"file.save"` id no longer resolves to anything and is **silently dropped** on load —
     the button simply disappears from their toolbar, no dead/empty button and no error. That is the correct
     degradation and it is already implemented; it needs a test, not new code.
   - **The user's remedy is explicit and should be in the manual:** pin `Deployment ▸ Save pgtp` (or whichever
     of the four they use) themselves, accepting that it is visible only on its own tab.
4. **REQUIRED WORK — the `_save_active_tab` router is DELETED, not repaired. A pre-existing live defect dies
   with it, and that must be recorded so nobody re-adds the router later without knowing what it cost.**
   The defect, stated plainly because it is attributable: **today, Ctrl+S with the Sandbox SQL Console, a
   draft fragment tab, Diff/Merge, Caption Management, the DDL Explorer or the Manual active silently writes
   the `.pgtp`** — `main_window.py:913-929`'s `else: self._doc_ui.save_project()` catches all six tab kinds.
   An earlier draft of this entry proposed fixing it with an explicit per-tab dispatch table plus a
   no-op-plus-status default; the owner's Ctrl+S ruling makes that unnecessary. **Removing the only app-level
   Ctrl+S host removes the whole bug class**: with no router there is no wrong branch to fall into, and each
   of the four save commands is wired directly to exactly one writer. Required of the implementer:
   - Delete `_save_active_tab` outright rather than leaving it as a "convenience" entry point with no caller —
     a dormant router is what gets re-bound to a key later.
   - **Do not reintroduce any tab-dispatching save under any name.** Record this as a stated invariant in the
     spec with the defect above as its justification, so a future "bring back Ctrl+S" request re-derives the
     dispatch problem instead of re-shipping it.
   - **Mandatory test:** no code path saves the `.pgtp` except `Deployment ▸ Save pgtp` and
     `Save as new pgtp` (and `Deploy .pgtp`'s outward push) — in particular, a test that the six tab kinds
     above have no save path at all.
4a. **Every `Ctrl+S` host in the codebase, verified — there are THREE, and only one of them is the router the
    ruling is about.** A literal "delete every Ctrl+S" sweep would cause an unrelated regression, and a
    literal "delete `File ▸ Save`" would leave an inconsistency:
   - **`MainWindow`'s `File ▸ Save` action** (`main_window.py:1796`, `save_action.setShortcut("Ctrl+S")`) →
     `_save_active_tab`. **This is the one that dies.** `Ctrl+Shift+S` (`:1799`, `_save_project_as`) dies with
     `Save As…`.
   - **`CodeEditorDialog` — MUST NOT DIE.** It has its own Ctrl+S twice over: a `WindowShortcut`-scoped
     `QShortcut` (`code_editor.py:514-515`) **and** a duplicate branch in `keyPressEvent` (`:531-543`, present
     because `QShortcut` activation is unreliable under the offscreen platform in tests). Both call
     `self.save`, which is the dialog's **OK/accept** — the same slot as `button_box.accepted` (`:507`) — and
     writes **nothing to disk**; it is paired with `Ctrl+W` = cancel (`:516`, `:540-542`). Killing it would be
     an unrelated regression in the `Edit code…` modal. **Explicitly carved out**, with that reason recorded.
   - **`PhpFileTab` — a REAL per-tab Ctrl+S that survives the deletion by accident, and needs an explicit
     decision.** Correcting a claim made during review that no such filter exists: it does.
     `php_file_tab.py:377-400`'s `eventFilter` (installed on its editor at `:193`) claims `Ctrl+S` →
     `self.save` (`:389-390`) and accepts the `ShortcutOverride` so the window-level shortcut never also fires
     (`:392-396`) — which is exactly what `main_window.py:924-926`'s comment describes, so **that comment is
     accurate, not stale.** Consequence: deleting `File ▸ Save` leaves the **PHP tab as the one tab in the app
     where Ctrl+S still saves**, while every other tab loses it. That inconsistency is worse than either
     uniform answer and must be decided, not inherited — see open questions. (Same file's `Ctrl+Z`/`Ctrl+Y`
     branches are §18.5 carve-out 1's native-undo routing and are untouched either way.)
   - The DDL object editor's event filter claims `Ctrl+Alt+F` and `Ctrl+Z`/`Ctrl+Y` only, **not** `Ctrl+S`
     (`ddl_object_editor.py:686-697`, `:789-792`) — so its Ctrl+S came solely from the window action and
     simply goes.
4b. **A user-facing string becomes a lie and must change in the same commit.**
    `ui/xsd_controller.py:535` tells the user verbatim:
    *"The XSD tab has unsaved changes — save it first (Ctrl+S)."* With Ctrl+S unbound that instruction is
    unfollowable; it must name `Deployment ▸ Save XSD`. Grep for sibling strings before assuming this is the
    only one, and note the manual (`resources/manual.md`) and §27's shortcut table both advertise Ctrl+S in
    several places.
5. **`Revert` → `Discard Changes` (label recommendation, with reasons).** Pick **`Discard Changes`**, not
   `Reload from Disk`:
   - `Revert` today means something genuinely different — `PgtpDocumentController.revert()`
     (`pgtp_document_controller.py:678-704`) reloads **`<path>.bak`**, i.e. *undo my last save*, and leaves
     the buffer **dirty**. Reusing the word for reload-from-disk would silently redefine a documented
     command; a new label makes the semantic change visible.
   - "Discard Changes" names the user's *intent*; "Reload from Disk" names the *mechanism*. The confirm
     dialog has to say what is lost either way, and the intent wording matches it.
   - **Gating is cheaper than today's, not more expensive.** `refresh_revert_action()`
     (`:662-676`) deliberately avoids being called from `set_dirty` because a per-keystroke
     `Path(bak).exists()` would `stat` a possibly-sshfs-mounted path. The new gate should be the **dirty
     flag**, not a re-read of the file — so it can safely hang off `set_dirty` and the `stat` disappears
     entirely. `backup_path()` and the `.bak` reader in `revert()` must be **deleted**, not left dead.
   - **Who still writes a `.bak`, verified:** `_write_project_text` (`:527-541`) — which already skips the
     `.bak` for a §18.2 project working copy and only writes one in **non-project** mode over an existing
     path — and `diff_merge_controller.apply_changes_to_target` (`:287-288`), which writes one beside the
     **compare target**, a different file. Neither is the project working copy, so *"nothing will write a
     `.bak` once in-place save is gone"* holds for the project case (which is what the gate change turns
     on) and **both other writers must stay untouched**.
   - Stays on the **File** menu, per the owner.
6. **`Run on quality` projectless — the safety that must ride along.** The confirmation names the resolved
   **database and host**, and the outcome lands in the Audit panel so a projectless session still leaves a
   record. **One correction to the framing:** the sandbox apply confirmation does **not** name the host
   today. `DdlObjectEditorPanel.__init__`'s seam docstring (`ddl_object_editor.py:574-577`) documents
   `sandbox_database_label()` as returning e.g. `"prod on db01:5432"`, but the shipped provider
   `MainWindow._sandbox_database_label` (`main_window.py:3658-3666`) returns `session.params.database`
   **alone**. So naming the host is a **new** requirement on *both* labels — and a spec-vs-code drift worth
   closing in the same pass — not a mirror of existing behaviour. It matters most exactly in projectless
   mode, where the target is *derived* (`active_target_params` → `seed_params(tree, self._settings)`, merging
   the app-level saved connection with the open `.pgtp`'s `<ConnectionOptions>`) and the user may well not
   know which host that resolved to.
7. **Projectless `Run on quality` currently has no password path — a wiring prerequisite, not a
   re-argument.** Verified: `_target_params_for_fetch` (`main_window.py:2579-2605`) short-circuits with
   `if self._ddl_project_settings is None … return params` — BUG-034's one-time prompt is **project-only** —
   and `connection_from_tree` forces `password=""` (§17: the password is never read from the XML). So in the
   owner's exact fast-bugfix scenario (open a `.pgtp`, no project, edit, push) the resolved target carries
   host/database/user but **no password** unless the user previously saved one via Connection Setup, and the
   apply fails on authentication with no prompt offered. The projectless leg therefore needs either the
   prompt extended to the projectless branch — with **nowhere to persist it** (there is no
   `.ddlproject/settings.json`; recommend **session-only**, and explicitly *not* writing it into app-level
   QSettings, which would be the "silently substituting some other stored credential" confusion BUG-034 was
   about) — or an explicit stated refusal *before* the confirmation. Silently failing on auth after a
   confirmation that named a production host is the worst of the three.
8. **Wiring `Run on quality`.** `_wire_ddl_object_apply_seams` (`main_window.py:3606-3656`) must read
   **`_target_params_for_fetch()`**, not `sandbox_controller.target_params`, and fill the already-existing
   but unwired `apply_to_target` / `live_identity` / `target_database_label` seams
   (`ddl_object_editor.py:529-532`). Of its docstring's three reasons for not wiring Apply to Target:
   reason 1 ("the identity seam has no source") is **stale for projectless** — `active_target_params(tree)`
   (`:2540`) resolves a projectless target with credentials — and true only for the *project* branch
   (`ProjectSettings.target`, still blocked on BUG-034); reason 2 ("reachability is not a fact") is **stale**
   — BUG-030 added `ddl_project_controller.py:550 refresh_target_connection_status()`, a real off-thread
   `SELECT 1`, with or without a project; reason 3 (**no revert snapshot, and §18.5 precondition 2's
   override is reachable with nothing verified** — `DdlObjectEditorPanel._precondition_validation` treats an
   un-checked buffer as an overridable "the ladder has not been run") **stands** and is exactly the posture
   the owner is deliberately changing. That docstring must be rewritten in the same commit rather than left
   describing a decision that has been reversed. **The project-mode `Run on quality` leg stays blocked on
   BUG-034** — so the shipped matrix is temporarily *projectless-only*, which is worth stating out loud
   because it inverts the intuitive expectation that a project can do more, not less.
9. **Audit reporting: do not mint a new prefix.** §18.5 D4 explicitly declined to create one. Recommend the
   projectless quality apply reports under the existing **`[Check]`** prefix (§18.5's apply/ladder channel),
   naming object + database + host, so the record is in the one place the user already looks.
10. **`Save XSD` and `Save PHP File` are relabels, not new code** — they are the existing
    `_xsd_ui.save()` and `_php_tabs.save_active_tab()` dispatcher branches given a discoverable name.
11. **Tools loses `Compare / Merge Two Files...` and `Apply Changes to Target`, but only the first lands
    here.** `Compare/Merge pgtp` on the Raw XML tab is the relabelled entry point.
    **`Apply Changes to Target` goes to FQ-021's mode-scoped Compare/Merge surface, NOT to Deployment**
    (settled 2026-08-08): it is only meaningful while a comparison is loaded, and it *replaces the app's open
    document* (`diff_merge_controller.py:300`'s `_reload` → `open_project_file`,
    `main_window.py:742`) — hosting it beside `Run on quality` would put two very differently-shaped
    irreversible actions under one menu.
12. **`Run on sandbox` / `Run on quality` / `Save in Project` are label changes to shipped concepts**
    (`Apply to Sandbox` / `Apply to Target` / `Save`). Their command ids are new (`deployment.run-on-sandbox`
    etc.); none of them is a legacy or default toolbar id, so **no alias is needed** — but the
    `DESTINATION_LABELS` dict (`ddl_object_editor.py:101-105`) and the §18.5/§26 spec text that quote the old
    labels verbatim must be updated together, or the manual and the UI disagree.

**Alternatives considered:**
- **Keep `File ▸ Save` as the one dispatcher and merely *add* `Deployment`.** Rejected by the owner — two
  homes for one capability is the ambiguity being removed. Recorded because it is the obvious
  lower-risk half-measure and someone will propose it.
- **A `Deployment` *toolbar* rather than a menu.** Rejected: §7's toolbar is the user-curated favourites
  bar and is explicitly *not* app-decided; a second app-owned toolbar would be a new concept for one
  feature, where the Editor menu bar (§26) is already the established home for per-tab commands.
- **Keeping `Ctrl+Shift+S` as project-only Save As.** This is what §18.5 and §27 currently pin ("`Ctrl+Shift+S`
  stays project-only — it does NOT re-route to the object tab", with a written rationale). The owner deletes
  it; that pinned ruling must be **explicitly overridden with a ledger row**, not quietly contradicted.
- **A menu-less, window-level `Save` action carrying `Ctrl+S`** (dispatching per tab, on the `F3` precedent of
  a window action with no menu home). Proposed during triage and **withdrawn by owner ruling 2026-08-08**.
  Recorded because it is the obvious way to keep the reflex, and because it had two real costs the ruling
  avoids: it would have kept a tab-dispatching router alive (the exact mechanism behind the pre-existing
  wrong-target defect in item 4), and a menu-less action is invisible to `_walk_menu_actions`, so making it
  pinnable/aliasable would have required a new registration seam in `ToolbarController` that does not exist.
- **Fixing the wrong-target defect with an explicit per-tab dispatch table plus a no-op-plus-status default**,
  keeping Ctrl+S. Superseded by the same ruling: deleting the router is a strictly stronger fix than making the
  router correct, because it removes the branch rather than adding a case to it.

**Suggested placement:** **EXTEND §26's "The Editor menu bar" inventory** — `Deployment` becomes its
**fifth** menu (History · Select · Parsing · Bookmarks/Navigation · Deployment), and §26's window-menu-bar
inventory loses File ▸ Save/Save As and Tools' two Compare/Merge entries. Also EXTEND: **§7** (the *deletion*
of the Ctrl+S save router and the standing invariant against re-adding one, the `.bak`/Revert contract,
`LEGACY_COMMANDS`/`LEGACY_ID_ALIASES`/`DEFAULT_TOOLBAR_IDS` dropping to five, the second accepted instance of
hiding an action), **§18.5** (`#### Save and Apply are two distinct, explicit user gestures` — Save's
*trigger* moves from `Ctrl+S`/File ▸ Save to a menu click, and the sub-bullets naming `Ctrl+S` as the Save-As
trigger on a never-saved object tab must be rewritten around `Deployment ▸ Save in Project`, including the
*"cancelling Save As from the close prompt ABORTS the close"* rule, which survives unchanged;
`#### "Deploy this edit…"` — the picker is superseded by the menu, though its "delegates to the existing
gestures, no new write path" rule survives verbatim and must be restated), **§12** (Compare/Merge's entry
point moves off Tools), and **§27** (the `Ctrl+O / Ctrl+S / Ctrl+Shift+S / Ctrl+W` row **split** — Ctrl+S and
Ctrl+Shift+S removed, Ctrl+O/Ctrl+W kept — and a **new row for `CodeEditorDialog`'s carved-out Ctrl+S/Ctrl+W**,
which §27 does not currently document at all and which a reader of the amended table would otherwise assume
was deleted). **CREATE nothing.** Supersession Ledger rows needed for: File ▸ Save/Save As deleted;
**`Ctrl+S` deleted** (this is the big one — §27's Save row and §18.5's whole `Ctrl+S`-triggered Save-As flow
are pinned behaviour); Ctrl+Shift+S deleted (overriding §18.5's *"`Ctrl+Shift+S` stays project-only"* ruling);
`file.save` retired and the default toolbar dropping six → five; `.bak`-based Revert replaced by dirty-gated
Discard Changes; `Deploy this edit…` picker superseded; the `_wire_ddl_object_apply_seams` "Apply to Target
deliberately not wired" decision reversed for the projectless leg.

**Open questions:**
1. **BLOCKING — does an in-place `Save pgtp` survive, and what does Ctrl+S do on the Raw XML tab?** The
   owner's Raw XML list is `Compare/Merge pgtp` · `Save as new pgtp` · `Deploy .pgtp` — **none of which is
   "write the current buffer back to the file it came from."** For a §18.2 project the `.pgtp` working copy
   is a first-class checked-out artifact (§18.2) that Save writes in place and `Deploy .pgtp` later pushes to
   the sshfs source, so in-place save is load-bearing; projectless, it is the only way to save at all. Three
   readings, none safe to guess: (a) `Save as new pgtp` **is** Save As and a fourth entry `Save pgtp`
   (in place) was simply omitted — **triage strongly recommends this**, with Ctrl+S → `Save pgtp`;
   (b) Ctrl+S → `Save as new pgtp`, i.e. a file dialog on every save, which destroys the reflex the ruling
   exists to protect; (c) Ctrl+S → `Deploy .pgtp`, which puts an outward push one keystroke away and
   violates §18.5's *"an irreversible outward effect must not be one keystroke away."* Note the knock-on:
   if in-place save really is gone, then "buffer differs from disk" is true from the first keystroke onward
   and `Discard Changes` becomes "throw away the entire session" with no intermediate save point.
2. **Where does `Apply Changes to Target` land?** The owner removes it from Tools but it appears in no
   Deployment list. It is only meaningful while a comparison is loaded, it is a **write** with its own
   ambiguity gate, and it **replaces the app's open document** (`diff_merge_controller.py:300`'s
   `_reload(target_path)` is wired to `open_project_file`, `main_window.py:742`). Triage recommends it move
   to FQ-021's mode-scoped Compare/Merge surface alongside Next/Previous Difference, **not** to Deployment.
3. Does the always-visible `Save` of item 3 above get a named entry *in addition* to the per-tab ones, or
   does the owner prefer the per-tab entries alone plus a hidden Ctrl+S binding? (Triage: a hidden,
   unnamed, unpinnable Ctrl+S is the discoverability defect this whole entry exists to fix.)

**RESOLVED 2026-08-08 — all three of the above are settled; they are left in place as the record of what was
asked.** (1) **In-place save survives as `Deployment ▸ Save pgtp`, and `Ctrl+S` dies** — the owner ruling
block at the top of this entry is final and supersedes an intermediate answer that kept a menu-less Ctrl+S.
(2) `Apply Changes to Target` goes to **FQ-021** (item 11). (3) Moot: there is no keystroke save, so the
per-tab named entries are the whole surface, and `file.save` retires rather than being re-pointed (item 3).

**Open questions (for the owner):**
1. **Does `PhpFileTab`'s own `Ctrl+S` die too?** Verified in item 4a: it is a real per-tab event filter
   (`php_file_tab.py:389-390`), independent of `File ▸ Save`, so it **survives the deletion unless explicitly
   removed** — leaving the PHP tab as the single tab in the app where Ctrl+S saves. Triage recommends
   **removing it**, for consistency with the ruling and because "Ctrl+S works here but nowhere else" is a
   worse discoverability state than "Ctrl+S works nowhere." Flagged rather than assumed, because it is a
   deletion of working behaviour the ruling did not name. (The same filter's Ctrl+Z/Ctrl+Y must stay.)
2. **Should `Ctrl+S` be bound to a SIGNPOST rather than left dead?** With the key unbound, pressing it does
   nothing at all — no write, no message. That is the *safe* failure, and it is what the ruling literally
   asks for. But for a reflex this strong the likely first reading is *"the app is broken / my work is
   unsaved"*, and the user's next action is to press it again. **Option, entirely the owner's to decline:**
   bind `Ctrl+S` to a **pure discoverability affordance** — writes nothing of any kind, touches no file and no
   database, and only shows a status-bar line naming where saving now lives (e.g. *"Saving is on the
   Deployment menu — Save pgtp."*). This is a signpost, **not a partial walk-back**: it cannot save, so it
   cannot save the wrong thing, which is the property the ruling exists to guarantee. It also has a precedent
   in this codebase's own posture — §7/§26 repeatedly prefer *stating* an unavailability over a silent
   absence (FQ-009's destination picker, `install_gate`'s verbatim reason strings). Declining it is coherent
   too; recorded so the choice is made rather than defaulted into.

**RESOLVED 2026-08-08 by the owner — questions 1 and 2 above are settled. Left in place as the record.**

- **Q1 — `PhpFileTab`'s `Ctrl+S` dies too.** Owner's words: *"Dies at all, inconsistency is a bad driver."*
  Remove the `Key_S` branch from `php_file_tab.py`'s `eventFilter` (the `Key_Z`/`Key_Y` branches STAY —
  §18.5 carve-out 1). After this there is **no Ctrl+S anywhere in the app** except the carved-out
  `CodeEditorDialog`, where it is the modal's OK button and writes nothing. "Ctrl+S works here but nowhere
  else" was judged a worse state than "Ctrl+S works nowhere", which is the whole reasoning: the value of the
  deletion is that the reflex has **one** answer everywhere, so a user cannot learn a habit that is right on
  one tab and silently wrong on the next.
- **Q2 — the signpost is DECLINED.** Ctrl+S is left genuinely dead: no write, no message, no status line.
  Implementers must not add one back as a "helpful hint" — the owner was asked directly and said the key
  dies. If field testing later shows users pressing it repeatedly and assuming data loss, reopen this as a
  new entry rather than treating it as an oversight to be quietly patched.
- Consequence of Q2 for the manual: since nothing on screen will explain the silence, `manual.md` carries the
  full weight of teaching where saving lives. The Keyboard Shortcuts chapter must state that **Ctrl+S is
  deliberately unbound and why**, not merely omit the row — an absent row reads as an oversight, and a user
  hunting for a lost shortcut needs to find the answer where they are looking.
3. Whether `Deploy .pgtp` (today one of §18.2's five File-menu project actions) is **moved** to Deployment or
   **mirrored** on it. Triage recommends moved: it is meaningful only with Raw XML active, and §18.2's project
   group loses nothing else.

---

## FQ-021: Compare/Merge becomes a mode; `Bookmarks` is renamed `Navigation` and gains the Difference commands
**Status:** PROCESSED (`75e2cdb` mode + read-only reasons, `1d53abd` Bookmarks→Navigation, `1ccfe9d` the
three mode-only members) — all three legs.

**The third leg closed a live REGRESSION, not just a queue entry.** FQ-020 removed `Apply Changes to
Target` from Tools expecting this entry to rehome it, leaving the comment *"Until FQ-021 lands it has no
menu home"* — and it never landed. So for a period a user could enter Compare/Merge mode, step every
difference and check them, and have **no gesture anywhere in the app** that wrote them to the target file.
The implementation was intact and tested the whole time; it was simply unreachable. Found by
`spec-harmonizer`, not by a test.

**The gate is the MODE, not the tab**, which `enter_diff_merge_mode`'s own docstring had already argued for
the read-only lock: the user may tab back to Raw XML mid-comparison. `leave_diff_merge_mode` sets the
current index to Raw XML, which emits nothing when Raw XML is *already* current — a reachable state via
the panel's Close button — so wiring visibility to `currentChanged` alone would have left three commands
visible after the mode ended. A test asserts zero `currentChanged` emissions while the members still hide.

`set_bookmarks_enabled` stopped disabling the whole `QMenu`, as its own docstring had predicted this pass
would have to.
**Requested:** 2026-08-08
**Idea (verbatim/summarized):** "Compare/Merge becomes a mode, mirroring Caption Mode: an
`enter_diff_merge_mode()`/`leave_diff_merge_mode()` pair that sets the Raw XML editor read-only, because a
hand edit can't participate in the merge and is discarded by the reload. `Bookmarks` → `Navigation`, gaining
`Next Difference` / `Previous Difference` **moved from Tools** — they already exist, this is a move, not new
commands — and visible only while in Compare/Merge mode." Settled in an owner review session.

**Problem — the read-only argument is verifiable, not a hunch:**
- The diff's **source is the parsed model**, never the Raw XML text: `DiffMergeController.compare_two_files`
  reads `self._project()` (`diff_merge_controller.py:123`), injected as `lambda: self._doc_ui.project`
  (`main_window.py:738`). A hand edit typed into Raw XML and not reparsed **cannot participate** in the
  comparison, while the editor happily accepts it.
- Then it is **destroyed**: `apply_changes_to_target` deep-copies the target's tree, applies the checked
  differences, writes a `.bak` beside the target, writes the target — and ends with `self._reload(target_path)`
  (`:300`), wired to `open_project_file(path)` (`main_window.py:742`), which **replaces the app's open
  document with the target file**. Any unsaved Raw XML edit made during the comparison is gone with no
  prompt.

So read-only-during-the-mode does two things at once: it stops the app implying an edit will count, and it
closes a live silent-data-loss path.

**Also verified:** Diff/Merge is a **hidden fixed tab** (`center_stage.py:151`, hidden at `:200`), and
Caption Mode's pair is literally `setTabVisible` + `xml_editor.setReadOnly(True)` (`:312-326`) — so the new
pair is a direct mirror. Today the three compare entry points just call
`setCurrentIndex(diff_merge_tab_index)` with no mode concept at all. Tools already carries
`Compare / Merge Two Files...`, **`Next Difference`**, **`Prev Difference`**, `Apply Changes to Target`
(`main_window.py:3882-3888`) — the two Difference commands are a **move**, and nothing new is authored.

**Proposed approach:**

- **`CenterStage.enter_diff_merge_mode()` / `leave_diff_merge_mode()`**, mirroring the caption pair:
  reveal + focus the Diff/Merge tab and `xml_editor.setReadOnly(True)`; reverse on leave. Called from the
  three compare entry points instead of their bare `setCurrentIndex`.
- **The mode outlives a tab switch, exactly like Caption Mode.** The user may tab back to Raw XML while a
  comparison is loaded and it must still be read-only — that is the whole point. So the visibility refresh
  for the mode's members hangs off the **mode transition**, not off `center_stage.currentChanged`.
- **`leave_diff_merge_mode()` must run before the reload.** `apply_changes_to_target` reloads at its very
  last statement; `open_project_file` → `setPlainText` into a **read-only** `XmlEditor` would either no-op
  or land in a widget the user then cannot edit. Sequence it explicitly and test it.
- **REQUIRED: an exit gesture that is not Apply. There is none today.** The Diff/Merge tab is **not** in
  `CenterStage._closable` (manual/xsd/ddl only), so it has no ✕, and the three compare entry points have no
  counterpart. **Mirror Caption Mode's exit exactly:** caption mode leaves via a *panel-owned* close
  callback, not a tab ✕ — `main_window.py:420` assigns
  `self.center_stage.caption_management_panel._on_close = self._close_caption_mode`, which calls
  `center_stage.leave_caption_mode()`. So `DiffMergePanel` gets its own Close affordance whose `_on_close`
  calls `leave_diff_merge_mode()`. Preferred over making the tab closable, because it is the established
  idiom for a *mode* (a mode is not a tab, and `_closable`'s three members are all plain tabs).
  Without this, entering the mode is a one-way door until Apply.
- **`Apply Changes to Target` moves here** (settled 2026-08-08; removed from Tools by FQ-020, and
  deliberately **not** placed on FQ-020's `Deployment` menu). It belongs on this mode-scoped surface beside
  the two Difference commands because it is only meaningful while a comparison is loaded, and because
  hosting it next to `Run on quality` would put two very differently-shaped irreversible actions under one
  menu. It is therefore a **third mode-only member** of `Navigation`, gated the same way — which makes the
  menu's name slightly strained (an apply is not navigation); see open questions.
- **`Bookmarks` → `Navigation`**, gaining `Next Difference` / `Previous Difference` moved off Tools, with
  the two Difference actions `setVisible(False)` outside the mode. The four bookmark actions stay
  **always visible** — they are per-*editor*, not per-mode — so the menu itself is never hidden.
- **Against FQ-016's recorded reason for not gating `Parsing`:** that reason was specifically that
  `Validate Project` is one of the **six default** toolbar buttons, so gating it would make a *default*
  button blink out on a fresh install. Next/Previous Difference are not defaults, so the governing
  precedent is `Select ▸ Select Parent Block` (FQ-015): hide the **action**, accept that a *user-pinned*
  button appears and disappears. Verified safe for enumeration:
  `ToolbarController._walk_menu_actions` (`toolbar_controller.py:212-268`) never tests `isVisible()`, so
  hidden actions remain in Customize Toolbar's Available list and keep stable ids.

**Two consequences the review did not name — both verified, both landmines:**

1. **The rename must NOT go into `LEGACY_ID_ALIASES`.** `ICON_ID_BY_COMMAND` is that dict **inverted**
   (`toolbar_registry.py:88-90`), so a row `{"bookmarks.next-bookmark": "navigation.next-bookmark"}` makes
   `icon_id_for("navigation.next-bookmark")` return `"bookmarks.next-bookmark"` **as an icon id**;
   `icons.load_svg_text` raises `KeyError` for it (`icons.py:131-141`), swallowed by `_set_action_icon`'s
   bare `except Exception: pass` (`toolbar_controller.py:378-382`) — so it will not crash, it will silently
   produce a wrong id-space mapping and permanently defeat any later default-icon binding for those
   commands. FQ-016 could safely edit `LEGACY_ID_ALIASES` because it **updated existing legacy rows** whose
   values are legacy *action* ids. A rename needs its **own** table (e.g. `RENAMED_ID_ALIASES`) consulted by
   `resolve_ids` and `resolve_icon_assignments` and deliberately **not** inverted into `ICON_ID_BY_COMMAND`.
   The same table carries `tools.next-difference → navigation.next-difference` and
   `tools.prev-difference → navigation.previous-difference`. **Note the label drift:** Tools says
   *"Prev Difference"*, the owner writes *"Previous Difference"* — the label change is itself an id change,
   **Settled 2026-08-08: `Previous Difference`**, matching `Previous Bookmark`. So the alias row is
   `tools.prev-difference → navigation.previous-difference`, and the label change is part of the move.
2. **PRECONDITION OF THIS ENTRY (not an implementation note): the read-only flag needs a reasons-set
   refcount — two modes cannot share one boolean.** Both `CenterStage.leave_caption_mode()` and the new
   `leave_diff_merge_mode()` call `xml_editor.setReadOnly(False)` **unconditionally**. Entering Compare/Merge
   while Caption Mode is active — or the reverse — and then leaving *one* **re-enables editing while the
   other mode is still on**, silently breaking the invariant each mode exists to enforce. **Settled
   2026-08-08: implement a set-of-reasons refcount** on the read-only state (`{"caption", "diff"}`;
   read-only while non-empty; each `enter_*` adds its reason, each `leave_*` discards only its own). Rejected
   alternative: explicit mutual exclusion (refuse to enter one mode while in the other) — it would forbid a
   comparison during caption work for no real reason. Naive mirroring of Caption Mode produces this bug **by
   default**, so it must be built with the mode, not after it, and it needs its own test (enter both, leave
   one, assert still read-only).

**Alternatives considered:**
- **Leave `Next`/`Prev Difference` on Tools and only add the mode.** Rejected by the owner, and it would keep
  two navigation homes — the exact complaint the Editor menu bar exists to fix.
- **A dedicated Diff/Merge toolbar or panel-local buttons.** Rejected: §7's toolbar is user-curated and not
  app-decided, and a third navigation surface for two commands that already exist is pure duplication.
- **Make Raw XML read-only only while the Diff/Merge tab is *current*, rather than for the mode's duration.**
  Rejected on the evidence above: the destroyed-edit path fires inside `apply_changes_to_target` regardless
  of which tab is showing, so a tab-scoped read-only would leave the data-loss window wide open.
- **Fix only the data loss** (prompt before the reload) and skip the mode. Rejected: it leaves the deeper
  falsehood — an editable buffer whose edits are structurally excluded from the merge — in place.

**Suggested placement:** EXTEND **§12 (Diff / Merge)** as the primary landing section — it owns the three
comparison entry points, the ambiguity gate and Apply; it must record the mode, the read-only rule, the
parsed-model-not-buffer source, and the fact that Apply **replaces the app's open document**. Also EXTEND
**§26** (the Editor menu bar: `Bookmarks` → `Navigation` plus the two moved members; the window bar's Tools
inventory loses them), **§7** (the new rename-alias table and its deliberate separation from
`LEGACY_ID_ALIASES`/`ICON_ID_BY_COMMAND`; the third accepted instance of hiding an *action*), and
**§13/§8** (the shared `xml_editor.setReadOnly` between Caption Mode and the new mode — the collision
above). **CREATE nothing.** Supersession Ledger rows: the `Bookmarks` menu renamed (every `bookmarks.*` id
changes); `Next`/`Prev Difference` moved off Tools and relabelled; `Apply Changes to Target` moved off Tools;
Compare/Merge becomes a mode with a panel-owned exit; the Raw XML read-only flag becomes a reasons set shared
with Caption Mode.

**Open questions:** three of the four raised on 2026-08-08 are **settled** and folded into the body above:
the read-only collision resolves to a **reasons-set refcount** (a precondition of this entry, not a note);
**`Apply Changes to Target` moves here**, not onto Deployment; and the mode's exit is a **panel-owned
`_on_close`** mirroring Caption Mode's, not a tab ✕. What remains:
1. **`Navigation` now hosts a write gesture.** With `Apply Changes to Target` here, the menu holds three
   mode-only members of which one is irreversible and *replaces the app's open document*. The name is
   strained and the grouping mixes navigation with an apply. Options for the owner: accept it (one menu, all
   Compare/Merge affordances together); or put a separator and a sub-grouping label; or give Apply its own
   home on the `DiffMergePanel` itself (which is where the mode's Close already lives, and where a panel-local
   button would be adjacent to the checkboxes it consumes — triage mildly prefers this, since it also keeps an
   irreversible write off a keyboard-navigable menu, consistent with §18.5's *"an irreversible outward effect
   must not be one keystroke away"*).
2. **§26 already records a not-yet-implemented target design that the whole `Bookmarks` menu and its actions
   are *disabled together* while Caption Mode is active** (gutter toggling stays usable). That now has to be
   reconciled with a renamed menu that also hosts mode-only members: disabling `Navigation` wholesale during
   Caption Mode would also kill Difference navigation, which has nothing to do with captions.

---

## FQ-022: A sandbox-scoped DDL Explorer — implementing §18.7's second instance
**Status:** PROCESSED (aa7a0e1; spec §18.7/§26) — two Database entries (`DDL Explorer (Quality)` / `DDL Explorer (Sandbox)`) and two dock tabs, driven by ONE role-parameterized fetch/open/lockstep/navigate path rather than a parallel implementation. **SESSION-FREE**, as §18.5 D2's read/write split allows and `refresh_capability_status` already proved: the predicate is `bool(sandbox.host)` via `_configured_sandbox_params()`, never `has_session`, and tests pin that opening the Explorer opens no session and that the session-keyed refresh does not close one. `active_target_params()` stays the sole target selector (BUG-034) — the sandbox path never touches it. The Sandbox entry exists at startup but is hidden until a qualifying project opens (or `Sandbox Setup...` adds a sandbox later, the one transition that does not rebind the controller), so `_walk_menu_actions` keeps enumerating it for Customize Toolbar and queued FQ-012; it disappears on project close, taking its tab rather than leaving a closed project's sandbox on screen.

**Three things §18.7 asks for that are deliberately NOT built, because the foundation is target-shaped and faking them would lie:** the sandbox tree renders **unmarked** (`compute_drift_markers` compares against a deployed-to-TARGET reference, so those markers on a sandbox row would show quality's drift); §18.6's completion `SchemaIndex`/`_ddl_schema` are **not** repointed by a sandbox fetch (an open object tab's completions must describe the lane its Apply will hit); and **no second reachability probe** was invented (item 3) — an unreachable sandbox reports in the status bar and the toggle springs back, matching the existing never-raises posture. Item 4 (reset/destroy) is also unimplemented; re-toggling re-fetches, which is a manual refresh.

**Item 5 stays OPEN and unanswered.** The sandbox tree is browse-only: no `Edit DDL`, no creation entries, suppressed at build time (`browse_only=True`) rather than by dangling a signal into nothing, which would be exactly the dead control carve-out 2 forbids. `open_ddl_object_tab`'s unused `key=` seam is untouched and still reserved for whatever the owner decides — under FQ-024's one-key rule an object with the same identity in both databases would otherwise collide on one tab.

**Two deviations from §18.7 wanting a ledger note:** the two Explorer tabs are **fixed at construction**, not dynamic key-addressed as the spec describes (converting would churn `find_controller`'s identity checks and ~90 test references for no user-visible difference); and **`RENAMED_ID_ALIASES` was created here**, in `toolbar_registry.py`, because §18.7 asked for a row in a table FQ-021 has not built yet — it ships with the one row this feature needs (`database.ddl-explorer` -> `database.ddl-explorer-quality`), consulted by `resolve_ids` and `resolve_icon_assignments` and inverted by nothing, and FQ-021 extends it. Tests: new `tests/ui/test_ddl_explorer_sandbox.py` (22) + 3 in `test_toolbar_registry.py`. Suite 4768 passed, 45 skipped.
**Requested:** 2026-08-08
**Idea (verbatim/summarized):** The owner's original framing: *"I see in the browser quality but not sandbox,
and I can apply to sandbox, but not quality."* The second half of that sentence is FQ-020's `Run on quality`;
this entry is the first half — a DDL Explorer instance that browses the **sandbox**, so the two directions
stop being asymmetric.

**Problem:** There is exactly **one** `BrowserPanel` (`ui/ddl_buffer_panel.py`), one left-dock "DDL Objects"
tab, one center `EditorPanel` DDL Explorer tab and **one** connection feeding all of it (§18.1) — the
**target**. Meanwhile the sandbox is the database the user's edits actually accumulate in (§18.5 D2: *"the
sandbox therefore **is** the desired state"*), and it is the one they cannot see. So the app applies to a
database it will not show, and shows a database it will not (yet) apply to. Nothing in the shipped UI can
answer *"what is currently in my sandbox?"* beyond the Sandbox Setup dialog's flat working-set list
(`SandboxSession.applied()`).

**This is EXTEND, not CREATE: §18.7 already exists as settled design (2026-08-05), not yet implemented.**

**What §18.7 already settles — do NOT re-decide any of this:**
- Two instances, both live simultaneously; each is **its own left-dock tree tab and its own center-stage
  editor tab**, never a toggle switching one shared pair between connections.
- `BrowserPanel` and `EditorPanel` are **instantiated twice, internals unchanged** — both already take a
  `DatabaseSchema` via `set_schema(schema, spans)` and a synthesized buffer via `set_ddl_text`, and neither
  is target-vs-sandbox-aware today or needs to become so. What changes is *how many are constructed and what
  params feed each fetch*.
- `CenterStage`'s single fixed `ddl_tab_index` becomes **two dynamic, key-addressed tabs**, reusing §18.5
  carve-out 9's append-only/tail-only machinery and its mandatory regression test. **The key is the connection
  role** (`"target"`/`"sandbox"`) — exactly one connection of each role exists per project.
- `MainWindow`'s single-instance wiring (`_open_ddl_explorer`, `_fetch_ddl_schema`,
  `_on_ddl_navigate_requested`, the menu-toggle↔tab-✕ visibility lockstep) is **parameterized by role, not
  duplicated**.
- **Drift markers are computed per source connection, not shared.** The target instance renders §18.2's
  `*`/`!` against the target's introspection; the sandbox instance renders against the sandbox's own
  introspection and its own working-set bookkeeping (`SandboxSession.applied`, `text_sha1`). Two separate
  computations, not one markers set redrawn twice.
- **The trees must tolerate genuine divergence in the object set** — the sandbox is an independent, editable
  database, so its object set can differ. Each tree is built from **its own connection's introspection
  alone**: no cross-referencing, no merged tree, no placeholder for "exists on the other side."
- **No dead controls:** no second Explorer entry at all until a sandbox exists (mirroring §18.5 carve-out 2).
- **Explicitly not designed there, and still not here:** any merged/diffed side-by-side view of the two trees
  (rejected by the divergence rule — a different, undesigned feature).
- Edit from **either** instance opens the same editor tab type; which connection an edit targets is governed
  entirely by the existing Apply gestures and their gates. Browsing the sandbox does **not** make
  Apply-to-Sandbox implicit and does not relax Apply-to-Target's preconditions.

**What §18.7 leaves TBD, and what this entry adds:**
1. **The menu wording and placement of the second entry** — §18.7 says verbatim that this is *"an
   implementation detail, not specified further here."* §26 currently sketches it as *"the DDL Explorer
   toggle gains a sandbox-scoped sibling."* Concrete proposal: two checkable Database-menu entries,
   **`DDL Explorer (Quality)`** and **`DDL Explorer (Sandbox)`**, the second **absent** until a sandbox
   exists. Rationale for renaming *both*: leaving the first as bare `DDL Explorer` next to an explicitly
   sandbox-scoped sibling makes the unlabelled one ambiguous. **Consequence that must be handled:** renaming
   it changes its command id (`database.ddl-explorer` → `database.ddl-explorer-quality`), so it needs a row
   in FQ-021's new `RENAMED_ID_ALIASES` table — **not** `LEGACY_ID_ALIASES`, for the
   `ICON_ID_BY_COMMAND`-inversion reason recorded in FQ-021. ("Quality" rather than "Target" matches the
   §18.8 node name and the owner's own vocabulary.)
2. **THE CORRECTION THAT SHAPES THIS ENTRY: the sandbox Explorer is SESSION-FREE.** A concern was raised
   that §18.7's Explorer needs a sandbox connection and therefore collides with
   `Database ▸ Open Sandbox Session` being a manual act. **It does not, and this must be recorded so nobody
   re-introduces the coupling.** §18.5 D2 pins `open_sandbox(params, runner) -> SandboxSession` as *"the
   **only** gate… Everything that writes goes through the returned session"* and then states explicitly:
   ***"Reads (probe, listing, introspecting the target for a baseline) are not gated."*** The Explorer is a
   pure read — `db/introspect.py::fetch_routines_and_triggers` over the sandbox's `ConnectionParams`. It needs
   **params, not a session.** Live proof this already works: `ddl_project_controller.py:505
   refresh_capability_status` (called from `set_active_project`) already runs `probe_sandbox_capabilities`
   over a real sandbox connection at project-open time with **no session open**.
   - **Therefore the availability predicate is `bool(sandbox_params.host)` — the same
     `sandbox_configured` convention `_target_is_configured` documents (`main_window.py:2633-2647`) — and
     explicitly NOT `sandbox_controller.has_session`.** Whoever implements this must not wire the second
     Explorer's presence into `_refresh_sandbox_affordances`'s session-keyed visibility set
     (`main_window.py:3390`), which is where the instinct will lead.
   - Corollary: opening the sandbox Explorer must **not** open a session as a side effect, and closing a
     session must **not** close the sandbox Explorer.
3. **`refresh_target_connection_status` has no sandbox twin for the fetch path.** BUG-030 added a real
   off-thread `SELECT 1` for the target (`ddl_project_controller.py:550`). The sandbox fetch should report an
   unreachable sandbox the same way rather than surfacing a raw exception — reuse that shape, do not invent a
   second reachability notion (this is also the engine FQ-018's status-bar indicator consumes, so a third one
   would be the anti-duplication trap that entry already calls out).
4. **What happens to an open sandbox Explorer when the sandbox is reset or destroyed mid-session** — §18.7
   lists this as an open question and it is still open. Note `SandboxSession.reset()` is schema-level
   (`DROP SCHEMA … CASCADE` + re-run baseline), so the object set can empty out under a live tree.
   Recommendation: on a completed reset, **re-fetch** the sandbox instance if its tab is open (a reset is a
   user-initiated, expected change, unlike §18.5 carve-out 5's incidental drift), and leave open *object
   editor* tabs untouched and silent per carve-out 5. Flagged, not settled.
5. **§18.1's "no context menu on table nodes" and FQ-024's single `Edit DDL` both now apply twice.** With
   FQ-024 landed, `Edit DDL` from the **sandbox** tree keys on `ref.key` and — in project mode — would take
   the checkout branch, seeding `ddl/*.sql` **from the sandbox's definition**. That is almost certainly wrong:
   the checked-out file's reference point is the *deployed* target definition (§18.2's drift markers compare
   against `ProjectSettings.deployed`), so seeding a checkout from the sandbox would poison the drift
   baseline. **Required:** `Edit DDL` invoked from the sandbox instance must **not** perform a checkout —
   either it always takes the projectless/live-source branch, or it is offered only for viewing. This
   interaction is not covered by §18.7 (written before FQ-024) and is the sharpest correctness risk in the
   feature.

**Alternatives considered:**
- **One Explorer with a connection dropdown** (switch the single instance between target and sandbox).
  Rejected by §18.7 itself — the point is comparing/working with both at once, and a toggle also forces one
  shared drift-marker computation, which the per-connection rule forbids.
- **A merged tree showing both databases with divergence badges.** Rejected by §18.7's "tolerate genuine
  divergence, no cross-referencing" rule; recorded here because it is the intuitive design and it is
  explicitly out of scope.
- **Reuse the Sandbox Setup dialog's working-set list instead of a tree.** Rejected: `applied()` lists only
  what *this app* applied, not what the sandbox actually contains (baseline objects, anything applied
  out-of-band), so it cannot answer the owner's question.

**Suggested placement:** **EXTEND §18.7** — it is the section, it is already written, and it is marked *"not
yet implemented."* The implementation pass should (a) flip its status header, (b) fill in the menu wording
left open (item 1), (c) **add the session-free rule of item 2 as an explicit statement**, since §18.7 never
says it and its absence is what caused the coupling concern in the first place, (d) resolve or restate its own
reset/destroy open question (item 4), and (e) add the FQ-024 interaction of item 5, which post-dates it. Also
touch **§26** (the Database menu's two Explorer entries and the rename) and **§7** (the `RENAMED_ID_ALIASES`
row, and `CenterStage`'s fixed `ddl_tab_index` becoming two role-keyed dynamic tabs). Supersession Ledger row
for the `DDL Explorer` menu-entry rename (id change) and for the fixed→dynamic tab change.

**Open questions:**
1. **Item 5 — what `Edit DDL` does from the sandbox tree in project mode.** Triage's position is that it must
   not seed a checkout from the sandbox; the owner should confirm whether the sandbox tree offers `Edit DDL`
   at all, or is read-only/browse-only for v1.
2. **Item 4 — the reset/destroy behaviour** (re-fetch recommended).
3. Whether the **left-dock** gets two "DDL Objects" tabs (§18.7's letter) or one tab with a role selector.
   §18.7 says two; triage flags only that the left dock already hosts several tabs and two same-named trees
   need distinguishable labels for the same reason the menu entries do.

---

## FQ-023: Make the three session-gated sandbox gestures present-and-reporting (and decide whether the sandbox session opens lazily)
**Status:** PROCESSED (`1df4ecf`) — the gestures state their reason instead of vanishing.

**⚠️ This entry's own ruling was REVERSED the next day.** It records Option B (lazy-open) as *"REJECTED by
the owner"*; **BUG-040 (2026-08-09) reversed exactly that** — the sandbox session now auto-connects on
project bind, and `Database ▸ Open`/`Close Sandbox Session` were deleted outright. The
present-and-reporting behaviour this entry shipped is what makes that survivable: a failed auto-open still
leaves a visible gesture that states the reason and offers an inline `Open`. Read BUG-040 before treating
anything below about session lifecycle as current. Original text follows unchanged.

**Superseded detail:** DECIDED 2026-08-08: Option A. Option B (lazy-open) was REJECTED by the owner, whose
words were *"Don't open lazily, it needs to be an explicit decision."* So: the three gestures become
present-and-reporting, and `Database ▸ Open Sandbox Session` **stays an explicit user act**. Implement Option
A only; Option B's analysis below is kept as the record of what was weighed, not as a live alternative.

Two consequences of that ruling for whoever implements this:
- **The inline *"Open a session now"* offer in Option A is still in scope** — it is not lazy-open. The
  distinction the owner is drawing is between the session opening *as a side effect* of some other gesture and
  it opening because the user clicked a thing that says it will open a session. A refusal that names the fix
  and offers it as an explicit click is the second kind, and it is what makes the reporting useful rather than
  merely honest. If in doubt, the safe reading is: **no connection is ever attempted without a click whose
  label says a session will be opened.**
- **`open_sandbox` stays the single ownership chokepoint** and `Sandbox Setup…` stays
  `ForeignDatabaseError`'s principal home, so triage objection 1 below never comes into play.
**Requested:** 2026-08-08
**Idea (verbatim/summarized):** Raised during triage of FQ-022, not by the owner. §18.7's sandbox Explorer
was thought to need a live sandbox session, which would collide with `Database ▸ Open Sandbox Session` being
a manual act; the proposal was to have the session **open lazily on first use** (keeping `open_sandbox`'s
ownership gate and `Close Sandbox Session`, and demoting or deleting `Open Sandbox Session`). **That premise
turned out to be wrong for the Explorer** — FQ-022 item 2 establishes the Explorer is a pure read and needs
no session at all. But the *underlying* complaint survives and is separable, which is why it is its own
entry rather than a ride-along.

**Problem — an invisible prerequisite, which is the same defect class as the `[Check] tier3: unavailable`
confusion the owner already hit.** `MainWindow._refresh_sandbox_affordances` (`main_window.py:3390-3415`)
binds **visibility, never enabled-state**, per §18.5 carve-out 2 (*"with no live session the control is
ABSENT, not greyed out"*). Concretely: with a project open **and** a sandbox configured **but no session
opened**, `Check Object in Sandbox`, `Check Object Without Applying` and `Sandbox SQL Console…` are **absent
from the menus entirely**. A user looking for "check my function" finds nothing, and nothing anywhere tells
them the missing precondition is a menu item three separators away. §18.8's Project Status window has the
same shape for its two session-dependent node actions (`_refresh_project_status_sandbox_actions`, which hands
the panel `None` so it renders no button at all).

Carve-out 2's posture is *"no dead controls"* — which is right when the control is genuinely inapplicable
(no sandbox configured at all). It is the wrong tool when the control is **one click away from applicable**:
absence cannot state a reason, and a reason is exactly what the user needs.

**Additional fact that makes the posture worth revisiting rather than just documenting.**
`ui/sandbox_controller.py:505 set_project` states as a principle that it *"opens nothing and provisions
nothing"* — but `ui/ddl_project_controller.py:505 refresh_capability_status`, called from
`set_active_project`, **already runs `probe_sandbox_capabilities` over a real sandbox connection at
project-open time.** So the "we never touch the sandbox until you ask" principle is already violated by
project-open itself, and the docstring is describing an intent the surrounding code does not honour. That is
the strongest argument that the manual-session posture is a leftover rather than a considered stance — and it
is also, on its own, a spec-vs-code drift worth correcting whichever option is chosen.

**Two options for the owner — deliberately not pre-decided:**

**Option A (smaller; triage's default recommendation): keep the manual session, make the three gestures
present-and-reporting.** They stay visible whenever a sandbox is *configured*, and clicking one with no
session states the reason and offers the fix — reusing the exact pattern already built for the destination
picker, which does not hide an unavailable destination but **states why**
(`ddl_object_editor.py:107-109`: *"Why a destination is NOT on offer, stated to the user in the picker rather
than left as a silent absence (FQ-009: the requester's complaint was 'there is no…')"*), and whose refusal
text for the sandbox destination **already reads "Open Sandbox Session"**
(asserted in `tests/ui/test_ddl_object_editor.py:1238`). So the app already contains both the pattern and the
sentence; the menus simply do not use them.
- Carve-out 2 is **narrowed, not overturned**: absent when no sandbox is configured (genuinely
  inapplicable), present-and-reporting when a sandbox exists but no session is open (one click from
  applicable). That distinction is the actual content of the change.
- Optionally, the refusal offers *"Open a session now"* inline — which is lazy-open **behind an explicit
  user click**, keeping every property Option B risks.

**Option B (the original proposal): open the session lazily on first use**, keeping `open_sandbox`'s
ownership gate and `Close Sandbox Session`, and demoting or deleting `Open Sandbox Session`.
Triage's objections, recorded so they are weighed rather than rediscovered:
1. **It relocates `ForeignDatabaseError` to a moment the user did not ask to connect.** §18.5 D2 makes
   `open_sandbox` the single ownership chokepoint and mandates that the refusal be shown **together with the
   "Create a sandbox database for me" offer** (*"a refusal without a way forward is the fastest route to the
   user concluding the tool is broken"*), with **Sandbox Setup… as its principal home**. Firing it implicitly
   from a Check or a console keystroke means a hard "PGTP Editor did not create this database" modal appears
   in a context that has no natural place for the create-a-sandbox-for-me remedy.
2. **§18.8 flicker.** `_refresh_project_status_sandbox_actions` makes the Project Status window's two
   session-dependent node buttons appear/disappear with `has_session`. Lazy-open makes them materialize as a
   side effect of unrelated gestures, so a window whose job is to *report state* would change shape for
   reasons it does not explain.
3. **Ownership of teardown becomes asymmetric.** A session the user never opened, but must explicitly close,
   is a strange contract — and `Close Sandbox Session`'s own visibility gate (`has_session`) would make it
   pop into the menu unprompted.
4. It does not buy the Explorer anything (FQ-022 item 2), so its whole justification rests on the three
   session-gated gestures — which Option A addresses directly.

**Alternatives considered:** doing nothing and documenting the prerequisite in the manual only — rejected:
the manual cannot be read from an absence, and §26/§7 already treat "the menu advertises one thing while the
key does another" as a defect class to eliminate rather than annotate. Also considered: making the three
gestures **disabled** rather than absent — rejected as the worst of both, since a greyed control with no
tooltip states even less than a stated refusal and directly contradicts carve-out 2's letter.

**Suggested placement:** EXTEND **§18.5 carve-out 2** (the no-dead-controls posture — this narrows it, and a
narrowing of a pinned carve-out needs a Supersession Ledger row) and **§18.5 D2** (the ownership gate's
single-chokepoint property, and the `set_project` "opens nothing" claim that project-open already
contradicts — that drift should be corrected regardless of which option wins). Also **§26** (whether
`Open Sandbox Session` survives, and the three gestures' presence rule) and **§18.8** (the two node actions'
appearance rule). **CREATE nothing.** If Option B is chosen it additionally needs a ledger row for demoting
or deleting a documented menu action.

**Open questions:**
1. **A or B?** — owner decision, unmade. Triage recommends **A**, with A's inline *"Open a session now"* offer
   as the discretionary extra, because it delivers the entire user-visible benefit (never hunting for an
   invisible prerequisite) while leaving `open_sandbox`'s single explicit chokepoint, §18.8's stability and
   `Close Sandbox Session`'s symmetry untouched.
2. If **A**: does `Open Sandbox Session` stay a menu item, or become only the inline offer inside the
   refusals? (Triage: keep the menu item — it is also how a user re-opens after an explicit close.)
3. If **B**: where does `ForeignDatabaseError` surface, and does it carry the mandatory "Create a sandbox
   database for me" action in every implicit-open context? D2 requires the remedy travel with the refusal, so
   this must be answered before B is implementable, not after.

---

## FQ-025: ALTER-TABLE action set in the DDL Explorer — column/constraint/index/comment/table ops that generate DDL into an editable tab
**Status:** PROCESSED — all three slices (`bc02d9c` + `8a88da4` + `532da30` slice 1; `c19a09f` + `b8a005d`
slice 2; `ef46625` + `69c95b5` slice 3). Eighteen operations reachable from the DDL Explorer.

**The submenu groups what is SCOPED TO THE CLICKED TABLE, not what emits `ALTER TABLE`** — which is the
question the user is answering — so Create Index, Drop Index and Drop Table sit there despite none being an
ALTER, with Drop Table in its own final group away from a mis-click on Drop Index. `Create Table…` is the
exception, at top level on the Tables branch root (mirroring FQ-002's `New Function/Procedure…` on the
routines root) **and** on table and view nodes, because a node is the only thing in this tree that names a
schema — which is exactly what the dialog consumes.

**Three of this entry's factual claims were wrong** and are corrected here so they are not re-read as
design: column nodes did not exist at all (the tree had to grow a `Columns (N)` group); *"Apply-to-Target
is not wired"* was stale; and both *"slice 2 includes the `_CONSTRAINTS_SQL` widening"* and *"Drop index
needs the new index-introspection query"* were false — all introspection shipped with slice 1's batch.

**Open question 2 was settled AGAINST this entry's own recommendation:** constraint names are REQUIRED,
because an auto-name like `orders_qty_check1` is what makes the Drop and Rename pickers a guessing game
later. The one exception is `CREATE TABLE`'s primary key, emitted unnamed — the single case where
Postgres's auto-name is deterministic and conventional. Both are in the §28 ledger.

**Known limits, recorded rather than hidden:** `Deployment ▸ Save in Project` on a generated tab opens
Save As… and its label reads slightly off (FQ-026's scope); Apply-to-**Target** refuses these buffers,
since `parse_buffer_identity` finds no `CREATE` — Apply-to-Sandbox is the intended path; the sandbox
`applied` row is per-table for ALTERs, so successive ALTERs overwrite each other's bookkeeping, and a
`DROP INDEX` buffer has no table in its identity at all; and every tab is still titled `ALTER <table>`
regardless of contents, which the owner has ruled should be fixed.

Superseded detail from the slice-1 flip: SLICE 1 PROCESSED —
the eight **column operations** ship end to end: an `Alter Table ▸` submenu on table nodes and on the new
column nodes, a dialog per operation, and the generated DDL in an editable tab that executes nothing until
the user runs it. Slice 2 (constraints/FKs) and slice 3 (indexes/comments/whole-table) are NOT shipped;
slice 2's **introspection** landed early (`ConstraintInfo`/`IndexInfo`) since it cost no extra queries.

**This entry's premise about the tree was WRONG, and it changed the work:** it said column nodes existed
and merely lacked a context menu. They did not exist at all — table nodes carried only trigger children,
and columns lived solely in the Properties panel. The tree therefore gained a `Columns (N)` group per
table. Its claim that Apply-to-Target is *"NOT wired (a pre-existing gap)"* is also stale — that was wired
projectless on 2026-08-08.

**The design question the entry raised and left open is answered: `AlterDdlRef`.** An ALTER is not an
object, and `DdlObjectRef` cannot express one without lying — its `qualified` would render `pr.orders()`,
spelling a table as a zero-argument routine in every confirmation the panel raises. So a separate
duck-typed ref, `kind="alter"`, with `name=""` **deliberately**: `build_ladder` adds tier 3's
`plpgsql_check` only when a name is present, and an ALTER creates no function to analyse, so *"tier 3 was
never going to run"* is the honest state rather than a failure. Tiers 0-2 still run. A serial counter gives
each generation its own tab — without it `open_ddl_object_tab` focuses the first and **silently discards**
the second statement. Save-to-object is suppressed **structurally** (always `_edit_ddl_live`, never
registered in the deploy manifest), so no `ddl/<object>.sql` is seeded and no drift marker speaks for it.

**Three consequences recorded rather than papered over:** `Deployment ▸ Save in Project` on an ALTER tab
opens Save As… (its label reads slightly off); Apply-to-**Target** refuses these buffers, since
`parse_buffer_identity` finds no `CREATE` and precondition 1 blocks it — Apply-to-Sandbox is the intended
run path; and the sandbox `applied` bookkeeping row is **per-table** for ALTERs, so successive ALTERs on
one table overwrite each other's row. `SNAPSHOT_VERSION` also went 1→2, refusing v1 rather than loading it
with the two new sections empty.
**Requested:** 2026-08-08
**Idea (verbatim/summarized):** "new DDL actions. In ddl explorer currently on right click we have Add trigger. I would like to add to that menu: Add column, Delete column, Add foreign key, Delete foreign key, Add constraint, Delete constraint. Functioning: when 'Delete' something, it should open a modal asking for the table and the column in a dropdown, defaulting to the table and the column the click was coming from. Once clicked ok, it should open a new tab on explorer and display the alter table ddl. The user can run it or not to their discretion. The add column behaves the same, offering a modal with a table dropdown, defaulting to the table it was summoned from, and all the fields that an add column could have (name, datatype dropdown, nullable, comment). At confirming the window it should open a tab with the Alter table ddl. Add constrain should ask for constraint name, a column (defaulting to clicked), have a + sign to add more columns to it, and a dropdown for the constraint types. Add foreign key behaves the same, should offer to which column we are binding, and in another section a table choser, -> column list populated with columns of the chosen table." — expanded through a converged follow-up "offer more DDL options" round into the full action set below.

**Problem:** The DDL Explorer can *create* brand-new objects (FQ-002: Add Trigger…, New Function/Procedure…) but offers no way to *alter* an existing table. Any column add/drop/rename, type change, NOT NULL / DEFAULT toggle, constraint or FK add/drop, index create/drop, comment, or whole-table create/drop currently requires the user to hand-write ALTER/CREATE/DROP SQL elsewhere — exactly the "your only option is to break the DB by hand" gap this app exists to close. There is also no context menu on **column** nodes at all, so the click context (the specific column the user right-clicked) can't seed a dialog today. The generated-DDL-into-an-editable-tab safeguard already proven by FQ-002 (generation is inert; running is a separate explicit gesture) is the right shape to extend, not reinvent.

**Proposed approach:** Add a uniform ALTER/CREATE/DROP action set to the DDL Explorer, every action sharing ONE shape: right-click → dialog → generated DDL opens in an editable tab → the user runs it (Apply-to-Sandbox) or not. **The opened DDL tab IS the safeguard — no confirmation dialogs at generation time, not even for Drop table** (requester's principle: "the opened ddl tab is a sufficient safeguard when running it is explicit"; generating `DROP TABLE t` executes nothing). No typed-name confirmations, no scary modals anywhere.

*Menu layout.* A new **"Alter Table ▸" submenu** on the table node groups the add/drop/modify actions; FQ-002's create-object actions (Add Trigger…, New Function/Procedure…) stay at the top level. **Create table** (table-independent, like New Function/Procedure) sits at top level / on the routines-or-tables branch root, NOT inside "Alter Table ▸". **Column nodes gain a context menu** (they have none today) so a right-clicked column pre-fills the dialog's column dropdown ("defaulting to … the column the click was coming from"); the same actions are reachable from the table node (column defaults to first/none). Every "which table/column" field is a dropdown defaulting to the click context but changeable. **All new menu items must honor the existing `browse_only=True` suppression** (sandbox Explorer, §18.7) exactly as the current create actions do.

*Full action set (~18, confirmed).* **Column ops:** Add column (name, datatype dropdown, nullable, comment) · Drop column · Rename column · Change column type (with free-text `USING` clause — a type change without it fails on incompatible data) · Set/Drop NOT NULL · Set/Drop DEFAULT. **Constraints/FK:** Add constraint (constraint name, a column defaulting to the clicked one, a "+" to add more columns, a TYPE dropdown covering PRIMARY KEY / UNIQUE / CHECK / EXCLUDE) · Add foreign key (dedicated dialog: which local column(s) we're binding, plus a target-table chooser whose selection populates a target-column list) · **one unified "Drop constraint…"** (lists every constraint on the table with its TYPE shown — replaces BOTH the original "Delete foreign key" and "Delete constraint", since in Postgres a FK is a constraint and `ALTER TABLE … DROP CONSTRAINT name` is identical for all types) · Rename constraint. **Indexes:** Create index (unique toggle + method dropdown btree/gin/gist) · Drop index. **Comments:** Set table comment · Set column comment (`COMMENT ON …`). **Whole-table:** Create table (a multi-column builder — the largest single dialog) · Drop table.

*Reuse the FQ-002 pattern exactly.* Dialogs mirror `ui/new_trigger_dialog.py::NewTriggerDialog` / `ui/new_routine_dialog.py::NewRoutineDialog`: non-modal `.show()` (NEVER `.exec()` — §30 no-un-patched-modal rule), pre-bound context shown read-only, all dropdown data INJECTED by the caller (the dialog never queries a DB), headless accessors read after the `accepted` signal, OK disabled until valid, inline red error label driven by attempting the skeleton render. `NewRoutineDialog.COMMON_RETURN_TYPES` (~lines 87-100) is the precedent for the Add-column datatype dropdown: an editable combo seeded with common types, validated by the allowlist. Skeleton generation is new pure functions — `alter_*_skeleton()` / `create_table_skeleton()` / `drop_*_skeleton()` — added as siblings in `db/ddl_skeleton.py` (~lines 87-209 today hold `trigger_skeleton`/`function_skeleton`/`procedure_skeleton`), following its conventions verbatim: pure (no Qt, no DB), identifiers via `quote_ident()` (allowlist, raises `UnsafeIdentifierError`), datatypes via `_SAFE_DATATYPE_RE` (~line 75), errors as `SkeletonError`, never a partial return.

*Where the DDL lands + how "run it" works.* Reuse `ui/center_stage.py::open_ddl_object_tab(ref, text, …)` (~lines 560-585) — the SAME editable `DdlObjectEditorPanel` tab FQ-002's Add Trigger already opens, whose Apply-to-Sandbox is wired (`ui/main_window.py::_apply_ddl_object_to_sandbox` ~line 4008 → `SandboxController.run_apply`) = the requester's "run it or not." **CAVEAT for spec-maintainer:** that panel's Save-to-`ddl/<object>.sql` and object-Check semantics fit a NEW object (a trigger) but NOT an ALTER of an existing table (an ALTER is a mutation, not an object with its own source file). For ALTER-generated tabs the meaningful affordances are run-against-sandbox + copy-out, and Save-to-object should be suppressed/not-applicable — recommend spec-maintainer define an ALTER/scratch tab semantic (or a distinct tab kind) rather than silently reusing object-Save.

*Introspection split (drives the slicing).* Verified against `db/introspect.py`: **available in-memory today** (`DatabaseSchema` / `TableInfo.columns` / `ColumnInfo`) — column name, formatted type, is_pk, is_fk, is_nullable, default, comment, `ColumnInfo.fk_target` ("schema.table.column"), `TableInfo.kind`, `DatabaseSchema.types` (domains/composites). **NOT captured today** — constraint NAMES (`con.conname` never selected), UNIQUE constraints (`_CONSTRAINTS_SQL` ~lines 210-226 filters `contype IN ('p','f')` only), CHECK constraints (~line 297 comment: "deliberately NOT captured"), index definitions (no index query exists). Consequence: the *add/create* side needs no new introspection (the user supplies the name; or Postgres auto-names). The *drop/rename-existing-named-object* side (unified Drop constraint, Rename constraint, Drop index) MUST list existing named objects → requires **introspection widening**: add `con.conname` + the `u`/`c`/`x` constraint types to `_CONSTRAINTS_SQL`, and add a new index-introspection query.

*Ship in three slices (fold each into its own increment):*
- **Slice 1 — Column operations, zero new introspection:** Add/Drop/Rename column, Change type (USING), Set/Drop NOT NULL, Set/Drop DEFAULT + the "Alter Table ▸" submenu scaffold + the new column-node context menu + the shared dialog/skeleton/tab plumbing. Highest value, fully self-contained and testable on existing introspection.
- **Slice 2 — Constraints & foreign keys:** Add constraint (typed, multi-column +), Add FK (target-table→column picker), unified Drop constraint (typed list), Rename constraint — INCLUDES the `_CONSTRAINTS_SQL` widening (conname + u/c/x types).
- **Slice 3 — Indexes, comments, whole-table:** Create/Drop index (Drop needs the new index-introspection query), Set table/column comment, Create table (multi-column builder), Drop table.

*Verified reuse map (cite when implementing):* `ui/ddl_buffer_panel.py::BrowserPanel._menu_for_item` (~463-511) — current context menu (Edit DDL on object rows; Add Trigger… on table nodes via `add_trigger_requested(table_info)`; New Function/Procedure… on the routines-branch root via `new_routine_requested()`); column nodes have NO menu; all menus suppressed when `browse_only=True`. `db/ddl_skeleton.py` (~87-209) — add the new skeleton functions as siblings. `ui/new_trigger_dialog.py` / `ui/new_routine_dialog.py` — dialog precedent. `db/introspect.py` — column & FK-target data present; constraint-name/unique/check/index widening absent. `ui/center_stage.py::open_ddl_object_tab` (~560-585) — hosts the generated DDL text. `ui/main_window.py` — Apply-to-Sandbox wired (~4008-4010); Save + sandbox-Check wired; **Apply-to-Target is NOT wired (a pre-existing gap affecting ALL DDL objects — explicitly NOT this feature's job; noted so the implementer doesn't think they broke it).**

**Alternatives considered:**
- Separate "Delete foreign key" + "Delete constraint" menu items (the original request) — rejected: identical DDL; unified typed "Drop constraint…" chosen (confirmed).
- Separate Add-PK / Add-UNIQUE / Add-CHECK menu items — rejected: those are the TYPE-dropdown values inside the one Add-constraint dialog; FK alone is split out because it needs the referenced-table→column section.
- A typed-name confirmation before Drop table — rejected: the tab-is-the-safeguard principle (generation is inert; running is the explicit gate).
- A flat context menu — rejected: "Alter Table ▸" submenu for scannability given ~18 actions.
- A dedicated scratch/SQL-console tab for the ALTER DDL vs reusing the FQ-002 editable tab — reused the editable tab for consistency with Add Trigger and because Apply-to-Sandbox is already wired there, with the Save-semantics caveat flagged for spec-maintainer above.

**Suggested placement:** EXTEND **§18.1** ("Routines & triggers browsing (DDL Explorer)" — the home of FQ-002's Explorer creation actions; this ALTER/modify set is the direct sibling). The section grows an "Alter Table ▸" submenu, a new column-node context menu, and the drop/rename actions, all honoring the §18.7 `browse_only` suppression. Also touches **§18.5** (the editable tab + Apply-to-Sandbox as the run path, and the ALTER-vs-object tab-semantics caveat above — likely a Supersession Ledger row for the tab-kind/Save-suppression narrowing) and requires an **introspection-model widening** (constraint names + unique/check + indexes) noted for §17/§18.1's schema model. NOT a new top-level section. (§18.1 confirmed live as of this triage.)

**Open questions** (non-blocking; flag to spec-maintainer/implementer):
1. The ALTER tab's Save semantics — triage recommends run-against-sandbox + copy-out, Save-to-object suppressed (spec-maintainer to formalize the tab kind).
2. Whether Add constraint / Add FK let the name be left blank → Postgres auto-name (triage recommends yes) vs require a name.
3. The Add-column datatype dropdown source — editable combo seeded with common types (like `COMMON_RETURN_TYPES`) for slice 1, optionally enriched from `DatabaseSchema.types` later.

*Collision status at triage:* clear — no concurrent session building ALTER-TABLE actions; `ddl_buffer_panel.py` / `ddl_skeleton.py` untouched by in-flight work (recent commits are the FQ-010..017 / bug-queue UX-review batch). Re-verify at pickup time.

---

## FQ-026: Eight names, four operations — one vocabulary per apply/check gesture, a yes/no answer for the sandbox comparison, and the death of the button row
**Status:** QUEUED
**Requested:** 2026-08-09
**Idea (verbatim/summarized):** The owner had to have the difference between eight labels explained to
them — `Apply to Sandbox`, `Run on sandbox`, `Deploy this edit… → sandbox`, `Check Object in Sandbox`,
`Check Object Without Applying`, `Run on quality`, `Deploy this edit… → quality`, `Apply to Target` — and
asked, verbatim: (1) `Check Object in Sandbox` should give "the single line of *are we in line with
sandbox*", because *"quality is already validated"*; (2) rename `Apply to Sandbox` → **"Check and commit
to sandbox"**; (3) rename `Check Object Without Applying` → **"Check and rollback"**; (4) `Apply to
Target` / `Run on quality` become one name, **"Apply to quality"**; (5) delete the panel buttons that
duplicate menu entries; (6) get rid of `Deploy this edit…` entirely.

**Problem:** Eight user-visible names denote **four** operations, and the naming carries no signal about
what distinguishes them. Verified against the code:

- `Apply to Sandbox` (panel button, `ddl_object_editor.py:1358`; context menu, `:848`; confirmation
  **title**, `:1017-1018`), `Run on sandbox` (`Deployment` menu / `DESTINATION_LABELS[DEST_SANDBOX]`,
  `:107-111`) and `Deploy this edit… → Run on sandbox` are all one path: `apply_to_sandbox()` →
  `db/ddl_check.py::apply_and_check` (`:1388`) — whole ladder, `commit=True`, `applied` bookkeeping row
  in the same transaction.
- `Check Object Without Applying` (`Parsing` menu since BUG-039) → `probe_check` (`:1427`) — the
  identical ladder with `commit=False` and no bookkeeping row.
- `Check Object in Sandbox` (`Parsing` menu) → `recheck` (`:1749`) — applies nothing; tiers 0-2 report
  "nothing to compile", tier 2 reports the bookkeeping fact `applied <timestamp>` plus D3's mandatory
  stale-buffer caveat, tier 3 lints what is actually IN the sandbox.
- `Apply to Target…` (panel button, `:1362`; confirmation **title** `"Apply to Target"`, `:1103-1104`),
  `Run on quality` (`DESTINATION_LABELS[DEST_TARGET]`) and `Deploy this edit… → Run on quality` are all
  `apply_to_target()` with its four hard preconditions.

Two structural aggravators. **(a) The confirmation-dialog titles are separate string literals from the
menu labels and have already drifted:** the menu says `Run on sandbox` / `Run on quality` while the
confirmation says `Apply to Sandbox` / `Apply to Target`. A user who picks a menu entry is answering a
modal that names the operation something else — a large part of what produced the confusion.
**(b) `Deploy this edit…` is a PICKER, not a fifth gesture** — it writes no DDL, adds no confirmation of
its own, and delegates to the three destinations. It exists because of FQ-009 ("the destinations are
undiscoverable"); FQ-020's `Deployment` menu made all three discoverable by name on the menu bar, and
**§18.5 already declares the picker superseded** (spec lines 4863 and 4936, dated 2026-08-08) while the
code still builds the button unconditionally (`_build_apply_row`, `:1325-1368`). So the picker is
currently a spec-vs-code gap, not a live design.

Separately, `Check Object in Sandbox` reports through the two D3a Audit channels as a multi-tier
narrative, when the question the owner actually asks when clicking it is one bit wide: *am I in line
with the sandbox?*

**Proposed approach:** Four operations, four names, one vocabulary each — plus one presentation change.

1. **`Check Object in Sandbox` — PRESENTATION ONLY. `recheck` is UNCHANGED.** Owner ruling, verbatim:
   *"The same way it does today. Don't change the underlying method, but the output should be a modal
   telling the current return's last line."* / *"Keep underlying methods as they are, but return me a
   simple answer."* The whole ladder still runs, **tier 3 still re-lints what is in the sandbox, and
   nothing loses re-lint coverage.** What changes is that the gesture surfaces a **modal with one line
   answering "are we in line with the sandbox?"**, sourced from the comparison `_recheck_tier2` already
   performs at `db/ddl_check.py:1841` (`recorded != text_sha1(request.buffer_text)`). The comparison is
   against **the tab's buffer** (owner-confirmed), and needs **no new query** — the hash is already in
   the `applied` row.
   - **The modal must have a line for BOTH states.** Today only the mismatch state speaks
     (`CAVEAT_STALE_BUFFER`, `:186-190`); a matching buffer is an *absence*. An absence cannot be the
     answer to a yes/no question, so a matching buffer needs an affirmative line ("this buffer matches
     what was applied to the sandbox at `<applied_at>`") or the gesture answers itself half the time.
   - **The name and the menu stay put.** Because the method is untouched, this remains a genuine check,
     so `Check Object in Sandbox` keeps its name and its home on `Parsing` (which BUG-039 established as
     "linting of the DDL"). No `RENAMED_ID_ALIASES` row needed for this one.
2. **`Apply to Sandbox` → `Check and commit to sandbox`**, replacing the menu label
   (`DESTINATION_LABELS[DEST_SANDBOX]`, today `"Run on sandbox"`), the context-menu entry (`:848`) and
   the confirmation title (`:1018`) with the one string.
3. **`Check Object Without Applying` → `Check and rollback`** (`Parsing` menu).
4. **`Apply to Target` / `Run on quality` → `Apply to quality`**, one name replacing the menu label
   (`DESTINATION_LABELS[DEST_TARGET]`) *and* the confirmation title (`:1104`). All four hard
   preconditions are untouched.
5. **Delete the panel button row.** `deploy_button` / `sandbox_button` / `target_button` and the whole
   `_build_apply_row` construction go; every path is the menu bar. **Owner has explicitly accepted the
   consequence**: a DDL object tab gets NO in-tab apply affordance, consistent with what FQ-020 did to
   saving.
6. **Delete `Deploy this edit…` entirely** — the picker method, `DESTINATION_LABELS`,
   `DESTINATION_UNAVAILABLE_REASONS` (`:119`) and the destination constants, closing the gap with §18.5's
   already-written supersession.

**Vocabulary invariant this feature must establish (the actual fix for the reported confusion):** each
operation has **one** name used identically across menu label, confirmation-dialog title, Audit `[Check]`
line and manual. The drift at (a) above is the failure mode; a single source per operation (the pattern
`DESTINATION_LABELS`' own docstring already argues for at `:103-106` — *"they must come from one place or
the UI and the manual disagree"*) is the guard. That constant is being deleted, so its role must be
re-homed, not dropped.

**Cost the owner accepted as a design, NOT as an estimate — surfaced here deliberately:**
`deploy_button` / `sandbox_button` / `target_button` / `deploy_this_edit` / `DESTINATION_LABELS` /
`DEST_*` total **106 references across 9 files**: `tests/ui/test_ddl_object_editor.py` (**38**),
`pgtp_editor/ui/ddl_object_editor.py` (34), `pgtp_editor/ui/main_window.py` (15),
`tests/ui/test_sandbox_check_console_wiring.py` (5), `docs/superpowers/CONSOLIDATED_SPEC.md` (5),
`docs/FEATURE_QUEUE.md` (6), `tests/ui/test_mainwindow_surface.py` (1), `docs/BUGFIX_QUEUE.md` (1),
`docs/TEST_LOG.md` (1). Request 5 is a **test-surface migration**, not a delete: the assertions that
today reach for a button must be rewritten against the `Deployment`/`Parsing` menu actions.

**Renames are menu-path ids — `RENAMED_ID_ALIASES` rows are mandatory.** `ui/toolbar_registry.py:136-150`
carries the FQ-020/FQ-021/FQ-022/BUG-039 rows to copy the pattern from (e.g.
`"database.check-object-without-applying": "parsing.check-object-without-applying"`). Without a row per
rename, a user's saved toolbar silently loses those buttons — the long comment at `:41-63` explains
exactly this. Needed for renames 2, 3 and 4; **not** for 1.

**Alternatives considered:**
- *Rewriting `Check Object in Sandbox` as a hash-vs-`applied.text_sha1` boolean, dropping the ladder* —
  what the request first read as. **Superseded by the owner's own clarification**, and rightly: it would
  have dropped tier 3, which is the only thing that catches what changed *underneath* the object since
  it was applied (a dependency altered, a table dropped). The premise "it's already been checked if it's
  there" holds only at apply time. Keeping the method and changing the presentation gets the one-line
  answer at zero cost to coverage.
- *Comparing the buffer against a re-fetched live definition (`pg_get_functiondef`)* — rejected on
  mechanism: Postgres normalizes what it hands back (whitespace, `AS $function$` quoting, argument
  spelling), so a byte comparison would report "different" on an object applied unchanged seconds ago.
  A normalizing comparison is real work for a worse answer. Moot now that the method is unchanged, but
  recorded so it is not re-proposed.
- *Keeping `Deploy this edit…` as a convenience umbrella* — rejected: it is a picker over three entries
  that are already named on the menu bar since FQ-020, so it now adds a step and a fifth name for four
  operations. §18.5 already says so.
- *Keeping the panel buttons and renaming them only* — rejected by the owner: duplicate surfaces are
  half the naming problem, and every duplicate is another string that can drift from the menu.
- *Disabling rather than deleting the buttons* — rejected: §18.5 carve-out 2 is explicit that an
  affordance whose seam is unwired is **ABSENT, not disabled**; a permanently-dead button row would
  violate the section this feature edits.

**Suggested placement:** **EXTEND, do not create.** Three sections, no new top-level one:
- **§18.5 D3/D3a** — owns the check ladder and the apply gestures. Takes: the four canonical names; the
  one-line modal for `Check Object in Sandbox` (with the both-states requirement); the deletion of the
  button row (updating the "**A small button row** carries the three sandbox gestures" text at spec line
  4545 and its v1 carve-out at 4644, both of which describe a row that is about to stop existing); and
  the removal of the "Historical: the *Deploy this edit…* picker" block's remaining live wiring at
  4936-4969.
- **§7 / §26** — the Editor menu bar and the per-tab entry tables: spec lines 1042, 1094-1095, 1113-1114,
  7013 (`Parsing` per-tab table), 7061-7070 (`Deployment` per-tab table, which explicitly notes
  `DESTINATION_LABELS` "must be updated with the spec text").
- **§30** — the modal is new UI surface: it must go through the **`ui/modals.py` seam** every other
  confirmation uses (confirmed present), because §30 forbids a test reaching an un-patched
  `QDialog.exec`/`QMessageBox.*`.
- Plus a **`RENAMED_ID_ALIASES`** row per rename (§7's toolbar-persistence contract).

**⚠️ This lands on spec text less than 48h old.** §18.5's supersession rows and the BUG-039/BUG-040
ledger rows are dated 2026-08-08, and the picker's supersession is already written. `spec-maintainer`
must **reconcile in place**, not append a competing narrative — several of the lines this feature edits
were themselves written by the previous day's reconciliation.

**Relationship to FQ-009 (read this before picking up either):** FQ-009 is `QUEUED — discoverability
half PROCESSED (4bc73b6); the quality leg is APPROVED and pending`. This entry **deletes the half of
FQ-009 that shipped** (the picker — its discoverability half, already declared superseded in §18.5 on
2026-08-08), while FQ-009's own entry **stays open, by owner ruling — do NOT mark it superseded**: its
quality leg is still wanted. The two entries now overlap, so whoever picks up FQ-009 must read FQ-026
first and implement the quality leg against the `Deployment` menu, not against the picker.
`Deployment ▸ Save in Project` survives as its own entry (§26 line 7061) and is not touched here.

**Open questions:**
1. **Modal *instead of* or *in addition to* the Audit output?** Today `recheck`'s result goes out over
   both D3a channels (`check_reported` narrative + `check_findings` objects). The owner asked for a
   modal with the single line; they did not say the tier detail and the findings should stop being
   reported. Triage recommends **both** — modal answers the yes/no, Audit keeps the full ladder detail
   and the clickable findings — but this is a real sub-decision for spec-maintainer.
2. **Does the tab CONTEXT menu keep the apply gestures?** Request 5 names the button row, but
   `ddl_object_editor.py:848` also offers `Apply to Sandbox` from the tab's context menu — another
   duplicate surface with its own label string. Triage recommends deleting it too for consistency with
   "menu bar only"; not explicitly ruled on.
3. **Where does the one-name-per-operation constant live** once `DESTINATION_LABELS` is deleted? The
   menu builder, a small module-level mapping, or the action registry — spec-maintainer's call, but the
   invariant must have a single owner or the drift recurs.
4. **`Check and commit to sandbox` / `Check and rollback` are noticeably longer** than what they replace
   and will widen the `Deployment` / `Parsing` menus. Accepted as clearer; flagged in case a shorter
   pair reading equally well emerges during design.

*Collision status at triage:* **CLEAR.** The triage agent reported every file this feature touches as
`UU` (conflicted) on `dev_review_01` and said not to start — that reading came from a stale git snapshot
and is **corrected here in place**: the FQ-020 merge was resolved and committed as `04c3591` earlier the
same day, and `git diff --diff-filter=U` reports zero unmerged paths. The working tree is clean apart
from the queue files. Nothing blocks a pickup on merge grounds.

What DOES want re-verification at pickup is line drift, not conflicts: `4828e3d` (BUG-038/039/040) moved
the two check gestures onto `Parsing`, deleted `Open`/`Close Sandbox Session`, and reworded
`DESTINATION_UNAVAILABLE_REASONS[DEST_SANDBOX]` — all in the same files and all landed after the line
numbers cited above were read.

---

## FQ-027: Three-column launcher (Standalone | Project | Maintenance), a Maintenance-mode menu filter, and a File ▸ New Session escape hatch
**Status:** PROCESSED (`da80b1a` + `23c5cb6`; spec §7/§11/§26 + two §28 ledger rows; manual `cca257a`) — **and it
SUPERSEDES FQ-011 wherever the two disagree (owner ruling, 2026-08-09).**

Shipped: the 1×3 launcher, Maintenance mode as the app's **first intent-based menu filter**, `File ▸ New
Session` with real teardown, and the deletion of `launcherSuppressed`. The mode is **session-only** — one
in-memory attribute, no QSettings key read or written, so a fresh window is always unfiltered and there is
no state to get stuck in.

**Two of this entry's own statements were FALSE against the code and were NOT built**, caught by
`spec-maintainer` folding the same entry and relayed to the implementer mid-flight: (1) the File menu
cannot be *"trimmed to exactly New Session + Save + Save All"* — FQ-020 had already deleted `File ▸
Save`/`Save As…` and **`Save All` has never existed anywhere in this app**. The intent behind it is met
instead by the filter's SCOPE: it walks the **window** bar only, so the Editor bar is untouched and
`Deployment ▸ Save XSD` stays exactly where it is. (2) The entry's menu-bar list names the dissolved `Edit`
menu and puts `Bookmarks` on the window bar; the hidden set actually implemented is **View · Database ·
Tools · Generation**.

**One defect found after the fact, by `manual-maintainer` writing the chapter:** the File trim trapped the
user in the application — `Exit` was hidden too, against §7's own membership table, leaving the title bar
as the only way to quit. Fixed in `23c5cb6`, which also pins the question that pass refused to answer from
inference: a hidden command's shortcut **stops firing** (`QAction.isEnabled()` is False for a hidden action
in PySide6, and Qt dispatches only to enabled actions), so `Ctrl+O` cannot open a project while `File ▸
Open...` is filtered out — the mode filters what you can DO, not merely what you can SEE.
FQ-027 is what the owner asked for *after* using the shipped launcher; FQ-011 is what was imagined before
it existed, and none of FQ-011 was ever implemented. See FQ-011's status block for the three concrete
disagreements (persistence, launcher shape, the `Generate`/default-toolbar-button case) and — more
importantly — for the four things that SURVIVE from it and must be carried into this implementation,
including the recorded objection that this is the app's first intent-based rather than capability-based
hiding. That objection is not retired by the supersession.
**Requested:** 2026-08-09
**Idea (verbatim/summarized):** "We have defined that we have three major modes: Standalone, Project and
Maintenance. So the initial window that comes up should only offer these three boxes. In Standalone:
Open pgtp / Open files. In Project mode: Open project / New project. In Maintenance mode: Edit XSD /
Open XSD. Project and standalone are OK for now, but in Maintenance mode I need different menus. Hide
everything else, and show only Schema menu."

**Problem:** The shipped launcher (spec §7, from FQ-010; `pgtp_editor/ui/launcher_dialog.py` +
`LAUNCHER_GROUPS`) presents **four** groups in an unconstrained layout: (1) *Open a `.pgtp` for editing*,
(2) *New Project / Open Project*, (3) *Open other files* (PHP), (4) *Maintenance mode* (XSD + §20
re_phpgen). The owner now wants the launcher to read as the app's **three major modes** in one visual
row, and — critically — wants Maintenance mode to actually *change the menu bar*, which is the
long-deferred half of the launcher story. FQ-011 designed the per-mode menu-filter **mechanism** (persisted
key, single `_refresh_*_affordances`-style visibility-only entry point, intent-not-capability hiding) but
left the **per-mode membership UNDECIDED** — §7 and §29 both record that "only `Generate` in project mode
has been named" and "no table may be invented." This entry supplies the first concrete membership answer
(Maintenance = Schema + Help only) and, because the filter needs an always-reachable way out, introduces a
new **File ▸ New Session** action as the escape hatch.

**Maintenance mode, in one line (owner, Q6):** *a mode for one-off **administrative/setup tasks** on the
app's own schema (Edit XSD / Import XSD), distinct from normal project/standalone editing.* That is why it
shows only Schema (+ Help) — everything else is out of the way for a focused admin task.

**Proposed approach:**
- **A 1×3 launcher: Standalone | Project | Maintenance**, three boxes in a single row. Restructures §7's
  `LAUNCHER_GROUPS` from four groups to three:
  - **Standalone** = *Open pgtp* (`File ▸ Open…`) + *Open files* (`File ▸ Open PHP File…`) — merges the
    shipped groups 1 and 3.
  - **Project** = *New project* / *Open project* (`File ▸ New Project…` / `Open Project…`) — unchanged
    group 2 (the idea says "Open project / New project"; entry order is a presentation detail for pickup).
  - **Maintenance** = **Edit XSD** + **Import XSD** — both existing Schema-menu QActions (§11). The §20
    re_phpgen entries currently in group 4 are **removed from the launcher**. NOTE: the idea's verbatim
    "Open XSD" does **not** map to a live command — the read-only `SchemaViewerWindow` / `Schema ▸ Open XSD`
    was deleted 2026-07-24 (spec ledger) in favor of the editable **Edit XSD** tab; per the owner's Q1
    answer the Maintenance box is **Edit XSD + Import XSD**, not the deleted viewer and not Edit AutoXSD.
  - Keep the existing entry-dispatch contract intact: groups hold **command ids only**
    (`toolbar_registry.command_id_for`), the picked entry's own QAction does the work via `action.trigger()`
    after the modal closes, and a group whose ids are all missing renders nothing (§7). This is a layout +
    membership change, not a rewrite of the dispatch mechanism.
- **Maintenance-mode menu filter (SESSION ONLY — does NOT persist across restarts).** When the user enters
  Maintenance mode, hide the menu bar down to **Schema + Help** (Help/F1/Manual must stay reachable, and
  Schema is the mode's whole point). Hidden: **Edit · View · Database · Tools · Bookmarks · Generation**
  (menubar build order per §26: File · Edit · View · Schema · Database · Tools · Bookmarks · Generation ·
  Help). This is the first concrete answer to FQ-011's UNDECIDED per-mode membership and MUST reuse
  FQ-011's settled mechanism verbatim: **visibility-only, never enabled-state** (no third grey-out
  posture), driven through a **single** refresh entry point, not ad-hoc `setVisible` in `_build_*_menu`.
  Recorded as intent-based hiding — a deliberate departure from the app's capability-based rule, exactly as
  FQ-011 frames it. **Scope is the menu bar ONLY — the toolbar is left alone** (owner, Q2): toolbar buttons
  backed by a now-hidden menu action may go empty/inert, which is accepted; the toolbar itself stays. This
  matches FQ-011's default scoping (menu-bar only unless explicitly widened).
- **Picking the Maintenance box in the launcher enters Maintenance mode for the session.** The mode is not
  a separate in-app toggle; choosing the Maintenance column is what applies the menu filter (FQ-011 already
  names the picked group as "the natural input" to the mode). Standalone/Project boxes leave the full menu
  bar in place. New Session (above) is what returns from Maintenance to the launcher, where the mode can be
  re-chosen or not.
- **File stays visible in Maintenance, trimmed to exactly New Session + Save + Save All — nothing else**
  (owner, Q1). This satisfies FQ-011's hard requirement that "whatever surface reveals/clears the mode must
  never be filtered out of any mode" (the escape hatch stays one click away) and lets XSD edits be saved
  without leaving the mode. So the visible File-menu items in Maintenance are precisely those three; every
  other File item (Open…, Open PHP File…, New/Open Project…, etc.) is hidden along with the other menus.
- **File ▸ New Session — the RENAMED former `File ▸ Show Launcher…`, given fuller behavior (owner, Q3).**
  There is exactly **ONE** action, not two: rename the existing Show Launcher action to **New Session** and
  make it re-initiate the app into the starting/launcher state: (a) prompt to **Save All** if there are
  unsaved changes, (b) **close everything** (documents/project/tabs), (c) **re-enter the launcher/starting
  state**, restoring the full menu bar first. It is the escape hatch from Maintenance mode's menu filter AND
  a general "start over" gesture. Because it clears the session-only Maintenance mode, it satisfies FQ-011's
  must-never-be-hidden requirement — so New Session (and thus the trimmed File menu above) must itself never
  be filtered out. `Show Launcher…` does **not** survive as a separate item; it *becomes* New Session.
- **Remove the launcher's "Don't show this again" suppress mechanism entirely** — the launcher always
  appears; there is no longer any way to skip it. Concretely, delete the whole suppression surface in
  `launcher_dialog.py`: the `QCheckBox("Don't show this again")` (`suppress_checkbox`, line 213) and its
  `suppress_requested` / `set_suppressed` accessors (lines 276-280); `LAUNCHER_SUPPRESSED_SETTINGS_KEY`
  (`"launcherSuppressed"`, line 90) with `launcher_suppressed()` / `set_launcher_suppressed()`
  (lines 150-157); the `force=` bypass path and the suppression read/write in `show_launcher`
  (`force` param line 314, the `if not force and launcher_suppressed(...)` early return line 326, and the
  `set_launcher_suppressed(...)` persist on exit line 337). Plus callers/manual: `main_window.py`
  (~line 2065, the "re-open the startup launcher on demand" wiring — `File ▸ Show Launcher…` with
  `force=True`) and `manual.md` (~lines 49-55). Rationale to record: with Maintenance being session-only
  and the new `File ▸ New Session` always re-entering the launcher, a persisted "skip the launcher forever"
  toggle is now **both redundant and a trap** — the launcher is the single starting gate for picking a
  mode, so it must always appear. Removing `force=` is consistent with Q3's ruling that Show Launcher…
  becomes New Session: there is no suppression left to bypass, so the `force=` parameter that only existed
  to override suppression goes away with it, and the single New Session action unconditionally shows the
  launcher after its save-all/close teardown.

**Alternatives considered:**
- **Keep `File ▸ Show Launcher…` as-is (light re-show) and add New Session as a second, separate action** —
  rejected by the owner's Q3 answer: exactly one action is wanted. `Show Launcher…` alone only opens the
  modal over the live session without tearing it down, which is not the full re-initiation the owner asked
  for. Resolution: **rename** Show Launcher to New Session and give it the save-all → close → relaunch
  behavior — one action, not two.
- **Filter the toolbar to match the Maintenance menu set** — rejected by the owner's Q2 answer: **menu-bar
  only, leave the toolbar alone**, per FQ-011's default scope. Toolbar buttons whose backing menu action is
  hidden may render empty/inert; that is explicitly **accepted**, and the toolbar itself stays visible and
  unchanged. Keeps the filter's blast radius to one surface (the menu bar), matching FQ-011's stated
  scoping.
- **Persist Maintenance mode across restarts** (FQ-011's default would-be design) — rejected by the owner's
  Q3 answer: session-only. This is *simpler and safer* than FQ-011's persisted-mode design — a session-only
  filter cannot strand a user in a menu-less app after restart, so it sidesteps the "persisted mode + a
  suppressible launcher is a trap" hazard §29(a) worries about, while still needing the New Session hatch
  within the session.
- **Hide Help too / hide the entire menu bar** — rejected on FQ-011's rule that Help/F1/Manual must never
  be filtered out (hiding the only documentation explaining why commands vanished). Help stays.
- **Drop the launcher to a mode-picker that stores a mode** — not proposed here; §7 is explicit that the
  groups are "a presentation of menu commands, not a mode picker," and the shipped dispatch triggers one
  QAction per launch. Maintenance mode entry could instead be triggered by the *act of picking the
  Maintenance box*, but the exact coupling (does picking a Maintenance entry set the session mode, or is
  the mode a separate toggle?) is left as an Open Question rather than invented.

**Suggested placement:** **EXTEND §7 (App shell / launcher)** in `CONSOLIDATED_SPEC.md` — this answers
FQ-011's explicitly-UNDECIDED per-mode menu membership for Maintenance mode (§7 launch-mode block
lines ~1181-1224 and §29 open question (a)/(b)/(c)) and revises §7's `LAUNCHER_GROUPS` from four groups to
a 1×3 three-mode row. It is a follow-on to **FQ-010** (the shipped launcher) and **FQ-011** (the planned
per-mode filter mechanism), NOT a duplicate: FQ-011 deliberately stopped at the mechanism and forbade
inventing a membership table, so a separate entry carrying the owner's now-given answer plus the new
`File ▸ New Session` action is the correct shape. Must reuse: §7's command-id/`action.trigger()` dispatch
contract; FQ-011's visibility-only, single-refresh-entry-point mechanism; the §11 Schema QActions
(Edit XSD, Import XSD) unchanged; and §26's menubar build order. Touches, at pickup: `launcher_dialog.py`
(`LAUNCHER_GROUPS` + a 1×3 layout; **removal** of the suppression checkbox/key/`force=` path per above),
a new menu-filter refresh entry point on `MainWindow`, and a new `File ▸ New Session` action wired to
save-all/close/relaunch. **SUPERSESSION-LEDGER-WORTHY when folded in:** this **removes** FQ-010's
"Suppressible, escapable and REVERSIBLE" launcher contract in §7 (the `launcherSuppressed` QSettings key,
the "Don't show this again" checkbox persisted on every exit path, and the `File ▸ Show Launcher…`
`force=True` bypass). The launcher becomes an unconditional starting gate; `spec-maintainer` should add a
ledger row for the withdrawn suppression capability, not silently drop it from the §7 body.

**Open questions:** None — all four recorded questions were answered by the owner and folded into the body
above: (Q1) File in Maintenance = New Session + Save + Save All only; (Q2) menu-bar filter only, toolbar
left alone with empty/inert buttons accepted; (Q3) exactly one action — Show Launcher… is renamed to New
Session and gains save-all/close/relaunch, so `force=`/suppression go away; (Q4/purpose) Maintenance =
one-off administrative/setup tasks on the app's own schema. Picking the Maintenance box enters the
session-only mode; New Session is the escape hatch. Nothing remains undecided for this feature.

---

## FQ-028: App-shell chrome redesign — Audit/Problems split + static status bar + a prominent color-coded mode indicator (left-dock findings tab, static status bar, colored toolbar+status-bar mode panel, bottom dock → Activity Log + Results tabs)
**Status:** QUEUED
**Requested:** 2026-08-09
**MERGED 2026-08-09:** this entry now also contains the mode-indicator design formerly tracked as **FQ-029**
(prominent, color-coded, right-anchored top-toolbar panel + upgraded status-bar label). The two overlapped
entirely on the status-bar mode label and the single source of truth for "current mode," so they were merged
into one coherent design at the owner's request. FQ-029 is retained below as a tombstone pointing here.
**Idea (verbatim/summarized):** "I dislike how the single 'Audit / Problems' bottom dock is used. A
this-session inventory found it does THREE unrelated jobs at once — (a) navigable click-to-jump findings,
(b) operation narration/log spew, (c) one-off errors — with self-contradictory lifecycles (some prefixes
clear-on-rerun, some accumulate forever, one clears per-tab) and heavy overlap with the status bar (many
events write to both). Split those jobs onto surfaces with coherent, single lifecycles: navigable findings
into a left-dock tab; the status bar into static-only indicators; the bottom dock into an Activity Log tab
and a saved-results tab." (Fully converged three-point redesign, all decisions asked-and-answered with the
requester plus a code-verification pass.) PLUS (merged FQ-029): "The major modes and minor modes should be
very visible in the toolbar area, to the right of the toolbar I need a panel that states the major and minor
mode (when there's). It should be in a contrasting background and different background color for each mode
for easy recognition."

**Problem:** The one `Audit / Problems` bottom dock (`QListWidget`, §7 lines ~539-554) is overloaded across
three unrelated jobs with mutually contradictory lifecycles, and it double-writes with the status bar. §7
today reserves nine prefixes against one another in one panel — `[Schema]` / `[Validate]` / `[Find]` /
`[PHP]` / `[Lint]` / `[Bookmark]` / `[Check]` / `[SQL]` / `[Project]` — but some clear-on-rerun (Find),
some accumulate forever (Lint/Validate), one clears per-tab, and the panel simultaneously carries navigable
hits, operation narration, learning chatter, generation stdout, and one-off refusals. Meanwhile ~40
transient `showMessage` calls (via the `_shell_status` trampoline, `ui/main_window.py:1290`, and
`ui/busy.py::busy_status`, line 50) scroll through the status bar, several duplicating what also lands in
the Audit panel. The result is that the results a user wants to STEP THROUGH scroll away, saved validation
history gets wiped by an unrelated op, and the status bar is a noise channel rather than an at-a-glance
state readout. This redesign gives each job a surface with ONE coherent lifecycle.

**Proposed approach (three coordinated parts):**

- **PART 1 — Navigable findings get their own LEFT-DOCK tab (not the center pane).** A new tab in the
  **left dock** beside the project tree / the FQ-003 coherence view / table references (precedent: the
  existing `left_tabs` — Table References / DB Check / FQ-003 coherence view). Left dock is chosen so the
  results list stays visible while each clicked hit opens in the CENTER editor — best for stepping through
  many. After Part 3's refinement this tab holds **only Find-All (`[Find]`) and List Bookmarks
  (`[Bookmark]`)** — the pure search/navigation results. **Lifecycle = clear-all-on-new-content,
  last-operation-wins across types:** any new navigable op wipes the whole tab and shows only its results
  (run Find-All then List-Bookmarks → the bookmarks replace the finds). **Click routing is UNCHANGED:**
  reuse today's `ui/main_window.py::_on_audit_item_clicked` dispatcher (line 1471) and the `Qt.UserRole+N`
  role convention (branch on raw / xsd / `DdlObjectRef.key` tuple / PHP-tab marker → jump to target in the
  center editor/tab). Folded-in defaults the requester did not object to: the tab **auto-opens/focuses**
  when a navigable op runs; it is a **single persistent tab** (created once, reused); the op's summary/count
  line (e.g. "5 matches for X", "N bookmarks") stays as a **header row** in the tab.

- **PART 2 — Status bar becomes STATIC-ONLY, AND a prominent color-coded mode indicator spans BOTH the top
  toolbar and the status bar** (persistent indicators, no scrolling transient messages). *(This part absorbs
  the merged FQ-029: the mode readout is no longer a plain status-bar label but a prominent, per-mode-colored
  indicator rendered on TWO surfaces from ONE source of truth.)*
  1. **Major mode = the SESSION workflow mode** (Standalone / Project / Maintenance), as established by
     **FQ-027** (the three-column launcher), always shown. **RECONCILED 2026-08-09 with FQ-027 (latest-wins):
     the mode is SESSION-ONLY and does NOT persist across restarts** — FQ-027's owner decision explicitly
     SUPERSEDES FQ-011's persisted-mode design. Picking a launcher column enters that mode for the session;
     `File ▸ New Session` (FQ-027) resets it and re-shows the launcher. So this indicator does NOT require a
     persisted-mode store — it simply DISPLAYS the current session mode that FQ-027 already establishes
     (FQ-011 remains the underlying visibility-only menu-filter MECHANISM that FQ-027 reuses). The label is
     the chosen WORKFLOW mode — **distinct from the auto-detected `AppState`**
     (`ui/project_status_model.py:110-118`: STANDALONE / PROJECT_NOT_SETUP / PROJECT_SETUP); actual
     project-open-ness + tier is conveyed by the DB dots (item 4 below), so a mode-vs-actual-state mismatch
     is possible (e.g. Project mode chosen but the open dialog cancelled) and is FQ-027's to reconcile.
     **HARD dependency, merged from FQ-029:** FQ-027 as written exposes NO readable current-major-mode object
     (it only applies a menu filter on launcher pick). This indicator NEEDS a readable current-major-mode
     value, so EITHER FQ-027 must expose a single in-memory session-mode accessor (e.g.
     `MainWindow.current_workflow_mode()`, set on launcher pick / New Session), OR this feature introduces
     that single source of truth itself. It is an in-memory SESSION value, never a QSettings key, and BOTH
     the toolbar panel and the status-bar label must read the SAME value (never a second, drifting notion).
  2. **Minor mode = an active editor SUB-STATE — Editing / Caption / Compare-Merge (Diff) / Edit XSD**, shown
     only "when there's one" (owner). Merged from FQ-029, this is now FOUR sub-states (FQ-028 originally
     covered only the first three), mapped 1:1 onto the app's real named states, coining nothing (obey
     §7:1060-1062's "mode has four meanings / use precise names" rule):
     - **Caption Mode** (§13 — `_mode_label` "Caption Mode (XML read-only)", flipped `:2302`/`:2357`).
     - **Compare/Merge / Diff** (§12 / FQ-021, shipped — owned by `ui/diff_merge_controller.py`). It does NOT
       touch `_mode_label` today → this adds the small new wiring to show "Diff" when it is active.
     - **Edit XSD** (§11 — `_xsd_mode`, `ui/xsd_controller.py`). *(New vs. original FQ-028, added from FQ-029.)*
     When none is active, no minor mode is shown — just the major mode. Keep and repurpose the existing
     permanent `_mode_label` for the status-bar side; keep `_debug_label` (`ui/main_window.py:205/490`).
  3. **The mode indicator renders on TWO surfaces from ONE source of truth (merged from FQ-029; owner wants
     BOTH):**
     - **(a) A NEW right-anchored, color-backed panel pinned into the top `QToolBar`.** The toolbar is the
       movable "Main Toolbar" (`ui/toolbar_controller.py:140`, `objectName("main_toolbar")`, added via
       `addToolBar` from `ui/main_window.py:871`, owned by `ToolbarController`, position persisted in
       `windowState`). Because a `QToolBar` is movable/floatable, "to the right of the toolbar" is only stable
       if the panel is part of the toolbar and RIGHT-ANCHORED: add an **expanding spacer widget** (`QWidget`
       with `sizePolicy` Expanding) via `toolbar.addWidget(...)` then the mode-panel widget, so it stays flush
       right regardless of how many command buttons precede it. It reads e.g. "Project" or "Project · Caption"
       (major, then minor when present) on a contrasting per-mode background. Built by `ToolbarController.build`
       (or by MainWindow right after `build`, where `addToolBar` lives) so it survives the same
       `saveState`/`restoreState` as the toolbar.
     - **(b) The status-bar mirror IS the upgraded `_mode_label`** (`ui/main_window.py:486-487`) — do NOT add a
       second label. Extend it to carry the MAJOR mode and the same per-mode background color, driven from the
       same source of truth as the toolbar panel. (This is the original FQ-028 Part 2.1/2.2 label, now the
       secondary mirror of the prominent top panel.)
     - **One update path:** a single helper — e.g. `MainWindow._refresh_mode_indicator()`, modeled on the
       existing single-entry `_refresh_*_affordances` convention — called at every major/minor transition
       (launcher pick / New Session; Caption enter/leave `:2302`/`:2357`; Compare/Merge enter/leave
       `diff_merge_controller.py`; Edit-XSD enter/leave `xsd_controller.py`). Both surfaces are rewritten by
       this one call — no ad-hoc `setText`/`setStyleSheet` scattered across transition sites.
     - **Passive indicator ONLY (owner):** no click behavior, no context menu, no mode switching from either
       surface. Mode changes stay with the launcher pick and `File ▸ New Session` (FQ-027).
     - **Theme-aware per-mode color palette (owner):** colors must adjust for light vs dark — NOT a fixed
       hardcoded set like the DEBUG chip (`_debug_label`, `:491-494`, static red, does not re-theme). Respect
       the `lightTheme` setting and re-render when `ui/theme.py::apply_theme(app, light)` flips. Recommended:
       a pure helper mirroring `theme.py`'s `light_palette()`/`dark_palette()` split — e.g.
       `mode_colors(light: bool) -> dict[str, tuple[bg, fg]]` — consulted by `_refresh_mode_indicator` and
       re-consulted from `apply_theme`. **Starting-proposal palette for the three MAJOR modes** (bg / fg;
       final values are the implementer's to tune):
       | Major mode | Light (bg / fg) | Dark (bg / fg) |
       |---|---|---|
       | **Standalone** | `#E3F2FD` / `#0D3B66` (calm blue) | `#1E3A5F` / `#CFE3FF` |
       | **Project** | `#E6F4EA` / `#1B5E20` (green — the "real work" mode) | `#1E3A28` / `#B6E3C0` |
       | **Maintenance** | `#FDECEA` / `#8B1E1E` (amber-red — deliberate "admin mode" alert cast) | `#3A2320` / `#F2B8AE` |
       **Minor mode is conveyed by TEXT, not a second color** (recommended): background stays the MAJOR mode's
       color; the minor mode is appended as text ("Project · Caption"), so users read workflow at a glance and
       need not learn a 3×4 color grid. (Two-tone alternative in Alternatives; owner's to overrule.) Verify
       AA-ish contrast against the live QDarkStyle chrome, not just the bare palette.
  4. **DB indicator dots, PROJECT MODE ONLY:** a Quality dot + a Sandbox dot, each white/red/green
     (white = not-set-up, red = offline, green = connected). This **REFINES FQ-018** (queued/unbuilt,
     status-bar Quality/Sandbox dots, 30s poll): FQ-018 showed the Quality dot even in standalone; the
     requester OVERRIDES → **both dots appear only when a project is open.** This entry SUBSUMES/REFINES
     FQ-018's status-bar-dots portion — reuse FQ-018's 30s-poll + §18.8 connectivity-state design
     (`QualityState` / `SandboxState` / `AppState`), just gate BOTH dots on project-open
     (`DdlProjectController.is_open` — folder is not None). NOTE: "project mode" for the dots means a project
     is ACTUALLY OPEN (`is_open`/`AppState`), NOT the "Project" workflow-mode label from item 1 — the dots
     follow real project-open state, so they can show under any workflow label and be absent even while the
     label reads Project.
  - **All ~40 transient `showMessage` call sites → the Activity Log tab** (Part 3 / FQ-019). They flow
    through the `_shell_status` trampoline (`ui/main_window.py:1290`) and `ui/busy.py::busy_status`
    (line 50) today. FLAG (non-blocking, requester accepted): errors/refusals ("Check — no sandbox session",
    "Target failed") become Activity-Log entries under this rule; v1 routes them to the log, and if
    immediacy proves insufficient a later toast could be added (see Open Questions).
  - **Busy / in-progress → a dedicated static-bar busy slot WITH A LIVE ELAPSED-SECONDS COUNTER** (e.g.
    "Validating… 3s", ticking), shown only while an op runs and cleared on completion. It replaces the
    current sticky `busy_status` messages ("Validating…", "Target: loading routines & triggers…") with a
    fixed status-bar element, consistent with "static bar."

- **PART 3 — Bottom dock (was "Audit / Problems") becomes TWO tabs.** Retire the "Audit / Problems" title;
  the bottom dock now hosts:
  - **Activity Log tab — IS the FQ-019 Activity Log feature** (queued/unbuilt): FQ-019's per-project file/DB
    action log PLUS all the Part-2 transient status-bar messages routed here. Per-project persist
    (`.ddlproject/`, JSONL), session-only when standalone. This entry PLACES FQ-019's panel here as one of
    the two tabs and feeds it the transients; **cross-reference FQ-019, do not duplicate its internal
    design.**
  - **Results tab — where validation results are SAVED (ACCUMULATED, not cleared).** Holds: sandbox
    **Check** (`[Check]`), PHP **Lint** (`[Lint]`), **Validate Project** (`[Validate]`), **Verify XSD**
    (`[Schema]` VERIFY rows) — the requester confirmed Validate + Verify count as checks. Rows stay
    **NAVIGABLE** (click → jump to line, same routing as today via `_on_audit_item_clicked`). **Persists
    same as the Activity Log** (per-project JSONL, session-only standalone). **Run separator (EXACT,
    requester-specified):** between each run — a blank line, then a header line = `YYYY-MM-DD ` (folded rec:
    also append `HH:MM:SS` so same-day runs differ — see Open Questions) followed by a 40-character dashed
    rule (`----------------------------------------`), then that run's result lines.
  - **This REFINES PART 1:** Check, Lint, Validate, Verify MOVE OUT of Part 1's left-dock findings tab into
    this Results tab; Part 1's tab is thereby reduced to Find-All + List-Bookmarks only.

**Complete disposition of all 9 current Audit prefixes (nothing orphaned):**
| Prefix | Destination | Lifecycle / note |
| --- | --- | --- |
| `[Find]` | Left-dock findings tab | ephemeral, clear-on-new |
| `[Bookmark]` | Left-dock findings tab | ephemeral, clear-on-new |
| `[Validate]` | Results tab | accumulated |
| `[Lint]` | Results tab | accumulated |
| `[Check]` findings | Results tab | accumulated; `[Check]` NARRATIVE lines ("Creating db…") ride in the same run's Results block (folded rec; alt = Activity Log, minor impl detail) |
| `[Schema]` Verify findings | Results tab | accumulated |
| `[Schema]` LEARNING chatter | Activity Log | "Learned N facts", "NEW ELEMENT" |
| `[PHP]` generation stdout | Activity Log | narration |
| `[SQL]` format-selection refusals | Activity Log | one-off refusals |
| `[Project]` DDL-project status/errors | Activity Log | status/narration |

Net split: **Left-dock = Find + Bookmarks; Results = Check + Lint + Validate + Verify; Activity Log =
generation output + schema-learning + format refusals + project status + all Part-2 transients + FQ-019's
action log.**

**Alternatives considered:**
- **Keep one Audit dock and just fix the lifecycle contradictions in place** — rejected: the panel's three
  jobs need three DIFFERENT lifecycles (ephemeral navigable / accumulated-saved / append-only narration) and
  two different LOCATIONS (side-by-side-with-editor for stepping vs. bottom for logs). One widget cannot carry
  all three coherently; that overload is precisely the reported problem.
- **Put the navigable findings in the CENTER pane** (a results tab beside editors) — rejected: a center tab
  hides the editor it should be jumping into, defeating step-through. Left dock keeps list + target both
  visible. (Cross-check: FQ-014's rejected "dedicated bookmarks left-dock tab" was rejected only because the
  Audit dock already existed as the app's list surface; that objection dissolves here since the Audit dock is
  being restructured anyway.)
- **Leave transient messages in the status bar** — rejected by the requester's core complaint: transient spew
  is the noise the static-bar redesign exists to remove. Transients go to the Activity Log; only persistent
  indicators + the live busy counter remain in the bar.
- **Clear the Results tab per-run like `[Find]`** — rejected: validation history is exactly what the requester
  wants SAVED across runs; hence the accumulate-with-run-separator model.
- **Route `[Check]` narrative to the Activity Log instead of the Results block** — kept as a minor Open
  Question; folded recommendation is in-Results-block so a run reads as one coherent unit.
- *(merged from FQ-029)* **Just relocate/upgrade the status-bar `_mode_label` and skip the top-toolbar
  panel** — rejected by the owner (BOTH surfaces wanted) and by the core complaint that the status bar is at
  the far bottom (`center_stage.py:468`) and is being deliberately quieted to static-only here; a prominent
  TOP indicator is the point. The status-bar label is kept, as the secondary mirror.
- *(merged from FQ-029)* **Encode the minor mode as a second background color / a two-tone split panel** —
  set aside for v1: 3 majors × 4 minor states is a 12-combination color vocabulary users would have to
  learn, defeating "easy recognition." Recommended: major = color, minor = text suffix. Owner's to overrule.
- *(merged from FQ-029)* **Make the mode panel clickable to switch modes / re-open the launcher** — rejected
  by the owner: passive indicator only. Mode changes stay with the launcher pick and `File ▸ New Session`.
- *(merged from FQ-029)* **Hardcode the per-mode colors (like the DEBUG chip's static red)** — rejected by
  the owner: the palette must be theme-aware and re-render on `apply_theme`, or the panel is low-contrast or
  garish in one of the two themes.

**Suggested placement:** **EXTEND §7 (App shell — "App shell", `CONSOLIDATED_SPEC.md` line ~492; confirm the
live number at write time).** §7 owns the Audit/Problems panel, the status bar, AND the nine-prefix
reservation rule (§7 lines ~539-554). This is a MAJOR amend: the prefix-reservation rule is
**dissolved/replaced** by the three-surface split (prefixes no longer coexist in one panel; they are routed
by destination), and the single Audit/Problems dock is **renamed into two bottom-dock tabs** (Activity Log +
Results) plus a new left-dock findings tab. **ALSO touches §18.8 (The Project Status window,
`CONSOLIDATED_SPEC.md` line ~6333 — a subsection of §18 DDL versioning; confirm live number)** — the
`QualityState`/`SandboxState`/`AppState` connectivity-state model behind the DB dots lives there and is the
natural home to describe the busy counter's state source. §7 ALSO owns the toolbar and the "mode has four
meanings / use precise names" rule (§7:1060-1062) that the merged mode-indicator obeys; the new
right-anchored colored mode panel is toolbar chrome added on the movable Main Toolbar via the spacer-widget
technique, and the theme-aware `mode_colors(light)` helper sits alongside `theme.py`'s pure palette builders.
**Cross-references FQ-011 / FQ-018 / FQ-019 / FQ-027** (see Dependencies below). **Expect MULTIPLE
Supersession Ledger rows:** (1) §7's nine-prefix single-panel reservation rule is overturned; (2) §7's single
Audit/Problems dock model is overturned (renamed into tabs + a left-dock tab); (3) FQ-018's
Quality-dot-in-standalone is overridden to project-mode-only for both dots; (4) *(merged from FQ-029)* §7's
monochrome status-bar `_mode_label` (Editing/Caption only) is upgraded into a colored major+minor indicator
mirrored by a new prominent top-toolbar panel. `spec-maintainer` should add ledger rows for each
withdrawn/overridden contract, not silently rewrite.
Must reuse (VERIFIED CITATIONS): click dispatcher + role convention `ui/main_window.py::_on_audit_item_clicked`
(line 1471) + `Qt.UserRole+N`; finding producers to redirect — `find_controller.py` (Find/Validate/Bookmark),
`lint_controller.py` (Lint), the Check findings channel `ui/main_window.py::_report_check_findings`
(line 3691, wired at ~3832), `xsd_controller.py` Verify rows; status bar today — permanent `_mode_label`
(`ui/main_window.py:486` init / `:2302` caption-on / `:2357` caption-off) + `_debug_label`
(`:205`/`:490`, the static-chip styling to AVOID copying verbatim); ~40 `showMessage` via the `_shell_status`
trampoline (`:1290`) + `ui/busy.py::busy_status` (line 50); mode states — `AppState` enum
(`ui/project_status_model.py:110-118`), standalone-vs-project gate `DdlProjectController.is_open`, Diff mode
owned by `ui/diff_merge_controller.py` (FQ-021), Edit-XSD mode `_xsd_mode` in `ui/xsd_controller.py` (§11),
Caption in `ui/center_stage.py`+`ui/main_window.py` (§13); the movable Main Toolbar + `addToolBar` seam
(`ui/toolbar_controller.py:140`, `ui/main_window.py:871`) for the right-anchored panel; the pure-palette
split in `ui/theme.py` (`light_palette`/`dark_palette`/`apply_theme`) that `mode_colors(light)` mirrors;
left-dock tab precedent — the existing `left_tabs` (Table References / DB Check / FQ-003 coherence view).

**Dependencies / relationships to already-queued work (sequence with these three):**
- **Depends on FQ-027** (three-column launcher + SESSION-ONLY Standalone/Project/Maintenance mode + the
  Maintenance menu filter + `File ▸ New Session`). RECONCILED 2026-08-09: FQ-027 is the concrete realization
  of the modes this indicator displays and it SUPERSEDES FQ-011's persisted-mode design with a session-only
  one, so Part 2.1's major mode reflects FQ-027's session mode (no persisted-mode store needed). **FQ-011**
  remains the underlying visibility-only, single-refresh-entry-point menu-filter MECHANISM that FQ-027 reuses;
  this entry only DISPLAYS the mode, it does not implement the filter. **HARD dependency (merged from
  FQ-029):** FQ-027 exposes no readable current-major-mode object today — see Part 2.1: FQ-027 must expose a
  single in-memory session-mode accessor, or this feature introduces that single source of truth itself.
- **Refines FQ-018** (status-bar DB dots) — Part 2.4 subsumes its status-bar portion, overriding it to
  project-mode-only for BOTH dots; fold FQ-018's 30s-poll + §18.8 design into this static bar. Owner also
  asked (via merged FQ-029) that the mode indicator and the DB dots share the status bar coherently — do not
  grow two rival indicator regions.
- **Places/consumes FQ-019** (Activity Log) — Part 3's Activity Log tab IS FQ-019; this entry positions it as
  one of the two bottom-dock tabs and routes Part-2 transients into it. Land FQ-019's Activity Log as the tab.
- **Absorbs FQ-029 (merged 2026-08-09)** — the prominent color-coded mode indicator across the top toolbar +
  status bar is now Part 2 (items 2 & 3) of THIS entry, not a separate feature. There is ONE source of truth
  and ONE update path (`_refresh_mode_indicator`) for the major/minor mode value shared by both surfaces; the
  earlier FQ-028↔FQ-029 "must coordinate" note is now internal. FQ-029 remains below as a tombstone.

**Open questions (non-blocking; flag to spec-maintainer/implementer):**
1. `[Check]` narrative lines → in-Results-block (recommended) vs Activity Log.
2. Results run-separator timestamp granularity — add `HH:MM:SS` (recommended, so same-day runs differ) vs
   date-only `YYYY-MM-DD` as literally specified by the requester.
3. Whether errors/refusals need a later transient toast if Activity-Log-only proves too quiet (v1: log only).
4. (RESOLVED 2026-08-09 — reconciled with FQ-027) The main-mode label reflects the SESSION-ONLY mode set by
   the launcher pick and reset by `File ▸ New Session`; it does NOT persist across restarts. Part 2.1 and the
   Dependencies section were updated to drop the FQ-011 persisted-mode assumption in favor of FQ-027's
   session-only stance (latest-wins). FQ-011 stays only as the menu-filter mechanism FQ-027 reuses.
5. *(merged from FQ-029)* Where FQ-027's single current-major-mode source of truth lives — added to FQ-027's
   implementation, or introduced by this feature — must be settled at pickup so both the toolbar panel and
   the status-bar label read the same value.
6. *(merged from FQ-029)* Minor mode as a text suffix (recommended) vs a two-tone / second-color treatment —
   owner's call if the text suffix proves insufficiently prominent.
7. *(merged from FQ-029)* Exact per-mode colors in the Part 2 table are a STARTING proposal; final values
   (and AA-contrast verification against the live QDarkStyle chrome, not the bare palette) are the
   implementer's to tune with the owner.
8. *(merged from FQ-029)* Whether the toolbar panel shows anything when NO major mode is set yet (e.g. before
   the launcher pick) or is simply blank/absent until a mode exists — left to pickup.

---

## FQ-029: [MERGED INTO FQ-028] Prominent, color-coded mode indicator — a right-aligned top-toolbar panel plus the upgraded status-bar label, one source of truth, theme-aware per-mode colors
**Status:** MERGED INTO FQ-028 (2026-08-09)
**Requested:** 2026-08-09
**Merge note:** This feature was merged into **FQ-028** at the owner's request on 2026-08-09, because the two
overlapped entirely on the status-bar mode label and the single source of truth for the current mode. The
full mode-indicator design — the right-anchored color-backed top-toolbar panel, the upgraded `_mode_label`
mirror, the four minor modes (Editing / Caption / Compare-Merge / Edit XSD), the theme-aware
`mode_colors(light)` palette, the single `_refresh_mode_indicator` update path, and the passive-only rule —
now lives in **FQ-028 Part 2 (items 1–3)** with its dependencies and open questions folded in there. The
original text is preserved below for the record; DESIGN AND IMPLEMENT IT FROM FQ-028, not from here.

<details><summary>Original FQ-029 text (superseded by FQ-028 — historical record)</summary>

**Status:** QUEUED
**Requested:** 2026-08-09
**Idea (verbatim/summarized):** "The major modes and minor modes should be very visible in the toolbar
area, to the right of the toolbar I need a panel that states the major and minor mode (when there's). It
should be in a contrasting background and different background color for each mode for easy recognition."

**Problem:** The app's operating mode is barely visible. Today the ONLY mode readout is `self._mode_label`
(`ui/main_window.py:486-487`), a plain `QLabel` added via `statusBar().addPermanentWidget(...)` at the far
BOTTOM of the window — a location the code itself flags as too easy to miss (`ui/center_stage.py:468`: the
`_mode_label` cue "is at the far bottom of the window, not on the tab they are looking at"). It shows only
"Editing Mode" / "Caption Mode (XML read-only)" (flipped at `:2302` / `:2357`), does NOT reflect
Compare/Merge (FQ-021, shipped) or Edit XSD (`_xsd_mode`, §11), has no notion of the three MAJOR workflow
modes FQ-027 introduces (Standalone / Project / Maintenance), and is monochrome — nothing distinguishes one
mode from another at a glance. The owner wants the mode to be UNMISSABLE: a prominent, color-coded panel
pinned to the RIGHT END of the top toolbar (where the eye rests while working), naming the major mode
always and the minor mode when one is active, with a distinct background color per mode for instant
recognition — while still keeping a mode readout in the status bar.

**Terminology (MANDATORY — reuse §7's rule, do not invent a fifth meaning of "mode"):** §7
(`CONSOLIDATED_SPEC.md:1060-1062`) records that "mode" already carries FOUR meanings and forbids conflating
them. This entry maps the owner's words onto the EXISTING named states, coining nothing:
- **Major mode = the SESSION workflow mode** — **Standalone / Project / Maintenance**, exactly the three
  FQ-027 establishes via the launcher pick (session-only, reset by `File ▸ New Session`). Always shown.
- **Minor mode = an active editor SUB-STATE**, shown only "when there's one" (owner). The three real,
  already-named sub-states, mapped 1:1:
  - **Caption Mode** (§13 — `_mode_label` "Caption Mode (XML read-only)", flipped at `:2302`/`:2357`).
  - **Compare/Merge** (§12 / FQ-021, shipped — owned by `ui/diff_merge_controller.py`; note it does NOT
    touch `_mode_label` today, so this is new wiring, exactly as FQ-028 Part 2.2 also observed).
  - **Edit XSD** (§11 — `_xsd_mode`; `ui/xsd_controller.py`).
  When none of the three is active, no minor mode is displayed — just the major mode. These are the app's
  distinct notions of "mode"; the panel READS them, it does not add a new state machine.

**Proposed approach:**
- **BOTH surfaces, driven from ONE source of truth (owner, Q2).** There is exactly one place that answers
  "what is the current (major, minor) mode," and both the new toolbar panel and the status-bar label render
  from it, kept in sync so they can never disagree:
  - **A new right-aligned, color-backed panel pinned into the top `QToolBar`.** The toolbar is the movable
    "Main Toolbar" (`ui/toolbar_controller.py:140`, `objectName("main_toolbar")`, added via `addToolBar`
    from `ui/main_window.py:871`, owned by `ToolbarController`, its position persisted in `windowState`).
    Because a `QToolBar` is user-movable/floatable, "to the right of the toolbar" is only stable if the
    panel is part of the toolbar and RIGHT-ANCHORED: add an **expanding spacer widget** (a `QWidget` with
    `sizePolicy` Expanding) via `toolbar.addWidget(...)` followed by the mode-panel widget, so the panel
    stays flush right regardless of how many command buttons precede it. The panel is a `QLabel`-like
    widget with a **contrasting, per-mode background** (see palette below), reading e.g. "Project" or
    "Project · Caption" (major, then minor when present). It is added by `ToolbarController.build` (or by
    MainWindow immediately after `build`, since that is where `addToolBar` already lives) so it survives the
    same `saveState`/`restoreState` the toolbar itself does.
  - **The status-bar indicator IS the upgraded `_mode_label` (owner, Q2) — reconcile, do not add a second
    label.** Keep the single existing permanent `_mode_label`; extend it to also carry the MAJOR mode and
    the same per-mode background color, driven from the same source of truth as the toolbar panel. This
    dovetails with FQ-028 Part 2.2, which already plans to keep-and-repurpose `_mode_label` for the minor
    mode and add Diff wiring — this entry is the color + major-mode + Edit-XSD superset of that.
  - **One update path.** Introduce (or reuse, if FQ-027 exposes one) a single small helper — e.g.
    `MainWindow._refresh_mode_indicator()` — modeled on the existing single-entry `_refresh_*_affordances`
    convention, called wherever a major- or minor-mode transition happens: the launcher pick / New Session
    (major, FQ-027), Caption enter/leave (`:2302`/`:2357`), Compare/Merge enter/leave
    (`diff_merge_controller.py`), and Edit-XSD enter/leave (`xsd_controller.py` / `_xsd_mode`). Both surfaces
    are rewritten by this one call. No ad-hoc `setText`/`setStyleSheet` scattered across the transition
    sites.
- **Passive indicator ONLY (owner, Q4).** No click behavior, no context menu, no mode switching from the
  panel. It displays; it does not act. (This deliberately does NOT re-open the launcher / trigger
  `File ▸ New Session` — that stays a File-menu action per FQ-027.)
- **Theme-aware per-mode color palette (owner, Q3) — colors adjust for light vs dark.** The colors must NOT
  be a fixed hardcoded set like the DEBUG chip (`_debug_label`, `ui/main_window.py:491-494`, a static red
  `setStyleSheet` that does NOT re-theme). They must respect the `lightTheme` setting and re-render when
  `ui/theme.py::apply_theme(app, light)` flips, so contrast holds in both themes. Recommended shape: a small
  pure helper (mirroring `theme.py`'s pure `light_palette()`/`dark_palette()` split) — e.g.
  `mode_colors(light: bool) -> dict[str, tuple[bg, fg]]` — consulted by `_refresh_mode_indicator` and
  re-consulted from `apply_theme`. **Starting-proposal palette for the three MAJOR modes** (background /
  foreground; final values are the implementer's to tune, but these give a concrete, contrast-checked
  starting point):
  | Major mode | Light theme (bg / fg) | Dark theme (bg / fg) |
  |---|---|---|
  | **Standalone** | `#E3F2FD` / `#0D3B66` (calm blue) | `#1E3A5F` / `#CFE3FF` |
  | **Project** | `#E6F4EA` / `#1B5E20` (green — the "real work" mode) | `#1E3A28` / `#B6E3C0` |
  | **Maintenance** | `#FDECEA` / `#8B1E1E` (amber-red — a deliberately "you are in an admin mode" alert cast, matching FQ-027's focused-admin framing) | `#3A2320` / `#F2B8AE` |
  - **Minor mode is conveyed by TEXT, not a second color** (recommended): the panel background stays the
    MAJOR mode's color and the minor mode is appended as text ("Project · Caption"), so the eye still reads
    workflow at a glance and does not have to learn 3×4 color combinations. (Alternative in Alternatives.)
  - Contrast: both variants target WCAG-AA-ish legibility on the panel; the implementer must verify against
    the actual QDarkStyle chrome `apply_theme` applies, not just the bare palette.
- **Hard dependency on FQ-027 for the MAJOR mode's live state (see Dependencies).** FQ-027 as written is
  session-only and does NOT currently specify a persisted OR in-memory "current major mode" object that
  anything can read — picking the launcher column simply applies the menu filter. This indicator NEEDS a
  readable current-major-mode value. So EITHER FQ-027 must be extended to expose a single in-memory
  session-mode accessor (e.g. `MainWindow.current_workflow_mode()` set on launcher pick / New Session), OR
  this feature introduces that single source of truth itself. Flag explicitly: the source of truth is an
  in-memory SESSION value, not a QSettings key (FQ-027 is session-only, superseding FQ-011's persisted-mode
  design), and it must be the SAME value FQ-028 Part 2.1's status-bar label reads — never a second,
  independently-drifting notion of "current mode."

**Alternatives considered:**
- **Just relocate/upgrade the existing `_mode_label` and skip the toolbar panel** — rejected by the owner's
  Q2 answer (BOTH surfaces wanted) and by the core complaint: the status bar is at the far bottom
  (`center_stage.py:468`) and, under FQ-028, is being deliberately quieted to static-only — a prominent
  TOP indicator is the point. The status-bar label is kept, but as the secondary mirror.
- **Encode the minor mode as a second background color / a split two-tone panel** — weighed against the
  text-suffix recommendation and set aside for v1: 3 majors × 4 minor states (Editing/Caption/Diff/XSD) is
  a 12-combination color vocabulary users would have to learn, defeating "easy recognition." Recommended:
  major = color, minor = text. Recorded as the owner's to overrule if a two-tone treatment is preferred.
- **Make the panel clickable to switch modes / re-open the launcher** — rejected by the owner's Q4 answer:
  passive indicator only. Mode changes stay with the launcher pick and `File ▸ New Session` (FQ-027).
- **Hardcode the per-mode colors (like the DEBUG chip's static red)** — rejected by the owner's Q3 answer:
  the palette must be theme-aware and re-render on `apply_theme`, or the panel will be low-contrast or
  garish in one of the two themes.
- **Fold this entirely into FQ-028 Part 2 and add nothing** — rejected: FQ-028 Part 2 is status-bar-only,
  covers only Editing/Caption/Diff as minor modes (NOT Edit XSD), and has NO color and NO top-toolbar
  surface. This is a genuine superset — the prominent colored top panel, the fourth minor mode, and the
  per-mode palette — so it EXTENDS FQ-028 rather than duplicating it. The two MUST share one source of
  truth for the major/minor mode value (see Dependencies), which is exactly why it is one entry, not a rival
  design.

**Suggested placement:** **EXTEND §7 (App shell — "App shell", `CONSOLIDATED_SPEC.md` line ~492; confirm the
live number at write time).** §7 owns the app shell, the toolbar, and the status bar, and §7:1060-1062 owns
the "mode has four meanings / use precise names" rule this entry must obey. This adds: (1) a right-anchored
color-backed mode panel on the Main Toolbar (spacer-widget technique on the movable toolbar
`ToolbarController` builds), (2) the upgrade of `_mode_label` to carry major mode + color, (3) a single
`_refresh_mode_indicator` entry point feeding both, and (4) a theme-aware `mode_colors(light)` helper
alongside `theme.py`'s pure palette builders. NOT a new top-level section — it is shell chrome. Must reuse
(VERIFIED CITATIONS): `self._mode_label` + `addPermanentWidget` precedent (`ui/main_window.py:486-487`,
flipped `:2302`/`:2357`), the static-chip styling precedent to AVOID copying verbatim (`_debug_label`,
`:491-494`), the movable Main Toolbar + `addToolBar` seam (`ui/toolbar_controller.py:140`,
`ui/main_window.py:871`), the pure-palette split in `ui/theme.py` (`light_palette`/`dark_palette`/
`apply_theme`), and the three minor-mode owners (`_xsd_mode` in `ui/xsd_controller.py` §11,
Caption in `ui/center_stage.py`+`ui/main_window.py` §13, Compare/Merge in `ui/diff_merge_controller.py`
§12/FQ-021). **Supersession-ledger-worthy when folded in:** it upgrades §7's monochrome status-bar
`_mode_label` (Editing/Caption only) into a colored major+minor indicator — `spec-maintainer` should record
the change in scope rather than silently rewriting the label's description, and coordinate the wording with
FQ-028 Part 2 if FQ-028 is folded first (they touch the same label).

**Dependencies / relationships to already-queued work:**
- **HARD dependency on FQ-027** — FQ-027 defines the three MAJOR modes this panel names. FLAG: FQ-027 as
  written provides NO readable current-major-mode object (it only applies a menu filter on launcher pick).
  This feature therefore requires FQ-027 to EITHER expose a single in-memory session-mode accessor OR have
  this feature introduce that single source of truth itself. It is an in-memory SESSION value (FQ-027 is
  session-only, superseding FQ-011's persisted-mode design), never a QSettings key.
- **Tightly coordinated with FQ-028 (Part 2 — static-only status bar)** — FQ-028 already plans to keep and
  repurpose `_mode_label` for the minor mode (Editing/Caption/Diff) and add the major-mode label and DB
  dots. This entry is the SUPERSET on the status-bar side (adds color + Edit XSD as a fourth minor mode) AND
  adds the new top-toolbar panel FQ-028 does not have. They MUST share ONE source of truth for the
  major/minor mode value and ONE update path (`_refresh_mode_indicator`) — do not build two. If FQ-028 lands
  first, this extends its `_mode_label` work; if this lands first, FQ-028 Part 2.2 reads this feature's
  source of truth. Sequence them together.
- **Relates to FQ-018** (status-bar Quality/Sandbox dots, refined by FQ-028 Part 2.3) — this feature adds NO
  connectivity notion; it only wants the status bar not to grow two rival indicator regions. Coordinate so
  the mode label/color and the DB dots share the status bar coherently (owner noted this explicitly).
- **Terminology-bound to §7:1060-1062** — must use "major mode = session workflow mode" and "minor mode =
  editor sub-state (Caption/Compare-Merge/Edit XSD)"; must NOT introduce a fifth meaning of "mode."

**Open questions (non-blocking; flag to spec-maintainer/implementer):**
1. Where FQ-027's single current-major-mode source of truth lives — added to FQ-027's implementation, or
   introduced by this feature — must be settled at pickup so FQ-028 and this feature read the same value.
2. Minor mode as text suffix (recommended) vs a two-tone / second-color treatment — owner's call if the
   text suffix proves insufficiently prominent.
3. Exact per-mode colors above are a STARTING proposal; final values (and AA-contrast verification against
   the live QDarkStyle chrome, not the bare palette) are the implementer's to tune with the owner.
4. Whether the toolbar panel should also show something when NO major mode is set yet (e.g. before the
   launcher pick) or simply be blank/absent until a mode exists — left to pickup.

</details>

---

## FQ-030: Deepen §18.6 completion into a plpgsql editing assistant — schema/alias/column completion, expand-SELECT, a snippet engine, and plpgsql-semantic completion (4 slices)
**Status:** QUEUED
**Requested:** 2026-08-09
**Idea (verbatim/summarized):** Converged product-brainstorm (owner picked all four slices, "love the
ideas!", plpgsql semantics explicitly in scope): turn the shipped single-hop §18.6 completion into a real
plpgsql editing assistant. (1) `hr.jobcard.` completes COLUMNS, and every item shows type/nullable/
comment/FK-target; (2) `FROM hr.jobcard jc` … `jc.` resolves the alias to that table's columns; (3) a
keyboard action expands a bare `SELECT FROM hr.jobcard` into `SELECT j.id, j.job, j.card FROM hr.jobcard j
WHERE ` with the caret after WHERE; (4) a keyword→snippet engine with tab-stops (`case` → full CASE
expression, plus a default plpgsql set) and a plain keyword↔body table editor in Maintenance mode; plus
plpgsql-semantic completion — trigger vars, local DECLARE vars/params, `%ROWTYPE`/`%TYPE` fields, JOIN-on-FK
with an auto-written ON clause, and signature help for the shop's own functions.

**Problem:** §18.6 completion today is single-hop and stops short of its own recorded extension point.
`hr.` offers tables and `NEW.`/`OLD.` offer a trigger table's columns, but `hr.jobcard.` shows NOTHING even
though every piece needed is already present: the caret resolver already parses the 3-segment dotted path
(`sql/caret_context.py:49-52,118`) and `SchemaIndex.known_columns()` already exists (`db/schema_index.py:76-82`
— VERIFIED: it returns bare name strings and keys on `"schema.table"`). The ONLY reason the column hop is
dead is that `_show_dotted_path_completions` reads solely `context.parts[0]` and has no `len(parts)==2`
branch (`ui/ddl_object_editor.py:1493-1514` — VERIFIED at :1507; the SQL-console twin is `ui/sql_console_panel.py:805`).
Beyond that near-free hop, nothing resolves table ALIASES (`jc.` is inert), there is no way to expand a bare
SELECT into a column-listed skeleton, there is no snippet/template mechanism at all, and none of the
plpgsql-specific affordances that would make this tool beat a generic SQL editor (local scope,
`%ROWTYPE`, JOIN-on-FK, signature help) exist — despite the underlying data (`ColumnInfo{data_type,
is_nullable,comment,fk_target}` `db/introspect.py:47-60`; `RoutineInfo{args,arg_types,return_type,signature}`
`:76-108`; composite types `:216-257`) already being fetched and sitting unused in the index. §18.6 itself
NAMED the seam for all of this — the "CodeEditor-level pluggable completion provider" extension point
(`CONSOLIDATED_SPEC.md:6361-6367`) — but never built it.

**Proposed approach:** ONE epic that EXTENDS §18.6 along its own named seam, in four dependency-ordered slices.
Slices 0/1/3 all rest on ONE new scope-resolver (Slice 1), so it is built once and the surfaces fall out thin.

- **Slice 0 — near-free win (data already present):**
  - **Schema→table→COLUMN cascade.** Add a `len(context.parts)==2 → index.known_columns("sch.tab")` branch to
    `_show_dotted_path_completions` (`ui/ddl_object_editor.py:1493-1514`) AND to the console twin
    (`ui/sql_console_panel.py:805`). `hr.` → tables (today), `hr.jobcard.` → columns (new). No new parsing, no
    new introspection — the resolver already yields `parts=["hr","jobcard"]`.
  - **Enrich every completion item** with type / nullable / comment / FK-target. `known_columns` returns bare
    names today (`db/schema_index.py:76-82`); widen it (or add a sibling returning `ColumnInfo`) so the shared
    popup's `(key, display)` pairs can render e.g. `job_id  int4 · NOT NULL · → hr.dept(id)`. All four fields
    are already on `ColumnInfo` (`db/introspect.py:47-60`) — surface, do not re-fetch.

- **Slice 1 — the Qt-free FROM/alias scope analyzer (the real parsing work):**
  - **Alias→table resolution.** `FROM hr.jobcard jc` … `jc.` → hr.jobcard's columns. Add a NEW statement-scope /
    FROM-clause analyzer BESIDE `sql/caret_context.py` (e.g. `sql/from_clause.py`), Qt-free, reusing
    `sql/tokenizer.py`'s opaque-region handling (strings / comments / dollar-quotes). Add a new `CaretContext`
    kind (e.g. `ALIAS_REF`) that the `_show_*_completions` dispatch consumes alongside `ROW_VARIABLE` /
    `DOTTED_PATH` (dispatch at `ui/ddl_object_editor.py:1488-1491`). Net-new but bounded — nothing resolves
    aliases today.
  - **Expand `SELECT FROM schema.table`.** A dedicated keyboard action on the DDL-object-editor / SQL-console
    `CodeEditor` that rewrites a bare `SELECT FROM hr.jobcard` into `SELECT j.id, j.job, j.card FROM hr.jobcard j
    WHERE ` with the caret one space after `WHERE`. Reuses `SchemaIndex.known_columns` + the Slice-1 analyzer +
    the existing single-undo-block insertion idiom (`ui/ddl_object_editor.py:1577-1596`). **Alias-derivation rule
    (nail this):** alias = first letter of the table name (jobcard→`j`), every column prefixed with it;
    collisions get a disambiguating suffix (`j`/`j2`, or `j`/`jc`). Expand the TYPED table — do NOT change its
    schema (the owner's example `SELECT FROM pr.jobcard → FROM hr.jobcard j` was a harmless typo; intent is to
    preserve the typed `hr.`).

- **Slice 2 — the template/snippet engine (net-new mechanism, rides §18.6's CodeEditor provider seam):**
  - **Snippets = keyword↔snippet pairs** (owner clarified: NOT a drag-and-drop builder — just keyword→body
    pairs). A prefix + dedicated key expands to a construct: `case` → full `CASE WHEN … THEN … ELSE … END`.
    Ship a default plpgsql set: `FOR rec IN SELECT … LOOP … END LOOP`, `IF/ELSIF/END IF`,
    `BEGIN … EXCEPTION WHEN … END`, `RAISE NOTICE`, a cursor declaration, and the trigger-function skeleton.
  - **Tab-stops / placeholders on `CodeEditor`** (net-new; nothing to reuse) so after ANY expansion — snippet OR
    the Slice-1 expand-SELECT — Tab jumps between the editable spots. This is what makes both pleasant.
  - **A minimal keyword↔pairs editor in Maintenance mode.** A plain table (trigger word ↔ body ↔ tab-stops)
    under `Schema ▸ Edit Snippets…`, NOT a builder GUI. HOME/SEQUENCING: FQ-027's session-only Maintenance mode
    (Schema+Help menu filter) is the natural home, but FQ-027 is QUEUED / not-yet-spec — so this editor TARGETS
    the Maintenance surface and SEQUENCES AFTER FQ-027; until FQ-027 lands it needs an interim home or waits.
    Snippet store persists (per-user config — flag per-user vs per-project as an impl choice, see Open questions).
  - **Unifying insight to record:** expand-SELECT (Slice 1) and snippets (Slice 2) are ONE mechanism —
    template expansion with tab-stops. Expand-SELECT is a schema-DYNAMIC template, `case` is a STATIC one. Build
    ONE engine, two flavors — do not build two insertion mechanisms.

- **Slice 3 — plpgsql-semantic completion (the differentiator; all ride the Slice-1 analyzer + enriched index):**
  - **Trigger variable completion.** Inside a `RETURNS trigger` function, offer `NEW`/`OLD`/`TG_OP`/
    `TG_TABLE_NAME`/etc., and `NEW.` → the triggering table's columns. Extends today's attached/unattached
    `NEW.`/`OLD.` handling (`ui/ddl_object_editor.py:1516-1575`).
  - **Local scope completion.** The function's own `DECLARE` variables + parameters inside its body — needs the
    Slice-1 analyzer to read the DECLARE block.
  - **`%ROWTYPE` / `%TYPE` field completion.** `rec hr.jobcard%ROWTYPE` → `rec.` → jobcard's columns (same
    resolver path as aliases; composites via `DatabaseSchema.types`, `db/introspect.py:216-257`).
  - **JOIN-on-FK.** After `FROM hr.jobcard j JOIN ` offer FK-related tables and auto-write the ON clause
    (`ON j.dept_id = d.id`), using `ColumnInfo.fk_target` (already fetched, `db/introspect.py:47-60`).
  - **Signature help.** Completing a call to one of the shop's own functions shows its parameter list;
    `RoutineInfo{args:[(name,type)], arg_types, return_type, signature}` (`db/introspect.py:76-108`) is present.

- **SHARED CONTRACTS TO REUSE (mandatory anti-fork guardrails from the placement gate):**
  - Extend `db/schema_index.py::SchemaIndex` (already carries columns / FK / routine-args / types) — do NOT
    build a second index.
  - The alias / FROM / DECLARE analyzer lives Qt-free in `sql/` beside `caret_context.py`, reusing
    `sql/tokenizer.py` — NEVER parse SQL in `ui/`.
  - Render through the ONE shared popup `ui/completion_popup.py::_CompletionPopup` /
    `CompletionPopupHostMixin` (`(key, display)` pairs) — do NOT invent a second popup.
  - Single fetch path `db/introspect.py::fetch_routines_and_triggers` pushed via the injection idiom
    (`set_schema_index`, panel-never-talks-to-DB, §18.5 D1) — do NOT add a lazy per-keystroke DB query
    (§18.6 invariant, `CONSOLIDATED_SPEC.md:6391`).
  - Insertion via the existing single-undo-block idiom (`ui/ddl_object_editor.py:1577-1596`).
- **CONSUMERS / WIRING:** deepen every SQL consumer of §18.6 via the shared machinery — the DDL object editor
  (`ui/ddl_object_editor.py:505,1476`), the Sandbox SQL Console (`ui/sql_console_panel.py:374,805`), and the raw
  XML editor (XML path). DO NOT wire the read-only DDL Explorer viewer (`ui/ddl_editor_panel.py`) — §18.6
  excludes it deliberately (`CONSOLIDATED_SPEC.md:6357-6358`).

**Alternatives considered:**
- **Build points 1/2/3 as three independent features** — REJECTED: they all rest on ONE scope-resolver, so the
  resolver is built once (Slice 1) and the surfaces fall out as thin consumers. Three parallel features would
  each grow its own resolver — the exact fork the gate forbids.
- **A rich drag-and-drop snippet BUILDER GUI** — REJECTED by the owner: a keyword↔body pairs table only, no
  builder.
- **Replacing §18.6's existing completion with a new path** — REJECTED: this is an EXTEND along §18.6's own
  named `CodeEditor`-level pluggable-provider seam (`CONSOLIDATED_SPEC.md:6361-6367`); the shipped single-hop
  behavior (schema→table, `NEW.`/`OLD.`) stays and is deepened, nothing is replaced or forked.
- **A second SchemaIndex / a second completion popup / parsing SQL in `ui/`** — REJECTED as the four classic
  duplication traps (see below); all reuse is mandated.

**Suggested placement:** **EXTEND §18.6 (`CONSOLIDATED_SPEC.md:6259`)**, realizing its recorded
`CodeEditor`-level pluggable-provider extension point (`:6361-6367`). Slices 0/1/3 are §18.6 deepenings; Slice
2's template engine rides the SAME seam. It is NOT a new top-level section. `spec-maintainer` should fold all
four slices into §18.6 (noting the completion machinery grows from single-hop to a scope-resolver-backed
assistant), preserve the §18.6 invariants (no lazy per-keystroke DB query `:6391`; read-only viewer excluded
`:6357-6358`), and CROSS-REFERENCE FQ-027 (`docs/FEATURE_QUEUE.md:3298`) for the Slice-2 snippet-editor's
Maintenance-mode home — sequenced AFTER FQ-027, referenced NOT as a hard spec dependency (FQ-027 is still
QUEUED). Must reuse the verified contracts above and their citations.

**Duplication traps (record and honor):** (1) no second `SchemaIndex` — extend the existing one; (2) no SQL
parsing in `ui/` — the analyzer is Qt-free in `sql/` reusing `sql/tokenizer.py`; (3) no second completion popup
— render through `ui/completion_popup.py`; (4) do NOT conflate Slice-2 editing snippets with FQ-002's
object-CREATION skeletons (different surface, different purpose); (5) do NOT wire the read-only DDL Explorer
viewer (`ui/ddl_editor_panel.py`, §18.6-excluded); (6) do NOT write FQ-027 as a spec dependency — it is QUEUED;
reference it for the Maintenance home and sequence after it.

**Open questions (non-blocking; flag to spec-maintainer/implementer):**
1. Snippet store scope — per-user vs per-project vs shipped-defaults-plus-user-overrides (owner leans toward a
   shipped default set with user overrides; settle at pickup).
2. The dedicated keys for expand-SELECT and snippet-expand — must NOT collide with Ctrl+Space completion or any
   existing shortcut; coordinate with FQ-012 (Customize Shortcuts) if it lands.
3. Casing convention for generated SQL (auto-uppercase keywords / lowercase identifiers) — nice-to-have, defer.

---

## FQ-031: Dual gutter line numbering for function/procedure bodies — show a body-relative (AS-anchored) number beside the absolute one, matching plpgsql error line numbers
**Status:** QUEUED
**Requested:** 2026-08-09
**Idea (verbatim/summarized):** "all function and procedure line numbering must start from the line with AS
because error messages from plpgsql start numbering from AS down."

**Problem:** This is a PURELY ADDITIVE DISPLAY gap, NOT a correctness defect — the app already maps plpgsql
findings correctly and AS-anchored. `db/ddl_check.py::body_line_offset(buffer_text)` (VERIFIED at :661) locates
the 1-based line `L` of the opening dollar-quote tag (`$$`/`$function$`/`$body$`), and `map_lineno` (VERIFIED at
:676) maps a `prosrc`-relative number to an absolute buffer line via `L + lineno - 1`. Per §18.5 D3 (its own
docstring, `db/ddl_check.py:679-680`: "`prosrc` line 1 **is** line `L`"), clicking a Check/Lint finding ALREADY
jumps to the right line — there is NO defect and NO change to finding navigation. The gap the owner is closing
is only the VISIBLE gutter: `ui/editor_gutter.py` shows ABSOLUTE buffer numbers (`number_text = str(block_number
+ 1)`, VERIFIED at :192), so line 1 is `CREATE OR REPLACE FUNCTION…`. A raw plpgsql error read by eye ("line 5")
does not line up with the gutter, because the gutter is not anchored at AS.

**Proposed approach (owner converged on "Dual numbers — absolute + body-relative"):**
- For function / procedure / trigger-function bodies in the DDL object editor, the gutter shows **TWO numbers
  per line: the ABSOLUTE buffer line (primary, unchanged) AND a BODY-RELATIVE number anchored so the
  `AS`/dollar-quote-opener line = body-relative line 1** — matching plpgsql's `prosrc` numbering (§18.5 D3,
  where prosrc line 1 IS line `L`).
- **Absolute stays primary and unchanged** — Find-All results, bookmarks, and the Check/Lint findings' absolute
  `line` all rely on absolute buffer lines, so DUAL (not replace) is required precisely so navigation is not
  disturbed. This is why the owner chose dual over renumber-only.
- **Lines ABOVE the AS opener (CREATE / RETURNS / LANGUAGE header) get NO body-relative number** — blank in the
  body-relative column; counting starts at line `L` and runs down.
- **Reuse `db/ddl_check.py::body_line_offset()` (:661) to locate the anchor `L`** — do NOT reimplement
  dollar-quote detection; it already handles `$$`/`$tag$` and line-comment stripping and is the §18.5 D3 source
  of truth.
- **Graceful absence:** if `body_line_offset` returns None (no locatable dollar-quote opener — e.g. a
  `LANGUAGE sql` function, or a non-routine buffer), show the ABSOLUTE number only, no body-relative column —
  mirroring §18.5 D3's "None is a real answer, never guess" discipline (`db/ddl_check.py:665-667`). Never render
  a guessed body-relative number.
- **Scope:** the DDL object editor's `CodeEditor` gutter when the edited object is a function / procedure /
  trigger-function (`ui/ddl_object_editor.py`, host of `CodeEditor` in `ui/code_editor.py`). Non-routine buffers
  and the raw XML editor are unaffected.
- **Rendering:** widen the gutter to render two numbers (e.g. `absolute│body-rel`, or two right-aligned
  columns). Note the gutter-width implication in `ui/editor_gutter.py` — the line-number zone width today is
  `self.width() - number_x` (:188) and `number_x` starts after the bookmark strip + fold glyph (:187); adding a
  second column requires widening the gutter and splitting that zone.

**Alternatives considered:**
- **Renumber the gutter body-relative ONLY (hide absolute)** — REJECTED by the owner (chose dual); it would also
  desync the gutter from the absolute lines that Find-All, bookmarks, and findings' absolute `line` rely on.
- **"Internal mapping is enough, change nothing"** — REJECTED: `map_lineno`/`body_line_offset` already make
  finding-navigation correct, but the owner specifically wants the VISIBLE numbers to match plpgsql's error
  numbering by eye, which the absolute-only gutter does not do.

**Suggested placement:** EXTEND **§18.5 D3** (the AS/dollar-quote line-anchor logic already lives there as
`body_line_offset`/`map_lineno`; this surfaces that SAME anchor in the gutter) with a **§8 (editor gutter)**
touch for the dual-column rendering. Confirm the live section numbers at spec-fold time. Reuse
`db/ddl_check.py::body_line_offset` — do NOT fork a second anchor computation. This is NOT a new top-level
section. No new introspection, no DB, no new parsing — `body_line_offset` already exists.

**Open questions (non-blocking):**
1. Whether the Sandbox SQL Console (§18.5 D4) should also show the body-relative column when its buffer happens
   to contain a `CREATE … AS $$` routine — recommend NO for v1 (the console is ad-hoc SQL, not a routine
   editor); keep it to the DDL object editor.
2. Exact two-number gutter layout — separator glyph, alignment, and whether the body-relative number is dimmed
   relative to the primary absolute number.

---
