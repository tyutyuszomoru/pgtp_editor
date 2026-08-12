# tests/ui/test_ddl_mode_wiring.py
"""MainWindow wiring for the dual-mode DDL verdict (FQ-260812022749 part 1).

`db/pg_dump_mode.py` shipped complete, pure and tested -- and with no caller at
all: nothing probed, nothing reported, and the quality-vs-sandbox major
comparison `server_major_divergence` exists for had never run. These tests pin
the three seams that make it live, and each of them fails against the tree the
module landed in:

* the probe runs **once per quality connection**, never per open (it spawns
  `pg_dump --version`, which `probe()` deliberately refuses to do);
* the `[DDL]` row reaches the Messages tab on **every** DDL open, because the
  owner ruled the notice repeats -- *"this way the choice is clear"*;
* a quality/sandbox major divergence is stated.

No database and no subprocess: `probe_quality_capabilities` and
`ddl_mode_prober` are plain attributes on the window (the same convention as
`DdlProjectController.probe_sandbox_capabilities`) and both are replaced here.
"""
from lxml import etree
import pytest
from PySide6.QtCore import QSettings

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import ProjectSettings, save_settings
from pgtp_editor.db.introspect import DatabaseSchema
from pgtp_editor.db.pg_dump_mode import DdlMode, decide_ddl_mode
from pgtp_editor.db.sandbox import SandboxCapabilities
from pgtp_editor.ui.audit_router import DDL_PREFIX
from pgtp_editor.ui.center_stage import DDL_EXPLORER_TARGET
from pgtp_editor.ui.main_window import MainWindow

from ._sandbox_stubs import sync_run


_TARGET = ConnectionParams(host="h", port="5432", database="d", user="u", password="p")


class _FakeProject:
    def __init__(self, tree):
        self.tree = tree


def _project_with_connection():
    return _FakeProject(
        etree.ElementTree(
            etree.fromstring(
                b'<Project><ConnectionOptions host="h" port="5432" login="u" '
                b'database="d"/></Project>'
            )
        )
    )


def _open(window):
    """One DDL open, as a user performs it.

    Deliberately NOT a bare `_open_ddl_explorer()`: revealing the tab checks the
    Database-menu toggle, whose `toggled` re-enters `_open_ddl_explorer`, so a
    direct call from the unchecked state fetches (and would report) TWICE. That
    re-entrancy predates this feature and is not what these tests are about --
    the toggle and `Reload DDL` are the two real gestures, and each is one open.
    """
    action = window._ddl_explorer_actions[DDL_EXPLORER_TARGET]
    if action.isChecked():
        window.reload_ddl_explorer()
    else:
        action.setChecked(True)


def _ddl_rows(window):
    return [
        text
        for text in window.results_panel.row_texts()
        if text.startswith(DDL_PREFIX)
    ]


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    """A window whose quality DDL Explorer opens with no I/O at all: no schema
    fetch, no capability probe, no `pg_dump --version` spawn."""
    win = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(win)
    win._run_async = sync_run
    win._current_project = _project_with_connection()
    monkeypatch.setattr(win, "_fetch_ddl_schema", lambda params: DatabaseSchema())

    win.probes = []

    def _probe(params, *, bin_dir=None):
        win.probes.append((params, bin_dir))
        return SandboxCapabilities(server_version=(16, 2))

    win.probe_quality_capabilities = _probe
    win.ddl_mode_prober = lambda caps, **kwargs: decide_ddl_mode(
        caps.server_version, "/usr/bin/pg_dump", (16, 4)
    )
    return win


def _open_project(window, tmp_path, **fields):
    settings = ProjectSettings(target=_TARGET, **fields)
    save_settings(tmp_path / "proj", settings)
    window._ddl_project_ui.set_active_project(tmp_path / "proj", settings)
    return settings


def test_the_ddl_row_is_reported_on_every_ddl_open(window):
    """The ruling is *every time*, not once per session and not only when the
    verdict is bad -- so two opens produce two rows."""
    _open(window)
    _open(window)

    rows = _ddl_rows(window)
    assert len(rows) == 2
    assert rows[0] == rows[1]
    assert "Full DDL via pg_dump 16.4 (server 16.2)." in rows[0]


def test_the_probe_runs_once_per_quality_connection_not_per_open(window):
    """`probe_ddl_mode` spawns; the notice does not. The second open reports
    from the cache."""
    _open(window)
    _open(window)
    _open(window)

    assert len(window.probes) == 1
    assert len(_ddl_rows(window)) == 3


def test_a_restricted_verdict_is_reported_just_as_loudly(window):
    window.ddl_mode_prober = lambda caps, **kwargs: decide_ddl_mode(
        caps.server_version, None, None
    )

    _open(window)

    row = _ddl_rows(window)[0]
    assert "Restricted DDL" in row
    assert window._ddl_mode_verdict.mode is DdlMode.RESTRICTED


def test_the_projects_binaries_folder_reaches_the_ddl_mode_probe(window, tmp_path):
    """FQ-260812025353's folder is what `pg_dump` is resolved through here too;
    PATH-only stays `None`, which is the pre-setting behaviour exactly."""
    _open_project(window, tmp_path, postgres_bin_dir="/opt/pg17/bin")

    _open(window)

    assert window.probes[-1][1] == "/opt/pg17/bin"


def test_changing_the_binaries_folder_reprobes(window, tmp_path):
    """A cached verdict names a binary; pointing the project at another one
    must not keep naming the old."""
    _open_project(window, tmp_path, postgres_bin_dir="/opt/pg16/bin")
    _open(window)

    _open_project(window, tmp_path, postgres_bin_dir="/opt/pg17/bin")
    _open(window)

    assert [bin_dir for _params, bin_dir in window.probes] == [
        "/opt/pg16/bin",
        "/opt/pg17/bin",
    ]


def test_a_quality_sandbox_major_divergence_is_reported(window, tmp_path):
    """The owner's principle -- the two databases MUST be the same major --
    was assumed and never enforced until `server_major_divergence` ran."""
    window.sandbox_controller._capabilities = SandboxCapabilities(
        server_version=(15, 6)
    )

    _open(window)

    rows = _ddl_rows(window)
    assert len(rows) == 2
    assert "Quality server is PostgreSQL 16.2" in rows[1]
    assert "sandbox is PostgreSQL 15.6" in rows[1]


def test_matching_majors_say_nothing(window):
    window.sandbox_controller._capabilities = SandboxCapabilities(
        server_version=(16, 0)
    )

    _open(window)

    assert len(_ddl_rows(window)) == 1


def test_an_unknown_sandbox_version_is_not_reported_as_a_divergence(window):
    """"Could not check" must never be spelled the same way as a real mismatch."""
    window.sandbox_controller._capabilities = SandboxCapabilities(
        probe_error="connection refused"
    )

    _open(window)

    assert len(_ddl_rows(window)) == 1


def test_a_failing_mode_probe_never_fails_the_ddl_open(window):
    """A version notice may not cost the user their Explorer."""

    def _boom(params, *, bin_dir=None):
        raise RuntimeError("no")

    window.probe_quality_capabilities = _boom

    _open(window)

    assert _ddl_rows(window) == []
    assert window.center_stage.currentWidget() is not None
