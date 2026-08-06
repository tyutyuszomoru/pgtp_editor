# UX consistency dossier — PGTP Editor

Survey 2026-08-07, tree at `4c40c66`. Evidence is `file:line` against real code, not the spec.
Read-only survey; nothing was changed. **40 findings: 10 high, 23 medium, 7 low**, plus 7 items
judged defensible as-is and 6 load-bearing constraints (§L) that constrain any rename.

Procedure for acting on this: owner asks → answer from the codebase → plan → `feature-triage`
entry → once settled, `spec-maintainer` per decision, then `spec-harmonizer` as a final sweep.

---

## Decide these first

Six rulings. Each, made once, settles a large block.

1. **Capitalisation rule for commands.** Title vs sentence case is a coin-flip, sometimes for *one
   gesture*: `Deploy this edit…` (button) vs `Deploy This Edit…` (menu); `Open sandbox session`
   (dialog button) vs `Open Sandbox Session` (menu). Settles ~20 items. **Safe** — the toolbar id
   slugger lowercases (`toolbar_registry.py:86`).
2. **One ellipsis character, one meaning.** Both `...` and `…` are live, sometimes adjacent:
   `Manage Captions...` directly above `Caption Filter…` (`main_window.py:3512-3514`). Proposed rule:
   `…` (U+2026) only, and only where a dialog/prompt opens before acting. Settles ~14. **Safe** —
   slugger strips trailing ellipsis of either form (`toolbar_registry.py:78`).
3. **One word for the non-sandbox database.** "Target" in Project Settings and the DDL editor,
   "Quality database" in Project Status, "quality" in the owner's speech. Settles ~15.
   **Partly load-bearing — see §L1.**
4. **The check-family vocabulary.** Four verbs (`Validate`, `Verify`, `Check`, `Lint`) for four related
   acts, plus three sandbox gestures whose names don't say what they do. Settles ~12 and is what
   caused the 2026-08-07 incident. **Renaming here is load-bearing — see §L2.**
5. **Audit-prefix rule.** Nine prefixes are live (not seven), and the real, undocumented rule is
   *"which run may clear my rows"*, not *"what kind of problem this is"*. Settles ~10.
6. **Where deploy lives and how it is gated.** `File ▸ Deploy .pgtp` writes irreversibly with **no
   confirmation at all**; `Database ▸ Deploy This Edit…` is gated four ways. Meanwhile
   `Tools ▸ Apply Changes to Target` uses "Target" for a *file*. Settles ~6 and is the highest-risk
   block here.

---

## A — Menu placement

### A1. Current inventory (from `_build_*_menu`, in order)

**File** (`main_window.py:1328`) — `Open...` (Ctrl+O) · `Open Recent ▸` · `Open PHP File…` · ─ ·
`New Project…` · `Open Project…` · `Close Project` · `Project Settings…` · `Deploy .pgtp` · ─ ·
`Save` (Ctrl+S) · `Save As...` (Ctrl+Shift+S) · `Revert` · `Close` (Ctrl+W) · ─ · `Exit`

**Edit** (`:1388`) — `Undo` · `Redo` · `History…` · ─ · `Cut`\* `Copy`\* `Paste`\* `Delete`\* · ─ ·
`Find...` (Ctrl+F) · `Find Next` (F3) · `Find All` (Ctrl+Shift+F) · `Replace...` (Ctrl+R) ·
`Replace All` (Ctrl+Alt+Return) · ─ · `Select Enclosing Block` (Ctrl+Shift+B) ·
`Select Parent Block` (Ctrl+Shift+A) · ─ · `Auto Parse XML` ☑ · ─ · `Preferences...`\*
(\* = stub → "Not yet implemented")

**View** (`:1462`) — `Project Tree` ☑ · `Properties Panel` ☑ · `Audit/Problems Panel` ☑ ·
`Raw XML Panel` ☑ · ─ · `Expand All` · `Collapse All` · ─ · `Light Theme` ☑ · ─ · `Customize Toolbar…`

**Schema** (`xsd_controller.py:192`) — `Edit XSD` · `Edit AutoXSD` · `Verify XSD` · `Export XSD` ·
`Import XSD` (+ `Go To XSD` Ctrl+L, window-level, **no menu entry**)

