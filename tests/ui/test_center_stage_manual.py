import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pgtp_editor.ui.center_stage import CenterStage


def test_manual_tab_hidden_until_shown(qtbot):
    cs = CenterStage()
    qtbot.addWidget(cs)
    assert cs.isTabVisible(cs.manual_tab_index) is False
    cs.show_manual()
    assert cs.isTabVisible(cs.manual_tab_index) is True
    assert cs.currentIndex() == cs.manual_tab_index
