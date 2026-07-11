# PGTP Editor — Design Specification

**Date:** 2026-07-11
**Status:** Approved for planning
**License of the resulting project:** GPL-3.0

## 1. Problem statement

SQL Maestro's **PostgreSQL PHP Generator** ("PHPGen") is a Windows GUI tool that compiles a `.pgtp` XML project file into a working PHP CRUD web application. The `.pgtp` format encodes the entire UI surface of the generated application — page layout, field captions, master-detail structure, permissions, event-handler code — and the organization's production CMMS/EAM systems depend heavily on it.

The vendor GUI does not support several workflows the team needs on an ongoing basis:

1. **Diff and merge** two `.pgtp` files, to bring a developer's local changes into a shared project file.
2. **Move and copy structural blocks** (specifically `Detail` master-detail subgrids), since the vendor GUI has no such operation.
3. **Keep field captions/labels coherent** across a project (the same underlying DB field should read the same everywhere it appears) and **translate the UI to other languages**.
4. **Generate "client" (read-only) copies of pages** for external/client-facing views.

This document specifies a companion desktop tool, **PGTP Editor**, that adds these capabilities without displacing the vendor GUI — PHPGen remains the only thing that compiles `.pgtp` → PHP; PGTP Editor only edits the `.pgtp` XML and can optionally invoke the vendor's own generator executable as a subprocess.

## 2. Background research (already completed)

This section records what was learned about the file format and ecosystem before design started, since it grounds every decision below and would be expensive to re-derive.

### 2.1 File format facts

- `.pgtp` is a single-root (`<Project>`) XML document: **UTF-8, no XML declaration, no BOM, LF line endings, no CDATA sections.**
- Inline PHP/JS event-handler code (`OnPageLoaded`, `BeforeUpdateRecord`, etc.) is stored as **entity-escaped text directly inside elements** — there is no CDATA wrapping.
- Consequence: any tool that edits this format must preserve exact serialization (attribute order, escaping, no reformatting), or round-tripping through the vendor GUI risks breaking.
- Sample project files used during design (`sample/dev_Ferrara.pgtp`, `sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp`) contain real, live plaintext DB and SSH credentials in `ConnectionOptions`/`ScriptConnectionOptions`. The `sample/` directory (and the `.superpowers/` brainstorming-session directory) are excluded via `.gitignore` — this is not a licensing concern for the repo (confirmed with the project owner) but the files must never be committed.

### 2.2 Element hierarchy

```
Project
├── ConnectionOptions / ScriptConnectionOptions      (DB + SSH tunnel credentials — passed through untouched, never edited by this tool)
├── DataSources → DataSource                          (one per table/view: PK fields, insert/update/delete SQL)
├── Presentation
│   ├── Groups → Group                                (menu group definitions, referenced by Page@groupName)
│   └── Pages → Page                                  (top-level pages; a real sample has 69 top-level, 160 incl. nested Details)
│       Page@type / tableName / fileName / caption / shortCaption / groupName
│       Page@{view,edit,insert,delete,copy,multiEdit}AbilityMode   ← permission flags, see §2.4
│       Page@export*Available / printAvailable
│       ├── ColumnPresentations → ColumnPresentation  (one per field: caption, fieldName, headerHint, shortCaption, insertFormCaption)
│       │     ├── ViewProperties / EditProperties / Format / Lookup
│       ├── Columns → {List,View,Edit,Insert,QuickFilter,FilterBuilder,Print,Export,Compare,MultiEdit,DefaultSortedColumns} → Column
│       │     (same field referenced by fieldName in up to ~10 context-specific visible/orderType lists)
│       ├── Details → Detail → Page (nested) + MasterForeignKeyColumnMap → FieldMap
│       │     (master-detail sub-grids; arbitrary nesting depth)
│       ├── PartitionNavigators → PartitionNavigator → Partition → Values → Value
│       │     (splits a page into tabs by a field's discrete values)
│       └── EventHandlers (OnPageLoaded, BeforeUpdateRecord, OnInsertFormLoaded, etc. — inline PHP/JS text)
├── UserCSS / PdfUserStyles / PrintUserStyles / UserJS
├── ExcludedPaths, DefaultPageProperties, DefaultDataFormats
```

