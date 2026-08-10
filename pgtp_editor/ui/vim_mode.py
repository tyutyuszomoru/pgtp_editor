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

# pgtp_editor/ui/vim_mode.py
"""`VimModeMixin`: the Qt half of the editing-mode layer (FQ-032, §8).

**Vim mode is not a fan feature. It IS the specification of the editing-primitive
layer the editor needs anyway.** The editors need advanced editing *operations*
regardless -- absolute go-to-line, **relative count-motions**, delete/change/yank
by word, by line, by motion -- and none of them exists today or has a menu
equivalent. The real choice was never *"vim or no vim"*; it was **adopt a standard
command vocabulary or invent one**, and Windows editors offer no such commands to
copy, so there is nothing to be consistent with. The case that decides it is
**`42j`**: a **count applied to a motion** is a grammar, not a command, and no
menu and no invented Ctrl-chord expresses it.

Terminology, owner-agreed and load-bearing
------------------------------------------
**Edit mode** is ordinary Windows-style typing (== vim's INSERT). **Command mode**
is the `Esc`-entered command state (== vim's NORMAL). **The word "normal" is
dropped from this feature entirely** because it collides with vim's own NORMAL and
would make every sentence ambiguous about which vocabulary it speaks.

The mode model -- five rules, and none of them is a setting
----------------------------------------------------------
* **No enable/disable setting and no persistence, anywhere.** Vim is always
  available (vim itself has no *"enable vim"* option), and a transient runtime
  fact stays out of `QSettings`.
* **Command mode is TRANSIENT and PER-EDITOR.** Every tab is independent; losing
  focus drops that editor back to Edit mode; **refocusing never resurrects it.**
  There is no *"which tab was in Command mode"* map anywhere.
* **On a read-only editor `Esc` does nothing and this layer is inactive
  ENTIRELY.** That deletes the whole motion-vs-mutation-in-a-read-only-buffer
  problem: no *"motions are fine but operators refuse"* split, no per-command
  read-only table, no new refusal sentences. The predicate is asked **at the
  keystroke** (`isReadOnly()`), never at construction, because Caption Mode and
  Compare/Merge flip it at runtime.
* **The mouse stays fully live in both editing modes and never changes the
  editing mode.** A click that moved the mode would make the indicator lie about
  a state the user did not ask to leave.
* **The plain (Edit-mode) editor gains NOTHING.** Every advanced operation lives
  only in Command mode. That is the sentence that makes this a specification
  rather than an addition: no invented parallel keymap ever appears in Edit mode.

ONE reset path, and it is a CORRECTNESS guarantee
-------------------------------------------------
:meth:`VimModeMixin._exit_command_mode` is the only way out, and every trigger
funnels into it -- **six** of them:

1. an insert-entry command (`i a I A o O s S cc C`, and `v` / `V`);
2. a `c{motion}` operator, which lands in Edit mode by definition;
3. **focus loss** (`focusOutEvent`) -- tab switch, click into another widget, the
   completion popup taking focus: all one mechanism, none special-cased;
4. the editor **becoming read-only** while Command mode holds (Caption Mode /
   Compare/Merge entry, through §8's `_set_raw_xml_read_only(reason)` seam) -- a
   mode that turns the buffer read-only under a Command-mode caret must not leave
   this layer live with nothing it may do;
5. a **document swap** (`setPlainText`) -- pending command state (a half-typed
   `42d`) describes a document that no longer exists;
6. executing a `:` palette command that **changes focus**, which is mechanically
   (3) and is listed separately only because it was an open question.

Six triggers with six ad-hoc resets is how one of them ends up missing, and the
missing one is a mode with no way out. **Since `DEC-260810193638` it is worse than
untidy: while Command mode holds, `Ctrl+R`'s Replace-focus is DEAD on that
editor**, so a mode left set is a silently broken `Ctrl+R` with nothing on screen
saying why except the indicator. `tests/ui/test_vim_mode.py` asserts that every
one of the six restores Replace-focus.

`focusOutEvent` is the established precedent, not a new idea: `CodeEditor` already
calls `exit_tab_stop_mode()` from it for exactly this reason. `XmlEditor` had no
`focusOutEvent` override at all, so this mixin supplies one for both families.

The interception seam is TWO mechanisms, and the split is stated
---------------------------------------------------------------
The editors are plain `QPlainTextEdit`s (not QScintilla).

* **Bare keys** are answered in :meth:`handle_command_mode_key`, which each host
  calls from its own `keyPressEvent` at the point the `Esc` precedence order puts
  it (see below). The host panels' `eventFilter`s see every key first but act only
  on a non-`None` `classify_editor_chord` answer, so letters reach the widget
  untouched -- and `u` is a **bare letter**: not in `EDITOR_CHORDS`, no row there,
  no reservation, invisible to all six surfaces' filters.
* **`Ctrl+R` needs the `ShortcutOverride` path** (:meth:`event`), the idiom the six
  surfaces already run for `Ctrl+Shift+Z`, because `Ctrl+R` is a live `QShortcut`
  (`find_replace_bar.install_focus_shortcuts`) and **a `QShortcut` outranks a
  widget's `keyPressEvent`**. This is the app's FIRST mode-conditional chord
  (`DEC-260810193638`) and **must not be read as licence for others**.

`Ctrl+D` / `Ctrl+K` / `Ctrl+U` are **not** answered here at all. They remain bound,
reserved and app-implemented at all six surfaces in Edit mode; **Command mode
declines them in exactly one place**, `code_editor.apply_editor_operation`, which
is the function whose docstring is *"the register of every boundary answer"*. Six
`eventFilter`s each testing the mode is six chances to drift, which is the argument
that centralised those chords to begin with.

Undo and redo route to the SURFACE's own answer
-----------------------------------------------
`u` and `Ctrl+R` call :meth:`vim_undo` / :meth:`vim_redo`, which default to the
editor's native stack -- correct for `CodeEditor`, because every one of its five
hosts answers `Ctrl+Z` with `self.editor.undo()`. `XmlEditor` overrides them to
emit `undo_requested` / `redo_requested`, its snapshot-history routing. Never
`QPlainTextEdit.undo()` from a bare-letter branch that bypassed the surface: that
is `F14`'s recorded defect, and reproducing it on a *reachable* key would be worse.

What this layer must NOT become
-------------------------------
* **Not a fourth minor mode.** The minor mode is winner-take-all and
  window-scoped; the editing mode is orthogonal and per-editor.
* **No dispatcher.** The editor that has focus is the editor the keys go to --
  Qt's own answer, needing no `active_*_editor()` branch.
* **No shortcut registry, so the vim keys are NOT rebindable.** FQ-012's machinery
  governs menu-action shortcuts; this is a separate keymap inside the editor, and
  the whole point is that it is a *standard* vocabulary.
* **No menu entry, no toolbar button, no setting.**
* **No new chord row and no new reservation.** Every chord claimed (`Esc`,
  `Ctrl+R`, `Ctrl+D`, `Ctrl+K`, `Ctrl+U`) was already reserved, so
  `RESERVED_SEQUENCES` gains nothing and the ledger test's set equality does not
  move. What is owed is **reason strings**.
* **No `sql/` call.** v1 motions are family-agnostic character and line
  arithmetic: `w`/`b`/`e` are vim's character-class rule (`pgtp_editor/vim/words`)
  and `%` is a character-level bracket scan, the same family as
  `code_editor.enclosing_bracket_span`. `sql/block_spans.py::structure_chain` is
  the DEFERRED text objects' dependency and is not consumed here -- this layer
  serves XML, PHP and JS buffers too, so a motion reading a SQL span model would
  be wrong on four of the six surfaces.

Deviation from the spec's letter, stated rather than hidden
----------------------------------------------------------
§8 says the answer lives in *"the vim mixin's `keyPressEvent`"*. Both host families
already own a long `keyPressEvent` whose ORDER is load-bearing (`Esc` has six
meanings and tab-stop mode must beat Command-mode entry), so the shared answer is
:meth:`handle_command_mode_key` and each host calls it at its own correct point.
The *answer* is in the shared layer, which is what the rule protects; putting it in
an MRO-shadowed `keyPressEvent` would have been dead code.
"""
from __future__ import annotations

