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

# pgtp_editor/lint/__init__.py
"""External PHP linting for the custom-PHP tabs (spec §22).

Deliberately split in three, along the seam that keeps the suite free of
subprocesses:

* `findings.py` -- **pure and Qt-free**: turns raw linter stdout/stderr/exit
  code into structured findings and into ready-to-append Audit lines. No
  filesystem, no `subprocess`, no PySide6, so canned linter output is all a
  test needs.
* `runner.py` -- the one place a process is actually spawned. Injectable
  everywhere it is used (`db/introspect.py`'s `runner=` precedent), so no test
  ever shells out to a real `php`.
* `config.py` -- the `lint_executable_path` key, stored in the SAME
  `generator_config.json` `generation/config.py` (§19) already owns.

This package imports **no Qt** except in `config.py` (which needs
`QStandardPaths` for the AppData location, exactly as `generation/config.py`
does). Importing `pgtp_editor.lint` itself pulls in nothing at all -- submodules
are imported explicitly so `findings` stays provably Qt-free.
"""
