# PGTP Editor — Generate PHP + File Save/Save As Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement File → Save / Save As (persisting the Raw XML editor buffer verbatim) and the Generation menu (Locate PHP Generator Executable, Generate PHP, Open Output Folder). Generate shells out to the real vendor generator via an injectable QProcess wrapper, streaming its output into the Audit panel and reporting success/failure.

**Architecture:** A new `pgtp_editor/generation/` package holds two Qt-light modules: `runner.py` (a *pure* `build_generate_command` plus a thin injectable `GeneratorRunner` wrapping `QProcess`) and `config.py` (exe-path persistence in AppData JSON, mirroring `schema_learning/storage.py` with an injectable `base_dir`). `MainWindow` gains two injectable `__init__` params (`generator_config_dir`, `generator_runner`) so tests use a `tmp_path` config dir and a **fake runner** — no real AppData writes and no real subprocess ever launched. Save/Save As write `center_stage.xml_editor.toPlainText()` and are reused by the Generate flow. Streamed generator lines are appended to the existing Audit panel with a `[PHP] ` prefix (mirroring the existing `[Find] ` / `[Schema] ` convention).

**Tech Stack:** Python 3.13, PySide6 (Qt widgets + `QProcess`/`QDesktopServices`), pytest, pytest-qt, pytest-timeout.

---

## Current-state facts (confirmed by reading this worktree)

- **No `pgtp_editor/generation/` package exists yet.** `pgtp_editor/` is a regular package (`__init__.py` present); `pgtp_editor/schema_learning/__init__.py` exists; `tests/__init__.py` and `tests/ui/__init__.py` exist.
- **`pgtp_editor/schema_learning/storage.py`** is the pattern to mirror: `_app_data_dir()` returns `Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))`; `schema_model_path(base_dir: Path | None = None)` returns `(base_dir or _app_data_dir()) / _MODEL_FILENAME`. No JSON there — `config.py` adds the JSON layer.
- **`MainWindow.__init__(self, schema_storage_dir: Path | None = None)`** (main_window.py:55). It stores `self._schema_storage_dir`. Creates `self.audit_panel = QListWidget()` (line 72), `self.center_stage = CenterStage()` (line 78), sets `self._current_project = None` / `self._current_project_path = None` (lines 97–98), then calls `self._build_menu_bar()` (line 102) as the **last** statement of `__init__`.
- **`self.center_stage.xml_editor`** is an `XmlEditor(QPlainTextEdit)` and exposes `toPlainText()` (inherited) and `setPlainText`. `navigate_to_line`, `highlight_error_line`, `set_line_wrap_enabled` also exist.
- **`ProjectModel`** (`pgtp_editor/model/nodes.py`) has `pages: list[PageNode]` and `tree: etree._ElementTree | None`. So the root `Project` element and its attributes are reachable as `self._current_project.tree.getroot()` → `.get("outputPath")`. No extra lxml parse needed to read `Project@outputPath`.
- **`_build_file_menu`** (main_window.py:484) currently has `self._add_stub_action(menu, "Save")` (line 490) and `self._add_stub_action(menu, "Save As...")` (line 491) as stubs. `"Open..."` is already wired to `self._open_project`.
- **`_build_generation_menu`** (main_window.py:623) currently has three stubs: `"Locate PHP Generator Executable..."`, `"Generate PHP..."`, `"Open Output Folder"`.
- **`_add_stub_action(self, menu, label)`** (main_window.py:563) → `add_stub_action(menu, label, self._not_implemented)`; `_not_implemented(label)` does `self.statusBar().showMessage(f"Not yet implemented: {label}", 5000)`.
- **Audit panel** is a `QListWidget`; Find All appends `QListWidgetItem` entries prefixed `"[Find] "` (constant `_FIND_RESULT_PREFIX = "[Find] "`, main_window.py:41). Schema entries are prefixed `"[Schema] "`. Clicking is routed through `self.audit_panel.itemClicked.connect(self._on_audit_item_clicked)` (line 89); items with no `Qt.ItemDataRole.UserRole` line data are click no-ops. We add a **new** prefix `"[PHP] "` for generator output.
- **The `.bak` convention** (main_window.py:459) is `backup_path = target_path + ".bak"` written via `shutil.copy2(target_path, backup_path)`. `shutil` is already imported at the top of main_window.py.
- **`QFileDialog` / `QMessageBox`** are already imported in main_window.py from `PySide6.QtWidgets`. `Qt` is imported from `PySide6.QtCore`. **`QProcess`, `QDesktopServices`, `QUrl` are NOT yet imported anywhere** in `pgtp_editor/` or `tests/`.
- **`_menu_helpers.py`**: `action_labels(menu)` (separators render as `"―"`), `find_top_menu(window, title)`, `find_action(menu, text)`.
- **`tests/ui/test_menus.py`**:
  - `test_file_menu_contents` asserts labels `["New Project","Open...","Open Recent","Save","Save As...","Close","―","Exit"]` — **stays valid** because we only re-wire Save / Save As, we do not rename them.
  - `test_generation_menu_contents` asserts `["Locate PHP Generator Executable...","―","Generate PHP...","―","Open Output Folder"]` — **stays valid** for the same reason.
  - `test_other_file_actions_show_stub_message` triggers `"New Project"` (still a stub) — unaffected.
