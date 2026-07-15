from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import schema_model_path, schema_xsd_path
from pgtp_editor.ui.schema_viewer_data import open_labels_text, open_xsd_text


def _seed_model():
    model = Model()
    entry, _ = model._get_or_create_path("PGTPProject")
    entry["attributes"]["viewMode"] = {
        "type": "integer",
        "values": ["1", "2"],
        "overflowed": False,
        "attr_seen_count": 2,
        "labels": {},
    }
    return model


def test_open_xsd_text_returns_none_when_neither_file_exists(tmp_path):
    assert open_xsd_text(tmp_path) is None


def test_open_xsd_text_generates_from_model_when_only_model_exists(tmp_path):
    model = _seed_model()
    model.save(schema_model_path(tmp_path))

    text = open_xsd_text(tmp_path)

    assert text is not None
    assert text.startswith("<?xml")
    assert "xs:schema" in text


def test_open_xsd_text_returns_xsd_file_verbatim_when_present(tmp_path):
    model = _seed_model()
    model.save(schema_model_path(tmp_path))
    xsd_path = schema_xsd_path(tmp_path)
    xsd_path.write_text("<?xml version='1.0'?><custom/>", encoding="utf-8")

    text = open_xsd_text(tmp_path)

    assert text == "<?xml version='1.0'?><custom/>"


def test_open_labels_text_returns_none_when_model_absent(tmp_path):
    assert open_labels_text(tmp_path) is None


def test_open_labels_text_returns_json_text_when_model_exists(tmp_path):
    model = _seed_model()
    model.save(schema_model_path(tmp_path))

    text = open_labels_text(tmp_path)

    assert text is not None
    assert text == schema_model_path(tmp_path).read_text(encoding="utf-8")
    assert "viewMode" in text
