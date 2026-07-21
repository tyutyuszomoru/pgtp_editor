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

import argparse
import logging
import os
import sys

from pgtp_editor import debuglog


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="pgtp_editor")
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.environ.get("PGTP_EDITOR_DEBUG", "") not in ("", "0"),
        help="write a full-detail diagnostic log for this session",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="optional .pgtp project to open at startup (used by the "
        "Windows 'Edit with PGTP Editor' right-click verb, which passes "
        "the clicked file path)",
    )
    return parser.parse_args(argv)


def main():
    args = parse_args(sys.argv[1:])
    session_path = debuglog.setup(debug=args.debug)

    # Qt imports AFTER setup so even import-time crashes are logged.
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import QSettings, qVersion
    from PySide6.QtWidgets import QApplication

    debuglog.install_qt_handler()
    settings = QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        "MDS",
        "PGTP Editor",
    )
    logging.getLogger(__name__).log(
        debuglog.TRACE if args.debug else logging.WARNING,
        "qt versions pyside=%s qt=%s settings=%s",
        pyside_version,
        qVersion(),
        settings.fileName(),
    )

    app = QApplication(sys.argv)

    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow(debug_log_path=session_path)
    window.show()

    # Open a file passed on the command line (e.g. the Windows "Edit with
    # PGTP Editor" right-click verb passes the clicked .pgtp path). Guarded on
    # existence: open_project_file surfaces parse errors gracefully but a
    # missing path would raise from load_project, so skip it and warn instead.
    if args.file is not None:
        if os.path.isfile(args.file):
            window.open_project_file(args.file)
        else:
            logging.getLogger(__name__).warning(
                "startup file not found, ignoring: %s", args.file
            )

    if session_path is not None:
        print(f"DEBUG logging -> {session_path}", file=sys.stderr)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
