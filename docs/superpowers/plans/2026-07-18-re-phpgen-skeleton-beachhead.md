# re_phpgen Skeleton Beachhead Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the reverse-engineering harness (oracle wrapper, normalizer, maskers, corpus catalog) and reproduce the invariant per-page PHP skeleton for top-level `Page` files to byte-parity against the vendor generator ("mask-the-holes" validation), per spec `docs/superpowers/specs/2026-07-18-re-phpgen-generator-design.md` §6 and §9.

**Architecture:** A standalone Python project at `C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen\` (its own git repo; the 37-project corpus already lives in `input\`, which is gitignored — it contains plaintext DB credentials). The vendor CLI is the test oracle. Pipeline for this plan: mask per-field method bodies + event-handler code out of real generated pages → cross-diff the residual skeletons across the corpus to classify content into the spec's four layers → rebuild the skeleton as a slot template → emit it for a real page → prove byte-parity after masking both sides identically.

**Tech Stack:** Python 3.11+ stdlib + `lxml` (XML) + `pytest`. No Jinja2 (YAGNI — slot replacement via unique tokens; PHP is full of `{}` so `str.format` is unusable anyway).

**Corpus facts the plan relies on (verified 2026-07-18):**
- Vendor exe: `C:\Program Files (x86)\SQL Maestro Group\PostgreSQL PHP Generator Professional\PgPHPGeneratorPro.exe` — CLI `<pgtp> -output <dir> -generate` works.
- Corpus: `...\re_phpgen\input\01.pgtp … 37.pgtp`, generated into sibling folders `input\01\ …` (generation batch may still be running; tasks that sweep the corpus must skip projects whose folder is missing/empty — e.g. `29` was empty at planning time. Smallest completed projects: `03` (153 KB), `05` (86 KB)).
- A generated project = `components/` + `database_engine/` runtime dirs (opaque, reused) + ~40 top-level page `.php` files.
- Top-level page class naming: schema-qualified table name with `_` (e.g. `xc_psv_statePage extends Page` in `psv_state.php`) — **not** the file name. Detail classes concatenate the ancestry chain (`sc_jcgroup_sc_r_jcg_jcPage extends DetailPage`).
- Per-field blocks are anchored by 3-line comment banners: `//` / `// <Context> column for <field> field` / `//`.

---

## File Structure (new repo: `C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen\`)

```
re_phpgen/
├── .gitignore                      # input/, work/, venv/, __pycache__/
├── pyproject.toml
├── src/re_phpgen/
│   ├── __init__.py
│   ├── config.py                   # vendor exe + corpus paths
│   ├── oracle.py                   # generate(pgtp, out_dir) via vendor CLI
│   ├── normalizer.py               # normalize(text) — volatile-noise removal
│   ├── php_scanner.py              # string/comment-aware brace scanner
│   ├── masker.py                   # mask method bodies + handler code
│   ├── handlers.py                 # extract event-handler texts from .pgtp
│   ├── catalog.py                  # project → [(page fileName, php path, class name)]
│   └── skeleton.py                 # emit_skeleton(slots) from template
├── templates/page_skeleton.php.tmpl   # derived in Task 8 (checked in)
├── scripts/
│   ├── check_determinism.py        # Task 3
│   ├── analyze_skeleton_layers.py  # Task 7
│   └── skeleton_coverage.py        # Task 10
├── docs/findings/                  # determinism.md, skeleton_layers.md
└── tests/
    ├── conftest.py
    ├── test_oracle.py
    ├── test_normalizer.py
    ├── test_php_scanner.py
    ├── test_masker.py
    ├── test_handlers.py
    ├── test_catalog.py
    ├── test_skeleton.py
    └── test_parity.py              # the beachhead gate
```

Work products (generated, not committed): `work/` for oracle output during tests/scripts.

---

### Task 1: Project scaffolding

**Files:**
- Create: `.gitignore`, `pyproject.toml`, `src/re_phpgen/__init__.py`, `src/re_phpgen/config.py`, `tests/conftest.py`

- [ ] **Step 1: Initialize repo and venv**

```powershell
cd "C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen"
git init
python -m venv venv
.\venv\Scripts\pip install pytest lxml
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
input/
work/
venv/
__pycache__/
*.pyc
.pytest_cache/
```

