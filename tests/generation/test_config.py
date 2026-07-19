import json

from pgtp_editor.generation.config import (
    DEFAULT_RE_PHPGEN_ROOT,
    generator_config_path,
    load_executable_path,
    load_re_phpgen_root,
    save_executable_path,
    save_re_phpgen_root,
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


def test_re_phpgen_root_defaults_when_unset(tmp_path):
    assert load_re_phpgen_root(base_dir=tmp_path) == DEFAULT_RE_PHPGEN_ROOT


def test_re_phpgen_root_roundtrip(tmp_path):
    save_re_phpgen_root(r"D:\elsewhere\re_phpgen", base_dir=tmp_path)
    assert load_re_phpgen_root(base_dir=tmp_path) == r"D:\elsewhere\re_phpgen"


def test_re_phpgen_root_preserves_executable_key(tmp_path):
    save_executable_path(r"C:\gen.exe", base_dir=tmp_path)
    save_re_phpgen_root(r"D:\re", base_dir=tmp_path)
    assert load_executable_path(base_dir=tmp_path) == r"C:\gen.exe"


def test_re_phpgen_root_defaults_when_file_absent(tmp_path):
    assert not (tmp_path / "generator_config.json").exists()
    assert load_re_phpgen_root(base_dir=tmp_path) == DEFAULT_RE_PHPGEN_ROOT


def test_re_phpgen_root_defaults_when_json_malformed(tmp_path):
    (tmp_path / "generator_config.json").write_text("{not json", encoding="utf-8")
    assert load_re_phpgen_root(base_dir=tmp_path) == DEFAULT_RE_PHPGEN_ROOT


def test_re_phpgen_root_defaults_when_json_not_dict(tmp_path):
    (tmp_path / "generator_config.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert load_re_phpgen_root(base_dir=tmp_path) == DEFAULT_RE_PHPGEN_ROOT


def test_re_phpgen_root_defaults_when_value_wrong_type(tmp_path):
    (tmp_path / "generator_config.json").write_text(
        json.dumps({"re_phpgen_root": 123}), encoding="utf-8"
    )
    assert load_re_phpgen_root(base_dir=tmp_path) == DEFAULT_RE_PHPGEN_ROOT


def test_re_phpgen_root_defaults_when_value_empty_string(tmp_path):
    (tmp_path / "generator_config.json").write_text(
        json.dumps({"re_phpgen_root": ""}), encoding="utf-8"
    )
    assert load_re_phpgen_root(base_dir=tmp_path) == DEFAULT_RE_PHPGEN_ROOT


def test_re_phpgen_root_defaults_when_key_missing(tmp_path):
    (tmp_path / "generator_config.json").write_text(
        json.dumps({"something_else": "x"}), encoding="utf-8"
    )
    assert load_re_phpgen_root(base_dir=tmp_path) == DEFAULT_RE_PHPGEN_ROOT


def test_re_phpgen_root_save_creates_the_directory_if_missing(tmp_path):
    nested = tmp_path / "does" / "not" / "exist"
    save_re_phpgen_root(r"D:\re_phpgen", base_dir=nested)
    assert (nested / "generator_config.json").exists()
    assert load_re_phpgen_root(base_dir=nested) == r"D:\re_phpgen"


def test_re_phpgen_root_save_writes_expected_json_shape(tmp_path):
    save_re_phpgen_root(r"D:\re_phpgen", base_dir=tmp_path)
    data = json.loads((tmp_path / "generator_config.json").read_text(encoding="utf-8"))
    assert data == {"re_phpgen_root": r"D:\re_phpgen"}


def test_re_phpgen_root_save_preserves_unrelated_keys(tmp_path):
    (tmp_path / "generator_config.json").write_text(
        json.dumps({"other": "keep"}), encoding="utf-8"
    )
    save_re_phpgen_root(r"D:\re_phpgen", base_dir=tmp_path)
    data = json.loads((tmp_path / "generator_config.json").read_text(encoding="utf-8"))
    assert data == {"other": "keep", "re_phpgen_root": r"D:\re_phpgen"}


def test_re_phpgen_root_save_overwrites_previous_value(tmp_path):
    save_re_phpgen_root(r"D:\first", base_dir=tmp_path)
    save_re_phpgen_root(r"D:\second", base_dir=tmp_path)
    assert load_re_phpgen_root(base_dir=tmp_path) == r"D:\second"
