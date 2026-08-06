"""MainWindow wiring for the Database/XML Coherence panel's *reference* side
(§17, FQ-003) — the half that used to live behind View ▸ "Find table
reference" and its own `TableReferencesPanel` tab.

Successor to `test_table_references_wiring.py`. The panel's own rendering
(badges, recursion depth, the owning-ColumnNode selection semantic) is pinned
in `test_coherence_panel.py`; what is asserted here is only what MainWindow
owns: the panel's signals reaching the Properties panel and the editor, and
the retired entry points staying retired.

No live DB — `_fetch_db_schema` and `_run_async` are injected seams.
"""
from unittest.mock import patch

from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.ui.main_window import MainWindow

PGTP_WITH_LOOKUP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <ConnectionOptions host="h" port="5432" login="u" database="d"/>
  <Presentation>
    <Pages>
      <Page fileName="orders" tableName="pr.orders" caption="Orders">
        <ColumnPresentations>
          <ColumnPresentation fieldName="objecttype">
            <Lookup tableName="kb.x_objecttype" linkFieldName="id">
              <OnTheFlyInsertPage fileName="x_objecttype" caption="X Objecttype"/>
            </Lookup>
          </ColumnPresentation>
        </ColumnPresentations>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def _schema():
    return DatabaseSchema(
        tables={
            "pr.orders": TableInfo(
                name="pr.orders",
                kind="table",
                columns=[ColumnInfo("objecttype", "integer", False, False, True, None)],
            ),
            "kb.x_objecttype": TableInfo(
                name="kb.x_objecttype",
                kind="table",
                columns=[ColumnInfo("id", "integer", True, False, False, None)],
            ),
        }
    )


def _sync_run(fn, on_result, on_error=None):
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001
        (on_error or (lambda _e: None))(exc)


def _window(qtbot, tmp_path, text=PGTP_WITH_LOOKUP):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "p.pgtp"
    path.write_text(text, encoding="utf-8")
    window.open_project_file(str(path))
    window._fetch_db_schema = lambda params: _schema()
    window._run_async = _sync_run
    return window


def _rows(panel):
    """Every row in the tree, flattened (depth is the panel's business)."""
    out = []

    def walk(item):
        out.append(item)
        for i in range(item.childCount()):
            walk(item.child(i))

    for i in range(panel.tree.topLevelItemCount()):
        walk(panel.tree.topLevelItem(i))
    return out


def _rows_of_kind(panel, kind):
    return [
        item
        for item in _rows(panel)
        if panel.node_for(item) is not None and panel.node_for(item).kind == kind
    ]


