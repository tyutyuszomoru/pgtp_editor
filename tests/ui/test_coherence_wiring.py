from unittest.mock import patch

from pgtp_editor.ui.main_window import MainWindow

PGTP_WITH_LOOKUP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
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


def _open(window, tmp_path):
    path = tmp_path / "p.pgtp"
    path.write_text(PGTP_WITH_LOOKUP, encoding="utf-8")
    window.open_project_file(str(path))


def test_toggle_on_reveals_and_populates_table_references_tab(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)

    window._toggle_table_references(True)

    idx = window.table_refs_tab_index
    assert window.left_tabs.isTabVisible(idx) is True
    assert window.left_tabs.currentIndex() == idx
    # The fixture references two tables: the lookup target "kb.x_objecttype"
    # and the page's own "pr.orders" (page tableName is a recorded reference per
    # the committed analysis / design spec). Sorted by name, kb.* comes first.
    assert window.table_refs_panel.tree.topLevelItemCount() == 2
    top = window.table_refs_panel.tree.topLevelItem(0)
    assert top.text(0).startswith("kb.x_objecttype")
    assert "(lookup with insert)" in top.child(0).text(0)


def test_toggle_off_hides_the_tab(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    window._toggle_table_references(True)

    window._toggle_table_references(False)

    assert window.left_tabs.isTabVisible(window.table_refs_tab_index) is False


def test_toggle_on_without_project_shows_message_and_unchecks(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._table_refs_action.setChecked(True)  # fires _toggle_table_references(True)

    assert window._table_refs_action.isChecked() is False
    assert window.left_tabs.isTabVisible(window.table_refs_tab_index) is False


def test_selection_drives_properties_panel(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    window._toggle_table_references(True)

    with patch.object(window.properties_panel, "show_node") as show:
        child = window.table_refs_panel.tree.topLevelItem(0).child(0)
        window.table_refs_panel.tree.setCurrentItem(child)

    assert show.called
    node, kind = show.call_args.args
    assert kind == "column"
    assert node is not None


def test_double_click_jumps_editor_to_lookup_line(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    window._toggle_table_references(True)

    with patch.object(window, "_tree_jump_to_line") as jump:
        child = window.table_refs_panel.tree.topLevelItem(0).child(0)
        window.table_refs_panel.tree.itemDoubleClicked.emit(child, 0)

    jump.assert_called_once()
    (line,) = jump.call_args.args
    assert isinstance(line, int) and line > 1


def test_tools_menu_has_no_reused_tables_entry(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    labels = []
    for menu in window.menuBar().findChildren(type(window.menuBar().addMenu("x"))):
        for action in menu.actions():
            labels.append(action.text())
    assert not any("Reused Tables" in (t or "") for t in labels)
    assert any("Find table reference" in (t or "") for t in labels)


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


PGTP_LOOKUP_NO_INSERT = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="items" tableName="pr.items" caption="Items">
        <ColumnPresentations>
          <ColumnPresentation fieldName="cat">
            <Lookup tableName="kb.x_category" linkFieldName="id"/>
          </ColumnPresentation>
        </ColumnPresentations>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def _open_text(window, tmp_path, text):
    path = tmp_path / "p.pgtp"
    path.write_text(text, encoding="utf-8")
    window.open_project_file(str(path))


def test_lookup_without_insert_shows_plain_lookup_label(qtbot, tmp_path):
    # A <Lookup> with no child <OnTheFlyInsertPage> renders "(lookup)" through
    # the full analyzer -> panel path (never "(lookup with insert)").
    window = MainWindow()
    qtbot.addWidget(window)
    _open_text(window, tmp_path, PGTP_LOOKUP_NO_INSERT)

    window._toggle_table_references(True)

    tree = window.table_refs_panel.tree
    labels = [
        tree.topLevelItem(t).child(c).text(0)
        for t in range(tree.topLevelItemCount())
        for c in range(tree.topLevelItem(t).childCount())
    ]
    lookup_labels = [lbl for lbl in labels if "Column 'cat'" in lbl]
    assert lookup_labels == ["Page 'Items' ▸ Column 'cat' (lookup)"]
    assert all("(lookup with insert)" not in lbl for lbl in labels)


def test_toggle_off_then_on_repopulates_the_tab(qtbot, tmp_path):
    # Toggling the tab off then on must recompute usages and refill the tree
    # (not leave it stale or empty).
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)

    window._toggle_table_references(True)
    first_count = window.table_refs_panel.tree.topLevelItemCount()
    assert first_count >= 1

    window._toggle_table_references(False)
    window._toggle_table_references(True)

    assert window.left_tabs.isTabVisible(window.table_refs_tab_index) is True
    assert window.table_refs_panel.tree.topLevelItemCount() == first_count


def test_page_reference_selection_drives_properties_with_page_kind(qtbot, tmp_path):
    # Selecting a page's own tableName reference drives Properties with the page
    # node and kind="page" (the non-lookup selection path).
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    window._toggle_table_references(True)

    tree = window.table_refs_panel.tree
    # Find the top-level "pr.orders" table row (the page's own reference).
    page_top = None
    for i in range(tree.topLevelItemCount()):
        if tree.topLevelItem(i).text(0).startswith("pr.orders"):
            page_top = tree.topLevelItem(i)
            break
    assert page_top is not None

    with patch.object(window.properties_panel, "show_node") as show:
        tree.setCurrentItem(page_top.child(0))

    assert show.called
    node, kind = show.call_args.args
    assert kind == "page"
    assert node is not None


def test_reparse_refreshes_visible_table_references_tab(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    window._toggle_table_references(True)
    assert window.table_refs_panel.tree.topLevelItemCount() >= 1

    # Replace the buffer with a project that references a second table, then
    # reparse. The visible tab must reflect the new content.
    window.center_stage.xml_editor.setPlainText(PGTP_TWO_LOOKUPS)
    with patch("pgtp_editor.ui.main_window.QMessageBox.information"):
        window._reparse_raw_xml()

    names = {
        window.table_refs_panel.tree.topLevelItem(i).text(0).split("  ")[0]
        for i in range(window.table_refs_panel.tree.topLevelItemCount())
    }
    assert "kb.x_category" in names