**Database** (`:1783`) — `Connection Setup…` · ─ · `Database/XML Coherence` ☑ · ─ · `DDL Explorer` ☑ · ─ ·
`New Function/Procedure…` · ─ ─ *(two consecutive separators, `:1818-1819`)* · `Sandbox SQL Console…`ʰ ·
`Open Sandbox Session`ʰ · `Close Sandbox Session`ʰ · `Check Object in Sandbox`ʰ ·
`Check Object Without Applying`ʰ · `Deploy This Edit…` · ─ · `Sandbox Setup…` · ─ · `Project Status…`
(ʰ = created hidden, revealed by `_refresh_sandbox_affordances`)

**Tools** (`:3510`) — `Manage Captions...` · `Caption Filter…` · ─ · `Validate Project` · ─ ·
`Lint Current File` · `Lint on Save` ☑ · `Locate PHP Linter…` · ─ · `Reparse Raw XML into Tree` · ─ ·
`Compare / Merge Two Files...` · `Next Difference` · `Prev Difference` · `Apply Changes to Target` · ─ ·
`Start MCP Server` ☑

**Bookmarks** (`find_controller.py:245`) — `Toggle Bookmark` (Ctrl+F2) · `Next Bookmark` (F2) ·
`Previous Bookmark` (Shift+F2) · ─ · `Clear All Bookmarks`

**Generation** (`generation_controller.py:200`) — `Locate PHP Generator Executable...` · ─ ·
`Generate PHP...` · ─ · `Open Output Folder` · ─ · `Locate panGen Runtime...` ·
`panGen (Generate Own PHP)` · `rePHPgen (Analyze Gap)` · `Save reJSON...`

**Help** (`:3624`) — `Manual` (F1) · `Open Log Folder` · `About`

### A2. Tools is a grab-bag — HIGH
`main_window.py:3510-3560` holds five unrelated families: captions, project validation, PHP lint, an XML
reparse, a whole diff/merge suite, an MCP toggle. Nothing about "Tools" predicts any of them.
**Recommend:** promote Captions to top-level (it is a full mode with its own panel, find bar and
shortcuts) or move under Edit; move the four diff/merge entries to a `Compare` menu or File;
`Reparse Raw XML into Tree` belongs beside `Edit ▸ Auto Parse XML` (`:1453`) — manual and automatic form
of one act, currently two menus apart; `Start MCP Server` → Preferences once that stub is real (the code
already says so, `:3547-3555`).

### A3. Lint spans two menus, one of them wrong — MEDIUM-HIGH
`Tools ▸ Lint Current File / Lint on Save / Locate PHP Linter…` (`:3528-3532`) but
`File ▸ Open PHP File…` (`:1345`) — one feature, two places. Worse, `Lint Current File` sits under
`Validate Project` because the code reasons they are "the same kind of gesture one tier down"
(`:3524-3526`) — a developer's taxonomy, not a user's.

### A4. The sandbox block is ordered backwards from the workflow — HIGH
`:1822-1896`. Six items with **no internal separators**, and `Sandbox Setup…` — the only entry point that
can *create* a sandbox (its own comment, `:1881-1886`) — is visually **last**, below the five things that
need it to exist. With no sandbox, five are hidden, so the user sees `Deploy This Edit…` floating alone
above `Sandbox Setup…`.
**Recommend:** `Sandbox Setup…` → ─ → `Open/Close Sandbox Session` → ─ → the two checks → ─ →
`Sandbox SQL Console…` → ─ → `Deploy This Edit…`. Four groups: lifecycle / verify / explore / ship.

### A5. Two consecutive separators — LOW
`:1818` and `:1819`. A removed item's tombstone. Delete one.

### A6. `Connection Setup…` is stranded — MEDIUM
`:1789`. Projectless-only; with a project open it is disabled and its equivalent lives in
`File ▸ Project Settings…` (`:1745-1760`, `:1918-1929`). So Database's *first* entry is dead in the app's
primary mode, and `_prompt_missing_connection` (`:1735`) already has to branch and redirect.

### A7. `Project Status…` (Database) vs `Project Settings…` (File) — MEDIUM
Near-identical names, different menus, and Status shows the connection health that Settings configures.

### A8. `New Function/Procedure…` alone in Database — LOW, defensible
`:1817`. Its comment explains the asymmetry honestly (`:1814-1816`): routines are unscoped, triggers need
a table. Reasoning holds — but see D3.

### A9. `Go To XSD` has a shortcut and no menu entry — MEDIUM
`xsd_controller.py:209-213`. Ctrl+L works, appears in no menu, and therefore can never reach Customize
Toolbar (`_all_menu_commands` walks the menu bar).

