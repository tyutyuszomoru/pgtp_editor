# tests/db/test_pg_dump_mode.py
"""Tests for the dual-mode DDL verdict (FQ-260812022749 Part 1).

**No test here spawns a process or reaches a database** — `decide_ddl_mode` is
pure, and `probe_ddl_mode` takes the `Which`/`ProcessRunner` seams that
`db/sandbox.py` already owns.
"""
import subprocess

from pgtp_editor.db.pg_dump_mode import (
    REASON_ABSENT,
    REASON_OK,
    REASON_OLDER,
    REASON_UNKNOWN_SERVER,
    REASON_UNREADABLE,
    RESTRICTED_CLONE_WARNING,
    DdlMode,
    decide_ddl_mode,
    probe_ddl_mode,
    server_major_divergence,
)
from pgtp_editor.db.sandbox import SandboxCapabilities


def _which_stub(present):
    return lambda name: present.get(name)


def _runner(stdout=b"pg_dump (PostgreSQL) 16.2\n", returncode=0):
    def run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=b"")

    return run


# --- the version rule: pg_dump major >= server major -------------------------
def test_equal_majors_are_full_mode():
    verdict = decide_ddl_mode((16, 0, 3), "/usr/bin/pg_dump", (16, 2))
    assert verdict.mode is DdlMode.FULL
    assert verdict.reason == REASON_OK
    assert verdict.full is True


def test_a_newer_pg_dump_is_full_mode_not_a_mismatch():
    """pg_dump dumps happily from an OLDER server; only newer-than-pg_dump is
    refused. Newer-than-server must never be reported as a problem."""
    assert decide_ddl_mode((15, 0, 6), "/usr/bin/pg_dump", (18, 0)).mode is DdlMode.FULL


def test_one_major_older_is_the_boundary_that_falls_back():
    verdict = decide_ddl_mode((17, 0, 1), "/usr/bin/pg_dump", (16, 9))
    assert verdict.mode is DdlMode.RESTRICTED
    assert verdict.reason == REASON_OLDER


def test_a_higher_minor_does_not_rescue_an_older_major():
    """The comparison is on the MAJOR only — pg_dump 16.9 still refuses a 17.0
    server."""
    assert decide_ddl_mode((17, 0, 0), "/usr/bin/pg_dump", (16, 99)).mode is DdlMode.RESTRICTED


def test_a_lower_minor_on_an_equal_major_is_still_full():
    assert decide_ddl_mode((16, 0, 9), "/usr/bin/pg_dump", (16, 0)).mode is DdlMode.FULL


# --- the three shapes, and both numbers in every message ---------------------
def test_absent_pg_dump_is_restricted_and_names_both_versions():
    verdict = decide_ddl_mode((16, 0, 3), None, None)
    assert verdict.mode is DdlMode.RESTRICTED
    assert verdict.reason == REASON_ABSENT
    assert "16.0.3" in verdict.message
    assert "unknown" in verdict.message  # the pg_dump number, honestly absent
    assert RESTRICTED_CLONE_WARNING in verdict.message


def test_older_pg_dump_message_names_both_numbers_and_the_refusal():
    verdict = decide_ddl_mode((17, 0, 1), "/usr/bin/pg_dump", (15, 6))
    assert "15.6" in verdict.message
    assert "17.0.1" in verdict.message
    assert "older" in verdict.message
    assert "refuse" in verdict.message


def test_full_mode_message_names_both_numbers():
    verdict = decide_ddl_mode((16, 0, 3), "/usr/bin/pg_dump", (17, 2))
    assert verdict.message == "Full DDL via pg_dump 17.2 (server 16.0.3)."


def test_full_mode_message_carries_no_clone_warning():
    verdict = decide_ddl_mode((16, 0, 3), "/usr/bin/pg_dump", (16, 2))
    assert RESTRICTED_CLONE_WARNING not in verdict.message


def test_an_unreadable_version_degrades_rather_than_guessing():
    verdict = decide_ddl_mode((16, 0, 3), "/usr/bin/pg_dump", None)
    assert verdict.mode is DdlMode.RESTRICTED
    assert verdict.reason == REASON_UNREADABLE
    assert "/usr/bin/pg_dump" in verdict.message
    assert "16.0.3" in verdict.message


def test_an_unknown_server_version_degrades_rather_than_guessing():
    verdict = decide_ddl_mode((), "/usr/bin/pg_dump", (17, 2))
    assert verdict.mode is DdlMode.RESTRICTED
    assert verdict.reason == REASON_UNKNOWN_SERVER
    assert "17.2" in verdict.message


