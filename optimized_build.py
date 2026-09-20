"""Build a size-optimized, onedir PyInstaller bundle for PGTP Editor.

Run from the repository root:

    python optimized_build.py

Produces dist/PGTPEditor/PGTPEditor.exe (plus its supporting _internal/
folder) - the exact onedir layout installer.iss expects to package.

"Optimized" here means smaller output, not a faster build: unused PySide6
Qt modules are excluded from the bundle (this app only ever imports
QtCore/QtGui/QtWidgets/QtSvg - see the EXCLUDED_QT_MODULES comment below for
how that was confirmed); the PyInstaller PySide6 hook still copies unused Qt
DLLs, translations, QML modules, WebEngine data, and non-widgets plugin
categories, so KEEP_QT_BINARIES + PRUNE_EXTRA_BINARIES + PRUNE_QT_DIRS strip
those from the finished bundle after COLLECT; and UPX compression is enabled
automatically when a usable `upx` executable is found on PATH.
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

# The distribution name from `pyproject.toml`'s `[project] name` (hyphenated; the
# import package is `pgtp_editor`). Restated here rather than imported so this
# build script keeps depending on nothing inside the package it builds.
DISTRIBUTION_NAME = "pgtp-editor"

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

# Resource files whose absence degrades the app SILENTLY rather than crashing it,
# so the build must refuse to produce the bundle instead of shipping it (BUG-057).
# curated.xsd is the sole feed for attribute completion, hover and the Properties
# panel labels (spec §11); without it `bundled_curated_xsd_text()` returns None and
# the app quietly falls back to a stub generated from the learned model.
REQUIRED_RESOURCE_FILES = ("curated.xsd", "manual.md")

# Confirmed by grepping every worktree's pgtp_editor/ tree for
# `from PySide6.<module>` imports: only QtCore, QtGui, QtWidgets, and QtSvg
# are ever used (QtSvg: ui/icons.py renders the Breeze toolbar SVGs via
# QSvgRenderer). Every other PySide6 submodule PyInstaller might otherwise
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
    # NOTE: PySide6.QtSvg is intentionally NOT excluded -- ui/icons.py imports
    # QSvgRenderer from it to render the toolbar icons. Excluding it makes the
    # frozen app silently ship with no toolbar icons (the icon load is wrapped
    # in a try/except that swallows the ImportError).
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

# Non-Qt third-party modules PyInstaller pulls in only through optional/typing
# branches of our real dependencies, never at runtime:
#   - numpy (+ numpy.libs): referenced only by psycopg's optional numpy type
#     adapters, which this app never registers. ~28 MB.
#   - yaml (PyYAML): reached only via an optional import branch. ~1 MB.
# Verified not present in sys.modules after importing the app's runtime modules,
# so excluding them is safe. This is the single biggest size win.
EXCLUDED_MODULES = ["numpy", "yaml"]

# Qt shared libraries we actively load. Any Qt6*.dll (or Qt63D*.dll) inside the
# finished bundle whose basename is NOT in this allowlist is deleted after
# COLLECT. The allowlist mirrors the Python modules we import (see the
# EXCLUDED_QT_MODULES header above): QtCore + QtGui + QtWidgets + QtSvg. An
# allowlist is used instead of a blocklist because PyInstaller's PySide6 hook
# copies ~140 Qt DLLs (~290 MB) wholesale regardless of which .pyd modules are
# excluded, and keeping the blocklist in sync would need a new entry per Qt
# release. If a future feature imports another Qt module, add its DLL here AND
# drop the module from EXCLUDED_QT_MODULES.
KEEP_QT_BINARIES = [
    "Qt6Core.dll",
    "Qt6Gui.dll",
    "Qt6Widgets.dll",
    "Qt6Svg.dll",
]

# Non-Qt runtime binaries the PySide6 PyInstaller hook still ships even though
# nothing in this app loads them. Matched by exact basename, case-insensitively.
#   - opengl32sw.dll: 20 MB software OpenGL fallback used only by QtQuick.
#   - QtWebEngineProcess.exe: WebEngine's out-of-process helper.
#   - avcodec/avformat/avutil/swresample/swscale: FFmpeg libs pulled in by
#     QtMultimedia. ~18 MB combined.
PRUNE_EXTRA_BINARIES = [
    "opengl32sw.dll",
    "QtWebEngineProcess.exe",
    "avcodec-61.dll",
    "avformat-61.dll",
    "avutil-59.dll",
    "swresample-5.dll",
    "swscale-8.dll",
]

# Directories inside the finished bundle that a QtWidgets+QtSvg app never
# loads. Deleted after COLLECT.
#   - PySide6/translations: Qt's built-in localizations (~7 MB, English only).
#   - PySide6/qml: QML modules used only by QtQuick/QtQml (~25 MB in-install).
#   - PySide6/resources: QtWebEngine data (icudtl.dat, v8_context_snapshot.*,
#     qtwebengine_*.pak) - ~101 MB in-install, of which the *devtools*.pak
#     alone is 72 MB.
#   - PySide6/plugins/<subdir>: Qt plugin categories none of our imported
#     modules use. Intentionally kept: platforms/ (mandatory qwindows.dll),
#     styles/ (native look), iconengines/ (SVG icons), imageformats/
#     (PNG/JPG/SVG/ICO).
PRUNE_QT_DIRS = [
    "PySide6/translations",
    "PySide6/qml",
    "PySide6/resources",
    "PySide6/plugins/assetimporters",
    "PySide6/plugins/canbus",
    "PySide6/plugins/designer",
    "PySide6/plugins/generic",
    "PySide6/plugins/geometryloaders",
    "PySide6/plugins/geoservices",
    "PySide6/plugins/multimedia",
    "PySide6/plugins/networkinformation",
    "PySide6/plugins/platforminputcontexts",
    "PySide6/plugins/position",
    "PySide6/plugins/qmllint",
    "PySide6/plugins/qmltooling",
    "PySide6/plugins/renderers",
    "PySide6/plugins/renderplugins",
    "PySide6/plugins/sceneparsers",
    "PySide6/plugins/scxmldatamodel",
    "PySide6/plugins/sensors",
    "PySide6/plugins/sqldrivers",
    "PySide6/plugins/texttospeech",
    "PySide6/plugins/tls",
    "PySide6/plugins/vectorimageformats",
    "PySide6/plugins/webview",
]


def _prune_bundle(app_dir: Path) -> None:
    """Delete unused Qt libraries and data from the finished onedir bundle.

    PyInstaller has no CLI switch to drop the Qt DLLs its PySide6 hook collects
    transitively, so we remove them here after COLLECT. Qt shared libraries are
    filtered against KEEP_QT_BINARIES (allowlist), extras against
    PRUNE_EXTRA_BINARIES (blocklist), directories against PRUNE_QT_DIRS. Every
    surface removed here is one this app has been confirmed not to load.
    """
    internal = app_dir / "_internal"
    freed = 0

    keep = {name.lower() for name in KEEP_QT_BINARIES}
    extra_deny = {name.lower() for name in PRUNE_EXTRA_BINARIES}
    for path in internal.rglob("*"):
        if not path.is_file():
            continue
        name_lc = path.name.lower()
        is_qt_lib = name_lc.startswith("qt6") and name_lc.endswith(".dll")
        if (is_qt_lib and name_lc not in keep) or name_lc in extra_deny:
            freed += path.stat().st_size
            path.unlink()

    for rel in PRUNE_QT_DIRS:
        target = internal / rel
        if target.is_dir():
            freed += sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
            shutil.rmtree(target)

    print(f"Pruned unused Qt files from bundle: {freed / 1024 / 1024:.1f} MB freed.")


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


def _distribution_metadata_available() -> bool:
    """Whether `pgtp-editor`'s dist-info exists in the building interpreter.

    `--copy-metadata` aborts the whole build when it does not, so it is asked
    first (see the call site for why the flag is wanted at all).
    """
    from importlib.metadata import PackageNotFoundError, distribution

    try:
        distribution(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return False
    except Exception:
        return False
    return True


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
    for name in REQUIRED_RESOURCE_FILES:
        if not (RESOURCES_SRC / name).is_file():
            raise SystemExit(
                f"Bundled resource not found: {RESOURCES_SRC / name}\n"
                "This file must be committed to the repository for the build to "
                "work from a clean checkout. Shipping without it degrades the app "
                "silently (curated.xsd feeds attribute completion, hover and the "
                "Properties labels; manual.md is the in-app manual)."
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

    # FQ-260810164455: carry the distribution's metadata into the bundle so the
    # frozen app can read its own version. `pgtp_editor/version.py` resolves the
    # version from `pyproject.toml` in a checkout, but a frozen build ships no
    # `pyproject.toml`, so `importlib.metadata` is its ONLY route -- and
    # PyInstaller collects no metadata unless asked. Without this flag the About
    # box in a shipped build would read "unknown". The alternative (a hardcoded
    # literal fallback in `version.py`) was rejected: it recreates the very
    # second copy that feature exists to remove.
    #
    # Guarded rather than passed unconditionally, because `--copy-metadata` is a
    # HARD build error when the distribution is not installed in the building
    # interpreter -- and the project is installed editable on Windows but not
    # necessarily anywhere else. A build from a bare checkout keeps working; it
    # just produces an app that reports "unknown", which is the honest answer.
    if _distribution_metadata_available():
        args += ["--copy-metadata", DISTRIBUTION_NAME]
    else:
        print(
            f"Distribution metadata for {DISTRIBUTION_NAME!r} not found in this "
            "interpreter - the frozen app will report its version as 'unknown'. "
            f"Install the project (pip install -e .) and re-run to embed it."
        )

    for module in EXCLUDED_QT_MODULES + EXCLUDED_MODULES:
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
        _prune_bundle(exe_path.parent)
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
