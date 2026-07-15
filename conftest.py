"""Global pytest configuration for the pgtp_editor test suite.

Forces Qt into headless "offscreen" mode *before* any test imports PySide6 or
creates a QApplication. Relying on the ``QT_QPA_PLATFORM=offscreen`` environment
variable being passed on the command line is fragile: any run launched without
it (an IDE test runner, a bare ``pytest`` invocation, a spawned subprocess) pops
real windows. Setting it here makes the guard unconditional -- it holds no
matter how pytest is launched, which stops the stray "Not Responding" Qt window
processes that otherwise accumulate on Windows.

Note this only prevents *visible* windows. A test that reaches an un-patched
modal call (``QDialog.exec()``, ``QMessageBox.*``, ``QFileDialog.*``) still
spins a blocking modal event loop even offscreen and would hang forever; the
``--timeout`` in pyproject.toml is the hard safety net for that case, aborting
the run with a traceback that names the offending test instead of hanging.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(autouse=True)
def _isolate_qsettings(tmp_path):
    """Point the default QSettings at a per-test temp directory so the app's
    ``QSettings("MDS", "PGTP Editor")`` (window geometry, theme, toolbar layout)
    never reads or writes the real user registry during tests -- and so one
    test's persisted state cannot leak into another (e.g. a window closed in one
    test writing geometry that a later default-size test would restore).
    """
    from PySide6.QtCore import QSettings

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.SystemScope, str(tmp_path)
    )
    yield
