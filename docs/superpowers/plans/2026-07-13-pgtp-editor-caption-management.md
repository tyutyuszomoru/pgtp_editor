# PGTP Editor — Caption Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Excel-style, filterable Caption Management grid that lists every caption-like attribute in the active project and writes edits back into the in-memory Raw XML buffer on exact source lines, while freezing (hiding) Raw XML for the duration of the session.

**Architecture:** A pure, Qt-free core (`pgtp_editor/ui/caption_scan.py`) provides `CaptionEntry`, `scan_captions(text)` and `apply_caption_edits(text, edits)` — the riskiest correctness (attribute-boundary-safe regex replace, XML escaping, line-anchored write-back) lives here and is fully unit-tested. A `CaptionManagementPanel(QWidget)` hosts a `QTableView` + a model fed through a multi-column `QSortFilterProxyModel` subclass; it is decoupled from `MainWindow` via injected callbacks (the `FindReplaceBar` pattern). `CenterStage` hosts the panel in its Caption Management tab and makes Raw XML the default-visible tab; `MainWindow`'s Tools → Manage Captions… snapshots + scans + enters caption mode (hiding Raw XML), Apply writes edits into the editor buffer, Close restores Raw XML.

**Tech Stack:** Python 3.13, PySide6 (Qt widgets), lxml, pytest, pytest-qt, pytest-timeout.

---

## Current-state facts (confirmed by reading this worktree)

These were verified by reading the code on branch `worktree-pgtp-editor-caption-management`. Do not re-derive them — use them.

- **Search & Replace is already implemented in this worktree.** `pgtp_editor/ui/center_stage.py`, `pgtp_editor/ui/main_window.py`, `pgtp_editor/ui/xml_editor.py`, `pgtp_editor/ui/find_replace_bar.py`, `pgtp_editor/ui/search.py`, and the corresponding tests already exist and pass. This plan builds on that state.
- `pgtp_editor/ui/center_stage.py`: `CenterStage(QTabWidget)` builds, **in this order**: `self.diff_merge_panel` → tab `"Diff / Merge"` (`self.diff_merge_tab_index`); `self.caption_management_tab_index = self.addTab(QWidget(), "Caption Management")` — **the Caption Management tab is currently an empty placeholder `QWidget()`, not stored on an attribute**; then `self.xml_editor = XmlEditor()`, `self.find_replace_bar = FindReplaceBar(self.xml_editor)`, wrapped in `self.raw_xml_tab` (a `QWidget` with a `QVBoxLayout` holding editor + bar), added as tab `"Raw XML"` (`self.raw_xml_tab_index`). The **last line of `__init__` is `self.setTabVisible(self.raw_xml_tab_index, False)`** — Raw XML is hidden by default today. `set_raw_xml_tab_visible(visible)` exists. So today the tab order is Diff/Merge(0), Caption Management(1), Raw XML(2), with only Diff/Merge and Caption Management visible.
- `pgtp_editor/ui/main_window.py`:
  - `_build_tools_menu` currently does `self._add_stub_action(menu, "Manage Captions...")` (label has a literal ASCII `...`, three dots), then separators, `Find Reused Tables...`, `Validate Project`, and a real `Reparse Raw XML into Tree` wired to `_reparse_raw_xml`.
  - `self.center_stage = CenterStage()` is created in `__init__` and `self.setCentralWidget(self.center_stage)`; then `line_clicked`, `find_replace_bar.set_on_find_all(...)`, and `audit_panel.itemClicked` are connected. `self.audit_panel` is a `QListWidget`. `_build_menu_bar()` is the last statement of `__init__`.
  - `_build_menu_bar` calls, in order: `_build_file_menu`, `_build_edit_menu`, `_build_view_menu`, `_build_diff_merge_menu`, `_build_schema_menu`, `_build_tools_menu`, `_build_generation_menu`, `_build_help_menu`. So `_build_view_menu` (which creates `self._raw_xml_panel_action`) runs **before** `_build_tools_menu`.
  - Raw-XML reveal helper `_reveal_raw_xml_tab(self)` exists: `set_raw_xml_tab_visible(True)` + `self._raw_xml_panel_action.setChecked(True)` + `setCurrentIndex(raw_xml_tab_index)`.
  - `self._current_project` is set in `open_project_file` (and `_reparse_raw_xml`); it is `None` until a project is loaded.
  - The QtWidgets import block imports `QDockWidget, QFileDialog, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QWidget`. `Qt` is imported from `PySide6.QtCore`.
  - `_add_stub_action(self, menu, label)` delegates to `add_stub_action(menu, label, self._not_implemented)`.
  - `statusBar().showMessage(msg, 5000)` is the established status-message pattern.
- `pgtp_editor/ui/xml_editor.py`: `XmlEditor(QPlainTextEdit)` — text is read with `toPlainText()` and set with `setPlainText(text)` (overridden to reset fold state). No caption-specific methods.
- `tests/ui/test_center_stage.py`: asserts `stage.count() == 3`; `tabText(0)=="Diff / Merge"`, `tabText(1)=="Caption Management"`, `tabText(2)=="Raw XML"`; **`test_raw_xml_tab_hidden_by_default` asserts `stage.isTabVisible(stage.raw_xml_tab_index) is False`** (this must change to the new default). Also has identity tests for the diff panel, the raw-xml container (`stage.raw_xml_tab`, `stage.xml_editor.parent() is stage.raw_xml_tab`), and the find/replace bar.
- `tests/ui/test_menus.py`: `test_tools_menu_contents` asserts the exact label list `["Manage Captions...", "―", "Find Reused Tables...", "―", "Validate Project", "―", "Reparse Raw XML into Tree"]` — this stays valid (the label is unchanged; only the wiring changes from stub to real). `test_view_menu_default_checked_states` asserts `Raw XML Panel` action `isChecked() is False`. Separators render as `"―"`. Helpers `action_labels`, `find_top_menu`, `find_action` live in `tests/ui/_menu_helpers.py`.
- `pgtp_editor/model/encoding.py`: `read_pgtp_text(path)` returns CESU-8-repaired UTF-8 text.
- `pgtp_editor/model/parser.py`: `load_project(path)` and `load_project_from_text(text, source_description="<editor>")` exist (not needed by the pure core, which parses with lxml directly).
- **lxml facts (verified in this worktree with a live check):** for `etree.fromstring(text.encode("utf-8"))`, `element.sourceline` is the 1-based line of the element's **opening tag**; a `.pgtp` opening tag with several attributes is on a **single line**, so all of an element's attributes share that one `sourceline`. `element.attrib` returns **decoded** values (`caption="A &amp; B"` → `"A & B"`). Malformed XML raises `etree.XMLSyntaxError`.
- Tests run headless via `conftest.py` (`QT_QPA_PLATFORM=offscreen`) with `--timeout=60 --timeout-method=thread` in `pyproject.toml`. **A test that reaches an un-patched modal (`QMessageBox.*`, `QDialog.exec()`, `QFileDialog.*`) hangs and is killed at 60s.** No feature here should reach an un-patched modal in a test.
- Real sample files live at `sample/dev_Ferrara.pgtp` (gitignored, may be absent). The skip pattern is `if not path.exists(): pytest.skip(...)`, with `SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"`. **They are absent in this worktree**, so the real-sample test will skip here.

---

## File Structure

