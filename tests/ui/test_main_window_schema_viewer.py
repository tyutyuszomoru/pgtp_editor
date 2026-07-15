from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import schema_model_path
from pgtp_editor.ui.main_window import MainWindow


def _seed_model(tmp_path):
    model = Model()
    entry, _ = model._get_or_create_path("PGTPProject")
    entry["attributes"]["viewMode"] = {
        "type": "integer",
        "values": ["1", "2"],
        "overflowed": False,
        "attr_seen_count": 2,
        "labels": {},
    }
    model.save(schema_model_path(tmp_path))


def test_open_xsd_viewer_creates_viewer_with_xsd(qtbot, tmp_path):
    _seed_model(tmp_path)
    window = MainWindow(schema_storage_dir=tmp_path)
    qtbot.addWidget(window)

    window._open_xsd_viewer()

    assert window._xsd_viewer is not None
    assert "xs:schema" in window._xsd_viewer.editor.toPlainText()


def test_open_xsd_viewer_reuses_same_window(qtbot, tmp_path):
    _seed_model(tmp_path)
    window = MainWindow(schema_storage_dir=tmp_path)
    qtbot.addWidget(window)

    window._open_xsd_viewer()
    first = window._xsd_viewer
    window._open_xsd_viewer()

    assert window._xsd_viewer is first


def test_open_xsd_viewer_empty_storage_shows_message_and_no_viewer(qtbot, tmp_path):
    window = MainWindow(schema_storage_dir=tmp_path)
    qtbot.addWidget(window)

    window._open_xsd_viewer()

    assert getattr(window, "_xsd_viewer", None) is None
    assert "No schema learned yet" in window.statusBar().currentMessage()


def test_open_labels_viewer_creates_viewer_with_json(qtbot, tmp_path):
    _seed_model(tmp_path)
    window = MainWindow(schema_storage_dir=tmp_path)
    qtbot.addWidget(window)

    window._open_labels_viewer()

    assert window._labels_viewer is not None
    assert "viewMode" in window._labels_viewer.editor.toPlainText()


def test_open_labels_viewer_empty_storage_shows_message_and_no_viewer(qtbot, tmp_path):
    window = MainWindow(schema_storage_dir=tmp_path)
    qtbot.addWidget(window)

    window._open_labels_viewer()

    assert getattr(window, "_labels_viewer", None) is None
    assert "No schema learned yet" in window.statusBar().currentMessage()
