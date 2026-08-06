# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# pgtp_editor/ui/php_file_tab.py
"""PhpFileTab: one standalone `.php`/text file, one `CenterStage` tab (spec §21).

Phase 1 of §21 -- the "Notepad++ baseline", and deliberately nothing more. In
the owner's words the custom-PHP surface is *"a rich text editor like we already
have, adding features one by one"*: so this module writes **no** new editor
widget. It hosts the existing `ui/code_editor.py::CodeEditor` in
`language="php"` mode -- the same widget §8's event-handler dialog and §18.5's
`DdlObjectEditorPanel` host -- with its own `FindReplaceBar` below it, the exact
layout precedent of the Edit XSD tab (§7/§11/§15) and of `DdlObjectEditorPanel`.

**No structural tie to a `.pgtp` project.** This module knows nothing about the
project document, the project tree, or whether a project is even loaded: a file
opens standalone either way. Consequently the tab's dirty state and undo stack
are its own -- dirtying a PHP tab must never mark the project document dirty,
and Ctrl+Z inside it must never revert the Raw XML buffer (the same carve-out
`DdlObjectEditorPanel` pins for §18.5, and for the same reason: `CodeEditor`
neither consumes nor re-emits Ctrl+Z/Ctrl+Y, so without an event filter the
window-level QShortcut would win).

**The tab never touches the filesystem behind the caller's back.** Opening takes
already-read text (plus, optionally, the path it came from, for the label and
the tooltip). Saving goes through the injected `resolve_save_path` seam --
`DdlObjectEditorPanel`'s idiom verbatim -- and the actual byte-writing through
an injectable `writer`, so a host that wants to route writes elsewhere (or a
test that wants no disk at all) substitutes one callable. Nothing here opens a
dialog; `QFileDialog` stays entirely on the host side.

**Folding is inert for PHP, by design and not by omission.** `CodeEditor`
carries the shared fold machinery (`ui/editor_gutter.py::GutterBookmarkFoldMixin`,
§8) and exposes `set_fold_regions`, but no host computes PHP regions yet -- a
PHP fold-region provider is §21's explicitly sequenced follow-up #1, a separate
pass. Likewise absent on purpose: the custom-code file-tree dock and Find in
Files (follow-ups #2 and #3), and any code intelligence at all -- §21 records
"no LSP, no parse-based autocomplete" as a scope decision, not a gap.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from pgtp_editor.ui.code_editor import CodeEditor
from pgtp_editor.ui.find_replace_bar import FindReplaceBar

#: The label a tab with no path yet carries (a text-only open).
UNTITLED_TITLE = "Untitled"


def php_tab_key(path) -> str:
    """The stable tab-map key for `path`.

    Keyed on the file's resolved absolute path, never on a remembered
    `CenterStage` index -- closing or reordering tabs must not be able to make
    a lookup stale (`open_ddl_object_tab`'s rule, §18.5). Resolving also means
    `./foo.php` and an absolute path to the same file focus the SAME tab
    instead of opening a second one.
    """
    return str(Path(path).expanduser().resolve())


def _default_writer(path: Path, text: str) -> None:
    """The default `writer`: what `MainWindow._save_ddl_object_editor` does."""
    path.write_text(text, encoding="utf-8", newline="")


class PhpFileTab(QWidget):
    """One open file, hosted as an ordinary closable `CenterStage` tab (§21).

    Layout mirrors Edit XSD and `DdlObjectEditorPanel`: the editor above, its
    own `FindReplaceBar` below, zero margins and zero spacing.
    """

    #: Emitted only on a clean→dirty / dirty→clean TRANSITION, never per
    #: keystroke -- it drives the tab title's `" *"` marker.
    dirty_changed = Signal(bool)

    #: Emitted after a successful save, carrying the path written (as str, so
    #: the signal stays Qt-native). Hosts use it for the status-bar message.
    saved = Signal(str)

    #: Emitted when a save attempt raised `OSError`, carrying the message. The
    #: tab stays dirty. The host owns the `QMessageBox` -- this widget never
    #: shows a modal.
    save_failed = Signal(str)

    def __init__(
        self,
        path=None,
        text: str = "",
        resolve_save_path: Callable[[], Path | None] | None = None,
        writer: Callable[[Path, str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path: Path | None = Path(path) if path is not None else None
        # The save seam, in full (`DdlObjectEditorPanel.resolve_save_path`'s
        # idiom): default is the path the file was opened from, so an ordinary
        # Ctrl+S on an opened file writes straight back to it. A text-only tab
        # resolves to None until the host injects a Save-As… resolver.
        self._resolve_save_path: Callable[[], Path | None] = (
            resolve_save_path if resolve_save_path is not None else self._remembered_save_path
        )
        self._writer: Callable[[Path, str], None] = writer or _default_writer

        # The EXISTING editor widget, in PHP mode (§8's highlighter already
        # covers PHP) -- never a second, parallel editor implementation.
        self.editor = CodeEditor(language="php")
        self.editor.setReadOnly(False)
        self.find_replace_bar = FindReplaceBar(self.editor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.editor)
        layout.addWidget(self.find_replace_bar)

        # Dirty state rides on this document's own modified flag -- entirely
        # separate from the project document's (§21: "independent of the
        # project document's dirty state").
        self.editor.document().modificationChanged.connect(self.dirty_changed)
        self.set_text(text)

        # Per-tab Ctrl+Z / Ctrl+Y / Ctrl+S, claimed before the window-level
        # QShortcuts can see them (§18.5 carve-out 1's mechanism, same
        # rationale): while this tab has focus, undo/redo must move THIS
        # document's stack and Save must write THIS file -- never the project
        # buffer. Installed on self.editor, not on CodeEditor itself, so the
        # read-only §18.1 EditorPanel never inherits the behavior.
        self.editor.installEventFilter(self)

    # --- Identity ---------------------------------------------------------
    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def key(self) -> str | None:
        """This tab's `CenterStage` map key, or None for a text-only tab
        (whose key the stage mints instead)."""
        return php_tab_key(self._path) if self._path is not None else None

    def tab_title(self) -> str:
        """The tab label: the bare file name plus the `" *"` dirty marker the
        Edit XSD tab established (§11)."""
        name = self._path.name if self._path is not None else UNTITLED_TITLE
        return name + (" *" if self.is_dirty() else "")

    def tab_tooltip(self) -> str:
        """The tab tooltip: the full path (the file name alone is ambiguous
        once two folders' `index.php` are open side by side)."""
        return str(self._path) if self._path is not None else UNTITLED_TITLE

    # --- Buffer -----------------------------------------------------------
    def text(self) -> str:
        return self.editor.toPlainText()

    def set_text(self, text: str) -> None:
        """Load the buffer WITHOUT marking it dirty -- this is the injected
        load half, not a user edit."""
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)

    # --- Dirty state ------------------------------------------------------
    def is_dirty(self) -> bool:
        return self.editor.document().isModified()

    def mark_clean(self) -> None:
        """Clear the dirty marker -- what a successful save calls."""
        self.editor.document().setModified(False)

    # --- Navigation -------------------------------------------------------
    def navigate_to_line(self, line: int) -> None:
        """Jump to `line` (1-based), delegating to `CodeEditor`'s shared
        navigation API (§8)."""
        self.editor.navigate_to_line(line)
        self.editor.setFocus()

    # --- The save seam ----------------------------------------------------
    def resolve_save_path(self) -> Path | None:
        """Where a save should write, or None if it cannot be resolved (the
        host's Save As… was cancelled, which cancels the save and is not an
        error)."""
        return self._resolve_save_path()

    def remember_save_path(self, path) -> None:
        """Adopt `path` as this tab's file: every subsequent save writes there
        silently, and the label/tooltip follow it (a Save As… renames the
        tab)."""
        self._path = Path(path)

    def _remembered_save_path(self) -> Path | None:
        return self._path

    def save(self) -> bool:
        """Write the buffer through the injected seams. Returns True on
        success; False when the path could not be resolved (cancelled Save
        As…) or the write raised `OSError` -- callers' close-confirmation
        flows must treat both exactly like Cancel, never as a completed save
        (`_save_ddl_object_editor`'s contract, §18.5)."""
        path = self.resolve_save_path()
        if path is None:
            return False
        path = Path(path)
        try:
            self._writer(path, self.text())
        except OSError as exc:
            self.save_failed.emit(str(exc))
            return False
        self.remember_save_path(path)
        self.mark_clean()
        self.saved.emit(str(path))
        return True

    # --- Per-tab Ctrl+Z / Ctrl+Y / Ctrl+S ---------------------------------
    def eventFilter(self, obj, event) -> bool:
        if obj is self.editor and event.type() in (
            QEvent.Type.ShortcutOverride,
            QEvent.Type.KeyPress,
        ):
            key = event.key()
            ctrl = event.modifiers() == Qt.KeyboardModifier.ControlModifier
            handler = None
            if ctrl and key == Qt.Key.Key_Z:
                handler = self.editor.undo
            elif ctrl and key == Qt.Key.Key_Y:
                handler = self.editor.redo
            elif ctrl and key == Qt.Key.Key_S:
                handler = self.save
            if handler is not None:
                if event.type() == QEvent.Type.ShortcutOverride:
                    # Claim the sequence so Qt never ALSO fires the
                    # window-level QShortcut for this key press -- no double
                    # undo, and no leak into the project buffer.
                    event.accept()
                else:
                    handler()
                return True
        return super().eventFilter(obj, event)
