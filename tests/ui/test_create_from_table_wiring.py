# tests/ui/test_create_from_table_wiring.py
"""MainWindow wiring for "create page/detail/lookup from a DB table" (SP3).

No live DB (schema injected via `_last_db_schema`), no modal (the duplicate
warning goes through the `_confirm_duplicate_page` seam), no real clipboard
dependency beyond QApplication's in-process clipboard.
"""
from PySide6.QtWidgets import QApplication

from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.ui.main_window import MainWindow

_RAW_XML = (
    '<Project>\n'
    '  <Presentation><Pages>\n'
    '    <Page fileName="pr_existing" tableName="pr.existing">\n'
    '      <ColumnPresentations/>\n'
    '    </Page>\n'
    '  </Pages></Presentation>\n'
    '</Project>\n'
)


def _schema():
    equipment = TableInfo(
        name="pr.equipment", kind="table",
        columns=[
            ColumnInfo("id", "integer", True, False, False, None),
            ColumnInfo("tag", "varchar(30)", False, False, True, None),
        ],
    )
    part = TableInfo(
        name="pr.part", kind="table",
        columns=[
            ColumnInfo("id", "integer", True, False, False, None),
            ColumnInfo("equipment_id", "integer", False, True, False, None,
                       fk_target="pr.equipment.id"),
        ],
    )
    existing = TableInfo(
        name="pr.existing", kind="table",
        columns=[ColumnInfo("id", "integer", True, False, False, None)],
    )
    return DatabaseSchema(tables={t.name: t for t in (equipment, part, existing)})


def _window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_RAW_XML)
    window._last_db_schema = _schema()
    return window


def test_create_page_inserts_before_pages_close(qtbot):
    window = _window(qtbot)
    window._on_db_create_requested("page", "pr.equipment")

    text = window.center_stage.xml_editor.toPlainText()
    assert 'tableName="pr.equipment"' in text
    # Inserted inside <Pages>, before its close.
    assert text.index('tableName="pr.equipment"') < text.index("</Pages>")
    # The pre-existing page is untouched and still present.
    assert 'tableName="pr.existing"' in text
    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index


def test_create_page_duplicate_prompts_and_dedupes_filename(qtbot):
    window = _window(qtbot)
    # pr.existing already has a page + fileName pr_existing.
    seen = []
    window._confirm_duplicate_page = lambda name: seen.append(name) or True
    window._on_db_create_requested("page", "pr.existing")

    text = window.center_stage.xml_editor.toPlainText()
    assert seen == ["pr.existing"]
    # Original + de-duplicated new page.
    assert 'fileName="pr_existing"' in text
    assert 'fileName="pr_existing_2"' in text


def test_create_page_duplicate_cancel_leaves_buffer_unchanged(qtbot):
    window = _window(qtbot)
    window._confirm_duplicate_page = lambda name: False
    before = window.center_stage.xml_editor.toPlainText()
    window._on_db_create_requested("page", "pr.existing")
    assert window.center_stage.xml_editor.toPlainText() == before


def test_create_detail_copies_to_clipboard_with_fk_link(qtbot):
    window = _window(qtbot)
    before = window.center_stage.xml_editor.toPlainText()
    window._on_db_create_requested("detail", "pr.part")

    clip = QApplication.clipboard().text()
    assert clip.startswith("<Detail ")
    assert 'foreginColumnName="equipment_id"' in clip
    assert 'masterColumnName="id"' in clip
    # Detail goes to the clipboard only — buffer is untouched.
    assert window.center_stage.xml_editor.toPlainText() == before
    assert "clipboard" in window.statusBar().currentMessage().lower()


def test_create_lookup_copies_to_clipboard(qtbot):
    window = _window(qtbot)
    window._on_db_create_requested("lookup", "pr.equipment")
    clip = QApplication.clipboard().text()
    assert clip.startswith("<Lookup ")
    assert 'tableName="pr.equipment"' in clip
    assert 'linkFieldName="id"' in clip


