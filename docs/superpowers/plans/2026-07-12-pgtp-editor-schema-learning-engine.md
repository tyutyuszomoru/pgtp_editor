# Schema Learning Engine + Auto-Enrich Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vendor the `pgtp_analytics` `pgtp_schema` inference engine into a new `pgtp_editor/schema_learning/` package (with a `labels` field added to `Model` and documentation-emission added to `xsd_gen`), and wire `MainWindow.open_project_file`'s success path to auto-enrich a per-user, ever-growing schema model/XSD from every file the user opens, reporting findings into the existing Audit panel.

**Architecture:** Four modules (`model.py`, `parser.py`, `types.py`, `xsd_gen.py`) are copied near-verbatim from `pgtp_analytics/pgtp_schema/` into `pgtp_editor/schema_learning/`, with two source changes (a `labels: dict[str, str]` field on each attribute entry in `model.py`, and `xs:documentation` emission for labeled enum values in `xsd_gen.py`). A new `storage.py` module resolves per-user file paths for `schema_model.json`/`schema.xsd` via `QStandardPaths.AppDataLocation`, with an overridable `base_dir` parameter for tests. `MainWindow` gains an optional `schema_storage_dir` constructor parameter and two new methods, `_enrich_schema_from_file` and `_report_schema_events`, called from the tail of `open_project_file`'s existing success path — never from its `except` branch — so a broken file never touches the schema model, and any schema-learning failure is caught and reported as a single terse Audit panel line rather than propagating or interrupting the primary "open a project" workflow.

**Tech Stack:** Python 3.10+, PySide6 (QStandardPaths, QMainWindow, QListWidget), defusedxml (ElementTree-based parsing), pytest, pytest-qt.

---

## Context for the implementing engineer

- Working directory for all tasks: the git worktree at `pgtp-editor-combined` (already checked out on branch `worktree-pgtp-editor-combined`). All file paths below are relative to that worktree root unless given as absolute paths.
- The **source files to vendor** live in a *different, unrelated* repo working tree on this machine, not in this worktree and not committed anywhere: `C:\Users\BotondZalai-RuzsicsP\docs\Software development\pgtp_editor\pgtp_analytics\pgtp_schema\model.py`, `parser.py`, `types.py`, `xsd_gen.py`. Read each one directly (Task 1/2/3 below give you the exact vendoring instructions and, where the file changes, the complete resulting code) — do not paraphrase from memory.
- The existing pytest suite in this worktree lives under `tests/` (`tests/model/`, `tests/diff/`, `tests/ui/`), configured via `pyproject.toml`'s `[tool.pytest.ini_options]` (`testpaths = ["tests"]`, `qt_api = "pyside6"`). The new tests for this sub-project go under `tests/schema_learning/` in this same worktree — **not** under `pgtp_analytics/tests/`, and not reusing that project's test file names verbatim (though the assertions inside follow the same style/conventions).
- Two real `.pgtp` sample files already exist, gitignored, directly in this worktree at `sample/dev_Ferrara.pgtp` and `sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp` — used by the integration test in Task 8.
- `defusedxml` is already installed in the local Python environment (`python -c "import defusedxml"` succeeds) — no `pip install` step is required before running tests in this plan, but Task 4 still adds the declared dependency to `pyproject.toml` so the requirement is correctly recorded for anyone else's environment.
- Run all `pytest`/`python` commands from the worktree root. This project uses PowerShell as the primary shell on this machine; the commands below are plain `pytest`/`python -c ...` invocations that work identically in PowerShell or POSIX shells.

---

## Task 1: Vendor `types.py` and `parser.py` unchanged

These two modules are copied byte-for-byte (aside from this plan not needing to touch their content at all) from `pgtp_analytics/pgtp_schema/`. No source changes. Tests are direct ports of the existing `pgtp_analytics` test suite's assertions, adjusted only to import from the new vendored location.

**Files:**
- Create: `pgtp_editor/schema_learning/__init__.py`
- Create: `pgtp_editor/schema_learning/types.py`
- Create: `pgtp_editor/schema_learning/parser.py`
- Test: `tests/schema_learning/__init__.py`
- Test: `tests/schema_learning/test_types.py`
- Test: `tests/schema_learning/test_parser.py`

- [ ] **Step 1: Create the package directories and empty `__init__.py` files**

Create `pgtp_editor/schema_learning/__init__.py` with this exact content (an empty package marker, matching the convention of other `pgtp_editor` subpackages):

```python
```

Create `tests/schema_learning/__init__.py` with this exact content:

```python
```

- [ ] **Step 2: Write the failing tests for `types.py`**

Create `tests/schema_learning/test_types.py`:

```python
from pgtp_editor.schema_learning.types import infer_scalar_type, combine_type


def test_infer_boolean():
    assert infer_scalar_type("true") == "boolean"
    assert infer_scalar_type("false") == "boolean"


def test_infer_integer():
    assert infer_scalar_type("42") == "integer"
    assert infer_scalar_type("-7") == "integer"


def test_infer_decimal():
    assert infer_scalar_type("3.14") == "decimal"
    assert infer_scalar_type("-0.5") == "decimal"


def test_infer_string_fallback():
    assert infer_scalar_type("hello") == "string"
    assert infer_scalar_type("") == "string"
    assert infer_scalar_type("1573119") == "integer"
    assert infer_scalar_type("R:\\var\\www\\html") == "string"


def test_combine_type_widens_toward_string():
    assert combine_type("boolean", "integer") == "integer"
    assert combine_type("integer", "boolean") == "integer"
    assert combine_type("integer", "decimal") == "decimal"
    assert combine_type("decimal", "string") == "string"
    assert combine_type("string", "boolean") == "string"
    assert combine_type("boolean", "boolean") == "boolean"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/schema_learning/test_types.py -v`
Expected: FAIL / collection error — `ModuleNotFoundError: No module named 'pgtp_editor.schema_learning.types'`

- [ ] **Step 4: Vendor `types.py`**

Create `pgtp_editor/schema_learning/types.py` with this exact content, copied verbatim from `pgtp_analytics/pgtp_schema/types.py`:

```python
import re

_BOOL_VALUES = {"true", "false"}
_INT_RE = re.compile(r"^-?\d+$")
_DECIMAL_RE = re.compile(r"^-?\d+\.\d+$")

_TYPE_RANK = {"boolean": 0, "integer": 1, "decimal": 2, "string": 3}


def infer_scalar_type(value):
    if value in _BOOL_VALUES:
        return "boolean"
    if _INT_RE.fullmatch(value):
        return "integer"
    if _DECIMAL_RE.fullmatch(value):
        return "decimal"
    return "string"


def combine_type(type_a, type_b):
    return type_a if _TYPE_RANK[type_a] >= _TYPE_RANK[type_b] else type_b
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/schema_learning/test_types.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Write the failing tests for `parser.py`**

Create `tests/schema_learning/test_parser.py`:

```python
import defusedxml.ElementTree as ET

