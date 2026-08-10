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

# pgtp_editor/ui/edit_snippets_dialog.py
"""The "Edit Snippets…" dialog (FQ-030) — `Settings` menu, Maintenance mode only.

**A plain table of trigger word ↔ body. Explicitly not a builder.** FQ-030
rejected a drag-and-drop snippet composer in as many words; the body is a
`QPlainTextEdit` and the template syntax is documented in the manual, not
assembled by widgets.

Shape, and why (the house style `customize_shortcuts_dialog.py` set):

- **The set is INJECTED and handed back.** The dialog neither reads nor writes
  the store — `ui/snippet_controller.py` does both. Everything here is testable
  with a list of `Snippet`s and no window.
- **Shown non-modally** (`show()`, never `.exec()`), the caller reading
  `result_snippets()` after `accepted` fires.
- **Every mutation has a programmatic seam** — `add_snippet`, `remove_row`,
  `set_body`, `set_snippets`, `restore_missing_defaults` — so tests drive it
  without simulating typing.
- **Export/Import are SIGNALS, not actions taken here.** They need file dialogs
  and, for import, the collision question; both belong to the controller, which
  owns every modal in this lane. The dialog only says the user asked.

Why the two halves (table above, body below) rather than a body column: a
snippet body is multi-line by nature — the shipped set's shortest is three
lines — and a table cell that holds `IF … THEN\\n … \\nEND IF;` on one squashed
row is unreadable and un-editable. The table answers "which snippets do I
have"; the pane answers "what does this one insert".

The **Origin** column exists because the store holds the WHOLE set (see
`sql/snippet_store.py`): once a user's file is written, nothing else
distinguishes a snippet we shipped from one they wrote, and "which of these are
mine?" is the first question anyone opening this dialog has.
"""
from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pgtp_editor.sql.snippet_store import (
    ORIGIN_DEFAULT,
    ORIGIN_MODIFIED_DEFAULT,
    defaults_missing_from,
    origin_of,
)
from pgtp_editor.sql.templates import DEFAULT_SNIPPETS, Snippet

#: Column indices of the one table.
COLUMN_PREFIX = 0
COLUMN_TITLE = 1
COLUMN_ORIGIN = 2

#: What the Origin column says, by `origin_of` answer. Worded from the user's
#: side ("yours"), not the code's ("user").
ORIGIN_LABELS = {
    ORIGIN_DEFAULT: "built-in",
    ORIGIN_MODIFIED_DEFAULT: "built-in, edited",
}
_ORIGIN_USER_LABEL = "yours"

_NEW_PREFIX = "newsnippet"
_NEW_TITLE = "(describe this snippet)"


