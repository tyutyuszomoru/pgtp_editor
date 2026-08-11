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
"""`python -m pgtp_editor` — the obvious command, made to work
(BUG-260812002307).

The real entry point is and stays `pgtp_editor.main:main`; the documented
`python -m pgtp_editor.main` form keeps working unchanged. This module is a
pure DELEGATION so the two can never diverge — no argument parsing, no logging
setup, no Qt import of its own. `main` reads `sys.argv[1:]` itself when given no
`argv`, which is exactly right for both module forms, and returns the process
exit code (`app.exec()`, or `0` from the `--mcp` path).
"""
from pgtp_editor.main import main

if __name__ == "__main__":
    raise SystemExit(main())