def test_coherence_run_reveals_the_tab_and_shows_the_reference_side(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window._run_db_check()

    idx = window.coherence_tab_index
    assert window.left_tabs.isTabVisible(idx) is True
    assert window.left_tabs.currentIndex() == idx
    labels = [
        f"{item.text(0)} {item.text(1)}" for item in _rows(window.coherence_panel)
    ]
    # The lookup target and the page's own binding both surface, as they did in
    # the retired Table references tab.
    assert any("kb.x_objecttype" in lbl for lbl in labels)
    assert any("pr.orders" in lbl for lbl in labels)
    assert any("lookup with insert" in lbl for lbl in labels)


def test_selection_drives_properties_panel(qtbot, tmp_path):
    """The panel's selection_changed reaches the shared Properties panel —
    unchanged from the Table references tab."""
    window = _window(qtbot, tmp_path)
    window._run_db_check()
    panel = window.coherence_panel

    lookups = _rows_of_kind(panel, "lookup")
    assert lookups

    with patch.object(window.properties_panel, "show_node") as show:
        panel.tree.setCurrentItem(lookups[0])

    assert show.called
    node, kind = show.call_args.args
    assert kind == "lookup"
    # §17: a lookup row's model node is the OWNING ColumnNode.
    assert node is not None


def test_page_row_selection_drives_properties_with_the_page_node(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._run_db_check()
    panel = window.coherence_panel

    pages = _rows_of_kind(panel, "page")
    assert pages

    with patch.object(window.properties_panel, "show_node") as show:
        panel.tree.setCurrentItem(pages[0])

    assert show.called
    node, kind = show.call_args.args
    assert kind == "page"
    assert node is not None


def test_double_click_on_an_xml_row_jumps_the_editor_to_its_line(qtbot, tmp_path):
    """jump_requested(line) is wired to _tree_jump_to_line — the mechanism the
    Table references tab already used."""
    window = _window(qtbot, tmp_path)
    window._run_db_check()
    panel = window.coherence_panel
    item = next(
        item
        for item in _rows(panel)
        if panel.node_for(item) is not None and panel.node_for(item).line is not None
    )

    with patch.object(window, "_tree_jump_to_line") as jump:
        panel.tree.itemDoubleClicked.emit(item, 0)

    jump.assert_called_once()
    (line,) = jump.call_args.args
    assert isinstance(line, int) and line > 1


def test_double_click_on_a_relation_row_goes_through_the_name_jump(qtbot, tmp_path):
    """name_jump_requested(kind, name) is a SEPARATE signal (Qt cannot overload
    one name) and must land on the name-based handler, not the line one."""
    window = _window(qtbot, tmp_path)
    window._run_db_check()
    panel = window.coherence_panel
    relations = _rows_of_kind(panel, "relation")
    assert relations

    with patch.object(window, "_on_db_jump_requested") as name_jump, patch.object(
        window, "_tree_jump_to_line"
    ) as line_jump:
        panel.tree.itemDoubleClicked.emit(relations[0], 0)

    name_jump.assert_called_once()
    kind, name = name_jump.call_args.args
    assert kind == "relation"
    assert name
    line_jump.assert_not_called()


def test_menus_offer_neither_reused_tables_nor_find_table_reference(qtbot):
    """The Tools ▸ "Find Reused Tables…" removal stands, and FQ-003 removed
    View ▸ "Find table reference" as well — the merged view is the only door."""
    window = MainWindow()
    qtbot.addWidget(window)
    labels = [
        action.text()
        for menu in window.menuBar().findChildren(type(window.menuBar().addMenu("x")))
        for action in menu.actions()
    ]
    assert not any("Reused Tables" in (t or "") for t in labels)
    assert not any("Find table reference" in (t or "") for t in labels)
    assert any("Database/XML Coherence" in (t or "") for t in labels)


PGTP_TWO_LOOKUPS = PGTP_WITH_LOOKUP.replace(
    "</Pages>",
    """  <Page fileName="items" tableName="pr.items" caption="Items">
        <ColumnPresentations>
          <ColumnPresentation fieldName="cat">
            <Lookup tableName="kb.x_category" linkFieldName="id"/>
          </ColumnPresentation>
        </ColumnPresentations>
      </Page>
</Pages>""",
)


def test_reparse_refreshes_the_visible_coherence_view(qtbot, tmp_path):
    """The reparse-refresh behavior the Table references tab had is preserved
    against the merged tree — and against the CACHED schema, no re-query."""
    window = _window(qtbot, tmp_path)
    fetches = []
    base = window._fetch_db_schema
    window._fetch_db_schema = lambda p: (fetches.append(1), base(p))[1]
    window._run_db_check()
    assert fetches == [1]

    window.center_stage.xml_editor.setPlainText(PGTP_TWO_LOOKUPS)
    window._reparse_raw_xml()

    assert fetches == [1]  # cached schema reused
    # The new lookup's target is a relation the DB does not have, so it shows
    # up flagged at its reference point in the Pages branch (§17), with the
    # table name in the badge column.
    text = [
        f"{item.text(0)} {item.text(1)}" for item in _rows(window.coherence_panel)
    ]
    assert any("kb.x_category" in row and "missing in DB" in row for row in text)
