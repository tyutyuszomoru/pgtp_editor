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

# pgtp_editor/ui/new_routine_dialog.py
"""The New Function/Procedure dialog (FQ-002, §18.1/§18.5).

**One dialog, kind as a field inside it** -- not two near-identical dialogs.
Reachable both from a right-click on the DDL Explorer's "Functions &
Procedures" branch and from the Database menu; neither entry point needs a
different dialog, because unlike a trigger a routine is not scoped to a
particular table.

Three fields only: **name**, **kind** (Function / Procedure) and **return
datatype**. There is deliberately no language picker (`LANGUAGE plpgsql` is
the default and the only v1 option -- this is a plpgsql IDE) and no
parameter-list editor; the user fills the signature in the editor tab, which
is already a SQL editor with §18.6 schema-aware completion.

The return-datatype field is **function-only, and hidden when Procedure is
selected -- not merely left optional**. `CREATE PROCEDURE` has no `RETURNS`
clause in Postgres at all (procedures use `OUT` parameters or return
nothing), so a procedure carrying a return type is a syntax error rather
than a tolerable input, and the kind switch calls
`procedure_skeleton` -- which takes no return type by construction -- rather
than passing a flag down.

The datatype input is an **editable** combo seeded with the common cases so
`trigger` (the headline FQ-002 flow: create a trigger function, then attach a
trigger to it) is one click, while `numeric(10,2)`, `integer[]` or
`pr.my_domain` remain typable -- the renderer's own allowlist accepts those
forms and refuses quotes/semicolons/dollar signs.

**No SQL is written here.** `db/ddl_skeleton.py` renders it; this dialog only
collects fields and calls the right renderer. Both refusals it can raise
(`SkeletonError`, `sandbox.UnsafeIdentifierError`) are surfaced as inline
validation with OK disabled, never as an escaping exception or a modal error
box.

Shown non-modally (`show()`, never `.exec()`), same convention as
`NewProjectDialog` / `ProjectSettingsDialog`: this dialog **persists nothing
and executes nothing**. The caller reads `routine_name()` / `kind()` /
`return_type()` / `skeleton()` back after `accepted` fires and does the tab
opening and manifest bookkeeping itself.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
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
    function_skeleton,
    procedure_skeleton,
)
from pgtp_editor.db.sandbox import UnsafeIdentifierError

#: The two kinds, in `DdlObjectRef.kind` spelling (lowercase) so the caller can
#: hand the value straight to `CenterStage.open_ddl_object_tab` without a
#: second mapping table.
KIND_FUNCTION = "function"
KIND_PROCEDURE = "procedure"

#: Seeded return types. `trigger` leads deliberately -- creating a trigger
#: function to hang a trigger off is the headline FQ-002 flow. The list is a
#: convenience, not a constraint: the combo is editable and any type the
#: renderer's allowlist accepts can be typed.
COMMON_RETURN_TYPES = (
    "trigger",
    "void",
    "boolean",
    "integer",
    "bigint",
    "numeric",
    "text",
    "jsonb",
    "date",
    "timestamptz",
    "uuid",
    "record",
)


class NewRoutineDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Function/Procedure")

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("my_function  (or schema.my_function)")

        self._kind_combo = QComboBox()
        self._kind_combo.addItem("Function", KIND_FUNCTION)
        self._kind_combo.addItem("Procedure", KIND_PROCEDURE)

        self._return_type_combo = QComboBox()
        self._return_type_combo.setEditable(True)
        self._return_type_combo.addItems(COMMON_RETURN_TYPES)
        self._return_type_combo.setCurrentText("trigger")

        form = QFormLayout()
        form.addRow("Name:", self._name_edit)
        form.addRow("Kind:", self._kind_combo)
        # Kept as attributes so the whole row (label included) can be hidden --
        # a stranded "Returns:" label next to nothing would read as a bug.
        self._return_type_label = QLabel("Returns:")
        form.addRow(self._return_type_label, self._return_type_combo)
        self._form = form

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: red;")
        self._error_label.setWordWrap(True)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_accept_clicked)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error_label)
        layout.addWidget(self._buttons)

        self._name_edit.textChanged.connect(self._revalidate)
        self._kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        self._return_type_combo.currentTextChanged.connect(self._revalidate)

        self._on_kind_changed()

        # Opening size only (BUG-036): freely resizable afterwards, hence
        # `resize()` and not `setFixedSize`. 200px is 37px more than the layout's
        # 163px minimum, and the slack lands on the word-wrapping error label
        # (a `QVBoxLayout` gives spare height to the only expanding item), so a
        # validation message wraps into space that already exists instead of
        # pushing the OK/Cancel box below the fold.
        self.resize(560, 200)

    # --- Kind switching -------------------------------------------------------
    def _on_kind_changed(self, *_args: object) -> None:
        """Show the return-type row for a function; hide **and** disable it for
        a procedure. Hiding alone would leave a stale value reachable through
        the accessor; disabling alone would leave a field on screen that cannot
        legally be filled."""
        is_function = self.kind() == KIND_FUNCTION
        self._return_type_label.setVisible(is_function)
        self._return_type_combo.setVisible(is_function)
        self._return_type_combo.setEnabled(is_function)
        self._revalidate()

    # --- Validation -----------------------------------------------------------
    def validation_error(self) -> str | None:
        """`None` when the current field state renders; otherwise the message
        shown inline. Implemented by *asking the renderer* rather than
        re-deriving its rules here -- a second copy of the identifier and
        datatype allowlists would drift from `db/ddl_skeleton.py`."""
        if not self.routine_name().strip():
            return "Enter a name for the new routine."
        if self.kind() == KIND_FUNCTION and not self.return_type().strip():
            return "A function needs a return type."
        try:
            self._render()
        except UnsafeIdentifierError as exc:
            return f"Not a usable Postgres identifier: {exc}"
        except SkeletonError as exc:
            return str(exc)
        return None

    def _revalidate(self, *_args: object) -> None:
        error = self.validation_error()
        # Empty fields are a not-yet-filled form, not a mistake to scold about;
        # the disabled OK button already communicates "not ready".
        self._error_label.setText("" if error is None or self._is_blank() else error)
        ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(error is None)

    def _is_blank(self) -> bool:
        if not self.routine_name().strip():
            return True
        return self.kind() == KIND_FUNCTION and not self.return_type().strip()

    def _on_accept_clicked(self) -> None:
        if self.validation_error() is not None:
            self._revalidate()
            return
        self.accept()

    # --- Getters (read after `accepted` fires) --------------------------------
    def routine_name(self) -> str:
        return self._name_edit.text()

    def kind(self) -> str:
        """`"function"` or `"procedure"` -- `DdlObjectRef.kind` spelling."""
        return self._kind_combo.currentData()

    def return_type(self) -> str:
        """The typed return type, or `""` for a procedure -- a procedure has no
        return type *by definition*, so the accessor reports none regardless of
        what the (hidden) combo happens to still hold."""
        if self.kind() != KIND_FUNCTION:
            return ""
        return self._return_type_combo.currentText()

    def skeleton(self) -> str:
        """The rendered `CREATE` text for the current field state.

        Raises `SkeletonError` / `UnsafeIdentifierError` for input
        `validation_error()` would have rejected, so a caller that checked the
        dialog was accepted never sees them.
        """
        return self._render()

    def _render(self) -> str:
        if self.kind() == KIND_PROCEDURE:
            return procedure_skeleton(name=self.routine_name().strip())
        return function_skeleton(
            name=self.routine_name().strip(),
            return_type=self.return_type().strip(),
        )
