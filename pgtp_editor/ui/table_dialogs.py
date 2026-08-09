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

# pgtp_editor/ui/table_dialogs.py
"""The index, comment and whole-table dialogs (FQ-025 slice 3, §18.1/§18.5).

Five dialogs for the slice's six menu items:

- `CreateIndexDialog` — index name, one or more columns, a UNIQUE toggle and an
  access-method dropdown.
- `DropIndexDialog` — the table's **droppable** indexes, and a line saying so
  when it hid one (see below — this is the slice's one non-obvious rule).
- `SetCommentDialog` — Set table comment *and* Set column comment, one class in
  two modes.
- `CreateTableDialog` — the multi-column builder; the only dialog here that is
  not about an existing table.
- `DropTableDialog` — table only, and **no confirmation**: FQ-025's ruling is
  that the generated tab is the safeguard, because generating `DROP TABLE t`
  executes nothing.

Everything shared with slices 1 and 2 is inherited, not re-implemented: these
subclass `alter_column_dialogs._AlterColumnDialogBase` (table dropdown,
read-only "From:" line, red inline error label, OK-disabled-until-valid, and
*validity is whatever the emitter says*), and the multi-column pickers are
slice 2's `constraint_dialogs._ColumnListPicker`. The FQ-002 rules therefore
hold here too: shown non-modally with `show()` and never `.exec()`; every list
is injected as plain data by the caller, so nothing here imports
`db/introspect`, opens a connection or queries anything; the click context is
pre-selected but changeable; and the message in the red label is the emitter's
own.

**Why `Drop index` hides rows and then says that it did.** Postgres creates an
implicit index for every PRIMARY KEY / UNIQUE / EXCLUDE constraint and then
*refuses* `DROP INDEX` on it — the constraint has to go instead. Listing those
would offer a statement that cannot succeed; silently omitting them would
create a "where did my unique index go?" mystery, since the user can see the
index in the Explorer. So they are filtered out **and named** in a plain note
that points at `Drop constraint…`, which is `introspect.IndexInfo`'s stated
rule for this picker.

**Free SQL text is user-typed only.** A `CREATE TABLE` column default is
arbitrary SQL (see `db/ddl_skeleton.ColumnSpec`), so those fields are built by
slice 1's `_user_typed_line_edit` and are never seeded, completed or injected.
A **comment** is deliberately *not* in that category: it is a SQL string
literal, escaped rather than allowlisted, so `SetCommentDialog` may be handed
the existing comment to edit — which is the difference between "change this
description" and "retype it from memory".
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.ddl_skeleton import (
    INDEX_METHODS,
    ColumnSpec,
    SkeletonError,
    create_index_skeleton,
    create_table_skeleton,
    drop_index_skeleton,
    drop_table_skeleton,
    set_column_comment_skeleton,
    set_table_comment_skeleton,
)
from pgtp_editor.ui.alter_column_dialogs import (
    COMMON_COLUMN_TYPES,
    ColumnSource,
    TableSource,
    _AlterColumnDialogBase,
    _user_typed_line_edit,
)
from pgtp_editor.ui.constraint_dialogs import _ColumnListPicker

#: The existing indexes to offer, in the same three shapes `ColumnSource` and
#: `ConstraintSource` accept — a `{table: [...]}` mapping, a `table -> [...]`
#: callable, or a bare sequence meaning "the indexes of the pre-bound table".
#: Each element is a plain name or anything carrying `.name` / `.columns` /
#: `.is_unique` / `.method` / `.constraint_name` / `.qualified_name`
#: (`db.introspect.IndexInfo` is exactly that shape, but this module never
#: imports it — the caller passes data, not a schema).
IndexSource = Mapping[str, Sequence[Any]] | Callable[[str], Sequence[Any]] | Sequence[Any]

#: `SetCommentDialog` modes. The menu item the user picked chooses one; it is
#: not a field inside the dialog, exactly as `ColumnActionDialog`'s operation
#: is not.
OP_TABLE_COMMENT = "table_comment"
OP_COLUMN_COMMENT = "column_comment"

_COMMENT_TITLES = {
    OP_TABLE_COMMENT: "Set Table Comment",
    OP_COLUMN_COMMENT: "Set Column Comment",
}

COMMENT_TARGETS = tuple(_COMMENT_TITLES)

_NO_INDEXES_MESSAGE = (
    "This table has no droppable indexes — pick another table, or reload the"
    " schema."
)

_BLANK_COMMENT_NOTE = (
    "Leaving this empty emits IS NULL, which removes the comment."
)


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Index:
    """One row of the index picker, normalised from injected data.

    A local shape rather than `db.introspect.IndexInfo` for slice 1's
    injected-data reason: the dialogs stay ignorant of the schema model, so a
    caller may hand over `IndexInfo`s, bare names, or anything else with a
    `.name`.
    """

    name: str
    qualified_name: str = ""
    columns: tuple[str, ...] = ()
    is_unique: bool = False
    method: str = ""
    #: The constraint that owns this index, or `""`. Non-empty means Postgres
    #: will refuse `DROP INDEX` on it — the whole reason this field exists.
    constraint_name: str = ""

    @property
    def is_constraint_backed(self) -> bool:
        return bool(self.constraint_name)

    @property
    def label(self) -> str:
        """`idx_orders_code — UNIQUE btree (code)`."""
        parts = []
        if self.is_unique:
            parts.append("UNIQUE")
        if self.method:
            parts.append(self.method)
        text = self.name
        if parts:
            text += f" — {' '.join(parts)}"
        if self.columns:
            text += f" ({', '.join(self.columns)})"
        return text


def _as_index(entry: Any) -> _Index:
    if isinstance(entry, _Index):
        return entry
    if isinstance(entry, str):
        return _Index(name=entry)
    return _Index(
        name=str(getattr(entry, "name", "")),
        qualified_name=str(getattr(entry, "qualified_name", "") or ""),
        columns=tuple(getattr(entry, "columns", ()) or ()),
        is_unique=bool(getattr(entry, "is_unique", False)),
        method=str(getattr(entry, "method", "") or ""),
        constraint_name=str(getattr(entry, "constraint_name", "") or ""),
    )


class CreateIndexDialog(_AlterColumnDialogBase):
    """Create index: name, columns, UNIQUE, access method.

    No column dropdown from the base — an index covers one *or more* columns,
    so slice 2's `_ColumnListPicker` replaces it, exactly as it does for
    `AddConstraintDialog`. The picker follows the table dropdown, because a
    column list only means something against its table.

    The index name is a **bare** identifier, not `schema.name`: the index is
    created in its table's schema and Postgres rejects a dotted name in
    `CREATE INDEX`. The emitter enforces that, and its refusal is what the red
    label shows.
    """

    _NEEDS_COLUMN = False

    def __init__(
        self,
        *,
        table: str,
        column: str = "",
        tables: TableSource = (),
        columns: ColumnSource = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            table=table,
            column=column,
            tables=tables,
            columns=columns,
            title="Create Index",
            parent=parent,
        )

    def _build_fields(self, form: QFormLayout) -> None:
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("idx_orders_code")
        form.addRow("Index name:", self._name_edit)

        self._column_picker = _ColumnListPicker()
        form.addRow("Columns:", self._column_picker)

        self._unique_check = QCheckBox("Unique")
        form.addRow("", self._unique_check)

        self._method_combo = QComboBox()
        self._method_combo.addItems(INDEX_METHODS)
        form.addRow("Method:", self._method_combo)

    def _change_signals(self) -> Sequence[object]:
        return (
            self._name_edit.textChanged,
            self._column_picker.changed,
            self._unique_check.toggled,
            self._method_combo.currentTextChanged,
        )

    def _reload_columns(self, select: str = "") -> None:
        # Called by the base at construction and on every table change, which
        # is precisely when the picker's offered columns must follow.
        super()._reload_columns(select=select)
        self._column_picker.set_columns(self._columns_for(self.table()), select=select)

    # --- Getters --------------------------------------------------------------
    def index_name(self) -> str:
        return self._name_edit.text().strip()

    def columns(self) -> list[str]:
        """The indexed columns, in the order the rows are in — index column
        order is semantic, so the picker never sorts it."""
        return self._column_picker.columns()

    def column_picker(self) -> _ColumnListPicker:
        return self._column_picker

    def unique(self) -> bool:
        return self._unique_check.isChecked()

    def method(self) -> str:
        return self._method_combo.currentText()

    def available_methods(self) -> list[str]:
        return [self._method_combo.itemText(i) for i in range(self._method_combo.count())]

    def _render_skeleton(self) -> str:
        if not self.index_name():
            raise SkeletonError("index name must not be empty")
        return create_index_skeleton(
            name=self.index_name(),
            table=self.table(),
            columns=self.columns(),
            unique=self.unique(),
            method=self.method(),
        )


class DropIndexDialog(_AlterColumnDialogBase):
    """Drop index — listing only the indexes Postgres will actually drop, and
    saying what it left out.

    See the module docstring: a PRIMARY KEY / UNIQUE / EXCLUDE constraint owns
    an implicit index that `DROP INDEX` refuses to touch. Those rows are
    filtered out of the picker *and named* in a plain (never red) note that
    points at `Drop constraint…`, so the list is honest about being partial.

    The emitter is handed the index's **own qualified identity**
    (`schema.index_name`), not the table's: an index name is unique within its
    schema and `DROP INDEX … ON table` does not exist in Postgres.
    """

    _NEEDS_COLUMN = False

    def __init__(
        self,
        *,
        table: str,
        column: str = "",
        tables: TableSource = (),
        columns: ColumnSource = (),
        indexes: IndexSource = (),
        parent: QWidget | None = None,
    ) -> None:
        # Read by `_build_fields` / `_reload_columns`, both of which the base
        # constructor calls.
        self._indexes_source = indexes
        self._index_entries: list[_Index] = []
        self._hidden_entries: list[_Index] = []
        super().__init__(
            table=table,
            column=column,
            tables=tables,
            columns=columns,
            title="Drop Index",
            parent=parent,
        )

    def _build_fields(self, form: QFormLayout) -> None:
        self._index_combo = QComboBox()
        form.addRow("Index:", self._index_combo)

        self._note_label = QLabel("")
        self._note_label.setWordWrap(True)
        form.addRow("", self._note_label)

    def _change_signals(self) -> Sequence[object]:
        return (self._index_combo.currentIndexChanged,)

    def _reload_columns(self, select: str = "") -> None:
        super()._reload_columns(select=select)
        self._reload_indexes()

    # --- Injected data --------------------------------------------------------
    def _indexes_for(self, table: str) -> list[_Index]:
        source = self._indexes_source
        if callable(source):
            entries: Sequence[Any] = source(table)
        elif isinstance(source, Mapping):
            entries = source.get(table, ())
        else:
            # A bare sequence describes the pre-bound table only — another
            # table borrowing it would list indexes that are not on it.
            entries = source if table == self._context_table else ()
        return [entry for entry in (_as_index(e) for e in entries) if entry.name]

    def _reload_indexes(self) -> None:
        every = self._indexes_for(self.table())
        self._index_entries = [e for e in every if not e.is_constraint_backed]
        self._hidden_entries = [e for e in every if e.is_constraint_backed]

        combo = self._index_combo
        combo.blockSignals(True)
        combo.clear()
        for entry in self._index_entries:
            # The label is for the human; the *data* is the qualified identity
            # the emitter needs, so what reaches it is never the display text.
            combo.addItem(entry.label, self._identity(entry))
        combo.blockSignals(False)
        combo.setEnabled(bool(self._index_entries))

    def _identity(self, entry: _Index) -> str:
        """`schema.index_name` — the spelling `DROP INDEX` takes.

        Injected `IndexInfo`s carry it directly. A caller who passed bare names
        instead gets the *selected table's* schema borrowed, which is correct
        because an index always lives in its table's schema.
        """
        if entry.qualified_name:
            return entry.qualified_name
        table = self.table()
        if "." in table:
            return f"{table.rsplit('.', 1)[0]}.{entry.name}"
        return entry.name

    def _refresh_validation(self, *_args: object) -> None:
        super()._refresh_validation()
        # Deliberately after the base: the note is not an error, must not be
        # red, and must never gate OK.
        self._note_label.setText(self.note())

    # --- Getters --------------------------------------------------------------
    def index_name(self) -> str:
        """The selected index's bare name — never its display label."""
        entry = self.selected_index()
        return entry.name if entry is not None else ""

    def index_identity(self) -> str:
        """The selected index's `schema.name`, which is what gets dropped."""
        data = self._index_combo.currentData()
        return str(data) if data else ""

    def selected_index(self) -> _Index | None:
        index = self._index_combo.currentIndex()
        if 0 <= index < len(self._index_entries):
            return self._index_entries[index]
        return None

    def index_labels(self) -> list[str]:
        return [self._index_combo.itemText(i) for i in range(self._index_combo.count())]

    def available_indexes(self) -> list[str]:
        """The droppable index names offered for the current table."""
        return [entry.name for entry in self._index_entries]

    def hidden_indexes(self) -> list[str]:
        """The constraint-backed index names deliberately NOT offered."""
        return [entry.name for entry in self._hidden_entries]

    def note(self) -> str:
        """Why the list is shorter than the Explorer's, or `""`.

        Never a reason OK is disabled — it explains an omission, it does not
        object to the user's choice.
        """
        if not self._hidden_entries:
            return ""
        listed = ", ".join(
            f"{entry.name} ({entry.constraint_name})" for entry in self._hidden_entries
        )
        count = len(self._hidden_entries)
        noun = "index is" if count == 1 else "indexes are"
        return (
            f"{count} {noun} not listed because a constraint owns it: {listed}. "
            "PostgreSQL refuses DROP INDEX on those — use Drop constraint… to "
            "remove the constraint, and its index goes with it."
        )

    def _render(self) -> tuple[str, str | None]:
        if not self.table():
            return "", "Choose the table to alter."
        if not self.index_identity():
            return "", _NO_INDEXES_MESSAGE
        return super()._render()

    def _render_skeleton(self) -> str:
        return drop_index_skeleton(index=self.index_identity())


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------
class SetCommentDialog(_AlterColumnDialogBase):
    """Set table comment **and** Set column comment — one class, two modes.

    They are one dialog because they collect the same thing (a comment) and
    differ only in whether a column is named; the column dropdown is simply
    absent in table mode. That is the same call slice 1's `ColumnActionDialog`
    makes for its four operations, and like it, the mode is fixed by the menu
    item rather than offered as a field — a dialog opened from "Set column
    comment" that could quietly comment the table instead would only invite
    disagreeing with the menu.

    **A comment may be pre-filled, unlike a `USING` clause or a `DEFAULT`.**
    Those are free SQL that no allowlist can cover, so slice 1 bound them to
    user typing alone. A comment is a *value* — rendered as a SQL string
    literal with its quotes doubled — so seeding the field with the existing
    comment is safe, and it is the difference between editing a description and
    retyping it from memory.

    **Blank removes the comment.** The emitter renders `IS NULL` for an empty
    box, which is Postgres's only spelling for "no comment"; the dialog says so
    in a plain note rather than treating empty as an error, because "take that
    comment off" is a legitimate thing to want.
    """

    def __init__(
        self,
        *,
        target: str,
        table: str,
        column: str = "",
        tables: TableSource = (),
        columns: ColumnSource = (),
        comment: str = "",
        parent: QWidget | None = None,
    ) -> None:
        if target not in _COMMENT_TITLES:
            raise ValueError(
                f"unknown comment target {target!r} — "
                f"expected one of {', '.join(COMMENT_TARGETS)}"
            )
        self._target = target
        # Per-instance override of the class attribute the base reads when it
        # builds the form: only the column flavour needs a column dropdown.
        self._NEEDS_COLUMN = target == OP_COLUMN_COMMENT
        self._initial_comment = comment
        super().__init__(
            table=table,
            column=column,
            tables=tables,
            columns=columns,
            title=_COMMENT_TITLES[target],
            parent=parent,
        )

    def _build_fields(self, form: QFormLayout) -> None:
        self._comment_edit = QLineEdit()
        self._comment_edit.setPlaceholderText("(blank removes the comment)")
        if self._initial_comment:
            self._comment_edit.setText(self._initial_comment)
        form.addRow("Comment:", self._comment_edit)

        note = QLabel(_BLANK_COMMENT_NOTE)
        note.setWordWrap(True)
        form.addRow("", note)

    def _change_signals(self) -> Sequence[object]:
        return (self._comment_edit.textChanged,)

    # --- Getters --------------------------------------------------------------
    def target(self) -> str:
        """The `OP_*` constant this dialog was built for."""
        return self._target

    def comment(self) -> str:
        """The comment text as typed. Deliberately NOT stripped of internal
        whitespace — a comment is prose, and only the emitter's
        blank-means-remove test looks at the edges."""
        return self._comment_edit.text()

    def removes_the_comment(self) -> bool:
        """True when OK will emit `IS NULL` rather than a literal."""
        return not self.comment().strip()

    def _render_skeleton(self) -> str:
        if self._target == OP_TABLE_COMMENT:
            return set_table_comment_skeleton(
                table=self.table(), comment=self.comment()
            )
        return set_column_comment_skeleton(
            table=self.table(), column=self.column(), comment=self.comment()
        )


