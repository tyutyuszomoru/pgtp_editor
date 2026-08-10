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

# pgtp_editor/ui/constraint_dialogs.py
"""The "Alter Table ▸" constraint dialogs (FQ-025 slice 2, §18.1/§18.5).

Four dialogs, matching the four emitters in `db/ddl_skeleton.py`:

- `AddConstraintDialog` — name, a TYPE dropdown (PRIMARY KEY / UNIQUE / CHECK /
  EXCLUDE) and, depending on the type, either a multi-column picker with a "+"
  or a free-SQL expression field.
- `AddForeignKeyDialog` — name, the local column(s), and a *referenced* table
  chooser whose selection repopulates a referenced-column picker.
- `DropConstraintDialog` — the one drop for every type, listing each existing
  constraint **with its type shown** so a FK is distinguishable from a CHECK
  before it is dropped.
- `RenameConstraintDialog` — the same typed picker plus a new name.

**Why `Add constraint` and `Add foreign key` share a base but `Drop` and
`Rename` do not.** The two `ADD`s collect the same first half — a constraint
name and a list of this table's columns, in order — and differ only in what
comes after it (a type-dependent definition vs. a referenced table and its
columns). `_AddConstraintDialogBase` owns that shared half. `Drop` and `Rename`
collect something categorically different — an *existing named* constraint —
and share `_ExistingConstraintDialogBase` instead. Forcing all four into one
base would produce a class whose fields are half-inapplicable in every mode.

**Where the shared column picker lives.** `_ColumnListPicker` is a plain
`QWidget`, not a dialog mixin, because it is used **three** times and not once
per dialog: the local columns of `AddConstraintDialog`, and both the local and
the referenced columns of `AddForeignKeyDialog`. Being a widget rather than a
base-class hook is what lets one dialog hold two independent instances.

Everything else is inherited verbatim from slice 1: these dialogs subclass
`alter_column_dialogs._AlterColumnDialogBase`, so the table dropdown, the
read-only "From:" click-context line, the red inline error label, the
OK-disabled-until-valid gating and the *validity-is-whatever-the-emitter-says*
rule are the same code, not a second implementation of the same rules. The four
FQ-002 rules therefore hold here too:

- shown non-modally (`show()`, never `.exec()`);
- **all list data is injected by the caller** — tables, columns and the existing
  constraints all arrive as plain data in `__init__`; nothing here imports
  `db/introspect`, opens a connection or queries anything;
- the click context is shown read-only *and* pre-selected, never frozen;
- OK is gated by calling the emitter and catching `SkeletonError` /
  `UnsafeIdentifierError`, so the message in the red label is the emitter's own.

**Free SQL text is user-typed only.** A `CHECK` body and an `EXCLUDE` element
list are arbitrary SQL that no allowlist can cover (see
`db/ddl_skeleton.add_constraint_skeleton`). The compensating rule is
provenance, and it is honoured structurally: the expression field is built by
slice 1's `_user_typed_line_edit`, which offers no way to seed, complete or
inject a value, and no constructor here accepts an initial expression.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
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
    CONSTRAINT_TYPES,
    EXCLUDE_METHODS,
    EXPRESSION_CONSTRAINT_TYPES,
    FK_ACTIONS,
    SkeletonError,
    add_constraint_skeleton,
    add_foreign_key_skeleton,
    drop_constraint_skeleton,
    rename_constraint_skeleton,
)
from pgtp_editor.ui.alter_column_dialogs import (
    ColumnSource,
    TableSource,
    _AlterColumnDialogBase,
    _user_typed_line_edit,
)

#: The existing constraints to offer. The same three shapes `ColumnSource`
#: accepts, for the same reason — a `{table: [...]}` mapping, a
#: `table -> [...]` callable, or a bare sequence meaning "the constraints of the
#: pre-bound table". Each element is either a plain name, or anything carrying
#: `.name` / `.kind` (`db.introspect.ConstraintInfo` is exactly that shape, but
#: this module never imports it — the caller passes data, not a schema).
ConstraintSource = (
    Mapping[str, Sequence[Any]] | Callable[[str], Sequence[Any]] | Sequence[Any]
)

#: Shown in the referential-action dropdowns. The leading blank is not a
#: keyword: it means "emit no `ON DELETE` clause at all", which is what the
#: emitter's `None` does — distinct in the generated *text* from spelling out
#: `NO ACTION`, even though Postgres treats them the same.
_NO_ACTION_CHOICE = "(none)"

_NO_CONSTRAINTS_MESSAGE = (
    "This table has no named constraints — pick another table, or reload the"
    " schema."
)


@dataclass(frozen=True)
class _Constraint:
    """One row of the typed constraint picker, normalised from injected data.

    Deliberately a local shape rather than `db.introspect.ConstraintInfo`: the
    dialogs must stay ignorant of the schema model (slice 1's injected-data
    rule), so a caller may hand over `ConstraintInfo`s, bare names, or anything
    else with a `.name`.
    """

    name: str
    kind: str = ""
    columns: tuple[str, ...] = ()
    definition: str = ""

    @property
    def label(self) -> str:
        """`fk_customer — FOREIGN KEY (customer_id)`.

        The **type is always shown**, which is the whole point of the unified
        drop: `ALTER TABLE … DROP CONSTRAINT` is identical for every type, so
        the list is the only place the user can tell a foreign key from a CHECK
        before dropping it.

        A constraint with no columns is legitimate — a table-level `CHECK
        (true)` has a NULL `conkey` — so the fallback is its `definition`
        rather than an empty pair of parentheses that would read as "constrains
        nothing".
        """
        text = self.name
        if self.kind:
            text += f" — {self.kind.upper()}"
        if self.columns:
            text += f" ({', '.join(self.columns)})"
        elif self.definition:
            text += f" — {self.definition}"
        return text

    @property
    def backs_an_index(self) -> bool:
        """True when Postgres maintains an implicit index for this constraint.

        PRIMARY KEY, UNIQUE and EXCLUDE each own an index that is dropped with
        them; CHECK and FOREIGN KEY own none.
        """
        return self.kind.lower() in ("primary key", "unique", "exclude")


def _as_constraint(entry: Any) -> _Constraint:
    if isinstance(entry, _Constraint):
        return entry
    if isinstance(entry, str):
        return _Constraint(name=entry)
    return _Constraint(
        name=str(getattr(entry, "name", "")),
        kind=str(getattr(entry, "kind", "") or ""),
        columns=tuple(getattr(entry, "columns", ()) or ()),
        definition=str(getattr(entry, "definition", "") or ""),
    )


class _ColumnListPicker(QWidget):
    """One-or-more column dropdowns with a "+" to add another and a "−" to
    remove one.

    **The last row can never be removed.** Its "−" is disabled whenever a
    single row remains, rather than allowing an empty picker that the emitter
    would then reject ("a PRIMARY KEY constraint needs at least one column")
    with the only cure being to press "+" again. Zero columns is not a state
    any constraint here can be built from, so it is not offered as a state —
    the dialog stays in a repairable shape instead of gating OK on a mistake
    the widget invited.

    Rows keep their order: a key's column order is semantic (it decides the
    backing index's usefulness, and a foreign key pairs its columns
    positionally), so the picker never sorts what the user arranged.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._columns: list[str] = []
        self._rows: list[tuple[QWidget, QComboBox, QPushButton]] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._add_button = QPushButton("+")
        self._add_button.setToolTip("Add another column to this key")
        self._add_button.setMaximumWidth(32)
        self._add_button.clicked.connect(self._on_add_clicked)

        add_row = QHBoxLayout()
        add_row.addWidget(self._add_button)
        add_row.addStretch(1)
        self._add_row_layout = add_row

        self._append_row()
        self._layout.addLayout(add_row)

    # --- Injected data --------------------------------------------------------
    def set_columns(self, columns: Sequence[str], select: str = "") -> None:
        """Replace the offered columns (the caller's injected list) and collapse
        back to a single row.

        Collapsing is deliberate: rows two and three named columns of the
        *previous* table, and silently re-pointing them at same-named columns of
        the new one would build a key out of coincidence.
        """
        self._columns = list(columns)
        while len(self._rows) > 1:
            self._remove_row(len(self._rows) - 1, notify=False)
        combo = self._rows[0][1]
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(self._columns)
        if select and select in self._columns:
            combo.setCurrentText(select)
        combo.blockSignals(False)
        self._refresh_enabled()
        self.changed.emit()

    # --- Rows -----------------------------------------------------------------
    def _append_row(self) -> None:
        combo = QComboBox()
        combo.addItems(self._columns)
        combo.currentIndexChanged.connect(self.changed)

        remove = QPushButton("−")
        remove.setToolTip("Remove this column from the key")
        remove.setMaximumWidth(32)

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(combo, 1)
        row_layout.addWidget(remove)

        remove.clicked.connect(lambda: self._on_remove_clicked(row_widget))

        self._rows.append((row_widget, combo, remove))
        self._layout.insertWidget(len(self._rows) - 1, row_widget)
        self._refresh_enabled()

    def _on_add_clicked(self) -> None:
        self._append_row()
        self.changed.emit()

    def _on_remove_clicked(self, row_widget: QWidget) -> None:
        for index, (widget, _combo, _button) in enumerate(self._rows):
            if widget is row_widget:
                self._remove_row(index)
                return

    def _remove_row(self, index: int, notify: bool = True) -> None:
        if len(self._rows) <= 1:
            # The guarantee stated in the class docstring, enforced here as well
            # as by the disabled button: a programmatic click must not empty the
            # picker either.
            return
        widget, _combo, _button = self._rows.pop(index)
        self._layout.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()
        self._refresh_enabled()
        if notify:
            self.changed.emit()

    def _refresh_enabled(self) -> None:
        only_one = len(self._rows) == 1
        for _widget, combo, button in self._rows:
            button.setEnabled(not only_one)
            combo.setEnabled(bool(self._columns))
        self._add_button.setEnabled(bool(self._columns))

    # --- Getters --------------------------------------------------------------
    def columns(self) -> list[str]:
        """The chosen columns, in row order, blanks dropped."""
        return [combo.currentText() for _w, combo, _b in self._rows if combo.currentText()]

    def row_count(self) -> int:
        return len(self._rows)

    def available_columns(self) -> list[str]:
        return list(self._columns)

    def add_row(self) -> None:
        """Headless equivalent of pressing "+"."""
        self._on_add_clicked()

    def remove_row(self, index: int) -> None:
        """Headless equivalent of pressing a row's "−"."""
        self._remove_row(index)

    def set_selection(self, columns: Sequence[str]) -> None:
        """Select `columns`, growing or shrinking the rows to match."""
        wanted = [c for c in columns if c in self._columns]
        if not wanted:
            return
        while len(self._rows) > len(wanted):
            self._remove_row(len(self._rows) - 1, notify=False)
        while len(self._rows) < len(wanted):
            self._append_row()
        for (_w, combo, _b), name in zip(self._rows, wanted):
            combo.setCurrentText(name)
        self.changed.emit()


