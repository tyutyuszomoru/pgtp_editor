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

# pgtp_editor/ui/ddl_object_editor.py
"""DdlObjectEditorPanel: the EDITABLE single-object DDL tab (spec §18.5).

The editable counterpart of §18.1's read-only `ddl_editor_panel.py::EditorPanel`
-- same `ui/code_editor.py::CodeEditor` in `language="sql"` mode (so the gutter,
bookmarks, folding, 4-character tab stop and SQL highlighting are inherited from
`ui/editor_gutter.py::GutterBookmarkFoldMixin`, never reimplemented here), same
per-tab `FindReplaceBar` routing precedent, same zero-margin layout -- except
this one is EDITABLE. `EditorPanel` stays read-only permanently.

**v1 is project-decoupled.** This module knows nothing about `.pgtp` projects,
`db/ddl_project.py`, a `ddl/` folder, a `deployed.json` manifest or `*`/`!`
state markers: all of those are §18.2 concepts and none is a prerequisite for
editing one routine. `resolve_save_path` is the ENTIRE §18.2 seam -- the panel
persists through an injected `Callable[[], Path | None]`, so §18.2's whole
change is that callable returning `project.ddl_dir / <the §18.2 filename>`
instead of a Save-As-picked path. No restructure, no new branch in the panel.

**The panel never talks to a database.** It does not import `db/introspect.py`,
never opens a connection and holds no connection parameters; the buffer is
handed to it as text. Apply / Check / the sandbox button row are deliberately
absent in v1 (settled carve-out 2 of §18.5) -- the `applied_sha1` slot below is
the inert seam through which the sandbox lane later renders "changed since last
applied" without a constructor change.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

from pgtp_editor.sql.formatter import format_selection as _format_selection_text
from pgtp_editor.ui.code_editor import CodeEditor
from pgtp_editor.ui.find_replace_bar import FindReplaceBar


@dataclass(frozen=True)
class DdlObjectRef:
    """The stable per-object identity of an editable DDL tab (§18.5).

    Derived from a `db/ddl_buffer.py::DdlObjectSpan` by the caller (the tab is
    keyed on identity, never on a remembered `CenterStage` index, so closing or
    reordering tabs cannot make the key stale).

    `disambiguate` is set by the CALLER, which is the only party that can see
    the sibling set: a routine renders as its bare `name` when it is the sole
    holder of its `schema.name`, and only an OVERLOADED routine renders its
    signature. The panel cannot infer this, and unconditionally rendering `()`
    would turn a no-argument `recalc` into `recalc()`.
    """

    kind: str  # "function" | "procedure" | "trigger"
    schema: str
    name: str
    table: str | None = None  # triggers only -- the table the trigger fires on
    arg_types: tuple[str, ...] = ()  # routines only; always () for a trigger
    # Declared last, with a default: caller-supplied overload disambiguation.
    disambiguate: bool = False

    @property
    def is_trigger(self) -> bool:
        return self.kind == "trigger"

    @property
    def signature(self) -> str:
        """`(integer, text)` / `()` -- the routine's argument-type list."""
        return "(" + ", ".join(self.arg_types) + ")"

    @property
    def key(self) -> tuple:
        """The hashable, stable identity used as the `CenterStage` tab-map key.

        Includes the argument types (PostgreSQL allows overloading
        `schema.name`) and the table (a trigger name is unique only per table).
        Deliberately EXCLUDES `disambiguate`, which is presentation only: the
        same object must map to the same tab whether or not a sibling exists.
        """
        return (self.kind, self.schema, self.name, self.table, self.arg_types)

    @property
    def short_title(self) -> str:
        """The tab label: the object's SHORT identity (§18.5).

        `recalc` for a sole-holder routine, `fmt(integer)` for an overloaded
        one, `orders.trg_audit` for a trigger.
        """
        if self.is_trigger:
            return f"{self.table}.{self.name}"
        if self.disambiguate:
            return f"{self.name}{self.signature}"
        return self.name

    @property
    def qualified(self) -> str:
        """The tab tooltip: the FULL source identity -- schema-qualified, with
        the signature for a routine and the table for a trigger."""
        if self.is_trigger:
            return f"{self.schema}.{self.table}.{self.name}"
        return f"{self.schema}.{self.name}{self.signature}"

    @property
    def default_file_name(self) -> str:
        """The Save As… prefill: the sole-holder form of §18.2's file scheme,
        so the file a v1 user saves is already shaped like the checked-out one
        §18.2 will manage."""
        if self.is_trigger:
            return f"{self.schema}.{self.table}.{self.name}.sql"
        return f"{self.schema}.{self.name}.sql"


