"""Tests for `lint/config.py` -- §22's `lint_executable_path`, stored in the
same `generator_config.json` §19 already owns."""
import json

from pgtp_editor.generation.config import (
    generator_config_path,
    load_executable_path,
    save_executable_path,
)
from pgtp_editor.lint.config import (
    lint_config_path,
    load_lint_executable_path,
    save_lint_executable_path,
)


def test_it_is_literally_the_same_config_file_as_generation(tmp_path):
    assert lint_config_path(tmp_path) == generator_config_path(tmp_path)


def test_roundtrip(tmp_path):
    save_lint_executable_path("/usr/bin/php", tmp_path)
    assert load_lint_executable_path(tmp_path) == "/usr/bin/php"
    data = json.loads(lint_config_path(tmp_path).read_text(encoding="utf-8"))
    assert data["lint_executable_path"] == "/usr/bin/php"


def test_absent_file_returns_none(tmp_path):
    assert load_lint_executable_path(tmp_path / "nope") is None


def test_malformed_file_returns_none_instead_of_raising(tmp_path):
    lint_config_path(tmp_path).write_text("{not json", encoding="utf-8")
    assert load_lint_executable_path(tmp_path) is None


def test_key_missing_returns_none(tmp_path):
    save_executable_path("/opt/phpgen.exe", tmp_path)
    assert load_lint_executable_path(tmp_path) is None


def test_empty_string_counts_as_unconfigured(tmp_path):
    save_lint_executable_path("", tmp_path)
    assert load_lint_executable_path(tmp_path) is None


def test_saving_the_linter_preserves_the_generator_path(tmp_path):
    save_executable_path("/opt/phpgen.exe", tmp_path)
    save_lint_executable_path("/usr/bin/php", tmp_path)
    assert load_executable_path(tmp_path) == "/opt/phpgen.exe"
    assert load_lint_executable_path(tmp_path) == "/usr/bin/php"


def test_saving_the_generator_preserves_the_linter_path(tmp_path):
    save_lint_executable_path("/usr/bin/php", tmp_path)
    save_executable_path("/opt/phpgen.exe", tmp_path)
    assert load_lint_executable_path(tmp_path) == "/usr/bin/php"
