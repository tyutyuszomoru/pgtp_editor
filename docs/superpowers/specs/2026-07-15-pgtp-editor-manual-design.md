# PGTP Editor — In-App Manual (Design)

## Goal

Ship an English user manual, authored in Markdown, that explains how PGTP Editor
works. It renders in a center-stage **Manual** tab and is navigable from a
**Contents** tab in the left dock (alongside the Project tree). Opened via
**Help ▸ Manual** (F1).

## Requirements (from user)

1. Manual content is Markdown.
2. Opens in a tab of the main window (center stage).
3. Also appears as a tab of the tree area (left dock) listing the chapters.
4. Renders the Markdown correctly (headings, lists, code, tables, emphasis).
5. English.

## Architecture

The manual is a bundled resource loaded at runtime; a rendering panel shows it in
the center stage; a contents panel in the left dock lists chapters parsed from the
Markdown headings and scrolls the rendered view when a chapter is clicked. No new
process, no network, no external assets — consistent with the app's offline,
single-file-tool nature.

### Components

**`pgtp_editor/resources/manual.md`** (new, bundled)
- The manual content. One `#` H1 title, then `##`/`###` chapters/sections.
- Shipped via `[tool.setuptools.package-data]` so it survives an installed build.

**`pgtp_editor/ui/manual_panel.py`** (new)
- `load_manual_text() -> str` — reads the bundled `manual.md` via
  `importlib.resources.files("pgtp_editor") / "resources" / "manual.md"`, decoded
  UTF-8. Raises a clear error if missing (packaging bug, caught at call site).