`input/` is excluded deliberately: multi-MB corpus containing plaintext DB/SSH credentials inside the `.pgtp` files. Never commit it.

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[project]
name = "re_phpgen"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["lxml"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
markers = ["oracle: invokes the vendor generator exe (slow, Windows-only)"]
```

- [ ] **Step 4: Write `src/re_phpgen/config.py`**

```python
from pathlib import Path

VENDOR_EXE = Path(
    r"C:\Program Files (x86)\SQL Maestro Group"
    r"\PostgreSQL PHP Generator Professional\PgPHPGeneratorPro.exe"
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = PROJECT_ROOT / "input"
WORK_ROOT = PROJECT_ROOT / "work"

# Runtime dirs inside a generated project — opaque vendor framework, never analyzed as pages.
RUNTIME_DIRS = {"components", "database_engine"}


def corpus_projects() -> list[str]:
    """Numbered projects whose generation output exists (skip still-running/missing)."""
    out = []
    for pgtp in sorted(CORPUS_ROOT.glob("*.pgtp")):
        gen_dir = CORPUS_ROOT / pgtp.stem
        if gen_dir.is_dir() and any(gen_dir.glob("*.php")):
            out.append(pgtp.stem)
    return out
```

- [ ] **Step 5: Write `tests/conftest.py` and empty `src/re_phpgen/__init__.py`**

```python
import pytest
from re_phpgen.config import CORPUS_ROOT, corpus_projects


@pytest.fixture(scope="session")
def corpus():
    projects = corpus_projects()
    if not projects:
        pytest.skip("corpus not generated yet")
    return projects
```

- [ ] **Step 6: Verify pytest collects (0 tests, no errors)**

Run: `.\venv\Scripts\pytest --collect-only`
Expected: `no tests ran` with exit code 5, no import errors.

- [ ] **Step 7: Commit**

```powershell
git add -A && git commit -m "chore: scaffold re_phpgen project (config, pytest, corpus gitignored)"
```

---

### Task 2: Oracle wrapper

**Files:**
- Create: `src/re_phpgen/oracle.py`
- Test: `tests/test_oracle.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from re_phpgen.config import CORPUS_ROOT, WORK_ROOT
from re_phpgen.oracle import generate


@pytest.mark.oracle
def test_generate_produces_php(corpus):
    project = "03" if "03" in corpus else corpus[0]
    out = WORK_ROOT / "test_oracle" / project
    generate(CORPUS_ROOT / f"{project}.pgtp", out)
    pages = list(out.glob("*.php"))
    assert len(pages) > 0
    assert (out / "components").is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_oracle.py -v`
Expected: FAIL with `ModuleNotFoundError`/`ImportError` for `re_phpgen.oracle`.

- [ ] **Step 3: Write `src/re_phpgen/oracle.py`**

```python
import subprocess
from pathlib import Path

from re_phpgen.config import VENDOR_EXE


def generate(pgtp: Path, out_dir: Path, timeout: int = 600) -> None:
    """Run the vendor generator: ground-truth .pgtp -> .php compilation (the oracle)."""
    if not pgtp.is_file():
        raise FileNotFoundError(pgtp)
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(VENDOR_EXE), str(pgtp), "-output", str(out_dir), "-generate"],
        check=True,
        timeout=timeout,
        capture_output=True,
    )
```

`subprocess.run` waits on the process handle (same as `Start-Process -Wait`, which the corpus batch already proved sufficient). If generation ever detaches and returns early, the test's `*.php` assertion catches it — then poll for output quiescence instead; don't guess now.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\venv\Scripts\pytest tests/test_oracle.py -v -m oracle`
Expected: PASS (takes up to a couple of minutes — real generation).

- [ ] **Step 5: Commit**

```powershell
git add -A && git commit -m "feat: oracle wrapper invoking vendor generator CLI"
```

---

### Task 3: Determinism check (first experiment — spec §9)

**Files:**
- Create: `scripts/check_determinism.py`, `docs/findings/determinism.md`

- [ ] **Step 1: Write `scripts/check_determinism.py`**

```python
"""Generate one project twice; report every byte-differing file with a diff excerpt.

Usage: python scripts/check_determinism.py [project=03]
"""
import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from re_phpgen.config import CORPUS_ROOT, WORK_ROOT
from re_phpgen.oracle import generate


def tree_files(root: Path) -> list[Path]:
    return sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())


def main(project: str = "03") -> None:
    pgtp = CORPUS_ROOT / f"{project}.pgtp"
    run_a = WORK_ROOT / "determinism" / f"{project}_a"
    run_b = WORK_ROOT / "determinism" / f"{project}_b"
    for d in (run_a, run_b):
        generate(pgtp, d)

    files_a, files_b = tree_files(run_a), tree_files(run_b)
    if files_a != files_b:
        print("FILE LIST DIFFERS:")
        print(sorted(set(files_a) ^ set(files_b)))

    differing = 0
    for rel in files_a:
        a_bytes = (run_a / rel).read_bytes()
        b_bytes = (run_b / rel).read_bytes()
        if a_bytes == b_bytes:
            continue
        differing += 1
        print(f"\n=== DIFFERS: {rel} ===")
        a_lines = a_bytes.decode("utf-8", "replace").splitlines()
        b_lines = b_bytes.decode("utf-8", "replace").splitlines()
        for line in list(difflib.unified_diff(a_lines, b_lines, lineterm=""))[:40]:
            print(line)
    print(f"\n{differing} differing file(s) out of {len(files_a)}")


if __name__ == "__main__":
    main(*sys.argv[1:])
```

