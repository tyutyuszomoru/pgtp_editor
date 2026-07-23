# Annotate-at-Cursor Labeling + Team Schema-Model Sharing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unusable Annotate Schema Values dialog with an in-editor annotation popover (label / bit-flags / note / kind at the cursor, with unlabeled-value underlines and next-unlabeled navigation), and add team sharing of the schema model through a dedicated git repo with in-app semantic merge.

**Architecture:** All annotation data stays in the labeler-owned fields of the per-user `schema_model.json` (`labels`, `kind`, plus new `notes` and `enum_mode`); the XSD remains a generated artifact. Pure logic (bit-flag derivation, unlabeled-span discovery, model merge, git transport) lives in Qt-free modules; the XML editor renders underlines and emits an annotate request; MainWindow owns the popover, persistence, and the three sync menu actions (network work off-thread via the existing `run_async` seam).

**Tech Stack:** Python 3.12, PySide6 (QPlainTextEdit extra selections, QFrame popup), pytest + pytest-qt offscreen, git CLI via `subprocess` (injectable runner).

**Spec:** `docs/superpowers/CONSOLIDATED_SPEC.md` §11 (plus §22 menu table, §23 shortcuts).

## Global Constraints

- Test command: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest <paths> -q` (PowerShell). Use the system `python` — NOT the repo `venv\`.
- Every new `.py` file starts with the standard GPL header — copy lines 1–14 verbatim from `pgtp_editor/schema_learning/model.py`.
- Tests mirror the package layout: `pgtp_editor/<area>/foo.py` → `tests/<area>/test_foo.py`.
- Never let a test reach an un-patched modal Qt call (`QDialog.exec`, `QMessageBox.*`, `QFileDialog.*`) — monkeypatch them.
- The Schema Learning Engine (`schema_learning/model.py` `merge_element`) never reads or clears labeler-owned fields (`labels`, `kind`, `notes`, `enum_mode`); readers always use `.get(...)` because engine-created entries lack the new keys.
- `schema.xsd` is a generated artifact: every code path that mutates the model and saves it also regenerates the XSD.
- Qt-free modules (`schema_learning/*.py` except imports of `QStandardPaths` in `storage.py`) must not import QtWidgets/QtGui.
- Commit after every green task; message style: `feat:`/`refactor:`/`test:` prefix, imperative mood.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `pgtp_editor/schema_learning/settings_index.py` | Modify | + `derived_bitflag_label`, `effective_labels`, `value_note`; `known_values`/`enum_hint` use union + effective labels + notes |
| `pgtp_editor/schema_learning/xsd_gen.py` | Modify | derived labels + notes in `xs:documentation`, union enumeration |
| `pgtp_editor/schema_learning/merge.py` | Create | Qt-free model-to-model semantic merge with `Conflict` records |
| `pgtp_editor/schema_learning/sync.py` | Create | Qt-free git transport (clone/pull/publish/fetch/push, injectable runner) |
| `pgtp_editor/schema_learning/storage.py` | Modify | + `team_repo_dir()` |
| `pgtp_editor/ui/xml_editor.py` | Modify | + `attribute_value_at_position`, `unlabeled_value_spans` (pure); underlines, `goto_next_unlabeled_value`, `request_annotate_at_cursor`, context-menu action |
| `pgtp_editor/ui/annotate_popover.py` | Create | Compact popup: Label / Bit-flags / Note / Kind, committed(dict)/cancelled signals |
| `pgtp_editor/ui/team_sync_dialog.py` | Create | QSettings-backed repo URL + key path config (`load_sync_config`) + settings dialog |
| `pgtp_editor/ui/merge_conflicts_dialog.py` | Create | Table of merge conflicts, per-row keep-master/use-incoming choice |
| `pgtp_editor/ui/main_window.py` | Modify | Schema menu rework, popover wiring + persistence, Publish/Fetch/Merge actions |
| `pgtp_editor/ui/annotate_schema_values_dialog.py` | **Delete** | superseded |
| `tests/ui/test_annotate_schema_values_dialog.py` | **Delete** | superseded |

---

### Task 1: Bit-flag derivation + effective labels (pure)

**Files:**
- Modify: `pgtp_editor/schema_learning/settings_index.py`
- Test: `tests/schema_learning/test_settings_index.py` (append)

**Interfaces:**
- Consumes: attribute-entry dict shape `{type, values, overflowed, attr_seen_count, labels, [kind], [notes], [enum_mode]}`.
- Produces (used by Tasks 2, 3, 5):
  - `derived_bitflag_label(value: str, labels: dict[str, str]) -> str | None`
  - `effective_labels(entry: dict) -> dict[str, str]` — explicit labels, plus derived composites when `entry.get("enum_mode") == "bitflags"`.
  - `value_note(entry: dict, value: str) -> str | None`

- [ ] **Step 1: Write the failing tests** — append to `tests/schema_learning/test_settings_index.py`:

```python
from pgtp_editor.schema_learning.settings_index import (
    derived_bitflag_label,
    effective_labels,
    value_note,
)


def _entry(values, labels=None, **extra):
    entry = {
        "type": "integer",
        "values": values,
        "overflowed": values is None,
        "attr_seen_count": 1,
        "labels": labels or {},
    }
    entry.update(extra)
    return entry


def test_derived_bitflag_label_composes_atomic_labels():
    labels = {"1": "A", "2": "B", "4": "C"}
    assert derived_bitflag_label("3", labels) == "A+B"
    assert derived_bitflag_label("5", labels) == "A+C"
    assert derived_bitflag_label("6", labels) == "B+C"
    assert derived_bitflag_label("7", labels) == "A+B+C"


def test_derived_bitflag_label_missing_bit_returns_none():
    assert derived_bitflag_label("3", {"1": "A"}) is None


def test_derived_bitflag_label_rejects_non_numeric_and_nonpositive():
    assert derived_bitflag_label("x", {"1": "A"}) is None
    assert derived_bitflag_label("0", {"1": "A"}) is None
    assert derived_bitflag_label("-2", {"2": "B"}) is None


def test_effective_labels_plain_mode_returns_labels_copy():
    entry = _entry(["1", "2"], labels={"1": "A"})
    result = effective_labels(entry)
    assert result == {"1": "A"}
    result["1"] = "mutated"
    assert entry["labels"]["1"] == "A"  # a copy, not the stored dict


def test_effective_labels_bitflags_derives_composites_explicit_wins():
    entry = _entry(
        ["1", "2", "3", "5"],
        labels={"1": "A", "2": "B", "5": "custom"},
        enum_mode="bitflags",
    )
    assert effective_labels(entry) == {
        "1": "A",
        "2": "B",
        "3": "A+B",       # derived
        "5": "custom",    # explicit overrides derived "A+?" (4 unlabeled anyway)
    }


def test_effective_labels_bitflags_overflowed_uses_label_keys():
    entry = _entry(None, labels={"1": "A", "2": "B"}, enum_mode="bitflags")
    assert effective_labels(entry) == {"1": "A", "2": "B"}


def test_value_note_reads_notes_dict():
    entry = _entry(["4"], notes={"4": "enables the <Watermark> child tag"})
    assert value_note(entry, "4") == "enables the <Watermark> child tag"
    assert value_note(entry, "1") is None
    assert value_note(_entry(["4"]), "4") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\schema_learning\test_settings_index.py -q`
Expected: FAIL — `ImportError: cannot import name 'derived_bitflag_label'`

- [ ] **Step 3: Implement** — add to `pgtp_editor/schema_learning/settings_index.py` (after `attribute_kind`), and update the module docstring's stale reference to `pgtp_editor.ui.annotate_schema_values_dialog` to say "the annotation popover (`pgtp_editor.ui.annotate_popover`, wired via MainWindow)":

```python
def derived_bitflag_label(value, labels):
    """Derived display label for a bit-flag composite ``value``.

    ``labels`` maps value-strings to labels; only the atomic power-of-two
    bits need labels (1, 2, 4, 8, ...). The composite's label is the '+'-join
    of its set bits' labels in ascending bit order (5 -> "A+C" from 1="A",
    4="C"). Returns None when ``value`` is not a positive integer or any set
    bit lacks a label — callers then fall back to showing the bare value.
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    parts = []
    bit = 1
    remaining = number
    while remaining:
        if remaining & 1:
            label = labels.get(str(bit))
            if label is None:
                return None
            parts.append(label)
        remaining >>= 1
        bit <<= 1
    return "+".join(parts)


def effective_labels(entry):
    """The labels to DISPLAY for an attribute entry: a copy of the explicit
    ``labels`` plus, when ``enum_mode == "bitflags"``, derived composite
    labels for every known value (explicit labels always win). The value
    universe is the union of engine-observed ``values`` and label keys, so
    derivation works even after enum overflow (``values`` is None)."""
    labels = entry.get("labels") or {}
    if entry.get("enum_mode") != "bitflags":
        return dict(labels)
    universe = set(entry.get("values") or []) | set(labels)
    result = {}
    for value in universe:
        explicit = labels.get(value)
        if explicit is not None:
            result[value] = explicit
            continue
        derived = derived_bitflag_label(value, labels)
        if derived is not None:
            result[value] = derived
    return result


def value_note(entry, value):
    """The labeler's free-text note for ``value`` (structural consequences,
    e.g. "enables the <Watermark> child tag"), or None."""
    return (entry.get("notes") or {}).get(value)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\schema_learning\test_settings_index.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/schema_learning/settings_index.py tests/schema_learning/test_settings_index.py
git commit -m "feat: bit-flag label derivation + effective_labels/value_note helpers"
```

---

### Task 2: `known_values` union + `enum_hint` notes

**Files:**
- Modify: `pgtp_editor/schema_learning/settings_index.py:46-76` (`enum_hint`) and `:93-106` (`known_values`)
- Test: `tests/schema_learning/test_settings_index.py` (append + adjust)

**Interfaces:**
- Consumes: Task 1's `effective_labels`.
- Produces: unchanged signatures — `known_values(model, tag_chain, attr) -> list[tuple[str, str | None]]`, `enum_hint(model, tag_chain, attr) -> str | None`. NEW SEMANTICS: value universe = union of `values` and explicit `labels` keys; labels come from `effective_labels`; `enum_hint` appends ` (note)` per value.

- [ ] **Step 1: Write the failing tests** — append (a `_model_for(entry)` helper may already exist under another name; reuse it if so, else add):

```python
from pgtp_editor.schema_learning.model import Model


def _model_for(entry, chain="Root/Item", attr="mode"):
    model = Model()
    model.paths = {
        chain: {
            "attributes": {attr: entry},
            "children": {},
            "instance_count": 1,
            "order": [],
            "order_stable": True,
            "has_text": False,
        }
    }
    return model


def test_known_values_includes_labeled_but_unobserved_values():
    entry = _entry(["1"], labels={"1": "A", "9": "special"})
    model = _model_for(entry)
    assert known_values(model, "Root/Item", "mode") == [
        ("1", "A"),
        ("9", "special"),
    ]


def test_known_values_overflowed_offers_label_keys():
    entry = _entry(None, labels={"1": "A"})
    model = _model_for(entry)
    assert known_values(model, "Root/Item", "mode") == [("1", "A")]


def test_known_values_overflowed_without_labels_is_empty():
    entry = _entry(None)
    model = _model_for(entry)
    assert known_values(model, "Root/Item", "mode") == []


def test_known_values_bitflags_shows_derived_labels():
    entry = _entry(["1", "2", "3"], labels={"1": "A", "2": "B"}, enum_mode="bitflags")
    model = _model_for(entry)
    assert known_values(model, "Root/Item", "mode") == [
        ("1", "A"),
        ("2", "B"),
        ("3", "A+B"),
    ]


def test_enum_hint_appends_notes_and_derived_labels():
    entry = _entry(
        ["1", "2", "3"],
        labels={"1": "A", "2": "B"},
        notes={"3": "adds the <Extra> tag"},
        enum_mode="bitflags",
        kind="setting",
    )
    model = _model_for(entry)
    assert enum_hint(model, "Root/Item", "mode") == (
        "mode — 1 = A · 2 = B · 3 = A+B (adds the <Extra> tag)"
    )
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\schema_learning\test_settings_index.py -q`
Expected: the five new tests FAIL (old semantics); pre-existing tests pass.

- [ ] **Step 3: Implement** — replace the bodies:

```python
def known_values(model, tag_chain, attr) -> list[tuple[str, str | None]]:
    """Sorted ``(value, label)`` pairs for an attribute at ``tag_chain``.

    The value universe is the UNION of engine-observed ``values`` and
    labeler-added ``labels`` keys — a value labeled before being observed,
    or dropped from ``values`` by enum overflow, still completes. Labels are
    the effective (explicit + derived bit-flag) labels. Returns ``[]`` when
    the attribute is unknown at the path or the universe is empty. Not
    filtered by kind."""
    entry = model.paths.get(tag_chain, {}).get("attributes", {}).get(attr)
    if entry is None:
        return []
    universe = set(entry.get("values") or []) | set(entry.get("labels") or {})
    if not universe:
        return []
    labels = effective_labels(entry)
    return [(value, labels.get(value)) for value in sorted(universe)]
```

and in `enum_hint`, replace everything from `labels = entry.get("labels") or {}` to the end with:

```python
    labels = entry.get("labels") or {}
    if not labels and not is_enum_candidate(entry):
        return None

    display = effective_labels(entry)
    notes = entry.get("notes") or {}
    universe = set(entry.get("values") or []) | set(labels)
    parts = []
    for value in sorted(universe):
        label = display.get(value)
        part = f"{value} = {label}" if label else f"{value}"
        note = notes.get(value)
        if note:
            part = f"{part} ({note})"
        parts.append(part)
    return f"{attr} — " + " · ".join(parts)
```

- [ ] **Step 4: Run the area tests; fix pre-existing expectations**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\schema_learning\ tests\ui\test_xml_editor_completion.py tests\ui\test_xml_editor_hover.py -q`
Expected: PASS. If any pre-existing test asserts the OLD `overflowed → []` behavior of `known_values` while labels exist, update that test to the new union semantics (this is the spec'd behavior change recorded in the Supersession Ledger).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/schema_learning/settings_index.py tests/schema_learning/test_settings_index.py tests/ui/test_xml_editor_completion.py tests/ui/test_xml_editor_hover.py
git commit -m "feat: known_values/enum_hint use value union, derived labels, notes"
```

---

### Task 3: XSD generation — derived labels + notes

**Files:**
- Modify: `pgtp_editor/schema_learning/xsd_gen.py:81-110` (`_attribute_lines`)
- Test: `tests/schema_learning/test_xsd_gen.py` (append)

**Interfaces:**
- Consumes: `effective_labels` from `settings_index` (same package — import at top: `from .settings_index import effective_labels`).
- Produces: `<xs:documentation>` text per enumeration value: `label`, `note`, or `label — note`; enumeration list = union of observed values and explicit label keys (non-overflowed entries only).

- [ ] **Step 1: Write the failing tests** — append to `tests/schema_learning/test_xsd_gen.py` (reuse the file's existing model-building helper if present; otherwise build a `Model` and assign `paths` as in Task 2's `_model_for`):

```python
def test_xsd_documentation_includes_derived_bitflag_labels_and_notes():
    entry = {
        "type": "integer",
        "values": ["1", "2", "3"],
        "overflowed": False,
        "attr_seen_count": 1,
        "labels": {"1": "A", "2": "B"},
        "notes": {"3": "adds the <Extra> tag"},
        "enum_mode": "bitflags",
    }
    model = Model()
    model.paths = {
        "Root": {
            "attributes": {"mode": entry},
            "children": {},
            "instance_count": 1,
            "order": [],
            "order_stable": True,
            "has_text": False,
        }
    }
    xsd = generate_xsd(model)
    assert "<xs:documentation>A</xs:documentation>" in xsd
    assert "<xs:documentation>A+B — adds the &lt;Extra&gt; tag</xs:documentation>" in xsd


def test_xsd_enumerates_labeled_but_unobserved_values():
    entry = {
        "type": "integer",
        "values": ["1"],
        "overflowed": False,
        "attr_seen_count": 1,
        "labels": {"9": "special"},
    }
    model = Model()
    model.paths = {
        "Root": {
            "attributes": {"mode": entry},
            "children": {},
            "instance_count": 1,
            "order": [],
            "order_stable": True,
            "has_text": False,
        }
    }
    xsd = generate_xsd(model)
    assert '<xs:enumeration value="9">' in xsd
    assert "<xs:documentation>special</xs:documentation>" in xsd
```

- [ ] **Step 2: Run to verify failure**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\schema_learning\test_xsd_gen.py -q`
Expected: the two new tests FAIL.

- [ ] **Step 3: Implement** — add `from .settings_index import effective_labels` at the top of `xsd_gen.py`, add the helper, and rework `_attribute_lines`:

```python
def _documentation_text(label, note):
    if label and note:
        return f"{label} — {note}"
    return label or note or None


def _attribute_lines(entry, attr_name):
    attr_entry = entry["attributes"][attr_name]
    required = attr_entry["attr_seen_count"] == entry["instance_count"]
    use = "required" if required else "optional"
    base_type = _XSD_BASE[attr_entry["type"]]

    universe = sorted(
        set(attr_entry.get("values") or []) | set(attr_entry.get("labels") or {})
    )
    if not attr_entry["overflowed"] and universe:
        labels = effective_labels(attr_entry)
        notes = attr_entry.get("notes") or {}
        lines = [f"    <xs:attribute name={quoteattr(attr_name)} use={quoteattr(use)}>"]
        lines.append("      <xs:simpleType>")
        lines.append(f"        <xs:restriction base={quoteattr(base_type)}>")
        for value in universe:
            doc = _documentation_text(labels.get(value), notes.get(value))
            if doc:
                lines.append(f"          <xs:enumeration value={quoteattr(value)}>")
                lines.append("            <xs:annotation>")
                lines.append(f"              <xs:documentation>{escape(doc)}</xs:documentation>")
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

- [ ] **Step 4: Run to verify pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\schema_learning\test_xsd_gen.py tests\schema_learning\ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/schema_learning/xsd_gen.py tests/schema_learning/test_xsd_gen.py
git commit -m "feat: XSD documentation carries derived bitflag labels and notes"
```

---

### Task 4: `attribute_value_at_position` (pure resolver)

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py:81-134` (`attribute_at_position`), `:230-244` (`_attribute_name_at`)
- Test: `tests/ui/test_xml_editor_annotate.py` (create)

**Interfaces:**
- Produces (used by Tasks 5, 7): `attribute_value_at_position(text: str, pos: int) -> tuple[str, str, str] | None` — `(tag_chain, attr, value)` with `value` unquoted; None under the same conditions as `attribute_at_position`. `attribute_at_position` keeps its exact contract (now delegates).

- [ ] **Step 1: Write the failing tests** — create `tests/ui/test_xml_editor_annotate.py` (GPL header, then):

```python
from pgtp_editor.ui.xml_editor import (
    attribute_at_position,
    attribute_value_at_position,
)

_XML = '<Root><Item mode="4" caption="hi &gt; there"/></Root>'


def test_resolves_value_and_chain_on_value():
    pos = _XML.index('"4"') + 1
    assert attribute_value_at_position(_XML, pos) == ("Root/Item", "mode", "4")


def test_resolves_on_attribute_name_token():
    pos = _XML.index("mode")
    assert attribute_value_at_position(_XML, pos) == ("Root/Item", "mode", "4")


def test_none_outside_opening_tags():
    assert attribute_value_at_position(_XML, _XML.index("</Root>") + 2) is None
    assert attribute_value_at_position(_XML, _XML.index("<Root>") + 1) is None


def test_attribute_at_position_still_returns_pair():
    pos = _XML.index('"4"') + 1
    assert attribute_at_position(_XML, pos) == ("Root/Item", "mode")
```

- [ ] **Step 2: Run to verify failure**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_xml_editor_annotate.py -q`
Expected: FAIL — `ImportError: cannot import name 'attribute_value_at_position'`

- [ ] **Step 3: Implement.** Rename `_attribute_name_at` → `_attribute_pair_at`, returning the pair; the value is `match.group(2)` minus its surrounding quote characters:

```python
def _attribute_pair_at(text: str, open_start: int, open_end: int, pos: int):
    """Return ``(name, value)`` (value unquoted) for the attribute whose
    name-token or quoted value contains ``pos`` within the opening tag
    spanning ``[open_start, open_end)``, or ``None`` if ``pos`` is over the
    tag name, in an inter-token gap, or on the tag delimiters."""
    tag_text = text[open_start:open_end]
    offset = pos - open_start
    for match in _ATTR_PAIR_RE.finditer(tag_text):
        on_name = match.start(1) <= offset < match.end(1)
        on_value = match.start(2) <= offset < match.end(2)
        if on_name or on_value:
            return match.group(1), match.group(2)[1:-1]
    return None
```

Then rewrite `attribute_at_position` as a thin delegate and put its old body (with `_attribute_pair_at`) into the new function:

```python
def attribute_at_position(text: str, pos: int):
    """Resolve a document character position to ``(tag_chain, attr)`` —
    see attribute_value_at_position, which this delegates to."""
    resolved = attribute_value_at_position(text, pos)
    if resolved is None:
        return None
    tag_chain, attr, _value = resolved
    return tag_chain, attr


def attribute_value_at_position(text: str, pos: int):
    """Resolve a document character position to ``(tag_chain, attr, value)``
    when it falls on an attribute (name token or quoted value) inside an
    *opening* tag; otherwise return ``None``. ``value`` is the attribute's
    current value with the quotes stripped. Same resolution rules and
    tag-chain construction as the original attribute_at_position."""
    spans = xml_structure.scan(text)
    containing = None
    for span in spans:
        real_open_end = _opening_tag_end(text, span.open_start)
        if real_open_end is None:
            continue
        if span.open_start <= pos < real_open_end and (
            containing is None or span.depth > containing.depth
        ):
            containing = span
            containing_open_end = real_open_end
    if containing is None:
        return None

    pair = _attribute_pair_at(text, containing.open_start, containing_open_end, pos)
    if pair is None:
        return None
    attr, value = pair

    names = [containing.name]
    walker = containing
    while walker.depth > 0:
        parent = xml_structure.parent_tag_span(spans, walker)
        if parent is None:
            break
        names.append(parent.name)
        walker = parent
    tag_chain = "/".join(reversed(names))
    return tag_chain, attr, value
```

(Keep the explanatory comments from the original `attribute_at_position` body — move them into the new function. Delete `_attribute_name_at`.)

- [ ] **Step 4: Run to verify pass (plus the hover suite that exercises `attribute_at_position`)**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_xml_editor_annotate.py tests\ui\test_xml_editor_hover.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor_annotate.py
git commit -m "feat: attribute_value_at_position resolver (chain, attr, value)"
```

---

### Task 5: Unlabeled-value underlines + Next Unlabeled Value

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py` — pure `unlabeled_value_spans` near the other module-level helpers; editor: new named selection list, refresh hook, `goto_next_unlabeled_value`
- Test: `tests/ui/test_xml_editor_annotate.py` (append)

**Interfaces:**
- Consumes: `is_enum_candidate`, `attribute_kind`, `effective_labels` (extend the existing `from pgtp_editor.schema_learning.settings_index import ...` import), cached `self._spans`/`self._spans_text`, `_make_span_cursor`, `_refresh_extra_selections`.
- Produces (used by Task 8/9): `unlabeled_value_spans(text, spans, model) -> list[tuple[int, int]]` (absolute value-text spans, quotes excluded, sorted); `XmlEditor.goto_next_unlabeled_value() -> bool`; `XmlEditor.set_schema_model` now refreshes underlines.

- [ ] **Step 1: Write the failing tests** — append to `tests/ui/test_xml_editor_annotate.py`:

```python
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.ui import xml_structure
from pgtp_editor.ui.xml_editor import XmlEditor, unlabeled_value_spans


def _entry(values, labels=None, **extra):
    entry = {
        "type": "integer",
        "values": values,
        "overflowed": values is None,
        "attr_seen_count": 1,
        "labels": labels or {},
    }
    entry.update(extra)
    return entry


def _model(paths_attrs):
    model = Model()
    model.paths = {
        chain: {
            "attributes": attrs,
            "children": {},
            "instance_count": 1,
            "order": [],
            "order_stable": True,
            "has_text": False,
        }
        for chain, attrs in paths_attrs.items()
    }
    return model


def test_unlabeled_value_spans_finds_only_unlabeled_enum_values():
    text = '<Root mode="1" mode2="2" free="x"/>'
    model = _model({
        "Root": {
            "mode": _entry(["1", "2"], labels={"1": "A"}),   # "1" labeled -> skip
            "mode2": _entry(["2"]),                          # unlabeled -> span
            # "free" not in schema -> skip
        }
    })
    spans = unlabeled_value_spans(text, xml_structure.scan(text), model)
    start = text.index('"2"') + 1
    assert spans == [(start, start + 1)]


def test_unlabeled_value_spans_skips_content_kind():
    text = '<Root caption="Hello"/>'
    model = _model({"Root": {"caption": _entry(["Hello"], kind="content")}})
    assert unlabeled_value_spans(text, xml_structure.scan(text), model) == []


def test_editor_renders_underlines_and_navigates(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1" b="2"/>')
    model = _model({"Root": {"a": _entry(["1"]), "b": _entry(["2"])}})
    editor.set_schema_model(model)
    assert len(editor._unlabeled_value_selections) == 2

    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    assert editor.goto_next_unlabeled_value() is True
    assert editor.textCursor().selectedText() == "1"
    assert editor.goto_next_unlabeled_value() is True
    assert editor.textCursor().selectedText() == "2"
    assert editor.goto_next_unlabeled_value() is True  # wraps
    assert editor.textCursor().selectedText() == "1"


def test_goto_next_unlabeled_returns_false_without_model(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1"/>')
    assert editor.goto_next_unlabeled_value() is False
```

- [ ] **Step 2: Run to verify failure**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_xml_editor_annotate.py -q`
Expected: new tests FAIL (`ImportError: cannot import name 'unlabeled_value_spans'`).

- [ ] **Step 3: Implement.**

3a. Pure function (place after `insert_attribute`); extend the settings_index import at the top of the file with `is_enum_candidate`, `attribute_kind`, `effective_labels`:

```python
def unlabeled_value_spans(text: str, spans, model) -> list[tuple[int, int]]:
    """Absolute ``(start, end)`` character spans (quotes excluded) of every
    enum-candidate attribute VALUE in ``text`` that has no effective label.
    Content-kind attributes are skipped — the labeler marked them as
    not-a-setting, so they should not nag. ``spans`` is
    ``xml_structure.scan(text)`` (pass the editor's cached scan). Sorted by
    start offset. Drives the dotted underlines and Next Unlabeled Value."""
    result = []
    label_cache: dict[int, dict] = {}
    for span in spans:
        open_end = _opening_tag_end(text, span.open_start)
        if open_end is None:
            continue
        names = [span.name]
        walker = span
        while walker.depth > 0:
            parent = xml_structure.parent_tag_span(spans, walker)
            if parent is None:
                break
            names.append(parent.name)
            walker = parent
        tag_chain = "/".join(reversed(names))
        attributes = model.paths.get(tag_chain, {}).get("attributes", {})
        if not attributes:
            continue
        tag_text = text[span.open_start:open_end]
        for match in _ATTR_PAIR_RE.finditer(tag_text):
            entry = attributes.get(match.group(1))
            if entry is None or not is_enum_candidate(entry):
                continue
            if attribute_kind(entry) == "content":
                continue
            cached = label_cache.get(id(entry))
            if cached is None:
                cached = label_cache[id(entry)] = effective_labels(entry)
            value = match.group(2)[1:-1]
            if cached.get(value) is not None:
                continue
            start = span.open_start + match.start(2) + 1
            result.append((start, start + len(value)))
    result.sort()
    return result
```

3b. Editor state — in `__init__`, right after the `_code_region_selections` block (line ~601), add:

```python
        # Dotted underlines beneath enum-candidate attribute values that have
        # no label yet — the labeler's "waiting for you" markers. Recomputed
        # from the cached structure scan on every text change and whenever a
        # fresh schema model is injected (set_schema_model). Rendered through
        # the shared extra-selections layering.
        self._unlabeled_underline_color = QColor("#b8a24e")
        self._unlabeled_value_selections: list[QTextEdit.ExtraSelection] = []
```

and register the refresh AFTER the `_rescan_structure` connection (so the span cache is fresh when we read it):

```python
        self.textChanged.connect(self._refresh_unlabeled_value_selections)
```

Add `QTextCharFormat` to the existing `PySide6.QtGui` import.

3c. Methods (near `_refresh_code_region_selections`):

```python
    def _refresh_unlabeled_value_selections(self) -> None:
        """Recompute the dotted underlines for unlabeled enum-candidate
        values from the cached scan. No model -> no underlines."""
        selections: list[QTextEdit.ExtraSelection] = []
        if self._schema_model is not None:
            for start, end in unlabeled_value_spans(
                self._spans_text, self._spans, self._schema_model
            ):
                selection = QTextEdit.ExtraSelection()
                selection.format.setUnderlineStyle(
                    QTextCharFormat.UnderlineStyle.DotLine
                )
                selection.format.setUnderlineColor(self._unlabeled_underline_color)
                selection.cursor = self._make_span_cursor(start, end)
                selections.append(selection)
        self._unlabeled_value_selections = selections
        self._refresh_extra_selections()

    def goto_next_unlabeled_value(self) -> bool:
        """Select the next unlabeled enum-candidate value after the caret
        (wrapping to the first). Returns False when there are none."""
        if self._schema_model is None:
            return False
        spans_list = unlabeled_value_spans(
            self._spans_text, self._spans, self._schema_model
        )
        if not spans_list:
            return False
        pos = self.textCursor().position()
        target = next(((s, e) for s, e in spans_list if s > pos), spans_list[0])
        cursor = self.textCursor()
        cursor.setPosition(target[0])
        cursor.setPosition(target[1], QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.centerCursor()
        return True
```

3d. `set_schema_model` (line ~1279) gains a refresh:

```python
    def set_schema_model(self, model) -> None:
        """Inject the current in-memory schema Model (or None). Passed by
        MainWindow after each enrich/annotation so hover tooltips, completion
        and the unlabeled-value underlines reflect the latest labels; None
        disables them (default)."""
        self._schema_model = model
        self._refresh_unlabeled_value_selections()
```

3e. `_refresh_extra_selections` (line ~845): add `selections.extend(self._unlabeled_value_selections)` immediately after the `self._code_region_selections` extend (underlines are char-level and never fight the background bands).

3f. `apply_theme_colors(self, light)`: alongside the other per-theme color assignments add `self._unlabeled_underline_color = QColor("#8a6d3b")` in the light branch and `QColor("#b8a24e")` in the dark branch, and call `self._refresh_unlabeled_value_selections()` where the method re-applies dependent selections.

Note the wrap-around subtlety in `goto_next_unlabeled_value`: when the caret sits exactly at a span's start, `s > pos` skips it — that is what makes repeated invocations advance instead of re-selecting (selecting a span puts the caret at its END, so the NEXT span is found; on the last span it wraps to the first).

- [ ] **Step 4: Run to verify pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_xml_editor_annotate.py tests\ui\test_xml_editor.py tests\ui\test_xml_editor_theme.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor_annotate.py
git commit -m "feat: dotted underlines + navigation for unlabeled enum values"
```

---

### Task 6: Annotation popover widget

**Files:**
- Create: `pgtp_editor/ui/annotate_popover.py`
- Test: `tests/ui/test_annotate_popover.py`

**Interfaces:**
- Produces (used by Task 8): `AnnotatePopover(tag_chain, attr, value, label="", note="", kind="unclassified", bitflags=False, parent=None)`; signals `committed = Signal(dict)` with keys `label: str, note: str, kind: str ("unclassified"|"setting"|"content"), bitflags: bool`, and `cancelled = Signal()`; method `show_at(global_point: QPoint)`.

- [ ] **Step 1: Write the failing tests** — create `tests/ui/test_annotate_popover.py` (GPL header, then):

```python
from PySide6.QtCore import Qt

from pgtp_editor.ui.annotate_popover import AnnotatePopover


def _popover(qtbot, **kwargs):
    popover = AnnotatePopover("Root/Item", "mode", "4", **kwargs)
    qtbot.addWidget(popover)
    return popover


def test_prefills_existing_annotation(qtbot):
    popover = _popover(
        qtbot, label="pdf", note="adds <X>", kind="setting", bitflags=True
    )
    assert popover.label_edit.text() == "pdf"
    assert popover.note_edit.text() == "adds <X>"
    assert popover.kind_combo.currentText() == "Setting"
    assert popover.bitflags_check.isChecked()
    assert "Root/Item" in popover.header_label.text()
    assert "mode" in popover.header_label.text()
    assert '"4"' in popover.header_label.text()


def test_enter_in_label_commits_payload(qtbot):
    popover = _popover(qtbot)
    committed = []
    popover.committed.connect(committed.append)
    popover.label_edit.setText("pdf")
    popover.note_edit.setText("enables <Watermark>")
    popover.bitflags_check.setChecked(True)
    popover.kind_combo.setCurrentText("Setting")
    popover.label_edit.returnPressed.emit()
    assert committed == [{
        "label": "pdf",
        "note": "enables <Watermark>",
        "kind": "setting",
        "bitflags": True,
    }]


def test_escape_cancels(qtbot):
    popover = _popover(qtbot)
    cancelled = []
    popover.cancelled.connect(lambda: cancelled.append(True))
    qtbot.keyClick(popover, Qt.Key.Key_Escape)
    assert cancelled == [True]
```

- [ ] **Step 2: Run to verify failure**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_annotate_popover.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgtp_editor.ui.annotate_popover'`

- [ ] **Step 3: Implement** — create `pgtp_editor/ui/annotate_popover.py` (GPL header, then):

```python
"""AnnotatePopover: the compact at-caret authoring surface for the schema
model's labeler-owned fields (labels / notes / kind / enum_mode).

Replaces the retired AnnotateSchemaValuesDialog. Pure view: it renders the
current annotation for one (tag_chain, attr, value) and emits `committed`
with the edited payload — persistence (model mutation, save, XSD regen)
belongs to MainWindow (_apply_annotation), keeping this widget stateless
about storage.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
)

# Display label paired with the stored kind string (kind is a labeler-owned
# model field; "unclassified" is stored as an ABSENT key).
_KIND_CHOICES = [
    ("Unclassified", "unclassified"),
    ("Setting", "setting"),
    ("Content", "content"),
]


class AnnotatePopover(QFrame):
    committed = Signal(dict)   # {"label", "note", "kind", "bitflags"}
    cancelled = Signal()

    def __init__(
        self,
        tag_chain: str,
        attr: str,
        value: str,
        label: str = "",
        note: str = "",
        kind: str = "unclassified",
        bitflags: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self.header_label = QLabel(f'{tag_chain}\n{attr} = "{value}"')
        self.header_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.label_edit = QLineEdit(label)
        self.label_edit.setPlaceholderText("Meaning — e.g. pdf")
        self.note_edit = QLineEdit(note)
        self.note_edit.setPlaceholderText(
            "Note — e.g. enables the <Watermark> child tag"
        )
        self.bitflags_check = QCheckBox("Bit-flags (values add up: 3 = 1+2)")
        self.bitflags_check.setChecked(bitflags)
        self.kind_combo = QComboBox()
        for display, _key in _KIND_CHOICES:
            self.kind_combo.addItem(display)
        for index, (_display, key) in enumerate(_KIND_CHOICES):
            if key == kind:
                self.kind_combo.setCurrentIndex(index)
                break

        layout = QFormLayout(self)
        layout.addRow(self.header_label)
        layout.addRow("Label:", self.label_edit)
        layout.addRow("Note:", self.note_edit)
        layout.addRow(self.bitflags_check)
        layout.addRow("Kind:", self.kind_combo)

        self.label_edit.returnPressed.connect(self._commit)
        self.note_edit.returnPressed.connect(self._commit)

    def _commit(self) -> None:
        _display, kind = _KIND_CHOICES[self.kind_combo.currentIndex()]
        self.committed.emit({
            "label": self.label_edit.text(),
            "note": self.note_edit.text(),
            "kind": kind,
            "bitflags": self.bitflags_check.isChecked(),
        })
        self.hide()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.hide()
            return
        super().keyPressEvent(event)

    def show_at(self, global_point) -> None:
        """Show as a popup at ``global_point`` with focus in the Label field."""
        self.move(global_point)
        self.show()
        self.label_edit.setFocus()
```

- [ ] **Step 4: Run to verify pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_annotate_popover.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/annotate_popover.py tests/ui/test_annotate_popover.py
git commit -m "feat: AnnotatePopover widget (label/note/bitflags/kind at caret)"
```

---

### Task 7: Editor annotate request (signal + context menu)

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py` — new signal near line 568, `request_annotate_at_cursor` + `schema_model()` accessor near `set_schema_model`, context-menu insertion in `_build_context_menu` (line ~1210)
- Test: `tests/ui/test_xml_editor_annotate.py` (append)

**Interfaces:**
- Produces (used by Task 8): `XmlEditor.annotate_value_requested = Signal(str, str, str)` (tag_chain, attr, value); `XmlEditor.request_annotate_at_cursor() -> bool`; `XmlEditor.schema_model()` accessor. Context menu shows "Annotate value…" when the cursor resolves to an attribute and a model is set.

- [ ] **Step 1: Write the failing tests** — append:

```python
def test_request_annotate_emits_context(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1"/>')
    editor.set_schema_model(_model({"Root": {"a": _entry(["1"])}}))
    cursor = editor.textCursor()
    cursor.setPosition(editor.toPlainText().index('"1"') + 1)
    editor.setTextCursor(cursor)
    received = []
    editor.annotate_value_requested.connect(
        lambda chain, attr, value: received.append((chain, attr, value))
    )
    assert editor.request_annotate_at_cursor() is True
    assert received == [("Root", "a", "1")]


def test_request_annotate_false_without_model_or_off_attribute(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1"/>')
    assert editor.request_annotate_at_cursor() is False  # no model
    editor.set_schema_model(_model({"Root": {"a": _entry(["1"])}}))
    cursor = editor.textCursor()
    cursor.setPosition(0)  # on '<', not an attribute
    editor.setTextCursor(cursor)
    assert editor.request_annotate_at_cursor() is False


def test_context_menu_offers_annotate_value_on_attribute(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1"/>')
    editor.set_schema_model(_model({"Root": {"a": _entry(["1"])}}))
    cursor = editor.textCursor()
    cursor.setPosition(editor.toPlainText().index('"1"') + 1)
    editor.setTextCursor(cursor)
    menu = editor._build_context_menu()
    texts = [action.text() for action in menu.actions()]
    assert "Annotate value…" in texts
```

- [ ] **Step 2: Run to verify failure**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_xml_editor_annotate.py -q`
Expected: new tests FAIL (`AttributeError: ... annotate_value_requested`).

- [ ] **Step 3: Implement.**

3a. Signal (after `redo_requested = Signal()`):

```python
    # Emitted when the user asks to annotate the attribute value at the
    # caret (Schema ▸ Annotate Value at Cursor / Ctrl+L / context menu).
    # Carries (tag_chain, attr, value); MainWindow opens the AnnotatePopover
    # and owns persistence.
    annotate_value_requested = Signal(str, str, str)
```

3b. Methods (next to `set_schema_model`):

```python
    def schema_model(self):
        """The injected schema Model, or None. Read-only accessor for
        MainWindow's annotation flow."""
        return self._schema_model

    def request_annotate_at_cursor(self) -> bool:
        """Resolve the caret onto an attribute (name token or value) and
        emit annotate_value_requested. Returns False when no model is set or
        the caret is not on an attribute. Works in read-only mode too —
        annotating edits the schema model, never the document."""
        if self._schema_model is None:
            return False
        resolved = attribute_value_at_position(
            self.toPlainText(), self.textCursor().position()
        )
        if resolved is None:
            return False
        self.annotate_value_requested.emit(*resolved)
        return True
```

3c. Context menu — in `_build_context_menu`, immediately before the "Add attribute ▸" block (line ~1239), add:

```python
        # "Annotate value…" opens the schema annotation popover for the
        # attribute under the cursor. Offered whenever the cursor resolves to
        # an attribute and a schema model is present (read-only mode too:
        # annotation edits the model, not the document).
        if self._schema_model is not None and attribute_value_at_position(
            self.toPlainText(), cursor.position()
        ) is not None:
            annotate_action = QAction("Annotate value…", menu)
            annotate_action.triggered.connect(self.request_annotate_at_cursor)
            if before is not None:
                menu.insertAction(before, annotate_action)
            else:
                menu.addAction(annotate_action)
```

- [ ] **Step 4: Run to verify pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_xml_editor_annotate.py tests\ui\test_xml_editor_add_attribute.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor_annotate.py
git commit -m "feat: annotate_value_requested signal + context-menu entry"
```

---

### Task 8: MainWindow — popover wiring, persistence, new menu actions

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` — `_build_schema_menu` (line ~1832), new handlers, signal connection where the editor's other signals are connected in `__init__`
- Test: `tests/ui/test_annotate_wiring.py` (create)

**Interfaces:**
- Consumes: Tasks 5–7 (`goto_next_unlabeled_value`, `request_annotate_at_cursor`, `schema_model()`, `annotate_value_requested`, `AnnotatePopover`), `attribute_kind`, `schema_model_path`/`schema_xsd_path`, `generate_xsd` (already imported).
- Produces: menu actions "Annotate Value at Cursor" (Ctrl+L) and "Next Unlabeled Value" (Ctrl+Shift+L); `MainWindow._apply_annotation(tag_chain, attr, value, edits)` persisting labeler fields; `[Schema] LABELED:` audit-line convention. (Part B menu items arrive in Task 13.)

- [ ] **Step 1: Write the failing tests** — create `tests/ui/test_annotate_wiring.py`. Copy the MainWindow construction fixture used in `tests/ui/test_schema_learning_wiring.py` (temp `QSettings` ini + `schema_storage_dir=tmp_path`) — reuse its helper if importable, otherwise replicate it verbatim. Then:

```python
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import schema_model_path, schema_xsd_path


def _seed_model(window):
    model = Model()
    model.paths = {
        "Root": {
            "attributes": {
                "mode": {
                    "type": "integer",
                    "values": ["4"],
                    "overflowed": False,
                    "attr_seen_count": 1,
                    "labels": {},
                }
            },
            "children": {},
            "instance_count": 1,
            "order": [],
            "order_stable": True,
            "has_text": False,
        }
    }
    window.center_stage.xml_editor.set_schema_model(model)
    return model


def test_apply_annotation_persists_all_fields(window):
    _seed_model(window)
    window._apply_annotation("Root", "mode", "4", {
        "label": "pdf",
        "note": "enables <Watermark>",
        "kind": "setting",
        "bitflags": True,
    })
    saved = Model.load(schema_model_path(window._schema_storage_dir))
    entry = saved.paths["Root"]["attributes"]["mode"]
    assert entry["labels"] == {"4": "pdf"}
    assert entry["notes"] == {"4": "enables <Watermark>"}
    assert entry["kind"] == "setting"
    assert entry["enum_mode"] == "bitflags"
    xsd = schema_xsd_path(window._schema_storage_dir).read_text(encoding="utf-8")
    assert "pdf" in xsd
    items = [window.audit_panel.item(i).text()
             for i in range(window.audit_panel.count())]
    assert any(line.startswith("[Schema] LABELED:") for line in items)


def test_apply_annotation_empty_strings_remove_fields(window):
    model = _seed_model(window)
    entry = model.paths["Root"]["attributes"]["mode"]
    entry["labels"]["4"] = "pdf"
    entry["notes"] = {"4": "x"}
    entry["kind"] = "setting"
    entry["enum_mode"] = "bitflags"
    window._apply_annotation("Root", "mode", "4", {
        "label": "", "note": "", "kind": "unclassified", "bitflags": False,
    })
    saved = Model.load(schema_model_path(window._schema_storage_dir))
    entry = saved.paths["Root"]["attributes"]["mode"]
    assert entry["labels"] == {}
    assert "notes" not in entry
    assert "kind" not in entry
    assert "enum_mode" not in entry


def test_schema_menu_has_new_actions(window):
    schema_menu = next(
        a.menu() for a in window.menuBar().actions() if a.text() == "Schema"
    )
    texts = [a.text() for a in schema_menu.actions() if a.text()]
    assert "Annotate Value at Cursor" in texts
    assert "Next Unlabeled Value" in texts
    assert "Annotate Schema Values..." not in texts
```

(`window` is the fixture name from the copied construction helper; align with whatever `test_schema_learning_wiring.py` calls it.)

- [ ] **Step 2: Run to verify failure**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_annotate_wiring.py -q`
Expected: FAIL (`AttributeError: _apply_annotation` / menu assertions).

- [ ] **Step 3: Implement** in `main_window.py`:

3a. Imports: add `attribute_kind` to the settings_index imports (add the import line if absent: `from pgtp_editor.schema_learning.settings_index import attribute_kind`), `from pgtp_editor.ui.annotate_popover import AnnotatePopover`, and `QKeySequence` from `PySide6.QtGui` if not already imported.

3b. In `__init__`, where other `center_stage.xml_editor` signals are connected, add:

```python
        self.center_stage.xml_editor.annotate_value_requested.connect(
            self._open_annotate_popover
        )
        # The live AnnotatePopover (kept on self so it is not garbage
        # collected while shown as a parentless-popup child).
        self._annotate_popover = None
```

3c. Replace the "Annotate Schema Values..." entry in `_build_schema_menu`:

```python
    def _build_schema_menu(self):
        menu = self.menuBar().addMenu("Schema")
        annotate_action = menu.addAction("Annotate Value at Cursor")
        annotate_action.setShortcut(QKeySequence("Ctrl+L"))
        annotate_action.triggered.connect(self._annotate_value_at_cursor)
        next_unlabeled_action = menu.addAction("Next Unlabeled Value")
        next_unlabeled_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        next_unlabeled_action.triggered.connect(self._goto_next_unlabeled_value)
        menu.addSeparator()
        open_xsd_action = menu.addAction("Open XSD")
        open_xsd_action.triggered.connect(self._open_xsd_viewer)
        open_labels_action = menu.addAction("Open XSD Labels (JSON)")
        open_labels_action.triggered.connect(self._open_labels_viewer)
```

3d. New handlers (replace `_open_annotate_schema_values`):

```python
    def _annotate_value_at_cursor(self):
        editor = self.center_stage.xml_editor
        if editor.schema_model() is None:
            self.statusBar().showMessage(self._NO_SCHEMA_MESSAGE, 5000)
            return
        if not editor.request_annotate_at_cursor():
            self.statusBar().showMessage(
                "Place the cursor on an attribute value to annotate it.", 5000
            )

    def _goto_next_unlabeled_value(self):
        if not self.center_stage.xml_editor.goto_next_unlabeled_value():
            self.statusBar().showMessage(
                "No unlabeled enum values in this document.", 5000
            )

    def _open_annotate_popover(self, tag_chain, attr, value):
        editor = self.center_stage.xml_editor
        model = editor.schema_model()
        entry = (
            model.paths.get(tag_chain, {}).get("attributes", {}).get(attr)
            if model is not None
            else None
        )
        if entry is None:
            # The document carries an attribute the model has not learned yet
            # (e.g. hand-typed since the last File ▸ Open). Learning is the
            # engine's job — never create entries from the labeler side.
            self.statusBar().showMessage(
                f"'{attr}' is not in the learned schema yet — "
                "File ▸ Open the file to learn it first.",
                5000,
            )
            return
        labels = entry.get("labels") or {}
        notes = entry.get("notes") or {}
        popover = AnnotatePopover(
            tag_chain,
            attr,
            value,
            label=labels.get(value, ""),
            note=notes.get(value, ""),
            kind=attribute_kind(entry),
            bitflags=entry.get("enum_mode") == "bitflags",
            parent=self,
        )
        popover.committed.connect(
            lambda edits: self._apply_annotation(tag_chain, attr, value, edits)
        )
        rect = editor.cursorRect()
        popover.show_at(editor.viewport().mapToGlobal(rect.bottomLeft()))
        self._annotate_popover = popover

    def _apply_annotation(self, tag_chain, attr, value, edits):
        """Write one popover commit into the labeler-owned model fields,
        persist model + regenerated XSD, and refresh the editor. Empty
        strings remove; 'unclassified' kind and un-checked bitflags remove
        their keys (absent == default, keeping the JSON tidy)."""
        editor = self.center_stage.xml_editor
        model = editor.schema_model()
        entry = model.paths[tag_chain]["attributes"][attr]
        label = edits["label"].strip()
        note = edits["note"].strip()
        entry.setdefault("labels", {})
        if label:
            entry["labels"][value] = label
        else:
            entry["labels"].pop(value, None)
        notes = entry.setdefault("notes", {})
        if note:
            notes[value] = note
        else:
            notes.pop(value, None)
        if not entry["notes"]:
            entry.pop("notes")
        if edits["bitflags"]:
            entry["enum_mode"] = "bitflags"
        else:
            entry.pop("enum_mode", None)
        if edits["kind"] == "unclassified":
            entry.pop("kind", None)
        else:
            entry["kind"] = edits["kind"]
        try:
            model_path = schema_model_path(self._schema_storage_dir)
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model.save(model_path)
            schema_xsd_path(self._schema_storage_dir).write_text(
                generate_xsd(model), encoding="utf-8"
            )
        except Exception as exc:
            self.audit_panel.addItem(f"[Schema] Could not save annotation: {exc}")
            return
        editor.set_schema_model(model)  # refreshes underlines
        shown = label if label else "(no label)"
        self.audit_panel.addItem(
            f'[Schema] LABELED: {tag_chain}@{attr} "{value}" = "{shown}"'
        )
```

Keep the old `AnnotateSchemaValuesDialog` import for now — it is removed in Task 9.

- [ ] **Step 4: Run to verify pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_annotate_wiring.py tests\ui\test_schema_learning_wiring.py tests\ui\test_menus.py tests\ui\test_schema_menu_entry_point.py -q`
Expected: `test_annotate_wiring.py` PASSES. `test_menus.py` / `test_schema_menu_entry_point.py` may FAIL on the removed "Annotate Schema Values..." action — update those assertions to the new action names now (they are asserting superseded behavior).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_annotate_wiring.py tests/ui/test_menus.py tests/ui/test_schema_menu_entry_point.py
git commit -m "feat: annotate popover wiring, persistence, Schema menu rework"
```

---

### Task 9: Delete the superseded dialog

**Files:**
- Delete: `pgtp_editor/ui/annotate_schema_values_dialog.py`, `tests/ui/test_annotate_schema_values_dialog.py`
- Modify: `pgtp_editor/ui/main_window.py` (drop import line 84 and any leftover references)

- [ ] **Step 1: Remove the files and references**

```bash
git rm pgtp_editor/ui/annotate_schema_values_dialog.py tests/ui/test_annotate_schema_values_dialog.py
```

In `main_window.py` delete `from pgtp_editor.ui.annotate_schema_values_dialog import AnnotateSchemaValuesDialog`. Then verify nothing else references it:

Run: `python -c "import subprocess; print(subprocess.run(['git','grep','-n','AnnotateSchemaValuesDialog'],capture_output=True,text=True).stdout)"` — expected: empty (docs/superpowers historical files excepted; those are frozen history and stay).

- [ ] **Step 2: Run the full suite**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`
Expected: PASS, no import errors.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: delete superseded AnnotateSchemaValuesDialog"
```

---

### Task 10: Semantic model merge (`schema_learning/merge.py`)

**Files:**
- Create: `pgtp_editor/schema_learning/merge.py`
- Test: `tests/schema_learning/test_merge.py`

**Interfaces:**
- Produces (used by Task 13):
  - `@dataclass Conflict: path: str; attr: str; field: str; value: str | None; base: str; incoming: str` — `field` ∈ `"labels" | "notes" | "kind" | "enum_mode"`; `value` is the dict key for labels/notes, None for scalars.
  - `merge_models(base: Model, incoming: Model) -> list[Conflict]` — folds `incoming` into `base` IN PLACE; engine fields merge additively; labeler fields union; on disagreement the base value is kept and a Conflict is returned (never silent).
  - `apply_resolution(model: Model, conflict: Conflict, use_incoming: bool) -> None`.

Merge semantics (the "sum counts" rule): `instance_count` and `attr_seen_count` are SUMMED, so an attribute stays required (`attr_seen_count == instance_count`) after merge iff it was required on BOTH sides — max() would wrongly resurrect required-ness, min() would wrongly drop it.

- [ ] **Step 1: Write the failing tests** — create `tests/schema_learning/test_merge.py` (GPL header, then):

```python
from pgtp_editor.schema_learning.merge import Conflict, apply_resolution, merge_models
from pgtp_editor.schema_learning.model import ENUM_MAX_VALUES, Model


def _model(paths):
    model = Model()
    model.paths = paths
    return model


def _element(attributes=None, instance_count=1, children=None, order=None):
    return {
        "attributes": attributes or {},
        "children": children or {},
        "instance_count": instance_count,
        "order": order or [],
        "order_stable": True,
        "has_text": False,
    }


def _attr(values, labels=None, seen=1, **extra):
    entry = {
        "type": "integer",
        "values": values,
        "overflowed": values is None,
        "attr_seen_count": seen,
        "labels": labels or {},
    }
    entry.update(extra)
    return entry


def test_superset_merge_is_conflict_free_and_additive():
    base = _model({"Root": _element({"a": _attr(["1"], labels={"1": "A"})})})
    incoming = _model({
        "Root": _element({
            "a": _attr(["1", "2"], labels={"1": "A", "2": "B"}),
            "b": _attr(["x"]),
        }),
        "Root/New": _element({}),
    })
    conflicts = merge_models(base, incoming)
    assert conflicts == []
    entry = base.paths["Root"]["attributes"]["a"]
    assert sorted(entry["values"]) == ["1", "2"]
    assert entry["labels"] == {"1": "A", "2": "B"}
    assert "b" in base.paths["Root"]["attributes"]
    assert "Root/New" in base.paths


def test_label_conflict_keeps_base_and_reports():
    base = _model({"Root": _element({"a": _attr(["4"], labels={"4": "pdf"})})})
    incoming = _model({"Root": _element({"a": _attr(["4"], labels={"4": "PDF export"})})})
    conflicts = merge_models(base, incoming)
    assert conflicts == [
        Conflict("Root", "a", "labels", "4", "pdf", "PDF export")
    ]
    assert base.paths["Root"]["attributes"]["a"]["labels"]["4"] == "pdf"


def test_apply_resolution_takes_incoming():
    base = _model({"Root": _element({"a": _attr(["4"], labels={"4": "pdf"})})})
    conflict = Conflict("Root", "a", "labels", "4", "pdf", "PDF export")
    apply_resolution(base, conflict, use_incoming=True)
    assert base.paths["Root"]["attributes"]["a"]["labels"]["4"] == "PDF export"
    apply_resolution(base, conflict, use_incoming=False)  # no-op
    assert base.paths["Root"]["attributes"]["a"]["labels"]["4"] == "PDF export"


def test_required_survives_only_when_required_on_both_sides():
    base = _model({"Root": _element({"a": _attr(["1"], seen=5)}, instance_count=5)})
    incoming = _model({"Root": _element({"a": _attr(["1"], seen=2)}, instance_count=3)})
    merge_models(base, incoming)
    entry = base.paths["Root"]
    attr = entry["attributes"]["a"]
    assert entry["instance_count"] == 8
    assert attr["attr_seen_count"] == 7
    assert attr["attr_seen_count"] != entry["instance_count"]  # optional now


def test_values_union_overflow():
    base = _model({"Root": _element({"a": _attr([str(i) for i in range(ENUM_MAX_VALUES)])})})
    incoming = _model({"Root": _element({"a": _attr(["x", "y"])})})
    merge_models(base, incoming)
    attr = base.paths["Root"]["attributes"]["a"]
    assert attr["overflowed"] is True
    assert attr["values"] is None


def test_kind_and_enum_mode_conflicts():
    base = _model({"Root": _element({"a": _attr(["1"], kind="setting")})})
    incoming = _model({"Root": _element({"a": _attr(["1"], kind="content", enum_mode="bitflags")})})
    conflicts = merge_models(base, incoming)
    assert conflicts == [
        Conflict("Root", "a", "kind", None, "setting", "content")
    ]
    # enum_mode was unset on base -> adopted, no conflict
    assert base.paths["Root"]["attributes"]["a"]["enum_mode"] == "bitflags"
```

- [ ] **Step 2: Run to verify failure**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\schema_learning\test_merge.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement** — create `pgtp_editor/schema_learning/merge.py` (GPL header, then):

```python
"""Qt-free model-to-model semantic merge for team schema sharing.

Folds one learned schema Model into another: engine-owned fields merge
additively (mirroring Model.merge_element's semantics across whole models),
labeler-owned fields (labels / notes / kind / enum_mode) merge by union with
NEVER-SILENT conflict surfacing — where both sides disagree, the base value
is kept and a Conflict record is returned for the caller (MainWindow's
Merge Team Models dialog, or Fetch Team Master's audit report) to resolve.

instance_count / attr_seen_count are SUMMED so that "required" (seen count
== instance count) survives a merge only when the attribute was required on
BOTH sides.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from .model import ENUM_MAX_VALUES
from .types import combine_type

LABELER_DICT_FIELDS = ("labels", "notes")
LABELER_SCALAR_FIELDS = ("kind", "enum_mode")


@dataclass
class Conflict:
    path: str
    attr: str
    field: str          # "labels" | "notes" | "kind" | "enum_mode"
    value: str | None   # dict key for labels/notes; None for scalar fields
    base: str
    incoming: str


def merge_models(base, incoming):
    """Fold ``incoming`` into ``base`` in place; return the conflicts."""
    conflicts: list[Conflict] = []
    for path, inc_entry in incoming.paths.items():
        if path not in base.paths:
            base.paths[path] = copy.deepcopy(inc_entry)
            continue
        _merge_element_entry(path, base.paths[path], inc_entry, conflicts)
    return conflicts


def apply_resolution(model, conflict, use_incoming):
    """Apply one user decision for ``conflict`` to ``model`` (the merge
    base). ``use_incoming=False`` is a no-op — the base value was kept."""
    if not use_incoming:
        return
    entry = model.paths[conflict.path]["attributes"][conflict.attr]
    if conflict.field in LABELER_DICT_FIELDS:
        entry.setdefault(conflict.field, {})[conflict.value] = conflict.incoming
    else:
        entry[conflict.field] = conflict.incoming


def _merge_element_entry(path, base_entry, inc_entry, conflicts):
    base_entry["instance_count"] += inc_entry["instance_count"]
    base_entry["has_text"] = base_entry["has_text"] or inc_entry["has_text"]

    for tag, inc_child in inc_entry["children"].items():
        child = base_entry["children"].get(tag)
        if child is None:
            base_entry["children"][tag] = dict(inc_child)
            base_entry["order"].append(tag)
        else:
            child["ever_absent"] = child["ever_absent"] or inc_child["ever_absent"]
            child["ever_multiple"] = (
                child["ever_multiple"] or inc_child["ever_multiple"]
            )
    if not inc_entry["order_stable"]:
        base_entry["order_stable"] = False
    common = set(base_entry["order"]) & set(inc_entry["order"])
    if [t for t in base_entry["order"] if t in common] != [
        t for t in inc_entry["order"] if t in common
    ]:
        base_entry["order_stable"] = False

    for attr, inc_attr in inc_entry["attributes"].items():
        base_attr = base_entry["attributes"].get(attr)
        if base_attr is None:
            base_entry["attributes"][attr] = copy.deepcopy(inc_attr)
            continue
        _merge_attribute_entry(path, attr, base_attr, inc_attr, conflicts)


def _merge_attribute_entry(path, attr, base_attr, inc_attr, conflicts):
    base_attr["type"] = combine_type(base_attr["type"], inc_attr["type"])
    base_attr["attr_seen_count"] += inc_attr["attr_seen_count"]

    if inc_attr["overflowed"]:
        base_attr["overflowed"] = True
        base_attr["values"] = None
    elif not base_attr["overflowed"]:
        merged = list(base_attr["values"])
        for value in inc_attr["values"]:
            if value not in merged:
                merged.append(value)
        if len(merged) > ENUM_MAX_VALUES:
            base_attr["overflowed"] = True
            base_attr["values"] = None
        else:
            base_attr["values"] = merged

    for field in LABELER_DICT_FIELDS:
        inc_dict = inc_attr.get(field) or {}
        if not inc_dict:
            continue
        base_dict = base_attr.setdefault(field, {})
        for value, inc_text in inc_dict.items():
            base_text = base_dict.get(value)
            if base_text is None:
                base_dict[value] = inc_text
            elif base_text != inc_text:
                conflicts.append(
                    Conflict(path, attr, field, value, base_text, inc_text)
                )

    for field in LABELER_SCALAR_FIELDS:
        inc_val = inc_attr.get(field)
        if inc_val is None:
            continue
        base_val = base_attr.get(field)
        if base_val is None:
            base_attr[field] = inc_val
        elif base_val != inc_val:
            conflicts.append(Conflict(path, attr, field, None, base_val, inc_val))
```

- [ ] **Step 4: Run to verify pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\schema_learning\test_merge.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/schema_learning/merge.py tests/schema_learning/test_merge.py
git commit -m "feat: Qt-free semantic model merge with never-silent conflicts"
```

---

### Task 11: Git transport (`schema_learning/sync.py`) + `team_repo_dir`

**Files:**
- Create: `pgtp_editor/schema_learning/sync.py`
- Modify: `pgtp_editor/schema_learning/storage.py` (add `team_repo_dir`)
- Test: `tests/schema_learning/test_sync.py`, `tests/schema_learning/test_storage.py` (append one test)

**Interfaces:**
- Produces (used by Tasks 12–13):
  - `class SyncError(Exception)`
  - `@dataclass SyncConfig: repo_url: str; clone_dir: Path; key_path: str | None = None`
  - `default_username() -> str` (sanitized `getpass.getuser()`)
  - `ensure_repo(config, runner=subprocess.run) -> Path` — clone or pull-rebase; sets local git identity; tolerates an EMPTY remote (first-ever publish).
  - `publish_model(config, model_path, username=None, runner=...) -> str | None` — repo-relative path published, None when nothing changed.
  - `fetch_master(config, runner=...) -> Path | None`
  - `team_model_paths(config, runner=...) -> list[Path]`
  - `push_master(config, master_model, runner=...) -> bool` — writes `master.json` via `master_model.save`, commits, pushes; False when unchanged.
  - `storage.team_repo_dir(base_dir=None) -> Path` → `<AppData or base_dir>/team_schema_repo`
- Key handling: when `key_path` is set, every git call runs with `GIT_SSH_COMMAND=ssh -i "<key>" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new`; when unset (local-path/`file://` URLs, tests) plain git.

- [ ] **Step 1: Write the failing tests** — create `tests/schema_learning/test_sync.py` (GPL header, then):

```python
import shutil
import subprocess

import pytest

from pgtp_editor.schema_learning import sync
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import team_repo_dir

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git CLI not available"
)


@pytest.fixture
def origin(tmp_path):
    origin_dir = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", str(origin_dir)],
        check=True, capture_output=True,
    )
    return origin_dir


def _config(tmp_path, origin, name="clone"):
    return sync.SyncConfig(
        repo_url=str(origin), clone_dir=tmp_path / name, key_path=None
    )


def _model_file(tmp_path):
    model = Model()
    model.paths = {"Root": {
        "attributes": {}, "children": {}, "instance_count": 1,
        "order": [], "order_stable": True, "has_text": False,
    }}
    path = tmp_path / "schema_model.json"
    model.save(path)
    return path


def test_publish_then_visible_from_second_clone(tmp_path, origin):
    model_path = _model_file(tmp_path)
    published = sync.publish_model(
        _config(tmp_path, origin, "clone_a"), model_path, username="alice"
    )
    assert published == "models/alice.json"
    config_b = _config(tmp_path, origin, "clone_b")
    assert [p.name for p in sync.team_model_paths(config_b)] == ["alice.json"]


def test_publish_unchanged_returns_none(tmp_path, origin):
    model_path = _model_file(tmp_path)
    config = _config(tmp_path, origin)
    assert sync.publish_model(config, model_path, username="alice") is not None
    assert sync.publish_model(config, model_path, username="alice") is None


def test_fetch_master_roundtrip(tmp_path, origin):
    config = _config(tmp_path, origin, "admin")
    assert sync.fetch_master(config) is None
    master = Model.load(_model_file(tmp_path))
    assert sync.push_master(config, master) is True
    other = _config(tmp_path, origin, "user")
    fetched = sync.fetch_master(other)
    assert fetched is not None
    assert Model.load(fetched).paths.keys() == master.paths.keys()


def test_push_retry_rebases_on_concurrent_push(tmp_path, origin):
    model_path = _model_file(tmp_path)
    config_a = _config(tmp_path, origin, "clone_a")
    config_b = _config(tmp_path, origin, "clone_b")
    sync.publish_model(config_a, model_path, username="alice")
    # B clones, then A advances origin again -> B's push must rebase+retry.
    sync.ensure_repo(config_b)
    sync.publish_model(config_a, model_path, username="alice2")
    assert sync.publish_model(config_b, model_path, username="bob") == "models/bob.json"
    assert {p.name for p in sync.team_model_paths(config_a)} == {
        "alice.json", "alice2.json", "bob.json"
    }


def test_bad_url_raises_sync_error(tmp_path):
    config = sync.SyncConfig(
        repo_url=str(tmp_path / "missing.git"),
        clone_dir=tmp_path / "clone",
        key_path=None,
    )
    with pytest.raises(sync.SyncError):
        sync.ensure_repo(config)


def test_default_username_is_sanitized(monkeypatch):
    monkeypatch.setattr(sync.getpass, "getuser", lambda: "büro user!")
    assert sync.default_username() == "b_ro_user_"


def test_key_path_sets_git_ssh_command(tmp_path):
    recorded = {}

    def runner(args, **kwargs):
        recorded["env"] = kwargs["env"]
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    config = sync.SyncConfig(
        repo_url="git@example:x.git", clone_dir=tmp_path / "c", key_path="k.pem"
    )
    sync._git(config, ["version"], cwd=None, runner=runner)
    assert 'ssh -i "k.pem"' in recorded["env"]["GIT_SSH_COMMAND"]
```

And append to `tests/schema_learning/test_storage.py`:

```python
def test_team_repo_dir_under_base_dir(tmp_path):
    from pgtp_editor.schema_learning.storage import team_repo_dir
    assert team_repo_dir(tmp_path) == tmp_path / "team_schema_repo"
```

- [ ] **Step 2: Run to verify failure**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\schema_learning\test_sync.py tests\schema_learning\test_storage.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError`.

- [ ] **Step 3: Implement.**

3a. `storage.py` — add:

```python
_TEAM_REPO_DIRNAME = "team_schema_repo"


def team_repo_dir(base_dir: Path | None = None) -> Path:
    """Local clone location of the team schema-sharing repo (a transport
    cache, not a source of truth — see CONSOLIDATED_SPEC §11)."""
    return (base_dir or _app_data_dir()) / _TEAM_REPO_DIRNAME
```

3b. Create `pgtp_editor/schema_learning/sync.py` (GPL header, then):

```python
"""Qt-free git transport for team schema-model sharing.

The team repo contains ONLY schema model JSONs: models/<username>.json per
user plus master.json. This module shells out to the git CLI through an
injectable ``runner`` (tests pass a fake or drive a local file-path origin);
when a deploy-key path is configured every call gets a scoped
GIT_SSH_COMMAND. All failures raise SyncError with git's stderr — callers
(MainWindow) report via [Schema] audit lines and leave local state alone.
"""
from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class SyncError(Exception):
    pass


@dataclass
class SyncConfig:
    repo_url: str
    clone_dir: Path
    key_path: str | None = None


def default_username() -> str:
    """OS username sanitized to [A-Za-z0-9_-] for use as a filename."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", getpass.getuser()) or "user"


def _git(config, args, cwd, runner=subprocess.run):
    env = os.environ.copy()
    if config.key_path:
        env["GIT_SSH_COMMAND"] = (
            f'ssh -i "{config.key_path}" -o IdentitiesOnly=yes '
            "-o StrictHostKeyChecking=accept-new"
        )
    completed = runner(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise SyncError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def ensure_repo(config, runner=subprocess.run) -> Path:
    """Clone the team repo if absent, else pull --rebase. Tolerates a brand
    new EMPTY remote (nothing to pull yet). Sets a local commit identity so
    commits work on machines without global git config."""
    clone_dir = Path(config.clone_dir)
    if not (clone_dir / ".git").exists():
        clone_dir.parent.mkdir(parents=True, exist_ok=True)
        _git(config, ["clone", config.repo_url, str(clone_dir)], cwd=None, runner=runner)
    else:
        try:
            _git(config, ["pull", "--rebase"], cwd=clone_dir, runner=runner)
        except SyncError as exc:
            # A just-created bare origin has no branch to pull from yet; the
            # first publish will create it. Anything else is a real failure.
            if "couldn't find remote ref" not in str(exc).lower():
                raise
    username = default_username()
    _git(config, ["config", "user.name", f"{username} (pgtp-editor)"],
         cwd=clone_dir, runner=runner)
    _git(config, ["config", "user.email", f"{username}@pgtp-editor.invalid"],
         cwd=clone_dir, runner=runner)
    return clone_dir


def _push_with_retry(config, clone_dir, runner, attempts=3):
    last = None
    for _ in range(attempts):
        try:
            _git(config, ["push", "-u", "origin", "HEAD"], cwd=clone_dir, runner=runner)
            return
        except SyncError as exc:
            last = exc
            _git(config, ["pull", "--rebase"], cwd=clone_dir, runner=runner)
    raise last


def publish_model(config, model_path, username=None, runner=subprocess.run):
    """Copy the local model into models/<username>.json, commit, push (with
    pull-rebase retry). Returns the repo-relative path, or None when the
    published content is identical to what the repo already holds."""
    username = username or default_username()
    clone_dir = ensure_repo(config, runner=runner)
    models_dir = clone_dir / "models"
    models_dir.mkdir(exist_ok=True)
    shutil.copyfile(model_path, models_dir / f"{username}.json")
    _git(config, ["add", "models/"], cwd=clone_dir, runner=runner)
    if not _git(config, ["status", "--porcelain"], cwd=clone_dir, runner=runner).strip():
        return None
    _git(config, ["commit", "-m", f"Publish annotations: {username}"],
         cwd=clone_dir, runner=runner)
    _push_with_retry(config, clone_dir, runner)
    return f"models/{username}.json"


def fetch_master(config, runner=subprocess.run):
    """Pull and return the path to master.json, or None when the team has
    no merged master yet."""
    clone_dir = ensure_repo(config, runner=runner)
    master = clone_dir / "master.json"
    return master if master.exists() else None


def team_model_paths(config, runner=subprocess.run):
    """Pull and return every models/*.json, sorted by filename."""
    clone_dir = ensure_repo(config, runner=runner)
    models_dir = clone_dir / "models"
    return sorted(models_dir.glob("*.json")) if models_dir.exists() else []


def push_master(config, master_model, runner=subprocess.run) -> bool:
    """Write ``master_model`` as master.json, commit and push (with retry).
    Returns False when the master is unchanged (nothing pushed)."""
    clone_dir = ensure_repo(config, runner=runner)
    master_model.save(clone_dir / "master.json")
    _git(config, ["add", "master.json"], cwd=clone_dir, runner=runner)
    if not _git(config, ["status", "--porcelain"], cwd=clone_dir, runner=runner).strip():
        return False
    _git(config, ["commit", "-m", "Merge team models into master"],
         cwd=clone_dir, runner=runner)
    _push_with_retry(config, clone_dir, runner)
    return True
```

- [ ] **Step 4: Run to verify pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\schema_learning\test_sync.py tests\schema_learning\test_storage.py -q`
Expected: PASS. (If the concurrent-push test flakes on git's default-branch naming, add `-c init.defaultBranch=main` to the bare-init command in the fixture — clones follow the origin's HEAD either way.)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/schema_learning/sync.py pgtp_editor/schema_learning/storage.py tests/schema_learning/test_sync.py tests/schema_learning/test_storage.py
git commit -m "feat: git transport for team schema sharing (publish/fetch/master)"
```

---

### Task 12: Team sync configuration (QSettings + dialog)

**Files:**
- Create: `pgtp_editor/ui/team_sync_dialog.py`
- Test: `tests/ui/test_team_sync_dialog.py`

**Interfaces:**
- Consumes: `SyncConfig` (Task 11), `team_repo_dir` (Task 11), MainWindow's injectable `self._settings` (QSettings).
- Produces (used by Task 13):
  - `SYNC_REPO_URL_KEY = "schema_sync/repo_url"`, `SYNC_KEY_PATH_KEY = "schema_sync/key_path"`
  - `load_sync_config(settings, base_dir=None) -> SyncConfig | None` — None when no repo URL configured.
  - `TeamSyncSettingsDialog(settings, parent=None)` — `repo_url_edit`, `key_path_edit` QLineEdits; OK persists to settings.

- [ ] **Step 1: Write the failing tests** — create `tests/ui/test_team_sync_dialog.py` (GPL header; build a temp `QSettings` ini the same way `tests/db/test_config.py` / existing UI tests do):

```python
from PySide6.QtCore import QSettings

from pgtp_editor.ui.team_sync_dialog import (
    SYNC_KEY_PATH_KEY,
    SYNC_REPO_URL_KEY,
    TeamSyncSettingsDialog,
    load_sync_config,
)


def _settings(tmp_path):
    return QSettings(str(tmp_path / "test.ini"), QSettings.Format.IniFormat)


def test_load_sync_config_none_when_unconfigured(tmp_path):
    assert load_sync_config(_settings(tmp_path), tmp_path) is None


def test_load_sync_config_builds_config(tmp_path):
    settings = _settings(tmp_path)
    settings.setValue(SYNC_REPO_URL_KEY, "git@host:team/schema.git")
    settings.setValue(SYNC_KEY_PATH_KEY, "C:/keys/deploy.pem")
    config = load_sync_config(settings, tmp_path)
    assert config.repo_url == "git@host:team/schema.git"
    assert config.key_path == "C:/keys/deploy.pem"
    assert config.clone_dir == tmp_path / "team_schema_repo"


def test_dialog_persists_on_accept(tmp_path, qtbot):
    settings = _settings(tmp_path)
    dialog = TeamSyncSettingsDialog(settings)
    qtbot.addWidget(dialog)
    dialog.repo_url_edit.setText("git@host:team/schema.git")
    dialog.key_path_edit.setText("k.pem")
    dialog.accept()
    assert settings.value(SYNC_REPO_URL_KEY) == "git@host:team/schema.git"
    assert settings.value(SYNC_KEY_PATH_KEY) == "k.pem"
```

- [ ] **Step 2: Run to verify failure**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_team_sync_dialog.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement** — create `pgtp_editor/ui/team_sync_dialog.py` (GPL header, then):

```python
"""Team schema-sharing configuration: repo URL + deploy-key path, persisted
in the injectable QSettings (same seam as db/config.py). load_sync_config
is the single translation point from settings to a SyncConfig."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
)

from pgtp_editor.schema_learning.storage import team_repo_dir
from pgtp_editor.schema_learning.sync import SyncConfig

SYNC_REPO_URL_KEY = "schema_sync/repo_url"
SYNC_KEY_PATH_KEY = "schema_sync/key_path"


def load_sync_config(settings, base_dir=None):
    """SyncConfig from QSettings, or None when no repo URL is configured."""
    repo_url = (settings.value(SYNC_REPO_URL_KEY, "") or "").strip()
    if not repo_url:
        return None
    key_path = (settings.value(SYNC_KEY_PATH_KEY, "") or "").strip() or None
    return SyncConfig(
        repo_url=repo_url, clone_dir=team_repo_dir(base_dir), key_path=key_path
    )


class TeamSyncSettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Team Sync Settings")
        self._settings = settings
        self.repo_url_edit = QLineEdit(settings.value(SYNC_REPO_URL_KEY, "") or "")
        self.repo_url_edit.setPlaceholderText("git@host:team/pgtp-schema.git")
        self.key_path_edit = QLineEdit(settings.value(SYNC_KEY_PATH_KEY, "") or "")
        self.key_path_edit.setPlaceholderText(
            "Path to the deploy SSH key (leave empty for local/HTTPS remotes)"
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QFormLayout(self)
        layout.addRow("Repository URL:", self.repo_url_edit)
        layout.addRow("SSH key path:", self.key_path_edit)
        layout.addRow(buttons)

    def accept(self):
        self._settings.setValue(SYNC_REPO_URL_KEY, self.repo_url_edit.text().strip())
        self._settings.setValue(SYNC_KEY_PATH_KEY, self.key_path_edit.text().strip())
        super().accept()
```

- [ ] **Step 4: Run to verify pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_team_sync_dialog.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/team_sync_dialog.py tests/ui/test_team_sync_dialog.py
git commit -m "feat: team sync settings (repo URL + deploy key) dialog"
```

---

### Task 13: MainWindow — Publish / Fetch / Merge actions + conflicts dialog

**Files:**
- Create: `pgtp_editor/ui/merge_conflicts_dialog.py`
- Modify: `pgtp_editor/ui/main_window.py` (`_build_schema_menu` + new handlers)
- Test: `tests/ui/test_merge_conflicts_dialog.py`, `tests/ui/test_schema_sync_wiring.py`

**Interfaces:**
- Consumes: `sync` module, `merge_models`/`apply_resolution`/`Conflict`, `load_sync_config`/`TeamSyncSettingsDialog`, `run_async` (already imported in main_window), `Model`, `generate_xsd`, `schema_model_path`/`schema_xsd_path`.
- Produces:
  - `MergeConflictsDialog(conflicts, parent=None)` with `resolutions() -> list[bool]` (True = use incoming), aligned index-wise with the given conflicts.
  - Menu: "Publish My Annotations", "Fetch Team Master", "Merge Team Models…", "Team Sync Settings…" between the annotate group and the viewers.
  - Audit-line conventions: `[Schema] Published annotations as …`, `[Schema] Fetched team master …`, `[Schema] CONFLICT (kept local): …`, `[Schema] Sync failed: …`, `[Schema] Merge aborted — nothing was pushed.`

- [ ] **Step 1: Write the failing tests.**

Create `tests/ui/test_merge_conflicts_dialog.py` (GPL header, then):

```python
from pgtp_editor.schema_learning.merge import Conflict
from pgtp_editor.ui.merge_conflicts_dialog import MergeConflictsDialog


def test_default_resolution_keeps_master_and_can_switch(qtbot):
    conflicts = [
        Conflict("Root", "a", "labels", "4", "pdf", "PDF export"),
        Conflict("Root", "a", "kind", None, "setting", "content"),
    ]
    dialog = MergeConflictsDialog(conflicts)
    qtbot.addWidget(dialog)
    assert dialog.resolutions() == [False, False]
    dialog.choice_combo(0).setCurrentIndex(1)  # use incoming
    assert dialog.resolutions() == [True, False]
```

Create `tests/ui/test_schema_sync_wiring.py` — reuse the same MainWindow fixture as Task 8, plus a synchronous `run_async` stand-in and monkeypatched sync functions:

```python
import pytest

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import schema_model_path
from pgtp_editor.schema_learning.sync import SyncConfig, SyncError
from pgtp_editor.ui import main_window as main_window_module
from pgtp_editor.ui.team_sync_dialog import SYNC_REPO_URL_KEY


@pytest.fixture(autouse=True)
def synchronous_run_async(monkeypatch):
    def fake_run_async(fn, on_result, on_error=None, pool=None):
        try:
            value = fn()
        except Exception as exc:  # mirror the real seam's catch-all
            if on_error is not None:
                on_error(exc)
            return None
        on_result(value)
        return None

    monkeypatch.setattr(main_window_module, "run_async", fake_run_async)


def _audit_lines(window):
    return [window.audit_panel.item(i).text()
            for i in range(window.audit_panel.count())]


def test_publish_unconfigured_shows_status_only(window):
    window._publish_my_annotations()
    assert not any("[Schema] Publish" in line for line in _audit_lines(window))


def test_publish_reports_success(window, monkeypatch):
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")
    Model().save(schema_model_path(window._schema_storage_dir))
    monkeypatch.setattr(
        main_window_module.sync, "publish_model",
        lambda config, path, username=None: "models/alice.json",
    )
    window._publish_my_annotations()
    assert "[Schema] Published annotations as models/alice.json" in _audit_lines(window)


def test_publish_failure_reports_audit_line(window, monkeypatch):
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")
    Model().save(schema_model_path(window._schema_storage_dir))
    def boom(config, path, username=None):
        raise SyncError("no network")
    monkeypatch.setattr(main_window_module.sync, "publish_model", boom)
    window._publish_my_annotations()
    assert any("[Schema] Sync failed: no network" in line
               for line in _audit_lines(window))


def test_fetch_master_merges_into_local_model(window, monkeypatch, tmp_path):
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")
    remote = Model()
    remote.paths = {"Root": {
        "attributes": {"a": {"type": "integer", "values": ["1"],
                             "overflowed": False, "attr_seen_count": 1,
                             "labels": {"1": "A"}}},
        "children": {}, "instance_count": 1, "order": [],
        "order_stable": True, "has_text": False,
    }}
    master_file = tmp_path / "master.json"
    remote.save(master_file)
    monkeypatch.setattr(
        main_window_module.sync, "fetch_master", lambda config: master_file
    )
    window._fetch_team_master()
    local = Model.load(schema_model_path(window._schema_storage_dir))
    assert local.paths["Root"]["attributes"]["a"]["labels"] == {"1": "A"}
    assert any("Fetched team master" in line for line in _audit_lines(window))
```

- [ ] **Step 2: Run to verify failure**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_merge_conflicts_dialog.py tests\ui\test_schema_sync_wiring.py -q`
Expected: FAIL — missing module / missing handlers.

- [ ] **Step 3: Implement.**

3a. Create `pgtp_editor/ui/merge_conflicts_dialog.py` (GPL header, then):

```python
"""MergeConflictsDialog: the admin's never-silent gate when folding team
models into master.json — one row per (path, attr, field, value) label
conflict, with an explicit keep-master / use-incoming choice per row."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

_HEADERS = ["Element Path", "Attribute", "Field", "Value", "Keep"]
CHOICE_COLUMN = 4


class MergeConflictsDialog(QDialog):
    def __init__(self, conflicts, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Merge Conflicts ({len(conflicts)})")
        self._conflicts = list(conflicts)

        self.table = QTableWidget(len(self._conflicts), len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        for row, conflict in enumerate(self._conflicts):
            for column, text in enumerate([
                conflict.path,
                conflict.attr,
                conflict.field,
                conflict.value or "",
            ]):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
            combo = QComboBox()
            combo.addItem(f"master: {conflict.base}")
            combo.addItem(f"incoming: {conflict.incoming}")
            self.table.setCellWidget(row, CHOICE_COLUMN, combo)
        self.table.resizeColumnsToContents()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def choice_combo(self, row):
        return self.table.cellWidget(row, CHOICE_COLUMN)

    def resolutions(self):
        """True per row where the incoming value should replace master's."""
        return [
            self.choice_combo(row).currentIndex() == 1
            for row in range(len(self._conflicts))
        ]
```

3b. `main_window.py` imports:

```python
from pgtp_editor.schema_learning import sync
from pgtp_editor.schema_learning.merge import apply_resolution, merge_models
from pgtp_editor.ui.merge_conflicts_dialog import MergeConflictsDialog
from pgtp_editor.ui.team_sync_dialog import TeamSyncSettingsDialog, load_sync_config
```

3c. Extend `_build_schema_menu` — after the "Next Unlabeled Value" action's `menu.addSeparator()`, insert:

```python
        publish_action = menu.addAction("Publish My Annotations")
        publish_action.triggered.connect(self._publish_my_annotations)
        fetch_action = menu.addAction("Fetch Team Master")
        fetch_action.triggered.connect(self._fetch_team_master)
        merge_action = menu.addAction("Merge Team Models…")
        merge_action.triggered.connect(self._merge_team_models)
        sync_settings_action = menu.addAction("Team Sync Settings…")
        sync_settings_action.triggered.connect(self._open_team_sync_settings)
        menu.addSeparator()
```

3d. Handlers (place after `_open_labels_viewer`):

```python
    def _sync_config(self):
        """The configured SyncConfig, or None (with a pointer to the
        settings dialog in the status bar)."""
        config = load_sync_config(self._settings, self._schema_storage_dir)
        if config is None:
            self.statusBar().showMessage(
                "Team sync is not configured — Schema ▸ Team Sync Settings…", 5000
            )
        return config

    def _open_team_sync_settings(self):
        dialog = TeamSyncSettingsDialog(self._settings, self)
        dialog.exec()

    def _publish_my_annotations(self):
        config = self._sync_config()
        if config is None:
            return
        model_path = schema_model_path(self._schema_storage_dir)
        if not model_path.exists():
            self.statusBar().showMessage(self._NO_SCHEMA_MESSAGE, 5000)
            return
        self.statusBar().showMessage("Publishing annotations…")
        run_async(
            lambda: sync.publish_model(config, model_path),
            self._on_publish_done,
            self._on_sync_error,
        )

    def _on_publish_done(self, published):
        if published is None:
            self.audit_panel.addItem("[Schema] Publish: no changes since last publish.")
        else:
            self.audit_panel.addItem(f"[Schema] Published annotations as {published}")
        self.statusBar().clearMessage()

    def _on_sync_error(self, exc):
        """Any sync failure: local model/XSD untouched, one audit line."""
        self.audit_panel.addItem(f"[Schema] Sync failed: {exc}")
        self.statusBar().clearMessage()

    def _fetch_team_master(self):
        config = self._sync_config()
        if config is None:
            return

        def job():
            master = sync.fetch_master(config)
            if master is None:
                raise sync.SyncError("no master.json in the team repo yet")
            return Model.load(master)

        self.statusBar().showMessage("Fetching team master…")
        run_async(job, self._on_master_fetched, self._on_sync_error)

    def _on_master_fetched(self, remote_model):
        model_path = schema_model_path(self._schema_storage_dir)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        local = Model.load(model_path) if model_path.exists() else Model()
        conflicts = merge_models(local, remote_model)
        local.save(model_path)
        schema_xsd_path(self._schema_storage_dir).write_text(
            generate_xsd(local), encoding="utf-8"
        )
        self.center_stage.xml_editor.set_schema_model(local)
        self.audit_panel.addItem(
            "[Schema] Fetched team master and merged it into the local model."
        )
        for conflict in conflicts[:20]:
            self.audit_panel.addItem(
                f"[Schema] CONFLICT (kept local): {conflict.path}@{conflict.attr}"
                f' {conflict.field} "{conflict.value or ""}"'
                f' local="{conflict.base}" master="{conflict.incoming}"'
            )
        if len(conflicts) > 20:
            self.audit_panel.addItem(
                f"[Schema] …and {len(conflicts) - 20} more conflicts (kept local)."
            )
        self.statusBar().clearMessage()

    def _merge_team_models(self):
        config = self._sync_config()
        if config is None:
            return

        def job():
            paths = sync.team_model_paths(config)
            master_path = Path(config.clone_dir) / "master.json"
            master = Model.load(master_path) if master_path.exists() else Model()
            return master, [(p.stem, Model.load(p)) for p in paths]

        self.statusBar().showMessage("Merging team models…")
        run_async(
            job,
            lambda result: self._on_team_models_loaded(config, result),
            self._on_sync_error,
        )

    def _on_team_models_loaded(self, config, result):
        master, user_models = result
        if not user_models:
            self.audit_panel.addItem(
                "[Schema] Merge: no models/*.json in the team repo yet."
            )
            self.statusBar().clearMessage()
            return
        conflicts = []
        for _name, user_model in user_models:
            conflicts.extend(merge_models(master, user_model))
        if conflicts:
            dialog = MergeConflictsDialog(conflicts, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.audit_panel.addItem("[Schema] Merge aborted — nothing was pushed.")
                self.statusBar().clearMessage()
                return
            for use_incoming, conflict in zip(dialog.resolutions(), conflicts):
                apply_resolution(master, conflict, use_incoming)
        run_async(
            lambda: sync.push_master(config, master),
            self._on_master_pushed,
            self._on_sync_error,
        )

    def _on_master_pushed(self, pushed):
        self.audit_panel.addItem(
            "[Schema] Merged team models into master and pushed."
            if pushed
            else "[Schema] Merge: master unchanged — nothing to push."
        )
        self.audit_panel.addItem(
            "[Schema] Run Schema ▸ Fetch Team Master to update your local model."
        )
        self.statusBar().clearMessage()
```

(`QDialog` and `Path` are already imported in main_window; verify and add if not.)

- [ ] **Step 4: Run to verify pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_merge_conflicts_dialog.py tests\ui\test_schema_sync_wiring.py tests\ui\test_menus.py -q`
Expected: PASS (update `test_menus.py` if it snapshots the Schema menu).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/merge_conflicts_dialog.py pgtp_editor/ui/main_window.py tests/ui/test_merge_conflicts_dialog.py tests/ui/test_schema_sync_wiring.py tests/ui/test_menus.py
git commit -m "feat: Publish/Fetch/Merge team schema actions with conflict gate"
```

---

### Task 14: Finalization — full suite, agents, spec sync

- [ ] **Step 1: Full suite**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`
Expected: PASS. Fix any stragglers before proceeding.

- [ ] **Step 2: Dispatch `feature-tester`** (per CLAUDE.md testing policy) with: feature name "Annotate-at-cursor labeling + team schema-model sharing", spec section §11 of `docs/superpowers/CONSOLIDATED_SPEC.md`, this plan file, and the changed-file list from `git diff --name-only main`. Iterate until green; it appends the `docs/TEST_LOG.md` entry.

- [ ] **Step 3: Dispatch `manual-maintainer`** (after feature-tester is green) with the same inputs — the manual must cover: the annotate popover (Ctrl+L / right-click "Annotate value…"), dotted underlines, Next Unlabeled Value (Ctrl+Shift+L), the Schema menu's Publish/Fetch/Merge/Team Sync Settings actions, and the note that `schema.xsd` is generated (hand-edits don't persist).

- [ ] **Step 4: Dispatch `spec-maintainer`** for a sync pass: confirm the deleted dialog, record the implemented shortcut for Next Unlabeled Value (Ctrl+Shift+L) in §23, add "Team Sync Settings…" to the §11/§22 Schema-menu lists, and resolve the corresponding §25 open-question row.

- [ ] **Step 5: Commit any log/manual/spec updates together with the final state**

```bash
git add -A
git commit -m "docs: TEST_LOG entry, manual + spec sync for annotate/team-sharing"
```

---

## Self-Review Notes

- **Spec coverage:** §11 Model fields (`notes`, `enum_mode`) — Tasks 1, 8; union `known_values` — Task 2; bit-flags derivation + surfacing in completion/hover/XSD — Tasks 1–3; annotation popover with all four controls — Tasks 6, 8; Ctrl+L + context menu — Tasks 7, 8; underlines + Next Unlabeled Value — Task 5; dialog deletion — Task 9; merge engine with never-silent conflicts — Task 10; git transport with deploy key + per-user files + retry — Task 11; settings-configurable repo URL/key — Task 12; three menu actions with failure behavior (local model untouched, `[Schema]` audit lines) — Task 13; XSD-regeneration-on-every-mutation — Tasks 8, 13. The endgame freeze is explicitly out of scope (spec §25 open question).
- **Value completion popup** already renders `value = label` and derived labels arrive via `known_values` — no `_show_value_completions` change needed.
- **Type consistency check:** `effective_labels`/`derived_bitflag_label`/`value_note` (Task 1) match their uses in Tasks 2, 3, 5; `Conflict` fields (Task 10) match `MergeConflictsDialog` and audit lines (Task 13); `SyncConfig(repo_url, clone_dir, key_path)` (Task 11) matches `load_sync_config` (Task 12) and all Task 13 call sites; popover payload keys `label/note/kind/bitflags` (Task 6) match `_apply_annotation` (Task 8).