- **Create** `pgtp_editor/ui/caption_scan.py` — pure Qt-free core: `CaptionEntry`, `CAPTION_ATTRIBUTES`, `scan_captions`, `apply_caption_edits` (Tasks 1–2).
- **Create** `pgtp_editor/ui/caption_management_panel.py` — `CaptionManagementPanel(QWidget)` + `_CaptionFilterProxyModel` (Tasks 3–6).
- **Modify** `pgtp_editor/ui/center_stage.py` — host the panel in the Caption Management tab; make Raw XML the default-visible tab; add `caption_management_panel` + visibility swap helpers (Task 7).
- **Modify** `pgtp_editor/ui/main_window.py` — wire Tools → Manage Captions… to enter/apply/close caption mode (Task 8).
- **Modify** `tests/ui/test_center_stage.py` — update default-visibility assertions (Task 7).
- **Create** `tests/ui/test_caption_scan.py` (Qt-free, Tasks 1–2), `tests/ui/test_caption_management_panel.py` (pytest-qt, Tasks 3–6).
- **Extend** `tests/ui/test_main_window.py` — caption-mode integration (Task 8).
- **Create** `tests/ui/test_caption_scan_real_sample.py` — real-sample smoke, skips if absent (Task 9).
- **Full-suite verification** (Task 10).

---

## Task 1: Pure core — `CaptionEntry` + `scan_captions`

**Files:**
- Create: `pgtp_editor/ui/caption_scan.py`
- Test: `tests/ui/test_caption_scan.py` (new file — Qt-free)

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_caption_scan.py`:

```python
from pgtp_editor.ui.caption_scan import CAPTION_ATTRIBUTES, CaptionEntry, scan_captions


def test_caption_attributes_fixed_order():
    assert CAPTION_ATTRIBUTES == (
        "caption",
        "shortCaption",
        "headerHint",
        "insertFormCaption",
        "groupName",
    )


def test_caption_entry_is_frozen_dataclass():
    entry = CaptionEntry(
        line=2, element_tag="Page", anchor="p1", attribute="caption", value="Hello"
    )
    assert (entry.line, entry.element_tag, entry.anchor, entry.attribute, entry.value) == (
        2,
        "Page",
        "p1",
        "caption",
        "Hello",
    )
    import dataclasses
    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.value = "changed"


def test_scan_single_attribute():
    text = '<Root>\n  <Page caption="Home" fileName="home"/>\n</Root>'
    entries = scan_captions(text)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.line == 2
    assert entry.element_tag == "Page"
    assert entry.attribute == "caption"
    assert entry.value == "Home"


def test_scan_multi_attribute_line_yields_one_row_per_attribute_in_fixed_order():
    # A single line carrying caption + shortCaption + groupName -> 3 rows,
    # ordered by the fixed CAPTION_ATTRIBUTES order, all on the same line.
    text = (
        "<Root>\n"
        '  <Page groupName="G" caption="C" shortCaption="S" fileName="home"/>\n'
        "</Root>"
    )
    entries = scan_captions(text)
    assert [(e.attribute, e.value, e.line) for e in entries] == [
        ("caption", "C", 2),
        ("shortCaption", "S", 2),
        ("groupName", "G", 2),
    ]


def test_scan_document_order_then_attribute_order():
    text = (
        "<Root>\n"
        '  <Page caption="P1" fileName="a"/>\n'
        '  <Detail caption="D1" shortCaption="D1s" tableName="t"/>\n'
        "</Root>"
    )
    entries = scan_captions(text)
    assert [(e.element_tag, e.attribute, e.line) for e in entries] == [
        ("Page", "caption", 2),
        ("Detail", "caption", 3),
        ("Detail", "shortCaption", 3),
    ]


def test_scan_decodes_entities_from_lxml():
    text = '<Root>\n  <Page caption="A &amp; B &lt;x&gt;"/>\n</Root>'
    entries = scan_captions(text)
    assert entries[0].value == "A & B <x>"


def test_scan_all_five_attributes():
    text = (
        "<Root>\n"
        '  <X caption="c" shortCaption="sc" headerHint="hh" '
        'insertFormCaption="ifc" groupName="gn"/>\n'
        "</Root>"
    )
    entries = scan_captions(text)
    assert [e.attribute for e in entries] == list(CAPTION_ATTRIBUTES)


def test_scan_ignores_non_caption_attributes():
    text = '<Root>\n  <Page fileName="home" tableName="t"/>\n</Root>'
    assert scan_captions(text) == []


def test_scan_malformed_text_returns_empty_list():
    assert scan_captions("<a><b></a>") == []


def test_scan_empty_text_returns_empty_list():
    assert scan_captions("") == []


def test_anchor_prefers_fieldName():
    text = '<Root>\n  <ColumnPresentation caption="C" fieldName="col1" tableName="t"/>\n</Root>'
    assert scan_captions(text)[0].anchor == "col1"


def test_anchor_falls_back_to_fileName_then_tableName_then_tag():
    file_text = '<Root>\n  <Page caption="C" fileName="home"/>\n</Root>'
    assert scan_captions(file_text)[0].anchor == "home"

    table_text = '<Root>\n  <Detail caption="C" tableName="t1"/>\n</Root>'
    assert scan_captions(table_text)[0].anchor == "t1"

    tag_text = '<Root>\n  <MenuGroup caption="C"/>\n</Root>'
    assert scan_captions(tag_text)[0].anchor == "MenuGroup"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_caption_scan.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgtp_editor.ui.caption_scan'`

- [ ] **Step 3: Create `caption_scan.py` (scan half only for now)**

Create `pgtp_editor/ui/caption_scan.py`:

```python
# pgtp_editor/ui/caption_scan.py
"""Pure, Qt-free scan/apply core for Caption Management.

`scan_captions(text)` parses the frozen Raw XML text with lxml and emits one
CaptionEntry per caption-like attribute (in the fixed CAPTION_ATTRIBUTES
order) on every element that carries one. `apply_caption_edits(text, edits)`
writes edited values back onto their exact source lines, byte-for-byte
preserving every unedited line. Both functions are Qt-free and fully
unit-tested; the riskiest correctness (attribute-boundary-safe replacement,
XML attribute escaping) lives here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

# The caption-like attributes collected by the scan, in the fixed emission
# order (spec §3). A line carrying several of these yields one row per
# attribute in this order.
CAPTION_ATTRIBUTES: tuple[str, ...] = (
    "caption",
    "shortCaption",
    "headerHint",
    "insertFormCaption",
    "groupName",
)

# Anchor resolution: prefer fieldName (columns), then fileName (pages), then
# tableName (details), else the element tag. Used for the Anchor column and
# inconsistency highlighting only -- never for write-back.
_ANCHOR_ATTRIBUTES: tuple[str, ...] = ("fieldName", "fileName", "tableName")


@dataclass(frozen=True)
class CaptionEntry:
    """One caption-like attribute found on one element.

    line:         1-based source line of the element's opening tag
                  (lxml `sourceline`). All attributes of a .pgtp element
                  share this single line (opening tags are single-line).
    element_tag:  the element's tag, e.g. "Page", "ColumnPresentation".
    anchor:       human-readable context/coherence key (fieldName, else
                  fileName, else tableName, else the tag). Display + grouping
                  only; not used for write-back.
    attribute:    one of CAPTION_ATTRIBUTES.
    value:        the decoded (unescaped) current value, as lxml returns it.
    """

    line: int
    element_tag: str
    anchor: str
    attribute: str
    value: str


def scan_captions(text: str) -> list[CaptionEntry]:
    """Return every caption-like attribute in `text`, in document order then
    CAPTION_ATTRIBUTES order. Returns [] if `text` is not well-formed XML
    (caption mode is only entered on a parsed project; this is defensive)."""
    try:
        root = etree.fromstring(text.encode("utf-8"))
    except etree.XMLSyntaxError:
        return []

    entries: list[CaptionEntry] = []
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue  # skip comments / processing instructions
        line = element.sourceline
        if line is None:
            continue  # defensive; not expected for parsed elements
        anchor = _resolve_anchor(element)
        for attribute in CAPTION_ATTRIBUTES:
            if attribute in element.attrib:
                entries.append(
                    CaptionEntry(
                        line=line,
                        element_tag=element.tag,
                        anchor=anchor,
                        attribute=attribute,
                        value=element.attrib[attribute],
                    )
                )
    return entries


def _resolve_anchor(element) -> str:
    for anchor_attribute in _ANCHOR_ATTRIBUTES:
        value = element.attrib.get(anchor_attribute)
        if value:
            return value
    return element.tag
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_caption_scan.py -v`
Expected: PASS (all scan tests).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/caption_scan.py tests/ui/test_caption_scan.py
git commit -m "feat: add Qt-free caption scan core (CaptionEntry/scan_captions)"
```

---

## Task 2: Pure core — `apply_caption_edits` (boundary-safe, escaping, line-anchored)

**Files:**
- Modify: `pgtp_editor/ui/caption_scan.py` (add `apply_caption_edits` + helpers)
- Test: `tests/ui/test_caption_scan.py` (append apply tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_caption_scan.py`:

```python
from pgtp_editor.ui.caption_scan import apply_caption_edits
from lxml import etree as _etree


def _entry(line, attribute, element_tag="Page", anchor="a", value=""):
    return CaptionEntry(
        line=line, element_tag=element_tag, anchor=anchor, attribute=attribute, value=value
    )


def test_apply_replaces_single_attribute_value():
    text = '<Root>\n  <Page caption="Old" fileName="home"/>\n</Root>'
    result = apply_caption_edits(text, [(_entry(2, "caption"), "New")])
    assert result == '<Root>\n  <Page caption="New" fileName="home"/>\n</Root>'


def test_apply_empty_edit_set_is_identity():
    text = '<Root>\n  <Page caption="Old"/>\n</Root>'
    assert apply_caption_edits(text, []) == text


def test_apply_preserves_unedited_lines_byte_for_byte():
    text = (
        "<Root>\n"
        '  <Page caption="Old" fileName="home"/>\n'
        '  <Detail caption="Keep" tableName="t"/>\n'
        "</Root>"
    )
    result = apply_caption_edits(text, [(_entry(2, "caption"), "New")])
    lines = result.splitlines(keepends=True)
    original_lines = text.splitlines(keepends=True)
    # Every line except line 2 is byte-identical.
    assert lines[0] == original_lines[0]
    assert lines[2] == original_lines[2]
    assert lines[3] == original_lines[3]
    assert 'caption="New"' in lines[1]


def test_apply_boundary_caption_not_matched_inside_shortCaption():
    # A line with BOTH caption and shortCaption/insertFormCaption: editing
    # `caption` must change ONLY caption, never the tail of the longer names.
    text = (
        "<Root>\n"
        '  <Page insertFormCaption="I" caption="C" shortCaption="S"/>\n'
        "</Root>"
    )
    result = apply_caption_edits(text, [(_entry(2, "caption"), "CHANGED")])
    assert result == (
        "<Root>\n"
        '  <Page insertFormCaption="I" caption="CHANGED" shortCaption="S"/>\n'
        "</Root>"
    )


def test_apply_shortCaption_edit_leaves_caption_untouched():
    text = '<Root>\n  <Page caption="C" shortCaption="S"/>\n</Root>'
    result = apply_caption_edits(text, [(_entry(2, "shortCaption"), "S2")])
    assert result == '<Root>\n  <Page caption="C" shortCaption="S2"/>\n</Root>'


def test_apply_escapes_special_characters_double_quoted():
    text = '<Root>\n  <Page caption="Old"/>\n</Root>'
    result = apply_caption_edits(text, [(_entry(2, "caption"), 'A & B < C > D "q"')])
    # & first, then < > "  -> the raw line contains the escaped form.
    assert 'caption="A &amp; B &lt; C &gt; D &quot;q&quot;"' in result


def test_apply_escaping_round_trips_through_lxml():
    text = '<Root>\n  <Page caption="Old" shortCaption="Keep"/>\n</Root>'
    new_value = 'Tom & Jerry <best> "friends"'
    result = apply_caption_edits(text, [(_entry(2, "caption"), new_value)])
    root = _etree.fromstring(result.encode("utf-8"))
    page = root[0]
    assert page.attrib["caption"] == new_value  # decodes back to the intended string
    assert page.attrib["shortCaption"] == "Keep"  # untouched attribute preserved


def test_apply_multiple_edits_on_same_line():
    text = '<Root>\n  <Page caption="C" shortCaption="S"/>\n</Root>'
    result = apply_caption_edits(
        text,
        [(_entry(2, "caption"), "C2"), (_entry(2, "shortCaption"), "S2")],
    )
    assert result == '<Root>\n  <Page caption="C2" shortCaption="S2"/>\n</Root>'


def test_apply_missing_attribute_on_line_is_skipped_not_crash():
    # Defensive: an edit naming an attribute that isn't on the given line
    # leaves that line unchanged and does not corrupt others.
    text = '<Root>\n  <Page caption="C"/>\n  <Page shortCaption="S"/>\n</Root>'
    result = apply_caption_edits(
        text,
        [
            (_entry(2, "shortCaption"), "WONT_MATCH"),  # line 2 has no shortCaption
            (_entry(3, "shortCaption"), "S2"),
        ],
    )
    assert result == '<Root>\n  <Page caption="C"/>\n  <Page shortCaption="S2"/>\n</Root>'


def test_apply_only_replaces_first_occurrence_on_line():
    # count=1: if the same attribute somehow appears twice on a line, only the
    # first is replaced (matches the scan's single-value read).
    text = '<Root>\n  <Page caption="A" caption="B"/>\n</Root>'
    result = apply_caption_edits(text, [(_entry(2, "caption"), "X")])
    assert result == '<Root>\n  <Page caption="X" caption="B"/>\n</Root>'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_caption_scan.py -v -k "apply"`
Expected: FAIL — `ImportError: cannot import name 'apply_caption_edits'`

- [ ] **Step 3: Add `apply_caption_edits` and helpers**

Append to `pgtp_editor/ui/caption_scan.py`:

```python
def apply_caption_edits(text: str, edits) -> str:
    """Return `text` with each edit's new value written onto its source line.

    `edits` is an iterable of `(entry, new_value)` pairs for CHANGED rows
    only (each `entry` carries the 1-based `line` and the `attribute` name).
    Each edit replaces `attribute="..."` on `text.splitlines(keepends=True)
    [line-1]` with `attribute="<escaped_new_value>"`:

    - The match is anchored with a negative lookbehind on word chars/hyphen so
      the attribute name cannot match the tail of a longer name (critical:
      `caption` must NOT match inside `shortCaption`/`insertFormCaption`).
      count=1 replaces only the first occurrence.
    - The new value is XML-attribute-escaped for a double-quoted attribute
      (& first, then < > "). .pgtp attributes use double quotes.
    - If the pattern does not match on that line (attribute unexpectedly
      absent), the line is left unchanged. Never crashes or corrupts.

    Unedited lines are byte-for-byte unchanged. Relies on the verified .pgtp
    convention that an element's opening tag (all its attributes) is on a
    single line (`sourceline`).
    """
    lines = text.splitlines(keepends=True)
    for entry, new_value in edits:
        index = entry.line - 1
        if not (0 <= index < len(lines)):
            continue  # defensive: line out of range
        lines[index] = _replace_attribute_on_line(lines[index], entry.attribute, new_value)
    return "".join(lines)


def _replace_attribute_on_line(line: str, attribute: str, new_value: str) -> str:
    pattern = re.compile(r'(?<![\w-])' + re.escape(attribute) + r'="[^"]*"')
    replacement = f'{attribute}="{_escape_attribute_value(new_value)}"'
    # re.sub treats backslashes in the replacement specially; pass a function
    # so the (already-escaped) replacement text is inserted verbatim.
    return pattern.sub(lambda _match: replacement, line, count=1)


def _escape_attribute_value(value: str) -> str:
    """Escape `value` for a double-quoted XML attribute. `&` must be escaped
    first so the ampersands introduced by the other replacements are not
    double-escaped."""
    value = value.replace("&", "&amp;")
    value = value.replace("<", "&lt;")
    value = value.replace(">", "&gt;")
    value = value.replace('"', "&quot;")
    return value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_caption_scan.py -v`
Expected: PASS (all scan + apply tests).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/caption_scan.py tests/ui/test_caption_scan.py
git commit -m "feat: add boundary-safe, escaping apply_caption_edits to caption core"
```

---

## Task 3: `CaptionManagementPanel` — model population and read-only/editable columns

**Files:**
- Create: `pgtp_editor/ui/caption_management_panel.py`
- Test: `tests/ui/test_caption_management_panel.py` (new file — pytest-qt)

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_caption_management_panel.py`:

```python
from PySide6.QtCore import Qt

from pgtp_editor.ui.caption_scan import CaptionEntry
from pgtp_editor.ui.caption_management_panel import CaptionManagementPanel


def _entry(line, tag, anchor, attribute, value):
    return CaptionEntry(
        line=line, element_tag=tag, anchor=anchor, attribute=attribute, value=value
    )


def _sample_entries():
    return [
        _entry(2, "Page", "home", "caption", "Home"),
        _entry(3, "Detail", "orders", "caption", "Orders"),
        _entry(3, "Detail", "orders", "shortCaption", "Ord"),
    ]


def test_headers_are_line_element_anchor_attribute_value(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    model = panel._model
    headers = [
        model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        for col in range(model.columnCount())
    ]
    assert headers == ["Line", "Element", "Anchor", "Attribute", "Value"]


def test_load_entries_populates_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    model = panel._model
    assert model.rowCount() == 3
    # Row 0 cells, in column order.
    assert model.index(0, 0).data() == "2"
    assert model.index(0, 1).data() == "Page"
    assert model.index(0, 2).data() == "home"
    assert model.index(0, 3).data() == "caption"
    assert model.index(0, 4).data() == "Home"


def test_only_value_column_is_editable(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    model = panel._model
    for col in range(5):
        flags = model.flags(model.index(0, col))
        editable = bool(flags & Qt.ItemFlag.ItemIsEditable)
        assert editable is (col == 4), f"column {col} editability wrong"


def test_load_entries_replaces_previous_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    panel.load_entries([_entry(9, "X", "a", "caption", "Solo")])
    assert panel._model.rowCount() == 1
    assert panel._model.index(0, 4).data() == "Solo"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_caption_management_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgtp_editor.ui.caption_management_panel'`

- [ ] **Step 3: Create `caption_management_panel.py` (model + panel skeleton)**

Create `pgtp_editor/ui/caption_management_panel.py`:

```python
# pgtp_editor/ui/caption_management_panel.py
"""CaptionManagementPanel: an Excel-style, filterable grid of every
caption-like attribute in the frozen Raw XML. Built on a QAbstractTableModel
fed through a multi-column QSortFilterProxyModel. Only the Value column is
editable; edited rows are tracked and emitted to apply_caption_edits. The
panel is decoupled from MainWindow via injected callbacks (the FindReplaceBar
pattern)."""
from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.ui.caption_scan import CaptionEntry, apply_caption_edits

_COLUMNS = ("Line", "Element", "Anchor", "Attribute", "Value")
_VALUE_COLUMN = 4

# Subtle tint for rows whose (anchor, attribute) group has divergent values.
_INCONSISTENT_BACKGROUND = QColor("#3a2f1d")


class _CaptionTableModel(QAbstractTableModel):
    """Holds the scanned entries and the current (possibly edited) value per
    row. Only the Value column is editable; edits update `_current_values`
    and mark the row dirty. Rows whose (anchor, attribute) group has more than
    one distinct current value are flagged inconsistent (background tint)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[CaptionEntry] = []
        self._current_values: list[str] = []

    # -- population ---------------------------------------------------------

    def set_entries(self, entries: Sequence[CaptionEntry]) -> None:
        self.beginResetModel()
        self._entries = list(entries)
        self._current_values = [entry.value for entry in self._entries]
        self.endResetModel()

    def entries(self) -> list[CaptionEntry]:
        return self._entries

    def changed_edits(self) -> list[tuple[CaptionEntry, str]]:
        """(entry, new_value) for every row whose current value differs from
        the originally-scanned value."""
        return [
            (entry, current)
            for entry, current in zip(self._entries, self._current_values)
            if current != entry.value
        ]

    # -- QAbstractTableModel ------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        column = index.column()
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if column == 0:
                return str(entry.line)
            if column == 1:
                return entry.element_tag
            if column == 2:
                return entry.anchor
            if column == 3:
                return entry.attribute
            if column == _VALUE_COLUMN:
                return self._current_values[index.row()]
        if role == Qt.ItemDataRole.BackgroundRole and self._is_inconsistent(index.row()):
            return _INCONSISTENT_BACKGROUND
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == _VALUE_COLUMN:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() != _VALUE_COLUMN:
            return False
        self._current_values[index.row()] = value
        # Value change can flip inconsistency for the whole (anchor, attribute)
        # group, so repaint the Value column of every row.
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.EditRole])
        top = self.index(0, _VALUE_COLUMN)
        bottom = self.index(self.rowCount() - 1, _VALUE_COLUMN)
        self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.BackgroundRole])
        return True

    # -- inconsistency ------------------------------------------------------

    def _is_inconsistent(self, row: int) -> bool:
        entry = self._entries[row]
        key = (entry.anchor, entry.attribute)
        values = {
            self._current_values[i]
            for i, other in enumerate(self._entries)
            if (other.anchor, other.attribute) == key
        }
        return len(values) > 1


class _CaptionFilterProxyModel(QSortFilterProxyModel):
    """Multi-column filter: a per-column case-insensitive substring filter,
    ANDed across all columns. Empty filters match everything."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._column_filters: dict[int, str] = {}

    def set_column_filter(self, column: int, text: str) -> None:
        self._column_filters[column] = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        model = self.sourceModel()
        for column, needle in self._column_filters.items():
            if not needle:
                continue
            index = model.index(source_row, column, source_parent)
            haystack = (index.data(Qt.ItemDataRole.DisplayRole) or "").lower()
            if needle not in haystack:
                return False
        return True


class CaptionManagementPanel(QWidget):
    def __init__(
        self,
        on_apply: Callable[[str], None] | None = None,
        on_close: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._on_apply = on_apply or (lambda edited_text: None)
        self._on_close = on_close or (lambda: None)
        self._snapshot_text = ""

        self._model = _CaptionTableModel(self)
        self._proxy = _CaptionFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )

        # One filter QLineEdit per column.
        self._filter_row = QWidget()
        filter_layout = QHBoxLayout(self._filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        self._filter_fields: list[QLineEdit] = []
        for column in range(self._model.columnCount()):
            field = QLineEdit()
            field.setPlaceholderText(f"Filter {_COLUMNS[column]}")
            field.textChanged.connect(
                lambda text, col=column: self._proxy.set_column_filter(col, text)
            )
            filter_layout.addWidget(field)
            self._filter_fields.append(field)

        self._apply_button = QPushButton("Apply")
        self._close_button = QPushButton("Close")
        self._apply_button.clicked.connect(self.apply)
        self._close_button.clicked.connect(self.close_panel)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._apply_button)
        button_row.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._filter_row)
        layout.addWidget(self._table)
        layout.addLayout(button_row)

    # -- API ----------------------------------------------------------------

    def load_entries(self, entries: Sequence[CaptionEntry], snapshot_text: str = "") -> None:
        """Populate the grid from a scan. `snapshot_text` is the frozen Raw
        XML the entries were scanned from; apply() writes edits back into it."""
        self._snapshot_text = snapshot_text
        self._model.set_entries(entries)

    def changed_edits(self) -> list[tuple[CaptionEntry, str]]:
        return self._model.changed_edits()

    def apply(self) -> None:
        """Compute the edited text from the snapshot + changed rows and invoke
        the injected on_apply callback with it."""
        edited_text = apply_caption_edits(self._snapshot_text, self._model.changed_edits())
        self._on_apply(edited_text)

    def close_panel(self) -> None:
        self._on_close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_caption_management_panel.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/caption_management_panel.py tests/ui/test_caption_management_panel.py
git commit -m "feat: add CaptionManagementPanel grid model (read-only cols + Value editable)"
```

