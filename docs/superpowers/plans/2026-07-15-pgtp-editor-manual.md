# PGTP Editor Manual — Implementation Plan

> **For agentic workers:** Use TDD. Steps use checkbox (`- [ ]`) syntax.

**Goal:** An in-app English Markdown manual: a center-stage **Manual** tab
(rendered) plus a left-dock **Contents** tab (chapter list that scrolls the manual),
opened via **Help ▸ Manual** (F1).

**Architecture:** `manual.md` is a bundled package resource. `manual_panel.py`
provides the loader, a heading parser, a `QTextBrowser` renderer, and a
`QTreeWidget` contents panel. `center_stage.py` gains a hidden Manual tab;
`main_window.py` wraps the left dock in a tabbed [Project | Contents] widget, wires
Help ▸ Manual (F1), and populates both panels once at construction.

**Tech Stack:** PySide6 (QTextBrowser, QTreeWidget, QTabWidget), importlib.resources,
pytest + pytest-qt, `QT_QPA_PLATFORM=offscreen`.

**Modal-hang guardrail:** No test may reach an unpatched `QMessageBox` /
`QDialog.exec()` / `QFileDialog`. Drive methods and signals directly. The Manual
feature has no modal dialogs — keep it that way.

**Already created (do not recreate):**
- `pgtp_editor/resources/manual.md` — the full manual content.
- `docs/superpowers/specs/2026-07-15-pgtp-editor-manual-design.md` — the spec.

---

### Task 1: Package the manual resource

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/ui/test_manual_resource.py`

- [ ] **Step 1: Failing test** — the bundled file is loadable as package data.

```python
# tests/ui/test_manual_resource.py
from importlib.resources import files


def test_manual_md_is_a_package_resource():
    res = files("pgtp_editor") / "resources" / "manual.md"
    text = res.read_text(encoding="utf-8")
    assert text.startswith("# PGTP Editor")
    assert "## Getting Started" in text
```

- [ ] **Step 2: Run — expect PASS already** (the file exists on disk in the source
  tree; this test guards its presence). Run:
  `python -m pytest tests/ui/test_manual_resource.py -q`

- [ ] **Step 3: Add package-data so it ships in an installed build.** Add to
  `pyproject.toml` after the `[tool.setuptools.packages.find]` block:

```toml
[tool.setuptools.package-data]
"pgtp_editor" = ["resources/*.md"]
```

- [ ] **Step 4: Run test — expect PASS.**

- [ ] **Step 5: Commit** — `git add -A && git commit -m "chore: package manual.md as a resource"`

---

### Task 2: Manual loader + chapter parser

**Files:**
- Create: `pgtp_editor/ui/manual_panel.py`
- Test: `tests/ui/test_manual_panel.py`

- [ ] **Step 1: Failing tests** for the pure functions.

```python
# tests/ui/test_manual_panel.py
from pgtp_editor.ui.manual_panel import Chapter, load_manual_text, parse_chapters


def test_load_manual_text_returns_bundled_content():
    text = load_manual_text()
    assert text.startswith("# PGTP Editor")
    assert "## The Code Editor" in text


def test_parse_chapters_levels_and_titles_in_order():
    md = "# Title\n\nintro\n\n## One\ntext\n\n### One-a\n\n## Two\n"
    chs = parse_chapters(md)
    assert chs == [
        Chapter(1, "Title"),
        Chapter(2, "One"),
        Chapter(3, "One-a"),
        Chapter(2, "Two"),
    ]


def test_parse_chapters_ignores_headings_in_code_fences():
    md = "# T\n\n```\n# not a heading\n## also not\n```\n\n## Real\n"
    chs = parse_chapters(md)
    assert chs == [Chapter(1, "T"), Chapter(2, "Real")]


def test_parse_chapters_ignores_tilde_fences_and_hash_without_space():
    md = "# T\n\n~~~\n## nope\n~~~\n\n#nospace not a heading\n\n## Real\n"
    chs = parse_chapters(md)
    assert chs == [Chapter(1, "T"), Chapter(2, "Real")]


def test_parse_chapters_trims_and_matches_real_manual():
    # The 1:1 heading model requires every heading to parse cleanly.
    chs = parse_chapters(load_manual_text())
    assert chs[0] == Chapter(1, "PGTP Editor")
    assert any(c == Chapter(2, "Caption Management") for c in chs)
    assert all(c.title == c.title.strip() and c.title for c in chs)
