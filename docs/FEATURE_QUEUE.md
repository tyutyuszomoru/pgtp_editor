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
**Status:** QUEUED
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
