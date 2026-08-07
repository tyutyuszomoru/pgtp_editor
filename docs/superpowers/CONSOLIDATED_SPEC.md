# PGTP Editor — Consolidated Specification

> **Status:** living document · **Last synthesized:** 2026-08-07 — **the UX-review batch FQ-010/FQ-013/FQ-014/FQ-015/FQ-016/FQ-017 folded in, with FQ-011 recorded as mechanism-only.** §7 gains the **startup launch modal** (`ui/launcher_dialog.py`, four groups of menu-path command ids, `launcherSuppressed` + `File ▸ Show Launcher…`, the `--mcp`-can-never-reach-it invariant) and loses both `File ▸ Open Recent`/`recentFiles` and the GUI's `argv[1]` open; §7/§26 gain a **second, fixed Editor menu bar** (History / Select / Parsing / Bookmarks) and record the **Edit menu's dissolution**; §8/§15 make every `FindReplaceBar` **permanently visible** (`Ctrl+F`/`Ctrl+R` become focus gestures, `Escape` returns focus); §8 gains **project-mode-only bookmark persistence** (`.ddlproject/bookmarks.json`) and **`List All Bookmarks`** with a new `[Bookmark]` Audit prefix, plus the `Select` menu and the trigger-time-dispatch fix for the two block-selection commands; §13 **deletes the caption find/replace modal** and makes the caption bar permanent with `Replace All` + `Clear filter` + a filter/project scope dropdown; §27 rewrites the Find/Replace rows, gives **`F3` its own menu-less window-level row** beside `Ctrl+L`, deletes `Ctrl+Shift+F`/`Ctrl+Alt+Return` and the Caption-Mode override row, and adds `Ctrl+A` and `Escape`. **FQ-011's per-mode menu membership is deliberately NOT specified** — only `Generate` in project mode was ever named (§7/§29). Six ledger rows (§28). Also corrected against the shipped code: the menu walk and the Find/Bookmark dispatchers live on `ToolbarController`/`FindValidateController`, not on `MainWindow`. (Previously 2026-08-06; before that 2026-08-05: §18.8 corrected to the 5-node model, then given its concrete per-node state enumeration + dark-mode asset convention, then a same-day fix to the Quality node's locked/gray semantic and the Sandbox2 install-state-vs-lint-result semantic; later the same day, BUG-020/021/022/023/024/025 folded in — Captions' preset row-predicate filter + active-filter banner + Unify scope prompt, §18.2's Open-Project validity gate + auto-open of the linked `.pgtp`, the tabbed Project Settings dialog, and Connection Setup… becoming projectless-mode-only; later still the same day, §18.1's Tables branch widened to every table (not just trigger-owning ones) plus click-to-Properties-panel column detail, with `ColumnInfo.comment` added; and finally BUG-021/026/027/028 — §18.2's project-action lambda wiring that made the `.pgtp` auto-open actually reachable, §17's role-split `(P# D# L#)` DB→XML counts and any-role mismatch rule, §7's toolbar widened to every menu command with menu-path ids, and §13's active-filter banner extended to the whole-row find filter). **2026-08-06:** FQ-001 folded into §18.2 — per-group Test buttons on the Project Settings dialog's Connections tab (generic connectivity for Target, superuser probe for Sandbox). Same day: the §18.2 project actions' menu location corrected from Database to **File**, matching the shipped `_build_file_menu` (§26, ledger 2026-08-06). Same day: FQ-002 folded in — §18.1 gains "Creating brand-new objects from the Explorer" (Add Trigger… on a table node, one New Function/Procedure… action on the routines-branch root and the Database menu, the shipped pure `db/ddl_skeleton.py` contract, and manifest registration of the new object so the existing §18.3/§18.4 deploy flow sees it), with §18.5 D1 gaining the third (creation) entry point into the same editable tab and two ledger rows (§28). Same day: FQ-003 folded in — §17 gains **the Database/XML Coherence view**, one merged left-dock surface replacing the two DB-check directions *and* §15's standalone Table References tab (direction toggle eliminated on the "DB is always the truth" framing; a recursive, depth-faithful Pages branch; one global mismatch toggle spanning both branches), with §15 reduced to a pointer, §26's View-menu "Find table reference" and the two Database-menu check items replaced by one Database-menu toggle, and two ledger rows (§28). **Same day, a status-accuracy audit against the shipped code** (no design changes): §17's coherence view, §18.1's FQ-002 creation entries, §18.4's formatter *consumer*, §18.6's completion and §18.8's Project Status window were all marked "not yet implemented" while shipping, and are now marked implemented; §18.5 is split honestly into the shipped editor half vs. the unbuilt Apply/sandbox/ladder half; §18.3 is restated as "every module ships, nothing reaches them"; §5's module tree/table, §7's tab & routing notes, §26 and §27 were swept for the same drift. One genuine design narrowing was recorded with a ledger row: §18.3 step 2's deploy blockers are **`*!` only**. **Also 2026-08-06, owner decision — the sandbox becomes *executable*, not merely inspectable:** §18.5 gains **D3a** (the Check gesture's concrete run contract — what `plpgsql_check_function_tb` is invoked with, how the four `plpgsql_check_state` values gate a run, and how findings reach the `[Check]` Audit lines with click-to-navigate) and **D4** (ad-hoc SQL execution against the sandbox — the **Sandbox SQL Console** tab, `db/sandbox_query.py`, `ui/sql_results_panel.py`, a 1 000-row cap, a mandatory statement timeout, and the **sandbox-only, structurally enforced** safety rule). §29's *"Execution against the sandbox … is not designed"* open question is **closed** by that pass; §5/§7/§26/§27/§18.8 updated to match, with five ledger rows (§28). **Finally, also 2026-08-06:** FQ-005 folded into §7's theme paragraph and §4 — the QDarkStyleSheet QSS layer now covers **both** themes (`_qdarkstyle_stylesheet(light)` / `_qss_cache`, explicit `LightPalette`/`DarkPalette`), retiring the *"light always assigns the empty stylesheet"* invariant and the dark-only attribution, with one ledger row (§28). **Also 2026-08-06, a second status-accuracy sweep against the shipped code** (no design changes): stale absence claims flipped for `db/routine_refs.py`'s pure layer (§18/§18.1/§29 — shipped, richer than sketched; its UI consumer is the remaining gap), the `lint/` and `mcp/` packages (§5/§7/§22/§23 — built, not fully wired), §21's `ui/php_file_tab.py` phase 1 (built, hosted by `CenterStage`, no File-menu entry yet), §18.2's since-built sandbox provisioning layer, §8/§27's gutter double-click bookmark toggle (shipped as designed), §18.1/§18.5 D1's `EditorPanel` span retention (done; `set_ddl_text` gained a third `schema` parameter) and §18.1's ddl_table row-pairing cue (shipped as the alternating shade); §18.8's stale menu-entry open bullet deleted and §28's FQ-003 row trailer corrected in place. No new ledger rows — these are status corrections, not supersessions. **Also 2026-08-06, a menu/shortcut/signal reference-accuracy batch from the 8-reviewer code-vs-spec audit** (no design changes, no ledger rows): §13/§26/§27's caption-mode shortcuts corrected to the shipped window-scoped, mode-gated Ctrl+F (Filter) / Ctrl+R (Replace) pair with a shortcut-less Tools menu item and a non-modal `show()` dialog (plus a caption-override row in §27's table); the DDL-object-editor fourth branch added to §15/§8/§26's `_active_find_bar`/`_active_bookmark_editor` dispatch lists; §17's coherence-panel jump signals corrected to `jump_requested(object)` + `name_jump_requested(kind, name)`; §15's `FindReplaceBar` signature corrected to `(editor, on_find_all=None)` with setter-injected callbacks; §9's reparse hook restated as the coherence-view refresh (`_refresh_db_check_if_open`, legacy name); §11's Schema-menu position fixed to between View and Database; §10's `show_node` kinds gained `"lookup"`/`"ddl_table"`; §27 gained the three-context Ctrl+Space row; §26 gained Edit ▸ History… (Undo/Redo step directly, §7), dropped the nonexistent Help ▸ Documentation, and clarified the two same-label "New Project" actions; and §5/§15 record that `ui/table_references_panel.py` **and** `ui/db_check_panel.py` (plus their tests) are now physically deleted. **Also 2026-08-06, the §18-area reference/status batch from the same audit** (stale-reference and false-status fixes; one ledger row): per-object tab keying corrected to `DdlObjectRef.key` (§18.1/§18.2); the write-seam wording re-scoped to writes **to the target** with sandbox writes through the sandbox session's named seams (§18.2/§18.5, matching D2's ownership table and the three-seams invariant); §18.3's reachability claim narrowed (the close-time deploy reminder ships — only the bundle/compare flow is unreachable), its step 3 restated to the shipped verbatim-text `db/deploy_bundle.py` assembly (the diff engine's second entry point is §18.5's Generate Deployment SQL), and `diff_schemas` pinned to its shipped `SchemaDiffResult` return; §18.4's stale "no live consumer" sentence dropped; §18.5's `apply_ddl`/`ApplyOutcome` sketches replaced by the shipped signatures (no `autocommit` parameter — `db/sandbox.py::_run_autocommit` owns that path; per-statement `results: tuple[StatementResult, ...]`); §18.6's consumer count widened to include the D4 console as a third completion consumer; §18.2/§18.7's `ProfileKey` claims re-marked as **target design, not implemented** (`db/config.py` ships only the hardcoded `"db"` group; no ConnectionSetupDialog profile selector exists — §17's own profile block deliberately untouched, its rewrite pending a human decision); and §18.8's asset pipeline pinned to the shipped `.svg`-only, stateless-connector `ui/project_status_model.py` layer (ledger row, §28). **Also 2026-08-06, the closing batch of the same audit** (structural/reference corrections plus one never-folded shipped feature): **FQ-004's Breeze toolbar icon picker** folded into §7/§5 (`ui/icon_picker_dialog.py`, `ui/icons.py`'s catalog, the `toolbarIconIds` assignments — shipped commit `a12b522`; one ledger row, §28, superseding "icon-less by design"); §5's false dependency claims corrected to the true arrows (`diff/` is Qt-free and imports only `model/`, consumed by `ui/`/`mcp/`; `model/` owns parse+serialization but is not the only lxml importer); `sql/caret_context.py` added to §5's tree and §18.4's "five modules" count scoped to the formatter feature; §7's tab-close dispatch restated as shipped (fixed indices first, dynamic tabs in the else branch by map lookup — behaviorally equivalent); §11's curated.xsd attribute count refreshed to 254 with a counts-drift caveat; §24's manual chapter enumeration replaced by a non-enumerating statement (the `manual-maintainer` agent owns the list; `manual.md`'s headings are the source of truth); §29 pruned of answered items (overload-rename trimmed to its timing sub-question; D2a's PATH-only/`--format=custom`/probe-fold answers pinned to the shipped `db/sandbox.py`; the debug-exclusions/`PROFILER_ID` item resolved against `debuglog.py`; the handler-body-storage *answer* moved into §6's `EventNode`); §30's test-environment summary rewritten to CLAUDE.md's platform-dependent interpreter + offscreen + `-n 10` parallel-suite rules; and §20.4's duplicated deferred-git paragraph reduced to a pointer at §21's canonical copy. **Also 2026-08-07, a correction pass against the shipped FQ-010/FQ-016/FQ-017 code** (two ledger rows): §7's claim that a launcher group choice *"sets the persisted launch mode"* is **wrong and corrected** — `show_launcher` triggers the picked QAction and stores no mode; FQ-011 stays recorded as **planned only**. §7/§13/§15/§26/§27's reason for deleting `set_find_actions*` is corrected too: **FQ-017 rescoped the caption shortcuts rather than deleting them**, and the real reason is the Qt **ambiguity** hazard (a window-level `Ctrl+F` would fire *neither* shortcut), which is why `Ctrl+F`/`Ctrl+R` are hosted **per tab** by `find_replace_bar.install_focus_shortcuts` at all six bar sites. FQ-016's shipped shape folded in: the Editor bar ships **three** menus (History · Parsing · Bookmarks; `Select`/`List All Bookmarks` are insertion points, leaving `Ctrl+Shift+B`/`Ctrl+Shift+A` temporarily unbound), `centralWidget()` is now an anonymous container, the alias table's outcome is pinned (`parsing.validate-project`, `find` retired from three tables, **six** default buttons, `edit-find.svg` still user-assignable), `Parsing` is deliberately ungated, and three §29 open items are **closed** — the `Ctrl+F` reveal, the Caption/Manual bar visibility, and lint staying whole on Tools. **Also 2026-08-07, FQ-013's wiring and FQ-014 folded in as shipped, with two corrections (two ledger rows):** (1) §8/§7's *"no `UserRole+2`"* payload rule is **wrong** — the router's PHP branch reads the CenterStage tab key from `UserRole+2`, so a `[Bookmark]` row in a PHP tab that omits it is **inert**; reusing the router's discriminator means **all three roles for PHP** and two for the others (§8 now carries the per-editor role table). (2) §8's claim that **Edit XSD / Edit AutoXSD bookmarks persist** is **impossible** — their schema files live in the app-level `schema_storage_dir`, outside any project, so `relative_key` returns `None`; exactly **three** editors persist (Raw XML, DDL object tabs, PHP file tabs) and the XSD editors join the identity-less ones as session-only by construction. Also pinned from the shipped code: the gate is the capability fact **`DdlProjectController.folder`** (projectless = bit-for-bit status quo, **no debounce started, no file written**); **400 ms debounce + synchronous flush on project transition and in `closeEvent`**, pending entries resolved at change time; **restore at the document load** plus a project-open sweep; the gutter mixin's new **module-level observer registry** (`add_bookmark_observer`/`remove_bookmark_observer`, `BOOKMARKS_TOGGLED`/`CLEARED`/`RESET`, `restore_bookmarks`, `WeakMethod`-held, `RuntimeError`-tolerant) which publishes and interprets nothing; and FQ-014's shipped shape (last on the Bookmarks menu, no shortcut, `_BOOKMARK_PREFIX` constant, 1-based lines, roles-less count/empty rows, active editor only, roles-less inert rows for unroutable editors, stale-row sweep on `BOOKMARKS_RESET` **only**). §29's bookmark-persistence item is closed except for the still-uncalled `prune_missing_files`. **Also 2026-08-07, FQ-015 folded in as shipped (commit `9146524`), with one ledger row:** the Editor menu bar's **`Select` menu is BUILT** — four menus now, `Select` between History and Parsing (`_build_select_menu`) — and all three commands resolve the editor at **trigger** time through `FindValidateController.active_selection_editor()`, which **delegates to `active_bookmark_editor()`** so "which editor is the user looking at" has one answer. `Select Enclosing Block` dispatches **by capability** (`XmlEditor.select_enclosing_block` vs `CodeEditor.select_enclosing_brackets`); `Select Parent Block` is XML-only and **HIDDEN** on `CodeEditor` tabs — **the affordance seam's first real capability gate**, which §7 had described as wired-but-unexercised. `CodeEditor.keyPressEvent`'s duplicate `Ctrl+Shift+B` is **kept** (measured: the QAction wins where it exists; the handler is the only host in the menu-less `CodeEditorDialog`). One §8 read-only defect fixed with it: `XmlEditor._is_text_modifying_key` treated a Ctrl chord's printable `text()` as typing, so a read-only `XmlEditor` **swallowed Ctrl+A** and flashed the read-only hint; a Ctrl/Meta chord is now a command, tested **after** `matches(Paste)` so Ctrl+V keeps its hint. Two §29 items closed (read-only `Select All`, the duplicate-handler question).
> **Source of truth:** this file is the single reconciled specification for PGTP Editor, and the **only**
> place specification content is written. It was originally synthesized from the dated design specs under
> [`docs/superpowers/specs/`](specs/) — a folder now **frozen as historical record** (read for rationale;
> never added to or edited). All new and changed design is written **directly here**, using a
> **latest-wins** rule: where a later decision overrode an earlier one, only the later decision
> is stated in the body, and the change is recorded in the [Supersession Ledger](#28-supersession-ledger).
> Maintained by the **`spec-maintainer`** agent (`.claude/agents/spec-maintainer.md`) — see
> [§31 Maintenance protocol](#31-maintenance-protocol).

---

## Table of contents

1. [Purpose & scope](#1-purpose--scope)
2. [`.pgtp` file format & invariants](#2-pgtp-file-format--invariants)
3. [Element hierarchy](#3-element-hierarchy)
4. [Technology choices](#4-technology-choices)
5. [Package / module layout](#5-package--module-layout)
6. [Data model](#6-data-model)
7. [App shell](#7-app-shell) — *includes the startup launch modal (FQ-010, shipped — **it stores no launch mode**) and the second, fixed **Editor menu bar** (FQ-016, shipped as three menus), both 2026-08-07; FQ-011's launch mode is **planned only***
8. [Raw XML editor](#8-raw-xml-editor) — *project-mode-only bookmark persistence (FQ-013) and `List All Bookmarks` (FQ-014) — **both shipped** 2026-08-07; the `Select` menu with trigger-time dispatch (FQ-015) and the permanently visible Find/Replace bar (FQ-016) — **both shipped***
9. [Editor ↔ Tree sync & Reparse](#9-editor--tree-sync--reparse)
10. [Properties panel](#10-properties-panel)
11. [Schema: curated XSD, learning & completion](#11-schema-curated-xsd-learning--completion)
12. [Diff / Merge](#12-diff--merge)
13. [Captions](#13-captions) — *the find/replace **modal is deleted**; the in-panel bar is permanent, with `Replace All` + `Clear filter` + a filter/project scope dropdown (FQ-017, 2026-08-07)*
14. [Columns](#14-columns)
15. [Search, Find All & Table References](#15-search-find-all--table-references) — *table references folded into §17's Database/XML Coherence view (FQ-003, 2026-08-06); §15 keeps a pointer only*
16. [Validation](#16-validation)
17. [Database](#17-database) — includes [the Database/XML Coherence view](#the-databasexml-coherence-view) — *implemented (FQ-003, 2026-08-06): `db/coherence.py`, `ui/coherence_panel.py`, the Database-menu toggle*
18. [DDL versioning (standalone Postgres mode)](#18-ddl-versioning-standalone-postgres-mode) — *partly implemented — see each subsection*
    - [18.1 Routines & triggers browsing (DDL Explorer)](#181-routines--triggers-browsing-ddl-explorer) — *implemented, including object **creation** (FQ-002, 2026-08-06); XML cross-refs' pure layer (`db/routine_refs.py`) shipped — its UI consumer is the remaining gap*
    - [18.2 Projects, checkout & state markers](#182-projects-checkout--state-markers) — *implemented (git integration is an explicit TBD placeholder)*
    - [18.3 Deploy workflow & schema diff/migration](#183-deploy-workflow--schema-diffmigration) — *all the pieces ship (diff/migration engine, `db/schema_snapshot.py`, `db/deploy_bundle.py`, `ui/schema_compare_panel.py`); **none are reachable** — no menu entries, no flow driving them*
    - [18.4 SQL/plpgsql selection formatter](#184-sqlplpgsql-selection-formatter) — *implemented, core + consumer: `Ctrl+Alt+F` / context-menu Format Selection in the DDL object editor, `[SQL]` Audit refusals wired*
    - [18.5 The DDL object editor, apply & sandbox validation](#185-the-ddl-object-editor-apply--sandbox-validation) — *partly implemented: the editable tab, Save/Save As, formatting and completion ship, and as of 2026-08-06 so do **Apply to Sandbox / Apply to Target / "Deploy this edit…"** (`ui/ddl_object_editor.py`, with all four Apply-to-Target preconditions enforced) and the **sandbox session controller** (`ui/sandbox_controller.py`, the host for `db/sandbox.py`'s previously unreachable `open_sandbox`). Still **not** built: the MainWindow wiring that hands the controller's operations to the panel's apply seams (so the affordances are absent in the running app), `db/ddl_check.py` and the validation ladder (D3/**D3a**, the Check run contract settled 2026-08-06), **D4's Sandbox SQL Console** (`db/sandbox_query.py`, `ui/sql_console_panel.py`, `ui/sql_results_panel.py` — ad-hoc sandbox-only SQL execution with a visible result set, settled 2026-08-06), and the deployment-script generation. The deliverable remains the generated deployment SQL script.*
    - [18.6 Schema-aware Ctrl+Space completion in the DDL object editor](#186-schema-aware-ctrlspace-completion-in-the-ddl-object-editor) — *implemented*
    - [18.7 Two live DDL Explorer instances — target vs. sandbox](#187-two-live-ddl-explorer-instances--target-vs-sandbox) — *settled design (2026-08-05), not yet implemented*
    - [18.8 The Project Status window](#188-the-project-status-window) — *implemented (5-node diagram, per-node click-through windows, Database ▸ Project Status…); two affordances deliberately withheld pending §18.5's sandbox lane, and the App node's action window is still the flagged placeholder (§29)*
19. [PHP generation (vendor) & Save](#19-php-generation-vendor--save)
20. [re_phpgen — own generator & gap loop](#20-re_phpgen--own-generator--gap-loop)
    - [20.4 Production cutover](#204-production-cutover-target-design--not-yet-reached) — *planned*
21. [Custom PHP editing](#21-custom-php-editing) — *phase 1 built (`ui/php_file_tab.py` + `CenterStage` hosting + `File ▸ Open PHP File…`, verified present 2026-08-07)*
22. [Lint integration](#22-lint-integration) — *`pgtp_editor/lint/` ships, consumed by `PhpFileTab`; **the three Tools-menu entries now exist** (`Lint Current File`, ☐ `Lint on Save`, `Locate PHP Linter…` — verified 2026-08-07). Status text inside §22 not yet re-audited*
23. [MCP integration](#23-mcp-integration) — *`pgtp_editor/mcp/` ships, headless `--mcp` works, and **Tools ▸ ☐ `Start MCP Server` now exists** (verified 2026-08-07). Status text inside §23/§5 not yet re-audited*
24. [In-app manual](#24-in-app-manual)
25. [Debug mode](#25-debug-mode)
26. [Consolidated menu bar](#26-consolidated-menu-bar) — ***two** menu bars since FQ-016 (2026-08-07): the window bar, and [the Editor menu bar](#the-editor-menu-bar-fq-016-2026-08-07) (**History · Select · Parsing · Bookmarks** — all four ship). `Edit` no longer exists*
27. [Consolidated keyboard shortcuts](#27-consolidated-keyboard-shortcuts) — *all bindings are **fixed**; FQ-012's rebinding dialog is a separate, un-folded proposal*
28. [Supersession ledger](#28-supersession-ledger)
29. [Open questions](#29-open-questions)
30. [Testing policy](#30-testing-policy)
31. [Maintenance protocol](#31-maintenance-protocol)

---

## 1. Purpose & scope

PGTP Editor is a **PySide6 (Qt6) desktop tool** for editing SQL Maestro PostgreSQL PHP Generator
("PHPGen" / the "vendor tool") `.pgtp` XML project files. It targets **`.pgtp` format version 22.8**.
It also functions as a **standalone Postgres DDL-versioning tool** (§18) — usable with **zero `.pgtp`
files involved** — sharing the app's existing DB connection, code editor, and diff infrastructure
rather than being a separate product.

**Product framing (the frame that ranks the roadmap, stated by the project owner).** The app exists to
help developers build **heavily plpgsql-centred applications safely and efficiently**. It is a direct
correction of what those developers hit in **DBeaver — "where the only possibility is to break the
database."** In DBeaver, editing a function and deploying it are the *same keystroke*: `CREATE OR
REPLACE` runs against the live database the moment you save, with no intermediate state, no preview and
no undo. **DBeaver's feature set is the floor, not the goal.** The direction is a smart IDE that keeps
the `.pgtp` XML and the database **in sync** for fast, safe function/procedure development. Consequently
the **edit → validate → apply loop (§18.5) is the core value proposition, not a side feature**, and
§18's ordering follows from that: the sandbox is the missing intermediate state where *"I changed this"*
and *"production changed"* are finally two different events; git versioning (§18.2), drift markers and
the reviewed deploy bundle (§18.3) are all downstream of that one separation.

**In scope:** parsing, viewing, structurally editing, diffing/merging, validating, and DB-checking
`.pgtp` files; invoking the vendor generator; (as a separate sub-project) reverse-engineering the
vendor's `.pgtp`→`.php` transformation; and — independent of `.pgtp` entirely — versioning PostgreSQL
routine/trigger DDL against git with live-DB drift detection and reviewed deploy (§18). This last item
is a deliberate broadening of the app's purpose beyond `.pgtp` editing: it was designed, and chosen to
live **in this same app as an independent mode**, rather than as a separate tool/repo (the alternative
modeled by `re_phpgen`, §20/§20.4) — see §18 for the rationale.

**Hard boundary (staged, with a named exit):** *today*, `.pgtp` → `.php` compilation is **one-way and
owned by vendor tooling**; PGTP Editor never edits or generates PHP as part of the editing workflow.
`re_phpgen` (§20) stays **gap-analysis-only**, invoked **read-only as a subprocess** — phpgen (the
vendor CLI/GUI) remains the tool of record. This is not a permanent wall: `re_phpgen`'s **stated end
goal is production replacement of the vendor generator**. The wall only opens once **all** of the
falsifiable promotion criteria in §20.4 hold, and even then cutover is **per-project and explicit**
(never silent, never automatic) — see §20.4 for the full criteria and cutover mechanism. phpgen remains
available indefinitely afterward as the fallback/reference oracle.

**Formally dropped features** (see ledger): Move/Copy of `Detail` blocks and Client read-only page
generation — both superseded by the Raw XML editor's structural block-select + OS clipboard, which can
cut/copy/paste even folded blocks.

---

## 2. `.pgtp` file format & invariants

These are load-bearing; every editing path must preserve them.

- Single-root `<Project>` XML. **UTF-8, no XML declaration, no BOM, LF line endings, no CDATA.**
- Inline PHP/JS event-handler code is stored as **entity-escaped text directly inside elements**
  (no CDATA wrapping). `<` and `&` must be XML-escaped when writing handler bodies.
- **Byte-for-byte round-trip fidelity is the master invariant:** attribute order, escaping, LF
  endings, and absence of reformatting must be preserved, or round-tripping through the vendor GUI
  breaks. Saving writes the **raw editor text** (the authoritative surface) — the parsed model is
  never re-serialized on save.
- An element's opening tag (all its attributes) is on a **single line** — relied upon by
  line-anchored edits (captions, DB rename).
- On-disk indentation unit: **two spaces**.
- One known benign residual: libxml2 un-escapes `&quot;` inside element *text* (not attribute values)
  to a literal `"` on reserialization. Round-trip tests normalize this; it is not a bug.
- Sample files (`sample/dev_Ferrara.pgtp`, `sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp`)
  contain live plaintext DB/SSH credentials. `sample/` and `.superpowers/` are git-ignored and must
  never be committed. Tests needing them skip gracefully when absent.

**Vendor generator CLI (confirmed):**
```
PgPHPGeneratorPro.exe "<project.pgtp>" -output "<output-folder>" -generate
```
Positional = absolute `.pgtp` path; `-output` = target dir; `-generate` = non-interactive. Nonzero
exit **or any stderr** = failure. The vendor CLI's `-generate` is **not trusted for automation** (it
uses a stricter XML parser than the GUI and hangs on a modal `EInvalidXML` dialog).

---

## 3. Element hierarchy

Parent→child whitelist (used by Tier-2 validation and by the model layer):

```
Project
├── ConnectionOptions / ScriptConnectionOptions   (DB+SSH creds — passed through untouched)
├── DataSources → DataSource                        (one per table/view; PK fields, CRUD SQL)
├── Presentation
│   ├── Groups → Group                              (menu groups, referenced by Page@groupName)
│   └── Pages → Page                                (top-level pages)
│       ├── ColumnPresentations → ColumnPresentation
│       │       children: ViewProperties (→ Format), EditProperties, Lookup
│       ├── Columns → {List,View,Edit,Insert,QuickFilter,FilterBuilder,Print,
│       │       Export,Compare,MultiEdit,DefaultSortedColumns} → Column   (~10 context lists)
│       ├── Details → Detail → Page(nested) + MasterForeignKeyColumnMap → FieldMap  (arbitrary depth)
│       ├── PartitionNavigators → PartitionNavigator → Partition → Values → Value
│       └── EventHandlers (OnXxx… inline PHP/JS text)
├── UserCSS / PdfUserStyles / PrintUserStyles / UserJS
├── ExcludedPaths, DefaultPageProperties, DefaultDataFormats
```

Notes:
- Nested `Detail` pages compile to PHP classes named by the full table-ancestry chain.
- **`Format` is never a direct child of `ColumnPresentation`** — it is always nested inside
  `ViewProperties` (grandchild). Verified 887/887 and 1175/1175 in the two samples. Parsers must use
  `col_el.find("ViewProperties/Format")`.
- The same DB table is frequently embedded as a `Detail` in multiple locations as fully-duplicated
  subtrees (PHPGen has no "shared detail" concept) — motivates the reused-table / table-references
  feature.

**Page "Abilities"** (multi-value enums, stored in `*AbilityMode` attributes):
View (Disabled/Separated Page[default]/Modal), Edit & Insert & Copying (…/Inline/Modal), Multi-edit
(Disabled/Separated/Modal), Delete & Multi-delete (Enabled[default]/Disabled). **The numeric-code →
label mapping is not yet fully known** (derive empirically; now powers editor hover tooltips only —
no longer blocks any feature).

---

## 4. Technology choices

| Concern | Choice |
|---|---|
| Language | Python (system interpreter, editable install) |
| GUI | PySide6 (Qt6), genuine `QDockWidget`/`QMainWindow` docking (LGPLv3) |
| XML (model) | `lxml` — preserves attribute order; fast on 4 MB+ files |
| XML (editor scanner) | lenient regex scanner (`ui/xml_structure.py`), **not** lxml (tolerates mid-edit malformed XML) |
| XML (schema learning) | `defusedxml` — independent second parse |
| DB | `psycopg` v3 (`psycopg[binary]`) via `pg_catalog` |
| Diff | custom domain-aware structural differ (identity-keyed, not line-based) |
| Code editor | custom, built on `QPlainTextEdit` |
| Theme QSS (both themes) | QDarkStyleSheet via `qdarkstyle>=3.2` (MIT) — **both** themes get a real QSS, from `qdarkstyle.dark.palette.DarkPalette` / `qdarkstyle.light.palette.LightPalette` (§7) |

**Licensing:** project is **GPL-3.0**. About box credits BoomslangXML (conceptual prior art),
QCodeEditor (MIT, ported), and QDarkStyleSheet (Colin Duquesnoy, MIT — **both** themes' QSS via the
`qdarkstyle` package, §7). Authors: **Botond Zalai-Ruzsics** and **MDS — Maintenance Data Services**
(https://maint-data.com). Not affiliated with / endorsed by SQL Maestro Group; as-is, no warranty.
(SuperNano credit removed.)

---

## 5. Package / module layout

Actual package (`pgtp_editor/`), reconciling the original design's `ops/`/`external/`/`validate/`
naming with what shipped:

```
pgtp_editor/
├── main.py            # argparse (--debug, optional positional file), QApplication bootstrap
├── debuglog.py        # always-on error log + --debug tracing
├── model/             # lxml-backed model — owns parsing + serialization of the project tree
│   │                  # (other modules also import lxml to work on trees/elements it hands out:
│   │                  # diff/apply.py, generation/from_table.py, ui/main_window.py, ui/caption_scan.py)
│   ├── nodes.py       # PageNode/DetailNode/ColumnNode/EventNode/ChildElement/RepresentationVisibility, identity, classify_event_side
│   ├── parser.py      # load_project(path) / load_project_from_text(text) / _build_project_model(tree)
│   ├── event_handlers.py  # authoritative 40-handler list, language_for_side
│   ├── line_index.py  # node_at_line(project, line) for click-to-tree
│   └── encoding.py
├── diff/              # domain-aware differ (Qt-free)
│   ├── records.py     # Difference dataclass
│   ├── differ.py      # diff_project / compare_block
│   ├── resolve.py     # resolve_path → node | ResolutionError
│   └── apply.py       # apply_differences (write-back)
├── generation/        # vendor CLI + own-generator wiring + create-from-table
│   ├── config.py      # generator_config.json (executable_path, re_phpgen_root)
│   ├── runner.py      # build_generate_command + GeneratorRunner(QProcess)
│   ├── re_runner.py   # subprocess to re_phpgen
│   ├── type_map.py    # pg-type → presentation rules + PAGE_DEFAULTS (parity source of truth)
│   ├── from_table.py  # build_page/build_detail/build_lookup/serialize
│   └── gap_summary.py
├── schema_learning/   # curated-XSD schema source + vendored learning engine + settings index
│   ├── model.py, parser.py (defusedxml), types.py, xsd_gen.py
│   ├── xsd_load.py    # Qt-free expat loader (DTD refused): curated.xsd → CuratedSchema (§11)
│   ├── xsd_verify.py  # Qt-free expat dialect verifier: verify_curated(text) → list[Issue] (§11)
│   ├── storage.py     # schema_model_path / curated_xsd_path / learned_xsd_path (AppData)
│   └── settings_index.py  # enum_hint, sums (additive-value) derivation, known_attributes/known_values, unused_setting_attributes
├── db/                # PostgreSQL introspection & comparison (Qt-free logic)
│   ├── config.py, introspect.py (psycopg lazy), compare.py, rename.py
│   │                  # introspect.py::run_queries is the sole READ seam — read-only, never commits
│   ├── ddl_buffer.py  # build_ddl_text(schema) → (text, [DdlObjectSpan]) — DDL Explorer buffer (§18.1)
│   ├── apply.py       # TARGET DESIGN, does not exist yet — the sole DB **write** seam: apply_ddl(...)
│   │                  # (explicit commit/rollback, ApplyOutcome); the codebase's first write path (§18.5)
│   ├── sandbox.py     # SHIPS, complete for D2/D2a: SandboxCapabilities/probe/ProjectCapabilityStatus/
│   │                  # ProjectTier, build_baseline_sql, quote_ident, is_app_owned/ForeignDatabaseError/
│   │                  # open_sandbox/create_sandbox_database, SandboxSession(apply/applied/reset) +
│   │                  # its SandboxExecutor seam, provision_sandbox, clone_data, install_gate/
│   │                  # install_plpgsql_check, LocalPostgresBackend (§18.5 D2/D2a)
│   ├── ddl_check.py   # TARGET DESIGN, does not exist yet — validation-ladder driver: CheckRequest →
│   │                  # CheckReport{per-tier outcome, [CheckFinding]}; probe_check/apply_and_check/
│   │                  # recheck/check_working_set, body_line_offset/map_lineno (§18.5 D3/D3a)
│   ├── sandbox_query.py # TARGET DESIGN, does not exist yet — ad-hoc sandbox SQL: run_sandbox_query(
│   │                  # session, sql, …) → QueryResult{columns, rows, truncated, …}, classify_statement,
│   │                  # QueryError; takes a SandboxSession, never ConnectionParams (§18.5 D4)
│   ├── ddl_project.py # pure DDL-project paths: object → ddl/*.sql filename (_n overload suffix,
│   │                  # sanitization), ProjectSettings/settings.json shape, DriftMarkers (§18.2)
│   ├── ddl_skeleton.py  # pure CREATE-skeleton generation for brand-new objects (FQ-002, §18.1)
│   ├── bookmark_store.py # pure project-local bookmark persistence (FQ-013, §8): <project>/
│   │                  # .ddlproject/bookmarks.json, relative_key / load_editor_bookmarks /
│   │                  # store_editor_bookmarks / prune_missing_files (the last has NO caller yet);
│   │                  # reads never raise — a raise would land in a gutter click
│   ├── coherence.py   # build_coherence_tree(project, schema) — the merged Database/XML view's
│   │                  # pure data layer over compare.py + analysis/reused_tables.py (§17)
│   ├── schema_index.py  # SchemaIndex — known_schemas/known_tables/known_columns/trigger_for_function;
│   │                  # the injected completion lookup built once per DDL fetch (§18.6)
│   ├── schema_diff.py # diff_schemas(source, target) → SchemaDiffResult; routine/trigger only,
│   │                  # table/column reported via .unsupported (§18.3)
│   ├── migration_gen.py # generate_migration(differences, *, header) → str; pure, deterministic;
│   │                  # raises UnsupportedDifference on table/column (§18.3/§18.5)
│   ├── schema_snapshot.py # dump_schema/load_schema + write_snapshot/read_snapshot — versioned JSON
│   │                  # so a live DB can be diffed against a checked-in file (§18.3); NO CALLER YET
│   └── deploy_bundle.py # §18.3 steps 1–3's pure decision layer: deploy_candidates / deploy_blockers
│                      # (`*!` only) / assemble_deploy_bundle → DeployPlan; NO CALLER YET
├── analysis/
│   └── reused_tables.py   # collect_table_usages → TableUsage/TableReference
├── validation/
│   └── tier2.py       # validate_project → list[ValidationIssue]
├── sql/               # SQL/plpgsql selection formatter core (Qt-free) — §18.4
│   ├── __init__.py    # façade: format_selection / FormatResult / Issue / SQL_KEYWORDS (test-pinned __all__)
│   ├── keywords.py    # SQL_KEYWORDS — the ONE dialect source, shared with ui/code_editor.py's highlighter
│   ├── issues.py      # Issue{message, start, end, start_line/col, end_line/col, fatal} (+ .line alias)
│   ├── tokenizer.py   # Token + tokenize(text) → list[Token] (verbatim, never raises)
│   ├── caret_context.py # resolve_caret_context(text, pos) → CaretContext | None — pure caret parsing
│   │                  # (dotted identifier path / NEW.·OLD. row variable) over that same tokenizer,
│   │                  # for §18.6's schema-aware Ctrl+Space completion; knows nothing of a live schema
│   ├── statements.py  # TARGET DESIGN (§18.5 D4) — split_statements(text) over that same tokenizer:
│   │                  # top-level `;` only, never inside a dollar-quoted body, string or comment
│   └── formatter.py   # format_selection(text, *, indent_unit="    ") → FormatResult; _Reindenter frame walk
├── lint/              # §22 PHP linting — SHIPS (commit 90c6806), consumed by ui/php_file_tab.py (§21);
│   │                  # Qt-free except config.py (QStandardPaths, the generation/config.py precedent)
│   ├── findings.py    # pure: linter stdout/stderr/exit code → LintOutcome/LintStatus + ready-to-append
│   │                  # [Lint] audit_lines — no filesystem, no subprocess, no PySide6
│   ├── runner.py      # the ONE place a linter process spawns (php -l), injectable everywhere it is
│   │                  # used (the db/introspect.py runner= precedent), DEFAULT_TIMEOUT_SECONDS
│   ├── config.py      # lint_executable_path key, stored in generation/config.py's generator_config.json
│   └── service.py     # LintService.lint_text = config + runner + parser; NEVER raises (advisory-only —
│                      # a lint failure must not unwind a save, §22)
├── mcp/               # §23 MCP server — SHIPS (commit 09db778): six read-only tools; headless --mcp
│   │                  # works (main.py), the Tools-menu "Start MCP Server" entry is NOT wired yet.
│   │                  # Importing the package starts nothing — no server, thread, socket or connection
│   ├── tools.py       # ToolRegistry + the six §23 tools: read_project / list_pages / get_node /
│   │                  # diff_projects / list_db_tables / list_db_routines — thin adapter, no new logic
│   ├── serialize.py   # pure data → JSON translation; never renders a password
│   ├── providers.py   # LiveProjectProvider (GUI's open in-memory model) / FileProjectProvider (headless)
│   ├── server.py      # stdio JSON-RPC transport: serve_stdio (--mcp) / start_server_thread (GUI)
│   └── __main__.py    # python -m pgtp_editor.mcp
└── ui/                # all PySide6 widgets (see below)
```

Key `ui/` modules: `main_window.py`, `center_stage.py`, `project_tree.py`, `xml_editor.py`,
`xml_structure.py`, `editor_gutter.py` (the one shared gutter/bookmark/fold implementation, §8),
`code_editor.py`, `php_file_tab.py` (§21's per-file standalone PHP tab — **ships**, hosted in
`CenterStage`'s dynamic key→widget map `_php_file_tabs`; `File ▸ Open PHP File…` now exists),
`event_body.py`, `properties_panel.py`, `find_replace_bar.py` (permanently visible since FQ-016, §8/§15),
`search.py`, `history.py`, `theme.py`, `toolbar_registry.py`, `toolbar_controller.py` (owns the menu-bar
walk and the toolbar's persistence, §7 — **not** `main_window.py`), `customize_toolbar_dialog.py`,
`icon_picker_dialog.py` (FQ-004's searchable Breeze icon picker, §7),
`launcher_dialog.py` (FQ-010's startup launch modal — `LAUNCHER_GROUPS`, `launcherSuppressed`,
`show_launcher(window, settings, …, force=False)`; §7),
`diff_merge_panel.py`, `caption_management_panel.py`,
`caption_scan.py`, *(`caption_find_replace_dialog.py` is **deleted** — FQ-017, §13)*
`connection_setup_dialog.py`, `coherence_panel.py` (§17's merged view), `ddl_editor_panel.py`,
`ddl_buffer_panel.py`, `ddl_object_editor.py` (§18.5's editable single-object tab),
`completion_popup.py` (the `_CompletionPopup` shared by `xml_editor.py` and `ddl_object_editor.py`,
§11/§18.6), `new_trigger_dialog.py` / `new_routine_dialog.py` (FQ-002 creation),
`schema_compare_panel.py` (§18.3's diff viewer — **built, not yet reachable**),
`project_status_model.py` / `project_status_panel.py` (§18.8),
`sandbox_controller.py` (§18.5's sandbox-lifecycle host — **ships**: owns the one `SandboxSession`,
runs every sandbox operation off the GUI thread through its injectable `self._run_async`, and refuses
every destructive operation unless the injected `confirm_destructive` approves; it opens no dialog),
`sql_console_panel.py` / `sql_results_panel.py` (§18.5 D4's Sandbox SQL Console tab and its result grid —
**target design**),
`manual_panel.py`, `about.py`, `icons.py` (the vendored-Breeze icon catalog + recolor/render
pipeline, §7 — the string helpers are Qt-free, only `themed_icon` touches Qt), plus the two off-GUI-thread helpers
`async_task.py` (`run_async(fn, on_result, on_error=None, pool=None)` — the executor behind MainWindow's
injectable `self._run_async`) and `busy.py` (`busy_status(status_bar, message)` context manager,
`format_size`).
`ui/ddl_object_editor.py::DdlObjectEditorPanel` — the editable single-object DDL tab (**specified once,
in §18.5**) — **ships**; it is a distinct tab type from the read-only `ddl_editor_panel.py::EditorPanel`,
which stays read-only permanently. `ui/table_references_panel.py` and `ui/db_check_panel.py` were
**deleted** (2026-08-06, superseded by `coherence_panel.py`, FQ-003 — §15's code note).
(Deleted with the curated-XSD pivot, §11: `schema_learning/sync.py`, `schema_learning/merge.py`,
`ui/annotate_popover.py`, `ui/team_sync_dialog.py`, `ui/merge_conflicts_dialog.py`,
`ui/schema_viewer.py`, `ui/schema_viewer_data.py`.)

**Dependency rule:** `model/` owns parse + serialization of the project tree (other modules may touch
lxml trees/elements it hands out — see the tree comment above). `diff/` is **Qt-free and imports only
`model/`**; consumers sit above it — `ui/main_window.py` imports `diff.apply`/`diff.differ`/
`diff.resolve`, and `mcp/tools.py` imports `diff.differ` (verified in the code; nothing in `diff/`
imports `ui/` or `mcp/`). Pure-logic
modules (`search`, `history`, `caption_scan`, `settings_index`, `xsd_load`, `xsd_verify`, `tier2`,
`analysis/*`, `type_map`, `from_table`, `xml_structure`, `sql/*`) are Qt-free and unit-testable without a
`QApplication`.

**`db/` is Qt-free with exactly one stated exception — `db/config.py`.** An earlier blanket claim that
`db/*` is Qt-free was **factually wrong** (see ledger, §28): `db/config.py` imports `QSettings` **at
module scope** (`from PySide6.QtCore import QSettings`, verified in the code) because the connection
store *is* QSettings, injected from MainWindow. That is `QtCore` only — no widgets, no `QApplication`
needed — and it is deliberate: the alternative is a second secrets/settings mechanism, which §17/§18.5
explicitly reject. Do **not** "fix" it by inventing a parallel store. The genuinely Qt-free `db/` modules
are therefore enumerated rather than assumed:

| `db/` module | Qt-free? | Status |
|---|---|---|
| `introspect.py`, `compare.py`, `rename.py`, `ddl_buffer.py`, `ddl_project.py`, `ddl_skeleton.py`, `bookmark_store.py`, `coherence.py`, `schema_index.py`, `schema_diff.py`, `migration_gen.py`, `schema_snapshot.py`, `deploy_bundle.py` | yes (verified — no `PySide6` import in any of them) | implemented (`schema_snapshot.py`/`deploy_bundle.py` have **no caller yet**, §18.3; `bookmark_store.py` is wired except for `prune_missing_files`, §8) |
| `sandbox.py` | yes (verified — no `PySide6` import) | **implemented in full** for D2/D2a, including `SandboxSession`/`open_sandbox`/`provision_sandbox`/`clone_data`/`install_plpgsql_check` and the `SandboxExecutor` seam. Its UI host is `ui/sandbox_controller.py` (§18.5 D2) |
| `apply.py`, `ddl_check.py`, `sandbox_query.py` | yes — **required** | target design, do not exist yet (§18.5 D3/D3a/D4) |
| `config.py` | **no** — `QtCore.QSettings` at module scope | implemented; the one accepted exception |

The arrow points **ui → core, never core → ui**: `sql/` is the live, test-enforced
precedent — `ui/code_editor.py` imports `SQL_KEYWORDS` from `sql/keywords.py`, never the reverse, and
`tests/sql/test_package_purity.py` pins it (static AST scan for `PySide6`/DB/network/`pgtp_editor.ui`/
`pgtp_editor.db` imports **plus** a fresh-interpreter subprocess check that importing `pgtp_editor.sql`
loads no Qt module at all) — §18.4.

---

## 6. Data model

`model/parser.py::load_project(path) → ProjectModel` uses `lxml.etree.parse()`. Refactored into a thin
path wrapper + `_build_project_model(tree, source_description)` (accepts an already-parsed tree);
`load_project_from_text(text, source_description="<editor>")` parses editor buffer via `io.BytesIO`.
`PgtpParseError(message, line=None)` carries the failing line for XMLSyntaxError.

**Nodes** (`model/nodes.py`), each carries its **identity key**, the full `dict(element.attrib)`
(generic capture — "everything phpgen lets you set" needs no model change), its `sourceline`, and a
retained reference to its live `lxml` element (for write-back):

- `PageNode` — identity `fileName` (fallback `tableName`+`caption`); `attrib`, `sourceline`,
  `element`, child `DetailNode`s, `ColumnNode`s, `EventNode`s.
- `DetailNode` — identity = parent identity + `tableName`; same shape as `PageNode` **including its own
  child `DetailNode`s (recurse)**; carries `sourceline` (outer `<Detail>`), `inner_sourceline` (nested
  `<Page>`), `element` (outer) **and** `inner_page_element` (nested). Merged attributes: nested `<Page>`
  precedence (`merged_attrib.update(inner_page_el.attrib)`).
- `ColumnNode` — identity = parent + `fieldName`; `attrib`, `sourceline`, `element`; four optional
  presentation children as `ChildElement | None`: `format`, `lookup`, `view_properties`,
  `edit_properties`; and `representations: list[RepresentationVisibility]`. Typed property
  `is_calculated` → `attrib.get("isCalculated") == "true"` (lowercase-string boolean convention,
  same as `visible="false"`); consumed by the DB check (§17).
- `EventNode` — identity = parent + handler tag; `{tag_name, side("C"/"S"), text, sourceline, element}`.
  `text` is the handler body as **plain XML-escaped element text** — confirmed, never CDATA; `<`/`&`
  are escaped on write (§2's storage invariant).
- `ChildElement` — `{attrib, sourceline, element}`; does not descend into its own children.
- `RepresentationVisibility` — `{name, visible: bool|None, sourceline: int|None}`.
- `ProjectModel` — `pages`, plus retained `tree: etree._ElementTree` (needed for serialization).

Parser currently parses `Page`, `Detail` (recursive), `ColumnPresentation` (→ columns), `EventHandlers`
(→ events). `DataSources`, `Groups`, `Partitions` are preserved untouched in the tree but not yet
modeled (no consumer). `startup tree is genuinely empty` — no placeholder project.

**Identity keys** (foundational to diff / resolve / rename / coherence):

| Element | Key |
|---|---|
| DataSource | `name` |
| Page (top-level) | `fileName` (fallback `tableName`+`caption`) |
| Detail | parent Page identity + `tableName` (+`caption` for matching) |
| ColumnPresentation | parent identity + `fieldName` |
| Column | parent identity + context + `fieldName` |
| Value | parent `Values` identity + `name` |
| Group | `groupName` |

Duplicate top-level `Page@fileName` is a **hard-blocking** validation rule (it would make identity
ambiguous).

**Event side classification:** authoritative **9 client / 31 server** handler list in
`model/event_handlers.py` as `EVENT_HANDLERS: list[tuple[tag, side]]`; `CLIENT_SIDE_EVENT_NAMES` (9) in
`model/nodes.py`; `classify_event_side(tag) → "C"/"S"`; `language_for_side(side) → "js"|"php"`. This
suffix-normalizing classifier is a **shared contract** — differ and code-editor reuse it; do not
reimplement.

- **Client (9):** OnBeforePageLoad, OnAfterPageLoad, OnInsertFormLoaded, OnEditFormLoaded,
  OnInsertFormEditorValueChanged, OnEditFormEditorValueChanged, OnInsertFormValidate,
  OnEditFormValidate, OnCalculateControlValues.
- **Server (31):** OnBeforePageExecute, OnPreparePage, OnGetCustomPagePermissions,
  OnGetCustomRecordPermissions, OnAddEnvironmentVariables, OnPageLoaded, OnPrepareColumnFilter,
  OnPrepareFilterBuilder, OnGetSelectionFilters, OnGetCustomFormLayout, OnGetCustomColumnGroup,
  OnCustomCompareValues, OnFileUpload, OnGetCustomExportOptions, OnCustomHTMLHeader,
  OnGetCustomTemplate, OnCustomRenderColumn, OnCustomRenderPrintColumn, OnCustomRenderExportColumn,
  OnCustomDrawRow, OnExtendedCustomDrawRow, OnCustomRenderTotals, OnCustomDefaultValues,
  OnCalculateFields, OnGetFieldValue, OnBeforeInsertRecord, OnBeforeUpdateRecord, OnBeforeDeleteRecord,
  OnAfterInsertRecord, OnAfterUpdateRecord, OnAfterDeleteRecord.

---

## 7. App shell

**Layout:** IDE-style docked panels. Left dock is a `QTabWidget` (`self.left_tabs`) hosting **Project
tree**, **Contents** (manual), the **Database/XML Coherence** view (§17 — one tab; it replaces the
former separate "Database Check" and "Table references" tabs, FQ-003) and **DDL Objects** (§18.1)
tabs (the latter two hidden until invoked). Center is a tabbed `CenterStage` (Raw XML
[default-visible working tab], Diff/Merge, Caption Management, Manual, Edit XSD, DDL Explorer —
non-Raw-XML tabs hidden until invoked). Every one of those is a **fixed** tab, created in
`CenterStage.__init__` and addressed by a stored integer index (`raw_xml_tab_index`, `xsd_tab_index`,
`ddl_tab_index`, …), shown/hidden with `setTabVisible`.

> **Stated invariant — append-only creation, tail-only removal.** Runtime-created tabs (the per-object
> DDL object editor tabs, §18.5 — **implemented**; the per-file **PHP file tabs**, §21, keyed by
> `php_tab_key` in `CenterStage._php_file_tabs` — **implemented**; §18.5 D4's single **Sandbox SQL Console** tab, keyed
> `("sandbox-sql",)` in the same key→widget map so re-invoking focuses the existing one rather than
> opening a second; and §18.5's read-only deployment-script preview tab, both still target design) are
> **always appended after the fixed set** (`addTab`, **never** `insertTab`) and removed only from the
> tail, and are addressed by a **key→widget map**, never a remembered index. This is not a stylistic
> preference: those **stored fixed indices are load-bearing in six places**, verified in the code —
> `FindValidateController.active_find_bar`, `active_bookmark_editor`, `MainWindow._save_active_tab` and
> `_on_ddl_navigate_requested` (all four compare `stage.currentIndex()` against `xsd_tab_index` /
> `ddl_tab_index`) — and, by delegation, `active_selection_editor` (FQ-015), which adds **no** index
> comparison of its own precisely because it forwards to `active_bookmark_editor` — plus
> `MainWindow._refresh_editor_menu_affordances` (which compares against `caption_management_tab_index` /
> `manual_tab_index`) and **every** `CenterStage.hide_*`/`show_*` method (`hide_manual`, `hide_edit_xsd`,
> `hide_ddl_explorer`, `set_raw_xml_tab_visible`, `enter_caption_mode`/`leave_caption_mode`) and
> `_on_tab_close_requested`'s index dispatch. A
> single `insertTab` anywhere ahead of the fixed set silently re-points all of them. Because the
> invariant is otherwise implicit, **a regression test is mandatory, not optional**: open two dynamic
> tabs, close the first, and assert every fixed index still resolves to its original widget
> (`widget(raw_xml_tab_index) is raw_xml_tab`, …). As shipped, `_on_tab_close_requested` checks the
> **fixed indices first** (`manual_tab_index` / `xsd_tab_index` / `ddl_tab_index`) and handles dynamic
> tabs in the **else** branch, where the tab is identified by a **key→widget map lookup, never by
> index** (`center_stage.py`). This is behaviorally equivalent to dispatching the dynamic case first —
> a dynamic tab can never occupy a fixed index — and the load-bearing part of the rule is the map
> lookup, not the branch order.
>
> One convenient consequence and one trap. Convenient: `setTabsClosable(True)` is already global, so an
> appended tab gets its ✕ for free. Trap: the `_closable = (manual_tab_index, xsd_tab_index,
> ddl_tab_index)` loop that **strips** the ✕ from non-closable tabs runs **once, in `__init__`** — it
> never sees a runtime tab, which is exactly the behavior wanted, but it means the fixed set's closability
> is decided at construction and must not be recomputed later over a widened tab range.

Bottom is a
persistent **Audit/Problems** panel (`QListWidget`) shared by `[Schema]`, `[Validate]`, `[Find]`, `[PHP]`
lines. Three further prefixes are **reserved against each other in all directions** — no feature may
quietly annex another's prefix, and no fourth SQL-ish prefix may be added:

| Prefix | Owner | Reports | State |
|---|---|---|---|
| `[SQL]` | §18.4 formatter, hosted by §18.5's tab | **Format Selection refusals** — layout only, no DB involved | **wired** (non-clickable, no line role) |
| `[Check]` | §18.5 sandbox validation ladder | **SQL/plpgsql validation findings** (`db/ddl_check.py`) on **two channels** — narrative lines (per-tier outcome, caveats, apply/cancel notices; non-clickable) and **findings** (`[Check] SEVERITY line N: message`, line on `UserRole`, the object's `DdlObjectRef.key` on `UserRole+1`, click-to-navigate). A finding whose line could not be mapped (§18.5 D3's mandatory `None`) is rendered **without** a line and **without** roles — never a guessed line | partly wired: `DdlObjectEditorPanel.check_reported` emits the narrative channel today; the findings channel arrives with `db/ddl_check.py` (§18.5 D3a) |
| `[Bookmark]` | §8's `List All Bookmarks` (FQ-014, 2026-08-07) | **The active editor's bookmarks** as clickable rows — `[Bookmark] line N: <preview>`, **1-based** line on `UserRole`, the active editor's existing click-target discriminator on `UserRole+1`, **and — for a PHP file tab only — that tab's `CenterStage` key on `UserRole+2`**, because the router's `"php"` branch reads the tab key from that slot and a row without it is inert (see §8). Plus a roles-less trailing count row and a roles-less empty-case row; an editor with **no** router branch at all (the read-only DDL Explorer buffer, an FQ-006 draft tab) gets **roles-less, inert** rows. Not SQL-ish, so the no-fourth-SQL-prefix rule below does not block it. **A module constant** (`_BOOKMARK_PREFIX` in `ui/find_controller.py`) beside `_FIND_RESULT_PREFIX`/`_VALIDATION_PREFIX` — never the literal typed inline | **wired** (`FindValidateController.list_all_bookmarks`, 2026-08-07) |
| `[Lint]` | §22 | **PHP** linting only (`php -l` / `phpcs`) | partly wired: `pgtp_editor/lint/` and the tab-side emission ship (§21/§22 — `PhpFileTab.lint_reported` carries already-`[Lint]`-prefixed `LintAuditLine`s); the **three Tools-menu entries now exist** (verified 2026-08-07), so the MainWindow append host is the remaining gap |

**No fourth SQL-ish prefix — and §18.5 D4's SQL console deliberately introduces none.** Ad-hoc query
results, query **errors** and the console's own caveats render **inside the Sandbox SQL Console's own
result panel** (`ui/sql_results_panel.py`), never in the Audit panel: a query error is not a validation
finding, and inventing `[Run]`/`[Query]`/`[Exec]` would breach the reservation above. The Audit panel
keeps exactly the prefixes in this table.

Right dock is the **Properties** panel.

**Dock visibility is bidirectional (BUG-007).** In `_build_view_menu` each of the **three dock actions**
— "Project Tree" (`tree_dock`), "Properties Panel" (`properties_dock`), "Audit/Problems Panel"
(`audit_dock`) — is wired **both ways**: `action.toggled → dock.setVisible` **and**
`dock.visibilityChanged → action.setChecked`. Closing a dock via its title-bar ✕ (or any programmatic
hide/show) therefore keeps the menu checkbox honest. **No recursion guard is needed**: `QAction.toggled`
and `QDockWidget.visibilityChanged` only fire on *actual* state changes, so the pair settles immediately
(the same Qt signal-coalescing the `CenterStage` Manual-tab sync relies on). The remaining non-dock
View-menu checkable keeps its one-way wiring: "Raw XML Panel" drives
`CenterStage.set_raw_xml_tab_visible` (a center tab). (The former "Find table reference" checkable —
one-way wiring to `_toggle_table_references`, a `left_tabs` tab — is gone with FQ-003; the equivalent
`left_tabs`-tab toggle is now Database ▸ **Database/XML Coherence**, §17/§26, and follows the same
one-way pattern.)

**Document state:** `_dirty` + `_set_dirty()` (title gets " *"); editor `textChanged` marks dirty;
load/save/revert clears. **Theme toggles never dirty either document:** a theme change re-applies
character formats in **two stages** (BUG-013), and the `_applying_theme` guard wraps **every** batch of
both — never a single whole-document `rehighlight()`. `XmlEditor.apply_theme_colors` swaps the colors and
(coalescing repeated palette-change events via `_theme_rehighlight_pending` + the parented single-shot
`_theme_kickoff_timer`) schedules `_rehighlight_for_theme`, which (stage 1) `rehighlightBlock`s the
**visible region only**, inside the guard, so what is on screen recolors together with the app chrome;
it then starts `_theme_sweep_timer` (0 ms interval, parented) driving `_theme_sweep_tick`, which (stage 2)
sweeps the **rest of the document from block 0** at `_THEME_SWEEP_BLOCKS_PER_TICK = 400` blocks per
event-loop turn, each turn again wrapped in the guard, so a multi-MB document never freezes the UI. A
fresh theme change while a sweep runs restarts it from block 0 with the new colors. Every batch fires a
spurious `textChanged` with no text actually changed; MainWindow's dirty handlers for **both** the Raw XML
and Edit XSD editors consult `XmlEditor.is_applying_theme()` and no-op, and the editor's own
`textChanged` bookkeeping skips the format-only batches the same way (see the debounced structure rescan,
§8). `.bak` (single, overwritten, `shutil.copy2`) is written before overwriting an
existing file on save — never on Save-As to a new path, never on a failed/no-op write.
`_write_project_text(path)` writes editor `toPlainText()` as UTF-8 with `newline=""` (byte-preserving).
`_current_project_path` is normalized to `str`.

**Per-tab document routing** (curated-XSD pivot, §11): the Edit XSD tab hosts a second document with
its **own dirty state** (tab-title `*` marker, independent of the project's `_dirty`). Find/Replace
gestures route to the **active** center-stage tab's `FindReplaceBar` via
`ui/find_controller.py::FindValidateController.active_find_bar()` (*the dispatcher lives on the
controller, not on `MainWindow` — stale spec reference corrected 2026-08-07*), which dispatches on
`center_stage.currentIndex()` and then on the dynamic-tab accessors: **Edit XSD/Edit AutoXSD tab** →
`stage.xsd_find_replace_bar` (the mode-aware XSD document, curated.xsd or learned.xsd per `_xsd_mode`,
§11); **DDL Explorer tab** → `stage.ddl_editor_panel.find_replace_bar` (the read-only DDL buffer's own
bar, §18.1 — without this branch Ctrl+F on the DDL tab bounced the user back to Raw XML); **the active
DDL object editor tab** (`stage.active_ddl_object_panel()`, §18.5) → its own `panel.find_replace_bar`,
where Replace is **live** rather than inert; **the active PHP file tab**
(`stage.active_php_file_tab()`, §21) → `php_tab.find_replace_bar`; **the active draft fragment tab**
(`stage.active_draft_fragment_tab()`, FQ-006) → `draft.find_replace_bar` (Replace live — a draft is a
scratch buffer with nothing to protect); **any other tab** → reveal Raw XML and return
`stage.find_replace_bar`. Since FQ-016 the bars are **permanently visible** (§8), so these gestures are
**focus** operations rather than reveals — and **`active_find_bar()` is no longer what `Ctrl+F`/`Ctrl+R` go
through**: those two are per-tab `WidgetWithChildrenShortcut` shortcuts installed at each bar
(`install_focus_shortcuts`, §7), which makes them a **no-op on tabs with no bar** (Manual, Diff/Merge). The
dispatcher above — reveal-fallback included — now serves **`F3` Find Next only**, where revealing Raw XML is
the right answer because the user asked to keep searching. *(This closes §29's open question on the reveal.)*

**There are exactly THREE per-tab dispatchers, and the third is deliberately a delegation.**
`active_find_bar()` (above) routes to bars; **`active_bookmark_editor()`** routes to editors and never
switches tabs (§8); **`active_selection_editor()`** (FQ-015) serves the `Select` menu and
`_refresh_editor_menu_affordances` and is implemented as `return self.active_bookmark_editor()` — one line,
on purpose: *"which editor is the user looking at?"* must have **one** answer and must not fork into two
index dispatches that can drift apart. It exists as a distinct **name** because the two express different
**contracts** — bookmarks require the shared gutter API (`ui/editor_gutter.py`), selection requires
`selectAll` plus that family's structural-selection method — so a future non-gutter editor tab may belong in
one and not the other. Never add a fourth dispatcher that re-derives the active editor.

**Ctrl+S routing.** `main_window.py::_save_active_tab()` routes three ways (**implemented**): XSD tab →
`_save_xsd()`; else the active **DDL object editor tab** (`stage.active_ddl_object_panel()`) →
`_save_ddl_object_editor(panel)`, persisting its text through the tab's *injected*
`resolve_save_path` (Save As… when no path is remembered, the checked-out `ddl/*.sql` under §18.2);
else `_save_project()`. **Ctrl+S there is
`Save` only:** it **never executes anything against a database** — pushing DDL to a database is the
separate, explicitly confirmed **Apply** gesture (§18.5), never implied by a save and never automatic.
The read-only DDL Explorer buffer keeps **no** save branch at all — it is DB-synthesized and has no save
path, the deliberate asymmetry against `active_find_bar`, which *does* branch for it. Project-level
state (`.bak`, `_current_project_path`, reparse) is untouched by XSD-tab and DDL-object-tab saves.

- **File ▸ Close** (Ctrl+W): if dirty, 3-way Save/Discard/Cancel (`_confirm_close()`, test-seam
  `confirm=`); clears editor+tree, resets state.
- **File ▸ Revert:** enabled only when `<current>.bak` exists; reloads from `.bak`, keeps real path,
  marks dirty.
**Startup: the launch modal** (FQ-010, settled 2026-08-07). The app presents its four ways in on every
launch instead of dropping the user into an empty Raw XML tab with no guidance. **The GUI no longer opens
a file passed on the command line** (ledger §28): `main()` keeps the optional positional `file` argument,
but only `--mcp` consumes it (as the headless server's default project, §23 `_DefaultPathProvider`); the
GUI branch that called `window.open_project_file(args.file)` is deleted, and the argument's `--help` text
describes only the `--mcp` use. `packaging/linux/pgtp-editor.desktop` drops its now-meaningless `%f`
(it never carried a `MimeType=` line, so the repo never registered a `.pgtp` association; a hand-wired
Windows "Edit with PGTP Editor" verb, which the repo also never created, stops working).

- **Where it lives.** `ui/launcher_dialog.py` — `LauncherDialog(entries, *, groups, suppressed, parent)`
  plus the module-level `show_launcher(window, settings, *, groups=LAUNCHER_GROUPS,
  resolve_entries=None, exec_dialog=None, force=False) -> str | None`, called from `main.py`
  **after `window.show()`** through a `launcher=` seam (so the persisted `windowState` is visibly restored
  first and the modal lands on top of it). `resolve_entries`/`exec_dialog` are the test seams — tests drive
  the dialog's methods and never enter a real modal loop. **It must never be constructed from
  `MainWindow.__init__`:** ~49 test files construct a `MainWindow`, and a modal there would hang every one
  of them (§30 forbids a test reaching an un-patched modal Qt call). The **user**-triggered re-open
  (`File ▸ Show Launcher…`) is a method on the host, like every other dialog.
- **Invariant: `--mcp` must remain structurally unable to reach it.** `main()`'s `if args.mcp: return
  run_mcp_server(args.file)` returns **before any Qt import** — stdio is the JSON-RPC transport and a GUI
  contending for stdout would corrupt every session. The launcher is created below that early return and
  nothing may move it above it.
- **Four groups**, held as the module table `LAUNCHER_GROUPS: tuple[tuple[str, tuple[str, ...]], ...]` —
  `(title, ordered command ids)`, where the ids are **§7's menu-path command ids**
  (`toolbar_registry.command_id_for`). The table holds **no label, no slot and no duplicate of any menu
  wiring**: `resolve_menu_entries(window)` reads `command_id → (menu-path label, QAction)` straight off
  `ToolbarController.collect_menu_commands()`/`menu_commands` (re-walked per call, so a menu built after
  startup is still found), and the picked entry's **own QAction** does the work via `action.trigger()`.
  A group whose every id is missing from the menu bar renders **nothing** rather than an empty frame —
  the launcher must never be able to stop the app from starting. The four groups:
  1. **Open a `.pgtp` for editing** — `File ▸ Open…`. This is the projectless lane: XML tooling, the
     §17 Database/XML Coherence view against the quality database (it needs only a non-empty editor
     buffer plus `Database ▸ Connection Setup…`, which is projectless-only, BUG-024), and generation.
  2. **New Project / Open Project** — `File ▸ New Project…` / `Open Project…`; covers both project
     workflows (sandbox/checkout, §18.2/§18.5; and `.pgtp` diff/merge versioning, §12/§18.3).
  3. **Open other files** — `File ▸ Open PHP File…` (§21).
  4. **Maintenance mode** — maintaining the app itself: the five §11 Schema actions (`Edit XSD`,
     `Edit AutoXSD`, `Verify XSD`, `Export XSD`, `Import XSD` — `Go To XSD` is a menu-less `Ctrl+L`
     action and therefore cannot be presented by path) plus the **§20 re_phpgen** Generation entries
     only: `Locate panGen Runtime…`, `panGen (Generate Own PHP)`, `rePHPgen (Analyze Gap)`,
     `Save reJSON…`. **§19's vendor-generation entries are deliberately OUT** (`Locate PHP Generator
     Executable…`, `Generate PHP…`, `Open Output Folder`) — they are ordinary development, not app
     maintenance. The split lands exactly on the §19/§20 boundary, which is why the grouping is
     defensible rather than arbitrary. **This membership is "for now" (owner's word) and explicitly
     open** — see §29.
- **What a group choice DOES — it triggers that entry's own QAction, and nothing else** (shipped, commit
  `02e47e0`). `show_launcher` runs the dialog through the `exec_dialog` runner, then persists
  `launcherSuppressed` on **every** exit path, then reads `dialog.chosen_command_id`; on a pick it looks
  the id up in the resolved entry map and calls **`action.trigger()` after the modal has already closed**
  (the runner has returned, so the triggered command — a file dialog, a project wizard — opens against an
  unobstructed window), and returns the picked command id to `main()`. Escape / close / an id missing from
  the map all return `None`. **Exactly one action fires per launch**, and the launcher **stores no launch
  mode**: `launcherSuppressed` is the only QSettings key it writes. The four groups are a *presentation of
  menu commands*, not a mode picker.
  > **Planned, NOT shipped — the launch mode is a separate, unimplemented feature** (FQ-011, "Launch mode"
  > below). Nothing in the shipped launcher writes a mode key and **no menu-bar filter exists** to consume
  > one; FQ-011's per-mode menu membership is still undecided, which is why only its mechanism is recorded.
  > If it is ever built, the group the user picked here is the natural input to it — the launcher would then
  > gain a mode write beside the `launcherSuppressed` write, changing nothing else in the flow above.
- **Suppressible, escapable and REVERSIBLE.** A persisted **"Don't show this again"** checkbox stores the
  QSettings bool **`launcherSuppressed`** (`LAUNCHER_SUPPRESSED_SETTINGS_KEY`) alongside `lightTheme` /
  `windowState` / `toolbarIds` / `toolbarIconIds` in `QSettings("MDS","PGTP Editor")`, read with
  `type=bool` because the ini backend hands booleans back as `"true"`/`"false"` strings. The flag is
  persisted on **every** exit path (ticking the box and then picking an entry must persist just as ticking
  it and closing does). Because a persisted tick would otherwise be a one-way door only a settings edit
  could undo, **`File ▸ Show Launcher…`** re-opens it with **`force=True`**, bypassing the flag.
  **Escape / window-close lands in the empty app exactly as today and never quits** — quitting would turn
  the launcher into a gate on running the app at all.
- **No recents in any group.** `File ▸ Open Recent` and its `recentFiles` store are **deleted** (see
  below), so the launcher ships recent-less and knowingly presents *actions*, not a resume list. A
  `recentProjects` store is the right memory for a project-centric app and is a separate, later
  decision that this design does not depend on (`db/ddl_project.py::is_project_dir` already exists as
  its validator).
- **Read it against the restored window state.** `closeEvent`'s `saveGeometry()`/`saveState()` restore
  means the modal lands on top of a fully restored dock/tab/toolbar layout while the app holds **no
  document, no project and no connection** — a *false signal of continuity*. The modal is deliberately
  unmissable for exactly that reason; a non-modal "Start" tab in `CenterStage` was the honest
  alternative and was **rejected by the owner** ("Let's do a modal"), recorded so it is not silently
  re-decided either way.

**`File ▸ Open Recent` and the `recentFiles` store are deleted** (FQ-010; ledger §28 — a documented
capability withdrawn, not a bug fix). Removed surface: `ui/pgtp_document_controller.py`'s
`_RECENT_FILES_KEY = "recentFiles"` / `_RECENT_FILES_MAX`, the `aboutToShow` wiring and initial rebuild,
the `recent_files` reader, `remember_recent_file`, `rebuild_recent_menu`, its two and only two writers
(`open_file`, `save_as`), the File-menu submenu itself, and `tests/ui/test_open_recent.py`. Owner's
framing: recent *files* belonged to the standalone-`.pgtp`-editor era the project has left.

**Undo/redo snapshot history** (`ui/history.py`, Qt-free): `SnapshotHistory(max_len=10)` with
`push/undo/redo/jump_to/entries/current_index`, coalescing identical consecutive text, truncating the
redo tail on a new push. Editor `textChanged` is debounced (~400 ms QTimer) and pushes only on change;
apply is guarded by a `_restoring` flag. **Ctrl+Z**/**Ctrl+Y** single-step, and the **Editor menu bar's
History ▸ Undo/Redo** items **step directly too** (same handlers as the shortcuts); the **separate
History ▸ History… action**
(`_open_history_jump_list`) is what opens the non-modal newest-first `QListWidget` jump popup, where
moving back = undo and forward = redo.

**Theme** (`ui/theme.py`): View ▸ "Light Theme" checkable toggles between **two explicit, symmetric,
platform-independent themes** — there is no third "restore the native/OS style+palette" state.
`light_palette()` and `dark_palette()` are pure functions (build and return a fresh `QPalette`,
mutating nothing) each setting a **complete** role set — every role the app surfaces, including
`Link`/`LinkVisited` (navy on light, light-cyan on dark, so About-box hyperlinks read on both) and an
explicit Disabled color group so greyed-out controls stay legible under Fusion. Light = white/near-white
backgrounds with dark text; dark = dark Window/Base with light text. `apply_theme(app, light: bool)` is
the only function that mutates the running QApplication: it **always** sets the Fusion style (Fusion
honors QPalette fully; many native styles largely ignore it) and applies `light_palette()` when `light`
is true, `dark_palette()` otherwise — and then sets the application stylesheet **unconditionally, for
both themes** (BUG-010 for dark; FQ-005, 2026-08-06, extended it to light):
`app.setStyleSheet(_qdarkstyle_stylesheet(light))`. `_qdarkstyle_stylesheet(light: bool) -> str`
returns `qdarkstyle.load_stylesheet(qt_api="pyside6", palette=LightPalette if light else DarkPalette)`
(`qdarkstyle.light.palette.LightPalette` / `qdarkstyle.dark.palette.DarkPalette`, **both passed
explicitly** — dark no longer relies on qdarkstyle's implicit default), lazily loaded (qdarkstyle warns
if loaded before a `QApplication` exists) and memoized per theme in the module-global
`_qss_cache: dict[bool, str]`. Neither theme is palette-only: Fusion + `dark_palette()` alone rendered
checkable menu indicators outlined near-black on the dark menu background (Fusion derives the indicator
frame from darkened Window/Button roles), and Fusion + `light_palette()` alone rendered as plain stock
Fusion chrome; the maintained stylesheet styles `QMenu::indicator` and every other widget consistently
in **both** themes, at **zero new dependency cost** (`qdarkstyle>=3.2` was already pinned).
`light_palette()`/`dark_palette()` are **unchanged and still applied beneath the QSS** — the QPalette
source stays hand-rolled for both themes (qdarkstyle's palettes are used only to generate QSS, never as
the app's `QPalette`), because palette-reading custom widgets (`XmlEditor.apply_theme_colors` keys off
the palette's Base lightness, §8) and any non-stylesheet-covered rendering must agree with the
stylesheet's look. **Invariant:** there is no "empty stylesheet" state — a light↔dark round-trip always
*replaces* the whole app QSS with the other theme's, so no stale QSS can survive a toggle.
Known side effect, now true in **both** themes: a non-empty app-level QSS makes Qt wrap the requested
style in an internal `QStyleSheetStyle` proxy whose `objectName()` reports `""`, so
`app.style().objectName()` is empty in both modes and **tests must never read the style back** — they
spy on `QApplication.setStyle` (monkeypatched on the class, not the singleton) and assert
`"Fusion"` was requested. Fusion is still genuinely requested and still governs everything the QSS does
not override. `qdarkstyle>=3.2` is a runtime dependency (pyproject + requirements.txt); the About box
credits QDarkStyleSheet (Colin Duquesnoy, MIT).
Persisted as QSettings bool `"lightTheme"` in
`QSettings("MDS","PGTP Editor")`; `MainWindow._restore_theme` applies the persisted theme
**unconditionally at startup for both states** (no startup capture of a default palette/style key
exists). Toolbar icons are re-tinted (`_refresh_toolbar_icons`) on every theme change and on startup
restore. Tests assert palette roles rather than pixels.

**Window-state persistence:** `closeEvent` saves `saveGeometry()`/`saveState()` to QSettings; restored
on construction (default size on a fresh install). Tests use a temp QSettings scope.

**Toolbar:** a `QToolBar` whose customizable universe is **every menu command**, not a hand-maintained
registry (BUG-027, 2026-08-05). `toolbar_registry.py` is reduced to **pure, Qt-free identity rules** —
`normalize_label` (strips `&` mnemonics and a trailing `…`/`...`), `slugify`, `command_id_for(path)`
(`["File","Save As..."] → "file.save-as"`), `menu_path_label(path)` (`"File › Save As"`),
`LEGACY_COMMANDS` (the pre-widening set — **six since FQ-016 retired `find`** — kept because they name the vendored icon files and define the
default), `LEGACY_ID_ALIASES`, `DEFAULT_TOOLBAR_IDS`, `ICON_ID_BY_COMMAND`, plus `valid_ids` and
`resolve_ids`. It holds **no command list**.

- **Ids are derived from the menu path, never hand-assigned.** A newly added menu action becomes
  toolbar-available with zero bookkeeping; the accepted trade-off is that *renaming* a menu label
  changes its id and drops that one button from an already-saved toolbar (self-healing — the user
  re-adds it).
- **Enumeration walks the live menu bar(s).** The walk lives on
  **`ui/toolbar_controller.py::ToolbarController`** (*not* on `MainWindow` — a stale spec reference
  corrected 2026-08-07): `_walk_menu_actions` is a depth-first walk yielding `(id, label, QAction)` for
  every **leaf** command, `all_menu_commands()` returns the ordered `(id, label)` pairs and
  `collect_menu_commands()` refreshes both `_menu_command_pairs` and the `_menu_commands` id→QAction map
  (also re-run at Customize-Toolbar-open time so commands added since startup are offered). **Skipped:**
  separators and submenu placeholder actions (an action that opens a submenu is not itself a command).
  Duplicate ids get a numeric `-2`, `-3` suffix so an id always resolves to exactly one action.
  *(The dynamic **Open Recent** skip rule is gone with the submenu itself, FQ-010 — a rule guarding a
  menu that no longer exists.)*
  > **The walk covers BOTH menu bars** (FQ-016, 2026-08-07). `ToolbarController.build(menu_bar,
  > add_toolbar)` stored a single `self._menu_bar` and rooted the walk at `self._menu_bar.actions()`;
  > with the **Editor menu bar** (below) it takes a **sequence of roots**, walked in order — one
  > mechanism, widened, never a second walk. Everything downstream flows from that single walk:
  > Customize Toolbar's Available list, command ids, FQ-004 icon assignments, and any future
  > shortcut-listing surface. Without the widening every command on the Editor menu bar would be
  > unpinnable and invisible to those features. Ordering is already fine — the container is built
  > before `build()` is called.
  > **Trap, load-bearing:** `QAction.menu()` hands the returned `QMenu`'s ownership to Python, so letting
  > that wrapper go out of scope **destroys the real menu and every action in it** (this crashed startup
  > with *"Internal C++ object (QAction) already deleted"* the moment `_restore_theme` touched the View
  > menu). Every submenu descended into — **and the action that owns it** — is pinned for the window's
  > lifetime in `_menu_keepalive`/`_menu_keepalive_seen`; that list is **never cleared** to re-pin.
- **The toolbar hosts the menus' OWN QActions.** `_apply_toolbar_ids` calls
  `toolbar.addAction(self._menu_commands[command_id])` — not a lookalike wired through a slot table — so
  a button shares the menu item's slot, enabled state, checked state (View-menu dock toggles stay in
  sync) and shortcut for free and can never drift. Corollary: repopulating uses
  `removeAction` in a loop, **never `QToolBar.clear()`**, which in PySide *deletes* the underlying
  QActions and would destroy live menu items.
- **Icons are optional — and, since FQ-004 (shipped, commit `a12b522`), user-assignable.** Only the
  legacy **six** (§7's alias table) carry a *default* icon (`ICON_ID_BY_COMMAND` maps menu-path id →
  `icons.ACTION_ICON_FILES` key); an icon is never a precondition for putting a command on the toolbar,
  and text-beside-icon copes. But **any** toolbar button can be decorated (or re-decorated) from the
  vendored **Breeze catalog**: `ui/icons.py` vendors a curated common-action subset of Breeze SVGs
  under `resources/icons/breeze/` and exposes an enumerable catalog over it — `icon_catalog()` (a lazy
  one-time directory scan cached in `_CATALOG_CACHE`, yielding `(icon_id, filename, human_name)`
  sorted by id; no checked-in manifest to drift), plus `catalog_ids`/`catalog_filename`/
  `search_catalog(query)` (every whitespace term must match id or human name, case-insensitively) and
  `human_name_for` — all Qt-free; only `themed_icon` touches Qt. **Two id spaces meet deliberately:**
  the six *legacy action ids* (`open`, `save`, …) naming the built-in defaults, and *catalog icon
  ids* — simply SVG filename stems (`document-save-as`) — which are what a user assignment stores;
  `load_svg_text`/`themed_icon` accept either, legacy first. Rendering: Breeze SVGs express color via
  `fill:currentColor` plus an embedded `.ColorScheme-Text { color:#232629; }` stylesheet, and QtSvg
  does **not** reliably resolve `currentColor`, so `recolor_svg` substitutes a literal fill for
  **both** before rendering; `themed_icon(action_id, color)` renders 22 px + 44 px (hi-dpi) pixmaps
  tinted to the app palette's window-text color. **Assignments** are `{command_id: catalog_icon_id}`,
  persisted in the sibling QSettings key **`toolbarIconIds`**
  (`toolbar_registry.ICON_ASSIGNMENTS_SETTINGS_KEY`) as sorted `"command_id=icon_id"` strings
  (`serialize_icon_assignments`/`parse_icon_assignments`, tolerant of every shape QSettings hands
  back); `resolve_icon_assignments` prunes on load against the live menu commands and the vendored
  catalog (legacy command ids mapped through `LEGACY_ID_ALIASES` first) — the same self-healing
  `resolve_ids` applies to the id list. `icon_id_for(command_id, assignments)` is the single lookup:
  the user's assignment wins, else the legacy default, else `None` (icon-less). **Absence of an
  assignment means "use the default"** — which is what keeps a pre-FQ-004 saved toolbar behaving
  exactly as before. `_set_action_icon` also
  calls `setIconVisibleInMenu(False)`, so decorating a shared action for the toolbar does not change how
  the menu looks. `_refresh_toolbar_icons` re-tints on every theme change.
- **Back-compat.** Saved toolbars from before the widening hold legacy ids; `resolve_ids` maps them
  through `LEGACY_ID_ALIASES` before `valid_ids` filters, so an existing user's toolbar survives instead
  of silently emptying to the default. `DEFAULT_TOOLBAR_IDS` is those aliases in legacy order, and
  `ICON_ID_BY_COMMAND` is the inverse map — so an alias also names which vendored SVG a default button
  carries. **The alias table was a hard dependency of the Editor-menu-bar move** (FQ-016): three of the
  aliases pointed at ids the move changes, and an alias left stale would have shipped a **default toolbar
  button that is empty and iconless on a fresh install**. Shipped outcome (`c327c9d`):

  | Legacy id | Menu-path id before FQ-016 | Shipped after the Editor-menu-bar move |
  |---|---|---|
  | `open` | `file.open` | unchanged |
  | `save` | `file.save` | unchanged |
  | `undo` | `edit.undo` | **`history.undo`** |
  | `redo` | `edit.redo` | **`history.redo`** |
  | `find` | `edit.find` | **RETIRED** — removed from `LEGACY_COMMANDS`, `LEGACY_ID_ALIASES` *and* `icons.ACTION_ICON_FILES`. Find has no menu home at all (it is a permanent bar, not a menu action); owner ruling: *"Find unpinnable is fine."* **`edit-find.svg` stays in the vendored Breeze catalog** (`resources/icons/breeze/`), so it remains freely **user-assignable** to any button through FQ-004's picker — only its *default-icon* binding is gone |
  | `validate` | `tools.validate-project` | **`parsing.validate-project`** |
  | `generate` | `generation.generate-php` | unchanged |

  Consequently **`LEGACY_COMMANDS` and `DEFAULT_TOOLBAR_IDS` are SIX, not seven** (`open`, `save`, `undo`,
  `redo`, `validate`, `generate`), and `icons.ACTION_ICON_FILES` holds six entries — the default toolbar a
  fresh install shows is six buttons. Anywhere this spec says "the legacy seven", read *six since FQ-016*.

  Non-pinned ids that also moved or vanished, and therefore silently drop off **user-saved** toolbars:
  `edit.auto-parse-xml` (→ `parsing.auto-parse-xml`), `edit.history` (→ `history.history`), and
  `edit.select-enclosing-block` / `edit.select-parent-block` (→ **`select.select-enclosing-block`** /
  **`select.select-parent-block`** since FQ-015 built the menu; `Select All` is additionally **new** as
  `select.select-all`, so the walk now yields three pinnable Select commands. None of the three is
  alias-pinned — they were never default toolbar buttons — so a user who had pinned either block command
  before FQ-016 re-adds it under the new id). **`tools.lint-current-file` does NOT move** — lint stayed whole on Tools (§26; §29's open item
  is closed that way). `resolve_ids` already prunes unknown ids, so nothing crashes — those buttons simply
  vanish and the user re-adds them. **Ids derive from label *and* menu path, so *moving* or *renaming* a
  command breaks saved ids while merely hiding one (`setVisible(False)`) breaks nothing** — the distinction
  the launch-mode filter below would depend on.

**Customize Toolbar** dialog (two lists + Add/Remove/Up/Down + **Choose Icon…**, FQ-004) writes an
ordered id list, persisted in
QSettings key `toolbarIds`, plus the icon-assignment map (`toolbarIconIds`, applied and saved together
on OK via `_apply_and_save_toolbar_ids(ids, icon_assignments)`). The **Available list shows all menu
commands in menu order, always**, each
labelled by its menu path (`File › Save As`) so the long list stays scannable; commands already on the
toolbar are shown **disabled** (not removed). Each **On-Toolbar row shows the icon that button will
carry** (assigned, or the command's built-in default), previewed through the same `themed_icon`
pipeline tinted to the palette window-text color so it matches the real button under either theme.
**Choose Icon…** — or double-clicking the row — opens
`ui/icon_picker_dialog.py::IconPickerDialog`: a searchable icon-mode `QListWidget` grid over the
Breeze catalog (`icons.search_catalog`), with an always-present leading **"Default" cell** (sentinel
`DEFAULT_CHOICE = None`) that clears the assignment back to the command's built-in icon or to none;
double-clicking a cell accepts the dialog. Test seams `selected_ids()`/`set_ids()`, FQ-004's
`icon_assignments()`/`set_icon_assignments()`/`assign_icon()` (which stands in for the picker), and
the picker's own `set_filter`/`visible_icon_ids`/`select_icon`/`chosen_icon_id`; never `.exec()` in
tests.

**The Editor menu bar — a second, FIXED menu bar directly above the central pane** (FQ-016, settled
2026-08-07). Owner's distinction, verbatim and not to be re-decided: *"that's not a toolbar, that's a
menubar. Toolbar is just a collection of favourite commands."* **Fixed** = the app decides its contents;
it is not user-composable, and it is not the customizable toolbar above.

- **Container** (shipped, commit `c327c9d`). `self.editor_menu_bar = QMenuBar()` with
  **`setNativeMenuBar(False)`** (it must never be a candidate for macOS absorption, or the Editor commands
  would silently merge into the window bar), placed in an **anonymous `QWidget` container** — held only as
  `centralWidget()`, never as a named attribute — carrying a `QVBoxLayout` with **zero content margins and
  zero spacing** and exactly two children in order: `[editor_menu_bar, center_stage]`. That container is
  what `setCentralWidget` receives. A `QMainWindow`'s own menu-bar/toolbar *areas* span the full window
  width including above the docks, so a bar that must sit **strictly** above the central pane cannot use
  them. **`window.center_stage` keeps pointing at the `CenterStage`**, which is what the ~534 test
  references address; **`window.centralWidget()` now returns the container**, so the one test that asserted
  `centralWidget() is center_stage` was the only one that had to change.
- **Platform split, stated so it is not discovered later:** macOS absorbs the *window* menu bar into the
  system menu bar while a **child** `QMenuBar` renders inline, so on macOS the two bars will not look
  like siblings. This is structural, not styling.
- **It holds *editing* commands, not strictly per-tab ones** — a deliberate concept name, because
  `History…` opens the **project snapshot** navigator and `Undo`/`Redo` are project-snapshot actions
  except on the Edit XSD and DDL object tabs, where §27's pinned carve-out routes `Ctrl+Z`/`Ctrl+Y` to
  that editor's own native stack. Calling the bar "per-tab" would be false. (Whether `History…` belongs
  here at all is an open item, §29 — the recorded recommendation is yes, with this naming.)
- **What SHIPS is FOUR menus, built by `_build_editor_menu_bar()` in this order** (three from FQ-016,
  commit `c327c9d`; `Select` added by FQ-015, commit `9146524`): **History** (`History…`, `Undo`, `Redo`,
  in that order — `_build_history_menu`), **Select** (`Select All`, separator, `Select Enclosing Block`,
  `Select Parent Block` — `_build_select_menu`), **Parsing** (`Auto Parse XML`, separator,
  `Validate Project` — `_build_parsing_menu`) and **Bookmarks** (built by
  `FindValidateController.build_bookmarks_menu(self.editor_menu_bar)`, which now takes the bar to build on
  so the same method can host the menu on either bar — **five** actions since FQ-014 landed
  `List All Bookmarks` after `Clear All Bookmarks`). Enumerated in §26. The commented **insertion point**
  that stood between History and Parsing is gone, consumed by the real menu; no such placeholder comment
  remains anywhere on this bar.
  > **The one-commit gap, recorded because a body statement was briefly false:** FQ-016's dissolution of
  > Edit was described as *re-homing* `Select Enclosing Block` / `Select Parent Block` onto **Select**, but
  > it **deleted** those two QActions and `Select` did not exist yet, so for the commits between `c327c9d`
  > and `9146524` **`Ctrl+Shift+A` had no host at all** and `Ctrl+Shift+B` survived only through
  > `CodeEditor.keyPressEvent` (Code Editor dialog / DDL object / PHP tabs). FQ-015 **closed it** — and note
  > the actions were **rebuilt, not relocated**: the two build-time `triggered.connect(self.center_stage
  > .xml_editor…)` lines the bug report named no longer existed by then. Ledger §28.
- **Per-menu membership is gated by the ACTIVE TAB KIND, never by mode** (`Parsing` was the original
  candidate; `Select` is the first actual user — see the shipped gating below). The word *"mode"*
  already carries four meanings in this project (the launch mode below, Caption Mode §13, `_xsd_mode`
  §11, `DdlObjectRef.kind`) — **use "active tab kind"** in spec and code. This is **capability** gating
  (the same predicate §26 already uses for `Check DDL Object`, *"disabled unless a DDL object editor tab
  is active, kept in sync on `center_stage.currentChanged`"*), so it is independent of the intent-based
  launch-mode filter below; if both exist they **compose**, and neither may be built as the other.
- **Build every member of every Editor-bar menu once and gate with `setVisible`; never create/destroy per
  tab.**
  `collect_menu_commands()` is re-walked whenever Customize Toolbar opens, so a menu whose actions are
  *destroyed* per tab kind would make the Available list vary with the active tab and leave
  `_menu_commands` holding dead QActions. **`MainWindow._refresh_editor_menu_affordances()`** is the single
  entry point, connected to `center_stage.currentChanged` in `__init__` and shaped exactly like
  `_refresh_sandbox_affordances` (*"Everything here binds VISIBILITY, never enabled-state"*).
- **Shipped gating — `_refresh_editor_menu_affordances` does exactly TWO things** (case 1 from `c327c9d`,
  case 2 from `9146524`), both binding **visibility, never enabled-state**:
  1. It hides **the whole bar widget** — `editor_menu_bar.setVisible(index not in
     (stage.caption_management_tab_index, stage.manual_tab_index))` — on the two tabs where all four menus
     are meaningless (Caption Management, Manual). **Hiding the bar WIDGET, not its actions, is
     load-bearing:** a toolbar button *is* the menu's own QAction (§7 above), so hiding the actions would
     blink any pinned button out of the toolbar as the user changes tabs, while hiding the container leaves
     every QAction enabled and every pinned button intact.
  2. It hides **`Select ▸ Select Parent Block`** on tabs whose active editor has no parent-block concept:
     `self._select_parent_action.setVisible(hasattr(editor, "select_parent_block"))`, where `editor` is
     `self._find_ui.active_selection_editor()`. **This is the seam's FIRST REAL CAPABILITY GATE** — the
     kind the bullets below said the seam was waiting for — and it asks the *editor* rather than
     enumerating tab indices, so a new editor tab kind is classified for free. Unlike case 1 it hides an
     **action**, so a user who pinned that command to the toolbar sees the button come and go with the tab:
     accepted deliberately, because the alternative is a toolbar button that no-ops.
- **`Parsing`'s per-tab membership gating is still deliberately NOT exercised** — a considered decision, not
  an omission. Both members are ungated: `Validate Project` is one of the **six default toolbar
  buttons**, so gating it per tab would make a *default* button appear and disappear as tabs change (the
  same QAction-sharing consequence as above), and both members are genuinely applicable whenever a document
  is open regardless of which tab is in front — gating them would be *intent*, not capability. §18.5 D3a's
  check members (predicate: *"a DDL object editor tab is active"*) remain the next candidate, but they are
  no longer the seam's first user.
- **The Edit menu is DISSOLVED, not emptied** (ledger §28). After the moves and deletions it has no
  members left: `Undo`/`Redo`/`History…` → **History**; `Cut`/`Copy`/`Paste`/`Delete` and
  `Preferences...` → **deleted stubs** (five of the seven `_add_stub_action` "Not yet implemented" stubs
  die here, leaving only the two tree stubs `Compare Selected` / `Copy Selected to...` in violation of
  the app's own absent-not-disabled rule; `MainWindow._add_stub_action` itself survives as an unused
  helper); the five Find/Replace entries → the permanent bar (§8/§15);
  the two selection commands → **Select**, where FQ-015 **rebuilt** them (they were deleted with the menu,
  not carried over — see the one-commit gap above, §8/FQ-015); `Auto Parse XML` → **Parsing**.
- **Deleting the five Find/Replace QActions takes their shortcuts with them** — see §27 for the per-key
  rulings (`Ctrl+F`/`Ctrl+R` become focus actions; **`F3` survives as a window-level shortcut with no
  menu entry**; `Ctrl+Shift+F` and `Ctrl+Alt+Return` are deleted).
- **`FindValidateController.set_find_actions` / `set_find_actions_enabled` are DELETED** (shipped;
  neither symbol exists in `pgtp_editor/` any more). That seam existed **solely** so Caption Mode could
  disable the Edit-menu `Find…`/`Replace…` QActions and let the caption `QShortcut`s win. With the
  QActions gone there is nothing left to disable — but note **why** the seam is not merely relocated:
  > **FQ-017 did NOT delete the caption shortcuts.** It *converted* them from window-scoped, mode-gated
  > `MainWindow` shortcuts opening the deleted modal into **panel-scoped
  > `WidgetWithChildrenShortcut` `QShortcut`s on `CaptionManagementPanel`** (`Ctrl+F` →
  > `focus_find_replace_bar`, `Ctrl+R` → `focus_replace_field`; §13, commit `02e47e0`). They are still
  > live.
  **The Qt hazard this creates, and the structural answer to it** (FQ-016, `c327c9d`): a single
  **window-level** `Ctrl+F` would be **ambiguous** against those panel-scoped ones. Qt does **not** prefer
  the narrower context — two enabled shortcuts matching the same key press are ambiguous and **neither
  fires** (only `activatedAmbiguously` is emitted). A window-level `Ctrl+F` would therefore have broken
  caption find/replace, i.e. re-created the exact conflict `set_find_actions_enabled` existed to arbitrate.
  So `Ctrl+F`/`Ctrl+R` are hosted **per editor tab** instead, by
  **`find_replace_bar.install_focus_shortcuts(host, bar)`** — a module-level helper that creates the two
  `WidgetWithChildrenShortcut` `QShortcut`s on the widget owning *both* the editor and the bar (so they fire
  with the caret in the **editor**, not only once the bar has focus), wires them to
  `bar.focus_find`/`bar.focus_replace`, and returns the pair so the caller can retain/inspect them. It is
  called at **all six bar construction sites**: `center_stage.py` ×3 (the FQ-006 **draft fragment tab**
  class on itself, the **Raw XML** tab container, the **Edit XSD** tab container), plus
  `ddl_editor_panel.py` (DDL Explorer), `ddl_object_editor.py` (the §18.5 object tab) and `php_file_tab.py`
  (§21) — each on itself. **The arbitration is
  now structural rather than gated: exactly one `Ctrl+F` match is live for any focus location**, which is
  what lets `set_find_actions*` go — not the (untrue) disappearance of the caption shortcuts. `F3` is
  deliberately *not* in that helper: it is one window-level action (§27), because nothing competes for it.
- **`Ctrl+F` is consequently a NO-OP on tabs with no bar** (Manual, Diff/Merge) instead of yanking the user
  to Raw XML — the per-tab hosting simply has no shortcut there. This **closes §29's open item** *"does
  `active_find_bar()`'s Raw-XML reveal survive a pure focus gesture?"* in the direction §29 recommended.
  `FindValidateController.active_find_bar()`'s `self._shell.reveal_raw_xml()` fallback **still exists and is
  still correct**, but its only remaining caller is `find_next` — i.e. the reveal survives on **F3's**
  fallback path only, where the user has explicitly asked to search on.

**Launch mode — PLANNED, NOT IMPLEMENTED: the mechanism only, and its per-mode menu membership is
UNDECIDED** (FQ-011, 2026-08-07). **Nothing of this ships**: no mode key is written by the launcher or
anything else, and no menu-bar filter exists — the shipped launcher only triggers the picked QAction
(above). *Would-be* design: the launcher group the user picks is persisted as a **launch mode** in the same
`QSettings("MDS","PGTP Editor")` scope as `lightTheme`/`windowState`/`toolbarIds`/`toolbarIconIds`, and
consumed by a **single** `_refresh_*_affordances`-style entry point called on mode change — never by
ad-hoc `setVisible` calls scattered through the `_build_*_menu` methods. What is settled is only the
mechanism and its consequences:

- **It binds VISIBILITY, never enabled-state**, following the one existing precedent verbatim
  (`MainWindow._refresh_sandbox_affordances`: *"Everything here binds VISIBILITY, never enabled-state
  (§18.5 carve-out 2: with no live session the control is ABSENT, not greyed out)"*). Greying out would
  introduce a **third** posture into an app that has deliberately kept two.
- **This is *intent*-based hiding and is therefore a deliberate departure from the app's existing
  *capability*-based rule** — recorded, not softened. Everywhere else the app hides what it genuinely
  cannot do (`has_session`, `_configured_sandbox_params()`, §26's *absent, not disabled* statements).
  `Generate` genuinely works in a project; hiding it because the user picked "project mode" is the app
  deciding the user did not mean it. The counter-proposal — fix the app's "Not yet implemented" stubs
  instead (seven when FQ-011 was proposed; **two** since FQ-016 deleted the five Edit-menu ones, leaving
  only the project-tree pair), a cheaper win against the same complaint — was **weighed and overridden by the owner**,
  which is their call. The two are not mutually exclusive.
- **An escape hatch is required**: a mode is persisted and the launcher itself may be suppressed, so
  there must be an always-reachable way to change or clear the mode **from inside** the app. Its shape
  and location are undecided (§29). Recorded recommendation: make the filter a default *emphasis* (a
  persistent "showing: <mode> — show all commands" affordance) rather than a lock. **`Help ▸ Manual`
  (F1) and whatever surface reveals/clears the mode must never be filtered out of any mode**, or the app
  can hide the only documentation explaining why commands are missing.
- **Three code interactions the implementer must not trip over**, all verified:
  1. **A hidden action is still enumerated by `_walk_menu_actions`**, so Customize Toolbar's Available
     list would offer commands the current mode hides. Whether the Available list filters by mode is
     undecided (§29).
  2. **The toolbar hosts the menus' OWN QActions**, so hiding a menu action **empties any pinned toolbar
     button** built from it. This is the single most likely source of surprise.
  3. **`Generate PHP...` is one of the six default toolbar buttons** (`LEGACY_ID_ALIASES`
     `generate → generation.generate-php` → `DEFAULT_TOOLBAR_IDS` → its vendored `run-build` SVG) **and
     it is the owner's own example of a command to hide in project mode.** So mode-filtering `Generate`
     empties a default button, by default, on a fresh install, in the app's primary mode.
- **Scope: the menu bar only.** Whether a mode affects docks, left-dock tabs or the toolbar is to be
  widened only on an explicit decision.
- **UNDECIDED — the per-mode membership itself.** Nobody has enumerated which commands each of the four
  modes shows; **only `Generate` in project mode has been named.** That enumeration is the bulk of the
  design and needs the owner, command by command or by a stated rule. **No table is invented here** —
  see §29. Independently: this filter is visibility-only and must stay independent of any command
  *relocation* between menus, since a move breaks saved toolbar ids and hiding does not.

---

## 8. Raw XML editor

`ui/xml_editor.py::XmlEditor(QPlainTextEdit)` with syntax highlighting, folding, a multi-zone gutter,
auto-indent/auto-close, structural selection, tag navigation, bookmarks, and event-code styling.

**Lenient scanner** (`ui/xml_structure.py`, Qt-free, never raises):
`@dataclass TagSpan{name, open_start, open_end, close_end|None, depth, self_closing}`;
`scan(text)→list[TagSpan]`; primitives `find_enclosing_open_tag`, `nesting_depth_at`,
`enclosing_tag_span(text,pos)` / `enclosing_tag_span_from_spans(spans,pos)`, `parent_tag_span`,
`matching_tag_target`, `parent_tag_target`, `closing_tag_start` (public).

**Highlighting** (`XmlSyntaxHighlighter`): four categories (delimiters/names, attribute names, values,
text), applied by the unchanged module regexes `_TAG_OPEN_RE` / `_TAG_CLOSE_RE` / `_ATTR_NAME_RE` /
`_ATTR_VALUE_RE`; **quoted-value state is propagated across blocks via Qt block state, and that state is
tag-aware** (BUG-016).

- **Four block states**, module-level constants in `ui/xml_editor.py`: `STATE_NORMAL = 0` (text content,
  outside any tag), `STATE_IN_UNCLOSED_STRING = 1` (inside a double-quoted attribute value),
  `STATE_IN_TAG = 2` (inside `<…>`, not inside a value), `STATE_IN_SINGLE_QUOTED = 3` (inside a
  single-quoted attribute value). `highlightBlock` coerces any other `previousBlockState()` (including
  Qt's `-1`) to `STATE_NORMAL`.
- The end state is computed by the method `XmlSyntaxHighlighter._end_state(text, state)`, which iterates
  **only the state-changing characters** found by the module regex
  `_STATE_CHARS_RE = re.compile(r"""[<>"']""")` — one C-speed pass yields a handful of matches per line
  instead of a Python loop over every character.
- **A quote only opens a value INSIDE a tag.** In text content — where `.pgtp` keeps its PHP
  event-handler bodies, full of quotes and apostrophes — quotes are ordinary characters and never change
  the propagated state. (Inline `"…"` pairs in text content are still string-colored by
  `_ATTR_VALUE_RE`; only the *propagated state* is tag-aware.)
- **Resync rule (the rule that bounds the cascade):** while inside a quoted value, a raw `<` resyncs the
  state to `STATE_IN_TAG`, because `<` cannot appear inside a well-formed attribute value (it must be
  `&lt;`). Without it an unterminated quote inside a tag still flips every following block's state to
  EOF; with it the next tag snaps the state back and the cascade stops after a block or two. Documented
  trade-off: a raw `<` typed inside an attribute value ends that value's highlighting early — acceptable,
  since such a document is invalid XML and it self-corrects once the quote is closed or the `<` escaped.
- A value continued from the previous block is coloured up to `_continued_string_end(text, quote)` — past
  the closing quote, at a raw `<` (the same resync), or end of line — and the four formatting regexes are
  then applied **from that offset on**.
- `_end_state` and `_continued_string_end` are **methods on `XmlSyntaxHighlighter`, deliberately** (not
  module functions), so `debuglog.py`'s `("ui.xml_editor", "XmlSyntaxHighlighter.")` qualname-prefix
  flood exclusion keeps covering them.
- Superseded: the old rule was `_has_unterminated_quote(text, start)` = *odd count of `"` on the line*.
  Parity never re-synchronised, so one parity-flipping `"` flipped every following block's state in turn
  and Qt cascaded a re-highlight **to the end of the document** on every such keystroke (measured: 5,972
  `highlightBlock` calls / 45 ms on a 6,002-block file). That helper no longer exists.

**Debounced structure rescan** (BUG-015). The structure rescan (`_rescan_structure`) and the
code-region rebuild (`_refresh_code_region_selections`) are each **O(document)** — a full
`toPlainText()` copy plus a whole-document pass — and are **no longer connected to `textChanged`
directly**. Both run behind a **parented single-shot** `self._rescan_timer = QTimer(self)` with
`_RESCAN_DEBOUNCE_MS = 250` (same debounce shape as MainWindow's ~400 ms snapshot-history timer, §7, and
the 400 ms auto-parse timer, §9). Never `QTimer.singleShot` — an unparented timer fires on an
already-deleted editor (BUG-014).

- `textChanged` → `_on_text_changed_schedule_rescan()`, which absorbs the `_applying_theme` skip
  (format-only theme sweeps change no characters, so spans/code-regions cannot differ — nothing is even
  scheduled) and otherwise (re)starts the timer.
- `_rescan_now()` executes the work in order: structure → code regions → matching-tag highlight →
  `self._gutter.update()` (fold glyphs are derived from `_spans`).
- Measured on a 1 MB / 21,002-block document: plain typing **216.1 → 2.0 ms per character**.
- **`_update_matching_tag_highlight` (on `cursorPositionChanged`) must NOT rescan when it finds `_spans`
  stale** — it **suppresses** the matching-tag highlight (clears `_matching_tag_selections`, refreshes,
  returns) and lets `_rescan_now` re-invoke it a few hundred ms later. This is load-bearing: typing moves
  the caret, so a rescan-if-stale on the cursor path would have run the full scan per keystroke and
  defeated the debounce entirely. It is also the correct rendering: while stale, the cached spans' offsets
  refer to the **pre-edit** text, so highlighting from them would paint a visibly wrong range — worse
  than none.
- **Two consumers must see exact structure and therefore bypass the debounce:** `setPlainText` is
  overridden to call `_rescan_now()` **synchronously** (a document *swap* — file load, revert, rename
  write-through — whose callers read spans/fold regions/code regions immediately), and `_toggle_fold` is
  overridden to call `_flush_pending_rescan()` (runs `_rescan_now()` only if the timer is active) before
  deferring to the shared mixin. **Design constraint / non-obvious trap:** the flush deliberately does
  **not** live in `_foldable_region_starting_at` — the gutter's `paintEvent` calls that hook for every
  visible block, so rescanning there would fire on every repaint (i.e. every keystroke) and silently undo
  the whole debounce.

**Folding:** driven by the (debounced) `scan()` results cached in `_spans`; one foldable region per
multi-line non-self-closing span; `QTextBlock.setVisible()`; `_fold_state: dict[int,bool]`; reset on
`setPlainText`. Folding only hides rendering — the character stream is intact, so copy/cut of a folded
block yields the **full** underlying text (a hard requirement; tested with nested folds).

**Gutter (`_EditorGutter`, `ui/editor_gutter.py`)** — three zones left to right: a 12px **bookmark strip**
(`_BOOKMARK_STRIP_WIDTH = 12`), a 16px **fold-glyph zone** (`_FOLD_GLYPH_WIDTH = 16`), then the
right-aligned **line-number area**. `mousePressEvent` routes by `event.position().x()`: a click in the
bookmark strip toggles that line's bookmark (`self._editor.toggle_bookmark(block.blockNumber())`), a
click in the fold zone toggles that line's fold (`self._editor._toggle_fold(block)`); a **single** click
in the line-number zone is a no-op.

**Implemented (commit `828fe02`, exactly as designed 2026-08-01) — double-click on the line number also
toggles a bookmark** (a second, larger click target for the same toggle, alongside the existing 12px
strip): the block-lookup loop formerly duplicated inside `mousePressEvent` is extracted into the
shared helper `_EditorGutter._block_at_y(click_y) -> QTextBlock | None`; the `mouseDoubleClickEvent`
handler checks `event.position().x() >= _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH` (i.e. the
line-number zone), and if so calls `toggle_bookmark` on `_block_at_y(event.position().y())` and repaints
the gutter. Purely additive: the single-click no-op in the line-number zone is unchanged.

**Shared gutter / bookmark / fold base (implemented — `ui/editor_gutter.py`, reused by every
`CodeEditor` incl. the DDL editor, §18.1):** the gutter (`_EditorGutter`), the bookmark set +
`toggle_bookmark`/`bookmarked_lines`/`next_bookmark`/`prev_bookmark`/`clear_bookmarks` (all
**block-number based**, hence generic), the **fold-state** machinery (`_fold_state`, `_toggle_fold`,
`_is_line_hidden_by_other_collapsed_fold`), the gutter width/geometry plumbing and the theme-aware
gutter colors (`_GUTTER_COLORS_DARK`/`_GUTTER_COLORS_LIGHT`, `_apply_gutter_theme_colors`) are **generic
to any `QPlainTextEdit`** and live in the **new module `ui/editor_gutter.py`** — a separate module
rather than a base inside `xml_editor.py`, so `code_editor.py` need not import from the ~1900-line
XML-specific module.

- The shared piece is a **mixin**, `GutterBookmarkFoldMixin`, not a base class: hosts declare it
  **before** `QPlainTextEdit` (`class XmlEditor(GutterBookmarkFoldMixin, QPlainTextEdit)`, likewise
  `CodeEditor`) so the mixin's `setPlainText`/`resizeEvent` sit ahead of Qt's in the MRO.
- The mixin deliberately has **no `__init__`**; each host calls `_init_gutter_bookmarks_folding()`
  explicitly from its own `__init__` after `super().__init__(parent)`. This is why no existing
  constructor ordering had to be inverted.
- Only the **foldable-region provider is pluggable**: the mixin calls
  `_foldable_region_starting_at(block)` → `(first_contained_block, last_contained_block)` (0-based) or
  `None`; the mixin's default folds nothing. `XmlEditor` overrides it with the **XML-span** provider
  (over `_spans`/`TagSpan`); `CodeEditor` overrides it with a lookup into regions installed from outside
  via `set_fold_regions(regions)` (see §8 "Code editor" below and §18.1).
- **Bookmark changes are published through a MODULE-LEVEL observer registry** (FQ-013/FQ-014, shipped
  2026-08-07) — `add_bookmark_observer(cb)` / `remove_bookmark_observer(cb)` plus the three reason
  constants `BOOKMARKS_TOGGLED` / `BOOKMARKS_CLEARED` / `BOOKMARKS_RESET`, and the restore entry point
  `restore_bookmarks(lines)`. `_notify_bookmark_observers(self, reason)` fires from `setPlainText`
  (`RESET`, **after** the text is in so an observer reads the final `blockCount()`), `toggle_bookmark`
  (`TOGGLED`) and `clear_bookmarks` (`CLEARED`). The mixin publishes `(editor, reason)` and
  **interprets nothing** — it stays Qt-widget-level and never learns about projects, stores or the Audit
  panel; the subscribers decide what a reason means. **Module-level rather than per-editor** because most
  editors are created inside tabs long after their host window, so one subscription at construction
  covers every editor that will ever exist (a per-editor signal would need a hook on every future tab).
  Observers are held **weakly** (`weakref.WeakMethod` for bound methods, so a subscribed window is never
  kept alive), duplicate registrations are ignored, and an observer that raises `RuntimeError` (its C++
  object destroyed) is **dropped** rather than raised through — a gutter click must never surface a
  stale-observer traceback. Other exception types propagate: they are bugs, and hiding them would make
  persistence fail silently.
- `ui/xml_editor.py` **re-exports** `_EditorGutter`, `_BOOKMARK_STRIP_WIDTH` and `_FOLD_GLYPH_WIDTH` so
  pre-existing importers (and tests) keep working unchanged, and re-declares **none** of the nine moved
  methods.

There is exactly **one** `class _EditorGutter` and **one** gutter `paintEvent` in the package — never a
second, near-duplicate gutter.

**Auto-indent / auto-close:** Enter inherits leading whitespace, +2 spaces when just after an opening
tag's `>`. Typing `<`→`<>`, `"`/`'` after `=`→ paired quotes, `>` completing an opening tag inserts
`</name>`; type-through when the next char is the auto-inserted one.

**Extra-selections infrastructure** — a single `_refresh_extra_selections()` is the only caller of
`setExtraSelections`, concatenating (bottom→top): `_current_line_selections`, `_matching_tag_selections`,
`_error_line_selection`. Each feature sets its own named list then calls the refresher.

**Public navigation API** (consumed by Properties, captions, DB check, table references, diff):
`navigate_to_line(line)` (1-based; center + one-shot full-line highlight), `line_text(line)`,
`select_range_on_line(line, start, end)`, `highlight_error_line(line)` (one-shot). `highlight_error_line`
is reimplemented in terms of `navigate_to_line`.

**Structural selection — the `Select` menu** (menu actions, not editor-owned QShortcuts; moved from the
dissolved Edit menu onto the **Editor menu bar** as its own three-item `Select` menu, FQ-015 —
**SHIPPED** 2026-08-07, commit `9146524`, `MainWindow._build_select_menu`, fourth menu **between History
and Parsing**):

| Entry | Chord | Acts on | Notes |
|---|---|---|---|
| `Select All` | Ctrl+A | the active editor's own `selectAll()` (`_select_all_in_active_editor`) | **new menu entry for behaviour that already worked** |
| — separator — | | | |
| `Select Enclosing Block` | Ctrl+Shift+B | `XmlEditor.select_enclosing_block` **or** `CodeEditor.select_enclosing_brackets`, whichever the editor has (`_select_enclosing_block`) | one command, two structural meanings |
| `Select Parent Block` | Ctrl+Shift+A | `XmlEditor.select_parent_block` only (`_select_parent_block`) | **XML-only; HIDDEN on `CodeEditor` tabs** |

- **Select All** is a **new menu entry for behaviour that already works.** Nothing in the app binds or
  steals Ctrl+A (the only near chord is `Ctrl+Shift+A`), so `QPlainTextEdit`'s built-in select-all was
  always live — including in the read-only buffers, since `setReadOnly(True)` keeps Qt's text-selectable
  interaction flag. The gap was **discoverability**, so the menu entry *is* the whole feature. It is
  deliberately **NOT gated in Caption Mode** (unlike Find/Replace, which that mode owns): selecting text
  mutates nothing. Verified by test on both editor families, on the read-only DDL Explorer buffer, and on
  Raw XML while Caption Mode holds it read-only — the §29 "verify, don't assume" item is closed.
  **Consequence of Qt's `ShortcutOverride`:** a *focused* text widget keeps handling Ctrl+A itself, so this
  action's own shortcut only fires when focus is elsewhere (e.g. the structure tree), where it then acts on
  the active editor — which is also why the action cannot steal Ctrl+A from a `QLineEdit`.
- **Select Enclosing Block — ONE command, two structural meanings, dispatched BY CAPABILITY.**
  On `XmlEditor` (Raw XML / Edit XSD / draft fragment tabs) it selects `text[open_start:close_end]`
  (uniform; self-closing = open span), no-op outside all elements. On `CodeEditor` (DDL Explorer, DDL
  object tabs, PHP tabs) it selects the innermost balanced `()[]{}` span — SQL and PHP have no XML tags to
  enclose, so the bracket pair is that family's equivalent and is what Ctrl+Shift+B always did there. The
  dispatch is `getattr(editor, "select_enclosing_block", None) or getattr(editor,
  "select_enclosing_brackets", None)`: **never assume one method name**, because the two are genuinely
  different operations, not two implementations of one interface.
- **Select Parent Block** is stateless, re-derived from `cursor.selectionStart()`; walks up one level per
  press; no-op at top level. It is **XML-only**, and on a `CodeEditor` tab the entry is **HIDDEN, not
  greyed** by `_refresh_editor_menu_affordances` (§7 — the affordance seam's **first real capability
  gate**, keyed on `hasattr(editor, "select_parent_block")`, matching the app's two-posture present/absent
  rule). Because Qt keeps a shortcut live only while its action is both enabled **and** visible, hiding the
  entry also **kills Ctrl+Shift+A there** — proven by a test that presses the chord on a PHP tab and
  asserts nothing was selected. `_select_parent_block` re-checks the capability as a **second belt** for
  programmatic and toolbar triggers, which bypass visibility.
- Both block commands build the selection **caret-at-start** (anchor at end, position at start) then
  `ensureCursorVisible()`. Selections are built purely from character offsets — never from visual
  hit-testing — so they work with folded content.
- **No shortcut changes.** All three chords keep exactly their current keys; none is new to the app
  (Ctrl+A is the platform default the widgets already implemented). `EXPECTED_HOST_SURFACE` needed no edit
  either — FQ-016 had pre-seeded the six `_select_*` names.

> **The bug this move fixed — the two selection actions were never covered by the app's own
> per-tab-dispatch rule.** They had been wired
> `select_enclosing_action.triggered.connect(self.center_stage.xml_editor.select_enclosing_block)` (and the
> same for `select_parent_block`) — bound to the *widget* at menu-build time — so Ctrl+Shift+B /
> Ctrl+Shift+A pressed on a PHP tab, a DDL object tab or a draft tab acted on the **Raw XML** document.
> (Historical precision: by the time FQ-015 ran, FQ-016 had already deleted those two `connect` lines with
> the Edit menu, so the actions were **rebuilt** rather than repaired — see §7's one-commit gap and the
> ledger.) The fix is **`FindValidateController.active_selection_editor()`**, which resolves the target at
> **trigger** time and **delegates to `active_bookmark_editor()`** so the question *"which editor is the
> user looking at?"* has exactly **one** answer and cannot fork into two dispatches that drift. It exists
> as a separate *name* because the two are different **contracts** — bookmarks need the shared gutter API
> (`ui/editor_gutter.py`), selection needs `selectAll` plus that family's structural method — so a future
> non-gutter editor tab may belong in one and not the other. A test asserts the two dispatches agree on
> every tab, and another asserts no selection action is connected to a bound widget method at build time.
>
> **The duplicate Ctrl+Shift+B handler: measured, then KEPT** (closing §29's open item).
> `CodeEditor.keyPressEvent` also handles the chord. With the QAction present, **Qt's shortcut map consumes
> the key before it reaches the focused `CodeEditor`**, so exactly one call occurs — verified by a test that
> counts calls, not assumed. The editor-side handler is retained on purpose: it is the **only** host for the
> chord in the menu-less `CodeEditorDialog`, and it remains the reliable path under the offscreen test
> platform where QShortcut activation is not guaranteed. Both paths now land on the **same** editor and
> `select_enclosing_brackets` is idempotent, so even a double delivery would be harmless.

**Matching-tag highlight & navigation:** on `cursorPositionChanged`, both the opening and closing tag
of the enclosing element are highlighted (self-closing → none), using the revision-guarded `_spans`
cache — which is refreshed by the **debounced** rescan above, so while the cache is stale the highlight
is **suppressed rather than recomputed** (see "Debounced structure rescan"). **Ctrl+click** jumps
between matching open/close tags; **Alt+click**
jumps to the parent element's open tag (both move caret + scroll, no selection; `event.accept()`
suppresses Qt's Alt-drag). Other modifier combos fall through.

**Right-click context menu:** `contextMenuEvent` first moves the caret to the actually-clicked
document position (`_prepare_context_menu_at(doc_pos)`) before building the menu, so
position-dependent entries (e.g. "Go To XSD", §11) reflect the clicked location rather than a
stale caret. **Selection right-click ▸ "Find"** prepends to the standard context menu when a selection
exists; emits `find_selected_text(str)` → MainWindow reveals Raw XML + prefills the Find bar.
**Line-wrap** toggle lives in the editor's right-click context menu (checkable), not the View menu.

**Bookmarks** (per-document; **session-only unless a project is open** — see "Bookmark persistence"
below; carried by **every** editor that mixes in
`GutterBookmarkFoldMixin` — `XmlEditor` *and* every `CodeEditor`, see "Gutter on every code editor"
below): `self._bookmarks: set[int]` (block numbers), reset on
`setPlainText`; `toggle_bookmark(block_number)`, `bookmarked_lines()` (sorted ascending),
`next_bookmark(from_line)`/`prev_bookmark(from_line)` (nearest strictly-after/-before, wrap-around,
`None` when empty), `clear_bookmarks()`, plus cursor-line wrappers `toggle_bookmark_at_cursor()` and
`goto_next_bookmark()`/`goto_prev_bookmark()` (center the target line). Rendered by
`_EditorGutter._draw_bookmark_tag` as an accent-colored (`_bookmark_color()`, theme-aware) rounded tag
in the gutter's bookmark strip — toggled by a single click in the strip, and (implemented — see above)
by a double-click in the line-number zone. **Bookmarks menu**
(`ui/find_controller.py::FindValidateController.build_bookmarks_menu`; **hosted on the Editor menu bar**
since FQ-016 — §7/§26 — having previously been a top-level window menu between Tools and Generation):
Toggle Bookmark (Ctrl+F2 → `toggle_bookmark_at_cursor`), Next Bookmark (F2 → `goto_next_bookmark`),
Previous Bookmark (Shift+F2 → `goto_prev_bookmark`), separator, Clear All Bookmarks (no shortcut →
`clear_bookmarks`), **List All Bookmarks** (no shortcut → `FindValidateController.list_all_bookmarks` —
FQ-014, below; **shipped**, last on the menu, and the fifth member of the retained
`_bookmark_actions` tuple Caption Mode gates). **The menu follows the active
editor tab** (settled 2026-08-01): `build_bookmarks_menu` captures **no** editor at build time; each
action is connected to a lambda that resolves its target at **trigger** time via
`FindValidateController.active_bookmark_editor()` (*on the controller, not `MainWindow` — stale spec
reference corrected 2026-08-07*) — Edit XSD tab → `stage.xsd_editor`, DDL Explorer tab →
`stage.ddl_editor_panel.editor`, an active DDL object editor tab (`stage.active_ddl_object_panel()`,
§18.5) → `panel.editor`, an active PHP file tab (`stage.active_php_file_tab()`, §21) → `php_tab.editor`,
an active draft fragment tab (`stage.active_draft_fragment_tab()`, FQ-006) → `draft.editor`, any other
tab → `stage.xml_editor`.
This mirrors `active_find_bar`'s per-tab dispatch with **one deliberate difference: it does NOT reveal /
switch to the Raw XML tab** as a fallback side effect (`active_find_bar` does; this must not), because
toggling a bookmark may never yank the user to a different tab; a non-editor tab
simply falls back to the Raw XML editor. The dispatch is the *only* thing needed, because
`GutterBookmarkFoldMixin` puts the identical bookmark API on every editor. The **"Edit code…"
`CodeEditorDialog` is a separate dialog, not a center-stage tab**, so the main window's Bookmarks menu does
not reach it — its gutter bookmark strip stays mouse-only. Out-of-range block numbers
are ignored defensively. **Persistence exists in project mode only** (below) and there are still **no
names** — a bookmark is a bare line, never a labelled entry.

**Bookmark persistence — project mode only** (FQ-013, **shipped** 2026-08-07 — pure store
`db/bookmark_store.py`, host wiring in `ui/main_window.py`; ledger §28). Bookmarks were
session-only *and* document-scoped, and the second half was the sharper loss: the fold-state lifecycle
**resets `self._bookmarks` to an empty set on every `setPlainText`** (`ui/editor_gutter.py`,
*"Bookmarks share the fold-state lifecycle: a new document starts with no bookmarks"*), so reopening a
project, reverting, an XSD mode switch, re-checking-out a DDL object or simply restarting lost every
bookmark in every editor.

- **Two tiers, gated on whether a §18.2 project is open.** *"Project mode"* here means **a project is
  open** — the capability fact **`DdlProjectController.folder`** (read as `self._ddl_project_ui.folder`,
  `None` when projectless) — **not** FQ-011's persisted launcher mode. This deliberately keeps the gate on
  the right side of the app's capability-not-intent rule and gives the feature **no dependency on
  FQ-010/FQ-011**. With a project open, bookmarks survive document reload **and** app restart. With **no**
  project open, behaviour is **bit-for-bit the status quo** — session-only, wiped by `setPlainText`, **no
  debounce started and no file written**; every host method short-circuits on the `None` folder
  (`_bookmark_store_target` returns `None`), so the projectless path costs one attribute read. That path
  must not regress or acquire a store; it is the status quo by explicit decision.
- **The store is a sibling file inside the project's already-private directory**, not a new key in
  `ProjectSettings`: `<project>/.ddlproject/bookmarks.json`, beside `settings.json`, inside the
  `.ddlproject/` directory `db/ddl_project.py::save_settings` already registers with the idempotent
  `_ensure_gitignored(project_dir, ".ddlproject/")`. Bookmarks are **personal, not shared**;
  `ProjectSettings` is the project's shared configuration (connections, deploy manifest, git settings)
  read and written by several controllers, and mixing them would make every bookmark toggle dirty the
  file the deploy pipeline depends on. **On-disk shape** (`indent=2`, `sort_keys=True`, so it stays
  human-diffable): `{"version": 1, "files": {"ddl/public.foo.sql": [3, 41], …}}`, values **0-based block
  numbers** exactly as the mixin holds them, sorted and de-duplicated. An **empty set removes its key**
  rather than storing `[]` (an editor with no bookmarks is indistinguishable from one never bookmarked, so
  recording it would accumulate a key per file ever opened); when the last key goes the file is truncated
  to an empty `files` map if it exists and is **not created** if it does not. `BOOKMARKS_VERSION` is cheap
  insurance — a reader that meets an unknown version reports *"no bookmarks"* instead of guessing at
  foreign data. **Reads never raise**, because a raise here would land in a gutter click: a missing,
  unreadable or malformed file, a wrong top-level type, an unknown version or a garbage entry all degrade
  to "no bookmarks" for the affected scope. Writes are **idempotent** (the same mapping twice is
  byte-identical) and call `_ensure_gitignored(project_dir, ".ddlproject/")` themselves, so the store is
  covered even if bookmarks are written before the project's first settings save. `Qt`-free and DB-free,
  like `db/ddl_project.py`.
- **Keys are project-relative, POSIX-separated.** Absolute paths do not survive a project being moved,
  cloned, or opened from another mount (the project is explicitly expected to live on an sshfs-mounted
  share, §18.3), and the project must be portable between the Windows and Linux checkouts — the same
  discipline `routine_ddl_paths` already follows.
- **Stale line numbers: restore leniently, drop silently.** Restore every stored line still within the
  document's block count and discard the out-of-range ones on load, matching the mixin's existing
  defensive posture. **No content-anchoring in v1** — storing the line's text and re-finding it carries
  real duplicate-match/moved-block ambiguity and is its own decision, deferred rather than smuggled in.
- **Which editors persist — exactly three, and only while a project is open** (`MainWindow._bookmark_file_path`
  is the single map from editor to keyed file; `None` means session-only):

  | Editor | Keyed by | Persists? |
  |---|---|---|
  | **Raw XML** (`stage.xml_editor`) | the open document's path (`self._doc_ui.project_path`) — in project mode the working-copy `.pgtp` inside the project | **yes**, when that path is inside the project folder |
  | **DDL object tabs** (§18.5, `stage.ddl_object_panels()`) | `panel.save_path` (the object's `ddl/*.sql`) | **yes** |
  | **PHP file tabs** (§21, `stage.php_file_tabs()`) | `tab.path` | **yes** |
  | **Edit XSD / Edit AutoXSD** (`stage.xsd_editor`) | — | **no — session-only** |
  | **Read-only DDL Explorer buffer** (`stage.ddl_editor_panel.editor`) | — | no — session-only |
  | **FQ-006 draft fragment tabs** | — | no — session-only |
  | **`Edit code…` `CodeEditorDialog`** | — | no — session-only |

  **The XSD editors cannot persist, and that is structural, not an omission** (corrected 2026-08-07;
  ledger §28 — an earlier statement claimed they did). Their schema files live in the **app-level schema
  storage directory** (`XsdController`'s `schema_storage_dir`), **not under any project**, so
  `bookmark_store.relative_key` returns `None` for them; the store has no root to key them against. The
  same rule covers **any** document opened from outside the project folder, including the Raw XML editor
  with a stray `.pgtp` — `relative_key` answers that on its own, so the host offers the path
  unconditionally and lets the store refuse it. **No identity is invented for the identity-less editors**
  (no absolute-path fallback, no synthetic id): that is the deliberate boundary of v1.
- **Save timing: a 400 ms debounce plus two synchronous flushes.** A user-chosen change
  (`BOOKMARKS_TOGGLED`, `BOOKMARKS_CLEARED`) calls `_schedule_bookmark_write` → single-shot
  `QTimer(_BOOKMARK_WRITE_DEBOUNCE_MS = 400)` → `_flush_bookmark_writes`; the flush is additionally
  **synchronous** on a **project transition** (`_on_bookmark_project_changed`) and in **`closeEvent`**, so
  the debounce can never be the reason a bookmark is lost. **Never inside `toggle_bookmark`** — a gutter
  single click must not do disk I/O. The pending map is keyed `(folder, path) → lines` with all three
  **resolved at change time**, so a pending write survives its tab being closed and the project being
  closed underneath it, and the flush itself touches **no widgets**. `closeEvent` also calls
  `remove_bookmark_observer`, so a closed window never answers a later editor's bookmark change.
  A `BOOKMARKS_RESET` is a **restore, never a write** — writing the just-emptied set back would erase what
  is stored.
- **Restore timing: at the document load, plus a project-open sweep.** The one moment the set is wiped is
  the mixin's `setPlainText`, so `BOOKMARKS_RESET` is the single restore hook — and it is the same moment
  for a **reopened project, a revert, an XSD-mode switch, a DDL re-checkout and an app restart**, so one
  hook covers all of them. `_restore_editor_bookmarks` calls `load_editor_bookmarks(folder, path,
  editor.blockCount())` and `editor.restore_bookmarks(lines)` only when non-empty, and does **not** rewrite
  the store, so a temporarily shortened document keeps its out-of-range lines on disk for when it grows
  back. Because a project can be opened **after** the `.pgtp` (no load event follows), opening a project
  additionally **sweeps** the already-loaded editors — Raw XML, every DDL object panel, every PHP tab.
- **`prune_missing_files(project_dir)` exists in the store but has NO caller yet** (drift noted
  2026-08-07): it drops keys whose file no longer exists in the project, the posture `resolve_ids` takes
  toward unknown toolbar ids (§7), and is safe on any project. Whether/where the host calls it (project
  open is the obvious trigger) is still the open item in §29 — until it is wired, a deleted DDL object
  leaves a dead key behind, which is harmless but unbounded.
- Rejected: persisting unconditionally in the app-level QSettings scope — with no project there is no
  defined root to key against, so it would have to key absolute paths and would accumulate entries for
  arbitrary files forever, with no owner and no cleanup rule.

**`List All Bookmarks` → clickable `[Bookmark]` Audit rows** (FQ-014, **shipped** 2026-08-07 —
`FindValidateController.list_all_bookmarks` / `clear_bookmark_results` / `_bookmark_audit_route`; ledger §28).
Bookmarks were reachable only **sequentially** (F2 / Shift+F2, wrap-around) with the gutter tags as the
only overview — and those show the scrolled viewport only, so in a several-thousand-line buffer the user
could not see how many bookmarks existed, what was at them, or jump to the fourth one directly.

- **Scope: the ACTIVE editor only**, not every open editor. It is the consistent sibling of every other
  bookmark command (all of which resolve exactly one document via `active_bookmark_editor()`), and a
  cross-editor list would need click routes the Audit router does not have: `_on_audit_item_clicked`
  routes on the single `UserRole+1` value (`"xsd"` → `_xsd_ui.reveal_line`; `LINT_AUDIT_TARGET` →
  `_php_tabs.navigate_to` with the tab key on `UserRole+2`; a **tuple** → `_navigate_to_ddl_object`;
  **anything else → Raw XML**), so a wrong-document fallback is the default failure — exactly what the
  `[Check]` branch's comment warns against. A modal dialog's bookmarks cannot be navigated to at all once
  it closes.
- **Payload: whatever the click router already understands for that editor — which for a PHP tab is BOTH
  halves, not one** (corrected 2026-08-07; ledger §28 — an earlier statement said *"no `UserRole+2`"*, and
  a PHP row obeying it would have been inert). Reusing the router's own discriminator means reusing its
  whole contract per branch. `_bookmark_audit_route(editor)` returns `(target, label, extra)`, keyed on
  editor **identity** (not on the current tab, so it cannot disagree with `active_bookmark_editor()`):

  | Active editor | `UserRole` | `UserRole+1` (target) | `UserRole+2` (extra) | label (empty case / status) |
  |---|---|---|---|---|
  | Raw XML | 1-based line | `"raw"` | — | `Raw XML` |
  | Edit XSD / AutoXSD | 1-based line | `"xsd"` | **omitted deliberately** — a mode-less `"xsd"` row targets whatever the tab already shows (`_xsd_ui.reveal_line(line, None)`), which is correct for a bookmark in the open schema | `Edit XSD` |
  | DDL object tab (§18.5) | 1-based line | `panel.ref.key` (**a tuple**) | — | `panel.ref.qualified` |
  | **PHP file tab (§21)** | 1-based line | `LINT_AUDIT_TARGET` (`"php"`) | **REQUIRED — the tab's `CenterStage` key**, which is exactly what `_php_tabs.navigate_to(key, line)` is given | `tab.tab_title()` |
  | DDL Explorer buffer (read-only) | — | `_NO_AUDIT_ROUTE` → **no roles set** | — | `the DDL Explorer` |
  | FQ-006 draft fragment tab | — | `_NO_AUDIT_ROUTE` → **no roles set** | — | `the draft fragment` |

  `MainWindow._on_audit_item_clicked`'s `"php"` branch reads the tab key off `UserRole + 2` (the same slot
  the `"xsd"` branch uses for its mode, read only on that branch, so the two never collide) — so a
  `[Bookmark]` row in a PHP tab that omitted it would be a row that cannot navigate. The implementation
  documents this at the code site. **Where the active editor has no click route at all**, its rows are
  emitted **roles-less and inert** rather than carrying a line that would navigate the Raw XML document
  instead — the same never-navigate-somewhere-wrong rule §7's `[Check]` unmapped-line case states, and a
  test clicks such a row to prove it does not yank the user to Raw XML. No new routes are added, and no
  per-row editor label is emitted (the one label appears in the empty-case row and the status message).
  Line numbers on the rows are **1-based**: the gutter's block numbers are 0-based, and every Audit
  consumer (`navigate_to_line`, `reveal_line`) plus `[Find]`'s rows and the gutter's printed numbers are
  1-based, so `list_all_bookmarks` converts with `block_number + 1`.
- **Its own `[Bookmark] ` prefix, as a module constant** beside `_FIND_RESULT_PREFIX` /
  `_VALIDATION_PREFIX` (§7's prefix table). **Not** a reuse of `[Find]`: the two would clear each other,
  and `[Find]`'s `"raw"|"xsd"` vocabulary cannot carry a DDL-object or PHP-tab payload under one prefix —
  precisely the overloading the prefix reservation exists to prevent. §7 forbids a fourth *SQL-ish*
  prefix; `[Bookmark]` is not SQL-ish.
- **Row grammar: Find All's, verbatim** — `f"{_BOOKMARK_PREFIX}line {line}: {preview}"`; a
  blank/whitespace-only line renders as just `line N`.
- **Clears its own rows first**, via a `startswith(_BOOKMARK_PREFIX)` bottom-up sweep in the same shape
  as `clear_find_results`/`clear_validation_results`. Repeat invocations replace, never stack.
- **Trailing roles-less count row** (`[Bookmark] 7 bookmark(s)`), matching `_finish_find_all`'s summary
  (*"no line data → clicking is a no-op"*), and a **roles-less empty-case row** (e.g. `[Bookmark] no
  bookmarks in <editor>`) plus a status message — Find All always emits its summary even at zero, so a
  command that produced literally nothing would read as broken.
- **No shortcut**, matching `Clear All Bookmarks` — and placed **immediately after it**, last on the
  Bookmarks menu: this produces a report, and F2/Shift+F2 already own
  stepping. **Reveals the Audit dock** through the existing injected `_show_audit_dock` callback (the same
  way `CoherenceController` receives it) rather than reaching for `audit_dock` from a controller —
  without it the command is a silent no-op whenever the dock is hidden.
- **A snapshot, not a live view**: toggling a bookmark afterwards does not re-sync the rows. The lane
  therefore subscribes `FindValidateController._on_editor_bookmarks_changed` to the mixin's observer
  registry (above) and acts on **`BOOKMARKS_RESET` only** — a `setPlainText` wiped that editor's set, so
  any listing now describes bookmarks that no longer exist and `clear_bookmark_results()` removes it.
  `BOOKMARKS_TOGGLED`/`BOOKMARKS_CLEARED` are deliberately **not** swept: re-syncing on every gutter click
  would turn the snapshot into a live view. The sweep clears the rows **wholesale rather than per editor**,
  because only one editor's listing can be present at a time (every listing starts by clearing the previous
  one). This stays necessary **even with persistence**, because projectless editors still wipe on reload and
  the restore is in-range-only. The gutter mixin knows nothing about the Audit panel — it publishes
  `(editor, reason)` and the row-owning controller interprets it; the mixin is **never** handed a reference
  to the panel.
- Rejected: a dedicated bookmarks list panel / left-dock tab (the Audit dock already *is* the app's
  list-of-locations surface, with a working click router, three precedents and a clear-scope convention).

**Every editor's Find/Replace bar is PERMANENTLY VISIBLE** (FQ-016, settled 2026-08-07; full mechanics in
§15, shortcuts in §27). This is a shared editor behaviour, not a per-tab one: all six `FindReplaceBar`
construction sites — `center_stage.py` ×3 (Raw XML, Edit XSD, the FQ-006 draft fragment tab),
`ddl_editor_panel.py`, `php_file_tab.py`, `ddl_object_editor.py` — get a bar that is shown in its
**expanded** form (both the find row and the replace row) from construction and never hides. Owner's
words: *"That section must be always visible… not the results, just the fields. no new feature,"* and the
accepted cost: *"this takes up a bit of space, but more natural to use."* `Ctrl+F`/`Ctrl+R` become
**focus** gestures and `Escape` **returns focus to the editor** instead of hiding the bar. The rejected
alternative — keep the bar hideable and merely default it to visible, which would have preserved
Escape-to-hide and kept `edit.find` pinnable — was **explicitly double-clarified away by the owner**;
its one honest argument was screen space, which the owner weighed and accepted.

**Bookmarks menu is disabled during Caption Mode** (settled 2026-08-01; **implemented** — status
corrected 2026-08-07): `build_bookmarks_menu` retains the menu as `FindValidateController._bookmarks_menu`
and its **five** actions as the `_bookmark_actions` tuple, and
`FindValidateController.set_bookmarks_enabled(bool)` — called from `MainWindow._enter_caption_mode`
(`False`) and `_close_caption_mode` (`True`) — sets the enabled state on the menu **and every child action
together**. Both halves are needed: disabling only the `QMenu` grays out the menu-bar entry but does not
disable the actions' keyboard shortcuts in Qt (the precedent was
`_editor_find_action`/`_editor_replace_action`, disabled individually rather than via their menu — those
two actions no longer exist since FQ-016 dissolved the Edit menu, but the Qt rule they demonstrated is
unchanged and is what this gating depends on). **Since FQ-016 the Bookmarks menu lives on the Editor menu
bar**, whose whole *widget* is hidden on the Caption Management tab (§26, resolved 2026-08-07) — that hides
the bar, never the actions, so this action-level gating is still what actually kills the shortcuts.
**Gutter bookmark toggling (single-click strip and the double-click on the line number) is
explicitly NOT gated by Caption Mode** and stays usable — bookmarks are a UI overlay independent of the
read-only editing state; only the Bookmarks menu (and therefore its shortcuts) is gated.

**Read-only key classification — `XmlEditor._is_text_modifying_key(event)`.** In read-only mode (Caption
Mode, §13) `keyPressEvent` emits `read_only_edit_attempted` and **swallows** the key when this predicate is
true, which is how the non-modal "XML is read-only" hint is raised. Its order is load-bearing and is
evaluated exactly as follows:

1. `event.matches(QKeySequence.StandardKey.Paste)` → **True**. Ctrl+V really *is* an edit attempt and keeps
   its hint; this is why the test comes **first**.
2. Backspace / Delete / Return / Enter → **True**.
3. **A Ctrl or Meta modifier → False: a chord is a COMMAND, never typing.**
4. Otherwise: a non-empty, printable `event.text()`.

**Defect fixed with FQ-015 (`9146524`).** Step 3 did not exist, so classification fell through to the
printable-text test — and `event.text()` for a Ctrl+letter chord is the bare letter on some platforms and
under `QTest.keyClick` (it is the control character `"\x01"` on Windows/Linux). A **read-only `XmlEditor`
therefore swallowed Ctrl+A** (and every other Ctrl+letter command) while flashing the read-only hint,
which would have made `Select All` fail in Caption Mode — the exact combination §29 flagged as
"verify, don't assume". A test covers Ctrl+A in a Caption-Mode-read-only Raw XML editor.

**Event-handler code styling & editing:** event-body line ranges (`event_body_line_ranges(text)`) get a
distinct background + monospace and work read-only (Caption Mode). A gutter marker / "Edit code…"
context action opens `CodeEditorDialog` (below) with the body and `language_for_side(side)`; on save,
pure `replace_event_body(text, start_line, new_code)` swaps inner content preserving tags/indentation.

**Code editor** (`ui/code_editor.py`): `CodeEditor(GutterBookmarkFoldMixin, QPlainTextEdit, language)` — monospace,
per-language `_CodeHighlighter` (JS / PHP / SQL keyword sets, strings, `//`+`#` line comments, `/* */`,
numbers), auto-close + selection-wrap for `()[]{}`/quotes, **Ctrl+Shift+B** bracket-select via pure
`enclosing_bracket_span(text,pos)`. The **`language="sql"`** mode (added for the DDL Explorer, §18.1)
uses `_SQL_KEYWORDS` (stored lowercase; matching is **case-insensitive** — `pg_get_functiondef` emits
uppercase, hand-written bodies vary), `--` line comments, single-quoted strings with `''` doubling
(double-quoted text is an identifier, left unstyled), and the shared `/* */` block comments.
That keyword set is **not defined in `ui/`**: it lives in the Qt-free core as
`pgtp_editor/sql/keywords.py::SQL_KEYWORDS` (a `frozenset` of 115 lowercase members) and
`code_editor.py` does `from pgtp_editor.sql.keywords import SQL_KEYWORDS` then binds
`_SQL_KEYWORDS = SQL_KEYWORDS` — a plain re-bind of the **same object**, so the existing
`_highlighter._keywords is _SQL_KEYWORDS` assertions still hold. It is therefore the **one shared
dialect source** for both the highlighter and the SQL/plpgsql selection formatter (§18.4): extend the
dialect in `sql/keywords.py` and both consumers see it, and the two can never disagree on what counts as
a keyword.
`CodeEditor` also exposes `navigate_to_line(line)` (1-based; the same public navigation entry point
`XmlEditor` exposes, used by the BrowserPanel → EditorPanel jump, §18.1). In its **`language="sql"` DDL
mode** navigation is **top-aligned** (the target line lands at the top of the viewport, not centered) —
overriding the earlier `centerCursor()` — so a clicked DDL object's banner sits at the top with its body
below (§18.1); every other language keeps `centerCursor()`, and `XmlEditor.navigate_to_line` stays
centered. Top-alignment is `_scroll_line_to_top(block)`: it drives the **vertical scrollbar**, whose
values count **visible** blocks in a `QPlainTextEdit` (via `_visible_block_offset`), so a *collapsed
fold above the target does not overshoot*, and it clamps to `[bar.minimum(), bar.maximum()]` so a target
near EOF simply scrolls to the bottom rather than being rejected. A **4-character tab stop**
(`_SQL_TAB_STOP_CHARS = 4`, `setTabStopDistance(4 × mono-char-advance)`) is likewise applied **only** when
`language == "sql"` (§18.1).

**Gutter on every code editor (deliberate, 2026-08-01).** Because the shared mixin sits on `CodeEditor`
itself rather than on a DDL-only subclass, the **JS/PHP "Edit code…" event-handler dialogs
(`CodeEditorDialog`) also get the line-number gutter and line bookmarks**. Folding is **inert** there:
no host installs fold regions, `_fold_regions` stays empty, and the default provider returns `None`, so
the fold zone simply never draws a glyph. This side effect was surfaced to the project owner, who
**explicitly chose to keep it** rather than gate the mixin per language: line numbers in a code editor
are conventional, and gating would add a second code path through the one gutter implementation.
Foldable regions are installed from outside via `CodeEditor.set_fold_regions(regions)` — an iterable of
`(start_block, first_contained_block, last_contained_block)` triples, all **0-based** — which replaces
any previous set and **drops `_fold_state`** (old block numbers no longer mean anything). `CodeEditor`
also exposes
`replace_current_selection(text)` (FindReplaceBar's Replace contract, mirroring `XmlEditor`), which
**no-ops on a read-only editor** — `QTextCursor` edits bypass `setReadOnly`, so this guard is what
actually protects read-only DDL buffers. `CodeEditorDialog(QDialog)` hosts it with
`saved(str)`/`cancelled` signals, **Ctrl+S** save / **Ctrl+W** cancel; never `.exec()` in tests.

**Tier-1 fallback:** on `PgtpParseError`, `_handle_parse_failure` keeps the `QMessageBox.critical`
dialog **and** re-reads the file, `setPlainText`, `highlight_error_line(exc.line)`, reveals + checks +
selects the Raw XML tab. Does not update `_current_project`/path or repopulate the tree.

---

## 9. Editor ↔ Tree sync & Reparse

- **Click-to-tree:** `model/line_index.py::node_at_line(project, line)` (document-order flat walk with
  depth-assigned end lines; Detail range starts at the outer `sourceline`; duplicate-table Details
  disambiguated by document position). `XmlEditor.line_clicked = Signal(int)` (1-based, from
  `mouseReleaseEvent`, left button only). MainWindow maps line → node → `project_tree.select_node(node)`
  → fires `currentItemChanged` → `PropertiesPanel.show_node`. `ProjectTreePanel` keeps an
  `id(node)→QTreeWidgetItem` map for O(1) selection. Wiring is one-directional (editor→tree→properties);
  no re-entrancy guard.
- **Double-click a tree node** → reveal Raw XML + `navigate_to_line(node.sourceline)`. Single click →
  Properties only.
- **Reparse** — `_reparse_raw_xml(silent: bool = False)`: `load_project_from_text(editor_text)`; on
  success (shared by every caller, manual or automatic) repopulate tree, set `_current_project`, clear
  Properties, show a status-bar confirmation, and refresh the **Database/XML Coherence view** if open
  (`_refresh_db_check_if_open` — a legacy name; it rebuilds the coherence tree against the **cached**
  schema via `_populate_db_check`, no live re-query, §17. The former separate Table References and
  Database Check panel refreshes are gone with those panels, FQ-003). On `PgtpParseError` the two modes
  diverge, both **preserving** the existing model/tree (neither re-reads the file nor touches the path):
  - `silent=False` (**Tools ▸ "Reparse Raw XML into Tree"**, the manual, explicit path) —
    `_handle_reparse_failure`: `QMessageBox.critical` + `highlight_error_line` jump to the error line.
  - `silent=True` (**auto-parse**, below) — no modal, no cursor jump; a transient status-bar message
    only ("Auto-parse: XML not well-formed yet — tree not updated"), leaving the tree in its last-good
    state.

  Reparse is the resync after manual edits, caption apply, code write-back, or create-from-table
  insertion — either explicitly triggered or, when auto-parse is enabled, automatically debounced off
  editor changes.

**Auto-parse XML** (Editor menu bar ▸ **Parsing** ▸ "Auto Parse XML", checkable, **off by default**, in-memory only — no
QSettings persistence, so it always starts unchecked on launch): when enabled, the app listens to
`XmlEditor.blockCountChanged` (a `QPlainTextEdit` signal that fires once whenever the document's line
count changes — Enter, multi-line paste, Ctrl+X, or Delete/Backspace joining lines — not once per line)
and, after a 400 ms debounce (`self._auto_parse_timer`, a singleShot `QTimer` mirroring the existing
`_snapshot_timer` debounce used for undo/redo history, §7), calls `_reparse_raw_xml(silent=True)`. The
timer restarts on each successive `blockCountChanged` firing (e.g. a held-down key), so it fires once
after the burst of edits settles rather than on every keystroke. Both the signal handler
(`_on_editor_block_count_changed`) and the debounced callback (`_auto_parse_now`) no-op whenever
`self._loading or self._restoring` is true or the toggle is off — the same guard flags that already gate
snapshot-history capture, so auto-parse never fires during programmatic text sets (file open, revert,
undo/redo restore). No Caption Mode gating is needed: the Raw XML editor is read-only while in Caption
Mode, so `blockCountChanged` cannot fire from user typing there. The manual Tools-menu action is
unaffected by the toggle and always uses `silent=False`.

---

## 10. Properties panel

`ui/properties_panel.py::PropertiesPanel(QWidget)` — **strictly read-only / navigate-only** (no cell is
editable, no write path). Header label + two-column (`Property`/`Value`) table + empty state.

`show_node(node, kind)` dispatches on `"page"|"detail"|"column"|"lookup"|"event"|"ddl_table"` (else
empty state) to a `RowSpec`-building pure function (`_ROW_BUILDERS`): `"lookup"` (§17's coherence-view
lookup references) reuses the column row builder with the `Column: {field_name}` header, and
`"ddl_table"` (§18.1's DDL Explorer table nodes) uses `_rows_for_ddl_table` with the `Table: {name}`
header and the paired alternating-shade row rendering.
`RowSpec{property_label, value, target_line, attr_name}`:

**Curated-label display** (§11): an attribute row whose value has a label in the curated XSD (explicit
`label="…"` or derived `sums` combination) renders the value as `value — label` (e.g.
`phpDriver: 1 — php-psql`). Display-only; the row's navigate-on-click behavior is unchanged.
- Page/Column: one row per `attrib` key, `target_line=node.sourceline`, `attr_name=key`.
- Detail: `caption` → outer `sourceline`; every other key → `inner_sourceline` (None → row click is a
  no-op).
- Event: exactly 3 rows — Handler (`tag_name`), Side (Client/Server), Functions (count via
  `_count_functions`, an approximate `function`-declaration regex).
- Column also appends a `— Representations —` divider then one row per `RepresentationVisibility`
  ("visible"/"hidden"/"— (not listed)", `target_line=rep.sourceline`).

Clicking a row → `navigate_to_line(target_line)`; if `attr_name` set, `_select_attribute_on_line`
selects the `attr="…"` span (silent no-op on miss; never crash).

---

## 11. Schema: curated XSD, learning & completion

Two XSD files with strictly separated roles, plus the learning engine's private JSON state. **The
hand-curated XSD is the official schema and the sole source feeding completion, hover hints, and the
Properties panel.** The vendored learning engine keeps running, but only as a discovery aid.

**Files** (`schema_learning/storage.py`, `QStandardPaths.AppDataLocation`, injectable `base_dir`):

| File | Path fn | Role |
|---|---|---|
| `curated.xsd` | `curated_xsd_path()` | **Official schema.** Hand-edited only (Edit XSD tab); never machine-written except the one-time first-run seed. Sole feed for completion / hover / Properties labels — **no learned fallback**. |
| `learned.xsd` | `learned_xsd_path()` | Generated discovery artifact. Regenerated by auto-learning on File ▸ Open; a reference for newly observed elements/attributes/values; never feeds completion; never touches `curated.xsd`. Openable read/write for analysis via **Schema ▸ Edit AutoXSD** in the same center-stage tab as Edit XSD (mode-aware, below). |
| bundled `resources/curated.xsd` | `storage.bundled_curated_xsd_text()` | **Curated v1.2** shipped with the app (`pgtp_editor/resources/curated.xsd`, in `[tool.setuptools.package-data]`; 109 elements / 254 `xs:attribute` definitions as of 2026-08-06 — the counts drift with curation, the XSD file itself is the source of truth; hand-commented, curated dialect). Version-marked by the XML comment `<!-- PGTP Editor curated schema v1.2 -->` and `storage.CURATED_BUNDLED_VERSION = "1.2"`. The **primary** seed source for the user's `curated.xsd` on first run. |
| `schema_model.json` | `schema_model_path()` | The learning engine's **private internal state** (counts, enum overflow). Feeds `learned.xsd` only. |

**One-time first-run seed:** on first run, if `curated.xsd` is absent, it is seeded by **copying the
bundled `resources/curated.xsd` (Curated v1.2)** — the real, hand-commented curated schema shipped with
the app (`storage.bundled_curated_xsd_text()`). Only when **no bundled resource is present** does the
app **fall back** to generating from the current learned model, emitting existing labels as `label="…"`
attributes (`xsd_gen.generate_curated_xsd`; `xsd_gen` gains a label-attribute emit mode). Seeding
happens **only when `curated.xsd` is absent** and **never overwrites an existing user file** — so
shipping a newer bundled version does **not** auto-upgrade a user who already has a `curated.xsd` (see
§29, open). After the seed the app never writes it (Import XSD replaces it wholesale, by explicit user
action).

**Dialect** — plain XSD plus three extensions of ours. Nothing external consumes the file; **Verify
checks our dialect, not W3C validity**:

- `label="…"` on `<xs:enumeration>` — the value's display meaning, e.g.
  `<xs:enumeration value="1" label="php-psql"/>`.
- `sums="true"` on `<xs:attribute>` — values are **additive**: the user labels only atomic values
  (1, 2, 4, 8, …); the app **derives** every combination's label (`3 = A+B` … `7 = A+B+C`,
  '+'-joined in ascending atomic order) for completion and hover. The Ctrl+Space value list offers
  **all** combinations (2^n − 1 rows) with derived labels — **capped at
  `settings_index.SUMS_MAX_ATOMS = 16` labeled atoms**: beyond 16, derivation is skipped entirely
  (2^n growth would freeze the UI) and only explicit enumeration labels are shown; Verify flags the
  attribute. An explicit enumeration row for a composite value overrides its derived label.
- `hint="…"` on `<xs:attribute>` — free-form attribute with a described meaning but no fixed values
  (no restriction block); the hint shows in hover; no value list in completion.

Curation of junk = **deleting enumeration rows**. There are no `kind`/`notes`/`enum_mode` concepts —
the file's structure is the entire vocabulary. An `xs:attribute` without enumerations completes by
name only.

**Engine model (private):** `Model.paths[chain]["attributes"][attr]` where `chain` = slash-joined tag
path from root (e.g. `PGTPProject/Pages/Page/Editor`, no indices). Attribute entries carry the
engine-owned `type`/`values`/`overflowed`/`attr_seen_count` only — the former labeler-owned fields
(`labels`/`kind`/`notes`/`enum_mode`) are gone. Enum overflow (`> ENUM_MAX_VALUES` →
`overflowed=True, values=None`): in `learned.xsd` an overflowed attribute emits the plain
non-enumerated XSD attribute form with no enumeration (test-pinned: `xsd_gen` only emits the
enumerated form when `not overflowed`). Overflow never applies to `curated.xsd` — it is hand-owned.

**Auto-learning** (unchanged trigger, new output): only **File ▸ Open** enriches (appended to the end
of the `open_project_file` success path, wrapped in try/except → one `[Schema] Could not update…`
audit line on failure). Reports via `_SCHEMA_REPORT_TEMPLATES`
(`new_element`/`new_attribute`/`new_value`/`enum_overflow`/`now_optional`); > 20 events collapse to
one summary line. Diff/Merge file pickers do **not** enrich. Enrichment updates `schema_model.json`
and regenerates **`learned.xsd` only**.

**Feeding pipeline:** `schema_learning/xsd_load.py` (Qt-free; streaming stdlib **expat** with a
`StartDoctypeDeclHandler` that raises `XsdLoadError` — **DTDs refused**, the same defensive posture as
defusedxml; the DTD-refusal message carries the offending line number, `line {n}: DTD declarations are
not allowed in the curated XSD`) parses `curated.xsd` via `load_curated(text) → CuratedSchema`:

```
CuratedSchema{
    model: Model,                                    # the existing in-memory Model shape
    attribute_lines: dict[(chain, attr) → line],     # 1-based source lines, power Go To XSD
    element_lines:   dict[chain → line],
}
```

Tag matching is **prefix-agnostic** (`xs:attribute` vs any prefix — only the local name matters, since
the user may use any namespace prefix in their curated file). Chains are built by a **type-reference
walk** from top-level `<element name=… type=…>` roots through named `complexType` child elements, with
a per-path **cycle guard** (`stack | {type_name}`): a recursive type stops, but a type reachable via
two different paths yields **both** chains. An **inline (unnamed) `complexType`** pushes a `None` frame
on the loader's type stack: attributes declared inside it land nowhere (they never leak into the
enclosing named type), while attributes declared **after** it closes correctly belong to the enclosing
named type again — Verify flags inline complexTypes as off-dialect. Per-attribute entries carry
`type` (base mapped to boolean/integer/decimal/string with **prefix-agnostic local-part fallback** —
`xsd:integer` still maps to integer, unknown bases default to string), `values`, `labels`,
`use`, and optional `sums`/`hint`; unknown structures are silently ignored — dialect complaints are
Verify's job, not the loader's. The loaded model feeds the `settings_index` query API — `known_attributes(model,
chain, present)`, `known_values(model, chain, attr)` (→ `[(value, label|None)]`), `enum_hint(model,
chain, attr)` (one-line hint, e.g. `editFormMode — 1 = modal · 2 = new page · 3 = inline`),
`unused_setting_attributes` — and therefore the completion/hover code keep their contracts. Loaded at
startup and on every Edit-XSD-tab save; handed to the editor via the existing
`set_schema_model(model)` (`None` disables). Semantics under the dialect: for a `sums` attribute,
`known_values` includes **all derived combinations**; `enum_hint` builds its hint from enumeration
labels (explicit and derived) or the `hint="…"` text; `unused_setting_attributes` = attributes the
curated schema knows for the chain that are absent from the tag — the old kind filter is gone: an
attribute is completion-worthy iff it exists in `curated.xsd`. The `sums` derivation is pure and
Qt-free in `settings_index.py` (composite label by decomposition into labeled atomic values; explicit
enumeration row wins; skipped when the labeled atoms exceed `SUMS_MAX_ATOMS = 16`).

**Disk-read guards:** every `curated.xsd` read catches **`OSError` and `UnicodeDecodeError`** (not just
parse errors). Startup / reload (`_load_curated_schema`, which also catches `XsdLoadError`) emits the
`[Schema] Curated XSD has XML errors: {error} — keeping last good schema` audit line and keeps the last
good in-memory schema live; opening the Edit XSD tab or running Verify against the saved file shows a
status-bar message (`Could not read curated.xsd: {error}`) and aborts.

**Mode-aware Edit XSD / Edit AutoXSD tab** (center stage): a **single** dedicated `CenterStage` tab —
one second `XmlEditor` instance with its own `FindReplaceBar` (full find/replace/Find All parity with
Raw XML) — that holds **either** the curated schema **or** the learned/auto schema. Which one is
tracked by `_xsd_mode ∈ {"curated","learned"}`:

- **Schema ▸ Edit XSD** loads `curated.xsd` into the tab in `"curated"` mode (title **"Edit XSD"**).
- **Schema ▸ Edit AutoXSD** loads `learned.xsd` (the auto-learning discovery artifact, regenerated on
  every File ▸ Open) into the **same** tab in `"learned"` mode (title **"Edit AutoXSD"**). Its purpose
  is **analysis** — comparing what auto-learning discovered against the hand-curated schema to decide
  what to hand-add to curated.

The tab title reflects the mode ("Edit XSD" vs "Edit AutoXSD") plus the existing dirty `" *"` suffix.
The tab owns its dirty state; Ctrl+S and the Find/Replace gestures route to the **active** tab (per-tab
document routing, §7). **Switching modes** (Edit XSD ↔ Edit AutoXSD) while the tab has unsaved edits
prompts the same three-way **Save/Discard/Cancel** used by `closeEvent`.

The tab is **closable** via a tab-bar ✕ (alongside Manual and DDL Explorer; Diff/Merge, Caption
Management, and Raw XML remain structural/non-closable, toggled only by their own entry points). Clicking it emits
`CenterStage.xsd_close_requested`, handled by `MainWindow._on_xsd_close_requested`, which reuses the
**same** `_confirm_close_xsd()` Save/Discard/Cancel prompt already used for mode-switching and
`closeEvent` — no separate confirmation dialog. On discard, on a clean tab, or after a successful
close-time save, `CenterStage.hide_edit_xsd()` hides the tab (mirroring `hide_manual()`) and the view
falls back to Raw XML; on cancel the tab stays open, visible, and dirty; a save failure during the
close-time save also leaves the tab open.

**Save / Verify / Export / Import act on the currently-open XSD** (the file the tab holds in its
current mode):

- **Save** (`"curated"`) → write `curated.xsd` (UTF-8, `newline=""`) → re-parse via `xsd_load` →
  refresh completion/hover/Properties immediately → auto-run Verify report-only on the saved text.
- **Save** (`"learned"`) → write `learned.xsd` (UTF-8, `newline=""`) → auto-run Verify report-only,
  but **does NOT feed completion/hover/Properties** (the learned schema never feeds completion — §11
  invariant preserved).
- **Verify / Export / Import** target whichever file the tab currently holds (curated or auto), not
  curated-only.

**Malformed XML on save** (curated mode): the text is still written (user text is never lost), the
audit line `[Schema] Curated XSD has XML errors: {error} — keeping last good schema` is emitted, and
the last good in-memory schema stays live.

**First-run seed audit line:** copying the bundled resource emits its seed audit line; the learned-model
**fallback** emits `[Schema] Bootstrapped curated.xsd from the learned schema (labels preserved)`
(failure → `[Schema] Could not bootstrap curated.xsd: {error}`).

**Go To XSD:** a **window-level `QAction`** (`Ctrl+L`, registered via `self.addAction(...)` on
MainWindow — deliberately **not** a Schema-menu item) plus a Raw XML editor right-click
**"Go To XSD"** context-menu entry. It **always forces curated mode** (it navigates to curated
attribute definitions; if the tab is in `"learned"` mode it switches back to `"curated"`, honoring the
unsaved-edits Save/Discard/Cancel prompt). It resolves the caret's attribute/element context (pure
`attribute_at_position` / `attribute_value_at_position` resolvers), activates the Edit XSD tab in
curated mode, and navigates to the `<xs:attribute name="…">` definition line via
`CuratedSchema.attribute_lines[(chain, attr)]`; if the attribute is absent, falls back to
`element_lines[chain]` (the element's type definition); otherwise a status-bar message. Lines come
from the **last successful parse** — navigation targets the saved file content, not unsaved tab edits.

**Schema menu — five items** (between View and Database — the menubar build order is File · Edit · View ·
Schema · Database · Tools · Bookmarks · Generation · Help; see consolidated menu, §26):
- **Edit XSD** — open (or switch) the mode-aware tab in curated mode.
- **Edit AutoXSD** — open (or switch) the same tab in learned mode on `learned.xsd` (analysis).
- **Verify XSD** — dialect rules via `schema_learning/xsd_verify.py::verify_curated(text) →
  list[Issue{line, message, fatal}]` (streaming expat, prefix-agnostic). Checks as shipped:
  **duplicate enumeration values** (per `xs:attribute`), **`label` off-enumeration** (`label="…"` on
  any non-enumeration tag), **`sums` off-attribute** (`sums` on any non-attribute tag), **`hint`
  off-attribute** (`hint` on any non-attribute tag), **unknown base type** (lenient: a base is accepted
  with *any* prefix whose local part is one of boolean/integer/decimal/string), **unresolved type
  references** (element `type=` naming no `complexType`), **duplicate type names**, **inline (unnamed)
  `complexType`** ("not part of the dialect"), **sums attribute with no labeled atomic values**,
  **sums attribute exceeding the derivation cap** ("too many values for derivation
  ({n} > 16)" when its enumeration count exceeds `SUMS_MAX_ATOMS`; both sums rules report at the
  attribute's start line), and **duplicate attribute name within one `complexType`** (a second
  `xs:attribute name="…"` inside the same `complexType` silently overwrote the first before this check
  existed; the seen-names set resets on every `complexType` start since complexTypes never nest in this
  dialect; reports at the line of the second/overwriting occurrence,
  `"duplicate attribute name '{name}' in this complexType"`). Malformed XML or a DTD declaration → a **single fatal Issue**
  (`XML error: …`, at the offending line). Issues are **sorted by line**. Menu action verifies the
  **active XSD** (curated or learned, per `_xsd_mode`): the XSD tab's live text when it has unsaved
  edits, else the saved file for the current mode; also auto-runs report-only on every Edit-XSD-tab
  save and on import. Audit output: one clickable line per issue,
  `[Schema] VERIFY line {n}: {message}` (line on `UserRole`, target `"xsd"` on `UserRole+1` — the same
  item-data click convention Find All uses; click activates the Edit XSD tab at that line), or
  `[Schema] VERIFY: no issues found.` when clean.
- **Export XSD** — Save-As copy of the **active XSD** (`curated.xsd` in curated mode, `learned.xsd` in
  learned mode; `shutil.copyfile`); refused with a status-bar message while the XSD tab has unsaved
  edits ("save it first").
- **Import XSD** — Open dialog → **verify the incoming file first** (hard refuse malformed XML with an
  "Import Refused" dialog; non-fatal dialect warnings prompt a `QMessageBox.question` Yes/No
  "Import With Warnings" confirm) → back up the **active file** (`curated.xsd.bak` / `learned.xsd.bak`)
  → replace → re-parse → refresh (curated-mode import re-feeds completion; learned-mode import does
  not). Read failures catch **`OSError` and `UnicodeDecodeError`** → "Import Failed"
  critical dialog; a write failure (`OSError`) → "Import Failed" as well. Success emits
  `[Schema] Imported curated XSD from {name}`, with the suffix
  `" (unsaved XSD tab edits were replaced)"` appended when the XSD tab was dirty, followed by the
  verify report. Team sharing = plain file exchange via Export/Import.

**Editor integration** (mechanics unchanged; source now exclusively `curated.xsd`):
- **Hover** over an attribute name/value in an opening tag shows a `QToolTip` with `enum_hint(...)`,
  including derived `sums` labels and `hint="…"` text. Pure resolver `attribute_at_position(text,pos)`.
- **Right-click ▸ Add attribute ▸** submenu from `unused_setting_attributes`; inserts ` name=""` with
  caret between quotes via pure `insert_attribute(text, insert_pos, name)`.
- **Ctrl+Space autocomplete:** `_CompletionPopup(QListWidget)` (frameless, non-modal). Attribute stage
  uses `known_attributes`; on choose, inserts ` name=""` and, if `known_values` non-empty, chains a
  value popup (displays `value` or `value = label`, inserts bare value; derived `sums` labels shown
  like explicit ones; a `hint` attribute offers no value list). ↑/↓ navigate, Enter/Tab/click choose,
  Esc/focus-out cancel, printable chars prefix-filter. Guarded by `not isReadOnly()` + model present +
  `enclosing_open_tag(...)` resolving.

---

## 12. Diff / Merge

Three dependency-ordered sub-projects. Inputs are always **Source** and **Target**; differences flow
Source→Target and **only Target is ever mutated/written**. Ethos: never a silent wrong result.

**Engine** (`diff/differ.py` + `diff/records.py`, Qt-free, operates only on loaded `ProjectModel`s —
no I/O, no mutation): `diff_project(source, target)→list[Difference]`; recursive
`compare_block(source_node, target_node, path, node_kind, ambiguous=False)`.
- Page matching: global by `fileName`. Detail matching: `(tableName, caption)` **scoped to the parent
  pair**. Column: by `fieldName`. Event: by base handler name via `classify_event_side` normalization.
- `Difference{kind: added|removed|changed, path: list[str], node_kind: page|detail|column|event|
  format|lookup|view_properties|edit_properties, attribute: str|None, old_value(Target), new_value(Source),
  ambiguous: bool}`. Attribute `changed` → `attribute` set; whole-subtree add/remove and event-text
  change → `attribute=None`. Event text change carries raw texts in old/new.
- Duplicate siblings sharing `(tableName, caption)` under one parent → paired **positionally**, every
  resulting `Difference` marked `ambiguous=True`.
- **No `moved` detection** (a relocation = one removed + one added).
- Column sub-elements (`format`/`lookup`/`view_properties`/`edit_properties`) are diffed via
  `_compare_child_element` (one `changed` per differing attrib key).

**resolve.py** — `resolve_path(project, path) → PageNode | DetailNode | ResolutionError`
(`ResolutionError{segment_index, message}`, never bare `None`). Path segments: `path[0]`=Page
`fileName`; `path[1:]`=`"tableName/caption"` Detail segments. Mirrors the differ's matching; duplicate
siblings → first match.

**Viewer** (`diff_merge_panel.py::DiffMergePanel`, replaces the placeholder at
`CenterStage.diff_merge_tab_index`) — horizontal splitter: a change-list `QTreeWidget` (rebuilt each
`show_differences`, shared prefixes reused; leaves carry the `Difference` and are the only checkable
items, **default unchecked = Skip**; ambiguous leaves prefixed `"⚠ "`) + a detail view (3 mutually
exclusive: Old/New rows for attribute change; read-only attrib table for whole-subtree add/remove;
stdlib `difflib.unified_diff` in a read-only `QPlainTextEdit` for event-text change). Next/Prev
Difference walk the flattened leaves (no wraparound).

**Three entry points** all converge on `show_differences`: Tools ▸ "Compare/Merge Two Files…" (Source
defaults to current project, Target prompted); Project-tree Page ▸ "Compare This Page With…";
Project-tree Detail ▸ "Compare This Detail With…" (uses `resolve_path`).

**Write-back** (`diff/apply.py::apply_differences(target, differences)→ApplyResult{applied, failed}`) —
mutates the retained `lxml` tree in place: `changed`→`element.set/del`; event `changed`→`element.text`;
`added`→`copy.deepcopy` the Source element and insert (append into the appropriate container, creating
`<Details>`/`<EventHandlers>` as needed); `removed`→`element.getparent().remove(element)`. Target
element located via `resolve_path` (+ one flat scan for column/event granularity).
- **Ambiguity gate** (in MainWindow, not apply.py): if **any** checked difference is ambiguous, refuse
  the **entire** batch with a `QMessageBox.critical` naming each; recovery = uncheck & re-run.
- **All-or-nothing:** apply to a `copy.deepcopy` of the tree; only if every checked non-ambiguous
  difference applies do we write. `.bak` via `shutil.copy2` immediately before writing; serialize with
  `etree.tostring(tree, xml_declaration=False, encoding="UTF-8", pretty_print=False)`, `"wb"`.
- After a successful Apply, Target is **auto-reloaded** (`open_project_file`); the change-list is **not**
  auto-cleared or auto-re-diffed (preserves review boundary). `.bak` is the only recovery (no in-app
  revert-merge).

---

## 13. Captions

A single Excel-style, filterable grid to review/edit every user-facing caption-like string.

**Pure core** (`ui/caption_scan.py`, Qt-free): caption-like attributes scanned =
`caption, shortCaption, headerHint, insertFormCaption, groupName`.
`CaptionEntry{line, element_tag, anchor, attribute, value, breadcrumb}` — `anchor` = `fieldName` else
`fileName` else `tableName` else tag; `breadcrumb` = ancestor Page/Detail captions joined ` → ` + own
label. `scan_captions(text)` (lxml; `[]` if not well-formed). `apply_caption_edits(text, edits)` operates
per source line with a **boundary-safe** regex (negative lookbehind so `caption` never matches inside
`shortCaption`/`insertFormCaption`), XML-attribute-escaping the new value; unmatched lines left
unchanged. Helpers `apply_find_replace(value, find, repl, mode, case)` and
`transform_caption(text, kind)` (Title Case / UPPERCASE / lowercase / Sentence case / Trim / Humanize).

**Grid** (`caption_management_panel.py::CaptionManagementPanel`) — columns
`Changed · Line · Breadcrumb · Element · Anchor · Attribute · Value · New Value`. **Value is read-only;
New Value is the only editable column.** A row is *changed* iff New Value is non-empty; the literal
sentinel `<NULL>` means set the caption to empty string. `changed_edits()` resolves that. Changed rows
tinted `#26343a`; inconsistency (same `(anchor, attribute)`, differing values) tinted `#3a2f1d`;
changed wins. **Filtering — three independent mechanisms** (BUG-020, 2026-08-05): Excel-style
per-column **header filter** popups (non-modal, checkable distinct values) via proxy
`set_value_filter(column, allowed|None)`, AND-ed with a regex **find filter**
(`set_regex_filter(pattern, mode, case)`), and a third, **preset row-predicate** filter
(`_CaptionFilterProxyModel.set_row_predicate(predicate, label: str = "")`) applied programmatically by
the Browser Pane's "See column in caption mode" entry path (`filter_to_field`/`filter_to_table`/
`filter_to_table_details`, reached via `MainWindow._on_tree_see_column_in_caption` →
`enter_caption_mode_for_field`/`enter_caption_mode_for_table_details`) rather than by any grid widget —
it narrows to a semantic condition (e.g. `field_name == "wbs_id"`) no manual gesture produces.

**Active-filter banner** (BUG-020, extended by BUG-028, both 2026-08-05). A `QLabel` + "Clear"
`QPushButton` (`self._filter_banner` / `self._filter_banner_label`) inserted above `self._table`,
refreshed by `_refresh_filter_banner()` after **every** preset filter setter, after `apply_find_filter`
and after `clear_all_filters` — always *after* the proxy has been invalidated, so the row counts are the
new ones. It represents **two** of the three mechanisms, joined by `"  ·  "` when both are active, and
reads `"Filtered: <descriptors> — showing N of M rows"` (`N = _proxy.rowCount()`,
`M = _model.rowCount()`):

| Source | Descriptor | Example |
|---|---|---|
| Preset row-predicate | `_proxy.row_predicate_label()` | `Field = wbs_id`, `Table = pr.equip`, `Table = pr.att  (Detail embeds)`, `Field = wbs_id  ·  Table = pr.equip` |
| Whole-row find filter | `_find_filter_descriptor()` | `Find "ord" (all columns)`, `Find "^Ord$" (regex, case-sensitive, all columns)` |

`_find_filter_descriptor()` returns `""` when `_proxy.find_pattern()` is empty; otherwise it builds
`Find "<pattern>" (<qualifiers>)` where the qualifiers list names the mode only when it is **not** the
default Normal (`regular` → `regex`, `extended` → `extended`), adds `case-sensitive` only when the case
flag is set, and **always** ends with **`all columns`** — the honest scope statement, because
`_passes_find_filter` accepts a row iff any column matches across `range(model.columnCount())`. Mode and
case are read through the proxy getters `find_mode()`/`find_case()` (added alongside the existing
`find_pattern()`), never off the private attributes. The banner **hides only when neither** descriptor is
present; `clear_all_filters()` remains the single path that deactivates everything (it already clears the
find pattern) — no second clear path exists. `apply_find_filter` refreshes only **after**
`set_regex_filter` returns normally, since an invalid regex raises `ValueError`.

**Header value filters are deliberately NOT represented in the banner** — they keep their own per-column
`_FILTER_INDICATOR` ▼ marker, and the ▼ marker stays exclusive to `set_value_filter`. Conversely the
preset predicate and the find filter are **not** per-column (the find filter is whole-row), so the banner
is their only surface — no ▼ is ever painted for them. **(The earlier inline per-column QLineEdit filter
row was removed.)**

Right-click: Insert NULL, Go to line in XML (Ctrl+G, injected `on_go_to_line`),
**Transform ▸**, **Unify** (set all inconsistent siblings to this value — see the scope prompt below when
a filter is active). Ctrl+C copies cells tab/newline-separated; Ctrl+V fills New Value (Excel vertical
fill). Decoupled from MainWindow via injected callbacks.

**Unify scope prompt when a filter is active** (BUG-023, 2026-08-05). `unify_current()` unconditionally
ran project-wide; it now checks `self._proxy.is_any_filter_active()` first. With **no filter active**,
behavior is unchanged — no prompt, unify runs project-wide via `unify_from_row(source_row)`. With
**any filter active** (header, find, or the preset predicate above), `_confirm_unify_scope()` — a
`QMessageBox` mirroring `MainWindow._confirm_close_xsd`'s string-returning pattern, so tests monkeypatch
it rather than ever driving a live modal — asks **"Filtered rows only" / "Entire project" / Cancel**.
"Filtered rows only" calls `unify_from_row(source_row, restrict_to=self._visible_source_rows())`;
"Entire project" calls the unrestricted form; Cancel does nothing.

**The caption find/replace MODAL IS DELETED; the in-panel bar is permanent** (FQ-017, settled
2026-08-07; ledger §28). Owner's instruction, verbatim: *"forget totally caption filter: delete totally
the modal and the menu, keep the find and replace bar as is now, always visible, with the same logic as in
editor window."* Caption find/replace existed **twice** — the non-modal `CaptionFindReplaceDialog`
(reached from `Tools ▸ Caption Filter…` and from two window-scoped, Caption-Mode-gated `Ctrl+F`/`Ctrl+R`
`QShortcut`s) and the `CaptionFindReplaceBar` already living inside the Caption Management tab. Two
surfaces, one job, and the two shortcuts were the same chords the Edit menu advertised for
`Find…`/`Replace...`, so **the menu advertised one behaviour while the key did another** — a live conflict
both halves of which disappear together with FQ-016.

**(a) Delete the modal outright.** Removed surface: the module `ui/caption_find_replace_dialog.py`; its
test file; ~16 references in `main_window.py` (`_make_caption_find_replace_dialog`,
`_open_caption_filter_dialog`, `_open_caption_replace_dialog`, `_caption_shortcut_open_filter`,
`_caption_shortcut_open_replace`, the two `QShortcut`s, the `Tools ▸ Caption Filter…` entry and the
`on_open_filter`/`on_open_replace` injections) plus their references in
`tests/ui/test_main_window.py` and `tests/ui/test_mainwindow_surface.py`.
`CaptionManagementPanel.set_regex_filter` **STAYS** — it is the panel's own internal filter path, not the
modal's.
> **Correction, load-bearing (the shipped shape, commit `02e47e0`):** the two `Ctrl+F`/`Ctrl+R`
> `QShortcut`s were **not deleted — they were RELOCATED and rescoped.** What died is the *window-scoped,
> Caption-Mode-gated* pair on `MainWindow` that opened the modal; `CaptionManagementPanel.__init__` now
> creates its own `Ctrl+F` → `focus_find_replace_bar` and `Ctrl+R` → `focus_replace_field`, both with
> **`Qt.ShortcutContext.WidgetWithChildrenShortcut`** on the panel, so they are live wherever the caption
> grid or the bar has focus and inert everywhere else. `FindValidateController.set_find_actions` /
> `set_find_actions_enabled` still go — but because **FQ-016 deleted the Edit-menu QActions they gated**
> and because `Ctrl+F` is now hosted **per surface** (so exactly one match is live for any focus location,
> §7/§27), not because the caption shortcuts went away. The narrower-context ambiguity rule in §7 is the
> reason FQ-016 could not simply install one window-level `Ctrl+F`.
> **Load-bearing code detail:** `MODE_LABELS` — the three search modes — used to be defined **in the
> deleted module** and imported by the survivor. It **moves to `caption_management_panel.py`**, which is
> now its only consumer and therefore owns it; without that move, deleting the module would break the very
> bar it is supposed to keep.

**(b) The bar becomes permanent.** `self.hide()` in `CaptionFindReplaceBar.__init__` goes; `show_bar()`
collapses to the **focus** operations `focus_find(initial_find="")` / `focus_replace()` (each focusing its
field and `selectAll()`-ing it); `Escape` **returns focus to the grid** instead of calling `close_bar()`.
**Both §29 sub-questions are answered by the shipped code:** the grid's context-menu entry survives as
**"Focus Find / Replace bar"** → `focus_find_replace_bar`, and the `current_filter_pattern()` seeding
survives there too — `focus_find_replace_bar` passes it into `focus_find`, which seeds Find-what when the
field is empty, so Filter-then-Replace reuse still works.

**(c) `Replace All` plus a scope dropdown — and what the dropdown does NOT do.** The bar's
`replace_field` is **already fully wired and live**: `textChanged → run_live_replace` → the injected
`live_replace_preview`, which on **every keystroke** rolls back the previous proposal from
`_live_replace_baseline` and writes a fresh one into the **New Value** column for the
currently-visible (filtered) rows; the placeholder text is literally `"Replace with (live)"`. So a
`Replace All` button is **not** restoring stranded capability for the filtered scope — that scope is
already covered, continuously. What only the modal could reach was the **project-wide** scope, which
`replace_all_find(..., in_selection=False)` already implements. Therefore:
- A **scope dropdown immediately before `Replace All`** offers *"in filtered results"* (**default**) and
  *"in all project"*.
- *"in filtered results"* keeps today's live behaviour. ***"in all project" is INERT until `Replace All`
  is pressed*** — the dropdown selects the scope; the **button** is what authorizes a project-wide write.
  The alternative (letting the dropdown drive the live preview) is **rejected explicitly**: it would make
  a single keystroke rewrite every caption in the project, against the panel's own standing rule that
  *"going project-wide stays an explicit, button-pressed gesture rather than something a keystroke can
  do."*
- **Recorded as an intentional semantic change, not a port:** the modal's `on_replace_all(find,
  replacement, mode, case, in_selection)` was **selection**-scoped; the new dropdown is
  **filter**-scoped. **Selection-scoped replace is dropped on purpose**, and no `in_selection` parameter
  whose meaning matches no control on screen may survive in the new call path.
- The whole design is sufficient protection without a modal because of §13's own staging discipline: a
  caption edit lands in **New Value** and only an explicit **Apply** touches the XML.

**(d) `Close` is removed — and `Replace All` inherits its commit duty.** The bar was constructed with
`on_close=self.commit_live_replace`, and `commit_live_replace` *"stop[s] tracking the live preview:
whatever it proposed becomes an ordinary, hand-editable New Value… it only forgets the rollback
baseline"* — i.e. `close_bar` was **the handoff from reversible preview to ordinary proposal**. With the
bar permanent, `on_close` never fires, so `_live_replace_baseline` would never be released and **a hand
edit of a previewed row's New Value would be silently reverted by the next re-run.** Settled 2026-08-07
by the owner's delegated authority:
- **"Active" is redefined as *the Find field is non-empty***, not *between `show_bar` and `close_bar`* —
  the natural reading once the bar is permanent. `is_active()` and `_refresh_live_replace`'s
  `if not is_active() and not baseline: return` guard are re-expressed against it.
- **`Replace All` commits the baseline.** An explicit, deliberate write is exactly the right handoff
  point, and **emptying the Find field already rolls everything back cleanly**, so the reversibility
  contract survives the loss of `Close`. This changes *when* a proposal stops being reversible, and that
  is the intended change.

**(e) `Clear filter`** binds to the **existing** `clear_all_filters()` (which already calls
`_refresh_live_replace()` afterwards) — do not write a second clear path. Note the mismatch to settle
(§29): that method clears **all** filters including the tree-set row predicates, while the singular label
*"Clear filter"* suggests only the text filter. Naming matters here because the banner is the only surface
that shows the predicate filters.

**(f) `mode_combo` keeps all THREE modes** — `Normal (plain string)` / `Extended (\n \t \0 \xNN)` /
`Regular expression`. The owner named only normal and regexp; **dropping `Extended` would be a capability
removal** (`apply_find_replace`/`matches` implement it, and the grid is the only place escape sequences in
caption text can be matched), so it stays pending explicit confirmation (§29).

**(g) Layout.** Today: `[find_field] [mode_combo] [match_case] [Filter] [Close]` over `[replace_field]
[status_label] [error_label]`. Target: `Close` **removed**, `Clear filter` **added**, and `[scope
dropdown] [Replace All]` beside the replace field per the owner's *"immediately before Replace All"*
ordering. **`Match case` and a status label already exist — do not add second ones.** The inline
`error_label` stays the **only** invalid-regex channel, never a modal; that rule is unchanged and
load-bearing.

**Two things explicitly OUT of scope, recorded so an implementer does not "improve" them:**
- **`Unify` is untouched.** `_confirm_unify_scope` stays exactly as it is. Converting it to the same
  dropdown for idiom consistency was proposed and **corrected by the owner:** *"unify is independent and
  important filling the fields with the same value as in the other. Replace replaces parts of words."*
  Whole-value propagation and substring editing are different operations, so a shared idiom is not owed.
- **The active-filter banner STAYS.** Not because of text filters — the permanent bar shows those
  plainly — but because it also describes **row-predicate** filters set by tree gestures (e.g. *"Field =
  wbs_id"*), which a text field cannot express. Retiring it would **re-create BUG-020**.

**Caption Mode** (`center_stage.py` + `main_window.py`): Tools ▸ "Manage Captions…". On enter, the Raw
XML editor **stays visible but read-only** (a persistent status-bar label reads "Caption Mode (XML
read-only)"; edit attempts flash a hint via a new `read_only_edit_attempted` signal). Reveal the Caption
Management tab, `scan_captions` the snapshot, `load_entries`. Apply computes
`apply_caption_edits(snapshot, changed_edits)` into the Raw XML buffer **in memory only** (no disk, no
`.bak`, no auto-reparse); the snapshot updates so line numbers stay valid. Close restores editing mode.
`_enter_caption_mode`/`_close_caption_mode` gate individual `QAction`s (never just their parent menu, so
the underlying keyboard shortcut is actually disabled too). **The Find…/Replace… pair it used to gate is
gone** (FQ-016/FQ-017, 2026-08-07): the Edit-menu QActions are deleted, and `Ctrl+F`/`Ctrl+R` are now
**per-surface `WidgetWithChildrenShortcut` shortcuts** — the caption panel owns its own pair, every bar host
owns its own — so exactly one match is live for any focus location and there is nothing left to arbitrate at
mode-switch time; `set_find_actions`/`set_find_actions_enabled` are deleted with it. **Note this is a
structural fix, not the disappearance of the caption shortcuts** — they still exist, rescoped to the panel. The same
individual-action gating pattern **is applied** (implemented; §8) to the **Bookmarks menu and its five actions**
(`FindValidateController._bookmarks_menu` + `_bookmark_actions` = Toggle/Next/Previous/Clear All/List All,
via `set_bookmarks_enabled`), since Caption Mode's read-only editor makes
line-anchored bookmark navigation ambiguous alongside caption-grid navigation — but **not** to gutter
bookmark toggling itself, which stays a click-driven overlay independent of read-only state.

---

## 14. Columns

Two additive extensions to `ColumnNode`, both built inside `_parse_columns`.

**Sub-element model** (`nodes.py`/`parser.py`, no UI): `ChildElement{attrib, sourceline, element}`;
`ColumnNode` gains `format`, `lookup`, `view_properties`, `edit_properties` (all `ChildElement|None`).
`Format` is located at `ViewProperties/Format` (grandchild); the other three are direct children.
Real attribute names (grounding): `Format`(type, decimalSeparator, thousandSeparator, numberAfterDecimal);
`Lookup`(tableName, linkFieldName, displayFieldName, lookupFilter, useLookupOrdering, lookupOrdering,
allowAddNewItemsOnTheFly?); `ViewProperties`(type, maxLength?); `EditProperties`(type ∈
textBox/autocomplete/dynamicCombobox/textArea, maxLength, placeholder, …). Differ threads these as four
new `node_kind`s; `apply.py` write-back for these is **scoped out** (documented limitation; a clean
`ApplyFailure` is produced for added/changed).

**Representation visibility** (surfaced read-only in Properties): 10 fixed representations
(`List, View, Edit, Insert, QuickFilter, FilterBuilder, Print, Export, Compare, MultiEdit`) each
appearing once per `<Columns>` block. `RepresentationVisibility{name, visible: bool|None, sourceline}`
(`visible="false"`→hidden, absent entry→visible, representation-present-but-field-absent→None).
`ColumnNode.representations: list[...]` built by `_build_representation_index(container_el)` in
`REPRESENTATION_NAMES` order. No editing, no diff/merge/write-back.

---

## 15. Search, Find All & Table References

**Search core** (`ui/search.py`, Qt-free) — **plain case-insensitive substring only** (no
regex/whole-word/case toggles, no options UI): `find_next(text, term, from_pos, *, wrap=True)`,
`iter_matches(text, term)` (lazy generator), `find_all_matches = list(iter_matches(...))`.
`Match{start, line(1-based), preview}`. Non-overlapping scan (advance by `len(term)`).

**Find/Replace bar** (`ui/find_replace_bar.py::FindReplaceBar(QWidget)`) — modeless, shown **below** the
editor inside the Raw XML tab (`center_stage.raw_xml_tab` container). Constructed as
`FindReplaceBar(editor, on_find_all=None)`; the other two callbacks are **setter-injected after
construction** (`set_on_stop_find_all(cb)`, `set_on_status(cb)` — a `set_on_find_all(cb)` also exists
for rebinding), not constructor parameters. Find/Replace fields + Find Next /
Find All(↔Stop) / Replace / Replace All. Replace-all rewrites all matches in one undo block
(right-to-left). The editor gains `replace_current_selection(text)`.

**The bar is PERMANENTLY VISIBLE, in its expanded form** (FQ-016, settled 2026-08-07; ledger §28). Four
hide/show sites are **deleted, not left inert**:

| Was | Becomes |
|---|---|
| `self.hide()` in `__init__` | gone — the bar is visible from construction |
| `show_find()` / `show_replace()` (the latter showing the replace row, the former hiding it) | collapse into **one focus operation**; the `_replace_row_widget.hide()/.show()` machinery becomes dead code, because the replace row is always shown |
| `keyPressEvent`'s `Escape → self.hide()` | `Escape → self._editor.setFocus()` only — focus returns to the editor, the bar stays |
| `_prefill_from_selection()`, called from **both** `show_find` and `show_replace` | **moved onto the focus path** — both `focus_find()` and `focus_replace()` call it first, so "select a word, press `Ctrl+F`" (or `Ctrl+R`, which arms the search and then puts the caret where the user types) still prefills. It stays distinct from `set_find_text`, which the editor's right-click ▸ Find path uses and which prefills *unconditionally* |

**Settled: `Ctrl+F` is a no-op on tabs with no bar** (was §29's open item). `active_find_bar()`'s Raw-XML
reveal was defensible when `Ctrl+F` *showed* a bar; as a pure **focus** gesture, yanking the user to a
different document would be surprising. The shipped answer is structural: `Ctrl+F`/`Ctrl+R` are
`install_focus_shortcuts` pairs **on each bar's host**, so on the Manual and Diff/Merge tabs no shortcut
exists and nothing happens. `active_find_bar()` and its reveal are unchanged and now serve **F3 only**.

**No Find/Replace menu entries exist any more.** The five Edit-menu actions — Find… (Ctrl+F), Find Next
(F3), Find All (Ctrl+Shift+F), Replace… (Ctrl+R), Replace All (Ctrl+Alt+Return) — are **deleted with the
Edit menu** (FQ-016, §7/§26; ledger §28). The bar's **buttons** are now the only menu-like surface for
Find All and Replace All, and the surviving keys are specified in §27: `Ctrl+F`/`Ctrl+R` as **focus**
gestures, **`F3` as a window-level shortcut with no menu entry** routed to `active_find_bar().find_next()`
(the `Ctrl+L` Go To XSD shape), and `Ctrl+Shift+F` / `Ctrl+Alt+Return` **gone**. **`F3` alone** routes
through `FindValidateController.active_find_bar()` (the full per-tab dispatch is in §7) and delegates to the
same `find_next` the button uses; `Ctrl+F`/`Ctrl+R` bypass that dispatcher entirely, because each bar's host
owns its own pair (`install_focus_shortcuts`) and therefore already knows which bar it means. Every
editing tab hosts its own `FindReplaceBar` instance; the Edit XSD one has full Find All parity, and the
DDL Explorer buffer is read-only so its Replace path no-ops via `CodeEditor.replace_current_selection`
(§8). (The old "Find & Replace…" Ctrl+H stub was removed long before.)

**Find All → Audit panel, streaming:** `_populate_find_all_results(term)` starts a chunked,
`QTimer`-driven run (batch **200** matches/tick, snapshot text once, cancel any in-flight run). Items
`"[Find] line N: preview"` (line on `UserRole`) + a trailing `"[Find] N match(es) for \"term\""` summary.
`_clear_find_results` removes only `[Find]` items. Status bar: `Finding "term"… found N` / `Found N
item(s)` / `Find All stopped — found N item(s)` / `N replacement(s) for "term"`. The Find All button
toggles to **Stop** while running. Single-threaded chunking only (no threads, no progress bar, no caps).
**Since FQ-016 the bar's button is the ONLY way to start a Find All** — `Ctrl+Shift+F` is deleted, on the
recorded reasoning that Find All writes `[Find]` rows into the Audit panel, is a deliberate and occasional
act, and now has a permanently visible button, so a chord earns little. The run's own `target`
discriminator (`"raw"`/`"xsd"`) is unchanged, and Find All stays **inert in both DDL tabs and in the PHP
and draft tabs**, because `_populate_find_all_results` understands only those two targets.

**Table references — moved to §17** (FQ-003, settled 2026-08-06; ledger §28). Table-reference analysis
is no longer an independently toggleable left-dock surface of its own. The pure analyzer
(`analysis/reused_tables.py::collect_table_usages`) and the tree presentation built on it are specified
in **§17's Database/XML Coherence view**, where they appear as the per-relation **References** sub-section
and as the whole **Pages** branch. The standalone "Table references" `left_tabs` tab
(`table_refs_tab_index`) and the **View menu** checkable "Find table reference" cease to exist as entry
points; the single Database-menu **Database/XML Coherence** toggle replaces them (§26). The still-earlier
Tools ▸ "Find Reused Tables…" modal, its handler and `reused_tables_window.py` remain removed/deleted.
**Code note (2026-08-06):** both superseded modules — `ui/table_references_panel.py` **and**
`ui/db_check_panel.py` — plus their two test files were **deleted** the same day (FQ-003 left them with
zero importers; the ui suite ran green after the deletion — 2216 passed). Neither exists in the tree.

---

## 16. Validation

Two tiers of §6.7.

**Tier 1 — well-formedness (blocking):** enforced where raw text bypasses the model (file open, Raw XML
panel, diff/merge manual-edit escape hatch). lxml reparse attempted; on failure the Tier-1 fallback
(§8) shows the dialog + opens the raw file with the error line highlighted.

**Tier 2 — structural sanity (on-demand, low false positive)** — `validation/tier2.py`:
`validate_project(project)→list[ValidationIssue{severity, message, line}]` over `tree.getroot()` in
document order. Checks: (1) **duplicate top-level `Page@fileName` = ERROR** (direct `<Pages>` children
only, nested Detail pages excluded); (2) missing required attrs = WARNING (`Page` missing
fileName/tableName; `ColumnPresentation` missing fieldName); (3) unexpected container child = WARNING
(`<Pages>`→`<Page>`, `<Details>`→`<Detail>`, `<ColumnPresentations>`→`<ColumnPresentation>`). Wired to
Tools ▸ Validate Project → Audit panel with `"[Validate] SEVERITY line N: message"` items (line on
`UserRole`, click navigates). Out of scope: deep referential integrity, full whitelist enforcement.

---

## 17. Database

Validate a `.pgtp` against a live PostgreSQL DB, reconcile by renaming, and synthesize new elements from a
DB table. **The DB is the truth; the XML is the interface checked against it** — the two check *functions*
in `db/compare.py` remain (they compute the two halves of the picture), but the **UI has no direction
choice**: both halves are presented together per relation in the single Database/XML Coherence view below.
All logic Qt-free in `db/`.

**Transport:** `psycopg` v3 (`psycopg[binary]`), no external `psql`. Connection seeded from XML
`<ConnectionOptions>` (design-time, **not** `<ScriptConnectionOptions>`) — host/port/database/`login`→user;
the **password is never read from XML** (obfuscated there) — entered by the user and persisted
**plaintext** to injectable `self._settings` (caveat shown in the dialog). Introspection uses
`pg_catalog` (not `information_schema`): `relkind IN (r,p,v,m)`, columns via `format_type` + `attnotnull`
+ `pg_get_expr`, PK/FK via `pg_constraint`.

- `db/config.py`: `ConnectionParams(host, port, database, user, password)` with `redacted()`
  (password→`***`); `connection_from_tree` (password `""`); `load_connection`/`save_connection`;
  `seed_params`. **Not Qt-free** — it imports `QtCore.QSettings` at module scope, the one stated
  exception to §5's `db/` rule. Today it hardcodes a single QSettings group, `_GROUP = "db"`.

**Connection profiles — one keying scheme for both dimensions (target design, §18.2 + §18.5).** §18.2
needs a **per-project** key; §18.5 D2 needs a **profile role** (`target` | `sandbox`). These land as
*one* mechanism, never two:

| Piece | Contract |
|---|---|
| `ProfileKey(project: str = "", role: str = "target")` (frozen dataclass), `DEFAULT_PROFILE = ProfileKey()` | The single key type. Both dimensions, one value. |
| `_group_for(key) -> str` | `key == DEFAULT_PROFILE` → **the literal string `"db"`**, byte for byte the existing group. Otherwise `"db_profiles/<slug(project)>/<role>"`, where `slug` = `sha1(path.casefold())[:16]` (`""` → `"_global"`) because a QSettings group name cannot contain `/` or `\`. |
| `load_connection(settings, key=DEFAULT_PROFILE)`, `save_connection(settings, params, key=DEFAULT_PROFILE)`, `seed_params(tree, settings, key=DEFAULT_PROFILE)` | A **trailing defaulted** parameter on each; every existing call site keeps working unchanged. |

- **The compatibility trick is load-bearing and must be preserved:** routing the default profile back to
  the *same* `"db"` group means existing users' saved connections are **not migrated at all** — there is
  nothing to migrate, nothing to get wrong, and an older build still reads them. **Every existing test in
  `tests/db/test_config.py` (9 as of 2026-08-02) must pass unedited**; that is itself the compatibility
  proof, and new tests may only be *added*. This is why the scheme beats read-fallback-plus-dual-write.
- **`seed_params` for a `role="sandbox"` key must NOT fall back to the project's `<ConnectionOptions>`.**
  That element describes the **target** database; seeding the sandbox profile from it is exactly how
  someone ends up pointing "the sandbox" at production. Sandbox seeding = saved settings only, else
  blanks with a `localhost`/`5432` default.
- Loaders keep the existing contract: an absent or garbage group returns `None` and **never raises**.
- Two profiles means **two plaintext passwords** in QSettings — the existing plaintext caveat label must
  be shown for the sandbox profile too, and a *superuser* sandbox password (needed for one-click
  `CREATE EXTENSION`, §18.5) is a trade the user must be shown, not assumed to have accepted.
- `db/introspect.py` (psycopg lazily imported): `ColumnInfo(name, data_type, is_pk, is_fk, is_nullable,
  default, fk_target)`; `TableInfo(name, kind(table|view|matview), columns)`; `DatabaseSchema.tables`
  keyed schema-qualified (`pr.equipment`). `run_queries(params, sql)` is the **only** connection-opening
  fn; `fetch_schema`/`test_connection` take `runner=` for fakes. `test_connection` runs `SELECT 1`,
  returns `(ok, message)`, never raises.
- `db/compare.py` (pure): `check_xml_against_db` (XML→DB) and `check_db_against_xml` (DB→XML) →
  `TableCheck{name, ok, kind, invocations, columns:[ColumnCheck], page_count=0, detail_count=0,
  lookup_count=0}`; reuses `analysis/reused_tables.py` traversal. **Role-split reference counts and the
  DB→XML mismatch rule** (BUG-026, 2026-08-05): `xml_table_role_counts(project) -> dict[str, dict[str,
  int]]` maps `tableName` → `{"page": n, "detail": n, "lookup": n}`, derived from the **same**
  `collect_table_usages` walk as the aggregate `xml_table_invocations` (kept for back-compat) by tallying
  each `TableReference.kind` — `"page"`/`"detail"` are table bindings and `"column"` is by construction a
  column **lookup** (`visit_columns` emits a column reference only when `column.lookup` carries a
  `tableName`). `check_db_against_xml` populates the three counts from it and computes
  **`ok = (page_count + detail_count + lookup_count) > 0`** — *referenced in **any** role* — replacing the
  earlier `table_name in columns_by_table`, which consulted only `xml_table_columns` (page/detail bindings
  only) and therefore marked a **lookup-only table a red mismatch while simultaneously showing it a
  nonzero invocation count**. `xml_table_columns`/`columns_by_table` are untouched and still drive the
  per-column present/absent check — a lookup-only table legitimately shows all-absent columns, which is
  informational, not a mismatch. `ok` stays the **single** mismatch signal: the panel's red styling, its
  header mismatch count, its "Show only mismatches" filter and the UserRole tuple all key off it, and no
  second "role counts" flag is introduced. `ColumnCheck{name, ok, info: ColumnInfo|None = None, is_calculated: bool = False}` —
  `is_calculated` (last, defaulted, so `check_db_against_xml`'s constructions need no change) carries
  the XML-side `isCalculated="true"` flag via `ColumnNode.is_calculated` (§6). `xml_table_columns`
  returns `dict[str, dict[str, bool]]` (`tableName` → `fieldName` → is_calculated), **OR-unioned**
  across pages/details bound to the same table (calculated anywhere it appears → calculated); name
  membership (`in`) still works for callers needing only the field-name set. `ok` deliberately stays
  "does a matching DB column literally exist" (informational — a calculated column can shadow a real
  DB column, yielding `ok=True` **and** `is_calculated=True`); consumers treat `is_calculated` as
  **overriding** `ok` for mismatch display/counting. `check_db_against_xml` is unchanged
  (membership-only use of `xml_table_columns`).
- `db/rename.py` (pure): `rename_field(text, old, new)` / `rename_table(...)` = literal global
  attribute replace.

**UI:** **Database** menu (Connection Setup…, the checkable **Database/XML Coherence** toggle — one entry,
replacing the two former "Check: XML→Database" / "Check: Database→XML" items, see the coherence view
below — and, after a separator, the checkable **DDL Explorer** toggle, §18.1). **Connection Setup… is projectless-mode
only** (BUG-024, 2026-08-05, §18): while a §18.2 local project is open, its own `ProjectSettings`
(`target`/`sandbox`) is the connection store, and the app-level profile this dialog edits would be a
redundant, silently-live shadow of it. `MainWindow` gates this with `self._connection_setup_action`,
stored on `self` (not a bare local) so `_refresh_project_dependent_actions()` — called from both
`_set_active_ddl_project` and `_close_ddl_project` — can flip `setEnabled(self._ddl_project_folder is
None)` on every project open/close transition; `_open_connection_setup()` itself also early-returns (no
dialog, a status-bar hint pointing at Project Settings) when a project is active, since two internal
callers — `_run_db_check`/`_open_ddl_explorer`'s shared `_prompt_missing_connection()` fallback — invoke
it directly on a missing connection and must be rerouted to **Project Settings…** instead while a project
is open, rather than opening the now-meaningless standalone dialog.
`ConnectionSetupDialog` (host/port/database/user, password EchoMode.Password, Test + status, plaintext
caveat; API `set_params`/`params()`/`test()`).

### The Database/XML Coherence view

> **Implemented and shipped, FQ-003, 2026-08-06** (`db/coherence.py::build_coherence_tree`,
> `ui/coherence_panel.py::CoherencePanel`, the hidden `left_tabs` "Database/XML Coherence" tab and the
> checkable Database-menu toggle `MainWindow._coherence_action`; results are project-tied and cleared on
> project close, BUG-011). It replaces **three** shipped left-dock
> surfaces with one: the XML→Database check, the Database→XML check (both `ui/db_check_panel.py`'s
> `DbCheckPanel` behind two Database-menu items) and the standalone "Table references" tab
> (`ui/table_references_panel.py::TableReferencesPanel`, formerly §15). All three already sit on the
> **same** data layer — `analysis/reused_tables.py::collect_table_usages` feeds `db/compare.py`'s two
> check functions (via `xml_table_invocations`/`xml_table_role_counts`) *and* the references panel — so
> only the presentation was triplicated. Ledger §28, 2026-08-06 (two rows).

**Framing (the invariant the whole view is built on): the database is always the truth; the XML is the
interface being checked against it.** Anything the XML references that the DB does not have is an error
(a renamed table, a dropped table, a typo) — the app will not work. Conversely, finding *where* a DB
relation plays in the XML is a first-class question, not a separate tool.

**One panel, one hidden `left_tabs` tab, one checkable Database-menu toggle** (§26). Two top-level
branches over one data source (`collect_table_usages` + `db/compare.py`'s DB-augmented layer):

**1. "Tables and Views" branch — DB-sourced.** Rooted in the live DB relation list. **Tables and views are
treated identically**: `db/introspect.py` already fetches both the same way (`relkind IN ('r','p','v','m')`,
`TableInfo.kind ∈ {table, view, matview}`) and neither `compare.py` nor `reused_tables.py` applies
kind-based filtering, so **no new special-casing for views is introduced**. Per relation, two
sub-sections:
- **Database columns** — today's per-column check list (`ColumnCheck`: DB type, nullable, PK underline,
  `(fk)`). The shipped three-way glyph/color convention carries over unchanged: calculated
  (`ColumnCheck.is_calculated`) → orange `~` (`_CALC_COLOR = QColor("#d08a1a")`); else `ok` → green ✓
  (`_OK_COLOR`); else red ✗ (`_BAD_COLOR`). **Calculated columns are shown but never flagged** (BUG-006)
  — they are intentionally DB-less by design, excluded from the mismatch count and from the mismatch
  filter, and rename stays gated off for them.
- **References** — the former Table-References content for that relation, **badge-summarized from the
  existing `TableCheck.page_count` / `.detail_count` / `.lookup_count` rollups** (BUG-026, `db/compare.py`)
  rather than from any new counting pass, and **expandable** to the full breadcrumb list the
  `TableReferencesPanel` shows today (`TableUsage.references: list[TableReference]`). The role-split
  rendering `(P{page_count} D{detail_count} L{lookup_count})` introduced by BUG-026 is retained as the
  relation-level badge (the aggregate `(×N)` form, which existed only for the XML→DB direction, goes away
  with the direction toggle).
- This branch stays **purely DB-sourced**: a name that exists only in the XML gets **no synthetic phantom
  row** here (see the mismatch toggle below).

**The direction toggle is eliminated, not merged.** Once DB state and XML state are displayed *together*
per relation, there is no remaining framing choice about which side is "ground truth for display" — the DB
always is. The two Database-menu direction items were an artifact of showing only one side at a time; the
merged view therefore has one entry point and no direction control anywhere in its UI or its caches.

**2. "Pages" branch — XML-sourced, a RECURSIVE tree mirroring the real XML structure, not a fixed depth.**
Each Page node shows its own bound table (if any) and its own lookup columns, then nests its child Details
the same way — each Detail carrying its own bound table, its own lookup columns and its own further nested
Details — **recursing to whatever depth the XML actually has**. This is exactly the shape
`reused_tables.py::visit_detail` already walks (a `<Detail>` may contain child `<Detail>`s at unlimited
depth). **The UI must NOT flatten this into an assumed "Page > Details > Detail > Lookups" fixed-depth
shape.** A **"lookup with insert"** badge is rendered wherever `TableReference.ref_type == "lookup with
insert"` (a `<Lookup>` carrying an `<OnTheFlyInsertPage>` child, `_lookup_ref_type`) — this distinction is
visible in today's breadcrumbs and must survive as a badge, never collapsed into a generic "lookup" label.

**3. Mismatch toggle — one global control filtering *both* branches** down to only the nodes needing
attention. Settled semantics:

| Where | Flagged when |
|---|---|
| Pages branch (node level) | The Page/Detail/Lookup's target table/view name **does not exist in the live DB at all** — flagged red **at that exact reference point**. This is where a renamed/dropped table surfaces; explicitly **not** as a phantom entry under Tables and Views. |
| Tables and Views (relation level) | A real DB relation with `page_count == detail_count == lookup_count == 0` — referenced nowhere in the XML in any role. Requester-confirmed: *"if neither Page, nor Detail nor Lookup is there, flag it. Probably needs attention."* |
| Tables and Views (column level) | `ColumnCheck.ok == False`, **excluding** `is_calculated` columns. |

The toggle is deliberately **"things needing attention," not strictly "things that are broken"** — an
unreferenced DB relation is not a coherence error in the same sense as a dangling XML reference, and is
still surfaced on purpose. **No mismatch-type enum exists today**: mismatches are derived ad hoc from
`ColumnCheck.ok` + `TableCheck.kind` (`None` = missing in DB) + the role counts, so the toggle needs its
own filter predicate spanning both branches — nothing pre-packaged covers it.

**Reuse mandate (binding on the implementer).** `analysis/reused_tables.py::collect_table_usages` is reused
**wholesale** — the page/detail/lookup walk is not reimplemented — and the existing `TableCheck` /
`ColumnCheck` rollup fields (`page_count` / `detail_count` / `lookup_count` / `is_calculated` / `ok`) are
the only counting logic; **no parallel counters.** `TableCheck.ok` remains the single table-level mismatch
signal, `ColumnCheck.ok` the single column-level one. Carried over from `DbCheckPanel` unchanged: the
header (`user@host:port/db` + mismatch count, minus the direction label), the `(T)`/`(V)`/`(M)` relation
prefixes, the uniform 4-tuple UserRole payload `(kind, name, ok, is_calculated)` on relation and column
items (relations always `False`), and the signals `rename_requested(kind, old)` (XML-side not-found,
non-calculated nodes) and `create_requested(kind, name)` (relation nodes → Create Page/Detail/Lookup,
below). The jump gesture is **two** signals as shipped (`coherence_panel.py`): a line-only
`jump_requested(object)` (1-based line or `None`; double-click on an **XML-sourced** row → reveal Raw XML
+ `navigate_to_line`, the mechanism `TableReferencesPanel` already used) plus
`name_jump_requested(kind: str, name: str)` (double-click on a **DB-sourced** relation/column
row). `selection_changed(node, kind)` → Properties keeps its
existing semantic that a lookup reference targets its **owning `ColumnNode`**.

**Left open as implementation detail, deliberately not invented here:** the exact tree-widget structure,
whether "Tables and Views" and "Pages" are two sub-tabs or two top-level roots in one widget, and the menu
action's final wording/placement. Behavior above is binding; those are not.

**Rejected alternatives (recorded so they are not re-litigated).**
1. *A connection-optional hybrid* keeping Table References a separate panel with only a cross-navigation
   link into DB Check. Superseded once the requester clarified that the motivation is **architectural** —
   three near-duplicate presentations of one DB-truth-vs-XML-interface question — not a UI-convenience
   link. The full merge was chosen.
2. *§18.3's precedent of rejecting a unified Compare/Deploy screen* was raised as a caution and
   **explicitly distinguished, not silently re-decided.** That rejection turned on **risk asymmetry**:
   Compare is read-only, Deploy is destructive, and merging them would dilute Deploy's guardrails. Both
   surfaces merged here are **read-only diagnostics with no write path**, so the asymmetry that drove
   §18.3's rejection does not exist and does not block this merge.

**Reparse refreshes an open coherence view** against the **cached schema** (`_last_db_schema` /
`_last_db_summary`), no live re-query — via `_populate_db_check(...)` and `_refresh_db_check_if_open()`
(guarded on tab visibility + valid buffer). The former `_last_db_check_direction` cache **disappears with
the direction toggle**.

**Coherence results are project-tied and torn down on project close (BUG-011).** `_close_project`, on the
**committed-close path only**, hides the view's `left_tabs` tab and clears the cached fields
(`_last_db_schema` / `_last_db_summary` → `None`), so a later reparse or rename cannot re-run against the
closed project's stale state. A **cancelled** close returns before this and leaves the still-open project's
tab alone; `_revert_project` keeps the project loaded and so does not tear down.

**Create Page/Detail/Lookup from a DB table** (`generation/type_map.py` + `generation/from_table.py`,
pure): right-click a table/view node in the coherence view's **Tables and Views** branch → **create page** (insert before `</Pages>`, jump +
select), **create detail** (copy `<Detail>` to clipboard), **create lookup** (copy `<Lookup/>` to
clipboard). Aims at full PHP-Generator new-table parity via `type_map` (single source of parity truth,
keyed on normalized pg type: numeric/char/text/boolean/date/timestamp families → presentation +
`Format`/`EditProperties`/filterOps rules) + `PAGE_DEFAULTS` (recordsPerPage=20, editAbilityMode=3,
export/print flags, contentEncoding=UTF-8, …). Page emits `<ColumnPresentations>` + all 10 `<Columns>`
representations (PK cols hidden in Edit/Insert/Compare/MultiEdit). FK inference: exactly one child FK →
use it, else empty placeholders. **The vendor misspelling `foreginColumnName` is reproduced verbatim.**
`ColumnInfo.fk_target` = `"schema.table.column"` via `pg_constraint`. Parity is calibrated against a
golden "freshly-added table" oracle; defaults are corpus-derived and **not yet fully vendor-confirmed**.

---

## 18. DDL versioning (standalone Postgres mode)

> **Status (audited against the code 2026-08-06): §18.1, §18.2, §18.4, §18.6 and §18.8 ship; §18.3 and
> §18.5 are partly built; §18.7 is untouched design.** Per subsection, and each subsection's own status
> block is the detail:
>
> | Subsection | State |
> |---|---|
> | 18.1 Browsing (DDL Explorer) | **Implemented**, including FQ-002 object *creation*. XML cross-refs: the pure layer (`db/routine_refs.py`) shipped; its UI consumer is the remaining gap. |
> | 18.2 Projects, checkout, markers | **Implemented** (git remains an explicit TBD placeholder). |
> | 18.3 Deploy workflow & schema diff | **Pieces implemented, flow absent.** `db/schema_diff.py`, `db/migration_gen.py`, `db/schema_snapshot.py`, `db/deploy_bundle.py`, `ui/schema_compare_panel.py` all exist and are tested; **nothing reaches any of them** — no menu entries, no caller. |
> | 18.4 Selection formatter | **Implemented, core + consumer** (`Ctrl+Alt+F` / context menu in the §18.5 tab, `[SQL]` Audit refusals wired). |
> | 18.5 DDL object editor / apply / sandbox | **Partly implemented.** The editable tab ships, and so do the tab's **Apply to Sandbox / Apply to Target / "Deploy this edit…"** gestures (`ui/ddl_object_editor.py`, all four Apply-to-Target preconditions enforced), the complete Qt-free sandbox layer (`db/sandbox.py`) and its lifecycle host (`ui/sandbox_controller.py`). Still absent: `db/apply.py`, `db/ddl_check.py`'s ladder (so the `[Check]` findings channel, D3a), `db/sandbox_query.py` + the D4 SQL console, the MainWindow wiring that hands the controller's operations to the panel's apply seams, and the deployment-script generation. |
> | 18.6 Ctrl+Space completion | **Implemented.** |
> | 18.7 Two DDL Explorer instances | **Not implemented** — still exactly one `BrowserPanel`, one dock tab, one connection. |
> | 18.8 Project Status window | **Implemented** (Database ▸ Project Status…), with two deliberately withheld buttons and one flagged placeholder — see §18.8. |
>
> §18.1 shipped exactly as specified below: `RoutineInfo`/`TriggerInfo`/
> `DatabaseSchema.routines`/`.triggers` (`db/introspect.py`), `db/ddl_buffer.py`/`DdlObjectSpan`,
> `ui/ddl_buffer_panel.py::BrowserPanel`, `ui/ddl_editor_panel.py::EditorPanel` (the CenterStage
> "DDL Explorer" tab), the `language="sql"` highlighter mode in `ui/code_editor.py` (§8), the
> Database-menu "DDL Explorer" checkable toggle, and the full main-window wiring (hidden left-dock
> "DDL Objects" tab, `navigate_requested` navigation, async fetch).
>
> **The 2026-08-01 §18.1 enhancement batch is also implemented and verified** (it was specified here
> ahead of implementation and has now landed): (a) editor affordances on the DDL `EditorPanel` — the
> line-number gutter, line bookmarks and code folding, via the **shared `GutterBookmarkFoldMixin` in the
> new module `ui/editor_gutter.py`** with its pluggable foldable-region provider (§8); (b) the
> **4-character** tab stop; (c) the revised BrowserPanel tree presentation — fully-qualified
> `schema.name`, the three-way `[F]`/`[P]`/`[T]` marker, per-argument `name (type)` children (backed by
> the new `RoutineInfo.args`), and composite trigger leaves with bracketed timing/event indicators; and
> (d) **top-aligned** DDL navigation. See the Supersession Ledger (§28) for each override.
>
> §18.1's XML cross-referencing has its **pure layer shipped** (`db/routine_refs.py`, commit `956e8fb`,
> tested); **the remaining §18.1 piece is its UI consumer** — nothing in `ui/` calls the module yet.
> §18.1's FQ-002 object-*creation* entry points (Add Trigger…, New Function/Procedure…) **have
> since shipped** — see that subsection.
>
> **§18.3's modules all exist; nothing calls them.** `db/schema_diff.py` and `db/migration_gen.py` are
> implemented and tested (`tests/db/test_schema_diff.py`) for the `routine`/`trigger` cases only;
> `table`/`column` differences are deliberately unsupported (`SchemaDiffResult.unsupported` names the
> tables a diff did not compare; `migration_gen.generate_migration` raises `UnsupportedDifference` rather
> than silently omitting a table/column change from the script). `db/schema_snapshot.py`,
> `db/deploy_bundle.py` and `ui/schema_compare_panel.py` have since landed too. What is **still missing is
> the workflow**: no `Database ▸ "Compare Schemas…"` / `"Save Schema Snapshot…"` menu entries exist, and
> nothing drives a batch through review → git → execute. See §18.3.
>
> **§18.4's SQL/plpgsql selection formatter is implemented end to end — core *and* consumer.** The Qt-free
> package `pgtp_editor/sql/` (`__init__.py`/`keywords.py`/`issues.py`/`tokenizer.py`/`formatter.py`,
> plus `caret_context.py` for §18.6) and its mirror `tests/sql/` are green, and `format_selection` **is
> called**: `ui/ddl_object_editor.py::DdlObjectEditorPanel.format_selection`, bound to **`Ctrl+Alt+F`**
> and a context-menu **"Format Selection"** item (both gated on a selection), with refusals emitted to the
> Audit panel under the **`[SQL]`** prefix (`MainWindow`'s `[SQL]` handler).
>
> **§18.5 is partly implemented.** The editable tab exists and works —
> `ui/ddl_object_editor.py::DdlObjectEditorPanel`/`DdlObjectRef`, opened by key through
> `CenterStage.open_ddl_object_tab`, with Save/Save As over the injected `resolve_save_path` seam,
> Format Selection, and §18.6 completion — and so do the **Apply to Sandbox / Apply to Target /
> "Deploy this edit…"** gestures on it, the **whole Qt-free sandbox layer** (`db/sandbox.py`:
> `SandboxSession`, `open_sandbox`'s ownership gate, `provision_sandbox`, `clone_data`,
> `install_plpgsql_check`, the `SandboxExecutor` seam) and its UI host `ui/sandbox_controller.py`.
> **What does not exist is the validate/execute half**: `db/apply.py` (the codebase's would-be **first DB
> write path**), `db/ddl_check.py`'s validation ladder and its `[Check]` findings channel (D3/D3a),
> `db/sandbox_query.py` + the **Sandbox SQL Console** (D4), the MainWindow wiring that binds the
> controller's session to the panel's apply seams (so the affordances are absent in the running app), and
> the deployment-script generation. The
> ladder, when built, must reuse the **already-landed** `db/schema_diff.py`/`db/migration_gen.py` (§18.3)
> rather than building them again. The tab is
> deliberately **decoupled from §18.2's git project for v1** — no
> `ddl/` folder, no `deployed.json`, no `*`/`!` markers — and is written against an **injected load/save
> pair** so §18.2 layers on later by swapping only where the buffer loads from and saves to.
> **§18.5's headline deliverable is the generated deployment SQL script**, not the editable tab: the
> sandbox is the *desired state*, production is the *current state*, and the output is one reviewed
> migration script run once to upgrade the real database. See §18.5's ranked outputs.

**Strategic framing.** This is **not** a feature bolted onto `.pgtp` editing — it is a standalone
Postgres DDL-versioning mode, independent of phpgen/`.pgtp` entirely, usable with zero `.pgtp` files
involved (§1). The project owner explicitly considered and **rejected** the `re_phpgen` precedent
(§20/§20.4 — the one place in this codebase where genuinely independent tooling was split into a
**separate repo**, invoked as a subprocess) for this workflow: DDL versioning stays **in the same app,
as an independent mode**, directly sharing the app's existing DB connection (§17), code editor
(`ui/code_editor.py::CodeEditor`, §8), and diff infrastructure (§12) — deliberately no
subprocess/repo split. Consequently this section was pulled out of §17 as its own top-level section
rather than left as a `§17.x` subsection: it broadens the app's stated purpose (§1), not just its
Database menu. Generic DB introspection primitives it depends on (`RoutineInfo`/`TriggerInfo`/
`DatabaseSchema.routines`/`.triggers`, §17) stay in §17, reused by both the pre-existing DB-check
features and this workflow.

Five parts. **Section order is not build order** — the numbering is historical and other documents
reference it, so it is kept stable:

| Part | Scope | Depends on |
|---|---|---|
| **§18.1** | Browses live routines/triggers in one synthesized read-only buffer (unchanged in shape from the original DDL Explorer design) | — (implemented) |
| **§18.5** | The **stateful sandbox as desired state**, the **generated deployment SQL script** (its headline deliverable), the validation ladder, and the **editable single-object DDL tab** (`ui/ddl_object_editor.py::DdlObjectEditorPanel`) with its Save/Apply gestures. **The editable tab is specified here and only here.** | §18.1 only — explicitly buildable **before** §18.2/§18.3 |
| **§18.2** | The "project" concept (a local folder — git optional/TBD, not the definition of a project, see below), `ddl/*.sql` file-per-object, `.ddlproject/settings.json`, checkout-to-edit, and the `*`/`!` state markers. Adds **no new tab type**: it swaps §18.5's tab's injected load/save pair and adds marker rendering. | §18.1, §18.5 |
| **§18.3** | The reviewed **batch** deploy workflow, reusing §18.1's browsing UI and the shared diff/migration engine originally specified as a schema-compare-only tool | §18.2 |
| **§18.4** | The Qt-free SQL/plpgsql selection formatter core (implemented), whose one host surface is §18.5's tab | §18.5 for its consumer |

**Build order is therefore §18.1 → §18.5 → §18.2 → §18.3.** §18.5 was deliberately re-scoped to sit
before §18.2: a git project, a manifest, a hash scheme and a marker recompute is a large prerequisite to
place in front of "edit one function and find out whether it compiles" (§18.5 D1, §28).

**Truth model (first-class design principle, not an implementation footnote): the database is the
sole source of truth; git is a history/audit log only, never authoritative for "current state."**
Owner's framing, preserved close to verbatim: *"the only source of truth in our projects is production
database DDL, production pgtp and production phps. Everything else is just a snapshot, approximation,
history."* Consequence, stated explicitly: on every project load (§18.2), the tool re-verifies every
local `ddl/` file (and, as of the 2026-08-03 revision below, the local `.pgtp` working copy) against the
live DB / the sshfs-mounted source `.pgtp` by fresh comparison — it never trusts git history, or any
cached/prior-session state, as representing current state. State markers (§18.2) are recomputed fresh on
every load, not persisted/cached across sessions.

> **Governing principle, stated once here because it now justifies choices across §18.2/§18.3/§18.5:
> "nothing the app manages should be a black box — plaintext files everywhere."** This is the same
> spirit that already justified `ddl/*.sql` being plain per-object files rather than one opaque buffer;
> §18.2's 2026-08-03 revision extends it to the project's own settings (one plaintext JSON, including the
> password, deliberately not routed through a binary/opaque app-global store) and to git itself, which is
> optional and — when configured — a transparent, inspectable layer on top of plain files, never a
> database the app hides state inside.

**Local project vs. git — settled 2026-08-03, superseding this section's earlier "project = git repo"
framing (§18.2, §28).** A **local project is a folder the user chooses on their own machine — not
necessarily a git repository.** Git is an **optional, deferred (TBD) configuration** a project may
eventually carry, never the definition of what a project *is*. See §18.2 for the full revision.

**Three operating modes — the taxonomy that organizes everything below (settled 2026-08-05, reframe of
material already designed in §18.2/§18.5 D2/§18.7, not a new capability).** The app never asks the user to
declare which mode they are in; the mode is a **consequence** of (a) whether a local project is open and
(b) whether that project's environment satisfies the sandbox requirements below. Read this table before
§18.2 onward — every subsection's scope is one of these three tiers, and "sandbox" is **not** a bare
per-project settings toggle: it is an **environment-capability-gated** tier, present only when the
project's own machine can actually run one (see the capability check below).

| # | Mode | What is active | Requires |
|---|---|---|---|
| **1** | **Standalone** | No project open. DDL Explorer (§18.1) is browsable — **read-only, permanently** — against any configured connection. No checkout, no editing beyond the read-only buffer, no linting, no deploy. **Database ▸ Connection Setup… is available only in this mode** (BUG-024, below). | A configured DB connection only — zero `.pgtp` files, zero local projects (§18.1's existing "standalone-mode friendly" framing, unchanged) |
| **2** | **Quality project** | A local project (§18.2) with **no working sandbox** — either the user never configured one, or the local machine doesn't meet the sandbox requirements below (graceful degradation, not an error). Gets: DDL editing (§18.5's object tab), local **Save** + §18.3's batch `deploy.sql` assembly, and **Apply to Target** (direct, confirm-gated deploy to the quality/target database). | A local project folder (§18.2); a `target` connection profile |
| **3** | **Development project** | A quality project **plus** a working local sandbox: reachable local Postgres, a schema (optionally with data, §18.5 D2a) cloned into it. Gets **everything in quality project mode, plus**: `plpgsql_check` linting (D3 tier 3), `SET plpgsql.extra_warnings` linting (D3 tier 1), sandbox-execution linting (D3 tier 2 — compiles/applies against the sandbox), **ad-hoc SQL execution against the sandbox with a visible result set** (§18.5 D4's Sandbox SQL Console — *running* a routine and seeing what it did, settled 2026-08-06, previously the open item), **Apply to Sandbox**, the sandbox-scoped second DDL Explorer instance (§18.7), and **Generate Deployment SQL** (§18.5's headline deliverable, which needs the sandbox as its desired-state source). | Everything in tier 2, **plus** a reachable local Postgres superuser connection (§18.2's New Project Test button) |

- **Tier 1 already matches shipped behavior** (§18.1's "Editing is deliberately NOT hosted here" /
  `EditorPanel` stays read-only permanently) — naming it "standalone" here is a label on existing design,
  not a change to it.
- **Tier 2 vs. tier 3 is not a user toggle — it is what the environment can support.** A project's owner
  may *intend* a development setup (they configured a sandbox connection in New Project) and still land in
  tier 2 at any given moment if the sandbox connection stops resolving, the machine doesn't have Postgres
  reachable, or the sandbox database was destroyed — the app does not error in that case, it simply
  operates as a quality project until the sandbox is reachable again. This is the same embrace-drift,
  surface-don't-force posture as the `*`/`!` markers.
- **`psql`/`pg_restore` are NOT a tier-3 prerequisite in general — only for the "with data" sandbox
  variant.** Verified against D2/D2a's actual mechanism: the schema-only baseline (`build_baseline_sql`,
  D2's default and the one that unlocks tiers 1–3 of the validation ladder) is **in-process `psycopg`
  only** — zero bundled bytes, zero external processes, per D2's "zero bundled bytes" invariant. `pg_dump`/
  `pg_restore` on `PATH` are required **only** by D2a's optional "with data" clone mode, which is a
  narrowly-scoped, explicitly-named exception layered on top of the schema-only path, not a general
  sandbox requirement. A development project with reachable Postgres and no `pg_dump`/`pg_restore` on
  `PATH` is still a fully-capable development project (schema-only sandbox); it only loses access to the
  "with data" cloning choice at New Project time.
- **Probe timing — settled 2026-08-05.** The environment-capability check (reachable local Postgres via
  §18.5 D2's `SandboxCapabilities.probe`, reused from §18.2's New Project Test button; plus `psql`/
  `pg_restore`-on-`PATH`, relevant only to D2a's "with data" clone path) runs **automatically whenever a
  project is opened**, and **on demand** whenever the **Project Status window (§18.8)** is brought up. It
  is not probed-once-and-cached from creation time: a sandbox that has died between sessions is detected
  at the next project open and correctly degrades the project from tier 3 to tier 2 for that session.
- **Capability display — settled design, §18.8.** The tier the project is currently running in (quality
  vs. development) and, if degraded, why (e.g. "sandbox unavailable: pg_restore not found on PATH") is
  surfaced in the **Project Status window** — a small node-and-connector diagram of project health,
  fully specified in §18.8. See §18.8 for the design and §29 for the one remaining open question (each
  node's click-through action-window content).

### 18.1 Routines & triggers browsing (DDL Explorer)

Extends database introspection to routines and triggers, synthesizes them into one shared browsable
buffer (the same architecture the app already trusts for its main document), and cross-references them
into the XML. This subsection is the browsing substrate that §18.2's checkout-to-edit and §18.3's deploy
workflow both build on directly — it is not a separate, self-contained feature.

**Introspection (lives in §17, reused here) — implemented:**

- `db/introspect.py` has: `RoutineInfo{schema, name, arg_types: list[str], **args: list[tuple[str, str]]
  (input argument name+type pairs — IN/INOUT/VARIADIC — in declared order)**, return_type, language, source,
  kind("function"|"procedure")}` sourced from `pg_proc` joined `pg_language`, with source text
  via `pg_get_functiondef(oid)`. `arg_types` (types only) is **retained** — it still feeds
  `build_ddl_text`'s banner comment (`-- FUNCTION schema.name(argtypes) --`); the `args` field adds
  the **argument names** the BrowserPanel tree needs (see tree presentation below).
  `_ROUTINES_SQL` was widened to select, alongside the existing `proargtypes`-derived `arg_types`:
  `COALESCE(p.proallargtypes, p.proargtypes::oid[])` run through `format_type` (ordinality-preserved),
  `p.proargnames`, and `p.proargmodes::text[]`. Those three **parallel arrays are correlated in Python**
  by the pure helper `_input_args(all_arg_types, arg_names, arg_modes) -> list[tuple[str, str]]` —
  deliberately not in SQL, for the **same reason `_decode_trigger_type` is in Python: the correlation is
  unit-testable without a live database**. Rules: an absent/NULL `proargmodes` reads as all-IN (Postgres
  omits it in the common case); the kept modes are exactly the **arguments the caller passes in** —
  `_INPUT_ARG_MODES = frozenset("ibv")`, i.e. `i` (IN), `b` (INOUT) and `v` (**VARIADIC**) — while `o`
  (OUT) and `t` (TABLE) entries, which are outputs, are dropped. VARIADIC is kept deliberately: a
  variadic parameter is supplied by the caller, so excluding it silently hid a real parameter of e.g.
  `f(fixed int, VARIADIC rest text[])` from the tree.
  An unnamed argument yields `""` as its name; a routine with zero input arguments has
  `args == []`. `TriggerInfo{schema,
  table, name, timing, events: list[str],
  function_name, definition}` sourced from `pg_trigger` + `pg_get_triggerdef(oid)` (trigger
  timing/events decoded from the raw `pg_trigger.tgtype` bitmask by `_decode_trigger_type`, in Python
  rather than SQL, so the mapping is unit-testable without a live database). The `DatabaseSchema`
  dataclass (`db/introspect.py`) has `.routines` and `.triggers` fields alongside `.tables`
  (backward-compatible, all default to empty).
- Fetched by `fetch_routines_and_triggers(params, runner=run_queries) -> DatabaseSchema`
  (`ROUTINE_TRIGGER_SQL` = `[_ROUTINES_SQL, _TRIGGERS_SQL]`) — still a **separate fetch path from
  `fetch_schema`**, not merged into it (`fetch_schema`'s existing 3-query contract and its tests are
  untouched, and DB Check keeps calling `fetch_schema` on its own). **Superseded (§18.6, §28): the
  `DatabaseSchema` this returns is no longer table-empty.** `fetch_routines_and_triggers` is **widened**
  to also run `SCHEMA_SQL` (the same three queries `fetch_schema` runs) and populate `.tables`, so DDL
  Explorer's one connect-time fetch now returns routines, triggers **and** tables/columns in a single
  round trip — the source `db/schema_index.py` (§18.6) is built from. This is one fetch path serving two
  consumers (DDL Explorer and, unchanged, DB Check via its own `fetch_schema` call), never a second
  parallel fetch and never a lazy per-keystroke query.

**Overloaded routines are never collapsed — each overload is its own tree entry, its own
`DdlObjectSpan` and its own editable §18.5 tab (settled 2026-08-02; this *corrects shipped behavior*,
see §28).** Owner's framing: *"just let repeat overloaded functions to the tree, the dropdown will
anyhow show the difference, also the ddl is clearly different."* PostgreSQL identifies a routine by
**`(schema, name, argtypes)`** — the same load-bearing fact that drives §18.5's Apply-to-target
signature refusal and §18.5's `diff_schemas` routine identity — so routine identity must carry argument
types **everywhere in this pipeline, with no exceptions**:

| Place | Shipped today (defective) | Required |
|---|---|---|
| `db/introspect.py::fetch_routines_and_triggers` | `routines[f"{schema}.{name}"] = RoutineInfo(...)` — overloads **collapse last-wins**, so the DDL Explorer shows only one of N and silently drops the rest | key on `RoutineInfo.signature` — the `@property` that is the **single source** of the rendered `schema.name(argtypes)` string (`db/introspect.py`; consumed verbatim, never re-rendered) — so every overload survives the fetch and the same string backs `build_ddl_text`'s banner, `db/schema_diff.py::routine_identity`, and §18.2's filenames |
| `db/ddl_buffer.py::DdlObjectSpan` | `{kind, schema, name, table, start_line, end_line}` — carries **no** `arg_types`, so two overloads produce two indistinguishable spans | add `signature: str | None = None` (routines only, `None` for triggers; a trailing defaulted field so existing positional/keyword constructions stay valid), populated from `RoutineInfo.signature` |
| `db/ddl_buffer.py::build_ddl_text` ordering | sorts by `(schema, kind_rank, name)` | sorts by `(schema, kind_rank, name, arg_types)` (the tuple of argument *types*, not the rendered signature string) — a name tie between overloads must break **deterministically**, never on dict insertion order |
| `ui/ddl_buffer_panel.py::BrowserPanel.set_schema` | `span_by_routine[(span.schema, span.name)]` — last-wins again, one span silently wins for all overloads | `span_by_routine` keyed on the plain string `span.signature`, looked up with `routine.signature` |

- The tree therefore shows **N sibling routine nodes with the same `schema.name` top line**, one per
  overload, each with its own `name (type)` argument children (§18.1's tree presentation, unchanged) —
  which is exactly what tells them apart visually; the top-line label rule is **not** changed to
  re-introduce a parenthesised argument list. Sibling order between overloads is by `arg_types`
  (the same tiebreak as the buffer — the tuple of argument *types* used purely for ordering, not for
  identity/keying), so tree and buffer never disagree.
- A zero-argument routine and an overload set are not special-cased against each other: `f()` and
  `f(integer)` are two ordinary siblings, the first rendering its empty `()` per the existing rule.
- Each overload's tree row navigates to **its own** banner line, and right-click ▸ Edit… (§18.5) opens
  **one tab per overload**, keyed on `DdlObjectRef.key` (§18.5 — the hashable tuple
  `ui/ddl_object_editor.py` derives from the span's identity, which carries `DdlObjectSpan.signature` /
  `RoutineInfo.signature` for routines) — not on a bare `arg_types` tuple.

**One synthesized buffer, not per-object viewers — reuses the Raw XML editor's proven shape
(`TagSpan`/§8 + `node_at_line`/§9: one shared text buffer, a structural span index over it, and a tree
that navigates into it via line numbers) instead of opening a bespoke read-only viewer per routine or
trigger:**

- **Implemented:** pure module `db/ddl_buffer.py`: `build_ddl_text(schema: DatabaseSchema) → tuple[str,
  list[DdlObjectSpan]]`. Synthesizes **one** text buffer concatenating every routine and trigger
  definition, in deterministic order (schema, then kind — functions/procedures before triggers — then
  name, then `arg_types` so overloads order stably), each preceded by a banner comment anchoring its span (e.g.
  `-- FUNCTION public.foo(integer) --`). `DdlObjectSpan{kind: "function"|"procedure"|"trigger", schema,
  name, table: str|None (triggers only — the table it fires on), **`signature: str | None = None`**
  (routines only, populated from `RoutineInfo.signature`; `None` for triggers — required so overloads
  are distinguishable; see the overload rule above), start_line, end_line}` plays the same
  role for this buffer that `TagSpan` (§8, `ui/xml_structure.py`) plays for the Raw XML buffer and that
  `node_at_line` (§9, `model/line_index.py`) plays for click-to-tree sync.
- **Implemented:** CenterStage tab `ui/ddl_editor_panel.py::EditorPanel(QWidget)` hosts the
  synthesized buffer in the **existing** `ui/code_editor.py::CodeEditor` widget under its
  **`language="sql"` mode** — the SQL/plpgsql `_CodeHighlighter` branch (case-insensitive
  `_SQL_KEYWORDS` matching — the keyword set itself lives in the Qt-free `sql/keywords.py`, §18.4 —
  `--` line comments, `''`-doubled single-quote strings, `/* */` block
  comments) added alongside the existing JS/PHP ones in that same file (§8). Has its own
  `FindReplaceBar` instance, following the same per-tab document-routing precedent as the Edit XSD tab
  (§7/§15) and the planned Custom PHP tabs (§21). The tab sits in `CenterStage` between Edit XSD and
  Manual (`ddl_tab_index`, hidden by default — a fixed index that becomes a **role-keyed dynamic tab**
  per §18.7), and is **closable** via a tab-bar ✕ that hides it
  directly (`hide_ddl_explorer()`) — read-only, so unlike Edit XSD there is no dirty prompt to route
  through. `CenterStage` exposes `show_ddl_explorer()`/`hide_ddl_explorer()` and a
  `ddl_explorer_visibility_changed = Signal(bool)`. API: `EditorPanel.set_ddl_text(text, spans=None,
  schema=None)`
  (a fresh `build_ddl_text` result — text plus its `DdlObjectSpan` list, which drives the fold regions,
  below; the panel converts the spans to fold regions **and retains the list** as `self._spans` —
  §18.5's once-required amendment, **done** — because the right-click ▸
  Edit entry point resolves the clicked line to the object whose `start_line..end_line` contains it;
  the third parameter retains the live `DatabaseSchema` alongside, for that same edit resolution via
  `ddl_buffer_panel.resolve_edit_target`)
  and `EditorPanel.navigate_to_line(line)` (delegates to
  `CodeEditor.navigate_to_line`, §8, then focuses the editor). This tab is **read-only, DB-sourced,
  live/synthesized** (`editor.setReadOnly(True)`; `CodeEditor.replace_current_selection` no-ops on
  read-only editors, the guard that actually protects the buffer since `QTextCursor` edits bypass
  `setReadOnly`) — and it is read-only **permanently, not provisionally**. The editable form is a
  **separate tab type**, the per-object DDL object editor of §18.5 (loading from the live introspected
  definition in v1, from the checked-out `ddl/*.sql` file once §18.2 exists). Nothing is ever pushed to a
  database from `EditorPanel`.
- **Implemented — editor affordances (parity with the Raw XML editor's `XmlEditor`, via the shared
  mixin — §8):** the DDL `CodeEditor` carries the **same three affordances `XmlEditor` has**: (i) a
  **line-number gutter**, (ii) **line bookmarks**, and (iii) **code folding**, all from
  `ui/editor_gutter.py::GutterBookmarkFoldMixin` (see §8) — **one** gutter/bookmark/fold implementation
  used by both editors, never a second parallel gutter. The mixin supplies the generic,
  block-number-based gutter + bookmark set + fold-state machinery; the **foldable-region provider is
  pluggable**. For the DDL buffer the foldable regions are **one per DDL object body**:
  `ddl_editor_panel.py::_fold_regions_for_spans(spans)` (pure) translates each `DdlObjectSpan` into the
  triple `(start_line - 1, start_line, end_line - 1)` — fold triggered on the **banner** block,
  containing the **body only**, so the banner stays visible when collapsed; a span with
  `end_line <= start_line` contributes **no** region. `EditorPanel.set_ddl_text(text, spans=None, schema=None)` takes
  that span list alongside the text and installs the regions via `CodeEditor.set_fold_regions`; passing
  `None`/`[]` simply leaves nothing foldable. `XmlEditor` keeps its **XML-span** fold provider
  (`_foldable_region_starting_at` over `_spans`/`TagSpan`, §8).
- **Implemented — tab stop = 4 characters.** `CodeEditor` sets `setTabStopDistance(4 × mono-char
  advance)` (`_SQL_TAB_STOP_CHARS = 4`) when `language == "sql"`, overriding Qt's monospace default
  (~8–11 chars) so `pg_get_functiondef`'s tab-indented bodies read at a sane width.
- **Implemented — top-aligned navigation.** `EditorPanel.navigate_to_line(line)` scrolls so the target
  line lands at the **top** of the editor viewport (not centered) — the clicked DDL object's banner sits
  at the top edge, so the whole object is visible below it. This is **DDL-specific**: gated on
  `language == "sql"` inside `CodeEditor.navigate_to_line`, so JS/PHP `CodeEditor`s and
  `XmlEditor.navigate_to_line` all keep `centerCursor()` (Properties/tree-jump callers expect
  centering). See §8 for `_scroll_line_to_top`'s visible-block counting and scrollbar clamping.
- **Implemented:** left-dock tree tab `ui/ddl_buffer_panel.py::BrowserPanel(QWidget)` — a `QWidget`
  wrapping an internal `self.tree = QTreeWidget()` (composition), matching this codebase's real
  convention for left-dock panels (`TableReferencesPanel`, `DbCheckPanel` — both `QWidget` subclasses
  wrapping an internal tree), not literal `QTreeWidget` subclassing. Built from the `DdlObjectSpan`
  index via `set_schema(schema, spans)` — one shared buffer plus a structural tree index, the same
  relationship the Raw XML tree bears to `xml_editor.py`. Emits `navigate_requested(line: int)` on leaf
  click, wired in MainWindow to `_on_ddl_navigate_requested(line)` → activate the center DDL Explorer
  tab + `EditorPanel.navigate_to_line(line)`. Lives in a hidden `left_tabs` tab titled **"DDL
  Objects"** (`ddl_browser_tab_index`), revealed/hidden in lockstep with the center tab. This is the
  tree that §18.2's `*`/`!` state markers will render on.

**Dual-grouped, cross-referenced tree — a deliberate design choice by the project owner:** a trigger
appears in the tree in **both** of its relationship places, not just one:

- **Tables** (top-level group): each table lists the triggers defined on it (via `TriggerInfo.table`).
- **Functions & Procedures** (top-level group): each function/procedure additionally lists the triggers
  that invoke it (reverse reference via `TriggerInfo.function_name`).
- A trigger is therefore **two tree leaves pointing at the same underlying `DdlObjectSpan`** (same
  buffer location) — clicking either jumps to the identical line in the `EditorPanel` tab. This mirrors
  the table-references precedent (now §17's coherence view, `TableUsage.references`) of showing the same
  object from multiple relationship angles rather than forcing a single parent — it is **not** a novel
  pattern, it already exists elsewhere in the app.
- Click on any leaf in `BrowserPanel` (function, procedure, or either trigger occurrence) → reveal the
  `EditorPanel` tab + `navigate_to_line(span.start_line)`, reusing the existing navigation API already
  described in §8 ("Public navigation API") and used by Properties/captions/DB check/table
  references/diff. DDL navigation is **top-aligned** (the object's first line lands at the top of the
  viewport — see EditorPanel navigation below), not centered.

**Tree presentation (`BrowserPanel._build_routines_branch` / `_build_tables_branch` /
`_add_trigger_leaf`) — implemented; the exact rendered labels (both worked examples below are
test-asserted byte-for-byte):**

*Routine node (Functions & Procedures branch)* — top line = the **fully-qualified** name
`schema.name`, a **three-way** marker, and — only for a routine with **zero** input arguments — an empty
`()`:

| Kind | Marker | Condition |
|---|---|---|
| Procedure | `[P]` | `kind == "procedure"` |
| Trigger function | `[T]` | `kind == "function"` and `return_type == "trigger"` |
| Function | `[F]` | any other `kind == "function"` |

- A routine **with** input arguments (`args` non-empty) renders its top line as `schema.name [marker]`
  (**no** parenthesised argument list on the top line) and lists **one second-level child per input
  argument**, in declared order, labeled `name (type)`.
- A routine with **zero** input arguments (`args == []`) renders its top line as `schema.name() [marker]`
  (empty parens) and has **no** argument-child nodes.
- (Note: the top-line arg-list omission is a **tree-label** decision only; `build_ddl_text`'s banner
  comment in the buffer still carries the full `(argtypes)` from `arg_types` — §18.1 buffer, unchanged.)
- **Argument child leaves carry no span** (`_SPAN_ROLE` unset), so clicking one navigates nowhere —
  `_on_item_clicked` only emits `navigate_requested` when the clicked item has a span. Routine leaves
  and both trigger occurrences carry theirs.
- **Child order under a routine:** argument leaves first (declared order), then the triggers that invoke
  the routine, **sorted by trigger name**. Routines themselves are sorted by `(schema, name)`.

*Trigger leaf* — used in **both** the Tables branch and the Functions & Procedures branch — the label is
the **composite** name `schema.table.triggername` followed by a **timing indicator** then **one event
indicator per event**, each bracketed:

| Timing | Letter | | Event | Letter |
|---|---|---|---|---|
| before | `[B]` | | insert | `[I]` |
| after | `[A]` | | update | `[U]` |
| instead of | `[I]` | | delete | `[D]` |
| | | | truncate | `[T]` |

Events render in the introspected order of `TriggerInfo.events` (`_decode_trigger_type` yields
insert → update → delete → truncate order). Example: a `BEFORE DELETE` trigger → `[B][D]`; an
`AFTER INSERT OR UPDATE` trigger → `[A][I][U]`. (The timing letter `[I]` "instead of" and the event
letter `[I]` "insert" collide as glyphs but never within one label position — timing is always the
first bracket, events follow; the composite `schema.table.triggername` prefix disambiguates in
practice.)

**Worked examples (reproduce exactly):**

Regular function with args — `CREATE OR REPLACE FUNCTION public.get_working_days_in_month(year integer,
month integer) RETURNS integer`:

```
public.get_working_days_in_month [F]
├─ year (integer)
└─ month (integer)
```

Trigger function (no args, `RETURNS trigger`) plus its trigger — `CREATE OR REPLACE FUNCTION
public.dont_delete_standards() RETURNS trigger` and `CREATE TRIGGER dont_delete_model_users BEFORE
DELETE ON public.phpgen_users FOR EACH ROW EXECUTE FUNCTION dont_delete_standards()`:

```
public.dont_delete_standards() [T]
└─ public.phpgen_users.dont_delete_model_users [B][D]
```

**XML cross-references — a third relationship angle. The pure layer shipped (`db/routine_refs.py`,
commit `956e8fb`, tested); the UI consumer is the remaining §18.1 gap — nothing in `ui/` calls it yet:**

- `db/routine_refs.py` (Qt-free, psycopg-free, I/O-free): cross-references routine/trigger names against
  the XML (event-handler bodies via `EventNode.text`, and **every** attribute value — deliberately not a
  hard-coded "SQL-bearing" attribute list, which would silently miss whichever attribute a project
  actually keeps its SQL in; the call-shaped match requirement below is what rejects prose) via
  **best-effort name matching** — same "no false confidence" ethos as `analysis/reused_tables.py` — so a
  DB-side routine can be traced to where the XML calls it. This is **approximate, not
  guaranteed-complete**: it is name matching, not a SQL parser, and must not claim completeness it
  cannot deliver. As shipped, the module is richer than first sketched:
  - `RoutineReference{routine_name, breadcrumb, node, kind, line, ref_type}` — one XML occurrence.
    `breadcrumb` is the human-readable path (`Page 'Orders' ▸ Event 'OnBeforeInsert'`), reusing
    `analysis/reused_tables.py`'s `_page_label`/`_detail_label` fallback order so breadcrumbs read the
    same here as in the coherence tree (§17); `ref_type` is `"call"` (a call-shaped occurrence —
    `name(` / `schema.name(`, case-insensitive, with a `(?<![\w.])` guard so `other_schema.foo(` never
    matches `public.foo`) or `"mention"` (a trigger's bare-whole-word match — a trigger has no call
    syntax, so the weaker signal is labelled as such). `kind` is `"page" | "detail" | "column" |
    "event"`; `line` is the 1-based `.pgtp` jump target or `None`; several hits on one line collapse to
    one reference.
  - `RoutineUsage{key, name, kind, ambiguous, info, references}` (+ the `referenced` property) — one DB
    routine or trigger with every reference found for it, keyed by `RoutineInfo.signature` (routines —
    consumed verbatim, never re-rendered, BUG-018) or `schema.table.name` (triggers, matching how
    `DatabaseSchema.triggers` is keyed). **Overloads are not conflated, and not invented either**: two
    overloads of one `schema.name` get separate `RoutineUsage` records sharing the same references, both
    marked `ambiguous=True` — reporting the ambiguity is honest; guessing an overload from the argument
    count would not be.
  - `collect_routine_references(project, schema) → list[RoutineUsage]` — every routine/trigger in the
    schema gets exactly one record, **including** the ones referenced nowhere (an empty `references`
    list answers "can I change this freely?"); returns `[]` when no `.pgtp` is linked rather than a
    list of routines misleadingly labelled unreferenced. `routine_reference_index(project, schema)` is
    the same keyed by `RoutineUsage.key` — the lookup a `BrowserPanel` leaf can do without a scan,
    since it already holds the signature.

  Unlike the table/function tree groupings (which navigate within the single DDL
  buffer), this angle navigates **across** buffers — `EditorPanel` tab → Raw XML tab — two separate
  documents, two separate `navigate_to_line` targets, not the same underlying span. This angle only
  applies when a project has a linked `.pgtp` (§18.2) — it is meaningless in a `.pgtp`-free project.

**Database menu & main-window wiring — implemented:**

- The Database menu gains a **checkable "DDL Explorer" toggle** (`self._ddl_explorer_action`), after a
  separator following the existing items (Connection Setup… and — after FQ-003 — the single
  **Database/XML Coherence** toggle that replaced the two direction items, §17). Toggle on → `_open_ddl_explorer()`; toggle off →
  `center_stage.hide_ddl_explorer()`.
- **Bidirectional lockstep** (the BUG-007 lesson — the tab has its own ✕):
  `CenterStage.ddl_explorer_visibility_changed(bool)` drives
  `_on_ddl_explorer_visibility_changed(visible)`, which shows/hides the left "DDL Objects" tab (making
  the tree dock visible and current when shown) **and** re-syncs the menu action's checked state, so
  closing via the tab ✕ unchecks the menu and vice versa.
- **Async fetch:** `_open_ddl_explorer()` runs `_fetch_ddl_schema(params)` (an **injectable seam** —
  a one-line wrapper around `fetch_routines_and_triggers(params)`, mirroring `_fetch_db_schema`; tests
  patch it to return a canned `DatabaseSchema`) through the shared `self._run_async` threadpool seam
  (the same off-thread executor the Database Check fetch uses, so a slow/dead host never freezes the
  window). On result: `text, spans = build_ddl_text(schema)` → `EditorPanel.set_ddl_text(text, spans,
  schema=schema)` +
  `BrowserPanel.set_schema(schema, spans)` + `show_ddl_explorer()` + a status-bar summary
  (`DDL Explorer: N routine(s), M trigger(s).`).
- **Standalone-mode friendly (§18):** connection params come from
  `seed_params(tree, self._settings)` where `tree` is the current project's lxml tree **or `None`**
  when no `.pgtp` is open — no project is required, only a configured connection. Missing host →
  status-bar message ("No database connection configured — set one up first."), uncheck the toggle,
  and open Connection Setup. Fetch error → status-bar message (`DDL Explorer failed: {exc}`) + uncheck
  the toggle. Params are logged redacted (`debuglog.redacted`).

**Editing is deliberately NOT hosted here.** The earlier "phase 2" sketch — making this multi-object
buffer editable in place and pushing `CREATE OR REPLACE FUNCTION …` from it, with the diff detected per
`DdlObjectSpan` — is **superseded** (§28). A regenerated, whole-schema browsing buffer cannot host
per-object validation, per-object apply, or per-object dirty state, and it conflicts with §18.2's
file-per-object model. `EditorPanel` is read-only **permanently**. The editable surface is §18.5's
separate single-object tab, which reaches this panel only through the right-click ▸ Edit entry point
(and therefore needs the retained span list noted above).

**Tables branch widened to every table, plus click-to-Properties (2026-08-05) — a completion of the
Tables branch's original scope, not a new feature:**

- **Every table in the connected schema is now a tree node**, not only tables that own a trigger. The
  original `_build_tables_branch` derived its whole node set from `schema.triggers` (`by_table` built by
  iterating `schema.triggers.values()` and grouping by `(schema, table)`) — a table with zero triggers
  never got a node at all, and the Tables branch under-represented the schema **by omission, not by
  design** (§18.1 never stated "trigger-owning tables only" as an intentional filter; it was incidental
  to building the branch from `TriggerInfo.table` before `DatabaseSchema.tables` existed in this fetch
  path — see the "Superseded (§18.6, §28)" note above, where `fetch_routines_and_triggers` was widened to
  populate `.tables`). `_build_tables_branch` now iterates `schema.tables` (sorted by table name) as the
  primary node source, and folds in the existing trigger grouping by `(schema_name, table_name)` lookup
  for whichever of those tables also appear in `by_table` — the two data sources merge on the same key
  tables already share. A table with triggers keeps exactly its current presentation (label suffixed
  `(N)` trigger count, trigger leaves nested underneath, per the worked examples above); a table with
  none is a **plain leaf node** — label is bare `schema.table` (no `(N)` suffix, since `N` would be `0`)
  — with no children.
- **Every table node (trigger-owning or plain) now carries a click target**: clicking it populates the
  **existing, shared** `ui/properties_panel.py::PropertiesPanel` (§10) — the same panel instance the
  XML/XSD project tree's Page/Detail/Column/Event selection already drives — **not** a new DDL-specific
  properties surface. This is the Properties panel's **first non-XML source**: `PropertiesPanel.show_node`
  already dispatches purely on a `kind: str` key into `_ROW_BUILDERS` (`"page"`, `"detail"`, `"column"`,
  `"event"` today), each mapped to a `(rows_fn, header_fn)` pair — this dispatch table is generic enough
  to accept a new key unchanged, confirming the placement-gate's belief. `_ROW_BUILDERS` gains
  `"ddl_table": (_rows_for_ddl_table, lambda t: f"Table: {t.name}")`, where `_rows_for_ddl_table(table:
  TableInfo) -> list[RowSpec]` is a new pure function alongside `_rows_for_attrib_node` /
  `_rows_for_detail` / `_rows_for_column` / `_rows_for_event` in `ui/properties_panel.py`, built the same
  Qt-free way. `BrowserPanel.navigate_requested`'s existing line-jump wiring is unaffected — a **second**
  signal on the table-node click (e.g. `table_selected(TableInfo)`, mirroring the shape of
  `edit_requested`/`checkout_requested` already on `BrowserPanel`) is what `MainWindow` connects to
  `self.properties_panel.show_node(table_info, "ddl_table")`, parallel to how the XML tree's own
  selection handler already calls `show_node` for its four kinds. A DDL table node offers **no *editing*
  context menu** — right-click ▸ **Edit…** / **Check Out for Versioning** (§18.1/§18.2) remain routine- and
  trigger-leaf-only, since a whole table has no single `DdlObjectSpan`/source text to hand those entry
  points. **Amended 2026-08-06 (FQ-002, §28): the table node does carry a context menu, holding exactly one
  *creation* entry — "Add Trigger…" — see "Creating brand-new objects from the Explorer" below.** The
  span-based limitation above is specific to *editing an object that already exists*; an object that does
  not exist yet has no source text to need a span for, so creation is not blocked by it. (The narrowing
  originally written here was a statement about the edit/checkout entry points, never a decision that a
  table row must be inert.)
  `PropertiesPanel` rows built from a `TableInfo` are **navigate-to-nothing**: every `RowSpec.target_line`
  is `None` (there is no XML/DDL-buffer source line a column-of-a-table maps to the way an XML attribute
  does), so `_on_row_clicked` no-ops on them exactly as it already does for any `RowSpec` with
  `target_line=None` (e.g. the Representations divider row, §10) — no new no-navigation-target case
  needed in `PropertiesPanel` itself.
- **`ColumnInfo` gains a `comment` field** (`db/introspect.py`): `comment: str | None = None`, trailing
  and defaulted so existing positional/keyword `ColumnInfo(...)` constructions across the codebase and
  tests stay valid. Sourced via `pg_catalog.col_description(a.attrelid, a.attnum)` — the catalog function
  keyed on the column's owning relation's oid and its attribute number, both already selected by
  `_COLUMNS_SQL` (`a.attrelid`, `a.attnum`) — added as a plain expression column to `_COLUMNS_SQL` (not a
  join; `col_description` is a builtin function, not a table), so the query still returns exactly one row
  per column and `_build_tables`'s column-row unpacking gains one trailing field:
  `for schema_name, rel_name, col_name, data_type, notnull, default, comment in column_rows`, threaded
  straight into `ColumnInfo(..., comment=comment)`. This is the **one shared assembly point** —
  `_build_tables` — already serving both `fetch_schema` and `fetch_routines_and_triggers`/§18.6's
  `schema_index.py`, so both existing callers gain comments for free with no second query path; a column
  with no comment set reads back as SQL `NULL` → Python `None`, same convention as `default`.
- **Per-column properties shown, one pair of rows per column**: name, data type, nullability, default
  value, comment — **two `RowSpec` rows per column**, not one, the first grouping concept `RowSpec`
  /`PropertiesPanel` has needed (every existing `_rows_for_*` builder emits exactly one row per logical
  attribute). Row 1 (identity line) — `property_label` = the column name, `value` = `"{data_type}{,
  NULL if is_nullable else NOT NULL}"` (e.g. `integer, NOT NULL`); row 2 (detail line) —
  `property_label` = `""` (blank, so it visually reads as a continuation of row 1, not a new named
  property), `value` = `"default: {default or '—'}  comment: {comment or '—'}"`. Both rows carry
  `attr_name=None` and `target_line=None` (no navigation, see above). This split is a deliberate
  **compact-identity / free-text-detail** grouping — the identity line (name, type, nullability) is
  what a reader scans first; the wider, more variable-length detail line (default expressions can be
  arbitrary SQL, comments arbitrary prose) is set apart underneath it. **Shipped — the pairing cue is
  implemented** as an alternating background shade per column-pair
  (`properties_panel.py::_PAIR_SHADE_COLOR`, a subtle `QColor(0, 0, 0, 18)` tint applied by
  `_populate_table(..., paired=(kind == "ddl_table"))` to every other 2-row record — rows 4–5, 8–9, … —
  a pure row-index computation), with no third "group ID" data field on `RowSpec`; every other `kind`
  passes `paired=False` and still emits exactly one row per attribute. Exact pixel/color treatment was
  left to implementation, consistent with this spec's general behavior-over-pixel-layout stance; the
  **row content and pairing order** (identity row, then detail row, per column, columns in `TableInfo`'s
  existing declared order) is the settled, reproducible part.

#### Creating brand-new objects from the Explorer — Add Trigger / Add Function or Procedure (FQ-002, 2026-08-06)

> **Status: implemented and shipped 2026-08-06 (commits `9f7c7c2` skeleton core, `849d4ae`/`484ef64`
> wiring).** All of it: the pure skeleton core (`db/ddl_skeleton.py`), both dialogs
> (`ui/new_trigger_dialog.py::NewTriggerDialog`, `ui/new_routine_dialog.py::NewRoutineDialog`), the
> table-node **Add Trigger…** context entry and the routines-branch **New Function/Procedure…** entry
> (`ui/ddl_buffer_panel.py`'s `new_trigger_requested`/`new_routine_requested` signals), the Database-menu
> **New Function/Procedure…** action, and manifest registration
> (`MainWindow._register_created_object`). Creation routes through `MainWindow._on_ddl_edit_requested`,
> the same path an Edit… uses, so there is exactly one tab-opening code path.

Until now the Explorer could only browse and edit objects that **already exist** in the connected
database (§18.1 browsing, §18.2 checkout, §18.5 editing). Originating a brand-new trigger, function or
procedure meant hand-writing `CREATE …` somewhere else entirely. This closes that gap **without adding a
new editor, a new tab type or a second deploy path**: the creation gesture ends in the *existing* §18.5
`DdlObjectEditorPanel` tab, pre-filled with a generated skeleton.

**Three entry points, one per shape of the thing being created:**

| Entry point | Gesture | Opens |
|---|---|---|
| `BrowserPanel.tree`, **Tables branch, a table node** | right-click ▸ **Add Trigger…** | the Add Trigger dialog, with that node's `schema.table` pre-bound (the table is *not* an editable field — it comes from the clicked node) |
| `BrowserPanel.tree`, the **"Functions & Procedures"** branch root (`_build_routines_branch`) | right-click ▸ **New Function/Procedure…** | the Add Function/Procedure dialog |
| **Database menu ▸ New Function/Procedure…** (§26) | click | the same dialog, same code path |

- The table-node entry is the reason §18.1's "no context menu" statement on table nodes is amended above
  (§28). Nothing else about the table node changes: left-click still emits `table_selected(TableInfo)` and
  still populates the shared `PropertiesPanel` (§10).
- **There is exactly one Function/Procedure action, not two** — kind is a *field inside the dialog*, not a
  choice made by picking a menu entry. Unlike a trigger, a routine is not scoped to a specific table, so
  the tree-root and menu entry point at an identical, argument-less command.
- The Database-menu placement is **after the ☐ DDL Explorer toggle, behind a separator**
  (`MainWindow._build_database_menu`) — that menu already owns Connection Setup, the two XML↔DB checks and
  DDL Explorer itself, and is where §18 puts everything except §18.2's five File-menu project actions
  (§26). Because the toolbar's command universe is derived by walking the live menu bar with menu-path ids
  (§7, BUG-027), this action is toolbar-customizable **for free** as `database.new-function-procedure`; no
  registry entry is written by hand.

**Add Trigger dialog — fields (all required):**

| Field | Widget shape | Values |
|---|---|---|
| Name | line edit | the trigger's own name; validated by the skeleton emitter, not sanitized (below) |
| Timing | single choice | `BEFORE` / `AFTER` / `INSTEAD OF` — `db/ddl_skeleton.py::TRIGGER_TIMINGS` verbatim, never a second literal list |
| Events | **multi-select** | `INSERT` / `UPDATE` / `DELETE` — `TRIGGER_EVENTS`; Postgres combines them with `OR`, so any non-empty subset is legal and at least one is mandatory |
| Level | single choice | `FOR EACH ROW` / `FOR EACH STATEMENT` — `TRIGGER_LEVELS`. **There is no transaction-level trigger in Postgres**; the original request's "for each transaction" was corrected at triage and must not reappear as a third option |
| Trigger function | chooser over existing objects | **only routines whose `RoutineInfo.return_type == "trigger"`** in the already-fetched `DatabaseSchema` (§18.1's single connect-time `fetch_routines_and_triggers` result — no extra query, no lazy fetch). These are exactly the tree's `[T]`-marked routines (§18.1 marker table) |

- **No inline "create a new trigger function" shortcut in v1.** If no routine returns `trigger`, the dialog
  says so plainly and offers no function to pick — the user creates the function first (via the
  Function/Procedure flow, choosing return type `trigger`) and then the trigger. Stating the gap beats a
  half-wired nested-creation path.
- The function chooser reuses the **existing picker idiom** already in `DdlObjectEditorPanel` for the
  reverse case — `_prompt_unattached_trigger_table` (§18.6, a thin, directly-testable `QInputDialog.getItem`
  wrapper over the schema's known tables) — rather than a new widget: same simple-selection-dialog
  convention, same testability seam.
- `INSTEAD OF` is view-only in Postgres. That constraint is the **dialog's** to enforce or to leave to the
  database; `ddl_skeleton.py` deliberately does not police it (see its `TRIGGER_TIMINGS` docstring).

**Add Function/Procedure dialog — fields:**

| Field | Values |
|---|---|
| Name | line edit; may be schema-qualified (`public.recalc`) |
| Kind | `Function` / `Procedure` — maps straight onto `DdlObjectRef.kind ∈ {"function","procedure"}` |
| Return datatype | **function-only, and hidden/disabled — not merely optional — when Kind is Procedure** |

**Why the return type is hidden rather than optional:** `CREATE PROCEDURE` has **no `RETURNS` clause at
all** in Postgres (procedures use `OUT` parameters); a return type on a procedure is a syntax error, not an
ignorable extra. `procedure_skeleton` accordingly **takes no return-type argument by construction** rather
than accepting and discarding one, so the impossible combination cannot be expressed anywhere in the stack.

**Skeleton generation — `db/ddl_skeleton.py` (implemented; this is its shipped contract):**

Pure and Qt-free — no Qt, no psycopg, no I/O, no clock — and **deterministic**: identical input yields
byte-identical output, so its tests are plain golden strings. **Nothing in it executes SQL**; it renders
text that lands in an editor a user may run nearly unchanged, which is why a skeleton must be *valid as
emitted*.

| Symbol | Contract |
|---|---|
| `TRIGGER_TIMINGS` | `("BEFORE", "AFTER", "INSTEAD OF")` |
| `TRIGGER_EVENTS` | `("INSERT", "UPDATE", "DELETE")` — also the **canonical emission order**: output follows this order regardless of the order the caller passes, so a dialog backed by an unordered set of checkbox states still produces stable, diffable text; the set is de-duplicated (`INSERT OR INSERT` is a syntax error) |
| `TRIGGER_LEVELS` | `("FOR EACH ROW", "FOR EACH STATEMENT")` |
| `SkeletonError(ValueError)` | **Refuse, don't degrade** — matching `migration_gen.UnsupportedDifference`: the caller renders the refusal and no half-formed SQL reaches the editor, where it would look authoritative and get run |
| `trigger_skeleton(*, name, table, timing, events, level, function_name) -> str` | `CREATE TRIGGER <name>` / `<timing> <events joined by " OR "> ON <table>` / `<level>` / `EXECUTE FUNCTION <function>();`. `table` and `function_name` may be schema-qualified — each dot-separated part is quoted **separately**, so the dot stays a separator instead of becoming part of a name. Raises `SkeletonError` on an unknown timing/level, an unknown event, or an empty event set |
| `function_skeleton(*, name, return_type) -> str` | `CREATE OR REPLACE FUNCTION <name>()` / `RETURNS <type>` / `LANGUAGE plpgsql` / `AS $$` / `BEGIN` / body stub / `END;` / `$$;` |
| `procedure_skeleton(*, name) -> str` | the same shape **minus any `RETURNS` line**, body stub = `-- TODO: implement` |

Two correctness rules the module exists to enforce, recorded because both are easy to get wrong by hand
and both are test-covered:

1. **`CREATE PROCEDURE` never gets a `RETURNS` clause** (see above — enforced by the signature itself).
2. **`RETURN NULL;` is invalid in a `void` function** ("RETURN cannot have a parameter in function
   returning void"). `_body_stub` therefore emits `-- TODO: implement` **alone** for `void` and
   `-- TODO: implement` + `RETURN NULL;` for every other return type. A plpgsql block whose body is only a
   comment is valid; a skeleton that fails the moment it is run is worse than one that does nothing.

Identifier handling follows the codebase's established **validated-not-sanitized** posture: every name
goes through `db/sandbox.py::quote_ident`, which double-quotes only after a strict allowlist and otherwise
raises `UnsafeIdentifierError` — arbitrary content is **never escaped into the output**. Mixed case
survives correctly (`MyFunc` → `"MyFunc"`); a name with a space or an embedded quote is **refused, not
mangled**. The **return type is the one free-text field** and cannot use `quote_ident` (`character
varying(255)`, `numeric(10,2)` and `integer[]` are all legitimate and none would survive it), so it gets
its own allowlist — `_SAFE_DATATYPE_RE = ^[A-Za-z_][A-Za-z0-9_ .,()\[\]]*$` — permitting precision,
arrays and schema-qualified domains while refusing **quotes, semicolons and dollar signs**, which is what
keeps a return type from closing the statement or the `$$` body. Empty name/return type → `SkeletonError`.

**v1 emits no parameter list and offers no language picker.** `LANGUAGE plpgsql` is the default and the
only option — this is a plpgsql IDE — and the user fills in the signature in the editor.

**Both flows end in the existing editable tab — no new tab type.** The dialog's accepted result is turned
into a `DdlObjectRef` (§18.5) for an object that does **not yet exist in the database**, plus the skeleton
text, and handed to the **existing** `CenterStage.open_ddl_object_tab(ref, text, resolve_save_path=…)`.
`DdlObjectRef` already models `kind ∈ {"function","procedure","trigger"}`, so the tab, its title/tooltip
rules, its dirty tracking, its Save/Save As… path, §18.4's Format Selection and §18.6's Ctrl+Space
completion all apply unchanged. The **only** structural novelty is the source of the buffer: skeleton text
instead of an introspected `RoutineInfo.source`/`TriggerInfo.definition` — see §18.5 D1's third-entry-point
note. Re-invoking the same creation with the same identity focuses the existing tab, because the tab map is
keyed on `DdlObjectRef.key` exactly as for an existing object.

**Deploy-pipeline integration — resolved 2026-08-06 against the code, and deliberately *not* a new
mechanism:**

- **Do NOT write new `CREATE`-emission logic.** `db/migration_gen.py` already handles brand-new objects:
  it emits every `kind in ("added", "changed")` difference as a bare `CREATE` for routines and as
  `DROP TRIGGER IF EXISTS` + `CREATE` for triggers (no portable `CREATE OR REPLACE TRIGGER` below PG 14).
  That path is correct and already tested; duplicating it would be the parallel-implementation trap.
- **But that path only fires when diffing two introspected `DatabaseSchema` snapshots** — §18.5's
  sandbox-vs-production flow, where `schema_diff.py` reports `target_object is None` as `kind="added"`. The
  **local-file-vs-DB** pipeline (§18.3/§18.4) is a different track: it identifies objects purely through
  `ProjectSettings.deployed` (`db/ddl_project.py`), which today is only ever populated by **checking out an
  object that already exists** ("file absent → seed from the live introspected definition … that write *is*
  the checkout", §18.2), and `compute_drift_markers()` iterates **only** `settings.deployed.items()`.
- Consequence, stated so nobody re-discovers it the hard way: a new `ddl/*.sql` written with no prior
  checkout **parses fine** (`parse_checked_out_header()` recovers identity from the file's own header, not
  from the manifest) but is **invisible to drift tracking** — no `*`, no tree marker, never surfaced as a
  pending change. That is a silent-wrong-result class of failure and is not acceptable.
- **Required: the creation flow registers the new object in `ProjectSettings.deployed` (the drift manifest)
  at creation time**, keyed by the same `ddl/*.sql` POSIX-relative path `routine_ddl_paths` /
  `trigger_ddl_path` compute, as a **"local exists, no last-deployed reference yet"** entry. The existing
  §18.3/§18.4 deploy UI then picks the object up through its **normal** drift/apply flow. **No second,
  parallel "new object" deploy path is created.**
- Concretely: the entry is a `DeployedObject` whose `content_hash` is the **empty string** as the
  never-deployed sentinel (`deployed_commit=None`). The existing comparison then does the right thing with
  no special-casing — `hash(local file) != ""` → `locally_edited` → the `*` marker, while the object's
  absence from the live schema leaves `live_drifted` **False** (`compute_drift_markers` reports a missing
  live definition as *not* drifted rather than manufacturing a false positive). So a freshly created,
  never-deployed object renders exactly as `*`, which is the truth. *Implementation note:*
  `DeployedObject.content_hash` is typed `str` (non-optional) and `compute_drift_markers`'s docstring
  currently reads "an object with no last-deployed reference at all … has no entry here" — that sentence
  describes objects **absent** from the manifest, and the sentinel entry above is the deliberate,
  documented exception; whoever implements this must extend that docstring rather than leave the two
  readings in tension.
- Creating an object **outside a project** (projectless mode, §18.2) writes no manifest entry, because
  there is no manifest — the tab still opens, Save As… still works, and the object simply has no drift
  state, consistent with everything else in projectless mode.

**Rejected: one unified "Add DDL object" dialog for all three kinds.** The required field sets genuinely
differ — a trigger needs timing, events, level, an owning table and an existing trigger function; a
function needs a return type a procedure **must not** have — so a single dialog would be mostly-irrelevant
fields no matter which kind was picked. `DdlObjectRef.kind` already treats the three as distinct
identities, and the split dialogs match that model. (One dialog *does* serve **two** kinds — function and
procedure — because they differ by exactly one field, which the Kind selector hides; that is the boundary
of the rejection, not a contradiction of it.)

### 18.2 Projects, checkout & state markers

> **Status: implemented and shipped (feature-tester green, `docs/TEST_LOG.md` 2026-08-03 — the main
> implementation pass and a small follow-up bug-fix pass for a re-open-redirect issue, since fixed).**
> `db/ddl_project.py` exists with the full `ProjectSettings`/`PgtpLink`/`DeployedObject`/`GitConfig`
> shape, `settings_path`/`load_settings`/`save_settings` (+ `.gitignore` maintenance),
> `routine_ddl_paths`/`trigger_ddl_path` (the `_1`-suffix overload scheme),
> `parse_checked_out_header`/`reconcile_routine_paths` (header-based rename detection), `content_hash`,
> and `DriftMarkers`/`compute_drift_markers`. The File-menu actions (**New Project…**, **Open
> Project…**, **Close Project**, **Project Settings…**, **Deploy .pgtp**), the project-settings JSON
> dialogs (`ui/new_project_dialog.py::NewProjectDialog`, `ui/project_settings_dialog.py::ProjectSettingsDialog`),
> `*`/`!` marker rendering on `BrowserPanel.set_schema`'s `drift_markers` parameter, and the
> checkout-to-edit path (`BrowserPanel`/`EditorPanel`'s `checkout_requested` signal,
> `MainWindow._checkout_and_edit`/`_ddl_checkout_relpath`) are all in place, as is the `.pgtp`-as-checked-
> out-artifact machinery (`MainWindow._link_pgtp_to_project_if_needed`, `_resolve_pgtp_project_path`,
> `_is_ddl_project_pgtp_working_copy`, `_deploy_pgtp`). The **New Project superuser Test button** reuses
> the §18.5 D2 capability probe (`db/sandbox.py::SandboxCapabilities`/`probe`) as specified — at the time
> that button shipped, the module was only the probe slice; the accumulating `SandboxSession`,
> `build_baseline_sql`, and the rest of the provisioning ladder **have since been built** in that same
> module (§18.5 D2/D2a — either way, not a gap in this subsection). Likewise, git integration throughout this
> subsection is an **explicit, intentional TBD/placeholder** (see "Git is optional and TBD" below) — it
> was never meant to be built in this pass, so its absence is not implementation drift. §18.1's browsing
> substrate and §18.5's editable tab are what this builds on, both also implemented.
>
> **This subsection adds no new tab type.** The editable single-object tab is
> `ui/ddl_object_editor.py::DdlObjectEditorPanel`, specified **once**, in **§18.5**. Everything here is
> the *versioning* layer around it: what a project is, how files are named, what checkout does to the
> tab's **injected load/save pair**, and the `*`/`!` drift markers. Do not restate the tab here.
>
> **Revised 2026-08-03 — a wholesale rewrite of the project model, superseding this subsection's earlier
> git-repo-based design (§28).** The sections below state the current, sole truth; see the Supersession
> Ledger for exactly what each replaces.

#### The external checkout process (outside this app's scope)

A developer starts work on a branch/bugfix/feature by running an **external**, out-of-app process that
checks out the production database's DDL, the production `.pgtp` file, and the production PHP files onto
a quality/staging server. **The app never performs this checkout itself** — it has no knowledge of, and
no code path for, provisioning that staging server or populating it from production. What the app deals
with begins one step later: the user opening the `.pgtp` file that process already produced.

#### What a "local project" is

The user opens the app and opens the `.pgtp` file from that quality server via an **sshfs mount** to
their own machine. At that point the app creates/recognizes a **local project**: a folder the user
chooses **on their own machine**, which becomes the working area for this checkout.

**A project is fundamentally a local folder — not necessarily a git repository.** This directly
supersedes this subsection's earlier opening line, *"a project = a git repo containing: …"* (§28). Using
git as an analogy only (git itself is **not** required — see "Git is optional" below), the owner's
framing: *"main is prod, each checkout a branch, and each time we open in the pgtp a worktree."* Owner's
framing for the truth model this all sits on, preserved close to verbatim: *"the only source of truth in
our projects is production database DDL, production pgtp and production phps. Everything else is just a
snapshot, approximation, history."*

**Git is optional and TBD — an explicit placeholder, not a designed mechanism.** New Project creation
*optionally* offers git configuration (server, user, the checkout/branch this project's folder is meant
to be a worktree of), exactly as §18.3's *"commit/push to git: explicit placeholder, not designed,
mechanism TBD"* framing already establishes for the deploy step — this is the same kind of placeholder,
recorded so it is not forgotten, not designed here. **Do not treat any of the following as implying a
live git workflow**: no commit step, no push step, no branch/worktree machinery is specified by this
revision. When git integration is eventually designed, it is designed then, as its own pass.

#### New Project creation flow

1. **User picks a folder on disk — that folder IS the project.** No hidden bootstrap directory is
   required to exist first; the folder itself is the project root.
2. **Optionally add a local sandbox**: a Postgres connection (host, port, user, password) plus a **Test
   button whose specific job is verifying the given user is a superuser** — not merely "can connect".
   This is a new *entry point* into the **already-designed** capability probe / connection-profile
   mechanism (§18.5 D2's `SandboxCapabilities.is_superuser`, sourced from `current_setting('is_superuser')`
   via `probe`) — reuse it as-is, do not build a second superuser check. Superuser is required because
   sandbox provisioning needs `CREATE EXTENSION` (§18.5 D2's one-click `plpgsql_check` install). This same
   step also presents a **"with data" / "without data"** choice (§18.5 D2a, settled 2026-08-05) deciding
   which provisioning strategy runs once the sandbox database is created: "without data" is the existing
   schema-only `build_baseline_sql` path (the default); "with data" clones the target database via
   `pg_dump`/`pg_restore` subprocesses instead — a scoped, one-shot exception to D2's otherwise-holding
   no-external-process invariant. The choice is recorded in the project's sandbox settings, not
   re-toggleable later; getting fresher data means destroying and recreating the sandbox.
3. **Optionally add git configuration** (server/user/checkout branch, this project as a worktree of it)
   — explicit **TBD/placeholder only**, per above. No UI beyond capturing the intent needs to be
   designed yet.

#### Opening an existing project

**"Open Project…" requires a valid project folder** (BUG-022, 2026-08-05). The folder picker
(`QFileDialog.getExistingDirectory` with `Option.ShowDirsOnly`, so only folders — never files — are
shown) does not accept just any folder: after the pick, `db/ddl_project.py::is_project_dir(path)` checks
for the project marker, the `.ddlproject/settings.json` file. A folder lacking the marker is **rejected**
with a warning dialog ("not a PGTP DDL project folder … no `.ddlproject/settings.json` marker found") and
the operation aborts rather than silently proceeding with a freshly-defaulted, effectively-empty
`ProjectSettings()`. Only a folder that already carries the marker opens.

Opening a project compares **two independent things**, both surfaced, neither auto-resolved:

1. A **checksum of the `.pgtp` working copy** against the source `.pgtp` at the sshfs-mounted path (new
   in this revision — see "The `.pgtp` file becomes a first-class checked-out artifact" below).
2. The **existing per-object DDL drift comparison** — the already-designed `*`/`!` markers, unchanged in
   mechanism (content-hash based, per the "last-deployed reference" material below).

Both comparisons are **recomputed fresh on every project load, never cached or trusted from a prior
session** — consistent with the truth-model principle stated at the top of §18 ("database is truth, git
is history only," now extended to "the source `.pgtp` is truth for the `.pgtp` link").

**Opening a project auto-opens its linked `.pgtp` working copy into the editor** (BUG-021, 2026-08-05).
Once the project folder is validated and made active, `MainWindow._auto_open_linked_pgtp` runs (skipped
only when the caller supplied its own `on_ready` continuation with its own load already in hand, e.g.
`_prompt_pgtp_open_mode`'s "Open Project…" choice or `_require_ddl_project`, avoiding a double-load race)
and reuses the existing `open_project_file` loader rather than a second load path:

- **`settings.pgtp.working_copy_path` set and the file exists** — auto-open it directly.
- **Not yet linked, and exactly one `*.pgtp` sits in the project folder** — auto-open that one candidate.
- **Not yet linked, and zero `*.pgtp` files in the project folder** — silent no-op; nothing to open yet,
  not an error.
- **Not yet linked, and multiple `*.pgtp` candidates** — never guess: report the file names via the
  Audit panel (`[Project] Multiple .pgtp files found in … — open one explicitly via File > Open.`) and
  leave the editor as-is.

> **The menu actions are lambda-wrapped, and this is load-bearing, not style.** `QAction.triggered`
> emits a `checked: bool`, so `open_project_action.triggered.connect(self._open_ddl_project)` invokes
> `_open_ddl_project(False)` — binding `on_ready=False`, which is *not* `None`, so the old
> `if on_ready is not None:` guard took the callback branch and called `False()`. The auto-open was
> therefore **dead code on the only path a user can reach it by**, while its unit test (which called the
> method directly) passed. Both project actions are wired as
> `…triggered.connect(lambda: self._open_ddl_project())` /
> `…triggered.connect(lambda: self._new_ddl_project())`, and the guard is hardened to
> **`if callable(on_ready):`** as defence in depth. Any argument-less action slot with optional
> parameters must be wired the same way. **Regression tests must drive the real signal**
> (`action.trigger()`), never just call the method — a direct call cannot reproduce this class of bug.

#### Neither browsing nor single-object editing needs a project — only *versioning* does

Opening the DDL Explorer (§18.1) stays **connection-only**, exactly as implemented today. Right-click ▸
Edit… (§18.5) is likewise connection-only: it loads the live introspected definition into the editable
tab, so "edit one function and find out whether it compiles" never requires a project. A project becomes
required only for the versioned workflow this subsection adds: **checked-out `ddl/` files, the checked-out
`.pgtp` working copy, drift markers and deploy**.

**No-project mode is completely unaffected by this entire revision — stated explicitly so it is not
misread.** Owner's framing, verbatim: *"No project mode is permitted, but no project mode is just pgtp
editing, ddl editing and saving locally. No lint, no ddl diff, nothing more, just works as an editor."*
None of the following — the project JSON, the `.pgtp` working-copy/no-`.bak` model, the drift markers —
applies when no project is open. **§19/§7's existing plain `.pgtp` save + `.bak` behavior is untouched in
that mode** (see "The `.pgtp` file becomes a first-class checked-out artifact" below for the precise
scope of what changes and what does not).

**Menu actions** (**File** menu, §26 — their own separator-delimited group between `Open…` and `Save`,
built by `MainWindow._build_file_menu`; *not* the Database menu, which keeps Connection Setup / Check /
DDL Explorer and the §18.5 sandbox entries): **New Project…**, **Open Project…**, **Close Project**,
**Project Settings…** (new, below), **Deploy .pgtp** (new, below).

**No project is ever created silently.** Invoking a **project-scoped** action with no project open —
Check Out for Versioning, Deploy, or anything that would write under `ddl/` — shows a **"Project
required"** dialog offering **Create… / Open… / Cancel**; on Create/Open the operation then proceeds
against the newly-active project, on Cancel nothing happens. Plain Edit… never raises this dialog.
Rationale, stated so it is not re-litigated: creating a folder-backed project on disk is an **outward
effect**, and this app confirms before outward effects (cf. Generate PHP's Save-vs-Save-As prompt §19,
Diff/Merge's Apply gate §12).

**File naming — disambiguate overloads with a numeric `_1` suffix, not with argument types.**

| Case | Path | Example |
|---|---|---|
| Routine, sole holder of its `schema.name` | `ddl/<schema>.<name>.sql` | `ddl/public.recalc.sql` |
| Routine that is **overloaded** (≥ 2 routines share `schema.name`) — **first** overload in signature order | `ddl/<schema>.<name>.sql` (**unsuffixed**, exactly as the sole-holder case) | `ddl/public.fmt.sql` (= `fmt(integer)`) |
| Each **further** overload, in signature order | `ddl/<schema>.<name>_<n>.sql`, `n` counting from **1** | `ddl/public.fmt_1.sql` (= `fmt(text)`), `ddl/public.fmt_2.sql` |
| Trigger (always table-qualified — a trigger name is unique only per table) | `ddl/<schema>.<table>.<trigger>.sql` | `ddl/public.orders.trg_audit.sql` |

Owner's decision, verbatim: *"as of filenames, just resolve it with `_1`"*. Argument types are **not**
put in the filename: `(integer, character varying[])` renders characters that are illegal or awkward on
Windows filesystems and in shells, and the resulting names are long and churn-prone. The trigger row is
unchanged by this decision.

**Suffix assignment — deterministic and stable across sessions and machines (this is the load-bearing
part, not a detail).**

- The overload set for a `schema.name` is ordered by its **argument-type signature**: the tuple
  `RoutineInfo.arg_types`, compared **lexicographically element-by-element as sorted strings**, shorter
  tuples first on a common prefix (so `f()` < `f(integer)` < `f(integer, text)` < `f(text)`). This is
  the **same** ordering §18.1 uses to order overload siblings in the tree and in `build_ddl_text`, so
  file order, tree order and buffer order never disagree.
- **Ordering is never taken from introspection row order.** `fetch_routines_and_triggers` returns
  whatever the catalog scan produced; letting that decide would reassign `public.fmt_1.sql` to a
  different signature between two runs on two machines — the file would keep its name and silently
  change meaning, in git, which is exactly the silent-wrong-result class this project refuses.
- **The first overload keeps the unsuffixed name.** Suffixes start at `_1` for the *second* signature.
  This keeps the overwhelmingly common non-overloaded case identical to the sole-holder case and means
  a routine that later becomes overloaded never has its existing file renamed.
- **Reconciliation when the set changes.** Path computation is a **pure function of the whole current
  overload set** (`db/ddl_project.py`, below), so the numbering is recomputed, not stored:
  - **An overload is added** — it takes the next free suffix **only if** its signature sorts after every
    existing one; if it sorts in the middle, the later files would shift, so the tool **renames the
    affected files deliberately with `git mv`** (never write-new + leave-old), in one operation, and
    reports the renames to the Audit panel. Renaming rather than appending keeps "file order = signature
    order" true, which is what makes the mapping recomputable at all.
  - **An overload is dropped** — its file is **left in place, not deleted and not renumbered.** A
    checked-out file is the user's git-tracked work; removing it is their call (`git rm`). The gap in
    numbering is harmless and is the price of never silently mutating a versioned tree. Renumbering is
    only ever performed by the add path above, and only when it must be.

> **The trade-off the superseded argtypes scheme was designed to avoid, stated plainly: `_1` is not
> self-describing.** `ddl/public.fmt_1.sql` does not tell you which overload it holds. That is
> acceptable **only because the mapping is recoverable from the file's own contents**: every `ddl/*.sql`
> is seeded from `pg_get_functiondef`, whose first line is a full
> `CREATE OR REPLACE FUNCTION public.fmt(text)` header carrying the complete signature. The signature is
> therefore always one line away, in the file, in git history, and in every diff — the filename is an
> identifier, the header is the identity. Consequence for the implementation: **the header is
> load-bearing**, so a checked-out file whose `CREATE OR REPLACE` header cannot be parsed back to a
> signature must be reported, never guessed at from its filename.

**Path computation is pure and Qt-free.** The `object → ddl/*.sql` path function — which takes the
**whole routine set**, not one routine, because both the "is this `schema.name` overloaded" decision and
the `_n` suffix assignment are properties of the set — the signature ordering above, and filename
sanitization (path separators, characters illegal on Windows, case-insensitive-filesystem collisions)
all live in the new pure module **`db/ddl_project.py`** — mirroring `db/ddl_buffer.py`'s precedent so
they are unit-testable without Qt and without a database. The same module owns the merged
project-settings JSON shape (below).

#### Project settings — one centralized, gitignored, plaintext JSON file

**Superseded 2026-08-03 (§28): the earlier two-file scheme (`.ddlproject/project.json` +
`.ddlproject/deployed.json`, both git-tracked) is replaced by a single file** — call it
`<project>/.ddlproject/settings.json` (path stable; the `.ddlproject/` folder now holds exactly one
file). **The file is gitignored — not committed — and holds plaintext, including the password.**

This is a deliberate pair of reversals from the original design, both owner-stated:

- **Password lives directly in this JSON, not in QSettings.** The earlier "Password handling" design —
  keeping the password **out of** git via the app's existing `db/config.py::ConnectionParams`/
  `save_connection` QSettings mechanism, generalized to a keyed `ProfileKey(project, role)` — is
  **superseded for project-scoped connections**. Owner's reasoning, preserved verbatim: *"if it remained
  in QSettings, it wouldn't be project specific"* — the project must be **self-contained/portable**: a
  folder that can be copied, backed up, or handed off complete, not dependent on a separate app-level
  global settings store keyed by a path that may not even resolve on the machine it's copied to. The
  password never reaches git anyway, because the file it lives in is gitignored — it is simply gitignored
  **instead of** QSettings-hidden, not gitignored **and** QSettings-hidden.
- **The deploy manifest no longer needs to be git-tracked, because there is no live git workflow yet for
  its state to "travel" through.** The earlier `deployed.json` was git-tracked specifically so
  "last-deployed" state would travel across machines/clones via git. But git integration for this whole
  local-project model is **itself still TBD/deferred** (see "Git is optional" above) — there is no commit
  step, no push step, nothing for that state to travel *through* yet. **When/if git integration is
  designed later, that is the point to revisit whether any of this needs to be git-tracked.** For now,
  everything is local-per-checkout, and merging the manifest into the gitignored settings file costs
  nothing that isn't already deferred.

**Governing principle for the whole local-project model, stated explicitly because it explains several
of these choices at once — owner's words: *"nothing the app manages should be a black box… plaintext
files everywhere."*** This is the same spirit that already justifies `ddl/*.sql` being plain per-object
files rather than one opaque buffer (above); it is now stated as a governing principle for local
projects generally, not only the `ddl/` folder — see also the callout at the top of §18.

**The merged JSON holds** (shape unchanged from the previous design except for the merge and the added
`.pgtp` fields below):

- **Project identity** — name, description.
- **The `.pgtp` link + its checkout/drift state** — the sshfs-mounted source path, the local working-copy
  path, and the last-computed checksum comparison (see "The `.pgtp` file becomes a first-class
  checked-out artifact," below). The link remains **optional**, exactly as before: a project may have
  zero, one pre-existing, or one newly-created `.pgtp`.
- **Target + sandbox connection profiles, including the password** — host/port/database/user/password
  for both the `target` and (§18.5 D2) `sandbox` roles, since the whole file is gitignored there is no
  reason to keep the password out of it the way the old design kept it out of git.
- **The merged deploy manifest** — content-hash + deployed commit id per DDL object, **unchanged in
  shape** from the previous `deployed.json` design (see "last-deployed reference," below); only its
  location and its git-tracked-ness change.

**A new, technically-detailed Project Settings dialog** (File menu ▸ **Project Settings…**) exposes
this JSON's **full contents**, for viewing and editing — not a simplified subset, the whole thing:
project identity, the `.pgtp` link and its paths, both connection profiles (including the password
fields, `EchoMode.Password` as elsewhere, §17), and the deploy manifest's raw per-object entries. This is
a new UI surface; add it to the **File**-menu action list (§26) alongside **New Project…** / **Open
Project…** / **Close Project** / **Deploy .pgtp** (below).

**Layout: a `QTabWidget`, four tabs** (BUG-025, 2026-08-05; layout only — the "whole JSON, nothing
hidden" contract above is unchanged). The dialog's field groups are distributed across tabs rather than
stacked in one long single-column `QVBoxLayout` (which pushed lower groups off-screen): **"General"**
(identity form — Name, Description — + the `.pgtp` link group), **"Connections"** (the Target connection
and Sandbox connection groups, the latter carrying its sandbox-mode radio sub-form), **"Git"** (the git
config group), **"Deploy manifest"** (the deploy-manifest table + Add/Remove buttons, on its own tab
since the table wants width). The OK/Cancel `QDialogButtonBox` stays outside/below the tab widget, not
inside any tab. Default size `560×480`, resizable (no `setFixedSize`). All fields keep their existing
`self._…`-attribute get/set wiring — reparenting into tabs does not change how any value round-trips.

**Each connection group on the "Connections" tab carries its own Test button + inline status label
(FQ-001, 2026-08-05) — two *different* tests, reusing the two flavors that already exist, never a third.**
Editing a saved project's connection details (a moved database, a rotated credential) previously had no
in-dialog verification path: the user saved blind and found out on next use. Each of the two groups built
by `ProjectSettingsDialog._build_connection_form` gets a `Test` button + `QLabel` status line appended
beneath its host/port/database/user/password rows by a small sibling helper,
`_add_test_row(group, on_click) -> (QPushButton, QLabel)` (kept separate from `_build_connection_form`
because the two groups wire different slots — `test_target` vs. `test_sandbox` — into the same row shape).
Both **test the values currently typed in the dialog's fields**,
never the last-saved `ProjectSettings.target`/`.sandbox` — the params object is rebuilt from the live field
widgets at click time by `target_params()`/`sandbox_params()`, exactly as `ConnectionSetupDialog.params()`
and `NewProjectDialog.sandbox_params()` already do.

| Group | Test performed | Reused verbatim from | Underlying call |
|---|---|---|---|
| **Target connection** | Generic connectivity — `SELECT 1`, green `Connected.` / red driver message | `ui/connection_setup_dialog.py::ConnectionSetupDialog.test` | `db/introspect.py::test_connection(params) -> tuple[bool, str]` (never raises; failure is the message) |
| **Sandbox connection** | **Superuser capability probe**, not mere connectivity | `ui/new_project_dialog.py::NewProjectDialog.test_sandbox` + `_apply_sandbox_probe_result` | `db/sandbox.py::probe(params) -> SandboxCapabilities` |

The sandbox result mapping is the same four-way ladder as the New Project dialog's, in this order —
`caps.probe_error is not None` → that message, red; **not `caps.is_superuser`** → *"Connected, but NOT a
superuser — sandbox provisioning needs CREATE EXTENSION."*, red; **mode is `SandboxMode.WITH_DATA`
and not `caps.data_clone_available`** → *"Connected — superuser, but 'with data' needs `pg_dump` and/or
`pg_restore` on PATH (not found)."* naming which binary is missing, red; otherwise *"Connected —
superuser."*, green. The `WITH_DATA` branch has a real source **in this dialog**: it reads the
already-present sandbox-mode radios (`_sandbox_mode_without_data_radio`/`_sandbox_mode_with_data_radio`,
§18.5 D2a) as currently set on screen, not the saved `settings.sandbox_mode`, via a `sandbox_mode()`
accessor matching `NewProjectDialog`'s. Unlike `NewProjectDialog`, this dialog **does not retain the
probe result** (no `_last_probe`): no caller reads a capability probe back off Project Settings — the
probe here exists purely to inform the user before they press OK.

**A single shared generic connectivity test for both groups was considered and explicitly rejected**
(owner-confirmed 2026-08-05): it would green-light a sandbox connection that connects fine as a
non-superuser and then fails at provisioning time (`CREATE EXTENSION`, §18.5 D2) — reintroducing exactly
the false-green the New Project superuser probe exists to prevent, and violating this project's
"never a silent wrong result" rule. The two tests stay distinct because the two connections have
genuinely different success conditions.

Mechanics follow the two source dialogs exactly, so nothing new is invented: the click disables its own
Test button, clears the label's stylesheet and shows the busy text (`"Testing connection…"` for target,
`"Testing…"` for sandbox); the work runs **off the GUI thread** through the injected `self._run_async`
seam (`ui/async_task.py::run_async`, assigned as a plain attribute in `__init__` so tests replace it with
a synchronous stub); the result/error callbacks run back on the GUI thread, set the label text plus
`color: green;`/`color: red;`, and re-enable the button. **No modal, no toast, no Audit line** — the
inline colored label is the entire feedback surface, matching the existing two Test buttons.

**Injection seams.** `ProjectSettingsDialog.__init__(self, settings, parent=None, tester: Tester =
test_connection, prober: Prober = probe)` — both new parameters are **defaulted keyword arguments**,
mirroring `ConnectionSetupDialog(parent, tester)` and `NewProjectDialog(parent, prober)`, so the dialog's
single construction site (`ui/main_window.py`, the **Project Settings…** action) needs no change and
tests can inject fakes. As in both source dialogs, `self._run_async = run_async` is set as a plain
attribute rather than a constructor parameter. The dialog still **persists nothing on its own**: testing a
connection neither writes `settings.json` nor mutates the active project's live connection — it only
reports.

**Connection profile persistence — reconciled with §17's `ProfileKey` scheme, least-invention reading.**
§17 specifies (**target design — not implemented**: `db/config.py` today still has only the single
hardcoded `"db"` QSettings group, no `ProfileKey`) a keyed `ProfileKey(project, role)` scheme backed by
QSettings, for exactly this project+role dimensionality. This revision changes **where the project-scoped
connection profile is persisted — into the project's own JSON file — not how it is selected or edited
at the UI layer.** `ConnectionSetupDialog`'s profile selector (§17/§18.5 D2) is likewise target design —
**no selector has been built** (the shipped dialog carries no profile code, and is disabled outright
while a project is open, BUG-024); as designed, the user would pick `target` or `sandbox` in that same
dialog. What changes is the **backing store** for a
project-scoped `ProfileKey`: instead of (or in addition to, as a migration convenience — unresolved,
§29) a `db_profiles/<slug(project)>/<role>` QSettings group, the project's own connection profiles are
read from and written to its `.ddlproject/settings.json`. The **non-project-scoped** default profile
(`DEFAULT_PROFILE`, the literal `"db"` QSettings group used when no project is open) is **untouched** —
that path has no project JSON to live in and keeps using QSettings exactly as §17 specifies. This is the
reading that requires the least invention beyond what the owner actually stated: the persistence backend
changes for project-scoped profiles; the UI/selector mechanism does not.

**Checkout-to-edit.** The gesture and the tab are §18.5's (right-click ▸ Edit… on `BrowserPanel.tree`
or inside an object's span in the read-only `EditorPanel` — see §18.5 for the entry-point table, the
widget idioms and the span resolution). What a project adds is a **second variant of that gesture**,
**Check Out for Versioning**, which performs the checkout below and *then* opens the same tab with its
injected load/save pair pointed at the checked-out file instead of the live definition. It is not a
second tab type and not a second editor.

**Checkout semantics (the operation itself):**

1. Resolve the object's `ddl/*.sql` path via `db/ddl_project.py` (naming scheme above).
2. **File absent** → **seed** it from the live introspected definition (`RoutineInfo.source`, i.e.
   `pg_get_functiondef`; `TriggerInfo.definition`, i.e. `pg_get_triggerdef` — §17/§18.1) and write it.
   That write **is** the checkout.
3. **File present** → open it from disk. **The local file is the editable truth and is never silently
   overwritten from the live DB.**
4. If the live DB has drifted from the last-deployed reference (the `!` marker, below), **surface it —
   an Audit line and the existing marker — but do not block editing.** This is the embrace-drift
   principle: the tool surfaces disagreement, it does not auto-resolve. (Drift blocks **deploy**, §18.3
   — never editing.)

Checkout itself never opens a database write transaction: it only reads, through
`db/introspect.py::run_queries` — the sole **read** seam, which only ever `execute`s + `fetchall`s and
never commits (§17). Database writes **to the target database** exist in exactly one place, the separate
`db/apply.py` seam introduced by §18.5; sandbox-scoped writes go through the sandbox session's own named
seams (`db/sandbox.py::SandboxExecutor`, §18.5 D2/D4 — the three-seams invariant, §18.5). Checkout uses
none of them.

**Save vs. Apply under a project — and how this relates to §18.3.** Once the tab's save callback points
at a checked-out file, **Ctrl+S / Save writes that `ddl/*.sql` file and nothing else** (UTF-8;
**deliberately no `.bak` sidecar** — the file is git-tracked (once git is configured; TBD, above) and the
working copy itself is the safety net regardless, an intentional divergence from §19's `.pgtp` save).
**Apply remains the separate, explicitly confirmed §18.5 gesture** and is unchanged by checkout: it can
target the sandbox or the target database, each confirm-gated. Saving never applies and applying never
saves.

**Stated plainly, since it was previously only implicit in the table below: deploying a DDL edit is an
explicit per-edit choice among three coexisting destinations, and the user picks which one on every edit
— this is a confirmation of the existing design, not a change to it.** The owner enumerated the three as
(A) save only to the sandbox, (B) save to disk for a future batch deploy, (C) deploy directly to the
currently-open/target database — which map onto the gestures already specified with **no changes needed**:
(A) = §18.5's **Apply to Sandbox**; (C) = §18.5's **Apply to Target** (unchanged: still confirm-gated
behind the four hard preconditions); (B) = the plain **Save** described in this paragraph (writes
`ddl/*.sql`), which is the track §18.3's batch Deploy later assembles into `deploy.sql`. Nothing about
this changes any of the three gestures; it is recorded here only so the "the user chooses per-edit which
of the three to use" framing is stated directly rather than left to be inferred from the table below.

The two write-to-a-real-database paths are deliberately different gestures with different guardrails,
and **§18.3 is authoritative whenever both could apply**:

| | §18.5 single-object **Apply** | §18.3 **Deploy** |
|---|---|---|
| Scope | exactly one object, the one in the active tab | a **batch** of `*`-flagged objects |
| Review | a confirmation naming the object and the database | a reviewed, order-adjustable SQL bundle |
| Drift gate | none — drift is surfaced, not blocking | **any `!`-flagged object blocks the whole batch** |
| Manifest / git | writes nothing to the deploy manifest, makes no commit | updates the project JSON's deploy manifest + commits (once git is configured) |
| Use it for | iterating on one routine | rolling a reviewed change set out |

Consequence, stated so the two never read as duplicates: a single-object Apply to the **target** database
is a legitimate, narrow, individually-confirmed action — but it is **not** a deploy. It does not record
last-deployed state, so the object will subsequently read as `!` (live DB differs from the last-deployed
reference), which is correct and intended: the versioned record of what is deployed is only ever written
by §18.3. **When a project is open and the objects involved are checked out, the reviewed §18.3 deploy is
the authoritative path**; single-object Apply exists for the edit/validate loop, not for rollout.

**Tab key under a project.** §18.5's dynamic-tab map is keyed by a stable per-object key; once an object
is checked out, that key is the **resolved absolute `ddl/*.sql` path**, so re-invoking Edit on a
checked-out object focuses the existing tab rather than opening a second one. (Project-less, the key is
`DdlObjectRef.key` — the hashable tuple derived from the object's `DdlObjectSpan` identity, the same key
`CenterStage._ddl_object_tabs` is addressed by — §18.5.)

**State markers — combinable, not a new third symbol.** Rendered on `BrowserPanel` (§18.1) tree items:

- `*` = the local file has an unsaved-to-deploy edit (differs from the last-deployed reference for that
  object).
- `!` = the **live DB** has drifted from the last-deployed reference for that object.
- These are **independent booleans that render together** when both are true (e.g. `*!`) — there is
  **no separate third state/symbol** for "both." This is a deliberate embrace-drift philosophy: the
  tool surfaces disagreement, it does not attempt to auto-resolve it.

> **Settled: "last-deployed reference" = a deploy manifest inside the project's own JSON, target
> design.** *(Superseded 2026-08-03, §28: previously a separately git-tracked `.ddlproject/deployed.json`
> — see "Project settings" above for why it merged into the single gitignored file and why that no
> longer requires the manifest itself to be git-tracked.)* The manifest records, per DDL object, **both**
> a content-hash and a deployed commit id, with distinct roles:
>
> - **Content-hash** — the mechanism actually used for all drift comparisons: `*` = hash(local `ddl/`
>   file) != stored hash; `!` = hash(live DB introspected definition) != stored hash. This keeps the
>   correctness-critical comparison independent of git plumbing entirely — no shelling out to git, no
>   dependency on history staying intact — consistent with the "database is truth, git is history only"
>   principle stated above.
> - **Deployed commit id** — stored purely for human traceability ("this object was deployed as of
>   commit X"), populated only once git integration exists (TBD, above); not consulted by the comparison
>   logic itself.
> - Implementation requirement: the hash must be computed the **same way** in all three places it's
>   used (local file content, live DB introspection via `pg_get_functiondef`/`pg_get_triggerdef`, and
>   the stored reference), so formatting/whitespace normalization doesn't produce false drift.
> - The manifest is written atomically, inside the project JSON, at the moment §18.3's deploy step
>   succeeds — alongside the git commit of the deploy itself, once git integration exists. Because the
>   project JSON is local-per-checkout (not committed), "last-deployed" state does **not** currently
>   travel across machines/clones the way the earlier git-tracked design intended; this is the accepted
>   consequence of git being deferred (above), and is exactly the kind of question to revisit once git
>   integration is designed.

Markers are recomputed **fresh on every project load** per the truth-model principle above — never
cached or trusted from a prior session.

#### The `.pgtp` file becomes a first-class checked-out artifact, parallel to a DDL object

**Superseded 2026-08-03 (§28), and scoped precisely: this applies ONLY when a local project is open.**
Outside a project (no-project mode, above), `.pgtp` save behavior is **completely untouched** — plain
save-in-place with a `.bak` sidecar on overwrite, exactly as §7/§19 already specify (`.bak` written via
`shutil.copy2` before overwriting an existing file; never on Save-As to a new path). This row's
supersession applies **only within the local-project context** described here.

**Under a local project, the app works on a local working copy of the `.pgtp`** — analogous to a
checked-out `ddl/*.sql` file:

- **Ordinary saves (Ctrl+S / File ▸ Save) write to this working copy, and there is deliberately no
  `.bak`.** Same rationale as `ddl/*.sql`'s existing no-`.bak` decision (above): the working copy itself
  is the safety net / history — an intentional divergence from §19's plain-mode `.pgtp` save, now
  extended from DDL objects to the `.pgtp` file itself.
- **Pushing the working copy back to overwrite the source `.pgtp`** at the sshfs-mounted path is a
  **separate, explicit "Deploy .pgtp" gesture** — never implied by Save, exactly as Apply is never
  implied by Save for a DDL object (§18.5).
- **"Deploy .pgtp" is reachable two ways**, mirroring how DDL's batch Deploy (§18.3) is already
  **on-demand**, not tied to any lifecycle event:
  - **On-demand, at any time during the session** — File menu ▸ **Deploy .pgtp** (§26).
  - **Offered as a convenience prompt when the project is closed**, if the working copy has unpushed
    changes relative to the source `.pgtp` — see §18.3's project-close addition, below. It is an offer,
    never a forced action: closing without deploying is always available.
- The **checksum comparison at project-open** (above) is what surfaces whether the working copy and the
  source `.pgtp` have diverged — surfaced, not auto-resolved, the same embrace-drift discipline as the
  `*`/`!` DDL markers.

### 18.3 Deploy workflow & schema diff/migration

> **Status (audited 2026-08-06): every module this subsection specifies now exists and is tested — and
> none of them is reachable from the running application.** The pieces ship; the flow does not.
>
> | Piece | State |
> |---|---|
> | `db/schema_diff.py` (`SchemaDifference`/`SchemaDiffResult`/`diff_schemas`/`routine_identity`/`trigger_identity`) | **Ships**, tested (`tests/db/test_schema_diff.py`). `routine`/`trigger` kinds only — `table`/`column` diffing is deliberately out of scope (`SchemaDiffResult.unsupported` names what wasn't compared). |
> | `db/migration_gen.py::generate_migration` | **Ships.** Raises `UnsupportedDifference` rather than silently dropping a table/column change. |
> | `db/schema_snapshot.py` | **Ships** (`dump_schema`/`load_schema` + `write_snapshot`/`read_snapshot`, versioned JSON, `SnapshotFormatError`/`UnsupportedSnapshotVersion`), tested (`tests/db/test_schema_snapshot.py`) — commit `dffb59b`. |
> | `db/deploy_bundle.py` — steps 1–3's decision layer (candidates, the `*!` ambiguity gate, adjustable order) | **Ships**, pure, tested (`tests/db/test_deploy_bundle.py`) — commit `dffb59b`. Step 4(a)'s git commit is present only as the documented no-op seam `git_commit_placeholder`. |
> | `ui/schema_compare_panel.py::SchemaComparePanel` — the diff-viewer UI | **Ships**, tested (`tests/ui/test_schema_compare_panel.py`) — commit `dffb59b`. Injected schema-source and `save_migration` callables; no Apply/Execute affordance by design. |
> | **The `Database ▸ "Compare Schemas…"` and `"Save Schema Snapshot…"` menu entries** | **Absent.** `MainWindow._build_database_menu` has no such actions. |
> | **The flow that drives a batch through review → git → execute (step 4)** | **Absent.** Nothing constructs a `DeployPlan`, nothing hosts `SchemaComparePanel`, nothing calls `write_snapshot`. `schema_compare_panel` and `deploy_bundle` are referenced nowhere else in `pgtp_editor/`. |
>
> Concretely: **no user gesture anywhere in the app reaches §18.3's deploy-bundle/compare flow.** The
> close-time reminder *is* wired (`MainWindow._remind_pending_ddl_deploys_on_close` — the "Project close
> is a reminder point" paragraph below, shipped as designed), but it only reminds about `*`-flagged
> candidates; it opens no bundle, no compare view and no snapshot. §18.5's
> sandbox-validation ladder is expected to reuse this same engine rather than re-implementing it.

**Deploy workflow:**

1. Locally `*`-flagged objects (§18.2) are candidates for a deploy bundle.
2. **A blocker is a `*!` object — a deploy *candidate* that is also live-drifted — and any one of them
   blocks the whole batch** (settled 2026-08-06, narrowing an earlier "any `!`-flagged object"; ledger
   §28). Reuses the exact ambiguity-gate/all-or-nothing discipline already established by Diff/Merge
   (§12: refuse the entire batch naming **every** blocker, recovery = resolve then re-run) rather than
   inventing new machinery. Do not let a stale local edit silently overwrite a live DB change that
   happened independently.
   - **A `!`-only object is explicitly *not* a blocker.** With no local edit it is not in the batch, so
     nothing would be written over it — and since single-object Apply (§18.5) routinely leaves objects
     `!`, blocking every deploy on unrelated `!` markers would make the gate un-actionable rather than
     protective. `db/deploy_bundle.py::deploy_blockers` implements exactly this: intersect the `*`
     candidate set with `live_drifted`.
   - A blocked batch is **data, not an exception**: `assemble_deploy_bundle` always returns a
     `DeployPlan`; blocked means `plan.blockers` is non-empty and `plan.bundle is None`, with
     `plan.refusal_message` naming every blocker plus the recovery. "Nothing to deploy" (no candidates,
     an empty bundle) is a *distinct*, deliberately unconflated outcome.
3. Assembled into a single reviewed SQL bundle — **statement order is adjustable, content is not
   editable there** (editing only happens in the single-object editor tabs, §18.5). As shipped, this
   edit-driven bundle is assembled from the checked-out `ddl/*.sql` files' **verbatim saved text**
   (`db/deploy_bundle.py` — `DeployCandidate`/`DeployBundle.sql_text` concatenate exactly what the user
   saved, and a candidate with no SQL is the named refusal `MissingCandidateSql`, never a silent gap; the
   module imports nothing from `db/schema_diff.py`), **not** by running the schema-diff engine over the
   files — what the user reviews is byte-for-byte what was saved. It is still not a second
   diff/generation engine, because it is not a diff/generation engine at all: the diff engine's
   **second entry point** is §18.5's **Generate Deployment SQL** (sandbox vs. target — ledger §28), and
   "one diff/generation engine, two entry points" lives there and in the schema-compare command below.
4. Once the bundle is approved: (a) commit/push to git with versioning — **explicit placeholder, not
   designed, mechanism TBD** — and (b) execute against the live database. Reuses the existing "never
   auto-execute DDL silently" non-goal below — this is a reviewed, explicit action, not automatic.

**Project close is a reminder point, not a forcing point (added 2026-08-03, §18.2).** Closing a project
whose working copies have pending changes:

- **If the `.pgtp` working copy has unpushed changes** relative to the source `.pgtp` (§18.2's checksum
  comparison), offers the **"Deploy .pgtp"** gesture as a convenience prompt.
- **If there are `*`-flagged DDL objects** that are candidates for a batch deploy, **reminds** the user
  they exist — it does **not** open the deploy-bundle flow automatically and does **not** force a
  decision either way.
- **Neither is ever forced.** Closing the project without deploying anything is always available;
  these are reminders surfaced at a natural checkpoint, consistent with the rest of §18's
  embrace-drift, surface-don't-auto-resolve discipline.

**Schema diff & migration engine (shared by both entry points):**

- New pure module `db/schema_diff.py` (mirrors `diff/differ.py`'s contract shape but is
  DB-object-keyed, not XML-node-keyed): `SchemaDifference{kind: added|removed|changed, object_kind:
  table|column|routine|trigger, identity: str, old_def, new_def}`; `diff_schemas(source:
  DatabaseSchema, target: DatabaseSchema) → SchemaDiffResult` — a `list[SchemaDifference]` **subclass**
  carrying the `.unsupported` sidecar (the not-compared names) that this subsection's viewer header and
  refusal behavior load-bear on (`db/schema_diff.py`; read `.unsupported` at the call site, before any
  list-producing transform drops it).
- `db/schema_snapshot.py`: `dump_schema`/`load_schema` — lets a live DB be diffed against a checked-in
  JSON snapshot file, not only DB-to-DB, so a target/desired schema can be versioned.
- `db/migration_gen.py::generate_migration(differences) → str` — ordered CREATE→ALTER→(guarded,
  opt-in)DROP SQL text.
- Viewer `ui/schema_compare_panel.py::SchemaComparePanel`, reusing `diff_merge_panel.py`'s split layout
  (change list + detail pane, default-unchecked = skip — same review discipline as §12). Schemas and the
  save target are **injected callables**, so the widget opens no connection, reads no file and reaches no
  modal dialog; `SchemaDiffResult.unsupported` is captured at compare time and shown in the header, and a
  `table`/`column` entry the generator refuses surfaces as a **named refusal**, never a quietly shortened
  script.
- **Hard non-goal, stated explicitly:** this never auto-executes DDL against a live database from the
  diff view. It only emits a reviewed `.sql` file (**"Save Migration As…"**) for the user's own deploy
  path, or (§18.3 step 4) the explicit, reviewed deploy action above. Auto-apply of DDL is out of scope
  — DDL against production is exactly the class of hard-to-reverse action this tool must not silently
  automate. **This non-goal is about *automatic* and *unreviewed* execution, not about all execution:**
  §18.5's single-object **Apply**, which does execute DDL against the sandbox or the target database, is
  compatible with it precisely because it is neither — it is one object, initiated by hand, behind a
  confirmation naming the object and the database. See §18.2's Apply-vs-Deploy table for which of the two
  is authoritative when both could apply (short answer: **Deploy**).
- **Database menu** gains **"Compare Schemas…"** (source/target: live connection or snapshot file) and
  **"Save Schema Snapshot…"**.

> **Settled: separate commands, one shared engine, target design.** The schema-compare entry point
> above stays a **fully separate sibling command**, not absorbed into the deploy workflow's UI; the
> diff/generation engine stays one engine with two entry points (as shipped: **Compare Schemas…** here
> and §18.5's **Generate Deployment SQL** — the deploy bundle itself is the verbatim-text assembly of
> step 3, not an engine consumer):
>
> - **`Database ▸ "Compare Schemas…"`** stays its own lightweight, **no-project-required** command
>   (live-vs-live, live-vs-snapshot) — useful even with zero DDL-versioning projects involved (e.g.
>   comparing staging vs. prod ad hoc).
> - The DDL-versioning project's **`Deploy`** command (§18.3 steps 1–4 above) is a separate, dedicated
>   flow — it carries the checkout-awareness, the `*!`-blocks-batch ambiguity gate, and the git-commit
>   step that a generic compare tool should not be burdened with.
> - There is never a **second** diff/generation engine: everything that diffs schemas or generates
>   migration SQL goes through the one `db/schema_diff.py`/`db/migration_gen.py` engine, just from
>   distinct entry points with distinct UIs suited to their distinct audiences/guardrails.
> - **Rejected alternative:** a single unified Compare/Deploy screen. Rejected because it would either
>   overload the simple compare tool with project/git machinery it doesn't need, or dilute the deploy
>   workflow's guardrails into a generic diff viewer.

### 18.4 SQL/plpgsql selection formatter

> **Status: implemented end to end — core (2026-08-01) *and* consumer.** The Qt-free package
> `pgtp_editor/sql/` and its mirror `tests/sql/` ship, and `format_selection` **is called**: the host is
> the **DDL object editor** (`ui/ddl_object_editor.py::DdlObjectEditorPanel`, §18.5), where
> `DdlObjectEditorPanel.format_selection` is bound to **`Ctrl+Alt+F`** (a panel-local `QShortcut`) and to
> a context-menu **"Format Selection"** item, both enabled only with a selection (§26/§27 carry the
> binding). Refusals are no longer a contract but **wiring**: the panel emits them and `MainWindow`
> renders them in the Audit panel under the **`[SQL]`** prefix — non-clickable, no line role — distinct
> from §18.5's `[Check]` validation findings (still unbuilt) and §22's `[Lint]`; the three-way
> reservation is in §7. Unchanged: there is **no auto-format mode**, **no "Lint Selection" action**, and
> **no rule catalog** beyond the tokenize/balance floor.

**Problem framing.** Once §18.5's DDL object editor makes plpgsql function/trigger bodies hand-editable,
"uniformity" for that editing means **consistent indentation and line breaks only** — not keyword
casing, not identifier casing, not comma placement/style, not literal values. This subsection defines
the formatter that enforces that narrow notion of uniformity.

**Trigger & scope — explicit-only, no auto-mode, full stop:**

- Invoked **only** by an explicit user action on the current text **selection**: **`Ctrl+Alt+F`** or the
  **"Format Selection"** context-menu item in §18.5's DDL object editor tab, both enabled only when a
  selection exists (§18.5 owns that wiring; §26/§27 record the binding). There is **no** auto-format-on-
  edit and **no** format-on-save, and — unlike Auto Parse XML (§9, off-by-default but togglable) — this
  formatter has **no auto-mode at all**: the user explicitly rejected an auto-mode as "intrusive and
  counterintuitive" during design. Do not add one without a fresh design decision superseding this one.
- Operates on **arbitrary selections** — a complete statement, a bare fragment (`where a = 1`,
  `order by a, b`, `, b, c`, even `;` alone all format), or a chunk of plpgsql control-flow (e.g. a
  `BEGIN...END` block) — not necessarily a whole function or trigger body.
- There is **no "Lint Selection" action** and **no rule catalog** beyond the tokenize/balance floor
  described below (no keyword-casing rule, no comma-style rule, nothing semantic). If future prose
  anywhere implies otherwise, that implication is wrong per this design.

**Core algorithm — hand-built tokenizer + nesting-depth reindenter, not an adopted library:**

Covers both plain-SQL clause structure (`SELECT`/`FROM`/`WHERE`/`JOIN`, paren depth) and plpgsql block
structure (`BEGIN`/`END`, `IF`/`ELSIF`/`END IF`, `LOOP`/`END LOOP`, `CASE`/`WHEN`/`END`). Reindents
**whitespace and line breaks only** — keyword casing, identifier casing, comma placement/style, and
literal values are never touched.

**Module shape (the formatter's five modules — the `sql/` package as a whole has since grown beyond
them: `caret_context.py` for §18.6, `statements.py` for §18.5 D4, see §5's tree; Qt-free, no DB/network
I/O; `tests/sql/` mirrors it):** the package
**`pgtp_editor/sql/`** (name follows the existing `db/`/`schema_learning/`/`analysis/`/`diff/` convention
of §5's layout) contains `keywords.py` (dialect set) → `tokenizer.py` (`Token`, `tokenize`) →
`formatter.py` (`FormatResult`, `format_selection`, the private `_Reindenter`) + `issues.py` (`Issue`),
with `__init__.py` as the façade.

**Public API:**

| Symbol | Shape |
|---|---|
| `format_selection` | `format_selection(text: str, *, indent_unit: str = DEFAULT_INDENT_UNIT) -> FormatResult` (`DEFAULT_INDENT_UNIT = "    "`, four spaces) |
| `FormatResult` | `@dataclass FormatResult{ok: bool, text: str, issues: list[Issue]}` — on refusal `ok=False` and `text` is the input **verbatim**, so even a caller that ignores `ok` cannot corrupt the selection |
| `Issue` | `@dataclass(frozen=True) Issue{message, start, end, start_line, start_col, end_line, end_col, fatal=True}` + property `line == start_line` |
| `tokenize` | `tokenize(text: str) -> list[Token]` — public on `pgtp_editor/sql/tokenizer.py` (lossless, verbatim, **never raises**) |
| `SQL_KEYWORDS` | the shared dialect set (see below) |

`sql/__init__.py`'s `__all__` is exactly `{"format_selection", "FormatResult", "Issue",
"SQL_KEYWORDS"}` and that surface is **test-pinned**; `tokenize`/`Token` are reached through
`pgtp_editor.sql.tokenizer` rather than the façade.

`Issue` **mirrors and extends** `schema_learning/xsd_verify.py`'s `Issue{line, message, fatal}` (§11):
same `message`/`fatal` framing, plus a precise span — 0-based `start`/`end` character offsets into the
input and 1-based `start_line`/`start_col`/`end_line`/`end_col` (`end_col` exclusive) — because this
feature must underline the exact offending construct, not just flag a line. `line` is kept as an alias of
`start_line` so the shape reads as a strict superset. This is a **pattern extension, not a shared
class**: `xsd_verify.Issue` is untouched and `sql.Issue` is a distinct type in the pure `sql/` package.

**Shared dialect source — `SQL_KEYWORDS` lives in the core, not in `ui/`:** the lowercase,
case-insensitively-matched keyword set is defined in **`pgtp_editor/sql/keywords.py::SQL_KEYWORDS`** (a
`frozenset` of 115 members: the highlighter's original §18.1 set plus the plpgsql control keywords the
tokenizer/block tracker need — `elseif`, `elsif`, `exit`, `continue`, `foreach`, `reverse`, `intersect`,
`while`), and `ui/code_editor.py` binds `_SQL_KEYWORDS = SQL_KEYWORDS` for `_CodeHighlighter`'s
`language="sql"` mode (§8). It is still exactly **one** source of truth shared by highlighter and
formatter — but on the correct side of §5's dependency arrow: `sql/` must be Qt-free, so importing the
set *from* `ui/` would have inverted **core must never import ui** (see the Supersession Ledger, §28).
Extend the dialect in `sql/keywords.py`; both consumers see it. `Token.keyword` is a **view** (lowercased
text when it is in the set, else `None`) — never a rewrite; `Token.text` stays verbatim.

**Tokenizer (`sql/tokenizer.py`) — lexical only, no grammar:** kinds are plain string constants
(`whitespace`, `newline`, `line_comment`, `block_comment`, `string`, `quoted_ident`, `dollar_string`,
`number`, `word`, `punct`), matching the codebase's existing `kind: str` convention (`db/ddl_buffer.py`).
`Token{kind, text, start, end, start_line, start_col, end_line, end_col, unterminated, tag}` with
`is_trivia`/`is_opaque`/`keyword`/`is_keyword`/`lowered` views. `OPAQUE_KINDS` = comments, strings,
quoted identifiers, dollar-quoted bodies: their **content is opaque and is never reindented or
line-broken internally**. Postgres specifics: `''`/`""` doubling is an escape (not a terminator), `E'…'`
additionally honors `\'`, `/* */` **nests**, `$$…$$`/`$tag$…$tag$` bodies are one token (`tag` recorded,
`""` for a bare `$$`), and an unterminated opaque region is **not** an exception — it becomes one token
with `unterminated=True` spanning from its opener to end-of-input, so the formatter can refuse with that
exact span.

**Unicode-aware identifiers and all three line endings** are guarantees, not incidentals (both came from
bugs found and fixed during verification):

- Word start/continue follow PostgreSQL's unquoted-identifier rule via `str.isalpha()` / `str.isalnum()`
  (`_` a start char, `_` and `$` continuation chars), so **accented identifiers are never split**
  (`ügyfél_száma` is one `word`). Splitting them let the reindenter insert spaces *inside* an identifier
  and corrupt the SQL.
- `\r\n`, a lone `\n` and a lone `\r` each count as **exactly one** line break for `Issue`/`Token`
  line/column bookkeeping (including a `\r\n` straddling two scan chunks), and dominant-EOL detection
  recognizes **CR-only** text — otherwise every span in classic-Mac text would point at the wrong line.

**Glue rules the tokenizer/spacer must honor** (a naive lexer plus "one space between tokens" would
change meaning, not just layout — the formatter only ever inserts single spaces between tokens, so
anything that must not be separated is kept as one unit or has its space suppressed):

| Construct | Rule |
|---|---|
| `::`, `:=`, `->>`, `#>>`, `#>`, `<=`, `<>`, `!=`, `\|\|`, `..`, `@>`, `<@`, `&&`, `~*`, `!~`, `^@`, … | multi-character operators are **one** `punct` token (longest match first) |
| `a.b`, `a::text`, `a, b` | no space around `.` / `::`; none before `,` `;` `)` `]` |
| `col%TYPE` / `col%ROWTYPE` | `%` glues when followed by `type`/`rowtype`; otherwise it is the modulo operator and keeps its spaces (`a % b`) |
| `$1` | positional parameter is one `word` token (`$ 1` is not valid SQL); a `$` opening a dollar-quote is tested first |
| `E'…'`, `U&'…'`, `B'…'`, `X'…'` | the prefix is glued to the opening quote (part of the `string` token); backslash escapes are honored only for the single-char `E`/`e` form |
| `1..10` | the `..` is the plpgsql range operator, never a fractional point |
| `f(x)`, `count(*)`, `"Q"(1)`, `f(a)(b)` | `(` glues to a preceding **non-keyword** word / quoted ident / `)` / `]` — but `in (1, 2)` and `values (1)` keep the space |
| `array[1]`, `a[i]`, `a[1][2]` | a subscript `[` always glues to its target (word, quoted ident, string, `)` or `]`) |
| unary `-`/`+` | glues to its operand when the token **before the sign** is an opener/operator/comma/keyword (`= -1`, `(-1)`, `, -1`, `select -1`); `a - 1` and `count(*) - 1` stay binary |

**Reindenter (`sql/formatter.py::_Reindenter`) — one frame stack does both indentation and balance,** so
there is a single implementation of "how deep are we". Frames: `root`, `paren`/`bracket`, the block
frames `begin`/`if`/`loop`/`case` (balance-relevant), and the soft frames `declare`/`when` (indent-only,
popped implicitly, never a refusal reason). It walks the significant tokens once (whitespace dropped,
each token carrying how many newlines preceded it), so deep nesting cannot blow the stack.

- **Indent** = `indent_unit` (default **4 spaces**) × open frames, with `exception` and a *statement*
  `else`/`elsif`/`elseif` **dedented one level** so they sit at their block's own level (in a `CASE`
  **expression** an `else` instead pops the branch's soft `when` frame, which aligns it with the `when`s),
  and **+1 level** for clause-continuation lines (a line continuing an open
  `select`/`from`/`where`/… clause at this nesting level).
- **Line breaks** happen before clause starters (`select from where group having order limit offset
  union except intersect join on values set returning with`), before block keywords
  (`begin declare exception else elsif elseif end when`), after `begin`/`declare`/`loop`/`exception`
  headers, after `;`, and after a `--` line comment (anything appended to it would be commented out). A
  JOIN phrase breaks **once**, before its first prefix word (`left outer join` stays on one line, and
  only when a `join` actually follows within three tokens).
- **Author line breaks are preserved wherever no rule applies.** A newline the author put in the source
  is honored, so hand-chosen layout — including **leading-comma style** — survives: this is how "never
  change comma placement or style" is honored while still line-breaking structurally. Blank lines between
  statements are **preserved but capped at one**, and leading blank lines are dropped.
- **`CASE` bodies stay on the `then` line** (expression-friendly: `when 1 then 'a'` is one line). Only a
  **statement** context — the nearest enclosing block being an `IF`, or a `BEGIN`'s `EXCEPTION` part —
  makes `then`/`else` force a break so the body starts on the next line.
- **Layout preservation:** the base indentation of the selection's **first content line** is re-applied
  to every emitted line (so a formatted block stays where it sat in the host document; tabs included);
  the **dominant EOL** (`\r\n` / `\n` / lone `\r`, ties → `\n`) is preserved; a trailing newline is
  preserved (and its absence too). **Empty / whitespace-only input is returned untouched with `ok=True`**
  (nothing to format, nothing to refuse).
- **Guaranteed invariants (test-pinned over a realistic corpus, an adversarial set and seeded fuzz):**
  the output's non-whitespace token texts equal the input's, in order, and only whitespace differs
  (`"".join(out.split()) == "".join(in.split())`); keyword casing, identifier casing, comma placement and
  literal values are never touched; formatting is **deterministic and idempotent**
  (`fmt(fmt(x)) == fmt(x)`, for any `indent_unit`); no input raises or stalls.

**False-positive guards (ordinary DDL must not hit the refusal gate).** These are load-bearing: without
them, everyday statements would be read as unbalanced plpgsql.

| Construct | Interpretation |
|---|---|
| `DROP TABLE IF EXISTS t;` / `CREATE … IF NOT EXISTS` | `IF` is a modifier, **not** a block opener |
| `BEGIN;` and `BEGIN TRANSACTION\|WORK\|ISOLATION …` | transaction control, **not** a plpgsql block — and a later bare `END;` at root level is then accepted instead of reported as unmatched |
| `DECLARE c CURSOR FOR …` (inline `CURSOR` before the next `;`) | a **statement**; a `DECLARE` that *ends its line* opens a plpgsql declaration section (told apart by layout), and that section's frame is popped by its `BEGIN` |
| `EXCEPTION` | **dedents** and marks the enclosing `BEGIN`'s exception part; it does **not** open a block |
| `END IF` / `END LOOP` / `END CASE` | two-token closers — the `if`/`loop`/`case` after `end` is never an opener, and never starts a new line |
| bare `LOOP` vs `FOR … LOOP` / `WHILE … LOOP` | a bare `LOOP` (at start, after `;`, or after `then`/`begin`/`else`/`exception`/`loop`/`declare`) opens a block on its own line; a loop **header** keeps its `LOOP` on the header line |
| `EXIT WHEN done` / `RAISE … WHEN` | ordinary statement tails — `WHEN` only opens an indented branch inside a `CASE` or an `EXCEPTION` part |

**Why build instead of adopt a library (record the investigation, not just the conclusion):**

| Candidate | Why ruled out |
|---|---|
| `sqlparse` | Token-based reformat, historically fragile around dollar-quoted (`$$...$$`) bodies. |
| `sqlfluff` | Confirmed via its own issue tracker (github.com/sqlfluff/sqlfluff #5864, "Linting doesn't work over plpgsql blocks") that it does not lint or fix inside plpgsql blocks. |
| `sqlglot` | Pure Python, real Postgres dialect + pretty-printer, but treats dollar-quoted bodies as **opaque string literals by design** — a generic SQL grammar can't safely reformat procedural plpgsql it doesn't model. Since selections here may themselves **be** plpgsql control-flow fragments (not just whole statements with an opaque body), this blocks the actual use case, not just an edge case. |
| `pgFormatter` / `pg_format` | The one mainstream tool with genuine plpgsql-aware reindentation (`BEGIN`/`END`, `IF`/`THEN`, loops) — but it's a **Perl CPAN module**. Ruled out on cross-platform packaging grounds: bundling/requiring a Perl runtime for a PySide6 desktop app distributed to Windows users is a real distribution liability, not hypothetical. |
| `pylintsql` (github.com/growdashtech/pylintsql) | Investigated because directly referenced during design. Wrong shape entirely: a thin CLI wrapper that scans `--sql`-marked strings inside **Python source files** and runs them through SQLFluff, project-wide — not an in-process function over an editor selection. Also inherits SQLFluff's same plpgsql-block limitation. Not used. |

**Conclusion:** no existing Python-ecosystem library handles plpgsql block reindentation, so a narrow
hand-built tokenizer (indentation/line-breaks only, not a full semantic parser) is the correct scope for
this feature — not a compromise forced by time pressure.

**Safety / refusal behavior — the only gate, unconditional:**

Formatting proceeds whenever the selection can be confidently tokenized and its parens/brackets/blocks
are balanced. If it cannot — an unmatched `BEGIN`/`IF`/`LOOP`/`CASE`/`END`, a stray or unmatched
paren/bracket, a wrong closer (`if … end loop;`), or a selection boundary that splits a string literal,
quoted identifier, `/* */` block comment or `$$…$$` dollar-quote in half — the formatter **refuses
entirely**: `ok=False`, `text` is the input **verbatim** (so the selection is left completely unchanged
even for a caller that ignores `ok`), and `issues` is non-empty with every entry `fatal=True`. Nothing is
guessed or partially applied. This is the project's existing "never a silent wrong result" ethos (cf.
Diff/Merge's ambiguity gate, §12) applied here. This tokenize/balance refusal is **unconditional and the
only thing that blocks formatting** — there is no separate semantic or lint gate layered on top (see the
explicit exclusions below). Clause-level incompleteness is *not* a refusal reason: a bare fragment
(`where a = 1`, `and x = 2`) is a legitimate selection.

- **All refusals are reported, sorted by offset** (`(start, end)`). An unclosed `IF` inside an unclosed
  `BEGIN` yields **two** issues; each carries the **opener's** span (the `begin`, the `if`, the `(`) or
  the offending closer's span (`end if`, `)`), with the line/column repeated in the message text
  (verbatim shape: `Unmatched IF -- no matching END IF in the selection (line 2, column 3).`). A wrong
  closer is reported **once**, against the opener, naming what was found instead
  (`... -- found END loop instead ...`).
- **Exception:** an unterminated string / quoted identifier / dollar-quote / block comment is reported
  **alone** and short-circuits **before** the balance walk, because any balance conclusion drawn past a
  broken quote is unreliable.
- **Reporting contract — now wired:** on refusal, the host reports through the **Audit panel** (§7 — the
  app's single output surface for all actions, already used by
  `[Schema]`/`[Validate]`/`[Find]`/`[PHP]`-prefixed lines) under the **`[SQL]`** prefix, and uses the
  `Issue` span to **underline the exact construct** (e.g. the specific unmatched `BEGIN`) rather than
  flagging the whole line — the span is carried precisely for that. The host is §18.5's DDL object editor
  tab (`DdlObjectEditorPanel`), which owns the transient underline (`setExtraSelections`, panel-local per
  carve-out 4) and emits refusals to `MainWindow`'s `[SQL]` Audit handler. The core is unchanged by the
  host's arrival.

**Explicitly out of scope of this subsection (deferred/future, not designed here):**

1. **The DDL object editor UI surface itself** — now **designed in §18.5** (a *new* editable per-object
   tab, `ui/ddl_object_editor.py::DdlObjectEditorPanel`; note it is **not** §18.1's read-only
   `EditorPanel` made editable — that panel stays read-only permanently). This subsection still covers
   only the reusable formatter core; the tab, its context menu, the `Ctrl+Alt+F` action, the
   selection-only enablement, the single-undo-step replacement and the `[SQL]` Audit reporting all
   belong to §18.5 — and all ship (this subsection's own status header above: implemented, core **and**
   consumer).
2. **Semantic/existence linting** (verifying that referenced tables/columns/functions actually exist) —
   **no longer merely deferred: it is designed in §18.5** as the sandbox-backed validation ladder
   (schema-only scratch PostgreSQL + the `okbob/plpgsql_check` extension). It remains **entirely outside
   `format_selection`'s refusal gate**, which stays tokenize/balance only, runs offline, and never
   touches a database. The two are separate surfaces reporting under separate Audit prefixes (`[SQL]`
   formatter refusals vs. `[Check]` validation findings, §7).
3. To restate plainly: there is **no** "Lint Selection" action, **no** rule catalog beyond the
   tokenize/balance floor, and **no** auto-format mode. Any of these appearing designed elsewhere in this
   document would be drift from this settled decision.

### 18.5 The DDL object editor, apply & sandbox validation

> **Status (audited 2026-08-06, re-audited the same day after the Apply/sandbox-controller work landed):
> partly implemented — the *editor* half and the *apply/sandbox-lifecycle* half ship; the
> *validate/execute* half does not.**
>
> **Ships:**
> - `ui/ddl_object_editor.py::DdlObjectEditorPanel` + `DdlObjectRef` — the editable single-object tab.
> - **Dynamic, key-addressed center tabs**: `CenterStage.open_ddl_object_tab(ref, text,
>   resolve_save_path=…, key=…)`, keyed on `DdlObjectRef.key` (never a remembered index), with the
>   append-only/tail-only discipline and its regression test (carve-out 9).
> - **Context menus** on `BrowserPanel.tree` and the DDL `EditorPanel` — `Edit <qualified>…` and the
>   §18.2 checkout variant, both via the `edit_requested(ref, source)` / `checkout_requested` signals.
> - **Three entry points into the same tab**: Edit… from the browser tree, Edit… from the read-only
>   buffer, and FQ-002's creation dialogs (D1's third entry point).
> - **Save / Save As** over the injected `resolve_save_path` seam (§18.2's entire hook).
> - **Format Selection** (`Ctrl+Alt+F` / context menu, §18.4) and **§18.6 Ctrl+Space completion**
>   (`set_schema_index`, injected per open tab), including the unattached-trigger table picker.
> - **The tab's Apply gestures and the `[Check]` contract**: `apply_to_sandbox()`/`apply_to_target()`/
>   **"Deploy this edit…"**, the conditional button row (absent when a seam is unwired — carve-out 2
>   honoured), all four Apply-to-Target preconditions, `record_check_report`/`last_check_report`/
>   `text_sha1`/`applied_sha1`, and the duck-typed `CheckReport`/`ApplyOutcome` readers
>   (`tier_outcomes`/`report_blockers`/`report_unverified`) — the panel imports neither `db/ddl_check.py`
>   nor `db/apply.py`, by design.
> - **The whole Qt-free sandbox layer, `db/sandbox.py`** — `SandboxSession` (`apply`/`applied`/`reset`)
>   and its `SandboxExecutor` seam, `open_sandbox`'s ownership gate, `create_sandbox_database`,
>   `provision_sandbox`, `build_baseline_sql`, D2a's `clone_data`, `install_gate`/
>   `install_plpgsql_check`, `LocalPostgresBackend` — **and its UI host**
>   `ui/sandbox_controller.py::SandboxController`, which owns the one session, runs every operation off
>   the GUI thread and refuses each destructive one unless the injected `confirm_destructive` approves.
>
> **Does not ship — the validate/execute lane:**
> - `db/apply.py` — the codebase's would-be **first DB write path**, with the notice-capture channel tier
>   1 depends on. Absent; the panel's `apply_to_target` seam therefore has nothing real behind it yet.
> - `db/ddl_check.py` and the **D3 validation ladder**; consequently the **`[Check]` findings channel**
>   (D3a) is still a contract — only the narrative channel (`check_reported`) exists (§18.4's `[SQL]`
>   refusals *are* wired — do not confuse the two prefixes).
> - **`db/sandbox_query.py` and the Sandbox SQL Console (D4)** — designed 2026-08-06, nothing built.
> - **The MainWindow wiring** that constructs the `SandboxController`, opens a session and passes
>   `apply_to_sandbox`/`apply_to_target`/`live_identity`/the label and confirm seams into each open tab —
>   without it the button row is absent in the running app even though the panel supports it.
> - **Generate Deployment SQL — output rank 1 — is not built**, and neither are the Database-menu entries
>   this subsection specifies.
>
> **`db/schema_diff.py`/`db/migration_gen.py` landed under §18.3** for the `routine`/`trigger` cases; the
> ladder and the deployment-script generation must call them once they exist rather than duplicating
> diff/migration logic. §18.1's browsing substrate and §18.4's formatter are the other implemented
> substrates this builds on.
>
> **This subsection is the single specification of the editable DDL tab.** §18.2 (projects, checkout,
> markers) references it and changes only *where the tab's buffer loads from and saves to*; it does not
> restate it and does not introduce a second editable surface. Two parallel design sessions on
> 2026-08-02 produced overlapping drafts of this tab; they are reconciled here, and the overrides are in
> the Supersession Ledger (§28).

#### The three outputs, ranked — read this before anything else

An earlier reading of this section as *"an editable tab with a lint target"* is **wrong** and is
superseded (§28). The feature's outputs are ranked by **value**, and the ranking is what the design must
serve:

| Rank | Output | What it is |
|---|---|---|
| **1** | **Generate Deployment SQL — THE deliverable** | Sandbox = **desired state**, production = **current state**, output = **one reviewed `.sql` migration script**, run once, to upgrade the real database. Built on `db/schema_diff.py` + `db/migration_gen.py` to §18.3's exact shapes. |
| **2** | **The stateful sandbox** | An accumulating, executable **desired state** you can prove is coherent (it compiles, it checks) *before* it is diffed. Not a scratch pad that resets between checks. |
| **3** | **Per-object Save / Apply** | A **convenience** and the **§18.2 precursor** — `Save As… .sql` is exactly §18.2's future `ddl/<schema>.<name>.sql` arriving early. Genuinely useful; **demoted from headline**. |

Build order follows the ranking's dependencies rather than the ranking itself: the write/read
capabilities and the connection profiles first (invisible infrastructure), then the sandbox
(`db/sandbox.py`) and the ladder (`db/ddl_check.py`), then the editable tab (which ships useful with **no
sandbox at all** — edit + Save As), then sandbox setup, then check wiring, and **finally the deployment
script**, which is worthless without validation: never ship a deployment script assembled from routines
nobody proved compile. The last thing built is the first thing the user cares about.

**Why the editor and the sandbox are one feature, not two.** A hand-editable DDL tab with no feedback
loop teaches the user nothing until the moment it is most expensive to learn. The alternatives to a
sandbox are all worse:

- **Deploy-time discovery** (§18.3) — the user finds out whether their plpgsql compiles at the exact
  moment the tool exists to make safe.
- **Apply-to-target discovery** — even with Apply's confirmation gate (below), *using production as your
  compiler* is precisely the outward effect this app is built to avoid; a confirm dialog makes an action
  deliberate, it does not make it a feedback loop.
- **Formatter-as-proxy** (§18.4) — the formatter is indentation and line breaks only, with no semantic
  rule and no database access at all. It can tell you your `BEGIN` is unmatched; it can never tell you
  `NEW.custmer_id` is a typo.

Reinforcing this: `pg_dump` sets `check_function_bodies = off` during restore, so a restored database has
had **zero** validation of its function bodies — "it restored cleanly" says nothing about whether the
routines compile. Editor and sandbox are therefore specified together and built together.

#### D1 — Editor scope: a single-object editable tab, project-decoupled for v1

The loop is **edit → validate against the sandbox → save, and/or explicitly apply**. Right-click an
object → **Edit…** opens a new **single-object editable tab** in `CenterStage` holding just that one
routine or trigger.

- **v1 has no `ddl/` folder, no project-settings JSON/deploy manifest, and no `*`/`!` state markers.**
  All three are §18.2 concepts; **none is a prerequisite** for editing one function with feedback. The
  buffer is loaded from the live introspected definition (`RoutineInfo.source` /
  `TriggerInfo.definition`, §17/§18.1).
- **The tab is written against an injected load/save pair, never a hard-coded source.** This is a
  structural requirement, not a style preference: it is the entire mechanism by which §18.2 layers on
  later **without rework** — checkout swaps the pair (live definition → checked-out
  `ddl/<schema>.<name>.sql`) and adds marker rendering on `BrowserPanel`, and the tab, its command set,
  its validation and its Apply gestures are untouched. The tab must not import `db/ddl_project.py`, must
  not know what a project is, and must not branch on whether one is open.
- **Rejected: build full §18.2 first.** *(Operative rationale — this reverses an earlier decision, §28.)*
  A git project, a manifest, a hash scheme and a marker recompute is a large prerequisite to place in
  front of "edit one function and find out whether it compiles."
- **Rejected: make the multi-object `EditorPanel` buffer editable in place.** A regenerated whole-schema
  buffer cannot carry per-object dirty state, per-object validation or per-object apply, and it conflicts
  with §18.2's file-per-object model. `EditorPanel` stays read-only **permanently** (§18.1), not
  provisionally.

**Two entry points for *editing an existing object*, both right-click, converging on one operation.**
(A third gesture — *creating* an object that does not exist yet — opens the same tab and is described after
this table.)

| Entry point | Gesture | Resolution |
|---|---|---|
| `BrowserPanel.tree` (§18.1, left dock "DDL Objects") | right-click an **object row** ▸ **Edit…** | the row's `DdlObjectSpan` (`Qt.ItemDataRole.UserRole`, `_SPAN_ROLE`) |
| DDL `EditorPanel`'s read-only SQL buffer (center "DDL Explorer" tab) | right-click inside an object's span ▸ **Edit \<schema>.\<name>(\<argtypes>)…** (the span's full signature, so two overloads' menu entries differ; triggers read **Edit \<schema>.\<table>.\<name>…**) | the retained `DdlObjectSpan` whose `start_line..end_line` contains the clicked line |

- **`EditorPanel` retains its span list** (`self._spans`) for the second entry point — the
  once-required amendment is **done**: `set_ddl_text(text, spans=None, schema=None)` keeps the spans
  after converting them to fold regions (§18.1), and its third parameter additionally retains the live
  `DatabaseSchema` the edit resolution (`resolve_edit_target`) needs alongside them.
- **Left-click behavior is unchanged** on both surfaces: the tree still emits `navigate_requested(line)`
  and the buffer still navigates top-aligned (§18.1).
- **Argument-name child leaves are not editable targets** — they carry no span (`_SPAN_ROLE` unset,
  §18.1), so their context menu offers no Edit. Only object rows (routine leaves and both trigger
  occurrences) do.
- **Widget idioms, matching what this codebase already does:** the tree uses
  `setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)` + `customContextMenuRequested` (the
  `coherence_panel.py` / `project_tree.py` pattern); the editor overrides `contextMenuEvent` and extends
  `createStandardContextMenu()` (the `xml_editor.py` pattern), moving the caret to the clicked document
  position first so the resolved span reflects the click and not a stale caret.
- Neither entry point writes to a database. With a project open, §18.2 adds a second variant of the
  gesture — **Check Out for Versioning** — which performs a checkout first and then opens this same tab
  with its load/save pair repointed.

**A third entry point opens this same tab for an object that does not exist yet (FQ-002, 2026-08-06, §28).**
The two rows above are both *Edit an existing object*; **creation** is a distinct gesture and is specified
in §18.1 ("Creating brand-new objects from the Explorer"): the Add Trigger / Add Function-or-Procedure
dialogs build a `DdlObjectRef` for a not-yet-existing object and call the same
`CenterStage.open_ddl_object_tab(ref, text, …)` with a generated **skeleton** (`db/ddl_skeleton.py`) as the
buffer text. Consequences for this subsection, all of them *nothing to change*:

- The ref is **not** resolved through `ui/ddl_buffer_panel.py::resolve_edit_target` — that helper looks the
  object up in the live `DatabaseSchema` and correctly returns `None` for something the database has never
  heard of. Creation builds its ref from the dialog's own fields instead; `resolve_edit_target` remains the
  single identity-derivation point for the two **edit** entry points and is unchanged.
- Tab identity, title/tooltip rules (`short_title`/`qualified`), dirty tracking, the close prompt, Save /
  Save As… (`resolve_save_path`, `default_file_name`), Format Selection and §18.6 completion all behave
  exactly as for an edited object — the panel never knew whether the DB holds the object, and must not
  start branching on it.
- The tab still **never writes to a database**. A created object reaches the database only through the
  ordinary Apply (§18.5) or Deploy (§18.3) gestures, on the user's explicit command.

**Tab shape (`ui/ddl_object_editor.py::DdlObjectEditorPanel`).** A **new tab type**, distinct from the
read-only `EditorPanel`, **one tab per object**. It hosts the **existing**
`ui/code_editor.py::CodeEditor` in `language="sql"` mode made **editable** (`setReadOnly(False)`) — the
same widget, highlighter, 4-character tab stop and `ui/editor_gutter.py::GutterBookmarkFoldMixin`
gutter/bookmarks/folding the read-only DDL Explorer uses (§8/§18.1) — plus its own `FindReplaceBar`
instance, following the established per-tab document-routing precedent (Edit XSD, DDL Explorer; §7/§15).

- **Re-invoking Edit on an already-open object focuses the existing tab** — never a second tab for the
  same object.
- **Title** = the object's short identity (`recalc`, `fmt(integer)`, `orders.trg_audit`) plus a dirty
  marker (the `" *"` convention the Edit XSD tab already uses, §11); **tooltip** = the full source
  identity (the qualified object name in v1, the absolute file path once checked out).
- **Closable.** Closing with unsaved changes prompts — reusing the established Edit-XSD pattern where
  the **tab signals the MainWindow** to run the confirm (`CenterStage.xsd_close_requested` →
  `MainWindow._on_xsd_close_requested` → `_confirm_close_xsd()`), rather than the tab deciding for
  itself. Save / Discard / Cancel; on Cancel the tab stays open and dirty.
- **Deliberately no `.bak` sidecar** on the file-backed variant — unlike `.pgtp` save (§19) and unlike
  `curated.xsd` import (§11). The file is git-tracked and **git is the history**; a `.bak` beside it
  would be untracked noise inside a versioned tree. This divergence from §19 is intentional.
- **A small button row** carries the three sandbox gestures — **Apply to Sandbox** / **Check** / **Check
  without applying** — each of which merely **emits a signal**; MainWindow owns every piece of DB work,
  off-thread. The same three are reachable from the Database menu and the tab's context menu (§26).
  **Not in v1** — see the v1 scope carve-outs below: v1 ships **no button row at all** rather than three
  dead or permanently-disabled buttons. The design above is what the row becomes when the sandbox lane
  lands; it is not a reversal.
- The panel holds an **`applied_sha1`** slot so it can render *"changed since you last applied it"*
  against the sandbox working set (D2), and so **Check** on a diverged buffer emits a `[Check]` caveat
  line instead of silently validating a stale version.
- **`resolve_save_path: Callable[[], Path | None]`** is the injected save half in concrete form: it
  returns the panel's remembered `_save_path`, and **when there is none it runs Save As…** (below) and
  returns what the user picked, or `None` if they cancelled. **§18.2's entire change is this one function
  returning `project.ddl_dir / <the §18.2 filename>`** — no restructure.

Consequences for existing wiring — **all extensions of existing dispatchers, no new machinery**:

- `FindValidateController.active_find_bar()` gains a branch for the active editable DDL tab (Ctrl+F / F3,
  and Ctrl+R, whose **Replace is live** here — unlike in the read-only DDL Explorer, where
  `CodeEditor.replace_current_selection` returns early on `isReadOnly()`). **Find All is inert** in this
  tab (its button is present but its target is unsupported) — see the v1 scope carve-outs. *(Since FQ-016
  the bar is permanently visible and Find All / Replace All are button-only, §15/§27.)*
- `active_bookmark_editor()` gains the same branch — still with **no** tab-switching side effect (§8).
- `_save_active_tab()` gains a branch (§7). The read-only DDL Explorer still gets none: it is
  DB-synthesized and has no save path, which is why Ctrl+S's routing is asymmetric to Ctrl+F's.
- This tab is §18.4's **first consumer** (Format Selection, below).

**`CenterStage` needs dynamic tabs — the largest structural piece of this design.** Today every tab is
created in `CenterStage.__init__` with a stored integer index (`raw_xml_tab_index`,
`diff_merge_tab_index`, `caption_management_tab_index`, `xsd_tab_index`, `ddl_tab_index`,
`manual_tab_index`) and shown/hidden via `setTabVisible`; `_on_tab_close_requested` dispatches by
comparing the closed index to those constants. Per-object tabs are created at **runtime**, so:

- Dynamic object tabs are **always appended after the fixed set**, so the stored fixed indices never
  shift and every existing index comparison stays correct.
- Dynamic tabs are looked up through a **key → widget map**, never by a remembered index — close/reorder
  must not be able to make an index stale. The key is a stable per-object identity: the object's
  `DdlObjectSpan` identity (kind + schema + name + argtypes, or + table for a trigger) project-less, and
  the **resolved absolute `ddl/*.sql` path** once checked out (§18.2).
- Close dispatch must therefore fall through from the fixed-index comparisons to a map lookup.

**Editor command set.** Inherited from the generic code editor rather than reimplemented:

| Affordance | Source |
|---|---|
| Undo / redo | **`QPlainTextEdit`'s native undo stack — the editor's own, never the project history.** Pinned invariant, see below |
| Find / Find Next / Replace / Replace All | its own **permanently visible** `FindReplaceBar` instance (FQ-016) + a branch in `active_find_bar` (§7/§15) |
| Find All | **inert in this tab** (the DDL Explorer precedent) — see the v1 scope carve-outs |
| Bookmarks (Ctrl+F2 / F2 / Shift+F2) + gutter + folding | `ui/editor_gutter.py::GutterBookmarkFoldMixin` (§8) + a branch in `active_bookmark_editor` |
| Auto-close & selection-wrap for brackets/quotes; bracket-select (Ctrl+Shift+B) | `CodeEditor.keyPressEvent` / `enclosing_bracket_span` (§8) — already generic, no change |
| 4-character tab stop, SQL highlighting, top-aligned `navigate_to_line` | `CodeEditor`'s `language="sql"` mode (§8/§18.1) — already generic |
| Standard context menu + the entries below | `createStandardContextMenu()` extended (the `xml_editor.py` idiom) |

**Two affordances are *not* inherited and are new work if wanted at all** (recorded because an earlier
draft wrongly listed them as inherited): a **wrap-lines toggle** — `CodeEditor.__init__` hard-sets
`QPlainTextEdit.LineWrapMode.NoWrap` and defines no context menu at all, so the Raw XML editor's
checkable wrap entry has no equivalent here; and **goto-line** — **no editor in the app has one**
(`Ctrl+G` is the caption grid's, §13). Neither is required by this design; if either is built it is an
additive `CodeEditor` feature in its own right, not a DDL-tab detail.

**Fold regions come from the object's own structure**, not from `EditorPanel`'s whole-buffer
`DdlObjectSpan` index: a single-object buffer has no banner spans. Regions are installed through the same
`CodeEditor.set_fold_regions(regions)` seam (§8).

**XML-editor affordances that deliberately do NOT apply here** (stated so a reader does not expect
them): **Select Parent Block** (Ctrl+Shift+A — XML tag hierarchy), **Add attribute ▸**, **Go To XSD**
(Ctrl+L), **Auto Parse XML**, attribute autocomplete and hover annotations, **Properties-panel sync**,
and **editor↔tree sync**. All are XML/schema-driven and meaningless for a SQL buffer. Since FQ-015 the
first of those is *enforced*, not merely absent by convention: `Select ▸ Select Parent Block` is **hidden**
whenever this tab is active, taking Ctrl+Shift+A with it (§7/§8). **Select Enclosing Block** (Ctrl+Shift+B)
does apply here, as the innermost balanced-bracket span.

#### v1 implementation scope — six settled carve-outs (2026-08-02)

Settled by the project owner while planning the tab's v1 implementation. These are **scope decisions for
the first shipping increment**, not reversals of the design above, except where a row says otherwise.

**1 — `Ctrl+Z` in the object tab uses the editor's NATIVE undo, and this is a pinned invariant with a
mandatory regression test.** The trap is real and silent: `main_window.py:401` installs a **window-level**
`QShortcut(QKeySequence("Ctrl+Z"))` wired to `MainWindow._undo`, which drives the **project snapshot
history** (`SnapshotHistory`, §7/§9) over the **Raw XML buffer**. `XmlEditor` deliberately consumes
Ctrl+Z in `keyPressEvent` and re-emits `undo_requested` so both paths reach the same `_undo`; the Edit
XSD tab does the same but routes its re-emission straight back into its own editor
(`stage.xsd_editor.undo_requested.connect(stage.xsd_editor.undo)`, `main_window.py:425`). **`CodeEditor`
does neither** — it neither consumes nor re-emits — so with the object tab focused the window shortcut
fires and **Ctrl+Z would revert the Raw XML project buffer while the user is looking at SQL.** The
required behavior:

- `Ctrl+Z` / `Ctrl+Y` with a `DdlObjectEditorPanel` active operate **only** on that editor's own
  `QPlainTextEdit` undo stack. The project history is not touched, not advanced and not rewound.
- Realized the same way the XSD tab does it — the editor consumes the key and the tab routes it back to
  its own `undo()`/`redo()` — so the window shortcut cannot also fire (no double-undo), rather than by
  disabling the window shortcut, which would break Ctrl+Z everywhere else.
- **Mandatory regression test** (`tests/ui/test_ddl_object_editor.py`): with an object tab active and a
  dirty Raw XML document, pressing Ctrl+Z changes the object buffer and leaves the Raw XML text
  **byte-identical**. This is a silent-wrong-result guard, not a nicety.

**2 — No sandbox button row in v1.** *Apply to Sandbox* / *Check* / *Check without applying* (and their
Database-menu twins) have their consumers in another lane; v1 therefore ships **no button row and none of
the three actions** rather than dead or permanently-disabled controls. A **v1 scope carve-out, not a
design reversal** — the button row, the three gestures, `applied_sha1` and the `[Check]` caveat line stay
specified above and arrive with `db/sandbox.py` + `db/ddl_check.py`.

**3 — Find All stays inert in the object tab; Find / Find Next / Replace / Replace All all work.**
This matches the **existing DDL Explorer precedent**: `main_window.py::_populate_find_all_results(term,
target="raw"|"xsd")` resolves its editor and bar from a two-valued `target` and understands nothing else,
so the DDL Explorer's Find All is already an unwired no-op. Generalizing that dispatcher to arbitrary
per-tab editors is its own change and is not v1 scope. The bar's Find All control is present (it is the
shared `FindReplaceBar`) and simply produces no results; nothing reports a false "0 matches" as though
the buffer had been searched.

**4 — The Format-Selection transient underline is panel-local.** It is rendered by
`DdlObjectEditorPanel` calling `setExtraSelections` on its `CodeEditor` — verified: **`CodeEditor` never
calls `setExtraSelections` today** (only `ui/xml_editor.py` does), so this is new, panel-owned state and
**not** a `CodeEditor` feature. It is cleared on **the next edit** (`textChanged`) or **the next format
attempt**, whichever comes first; it is never persisted, never restored on tab focus, and never
accumulated across refusals.

**5 — Re-running Database ▸ DDL Explorer leaves open object tabs untouched and silent.** A fresh
`fetch_routines_and_triggers` rebuilds the read-only buffer and the tree only. Open
`DdlObjectEditorPanel` tabs are **not** reloaded, **not** marked, **not** closed and **not** prompted
about — even though their live definitions may have changed underneath them. Rationale: the tab's buffer
is the user's in-progress edit, and the one thing worse than a stale buffer is a tool that discards
hand-written SQL to resync itself. Drift detection against the live database is §18.2's `!` marker and
§18.5's mandatory pre-generate drift check, both of which arrive later; **v1 states the gap rather than
half-solving it**.

**6 — `[SQL]` Audit lines are not clickable.** Formatter-refusal lines carry **no line role** on their
`QListWidgetItem` — the same treatment the existing `[Find]` summary line gets — so clicking one does
nothing. The refusal's location is already conveyed by the transient underline over the exact offending
span (carve-out 4) and by the line/column repeated in the `Issue` message text (§18.4). Click-to-navigate
Audit lines remain `[Validate]`, `[Find]` results and (later) `[Check]`.

#### Format Selection — §18.4's formatter finally gets its consumer

- **Format Selection**, bound to **`Ctrl+Alt+F`**, plus a **context-menu item** in this tab. Both are
  **enabled only when there is a selection**. `Ctrl+Alt+F` was chosen because it did not collide with the
  then-existing `Ctrl+Shift+F` Find All — §18.4 left the binding TBD and this is the choice. *(That
  collision is moot since FQ-016 deleted `Ctrl+Shift+F`, §27; the binding stands unchanged.)*
- Calls `sql.format_selection(selected_text)` (§18.4).
- **On success** the selection is replaced as a **single undo step** (one `QTextCursor` edit block), so
  one Ctrl+Z reverts the whole reformat.
- **On refusal** (`ok=False`) the text is left **completely unchanged** — `FormatResult.text` is the
  input verbatim, so even a caller that ignored `ok` could not corrupt it — and **each `Issue` is
  reported to the Audit panel** (§7) with the **`[SQL]`** prefix — **not clickable, no line role**
  (carve-out 6 above). The offending span is additionally **underlined in the editor** using the
  `Issue`'s precise `start`/`end` — which is *why* §18.4's `Issue` carries a span at all. The underline
  is **panel-local** (`DdlObjectEditorPanel` owns the `setExtraSelections` call; `CodeEditor` has no such
  feature) and **transient** — cleared on the next edit or the next format attempt — never persistent
  state.
- Offered **only in this tab** — **not** in the read-only DDL Explorer buffer, where a reformat could not
  be applied anyway.
- Restated from §18.4 and unchanged: **selection-only**, **no auto-format mode**, **no "Lint
  Selection"**, and **no rule catalog beyond the tokenize/balance floor**.

#### Save and Apply are two distinct, explicit user gestures

**Neither is ever automatic, and neither is ever implied by the other.**

| Gesture | What it does | Trigger |
|---|---|---|
| **Save** | Persists the edited text through the tab's **injected save callback** — **a real `.sql` file on disk chosen via Save As… in v1** (below), the checked-out `ddl/*.sql` file under §18.2. **Touches no database, ever.** | `Ctrl+S` via `_save_active_tab` (§7), File ▸ Save |
| **Apply** | **Executes** the buffer's DDL against a database — the **sandbox** (where it is *meant* to persist, D2) or the **target** (behind the hard gates below) — through the write seam below. **Persists nothing to disk** and clears no dirty state. | Explicit menu / context-menu / panel action only. **Deliberately no keyboard shortcut** — an irreversible outward effect must not be one keystroke away. |

**v1 Save ships `Save As… .sql` — a real file, not an in-session buffer (settled 2026-08-02).** An
earlier reading of this section left it ambiguous whether v1 *"persists the in-session buffer"* or
whether `resolve_save_path` simply *"returns `None` until Save As picks one"*; it is resolved **in favor
of a real file** (§28), which is consistent with this section's own output ranking: *"`Save As… .sql` is
exactly §18.2's future `ddl/<schema>.<name>.sql` arriving early."* An editor whose Save produces nothing
durable is not a save.

- **`Ctrl+S` with no remembered path opens a file dialog** (`QFileDialog.getSaveFileName`,
  `SQL files (*.sql)`), prefilled with the object's identity-derived name — the sole-holder form of
  §18.2's scheme, `<schema>.<name>.sql` for a routine and `<schema>.<table>.<trigger>.sql` for a trigger
  — so the v1 file a user saves is already shaped like the checked-out file §18.2 will manage.
- **The chosen path is remembered** on the panel (`_save_path`) for the rest of the session, so every
  subsequent `Ctrl+S` writes silently to it: UTF-8, `newline=""`, and **deliberately no `.bak` sidecar**
  (the same intentional divergence from §19 stated above). Saving clears the dirty marker.
- **Cancelling the dialog cancels the save.** Nothing is written, the tab stays dirty, and no error is
  reported — a cancelled dialog is not a failure.
- **Cancelling Save As reached from the close-confirmation prompt ABORTS THE CLOSE.** Close ▸ *Save* on a
  never-saved tab runs Save As…; if the user cancels it, the tab **stays open and dirty** — exactly as
  Close ▸ *Cancel* would. The confirm flow must therefore propagate the save's success/cancel back to
  `MainWindow._on_ddl_object_close_requested` rather than assuming *Save* succeeded. Silently discarding
  an edit because a file dialog was dismissed is a data-loss bug, not a corner case.
- **Save still never touches a database.** Save As writes a file; Apply executes DDL; neither ever
  implies the other.
- **`Ctrl+Shift+S` stays project-only — it does NOT re-route to the object tab.** It remains File ▸ Save
  As for the `.pgtp` project (`main_window.py::_save_project_as`), unchanged. Recommended and settled
  this way because `Ctrl+Shift+S` today is bound directly to `_save_project_as` (not through a
  `_save_active_tab`-style dispatcher), because the object tab's "save to a new path" need is already met
  by the first `Ctrl+S`, and because a *"save the current project under a new name"* command that
  silently means *"write this one function somewhere"* when a tab happens to be focused is precisely the
  kind of which-system ambiguity §19 and §12 exist to prevent. A **Save As…** entry in the object tab's
  own context menu is the additive, unambiguous way to re-point an already-saved tab; it is optional in
  v1 and takes no shortcut.

#### "Deploy this edit…" — the explicit per-edit destination command (settled 2026-08-05)

**Ctrl+S remains exactly what it is today — a plain file save that never touches a database.** This
command does not reopen or contradict that; it adds a **separately-triggered, explicit** action that
presents the three coexisting per-edit destinations described in §18.2 (*"deploying a DDL edit is an
explicit per-edit choice among three coexisting destinations, and the user picks which one on every
edit"*) as one command, instead of requiring the user to already know which of three separate gestures
(Ctrl+S, the Apply-to-Sandbox action, the Apply-to-Target action) they want before they start.

- **Trigger — a per-tab action on the DDL object editor, not a keyboard shortcut.** Following the existing
  idiom for other tab-local actions on this same tab (Format Selection, §18.4/§18.5 — a context-menu item
  plus a bound key), **"Deploy this edit…"** is exposed as a **context-menu item** on `DdlObjectEditorPanel`
  (and, matching this tab's existing pattern of also surfacing its actions on a menu, a Database-menu
  entry alongside the tab's other five §18.5 actions, §26) — **deliberately no keyboard shortcut**, for the
  same reason Apply itself takes none: *"an irreversible outward effect must not be one keystroke away."*
  A toolbar button is an acceptable alternative surface if the implementation finds it fits better, but a
  bound shortcut does not.
- **What it does — opens the existing 3-way destination choice, reusing the already-built gestures rather
  than duplicating them.** Invoking it presents the three destinations named in §18.2's table (Apply to
  Sandbox / Save for a future batch deploy / Apply to Target) and, once the user picks one, **delegates
  straight to that gesture's existing, already-specified wiring** — it is a picker in front of the three
  gestures, not a fourth thing that writes DDL or files on its own:
  - **Apply to Sandbox** → the existing `apply_and_check(session, ref, ddl_text, caps)` entry point (D3),
    confirm-gated exactly as today.
  - **Save (for a future batch deploy)** → the existing plain **Save** gesture described above — writes
    the buffer to disk (`Save As… .sql` in v1; the checked-out `ddl/*.sql` file once §18.2 checkout is in
    play) and touches no database, exactly as Save always has.
  - **Apply to Target** → the existing Apply-to-target path, unchanged: still gated behind all four hard
    preconditions (signature-change refusal, green-sandbox-validation gate with a named override, the
    transactional apply-with-no-revert-snapshot caveat, and the confirmation naming the object **and** the
    database) and still reports to the Audit panel under `[Check]`.
- **No new write path, no new confirmation mechanism, no new Applier.** This command adds a **selection
  UI** in front of three gestures that already exist and are already specified above and in D3/the write
  seam — `db/apply.py::apply_ddl`, `db/ddl_check.py`'s three entry points, and the plain-file Save
  callback are **not** duplicated, forked, or given a second code path for this entry point.
- **Preserves the "irreversible action must not be one keystroke away" invariant — it does not reopen
  it.** The command itself carries no shortcut, and picking "Apply to Target" from it still runs through
  every one of Apply-to-target's existing hard preconditions and its own explicit confirmation. Nothing
  about this command shortens or bypasses any existing gate.

Validation (the ladder in D3) is a third, likewise explicit gesture. It comes in **two modes** and the
difference is user-visible: **Apply to Sandbox → Check** *commits* to the sandbox (that is the point —
the sandbox is the accumulating desired state, D2), while **Check without applying** runs the same
ladder inside a transaction that is explicitly rolled back. The earlier framing — *"validation writes
nothing durable anywhere; everything it does inside the sandbox is rolled back"* — is **retracted**
(§28).

#### The write seam — `db/apply.py`, the codebase's first database write path

Until now the app has had exactly one connection-opening function,
`db/introspect.py::run_queries(params, sql_list, connect_timeout=10)`, which opens one `psycopg`
connection, `execute`s each statement, `fetchall`s, and closes it in a `finally` — **no `COMMIT`, no
explicit `ROLLBACK`, no `autocommit`** (verified in the code). Apply is the first feature that needs to
write. The design is deliberately conservative:

- **A separate, clearly-named write seam: the new Qt-free module `db/apply.py`.** `run_queries` is
  **never widened** — not with an `autocommit` flag, not with a commit path, not with "just this one
  DDL statement". The read seam stays read-only so that *"does this code write to the database?"* stays
  answerable by **which function is called**, statically, without reading arguments. (Distinct from
  `diff/apply.py::apply_differences`, which mutates an lxml tree and touches no database — different
  package, different domain.)
  Nothing about the two-seam split costs the ladder anything, because the ladder's single
  session/transaction lives entirely on the write side.

> **Settled, not provisional — the competing proposal was withdrawn by its author.** Phase 1 of
> `plans/2026-08-02-ddl-object-editor-and-sandbox.md` instead widened `db/introspect.py::run_queries`
> with `autocommit=`, `notices=`, the `cursor.description is None` guard and a `QueryFailure` exception,
> keeping it "the sole psycopg call site". That design session **conceded the two-seam split on
> 2026-08-02** — *"does this code write to the database? stays answerable by which function is called,
> statically, without reading arguments"* — and dropped the widening task from its plan. Every capability
> that proposal needed now lives on `apply_ddl` (mixed-statement execution, notice capture,
> statement-indexed failure); `QueryFailure` is unnecessary because `ApplyOutcome.statement_index`
> carries the same information **as data** rather than as an exception. `run_queries` is never widened.
> The plan file's Phase 1 text is stale on this point — the spec is authoritative.
- **Shape (as shipped).** `apply_ddl(target, statements: Sequence[str], *, commit: bool = True,
  runner: ApplyRunner = DEFAULT_APPLY_RUNNER, clock: Callable[[], float] = time.perf_counter) ->
  ApplyOutcome` (`db/apply.py`). `target` is a `ConnectionParams`, or anything carrying one as `.params`
  (a `db/sandbox.py::SandboxSession` — the ladder hands its session straight in; Apply-to-Target hands
  in the target's params). It runs the statements as **one transaction**, then **explicitly**
  `commit()`s when `commit=True` and **explicitly** `rollback()`s otherwise — never relying on implicit
  close-time rollback for correctness — with the single psycopg touchpoint injected as `runner`.
  **There is no `autocommit` parameter.** The one statement PostgreSQL forbids inside a transaction
  block — `CREATE DATABASE` for an app-owned sandbox — is owned by `db/sandbox.py::_run_autocommit`,
  called only from `create_sandbox_database`, exactly as D2's ownership table below states; it never
  routes through `apply_ddl`.
- **It must execute a *mixed* statement list — this is a hard correctness requirement, not an
  optimization.** The ladder is necessarily **one** call: the session/transaction has to span
  `SET plpgsql.extra_*` → the DDL → the `plpgsql_check_function_tb` **SELECT**. So `apply_ddl` runs
  statements that return **no** result set (`SET`, `CREATE FUNCTION`, `CREATE TRIGGER`,
  `CREATE EXTENSION`, `CREATE DATABASE`, the bookkeeping `INSERT`) alongside statements that **do**
  (the check SELECT). **In psycopg 3, `cursor.fetchall()` after a non-row-returning statement raises
  `ProgrammingError: the last operation didn't produce a result`** — so `apply_ddl` **must guard on
  `cursor.description is None`** and record a row-less `StatementResult` for that statement instead of
  fetching. Results are returned **per statement, in order, for the statements that ran**
  (`ApplyOutcome.results: tuple[StatementResult, ...]`, each entry carrying its `index` into the
  statement list), which is what lets the caller attribute each result to the tier that produced it —
  the ladder reads its check SELECT's rows off the last entry. `db/introspect.py::run_queries`
  does **not** get this guard, because it does not get writes — it keeps its unconditional `fetchall()`
  over read-only queries.
- **Notice capture is part of the seam, because tier 1 has no other channel.**
  `SET plpgsql.extra_warnings = 'all'` returns **no rows**; PostgreSQL delivers its findings as
  asynchronous `WARNING` diagnostics during `CREATE FUNCTION`. `apply_ddl` therefore registers a
  connection notice handler and normalizes each diagnostic into a **psycopg-free frozen
  `Notice{severity, message, detail, hint, context, sqlstate}`** (duck-typed `getattr` over the
  driver object), collected on `ApplyOutcome.notices`. Nothing downstream of the seam ever touches a
  psycopg object.
- **`ApplyOutcome`** captures failure as data rather than raising raw psycopg exceptions (shipped
  shape, `db/apply.py` — a frozen dataclass): `{ok: bool, statement_index: int | None, statement: str,
  committed: bool, results: tuple[StatementResult, ...], notices: tuple[Notice, ...], notices_captured:
  bool, sqlstate, message, detail, hint, position: int | None, line: int | None, elapsed_ms: float}`,
  where each `StatementResult` is `{index, statement, columns: tuple[str, ...] | None, rows:
  tuple[tuple, ...], affected: int | None, status: str}` (`columns is None` exactly when the statement
  produced no result set — the driver's `cursor.description`, never guessed from the SQL text; `status`
  is `cursor.statusmessage`, shown verbatim). The diagnostic fields are the same ones `CheckFinding`
  carries, so a failed apply and a validation finding render identically. **`statement_index` is the
  tier-attribution mechanism**: without it, a `plpgsql_check` call that itself fails gets misreported as
  *"your DDL is broken"* — precisely the silent-wrong-result class this project refuses. Its `message`
  renders the driver's primary message **verbatim**, so `test_connection`'s `(False, str(exc))` contract
  and MainWindow's status-bar strings do not regress.
- **Injectable, like every other DB path:** every caller takes `applier: Applier = apply_ddl`, mirroring
  the existing `runner: Runner = run_queries` convention, so the whole suite runs with psycopg absent.
- **Off the GUI thread**, via `self._run_async` (`ui/async_task.py::run_async`) with `ui/busy.py`'s
  `busy_status` — a dead host must never freeze the window (§18.1's precedent).

**Applying to the sandbox** is guarded by the ownership rule in D2 — *the app owns its sandbox databases
by naming convention and refuses to apply DDL to a database it did not create* — enforced as a hard
precondition in `db/sandbox.py` before the applier is ever called.

**Applying to the target database has four hard preconditions, in this order.** A confirmation dialog is
the *last* of them, not the only one.

**1 — Refuse a changed signature. No override, no consent path.** Immediately before applying,
re-introspect the live catalog and compare the buffer's `(schema, name, argtypes)` against it. **If they
differ, refuse**, name the mismatch, and direct the user to the deployment-script path. The reason is
that no confirmation gate *can* catch this: **PostgreSQL identifies a function by
`(schema, name, argtypes)`**, so editing `calc_total(integer)` into `calc_total(bigint)` and applying
makes `CREATE OR REPLACE` **create a second function and leave the old one live**. Every existing caller
keeps hitting the old one. The statement **succeeds**, and the confirmation dialog was **truthful** —
there is nothing for a confirm-gate to refuse. This is a silent wrong result in production, the worst
possible place for one.

> **Stated plainly, because it is a real capability loss and it is the correct trade:** this makes
> **parameter renames and argument-type changes unreachable from Apply.** They belong in the reviewable
> deployment-script path, where the change surfaces as `removed` + `added` and the generator refuses (or
> demands an explicit guarded `DROP`) rather than emitting a bare `CREATE OR REPLACE`. **Routine identity
> must never degrade to `schema.name` anywhere in this pipeline.**

**Related, and different — the failure that is loud.** `CREATE OR REPLACE FUNCTION` also **hard-errors**
on a changed *return type* (*"cannot change return type of existing function"*) or a renamed *input
parameter* (*"cannot change name of input parameter"*). That one fails visibly rather than silently, so
it needs no refusal of its own here — but it is a standing reason not to aim single statements at
production, and the deployment generator must detect it during its pre-generate drift check and refuse
with a named blocker (see "Generate Deployment SQL" below) instead of emitting a script that errors
halfway through on production.

**2 — Gate on a green sandbox validation, with a *named* override.** Apply-to-target is disabled unless
the ladder (D3) last ran green for this buffer. When the sandbox is unavailable, or lacks a required
extension, the user may override — but the override dialog must **enumerate exactly what could not be
checked** (which tiers, and why), never a generic "proceed anyway". Both halves are deliberate:
**refusing silently would be worse than DBeaver; applying unvalidated *is* DBeaver.**

**3 — Apply runs inside a transaction and rolls back on failure. There is no revert snapshot.**
`apply_ddl(..., commit=True)` wraps the statements so a rejected statement leaves the target untouched.
**State the resulting gap rather than leaving it implied: a successful-but-wrong apply has no in-app way
back until §18.2's checkout ships.** The rollback covers what PostgreSQL *rejects*, not what compiles
fine and behaves badly. Recovery today is the user's own backup or their git history — this app has
neither for the target. **This raises the value of landing §18.2 sooner**, and is a reason to prefer the
deployment-script path for anything non-trivial.

**4 — An explicit confirmation naming both the object and the database**, e.g. *"Apply
`public.recalc(integer)` to database `prod` on `db01:5432`?"* — never a generic "Are you sure?". The
confirmation must make *which system* unmistakable, in the same spirit as Diff/Merge's ambiguity gate
(§12) and Generate PHP's Save-vs-Save-As prompt (§19).

Applying to the target is additionally refused outright when the buffer is empty, and the result
(success, or the `ApplyOutcome`'s sqlstate/message) is reported to the Audit panel under `[Check]` and to
the status bar.

**Relationship to §18.3, so the two never read as duplicates.** §18.3 remains the **reviewed batch
deploy** of many objects with the `!`-drift gate, the assembled bundle and the git commit. Single-object
Apply is a **different, narrower, individually-confirmed gesture** with no bundle, no drift gate and no
manifest write. **When both could apply — a project is open and the object is checked out — §18.3's
Deploy is authoritative**; Apply exists for the edit/validate loop, not for rollout. See §18.2's
Apply-vs-Deploy table.

#### D2 — Sandbox source: bring-your-own local PostgreSQL for v1

The user runs their own local PostgreSQL server. The app adds a **second connection profile** with
`role = sandbox` alongside the existing `role = target` connection, persisted through the **same**
generalized `db/config.py` keyed-group scheme §18.2 already requires (§17) — one store, two dimensions
(project key, profile role), never a second settings mechanism and **never a second connection dialog**:
`ui/connection_setup_dialog.py` gains a profile selector, it is not forked. The exact keying scheme
(`ProfileKey`, the `"db"` compatibility group, the sandbox's no-`<ConnectionOptions>`-fallback rule) is
specified once, in §17.

**The sandbox is STATEFUL and accumulates applied edits — that is its purpose.** The earlier framing —
*"apply in a transaction → always `ROLLBACK`; the sandbox database stays pristine across any number of
checks"* — is **retracted** (§28), both by decision (*"we're doing schema changes on a sandbox, rollback
is symbolic"*) and because it was a **design defect**: a pristine-baseline-per-check model **cannot
validate interdependent edits.** Edit `A`, which calls `B`, and also edit `B`; under
rollback-after-every-check, `A` is forever validated against the *old* `B`, and the combination the user
is actually building is never checked at all. The accumulating working set can check it; a pristine
baseline cannot.

- **Rollback survives in exactly one narrow role:** the **"Check without applying"** probe — a
  convenience for *"what would this do?"*, not a safety mechanism, and not threaded through the rest of
  the code.
- **The real safety property is the ownership guard** (below), enforced in **one place**, not rollback
  discipline scattered across call sites.
- The sandbox therefore **is** the desired state, and is the source the deployment script is generated
  from. It is meant to hold your changes between sessions.

**Working-set bookkeeping — the sandbox must be able to say what is in it.** Provisioning creates a
reserved schema `pgtp_editor_sandbox` holding one table:

```
applied(kind text, schema_name text, object_name text, table_name text,
        applied_at timestamptz, text_sha1 text,
        primary key (kind, schema_name, object_name, table_name))
```

- `SandboxSession.apply(ref, ddl_text)` is **one** committing, atomic call: the DDL plus the `applied`
  upsert in a single transaction.
- `SandboxSession.applied() -> list[AppliedObject]` is one `SELECT`, and is what the Sandbox Setup
  dialog's working-set list and the deployment generator both read.
- `SandboxSession.reset()` is **schema-level** — `DROP SCHEMA <each app schema> CASCADE` (never the
  reserved bookkeeping schema) followed by a re-run of the baseline — deliberately **not**
  `DROP DATABASE`, which fails while any session is connected and would need a maintenance-database
  connection and `WITH (FORCE)` (PG 13+). Schema-level reset is just as complete here and avoids all of
  it.
- **`text_sha1` is not bookkeeping garnish.** It is what lets the UI say *"this tab has changed since you
  last applied it"* and what makes **Check** refuse to silently validate a stale version. An in-memory
  list would forget across an app restart **while the sandbox still holds the edits** — a silent
  wrong-state trap.

**Baseline provisioning is not optional — an empty sandbox is actively harmful.** Against an empty
database, tiers 2 and 3 report `relation "pr.equipment" does not exist` for essentially every real
routine: a **false ERROR**, which reads *worse* than "could not check" because it looks like a genuine
finding. Provisioning is therefore core, not deferred.

- The deliberate simplification, and it is a large one: **`plpgsql_check` is catalog-based and reads no
  rows.** It needs relations, columns and types to *exist*; it does not care about primary keys, foreign
  keys, defaults, indexes or data. So the baseline provisions **schemas → types (domains and composites)
  → tables (columns + `format_type` + `attnotnull` only) → views/matviews → routines → triggers**, in
  that order, which is load-bearing.
- Routines are emitted under `SET check_function_bodies = off` so one bad pre-existing routine cannot
  block provisioning; triggers come after routines because `CREATE TRIGGER` resolves its function
  immediately.
- **Deliberately omitted:** PK, FK, `DEFAULT` (which also sidesteps `nextval('seq')` needing sequences),
  indexes, extensions, sequences and all data.
- **Recorded gap, must be closed by the implementation:** `DatabaseSchema` (§17) **models no view
  definitions** — it has `tables`/`routines`/`triggers` only, and `TableInfo` carries columns, not a
  definition. A **`pg_get_viewdef` query must be added** to `db/introspect.py` (plus a `pg_type` query
  for `typtype IN ('d','c')`), or **every routine touching a view fails to compile** in the sandbox and
  the ladder reports false errors.
- `snapshot_for_baseline(target_params, runner=run_queries) -> BaselineSnapshot` lives in
  `db/introspect.py` (reusing `SCHEMA_SQL` + `ROUTINE_TRIGGER_SQL` + the two new queries);
  `build_baseline_sql(snapshot) -> list[str]` lives in `db/sandbox.py` and is **pure — no I/O, no DB**.
  Every identifier is quoted through a strict allowlist helper; a schema named `weird"name` is
  **refused**, never string-interpolated.
- **The incompleteness must be stated in the UI, not buried.** The report's caveats carry it verbatim:
  extensions, sequences, constraints, defaults and data are not reproduced, so findings that reference
  them are unreliable.

**The rest of D2's contract:**

- **Zero bundled bytes.** The app ships no server, no client binaries, and invokes no external process.
  Everything goes over `psycopg` through the two seams above (§17's "no external `psql`" transport rule
  is **not** touched by v1).
- **Capability probe — three states plus "unknown", never a silent "absent".** On sandbox connect,
  `probe(params, runner=run_queries) -> SandboxCapabilities` runs a small module-level `PROBE_SQL` list
  (a sibling of `SCHEMA_SQL`): `current_setting('server_version_num')`; `current_setting('is_superuser')`
  (which works for non-superusers, unlike `pg_user.usesuper`); `SELECT extname FROM pg_extension`;
  `SELECT name FROM pg_available_extensions`; and `current_database()` +
  `shobj_description(oid, 'pg_database')` for the ownership marker. `SandboxCapabilities{server_version:
  tuple[int, ...], is_superuser: bool, installed_extensions: frozenset[str], available_extensions:
  frozenset[str], database: str, owner_marker: str | None, probe_error: str | None}` is cached, and
  **`probe` never raises** — a failure becomes `probe_error`. Its derived property
  `plpgsql_check_state ∈ {installed, installable, absent, unknown}` returns **`"unknown"` whenever
  `probe_error` is set** and never degrades to `"absent"`. What is missing is reported to the user as
  *missing*, never silently skipped (see D3).
- **One-click extension install, behind a pure gate.** `install_plpgsql_check(session)` runs
  `CREATE EXTENSION IF NOT EXISTS plpgsql_check` and is reachable **only through a `SandboxSession`**,
  which by construction means the database is app-owned. Whether to offer it at all is decided by the
  pure `install_gate(caps) -> tuple[bool, str]`: offered only when the state is `installable` **and**
  `caps.is_superuser`; otherwise it returns the exact reason string the UI shows — *"already
  installed."* / *"`CREATE EXTENSION` requires superuser; ask your DBA, or connect the sandbox profile as
  a superuser."* / the platform install text for `absent` (**the app cannot fix that one — it is a C
  library on disk**) / *"could not probe the server."*

  > **One action, two entry points — the apparent conflict between §18.5 and §18.8 is resolved this way
  > (2026-08-06, ledger §28).** There is exactly **one** install action:
  > `SandboxController.install_plpgsql_check()`, which consults the pure `install_gate` and then calls
  > `db/sandbox.py::install_plpgsql_check(session)`. Its **primary UI home is Sandbox Setup…**, inside
  > the dialog, next to the probe result it depends on — never a top-level menu item. §18.8's **Sandbox2
  > action window** is a **second, equally valid entry point to that same controller method** (wired
  > through the zero-argument adapter `SandboxController.on_install_plpgsql_check`), not a second
  > implementation: it re-derives no gate, re-types no reason string and opens no session of its own.
  > Both surfaces show `install_gate`'s reason verbatim when the gate refuses, and both show the same
  > *"already installed."* line when there is nothing to do.
- **Backend interface.** All of this sits behind a Qt-free protocol in `db/sandbox.py` so a managed or
  bundled server can be added later (§29) without the choice leaking into the UI:

  | Member | Contract |
  |---|---|
  | `ensure_running() → dsn` | Return a usable DSN/`ConnectionParams` for the sandbox, starting the server if this backend owns one. For `LocalPostgresBackend` (v1) this is a no-op that returns the configured profile and fails loudly if it cannot connect. |
  | `capabilities() → SandboxCapabilities` | Delegates to `probe` (full field list above) and caches. **The ladder's tier availability is derived only from this** — never from a bare `try: … except: assume absent`. |

- **Ownership rule (safety, non-negotiable — stated verbatim as settled).** The app **owns its sandbox
  databases by naming convention** and **refuses to apply DDL to a database it did not create.** The
  refusal is a hard error surfaced to the user, not a warning: a user who points the sandbox profile at
  their production database must get "this is not a sandbox I created", never an executed DDL statement.
  This is the same "never a silent wrong result" stance as Diff/Merge's ambiguity gate (§12) and §18.4's
  refusal contract. **Now that the sandbox is stateful, this is the *only* safety property left** — it
  carries the weight rollback used to be imagined to carry, so its shape is pinned:

  | Piece | Contract |
  |---|---|
  | `SANDBOX_DB_PREFIX = "pgtp_sandbox_"`, `OWNER_MARKER_PREFIX = "pgtp-editor-sandbox:"` | Two markers, because one is not enough. |
  | `is_app_owned(database, owner_marker) -> bool` (pure) | True only when the name starts with the prefix **and** the `pg_database` comment starts with the marker prefix. **The name alone is spoofable** — a user can name production `pgtp_sandbox_prod`; the comment is written only by our own provisioning. |
  | `ForeignDatabaseError` (psycopg-free) | Message names the database and says plainly *"PGTP Editor did not create this database and will not write to it."* |
  | `open_sandbox(params, runner=run_queries) -> SandboxSession` | Probes, checks ownership, **raises `ForeignDatabaseError` if not owned.** **This is the only gate.** Everything that writes goes through the returned session; nothing else in the codebase re-checks ownership and no write path bypasses the session. Reads (probe, listing, introspecting the *target* for a baseline) are not gated. |
  | `create_sandbox_database(admin_params, name)` | `name` must match `^pgtp_sandbox_[a-z0-9_]{1,40}$` — **validated, not sanitized**: anything else is refused. Runs `CREATE DATABASE` + `COMMENT ON DATABASE … IS 'pgtp-editor-sandbox:<uuid>:<iso8601>'` with `autocommit=True` against the maintenance database, since PostgreSQL forbids `CREATE DATABASE` in a transaction block. This is the **one** `autocommit=True` call in the app, made from `db/sandbox.py` and nowhere else. |

- **The "create a sandbox for me" offer is a mandatory mitigation, not optional polish.** The ownership
  rule collides head-on with the most likely real setup: the realistic sandbox is a local restore of
  production named `myapp_dev`. `open_sandbox` **will** refuse it, and a bare refusal reads as *the tool
  being broken*. So wherever `ForeignDatabaseError` surfaces — principally **Sandbox Setup…** — the
  refusal must be shown **together with an explicit "Create a sandbox database for me" action**
  (`create_sandbox_database` + `build_baseline_sql` seeded from the **target** profile, off-thread with
  `busy_status`). A refusal without a way forward is the fastest route to the user concluding the tool is
  broken. *(A future "adopt this database" flow — stamp the marker after an explicit typed confirmation —
  is worth designing but is deliberately not specified here.)*

##### D2a — Optional "with data" sandbox cloning (settled 2026-08-05)

**Everything above in D2 is the schema-only baseline path and stays exactly as specified — this is an
additional, optional mode layered alongside it, not a replacement.** `build_baseline_sql` remains the
`plpgsql_check`-only path: in-process, `psycopg`-only, schema/types/tables/views/routines/triggers, zero
rows. D2a adds a second, explicitly-chosen provisioning mode that also brings the **data**, for the user
who wants to run/exercise routines against realistic rows rather than only catalog-check them.

- **A DELIBERATE, SCOPED EXCEPTION to D2's "zero bundled bytes, no external process" invariant, and
  narrowly for this path only.** Data cloning shells out to the **`pg_dump`**/**`pg_restore`** binaries as
  external subprocesses (custom-format dump piped or spooled into a restore against the sandbox
  database). The app does not bundle these binaries — it locates and invokes whatever `pg_dump`/
  `pg_restore` is on the user's `PATH` (matching the existing precedent of invoking the vendor generator
  and `re_phpgen` as external subprocesses, §1/§20) — but this is still a real, named departure from "the
  app ships no server, no client binaries, and invokes no external process. Everything goes over
  `psycopg`," which otherwise continues to hold for the rest of sandbox provisioning. **The schema-only
  baseline path is untouched: it stays in-process/`psycopg`, today and after this addition.** A missing
  `pg_dump`/`pg_restore` on `PATH` is reported to the user as a named, actionable failure (which binary,
  which `PATH` was searched) — never a silent fall-back to schema-only and never a bare stack trace.
- **Chosen at sandbox-creation time, not toggled later.** The New Project dialog's (§18.2) local-sandbox
  step — currently "add a Postgres connection + a superuser Test button" — gains a **"with data" /
  "without data"** choice presented at that same step. "Without data" is the existing D2 schema-only
  `build_baseline_sql` path, unchanged, and stays the default. "With data" runs `pg_dump` against the
  **target** profile and `pg_restore` into the freshly `create_sandbox_database`-provisioned sandbox,
  **instead of** `build_baseline_sql` for that sandbox — the two are alternative provisioning strategies
  for the same one-time setup step, never both run in sequence.
- **Cloning is one-shot only — there is no refresh/re-sync operation.** The clone reflects the target
  database at the moment the sandbox was created and is never automatically refreshed. To get fresher
  production data later, the user **destroys and recreates the sandbox**: `SandboxSession.reset()`
  already performs `DROP SCHEMA … CASCADE` on every app schema (D2, above) — for a "with data" sandbox
  this is followed by **re-running the pg_dump/pg_restore clone**, not a re-run of `build_baseline_sql`,
  so a reset sandbox ends up in the same mode (with or without data) it was created in. `reset()` itself
  is unchanged in its schema-level (never `DROP DATABASE`) shape; only which provisioning step follows
  the `DROP SCHEMA … CASCADE` depends on the sandbox's recorded mode.
- **The sandbox's mode (with-data or schema-only) is recorded, not re-derived.** It must be stored
  alongside the sandbox's other project-scoped state (the project's `.ddlproject/settings.json`, §18.2)
  so `reset()` and any later "what kind of sandbox is this" UI question do not have to guess from the
  database's current contents.
- **Everything else about D2/D3 is unaffected.** Ownership-by-naming-convention (`is_app_owned`,
  `open_sandbox`'s single gate), the `applied` working-set bookkeeping table, and the validation ladder
  (D3) apply identically to a with-data sandbox — `plpgsql_check` still reads no rows either way, so the
  ladder gains no new capability from the presence of data; what data cloning buys is the **separate**
  capability of actually *executing* routines against realistic rows — designed 2026-08-06 as **D4's
  Sandbox SQL Console**, still a distinct surface and **not** a new validation tier. D4 works against a
  schema-only sandbox too (you can run anything; there are simply no rows to find), so D2a is what makes
  it *interesting*, never what makes it *available*.

#### D3 — The validation ladder

Four tiers, applied in order, each independently available or unavailable. `db/ddl_check.py` (Qt-free)
drives them and returns a report carrying **per-tier outcome** as well as findings.

| Tier | Mechanism | Requires | Catches |
|---|---|---|---|
| 0 | Offline syntax check | nothing | syntax errors while typing — **collapses into tier 2**, see the licensing caveat below |
| 1 | `SET plpgsql.extra_warnings = 'all'` (+ `plpgsql.extra_errors`) before the DDL, **with the notice channel of `db/apply.py` active** | any server, **no superuser** | `shadowed_variables`, `strict_multi_assignment`, `too_many_rows` |
| 2 | Execute the DDL against the app-owned sandbox — **committing** for Apply, rolled back for the "check without applying" probe | write access to an app-owned sandbox DB | whether the DDL actually applies at all (parse + `check_function_bodies` + dependency resolution) |
| 3 | `plpgsql_check_function_tb()` on the object, in the **same session** as tier 2 | the extension installed in the sandbox DB | missing columns, wrong types, unresolved relations, trigger `NEW.x`/`OLD.x` misuse, dead code, missing `RETURN`, volatility violations, SQL-injection risk |

> **Tier 1 correction — it does not work the way an earlier draft of this table claimed (§28).**
> `SET plpgsql.extra_warnings = 'all'` delivers its findings as **asynchronous `WARNING` notices** during
> `CREATE FUNCTION`, and **the statements return no rows at all**. A row-fetching runner therefore yields
> **nothing** from tier 1, forever. Tier 1 is consequently specified as **dependent on the notice-capture
> channel on `db/apply.py`** (the normalized `Notice` records on `ApplyOutcome`, see the write seam): its
> findings are parsed out of `Notice.context` strings of the form
> `compilation of PL/pgSQL function "f" near line 3`. **Where that channel is not available, tier 1 must
> report `unavailable`, not `passed`.** Documenting a tier as working when it silently yields nothing is
> exactly the never-report-clean-when-unchecked violation this section otherwise forbids.
>
> Related and still unpinned: `SET plpgsql.extra_errors` with an invalid value errors *at SET time* once
> plpgsql is loaded, and plpgsql may not be loaded yet in a fresh session — this needs live-server
> confirmation before tier 1 ships.

**Three gestures, three entry points on `db/ddl_check.py`** — they differ in what they commit, and that
difference is user-visible:

| Entry point | Commits? | Notes |
|---|---|---|
| `probe_check(session, ref, ddl_text, caps)` — *"Check without applying"* | no | One call, explicitly rolled back. A convenience, not a guard. |
| `apply_and_check(session, ref, ddl_text, caps)` — *"Apply to Sandbox"* then check | **yes** | Tier 2's outcome **is** the apply's outcome; the working-set row is written in the same transaction. |
| `recheck(session, ref, caps)` — *"Check"* | no (nothing new applied) | Runs the ladder against the sandbox **as it currently stands**. Tier 2 reports `passed` with *"applied &lt;timestamp&gt;"* from the bookkeeping table. **If the caller's buffer hash differs from `applied.text_sha1`, the report carries a caveat saying so** — never silently check a stale version. |

Tier attribution uses the `ApplyOutcome.statement_index` of the statement list the driver built; a
failure in the `plpgsql_check` call must never be reported as *"your DDL is broken"*.

**The hard rule — an unavailable tier reports "could not check", never "clean."** This is the project's
"never a silent wrong result" invariant applied to validation: a green result must mean *checked and
found nothing*, never *not checked*. Concretely, the report distinguishes at least
`passed` / `found_issues` / `unavailable(reason)` / `errored(reason)` per tier, and the UI renders an
unavailable tier as an explicit, visible statement of what was **not** verified — it is never collapsed
into the overall OK state, never hidden behind a preference, and never degraded to a one-off toast the
user can miss.

**Report shape.** `CheckReport{tier0..tier3: TierOutcome, findings: list[CheckFinding], caveats:
list[str]}`, where `TierOutcome{status ∈ passed | found_issues | unavailable | errored, reason, detail}`.
`caveats` carries the honest text that must not be buried: the baseline's missing
extensions/sequences/constraints/defaults/data (D2), `plpgsql_check`'s known blind spots (below), and the
stale-buffer warning from `recheck`. The UI renders **one line per tier, always**, plus one line per
caveat.

**Why tier 2 may be run repeatedly, now that it commits.** PostgreSQL has **transactional DDL**, so the
probe variant leaves zero trace; the committing variant is *meant* to leave a trace — `CREATE OR REPLACE`
is idempotent, so re-applying the same object is a no-op, and the working-set table records what is in
there. Tier 3 runs in the **same session** as tier 2, after the object exists, which is what makes
catalog-based checking possible. (The earlier claim that the sandbox "stays pristine across any number of
checks" is retracted — see D2 and §28.)

**Line-number mapping is a correctness trap and is specified, not left to the implementer.**
`plpgsql_check` reports `lineno` relative to **`prosrc`** (the dollar-quoted body), while the tab's
buffer is **`pg_get_functiondef`** output (header + body). An off-by-header-length line number is exactly
the silent-wrong-result class this project refuses.

- `body_line_offset(buffer_text) -> int | None` locates the opening dollar-quote tag (`$$`, `$function$`,
  `$body$`, …) that begins the body and returns its **1-based line number** `L`.
- `map_lineno(buffer_text, lineno) -> int | None` → `L + lineno - 1`. `prosrc` begins with the newline
  that terminates the `AS $tag$` line, so `prosrc` line 1 **is** line `L`.
- **If the opener cannot be located, `lineno` is falsy, or the result is out of range, return `None`** and
  render the finding **with no line at all**. Never guess.
- **Tier-2 failures need no offset:** they carry a `position` — a character offset into the statement we
  sent, which *is* the buffer — so `line = buffer_text.count("\n", 0, position) + 1` is exact.
- **Tier-1 notices** arrive as `Notice.context` strings (`… near line 3`): regex the line, then apply the
  same `map_lineno`.
- The mapping must be pinned by fixture tests over a **verbatim captured `pg_get_functiondef` output**,
  plus a `LANGUAGE sql` variant, a body opened on the same line as `AS $$`, a `$body$`-tagged variant, a
  buffer with a `$$` inside a comment before the real opener, and a buffer with **no** opener →
  `None`. **A live-server confirmation of the `prosrc` ↔ `pg_get_functiondef` offset is the single
  highest-value live test in this feature and must exist before any finding is rendered against a line.**

**Recovering the applied object's OID for tier 3.** Primary:
`to_regprocedure(format('%s.%s(%s)', schema, name, argtypes))`, built from the `RoutineInfo` the tree
supplied. Fallback, for the case where the user edited the signature: `SELECT oid FROM pg_proc WHERE
xmin = pg_current_xact_id()::text::xid` inside the apply transaction — the catalog row just written is
the one carrying our xid. **The fallback is clever and therefore suspect: it must be confirmed against a
live server before it is relied on.** (Note that for Apply-to-target the signature-change case is refused
outright, above; this fallback exists only for the sandbox.)

**Tier 0 caveat — licensing.** The obvious offline choice, `pglast` (real PostgreSQL grammar via
libpg_query), is **GPL-3.0-or-later**. PGTP Editor is itself GPL-3.0 (§4), so it is usable *today*, but it
would become unusable if the project ever ships under a proprietary license — record the dependency as
license-load-bearing. The license-free alternative, which needs no new dependency at all, is to run a
throwaway `CREATE FUNCTION` inside a rolled-back transaction and let PostgreSQL's own parser be the
syntax checker — i.e. tier 0 collapses into tier 2 when a sandbox is available, and is simply reported
as unavailable when it is not. (§18.4's `format_selection` is **not** a tier: it is a layout formatter
whose tokenize/balance refusal is not a syntax check and must not be presented as one.)

#### D3a — Running the ladder: the Check gesture's concrete run contract (settled 2026-08-06)

**Owner decision: running `plpgsql_check` against a routine in the sandbox and *getting results back*
must work — not merely knowing whether the extension is installed.** §18.8's Sandbox2 node reports
install state and nothing more; this subsection is where the *run* is specified end to end. It adds no
new tier, no new module and no new prefix: it makes D3's tier 3 concretely invocable, reportable and
clickable through the seams that already exist.

**What is invoked, and against what.**

| Question | Contract |
|---|---|
| Which function | **`plpgsql_check_function_tb`** only — never `plpgsql_check_function` (whose `format` argument would hand back a formatted blob instead of rows) and never `plpgsql_check_all_functions`/`_relations` (whole-database sweeps we neither asked for nor can attribute to a tab). |
| Call shape | **Named notation, always** (positional order is `other_warnings, performance_warnings, extra_warnings`, *not* the README's), with **`fatal_errors => false`** (else exactly one finding per function) and **`all_warnings => true`** (warnings are off by default). The misspelled **`anyelememttype`** parameter is spelled with the typo verbatim if it is ever passed. `"position"` is **double-quoted** in the select list. |
| Scope of one run | **Exactly one object — the object the gesture was invoked on** (the active `DdlObjectEditorPanel`'s `DdlObjectRef`). There is no implicit multi-object run: a whole-schema sweep would produce findings nobody asked for, attributable to no tab, and would make the gesture's cost unpredictable. |
| Working-set sweeps | Specified as a **pure loop, not a second mechanism**: `check_working_set(session, caps, *, recheck=recheck) -> dict[ref, CheckReport]` iterates `SandboxSession.applied()` and calls the same `recheck` entry point per row. It exists for **Generate Deployment SQL**'s future *"is everything in the desired state green?"* question and **gets no menu entry of its own in this pass** — no dead controls, and no second reporting path. |
| Trigger tabs | Unchanged from D3: **tier 2 is the `CREATE TRIGGER` itself; tier 3 checks the *referenced function* with `relid` set** to the table OID (omitting `relid` errors *"missing trigger relation"*), plus `oldtable => t.tgoldtable, newtable => t.tgnewtable` when the trigger declares transition tables. |
| OID recovery | D3's `to_regprocedure(format('%s.%s(%s)', …))` primary, with the `xmin = pg_current_xact_id()` in-transaction fallback — the fallback is sandbox-only and **must be confirmed against a live server** before it is relied on (§30's env-gated file). |

**A finding is a `CheckFinding`, and the 11 returned columns map onto it 1:1.**
`plpgsql_check_function_tb` returns `(functionid regproc, lineno int, statement, sqlstate, message,
detail, hint, level, "position" int, query, context)`. `db/ddl_check.py::CheckFinding` mirrors and
extends `validation/tier2.py::ValidationIssue{severity, message, line}` (never widen that type — §18.5's
reuse map) with `sqlstate`, `level` (plpgsql_check's **raw** level string, kept verbatim), `position`,
`statement`, `query`, `detail`, `hint`, `context`, the source **tier** that produced it, and the object
identity. `line` is `map_lineno(buffer_text, lineno)` — **`None` when the dollar-quote opener cannot be
located, `lineno` is falsy or the result is out of range**, and a `None` line is rendered with no line at
all (D3; never a guess).

`level → severity` is a fixed, total mapping, applied in exactly one place:

| `level` (raw, preserved) | Audit `SEVERITY` token |
|---|---|
| `error` | `ERROR` |
| `warning`, `warning extra`, `warning performance`, `warning security` | `WARNING` |
| `compatibility` | `INFO` |
| anything else (a future level this table does not know) | `WARNING`, and the raw `level` is appended to the message in parentheses — **never dropped, never silently mapped to `INFO`** |

**How findings reach the Audit panel — two channels, and only one of them is clickable.** The shipped
`DdlObjectEditorPanel` already owns the `[Check]` prefix (`CHECK_PREFIX`, baked into the lines it emits
so the reservation lives with the feature that owns it) and emits **`check_reported(list[str])`** with
ready-to-append, already-prefixed lines. That signal is the **narrative channel** and keeps exactly its
current job:

- one line per tier, **always** — an `unavailable`/`errored` tier is stated, never collapsed into the
  overall OK state (D3's hard rule);
- one line per caveat (the baseline's missing extensions/sequences/constraints/defaults/data;
  `plpgsql_check`'s known blind spots — dynamic `EXECUTE`, `refcursor` fetched into a `record`, runtime
  temp tables; `recheck`'s stale-buffer warning when the buffer hash differs from `applied.text_sha1`);
- the apply/cancel/refusal notices the panel already emits.

Narrative lines carry **no line role and are not clickable**, the same treatment `[SQL]` and the `[Find]`
summary line get.

**Findings move to a second, clickable channel: `check_findings(list)`.** The panel emits the duck-typed
`CheckFinding` objects (or `(severity, line, message)` triples from a test stub — read by attribute, the
same duck-typing discipline `tier_outcomes`/`report_blockers` already use), and **`MainWindow` renders
them**: `"[Check] {SEVERITY} line {N}: {message}"`, the mapped line on `UserRole`, the object's
`DdlObjectRef.key` on `UserRole+1`, click-to-navigate = focus that object's tab and place the caret on
that line. A finding with `line is None` is rendered as `"[Check] {SEVERITY}: {message}"` with **neither
role set**, so it is inert rather than navigating somewhere wrong.

> **This overrides shipped behavior (ledger §28).** `DdlObjectEditorPanel._result_lines` currently folds
> findings **into** the narrative channel as `"  finding: line N: message"` strings. That was the right
> placeholder while `db/ddl_check.py` did not exist, but a pre-formatted string cannot carry the
> `UserRole` line and `UserRole+1` target that the reuse map's click-to-navigate contract requires, and
> the reuse map is explicit that this feature adds **no new diagnostics panel** — so the navigation has
> to live on the existing Audit item roles. When `db/ddl_check.py` lands, `_result_lines` stops emitting
> `finding:` lines and the panel emits them on `check_findings` instead. Tier lines, caveats and the
> `ok is False` summary stay exactly where they are.

**How the four `plpgsql_check_state` values gate a run — a run is never a silent no-op.** Tier 3's
availability is derived **only** from `SandboxCapabilities` (the `PostgresBackend.capabilities()`
contract), never from a bare `try: … except: assume absent`:

| `plpgsql_check_state` | Tier 3 outcome | What the user sees |
|---|---|---|
| `installed` | runs; `passed` or `found_issues` | the findings, plus the blind-spots caveat |
| `installable` | **`unavailable`** with `install_gate`'s reason | `[Check] tier3: unavailable — plpgsql_check is available on this server but not installed in this sandbox.` **plus** a line naming the one-click install and where it lives (*"Install it from Database ▸ Sandbox Setup…, or the Project Status window's plpgsql_check node."*). When `install_gate` refuses because the connection is not a superuser, its exact `CREATE EXTENSION requires superuser` sentence is shown instead — never re-typed |
| `absent` | **`unavailable`** | `install_gate`'s platform-install text **verbatim** — the extension is a C library on disk and **the app cannot fix it**; the message says so and names the `apt`/`dnf` packages (§18.5's `plpgsql_check` integration specifics) |
| `unknown` | **`unavailable`** | *"could not probe the server."* — **never** degraded to `absent`, because "could not check" and "genuinely not there" are different facts (D2) |

In all three non-`installed` cases **tiers 1 and 2 still run** and their outcomes are reported normally:
losing tier 3 costs the semantic analysis, not the compile check. The overall report is **not green** in
any of them, and the only way past is Apply-to-target's precondition-2 override, which **enumerates
exactly which tiers could not be checked and why** (`report_unverified`) rather than offering a generic
"proceed anyway".

**When the gesture itself is unavailable.** With **no live `SandboxSession`** there is no Check gesture at
all — no button, no enabled menu item (carve-out 2's "no dead controls", the same posture as the
absent apply row). The user's path back is stated where the absence is visible: **Database ▸ Sandbox
Setup…**, or the Project Status window (§18.8), whose Sandbox node names the specific degradation
(`ProjectCapabilityStatus.degraded_reason`, never a bare "sandbox unavailable"). **A missing sandbox is
never reported as a clean check.**

**Where the run happens.** `db/ddl_check.py` is Qt-free and opens no connection: it composes the
statement list and hands it to **`db/apply.py::apply_ddl`** (the ladder is necessarily *one* call —
`SET plpgsql.extra_*` → the DDL → the `plpgsql_check_function_tb` SELECT must share one
session/transaction), with `ApplyOutcome.statement_index` doing the tier attribution so a failure *in the
check call* is never reported as *"your DDL is broken"*. The **UI host is
`ui/sandbox_controller.py`**, which already owns the session and the off-GUI-thread seam: the ladder
gestures join `SandboxOperation` as `CHECK` (non-destructive — no `confirm_destructive` prompt) and
report through the same `SandboxOperationResult`/`operation_finished` path as every other sandbox
operation. The panel keeps knowing nothing: it calls its injected `apply_to_sandbox(ref, text)` seam and
records whatever report comes back (`record_check_report`, keyed by `text_sha1`).

#### D4 — Ad-hoc SQL execution against the sandbox: the Sandbox SQL Console (settled 2026-08-06)

**Owner decision, closing §29's *"running a function and seeing its results is not designed"*.** It is
*"the difference between a validator and an IDE"*, and the sandbox is what makes it safe in a way DBeaver
cannot: the sandbox is **disposable and resettable**, and that single property is the whole argument for
allowing execution here — and the whole reason the boundary below is where it is.

##### The safety boundary — read this first, because an implementer will otherwise generalize it

**Ad-hoc SQL execution is sandbox-only. It may never target the production/target database — not behind a
confirmation, not behind a preference, not behind a typed database name, not "read-only queries only".**

- **The boundary is structural, not procedural.** `db/sandbox_query.py::run_sandbox_query` takes a
  **`SandboxSession`**, never a `ConnectionParams`. A session exists only through `open_sandbox`, the
  single ownership gate, so an ad-hoc statement can only ever reach a database whose name carries
  `pgtp_sandbox_` **and** whose `pg_database` comment carries `pgtp-editor-sandbox:` — a database this app
  created and can wipe with `reset()`. **There is no free function that runs arbitrary SQL against
  arbitrary `ConnectionParams`, by design** — exactly the sentence `install_plpgsql_check(session)`
  already carries, and for the same reason.
- **Why this is compatible with §18.3's never-auto-execute non-goal, rather than a hole in it.** That
  non-goal is about **automatic** and **unreviewed** execution. Ad-hoc SQL is neither: the user typed it
  and pressed Run. What separates it from Apply-to-Target is not deliberateness — Apply is deliberate too
  — it is **reversibility**. Apply-to-Target has *no revert snapshot* (precondition 3): a
  successful-but-wrong statement against production cannot be undone from inside the app. A
  successful-but-wrong statement against the sandbox is undone by **Reset Sandbox**. That asymmetry *is*
  the rule; it is not a judgement about how careful the user is.
- **Consequently the console is absent, not disabled, without a live sandbox session** (§18.5 carve-out
  2 / §18.7's posture), and there is **no "run against target" affordance anywhere — not even a disabled
  one**. Adding one would require a spec change here and a Supersession Ledger row; an implementer must
  not add it as a convenience.
- **A read-only production query surface is a different feature and is not authorized by this
  subsection.** It is neither designed nor implied (§29).

##### Where the user types it

**One new dynamic center tab — the Sandbox SQL Console** (`ui/sql_console_panel.py::SqlConsolePanel`),
appended after `CenterStage`'s fixed set and keyed `("sandbox-sql",)` in the same key→widget map the
per-object tabs use (§7): **single-instance** — re-invoking the command focuses the existing tab rather
than opening a second console. A `QSplitter` with:

- **top:** `ui/code_editor.py::CodeEditor(language="sql")` — the same editor, the same SQL highlighter
  (`sql/keywords.py`'s one dialect source), the same gutter mixin. §18.6's `SchemaIndex` completion is
  injected the same way it is into an object tab, so Ctrl+Space works here too. §18.4's **Format
  Selection** (`Ctrl+Alt+F`) is available here on the same selection-only terms — its host set widens
  from one tab to two, with no change to the formatter.
- **bottom:** `ui/sql_results_panel.py::SqlResultsPanel` — the result grid, plus a one-line **status
  strip** (rows returned, truncation notice, elapsed ms, and each executed statement's command status).

**Rejected: a second bottom dock beside Audit.** The Audit dock is one shared `QListWidget` and a result
set is not a list; a second bottom dock would compete with it for vertical space; and the results belong
to the console that produced them, so they live with it. **Rejected: making the DDL object editor
executable.** One execution surface only. The object tab instead gains one context-menu bridge —
**"Run in Sandbox Console"**, which **copies the selection into the console tab and focuses it, without
executing anything**. No second execution path, no second confirmation surface.

##### What a result set is, as data — `db/sandbox_query.py` (Qt-free, opens no connection)

```
QueryResult{columns: tuple[str, ...], rows: list[tuple], truncated: bool, row_limit: int,
            command_status: str | None, duration_ms: int | None, statement: str,
            error: QueryError | None}
QueryError{sqlstate, message, detail, hint, position, line}
```

- **`QueryError`'s field names are deliberately `ApplyOutcome`'s and `CheckFinding`'s**, so a failed
  query, a failed apply and a validation finding render identically and share one formatting helper —
  the same pattern-extension discipline §18.4 set with `xsd_verify.Issue`.
- `line` is derived from `position` exactly as D3 does for tier-2 failures — `position` is a character
  offset into the statement we sent, which **is** the buffer, so
  `line = statement.count("\n", 0, position) + 1` is exact. No `map_lineno` is involved: there is no
  `prosrc`/`pg_get_functiondef` offset here.
- **`truncated` is a first-class field, never inferred from `len(rows) == row_limit`.** A result that is
  exactly at the cap and a result that was cut off must be distinguishable — reporting a truncated set as
  complete is precisely the silent-wrong-result class this project refuses.
- `command_status` carries PostgreSQL's own tag (`SELECT 100`, `UPDATE 3`, `CREATE FUNCTION`) so a
  statement that returns no rows still reports **what it did**, rather than an empty grid.

**Row cap — pick one and state it: `DEFAULT_ROW_LIMIT = 1000`.** An unbounded `SELECT *` over a
production-sized table cloned by D2a would freeze or OOM the app, and a model/grid holding a million
tuples is unusable anyway. The cap is user-adjustable in the console's own spin box, bounded by
`MAX_ROW_LIMIT = 100_000`; **there is no "unlimited" option.**

- **Enforcement is client-side and exact:** fetch `row_limit + 1` rows (`cursor.fetchmany`); if the extra
  row came back, set `truncated=True` and drop it. **Never** by rewriting the user's SQL into
  `SELECT * FROM (…) LIMIT n` — arbitrary input includes multi-statement text, `DO` blocks and DDL, and
  a rewrite would either fail on them or change their meaning.
- **Truncation is stated in the UI, not implied by a short grid**: the status strip reads
  *"first 1 000 of more rows — raise the row limit or add your own LIMIT."*

**The execution seam is the one that already exists.** `run_sandbox_query` runs through
**`SandboxSession.executor`** — the `SandboxExecutor` protocol `db/sandbox.py` already defines and
`SandboxSession.apply`/`applied` already use. It is **not** a fourth connection-opening function, and
`db/sandbox_query.py` itself imports no driver. The protocol gains **one** method, mirroring the guard
`apply_ddl` needs for the same reason:

```
fetch(params, sql, *, row_limit: int, statement_timeout_ms: int) -> FetchResult
    # FetchResult{columns, rows, truncated, command_status}
```

`_RealSandboxExecutor.fetch` opens one connection (lazy psycopg import, as everywhere else), issues
`SET LOCAL statement_timeout = '<ms>ms'`, executes, **guards on `cursor.description is None`** (psycopg 3
raises `ProgrammingError` on `fetchall()` after a non-row-returning statement) and returns an empty row
list with the command status for those, `fetchmany(row_limit + 1)` for the rest. Tests inject a fake
executor and never touch a server.

##### Multiple statements, transactions, and what commits

- **The Run gesture executes the selection if there is one, otherwise the whole buffer**, split into
  statements by the new pure `sql/statements.py::split_statements(text)`, built on §18.4's **existing
  tokenizer** (verified: `sql/tokenizer.py` already recognizes dollar-quoted bodies with tags, strings,
  quoted identifiers and both comment forms as single opaque tokens) so a `;` inside a `$$ … $$` routine
  body, a string or a comment **never** splits a statement. This is reuse, not a second SQL scanner.
- **All statements of one Run execute in order inside one transaction, which commits.** The grid shows
  the **last row-returning** statement's result; every statement's `command_status` is listed in the
  status strip. A failure aborts the run at that statement, rolls the whole transaction back, and reports
  the `QueryError` with the failing statement's index and text — partial application of a multi-statement
  Run is never left behind silently.
- **Yes, it commits — and that is the point.** *"Run my procedure and see what it did to the rows"* is
  unanswerable under a forced rollback, and the sandbox is the accumulating desired state (D2), not a
  scratch pad. The counterweight is the reversibility argument above, not a rollback.
- **Object-changing statements are surfaced, because they can desync the working set.** The pure
  `classify_statement(sql) -> "read" | "write" | "ddl" | "unknown"` (leading-keyword based, deliberately
  conservative) gates one confirmation: when any statement in the Run classifies as `ddl` **or**
  `unknown`, the console asks first — *"This Run changes objects in the sandbox. The sandbox's applied
  working set (and what your open tabs believe is applied) may no longer match. Reset Sandbox
  re-establishes a known state."* — with a **"don't ask again for this sandbox session"** checkbox. The
  confirmation is an **injected `confirm` seam**, exactly like every Apply confirmation, so a test can
  never reach a modal (§30). `unknown` is treated as `ddl` and the prompt says the classifier could not
  tell: an unclassifiable statement is never waved through as harmless.
- **The console never writes the `pgtp_editor_sandbox.applied` bookkeeping table.** That table records
  what **Apply to Sandbox** put there; an ad-hoc `CREATE OR REPLACE` is not an apply and must not
  masquerade as one. The divergence it can cause is surfaced (above), never papered over.

##### Long-running statements, and the honest gap

- **Everything runs off the GUI thread**, through `SandboxController` (`self._run_async` +
  `ui/busy.py::busy_status`) — the console opens nothing itself and blocks the event loop never. Run is
  disabled while a Run is in flight.
- **A statement timeout is mandatory, and it is the primary control**:
  `DEFAULT_STATEMENT_TIMEOUT_MS = 30_000`, adjustable in the console with a **minimum of 1 000 ms and no
  "unlimited" setting**. A timeout comes back as a named `QueryError` (sqlstate `57014`) reading
  *"statement cancelled: exceeded the console's statement timeout of N s — raise the timeout or narrow
  the query"* — never a hang and never a bare stack trace.
- **Stated gap: there is no in-app Cancel button in v1.** Cancelling a running statement needs
  `connection.cancel()` on a handle held by another thread, and `SandboxExecutor` implementations open
  **one connection per call** and close it themselves — there is no reusable handle to cancel. Saying so
  is better than a button that does nothing. Recorded as open (§29); revisit if a persistent-connection
  executor ever lands.

##### Reporting, and the prefix that is deliberately not created

Results, errors, truncation notices and the object-change caveat render **in the console's own
`SqlResultsPanel`**, never in the Audit panel. A query error is not a validation finding, and §7's
three-way prefix reservation forbids a fourth SQL-ish prefix — **do not add `[Run]`, `[Query]` or
`[Exec]`.** The only thing the console ever puts in the Audit panel is nothing at all.

##### Reuse map for D4 — what this builds on rather than duplicates

| Need | Existing thing to reuse |
|---|---|
| Session, ownership gate, execution | `db/sandbox.py::SandboxSession` + its `SandboxExecutor` (one new `fetch` method) — **never** a new connection-opening function |
| Session lifecycle, off-thread work, failure reporting | `ui/sandbox_controller.py` (`self._run_async`, `SandboxOperationResult`, `operation_finished`) — the console holds no session |
| Editor, highlighter, gutter | `ui/code_editor.py::CodeEditor(language="sql")` + `ui/editor_gutter.py` |
| Statement splitting | `sql/tokenizer.py` via the new pure `sql/statements.py` — **no second SQL scanner** |
| Completion / formatting in the console | §18.6's injected `SchemaIndex`; §18.4's `format_selection` (`Ctrl+Alt+F`), both unchanged |
| Diagnostic record shape | `ApplyOutcome`/`CheckFinding`'s field names (`sqlstate`/`message`/`detail`/`hint`/`position`) |
| Dynamic tab hosting | `CenterStage`'s key→widget map + §7's append-only/tail-only invariant |
| Confirmation | the injected `confirm(title, text) -> bool` seam the Apply gestures already use |
| Busy state | `ui/busy.py::busy_status` |

#### Generate Deployment SQL — the deliverable (output rank 1)

**Sandbox = desired state. Production = current state. Output = one reviewed `.sql` migration script,
run once, to upgrade the real database.** The user who has edited three routines in the sandbox and
checked them green gets exactly one file — with an explicit refusal if production moved underneath them,
and an explicit statement of what the script does *not* cover.

**§18.3 reuse, not a parallel engine.** §18.3 already specifies `db/schema_diff.py::diff_schemas`,
`db/migration_gen.py::generate_migration`, `Database ▸ Compare Schemas…` and `Save Migration As…` under
*"one diff/generation engine, two entry points"*. §18.5 **creates those two modules with §18.3's exact
dataclass shape and signatures** and implements **only the routine/trigger cases**; the table/column
cases are defined in the type and left unimplemented. §18.3 later fills them in — **nothing built here is
thrown away, and no second "assemble SQL" mechanism is created.**

> **One divergence from §18.3, stated so it is not read as a contradiction.** §18.3 assumed the desired
> state comes from a checked-in JSON snapshot (`db/schema_snapshot.py`). **A live sandbox is a strictly
> better source** — you can execute against it, so the desired state is provably coherent before it is
> diffed. §18.5 therefore adds a **third** source alongside §18.3's "live connection or snapshot": the
> sandbox. It does **not** build `db/schema_snapshot.py`; that stays §18.3's.

**`db/schema_diff.py` (pure, Qt-free, no I/O).**

- `SchemaDifference{kind ∈ added|removed|changed, object_kind ∈ table|column|routine|trigger, identity:
  str, old_def: str | None, new_def: str | None}` — **verbatim §18.3**. Do not "improve" the field names;
  §18.3's full engine populates the same type.
- `diff_schemas(source: DatabaseSchema, target: DatabaseSchema) -> SchemaDiffResult` (the
  `list[SchemaDifference]` subclass carrying `.unsupported`, §18.3), keyed on
  `DatabaseSchema.routines`/`.triggers`, which `fetch_routines_and_triggers` already populates for **any**
  connection — sandbox or production — with no new catalog query.
- **Routine identity is the full signature**, `schema.name(argtype, argtype)`, built from
  `RoutineInfo.arg_types` — **never** `schema.name`. This is the same load-bearing fact as the
  Apply-to-target signature refusal: a changed argument type is a *different function* to PostgreSQL, so
  it must surface as **`removed` + `added`**, never as `changed`.
- Trigger identity is `schema.table.name`, matching `DatabaseSchema.triggers`' existing key.
- `changed` is decided by **exact text comparison** of `RoutineInfo.source` / `TriggerInfo.definition`.
  Both come from `pg_get_functiondef` / `pg_get_triggerdef` on each side, so formatting is
  server-normalized and a cosmetic-only diff is impossible **within one server major**.
- **`table`/`column` are not implemented.** They are skipped and the omission is **returned**, not
  swallowed (an `unsupported: list[str]` or a module-level `SUPPORTED_OBJECT_KINDS` the caller checks),
  so the UI states *"table and column changes are not compared — §18.3"*. **A silently table-blind diff
  presented as a full migration is exactly the silent-wrong-result class this project refuses.**

**`db/migration_gen.py::generate_migration(differences, *, header: str = "") -> str` (pure,
deterministic — byte-identical output for identical input, so tests are golden-string assertions).**
Emission follows §18.3's CREATE→ALTER→guarded-DROP order with only the first and last stages populated:

1. **Header comment block:** generated-at; sandbox and production connection summaries
   (`user@host:port/db`, **redacted — never a password**, via `debuglog.redacted`'s shape); **both server
   versions**; which content model produced the script; which baseline model the sandbox was provisioned
   from; and the explicit *"table/column changes are not included"* limitation.
2. `added` + `changed` **routines** → the `new_def` verbatim (`pg_get_functiondef` already emits
   `CREATE OR REPLACE`).
3. `added` + `changed` **triggers** → `DROP TRIGGER IF EXISTS <name> ON <table>;` followed by the
   `new_def`. Triggers have no portable `OR REPLACE` below PG 14, and the drop-then-create pair is
   idempotent on every supported major — simpler than branching on the target's version.
4. `removed` routines/triggers → **commented-out** guarded `DROP` statements carrying a `-- REVIEW:`
   marker. **Never live DROP text.** An object absent from the sandbox far more likely means *"the user
   never touched it"* than *"delete this from production"*.

Every statement is `;`-terminated and blank-line separated, so the script is copy-pasteable into `psql`
and diffable in git. A `table`/`column` difference raises the module-defined `UnsupportedDifference`
(Qt-free, psycopg-free); the caller renders the refusal. **Never emit a partial script that silently
drops table changes on the floor.**

> **Module-docstring requirement (a real trap, not pedantry):** both modules land with their
> table/column halves deliberately hollow. The next contributor sees `db/migration_gen.py` and reasonably
> assumes it generates migrations. It generates **routine and trigger** migrations. Each module docstring
> must open with that limitation in its **first sentence**, and `UnsupportedDifference` must be a real,
> raised exception — never a silent skip.

**Dependency ordering — verified, and the obvious tool is the wrong one.** **Use stable alphabetical
ordering by identity, routines before triggers.** Do not make deployment-SQL generation depend on tier 3.

- **PL/pgSQL bodies are not resolved at CREATE time.** With `check_function_bodies = on`, the plpgsql
  validator parses the body's *statement structure* only; the SQL expressions inside it — including calls
  to other functions and references to tables — are parsed and planned lazily, at first execution. So
  `CREATE OR REPLACE FUNCTION a()` whose body calls `b()` **succeeds even when `b()` does not exist.**
  The strongest evidence is this feature's own premise: if CREATE-time validation resolved relations and
  callees, tier 3 would have nothing left to catch. **Forward references between plpgsql routines
  therefore need no ordering at all.**
- **Exception 1 — `LANGUAGE sql` routines** *are* parsed and analyzed at creation, and PG 14+
  `BEGIN ATOMIC` bodies additionally record **real catalog dependencies**. These genuinely need ordering.
- **Exception 2 — triggers.** `CREATE TRIGGER` resolves its function immediately (`pg_trigger.tgfoid` is
  a hard catalog reference) and the table must already exist. "Routines before triggers" is therefore a
  real constraint, not cosmetics.
- **`plpgsql_show_dependency_tb()` is REJECTED for this purpose, despite looking perfect.** It returns
  exactly the `FUNCTION`/`OPERATOR`/`RELATION` dependency set per routine and would drive a clean
  topological sort — but it is a `plpgsql_check` function, so **it covers only plpgsql routines: precisely
  the language that does not need ordering.** It cannot see inside the `LANGUAGE sql` routines that
  actually do. Adopting it would make generating a deployment script depend on tier 3 — an optional,
  per-database, superuser-gated C extension — in exchange for ordering information about the cases that
  were never at risk. **The deliverable must be producible on a bare PostgreSQL with no extensions.**
  Topological ordering is recorded as a possible **follow-on supplement**, never a replacement for
  handling the SQL-language case.
- If any emitted routine's `new_def` is non-plpgsql (detectable from `RoutineInfo.language`, which
  `fetch_routines_and_triggers` already populates — thread it onto the difference), emit a **header
  warning**: *"N non-PL/pgSQL routine(s) are included; statement order may need manual adjustment (their
  bodies are resolved at CREATE time)."* Honest, cheap, non-blocking.

**Mandatory pre-generate drift check.** Before generating, run `fetch_routines_and_triggers` against
production **off-thread** (one read-only introspection call — no new code) and compare it against the
sandbox's baseline-time definitions **for the objects in the applied set**. Any object whose production
definition changed since provisioning is a **`!` drift blocker**, reusing §18.3's *"any `!`-flagged
object blocks the batch"* all-or-nothing discipline, which itself reuses Diff/Merge's §12 ambiguity gate:
**refuse the whole script, name every blocker**, recovery = re-provision or re-apply, then re-run. This
is what stops a deployment script from silently overwriting a production hotfix made during the dev
cycle. The same introspection pass has both signatures in hand, so it is also where the
**`CREATE OR REPLACE` hard-failure cases are caught** — a changed *return type* or a renamed *input
parameter* is refused with a named blocker (*"pr.calc_total: return type changed; a deployment script
cannot replace this in place"*) rather than emitting a script that errors halfway through on production.

**Honest caveats the script must carry, because they are real:**

- **`pg_get_functiondef` text is not stable across server majors**, and sandbox and production are
  frequently different majors. Purely cosmetic rendering differences surface as **phantom `changed`
  entries**, producing a script full of idempotent no-op replacements. Harmless but noisy, and it erodes
  trust in the diff. Mitigation: report **both** server versions in the header and say so prominently
  when they differ. A normalizing comparison is a rabbit hole — do not start it.
- **The baseline's incompleteness (D2) propagates into the deliverable.** A routine valid *in the
  sandbox* may be invalid in production if it relies on a `DEFAULT nextval(...)`, a constraint or an
  extension the baseline omitted. The sandbox is a **structural approximation** of production, not a
  copy; the header must say which baseline model produced it.

**UI flow — review before write.** **Database ▸ Generate Deployment SQL…**, disabled unless a sandbox
profile is configured. Both introspection calls run off the GUI thread (`self._run_async` +
`busy_status`). Guards, each with its own specific message: no sandbox → open Sandbox Setup; empty
applied set → *"nothing has been applied to the sandbox yet"*; drift blockers → the §12-style refusal
naming every blocker; `UnsupportedDifference` → the table/column refusal. On success the script is shown
in a **read-only preview tab** reusing `CodeEditor(language="sql")` (a dynamic tab, appended per §7's
invariant) with a **Save Migration As…** button writing UTF-8 `newline=""`, mirroring `_save_xsd`
exactly. **Do not write a file the user has not read — this is DDL destined for production. The script is
never executed by this app; there is no execute path, not even a disabled one** (§18.3's hard non-goal,
inherited verbatim).

> **Not built here:** §18.3's own **Compare Schemas…** and **Save Migration As…** commands. §18.5 builds
> the engine those two will call; building their UI is §18.3's job, and its settled *"separate sibling
> command, no-project-required"* framing must not be pre-empted by a §18.5-shaped screen. Say so in the
> code comment so the next reader does not "finish" it wrongly.

#### Reuse map — what this feature builds on rather than duplicates

| Need | Existing thing to reuse |
|---|---|
| SQL **reads** | `db/introspect.py::run_queries` — the sole read seam, read-only; every new function takes `runner: Runner = run_queries` so the suite runs with psycopg absent |
| SQL **writes** | `db/apply.py::apply_ddl` — the sole write seam **to the target database** (above); sandbox-scoped writes go through the sandbox session's own named seams (`db/sandbox.py::SandboxExecutor` + `_run_autocommit`, D2/D4 — the three-seams invariant below, ledger §28). `applier: Applier = apply_ddl` injectable the same way. **Never an unnamed fourth connection-opening function.** |
| Connection profile & dialog | `db/config.py::ConnectionParams` + `ui/connection_setup_dialog.py` — add a profile dimension (§17/§18.2); **no second dialog** |
| Diagnostics surface | the existing Audit/Problems panel (§7): `"[Check] SEVERITY line N: message"`, line on `UserRole`, target on `UserRole+1`, click-to-navigate — **no new diagnostics panel** |
| Diagnostic record | the shape of `validation/tier2.py::ValidationIssue{severity, message, line}` |
| Line mapping | `db/ddl_buffer.py::DdlObjectSpan` — translates a per-routine `lineno` into a buffer line (the *within-object* `prosrc` → buffer offset is D3's `map_lineno`) |
| Diff / migration generation | §18.3's `db/schema_diff.py` + `db/migration_gen.py` **shapes and signatures**, created here with the routine/trigger cases only — **one engine, two entry points**; never a parallel generator |
| Production introspection for the drift check | `db/introspect.py::fetch_routines_and_triggers` — already read-only, already exists, no new catalog query |
| Off-GUI-thread work | `ui/async_task.py::run_async` via MainWindow's injectable `self._run_async`, with `ui/busy.py::busy_status` for the status-bar busy state |
| External process (if ever) | `generation/runner.py::GeneratorRunner` (QProcess, streamed lines) — **v1 spawns nothing**; do not write a second process runner |
| Editor widget | `ui/code_editor.py::CodeEditor(language="sql")` + `ui/editor_gutter.py::GutterBookmarkFoldMixin` |
| Formatter | §18.4's `format_selection` — this tab is its first consumer |
| Menu home | the **Database** menu (`main_window.py::_build_database_menu`) — **no new top-level menu** |
| Verifying the sandbox matches | `Database ▸ Compare Schemas…` (§18.3) pointed at the sandbox |

**Findings type.** `db/ddl_check.py::CheckFinding` **mirrors and extends** `ValidationIssue`'s
`{severity, message, line}` shape — the same pattern-extension precedent §18.4 set with
`xsd_verify.Issue` — adding `sqlstate`, `level` (plpgsql_check's raw level string), `position`,
`statement`, `detail`, `hint`, `context` and the object identity. **Do not widen
`validation/tier2.py::ValidationIssue` itself**: its three fields are asserted by existing tests and it
belongs to `.pgtp` structural validation, a different domain.

**Line-number honesty** is specified in full in D3 above (`body_line_offset` / `map_lineno`, the exact
`position`-derived line for tier 2, the `near line N` regex for tier 1, and the mandatory `None` when the
opener cannot be located). It is not restated here.

#### Audit-panel prefix: `[Check]`

Findings from this feature use **`[Check]`** — `"[Check] ERROR line 42: record has no field \"foo\""` —
following the same click-to-navigate convention as `[Validate]`/`[Find]`. It is distinct from §18.4's
`[SQL]` (formatter refusals: layout only, no database) and from §22's `[Lint]` (PHP only). The three-way
reservation is recorded in §7 and on each owning section deliberately: several linter-shaped features
feeding one Audit panel must be distinguishable at a glance, none may annex another's prefix, and no
fourth SQL-ish prefix may be introduced.

#### `plpgsql_check` integration specifics

Verified against the shipped `plpgsql_check--2.10.sql`; these facts **constrain the implementation** and
are recorded so they are not rediscovered the hard way.

- **v2.10.4, MIT** (the `LICENSE` file; `META.json` wrongly claims BSD). Supports PostgreSQL 14–18.
- It is a **C extension, ABI-bound per PostgreSQL major**. The `.so`/`.dll` must already be present on
  the server — the app **cannot** install it over a psycopg connection. Detection, not installation, is
  the app's job.
- **`CREATE EXTENSION` requires superuser** (the control file omits both `trusted` and `superuser`, so
  PostgreSQL's default applies), and the extension is **per-database**. There is **no upgrade path**:
  updating means `DROP EXTENSION` + `CREATE EXTENSION`.
- **Calling** the check functions requires **no** privilege — there is no ACL gate in the source and no
  `REVOKE` in the install script. A DBA-installed extension on a shared server is usable by an ordinary
  user, so *"detect it on the user's own server and use it when present"* is a **first-class supported
  path**, not a fallback.
- **No `shared_preload_libraries` entry is needed** for active mode (`plpgsql_check.mode` defaults to
  `by_function`) — no config edit, no server restart, nothing the app would have to talk a user through.
- Availability, for the honest "how do I get it?" message: Linux
  `apt install postgresql-NN-plpgsql-check` (PGDG) / `dnf install plpgsql_check_NN`. Windows has no
  GitHub release asset, no StackBuilder entry and no upstream CI — only the author's personal build
  (`pgsql.cz`, **2.8.5, PG 17+18, x64 only**, ~350 KB: two DLLs + `.control` + `.sql`).

**API gotchas — all of these are call-shape requirements, not trivia:**

| Fact | Consequence for the caller |
|---|---|
| The parameter is misspelled **`anyelememttype`** (`m` for `n`) | named-notation calls must use the typo verbatim |
| Positional order is `other_warnings, performance_warnings, extra_warnings` — **not** the README's order | **always use named notation**; never rely on position |
| `format` (`text`/`json`/`xml`) exists on `plpgsql_check_function` only, **not** on `_tb` | use `_tb` and consume rows, not a formatted blob |
| `plpgsql_check_function_tb` returns **11 columns**: `(functionid regproc, lineno int, statement, sqlstate, message, detail, hint, level, "position" int, query, context)` | `"position"` **must be double-quoted** in the select list; the 11 columns map 1:1 onto `CheckFinding` |
| `fatal_errors` defaults to true | pass **`fatal_errors => false`** for a GUI, else you get exactly one finding per function |
| Warnings are off by default | pass **`all_warnings => true`** |
| **Trigger functions require `relid`** | omitting it errors *"missing trigger relation"*; pass the table OID, plus `oldtable => t.tgoldtable, newtable => t.tgnewtable` when the trigger declares transition tables |
| `level` values are `error`, `warning`, `warning extra`, `warning performance`, `warning security`, `compatibility` | map to the Audit panel's `SEVERITY` token; keep the raw string in `CheckFinding.level` |

**Known blind spots** (must be stated in the UI's "what was checked" text, per the never-silently-clean
rule): dynamic `EXECUTE`, `refcursor` fetched into a `record`, and temp tables created at runtime.
Escape hatches for false positives are `plpgsql_check_pragma('type: …')` inside the body and
`SET plpgsql.enable_check TO false`.

**Trigger tabs are a second, quieter special case** — easy to get 80% right and silently wrong on the
rest. The tab holds a `CREATE TRIGGER` statement, but tier 3 checks **functions**. So for a trigger tab,
**tier 2 is the `CREATE TRIGGER` itself** and **tier 3 checks the *referenced* function with `relid`
set**. Additionally, `CREATE OR REPLACE TRIGGER` exists only on **PG 14+**: below that the statement list
must be preceded by a `DROP TRIGGER IF EXISTS`, gated on `caps.server_version`.

**Bonus surface, not v1:** `plpgsql_show_dependency_tb()` returns `(type, oid, schema, name, params)` —
a ready-made "what does this routine touch" view that would slot into `BrowserPanel` as a further
relationship angle alongside §18.1's dual grouping. Noted, not designed. **It is explicitly rejected as
a dependency-ordering source for the deployment script** (see "Generate Deployment SQL" above) — it
covers only plpgsql routines, i.e. exactly the ones that need no ordering.

#### Invariants this feature must conform to

1. **Three connection-opening seams, each with one job, and never a fourth** *(corrected 2026-08-06 —
   the earlier "two seams" statement did not account for the sandbox executor that has since shipped;
   ledger §28)*:
   - `db/introspect.py::run_queries` — the sole **read** seam, read-only, never widened (no
     `autocommit=`, no commit path, not "just this one DDL statement"), so *"does this code write to the
     database?"* stays answerable by **which function is called**, statically.
   - `db/apply.py::apply_ddl` — the sole **write** seam for DDL applied to *either* database, with the
     mixed-statement `cursor.description is None` guard and the notice-capture channel.
   - `db/sandbox.py::SandboxExecutor` (`execute`/`query`/`fetch`) — the **sandbox lane's** execution
     seam, reachable only through an ownership-gated `SandboxSession`; `SandboxSession.apply`/`applied`/
     `reset`, `install_plpgsql_check` and D4's `run_sandbox_query` all go through it and nothing else
     does. Its narrowness *is* the safety property (D4).

   Every new path takes `runner: Runner = run_queries` / `applier: Applier = apply_ddl` / an injected
   `executor`, so the whole suite runs without psycopg importable.
2. Every module this feature adds under `db/` — `apply.py`, `sandbox.py`, `ddl_check.py`,
   `sandbox_query.py`, `schema_diff.py`, `migration_gen.py` — and `validation/` stay **Qt-free**; only `ui/` imports PySide6
   (§5). The one pre-existing exception, `db/config.py`'s module-scope `QSettings`, is **not** to be
   "fixed" by inventing a second store (§5/§17).
3. Every connection-opening call runs **off the GUI thread** (`self._run_async`) with busy state
   (`ui/busy.py`) — a dead sandbox host must never freeze the window (§18.1's precedent).
4. Any new params type must be redactable through `debuglog.redacted(params)`; the redaction test is
   locked (§25).
5. Config persistence follows the existing pattern: injectable store, loaders tolerate
   absent/unreadable/malformed input and **never raise**.
6. The byte-for-byte `.pgtp` round-trip (§2) is untouched — **this feature never writes the project
   file**, and works with zero `.pgtp` files open (§18's standalone mode).
7. Tests mirror the package layout (`tests/db/test_apply.py`, `tests/db/test_sandbox.py`,
   `tests/db/test_ddl_check.py`, `tests/db/test_sandbox_query.py`, `tests/sql/test_statements.py`,
   `tests/db/test_schema_diff.py`, `tests/db/test_migration_gen.py`,
   `tests/ui/test_ddl_object_editor.py`, `tests/ui/test_sandbox_controller.py`,
   `tests/ui/test_sql_console_panel.py`, `tests/ui/test_sql_results_panel.py`);
   dialogs use `show()`, never `.exec()`; context menus are built
   by a `_context_menu_for(item) -> QMenu | None` helper the test can trigger **without** `exec()`; no
   un-patched modal (§30). **Every Apply confirmation is a test seam** (an injectable `confirm=`
   callable, the `_confirm_close()` precedent) — a test must never be able to reach a real
   apply-to-target prompt, and must never be able to execute DDL by accident. **D4's console is held to
   the same standard**: its object-change confirmation is the same injected `confirm` seam, and
   `run_sandbox_query` is driven by a fake `SandboxExecutor` in every test — a test must never be able to
   execute arbitrary SQL against anything real. There is deliberately **no test path that constructs a
   query against `ConnectionParams`**, because no such API exists.
8. **No live PostgreSQL in the default suite.** Every DB path takes `runner=`/`applier=` and is driven by
   a fake, exactly as `tests/db/test_introspect.py` does today; `db/sandbox.py`'s pure predicates
   (`is_app_owned`, `install_gate`, `build_baseline_sql`) and both diff/generation modules are tested
   directly with no runner at all. The handful of facts that genuinely need a server live in **one
   env-gated file** (`tests/db/test_sandbox_live.py`, skipped unless a sandbox DSN env var is set),
   covering at minimum: `cursor.description is None` for `SET`/`CREATE FUNCTION`/`CREATE EXTENSION`; that
   `plpgsql.extra_warnings='all'` actually delivers notices and its `CONTEXT` matches the `near line N`
   regex; **the `prosrc` ↔ `pg_get_functiondef` line offset** (do not ship rendered line numbers without
   it); `plpgsql_check_function_tb`'s 11-column order, the `anyelememttype` typo and the trigger `relid`
   requirement; the `xmin = pg_current_xact_id()` OID-recovery fallback; that `CREATE DATABASE` requires
   autocommit and schema-level reset works with a live connection open; and the two ordering claims —
   that a plpgsql body calling a nonexistent function **creates fine**, and that the same is **not** true
   for a `LANGUAGE sql` function. **Added for D4:** that `SET LOCAL statement_timeout` actually cancels a
   long statement and surfaces sqlstate **`57014`**, and that `fetchmany(row_limit + 1)` distinguishes a
   result exactly at the cap from a truncated one.
9. **`CenterStage`'s append-only / tail-only dynamic-tab invariant (§7) has a mandatory regression test**
   — this feature is the first to create runtime tabs, and five existing call sites depend on the fixed
   indices staying put.

### 18.6 Schema-aware Ctrl+Space completion in the DDL object editor

> **Status: implemented and shipped** (designed 2026-08-04; verified against the code 2026-08-06). Every
> piece below exists: `pgtp_editor/db/schema_index.py::SchemaIndex` (`known_schemas`/`known_tables`/
> `known_columns`/`trigger_for_function`, tested in `tests/db/test_schema_index.py`);
> `pgtp_editor/sql/caret_context.py`, the Qt-free caret resolver; `pgtp_editor/ui/completion_popup.py`,
> where §11's `_CompletionPopup` was **extracted for reuse** and is now imported by both `ui/xml_editor.py`
> and `ui/ddl_object_editor.py` rather than cloned; `DdlObjectEditorPanel.set_schema_index(index)` with
> the `None`-disables contract; the Ctrl+Space key handling, the three contexts, and the session-only
> unattached-trigger table prompt (`_prompt_unattached_trigger_table`, `_unattached_trigger_table` —
> never persisted); the widened `db/introspect.py::fetch_routines_and_triggers`, which now runs
> `ROUTINE_TRIGGER_SQL + SCHEMA_SQL` in one call and returns `.tables` populated (`fetch_schema` itself
> untouched); and `MainWindow`'s wiring, which builds one `SchemaIndex` per DDL fetch and pushes it into
> every open tab via `panel.set_schema_index(...)`. Tests: `tests/ui/test_ddl_object_editor_completion.py`,
> `tests/ui/test_ddl_schema_index_wiring.py`.
>
> The 2026-08-04 placement gate recommended **EXTEND**, not a new top-level feature, and the shipped shape
> honoured it: one popup widget serving multiple editors, one widened introspection fetch rather than a
> parallel one. No longer scoped to §18.5's **editable** `DdlObjectEditorPanel` alone: the §18.5 **D4
> Sandbox SQL Console** is a **third completion consumer** (`ui/sql_console_panel.py` imports
> `sql/caret_context.py::resolve_caret_context` and the shared popup host from `ui/completion_popup.py`,
> with its own Ctrl+Space wiring — ledger §28); the `CodeEditor`-level
> pluggable provider below remains the un-built natural extension.

**What it is.** Pressing **Ctrl+Space** inside the DDL object editor tab (§18.5,
`ui/ddl_object_editor.py::DdlObjectEditorPanel`, hosting `ui/code_editor.py::CodeEditor` in
`language="sql"` mode, made editable) opens a completion popup offering schema-aware suggestions, in
three contexts:

| Context | Trigger | Offers |
|---|---|---|
| Schema-qualified table reference | caret in/after a schema name (optionally partial) | matching table names in that schema, schema-qualified, prefix-filtered as more is typed |
| `NEW.`/`OLD.` inside an **attached** trigger function | caret after `NEW.` or `OLD.` inside a routine's body, and that routine **is** some trigger's function (reverse lookup via `TriggerInfo.function_name`) | the column names of that trigger's target table (`TriggerInfo.table`) |
| `NEW.`/`OLD.` inside an **unattached** trigger function | same trigger-context syntax, but no `TriggerInfo` currently references this routine | tells the user no trigger is defined for this function, then prompts a table pick (a small picker reusing an existing simple-selection-dialog idiom); once picked, offers that table's columns |

**Popup widget — reused, not rebuilt.** §11's `_CompletionPopup(QListWidget)` was **extracted out of
`ui/xml_editor.py` into its own module `pgtp_editor/ui/completion_popup.py`** and is now imported by its
consumers — `ui/xml_editor.py` (which re-exports the name so §11's call sites and tests are unchanged),
`ui/ddl_object_editor.py`, and the §18.5 D4 sandbox SQL console — one widget
class, three instantiations, no clone. Its contract is unchanged: frameless
(`Qt.WindowType.Popup`), non-modal, `(key, display)` master list with a running prefix filter, ↑/↓
navigate, Enter/Tab/click choose, Esc/focus-out cancel, printable characters filter — the exact same
shape and keyboard contract §11 already ships, so this feature added a **second instantiation of the same
class/pattern** in the DDL object editor's module (the D4 console later added the third), not a second
popup implementation. `_CompletionPopup`
itself needs no XML-specific change to be reused here; it already only deals in `(key, display)` pairs.

**Caret-context resolution — new Qt-free module under `sql/`.** Alongside `sql/keywords.py` and
`sql/tokenizer.py`, a new pure module resolves what is "under the caret": identifier boundaries,
dotted-path parsing (`schema.table`), and detecting a `NEW.`/`OLD.` reference specifically inside a
trigger-function body. Qt-free and unit-testable independent of Qt and of a live database, matching the
rest of `sql/`'s dependency posture (§5). This module's output — a resolved context (bare identifier,
`schema.` prefix, `schema.table.` prefix, or `NEW.`/`OLD.` inside a body) — is what the panel uses to pick
which of the table above's three rows applies and what prefix to filter on.

**Data source — `db/introspect.py::fetch_routines_and_triggers` is widened, not duplicated.** DDL
Explorer's existing connect-time fetch (§18.1) now also populates `DatabaseSchema.tables` by additionally
running `SCHEMA_SQL` (the same three queries `fetch_schema`, §17, runs for DB Check) inside the one
`fetch_routines_and_triggers` call. This **supersedes** §18.1's earlier statement that the returned
`DatabaseSchema` "always has an empty `.tables`" (§28) — that was true only because nothing yet consumed
table/column data from this fetch path; completion is now that consumer. `fetch_schema` itself is
**unchanged** and DB Check keeps calling it directly — this is one widened fetch on DDL Explorer connect
serving two consumers (routines/triggers browsing **and** completion's table/column data), not a second
parallel fetch, and **not** a lazy per-keystroke fetch: the index (below) is built once per DDL Explorer
connect/refresh, exactly like the tree and the read-only buffer are.

**Injection shape — preserves §18.5 D1's "the panel never talks to a database" invariant.** A new pure,
Qt-free lookup module, `pgtp_editor/db/schema_index.py` (alongside `schema_learning/settings_index.py`,
§11's analogous query-API module), is built **once** from the `DatabaseSchema` DDL Explorer fetches,
exposing at minimum:

| Member | Contract |
|---|---|
| `known_schemas() -> list[str]` | every schema name present in the fetched `DatabaseSchema` |
| `known_tables(schema, prefix="") -> list[str]` | table names in `schema` whose name starts with `prefix` (case-insensitive, matching the `_CompletionPopup` filter convention) |
| `known_columns(table) -> list[str]` | column names of `schema.table` (schema-qualified key, matching `DatabaseSchema.tables`' existing keying, §17) |
| trigger-function reverse lookup (e.g. `trigger_for_function(schema, name, arg_types) -> TriggerInfo \| None`) | resolves a routine's `RoutineInfo.signature` (§18.1) against `DatabaseSchema.triggers` via `TriggerInfo.function_name`, so the panel can tell an attached trigger function from an unattached one |

This index object is **handed to each open `DdlObjectEditorPanel` by injection** — the same idiom as
`set_schema_model(model)` on `XmlEditor` (§11): a `set_schema_index(index)` (or equivalent) call, `None`
disabling completion entirely. `DdlObjectEditorPanel` never imports `db/introspect.py`, never holds a
connection or connection parameters, and this feature adds nothing to that invariant's list of
exceptions (§18.5 D1).

**The unattached-trigger table pick is session-only — never persisted.** When Ctrl+Space resolves a
`NEW.`/`OLD.` context inside a routine that no `TriggerInfo` currently references, the user is told plainly
that no trigger is defined for this function and is prompted to pick which table it belongs to. This
choice is **not written anywhere** — not to the project's `settings.json` (§18.2), not to any sidecar
file next to a checked-out `ddl/*.sql`, not anywhere else on disk. It lives only in the panel's in-memory
state for that tab and is **forgotten** the moment the app restarts or the tab closes. This is a
deliberate choice, not an oversight: persisting it would give `DdlObjectEditorPanel` a second source of
durable state beyond the injected load/save pair, breaking §18.5 D1's project-decoupling invariant (the
panel "must not know what a project is, and must not branch on whether one is open"). A user reopening
the same trigger-function tab in a later session simply gets prompted again.

**Scope for this pass — the DDL object editor only.** This feature reaches `DdlObjectEditorPanel` alone.
It deliberately does **not** reach:

- the **read-only** DDL Explorer viewer tab (`ui/ddl_editor_panel.py::EditorPanel`, §18.1) — that buffer
  is `setReadOnly(True)` permanently and completion there would suggest edits that cannot land;
- any other `CodeEditor` consumer (the JS/PHP "Edit code…" dialogs, §21's planned Custom PHP tabs).

**Natural extension point, explicitly not built now.** A future pass may generalize this into a
`CodeEditor`-level pluggable completion provider — mirroring the `GutterBookmarkFoldMixin` pattern
already used for the gutter/bookmark/fold split (§8) — if/when Ctrl+Space completion is wanted on other
`CodeEditor` consumers. This is recorded as the natural next step, not designed here, and not a
prerequisite for this pass: v1 of this feature wires Ctrl+Space directly on `DdlObjectEditorPanel`'s
`CodeEditor` instance, the same way §18.5 already wires Format Selection (Ctrl+Alt+F) as a panel-local
affordance rather than a generic `CodeEditor` feature.

**Reuse map — what this feature builds on rather than duplicates.**

| Need | Existing thing to reuse |
|---|---|
| Completion popup widget | `ui/completion_popup.py::_CompletionPopup` (§11's widget, extracted to its own module and shared by `xml_editor.py` and `ddl_object_editor.py`) — not reimplemented |
| Injection idiom | `XmlEditor.set_schema_model(model)` (§11) — mirrored as the DDL panel's `set_schema_index(index)` |
| Table/column/schema data source | `db/introspect.py::fetch_routines_and_triggers`, widened to also run `SCHEMA_SQL` (§17/§18.1) — no second fetch path |
| Query-API module precedent | `schema_learning/settings_index.py` (§11) — the shape `db/schema_index.py` follows |
| Trigger/function cross-reference | `TriggerInfo.function_name` / `RoutineInfo.signature` (§18.1) — the same reverse-lookup fact §18.1's dual-grouped tree already uses |
| Caret/token analysis | `sql/keywords.py`, `sql/tokenizer.py` (§18.4) — the new caret-context resolver joins them as a Qt-free `sql/` module |
| Editable host tab | `ui/ddl_object_editor.py::DdlObjectEditorPanel` (§18.5) — the only consumer in this pass |
| Simple table-pick idiom | an existing simple selection-dialog idiom (unattached-trigger table prompt) — no new dialog pattern invented |

**Invariants this feature must conform to** (inherited from §18.5 D1 and §5, restated because they are
load-bearing here specifically):

1. `DdlObjectEditorPanel` still never imports `db/introspect.py`, never opens a connection, and never
   branches on whether a project is open. `db/schema_index.py` is Qt-free; only `ui/` wires it in.
2. The unattached-trigger table association is **never** durable state — no project JSON, no sidecar
   file, no cache surviving tab close or app restart.
3. `fetch_schema`'s existing 3-query contract and its tests are untouched; DB Check keeps its own,
   separate `fetch_schema` call. The widening lands only in `fetch_routines_and_triggers`.
4. The index is built **once per DDL Explorer connect/refresh**, not per keystroke and not lazily
   per-popup-open.

### 18.7 Two live DDL Explorer instances — target vs. sandbox

> **Status: settled design (2026-08-05), not yet implemented.** Today there is exactly **one**
> `BrowserPanel` instance (`ui/ddl_buffer_panel.py`), **one** left-dock "DDL Objects" tab, **one** center
> `EditorPanel` DDL Explorer tab, and **one** database connection feeding all of it (§18.1). This
> subsection makes the DDL Explorer **per-connection** rather than a singleton, so a project with a
> provisioned sandbox (§18.5 D2/D2a) can browse it independently of the target/production database it was
> cloned from.

**What it is.** Once a project has a sandbox configured (§18.2's New Project sandbox step, or a sandbox
added later via Sandbox Setup…), a **second, separate DDL Explorer instance** becomes available: one
instance browses the **target** database (unchanged — today's single instance, connection `role =
target`), and the other browses the **local sandbox** (`role = sandbox`, §18.5 D2). Both can be open
simultaneously; each is its own left-dock tree tab and its own center-stage editor tab, not a toggle that
switches one shared pair between two connections.

- **The sandbox instance appears only once a sandbox exists for the active project.** With no sandbox
  configured, the DDL Explorer toggle behaves exactly as it does today (§18.1) — one instance, against
  the target connection. There is no empty/disabled "Sandbox DDL Explorer" affordance shown when no
  sandbox exists; the second instance's menu entry/tab is simply absent until a sandbox is provisioned,
  the same "no dead controls" posture already established for the sandbox button row (§18.5 carve-out 2).
- **Reuses `BrowserPanel`/`EditorPanel` as-is, instantiated twice — not a rewrite.** Both widget classes
  already take a `DatabaseSchema` (`set_schema`) and a synthesized buffer (`set_ddl_text`) as data; nothing
  about their rendering, tree-building or navigation logic is target-vs-sandbox-aware today, and none of
  it needs to become so. What changes is **how many of each are constructed and what connection params
  feed each one's fetch** — this is new instantiation/wiring, not new tree or editor behavior.

**Architecture change — tab identity keyed per-connection, not a singleton.** This is the genuinely new
part:

- `CenterStage`'s single fixed `ddl_tab_index` (§7/§18.1) becomes **two** dynamic tabs, addressed the same
  way §18.5's per-object tabs already are — by a **stable key**, not a remembered index — reusing the
  append-only/tail-only dynamic-tab machinery and its mandatory regression test (§18.5's carve-out 9)
  rather than inventing a second tab-management scheme. The key is the connection **role**
  (`"target"`/`"sandbox"`), since exactly one connection of each role can exist per project.
- Likewise the left-dock "DDL Objects" tab (§18.1) becomes **two** dock tabs, one per role, each wrapping
  its own `BrowserPanel` instance.
- `MainWindow`'s existing single-instance wiring (`_open_ddl_explorer()`, `_fetch_ddl_schema`,
  `_on_ddl_navigate_requested`, the visibility lockstep between the menu toggle and the tab ✕, §18.1) is
  **parameterized by role** rather than duplicated: one fetch/open/navigate/lockstep code path taking
  `role` and the corresponding `ConnectionParams`, invoked once for `target` (as today) and, when a sandbox
  exists, again for `sandbox`. The Database-menu "DDL Explorer" toggle becomes **two** checkable entries
  (or one toggle plus a second, sandbox-scoped one appearing once a sandbox exists) — exact menu wording
  is an implementation detail, not specified further here.
- Right-click ▸ Edit… (§18.5) from **either** instance opens the same `DdlObjectEditorPanel` tab type;
  which connection an edit ultimately targets (Apply to Sandbox vs. Apply to Target, §18.5) is governed
  entirely by the existing Apply gestures and their confirmation gates — browsing the sandbox's tree does
  **not** change what Apply-to-target's four hard preconditions require, and does not make Apply-to-sandbox
  implicit.

**Drift-marker computation is scoped per source connection — not a single shared computation.** §18.2's
`*`/`!` markers (local-file-vs-deployed, live-DB-vs-deployed) are computed once per introspected
`DatabaseSchema`, and each `BrowserPanel` instance now renders markers computed **against its own
connection's introspection**, not a markers set borrowed from the other instance. Concretely: the target
instance's `!` marker means *"the target database has drifted from the last-deployed reference"* exactly
as today; the sandbox instance's tree renders against the sandbox's own introspected schema and the
sandbox's own working-set bookkeeping (`SandboxSession.applied`, §18.5 D2's `text_sha1`) — it is a
**separate** drift/state computation, not the target's markers redrawn on a second tree.

**The tree must tolerate genuine divergence in the object set, not just drift on an identical set.** This
is the load-bearing difference from every other place in the app that shows "the same data from two
angles" (e.g. §15's Table References, §18.1's dual-grouped tree): the sandbox is an **independent,
editable database**, so its introspected routines/triggers/tables can be a **different set** from the
target's — objects applied only to the sandbox and never deployed, objects that exist on target but were
never cloned/applied to the sandbox, or (for a schema-only D2 baseline) tables present with columns but no
data. Each `BrowserPanel` instance's tree is built from **its own connection's introspection alone**
(`set_schema(schema, spans)`, unchanged signature) — there is no cross-referencing, no merged tree, and no
attempt to align the two trees' node sets or render a placeholder for "exists on the other side but not
here." An object present in the sandbox but not the target (or vice versa) simply does not appear in the
other instance's tree at all, exactly as if it were the only connection open.

**Reuse map — what this feature builds on rather than duplicates.**

| Need | Existing thing to reuse |
|---|---|
| Tree widget + rendering rules | `ui/ddl_buffer_panel.py::BrowserPanel` (§18.1) — instantiated twice, unchanged internals |
| Read-only synthesized buffer + editor | `ui/ddl_editor_panel.py::EditorPanel` (§18.1) — instantiated twice, unchanged internals |
| Introspection fetch | `db/introspect.py::fetch_routines_and_triggers` (§18.1/§18.6) — called once per role with that role's `ConnectionParams` |
| Second connection profile | `role = sandbox` (§18.5 D2). §17's keyed `ProfileKey` scheme is **target design, not implemented** — what ships today is `db/config.py`'s single hardcoded `"db"` QSettings group plus the project-scoped profiles in the project's own `.ddlproject/settings.json` (`ProjectSettings.target`/`.sandbox`, §18.2, ledger 2026-08-03) — no new connection mechanism either way |
| Dynamic, key-addressed tabs (not index-addressed) | §18.5's per-object `DdlObjectEditorPanel` tabs and their append-only/tail-only invariant + regression test (§18.5 carve-out 9) — the same pattern, keyed on connection role instead of object identity |
| Drift markers | §18.2's `*`/`!` computation (`compute_drift_markers`) — invoked per connection, not shared |
| "No dead controls" posture | §18.5 carve-out 2 (no sandbox button row until the sandbox lane exists) — mirrored here as "no second DDL Explorer entry until a sandbox exists" |

**Explicitly not designed here:** the exact menu/tab wording and layout for the two instances (left as an
implementation detail); any merged/diffed view showing both trees side-by-side or overlaid (rejected by
the "tolerate genuine divergence, no cross-referencing" rule above — that would be a different, undesigned
feature); and what happens to an open sandbox DDL Explorer instance when the sandbox is destroyed/reset
mid-session (an open question, below).

---

### 18.8 The Project Status window

> **Status: implemented and shipped 2026-08-06** (designed 2026-08-05, corrected the same day to the
> 5-node model below; the 4-node model in which the `app` node conflated **project tier** with **sandbox
> connectivity** is superseded, not layered alongside — Supersession Ledger, §28). Shipped as
> `ui/project_status_model.py` (the pure `build_diagram`/`quality_state` layer + assets, commit
> `9aa14ca`), `ui/project_status_panel.py::ProjectStatusPanel` (commit `7b0588d`) and the
> `MainWindow._build_project_status_diagram` / `_open_project_status` wiring behind **Database ▸ Project
> Status…** (commits `484ef64`/`4abaf61`). Opening the entry point **re-probes** rather than reading a
> cached result, the window is non-modal and single-instance (re-invoking raises the existing one), and
> the per-node **click-through action windows for Quality, Sandbox, Sandbox1 and Sandbox2 exist**.
>
> Three deliberate holes, stated rather than glossed:
>
> 1. **Sandbox1's "run/redo data clone" button is not offered**, and
> 2. **Sandbox2's "install plpgsql_check" button is not offered** — the panel accepts both as injected
>    callbacks (`on_run_data_clone`, `on_install_plpgsql_check`) and **hides any affordance whose callback
>    is `None`**, and `MainWindow` still passes `None` for both. **The reason has narrowed (2026-08-06):**
>    `ui/sandbox_controller.py::SandboxController` now ships and exposes exactly the two zero-argument
>    adapters these callbacks want (`on_run_data_clone` / `on_install_plpgsql_check`), each delegating to
>    `db/sandbox.py` and each already off-thread and confirmation-gated. What is still missing is only the
>    **MainWindow wiring** that constructs the controller, opens a session and passes those two bound
>    methods in. Until that lands the two windows stay status-only — the same "no dead controls" posture
>    as §18.5 carve-out 2. Sandbox2's button is **not** a second install action: it is one of two entry
>    points to the single one specified in §18.5 D2 (the other being Sandbox Setup…, the primary home).
> 3. **The App node's action window remains the deliberate placeholder** this subsection already flags as
>    open in §29: it states the tier plainly (`_APP_TIER_TEXT`) and offers no action. What the App node
>    should *do* is still undesigned.

**What it is.** A small graphical status window rendering project health as a **node-and-connector
diagram**, read left-to-right as a horizontal chain that splits at the end: **quality → app → sandbox →
(sandbox1 / sandbox2)**. It is the visual home of the top-of-§18 capability probe's result
(`ProjectCapabilityStatus`, `pgtp_editor/db/sandbox.py`) — the same probe already wired to run
automatically on project open (`MainWindow._set_active_ddl_project` → `refresh_project_capability_status()`)
and, per this subsection, again on demand whenever this window itself is opened.

**Layout — five node families plus connectors, in this arrangement:**

```
[quality] --connector--> [app] --connector--> [sandbox] --connector--> [sandbox1]  (upper)
                                                                  \--connector--> [sandbox2]  (lower)
```

| Node | Position | Represents | Backing state |
|---|---|---|---|
| **Quality** | leftmost | The quality/target database's connection status | The `target` connection profile (§17/§18.2) — reachability, not yet further broken into states beyond connected/not by this pass |
| **App** | 2nd | The project's **tier** — standalone / quality-project / development-project — and nothing else | `ProjectCapabilityStatus`/`ProjectTier`, rendered as one of the 3 states below. **No longer carries sandbox connectivity** — that is now the Sandbox node's job |
| **Sandbox** | 3rd, its own full node (not a connector) | The sandbox database's **live connectivity**: not-set-up / connection-ok / offline / connected-but-tools-missing | `SandboxCapabilities` (probe reachability) + `SandboxMode`/`data_clone_available` for the tools-missing state — see the state table below |
| **Sandbox1** | upper-right | The sandbox's **data-fill** status: schema-only vs. data-cloned via `pg_restore` (§18.5 D2/D2a), and whether that provisioning succeeded | D2a's clone outcome / `db/ddl_project.py::ProjectSettings.sandbox_mode` (`SandboxMode.SCHEMA_ONLY` / `WITH_DATA`) plus success/failure of the last provisioning run |
| **Sandbox2** | lower-right | Whether the **`plpgsql_check` Postgres extension is installed** in the sandbox database — a capability/installation marker, **not** a per-object lint pass/fail result (that already lives in the DDL object editor's Audit panel, §18.5 D3) | `SandboxCapabilities.plpgsql_check_state`, **but see the corrected 2-state reading below** — the property's own 4 values don't map 1:1 onto this node (flagged, not glossed over) |
| **Connectors** | between each pair | Line art linking quality→app, app→sandbox, and sandbox→(sandbox1, sandbox2); the sandbox→sandbox1/2 connector visually splits into two after the sandbox node | **Stateless — position-keyed, one asset each** (`ui/project_status_model.py::ConnectorKind`: `connector_quality-app` / `connector_app-sandbox` / `connector_sandbox-db`, the third being the visually-splitting one), plus `_drk` variants; resolved 2026-08-06, ledger §28 |

The owner's diagram depicts the Sandbox node with its own icon (a monitor/screen bearing a Postgres
elephant logo plus a database icon) — visually distinct from a connector, confirming it is a fifth node
family, not a richer connector state grafted onto the app→sandbox1/2 link.

**Image asset convention — shipped.** Each node/connector is rendered from a pre-made bundled image in
`pgtp_editor/resources/status/`, named `[position]_[status]` — e.g. `app_project_setup`,
`sandbox_connected`, `sandbox1_filled`, `connector_quality-app`. Assets are **`.svg` only**
(`ui/project_status_model.py::ASSET_EXTENSION = ".svg"`, per BUG-029 — the earlier `.png` slices were
deleted), and the lookup table **is** the state enums: each per-family enum's *value* is the filename
stem, resolved through `asset_filename(stem, dark) -> "<stem>[_drk].svg"`, with `all_asset_stems()`
backing the test that guards against a typo'd stem shipping as a silently missing image.

**Dark-mode asset convention — every asset has a `_drk` counterpart.** For each `[position]_[status]`
base file there is a same-named dark-theme variant with a `_drk` suffix appended before the extension —
e.g. `quality_connection_ok.svg` / `quality_connection_ok_drk.svg`, `sandbox_connected.svg` /
`sandbox_connected_drk.svg` (`DARK_SUFFIX = "_drk"`, applied by `asset_filename(stem, dark)`). The
loading code selects the `_drk` file whenever the app is currently running in its dark theme, and the
plain file otherwise.
**Verified against the codebase, not assumed:** the app has no OS/system dark-mode *detection* — theme
selection is an explicit, user-toggled menu checkbox, **Light Theme** (`MainWindow`, `main_window.py`,
unchecked by default, i.e. dark-by-default), applied via `ui/theme.py::apply_theme(app, light: bool)`.
There is no `QStyleHints`/`colorScheme()` OS-preference read anywhere in `pgtp_editor/`. This window's
`_drk`-vs-plain selection should therefore key off the **same boolean** the Light Theme action already
tracks (`MainWindow._light_theme_action.isChecked()` / the `light` argument last passed to
`apply_theme`), not a new or different signal — reusing the existing toggle, not adding a second
theme-detection mechanism.

**Per-node state enumeration — concrete, from the owner's reference images, now shipped as the enums in
`ui/project_status_model.py`** (`QualityState`/`AppState`/`SandboxState`/`Sandbox1State`/`Sandbox2State`,
whose values are the asset filename stems). This supersedes nothing added above; it fills in the exact
state lists the node-family table and the App/Sandbox state tables already reference, plus gives
Quality, Sandbox1 and Sandbox2 their first explicit enumerations.

| Node | States (icon look) | Notes |
|---|---|---|
| **Quality** | `quality_connection_not_set_up` (locked/gray padlock over a database icon); `quality_offline` (red — connection attempted but failed/unreachable); `quality_connection_ok` (green — connected, healthy) | **Corrected 2026-08-05:** the locked/gray icon is **not** a distinct auth-failure mode alongside a general error state — its actual filename is `quality_connection_not_set_up`, i.e. the quality/target connection is simply **not configured yet**, the same semantic category as the Sandbox node's `sandbox_not_set_up` state. This mirrors the Sandbox node's not_set_up/offline/connected pattern exactly: `not_set_up` (never configured) / `offline` (configured but unreachable) / `connection_ok` (configured and healthy). The earlier "is locked/gray a distinct failure mode from red?" open question is resolved by this — there is no ambiguity once locked/gray is understood as "not set up," not "auth failed" |
| **App** | `app_standalone` (a generic "\<XML\>" editor-window icon — the plain-editor-no-project look); `app_project_not_setup` (gray/inactive gear+lightbulb); `app_project_setup` (green gear+lightbulb) | Matches the already-specified 3-state, tier-only model above one-for-one; this row only supplies the concrete icon look per state |
| **Sandbox** | `sandbox_offline` (red — offline/unreachable); `sandbox_not_set_up` (gray — not set up); `sandbox_connected` (green — connection ok) | **Only 3 visual states, not 4.** The previously-noted `sandbox_tools_missing` condition (sandbox reachable but `psql`/`pg_restore` absent) is **not** a distinct icon — it still renders the same green/connected icon, with the missing-tool detail surfaced only in the node's click-through status/help window (consistent with this subsection's existing click-through description above: name the missing tool, link to help). The Sandbox node's state table earlier in this subsection listed `sandbox_tools_missing` as one of four *backing states*; that backing-state distinction is still real (`SandboxCapabilities`/`degraded_reason` still tell tools-missing apart from offline, kept as `SandboxDegradation` for the click-through window), but **it maps onto the same icon as `sandbox_connected`**, not a fourth icon — corrected here from any earlier reading that implied a 4th visual state |
| **Sandbox1** (data-fill) | `sandbox1_empty` (lighter/schema-only look — schema-only, or a with-data sandbox whose clone has not yet landed); `sandbox1_filled` (fuller green — data cloned via `pg_restore`, §18.5 D2a) | 2 visual states. **Open point (§29):** no distinct "clone in progress" or "clone failed" icon has been provided yet — flagged as a gap to confirm with the owner, not invented here |
| **Sandbox2** (`plpgsql_check` capability) | `sandbox2_plpgsql_check_not_installed` (red X over a magnifying-glass-on-database icon); `sandbox2_plpgsql_check_installed` (teal/cyan check-mark, same magnifying-glass-on-database motif) | **Corrected 2026-08-05:** these are **install-state** icons, not run-result icons — the red-X state means "the `plpgsql_check` extension is not installed in this sandbox," and the check-mark state means "it is installed." This is **not** whether a specific routine passed or failed a lint check (that per-object result lives in the DDL object editor's Audit panel, §18.5 D3) — this node shows environment/capability status only. The earlier "no distinct not-yet-run icon" open question no longer applies: there is no run result to represent here, only installed/not-installed, and 2 states fully cover that |

Each state name in this table **is** the shipped asset filename stem — the enum values in
`ui/project_status_model.py` are the stems, and `tests/ui/` guards that every stem's `.svg` (and `_drk`
variant) actually ships in `resources/status/`; the earlier verify-before-wiring caveat is retired.

**App node — 3 states, project tier only (corrected from the 4-state conflated model):**

| State | Meaning | Corresponds to |
|---|---|---|
| `app_standalone` | No project is open at all | Tier 1 (standalone, §18 taxonomy) |
| `app_project_not_setup` | A DDL-versioning project is active but has no working sandbox | Tier 2 (quality project), `ProjectCapabilityStatus.tier is ProjectTier.QUALITY` |
| `app_project_setup` | A DDL-versioning project is active with a working sandbox | Tier 3 (development project), `ProjectCapabilityStatus.tier is ProjectTier.DEVELOPMENT` |

The App node no longer distinguishes *why* a project is at tier 2 (never configured vs. configured-but-
offline vs. tools-missing) — that finer-grained live-connectivity detail is now the **Sandbox** node's
job, described next. The App node answers exactly one question — "what tier is this project running
in?" — and answers it the same way regardless of *why* tier 3 isn't reached.

**Implementation note — verify before building.** `pgtp_editor/db/sandbox.py::ProjectTier` today is a
**2-member** enum (`QUALITY`, `DEVELOPMENT`); there is no `ProjectTier` member for tier 1 at all —
"standalone" is simply the absence of an open project, never a value the enum carries, and
`determine_project_tier()`'s own docstring says as much ("Tier 1 … is therefore never returned"). The
corrected 3-state App node above is therefore **not** a straight 1:1 rendering of one enum: `app_standalone`
must be derived from "no project is currently open" (a fact `ProjectCapabilityStatus` itself doesn't
carry — it models only an already-open project), while `app_project_not_setup`/`app_project_setup` map
directly onto `ProjectTier.QUALITY`/`DEVELOPMENT`. This is a clean, buildable mapping, but it is **not**
the shape the first (4-state, now-superseded) pass assumed, so flag it rather than assume the existing
`ProjectCapabilityStatus`/`ProjectTier` shapes need no adjustment — they don't need new members, but the
window's App-node rendering logic needs an explicit "is a project open at all?" check that sits outside
`ProjectCapabilityStatus`.

**Sandbox node — NEW, distinct node; the live-connectivity counterpart to the App node's tier state.**
Shipped stems: `ui/project_status_model.py::SandboxState`. **3 visual states**
(confirmed against the owner's reference images, below), backed by a 4-way distinction in the underlying
capability model — the 4th backing condition (tools-missing) does not get its own icon:

| Visual state (shipped stem) | Icon look | Meaning | Backing state |
|---|---|---|---|
| `sandbox_not_set_up` | gray | No sandbox is configured for this project at all | `ProjectCapabilityStatus.degraded_reason == "no local sandbox configured for this project"` (`NO_SANDBOX_REASON`, compared exactly) |
| `sandbox_connected` | green | A sandbox is configured and reachable — **also covers the tools-missing condition below**, which renders identically | `ProjectCapabilityStatus.tier is ProjectTier.DEVELOPMENT`; **or** reachable with `SandboxMode is WITH_DATA` and `psql`/`pg_restore` missing from `PATH` (see the tools-missing row) |
| `sandbox_offline` | red | A sandbox is configured but currently unreachable | `ProjectCapabilityStatus.tier is ProjectTier.QUALITY` with a `degraded_reason` naming an unreachable probe (e.g. `"sandbox unreachable: …"`) |

**Tools-missing is a backing condition, not a 4th icon.** When the sandbox database itself is reachable
but `psql`/`pg_restore` are not on `PATH` (relevant only when `SandboxMode is WITH_DATA`, matching D2a's
existing capability distinction; `ProjectCapabilityStatus.tier is ProjectTier.QUALITY` with
`degraded_reason` naming `pg_dump`/`pg_restore` missing), the node still renders the plain
`sandbox_connected` (green) icon — there is no separate `sandbox_tools_missing` asset. The detail is
surfaced only in the node's click-through status/help window (below: names the missing tool, links to
help). **Corrected here** from an earlier reading of this subsection that could be taken to imply a
4th visual state; the click-through behavior described later in this subsection was already right, this
table is what's been tightened to match it.

This is the fine-grained, live-connectivity state the old conflated `app_*` node used to carry
(`app_sandbox_not_set_up` / `app_sandbox_connection_ok` / `app_sandbox_offline` from the superseded pass
map onto `sandbox_not_set_up` / `sandbox_connected` / `sandbox_offline` here). The stems above are the
shipped `SandboxState` enum values — the earlier inferred-not-owner-verbatim caveat is retired.

**Absence rule — no sandbox means the sandbox nodes are ABSENT, not grayed out — now covering three
node families, not two.** When `ProjectCapabilityStatus.degraded_reason == "no local sandbox configured
for this project"` (i.e. the project has never had a sandbox configured at all), **the Sandbox node,
Sandbox1, Sandbox2, and their connectors do not render at all** — the diagram shows only quality→app,
ending at the app node. This is the same "no dead controls" posture already established for the sandbox
button row (§18.5 carve-out 2) and for the second DDL Explorer instance (§18.7): an inactive capability
is not shown disabled, it is simply not shown. A sandbox that IS configured but currently offline or
tools-missing still renders the Sandbox node plus Sandbox1/Sandbox2 — in whatever failed/unknown state
applies — because a sandbox exists conceptually for this project even though it is not fully reachable
right now; only "never configured" removes the nodes entirely.

**Probe timing — unchanged from the top-of-§18 taxonomy, restated here as this window's specific
trigger.** The capability probe (`refresh_project_capability_status()`) runs (a) automatically whenever
a project is opened (already wired, `_set_active_ddl_project`), and (b) on demand whenever the Project
Status window itself is invoked — opening this window is itself a trigger for a fresh probe, not a
passive reader of a stale cached result.

**All five node families are clickable, but the click-through behavior is now two distinct patterns, not
one uniform "opens an action window":**

- **Quality and App — one-step action window.** Clicking the Quality node opens an action window showing
  connection info plus a reconnect action. Clicking the App node opens *some* action window scoped to the
  project-tier concern, but its exact contents are **not yet specified by the owner** (unchanged open
  question from the first pass — flagged again in §29, not invented here).
- **Sandbox — one-step status/help window.** Clicking the Sandbox node opens a window showing
  status/connection details; if the underlying condition is specifically tools-missing (a reachable
  sandbox with `psql`/`pg_restore` absent from `PATH` — rendered as the same `sandbox_connected`
  icon, not a distinct one, per the state table above), the window **names the missing tool** and links
  to a help section. **Verified:**
  the app's only existing help surface is the general **in-app manual** (§24, `resources/manual.md`,
  toggled via F1 / Help ▸ Manual, `MainWindow` around `main_window.py:3777`) — there is no dedicated,
  topic-anchored help-navigation concept (no deep-link-to-a-heading mechanism). "Links to a help
  section" therefore most plausibly means **opening the manual**, ideally scrolled to a
  tool-installation topic — but no such topic exists there yet, and no anchor/deep-link mechanism exists
  to jump to one even if it did. Treat both the manual content and any deep-link mechanism as **new
  work**, not reuse, and record it as open in §29.
- **Sandbox1 and Sandbox2 — two-step status+action window, NOT a direct one-click trigger.** Clicking
  either opens a status/help window that **itself contains an embedded action button** — e.g. Sandbox1's
  window offers "run data clone now" / "redo clone." Sandbox2's window, when `not_installed`, offers an
  **"install the plpgsql_check extension"** action button (runs `CREATE EXTENSION IF NOT EXISTS
  plpgsql_check` against the sandbox — the same one-click install already specified as living inside
  Sandbox Setup, §18.5 ledger row 2026-08-02, via `install_plpgsql_check(session)`, now also reachable
  from here) — **not** "run a check," since this node is about installation state, not a lint result.
  When Sandbox2 is already `installed`, the window is purely informational (states the fact); **no
  meaningful action remains to offer in that state** — there is nothing left to install, and re-running
  `CREATE EXTENSION IF NOT EXISTS` on an already-installed extension is a no-op not worth surfacing as a
  button. This is a deliberate two-step pattern (open status → press the button inside it, when one
  applies), not a single click that fires the action directly — distinct from how Quality/App/Sandbox's
  action windows are described.

**Explicitly not yet specified (recorded, not blocking):**
- **The App node's action-window contents/behavior.** Flagged explicitly in §29 as an open question —
  implementers must not invent this; it needs a further owner pass. (Quality's, Sandbox's, Sandbox1's and
  Sandbox2's click-through *patterns* are now specified above; App's is the one node whose action-window
  content remains entirely open.)
- **The Sandbox node's "links to a help section" content and deep-link mechanism.** Verified: the app's
  only existing help surface is the general in-app manual (§24), which has no topic-anchored deep-link
  mechanism today — both the tool-installation help content and any way to jump straight to it are new
  work, not reuse (see above).

**Reuse map.**

| Need | Existing thing to reuse |
|---|---|
| Tier data (App node) | `db/sandbox.py::ProjectCapabilityStatus`/`ProjectTier`/`determine_project_tier` — consumed as-is, not recomputed; App-node rendering additionally needs an "is a project open at all?" check outside this shape (see implementation note above) |
| Live connectivity (Sandbox node) | `db/sandbox.py::SandboxCapabilities` (`probe_error`) + `ProjectCapabilityStatus.degraded_reason` + `SandboxMode`/`data_clone_available` for the tools-missing state |
| Probe trigger | `MainWindow.refresh_project_capability_status()` — called again on this window's open, exactly as it already is on project open |
| Data-fill state (Sandbox1) | `db/sandbox.py::SandboxMode` (`SCHEMA_ONLY`/`WITH_DATA`) + D2a's clone outcome |
| plpgsql_check install state (Sandbox2) | `SandboxCapabilities.plpgsql_check_state` — **flagged mismatch:** this property already returns exactly the right *kind* of fact (installed vs. not, never a lint result), confirmed by its own docstring and by `install_plpgsql_check(session)` (§18.5 D2) being the same `CREATE EXTENSION IF NOT EXISTS plpgsql_check` action this node's button fires. But it is **4-valued** (`"installed"` / `"installable"` / `"absent"` / `"unknown"`), while this node has only **2** icons (`sandbox2_plpgsql_check_installed` / `sandbox2_plpgsql_check_not_installed`). The rendering logic must collapse `"installable"`/`"absent"`/`"unknown"` onto the single `not_installed` icon (all three mean "not installed," just for different reasons — extension available-but-uninstalled, unavailable, or probe-failed) — this collapse is not yet owner-confirmed and is left as an implementation detail rather than a further open design question, since the 2-icon set leaves no room for a 4th visual state |
| Install action (Sandbox2) | **One action, two entry points** (settled 2026-08-06, §18.5 D2, ledger §28): `SandboxController.install_plpgsql_check()` → `install_gate` → `db/sandbox.py::install_plpgsql_check(session)`. **Primary home: Sandbox Setup…**, inside the dialog next to the probe result it depends on. This window's Sandbox2 button is the **second entry point to that same method** (via the `on_install_plpgsql_check` adapter) — it re-derives no gate, re-types no reason string and opens no session of its own |
| Session, off-thread execution (Sandbox1/Sandbox2 buttons) | `ui/sandbox_controller.py::SandboxController` — the holder of the one `SandboxSession`; this window never calls `open_sandbox` itself |
| "No dead controls" posture | §18.5 carve-out 2 / §18.7's absent-not-disabled sandbox-instance rule — same principle, now governing the Sandbox node, Sandbox1, Sandbox2, and their connectors together |

---

## 19. PHP generation (vendor) & Save

Implements §6.6. Shells out to the vendor generator; because the generator reads from disk, this also
owns File Save / Save As.

- `generation/config.py` (`generator_config.json` in AppData; injectable `generator_config_dir`):
  `load_executable_path`/`save_executable_path` (`executable_path` key) and `re_phpgen_root` (§20).
- `generation/runner.py`: `build_generate_command(exe, pgtp_path, output_folder)` (pure) →
  `[exe, pgtp_path, "-output", output_folder, "-generate"]`. `GeneratorRunner` wraps `QProcess`
  (`run(command, on_output, on_finished, cwd=None, extra_env=None)`, merged stderr; injectable).
- **Save / Save As:** write raw editor text UTF-8 (`.bak` first if overwriting). Save → `_current_project_path`
  (else Save As). Save As → `getSaveFileName` (`PGTP files (*.pgtp)`).
- **Generate PHP flow:** guard no-project / no-exe; prompt Save vs Save As (so disk matches editor);
  output folder prefilled from `Project@outputPath` else project dir; run with streaming `[PHP]` audit
  lines; finish → summary + success/critical dialog. **Locate PHP Generator Executable…**
  (`getOpenFileName`). **Open Output Folder** via `QDesktopServices.openUrl` (enabled after a run).
- **Output folder default when a local project (§18.2) is open — added 2026-08-03.** The output-folder
  prefill above (`Project@outputPath` else project dir — "project dir" there meaning the directory
  containing the open `.pgtp` file, unrelated to §18.2's local project) is **superseded by the local
  project's own folder** whenever a §18.2 local project is open: the folder the user chose when creating
  the project (§18.2) becomes the prefilled output folder, ahead of both existing fallbacks. This is
  still a **prefill**, not a silent redirect — the folder picker in the Generate PHP flow above is
  unchanged and the user can still pick a different folder; only the default changes. This does not
  apply outside a local project (no-project mode keeps today's `Project@outputPath`-else-project-dir
  default unchanged, consistent with §18.2's "no-project mode is completely unaffected" principle).

---

## 20. re_phpgen — own generator & gap loop

A **separate standalone repo** (`C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen`, branch `master`)
that reverse-engineers the vendor `.pgtp`→`.php` transformation. Design/spec/plan docs live in the
pgtp_editor repo; implementation lives in re_phpgen. Strategy: **parity-first** — emit per-page `.php`
byte-identical (after normalization) to freshly-regenerated vendor output, running against the vendor's
**unmodified** runtime; a future Phase 2 uses the harvested runtime-contract map to begin owning the
runtime.

- **Pipeline:** parse `.pgtp` (reuse pgtp_editor's model layer read-only; must expose `DataSources`) →
  intermediate model → per-page emit. Template + procedural hybrid: a **single** `page_class.php.tmpl`
  serves both master and detail classes (master vs detail = two slot differences: `EXTENDS`, `CMDRG`);
  all conditionality lives in Python slot-computation, never the template language. Modules: `catalog.py`
  (`detail_tree`), `skeleton.py` (`emit_page_file`), `pangen.py` (`emit_project`, best-effort),
  `gap.py` (`CAUSE_MARKERS`), `cli.py`/`__main__.py`.
- **Oracle & corpus:** vendor CLI is the test oracle; corpus = 37 real projects (`input/01..37.pgtp`).
  **Hard rule: regenerate, never trust stale pairs.** Normalizer (`normalize(php)`) folds
  non-determinism; comparison mode `masked-skeleton-v1` masks handler code + method bodies symmetrically.
- **Verified derivation rules** (master/detail slice): Detail emits a class **iff FK valid** (every
  `FieldMap@foreginColumnName` names a field in the detail's own field set), else the subtree drops;
  class order = depth-first **post-order** (children before parent, master last); detail class name =
  `"_".join(sanitize(t) for t in ancestry)+"Page"` with file-global 2-digit ordinals on duplicate stems;
  DetailPage skeleton = master skeleton − `CreateMasterDetailRecordGrid` + `extends DetailPage`; the
  global-handler block + `GetEnable*` flags + page parameters map from attributes by corpus correlation
  (residual ambiguity → manual GUI probe, never guessed).
- **Gap loop (editor integration):** the vendor baseline is produced **manually from the GUI** (the CLI
  is untrusted for automation). The editor calls re_phpgen **as a subprocess, never imports it**;
  `re_phpgen_root` config key resolves the runtime (`<root>\venv\Scripts\python.exe` if present else
  `sys.executable`; **Locate panGen Runtime…** overrides, validated to contain `src\re_phpgen`). CLI:
  `pangen <project> --out <dir>` and `analyze <project> --vendor <dir> --ours <dir> --json <path>` (writes
  a `schema_version 1` gap JSON with per-page statuses ok/diff/missing/error, cause buckets, capped
  `difflib` hunks). Editor menu actions (Generation menu conventions): **panGen (Generate Own PHP)** →
  `pangen … --out <folder>\_pangen`; **rePHPgen (Analyze Gap)** → require a vendor `.php` present, then
  pangen + analyze → summary; **Save reJSON…** (enabled after an analysis); **Locate panGen Runtime…**.

> **Branch-model note:** the re-phpgen work was folded into `main` and the branch deleted 2026-07-20; the
> project is now single-branch. Some re_phpgen spec headers still say `Branch: re-phpgen` (stale).

### 20.4 Production cutover (target design — not yet reached)

> **Status: target state, not yet implemented.** No promotion has happened; nothing described here
> exists in the codebase yet. This subsection formalizes the exit criteria referenced by §1's staged
> hard boundary.

`re_phpgen`'s end goal is to **replace** the vendor generator for real deployments, not to remain a
permanent gap-analysis-only tool. Promotion out of gap-analysis-only status requires **all three**
falsifiable criteria to hold simultaneously — none is sufficient alone:

1. **100% byte-parity** (post-normalization, `masked-skeleton-v1` comparison mode, §20) across the
   **full 37-project corpus** — the gap-analysis JSON must show zero `missing`, zero `error`, and zero
   residual-`diff` statuses for every page in every project.
2. **Verified determinism** — a twice-generate diff (same project, same `re_phpgen` run twice) must be
   empty. Currently unverified (§29 Open questions).
3. **The 8 parked edge-case pages** (471/479 cap, §20/§29) are resolved (parity achieved) or explicitly
   accepted as known-unsupported (documented, not silently dropped).

**Cutover mechanism, once all three hold:** promotion is **per-project and explicit** — a deliberate
user action via a new **Generation menu** action (name/placement TBD at implementation time, alongside
the existing panGen/rePHPgen actions, §26) — never silent, never automatic based on crossing a parity
percentage threshold. phpgen (vendor CLI/GUI) remains available **indefinitely** afterward as the
fallback/reference oracle: parity regressions in `re_phpgen` output are caught by diffing against
phpgen, never assumed away once cutover happens.

**Deferred, not designed here:** a minimal Git integration scoped to `re_phpgen`'s per-project output
folder — see §21's forward-reference paragraph, which is the canonical statement of this deferral.

---

## 21. Custom PHP editing

> **Status: phase 1 built, not fully wired (2026-08-06 audit).** `ui/php_file_tab.py::PhpFileTab`
> ships (commit `82af729`) — one standalone `.php`/text file per tab, its own dirty state, its own
> `FindReplaceBar`, save through an injected `resolve_save_path` + `writer` pair, the Ctrl+Z event-filter
> carve-out, and §22's lint seams (`lint_on_save`, `request_lint()`, `lint_reported`) — and `CenterStage`
> hosts it in the dynamic key→widget map (`_php_file_tabs`, keyed by `php_tab_key`;
> `open_php_file_tab`/`close_php_file_tab`/`update_php_file_tab`/`active_php_file_tab`, re-invoking
> focuses the existing tab). **The entry point now exists** (verified 2026-08-07): `_build_file_menu` builds
> **File ▸ "Open PHP File…"** between `Open…` and the §18.2 project group, connected through a lambda to
> `_php_tabs.open_php_file_dialog()`. **Drag-drop is still absent.** Scope is deliberately narrow, in the owner's own words: *"php ide from my point of view is a rich
> text editor like we already have, adding features one by one. the goal is to have something as
> useful as notepad++."* This is **not** a new IDE architecture and **not** code intelligence/LSP —
> it reuses the existing `ui/code_editor.py::CodeEditor` widget (already implemented; already does PHP
> syntax highlighting for inline event-handler bodies, §8) as a general multi-file editor, with
> features added incrementally.

**Phase 1 (the "Notepad++" baseline):**
- **File ▸ "Open PHP File…"** (+ drag-drop) opens any `.php`/text file in a new `CenterStage` tab
  (closable, dirty-marked) — the same per-tab document routing precedent as the Edit XSD tab (§7).
  Multiple files open concurrently as ordinary tabs. **No structural tie to a `.pgtp` project is
  required at this level** — any file opens standalone, independent of whether a project is loaded.
- Each tab hosts the **existing** `CodeEditor` in `language="php"` mode with its own
  `FindReplaceBar` instance (same pattern as Edit XSD, §7/§15) and its own Ctrl+S/undo, independent of
  the project document's dirty state.

**Explicitly sequenced, incremental follow-ups** (named as the roadmap only — not designed in detail
here; build one at a time, in this order, matching "adding features one by one"):
1. **A PHP fold-region provider** for `CodeEditor` — the shared fold *machinery* already exists since the
   2026-08-01 `GutterBookmarkFoldMixin` extraction (§8, `ui/editor_gutter.py`): `CodeEditor` mixes the
   mixin in, overrides `_foldable_region_starting_at` as a lookup into `self._fold_regions`, and exposes
   `set_fold_regions(regions)` for hosts to install regions from outside. What is missing is only the
   **PHP-specific region computation** (brace/`{`…`}` blocks, function/class bodies, heredocs) plus the
   host wiring that calls `set_fold_regions()` — today no host installs regions for JS/PHP, so folding is
   inert there (§8). Mirrors how the DDL editor installs `DdlObjectSpan`-derived regions.
2. **A file-tree dock tab** for a configured "custom code" folder (parallel to Project Tree, §7),
   giving the scattered Gantt/print/loader-style files one browsable home instead of ad-hoc opening —
   folder configured per-project, analogous to `Project@outputPath`.
3. **Find in Files** across that folder — extends §15's search core to multi-file.

**Explicit non-goal:** no code intelligence — no LSP, no parse-based autocomplete. This is a recorded
scope decision, not a gap to eventually fill.

**Forward reference (deferred, not designed here):** once this section and §20.4 (Production cutover)
both exist, a minimal **Git integration** — status/commit/diff/pull/push, subprocess-based wrapper, not
a full client — scoped to this section's custom-PHP folder and/or `re_phpgen`'s per-project output
folder is the natural next step. Explicitly deferred; no section number spent on it yet.

---

## 22. Lint integration

> **Status: built, not fully wired (2026-08-06 audit).** The `pgtp_editor/lint/` package ships (commit
> `90c6806`: `findings.py` — pure stdout/stderr/exit-code parsing into `LintOutcome`/`LintStatus` and
> ready-to-append `[Lint]` `audit_lines`; `runner.py` — the one injectable process spawn;
> `config.py` — the `lint_executable_path` key; `service.py` — `LintService.lint_text`, which **never
> raises**), and `ui/php_file_tab.py` consumes it (§21): the tab owns `lint_on_save`, `request_lint()`
> and the `lint_reported` signal, and runs the lint off the GUI thread. **Remaining gap: the MainWindow
> host side** — Tools ▸ "Lint Current File", the "Locate PHP Linter…" action and the Audit-panel append
> consuming `lint_reported` are not wired yet. The §21-first sequencing held: the lint hangs off §21's
> tab, which itself shipped first.

- Runs an external linter (`php -l`, optionally full `phpcs`) against the active custom-PHP tab's
  content (§21), either on save (toggleable) or via **Tools ▸ "Lint Current File"**.
- Executable path configured with the same pattern as `generation/config.py`'s `executable_path`
  (§19): a new `lint_executable_path` key + a "Locate PHP Linter…" action.
- Output feeds the existing Audit panel (§7) with a new `[Lint]` prefix, following the same
  click-to-navigate convention as `[Validate]`/`[Find]`.
- **`[Lint]` is reserved for PHP linting, and only PHP linting.** SQL/plpgsql findings from §18.5's
  sandbox validation ladder use **`[Check]`**, and §18.4's formatter refusals use **`[SQL]`**. The
  three-way reservation is recorded here as well as in §7 and §18.5 deliberately: several
  linter-shaped features feeding one Audit panel must be distinguishable at a glance, and none may
  quietly annex another's prefix.
- **Non-blocking:** advisory only — never prevents Save.

---

## 23. MCP integration

> **Status: built, not fully wired (2026-08-06 audit).** `pgtp_editor/mcp/` ships (commit `09db778`:
> `server.py` — the stdio JSON-RPC transport, `serve_stdio`/`start_server_thread`; `tools.py` — exactly
> the six tools below; `providers.py` — `LiveProjectProvider`/`FileProjectProvider`; `serialize.py` —
> pure data→JSON, never renders a password; plus `__main__.py` for `python -m pgtp_editor.mcp`), and
> `main.py` carries the **`--mcp`** flag, which runs the headless stdio server instead of the GUI.
> Importing the package starts nothing — a session begins only via `serve_stdio` or
> `start_server_thread`. **Remaining gap: the Tools ▸ "Start MCP Server" menu entry** (the GUI-side
> `LiveProjectProvider` wiring in `MainWindow`) is not wired yet.

- An optional embedded MCP server, **off by default** (opt-in in Preferences) — it exposes project
  data to any connected MCP client, so it must not be silent or default-on.
- Exposes the app's already-Qt-free pure layers (`model/`, `diff/`, `db/`, `analysis/` — per §5's
  existing dependency rule, these have no Qt dependency) as MCP tools via a thin adapter, with **no new
  business logic**: e.g. `read_project(path)`, `list_pages(path)`, `get_node(path, identity)`,
  `diff_projects(source, target)`, `list_db_tables(connection)`, `list_db_routines(connection)` (the
  last two build on §18.1's DDL Explorer introspection, which now exists).
- Runs over **stdio**; started via **Tools ▸ "Start MCP Server"** or a `--mcp` CLI flag for headless
  use. When the GUI is running it shares the currently-open in-memory model; running headless it
  operates file-path-driven instead.

---

## 24. In-app manual

English Markdown manual bundled at `pgtp_editor/resources/manual.md` (via
`[tool.setuptools.package-data]`). `ui/manual_panel.py`: `load_manual_text()` (via `importlib.resources`),
`parse_chapters(md)→list[Chapter{level, title}]` (ATX headings, skips fenced code), `ManualPanel(QTextBrowser)`
(read-only, external links, `set_markdown`, `scroll_to_chapter(index)`), `ManualContentsPanel(QWidget)`
(`QTreeWidget`, `chapter_selected(int)`). Center-stage **Manual** tab + left-dock **Contents** tab; **Help
▸ Manual (F1)**. **The chapter list is owned by the `manual-maintainer` agent** and evolves with every
feature — this spec deliberately does not enumerate it. `manual.md`'s `##` ATX headings are the source
of truth, and the Contents tree is derived from them by `parse_chapters`; a feature is not done until
the manual reflects it (`CLAUDE.md`'s manual policy). Offline, read-only (no editing/searching, single
language).

---

## 25. Debug mode

Activated by `--debug` or `PGTP_EDITOR_DEBUG=1`; `debuglog.setup(debug=)` runs **before** `QApplication`.
Only new module: `debuglog.py`. Log dir `%LOCALAPPDATA%\MDS\PGTP Editor\logs\` (fallback
`~/.pgtp_editor/logs`, pure `log_dir()`): `errors.log` always-on (WARNING+, rotating 3×1 MB) +
`debug_YYYYMMDD_HHMMSS.log` per session (unrotated).

- **Always captured:** session header, uncaught exceptions (`sys.excepthook` + `threading.excepthook` +
  Qt slot path), Qt messages (`qInstallMessageHandler`), Python warnings.
- **Debug adds:** (a) auto-trace via `sys.monitoring` (3.12+, `PROFILER_ID`, PY_START/PY_RETURN/RAISE),
  scoped to `pgtp_editor` files with a hot-path exclusion list, TRACE level (5) to the debug file, args/
  returns not logged; (b) ~15 semantic seam logs (open/save/close, parse/reparse, undo/redo, DB
  connect/test/check/rename, generation command+exit+duration, schema enrich, diff/merge, caption,
  theme/toolbar/dock, dialog open/close). **Redaction:** `ConnectionParams.redacted()` (locked by test).
- UI: status-bar "DEBUG" chip; **Help ▸ Open Log Folder** (injectable `opener=` seam). Failure-safe
  (tracer failure → WARNING + continue).

---

## 26. Consolidated menu bar

**Since FQ-016 (2026-08-07) the app has TWO menu bars** (§7 owns the container and the mechanics):

| Bar | What it holds | Composability |
|---|---|---|
| **The window menu bar** (`QMainWindow`'s own, spanning the full width above the docks) | window-global commands: File, View, Schema, Database, Tools, Generation, Help | fixed |
| **The Editor menu bar** (a child `QMenuBar` in an anonymous container widget that *is* `centralWidget()`, **strictly above the central pane**, `CenterStage` below it) | **editing** commands: **History · Select · Parsing · Bookmarks** — **all four ship** (`Select` added by FQ-015, `9146524`) | **fixed** — the app decides its contents. It is *not* the user-curated favourites toolbar (§7) |

Both bars are walked by the **one** `ToolbarController` menu walk, so every command on either is
toolbar-pinnable and carries a menu-path id (§7). On **macOS** the window bar is absorbed into the system
menu bar while the child bar renders inline, so the two will not look like siblings there.

Final reconciled state of the **window menu bar** (after all overrides — the original top-level
"Diff/Merge" menu was folded into Tools; "New Project" removed; line-wrap moved to editor context menu).
The removed "New Project" was the 2026-07-15 **generation stub** (ledger §28); the **New Project…** listed
under File below is §18.2's later, distinct DDL-project action that merely reuses the same label:

- **File:** Open (Ctrl+O), ⎯, **the §18.2 project action group** (see below), ⎯,
  Save (Ctrl+S), Save As (Ctrl+Shift+S), Revert, Close (Ctrl+W), ⎯, **Show Launcher…**, Exit. Real build
  order in `MainWindow._build_file_menu`: `Open…` · separator · **`Open PHP File…`** (§21 — no structural
  tie to a `.pgtp`, opens with or without a project) · separator · the five project actions · separator ·
  Save / Save As / Revert / Close · separator · `Show Launcher…` · Exit.
  **`Open Recent` is DELETED** (FQ-010, 2026-08-07 — ledger §28: a documented capability withdrawn,
  together with the `recentFiles` store; §7). **`Show Launcher…`** re-opens FQ-010's launcher with
  `force=True`, which is what keeps the persisted "Don't show this again" reversible.
  - **§18.2 project actions** (revised 2026-08-03 — renamed from "New/Open/Close DDL Project" and
    expanded; **corrected 2026-08-06**: these five live on the **File** menu, in their own
    separator-delimited group between `Open…` and `Save`, *not* on the Database menu — §24):
    **New Project…** (folder picker; optionally offers local-sandbox setup — a Postgres connection plus
    a Test button that specifically verifies superuser, reusing §18.5 D2's capability probe, plus a
    "with data"/"without data" provisioning choice (§18.5 D2a) — and optionally offers git configuration,
    explicit TBD placeholder only), **Open Project…** (runs the `.pgtp`-checksum **and** DDL drift
    comparisons, both surfaced, neither auto-resolved), **Close Project** (a reminder point for pending
    `.pgtp`/DDL deploys, §18.3 — never a forced action), **Project Settings…** (new dialog exposing the
    full project JSON — identity, `.pgtp` link, both connection profiles including password, deploy
    manifest), and **Deploy .pgtp** (on-demand push of the local `.pgtp` working copy back to the
    sshfs-mounted source; also offered as a close-time convenience prompt, §18.3).
- **Edit: THE MENU NO LONGER EXISTS** (FQ-016, 2026-08-07 — ledger §28). It was dissolved, not emptied:
  `Undo`/`Redo`/`History…` → the Editor bar's **History**; `Cut`/`Copy`/`Paste`/`Delete` and
  `Preferences...` → **deleted stubs**; the five Find/Replace entries → the permanently visible
  `FindReplaceBar` (§8/§15/§27); `Select Enclosing Block`/`Select Parent Block` → the Editor bar's
  **Select**, where FQ-015 (`9146524`) **rebuilt** them with trigger-time dispatch — they were *deleted*
  with the menu, leaving `Ctrl+Shift+A` hostless for one commit (§7, ledger §28); `Auto Parse XML` → the
  Editor bar's **Parsing**.
- **View** (real order and labels): ☑ Project Tree, ☑ Properties Panel,
  ☑ Audit/Problems Panel, ☑ Raw XML Panel (checked by default), — , Expand All, Collapse All, — ,
  ☐ Light Theme, — , Customize Toolbar… (opens the toolbar customization dialog, §7). The three **dock**
  checkboxes (Project Tree / Properties Panel / Audit/Problems Panel) are bidirectional — closing a dock
  by its title-bar ✕ unchecks the menu item (BUG-007, §7). **The former ☐ "Find table reference" checkable
  is gone** (FQ-003, 2026-08-06) — table references are a sub-branch of the Database ▸ Database/XML
  Coherence view (§17), not an independently toggleable panel.
- **Bookmarks: moved off this bar** onto the Editor menu bar (FQ-016, 2026-08-07) — see the Editor-menu-bar
  inventory below. It was previously a top-level window menu between Tools and Generation.
- **Schema:** Edit XSD, Edit AutoXSD, Verify XSD, Export XSD, Import XSD — five items (§11). Verify /
  Export / Import act on the **active XSD** (curated or learned, per `_xsd_mode`), not curated-only.
  (Go To XSD is **not** a menu item: it is a window-level Ctrl+L `QAction` added via
  `MainWindow.addAction` plus a Raw XML editor context-menu entry; it always forces curated mode.)
- **Database:** Connection Setup… (**projectless-mode only** — disabled while a §18.2 project is open,
  since the project's own `target`/`sandbox` connections in Project Settings… are authoritative then;
  BUG-024, 2026-08-05), ⎯, ☐ **Database/XML Coherence** (checkable toggle revealing the merged
  left-dock coherence view, §17 — **one** entry replacing the former *Check: XML→Database* and
  *Check: Database→XML* items **and** the View menu's *Find table reference*; deliberately **no
  shortcut**; toolbar-customizable for free via §7's menu-path id derivation. Final wording is an
  implementation detail, FQ-003), ⎯, ☐ DDL Explorer
  (checkable toggle, §18.1; kept in lockstep with the center tab's ✕), ⎯, **New Function/Procedure…**
  (FQ-002, 2026-08-06, **implemented** — opens the one Add Function/Procedure dialog whose *Kind* field
  chooses function vs. procedure, then opens the §18.5 editor tab on a generated skeleton; the trigger
  counterpart is deliberately **not** here, since a trigger is scoped to a table and is reached by
  right-clicking that table's node in the DDL Explorer tree — §18.1. Requires a configured connection, like
  the other Database-menu entries; deliberately **no shortcut**, and toolbar-customizable for free as
  `database.new-function-procedure` via §7's menu-path id derivation), **Project Status…** (§18.8,
  **implemented** — opens the non-modal, single-instance node diagram and re-probes on every invocation;
  no shortcut). Everything §18 adds lives in **this** menu (except §18.2's five project actions, which
  are on **File** — see below); no new top-level menu is created for it, and no "locate binary" action
  is added, because v1 spawns no external process. **The remaining entries below are target design
  (2026-08-02) and none of them exists in `_build_database_menu` today:**
  - **Once a project has a sandbox configured (§18.5 D2/D2a), the DDL Explorer toggle above gains a
    sandbox-scoped sibling** (§18.7, settled 2026-08-05): a second checkable entry opening a separate DDL
    Explorer instance against the sandbox connection, absent entirely when no sandbox exists (no dead
    controls, mirroring §18.5 carve-out 2's posture). Exact wording/placement of the second entry is an
    implementation detail, not pinned here.
  - ⎯ then (§18.5) **Sandbox Setup…** (the `role=sandbox` profile in the same `ConnectionSetupDialog`,
    plus the capability-probe result, the one-click **Install plpgsql_check** button *inside* that dialog
    next to the probe result, the working-set list and **Reset Sandbox**, and — when the configured
    database is not app-owned — the refusal together with the mandatory **"Create a sandbox database for
    me"** offer — the **Install plpgsql_check** button here is the *primary* home of the single install
    action §18.8's Sandbox2 window is the second entry point to, §18.5 D2); **Check DDL Object** (runs
    the validation ladder against the active DDL object editor tab, D3a) and **Check without applying**
    (the same ladder inside an explicitly rolled-back transaction); **Apply to Sandbox**;
    **Apply to Target Database…** (the ellipsis marks the confirmation naming
    object + database, and it is additionally gated on a green sandbox validation and refused outright on
    a changed signature — §18.5); **Generate Deployment SQL…** (the feature's rank-1 deliverable;
    disabled unless a sandbox profile is configured); and **Deploy this edit…** (§18.5, settled
    2026-08-05 — opens the same 3-way destination picker as the DDL object editor tab's own context-menu
    action of the same name, reusing Apply to Sandbox / Save / Apply to Target Database…'s existing
    wiring rather than a fourth gesture; deliberately **no shortcut**); and ☐ **Sandbox SQL Console**
    (§18.5 D4, settled 2026-08-06 — a **checkable toggle** revealing the single dynamic center tab, kept
    in lockstep with that tab's ✕, exactly like the DDL Explorer toggle. Following §18.7's precedent the
    entry is **absent, not disabled, until the active project has a sandbox** — it is created when the
    sandbox lane comes up and removed when the project closes — and there is **no target-database
    counterpart of it, not even a disabled one**, per D4's safety boundary. Toolbar-customizable for free
    as `database.sandbox-sql-console` via §7's menu-path id derivation). **Check DDL Object / Check
    without applying / Apply to
    Sandbox / Apply to Target Database… / Deploy this edit…** are **disabled unless a DDL object editor
    tab is active**, kept in sync on `center_stage.currentChanged`; Apply is never automatic and never
    implied by Save. Sandbox Setup, Sandbox SQL Console and Generate Deployment SQL do **not** require an
    object tab (the console requires a live sandbox **session**, which is a different precondition). There is
    no "locate binary" action — v1 spawns no external process, **except** §18.5 D2a's optional
    `pg_dump`/`pg_restore` sandbox data-cloning path, a narrowly-scoped exception to that invariant (§18.5
    D2a). **None of these entries ships with the editable tab's first increment** — the sandbox lane is a
    later carve-out (§18.5, v1 scope), and the tab likewise ships with **no button row** rather than
    disabled controls.
  - **The §18.2 project actions (New Project… / Open Project… / Close Project / Project Settings… /
    Deploy .pgtp) are *not* on this menu** — they live on the **File** menu (above; corrected
    2026-08-06, §24). Everything else §18 adds does live here.
  - (§18.3) **Compare Schemas…** and **Save Schema Snapshot…** — **still absent**, even though the
    engine, the snapshot module and the diff viewer they would drive all ship (§18.3 status).

  ("Format Selection" is **not** a menu-bar item: it is a `Ctrl+Alt+F` action plus a context-menu entry
  scoped to the DDL object editor tab **and (§18.5 D4) the Sandbox SQL Console tab** — see §27. "Deploy
  this edit…" is likewise primarily a **context-menu item** on the object tab, mirrored onto this menu as
  described above. **"Run in Sandbox Console"** — §18.5 D4's one bridge from the object tab, which
  **copies the selection into the console and focuses it without executing** — is a context-menu item
  only, on that tab, with no menu-bar entry and no shortcut: it is a navigation gesture, not a second
  execution path.)
- **Tools:** Manage Captions…, Reparse Raw XML into Tree, Compare/Merge Two Files…, Next/Previous
  Difference, Apply Changes to Target, Lint Current File, ☐ Lint on Save, Locate PHP Linter… (§22 — these
  three **do** exist in `_build_tools_menu` as of 2026-08-07; §22's "the Tools-menu wiring is the remaining
  gap" status note is stale), ☐ Start MCP Server (§23 — checkable, unchecked at startup; unchecking is the
  stop gesture).
  **`Caption Filter…` is DELETED** with the caption modal (FQ-017, 2026-08-07 — ledger §28; §13).
  **`Validate Project` MOVED to the Editor bar's `Parsing`** (FQ-016, shipped — it is the owner's *"validate
  xml"*; its `LEGACY_ID_ALIASES` entry was updated in the same commit to `parsing.validate-project`, §7).
  **All three lint entries STAYED here** (FQ-016 decision, closing that §29 open item): moving only
  `Lint Current File` would have split lint across two bars, which is the exact complaint the Editor bar
  exists to fix.
- **Generation:** Locate PHP Generator Executable…, Generate PHP…, Open Output Folder, panGen (Generate
  Own PHP), rePHPgen (Analyze Gap), Save reJSON…, Locate panGen Runtime….
- **Help:** Manual (F1), Open Log Folder, About. **`Manual` (F1) must never be filtered out of any launch
  mode** (§7) — otherwise the app can hide the only documentation explaining why commands are missing.

### The Editor menu bar (FQ-016, 2026-08-07)

Strictly above the central pane, holding **editing** commands (the deliberate concept name —
`History…` is project-global, so calling the bar "per-tab" would be false; §7). **FOUR menus ship**
(History · **Select** · Parsing · Bookmarks, built in that order by
`MainWindow._build_editor_menu_bar`) — `Select` landed with FQ-015 (`9146524`), which also consumed the
commented insertion point that used to mark its place. **`List All Bookmarks`** (FQ-014)
**ships** as the Bookmarks menu's fifth entry. **The whole bar is hidden on the Caption Management and Manual tabs**
(`_refresh_editor_menu_affordances`, on `center_stage.currentChanged`) — the bar *widget*, never its
actions, so no pinned toolbar button blinks out; this closes §29's open item on those two tabs in the
direction it recommended. That same refresh now also hides **one action**, `Select ▸ Select Parent Block`
(below) — the seam's first capability gate.

- **History:** History… (no shortcut — opens the non-modal history-jump navigator, §7), Undo (Ctrl+Z),
  Redo (Ctrl+Y), **in that order** (owner: *"everyone uses Ctrl+Z/Ctrl+Y anyway"*). Ids become
  `history.undo` / `history.redo`, both `LEGACY_ID_ALIASES`-pinned and therefore **updated in the same
  commit** (§7). `Ctrl+Z`/`Ctrl+Y` keep §27's pinned carve-out routing them to the Edit XSD / DDL object
  tab's own native undo stack.
- **Select — SHIPPED** (FQ-015, `9146524`, `_build_select_menu`, **between History and Parsing**):
  Select All (Ctrl+A — new entry for existing behaviour), separator, Select Enclosing Block (Ctrl+Shift+B),
  Select Parent Block (Ctrl+Shift+A). **All three resolve the active editor at *trigger* time** via
  `FindValidateController.active_selection_editor()` (which delegates to `active_bookmark_editor()`), fixing
  the long-standing build-time binding bug in the two block commands (§8). `Select Enclosing Block`
  dispatches **by capability** — `XmlEditor.select_enclosing_block` (XML element) on Raw XML / Edit XSD /
  draft tabs, `CodeEditor.select_enclosing_brackets` (innermost balanced `()[]{}`) on DDL Explorer / DDL
  object / PHP tabs. `Select Parent Block` is **XML-only and HIDDEN — never greyed — on `CodeEditor` tabs**
  by `_refresh_editor_menu_affordances`, which kills Ctrl+Shift+A there too. New pinnable ids:
  `select.select-all` / `select.select-enclosing-block` / `select.select-parent-block` (§7).
- **Parsing:** ☐ Auto Parse XML (§9; unchecked by default, in-memory only), separator, **Validate Project**
  (moved from Tools — the owner's *"validate xml"*). **`Lint Current File` stayed on Tools** with its two
  siblings (§29's open item, closed that way: moving only the first of the three would split lint across two
  bars). **Neither member is gated today, deliberately** — see §7: `Validate Project` is a *default* toolbar
  button, and a toolbar button is the menu's own QAction, so per-tab `setVisible` gating would make a
  default button appear and disappear as tabs change. The `setVisible`-by-**active tab kind** seam (never
  create/destroy, never enabled-state, §7) **has since found its first genuine *capability* gate — in
  `Select`, not here**: `Select ▸ Select Parent Block` is hidden on `CodeEditor` tabs (FQ-015, above).
  **The plpgsql-check member does not exist yet:** §18.5
  D3a's `Check DDL Object` / `Check without applying` are target design and are currently assigned to the
  **Database** menu (above); they land with `db/ddl_check.py`, and their *"a DDL object editor tab is
  active"* predicate would be this menu's first gated member (no longer the *seam's* first user — FQ-015
  took that). **Open owner call (§29):** whether those two Check
  gestures move here (the recorded recommendation — they are per-tab and this is the per-tab bar — with
  **no Database-menu twins**, which would override §26's placement above and need a ledger row) or stay on
  Database.
- **Bookmarks:** Toggle Bookmark (Ctrl+F2), Next Bookmark (F2), Previous Bookmark (Shift+F2), separator,
  Clear All Bookmarks, **List All Bookmarks** — five actions, hosted here by
  `FindValidateController.build_bookmarks_menu(bar)`, which now takes the bar to build on.
  **`List All Bookmarks` ships** (FQ-014, 2026-08-07; **no shortcut** — it writes clickable `[Bookmark]`
  rows into the Audit dock for the **active** editor only and reveals the dock, §7/§8).
  **Every action follows the active editor tab** (§8):
  the target is resolved at trigger time by `FindValidateController.active_bookmark_editor()` — Edit XSD
  tab → `stage.xsd_editor`, DDL Explorer tab → `stage.ddl_editor_panel.editor`, an active DDL object
  editor tab → `panel.editor`, an active PHP file tab → `php_tab.editor`, an active draft fragment tab →
  `draft.editor`, any other tab → `stage.xml_editor` — and the menu never switches/reveals a tab. Target
  design (2026-08-01, not yet implemented, §8/§13): the whole menu and its actions are disabled together
  while Caption Mode is active (gutter bookmark toggling stays usable).

**Settled (was §29's open item):** on the **Caption Management** and **Manual** tabs the Editor menu bar
shows **nothing — the whole bar widget is hidden** (`_refresh_editor_menu_affordances`), which is exactly
the recorded recommendation and what the visibility refresh gives for free. Hiding the *widget* rather than
its actions is deliberate: a pinned toolbar button is the menu's own QAction and would otherwise vanish with
it. **The one place an *action* is hidden instead is `Select ▸ Select Parent Block`** (FQ-015), where the
absent-not-greyed rule outweighs a pinned button coming and going — the only accepted instance of that
trade-off on this bar.

> **Concurrent-work collision, recorded not resolved:** a separate queued proposal (FQ-012, a *Customize
> Shortcuts…* dialog under **View**, beside *Customize Toolbar…*) would add a View-menu entry here and
> would recast §27's table as rebindable defaults. It is **not folded into this spec** and overlaps this
> section and §27 directly; whoever picks it up must reconcile it against the FQ-016 rulings below (in
> particular, `F3` is a bare window-level shortcut with **no menu entry**, so it falls outside
> `collect_menu_commands()`'s enumeration and into that proposal's reserved-rows carve-out, exactly like
> `Ctrl+L`).

Toolbar default since FQ-016: **six** buttons — Open, Save, Undo, Redo, Validate, Generate (customizable).
**`Find` is gone from the default set**: it has no menu home (the bar is permanent), so its alias, its
`LEGACY_COMMANDS` row and its default-icon binding were all retired; `edit-find.svg` stays user-assignable
from the Breeze catalog. `Undo`/`Redo`/`Validate` now resolve to `history.undo` / `history.redo` /
`parsing.validate-project` — see §7's alias table.

---

## 27. Consolidated keyboard shortcuts

| Shortcut | Action | Context |
|---|---|---|
| Ctrl+O / Ctrl+S / Ctrl+Shift+S / Ctrl+W | Open / Save / Save As / Close | Window. **Save** routes to the active center-stage tab: Raw XML, Edit XSD, or (**implemented**, §18.5) the active DDL object editor tab, where Save persists text only and **never** executes DDL (§7); on that tab the **first** Ctrl+S opens **Save As… (`*.sql`)** and remembers the path, and cancelling that dialog from the close-confirmation prompt **aborts the close**. **Ctrl+Shift+S stays project-only** (`_save_project_as`) and deliberately does **not** re-route to the object tab (§18.5) |
| Ctrl+Z / Ctrl+Y | Undo / Redo (single step) | Window — project snapshot history (`MainWindow._undo`). **Exception, pinned (implemented, §18.5 carve-out 1):** with the Edit XSD tab or a **DDL object editor tab** active, Ctrl+Z/Ctrl+Y drive **that editor's own native undo stack**. The object tab realizes it with an **event filter** on its editor that accepts the key and calls `editor.undo()`/`redo()` itself, because `CodeEditor` neither consumes nor re-emits the key and the window shortcut would otherwise revert the **Raw XML project buffer** |
| Ctrl+F / Ctrl+R | **FOCUS** the owning tab's Find field / Replace field (FQ-016, 2026-08-07 — they no longer *show* a bar; the bar is permanently visible, §8/§15) | **Per tab, NOT window-level:** each of the six `FindReplaceBar` hosts installs its own pair of `WidgetWithChildrenShortcut` `QShortcut`s via `find_replace_bar.install_focus_shortcuts(host, bar)` — Raw XML tab, Edit XSD tab, DDL Explorer (`ddl_editor_panel`), the DDL object editor tab, a PHP file tab, a draft fragment tab — and `CaptionManagementPanel` owns an equivalent panel-scoped pair of its own (§13/FQ-017). **A window-level `Ctrl+F` is forbidden**: it would be *ambiguous* against those panel-scoped ones and Qt would fire **neither** (§7). Consequences: exactly one match is live for any focus location; **`Ctrl+F` is a NO-OP on tabs with no bar** (Manual, Diff/Merge) instead of yanking the user to Raw XML — which **closes** §29's reveal question in the recommended direction — and `FindValidateController.active_find_bar()`'s reveal fallback now serves **`F3` only**. Replace is **inert in the DDL Explorer** — that buffer is read-only (`CodeEditor.replace_current_selection` returns early on `isReadOnly()`) — and **live** in the DDL object editor, PHP and draft tabs. **No menu entry advertises either key any more** (the Edit menu is dissolved) and neither key is mode-gated, so the long-standing "the menu advertises one behaviour while the key does another" conflict disappears from both ends, and `set_find_actions`/`set_find_actions_enabled` are deleted (§7) |
| **F3** | **Find Next** — routed to `active_find_bar().find_next()` | **Window-level shortcut with NO menu entry** (FQ-016, 2026-08-07). Owner ruling: *"why does F3 die? it should find next."* It survives the Edit menu's dissolution rebound onto the same window-level, menu-less shape as **Ctrl+L Go To XSD** (next block), using the exact dispatch the deleted Edit QAction used. **Window-level, NOT bar-local:** the whole point is that it works while the caret is in the **editor**, so it must not be a `keyPressEvent` on `FindReplaceBar`, which would only fire once the bar already has focus. Consequence, accepted: a shortcut with no menu entry is **invisible to `_walk_menu_actions`** and therefore **can never be pinned** to the toolbar — it joins the existing `Ctrl+L` / `Ctrl+Alt+F` / `Ctrl+Return` category, alongside Find itself (*"Find unpinnable is fine"*) |
| *(deleted)* | ~~Find All (Ctrl+Shift+F)~~ · ~~Replace All (Ctrl+Alt+Return)~~ | **Both chords are GONE** (FQ-016, 2026-08-07; ledger §28) — the commands survive as **buttons on the now-permanent bar**. Find All writes `[Find]` rows into the Audit panel: a deliberate, occasional act with a visible button earns little from a chord. Replace All is a **bulk edit that now sits beside a scope dropdown** (FQ-017's *"in filtered results"* / *"in all project"*, §13) which a keystroke would bypass entirely — losing the keystroke is a gain under this project's own rule that a broad, hard-to-inspect effect must not be one chord away |
| **Ctrl+A** | **Select All** | **Editor menu bar ▸ Select** (**SHIPPED**, FQ-015 `9146524`, §8/§26). Acts on `active_selection_editor().selectAll()`, resolved at **trigger** time. The chord is **not new to the app** — `QPlainTextEdit`'s built-in select-all was always live and nothing bound or stole it; the menu entry is the feature. Qt's `ShortcutOverride` means a **focused** text widget still handles the key itself, so this QAction's shortcut fires only when focus is elsewhere (e.g. the structure tree) — which is also why it cannot steal Ctrl+A from a `QLineEdit`. **Live in read-only editors** (DDL Explorer, Raw XML in Caption Mode): `setReadOnly(True)` keeps Qt's selectable-text flag, and **deliberately not gated in Caption Mode** — selecting mutates nothing. This is exactly what the FQ-015 fix to `XmlEditor._is_text_modifying_key` protects (§8): a Ctrl chord is a command, so a read-only editor no longer swallows the key to flash its hint |
| **Ctrl+Shift+B / Ctrl+Shift+A** | **Select Enclosing Block / Select Parent Block** | **Editor menu bar ▸ Select** (**SHIPPED**, FQ-015 `9146524`, §8/§26) — re-homed off the dissolved Edit menu and **rebuilt**, with **trigger-time dispatch** replacing the old build-time binding to the Raw XML editor (which made both chords act on the wrong document from any other tab). **Ctrl+Shift+B is per editor family:** XML element on Raw XML / Edit XSD / draft tabs, innermost balanced `()[]{}` on DDL Explorer / DDL object / PHP tabs. **Ctrl+Shift+A is XML-only and DEAD on `CodeEditor` tabs** — its action is hidden there (§7's capability gate), and Qt keeps a shortcut live only while its action is visible **and** enabled. Historical note (ledger §28): between `c327c9d` and `9146524` **Ctrl+Shift+A had no host at all** and Ctrl+Shift+B survived only through `CodeEditor.keyPressEvent` |
| Ctrl+click / Alt+click | Jump to matching tag / parent tag | Raw XML editor |
| Ctrl+F2 / F2 / Shift+F2 | Toggle / Next / Previous Bookmark | The **active editor tab** — Raw XML / Edit XSD / DDL Explorer / the DDL object editor tab / a PHP file tab / a draft fragment tab — resolved at trigger time by `FindValidateController.active_bookmark_editor()`, never switching tabs (Bookmarks menu, now on the **Editor menu bar**, §8/§26; disabled in Caption Mode, §13 — target design 2026-08-01). **`Clear All Bookmarks` and `List All Bookmarks` deliberately carry no shortcut** — the latter (FQ-014) is **not built yet** |
| double-click (line-number gutter zone) | Toggle bookmark on that line | Raw XML editor gutter (settled 2026-08-01, **implemented** — commit `828fe02`, §8 — additive alongside the existing single-click 12px bookmark strip; NOT gated by Caption Mode) |
| Ctrl+L | Go To XSD (jump to the attribute's definition in curated.xsd; always forces curated mode) | Window-level QAction (also in the Raw XML editor context menu). **The shape `F3` copies** (above): a window-level command with **no menu entry**, therefore outside `_walk_menu_actions` and un-pinnable — the category also holding `Ctrl+Alt+F` Format Selection and `Ctrl+Return` Run |
| Ctrl+Space | Completion popup (`_CompletionPopup`, frameless, non-modal) | Three shipped contexts: the **Raw XML editor**'s schema-driven attribute/value completion (§11), the **DDL object editor tab**'s schema-aware SQL completion (§18.6), and the **Sandbox SQL Console tab** (per the manual's Keyboard Shortcuts chapter, which lists all three; §18.5 D4) |
| Ctrl+Alt+F | **Format Selection** (§18.4's `format_selection` on the current selection; single undo step on success, `[SQL]` Audit lines + transient underline on refusal) | The DDL object editor tab (**implemented**, §18.5) and — target design, §18.5 D4 — the **Sandbox SQL Console** tab; in both cases only with a non-empty selection, and also a context-menu item. The formatter itself is unchanged: its host set widens from one tab to two. *(The old note that "`Ctrl+Shift+F` stays Find All" no longer applies — that chord is deleted, see above.)* |
| Ctrl+Return | **Run** — execute the selection, or the whole buffer when there is no selection, against the **sandbox** (§18.5 D4, target design 2026-08-06) | **Sandbox SQL Console tab only.** This is the one execution gesture that *does* carry a shortcut, and it does not reopen the *"an irreversible outward effect must not be one keystroke away"* rule — that rule is about **irreversibility**, and the sandbox is disposable and `reset()`-able by construction, which is the same asymmetry that authorizes ad-hoc execution at all (D4's safety boundary). Object-changing statements still pass the injected confirmation; there is **no target-database Run**, with or without a shortcut |
| *(no shortcut, deliberately)* | **Check DDL Object** / **Check without applying** / **Apply to Sandbox** / **Apply to Target Database…** / **Generate Deployment SQL…** / **Deploy this edit…** | Database menu, the DDL object editor tab's context menu, and (for the three check/apply gestures) its button row (§18.5. **Status 2026-08-06:** the tab's own **Apply to Sandbox / Apply to Target… / Deploy this edit…** ship, with the button row appearing only when the corresponding seam is wired; the **Check** gestures wait on `db/ddl_check.py` (D3a), and none of the Database-menu twins exists yet). Apply is an **irreversible outward effect** and must not be one keystroke away; the target-database variant additionally requires a green sandbox validation, refuses a changed signature outright, and confirms naming the object **and** the database. **Deploy this edit…** (§18.5, settled 2026-08-05) is a picker in front of these same three destinations (Apply to Sandbox / Save / Apply to Target Database…) and reuses their existing wiring rather than adding a fourth gesture — likewise deliberately unshortcut. |
| *(no shortcut, deliberately)* | **Add Trigger…** / **New Function/Procedure…** | DDL Explorer tree context menus (table node / "Functions & Procedures" root) and, for the routine one, **Database ▸ New Function/Procedure…** (§18.1, FQ-002 — **implemented** 2026-08-06: `db/ddl_skeleton.py`, both dialogs, both context entries and the menu action). Both are dialog-gated and write **nothing** to a database — they only open a §18.5 editor tab on generated skeleton text — so the reason for withholding a shortcut is menu-hygiene, not the irreversible-outward-effect rule above. |
| *(no shortcut, deliberately)* | **Database/XML Coherence** (checkable) | Database menu (§17/§26, FQ-003, **implemented** 2026-08-06). It replaces three previously unshortcut entry points — Check: XML→Database, Check: Database→XML and View ▸ Find table reference — none of which carried a shortcut either, so nothing is lost; the merged view is read-only and reached by toggle, not by keystroke |
| Escape | **Return focus to the document** — never hide anything | Any editor's `FindReplaceBar` returns focus to its editor; the Caption Management tab's `CaptionFindReplaceBar` returns focus to the grid (FQ-016/FQ-017, 2026-08-07). Both bars used to *hide* on Escape; both are now permanent |
| Ctrl+G | Go to line in XML | Caption grid |
| Ctrl+Shift+B | Bracket-select, handled by **`CodeEditor.keyPressEvent` itself** | Code editor dialog (its **only** host — that dialog has no menu bar); also present on every `CodeEditor` tab, where it is **shadowed** by the Select menu's QAction: Qt's shortcut map consumes the chord before the focused widget, so exactly **one** call occurs (measured, FQ-015). Kept deliberately: it is the menu-less dialog's only path and the reliable one under the offscreen test platform, both paths now land on the same editor, and `select_enclosing_brackets` is idempotent |
| Ctrl+S / Ctrl+W | Save / Cancel | Code editor dialog |
| F1 | Manual | Window |

**§18.5 introduces exactly two new bindings** — `Ctrl+Alt+F` (which §18.4 had left TBD, shipped) and, as
of D4, `Ctrl+Return` scoped to the Sandbox SQL Console tab. Everything else it
needs joins the **existing** per-tab dispatchers rather than adding shortcuts: `active_find_bar()`,
`active_bookmark_editor()` and `_save_active_tab()` each gain one branch.

**Every binding in this table is FIXED** — set inline as a literal string at each action's construction
site, with no central registry and no user-facing rebinding. A separate queued proposal (FQ-012, a
*Customize Shortcuts…* dialog) would overturn that; it is **not folded into this spec**, and it overlaps
this table and §26's View menu directly. Note for whoever reconciles it: `F3`, `Ctrl+L`, `Ctrl+Alt+F` and
`Ctrl+Return` are **not** menu actions, so they fall outside the menu-bar enumeration such a dialog would
be built on.

---

## 28. Supersession ledger

Chronological record of decisions where a later spec overrode an earlier one. **Only the later decision
is authoritative** (and is what appears in the body above).

| Date | Superseded | Replaced by |
|---|---|---|
| 2026-07-12 | Original §6.2 Move/Copy of Detail blocks | Raw XML structural block-select + OS clipboard (incl. folded blocks) — **feature dropped** |
| 2026-07-12 | Original §6.5 Client read-only page generation | Same (copy page in raw XML, set `*AbilityMode` by hand) — **feature dropped** |
| 2026-07-12 | Properties "Real Raw XML display" (model roadmap SP2) | Folded into the XML Editor foundation |
| 2026-07-12 | Properties: `highlight_error_line` as primary API | Generalized `navigate_to_line`; `highlight_error_line` reimplemented on it; `line_text`/`select_range_on_line` added |
| 2026-07-12 | Original §6.1 `moved` difference kind | Dropped — a relocation = one removed + one added (no project-wide Detail identity) |
| 2026-07-12 | `resolve_path` nullable return | `ResolutionError{segment_index, message}` (never bare `None`) |
| 2026-07-12 | Model layer "discards the lxml tree" | Tree + per-node `element` retained (enables byte-faithful write-back) |
| 2026-07-13 | Original §6.3 grouped-coherence caption audit | Flat line-anchored caption grid (coherence re-added later as the one-click "Unify") |
| 2026-07-14 | Caption mode hides Raw XML + 5-col Value-editable grid + inline filter row | Raw XML visible-but-read-only; 8-col grid with read-only Value + editable New Value; header filters + find/replace modal |
| 2026-07-15 | Original View-menu "Wrap Raw XML Lines" | Moved to the Raw XML editor's right-click context menu |
| 2026-07-15 | Original top-level "Diff / Merge" menu | Items moved into the Tools menu; top-level menu removed |
| 2026-07-15 | Original File-menu "New Project" | Removed |
| 2026-07-15 | Original View-menu Raw XML unchecked-by-default | Raw XML tab visible/checked by default |
| 2026-07-15 | Editor-owned `QShortcut`s for block select | Edit-menu actions own Ctrl+Shift+B / Ctrl+Shift+A (WindowShortcut) |
| 2026-07-15 | Structural-select caret-at-end | Caret-at-start (anchor end, position start) + `ensureCursorVisible` |
| 2026-07-15 | Annotate UI flat one-row-per-value table (2026-07-12 SP B) | Two-pane labeler + `kind` classification; hover hints; XSD annotations |
| 2026-07-15 | About box SuperNano credit | Removed; MDS/author credits, format v22.8 |
| 2026-07-15 | Edit-menu "Find & Replace…" (Ctrl+H) stub | Real Find/Replace actions (Ctrl+F/F3/Ctrl+Shift+F/Ctrl+R/Ctrl+Alt+Return) |
| 2026-07-13 | Synchronous Find All | Streaming chunked Find All with Stop + counts |
| 2026-07-19 | `_closing_tag_start` private in xml_editor | Promoted to public `closing_tag_start` in `xml_structure` |
| 2026-07-19 | re_phpgen `page_skeleton.php.tmpl`; two-template master/detail | Single `page_class.php.tmpl` + `file_frame.php.tmpl`, Python slot-computation |
| 2026-07-19 | Vendor CLI trusted as automation oracle (for the editor gap loop) | Manual GUI vendor baseline (CLI hangs on modal `EInvalidXML`) |
| 2026-07-20 | DB-check populate inline in `on_result`; Toolbar Available = registry-minus-present | `_populate_db_check` + cached-schema reparse refresh; Available = all commands, present ones disabled |
| 2026-07-20 | Multi-branch model (incl. re-phpgen branch) | Single-branch (`main`); re-phpgen folded in & branch deleted |
| 2026-07-21 | "Find Reused Tables" modal (`ReusedTablesWindow`) + `TableUsage.breadcrumbs` | Table References dock tab + `TableUsage.references: list[TableReference]`; modal deleted |
| 2026-07-23 | Two-pane Annotate Schema Values dialog (`annotate_schema_values_dialog.py`) + Schema ▸ "Annotate Schema Values…" (2026-07-15) | Annotate-at-cursor popover in the XML editor (Ctrl+L / value context menu) authoring `labels`/`kind`/`notes`/`enum_mode` + unlabeled-value dotted underlines + Next Unlabeled Value navigation; dialog and menu action deleted |
| 2026-07-23 | `known_values` = engine-observed values only | Union of engine-observed values and labeler-added label keys |
| 2026-07-24 | Annotate-at-cursor popover (`ui/annotate_popover.py`, Ctrl+L, context-menu "Annotate value…") (2026-07-23) | Direct hand-editing of `curated.xsd` in the Edit XSD tab; popover deleted; **Ctrl+L reassigned to Go To XSD** |
| 2026-07-24 | Unlabeled-value dotted underlines + Next Unlabeled Value (Ctrl+Shift+L) (2026-07-23) | Removed (curation happens in the XSD, not the document); Ctrl+Shift+L freed |
| 2026-07-24 | Labeler-owned model fields `labels`/`kind`/`notes`/`enum_mode` + bitflag derivation in `settings_index` | XSD dialect `label=`/`sums=`/`hint=` on `curated.xsd`; additive-value derivation reimplemented against `sums`; `kind`/`notes` concepts dropped |
| 2026-07-24 | Team schema-model sharing via git — `schema_learning/sync.py`, `schema_learning/merge.py`, `ui/team_sync_dialog.py`, `ui/merge_conflicts_dialog.py`, Schema ▸ Publish/Fetch/Merge/Team Sync Settings, `schema_sync/*` QSettings keys, `team_repo_dir`, the sum-based count-merge accepted-limitation | Schema ▸ **Export XSD / Import XSD** plain file exchange (verify-before-import, `curated.xsd.bak` backup) |
| 2026-07-24 | Read-only `SchemaViewerWindow` + Schema ▸ Open XSD / Open XSD Labels (JSON) (`ui/schema_viewer.py`, `ui/schema_viewer_data.py`) | Editable **Edit XSD** center-stage tab (second `XmlEditor` + own `FindReplaceBar`) |
| 2026-07-24 | "`schema.xsd` is a generated, read-only artifact — hand-edits do not persist"; per-user JSON model as local source of truth for completion | **Inverted:** `curated.xsd` is the official, hand-edited-only schema and sole completion/hover/Properties source; the generated-artifact role moves to `learned.xsd`; `schema_model.json` demoted to the engine's private state |
| 2026-07-24 | Endgame "freeze master → bundle XSD into the app" (learning-period close-out) | Superseded — the curated XSD is official from day one; no learning-period endgame exists |
| 2026-07-27 | Unbounded `sums` derivation — completion offers all 2^n − 1 combinations for any number of labeled atoms (2026-07-24) | Capped at `settings_index.SUMS_MAX_ATOMS = 16` labeled atoms: beyond that, derivation is skipped (explicit labels only, UI-freeze guard) and Verify flags the attribute |
| 2026-07-29 | §1 "Hard boundary" as a **permanent, no-exit** wall — `.pgtp`→`.php` compilation strictly one-way and vendor-owned, with no stated path for `re_phpgen` (§20) to ever become the tool of record | **Staged** boundary with named exit criteria: the wall holds exactly as before *today* (`re_phpgen` stays gap-analysis-only, invoked read-only as a subprocess; phpgen remains tool of record), but `re_phpgen`'s stated end goal is production replacement of the vendor generator, gated by three falsifiable promotion criteria (100% byte-parity across the 37-project corpus, verified determinism, the 8 parked edge pages resolved-or-accepted) formalized in new §20.4 "Production cutover" (target design, not yet reached); cutover is per-project and explicit via a future Generation-menu action, never silent/automatic; phpgen remains available indefinitely as fallback/reference oracle |
| 2026-07-29 | §17.1 DDL Explorer as `ui/ddl_explorer_panel.py::DdlExplorerPanel`, a tree grouped by kind only (Functions / Procedures / Triggers), with each leaf opening its own separate read-only source viewer (reusing `CodeEditor` per object) | Single synthesized DDL buffer (`db/ddl_buffer.py::build_ddl_text` + `DdlObjectSpan` index) hosted in one new `CodeEditor` tab under a new `language="sql"` mode, paired with a dual-grouped (Tables **and** Functions & Procedures) cross-referenced left-dock tree where triggers appear as two leaves pointing at the same span — reusing the Raw XML editor's `TagSpan`/`node_at_line` buffer-plus-span-index architecture (§8/§9) instead of per-object viewers |
| 2026-07-29 | §1 scope: PGTP Editor described purely as a `.pgtp`-editing tool (plus its vendor-generation and re_phpgen sub-projects), with no standalone/DB-only usage mode | Scope explicitly **broadened**: PGTP Editor also functions as a **standalone Postgres DDL-versioning tool**, usable with zero `.pgtp` files, sharing the app's DB connection/code editor/diff infrastructure as an independent mode (not a separate repo, unlike the `re_phpgen` precedent) — new top-level §18 |
| 2026-07-29 | §17.1 "Routines & triggers (DDL Explorer)" as a `§17.x` Database subsection, scoped to read-only browsing only, with phase-2 write-back sketched as inline `EditorPanel` DB push | **Relocated and reframed** as §18.1 "Routines & triggers browsing (DDL Explorer)" — a subsection of new top-level §18 "DDL versioning (standalone Postgres mode)" — now explicitly the shared browsing substrate for §18.2's checkout-to-edit and §18.3's deploy workflow, not a self-contained DB-menu feature; `RoutineInfo`/`TriggerInfo`/`DatabaseSchema.routines`/`.triggers` stay generic introspection in §17, reused by both the pre-existing DB-check features and the new §18 workflow |
| 2026-07-29 | §17.2 "Schema diff & migration" as a standalone `§17.x` Database subsection (schema-compare-only entry point: live-vs-live or live-vs-snapshot `DatabaseSchema` diff, "Compare Schemas…"/"Save Schema Snapshot…") | **Relocated** into §18.3 "Deploy workflow & schema diff/migration" as the shared diff/migration engine (`db/schema_diff.py`/`db/schema_snapshot.py`/`db/migration_gen.py`) now also invoked from §18.3's edit-driven deploy entry point (comparing local `ddl/` files against the last-deployed reference) — **one diff/generation engine, two entry points**. Whether the original schema-compare entry point should be fully absorbed into §18.3 or remain a sibling feature sharing only the diff core is an **explicit open question** (§29), not resolved by this relocation |
| 2026-07-29 | Both mechanisms left as explicit open questions pending owner sign-off (§18.2 "last-deployed reference" mechanism; §18.3 vs. original §17.2 schema-compare — absorb or sibling) | Settled, target design: **content-hash + commit-id git-tracked deploy manifest** (`.ddlproject/deployed.json`) as the last-deployed reference, hash-based drift comparison independent of git plumbing (§18.2); **separate `Compare Schemas…`/`Deploy` commands sharing one `db/schema_diff.py`/`db/migration_gen.py` engine**, unified screen explicitly rejected (§18.3) |
| 2026-07-30 | `curated.xsd` seeded on first run by **generating from the learned model** (2026-07-24) | Seeded by **copying the bundled `resources/curated.xsd` (Curated v1.2)**; learned-model generation is now the **fallback** used only when no bundled resource exists |
| 2026-07-30 | Single-purpose curated-only **Edit XSD** tab; **Schema menu = exactly these four** (Edit XSD, Verify, Export, Import); Verify/Export/Import curated-only (2026-07-24) | **Mode-aware** Edit XSD / Edit AutoXSD tab (`_xsd_mode ∈ {"curated","learned"}`, opens `learned.xsd` for analysis); Verify/Export/Import act on the **active XSD**; **Schema menu has five items** (Edit XSD, Edit AutoXSD, Verify, Export, Import) |
| 2026-08-01 | Edit XSD / Edit AutoXSD tab had **no close affordance at all** once revealed (only Raw XML/other-tab clicks or app close ended it; BUG-001) | **Closable** via tab-bar ✕ (`CenterStage.xsd_close_requested` → `MainWindow._on_xsd_close_requested`), reusing the existing `_confirm_close_xsd()` Save/Discard/Cancel prompt; hides via `hide_edit_xsd()` and falls back to Raw XML |
| 2026-08-01 | "Light Theme" **off** = restore the native/OS style+palette captured at startup (`_default_palette`/`_default_style_key`; `apply_theme(app, light, default_palette, default_style)`), with `_restore_theme` a no-op when `lightTheme` was False — dark only "worked" on the one native-dark platform (Windows) it was built on (BUG-004) | Symmetric explicit themes (commit 7ec792f): new pure `dark_palette()` mirroring `light_palette()`'s complete role coverage; `apply_theme(app, light: bool)` always sets Fusion + one of the two palettes; startup capture removed and `_restore_theme` applies the persisted theme unconditionally for both states; QSettings bool `"lightTheme"` unchanged |
| 2026-08-01 | §18.1 `RoutineInfo` carried argument **types only** (`arg_types: list[str]`), no argument names | `RoutineInfo` gains `args: list[tuple[str, str]]` (input argument **name+type pairs**, declared order, IN/INOUT only); the introspection query sources argument names; `arg_types` retained for `build_ddl_text`'s banner |
| 2026-08-01 | §18.1 BrowserPanel routine top-line = bare `name(argtypes)  [marker]` with a **binary** marker (`[F]` function / `[P]` procedure); no per-argument children | Top-line = **fully-qualified** `schema.name` with a **three-way** marker (`[P]` procedure / `[T]` trigger-function `return_type=="trigger"` / `[F]` other function); a routine **with** inputs lists each as a `name (type)` second-level child and carries **no** parens on the top line; a **zero-input** routine shows empty `()` on the top line and no children |
| 2026-08-01 | §18.1 BrowserPanel trigger leaf = `name  (timing/events) on table` (Tables branch) / `name  (timing/events) → function` (Functions branch) | Composite `schema.table.triggername` + bracketed **timing indicator** (`[B]`before / `[A]`after / `[I]`instead of) + **one bracketed event indicator per event** (`[I]`insert / `[U]`update / `[D]`delete / `[T]`truncate), e.g. `[B][D]`, in both branches |
| 2026-08-01 | §18.1 DDL `EditorPanel`/`CodeEditor` navigation **centered** (`CodeEditor.navigate_to_line` used `centerCursor()`) | DDL navigation **top-aligned** — the object's first line lands at the top of the viewport; DDL-editor-specific, `XmlEditor.navigate_to_line` stays **centered** (its Properties/tree-jump callers expect centering) |
| 2026-08-01 | §8 gutter / bookmarks / folding existed **only** on `XmlEditor`; DDL `EditorPanel`'s `CodeEditor` had none (no gutter/line-numbers/bookmarks/folding, Qt-mono default tab stop) | Generic gutter + bookmark + fold-**state** machinery **extracted into a shared base** — realized as the mixin `GutterBookmarkFoldMixin` in the new module `ui/editor_gutter.py` — with a **pluggable foldable-region provider**, used by **both** `XmlEditor` (XML-span provider) and the DDL editor (DDL-object provider over the `DdlObjectSpan` index); DDL editor also gains a **4-character tab stop** — one gutter implementation, never a parallel second |
| 2026-08-01 | §8 gutter + line bookmarks were **Raw-XML-only** — the "Edit code…" JS/PHP event-handler editor (`CodeEditorDialog`/`CodeEditor`) had no gutter, no line numbers and no bookmarks | The shared `GutterBookmarkFoldMixin` (`ui/editor_gutter.py`) sits on **`CodeEditor` itself**, so **every** code editor — including the JS/PHP event-handler dialogs — now shows the line-number gutter and supports line bookmarks (folding inert there: no regions installed). Surfaced as a side effect of the extraction and **explicitly kept by the project owner** rather than gated per language: line numbers in a code editor are conventional, and gating would add a second code path. Bookmarks stay **session-only, per-document**; the "Edit code…" `CodeEditorDialog` is a dialog rather than a center-stage tab, so the Bookmarks menu does not reach it (its gutter strip stays mouse-only) |
| 2026-08-01 | The Bookmarks menu/shortcuts remained bound to the **Raw XML editor only** (the row above, same date) | **Per-tab dispatch:** `_build_bookmarks_menu` captures no editor; each of the four actions resolves its target at **trigger** time via `main_window.py::_active_bookmark_editor()` — Edit XSD tab → `stage.xsd_editor`, DDL Explorer tab → `stage.ddl_editor_panel.editor`, any other tab → `stage.xml_editor` — mirroring `_active_find_bar` but **without** its `_reveal_raw_xml_tab()` side effect (toggling a bookmark must never switch tabs). The `CodeEditorDialog` remains out of the menu's reach |
| 2026-08-01 | §18.4 formatter reuses **`_SQL_KEYWORDS` imported from `pgtp_editor/ui/code_editor.py`** as its shared dialect source (settled design, same date) | **Relocated, not imported:** the set lives in the Qt-free core as `pgtp_editor/sql/keywords.py::SQL_KEYWORDS` (a `frozenset` of 115 lowercase members; added `elseif`, `elsif`, `exit`, `continue`, `foreach`, `reverse`, `intersect`, `while`) and `ui/code_editor.py` binds `_SQL_KEYWORDS = SQL_KEYWORDS` (same object, so `_highlighter._keywords is _SQL_KEYWORDS` still holds). Importing from `ui/` would have inverted §5's dependency rule (core must never import ui; `sql/` must stay Qt-free, now test-enforced by `tests/sql/test_package_purity.py`) — still exactly one shared source of truth for the highlighter's `language="sql"` mode and the formatter, just on the correct side of the arrow |
| 2026-08-01 | §18.4 module shape sketched in §5's tree as a single `sql/formatter.py` ("name TBD") with entry point `format_selection(text) -> FormatResult` and a `FormatResult` that "is either the reformatted text or a refusal" (settled design, same date) | **Five modules** as shipped — `sql/__init__.py` façade + `keywords.py`/`issues.py`/`tokenizer.py`/`formatter.py` — with `format_selection(text: str, *, indent_unit: str = "    ") -> FormatResult`, `FormatResult(ok, text, issues)` whose `text` on refusal is the input **verbatim** (an `ok`-ignoring caller cannot corrupt the selection), frozen `Issue(message, start, end, start_line, start_col, end_line, end_col, fatal=True)` with `.line == start_line` for `xsd_verify.Issue` parity, and a public `tokenize(text) -> list[Token]` on `sql/tokenizer.py` (the façade's `__all__` stays the four documented names) |
| 2026-08-01 | Dark theme = Fusion + `dark_palette()` **palette-only** (the BUG-004 fix above, same date) — Fusion+palette alone rendered checkable menu indicators outlined near-black on the dark menu background (BUG-010) | Dark = Fusion + `dark_palette()` **+ the QDarkStyleSheet dark QSS** (`qdarkstyle>=3.2`, new runtime dependency, MIT-credited in About); light **always** clears the stylesheet (`app.setStyleSheet("")`) so round-trips leave no stale QSS; the palette stays applied beneath the QSS for palette-reading custom widgets; side effect: `app.style().objectName()` is empty in dark mode (`QStyleSheetStyle` wrapping) |
| 2026-08-01 | §8 `XmlEditor` ran the O(document) structure rescan (`_rescan_structure`) and code-region rebuild (`_refresh_code_region_selections`) **synchronously on every `textChanged`** — i.e. a full `toPlainText()` copy + whole-document pass per keystroke — and `_update_matching_tag_highlight` **rescanned when it found `_spans` stale** on `cursorPositionChanged` (BUG-015) | Both rescans **debounced** behind a parented single-shot `self._rescan_timer = QTimer(self)`, `_RESCAN_DEBOUNCE_MS = 250`, scheduled by `_on_text_changed_schedule_rescan` (which absorbs the `_applying_theme` skip) and executed by `_rescan_now()` (structure → code regions → matching-tag highlight → gutter repaint); `_update_matching_tag_highlight` now **suppresses** the highlight when spans are stale instead of rescanning (a rescan there would run per keystroke via the caret and defeat the debounce; stale offsets would paint a wrong range anyway); two exact-structure carve-outs bypass the debounce — `setPlainText` calls `_rescan_now()` synchronously (document swap) and `_toggle_fold` calls `_flush_pending_rescan()` first, with the flush deliberately **not** in `_foldable_region_starting_at` (the gutter `paintEvent` calls it per visible block). Measured 216.1 → 2.0 ms per typed character on a 1 MB / 21,002-block document |
| 2026-08-01 | §8 `XmlSyntaxHighlighter` block state = **odd-`"`-parity per line** (`_has_unterminated_quote(text, start)`), never re-synchronising, so one parity-flipping `"` cascaded a Qt re-highlight to the **end of the document** on every such keystroke (5,972 `highlightBlock` calls / 45 ms on a 6,002-block file; BUG-016) | **Tag-aware four-state machine** — `STATE_NORMAL`/`STATE_IN_UNCLOSED_STRING`/`STATE_IN_TAG`/`STATE_IN_SINGLE_QUOTED` computed by the method `XmlSyntaxHighlighter._end_state(text, state)` over the state-changing characters matched by `_STATE_CHARS_RE = [<>"']` — where a quote only opens a value **inside a tag** (quotes in text content, i.e. PHP handler bodies, are inert), plus the **`<` resync rule**: a raw `<` inside a quoted value snaps the state back to `STATE_IN_TAG`, bounding the cascade to a block or two (trade-off: a raw `<` inside an attribute value ends that value's highlighting early — the document is invalid XML anyway and it self-corrects). `_has_unterminated_quote` deleted; continuation handled by `_continued_string_end(text, quote)`; helpers kept as **methods** so `debuglog.py`'s `("ui.xml_editor", "XmlSyntaxHighlighter.")` flood exclusion still covers them |
| 2026-08-01 | §7 a theme toggle re-applied formats via **one synchronous whole-document `rehighlight()`** inside `XmlEditor.apply_theme_colors`'s `_applying_theme` guard — which blocked the UI ~1.5 s+ on a multi-MB document (BUG-013) | **Two-stage, guarded per batch:** `apply_theme_colors` swaps colors and schedules `_rehighlight_for_theme` (coalesced via `_theme_rehighlight_pending` + the parented single-shot `_theme_kickoff_timer`), which rehighlights the **visible region** first, then a parented 0 ms `_theme_sweep_timer` drives `_theme_sweep_tick` over the rest of the document at `_THEME_SWEEP_BLOCKS_PER_TICK = 400` blocks per event-loop turn; the `_applying_theme` guard wraps **every** batch, so `is_applying_theme()` still keeps both dirty handlers and the editor's own rescan bookkeeping quiet |
| 2026-08-01 | §7/§15 Ctrl+F & the Edit-menu Find/Replace actions routed to **Raw XML or Edit XSD only** — with the DDL Explorer tab active they fell through to the default branch, which *revealed the Raw XML tab* and used its bar | `_active_find_bar()` gains a **DDL Explorer branch** returning `stage.ddl_editor_panel.find_replace_bar`, so Ctrl+F on the DDL tab searches the DDL buffer in place. **Ctrl+S stays asymmetric on purpose:** `_save_active_tab()` still branches only Edit-XSD-vs-project, because the DDL buffer is read-only and has no save path |
| 2026-08-02 | §18.2 checked-out object file path = flat **`ddl/<schema>.<name>.sql`** for every object kind (2026-07-29) | **Disambiguate-only-when-needed** scheme: a routine that is the sole holder of its `schema.name` keeps `ddl/<schema>.<name>.sql`; an **overloaded** routine appends its argument types (`ddl/public.fmt(integer).sql`); a **trigger** is always table-qualified (`ddl/<schema>.<table>.<trigger>.sql`). The flat scheme collided — Postgres allows function overloads sharing `schema.name`, and trigger names are unique only per table. Accepted trade-off: the first overload's file must be **renamed** (deliberately, `git mv`) when a second overload appears. Path computation, the overload decision and filename sanitization live in the new pure Qt-free `db/ddl_project.py`. *(The overload half of this row was itself superseded later the same day by the `_1` numeric-suffix scheme — see the row below; the trigger half stands.)* |
| 2026-08-02 | §18.2 "Checkout-to-edit" as a **single paragraph** — right-click in `BrowserPanel`/`EditorPanel` opens "a new, single-object editable tab", with no design for how a project comes to exist, what the tab is, how it is titled/closed/saved, or how `CenterStage` hosts a runtime-created tab (2026-07-29) | Full editable-tab design (target design): two right-click entry points with named widget idioms; a **"DDL project required"** Create…/Open…/Cancel dialog plus three Database-menu project actions; checkout semantics (seed-from-live when the file is absent, open-from-disk when present, **never silently overwrite local from the DB**, drift surfaced but **never blocking edit**); `ui/ddl_object_editor.py::DdlObjectEditorPanel`, one tab per object, re-Edit **focuses** the existing tab, short-identity title + dirty marker, tooltip, MainWindow-owned close confirm (the Edit-XSD pattern), **deliberately no `.bak`** (git is the history — an intentional divergence from §19); `CenterStage` gains **dynamic tabs appended after the fixed set** and addressed by a **key→widget map**, never a remembered index. *(Later the same day: the tab material was relocated from §18.2 to §18.5 and the project-required dialog re-scoped to project actions only — see the de-duplication and scoping rows below.)* |
| 2026-08-02 | §18.4's trigger binding **TBD**, its host surface undesigned, and its Audit-panel prefix unchosen — "§26/§27 gain no entry" (2026-08-01) | **Settled: `Ctrl+Alt+F`** (plus a **"Format Selection"** context-menu item), scoped to the DDL object editor tab and enabled only with a selection; `Ctrl+Shift+F` stays **Find All**. Refusals report to the Audit panel under the **`[SQL]`** prefix with a **transient underline** over the `Issue`'s exact span; success replaces the selection as a **single undo step**. §26/§27 now carry the binding. Still unimplemented — the host tab does not exist yet |
| 2026-08-02 | §18.1's "explicitly phase 2" write-back sketch: the editable DDL surface = the **multi-object `EditorPanel` buffer made editable in place**, pushing `CREATE OR REPLACE FUNCTION …` straight to the live DB with the diff detected per `DdlObjectSpan` | The editable surface is a **separate single-object tab type** (`ui/ddl_object_editor.py::DdlObjectEditorPanel`, right-click ▸ Edit… from `BrowserPanel` or from a span in `EditorPanel`), and `EditorPanel` is read-only **permanently**, not provisionally — a regenerated multi-object browsing buffer cannot carry per-object dirty state, per-object validation or per-object apply, and it conflicts with §18.2's file-per-object model. Nothing is ever pushed to a database from `EditorPanel` |
| 2026-08-02 | Two parallel design sessions specified the **same** editable single-object DDL tab under two names in two places — `ui/ddl_object_editor.py::DdlObjectEditorPanel` described inside §18.2 ("the DDL Editor surface"), and `ui/ddl_object_panel.py` ("name TBD") described inside a separate §18.5 | **De-duplicated to one specification:** the module/class is **`ui/ddl_object_editor.py::DdlObjectEditorPanel`** everywhere (§5/§7/§8/§18.1–§18.5/§26/§27), and the tab is specified **once, in §18.5**, where the sandbox lives — validation and the edit→validate→apply loop are one feature. §18.2 is renamed **"Projects, checkout & state markers"**, keeps only the project/file-naming/marker/manifest material, and *references* the tab: checkout changes only its injected load/save pair and adds marker rendering. The `CenterStage` dynamic-tab requirement (fixed indices never shift; key→widget map), the two right-click entry points with the `EditorPanel`-retains-spans amendment, and the Format Selection block all moved from §18.2 into §18.5 unchanged in substance |
| 2026-08-02 | **Scoping: "build full §18.2 first"** — the editable tab was specified as part of the git-project/checkout workflow, so a project, `ddl/` files, `.ddlproject/deployed.json` and `*`/`!` markers were prerequisites for editing one object | **Reversed by the project owner after seeing both designs: §18.5's scoping wins.** The tab is **project-decoupled in v1** — no `ddl/` folder, no manifest, no markers required to edit one object; it loads from the live introspected definition. It is written against an **injected load/save pair**, not a hard-coded source, so §18.2 layers on later by swapping only *where the buffer loads from and saves to*. Operative rationale, preserved verbatim in §18.5 D1: *"a git project, a manifest, a hash scheme and a marker recompute is a large prerequisite in front of 'edit one function and find out whether it compiles'."* Build order is now §18.1 → §18.5 → §18.2 → §18.3 |
| 2026-08-02 | §18.2: *"Saving writes to that local file **only** — it never touches the live DB directly (DB writes only happen via the reviewed §18.3 deploy step)"* — the editable tab had no path to a database at all | **Save and Apply are two distinct, explicit user gestures**, never automatic and never implied by each other: **Save** persists the edited text (buffer in v1, `ddl/*.sql` once checked out) and touches no database; **Apply** executes the DDL against a database. **Apply targets BOTH the sandbox and the target database, each confirm-gated** — the sandbox behind §18.5's naming-convention ownership rule, the target behind an explicit confirmation **naming the object and the database**. §18.3 remains the **reviewed batch deploy** with the `!`-drift gate and is **authoritative whenever both could apply**; single-object Apply is a narrower, individually-confirmed gesture that writes no manifest and makes no commit (§18.2's Apply-vs-Deploy table) |
| 2026-08-02 | §18.5's deliberately-open question *"what apply commits to in a project-less v1"* — candidates were (a) the target database via a confirm-gated `CREATE OR REPLACE` or (b) only the local buffer, deferring all durable writes to §18.2/§18.3 | **Resolved: both destinations, each its own confirm-gated gesture** (sandbox and target), per the row above. Removed from §29 as an open question |
| 2026-08-02 | §17/§18 single-seam assumption: `db/introspect.py::run_queries` is the **only** connection-opening function and is implicitly read-only (verified: it `execute`s + `fetchall`s and closes in a `finally`, never committing). One competing draft proposed making it **the write path too**, adding an `autocommit: bool = False` parameter and relying on close-time implicit rollback | **Rejected in favor of a separate, clearly-named write seam:** the new Qt-free module **`db/apply.py::apply_ddl(params, statements, *, commit, autocommit=False)`** — the codebase's **first database write path** — with **explicit** `commit()`/`rollback()` (never implicit close-time rollback) and an `ApplyOutcome` that captures failure as data. `run_queries` is **never widened** and stays the read-only read seam, so *"does this code write to the database?"* remains answerable by **which function is called**. Injectable as `applier: Applier = apply_ddl`, mirroring `runner: Runner = run_queries`. Never a third connection-opening function |
| 2026-08-02 | §17/§18.1 assumed a **single** connection profile — one live "target" database per session (`db/config.py`, fixed QSettings group `"db"`), with §18.2's only planned generalization being a **project key** | **Two** profiles: the existing `role = target` plus a new **`role = sandbox`** (§18.5 D2), persisted through the **same** generalized keyed-group scheme in `db/config.py` — one store, two dimensions (project key + profile role), one `ConnectionSetupDialog` with a profile selector. Not a second settings mechanism and not a second dialog |
| 2026-08-02 | §18.5 read as *"an editable tab with a lint target"* — the editable single-object tab and its Save/Apply gestures were the headline, and no deployment artifact was specified at all | **Outputs explicitly ranked, Apply demoted:** **(1) Generate Deployment SQL is THE deliverable** — sandbox = *desired state*, production = *current state*, output = one reviewed `.sql` migration script run once to upgrade the real database, built on `db/schema_diff.py` + `db/migration_gen.py` **to §18.3's exact `SchemaDifference` shape and signatures**, implementing the routine/trigger cases and leaving table/column to §18.3 (honouring *"one diff/generation engine, two entry points"*, with a raised `UnsupportedDifference` rather than a silent skip); **(2) the stateful sandbox** as accumulating executable desired state; **(3) per-object Save / Apply** as a convenience and the §18.2 precursor. Build order re-ranked accordingly — the deployment script is built last (it is worthless without validation) and is the first thing the user cares about. Also settled here: **stable alphabetical ordering, routines before triggers** (plpgsql bodies are not resolved at CREATE time, so forward references need no ordering; `LANGUAGE sql`/`BEGIN ATOMIC` routines and triggers are the real exceptions), with **`plpgsql_show_dependency_tb()` explicitly REJECTED** as the ordering source — it covers only plpgsql routines, precisely the ones that need no ordering, and would make the deliverable depend on an optional superuser-gated C extension |
| 2026-08-02 | §18.5 D2/D3: *"apply in a transaction → always `ROLLBACK`"*; *"the sandbox database stays pristine across any number of checks — no cleanup step, no accumulating garbage"*; *"validation writes nothing durable anywhere: everything it does inside the sandbox is rolled back"* | **Retracted — the sandbox is STATEFUL and accumulates applied edits; that is its purpose.** Owner's framing: *"we're doing schema changes on a sandbox, rollback is symbolic."* It was also a **design defect**: a pristine-baseline-per-check model **cannot validate interdependent edits** — edit `A` which calls `B`, and also edit `B`, and `A` is forever checked against the old `B`. Rollback survives **only** as the narrow *"check without applying"* probe, a convenience and not a guard. **The ownership guard is now the only safety property** and is pinned accordingly (`SANDBOX_DB_PREFIX` **and** a `pg_database` comment marker, because a name alone is spoofable; `is_app_owned` pure; `ForeignDatabaseError`; `open_sandbox` as the single gate). Adds the `pgtp_editor_sandbox.applied` working-set table with `text_sha1`, schema-level `reset()`, and **mandatory baseline provisioning** (an empty sandbox makes tiers 2–3 *actively harmful* — a false `relation … does not exist` ERROR reads worse than "could not check"): schemas → types → tables (columns only) → views → routines → triggers, deliberately omitting PK/FK/defaults/indexes/data because `plpgsql_check` is catalog-based and reads no rows. **Recorded gap:** `DatabaseSchema` models no view definitions, so a `pg_get_viewdef` query must be added or every routine touching a view fails to compile. **R5 mitigation is mandatory:** the realistic sandbox is a local restore named `myapp_dev`, `open_sandbox` refuses it, and the refusal reads as the tool being broken — so the *"create a sandbox for me"* offer ships with the refusal, not as later polish |
| 2026-08-02 | §18.5 Apply-to-target gated **only** by an explicit confirmation naming the object and the database | **Four hard preconditions, the confirmation being the last.** (1) **A changed signature is refused outright — no override, no consent path.** PostgreSQL identifies a function by `(schema, name, argtypes)`, so editing `calc_total(integer)` into `calc_total(bigint)` and applying makes `CREATE OR REPLACE` **create a second function and leave the old one live**; every existing caller keeps hitting the old one, the statement **succeeds**, and the confirmation dialog was **truthful** — no confirm-gate can catch it because there is nothing to refuse (R14). This deliberately makes parameter renames and argument-type changes **unreachable from Apply**, which is correct: they belong in the reviewable script path. Recorded alongside it, R13: `CREATE OR REPLACE FUNCTION` **hard-errors** on a changed *return type* or a renamed *input parameter*, which fails loudly but is a standing reason not to aim single statements at production — the deployment generator refuses those as named blockers during its drift check. (2) **Gated on a green sandbox validation, with an override that NAMES what could not be checked** — refusing silently would be worse than DBeaver; applying unvalidated *is* DBeaver. (3) **Runs in a transaction and rolls back on failure, with no revert snapshot** — stated explicitly: **a successful-but-wrong apply has no in-app way back until §18.2's checkout ships**, since the rollback covers what PostgreSQL rejects, not what compiles fine and behaves badly; this raises the value of landing §18.2 sooner. (4) The confirmation, unchanged |
| 2026-08-02 | §18.5 D3 tier 1: *"`SET plpgsql.extra_warnings = 'all'` … catches `shadowed_variables`, `strict_multi_assignment`, `too_many_rows`"* — documented as a working tier over the existing row-fetching runner | **Corrected — as specced the tier yielded nothing.** Its findings are delivered as **asynchronous `WARNING` notices** and the statements **return no rows**, so a row-fetching runner discards them entirely. Tier 1 is now specified against a **notice-capture channel** on the write seam (a psycopg-free normalized `Notice{severity, message, detail, hint, context, sqlstate}` collected on `ApplyOutcome.notices`), with findings parsed from `Notice.context`'s `near line N` and mapped through `map_lineno`; **where that channel is unavailable the tier reports `unavailable`, never `passed`.** Related correction: **tier 2 cannot reuse a plain `fetchall()` path** — psycopg 3 raises `ProgrammingError` on `fetchall()` after `SET`/`CREATE FUNCTION`/`CREATE EXTENSION`, so the write seam **must guard on `cursor.description is None`** and return results positionally 1:1 with the statement list (the earlier claim that tier 2 *"needs no new write path — it is the existing runner, used as-is"* was wrong). Line mapping is likewise pinned rather than left open: `body_line_offset`/`map_lineno` (`prosrc` line 1 **is** the dollar-quote opener's line), the exact `position`-derived line for tier-2 failures, and a mandatory **`None`** (render with no line) when the opener cannot be located — never a guess |
| 2026-08-02 | §5 dependency rule listed **`db/*`** among the modules that "are Qt-free and unit-testable without a `QApplication`" | **Factually wrong claim corrected** (pre-existing error; the code was never at fault): `db/config.py` imports `QtCore.QSettings` **at module scope**, because the connection store *is* QSettings. §5 now **enumerates** the genuinely Qt-free `db/` modules (`introspect`, `compare`, `rename`, `ddl_buffer`, plus the target-design `apply`/`sandbox`/`ddl_check`/`ddl_project`/`schema_diff`/`migration_gen`) and names `config.py` as the one accepted exception — **not** to be "fixed" by inventing a second settings/secrets store, which §17/§18.5 explicitly reject |
| 2026-08-02 | §26/§27 named the ladder gesture **"Validate DDL Object"**, a single menu action, with no deployment entry | **"Check DDL Object"**, matching the `[Check]` Audit prefix and `db/ddl_check.py`, and **three distinct gestures** — *Apply to Sandbox* (commits), *Check* (`recheck` against the sandbox as it stands), *Check without applying* (the rolled-back probe) — surfaced on the tab's own button row as well as the menu and context menu; the Database menu additionally gains **Generate Deployment SQL…**, and the one-click *Install plpgsql_check* lives **inside** Sandbox Setup next to the probe result rather than as a fourth menu item |
| 2026-08-02 | §7 stated the append-after-the-fixed-set / key→widget-map rule for dynamic `CenterStage` tabs as a one-clause aside, with the underlying fragility left implicit | **Promoted to an explicitly stated invariant with a mandatory regression test:** append-only creation (`addTab`, never `insertTab`) and tail-only removal, because the stored fixed indices are **load-bearing in five verified places** — `_active_find_bar`, `_active_bookmark_editor`, `_save_active_tab`, `_on_ddl_navigate_requested` and every `CenterStage.hide_*` (plus `_on_tab_close_requested`'s index dispatch, which must gain a widget-type branch *before* any index comparison). One `insertTab` ahead of the fixed set silently re-points all of them |
| 2026-08-02 | §18.4 recorded semantic/existence linting (do the referenced tables/columns/functions exist?) as *"a separate, explicitly deferred idea — not designed here"*, a forward pointer only | **Designed, in §18.5**, as the sandbox-backed **four-tier validation ladder** (`db/ddl_check.py` + `db/sandbox.py`, `okbob/plpgsql_check`), with the hard rule that **an unavailable tier reports "could not check", never "clean."** It remains **entirely outside** `format_selection`'s refusal gate, which stays tokenize/balance-only and offline. Findings report under **`[Check]`**, distinct from §18.4's `[SQL]` and §22's `[Lint]` — a three-way prefix reservation recorded in §7, §18.4, §18.5 and §22 |
| 2026-08-02 | §18.1 **as shipped**: routine identity is `schema.name` — `db/introspect.py::fetch_routines_and_triggers` keys `routines[f"{schema}.{name}"]`, `DdlObjectSpan` carries no `arg_types`, and `BrowserPanel` indexes `span_by_routine[(schema, name)]`. Overloads therefore **collapse last-wins**: the DDL Explorer shows one of N and silently drops the rest | **Overloads are never collapsed — each gets its own tree entry, its own `DdlObjectSpan`/DDL-buffer span and its own editable §18.5 tab.** Owner: *"just let repeat overloaded functions to the tree, the dropdown will anyhow show the difference, also the ddl is clearly different."* Routine identity carries argument types **everywhere**: the introspection dict keys on the full signature, `DdlObjectSpan` gains a `signature: str | None` field (from `RoutineInfo.signature`), `build_ddl_text` still breaks name ties on `arg_types` (the tuple of argument *types*, used only for ordering), and `BrowserPanel` indexes on `signature`. The tree shows N sibling nodes with the same `schema.name` top line, told apart by their existing per-argument `name (type)` children — the top-line label rule is **not** changed back to a parenthesised argument list. **Corrects shipped behavior**, and aligns §18.1 with the identity rule §18.5 already enforces for Apply-to-target and `diff_schemas`. *(Identity mechanism subsequently refined by BUG-019, 2026-08-02: the module-level rendering sketched here was settled instead as the `RoutineInfo.signature` `@property` — the single source consumed verbatim by `db/ddl_buffer.py`, `db/schema_diff.py::routine_identity` and `ui/ddl_buffer_panel.py`; see the BUG-019 entry in `docs/BUGFIX_QUEUE.md` for the full settlement.)* |
| 2026-08-02 | §18.2 overload filenames = **argument types in the name** (`ddl/public.fmt(integer).sql`), the "disambiguate-only-when-needed" scheme settled earlier the same day (the row above) | **Numeric `_n` suffix instead.** Owner: *"as of filenames, just resolve it with `_1`."* The sole holder of a `schema.name` — and the **first** overload in signature order — keeps `ddl/<schema>.<name>.sql`; further overloads get `_1`, `_2`, …. Argtypes in filenames render characters illegal/awkward on Windows and produce long churn-prone names. **Ordering is by the sorted argument-type signature, never by introspection row order** (which would silently reassign a file to a different signature between runs/machines, in git); a mid-set addition **renames with `git mv`**, a dropped overload leaves its file and its numbering gap alone. Accepted cost: `_1` is not self-describing — the mapping is recoverable from the file's own `CREATE OR REPLACE …(args)` header, which is therefore load-bearing and must be reported rather than guessed if unparseable. **Trigger filenames unchanged** (`ddl/<schema>.<table>.<trigger>.sql`) |
| 2026-08-02 | §18.5's unresolved v1 Save: the Save/Apply table said Save persists *"the in-session buffer in v1"*, while `resolve_save_path` said it *"returns `None` until Save As picks one"* — an editor whose Save produced nothing durable | **v1 ships `Save As… .sql`.** `Ctrl+S` on an object tab with no remembered path opens `getSaveFileName` (`SQL files (*.sql)`, prefilled with the §18.2 sole-holder filename shape); the chosen path is remembered and every later `Ctrl+S` writes it silently (UTF-8, `newline=""`, **no `.bak`**). Cancelling the dialog cancels the save; **cancelling Save As reached from the close-confirmation prompt ABORTS THE CLOSE** (the confirm flow must propagate save-cancel, or a dismissed dialog silently discards the edit). Save still **never** touches a database. Consistent with this section's own ranking — *"`Save As… .sql` is exactly §18.2's future `ddl/<schema>.<name>.sql` arriving early."* Also settled: **`Ctrl+Shift+S` stays project-only** and does not re-route to the object tab |
| 2026-08-02 | §27 stated `Ctrl+Z`/`Ctrl+Y` flatly as *"Window"* — i.e. the project snapshot history — with no carve-out for a DDL object editor tab | **Pinned invariant with a mandatory regression test: `Ctrl+Z` in the object tab uses the editor's NATIVE undo.** The window-level `QShortcut` at `main_window.py:401` drives **project-history** undo over the **Raw XML buffer**; `XmlEditor` consumes and re-emits it and the XSD tab routes its re-emission back into its own editor, but **`CodeEditor` does neither** — so without this the object tab's Ctrl+Z would silently revert the Raw XML project buffer while the user is looking at SQL. Realized the XSD way (editor consumes, tab reroutes to its own `undo()`), never by disabling the window shortcut. Test: object tab active + dirty Raw XML → Ctrl+Z changes the object buffer and leaves the Raw XML text byte-identical |
| 2026-08-02 | §18.5 read as one undivided increment: a panel button row carrying *Apply to Sandbox*/*Check*/*Check without applying*, Find All listed among the tab's inherited affordances, and no statement about a DDL Explorer re-run or `[SQL]` line behavior | **Six v1 scope carve-outs, owner-confirmed** (scope, not design reversals — the sandbox design above stands unchanged): (1) native `Ctrl+Z`, the row above; (2) **no button row and none of the three sandbox gestures in v1** — no dead or permanently-disabled controls, and the Database menu's five §18.5 entries likewise wait; (3) **Find All inert in the object tab**, matching the DDL Explorer precedent (`_populate_find_all_results` understands only `target="raw"`/`"xsd"`), while Find / Find Next / Replace / Replace All all work; (4) the Format-Selection **transient underline is panel-local** — `DdlObjectEditorPanel` owns the `setExtraSelections` call (verified: `CodeEditor` never calls it), cleared on the next edit or next format attempt; (5) **re-running Database ▸ DDL Explorer leaves open object tabs untouched and silent** — no reload, no marking, no prompt, even though live definitions may have changed underneath (drift is §18.2's `!` marker and §18.5's pre-generate drift check, later); (6) **`[SQL]` Audit lines are not clickable** — no line role, same as the existing `[Find]` summary line |
| 2026-08-03 | §18.2's project definition: *"'Project' — a new concept, distinct from a `.pgtp` file. A project = a git repo containing: …"* (`.ddlproject/project.json`, `ddl/*.sql`, `.ddlproject/deployed.json`, all git-tracked) | **A project is fundamentally a local folder the user chooses on their own machine — not necessarily a git repository.** Git is an **optional, TBD/deferred configuration** a project may eventually carry (server, user, the checkout/branch this project's folder is meant to be a worktree of), never the definition of a project. Owner's framing, preserved verbatim: *"the only source of truth in our projects is production database DDL, production pgtp and production phps. Everything else is just a snapshot, approximation, history"* and, using git only as an analogy (git itself not required): *"main is prod, each checkout a branch, and each time we open in the pgtp a worktree."* New Project creation flow: (1) pick a folder — that folder IS the project; (2) optionally add a local sandbox (Postgres connection + a Test button that specifically verifies superuser, reusing §18.5 D2's `SandboxCapabilities.is_superuser` probe as a new entry point, not a new mechanism); (3) optionally configure git — explicit placeholder only, not designed, mechanism TBD, mirroring §18.3's existing git-commit placeholder. Opening an existing project now compares **two** things, both surfaced, neither auto-resolved: a checksum of the `.pgtp` working copy against the source `.pgtp` at its sshfs-mounted path, plus the existing per-object DDL drift comparison. Menu actions renamed/expanded accordingly: **New Project…** / **Open Project…** / **Close Project** / **Project Settings…** / **Deploy .pgtp** (§26) |
| 2026-08-03 | §18.2's password-handling paragraph: the plaintext password is kept **out of** git by reusing `db/config.py`'s QSettings mechanism, generalized to a keyed `ProfileKey(project, role)` store (§17) | **The password now lives directly inside the project's own gitignored JSON file, not in QSettings, for project-scoped connections.** Owner's reasoning, preserved verbatim: *"if it remained in QSettings, it wouldn't be project specific"* — the project must be self-contained/portable (a folder that can be copied, backed up, or handed off complete), not dependent on a separate app-level global settings store keyed by a path that may not resolve elsewhere. The password never reaches git regardless, because the file it lives in is gitignored — gitignored **instead of** QSettings-hidden, not both. **Reconciled with §17's `ProfileKey` scheme on the least-invention reading:** the UI/selector mechanism (`ConnectionSetupDialog`'s profile selector, `target`/`sandbox`) is unchanged; only the **persistence backend** for a project-scoped `ProfileKey` changes, from a `db_profiles/<slug(project)>/<role>` QSettings group to the project's own `.ddlproject/settings.json`. The **non-project-scoped default profile** (`DEFAULT_PROFILE`, the literal `"db"` QSettings group used with no project open) is untouched and keeps using QSettings exactly as §17 already specifies |
| 2026-08-03 | §18.2's two-file scheme: `.ddlproject/project.json` (identity/metadata/`.pgtp` link, git-tracked) + `.ddlproject/deployed.json` (deploy manifest, git-tracked) | **Merged into one centralized, gitignored, plaintext JSON file** (`.ddlproject/settings.json`), holding project identity, the `.pgtp` link + its checkout/drift state, both connection profiles (target + sandbox, including password — see the password-handling row above), and the deploy manifest (content-hash + deployed commit id per object, **unchanged in shape**). The deploy manifest no longer needs to be git-tracked for its stated original reason ("so last-deployed state travels across machines") because git integration for this whole model is itself still TBD/deferred (the row above) — there is no live git workflow yet for that state to travel through; **revisit this when git integration is designed.** Governing principle stated explicitly because it explains this merge and the password change together — owner's words: *"nothing the app manages should be a black box… plaintext files everywhere"* — the same spirit that already justified `ddl/*.sql` as plain per-object files, now stated as a principle for the whole local-project model. New UI surface: **Project Settings…** dialog exposing this JSON's full contents (§18.2/§26) |
| 2026-08-03 | §7/§19's general `.pgtp` save behavior — plain save-in-place with a `.bak` sidecar written via `shutil.copy2` before overwriting an existing file, never on Save-As — implicitly assumed to apply universally, with no project-scoped carve-out | **Superseded, but ONLY within the local-project context — no-project-mode `.pgtp` save behavior is completely untouched by this row.** When a §18.2 local project is open, the `.pgtp` becomes a first-class checked-out artifact, parallel to a DDL object: the app works on a **local working copy** of the `.pgtp`; ordinary Ctrl+S/File ▸ Save writes to this working copy with **no `.bak`** (same rationale as `ddl/*.sql`'s existing no-`.bak` decision — the working copy itself is the safety net). Pushing the working copy back to overwrite the source `.pgtp` at the sshfs-mounted path is a separate, explicit **"Deploy .pgtp"** gesture, reachable both on-demand at any time (Database menu, mirroring DDL's on-demand batch Deploy, §18.3) and as a convenience prompt offered at project close if the working copy has unpushed changes (never forced). Outside a local project, §7/§19's existing plain-save-plus-`.bak` behavior is exactly as it was — this row does not touch it |
| 2026-08-04 | §18.1: *"a **separate fetch path from `fetch_schema`**, not merged into it: an implementation choice to avoid touching `fetch_schema`'s existing 3-query contract and its tests, since the DB Check features never need routine/trigger data. The `DatabaseSchema` it returns always has an empty `.tables`; only `.routines`/`.triggers` are populated"* | **Widened, not merged: `fetch_routines_and_triggers` now additionally runs `SCHEMA_SQL` (§17) and populates `.tables` too** (§18.6). `fetch_schema` itself and its existing 3-query contract/tests are untouched, and DB Check keeps calling `fetch_schema` directly — this is one connect-time fetch on DDL Explorer now serving two consumers (routine/trigger browsing **and** §18.6's schema-aware Ctrl+Space completion, via the new `db/schema_index.py`), not a second parallel fetch and not a lazy per-keystroke query |
| 2026-08-05 | §18.5 D2's "Zero bundled bytes" invariant, stated flatly: *"The app ships no server, no client binaries, and invokes no external process. Everything goes over `psycopg`."* — with no carve-out of any kind | **A single, deliberate, narrowly-scoped exception for optional sandbox data cloning (new §18.5 D2a).** The schema-only `build_baseline_sql` baseline path (D2's core contract) is completely unchanged and stays in-process/`psycopg`-only, today and after this addition. The **new, optional** "with data" sandbox-provisioning mode shells out to **`pg_dump`**/**`pg_restore`** as external subprocesses against the user's locally-installed binaries (the app bundles neither) — chosen once, at sandbox-creation time (a "with data"/"without data" choice added to the New Project dialog's local-sandbox step, §18.2), never toggled later. Cloning is **one-shot**: there is no refresh/re-sync operation — refreshing means destroying and recreating the sandbox, whose existing schema-level `reset()` (`DROP SCHEMA … CASCADE`) is followed by a re-run of whichever provisioning strategy (schema-only or with-data) the sandbox was created with, recorded in the project's sandbox settings rather than re-derived. A missing `pg_dump`/`pg_restore` on `PATH` is a named, actionable failure, never a silent fall-back to schema-only. Everything else in D2/D3 (ownership guard, working-set bookkeeping, the validation ladder) is unaffected — `plpgsql_check` still reads no rows regardless of which baseline mode produced the sandbox |
| 2026-08-05 | §18.1/§18.5's implicit architecture: **exactly one** `BrowserPanel` instance, **one** left-dock "DDL Objects" tab, **one** center `EditorPanel` DDL Explorer tab, and **one** database connection feeding all of it — stated as fact throughout §18.1 ("the tab," "the tree") with no per-connection variant ever contemplated | **New §18.7: the DDL Explorer becomes per-connection, not a singleton, once a project has a sandbox.** A second, independent instance of the existing `BrowserPanel`/`EditorPanel` pair browses the `role=sandbox` connection (§18.5 D2) alongside the existing target-database instance — both may be open simultaneously, each its own dock tab and center tab. `CenterStage`'s dynamic-tab key→widget map (previously used only for §18.5's per-object tabs) is generalized to also key the two DDL Explorer tabs by connection **role**, rather than the fixed `ddl_tab_index`; the left-dock "DDL Objects" tab likewise becomes two, one per role. `BrowserPanel`/`EditorPanel`'s own rendering/tree-building/navigation code is **reused unmodified** — only instantiation count and which `ConnectionParams` feeds each instance's fetch changes. Drift-marker computation (§18.2's `*`/`!`) is scoped **per source connection**, not shared between the two instances, and each instance's tree must tolerate its connection's object set genuinely diverging from the other's (no cross-referencing, no merged/diffed tree — an object present only in the sandbox or only on target simply does not appear in the other instance at all). The sandbox-scoped instance's menu/dock entry is **absent**, not disabled, until a sandbox exists for the active project (mirroring §18.5 carve-out 2's "no dead controls" posture) |
| 2026-08-05 | §18's "Five parts" table described §18.2's scope as *"the 'project' concept (**git repo**, `ddl/*.sql` file-per-object, `.ddlproject/` manifests)"* — a stale description left in place after the 2026-08-03 "project = local folder, not necessarily git" revision superseded it elsewhere in the same top-level section | **Corrected to match the already-current body text, no design change:** §18.2's scope is now described as *"a local folder (git optional/TBD, not the definition of a project), `ddl/*.sql` file-per-object, `.ddlproject/settings.json`, checkout-to-edit, and the `*`/`!` state markers."* This is a **prose-drift fix, not a new decision** — the 2026-08-03 row above already establishes the current truth; this row only records that the "Five parts" table itself had not been updated to match it. Also new the same day: an explicit **"three operating modes" taxonomy** (standalone / quality project / development project) added at the top of §18, reframing — not changing — the already-settled scope of §18.1 (read-only, unchanged), §18.2/§18.5 (quality-project capabilities: DDL editing, Save, batch deploy.sql, Apply-to-Target), and §18.5 D2/D2a/§18.7 (development-project capabilities: sandbox linting tiers, Apply-to-Sandbox, the sandbox DDL Explorer instance, Generate Deployment SQL) — gating "development project" on an **environment capability** (reachable local Postgres; `psql`/`pg_restore` on `PATH` required only for D2a's optional "with data" clone, verified against D2's actual in-process-`psycopg`-only schema baseline, not a general sandbox prerequisite) rather than a bare per-project settings toggle. Where/when the capability check runs and how tier 2-vs-3 is surfaced to the user is recorded as a new open question (§29), not resolved by this pass |
| 2026-08-05 | The "Project Status" window/screen was named as the planned destination for tier/capability/degradation-reason display (top of §18, added same day) but stated explicitly as **NOT YET DESIGNED** — "the owner has UI reference images saved locally for it but has not yet specified its layout or behavior," recorded as an open question in §29 | **New §18.8: the window is now fully specified as a node-and-connector diagram** — quality (target-DB connection) → app (`ProjectCapabilityStatus`/`ProjectTier`'s 4 named states: `app_standalone`/`app_sandbox_not_set_up`/`app_sandbox_connection_ok`/`app_sandbox_offline`) → sandbox1 (data-fill status, upper) / sandbox2 (`plpgsql_check` capability, lower), the app→sandbox connector splitting in two. Sandbox1/sandbox2/their connector are **absent, not grayed out**, whenever no sandbox is configured at all (mirroring §18.5 carve-out 2 / §18.7's absent-not-disabled rule). All four node families are clickable, each opening a node-specific "action window." **Deliberately left open, not invented:** the four action windows' exact contents/behavior (§29), the exact connector state set beyond the `connector_[status]` naming convention, and the menu/shortcut entry point — this row fills the previously-flagged design gap, it does not merely reword it |
| 2026-08-05 | §18.8's just-written **4-node** model (row directly above, same day): a single 4-state `app_*` node (`app_standalone`/`app_sandbox_not_set_up`/`app_sandbox_connection_ok`/`app_sandbox_offline`) that **conflated project tier and sandbox live connectivity into one node**, in a `quality → app → (sandbox1 / sandbox2)` chain | **Corrected to a 5-node model** — a real correction of just-written design, not a refinement of the still-open question, hence its own ledger row. Chain is now `quality → app → sandbox → (sandbox1 / sandbox2)`. **App node narrowed to 3 states, project tier only** (`app_standalone`/`app_project_not_setup`/`app_project_setup`), mapping onto `ProjectTier`'s existing `QUALITY`/`DEVELOPMENT` plus "no project open" (not itself a `ProjectTier` member — see the App-node implementation note in §18.8). **New, distinct `sandbox_*` node** takes over the live-connectivity states the old `app_*` node used to carry, plus a new `sandbox_tools_missing` state (sandbox DB reachable but `psql`/`pg_restore` absent, relevant only under `SandboxMode.WITH_DATA`) that the 4-node model had no room for. Sandbox1/sandbox2 unchanged in meaning. Click-through is also corrected from one uniform pattern to two: Quality/Sandbox open a one-step status/reconnect-or-help window; Sandbox1/Sandbox2 open a two-step status+help window with an embedded action button ("run data clone now" / "run `plpgsql_check` install now"); the App node's action window remains the one genuinely unspecified click-through, carried over from the prior pass. Absence rule widened from "sandbox1/sandbox2 absent" to "sandbox node + sandbox1 + sandbox2 + their connectors all absent" when no sandbox is configured. **Implementation note, not papered over:** the shipped `ProjectCapabilityStatus`/`ProjectTier`/`SandboxCapabilities` shapes in `pgtp_editor/db/sandbox.py` do not need new members to support this corrected model, but they also do not natively expose "is a project open at all?" (needed for `app_standalone`) — the window's rendering logic must add that check itself rather than reading it off `ProjectCapabilityStatus`, which only ever describes an already-open project |
| 2026-08-05 | §18's three-modes table (Tier 1) and the Database-menu descriptions (§17's "UI:" paragraph, §26) listed **Connection Setup…** as unconditionally available, with no mode gating stated one way or the other (an incidental omission, not a considered decision — BUG-024) | **Connection Setup… is projectless-mode only.** While a §18.2 local project is open, the project's own `ProjectSettings.target`/`.sandbox` (edited via **Project Settings…**) is the sole connection store; the app-level `Connection Setup…` action is now disabled (`self._connection_setup_action.setEnabled(self._ddl_project_folder is None)`, refreshed by `_refresh_project_dependent_actions()` on both project open and close) and `_open_connection_setup()`/the two internal missing-connection callers (`_run_db_check`, `_open_ddl_explorer`) reroute to Project Settings… instead of opening the dialog while a project is active. Corrects the prior unconditional-availability framing in both §18's Tier-1 row and §17/§26's Database-menu prose |
| 2026-08-05 | §18.2's auto-open of a project's linked `.pgtp` (added earlier the same day) was specified as behavior only, with the menu wiring left unstated — and as shipped it was **dead on the only path a user can reach**: `open_project_action.triggered.connect(self._open_ddl_project)` let `QAction.triggered`'s `checked: bool` bind to `on_ready`, so `on_ready=False` passed the `if on_ready is not None:` guard, called `False()` and never reached the auto-open branch (BUG-021, reopened after 2508d2a) | **The wiring is now part of the specification, not an implementation detail:** both project actions are connected through an argument-swallowing lambda (`lambda: self._open_ddl_project()` / `lambda: self._new_ddl_project()`) and both guards are hardened from `is not None` to **`callable(on_ready)`**. The `_auto_open_linked_pgtp` zero/one/multiple logic is unchanged — it was always correct. Generalized rules recorded in §18.2: any argument-less action slot with optional parameters is lambda-wrapped, and a regression test for such a slot must drive the **real signal** (`action.trigger()`), since a direct method call cannot reproduce the defect (the pre-existing test passed against dead code) |
| 2026-08-05 | §17 `TableCheck{name, ok, kind, invocations, columns}`, with `check_db_against_xml`'s table-level `ok = table_name in columns_by_table` — i.e. *"the table name appears among the **page/detail** bindings"* — and `DbCheckPanel` rendering a single aggregate `(×N)` invocation count in **both** directions (BUG-026) | **`TableCheck` gains `page_count`/`detail_count`/`lookup_count`** (defaulted, so `check_xml_against_db` is untouched), populated from the new **`xml_table_role_counts(project)`** in `db/compare.py`, and the DB→XML table-level rule becomes **`ok = (page_count + detail_count + lookup_count) > 0`** — *referenced in **any** role, page, detail **or** lookup*. A lookup-only table is therefore no longer a red mismatch contradicting its own nonzero count. The **DB→XML** tree shows the role split `(P# D# L#)`; **XML→DB** keeps `(×N)`. `xml_table_columns`/`xml_table_invocations` are unchanged and still drive the per-column check and the aggregate; `ok` remains the **single** mismatch signal for styling, the header count, "Show only mismatches" and the UserRole tuple — no parallel role-count mismatch flag |
| 2026-08-05 | §7 (and the 2026-07-20 ledger row *"Toolbar Available = registry-minus-present" → "Available = all commands, present ones disabled"*, whose **"all commands" meant all commands in the static registry**): the toolbar was *"driven by a stable action-id registry (`toolbar_registry.py`)"* holding a hardcoded 7-entry `AVAILABLE_COMMANDS`, with each toolbar button a **freshly-built `QAction`** wired through a hardcoded `_toolbar_slots` dict — a closed universe that could never offer a real menu command (BUG-027) | **Available = every MENU command**, enumerated by walking the live menu bar (`MainWindow._walk_menu_actions`/`_all_menu_commands`/`_collect_menu_commands`), with ids **derived from the menu path** (`File › Save As... → file.save-as`) instead of hand-assigned. `AVAILABLE_COMMANDS` and `_toolbar_slots` are gone; `toolbar_registry.py` is reduced to pure identity rules (`normalize_label`/`slugify`/`command_id_for`/`menu_path_label`, `LEGACY_COMMANDS`, `LEGACY_ID_ALIASES`, `DEFAULT_TOOLBAR_IDS`, `ICON_ID_BY_COMMAND`, `valid_ids`, `resolve_ids`). The toolbar hosts the **menus' own QActions**, so a button shares the menu item's slot, enabled state, checked state and shortcut (hence `removeAction` in a loop, never `QToolBar.clear()`, which deletes them). Icons stay **optional** — only the legacy seven have vendored SVGs, and they are hidden in menus (`setIconVisibleInMenu(False)`). Pre-widening saved toolbars survive via `LEGACY_ID_ALIASES` applied in `resolve_ids`. Excluded from the walk: separators, submenu placeholders, and the dynamic **Open Recent** submenu wholesale. Load-bearing gotcha recorded in §7: `QAction.menu()` transfers ownership to Python, so every descended submenu **and its owning action** is pinned in `_menu_keepalive` for the window's lifetime |
| 2026-08-05 | §13's active-filter banner (BUG-020, earlier the same day) represented **only** the preset row-predicate: `_refresh_filter_banner` read `row_predicate_label()` and hid the banner whenever that label was empty, and `apply_find_filter` never refreshed it — so a find filter narrowed the grid with nothing on screen stating the find text, its mode/case or its scope (BUG-028) | **The banner represents the whole-row find filter as well.** `apply_find_filter` refreshes the banner (only after `set_regex_filter` returns normally — an invalid regex raises), and `_refresh_filter_banner` composes **both** descriptors, joined by the same `"  ·  "` separator: the preset label, and `_find_filter_descriptor()`'s `Find "<pattern>" (<qualifiers>)` — mode named only when non-default (`regex`/`extended`), `case-sensitive` only when set, always ending with **`all columns`** (the find filter matches any column, so that is the honest scope). Mode/case are read through new proxy getters `find_mode()`/`find_case()`. The banner hides only when **neither** is present; `clear_all_filters()` stays the single clear path. **Header value filters remain deliberately unrepresented** in the banner — they keep their exclusive per-column ▼ marker, which is never painted for the find filter or the preset predicate |
| 2026-08-06 | §18.1 (2026-08-05, Tables-branch widening): *"A DDL table node is **click-only, no context menu** — right-click ▸ Edit…/Check Out remain routine- and trigger-leaf-only, since a whole table has no single `DdlObjectSpan`/source text to hand those entry points"*; mirrored in code by `BrowserPanel.table_selected`'s docstring | **Carve-out for creation (FQ-002).** A table node **does** get a context menu, holding exactly one entry — **Add Trigger…** — which opens the new-trigger dialog (name · timing · events · level · existing-trigger-function chooser) and then a §18.5 editor tab on a `db/ddl_skeleton.py::trigger_skeleton` result. The original narrowing stands **for editing**: Edit… / Check Out for Versioning stay routine- and trigger-leaf-only, because they need a source span. A not-yet-existing object has no source text, so the span limitation does not apply to it. Left-click behavior (`table_selected(TableInfo)` → shared `PropertiesPanel`) is unchanged |
| 2026-08-06 | §18.5 D1: *"**Two entry points, both right-click, converging on one operation**"* — the editable `DdlObjectEditorPanel` tab was reachable only by Edit… on `BrowserPanel.tree` or inside a span in the read-only `EditorPanel` (plus §18.2's Check Out variant), all of which resolve an **existing** object through `resolve_edit_target` against the live `DatabaseSchema` | **A third, non-edit gesture opens the same tab: creation (FQ-002).** The §18.1 Add Trigger / Add Function-or-Procedure dialogs build a `DdlObjectRef` for an object the database has never heard of and call the same `CenterStage.open_ddl_object_tab(ref, text, …)` with **generated skeleton text** instead of an introspected `RoutineInfo.source`/`TriggerInfo.definition`. `resolve_edit_target` is **not** on this path (it correctly returns `None` for a non-existent object) and remains the single identity-derivation point for the two edit entry points. The panel gains **no** new capability and must not branch on whether the object exists |
| 2026-08-06 | §18.2/§26 placed the five project actions (**New Project…**, **Open Project…**, **Close Project**, **Project Settings…**, **Deploy .pgtp**) on the **Database** menu, "alongside the existing Connection Setup / Check / DDL Explorer entries", and §26's Database bullet carried their full descriptions | **Spec-vs-reality drift corrected in favor of the shipped code — the five live on the FILE menu**, owner-confirmed. `MainWindow._build_file_menu` builds them as their own separator-delimited group between `Open…` and `Save` (`New Project…`, `Open Project…`, `Close Project`, `Project Settings…`, `Deploy .pgtp`); `_build_database_menu` contains **no** project action. §26's File bullet now carries the group and its descriptions, and the Database bullet states explicitly that these five are not on it (Connection Setup / Check / DDL Explorer and the §18.5 sandbox entries genuinely are). Nothing about the actions' behavior, gating or wiring changes — **menu location only**. `pgtp_editor/resources/manual.md` already documented them as **File ▸ …** and was correct throughout |
| 2026-08-06 | §17's **two-direction DB Check framing**: two Database-menu items (*Check: XML→Database* / *Check: Database→XML*) driving one `DbCheckPanel` in a hidden `left_tabs` tab, with a direction label in its header, a direction-dependent per-table count suffix (`(P# D# L#)` for DB→XML vs. the aggregate `(×N)` for XML→DB) and a `_last_db_check_direction` cache consulted on reparse | **One Database-menu checkable toggle, one merged "Database/XML Coherence" view, no direction control anywhere** (FQ-003). The direction toggle is **eliminated, not merged**: once DB state and XML state are shown together per relation, there is no remaining choice about which side is ground truth for display — **the DB always is, and the XML is always the interface being checked against it** (requester's core framing). The view has two branches over the same data layer: **Tables and Views** (DB-sourced; per relation a *Database columns* sub-section = today's `ColumnCheck` list with calculated columns shown but never flagged, BUG-006, and a *References* sub-section badge-summarized from the existing `TableCheck.page_count`/`.detail_count`/`.lookup_count` rollups, BUG-026, expandable to the full breadcrumbs) and **Pages** (a **recursive** tree mirroring the real XML depth — Page → bound table + lookup columns → nested Details, each with their own table/lookups/further Details, exactly `visit_detail`'s unlimited recursion; the UI must **not** flatten it to a fixed "Page > Details > Detail > Lookups" shape, and the `"lookup with insert"` `ref_type` stays a distinct badge). One **global mismatch toggle** filters both branches: a Pages node whose target relation is absent from the live DB is flagged **at that reference point** (never as a phantom row under Tables and Views, which stays purely DB-sourced); a real relation with `page_count == detail_count == lookup_count == 0` **is** flagged (requester-confirmed — the toggle is "things needing attention," not strictly "things that are broken"); `ColumnCheck.ok == False` folds in, excluding calculated columns. No mismatch-type enum exists today, so the toggle carries its own predicate. `collect_table_usages` and the existing rollup fields must be reused wholesale — **no parallel counting logic**. The `(P# D# L#)` badge survives as the relation-level form; the aggregate `(×N)` and `_last_db_check_direction` go away with the direction. Rejected alternatives recorded in §17: the connection-optional hybrid with a cross-navigation link (superseded — the motivation is architectural, not a UI convenience), and §18.3's unified-Compare/Deploy rejection, **explicitly distinguished rather than silently re-decided** (that turned on **risk asymmetry** — Compare read-only vs. Deploy destructive — and both surfaces merged here are read-only diagnostics with no write path). Settled design, **not yet implemented** *\[status correction, 2026-08-06 audit — the trailing clause was stale when written into this row: the view has since shipped (`db/coherence.py`, `ui/coherence_panel.py`, the Database-menu toggle; see §17 and the TOC). The design content of this row is unchanged\]* |
| 2026-08-06 | §18.3 step 2: *"**Any `!`-flagged object blocks deploy of the batch it's part of**"* — read literally, every live-drifted object in the project, whether or not it is part of the batch | **Narrowed to `*!` only: a blocker is a deploy *candidate* (`*`, locally edited) that is **also** live-drifted (`!`).** A `!`-only object is **not** a blocker — with no pending local edit it is not in the batch and nothing would overwrite it, and since §18.5's single-object Apply routinely leaves objects `!`, blocking every deploy on unrelated `!` markers would make the gate un-actionable rather than protective. Everything else about the gate is unchanged: one blocker refuses the **whole** batch, the refusal names **every** blocker, recovery is resolve-then-re-run. Implemented as `db/deploy_bundle.py::deploy_blockers` (candidates ∩ `live_drifted`), with blocked-ness expressed as **data** (`DeployPlan.blockers` non-empty + `bundle is None` + `refusal_message`), and "nothing to deploy" kept as a deliberately distinct outcome |
| 2026-08-06 | §15's **Table References tab** as an independent left-dock surface: `TableReferencesPanel` in its own hidden `left_tabs` tab ("Table references", `table_refs_tab_index`), revealed by the **View menu** checkable "Find table reference", refreshed on reparse when visible — specified in §15 as a sibling of Search/Find All and cross-referenced from §17 | **Folded into §17's Database/XML Coherence view** (FQ-003, row above). Table references are no longer independently toggleable: they appear as the per-relation **References** sub-section of the *Tables and Views* branch and as the whole **Pages** branch of the merged view. The `table_refs_tab_index` hidden tab and the **View ▸ Find table reference** checkable both **disappear as standalone entry points** (§26's View bullet loses that item); the single Database ▸ **Database/XML Coherence** toggle is the only entry point. §15 keeps a pointer only. The pure analyzer `analysis/reused_tables.py::collect_table_usages` and its `TableUsage`/`TableReference` shapes are **unchanged** and must be reused wholesale by the merged view — this row moves presentation, not analysis. The earlier removal of Tools ▸ "Find Reused Tables…" / `reused_tables_window.py` stands |
| 2026-08-06 | §29 open question: *"**Execution against the sandbox (§18.5)** — running a function and seeing its results is not designed. It is the difference between a validator and an IDE… Scope it as a follow-on feature or fold it into v1 — undecided."*, mirrored by §18's tier-3 row (*"see the open item below for running a routine against sandbox rows, which is separate and not yet designed"*) | **Closed by owner decision — designed as §18.5 D4, the Sandbox SQL Console.** A single dynamic center tab (`ui/sql_console_panel.py`, keyed `("sandbox-sql",)`) pairing `CodeEditor(language="sql")` with `ui/sql_results_panel.py::SqlResultsPanel`; the Qt-free `db/sandbox_query.py::run_sandbox_query(session, sql, …) -> QueryResult{columns, rows, truncated, row_limit, command_status, duration_ms, error}` running through the **existing** `SandboxSession.executor` (one new `fetch` method with the `cursor.description is None` guard) — **never a new connection-opening function**; `DEFAULT_ROW_LIMIT = 1000` enforced client-side by `fetchmany(row_limit + 1)` (never by rewriting the user's SQL), `truncated` a first-class field so an at-the-cap result and a cut-off result are distinguishable; a **mandatory** `DEFAULT_STATEMENT_TIMEOUT_MS = 30_000` with no "unlimited" setting and **no Cancel button in v1** (stated, with the reason: per-call connections leave no handle to `cancel()`); multi-statement Runs split by the new pure `sql/statements.py::split_statements` over §18.4's **existing** tokenizer, executed in **one committing transaction**, aborted and rolled back whole on failure; object-changing statements (`classify_statement` → `ddl`/`unknown`) gated by the same injected `confirm` seam the Apply gestures use, with the working-set-divergence caveat surfaced rather than papered over. **Safety rule, stated so nobody generalizes it: sandbox-only, enforced structurally** — `run_sandbox_query` takes a `SandboxSession`, never `ConnectionParams`, so execution can only reach an `open_sandbox`-gated, app-owned, `reset()`-able database. The distinction from §18.3's never-auto-execute non-goal is **reversibility**, not deliberateness. No `[Run]`/`[Query]` Audit prefix is created: results and errors live in the console's own panel |
| 2026-08-06 | §18.5 D3 specified the ladder's tiers, report shape and line mapping, but never pinned **how a `plpgsql_check` run is actually invoked, scoped, gated or reported** — §18.8's Sandbox2 node covered only the extension's *install state*, and *"the `[Check]` Audit results"* remained a contract with no rendering rule | **New D3a, the Check gesture's concrete run contract.** `plpgsql_check_function_tb` only (never `plpgsql_check_function`, never the `_all_*` sweeps), **named notation always**, `fatal_errors => false`, `all_warnings => true`, `relid` for trigger functions; **exactly one object per run** (the active tab's `DdlObjectRef`), with working-set sweeps defined as a pure `check_working_set` loop over the same `recheck` entry point and **no menu entry of its own**. The 11 returned columns map 1:1 onto `CheckFinding`; a **total** `level → SEVERITY` mapping is pinned (an unknown future level maps to `WARNING` with the raw level appended, never dropped). **The four `plpgsql_check_state` values each gate the run with a distinct, user-visible outcome** — `installed` runs; `installable` reports `unavailable` plus where the one-click install lives; `absent` reports `install_gate`'s platform text verbatim; `unknown` reports *"could not probe the server."* and **never** degrades to `absent` — with tiers 1 and 2 still running in all three, the report never green, and precondition 2's enumerating override the only way past. With **no session** the gesture is **absent**, and the absence names the way back (Sandbox Setup… / Project Status), never a clean check |
| 2026-08-06 | `ui/ddl_object_editor.py::_result_lines` **as shipped** folds validation findings into the narrative `check_reported(list[str])` channel as pre-formatted `"  finding: line N: message"` strings | **Findings move to a second, clickable channel, `check_findings(list)`.** A pre-formatted string cannot carry the `UserRole` line and `UserRole+1` target that §18.5's reuse-map contract (*"the existing Audit panel … click-to-navigate — **no new diagnostics panel**"*) requires. `MainWindow` renders each finding as `"[Check] SEVERITY line N: message"` with both roles set; a finding whose line could not be mapped (D3's mandatory `None`) is rendered **without a line and without roles**, inert rather than navigating somewhere wrong. `check_reported` keeps the narrative channel unchanged — one line per tier **always**, caveats, apply/cancel notices, all non-clickable. `_result_lines` stops emitting `finding:` lines when `db/ddl_check.py` lands |
| 2026-08-06 | §18.5 invariant 1: *"**Two seams, one direction each:** `run_queries` … `apply_ddl` … **Never a third connection-opening function.**"* — written before `db/sandbox.py`'s `SandboxExecutor` shipped, which is in fact a third | **Corrected to three seams, each with one job, and never a fourth**: `run_queries` (read-only, never widened), `apply_ddl` (the DDL write seam, mixed-statement guard + notice capture), and `SandboxExecutor` (`execute`/`query`/`fetch`) — the **sandbox lane's** seam, reachable **only** through an ownership-gated `SandboxSession`, used by `apply`/`applied`/`reset`, `install_plpgsql_check` and D4's `run_sandbox_query`. Its narrowness is not an accident to be tidied away: it *is* D4's safety property, and it is why ad-hoc SQL can never reach production. A code correction is **not** implied — the code was right and the invariant's wording was stale |
| 2026-08-06 | The one-click **Install plpgsql_check** action had **two specified homes with no stated relationship** — §18.5 D2/§26 (*"inside the Sandbox Setup dialog next to the probe result … not as a separate menu item"*) and §18.8's Sandbox2 action window (*"offers an 'install the plpgsql_check extension' action button … now also reachable from here"*) — flagged as a conflict by the 2026-08-06 audit | **Resolved as one action with two entry points, neither a duplicate.** The single action is `SandboxController.install_plpgsql_check()` → the pure `install_gate` → `db/sandbox.py::install_plpgsql_check(session)`. **Sandbox Setup… is the primary home** (next to the probe result it depends on); §18.8's Sandbox2 window is a **second entry point to that same method**, wired through the shipped zero-argument adapter `on_install_plpgsql_check`, re-deriving no gate, re-typing no reason string and opening no session of its own. Both surfaces show `install_gate`'s reason verbatim on refusal and the same *"already installed."* line when there is nothing to do. Still **no top-level menu item** for it |
| 2026-08-06 | §7/§4 theme: the QSS layer was **dark-only** — `apply_theme` did `app.setStyleSheet("" if light else _dark_stylesheet())`, with a single `_dark_qss_cache: str \| None` global, and *"light **always** assigns the empty stylesheet … so a light↔dark round-trip never leaves stale dark QSS behind"* was a stated invariant (BUG-010 row, 2026-08-01). Light was therefore Fusion + `light_palette()` only — stock, unstyled chrome | **Both themes get the QDarkStyleSheet QSS** (FQ-005): `_dark_stylesheet()` → **`_qdarkstyle_stylesheet(light: bool)`** caching both variants in **`_qss_cache: dict[bool, str]`** and passing `palette=LightPalette if light else DarkPalette` **explicitly** (dark previously relied on qdarkstyle's implicit default); `apply_theme` calls `app.setStyleSheet(_qdarkstyle_stylesheet(light))` **unconditionally**. **Zero new dependencies** — `qdarkstyle>=3.2` was already pinned and ships `qdarkstyle.light.palette.LightPalette`. The empty-stylesheet clause is **retired**: the new invariant is that a toggle always *replaces* the entire app QSS, so staleness is impossible without an empty state. `light_palette()`/`dark_palette()` are **unchanged** — only the QSS *source* changed, so `XmlEditor.apply_theme_colors` (keyed off palette Base lightness) is unaffected. Rejected vehicles, recorded: `qtass-pyside6` (no license, `requires-python<3.14` vs. the installed 3.14.6, near-zero maintenance signal) and, as the moot fallback, `qt-material` (BSD-2-Clause) — no dependency was needed. Consequent **test-contract** change: a non-empty app QSS wraps the style in Qt's `QStyleSheetStyle` proxy (`objectName() == ""`), which already silently held for dark but was masked by the light-only `"fusion"` read-back assertions; tests now **spy on `QApplication.setStyle`** instead of reading `app.style().objectName()`. Not a functional regression — Fusion is still requested and still governs anything the QSS leaves alone |
| 2026-08-06 | §18.8's asset pipeline as designed: images "saved locally, not yet wired", `.png` examples (`quality_ok.png`/`quality_ok_drk.png`), wiring left as an "implementation task", state names flagged candidate/not-owner-verbatim (`sandbox_connection_ok`, a Quality `error` state), and **connectors "carry state"** with a `connector_[status]` state set left to enumerate (§29) | **Pinned to the shipped `ui/project_status_model.py` layer.** Assets are **`.svg`-only** in `resources/status/` (`ASSET_EXTENSION = ".svg"`, BUG-029 — the `.png` slices were deleted); each per-family enum's *value* IS the filename stem, resolved via `asset_filename(stem, dark)` with `DARK_SUFFIX = "_drk"` and guarded by `all_asset_stems()`-parametrized tests. Shipped stems: `quality_connection_not_set_up`/`quality_offline`/`quality_connection_ok`; `app_standalone`/`app_project_not_setup`/`app_project_setup`; `sandbox_not_set_up`/`sandbox_connected`/`sandbox_offline`; `sandbox1_empty`/`sandbox1_filled`; `sandbox2_plpgsql_check_installed`/`sandbox2_plpgsql_check_not_installed`. **Connectors are position-keyed and STATELESS** — exactly three assets (`ConnectorKind`: `connector_quality-app`/`connector_app-sandbox`/`connector_sandbox-db`, the third visually splitting after the Sandbox node), no per-state variants; the §29 "connector state set" open question is closed. The 4-way tools-missing backing distinction survives as `SandboxDegradation` for the click-through window, still with no icon of its own |
| 2026-08-06 | §7: *"Icons are optional. Only the legacy seven have vendored SVGs … every other command is icon-less by design"* — a closed icon universe (seven vendored Breeze SVGs via `ACTION_ICON_FILES`, `ICON_ID_BY_COMMAND` defaults) with no way for a user to assign an icon to any other toolbar command (BUG-027 row, 2026-08-05) | **Any toolbar button is user-decoratable from a vendored Breeze catalog** (FQ-004 — shipped in commit `a12b522`; this row is the mandatory-policy catch-up, folding an already-shipped design into the spec). `ui/icons.py` widens the vendored pack to a curated common-action subset and adds an enumerable, lazily-directory-scanned catalog (`icon_catalog`/`catalog_ids`/`catalog_filename`/`search_catalog`/`human_name_for`; catalog icon ids = SVG filename stems, a second id space beside the legacy action ids, both accepted by `load_svg_text`/`themed_icon`). The Customize Toolbar dialog gains per-row icon previews plus a **Choose Icon…** button / row double-click opening `ui/icon_picker_dialog.py::IconPickerDialog` (searchable icon grid over the catalog; always-first "Default" cell, sentinel `DEFAULT_CHOICE = None`, clears the assignment; test seams `set_filter`/`visible_icon_ids`/`select_icon`/`chosen_icon_id`, never `.exec()`). Assignments `{command_id: catalog_icon_id}` persist in the sibling QSettings key **`toolbarIconIds`** (`serialize_icon_assignments`/`parse_icon_assignments`), pruned on load by `toolbar_registry.resolve_icon_assignments` (legacy ids through `LEGACY_ID_ALIASES`; vanished commands/icons dropped) and resolved per button by `icon_id_for` — assignment wins, else legacy default, else icon-less. "Icons are optional" itself **stands**: an icon is still never a precondition, and with no assignment stored, behavior is exactly pre-FQ-004 |
| 2026-08-07 | §7: *"**Startup file:** `main()` opens a `.pgtp` passed as `argv[1]` (Windows "Edit with PGTP Editor" verb) when it is an existing file; else logs a warning"* — the app's only startup behaviour, with **no launcher, welcome screen or start page anywhere in the spec** and §7's *"startup tree is genuinely empty — no placeholder project"* left as the whole of the first-run experience | **A launch modal presenting the four ways in, and the GUI stops opening a file passed on the command line** (FQ-010). `ui/launcher_dialog.py`'s `LauncherDialog` + `show_launcher(window, settings, …, force=False)` is shown from `main.py` **after `window.show()`** behind a `launcher=` seam — never from `MainWindow.__init__` (~49 test files construct one; a modal there would hang every one), and structurally unreachable from `--mcp`, which returns before any Qt import. Four groups held as `LAUNCHER_GROUPS` of **menu-path command ids**, resolved off `ToolbarController`'s walk and dispatched by triggering the menu's **own QAction** — no second implementation of anything: (1) Open a pgtp for editing, (2) New Project / Open Project, (3) Open other files, (4) Maintenance mode = the five §11 XSD actions + §20's four re_phpgen entries only, §19's vendor-generation trio deliberately OUT (membership is the owner's *"for now"*, §29). Persisted `launcherSuppressed` "Don't show this again", made reversible by **`File ▸ Show Launcher…`** (`force=True`); Escape/close lands in the empty app and **never quits**. **`args.file` survives but only `--mcp` consumes it** (§23's default project); the GUI's open branch and the `.desktop` `%f` are deleted, and the argument's help text is reworded. A non-modal "Start" tab in `CenterStage` was the honest alternative and was **rejected by the owner** (*"Let's do a modal"*) — recorded because it needed no `main.py` seam and no test-hang risk; the modal's decisive advantage is being unmissable, which is the owner's actual complaint |
| 2026-08-07 | §7/§26: **`File ▸ Open Recent`** and the `recentFiles` QSettings store (`_RECENT_FILES_KEY`/`_RECENT_FILES_MAX = 10`, the `aboutToShow` rebuild, `recent_files`/`remember_recent_file`/`rebuild_recent_menu`, written only by `open_file` and `save_as`), plus §7's toolbar-enumeration rule *"Skipped: … the dynamic **Open Recent** submenu wholesale — its children are transient per-session file entries and must never be pinnable"* | **A documented capability WITHDRAWN, not replaced** (FQ-010, owner instruction). The submenu, the store, both writers and `tests/ui/test_open_recent.py` are deleted, and the enumeration's skip rule is deleted with them rather than left guarding a menu that no longer exists. Owner's framing: recent *files* belonged to the standalone-`.pgtp`-editor era the project has left. `recentFiles` was the **only** launch-time memory of prior work that existed (`recentProjects`/`lastProject` never existed; PHP files were never recorded), so the launcher above ships **recent-less and knowingly presents actions, not a resume list**. A `recentProjects` store — the memory a project-centric app should have, with `db/ddl_project.py::is_project_dir` already available as its validator — is a **separate, later decision** that nothing here depends on |
| 2026-08-07 | §8: bookmarks are **"session-only, per-document"**, stated as settled design and closed with *"No persistence, no list panel, no names."* — `self._bookmarks` reset to an empty set on every `setPlainText` in every editor, so reopening a project, reverting, an XSD mode switch, a re-checkout or a restart lost them all | **Persistence exists — in project mode ONLY (FQ-013), and there IS now a list surface (FQ-014).** *"No names"* stands unchanged. **Persistence:** with a §18.2 project open, bookmarks survive document reload and app restart, stored in **`<project>/.ddlproject/bookmarks.json`** — a sibling of `settings.json` inside the directory `save_settings` already registers via the idempotent `_ensure_gitignored(project_dir, ".ddlproject/")`, deliberately **not** a new key in `ProjectSettings` (personal caret furniture must not dirty the shared config the deploy pipeline depends on). Keys are **project-relative with POSIX separators** so the store survives a move/clone/sshfs remount and is portable between the Windows and Linux checkouts. Stale lines: **restore in-range, drop out-of-range silently**, no content-anchoring in v1. Identity-less editors (the read-only DDL Explorer buffer, FQ-006 draft tabs, the `Edit code…` dialog) stay session-only. Writes are **coarse** (project/app close or a debounce), never inside the hot `toggle_bookmark` gesture. **With no project open, behaviour is exactly unchanged** — session-only, no store, no file: the projectless path is the status quo by explicit decision, and the gate is *"is a project open"* (a capability fact), **not** FQ-011's launcher mode. **The list surface:** `List All Bookmarks` writes clickable `[Bookmark]` rows into the existing Audit dock for the **active editor only** — a new reserved prefix (§7), Find All's two-role payload and row grammar, its own bottom-up clear sweep, a roles-less count row and a roles-less empty-case row, no shortcut, revealing the dock through the injected `_show_audit_dock`. A dedicated bookmarks panel was **not** built: the Audit dock already is the app's list-of-locations surface with a working click router |
| 2026-08-07 | §8/§26/§27: `Select Enclosing Block` (Ctrl+Shift+B) and `Select Parent Block` (Ctrl+Shift+A) as **Edit-menu** actions described as *"Raw XML editor (menu-owned)"* — and, in the code, `triggered.connect(self.center_stage.xml_editor.select_enclosing_block)`, i.e. **bound to the widget at menu-build time** | **A three-item `Select` menu on the Editor menu bar, and the binding bug fixed with the move** (FQ-015). `Select All` (Ctrl+A) joins them as a **new menu entry for behaviour that already worked** — nothing ever bound or stole Ctrl+A, so the gap was pure discoverability. All three now resolve the target editor at **trigger** time via an `active_selection_editor()`-style dispatch mirroring `active_bookmark_editor()`, mapping to **each editor family's own method** (`XmlEditor.select_enclosing_block` selects XML tag spans; `CodeEditor.select_enclosing_brackets` selects bracket pairs — different semantics, so one name cannot be assumed). The build-time binding meant **Ctrl+Shift+B/A from a PHP tab, a DDL object tab or a draft tab acted on the Raw XML document**, and `CodeEditor` additionally handles Ctrl+Shift+B in its own `keyPressEvent` — two competing handlers for one chord, one tab-correct and one not. The spec's per-tab-dispatch rule already existed; these two actions were simply **never covered by it**. No shortcut changes |
| 2026-08-07 | §7/§26/§27: **one** menu bar, with the **Edit** menu holding project-history Undo/Redo/History…, four dead stubs, the five Find/Replace actions, the two selection commands, `Auto Parse XML` and `Preferences`; and §15's `FindReplaceBar` *"hides itself on construction … `show_find` hides the replace row while `show_replace` shows it … `Esc` hides & returns focus"*, with `Ctrl+F`/`Ctrl+R` as two different **reveal** gestures onto one widget | **TWO menu bars, the Edit menu DISSOLVED, and the Find/Replace bar PERMANENTLY VISIBLE** (FQ-016). A second, **fixed** `QMenuBar` inside a container widget becomes the central widget with `CenterStage` below it — owner's distinction, verbatim: *"that's not a toolbar, that's a menubar. Toolbar is just a collection of favourite commands."* Its four menus: **History** (`History…`, `Undo`, `Redo`), **Select** (FQ-015), **Parsing** (`Auto Parse XML` + `Validate Project` moved off Tools, gated by **active tab kind** — never called a "mode" — with the plpgsql-check member landing with §18.5 D3a), **Bookmarks** (moved off the window bar). Edit is **removed, not emptied**: its stubs are deleted (five of the seven absent-not-disabled violators die here), its Find/Replace family becomes the permanent bar's buttons, and its remaining members move. The bar is shown **expanded** at all six construction sites; `self.hide()`, the `show_find`/`show_replace` split and `Escape → hide` are **deleted, not left inert** — `Ctrl+F`/`Ctrl+R` become **focus** gestures and `Escape` returns focus to the editor; `_prefill_from_selection` must move onto the focus path or "select a word, press Ctrl+F" stops prefilling. Shortcut fallout, per key: **`F3` survives** as a **window-level shortcut with no menu entry** routed to `active_find_bar().find_next()` on the `Ctrl+L` Go To XSD precedent (and is therefore un-pinnable, like Find itself — *"Find unpinnable is fine"*); **`Ctrl+Shift+F` and `Ctrl+Alt+Return` are deleted**, their commands surviving as buttons (Replace All now sits beside FQ-017's scope dropdown, which a keystroke would bypass). `set_find_actions`/`set_find_actions_enabled` die with the QActions they gated. Toolbar identity: the **one** `ToolbarController` walk is widened to a **sequence of menu-bar roots** (never a second walk), and `LEGACY_ID_ALIASES` is updated **in the same commit** for `undo→history.undo`, `redo→history.redo` and **`validate→parsing.validate-project`** (settled 2026-08-07 by the owner's delegated authority — the fourth pinned id, which triage found late), with the now-homeless `find` alias and its `edit-find` SVG retired deliberately; otherwise default toolbar buttons ship empty and iconless. Rejected: a `QToolBar` instead (owner, verbatim), keeping `Edit` as a thin shell, and merely defaulting the bar to visible while keeping it hideable |
| 2026-08-07 | §7 (FQ-010, written earlier the same day): *"**A group choice sets the persisted launch mode** consumed by the menu-bar filter"* — the launcher described as feeding FQ-011's mode filter | **Corrected against the shipped launcher (`02e47e0`): a group choice triggers the picked entry's own QAction and nothing else.** `show_launcher` runs the dialog, persists `launcherSuppressed` on every exit path, then calls `action.trigger()` **after the modal has closed** and returns the picked command id; `launcherSuppressed` is the **only** key it writes. **No launch mode is stored and no menu-bar filter exists** — FQ-011 is deliberately unimplemented (its per-mode membership is undecided, §29), so the earlier sentence described a consumer that does not exist and put the spec at odds with the manual, which correctly refused to document the mode. FQ-011's mechanism stays recorded as **planned**, explicitly separated from what ships |
| 2026-08-07 | §7's FQ-016 row and body (written earlier the same day): `set_find_actions`/`set_find_actions_enabled` *"die … with FQ-017 **deleting the caption shortcuts**"*; the Editor bar described as shipping **four** menus (History/Select/Parsing/Bookmarks); the `find` retirement described as *"the `find` alias **and its `edit-find` SVG**"* going | **Three corrections against the shipped code (`c327c9d` + `02e47e0`).** (1) **FQ-017 did not delete the caption shortcuts — it rescoped them:** `CaptionManagementPanel` now owns `Ctrl+F`/`Ctrl+R` as **panel-scoped `WidgetWithChildrenShortcut` `QShortcut`s**. The real reason `set_find_actions*` are gone is **structural**: a *window-level* `Ctrl+F` would be **ambiguous** against those panel-scoped ones and Qt fires **neither** (it does not prefer the narrower context), so FQ-016 hosts `Ctrl+F`/`Ctrl+R` **per editor tab** through the new **`find_replace_bar.install_focus_shortcuts(host, bar)`** at all six bar sites — exactly one match live for any focus location, nothing left to gate. Side effects, both recorded as settled: `Ctrl+F` is a **no-op on tabs with no bar** (Manual, Diff/Merge) instead of revealing Raw XML (closing §29's reveal question its own recommended way), and `active_find_bar()`'s reveal now serves **F3 only**. (2) **Three menus ship, not four** — History · Parsing · Bookmarks; `Select` (FQ-015) and `List All Bookmarks` (FQ-014) are insertion points, and until FQ-015 lands **`Ctrl+Shift+B`/`Ctrl+Shift+A` are unbound** on the Raw XML editor. `Parsing`'s per-tab gating is deliberately **unexercised** (a *default* toolbar button shares the menu QAction, so gating `Validate Project` per tab would make that button appear/disappear); the whole-bar hide on the Caption/Manual tabs hides the **widget**, never the actions, for the same reason. (3) **`edit-find.svg` STAYS in the vendored Breeze catalog** and remains user-assignable — only the `find` *default* binding was retired, from `LEGACY_COMMANDS`, `LEGACY_ID_ALIASES` **and** `icons.ACTION_ICON_FILES`, making `LEGACY_COMMANDS`/`DEFAULT_TOOLBAR_IDS` **six**. Also settled with the same commit: **all three lint entries stay on Tools** (§29's split-lint question, closed) |
| 2026-08-07 | §13/§26/§27: caption find/replace exists **twice** — the non-modal `CaptionFindReplaceDialog` (`Tools ▸ Caption Filter…` plus two window-scoped, Caption-Mode-gated `Ctrl+F`/`Ctrl+R` `QShortcut`s, with Scope *In selection[default] / Global*) **and** the in-panel `CaptionFindReplaceBar`, which hid itself and closed on Escape | **The modal and its menu entry are DELETED; the bar is permanent and absorbs the missing capability** (FQ-017). Owner, verbatim: *"forget totally caption filter: delete totally the modal and the menu, keep the find and replace bar as is now, always visible, with the same logic as in editor window."* The module, its tests, its ~16 `main_window.py` references and the two `QShortcut`s go (which also retires §27's Caption-Mode override row and, with FQ-016, `set_find_actions*`); `MODE_LABELS` **moves into the panel**, its only remaining consumer. The bar keeps its **live** filtered replace and gains **`Clear filter`** (bound to the existing `clear_all_filters()`), a **scope dropdown** immediately before a new **`Replace All`** — *"in filtered results"* (default) / *"in all project"* — and loses **`Close`**. Two rulings this forces: *"in all project"* is **inert until `Replace All` is pressed** (letting the dropdown drive the live preview is rejected explicitly: one keystroke would rewrite every caption in the project, against the panel's own standing rule that project-wide must be button-pressed); and, since `on_close=commit_live_replace` can never fire on a permanent bar, **"active" is redefined as *the Find field is non-empty* and `Replace All` commits the baseline** (settled 2026-08-07 by the owner's delegated authority — otherwise `_live_replace_baseline` is never released and a hand edit of a previewed row is silently reverted by the next re-run; emptying the Find field still rolls everything back, so reversibility survives). **Selection-scoped replace is dropped on purpose** — the new scope is filter-scoped, and no `in_selection` parameter matching no on-screen control may survive. Explicitly untouched: **`Unify`** (owner's correction: whole-value propagation and substring editing are different operations, so `_confirm_unify_scope` stays as-is) and the **active-filter banner** (it also reports tree-set row predicates no text field can express; retiring it would re-create BUG-020). All **three** `mode_combo` modes stay — dropping `Extended` would be a capability removal |
| 2026-08-07 | §8's FQ-014 payload rule and §7's `[Bookmark]` prefix row (both written earlier the same day): *"**Payload: Find All's two-role shape, unchanged** — line on `UserRole`, the existing target discriminator on `UserRole+1` … this command reuses whichever discriminator the click router already understands for that editor — **no new routes, no `UserRole+2`**, no per-row editor label"* | **Corrected against the shipped router: for a PHP file tab the reused contract is BOTH halves, so `UserRole+2` IS required.** `MainWindow._on_audit_item_clicked`'s `target == LINT_AUDIT_TARGET` branch calls `self._php_tabs.navigate_to(item.data(Qt.ItemDataRole.UserRole + 2), line)` — the tab key on `UserRole+2` is *how a row says which PHP tab it belongs to* (§22's `[Lint]` contract). A `[Bookmark]` row obeying the old sentence would have been **inert in every PHP tab**: it could not navigate at all. "Reusing the discriminator the router already understands" therefore means **the whole per-branch contract**: line on `UserRole` + target on `UserRole+1` **+ tab key on `UserRole+2`** for PHP, and the two roles only for Raw XML, Edit XSD and DDL object tabs (the XSD branch's `UserRole+2` is its *mode*, left unset on purpose so a bookmark targets the schema the tab already shows; the DDL branch's target is a `DdlObjectRef.key` tuple). Implemented in `FindValidateController._bookmark_audit_route`, which returns `(target, label, extra)` and documents this at the code site. **No new routes** still holds — the correction is that one existing route has two payload slots, not one |
| 2026-08-07 | §8's FQ-013 *"Which editors persist"* list (written earlier the same day): *"those with a stable project-relative identity — DDL object tabs and PHP file tabs …, the Raw XML editor …, **and Edit XSD / Edit AutoXSD (their schema files)**"*; plus the deliberately unresolved *"**Write timing** is … project close / app close, **or** a debounce (§29 — pick one)"* | **The XSD editors CANNOT persist — they are session-only by construction — and the timing is pinned to debounce + synchronous flushes.** (1) The XSD editors' schema files live in the **app-level schema storage directory** (`XsdController.schema_storage_dir`), **not under any project**, so `bookmark_store.relative_key(project_dir, path)` returns `None` for them and `MainWindow._bookmark_file_path` deliberately returns `None`: there is no project-relative key to store them under, and **no identity is invented** (no absolute-path fallback, no synthetic id). Exactly **three** editors persist — the Raw XML editor (the open `.pgtp`, via `self._doc_ui.project_path`), DDL object tabs (`panel.save_path`) and PHP file tabs (`tab.path`) — and only while a §18.2 project is open; everything else (the XSD editors, the read-only DDL Explorer buffer, FQ-006 draft tabs, the `Edit code…` dialog) is session-only, which is a boundary, not an omission. The same rule silently covers a document opened from **outside** the project folder. (2) **Timing, both halves rather than "pick one":** a **400 ms single-shot debounce** (`_BOOKMARK_WRITE_DEBOUNCE_MS`) after a user-chosen change (`BOOKMARKS_TOGGLED`/`BOOKMARKS_CLEARED`), **plus a synchronous `_flush_bookmark_writes()`** on a project transition and in `closeEvent`, so the debounce can never be the reason a bookmark is lost; still **never** inside `toggle_bookmark`. The pending entry is `(folder, path, lines)` **resolved at change time**, so a pending write survives its tab or its project closing underneath it and the flush touches no widgets. A `BOOKMARKS_RESET` is a **restore, never a write**. Restore happens at the document load (the one moment the set is wiped — covering reopen, revert, XSD-mode switch, re-checkout and restart) plus a sweep when a project opens, for the `.pgtp`-first/project-second order in which no load event follows. `closeEvent` also unsubscribes the observer |
| 2026-08-07 | §7/§26/§27's FQ-016 statements that dissolving `Edit` **re-homed** `Select Enclosing Block` / `Select Parent Block` onto the Editor bar's `Select` menu, with the FQ-015 row (above) describing the fix as repairing the two build-time `triggered.connect(self.center_stage.xml_editor…)` bindings | **Both were briefly false in the shipped tree, and FQ-015 (`9146524`) closed the gap by REBUILDING rather than re-homing.** FQ-016 (`c327c9d`) **deleted** the two QActions with the menu while `Select` did not yet exist, so for the commits in between **`Ctrl+Shift+A` had no host at all** and `Ctrl+Shift+B` survived only through `CodeEditor.keyPressEvent` (Code Editor dialog / DDL object / PHP tabs). By the time FQ-015 ran, the two build-time `connect` lines it was chartered to fix **no longer existed** — the bug is therefore recorded as *prevented by construction* in the rebuilt menu (trigger-time `active_selection_editor()`), not as a repair. Recorded because a body statement about shipped behaviour was untrue for a window of commits; nothing about the intended design changed |
| 2026-08-07 | §7/§26 (FQ-016, earlier the same day): the Editor bar's `setVisible`-by-**active-tab-kind** seam is *"wired and waiting"*, and **§18.5 D3a's Check members** — predicate *"a DDL object editor tab is active"* — are *"the first real use of the gating seam"* / *"the first genuine capability gate"* | **`Select ▸ Select Parent Block` is the seam's first real capability gate** (FQ-015, `9146524`). `_refresh_editor_menu_affordances` now hides that one **action** when the active editor lacks the capability — `setVisible(hasattr(editor, "select_parent_block"))` over `active_selection_editor()` — so `CodeEditor` tabs (DDL Explorer, DDL object, PHP) show no entry and **Ctrl+Shift+A is dead there**, since Qt keeps a shortcut live only while its action is visible *and* enabled. Two consequences stated rather than discovered: asking the **editor** (`hasattr`) instead of enumerating tab indices classifies a future editor kind for free; and because this hides an **action**, not the bar widget, a user who pinned this command sees that toolbar button come and go with the tab — accepted here (the alternative is a button that no-ops) and still the **only** action-level hide on the bar. §18.5 D3a's Check members remain the next candidate but are no longer "first". A slot-level capability guard (`getattr(editor, "select_parent_block", None)`) is the mandatory **second belt** for programmatic and toolbar triggers, which bypass visibility |
| 2026-08-07 | §8: `XmlEditor._is_text_modifying_key` classified **any** printable `event.text()` as typing, so in read-only mode (Caption Mode) `keyPressEvent` swallowed the key and emitted `read_only_edit_attempted` | **A Ctrl/Meta chord is a COMMAND, never typing — tested after `matches(Paste)`** (FQ-015, `9146524`). `event.text()` for a Ctrl+letter chord is the bare letter on some platforms and under `QTest.keyClick` (the control character `"\x01"` on Windows/Linux), so a **read-only `XmlEditor` swallowed `Ctrl+A`** — and every other Ctrl+letter command — while flashing the read-only hint, which would have made FQ-015's `Select All` fail in Caption Mode. Ordering is load-bearing: the `Paste` test stays **first** so `Ctrl+V` keeps its hint, because that chord genuinely *is* an edit attempt. This is the §29 "verify `Select All` in read-only editors, don't assume" item paying off with a real defect |

---

## 29. Open questions

**From the 2026-08-07 UX-review batch (FQ-010 – FQ-017).** These are genuinely undecided, not
unrecorded — nothing below was invented in the body above:

- **The launch mode's per-mode menu membership is UNDECIDED, and it is the bulk of that design** (FQ-011,
  §7). Nobody has enumerated which commands each of the four modes shows; **only `Generate` in project
  mode has been named.** The mechanism (persisted key, one visibility-binding refresh entry point,
  intent-not-capability hiding as a deliberate departure) is settled; the table is not, and no table may be
  invented. Three sub-questions ride with it: **(a)** what the required **escape hatch** is and where it
  lives (a persisted mode plus a suppressible launcher is otherwise a trap; recorded recommendation: a
  default *emphasis* with a "show all commands" affordance, never a lock); **(b)** whether Customize
  Toolbar's **Available list filters by mode**, given that a hidden action is still enumerated by the walk;
  **(c)** whether hiding **`Generate PHP...`** — one of the six default toolbar buttons — in the app's
  primary mode on a fresh install is acceptable, since the toolbar hosts the menu's own QAction and hiding
  it empties the button. Also open: whether a mode affects anything **beyond** the menu bar.
- **The launcher's "Maintenance mode" group membership is explicitly open** (FQ-010, §7) — the owner said
  *"for now"* XSD + §20. `Help ▸ Open Log Folder`, `View ▸ Customize Toolbar…`, `Tools ▸ Locate PHP
  Linter…` and `Tools ▸ Start MCP Server` were raised as candidates and neither included nor ruled out.
  (Adding one is a one-line change in `LAUNCHER_GROUPS`.) Deliberately out of scope for that entry: the
  wider UX review's naming rulings, so no new vocabulary was coined for the group entries.
- **Does the Editor bar's `Parsing` menu host §18.5 D3a's `Check DDL Object` / `Check without applying`,
  overriding §26's Database-menu placement** (with **no** Database-menu twins, which would need its own
  ledger row), **or do they stay on Database?** Owner call; the recorded recommendation is the former — the
  gestures are per-tab and `Parsing` is the per-tab bar. *(The related lint sub-question is **RESOLVED**:
  all three lint entries stayed on Tools — see below.)*
- **~~Does lint follow `Lint Current File` onto `Parsing`?~~ — RESOLVED 2026-08-07 (`c327c9d`):** **no.**
  All three entries (`Lint Current File`, ☐ `Lint on Save`, `Locate PHP Linter…`) stay on **Tools**, because
  moving only the first would split lint across two bars — the exact complaint the Editor bar exists to fix
  (§26).
- **~~What does the Editor menu bar show on the Caption Management tab and on the Manual tab?~~ —
  RESOLVED 2026-08-07 (`c327c9d`):** nothing; `_refresh_editor_menu_affordances` hides **the whole bar
  widget** on both (never its actions, which a pinned toolbar button shares). Still open in the same area:
  **is `History…` acceptable on a bar otherwise made of per-tab commands?** (Recommendation: yes, and
  describe the bar as holding *editing* commands — which the body now does.)
- **~~Does `active_find_bar()`'s Raw-XML reveal survive `Ctrl+F` becoming a pure focus gesture?~~ —
  RESOLVED 2026-08-07 (`c327c9d`), in the direction this list recommended:** `Ctrl+F`/`Ctrl+R` are per-tab
  `WidgetWithChildrenShortcut` shortcuts (`install_focus_shortcuts`), so they are a **no-op on tabs with no
  bar** (Manual, Diff/Merge); `active_find_bar()`'s reveal survives only on **F3**'s fallback path. The
  FQ-017 half is resolved too (`02e47e0`): `current_filter_pattern()` seeding **survives** on the focus path
  (`focus_find` seeds only an empty field), and the grid's context-menu entry survives as **"Focus Find /
  Replace bar"**.
- **~~Bookmark persistence details to confirm~~ — RESOLVED 2026-08-07 by the shipped FQ-013 wiring**, and
  answered in §8's body: the identity-less editors stay session-only **and so do the XSD editors** (their
  schema files live in the app-level `schema_storage_dir`, outside any project, so `relative_key` returns
  `None` — the earlier "XSD persists" claim is superseded, ledger §28); **write timing is a 400 ms debounce
  plus a synchronous flush on project transition and in `closeEvent`**, never inside the gutter gesture;
  the stale-line policy is restore-in-range / drop-out-of-range with **no** content anchoring (a `version`
  bump if that ever changes). **Still open, narrowed to one question:** `prune_missing_files` is built and
  tested but has **no caller** — whether the host prunes on project open (the obvious trigger) is
  undecided, so a deleted DDL object currently leaves a dead key in `bookmarks.json`.
- **~~`Select All` in the read-only editors must be verified, not assumed~~ / ~~retire `CodeEditor`'s
  duplicate Ctrl+Shift+B handler?~~ — BOTH RESOLVED 2026-08-07 (`9146524`, FQ-015, §8):** `Select All` **is**
  live in the DDL Explorer buffer and in Caption-Mode Raw XML, now covered by tests — and the verification
  found a real defect on the way (`XmlEditor._is_text_modifying_key` classified a Ctrl chord's printable
  `text()` as typing, so a read-only editor swallowed Ctrl+A; fixed). The duplicate handler is **KEPT**:
  measurement showed the QAction wins wherever it exists (one call, not two), and the handler is the only
  host in the menu-less `CodeEditorDialog`.
- **Caption bar details to confirm** (FQ-017, §13): does **`Extended`** survive in `mode_combo` (three modes
  exist, two were named; the body keeps all three because dropping one removes a real capability), and does
  **`Clear filter`** clear only the text filter or **all** filters including the tree-set row predicates the
  retained banner describes? The existing `clear_all_filters()` does the latter while the singular label
  suggests the former.
- **Not folded in, and colliding with §26/§27:** FQ-012's *Customize Shortcuts…* dialog would recast §27's
  fixed-binding table as user-rebindable defaults and add a View-menu entry beside *Customize Toolbar…*. It
  is a separate concurrent proposal, not settled here.

- **Ability-code numeric mapping** (`*AbilityMode`): integer→label mapping still unknown; derive
  empirically. No longer blocking — powers editor hover tooltips.
- **Bundled-curated version upgrades:** shipping a newer bundled `curated.xsd` (e.g. v1.3) does **not**
  update an existing user's hand-owned `curated.xsd` — seeding is seed-only-when-absent
  (`CURATED_BUNDLED_VERSION` marks the bundled version). Whether/how to offer an opt-in re-seed or a
  merge on version bump is unresolved.
- **Create-from-table parity is not yet vendor-confirmed:** `type_map` defaults and caption humanization
  are corpus-derived; needs a golden "freshly-added table" `.pgtp` from PHP Generator to calibrate and
  re-baseline the golden fixtures.
- **re_phpgen:** caption localization (verbatim vs `Project@localizationFileName`), alias/handler counter
  numbering scheme, DataSource-schema origin (`.pgtp` vs live DB), determinism (unverified until the
  twice-generate diff runs); flag-mapping residual ambiguity; 8 parked edge pages (471/479 cap).
- **Event tag naming variants** (e.g. `_SimpleHandler` suffix) — verify normalization before matching the
  9/31 list.
- **~~Debug exclusion list / `PROFILER_ID` availability~~ — RESOLVED (shipped in `debuglog.py`):** the
  hot-path exclusion list and the seam set are implemented, and the tracer registers as
  `_TOOL_ID = sys.monitoring.PROFILER_ID` with the existing failure-safe behavior (tracer failure →
  WARNING + continue, §25). *(The former "handler body storage" entry here stated an answer, not a
  question — the fact lives in §2's storage invariants and §6's `EventNode`, and was removed from this
  list.)*
- **Fold re-scan performance** and `line_index` O(N²) — accepted for now; optimize only if profiling
  demands.
- **~~§18.4 formatter host, shortcut and audit prefix~~ — RESOLVED 2026-08-02 (§18.5):** the host is the
  DDL object editor tab (`ui/ddl_object_editor.py::DdlObjectEditorPanel`), the trigger is `Ctrl+Alt+F`
  plus a "Format Selection" context-menu item (selection-only), and refusals report under the `[SQL]`
  Audit prefix with a transient underline over the `Issue` span. §26/§27 carry the binding, and as of
  2026-08-06 **all of it is built and wired** (§18.4 status). **Still not open:** whether an auto-format mode exists — it does **not**, by explicit
  decision (§18.4).
- **~~What "Apply" writes to in a project-less v1 (§18.5)~~ — RESOLVED 2026-08-02:** **both** the
  sandbox and the target database, each its own explicit, confirm-gated gesture, through the new
  `db/apply.py` write seam; Save and Apply are separate gestures; §18.3's reviewed batch deploy stays
  authoritative when both could apply (§18.2/§18.5, ledger §28).
- **Overload-rename *timing* (§18.2):** the collision scheme itself is settled — the `_n` numeric-suffix
  filenames (ledger §28, the "*Numeric `_n` suffix instead*" row), with a mid-set addition renaming via
  `git mv` (§18.2). What survives of the original question is only *when* the tool performs that rename:
  eagerly at the next introspection, lazily at the next checkout of either overload, or only on explicit
  user confirmation — unresolved. Doing
  nothing is not an option: two overloads would otherwise contend for one path.
- **The deployment script's content model (§18.5)** — **(a) working set** (everything in the sandbox's
  `applied` table; already available, needs no extra connection, but may carry no-op statements for
  objects the user touched then reverted, and **cannot see production changing underneath the user**) vs.
  **(b) true diff against production at generate time** (`diff_schemas(sandbox, production)` — exactly
  the delta, catches drift by construction, at the cost of one extra read-only introspection). The
  mandatory pre-generate drift check is specified either way, which buys (b)'s single real safety benefit
  at a fraction of its scope; and because `diff_schemas` is written source-agnostic, switching is a
  one-line change at the call site. **Unresolved — and whichever way it goes, the script header must
  state which model produced it.**
- **Transaction-wrapping the generated deployment script (§18.5)** — PostgreSQL has transactional DDL, so
  `BEGIN; … COMMIT;` around the whole script makes deployment atomic, a very strong property for exactly
  this use case. But it changes how the user's own deploy tooling must invoke it. Candidate: emit the
  `BEGIN`/`COMMIT` pair **commented out** in the header with a one-line explanation and let the user
  choose. **Nobody has actually made this decision.**
- **~~Execution against the sandbox (§18.5)~~ — RESOLVED 2026-08-06 by owner decision (§18.5 D4, ledger
  §28).** It is **folded in, not deferred**, and it is **not a new ladder tier**: D3's four tiers are
  unchanged, and execution is a separate *surface* — the **Sandbox SQL Console**, one dynamic center tab
  pairing `CodeEditor(language="sql")` with `ui/sql_results_panel.py`, backed by the Qt-free
  `db/sandbox_query.py`. The same pass pinned the **run contract for `plpgsql_check` itself** (D3a), so
  the two halves of *"the difference between a validator and an IDE"* — semantic analysis with results,
  and actual execution with results — are both specified. The 2026-08-05 three-modes taxonomy's tier-3
  row now names this capability instead of pointing here. **Settled and no longer open:** sandbox-only
  execution enforced structurally (`run_sandbox_query(session, …)`, never `ConnectionParams`); a
  1 000-row cap with a first-class `truncated` flag; a mandatory 30 s statement timeout; one committing
  transaction per Run; the object-change confirmation; and results reporting into the console's own panel
  rather than a fourth Audit prefix. **What remains open is listed as its own item below (cancellation).**
- **§18.5 D4 — cancelling a running statement.** There is **no Cancel button in v1**, stated rather than
  faked: cancelling needs `connection.cancel()` on a handle held by another thread, and every
  `SandboxExecutor` implementation opens **one connection per call** and closes it itself, so no handle
  survives to cancel. The mandatory statement timeout is the control in its place. Revisit if a
  persistent-connection executor is ever introduced — which would itself be a design change (the
  per-call-connection shape is what keeps the executor trivially fake-able in tests).
- **§18.5 D4 — a read-only *production* query surface is NOT authorized by D4 and is not designed.**
  Recorded here only so the omission reads as deliberate: D4's boundary is sandbox-only because the
  sandbox is `reset()`-able, and "but read-only queries are harmless" is exactly the generalization D4
  forbids an implementer from making on its own. If it is ever wanted, it needs its own design pass, its
  own gating and its own ledger row — it does not arrive by widening `run_sandbox_query`.
- **§18.5 D4 — persistence of console buffers.** Not designed: whether the console tab's SQL text
  survives an app restart (or a project close), and whether a per-project history of executed statements
  is kept. v1's assumption is **no persistence at all** — the tab is session-only, like the object tab's
  unattached-trigger association — but this has not been owner-confirmed.
- **~~Where the tier-2/tier-3 (quality-project vs. development-project) environment-capability check
  runs~~ — RESOLVED 2026-08-05 (top of §18):** the probe (reusing §18.5 D2's `SandboxCapabilities.probe`)
  runs automatically on every project **open** (so a sandbox that died between sessions correctly degrades
  the project to quality-project mode for that session) and again on demand whenever the **Project Status
  window (§18.8, RESOLVED 2026-08-05 — see below)** is brought up — it is not cached from creation time.
  The `pg_dump`/`pg_restore`-on-`PATH` sub-question is also resolved, by the shipped `db/sandbox.py`:
  the check is **folded into the same probe** (`SandboxCapabilities.pg_dump_path`/`.pg_restore_path`,
  filled via the injectable `which=shutil.which` seam), and `require_data_clone_tools` re-checks
  namedly at clone time.
- **~~The "Project Status" window/screen — layout and behavior~~ — RESOLVED 2026-08-05 (§18.8), corrected
  same day to a 5-node model:** the window is a small node-and-connector diagram, read as a horizontal
  chain: **quality → app → sandbox → (sandbox1 / sandbox2)**, the last connector splitting after the
  sandbox node. The **app node is now project-tier-only, 3 states** (`app_standalone` /
  `app_project_not_setup` / `app_project_setup`), a corrected reading of a first pass that had wrongly
  conflated project tier and sandbox connectivity into one 4-state `app_*` node. Sandbox connectivity is
  now its own **new, distinct node** (`sandbox_*`: not-set-up / connection-ok / offline /
  connected-but-tools-missing), with sandbox1/sandbox2 unchanged in meaning (data-fill status;
  `plpgsql_check` capability respectively). The sandbox node, sandbox1, sandbox2, and their connectors
  remain **absent** (not disabled) whenever no sandbox is configured at all. **Still open, and the reason
  this item is not fully closed:** the App node's action-window contents/behavior is **NOT designed** and
  must not be invented — a further owner pass is needed. (Quality/Sandbox/Sandbox1/Sandbox2's
  click-through *patterns* are now specified: Quality opens a connection-info+reconnect window; Sandbox
  opens a status/help window naming the missing tool when degraded by missing `psql`/`pg_restore`;
  Sandbox1/Sandbox2 open a two-step status+help window with an embedded action button, e.g. "run data
  clone now" / "install the plpgsql_check extension" (Sandbox2 is an install-state marker, not a lint
  pass/fail result — only the App node's action window is unspecified.)
  Sandbox1/Sandbox2's embedded action buttons are **specified but deliberately not offered yet** — they
  need a live `SandboxSession` no UI can create until §18.5's sandbox lane lands, so `MainWindow` passes
  `None` for both callbacks and the panel hides them (§18.8). The window's **entry point is settled and
  shipped: Database ▸ Project Status…, no shortcut** (§26/§18.8).
  The connector-state question is **resolved** (2026-08-06, ledger §28): connectors shipped
  **stateless and position-keyed** (`ConnectorKind`, one asset each), so no per-connector state set
  remains to enumerate. Still unspecified: the
  Sandbox node's tools-missing help-section content/deep-link mechanism (verified: the app's only
  existing help surface, the in-app manual §24, has no topic-anchor/deep-link mechanism today — both are
  new work) — left as either a future spec detail or an implementation detail per §18.8.
  **Implementation note:** `ProjectTier`
  (`pgtp_editor/db/sandbox.py`) is a 2-member enum (`QUALITY`/`DEVELOPMENT`) with no tier-1 member at
  all — the corrected 3-state App node's `app_standalone` state must be derived from "no project is
  currently open," a fact outside `ProjectCapabilityStatus` itself, not from a third enum member; no
  code change is required, but the window's App-node rendering logic needs this explicit check (§18.8).
  **Added 2026-08-05, concrete per-node state list from the owner's reference images (§18.8):** three
  further small gaps, none blocking, all flagged rather than invented:
  1. **Quality node — RESOLVED 2026-08-05, no longer an open gap.** The locked/gray icon is
     `quality_connection_not_set_up`, not a distinct auth-failure mode alongside a general error state —
     it means the quality/target connection is simply not configured yet, the same semantic category as
     the Sandbox node's `sandbox_not_set_up`. The Quality node's 3 states are therefore `not_set_up`
     (locked/gray) / `error` (red, connection attempted but failed) / `connection_ok` (green), mirroring
     the Sandbox node's not_set_up/offline/connection_ok pattern exactly.
  2. **Sandbox1 — no "in-progress"/"clone-failed" icon provided.** Sandbox1 (data-fill) shows only 2
     states in the reference images (not-filled, filled) with no distinct "clone in progress" or "clone
     failed" icon. Flagged for owner confirmation, not invented here.
  2a. **Sandbox2 — corrected 2026-08-05, no longer an open gap.** The earlier note here speculated about
     a missing "not-yet-run" icon, on the mistaken premise that Sandbox2 was a `plpgsql_check` pass/fail
     result. It is actually an **install-state** marker (`sandbox2_plpgsql_check_installed` /
     `sandbox2_plpgsql_check_not_installed` — is the extension installed in the sandbox, not whether a
     routine passed a lint check; that per-object result lives in the DDL object editor's Audit panel,
     §18.5 D3). There is no "run" to be pending, so no third icon is missing. **What remains genuinely
     open:** `SandboxCapabilities.plpgsql_check_state` is 4-valued (`installed`/`installable`/`absent`/
     `unknown`) while this node has only 2 icons; collapsing `installable`/`absent`/`unknown` onto the
     single `not_installed` icon is a reasonable implementation default but is not owner-confirmed (§18.8
     reuse map).
  3. **Dark-mode asset convention — confirmed reuse, not a new mechanism; shipped.** Every image asset
     gets a `_drk`-suffixed dark-theme counterpart (`quality_connection_ok.svg` /
     `quality_connection_ok_drk.svg` — `.svg`-only per BUG-029, resolved through
     `ui/project_status_model.py::asset_filename(stem, dark)`). The app's theme selection is the existing user-toggled
     **Light Theme** menu checkbox (`ui/theme.py::apply_theme`, `MainWindow._light_theme_action`) — there
     is no OS/system dark-mode *detection* anywhere in `pgtp_editor/` today. The `_drk`-vs-plain asset
     choice should key off this existing toggle's boolean state, not a new detection mechanism; this is
     recorded as confirmed-available reuse, not a gap, but is called out here because it was easy to
     mistake for requiring new OS-theme-detection capability.
- **`db/routine_refs.py`'s UI consumer (§18.1's remaining gap)** — XML↔routine cross-referencing,
  answering *"which `.pgtp` pages break if I change this function?"* before a deployment script is
  generated. **No other tool can do this**, and it is the XML↔DB sync the owner describes as the point
  of the app (§1). The pure layer is **no longer the open part**: `db/routine_refs.py` shipped (commit
  `956e8fb`, tested — `RoutineReference` with `breadcrumb`/`ref_type`, `RoutineUsage` with the overload
  `ambiguous` flag, `collect_routine_references`/`routine_reference_index`, §18.1). What remains
  undesigned is the **UI consumer**: which surface presents the usages (a `BrowserPanel` sub-branch,
  the Properties panel, §17's coherence view, …) and drives the cross-buffer `EditorPanel`-tab →
  Raw-XML-tab navigation. Nothing in `ui/` calls the module yet; a strong candidate for the next
  design pass.
- **Project-relative paths when the folder moves (§18.2).** *(Narrowed 2026-08-03: the merged project
  JSON now holds the connection profiles directly, so the QSettings-key portion of this question is
  largely moot for project-scoped connections — see §18.2's "Path computation"/"Project settings"
  material for the reconciled reading. The migration-convenience question below is what remains.)* Since
  the project's own connection profiles now live inside `.ddlproject/settings.json`, a copied/moved
  project folder carries its connection profiles (including password) with it automatically — self-
  contained by construction. Still unresolved: (a) whether a **non-project-scoped** `ProfileKey` slug
  migration path is worth keeping for any transitional QSettings-backed profiles that predate this
  revision (probably not, since nothing has shipped yet); (b) whether the optional `.pgtp` link inside
  the JSON is stored relative to the project root or absolute (relative survives a folder move without
  edits; absolute is simpler to implement first).
- **§18.5 D2a — `pg_dump`/`pg_restore` invocation details — largely ANSWERED by the shipped
  `db/sandbox.py`:** binaries are found on **`PATH` only**, via the injectable `which=shutil.which`
  seam (`probe` / `require_data_clone_tools`) — no configurable binary location shipped; the dump
  format is pinned to **`--format=custom`** (`clone_data`); and the on-`PATH` check is folded into the
  capability probe (`SandboxCapabilities.pg_dump_path`/`.pg_restore_path`), with
  `require_data_clone_tools` failing namedly at clone time. Still open: whether large-database cloning
  needs a progress indicator beyond
  the existing `busy_status` spinner, and whether/how a version mismatch between the target server's
  `pg_dump` requirements and the binary found on `PATH` is detected and reported. Flag back to the user
  rather than guess.
- **§18.7 — sandbox destroyed/reset while its DDL Explorer instance is open.** Not designed: whether the
  sandbox-scoped DDL Explorer tab and dock auto-close, show a stale/error state, or require the user to
  manually reopen after a `SandboxSession.reset()` or a sandbox-connection removal. Left as an open
  question in §18.7 rather than guessed at.
- **§18.5 "Deploy this edit…" — exact picker UI.** Not designed: whether the 3-way destination choice is
  presented as a small modal dialog with three buttons, a `QMenu` fly-out, or another idiom; this is
  deliberately left to the implementation as long as it (a) is not a keyboard shortcut and (b) delegates
  to the three existing gestures' own wiring/confirmations rather than reimplementing any of them.

---

## 30. Testing policy

(Authoritative in [`CLAUDE.md`](../../CLAUDE.md); summarized here.)

- Every completed feature triggers the **`feature-tester`** agent and produces a `docs/TEST_LOG.md`
  entry (append-only, newest at top). A feature without a green feature-tester run + log entry is not
  done.
- **The interpreter is platform-dependent — confirm by import check, never assume.** On Windows the
  project is typically installed editable into the **system `python`** (the repo `venv\` is a bare
  leftover without pytest); on Linux it is the reverse — the repo's **`venv/bin/python`** carries
  pytest/pytest-qt/pytest-xdist and the system `python` does not. Use whichever
  `… -c "import pytest, PySide6"` succeeds.
- Qt runs headless via **`QT_QPA_PLATFORM=offscreen`**, and the **full suite runs in parallel with
  `-n 10`** (pytest-xdist, ~2.5 min) — serial runs take ~8 min and can produce spurious per-test
  pytest-timeout failures that do **not** reproduce under `-n 10`; never diagnose those as regressions,
  re-run in parallel first. PowerShell: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q -n 10`;
  bash/zsh: `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q -n 10`. Never pipe a suite run
  through `tail` (it discards the failing test's name) — filter with `grep -E "passed|failed|^FAILED"`.
- Tests mirror the package: `pgtp_editor/<area>/foo.py` → `tests/<area>/test_foo.py`.
- **Never let a test reach an un-patched modal Qt call** (`QDialog.exec`, `QMessageBox.*`,
  `QFileDialog.*`, `QMenu.exec`) — monkeypatch them. Widgets expose test seams (`selected_ids`,
  `set_params`, `changed_edits`, `filter()`/`replace_all()`, `_history_jump`, `confirm=`, injectable
  `runner=`/`opener=`/config dirs) precisely so tests drive logic without modal loops.
- Real-sample tests skip gracefully when the git-ignored sample files are absent.
- The self-diff regression guard (`diff_project(m, m) == []`) and byte-for-byte round-trip
  (load→save→diff) must stay green — they protect the master serialization invariant.

---

## 31. Maintenance protocol

This document is maintained by the **`spec-maintainer`** agent (`.claude/agents/spec-maintainer.md`),
which has two duties:

1. **Keep this file in sync — it is the single write target for specification content.** Whenever a
   design decision is **settled** (a new feature designed after brainstorming, an intentional change to
   an existing feature, or a shipped feature that diverges from what this document says), the agent
   writes it **directly into this file** using latest-wins reconciliation — from the dispatching prompt,
   the feature's plan under [`docs/superpowers/plans/`](plans/), and the changed code — updates the
   affected section(s), and appends a row to the [Supersession Ledger](#28-supersession-ledger) for any
   override. It never leaves two contradictory statements in the body.
   **`docs/superpowers/specs/` is frozen historical record:** no new dated spec files are ever created
   there and the existing ones are never edited; they are read only for rationale and to back the
   ledger's evidence (per [`CLAUDE.md`](../../CLAUDE.md)).
2. **Gate brainstorming.** Whenever brainstorming runs for a new idea, the agent first locates where the
   idea belongs in this spec — flagging any existing feature that already covers most of it and any
   near-duplicate that should be *extended* rather than *forked*. The goal is cohesive, complex features
   over parallel functionalities that differ only marginally; the up-front design cost is deliberately
   accepted to avoid the larger cost of building then correcting/overwriting redundant work.

When editing: change the body to reflect the new decision, move the old decision into the ledger (do not
leave it in the body), update `Last synthesized`, and keep section numbers/anchors stable where possible.
