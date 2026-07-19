# panGen + rePHPgen Gap Analysis (Generation menu) — Design

**Date:** 2026-07-19

Wires the `re_phpgen` reverse-engineering sub-project (standalone repo at `C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen`, see `2026-07-18-re-phpgen-generator-design.md`) into the editor as three Generation-menu actions. The purpose is a repeatable improvement loop: generate with **our** generator, compare against **vendor** output, and capture the deltas as a machine-readable gap JSON that drives the next generator improvement.

## 1. Purpose and workflow

The gap JSON is the test: `ours vs vendor → deltas → improve generator → repeat`.

**The vendor baseline is produced manually.** The vendor CLI (`-generate`) is not trusted for automation — it uses a stricter XML parser than the GUI and hangs on a modal `EInvalidXML` dialog (learned 2026-07-18/19). The user generates vendor PHP from the vendor GUI into the output folder; the editor never runs the vendor executable for analysis purposes. (The existing *Generate PHP…* menu item remains available but is not part of this loop.)

Workflow: open project → (user has manually generated vendor PHP into the output folder) → **panGen** emits our PHP → **rePHPgen** computes the gap JSON → **Save reJSON…** persists it.

## 2. Scope

**In scope**
- A CLI in the `re_phpgen` repo (`python -m re_phpgen`) with `pangen` and `analyze` subcommands.
- Three new Generation-menu actions in the editor (user's naming): **panGen (Generate Own PHP)**, **rePHPgen (Analyze Gap)**, **Save reJSON…**, plus **Locate panGen Runtime…** for configuration.
- The versioned gap-JSON format.

**Out of scope**
- Improving the generator itself (template variants, DoBeforeCreate grammar — separate specs in the re_phpgen project).
- Running the vendor executable as part of analysis (manual-GUI baseline only).
- Any UI beyond menu actions + Audit-panel/status-bar/summary-dialog feedback (no new panel).
- Auto-fixing CESU-8/invalid-XML projects (already handled by the repair workflow in the re_phpgen project).

## 3. Architecture: subprocess boundary

The editor calls `re_phpgen` **as a subprocess** (user decision — isolation over import coupling), mirroring how it already runs the vendor exe:

```
pgtp_editor (Qt)                      re_phpgen repo (own venv)
Generation menu ── GeneratorRunner ──► python -m re_phpgen pangen …
                   (existing async     python -m re_phpgen analyze …
                    runner, stdout ──► Audit panel)
```

- **Runtime resolution:** new config key `re_phpgen_root` in the existing generation config JSON (AppData; same file as the vendor-exe path). Default: `C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen`. The subprocess Python is `<re_phpgen_root>\venv\Scripts\python.exe` if present, else `sys.executable`. *Locate panGen Runtime…* opens a directory dialog to override; the chosen dir must contain `src\re_phpgen` (validated, clear error otherwise).
- The editor never imports re_phpgen modules; all data crosses the boundary as CLI args, stdout lines, exit codes, and the JSON file.

## 4. re_phpgen CLI (new `src/re_phpgen/__main__.py` + `cli.py` in that repo)

### `pangen <project.pgtp> --out <dir>`
Emits our best-effort `.php` for **every** top-level page of the project (catalog → slots → skeleton template). Best-effort is deliberate: pages beyond the currently supported template variant are still emitted (with `@@HOLE:…@@` markers and whatever the template produces), because the delta against vendor output is exactly the signal we want. Prints `pangen: N pages -> <dir>` on success. Exit 0 on success; nonzero with a stderr message on failure (unreadable project, unwritable dir).

### `analyze <project.pgtp> --vendor <dir> --ours <dir> --json <path>`
Per-page comparison using the proven symmetric pipeline (`normalize → mask_handler_code → mask_method_bodies` on BOTH sides — comparison mode string `masked-skeleton-v1` recorded in the JSON):
- For each catalog page: load `<vendor>/<fileName>.php` and `<ours>/<fileName>.php`; statuses `ok` (masked byte-identical), `diff`, `missing_vendor`, `missing_ours`, `error` (with message).
- For `diff` pages: cause buckets via the existing conditional-feature markers (master-detail, chart, partition, global-handler, unclassified) + diff hunks from `difflib.unified_diff` on the masked texts, capped at 20 hunks/page and 200 lines/page, with `hunks_omitted` count.
- Writes the JSON (UTF-8), prints a one-line summary (`analyze: ok X / diff Y / missing Z of N pages -> <json>`). Exit 0 even when diffs exist (diffs are data, not failure); nonzero only on operational failure.

### Gap JSON format (schema_version 1)
```json
{
  "schema_version": 1,
  "generated_at": "2026-07-19T12:34:56",
  "project": "C:\\...\\proj.pgtp",
  "vendor_dir": "...", "ours_dir": "...",
  "comparison": "masked-skeleton-v1",
  "summary": {
    "pages": 40, "ok": 3, "diff": 35, "missing_vendor": 1,
    "missing_ours": 0, "error": 1,
    "causes": {"master-detail": 20, "partition": 4, "unclassified": 11}
  },
  "pages": [
    {"file": "psv_state", "table": "xc.psv_state", "status": "diff",
     "causes": ["master-detail"], "hunks_omitted": 0,
     "hunks": [{"header": "@@ -12,3 +12,4 @@", "lines": ["-...", "+..."]}]}
  ]
}
```
Hunks contain real output lines (may include client captions) — acceptable: the file is user-owned, written only where the user points it, never auto-committed.

## 5. Editor menu actions (`pgtp_editor/ui/main_window.py` + `pgtp_editor/generation/`)

All three follow the existing Generate PHP conventions: require an open project, save-first prompt, reuse of the output-folder flow (directory dialog prefilled from `Project@outputPath`, remembered in `_current_output_folder`), async `GeneratorRunner` subprocess with stdout streamed into the Audit panel, success/failure via status bar + message box.

- **panGen (Generate Own PHP):** choose/reuse output folder → runs `pangen <project> --out <output-folder>\_pangen`. The `_pangen` sibling subfolder (user decision) keeps our files from ever overwriting the manually generated vendor baseline.
- **rePHPgen (Analyze Gap):** choose/reuse output folder → **precondition check:** at least one page's `<fileName>.php` exists in the output folder; if none, message "No vendor output found — generate from the PHP Generator GUI into this folder first" and abort. Then runs `pangen` (refresh ours) followed by `analyze --vendor <output-folder> --ours <output-folder>\_pangen --json <work>\gap.json` (editor work area in AppData). On success: Audit-panel summary line, status-bar message, and a summary message box (page counts per status/cause); remembers the JSON path and enables Save reJSON.
- **Save reJSON…:** `QFileDialog.getSaveFileName`, default `<project-stem>_gap.json` in the output folder; copies the last analysis JSON. Disabled (greyed) until an analysis has succeeded in this session.
- **Locate panGen Runtime…:** directory dialog → validates → stores `re_phpgen_root`.

Error surface: missing/invalid `re_phpgen_root` → message box pointing at *Locate panGen Runtime…*; nonzero CLI exit → failure dialog + Audit panel log (same pattern as vendor generation failures).

## 6. Testing

- **re_phpgen repo:** unit tests for both subcommands against a synthetic mini-project in `tmp_path` (tiny XML with 2 pages + fabricated "vendor" PHP): pangen emits N files; analyze produces correct statuses (`ok`, `diff`, `missing_vendor`), hunk caps, valid schema; plus one corpus-backed smoke test (skipped if corpus absent).
- **pgtp_editor repo:** tests mirror package layout (`tests/generation/`, `tests/ui/`): CLI command construction (paths, `_pangen` suffix, venv-python resolution incl. fallback), precondition check, Save-reJSON enable/disable state machine, and menu handlers with `GeneratorRunner` + all modal dialogs monkeypatched (house rule: no un-patched modal Qt in tests).
- Editor feature completion gates on the **feature-tester agent** + `docs/TEST_LOG.md` entry per CLAUDE.md.

## 7. Risks / notes

- The gap JSON's value tracks the corpus knowledge: `analyze` reuses re_phpgen's masking; as HOLE_METHODS evolve there, the editor picks changes up for free through the subprocess boundary (no editor release needed).
- If the user's manually generated vendor output is stale relative to the edited `.pgtp`, deltas will include phantom gaps. The JSON header records both paths and the project file's mtime vs the newest vendor `.php` mtime; `analyze` adds a `"vendor_older_than_project": true` warning flag when applicable (surfaced in the editor summary).
- Two repos change; the re_phpgen CLI must land first (editor tests stub the subprocess, so editor work isn't blocked, but manual end-to-end verification needs both).
