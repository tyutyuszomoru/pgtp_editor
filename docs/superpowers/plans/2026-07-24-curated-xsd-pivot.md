# Curated-XSD Pivot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the hand-curated `curated.xsd` the single schema source (dialect: `label=`/`sums=`/`hint=`) feeding completion/hover/Properties, editable in a center-stage tab with Go To XSD and Verify/Export/Import — deleting the annotate popover, underlines, and git team sync.

**Architecture:** A new Qt-free expat-based parser (`schema_learning/xsd_load.py`) reads `curated.xsd` into the existing `Model.paths` shape with source-line maps, so the `settings_index` query API keeps its contracts (rewritten internally for the dialect: sums derivation, hint). Auto-learning is untouched except its output target (`learned.xsd`); it never feeds completion. The Edit XSD tab is a second `XmlEditor` + `FindReplaceBar` in the existing `CenterStage` QTabWidget with per-tab dirty/save/find routing in MainWindow.

**Tech Stack:** Python 3.12, PySide6, `xml.parsers.expat` (DTD-forbidden) for line-aware XSD parsing, pytest offscreen.

**Spec:** `docs/superpowers/CONSOLIDATED_SPEC.md` §11 "Schema: curated XSD, learning & completion" (plus §5/§7/§8/§10/§15/§22/§23 ripples), commit 600cca2.

## Global Constraints

