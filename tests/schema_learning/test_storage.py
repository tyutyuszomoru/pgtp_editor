from pathlib import Path

from pgtp_editor.schema_learning.storage import schema_model_path, schema_xsd_path


def test_schema_model_path_uses_given_base_dir(tmp_path):
    result = schema_model_path(tmp_path)
    assert result == tmp_path / "schema_model.json"


def test_schema_xsd_path_uses_given_base_dir(tmp_path):
    result = schema_xsd_path(tmp_path)
    assert result == tmp_path / "schema.xsd"


def test_schema_model_path_defaults_to_real_app_data_location_when_no_base_dir():
    result = schema_model_path()
    assert result.name == "schema_model.json"
    assert isinstance(result, Path)


def test_schema_xsd_path_defaults_to_real_app_data_location_when_no_base_dir():
    result = schema_xsd_path()
    assert result.name == "schema.xsd"
    assert isinstance(result, Path)


def test_schema_model_path_and_schema_xsd_path_share_the_same_directory(tmp_path):
    model_path = schema_model_path(tmp_path)
    xsd_path = schema_xsd_path(tmp_path)
    assert model_path.parent == xsd_path.parent == tmp_path