# ---------------------------------------------------------------------------
# Whole-table
# ---------------------------------------------------------------------------
class _NewColumnRows(QWidget):
    """The `CREATE TABLE` column builder: name, type, nullable, default, PK.

    **Not `_ColumnListPicker`.** That widget *chooses* among a table's existing
    columns; this one *defines* columns that do not exist yet, so each row is a
    small form rather than a dropdown. Sharing a base between them would be a
    base with nothing in it but the "+"/"−" bookkeeping.

    Like the picker, the last row can never be removed: a table with zero
    columns is not a state any `CREATE TABLE` can be built from, so it is not
    offered as a state.

    Row order is preserved and is the column order of the emitted table.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        for text, stretch in (
            ("Name", 2),
            ("Type", 2),
            ("Nullable", 0),
            ("Default", 2),
            ("PK", 0),
        ):
            header.addWidget(QLabel(text), stretch)
        header.addSpacing(32)
        self._layout.addLayout(header)

        self._add_button = QPushButton("+")
        self._add_button.setToolTip("Add another column")
        self._add_button.setMaximumWidth(32)
        self._add_button.clicked.connect(self._on_add_clicked)

        add_row = QHBoxLayout()
        add_row.addWidget(self._add_button)
        add_row.addStretch(1)

        self._append_row()
        self._layout.addLayout(add_row)

    # --- Rows -----------------------------------------------------------------
    def _append_row(self) -> None:
        name = QLineEdit()
        name.setPlaceholderText("column_name")
        name.textChanged.connect(self.changed)

        datatype = QComboBox()
        datatype.setEditable(True)
        datatype.addItems(COMMON_COLUMN_TYPES)
        datatype.setCurrentText(COMMON_COLUMN_TYPES[0])
        datatype.currentTextChanged.connect(self.changed)

        nullable = QCheckBox()
        nullable.setToolTip("Nullable")
        nullable.setChecked(True)
        nullable.toggled.connect(self.changed)

        # A DEFAULT is arbitrary SQL, so it gets the widget that cannot be
        # seeded from anywhere but the keyboard (see the module docstring).
        default = _user_typed_line_edit("(optional) now()")
        default.textChanged.connect(self.changed)

        primary = QCheckBox()
        primary.setToolTip("Part of the primary key")
        primary.toggled.connect(self.changed)

        remove = QPushButton("−")
        remove.setToolTip("Remove this column")
        remove.setMaximumWidth(32)

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(name, 2)
        row_layout.addWidget(datatype, 2)
        row_layout.addWidget(nullable, 0)
        row_layout.addWidget(default, 2)
        row_layout.addWidget(primary, 0)
        row_layout.addWidget(remove)

        remove.clicked.connect(lambda: self._on_remove_clicked(row_widget))

        self._rows.append(
            {
                "widget": row_widget,
                "name": name,
                "datatype": datatype,
                "nullable": nullable,
                "default": default,
                "primary_key": primary,
                "remove": remove,
            }
        )
        # +1 for the header layout, which occupies index 0.
        self._layout.insertWidget(len(self._rows), row_widget)
        self._refresh_enabled()

    def _on_add_clicked(self) -> None:
        self._append_row()
        self.changed.emit()

    def _on_remove_clicked(self, row_widget: QWidget) -> None:
        for index, row in enumerate(self._rows):
            if row["widget"] is row_widget:
                self._remove_row(index)
                return

    def _remove_row(self, index: int, notify: bool = True) -> None:
        if len(self._rows) <= 1 or not 0 <= index < len(self._rows):
            # The guarantee stated in the class docstring, enforced here as well
            # as by the disabled button.
            return
        row = self._rows.pop(index)
        widget = row["widget"]
        self._layout.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()
        self._refresh_enabled()
        if notify:
            self.changed.emit()

    def _refresh_enabled(self) -> None:
        only_one = len(self._rows) == 1
        for row in self._rows:
            row["remove"].setEnabled(not only_one)

    # --- Getters / headless setters -------------------------------------------
    def row_count(self) -> int:
        return len(self._rows)

    def add_row(self) -> None:
        """Headless equivalent of pressing "+"."""
        self._on_add_clicked()

    def remove_row(self, index: int) -> None:
        """Headless equivalent of pressing a row's "−"."""
        self._remove_row(index)

    def set_row(
        self,
        index: int,
        *,
        name: str | None = None,
        datatype: str | None = None,
        nullable: bool | None = None,
        default: str | None = None,
        primary_key: bool | None = None,
    ) -> None:
        """Fill one row, growing the list if needed — the headless equivalent
        of typing into it."""
        while len(self._rows) <= index:
            self._append_row()
        row = self._rows[index]
        if name is not None:
            row["name"].setText(name)
        if datatype is not None:
            row["datatype"].setCurrentText(datatype)
        if nullable is not None:
            row["nullable"].setChecked(nullable)
        if default is not None:
            row["default"].setText(default)
        if primary_key is not None:
            row["primary_key"].setChecked(primary_key)
        self.changed.emit()

    def specs(self) -> list[ColumnSpec]:
        """The defined columns, in row order.

        A blank default is `None` ("no DEFAULT clause"), not an empty
        expression — the emitter rightly refuses the latter. A blank *name* is
        passed through as-is so the emitter can be the one to say "column name
        must not be empty", keeping validation in exactly one place.
        """
        specs: list[ColumnSpec] = []
        for row in self._rows:
            default = row["default"].text().strip()
            specs.append(
                ColumnSpec(
                    name=row["name"].text().strip(),
                    datatype=row["datatype"].currentText().strip(),
                    nullable=row["nullable"].isChecked(),
                    default=default or None,
                )
            )
        return specs

    def primary_key(self) -> list[str]:
        """The PK-checked column names, in row order (key order is semantic)."""
        return [
            row["name"].text().strip()
            for row in self._rows
            if row["primary_key"].isChecked() and row["name"].text().strip()
        ]