from pgtp_editor.schema_learning.parser import walk_element, walk_document


def test_walk_single_element_yields_its_own_path_and_attrib():
    root = ET.fromstring('<Root a="1" b="2"/>')
    events = list(walk_element(root, root.tag))

    assert events == [("Root", {"a": "1", "b": "2"}, {}, False)]


def test_walk_nested_elements_builds_full_paths():
    root = ET.fromstring('<Root><Child x="1"/><Child x="2"/></Root>')
    events = list(walk_element(root, root.tag))

    paths = [e[0] for e in events]
    assert paths == ["Root", "Root/Child", "Root/Child"]
    assert events[0][2] == {"Child": 2}
    assert events[1][1] == {"x": "1"}
    assert events[2][1] == {"x": "2"}


def test_walk_grandchild_path_includes_full_ancestry():
    root = ET.fromstring("<A><B><C/></B></A>")
    events = list(walk_element(root, root.tag))

    paths = [e[0] for e in events]
    assert paths == ["A", "A/B", "A/B/C"]


def test_walk_detects_meaningful_text():
    root = ET.fromstring("<Root>hello</Root>")
    events = list(walk_element(root, root.tag))

    assert events[0][3] is True


def test_walk_ignores_whitespace_only_text():
    root = ET.fromstring("<Root>\n  <Child/>\n</Root>")
    events = list(walk_element(root, root.tag))

    assert events[0][3] is False


def test_walk_document_parses_from_file(tmp_path):
    xml_path = tmp_path / "sample.xml"
    xml_path.write_text('<Root a="1"><Child/></Root>', encoding="utf-8")

    events = list(walk_document(str(xml_path)))

    assert events[0][0] == "Root"
    assert events[1][0] == "Root/Child"


def test_walk_document_strips_cesu8_surrogate_pairs(tmp_path):
    # CESU-8 mis-encoded surrogate pair (as could appear in a malformed
    # real-world .pgtp file's free-text content) must be stripped rather
    # than raising a not-well-formed-XML error.
    xml_path = tmp_path / "cesu8.xml"
    surrogate_pair_bytes = b"\xed\xa0\xbd\xed\xb8\x80"  # mis-encoded U+1F600
    data = b'<Root a="1">before' + surrogate_pair_bytes + b"after</Root>"
    xml_path.write_bytes(data)

    events = list(walk_document(str(xml_path)))

    assert events[0][0] == "Root"
    assert events[0][3] is True
```

- [ ] **Step 7: Run the test to verify it fails**

Run: `pytest tests/schema_learning/test_parser.py -v`
Expected: FAIL / collection error — `ModuleNotFoundError: No module named 'pgtp_editor.schema_learning.parser'`

- [ ] **Step 8: Vendor `parser.py`**

Create `pgtp_editor/schema_learning/parser.py` with this exact content, copied verbatim from `pgtp_analytics/pgtp_schema/parser.py`:

```python
import io
import re

import defusedxml.ElementTree as ET

# Matches CESU-8 encoded UTF-16 surrogate pairs: some real-world .pgtp files
# contain emoji in free-text element content (e.g. embedded PHP/JS source)
# that tools have mis-encoded as two 3-byte UTF-8 sequences representing a
# surrogate pair, instead of one proper 4-byte UTF-8 sequence. Each 3-byte
# sequence is syntactically valid UTF-8 but decodes to a lone/paired
# surrogate codepoint, which is forbidden by the XML spec and makes expat
# reject the file as "not well-formed". Since this tool only cares about
# document structure (not the exact text of free-form content), we strip
# these sequences before parsing rather than trying to recover the emoji.
_CESU8_SURROGATE_PAIR_RE = re.compile(
    rb"[\xed][\xa0-\xaf][\x80-\xbf][\xed][\xb0-\xbf][\x80-\xbf]"
)


def _read_sanitized_bytes(file_path):
    with open(file_path, "rb") as f:
        data = f.read()
    return _CESU8_SURROGATE_PAIR_RE.sub(b"", data)


def walk_document(file_path):
    data = _read_sanitized_bytes(file_path)
    root = ET.parse(io.BytesIO(data)).getroot()
    yield from walk_element(root, root.tag)


def walk_element(elem, path):
    child_tag_counts = {}
    for child in elem:
        child_tag_counts[child.tag] = child_tag_counts.get(child.tag, 0) + 1

    has_text = bool(elem.text and elem.text.strip())

    yield path, dict(elem.attrib), child_tag_counts, has_text

    for child in elem:
        yield from walk_element(child, f"{path}/{child.tag}")
```

- [ ] **Step 9: Run the test to verify it passes**

Run: `pytest tests/schema_learning/test_parser.py -v`
Expected: PASS (7 tests)

- [ ] **Step 10: Commit**

```bash
git add pgtp_editor/schema_learning/__init__.py pgtp_editor/schema_learning/types.py pgtp_editor/schema_learning/parser.py tests/schema_learning/__init__.py tests/schema_learning/test_types.py tests/schema_learning/test_parser.py
git commit -m "feat(schema-learning): vendor types.py and parser.py from pgtp_analytics"
```

---

## Task 2: Vendor `model.py` with the `labels` field addition

`model.py` is copied from `pgtp_analytics/pgtp_schema/model.py` with one addition: every attribute entry (both branches inside `merge_element`) gains `"labels": {}`, and `merge_element` never reads or writes that key afterward — it is purely additive storage for the future "Annotate Schema Values..." UI. This task ports the full existing `pgtp_analytics` test suite for `model.py` (renamed import) plus three new tests specific to `labels` preservation.

**Files:**
- Create: `pgtp_editor/schema_learning/model.py`
- Test: `tests/schema_learning/test_model.py`

- [ ] **Step 1: Write the failing tests — ported existing behavior plus new `labels` tests**

Create `tests/schema_learning/test_model.py`:

```python
from pgtp_editor.schema_learning.model import Model


def test_new_path_emits_new_element_and_new_attribute_events():
    model = Model()
    events = model.merge_element("Root", {"a": "1", "b": "x"}, {}, False)

    kinds = [e["kind"] for e in events]
    assert "new_element" in kinds
    assert kinds.count("new_attribute") == 2

    entry = model.paths["Root"]
    assert entry["instance_count"] == 1
    assert entry["attributes"]["a"]["type"] == "integer"
    assert entry["attributes"]["a"]["values"] == ["1"]
    assert entry["attributes"]["b"]["type"] == "string"


def test_repeat_instance_same_value_emits_no_new_events():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    events = model.merge_element("Root", {"a": "1"}, {}, False)

    assert events == []
    assert model.paths["Root"]["instance_count"] == 2
    assert model.paths["Root"]["attributes"]["a"]["attr_seen_count"] == 2


def test_new_distinct_value_emits_new_value_event():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    events = model.merge_element("Root", {"a": "2"}, {}, False)

    assert [e["kind"] for e in events] == ["new_value"]
    assert model.paths["Root"]["attributes"]["a"]["values"] == ["1", "2"]


