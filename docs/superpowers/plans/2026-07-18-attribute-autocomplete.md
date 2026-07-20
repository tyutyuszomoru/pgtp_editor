# Ctrl+Space Attribute Autocomplete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ctrl+Space inside an opening tag in the Raw XML editor pops up the schema's attributes for that element (minus present ones); Tab/Enter inserts `name=""` with the caret between the quotes; if the attribute has known values, a second popup chains in to pick the value.

**Architecture:** Two Qt-free query helpers in `schema_learning/settings_index.py` (`known_attributes`, `known_values`) read the same in-memory `Model` the XSD is generated from. A reusable `_CompletionPopup(QListWidget)` in `ui/xml_editor.py` serves both stages (attribute list, then value list): it holds a filter string, navigates with arrows, emits `chosen(str)`/`cancelled`, and is shown non-modally at the caret. `XmlEditor.keyPressEvent` traps Ctrl+Space and calls testable `_show_attribute_completions()` / `_show_value_completions()` seams; insertion reuses the exact `_insert_attribute` splice. Empty candidate list → silent no-op (no status signal exists on the editor; keeping it silent avoids new coupling and matches the "no-op when nothing to offer" behavior of `unused_attributes_at`).

**Tech Stack:** Python 3.10+, PySide6 (Qt6), pytest + pytest-qt, offscreen Qt. Follow the repo's hard rules: no unpatched modals in tests (popup is a non-modal child widget driven by methods/signals + one real keypress), pure logic stays Qt-free and unit-tested.

---

### Task 1: `known_attributes` pure helper

**Files:**
- Modify: `pgtp_editor/schema_learning/settings_index.py`
- Test: `tests/schema_learning/test_settings_index.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/schema_learning/test_settings_index.py`. Add `known_attributes` to the existing import block at the top of the file (line 2-7), so it reads:

```python
from pgtp_editor.schema_learning.settings_index import (
    attribute_kind,
    enum_hint,
    is_enum_candidate,
    known_attributes,
    unused_setting_attributes,
)
```