class _AddConstraintDialogBase(_AlterColumnDialogBase):
    """The half `Add constraint` and `Add foreign key` genuinely share: a
    constraint name and an ordered, growable list of *this* table's columns.

    `_NEEDS_COLUMN` is off because slice 1's single column dropdown is the wrong
    control here — a key has one *or more* columns — so the picker replaces it
    rather than sitting beside it.

    The constraint name is **required**, mirroring the emitter. Leaving it blank
    would let Postgres auto-name the constraint (`orders_qty_check1`), which is
    exactly what makes the drop and rename pickers a guessing game afterwards.
    """

    _NEEDS_COLUMN = False

    def _build_fields(self, form: QFormLayout) -> None:
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("constraint_name")
        form.addRow("Constraint name:", self._name_edit)

        self._column_picker = _ColumnListPicker()
        form.addRow(self._columns_label(), self._column_picker)

        self._build_extra_fields(form)

    def _columns_label(self) -> str:
        return "Columns:"

    def _build_extra_fields(self, form: QFormLayout) -> None:
        """Rows below the shared column picker. Default: none."""

    def _change_signals(self) -> Sequence[object]:
        return (self._name_edit.textChanged, self._column_picker.changed)

    def _reload_columns(self, select: str = "") -> None:
        # The base calls this at construction and again on every table change,
        # which is precisely when the picker's offered columns must follow.
        super()._reload_columns(select=select)
        self._column_picker.set_columns(self._columns_for(self.table()), select=select)

    # --- Getters --------------------------------------------------------------
    def constraint_name(self) -> str:
        return self._name_edit.text().strip()

    def columns(self) -> list[str]:
        """The chosen columns, in the order the rows are in."""
        return self._column_picker.columns()

    def column_picker(self) -> _ColumnListPicker:
        """The "+"/"−" widget itself — the headless entry point for tests and
        for a caller that wants to pre-select a multi-column key."""
        return self._column_picker


