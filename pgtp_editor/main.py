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
    if session_path is not None:
        print(f"DEBUG logging -> {session_path}", file=sys.stderr)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
