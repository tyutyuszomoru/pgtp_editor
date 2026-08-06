# tests/ui/_sandbox_stubs.py
"""Shared stubs for the §18.2 New Project sandbox step (FQ-007).

Creating a project with a sandbox connection now **creates and provisions the
sandbox database** through `MainWindow.sandbox_controller`. Every `db/sandbox.py`
entry point on that controller is an injected seam; this module replaces all of
them (plus the controller's off-thread runner) so a MainWindow test can exercise
project creation without a single real connection, `CREATE DATABASE`, `pg_dump`
or background thread.

Import and call `stub_sandbox_provisioning(window)` right after building the
window, before any `_create_ddl_project` call.
"""
from __future__ import annotations

from types import SimpleNamespace

from pgtp_editor.db.introspect import BaselineSnapshot


def sync_run(fn, on_result, on_error=None):
    """The suite's usual synchronous stand-in for `ui/async_task.py::run_async`."""
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001 -- mirrors run_async's error channel
        (on_error or (lambda _e: None))(exc)


def fake_session(params=None, schema_names=frozenset(), applied_rows=()):
    """The minimum a `SandboxSession` stand-in needs for the provisioning path:
    the params it was opened on and the schema set the controller records.

    `applied()` and `executor` are here because two other surfaces read them off
    a live session -- `ui/sandbox_setup_dialog.py`'s working-set table and
    `db/ddl_check.py`'s `CheckSession` protocol -- and a stub that lacks them
    makes the dialog raise inside a Qt slot rather than fail a test.
    """
    return SimpleNamespace(
        params=params,
        schema_names=schema_names,
        mode=None,
        executor=None,
        applied=lambda: list(applied_rows),
    )


def stub_sandbox_provisioning(window, *, created=None):
    """Make `window`'s sandbox controller provision entirely in-memory.

    Returns the list every created database name is appended to, so a test can
    assert *which* auto-generated name was used without reaching a server.
    """
    controller = window.sandbox_controller
    created = [] if created is None else created
    controller._run_async = sync_run
    controller._database_creator = lambda admin_params, name: created.append(name)
    controller._snapshotter = lambda target_params: BaselineSnapshot()
    controller._provisioner = lambda snapshot, params, mode, **kwargs: fake_session(params)
    controller._opener = lambda params, **kwargs: fake_session(params)
    controller._installer = lambda session: None
    controller._cloner = lambda target_params, sandbox_params: None
    return created