- [ ] **Step 2: Run it**

Run: `.\venv\Scripts\python scripts/check_determinism.py 03`
Expected: a report ending `N differing file(s) out of M`. Hoped-for N=0; any N>0 lines show the volatile patterns (timestamps, GUIDs, paths…).

- [ ] **Step 3: Record findings in `docs/findings/determinism.md`**

Write down: project used, N/M, and for each volatile pattern the exact regex that matches it (these become normalizer rules in Task 4). If N=0, record that too — the normalizer then only needs line-ending unification.

- [ ] **Step 4: Commit**

```powershell
git add -A && git commit -m "feat: determinism check script + recorded findings"
```

---

### Task 4: Normalizer

**Files:**
- Create: `src/re_phpgen/normalizer.py`
- Test: `tests/test_normalizer.py`

- [ ] **Step 1: Write the failing test**

```python
from re_phpgen.normalizer import normalize


def test_line_endings_unified():
    assert normalize("a\r\nb\r\n") == "a\nb\n"


def test_stable_text_unchanged():
    php = "<?php\n    class xPage extends Page\n    {\n    }\n"
    assert normalize(php) == php
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\venv\Scripts\pytest tests/test_normalizer.py -v`
Expected: FAIL with `ModuleNotFoundError` for `re_phpgen.normalizer`.

- [ ] **Step 3: Write `src/re_phpgen/normalizer.py`**

```python
import re

# Volatile patterns discovered by scripts/check_determinism.py (docs/findings/determinism.md).
# Each entry: (compiled pattern, replacement). Empty if generation proved deterministic.
RULES: list[tuple[re.Pattern[str], str]] = []


def normalize(text: str) -> str:
    """Canonical form for diffing: unify line endings, blank out volatile noise."""
    text = text.replace("\r\n", "\n")
    for pattern, replacement in RULES:
        text = pattern.sub(replacement, text)
    return text
```

Then encode every volatile pattern from `docs/findings/determinism.md` as a `RULES` entry, **each with its own test** asserting a real captured sample line normalizes to the replacement (copy sample lines from the determinism diff output into the tests).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\venv\Scripts\pytest tests/test_normalizer.py -v`
Expected: PASS.

- [ ] **Step 5: Add the end-to-end determinism assertion**

Append to `tests/test_normalizer.py` (uses the two runs Task 3 left in `work/determinism/`):

```python
import pytest
from re_phpgen.config import WORK_ROOT


@pytest.mark.oracle
def test_normalized_reruns_identical():
    run_a, run_b = WORK_ROOT / "determinism" / "03_a", WORK_ROOT / "determinism" / "03_b"
    if not run_a.is_dir():
        pytest.skip("run check_determinism.py first")
    for php_a in run_a.rglob("*.php"):
        php_b = run_b / php_a.relative_to(run_a)
        assert normalize(php_a.read_text("utf-8")) == normalize(
            php_b.read_text("utf-8")
        ), php_a.name
```

Run: `.\venv\Scripts\pytest tests/test_normalizer.py -v -m oracle`
Expected: PASS — this proves `normalize()` fully absorbs generation noise, the precondition for all parity diffs.

- [ ] **Step 6: Commit**

```powershell
git add -A && git commit -m "feat: normalizer absorbing all vendor-generation nondeterminism"
```

---

### Task 5: String/comment-aware PHP scanner + method-body masker

The skeleton is what remains of a page after removing the two hole types: (a) per-field method bodies, (b) event-handler code pasted from the XML. This task does (a).

**Files:**
- Create: `src/re_phpgen/php_scanner.py`, `src/re_phpgen/masker.py`
- Test: `tests/test_php_scanner.py`, `tests/test_masker.py`

- [ ] **Step 1: Write the failing scanner test**

```python
from re_phpgen.php_scanner import find_body_span


SRC = """
    class fooPage extends Page
    {
        protected function AddEditColumns(Grid $grid)
        {
            $x = 'a string with } brace';
            // a comment with } brace
            /* block } comment */
            if (true) { $y = "another } one"; }
        }

        protected function CreateGrid()
        {
            return null;
        }
    }
"""


def test_find_body_span_skips_strings_and_comments():
    span = find_body_span(SRC, "AddEditColumns")
    body = SRC[span[0]:span[1]]
    assert "a string with" in body
    assert "CreateGrid" not in body


def test_missing_method_returns_none():
    assert find_body_span(SRC, "NoSuchMethod") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\venv\Scripts\pytest tests/test_php_scanner.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/re_phpgen/php_scanner.py`**

```python
import re