def test_type_widens_when_a_non_matching_value_appears():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.merge_element("Root", {"a": "hello"}, {}, False)

    assert model.paths["Root"]["attributes"]["a"]["type"] == "string"


def test_enum_overflows_past_ten_distinct_values():
    model = Model()
    events = []
    for i in range(11):
        events = model.merge_element("Root", {"a": str(i)}, {}, False)

    attr = model.paths["Root"]["attributes"]["a"]
    assert attr["overflowed"] is True
    assert attr["values"] is None
    assert any(e["kind"] == "enum_overflow" for e in events)


def test_overflowed_attribute_never_emits_new_value_again():
    model = Model()
    for i in range(11):
        model.merge_element("Root", {"a": str(i)}, {}, False)

    events = model.merge_element("Root", {"a": "not-seen-before"}, {}, False)
    assert events == []


def test_missing_attribute_flips_required_to_optional():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.merge_element("Root", {"a": "2"}, {}, False)
    events = model.merge_element("Root", {}, {}, False)

    assert any(e["kind"] == "now_optional" and e["attr"] == "a" for e in events)
    assert model.paths["Root"]["attributes"]["a"]["attr_seen_count"] == 2
    assert model.paths["Root"]["instance_count"] == 3


def test_optional_attribute_missing_again_emits_no_further_event():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.merge_element("Root", {}, {}, False)
    events = model.merge_element("Root", {}, {}, False)

    assert events == []


def test_child_seen_in_every_instance_is_required_single():
    model = Model()
    model.merge_element("Root", {}, {"A": 1}, False)
    model.merge_element("Root", {}, {"A": 1}, False)

    child = model.paths["Root"]["children"]["A"]
    assert child["ever_absent"] is False
    assert child["ever_multiple"] is False


def test_child_missing_in_some_instance_is_marked_ever_absent():
    model = Model()
    model.merge_element("Root", {}, {"A": 1, "B": 1}, False)
    model.merge_element("Root", {}, {"A": 1}, False)

    assert model.paths["Root"]["children"]["B"]["ever_absent"] is True
    assert model.paths["Root"]["children"]["A"]["ever_absent"] is False


def test_child_appearing_only_later_is_retroactively_ever_absent():
    model = Model()
    model.merge_element("Root", {}, {"A": 1}, False)
    model.merge_element("Root", {}, {"A": 1, "B": 1}, False)

    assert model.paths["Root"]["children"]["B"]["ever_absent"] is True


def test_child_appearing_multiple_times_in_one_instance_is_ever_multiple():
    model = Model()
    model.merge_element("Root", {}, {"A": 3}, False)

    assert model.paths["Root"]["children"]["A"]["ever_multiple"] is True


def test_order_stable_when_consistent():
    model = Model()
    model.merge_element("Root", {}, {"A": 1, "B": 1}, False)
    model.merge_element("Root", {}, {"A": 1, "B": 1}, False)

    assert model.paths["Root"]["order_stable"] is True
    assert model.paths["Root"]["order"] == ["A", "B"]


def test_order_unstable_when_relative_order_changes():
    model = Model()
    model.merge_element("Root", {}, {"A": 1, "B": 1}, False)
    model.merge_element("Root", {}, {"B": 1, "A": 1}, False)

    assert model.paths["Root"]["order_stable"] is False


def test_has_text_flag_sticky_once_true():
    model = Model()
    model.merge_element("Root", {}, {}, True)
    model.merge_element("Root", {}, {}, False)

    assert model.paths["Root"]["has_text"] is True


def test_secret_named_attribute_never_captures_values():
    model = Model()
    events1 = model.merge_element("Root", {"password": "hunter2"}, {}, False)

    attr = model.paths["Root"]["attributes"]["password"]
    assert attr["overflowed"] is True
    assert attr["values"] is None
    assert not any(e["kind"] in ("new_value", "enum_overflow") for e in events1)

    events2 = model.merge_element("Root", {"password": "other"}, {}, False)
    attr = model.paths["Root"]["attributes"]["password"]
    assert attr["overflowed"] is True
    assert attr["values"] is None
    assert not any(e["kind"] in ("new_value", "enum_overflow") for e in events2)


def test_secret_name_matching_is_case_insensitive_substring():
    model = Model()
    model.merge_element(
        "Root",
        {"Password": "a", "DB_PASSWORD": "b", "authToken": "c"},
        {},
        False,
    )

    for attr_name in ("Password", "DB_PASSWORD", "authToken"):
        attr = model.paths["Root"]["attributes"][attr_name]
        assert attr["overflowed"] is True
        assert attr["values"] is None


def test_non_secret_attribute_still_gets_normal_enum_tracking():
    model = Model()
    model.merge_element("Root", {"name": "x"}, {}, False)
    model.merge_element("Root", {"name": "y"}, {}, False)

    attr = model.paths["Root"]["attributes"]["name"]
    assert attr["overflowed"] is False
    assert attr["values"] == ["x", "y"]


def test_secret_named_attribute_still_emits_new_attribute_event():
    model = Model()
    events = model.merge_element("Root", {"password": "hunter2"}, {}, False)

    assert any(e["kind"] == "new_attribute" and e["attr"] == "password" for e in events)


# --- labels field: new tests for this sub-project ---


def test_freshly_created_attribute_entry_has_empty_labels():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)

    assert model.paths["Root"]["attributes"]["a"]["labels"] == {}


def test_secret_attribute_entry_also_has_empty_labels():
    model = Model()
    model.merge_element("Root", {"password": "hunter2"}, {}, False)

    assert model.paths["Root"]["attributes"]["password"]["labels"] == {}


def test_labels_round_trip_through_to_dict_from_dict_and_save_load(tmp_path):
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.paths["Root"]["attributes"]["a"]["labels"]["1"] = "Full export"

    restored = Model.from_dict(model.to_dict())
    assert restored.paths["Root"]["attributes"]["a"]["labels"] == {"1": "Full export"}

    save_path = tmp_path / "model.json"
    model.save(save_path)
    loaded = Model.load(save_path)
    assert loaded.paths["Root"]["attributes"]["a"]["labels"] == {"1": "Full export"}


def test_merge_element_never_alters_existing_labels_across_repeated_merges():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.paths["Root"]["attributes"]["a"]["labels"]["1"] = "One"

    # Merge several more times, including a new distinct value, and confirm
    # the previously-set label survives untouched.
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.merge_element("Root", {"a": "2"}, {}, False)

    assert model.paths["Root"]["attributes"]["a"]["labels"] == {"1": "One"}