class AddConstraintDialog(_AddConstraintDialogBase):
    """Add constraint: name, TYPE, and a definition whose *shape* the type picks.

    `PRIMARY KEY` and `UNIQUE` are defined by a column list, so the "+" picker
    is shown. `CHECK` and `EXCLUDE` are defined by an expression, so the picker
    is hidden and the free-SQL field takes its place — `EXCLUDE` additionally
    revealing the index-method dropdown. Rows are hidden rather than disabled
    because an inapplicable-but-visible column picker on a CHECK reads as "this
    CHECK constrains that column", which is not a thing.

    `EXCLUDE` is expression-shaped rather than column-shaped because its element
    list carries a per-element operator (`room WITH =, during WITH &&`) that no
    column picker can express; see `db/ddl_skeleton.EXPRESSION_CONSTRAINT_TYPES`.
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
            title="Add Constraint",
            parent=parent,
        )

    def _build_fields(self, form: QFormLayout) -> None:
        self._type_combo = QComboBox()
        self._type_combo.addItems(CONSTRAINT_TYPES)
        form.addRow("Type:", self._type_combo)
        super()._build_fields(form)
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        self._apply_type_visibility()

    def _build_extra_fields(self, form: QFormLayout) -> None:
        self._expression_edit = _user_typed_line_edit("qty > 0")
        form.addRow("Expression:", self._expression_edit)

        self._method_combo = QComboBox()
        self._method_combo.addItems(EXCLUDE_METHODS)
        form.addRow("Using method:", self._method_combo)

    def _change_signals(self) -> Sequence[object]:
        return (
            *super()._change_signals(),
            self._type_combo.currentTextChanged,
            self._expression_edit.textChanged,
            self._method_combo.currentTextChanged,
        )

    def _on_type_changed(self, *_args: object) -> None:
        self._apply_type_visibility()
        self._refresh_validation()

    def _apply_type_visibility(self) -> None:
        expression_shaped = self.constraint_type() in EXPRESSION_CONSTRAINT_TYPES
        self._form.setRowVisible(self._column_picker, not expression_shaped)
        self._form.setRowVisible(self._expression_edit, expression_shaped)
        self._form.setRowVisible(self._method_combo, self.constraint_type() == "EXCLUDE")

    # --- Getters --------------------------------------------------------------
    def constraint_type(self) -> str:
        return self._type_combo.currentText()

    def available_constraint_types(self) -> list[str]:
        return [self._type_combo.itemText(i) for i in range(self._type_combo.count())]

    def expression(self) -> str:
        """The user's own typed CHECK body / EXCLUDE element list."""
        return self._expression_edit.text().strip()

    def method(self) -> str:
        return self._method_combo.currentText()

    def _render_skeleton(self) -> str:
        if not self.constraint_name():
            raise SkeletonError("constraint name must not be empty")
        constraint_type = self.constraint_type()
        if constraint_type in EXPRESSION_CONSTRAINT_TYPES:
            return add_constraint_skeleton(
                table=self.table(),
                name=self.constraint_name(),
                constraint_type=constraint_type,
                expression=self.expression(),
                method=self.method(),
            )
        return add_constraint_skeleton(
            table=self.table(),
            name=self.constraint_name(),
            constraint_type=constraint_type,
            columns=self.columns(),
        )


