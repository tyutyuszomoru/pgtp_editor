"""Shared fixtures for tests/ui/.

Autouse app-style/palette reset: BUG-004 made MainWindow's theme restore
(``_restore_theme``) unconditional -- every ``MainWindow()`` construction now
explicitly sets the QApplication's style to "Fusion" and applies a real
light/dark palette (``pgtp_editor.ui.theme.apply_theme``), even in tests that
never touch theming at all. QApplication is a process-wide singleton shared
across the whole pytest session, so that mutation would otherwise leak
forward into whatever test constructs a widget next -- confirmed to break
``test_menus.py``'s menu-bar assertions, since Fusion renders (and can
overflow) the menu bar differently than the native offscreen-platform style
those tests were written against. Reset unconditionally after every test in
this package so no test's app-style/palette mutation, from theming or
otherwise, can leak into another.
"""
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget


@pytest.fixture(autouse=True)
def _reset_app_style_and_palette(qapp):
    original_style = qapp.style().objectName()
    original_palette = QPalette(qapp.palette())
    # The dark theme also sets an app-global stylesheet (BUG-010's
    # QMenu::indicator QSS) -- restore it too, or a dark-theme test would
    # leak menu styling into every later widget test.
    original_stylesheet = qapp.styleSheet()
    try:
        yield
    finally:
        qapp.setStyle(original_style)
        qapp.setPalette(original_palette)
        qapp.setStyleSheet(original_stylesheet)


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path):
    """Most `MainWindow()` constructions across tests/ui/ don't inject a
    `settings=` override, so without this fixture they fall through to the
    real on-disk QSettings (IniFormat/UserScope, "MDS"/"PGTP Editor") --
    the developer's actual saved config file, shared by the whole machine
    and every xdist worker. `_restore_window_state`/`_build_toolbar` then
    apply whatever geometry/windowState/toolbarIds that file happens to hold
    to freshly constructed windows, producing outcomes that depend on
    execution order/parallelism -- confirmed flaky under `-n` load in both
    test_main_window.py and test_main_window_theme.py. Redirect the default
    IniFormat/UserScope search path to a per-test temp dir so every
    uninjected `MainWindow()` anywhere in tests/ui/ gets an isolated, empty
    settings store; tests that already inject their own `settings=` are
    unaffected since this only changes where the *default* one resolves."""
    before = QSettings(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, "MDS", "PGTP Editor"
    ).fileName()
    default_dir = str(Path(before).parent.parent)  # strip "/MDS/PGTP Editor.ini"
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    yield
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, default_dir
    )


@pytest.fixture(autouse=True)
def _reset_keyboard_modifiers():
    """`QGuiApplication::keyboardModifiers()` is process-global and is
    updated by `QTest`-synthesised key/mouse events; under `offscreen`
    nothing ever clears it again, so a `Ctrl+Shift+...` test leaves Shift
    latched for the rest of that xdist worker process. `QTableView.selectRow`
    (and any other gesture-interpreting API) reads that global state, so a
    later, unrelated test can silently behave as if Shift were held. See
    BUG-018."""
    yield
    if QGuiApplication.instance() is not None and QGuiApplication.keyboardModifiers():
        QTest.keyClick(QWidget(), Qt.Key.Key_Shift, Qt.KeyboardModifier.NoModifier)
