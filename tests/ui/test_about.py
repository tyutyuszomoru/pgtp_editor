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


def test_shows_the_app_version_from_the_single_source(qtbot=None):
    """`FQ-260810164455`: the box showed no version at all. It now renders the one
    read from `pyproject.toml` -- and spells no version literal of its own."""
    from pgtp_editor.version import __version__

    assert __version__ in ABOUT_TEXT
    assert f"PGTP Editor version {__version__}" in ABOUT_TEXT


def test_every_version_in_the_box_is_LABELLED():
    """Two unrelated versions render here and they were conflated once already:
    the app's release and SQL Maestro's `.pgtp` FORMAT version. Neither number may
    appear without saying what it versions."""
    from pgtp_editor.version import __version__

    assert f"PGTP Editor version {__version__}" in ABOUT_TEXT
    assert "project format version 22.8" in ABOUT_TEXT
    assert "not this application's" in ABOUT_TEXT


def test_the_about_box_spells_no_version_literal_of_its_own():
    import re
    from pathlib import Path

    import pgtp_editor.ui.about as about

    source = Path(about.__file__).read_text(encoding="utf-8")
    literals = set(re.findall(r"\b\d+\.\d+(?:\.\d+)?\b", source))
    # 22.8 is the VENDOR's format version and belongs here; 3 in "GPL-3.0" and
    # the like are not version literals of this app. Anything that looks like an
    # app release (x.y.z) must have come from `pgtp_editor.version`.
    assert not [item for item in literals if item.count(".") == 2 and item != "3.0"], (
        f"about.py contains an app-version-shaped literal: {literals}"
    )


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