- **Modal patching pattern in tests** (verified): `with patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:` and `with patch("pgtp_editor.ui.main_window.QFileDialog.getOpenFileName", return_value=(str(path), "PGTP files (*.pgtp)")):`. The suite runs headless offscreen (`conftest.py` sets `QT_QPA_PLATFORM=offscreen`) with `--timeout=60 --timeout-method=thread` (pyproject.toml). **Any un-patched `QMessageBox` / `QFileDialog` / `QDesktopServices.openUrl` blocks the modal event loop and the test is killed at 60 s.**
- **Injectable-dir test pattern** (from `test_annotate_schema_values_dialog.py`): construct with `schema_storage_dir=tmp_path` and assert against files under it. We mirror this with `generator_config_dir=tmp_path`.
- **Pre-existing failures (unrelated to this feature — DO NOT fix):** `python -m pytest -q` on this worktree reports exactly **3 failed, 551 passed, 23 skipped**. All 3 failures are missing gitignored sample fixtures:
  - `tests/schema_learning/test_real_samples_integration.py::test_both_real_sample_files_merge_into_one_model_without_raising`
  - `tests/schema_learning/test_real_samples_integration.py::test_generated_xsd_from_real_samples_is_well_formed_xml`
  - `tests/ui/test_open_project.py::test_open_real_sample_file_populates_editor_byte_for_byte`
  (each asserts `sample/dev_Ferrara.pgtp` / real-sample files exist). This is the baseline; the plan's "all pass" checks mean "no *new* failures beyond these 3".

---

## File Structure

- **Create** `pgtp_editor/generation/__init__.py` (empty package marker) — Task 1.
- **Create** `pgtp_editor/generation/runner.py` — `build_generate_command` (pure) + `GeneratorRunner` (Tasks 1, 3).
- **Create** `pgtp_editor/generation/config.py` — `generator_config_path` / `load_executable_path` / `save_executable_path` (Task 2).
- **Modify** `pgtp_editor/ui/main_window.py` — DI params, Save/Save As, Generation wiring (Tasks 4–8).
- **Create** `tests/generation/__init__.py`, `tests/generation/test_runner.py`, `tests/generation/test_config.py` (Tasks 1–3).
- **Create** `tests/ui/test_save_project.py`, `tests/ui/test_generation.py` (Tasks 5–8).

---

## Task 1: `generation` package + pure `build_generate_command`

**Files:**
- Create: `pgtp_editor/generation/__init__.py`
- Create: `pgtp_editor/generation/runner.py`
- Create: `tests/generation/__init__.py`
- Test: `tests/generation/test_runner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/generation/__init__.py` (empty file).

Create `tests/generation/test_runner.py`:

```python
from pgtp_editor.generation.runner import build_generate_command


def test_build_generate_command_basic():
    assert build_generate_command("gen.exe", "proj.pgtp", "out") == [
        "gen.exe",
        "proj.pgtp",
        "-output",
        "out",
        "-generate",
    ]


def test_build_generate_command_preserves_paths_with_spaces_without_quoting():
    # The list form is passed straight to QProcess.start(program, args), which
    # does its own argument quoting -- so spaces must be left untouched here.
    command = build_generate_command(
        r"C:\Program Files\PgGen\PgPHPGeneratorPro.exe",
        r"C:\My Projects\dev app.pgtp",
        r"C:\Out Folder\gen",
    )
    assert command == [
        r"C:\Program Files\PgGen\PgPHPGeneratorPro.exe",
        r"C:\My Projects\dev app.pgtp",
        "-output",
        r"C:\Out Folder\gen",
        "-generate",
    ]


def test_build_generate_command_is_five_elements_in_fixed_order():
    command = build_generate_command("e", "p", "o")
    assert len(command) == 5
    assert command[0] == "e"
    assert command[1] == "p"
    assert command[2] == "-output"
    assert command[3] == "o"
    assert command[4] == "-generate"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/generation/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgtp_editor.generation'`.

- [ ] **Step 3: Create the package + `build_generate_command`**

Create `pgtp_editor/generation/__init__.py` (empty file).

Create `pgtp_editor/generation/runner.py`:

```python
# pgtp_editor/generation/runner.py
"""Invoke the SQL Maestro PostgreSQL PHP Generator CLI.

Two pieces:
- `build_generate_command`: a PURE function assembling the exact argument
  vector. This holds the load-bearing correctness and is fully unit-tested.
- `GeneratorRunner`: a thin QProcess wrapper (added in a later task) that runs
  the command asynchronously, streaming merged stdout/stderr line-by-line so
  the UI never freezes. It is injectable into MainWindow so tests use a fake
  and never spawn a real process.

The confirmed CLI shape is:
    PgPHPGeneratorPro.exe "<project.pgtp>" -output "<output-folder>" -generate
"""
from __future__ import annotations


def build_generate_command(executable: str, pgtp_path: str, output_folder: str) -> list[str]:
    """Return the argument vector for a non-interactive generation run.

    Returned as a list (not a shell string) so QProcess.start(program, args)
    handles quoting -- paths with spaces need no manual escaping here.
    """
    return [executable, pgtp_path, "-output", output_folder, "-generate"]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/generation/test_runner.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/generation/__init__.py pgtp_editor/generation/runner.py tests/generation/__init__.py tests/generation/test_runner.py
git commit -m "feat: add generation package with pure build_generate_command"
```

---

## Task 2: `generation/config.py` — executable-path persistence

**Files:**
- Create: `pgtp_editor/generation/config.py`
- Test: `tests/generation/test_config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/generation/test_config.py`:

