# Template Variant Generalization + Master-Detail Emission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the fixed single-class skeleton template into derived slots (global handlers, `GetEnable*` flags, page parameters) and emit multi-class master-detail page files, per spec `docs/superpowers/specs/2026-07-19-re-phpgen-template-variants-master-detail-design.md`.

**Architecture:** All work in the `re_phpgen` repo (`C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen`, git `master`; venv at `venv\`; tests `.\venv\Scripts\pytest -q -m "not oracle"`). The single file template splits into a **file frame** + **one class template** (master vs detail = two slots: `EXTENDS`, `CMDRG`). Conditional content is computed in Python as slot values (whole blocks or empty string); the dumb `@@SLOT:NAME@@` engine stays. New `catalog.detail_tree` walks nested `Details/Detail/Page` with the FK-validity emission filter; `skeleton.class_plans_for_page` produces the post-order class list with file-global ordinal naming; `skeleton.emit_page_file` assembles the file. Two rules are **derived from corpus correlation during implementation** (the `GetEnable*` flag mapping and the `CreatePageNavigator` variant predicate) — those tasks contain the derivation procedure, encoding shape, and corpus-wide validation tests instead of pre-known constants.

**Tech Stack:** Python 3.11 stdlib + lxml; existing modules `config.parse_pgtp` (lru-cached, recover=True), `catalog.top_level_pages`/`PageInfo`, `skeleton.sanitize_table_name`/`class_name_index`/`_encoding_for`, masking pipeline (`normalizer.normalize` → `handlers.handler_texts`/`mask_handler_code` → `masker.mask_method_bodies`).

**Authoritative rules:** `docs/findings/master_detail_analysis.md` (re_phpgen repo, commit `a4c76da`) — referred to below as **MDA**. Key verified rules: FK-validity emission filter (MDA §6: every `FieldMap@foreginColumnName` — vendor's spelling — must be in the detail Page's own `ColumnPresentation@fieldName` set, else the detail subtree is dropped); depth-first post-order class order, master last (§1); ancestry-chain naming rooted at the master stem, 2-digit file-global ordinals in emission order for duplicate full stems (§2); leaf DetailPage = master skeleton − `CreateMasterDetailRecordGrid` + `extends DetailPage`; intermediate details carry `CreateMasterDetailRecordGrid` (§3–5); all wiring is inside already-masked holes (§4). Known exclusions: 8 edge pages (§unresolved) cap corpus reproduction at 471/479.

**Corpus caution:** the corpus is live-growing and gitignored; corpus-wide tests must compute their denominators at runtime, tolerate the ≤8 known mismatches, and `pytest.skip` when the corpus is absent. Never read/print `ConnectionOptions`/`ScriptConnectionOptions` values. Never run the vendor exe.

---

## File Structure

```
templates/
├── file_frame.php.tmpl        # NEW: header (incl. @@SLOT:GLOBAL_HANDLERS@@) + @@SLOT:CLASSES@@ + footer
├── page_class.php.tmpl        # NEW: one class (EXTENDS/CMDRG/FLAGS/PNAV/… slots)
└── page_skeleton.php.tmpl     # RETIRED in Task 6 (deleted after gates pass)

src/re_phpgen/
├── catalog.py                 # + DetailNode, detail_tree()
├── skeleton.py                # + ClassPlan, class_plans_for_page(), emit_page_file(),
│                              #   FLAG_RULES data, slot computation; emit_skeleton stays for the old template until Task 6
└── pangen.py                  # Task 6: calls emit_page_file

tests/
├── test_catalog.py            # + detail-tree tests
├── test_skeleton.py           # + naming/ordinal/class-plan tests + corpus reproduction test
├── test_flag_rules.py         # NEW: mapping validation (synthetic + corpus)
├── test_emit_page_file.py     # NEW: assembly + parity gates (03 regression + 09 gates)
└── test_pangen.py             # Task 6: emit_project uses emit_page_file

docs/findings/master_detail_analysis.md   # + appendix: derived flag mapping + pnav predicate (Task 3)
```

Shared synthetic fixture used by several tasks (define once in `tests/_md_fixtures.py`, import elsewhere):

```python
# tests/_md_fixtures.py
"""Synthetic master-detail project fixtures for template/emission tests."""

MD_XML = b"""<Project>
  <Presentation><Pages>
    <Page fileName="m" tableName="s.master" type="grid" recordsPerPage="20">
      <ColumnPresentations>
        <ColumnPresentation fieldName="id"/>
      </ColumnPresentations>
      <Details>
        <Detail>
          <MasterForeignKeyColumnMap>
            <FieldMap masterColumnName="id" foreginColumnName="master_id"/>
          </MasterForeignKeyColumnMap>
          <Page fileName="d1" tableName="s.child_a" recordsPerPage="10">
            <ColumnPresentations>
              <ColumnPresentation fieldName="master_id"/>
              <ColumnPresentation fieldName="x"/>
            </ColumnPresentations>
            <Details>
              <Detail>
                <MasterForeignKeyColumnMap>
                  <FieldMap masterColumnName="x" foreginColumnName="a_x"/>
                </MasterForeignKeyColumnMap>
                <Page fileName="d1a" tableName="s.grand" recordsPerPage="10">
                  <ColumnPresentations>
                    <ColumnPresentation fieldName="a_x"/>
                  </ColumnPresentations>
                </Page>
              </Detail>
            </Details>
          </Page>
        </Detail>
        <Detail>
          <MasterForeignKeyColumnMap>
            <FieldMap masterColumnName="id" foreginColumnName="NO_SUCH_COL"/>
          </MasterForeignKeyColumnMap>
          <Page fileName="dbad" tableName="s.invalid" recordsPerPage="10">
            <ColumnPresentations>
              <ColumnPresentation fieldName="other"/>
            </ColumnPresentations>
          </Page>
        </Detail>
        <Detail>
          <MasterForeignKeyColumnMap>
            <FieldMap masterColumnName="id" foreginColumnName="master_id"/>
          </MasterForeignKeyColumnMap>
          <Page fileName="d2" tableName="s.child_b" recordsPerPage="10">
            <ColumnPresentations>
              <ColumnPresentation fieldName="master_id"/>
            </ColumnPresentations>
          </Page>
        </Detail>
      </Details>
    </Page>
  </Pages></Presentation>
</Project>"""
```

Expected emission for this fixture (per MDA rules): post-order class list `s_master_s_child_a_s_grand`, `s_master_s_child_a`, `s_master_s_child_b`, master `s_master` — the FK-invalid `s.invalid` detail is dropped.

---

### Task 1: Detail-tree walker with FK-validity filter (`catalog.py`)

**Files:**
- Modify: `src/re_phpgen/catalog.py`
- Create: `tests/_md_fixtures.py` (content above, verbatim)
- Test: `tests/test_catalog.py` (extend)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_catalog.py`):

