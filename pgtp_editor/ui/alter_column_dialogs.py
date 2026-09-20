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

# pgtp_editor/ui/alter_column_dialogs.py
"""The "Alter Table ▸" column-operation dialogs (FQ-025 slice 1, §18.1/§18.5).

Five dialog classes cover the eight column operations, split by *what the
dialog actually collects* rather than one-per-menu-item:

- `ColumnActionDialog` — the four operations whose entire input is "which table,
  which column": Drop column, Set NOT NULL, Drop NOT NULL, Drop DEFAULT. They
  share one form to the pixel, so they share one class parameterised by an
  `OP_*` constant (the same "one dialog, kind as a field inside it" call
  `NewRoutineDialog` makes for Function/Procedure). The operation is *not* a
  user-editable field here, though: the menu item the user picked chose it, and
  offering "…and actually do something else" would only invite disagreeing with
  the menu.
- `AddColumnDialog` — name, datatype, nullable, comment.
- `RenameColumnDialog` — the new name.
- `ChangeColumnTypeDialog` — the new datatype and an optional `USING` clause.
- `SetColumnDefaultDialog` — the default expression.

Everything they share (the table dropdown, the column dropdown, the read-only
click-context line, the error label, the OK gating) lives in
`_AlterColumnDialogBase`.

Four rules carried over verbatim from the FQ-002 precedent
(`new_trigger_dialog.py` / `new_routine_dialog.py`):

- **Shown non-modally** (`show()`, never `.exec()`). The dialog persists nothing
  and executes nothing; the caller reads the accessors (or the ready-rendered
  `skeleton()`) back after `accepted` fires and opens the editor tab itself.
- **All dropdown data is injected by the caller.** These dialogs open no
  connection, import nothing from `db/introspect`, and learn about tables and
  columns only through the plain data handed to `__init__`.
- **The click context is shown read-only *and* pre-selected in the dropdowns.**
  Which table/column an operation targets defaults to the node that was
  right-clicked but stays changeable — the entry's core interaction rule — so
  the origin is stated as a read-only line rather than by freezing the combos.
- **OK is disabled until the input renders**, and "renders" is decided by
  *calling the emitter and catching its exception*, never by a second copy of
  its rules here. The caught message is what the inline red label shows, so the
  user reads `db/ddl_skeleton.py`'s own words ("a column needs a datatype",
  "USING clause must not be empty", "…has unbalanced parentheses: …").

**Free SQL text is user-typed only.** `alter_column_type_skeleton`'s `USING`
clause and `set_column_default_skeleton`'s `DEFAULT` expression are arbitrary
SQL and cannot be allowlisted; the emitter checks only that they stay one
statement, and its docstring puts the rest of the burden here: those two fields
must only ever carry the user's own keystrokes, never a value passed through
from a database, a file, or a `.pgtp` project. This module honours that
structurally — see `_user_typed_line_edit`, the only way those two widgets are
built, and note that neither is seeded, pre-filled, completed or injected from
anywhere. No constructor of any class here accepts an initial `using` or
`expression` value; adding one would break the rule.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.ddl_skeleton import (
    SkeletonError,
    add_column_skeleton,
    alter_column_type_skeleton,
    drop_column_default_skeleton,
    drop_column_not_null_skeleton,
    drop_column_skeleton,
    rename_column_skeleton,
    set_column_default_skeleton,
    set_column_not_null_skeleton,
)
from pgtp_editor.db.sandbox import UnsafeIdentifierError
from pgtp_editor.ui.status_colours import STATUS_ERROR, StatusLabel

#: The table names to offer, or a callable producing them. The caller derives
#: them from the already-loaded `introspect.DatabaseSchema`; this dialog never
#: learns what a connection is.
TableSource = Sequence[str] | Callable[[], Sequence[str]]

#: The columns to offer. Three accepted shapes, all plain data:
#: a `{table: [column, ...]}` mapping, a `table -> [column, ...]` callable, or a
#: bare sequence meaning "the columns of the pre-bound table" (unambiguous
#: because that table is always passed explicitly).
ColumnSource = (
    Mapping[str, Sequence[str]]
    | Callable[[str], Sequence[str]]
    | Sequence[str]
)

#: Seeded column types for the editable datatype combo — the same convenience
#: -not-a-constraint posture as `NewRoutineDialog.COMMON_RETURN_TYPES`: anything
#: `db/ddl_skeleton.py`'s datatype allowlist accepts can be typed instead
#: (`numeric(10,2)`, `integer[]`, `pr.my_domain`).
COMMON_COLUMN_TYPES = (
    "text",
    "integer",
    "bigint",
    "boolean",
    "numeric",
    "numeric(10,2)",
    "character varying(255)",
    "date",
    "timestamptz",
    "jsonb",
    "uuid",
)

#: `ColumnActionDialog` operations — the four that collect nothing but "which
#: table, which column".
OP_DROP_COLUMN = "drop_column"
OP_SET_NOT_NULL = "set_not_null"
OP_DROP_NOT_NULL = "drop_not_null"
OP_DROP_DEFAULT = "drop_default"

#: operation -> (window title, emitter). The emitters all take exactly
#: `table=`/`column=`, which is precisely why these four share a dialog.
_COLUMN_ACTIONS: dict[str, tuple[str, Callable[..., str]]] = {
    OP_DROP_COLUMN: ("Drop Column", drop_column_skeleton),
    OP_SET_NOT_NULL: ("Set NOT NULL", set_column_not_null_skeleton),
    OP_DROP_NOT_NULL: ("Drop NOT NULL", drop_column_not_null_skeleton),
    OP_DROP_DEFAULT: ("Drop DEFAULT", drop_column_default_skeleton),
}

COLUMN_ACTIONS = tuple(_COLUMN_ACTIONS)

_NO_COLUMNS_MESSAGE = (
    "This table has no columns to choose from — pick another table, or reload"
    " the schema."
)


def _user_typed_line_edit(placeholder: str) -> QLineEdit:
    """Build the widget for a field that carries **arbitrary SQL**.

    `USING` clauses and `DEFAULT` expressions cannot be allowlisted (see
    `db/ddl_skeleton.alter_column_type_skeleton`), so the emitter's only
    remaining guarantee is that the statement stays one statement. The
    compensating rule it delegates to this layer is provenance: such a field may
    contain the user's own typing and nothing else. This helper is the single
    place those widgets are created, and it deliberately offers **no** way to
    seed, pre-fill or complete them — no initial text argument, no completer, no
    injected model. A future change that wants to pre-populate a `USING` clause
    from introspected data has to defeat this function to do it.
    """
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    return edit


class _AlterColumnDialogBase(QDialog):
    """Table/column context, validation and OK gating shared by slice 1.

    Subclasses add their own rows via `_build_fields`, list the widgets whose
    changes re-validate via `_change_signals`, and render via
    `_render_skeleton`, which may raise — the base catches.
    """

    #: Subclasses that identify an existing column keep the column dropdown;
    #: `AddColumnDialog` (whose column does not exist yet) turns it off.
    _NEEDS_COLUMN = True

    def __init__(
        self,
        *,
        table: str,
        column: str = "",
        tables: TableSource = (),
        columns: ColumnSource = (),
        title: str = "Alter Table",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)

        self._context_table = table
        self._context_column = column
        self._columns_source = columns

        names = tables() if callable(tables) else tables
        # The clicked table is always offered even if the injected list somehow
        # omits it: the dialog must never contradict the node it was summoned
        # from.
        table_names = sorted({*names, table} - {""})
        self._tables: list[str] = table_names

        self._table_combo = QComboBox()
        self._table_combo.addItems(self._tables)
        if table:
            self._table_combo.setCurrentText(table)

        self._column_combo = QComboBox()

        # A `StatusLabel` in the error KIND, painted per theme: plain
        # `color: red` measured 3.98:1 on the dark chrome and 3.83:1 on the
        # light one -- below 4.5:1 in BOTH (BUG-260812063745).
        self._error_label = StatusLabel("")
        self._error_label.set_status_kind(STATUS_ERROR)
        self._error_label.setWordWrap(True)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_accept_clicked)
        self._buttons.rejected.connect(self.reject)

        form = QFormLayout()
        # The click context, stated read-only. The dropdowns below default to
        # it but stay changeable, so this line answers "where did this dialog
        # come from?" without the combos having to be frozen to say it.
        form.addRow("From:", QLabel(self._context_description()))
        form.addRow("Table:", self._table_combo)
        if self._NEEDS_COLUMN:
            form.addRow("Column:", self._column_combo)
        self._form = form
        self._build_fields(form)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error_label)
        layout.addWidget(self._buttons)

        self._reload_columns(select=self._context_column)
        self._table_combo.currentTextChanged.connect(self._on_table_changed)
        self._column_combo.currentIndexChanged.connect(self._refresh_validation)
        for signal in self._change_signals():
            signal.connect(self._refresh_validation)

        # Opening size only (BUG-036 convention): resizable afterwards, with the
        # slack landing on the word-wrapping error label.
        self.resize(560, 200)
        self._refresh_validation()

    # --- Subclass hooks -------------------------------------------------------
    def _build_fields(self, form: QFormLayout) -> None:
        """Add the operation's own rows. Default: none (table/column only)."""

    def _change_signals(self) -> Sequence[object]:
        """Signals that should re-run validation. Table/column are wired by the
        base; subclasses list only their own widgets'."""
        return ()

    def _render_skeleton(self) -> str:
        raise NotImplementedError

    # --- Context / injected data ---------------------------------------------
    def _context_description(self) -> str:
        if self._context_column:
            return f"{self._context_table}.{self._context_column}"
        return self._context_table or "(no table)"

    def _columns_for(self, table: str) -> list[str]:
        source = self._columns_source
        if callable(source):
            names: Sequence[str] = source(table)
        elif isinstance(source, Mapping):
            names = source.get(table, ())
        else:
            # A bare sequence describes the pre-bound table only; another table
            # borrowing that list would be a fabricated column set.
            names = source if table == self._context_table else ()
        return list(names)

    def _reload_columns(self, select: str = "") -> None:
        columns = self._columns_for(self.table())
        self._column_combo.blockSignals(True)
        self._column_combo.clear()
        self._column_combo.addItems(columns)
        if select and select in columns:
            self._column_combo.setCurrentText(select)
        self._column_combo.blockSignals(False)
        self._column_combo.setEnabled(bool(columns))

    def _on_table_changed(self, *_args: object) -> None:
        # Re-selecting the origin table restores the clicked column; any other
        # table starts at its own first column.
        select = (
            self._context_column if self.table() == self._context_table else ""
        )
        self._reload_columns(select=select)
        self._refresh_validation()

    # --- Getters (read after `accepted` fires) --------------------------------
    def table(self) -> str:
        return self._table_combo.currentText()

    def column(self) -> str:
        return self._column_combo.currentText() if self._NEEDS_COLUMN else ""

    def context_table(self) -> str:
        """The table the click came from, whatever the dropdown now says."""
        return self._context_table

    def context_column(self) -> str:
        """The column the click came from, whatever the dropdown now says."""
        return self._context_column

    def available_tables(self) -> list[str]:
        """The injected table names, sorted, with the clicked table included."""
        return list(self._tables)

    def available_columns(self) -> list[str]:
        """The injected columns of the currently selected table."""
        return [self._column_combo.itemText(i) for i in range(self._column_combo.count())]

    def skeleton(self) -> str:
        """The rendered statement(s) for the current field state, or `""` when
        that state is invalid (see `validation_error`). All SQL comes from
        `db/ddl_skeleton.py`; none is assembled here."""
        rendered, _ = self._render()
        return rendered

    def validation_error(self) -> str | None:
        """Why OK is disabled, or `None` when the current state is valid."""
        _, error = self._render()
        return error

    def is_valid(self) -> bool:
        return self.validation_error() is None

    # --- Validation -----------------------------------------------------------
    def _render(self) -> tuple[str, str | None]:
        """Render, or explain the refusal. Never raises: `SkeletonError` and
        `UnsafeIdentifierError` both become inline validation text, so the
        message the user reads is the emitter's own."""
        if not self.table():
            return "", "Choose the table to alter."
        if self._NEEDS_COLUMN and not self.column():
            return "", _NO_COLUMNS_MESSAGE
        try:
            return self._render_skeleton(), None
        except (SkeletonError, UnsafeIdentifierError) as exc:
            return "", str(exc)

    def _refresh_validation(self, *_args: object) -> None:
        error = self.validation_error()
        self._error_label.setText(error or "")
        ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(error is None)

    def _on_accept_clicked(self) -> None:
        # Belt-and-braces alongside the disabled OK button: a programmatic click
        # must not smuggle invalid DDL past validation.
        if not self.is_valid():
            self._refresh_validation()
            return
        self.accept()


