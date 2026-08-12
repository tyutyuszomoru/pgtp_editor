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

# pgtp_editor/ui/editor_gutter.py
"""The ONE gutter / bookmark / fold implementation in the codebase (spec §8).

Extracted verbatim out of ``ui/xml_editor.py`` so the DDL Explorer's
``CodeEditor`` (§18.1) reuses it instead of growing a second, near-duplicate
gutter. Two pieces:

- ``_EditorGutter`` — the QPlainTextEdit side-widget with its three zones
  (bookmark strip, fold-glyph zone, line numbers).
- ``GutterBookmarkFoldMixin`` — the generic, **block-number based** state and
  behavior: the bookmark set (``toggle_bookmark`` / ``bookmarked_lines`` /
  ``next_bookmark`` / ``prev_bookmark`` / ``clear_bookmarks`` /
  ``restore_bookmarks`` + cursor-line wrappers) and the fold-state machinery (``_fold_state`` / ``_toggle_fold`` /
  ``_is_line_hidden_by_other_collapsed_fold``), plus gutter width/geometry
  plumbing and the theme-aware gutter colors.

Mixed into a ``QPlainTextEdit`` subclass *before* ``QPlainTextEdit`` (so the
mixin's ``resizeEvent``/``setPlainText`` sit ahead of Qt's in the MRO), and
activated from the host's ``__init__`` by calling
``_init_gutter_bookmarks_folding()``. It deliberately has no ``__init__`` of
its own so the host's ``super().__init__(parent)`` still reaches
``QPlainTextEdit`` unchanged.

The **only pluggable piece** is the foldable-region provider: the mixin calls
``_foldable_region_starting_at(block)``, which must return
``(first_contained_block, last_contained_block)`` (0-based block numbers) for
the region starting on ``block``, or ``None``. ``XmlEditor`` overrides it with
its XML-span provider (over ``_spans``/``TagSpan``); the DDL ``CodeEditor``
overrides it with a ``DdlObjectSpan``-driven one (banner → ``end_line``). The
default here folds nothing.

Bookmark-change notifications (FQ-013 / FQ-014)
-----------------------------------------------
Two features outside this file need to know *when* an editor's bookmark set
changed: FQ-013's project-local persistence (which must save the changed set and
restore it after a document load) and FQ-014's ``[Bookmark]`` Audit rows (which
must be swept when the set is wiped, so a listing never outlives what it
describes). Neither may leak into this module: the mixin is a **Qt-widget-level
shared base** and must stay ignorant of projects, project folders, stores and
docks. So it *publishes* and never interprets — see
:func:`add_bookmark_observer`. Observers get ``(editor, reason)`` where reason is
one of :data:`BOOKMARKS_TOGGLED` / :data:`BOOKMARKS_CLEARED` /
:data:`BOOKMARKS_RESET`, and decide for themselves what it means.

Dual (body-relative) line numbers (FQ-031)
------------------------------------------
``plpgsql_check`` and PostgreSQL's own compile errors count lines from the
routine *body* — line 1 is the ``AS $$`` opener line — while this gutter counts
from the top of the buffer. In a DDL object tab the buffer is whole
``pg_get_functiondef`` output, so *"error at line 7"* is not gutter line 7. A
host may therefore hand this mixin an **anchor** with
:meth:`GutterBookmarkFoldMixin.set_body_line_anchor`, and the gutter then paints
a second, dimmed column of body-relative numbers left of the absolute ones.

It is **off by default and off after every** ``setPlainText``: the anchor starts
as ``None``, and with ``None`` every geometry and paint path is byte-identical to
what it was before this feature existed — the Raw XML editor, the PHP tabs, the
SQL console and the DDL Explorer buffer pay nothing (not a pixel of gutter
width) for a convenience that belongs to one tab.

A **module-level** registry rather than a per-editor signal, deliberately: every
editor in the app carries this mixin, most of them inside tabs created long after
the host was built (DDL object tabs, PHP file tabs, draft tabs, the
``Edit code…`` dialog), so a per-editor subscription would need a wiring line at
every construction site — six files, several of them owned by other lanes. One
subscription covers every editor that will ever exist. Bound methods are held
**weakly** (``weakref.WeakMethod``) so an observer does not keep its window
alive, and an observer whose underlying C++ object has been destroyed is dropped
rather than raised through — a notification fires from a single gutter click, and
a click may not blow up.
"""
from __future__ import annotations

