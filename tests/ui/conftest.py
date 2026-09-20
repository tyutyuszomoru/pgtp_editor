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
from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt, QThreadPool
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from pgtp_editor.ui import async_task


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_async: this test drives ui/async_task.py's real threadpool on "
        "purpose, so `_no_leaked_async_tasks` drains it without failing it.",
    )


@pytest.fixture(autouse=True)
def _offline_ddl_mode_probe(monkeypatch):
    """Keep FQ-260812022749's DDL-mode probe off the wire and out of a shell.

    `MainWindow.__init__` binds two `db/pg_dump_mode.py` seams from this
    module's globals: `probe_quality_capabilities` (which opens a real
    connection, up to `connect_timeout=10` per call) and `ddl_mode_prober`
    (which spawns `pg_dump --version`). Every `_open_ddl_explorer` on the
    quality role reaches both, and the great majority of tests that open the
    Explorer stub only `_fetch_ddl_schema` -- so without this the suite would
    dial each test's fake host and shell out on every one.

    The replacements are the REAL rule with the I/O removed: an unprobed
    `SandboxCapabilities` and `decide_ddl_mode`, the pure function, told that
    no `pg_dump` was located. Tests about the verdict itself replace
    `window.probe_quality_capabilities` / `window.ddl_mode_prober` on the
    instance, which wins over this.
    """
    from pgtp_editor.db.pg_dump_mode import decide_ddl_mode
    from pgtp_editor.db.sandbox import SandboxCapabilities
    from pgtp_editor.ui import main_window as main_window_module

    monkeypatch.setattr(
        main_window_module,
        "sandbox_probe",
        lambda params, *a, **k: SandboxCapabilities(
            probe_error="the quality server was not probed (test stub)"
        ),
    )
    monkeypatch.setattr(
        main_window_module,
        "probe_ddl_mode",
        lambda caps, **k: decide_ddl_mode(caps.server_version, None, None),
    )
    # A THIRD seam, added when the dual-mode buffer was wired: a FULL verdict
    # makes `_open_ddl_explorer` call `fetch_schema_dump`, which spawns
    # `pg_dump --schema-only` against the test's fake host. The stub above
    # yields RESTRICTED, so most tests never reach it -- but any test that
    # installs a full verdict on the instance does, and it shelled out for real
    # until this existed (observed: `could not translate host name "h"`).
    #
    # It raises rather than returning canned SQL on purpose. A silent empty
    # dump would render an empty full-mode buffer and read as a rendering bug;
    # `SchemaDumpError` is the shipped refusal path, so an unprepared test
    # degrades to restricted with a named row -- visible, and correct. Tests
    # about full mode inject their own dump text over this.
    #
    # The three arguments are not optional: `SchemaDumpError(step, returncode,
    # stderr)` builds its own message. Constructing it with one argument raised
    # a `TypeError` from inside this stub, which `_open_ddl_explorer`'s generic
    # `except Exception` still degraded on -- so the suite stayed green while
    # this seam was, in fact, never exercising the refusal path it documents.
    monkeypatch.setattr(
        main_window_module,
        "fetch_schema_dump",
        lambda params, path, **k: (_ for _ in ()).throw(
            main_window_module.SchemaDumpError(
                "no pg_dump was run (test stub)",
                1,
                "inject dump text to test full mode",
            )
        ),
    )


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


@pytest.fixture(autouse=True)
def _flush_deferred_deletes(qapp):
    """Actually destroy the widgets each test left behind.

    `qtbot.addWidget` schedules teardown via `deleteLater()`, which only posts
    a `DeferredDelete` event -- and pytest-qt never runs an event loop that
    delivers it. `QApplication.processEvents()` does not deliver it either.
    So every widget every test created stayed alive for the whole worker
    process: measured at a constant 13 top-level widgets leaked per
    `MainWindow` (11 QMenu + the window + a QFrame), accumulating linearly --
    13, 26, 39 ... 104 after only eight tests.

    That is why the suite was unusable. Construction is O(live widgets): eight
    MainWindow tests took 12.85s with the corpse pile and 4.46s without, and a
    worker running hundreds of them degrades until it dies -- the "runs for
    10-30 minutes and has no conclusions" symptom.

    `sendPostedEvents(None, DeferredDelete)` is the one call that actually
    delivers those events. **This is a test-harness fix, not an app fix**: the
    application itself frees everything correctly, because its real event loop
    delivers `DeferredDelete` normally. Verified by constructing and dropping
    MainWindows outside pytest -- with this flush, every instance is freed and
    the top-level count stays at zero.
    """
    yield
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


@pytest.fixture(autouse=True)
def _no_leaked_async_tasks(qapp, request):
    """Fail the test that leaks an off-GUI-thread task, not the bystander.

    BUG-043: a `ui/async_task.py::run_async` worker started by one test can
    finish after that test's `MainWindow` is gone. Delivery is a queued signal
    on the GUI thread, so the callback runs during *whatever test happens to be
    running* when it lands, touching a deleted C++ object and raising out of the
    Qt event loop. pytest-qt charges that to the innocent test -- which is why
    the failing name rotated between runs, why the file passed when run alone,
    and why a real defect got dismissed on sight for a day. Making the leak stop
    is not enough; it has to be **attributed**, or the next one costs the same
    day again.

    So the rule this enforces is a testability invariant, not a cleanup: **no
    test may end with a task still in flight.** Every off-thread seam in the app
    is reachable from `window._run_async` (BUG-043 made the sandbox lane the
    last exception), so the fix in a failing test is always the same one line --
    inject `tests/ui/_sandbox_stubs.py::sync_run` and the lane runs
    synchronously, in-test, where its result belongs.

    Deliberate exceptions (`tests/ui/test_async_task.py` exercises the real
    threadpool on purpose) mark themselves with ``@pytest.mark.real_async``;
    they are still drained, just not failed.

    Ordering matters and is the reason this fixture is declared LAST in this
    file: same-scope autouse fixtures tear down in reverse declaration order, so
    this runs BEFORE `_flush_deferred_deletes` actually destroys the widgets.
    Draining after destruction would be too late -- it would make the crash
    deterministic rather than prevent it. `qtbot`'s own teardown has already
    run, but it only *schedules* deletion via `deleteLater()`, so the receivers
    are still alive here and a drained task delivers harmlessly.
    """
    yield
    leaked = set(async_task._INFLIGHT)
    if not leaked:
        return
    # Drain first, so this test's leak cannot go on to poison a later one even
    # though we are about to fail this one for it.
    QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()
    async_task._INFLIGHT.clear()
    if request.node.get_closest_marker("real_async") is not None:
        return
    pytest.fail(
        f"{len(leaked)} async_task worker(s) were still in flight when this test "
        f"ended; their callbacks would have landed inside an unrelated test and "
        f"failed it instead (BUG-043).\n"
        f"Fix it here, not there: stub the off-thread seam with "
        f"`from tests.ui._sandbox_stubs import sync_run` and "
        f"`window._run_async = sync_run` (the window-wide trampoline reaches "
        f"every lane, sandbox included). If this test exercises the real "
        f"threadpool on purpose, mark it `@pytest.mark.real_async`."
    )