Then append these tests (reuse the file's existing `_model_settings`-style helper by defining a local one, since the module-level `_model_with` builds a single-attr path):

```python
def _model_multi(tag_chain, names, kind="setting"):
    model = Model()
    attributes = {
        name: {
            "type": "integer",
            "values": ["1", "2"],
            "overflowed": False,
            "attr_seen_count": 2,
            "labels": {},
            "kind": kind,
        }
        for name in names
    }
    model.paths[tag_chain] = {
        "attributes": attributes,
        "children": {},
        "instance_count": 1,
        "order": [],
        "order_stable": True,
        "has_text": False,
    }
    return model


def test_known_attributes_returns_all_minus_present_sorted():
    model = _model_multi("Root/Node", ["zeta", "alpha", "mid"])
    assert known_attributes(model, "Root/Node", {"mid"}) == ["alpha", "zeta"]


def test_known_attributes_not_filtered_by_kind():
    # unclassified/content attributes are still offered (broad list)
    model = _model_multi("Root/Node", ["a", "b"], kind="content")
    assert known_attributes(model, "Root/Node", set()) == ["a", "b"]


def test_known_attributes_empty_present_returns_all():
    model = _model_multi("Root/Node", ["a", "b"])
    assert known_attributes(model, "Root/Node", []) == ["a", "b"]


def test_known_attributes_unknown_path_returns_empty():
    model = _model_multi("Root/Node", ["a"])
    assert known_attributes(model, "Root/Missing", set()) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/schema_learning/test_settings_index.py -k known_attributes -q`
Expected: FAIL — `ImportError: cannot import name 'known_attributes'`.

- [ ] **Step 3: Write minimal implementation**

Append to `pgtp_editor/schema_learning/settings_index.py`:

```python
def known_attributes(model, tag_chain, present_attrs) -> list[str]:
    """Sorted names of every attribute the schema records at ``tag_chain`` that
    the element does not already carry.

    Unlike ``unused_setting_attributes`` this is NOT filtered by kind — the full
    set the model has observed for the element is offered (the broad list the
    XSD shows). ``present_attrs`` is a collection of names already on the tag.
    An unknown ``tag_chain`` yields ``[]``.
    """
    attributes = model.paths.get(tag_chain, {}).get("attributes", {})
    present = set(present_attrs)
    return sorted(name for name in attributes if name not in present)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/schema_learning/test_settings_index.py -k known_attributes -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/schema_learning/settings_index.py tests/schema_learning/test_settings_index.py
git commit -m "feat: known_attributes schema query helper"
```

---

### Task 2: `known_values` pure helper

**Files:**
- Modify: `pgtp_editor/schema_learning/settings_index.py`
- Test: `tests/schema_learning/test_settings_index.py`

- [ ] **Step 1: Write the failing tests**

Add `known_values` to the same import block (keep alphabetical: after `known_attributes`). Append these tests:

```python
def _model_one(entry, tag_chain="Root/Node", attr="editAbilityMode"):
    model = Model()
    model.paths[tag_chain] = {
        "attributes": {attr: entry},
        "children": {},
        "instance_count": 1,
        "order": [],
        "order_stable": True,
        "has_text": False,
    }
    return model


def test_known_values_pairs_sorted_with_labels():
    entry = {
        "type": "integer",
        "values": ["3", "0", "2"],
        "overflowed": False,
        "attr_seen_count": 3,
        "labels": {"0": "none", "3": "full"},
    }
    model = _model_one(entry)
    assert known_values(model, "Root/Node", "editAbilityMode") == [
        ("0", "none"),
        ("2", None),
        ("3", "full"),
    ]


def test_known_values_empty_when_overflowed():
    entry = {
        "type": "string",
        "values": ["a", "b"],
        "overflowed": True,
        "attr_seen_count": 9,
        "labels": {},
    }
    model = _model_one(entry)
    assert known_values(model, "Root/Node", "editAbilityMode") == []


def test_known_values_empty_when_no_values():
    entry = {
        "type": "string",
        "values": [],
        "overflowed": False,
        "attr_seen_count": 0,
        "labels": {},
    }
    model = _model_one(entry)
    assert known_values(model, "Root/Node", "editAbilityMode") == []


def test_known_values_empty_for_unknown_attr():
    entry = {
        "type": "integer",
        "values": ["1"],
        "overflowed": False,
        "attr_seen_count": 1,
        "labels": {},
    }
    model = _model_one(entry)
    assert known_values(model, "Root/Node", "missing") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/schema_learning/test_settings_index.py -k known_values -q`
Expected: FAIL — `ImportError: cannot import name 'known_values'`.

- [ ] **Step 3: Write minimal implementation**

Append to `pgtp_editor/schema_learning/settings_index.py`:

```python
def known_values(model, tag_chain, attr) -> list[tuple[str, str | None]]:
    """Sorted ``(value, label)`` pairs for an attribute's known value set at
    ``tag_chain`` — the same values ``enum_hint`` renders. ``label`` is
    ``labels.get(value)`` or ``None``.

    Returns ``[]`` when the attribute is unknown at the path, its entry is
    ``overflowed``, or it has no ``values`` (nothing reliable to offer). Not
    filtered by kind, so any enumerated attribute chains into the value picker.
    """
    entry = model.paths.get(tag_chain, {}).get("attributes", {}).get(attr)
    if entry is None or entry.get("overflowed") or not entry.get("values"):
        return []
    labels = entry.get("labels") or {}
    return [(value, labels.get(value)) for value in sorted(entry["values"])]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/schema_learning/test_settings_index.py -k known_values -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/schema_learning/settings_index.py tests/schema_learning/test_settings_index.py
git commit -m "feat: known_values schema query helper"
```

---

### Task 3: `_CompletionPopup` widget

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor_completion.py` (create)

A `QListWidget` subclass that holds a master list of `(key, display)` items plus a running filter string, navigates with arrows (base behavior), filters case-insensitively by key prefix, and emits `chosen(str)` / `cancelled`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_xml_editor_completion.py`:

```python
"""Ctrl+Space attribute/value completion: the reusable _CompletionPopup and
the XmlEditor seams that drive it (never via a blocking modal)."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.ui.xml_editor import XmlEditor, _CompletionPopup


def _popup(qtbot, items):
    popup = _CompletionPopup()
    qtbot.addWidget(popup)
    popup.set_items(items)
    return popup


def test_popup_lists_all_keys_initially(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha"), ("beta", "beta")])
    assert popup.visible_keys() == ["alpha", "beta"]
    assert popup.current_key() == "alpha"  # row 0 preselected


def test_popup_filter_prefix_case_insensitive(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha"), ("Album", "Album"), ("beta", "beta")])
    popup.append_filter("al")
    assert popup.visible_keys() == ["Album", "alpha"]
    assert popup.current_key() == "Album"  # sorted order preserved, row 0


def test_popup_backspace_restores(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha"), ("beta", "beta")])
    popup.append_filter("a")
    assert popup.visible_keys() == ["alpha"]
    popup.backspace_filter()
    assert popup.visible_keys() == ["alpha", "beta"]


def test_popup_display_differs_from_key(qtbot):
    popup = _popup(qtbot, [("2", "2 = new page"), ("1", "1 = modal")])
    # keys drive filtering/selection; display is what the row shows
    assert popup.visible_keys() == ["1", "2"]
    item0 = popup.item(0)
    assert item0.text() == "1 = modal"


def test_popup_enter_emits_chosen_current_key(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha"), ("beta", "beta")])
    with qtbot.waitSignal(popup.chosen, timeout=500) as sig:
        QTest.keyClick(popup, Qt.Key.Key_Return)
    assert sig.args == ["alpha"]


def test_popup_tab_emits_chosen(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha")])
    with qtbot.waitSignal(popup.chosen, timeout=500) as sig:
        QTest.keyClick(popup, Qt.Key.Key_Tab)
    assert sig.args == ["alpha"]


def test_popup_escape_emits_cancelled(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha")])
    with qtbot.waitSignal(popup.cancelled, timeout=500):
        QTest.keyClick(popup, Qt.Key.Key_Escape)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_xml_editor_completion.py -q`
Expected: FAIL — `ImportError: cannot import name '_CompletionPopup'`.

- [ ] **Step 3: Write minimal implementation**

In `pgtp_editor/ui/xml_editor.py`: add `QListWidget` and `QListWidgetItem` to the `PySide6.QtWidgets` import on line 30 so it reads:

```python
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QTextEdit,
    QToolTip,
    QWidget,
)
```

Then add this class at module level (after the pure helpers, before `class XmlEditor`):

```python
class _CompletionPopup(QListWidget):
    """Frameless completion list for the XML editor. Holds a master list of
    ``(key, display)`` items and a running filter; arrows navigate, printable
    chars filter by key prefix (case-insensitive), Enter/Tab choose, Esc
    cancels. Emits the chosen *key* (not the display string)."""

    chosen = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setUniformItemSizes(True)
        self._items: list[tuple[str, str]] = []
        self._filter = ""

    def set_items(self, items: list[tuple[str, str]]) -> None:
        """Replace the master list with ``(key, display)`` pairs and reset the
        filter, selecting the first row."""
        self._items = list(items)
        self._filter = ""
        self._rebuild()

    def append_filter(self, text: str) -> None:
        self._filter += text
        self._rebuild()

    def backspace_filter(self) -> None:
        self._filter = self._filter[:-1]
        self._rebuild()

    def visible_keys(self) -> list[str]:
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]

    def current_key(self):
        item = self.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _rebuild(self) -> None:
        prefix = self._filter.lower()
        self.clear()
        for key, display in self._items:
            if key.lower().startswith(prefix):
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.addItem(item)
        if self.count():
            self.setCurrentRow(0)

    def _choose_current(self) -> None:
        key = self.current_key()
        if key is not None:
            self.chosen.emit(key)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            self._choose_current()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        if key == Qt.Key.Key_Backspace:
            self.backspace_filter()
            event.accept()
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            super().keyPressEvent(event)
            return
        text = event.text()
        if text and text.isprintable() and not text.isspace():
            self.append_filter(text)
            event.accept()
            return
        super().keyPressEvent(event)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_xml_editor_completion.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor_completion.py
git commit -m "feat: _CompletionPopup filtered list widget for editor autocomplete"
```

---

### Task 4: Attribute completion — Ctrl+Space trigger + insert

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor_completion.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_xml_editor_completion.py`:

```python
def _model_attrs(tag_chain, names):
    model = Model()
    model.paths[tag_chain] = {
        "attributes": {
            n: {
                "type": "integer",
                "values": [],
                "overflowed": False,
                "attr_seen_count": 1,
                "labels": {},
            }
            for n in names
        },
        "children": {},
        "instance_count": 1,
        "order": [],
        "order_stable": True,
        "has_text": False,
    }
    return model


def _editor_in_tag(qtbot, text, model, marker):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    editor.set_schema_model(model)
    cursor = editor.textCursor()
    cursor.setPosition(text.index(marker))
    editor.setTextCursor(cursor)
    return editor


def test_ctrl_space_opens_attribute_popup(qtbot):
    text = '<Page editFormMode="1"></Page>'
    model = _model_attrs("Page", ["editFormMode", "pageMode", "layout"])
    editor = _editor_in_tag(qtbot, text, model, "Page")
    QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    popup = editor._completion_popup
    assert popup.isVisible()
    assert popup.visible_keys() == ["layout", "pageMode"]  # present editFormMode excluded


def test_ctrl_space_no_popup_without_model(qtbot):
    text = '<Page editFormMode="1"></Page>'
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("Page"))
    editor.setTextCursor(cursor)
    QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    assert editor._completion_popup is None or not editor._completion_popup.isVisible()