- `parse_chapters(md_text) -> list[Chapter]` where `Chapter` is a small dataclass
  `(level: int, title: str)`. Parses ATX headings (`#`..`######`) in document
  order, **skipping fenced code blocks** (```` ``` ```` / `~~~`) so `#comments`
  inside code samples are never treated as chapters. Heading order here is 1:1
  with the heading blocks Qt produces from the same Markdown.
- `ManualPanel(QTextBrowser)` — read-only, `setOpenExternalLinks(True)`.
  - `set_markdown(text)`: stores text, `setMarkdown(text)`.
  - `scroll_to_chapter(index)`: walks `document()` blocks in order, counting blocks
    whose `blockFormat().headingLevel() > 0`; on reaching the `index`-th heading,
    moves a cursor to that block, `setTextCursor`, and pins it to the top via
    `verticalScrollBar().setValue(cursorRect().top + current)`. Robust to duplicate
    titles (positional, not text-matched). No-op if index out of range.
- `ManualContentsPanel(QWidget)` — a `QTreeWidget` (single column, no header).
  - `set_chapters(chapters)`: builds items; H1 shown as the root/title, `##` as
    top-level entries, `###` nested under the preceding `##`. Each item stores its
    positional chapter index in `Qt.UserRole`.
  - `chapter_selected = Signal(int)` emitted on `itemClicked` with the stored index.

### Integration

**`center_stage.py`**
- Add `self.manual_panel = ManualPanel()`, `self.manual_tab_index = addTab(…, "Manual")`.
- Hidden by default (`setTabVisible(manual_tab_index, False)`), matching the
  Diff/Merge + Caption pattern.
- `show_manual()`: reveal the Manual tab and `setCurrentIndex` to it.

**`main_window.py`**
- Wrap the left dock content in a `QTabWidget` (`self.left_tabs`):
  tab **"Project"** = existing `project_tree`; tab **"Contents"** =
  `self.manual_contents` (a `ManualContentsPanel`). `tree_dock.setWidget(left_tabs)`.
  The existing View-menu toggle keeps targeting `tree_dock` (unchanged).
- On project load path — the manual is static, so populate contents **once** at
  construction: `text = load_manual_text(); center_stage.manual_panel.set_markdown(text);
  manual_contents.set_chapters(parse_chapters(text))`. Wrapped in try/except so a
  packaging failure degrades gracefully (log to status bar, no crash).
- Help menu: replace the `"Documentation"` stub with a real `"Manual"` action,
  shortcut **F1**, triggering `_show_manual()`.
- `_show_manual()`: `center_stage.show_manual()`; ensure `tree_dock` visible and
  switch `left_tabs` to the Contents tab so chapters are in view.
- Wire `manual_contents.chapter_selected` → `center_stage.manual_panel.scroll_to_chapter`
  (revealing the Manual tab first if hidden).

## Manual content (chapters)

Authored in this project; covers every shipped feature. Chapter list:

1. **PGTP Editor** (H1 title + one-paragraph what-it-is)
2. Getting Started — opening a `.pgtp`, the layout (tree / center / properties),
   saving, Save As.
3. The Project Tree — pages, details, columns, events; single-click = Properties,
   double-click = jump to XML; right-click actions per node type (Jump / Select
   block / See in Caption Mode / Add Event Handler / column visibility+presentation).
4. Properties — read-only inspector; column visibility across the fixed
   representation lists (List/View/Edit/Insert/QuickFilter/FilterBuilder/Print/
   Export/Compare/MultiEdit).
5. The Raw XML Editor — editing, current-line and matching-tag highlight,
   Ctrl+Shift+B block select (jumps to block start), code-region styling.
6. Find, Replace & Find All — the search bar, Find All (continuous, Stop button,
   "Found N" status), Replace All count, in-editor Find from selection.
7. The Code Editor — editing event-handler JS/PHP: opening from the XML editor
   ("Edit code…") or the tree; syntax highlighting; auto-close brackets/quotes;
   selection-wrap; Ctrl+Shift+B; Ctrl+S save, Ctrl+W cancel; adding a new handler
   from the Page menu (client vs server handlers).
8. Caption Management — entering the mode; the grid columns (Changed / Line /
   Breadcrumb / Element / Anchor / Attribute / Value / New Value); `<NULL>`;
   editing New Value; coloring & the Changed marker; Go to line (Ctrl+G);
   copy/paste; header filters with the search box; Find/Filter/Replace modal
   (String/Extended/Regex, match case, In-selection/Global); Bulk Transform &
   Unify; Clear all filters; exiting the mode.
9. Diff / Merge — comparing two `.pgtp` files.
10. Validation — running validation, reading issues, jumping to them.
11. Generating PHP — setting the generator path, Generate, save/save-as prompt.
12. Keyboard Shortcuts — consolidated table.
13. The Manual — F1, the Contents tab, clicking a chapter to scroll.

## Testing

Headless (`QT_QPA_PLATFORM=offscreen`), no modal `.exec()` — drive methods/signals
directly.

- `parse_chapters`: levels/titles in order; `#` inside ```` ``` ```` and `~~~`
  fences ignored; `###` nesting; leading/trailing spaces trimmed; a `#` with no
  space (`#foo`) is *not* a heading (matches CommonMark/Qt).
- `load_manual_text`: returns non-empty text beginning with `# ` and the bundled
  file exists on disk under `pgtp_editor/resources/`.
- Consistency: number of `parse_chapters` entries == number of heading blocks Qt
  produces from `setMarkdown` of the same text (guards the positional scroll model).
- `ManualPanel.scroll_to_chapter(i)`: cursor lands on the i-th heading block whose
  text equals `chapters[i].title`; out-of-range is a no-op.
- `ManualContentsPanel.set_chapters` + `itemClicked` emits the correct index;
  nesting parents `###` under `##`.
- `center_stage.show_manual()` reveals + selects the Manual tab.
- `main_window`: `_show_manual()` reveals the Manual tab, makes the dock visible,
  and selects the Contents tab; `chapter_selected` scrolls the panel. F1 action
  exists and is wired.

## Non-goals

- Editing the manual from the app; searching within the manual; live-reload.
- Multi-language (English only, per request).
- Anchored hyperlinks between chapters (positional scroll is sufficient).
