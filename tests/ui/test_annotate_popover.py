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

from PySide6.QtCore import Qt

from pgtp_editor.ui.annotate_popover import AnnotatePopover


def _popover(qtbot, **kwargs):
    popover = AnnotatePopover("Root/Item", "mode", "4", **kwargs)
    qtbot.addWidget(popover)
    return popover


def test_prefills_existing_annotation(qtbot):
    popover = _popover(
        qtbot, label="pdf", note="adds <X>", kind="setting", bitflags=True
    )
    assert popover.label_edit.text() == "pdf"
    assert popover.note_edit.text() == "adds <X>"
    assert popover.kind_combo.currentText() == "Setting"
    assert popover.bitflags_check.isChecked()
    assert "Root/Item" in popover.header_label.text()
    assert "mode" in popover.header_label.text()
    assert '"4"' in popover.header_label.text()


def test_enter_in_label_commits_payload(qtbot):
    popover = _popover(qtbot)
    committed = []
    popover.committed.connect(committed.append)
    popover.label_edit.setText("pdf")
    popover.note_edit.setText("enables <Watermark>")
    popover.bitflags_check.setChecked(True)
    popover.kind_combo.setCurrentText("Setting")
    popover.label_edit.returnPressed.emit()
    assert committed == [{
        "label": "pdf",
        "note": "enables <Watermark>",
        "kind": "setting",
        "bitflags": True,
    }]


def test_escape_cancels(qtbot):
    popover = _popover(qtbot)
    cancelled = []
    popover.cancelled.connect(lambda: cancelled.append(True))
    qtbot.keyClick(popover, Qt.Key.Key_Escape)
    assert cancelled == [True]
