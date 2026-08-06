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

# pgtp_editor/mcp/__main__.py
"""`python -m pgtp_editor.mcp [project.pgtp]` — §23's headless MCP server.

Exists because that is the shape MCP client configs expect (`command`/`args`
pointing at a module), while `pgtp_editor --mcp` is the shape a shell user
expects. Both are the SAME start path: this module is a shim over
`pgtp_editor.main.run_mcp_server`, which is the only place the server is
actually constructed. Nothing here runs on import of the `pgtp_editor.mcp`
package — only on being executed as a module.

No Qt, no `QApplication`: stdout is the JSON-RPC channel.
"""
from __future__ import annotations

import sys

from pgtp_editor.main import parse_args, run_mcp_server


def main(argv=None) -> int:
    """Parse `[--debug] [file]` with the app's own parser (so the flags mean
    exactly what they mean for `pgtp_editor --mcp`) and run the server.

    `--mcp` is implied here and accepted for symmetry, so a client config can
    pass it harmlessly.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)

    from pgtp_editor import debuglog

    debuglog.setup(debug=args.debug)
    return run_mcp_server(args.file)


if __name__ == "__main__":
    sys.exit(main())
