from pgtp_editor.ui.center_stage import CenterStage


def test_four_tabs_in_order(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.count() == 4
    assert stage.tabText(0) == "Properties"
    assert stage.tabText(1) == "Diff / Merge"
    assert stage.tabText(2) == "Caption Management"
    assert stage.tabText(3) == "Raw XML"


def test_raw_xml_tab_hidden_by_default(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.isTabVisible(stage.raw_xml_tab_index) is False
    assert stage.isTabVisible(stage.properties_tab_index) is True


def test_set_raw_xml_tab_visible(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.set_raw_xml_tab_visible(True)
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True


def test_set_properties_tab_visible(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.set_properties_tab_visible(False)
    assert stage.isTabVisible(stage.properties_tab_index) is False
