# tests/ui/test_about.py
from pgtp_editor.ui.about import ABOUT_TEXT


def test_credits_mention_all_three_projects():
    assert "BoomslangXML" in ABOUT_TEXT
    assert "QCodeEditor" in ABOUT_TEXT
    assert "SuperNano" in ABOUT_TEXT


def test_credits_mention_license():
    assert "GPL-3.0" in ABOUT_TEXT
