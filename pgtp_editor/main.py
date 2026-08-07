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
        "--mcp",
        action="store_true",
        default=False,
        help="run §23's MCP server on stdio INSTEAD of the GUI (headless, "
        "off by default; the optional file argument becomes the default "
        "project for tool calls that omit a path)",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="only meaningful with --mcp: the .pgtp that becomes the headless "
        "server's default project for path-less tool calls. The GUI IGNORES "
        "it — it always starts at the launcher (FQ-010)",
    )
    return parser.parse_args(argv)


class _DefaultPathProvider:
    """Headless `--mcp <file>`: a `FileProjectProvider` with a default path.

    §23's headless mode is "file-path-driven", i.e. every tool call names a
    `.pgtp`. When the user *did* name one on the command line, making every
    client call repeat it would be gratuitous, so a path-less call resolves to
    that file. This adds no logic of its own beyond substituting the default —
    all parsing/validation stays in `FileProjectProvider`, and an explicit
    `path` argument still wins (so e.g. `diff_projects` can name two files).

    `LiveProjectProvider` is deliberately NOT used here: it exists for the
    in-app case, where there is a real in-memory model to share. Headless has
    none.
    """

    def __init__(self, default_path, delegate=None):
        from pgtp_editor.mcp import FileProjectProvider

        self._default_path = default_path
        self._delegate = delegate if delegate is not None else FileProjectProvider()

    def resolve(self, path=None):
        return self._delegate.resolve(path or self._default_path)


def run_mcp_server(path=None, *, serve=None, stderr=None):
    """Run §23's MCP server on stdio and return a process exit code.

    THE single implementation behind both start paths: the `--mcp` flag (see
    `main`) and `python -m pgtp_editor.mcp` (see `pgtp_editor/mcp/__main__.py`,
    a shim that calls straight into here). Neither constructs a `QApplication`
    nor imports anything from `pgtp_editor.ui` — stdout is the JSON-RPC
    channel, and a GUI contending for it would corrupt every session.

    Blocks until the peer closes stdin. `serve` is injectable so tests never
    enter a real stdio loop.
    """
    stderr = stderr if stderr is not None else sys.stderr

    provider = None
    if path is not None:
        # Fail loudly and early rather than answering every tool call with the
        # same error, and never with a traceback as the user-facing output.
        if not os.path.isfile(path):
            print(f"pgtp_editor --mcp: no such .pgtp file: {path}", file=stderr)
            return 2
        try:
            with open(path, "rb"):
                pass
        except OSError as exc:
            print(
                f"pgtp_editor --mcp: cannot read {path}: {exc.strerror or exc}",
                file=stderr,
            )
            return 2
        provider = _DefaultPathProvider(path)

    if serve is None:
        from pgtp_editor.mcp import serve_stdio as serve

    print(
        "PGTP Editor MCP server on stdio"
        + (f" (default project: {path})" if path else ""),
        file=stderr,
    )
    serve(provider=provider)
    return 0


def main(argv=None, *, launcher=None):
    """Run the GUI (or, with --mcp, §23's headless server) and return an exit code.

    `argv` defaults to the real command line; `launcher` is the FQ-010 startup
    launcher seam (see below). Both exist so the suite can drive this function
    without a real command line and without a real modal.
    """
    args = parse_args(sys.argv[1:] if argv is None else argv)
    session_path = debuglog.setup(debug=args.debug)

    # --mcp runs the server INSTEAD of the GUI, and returns here before any Qt
    # import: stdio is the MCP transport, so a GUI process sharing stdout would
    # corrupt the protocol stream (see mcp/server.py's module docstring, which
    # names serve_stdio "THE headless --mcp entry point"). The in-app server is
    # a separate thing entirely -- start_server_thread from a GUI gesture.
    #
    # INVARIANT (FQ-010): this early return is what makes the startup launcher
    # STRUCTURALLY unreachable headlessly -- ui/launcher_dialog.py is not even
    # imported on this path. NEVER move the launcher (or any Qt import) above
    # this return: a GUI contending for stdout corrupts every MCP session.
    if args.mcp:
        return run_mcp_server(args.file)

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

    # FQ-010: the startup launcher -- the ONE automatic show, here and never in
    # `MainWindow.__init__` (49 test files construct a MainWindow; a modal there
    # would hang every one of them). Behind the `launcher=` seam, like every
    # other confirmation in this codebase, so the suite never enters a real
    # modal loop. Deliberately AFTER `window.show()`: the persisted
    # `windowState` is visibly restored first, then the launcher lands on top of
    # it. Escape/close inside it lands in the empty app exactly as before and
    # never quits, so nothing here reads its return value.
    #
    # `args.file` is deliberately NOT opened: the GUI no longer opens a `.pgtp`
    # passed on the command line (FQ-010). The argument itself stays -- it is the
    # headless `--mcp` server's default project, passed at the early return above.
    if launcher is None:
        from pgtp_editor.ui import launcher_dialog

        launcher = launcher_dialog.show_launcher
    launcher(window, settings)

    if session_path is not None:
        print(f"DEBUG logging -> {session_path}", file=sys.stderr)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
