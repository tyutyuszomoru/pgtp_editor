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
from importlib.resources import files

from pgtp_editor import debuglog

APPLICATION_NAME = "PGTP Editor"
ORGANIZATION_NAME = "MDS"
DESKTOP_FILE_NAME = "pgtp-editor"


def _load_app_icon():
    """Load the bundled app icon as a QIcon, or None if it can't be found.

    Guarded so a partial/broken install (missing resource file) never crashes
    startup -- the app just runs without a custom icon in that case.
    """
    from PySide6.QtGui import QIcon

    try:
        resource = files("pgtp_editor") / "resources" / "app_icon.png"
        if not resource.is_file():
            return None
        with resource.open("rb") as fh:
            data = fh.read()
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        return None

    icon = QIcon()
    from PySide6.QtGui import QPixmap

    pixmap = QPixmap()
    if not pixmap.loadFromData(data):
        return None
    icon.addPixmap(pixmap)
    return icon if not icon.isNull() else None


def apply_app_identity(app):
    """Set application/desktop identity and window icon on `app`.

    Factored out of main() so tests can call it directly (under
    QT_QPA_PLATFORM=offscreen) without running the full event loop. Sets the
    application name/organization/display name and the desktop-file name
    (must match the basename of packaging/linux/pgtp-editor.desktop, which is
    how KDE/Wayland associates the taskbar icon) plus the QApplication-level
    window icon (drives the in-window/title-bar corner icon and is the
    taskbar fallback). Every setter is guarded with getattr so this is a
    no-op against stand-in/fake app objects that don't implement the full
    QApplication API (e.g. in unit tests).
    """
    app_cls = type(app)
    for name, value in (
        ("setApplicationName", APPLICATION_NAME),
        ("setOrganizationName", ORGANIZATION_NAME),
        ("setApplicationDisplayName", APPLICATION_NAME),
        ("setDesktopFileName", DESKTOP_FILE_NAME),
    ):
        setter = getattr(app_cls, name, None)
        if setter is not None:
            setter(value)

    # Only load the icon (constructs a real QPixmap/QIcon, which requires an
    # actual QGuiApplication instance to exist) when `app` genuinely supports
    # setWindowIcon -- a stand-in/fake app object in tests may not have a real
    # Qt application behind it at all, and building a QPixmap with none can
    # crash the process rather than just fail an attribute lookup.
    if hasattr(app, "setWindowIcon"):
        icon = _load_app_icon()
        if icon is not None:
            app.setWindowIcon(icon)


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
    apply_app_identity(app)

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