---

## Task 4: `CaptionManagementPanel` — per-column filtering and sorting

**Files:**
- Modify: `tests/ui/test_caption_management_panel.py` (append; no production change — filtering/sorting implemented in Task 3)

- [ ] **Step 1: Write the tests**

Append to `tests/ui/test_caption_management_panel.py`:

```python
def _visible_value_column(panel):
    proxy = panel._proxy
    return [
        proxy.index(r, 4).data(Qt.ItemDataRole.DisplayRole)
        for r in range(proxy.rowCount())
    ]


def test_filter_value_column_narrows_visible_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Home"),
            _entry(3, "Detail", "orders", "caption", "Orders"),
            _entry(4, "Detail", "orders", "shortCaption", "Ord"),
        ]
    )
    # Column 4 is Value; filtering "ord" (case-insensitive) keeps Orders + Ord.
    panel._filter_fields[4].setText("ord")
    assert sorted(_visible_value_column(panel)) == ["Ord", "Orders"]


def test_filter_attribute_column(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Home"),
            _entry(3, "Detail", "orders", "shortCaption", "Ord"),
        ]
    )
    panel._filter_fields[3].setText("shortcaption")  # case-insensitive
    assert _visible_value_column(panel) == ["Ord"]


def test_filters_are_anded_across_columns(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Home"),
            _entry(3, "Detail", "orders", "caption", "Orders"),
            _entry(4, "Detail", "orders", "shortCaption", "Ord"),
        ]
    )
    panel._filter_fields[1].setText("detail")   # Element == Detail
    panel._filter_fields[3].setText("caption")  # Attribute contains "caption"
    # Both Detail rows have Attribute containing "caption" (caption AND
    # shortCaption), so ANDing keeps both.
    assert sorted(_visible_value_column(panel)) == ["Ord", "Orders"]

    panel._filter_fields[4].setText("orders")   # now also Value contains "orders"
    assert _visible_value_column(panel) == ["Orders"]


def test_empty_filter_shows_all_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Home"),
            _entry(3, "Detail", "orders", "caption", "Orders"),
        ]
    )
    panel._filter_fields[4].setText("home")
    panel._filter_fields[4].setText("")  # cleared
    assert sorted(_visible_value_column(panel)) == ["Home", "Orders"]


def test_sorting_by_value_column(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Zebra"),
            _entry(3, "Detail", "orders", "caption", "Apple"),
        ]
    )
    panel._proxy.sort(4, Qt.SortOrder.AscendingOrder)
    assert _visible_value_column(panel) == ["Apple", "Zebra"]
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_caption_management_panel.py -v -k "filter or sorting"`
Expected: PASS. These pass immediately because the proxy filtering and `setSortingEnabled` were implemented in Task 3; if any fail, fix `_CaptionFilterProxyModel`/the model's `EditRole` data in `caption_management_panel.py` and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_caption_management_panel.py
git commit -m "test: cover CaptionManagementPanel per-column filtering and sorting"
```

---

## Task 5: `CaptionManagementPanel` — dirty tracking and Apply/Close callbacks

**Files:**
- Modify: `tests/ui/test_caption_management_panel.py` (append; no production change — dirty tracking + apply/close implemented in Task 3)

- [ ] **Step 1: Write the tests**

Append to `tests/ui/test_caption_management_panel.py`:

```python
def _set_value(panel, row, text):
    # Set through the source model's Value column, mirroring an editor commit.
    index = panel._model.index(row, 4)
    panel._model.setData(index, text, Qt.ItemDataRole.EditRole)


