# Generate PHP (vendor tool invocation) + File Save/Save As — Design

**Date:** 2026-07-13

Implements §6.6 of `docs/superpowers/specs/2026-07-11-pgtp-editor-design.md`. Generate PHP shells out to the real SQL Maestro PostgreSQL PHP Generator to compile the active `.pgtp` into PHP. Because the generator reads the file **from disk**, this feature also implements the currently-stubbed **File → Save / Save As** (persisting the Raw XML editor buffer), which Generate reuses.

## 1. Purpose

Let the user, from within the editor, (a) persist their edits to disk (Save / Save As), (b) configure the path to the vendor generator executable once, and (c) run the generator on the active project into a chosen output folder — with the generator's output streamed into the Audit panel and any failure clearly surfaced.

## 2. Scope

**In scope**
- **File → Save / Save As…** — write the Raw XML editor buffer verbatim to disk. Save overwrites the current path (keeping a `.bak`); Save As prompts for a new path and adopts it as the current project path.
- **Generation → Locate PHP Generator Executable…** — a file dialog whose chosen path is stored in a per-user JSON config in AppData (the Schema-Learning storage pattern).
- **Generation → Generate PHP…** — require an open project; ensure the executable is configured; ask Save vs Save As (so on-disk content matches the editor); pick an output folder (pre-filled from the project's `Project@outputPath` if present); run the generator as a subprocess; stream stdout/stderr into the Audit panel; report success/failure in a final dialog.
- **Generation → Open Output Folder** — open the most recent output folder in the OS file browser (best-effort; disabled until a generation has run).

**Out of scope**
- Re-serialising the parsed model (Save writes the raw editor text — the authoritative edit surface).
- Any change to `.pgtp` content by this feature (the generator only reads it).
- Bundling/installing the vendor tool; validating the generated PHP.
- Progress percentage (the generator does not report one; streamed log lines are enough).

## 3. The vendor CLI (confirmed)

```
PgPHPGeneratorPro.exe "<project.pgtp>" -output "<output-folder>" -generate
```
Positional: absolute path to the `.pgtp`. `-output "<folder>"`: target directory. `-generate`: triggers non-interactive generation. A nonzero exit code or any stderr output is treated as failure.

## 4. Persistence — `pgtp_editor/generation/config.py`

Mirror `pgtp_editor/schema_learning/storage.py` (which uses `QStandardPaths.writableLocation(AppDataLocation)` and accepts an injectable `base_dir` for tests):

- `generator_config_path(base_dir: Path | None = None) -> Path` → `<base_dir or AppData>/generator_config.json`.
- `load_executable_path(base_dir=None) -> str | None` — read the JSON `{"executable_path": "..."}`; return `None` if the file is absent/unreadable/missing the key.
- `save_executable_path(path: str, base_dir=None) -> None` — write/merge the JSON (create the dir if needed).

`MainWindow.__init__` gains an injectable `generator_config_dir: Path | None = None` (same pattern as the existing `schema_storage_dir`) so tests use a `tmp_path` and never touch real AppData.

## 5. Command building + run — `pgtp_editor/generation/runner.py`

- `build_generate_command(executable: str, pgtp_path: str, output_folder: str) -> list[str]` — **pure**, returns `[executable, pgtp_path, "-output", output_folder, "-generate"]`. Fully unit-tested (this is the load-bearing correctness).
- `GeneratorRunner` — wraps `QProcess` so output streams without freezing the UI:
  - `run(command: list[str], on_output: Callable[[str], None], on_finished: Callable[[int], None]) -> None` — starts the process, connects `readyReadStandardOutput`/`readyReadStandardError` to emit decoded lines to `on_output`, and `finished` to call `on_finished(exit_code)`. stderr is merged into the same stream (via `setProcessChannelMode(MergedChannels)`) so all generator chatter is captured in order.
  - The runner is injectable into `MainWindow` (default: a real `GeneratorRunner`); tests inject a fake that records the command and synthesises `on_output`/`on_finished` calls, so no real process or `QProcess` event loop is needed.

## 6. File Save / Save As — `MainWindow`

- `_write_project_text(path)` — write `center_stage.xml_editor.toPlainText()` to `path` as UTF-8. If `path` already exists, first copy it to `path + ".bak"` (same `.bak` convention as Diff/Merge apply).
- **Save** (`_save_project`): if no current path → delegate to Save As. Else `_write_project_text(_current_project_path)`; status `Saved <name>`.
- **Save As** (`_save_project_as`): `QFileDialog.getSaveFileName` (filter `PGTP files (*.pgtp)`); on accept, `_write_project_text(path)`, set `_current_project_path = path`, status `Saved as <name>`. Cancel → no-op.
- Wire the File-menu **Save** / **Save As…** actions (currently stubs) to these. (Undo/Redo/Cut/… stay stubs.)

## 7. Generation flow — `MainWindow`

- **Locate PHP Generator Executable…** (`_locate_generator`): `QFileDialog.getOpenFileName` (filter `Executables (*.exe);;All files (*)`); on accept, `save_executable_path(path, self._generator_config_dir)`; status `PHP Generator set: <name>`.
- **Generate PHP…** (`_generate_php`):
  1. If no open project (`_current_project is None` and editor empty) → info status, stop.
  2. `exe = load_executable_path(self._generator_config_dir)`; if `None` → info dialog "Locate the PHP Generator executable first" and stop (do not silently proceed).
  3. Ask **Save vs Save As** (a `QMessageBox` with Save / Save As… / Cancel). Cancel → stop. Save → `_save_project` (must yield a concrete path; if still none, treat as Save As). Save As → `_save_project_as`; if cancelled, stop. After this step `_current_project_path` is a real on-disk file matching the editor.
  4. Pick **output folder** (`QFileDialog.getExistingDirectory`), pre-filled from the project's `Project@outputPath` attribute if readable, else the project's own directory. Cancel → stop.
  5. `command = build_generate_command(exe, _current_project_path, output_folder)`; clear prior `[PHP]` Audit entries; `self._generator_runner.run(command, on_output=self._append_generator_output, on_finished=self._on_generation_finished)`; remember `output_folder` for Open Output Folder; status `Generating…`.
  - `_append_generator_output(line)` → append `"[PHP] " + line` to the Audit panel (same panel Find All uses; a distinct prefix so `_clear_find_results`-style clearing can target `[PHP]`).
  - `_on_generation_finished(exit_code)` → append a `[PHP] Generation finished (exit N)` summary; show a final `QMessageBox` (success if `exit_code == 0`, else critical with a pointer to the Audit log); status `Generation succeeded` / `Generation failed (exit N)`.
- **Open Output Folder** (`_open_output_folder`): if a folder was recorded, `QDesktopServices.openUrl(QUrl.fromLocalFile(folder))`; else info status. (Action starts disabled / no-ops until a generation has run.)

## 8. Error handling (§7 of the master design)
- Subprocess failure (nonzero exit or stderr) is always reported as a failed generation — never swallowed. The full generator output remains visible in the Audit panel.
- Save I/O errors (`OSError`) surface a `QMessageBox.critical` with the message; the editor buffer is untouched.
- If the configured executable no longer exists, `QProcess` fails to start → surfaced via the `finished`/`errorOccurred` path as a failure (the runner maps a start failure to `on_finished` with a nonzero code and an `on_output` diagnostic line).

## 9. Testing
- **`config.py` (unit):** save→load round-trip with a `tmp_path` base_dir; `load` returns `None` when file absent / malformed / key missing; `save` creates the directory.
- **`runner.py` (unit):** `build_generate_command` returns the exact 5-element list for representative paths (incl. paths with spaces — the list form needs no quoting). The `QProcess` wrapper itself is exercised only via the fake-runner injection in MainWindow tests (no real process spawned).
- **Save/Save As (pytest-qt):** `_write_project_text` writes the editor text; overwrite creates a `.bak` with the prior content; Save with no path routes to Save As; Save As adopts the new path. Patch `QFileDialog.getSaveFileName`.
- **Generation flow (pytest-qt):** inject a **fake runner** that records the command and drives `on_output`/`on_finished`. Assert: no-exe path shows the locate dialog (patched) and doesn't run; Save-vs-Save-As prompt patched to "Save"; output folder dialog patched; the built command equals `build_generate_command(...)`; streamed lines land in the Audit panel as `[PHP] …`; a zero exit shows the success dialog (patched) and a nonzero exit shows the failure dialog (patched); Open Output Folder enabled only after a run (patch `QDesktopServices.openUrl`).
- **CRITICAL:** every `QMessageBox`, `QFileDialog`, and `QDesktopServices.openUrl` in a test MUST be patched — the suite runs headless with a `--timeout=60` guard, and any un-patched modal hangs. No real subprocess is ever launched in tests.

## 10. Components / isolation
- `generation/config.py` — exe-path persistence (AppData JSON), injectable base_dir. Depends only on `QStandardPaths` + `json`.
- `generation/runner.py` — pure `build_generate_command` + a thin `QProcess` `GeneratorRunner`. The pure builder holds the correctness; the runner is injectable so MainWindow tests never spawn a process.
- `main_window.py` — File Save/Save As handlers + Generation menu wiring (locate / generate / open-output), reusing the Audit panel for streamed output. Modal prompts (Save-vs-Save-As, result dialog, file/folder dialogs) live here and are patched in tests.
