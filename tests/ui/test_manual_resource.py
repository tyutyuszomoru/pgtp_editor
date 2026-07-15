from importlib.resources import files


def test_manual_md_is_a_package_resource():
    res = files("pgtp_editor") / "resources" / "manual.md"
    text = res.read_text(encoding="utf-8")
    assert text.startswith("# PGTP Editor")
    assert "## Getting Started" in text
