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
    # Hold the returned task: the threadpool auto-deletes the runnable after
    # run(), and dropping our reference could GC the signals holder before the
    # queued result is delivered on the GUI thread.
    task = run_async(lambda: 21 * 2, on_result=results.append)
    with qtbot.waitSignal(task.signals.result, timeout=3000):
        pass
    assert results == [42]
