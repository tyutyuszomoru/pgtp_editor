"""Build a size-optimized, onedir PyInstaller bundle for PGTP Editor.

Run from the repository root:

    python optimized_build.py

Produces dist/PGTPEditor/PGTPEditor.exe (plus its supporting _internal/
folder) - the exact onedir layout installer.iss expects to package.

"Optimized" here means smaller output, not a faster build: unused PySide6
Qt modules are excluded from the bundle (this app only ever imports
QtCore/QtGui/QtWidgets - see the EXCLUDED_QT_MODULES comment below for how
that was confirmed), and UPX compression is enabled automatically when a
usable `upx` executable is found on PATH.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

REPO_ROOT = Path(__file__).resolve().parent
ENTRY_POINT = REPO_ROOT / "pgtp_editor" / "main.py"
ICON_PATH = REPO_ROOT / "docs" / "pgtpeditor.ico"
APP_NAME = "PGTPEditor"

# Non-Python package data loaded at runtime via importlib.resources
# (`files("pgtp_editor") / "resources" / ...`): the in-app manual
# (resources/manual.md, ui/manual_panel.py) and the Breeze toolbar SVGs
# (resources/icons/, ui/icons.py). PyInstaller does not pick these up on its
# own - without bundling them the app launches but the Manual tab is empty and
# toolbar icons fail to load. The bundle destination MUST stay
# "pgtp_editor/resources" so it lands next to the imported package and
# files("pgtp_editor") resolves to it inside the frozen app.
RESOURCES_SRC = REPO_ROOT / "pgtp_editor" / "resources"
RESOURCES_DEST = "pgtp_editor/resources"

# Confirmed by grepping every worktree's pgtp_editor/ tree for
# `from PySide6.<module>` imports: only QtCore, QtGui, and QtWidgets are
# ever used. Every other PySide6 submodule PyInstaller might otherwise
# pull in transitively gets excluded here. If a future feature imports a
# module not in this app's actual dependency set, add it above this list
# and re-run the grep check described in this project's build docs
# before removing it from EXCLUDED_QT_MODULES.
EXCLUDED_QT_MODULES = [
    "PySide6.QtNetwork",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSql",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtBluetooth",
    "PySide6.QtSerialPort",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtNfc",
    "PySide6.QtDBus",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtTest",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPrintSupport",
    "PySide6.QtXml",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtNetworkAuth",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
]


def _find_upx() -> str | None:
    """Return the upx executable's path if one is on PATH, else None.

    UPX is an optional, separately-installed compressor - PyInstaller's
    --upx-dir flag expects a directory, and passing one that doesn't
    contain a working upx binary makes the whole build fail rather than
    degrade gracefully. Detecting availability here means this script
    produces a working (if slightly larger) build on a machine without
    UPX installed, instead of erroring out.
    """
    upx_path = shutil.which("upx")
    if upx_path is None:
        return None
    return str(Path(upx_path).resolve().parent)


def build() -> None:
    if not ENTRY_POINT.exists():
        raise SystemExit(f"Entry point not found: {ENTRY_POINT}")
    if not ICON_PATH.exists():
        raise SystemExit(
            f"Icon not found: {ICON_PATH}\n"
            "This file must be committed to the repository for the build "
            "to work from a clean checkout - see docs/pgtpeditor.ico."
        )
    if not RESOURCES_SRC.is_dir():
        raise SystemExit(
            f"Resources folder not found: {RESOURCES_SRC}\n"
            "The bundled manual and toolbar icons live here; the build cannot "
            "produce a working app without it."
        )

    # PyInstaller wants "<src><os.pathsep><dest>" for --add-data.
    resources_spec = f"{RESOURCES_SRC}{os.pathsep}{RESOURCES_DEST}"

    args = [
        str(ENTRY_POINT),
        "--name", APP_NAME,
        "--onedir",
        "--windowed",
        "--icon", str(ICON_PATH),
        "--add-data", resources_spec,
        "--distpath", str(REPO_ROOT / "dist"),
        "--workpath", str(REPO_ROOT / "build"),
        "--clean",
        "--noconfirm",
    ]

    for module in EXCLUDED_QT_MODULES:
        args += ["--exclude-module", module]

    upx_dir = _find_upx()
    if upx_dir is not None:
        args += ["--upx-dir", upx_dir]
        print(f"UPX found at {upx_dir} - compression enabled.")
    else:
        print("UPX not found on PATH - building without compression "
              "(output will be larger; install UPX and re-run to shrink it).")

    print(f"Building {APP_NAME} from {ENTRY_POINT} ...")
    PyInstaller.__main__.run(args)

    exe_path = REPO_ROOT / "dist" / APP_NAME / f"{APP_NAME}.exe"
    if exe_path.exists():
        print(f"Build complete: {exe_path}")
    else:
        raise SystemExit(
            f"PyInstaller reported success but {exe_path} was not found - "
            "check the build output above for the actual output layout."
        )


if __name__ == "__main__":
    if sys.platform != "win32":
        print(
            "Warning: this produces a Windows .exe bundle even when run "
            "elsewhere for cross-compilation testing, but the real "
            "installer.iss packaging step only runs on Windows.",
            file=sys.stderr,
        )
    build()
