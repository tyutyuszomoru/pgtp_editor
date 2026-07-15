"""UI tests for SP2: XmlEditor code-region styling + "Edit code…" affordance,
and MainWindow's CodeEditorDialog write-back. No .exec() / no modal loop."""
from lxml import etree

from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.xml_editor import XmlEditor


MULTILINE = (
    "<Page>\n"
    '  <EventHandlers>\n'
    '    <OnPreparePage enabled="true">\n'
    "$this-&gt;dataset-&gt;AddDistinct('id');\n"
    "    </OnPreparePage>\n"
    "  </EventHandlers>\n"
    "</Page>\n"
)

CLIENT_SAMPLE = (
    "<Page>\n"
    '  <OnBeforePageLoad enabled="true">alert(1);</OnBeforePageLoad>\n'
    "</Page>\n"
)


def _place_cursor_on_line(editor, line):
    block = editor.document().findBlockByNumber(line - 1)
    from PySide6.QtGui import QTextCursor

    editor.setTextCursor(QTextCursor(block))


# ---------------------------------------------------------------------------
# Code-region styling
# ---------------------------------------------------------------------------

def test_code_region_lines_get_background_selection(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(MULTILINE)
    # There is exactly one handler spanning 3 lines (open .. close inclusive).
    assert len(editor._code_region_selections) == 3
    bg = editor._code_region_selections[0].format.background().color()
    assert bg == editor._code_region_color


def test_code_region_selections_apply_when_read_only(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setReadOnly(True)
    editor.setPlainText(MULTILINE)
    assert len(editor._code_region_selections) == 3


def test_no_code_region_when_no_handlers(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<Page><Caption>x</Caption></Page>")
    assert editor._code_region_selections == []


# ---------------------------------------------------------------------------
# event_body_start_line_at_cursor + context menu
# ---------------------------------------------------------------------------

def test_start_line_at_cursor_inside_body(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(MULTILINE)
    _place_cursor_on_line(editor, 4)  # the code line
    assert editor.event_body_start_line_at_cursor() == 3


def test_start_line_at_cursor_on_open_tag_line(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(MULTILINE)
    _place_cursor_on_line(editor, 3)  # the <OnPreparePage> line
    assert editor.event_body_start_line_at_cursor() == 3


def test_start_line_at_cursor_outside_body(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(MULTILINE)
    _place_cursor_on_line(editor, 1)  # <Page>
    assert editor.event_body_start_line_at_cursor() is None


def test_edit_code_action_present_inside_body(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(MULTILINE)
    _place_cursor_on_line(editor, 4)
    menu = editor._build_context_menu()
    labels = [a.text() for a in menu.actions()]
    assert "Edit code…" in labels


def test_edit_code_action_absent_outside_body(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(MULTILINE)
    _place_cursor_on_line(editor, 1)
    menu = editor._build_context_menu()
    labels = [a.text() for a in menu.actions()]
    assert "Edit code…" not in labels


def test_edit_code_action_emits_start_line(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(MULTILINE)
    _place_cursor_on_line(editor, 4)
    menu = editor._build_context_menu()
    edit_action = next(a for a in menu.actions() if a.text() == "Edit code…")

    received = []
    editor.edit_code_requested.connect(received.append)
    edit_action.trigger()
    assert received == [3]


# ---------------------------------------------------------------------------
# MainWindow: opening the dialog + write-back on save
# ---------------------------------------------------------------------------

def test_edit_code_opens_dialog_with_body_and_language(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(MULTILINE)

    window._on_edit_code_requested(3)
    dialog = window._code_editor_dialog
    assert dialog is not None
    assert dialog._language == "php"  # server-side handler
    assert "$this->dataset->AddDistinct('id');" in dialog.code()
    assert "&gt;" not in dialog.code()  # displayed unescaped
    assert "OnPreparePage" in dialog.windowTitle()


def test_edit_code_client_handler_uses_js(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(CLIENT_SAMPLE)

    window._on_edit_code_requested(2)
    assert window._code_editor_dialog._language == "js"


def test_save_writes_escaped_body_into_buffer_and_reparses(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(MULTILINE)

    window._on_edit_code_requested(3)
    dialog = window._code_editor_dialog
    dialog.set_code("if (a < b && c > d) new();")
    dialog.save()  # emits saved(new_code) -> write-back

    raw = window.center_stage.xml_editor.toPlainText()
    # Escaped code sits between the tags.
    assert "if (a &lt; b &amp;&amp; c &gt; d) new();" in raw
    assert "AddDistinct" not in raw
    # Tags/attributes preserved and the whole document re-parses.
    assert '<OnPreparePage enabled="true">' in raw
    root = etree.fromstring(raw.encode("utf-8"))
    assert root.find(".//OnPreparePage").text == "if (a < b && c > d) new();"


def test_save_simple_body_present_between_tags(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(MULTILINE)

    window._on_edit_code_requested(3)
    window._code_editor_dialog.set_code("new;")
    window._code_editor_dialog.save()

    raw = window.center_stage.xml_editor.toPlainText()
    inner = raw.split('<OnPreparePage enabled="true">', 1)[1].split(
        "</OnPreparePage>", 1
    )[0]
    assert "new;" in inner
    etree.fromstring(raw.encode("utf-8"))  # re-parses


def test_cancel_does_not_change_buffer(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(MULTILINE)
    before = window.center_stage.xml_editor.toPlainText()

    window._on_edit_code_requested(3)
    window._code_editor_dialog.set_code("SHOULD NOT BE WRITTEN")
    window._code_editor_dialog.cancel()

    assert window.center_stage.xml_editor.toPlainText() == before