---

## B — Naming

### B1. Same gesture, two capitalisations — HIGH

| Gesture | Sentence case | Title case |
|---|---|---|
| Deploy picker | button `ddl_object_editor.py:1310`; context `:824`; docstrings `:44,94,514,651,871,1202` | menu `main_window.py:1877`; dialog title `ddl_object_editor.py:1272`; status `main_window.py:3437` |
| Open a session | `"Open sandbox session"` `sandbox_setup_dialog.py:414` | `"Open Sandbox Session"` `main_window.py:1838` |
| Data clone | `"Re-run data clone"` `:403`; `"Run data clone now"` / `"Redo data clone"` `project_status_panel.py:1080` | — |
| Re-probe | `"Re-check sandbox"` `:246`; `"Re-check"` `project_status_panel.py:607` | — |

Buttons overall: `Find All`, `Add Row`, `Save Migration As…`, `Apply to Sandbox` (Title) vs
`Clear filters` (`coherence_panel.py:229`), `Select all`, `Create a sandbox database for me`
(`sandbox_setup_dialog.py:462`), `Reset sandbox` (`:408`), `Provision sandbox` (`:452`),
`Install plpgsql_check` (`:428`) (sentence).

### B2. The tree context menu is written in a different style — MEDIUM
`project_tree.py:169,173,223,227,240,244` — `Jump to page xml`, `Select detail xml`,
`Jump to column visibility in xml`: lower-case "xml" where the rest of the app says `XML`. Same file
`:178,231,248` — `See database table in caption mode` while the indicator reads
`Caption Mode (XML read-only)` (`main_window.py:1650`). Densest single cluster.

### B3. quality / target / Quality database — HIGH
Both words are on screen simultaneously in different windows:
- `"Quality database"` — Project Status node title + detail heading, `project_status_panel.py:141`, `:1000-1001`
- `"Quality project"` — tier caption, `:155`, and `"Tier 2 — quality project: …"` `:177`
- `"the quality database's data"` — `:1065`
- `"Target connection"` — Project Settings group box, `project_settings_dialog.py:97`
- `"Apply to Target…"` — `ddl_object_editor.py:1323`, `:823`
- **`"the target ('quality') apply lane…"` — `ddl_object_editor.py:119`.** This string glosses one word
  with the other. That is the finding in one line.
- `"With data (clone the target's rows)"` `sandbox_setup_dialog.py:443` vs
  `"a copy of the quality database's data"` `project_status_panel.py:1065` — same clone, two words.

### B4. "target" means three things, two of them dangerous — HIGH (safety)
- `Tools ▸ Apply Changes to Target` (`main_window.py:3544`, `diff_merge_controller.py:243`) writes to
  **another `.pgtp` file**.
- `Apply to Target…` in a DDL tab (`ddl_object_editor.py:1323`) writes to the **live production database**.

Two menus apart, which is the only reason it has not bitten yet.
**Recommend:** rename the diff/merge one (`Apply Checked Changes to the Other File`) and reserve
Target/Quality for the database.

### B5. Four verbs for the check family — HIGH
`Tools ▸ Validate Project` · `Schema ▸ Verify XSD` · `Database ▸ Check Object …` ·
`Tools ▸ Lint Current File`. All four inspect something the user has and report into the same Audit dock.
The prefixes then add a fifth label (`[Validate]`, `[Schema] VERIFY`, `[Check]`, `[Lint]`).
**Recommend:** one verb — `Check` — scoped by object: `Check Project`, `Check Schema (XSD)`,
`Check This PHP File`, plus B6. If four verbs stay, the manual must state the rule; it does not.

### B6. Three sandbox gestures whose names mislead — HIGH (the 2026-08-07 incident)

| Label | Where | What it does |
|---|---|---|
| `Apply to Sandbox` | `ddl_object_editor.py:1320`, `:821` | full ladder AND **commits** |
| `Check Object Without Applying` | `main_window.py:1863`, handler `:3408-3421` | full ladder, **commits nothing** |
| `Check Object in Sandbox` | `main_window.py:1852`, handler `:3396-3406` | **compiles nothing** — reads what is already there; tier 1 `unavailable`, tier 2 bookkeeping only |

