# tests/ui/test_create_from_table_wiring.py
"""MainWindow wiring for "create page/detail/lookup from a DB table" (SP3, as
redirected by FQ-006).

All three kinds now open a **draft tab** in the center stage holding the
serialized fragment. Nothing is spliced into the project buffer and nothing is
copied to the clipboard any more; the duplicate check survives only as a
non-blocking status-bar heads-up.

No live DB (schema injected via `CoherenceController.last_schema`), no modal —
the old `confirm_duplicate_page` seam is gone along with the blocking dialog it
bypassed.
"""
from PySide6.QtWidgets import QApplication

from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.ui.center_stage import DRAFT_TAB_KEY_KIND, DraftFragmentTab
from pgtp_editor.ui.main_window import MainWindow

_RAW_XML = (
    '<Project>\n'
    '  <Presentation><Pages>\n'
    '    <Page fileName="existing" tableName="pr.existing">\n'
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
    window._db_ui.last_schema = _schema()
    return window


def _drafts(window):
    return list(window.center_stage.draft_fragment_tabs().values())


def _only_draft(window):
    drafts = _drafts(window)
    assert len(drafts) == 1
    return drafts[0]


# --- each kind opens a draft tab with the serialized fragment ---------------
def test_create_page_opens_a_draft_tab_and_leaves_the_buffer_alone(qtbot):
    window = _window(qtbot)
    before = window.center_stage.xml_editor.toPlainText()
    window._db_ui.on_create_requested("page", "pr.equipment")

    draft = _only_draft(window)
    assert isinstance(draft, DraftFragmentTab)
    text = draft.toPlainText()
    assert text.startswith("<Page ")
    assert 'tableName="pr.equipment"' in text
    assert 'fileName="equipment"' in text
    # The project buffer is untouched -- the splice path is gone.
    assert window.center_stage.xml_editor.toPlainText() == before
    # The draft tab is focused, named for kind + source table.
    stage = window.center_stage
    assert stage.currentWidget() is draft
    assert stage.tabText(stage.indexOf(draft)) == "New Page: pr.equipment"
    assert "new tab" in window.statusBar().currentMessage()


def test_create_detail_opens_a_draft_tab_with_the_fk_link(qtbot):
    window = _window(qtbot)
    before = window.center_stage.xml_editor.toPlainText()
    QApplication.clipboard().setText("untouched")
    window._db_ui.on_create_requested("detail", "pr.part")

    draft = _only_draft(window)
    text = draft.toPlainText()
    assert text.startswith("<Detail ")
    # Generation is unchanged, vendor misspelling included.
    assert 'foreginColumnName="equipment_id"' in text
    assert 'masterColumnName="id"' in text
    assert window.center_stage.xml_editor.toPlainText() == before
    # The clipboard path is gone.
    assert QApplication.clipboard().text() == "untouched"
    assert "clipboard" not in window.statusBar().currentMessage().lower()
    stage = window.center_stage
    assert stage.tabText(stage.indexOf(draft)) == "New Detail: pr.part"


def test_create_lookup_opens_a_draft_tab(qtbot):
    window = _window(qtbot)
    before = window.center_stage.xml_editor.toPlainText()
    QApplication.clipboard().setText("untouched")
    window._db_ui.on_create_requested("lookup", "pr.equipment")

    draft = _only_draft(window)
    text = draft.toPlainText()
    assert text.startswith("<Lookup ")
    assert 'tableName="pr.equipment"' in text
    assert 'linkFieldName="id"' in text
    assert window.center_stage.xml_editor.toPlainText() == before
    assert QApplication.clipboard().text() == "untouched"
    stage = window.center_stage
    assert stage.tabText(stage.indexOf(draft)) == "New Lookup: pr.equipment"


def test_create_lookup_composite_pk_leaves_link_empty(qtbot):
    window = _window(qtbot)
    schema = window._db_ui.last_schema
    schema.tables["pr.bridge"] = TableInfo(
        name="pr.bridge", kind="table",
        columns=[
            ColumnInfo("a_id", "integer", True, False, False, None),
            ColumnInfo("b_id", "integer", True, False, False, None),
            ColumnInfo("label", "text", False, False, True, None),
        ],
    )
    window._db_ui.on_create_requested("lookup", "pr.bridge")

    text = _only_draft(window).toPlainText()
    assert text.startswith("<Lookup ")
    assert 'linkFieldName=""' in text
    assert 'displayFieldName="label"' in text


# --- a new tab every time, never a shared scratch tab ----------------------
def test_two_creations_open_two_draft_tabs(qtbot):
    """FQ-006: Page from table A then Detail from table B must leave TWO tabs
    open — never one silently overwritten."""
    window = _window(qtbot)
    stage = window.center_stage
    fixed_count = stage.count()

    window._db_ui.on_create_requested("page", "pr.equipment")
    window._db_ui.on_create_requested("detail", "pr.part")

    drafts = _drafts(window)
    assert len(drafts) == 2
    assert drafts[0] is not drafts[1]
    assert stage.count() == fixed_count + 2
    titles = {stage.tabText(stage.indexOf(d)) for d in drafts}
    assert titles == {"New Page: pr.equipment", "New Detail: pr.part"}
    assert drafts[0].toPlainText().startswith("<Page ")
    assert drafts[1].toPlainText().startswith("<Detail ")


def test_same_kind_and_table_twice_still_opens_two_tabs(qtbot):
    """Not single-instance: repeating the exact same gesture must not clobber
    an in-progress edit in the first draft."""
    window = _window(qtbot)
    window._db_ui.on_create_requested("page", "pr.equipment")
    first = _only_draft(window)
    first.editor.setPlainText("<Page>my edits</Page>")

    window._db_ui.on_create_requested("page", "pr.equipment")

    drafts = _drafts(window)
    assert len(drafts) == 2
    assert first.toPlainText() == "<Page>my edits</Page>"  # untouched
    keys = list(window.center_stage.draft_fragment_tabs())
    assert all(key[0] == DRAFT_TAB_KEY_KIND for key in keys)
    assert len(set(keys)) == 2  # distinct identities


# --- the duplicate heads-up is informational only --------------------------
def test_duplicate_page_opens_the_tab_anyway_with_a_status_note(qtbot):
    """The blocking dialog and the `_dedupe_file_name` auto-rename are gone:
    the draft keeps the generator's fileName and only a status note is shown."""
    window = _window(qtbot)
    # pr.existing already has a <Page fileName="existing" tableName="pr.existing">.
    window._db_ui.on_create_requested("page", "pr.existing")

    draft = _only_draft(window)
    text = draft.toPlainText()
    assert 'fileName="existing"' in text  # NOT existing_2
    assert "existing_2" not in text
    message = window.statusBar().currentMessage()
    assert "Note:" in message
    assert 'fileName="existing"' in message
    # No auto-insert happened, so no seam was needed and none exists.
    assert not hasattr(window._db_ui, "confirm_duplicate_page")


def test_duplicate_filename_only_still_notes(qtbot):
    raw = (
        "<Project>\n"
        "  <Presentation><Pages>\n"
        # Same derived fileName ("equipment") but a DIFFERENT tableName.
        '    <Page fileName="equipment" tableName="pr.other">\n'
        "      <ColumnPresentations/>\n"
        "    </Page>\n"
        "  </Pages></Presentation>\n"
        "</Project>\n"
    )
    window = _window(qtbot)
    window.center_stage.xml_editor.setPlainText(raw)
    window._db_ui.on_create_requested("page", "pr.equipment")

    assert 'fileName="equipment"' in _only_draft(window).toPlainText()
    assert 'fileName="equipment"' in window.statusBar().currentMessage()


def test_referenced_table_notes_without_a_filename_clash(qtbot):
    window = _window(qtbot)
    window._db_ui.on_create_requested("lookup", "pr.existing")

    assert _drafts(window)  # tab opened regardless
    message = window.statusBar().currentMessage()
    assert "already referenced" in message
    assert "pr.existing" in message


def test_no_note_when_nothing_collides(qtbot):
    window = _window(qtbot)
    window._db_ui.on_create_requested("page", "pr.equipment")
    assert "Note:" not in window.statusBar().currentMessage()


# --- no </Pages> anchor is no longer a failure mode ------------------------
def test_create_page_without_pages_close_still_opens_a_draft(qtbot):
    """The splice needed a </Pages> anchor; a draft tab does not."""
    window = _window(qtbot)
    window.center_stage.xml_editor.setPlainText(
        "<Project>\n  <Presentation/>\n</Project>\n"
    )
    window._db_ui.on_create_requested("page", "pr.equipment")

    assert _only_draft(window).toPlainText().startswith("<Page ")
    assert "</Pages>" not in window.statusBar().currentMessage()


# --- guards -----------------------------------------------------------------
def test_create_without_schema_shows_status_and_opens_nothing(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_RAW_XML)
    window._db_ui.last_schema = None
    window._db_ui.on_create_requested("page", "pr.equipment")
    # FQ-003: the hint now names the merged view, not the retired check.
    assert "Database/XML Coherence" in window.statusBar().currentMessage()
    assert _drafts(window) == []


def test_create_unknown_table_shows_status_and_opens_nothing(qtbot):
    window = _window(qtbot)
    before = window.center_stage.xml_editor.toPlainText()
    window._db_ui.on_create_requested("page", "pr.does_not_exist")
    assert window.center_stage.xml_editor.toPlainText() == before
    assert "pr.does_not_exist" in window.statusBar().currentMessage()
    assert _drafts(window) == []


def test_create_unknown_kind_opens_nothing(qtbot):
    window = _window(qtbot)
    window._db_ui.on_create_requested("nonsense", "pr.equipment")
    assert _drafts(window) == []


# -- FQ-006 follow-up: a draft tab's own Find bar must be reachable ----------
#
# The draft tab builds an `XmlEditor` and a `FindReplaceBar`, but
# `FindValidateController`'s per-tab routing dispatches through
# `active_ddl_object_panel()` / `active_php_file_tab()`. A draft tab is neither,
# so Ctrl+F fell through to the Raw XML fallback -- which REVEALS that tab and
# searches the wrong document -- while the draft's own bar sat hidden and
# unreachable. Found by a manual-maintainer pass verifying the docs against the
# code, not by any test, which is why these exist.


def test_ctrl_f_in_a_draft_tab_searches_the_draft_not_raw_xml(qtbot):
    window = _window(qtbot)
    window._db_ui.on_create_requested("page", "pr.equipment")
    draft = _only_draft(window)

    assert window.center_stage.active_draft_fragment_tab() is draft
    assert window._find_ui.active_find_bar() is draft.find_replace_bar
    # The Raw XML fallback would also have switched tabs; it must not have.
    assert window.center_stage.currentWidget() is draft


def test_bookmarks_in_a_draft_tab_act_on_the_draft_editor(qtbot):
    window = _window(qtbot)
    window._db_ui.on_create_requested("detail", "pr.equipment")
    draft = _only_draft(window)

    assert window._find_ui.active_bookmark_editor() is draft.editor


def test_routing_falls_back_once_the_draft_tab_is_closed(qtbot):
    window = _window(qtbot)
    window._db_ui.on_create_requested("lookup", "pr.equipment")
    draft = _only_draft(window)
    key = window.center_stage.draft_fragment_tab_key(draft)
    window.center_stage.close_draft_fragment_tab(key)

    assert window.center_stage.active_draft_fragment_tab() is None
    assert window._find_ui.active_find_bar() is window.center_stage.find_replace_bar
