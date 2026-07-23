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

from pgtp_editor.schema_learning.merge import Conflict
from pgtp_editor.ui.merge_conflicts_dialog import MergeConflictsDialog


def test_default_resolution_keeps_master_and_can_switch(qtbot):
    conflicts = [
        Conflict("Root", "a", "labels", "4", "pdf", "PDF export"),
        Conflict("Root", "a", "kind", None, "setting", "content"),
    ]
    dialog = MergeConflictsDialog(conflicts)
    qtbot.addWidget(dialog)
    assert dialog.resolutions() == [False, False]
    dialog.choice_combo(0).setCurrentIndex(1)  # use incoming
    assert dialog.resolutions() == [True, False]
