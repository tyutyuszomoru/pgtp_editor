# Editor Bookmarks (Design)

Line bookmarks in the Raw XML editor: toggle via the gutter or Ctrl+F2, navigate
with F2/Shift+F2, managed from a Bookmarks menu. Session-only.

## Decisions (from brainstorming)

- **Toggle:** click a dedicated bookmark strip in the gutter margin, AND Ctrl+F2
  toggles the current line.
- **Persistence:** session-only — bookmarks clear when a file is opened/closed
  (same lifecycle as fold state); no on-disk persistence, so line numbers can't
  drift from external edits.
- **Navigation & menu:** a **Bookmarks** menu — Toggle Bookmark (Ctrl+F2),
  Next Bookmark (F2), Previous Bookmark (Shift+F2), Clear All Bookmarks. F2/Shift+F2
  wrap around.
- **Marker:** a small filled rounded **tag** drawn in the gutter, in a palette
  accent color (reads in both Light and Dark themes).

## Background (existing code)

- `pgtp_editor/ui/xml_editor.py`: `XmlEditor(QPlainTextEdit)` with a gutter widget
  (`_EditorGutter`/line-number area) whose `paintEvent` draws line numbers and the
  fold chevron via `_draw_fold_glyph`; `mousePressEvent` toggles folds when the
  click x < `_FOLD_GLYPH_WIDTH`. `_fold_state: dict[int,bool]` is reset in
  `setPlainText`/on load. Gutter width is computed for the line-number digits +
  `_FOLD_GLYPH_WIDTH`. The editor already reacts to palette changes
  (`apply_theme_colors`) and exposes gutter colors `_gutter_bg_color`/`_gutter_fg_color`.
- `main_window.py`: `_build_menu_bar` assembles the menus; the Raw XML editor is
  `center_stage.xml_editor`; `navigate_to_line`/line-centering helpers exist for
  jumping.

## Architecture

Bookmarks are tracked on the editor by **block number** (line index), a session
`set[int]`, mirroring the fold-state lifecycle.

### `xml_editor.py`
- `self._bookmarks: set[int]` initialized in `__init__`; **reset to empty** wherever
  `_fold_state` is reset (load / `setPlainText`), so bookmarks are session/file-scoped.
- Methods (pure-ish, unit-testable):
  - `toggle_bookmark(block_number)` — add/remove; repaints the gutter.
  - `bookmarked_lines() -> list[int]` — sorted block numbers.
  - `next_bookmark(from_line) -> int | None` — smallest bookmark > `from_line`,
    wrapping to the smallest overall; `None` if no bookmarks.
  - `prev_bookmark(from_line) -> int | None` — largest bookmark < `from_line`,
    wrapping to the largest; `None` if none.
  - `clear_bookmarks()` — empties + repaints.
  - `toggle_bookmark_at_cursor()` / `goto_next_bookmark()` / `goto_prev_bookmark()`
    — convenience wrappers operating on the current cursor line and moving/centering
    the cursor (reuse the existing line-centering).
- **Gutter layout:** widen the gutter to three zones — a left **bookmark strip**
  (`_BOOKMARK_STRIP_WIDTH`), the line-number area, and the existing fold zone.
  - `paintEvent`: for each visible block whose number is bookmarked, draw a filled
    rounded tag (`drawRoundedRect`, no border, palette accent fill; antialiased) in
    the bookmark strip, vertically centered on the line.
  - `mousePressEvent`: if the click x is within the bookmark strip → toggle the
    bookmark for the clicked block; else keep the existing fold-toggle behavior
    (adjust the fold-zone x test for the new offset).
- Accent color: derive from the palette (`QPalette.Highlight`) so it's theme-aware;
  recompute in `apply_theme_colors` if colors are cached.

### `main_window.py`
- `_build_bookmarks_menu()` (called from `_build_menu_bar`): a **Bookmarks** menu:
  - "Toggle Bookmark" — Ctrl+F2 → `xml_editor.toggle_bookmark_at_cursor`.
  - "Next Bookmark" — F2 → `xml_editor.goto_next_bookmark`.
  - "Previous Bookmark" — Shift+F2 → `xml_editor.goto_prev_bookmark`.
  - "Clear All Bookmarks" → `xml_editor.clear_bookmarks`.
- Navigation with no bookmarks is a no-op (optional status message); with one, F2
  re-centers it. Shortcuts are set on the menu actions (no conflict — F2 is the
  Find-Next accelerator in the Edit menu currently; **resolve:** Find Next is on F3
  in the Edit menu, so F2/Shift+F2 are free — confirm during implementation and, if
  F2 is taken, keep Bookmarks' F2 and move the other, reporting the change).

## Data flow

Gutter click in the bookmark strip → `toggle_bookmark(block)` → repaint. Menu/shortcut
→ editor convenience method → toggle or move+center the cursor → repaint. Opening a
file resets `_bookmarks` (empty).

## Error handling

- Navigation with an empty bookmark set: no-op (guard returns None).
- Bookmarks on lines later removed by editing: block-number set may point past EOF;
  navigation/paint must ignore out-of-range block numbers safely.

## Testing (headless, no modals)

- Editor logic: `toggle_bookmark` add/remove; `bookmarked_lines` sorted;
  `next_bookmark`/`prev_bookmark` ordering, wrap-around, and `None` when empty;
  `clear_bookmarks`; bookmarks reset on `setPlainText`/load.
- Gutter: a synthesized mouse press in the bookmark strip toggles the correct
  block's bookmark (mirror the existing fold-click test); a press in the fold zone
  still toggles folds (no regression).
- Menu: the four Bookmarks actions exist with the right shortcuts (Ctrl+F2/F2/
  Shift+F2) and call through to the editor; toggle-at-cursor bookmarks the cursor's
  line; goto-next moves the cursor to the next bookmark (wrap). No `.exec()`/modal.

## Non-goals

- Persisting bookmarks across sessions or in the `.pgtp` file.
- Bookmarks in the Diff/Merge or Caption views (Raw XML editor only).
- A bookmarks list panel (declined in favor of the menu + gutter).
- Named/annotated bookmarks (plain line marks only).
