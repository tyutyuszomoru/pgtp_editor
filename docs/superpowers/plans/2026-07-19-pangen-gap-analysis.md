# panGen + rePHPgen Gap Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three Generation-menu actions — panGen (emit our PHP), rePHPgen (gap JSON of ours-vs-vendor deltas), Save reJSON — backed by a new `python -m re_phpgen` CLI, per spec `docs/superpowers/specs/2026-07-19-pgtp-editor-pangen-gap-analysis-design.md`.

**Architecture:** Two repos. The `re_phpgen` repo (`C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen`, own git repo/venv) gains library functions (`gap.build_gap_report`, `pangen.emit_project`) and a CLI wrapping them. The editor calls the CLI as a subprocess through the existing injectable `GeneratorRunner`, chaining pangen → analyze for the rePHPgen action. The editor never imports re_phpgen and never runs the vendor exe (the vendor baseline is generated manually from the GUI).

**Tech Stack:** Python stdlib (`argparse`, `difflib`, `json`) + existing re_phpgen modules; PySide6 in the editor. Tests: pytest (+ pytest-qt patterns already in the editor; `$env:QT_QPA_PLATFORM='offscreen'`).

**Verified API anchors (2026-07-19):**
- re_phpgen: `catalog.top_level_pages(pgtp) -> list[PageInfo(file_name, table_name, page_type)]`, `skeleton.emit_skeleton(slots: dict) -> str`, `skeleton.slots_for_page(pgtp, page) -> dict`, `handlers.handler_texts(pgtp)`, `handlers.mask_handler_code(text, texts)`, `masker.mask_method_bodies(text)`, `normalizer.normalize(text)`. `scripts/skeleton_coverage.py` holds `CAUSE_MARKERS` as a list of `(tag, marker)` tuples — Task 1 moves it into the library.
- editor: `pgtp_editor/generation/config.py` (AppData JSON, `base_dir` override pattern), `pgtp_editor/generation/runner.py` (`build_generate_command` pure builder + `GeneratorRunner.run(command, on_output, on_finished)`), `pgtp_editor/ui/main_window.py:1925` `_build_generation_menu`, `_generate_php` flow at `main_window.py:1965` (guard → project check → exe check → save prompt → folder dialog → runner). Editor tests live in `tests/generation/` and `tests/ui/` (see `tests/ui/_menu_helpers.py`, `_sample_project.py` for the established fixtures).

**Run commands:** re_phpgen repo: `.\venv\Scripts\pytest -q -m "not oracle"`. Editor repo: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\<area>\ -q`.

---

## File Structure

**re_phpgen repo** (Tasks 1–3):
```
src/re_phpgen/
├── gap.py         # build_gap_report + CAUSE_MARKERS (moved from coverage script)
├── pangen.py      # emit_project
├── cli.py         # argparse: pangen / analyze subcommands
└── __main__.py    # python -m re_phpgen → cli.main()
scripts/skeleton_coverage.py   # refactor: import CAUSE_MARKERS from gap
tests/test_gap.py, tests/test_pangen.py, tests/test_cli.py
```

**pgtp_editor repo** (Tasks 4–7):
```
pgtp_editor/generation/config.py     # + re_phpgen_root accessors
pgtp_editor/generation/re_runner.py  # pure builders: python resolution, pangen/analyze commands, _pangen dir
pgtp_editor/generation/gap_summary.py# gap JSON → display summary
pgtp_editor/ui/main_window.py        # menu items + handlers + Save-reJSON state
tests/generation/test_config.py      # extend
tests/generation/test_re_runner.py, tests/generation/test_gap_summary.py
tests/ui/test_pangen_menu.py
```

---

### Task 1: `re_phpgen.gap` — the gap report builder

**Repo:** `C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen`
**Files:**
- Create: `src/re_phpgen/gap.py`
- Modify: `scripts/skeleton_coverage.py` (import `CAUSE_MARKERS` from the new module instead of defining it)
- Test: `tests/test_gap.py`

- [ ] **Step 1: Write the failing test** (`tests/test_gap.py`) — synthetic project + fabricated vendor/ours dirs; no corpus, no oracle:

```python
import json
from pathlib import Path

from re_phpgen.gap import CAUSE_MARKERS, build_gap_report

XML = b"""<Project>
  <Presentation><Pages>
    <Page fileName="alpha" tableName="s.alpha" type="grid"/>
    <Page fileName="beta" tableName="s.beta" type="grid"/>
    <Page fileName="gamma" tableName="s.gamma" type="grid"/>
  </Pages></Presentation>
</Project>"""

PHP_OK = "<?php\n    class s_alphaPage extends Page\n    {\n    }\n"
PHP_VENDOR_BETA = "<?php\n    class s_betaPage extends Page\n    {\n        $x = 1;\n        function CreateMasterDetailRecordGrid() { return null; }\n    }\n"
PHP_OURS_BETA = "<?php\n    class s_betaPage extends Page\n    {\n        $x = 2;\n        function CreateMasterDetailRecordGrid() { return null; }\n    }\n"


def _make(tmp_path):
    pgtp = tmp_path / "t.pgtp"
    pgtp.write_bytes(XML)
    vendor, ours = tmp_path / "vendor", tmp_path / "ours"
    vendor.mkdir(); ours.mkdir()
    (vendor / "alpha.php").write_text(PHP_OK, encoding="utf-8")
    (ours / "alpha.php").write_text(PHP_OK, encoding="utf-8")
    (vendor / "beta.php").write_text(PHP_VENDOR_BETA, encoding="utf-8")
    (ours / "beta.php").write_text(PHP_OURS_BETA, encoding="utf-8")
    (ours / "gamma.php").write_text(PHP_OK, encoding="utf-8")  # vendor missing
    return pgtp, vendor, ours