Names sort by *mechanism*; users sort by *question*. The most inviting label is the only one that cannot
answer "would this compile?" — exactly the trap that produced two `unavailable` messages.
**Recommend:** keep `Apply to Sandbox`; rename the probe to something like
`Compile Check (Nothing Is Kept)` so it reads as the obvious first choice; move the word "Check" off
`Check Object in Sandbox` entirely (e.g. `Inspect the Applied Version`).

### B7. Dock titles ≠ their View-menu toggles — MEDIUM
`"Properties"` (`main_window.py:423`) vs `Properties Panel` (`:1478`) · `"Audit / Problems"` (`:313`) vs
`Audit/Problems Panel` (`:1485`) · `Raw XML` tab vs `Raw XML Panel` (`:1492`) · `Project Tree` ✅ (`:257`,
`:1470`). Prose adds a third form, `"Audit / Problems panel"` (`generation_controller.py` ×4).

### B8. Same act, two labels — MEDIUM
`Clear filters` (`coherence_panel.py:229`) vs `Clear all filters` (`caption_management_panel.py:1539`) —
and `coherence_panel.py:218-220` explicitly says the two banners should look the same wherever met ·
`Re-check sandbox` vs `Re-check` · three data-clone labels · `Edit ▸ Find...` vs the caption panel's
`Find / Replace bar` (names a *widget*, not an act).

### B9. Dialog titles vs their commands — LOW-MEDIUM
`Connection Setup…` → `"Database Connection Setup"` (gains two words) · `Caption Filter…` → title varies
by mode. Rule: title == command minus the ellipsis.

### B10. Tab titles — LOW
All Title Case except `"Deploy manifest"` (`project_settings_dialog.py:204`), beside `Connections` /
`General` / `Git`.

### B11. Generation labels — LOW, defensible
`panGen (Generate Own PHP)`, `rePHPgen (Analyze Gap)` — proper noun + gloss is the right pattern.
`Save reJSON...` lacks a gloss.

---

## C — Wording

### C1. Nine Audit prefixes, and the real rule is not the guessable one — HIGH

| Prefix | Owner | Meaning |
|---|---|---|
| `[Check] ` | `ddl_object_editor.py:92` | the §18.5 validation ladder |
| `[Find] ` | `find_controller.py:111` | Find All rows |
| `[Validate] ` | `find_controller.py:114` | tier-2 project validation |
| `[Lint] ` | `lint/findings.py:54` | PHP lint |
| `[PHP] ` | `generation_controller.py:105` | PHP **generator** output — not lint |
| `[Schema] ` | `xsd_controller.py:99-103,228` | XSD learning + Verify XSD |
| `[SQL] ` | `main_window.py:119` | SQL **formatter refusals** only |
| `[Sandbox] ` | `main_window.py:133` | sandbox controller operations |
| `[Project] ` | `ddl_project_controller.py:382,472,545,584,601,606,609,613`; `main_window.py:2471,2765` | project notices — **no constant**, typed inline ten times |

The rule that exists is a **clear-scope tag**: only three are read back, via `startswith`, so each feature
can clear its own rows — `find_controller.py:505`, `:515`, `generation_controller.py:261`. `[Lint]`
additionally routes clicks (`lint/findings.py:57-60`).
**Recommend:** rename the two actively misleading ones (`[PHP]` → `[Generate]`, `[SQL]` → `[Format]`);
give `[Project]` a constant; document the set as "which feature produced this line". **See §L3.**

### C2. Audit line grammar differs per prefix — MEDIUM
`[Validate] ERROR line 12: msg` (`find_controller.py:539-543`) · `[Check] ERROR line 12: msg`
(`main_window.py:2929-2932`) · `[Lint]` adds `OK:` / `NOT RUN:` / `note:` — upper case beside lower case
in one family (`lint/findings.py:246-314`) · `[Schema] VERIFY line 12:` plus `NEW ELEMENT:` /
`ENUM OVERFLOWED:` (`xsd_controller.py:99-103,635`) · `[Sandbox]` / `[Project]` carry free prose, no token.
**Recommend:** `[Tag] LEVEL line N: message`, LEVEL always upper case from a fixed set; retire `note:`
for `INFO:`.

### C3. Status-bar messages have no style — MEDIUM-HIGH
- Terminal period inconsistent: `"Project closed."` / `"Validation passed — no issues."` vs
  `"Opened {path}"` / `"Saved {path}"` / `"Generation succeeded"` / `"panGen finished"`.