def test_create_without_schema_shows_status(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_RAW_XML)
    window._last_db_schema = None
    window._on_db_create_requested("page", "pr.equipment")
    assert "Database check" in window.statusBar().currentMessage()


def test_create_page_unknown_table_shows_status(qtbot):
    window = _window(qtbot)
    before = window.center_stage.xml_editor.toPlainText()
    window._on_db_create_requested("page", "pr.does_not_exist")
    # Guard: schema present but table absent → status message, buffer untouched.
    assert window.center_stage.xml_editor.toPlainText() == before
    assert "pr.does_not_exist" in window.statusBar().currentMessage()


_TAB_XML = (
    "<Project>\n"
    "\t<Presentation>\n"
    "\t\t<Pages>\n"
    '\t\t\t<Page fileName="pr_existing" tableName="pr.existing">\n'
    "\t\t\t\t<ColumnPresentations/>\n"
    "\t\t\t</Page>\n"
    "\t\t</Pages>\n"
    "\t</Presentation>\n"
    "</Project>\n"
)


def test_create_page_into_tab_indented_buffer(qtbot):
    window = _window(qtbot)
    window.center_stage.xml_editor.setPlainText(_TAB_XML)
    window._on_db_create_requested("page", "pr.equipment")

    text = window.center_stage.xml_editor.toPlainText()
    assert 'tableName="pr.equipment"' in text
    assert text.index('tableName="pr.equipment"') < text.index("</Pages>")
    # </Pages> sits at 2 tabs, so the new <Page> is spliced at 3 tabs.
    new_page_line = next(
        ln for ln in text.splitlines() if 'tableName="pr.equipment"' in ln
    )
    assert new_page_line.startswith("\t\t\t<Page ")


def test_create_page_filename_collision_only_prompts(qtbot):
    """A fileName clash (different tableName) still triggers the dedupe prompt."""
    raw = (
        "<Project>\n"
        "  <Presentation><Pages>\n"
        '    <Page fileName="pr_equipment" tableName="pr.other">\n'
        "      <ColumnPresentations/>\n"
        "    </Page>\n"
        "  </Pages></Presentation>\n"
        "</Project>\n"
    )
    window = _window(qtbot)
    window.center_stage.xml_editor.setPlainText(raw)
    seen = []
    window._confirm_duplicate_page = lambda name: seen.append(name) or True
    window._on_db_create_requested("page", "pr.equipment")

    text = window.center_stage.xml_editor.toPlainText()
    assert seen == ["pr.equipment"]  # fileName collision alone prompts
    assert 'fileName="pr_equipment_2"' in text
    assert 'tableName="pr.equipment"' in text


def test_create_page_no_pages_close_shows_status(qtbot):
    window = _window(qtbot)
    window.center_stage.xml_editor.setPlainText(
        "<Project>\n  <Presentation/>\n</Project>\n"
    )
    before = window.center_stage.xml_editor.toPlainText()
    window._on_db_create_requested("page", "pr.equipment")
    # No </Pages> anchor → buffer untouched, status explains why.
    assert window.center_stage.xml_editor.toPlainText() == before
    assert "</Pages>" in window.statusBar().currentMessage()


def test_create_lookup_composite_pk_leaves_link_empty(qtbot):
    window = _window(qtbot)
    # Inject a table with a composite PK.
    schema = window._last_db_schema
    bridge = TableInfo(
        name="pr.bridge", kind="table",
        columns=[
            ColumnInfo("a_id", "integer", True, False, False, None),
            ColumnInfo("b_id", "integer", True, False, False, None),
            ColumnInfo("label", "text", False, False, True, None),
        ],
    )
    schema.tables["pr.bridge"] = bridge
    window._on_db_create_requested("lookup", "pr.bridge")
    clip = QApplication.clipboard().text()
    assert clip.startswith("<Lookup ")
    assert 'linkFieldName=""' in clip
    assert 'displayFieldName="label"' in clip