class CreateTableDialog(_AlterColumnDialogBase):
    """Create table — the one dialog here with no table to alter.

    **Why it still subclasses the alter base.** Everything below the first two
    rows is identical to its siblings: the red inline label, OK gated by
    calling the emitter, the `skeleton()` / `validation_error()` accessors. So
    rather than a second copy of that machinery, this class *reinterprets* the
    base's `table()` to mean "the table being created" — the name typed into
    its own field — and hides the two inherited rows that presuppose an
    existing one (the read-only "From:" line and the table dropdown). The
    caller may still pass a `schema`, which seeds the name field with
    `schema.` so a table created from a right-click lands where the click was.

    That reinterpretation is what makes the base's validation work unchanged:
    the emitter is called with `table=` exactly as every other dialog calls it,
    and its refusals ("table has an empty name part", an unsafe identifier) are
    what the red label shows.

    What the dialog cannot express is stated by the emitter it drives — no
    foreign keys, unique/check constraints, indexes or identity columns; see
    `db/ddl_skeleton.create_table_skeleton`. Those are the *other* dialogs in
    this feature, applied to the table once it exists, and the generated text
    is editable before anything runs.
    """

    _NEEDS_COLUMN = False

    def __init__(
        self,
        *,
        schema: str = "",
        tables: TableSource = (),
        parent: QWidget | None = None,
    ) -> None:
        # Read by `_build_fields`, which the base constructor calls.
        self._initial_schema = schema
        super().__init__(
            table="",
            tables=tables,
            columns=(),
            title="Create Table",
            parent=parent,
        )
        # The inherited context rows presuppose an existing table. Row 0 is the
        # read-only "From:" line (whose label widget the base does not keep a
        # reference to, hence the index); the table dropdown is addressed by
        # widget.
        self._form.setRowVisible(0, False)
        self._form.setRowVisible(self._table_combo, False)

    def _build_fields(self, form: QFormLayout) -> None:
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("public.new_table")
        if self._initial_schema:
            self._name_edit.setText(f"{self._initial_schema}.")
        form.addRow("New table:", self._name_edit)

        self._rows_widget = _NewColumnRows()
        form.addRow("Columns:", self._rows_widget)

    def _change_signals(self) -> Sequence[object]:
        return (self._name_edit.textChanged, self._rows_widget.changed)

    # --- Getters --------------------------------------------------------------
    def table(self) -> str:
        """The table to CREATE — this dialog's reinterpretation of the base's
        "which table" (see the class docstring)."""
        return self._name_edit.text().strip()

    def column_rows(self) -> _NewColumnRows:
        """The multi-column builder — the headless entry point for tests and
        for a caller that wants to pre-fill a row."""
        return self._rows_widget

    def specs(self) -> list[ColumnSpec]:
        return self._rows_widget.specs()

    def primary_key(self) -> list[str]:
        return self._rows_widget.primary_key()

    def _render(self) -> tuple[str, str | None]:
        # The base's "Choose the table to alter." is the wrong sentence when
        # there is nothing to choose from and nothing to alter.
        if not self.table():
            return "", "Name the table to create."
        return super()._render()

    def _render_skeleton(self) -> str:
        return create_table_skeleton(
            table=self.table(),
            columns=self.specs(),
            primary_key=self.primary_key(),
        )


