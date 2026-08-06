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

"""Customize Toolbar dialog (Sub-project E).

Two lists -- Available (commands not on the toolbar) and On Toolbar (current,
in order) -- with Add / Remove / Up / Down buttons and OK / Cancel. The
mutating slots and the id accessors form the test seam; tests drive them
directly and never call `.exec()`.

FQ-004 added a per-row icon to the On-Toolbar list: each row shows the icon
that button will carry (assigned, or the command's built-in default), and
"Choose Icon…" / double-click opens `IconPickerDialog` over the vendored
Breeze catalog. The assignment map is `{command_id: icon_id}`, exposed through
`icon_assignments()` / `set_icon_assignments()` -- the same headless seam
`selected_ids()` / `set_ids()` provide for the id list, and `assign_icon()`
stands in for the picker so tests never `.exec()` anything.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from pgtp_editor.ui import icons
from pgtp_editor.ui.toolbar_registry import icon_id_for


class CustomizeToolbarDialog(QDialog):
    def __init__(self, available, current_ids, parent=None, icon_assignments=None):
        super().__init__(parent)
        self.setWindowTitle("Customize Toolbar")
        # All commands as (id, label); keep the registry order for the
        # Available list and label lookups.
        self._all = list(available)
        self._labels = {cid: label for cid, label in self._all}
        self._registry_order = [cid for cid, _label in self._all]
        # command_id -> catalog icon id. Absent == use the built-in default,
        # which is what keeps a pre-FQ-004 saved toolbar behaving unchanged.
        self._icon_assignments = dict(icon_assignments or {})

        layout = QVBoxLayout(self)
        lists_row = QHBoxLayout()
        self.available_list = QListWidget(self)
        self.toolbar_list = QListWidget(self)
        lists_row.addWidget(self.available_list)

        buttons_col = QVBoxLayout()
        self.add_button = QPushButton("Add →", self)
        self.remove_button = QPushButton("← Remove", self)
        self.up_button = QPushButton("Up", self)
        self.down_button = QPushButton("Down", self)
        self.icon_button = QPushButton("Choose Icon…", self)
        for btn in (
            self.add_button,
            self.remove_button,
            self.up_button,
            self.down_button,
            self.icon_button,
        ):
            buttons_col.addWidget(btn)
        buttons_col.addStretch(1)
        lists_row.addLayout(buttons_col)
        lists_row.addWidget(self.toolbar_list)
        layout.addLayout(lists_row)

        self.add_button.clicked.connect(self._add_selected)
        self.remove_button.clicked.connect(self._remove_selected)
        self.up_button.clicked.connect(self._move_up)
        self.down_button.clicked.connect(self._move_down)
        self.icon_button.clicked.connect(self._choose_icon)
        self.toolbar_list.itemDoubleClicked.connect(
            lambda _item: self._choose_icon()
        )

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.set_ids(current_ids)

    # -- list population -----------------------------------------------------

    def _make_item(self, command_id, with_icon=False):
        item = QListWidgetItem(self._labels.get(command_id, command_id))
        item.setData(Qt.ItemDataRole.UserRole, command_id)
        if with_icon:
            icon_id = self.effective_icon_id(command_id)
            if icon_id:
                item.setIcon(icons.themed_icon(icon_id, self._icon_color()))
        return item

    @staticmethod
    def _icon_color():
        """Tint the preview icons the same way the toolbar does -- the app
        palette's window-text color, so the preview matches the real button
        under either theme."""
        app = QApplication.instance()
        if app is None:
            return "#232629"
        return app.palette().color(QPalette.ColorRole.WindowText)

    def set_ids(self, ids):
        """Reset both lists: `ids` populate the On-Toolbar list in that order;
        Available lists EVERY command in registry order, with commands already
        on the toolbar shown disabled so they can't be added twice."""
        current = [cid for cid in ids if cid in self._labels]
        self.toolbar_list.clear()
        for cid in current:
            self.toolbar_list.addItem(self._make_item(cid, with_icon=True))
        current_set = set(current)
        self.available_list.clear()
        for cid in self._registry_order:
            item = self._make_item(cid)
            if cid in current_set:
                item.setFlags(
                    item.flags()
                    & ~Qt.ItemFlag.ItemIsEnabled
                    & ~Qt.ItemFlag.ItemIsSelectable
                )
            self.available_list.addItem(item)

    # -- accessors (test seam) -----------------------------------------------

    def _ids_of(self, list_widget):
        return [
            list_widget.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(list_widget.count())
        ]

    def selected_ids(self):
        """Ordered ids currently on the toolbar list."""
        return self._ids_of(self.toolbar_list)

    def _available_ids(self):
        return self._ids_of(self.available_list)

    def _available_enabled_ids(self):
        """Available ids whose item is enabled (i.e. addable -- not already on
        the toolbar). Test seam."""
        out = []
        for row in range(self.available_list.count()):
            item = self.available_list.item(row)
            if item.flags() & Qt.ItemFlag.ItemIsEnabled:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return out

    def result_ids(self):
        """The chosen ordered id list (== `selected_ids()`)."""
        return self.selected_ids()

    # -- icon assignments (test seam, FQ-004) --------------------------------

    def icon_assignments(self):
        """`{command_id: icon_id}` for the buttons the user gave an explicit
        icon. Commands still on their default are simply absent."""
        return dict(self._icon_assignments)

    def result_icon_assignments(self):
        """The assignment map to persist, pruned to commands actually on the
        toolbar (removing a button drops its assignment with it)."""
        on_toolbar = set(self.selected_ids())
        return {
            cid: icon_id
            for cid, icon_id in self._icon_assignments.items()
            if cid in on_toolbar
        }

    def set_icon_assignments(self, assignments):
        """Replace the whole assignment map and repaint the On-Toolbar rows."""
        self._icon_assignments = {
            cid: icon_id for cid, icon_id in dict(assignments or {}).items() if icon_id
        }
        self._refresh_toolbar_icons()

    def assign_icon(self, command_id, icon_id):
        """Assign `icon_id` to `command_id`, or clear the assignment (back to
        the command's default) when `icon_id` is falsy. This is what the picker
        calls -- and what tests call instead of opening it."""
        if icon_id:
            self._icon_assignments[command_id] = icon_id
        else:
            self._icon_assignments.pop(command_id, None)
        self._refresh_toolbar_icons()

    def effective_icon_id(self, command_id):
        """The icon this button will actually show: the assignment if any,
        else the built-in default, else None."""
        return icon_id_for(command_id, self._icon_assignments)

    def _refresh_toolbar_icons(self):
        for row in range(self.toolbar_list.count()):
            item = self.toolbar_list.item(row)
            cid = item.data(Qt.ItemDataRole.UserRole)
            icon_id = self.effective_icon_id(cid)
            if icon_id:
                item.setIcon(icons.themed_icon(icon_id, self._icon_color()))
            else:
                item.setIcon(QIcon())

    def _choose_icon(self):
        """Open the Breeze icon picker for the selected On-Toolbar row and
        apply its choice. Modal, and never reached from a test -- tests call
        `assign_icon` directly."""
        item = self.toolbar_list.currentItem()
        if item is None:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        # Imported here so the picker (and its catalog render) is only built
        # when the user actually asks for it.
        from pgtp_editor.ui.icon_picker_dialog import IconPickerDialog

        dialog = IconPickerDialog(
            self._icon_assignments.get(cid), self._icon_color(), self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.assign_icon(cid, dialog.chosen_icon_id())
        self._select_toolbar(cid)

    # -- selection helpers (test seam) ---------------------------------------

    def _select_in(self, list_widget, command_id):
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == command_id:
                list_widget.setCurrentRow(row)
                return
        list_widget.setCurrentRow(-1)

    def _select_available(self, command_id):
        self._select_in(self.available_list, command_id)

    def _select_toolbar(self, command_id):
        self._select_in(self.toolbar_list, command_id)

    # -- button slots --------------------------------------------------------

    def _add_selected(self):
        item = self.available_list.currentItem()
        if item is None:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid in set(self.selected_ids()):
            return
        self.set_ids(self.selected_ids() + [cid])
        self._select_toolbar(cid)

    def _remove_selected(self):
        item = self.toolbar_list.currentItem()
        if item is None:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        remaining = [c for c in self.selected_ids() if c != cid]
        self.set_ids(remaining)
        self._select_available(cid)

    def _move_up(self):
        row = self.toolbar_list.currentRow()
        if row <= 0:
            return
        ids = self.selected_ids()
        ids[row - 1], ids[row] = ids[row], ids[row - 1]
        moved = ids[row - 1]
        self.set_ids(ids)
        self._select_toolbar(moved)

    def _move_down(self):
        row = self.toolbar_list.currentRow()
        if row < 0 or row >= self.toolbar_list.count() - 1:
            return
        ids = self.selected_ids()
        ids[row], ids[row + 1] = ids[row + 1], ids[row]
        moved = ids[row + 1]
        self.set_ids(ids)
        self._select_toolbar(moved)