def test_every_restricted_message_warns_against_cloning():
    for verdict in (
        decide_ddl_mode((16,), None, None),
        decide_ddl_mode((17,), "/x/pg_dump", (15,)),
        decide_ddl_mode((16,), "/x/pg_dump", None),
        decide_ddl_mode((), "/x/pg_dump", (16,)),
    ):
        assert verdict.mode is DdlMode.RESTRICTED
        assert RESTRICTED_CLONE_WARNING in verdict.message


def test_the_verdict_carries_both_numbers_as_data_not_only_as_prose():
    verdict = decide_ddl_mode((16, 0, 3), "/usr/bin/pg_dump", (17, 2))
    assert verdict.server_version == (16, 0, 3)
    assert verdict.pg_dump_version == (17, 2)
    assert verdict.pg_dump_path == "/usr/bin/pg_dump"


# --- probe_ddl_mode: composition over the existing seams ---------------------
def test_probe_ddl_mode_finds_pg_dump_in_the_configured_folder(tmp_path):
    binary = tmp_path / "pg_dump"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")

    verdict = probe_ddl_mode(
        SandboxCapabilities(server_version=(16, 0, 3)),
        bin_dir=str(tmp_path),
        which=_which_stub({}),
        run=_runner(b"pg_dump (PostgreSQL) 16.2\n"),
    )

    assert verdict.mode is DdlMode.FULL
    assert verdict.pg_dump_path == str(binary)


def test_probe_ddl_mode_falls_back_to_path(tmp_path):
    verdict = probe_ddl_mode(
        SandboxCapabilities(server_version=(16, 0, 3)),
        bin_dir=str(tmp_path),
        which=_which_stub({"pg_dump": "/usr/bin/pg_dump"}),
        run=_runner(),
    )
    assert verdict.pg_dump_path == "/usr/bin/pg_dump"
    assert verdict.mode is DdlMode.FULL


def test_probe_ddl_mode_reports_an_absent_binary_without_spawning():
    def run(argv, **kwargs):  # pragma: no cover -- must never be reached
        raise AssertionError("nothing to run")

    verdict = probe_ddl_mode(
        SandboxCapabilities(server_version=(16, 0, 3)),
        which=_which_stub({}),
        run=run,
    )

    assert verdict.reason == REASON_ABSENT


def test_probe_ddl_mode_reports_a_folder_binary_that_is_too_old(tmp_path):
    (tmp_path / "pg_dump").write_text("#!/bin/sh\n", encoding="utf-8")

    verdict = probe_ddl_mode(
        SandboxCapabilities(server_version=(17, 0, 1)),
        bin_dir=str(tmp_path),
        which=_which_stub({}),
        run=_runner(b"pg_dump (PostgreSQL) 15.6\n"),
    )

    assert verdict.mode is DdlMode.RESTRICTED
    assert verdict.reason == REASON_OLDER
    assert "15.6" in verdict.message and "17.0.1" in verdict.message


def test_probe_ddl_mode_never_raises_when_the_process_explodes():
    def run(argv, **kwargs):
        raise OSError("exec format error")

    verdict = probe_ddl_mode(
        SandboxCapabilities(server_version=(16, 0, 3)),
        which=_which_stub({"pg_dump": "/usr/bin/pg_dump"}),
        run=run,
    )

    assert verdict.mode is DdlMode.RESTRICTED
    assert verdict.reason == REASON_UNREADABLE


def test_probe_ddl_mode_re_resolves_rather_than_trusting_a_stale_caps_path(tmp_path):
    """`caps.pg_dump_path` may have been probed before the binaries folder was
    set. Two resolutions that can disagree is how a "which one is right?" bug
    is manufactured."""
    binary = tmp_path / "pg_dump"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")

    verdict = probe_ddl_mode(
        SandboxCapabilities(server_version=(16,), pg_dump_path="/stale/pg_dump"),
        bin_dir=str(tmp_path),
        which=_which_stub({}),
        run=_runner(),
    )

    assert verdict.pg_dump_path == str(binary)


def test_a_failed_capability_probe_still_produces_a_restricted_verdict():
    verdict = probe_ddl_mode(
        SandboxCapabilities(probe_error="could not connect"),
        which=_which_stub({"pg_dump": "/usr/bin/pg_dump"}),
        run=_runner(),
    )
    assert verdict.mode is DdlMode.RESTRICTED
    assert verdict.reason == REASON_UNKNOWN_SERVER


# --- the one version rule, applied across the two servers --------------------
def test_matching_majors_report_nothing():
    assert server_major_divergence((16, 0, 3), (16, 2, 1)) is None


def test_diverging_majors_are_reported_with_both_numbers():
    message = server_major_divergence((17, 0, 1), (15, 6))
    assert message is not None
    assert "17.0.1" in message and "15.6" in message
    assert "same major version" in message


def test_an_unknown_version_is_could_not_check_not_a_divergence():
    assert server_major_divergence((), (15, 6)) is None
    assert server_major_divergence((16, 2), ()) is None