def test_statuses_and_summary(tmp_path):
    pgtp, vendor, ours = _make(tmp_path)
    report = build_gap_report(pgtp, vendor, ours)
    by_file = {p["file"]: p for p in report["pages"]}
    assert by_file["alpha"]["status"] == "ok"
    assert by_file["beta"]["status"] == "diff"
    assert by_file["gamma"]["status"] == "missing_vendor"
    assert report["summary"] == {
        "pages": 3, "ok": 1, "diff": 1, "missing_vendor": 1,
        "missing_ours": 0, "error": 0, "causes": {"master-detail": 1},
    }
    assert report["schema_version"] == 1
    assert report["comparison"] == "masked-skeleton-v1"


def test_diff_page_has_hunks_with_real_lines(tmp_path):
    pgtp, vendor, ours = _make(tmp_path)
    report = build_gap_report(pgtp, vendor, ours)
    beta = next(p for p in report["pages"] if p["file"] == "beta")
    assert beta["hunks"], "diff page must carry at least one hunk"
    joined = "\n".join(beta["hunks"][0]["lines"])
    assert "$x = 1;" in joined and "$x = 2;" in joined
    assert beta["hunks_omitted"] == 0


def test_vendor_staleness_flag(tmp_path):
    import os, time
    pgtp, vendor, ours = _make(tmp_path)
    old = time.time() - 3600
    for php in vendor.glob("*.php"):
        os.utime(php, (old, old))
    report = build_gap_report(pgtp, vendor, ours)
    assert report["vendor_older_than_project"] is True


def test_report_is_json_serializable(tmp_path):
    pgtp, vendor, ours = _make(tmp_path)
    json.dumps(build_gap_report(pgtp, vendor, ours))


def test_cause_markers_moved_here():
    assert any(tag == "master-detail" for tag, _marker in CAUSE_MARKERS)
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: re_phpgen.gap`): `.\venv\Scripts\pytest tests/test_gap.py -v`

- [ ] **Step 3: Write `src/re_phpgen/gap.py`.** Move the `CAUSE_MARKERS` list verbatim out of `scripts/skeleton_coverage.py` (keep its `(tag, marker)` tuple shape and comment):

```python
"""Gap report: per-page ours-vs-vendor deltas as a JSON-serializable dict.

The comparison is the proven symmetric pipeline (normalize -> mask handlers ->
mask method bodies on BOTH sides), so the report captures skeleton-level deltas.
"""
from __future__ import annotations

import datetime as _dt
from difflib import unified_diff
from pathlib import Path

from re_phpgen.catalog import top_level_pages
from re_phpgen.handlers import handler_texts, mask_handler_code
from re_phpgen.masker import mask_method_bodies
from re_phpgen.normalizer import normalize

SCHEMA_VERSION = 1
COMPARISON = "masked-skeleton-v1"
MAX_HUNKS_PER_PAGE = 20
MAX_HUNK_LINES_PER_PAGE = 200

# (tag, marker) — moved verbatim from scripts/skeleton_coverage.py, including
# its original comment block. Grepped against the RAW vendor PHP (markers may
# live inside method bodies that masking hides).
CAUSE_MARKERS = [
    # ... (the existing list from scripts/skeleton_coverage.py, unchanged)
]


def _masked(text: str, htexts: list[str]) -> str:
    return mask_method_bodies(mask_handler_code(normalize(text), htexts))


def _causes(vendor_raw: str) -> list[str]:
    found = [tag for tag, marker in CAUSE_MARKERS if marker in vendor_raw]
    return found or ["unclassified"]


def _hunks(ours: str, vendor: str) -> tuple[list[dict], int]:
    diff = list(unified_diff(ours.splitlines(), vendor.splitlines(), lineterm="", n=2))
    hunks: list[dict] = []
    current: dict | None = None
    for line in diff[2:]:  # skip ---/+++ file headers
        if line.startswith("@@"):
            if current is not None:
                hunks.append(current)
            current = {"header": line, "lines": []}
        elif current is not None:
            current["lines"].append(line)
    if current is not None:
        hunks.append(current)

    kept: list[dict] = []
    kept_lines = 0
    omitted = 0
    for hunk in hunks:
        if len(kept) >= MAX_HUNKS_PER_PAGE or kept_lines + len(hunk["lines"]) > MAX_HUNK_LINES_PER_PAGE:
            omitted += 1
            continue
        kept.append(hunk)
        kept_lines += len(hunk["lines"])
    return kept, omitted


def build_gap_report(pgtp: Path, vendor_dir: Path, ours_dir: Path) -> dict:
    htexts = handler_texts(pgtp)
    pages = top_level_pages(pgtp)
    counts = {"ok": 0, "diff": 0, "missing_vendor": 0, "missing_ours": 0, "error": 0}
    causes_count: dict[str, int] = {}
    entries: list[dict] = []
    newest_vendor_mtime = 0.0

    for page in pages:
        vendor_php = vendor_dir / f"{page.file_name}.php"
        ours_php = ours_dir / f"{page.file_name}.php"
        entry: dict = {"file": page.file_name, "table": page.table_name,
                       "status": "", "causes": [], "hunks": [], "hunks_omitted": 0}
        try:
            if not vendor_php.is_file():
                entry["status"] = "missing_vendor"
            elif not ours_php.is_file():
                entry["status"] = "missing_ours"
            else:
                newest_vendor_mtime = max(newest_vendor_mtime, vendor_php.stat().st_mtime)
                vendor_raw = vendor_php.read_text("utf-8", errors="replace")
                ours_masked = _masked(ours_php.read_text("utf-8", errors="replace"), htexts)
                vendor_masked = _masked(vendor_raw, htexts)
                if ours_masked == vendor_masked:
                    entry["status"] = "ok"
                else:
                    entry["status"] = "diff"
                    entry["causes"] = _causes(vendor_raw)
                    entry["hunks"], entry["hunks_omitted"] = _hunks(ours_masked, vendor_masked)
                    for cause in entry["causes"]:
                        causes_count[cause] = causes_count.get(cause, 0) + 1
        except Exception as exc:  # noqa: BLE001 — one bad page must not sink the report
            entry["status"] = "error"
            entry["error"] = str(exc)
        counts[entry["status"]] += 1
        entries.append(entry)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "project": str(pgtp),
        "vendor_dir": str(vendor_dir),
        "ours_dir": str(ours_dir),
        "comparison": COMPARISON,
        "vendor_older_than_project": bool(newest_vendor_mtime) and pgtp.stat().st_mtime > newest_vendor_mtime,
        "summary": {"pages": len(pages), **counts, "causes": causes_count},
        "pages": entries,
    }