class DdlObjectEditorPanel(QWidget):
    """One editable DDL object, one tab (§18.5).

    Layout mirrors `EditorPanel`: the editor above, its own `FindReplaceBar`
    below, zero margins and zero spacing. No button row -- v1 ships none rather
    than three dead sandbox controls (carve-out 2).
    """

    #: Emitted only on a clean→dirty / dirty→clean TRANSITION, never per
    #: keystroke -- it drives the tab title's `" *"` marker.
    dirty_changed = Signal(bool)

    #: Emitted when Format Selection (§18.4/§18.5 carve-out 4/6) refuses --
    #: never on success. Carries the formatter's `sql.issues.Issue` list, for
    #: the host to report to the Audit panel under the `[SQL]` prefix
    #: (not clickable, no line role -- carve-out 6).
    format_refused = Signal(list)

    def __init__(
        self,
        ref: DdlObjectRef,
        text: str = "",
        resolve_save_path: Callable[[], Path | None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ref = ref
        self._save_path: Path | None = None
        # The §18.2 seam, in full. Default: the remembered path, or None when
        # nothing has been picked yet. Increment B's host supplies a callable
        # that runs Save As…; §18.2's supplies the project's ddl/ path. The
        # panel itself never opens a dialog and never learns what a project is.
        self._resolve_save_path: Callable[[], Path | None] = (
            resolve_save_path if resolve_save_path is not None else self._remembered_save_path
        )

        #: Inert v1 seam (§18.5): sha1 of the text last applied to the sandbox,
        #: so the sandbox lane can later render "changed since last applied"
        #: and emit a `[Check]` caveat without a constructor change. Nothing in
        #: v1 reads or writes it.
        self.applied_sha1: str | None = None

        self.editor = CodeEditor(language="sql")
        # EDITABLE -- the behavioral difference from §18.1's EditorPanel. In
        # particular `CodeEditor.replace_current_selection` (FindReplaceBar's
        # Replace) early-returns on a read-only editor; here it applies.
        self.editor.setReadOnly(False)
        self.find_replace_bar = FindReplaceBar(self.editor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.editor)
        layout.addWidget(self.find_replace_bar)

        # Dirty state rides on the document's own modified flag, whose
        # modificationChanged signal fires on transitions only.
        self.editor.document().modificationChanged.connect(self.dirty_changed)
        self.set_text(text)

        # Carve-out 1 (§18.5, pinned invariant): CodeEditor neither consumes
        # nor re-emits Ctrl+Z/Ctrl+Y, so with no filter the window-level
        # QShortcut at main_window.py:401 would fire and revert the RAW XML
        # project buffer while this tab is focused. Installed on self.editor
        # (not CodeEditor itself, which the read-only §18.1 EditorPanel also
        # uses and must not gain this behavior) so ONLY this tab's own native
        # undo stack is ever touched. See eventFilter below.
        self.editor.installEventFilter(self)

        # Format Selection (§18.4's consumer, §18.5): Ctrl+Alt+F, enabled only
        # with a selection. The redundant eventFilter branch below handles the
        # key directly too, mirroring CodeEditorDialog's Ctrl+S/Ctrl+W
        # convention -- QShortcut activation is not reliable under the
        # offscreen platform in tests.
        self._format_shortcut = QShortcut(QKeySequence("Ctrl+Alt+F"), self)
        self._format_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._format_shortcut.activated.connect(self.format_selection)
        self._format_shortcut.setEnabled(False)
        self.editor.selectionChanged.connect(self._update_format_shortcut_enabled)
        # Carve-out 4: the refusal underline is transient -- cleared on the
        # next edit, or the next format attempt (format_selection itself
        # clears it before trying again).
        self.editor.textChanged.connect(self._clear_format_underline)

    # --- Identity ---------------------------------------------------------
    @property
    def ref(self) -> DdlObjectRef:
        return self._ref

    def tab_title(self) -> str:
        """The `CenterStage` tab label: the short identity plus the `" *"`
        dirty marker the Edit XSD tab already established (§11)."""
        return self._ref.short_title + (" *" if self.is_dirty() else "")

    def tab_tooltip(self) -> str:
        """The tab tooltip: the full source identity (§18.5)."""
        return self._ref.qualified

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
        """Jump to `line` (1-based), delegating to CodeEditor's shared
        navigation API (§8)."""
        self.editor.navigate_to_line(line)
        self.editor.setFocus()

    # --- The §18.2 save seam ---------------------------------------------
    def resolve_save_path(self) -> Path | None:
        """Where a save should write, or None if it cannot be resolved (in v1:
        the user cancelled Save As…, which cancels the save and is not an
        error). The entire surface §18.2 repoints."""
        return self._resolve_save_path()

    def remember_save_path(self, path: Path) -> None:
        """Remember the path a save resolved to, so every subsequent Ctrl+S
        writes silently to it for the rest of the session (§18.5)."""
        self._save_path = Path(path)

    @property
    def save_path(self) -> Path | None:
        return self._save_path

    def _remembered_save_path(self) -> Path | None:
        return self._save_path

    # --- Ctrl+Z / Ctrl+Y native-undo carve-out (§18.5 carve-out 1) --------
    def eventFilter(self, obj, event) -> bool:
        if obj is self.editor and event.type() in (
            QEvent.Type.ShortcutOverride,
            QEvent.Type.KeyPress,
        ):
            key = event.key()
            is_undo = key == Qt.Key.Key_Z and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            is_redo = key == Qt.Key.Key_Y and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            if is_undo or is_redo:
                if event.type() == QEvent.Type.ShortcutOverride:
                    # Claim the sequence so Qt never also fires the
                    # window-level Ctrl+Z/Ctrl+Y QShortcut for this key press
                    # (no double-undo, no leak into the Raw XML buffer).
                    event.accept()
                else:
                    self.editor.undo() if is_undo else self.editor.redo()
                return True
            if (
                key == Qt.Key.Key_F
                and event.modifiers()
                == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
            ):
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                else:
                    self.format_selection()
                return True
        if obj is self.editor and event.type() == QEvent.Type.ContextMenu:
            menu = self._build_context_menu()
            menu.exec(event.globalPos())
            return True
        return super().eventFilter(obj, event)

    def _build_context_menu(self):
        """Build (but do not exec) the editor's context menu -- split out so
        tests can inspect it directly instead of ever driving a real modal
        `QMenu.exec` (the `xml_editor.py` `_build_context_menu` precedent).
        Adds Format Selection (§18.4/§18.5) alongside the standard entries,
        enabled only with a selection -- same gate as the Ctrl+Alt+F shortcut."""
        menu = self.editor.createStandardContextMenu()
        menu.addSeparator()
        action = menu.addAction("Format Selection", self.format_selection)
        action.setEnabled(self.editor.textCursor().hasSelection())
        return menu

    # --- Format Selection (§18.4's consumer, §18.5) ------------------------
    def _update_format_shortcut_enabled(self) -> None:
        self._format_shortcut.setEnabled(self.editor.textCursor().hasSelection())

    def _clear_format_underline(self) -> None:
        self.editor.setExtraSelections([])

    def format_selection(self) -> None:
        """Reindent the current selection in place (§18.4's `format_selection`,
        finally consumed), or -- on refusal -- leave it byte-for-byte
        unchanged, underline each offending span, and emit `format_refused`
        for the host to report under `[SQL]` (carve-outs 4 &amp; 6)."""
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return
        self._clear_format_underline()
        start = cursor.selectionStart()
        # QTextCursor.selectedText() joins lines with U+2029 (paragraph
        # separator), never "\n" -- the tokenizer expects real newlines.
        selected = cursor.selectedText().replace(" ", "\n")
        result = _format_selection_text(selected)
        if result.ok:
            cursor.beginEditBlock()
            cursor.insertText(result.text)
            cursor.endEditBlock()
            return
        selections = []
        for issue in result.issues:
            extra = QTextEdit.ExtraSelection()
            span_cursor = QTextCursor(self.editor.document())
            span_cursor.setPosition(start + issue.start)
            span_cursor.setPosition(start + issue.end, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            fmt.setUnderlineColor(QColor("red"))
            extra.cursor = span_cursor
            extra.format = fmt
            selections.append(extra)
        self.editor.setExtraSelections(selections)
        self.format_refused.emit(result.issues)