def test_labels_survive_enum_overflow_even_though_values_becomes_none():
    model = Model()
    model.merge_element("Root", {"a": "0"}, {}, False)
    model.paths["Root"]["attributes"]["a"]["labels"]["0"] = "Zero label"

    for i in range(1, 11):
        model.merge_element("Root", {"a": str(i)}, {}, False)

    attr = model.paths["Root"]["attributes"]["a"]
    assert attr["overflowed"] is True
    assert attr["values"] is None
    assert attr["labels"] == {"0": "Zero label"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/schema_learning/test_model.py -v`
Expected: FAIL / collection error — `ModuleNotFoundError: No module named 'pgtp_editor.schema_learning.model'`

- [ ] **Step 3: Vendor `model.py` with the `labels` field addition**

Create `pgtp_editor/schema_learning/model.py` with this exact content — copied from `pgtp_analytics/pgtp_schema/model.py`, with `"labels": {}` added to both attribute-entry dict literals inside `merge_element`:

```python
import json

from .types import infer_scalar_type, combine_type

ENUM_MAX_VALUES = 10

_SECRET_NAME_SUBSTRINGS = ("password", "pwd", "secret", "token")


def _looks_like_secret(attr_name):
    lowered = attr_name.lower()
    return any(substring in lowered for substring in _SECRET_NAME_SUBSTRINGS)


class Model:
    def __init__(self):
        self.paths = {}

    def _get_or_create_path(self, path):
        is_new = path not in self.paths
        if is_new:
            self.paths[path] = {
                "attributes": {},
                "children": {},
                "instance_count": 0,
                "order": [],
                "order_stable": True,
                "has_text": False,
            }
        return self.paths[path], is_new

    def merge_element(self, path, attrib, child_tag_counts, has_text):
        events = []
        entry, is_new = self._get_or_create_path(path)
        if is_new:
            events.append({"kind": "new_element", "path": path})

        prev_instance_count = entry["instance_count"]
        new_instance_count = prev_instance_count + 1

        for attr_name, attr_entry in entry["attributes"].items():
            if attr_name in attrib:
                continue
            was_required = attr_entry["attr_seen_count"] == prev_instance_count
            is_required_now = attr_entry["attr_seen_count"] == new_instance_count
            if was_required and not is_required_now:
                events.append({"kind": "now_optional", "path": path, "attr": attr_name})

        entry["instance_count"] = new_instance_count

        for attr_name, value in attrib.items():
            value_type = infer_scalar_type(value)

            if attr_name not in entry["attributes"]:
                if _looks_like_secret(attr_name):
                    entry["attributes"][attr_name] = {
                        "type": value_type,
                        "values": None,
                        "overflowed": True,
                        "attr_seen_count": 1,
                        "labels": {},
                    }
                else:
                    entry["attributes"][attr_name] = {
                        "type": value_type,
                        "values": [value],
                        "overflowed": False,
                        "attr_seen_count": 1,
                        "labels": {},
                    }
                events.append({"kind": "new_attribute", "path": path, "attr": attr_name})
                continue

            attr_entry = entry["attributes"][attr_name]
            attr_entry["type"] = combine_type(attr_entry["type"], value_type)
            attr_entry["attr_seen_count"] += 1

            if attr_entry["overflowed"]:
                continue

            if value in attr_entry["values"]:
                continue

            attr_entry["values"].append(value)
            events.append({"kind": "new_value", "path": path, "attr": attr_name, "value": value})

            if len(attr_entry["values"]) > ENUM_MAX_VALUES:
                attr_entry["overflowed"] = True
                attr_entry["values"] = None
                events.append({"kind": "enum_overflow", "path": path, "attr": attr_name})

        self._merge_children(entry, prev_instance_count, child_tag_counts)

        if has_text:
            entry["has_text"] = True

        return events

    def _merge_children(self, entry, prev_instance_count, child_tag_counts):
        seen_order = list(child_tag_counts.keys())

        for tag, child_entry in entry["children"].items():
            if child_tag_counts.get(tag, 0) == 0:
                child_entry["ever_absent"] = True

        for tag in seen_order:
            count = child_tag_counts[tag]
            if tag not in entry["children"]:
                entry["children"][tag] = {
                    "ever_absent": prev_instance_count > 0,
                    "ever_multiple": count > 1,
                }
                entry["order"].append(tag)
            elif count > 1:
                entry["children"][tag]["ever_multiple"] = True

        common = set(entry["order"]) & set(seen_order)
        order_common = [t for t in entry["order"] if t in common]
        seen_common = [t for t in seen_order if t in common]
        if order_common != seen_common:
            entry["order_stable"] = False

    def to_dict(self):
        return {"paths": self.paths}

    @classmethod
    def from_dict(cls, data):
        model = cls()
        model.paths = data.get("paths", {})
        return model

    def save(self, file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)

    @classmethod
    def load(cls, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/schema_learning/test_model.py -v`
Expected: PASS (23 tests)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/schema_learning/model.py tests/schema_learning/test_model.py
git commit -m "feat(schema-learning): vendor model.py with labels field for future annotation UI"
```

---

## Task 3: Vendor `xsd_gen.py` with `xs:documentation` emission for labeled enum values

`xsd_gen.py` is copied from `pgtp_analytics/pgtp_schema/xsd_gen.py` with one change inside `_attribute_lines`: the enumeration-emitting loop now checks `attr_entry.get("labels", {})` for each value and, when a non-empty label exists, emits a nested `<xs:annotation><xs:documentation>` instead of the plain self-closed `<xs:enumeration .../>`. `escape` is already imported at module scope; no new import is needed.

**Files:**
- Create: `pgtp_editor/schema_learning/xsd_gen.py`
- Test: `tests/schema_learning/test_xsd_gen.py`

- [ ] **Step 1: Write the failing tests — ported existing behavior plus new documentation-emission tests**

Create `tests/schema_learning/test_xsd_gen.py`:

```python
import defusedxml.ElementTree as ET

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.xsd_gen import _type_name, generate_xsd


def _build_sample_model():
    model = Model()
    model.merge_element("Root", {"mode": "1"}, {"Child": 1}, False)
    model.merge_element("Root", {"mode": "2"}, {"Child": 1}, False)
    model.merge_element("Root/Child", {"name": "x"}, {}, False)
    model.merge_element("Root/Child", {"name": "y"}, {}, False)
    return model


def test_generated_xsd_is_well_formed_xml():
    model = _build_sample_model()
    xsd_text = generate_xsd(model)

    ET.fromstring(xsd_text)  # raises if malformed


def test_generated_xsd_declares_root_element():
    model = _build_sample_model()
    xsd_text = generate_xsd(model)

    assert '<xs:element name="Root" type="Root_Type"/>' in xsd_text


def test_generated_xsd_includes_enumeration_for_small_value_set():
    model = _build_sample_model()
    xsd_text = generate_xsd(model)

    assert '<xs:enumeration value="1"/>' in xsd_text
    assert '<xs:enumeration value="2"/>' in xsd_text


def test_generated_xsd_declares_child_element_with_type_ref():
    model = _build_sample_model()
    xsd_text = generate_xsd(model)

    assert 'name="Child" type="Root_Child_Type"' in xsd_text


def test_generated_xsd_marks_overflowed_attribute_as_plain_type():
    model = Model()
    for i in range(11):
        model.merge_element("Root", {"free": str(i)}, {}, False)

    xsd_text = generate_xsd(model)
    assert '<xs:attribute name="free" type="xs:integer" use="required"/>' in xsd_text
    assert "xs:enumeration" not in xsd_text


def test_generated_xsd_marks_optional_attribute():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.merge_element("Root", {}, {}, False)

    xsd_text = generate_xsd(model)
    assert 'use="optional"' in xsd_text


def test_generated_xsd_uses_unbounded_for_repeated_children():
    model = Model()
    model.merge_element("Root", {}, {"Item": 3}, False)
    model.merge_element("Root/Item", {}, {}, False)

    xsd_text = generate_xsd(model)
    assert 'maxOccurs="unbounded"' in xsd_text


def test_generated_xsd_marks_mixed_content():
    model = Model()
    model.merge_element("Root", {}, {}, True)

    xsd_text = generate_xsd(model)
    assert 'mixed="true"' in xsd_text


def test_type_name_for_simple_paths_without_underscores():
    assert _type_name("Root") == "Root_Type"
    assert _type_name("Root/Child") == "Root_Child_Type"


def test_type_name_escapes_literal_underscores_to_avoid_collision():
    assert _type_name("A_B/C") == "A__B_C_Type"
    assert _type_name("A/B_C") == "A_B__C_Type"
    assert _type_name("A_B/C") != _type_name("A/B_C")


def test_generate_xsd_does_not_collide_type_names_for_underscore_paths():
    model = Model()
    model.merge_element("A_B/C", {}, {}, False)
    model.merge_element("A/B_C", {}, {}, False)

    xsd_text = generate_xsd(model)

    name1 = _type_name("A_B/C")
    name2 = _type_name("A/B_C")
    assert name1 != name2
    assert f'<xs:complexType name="{name1}"' in xsd_text
    assert f'<xs:complexType name="{name2}"' in xsd_text


# --- xs:documentation emission: new tests for this sub-project ---


def test_labeled_enum_value_emits_documentation_while_unlabeled_stays_plain():
    model = Model()
    model.merge_element("Root", {"mode": "1"}, {}, False)
    model.merge_element("Root", {"mode": "2"}, {}, False)
    model.paths["Root"]["attributes"]["mode"]["labels"]["1"] = "Full export"

    xsd_text = generate_xsd(model)

    assert (
        '<xs:enumeration value="1">\n'
        "            <xs:annotation>\n"
        "              <xs:documentation>Full export</xs:documentation>\n"
        "            </xs:annotation>\n"
        "          </xs:enumeration>"
    ) in xsd_text
    assert '<xs:enumeration value="2"/>' in xsd_text
    ET.fromstring(xsd_text)  # still well-formed XML


def test_missing_labels_key_does_not_raise_key_error():
    # Simulates a schema_model.json written before this sub-project existed:
    # no "labels" key at all on the attribute entry.
    model = Model()
    model.merge_element("Root", {"mode": "1"}, {}, False)
    del model.paths["Root"]["attributes"]["mode"]["labels"]

    xsd_text = generate_xsd(model)

    assert '<xs:enumeration value="1"/>' in xsd_text


def test_empty_string_label_is_treated_as_no_label():
    model = Model()
    model.merge_element("Root", {"mode": "1"}, {}, False)
    model.paths["Root"]["attributes"]["mode"]["labels"]["1"] = ""

    xsd_text = generate_xsd(model)

    assert '<xs:enumeration value="1"/>' in xsd_text
    assert "xs:documentation" not in xsd_text


def test_label_with_xml_special_characters_is_escaped():
    model = Model()
    model.merge_element("Root", {"mode": "1"}, {}, False)
    model.paths["Root"]["attributes"]["mode"]["labels"]["1"] = "A & B < C"

    xsd_text = generate_xsd(model)

    assert "<xs:documentation>A &amp; B &lt; C</xs:documentation>" in xsd_text
    ET.fromstring(xsd_text)  # must remain well-formed XML despite the raw label text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/schema_learning/test_xsd_gen.py -v`
Expected: FAIL / collection error — `ModuleNotFoundError: No module named 'pgtp_editor.schema_learning.xsd_gen'`

- [ ] **Step 3: Vendor `xsd_gen.py` with the documentation-emission change**

Create `pgtp_editor/schema_learning/xsd_gen.py` with this exact content:

```python
from xml.sax.saxutils import escape, quoteattr

_XSD_BASE = {
    "boolean": "xs:boolean",
    "integer": "xs:integer",
    "decimal": "xs:decimal",
    "string": "xs:string",
}


def _type_name(path):
    escaped_segments = [segment.replace("_", "__") for segment in path.split("/")]
    return "_".join(escaped_segments) + "_Type"


def generate_xsd(model):
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" elementFormDefault="qualified">',
    ]

    root_paths = sorted(p for p in model.paths if "/" not in p)
    for root_path in root_paths:
        lines.append(
            f'  <xs:element name={quoteattr(root_path)} type={quoteattr(_type_name(root_path))}/>'
        )

    for path in sorted(model.paths):
        lines.extend(_complex_type_lines(path, model.paths[path]))

    lines.append("</xs:schema>")
    return "\n".join(lines) + "\n"


def _complex_type_lines(path, entry):
    lines = []
    if not entry["order_stable"]:
        lines.append(
            f"  <!-- WARNING: child order varies across samples for {escape(path)}; "
            f"using first-observed order -->"
        )

    mixed_attr = ' mixed="true"' if entry["has_text"] else ""
    lines.append(f'  <xs:complexType name={quoteattr(_type_name(path))}{mixed_attr}>')

    if entry["order"]:
        lines.append("    <xs:sequence>")
        for tag in entry["order"]:
            child_info = entry["children"][tag]
            min_occurs = "0" if child_info["ever_absent"] else "1"
            max_occurs = "unbounded" if child_info["ever_multiple"] else "1"
            child_type = _type_name(f"{path}/{tag}")
            lines.append(
                f"      <xs:element name={quoteattr(tag)} type={quoteattr(child_type)} "
                f"minOccurs={quoteattr(min_occurs)} maxOccurs={quoteattr(max_occurs)}/>"
            )
        lines.append("    </xs:sequence>")

    for attr_name in sorted(entry["attributes"]):
        lines.extend(_attribute_lines(entry, attr_name))

    lines.append("  </xs:complexType>")
    return lines


def _attribute_lines(entry, attr_name):
    attr_entry = entry["attributes"][attr_name]
    required = attr_entry["attr_seen_count"] == entry["instance_count"]
    use = "required" if required else "optional"
    base_type = _XSD_BASE[attr_entry["type"]]

    if not attr_entry["overflowed"] and attr_entry["values"]:
        lines = [f"    <xs:attribute name={quoteattr(attr_name)} use={quoteattr(use)}>"]
        lines.append("      <xs:simpleType>")
        lines.append(f"        <xs:restriction base={quoteattr(base_type)}>")
        labels = attr_entry.get("labels", {})
        for value in sorted(attr_entry["values"]):
            label = labels.get(value)
            if label:
                lines.append(f"          <xs:enumeration value={quoteattr(value)}>")
                lines.append("            <xs:annotation>")
                lines.append(f"              <xs:documentation>{escape(label)}</xs:documentation>")
                lines.append("            </xs:annotation>")
                lines.append("          </xs:enumeration>")
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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/schema_learning/test_xsd_gen.py -v`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/schema_learning/xsd_gen.py tests/schema_learning/test_xsd_gen.py
git commit -m "feat(schema-learning): vendor xsd_gen.py with xs:documentation emission for labeled values"
```

---

## Task 4: Add `storage.py` and the `defusedxml` dependency

New module resolving per-user file paths for `schema_model.json` and `schema.xsd`, using `QStandardPaths.AppDataLocation`, with an optional `base_dir` override for test isolation. Also declares `defusedxml` as a project dependency (required transitively by `schema_learning/parser.py`, and used directly by these new tests).

**Files:**
- Modify: `pyproject.toml`
- Create: `pgtp_editor/schema_learning/storage.py`
- Test: `tests/schema_learning/test_storage.py`

- [ ] **Step 1: Add `defusedxml` to `pyproject.toml`'s dependencies**

Read the current `dependencies` list in `pyproject.toml`:

```toml
dependencies = [
    "PySide6>=6.6",
    "lxml>=5.0",
]
```

Change it to:

```toml
dependencies = [
    "PySide6>=6.6",
    "lxml>=5.0",
    "defusedxml>=0.7",
]
```

- [ ] **Step 2: Write the failing tests for `storage.py`**

Create `tests/schema_learning/test_storage.py`:

```python
from pathlib import Path

from pgtp_editor.schema_learning.storage import schema_model_path, schema_xsd_path


def test_schema_model_path_uses_given_base_dir(tmp_path):
    result = schema_model_path(tmp_path)
    assert result == tmp_path / "schema_model.json"


def test_schema_xsd_path_uses_given_base_dir(tmp_path):
    result = schema_xsd_path(tmp_path)
    assert result == tmp_path / "schema.xsd"


def test_schema_model_path_defaults_to_real_app_data_location_when_no_base_dir():
    result = schema_model_path()
    assert result.name == "schema_model.json"
    assert isinstance(result, Path)


def test_schema_xsd_path_defaults_to_real_app_data_location_when_no_base_dir():
    result = schema_xsd_path()
    assert result.name == "schema.xsd"
    assert isinstance(result, Path)


def test_schema_model_path_and_schema_xsd_path_share_the_same_directory(tmp_path):
    model_path = schema_model_path(tmp_path)
    xsd_path = schema_xsd_path(tmp_path)
    assert model_path.parent == xsd_path.parent == tmp_path
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/schema_learning/test_storage.py -v`
Expected: FAIL / collection error — `ModuleNotFoundError: No module named 'pgtp_editor.schema_learning.storage'`

- [ ] **Step 4: Create `storage.py`**

Create `pgtp_editor/schema_learning/storage.py` with this exact content:

```python
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_MODEL_FILENAME = "schema_model.json"
_XSD_FILENAME = "schema.xsd"


def _app_data_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


def schema_model_path(base_dir: Path | None = None) -> Path:
    return (base_dir or _app_data_dir()) / _MODEL_FILENAME


def schema_xsd_path(base_dir: Path | None = None) -> Path:
    return (base_dir or _app_data_dir()) / _XSD_FILENAME
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/schema_learning/test_storage.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run the full `schema_learning` test suite so far to confirm nothing regressed**

Run: `pytest tests/schema_learning -v`
Expected: PASS (all tests from Tasks 1–4)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml pgtp_editor/schema_learning/storage.py tests/schema_learning/test_storage.py
git commit -m "feat(schema-learning): add storage.py path helpers and defusedxml dependency"
```

---

## Task 5: Wire `MainWindow` — constructor override and `_enrich_schema_from_file`/`_report_schema_events`

Extends `pgtp_editor/ui/main_window.py` with the new imports, an optional `schema_storage_dir` constructor parameter, the two new methods, and the one-line call at the end of `open_project_file`'s success path. This task is split into two steps of wiring (constructor + methods first, then the call site) so each piece is independently testable, per bite-sized TDD granularity.

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Test: `tests/ui/test_schema_learning_wiring.py`

- [ ] **Step 1: Write the failing test for the `schema_storage_dir` constructor parameter and `_enrich_schema_from_file` on success**

Create `tests/ui/test_schema_learning_wiring.py`:

```python
"""Tests for the schema-learning auto-enrich wiring on MainWindow.open_project_file.

These use MainWindow(schema_storage_dir=tmp_path) so the schema model/XSD
are written to an isolated per-test directory, never the real user's
AppData location.
"""
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import schema_model_path, schema_xsd_path
from pgtp_editor.ui.main_window import MainWindow

VALID_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
        <EventHandlers>
          <OnPreparePage>echo 'hi';</OnPreparePage>
        </EventHandlers>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""

MALFORMED_PGTP = "<Project><Presentation><Pages><Page></Pages></Presentation></Project>"


def test_open_project_file_creates_schema_model_and_xsd_on_success(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    project_path = tmp_path / "valid.pgtp"
    project_path.write_text(VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(project_path))

    model_path = schema_model_path(storage_dir)
    xsd_path = schema_xsd_path(storage_dir)
    assert model_path.exists()
    assert xsd_path.exists()

    model = Model.load(model_path)
    assert "Project" in model.paths


def test_open_project_file_appends_audit_entries_on_success(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    project_path = tmp_path / "valid.pgtp"
    project_path.write_text(VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(project_path))

    assert window.audit_panel.count() >= 1
    first_entry_text = window.audit_panel.item(0).text()
    assert first_entry_text.startswith("[Schema]")


def test_second_open_of_same_shape_file_reuses_and_grows_existing_model(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    project_path = tmp_path / "valid.pgtp"
    project_path.write_text(VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(project_path))
    model_path = schema_model_path(storage_dir)
    first_mtime_ns = model_path.stat().st_mtime_ns

    window.audit_panel.clear()
    window.open_project_file(str(project_path))

    # Re-opening the identical file merges into the *same* model file
    # (still exists, was rewritten) rather than creating a second one.
    assert model_path.exists()
    assert model_path.stat().st_mtime_ns >= first_mtime_ns
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/ui/test_schema_learning_wiring.py -v`
Expected: FAIL — `TypeError: MainWindow.__init__() got an unexpected keyword argument 'schema_storage_dir'`

- [ ] **Step 3: Add the imports, constructor parameter, and the two new methods to `main_window.py`**

In `pgtp_editor/ui/main_window.py`, change the import block at the top of the file from:

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from pgtp_editor.diff.differ import compare_block, diff_project
from pgtp_editor.diff.resolve import ResolutionError, resolve_path
from pgtp_editor.model.parser import load_project
from pgtp_editor.ui._stub_action import add_stub_action
from pgtp_editor.ui.about import show_about_dialog
from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.project_tree import ProjectTreePanel
```

to:

```python
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from pgtp_editor.diff.differ import compare_block, diff_project
from pgtp_editor.diff.resolve import ResolutionError, resolve_path
from pgtp_editor.model.parser import load_project
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.parser import walk_document
from pgtp_editor.schema_learning.storage import schema_model_path, schema_xsd_path
from pgtp_editor.schema_learning.xsd_gen import generate_xsd
from pgtp_editor.ui._stub_action import add_stub_action
from pgtp_editor.ui.about import show_about_dialog
from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.project_tree import ProjectTreePanel


_SCHEMA_REPORT_TEMPLATES = {
    "new_element": "[Schema] NEW ELEMENT: {path} (first seen in {source})",
    "new_attribute": "[Schema] NEW ATTRIBUTE: {path}@{attr} (first seen in {source})",
    "new_value": '[Schema] NEW ATTR VALUE: {path}@{attr} += "{value}" (from {source})',
    "enum_overflow": "[Schema] ENUM OVERFLOWED: {path}@{attr} now free-form string (from {source})",
    "now_optional": "[Schema] NOW OPTIONAL: {path}@{attr} (previously required, from {source})",
}
```

Then change the `MainWindow.__init__` signature and body from:

```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PGTP Editor")
        self.resize(1400, 900)
```

to:

```python
class MainWindow(QMainWindow):
    def __init__(self, schema_storage_dir: Path | None = None):
        super().__init__()
        self._schema_storage_dir = schema_storage_dir
        self.setWindowTitle("PGTP Editor")
        self.resize(1400, 900)
```

Then add the two new methods immediately after `open_project_file` (i.e. directly before `_compare_merge_two_files`), leaving `open_project_file` itself unchanged for this step:

```python
    def _enrich_schema_from_file(self, path):
        try:
            model_path = schema_model_path(self._schema_storage_dir)
            xsd_path = schema_xsd_path(self._schema_storage_dir)
            model_path.parent.mkdir(parents=True, exist_ok=True)

            if model_path.exists():
                model = Model.load(model_path)
            else:
                model = Model()

            events = []
            for elem_path, attrib, child_tag_counts, has_text in walk_document(path):
                events.extend(model.merge_element(elem_path, attrib, child_tag_counts, has_text))

            model.save(model_path)
            xsd_path.write_text(generate_xsd(model), encoding="utf-8")

            self._report_schema_events(events, path)
        except Exception as exc:
            self.audit_panel.addItem(f"[Schema] Could not update schema knowledge: {exc}")

    def _report_schema_events(self, events, source_path):
        source_name = Path(source_path).name
        if len(events) > 20:
            self.audit_panel.addItem(f"[Schema] Learned {len(events)} new structural facts from {source_name}")
            return
        for event in events:
            template = _SCHEMA_REPORT_TEMPLATES[event["kind"]]
            self.audit_panel.addItem(template.format(source=source_name, **event))
```

- [ ] **Step 4: Run the test to verify the constructor and methods exist but enrichment still isn't wired**

Run: `pytest tests/ui/test_schema_learning_wiring.py -v`
Expected: FAIL — the constructor no longer raises `TypeError`, but `test_open_project_file_creates_schema_model_and_xsd_on_success` and `test_open_project_file_appends_audit_entries_on_success` fail with `assert False` (the model/xsd files don't exist yet, the audit panel is still empty) because `open_project_file` does not call `_enrich_schema_from_file` yet.

- [ ] **Step 5: Add the one-line call to `open_project_file`'s success path**

In `pgtp_editor/ui/main_window.py`, change the tail of `open_project_file` from:

```python
        self.project_tree.populate_from_project(project)
        self._current_project = project
        self._current_project_path = path
        self.statusBar().showMessage(f"Opened: {path}", 5000)
```

to:

```python
        self.project_tree.populate_from_project(project)
        self._current_project = project
        self._current_project_path = path
        self.statusBar().showMessage(f"Opened: {path}", 5000)
        self._enrich_schema_from_file(path)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/ui/test_schema_learning_wiring.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Run the full existing `tests/ui` suite to confirm no regressions**

Run: `pytest tests/ui -v`
Expected: PASS (all pre-existing UI tests, including every test in `tests/ui/test_open_project.py`, continue to pass unchanged)

- [ ] **Step 8: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_schema_learning_wiring.py
git commit -m "feat(ui): wire File -> Open to auto-enrich the local schema model"
```

---

## Task 6: UI test — parse failure never touches the schema model files

Confirms the ordering guarantee from the design spec: `_enrich_schema_from_file` is only ever reached from `open_project_file`'s success path, never from its `except` branch. Covers both the "file never existed" case and the "pre-seeded model file must remain byte-for-byte unchanged" case.

**Files:**
- Modify: `tests/ui/test_schema_learning_wiring.py`

- [ ] **Step 1: Write the failing (well — currently-passing-by-accident, verify-first) tests**

Append to `tests/ui/test_schema_learning_wiring.py`:

```python
def test_parse_failure_does_not_create_schema_model_file(qtbot, tmp_path):
    from unittest.mock import patch

    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    broken_path = tmp_path / "broken.pgtp"
    broken_path.write_text(MALFORMED_PGTP, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(broken_path))

    model_path = schema_model_path(storage_dir)
    xsd_path = schema_xsd_path(storage_dir)
    assert not model_path.exists()
    assert not xsd_path.exists()


def test_parse_failure_leaves_pre_seeded_schema_model_byte_for_byte_unchanged(qtbot, tmp_path):
    from unittest.mock import patch

    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True)
    model_path = schema_model_path(storage_dir)
    seeded_content = '{\n  "paths": {}\n}'
    model_path.write_text(seeded_content, encoding="utf-8")
    mtime_before = model_path.stat().st_mtime_ns

    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    broken_path = tmp_path / "broken.pgtp"
    broken_path.write_text(MALFORMED_PGTP, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(broken_path))

    assert model_path.read_text(encoding="utf-8") == seeded_content
    assert model_path.stat().st_mtime_ns == mtime_before


def test_parse_failure_appends_no_schema_audit_entry(qtbot, tmp_path):
    from unittest.mock import patch

    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    broken_path = tmp_path / "broken.pgtp"
    broken_path.write_text(MALFORMED_PGTP, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(broken_path))

    assert window.audit_panel.count() == 0
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `pytest tests/ui/test_schema_learning_wiring.py -v`
Expected: PASS (6 tests total in this file) — these tests pass immediately given the wiring from Task 5, since `_enrich_schema_from_file` is only ever called after the `try` block's success path completes and the `except Exception as exc: ...; return` branch in `open_project_file` returns before reaching it. This step exists to make that guarantee an explicit, permanent regression test rather than an implicit property nobody checks.

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_schema_learning_wiring.py
git commit -m "test(ui): verify a parse failure never touches the schema model files"
```

---

## Task 7: Production entry point unaffected — confirm `MainWindow()` with no arguments still works

The constructor parameter added in Task 5 must remain fully optional so that whatever code constructs `MainWindow()` today (the real application entry point) needs no change. This task locates that call site and adds one explicit regression test proving the zero-argument path still resolves to the real `AppDataLocation` (rather than silently doing nothing or raising).

**Files:**
- Test: `tests/ui/test_schema_learning_wiring.py`

- [ ] **Step 1: Find the production entry point that constructs `MainWindow`**

Run: `grep -rn "MainWindow(" pgtp_editor --include=*.py`
Expected output includes a line such as `pgtp_editor/app.py:N:    window = MainWindow()` (or equivalent `main.py`), calling the constructor with no arguments. No change is needed to that call site — this step is a confirmation, not a modification, that the existing zero-argument construction remains valid after Task 5's signature change (`schema_storage_dir: Path | None = None` defaults to `None`, so old call sites are unaffected).

- [ ] **Step 2: Write the regression test for the zero-argument constructor path**

Append to `tests/ui/test_schema_learning_wiring.py`:

```python
def test_main_window_constructs_with_no_arguments_and_resolves_real_app_data_dir(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window._schema_storage_dir is None

    model_path = schema_model_path(window._schema_storage_dir)
    assert model_path.name == "schema_model.json"
    # Resolves to the real per-user AppDataLocation, not empty/relative.
    assert model_path.is_absolute()
```

- [ ] **Step 3: Run the test to verify it passes**

Run: `pytest tests/ui/test_schema_learning_wiring.py -v`
Expected: PASS (7 tests total in this file)

- [ ] **Step 4: Commit**

```bash
git add tests/ui/test_schema_learning_wiring.py
git commit -m "test(ui): confirm MainWindow() with no arguments still resolves the real AppData path"
```

---

## Task 8: Integration test against the two real sample files

Runs the enrichment path (`walk_document` + `Model.merge_element`, no UI involved) end-to-end against both real `.pgtp` sample files already present in this worktree's `sample/` directory, feeding both into one shared `Model` instance sequentially — mirroring a user opening two files in a row.

**Files:**
- Test: `tests/schema_learning/test_real_samples_integration.py`

- [ ] **Step 1: Confirm the sample files exist at the expected paths**

Run: `python -c "from pathlib import Path; p = Path('sample'); print(sorted(f.name for f in p.glob('*.pgtp')))"`
Expected: `['Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp', 'dev_Ferrara.pgtp']`

- [ ] **Step 2: Write the integration test**

Create `tests/schema_learning/test_real_samples_integration.py`:

```python
"""Integration test running the schema-learning engine end-to-end against
the two real .pgtp sample files checked into this worktree's sample/
directory (gitignored, not tracked, but present on disk for local dev and
CI alike).

This drives walk_document + Model.merge_element directly — no UI, no
MainWindow — mirroring exactly what _enrich_schema_from_file does inside
pgtp_editor/ui/main_window.py.
"""
from pathlib import Path

import defusedxml.ElementTree as ET

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.parser import walk_document
from pgtp_editor.schema_learning.xsd_gen import generate_xsd

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"
SAMPLE_FILES = [
    SAMPLE_DIR / "dev_Ferrara.pgtp",
    SAMPLE_DIR / "Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp",
]


def test_both_real_sample_files_merge_into_one_model_without_raising():
    for path in SAMPLE_FILES:
        assert path.exists(), f"expected sample file missing: {path}"

    model = Model()
    for path in SAMPLE_FILES:
        for elem_path, attrib, child_tag_counts, has_text in walk_document(str(path)):
            model.merge_element(elem_path, attrib, child_tag_counts, has_text)

    assert len(model.paths) > 10


def test_generated_xsd_from_real_samples_is_well_formed_xml():
    model = Model()
    for path in SAMPLE_FILES:
        for elem_path, attrib, child_tag_counts, has_text in walk_document(str(path)):
            model.merge_element(elem_path, attrib, child_tag_counts, has_text)

    xsd_text = generate_xsd(model)

    ET.fromstring(xsd_text)  # raises if malformed
```

- [ ] **Step 3: Run the test to verify it passes**

Run: `pytest tests/schema_learning/test_real_samples_integration.py -v`
Expected: PASS (2 tests). If either sample file's structure trips an unanticipated parsing edge case, this is the point in the plan where that would surface — investigate via `systematic-debugging` rather than loosening the assertions.

- [ ] **Step 4: Run the entire test suite (existing + all new) to confirm no regressions anywhere**

Run: `pytest -v`
Expected: PASS — every pre-existing test in `tests/model`, `tests/diff`, `tests/ui` continues to pass, plus all new tests under `tests/schema_learning/` and the schema-learning additions to `tests/ui/test_schema_learning_wiring.py`.

- [ ] **Step 5: Commit**

```bash
git add tests/schema_learning/test_real_samples_integration.py
git commit -m "test(schema-learning): add end-to-end integration test against real sample files"
```

---

## Summary of files touched by this plan

**Created:**
- `pgtp_editor/schema_learning/__init__.py`
- `pgtp_editor/schema_learning/types.py`
- `pgtp_editor/schema_learning/parser.py`
- `pgtp_editor/schema_learning/model.py`
- `pgtp_editor/schema_learning/xsd_gen.py`
- `pgtp_editor/schema_learning/storage.py`
- `tests/schema_learning/__init__.py`
- `tests/schema_learning/test_types.py`
- `tests/schema_learning/test_parser.py`
- `tests/schema_learning/test_model.py`
- `tests/schema_learning/test_xsd_gen.py`
- `tests/schema_learning/test_storage.py`
- `tests/schema_learning/test_real_samples_integration.py`
- `tests/ui/test_schema_learning_wiring.py`

**Modified:**
- `pyproject.toml` (added `"defusedxml>=0.7"` to `dependencies`)
- `pgtp_editor/ui/main_window.py` (new imports, `_SCHEMA_REPORT_TEMPLATES`, `schema_storage_dir` constructor parameter, `_enrich_schema_from_file`, `_report_schema_events`, one-line call in `open_project_file`)

**Explicitly not touched (per spec §2.2, confirmed in Task 7):**
- `pgtp_editor/model/parser.py`, `pgtp_editor/model/nodes.py` — the existing lxml-based project parser used for the Project Tree/diffing, entirely independent of this sub-project.
- `_compare_merge_two_files`, `_compare_page_with`, `_compare_detail_with` in `pgtp_editor/ui/main_window.py` — these call `load_project` directly for Diff/Merge file pickers and deliberately do not trigger schema enrichment.
- `pgtp_analytics/pgtp_schema/cli.py` — not vendored; the original standalone tool's CLI remains untouched in its own repo.
