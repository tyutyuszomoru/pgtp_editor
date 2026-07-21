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
