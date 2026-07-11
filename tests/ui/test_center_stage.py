from pgtp_editor.ui.center_stage import CenterStage


def test_three_tabs_in_order(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.count() == 3
    assert stage.tabText(0) == "Diff / Merge"
    assert stage.tabText(1) == "Caption Management"
    assert stage.tabText(2) == "Raw XML"


def test_raw_xml_tab_hidden_by_default(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.isTabVisible(stage.raw_xml_tab_index) is False


def test_set_raw_xml_tab_visible(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.set_raw_xml_tab_visible(True)
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True


from pgtp_editor.ui.diff_merge_panel import DiffMergePanel


def test_diff_merge_tab_holds_a_real_diff_merge_panel(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.diff_merge_panel, DiffMergePanel)
    assert stage.widget(stage.diff_merge_tab_index) is stage.diff_merge_panel
