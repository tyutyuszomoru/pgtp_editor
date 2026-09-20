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
from pgtp_editor.ui import main_window as main_window_module
from pgtp_editor.db.pg_dump_ddl import SchemaDumpError
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

    Drives the toggle / `Reload DDL` because those are the two real gestures,
    and each is one open.

    This helper used to carry a warning that a bare `_open_ddl_explorer()`
    fetches TWICE, because the lockstep's `setChecked(True)` re-entered the
    opener from an unchecked action. That was true and is now FIXED
    (BUG-260812071208, `_ddl_explorer_syncing`): a direct call is one open too.
    The comment is corrected rather than kept, so it does not preserve a false
    fact about the code.
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
    # This fixture's verdict is FULL, so the buffer layer now asks for a
    # `pg_dump --schema-only`. Stubbing it keeps the fixture's promise of no I/O
    # at all (the conftest seam raises, which would add a degrade row and change
    # what these tests count). The schema is empty, so a preamble-only dump
    # leaves no relation unattributed and therefore no degrade.
    win.dumps = []

    def _dump(params, pg_dump_path, **kwargs):
        win.dumps.append((params, pg_dump_path))
        return "SET statement_timeout = 0;\n"

    monkeypatch.setattr(main_window_module, "fetch_schema_dump", _dump)
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


# ---------------------------------------------------------------------------
# FQ-260812022749 part 3: the dual-mode BUFFER, wired.
#
# The verdict was already reported before this; what these pin is the half that
# actually spawns and actually changes what the user reads -- when `pg_dump` is
# invoked, how often, what happens when it refuses, and that the tree and the
# text agree because they come from ONE buffer.
# ---------------------------------------------------------------------------

def test_a_RESTRICTED_verdict_SPAWNS_NOTHING(window):
    """The invariant the whole degrade design rests on: restricted mode is the
    buffer it always was and costs no subprocess at all. A dump taken and then
    ignored would be a silent multi-second cost on every open on exactly the
    servers that cannot use it.

    The verdict deliberately CARRIES a `pg_dump_path`: an old `pg_dump` beside
    a newer server is restricted *with* a located binary, which is the only
    shape that can distinguish "the mode decides" from "a path was found". A
    restriction with no path at all would pass against a gate that never read
    the mode."""
    window.ddl_mode_prober = lambda caps, **kwargs: decide_ddl_mode(
        caps.server_version, "/usr/bin/pg_dump", (14, 1)
    )

    _open(window)
    _open(window)

    verdict = window._ddl_mode_verdict
    assert verdict.mode is DdlMode.RESTRICTED
    assert verdict.pg_dump_path == "/usr/bin/pg_dump"  # located, and unused
    assert window.dumps == []


def test_an_open_takes_EXACTLY_ONE_dump(window):
    """One `pg_dump --schema-only` per Explorer build, no more -- and the count
    is per OPEN, so BUG-260812071208's doubled open would show up here as a
    doubled dump even though its own regression net counts introspections.
    That is the point of asserting it on this side too: the dump is the
    expensive half."""
    _open(window)
    assert len(window.dumps) == 1

    _open(window)
    assert len(window.dumps) == 2

    # ...and it is this connection's own dump, not a cached one from elsewhere.
    assert {params.database for params, _path in window.dumps} == {"d"}
    assert {path for _params, path in window.dumps} == {"/usr/bin/pg_dump"}


def test_a_REFUSED_dump_degrades_with_a_NAMED_row_and_still_opens(window, monkeypatch):
    """A refused or timed-out `pg_dump` may never cost the user their Explorer:
    it degrades to the restricted buffer and SAYS SO, naming the refusal."""
    def _refuse(params, pg_dump_path, **kwargs):
        raise SchemaDumpError(
            "pg_dump --schema-only", 1, "permission denied for schema pr"
        )

    monkeypatch.setattr(main_window_module, "fetch_schema_dump", _refuse)

    _open(window)

    rows = _ddl_rows(window)
    assert len(rows) == 2
    assert "permission denied for schema pr" in rows[1]
    assert "pg_dump --schema-only" in rows[1]
    # The Explorer opened anyway, with a real (restricted) buffer in it.
    assert window.center_stage.currentIndex() == window.center_stage.ddl_tab_index
    assert window.center_stage.isTabVisible(window.center_stage.ddl_tab_index)


def test_the_degrade_row_sits_BESIDE_the_mode_row_not_instead_of_it(window, monkeypatch):
    """Order and coexistence, both load-bearing: the mode row is an owner ruling
    on every open and the degrade is additional information, so a degrade must
    not swallow, replace or precede it."""
    def _refuse(params, pg_dump_path, **kwargs):
        raise SchemaDumpError("pg_dump --schema-only", 1, "timed out after 60s")

    monkeypatch.setattr(main_window_module, "fetch_schema_dump", _refuse)

    _open(window)

    rows = _ddl_rows(window)
    assert "Full DDL via pg_dump 16.4 (server 16.2)." in rows[0]
    assert "timed out" in rows[1]
    assert "timed out" not in rows[0]


def test_an_unexpected_dump_failure_is_degraded_too_not_raised(window, monkeypatch):
    """`SchemaDumpError` is the shipped refusal, but the open must survive
    anything the seam throws -- an OSError from a half-installed binary is not a
    reason to lose the Explorer."""
    def _explode(params, pg_dump_path, **kwargs):
        raise OSError("Permission denied: /usr/bin/pg_dump")

    monkeypatch.setattr(main_window_module, "fetch_schema_dump", _explode)

    _open(window)

    rows = _ddl_rows(window)
    assert len(rows) == 2
    assert "/usr/bin/pg_dump" in rows[1]
    assert window.center_stage.isTabVisible(window.center_stage.ddl_tab_index)


