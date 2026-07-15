import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pgtp_editor.ui.manual_panel import Chapter, load_manual_text, parse_chapters


def test_load_manual_text_returns_bundled_content():
    text = load_manual_text()
    assert text.startswith("# PGTP Editor")
    assert "## The Code Editor" in text


def test_parse_chapters_levels_and_titles_in_order():
    md = "# Title\n\nintro\n\n## One\ntext\n\n### One-a\n\n## Two\n"
    chs = parse_chapters(md)
    assert chs == [
        Chapter(1, "Title"),
        Chapter(2, "One"),
        Chapter(3, "One-a"),
        Chapter(2, "Two"),
    ]


def test_parse_chapters_ignores_headings_in_code_fences():
    md = "# T\n\n```\n# not a heading\n## also not\n```\n\n## Real\n"
    chs = parse_chapters(md)
    assert chs == [Chapter(1, "T"), Chapter(2, "Real")]


def test_parse_chapters_ignores_tilde_fences_and_hash_without_space():
    md = "# T\n\n~~~\n## nope\n~~~\n\n#nospace not a heading\n\n## Real\n"
    chs = parse_chapters(md)
    assert chs == [Chapter(1, "T"), Chapter(2, "Real")]


def test_parse_chapters_trims_and_matches_real_manual():
    # The 1:1 heading model requires every heading to parse cleanly.
    chs = parse_chapters(load_manual_text())
    assert chs[0] == Chapter(1, "PGTP Editor")
    assert any(c == Chapter(2, "Caption Management") for c in chs)
    assert all(c.title == c.title.strip() and c.title for c in chs)