- `"Opened {path}"` **and** `"Opened: {path}"` both exist (`pgtp_document_controller.py`).
- Three "saved" formats: `"Saved {path}"`, `"Saved {path.name}"`, `"Saved as {Path(path).name}"`.
- Four phrasings of one precondition: `"Open a project first."` / `"Open a project to validate."` /
  `"Open a project before generating."` / `"No project open."`.
- `"Lint: no custom-PHP tab is active"` uses a `Feature:` prefix style found nowhere else, no period,
  and does not say what to do — contrast the good pair at `main_window.py:3437`/`:3441`.
**Recommend one rule:** sentence, terminal period, name the object, state the outcome; if the user must
act, name the gesture. Basename not full path. One constant for the "open a project" case.

### C4. `REASON_*` — voice excellent, remedy coverage not uniform — MEDIUM
`db/ddl_check.py:125-250`, `:1734-1820`, `db/sandbox.py:1174-1189`. **The voice is the best string set in
the app** — lower-case fragment completing "unavailable: …", always naming what was *not* verified, never
letting silence read as clean. Do not restyle.

Has a remedy: `REASON_TIER0_NO_SANDBOX` `:157` · `REASON_OBJECT_ABSENT` `:224` ·
`REASON_NOT_INSTALLED` `:212` + `REASON_INSTALL_LOCATIONS` `:203` · `REASON_NOT_IN_WORKING_SET` `:1741` ·
`_REASON_ABSENT` `sandbox.py:1184` · `REASON_REQUIRES_SUPERUSER` `:1179`.
Lacks one: `REASON_NO_NOTICE_CHANNEL` `:133` · `REASON_UNKNOWN_CAPABILITY` `:216` ·
`REASON_RELATION_ABSENT` `:232` · `REASON_TRIGGER_FUNCTION_UNKNOWN` `:238` ·
`REASON_WORKING_SET_UNREADABLE` `:1748` · `_REASON_COULD_NOT_PROBE` `sandbox.py:1189`.
Borderline: `REASON_TIER_NOT_BUILT` `:125` (explains, does not instruct) · `REASON_NOT_REACHED` `:141`
(defensible — remedy is visible in the same report).
**Recommend:** rule that every unavailable reason ends with a remedy **or an explicit "nothing you can do
here"**. Two of them genuinely have no user remedy; say so rather than trailing off.

### C5. Three live strings name a command that does not exist — HIGH
`ddl_object_editor.py:123`, `:1107`, `:1146` all send the user to **`Database ▸ Compare Schemas…`**:
the reason Apply-to-Target is unavailable, and both signature-refusal messages. **No such entry exists** —
`CONSOLIDATED_SPEC.md:2907` itself states "**Absent.** `MainWindow._build_database_menu` has no such
actions." So the only documented escape from a signature-change refusal points at nothing. See D1.

### C6. `NO_SESSION_TEXT` names the setup surface for a session act — MEDIUM
`sql_console_panel.py:168-171` says "open one via Database ▸ Sandbox Setup…." while the command literally
named `Open Sandbox Session` exists (`main_window.py:1838`). Not wrong (Setup contains such a button,
`sandbox_setup_dialog.py:414`) but the two-step route, naming a differently-capitalised twin. The sibling
strings get it right (`ddl_object_editor.py:114-116`). Three strings, one condition, three routings.

### C7. Three menu-path separators in user-facing text — MEDIUM
`▸` (~100 sites, incl. `ddl_check.py:157,203,224`, `sql_console_panel.py:169`) ·
`>` (`generation_controller.py:383`) · `›` (`toolbar_registry.py:100-104` `menu_path_label`, and
`manual.md:2040`). So Customize Toolbar shows `File › Save As` while errors say `File ▸ Save As`.

### C8. Ellipsis: both characters, adjacent — MEDIUM
`...` (12): `Open...` `:1330` · `Save As...` `:1371` · `Find...` `:1413` · `Replace...` `:1425` ·
`Preferences...` `:1460` · `Manage Captions...` `:3512` · `Compare / Merge Two Files...` `:3537` ·
`Locate PHP Generator Executable...` `:201` · `Generate PHP...` `:204` · `Locate panGen Runtime...` `:210` ·
`Save reJSON...` `:216` · `Copy Selected to...` `project_tree.py:257`.
`…` (~22): the rest.
Worst adjacencies: `Manage Captions...` immediately above `Caption Filter…` (`:3512-3514`); `Open...` two
lines above `Open PHP File…` (`:1330`, `:1345`).
Missing where a dialog *does* open: `Export XSD` / `Import XSD` (`xsd_controller.py:202-205`, Import opens
a file dialog at `:562`). Present where nothing opens: `Create new detail from this table…` /
`…lookup…` (`coherence_panel.py:591-592`) open a draft tab, while the sibling
`Create new page from this table` has none — three siblings, two spellings.

