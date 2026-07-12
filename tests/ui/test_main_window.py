from PySide6.QtCore import Qt

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


def test_tree_dock_on_left(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.dockWidgetArea(window.tree_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.tree_dock.windowTitle() == "Project Tree"


def test_audit_dock_on_bottom(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.dockWidgetArea(window.audit_dock) == Qt.DockWidgetArea.BottomDockWidgetArea
    assert window.audit_dock.windowTitle() == "Audit / Problems"


def test_properties_dock_on_right(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.dockWidgetArea(window.properties_dock) == Qt.DockWidgetArea.RightDockWidgetArea
    assert window.properties_dock.windowTitle() == "Properties"


def test_center_stage_is_central_widget(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.centralWidget() is window.center_stage


def test_not_implemented_shows_status_message(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._not_implemented("Delete Page")
    assert window.statusBar().currentMessage() == "Not yet implemented: Delete Page"


from pgtp_editor.ui.properties_panel import PropertiesPanel


def test_properties_panel_is_a_real_properties_panel(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert isinstance(window.properties_panel, PropertiesPanel)
    assert window.properties_dock.widget() is window.properties_panel


def test_selecting_tree_item_populates_properties_panel(qtbot):
    from tests.ui._sample_project import build_sample_project

    window = MainWindow()
    qtbot.addWidget(window)
    window.project_tree.populate_from_project(build_sample_project())

    page_item = window.project_tree.topLevelItem(0)
    window.project_tree.setCurrentItem(page_item)

    assert window.properties_panel.is_showing_empty_state() is False
    assert window.properties_panel.header_text().startswith("Page:")


def test_clearing_tree_selection_returns_properties_panel_to_empty_state(qtbot):
    from tests.ui._sample_project import build_sample_project

    window = MainWindow()
    qtbot.addWidget(window)
    window.project_tree.populate_from_project(build_sample_project())
    window.project_tree.setCurrentItem(window.project_tree.topLevelItem(0))
    window.project_tree.setCurrentItem(None)

    assert window.properties_panel.is_showing_empty_state() is True