```python
from re_phpgen.catalog import detail_tree, top_level_pages
from tests._md_fixtures import MD_XML


def _md_project(tmp_path):
    pgtp = tmp_path / "md.pgtp"
    pgtp.write_bytes(MD_XML)
    return pgtp, top_level_pages(pgtp)[0]


def test_detail_tree_structure_and_fk_filter(tmp_path):
    pgtp, master = _md_project(tmp_path)
    roots = detail_tree(pgtp, master)
    # FK-invalid s.invalid dropped; two valid roots in document order
    assert [n.table_name for n in roots] == ["s.child_a", "s.child_b"]
    assert [c.table_name for c in roots[0].children] == ["s.grand"]
    assert roots[1].children == ()


def test_detail_tree_invalid_parent_drops_whole_subtree(tmp_path):
    # Wrap the valid grandchild under an FK-invalid parent: nothing emits.
    xml = MD_XML.replace(b'foreginColumnName="master_id"/>', b'foreginColumnName="gone"/>', 1)
    pgtp = tmp_path / "md2.pgtp"
    pgtp.write_bytes(xml)
    master = top_level_pages(pgtp)[0]
    assert [n.table_name for n in detail_tree(pgtp, master)] == ["s.child_b"]


def test_detail_tree_plain_page_is_empty(tmp_path):
    xml = b'<Project><Presentation><Pages><Page fileName="p" tableName="s.p" type="grid"/></Pages></Presentation></Project>'
    pgtp = tmp_path / "plain.pgtp"
    pgtp.write_bytes(xml)
    master = top_level_pages(pgtp)[0]
    assert detail_tree(pgtp, master) == ()
```

- [ ] **Step 2: Run → FAIL** (ImportError `detail_tree`): `.\venv\Scripts\pytest tests/test_catalog.py -q`

- [ ] **Step 3: Implement** (append to `src/re_phpgen/catalog.py`):