def test_ctrl_space_no_popup_when_read_only(qtbot):
    text = '<Page editFormMode="1"></Page>'
    model = _model_attrs("Page", ["pageMode"])
    editor = _editor_in_tag(qtbot, text, model, "Page")
    editor.setReadOnly(True)
    QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    assert editor._completion_popup is None or not editor._completion_popup.isVisible()


def test_ctrl_space_no_popup_outside_tag(qtbot):
    text = "<Page>body</Page>"
    model = _model_attrs("Page", ["pageMode"])
    editor = _editor_in_tag(qtbot, text, model, "body")
    QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    assert editor._completion_popup is None or not editor._completion_popup.isVisible()


def test_choosing_attribute_inserts_name_equals_quotes(qtbot):
    text = '<Page editFormMode="1"></Page>'
    model = _model_attrs("Page", ["pageMode"])
    editor = _editor_in_tag(qtbot, text, model, "Page")
    editor._show_attribute_completions()
    editor._completion_popup.chosen.emit("pageMode")
    new_text = editor.toPlainText()
    assert new_text == '<Page editFormMode="1" pageMode=""></Page>'
    caret = editor.textCursor().position()
    assert new_text[caret - 1] == '"' and new_text[caret] == '"'
    assert not editor._completion_popup.isVisible()  # popup dismissed after choose


