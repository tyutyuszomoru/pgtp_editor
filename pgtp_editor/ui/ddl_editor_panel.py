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

# pgtp_editor/ui/ddl_editor_panel.py
"""EditorPanel: the CenterStage "DDL Explorer" tab (spec §18.1).

Hosts the ONE synthesized routine/trigger buffer (`db/ddl_buffer.py::
build_ddl_text`) in the existing `CodeEditor` under its "sql" language mode,
with its own `FindReplaceBar` instance — the same per-tab document-routing
precedent as the Edit XSD tab (§7/§15). The buffer is read-only, DB-sourced,
live/synthesized: the checked-out, editable form lives in `ddl/*.sql` files
(§18.2), edited in a separate tab type. `BrowserPanel.navigate_requested`
(ui/ddl_buffer_panel.py) jumps here via `navigate_to_line`.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QVBoxLayout, QWidget

from pgtp_editor.ui.code_editor import (
    CLAIMED_NOT_UNDO_REDO,
    REDO,
    UNDO,
    CodeEditor,
    apply_shrink_structural_selection,
    classify_editor_chord,
    is_mutating_editor_operation,
)
from pgtp_editor.ui.ddl_buffer_panel import RELOAD_LABEL, resolve_edit_target
from pgtp_editor.ui.find_replace_bar import FindReplaceBar, install_focus_shortcuts


def _fold_regions_for_spans(spans) -> list[tuple[int, int, int]]:
    """Translate `DdlObjectSpan`s into the shared fold base's
    ``(start_block, first_contained_block, last_contained_block)`` triples
    (0-based block numbers) -- the DDL-object foldable-region provider (§18.1).

    A span's `start_line` is the object's 1-based BANNER line and `end_line`
    the last line of its source. The fold is triggered on the banner block and
    contains the body only, so the banner stays visible when collapsed. Spans
    with no body (`end_line <= start_line`) contribute no region.
    """
    regions: list[tuple[int, int, int]] = []
    for span in spans:
        if span.end_line <= span.start_line:
            continue  # nothing below the banner to fold
        regions.append((span.start_line - 1, span.start_line, span.end_line - 1))
    return regions


class EditorPanel(QWidget):
    #: Right-click inside an object's span ▸ Edit DDL: <schema>.<name>(<argtypes>)
    #: (spec §18.5, D1 entry point 2). Same payload shape as
    #: `BrowserPanel.edit_requested` -- the object's `DdlObjectRef` and its
    #: current source text. The ONLY editing signal since FQ-024, mirroring
    #: `BrowserPanel`: `checkout_requested` is withdrawn and checkout is a
    #: branch of MainWindow's handler for this signal (§18.1/§18.2).
    edit_requested = Signal(object, str)

    #: Right-click ▸ Reload DDL, or `Ctrl+Shift+R` with the caret in this buffer
    #: (BUG-062). "Re-introspect the connection this Explorer was opened over and
    #: rebuild everything from the result."
    #:
    #: A SIGNAL, not a call: §18.5 D1's injection idiom says this panel never
    #: talks to a database, and the fetch it asks for is the host's
    #: `_open_ddl_explorer(role)` -- the same path the Database-menu toggle runs,
    #: which is why reload is a re-introspection and NOT a re-render of a cached
    #: `SchemaIndex`. A cached index is exactly what goes stale when the user
    #: applies a change, so serving reload from it would answer the gesture with
    #: the data the gesture exists to replace. (BUG-045 is what reaching for the
    #: database from here looks like.)
    #:
    #: Carries NO role: this panel does not know which of §18.7's two Explorers
    #: it is, and it must not learn -- the host connects each instance's signal
    #: to that instance's role, exactly as it does for `edit_requested`.
    reload_requested = Signal()

    def __init__(
        self, parent: QWidget | None = None, *, browse_only: bool = False
    ) -> None:
        """`browse_only` suppresses the right-click ▸ `Edit DDL` entry (§18.7,
        FQ-022).

        The SANDBOX Explorer instance passes it. `Edit DDL` from the sandbox's
        buffer would reach `MainWindow._on_ddl_edit_requested`, which in project
        mode takes the CHECKOUT branch and would seed `ddl/*.sql` from the
        *sandbox's* definition -- poisoning §18.2's drift baseline, whose
        reference point is the deployed target definition. Rather than teach the
        panel about checkouts, the sandbox instance simply does not offer the
        gesture (§18.7's "browse-only for v1", pending an owner ruling on whether
        it should instead always take the projectless/live-source branch).

        Off by default, so the target instance -- and every existing caller --
        keeps today's behaviour untouched.
        """
        super().__init__(parent)
        #: Whether this instance offers `Edit DDL` at all (see above).
        self._browse_only = browse_only
        self.editor = CodeEditor(language="sql")
        # Read-only by design (§18.1): phase-2 inline write-back, if ever
        # built, is a separate, diff-gated feature — this tab never edits.
        self.editor.setReadOnly(True)
        self.find_replace_bar = FindReplaceBar(self.editor)

        # Retained so right-click ▸ Edit DDL (§18.5, D1 entry point 2) can find
        # which object the click landed inside; the schema that produced them
        # resolves the click to a `DdlObjectRef` + live source text (shared
        # helper with BrowserPanel's tree, `ddl_buffer_panel.resolve_edit_target`).
        self._spans = []
        self._schema = None
        self.editor.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.editor)
        layout.addWidget(self.find_replace_bar)

        # FQ-016: the bar is permanently visible, so Ctrl+F / Ctrl+R FOCUS it.
        # Scoped to this panel and its children so the keys work with the caret
        # in the (read-only) buffer. Replace is inert here by design --
        # `CodeEditor.replace_current_selection` early-returns on a read-only
        # editor -- but focusing the field is not, so both keys are installed.
        self._focus_find_shortcut, self._focus_replace_shortcut = (
            install_focus_shortcuts(self, self.find_replace_bar)
        )

        # Reload DDL (BUG-062). `Ctrl+Shift+R`, scoped to this panel and its
        # children so it fires with the caret in the buffer -- the
        # `install_focus_shortcuts` / `DdlObjectEditorPanel._format_shortcut`
        # scope, for the same reason.
        #
        # THIS QShortcut IS THE GESTURE'S ONLY KEYBOARD HOST (DEC-012, as
        # answered: *any gesture with a command form -- menu bar OR context menu
        # -- has exactly one keyboard host*). Reload has three affordances: this
        # panel's context menu, the tree's, and the host's Database-menu action.
        # Neither menu form carries a shortcut; both are click-only commands,
        # exactly as `Format Selection` ships since BUG-054.
        #
        # Why the widget and not the QAction -- the choice the one-host rule
        # leaves open, and which the Format Selection precedent already made the
        # same way. Reload is per-ROLE (§18.7 gives the target and the sandbox
        # their own Explorer, their own connection and their own tab), so a
        # window-level chord would have to guess which of the two the user meant
        # from something other than focus. Here the answer is the buffer the
        # caret is in, which is the only place the question has one answer.
        # `Ctrl+Shift+R` is free of all six binding mechanisms (nothing else
        # binds it, and Qt's tables bind Refresh to F5 on both schemes); it is
        # recorded in `shortcut_registry.RESERVED_SEQUENCES` so no rebinding can
        # be pointed at it.
        self._reload_shortcut = QShortcut(QKeySequence("Ctrl+Shift+R"), self)
        self._reload_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self._reload_shortcut.activated.connect(self.reload_requested.emit)

    def set_ddl_text(self, text: str, spans=None, schema=None) -> None:
        """Replace the synthesized buffer (a fresh `build_ddl_text` result).

        `spans` is that call's `DdlObjectSpan` list; it drives the shared fold
        base's foldable regions (§18.1) -- ONE region per DDL object body, from
        the object's banner line (`start_line`) through its `end_line`, so
        folding an object collapses its source under its banner. Passing None
        (or an empty list) simply leaves nothing foldable. `schema` is the
        `DatabaseSchema` that produced `spans`, retained (with the spans) so
        a later right-click can resolve the clicked object (§18.5)."""
        self.editor.setPlainText(text)
        spans = spans or []
        self.editor.set_fold_regions(_fold_regions_for_spans(spans))
        self._spans = spans
        self._schema = schema

    def navigate_to_line(self, line: int) -> None:
        """Jump to `line` (1-based) — BrowserPanel's `navigate_requested`
        target, delegating to CodeEditor's shared navigation API (§8)."""
        self.editor.navigate_to_line(line)
        self.editor.setFocus()

    def _span_at_line(self, line: int):
        """The `DdlObjectSpan` whose `start_line..end_line` contains the
        1-based `line`, or None outside any object's body."""
        for span in self._spans:
            if span.start_line <= line <= span.end_line:
                return span
        return None

    #: The reserved editor chord set (`EDITOR_CHORDS`), claimed AND
    #: answered here (BUG-048).
    #: Shaped after `DdlObjectEditorPanel.eventFilter`'s §18.5 carve-out 1, for
    #: the same hazard at the sibling site nobody filtered: a read-only
    #: `QPlainTextEdit` does not claim the `ShortcutOverride` for undo/redo, so
    #: without this the window-level Ctrl+Z QShortcut fired here and silently
    #: reverted the **Raw XML project buffer** — a different document than the
    #: one on screen. The object tab routes the key into its own undo stack;
    #: this buffer is synthesized by `build_ddl_text` and read-only by design
    #: (§18.1), so there is no stack to route to and the honest answer is to
    #: state the reason (FQ-023) rather than to leave a dead key.
    _UNDO_REDO_REFUSAL = "this buffer is read only — there is nothing to undo here"

    #: The same shape for the four chords that would EDIT (paste, and the three
    #: line-editing gestures the app took ownership of on 2026-08-10). They are
    #: answered here, but the answer is a stated reason rather than an edit: the
    #: buffer is synthesized by `build_ddl_text` and read-only by design (§18.1),
    #: and `apply_editor_operation` refuses a read-only editor on its own — so
    #: without this the key would be silently dead, which FQ-023 rules out. It is
    #: a DIFFERENT sentence from the undo one on purpose: none of these asks for
    #: an undo, and "there is nothing to undo here" would be the wrong reason.
    _EDIT_REFUSAL = "this buffer is read only — edit the object in its own tab"

    def eventFilter(self, obj, event) -> bool:
        operation = (
            classify_editor_chord(event)
            if obj is self.editor
            and event.type()
            in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress)
            else None
        )
        if operation is not None:
            if event.type() == QEvent.Type.ShortcutOverride:
                # Claiming the sequence is what stops the window shortcut;
                # answering the KeyPress is what stops the silence. Both halves
                # are required — writing only the second changes nothing.
                event.accept()
            elif operation in (UNDO, REDO):
                self.editor.report_refusal(self._UNDO_REDO_REFUSAL)
            elif is_mutating_editor_operation(operation):
                self.editor.report_refusal(self._EDIT_REFUSAL)
            elif operation == CLAIMED_NOT_UNDO_REDO:
                # `Ctrl+Shift+Z` = Shrink Selection (FQ-034), and it RUNS here
                # even though every other gesture in this panel refuses: the
                # buffer is read-only, and **read-only is irrelevant to
                # selecting** — the same argument that keeps `Select All` and
                # `Ctrl+Shift+B` live in this panel (§8). So no refusal is owed,
                # and none is stated; the ladder simply works on the synthesized
                # DDL, which is the surface where reading structure matters most.
                apply_shrink_structural_selection(self.editor)
            # else: the `Alt+Backspace` pair (suppressed app-wide so the keyboard
            # is identical on both platforms), claimed here for the same reason as
            # everywhere else — Qt would otherwise answer it itself — but the
            # read-only refusal above must NOT be stated for it: it does not ask
            # for an undo, so answering "nothing to undo here" would be a wrong
            # reason, which is worse than none.
            return True
        if obj is self.editor and event.type() == QEvent.Type.ContextMenu:
            menu = self._build_context_menu_at(event.pos())
            menu.exec(event.globalPos())
            return True
        return super().eventFilter(obj, event)

    def _build_context_menu_at(self, local_pos):
        """Build (but do not exec) the context menu for a click at
        `local_pos` (editor-widget coordinates) -- split out from
        `eventFilter` so tests can inspect it directly instead of ever
        driving a real modal `QMenu.exec` (the `xml_editor.py`
        `_build_context_menu` precedent)."""
        # event.pos() is delivered in the editor's own coordinates, but
        # cursorForPosition expects viewport coordinates (xml_editor.py's
        # contextMenuEvent precedent) -- move the caret to the clicked
        # position FIRST, so the resolved span reflects the click rather than
        # a stale caret (§18.5, D1).
        viewport_pos = self.editor.viewport().mapFrom(self.editor, local_pos)
        cursor = self.editor.cursorForPosition(viewport_pos)
        self.editor.setTextCursor(cursor)
        line = cursor.blockNumber() + 1
        span = self._span_at_line(line)
        menu = self.editor.createStandardContextMenu()
        # A browse-only instance still gets the standard (copy/select-all) menu
        # -- reading the buffer is the whole point of it -- just no Edit DDL.
        if not self._browse_only and span is not None and self._schema is not None:
            resolved = resolve_edit_target(self._schema, span)
            if resolved is not None:
                ref, source = resolved
                menu.addSeparator()
                # ONE editing entry (FQ-024), still carrying the full object
                # identity: the click landed somewhere in a whole-schema buffer,
                # so the entry has to say WHICH object it resolved to -- and two
                # overloads of one name must read differently.
                menu.addAction(
                    f"Edit DDL: {ref.qualified}",
                    lambda: self.edit_requested.emit(ref, source),
                )
        # Reload DDL (BUG-062), offered ANYWHERE in the buffer -- outside every
        # object's span, and on a browse-only instance too. It is a property of
        # the CONNECTION this tab was filled from, not of the clicked object, so
        # unlike `Edit DDL` it has nothing to resolve and no reason to be absent.
        # The sandbox instance needs it most: applying to a sandbox is precisely
        # the operation whose result the user then wants to re-read.
        #
        # NO `setShortcut` here: `Ctrl+Shift+R` has exactly one keyboard host
        # (the QShortcut in `__init__`), and adding it to this action would be
        # the two-hosts-for-one-gesture defect DEC-012 forbids.
        menu.addSeparator()
        menu.addAction(RELOAD_LABEL, self.reload_requested.emit)
        return menu