```python
@dataclass(frozen=True)
class DetailNode:
    """One EMITTED detail (FK-valid) in a page's detail tree."""
    table_name: str
    records_per_page: str          # detail Page@recordsPerPage ("" if absent)
    element: object                # the nested lxml Page element (for slot derivation)
    children: tuple["DetailNode", ...]


def _fk_valid(detail_el) -> bool:
    """MDA §6: every FieldMap@foreginColumnName (vendor spelling) must be a
    field of the detail's own Page (ColumnPresentation@fieldName set)."""
    page_el = detail_el.find("Page")
    if page_el is None:
        return False
    fields = {
        cp.get("fieldName", "")
        for cp in page_el.findall("ColumnPresentations/ColumnPresentation")
    }
    fmaps = detail_el.findall("MasterForeignKeyColumnMap/FieldMap")
    if not fmaps:
        return False
    return all(fm.get("foreginColumnName", "") in fields for fm in fmaps)


def _walk_details(page_el) -> tuple[DetailNode, ...]:
    nodes: list[DetailNode] = []
    for detail_el in page_el.findall("Details/Detail"):
        if not _fk_valid(detail_el):
            continue  # vendor silently drops the whole subtree (MDA §6)
        child_page = detail_el.find("Page")
        nodes.append(
            DetailNode(
                table_name=child_page.get("tableName", ""),
                records_per_page=child_page.get("recordsPerPage", ""),
                element=child_page,
                children=_walk_details(child_page),
            )
        )
    return tuple(nodes)


def detail_tree(pgtp: Path, page: PageInfo) -> tuple[DetailNode, ...]:
    """Emitted (FK-valid) detail roots of a top-level page, document order."""
    from re_phpgen.config import parse_pgtp

    tree = parse_pgtp(pgtp)
    for el in tree.findall("Presentation/Pages/Page"):
        if el.get("fileName", "") == page.file_name:
            return _walk_details(el)
    return ()
```