class ColumnActionDialog(_AlterColumnDialogBase):
    """Drop column / Set NOT NULL / Drop NOT NULL / Drop DEFAULT.

    Four menu items, one form: each collects exactly "which table, which
    column", and their emitters take exactly `table=`/`column=`. Splitting them
    into four classes would produce four identical bodies differing only in a
    function reference and a title string.
    """

    def __init__(
        self,
        *,
        operation: str,
        table: str,
        column: str = "",
        tables: TableSource = (),
        columns: ColumnSource = (),
        parent: QWidget | None = None,
    ) -> None:
        if operation not in _COLUMN_ACTIONS:
            raise ValueError(
                f"unknown column operation {operation!r} — "
                f"expected one of {', '.join(COLUMN_ACTIONS)}"
            )
        self._operation = operation
        title, self._emitter = _COLUMN_ACTIONS[operation]
        super().__init__(
            table=table,
            column=column,
            tables=tables,
            columns=columns,
            title=title,
            parent=parent,
        )

    def operation(self) -> str:
        """The `OP_*` constant this dialog was built for — fixed by the menu
        item, not a field the user can change."""
        return self._operation

    def _render_skeleton(self) -> str:
        return self._emitter(table=self.table(), column=self.column())


class AddColumnDialog(_AlterColumnDialogBase):
    """Add column: name, datatype, nullable, comment.

    No column dropdown — the column being named does not exist yet, so the
    click context contributes the *table* and (when the click came from a
    column node) only the read-only "From:" line.
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
            title="Add Column",
            parent=parent,
        )

    def _build_fields(self, form: QFormLayout) -> None:
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("new_column")

        self._type_combo = QComboBox()
        self._type_combo.setEditable(True)
        self._type_combo.addItems(COMMON_COLUMN_TYPES)
        self._type_combo.setCurrentText(COMMON_COLUMN_TYPES[0])

        self._nullable_check = QCheckBox("Nullable")
        self._nullable_check.setChecked(True)

        self._comment_edit = QLineEdit()
        self._comment_edit.setPlaceholderText("(optional) column comment")

        form.addRow("Name:", self._name_edit)
        form.addRow("Datatype:", self._type_combo)
        form.addRow("", self._nullable_check)
        form.addRow("Comment:", self._comment_edit)

    def _change_signals(self) -> Sequence[object]:
        return (
            self._name_edit.textChanged,
            self._type_combo.currentTextChanged,
            self._nullable_check.toggled,
            self._comment_edit.textChanged,
        )

    # --- Getters --------------------------------------------------------------
    def column_name(self) -> str:
        return self._name_edit.text().strip()

    def datatype(self) -> str:
        return self._type_combo.currentText().strip()

    def nullable(self) -> bool:
        return self._nullable_check.isChecked()

    def comment(self) -> str:
        return self._comment_edit.text().strip()

    def _render_skeleton(self) -> str:
        if not self.column_name():
            raise SkeletonError("column name must not be empty")
        return add_column_skeleton(
            table=self.table(),
            column=self.column_name(),
            datatype=self.datatype(),
            nullable=self.nullable(),
            # Blank is "no comment": the emitter emits no second statement at
            # all rather than `IS ''`, which means something different.
            comment=self.comment() or None,
        )


class RenameColumnDialog(_AlterColumnDialogBase):
    """Rename column: the one extra field is the new name."""

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
            title="Rename Column",
            parent=parent,
        )

    def _build_fields(self, form: QFormLayout) -> None:
        self._new_name_edit = QLineEdit()
        self._new_name_edit.setPlaceholderText("new_name")
        form.addRow("New name:", self._new_name_edit)

    def _change_signals(self) -> Sequence[object]:
        return (self._new_name_edit.textChanged,)

    def new_name(self) -> str:
        return self._new_name_edit.text().strip()

    def _render_skeleton(self) -> str:
        if not self.new_name():
            raise SkeletonError("new column name must not be empty")
        return rename_column_skeleton(
            table=self.table(),
            column=self.column(),
            new_name=self.new_name(),
        )


class ChangeColumnTypeDialog(_AlterColumnDialogBase):
    """Change column type, with the optional `USING` clause.

    `USING` gets its own field rather than being left to the editor tab because
    a type change without it fails outright on incompatible data — the whole
    reason the entry calls it out. The field is built by
    `_user_typed_line_edit`: it is never seeded from the schema, the project or
    a file (see the module docstring).
    """

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
            title="Change Column Type",
            parent=parent,
        )

    def _build_fields(self, form: QFormLayout) -> None:
        self._type_combo = QComboBox()
        self._type_combo.setEditable(True)
        self._type_combo.addItems(COMMON_COLUMN_TYPES)
        self._type_combo.setCurrentText(COMMON_COLUMN_TYPES[0])

        self._using_edit = _user_typed_line_edit("(optional) trim(code)::integer")

        form.addRow("New datatype:", self._type_combo)
        form.addRow("USING:", self._using_edit)

    def _change_signals(self) -> Sequence[object]:
        return (self._type_combo.currentTextChanged, self._using_edit.textChanged)

    def datatype(self) -> str:
        return self._type_combo.currentText().strip()

    def using(self) -> str:
        """The user's own typed `USING` expression, or `""` for none."""
        return self._using_edit.text().strip()

    def _render_skeleton(self) -> str:
        # An untouched field is "no USING clause" (`None`), not an empty one —
        # the emitter rightly refuses a blank `USING` as a syntax error.
        using = self.using() or None
        return alter_column_type_skeleton(
            table=self.table(),
            column=self.column(),
            datatype=self.datatype(),
            using=using,
        )


class SetColumnDefaultDialog(_AlterColumnDialogBase):
    """Set DEFAULT: one free-SQL expression field.

    Dropping a default is `ColumnActionDialog(OP_DROP_DEFAULT)` — a blank
    expression here is a syntax error, not "remove the default", so the two are
    different operations rather than one field's empty state. Like `USING`, the
    expression is built by `_user_typed_line_edit` and carries typed input only.
    """

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
            title="Set DEFAULT",
            parent=parent,
        )

    def _build_fields(self, form: QFormLayout) -> None:
        self._expression_edit = _user_typed_line_edit("0   ·   now()   ·   'pending'")
        form.addRow("Default:", self._expression_edit)

    def _change_signals(self) -> Sequence[object]:
        return (self._expression_edit.textChanged,)

    def default_expression(self) -> str:
        """The user's own typed default expression."""
        return self._expression_edit.text().strip()

    def _render_skeleton(self) -> str:
        return set_column_default_skeleton(
            table=self.table(),
            column=self.column(),
            expression=self.default_expression(),
        )
