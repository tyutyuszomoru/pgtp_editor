from pgtp_editor.ui.main_window import MainWindow


def test_window_title(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "PGTP Editor"


def test_default_size(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.size().width() == 1400
    assert window.size().height() == 900
