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
"""`ui/file_filters.py` -- the platform rule for "locate an executable" dialogs.

Pure strings, so none of this needs a `QApplication` or reaches a modal.
"""

import pgtp_editor.ui.file_filters as file_filters
from pgtp_editor.ui.file_filters import ALL_FILES, WINDOWS_EXECUTABLES, executable_filter


def _leading(name_filter: str) -> str:
    """The filter `QFileDialog` selects initially: the first `;;`-separated one."""
    return name_filter.split(";;")[0]


def test_posix_leads_with_all_files(monkeypatch):
    """The regression this module exists for.

    On Linux an executable has no extension, so a dialog opening on
    `Executables (*.exe)` shows an apparently EMPTY directory and the user must
    know to switch filters before they can see the `php` they came for.
    """
    monkeypatch.setattr(file_filters, "_WINDOWS", False)
    assert _leading(executable_filter()) == ALL_FILES


def test_windows_leads_with_exe(monkeypatch):
    """Windows keeps the filter that is right there -- the fix is ordering, not
    dropping the `.exe` entry."""
    monkeypatch.setattr(file_filters, "_WINDOWS", True)
    assert _leading(executable_filter()) == WINDOWS_EXECUTABLES


def test_both_entries_are_always_offered(monkeypatch):
    """Neither platform LOSES an option: a `.exe` under Wine and an
    extension-less binary on Windows both stay reachable by switching."""
    for windows in (True, False):
        monkeypatch.setattr(file_filters, "_WINDOWS", windows)
        name_filter = executable_filter()
        assert ALL_FILES in name_filter
        assert WINDOWS_EXECUTABLES in name_filter
        assert name_filter.count(";;") == 1


def test_the_two_locate_dialogs_share_this_one_rule():
    """Both call sites go through the helper, so the platform rule cannot drift
    back to being right on one platform and wrong on the other."""
    import inspect

    from pgtp_editor.ui import generation_controller, lint_controller

    for module in (lint_controller, generation_controller):
        source = inspect.getsource(module)
        assert "executable_filter()" in source, module.__name__
        # The hard-coded Windows-only filter must not creep back in.
        assert "Executables (*.exe);;All files (*)" not in source, module.__name__
