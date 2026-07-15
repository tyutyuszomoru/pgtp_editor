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


def test_manual_panel_renders_and_scrolls_to_chapter(qtbot):
    from pgtp_editor.ui.manual_panel import ManualPanel, parse_chapters
    md = "# T\n\nintro\n\n## One\naaa\n\n## Two\nbbb\n\n## Three\nccc\n"
    panel = ManualPanel()
    qtbot.addWidget(panel)
    panel.set_markdown(md)
    chapters = parse_chapters(md)
    # scroll to "Two" (index 2): cursor block text must equal that heading.
    panel.scroll_to_chapter(2)
    assert panel.textCursor().block().text() == chapters[2].title
    panel.scroll_to_chapter(999)  # out of range: no crash, no move
    assert panel.textCursor().block().text() == chapters[2].title


def test_manual_heading_count_matches_parse_chapters(qtbot):
    from pgtp_editor.ui.manual_panel import ManualPanel, load_manual_text, parse_chapters
    text = load_manual_text()
    panel = ManualPanel()
    qtbot.addWidget(panel)
    panel.set_markdown(text)
    # Collect (level, text) of every heading block Qt produced, in order.
    doc = panel.document()
    qt_headings = []
    block = doc.begin()
    while block.isValid():
        level = block.blockFormat().headingLevel()
        if level > 0:
            qt_headings.append((level, block.text()))
        block = block.next()
    chapters = parse_chapters(text)
    # Count must match...
    assert len(qt_headings) == len(chapters)
    # ...AND each Nth heading must align in level and title. This catches a
    # same-count desync (e.g. a setext heading Qt sees but parse_chapters
    # doesn't) that would silently mis-target every subsequent chapter's scroll.
    for (qt_level, qt_text), chapter in zip(qt_headings, chapters):
        assert qt_level == chapter.level
        assert qt_text == chapter.title


def test_contents_panel_emits_positional_index(qtbot):
    from pgtp_editor.ui.manual_panel import Chapter, ManualContentsPanel
    panel = ManualContentsPanel()
    qtbot.addWidget(panel)
    chapters = [
        Chapter(1, "Title"), Chapter(2, "One"),
        Chapter(3, "One-a"), Chapter(2, "Two"),
    ]
    panel.set_chapters(chapters)
    received = []
    panel.chapter_selected.connect(received.append)
    # "One-a" is nested under "One"; find it and click.
    one = _find_item(panel.tree, "One")
    one_a = one.child(0)
    assert one_a.text(0) == "One-a"
    panel.tree.itemClicked.emit(one_a, 0)
    assert received == [2]  # positional index of "One-a"


def _find_item(tree, title):
    it = tree.invisibleRootItem()
    stack = [it.child(i) for i in range(it.childCount())]
    while stack:
        node = stack.pop()
        if node.text(0) == title:
            return node
        stack.extend(node.child(i) for i in range(node.childCount()))
    return None