### C9. Confirmation dialogs — MEDIUM
Titles uniformly Title Case ✅ — leave alone. But: `Apply Failed -- No Changes Written` uses `--` where
the app uses `—`; title `"Unpushed .pgtp Changes"` with body "…not yet deployed…" while the command is
`Deploy .pgtp` (`ddl_project_controller.py:486-491`) — "Unpushed" appears nowhere else; and
`"cancelled -- …"` / `"Cancelled -- …"` are the same sentence capitalised two ways.

### C10. Smart quotes in two tooltips only — LOW
`coherence_panel.py:209-211` uses `“…”` where the app elsewhere uses `'…'`.

---

## D — Functionality placement

### D1. A whole feature is built, tested and unreachable — HIGH
`ui/schema_compare_panel.py` (490 lines): grouped schema diff, default-unchecked review discipline,
`Save Migration As…`. `SchemaComparePanel` appears outside its own module **only** in its test. Nothing
instantiates it, while three refusal messages send users to it (C5) and `db/schema_diff.py` +
`db/migration_gen.py` + `db/schema_snapshot.py` all exist, tested, to feed it.
**One `menu.addAction("Compare Schemas…")` resolves C5 and unlocks the documented escape. Highest
value-to-effort item in this dossier.**

### D2. `File ▸ Deploy .pgtp` writes irreversibly with no confirmation — HIGH (safety)
`ddl_project_controller.py:674-694` reads the working copy and `write_text`s it straight over
`link.source_path` — an sshfs-mounted shared/quality file. No confirmation, no ellipsis on the label
(`main_window.py:1364`), no backup. Contrast `Deploy This Edit…`, two menus away: explicit picker, four
hard preconditions, named override, and a deliberate no-shortcut policy because "an irreversible outward
effect must not be one keystroke away" (`main_window.py:1873-1875`).
**Recommend:** confirmation naming the destination path (the app already has `destructive_warning`
machinery and a stated rule that a confirmation must name what it will hit), and rename to
`Deploy .pgtp to Source…`.

### D3. Context-menu only, where a menu is expected — MEDIUM
`Check Out for Versioning` (`ddl_buffer_panel.py:459`) — core §18.2 act, tree only, no shortcut, invisible
to Customize Toolbar · `Format Selection` (`ddl_object_editor.py:806`, Ctrl+Alt+F `:687`, also
`sql_console_panel.py:503`) — so `[SQL]` exists to report refusals from a command only findable by
right-click · `Run in Sandbox Console` (`:814`) vs the menu's `Sandbox SQL Console…` — two doors, different
behaviour, one discoverable · `Add Trigger…` (`ddl_buffer_panel.py:468`) tree-only while
`New Function/Procedure…` is in **both** (`main_window.py:1817`, `ddl_buffer_panel.py:476`) ·
`Edit {ref.qualified}…` (`:456`) — the primary way to open a DDL object, context menu only.

### D4. Two ways, different behaviour — MEDIUM
Open a session (menu vs `Sandbox Setup…` button) · data clone (Sandbox Setup vs Project Status, three
labels) · install plpgsql_check (both, and `REASON_INSTALL_LOCATIONS` honestly names both — the good case) ·
connection editing (A6) · find bar (four surfaces, one menu entry, Ctrl+F re-routed per mode,
`main_window.py:1737`).

### D5. Project Status is a status window holding actions — MEDIUM
`project_status_panel.py`: `Reconnect` (`:1005`), `Run data clone now` / `Redo data clone` (`:1080`),
`Install`, `Open help` (`:1043`) — two duplicate Sandbox Setup's, one is destructive. And the App node
ships a placeholder to users: *"This window will grow project-tier actions once their contents are
specified."* (`:1021-1022`).
**Recommend:** decide read-only (keep `Reconnect`, drop the rest) or action-bearing (then Sandbox Setup
overlaps); either way remove the placeholder.