class AddForeignKeyDialog(_AddConstraintDialogBase):
    """Add foreign key: the local column(s), plus a referenced table whose
    selection **repopulates** a referenced-column picker.

    Split out of `AddConstraintDialog` rather than added as a fifth TYPE
    because of exactly this second section: no other constraint type has a
    target. The two dialogs still share `_AddConstraintDialogBase` for the name
    and the local column picker, which are identical.
    """

    def __init__(
        self,
        *,
        table: str,
        column: str = "",
        tables: TableSource = (),
        columns: ColumnSource = (),
        ref_table: str = "",
        parent: QWidget | None = None,
    ) -> None:
        # Read by `_build_fields`, which the base constructor calls.
        self._initial_ref_table = ref_table
        super().__init__(
            table=table,
            column=column,
            tables=tables,
            columns=columns,
            title="Add Foreign Key",
            parent=parent,
        )

    def _columns_label(self) -> str:
        return "Local column(s):"

    def _build_extra_fields(self, form: QFormLayout) -> None:
        self._ref_table_combo = QComboBox()
        self._ref_table_combo.addItems(self._tables)
        if self._initial_ref_table and self._initial_ref_table in self._tables:
            self._ref_table_combo.setCurrentText(self._initial_ref_table)

        self._ref_column_picker = _ColumnListPicker()

        self._on_delete_combo = QComboBox()
        self._on_delete_combo.addItems((_NO_ACTION_CHOICE, *FK_ACTIONS))
        self._on_update_combo = QComboBox()
        self._on_update_combo.addItems((_NO_ACTION_CHOICE, *FK_ACTIONS))

        form.addRow("References table:", self._ref_table_combo)
        form.addRow("Referenced column(s):", self._ref_column_picker)
        form.addRow("ON DELETE:", self._on_delete_combo)
        form.addRow("ON UPDATE:", self._on_update_combo)

        self._reload_ref_columns()
        self._ref_table_combo.currentTextChanged.connect(self._on_ref_table_changed)

    def _change_signals(self) -> Sequence[object]:
        return (
            *super()._change_signals(),
            self._ref_column_picker.changed,
            self._on_delete_combo.currentTextChanged,
            self._on_update_combo.currentTextChanged,
        )

    def _reload_ref_columns(self) -> None:
        self._ref_column_picker.set_columns(self._columns_for(self.ref_table()))

    def _on_ref_table_changed(self, *_args: object) -> None:
        self._reload_ref_columns()
        self._refresh_validation()

    # --- Getters --------------------------------------------------------------
    def ref_table(self) -> str:
        return self._ref_table_combo.currentText()

    def ref_columns(self) -> list[str]:
        return self._ref_column_picker.columns()

    def ref_column_picker(self) -> _ColumnListPicker:
        return self._ref_column_picker

    def available_ref_columns(self) -> list[str]:
        """The referenced table's injected columns — what the repopulation
        produced."""
        return self._ref_column_picker.available_columns()

    def on_delete(self) -> str | None:
        return self._action_or_none(self._on_delete_combo)

    def on_update(self) -> str | None:
        return self._action_or_none(self._on_update_combo)

    @staticmethod
    def _action_or_none(combo: QComboBox) -> str | None:
        text = combo.currentText()
        return None if text == _NO_ACTION_CHOICE else text

    def _render_skeleton(self) -> str:
        if not self.constraint_name():
            raise SkeletonError("constraint name must not be empty")
        if not self.ref_table():
            raise SkeletonError("choose the table this foreign key references")
        return add_foreign_key_skeleton(
            table=self.table(),
            name=self.constraint_name(),
            columns=self.columns(),
            ref_table=self.ref_table(),
            ref_columns=self.ref_columns(),
            on_delete=self.on_delete(),
            on_update=self.on_update(),
        )