# -- the tree and the text are ONE buffer -----------------------------------

_FULL_DUMP = """SET statement_timeout = 0;

CREATE TABLE pr.orders (
    id integer NOT NULL,
    tag text
);

CREATE INDEX ix_tag ON pr.orders USING btree (tag);
"""


def _orders_schema():
    from pgtp_editor.db.introspect import ColumnInfo, TableInfo

    return DatabaseSchema(
        tables={
            "pr.orders": TableInfo(
                name="pr.orders",
                kind="table",
                columns=[
                    ColumnInfo(
                        name="id", data_type="integer", is_pk=True, is_fk=False,
                        is_nullable=False, default=None,
                    ),
                    ColumnInfo(
                        name="tag", data_type="text", is_pk=False, is_fk=False,
                        is_nullable=True, default=None,
                    ),
                ],
            )
        }
    )


def test_in_FULL_mode_the_editor_shows_pg_dumps_OWN_text(window, monkeypatch):
    """The user-visible half of the feature: what is on screen after a full-mode
    open is the dump's statements, not the synthesizer's reconstruction."""
    monkeypatch.setattr(window, "_fetch_ddl_schema", lambda params: _orders_schema())
    monkeypatch.setattr(
        main_window_module, "fetch_schema_dump", lambda *a, **k: _FULL_DUMP
    )

    _open(window)

    text = window.center_stage.ddl_editor_panel.editor.toPlainText()
    assert "CREATE INDEX ix_tag ON pr.orders USING btree (tag);" in text
    assert "-- NOTE: reconstructed by PGTP Editor" not in text
    # A dump that attributes every relation degrades nothing, so the mode row
    # stands alone -- the anchor that keeps the assertion above from passing on
    # a silently degraded buffer that happened to contain the string.
    assert len(_ddl_rows(window)) == 1


def test_the_TREE_navigates_into_the_SAME_full_mode_buffer(window, monkeypatch):
    """The tree is handed `buffer.spans` -- the very list the text was rendered
    with -- so clicking a relation in full mode lands on the DUMP's own
    `CREATE TABLE`, at a line number derived from the dump. Handing the tree a
    separately-built span list would put the caret on a plausible wrong line,
    which is the failure this asserts against by reading the landed line back
    out of the editor.

    The caret lands on the object's banner, not on `CREATE TABLE` itself: full
    mode keeps the banner and DELIBERATELY drops containment (owner-settled,
    2026-08-12), so the table's span is its banner plus the dump's own
    `CREATE TABLE`, and the separately-emitted index is outside it."""
    monkeypatch.setattr(window, "_fetch_ddl_schema", lambda params: _orders_schema())
    monkeypatch.setattr(
        main_window_module, "fetch_schema_dump", lambda *a, **k: _FULL_DUMP
    )

    _open(window)

    panel = window._ddl_browser_panels[DDL_EXPLORER_TARGET]
    table_item = panel.tree.topLevelItem(0).child(0)
    panel._on_item_clicked(table_item, 0)

    editor = window.center_stage.ddl_editor_panel.editor
    lines = editor.toPlainText().splitlines()
    landed = editor.textCursor().blockNumber()  # 0-based

    assert lines[landed] == "-- TABLE pr.orders --"
    # The text under that banner is the DUMP's statement, verbatim -- the
    # restricted synthesizer renders the same table with a `NOT NULL` column
    # list of its own and a reconstruction notice, so this line pair can only
    # come from the full-mode buffer the tree was handed spans for.
    following = lines[landed + 1: landed + 6]
    assert "CREATE TABLE pr.orders (" in following
    assert "    id integer NOT NULL," in following
    assert "-- NOTE: reconstructed by PGTP Editor" not in editor.toPlainText()


# ---------------------------------------------------------------------------
# BUG-260812110307: a discarded fetch is not an open.
# ---------------------------------------------------------------------------

def test_a_fetch_discarded_by_a_close_reports_no_ddl_row(window):
    """The owner's ruling is "report the mode on EVERY DDL open"; this NARROWS
    it to "every open that REVEALS a panel", deliberately.

    A fetch the user closed out from under paints nothing, so a mode notice for
    it would describe a panel that is not there. BUG-260812071208's invariant is
    preserved exactly rather than reversed: one open, one fetch, one row — and a
    discarded fetch was not an open.
    """
    queued = []
    window._run_async = lambda fn, on_result, on_error=None: queued.append(
        (fn, on_result)
    )
    action = window._ddl_explorer_actions[DDL_EXPLORER_TARGET]

    action.setChecked(True)
    action.setChecked(False)  # closed while the fetch is out
    fn, on_result = queued[0]
    on_result(fn())

    assert _ddl_rows(window) == []


def test_the_next_real_open_after_a_discarded_one_still_reports_exactly_one_row(
    window,
):
    """The other half, and the one that proves the narrowing did not become a
    swallowed notice: the sentence still appears on the next real open — read
    from the probe cache the discarded result KEPT, so it costs no second
    `pg_dump --version` and no second probe connection."""
    queued = []
    window._run_async = lambda fn, on_result, on_error=None: queued.append(
        (fn, on_result)
    )
    action = window._ddl_explorer_actions[DDL_EXPLORER_TARGET]
    action.setChecked(True)
    action.setChecked(False)
    fn, on_result = queued[0]
    on_result(fn())
    assert len(window.probes) == 1  # the discarded fetch did probe

    window._run_async = sync_run
    _open(window)

    assert len(_ddl_rows(window)) == 1
    # No SECOND probe: the verdict cache is connection-scoped and survives the
    # close, which is why nothing is re-spawned to say the same sentence.
    assert len(window.probes) == 1
