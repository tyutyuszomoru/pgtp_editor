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

# pgtp_editor/ui/activity_panel.py
"""ActivityPanel: the "Activity Log" dock's widget (FQ-019).

The thin half of the feature. All of the logic -- the entry shape, the source
taxonomy, the JSONL store, the previews and the dynamic timestamp format --
lives in the Qt-free `db/activity_log.py`; this panel only maps its rendered
rows onto a `QListWidget` and routes a click to a read-only viewer.

**It owns no log.** `set_entries(...)` / `append(...)` take plain
`ActivityEntry` data; the panel never constructs an `ActivityLog`, reads a
file, or asks whether a project is open. The dock registration, the debounce
timer, the project transitions and the ~8 `record(...)` emit points are the
host's, so this widget is constructible in a test with two hand-built entries.

**One fixed timestamp format, `YYYY-MM-DD HH:MM`, on every row** (owner
decision, superseding both the FQ-019 queue entry's dynamic `HH:MM`-when-
same-day rule and the core's `timestamp_format(entries)`). A row's rendered
text therefore depends on that row alone: the panel never consults the set, and
`append` adds one item without touching the rows already on screen. The format
is taken from the core's `TIME_FORMAT` constant, never from a `strftime` call
written here, so the core stays the one place it is spelled.

**A separate dock, not an Audit prefix.** The Audit panel is a findings surface
governed by §7's closed prefix reservation; this is an operations journal with
timestamps, provenance and success/error status. They sit side by side.

**Click routing, and how a row with two payloads disambiguates.** The row shows
only 20-character previews; the full DDL and the full error are retained by the
core precisely so a click can open them. A row can carry both, so:

* a plain click opens the row's *primary* payload -- the error when the action
  failed (that is why the reader clicked), the DDL otherwise;
* the context menu lists whichever of the two the row actually has, by name, so
  a failed DDL row still reaches its statement.

Both routes go through `open_viewer(...)`, which reuses
`ui/code_editor.py::CodeEditorDialog` -- the app's existing syntax-highlighted
editor -- with its internal editor set read-only and shown NON-modally with
`.show()`. No third highlighter is written, and no `.exec()` is on any path a
test reaches (§30).
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.activity_log import (
    TIME_FORMAT,
    ActivityEntry,
    render_row,
)

from .code_editor import CodeEditorDialog

#: The one timestamp format every row uses, always (owner decision: the dynamic
#: same-day/multi-day switch is dropped). Aliased here so the panel and its
#: tests name one thing, and re-pointed in one line if the core renames it.
ROW_TIME_FORMAT = TIME_FORMAT

#: The failed-row foreground, the same red the Coherence panel uses for "this
#: row is the problem" so failure looks the same wherever the user meets it.
_FAILED_COLOR = QColor("#d02020")

#: `Qt.UserRole` payload: the entry's index in `entries`. The index is stable
#: (the log is append-only and rows are in file order, oldest first), and
#: carrying it rather than the entry keeps the widget's data and the panel's
#: data one object.
ENTRY_ROLE = Qt.ItemDataRole.UserRole

#: What `open_viewer` was asked for, and what `viewer_actions` returns.
VIEW_DDL = "ddl"
VIEW_ERROR = "error"

#: Context-menu labels for the two payloads.
VIEWER_LABELS = {VIEW_DDL: "View full DDL…", VIEW_ERROR: "View full error…"}

#: The `CodeEditor` language each viewer uses. The DDL is always SQL; an error
#: is highlighted as SQL when it came from a database action (it quotes the
#: statement) and left unhighlighted for a file/IO error, where SQL keyword
#: colouring would be noise. An unknown language simply installs no rules.
VIEWER_LANGUAGE_SQL = "sql"
VIEWER_LANGUAGE_TEXT = "text"

EMPTY_TEXT = "No activity recorded yet."


class ActivityPanel(QWidget):
    """The Activity Log dock's contents: one row per journalled action.

    Host surface (all the wiring pass needs):
    `set_entries(entries)`, `append(entry)`, `clear()`, and the read-only
    `entries` / `row_texts()` accessors.
    """

    #: (dialog) -- emitted after a click opened a full-text viewer. The host may
    #: ignore it; it exists so a test can observe the routing without reaching
    #: into the widget.
    viewer_opened = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: tuple[ActivityEntry, ...] = ()
        # Non-modal viewers are kept alive here: a QDialog with no parent
        # reference goes out of scope and closes itself the instant the slot
        # returns.
        self._viewers: list[CodeEditorDialog] = []

        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        self.list.itemClicked.connect(self._on_item_clicked)

        self.empty_label = QLabel(EMPTY_TEXT)
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setMargin(12)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.empty_label, 1)

        self._rebuild()

    # -- population ----------------------------------------------------------

    @property
    def entries(self) -> tuple[ActivityEntry, ...]:
        """The displayed set, oldest first."""
        return self._entries

    def set_entries(self, entries: Iterable[ActivityEntry]) -> None:
        """Show exactly `entries`, oldest first -- project open, project close
        (with `()`), and any full refresh. Re-renders every row."""
        self._entries = tuple(entries)
        self._rebuild()

    def append(self, entry: ActivityEntry) -> None:
        """Add one newly recorded entry at the end.

        A pure append: with one fixed timestamp format, a new entry cannot
        change how an existing row reads, so the rows already on screen are left
        alone.
        """
        index = len(self._entries)
        self._entries = self._entries + (entry,)
        self.list.addItem(self._make_item(index, entry))
        self._update_empty_state()

    def clear(self) -> None:
        """Back to the empty state (project close / standalone reset)."""
        self.set_entries(())

    def row_texts(self) -> list[str]:
        """Every visible row's text, in order -- what a copy of the panel would
        yield, and the shape tests assert."""
        return [self.list.item(row).text() for row in range(self.list.count())]

    def _rebuild(self) -> None:
        self.list.clear()
        for index, entry in enumerate(self._entries):
            self.list.addItem(self._make_item(index, entry))
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        has_rows = bool(self._entries)
        self.list.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)

    def _make_item(self, index: int, entry: ActivityEntry) -> QListWidgetItem:
        item = QListWidgetItem(render_row(entry, ROW_TIME_FORMAT))
        item.setData(ENTRY_ROLE, index)
        if entry.failed:
            item.setForeground(QBrush(_FAILED_COLOR))
        if entry.session_only:
            # A standalone entry dies with the session and is never written;
            # italics say "this one is not in the project's file" without
            # spending a column on it.
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
        item.setToolTip(self._tooltip_for(entry))
        return item

    @staticmethod
    def _tooltip_for(entry: ActivityEntry) -> str:
        hints = [VIEWER_LABELS[kind] for kind in _payload_kinds(entry)]
        if not hints:
            return ""
        return "Click to open the full text — " + ", ".join(hints)

    # -- click routing -------------------------------------------------------

    def entry_at(self, item: QListWidgetItem | None) -> ActivityEntry | None:
        """The entry behind a row, or None."""
        if item is None:
            return None
        index = item.data(ENTRY_ROLE)
        if not isinstance(index, int) or not 0 <= index < len(self._entries):
            return None
        return self._entries[index]

    @staticmethod
    def viewer_actions(entry: ActivityEntry | None) -> list[tuple[str, str]]:
        """The (kind, label) viewers this row offers -- `[]` for a row carrying
        neither a DDL nor an error. Pure, so the context menu is assertable
        without a popup."""
        if entry is None:
            return []
        return [(kind, VIEWER_LABELS[kind]) for kind in _payload_kinds(entry)]

    @staticmethod
    def primary_viewer(entry: ActivityEntry | None) -> str | None:
        """What a plain click on this row opens: the error when the action
        failed, otherwise the DDL, and nothing when the row has neither."""
        kinds = _payload_kinds(entry) if entry is not None else ()
        if not kinds:
            return None
        if entry.failed and VIEW_ERROR in kinds:
            return VIEW_ERROR
        return kinds[0]

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        entry = self.entry_at(item)
        kind = self.primary_viewer(entry)
        if kind is None:
            return  # a file row with no payload is inert, by design
        self.open_viewer(entry, kind)

    def open_viewer(self, entry: ActivityEntry, kind: str) -> CodeEditorDialog | None:
        """Show the row's UNTRUNCATED text in a read-only, syntax-highlighted
        viewer and return it (None when the row has no such payload).

        Reuses `CodeEditorDialog` rather than writing a third highlighter; its
        `saved`/`cancelled` signals fire harmlessly in read-only use. Shown with
        `.show()`, never `.exec()`.
        """
        text = _payload_text(entry, kind)
        if not text:
            return None
        dialog = CodeEditorDialog(
            _viewer_language(entry, kind),
            title=_viewer_title(entry, kind),
            parent=self,
        )
        dialog.set_code(text)
        dialog._editor.setReadOnly(True)
        self._viewers.append(dialog)
        dialog.finished.connect(lambda _result, d=dialog: self._forget_viewer(d))
        dialog.show()
        self.viewer_opened.emit(dialog)
        return dialog

    def _forget_viewer(self, dialog: CodeEditorDialog) -> None:
        if dialog in self._viewers:
            self._viewers.remove(dialog)

    def _on_context_menu(self, pos) -> None:  # pragma: no cover - GUI popup
        item = self.list.itemAt(pos)
        entry = self.entry_at(item)
        actions = self.viewer_actions(entry)
        if not actions:
            return
        menu = QMenu(self.list)
        for kind, label in actions:
            action = menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, k=kind: self.open_viewer(entry, k)
            )
        menu.exec(self.list.viewport().mapToGlobal(pos))


# -- pure helpers -------------------------------------------------------------


def _payload_kinds(entry: ActivityEntry) -> tuple[str, ...]:
    """Which full-text payloads this entry actually has, DDL first."""
    kinds: list[str] = []
    if entry.ddl_full:
        kinds.append(VIEW_DDL)
    if entry.error_full:
        kinds.append(VIEW_ERROR)
    return tuple(kinds)


def _payload_text(entry: ActivityEntry, kind: str) -> str | None:
    return entry.error_full if kind == VIEW_ERROR else entry.ddl_full


def _viewer_language(entry: ActivityEntry, kind: str) -> str:
    """SQL for a DDL, and for an error raised by a database action; plain text
    for a file/IO error, where SQL colouring would only add noise."""
    if kind == VIEW_DDL:
        return VIEWER_LANGUAGE_SQL
    return VIEWER_LANGUAGE_SQL if entry.verb else VIEWER_LANGUAGE_TEXT


def _viewer_title(entry: ActivityEntry, kind: str) -> str:
    what = "Error" if kind == VIEW_ERROR else "DDL"
    action = entry.verb or entry.file_verb or ""
    parts = [part for part in (entry.source, action) if part]
    return f"{what} — {' '.join(parts)}" if parts else what


def rendered_rows_for(entries: Sequence[ActivityEntry]) -> list[str]:
    """The rows `set_entries(entries)` would show, without building a widget."""
    return [render_row(entry, ROW_TIME_FORMAT) for entry in entries]
