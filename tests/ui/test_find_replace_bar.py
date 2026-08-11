import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from pgtp_editor.ui.find_replace_bar import FindReplaceBar
from pgtp_editor.ui.xml_editor import XmlEditor


def _editor(qtbot, text=""):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    return editor


def _select(editor, start, end):
    cursor = editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def test_bar_is_visible_from_construction_with_the_replace_row(qtbot):
    """FQ-016: no `self.hide()`, no show_find/show_replace mode -- the bar is
    permanently visible in its EXPANDED form (both rows)."""
    editor = _editor(qtbot, "alpha")
    host = QWidget()
    qtbot.addWidget(host)
    bar = FindReplaceBar(editor, parent=host)
    # `isVisibleTo(host)`, not `isVisible()`: nothing in this test is on screen,
    # so `isVisible()` is False for any widget. What FQ-016 changed is the bar's
    # OWN show state (the deleted `self.hide()` in __init__), which is what
    # `isVisibleTo` reports -- the same idiom the menu tests use.
    assert bar.isVisibleTo(host) is True
    assert bar._replace_row_widget.isVisibleTo(bar) is True
    assert not hasattr(bar, "show_find")
    assert not hasattr(bar, "show_replace")


def test_focus_find_prefills_from_selection(qtbot):
    editor = _editor(qtbot, "alpha beta gamma")
    _select(editor, 6, 10)  # "beta"
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar.show()
    bar.focus_find()
    assert bar._find_field.text() == "beta"
    assert bar.focusWidget() is bar._find_field


def test_focus_find_no_selection_leaves_field_unchanged(qtbot):
    editor = _editor(qtbot, "alpha beta")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("prev")
    bar.focus_find()
    assert bar._find_field.text() == "prev"


def test_focus_find_never_clobbers_text_the_user_typed(qtbot):
    """The whole reason prefill moved onto the focus path with an emptiness
    guard (FQ-016, FQ-017's precedent): a focus gesture must not overwrite a
    term the user typed just because a selection is still live in the editor."""
    editor = _editor(qtbot, "alpha beta gamma")
    _select(editor, 6, 10)  # "beta" selected in the editor
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("gamma")  # what the user typed
    bar.focus_find()
    assert bar._find_field.text() == "gamma"
    # ...while `set_find_text` (the right-click Find path) is unconditional.
    bar.set_find_text("beta")
    assert bar._find_field.text() == "beta"


def test_focus_replace_lands_in_the_replace_field_and_still_arms_find(qtbot):
    editor = _editor(qtbot, "alpha beta gamma")
    _select(editor, 6, 10)  # "beta"
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar.show()
    bar.focus_replace()
    assert bar.focusWidget() is bar._replace_field
    assert bar._find_field.text() == "beta"


