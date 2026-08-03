# tests/db/test_sandbox.py
"""Tests for pgtp_editor.db.sandbox -- the capability probe slice of §18.5 D2
(reused as-is by §18.2's New Project "Test superuser" button). psycopg is
never imported here: `probe` takes an injected `runner=` callable.
"""
from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.sandbox import PROBE_SQL, SandboxCapabilities, probe

_PARAMS = ConnectionParams(host="h", port="5432", database="d", user="u", password="s3cr3t")


def _canned_runner(
    version="160003",
    is_superuser="on",
    installed=(),
    available=("plpgsql_check",),
    database="sandbox_db",
    owner_marker=None,
):
    def runner(params, sql_list):
        assert list(sql_list) == PROBE_SQL
        return [
            [(version,)],
            [(is_superuser,)],
            [(name,) for name in installed],
            [(name,) for name in available],
            [(database, owner_marker)],
        ]

    return runner


def test_probe_decodes_server_version_and_superuser():
    caps = probe(_PARAMS, runner=_canned_runner())
    assert caps.server_version == (16, 0, 3)
    assert caps.is_superuser is True
    assert caps.probe_error is None


def test_probe_non_superuser_reads_false_not_a_permission_error():
    caps = probe(_PARAMS, runner=_canned_runner(is_superuser="off"))
    assert caps.is_superuser is False


def test_probe_collects_installed_and_available_extensions():
    caps = probe(
        _PARAMS,
        runner=_canned_runner(installed=("pgcrypto",), available=("pgcrypto", "plpgsql_check")),
    )
    assert caps.installed_extensions == frozenset({"pgcrypto"})
    assert caps.available_extensions == frozenset({"pgcrypto", "plpgsql_check"})


def test_probe_reads_database_name_and_owner_marker():
    caps = probe(_PARAMS, runner=_canned_runner(database="pgtp_sandbox_abc", owner_marker="pgtp_editor"))
    assert caps.database == "pgtp_sandbox_abc"
    assert caps.owner_marker == "pgtp_editor"


def test_probe_owner_marker_may_be_none():
    caps = probe(_PARAMS, runner=_canned_runner(owner_marker=None))
    assert caps.owner_marker is None


def test_probe_never_raises_on_a_failing_runner():
    def failing_runner(params, sql_list):
        raise RuntimeError("could not connect to server")

    caps = probe(_PARAMS, runner=failing_runner)

    assert caps.probe_error == "could not connect to server"
    assert caps.is_superuser is False  # every other field left at its default
    assert caps.server_version == ()


def test_probe_never_raises_on_malformed_rows():
    def malformed_runner(params, sql_list):
        return [[("not-a-number",)], [("on",)], [], [], [("db", None)]]

    caps = probe(_PARAMS, runner=malformed_runner)

    assert caps.probe_error is not None


# --- SandboxCapabilities.plpgsql_check_state ---------------------------------
def test_plpgsql_check_state_installed_when_in_installed_extensions():
    caps = SandboxCapabilities(installed_extensions=frozenset({"plpgsql_check"}))
    assert caps.plpgsql_check_state == "installed"


def test_plpgsql_check_state_installable_when_only_available():
    caps = SandboxCapabilities(available_extensions=frozenset({"plpgsql_check"}))
    assert caps.plpgsql_check_state == "installable"


def test_plpgsql_check_state_absent_when_neither_installed_nor_available():
    caps = SandboxCapabilities()
    assert caps.plpgsql_check_state == "absent"


def test_plpgsql_check_state_unknown_on_probe_error_never_degrades_to_absent():
    """A probe failure must read as "could not check", never as "genuinely
    not there" -- even if installed_extensions defaults to empty."""
    caps = SandboxCapabilities(probe_error="connection refused")
    assert caps.plpgsql_check_state == "unknown"


def test_plpgsql_check_state_unknown_wins_even_if_extensions_look_installed():
    """probe_error must win regardless of what other fields happen to hold
    (defensive: a caller must never partially trust a failed probe)."""
    caps = SandboxCapabilities(
        installed_extensions=frozenset({"plpgsql_check"}), probe_error="timed out"
    )
    assert caps.plpgsql_check_state == "unknown"


# --- Injected seam, no psycopg ------------------------------------------------
def test_probe_module_imports_no_psycopg():
    import ast
    from pathlib import Path

    import pgtp_editor.db.sandbox as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any("psycopg" in name for name in imported)
