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


# In-flight tasks are held here for their whole lifetime. Without this, the
# _Task (and its _TaskSignals holder) can be garbage-collected once run()
# returns on the worker thread -- before the GUI thread processes the queued
# result/error signal -- so the callback silently never fires and the caller is
# stuck in its busy state forever. Each task removes itself on delivery.
_INFLIGHT: set[_Task] = set()


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn
        self.signals = _TaskSignals()
        # We own the lifetime via _INFLIGHT; don't let the pool delete the C++
        # runnable out from under us the moment run() returns.
        self.setAutoDelete(False)

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

    The worker is retained internally (in ``_INFLIGHT``) until its result/error
    is delivered on the GUI thread, then released -- callers need not keep the
    returned reference alive. Uses ``QThreadPool.globalInstance()`` unless
    ``pool`` is given.
    """
    task = _Task(fn)
    task.signals.result.connect(on_result)
    if on_error is not None:
        task.signals.error.connect(on_error)

    # Release the task AFTER the user callbacks have run (both connections are
    # queued to the GUI thread, delivered in connection order), so it -- and its
    # signals holder -- stay alive across the thread boundary.
    def _release(_ignored=None):
        _INFLIGHT.discard(task)

    task.signals.result.connect(_release)
    task.signals.error.connect(_release)
    _INFLIGHT.add(task)

    (pool or QThreadPool.globalInstance()).start(task)
    return task
