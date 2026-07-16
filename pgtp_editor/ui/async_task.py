# pgtp_editor/ui/async_task.py
"""Run a blocking callable off the GUI thread and deliver its result back ON it.

The Database Check opens a PostgreSQL connection; doing that on the GUI thread
freezes the whole window until the connection resolves (or the OS TCP timeout
fires). `run_async` hands the work to a `QThreadPool` worker and marshals the
result — or the exception — back to the GUI thread via queued signals, so the
callbacks run where it is safe to touch widgets.

Kept deliberately tiny and Qt-only (no DB knowledge): `db/` stays pure logic,
this lives in `ui/`. Tests inject a synchronous stand-in for `run_async` on the
window/dialog rather than spinning real threads, so the suite is deterministic;
one focused test here proves the real threadpool path delivers.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _TaskSignals(QObject):
    # object (not a concrete type) so any return value / exception rides across.
    result = Signal(object)
    error = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn
        self.signals = _TaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            value = self._fn()
        except Exception as exc:  # noqa: BLE001 — any failure is delivered, not raised
            self.signals.error.emit(exc)
        else:
            self.signals.result.emit(value)


def run_async(
    fn: Callable[[], Any],
    on_result: Callable[[Any], None],
    on_error: Callable[[BaseException], None] | None = None,
    pool: QThreadPool | None = None,
) -> _Task:
    """Run ``fn()`` on a threadpool worker; deliver back on the GUI thread.

    ``on_result(value)`` fires on success, ``on_error(exc)`` on failure. Because
    the receivers live on the GUI thread and the signals cross threads, Qt uses
    a queued connection, so both callbacks run on the GUI thread — safe to touch
    widgets. Uses ``QThreadPool.globalInstance()`` unless ``pool`` is given.

    Returns the worker so a caller may keep a reference if desired; the
    threadpool owns and auto-deletes it after ``run`` completes.
    """
    task = _Task(fn)
    task.signals.result.connect(on_result)
    if on_error is not None:
        task.signals.error.connect(on_error)
    (pool or QThreadPool.globalInstance()).start(task)
    return task
