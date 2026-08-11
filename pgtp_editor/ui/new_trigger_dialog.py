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

# pgtp_editor/ui/new_trigger_dialog.py
"""The Add Trigger dialog (FQ-002) -- reached by right-clicking a **table or
view** node in the DDL Explorer, and the origin of a brand-new trigger.

Collects exactly the fields `CREATE TRIGGER` needs beyond the table itself:
name, timing, event(s), level, and the trigger function to attach.

Five deliberate constraints:

- **The target table is given, not chosen.** The right-clicked node already
  fixed it; re-offering it as a field would only invite disagreeing with the
  node the user clicked.
- **The target's KIND is given too, and it filters the timings**
  (DEC-260811025733). A table offers `BEFORE`/`AFTER`, a view offers
  `INSTEAD OF` and nothing else, and both lists come from
  `ddl_skeleton.trigger_timings_for_kind` rather than being decided here. This
  is PostgreSQL's split, not a preference: `INSTEAD OF` is only legal on a view
  and is the standard way to make one updatable, while `BEFORE`/`AFTER` are only
  legal on a table. Before the ruling this dialog never learned the kind and
  offered all three, so a view could be handed `BEFORE INSERT` -- a rendered,
  authoritative-looking statement the server rejects. A `"matview"` target has
  no legal timing at all and is refused outright here as a safety net; the tree
  does not offer the gesture on one in the first place.
- **Events are multi-select.** Postgres combines them with `OR`
  (`BEFORE INSERT OR UPDATE`), so this is a set of checkboxes rather than a
  one-of combo. At least one is required.
- **Every choice is driven off `db/ddl_skeleton.py`'s own constants**
  (`trigger_timings_for_kind` / `TRIGGER_EVENTS` / `TRIGGER_LEVELS`) rather than
  re-typed here, so the widgets and the emitter cannot drift apart. Notably
  there is no "for each transaction" level -- Postgres has none (the original
  FQ-002 request asked for it and was corrected).
- **Only existing trigger-returning functions are offered**, and they are
  *injected* by the caller -- this dialog opens no connection and introspects
  nothing (the same "never talks to a database" posture as
  `DdlObjectEditorPanel`). Inline "create a new function" is out of scope for
  v1. With no candidate at all the dialog says so plainly and blocks OK: there
  is genuinely nothing to attach, and a skeleton naming a function that does
  not exist would fail the moment it ran.

The function chooser reuses the flat, sorted, non-editable list of
`schema.function` strings that `DdlObjectEditorPanel`'s unattached-trigger
table picker established (`_prompt_unattached_trigger_table`, itself a
`QInputDialog.getItem` list) -- the same idiom, embedded as a combo box
because this one lives inside a larger form instead of standing alone.

Shown non-modally (`show()`, never `.exec()`), same convention as
`NewProjectDialog` / `ConnectionSetupDialog`: this dialog **persists nothing
and executes nothing**. The caller reads the fields (or the ready-rendered
`skeleton()`) back after `accepted` fires and opens the editor tab itself.

Nothing invalid can leave through `accept()`: OK stays disabled and an inline
message explains why, including for a hostile identifier -- `SkeletonError`
and `UnsafeIdentifierError` are caught and rendered as validation text rather
than escaping as a traceback.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.ddl_skeleton import (
    TRIGGER_EVENTS,
    TRIGGER_LEVELS,
    SkeletonError,
    trigger_skeleton,
    trigger_timings_for_kind,
)
from pgtp_editor.db.sandbox import UnsafeIdentifierError

#: Either the candidate names outright, or a callable producing them -- the
#: caller filters `introspect.RoutineInfo` down to `trigger`-returning
#: routines; this dialog never learns what a connection is.
FunctionSource = Sequence[str] | Callable[[], Sequence[str]]

_NO_FUNCTIONS_MESSAGE = (
    "No trigger functions exist in this database — a trigger can only attach to"
    " a function that RETURNS trigger. Create one first, then add the trigger."
)

#: The refusal for a target that can carry no trigger at whatever timing --
#: today only a materialized view. Stated, not crashed: the tree already keeps
#: the gesture off a matview node, so this is the safety net behind that gate
#: for any other way in (a caller wiring the dialog up itself, a future kind).
NO_TRIGGERS_MESSAGE = (
    "Materialized views cannot have triggers — PostgreSQL supports none on them."
)

#: What the read-only target row is called, per kind.
_TARGET_LABELS = {"table": "Table:", "view": "View:", "matview": "Materialized view:"}


class NewTriggerDialog(QDialog):
    def __init__(
        self,
        table: str,
        functions: FunctionSource = (),
        parent: QWidget | None = None,
        *,
        kind: str = "table",
    ) -> None:
        super().__init__(parent)
        self._table = table
        # `introspect.TableInfo.kind` verbatim. Keyword-only and defaulted to the
        # commonest and most restrictive case, so an existing two-argument call
        # keeps meaning "a table" rather than silently widening.
        self._kind = kind
        self._timings = trigger_timings_for_kind(kind)
        names = functions() if callable(functions) else functions
        # Sorted and de-duplicated: the same stable, flat presentation the
        # existing table picker uses.
        self._functions: list[str] = sorted(set(names))
        self.setWindowTitle("Add Trigger")

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._refresh_validation)

        self._timing_combo = QComboBox()
        self._timing_combo.addItems(self._timings)
        self._timing_combo.currentIndexChanged.connect(self._refresh_validation)
        if not self._timings:
            self._timing_combo.setEnabled(False)

        # One checkbox per canonical event, in the emitter's own order. The
        # emitter re-orders and de-duplicates anyway, so the checked set can be
        # handed over as-is.
        self._event_checks: dict[str, QCheckBox] = {}
        events_row = QHBoxLayout()
        for event in TRIGGER_EVENTS:
            check = QCheckBox(event)
            check.toggled.connect(self._refresh_validation)
            self._event_checks[event] = check
            events_row.addWidget(check)
        events_row.addStretch(1)

        self._level_combo = QComboBox()
        self._level_combo.addItems(TRIGGER_LEVELS)
        self._level_combo.currentIndexChanged.connect(self._refresh_validation)

        self._function_combo = QComboBox()
        self._function_combo.addItems(self._functions)
        self._function_combo.currentIndexChanged.connect(self._refresh_validation)
        if not self._functions:
            self._function_combo.setEnabled(False)

        form = QFormLayout()
        # The row names what was clicked: calling a view "Table:" while the only
        # timing on offer is `INSTEAD OF` would read as a mismatch.
        form.addRow(_TARGET_LABELS.get(kind, "Table:"), QLabel(table))
        form.addRow("Name:", self._name_edit)
        form.addRow("Timing:", self._timing_combo)
        form.addRow("Events:", events_row)
        form.addRow("Level:", self._level_combo)
        form.addRow("Trigger function:", self._function_combo)

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

        self._refresh_validation()

    # --- Getters (read after `accepted` fires) -------------------------------
    def table(self) -> str:
        """The target table, exactly as the caller handed it over."""
        return self._table

    def kind(self) -> str:
        """What the target is — `"table"` / `"view"` / `"matview"`, as handed
        over. Read by tests and by anything that needs to know why the timing
        list looks the way it does."""
        return self._kind

    def offered_timings(self) -> list[str]:
        """The timings this target may carry, i.e. what the combo holds. Empty
        for a materialized view."""
        return list(self._timings)

    def trigger_name(self) -> str:
        return self._name_edit.text().strip()

    def timing(self) -> str:
        return self._timing_combo.currentText()

    def events(self) -> list[str]:
        """The checked events, in `TRIGGER_EVENTS` (canonical) order."""
        return [
            event
            for event in TRIGGER_EVENTS
            if self._event_checks[event].isChecked()
        ]

    def level(self) -> str:
        return self._level_combo.currentText()

    def function_name(self) -> str:
        return self._function_combo.currentText() if self._functions else ""

    def candidate_functions(self) -> list[str]:
        """The injected candidates, sorted and de-duplicated."""
        return list(self._functions)

    def skeleton(self) -> str:
        """The `CREATE TRIGGER` text for the current field state, or `""` when
        that state is invalid (see `validation_error`). Rendered by
        `db/ddl_skeleton.py` -- no SQL is assembled here."""
        rendered, _ = self._render()
        return rendered

    def validation_error(self) -> str | None:
        """Why OK is disabled, or None when the current state is valid."""
        _, error = self._render()
        return error

    def is_valid(self) -> bool:
        return self.validation_error() is None

    # --- Validation ---------------------------------------------------------
    def _render(self) -> tuple[str, str | None]:
        """Render, or explain the refusal. Never raises: `SkeletonError` and
        `UnsafeIdentifierError` both become inline validation text."""
        # Ahead of every other check: with no legal timing there is no field
        # state that could become a statement, so nothing else is worth saying.
        if not self._timings:
            return "", NO_TRIGGERS_MESSAGE
        if not self._functions:
            return "", _NO_FUNCTIONS_MESSAGE
        if not self.trigger_name():
            return "", "Enter a name for the trigger."
        if not self.events():
            return "", "Select at least one event (INSERT, UPDATE or DELETE)."
        function_name = self.function_name()
        if not function_name:
            return "", "Choose the trigger function to attach."
        try:
            return (
                trigger_skeleton(
                    name=self.trigger_name(),
                    table=self._table,
                    timing=self.timing(),
                    events=self.events(),
                    level=self.level(),
                    function_name=function_name,
                    kind=self._kind,
                ),
                None,
            )
        except (SkeletonError, UnsafeIdentifierError) as exc:
            return "", str(exc)

    def _refresh_validation(self) -> None:
        error = self.validation_error()
        self._error_label.setText(error or "")
        ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(error is None)

    def _on_accept_clicked(self) -> None:
        # Belt-and-braces alongside the disabled OK button: a programmatic
        # click must not smuggle an invalid trigger past validation.
        if not self.is_valid():
            self._refresh_validation()
            return
        self.accept()
