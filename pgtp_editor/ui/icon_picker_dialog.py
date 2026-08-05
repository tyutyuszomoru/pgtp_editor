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

"""Breeze icon picker (FQ-004).

A searchable grid over the vendored Breeze catalog (`icons.icon_catalog`),
plus a leading "Default" cell that clears any assignment. Every cell is
rendered through the normal `icons.themed_icon` pipeline, so the picker shows
exactly the tinted artwork the toolbar will show.

Test seam, mirroring `CustomizeToolbarDialog`: `set_filter`,
`visible_icon_ids`, `select_icon`, `chosen_icon_id`. Tests drive those and
never call `.exec()`.
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from pgtp_editor.ui import icons

#: Sentinel used by the "Default" cell -- choosing it means "no assignment",
#: i.e. fall back to the command's built-in icon (or to no icon at all).
DEFAULT_CHOICE = None

_DEFAULT_ROLE_VALUE = "\x00default"


class IconPickerDialog(QDialog):
    def __init__(self, current_icon_id=None, color=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Icon")
        self._color = color if color is not None else self._default_color()
        self._chosen = current_icon_id or DEFAULT_CHOICE

        layout = QVBoxLayout(self)
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Search icons…")
        self.search_edit.setClearButtonEnabled(True)
        layout.addWidget(self.search_edit)

        self.icon_list = QListWidget(self)
        self.icon_list.setViewMode(QListView.ViewMode.IconMode)
        self.icon_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.icon_list.setMovement(QListView.Movement.Static)
        self.icon_list.setIconSize(QSize(22, 22))
        self.icon_list.setGridSize(QSize(110, 64))
        self.icon_list.setWordWrap(True)
        self.icon_list.setUniformItemSizes(True)
        layout.addWidget(self.icon_list)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.search_edit.textChanged.connect(self.set_filter)
        self.icon_list.currentItemChanged.connect(self._on_current_changed)
        self.icon_list.itemDoubleClicked.connect(self._on_double_clicked)

        self.resize(560, 420)
        self.set_filter("")

    # -- rendering -----------------------------------------------------------

    @staticmethod
    def _default_color():
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return "#232629"
        return app.palette().color(QPalette.ColorRole.WindowText)

    # -- population (test seam) ----------------------------------------------

    def set_filter(self, text):
        """Repopulate the grid with the catalog entries matching `text`. The
        "Default" cell is always present, first."""
        previous = self._chosen
        self.icon_list.blockSignals(True)
        try:
            self.icon_list.clear()
            default_item = QListWidgetItem("Default")
            default_item.setData(
                Qt.ItemDataRole.UserRole, _DEFAULT_ROLE_VALUE
            )
            default_item.setToolTip(
                "Use this command's built-in icon, or none if it has none"
            )
            self.icon_list.addItem(default_item)
            for icon_id, _filename, label in icons.search_catalog(text):
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, icon_id)
                item.setToolTip(icon_id)
                item.setIcon(icons.themed_icon(icon_id, self._color))
                self.icon_list.addItem(item)
        finally:
            self.icon_list.blockSignals(False)
        self._chosen = previous
        self.select_icon(previous)

    def visible_icon_ids(self):
        """Catalog ids currently listed, excluding the "Default" cell."""
        out = []
        for row in range(self.icon_list.count()):
            value = self.icon_list.item(row).data(Qt.ItemDataRole.UserRole)
            if value != _DEFAULT_ROLE_VALUE:
                out.append(value)
        return out

    def has_default_choice(self):
        """True when the reset-to-default cell is offered (it always is)."""
        for row in range(self.icon_list.count()):
            if (
                self.icon_list.item(row).data(Qt.ItemDataRole.UserRole)
                == _DEFAULT_ROLE_VALUE
            ):
                return True
        return False

    # -- selection (test seam) -----------------------------------------------

    def select_icon(self, icon_id):
        """Select the cell for `icon_id` (None -> the Default cell). A no
        longer visible id falls back to Default."""
        wanted = _DEFAULT_ROLE_VALUE if not icon_id else icon_id
        for row in range(self.icon_list.count()):
            item = self.icon_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == wanted:
                self.icon_list.setCurrentRow(row)
                self._chosen = icon_id or DEFAULT_CHOICE
                return
        self.icon_list.setCurrentRow(0)
        self._chosen = DEFAULT_CHOICE

    def chosen_icon_id(self):
        """The picked catalog icon id, or `DEFAULT_CHOICE` (None) for the
        reset-to-default cell."""
        return self._chosen

    # -- slots ---------------------------------------------------------------

    def _on_current_changed(self, current, _previous=None):
        if current is None:
            return
        value = current.data(Qt.ItemDataRole.UserRole)
        self._chosen = DEFAULT_CHOICE if value == _DEFAULT_ROLE_VALUE else value

    def _on_double_clicked(self, item):
        self._on_current_changed(item)
        self.accept()