```python
import json

from pgtp_editor.generation.config import (
    generator_config_path,
    load_executable_path,
    save_executable_path,
)


def test_generator_config_path_uses_base_dir(tmp_path):
    assert generator_config_path(tmp_path) == tmp_path / "generator_config.json"


def test_save_then_load_round_trip(tmp_path):
    save_executable_path(r"C:\PgGen\PgPHPGeneratorPro.exe", base_dir=tmp_path)
    assert load_executable_path(base_dir=tmp_path) == r"C:\PgGen\PgPHPGeneratorPro.exe"


def test_save_creates_the_directory_if_missing(tmp_path):
    nested = tmp_path / "does" / "not" / "exist"
    save_executable_path("gen.exe", base_dir=nested)
    assert (nested / "generator_config.json").exists()
    assert load_executable_path(base_dir=nested) == "gen.exe"


def test_save_writes_expected_json_shape(tmp_path):
    save_executable_path("gen.exe", base_dir=tmp_path)
    data = json.loads((tmp_path / "generator_config.json").read_text(encoding="utf-8"))
    assert data == {"executable_path": "gen.exe"}


def test_load_returns_none_when_file_absent(tmp_path):
    assert load_executable_path(base_dir=tmp_path) is None


def test_load_returns_none_when_json_malformed(tmp_path):
    (tmp_path / "generator_config.json").write_text("{not json", encoding="utf-8")
    assert load_executable_path(base_dir=tmp_path) is None


def test_load_returns_none_when_key_missing(tmp_path):
    (tmp_path / "generator_config.json").write_text(
        json.dumps({"something_else": "x"}), encoding="utf-8"
    )
    assert load_executable_path(base_dir=tmp_path) is None


def test_save_merges_into_existing_json_preserving_other_keys(tmp_path):
    (tmp_path / "generator_config.json").write_text(
        json.dumps({"other": "keep"}), encoding="utf-8"
    )
    save_executable_path("gen.exe", base_dir=tmp_path)
    data = json.loads((tmp_path / "generator_config.json").read_text(encoding="utf-8"))
    assert data == {"other": "keep", "executable_path": "gen.exe"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/generation/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgtp_editor.generation.config'`.

- [ ] **Step 3: Create `config.py`**

Create `pgtp_editor/generation/config.py`:

```python
# pgtp_editor/generation/config.py
"""Per-user persistence of the PHP Generator executable path.

Mirrors pgtp_editor/schema_learning/storage.py: a `base_dir` override (used by
tests with a tmp_path) falls back to the OS AppData location. Stored as a small
JSON object {"executable_path": "..."}; load tolerates an absent, unreadable,
malformed, or key-missing file by returning None (never raises).
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_CONFIG_FILENAME = "generator_config.json"
_EXECUTABLE_KEY = "executable_path"


def _app_data_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


def generator_config_path(base_dir: Path | None = None) -> Path:
    return (base_dir or _app_data_dir()) / _CONFIG_FILENAME


def load_executable_path(base_dir: Path | None = None) -> str | None:
    """Return the stored executable path, or None if it cannot be determined
    (file absent / unreadable / not valid JSON / key missing)."""
    path = generator_config_path(base_dir)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get(_EXECUTABLE_KEY)
    return value if isinstance(value, str) else None


def save_executable_path(path: str, base_dir: Path | None = None) -> None:
    """Persist `path` under the executable key, creating the directory and
    preserving any other keys already present in the file."""
    config_path = generator_config_path(base_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    try:
        existing = config_path.read_text(encoding="utf-8")
        loaded = json.loads(existing)
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError, TypeError):
        data = {}

    data[_EXECUTABLE_KEY] = path
    config_path.write_text(json.dumps(data), encoding="utf-8")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/generation/test_config.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/generation/config.py tests/generation/test_config.py
git commit -m "feat: persist PHP Generator executable path in AppData JSON"
```

---

## Task 3: `GeneratorRunner` QProcess wrapper

**Files:**
- Modify: `pgtp_editor/generation/runner.py` (add `GeneratorRunner`)
- Test: `tests/generation/test_runner.py` (add construction + signature tests)

> The `QProcess` event loop is intentionally NOT driven in tests (that would spawn a real process / spin a loop under `--timeout`). This task pins the class's *shape* — its `run(command, on_output, on_finished)` signature — which every MainWindow generation test then satisfies with a **fake runner** exposing the identical signature. The real wrapper's live behavior is exercised only by hand against the actual vendor exe.

- [ ] **Step 1: Add the failing tests**

Append to `tests/generation/test_runner.py`:

```python
import inspect

from pgtp_editor.generation.runner import GeneratorRunner


def test_generator_runner_is_constructible(qtbot):
    runner = GeneratorRunner()
    assert runner is not None


def test_generator_runner_run_signature_is_the_injection_contract():
    # MainWindow injects a fake with this exact signature; keep them in lockstep.
    params = list(inspect.signature(GeneratorRunner.run).parameters)
    assert params == ["self", "command", "on_output", "on_finished"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/generation/test_runner.py -v`
Expected: FAIL — `ImportError: cannot import name 'GeneratorRunner'`.

- [ ] **Step 3: Add `GeneratorRunner` to `runner.py`**

Add to `pgtp_editor/generation/runner.py` (after `build_generate_command`; add the imports at the top of the file):

```python
from collections.abc import Callable

from PySide6.QtCore import QObject, QProcess
```

```python
class GeneratorRunner(QObject):
    """Runs a generator command asynchronously via QProcess, streaming merged
    stdout+stderr to `on_output` line-by-line and calling `on_finished(exit_code)`
    when it ends. Injectable into MainWindow (default: a real instance); tests
    inject a fake exposing the same `run(command, on_output, on_finished)`.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._on_output: Callable[[str], None] = lambda line: None
        self._on_finished: Callable[[int], None] = lambda code: None

    def run(
        self,
        command: list[str],
        on_output: Callable[[str], None],
        on_finished: Callable[[int], None],
    ) -> None:
        self._on_output = on_output
        self._on_finished = on_finished

        process = QProcess(self)
        # Merge stderr into stdout so all generator chatter is captured in order.
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._emit_output)
        process.finished.connect(self._emit_finished)
        # A failure to start (e.g. exe no longer exists) never emits finished;
        # map it to a diagnostic line + a nonzero finish so callers see a failure.
        process.errorOccurred.connect(self._on_error)
        self._process = process

        program, *args = command
        process.start(program, args)

    def _emit_output(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            self._on_output(line)

    def _emit_finished(self, exit_code: int, _exit_status) -> None:
        self._on_finished(int(exit_code))

    def _on_error(self, _error) -> None:
        if self._process is None:
            return
        self._on_output(f"Failed to start generator: {self._process.errorString()}")
        self._on_finished(1)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/generation/test_runner.py -v`
