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
"""`QFileDialog` name-filter strings, in one place because they are
platform-dependent and were previously wrong on one of the two platforms.

Qt-free by design: these are plain strings, so the rule can be unit-tested
without a `QApplication` and without reaching a modal (`CLAUDE.md`).

Why this module exists
----------------------
Both "locate an executable" dialogs -- `Locate PHP Linter…` (§22) and
`Locate PHP Generator…` / `Locate panGen Runtime…` (§19/§20) -- hard-coded
`"Executables (*.exe);;All files (*)"`. On Windows that is right. On Linux,
where executables carry no extension, `*.exe` matches **nothing**: the dialog
opens apparently empty and the user has to know to switch the filter to
*All files* before they can see the `php` they are looking for.

This project is developed and used on **both** Windows and Linux (`CLAUDE.md`),
so a Windows-only filter is a real defect on the other half, not a cosmetic
detail -- and it was duplicated at two call sites, so it is fixed once here.

The fix is ordering, not omission: the *first* filter in the string is the one
`QFileDialog` selects initially, so each platform leads with the filter that
actually matches its executables and keeps the other available.
"""

import sys

#: True on Windows, where executables are identified by an `.exe` extension.
_WINDOWS = sys.platform.startswith("win")

#: All files, no filtering -- the correct default on POSIX, where an executable
#: has no distinguishing extension.
ALL_FILES = "All files (*)"

#: Windows executables.
WINDOWS_EXECUTABLES = "Executables (*.exe)"


def executable_filter() -> str:
    """The name filter for a "locate an executable" dialog on this platform.

    Windows leads with `*.exe`; every other platform leads with *All files*, so
    the dialog shows candidates immediately instead of appearing empty. Both
    entries are always present, so a user can still switch either way -- e.g.
    to pick a `.exe` under Wine, or a extension-less binary on Windows.
    """
    if _WINDOWS:
        return f"{WINDOWS_EXECUTABLES};;{ALL_FILES}"
    return f"{ALL_FILES};;{WINDOWS_EXECUTABLES}"