def find_body_span(text: str, method_name: str) -> tuple[int, int] | None:
    """(start, end) character span of the body of `function <name>(...) { ... }`,
    excluding the outer braces. Brace matching skips PHP strings and comments.
    """
    decl = re.search(rf"function\s+{re.escape(method_name)}\s*\(", text)
    if decl is None:
        return None
    open_brace = text.find("{", decl.end())
    if open_brace == -1:
        return None

    depth, i, n = 1, open_brace + 1, len(text)
    while i < n and depth:
        c = text[i]
        if c in ("'", '"'):                      # quoted string: skip to unescaped close
            quote, i = c, i + 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    break
                i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":   # line comment
            i = text.find("\n", i)
            if i == -1:
                return None
        elif c == "/" and i + 1 < n and text[i + 1] == "*":   # block comment
            i = text.find("*/", i)
            if i == -1:
                return None
            i += 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return (open_brace + 1, i)
        i += 1
    return None
```

- [ ] **Step 4: Run scanner tests to verify they pass**

Run: `.\venv\Scripts\pytest tests/test_php_scanner.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing masker test**

```python
from re_phpgen.masker import HOLE_METHODS, mask_method_bodies
from tests.test_php_scanner import SRC


def test_mask_replaces_listed_method_bodies():
    masked = mask_method_bodies(SRC, ["AddEditColumns"])
    assert "@@HOLE:AddEditColumns@@" in masked
    assert "a string with" not in masked
    assert "CreateGrid" in masked            # unlisted method untouched


def test_hole_methods_is_the_per_field_context_list():
    assert "AddEditColumns" in HOLE_METHODS
    assert "AddInsertColumns" in HOLE_METHODS
```

- [ ] **Step 6: Run masker test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_masker.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 7: Write `src/re_phpgen/masker.py`**

```python
from re_phpgen.php_scanner import find_body_span

# Methods whose bodies are per-field emissions ("holes" in the skeleton).
# Initial list from the observed method inventory of development_equipment.php;
# Task 7's cross-diff report extends it if other methods vary per page.
HOLE_METHODS = [
    "AddOperationsColumns",
    "AddFieldColumns",
    "AddSingleRecordViewColumns",
    "AddEditColumns",
    "AddMultiEditColumns",
    "AddToggleEditColumns",
    "AddInsertColumns",
    "AddMultiUploadColumn",
    "AddPrintColumns",
    "AddExportColumns",
    "AddCompareColumns",
    "AddCompareHeaderColumns",
    "getFiltersColumns",
    "setupQuickFilter",
    "setupColumnFilter",
    "setupFilterBuilder",
    "doRegisterHandlers",
    "CreateGrid",
]


def mask_method_bodies(text: str, methods: list[str] | None = None) -> str:
    """Replace each listed method's body with a @@HOLE:<name>@@ placeholder."""
    result = text
    for name in methods if methods is not None else HOLE_METHODS:
        span = find_body_span(result, name)
        if span is None:
            continue
        result = result[: span[0]] + f" @@HOLE:{name}@@ " + result[span[1]:]
    return result
```

- [ ] **Step 8: Run masker tests, then a real-corpus smoke test**

Run: `.\venv\Scripts\pytest tests/test_masker.py -v`
Expected: PASS.

Append a real-file test to `tests/test_masker.py`:

```python
from re_phpgen.config import CORPUS_ROOT


def test_masks_every_page_of_smallest_project(corpus):
    project = "03" if "03" in corpus else corpus[0]
    for php in (CORPUS_ROOT / project).glob("*.php"):
        text = php.read_text("utf-8")
        masked = mask_method_bodies(text)
        if "AddFieldColumns" in text:
            assert "@@HOLE:AddFieldColumns@@" in masked, php.name
```

Run: `.\venv\Scripts\pytest tests/test_masker.py -v`
Expected: PASS. A failure here means the brace scanner mis-tracks some real construct — fix the scanner, don't weaken the test.

- [ ] **Step 9: Commit**

```powershell
git add -A && git commit -m "feat: PHP brace scanner + per-field method-body masker"
```

---

### Task 6: Event-handler extraction and masking

Hole type (b): handler code copied verbatim from the XML into the page. We know the exact text from the `.pgtp` itself, so masking is find-and-replace of known strings.

**Files:**
- Create: `src/re_phpgen/handlers.py`
- Test: `tests/test_handlers.py`

- [ ] **Step 1: Write the failing test**

```python
from lxml import etree

from re_phpgen.handlers import handler_texts, mask_handler_code

XML = b"""<Project>
  <EventHandlers>
    <OnGlobalBeforePageExecute>$x = 1 &amp;&amp; 2;</OnGlobalBeforePageExecute>
  </EventHandlers>
  <Presentation><Pages><Page fileName="p">
    <EventHandlers><OnPageLoaded>echo "hi";</OnPageLoaded></EventHandlers>
  </Page></Pages></Presentation>
</Project>"""


def test_handler_texts_collects_all_unescaped(tmp_path):
    pgtp = tmp_path / "t.pgtp"
    pgtp.write_bytes(XML)
    texts = handler_texts(pgtp)
    assert "$x = 1 && 2;" in texts          # entity-unescaped
    assert 'echo "hi";' in texts            # page-level too


def test_mask_handler_code_replaces_verbatim_occurrence():
    php = 'before\n    $x = 1 && 2;\nafter'
    masked = mask_handler_code(php, ["$x = 1 && 2;"])
    assert "@@HANDLER@@" in masked and "$x = 1" not in masked
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\venv\Scripts\pytest tests/test_handlers.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/re_phpgen/handlers.py`**