### 2.3 The one-way compilation boundary

Cross-checking a real generated file (`sample/development_equipment.php`) against its source `Page` in `dev_Ferrara.pgtp` confirmed: `.pgtp` → `.php` compilation is **strictly one-way and performed entirely by the vendor's own tooling.** A `ColumnPresentation@fieldName="tag" caption="Tag"` was traced directly into the compiled output as a literal constructor argument (`new TextViewColumn('tag', 'tag', 'Tag', ...)`). System-level UI strings (e.g. "Actions") instead route through `GetLocalizerCaptions()->GetMessageString(...)`, backed by a separate `lang.*.php` localization file referenced by `Project@localizationFileName` — that mechanism is **out of scope** for this tool.

**Design consequence: PGTP Editor never generates or edits PHP.** It only reads/writes `.pgtp` XML, plus optionally shells out to the vendor's own compiler (§6.6).

A secondary finding: nested `Detail` pages compile to PHP classes named by the full table-ancestry chain (e.g. `pr_equipment_pr_attachment_pr_r_characteristicPage extends DetailPage`). This also revealed that **the same DB table is sometimes embedded as a `Detail` in multiple different structural locations within one project** (e.g. `pr_r_characteristic` appears independently under `Equipment` directly, under `Equipment → Attachment`, and under `Equipment → Component` — three separate, fully-duplicated XML subtrees, since PHPGen has no "shared detail" concept). These duplicated embeddings can drift apart over time even though they conceptually represent the same thing — this directly motivated the "reused-table coherence" feature (§6.4).

### 2.4 Page "Abilities" are multi-value enums, not booleans

Confirmed from the official manual (`PgPHPGenerator Manual.pdf`, §5.7.2, "Abilities" tab, p.212-213):

| Ability | Possible values |
|---|---|
| View | Disabled / Separated Page (default) / Modal window |
| Edit | Disabled / Separated Page (default) / Inline mode / Modal window |
| Insert | Disabled / Separated Page (default) / Inline mode / Modal window |
| Copying | Disabled / Separated Page (default) / Inline mode / Modal window |
| Multi-edit | Disabled / Separated Page (default) / Modal window |
| Delete | Enabled (default) / Disabled — separate simple flag |
| Multi-delete | Enabled (default) / Disabled — separate simple flag |

The manual documents the GUI labels, not the underlying integer codes stored in `*AbilityMode` attributes. **The exact numeric mapping is not yet known and must be derived empirically** (§8, deferred item) before the Client Page feature (§6.5) can correctly implement "read-only."

### 2.5 Confirmed CLI syntax for the vendor generator

Confirmed both by the project owner and independently in the manual (§2.3 of the manual):

```
PHPGenerator[.exe] [<project_file_name>] [-o|-output <output_directory>] [-g|-generate] [-h|-help]
```

Real example in use today:

```
"C:\Program Files (x86)\SQL Maestro Group\PostgreSQL PHP Generator Professional\PgPHPGeneratorPro.exe" "project.pgtp" -output "C:\path\to\output" -generate
```

### 2.6 Existing precedent: the translator toolchain

Before this project, a 3-script Python pipeline (`extract_ui_strings.py` → `translate_ui_strings.py` → `apply_translations.py`, documented in `translator/CaseStudy_LLM_Python_Toolchain.docx`) already solved bulk UI-string translation against a real 4MB production file: extracts 8 string types anchored by `fieldName` (for column-level strings) or by type (for page/menu-level strings) into a CSV, batches 60 strings per Claude API call with type+context hints, and writes translations back using `fieldName` as the anchor so the same English word can translate differently in different tables. It flagged 157 same-field/different-caption conflicts for manual resolution rather than guessing, and verified XML tag count was unchanged after each run. **This is the direct precedent for the Caption Management feature (§6.3)** — the same fieldName-anchored substitution mechanism, not a new engine.

## 3. Scope

### 3.1 In scope

