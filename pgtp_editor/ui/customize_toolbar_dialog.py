"""Customize Toolbar dialog (Sub-project E).

Two lists -- Available (commands not on the toolbar) and On Toolbar (current,
in order) -- with Add / Remove / Up / Down buttons and OK / Cancel. The
mutating slots and the id accessors form the test seam; tests drive them
directly and never call `.exec()`.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class CustomizeToolbarDialog(QDialog):
    def __init__(self, available, current_ids, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize Toolbar")
        # All commands as (id, label); keep the registry order for the
        # Available list and label lookups.
        self._all = list(available)
        self._labels = {cid: label for cid, label in self._all}
        self._registry_order = [cid for cid, _label in self._all]

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
        for btn in (self.add_button, self.remove_button, self.up_button, self.down_button):
            buttons_col.addWidget(btn)
        buttons_col.addStretch(1)
        lists_row.addLayout(buttons_col)
        lists_row.addWidget(self.toolbar_list)
        layout.addLayout(lists_row)

        self.add_button.clicked.connect(self._add_selected)
        self.remove_button.clicked.connect(self._remove_selected)
        self.up_button.clicked.connect(self._move_up)
        self.down_button.clicked.connect(self._move_down)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.set_ids(current_ids)

    # -- list population -----------------------------------------------------

    def _make_item(self, command_id):
        item = QListWidgetItem(self._labels.get(command_id, command_id))
        item.setData(Qt.ItemDataRole.UserRole, command_id)
        return item

    def set_ids(self, ids):
        """Reset both lists from an ordered id list: `ids` populate the
        On-Toolbar list in that order; the rest fill Available in registry
        order."""
        current = [cid for cid in ids if cid in self._labels]
        self.toolbar_list.clear()
        for cid in current:
            self.toolbar_list.addItem(self._make_item(cid))
        current_set = set(current)
        self.available_list.clear()
        for cid in self._registry_order:
            if cid not in current_set:
                self.available_list.addItem(self._make_item(cid))

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

    def result_ids(self):
        """The chosen ordered id list (== `selected_ids()`)."""
        return self.selected_ids()

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
        # Move the current On-Toolbar list to include the selected id, keeping
        # Available as the registry-ordered complement.
        cid = item.data(Qt.ItemDataRole.UserRole)
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