```python
from pathlib import Path

from lxml import etree


def handler_texts(pgtp: Path) -> list[str]:
    """Every event-handler code body in the project (global + per-page),
    entity-unescaped exactly as the generator pastes it, longest first
    (so masking never clobbers a short handler embedded in a longer one).
    """
    tree = etree.parse(str(pgtp))
    texts = {
        el.text
        for el in tree.iter()
        if el.getparent() is not None
        and el.getparent().tag == "EventHandlers"
        and el.text
        and el.text.strip()
    }
    return sorted(texts, key=len, reverse=True)


def mask_handler_code(php_text: str, texts: list[str]) -> str:
    for t in texts:
        php_text = php_text.replace(t, "@@HANDLER@@")
        normalized = t.replace("\r\n", "\n")
        if normalized != t:
            php_text = php_text.replace(normalized, "@@HANDLER@@")
    return php_text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\venv\Scripts\pytest tests/test_handlers.py -v`
Expected: PASS.

Known risk (spec §11 adjacent): the generator may re-indent handler code, breaking verbatim matching. Task 7's report will show handler text surviving in skeletons if so; the fix then is whitespace-tolerant matching (normalize leading indentation on both sides before replacing) — do not implement it preemptively.

- [ ] **Step 5: Commit**

```powershell
git add -A && git commit -m "feat: event-handler extraction from .pgtp + verbatim masking"
```

---

### Task 7: Corpus catalog + skeleton-layer analysis (spec §6 method)

**Files:**
- Create: `src/re_phpgen/catalog.py`, `scripts/analyze_skeleton_layers.py`, `docs/findings/skeleton_layers.md`
- Test: `tests/test_catalog.py`

- [ ] **Step 1: Write the failing catalog test**

```python
from re_phpgen.catalog import top_level_pages
from re_phpgen.config import CORPUS_ROOT


def test_catalog_matches_generated_files(corpus):
    project = "03" if "03" in corpus else corpus[0]
    pages = top_level_pages(CORPUS_ROOT / f"{project}.pgtp")
    assert len(pages) > 0
    found = sum(1 for p in pages if (CORPUS_ROOT / project / f"{p.file_name}.php").is_file())
    assert found / len(pages) > 0.9   # tolerate excluded/special pages, not systemic mismatch
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/re_phpgen/catalog.py`**

```python
from dataclasses import dataclass
from pathlib import Path

from lxml import etree


@dataclass(frozen=True)
class PageInfo:
    file_name: str      # Page@fileName → <fileName>.php
    table_name: str     # Page@tableName (schema-qualified) → class name stem
    page_type: str      # Page@type ("" if absent)


def top_level_pages(pgtp: Path) -> list[PageInfo]:
    """Top-level Pages only: Presentation/Pages/Page, NOT nested Detail pages."""
    tree = etree.parse(str(pgtp))
    pages = []
    for el in tree.findall("Presentation/Pages/Page"):
        pages.append(
            PageInfo(
                file_name=el.get("fileName", ""),
                table_name=el.get("tableName", ""),
                page_type=el.get("type", ""),
            )
        )
    return [p for p in pages if p.file_name]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\venv\Scripts\pytest tests/test_catalog.py -v`
Expected: PASS. If the XPath finds nothing, inspect the real structure with `grep -m3 "<Pages>" input/03.pgtp` and fix the path — the element hierarchy is documented in the format memory as `Presentation/Pages/Page`.

- [ ] **Step 5: Write `scripts/analyze_skeleton_layers.py`**