def test_attribute_insert_is_single_undo(qtbot):
    text = '<Page editFormMode="1"></Page>'
    model = _model_attrs("Page", ["pageMode"])
    editor = _editor_in_tag(qtbot, text, model, "Page")
    editor._show_attribute_completions()
    editor._completion_popup.chosen.emit("pageMode")
    assert "pageMode" in editor.toPlainText()
    editor.undo()
    assert editor.toPlainText() == text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_xml_editor_completion.py -k "ctrl_space or attribute_insert or choosing_attribute" -q`
Expected: FAIL — `AttributeError: 'XmlEditor' object has no attribute '_completion_popup'` / `_show_attribute_completions`.

- [ ] **Step 3: Write minimal implementation**

In `XmlEditor.__init__`, add an instance attribute (place near the other UI state, e.g. right after `self._schema_model` is initialized — search for `self._schema_model` in `__init__`; if it is only set in `set_schema_model`, add the init in `__init__` alongside other `self._...` defaults):

```python
        self._completion_popup: _CompletionPopup | None = None
```

In `keyPressEvent`, immediately AFTER the Ctrl+Y / Ctrl+Shift+Z redo block (after line ~1008, before the `Key_Return` handling) add:

```python
        if mods == ctrl and event.key() == Qt.Key.Key_Space:
            self._show_attribute_completions()
            event.accept()
            return