import weakref
from collections.abc import Callable, Iterable

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QTextBlock, QTextCursor
from PySide6.QtWidgets import QWidget

from .theme_model import theme_for

# Fixed horizontal allowance reserved for the fold-triangle glyph, added on
# top of the digit-count-dependent width for line numbers.
_FOLD_GLYPH_WIDTH = 16

# Fixed horizontal allowance reserved on the LEFT of the gutter for the
# bookmark strip (where the rounded bookmark tags are drawn / clicked to
# toggle). Sits left of the fold zone and the line numbers, which both shift
# right by this amount.
_BOOKMARK_STRIP_WIDTH = 12

# Horizontal gap between the body-relative column and the absolute one, used
# ONLY when a body anchor is set (FQ-031). The separator rule is drawn down its
# middle. Zero cost when no anchor is set -- see `_gutter_width`.
_BODY_COLUMN_GAP = 7

# How far the body-relative number is blended toward the gutter background
# (0.0 = the normal foreground, 1.0 = invisible). Dimmed so the absolute number
# stays the primary one the eye lands on.
_BODY_NUMBER_DIM = 0.45

# The theme-aware gutter colors, shared by every editor that carries the mixin.
# Read from the theme file's `decorations` (FQ-260812021715) rather than spelled
# here: the gutter is an editor decoration like the current-line band, and a
# second per-theme table outside the theme file is the mistake
# `mode_indicator.py`'s docstring records.


def _gutter_colors(light: bool) -> tuple[str, str]:
    """The gutter's `(background, foreground)` for the theme."""
    theme = theme_for(light)
    return (
        theme.decoration("gutter_background"),
        theme.decoration("gutter_foreground"),
    )

#: One bookmark was added or removed (a gutter click, a double-click on the line
#: number, or Ctrl+F2). The set the user *chose* changed, so FQ-013's persistence
#: lane records it.
BOOKMARKS_TOGGLED = "toggled"

#: Every bookmark in the editor was dropped on purpose (Clear All Bookmarks).
#: Also a chosen set (the empty one), so it is recorded the same way.
BOOKMARKS_CLEARED = "cleared"

#: A new document was loaded (``setPlainText``) and the set was wiped as part of
#: the fold-state lifecycle. NOT a user choice, so it must never be written back
#: over a stored set -- it is the moment to RESTORE one, and the moment FQ-014's
#: Audit rows go stale.
BOOKMARKS_RESET = "reset"

#: Registered bookmark observers. Bound methods are stored as ``WeakMethod``, so
#: an observer's owner (a window, a controller) is never kept alive by this list.
_bookmark_observers: list = []


def add_bookmark_observer(callback: Callable[[object, str], None]) -> None:
    """Subscribe `callback` to every editor's bookmark changes; it is called as
    ``callback(editor, reason)`` (see the module docstring).

    Idempotent per callback: registering the same bound method twice registers
    it once, so a host that re-runs its wiring does not double-notify."""
    entry = weakref.WeakMethod(callback) if hasattr(callback, "__self__") else callback
    for existing in _bookmark_observers:
        if _resolve_observer(existing) == callback:
            return
    _bookmark_observers.append(entry)


def remove_bookmark_observer(callback: Callable[[object, str], None]) -> None:
    """Unsubscribe `callback`; a no-op if it is not registered."""
    for existing in list(_bookmark_observers):
        if _resolve_observer(existing) in (callback, None):
            _bookmark_observers.remove(existing)


def _resolve_observer(entry):
    """The live callable behind a registry entry, or None once it has died."""
    return entry() if isinstance(entry, weakref.WeakMethod) else entry


