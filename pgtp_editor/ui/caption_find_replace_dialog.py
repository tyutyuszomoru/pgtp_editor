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

# pgtp_editor/ui/caption_find_replace_dialog.py
"""CaptionFindReplaceDialog: one reusable, Notepad++-style Find/Filter/Replace
dialog for the Caption grid (Phase 4).

Two roles selected at construction via ``replace_enabled``:

* **Filter mode** (``replace_enabled=False``, Tools -> Caption Filter…): only
  Find-what + Search Mode + Match case + Filter/Close. The Filter button pushes
  the pattern to the grid via the injected ``on_filter(pattern, mode, case)``.
* **Replace mode** (``replace_enabled=True``, Ctrl+R): additionally shows the
  Replace-with field, the Scope radios, and a Replace All button, which invokes
  ``on_replace_all(find, replacement, mode, case, in_selection)``.

All behavior lives in ``_do_filter`` / ``_do_replace_all``; tests set the field
widgets and call those directly — NO test calls ``.exec()``. Invalid regex is
caught and shown as inline (non-blocking) error text, never a modal.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from pgtp_editor.ui.caption_scan import SEARCH_MODES

# Search-mode radio labels, in display order, paired with the caption_scan mode.
_MODE_LABELS: tuple[tuple[str, str], ...] = (
    ("Normal (plain string)", "normal"),
    ("Extended (\\n \\t \\0 \\xNN)", "extended"),
    ("Regular expression", "regular"),
)


class CaptionFindReplaceDialog(QDialog):
    def __init__(
        self,
        on_filter: Callable[[str, str, bool], None],
        on_replace_all: Callable[[str, str, str, bool, bool], None] | None = None,
        replace_enabled: bool = False,
        initial_find: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._on_filter = on_filter
        self._on_replace_all = on_replace_all or (lambda *args: None)
        self._replace_enabled = replace_enabled
        self.setWindowTitle("Caption Replace" if replace_enabled else "Caption Filter")

        layout = QVBoxLayout(self)

        # -- Find what / Replace with fields -------------------------------
        find_row = QHBoxLayout()
        find_row.addWidget(QLabel("Find what:"))
        self.find_field = QLineEdit(initial_find)
        find_row.addWidget(self.find_field)
        layout.addLayout(find_row)

        self._replace_row_widgets: list = []
        replace_row = QHBoxLayout()
        self._replace_label = QLabel("Replace with:")
        self.replace_field = QLineEdit()
        replace_row.addWidget(self._replace_label)
        replace_row.addWidget(self.replace_field)
        layout.addLayout(replace_row)
        if not replace_enabled:
            self._replace_label.setVisible(False)
            self.replace_field.setVisible(False)
            self.replace_field.setEnabled(False)

        # -- Search Mode radios --------------------------------------------
        mode_box = QGroupBox("Search Mode")
        mode_layout = QVBoxLayout(mode_box)
        self._mode_group = QButtonGroup(self)
        self._mode_buttons: dict[str, QRadioButton] = {}
        for label, mode in _MODE_LABELS:
            button = QRadioButton(label)
            self._mode_group.addButton(button)
            mode_layout.addWidget(button)
            self._mode_buttons[mode] = button
        self._mode_buttons["normal"].setChecked(True)
        layout.addWidget(mode_box)

        # -- Match case ----------------------------------------------------
        self.match_case_checkbox = QCheckBox("Match case")
        layout.addWidget(self.match_case_checkbox)

        # -- Scope radios (Replace mode only) ------------------------------
        self._scope_box = QGroupBox("Scope")
        scope_layout = QVBoxLayout(self._scope_box)
        self.in_selection_radio = QRadioButton("In selection (filtered rows)")
        self.global_radio = QRadioButton("Global (all rows)")
        self.in_selection_radio.setChecked(True)  # default In selection
        scope_layout.addWidget(self.in_selection_radio)
        scope_layout.addWidget(self.global_radio)
        layout.addWidget(self._scope_box)
        self._scope_box.setVisible(replace_enabled)

        # -- Inline (non-blocking) error label -----------------------------
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #d05050;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        # -- Buttons -------------------------------------------------------
        button_box = QDialogButtonBox()
        self.filter_button = QPushButton("Filter")
        self.filter_button.clicked.connect(self._do_filter)
        button_box.addButton(self.filter_button, QDialogButtonBox.ButtonRole.ActionRole)
        if replace_enabled:
            self.replace_all_button = QPushButton("Replace All")
            self.replace_all_button.clicked.connect(self._do_replace_all)
            button_box.addButton(
                self.replace_all_button, QDialogButtonBox.ButtonRole.ActionRole
            )
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        button_box.addButton(close_button, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(button_box)

    # -- field getters ------------------------------------------------------

    def selected_mode(self) -> str:
        for mode, button in self._mode_buttons.items():
            if button.isChecked():
                return mode
        return "normal"

    def set_mode(self, mode: str) -> None:
        if mode not in SEARCH_MODES:
            raise ValueError(f"Unknown search mode: {mode!r}")
        self._mode_buttons[mode].setChecked(True)

    def match_case(self) -> bool:
        return self.match_case_checkbox.isChecked()

    def in_selection(self) -> bool:
        return self.in_selection_radio.isChecked()

    def _clear_error(self) -> None:
        self.error_label.setText("")

    def _show_error(self, message: str) -> None:
        # Non-blocking: inline label only, never a modal.
        self.error_label.setText(message)

    # -- button handlers ----------------------------------------------------

    def _do_filter(self) -> None:
        """Read the fields and push the find pattern to the grid filter. Catches
        invalid-regex ValueError from a downstream compile and shows it inline."""
        self._clear_error()
        find = self.find_field.text()
        mode = self.selected_mode()
        case = self.match_case()
        try:
            self._on_filter(find, mode, case)
        except ValueError as exc:
            self._show_error(str(exc))

    def _do_replace_all(self) -> None:
        """Read the fields and invoke the Replace-All callback. Catches
        invalid-regex ValueError and shows it inline (never a modal)."""
        self._clear_error()
        find = self.find_field.text()
        replacement = self.replace_field.text()
        mode = self.selected_mode()
        case = self.match_case()
        in_selection = self.in_selection()
        try:
            self._on_replace_all(find, replacement, mode, case, in_selection)
        except ValueError as exc:
            self._show_error(str(exc))