1. Diff/Merge between two `.pgtp` files (§6.1)
2. Move/Copy of `Detail` blocks; copy (not move) of `Page` blocks (§6.2)
3. Unified Caption Management: coherence audit + LLM translation (§6.3)
4. Reused-table coherence check within a single file (§6.4)
5. Client (read-only) page generation (§6.5)
6. Invoking the vendor's PHP Generator executable to compile output (§6.6)
7. Structural + well-formedness validation (§6.7)

### 3.2 Explicitly out of scope

- Any editing or generation of PHP output — strictly the vendor GUI/CLI's job (§2.3).
- Live database connectivity/schema validation — the tool has no DB connection and does not verify that a `fieldName` actually exists in the live schema. Where an operation can't be verified this way (e.g. copying a `Detail` whose FK mapping may not make sense under a new parent), it is **flagged in the Audit panel for manual developer review, never silently blocked or silently trusted.**
- Field-level (`ColumnPresentation`) move or copy — considered during design and explicitly dropped; doesn't make sense as a standalone operation once Page/Detail are handled.
- Reordering Pages — Page order was confirmed to be arbitrary/meaningless, so no reorder UI is being built.
- Deep referential-integrity validation (verifying `Lookup@tableName` / `FieldMap` targets actually exist elsewhere in the file) — useful but open-ended; treated as a stretch goal after the validation set in §6.7, not core scope.
- A "3-way merge with tracked common ancestor" model — considered during design (the initial framing was git-like checkout/merge-back against a "production" file) and explicitly simplified: there is no VCS underneath the current workflow, and the team does not want the tool to introduce implicit checkout/base-tracking. Diff/merge is a plain two-file, one-way operation (§6.1).

## 4. Architecture

### 4.1 Technology choices

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python | Matches the existing translator toolchain; team's working language for this domain. |
| GUI | PySide6 (Qt6) | Genuine docking (`QDockWidget`/`QMainWindow`) for the IDE-style layout (§5.1); LGPLv3, compatible with a GPL3 project. |
| XML | `lxml`, not stdlib `ElementTree` | Preserves attribute order and gives tighter control over round-trip serialization fidelity; much faster than `ElementTree` on 4MB+ files. Round-trip fidelity (load a sample, save unchanged, byte-diff against the original) must be empirically verified early — see §8. |
| Code editor widget | Custom, built on `QPlainTextEdit` | See §4.3. |
| Diff algorithm | Custom domain-aware structural differ | See §4.2. Generic XML-diff libraries/tree-edit-distance algorithms don't know that a `Page` is identified by `fileName` or a `ColumnPresentation` by `fieldName` — they would see a moved `Detail` as an unrelated delete+insert pair. |