(Match the module's import style — `dataclass` is already imported. If `catalog.py` uses `etree.parse` instead of `parse_pgtp`, keep consistency with what the file currently does.)

- [ ] **Step 4: Run → PASS**, then full suite `.\venv\Scripts\pytest -q -m "not oracle"` green (report count; baseline is 48).

- [ ] **Step 5: Commit:** `git add -A; git commit -m "feat: detail-tree walker with FK-validity emission filter"`

---

### Task 2: Class plans — post-order + ancestry naming + file-global ordinals (`skeleton.py`)

**Files:**
- Modify: `src/re_phpgen/skeleton.py`
- Test: `tests/test_skeleton.py` (extend)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_skeleton.py`):

```python
from re_phpgen.catalog import top_level_pages
from re_phpgen.skeleton import class_plans_for_page
from tests._md_fixtures import MD_XML


def _md(tmp_path, xml=MD_XML, name="md.pgtp"):
    pgtp = tmp_path / name
    pgtp.write_bytes(xml)
    return pgtp, top_level_pages(pgtp)[0]


def test_class_plans_postorder_names_and_extends(tmp_path):
    pgtp, master = _md(tmp_path)
    plans = class_plans_for_page(pgtp, master)
    assert [(p.stem, p.extends, p.has_children) for p in plans] == [
        ("s_master_s_child_a_s_grand", "DetailPage", False),
        ("s_master_s_child_a", "DetailPage", True),
        ("s_master_s_child_b", "DetailPage", False),
        ("s_master", "Page", True),
    ]


def test_class_plans_plain_page_single_master(tmp_path):
    xml = b'<Project><Presentation><Pages><Page fileName="p" tableName="s.p" type="grid"/></Pages></Presentation></Project>'
    pgtp, master = _md(tmp_path, xml, "plain.pgtp")
    plans = class_plans_for_page(pgtp, master)
    assert [(p.stem, p.extends, p.has_children) for p in plans] == [("s_p", "Page", False)]


def test_duplicate_full_stems_get_emission_order_ordinals(tmp_path):
    # Two sibling details on the SAME table -> second gets '01' (MDA §2).
    xml = MD_XML.replace(b'tableName="s.child_b"', b'tableName="s.child_a"')
    pgtp, master = _md(tmp_path, xml, "dup.pgtp")
    stems = [p.stem for p in class_plans_for_page(pgtp, master)]
    assert "s_master_s_child_a" in stems and "s_master_s_child_a01" in stems
    # emission (post-order) order decides which is unsuffixed:
    assert stems.index("s_master_s_child_a") < stems.index("s_master_s_child_a01")
```

- [ ] **Step 2: Run → FAIL** (ImportError `class_plans_for_page`).

- [ ] **Step 3: Implement** (append to `src/re_phpgen/skeleton.py`):

```python
from dataclasses import dataclass

from re_phpgen.catalog import DetailNode, detail_tree


@dataclass(frozen=True)
class ClassPlan:
    """One class to emit into a page file, in emission order."""
    stem: str                      # class name minus 'Page'
    extends: str                   # "Page" | "DetailPage"
    element: object                # lxml Page element (master or nested detail)
    has_children: bool             # -> CreateMasterDetailRecordGrid block
    ancestry_tables: tuple[str, ...]  # raw tableNames master..self (dotted-permission source)


def class_plans_for_page(pgtp: Path, page: PageInfo) -> list[ClassPlan]:
    """Post-order detail classes then the master, named per MDA §1-§2:
    stem = master stem + '_' + '_'.join(sanitized ancestry tableNames);
    duplicate full stems get 2-digit ordinals in emission order (file-global)."""
    master_stem = class_name_index(pgtp)[page.file_name]
    seen: dict[str, int] = {}

    def unique(stem: str) -> str:
        n = seen.get(stem, 0)
        seen[stem] = n + 1
        return stem if n == 0 else f"{stem}{n:02d}"

    plans: list[ClassPlan] = []

    def emit(node: DetailNode, prefix: str, tables: tuple[str, ...]) -> None:
        stem_base = prefix + "_" + sanitize_table_name(node.table_name)
        ancestry = tables + (node.table_name,)
        for child in node.children:
            emit(child, stem_base, ancestry)
        plans.append(
            ClassPlan(
                stem=unique(stem_base),
                extends="DetailPage",
                element=node.element,
                has_children=bool(node.children),
                ancestry_tables=ancestry,
            )
        )

    roots = detail_tree(pgtp, page)
    for root in roots:
        emit(root, master_stem, (page.table_name,))

    # master last; its own stem participates in the ordinal namespace too
    tree = parse_pgtp(pgtp)
    master_el = next(
        el for el in tree.findall("Presentation/Pages/Page")
        if el.get("fileName", "") == page.file_name
    )
    plans.append(
        ClassPlan(
            stem=unique(master_stem),
            extends="Page",
            element=master_el,
            has_children=bool(roots),
            ancestry_tables=(page.table_name,),
        )
    )
    return plans
```

Note on the ordinal in `emit`: MDA §2 says ordinals attach as the chain is BUILT for one known edge case (`adm_clients`, parked) — the model above (ordinal on the final stem, emission order) is the 471/479 rule; do not attempt the parked refinement.

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Corpus reproduction test** (append to `tests/test_skeleton.py`) — locks the 471/479 result:

```python
import re

import pytest

from re_phpgen.config import CORPUS_ROOT


DETAIL_DECL = re.compile(r"class (\w+)Page extends DetailPage")


def test_detail_class_lists_reproduce_vendor(corpus):
    """MDA: post-order + naming + FK filter reproduces >=471/479 pure pages;
    the residual (<=8 at analysis time) are the parked edge cases. The corpus
    grows, so assert a ratio, not absolute counts."""
    total = mismatches = 0
    for project in corpus:
        pgtp = CORPUS_ROOT / f"{project}.pgtp"
        for page in top_level_pages(pgtp):
            php = CORPUS_ROOT / project / f"{page.file_name}.php"
            if not php.is_file():
                continue
            text = php.read_text("utf-8", errors="replace")
            vendor_stems = DETAIL_DECL.findall(text)
            if "extends ViewBasedPage" in text or "extends CommonPage" in text:
                continue  # mixed pages out of scope
            plans = class_plans_for_page(pgtp, page)
            ours = [p.stem for p in plans if p.extends == "DetailPage"]
            if not vendor_stems and not ours:
                continue
            total += 1
            if ours != vendor_stems:
                mismatches += 1
    if total == 0:
        pytest.skip("no master-detail pages in corpus")
    assert mismatches / total <= 0.02, f"{mismatches}/{total} detail lists mismatch"
```

Run: `.\venv\Scripts\pytest tests/test_skeleton.py -q` — expect PASS with a mismatch count ≤8 at current corpus size. If the ratio fails, debug the model against MDA before proceeding (do not loosen the threshold).

- [ ] **Step 6: Full suite green, commit:** `git add -A; git commit -m "feat: class plans (post-order, ancestry naming, emission ordinals)"`

---

### Task 3: Derive the `GetEnable*` flag mapping + `CreatePageNavigator` variant predicate (corpus correlation)

This is a **derivation task**: the constants are unknown until the correlation runs; the deliverables are (a) the encoded rules in `skeleton.py`, (b) corpus-wide validation tests, (c) a findings appendix.

**Files:**
- Create: `work/derive_flag_rules.py` (scratch, gitignored)
- Modify: `src/re_phpgen/skeleton.py` (add `FLAG_RULES` + `flags_block`, `PNAV` predicate + `pnav_block`)
- Create: `tests/test_flag_rules.py`
- Modify: `docs/findings/master_detail_analysis.md` (appendix)

- [ ] **Step 1: Write the correlation script** (`work/derive_flag_rules.py`):

```python
"""Correlate page XML ability attributes with emitted GetEnable* flag lines and
CreatePageNavigator body variants, across every corpus page (top-level AND
detail classes; detail flags derive from the detail Page element).

Output: for each flag line observed in vendor PHP (e.g.
'public function GetEnableModalGridInsert() { return true; }'), the exact set
of (attribute, value) combinations of the owning Page element that co-occur
with presence vs absence. Prints a decision table; credentials elements never
read."""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from re_phpgen.catalog import detail_tree, top_level_pages
from re_phpgen.config import CORPUS_ROOT, corpus_projects, parse_pgtp

FLAG_RE = re.compile(r"function (GetEnable\w+)\(\)\s*{\s*return true;\s*}")
ABILITY_ATTRS = [
    "viewAbilityMode", "editAbilityMode", "insertAbilityMode", "copyAbilityMode",
    "multiEditAbility", "deleteSelectedAbilityMode", "inlineOperationsRequireConfirmation",
]

# For every (class in vendor php) x (owning XML Page element): record
# (attrs tuple) -> flag set, then print contradictions / clean mappings.
# The class->element pairing uses class_plans_for_page order vs the vendor
# class declaration order (Task 2 proved they align).
...
```

(The `...` body is the executor's to write — it is scratch tooling, not production code; the deliverable is the printed decision table. Pair classes to elements via `class_plans_for_page` and vendor declaration order; extract each class body with the brace matcher from `php_scanner.find_body_span` applied at class scope or a simple `class X extends` split; collect the flag sets and the `CreatePageNavigator` body shape (full `new PageNavigator('pnav', …)` vs simpler variant) per element attributes, including `recordsPerPage`.)

- [ ] **Step 2: Run and iterate until the mapping is clean:**

`.\venv\Scripts\python work/derive_flag_rules.py`

Success criterion: for each flag, a deterministic predicate over the owning Page element's attributes that reproduces presence/absence on ≥99% of classes, with the exceptions listed. Same for the pnav variant (hypotheses to test first: `recordsPerPage` value; `NavigatorPosition`; detail vs master). If a flag stays ambiguous, record the ambiguity + affected pages in the findings appendix and encode the majority rule (spec §6 fallback: manual GUI probe is user-opt-in later, never guess silently).

- [ ] **Step 3: Encode the result in `skeleton.py`** as data + two pure functions (exact predicates come from Step 2; the SHAPE is fixed):

```python
# Derived by work/derive_flag_rules.py from corpus correlation (findings appendix).
# Each rule: (flag method name, predicate over the owning Page element's attrib dict).
FLAG_RULES: list[tuple[str, "Callable[[dict[str, str]], bool]"]] = [
    # e.g. ("GetEnableModalGridInsert", lambda a: a.get("insertAbilityMode") == "3"),
    # ... filled from the derivation
]


def flags_block(page_attrib: dict[str, str]) -> str:
    """The GetEnable* one-liner block for a class, '' when no flag applies."""
    lines = [
        f"        public function {name}() {{ return true; }}"
        for name, pred in FLAG_RULES
        if pred(page_attrib)
    ]
    return "\n".join(lines)


def pnav_block(page_attrib: dict[str, str], extends: str) -> str:
    """CreatePageNavigator body per the derived variant predicate; the
    SetRowsPerPage(N) parameter comes from recordsPerPage."""
    # exact text from the derivation step; N = page_attrib.get("recordsPerPage", "20")
    ...
```

(The literal block texts come from the vendor skeletons captured in Step 2 — copy them exactly, indentation included; they must survive the masked comparison byte-identically.)

- [ ] **Step 4: Write the validation tests** (`tests/test_flag_rules.py`):

```python
import re

import pytest

from re_phpgen.catalog import top_level_pages
from re_phpgen.config import CORPUS_ROOT
from re_phpgen.skeleton import FLAG_RULES, class_plans_for_page, flags_block

FLAG_RE = re.compile(r"function (GetEnable\w+)\(\)\s*{\s*return true;\s*}")


def test_flag_rules_nonempty_and_wellformed():
    assert FLAG_RULES, "derivation must have produced at least one rule"
    for name, pred in FLAG_RULES:
        assert name.startswith("GetEnable") and callable(pred)


def test_flags_reproduce_vendor_corpus_wide(corpus):
    """For every pure page: our flags_block per class == vendor's flag set.
    Ratio assertion (corpus grows; derivation exceptions documented)."""
    total = wrong = 0
    for project in corpus:
        pgtp = CORPUS_ROOT / f"{project}.pgtp"
        for page in top_level_pages(pgtp):
            php = CORPUS_ROOT / project / f"{page.file_name}.php"
            if not php.is_file():
                continue
            text = php.read_text("utf-8", errors="replace")
            if "extends ViewBasedPage" in text or "extends CommonPage" in text:
                continue
            # split vendor text into class bodies in declaration order and
            # compare each class's vendor flag set to ours
            plans = class_plans_for_page(pgtp, page)
            vendor_classes = re.split(r"(?=    class \w+Page extends )", text)[1:]
            if len(vendor_classes) != len(plans):
                continue  # structural mismatch pages are Task 2/5's concern
            for plan, body in zip(plans, vendor_classes):
                total += 1
                ours = {n for n, p in FLAG_RULES if p(dict(plan.element.attrib))}
                if ours != set(FLAG_RE.findall(body)):
                    wrong += 1
    if total == 0:
        pytest.skip("corpus absent")
    assert wrong / total <= 0.01, f"{wrong}/{total} classes' flag sets mismatch"
```

- [ ] **Step 5: Findings appendix.** Append to `docs/findings/master_detail_analysis.md`: the derived decision table per flag (attribute, values, confidence, exceptions with page names), the pnav variant predicate + both literal body texts, and the exact reproduction numbers.

- [ ] **Step 6: Full suite green, commit:** `git add -A; git commit -m "feat: derived GetEnable*/pnav rules from corpus correlation (+ findings appendix)"`

---

### Task 4: Template decomposition (frame + class templates)

**Files:**
- Create: `templates/file_frame.php.tmpl`, `templates/page_class.php.tmpl`
- Modify: `src/re_phpgen/skeleton.py` (add `emit_frame`, `emit_class` — `emit_skeleton` + old template stay untouched until Task 6)
- Test: `tests/test_emit_page_file.py` (new; assembly-shape tests only in this task)

- [ ] **Step 1: Derive the two templates from the current one + a real project-09 page.** Split `templates/page_skeleton.php.tmpl` at the class boundary:
  - `file_frame.php.tmpl` = everything above `class @@SLOT:CLASS_NAME@@Page` + the footer from `try {` down. Insert `@@SLOT:GLOBAL_HANDLERS@@` at the exact position where the vendor emits `// OnGlobal… event handler` blocks (find it by diffing the masked skeleton of a project-09 plain page against a project-03 one — the beachhead gap analysis already showed it: the empty line after the `GetConnectionOptions` region). Insert `@@SLOT:CLASSES@@` where the class block was. Footer keeps the existing `@@SLOT:CLASS_NAME@@`/`@@SLOT:PAGE_NAME@@`/`@@SLOT:FILE_NAME@@`/`@@SLOT:TABLE_NAME@@`/`@@SLOT:ENCODING@@` slots (they refer to the MASTER).
  - `page_class.php.tmpl` = the class block, with `extends @@SLOT:EXTENDS@@`, the `GetEnable*` literals replaced by `@@SLOT:FLAGS@@`, the `CreatePageNavigator` body replaced by `@@SLOT:PNAV@@`, and `@@SLOT:CMDRG@@` inserted at the exact position `CreateMasterDetailRecordGrid` occupies in vendor master classes (locate via a real project-09 master-detail page's masked skeleton).
  Verification of positions is Task 5's parity gates; here just make the split.

- [ ] **Step 2: Failing assembly-shape tests** (`tests/test_emit_page_file.py`):

```python
from re_phpgen.skeleton import emit_class, emit_frame


def test_emit_class_fills_extends_and_conditionals():
    text = emit_class({
        "CLASS_NAME": "s_x", "EXTENDS": "DetailPage",
        "FLAGS": "        public function GetEnableModalGridInsert() { return true; }",
        "PNAV": "            return null;",
        "CMDRG": "",
        "TABLE_NAME": "s.x", "ENCODING": "UTF-8",
    } | _remaining_class_slots())
    assert "extends DetailPage" in text
    assert "GetEnableModalGridInsert" in text
    assert "CreateMasterDetailRecordGrid" not in text
    assert "@@SLOT:" not in text


def test_emit_frame_wraps_classes():
    text = emit_frame({
        "GLOBAL_HANDLERS": "",
        "CLASSES": "    class s_xPage extends Page\n    {\n    }",
        "CLASS_NAME": "s_x", "PAGE_NAME": "s_x", "FILE_NAME": "x",
        "TABLE_NAME": "s.x", "ENCODING": "UTF-8",
    })
    assert text.startswith("<?php")
    assert "class s_xPage" in text
    assert "GetApplication()->Run();" in text
    assert "@@SLOT:" not in text
```

(`_remaining_class_slots()` is a tiny test helper returning empty strings for whatever other slots the class template ended up with — write it against the real template's slot list, asserting the list explicitly so template/slot drift fails loudly.)

- [ ] **Step 3: Implement `emit_frame`/`emit_class`** in `skeleton.py` — same pattern as `emit_skeleton` but reading the two new template files (factor the shared fill logic into a private `_fill(template_path, slots)`).

- [ ] **Step 4: Run → PASS, full suite green, commit:** `git add -A; git commit -m "feat: file-frame + class templates with conditional slots"`

---

### Task 5: `emit_page_file` + parity gates (the heart of the slice)

**Files:**
- Modify: `src/re_phpgen/skeleton.py` (add `emit_page_file`, `_class_slots`, `_global_handlers_block`)
- Test: `tests/test_emit_page_file.py` (extend with the gates)

- [ ] **Step 1: Implement slot computation + assembly:**

```python
def _global_handlers_block(pgtp: Path) -> str:
    """Vendor injects '// On<Name> event handler' + the pasted code for each
    project-level global handler, into every page (MDA-confirmed on project 09;
    masked to @@HANDLER@@ on both sides at comparison time)."""
    tree = parse_pgtp(pgtp)
    blocks: list[str] = []
    handlers_el = tree.find("EventHandlers")
    if handlers_el is not None:
        for el in handlers_el:
            code = (el.text or "")
            if not code.strip():
                continue
            blocks.append(f"    // {el.tag} event handler\n{code}")
    return "\n".join(blocks)


def _class_slots(pgtp: Path, plan: ClassPlan) -> dict[str, str]:
    attrib = dict(plan.element.attrib)
    cmdrg = ""
    if plan.has_children:
        cmdrg = (
            "        function CreateMasterDetailRecordGrid()\n"
            "        {\n"
            "        }\n"
        )
    return {
        "CLASS_NAME": plan.stem,
        "EXTENDS": plan.extends,
        "FLAGS": flags_block(attrib),
        "PNAV": pnav_block(attrib, plan.extends),
        "CMDRG": cmdrg,
        "TABLE_NAME": ".".join(plan.ancestry_tables),
        "ENCODING": attrib.get("contentEncoding") or "UTF-8",
        # plus whatever further slots page_class.php.tmpl carries (Task 4's
        # explicit slot list) — each derived from attrib or plan, never hard-coded
    }


def emit_page_file(pgtp: Path, page: PageInfo) -> str:
    """Assemble the complete page .php: frame + post-order classes + master."""
    plans = class_plans_for_page(pgtp, page)
    classes = "\n".join(emit_class(_class_slots(pgtp, plan)) for plan in plans)
    master = plans[-1]
    return emit_frame({
        "GLOBAL_HANDLERS": _global_handlers_block(pgtp),
        "CLASSES": classes,
        "CLASS_NAME": master.stem,
        "PAGE_NAME": master.stem,
        "FILE_NAME": page.file_name,
        "TABLE_NAME": page.table_name,
        "ENCODING": _encoding_for(pgtp, page.file_name),
    })
```

Exact CMDRG body/indentation and inter-class separators must be tuned against the vendor files — that's what the gates below are for. Iterate with the first-diff-hunk debug pattern from `tests/test_parity.py` (`_report_first_hunk`): every fix must be a rule, not a page-specific patch.

- [ ] **Step 2: Parity gates** (append to `tests/test_emit_page_file.py`) — all use the standard symmetric masking and real corpus files, `pytest.skip` when absent:

```python
import pytest

from re_phpgen.catalog import detail_tree, top_level_pages
from re_phpgen.config import CORPUS_ROOT
from re_phpgen.handlers import handler_texts, mask_handler_code
from re_phpgen.masker import mask_method_bodies
from re_phpgen.normalizer import normalize
from re_phpgen.skeleton import emit_page_file


def _masked(text, htexts):
    return mask_method_bodies(mask_handler_code(normalize(text), htexts))


def _gate(project, file_name):
    pgtp = CORPUS_ROOT / f"{project}.pgtp"
    php = CORPUS_ROOT / project / f"{file_name}.php"
    if not pgtp.is_file() or not php.is_file():
        pytest.skip(f"corpus page {project}/{file_name} absent")
    htexts = handler_texts(pgtp)
    page = next(p for p in top_level_pages(pgtp) if p.file_name == file_name)
    ours = _masked(emit_page_file(pgtp, page), htexts)
    vendor = _masked(php.read_text("utf-8", errors="replace"), htexts)
    assert ours == vendor


# (a) regression: the beachhead project-03 pages still hold
def test_gate_03_plain_regression():
    _gate("03", "<the page test_parity.py::PAGE_FILE uses — read it and inline the name>")

# (b) project-09 plain page: global handler + flags slots
def test_gate_09_plain():
    _gate("09", "x_charcategory")

# (c) single-detail master-detail page — pick at runtime: the first project-09
# page whose detail_tree has exactly 1 root and no grandchildren and whose
# vendor php has no partition/chart/ViewBased markers; skip if none.
def test_gate_09_single_detail(): ...

# (d) deep/multi-detail page: >=3 details incl. one nested >=2 deep, same
# marker exclusions; skip if none.
def test_gate_09_deep_nested(): ...

# (e) FK-invalid degrades to plain: x_hseflag (MDA §6) — its emitted file must
# have NO DetailPage class and NO CreateMasterDetailRecordGrid, and reach parity.
def test_gate_fk_invalid_plain():
    _gate("01", "x_hseflag")
```

For (c)/(d) write the runtime page-picker exactly as commented (detail_tree + marker exclusion on the raw vendor text: `private $partitions`, `new Chart(`, `extends ViewBasedPage`, `extends CommonPage`, `extends NestedFormPage`) — deterministic first match in catalog order, `pytest.skip` if none qualifies. For (a) read `tests/test_parity.py` and inline its `PROJECT`/`PAGE_FILE` values; ALSO keep `test_parity.py` itself green until Task 6 retires the old path.

- [ ] **Step 3: Iterate to green.** This is the core reverse-engineering loop; expected friction points: exact blank-line counts between classes, the GLOBAL_HANDLERS insertion position, CMDRG indentation, per-class encoding vs master encoding. Debug protocol: first differing hunk → attribute to a rule (frame position? class template? slot text?) → fix the rule → rerun all gates + the corpus reproduction tests from Tasks 2–3.

- [ ] **Step 4: Full suite green, commit:** `git add -A; git commit -m "feat: emit_page_file — multi-class master-detail assembly at masked parity"`

---

### Task 6: Switch pangen over, retire the old template, measure

**Files:**
- Modify: `src/re_phpgen/pangen.py` (call `emit_page_file` instead of `emit_skeleton(slots_for_page(...))`)
- Modify: `tests/test_pangen.py` (assertions unchanged in spirit; the emitted file for a master-detail fixture now contains multiple classes)
- Modify: `tests/test_parity.py` (route through `emit_page_file`; the two existing gates must still pass)
- Delete: `templates/page_skeleton.php.tmpl`; remove `emit_skeleton`/`slots_for_page` if no caller remains (grep first)
- Modify: `docs/findings/master_detail_analysis.md` (coverage results)

- [ ] **Step 1: Switch `pangen.emit_project`:** replace `emit_skeleton(slots_for_page(pgtp, page))` with `emit_page_file(pgtp, page)`. Run `tests/test_pangen.py` — the existing tests must stay green (emit_project's contract is unchanged). Add one test: the MD fixture emits a file containing `extends DetailPage` and the post-order class names.

- [ ] **Step 2: Route `tests/test_parity.py` through `emit_page_file`** (replace the `emit_skeleton(slots_for_page(...))` call), run it green.

- [ ] **Step 3: Retire the old template** — grep for `page_skeleton.php.tmpl`, `emit_skeleton`, `slots_for_page` callers; delete the template and any now-dead functions + their dead tests. Full suite green.

- [ ] **Step 4: Measure and record.** Run `.\venv\Scripts\python scripts\skeleton_coverage.py` and `.\venv\Scripts\python -m re_phpgen analyze input\09.pgtp --vendor tests\_origen --ours <fresh pangen run> --json work\post_md_gap.json` (regenerate ours first with `python -m re_phpgen pangen input\09.pgtp --out work\post_md_pangen`; use `--ours work\post_md_pangen`). Append both numbers + the remaining cause histogram to the findings doc ("coverage after template-variants+master-detail slice: X/Y corpus, Z/99 project 09"). Expected region per spec: project 09 ~85/99; corpus in the hundreds. If dramatically below, the gates missed a systematic rule — investigate before declaring done.

- [ ] **Step 5: Commit:** `git add -A; git commit -m "feat: pangen emits via emit_page_file; retire fixed template; record coverage"`

---

## Verification (whole plan)

- `.\venv\Scripts\pytest -q -m "not oracle"` fully green in re_phpgen (report final count vs the 48 baseline).
- All five parity gates green; corpus reproduction tests (Task 2 detail lists, Task 3 flags) green at their thresholds.
- Coverage strictly improved and recorded; project-03 regression gates never broke.
- No editor changes needed (subprocess boundary); optionally re-run the editor's rePHPgen action afterwards to confirm the improved numbers flow through.

## Explicitly deferred

- `ViewBasedPage`/`NestedFormPage`/`CommonPage` class emission (mixed pages).
- Partition and chart template variants.
- The 8 parked edge pages (master-stem ordinal ×6, junction-detail drop ×1, mid-chain ordinal ×1) — each carries its documented disambiguation experiment in MDA.
- Any hole unmasking.