- Test command (PowerShell): `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest <paths> -q` — system `python`, NOT the repo `venv\`.
- Every new `.py` file starts with the GPL header — copy lines 1–14 BYTE-IDENTICAL from `pgtp_editor/schema_learning/model.py`. Do not invent a different holder.
- Tests mirror the package layout; never let a test reach an un-patched modal Qt call (`QDialog.exec`, `QMessageBox.*`, `QFileDialog.*`).
- `schema_learning/*.py` modules are Qt-free (no QtWidgets/QtGui; `storage.py`'s QtCore `QStandardPaths` import is the only exception).
- **Suite must be green after every task** — deletions and semantics changes update their tests in the same task.
- Spec-pinned invariants: completion/hover/Properties come EXCLUSIVELY from `curated.xsd` (no learned fallback); `learned.xsd` overflowed attributes emit the plain non-enumerated form; malformed XSD save still writes the user's text and keeps the last good in-memory schema; Verify checks OUR dialect, not W3C validity.
- Commit per green task; `feat:`/`refactor:`/`test:` prefix; trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `pgtp_editor/schema_learning/storage.py` | Modify | + `curated_xsd_path()`, `learned_xsd_path()`; later −`schema_xsd_path`, −`team_repo_dir` |
| `pgtp_editor/schema_learning/model.py` | Modify | drop `"labels": {}` initialization (engine-owned fields only) |
| `pgtp_editor/schema_learning/xsd_gen.py` | Modify | + `generate_curated_xsd(model)` (label-attribute emit, bootstrap only) |
| `pgtp_editor/schema_learning/xsd_load.py` | Create | expat parser: curated XSD → `CuratedSchema(model, attribute_lines, element_lines)` |
| `pgtp_editor/schema_learning/xsd_verify.py` | Create | dialect verifier → `list[Issue]` |
| `pgtp_editor/schema_learning/settings_index.py` | Rewrite | dialect semantics: sums derivation, hint, no kind |
| `pgtp_editor/ui/center_stage.py` | Modify | + Edit XSD tab (2nd XmlEditor + FindReplaceBar) |
| `pgtp_editor/ui/xml_editor.py` | Modify | − underlines/annotate; + `goto_xsd_requested` + context entry |
| `pgtp_editor/ui/properties_panel.py` | Modify | + curated-label display |
| `pgtp_editor/ui/main_window.py` | Modify | feeding pipeline, tab routing, 4-item Schema menu, Go To XSD, Verify/Export/Import |
| DELETE | | `schema_learning/sync.py`, `schema_learning/merge.py`, `ui/annotate_popover.py`, `ui/team_sync_dialog.py`, `ui/merge_conflicts_dialog.py`, `ui/schema_viewer.py`, `ui/schema_viewer_data.py` + their tests |

---

### Task 1: Storage paths for the two XSD files

**Files:**
- Modify: `pgtp_editor/schema_learning/storage.py`
- Test: `tests/schema_learning/test_storage.py` (append)

**Interfaces:**
- Produces: `curated_xsd_path(base_dir=None) -> Path` → `<base>/curated.xsd`; `learned_xsd_path(base_dir=None) -> Path` → `<base>/learned.xsd`. (`schema_xsd_path` and `team_repo_dir` stay for now; removed in Tasks 7 and 2 respectively.)

- [ ] **Step 1: Failing tests** — append to `tests/schema_learning/test_storage.py`:

```python
def test_curated_and_learned_xsd_paths(tmp_path):
    from pgtp_editor.schema_learning.storage import curated_xsd_path, learned_xsd_path
    assert curated_xsd_path(tmp_path) == tmp_path / "curated.xsd"
    assert learned_xsd_path(tmp_path) == tmp_path / "learned.xsd"
```

- [ ] **Step 2: Run** `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\schema_learning\test_storage.py -q` — FAIL (ImportError).

- [ ] **Step 3: Implement** — add to `storage.py`:

```python
_CURATED_XSD_FILENAME = "curated.xsd"
_LEARNED_XSD_FILENAME = "learned.xsd"


def curated_xsd_path(base_dir: Path | None = None) -> Path:
    """The official, hand-curated schema (spec §11). Hand-edited only —
    never machine-written except the one-time bootstrap."""
    return (base_dir or _app_data_dir()) / _CURATED_XSD_FILENAME


def learned_xsd_path(base_dir: Path | None = None) -> Path:
    """The generated discovery artifact regenerated by auto-learning.
    Never feeds completion; never touches curated.xsd."""
    return (base_dir or _app_data_dir()) / _LEARNED_XSD_FILENAME
```

- [ ] **Step 4: Run** the same command — PASS.
- [ ] **Step 5: Commit** `feat: curated/learned XSD storage paths`

---

### Task 2: The big deletion — retire popover, underlines, team sync, viewers; placeholder Schema menu

**Files:**
- Delete: `pgtp_editor/schema_learning/sync.py`, `pgtp_editor/schema_learning/merge.py`, `pgtp_editor/ui/annotate_popover.py`, `pgtp_editor/ui/team_sync_dialog.py`, `pgtp_editor/ui/merge_conflicts_dialog.py`, `pgtp_editor/ui/schema_viewer.py`, `pgtp_editor/ui/schema_viewer_data.py`
- Delete tests: `tests/schema_learning/test_sync.py`, `tests/schema_learning/test_merge.py`, `tests/ui/test_annotate_popover.py`, `tests/ui/test_team_sync_dialog.py`, `tests/ui/test_merge_conflicts_dialog.py`, `tests/ui/test_schema_sync_wiring.py`, `tests/ui/test_annotate_wiring.py`, `tests/ui/test_schema_viewer.py`, `tests/ui/test_schema_viewer_data.py`, `tests/ui/test_main_window_schema_viewer.py`
- Modify: `pgtp_editor/ui/main_window.py`, `pgtp_editor/ui/xml_editor.py`, `pgtp_editor/schema_learning/storage.py` (−`team_repo_dir`, −`_TEAM_REPO_DIRNAME`), `tests/schema_learning/test_storage.py` (−its team_repo_dir test), `tests/ui/test_xml_editor_annotate.py` (trim), `tests/ui/test_menus.py`, `tests/ui/test_schema_menu_entry_point.py`

**Interfaces:**
- Produces: a Schema menu with EXACTLY four actions — "Edit XSD", "Verify XSD", "Export XSD", "Import XSD" — all wired to `self._not_implemented("<name>")` placeholders (rewired in Tasks 8–11). `_prepare_context_menu_at`, `attribute_value_at_position`, `attribute_at_position`, `enclosing_open_tag` are KEPT (later tasks depend on them).

- [ ] **Step 1: main_window.py surgery.** Remove:
  - imports: `AnnotatePopover`, `sync` module, `merge_models`/`apply_resolution`, `TeamSyncSettingsDialog`/`load_sync_config`, `MergeConflictsDialog`, `SchemaViewerWindow`, `open_xsd_text`/`open_labels_text`, `attribute_kind` (if only annotate used it).
  - state: `self._annotate_popover`, `self._xsd_viewer`, `self._labels_viewer` (and the "Read-only schema viewer windows" comment block), the `annotate_value_requested` connection.
  - methods: `_annotate_value_at_cursor`, `_goto_next_unlabeled_value`, `_open_annotate_popover`, `_apply_annotation`, `_open_xsd_viewer`, `_open_labels_viewer`, `_sync_config`, `_open_team_sync_settings`, `_publish_my_annotations`, `_on_publish_done`, `_on_sync_error`, `_fetch_team_master`, `_on_master_fetched`, `_merge_team_models`, `_on_team_models_loaded`, `_on_master_pushed`, and the module-level provenance helpers `_labeler_keys`, `_labeler_value`, `_merge_user_model_with_provenance`.
  - Replace `_build_schema_menu` with:

```python
    def _build_schema_menu(self):
        menu = self.menuBar().addMenu("Schema")
        edit_action = menu.addAction("Edit XSD")
        edit_action.triggered.connect(lambda: self._not_implemented("Edit XSD"))
        verify_action = menu.addAction("Verify XSD")
        verify_action.triggered.connect(lambda: self._not_implemented("Verify XSD"))
        export_action = menu.addAction("Export XSD")
        export_action.triggered.connect(lambda: self._not_implemented("Export XSD"))
        import_action = menu.addAction("Import XSD")
        import_action.triggered.connect(lambda: self._not_implemented("Import XSD"))
```

- [ ] **Step 2: xml_editor.py surgery.** Remove: `unlabeled_value_spans` (module function), `_unlabeled_value_selections`/`_unlabeled_underline_color` state + both `apply_theme_colors` assignments + its refresh call there, the `textChanged.connect(self._refresh_unlabeled_value_selections)` connection, `_refresh_unlabeled_value_selections`, its extend in `_refresh_extra_selections`, `goto_next_unlabeled_value`, `annotate_value_requested` signal, `request_annotate_at_cursor`, `schema_model()` accessor stays (harmless, used by tests) — actually KEEP `schema_model()`. Remove the context-menu "Annotate value…" block. Remove now-unused imports (`is_enum_candidate`, `attribute_kind`, `effective_labels` from settings_index; `QTextCharFormat` if unused elsewhere — check first).

- [ ] **Step 3: Trim `tests/ui/test_xml_editor_annotate.py`.** KEEP: all `attribute_value_at_position`/`attribute_at_position` resolver tests, the `_prepare_context_menu_at` caret-targeting + selection-preservation tests, the `_entry`/`_model` helpers (used by kept tests — adjust if a kept test used deleted functions). DELETE: underline tests, `goto_next_unlabeled_value` tests, `request_annotate_at_cursor`/annotate-context-menu tests, read-only annotate test, derived-label-counts-as-labeled underline test. The caret-targeting test asserted "Annotate value…" appears for value b — rewrite that assertion to use `request := attribute_value_at_position(editor.toPlainText(), editor.textCursor().position())` returning `("Root", "b", "2")` after `_prepare_context_menu_at`, dropping the menu-content check.

- [ ] **Step 4: Delete files** (`git rm` the seven modules + ten test files), remove `team_repo_dir`/`_TEAM_REPO_DIRNAME` from storage.py and its test. Update `tests/ui/test_menus.py` and `tests/ui/test_schema_menu_entry_point.py` to assert the Schema menu contains exactly `["Edit XSD", "Verify XSD", "Export XSD", "Import XSD"]` (use the existing `find_top_menu`/`action_labels` helpers from `tests/ui/_menu_helpers.py`).

- [ ] **Step 5: Verify no stragglers**

Run: `git grep -nE "AnnotatePopover|team_sync|merge_conflicts|SchemaViewerWindow|schema_viewer_data|unlabeled_value_spans|goto_next_unlabeled|annotate_value_requested|team_repo_dir|from pgtp_editor.schema_learning import sync|schema_learning.merge" -- "pgtp_editor" "tests"`
Expected: no hits.

- [ ] **Step 6: Full suite**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`
Expected: PASS (count drops by the deleted test files' tests). Completion/hover still work — they are still fed by the enrichment model until Task 7.

- [ ] **Step 7: Commit** `refactor: delete annotate popover, underlines, team sync, schema viewers`

---

### Task 3: Engine model sheds labeler fields

**Files:**
- Modify: `pgtp_editor/schema_learning/model.py:69-85` (both new-entry dicts), `tests/schema_learning/test_model.py` (expectations)

**Interfaces:**
- Produces: engine-created attribute entries are exactly `{type, values, overflowed, attr_seen_count}` — no `labels` key. All readers already use `.get("labels")` (verify: `xsd_gen.py`, `settings_index.py`).

- [ ] **Step 1: Failing test** — append to `tests/schema_learning/test_model.py`:

```python
def test_new_attribute_entries_carry_engine_fields_only():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    entry = model.paths["Root"]["attributes"]["a"]
    assert set(entry) == {"type", "values", "overflowed", "attr_seen_count"}
```

- [ ] **Step 2: Run** `tests\schema_learning\test_model.py` — FAIL (labels key present).
- [ ] **Step 3: Implement** — delete the `"labels": {},` line from BOTH new-entry dicts in `merge_element` (the secret-name branch and the normal branch). Fix any existing model tests asserting the `labels` key.
- [ ] **Step 4: Run** `tests\schema_learning\ -q` — PASS (settings_index/xsd_gen tests still pass because they build entries explicitly or use `.get`; fix any that assert `labels` on engine-created entries).
- [ ] **Step 5: Commit** `refactor: engine model entries carry engine-owned fields only`

---

### Task 4: `generate_curated_xsd` — bootstrap emit mode

**Files:**
- Modify: `pgtp_editor/schema_learning/xsd_gen.py`
- Test: `tests/schema_learning/test_xsd_gen.py` (append)

**Interfaces:**
- Consumes: `effective_labels` still exists at this point (old bitflag version — fine for bootstrap: old models carry explicit `labels`; after Task 6's rewrite, `effective_labels(entry)` without `sums` returns the explicit dict, same result).
- Produces: `generate_curated_xsd(model) -> str` — identical structure to `generate_xsd` but enumerations carry `label="…"` ATTRIBUTES (no `xs:annotation`/`xs:documentation`), used only by the one-time bootstrap.

- [ ] **Step 1: Failing test:**

```python
def test_generate_curated_xsd_emits_label_attributes():
    entry = {
        "type": "integer", "values": ["0", "1"], "overflowed": False,
        "attr_seen_count": 1, "labels": {"1": "php-psql"},
    }
    model = Model()
    model.paths = {"Root": {
        "attributes": {"phpDriver": entry}, "children": {},
        "instance_count": 1, "order": [], "order_stable": True, "has_text": False,
    }}
    xsd = generate_curated_xsd(model)
    assert '<xs:enumeration value="0"/>' in xsd
    assert '<xs:enumeration value="1" label="php-psql"/>' in xsd
    assert "xs:documentation" not in xsd


def test_generate_curated_xsd_overflowed_stays_plain():
    entry = {"type": "string", "values": None, "overflowed": True,
             "attr_seen_count": 1, "labels": {"x": "y"}}
    model = Model()
    model.paths = {"Root": {
        "attributes": {"a": entry}, "children": {},
        "instance_count": 1, "order": [], "order_stable": True, "has_text": False,
    }}
    xsd = generate_curated_xsd(model)
    assert "<xs:restriction" not in xsd
```

- [ ] **Step 2: Run** — FAIL (ImportError).
- [ ] **Step 3: Implement** — in `xsd_gen.py` add a parallel generator (mirror `generate_xsd`/`_complex_type_lines` with an `attribute_lines_fn` parameter to avoid duplicating the type walk):

```python
def generate_xsd(model):
    return _generate(model, _attribute_lines)


def generate_curated_xsd(model):
    """Bootstrap emit mode (spec §11): labels ride as label="…" attributes on
    xs:enumeration — our curated dialect — instead of xs:documentation. Used
    exactly once, to seed curated.xsd from the learned model."""
    return _generate(model, _curated_attribute_lines)


def _generate(model, attribute_lines_fn):
    # ... body of the old generate_xsd, with _complex_type_lines(path, entry, attribute_lines_fn)
    # and _complex_type_lines calling attribute_lines_fn(entry, attr_name) instead of _attribute_lines.


def _curated_attribute_lines(entry, attr_name):
    attr_entry = entry["attributes"][attr_name]
    required = attr_entry["attr_seen_count"] == entry["instance_count"]
    use = "required" if required else "optional"
    base_type = _XSD_BASE[attr_entry["type"]]
    universe = sorted(
        set(attr_entry.get("values") or []) | set(attr_entry.get("labels") or {})
    )
    if not attr_entry["overflowed"] and universe:
        labels = effective_labels(attr_entry)
        lines = [f"    <xs:attribute name={quoteattr(attr_name)} use={quoteattr(use)}>"]
        lines.append("      <xs:simpleType>")
        lines.append(f"        <xs:restriction base={quoteattr(base_type)}>")
        for value in universe:
            label = labels.get(value)
            if label:
                lines.append(
                    f"          <xs:enumeration value={quoteattr(value)} "
                    f"label={quoteattr(label)}/>"
                )
            else:
                lines.append(f"          <xs:enumeration value={quoteattr(value)}/>")
        lines.append("        </xs:restriction>")
        lines.append("      </xs:simpleType>")
        lines.append("    </xs:attribute>")
        return lines
    return [
        f"    <xs:attribute name={quoteattr(attr_name)} type={quoteattr(base_type)} "
        f"use={quoteattr(use)}/>"
    ]
```

Refactor `generate_xsd`'s existing body into `_generate` exactly (no behavior change — existing tests guard it).

- [ ] **Step 4: Run** `tests\schema_learning\test_xsd_gen.py -q` then `tests\schema_learning\ -q` — PASS.
- [ ] **Step 5: Commit** `feat: generate_curated_xsd bootstrap emit mode (label attributes)`

---

### Task 5: `xsd_load.py` — curated XSD → Model + line maps

**Files:**
- Create: `pgtp_editor/schema_learning/xsd_load.py`
- Test: `tests/schema_learning/test_xsd_load.py`

**Interfaces:**
- Produces (Tasks 7–10, 12–13 depend on these):
  - `class XsdLoadError(Exception)` — message includes `line N`.
  - `@dataclass CuratedSchema: model: Model; attribute_lines: dict[tuple[str, str], int]; element_lines: dict[str, int]` — keys are `(chain, attr)` / `chain` (slash-joined), values 1-based source lines.
  - `load_curated(text: str) -> CuratedSchema`.
  - Attribute entries in `model.paths[chain]["attributes"][attr]`: `{type: "boolean"|"integer"|"decimal"|"string", values: list[str], overflowed: False, attr_seen_count: 1, labels: dict[str,str], use: "optional"|"required", [sums: True], [hint: str]}`.

- [ ] **Step 1: Failing tests** — create `tests/schema_learning/test_xsd_load.py` (GPL header):

```python
import pytest

from pgtp_editor.schema_learning.xsd_load import CuratedSchema, XsdLoadError, load_curated

_XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" elementFormDefault="qualified">
  <xs:element name="Root" type="Root_Type"/>
  <xs:complexType name="Root_Type">
    <xs:sequence>
      <xs:element name="Item" type="Root_Item_Type" minOccurs="0" maxOccurs="1"/>
    </xs:sequence>
    <xs:attribute name="localizationFileName" use="required" hint="Path to localization file" type="xs:string"/>
  </xs:complexType>
  <xs:complexType name="Root_Item_Type">
    <xs:attribute name="phpDriver" use="optional">
      <xs:simpleType>
        <xs:restriction base="xs:integer">
          <xs:enumeration value="0" label="pdo"/>
          <xs:enumeration value="1" label="php-psql"/>
        </xs:restriction>
      </xs:simpleType>
    </xs:attribute>
    <xs:attribute name="printProperties" use="optional" sums="true">
      <xs:simpleType>
        <xs:restriction base="xs:integer">
          <xs:enumeration value="1" label="A"/>
          <xs:enumeration value="2" label="B"/>
        </xs:restriction>
      </xs:simpleType>
    </xs:attribute>
  </xs:complexType>
</xs:schema>
"""


def test_parses_chains_attributes_labels():
    schema = load_curated(_XSD)
    assert set(schema.model.paths) == {"Root", "Root/Item"}
    php = schema.model.paths["Root/Item"]["attributes"]["phpDriver"]
    assert php["type"] == "integer"
    assert php["values"] == ["0", "1"]
    assert php["labels"] == {"0": "pdo", "1": "php-psql"}
    assert "sums" not in php
    loc = schema.model.paths["Root"]["attributes"]["localizationFileName"]
    assert loc["hint"] == "Path to localization file"
    assert loc["values"] == []
    assert loc["use"] == "required"


def test_sums_flag_and_line_maps():
    schema = load_curated(_XSD)
    pp = schema.model.paths["Root/Item"]["attributes"]["printProperties"]
    assert pp["sums"] is True
    # line maps: the xs:attribute lines and complexType lines (1-based)
    assert schema.attribute_lines[("Root/Item", "phpDriver")] == 12
    assert schema.element_lines["Root/Item"] == 11
    assert ("Root", "localizationFileName") in schema.attribute_lines


def test_malformed_xml_raises_with_line():
    with pytest.raises(XsdLoadError) as excinfo:
        load_curated("<xs:schema><oops</xs:schema>")
    assert "line" in str(excinfo.value)


def test_dtd_is_refused():
    with pytest.raises(XsdLoadError):
        load_curated('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><xs:schema/>')


def test_type_cycle_does_not_hang():
    cyclic = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="A" type="A_Type"/>
  <xs:complexType name="A_Type">
    <xs:sequence><xs:element name="A" type="A_Type"/></xs:sequence>
  </xs:complexType>
</xs:schema>"""
    schema = load_curated(cyclic)
    assert "A" in schema.model.paths
```

(Verify the two line-number assertions against the literal `_XSD` string — count lines; adjust the expected integers to the actual layout, they must be exact.)

- [ ] **Step 2: Run** — FAIL (ModuleNotFoundError).
- [ ] **Step 3: Implement** — create `pgtp_editor/schema_learning/xsd_load.py` (GPL header, then):

```python
"""Parse the hand-curated XSD (our dialect: label=/sums=/hint=) into the
in-memory Model shape that settings_index and the editor consume, plus
source-line maps for Go To XSD.

Streaming expat parser (DTDs forbidden — same defensive posture as
defusedxml) so every xs:attribute / xs:complexType records its 1-based
source line. Unknown structures are ignored; Verify (xsd_verify.py) is the
place that complains about dialect violations, not this loader.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from xml.parsers import expat

from .model import Model

_XSD_TO_SCALAR = {
    "xs:boolean": "boolean",
    "xs:integer": "integer",
    "xs:decimal": "decimal",
    "xs:string": "string",
}


class XsdLoadError(Exception):
    pass


@dataclass
class CuratedSchema:
    model: Model
    attribute_lines: dict[tuple[str, str], int] = field(default_factory=dict)
    element_lines: dict[str, int] = field(default_factory=dict)


def _local(tag: str) -> str:
    """'xs:attribute' -> 'attribute' (prefix-agnostic — the user may use any
    namespace prefix in their curated file)."""
    return tag.rsplit(":", 1)[-1]


class _Collector:
    def __init__(self, parser):
        self._parser = parser
        self.roots: list[tuple[str, str]] = []   # (element name, type name)
        self.types: dict[str, dict] = {}          # type name -> record
        self._stack: list[str] = []               # local names
        self._current_type: dict | None = None
        self._current_attr: dict | None = None

    def start(self, tag, attrs):
        local = _local(tag)
        parent = self._stack[-1] if self._stack else None
        self._stack.append(local)
        line = self._parser.CurrentLineNumber
        if local == "complexType" and attrs.get("name"):
            self._current_type = {
                "line": line, "children": [], "attributes": {},
            }
            self.types[attrs["name"]] = self._current_type
        elif local == "element":
            name, type_name = attrs.get("name"), attrs.get("type")
            if name and type_name:
                if parent == "schema":
                    self.roots.append((name, type_name))
                elif self._current_type is not None:
                    self._current_type["children"].append((name, type_name))
        elif local == "attribute" and self._current_type is not None:
            self._current_attr = {
                "name": attrs.get("name", ""),
                "line": line,
                "use": attrs.get("use", "optional"),
                "sums": attrs.get("sums") == "true",
                "hint": attrs.get("hint"),
                "base": attrs.get("type"),
                "values": [],
                "labels": {},
            }
        elif local == "restriction" and self._current_attr is not None:
            self._current_attr["base"] = attrs.get("base")
        elif local == "enumeration" and self._current_attr is not None:
            value = attrs.get("value", "")
            self._current_attr["values"].append(value)
            label = attrs.get("label")
            if label is not None:
                self._current_attr["labels"][value] = label

    def end(self, tag):
        local = _local(tag)
        self._stack.pop()
        if local == "attribute" and self._current_attr is not None:
            attr = self._current_attr
            if attr["name"] and self._current_type is not None:
                self._current_type["attributes"][attr["name"]] = attr
            self._current_attr = None
        elif local == "complexType":
            self._current_type = None


def _forbid_dtd(*_args):
    raise XsdLoadError("DTD declarations are not allowed in the curated XSD")


def load_curated(text: str) -> CuratedSchema:
    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = _forbid_dtd
    collector = _Collector(parser)
    parser.StartElementHandler = collector.start
    parser.EndElementHandler = collector.end
    try:
        parser.Parse(text, True)
    except expat.ExpatError as exc:
        raise XsdLoadError(
            f"line {exc.lineno}: {expat.errors.messages[exc.code]}"
        ) from exc

    schema = CuratedSchema(model=Model())
    for root_name, root_type in collector.roots:
        _walk(schema, collector.types, root_name, root_type, "", set())
    return schema


def _walk(schema, types, tag, type_name, parent_chain, stack):
    record = types.get(type_name)
    if record is None or type_name in stack:
        return
    chain = f"{parent_chain}/{tag}" if parent_chain else tag
    schema.element_lines[chain] = record["line"]
    entry, _is_new = schema.model._get_or_create_path(chain)
    for attr_name, attr in record["attributes"].items():
        model_entry = {
            "type": _XSD_TO_SCALAR.get(attr["base"], "string"),
            "values": list(attr["values"]),
            "overflowed": False,
            "attr_seen_count": 1,
            "labels": dict(attr["labels"]),
            "use": attr["use"],
        }
        if attr["sums"]:
            model_entry["sums"] = True
        if attr["hint"]:
            model_entry["hint"] = attr["hint"]
        entry["attributes"][attr_name] = model_entry
        schema.attribute_lines[(chain, attr_name)] = attr["line"]
    for child_tag, child_type in record["children"]:
        _walk(schema, types, child_tag, child_type, chain, stack | {type_name})
```

- [ ] **Step 4: Run** `tests\schema_learning\test_xsd_load.py -q` — PASS.
- [ ] **Step 5: Commit** `feat: xsd_load — curated XSD parser with line maps`

---

### Task 6: `settings_index` rewrite — dialect semantics (sums / hint / no kind)

**Files:**
- Rewrite: `pgtp_editor/schema_learning/settings_index.py`
- Rewrite: `tests/schema_learning/test_settings_index.py`
- Modify: `tests/ui/test_xml_editor_completion.py`, `tests/ui/test_xml_editor_hover.py`, `tests/ui/test_xml_editor_add_attribute.py` (entry-shape fixtures + expectations)

**Interfaces:**
- Consumers keep working: `xml_editor.py` imports `known_attributes`, `known_values`, `enum_hint`, `unused_setting_attributes` — signatures unchanged. `xsd_gen.py` imports `effective_labels` — keep a function of that name with the same one-arg signature.
- Produces:
  - `derived_sums_labels(entry) -> dict[str, str]` — all 2^n−1 combination labels from numerically-parsed labeled atomic values, '+'-joined ascending; explicit labels overlaid last.
  - `effective_labels(entry) -> dict[str, str]` — explicit labels; when `entry.get("sums")` → `derived_sums_labels`.
  - `known_values(model, chain, attr) -> list[tuple[str, str | None]]` — `[]` for unknown attr or `hint` attributes; for `sums`: every derived combination; else the enumeration values; sorted numerically when values parse as int, else lexically.
  - `enum_hint(model, chain, attr) -> str | None` — `hint` attribute → `f"{attr} — {hint}"`; else built from `known_values`; None when neither.
  - `value_label(model, chain, attr, value) -> str | None` (new — Task 12 Properties).
  - `known_attributes(model, chain, present)` and `unused_setting_attributes(model, chain, present)` — identical: every attribute the curated schema knows at the chain minus present (kind filter is GONE; keep both names for the two call sites).
  - DELETED: `is_enum_candidate`, `attribute_kind`, `value_note`, `derived_bitflag_label`.

- [ ] **Step 1: Rewrite the test file** — `tests/schema_learning/test_settings_index.py` becomes (GPL header, then):

```python
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.settings_index import (
    derived_sums_labels,
    effective_labels,
    enum_hint,
    known_attributes,
    known_values,
    unused_setting_attributes,
    value_label,
)


def _entry(values, labels=None, **extra):
    entry = {
        "type": "integer",
        "values": values,
        "overflowed": False,
        "attr_seen_count": 1,
        "labels": labels or {},
        "use": "optional",
    }
    entry.update(extra)
    return entry


def _model(attrs, chain="Root"):
    model = Model()
    model.paths = {chain: {
        "attributes": attrs, "children": {}, "instance_count": 1,
        "order": [], "order_stable": True, "has_text": False,
    }}
    return model


def test_derived_sums_labels_all_combinations():
    entry = _entry(["1", "2", "4"], labels={"1": "A", "2": "B", "4": "C"}, sums=True)
    assert derived_sums_labels(entry) == {
        "1": "A", "2": "B", "4": "C",
        "3": "A+B", "5": "A+C", "6": "B+C", "7": "A+B+C",
    }


def test_derived_sums_explicit_row_overrides():
    entry = _entry(["1", "2", "3"], labels={"1": "A", "2": "B", "3": "both"}, sums=True)
    assert derived_sums_labels(entry)["3"] == "both"


def test_derived_sums_skips_unlabeled_and_non_numeric_atoms():
    entry = _entry(["1", "2", "x"], labels={"1": "A", "x": "odd"}, sums=True)
    result = derived_sums_labels(entry)
    assert result["1"] == "A"
    assert "3" not in result          # 2 unlabeled -> not an atom
    assert result["x"] == "odd"       # explicit non-numeric label survives


def test_known_values_sums_offers_all_combinations_numerically_sorted():
    model = _model({"pp": _entry(["1", "2", "4"], labels={"1": "A", "2": "B", "4": "C"}, sums=True)})
    values = known_values(model, "Root", "pp")
    assert values == [
        ("1", "A"), ("2", "B"), ("3", "A+B"), ("4", "C"),
        ("5", "A+C"), ("6", "B+C"), ("7", "A+B+C"),
    ]


def test_known_values_plain_and_hint():
    model = _model({
        "phpDriver": _entry(["0", "1"], labels={"0": "pdo", "1": "php-psql"}),
        "loc": _entry([], hint="Path to localization file"),
    })
    assert known_values(model, "Root", "phpDriver") == [("0", "pdo"), ("1", "php-psql")]
    assert known_values(model, "Root", "loc") == []
    assert known_values(model, "Root", "missing") == []


def test_enum_hint_variants():
    model = _model({
        "phpDriver": _entry(["0", "1"], labels={"0": "pdo", "1": "php-psql"}),
        "loc": _entry([], hint="Path to localization file"),
        "bare": _entry([]),
    })
    assert enum_hint(model, "Root", "phpDriver") == "phpDriver — 0 = pdo · 1 = php-psql"
    assert enum_hint(model, "Root", "loc") == "loc — Path to localization file"
    assert enum_hint(model, "Root", "bare") is None


def test_known_and_unused_attributes_no_kind_filter():
    model = _model({"a": _entry(["1"]), "b": _entry([])})
    assert known_attributes(model, "Root", {"a"}) == ["b"]
    assert unused_setting_attributes(model, "Root", {"a"}) == ["b"]
    assert known_attributes(model, "Nope", set()) == []


def test_value_label_uses_effective_labels():
    model = _model({"pp": _entry(["1", "2"], labels={"1": "A", "2": "B"}, sums=True)})
    assert value_label(model, "Root", "pp", "3") == "A+B"
    assert value_label(model, "Root", "pp", "9") is None
    assert value_label(model, "Root", "missing", "1") is None


def test_effective_labels_plain_is_copy():
    entry = _entry(["1"], labels={"1": "A"})
    result = effective_labels(entry)
    result["1"] = "mutated"
    assert entry["labels"]["1"] == "A"
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Rewrite** `settings_index.py` (GPL header + docstring describing the curated-dialect entry shape, then):

```python
def derived_sums_labels(entry):
    """All combination labels for a sums attribute. Atoms = the labeled,
    positive-integer enumeration values; every non-empty subset's sum gets a
    '+'-joined label in ascending atomic order. On duplicate sums the first
    (smallest-atoms) subset wins; explicit enumeration labels overlay LAST,
    so a hand-written composite row always wins (spec §11)."""
    labels = entry.get("labels") or {}
    atoms = []
    for value in entry.get("values") or []:
        label = labels.get(value)
        if label is None:
            continue
        try:
            number = int(value)
        except ValueError:
            continue
        if number > 0:
            atoms.append((number, label))
    atoms.sort()
    result = {}
    for mask in range(1, 1 << len(atoms)):
        total = 0
        parts = []
        for index, (number, label) in enumerate(atoms):
            if mask & (1 << index):
                total += number
                parts.append(label)
        result.setdefault(str(total), "+".join(parts))
    result.update(labels)
    return result


def effective_labels(entry):
    """The labels to display for an attribute entry: explicit labels, plus
    derived combination labels when the attribute is marked sums."""
    if entry.get("sums"):
        return derived_sums_labels(entry)
    return dict(entry.get("labels") or {})


def _value_sort_key(value):
    try:
        return (0, int(value), value)
    except ValueError:
        return (1, 0, value)


def known_values(model, tag_chain, attr):
    """Sorted ``(value, label)`` pairs for the value-completion popup.
    ``[]`` for an unknown attribute or a hint attribute (free-form — no
    value list, spec §11). For sums attributes the universe is every derived
    combination (2^n − 1 rows)."""
    entry = model.paths.get(tag_chain, {}).get("attributes", {}).get(attr)
    if entry is None or entry.get("hint"):
        return []
    labels = effective_labels(entry)
    universe = set(labels) if entry.get("sums") else set(entry.get("values") or [])
    if not universe:
        return []
    return [(v, labels.get(v)) for v in sorted(universe, key=_value_sort_key)]


def enum_hint(model, tag_chain, attr):
    """One-line hover hint: the hint text for free-form attributes, else the
    value = label list (derived sums labels included)."""
    entry = model.paths.get(tag_chain, {}).get("attributes", {}).get(attr)
    if entry is None:
        return None
    hint = entry.get("hint")
    if hint:
        return f"{attr} — {hint}"
    pairs = known_values(model, tag_chain, attr)
    if not pairs:
        return None
    parts = [f"{v} = {l}" if l else f"{v}" for v, l in pairs]
    return f"{attr} — " + " · ".join(parts)


def value_label(model, tag_chain, attr, value):
    """The display label for one concrete value, or None (Properties panel)."""
    entry = model.paths.get(tag_chain, {}).get("attributes", {}).get(attr)
    if entry is None:
        return None
    return effective_labels(entry).get(value)


def known_attributes(model, tag_chain, present_attrs):
    """Sorted attribute names the curated schema knows at ``tag_chain`` that
    the element does not already carry. An attribute is completion-worthy iff
    it exists in curated.xsd — there is no kind filter (spec §11)."""
    attributes = model.paths.get(tag_chain, {}).get("attributes", {})
    present = set(present_attrs)
    return sorted(name for name in attributes if name not in present)


def unused_setting_attributes(model, tag_chain, present_attrs):
    """Alias of known_attributes, kept for the Add-attribute submenu call
    site (the old kind filter is gone with the curated-XSD pivot)."""
    return known_attributes(model, tag_chain, present_attrs)
```

Delete `is_enum_candidate`, `attribute_kind`, `value_note`, `derived_bitflag_label` and the old bodies.

- [ ] **Step 4: Fix ripples.** `xsd_gen.py` still imports `effective_labels` — works (entries without `sums` → explicit dict). Old-era model entries in learned data have no `use` key — none of the new functions require it. Update `tests/ui/test_xml_editor_completion.py` / `test_xml_editor_hover.py` / `test_xml_editor_add_attribute.py`: entry fixtures using `kind="setting"`/`kind="content"` — remove kind kwargs; hover tests asserting kind-gated behavior (hint only for settings) now expect hints for ANY known attribute with values/hint; `known_values` overflow-union expectations replaced by the new semantics. `tests/schema_learning/test_xsd_gen.py` keeps passing (its entries carry explicit labels only).

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\schema_learning\ tests\ui\test_xml_editor_completion.py tests\ui\test_xml_editor_hover.py tests\ui\test_xml_editor_add_attribute.py -q` — PASS.

- [ ] **Step 5: Full suite** — PASS.
- [ ] **Step 6: Commit** `feat: settings_index rewritten for the curated-XSD dialect (sums/hint)`

---

### Task 7: Feeding pipeline — startup load, bootstrap, learned-only enrichment

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (`__init__` tail, `_enrich_schema_from_file`, imports), `pgtp_editor/schema_learning/storage.py` (−`schema_xsd_path`, −`_XSD_FILENAME`), `tests/schema_learning/test_storage.py`, `tests/ui/test_schema_learning_wiring.py`
- Test: `tests/ui/test_curated_feed_wiring.py` (create; reuse the MainWindow fixture pattern from `tests/ui/test_schema_learning_wiring.py`, fixture name `window`)

**Interfaces:**
- Consumes: `load_curated`/`XsdLoadError`/`CuratedSchema` (Task 5), `generate_curated_xsd` (Task 4), `curated_xsd_path`/`learned_xsd_path` (Task 1).
- Produces: `MainWindow._curated_schema: CuratedSchema | None`; `_load_curated_schema() -> bool` (parses file → `set_schema_model(schema.model)`, keeps last good on failure + `[Schema] Curated XSD has XML errors: … — keeping last good schema` audit line); `_ensure_curated_bootstrap()` (writes `generate_curated_xsd` when curated absent and model json present, audit line `[Schema] Bootstrapped curated.xsd from the learned schema`); enrichment writes `learned.xsd` only and NEVER calls `set_schema_model` with the learned model.

- [ ] **Step 1: Failing tests** — create `tests/ui/test_curated_feed_wiring.py` (GPL header; replicate the `window` fixture):

```python
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import (
    curated_xsd_path,
    learned_xsd_path,
    schema_model_path,
)

_CURATED = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Root" type="Root_Type"/>
  <xs:complexType name="Root_Type">
    <xs:attribute name="phpDriver" use="optional">
      <xs:simpleType><xs:restriction base="xs:integer">
        <xs:enumeration value="0" label="pdo"/>
      </xs:restriction></xs:simpleType>
    </xs:attribute>
  </xs:complexType>
</xs:schema>
"""


def _seed_curated(window):
    path = curated_xsd_path(window._schema_storage_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_CURATED, encoding="utf-8")


def test_load_curated_schema_feeds_editor(window):
    _seed_curated(window)
    assert window._load_curated_schema() is True
    model = window.center_stage.xml_editor.schema_model()
    assert model.paths["Root"]["attributes"]["phpDriver"]["labels"] == {"0": "pdo"}


def test_malformed_curated_keeps_last_good(window):
    _seed_curated(window)
    window._load_curated_schema()
    curated_xsd_path(window._schema_storage_dir).write_text("<broken", encoding="utf-8")
    assert window._load_curated_schema() is False
    model = window.center_stage.xml_editor.schema_model()
    assert model is not None  # last good schema stayed live
    items = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any("Curated XSD has XML errors" in line for line in items)


def test_bootstrap_seeds_curated_from_learned_model(window):
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model_path = schema_model_path(window._schema_storage_dir)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(model_path)
    window._ensure_curated_bootstrap()
    text = curated_xsd_path(window._schema_storage_dir).read_text(encoding="utf-8")
    assert "<xs:schema" in text and 'name="a"' in text
    # second call must not rewrite (hand-owned after bootstrap)
    curated_xsd_path(window._schema_storage_dir).write_text(text + "<!-- edited -->", encoding="utf-8")
    window._ensure_curated_bootstrap()
    assert curated_xsd_path(window._schema_storage_dir).read_text(encoding="utf-8").endswith("<!-- edited -->")


def test_enrichment_writes_learned_only_and_keeps_curated_feed(window, tmp_path):
    _seed_curated(window)
    window._load_curated_schema()
    sample = tmp_path / "sample.pgtp"
    sample.write_text('<PGTPProject><New thing="x"/></PGTPProject>', encoding="utf-8")
    window._enrich_schema_from_file(str(sample))
    assert learned_xsd_path(window._schema_storage_dir).exists()
    # completion feed still the curated model — learned attrs are NOT offered
    model = window.center_stage.xml_editor.schema_model()
    assert "PGTPProject/New" not in model.paths
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** in `main_window.py`:
  - imports: `from pgtp_editor.schema_learning.storage import curated_xsd_path, learned_xsd_path, schema_model_path` (drop `schema_xsd_path`), `from pgtp_editor.schema_learning.xsd_gen import generate_curated_xsd, generate_xsd`, `from pgtp_editor.schema_learning.xsd_load import XsdLoadError, load_curated`.
  - `__init__` (near the schema-storage setup): `self._curated_schema = None`, then AFTER the audit panel exists: `self._ensure_curated_bootstrap()`, `self._load_curated_schema()`.

```python
    def _load_curated_schema(self) -> bool:
        """Parse curated.xsd and feed completion/hover from it — the SOLE
        schema source (spec §11). On parse failure the last good in-memory
        schema stays live; returns False. Missing file → False, silent."""
        path = curated_xsd_path(self._schema_storage_dir)
        if not path.exists():
            return False
        try:
            schema = load_curated(path.read_text(encoding="utf-8"))
        except (OSError, XsdLoadError) as exc:
            self.audit_panel.addItem(
                f"[Schema] Curated XSD has XML errors: {exc} — keeping last good schema"
            )
            return False
        self._curated_schema = schema
        self.center_stage.xml_editor.set_schema_model(schema.model)
        return True

    def _ensure_curated_bootstrap(self) -> None:
        """One-time seed: if curated.xsd is absent but the learning engine
        has state, emit it (labels as label="…" attributes). Never runs when
        the file exists — curated.xsd is hand-owned (spec §11)."""
        curated = curated_xsd_path(self._schema_storage_dir)
        if curated.exists():
            return
        model_path = schema_model_path(self._schema_storage_dir)
        if not model_path.exists():
            return
        try:
            model = Model.load(model_path)
            curated.parent.mkdir(parents=True, exist_ok=True)
            curated.write_text(generate_curated_xsd(model), encoding="utf-8")
        except Exception as exc:
            self.audit_panel.addItem(f"[Schema] Could not bootstrap curated.xsd: {exc}")
            return
        self.audit_panel.addItem(
            "[Schema] Bootstrapped curated.xsd from the learned schema (labels preserved)"
        )
```

  - `_enrich_schema_from_file`: replace `xsd_path = schema_xsd_path(...)` with `learned_xsd_path(...)`; DELETE the `self.center_stage.xml_editor.set_schema_model(model)` line (and its comment); after the save/write, append:

```python
            self._ensure_curated_bootstrap()
            if self._curated_schema is None:
                self._load_curated_schema()
```

  - `storage.py`: delete `schema_xsd_path` + `_XSD_FILENAME`; fix its test. Update `tests/ui/test_schema_learning_wiring.py`: expectations that enrichment wrote `schema.xsd` → `learned.xsd`; any assertion that enrichment updates the editor's model → now asserts it does NOT (curated-only feed).

- [ ] **Step 4: Run** `tests\ui\test_curated_feed_wiring.py tests\ui\test_schema_learning_wiring.py tests\schema_learning\test_storage.py -q` — PASS; then full suite — PASS.
- [ ] **Step 5: Commit** `feat: curated.xsd feeds completion; enrichment writes learned.xsd only; bootstrap`

---

### Task 8: Edit XSD tab — center stage, dirty state, save & find routing

**Files:**
- Modify: `pgtp_editor/ui/center_stage.py`, `pgtp_editor/ui/main_window.py`
- Test: `tests/ui/test_edit_xsd_tab.py` (create; `window` fixture as before)

**Interfaces:**
- Consumes: `_load_curated_schema` (Task 7), `curated_xsd_path`.
- Produces:
  - `CenterStage.xsd_editor` (XmlEditor), `CenterStage.xsd_find_replace_bar` (FindReplaceBar), `CenterStage.xsd_tab_index`, `CenterStage.show_edit_xsd()`.
  - `MainWindow._open_edit_xsd()`, `_save_curated_xsd()`, `_set_xsd_dirty(bool)` (tab title "Edit XSD" / "Edit XSD *"), `_active_find_bar()`, save routing `_save_active_tab()` bound to Ctrl+S; `closeEvent` honors XSD dirty state. Verify auto-run hook point: `_save_curated_xsd` ends by calling `self._load_curated_schema()` (+ Task 10 will append verify).

- [ ] **Step 1: Failing tests** — create `tests/ui/test_edit_xsd_tab.py` (GPL header):

```python
from pgtp_editor.schema_learning.storage import curated_xsd_path

_MINIMAL = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Root" type="Root_Type"/>
  <xs:complexType name="Root_Type">
    <xs:attribute name="a" use="optional" type="xs:string"/>
  </xs:complexType>
</xs:schema>
"""


def _seed(window, text=_MINIMAL):
    path = curated_xsd_path(window._schema_storage_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_open_edit_xsd_loads_file_into_tab(window):
    _seed(window)
    window._open_edit_xsd()
    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index
    assert stage.tabText(stage.xsd_tab_index) == "Edit XSD"
    assert stage.xsd_editor.toPlainText() == _MINIMAL
    assert window._xsd_dirty is False


def test_editing_marks_dirty_and_save_reparses(window):
    path = _seed(window)
    window._open_edit_xsd()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_MINIMAL.replace('name="a"', 'name="b"'))
    # setPlainText fires textChanged -> dirty
    assert window._xsd_dirty is True
    assert stage.tabText(stage.xsd_tab_index) == "Edit XSD *"
    window._save_curated_xsd()
    assert window._xsd_dirty is False
    assert 'name="b"' in path.read_text(encoding="utf-8")
    model = stage.xml_editor.schema_model()
    assert "b" in model.paths["Root"]["attributes"]


def test_malformed_save_still_writes_and_keeps_last_good(window):
    path = _seed(window)
    window._open_edit_xsd()
    window._load_curated_schema()
    good_model = window.center_stage.xml_editor.schema_model()
    window.center_stage.xsd_editor.setPlainText("<broken")
    window._save_curated_xsd()
    assert path.read_text(encoding="utf-8") == "<broken"   # text never lost
    assert window.center_stage.xml_editor.schema_model() is good_model


def test_ctrl_s_routes_to_active_tab(window):
    _seed(window)
    window._open_edit_xsd()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    window._save_active_tab()
    assert window._xsd_dirty is False  # saved the XSD, not the project


def test_find_bar_routing(window):
    _seed(window)
    window._open_edit_xsd()
    assert window._active_find_bar() is window.center_stage.xsd_find_replace_bar
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)
    assert window._active_find_bar() is window.center_stage.find_replace_bar
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**

3a. `center_stage.py` — after the raw_xml_tab block, before the manual tab:

```python
        # Edit XSD tab (spec §11): a second, fully-featured editor for the
        # hand-curated schema. Hidden until Schema ▸ Edit XSD reveals it.
        self.xsd_editor = XmlEditor()
        self.xsd_find_replace_bar = FindReplaceBar(self.xsd_editor)
        self.xsd_tab = QWidget()
        xsd_layout = QVBoxLayout(self.xsd_tab)
        xsd_layout.setContentsMargins(0, 0, 0, 0)
        xsd_layout.setSpacing(0)
        xsd_layout.addWidget(self.xsd_editor)
        xsd_layout.addWidget(self.xsd_find_replace_bar)
        self.xsd_tab_index = self.addTab(self.xsd_tab, "Edit XSD")
```

and in the defaults block: `self.setTabVisible(self.xsd_tab_index, False)`. Add:

```python
    def show_edit_xsd(self):
        self.setTabVisible(self.xsd_tab_index, True)
        self.setCurrentIndex(self.xsd_tab_index)
```

(The close-button-stripping loop already excludes only the manual tab and runs over `self.count()` — the new tab is created before that loop, so it is covered.)

3b. `main_window.py`:
  - `__init__`: `self._xsd_dirty = False`, `self._xsd_loading = False`; connections:

```python
        stage = self.center_stage
        stage.xsd_editor.textChanged.connect(self._on_xsd_text_changed)
        # The XSD tab uses the editor's native undo (no snapshot history):
        # XmlEditor consumes Ctrl+Z/Ctrl+Y and re-emits; route them back.
        stage.xsd_editor.undo_requested.connect(stage.xsd_editor.undo)
        stage.xsd_editor.redo_requested.connect(stage.xsd_editor.redo)
        stage.xsd_find_replace_bar.set_on_status(self.statusBar().showMessage)
```

  - Methods:

```python
    def _on_xsd_text_changed(self) -> None:
        if self._xsd_loading:
            return
        self._set_xsd_dirty(True)

    def _set_xsd_dirty(self, dirty: bool) -> None:
        self._xsd_dirty = dirty
        stage = self.center_stage
        stage.setTabText(stage.xsd_tab_index, "Edit XSD *" if dirty else "Edit XSD")

    def _open_edit_xsd(self) -> None:
        """Schema ▸ Edit XSD: load curated.xsd into the XSD tab (unless the
        tab already holds unsaved edits) and switch to it."""
        stage = self.center_stage
        if not self._xsd_dirty:
            path = curated_xsd_path(self._schema_storage_dir)
            text = path.read_text(encoding="utf-8") if path.exists() else (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
                'elementFormDefault="qualified">\n</xs:schema>\n'
            )
            self._xsd_loading = True
            try:
                stage.xsd_editor.setPlainText(text)
            finally:
                self._xsd_loading = False
            self._set_xsd_dirty(False)
        stage.show_edit_xsd()

    def _save_curated_xsd(self) -> None:
        """Save the XSD tab. The text is ALWAYS written (user text is never
        lost); a malformed file keeps the last good schema live (spec §11)."""
        path = curated_xsd_path(self._schema_storage_dir)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                self.center_stage.xsd_editor.toPlainText(), encoding="utf-8", newline=""
            )
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save:\n\n{exc}")
            return
        self._set_xsd_dirty(False)
        self.statusBar().showMessage("Saved curated.xsd", 5000)
        self._load_curated_schema()

    def _save_active_tab(self) -> None:
        """Ctrl+S / File ▸ Save routes to the active center-stage tab."""
        stage = self.center_stage
        if stage.currentIndex() == stage.xsd_tab_index:
            self._save_curated_xsd()
        else:
            self._save_project()

    def _active_find_bar(self):
        """The FindReplaceBar of the active editor tab; defaults to the Raw
        XML bar (revealing that tab) when neither editor tab is active."""
        stage = self.center_stage
        if stage.currentIndex() == stage.xsd_tab_index:
            return stage.xsd_find_replace_bar
        self._reveal_raw_xml_tab()
        return stage.find_replace_bar
```

  - Rewire: the File ▸ Save action's `triggered` handler → `self._save_active_tab` (find the `save_action.setShortcut("Ctrl+S")` block). `_show_find_bar` → `self._active_find_bar().show_find()`; `_show_replace_bar` → `self._active_find_bar().show_replace()`; `_find_next` → `self._active_find_bar().find_next()` (remove their unconditional `_reveal_raw_xml_tab()` calls — `_active_find_bar` handles the fallback). The Edit-menu Find All / Replace All handlers (lines ~1801-1805) → `self._active_find_bar().find_all()` / `.replace_all()`.
  - **Find All on the XSD tab:** the XSD bar gets its own streaming callback wired in `__init__`:

```python
        stage.xsd_find_replace_bar.set_on_find_all(
            lambda term: self._populate_find_all_results(term, target="xsd")
        )
        stage.xsd_find_replace_bar.set_on_stop_find_all(self._stop_find_all)
```

Extend `_populate_find_all_results(self, term, target="raw")`: choose `text` from `stage.xsd_editor` when `target == "xsd"`; store the target with each result line's item data alongside the line number; the `[Find]`-click navigation handler navigates in the corresponding editor (and reveals the corresponding tab). Read `_populate_find_all_results`, `_on_find_result_clicked`/audit click routing and `set_find_all_running` usage before editing — mirror the existing raw-tab flow for `"xsd"`, switching only text source, `set_find_all_running` target bar, and navigation editor.
  - `closeEvent`: before the existing dirty-project handling, add the same pattern for `self._xsd_dirty` (reuse `_confirm_close`-style question via a small `_confirm_close_xsd()` returning save/discard/cancel; on "save" call `_save_curated_xsd()`). Tests monkeypatch it — never a live modal.

- [ ] **Step 4: Run** `tests\ui\test_edit_xsd_tab.py tests\ui\test_center_stage.py tests\ui\test_find_replace_bar.py tests\ui\test_search.py tests\ui\test_main_window.py -q` — PASS (fix any center-stage index assumptions in existing tests).
- [ ] **Step 5: Full suite** — PASS. **Step 6: Commit** `feat: Edit XSD center-stage tab with per-tab dirty/save/find routing`

---

### Task 9: Go To XSD

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py` (signal + context-menu entry), `pgtp_editor/ui/main_window.py` (handler + menu rewire of "Edit XSD" action + new Ctrl+L shortcut)
- Test: `tests/ui/test_xml_editor_annotate.py` (append editor-side), `tests/ui/test_edit_xsd_tab.py` (append wiring)

**Interfaces:**
- Consumes: `attribute_value_at_position`, `enclosing_open_tag` (pure), `CuratedSchema.attribute_lines`/`element_lines` (Task 5), `_open_edit_xsd` (Task 8).
- Produces: `XmlEditor.goto_xsd_requested = Signal(str, str)` — `(tag_chain, attr)` with `attr == ""` when the cursor is in a tag but not on an attribute; `XmlEditor.request_goto_xsd() -> bool`; context-menu action "Go To XSD"; `MainWindow._goto_xsd(chain, attr)`.

- [ ] **Step 1: Failing tests.** Append to `tests/ui/test_xml_editor_annotate.py`:

```python
def test_request_goto_xsd_emits_chain_and_attr(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1"/>')
    editor.set_schema_model(_model({"Root": {"a": _entry(["1"])}}))
    cursor = editor.textCursor()
    cursor.setPosition(editor.toPlainText().index('"1"') + 1)
    editor.setTextCursor(cursor)
    received = []
    editor.goto_xsd_requested.connect(lambda c, a: received.append((c, a)))
    assert editor.request_goto_xsd() is True
    assert received == [("Root", "a")]


def test_request_goto_xsd_element_only_when_not_on_attribute(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1"/>')
    editor.set_schema_model(_model({"Root": {"a": _entry(["1"])}}))
    cursor = editor.textCursor()
    cursor.setPosition(1)  # on the tag name
    editor.setTextCursor(cursor)
    received = []
    editor.goto_xsd_requested.connect(lambda c, a: received.append((c, a)))
    assert editor.request_goto_xsd() is True
    assert received == [("Root", "")]
```

Append to `tests/ui/test_edit_xsd_tab.py` (uses `_seed`/`_MINIMAL` — extend `_MINIMAL` if needed so it has attribute `a`):

```python
def test_goto_xsd_navigates_to_attribute_line(window):
    _seed(window)
    window._load_curated_schema()
    window._goto_xsd("Root", "a")
    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index
    line = window._curated_schema.attribute_lines[("Root", "a")]
    assert stage.xsd_editor.textCursor().blockNumber() + 1 == line


def test_goto_xsd_falls_back_to_element_then_status(window):
    _seed(window)
    window._load_curated_schema()
    window._goto_xsd("Root", "missing")
    line = window._curated_schema.element_lines["Root"]
    assert window.center_stage.xsd_editor.textCursor().blockNumber() + 1 == line
    window._goto_xsd("Nope", "x")
    assert "not in the curated XSD" in window.statusBar().currentMessage()
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**

3a. `xml_editor.py` — signal (with the other signals): `goto_xsd_requested = Signal(str, str)`; method next to `schema_model()`:

```python
    def request_goto_xsd(self) -> bool:
        """Resolve the caret to (tag_chain, attr) — attr "" when the caret is
        inside an opening tag but not on an attribute — and emit
        goto_xsd_requested. False when no model or unresolvable."""
        if self._schema_model is None:
            return False
        text = self.toPlainText()
        pos = self.textCursor().position()
        resolved = attribute_value_at_position(text, pos)
        if resolved is not None:
            tag_chain, attr, _value = resolved
            self.goto_xsd_requested.emit(tag_chain, attr)
            return True
        enclosing = enclosing_open_tag(text, pos)
        if enclosing is None:
            return False
        tag_chain, _present, _insert = enclosing
        self.goto_xsd_requested.emit(tag_chain, "")
        return True
```

Context menu — in `_build_context_menu`, where "Annotate value…" used to be, gate on `self._schema_model is not None and enclosing_open_tag(self.toPlainText(), cursor.position()) is not None`, action text `"Go To XSD"`, triggered → `self.request_goto_xsd` (same `before`-anchor insertion idiom as "Find").

3b. `main_window.py` — connect in `__init__`: `stage.xml_editor.goto_xsd_requested.connect(self._goto_xsd)`. Rewire the Schema menu: "Edit XSD" action → `self._open_edit_xsd` (drop the placeholder) and add below it a window-level action `goto_action = menu.addAction("Go To XSD")` with `goto_action.setShortcut(QKeySequence("Ctrl+L"))` triggered →:

```python
    def _goto_xsd_at_cursor(self):
        editor = self.center_stage.xml_editor
        if editor.schema_model() is None or not editor.request_goto_xsd():
            self.statusBar().showMessage(
                "Place the cursor inside an element in the Raw XML first.", 5000
            )
```

Wait — the spec menu is EXACTLY four items. Put Ctrl+L on a `QAction` added to the WINDOW (`self.addAction(...)`), not the menu:

```python
        goto_xsd_action = QAction("Go To XSD", self)
        goto_xsd_action.setShortcut(QKeySequence("Ctrl+L"))
        goto_xsd_action.triggered.connect(self._goto_xsd_at_cursor)
        self.addAction(goto_xsd_action)
```

Handler:

```python
    def _goto_xsd(self, tag_chain: str, attr: str) -> None:
        """Open the Edit XSD tab and select the attribute's definition;
        fall back to the element's type definition; else status message.
        Lines come from the last successful parse — navigation targets the
        saved file content."""
        schema = self._curated_schema
        if schema is None:
            self.statusBar().showMessage(
                "No curated XSD loaded yet — Schema ▸ Edit XSD.", 5000
            )
            return
        line = schema.attribute_lines.get((tag_chain, attr))
        if line is None:
            line = schema.element_lines.get(tag_chain)
        if line is None:
            self.statusBar().showMessage(
                f"'{tag_chain}' is not in the curated XSD yet.", 5000
            )
            return
        self._open_edit_xsd()
        self.center_stage.xsd_editor.navigate_to_line(line)
```

- [ ] **Step 4: Run** the two test files + `tests\ui\test_menus.py` (menu still exactly 4 items; add an assertion that the window carries the Ctrl+L action if the file checks shortcuts) — PASS. Full suite — PASS.
- [ ] **Step 5: Commit** `feat: Go To XSD from the Raw XML editor (Ctrl+L)`

---

### Task 10: Verify XSD — dialect verifier + menu + clickable audit lines + auto-run on save

**Files:**
- Create: `pgtp_editor/schema_learning/xsd_verify.py`
- Modify: `pgtp_editor/ui/main_window.py`
- Test: `tests/schema_learning/test_xsd_verify.py` (create), `tests/ui/test_edit_xsd_tab.py` (append)

**Interfaces:**
- Produces: `@dataclass Issue: line: int; message: str; fatal: bool = False`; `verify_curated(text: str) -> list[Issue]` (Qt-free; malformed XML/DTD → single fatal issue; sorted by line). MainWindow `_verify_xsd()` menu handler; audit convention `[Schema] VERIFY line {n}: {message}` with item data `("xsd", n)` for click-to-line; clean run → `[Schema] VERIFY: no issues found.`; `_save_curated_xsd` appends a report-only verify pass.

- [ ] **Step 1: Failing tests** — `tests/schema_learning/test_xsd_verify.py` (GPL header):

```python
from pgtp_editor.schema_learning.xsd_verify import Issue, verify_curated


def _wrap(body):
    return (
        '<?xml version="1.0"?>\n'
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">\n'
        f"{body}\n</xs:schema>\n"
    )


def test_clean_dialect_has_no_issues():
    text = _wrap(
        '  <xs:element name="Root" type="Root_Type"/>\n'
        '  <xs:complexType name="Root_Type">\n'
        '    <xs:attribute name="a" use="optional" sums="true">\n'
        '      <xs:simpleType><xs:restriction base="xs:integer">\n'
        '        <xs:enumeration value="1" label="A"/>\n'
        "      </xs:restriction></xs:simpleType>\n"
        "    </xs:attribute>\n"
        "  </xs:complexType>"
    )
    assert verify_curated(text) == []


def test_malformed_is_single_fatal_issue():
    issues = verify_curated("<broken")
    assert len(issues) == 1 and issues[0].fatal


def test_duplicate_enum_values_flagged():
    text = _wrap(
        '  <xs:complexType name="T">\n'
        '    <xs:attribute name="a">\n'
        "      <xs:simpleType><xs:restriction base=\"xs:integer\">\n"
        '        <xs:enumeration value="1"/>\n'
        '        <xs:enumeration value="1"/>\n'
        "      </xs:restriction></xs:simpleType>\n"
        "    </xs:attribute>\n"
        "  </xs:complexType>"
    )
    assert any("duplicate enumeration value" in i.message for i in verify_curated(text))


def test_misplaced_dialect_attributes_and_bad_base():
    text = _wrap(
        '  <xs:complexType name="T" label="wrong">\n'
        '    <xs:attribute name="a" >\n'
        '      <xs:simpleType><xs:restriction base="xs:unknown">\n'
        '        <xs:enumeration value="1" sums="true"/>\n'
        "      </xs:restriction></xs:simpleType>\n"
        "    </xs:attribute>\n"
        "  </xs:complexType>"
    )
    messages = " | ".join(i.message for i in verify_curated(text))
    assert "label" in messages          # label on non-enumeration
    assert "sums" in messages           # sums off xs:attribute
    assert "unknown base type" in messages


def test_unresolved_child_type_and_duplicate_type_names():
    text = _wrap(
        '  <xs:element name="Root" type="Missing_Type"/>\n'
        '  <xs:complexType name="T"/>\n'
        '  <xs:complexType name="T"/>'
    )
    messages = " | ".join(i.message for i in verify_curated(text))
    assert "unresolved type reference" in messages
    assert "duplicate type name" in messages
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `xsd_verify.py` (GPL header, then) — same expat pattern as `xsd_load` (streaming handlers, DTD forbidden → fatal issue, prefix-agnostic `_local`):

```python
"""Dialect verifier for the curated XSD (spec §11): OUR rules, not W3C
schema-for-schemas validity. Streaming expat pass collecting Issues with
1-based line numbers."""
from __future__ import annotations

from dataclasses import dataclass
from xml.parsers import expat

_KNOWN_BASES = {"xs:boolean", "xs:integer", "xs:decimal", "xs:string"}


@dataclass
class Issue:
    line: int
    message: str
    fatal: bool = False


def _local(tag):
    return tag.rsplit(":", 1)[-1]


class _Checker:
    def __init__(self, parser):
        self._parser = parser
        self.issues: list[Issue] = []
        self._enum_values_seen: set[str] | None = None   # per open xs:attribute
        self._type_names: dict[str, int] = {}
        self._type_refs: list[tuple[str, int]] = []
        self._in_attribute = 0

    def start(self, tag, attrs):
        local = _local(tag)
        line = self._parser.CurrentLineNumber
        if "label" in attrs and local != "enumeration":
            self.issues.append(Issue(line, f"label=\"…\" belongs on xs:enumeration, not on {local}"))
        if "sums" in attrs and local != "attribute":
            self.issues.append(Issue(line, f"sums=\"true\" belongs on xs:attribute, not on {local}"))
        if local == "complexType":
            name = attrs.get("name")
            if name:
                if name in self._type_names:
                    self.issues.append(Issue(line, f"duplicate type name '{name}'"))
                else:
                    self._type_names[name] = line
        elif local == "element":
            type_name = attrs.get("type")
            if type_name:
                self._type_refs.append((type_name, line))
        elif local == "attribute":
            self._in_attribute += 1
            self._enum_values_seen = set()
        elif local == "restriction":
            base = attrs.get("base")
            if base and base not in _KNOWN_BASES:
                self.issues.append(Issue(line, f"unknown base type '{base}'"))
        elif local == "enumeration" and self._enum_values_seen is not None:
            value = attrs.get("value", "")
            if value in self._enum_values_seen:
                self.issues.append(Issue(line, f"duplicate enumeration value '{value}'"))
            self._enum_values_seen.add(value)

    def end(self, tag):
        if _local(tag) == "attribute":
            self._in_attribute -= 1
            self._enum_values_seen = None

    def finish(self):
        for type_name, line in self._type_refs:
            if type_name not in self._type_names:
                self.issues.append(Issue(line, f"unresolved type reference '{type_name}'"))
        self.issues.sort(key=lambda issue: issue.line)
        return self.issues


def verify_curated(text: str) -> list[Issue]:
    parser = expat.ParserCreate()
    checker = _Checker(parser)

    def _forbid_dtd(*_args):
        raise expat.ExpatError("DTD declarations are not allowed")

    parser.StartDoctypeDeclHandler = _forbid_dtd
    parser.StartElementHandler = checker.start
    parser.EndElementHandler = checker.end
    try:
        parser.Parse(text, True)
    except expat.ExpatError as exc:
        lineno = getattr(exc, "lineno", parser.CurrentLineNumber) or 1
        return [Issue(lineno, f"XML error: {exc}", fatal=True)]
    return checker.finish()
```

(Note: `xs:unknown` base check compares the PREFIXED string against `_KNOWN_BASES` — the bootstrap emits `xs:` prefixes; a user file with another prefix would false-positive. Accept for now: compare on the local part too — `base in _KNOWN_BASES or _local(base) in {b.split(":")[1] for b in _KNOWN_BASES}` — implement this lenient form.)

3b. `main_window.py` — rewire "Verify XSD" placeholder:

```python
    def _verify_xsd(self) -> None:
        stage = self.center_stage
        if self._xsd_dirty:
            text = stage.xsd_editor.toPlainText()   # verify what the user sees
        else:
            path = curated_xsd_path(self._schema_storage_dir)
            if not path.exists():
                self.statusBar().showMessage("No curated XSD yet.", 5000)
                return
            text = path.read_text(encoding="utf-8")
        self._report_verify_issues(verify_curated(text))

    def _report_verify_issues(self, issues) -> None:
        if not issues:
            self.audit_panel.addItem("[Schema] VERIFY: no issues found.")
            return
        for issue in issues:
            item = QListWidgetItem(f"[Schema] VERIFY line {issue.line}: {issue.message}")
            item.setData(Qt.ItemDataRole.UserRole, ("xsd", issue.line))
            self.audit_panel.addItem(item)
```

Extend the audit-panel click handler (find `_on_audit_item_clicked` / the existing `[Find]` click routing): when item data is `("xsd", line)` → `self._open_edit_xsd()`; `self.center_stage.xsd_editor.navigate_to_line(line)`. `_save_curated_xsd` gains, after `_load_curated_schema()`: `self._report_verify_issues(verify_curated(self.center_stage.xsd_editor.toPlainText()))` — report-only.

- [ ] **Step 4: Failing wiring tests** — append to `tests/ui/test_edit_xsd_tab.py`:

```python
def test_verify_reports_clickable_issue_lines(window):
    _seed(window, _MINIMAL.replace(
        '<xs:attribute name="a" use="optional" type="xs:string"/>',
        '<xs:attribute name="a" use="optional" type="xs:string" label="wrong"/>',
    ))
    window._verify_xsd()
    items = [window.audit_panel.item(i) for i in range(window.audit_panel.count())]
    verify_items = [i for i in items if "VERIFY line" in i.text()]
    assert verify_items and verify_items[0].data(Qt.ItemDataRole.UserRole)[0] == "xsd"


def test_save_auto_verifies_report_only(window):
    _seed(window)
    window._open_edit_xsd()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL)
    window._save_curated_xsd()
    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any(t.startswith("[Schema] VERIFY") for t in texts)
```

- [ ] **Step 5: Run** all three touched test files + full suite — PASS.
- [ ] **Step 6: Commit** `feat: Verify XSD — dialect verifier with clickable audit lines, auto-run on save`

---

### Task 11: Export / Import XSD

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Test: `tests/ui/test_edit_xsd_tab.py` (append)

**Interfaces:**
- Consumes: `verify_curated` (Task 10), `_load_curated_schema` (Task 7), `curated_xsd_path`.
- Produces: `_export_xsd()` (QFileDialog.getSaveFileName → copy), `_import_xsd()` (getOpenFileName → verify: fatal → QMessageBox.critical refuse; non-fatal issues → QMessageBox.question Yes/No → `.bak` current → replace → `_load_curated_schema()` → reload tab if it was loaded).

- [ ] **Step 1: Failing tests** (monkeypatch every dialog):

```python
def test_export_copies_curated(window, monkeypatch, tmp_path):
    _seed(window)
    dest = tmp_path / "out.xsd"
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(dest), "")),
    )
    window._export_xsd()
    assert dest.read_text(encoding="utf-8") == _MINIMAL


def test_import_refuses_malformed(window, monkeypatch, tmp_path):
    _seed(window)
    bad = tmp_path / "bad.xsd"
    bad.write_text("<broken", encoding="utf-8")
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(bad), "")),
    )
    criticals = []
    monkeypatch.setattr(
        main_window_module.QMessageBox, "critical",
        staticmethod(lambda *a, **k: criticals.append(a)),
    )
    window._import_xsd()
    assert criticals
    assert curated_xsd_path(window._schema_storage_dir).read_text(encoding="utf-8") == _MINIMAL


def test_import_replaces_with_bak_and_reloads(window, monkeypatch, tmp_path):
    _seed(window)
    window._load_curated_schema()
    incoming = tmp_path / "incoming.xsd"
    incoming.write_text(_MINIMAL.replace('name="a"', 'name="z"'), encoding="utf-8")
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(incoming), "")),
    )
    window._import_xsd()
    path = curated_xsd_path(window._schema_storage_dir)
    assert 'name="z"' in path.read_text(encoding="utf-8")
    assert (path.parent / "curated.xsd.bak").read_text(encoding="utf-8") == _MINIMAL
    assert "z" in window.center_stage.xml_editor.schema_model().paths["Root"]["attributes"]
```

(Import the module as `main_window_module` at the top of the test file: `from pgtp_editor.ui import main_window as main_window_module`.)

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** — rewire the two placeholders:

```python
    def _export_xsd(self) -> None:
        source = curated_xsd_path(self._schema_storage_dir)
        if not source.exists():
            self.statusBar().showMessage("No curated XSD yet.", 5000)
            return
        if self._xsd_dirty:
            self.statusBar().showMessage(
                "The XSD tab has unsaved changes — save it first (Ctrl+S).", 5000
            )
            return
        dest, _filter = QFileDialog.getSaveFileName(
            self, "Export XSD", "curated.xsd", "XSD files (*.xsd)"
        )
        if not dest:
            return
        try:
            shutil.copyfile(source, dest)
        except OSError as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not export:\n\n{exc}")
            return
        self.statusBar().showMessage(f"Exported to {Path(dest).name}", 5000)

    def _import_xsd(self) -> None:
        """Replace curated.xsd with a teammate's file: verify first (hard
        refuse malformed XML; dialect warnings importable), back up, replace,
        re-parse (spec §11)."""
        source, _filter = QFileDialog.getOpenFileName(
            self, "Import XSD", "", "XSD files (*.xsd);;All files (*)"
        )
        if not source:
            return
        try:
            text = Path(source).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Import Failed", f"Could not read:\n\n{exc}")
            return
        issues = verify_curated(text)
        if any(issue.fatal for issue in issues):
            QMessageBox.critical(
                self, "Import Refused",
                "The file is not well-formed XML:\n\n" + issues[0].message,
            )
            return
        if issues:
            answer = QMessageBox.question(
                self, "Import With Warnings",
                f"The file has {len(issues)} dialect warning(s). Import anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        target = curated_xsd_path(self._schema_storage_dir)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.copy2(target, str(target) + ".bak")
            target.write_text(text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Import Failed", f"Could not write:\n\n{exc}")
            return
        self._set_xsd_dirty(False)
        self._load_curated_schema()
        stage = self.center_stage
        if stage.xsd_editor.toPlainText():
            self._xsd_loading = True
            try:
                stage.xsd_editor.setPlainText(text)
            finally:
                self._xsd_loading = False
        self.audit_panel.addItem(f"[Schema] Imported curated XSD from {Path(source).name}")
        self._report_verify_issues(issues)
```

(`shutil` is already imported in main_window.)

- [ ] **Step 4: Run** `tests\ui\test_edit_xsd_tab.py -q`, then full suite — PASS.
- [ ] **Step 5: Commit** `feat: Export/Import XSD (verify-first, .bak, re-parse)`

---

### Task 12: Properties panel — curated labels

**Files:**
- Modify: `pgtp_editor/ui/properties_panel.py`, `pgtp_editor/ui/main_window.py` (one line in `_load_curated_schema`)
- Test: `tests/ui/test_properties_panel.py` (append)

**Interfaces:**
- Consumes: `value_label(model, chain, attr, value)` (Task 6), `attribute_at_position` (pure, from xml_editor), the injected `_xml_editor` (`toPlainText`, `line_text`, `document`).
- Produces: `PropertiesPanel.set_schema_model(model)`; attribute rows whose value has a curated label render `value — label` (display-only; click/navigate behavior unchanged). `MainWindow._load_curated_schema` additionally calls `self.properties_panel.set_schema_model(schema.model)`.

- [ ] **Step 1: Failing test** — append to `tests/ui/test_properties_panel.py` (mirror that file's existing fake-editor/node fixtures; adapt names to what exists there):

```python
def test_attribute_row_shows_curated_label(qtbot):
    # Build a panel whose injected editor holds a document containing the
    # node's line, and a schema model with a label for the value.
    from pgtp_editor.schema_learning.model import Model
    from pgtp_editor.ui.xml_editor import XmlEditor
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root>\n  <Page phpDriver="1"/>\n</Root>')
    model = Model()
    model.paths = {"Root/Page": {
        "attributes": {"phpDriver": {
            "type": "integer", "values": ["0", "1"], "overflowed": False,
            "attr_seen_count": 1, "labels": {"1": "php-psql"}, "use": "optional",
        }},
        "children": {}, "instance_count": 1, "order": [],
        "order_stable": True, "has_text": False,
    }}
    panel = PropertiesPanel(editor)
    qtbot.addWidget(panel)
    panel.set_schema_model(model)

    class _Node:
        sourceline = 2
        attrib = {"phpDriver": "1"}
        file_name = "x"
        identity = "x"

    panel.show_node(_Node(), "page")
    assert panel.table.item(0, 1).text() == "1 — php-psql"


def test_attribute_row_plain_without_model(qtbot):
    from pgtp_editor.ui.xml_editor import XmlEditor
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root>\n  <Page phpDriver="1"/>\n</Root>')
    panel = PropertiesPanel(editor)
    qtbot.addWidget(panel)

    class _Node:
        sourceline = 2
        attrib = {"phpDriver": "1"}
        file_name = "x"
        identity = "x"

    panel.show_node(_Node(), "page")
    assert panel.table.item(0, 1).text() == "1"
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** in `properties_panel.py` — imports at the Qt section: `from pgtp_editor.schema_learning.settings_index import value_label` and `from pgtp_editor.ui.xml_editor import attribute_at_position`. In `__init__`: `self._schema_model = None`. Add:

```python
    def set_schema_model(self, model) -> None:
        """Inject the curated schema model (or None). Labels decorate
        attribute values as 'value — label' (spec §10); display-only."""
        self._schema_model = model

    def _display_value(self, spec: RowSpec) -> str:
        if (
            self._schema_model is None
            or spec.attr_name is None
            or spec.target_line is None
        ):
            return spec.value
        line_text = self._xml_editor.line_text(spec.target_line)
        needle = f'{spec.attr_name}="'
        index = line_text.find(needle)
        if index == -1:
            return spec.value
        block = self._xml_editor.document().findBlockByNumber(spec.target_line - 1)
        if not block.isValid():
            return spec.value
        resolved = attribute_at_position(
            self._xml_editor.toPlainText(), block.position() + index + 1
        )
        if resolved is None:
            return spec.value
        chain, attr = resolved
        label = value_label(self._schema_model, chain, attr, spec.value)
        return f"{spec.value} — {label}" if label else spec.value
```

and in `_populate_table` change the value cell to `self._make_item(self._display_value(row_spec))`.

In `main_window.py` `_load_curated_schema`, after `set_schema_model(schema.model)` add `self.properties_panel.set_schema_model(schema.model)`.

- [ ] **Step 4: Run** `tests\ui\test_properties_panel.py tests\ui\test_properties_panel_rows.py tests\ui\test_curated_feed_wiring.py -q`, then full suite — PASS.
- [ ] **Step 5: Commit** `feat: Properties panel shows curated labels (value — label)`

---

### Task 13: Finalization — suite, agents, spec sync

- [ ] **Step 1:** Full suite: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q` — PASS.
- [ ] **Step 2:** Dispatch `feature-tester` with: feature "Curated XSD as single schema source", spec §11 of `docs/superpowers/CONSOLIDATED_SPEC.md`, this plan, changed files from `git diff --name-only main...HEAD`. Iterate until green; it appends `docs/TEST_LOG.md`.
- [ ] **Step 3:** Dispatch `manual-maintainer` (after green): the manual must replace ALL annotate/team-sharing content with: Edit XSD tab workflow (dialect: `label=`, `sums="true"`, `hint=`; curation by deleting rows), Go To XSD (Ctrl+L), Verify/Export/Import, `learned.xsd` as the discovery reference, per-tab Ctrl+S, and the note that completion comes exclusively from `curated.xsd`.
- [ ] **Step 4:** Dispatch `spec-maintainer` for a sync pass: any naming that settled during implementation (e.g. `CuratedSchema` fields, verify rule wording, the window-level Ctrl+L action), confirm deleted modules, resolve leftovers.
- [ ] **Step 5:** Commit docs updates; hand back for branch finishing.

---

## Self-Review Notes

- **Spec coverage:** files/roles table → T1/T7; bootstrap → T4/T7; dialect → T5 (parse), T6 (semantics), T10 (verify); exclusive curated feed + learned-only enrichment → T7; Edit XSD tab + routing + malformed-save behavior → T8; Go To XSD incl. fallbacks → T9; four-item menu → T2 (placeholders) + T8/T9/T10/T11 (rewiring); Export/Import → T11; Properties labels → T12; deletions + ledger'd behavior removals → T2/T3.
- **Ordering keeps the suite green:** T2's deletions leave completion fed by the old enrichment path until T7 flips the source; T6's semantics rewrite lands before T7 so the first curated feed already uses dialect semantics.
- **Type consistency:** `CuratedSchema(model, attribute_lines, element_lines)` (T5) matches T7 storage and T9 lookups; `value_label` (T6) matches T12; `Issue(line, message, fatal)` (T10) matches T10's UI and T11's import gate; `verify_curated(text)` name consistent across T10/T11; `_active_find_bar`/`_save_active_tab` (T8) referenced nowhere else by other names.
- **Known accepted risks:** Go To XSD line map is stale while the XSD tab has unsaved edits (documented in `_goto_xsd` docstring; spec-consistent — navigation targets the last parsed save). Old `schema.xsd` files in AppData become stale orphans (harmless).