class EditSnippetsDialog(QDialog):
    """`snippets` are the rows to edit; `read_only` disables every mutation.

    `read_only` is how a store that FAILED to load is shown: the user sees the
    defaults that are actually in force and the reason their file was not used,
    but cannot press OK — saving would overwrite a file that is probably one
    typo away from being fine (`sql/snippet_store.py` states that contract).
    """

    #: The user asked to write the current rows to a file of their choosing.
    export_requested = Signal()
    #: The user asked to read a file into the current rows.
    import_requested = Signal()

    def __init__(
        self,
        snippets: Sequence[Snippet] = DEFAULT_SNIPPETS,
        parent=None,
        *,
        read_only: bool = False,
        note: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Snippets")
        self.resize(760, 560)

        self._snippets: list[Snippet] = list(snippets)
        self._read_only = bool(read_only)
        #: Suppresses the cell/body change handlers while the widgets are being
        #: repopulated from `_snippets`, so redrawing is never mistaken for
        #: editing.
        self._loading = False

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Type a trigger word in a SQL editor and press Ctrl+Alt+E to insert "
            "its body. Use {{1}}, {{2}}… for the spots Tab jumps between, and "
            "{{0}} for where the caret ends up."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._note_label = QLabel(note)
        self._note_label.setWordWrap(True)
        self._note_label.setVisible(bool(note))
        layout.addWidget(self._note_label)

        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["Trigger word", "Description", "Origin"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COLUMN_TITLE, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        layout.addWidget(QLabel("Body of the selected snippet:"))
        self.body = QPlainTextEdit(self)
        self.body.setEnabled(False)
        layout.addWidget(self.body, 1)

        buttons_row = QHBoxLayout()
        self.add_button = QPushButton("Add", self)
        self.delete_button = QPushButton("Delete", self)
        self.restore_button = QPushButton("Restore Built-ins", self)
        self.export_button = QPushButton("Export…", self)
        self.import_button = QPushButton("Import…", self)
        for button in (
            self.add_button,
            self.delete_button,
            self.restore_button,
            self.export_button,
            self.import_button,
        ):
            buttons_row.addWidget(button)
        buttons_row.addStretch(1)
        layout.addLayout(buttons_row)

        self._message = QLabel("")
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.add_button.clicked.connect(self.add_snippet)
        self.delete_button.clicked.connect(self.remove_selected)
        self.restore_button.clicked.connect(self.restore_missing_defaults)
        self.export_button.clicked.connect(self.export_requested.emit)
        self.import_button.clicked.connect(self.import_requested.emit)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.currentCellChanged.connect(self._on_row_changed)
        self.body.textChanged.connect(self._on_body_changed)

        self._reload_table()
        if self._read_only:
            self._apply_read_only()

    # -- read-only surface ---------------------------------------------------

    def result_snippets(self) -> tuple[Snippet, ...]:
        """The rows as they now stand — what the caller persists on `accepted`."""
        return tuple(self._snippets)

    def message(self) -> str:
        """Whatever the dialog last said inline (a refusal, an import summary)."""
        return self._message.text()

    def note(self) -> str:
        """The standing note under the intro (why the store is read-only, …)."""
        return self._note_label.text()

    def validation_error(self) -> str | None:
        """Why these rows cannot be saved, or None.

        Only two things make a set unusable, and both are about the trigger
        word, because that is the only field the expansion gesture looks up: a
        blank one can never be typed, and a duplicate makes which body you get
        depend on row order. Bodies are never validated — an unfinished
        template is a legitimate thing to save and come back to.
        """
        seen: set[str] = set()
        for snippet in self._snippets:
            key = snippet.prefix.strip().lower()
            if not key:
                return "Every snippet needs a trigger word."
            if key in seen:
                return f"The trigger word '{snippet.prefix}' is used twice."
            seen.add(key)
        return None

    # -- mutation seams ------------------------------------------------------

    def set_snippets(self, snippets: Sequence[Snippet]) -> None:
        """Replace every row (what the controller calls after an import)."""
        self._snippets = list(snippets)
        self._reload_table()

    def add_snippet(
        self, prefix: str = _NEW_PREFIX, title: str = _NEW_TITLE, template: str = ""
    ) -> int:
        """Append a row and select it. Returns its index.

        The default trigger word is deliberately a real, typeable word rather
        than an empty cell: an empty one fails `validation_error` and the user
        would meet a refusal before they had done anything wrong.
        """
        if self._read_only:
            return -1
        prefix = self._unique_prefix(prefix)
        self._snippets.append(Snippet(prefix, title, template))
        self._reload_table()
        row = len(self._snippets) - 1
        self.table.setCurrentCell(row, COLUMN_PREFIX)
        return row

    def remove_row(self, row: int) -> bool:
        """Delete row `row`. Built-in rows are deletable — the store holds the
        whole set, so a deleted built-in stays gone until `Restore Built-ins`
        puts it back, which is the point of having that button."""
        if self._read_only or not 0 <= row < len(self._snippets):
            return False
        del self._snippets[row]
        self._reload_table()
        return True

    def remove_selected(self) -> bool:
        return self.remove_row(self.table.currentRow())

    def set_body(self, text: str, row: int | None = None) -> bool:
        """Set the body of `row` (the selected row by default)."""
        row = self.table.currentRow() if row is None else row
        if self._read_only or not 0 <= row < len(self._snippets):
            return False
        current = self._snippets[row]
        self._snippets[row] = Snippet(current.prefix, current.title, text)
        if row == self.table.currentRow() and self.body.toPlainText() != text:
            self._loading = True
            try:
                self.body.setPlainText(text)
            finally:
                self._loading = False
        self._refresh_origin(row)
        return True

    def restore_missing_defaults(self) -> tuple[Snippet, ...]:
        """Append every shipped snippet the set no longer has. Returns them.

        Never touches an existing row: a built-in the user has *edited* is
        their snippet now, and re-adding our version would be exactly the
        silent overwrite the import rule forbids.
        """
        if self._read_only:
            return ()
        missing = defaults_missing_from(self._snippets)
        if not missing:
            self._message.setText("Every built-in snippet is already here.")
            return ()
        self._snippets.extend(missing)
        self._reload_table()
        self._message.setText(
            f"Restored {len(missing)} built-in snippet(s): "
            + ", ".join(s.prefix for s in missing)
        )
        return missing

    def show_message(self, text: str) -> None:
        """Say something inline (the controller reports import results here)."""
        self._message.setText(text)

    # -- internals -----------------------------------------------------------

    def _unique_prefix(self, wanted: str) -> str:
        taken = {s.prefix.strip().lower() for s in self._snippets}
        if wanted.strip().lower() not in taken:
            return wanted
        index = 2
        while f"{wanted}{index}".lower() in taken:
            index += 1
        return f"{wanted}{index}"

    def _reload_table(self) -> None:
        selected = self.table.currentRow()
        self._loading = True
        try:
            self.table.setRowCount(len(self._snippets))
            for row, snippet in enumerate(self._snippets):
                self._set_cell(row, COLUMN_PREFIX, snippet.prefix, editable=True)
                self._set_cell(row, COLUMN_TITLE, snippet.title, editable=True)
                self._set_cell(
                    row,
                    COLUMN_ORIGIN,
                    ORIGIN_LABELS.get(origin_of(snippet), _ORIGIN_USER_LABEL),
                    editable=False,
                )
        finally:
            self._loading = False
        if self._snippets:
            row = min(max(selected, 0), len(self._snippets) - 1)
            self.table.setCurrentCell(row, COLUMN_PREFIX)
            self._show_body(row)
        else:
            self._show_body(-1)

    def _set_cell(self, row: int, column: int, text: str, *, editable: bool) -> None:
        item = self.table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, column, item)
        item.setText(text)
        flags = item.flags()
        if editable and not self._read_only:
            flags |= Qt.ItemFlag.ItemIsEditable
        else:
            flags &= ~Qt.ItemFlag.ItemIsEditable
        item.setFlags(flags)

    def _show_body(self, row: int) -> None:
        self._loading = True
        try:
            if 0 <= row < len(self._snippets):
                self.body.setPlainText(self._snippets[row].template)
                self.body.setEnabled(not self._read_only)
            else:
                self.body.setPlainText("")
                self.body.setEnabled(False)
        finally:
            self._loading = False

    def _on_row_changed(self, row, _column, _prev_row, _prev_column) -> None:
        if not self._loading:
            self._show_body(row)

    def _on_item_changed(self, item) -> None:
        if self._loading:
            return
        row = item.row()
        if not 0 <= row < len(self._snippets):
            return
        current = self._snippets[row]
        if item.column() == COLUMN_PREFIX:
            self._snippets[row] = Snippet(
                item.text().strip(), current.title, current.template
            )
        elif item.column() == COLUMN_TITLE:
            self._snippets[row] = Snippet(
                current.prefix, item.text(), current.template
            )
        else:
            return
        self._refresh_origin(row)

    def _on_body_changed(self) -> None:
        if self._loading:
            return
        row = self.table.currentRow()
        if not 0 <= row < len(self._snippets):
            return
        current = self._snippets[row]
        self._snippets[row] = Snippet(
            current.prefix, current.title, self.body.toPlainText()
        )
        self._refresh_origin(row)

    def _refresh_origin(self, row: int) -> None:
        """Re-derive the Origin cell. It is a FUNCTION of the row's content, so
        every edit has to redraw it: retyping a built-in's body makes it
        "built-in, edited" the moment it stops matching ours."""
        if not 0 <= row < len(self._snippets):
            return
        self._loading = True
        try:
            self._set_cell(
                row,
                COLUMN_ORIGIN,
                ORIGIN_LABELS.get(origin_of(self._snippets[row]), _ORIGIN_USER_LABEL),
                editable=False,
            )
        finally:
            self._loading = False

    def _on_accept(self) -> None:
        """OK: refuse INLINE rather than through a message box, so the row the
        complaint is about stays visible next to the complaint."""
        error = self.validation_error()
        if error:
            self._message.setText(error)
            return
        self.accept()

    def _apply_read_only(self) -> None:
        for button in (
            self.add_button,
            self.delete_button,
            self.restore_button,
            self.import_button,
        ):
            button.setEnabled(False)
        self.body.setReadOnly(True)
        ok = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setEnabled(False)