import weakref
from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QWidget,
)

from pgtp_editor.ui.completion_popup import _CompletionPopup
from pgtp_editor.ui.mode_indicator import EDITING_COMMAND, EDITING_EDIT
from pgtp_editor.vim import (
    LINEWISE,
    REDO_KEY,
    Command,
    VimGrammar,
    word_backward,
    word_end,
    word_forward,
)

#: Qt's paragraph separator, which `QTextCursor.selectedText()` uses in place of
#: `\n`. Text on its way to the clipboard must be translated back.
_PARAGRAPH_SEPARATOR = "\u2029"

#: The refusal the `:` palette gives where it has no namespace to offer -- i.e.
#: in `CodeEditorDialog`, which is deliberately menu-less. **It must SAY this
#: rather than open an empty palette**: the palette's namespace IS the menu tree,
#: and an empty command line is the "dead control" posture §7 forbids.
PALETTE_UNAVAILABLE = (
    "the ':' command line lists this window's menu commands, and this dialog has "
    "no menus"
)

#: `n` / `N` drive the app's EXISTING Find bar -- there is no second search
#: engine and no second results surface. The bar searches FORWARDS only
#: (`FindReplaceBar.find_next`), so `N` states that instead of inventing a
#: backwards search of its own.
NO_BACKWARD_SEARCH = (
    "the Find bar searches forwards only — there is no backwards search to run"
)

#: What `/` and `n` say on a surface that has no Find bar at all.
NO_FIND_BAR = "this editor has no Find bar to search with"


# -- the editing-mode change registry -----------------------------------------
#
# The indicator must follow an editing-mode transition on ANY editor, including
# tabs created at runtime in three different files. A per-editor signal
# connection would need a wiring line per creation site and the next tab type
# would have to remember, so the mode PUBLISHES instead -- exactly as
# `ui/editor_gutter.py` publishes bookmark changes "without knowing this panel
# exists", and for the same reason: the producer is per-widget and dynamic, the
# consumer is one long-lived host. Bound methods are held **weakly**, so an
# observer's owner is never kept alive by this list.
_editing_mode_observers: list = []


def add_editing_mode_observer(callback: Callable[[object], None]) -> None:
    """Subscribe `callback` to every editor's editing-mode transitions; it is
    called as ``callback(editor)``.

    Idempotent per callback, so a host that re-runs its wiring does not
    double-notify."""
    entry = weakref.WeakMethod(callback) if hasattr(callback, "__self__") else callback
    for existing in _editing_mode_observers:
        if _resolve_observer(existing) == callback:
            return
    _editing_mode_observers.append(entry)


def remove_editing_mode_observer(callback: Callable[[object], None]) -> None:
    """Unsubscribe `callback`; a no-op if it is not registered."""
    for existing in list(_editing_mode_observers):
        if _resolve_observer(existing) in (callback, None):
            _editing_mode_observers.remove(existing)


def _resolve_observer(entry):
    """The live callable behind a registry entry, or None once it has died."""
    return entry() if isinstance(entry, weakref.WeakMethod) else entry


def _notify_editing_mode_observers(editor) -> None:
    """Publish `editor` to every live observer.

    A dead observer (its owner garbage-collected, or its C++ object destroyed) is
    dropped rather than raised through: this runs inside a keystroke, and a
    keystroke may not fail. Any other exception propagates, because that is a real
    bug in an observer and hiding it would make the indicator lie silently."""
    for entry in list(_editing_mode_observers):
        callback = _resolve_observer(entry)
        if callback is None:
            if entry in _editing_mode_observers:
                _editing_mode_observers.remove(entry)
            continue
        try:
            callback(editor)
        except RuntimeError:
            if entry in _editing_mode_observers:
                _editing_mode_observers.remove(entry)


