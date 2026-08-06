"""Tests for `lint/runner.py` -- the argv and the executable resolution.

The spawning itself is deliberately NOT exercised: `tests/lint/conftest.py`
forbids real processes, and everything that depends on the linter's *output*
is covered from canned text in `test_findings.py` / `test_service.py`.
"""
import os
import shutil
import stat

from pgtp_editor.lint.runner import (
    DEFAULT_TIMEOUT_SECONDS,
    LintProcessResult,
    build_php_lint_command,
    resolve_executable,
)


def _make_executable(path):
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_command_is_php_dash_l():
    assert build_php_lint_command("/usr/bin/php", "/tmp/b.php") == [
        "/usr/bin/php",
        "-l",
        "/tmp/b.php",
    ]


def test_command_does_not_pass_dash_n():
    # Linting under a different php.ini than the code runs under produces
    # findings that do not reproduce.
    assert "-n" not in build_php_lint_command("php", "x.php")


def test_default_timeout_is_finite():
    assert 0 < DEFAULT_TIMEOUT_SECONDS <= 60


def test_process_result_defaults():
    result = LintProcessResult(exit_code=0)
    assert result.stdout == "" and result.stderr == "" and result.timed_out is False


# --- resolve_executable ------------------------------------------------------
def test_none_and_blank_resolve_to_none():
    assert resolve_executable(None) is None
    assert resolve_executable("") is None
    assert resolve_executable("   ") is None


def test_an_existing_executable_path_resolves(tmp_path):
    php = _make_executable(tmp_path / "php")
    assert resolve_executable(str(php)) == str(php)


def test_a_missing_path_resolves_to_none(tmp_path):
    assert resolve_executable(str(tmp_path / "nope" / "php")) is None


def test_a_directory_resolves_to_none(tmp_path):
    assert resolve_executable(str(tmp_path)) is None


def test_a_non_executable_file_resolves_to_none(tmp_path):
    plain = tmp_path / "php"
    plain.write_text("not a program", encoding="utf-8")
    plain.chmod(0o644)
    if os.access(plain, os.X_OK):  # Windows: every existing file reads as X_OK
        return
    assert resolve_executable(str(plain)) is None


def test_a_bare_name_is_looked_up_on_path(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/" + name)
    assert resolve_executable("php") == "/usr/bin/php"


def test_a_bare_name_absent_from_path_resolves_to_none(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert resolve_executable("php") is None
