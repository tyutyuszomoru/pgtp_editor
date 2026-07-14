import json

from pgtp_editor.generation.config import (
    generator_config_path,
    load_executable_path,
    save_executable_path,
)


def test_generator_config_path_uses_base_dir(tmp_path):
    assert generator_config_path(tmp_path) == tmp_path / "generator_config.json"


def test_save_then_load_round_trip(tmp_path):
    save_executable_path(r"C:\PgGen\PgPHPGeneratorPro.exe", base_dir=tmp_path)
    assert load_executable_path(base_dir=tmp_path) == r"C:\PgGen\PgPHPGeneratorPro.exe"


def test_save_creates_the_directory_if_missing(tmp_path):
    nested = tmp_path / "does" / "not" / "exist"
    save_executable_path("gen.exe", base_dir=nested)
    assert (nested / "generator_config.json").exists()
    assert load_executable_path(base_dir=nested) == "gen.exe"


def test_save_writes_expected_json_shape(tmp_path):
    save_executable_path("gen.exe", base_dir=tmp_path)
    data = json.loads((tmp_path / "generator_config.json").read_text(encoding="utf-8"))
    assert data == {"executable_path": "gen.exe"}


def test_load_returns_none_when_file_absent(tmp_path):
    assert load_executable_path(base_dir=tmp_path) is None


def test_load_returns_none_when_json_malformed(tmp_path):
    (tmp_path / "generator_config.json").write_text("{not json", encoding="utf-8")
    assert load_executable_path(base_dir=tmp_path) is None


def test_load_returns_none_when_key_missing(tmp_path):
    (tmp_path / "generator_config.json").write_text(
        json.dumps({"something_else": "x"}), encoding="utf-8"
    )
    assert load_executable_path(base_dir=tmp_path) is None


def test_save_merges_into_existing_json_preserving_other_keys(tmp_path):
    (tmp_path / "generator_config.json").write_text(
        json.dumps({"other": "keep"}), encoding="utf-8"
    )
    save_executable_path("gen.exe", base_dir=tmp_path)
    data = json.loads((tmp_path / "generator_config.json").read_text(encoding="utf-8"))
    assert data == {"other": "keep", "executable_path": "gen.exe"}