```python
"""Cross-diff masked skeletons across the corpus; classify lines into the spec's layers.

Layer 1: line appears in every page of every project (global constant).
Layer 2: line constant within a project but not global (project parameter).
Rest:    per-page (derived identifiers / unmasked leftovers -> report for review).

Output: docs/findings/skeleton_layers_report.txt (+ summary printed).
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from re_phpgen.catalog import top_level_pages
from re_phpgen.config import CORPUS_ROOT, PROJECT_ROOT, corpus_projects
from re_phpgen.handlers import handler_texts, mask_handler_code
from re_phpgen.masker import mask_method_bodies
from re_phpgen.normalizer import normalize


def skeleton(php_path: Path, htexts: list[str]) -> list[str]:
    text = normalize(php_path.read_text("utf-8"))
    text = mask_handler_code(text, htexts)
    return mask_method_bodies(text).splitlines()


def main() -> None:
    line_projects: dict[str, set[str]] = defaultdict(set)   # line -> projects containing it
    line_pages: dict[str, int] = defaultdict(int)            # line -> page count
    total_pages = 0
    per_project_pages: dict[str, int] = {}

    for project in corpus_projects():
        htexts = handler_texts(CORPUS_ROOT / f"{project}.pgtp")
        pages = [
            p for p in top_level_pages(CORPUS_ROOT / f"{project}.pgtp")
            if (CORPUS_ROOT / project / f"{p.file_name}.php").is_file()
        ]
        per_project_pages[project] = len(pages)
        for p in pages:
            total_pages += 1
            for line in set(skeleton(CORPUS_ROOT / project / f"{p.file_name}.php", htexts)):
                line_projects[line].add(project)
                line_pages[line] += 1

    n_projects = len(per_project_pages)
    layer1 = {l for l, c in line_pages.items() if c == total_pages}
    # Layer-2 candidate: appears in every page of at least one project (project-constant)
    # but not in every page globally.
    layer2 = {
        l for l in line_pages
        if l not in layer1
        and any(line_pages[l] >= per_project_pages[p] for p in line_projects[l])
        and len(line_projects[l]) < n_projects
    }
    per_page = [l for l in line_pages if l not in layer1 and l not in layer2]

    report = PROJECT_ROOT / "docs" / "findings" / "skeleton_layers_report.txt"
    with report.open("w", encoding="utf-8") as f:
        f.write(f"projects={n_projects} pages={total_pages}\n\n")
        for name, lines in [("LAYER1", layer1), ("LAYER2-CANDIDATE", layer2), ("PER-PAGE", per_page)]:
            f.write(f"===== {name} ({len(lines)} lines) =====\n")
            for l in sorted(lines):
                f.write(l + "\n")
            f.write("\n")
    print(f"pages={total_pages} layer1={len(layer1)} "
          f"layer2~={len(layer2)} per-page={len(per_page)} -> {report}")


if __name__ == "__main__":
    main()
```

Note: the layer-2 heuristic above is a starting filter, not truth — the point of the report is **human review**. The executor reads `skeleton_layers_report.txt`, especially the PER-PAGE section, which must shrink to only: derived identifiers (class names, handler-link names), page-parameter lines (captions, table names), and any leftovers exposing an unmasked varying method (→ add it to `HOLE_METHODS`) or failed handler masking (→ whitespace-tolerant matching per Task 6 note).

- [ ] **Step 6: Run analysis and iterate the maskers until PER-PAGE is explainable**

Run: `.\venv\Scripts\python scripts/analyze_skeleton_layers.py`
Expected: summary line + report file. Iterate: every PER-PAGE line must be attributable to a slot (derived identifier or page/project parameter). Add newly-discovered varying methods to `HOLE_METHODS` (with the masker test updated) and rerun until stable.

- [ ] **Step 7: Write up `docs/findings/skeleton_layers.md`**

Record: the final `HOLE_METHODS` list; the layer-1 line count; every layer-2 parameter found and its XML/settings source (e.g. output path, encoding, userspice header → which project-level XML element); every per-page slot and its derivation rule (class name = `tableName` with `.`→`_` + `Page` — verify and state exactly); whether handler masking needed whitespace tolerance; resolution of the caption-localization question from spec §11 if the data answers it.

- [ ] **Step 8: Commit**

```powershell
git add -A && git commit -m "feat: corpus catalog + skeleton layer analysis with findings"
```

---

### Task 8: Skeleton template + emitter

**Files:**
- Create: `templates/page_skeleton.php.tmpl`, `src/re_phpgen/skeleton.py`
- Test: `tests/test_skeleton.py`

- [ ] **Step 1: Derive the template from a real page**

Pick the simplest top-level page of the smallest completed project (fewest bytes: `ls -S` the `input/03/*.php` list, take the smallest non-runtime page). Produce its masked skeleton and replace every layer-2/per-page token (per `docs/findings/skeleton_layers.md`) with `@@SLOT:<name>@@` tokens:

```powershell
.\venv\Scripts\python -c "
import sys; sys.path.insert(0, 'src')
from pathlib import Path
from re_phpgen.config import CORPUS_ROOT
from re_phpgen.handlers import handler_texts, mask_handler_code
from re_phpgen.masker import mask_method_bodies
from re_phpgen.normalizer import normalize
page = Path('input/03/<CHOSEN_PAGE>.php')   # executor fills in the chosen page
text = mask_method_bodies(mask_handler_code(normalize(page.read_text('utf-8')), handler_texts(CORPUS_ROOT / '03.pgtp')))
Path('templates/page_skeleton.php.tmpl').write_text(text, encoding='utf-8', newline='\n')
"
```

Then hand-edit `templates/page_skeleton.php.tmpl`, guided by the findings doc: replace each concrete page/project value with its slot. Minimum slot set (extend per findings): `@@SLOT:CLASS_NAME@@`, `@@SLOT:TABLE_NAME@@`, `@@SLOT:PAGE_CAPTION@@`, `@@SLOT:PROJECT_HEADER@@` (the per-project global-handler/userspice block), plus `@@HANDLER@@`/`@@HOLE:*@@` markers kept as-is (they are masked on both sides at parity time).

