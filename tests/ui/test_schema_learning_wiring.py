"""Tests for the schema-learning auto-enrich wiring on MainWindow.open_project_file.

These use MainWindow(schema_storage_dir=tmp_path) so the schema model/XSD
are written to an isolated per-test directory, never the real user's
AppData location.
"""
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import schema_model_path, schema_xsd_path
from pgtp_editor.ui.main_window import MainWindow

VALID_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
        <EventHandlers>
          <OnPreparePage>echo 'hi';</OnPreparePage>
        </EventHandlers>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""

MALFORMED_PGTP = "<Project><Presentation><Pages><Page></Pages></Presentation></Project>"


def test_open_project_file_creates_schema_model_and_xsd_on_success(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    project_path = tmp_path / "valid.pgtp"
    project_path.write_text(VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(project_path))

    model_path = schema_model_path(storage_dir)
    xsd_path = schema_xsd_path(storage_dir)
    assert model_path.exists()
    assert xsd_path.exists()

    model = Model.load(model_path)
    assert "Project" in model.paths


def test_open_project_file_appends_audit_entries_on_success(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    project_path = tmp_path / "valid.pgtp"
    project_path.write_text(VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(project_path))

    assert window.audit_panel.count() >= 1
    first_entry_text = window.audit_panel.item(0).text()
    assert first_entry_text.startswith("[Schema]")


def test_second_open_of_same_shape_file_reuses_and_grows_existing_model(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    project_path = tmp_path / "valid.pgtp"
    project_path.write_text(VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(project_path))
    model_path = schema_model_path(storage_dir)
    first_mtime_ns = model_path.stat().st_mtime_ns

    window.audit_panel.clear()
    window.open_project_file(str(project_path))

    # Re-opening the identical file merges into the *same* model file
    # (still exists, was rewritten) rather than creating a second one.
    assert model_path.exists()
    assert model_path.stat().st_mtime_ns >= first_mtime_ns


def test_parse_failure_does_not_create_schema_model_file(qtbot, tmp_path):
    from unittest.mock import patch

    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    broken_path = tmp_path / "broken.pgtp"
    broken_path.write_text(MALFORMED_PGTP, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(broken_path))

    model_path = schema_model_path(storage_dir)
    xsd_path = schema_xsd_path(storage_dir)
    assert not model_path.exists()
    assert not xsd_path.exists()


def test_parse_failure_leaves_pre_seeded_schema_model_byte_for_byte_unchanged(qtbot, tmp_path):
    from unittest.mock import patch

    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True)
    model_path = schema_model_path(storage_dir)
    seeded_content = '{\n  "paths": {}\n}'
    model_path.write_text(seeded_content, encoding="utf-8")
    mtime_before = model_path.stat().st_mtime_ns

    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    broken_path = tmp_path / "broken.pgtp"
    broken_path.write_text(MALFORMED_PGTP, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(broken_path))

    assert model_path.read_text(encoding="utf-8") == seeded_content
    assert model_path.stat().st_mtime_ns == mtime_before


def test_parse_failure_appends_no_schema_audit_entry(qtbot, tmp_path):
    from unittest.mock import patch

    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    broken_path = tmp_path / "broken.pgtp"
    broken_path.write_text(MALFORMED_PGTP, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(broken_path))

    assert window.audit_panel.count() == 0


def test_report_schema_events_with_exactly_20_events_prints_one_line_each(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    source_path = tmp_path / "twenty.pgtp"
    source_path.write_text(VALID_PGTP, encoding="utf-8")

    events = [
        {"kind": "new_attribute", "path": "Project/Presentation/Pages/Page", "attr": f"attr{i}"}
        for i in range(20)
    ]

    window._report_schema_events(events, str(source_path))

    assert window.audit_panel.count() == 20
    for i in range(20):
        expected = f"[Schema] NEW ATTRIBUTE: Project/Presentation/Pages/Page@attr{i} (first seen in twenty.pgtp)"
        assert window.audit_panel.item(i).text() == expected

    summary_prefix = "[Schema] Learned"
    for i in range(window.audit_panel.count()):
        assert not window.audit_panel.item(i).text().startswith(summary_prefix)


def test_report_schema_events_with_21_events_collapses_to_summary_line(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    source_path = tmp_path / "twentyone.pgtp"
    source_path.write_text(VALID_PGTP, encoding="utf-8")

    events = [
        {"kind": "new_attribute", "path": "Project/Presentation/Pages/Page", "attr": f"attr{i}"}
        for i in range(21)
    ]

    window._report_schema_events(events, str(source_path))

    assert window.audit_panel.count() == 1
    expected = "[Schema] Learned 21 new structural facts from twentyone.pgtp"
    assert window.audit_panel.item(0).text() == expected

    for i in range(21):
        per_event_text = (
            f"[Schema] NEW ATTRIBUTE: Project/Presentation/Pages/Page@attr{i} "
            f"(first seen in twentyone.pgtp)"
        )
        assert per_event_text != window.audit_panel.item(0).text()


def test_main_window_constructs_with_no_arguments_and_resolves_real_app_data_dir(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window._schema_storage_dir is None

    model_path = schema_model_path(window._schema_storage_dir)
    assert model_path.name == "schema_model.json"
    # Resolves to the real per-user AppDataLocation, not empty/relative.
    assert model_path.is_absolute()
