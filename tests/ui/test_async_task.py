# tests/ui/test_async_task.py
"""Tests for the run_async threadpool helper.

Kept fast and robust: trivial in-memory callables only (no network, no DB). Two
tests drive the QRunnable's run()+signal emission directly (no pool, no real
thread) so they cannot flake on scheduling; one test proves the real
QThreadPool path delivers, waiting on the signal and holding the returned task
so it is not garbage-collected before the queued signal arrives.
"""
from pgtp_editor.ui.async_task import _Task, run_async


def test_task_run_emits_result(qtbot):
    task = _Task(lambda: 21 * 2)
    got = []
    task.signals.result.connect(got.append)
    task.run()  # direct call, same thread -- deterministic
    assert got == [42]


def test_task_run_emits_error(qtbot):
    def boom():
        raise ValueError("nope")

    task = _Task(boom)
    errors = []
    task.signals.error.connect(errors.append)
    task.run()
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)
    assert "nope" in str(errors[0])


def test_run_async_delivers_result_via_real_pool(qtbot):
    results = []
    # BUG-012: don't waitSignal on task.signals.result -- run_async starts the
    # worker IMMEDIATELY, and with a trivial callable the signal can fire
    # before waitSignal's spy connects (Qt delivers only to connections
    # existing at emit time), which flaked under parallel (-n 10) CPU load.
    # waitUntil on the on_result side effect is race-free by construction:
    # on_result is connected inside run_async before the pool starts, and this
    # is the same pattern the sibling real-pool tests already use.
    run_async(lambda: 21 * 2, on_result=results.append)
    qtbot.waitUntil(lambda: results == [42], timeout=5000)


def test_run_async_delivers_even_without_caller_reference(qtbot):
    """Production callers discard the returned task, so run_async must retain it
    internally until delivery -- otherwise the callback is silently dropped and
    the caller stays stuck in its busy state. Provoke GC and assert delivery."""
    import gc

    results = []
    run_async(lambda: 7, on_result=results.append)  # return value discarded
    gc.collect()  # would collect the task + signals holder if not retained
    qtbot.waitUntil(lambda: results == [7], timeout=3000)


def test_inflight_set_is_empty_after_delivery(qtbot):
    from pgtp_editor.ui.async_task import _INFLIGHT

    results = []
    run_async(lambda: 1, on_result=results.append)
    qtbot.waitUntil(lambda: results == [1], timeout=3000)
    qtbot.waitUntil(lambda: len(_INFLIGHT) == 0, timeout=3000)