def _notify_bookmark_observers(editor, reason: str) -> None:
    """Publish `(editor, reason)` to every live observer.

    A dead observer (its owner garbage-collected, or its C++ object destroyed --
    the usual case being a window from an earlier session that was never closed)
    is dropped instead of raised through: this runs inside a gutter click and a
    click may not fail. Any other exception propagates, because that is a real
    bug in an observer and hiding it would make persistence fail silently."""
    for entry in list(_bookmark_observers):
        callback = _resolve_observer(entry)
        if callback is None:
            if entry in _bookmark_observers:
                _bookmark_observers.remove(entry)
            continue
        try:
            callback(editor, reason)
        except RuntimeError:
            if entry in _bookmark_observers:
                _bookmark_observers.remove(entry)


class _EditorGutter(QWidget):
    """Line-number and fold-marker gutter, the standard QPlainTextEdit
    side-widget pattern (Qt's "Code Editor Example")."""

    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor._gutter_width(), 0)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(event.rect(), self._editor._gutter_bg_color)

        block = self._editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self._editor.blockBoundingGeometry(block).translated(
            self._editor.contentOffset()
        ).top()
        bottom = top + self._editor.blockBoundingRect(block).height()

        # Three zones, left to right: the bookmark strip
        # [0, _BOOKMARK_STRIP_WIDTH), the fold zone
        # [_BOOKMARK_STRIP_WIDTH, _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH),
        # and the line-number area (right-aligned against the gutter's right
        # edge). The fold glyph and numbers both shift right by the strip width.
        number_x = _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH
        line_number_width = self.width() - number_x

        # FQ-031's optional body-relative column, left of the absolute one. With
        # no anchor set (`body_width == 0`) every number below is painted at
        # exactly the coordinates it was painted at before this existed.
        body_width = self._editor._body_number_column_width()
        if body_width:
            line_number_width -= body_width + _BODY_COLUMN_GAP
            separator_x = number_x + body_width + _BODY_COLUMN_GAP // 2
            painter.setPen(self._editor._body_number_color())
            painter.drawLine(
                separator_x, event.rect().top(), separator_x, event.rect().bottom()
            )

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number_text = str(block_number + 1)
                painter.setPen(self._editor._gutter_fg_color)
                painter.drawText(
                    number_x + (body_width + _BODY_COLUMN_GAP if body_width else 0),
                    int(top),
                    line_number_width,
                    self._editor.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number_text,
                )

                if body_width:
                    body_number = self._editor.body_relative_line(block_number)
                    # Header lines (above the anchor) get NO body-relative
                    # number at all -- blank, never a dash or a 0, so nothing
                    # in that column can be read as a line plpgsql could name.
                    if body_number is not None:
                        painter.setPen(self._editor._body_number_color())
                        painter.drawText(
                            number_x,
                            int(top),
                            body_width,
                            self._editor.fontMetrics().height(),
                            Qt.AlignmentFlag.AlignRight,
                            str(body_number),
                        )

                if block_number in self._editor._bookmarks:
                    self._draw_bookmark_tag(painter, int(top))

                if self._editor._foldable_region_starting_at(block) is not None:
                    collapsed = self._editor._fold_state.get(block_number, False)
                    self._draw_fold_glyph(painter, int(top), collapsed)

            block = block.next()
            top = bottom
            bottom = top + self._editor.blockBoundingRect(block).height()
            block_number += 1

    def _draw_bookmark_tag(self, painter: QPainter, top: int) -> None:
        """Draw a small filled rounded tag in the bookmark strip, vertically
        centered on the line, in the palette's Highlight accent (theme-aware,
        no border, antialiased)."""
        line_height = self._editor.fontMetrics().height()
        tag_w = _BOOKMARK_STRIP_WIDTH - 4
        tag_h = max(4, min(line_height - 6, _BOOKMARK_STRIP_WIDTH))
        x = 2
        y = top + (line_height - tag_h) // 2
        radius = max(1, tag_h // 4)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._editor._bookmark_color())
        painter.drawRoundedRect(QRect(x, y, tag_w, tag_h), radius, radius)
        painter.restore()

    def _draw_fold_glyph(self, painter: QPainter, top: int, collapsed: bool) -> None:
        line_height = self._editor.fontMetrics().height()
        glyph_size = min(_FOLD_GLYPH_WIDTH - 6, line_height - 6)
        half = max(2, glyph_size // 2)
        depth = max(1, half // 2)  # how far the chevron's tip protrudes
        cx = _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH // 2
        cy = top + line_height // 2
        # A fine, unfilled chevron (technical arrow) rather than a filled triangle.
        pen = QPen(self._editor._gutter_fg_color)
        pen.setWidthF(1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if collapsed:
            # Right-pointing chevron ">"
            painter.drawLine(cx - depth, cy - half, cx + depth, cy)
            painter.drawLine(cx + depth, cy, cx - depth, cy + half)
        else:
            # Down-pointing chevron "v"
            painter.drawLine(cx - half, cy - depth, cx, cy + depth)
            painter.drawLine(cx, cy + depth, cx + half, cy - depth)
        painter.restore()

    def _block_at_y(self, click_y: float) -> QTextBlock | None:
        """The visible block whose painted row contains ``click_y`` (gutter
        widget coordinates), or ``None`` past the last visible block. Walks the
        same first-visible-block/height chain the paint loop does, so it stays
        correct while the view is scrolled and while folds hide blocks."""
        block = self._editor.firstVisibleBlock()
        top = self._editor.blockBoundingGeometry(block).translated(
            self._editor.contentOffset()
        ).top()
        bottom = top + self._editor.blockBoundingRect(block).height()

        while block.isValid() and top <= click_y:
            if block.isVisible() and top <= click_y < bottom:
                return block
            block = block.next()
            top = bottom
            bottom = top + self._editor.blockBoundingRect(block).height()
        return None

    def mousePressEvent(self, event) -> None:
        click_x = event.position().x()
        # Zone routing: bookmark strip toggles the clicked line's bookmark;
        # fold zone keeps the existing fold toggle; a click in the line-number
        # area does nothing (as before).
        in_bookmark_strip = click_x < _BOOKMARK_STRIP_WIDTH
        in_fold_zone = (
            _BOOKMARK_STRIP_WIDTH
            <= click_x
            < _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH
        )
        if not (in_bookmark_strip or in_fold_zone):
            return
        block = self._block_at_y(event.position().y())
        if block is None:
            return
        if in_bookmark_strip:
            self._editor.toggle_bookmark(block.blockNumber())
        else:
            self._editor._toggle_fold(block)
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        """Second, larger click target for the bookmark toggle (spec §8/§27):
        a double-click in the **line-number zone** toggles that line's
        bookmark. Purely additive — the single click there is (and stays) a
        no-op, so Qt's press-before-double-click delivery cannot leave the user
        with two effects. In the bookmark strip and the fold zone the event is
        handed to ``QWidget`` unchanged, which re-dispatches it to
        ``mousePressEvent`` exactly as it does today."""
        if event.position().x() < _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH:
            super().mouseDoubleClickEvent(event)
            return
        block = self._block_at_y(event.position().y())
        if block is None:
            return
        self._editor.toggle_bookmark(block.blockNumber())
        self.update()


class GutterBookmarkFoldMixin:
    """Gutter + line bookmarks + code folding for any ``QPlainTextEdit``.

    Everything here is block-number based and therefore language-agnostic; the
    single language-specific hook is ``_foldable_region_starting_at``.
    """

    # --- Setup -------------------------------------------------------------
    def _init_gutter_bookmarks_folding(self) -> None:
        """Create the gutter, the fold/bookmark state and the signal wiring.
        Call from the host editor's ``__init__`` (after ``super().__init__``)."""
        self._gutter = _EditorGutter(self)
        self._fold_state: dict[int, bool] = {}
        # Session/file-scoped line bookmarks, tracked by block number. Reset
        # alongside _fold_state on every setPlainText (a new document loaded),
        # so bookmarks never drift from external edits or leak across documents.
        self._bookmarks: set[int] = set()
        # FQ-031: the 1-based ABSOLUTE buffer line whose body-relative number is
        # 1 (the `AS $$` opener), or None for "this buffer has no routine body".
        # None is the default and the only value any editor but a DDL object tab
        # ever holds, and it makes the whole feature inert.
        self._body_line_anchor: int | None = None
        # The gutter widget reads these two directly when painting; they
        # default to the DARK set and are swapped by _apply_gutter_theme_colors.
        _default_bg, _default_fg = _gutter_colors(False)
        self._gutter_bg_color = QColor(_default_bg)
        self._gutter_fg_color = QColor(_default_fg)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter_on_scroll)
        self._update_gutter_width(0)

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
        # Folding state is per-document-instance; a fresh setPlainText call
        # (a new document loaded into this editor) starts fully unfolded.
        self._fold_state = {}
        # Bookmarks share the fold-state lifecycle: a new document starts with
        # no bookmarks (session/file-scoped, see _init_gutter_bookmarks_folding).
        self._bookmarks = set()
        # The body anchor describes THIS text and nothing else: a new document
        # invalidates it, and a stale anchor would number every line wrong
        # rather than merely omit the column. The host re-sets it after loading
        # (see `set_body_line_anchor`); silence means off.
        if getattr(self, "_body_line_anchor", None) is not None:
            # Only when one was actually set: an editor that never uses the
            # feature must not even get the extra geometry call.
            self._body_line_anchor = None
            self._refresh_body_number_column()
        # Published AFTER the wipe, with the new document already in place, so an
        # observer that restores a stored set (FQ-013) sees the final blockCount
        # and one that sweeps stale rows (FQ-014) sees an empty set.
        _notify_bookmark_observers(self, BOOKMARKS_RESET)

    # --- Foldable-region provider (the ONE pluggable piece) ----------------
    def _foldable_region_starting_at(self, block):
        """Return ``(first_contained_block, last_contained_block)`` (0-based
        block numbers) for the foldable region starting on ``block``, or
        ``None``. Overridden per editor; the default folds nothing."""
        return None

    # --- Folding -----------------------------------------------------------
    def _toggle_fold(self, block) -> None:
        region = self._foldable_region_starting_at(block)
        if region is None:
            return
        first_contained, last_contained = region
        block_number = block.blockNumber()
        currently_collapsed = self._fold_state.get(block_number, False)
        new_visible = currently_collapsed  # if collapsed, expand; else collapse
        for line_number in range(first_contained, last_contained + 1):
            contained_block = self.document().findBlockByNumber(line_number)
            if new_visible and self._is_line_hidden_by_other_collapsed_fold(
                line_number, exclude_block_number=block_number
            ):
                # Expanding this region must not reveal lines that belong to
                # a separate, still-collapsed nested fold (e.g. re-expanding
                # an outer element after its inner child was independently
                # collapsed and never re-expanded).
                continue
            contained_block.setVisible(new_visible)
        self._fold_state[block_number] = not currently_collapsed
        self.document().markContentsDirty(block.position(), self.document().characterCount() - block.position())
        self.viewport().update()

    def _is_line_hidden_by_other_collapsed_fold(self, line_number: int, exclude_block_number: int) -> bool:
        for other_block_number, collapsed in self._fold_state.items():
            if other_block_number == exclude_block_number or not collapsed:
                continue
            other_block = self.document().findBlockByNumber(other_block_number)
            other_region = self._foldable_region_starting_at(other_block)
            if other_region is None:
                continue
            other_first, other_last = other_region
            if other_first <= line_number <= other_last:
                return True
        return False

    # --- Bookmarks ---------------------------------------------------------
    def toggle_bookmark(self, block_number: int) -> None:
        """Add or remove a bookmark on ``block_number`` (0-based line index)
        and repaint the gutter so the tag appears/disappears immediately."""
        if block_number in self._bookmarks:
            self._bookmarks.discard(block_number)
        else:
            self._bookmarks.add(block_number)
        self._gutter.update()
        _notify_bookmark_observers(self, BOOKMARKS_TOGGLED)

    def bookmarked_lines(self) -> list[int]:
        """Bookmarked block numbers in ascending order."""
        return sorted(self._bookmarks)

    def next_bookmark(self, from_line: int) -> int | None:
        """Smallest bookmark strictly greater than ``from_line``, wrapping to
        the smallest bookmark overall; ``None`` when there are no bookmarks."""
        ordered = self.bookmarked_lines()
        if not ordered:
            return None
        for line in ordered:
            if line > from_line:
                return line
        return ordered[0]

    def prev_bookmark(self, from_line: int) -> int | None:
        """Largest bookmark strictly less than ``from_line``, wrapping to the
        largest bookmark overall; ``None`` when there are no bookmarks."""
        ordered = self.bookmarked_lines()
        if not ordered:
            return None
        for line in reversed(ordered):
            if line < from_line:
                return line
        return ordered[-1]

    def clear_bookmarks(self) -> None:
        """Remove every bookmark and repaint the gutter."""
        self._bookmarks = set()
        self._gutter.update()
        _notify_bookmark_observers(self, BOOKMARKS_CLEARED)

    def restore_bookmarks(self, lines: Iterable[int]) -> None:
        """Replace this editor's bookmark set with `lines` (0-based block
        numbers), dropping any that fall outside the current document, and
        repaint the gutter.

        The counterpart to :data:`BOOKMARKS_RESET`: FQ-013's persistence lane
        calls this with what it loaded for the document just placed in this
        editor. Deliberately publishes **no** notification -- it is the *answer*
        to one, and re-publishing would either loop or make a restore look like a
        user edit worth writing back."""
        block_count = self.blockCount()
        self._bookmarks = {
            line
            for line in lines
            if isinstance(line, int)
            and not isinstance(line, bool)
            and 0 <= line < block_count
        }
        gutter = getattr(self, "_gutter", None)
        if gutter is not None:
            gutter.update()

    def toggle_bookmark_at_cursor(self) -> None:
        """Toggle a bookmark on the line the text cursor currently sits on."""
        self.toggle_bookmark(self.textCursor().blockNumber())

    def goto_next_bookmark(self) -> None:
        """Move the cursor to the next bookmark after the current line (with
        wrap-around) and center it. No-op when there are no bookmarks."""
        target = self.next_bookmark(self.textCursor().blockNumber())
        if target is not None:
            self._goto_bookmark_line(target)

    def goto_prev_bookmark(self) -> None:
        """Move the cursor to the previous bookmark before the current line
        (with wrap-around) and center it. No-op when there are no bookmarks."""
        target = self.prev_bookmark(self.textCursor().blockNumber())
        if target is not None:
            self._goto_bookmark_line(target)

    def _goto_bookmark_line(self, block_number: int) -> None:
        """Move the cursor to ``block_number`` (0-based) and center it. Guards
        against out-of-range bookmarks that may point past EOF after edits."""
        block = self.document().findBlockByNumber(block_number)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()

    # --- Body-relative line numbers (FQ-031) --------------------------------
    def set_body_line_anchor(self, anchor: int | None) -> None:
        """Turn the body-relative gutter column on (or off, with ``None``).

        `anchor` is the **1-based ABSOLUTE buffer line of the routine body's
        opening dollar-quote** — i.e. exactly what
        `db/ddl_check.py::body_line_offset(buffer_text)` returns, `None`
        included. It is deliberately a *position*, not a header line *count*:
        `body_line_offset` already answers this question in this unit, and
        `map_lineno` maps a plpgsql line onto the buffer as `L + lineno - 1`
        (§18.5 D3: "prosrc line 1 **is** line L"). Passing the offset straight
        through means the call site does no arithmetic at all, and the one
        rule that could be got wrong lives here rather than at every caller:
        an anchor of `L` makes absolute line `L` read body-relative **1**,
        which is precisely the number plpgsql would print.

        `None` (the default, and the value after every `setPlainText`) restores
        the plain single-column gutter exactly — no second column, no separator
        and not one pixel of extra width. An anchor below 1 is treated as
        `None`: a body cannot start before the buffer does, and refusing is
        better than renumbering from a nonsense origin.
        """
        usable = (
            isinstance(anchor, int)
            and not isinstance(anchor, bool)
            and anchor >= 1
        )
        normalized = anchor if usable else None
        if normalized == self._body_line_anchor:
            return
        self._body_line_anchor = normalized
        self._refresh_body_number_column()

    def set_body_line_anchor_from_text(self, buffer_text: str) -> None:
        """`set_body_line_anchor(body_line_offset(buffer_text))` — the whole
        seam in one call, so a host never has to hold the offset convention in
        its head. A buffer with no locatable dollar-quote opener (a `LANGUAGE
        sql` function, a table, a plain SQL buffer) yields `None` and the
        column simply does not appear; nothing is ever guessed (§18.5 D3).

        `db/ddl_check.py` is imported lazily: this widget-level module is
        imported by every editor in the app and must not drag the `db` package
        in for editors that will never call this."""
        from pgtp_editor.db.ddl_check import body_line_offset

        self.set_body_line_anchor(body_line_offset(buffer_text or ""))

    def body_line_anchor(self) -> int | None:
        """The current anchor (see `set_body_line_anchor`), or None when the
        body-relative column is off."""
        return getattr(self, "_body_line_anchor", None)

    def body_relative_line(self, block_number: int) -> int | None:
        """The body-relative (plpgsql-style) 1-based line number for the 0-based
        `block_number`, or None when there is no anchor or the line sits in the
        header ABOVE it. Header lines have no honest body-relative number, so
        they get none — the column is blank there."""
        anchor = getattr(self, "_body_line_anchor", None)
        if anchor is None:
            return None
        relative = (block_number + 1) - anchor + 1
        return relative if relative >= 1 else None

    def _body_number_column_width(self) -> int:
        """Pixel width of the body-relative column, or **0** when it is off
        (which is what keeps `_gutter_width` unchanged for every other editor).
        Sized from the largest body-relative number the document can show."""
        anchor = getattr(self, "_body_line_anchor", None)
        if anchor is None:
            return 0
        largest = max(1, self.blockCount() - anchor + 1)
        return len(str(largest)) * self.fontMetrics().horizontalAdvance("9")

    def _body_number_color(self) -> QColor:
        """The dimmed foreground for the secondary column and its separator:
        the gutter foreground blended toward the gutter background, so it reads
        as subordinate in both themes without a second hard-coded palette."""
        foreground = self._gutter_fg_color
        background = self._gutter_bg_color
        blend = lambda a, b: int(round(a + (b - a) * _BODY_NUMBER_DIM))  # noqa: E731
        return QColor(
            blend(foreground.red(), background.red()),
            blend(foreground.green(), background.green()),
            blend(foreground.blue(), background.blue()),
        )

    def _refresh_body_number_column(self) -> None:
        """Re-apply the gutter geometry and repaint after the anchor changed."""
        self._update_gutter_width(0)
        gutter = getattr(self, "_gutter", None)
        if gutter is None:
            return
        # The gutter widget's own geometry is otherwise only set on resize, so
        # an anchor set after the editor is laid out would leave it at the old
        # width and clip (or leave a gap beside) the new column.
        contents_rect = self.contentsRect()
        gutter.setGeometry(
            QRect(
                contents_rect.left(),
                contents_rect.top(),
                self._gutter_width(),
                contents_rect.height(),
            )
        )
        gutter.update()

    # --- Colors / geometry -------------------------------------------------
    def _bookmark_color(self) -> QColor:
        """The bookmark tag's fill, derived from the palette's Highlight role
        so it reads in both Light and Dark themes. Recomputed on each paint,
        so it tracks palette changes with no cache to invalidate."""
        return self.palette().color(QPalette.ColorRole.Highlight)

    def _apply_gutter_theme_colors(self, light: bool) -> None:
        """Swap the gutter's background/foreground between the LIGHT and DARK
        sets and repaint. Hosts call this from their own theme handling."""
        background, foreground = _gutter_colors(light)
        self._gutter_bg_color = QColor(background)
        self._gutter_fg_color = QColor(foreground)
        self._gutter.update()

    def _gutter_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        digit_width = self.fontMetrics().horizontalAdvance("9")
        body_width = self._body_number_column_width()
        return (
            digits * digit_width
            + _BOOKMARK_STRIP_WIDTH
            + _FOLD_GLYPH_WIDTH
            + 6
            # 0 unless a body anchor is set (FQ-031), so every editor without a
            # routine body keeps the exact width it had before.
            + (body_width + _BODY_COLUMN_GAP if body_width else 0)
        )

    def _update_gutter_width(self, _new_block_count: int) -> None:
        self.setViewportMargins(self._gutter_width(), 0, 0, 0)

    def _update_gutter_on_scroll(self, rect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        contents_rect = self.contentsRect()
        self._gutter.setGeometry(
            QRect(contents_rect.left(), contents_rect.top(), self._gutter_width(), contents_rect.height())
        )
