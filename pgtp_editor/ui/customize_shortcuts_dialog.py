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

# pgtp_editor/ui/customize_shortcuts_dialog.py
"""The "Customize Shortcuts…" dialog (FQ-012) — View menu, sibling to
"Customize Toolbar…".

One table row per menu command, showing where the command lives
(`menu_path_label()`'s `"File › Discard Changes"`), its current key and its
built-in default, plus a greyed block of **reserved** rows for the keys the
app pins (FQ-012 settled decision 1: shown read-only so the user can see they
exist and why they are locked, rather than silently missing).

Four rules carried from the current house style
(`customize_toolbar_dialog.py`, `alter_column_dialogs.py`):

- **The command list is INJECTED.** This dialog never touches a `QMenuBar`.
  The host already walks it (`ToolbarController.collect_menu_commands()` /
  `_walk_menu_actions`) and hands the result in as plain
  `shortcut_registry.CommandBinding` data, which is what lets the whole thing
  be tested with stub rows and no window.
- **Shown non-modally** (`show()`, never `.exec()`), with the caller reading
  `result_overrides()` back after `accepted` fires and doing the
  `QAction.setShortcut()` pass itself. Nothing here writes QSettings, and
  nothing here holds a QAction.
- **Every mutation has a programmatic seam** — `set_binding`, `clear_binding`,
  `reset_to_default`, `restore_all_defaults` — so tests drive the dialog
  without a key-capture gesture, the way `assign_icon` stands in for the icon
  picker.
- **All the rules are in `shortcut_registry`, none of them here.** Conflict
  detection, the steal, the reserved tables and the persistence shape are pure
  functions in that module; this file is the widget that calls them.

**The conflict interaction, concretely** (FQ-012 settled decision 2, "warn +
reassign (steal), user's choice"): `conflict_message()` is what the inline
label shows *before* anything is committed, naming the command that currently
holds the key; committing calls `set_binding`, which returns the ids it stole
so the caller can say so. A **refusal** (`refusal_message()`) is different and
is not overridable — the dialog owns menu QActions only and cannot clear a
window-scoped `QShortcut`, so those keys are simply not available as targets.
Both exist because Qt answers an ambiguous shortcut by firing **neither**
action; see the `shortcut_registry` docstring.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pgtp_editor.ui.shortcut_registry import (
    RESERVED_BINDINGS,
    RESERVED_COMMAND_IDS,
    CommandBinding,
    ReservedBinding,
    assign_shortcut,
    commands_holding,
    default_bindings,
    is_rebindable,
    normalize_sequence,
    overrides_for,
    refusal_for,
    resolve_bindings,
)

#: Column indices of the one table.
COLUMN_COMMAND = 0
COLUMN_SHORTCUT = 1
COLUMN_NOTE = 2

#: Marks a reserved (read-only) row so the accessors can skip it. Reserved rows
#: carry no command id -- they are not commands.
_ROW_KIND_ROLE = Qt.ItemDataRole.UserRole + 1


class CustomizeShortcutsDialog(QDialog):
    """`commands` are the editable rows, injected; `overrides` is the saved
    `{command_id: sequence}` map (absent == on its default); `reserved` are the
    read-only rows, defaulting to what §27 pins.

    Accepts `CommandBinding`s or bare `(command_id, label, default_sequence)`
    tuples, so a caller that has not built the dataclass yet still works.
    """

    def __init__(
        self,
        commands: Sequence[CommandBinding | tuple],
        overrides: Mapping[str, str] | None = None,
        parent=None,
        reserved: Sequence[ReservedBinding] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Customize Shortcuts")

        self._commands: list[CommandBinding] = [
            item if isinstance(item, CommandBinding) else CommandBinding(*item)
            for item in commands
        ]
        self._labels = {cmd.command_id: cmd.label for cmd in self._commands}
        self._defaults = default_bindings(self._commands)
        # Copied, never aliased: cancelling must leave the caller's map exactly
        # as it was, and the caller keeps holding the dict it passed in.
        self._bindings = resolve_bindings(self._commands, dict(overrides or {}))
        self._reserved = list(
            RESERVED_BINDINGS if reserved is None else reserved
        )

        layout = QVBoxLayout(self)
        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Command", "Shortcut", "Note"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            COLUMN_COMMAND, QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            COLUMN_NOTE, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)

        capture_row = QHBoxLayout()
        self.key_edit = QKeySequenceEdit(self)
        capture_row.addWidget(QLabel("New shortcut:", self))
        capture_row.addWidget(self.key_edit)
        self.assign_button = QPushButton("Assign", self)
        self.clear_button = QPushButton("Clear", self)
        self.reset_button = QPushButton("Reset to Default", self)
        self.restore_all_button = QPushButton("Restore All Defaults", self)
        for button in (
            self.assign_button,
            self.clear_button,
            self.reset_button,
            self.restore_all_button,
        ):
            capture_row.addWidget(button)
        layout.addLayout(capture_row)

        # The inline conflict/refusal line -- the "flag it BEFORE commit" half
        # of FQ-012's warn-and-steal rule.
        self.message_label = QLabel("", self)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.assign_button.clicked.connect(self._assign_from_capture)
        self.clear_button.clicked.connect(self._clear_current)
        self.reset_button.clicked.connect(self._reset_current)
        self.restore_all_button.clicked.connect(self.restore_all_defaults)
        self.table.currentCellChanged.connect(
            lambda *_args: self._on_row_changed()
        )
        self.key_edit.keySequenceChanged.connect(
            lambda *_args: self._refresh_message()
        )

        self._populate()

    # -- table population ----------------------------------------------------

    def _populate(self) -> None:
        self.table.setRowCount(len(self._commands) + len(self._reserved))
        for row, command in enumerate(self._commands):
            # A command §27 pins (Manual/F1) is enumerated by the menu walk like
            # any other, so it HAS a row -- but the row is read-only for the
            # same reason the reserved-key rows below are: showing it locked is
            # honest, hiding it looks like an incomplete list.
            rebindable = is_rebindable(command.command_id)
            label_item = QTableWidgetItem(command.label)
            label_item.setData(Qt.ItemDataRole.UserRole, command.command_id)
            label_item.setData(
                _ROW_KIND_ROLE, "command" if rebindable else "reserved"
            )
            self.table.setItem(row, COLUMN_COMMAND, label_item)
            self.table.setItem(
                row,
                COLUMN_SHORTCUT,
                QTableWidgetItem(self._bindings.get(command.command_id, "")),
            )
            self.table.setItem(row, COLUMN_NOTE, QTableWidgetItem(self._note(command)))
            if not rebindable:
                for column in (COLUMN_COMMAND, COLUMN_SHORTCUT, COLUMN_NOTE):
                    item = self.table.item(row, column)
                    item.setFlags(
                        item.flags()
                        & ~Qt.ItemFlag.ItemIsEnabled
                        & ~Qt.ItemFlag.ItemIsSelectable
                    )
        for offset, entry in enumerate(self._reserved):
            row = len(self._commands) + offset
            for column, text in (
                (COLUMN_COMMAND, "(reserved)"),
                (COLUMN_SHORTCUT, entry.sequence),
                (COLUMN_NOTE, entry.reason),
            ):
                item = QTableWidgetItem(text)
                item.setData(_ROW_KIND_ROLE, "reserved")
                # Greyed and unselectable: there is nothing to do to this row.
                item.setFlags(
                    item.flags()
                    & ~Qt.ItemFlag.ItemIsEnabled
                    & ~Qt.ItemFlag.ItemIsSelectable
                )
                self.table.setItem(row, column, item)

    def _note(self, command: CommandBinding) -> str:
        reason = RESERVED_COMMAND_IDS.get(command.command_id)
        if reason:
            return f"reserved — {reason}"
        default = self._defaults.get(command.command_id, "")
        current = self._bindings.get(command.command_id, "")
        if current == default:
            return ""
        return f"default: {default}" if default else "default: (none)"

    def _refresh_rows(self) -> None:
        for row, command in enumerate(self._commands):
            self.table.item(row, COLUMN_SHORTCUT).setText(
                self._bindings.get(command.command_id, "")
            )
            self.table.item(row, COLUMN_NOTE).setText(self._note(command))

    # -- accessors (test seam) -----------------------------------------------

    def command_ids(self) -> list[str]:
        """The editable command ids, in injected order."""
        return [command.command_id for command in self._commands]

    def reserved_sequences(self) -> list[str]:
        """The read-only rows' key sequences, in table order."""
        return [entry.sequence for entry in self._reserved]

    def bindings(self) -> dict[str, str]:
        """Every editable command's current binding (`""` == unbound)."""
        return dict(self._bindings)

    def binding_of(self, command_id: str) -> str:
        return self._bindings.get(command_id, "")

    def result_overrides(self) -> dict[str, str]:
        """The map to persist: only the commands that differ from their
        captured default. Read after `accepted`."""
        return overrides_for(self._commands, self._bindings)

    def current_command_id(self) -> str | None:
        """The command id of the selected row, or None (a reserved row cannot
        be selected, so this is None for those)."""
        item = self.table.item(self.table.currentRow(), COLUMN_COMMAND)
        if item is None or item.data(_ROW_KIND_ROLE) != "command":
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def select_command(self, command_id: str) -> None:
        """Select a command's row by id. Test seam and the post-mutation
        re-selection helper, mirroring `_select_toolbar`."""
        for row, command in enumerate(self._commands):
            if command.command_id == command_id:
                self.table.setCurrentCell(row, COLUMN_COMMAND)
                return
        self.table.setCurrentCell(-1, COLUMN_COMMAND)

    # -- the two pre-commit messages -----------------------------------------

    def refusal_message(self, command_id: str, sequence: str) -> str | None:
        """Why this assignment cannot be made at all, or None. Not
        overridable -- see the module docstring."""
        return refusal_for(command_id, sequence)

    def conflict_message(self, command_id: str, sequence: str) -> str | None:
        """"`Ctrl+S` is already bound to `Save`" — shown BEFORE the user
        commits, so the steal is a choice rather than a surprise. None when the
        key is free."""
        holders = commands_holding(self._bindings, sequence, exclude=command_id)
        if not holders:
            return None
        names = ", ".join(self._labels.get(cid, cid) for cid in holders)
        normalized = normalize_sequence(sequence)
        return (
            f"{normalized} is already bound to {names}. Assigning it here "
            f"will clear that binding."
        )

    # -- mutations (test seam) -----------------------------------------------

    def set_binding(self, command_id: str, sequence: str) -> list[str]:
        """Bind `sequence` to `command_id`, stealing it from whoever holds it,
        and return the ids it was stolen from (empty when the key was free).

        Raises `ValueError` for a refused assignment; `refusal_message` is how
        the UI avoids ever reaching that.
        """
        self._bindings, stolen = assign_shortcut(
            self._bindings, command_id, sequence
        )
        self._refresh_rows()
        return stolen

    def clear_binding(self, command_id: str) -> None:
        """Leave the command with no key at all — a legitimate state, and what
        the loser of a steal is left in."""
        self.set_binding(command_id, "")

    def reset_to_default(self, command_id: str) -> list[str]:
        """Put one command back on its captured default (stealing it back if
        another command has since taken that key)."""
        return self.set_binding(command_id, self._defaults.get(command_id, ""))

    def restore_all_defaults(self) -> None:
        """Every command back on the binding it was built with, so
        `result_overrides()` becomes empty."""
        self._bindings = dict(self._defaults)
        self._refresh_rows()
        self.message_label.setText("")

    # -- widget slots (never reached from a test) ----------------------------

    def _assign_from_capture(self) -> None:
        command_id = self.current_command_id()
        if command_id is None:
            return
        sequence = self.key_edit.keySequence().toString()
        refusal = self.refusal_message(command_id, sequence)
        if refusal:
            self.message_label.setText(refusal)
            return
        stolen = self.set_binding(command_id, sequence)
        if stolen:
            names = ", ".join(self._labels.get(cid, cid) for cid in stolen)
            self.message_label.setText(f"Cleared the binding of {names}.")
        else:
            self.message_label.setText("")
        self.select_command(command_id)

    def _clear_current(self) -> None:
        command_id = self.current_command_id()
        if command_id is None:
            return
        refusal = self.refusal_message(command_id, "")
        if refusal:
            self.message_label.setText(refusal)
            return
        self.clear_binding(command_id)
        self.select_command(command_id)

    def _reset_current(self) -> None:
        command_id = self.current_command_id()
        if command_id is None:
            return
        self.reset_to_default(command_id)
        self.select_command(command_id)

    def _on_row_changed(self) -> None:
        command_id = self.current_command_id()
        if command_id is None:
            self.key_edit.clear()
            self.message_label.setText("")
            return
        self.key_edit.setKeySequence(self.binding_of(command_id))
        self._refresh_message()

    def _refresh_message(self) -> None:
        command_id = self.current_command_id()
        if command_id is None:
            return
        sequence = self.key_edit.keySequence().toString()
        message = self.refusal_message(
            command_id, sequence
        ) or self.conflict_message(command_id, sequence)
        self.message_label.setText(message or "")