Expected: PASS (5 passed — 3 from Task 1 + 2 new).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/generation/runner.py tests/generation/test_runner.py
git commit -m "feat: add injectable GeneratorRunner QProcess wrapper"
```

---

## Task 4: Inject `generator_config_dir` and `generator_runner` into `MainWindow`

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (`__init__` signature + stored attrs + imports)
- Test: `tests/ui/test_generation.py` (new file)

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_generation.py`:

```python
from pgtp_editor.generation.runner import GeneratorRunner
from pgtp_editor.ui.main_window import MainWindow


class FakeRunner:
    """Records the command and lets a test drive on_output/on_finished by hand.
    Mirrors GeneratorRunner.run's signature exactly (no real process spawned)."""

    def __init__(self):
        self.commands = []
        self._on_output = None
        self._on_finished = None

    def run(self, command, on_output, on_finished):
        self.commands.append(command)
        self._on_output = on_output
        self._on_finished = on_finished

    def emit_output(self, line):
        self._on_output(line)

    def emit_finished(self, exit_code):
        self._on_finished(exit_code)


def test_defaults_to_a_real_generator_runner(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    assert isinstance(window._generator_runner, GeneratorRunner)


def test_injected_runner_and_config_dir_are_stored(qtbot, tmp_path):
    fake = FakeRunner()
    window = MainWindow(generator_config_dir=tmp_path, generator_runner=fake)
    qtbot.addWidget(window)
    assert window._generator_runner is fake
    assert window._generator_config_dir == tmp_path


def test_output_folder_starts_unset(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    assert window._current_output_folder is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/ui/test_generation.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'generator_config_dir'`.

- [ ] **Step 3: Add imports + widen the signature**

In `pgtp_editor/ui/main_window.py`:

1. Add near the other `pgtp_editor` imports:

```python
from pgtp_editor.generation.config import load_executable_path, save_executable_path
from pgtp_editor.generation.runner import GeneratorRunner, build_generate_command
```

2. Add to the `from PySide6.QtCore import ...` line (currently `Qt, QTimer`) → add `QUrl`:

```python
from PySide6.QtCore import Qt, QTimer, QUrl
```

3. Add a new import for `QDesktopServices` (place with the Qt imports):

```python
from PySide6.QtGui import QDesktopServices
```

4. Add the `[PHP]` prefix constant next to `_FIND_RESULT_PREFIX` (main_window.py:41):

```python
_GENERATOR_OUTPUT_PREFIX = "[PHP] "
```

5. Change the `__init__` signature (main_window.py:55) from:

```python
    def __init__(self, schema_storage_dir: Path | None = None):
        super().__init__()
        self._schema_storage_dir = schema_storage_dir
```

to:

```python
    def __init__(
        self,
        schema_storage_dir: Path | None = None,
        generator_config_dir: Path | None = None,
        generator_runner=None,
    ):
        super().__init__()
        self._schema_storage_dir = schema_storage_dir
        self._generator_config_dir = generator_config_dir
        self._generator_runner = generator_runner if generator_runner is not None else GeneratorRunner()
        self._current_output_folder = None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ui/test_generation.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `python -m pytest -q`
Expected: 3 failed, (554)+ passed — the only failures are the 3 pre-existing sample-fixture ones listed in Current-state facts. No new failures.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_generation.py
git commit -m "feat: inject generator_config_dir and generator_runner into MainWindow"
```

---

## Task 5: File → Save / Save As

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (`_write_project_text`, `_save_project`, `_save_project_as`; wire the two File-menu actions)
- Test: `tests/ui/test_save_project.py` (new file)

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_save_project.py`:

```python
from unittest.mock import patch

from pgtp_editor.ui.main_window import MainWindow


