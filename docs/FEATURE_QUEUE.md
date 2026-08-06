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