# -- the `:` palette's matcher (pure, so it is tested without a widget) --------
def palette_matches(query: str, entries) -> list[tuple[str, str]]:
    """The `(command_id, label)` entries `query` selects, best first.

    **The verb rule is the FULL menu path**, not the leaf label: leaf labels are
    not unique across two menu bars (`Reload DDL` exists as a menu action *and*
    two context-menu forms), and a palette whose verb is ambiguous has to invent a
    disambiguator -- which is a second vocabulary. The palette therefore matches
    and echoes `Deployment › Apply to quality`.

    Matching is a case-insensitive **subsequence** over the path with separators
    and spaces ignored, so `:deployqual` finds it; ranking prefers an earlier
    first hit and then a shorter label, so the most specific match leads.
    """
    needle = "".join(query.lower().split())
    needle = needle.replace("›", "").replace(">", "")
    ranked: list[tuple[int, int, str, str]] = []
    for command_id, label in entries:
        haystack = "".join(str(label).lower().split()).replace("›", "")
        if not needle:
            ranked.append((0, len(str(label)), command_id, str(label)))
            continue
        index = 0
        first = -1
        for character in needle:
            index = haystack.find(character, index)
            if index < 0:
                break
            if first < 0:
                first = index
            index += 1
        else:
            ranked.append((first, len(str(label)), command_id, str(label)))
    ranked.sort(key=lambda row: (row[0], row[1], row[3]))
    return [(command_id, label) for _first, _length, command_id, label in ranked]


class VimCommandLine(QWidget):
    """The `:` command line -- a transient widget **over the editor**.

    **It may NOT live in the status bar.** §7's owner rule is that the bar is
    static-only (*"a slot either always states a defined fact, or it does not
    belong"*) and `StaticStatusBar.showMessage` is overridden to paint nothing. It
    is **not a `QDialog`** either, because `Esc` inside it must cancel the palette
    and return to **Command mode** rather than reaching row 6 of the `Esc`
    precedence table and cancelling a dialog.

    Its namespace **is** the app's own menu tree, derived through
    `ToolbarController.collect_menu_commands()`; nothing here is designed, so the
    `:` vocabulary auto-syncs as the menus change and there is never a second
    vocabulary to maintain. Completion reuses the shipped `_CompletionPopup`
    rather than a new list widget -- but never gives it focus, so the caret stays
    in this line while the list filters underneath it.
    """

    #: The chosen command's id, or `"set wrap"` / `"set nowrap"`.
    accepted = Signal(str)
    #: `Esc`: back to Command mode with the buffer untouched.
    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._entries: list[tuple[str, str]] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)
        self._prompt = QLabel(":", self)
        self._field = QLineEdit(self)
        self._field.setFrame(False)
        layout.addWidget(self._prompt)
        layout.addWidget(self._field)
        self._popup = _CompletionPopup(self)
        self._popup.chosen.connect(self._choose_key)
        self._field.textChanged.connect(self._refilter)
        self._field.returnPressed.connect(self._accept_current)
        self._field.installEventFilter(self)
        self.setAutoFillBackground(True)

    # -- the surface the mixin drives ---------------------------------------
    @property
    def field(self) -> QLineEdit:
        return self._field

    @property
    def popup(self) -> _CompletionPopup:
        return self._popup

    def open_with(self, entries) -> None:
        """Show the line over the editor, offering `entries`."""
        self._entries = [(str(cid), str(label)) for cid, label in entries]
        self._field.clear()
        self._refilter("")
        self.show()
        self._field.setFocus()

    def close_line(self) -> None:
        self._popup.hide()
        self.hide()

    def matches(self) -> list[tuple[str, str]]:
        """The current query's matches -- what the popup is showing."""
        return palette_matches(self._field.text(), self._entries)

    # -- internals ----------------------------------------------------------
    def _refilter(self, _text: str = "") -> None:
        text = self._field.text()
        if text.strip().lower().startswith("set"):
            # `:set` is not a menu command, so the menu namespace has nothing to
            # offer for it. v1's option list is `wrap` / `nowrap` and nothing
            # else: `:set` may only reach an option the app ALREADY has, so the
            # palette never becomes the place a setting is invented.
            self._popup.set_items([("set wrap", "set wrap"), ("set nowrap", "set nowrap")])
        else:
            self._popup.set_items([(cid, label) for cid, label in self.matches()])
        self._place_popup()

    def _place_popup(self) -> None:
        if not self._popup.count():
            self._popup.hide()
            return
        if self.isVisible():
            self._popup.move(self.mapToGlobal(self.rect().topLeft()))
            self._popup.resize(max(self.width(), 240), min(220, 22 * self._popup.count() + 8))
            self._popup.show()
            # Focus stays in the field: the popup is a filtered DISPLAY here, and
            # a popup that stole focus would drop Command mode through the one
            # reset path and cancel the palette out from under the user.
            self._field.setFocus()

    def _choose_key(self, key: str) -> None:
        self.accepted.emit(key)

    def _accept_current(self) -> None:
        text = self._field.text().strip()
        lowered = text.lower()
        if lowered.startswith("set"):
            option = lowered[3:].strip()
            if option in ("wrap", "nowrap"):
                self.accepted.emit(f"set {option}")
                return
            self.accepted.emit(f"set?{option}")  # refused by the mixin, with the reason
            return
        matches = self.matches()
        if not matches:
            self.accepted.emit(f"?{text}")  # refused by the mixin, with the reason
            return
        key = self._popup.current_key() or matches[0][0]
        self.accepted.emit(key)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._field and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.cancelled.emit()
                return True
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down) and self._popup.count():
                row = self._popup.currentRow()
                row += 1 if key == Qt.Key.Key_Down else -1
                self._popup.setCurrentRow(max(0, min(self._popup.count() - 1, row)))
                return True
        return super().eventFilter(obj, event)


