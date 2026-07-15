from pgtp_editor.ui.center_stage import CenterStage


def test_tabs_in_order(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.count() == 4
    assert stage.tabText(0) == "Diff / Merge"
    assert stage.tabText(1) == "Caption Management"
    assert stage.tabText(2) == "Raw XML"
    assert stage.tabText(3) == "Manual"


def test_default_tab_visibility_raw_xml_shown_others_hidden(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    # New default (spec §6.1): Raw XML is the working tab; Diff/Merge and
    # Caption Management are revealed only when invoked.
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True
    assert stage.isTabVisible(stage.diff_merge_tab_index) is False
    assert stage.isTabVisible(stage.caption_management_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index


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


from pgtp_editor.ui.xml_editor import XmlEditor


def test_raw_xml_tab_holds_a_real_xml_editor(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.xml_editor, XmlEditor)
    # The Raw XML tab now hosts a container widget (editor + find/replace
    # bar); xml_editor remains the accessor and lives inside that container.
    assert stage.widget(stage.raw_xml_tab_index) is stage.raw_xml_tab
    assert stage.xml_editor.parent() is stage.raw_xml_tab


from pgtp_editor.ui.find_replace_bar import FindReplaceBar


def test_raw_xml_tab_container_holds_find_replace_bar(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.find_replace_bar, FindReplaceBar)
    assert stage.find_replace_bar.parent() is stage.raw_xml_tab


from pgtp_editor.ui.caption_management_panel import CaptionManagementPanel


def test_caption_management_tab_holds_the_panel(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.caption_management_panel, CaptionManagementPanel)
    assert stage.widget(stage.caption_management_tab_index) is stage.caption_management_panel


def test_enter_caption_mode_keeps_raw_visible_readonly_shows_caption(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_caption_mode()
    # Phase 1: Raw XML stays VISIBLE but read-only (no longer hidden).
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True
    assert stage.xml_editor.isReadOnly() is True
    assert stage.isTabVisible(stage.caption_management_tab_index) is True
    assert stage.currentIndex() == stage.caption_management_tab_index


def test_leave_caption_mode_restores_raw(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_caption_mode()
    stage.leave_caption_mode()
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True
    assert stage.xml_editor.isReadOnly() is False
    assert stage.isTabVisible(stage.caption_management_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index