### D6. Seven "Not yet implemented" stubs — MEDIUM
`Edit ▸ Cut / Copy / Paste / Delete` (`main_window.py:1404-1407`), `Edit ▸ Preferences...` (`:1460`),
tree `Compare Selected` / `Copy Selected to...` (`project_tree.py:256-257`).
This contradicts the rule the sandbox surfaces follow rigorously — "an affordance whose seam is unwired is
ABSENT, not disabled" (`ddl_object_editor.py:1291-1293`, `sandbox_setup_dialog.py:258`). Two opposite
policies in one app. **Cut/Copy/Paste are *expected* to work; a "Not yet implemented" Paste is worse than
no Paste** — wire them to the focused widget's built-in slots or remove them.

### D7. `Reparse Raw XML into Tree` two menus from `Auto Parse XML` — LOW-MEDIUM
`main_window.py:3535` vs `:1453`.

---

## E — Shortcut coherence

Inventory: Ctrl+O/S/Shift+S/W (File) · Ctrl+Z/Y (QShortcut, **not on the menu items**) ·
Ctrl+F / F3 / Ctrl+Shift+F / Ctrl+R / Ctrl+Alt+Return (Edit) · Ctrl+Shift+B / Ctrl+Shift+A ·
Ctrl+F2 / F2 / Shift+F2 (`find_controller.py:249,255,261`) · Ctrl+L Go To XSD (no menu entry) · F1 Manual ·
Ctrl+Space completion · Ctrl+Alt+F Format Selection (no menu entry, two owners) · Ctrl+Return Run
(console, no menu entry) · Ctrl+G go-to-line (caption panel, no menu entry) · Ctrl+W Cancel (code dialog).

### E1. Two mode-scoped collisions — MEDIUM
**Ctrl+R** is `Edit ▸ Replace...` (`:1426`) *and* a window-level caption-replace `QShortcut` (`:390`).
Behaviour is presumably right, but the menu keeps showing Ctrl+R next to `Replace...` while in Caption
Mode it does something else. **Ctrl+W** is `File ▸ Close` and the code dialog's Cancel
(`code_editor.py:516`) — dialog-scoped, but Esc is expected.