class DropTableDialog(_AlterColumnDialogBase):
    """Drop table — table dropdown, a plain note, and **no confirmation**.

    FQ-025's ruling, honoured deliberately: there is no typed-name gate, no
    "are you sure?", and no red warning, because generating `DROP TABLE t`
    executes nothing. The safeguard is that the statement lands in an editable
    tab and running it is a separate explicit gesture — putting the friction at
    generation time would place it where nothing happens and leave it absent
    where something does.

    The note states the consequence rather than objecting to it, the same way
    `DropConstraintDialog`'s does, and never gates OK.
    """

    _NEEDS_COLUMN = False

    def __init__(
        self,
        *,
        table: str,
        column: str = "",
        tables: TableSource = (),
        columns: ColumnSource = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            table=table,
            column=column,
            tables=tables,
            columns=columns,
            title="Drop Table",
            parent=parent,
        )

    def _build_fields(self, form: QFormLayout) -> None:
        note = QLabel(
            "This generates DROP TABLE into an editable tab — nothing runs "
            "until you apply it. No CASCADE is emitted, so PostgreSQL will "
            "refuse if a view or another table's foreign key depends on this "
            "table."
        )
        note.setWordWrap(True)
        form.addRow("", note)

    def _render_skeleton(self) -> str:
        return drop_table_skeleton(table=self.table())