class _ExistingConstraintDialogBase(_AlterColumnDialogBase):
    """The typed picker of an **existing** constraint, shared by Drop and
    Rename.

    Both answer "which named constraint on this table?", which is a different
    question from the two `ADD`s' "what shall this new one contain?" — hence a
    separate base. The list follows the table dropdown, because a constraint
    name is only meaningful against its table.
    """

    _NEEDS_COLUMN = False

    def __init__(
        self,
        *,
        table: str,
        column: str = "",
        tables: TableSource = (),
        columns: ColumnSource = (),
        constraints: ConstraintSource = (),
        title: str = "Alter Table",
        parent: QWidget | None = None,
    ) -> None:
        # Read by `_build_fields` / `_reload_columns`, both of which the base
        # constructor calls.
        self._constraints_source = constraints
        self._constraint_entries: list[_Constraint] = []
        super().__init__(
            table=table,
            column=column,
            tables=tables,
            columns=columns,
            title=title,
            parent=parent,
        )

    def _build_fields(self, form: QFormLayout) -> None:
        self._constraint_combo = QComboBox()
        form.addRow("Constraint:", self._constraint_combo)
        self._build_extra_fields(form)

    def _build_extra_fields(self, form: QFormLayout) -> None:
        """Rows below the picker. Default: none."""

    def _change_signals(self) -> Sequence[object]:
        return (self._constraint_combo.currentIndexChanged,)

    def _reload_columns(self, select: str = "") -> None:
        super()._reload_columns(select=select)
        self._reload_constraints()

    def _constraints_for(self, table: str) -> list[_Constraint]:
        source = self._constraints_source
        if callable(source):
            entries: Sequence[Any] = source(table)
        elif isinstance(source, Mapping):
            entries = source.get(table, ())
        else:
            # A bare sequence describes the pre-bound table only — another
            # table borrowing it would list constraints that do not exist on it.
            entries = source if table == self._context_table else ()
        normalised = [_as_constraint(entry) for entry in entries]
        return [entry for entry in normalised if entry.name]

    def _reload_constraints(self) -> None:
        self._constraint_entries = self._constraints_for(self.table())
        combo = self._constraint_combo
        combo.blockSignals(True)
        combo.clear()
        for entry in self._constraint_entries:
            # The label carries the type; the *data* carries the bare name, so
            # what reaches the emitter is never the human-readable string.
            combo.addItem(entry.label, entry.name)
        combo.blockSignals(False)
        combo.setEnabled(bool(self._constraint_entries))

    # --- Getters --------------------------------------------------------------
    def constraint_name(self) -> str:
        """The selected constraint's bare name — never its typed label."""
        data = self._constraint_combo.currentData()
        return str(data) if data else ""

    def constraint_kind(self) -> str:
        entry = self.selected_constraint()
        return entry.kind if entry is not None else ""

    def selected_constraint(self) -> _Constraint | None:
        index = self._constraint_combo.currentIndex()
        if 0 <= index < len(self._constraint_entries):
            return self._constraint_entries[index]
        return None

    def constraint_labels(self) -> list[str]:
        """What the picker displays — each entry with its TYPE shown."""
        return [
            self._constraint_combo.itemText(i)
            for i in range(self._constraint_combo.count())
        ]

    def available_constraints(self) -> list[str]:
        """The selectable constraint names for the current table."""
        return [
            str(self._constraint_combo.itemData(i))
            for i in range(self._constraint_combo.count())
        ]

    def _render(self) -> tuple[str, str | None]:
        if not self.table():
            return "", "Choose the table to alter."
        if not self.constraint_name():
            return "", _NO_CONSTRAINTS_MESSAGE
        return super()._render()