```

(The `CAUSE_MARKERS` placeholder comment above means: physically move the existing list from `scripts/skeleton_coverage.py`; do not retype it.)

- [ ] **Step 4: Refactor `scripts/skeleton_coverage.py`** — delete its `CAUSE_MARKERS` definition, add `from re_phpgen.gap import CAUSE_MARKERS`, keep behavior identical.

- [ ] **Step 5: Run → PASS**, then the repo's full suite: `.\venv\Scripts\pytest -q -m "not oracle"` (expect prior count + 5 new, all green; the coverage script refactor is exercised by running `.\venv\Scripts\python scripts\skeleton_coverage.py` once — same output shape as before).

- [ ] **Step 6: Commit** (re_phpgen repo): `git add -A; git commit -m "feat: gap report builder (ours-vs-vendor deltas as JSON dict)"`

---

### Task 2: `re_phpgen.pangen` — emit our PHP for a whole project

**Repo:** re_phpgen
**Files:**
- Create: `src/re_phpgen/pangen.py`
- Test: `tests/test_pangen.py`

- [ ] **Step 1: Write the failing test:**

```python
from re_phpgen.pangen import emit_project

XML = b"""<Project>
  <Presentation><Pages>
    <Page fileName="alpha" tableName="s.alpha" type="grid"/>
    <Page fileName="beta" tableName="s.beta" type="grid"/>
  </Pages></Presentation>
</Project>"""


def test_emit_project_writes_one_php_per_page(tmp_path):
    pgtp = tmp_path / "t.pgtp"
    pgtp.write_bytes(XML)
    out = tmp_path / "out"
    count = emit_project(pgtp, out)
    assert count == 2
    alpha = (out / "alpha.php").read_text(encoding="utf-8")
    assert "s_alphaPage" in alpha            # slots really filled
    assert (out / "beta.php").is_file()


def test_emit_project_is_best_effort(tmp_path, monkeypatch):
    """A page whose slot derivation raises is skipped with a count shortfall,
    not a crash — deltas on the others are still valuable."""
    import re_phpgen.pangen as pangen_mod

    def boom(pgtp, page):
        if page.file_name == "beta":
            raise ValueError("unsupported variant")
        return real(pgtp, page)

    real = pangen_mod.slots_for_page
    monkeypatch.setattr(pangen_mod, "slots_for_page", boom)
    pgtp = tmp_path / "t.pgtp"
    pgtp.write_bytes(XML)
    out = tmp_path / "out"
    assert emit_project(pgtp, out) == 1
    assert (out / "alpha.php").is_file() and not (out / "beta.php").exists()
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError`): `.\venv\Scripts\pytest tests/test_pangen.py -v`

- [ ] **Step 3: Write `src/re_phpgen/pangen.py`:**

```python
"""Emit our best-effort .php for every top-level page of a project (panGen)."""
from __future__ import annotations

import sys
from pathlib import Path

from re_phpgen.catalog import top_level_pages
from re_phpgen.skeleton import emit_skeleton, slots_for_page