### E2. Comparable commands, one has a shortcut — MEDIUM
`Find All` Ctrl+Shift+F vs `Replace All` Ctrl+Alt+Return — mismatched shape for a pair ·
**`Validate Project` has none** despite being in `DEFAULT_TOOLBAR_IDS` and among the most repeated acts ·
`Lint Current File` none · **`Check Object Without Applying` has none — the single most valuable missing
shortcut**, being the free non-committing probe run in a tight loop (`Apply to Sandbox` correctly has none;
`Deploy This Edit…`'s absence is deliberate policy and does not argue against one for the probe) ·
`Reparse Raw XML into Tree` none · three commands own a shortcut with **no menu entry at all**.

### E3. Undo/Redo show no shortcut hint — LOW
`main_window.py:1391-1398` creates them without `setShortcut`; Ctrl+Z/Y are separate `QShortcut`s, so the
Edit menu shows Undo/Redo bare in a menu where everything else shows a hint. Users learn shortcuts from
menus.

---

## Defensible as-is — do not "fix"

- **`REASON_*` voice** (`db/ddl_check.py`, `db/sandbox.py`) — the best strings in the app. Only the
  missing-remedy subset (C4) needs work.
- **`New Function/Procedure…` in the menu, `Add Trigger…` tree-only** — a trigger needs a table. Signpost
  (D3), do not move.
- **`Deploy This Edit…` having no shortcut** — correct and stated. Extend the reasoning to `Deploy .pgtp`
  (D2) rather than relaxing it here.
- **Confirmation dialog titles** — already uniform Title Case.
- **Generation's proper-noun + gloss labels.**
- **`sandbox1_unknown` / `sandbox1_not_provisioned` reusing the "empty" icon**
  (`project_status_model.py:364-370`) — documented interim, captions carry truth, alias confined to one
  function. Artwork debt, not naming chaos.
- **Hidden-not-disabled sandbox entries** — a coherent rule; the inconsistency is D6, the stubs violating it.
- **`[Lint]` / `"xsd"` audit target tags** — they route clicks. Rename visible text only.

---

## §L — Load-bearing: do not rename without touching these

**L1. `quality_*` state stems are asset filenames.** `project_status_model.py:88,103-107,167` and
`asset_filename` (`:386-394`) turn state values into `resources/status/*.svg`:
`quality_connection_not_set_up[_drk].svg`, `quality_connection_ok*`, `quality_offline*`,
`connector_quality-app*`, plus `app_project_not_setup*`, `sandbox1_*`, `sandbox2_plpgsql_check_*`.
`_STATE_CAPTIONS` (`project_status_panel.py:150`) is keyed by the same stems deliberately "so there is no
second table to drift out of step". **User-facing captions are free to change; the stems are not** —
renaming means ~20 SVGs + the caption dict + the tests asserting every emittable asset exists.

**L2. Toolbar command ids derive from menu label AND menu location.**
`toolbar_registry.py:92-97`: `command_id_for(["File","Save As..."]) → "file.save-as"`. Its own docstring
(`:28-32`) states the tradeoff.
- **Case changes and `...`↔`…` are SAFE** — `normalize_label` strips `&` and trailing ellipsis, `slugify`
  lowercases (`:80-89`).
- **Word changes are NOT** — a rename drops that button from saved toolbars and from saved per-command icon
  assignments (`ICON_ASSIGNMENTS_SETTINGS_KEY = "toolbarIconIds"`, `:117`).
- **Moving a command between menus is NOT** — the first path segment is part of the id, so every A2/A3
  move breaks its saved id.
- **Two ids are hardcoded:** `LEGACY_ID_ALIASES` (`:56-63`) pins `"validate" → "tools.validate-project"`
  and `"generate" → "generation.generate-php"`; these define `DEFAULT_TOOLBAR_IDS` and key
  `ICON_ID_BY_COMMAND` → the vendored SVGs. **Renaming `Validate Project` or `Generate PHP...`, or moving
  either out of its menu, silently empties a default toolbar button.** Update `LEGACY_ID_ALIASES` in the
  same commit; a rename wave should generalise it into an old-id→new-id map.
- Degradation is self-healing (the user re-adds the button), so this is a cost, not a blocker.

**L3. Three audit prefixes are read back.** `find_controller.py:505` (`[Find]`), `:515` (`[Validate]`),
`generation_controller.py:261` (`[PHP]`). Renaming one without its `startswith` leaves stale rows
accumulating forever. `CHECK_PREFIX` is imported cross-module (`main_window.py:77`);
`LINT_PREFIX` + `LINT_AUDIT_TARGET` (`lint/findings.py:54-60`) drive click routing.

**L4. `ProjectSettings` field names are a settings-file schema.** `settings.target`, `settings.sandbox`,
`sandbox_mode` persist in `.ddlproject/settings.json`. A user-facing Target→Quality rename must not rename
these without a migration, or every existing project loses its connection.

**L5. `SANDBOX_DB_PREFIX = "pgtp_sandbox_"` and `OWNER_MARKER_PREFIX = "pgtp-editor-sandbox:"`**
(`db/sandbox.py:611-612`) are the ownership guard — the app only writes to a database it created and
marked. They appear in user-facing text (`new_project_dialog.py:142`, `sandbox_setup_dialog.py:459`) and
**must stay verbatim**; existing sandboxes would become unwritable.

**L6. `_UNREACHABLE_PREFIX = "sandbox unreachable:"` / `_UNAVAILABLE_PREFIX = "sandbox unavailable:"`**
(`project_status_model.py:181-182`) are matched against probe reason strings to classify degradation,
"verified verbatim against the producing code". Rewording producer or matcher alone silently reclassifies
healthy states.

---

## Counts

| Category | Findings | High | Medium | Low / noted |
|---|---|---|---|---|
| A — Menu placement | 9 | 2 | 5 | 2 |
| B — Naming | 11 | 4 | 5 | 2 |
| C — Wording | 10 | 2 | 7 | 1 |
| D — Functionality placement | 7 | 2 | 4 | 1 |
| E — Shortcuts | 3 | 0 | 2 | 1 |
| **Total** | **40** | **10** | **23** | **7** |

Raw tallies: 9 audit prefixes (estimated 7) · 12 `...` vs ~22 `…` · 4 check verbs · 3 words for one
database · 3 labels for one data-clone act · 3 menu-path separators · 4 phrasings of "open a project
first" · 3 formats for "saved" · 7 stub entries · 5 shortcuts with no menu entry · 3 live strings naming
a nonexistent command · 1 fully-built panel reachable from nowhere.

## Act on these regardless of the rulings

1. **`ui/schema_compare_panel.py` is built, tested, instantiated nowhere**, while three live refusal
   messages send users to the command that would open it. One `addAction` fixes both (D1 + C5).
2. **`File ▸ Deploy .pgtp` overwrites the shared source file with no confirmation** (D2,
   `ddl_project_controller.py:674`).
