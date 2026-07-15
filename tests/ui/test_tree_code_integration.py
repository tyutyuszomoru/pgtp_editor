"""UI tests for SP3: MainWindow wiring for the tree's event-node "Edit code…"
and the Page "Add Event Handler ▸" submenu. No .exec() / no modal loop."""
from lxml import etree

from pgtp_editor.model.nodes import EventNode, PageNode
from pgtp_editor.ui.main_window import MainWindow


# A buffer whose <Page> at line 3 already has an OnPreparePage handler on line 5.
BUFFER = (
    "<Project>\n"
    "  <Pages>\n"
    '    <Page fileName="equipment">\n'
    "      <EventHandlers>\n"
    '        <OnPreparePage enabled="true">$x-&gt;go();</OnPreparePage>\n'
    "      </EventHandlers>\n"
    "    </Page>\n"
    "  </Pages>\n"
    "</Project>\n"
)


# ---------------------------------------------------------------------------
# event-node Edit code…
# ---------------------------------------------------------------------------

def test_edit_event_code_opens_dialog_with_body_and_language(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(BUFFER)

    node = EventNode(
        identity="OnPreparePage",
        tag_name="OnPreparePage",
        side="S",
        text="$x->go();",
        sourceline=5,
    )
    window._on_tree_edit_event_code(node)

    dialog = window._code_editor_dialog
    assert dialog is not None
    assert dialog._language == "php"  # server side
    assert dialog.code() == "$x->go();"
    assert "OnPreparePage" in dialog.windowTitle()


def test_edit_event_code_client_uses_js(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(BUFFER)
    node = EventNode(
        identity="OnBeforePageLoad",
        tag_name="OnBeforePageLoad",
        side="C",
        text="alert(1);",
        sourceline=5,
    )
    window._on_tree_edit_event_code(node)
    assert window._code_editor_dialog._language == "js"


def test_edit_event_code_save_writes_back_to_buffer(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(BUFFER)
    node = EventNode(
        identity="OnPreparePage",
        tag_name="OnPreparePage",
        side="S",
        text="$x->go();",
        sourceline=5,
    )
    window._on_tree_edit_event_code(node)
    window._code_editor_dialog.set_code("if (a < b) c();")
    window._code_editor_dialog.save()

    raw = window.center_stage.xml_editor.toPlainText()
    assert "if (a &lt; b) c();" in raw
    root = etree.fromstring(raw.encode("utf-8"))
    assert root.find(".//OnPreparePage").text == "if (a < b) c();"


# ---------------------------------------------------------------------------
# Page Add Event Handler ▸ (insert)
# ---------------------------------------------------------------------------

def test_add_event_handler_opens_empty_dialog_in_language(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(BUFFER)
    page = PageNode(identity="equipment", attrib={"fileName": "equipment"}, sourceline=3)

    window._on_tree_add_event_handler(page, "OnAfterPageLoad")

    dialog = window._code_editor_dialog
    assert dialog is not None
    assert dialog.code() == ""  # empty to start
    assert dialog._language == "js"  # OnAfterPageLoad is client-side
    assert "OnAfterPageLoad" in dialog.windowTitle()


def test_add_event_handler_save_inserts_into_buffer(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(BUFFER)
    page = PageNode(identity="equipment", attrib={"fileName": "equipment"}, sourceline=3)

    window._on_tree_add_event_handler(page, "OnAfterPageLoad")
    window._code_editor_dialog.set_code("doThing();")
    window._code_editor_dialog.save()

    raw = window.center_stage.xml_editor.toPlainText()
    assert '<OnAfterPageLoad enabled="true">' in raw
    assert "doThing();" in raw
    # Re-parses and the new handler joins the page's EventHandlers.
    root = etree.fromstring(raw.encode("utf-8"))
    handlers = root.find(".//Page/EventHandlers")
    tags = [c.tag for c in handlers]
    assert "OnPreparePage" in tags and "OnAfterPageLoad" in tags


def test_add_event_handler_server_uses_php(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(BUFFER)
    page = PageNode(identity="equipment", attrib={"fileName": "equipment"}, sourceline=3)
    window._on_tree_add_event_handler(page, "OnBeforePageExecute")
    assert window._code_editor_dialog._language == "php"