- [ ] **Step 2: Write the failing emitter test**

```python
from re_phpgen.skeleton import emit_skeleton


def test_emit_fills_all_slots():
    out = emit_skeleton(
        {
            "CLASS_NAME": "xc_fooPage",
            "TABLE_NAME": '"xc"."foo"',
            "PAGE_CAPTION": "Foo",
            "PROJECT_HEADER": "// header",
        }
    )
    assert "xc_fooPage" in out
    assert "@@SLOT:" not in out            # no slot left unfilled


def test_unknown_slot_in_template_raises():
    import pytest
    with pytest.raises(KeyError):
        emit_skeleton({"CLASS_NAME": "x"})   # missing the rest
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_skeleton.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Write `src/re_phpgen/skeleton.py`**

```python
import re

from re_phpgen.config import PROJECT_ROOT

TEMPLATE = PROJECT_ROOT / "templates" / "page_skeleton.php.tmpl"
_SLOT = re.compile(r"@@SLOT:(\w+)@@")


def emit_skeleton(slots: dict[str, str]) -> str:
    text = TEMPLATE.read_text("utf-8")

    def fill(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in slots:
            raise KeyError(f"template slot {name!r} not provided")
        return slots[name]

    return _SLOT.sub(fill, text)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\venv\Scripts\pytest tests/test_skeleton.py -v`
Expected: PASS. If the template ended up with slots beyond the test's set, update the test's slot dict to the real full set — the template is the source of truth.

- [ ] **Step 6: Commit**

```powershell
git add -A && git commit -m "feat: page skeleton template + slot emitter"
```

---

### Task 9: The beachhead gate — mask-the-holes byte-parity (spec §6 definition of done)

**Files:**
- Create: `tests/test_parity.py`
- Modify: `src/re_phpgen/skeleton.py` (add `slots_for_page`)

- [ ] **Step 1: Write the failing parity test**

```python
import pytest

from re_phpgen.catalog import top_level_pages
from re_phpgen.config import CORPUS_ROOT
from re_phpgen.handlers import handler_texts, mask_handler_code
from re_phpgen.masker import mask_method_bodies
from re_phpgen.normalizer import normalize
from re_phpgen.skeleton import emit_skeleton, slots_for_page

PROJECT = "03"
PAGE_FILE = "<CHOSEN_PAGE>"   # the Task 8 template's source page


def _masked(text: str, htexts: list[str]) -> str:
    return mask_method_bodies(mask_handler_code(normalize(text), htexts))


def test_skeleton_byte_parity_on_template_source_page():
    pgtp = CORPUS_ROOT / f"{PROJECT}.pgtp"
    htexts = handler_texts(pgtp)
    page = next(p for p in top_level_pages(pgtp) if p.file_name == PAGE_FILE)

    vendor = _masked(
        (CORPUS_ROOT / PROJECT / f"{PAGE_FILE}.php").read_text("utf-8"), htexts
    )
    ours = _masked(emit_skeleton(slots_for_page(pgtp, page)), htexts)

    assert ours == vendor


def test_skeleton_byte_parity_on_second_page_same_project():
    """The template must generalize beyond the page it was derived from."""
    pgtp = CORPUS_ROOT / f"{PROJECT}.pgtp"
    htexts = handler_texts(pgtp)
    others = [
        p for p in top_level_pages(pgtp)
        if p.file_name != PAGE_FILE
        and (CORPUS_ROOT / PROJECT / f"{p.file_name}.php").is_file()
    ]
    if not others:
        pytest.skip("project has a single page")
    page = others[0]
    vendor = _masked(
        (CORPUS_ROOT / PROJECT / f"{page.file_name}.php").read_text("utf-8"), htexts
    )
    ours = _masked(emit_skeleton(slots_for_page(pgtp, page)), htexts)
    assert ours == vendor
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\venv\Scripts\pytest tests/test_parity.py -v`
Expected: FAIL — `slots_for_page` doesn't exist yet.

- [ ] **Step 3: Implement `slots_for_page` in `src/re_phpgen/skeleton.py`**

```python
from pathlib import Path

from lxml import etree

from re_phpgen.catalog import PageInfo


def class_name_for(page: PageInfo) -> str:
    # Verified rule from Task 7 findings: schema-qualified table name,
    # '.' -> '_', suffixed 'Page' (e.g. xc.psv_state -> xc_psv_statePage).
    return page.table_name.replace(".", "_") + "Page"


def slots_for_page(pgtp: Path, page: PageInfo) -> dict[str, str]:
    """Derive every template slot from the .pgtp for one top-level page.
    The exact slot set mirrors templates/page_skeleton.php.tmpl (Task 8) and
    the derivations recorded in docs/findings/skeleton_layers.md (Task 7).
    """
    tree = etree.parse(str(pgtp))
    slots = {
        "CLASS_NAME": class_name_for(page),
        "TABLE_NAME": page.table_name,
        "PAGE_CAPTION": _page_caption(tree, page),
        "PROJECT_HEADER": _project_header(tree),
    }
    return slots
```

`_page_caption` / `_project_header` (and any further slots the template demands) are written against the exact sources recorded in the findings doc — e.g. `Page@caption`, and the project-level global handler / userspice block. Each derivation gets its own unit test in `tests/test_skeleton.py` with values taken from project 03's XML.

- [ ] **Step 4: Iterate to green — this is the core reverse-engineering loop**

Run: `.\venv\Scripts\pytest tests/test_parity.py -v`

Debug protocol for a diff: print `difflib.unified_diff(ours, vendor)`, take the **first** differing line, attribute it (wrong slot derivation? missing slot? unmasked varying method → extend `HOLE_METHODS` + its test? handler indentation → Task 6's whitespace-tolerant fix?), fix that one cause, rerun. Repeat until byte-identical. Do not special-case the test page — every fix must be a rule, not a patch.

Expected end state: both tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add -A && git commit -m "feat: skeleton byte-parity achieved on real pages (beachhead gate)"
```

---

### Task 10: Skeleton coverage across the corpus (spec §9 metric)

**Files:**
- Create: `scripts/skeleton_coverage.py`

- [ ] **Step 1: Write `scripts/skeleton_coverage.py`**

```python
"""Skeleton parity coverage: % of all corpus top-level pages whose masked
skeleton is byte-identical to our emitted skeleton. Spec §9's metric, scoped
to the skeleton beachhead."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from re_phpgen.catalog import top_level_pages
from re_phpgen.config import CORPUS_ROOT, corpus_projects
from re_phpgen.handlers import handler_texts, mask_handler_code
from re_phpgen.masker import mask_method_bodies
from re_phpgen.normalizer import normalize
from re_phpgen.skeleton import emit_skeleton, slots_for_page


def masked(text: str, htexts: list[str]) -> str:
    return mask_method_bodies(mask_handler_code(normalize(text), htexts))


def main() -> None:
    ok = fail = 0
    failures: list[str] = []
    for project in corpus_projects():
        pgtp = CORPUS_ROOT / f"{project}.pgtp"
        htexts = handler_texts(pgtp)
        for page in top_level_pages(pgtp):
            vendor_php = CORPUS_ROOT / project / f"{page.file_name}.php"
            if not vendor_php.is_file():
                continue
            try:
                ours = masked(emit_skeleton(slots_for_page(pgtp, page)), htexts)
                vendor = masked(vendor_php.read_text("utf-8"), htexts)
                if ours == vendor:
                    ok += 1
                    continue
            except Exception as e:                      # noqa: BLE001 — survey must finish
                failures.append(f"{project}/{page.file_name}: ERROR {e}")
                fail += 1
                continue
            failures.append(f"{project}/{page.file_name}: DIFF")
            fail += 1
    total = ok + fail
    print(f"skeleton parity: {ok}/{total} pages ({ok / total:.1%})")
    for line in failures[:50]:
        print("  " + line)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it and record the baseline**

Run: `.\venv\Scripts\python scripts/skeleton_coverage.py`
Expected: a percentage. It will **not** be 100% — other projects have different per-project headers and likely page-type variants (`DetailPage`-only files, modal/view pages) the single template doesn't cover yet. Record the number and the dominant failure causes at the end of `docs/findings/skeleton_layers.md`. That ranked failure list **is the input for the next plan** (page-type skeleton variants, then cell emitters).

- [ ] **Step 3: Commit and update project memory/status**

```powershell
git add -A && git commit -m "feat: corpus-wide skeleton parity coverage metric"
```

Also update the `re-phpgen-reverse-engineering` memory file's status line (beachhead achieved, coverage %, next: variants/cell emitters).

---

## Verification (whole plan)

Run: `.\venv\Scripts\pytest -v` (all tests, including `-m oracle` once) — everything green.
The beachhead's definition of done (spec §6): `tests/test_parity.py` passes — our emitted skeleton for real top-level pages is byte-identical to the vendor's after identical masking/normalization on both sides.

## Explicitly deferred (next plans)

- Per-field **cell emitters** (`(context × editor-type)` matrix) — needs the fine-grained banner segmenter; the coarse method-body masker here is intentionally not it.
- `DetailPage` / modal / view-based skeleton variants (spec §6 names them follow-on slices).
- Runtime-contract map document (spec §8) — starts alongside cell-emitter work, when we begin cataloging constructor signatures.
- Model-layer reuse from `pgtp_editor` (spec §7) — the beachhead needs only shallow XML access (`catalog.py`, `handlers.py`); re-evaluate when cell emitters need `DataSources` schema.