class VimModeMixin:
    """Command mode over both editor families. See the module docstring.

    Mixed in **before** `QPlainTextEdit`, with **no `__init__` of its own** (the
    `GutterBookmarkFoldMixin` / `CompletionPopupHostMixin` idiom); each host calls
    :meth:`_init_vim_mode` from its own constructor after `super().__init__()`.
    """

    #: Emitted on every editing-mode transition of THIS editor. The registry
    #: above is what the main window listens to; this signal is for a host that
    #: owns exactly one editor and renders its mode locally -- i.e.
    #: `CodeEditorDialog`'s chrome, which has no `MainWindow` to ask.
    editing_mode_changed = Signal()

    # --- setup -------------------------------------------------------------
    def _init_vim_mode(self) -> None:
        """Declare the editing-mode state. Call from the host's ``__init__``.

        Note what is NOT here: no setting is read, nothing is restored, and no
        registry of *"which editor was in Command mode"* is consulted. Every
        editor starts in **Edit mode**, always.
        """
        self._vim_command_mode = False
        self._vim_grammar = VimGrammar()
        self._vim_command_line: VimCommandLine | None = None
        self._vim_command_provider = None

    # --- the mode ----------------------------------------------------------
    @property
    def in_command_mode(self) -> bool:
        """Whether THIS editor is in Command mode. False on every editor that
        has not just been sent `Esc`, and False on every read-only one."""
        return bool(getattr(self, "_vim_command_mode", False))

    def editing_mode_label(self) -> str | None:
        """What the mode indicator renders, or **None** when the segment must be
        ABSENT -- i.e. on a read-only editor, where this layer is inactive
        entirely and the buffer already names itself in its tab title."""
        if self.isReadOnly():
            return None
        return EDITING_COMMAND if self.in_command_mode else EDITING_EDIT

    def enter_command_mode(self) -> bool:
        """`Esc` in an editable editor. Returns whether the mode changed.

        On a **read-only** editor this does nothing at all -- no hint, no journal
        line, no refusal (§8's `Esc` precedence, row 5). The predicate is asked
        HERE, at the keystroke, and never cached at construction, because Caption
        Mode and Compare/Merge flip `setReadOnly` at runtime.
        """
        if self.isReadOnly() or self.in_command_mode:
            return False
        self._vim_command_mode = True
        self._vim_grammar.reset()
        self._announce_editing_mode()
        return True

    def _exit_command_mode(self) -> bool:
        """**The ONE reset path.** Drops to Edit mode, discards any pending
        count/operator, and closes the `:` line. Idempotent, so every one of the
        six triggers may call it unconditionally.

        This is a correctness guarantee, not tidiness: while Command mode holds,
        `Ctrl+R`'s Replace-focus is dead on this editor (`DEC-260810193638`), so a
        mode left set is a silently broken `Ctrl+R`.
        """
        grammar = getattr(self, "_vim_grammar", None)
        if grammar is not None:
            grammar.reset()
        line = getattr(self, "_vim_command_line", None)
        if line is not None and line.isVisible():
            line.close_line()
        if not getattr(self, "_vim_command_mode", False):
            return False
        self._vim_command_mode = False
        self._announce_editing_mode()
        return True

    def _announce_editing_mode(self) -> None:
        self.editing_mode_changed.emit()
        _notify_editing_mode_observers(self)

    # --- the exit triggers Qt hands us -------------------------------------
    def focusOutEvent(self, event) -> None:
        """Exit trigger 3: **focus loss.** Tab switch, a click into another
        widget, a `:` command that opened a dialog, and the completion popup
        taking focus are all one mechanism here, none special-cased.

        The single carve-out is this editor's OWN `:` command line, which
        necessarily takes focus to be typed into. That narrows the trigger; it
        does not add a second reset path -- and it is what lets `Esc` in the
        palette return to Command mode as specified.
        """
        if not self._vim_focus_stays_in_command_mode():
            self._exit_command_mode()
        super().focusOutEvent(event)

    def _vim_focus_stays_in_command_mode(self) -> bool:
        line = getattr(self, "_vim_command_line", None)
        if line is None or not line.isVisible():
            return False
        focused = QApplication.focusWidget()
        if focused is None:
            return False
        return focused is line or line.isAncestorOf(focused) or focused is line.popup

    def setReadOnly(self, read_only: bool) -> None:
        """Exit trigger 4: the editor **becomes read-only** while Command mode
        holds (Caption Mode / Compare/Merge entry, through §8's
        `_set_raw_xml_read_only(reason)` seam). A mode that turns the buffer
        read-only under a Command-mode caret must not leave this layer live with
        nothing it may do."""
        changed = bool(read_only) and self.in_command_mode
        super().setReadOnly(read_only)
        if changed:
            self._exit_command_mode()
        elif getattr(self, "_vim_grammar", None) is not None:
            # The indicator's editing-mode segment is PRESENT exactly when the
            # focused editor is editable, so a read-only flip changes it even
            # from Edit mode.
            self._announce_editing_mode()

    def setPlainText(self, text: str) -> None:
        """Exit trigger 5: a **document swap.** The same moment that resets
        bookmarks, fold state, the FQ-031 gutter anchor and FQ-034's expansion
        stack: pending command state (a half-typed `42d`) describes a document
        that no longer exists."""
        self._exit_command_mode()
        super().setPlainText(text)

    # --- the `Ctrl+R` interposer ------------------------------------------
    def event(self, e) -> bool:
        """Accept `Ctrl+R`'s `ShortcutOverride` while Command mode holds.

        **This is the only way Command mode can answer that chord.** `Ctrl+R` is a
        live `QShortcut` (`install_focus_shortcuts`, `WidgetWithChildrenShortcut`,
        six hosts plus the caption panel's own pair) and **a `QShortcut` outranks a
        widget's `keyPressEvent`**, so without claiming the override the Replace
        field would take the key before this editor ever saw it. It is the shape
        the six surfaces already run for `Ctrl+Shift+Z` -- an existing, proven
        idiom that simply became unavoidable here.

        In **Edit mode** nothing is claimed, so `Ctrl+R` keeps focusing Replace,
        which is the whole of the mode-conditionality (`DEC-260810193638`).
        """
        if (
            e.type() == QEvent.Type.ShortcutOverride
            and self.in_command_mode
            and e.key() == Qt.Key.Key_R
            and e.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            e.accept()
            return True
        return super().event(e)

    # --- the keyboard ------------------------------------------------------
    def handle_command_mode_key(self, event) -> bool:
        """Answer one key press. Returns whether Command mode consumed it.

        Each host calls this from its own `keyPressEvent` at the point the `Esc`
        precedence order puts it -- **after** the completion popup (which has
        focus, so the editor never sees the key), after a `FindReplaceBar` field
        (a different widget), after tab-stop mode, and after the
        `classify_editor_chord` block so `Ctrl+Z`/`Ctrl+Y`/`Ctrl+D`/`Ctrl+K`/
        `Ctrl+U` keep their surface answers.
        """
        if self.isReadOnly():
            # Row 5: vim is inactive ENTIRELY on a read-only buffer. Also the
            # backstop for trigger 4, in case something set `setReadOnly` behind
            # this mixin's back.
            self._exit_command_mode()
            return False

        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_Escape:
            if self.in_command_mode:
                # Row 4': discard any pending count/operator and STAY in Command
                # mode. `Esc` never leaves the mode.
                self._vim_grammar.reset()
                return True
            return self.enter_command_mode()

        if not self.in_command_mode:
            return False

        if key == Qt.Key.Key_R and modifiers == Qt.KeyboardModifier.ControlModifier:
            return self._vim_feed(REDO_KEY)

        if modifiers & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            # Every other chord keeps its Edit-mode meaning. Command mode claims
            # exactly four `Ctrl` chords and three of them are declined
            # elsewhere, in `apply_editor_operation`.
            return False

        if key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_Home,
            Qt.Key.Key_End,
            Qt.Key.Key_PageUp,
            Qt.Key.Key_PageDown,
        ):
            # Navigation keys move the caret in Command mode exactly as they do in
            # Edit mode, the same posture the mouse has.
            return False

        # The three keys that would MUTATE the buffer if they fell through, given
        # their vim meanings so they are answered rather than swallowed.
        substitutes = {
            Qt.Key.Key_Backspace: "h",
            Qt.Key.Key_Return: "j",
            Qt.Key.Key_Enter: "j",
            Qt.Key.Key_Delete: "x",
        }
        if key in substitutes:
            return self._vim_feed(substitutes[key])
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            # Consumed with no answer: a Tab that inserted a tab character would
            # mutate the buffer from Command mode, and vim has no Tab command to
            # borrow. The indicator is what explains why the key did nothing.
            return True

        text = event.text()
        if not text or not text.isprintable():
            return True
        consumed = False
        for character in text:
            consumed = self._vim_feed(character) or consumed
        return True

    def _vim_feed(self, token: str) -> bool:
        command = self._vim_grammar.feed(token)
        if command is None:
            return True
        self._vim_run(command)
        return True

    # --- running a resolved command ---------------------------------------
    def _vim_run(self, command: Command) -> None:
        if command.action is not None:
            self._vim_run_action(command)
            return
        if command.operator is not None:
            self._vim_run_operator(command)
            return
        position = self._vim_motion_position(command)
        if position is None:
            return
        cursor = self.textCursor()
        cursor.setPosition(position)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    # --- motions -----------------------------------------------------------
    def _vim_motion_position(self, command: Command) -> int | None:
        """The caret offset `command`'s motion resolves to, or None -- in which
        case the refusal has already been STATED (FQ-023: a gesture that cannot
        run says why, never nothing)."""
        motion = command.motion
        count = max(1, command.count)
        cursor = self.textCursor()
        position = cursor.position()
        block = cursor.block()
        line_start = block.position()
        line_end = line_start + block.length() - 1

        if motion == "h":
            target = max(line_start, position - count)
            return self._vim_moved(target, position, "already at the start of the line")
        if motion == "l":
            target = min(line_end, position + count)
            return self._vim_moved(target, position, "already at the end of the line")
        if motion in ("j", "k"):
            return self._vim_vertical(motion, count, position, block)
        if motion in ("w", "b", "e"):
            return self._vim_word(motion, count, position)
        if motion == "0":
            return line_start
        if motion == "^":
            return line_start + self._vim_indent_width(block.text())
        if motion == "$":
            return line_end
        if motion in ("gg", "G"):
            return self._vim_absolute_line(command, motion)
        if motion in ("{", "}"):
            return self._vim_paragraph(motion, count, block)
        if motion in ("f", "t", "F", "T"):
            return self._vim_find_char(motion, count, command.target, position, block)
        if motion == "%":
            return self._vim_bracket_match(position, block)
        return None

    def _vim_moved(self, target: int, position: int, reason: str) -> int | None:
        if target == position:
            self.report_refusal(reason)
            return None
        return target

    def _vim_word(self, motion, count, position) -> int | None:
        """`w` / `b` / `e`, by **vim's own character-class rule**.

        Delegated to the Qt-free `pgtp_editor/vim/words.py`, and deliberately NOT
        to `sql/tokenizer.py`: a vim word is not a SQL token, and this layer
        serves XML, PHP and JS buffers where no SQL tokenizer applies.
        """
        text = self.toPlainText()
        target = position
        for _ in range(count):
            if motion == "w":
                target = word_forward(text, target)
            elif motion == "b":
                target = word_backward(text, target)
            else:
                target = word_end(text, target)
        reason = {
            "w": "there is no word after the caret",
            "b": "there is no word before the caret",
            "e": "there is no word end after the caret",
        }[motion]
        return self._vim_moved(target, position, reason)

    def _vim_vertical(self, motion, count, position, block) -> int | None:
        document = self.document()
        current = block.blockNumber()
        last = document.blockCount() - 1
        wanted = current + count if motion == "j" else current - count
        if wanted > last:
            available = last - current
            self.report_refusal(
                f"there are only {available} lines below the caret"
                if available
                else "already on the last line"
            )
            return None
        if wanted < 0:
            self.report_refusal(
                f"there are only {current} lines above the caret"
                if current
                else "already on the first line"
            )
            return None
        column = position - block.position()
        target_block = document.findBlockByNumber(wanted)
        return target_block.position() + min(column, max(0, target_block.length() - 1))

    def _vim_absolute_line(self, command: Command, motion: str) -> int | None:
        document = self.document()
        last = document.blockCount() - 1
        if motion == "gg" and not command.has_count:
            number = 0
        elif motion == "G" and not command.has_count:
            number = last
        else:
            number = command.count - 1
        if number > last:
            self.report_refusal(f"the document has only {last + 1} lines")
            return None
        target_block = document.findBlockByNumber(max(0, number))
        return target_block.position() + self._vim_indent_width(target_block.text())

    def _vim_paragraph(self, motion, count, block) -> int | None:
        """`{` / `}`: the previous / next blank line -- pure blank-line
        arithmetic over the buffer, nothing language-aware."""
        document = self.document()
        last = document.blockCount() - 1
        number = block.blockNumber()
        step = 1 if motion == "}" else -1
        found = number
        for _ in range(count):
            probe = found + step
            while 0 <= probe <= last and document.findBlockByNumber(probe).text().strip():
                probe += step
            if not 0 <= probe <= last:
                found = last if step > 0 else 0
                break
            found = probe
        if found == number:
            self.report_refusal(
                "there is no blank line after the caret"
                if step > 0
                else "there is no blank line before the caret"
            )
            return None
        return document.findBlockByNumber(found).position()

    def _vim_find_char(self, motion, count, target, position, block) -> int | None:
        """`f` / `t` / `F` / `T`: a character search **on the current line**."""
        if not target:
            return None
        line = block.text()
        column = position - block.position()
        forward = motion in ("f", "t")
        till = motion in ("t", "T")
        found = column
        for _ in range(count):
            index = line.find(target, found + 1) if forward else line.rfind(target, 0, max(0, found))
            if index < 0:
                found = -1
                break
            candidate = index - 1 if (till and forward) else index + 1 if till else index
            if till and candidate == found:
                # `t` immediately before its target is not a move; look further.
                index = (
                    line.find(target, index + 1)
                    if forward
                    else line.rfind(target, 0, index)
                )
                if index < 0:
                    found = -1
                    break
                candidate = index - 1 if forward else index + 1
            found = candidate
        if found < 0:
            direction = "after" if forward else "before"
            self.report_refusal(
                f"no '{target}' {direction} the caret on this line"
            )
            return None
        return block.position() + found

    def _vim_bracket_match(self, position, block) -> int | None:
        """`%`: **character-level** bracket matching, the same family as
        `code_editor.enclosing_bracket_span`.

        It inherits a divergence this project already records and accepts: a
        character-level scan counts a `(` inside a string literal or a comment.
        `Ctrl+Shift+B` has exactly the same property and both implementations
        survive, *because they also serve PHP and JS tabs, which have no SQL
        tokenizer to consult.* `%` is in the same position for the same reason, so
        it takes the same answer rather than a new one -- and it must NOT reach
        for FQ-034's token-level paren rung.
        """
        openers = "([{"
        closers = ")]}"
        pairs = dict(zip(openers, closers))
        reverse = {value: key for key, value in pairs.items()}
        text = self.toPlainText()
        line_end = min(block.position() + block.length() - 1, len(text))
        index = position
        while index < line_end and text[index] not in openers + closers:
            index += 1
        if index >= line_end or text[index] not in openers + closers:
            self.report_refusal("there is no bracket on this line to match")
            return None
        character = text[index]
        if character in openers:
            depth = 0
            for probe in range(index, len(text)):
                if text[probe] == character:
                    depth += 1
                elif text[probe] == pairs[character]:
                    depth -= 1
                    if depth == 0:
                        return probe
        elif character in closers:
            depth = 0
            for probe in range(index, -1, -1):
                if text[probe] == character:
                    depth += 1
                elif text[probe] == reverse[character]:
                    depth -= 1
                    if depth == 0:
                        return probe
        self.report_refusal(f"'{character}' has no match in this buffer")
        return None

    @staticmethod
    def _vim_indent_width(line: str) -> int:
        return len(line) - len(line.lstrip())

    # --- operators ---------------------------------------------------------
    def _vim_run_operator(self, command: Command) -> None:
        """`d` / `c` / `y` over the range `command.motion` names.

        **There is no visual mode and therefore no selection target**: the two
        ways to operate on a range are operator+motion here, or select
        Windows-style and use `Ctrl+C`/`Ctrl+X`/`Delete` in Edit mode. A `d`
        pressed after a Windows-style selection is a Command-mode `d` waiting for
        a motion, not *"delete the selection"*.
        """
        span = (
            self._vim_linewise_span(command)
            if command.is_linewise
            else self._vim_motion_span(command)
        )
        if span is None:
            return
        start, end, clipboard_text = span
        self._vim_to_clipboard(clipboard_text)
        cursor = self.textCursor()
        if command.operator == "y":
            # vim leaves the caret at the start of a yank.
            cursor.setPosition(start)
            self.setTextCursor(cursor)
            return
        cursor.beginEditBlock()
        try:
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        if command.operator == "c":
            # Exit trigger 2: `c{motion}` lands in Edit mode by definition.
            self._exit_command_mode()

    def _vim_motion_span(self, command: Command):
        cursor = self.textCursor()
        position = cursor.position()
        target = self._vim_motion_position(command)
        if target is None:
            return None
        start, end = min(position, target), max(position, target)
        if command.is_inclusive and target > position:
            end = min(end + 1, self.document().characterCount() - 1)
        return start, end, self._vim_text_between(start, end)

    def _vim_linewise_span(self, command: Command):
        """`dd` / `yy` / `cc` (and `Y` / `S`) -- whole lines.

        Two variants, because vim's are different: a linewise **delete or yank**
        takes the trailing newline with the lines (or the preceding one on the
        last line, exactly as `apply_editor_operation`'s `DELETE_LINE` does),
        while `cc` **keeps the line** and clears its text so the caret has
        somewhere to type.

        The clipboard always receives the lines plus a trailing `\\n`, which is
        what makes `dd`+`p` move text. **`dd` therefore clobbers the clipboard** --
        vim's own behaviour, accepted deliberately, and the user who wanted their
        clipboard kept has `Ctrl+Z`.
        """
        document = self.document()
        block = self.textCursor().block()
        last = document.blockCount() - 1
        first_number = block.blockNumber()
        last_number = min(last, first_number + max(1, command.count) - 1)
        first_block = document.findBlockByNumber(first_number)
        last_block = document.findBlockByNumber(last_number)
        text_start = first_block.position()
        text_end = last_block.position() + last_block.length() - 1
        clipboard_text = self._vim_text_between(text_start, text_end) + "\n"
        if command.operator == "c":
            return text_start, text_end, clipboard_text
        start, end = text_start, text_end
        if last_number < last:
            end += 1  # take the trailing newline with the lines
        elif start > 0:
            start -= 1  # the last line has none: take the one before it instead
        return start, end, clipboard_text

    def _vim_text_between(self, start: int, end: int) -> str:
        probe = QTextCursor(self.document())
        probe.setPosition(start)
        probe.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        return probe.selectedText().replace(_PARAGRAPH_SEPARATOR, "\n")

    def _vim_to_clipboard(self, text: str) -> None:
        """**ONE shared SYSTEM clipboard, no vim registers.**

        `y` / `Y` and every delete write it -- that is vim's own unnamed-register
        behaviour, so `dd`+`p` moves text and it interoperates with
        `Ctrl+C`/`Ctrl+V` and with other applications. Two costs are accepted
        deliberately and must not be "fixed" into a register system: `dd`
        clobbers the clipboard, and **there is no linewise paste** (a linewise
        flag is a second piece of state travelling with the text, i.e. a parallel
        register by another name).
        """
        clipboard = QApplication.clipboard()
        if clipboard is not None and text:
            clipboard.setText(text)

    # --- actions -----------------------------------------------------------
    def _vim_run_action(self, command: Command) -> None:
        action = command.action
        if action in ("i", "v", "V"):
            # `v` / `V` are **insert-entry aliases**: there is NO visual mode, so
            # they drop to Edit mode and the user selects the Windows-native way,
            # with the mouse or Shift+motion (owner: selection is a Windows
            # method).
            self._exit_command_mode()
            return
        if action in ("a", "I", "A", "o", "O"):
            self._vim_insert_entry(action)
            return
        if action in ("p", "P"):
            self._vim_paste(action)
            return
        if action == "u":
            self.vim_undo()
            return
        if action == "redo":
            self.vim_redo()
            return
        if action == "r":
            self._vim_replace_char(command)
            return
        if action == "search":
            self._vim_search()
            return
        if action in ("find-next", "find-previous"):
            self._vim_search_step(action)
            return
        if action == "palette":
            self._vim_open_palette()

    def _vim_insert_entry(self, action: str) -> None:
        cursor = self.textCursor()
        block = cursor.block()
        line_start = block.position()
        line_end = line_start + block.length() - 1
        indent = block.text()[: self._vim_indent_width(block.text())]
        if action == "a":
            cursor.setPosition(min(line_end, cursor.position() + 1))
        elif action == "I":
            cursor.setPosition(line_start + self._vim_indent_width(block.text()))
        elif action == "A":
            cursor.setPosition(line_end)
        elif action == "o":
            cursor.setPosition(line_end)
            cursor.insertText("\n" + indent)
        elif action == "O":
            cursor.setPosition(line_start)
            cursor.insertText(indent + "\n")
            cursor.setPosition(line_start + len(indent))
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self._exit_command_mode()

    def _vim_paste(self, action: str) -> None:
        """`p` / `P`: paste plain text **INLINE**, exactly as `Ctrl+V` does.

        Routed through the path the app already owns -- `apply_editor_operation`'s
        `PASTE` branch, delegating to `QPlainTextEdit.paste()` -- so the read-only
        guard and the single undo step stay Qt's and this layer adds only the
        gesture. `PASTE` is explicitly **not** among the operations Command mode
        declines (`DEC-260810193637` freed three, not four).

        With no linewise flag the two differ only in caret placement: `p` pastes
        after the caret, `P` at it.
        """
        from pgtp_editor.ui.code_editor import PASTE, apply_editor_operation

        if action == "p":
            cursor = self.textCursor()
            block = cursor.block()
            line_end = block.position() + block.length() - 1
            cursor.setPosition(min(line_end, cursor.position() + 1))
            self.setTextCursor(cursor)
        apply_editor_operation(self, PASTE)

    def _vim_replace_char(self, command: Command) -> None:
        count = max(1, command.count)
        cursor = self.textCursor()
        block = cursor.block()
        line_end = block.position() + block.length() - 1
        if cursor.position() + count > line_end:
            self.report_refusal(
                "there are fewer than "
                f"{count} characters left on this line to replace"
            )
            return
        cursor.beginEditBlock()
        try:
            cursor.setPosition(cursor.position() + count, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText((command.target or "") * count)
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)

    # --- undo / redo, routed to the SURFACE's answer -----------------------
    def vim_undo(self) -> None:
        """`u`. The default is this editor's own stack, which IS every
        `CodeEditor` surface's answer to `Ctrl+Z` (all five call
        `self.editor.undo()`). `XmlEditor` overrides it, because its answer is the
        window's snapshot history."""
        self.undo()

    def vim_redo(self) -> None:
        """`Ctrl+R`, and **only** in Command mode. `Ctrl+Y` remains the app's redo
        everywhere (DEC-015, unchanged)."""
        self.redo()

    # --- the app's EXISTING Find bar --------------------------------------
    def vim_find_bar(self):
        """This editor's `FindReplaceBar`, or None.

        Resolved by walking up the parent chain for a bar whose `editor` IS this
        editor, rather than by a wiring line per creation site: the six bars are
        built in five different files, three of them at runtime, and the next tab
        type would have to remember.
        """
        from pgtp_editor.ui.find_replace_bar import FindReplaceBar

        widget = self.parentWidget()
        while widget is not None:
            for bar in widget.findChildren(FindReplaceBar):
                if bar.editor is self:
                    return bar
            if widget.isWindow():
                break
            widget = widget.parentWidget()
        return None

    def _vim_search(self) -> None:
        """`/`: opens and drives the app's EXISTING Find bar. **No second search
        engine, and no second results surface.**

        Focusing the bar is a focus loss on this editor, so it drops Command mode
        through the one reset path -- which is correct and needs no special case.
        """
        bar = self.vim_find_bar()
        if bar is None:
            self.report_refusal(NO_FIND_BAR)
            return
        bar.focus_find()

    def _vim_search_step(self, action: str) -> None:
        if action == "find-previous":
            self.report_refusal(NO_BACKWARD_SEARCH)
            return
        bar = self.vim_find_bar()
        if bar is None:
            self.report_refusal(NO_FIND_BAR)
            return
        bar.find_next()

    # --- the `:` palette ---------------------------------------------------
    def set_vim_command_provider(self, provider) -> None:
        """Install an explicit `() -> [(command_id, label), ...]` provider plus
        its trigger, overriding the window lookup below. Used by tests."""
        self._vim_command_provider = provider

    def vim_command_entries(self):
        """The `:` namespace: the app's own menu tree, or None where there is
        none.

        **Derive, don't design.** The verbs come from the shipped FQ-012
        enumeration (`ToolbarController.collect_menu_commands`), reached by asking
        the top-level window -- so `:deploy quality` triggers the real
        `Deployment ▸ Apply to quality` `QAction`, the namespace auto-syncs as the
        menus change, and there is never a second vocabulary to maintain.

        **None means the palette is UNAVAILABLE and must say so**, which is
        exactly `CodeEditorDialog`: the palette's namespace IS the menu tree and a
        menu-less dialog has none.
        """
        provider = getattr(self, "_vim_command_provider", None)
        if provider is not None:
            return provider()
        window = self.window()
        hook = getattr(window, "vim_command_entries", None)
        if window is self or not callable(hook):
            return None
        return hook()

    def _vim_open_palette(self) -> None:
        entries = self.vim_command_entries()
        if entries is None:
            self.report_refusal(PALETTE_UNAVAILABLE)
            return
        line = self._vim_ensure_command_line()
        line.open_with(entries)
        self._vim_place_command_line()

    def _vim_ensure_command_line(self) -> VimCommandLine:
        line = getattr(self, "_vim_command_line", None)
        if line is None:
            line = VimCommandLine(self)
            line.accepted.connect(self._vim_palette_accepted)
            line.cancelled.connect(self._vim_palette_cancelled)
            line.hide()
            self._vim_command_line = line
        return line

    def _vim_place_command_line(self) -> None:
        line = self._vim_command_line
        if line is None:
            return
        height = line.sizeHint().height()
        viewport = self.viewport()
        line.setGeometry(0, max(0, viewport.height() - height), viewport.width(), height)

    def _vim_palette_cancelled(self) -> None:
        """`Esc` in the `:` line: cancel the palette and **return to Command
        mode** -- which is why this widget is not a `QDialog` (row 6 of the `Esc`
        precedence table would have cancelled the dialog instead)."""
        line = self._vim_command_line
        if line is not None:
            line.close_line()
        self.setFocus()

    def _vim_palette_accepted(self, key: str) -> None:
        line = self._vim_command_line
        if line is not None:
            line.close_line()
        self.setFocus()
        if key.startswith("set "):
            self._vim_set_option(key[4:].strip())
            return
        if key.startswith("set?"):
            self.report_refusal(
                f"':set {key[4:]}' is not an option — v1 has 'wrap' and 'nowrap'"
            )
            return
        if key.startswith("?"):
            self.report_refusal(f"no command matches ':{key[1:]}'")
            return
        entries = self.vim_command_entries() or []
        labels = {command_id: label for command_id, label in entries}
        if key not in labels:
            self.report_refusal(f"no command matches ':{key}'")
            return
        action = self._vim_action_for(key)
        if action is None:
            self.report_refusal(f"'{labels[key]}' is not available right now")
            return
        # A `:` command reaches its target through the EXISTING dispatch --
        # `collect_menu_commands()` plus `QAction.trigger()` -- and adds no fourth
        # dispatcher. One that changes focus resets Command mode through the one
        # focus-loss path, with no special case.
        action.trigger()

    def _vim_action_for(self, command_id: str):
        window = self.window()
        hook = getattr(window, "vim_command_action", None)
        if window is not self and callable(hook):
            return hook(command_id)
        return None

    def _vim_set_option(self, option: str) -> None:
        """`:set wrap` / `:set nowrap` -- **v1's whole `:set` vocabulary**, on one
        rule: `:set` may only reach an option the app ALREADY has, so the palette
        never becomes the place a setting is invented.

        `number` / `nonumber` are deliberately excluded: the gutter's line-number
        column is unconditional, so `:set nonumber` would be a NEW capability, and
        adding one *through the palette* is exactly the smuggling this rule
        forbids.
        """
        if option == "wrap":
            self.set_line_wrap_enabled(True)
            return
        if option == "nowrap":
            self.set_line_wrap_enabled(False)
            return
        self.report_refusal(
            f"':set {option}' is not an option — v1 has 'wrap' and 'nowrap'"
        )