def _window(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    return window


def test_write_project_text_writes_editor_buffer_verbatim(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("<Project/>\n")
    target = tmp_path / "out.pgtp"

    window._write_project_text(str(target))

    assert target.read_text(encoding="utf-8") == "<Project/>\n"


def test_write_project_text_makes_bak_on_overwrite(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    target = tmp_path / "out.pgtp"
    target.write_text("OLD CONTENT", encoding="utf-8")
    window.center_stage.xml_editor.setPlainText("NEW CONTENT")

    window._write_project_text(str(target))

    assert target.read_text(encoding="utf-8") == "NEW CONTENT"
    assert (tmp_path / "out.pgtp.bak").read_text(encoding="utf-8") == "OLD CONTENT"


def test_write_project_text_no_bak_when_file_absent(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    target = tmp_path / "fresh.pgtp"
    window.center_stage.xml_editor.setPlainText("data")

    window._write_project_text(str(target))

    assert not (tmp_path / "fresh.pgtp.bak").exists()


def test_save_with_no_current_path_routes_to_save_as(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window._current_project_path is None
    window.center_stage.xml_editor.setPlainText("data")
    target = tmp_path / "saved.pgtp"

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(target), "PGTP files (*.pgtp)"),
    ):
        window._save_project()

    assert target.read_text(encoding="utf-8") == "data"
    assert window._current_project_path == str(target)


def test_save_with_existing_path_writes_without_dialog(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    target = tmp_path / "existing.pgtp"
    target.write_text("old", encoding="utf-8")
    window._current_project_path = str(target)
    window.center_stage.xml_editor.setPlainText("updated")

    # No dialog should be invoked; if it were, the test would hang -- so the
    # absence of a patch here is itself the assertion that none is shown.
    window._save_project()

    assert target.read_text(encoding="utf-8") == "updated"
    assert window.statusBar().currentMessage() == "Saved existing.pgtp"


def test_save_as_adopts_the_new_path(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("data")
    target = tmp_path / "as.pgtp"

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(target), "PGTP files (*.pgtp)"),
    ):
        window._save_project_as()

    assert window._current_project_path == str(target)
    assert window.statusBar().currentMessage() == "Saved as as.pgtp"


def test_save_as_cancel_is_a_noop(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._current_project_path = None
    window.center_stage.xml_editor.setPlainText("data")

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName",
        return_value=("", ""),
    ):
        window._save_project_as()

    assert window._current_project_path is None


def test_save_surfaces_os_error_and_leaves_buffer_untouched(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._current_project_path = str(tmp_path / "x.pgtp")
    window.center_stage.xml_editor.setPlainText("keep me")

    with patch(
        "pgtp_editor.ui.main_window.MainWindow._write_project_text",
        side_effect=OSError("disk full"),
    ), patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window._save_project()

    assert mock_critical.called
    assert window.center_stage.xml_editor.toPlainText() == "keep me"


def test_file_menu_save_actions_are_wired(qtbot, tmp_path):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("data")
    target = tmp_path / "menu.pgtp"
    file_menu = find_top_menu(window, "File")

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(target), "PGTP files (*.pgtp)"),
    ):
        find_action(file_menu, "Save").trigger()

    assert target.read_text(encoding="utf-8") == "data"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/ui/test_save_project.py -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_write_project_text'` (and the menu-wiring test triggers the old stub, producing a `"Not yet implemented: Save"` status instead of writing).

- [ ] **Step 3: Add the Save handlers and wire the menu**

In `pgtp_editor/ui/main_window.py`, add these methods to `MainWindow` (place them just before `_build_menu_bar`):

```python
    def _write_project_text(self, path) -> None:
        """Write the Raw XML editor buffer verbatim to `path` as UTF-8. If
        `path` already exists, copy it to `path + '.bak'` first (same .bak
        convention as Apply-to-Target)."""
        if Path(path).exists():
            shutil.copy2(path, path + ".bak")
        Path(path).write_text(self.center_stage.xml_editor.toPlainText(), encoding="utf-8")

    def _save_project(self) -> None:
        if not self._current_project_path:
            self._save_project_as()
            return
        try:
            self._write_project_text(self._current_project_path)
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save:\n\n{exc}")
            return
        self.statusBar().showMessage(f"Saved {Path(self._current_project_path).name}", 5000)

    def _save_project_as(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save Project As", "", "PGTP files (*.pgtp)"
        )
        if not path:
            return
        try:
            self._write_project_text(path)
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save:\n\n{exc}")
            return
        self._current_project_path = path
        self.statusBar().showMessage(f"Saved as {Path(path).name}", 5000)
```

In `_build_file_menu` (main_window.py:490–491), replace:

```python
        self._add_stub_action(menu, "Save")
        self._add_stub_action(menu, "Save As...")
```

with:

```python
        save_action = menu.addAction("Save")
        save_action.triggered.connect(self._save_project)
        save_as_action = menu.addAction("Save As...")
        save_as_action.triggered.connect(self._save_project_as)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ui/test_save_project.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Confirm the menu-contents test still holds**

Run: `python -m pytest tests/ui/test_menus.py -v -k "file_menu"`
Expected: PASS — `test_file_menu_contents` labels are unchanged (Save / Save As... kept their labels); `test_other_file_actions_show_stub_message` still triggers `"New Project"` (still a stub).

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_save_project.py
git commit -m "feat: implement File Save / Save As with .bak-on-overwrite"
```

---

## Task 6: Generation → Locate PHP Generator Executable

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (`_locate_generator`; wire the Generation-menu action)
- Test: `tests/ui/test_generation.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_generation.py`:

```python
from unittest.mock import patch

from pgtp_editor.generation.config import load_executable_path


def test_locate_generator_saves_chosen_path(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    exe = tmp_path / "PgPHPGeneratorPro.exe"
    exe.write_text("", encoding="utf-8")

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(exe), "Executables (*.exe)"),
    ):
        window._locate_generator()

    assert load_executable_path(base_dir=tmp_path) == str(exe)
    assert window.statusBar().currentMessage() == f"PHP Generator set: {exe.name}"


def test_locate_generator_cancel_is_a_noop(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=("", ""),
    ):
        window._locate_generator()

    assert load_executable_path(base_dir=tmp_path) is None


def test_locate_generator_menu_action_is_wired(qtbot, tmp_path):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    exe = tmp_path / "gen.exe"
    exe.write_text("", encoding="utf-8")
    menu = find_top_menu(window, "Generation")

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(exe), "Executables (*.exe)"),
    ):
        find_action(menu, "Locate PHP Generator Executable...").trigger()

    assert load_executable_path(base_dir=tmp_path) == str(exe)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/ui/test_generation.py -v -k "locate"`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_locate_generator'` (and the menu action still triggers the stub).

- [ ] **Step 3: Add the handler and wire the menu**

In `pgtp_editor/ui/main_window.py`, add to `MainWindow` (group the generation handlers together — place before `_build_help_menu`):

```python
    def _locate_generator(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Locate PHP Generator Executable", "", "Executables (*.exe);;All files (*)"
        )
        if not path:
            return
        save_executable_path(path, base_dir=self._generator_config_dir)
        self.statusBar().showMessage(f"PHP Generator set: {Path(path).name}", 5000)
```

In `_build_generation_menu` (main_window.py:623), replace:

```python
        self._add_stub_action(menu, "Locate PHP Generator Executable...")
```

with:

```python
        locate_action = menu.addAction("Locate PHP Generator Executable...")
        locate_action.triggered.connect(self._locate_generator)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ui/test_generation.py -v -k "locate"`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_generation.py
git commit -m "feat: implement Generation > Locate PHP Generator Executable"
```

---

## Task 7: Generation → Generate PHP flow

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (`_generate_php`, `_project_output_folder_default`, `_clear_generator_output`; wire the Generate action)
- Test: `tests/ui/test_generation.py` (append)

> **MODAL SAFETY (restated):** every test here patches `QMessageBox.information` / `QMessageBox.question` / `QMessageBox.critical` and `QFileDialog.getExistingDirectory`, and injects the `FakeRunner`. No real subprocess, no real modal. An un-patched modal would be killed by the 60 s timeout.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_generation.py`:

```python
from PySide6.QtWidgets import QMessageBox

from pgtp_editor.generation.runner import build_generate_command


def _configured_window(qtbot, tmp_path, exe_name="gen.exe"):
    """A window with a configured exe and a fake runner injected."""
    fake = FakeRunner()
    window = MainWindow(generator_config_dir=tmp_path, generator_runner=fake)
    qtbot.addWidget(window)
    exe = tmp_path / exe_name
    exe.write_text("", encoding="utf-8")
    from pgtp_editor.generation.config import save_executable_path
    save_executable_path(str(exe), base_dir=tmp_path)
    return window, fake, exe


def test_generate_with_no_open_project_stops(qtbot, tmp_path):
    fake = FakeRunner()
    window = MainWindow(generator_config_dir=tmp_path, generator_runner=fake)
    qtbot.addWidget(window)
    # editor empty and no current project
    window._generate_php()
    assert fake.commands == []


def test_generate_with_no_configured_exe_shows_info_and_stops(qtbot, tmp_path):
    fake = FakeRunner()
    window = MainWindow(generator_config_dir=tmp_path, generator_runner=fake)
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("<Project/>")

    with patch("pgtp_editor.ui.main_window.QMessageBox.information") as mock_info:
        window._generate_php()

    assert mock_info.called
    assert fake.commands == []


def test_generate_happy_path_builds_and_runs_command(qtbot, tmp_path):
    window, fake, exe = _configured_window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("<Project/>")
    project_path = tmp_path / "proj.pgtp"
    window._current_project_path = str(project_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._generate_php()

    assert fake.commands == [build_generate_command(str(exe), str(project_path), str(out_dir))]
    assert window._current_output_folder == str(out_dir)


def test_generate_cancel_at_save_prompt_stops(qtbot, tmp_path):
    window, fake, exe = _configured_window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("<Project/>")
    window._current_project_path = str(tmp_path / "proj.pgtp")

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Cancel,
    ):
        window._generate_php()

    assert fake.commands == []


def test_generate_cancel_at_output_folder_stops(qtbot, tmp_path):
    window, fake, exe = _configured_window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("<Project/>")
    window._current_project_path = str(tmp_path / "proj.pgtp")

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value="",
    ):
        window._generate_php()

    assert fake.commands == []


def test_generate_streams_output_lines_into_audit_panel(qtbot, tmp_path):
    window, fake, exe = _configured_window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("<Project/>")
    window._current_project_path = str(tmp_path / "proj.pgtp")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._generate_php()

    fake.emit_output("Generating page 1")
    fake.emit_output("Generating page 2")

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert "[PHP] Generating page 1" in texts
    assert "[PHP] Generating page 2" in texts


def test_generate_output_folder_prefilled_from_project_output_path(qtbot, tmp_path):
    from pgtp_editor.model.parser import load_project_from_text

    window, fake, exe = _configured_window(qtbot, tmp_path)
    out_attr = str(tmp_path / "declared_out")
    xml = f'<Project outputPath="{out_attr}"><Presentation><Pages/></Presentation></Project>'
    window.center_stage.xml_editor.setPlainText(xml)
    window._current_project = load_project_from_text(xml)
    window._current_project_path = str(tmp_path / "proj.pgtp")

    captured = {}

    def fake_dir(parent, caption, directory):
        captured["directory"] = directory
        return ""

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        side_effect=fake_dir,
    ):
        window._generate_php()

    assert captured["directory"] == out_attr
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/ui/test_generation.py -v -k "generate"`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_generate_php'` (and the menu Generate action still hits the stub).

- [ ] **Step 3: Add the flow + wire the menu**

> Implement Task 8's `_on_generation_finished` / `_append_generator_output` at the same time as this task (they are referenced by `_generate_php`), so the module imports cleanly. Both tasks are committed conceptually together; the split is only for test grouping.

In `pgtp_editor/ui/main_window.py`, add to `MainWindow` (after `_locate_generator`):

```python
    def _project_output_folder_default(self) -> str:
        """Prefill for the output-folder dialog: the project's Project@outputPath
        if readable, else the directory of the current project file, else ''."""
        project = self._current_project
        if project is not None and project.tree is not None:
            root = project.tree.getroot()
            if root is not None:
                declared = root.get("outputPath")
                if declared:
                    return declared
        if self._current_project_path:
            return str(Path(self._current_project_path).parent)
        return ""

    def _clear_generator_output(self) -> None:
        """Remove only prior [PHP]-prefixed Audit entries (leave [Find]/[Schema])."""
        for row in range(self.audit_panel.count() - 1, -1, -1):
            if self.audit_panel.item(row).text().startswith(_GENERATOR_OUTPUT_PREFIX):
                self.audit_panel.takeItem(row)

    def _generate_php(self) -> None:
        # 1. Require an open project (a tracked model or non-empty editor).
        if self._current_project is None and not self.center_stage.xml_editor.toPlainText().strip():
            self.statusBar().showMessage("Open a project before generating.", 5000)
            return

        # 2. Require a configured executable.
        exe = load_executable_path(base_dir=self._generator_config_dir)
        if exe is None:
            QMessageBox.information(
                self,
                "Generate PHP",
                "Locate the PHP Generator executable first (Generation > Locate PHP Generator Executable...).",
            )
            return

        # 3. Save vs Save As vs Cancel so on-disk content matches the editor.
        choice = QMessageBox.question(
            self,
            "Save Before Generating",
            "The generator reads the project from disk. Save the current editor "
            "contents before generating?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.SaveAll  # used as the "Save As..." button
            | QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return
        if choice == QMessageBox.StandardButton.SaveAll:
            self._save_project_as()
        else:
            self._save_project()  # delegates to Save As when there's no path yet
        if not self._current_project_path:
            return  # Save As was cancelled -> nothing on disk to generate from

        # 4. Output folder (prefilled).
        output_folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self._project_output_folder_default()
        )
        if not output_folder:
            return

        # 5. Run via the injected runner.
        self._clear_generator_output()
        command = build_generate_command(exe, self._current_project_path, output_folder)
        self._current_output_folder = output_folder
        self.statusBar().showMessage("Generating…")
        self._generator_runner.run(
            command,
            on_output=self._append_generator_output,
            on_finished=self._on_generation_finished,
        )

    def _append_generator_output(self, line: str) -> None:
        self.audit_panel.addItem(f"{_GENERATOR_OUTPUT_PREFIX}{line}")
```

> Note: `QMessageBox.SaveAll` is repurposed as the "Save As…" third button (it renders as "Save All"). If a distinct labelled button is preferred, a `QMessageBox` instance with `addButton` can replace the static `.question` call; the test patches `QMessageBox.question` and asserts on the returned enum, so keep the static form for testability.

In `_build_generation_menu`, replace:

```python
        self._add_stub_action(menu, "Generate PHP...")
```

with:

```python
        generate_action = menu.addAction("Generate PHP...")
        generate_action.triggered.connect(self._generate_php)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ui/test_generation.py -v -k "generate"`
Expected: PASS (7 passed). (Requires `_on_generation_finished` from Task 8 to exist — implement it now per the note above.)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_generation.py
git commit -m "feat: implement Generate PHP flow with save prompt, output folder, streaming"
```

---

## Task 8: Generation finish handler + Open Output Folder

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (`_on_generation_finished`, `_open_output_folder`; wire Open Output Folder action)
- Test: `tests/ui/test_generation.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_generation.py`:

```python
def _run_generation(window, fake, tmp_path):
    from PySide6.QtWidgets import QMessageBox
    window.center_stage.xml_editor.setPlainText("<Project/>")
    window._current_project_path = str(tmp_path / "proj.pgtp")
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._generate_php()
    return out_dir


def test_zero_exit_shows_success_dialog_and_summary(qtbot, tmp_path):
    window, fake, exe = _configured_window(qtbot, tmp_path)
    _run_generation(window, fake, tmp_path)

    with patch("pgtp_editor.ui.main_window.QMessageBox.information") as mock_info:
        fake.emit_finished(0)

    assert mock_info.called
    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert "[PHP] Generation finished (exit 0)" in texts
    assert window.statusBar().currentMessage() == "Generation succeeded"


def test_nonzero_exit_shows_failure_dialog(qtbot, tmp_path):
    window, fake, exe = _configured_window(qtbot, tmp_path)
    _run_generation(window, fake, tmp_path)

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        fake.emit_finished(3)

    assert mock_critical.called
    assert window.statusBar().currentMessage() == "Generation failed (exit 3)"


def test_open_output_folder_before_any_run_is_a_noop(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    assert window._current_output_folder is None

    with patch("pgtp_editor.ui.main_window.QDesktopServices.openUrl") as mock_open:
        window._open_output_folder()

    assert not mock_open.called


def test_open_output_folder_after_run_opens_the_folder(qtbot, tmp_path):
    window, fake, exe = _configured_window(qtbot, tmp_path)
    out_dir = _run_generation(window, fake, tmp_path)

    with patch("pgtp_editor.ui.main_window.QDesktopServices.openUrl") as mock_open:
        window._open_output_folder()

    assert mock_open.called
    opened_url = mock_open.call_args.args[0]
    assert opened_url.toLocalFile().rstrip("/") == str(out_dir).replace("\\", "/").rstrip("/")


def test_open_output_folder_menu_action_is_wired(qtbot, tmp_path):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window, fake, exe = _configured_window(qtbot, tmp_path)
    _run_generation(window, fake, tmp_path)
    menu = find_top_menu(window, "Generation")

    with patch("pgtp_editor.ui.main_window.QDesktopServices.openUrl") as mock_open:
        find_action(menu, "Open Output Folder").trigger()

    assert mock_open.called
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/ui/test_generation.py -v -k "exit or open_output"`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_on_generation_finished'` / `_open_output_folder` (and the Open Output Folder menu action still hits the stub). (If you already added `_on_generation_finished` during Task 7 per its note, that part will already exist; add `_open_output_folder` and the wiring here.)

- [ ] **Step 3: Add the handlers + wire the menu**

In `pgtp_editor/ui/main_window.py`, add to `MainWindow` (after `_append_generator_output`):

```python
    def _on_generation_finished(self, exit_code: int) -> None:
        self.audit_panel.addItem(f"{_GENERATOR_OUTPUT_PREFIX}Generation finished (exit {exit_code})")
        if exit_code == 0:
            QMessageBox.information(self, "Generate PHP", "Generation succeeded.")
            self.statusBar().showMessage("Generation succeeded", 5000)
        else:
            QMessageBox.critical(
                self,
                "Generate PHP",
                f"Generation failed (exit {exit_code}). See the Audit / Problems panel for the generator log.",
            )
            self.statusBar().showMessage(f"Generation failed (exit {exit_code})", 5000)

    def _open_output_folder(self) -> None:
        if not self._current_output_folder:
            self.statusBar().showMessage("No output folder yet — run Generate PHP first.", 5000)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._current_output_folder))
```

In `_build_generation_menu`, replace:

```python
        self._add_stub_action(menu, "Open Output Folder")
```

with:

```python
        open_output_action = menu.addAction("Open Output Folder")
        open_output_action.triggered.connect(self._open_output_folder)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ui/test_generation.py -v`
Expected: PASS (all generation tests, including the earlier Tasks 4/6/7 ones).

- [ ] **Step 5: Confirm the Generation menu-contents test still holds**

Run: `python -m pytest tests/ui/test_menus.py -v -k "generation"`
Expected: PASS — `test_generation_menu_contents` labels unchanged (only wiring changed).

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_generation.py
git commit -m "feat: report generation result and wire Open Output Folder"
```

---

## Task 9: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the entire suite**

Run: `python -m pytest -q`

Expected: **3 failed, (563)+ passed, 23 skipped**. The ONLY failures must be the three pre-existing, unrelated missing-sample-fixture tests documented in Current-state facts:
- `tests/schema_learning/test_real_samples_integration.py::test_both_real_sample_files_merge_into_one_model_without_raising`
- `tests/schema_learning/test_real_samples_integration.py::test_generated_xsd_from_real_samples_is_well_formed_xml`
- `tests/ui/test_open_project.py::test_open_real_sample_file_populates_editor_byte_for_byte`

These depend on gitignored real-sample `.pgtp` files absent from this worktree and are **out of scope** — do NOT attempt to fix them. Any *other* failure or a hang (a test killed at the 60 s `--timeout`) indicates an un-patched modal or a real subprocess and must be fixed before this task is considered done.

- [ ] **Step 2: Confirm no new hangs and the generation/save suites are green in isolation**

Run: `python -m pytest tests/generation tests/ui/test_generation.py tests/ui/test_save_project.py tests/ui/test_menus.py -v`
Expected: all pass (no timeouts).

- [ ] **Step 3: Commit (if any lint/formatting touch-ups were needed; otherwise skip)**

```bash
git add -A
git commit -m "test: full-suite green for Generate PHP + Save/Save As (pre-existing sample failures unrelated)"
```

---

## Requirement → task traceability (self-review)

- **§4 config.py** — `generator_config_path` / `load_executable_path` / `save_executable_path`, injectable `base_dir`, JSON `{"executable_path": ...}`, `load` returns None when absent/malformed/key-missing, `save` creates the dir + merges → **Task 2**.
- **§4 MainWindow injectable `generator_config_dir`** (same as `schema_storage_dir`) → **Task 4**.
- **§5 pure `build_generate_command`** returning the exact 5-element list incl. paths-with-spaces → **Task 1**.
- **§5 `GeneratorRunner`** wrapping `QProcess` (MergedChannels, readyRead→on_output, finished→on_finished, start-failure→on_finished nonzero + diagnostic), injectable, fake used in tests → **Task 3** (class) + **Tasks 4, 7, 8** (injection + FakeRunner usage).
- **§6 Save/Save As** — `_write_project_text` (UTF-8 verbatim, `.bak` on overwrite), Save routes to Save As when no path, Save As adopts path, OSError→critical, File-menu wiring, Undo/Redo/etc. stay stubs → **Task 5**.
- **§7 Locate** — `getOpenFileName` (`Executables (*.exe);;All files (*)`), `save_executable_path`, status message, wiring → **Task 6**.
- **§7 Generate flow** — (1) require open project, (2) require configured exe else info dialog+stop, (3) Save/Save As/Cancel `QMessageBox`, (4) output folder prefilled from `Project@outputPath` else project dir, (5) build command + clear prior `[PHP]` + run via injected runner + remember folder + `Generating…`; stream `[PHP] `-prefixed lines; finish→summary line + success/failure dialog + status → **Tasks 7, 8**.
- **§7 Open Output Folder** — `QDesktopServices.openUrl(QUrl.fromLocalFile(...))`, no-op/disabled until a run → **Task 8**.
- **§8 error handling** — nonzero exit surfaced as failure (never swallowed), full log visible in Audit, Save OSError→critical, start-failure mapped through finished → **Tasks 3, 5, 8**.
- **§9 testing** — config unit (tmp_path), runner unit (incl. spaces), Save/Save As pytest-qt, generation flow with fake runner + patched modals, `[PHP]` streaming, zero/nonzero exit dialogs, Open Output Folder only after a run → **Tasks 1–3, 5–8**.
- **§9 MODAL SAFETY / no real subprocess** — every generation/save test patches `QMessageBox.*` / `QFileDialog.*` / `QDesktopServices.openUrl` and injects `FakeRunner`; stated explicitly in Tasks 5, 7, 8 headers → satisfied.
- **Full-suite verification + pre-existing 3 sample failures noted as unrelated** → **Task 9**.

## Consistency check (names used identically across tasks)

- `self._generator_runner`, `self._generator_config_dir`, `self._current_output_folder`, `self._current_project_path`, `self._current_project` — all introduced in Task 4 and reused verbatim thereafter.
- Handlers: `_write_project_text`, `_save_project`, `_save_project_as`, `_locate_generator`, `_generate_php`, `_append_generator_output`, `_on_generation_finished`, `_open_output_folder`, `_project_output_folder_default`, `_clear_generator_output`.
- Constant `_GENERATOR_OUTPUT_PREFIX = "[PHP] "` (Task 4), consumed by `_append_generator_output`, `_clear_generator_output`, `_on_generation_finished`.
- The fake runner's `run(self, command, on_output, on_finished)` matches `GeneratorRunner.run`'s signature exactly (pinned by `test_generator_runner_run_signature_is_the_injection_contract` in Task 3).

## Notes / resolved spec ambiguities

- **"Editor empty" (§7.1)** interpreted as `toPlainText().strip() == ""`.
- **"Save must yield a concrete path; if still none treat as Save As" (§7.3)** — `_save_project` already delegates to Save As when path is None; `_generate_php` re-checks `self._current_project_path` after the save step and stops if still None (covers a cancelled Save As).
- **`Project@outputPath` (§7.4)** read via `self._current_project.tree.getroot().get("outputPath")` (the `ProjectModel.tree` is retained by the parser — no extra lxml parse), falling back to the project file's directory.
- **Save-vs-Save-As 3-way prompt** implemented with static `QMessageBox.question` using `Save | SaveAll | Cancel` (SaveAll repurposed as "Save As…") so tests can patch `QMessageBox.question` and assert on the returned enum. A custom-button `QMessageBox` instance is a valid alternative if distinct labels are required, but keep it patchable.
