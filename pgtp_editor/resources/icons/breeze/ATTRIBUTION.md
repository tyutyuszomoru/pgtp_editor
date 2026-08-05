# Breeze icon attribution

The SVG icons in this folder are from the KDE **breeze-icons** project:

https://github.com/KDE/breeze-icons

© KDE contributors. Licensed under **LGPL-3.0-only** (see
`LICENSE-LGPL-3.0.txt` in this folder).

The files are unmodified upstream Breeze SVGs, taken from the project's
22×22 `actions` set. PGTP Editor recolors them only at runtime (substituting a
concrete fill for the `currentColor` / `.ColorScheme-Text` mechanism) so the
toolbar icons stay legible against both the light and dark themes; the vendored
files on disk are byte-for-byte upstream.

## Scope of the vendored subset

This is a **curated subset** of Breeze's `actions` category, not the whole
category: a set of common toolbar actions (file, edit, navigation, view/zoom,
run/stop, configure, help, and a few code/table icons), chosen so the
Customize Toolbar icon picker offers a useful but scannable catalog without
bloating the packaged application. Seven of them are the toolbar's built-in
defaults (`document-open`, `document-save`, `edit-undo`, `edit-redo`,
`edit-find`, `dialog-ok-apply`, `run-build`); the rest are choosable by the
user for any toolbar button.

## Icons used

- `application-exit.svg`
- `arrow-down.svg`
- `arrow-left.svg`
- `arrow-right.svg`
- `arrow-up.svg`
- `bookmark-new.svg`
- `bookmarks.svg`
- `code-block.svg`
- `code-class.svg`
- `code-context.svg`
- `code-function.svg`
- `configure-shortcuts.svg`
- `configure.svg`
- `configure-toolbars.svg`
- `database-change-key.svg`
- `database-index.svg`
- `delete-table-row.svg`
- `dialog-cancel.svg`
- `dialog-close.svg`
- `dialog-messages.svg`
- `dialog-ok-apply.svg`
- `dialog-ok.svg`
- `document-close.svg`
- `document-duplicate.svg`
- `document-edit.svg`
- `document-export.svg`
- `document-import.svg`
- `document-new.svg`
- `document-open-folder.svg`
- `document-open-recent.svg`
- `document-open.svg`
- `document-preview.svg`
- `document-print-preview.svg`
- `document-print.svg`
- `document-properties.svg`
- `document-revert.svg`
- `document-save-all.svg`
- `document-save-as.svg`
- `document-save.svg`
- `edit-clear-all.svg`
- `edit-clear.svg`
- `edit-comment.svg`
- `edit-copy.svg`
- `edit-cut.svg`
- `edit-delete.svg`
- `edit-duplicate.svg`
- `edit-entry.svg`
- `edit-find-replace.svg`
- `edit-find.svg`
- `edit-paste.svg`
- `edit-redo.svg`
- `edit-rename.svg`
- `edit-select-all.svg`
- `edit-undo.svg`
- `folder-new.svg`
- `folder-sync.svg`
- `format-text-bold.svg`
- `format-text-italic.svg`
- `format-text-underline.svg`
- `go-down.svg`
- `go-first.svg`
- `go-home.svg`
- `go-jump.svg`
- `go-last.svg`
- `go-next.svg`
- `go-previous.svg`
- `go-up.svg`
- `help-about.svg`
- `help-contents.svg`
- `help-hint.svg`
- `insert-table.svg`
- `list-add.svg`
- `list-remove.svg`
- `media-playback-pause.svg`
- `media-playback-start.svg`
- `media-playback-stop.svg`
- `object-locked.svg`
- `object-unlocked.svg`
- `process-stop.svg`
- `quickopen-file.svg`
- `quickopen.svg`
- `run-build-clean.svg`
- `run-build.svg`
- `settings-configure.svg`
- `system-run.svg`
- `tab-close.svg`
- `table.svg`
- `tab-new.svg`
- `tools-report-bug.svg`
- `view-filter.svg`
- `view-fullscreen.svg`
- `view-hidden.svg`
- `view-list-details.svg`
- `view-list-icons.svg`
- `view-list-tree.svg`
- `view-refresh.svg`
- `view-sort-ascending.svg`
- `view-sort-descending.svg`
- `view-split-left-right.svg`
- `view-split-top-bottom.svg`
- `view-visible.svg`
- `window-new.svg`
- `zoom-fit-best.svg`
- `zoom-in.svg`
- `zoom-original.svg`
- `zoom-out.svg`