def test_editing_value_marks_row_changed(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    _set_value(panel, 0, "Homepage")
    assert panel.changed_edits() == [(_sample_entries()[0], "Homepage")]


def test_unchanged_rows_are_not_emitted(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    assert panel.changed_edits() == []


def test_editing_then_restoring_original_value_is_not_dirty(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    _set_value(panel, 0, "Homepage")
    _set_value(panel, 0, "Home")  # back to the original scanned value
    assert panel.changed_edits() == []


def test_apply_invokes_callback_with_edited_text(qtbot):
    captured = {}
    panel = CaptionManagementPanel(on_apply=lambda text: captured.setdefault("text", text))
    qtbot.addWidget(panel)
    snapshot = '<Root>\n  <Page caption="Home" fileName="home"/>\n</Root>'
    entries = [_entry(2, "Page", "home", "caption", "Home")]
    panel.load_entries(entries, snapshot_text=snapshot)
    _set_value(panel, 0, "Homepage")
    panel.apply()
    assert captured["text"] == '<Root>\n  <Page caption="Homepage" fileName="home"/>\n</Root>'


def test_apply_with_no_edits_returns_identical_text(qtbot):
    captured = {}
    panel = CaptionManagementPanel(on_apply=lambda text: captured.setdefault("text", text))
    qtbot.addWidget(panel)
    snapshot = '<Root>\n  <Page caption="Home"/>\n</Root>'
    panel.load_entries([_entry(2, "Page", "home", "caption", "Home")], snapshot_text=snapshot)
    panel.apply()
    assert captured["text"] == snapshot


def test_close_invokes_close_callback(qtbot):
    calls = []
    panel = CaptionManagementPanel(on_close=lambda: calls.append(True))
    qtbot.addWidget(panel)
    panel.close_panel()
    assert calls == [True]
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_caption_management_panel.py -v -k "changed or dirty or restoring or apply or close or unchanged"`
Expected: PASS. These pass because dirty tracking (`changed_edits`) and `apply`/`close_panel` were implemented in Task 3.

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_caption_management_panel.py
git commit -m "test: cover CaptionManagementPanel dirty tracking and apply/close callbacks"
```

---

## Task 6: `CaptionManagementPanel` — inconsistency highlight

**Files:**
- Modify: `tests/ui/test_caption_management_panel.py` (append; no production change — highlight implemented in Task 3)

- [ ] **Step 1: Write the tests**

Append to `tests/ui/test_caption_management_panel.py`:

```python
from pgtp_editor.ui.caption_management_panel import _INCONSISTENT_BACKGROUND


def _background(panel, row):
    return panel._model.index(row, 0).data(Qt.ItemDataRole.BackgroundRole)


def test_divergent_anchor_attribute_group_is_tinted(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    # Same (anchor="acct", attribute="caption") but different values -> both
    # rows flagged inconsistent.
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Accounts"),
        ]
    )
    assert _background(panel, 0) == _INCONSISTENT_BACKGROUND
    assert _background(panel, 1) == _INCONSISTENT_BACKGROUND


def test_consistent_group_is_not_tinted(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Account"),  # identical value
        ]
    )
    assert _background(panel, 0) is None
    assert _background(panel, 1) is None


def test_editing_a_value_can_clear_inconsistency(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Accounts"),
        ]
    )
    assert _background(panel, 0) == _INCONSISTENT_BACKGROUND
    # Align the second row's value with the first -> group now consistent.
    _set_value(panel, 1, "Account")
    assert _background(panel, 0) is None
    assert _background(panel, 1) is None


def test_different_attribute_same_anchor_not_grouped(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    # Same anchor, DIFFERENT attribute -> not the same group -> not tinted.
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(2, "Page", "acct", "shortCaption", "Acct"),
        ]
    )
    assert _background(panel, 0) is None
    assert _background(panel, 1) is None
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_caption_management_panel.py -v -k "tinted or inconsistency or grouped"`
Expected: PASS. Implemented via `_is_inconsistent` + `BackgroundRole` in Task 3.

- [ ] **Step 3: Run the whole panel suite**

Run: `python -m pytest tests/ui/test_caption_management_panel.py -v`
Expected: PASS (all).

- [ ] **Step 4: Commit**

```bash
git add tests/ui/test_caption_management_panel.py
git commit -m "test: cover CaptionManagementPanel inconsistency highlighting"
```

---

## Task 7: `CenterStage` — host the panel + Raw XML as default-visible tab

**Files:**
- Modify: `pgtp_editor/ui/center_stage.py`
- Modify: `tests/ui/test_center_stage.py` (update default-visibility assertions; add panel identity + visibility-swap tests)

- [ ] **Step 1: Update / add the affected tests**

In `tests/ui/test_center_stage.py`, replace the body of `test_raw_xml_tab_hidden_by_default` with the new default (Raw XML visible; the other two hidden), renaming it:

```python
def test_default_tab_visibility_raw_xml_shown_others_hidden(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    # New default (spec §6.1): Raw XML is the working tab; Diff/Merge and
    # Caption Management are revealed only when invoked.
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True
    assert stage.isTabVisible(stage.diff_merge_tab_index) is False
    assert stage.isTabVisible(stage.caption_management_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index
```

Append these new tests to `tests/ui/test_center_stage.py`:

```python
from pgtp_editor.ui.caption_management_panel import CaptionManagementPanel


def test_caption_management_tab_holds_the_panel(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.caption_management_panel, CaptionManagementPanel)
    assert stage.widget(stage.caption_management_tab_index) is stage.caption_management_panel


def test_enter_caption_mode_hides_raw_shows_caption(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_caption_mode()
    assert stage.isTabVisible(stage.raw_xml_tab_index) is False
    assert stage.isTabVisible(stage.caption_management_tab_index) is True
    assert stage.currentIndex() == stage.caption_management_tab_index


def test_leave_caption_mode_restores_raw(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_caption_mode()
    stage.leave_caption_mode()
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True
    assert stage.isTabVisible(stage.caption_management_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index
```

> Note: `test_three_tabs_in_order` (order Diff/Merge, Caption Management, Raw XML) and the existing `test_diff_merge_tab_holds_a_real_diff_merge_panel`, `test_raw_xml_tab_holds_a_real_xml_editor`, `test_raw_xml_tab_container_holds_find_replace_bar`, and `test_set_raw_xml_tab_visible` tests stay unchanged and must still pass.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_center_stage.py -v`
Expected: FAIL — the renamed default-visibility test fails (Raw XML is hidden today); `test_caption_management_tab_holds_the_panel` fails on `stage.caption_management_panel` (no such attribute); the enter/leave tests fail on `enter_caption_mode`/`leave_caption_mode` (no such methods).

- [ ] **Step 3: Update `CenterStage`**

Replace the full contents of `pgtp_editor/ui/center_stage.py` with:

```python
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from pgtp_editor.ui.caption_management_panel import CaptionManagementPanel
from pgtp_editor.ui.diff_merge_panel import DiffMergePanel
from pgtp_editor.ui.find_replace_bar import FindReplaceBar
from pgtp_editor.ui.xml_editor import XmlEditor


class CenterStage(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.diff_merge_panel = DiffMergePanel()
        self.diff_merge_tab_index = self.addTab(self.diff_merge_panel, "Diff / Merge")

        self.caption_management_panel = CaptionManagementPanel()
        self.caption_management_tab_index = self.addTab(
            self.caption_management_panel, "Caption Management"
        )

        self.xml_editor = XmlEditor()
        self.find_replace_bar = FindReplaceBar(self.xml_editor)
        self.raw_xml_tab = QWidget()
        raw_layout = QVBoxLayout(self.raw_xml_tab)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.setSpacing(0)
        raw_layout.addWidget(self.xml_editor)
        raw_layout.addWidget(self.find_replace_bar)
        self.raw_xml_tab_index = self.addTab(self.raw_xml_tab, "Raw XML")

        # New default (spec §6.1): Raw XML is the working tab; Diff/Merge and
        # Caption Management are revealed only when their entry points run.
        self.setTabVisible(self.diff_merge_tab_index, False)
        self.setTabVisible(self.caption_management_tab_index, False)
        self.setTabVisible(self.raw_xml_tab_index, True)
        self.setCurrentIndex(self.raw_xml_tab_index)

    def set_raw_xml_tab_visible(self, visible):
        self.setTabVisible(self.raw_xml_tab_index, visible)

    def enter_caption_mode(self):
        """Freeze/hide Raw XML and reveal + switch to Caption Management."""
        self.setTabVisible(self.raw_xml_tab_index, False)
        self.setTabVisible(self.caption_management_tab_index, True)
        self.setCurrentIndex(self.caption_management_tab_index)

    def leave_caption_mode(self):
        """Hide Caption Management and restore + switch to Raw XML."""
        self.setTabVisible(self.caption_management_tab_index, False)
        self.setTabVisible(self.raw_xml_tab_index, True)
        self.setCurrentIndex(self.raw_xml_tab_index)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_center_stage.py -v`
Expected: PASS (all, including the renamed default-visibility test and the three new tests).

- [ ] **Step 5: Run the menu/main-window tests that depend on Raw XML default visibility**

Run: `python -m pytest tests/ui/test_menus.py tests/ui/test_main_window.py -v`
Expected: mostly PASS. **If any test that previously assumed the Diff/Merge tab was the *current* tab now fails because Raw XML is current, that is a test that codified the old default — update it (do not weaken) to reflect the new default, matching the intent of spec §6.1.** Do not change production behaviour to re-hide Raw XML. In particular the diff-merge flows call `setCurrentIndex(self.center_stage.diff_merge_tab_index)` explicitly, so they remain correct; the parse-failure flow calls `set_raw_xml_tab_visible(True)` which is a no-op-if-already-visible and still switches to Raw XML.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/center_stage.py tests/ui/test_center_stage.py
git commit -m "feat: host CaptionManagementPanel + make Raw XML the default-visible tab"
```

---

## Task 8: `MainWindow` — wire Tools → Manage Captions… (enter / apply / close)

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (`_build_tools_menu` wiring + three handlers + panel-callback wiring in `__init__`)
- Test: `tests/ui/test_main_window.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_main_window.py`:

```python
def test_manage_captions_requires_non_empty_raw_xml(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    # No project / empty editor -> info message, no mode switch.
    window.center_stage.xml_editor.setPlainText("")
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()
    assert window.center_stage.isTabVisible(
        window.center_stage.caption_management_tab_index
    ) is False
    assert "Manage Captions" in window.statusBar().currentMessage()


def test_manage_captions_enters_mode_and_populates_grid(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home" fileName="home"/>\n</Root>'
    )
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()

    stage = window.center_stage
    assert stage.isTabVisible(stage.raw_xml_tab_index) is False
    assert stage.isTabVisible(stage.caption_management_tab_index) is True
    assert stage.currentIndex() == stage.caption_management_tab_index
    assert stage.caption_management_panel._model.rowCount() == 1
    assert stage.caption_management_panel._model.index(0, 4).data() == "Home"


def test_manage_captions_apply_writes_into_editor_buffer_and_reports_count(qtbot):
    from PySide6.QtCore import Qt
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home" fileName="home"/>\n</Root>'
    )
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()

    panel = window.center_stage.caption_management_panel
    panel._model.setData(panel._model.index(0, 4), "Homepage", Qt.ItemDataRole.EditRole)
    panel.apply()

    assert window.center_stage.xml_editor.toPlainText() == (
        '<Root>\n  <Page caption="Homepage" fileName="home"/>\n</Root>'
    )
    assert "1" in window.statusBar().currentMessage()


def test_manage_captions_apply_with_no_edits_reports_zero(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home"/>\n</Root>'
    )
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()

    panel = window.center_stage.caption_management_panel
    panel.apply()
    assert window.center_stage.xml_editor.toPlainText() == (
        '<Root>\n  <Page caption="Home"/>\n</Root>'
    )
    assert "0" in window.statusBar().currentMessage()


def test_manage_captions_close_restores_raw_xml(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home"/>\n</Root>'
    )
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()
    window.center_stage.caption_management_panel.close_panel()

    stage = window.center_stage
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True
    assert stage.isTabVisible(stage.caption_management_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index


def test_manage_captions_apply_then_reedit_uses_updated_snapshot(qtbot):
    from PySide6.QtCore import Qt
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home"/>\n</Root>'
    )
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()
    panel = window.center_stage.caption_management_panel

    panel._model.setData(panel._model.index(0, 4), "Homepage", Qt.ItemDataRole.EditRole)
    panel.apply()  # editor now has caption="Homepage"; snapshot updated

    # A second edit applies cleanly on the updated snapshot (line still valid).
    panel._model.setData(panel._model.index(0, 4), "Landing", Qt.ItemDataRole.EditRole)
    panel.apply()
    assert window.center_stage.xml_editor.toPlainText() == (
        '<Root>\n  <Page caption="Landing"/>\n</Root>'
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_main_window.py -v -k "manage_captions"`
Expected: FAIL — triggering `Manage Captions...` only shows the stub status message ("Not yet implemented: Manage Captions..."), so the caption tab is never revealed and `_enter_caption_mode`/panel wiring doesn't exist.

- [ ] **Step 3: Wire the panel callbacks in `__init__`**

In `pgtp_editor/ui/main_window.py`, in `MainWindow.__init__`, immediately after the existing
`self.audit_panel.itemClicked.connect(self._on_audit_item_clicked)` line (both `self.center_stage` and `self.audit_panel` exist by then), add:

```python
        self.center_stage.caption_management_panel._on_apply = self._apply_caption_edits
        self.center_stage.caption_management_panel._on_close = self._close_caption_mode
```

> These reassign the panel's injected callbacks (the panel was constructed inside `CenterStage` with the default no-op callbacks). `apply()`/`close_panel()` read `self._on_apply`/`self._on_close` at call time, so reassigning here is sufficient — no CenterStage constructor parameter is needed.

- [ ] **Step 4: Replace the Manage Captions… stub with a real action and add the handlers**

In `_build_tools_menu`, replace the line
`self._add_stub_action(menu, "Manage Captions...")`
with:

```python
        manage_captions_action = menu.addAction("Manage Captions...")
        manage_captions_action.triggered.connect(self._enter_caption_mode)
```

Add these three methods to `MainWindow` (place them right after `_replace_all`, keeping the center-stage-mode methods grouped):

```python
    def _enter_caption_mode(self):
        """Tools -> Manage Captions...: snapshot the frozen Raw XML, scan it,
        load the grid, and enter caption mode (Raw XML hidden). Requires
        non-empty Raw XML; otherwise a status message and no mode change."""
        snapshot = self.center_stage.xml_editor.toPlainText()
        if not snapshot.strip():
            self.statusBar().showMessage(
                "Manage Captions: open a project (Raw XML is empty) first.", 5000
            )
            return
        entries = caption_scan.scan_captions(snapshot)
        self.center_stage.caption_management_panel.load_entries(entries, snapshot_text=snapshot)
        self.center_stage.enter_caption_mode()

    def _apply_caption_edits(self, edited_text: str) -> None:
        """Panel Apply callback: count the changed rows, write the edited text
        into the Raw XML editor buffer (in memory only), and refresh the
        panel's snapshot so further edits in the same session stay line-valid."""
        panel = self.center_stage.caption_management_panel
        changed_count = len(panel.changed_edits())
        self.center_stage.xml_editor.setPlainText(edited_text)
        panel.load_entries(caption_scan.scan_captions(edited_text), snapshot_text=edited_text)
        self.statusBar().showMessage(f"Updated {changed_count} caption(s).", 5000)

    def _close_caption_mode(self):
        """Panel Close callback: leave caption mode and restore Raw XML.
        Pending (unapplied) edits are discarded by re-scanning on next enter."""
        self.center_stage.leave_caption_mode()
```

- [ ] **Step 5: Add the `caption_scan` import**

In `pgtp_editor/ui/main_window.py`, next to the existing `from pgtp_editor.ui import search` line, add:

```python
from pgtp_editor.ui import caption_scan
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_main_window.py -v -k "manage_captions"`
Expected: PASS (6 passed). No modal is reached (Close discards silently — the spec makes the confirm prompt optional; this plan omits it, so there is nothing to patch).

- [ ] **Step 7: Confirm the Tools-menu label test still holds**

Run: `python -m pytest tests/ui/test_menus.py -v -k "tools_menu"`
Expected: PASS — `test_tools_menu_contents` is unchanged because the label `"Manage Captions..."` is identical; only the wiring changed from stub to real.

- [ ] **Step 8: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_main_window.py
git commit -m "feat: wire Tools -> Manage Captions... to caption-mode enter/apply/close"
```

---

## Task 9: Real-sample smoke test (skips if `sample/*.pgtp` absent)

**Files:**
- Create: `tests/ui/test_caption_scan_real_sample.py` (new file — Qt-free)

- [ ] **Step 1: Write the test**

Create `tests/ui/test_caption_scan_real_sample.py`:

```python
"""Real-sample smoke test for the caption scan/apply core.

Skips if the gitignored sample file is not present on disk (as in CI /
fresh worktrees). Qt-free -- exercises only the pure core against real data.
"""
from pathlib import Path

import pytest

from pgtp_editor.model.encoding import read_pgtp_text
from pgtp_editor.ui.caption_scan import CAPTION_ATTRIBUTES, apply_caption_edits, scan_captions

SAMPLE = Path(__file__).resolve().parents[2] / "sample" / "dev_Ferrara.pgtp"


def _require_sample():
    if not SAMPLE.exists():
        pytest.skip(f"sample fixture not present on disk: {SAMPLE}")


def test_scan_real_sample_finds_caption_rows():
    _require_sample()
    text = read_pgtp_text(str(SAMPLE))
    entries = scan_captions(text)
    assert entries, "expected at least one caption-like attribute in the sample"
    # Every emitted row names a known caption attribute and sits on a real line.
    for entry in entries:
        assert entry.attribute in CAPTION_ATTRIBUTES
        assert entry.line >= 1
        # The scanned value is exactly what sits (decoded) on that source line;
        # confirm the attribute name literally appears on the reported line.
        source_line = text.splitlines()[entry.line - 1]
        assert f"{entry.attribute}=" in source_line


def test_apply_then_rescan_reflects_change_on_real_sample():
    _require_sample()
    text = read_pgtp_text(str(SAMPLE))
    entries = scan_captions(text)
    target = entries[0]
    new_value = target.value + " [EDITED]"

    edited = apply_caption_edits(text, [(target, new_value)])
    rescanned = scan_captions(edited)

    # The same (line, attribute) row now carries the edited value, and the
    # edited text still parses (rescan is non-empty).
    assert rescanned, "edited text must still be well-formed and scan non-empty"
    match = next(
        e for e in rescanned if e.line == target.line and e.attribute == target.attribute
    )
    assert match.value == new_value
```

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/ui/test_caption_scan_real_sample.py -v`
Expected: SKIPPED (2 skipped) in this worktree — `sample/dev_Ferrara.pgtp` is absent. On a machine where the sample is present, both must PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_caption_scan_real_sample.py
git commit -m "test: real-sample smoke for caption scan/apply (skips if absent)"
```

---

## Task 10: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the entire suite**

Run: `python -m pytest -q`
Expected: all tests pass (0 failures), with the real-sample caption test skipped if the sample is absent. Confirm no test hangs (the `--timeout=60` guard would name any test that reached an un-patched modal; none should).

- [ ] **Step 2: Confirm no un-patched modal was introduced**

Run: `python -m pytest tests/ui/test_main_window.py tests/ui/test_menus.py tests/ui/test_center_stage.py -q`
Expected: PASS with no timeout. (Caption Management adds no `QMessageBox`/`QDialog`/`QFileDialog` calls; `_enter_caption_mode`'s empty-buffer path uses a status-bar message, not a modal.)

- [ ] **Step 3: Commit (if any incidental test updates from Task 7 Step 5 remain unstaged)**

```bash
git add -A
git commit -m "test: full-suite green after caption management (update default-tab assertions)"
```

(If nothing is unstaged, skip this commit.)

---

## Requirement → task traceability (self-review)

- Pure Qt-free core module `caption_scan.py` → **Tasks 1–2** (spec §4, §9).
- `CaptionEntry` frozen dataclass (line/element_tag/anchor/attribute/value) → **Task 1** (§4.1).
- `scan_captions` walks `root.iter()`, fixed attribute order, one row per caption-like attribute; decoded values; `sourceline`; skip `None` sourceline; malformed → `[]` → **Task 1** (§4.2, §7).
- Anchor resolution (fieldName → fileName → tableName → tag) → **Task 1** (§4.1, §8).
- `apply_caption_edits` line-anchored single-line replace, `count=1` → **Task 2** (§4.3, §7).
- Attribute-boundary safety (`(?<![\w-])<attr>="[^"]*"`; `caption` not matched inside `shortCaption`/`insertFormCaption`) → **Task 2** dedicated test (§4.3, §8).
- XML attribute escaping `& < > "` (`&` first) + round-trip → **Task 2** (§4.3, §7, §8).
- Only unedited-line bytes preserved; single-line opening tags (verified) → **Task 2** (§4.3).
- Empty edit set → identity; missing attribute → skipped, no crash → **Task 2** (§7).
- `CaptionManagementPanel` = `QTableView` + model + proxy → **Task 3** (§5, §9).
- Columns Line·Element·Anchor·Attribute·Value; only Value editable; sortable → **Tasks 3–4** (§5).
- Excel-like per-column `QLineEdit` filters ANDed via `filterAcceptsRow` → **Task 4** (§5).
- Inconsistency highlight for divergent `(anchor, attribute)` groups; purely visual → **Task 6** (§5).
- Dirty tracking; only changed rows emitted; injected `on_apply`/`on_close`; `load_entries`/`apply` → **Tasks 3, 5** (§5).
- Apply / Close buttons; Close without Apply discards → **Tasks 5, 8** (§5, §6.2).
- Default tab visibility: Raw XML default-visible, others hidden; existing tests updated (not weakened) → **Task 7** (§6.1, §8).
- Enter caption mode: require non-empty Raw XML; snapshot + scan + load + hide Raw XML + reveal/switch → **Task 8** (§6.2).
- Apply: `apply_caption_edits(snapshot, changed)` → editor buffer (in memory) + status count; snapshot refreshed for same-session re-edits → **Task 8** (§6.2).
- Close/leave restores Raw XML → **Tasks 7, 8** (§6.2).
- No unpatched modal; headless `--timeout=60` guard noted → **Tasks 8, 10** (§8).
- Real-sample smoke, skips if absent → **Task 9** (§8).
- Full-suite verification + update existing center_stage/menu tests → **Tasks 7, 10** (§8).
- Out of scope (Translate via Claude; grouped canonical-value UI; disk persistence/.bak; auto-reparse after Apply) → intentionally **not** built (§2).

## Blocked / follow-up work (not part of this plan)

- **Translate via Claude** (bulk LLM translation) reusing this grid + line-anchored apply — deferred follow-up (spec §2).
- Grouped "pick one canonical value" coherence UI (the original §6.3) — intentionally cut (spec §2).
- Auto-reparsing the tree after Apply — the user runs the existing Tools → Reparse Raw XML into Tree (spec §2).
