"""--debug activation: CLI flag, env var, setup ordering seam."""
from pgtp_editor.main import parse_args


def test_parse_args_default_no_debug(monkeypatch):
    monkeypatch.delenv("PGTP_EDITOR_DEBUG", raising=False)
    assert parse_args([]).debug is False


def test_parse_args_debug_flag():
    assert parse_args(["--debug"]).debug is True


def test_parse_args_env_var(monkeypatch):
    monkeypatch.setenv("PGTP_EDITOR_DEBUG", "1")
    assert parse_args([]).debug is True


def test_parse_args_env_var_zero_is_off(monkeypatch):
    monkeypatch.setenv("PGTP_EDITOR_DEBUG", "0")
    assert parse_args([]).debug is False
