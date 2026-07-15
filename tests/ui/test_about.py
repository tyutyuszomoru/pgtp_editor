# tests/ui/test_about.py
from pgtp_editor.ui.about import ABOUT_TEXT


def test_mentions_authors():
    assert "Botond Zalai-Ruzsics" in ABOUT_TEXT
    assert "Maintenance Data Services" in ABOUT_TEXT
    assert "maint-data.com" in ABOUT_TEXT


def test_mentions_credit_and_disclaimer():
    assert "sqlmaestro.com" in ABOUT_TEXT
    assert "not affiliated with, endorsed by, or connected to" in ABOUT_TEXT
    assert "SQL Maestro Group" in ABOUT_TEXT


def test_mentions_format_version():
    assert "22.8" in ABOUT_TEXT


def test_keeps_license_and_genuine_credits():
    assert "GPL-3.0" in ABOUT_TEXT
    assert "BoomslangXML" in ABOUT_TEXT
    assert "QCodeEditor" in ABOUT_TEXT


def test_drops_supernano_credit():
    assert "SuperNano" not in ABOUT_TEXT
    assert "nano" not in ABOUT_TEXT


def test_credits_breeze_icons():
    assert "Breeze" in ABOUT_TEXT
    assert "LGPL" in ABOUT_TEXT
    assert "KDE" in ABOUT_TEXT