def emit_project(pgtp: Path, out_dir: Path) -> int:
    """Write <fileName>.php for each top-level page; return the number written.
    Pages whose emission fails are skipped with a stderr note (best-effort by
    design — the gap report on the successful pages is still the payload)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for page in top_level_pages(pgtp):
        try:
            php = emit_skeleton(slots_for_page(pgtp, page))
        except Exception as exc:  # noqa: BLE001
            print(f"pangen: skipped {page.file_name}: {exc}", file=sys.stderr)
            continue
        (out_dir / f"{page.file_name}.php").write_text(php, encoding="utf-8", newline="")
        written += 1
    return written
```

- [ ] **Step 4: Run → PASS**, then full suite green.

- [ ] **Step 5: Commit:** `git add -A; git commit -m "feat: pangen emit_project (best-effort whole-project emission)"`

---

### Task 3: re_phpgen CLI (`python -m re_phpgen`)

**Repo:** re_phpgen
**Files:**
- Create: `src/re_phpgen/cli.py`, `src/re_phpgen/__main__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** (calls `main(argv)` directly — no subprocess needed):

```python
import json

from re_phpgen.cli import main
from tests.test_pangen import XML


def _project(tmp_path):
    pgtp = tmp_path / "t.pgtp"
    pgtp.write_bytes(XML)
    return pgtp


def test_pangen_subcommand(tmp_path, capsys):
    pgtp = _project(tmp_path)
    out = tmp_path / "ours"
    assert main(["pangen", str(pgtp), "--out", str(out)]) == 0
    assert (out / "alpha.php").is_file()
    assert "pangen: 2 pages" in capsys.readouterr().out


def test_analyze_subcommand_writes_json_and_summary_line(tmp_path, capsys):
    pgtp = _project(tmp_path)
    ours = tmp_path / "ours"
    main(["pangen", str(pgtp), "--out", str(ours)])
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "alpha.php").write_text((ours / "alpha.php").read_text(encoding="utf-8"), encoding="utf-8")
    json_path = tmp_path / "gap.json"
    assert main(["analyze", str(pgtp), "--vendor", str(vendor),
                 "--ours", str(ours), "--json", str(json_path)]) == 0
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["summary"]["ok"] == 1
    assert report["summary"]["missing_vendor"] == 1   # beta not in vendor dir
    assert "analyze: ok 1" in capsys.readouterr().out


def test_missing_project_is_operational_failure(tmp_path, capsys):
    assert main(["pangen", str(tmp_path / "nope.pgtp"), "--out", str(tmp_path / "o")]) != 0
```

- [ ] **Step 2: Run → FAIL**: `.\venv\Scripts\pytest tests/test_cli.py -v`

- [ ] **Step 3: Write `src/re_phpgen/cli.py`:**

```python
"""CLI consumed by the pgtp_editor Generation menu (subprocess boundary)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from re_phpgen.gap import build_gap_report
from re_phpgen.pangen import emit_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="re_phpgen")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pangen = sub.add_parser("pangen", help="emit our .php for every top-level page")
    p_pangen.add_argument("project")
    p_pangen.add_argument("--out", required=True)

    p_analyze = sub.add_parser("analyze", help="gap JSON: ours vs vendor output")
    p_analyze.add_argument("project")
    p_analyze.add_argument("--vendor", required=True)
    p_analyze.add_argument("--ours", required=True)
    p_analyze.add_argument("--json", required=True, dest="json_path")

    args = parser.parse_args(argv)
    project = Path(args.project)
    if not project.is_file():
        print(f"error: project not found: {project}", file=sys.stderr)
        return 2

    if args.command == "pangen":
        count = emit_project(project, Path(args.out))
        print(f"pangen: {count} pages -> {args.out}")
        return 0

    report = build_gap_report(project, Path(args.vendor), Path(args.ours))
    json_path = Path(args.json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    s = report["summary"]
    print(
        f"analyze: ok {s['ok']} / diff {s['diff']} / missing "
        f"{s['missing_vendor'] + s['missing_ours']} of {s['pages']} pages -> {json_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

And `src/re_phpgen/__main__.py`:

```python
from re_phpgen.cli import main

raise SystemExit(main())
```

- [ ] **Step 4: Run → PASS**, full suite green, plus one real smoke by hand: `.\venv\Scripts\python -m re_phpgen pangen input\03.pgtp --out work\cli_smoke` → expect `pangen: 6 pages -> work\cli_smoke`.

- [ ] **Step 5: Commit:** `git add -A; git commit -m "feat: CLI (pangen/analyze subcommands) for editor integration"`

---

### Task 4: Editor config — `re_phpgen_root`

**Repo:** `C:\Users\BotondZalai-RuzsicsP\docs\Software development\pgtp_editor` (branch `re-phpgen`)
**Files:**
- Modify: `pgtp_editor/generation/config.py`
- Test: `tests/generation/test_config.py` (extend)

- [ ] **Step 1: Write the failing tests** (append to `tests/generation/test_config.py`, mirroring the existing executable-path tests' style):

```python
from pgtp_editor.generation.config import (
    DEFAULT_RE_PHPGEN_ROOT,
    load_re_phpgen_root,
    save_re_phpgen_root,
)


def test_re_phpgen_root_defaults_when_unset(tmp_path):
    assert load_re_phpgen_root(base_dir=tmp_path) == DEFAULT_RE_PHPGEN_ROOT


def test_re_phpgen_root_roundtrip(tmp_path):
    save_re_phpgen_root(r"D:\elsewhere\re_phpgen", base_dir=tmp_path)
    assert load_re_phpgen_root(base_dir=tmp_path) == r"D:\elsewhere\re_phpgen"


def test_re_phpgen_root_preserves_executable_key(tmp_path):
    from pgtp_editor.generation.config import load_executable_path, save_executable_path
    save_executable_path(r"C:\gen.exe", base_dir=tmp_path)
    save_re_phpgen_root(r"D:\re", base_dir=tmp_path)
    assert load_executable_path(base_dir=tmp_path) == r"C:\gen.exe"
```

- [ ] **Step 2: Run → FAIL** (ImportError): `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\generation\test_config.py -q`

- [ ] **Step 3: Implement** — append to `pgtp_editor/generation/config.py`:

```python
_RE_PHPGEN_ROOT_KEY = "re_phpgen_root"
DEFAULT_RE_PHPGEN_ROOT = r"C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen"


def load_re_phpgen_root(base_dir: Path | None = None) -> str:
    """Stored re_phpgen repo root, falling back to the machine default."""
    path = generator_config_path(base_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return DEFAULT_RE_PHPGEN_ROOT
    value = data.get(_RE_PHPGEN_ROOT_KEY) if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else DEFAULT_RE_PHPGEN_ROOT


def save_re_phpgen_root(root: str, base_dir: Path | None = None) -> None:
    config_path = generator_config_path(base_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError, TypeError):
        data = {}
    data[_RE_PHPGEN_ROOT_KEY] = root
    config_path.write_text(json.dumps(data), encoding="utf-8")
```

- [ ] **Step 4: Run → PASS**: same command, plus `python -m pytest tests\generation\ -q` all green.

- [ ] **Step 5: Commit:** `git add -A; git commit -m "feat: re_phpgen_root setting in generation config"`

---

### Task 5: Editor pure builders — `re_runner.py`

**Repo:** pgtp_editor
**Files:**
- Create: `pgtp_editor/generation/re_runner.py`
- Test: `tests/generation/test_re_runner.py`

- [ ] **Step 1: Write the failing tests:**

```python
from pathlib import Path

from pgtp_editor.generation.re_runner import (
    PANGEN_SUBFOLDER,
    build_analyze_command,
    build_pangen_command,
    pangen_output_dir,
    resolve_re_phpgen_python,
    validate_re_phpgen_root,
)


def test_pangen_output_dir_is_sibling_subfolder():
    assert pangen_output_dir(r"C:\out") == str(Path(r"C:\out") / PANGEN_SUBFOLDER)


def test_resolve_python_prefers_repo_venv(tmp_path):
    venv_python = tmp_path / "venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_bytes(b"")
    assert resolve_re_phpgen_python(str(tmp_path)) == str(venv_python)


def test_resolve_python_falls_back_to_sys_executable(tmp_path):
    import sys
    assert resolve_re_phpgen_python(str(tmp_path)) == sys.executable


def test_validate_root_requires_package_dir(tmp_path):
    assert validate_re_phpgen_root(str(tmp_path)) is False
    (tmp_path / "src" / "re_phpgen").mkdir(parents=True)
    assert validate_re_phpgen_root(str(tmp_path)) is True


def test_build_pangen_command(tmp_path):
    cmd = build_pangen_command("py.exe", str(tmp_path), r"C:\p.pgtp", r"C:\out")
    assert cmd == ["py.exe", "-m", "re_phpgen", "pangen", r"C:\p.pgtp",
                   "--out", str(Path(r"C:\out") / PANGEN_SUBFOLDER)]


def test_build_analyze_command(tmp_path):
    cmd = build_analyze_command("py.exe", str(tmp_path), r"C:\p.pgtp", r"C:\out", r"C:\gap.json")
    assert cmd == ["py.exe", "-m", "re_phpgen", "analyze", r"C:\p.pgtp",
                   "--vendor", r"C:\out",
                   "--ours", str(Path(r"C:\out") / PANGEN_SUBFOLDER),
                   "--json", r"C:\gap.json"]
```

- [ ] **Step 2: Run → FAIL**: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\generation\test_re_runner.py -q`

- [ ] **Step 3: Write `pgtp_editor/generation/re_runner.py`:**

```python
# pgtp_editor/generation/re_runner.py
"""Pure command builders for the re_phpgen CLI (panGen / rePHPgen actions).

Subprocess-boundary counterpart of runner.build_generate_command: everything
here is a pure function over paths so it is fully unit-testable; the commands
are executed by the same injectable GeneratorRunner the vendor generation uses.
The subprocess must run with cwd=<re_phpgen_root> and PYTHONPATH including
<root>/src (handled by MainWindow via QProcess working directory — see
build_* docstrings) so `-m re_phpgen` resolves without installing the package.
"""
from __future__ import annotations

import sys
from pathlib import Path

PANGEN_SUBFOLDER = "_pangen"


def pangen_output_dir(output_folder: str) -> str:
    """Our generator's output: a sibling subfolder so vendor files are never overwritten."""
    return str(Path(output_folder) / PANGEN_SUBFOLDER)


def resolve_re_phpgen_python(root: str) -> str:
    """The repo's venv python if present, else the editor's interpreter."""
    venv_python = Path(root) / "venv" / "Scripts" / "python.exe"
    return str(venv_python) if venv_python.is_file() else sys.executable


def validate_re_phpgen_root(root: str) -> bool:
    return (Path(root) / "src" / "re_phpgen").is_dir()


def build_pangen_command(python: str, root: str, pgtp_path: str, output_folder: str) -> list[str]:
    """Run from cwd=root (pyproject's pythonpath=['src','.'] applies only to
    pytest; QProcess must set PYTHONPATH=<root>/src or cwd-launch via venv
    python, which has the package importable through its editable/dev layout)."""
    return [python, "-m", "re_phpgen", "pangen", pgtp_path,
            "--out", pangen_output_dir(output_folder)]


def build_analyze_command(python: str, root: str, pgtp_path: str,
                          output_folder: str, json_path: str) -> list[str]:
    return [python, "-m", "re_phpgen", "analyze", pgtp_path,
            "--vendor", output_folder,
            "--ours", pangen_output_dir(output_folder),
            "--json", json_path]
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit:** `git add -A; git commit -m "feat: pure command builders for re_phpgen CLI"`

**Note for Task 7:** `python -m re_phpgen` requires the package importable in the subprocess. The re_phpgen venv python does NOT automatically see `src/`. MainWindow must set the QProcess environment: `PYTHONPATH=<root>\src` and working directory `<root>`. `GeneratorRunner` currently exposes no env hook — Task 6 adds one.

---

### Task 6: `GeneratorRunner` env/cwd support

**Repo:** pgtp_editor
**Files:**
- Modify: `pgtp_editor/generation/runner.py` (`GeneratorRunner.run`)
- Test: `tests/generation/test_runner.py` (extend)

- [ ] **Step 1: Write the failing test** (append; follow the existing GeneratorRunner test style in that file — they run a real tiny process via `sys.executable`):

```python
import sys


def test_runner_applies_cwd_and_extra_env(qtbot, tmp_path):
    from pgtp_editor.generation.runner import GeneratorRunner

    runner = GeneratorRunner()
    lines: list[str] = []
    codes: list[int] = []
    code = "import os; print(os.getcwd()); print(os.environ.get('PGTP_TEST_ENV', ''))"
    runner.run(
        [sys.executable, "-c", code],
        on_output=lines.append,
        on_finished=codes.append,
        cwd=str(tmp_path),
        extra_env={"PGTP_TEST_ENV": "hello"},
    )
    qtbot.waitUntil(lambda: bool(codes), timeout=10000)
    assert codes == [0]
    assert lines[0].lower() == str(tmp_path).lower()
    assert lines[1] == "hello"
```

- [ ] **Step 2: Run → FAIL** (unexpected keyword `cwd`): `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\generation\test_runner.py -q`

- [ ] **Step 3: Implement** — extend `GeneratorRunner.run` signature (keep old callers valid via defaults):

```python
    def run(
        self,
        command: list[str],
        on_output: Callable[[str], None],
        on_finished: Callable[[int], None],
        cwd: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        ...
        process.errorOccurred.connect(self._on_error)
        if cwd:
            process.setWorkingDirectory(cwd)
        if extra_env:
            from PySide6.QtCore import QProcessEnvironment
            env = QProcessEnvironment.systemEnvironment()
            for key, value in extra_env.items():
                env.insert(key, value)
            process.setProcessEnvironment(env)
        self._process = process
```

(Insert the `cwd`/`extra_env` block between `errorOccurred.connect` and `self._process = process`; everything else unchanged.)

- [ ] **Step 4: Run → PASS**, then `python -m pytest tests\generation\ -q` all green.

- [ ] **Step 5: Commit:** `git add -A; git commit -m "feat: GeneratorRunner cwd/env support for re_phpgen subprocesses"`

---

### Task 7: `gap_summary.py` — JSON → display text

**Repo:** pgtp_editor
**Files:**
- Create: `pgtp_editor/generation/gap_summary.py`
- Test: `tests/generation/test_gap_summary.py`

- [ ] **Step 1: Write the failing tests:**

```python
import json

from pgtp_editor.generation.gap_summary import summarize_gap_json

REPORT = {
    "schema_version": 1,
    "vendor_older_than_project": True,
    "summary": {"pages": 40, "ok": 3, "diff": 35, "missing_vendor": 1,
                "missing_ours": 0, "error": 1,
                "causes": {"master-detail": 20, "unclassified": 15}},
}


def test_summarize_gap_json(tmp_path):
    path = tmp_path / "gap.json"
    path.write_text(json.dumps(REPORT), encoding="utf-8")
    text = summarize_gap_json(path)
    assert "3 ok" in text and "35 diff" in text and "40 pages" in text
    assert "master-detail: 20" in text
    assert "WARNING" in text and "older" in text     # staleness surfaced


def test_summarize_malformed_json_returns_error_text(tmp_path):
    path = tmp_path / "gap.json"
    path.write_text("{not json", encoding="utf-8")
    assert "Could not read gap JSON" in summarize_gap_json(path)
```

- [ ] **Step 2: Run → FAIL**: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\generation\test_gap_summary.py -q`

- [ ] **Step 3: Write `pgtp_editor/generation/gap_summary.py`:**

```python
# pgtp_editor/generation/gap_summary.py
"""Human-readable summary of a re_phpgen gap JSON (for dialog/status display)."""
from __future__ import annotations

import json
from pathlib import Path


def summarize_gap_json(path: Path) -> str:
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        summary = report["summary"]
        lines = [
            f"{summary['pages']} pages: {summary['ok']} ok, {summary['diff']} diff, "
            f"{summary['missing_vendor'] + summary['missing_ours']} missing, "
            f"{summary['error']} error",
        ]
        causes = summary.get("causes") or {}
        if causes:
            ranked = sorted(causes.items(), key=lambda kv: -kv[1])
            lines.append("Diff causes: " + ", ".join(f"{k}: {v}" for k, v in ranked))
        if report.get("vendor_older_than_project"):
            lines.append("WARNING: vendor output is older than the project file - regenerate from the GUI.")
        return "\n".join(lines)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return f"Could not read gap JSON: {exc}"
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit:** `git add -A; git commit -m "feat: gap JSON summary formatting"`

---

### Task 8: Menu actions in MainWindow

**Repo:** pgtp_editor
**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (`_build_generation_menu` at :1925; new handlers after `_open_output_folder`; imports at top near the existing generation imports :33)
- Test: `tests/ui/test_pangen_menu.py`

**Study first:** `tests/ui/_menu_helpers.py`, `tests/ui/_sample_project.py`, and an existing menu test (e.g. `tests/ui/test_database_menu.py`) for the established MainWindow-fixture pattern (fake runner injection, `_generator_config_dir` tmp override, monkeypatched dialogs). Reuse those fixtures — do not invent a new harness.

- [ ] **Step 1: Write the failing tests** (adapt fixture names to what `_menu_helpers.py` provides; the assertions below are the contract):

```python
"""Generation-menu panGen / rePHPgen / Save reJSON wiring.

House rule: every modal (QMessageBox.question/information/warning,
QFileDialog.getExistingDirectory/getSaveFileName) is monkeypatched.
The GeneratorRunner is replaced by a fake capturing commands and letting the
test drive on_finished callbacks explicitly."""
import json
from pathlib import Path

import pytest


class FakeRunner:
    def __init__(self):
        self.calls = []          # list of (command, cwd, extra_env)
        self.pending = []        # on_finished callbacks in call order

    def run(self, command, on_output, on_finished, cwd=None, extra_env=None):
        self.calls.append((command, cwd, extra_env))
        self.pending.append(on_finished)


@pytest.fixture
def window_with_fake_runner(...):   # build on the existing MainWindow fixture
    ...


def test_pangen_runs_cli_into_sibling_subfolder(window_with_fake_runner, monkeypatch, tmp_path):
    window, runner = window_with_fake_runner
    # save prompt -> Save; folder dialog -> tmp_path
    ...monkeypatch QMessageBox.question -> Save, QFileDialog.getExistingDirectory -> str(tmp_path)
    window._pangen()
    command, cwd, extra_env = runner.calls[0]
    assert command[1:4] == ["-m", "re_phpgen", "pangen"]
    assert command[-1].endswith("_pangen")
    assert cwd and Path(cwd).name == "re_phpgen"          # runs from the repo root
    assert "src" in extra_env["PYTHONPATH"]


def test_re_phpgen_requires_vendor_output(window_with_fake_runner, monkeypatch, tmp_path):
    window, runner = window_with_fake_runner
    ...dialogs patched; tmp_path contains NO .php files
    infos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a))
    window._re_phpgen_analyze()
    assert runner.calls == []                              # nothing launched
    assert any("vendor output" in str(a).lower() for a in infos)


def test_re_phpgen_chains_pangen_then_analyze_and_enables_save(window_with_fake_runner, monkeypatch, tmp_path):
    window, runner = window_with_fake_runner
    (tmp_path / "alpha.php").write_text("<?php\n", encoding="utf-8")   # vendor baseline present
    ...dialogs patched to choose tmp_path
    window._re_phpgen_analyze()
    assert runner.calls[0][0][3] == "pangen"
    # finish pangen successfully -> analyze launches
    (fake_json := window._gap_json_work_path()).parent.mkdir(parents=True, exist_ok=True)
    fake_json.write_text(json.dumps({"schema_version": 1, "vendor_older_than_project": False,
        "summary": {"pages": 1, "ok": 1, "diff": 0, "missing_vendor": 0,
                    "missing_ours": 0, "error": 0, "causes": {}}}), encoding="utf-8")
    runner.pending[0](0)
    assert runner.calls[1][0][3] == "analyze"
    assert window._save_rejson_action.isEnabled() is False   # not until analyze finishes
    runner.pending[1](0)
    assert window._save_rejson_action.isEnabled() is True


def test_save_rejson_copies_last_json(window_with_fake_runner, monkeypatch, tmp_path):
    window, runner = window_with_fake_runner
    src = window._gap_json_work_path()
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text('{"schema_version": 1}', encoding="utf-8")
    window._last_gap_json = src
    window._save_rejson_action.setEnabled(True)
    target = tmp_path / "out.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window._save_rejson()
    assert target.read_text(encoding="utf-8") == '{"schema_version": 1}'


def test_locate_pangen_runtime_validates_and_saves(window_with_fake_runner, monkeypatch, tmp_path):
    window, _ = window_with_fake_runner
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a))
    window._locate_pangen_runtime()
    assert warnings                                        # invalid dir rejected
    (tmp_path / "src" / "re_phpgen").mkdir(parents=True)
    window._locate_pangen_runtime()
    from pgtp_editor.generation.config import load_re_phpgen_root
    assert load_re_phpgen_root(base_dir=window._generator_config_dir) == str(tmp_path)
```

(The `...` fixture plumbing means: copy the exact fixture/monkeypatch pattern from the neighbouring menu test file; the assertions and handler names above are fixed.)

- [ ] **Step 2: Run → FAIL** (missing handlers): `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_pangen_menu.py -q`

- [ ] **Step 3: Implement in `main_window.py`.**

Imports (extend the existing generation import block at :33):

```python
from pgtp_editor.generation.config import (
    load_executable_path, save_executable_path,
    load_re_phpgen_root, save_re_phpgen_root,
)
from pgtp_editor.generation.gap_summary import summarize_gap_json
from pgtp_editor.generation.re_runner import (
    build_analyze_command, build_pangen_command,
    resolve_re_phpgen_python, validate_re_phpgen_root,
)
```

Menu additions in `_build_generation_menu` (after the existing items):

```python
        menu.addSeparator()
        locate_pangen_action = menu.addAction("Locate panGen Runtime...")
        locate_pangen_action.triggered.connect(self._locate_pangen_runtime)
        pangen_action = menu.addAction("panGen (Generate Own PHP)")
        pangen_action.triggered.connect(self._pangen)
        re_phpgen_action = menu.addAction("rePHPgen (Analyze Gap)")
        re_phpgen_action.triggered.connect(self._re_phpgen_analyze)
        self._save_rejson_action = menu.addAction("Save reJSON...")
        self._save_rejson_action.triggered.connect(self._save_rejson)
        self._save_rejson_action.setEnabled(False)
```

Handlers (new methods; also add `self._last_gap_json: Path | None = None` next to `self._current_output_folder` in `__init__`):

```python
    # --- panGen / rePHPgen -------------------------------------------------

    def _gap_json_work_path(self) -> Path:
        from pgtp_editor.generation.config import generator_config_path
        return generator_config_path(self._generator_config_dir).parent / "last_gap.json"

    def _re_phpgen_runtime(self) -> tuple[str, str, dict[str, str]] | None:
        """(python, root, extra_env) or None after showing guidance."""
        root = load_re_phpgen_root(base_dir=self._generator_config_dir)
        if not validate_re_phpgen_root(root):
            QMessageBox.information(
                self, "panGen",
                "re_phpgen runtime not found. Set it via "
                "Generation > Locate panGen Runtime...",
            )
            return None
        python = resolve_re_phpgen_python(root)
        return python, root, {"PYTHONPATH": str(Path(root) / "src")}

    def _prepare_generation_run(self) -> str | None:
        """Shared preamble: in-flight guard, open project, save prompt, output
        folder. Returns the output folder or None. Mirrors _generate_php steps
        0/1/3/4 (no vendor-exe check)."""
        if self._is_generating:
            self.statusBar().showMessage("A generation is already in progress.", 5000)
            return None
        if self._current_project is None and not self.center_stage.xml_editor.toPlainText().strip():
            self.statusBar().showMessage("Open a project first.", 5000)
            return None
        choice = QMessageBox.question(
            self, "Save Before Running",
            "panGen reads the project from disk. Save the current editor contents first?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.SaveAll
            | QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return None
        if choice == QMessageBox.StandardButton.SaveAll:
            self._save_project_as()
        else:
            self._save_project()
        if not self._current_project_path:
            return None
        output_folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self._project_output_folder_default()
        )
        return output_folder or None

    def _pangen(self) -> None:
        runtime = self._re_phpgen_runtime()
        if runtime is None:
            return
        python, root, extra_env = runtime
        output_folder = self._prepare_generation_run()
        if not output_folder:
            return
        self._clear_generator_output()
        self._current_output_folder = output_folder
        self._is_generating = True
        self.statusBar().showMessage("panGen running…")
        command = build_pangen_command(python, root, self._current_project_path, output_folder)
        self._generator_runner.run(
            command,
            on_output=self._append_generator_output,
            on_finished=self._on_pangen_finished,
            cwd=root,
            extra_env=extra_env,
        )

    def _on_pangen_finished(self, exit_code: int) -> None:
        self._is_generating = False
        if exit_code == 0:
            self.statusBar().showMessage("panGen finished", 5000)
        else:
            QMessageBox.warning(self, "panGen", f"panGen failed (exit {exit_code}). See the Audit panel.")

    def _re_phpgen_analyze(self) -> None:
        runtime = self._re_phpgen_runtime()
        if runtime is None:
            return
        python, root, extra_env = runtime
        output_folder = self._prepare_generation_run()
        if not output_folder:
            return
        # Precondition: a manually generated vendor baseline must exist.
        if not any(Path(output_folder).glob("*.php")):
            QMessageBox.information(
                self, "rePHPgen",
                "No vendor output found in this folder. Generate the project from "
                "the PHP Generator GUI into this folder first, then run rePHPgen.",
            )
            return
        self._clear_generator_output()
        self._current_output_folder = output_folder
        self._is_generating = True
        self._save_rejson_action.setEnabled(False)
        json_path = self._gap_json_work_path()
        pangen_command = build_pangen_command(python, root, self._current_project_path, output_folder)
        analyze_command = build_analyze_command(
            python, root, self._current_project_path, output_folder, str(json_path)
        )

        def after_analyze(exit_code: int) -> None:
            self._is_generating = False
            if exit_code != 0:
                QMessageBox.warning(self, "rePHPgen", f"Analysis failed (exit {exit_code}). See the Audit panel.")
                return
            self._last_gap_json = json_path
            self._save_rejson_action.setEnabled(True)
            summary = summarize_gap_json(json_path)
            self._append_generator_output(summary.replace("\n", " | "))
            self.statusBar().showMessage("rePHPgen analysis complete", 5000)
            QMessageBox.information(self, "rePHPgen — Gap Summary", summary)

        def after_pangen(exit_code: int) -> None:
            if exit_code != 0:
                self._is_generating = False
                QMessageBox.warning(self, "rePHPgen", f"panGen step failed (exit {exit_code}). See the Audit panel.")
                return
            self._generator_runner.run(
                analyze_command,
                on_output=self._append_generator_output,
                on_finished=after_analyze,
                cwd=root,
                extra_env=extra_env,
            )

        self.statusBar().showMessage("rePHPgen running…")
        self._generator_runner.run(
            pangen_command,
            on_output=self._append_generator_output,
            on_finished=after_pangen,
            cwd=root,
            extra_env=extra_env,
        )

    def _save_rejson(self) -> None:
        if not self._last_gap_json or not self._last_gap_json.is_file():
            self.statusBar().showMessage("No gap JSON yet — run rePHPgen first.", 5000)
            return
        stem = Path(self._current_project_path).stem if self._current_project_path else "project"
        default_dir = self._current_output_folder or ""
        target, _filter = QFileDialog.getSaveFileName(
            self, "Save reJSON", str(Path(default_dir) / f"{stem}_gap.json"), "JSON (*.json)"
        )
        if not target:
            return
        Path(target).write_text(self._last_gap_json.read_text(encoding="utf-8"), encoding="utf-8")
        self.statusBar().showMessage(f"Gap JSON saved: {Path(target).name}", 5000)

    def _locate_pangen_runtime(self) -> None:
        root = QFileDialog.getExistingDirectory(
            self, "Locate panGen Runtime (re_phpgen repo root)",
            load_re_phpgen_root(base_dir=self._generator_config_dir),
        )
        if not root:
            return
        if not validate_re_phpgen_root(root):
            QMessageBox.warning(
                self, "Locate panGen Runtime",
                "That folder does not look like the re_phpgen repo (missing src\\re_phpgen).",
            )
            return
        save_re_phpgen_root(root, base_dir=self._generator_config_dir)
        self.statusBar().showMessage(f"panGen runtime set: {root}", 5000)
```

- [ ] **Step 4: Run → PASS**: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_pangen_menu.py -q`, then the touched areas: `python -m pytest tests\generation\ tests\ui\ -q`.

- [ ] **Step 5: Commit:** `git add -A; git commit -m "feat: panGen / rePHPgen / Save reJSON Generation-menu actions"`

---

### Task 9: End-to-end verification + feature gate

**Repos:** both

- [ ] **Step 1: Manual end-to-end smoke** (requires the corpus): open `input\03.pgtp`'s copy in the editor (or any project with manually generated vendor output), run **panGen** → confirm `_pangen\*.php` appear; run **rePHPgen** → confirm summary dialog + Audit line; **Save reJSON…** → open the saved JSON, confirm schema fields and at least one `diff` page with hunks.

- [ ] **Step 2: Full suites green in both repos:**
- re_phpgen: `.\venv\Scripts\pytest -q -m "not oracle"`
- editor: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`

- [ ] **Step 3: Feature-tester gate (CLAUDE.md, mandatory):** dispatch the `feature-tester` agent with this feature name ("panGen + rePHPgen gap analysis"), the spec path (`docs/superpowers/specs/2026-07-19-pgtp-editor-pangen-gap-analysis-design.md`), this plan path, and the changed editor files (Tasks 4–8). It appends the verified entry to `docs/TEST_LOG.md`. Fix any implementation bugs it reports and re-dispatch until green.

- [ ] **Step 4: Commit the TEST_LOG entry** (editor repo): `git add docs/TEST_LOG.md; git commit -m "test: TEST_LOG entry for panGen + rePHPgen gap analysis"`

---

## Self-review notes (spec coverage)

- Spec §4 CLI (`pangen`, `analyze`, JSON schema, exit codes, summary lines) → Tasks 1–3. Exit 0 with diffs present, nonzero only operational — Task 3 test `test_missing_project_is_operational_failure`.
- Spec §5 menu actions incl. save-first flow, `_pangen` subfolder, vendor-output precondition, Save-reJSON enable state, Locate runtime validation → Tasks 5–8.
- Spec §3 runtime resolution (venv python, fallback) + subprocess env (`PYTHONPATH`, cwd) → Tasks 5–6.
- Spec §7 staleness flag → Task 1 (`vendor_older_than_project`) + Task 7 (WARNING line) + summary dialog (Task 8).
- Spec §6 testing (synthetic mini-project, no modal Qt unpatched, feature-tester gate) → Tasks 1–3 fixtures, Task 8 house-rule header, Task 9.
- Deliberately not built (YAGNI): no gap-JSON viewer panel, no auto-refresh of vendor output, no multi-project batch analysis.