class DropConstraintDialog(_ExistingConstraintDialogBase):
    """The one Drop, for every constraint type.

    There is no separate "Delete foreign key": in Postgres a FK *is* a
    constraint and the statement is identical, so the type lives in the picker's
    labels instead of in the menu.

    **It states, it does not refuse.** Dropping a primary key or a unique
    constraint also drops the index Postgres maintains for it, and may be
    blocked by other tables' foreign keys — but this dialog writes no statement
    to a database. It generates text into an editable tab whose execution is a
    separate, explicit gesture, and Postgres itself gives the authoritative
    answer at that moment. So a consequential choice gets a plain non-red note
    beside it and OK stays enabled: refusing here would only be guessing at
    dependencies this layer cannot see, and would block the legitimate case
    (drop the PK, then re-add it differently) that this whole feature exists to
    make possible. The same reasoning as slice 1's `DROP COLUMN`, which emits no
    `CASCADE` and blocks nothing.
    """

    def __init__(
        self,
        *,
        table: str,
        column: str = "",
        tables: TableSource = (),
        columns: ColumnSource = (),
        constraints: ConstraintSource = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            table=table,
            column=column,
            tables=tables,
            columns=columns,
            constraints=constraints,
            title="Drop Constraint",
            parent=parent,
        )

    def _build_extra_fields(self, form: QFormLayout) -> None:
        self._note_label = QLabel("")
        self._note_label.setWordWrap(True)
        form.addRow("", self._note_label)

    def _refresh_validation(self, *_args: object) -> None:
        super()._refresh_validation()
        # Deliberately *after* the base: the note is not an error, must not be
        # red, and must never gate OK.
        self._note_label.setText(self.note())

    def note(self) -> str:
        """A consequence worth stating, or `""`. Never a reason OK is disabled."""
        entry = self.selected_constraint()
        if entry is None:
            return ""
        kind = entry.kind.lower()
        if kind == "primary key":
            return (
                "This is the table's PRIMARY KEY. Dropping it also drops the "
                "index behind it, and Postgres will refuse if another table's "
                "foreign key still references it."
            )
        if entry.backs_an_index:
            return (
                f"This {kind.upper()} constraint owns an index, which is dropped "
                "with it."
            )
        return ""

    def _render_skeleton(self) -> str:
        return drop_constraint_skeleton(
            table=self.table(), name=self.constraint_name()
        )


class RenameConstraintDialog(_ExistingConstraintDialogBase):
    """Rename constraint: the typed picker plus a new name.

    Renaming to the current name is refused — by the emitter, whose message is
    what the red label shows — because Postgres errors on it.
    """

    def __init__(
        self,
        *,
        table: str,
        column: str = "",
        tables: TableSource = (),
        columns: ColumnSource = (),
        constraints: ConstraintSource = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            table=table,
            column=column,
            tables=tables,
            columns=columns,
            constraints=constraints,
            title="Rename Constraint",
            parent=parent,
        )

    def _build_extra_fields(self, form: QFormLayout) -> None:
        self._new_name_edit = QLineEdit()
        self._new_name_edit.setPlaceholderText("new_constraint_name")
        form.addRow("New name:", self._new_name_edit)

    def _change_signals(self) -> Sequence[object]:
        return (*super()._change_signals(), self._new_name_edit.textChanged)

    def new_name(self) -> str:
        return self._new_name_edit.text().strip()

    def _render_skeleton(self) -> str:
        if not self.new_name():
            raise SkeletonError("new constraint name must not be empty")
        return rename_constraint_skeleton(
            table=self.table(),
            name=self.constraint_name(),
            new_name=self.new_name(),
        )