```

Add these methods to `XmlEditor` (near `_insert_attribute`):

```python
    def _ensure_completion_popup(self) -> "_CompletionPopup":
        if self._completion_popup is None:
            self._completion_popup = _CompletionPopup(self)
        return self._completion_popup

    def _popup_at_caret(self, popup: "_CompletionPopup") -> None:
        """Show ``popup`` just below the caret and give it focus."""
        rect = self.cursorRect()
        point = self.viewport().mapToGlobal(rect.bottomLeft())
        popup.move(point)
        popup.show()
        popup.setFocus()

    def _show_attribute_completions(self) -> None:
        """Ctrl+Space entry point. Opens the attribute popup for the opening tag
        at the caret. No-op when read-only, no model, not inside an opening tag,
        or nothing unused is left to offer."""
        if self.isReadOnly() or self._schema_model is None:
            return
        resolved = enclosing_open_tag(self.toPlainText(), self.textCursor().position())
        if resolved is None:
            return
        tag_chain, present_attrs, _insert_pos = resolved
        names = known_attributes(self._schema_model, tag_chain, present_attrs)
        if not names:
            return
        popup = self._ensure_completion_popup()
        popup.set_items([(n, n) for n in names])
        try:
            popup.chosen.disconnect()
            popup.cancelled.disconnect()
        except (RuntimeError, TypeError):
            pass
        popup.chosen.connect(self._complete_attribute)
        popup.cancelled.connect(popup.hide)
        self._popup_at_caret(popup)

    def _complete_attribute(self, name: str) -> None:
        """Insert ``name=""`` at the caret's opening tag (single undoable edit,
        caret between the quotes), hide the attribute popup, then chain into the
        value picker when the schema knows values for ``name``."""
        popup = self._completion_popup
        if popup is not None:
            popup.hide()
        resolved = enclosing_open_tag(self.toPlainText(), self.textCursor().position())
        if resolved is None:
            return
        tag_chain, _present, insert_pos = resolved
        fragment = f' {name}=""'
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.setPosition(insert_pos)
        cursor.insertText(fragment)
        cursor.endEditBlock()
        caret = insert_pos + len(fragment) - 1  # between the quotes
        cursor.setPosition(caret)
        self.setTextCursor(cursor)
        values = known_values(self._schema_model, tag_chain, name)
        if values:
            self._show_value_completions(values)
```

Add `known_attributes` and `known_values` to the `from pgtp_editor.schema_learning.settings_index import (...)` block (line 32).

> Note: `_show_value_completions` is added in Task 5. For this task, either stub it as a no-op method returning `None` OR order the work so Task 5's method exists. To keep Task 4 green in isolation, add a temporary stub now and replace it in Task 5:
> ```python
>     def _show_value_completions(self, pairs) -> None:  # replaced in Task 5
>         return None
> ```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_xml_editor_completion.py -q`
Expected: PASS (all attribute + popup tests).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor_completion.py
git commit -m "feat: Ctrl+Space attribute completion popup + insert"
```

---

### Task 5: Value-picker chaining

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py`
- Test: `tests/ui/test_xml_editor_completion.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_xml_editor_completion.py`:

```python
def _model_valued(tag_chain, attr, values, labels=None):
    model = Model()
    model.paths[tag_chain] = {
        "attributes": {
            attr: {
                "type": "integer",
                "values": values,
                "overflowed": False,
                "attr_seen_count": len(values),
                "labels": labels or {},
            }
        },
        "children": {},
        "instance_count": 1,
        "order": [],
        "order_stable": True,
        "has_text": False,
    }
    return model


def test_choosing_valued_attribute_chains_value_popup(qtbot):
    text = "<Page></Page>"
    model = _model_valued("Page", "editAbilityMode", ["0", "2", "3"], {"0": "none"})
    editor = _editor_in_tag(qtbot, text, model, "Page")
    editor._show_attribute_completions()
    editor._completion_popup.chosen.emit("editAbilityMode")
    popup = editor._completion_popup
    assert popup.isVisible()
    assert popup.visible_keys() == ["0", "2", "3"]
    assert popup.item(0).text() == "0 = none"  # label rendered
    assert popup.item(1).text() == "2"  # bare value when unlabeled


def test_choosing_value_inserts_between_quotes(qtbot):
    text = "<Page></Page>"
    model = _model_valued("Page", "editAbilityMode", ["0", "2", "3"])
    editor = _editor_in_tag(qtbot, text, model, "Page")
    editor._show_attribute_completions()
    editor._completion_popup.chosen.emit("editAbilityMode")
    editor._completion_popup.chosen.emit("2")
    new_text = editor.toPlainText()
    assert new_text == '<Page editAbilityMode="2"></Page>'
    caret = editor.textCursor().position()
    assert new_text[caret - 1] == '"'  # caret lands just after the closing quote
    assert not editor._completion_popup.isVisible()


def test_attribute_without_values_opens_no_value_popup(qtbot):
    text = "<Page></Page>"
    model = _model_valued("Page", "caption", [])  # empty values -> no chain
    editor = _editor_in_tag(qtbot, text, model, "Page")
    editor._show_attribute_completions()
    editor._completion_popup.chosen.emit("caption")
    new_text = editor.toPlainText()
    assert new_text == '<Page caption=""></Page>'
    assert not editor._completion_popup.isVisible()
    caret = editor.textCursor().position()
    assert new_text[caret - 1] == '"' and new_text[caret] == '"'  # between quotes


def test_value_escape_leaves_empty_value(qtbot):
    text = "<Page></Page>"
    model = _model_valued("Page", "editAbilityMode", ["0", "2"])
    editor = _editor_in_tag(qtbot, text, model, "Page")
    editor._show_attribute_completions()
    editor._completion_popup.chosen.emit("editAbilityMode")
    editor._completion_popup.cancelled.emit()
    assert editor.toPlainText() == '<Page editAbilityMode=""></Page>'
    assert not editor._completion_popup.isVisible()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_xml_editor_completion.py -k "value" -q`
Expected: FAIL — value popup never appears (stub returns None) / value not inserted.

- [ ] **Step 3: Write the implementation**

Replace the Task-4 `_show_value_completions` stub with the real method, and add `_complete_value`:

```python
    def _show_value_completions(self, pairs) -> None:
        """Open the value picker for the just-inserted attribute. ``pairs`` is a
        list of ``(value, label)``; rows show ``value`` or ``value = label`` but
        carry the bare value as their key. The caret is between the quotes."""
        popup = self._ensure_completion_popup()
        items = [
            (value, f"{value} = {label}" if label else value)
            for value, label in pairs
        ]
        popup.set_items(items)
        try:
            popup.chosen.disconnect()
            popup.cancelled.disconnect()
        except (RuntimeError, TypeError):
            pass
        popup.chosen.connect(self._complete_value)
        popup.cancelled.connect(popup.hide)
        self._popup_at_caret(popup)

    def _complete_value(self, value: str) -> None:
        """Insert ``value`` at the caret (between the quotes) as one undoable
        edit, move the caret just after the closing quote, and hide the popup."""
        popup = self._completion_popup
        if popup is not None:
            popup.hide()
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.insertText(value)
        cursor.endEditBlock()
        cursor.setPosition(cursor.position() + 1)  # step past the closing quote
        self.setTextCursor(cursor)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_xml_editor_completion.py -q`