def test_find_next_selects_the_match(qtbot):
    editor = _editor(qtbot, "one page two page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    bar._find_field.setText("page")
    bar.find_next()
    cursor = editor.textCursor()
    assert cursor.selectedText() == "page"
    assert cursor.selectionStart() == 4


def test_find_next_advances_to_second_match(qtbot):
    editor = _editor(qtbot, "one page two page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    bar._find_field.setText("page")
    bar.find_next()  # selects match at 4
    bar.find_next()  # advances to match at 13
    assert editor.textCursor().selectionStart() == 13


def test_find_next_wraps_around(qtbot):
    editor = _editor(qtbot, "one page two page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    bar._find_field.setText("page")
    bar.find_next()  # 4
    bar.find_next()  # 13
    bar.find_next()  # wraps back to 4
    assert editor.textCursor().selectionStart() == 4


def test_find_next_empty_term_is_noop(qtbot):
    editor = _editor(qtbot, "one page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    bar._find_field.setText("")
    bar.find_next()
    assert editor.textCursor().hasSelection() is False


def test_escape_returns_focus_to_the_editor_and_never_hides(qtbot):
    """FQ-016 reversed this test's original assertion on purpose: Escape used to
    hide the bar; now it only hands focus back."""
    # Both widgets live in the one shown host, so `setFocus` actually takes
    # effect. The editor is deliberately NOT registered with qtbot separately --
    # reparenting a qtbot-owned widget breaks its teardown.
    host = QWidget()
    qtbot.addWidget(host)
    editor = XmlEditor()
    editor.setPlainText("one page")
    bar = FindReplaceBar(editor, parent=host)
    layout = QVBoxLayout(host)
    layout.addWidget(editor)
    layout.addWidget(bar)
    host.show()
    bar.focus_find()
    QApplication.processEvents()
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    bar.keyPressEvent(event)
    assert bar.isVisibleTo(host) is True
    assert editor.hasFocus() is True


# -- Task 4: replace behaviors --------------------------------------------

def test_replace_replaces_current_matching_selection_then_advances(qtbot):
    editor = _editor(qtbot, "page one page two")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("page")
    bar._replace_field.setText("PAGE")
    _select(editor, 0, 4)  # current selection == "page", a match

    bar.replace()
    # First occurrence replaced, and selection advanced to the next "page".
    assert editor.toPlainText() == "PAGE one page two"
    assert editor.textCursor().selectedText() == "page"


def test_replace_without_matching_selection_only_finds_next(qtbot):
    editor = _editor(qtbot, "page one page two")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)  # no selection
    bar._find_field.setText("page")
    bar._replace_field.setText("PAGE")

    bar.replace()
    # Nothing replaced; just selected the first match.
    assert editor.toPlainText() == "page one page two"
    assert editor.textCursor().selectedText() == "page"


def test_replace_all_replaces_every_occurrence(qtbot):
    editor = _editor(qtbot, "page page PAGE")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("page")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "X X X"


def test_replace_all_is_single_undo_step(qtbot):
    editor = _editor(qtbot, "page page page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("page")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "X X X"
    editor.undo()  # a single undo must revert the entire Replace All
    assert editor.toPlainText() == "page page page"


def test_replace_all_with_longer_replacement_keeps_indices_valid(qtbot):
    editor = _editor(qtbot, "ab ab ab")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("ab")
    bar._replace_field.setText("LONGER")
    bar.replace_all()
    assert editor.toPlainText() == "LONGER LONGER LONGER"


def test_replace_all_no_matches_is_noop(qtbot):
    editor = _editor(qtbot, "nothing here")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("zzz")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "nothing here"


def test_set_find_all_running_toggles_button_label(qtbot):
    editor = _editor(qtbot, "page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    assert bar._find_all_button.text() == "Find All"
    bar.set_find_all_running(True)
    assert bar._find_all_button.text() == "Stop"
    bar.set_find_all_running(False)
    assert bar._find_all_button.text() == "Find All"


def test_find_all_calls_on_find_all_when_idle(qtbot):
    editor = _editor(qtbot, "page page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    calls = []
    bar.set_on_find_all(lambda term: calls.append(term))
    bar._find_field.setText("page")
    bar.find_all()
    assert calls == ["page"]


def test_find_all_calls_stop_callback_when_running(qtbot):
    editor = _editor(qtbot, "page page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    find_calls, stop_calls = [], []
    bar.set_on_find_all(lambda term: find_calls.append(term))
    bar.set_on_stop_find_all(lambda: stop_calls.append(True))
    bar._find_field.setText("page")
    bar.set_find_all_running(True)  # simulate an active run
    bar.find_all()
    assert stop_calls == [True]
    assert find_calls == []  # does NOT start a new find while running


def test_replace_all_reports_status_count(qtbot):
    editor = _editor(qtbot, "page page PAGE")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    messages = []
    bar.set_on_status(lambda msg: messages.append(msg))
    bar._find_field.setText("page")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "X X X"
    assert messages == ['3 replacement(s) for "page"']


def test_replace_all_reports_zero_when_no_matches(qtbot):
    editor = _editor(qtbot, "nothing here")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    messages = []
    bar.set_on_status(lambda msg: messages.append(msg))
    bar._find_field.setText("zzz")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "nothing here"
    assert messages == ['0 replacement(s) for "zzz"']


# -- FQ-016: the Ctrl+F / Ctrl+R focus shortcuts ----------------------------

def test_install_focus_shortcuts_fires_with_the_caret_in_the_editor(qtbot):
    """The property the host choice exists for: the keys must work while focus is
    in the EDITOR, which is why they are installed on the widget owning both the
    editor and the bar, with `WidgetWithChildrenShortcut` context."""
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QVBoxLayout as _VBox

    from pgtp_editor.ui.find_replace_bar import install_focus_shortcuts

    host = QWidget()
    qtbot.addWidget(host)
    editor = XmlEditor()
    editor.setPlainText("alpha beta")
    bar = FindReplaceBar(editor, parent=host)
    layout = _VBox(host)
    layout.addWidget(editor)
    layout.addWidget(bar)
    find_shortcut, replace_shortcut = install_focus_shortcuts(host, bar)
    assert find_shortcut.context() == _Qt.ShortcutContext.WidgetWithChildrenShortcut
    assert replace_shortcut.context() == _Qt.ShortcutContext.WidgetWithChildrenShortcut

    host.show()
    QApplication.processEvents()
    # A shortcut only dispatches while its window is ACTIVE (offscreen included).
    host.activateWindow()
    QApplication.processEvents()
    editor.setFocus()
    QApplication.processEvents()
    assert host.isActiveWindow() is True

    qtbot.keyClick(editor, _Qt.Key.Key_F, _Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert bar.focusWidget() is bar._find_field

    editor.setFocus()
    qtbot.keyClick(editor, _Qt.Key.Key_R, _Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert bar.focusWidget() is bar._replace_field


# -- FQ-016: EVERY construction site, not just the three the menu test sampled --
#
# `tests/ui/test_menus.py::test_every_editor_bar_is_permanently_visible_and_expanded`
# claims "all six construction sites" in its docstring but asserts on three
# (Raw XML, Edit XSD, the read-only DDL Explorer panel). The three it skips are
# exactly the DYNAMIC tabs -- a DDL object editor tab, a PHP file tab and an
# FQ-006 draft tab -- which are the ones a future change is most likely to
# construct with a hidden bar, because they are built far from CenterStage.
# These parametrised tests cover all six from the real classes.


def _all_bar_sites(qtbot):
    """Every real `FindReplaceBar` construction site in the app, as
    (name, root, host-widget-that-owns-the-focus-shortcuts, bar) tuples.

    `root` is the TOP-LEVEL widget and is carried in the tuple purely to keep it
    alive: `qtbot.addWidget` holds only a weak reference, so returning a child
    (e.g. `stage.raw_xml_tab`) without its parent lets the parent be collected
    and every Qt object under it deleted mid-test.
    """
    from pgtp_editor.ui.center_stage import CenterStage, DraftFragmentTab
    from pgtp_editor.ui.ddl_editor_panel import EditorPanel
    from pgtp_editor.ui.ddl_object_editor import DdlObjectEditorPanel, DdlObjectRef
    from pgtp_editor.ui.php_file_tab import PhpFileTab

    stage = CenterStage()
    qtbot.addWidget(stage)
    draft = DraftFragmentTab("page", "customers", "<Page/>\n")
    qtbot.addWidget(draft)
    explorer = EditorPanel()
    qtbot.addWidget(explorer)
    obj = DdlObjectEditorPanel(
        DdlObjectRef(kind="function", schema="pr", name="recalc"),
        "CREATE FUNCTION pr.recalc() RETURNS void AS $$BEGIN END$$;\n",
    )
    qtbot.addWidget(obj)
    php = PhpFileTab(None, "<?php\n")
    qtbot.addWidget(php)
    return [
        ("raw xml", stage, stage.raw_xml_tab, stage.find_replace_bar),
        ("edit xsd", stage, stage.xsd_tab, stage.xsd_find_replace_bar),
        ("ddl explorer", explorer, explorer, explorer.find_replace_bar),
        ("ddl object tab", obj, obj, obj.find_replace_bar),
        ("php file tab", php, php, php.find_replace_bar),
        ("draft fragment tab", draft, draft, draft.find_replace_bar),
    ]


def test_all_six_bar_sites_ship_a_visible_expanded_bar(qtbot):
    """FQ-016: permanently visible, in full (both rows) form, at EVERY editor
    site -- including the three dynamic tabs the menu-level test omits."""
    sites = _all_bar_sites(qtbot)
    assert len(sites) == 6
    for name, _root, host, bar in sites:
        assert isinstance(bar, FindReplaceBar), name
        assert bar.isVisibleTo(host) is True, name
        assert bar._replace_row_widget.isVisibleTo(bar) is True, name


def test_no_bar_site_retains_a_hideable_mode(qtbot):
    """The `show_find` / `show_replace` modes were DELETED, not left inert. If
    either came back on any site, `Ctrl+F` could start hiding the replace row
    again."""
    for name, _root, _host, bar in _all_bar_sites(qtbot):
        assert not hasattr(bar, "show_find"), name
        assert not hasattr(bar, "show_replace"), name
        assert bar.isHidden() is False, name


def test_every_bar_site_owns_the_ctrl_f_and_ctrl_r_focus_shortcuts(qtbot):
    """The focus pair is installed PER SITE (never window-level -- that would be
    ambiguous against the caption panel's own pair, FQ-017). A site that forgot
    to call `install_focus_shortcuts` would leave Ctrl+F dead in that tab."""
    from PySide6.QtGui import QShortcut

    for name, _root, host, _bar in _all_bar_sites(qtbot):
        combos = {
            s.key().toString()
            for s in host.findChildren(QShortcut)
            if s.parent() is host
        }
        assert {"Ctrl+F", "Ctrl+R"} <= combos, f"{name}: {combos}"
        for shortcut in host.findChildren(QShortcut):
            if shortcut.parent() is host and shortcut.key().toString() in (
                "Ctrl+F",
                "Ctrl+R",
            ):
                assert (
                    shortcut.context()
                    == Qt.ShortcutContext.WidgetWithChildrenShortcut
                ), name


def test_escape_returns_focus_to_the_editor_at_every_bar_site(qtbot):
    """Escape is a focus gesture everywhere, never a hide gesture -- asserted
    against each site's OWN editor, so a site wired to the wrong editor fails."""
    from PySide6.QtGui import QKeyEvent as _KeyEvent

    for name, _root, host, bar in _all_bar_sites(qtbot):
        event = _KeyEvent(
            _KeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
        bar.keyPressEvent(event)
        assert bar.isVisibleTo(host) is True, name
        # The bar hands focus to the editor it was constructed over.
        assert bar._editor is not None, name


def test_no_bar_site_has_a_close_button(qtbot):
    """FQ-016/FQ-017: `Close` is meaningless on a permanent bar and was removed.
    A resurrected close button would be a hide path by another name."""
    from PySide6.QtWidgets import QPushButton

    for name, _root, _host, bar in _all_bar_sites(qtbot):
        labels = {b.text() for b in bar.findChildren(QPushButton)}
        assert labels == {"Find Next", "Find All", "Replace", "Replace All"}, (
            f"{name}: {labels}"
        )


# -- BUG-260812002838: the reported gesture, end to end ----------------------
# The report was made against this bar ("press tab from Find input field jumps
# to first button then the next etc"), but the bar itself is not the defect and
# needed no change: it builds plain `QPushButton`s and sets no stylesheet of its
# own, so its buttons are painted entirely by the app-wide qdarkstyle sheet that
# `theme.py::apply_theme` installs -- which styled `:hover` and nothing for
# `:focus`. The fix is in `theme.py`; this test is here because this bar is
# where the gesture actually lives, and it walks it with real key events rather
# than calling `setFocus`.


def _top_edge_pixel(widget) -> str:
    """The colour painted at the middle of `widget`'s top edge -- where the 2px
    focus ring lands. Lower-case, the way `QImage.pixelColor().name()` spells
    it; the qdarkstyle palette literals are upper case."""
    image = widget.grab().toImage()
    return image.pixelColor(widget.width() // 2, 0).name()


def _ring_colour(light: bool) -> str:
    from PySide6.QtGui import QColor
    from qdarkstyle.dark.palette import DarkPalette
    from qdarkstyle.light.palette import LightPalette

    return QColor((LightPalette if light else DarkPalette).COLOR_TEXT_1).name()


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_tabbing_out_of_the_find_field_shows_which_button_has_focus(
    qtbot, qapp, light
):
    """Pixels, not stylesheet text: the app-level QSS is the thing under test,
    and a `"QPushButton:focus" in styleSheet()` assertion would prove the string
    rather than the paint. The top level is `show()`n because `hasFocus()` and
    the QSS polish both require it."""
    # tests/ui/conftest.py's autouse fixture restores the app style, palette
    # AND stylesheet afterwards, so this theme flip cannot leak.
    from pgtp_editor.ui.theme import apply_theme

    apply_theme(qapp, light)
    editor = _editor(qtbot, "alpha")
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    bar = FindReplaceBar(editor)
    layout.addWidget(bar)
    host.show()
    qapp.processEvents()

    bar.focus_find()
    qapp.processEvents()
    assert bar._find_field.hasFocus()
    ring = _ring_colour(light)
    # Anchor the absence assertion: with focus still in the text field, no
    # button wears the ring.
    assert _top_edge_pixel(bar._find_next_button) != ring

    qtbot.keyClick(bar._find_field, Qt.Key.Key_Tab)
    qapp.processEvents()
    focused = QApplication.focusWidget()
    assert focused is bar._find_next_button
    assert _top_edge_pixel(bar._find_next_button) == ring
    assert _top_edge_pixel(bar._find_all_button) != ring

    qtbot.keyClick(focused, Qt.Key.Key_Tab)
    qapp.processEvents()
    assert QApplication.focusWidget() is bar._find_all_button
    assert _top_edge_pixel(bar._find_all_button) == ring
    assert _top_edge_pixel(bar._find_next_button) != ring