```

- [ ] **Step 2: Run — expect FAIL** (module missing).
  `python -m pytest tests/ui/test_manual_panel.py -q`

- [ ] **Step 3: Implement the loader + parser** (top of `manual_panel.py`):

```python
from dataclasses import dataclass
from importlib.resources import files

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextBrowser, QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt, Signal


@dataclass(frozen=True)
class Chapter:
    level: int
    title: str


def load_manual_text() -> str:
    resource = files("pgtp_editor") / "resources" / "manual.md"
    return resource.read_text(encoding="utf-8")


def parse_chapters(md_text: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    in_fence = False
    fence_marker = ""
    for raw in md_text.splitlines():
        stripped = raw.strip()
        if in_fence:
            if stripped.startswith(fence_marker):
                in_fence = False
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = True
            fence_marker = stripped[:3]
            continue
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            rest = stripped[hashes:]
            # ATX heading requires a space after the hashes (CommonMark/Qt).
            if 1 <= hashes <= 6 and rest.startswith(" "):
                title = rest.strip()
                if title:
                    chapters.append(Chapter(hashes, title))
    return chapters
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit** — `git commit -am "feat: manual loader and chapter parser"`

---

### Task 3: ManualPanel (renderer + scroll)

**Files:**
- Modify: `pgtp_editor/ui/manual_panel.py`
- Test: `tests/ui/test_manual_panel.py`

- [ ] **Step 1: Failing tests.**

```python
def test_manual_panel_renders_and_scrolls_to_chapter(qtbot):
    from pgtp_editor.ui.manual_panel import ManualPanel, parse_chapters
    md = "# T\n\nintro\n\n## One\naaa\n\n## Two\nbbb\n\n## Three\nccc\n"
    panel = ManualPanel()
    qtbot.addWidget(panel)
    panel.set_markdown(md)
    chapters = parse_chapters(md)
    # scroll to "Two" (index 2): cursor block text must equal that heading.
    panel.scroll_to_chapter(2)
    assert panel.textCursor().block().text() == chapters[2].title
    panel.scroll_to_chapter(999)  # out of range: no crash, no move
    assert panel.textCursor().block().text() == chapters[2].title


def test_manual_heading_count_matches_parse_chapters(qtbot):
    from pgtp_editor.ui.manual_panel import ManualPanel, load_manual_text, parse_chapters
    text = load_manual_text()
    panel = ManualPanel()
    qtbot.addWidget(panel)
    panel.set_markdown(text)
    # Count heading blocks Qt produced.
    doc = panel.document()
    heading_blocks = 0
    block = doc.begin()
    while block.isValid():
        if block.blockFormat().headingLevel() > 0:
            heading_blocks += 1
        block = block.next()
    assert heading_blocks == len(parse_chapters(text))
```

- [ ] **Step 2: Run — expect FAIL** (ManualPanel missing).

- [ ] **Step 3: Implement `ManualPanel`** (append to `manual_panel.py`):

```python
class ManualPanel(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self._markdown = ""

    def set_markdown(self, text: str) -> None:
        self._markdown = text
        self.setMarkdown(text)

    def scroll_to_chapter(self, index: int) -> None:
        if index < 0:
            return
        doc = self.document()
        seen = -1
        block = doc.begin()
        while block.isValid():
            if block.blockFormat().headingLevel() > 0:
                seen += 1
                if seen == index:
                    cursor = QTextCursor(block)
                    self.setTextCursor(cursor)
                    top = self.cursorRect().top()
                    bar = self.verticalScrollBar()
                    bar.setValue(bar.value() + top)
                    return
            block = block.next()
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit** — `git commit -am "feat: ManualPanel rendering and positional scroll"`

---

### Task 4: ManualContentsPanel (chapter tree)

**Files:**
- Modify: `pgtp_editor/ui/manual_panel.py`
- Test: `tests/ui/test_manual_panel.py`

- [ ] **Step 1: Failing tests.**

```python
def test_contents_panel_emits_positional_index(qtbot):
    from pgtp_editor.ui.manual_panel import Chapter, ManualContentsPanel
    panel = ManualContentsPanel()
    qtbot.addWidget(panel)
    chapters = [
        Chapter(1, "Title"), Chapter(2, "One"),
        Chapter(3, "One-a"), Chapter(2, "Two"),
    ]
    panel.set_chapters(chapters)
    received = []
    panel.chapter_selected.connect(received.append)
    # "One-a" is nested under "One"; find it and click.
    one = _find_item(panel.tree, "One")
    one_a = one.child(0)
    assert one_a.text(0) == "One-a"
    panel.tree.itemClicked.emit(one_a, 0)
    assert received == [2]  # positional index of "One-a"


def _find_item(tree, title):
    it = tree.invisibleRootItem()
    stack = [it.child(i) for i in range(it.childCount())]
    while stack:
        node = stack.pop()
        if node.text(0) == title:
            return node
        stack.extend(node.child(i) for i in range(node.childCount()))
    return None
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement `ManualContentsPanel`** (append to `manual_panel.py`).
  Build items with the positional index stored in `Qt.ItemDataRole.UserRole`. H1 is
  the tree title (a top-level bold item); `##` are top-level under it or siblings;
  `###` nest under the most recent `##`. Keep it simple and index-accurate:

```python
class ManualContentsPanel(QWidget):
    chapter_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        layout.addWidget(self.tree)
        self.tree.itemClicked.connect(self._on_item_clicked)

    def set_chapters(self, chapters) -> None:
        self.tree.clear()
        last_h2 = None
        title_item = None
        for index, ch in enumerate(chapters):
            item = QTreeWidgetItem([ch.title])
            item.setData(0, Qt.ItemDataRole.UserRole, index)
            if ch.level <= 1:
                self.tree.addTopLevelItem(item)
                title_item = item
                last_h2 = None
            elif ch.level == 2:
                if title_item is not None:
                    title_item.addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
                last_h2 = item
            else:  # level >= 3
                parent = last_h2 or title_item
                if parent is not None:
                    parent.addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
        self.tree.expandAll()

    def _on_item_clicked(self, item, _column) -> None:
        index = item.data(0, Qt.ItemDataRole.UserRole)
        if index is not None:
            self.chapter_selected.emit(int(index))
```

Add `QVBoxLayout, QWidget` to the imports.

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit** — `git commit -am "feat: ManualContentsPanel chapter tree"`

---

### Task 5: Center-stage Manual tab

**Files:**
- Modify: `pgtp_editor/ui/center_stage.py`
- Test: `tests/ui/test_center_stage_manual.py`

- [ ] **Step 1: Failing test.**

```python
# tests/ui/test_center_stage_manual.py
from pgtp_editor.ui.center_stage import CenterStage


def test_manual_tab_hidden_until_shown(qtbot):
    cs = CenterStage()
    qtbot.addWidget(cs)
    assert cs.isTabVisible(cs.manual_tab_index) is False
    cs.show_manual()
    assert cs.isTabVisible(cs.manual_tab_index) is True
    assert cs.currentIndex() == cs.manual_tab_index
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement.** In `center_stage.py`, import `ManualPanel`, and after
  the Raw XML tab is added:

```python
from pgtp_editor.ui.manual_panel import ManualPanel
...
        self.manual_panel = ManualPanel()
        self.manual_tab_index = self.addTab(self.manual_panel, "Manual")
        self.setTabVisible(self.manual_tab_index, False)
```

Keep the existing `setCurrentIndex(self.raw_xml_tab_index)` as the default. Add:

```python
    def show_manual(self):
        self.setTabVisible(self.manual_tab_index, True)
        self.setCurrentIndex(self.manual_tab_index)
```

- [ ] **Step 4: Run — expect PASS.** Also run the existing center-stage tests to
  confirm the default tab and visibility of other tabs are unchanged.

- [ ] **Step 5: Commit** — `git commit -am "feat: center-stage Manual tab"`

---

### Task 6: Main-window wiring (left dock tabs, Help ▸ Manual, F1)

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Test: `tests/ui/test_main_window_manual.py`

Read the current dock setup at `main_window.py:104-107` and the Help menu at
`main_window.py:1304-1306` before editing.

- [ ] **Step 1: Failing test.** Construct the window offscreen; assert the wiring.

```python
# tests/ui/test_main_window_manual.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pgtp_editor.ui.main_window import MainWindow


def test_manual_populated_and_show_manual_reveals(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    # Contents populated once at construction.
    assert win.manual_contents.tree.topLevelItemCount() >= 1
    # Manual panel has rendered content.
    assert win.center_stage.manual_panel.document().characterCount() > 100

    win._show_manual()
    cs = win.center_stage
    assert cs.isTabVisible(cs.manual_tab_index) is True
    assert cs.currentIndex() == cs.manual_tab_index
    assert win.tree_dock.isVisible() is True
    # Contents tab selected in the left dock.
    assert win.left_tabs.currentWidget() is win.manual_contents


def test_chapter_click_scrolls_manual(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    win._show_manual()
    # Emit a chapter selection; panel cursor should move to that heading block.
    from pgtp_editor.ui.manual_panel import parse_chapters, load_manual_text
    chapters = parse_chapters(load_manual_text())
    target = min(3, len(chapters) - 1)
    win.manual_contents.chapter_selected.emit(target)
    assert win.center_stage.manual_panel.textCursor().block().text() == chapters[target].title
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement.**

Wrap the dock content in a tab widget. Replace the current
`self.tree_dock.setWidget(self.project_tree)` (around `main_window.py:106`) with:

```python
from PySide6.QtWidgets import QTabWidget  # if not already imported
from pgtp_editor.ui.manual_panel import ManualContentsPanel, load_manual_text, parse_chapters
...
        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(self.project_tree, "Project")
        self.manual_contents = ManualContentsPanel()
        self.left_tabs.addTab(self.manual_contents, "Contents")
        self.tree_dock.setWidget(self.left_tabs)
```

After `center_stage` exists, populate the manual once (near other center_stage
setup; the manual is static). Guard against a packaging failure:

```python
        try:
            manual_text = load_manual_text()
            self.center_stage.manual_panel.set_markdown(manual_text)
            self.manual_contents.set_chapters(parse_chapters(manual_text))
            self.manual_contents.chapter_selected.connect(self._on_manual_chapter_selected)
        except Exception as exc:  # pragma: no cover - packaging safety net
            self.statusBar().showMessage(f"Manual unavailable: {exc}")
```

Replace the Help stub. In `_build_help_menu` (currently
`self._add_stub_action(menu, "Documentation")`), use a real action:

```python
    def _build_help_menu(self):
        menu = self.menuBar().addMenu("Help")
        manual_action = menu.addAction("Manual")
        manual_action.setShortcut("F1")
        manual_action.triggered.connect(self._show_manual)
```

Add the methods:

```python
    def _show_manual(self):
        self.center_stage.show_manual()
        self.tree_dock.setVisible(True)
        self.left_tabs.setCurrentWidget(self.manual_contents)

    def _on_manual_chapter_selected(self, index):
        self.center_stage.show_manual()
        self.center_stage.manual_panel.scroll_to_chapter(index)
```

- [ ] **Step 4: Run — expect PASS.** Then run the full suite:
  `python -m pytest -q` — expect all green (prior baseline 963 + new tests).

- [ ] **Step 5: Commit** — `git commit -am "feat: wire Manual into main window (Help/F1, Contents tab)"`

---

### Task 7: Full-suite verification

- [ ] **Step 1:** `python -m pytest -q` — expect all passing, no timeouts.
- [ ] **Step 2:** Confirm no test triggered a modal (no 60s stalls).
- [ ] **Step 3: Commit** any final tidy-ups.

## Self-review notes

- Spec coverage: resource packaging (T1), loader/parser (T2), render+scroll (T3),
  contents tree (T4), center tab (T5), dock tabs + Help/F1 + wiring (T6). All spec
  sections mapped.
- The positional scroll model is guarded by `test_manual_heading_count_matches_parse_chapters`.
- `Chapter`, `load_manual_text`, `parse_chapters`, `ManualPanel.set_markdown`/
  `scroll_to_chapter`, `ManualContentsPanel.set_chapters`/`chapter_selected`,
  `CenterStage.show_manual`/`manual_tab_index`, `MainWindow.left_tabs`/
  `manual_contents`/`_show_manual`/`_on_manual_chapter_selected` — names consistent
  across tasks.
