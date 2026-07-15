from pgtp_editor.ui.schema_viewer import SchemaViewerWindow


def test_set_content_puts_text_in_readonly_editor(qtbot):
    window = SchemaViewerWindow()
    qtbot.addWidget(window)

    window.set_content("<?xml version='1.0'?>\n<root/>")

    assert window.editor.isReadOnly() is True
    assert window.editor.toPlainText() == "<?xml version='1.0'?>\n<root/>"


def test_set_title_sets_window_title(qtbot):
    window = SchemaViewerWindow()
    qtbot.addWidget(window)

    window.set_title("Schema XSD")

    assert window.windowTitle() == "Schema XSD"