Expected: PASS (all completion tests).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor_completion.py
git commit -m "feat: chain attribute completion into value picker"
```

---

### Task 6: End-to-end keypress flow + manual note

**Files:**
- Modify: `pgtp_editor/resources/manual.md`
- Test: `tests/ui/test_xml_editor_completion.py`

- [ ] **Step 1: Write the failing end-to-end test**

Append to `tests/ui/test_xml_editor_completion.py`. This drives the whole flow through real keystrokes on the popup (filter → Tab → value pick):

```python
def test_end_to_end_ctrl_space_filter_tab_value(qtbot):
    text = "<Page></Page>"
    model = _model_valued("Page", "editAbilityMode", ["0", "2", "3"], {"2": "inline"})
    # also offer a decoy attribute so filtering is meaningful
    model.paths["Page"]["attributes"]["caption"] = {
        "type": "string", "values": [], "overflowed": False,
        "attr_seen_count": 1, "labels": {},
    }
    editor = _editor_in_tag(qtbot, text, model, "Page")

    QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    popup = editor._completion_popup
    assert popup.visible_keys() == ["caption", "editAbilityMode"]

    # type "edit" to filter down, then Tab to insert
    for ch in "edit":
        QTest.keyClick(popup, ch)
    assert popup.visible_keys() == ["editAbilityMode"]
    QTest.keyClick(popup, Qt.Key.Key_Tab)

    # value picker now open; pick "2" via Down+Enter
    assert popup.visible_keys() == ["0", "2", "3"]
    QTest.keyClick(popup, Qt.Key.Key_Down)  # select "2"
    QTest.keyClick(popup, Qt.Key.Key_Return)

    assert editor.toPlainText() == '<Page editAbilityMode="2"></Page>'
```

- [ ] **Step 2: Run test to verify it fails (or passes)**

Run: `python -m pytest tests/ui/test_xml_editor_completion.py::test_end_to_end_ctrl_space_filter_tab_value -q`
Expected: PASS if Tasks 3-5 are correct. If it FAILS, the failure pinpoints a real wiring gap (e.g., popup not receiving keys because focus wasn't set) — fix in `xml_editor.py`, do not weaken the test.

- [ ] **Step 3: Add the manual note**

In `pgtp_editor/resources/manual.md`, find the Raw XML editor feature description (search for "Add attribute" or "right-click"). Add a sentence to that section:

```markdown
Press **Ctrl+Space** inside an opening tag to list the attributes the schema
knows for that element; use the arrow keys and **Tab** (or Enter) to insert the
chosen one as `name=""`. When the attribute has known values, a second list
appears so you can pick the value too. **Esc** dismisses either list.
```

- [ ] **Step 4: Run the full suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: PASS — previous total + the new tests, 0 failures. (Real-sample tests may skip as usual.)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/resources/manual.md tests/ui/test_xml_editor_completion.py
git commit -m "test: end-to-end Ctrl+Space flow; docs: manual note"
```

---

## Self-review notes

- **Spec coverage:** `known_attributes` (Task 1), `known_values` (Task 2), popup with filter/nav/choose/cancel (Task 3), Ctrl+Space trigger + guards + `name=""` insert reusing the splice (Task 4), value chaining with label rendering + Esc-leaves-empty (Task 5), end-to-end keypress + manual note (Task 6). Every spec section maps to a task.
- **Deviation from spec:** the spec's "brief status message" when there are no candidates is implemented as a silent no-op (the editor exposes no status signal; adding one is out of scope). Behavior otherwise matches.
- **Type consistency:** popup items are `(key, display)` throughout; `chosen` always carries the key; `known_values` returns `(value, label|None)` which Task 5 maps to `(value, display)`. `enclosing_open_tag` returns `(tag_chain, present_attrs, insert_pos)` everywhere it is used.
- **Insertion:** `_complete_attribute` re-derives `insert_pos` from the live buffer (identical to the existing `_insert_attribute`) so a single `beginEditBlock`/`endEditBlock` yields one undo step; `_complete_value` inserts between the quotes and steps the caret past the closing quote.