Alternatives considered and rejected: wxPython (would have let us more directly reuse BoomslangXML's code, but PySide6's docking and code-editor story is stronger, and wxPython's AUI docking is comparatively rough); Tkinter (zero install friction, but no native docking manager and no adequate syntax-highlighting widget without significant extra work — not a fit for the IDE-style layout that was specifically chosen).

### 4.2 Module layout

```
pgtp_editor/
├── model/       # lxml wrapper: load/save .pgtp, identity-key resolution (§4.4),
│                # typed accessors for Page/Detail/ColumnPresentation/Column/etc.
│                # THE ONLY module that touches raw XML/lxml directly.
├── diff/        # domain-aware differ: given two model trees (or two subtrees —
│                # reused at Detail-vs-Detail scope for §6.4), produces a list of
│                # Difference records (added/removed/changed/moved), keyed by
│                # identity, not document position.
├── ops/         # mutating operations: move/copy Detail, copy Page, create client
│                # page, coherence audit + apply, translate. All go through model/
│                # — nothing bypasses it. This is what makes undo/redo and dirty-
│                # tracking uniform regardless of which feature triggered an edit.
├── validate/    # Tier 1 (well-formedness) and Tier 2 (structural sanity) checks (§6.7)
├── external/    # subprocess wrapper for invoking PgPHPGeneratorPro.exe (§6.6)
├── ui/          # PySide6 widgets: main window, project tree, properties panel,
│                # diff/merge panel, caption-management panel, audit panel, menus,
│                # the custom code-editor widget (§4.3)
└── main.py
```

### 4.3 Code editor widget

Requirements (from the team): (1) syntax highlighting, specifically so an **unclosed quote visibly propagates** — everything after an unterminated `"` should render as string-colored text until the next quote or EOF, making the error obvious at a glance; (2) automatic bracket/quote closing; (3) automatic closing-tag insertion for XML.

Two open-source references were evaluated:

- **[QCodeEditor](https://github.com/luchko/QCodeEditor)** (luchko, MIT license) — small (15 commits), extends `QPlainTextEdit`, provides line numbers, current-line highlighting, and a `QSyntaxHighlighter` hook with a bundled XML-highlighter example. **It targets PyQt4/PyQt5, not PySide6** — these are different Qt bindings that cannot be mixed in one process, so this cannot be a direct dependency. It is used as a **reference skeleton to port to PySide6**, credited in About, same treatment as BoomslangXML below.
- Requirement (1) maps cleanly onto Qt's `QSyntaxHighlighter` block-state mechanism (`setCurrentBlockState`/`previousBlockState`), the standard technique Qt-based editors use for multi-line strings/comments — a good, well-trodden fit.
- Requirements (2) and (3) are **not present in QCodeEditor** and have no reliable off-the-shelf library for generic XML in Qt. Both require custom `keyPressEvent` handling: (2) is the standard auto-close-on-typing-an-opener pattern; (3) additionally requires scanning backward from the cursor for the nearest unclosed tag name to know what `</...>` to insert. These are scoped as real implementation work, not assumed to come for free.

This widget is also the **mandatory fallback UI for Tier 1 validation failures** (§6.7), not merely an optional power-user view — see §6.7 for the exact recovery flow.

### 4.4 Identity keys

Since raw XML has no IDs, every cross-cutting feature (diff, move/copy, coherence audit) needs a stable way to recognize "this element is logically the same thing" across files or after reordering. Proposed keys, one per element type:

| Element | Identity key |
|---|---|
| `DataSource` | `name` |
| `Page` (top-level) | `fileName` (falls back to `tableName`+`caption` if `fileName` is empty) |
| `Detail` | parent Page's identity + own `tableName` (two Details under the same Page with the same table is the pathological duplicate case — flagged, never silently merged) |
| `ColumnPresentation` | parent Page identity + `fieldName` |
| `Column` (in List/View/Edit/etc.) | parent Page identity + containing context + `fieldName` |
| `Value` (dropdown) | parent `Values` identity + `name` |
| `Group` | `groupName` |

Using `fileName` as the Page identity key is also *why* the duplicate-`fileName` validation rule (§6.7) is load-bearing for correctness, not just a nicety mirroring the vendor GUI: if two Pages shared a `fileName`, the identity-key scheme itself would become ambiguous.

## 5. UI shell

### 5.1 Overall layout

**IDE-style docked panels** (chosen over two alternatives considered: a "mode switcher" with big top-level tabs giving each feature the whole window, and a hybrid tree-always-visible-with-toggled-stage design). Project tree is permanently visible on the left; the center area is tabbed (Properties / Diff-Merge / Caption Management); a persistent bottom panel shows the Audit/Problems list (coherence-audit findings, Tier-2 validation warnings, unresolved Detail-mapping flags from cross-file copies). Panels are resizable and dockable via `QDockWidget`.

### 5.2 Menu bar

| Menu | Items |
|---|---|
| **File** | New Project, Open..., Open Recent ▸, Save, Save As..., Close, ―, Exit |
| **Edit** | Undo, Redo, ―, Cut, Copy, Paste, Delete, ―, Find..., Find & Replace... (Ctrl+H), ―, Preferences... |
| **View** | ☑ Project Tree, ☑ Properties Panel, ☑ Audit/Problems Panel, ☐ Raw XML (text editor) Panel, ―, Expand All, Collapse All |
| **Diff / Merge** | Compare / Merge Two Files... (prompts for **Source** and **Target**, §6.1), ―, Next Difference, Prev Difference, Apply Changes to Target (overwrites Target, keeps a `.bak`) |
| **Tools** | Create Client (Readonly) Page..., Move/Copy Detail..., ―, Manage Captions... (unified coherence + translation, §6.3), ―, Find Reused Tables... (§6.4), ―, Validate Project (orphan refs, dupe filenames) |
| **Generation** | Locate PHP Generator Executable... (one-time setting), ―, Generate PHP... (prompts for output folder, pre-filled from `Project@outputPath`, then runs the CLI from §2.5), ―, Open Output Folder |
| **Help** | Documentation, About (OSS credits, §9) |

### 5.3 Right-click context menus

**On a Page:**
```
Edit Properties
―
Copy  Paste  Duplicate
Copy to Other Open Project...
―
Add Detail...
―
Create Client (Readonly) Page
Compare This Page With...
―
Find Field Usages...
Rename / Unify Captions...
―
Delete Page
```
(No "Cut" — per §6.2, Page order is arbitrary and Page never has a move operation, only copy.)

**On a Detail:**
```
Edit Properties
―
Cut  Copy  Paste  Duplicate
Move to Parent Page...
Copy to Other Open Project...
―
Add Nested Detail...
―
Create Client (Readonly) Page
Compare This Detail With...
Compare with Other Instance... (§6.4, only shown when this table appears elsewhere in the file)
―
Delete Detail (+ nested)
```

**On a Field (`ColumnPresentation` leaf):**
```
Edit Caption / Hint / Short Caption
―
Find All Usages of This Field
Unify Captions Across Pages...
―
Delete Field
```
(Note: earlier drafts of this menu included "Copy Field" / "Copy Field to Other Page..." — removed per the finalized scope decision in §3.2 that field-level copy doesn't make sense as a standalone feature.)

**Multi-select** (ctrl/shift-click several Pages or Details): Compare Selected, Create Client Pages for Selected (batch), Copy Selected to...

## 6. Feature designs

### 6.1 Diff / Merge

A **one-way, two-file** operation — deliberately not a 3-way merge with a tracked common ancestor (that framing was explored and dropped, §3.2), and deliberately not a symmetric "keep A or keep B" model. The two inputs are called **Source** and **Target**; differences flow from Source into Target.

- **Engine:** the differ walks both trees using the identity keys from §4.4 (not document position), producing a flat list of `Difference` records: `added` (exists only in Source), `removed` (exists only in Target), `changed` (same identity, different attributes/text/children — recorded per-attribute, not as an opaque blob), `moved` (same identity, different parent — this is what makes Detail/Page relocation surface as a single "move" rather than a delete+insert pair, the core payoff of a domain-aware differ over line-based diff).
- **UI:** a change-list on the left, grouped by Page/Detail (e.g. "Equipment ▸ caption: changed", "Equipment ▸ Details ▸ Sub-item: moved from Work Orders"). Selecting an entry shows its detail on the right: attribute-level side-by-side for structural changes, line-based text diff for long text content (event-handler code, descriptions) where that's still the more readable form.
- **Resolution:** each difference is a candidate patch with **Apply / Skip** (default: skip — nothing changes until explicitly chosen), not "keep A / keep B," since without an ancestor there's no notion of which side is "right" — every difference is a genuine developer decision.
- **Output:** applying the chosen patches **overwrites the Target file directly**, with an automatic `.bak` backup of the pre-merge Target kept first (same convention as the existing translator toolchain, §2.6) — not a one-way door.

### 6.2 Move / Copy

Scope was narrowed during design to exactly what's needed:

- **`Detail`**: the core of this feature. **Move** re-parents a `Detail` subtree (its nested `Page` + `MasterForeignKeyColumnMap`) to a different parent Page's `Details` list — same file or a different open file. **Copy** duplicates it instead of relocating it. Since a moved/copied Detail's FK mapping references specific field names on both sides of the join, and the tool has no live DB schema to verify against, the mapping is carried over as-is and **flagged in the Audit panel** ("verify FK mapping after moving/copying this Detail") rather than the tool guessing or silently trusting it.
- **`Page`**: **copy only** — no move/reorder operation, since Page order was confirmed to be arbitrary and carries no meaning. Copy works within the same file (duplicate) or into another open project's `Pages` list.
- **`ColumnPresentation` (field)**: **no move or copy operation at all.** Considered during design, then explicitly dropped as not making sense as a standalone feature once Detail and Page are handled.
- **Cross-file mechanics:** both files must be open simultaneously as separate project tabs sharing the app's clipboard; copy from one tree, paste into the other, like any tree UI.
- Every paste that would violate the fileName-uniqueness rule (§6.7) is blocked with an inline rename prompt at paste time, not a silent failure discovered later.

### 6.3 Caption Management (unified coherence audit + translation)

Originally scoped as two separate features (a coherence audit and a translation tool); merged during design on the observation that both are the same underlying operation — **"apply a caption value to an anchor everywhere it appears"** — differing only in where the replacement value comes from.

- **Scan:** scoped to the currently active open project file (not all open files at once — cross-file caption comparison isn't a requirement here, unlike Move/Copy or Diff/Merge). Extracts every caption-like string (`caption`, `shortCaption`, `headerHint`, `insertFormCaption`, `groupName`, `Value@caption`, `Page@caption`, `Detail@caption`) anchored the same way the existing translator toolchain already does — `ColumnPresentation@fieldName` for column-level strings, the element itself for page/menu-level ones (§2.6). Groups all distinct values found per anchor into one panel (e.g. anchor `tag` → "Tag" used on 2 pages, "Asset Tag" used on 1 — flagged as inconsistent).
- **Two ways to produce a replacement value for a group:**
  - **Pick Existing** — choose one of the values already present elsewhere in the project as the canonical one (the coherence-audit case).
  - **Translate** — a bulk action, not a per-row one: pick a target language once and the *entire current scan* is sent to Claude in one operation (batches of 60 strings per API call under the hood, each with its string-type + context hint, exactly matching the existing toolchain's proven approach, §2.6). This populates a translated candidate value for every anchor at once, which can then be reviewed and applied per-anchor or in bulk — mirroring how `translate_ui_strings.py` already processes a whole project's strings in one run rather than one string at a time.
- **Apply:** identical regardless of source — the fieldName-anchored substitution already proven in `apply_translations.py` (for column-level strings, `fieldName` is the anchor so only that specific field's caption changes even if the same English word appears elsewhere meaning something different; other string types use plain attribute substitution).
- One menu entry, **Manage Captions...**, not two — since underneath it's one operation with two ways to source the replacement value.

### 6.4 Reused-table coherence

A distinct problem from §6.3: when the *same DB table* is embedded as a `Detail` in multiple structural locations within one file (confirmed real example, §2.3: `r_characteristic` independently embedded under Equipment, under Equipment→Attachment, and under Equipment→Component), those independent copies can drift in captions, which columns are hidden/shown, and which are read/write — even though they conceptually should usually match.

Rather than a new engine, this **reuses the §6.1 differ and diff/merge UI at Detail-subtree scope** instead of whole-file scope:

- **Tools → Find Reused Tables...** scans the open file, groups all `Detail` (and top-level `Page`) elements by `tableName`, and lists groups where more than one instance exists.
- Right-click any instance within such a group → **Compare with Other Instance...** → opens the exact same Source/Target diff view from §6.1, scoped to the two selected subtrees. Same Apply/Skip-per-difference workflow, **never automatic** — matching the requirement that reconciling reused-table drift is always a developer decision, not an automatic sync.
- With 3+ instances in a group, reconciliation is done pairwise (pick any two, diff, repeat) rather than building a separate N-way merge UI — this was an explicit simplification, reusing §6.1 exactly rather than inventing new merge machinery.

### 6.5 Client (read-only) page generation

Clones a selected `Page` subtree — recursively including nested `Details` — into new `Page`/`Detail` elements in the same file, then rewrites the clone's ability attributes to be read-only:

- `viewAbilityMode` set to a non-Disabled code (the page must remain viewable).
- `editAbilityMode`, `insertAbilityMode`, `copyAbilityMode`, `multiEditAbility` set to their respective Disabled code.
- Delete/Multi-delete bits cleared.

**This cannot be correctly implemented until the exact numeric ability codes are empirically derived** (§2.4, deferred item in §8) — using the wrong constant would silently ship a "client page" that's still editable, which is worse than not having the feature at all.

Naming convention (fixed, no per-instance prompt): the clone's `fileName` is `<original>_client` (e.g. `development_equipment` → `development_equipment_client`). The caption gets an analogous suffix (e.g. "Equipment" → "Equipment (Client)") for recognizability in the running app's own menus — this suffix convention was proposed during design and not explicitly contested. Must still satisfy the fileName-uniqueness rule (§6.7); the deterministic `_client` suffix makes collisions rare but the same paste-time check applies.

### 6.6 Generate PHP (vendor tool invocation)

A **completely different kind of "generate" from §6.5** — kept in a separate top-level **Generation** menu specifically to avoid the two being confused (one is an in-tool XML clone operation; the other shells out to the real vendor compiler and touches no `.pgtp` content at all).

- **Generation → Locate PHP Generator Executable...** — one-time configuration, stored in Preferences. The path can be pre-suggested by reading the currently-open project's own `Project@localizationFileName` attribute, which already points into the same vendor install directory (e.g. `...\PostgreSQL PHP Generator Professional\lang.fr.php`).
- **Generation → Generate PHP...** — prompts for an output folder, pre-filled from the project's own `Project@outputPath` attribute (already stored in the file). Then runs, as a subprocess:
  ```
  PgPHPGeneratorPro.exe "<project.pgtp>" -output "<folder>" -generate
  ```
  stdout/stderr are streamed into a log panel — a nonzero exit code or stderr output is always surfaced as a failure, never swallowed.

### 6.7 Validation

Two tiers, both feeding the Audit panel (§5.1):

**Tier 1 — well-formedness (blocking).** The tool's own structured operations (move/copy/coherence/translate/client-page) can never produce malformed XML by construction — they mutate a valid in-memory `lxml` tree and serialize it. This tier only matters at the points where raw text can bypass the model: **(a)** opening any file (it may have been hand-edited outside the tool), **(b)** the optional Raw XML text-editor panel (§4.3) where a developer edits a node's text directly, **(c)** the diff/merge view's "edit manually" escape hatch. At all three, an `lxml` reparse is attempted before the change is accepted.

**On a parse failure, the tool does not just show an error dialog and stop.** The tree panel explicitly displays a "failed to parse" state (not a blank/stale tree), and the app automatically opens the raw file in the text-editor fallback view (§4.3) with the parse error highlighted at its exact line/column — the fix happens directly in text form, using the same editor's syntax highlighting (including the unclosed-quote propagation behavior from §4.3) to make the problem visible.

**Tier 2 — structural sanity (mostly warn, one hard block).** The parent→child map from §2.2 acts as a whitelist — anything found in an unexpected location is flagged ("wrongly placed blocks"). Missing required attributes per element type (e.g. a `Page` without `fileName`/`tableName`) are warned in the Audit panel, not save-blocking. **Duplicate `Page@fileName` is the one hard-blocking rule in this tier** — checked live, at creation/rename/paste/copy time (not only at save), mirroring the vendor GUI's own behavior and, as noted in §4.4, protecting the tool's own identity-key scheme from becoming ambiguous.

Deep referential-integrity checks (verifying that `Lookup`/`FieldMap` targets actually exist) are explicitly deferred (§3.2) — useful, but open-ended, and not needed for the core workflows above.

## 7. Error handling

- **File I/O:** parse errors surface with line/column (§6.7 Tier 1) rather than a generic "failed to open" message.
- **External process (§6.6):** subprocess failures are never swallowed — nonzero exit code or stderr output is reported as a failed generation, not silently treated as success.
- **Destructive operations:** Delete (Page/Detail/Field) prompts for confirmation. Merge-overwrite (§6.1) keeps an automatic `.bak` of the pre-merge Target.
- **Cross-file paste conflicts:** a paste that would violate the fileName-uniqueness rule (§6.7) is blocked with an inline rename prompt at the point of paste, not discovered later at save time.

## 8. Testing strategy and deferred empirical work

**Automated testing** concentrates on `model/`, `diff/`, and `ops/` — pure logic with no Qt dependency:

- Round-trip fidelity: load a sample file, save unchanged, byte-diff against the original.
- Identity-key matching and differ correctness — using **small synthetic XML fixtures** built specifically to exercise add/remove/change/move cases, rather than relying only on the two large real sample files (which are useful for integration coverage but too large/slow to reason about per-unit-test).
- Coherence-audit grouping logic.
- Client-page ability-flag rewriting — blocked on the empirical ability-code lookup table below.

The two real sample files serve as **integration/regression tests**: "open, make no changes, save, byte-diff" and "run coherence audit, assert the known `tag`/`objecttype_id` inconsistencies are detected."

The **UI layer** gets standard manual/exploratory testing for desktop GUI work rather than heavy automated coverage — a deliberately lower bar than the model/diff logic underneath it, since Qt widget testing has a much lower value-to-effort ratio here.

**Deferred empirical work required before implementation can be considered complete** (these are concrete, scoped research tasks, not open-ended unknowns):

1. **Ability-code lookup table (§2.4, blocks §6.5):** build small test projects in the real PHPGenerator GUI that each differ by exactly one Ability dropdown setting, save, and diff the XML to derive the exact numeric code for each of Disabled/Separated Page/Inline mode/Modal window (View/Edit/Insert/Copying), Disabled/Separated Page/Modal window (Multi-edit), and the Delete/Multi-delete bit(s).
2. **lxml round-trip fidelity (architecture assumption in §4.1):** confirmed empirically as part of the automated test suite above, but flagged here since the whole "preserve exact serialization" design principle (§2.1) depends on it holding true in practice, not just in theory.

## 9. Licensing and credits

The project is licensed **GPL-3.0**. The About dialog (Help → About) credits:

- **[BoomslangXML](https://github.com/driscollis/BoomslangXML)** (Mike Driscoll) — cited as prior art for the tree-based XML editing approach. It is a wxPython application, not a library, and is not a runtime dependency of this project — credited for the conceptual approach, not for reused code.
- **[QCodeEditor](https://github.com/luchko/QCodeEditor)** (luchko, MIT license) — the code-editor widget (§4.3) is a PySide6 port of this project's approach (line numbers, current-line highlighting, the `QSyntaxHighlighter` hook pattern). Credited per MIT's attribution requirement.
- **[SuperNano](https://github.com/LcfherShell/SuperNano)** (LcfherShell, GPL-3.0) — evaluated during design as a possible embeddable text-editing component; found to be a curses/TUI console application (not a GUI widget, no syntax highlighting), so **it is not used as a dependency**. Credited only if any concept from it ends up genuinely reused; otherwise this entry should be removed before release rather than credited speculatively.
- Standard license notices for actually-vendored dependencies: PySide6 (LGPLv3), lxml (BSD), and the Anthropic Python SDK (MIT) used by the translation feature (§6.3).

## 10. Summary of explicit scope decisions (changelog from initial framing)

Recorded here because several of these reversed or narrowed an earlier assumption made during design, and the reasoning matters for anyone picking this spec up cold:

- Diff/merge is **not** a 3-way merge against a tracked "production" file with tool-managed checkout snapshots — that was the initial framing, dropped once it was clarified there's no VCS underneath the actual workflow today. It is a plain one-way, two-file (**Source**/**Target**) patch/cherry-pick operation.
- Move/Copy scope was narrowed twice: first expanded to "Page + Detail + Field, cross-file," then narrowed to **Detail move+copy, Page copy-only, no Field operations at all** once the actual need was thought through.
- Coherence audit and translation were designed as two separate menu items, then **unified into one Caption Management feature** on the realization they're the same substitution operation with a different value source.
- The reused-table coherence check (§6.4) was a new requirement surfaced mid-design (not in the original four goals) and was scoped to **reuse the diff/merge engine** rather than become a new one.
- The text-editor widget's reference implementation changed from QScintilla to a **PySide6 port of QCodeEditor** once QCodeEditor was pointed out directly, since introducing a separate Scintilla binding alongside a QCodeEditor-inspired `QPlainTextEdit` widget would have been redundant.
