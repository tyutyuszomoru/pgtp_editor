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

# pgtp_editor/ui/_stub_action.py
"""Shared helper: a menu action wired to a not-yet-implemented callback.

Used by both ProjectTreePanel (context menus) and MainWindow (menu bar)
so the wiring pattern lives in exactly one place.
"""


def add_stub_action(menu, label, callback):
    action = menu.addAction(label)
    action.triggered.connect(lambda checked=False, l=label: callback(l))
    return action
