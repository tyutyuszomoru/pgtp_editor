# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Tests for the Edit XSD center-stage tab: per-tab dirty/save/find routing
(spec §11, Task 8)."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeySequence

from tests.ui._menu_helpers import find_action, find_top_menu

from pgtp_editor.schema_learning.storage import curated_xsd_path
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui import main_window as main_window_module

_MINIMAL = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Root" type="Root_Type"/>
  <xs:complexType name="Root_Type">
    <xs:attribute name="a" use="optional" type="xs:string"/>
  </xs:complexType>
</xs:schema>
"""


@pytest.fixture
def window(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    win = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(win)
    return win


def _seed(window, text=_MINIMAL):
    path = curated_xsd_path(window._schema_storage_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_open_edit_xsd_loads_file_into_tab(window):
    _seed(window)
    window._open_edit_xsd()
    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index
    assert stage.tabText(stage.xsd_tab_index) == "Edit XSD"
    assert stage.xsd_editor.toPlainText() == _MINIMAL
    assert window._xsd_dirty is False


def test_editing_marks_dirty_and_save_reparses(window):
    path = _seed(window)
    window._open_edit_xsd()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_MINIMAL.replace('name="a"', 'name="b"'))
    # setPlainText fires textChanged -> dirty
    assert window._xsd_dirty is True
    assert stage.tabText(stage.xsd_tab_index) == "Edit XSD *"
    window._save_curated_xsd()
    assert window._xsd_dirty is False
    assert 'name="b"' in path.read_text(encoding="utf-8")
    model = stage.xml_editor.schema_model()
    assert "b" in model.paths["Root"]["attributes"]


def test_malformed_save_still_writes_and_keeps_last_good(window):
    path = _seed(window)
    window._open_edit_xsd()
    window._load_curated_schema()
    good_model = window.center_stage.xml_editor.schema_model()
    window.center_stage.xsd_editor.setPlainText("<broken")
    window._save_curated_xsd()
    assert path.read_text(encoding="utf-8") == "<broken"   # text never lost
    assert window.center_stage.xml_editor.schema_model() is good_model


def test_ctrl_s_routes_to_active_tab(window):
    _seed(window)
    window._open_edit_xsd()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    window._save_active_tab()
    assert window._xsd_dirty is False  # saved the XSD, not the project


def test_find_bar_routing(window):
    _seed(window)
    window._open_edit_xsd()
    assert window._active_find_bar() is window.center_stage.xsd_find_replace_bar
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)
    assert window._active_find_bar() is window.center_stage.find_replace_bar


def test_close_event_xsd_dirty_discard_closes(window, monkeypatch):
    _seed(window)
    window._open_edit_xsd()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    assert window._xsd_dirty is True
    monkeypatch.setattr(window, "_confirm_close_xsd", lambda: "discard")
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()


def test_close_event_xsd_dirty_cancel_ignores(window, monkeypatch):
    _seed(window)
    window._open_edit_xsd()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    monkeypatch.setattr(window, "_confirm_close_xsd", lambda: "cancel")
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert window._xsd_dirty is True


def test_close_event_xsd_dirty_save_writes_and_closes(window, monkeypatch):
    path = _seed(window)
    window._open_edit_xsd()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL.replace('name="a"', 'name="b"'))
    monkeypatch.setattr(window, "_confirm_close_xsd", lambda: "save")
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    assert window._xsd_dirty is False
    assert 'name="b"' in path.read_text(encoding="utf-8")


def test_theme_toggle_does_not_mark_dirty(window):
    """Regression: apply_theme_colors's rehighlight() must not be mistaken
    for a real edit by either editor's dirty tracking (see
    XmlEditor.is_applying_theme)."""
    window.center_stage.xml_editor.apply_theme_colors(True)
    window.center_stage.xml_editor.apply_theme_colors(False)
    window.center_stage.xsd_editor.apply_theme_colors(True)
    window.center_stage.xsd_editor.apply_theme_colors(False)
    assert window._dirty is False
    assert window._xsd_dirty is False


def test_goto_xsd_navigates_to_attribute_line(window):
    _seed(window)
    window._load_curated_schema()
    window._goto_xsd("Root", "a")
    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index
    line = window._curated_schema.attribute_lines[("Root", "a")]
    assert stage.xsd_editor.textCursor().blockNumber() + 1 == line


def test_goto_xsd_falls_back_to_element_then_status(window):
    _seed(window)
    window._load_curated_schema()
    window._goto_xsd("Root", "missing")
    line = window._curated_schema.element_lines["Root"]
    assert window.center_stage.xsd_editor.textCursor().blockNumber() + 1 == line
    window._goto_xsd("Nope", "x")
    assert "not in the curated XSD" in window.statusBar().currentMessage()


def test_window_carries_goto_xsd_action_with_ctrl_l_shortcut(window):
    matches = [a for a in window.actions() if a.text() == "Go To XSD"]
    assert len(matches) == 1
    assert matches[0].shortcut() == QKeySequence("Ctrl+L")


def test_goto_xsd_at_cursor_navigates_to_attribute_line(window):
    _seed(window)
    window._load_curated_schema()
    stage = window.center_stage
    stage.xml_editor.setPlainText('<Root a="1"/>')
    cursor = stage.xml_editor.textCursor()
    cursor.setPosition(stage.xml_editor.toPlainText().index('"1"') + 1)
    stage.xml_editor.setTextCursor(cursor)

    window._goto_xsd_at_cursor()

    assert stage.currentIndex() == stage.xsd_tab_index
    line = window._curated_schema.attribute_lines[("Root", "a")]
    assert stage.xsd_editor.textCursor().blockNumber() + 1 == line


def test_goto_xsd_at_cursor_unresolvable_shows_status_and_stays_put(window):
    _seed(window)
    window._load_curated_schema()
    stage = window.center_stage
    stage.xml_editor.setPlainText("")

    window._goto_xsd_at_cursor()

    assert stage.currentIndex() != stage.xsd_tab_index
    assert (
        "Place the cursor inside an element"
        in window.statusBar().currentMessage()
    )


def test_edit_xsd_menu_action_loads_file_into_tab(window):
    _seed(window)
    menu = find_top_menu(window, "Schema")
    find_action(menu, "Edit XSD").trigger()
    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index
    assert stage.xsd_editor.toPlainText() == _MINIMAL


def test_verify_reports_clickable_issue_lines(window):
    _seed(window, _MINIMAL.replace(
        '<xs:attribute name="a" use="optional" type="xs:string"/>',
        '<xs:attribute name="a" use="optional" type="xs:string" label="wrong"/>',
    ))
    window._verify_xsd()
    items = [window.audit_panel.item(i) for i in range(window.audit_panel.count())]
    verify_items = [i for i in items if "VERIFY line" in i.text()]
    assert verify_items
    verify_item = verify_items[0]
    assert verify_item.data(Qt.ItemDataRole.UserRole + 1) == "xsd"
    assert isinstance(verify_item.data(Qt.ItemDataRole.UserRole), int)


def test_verify_menu_action_wired(window):
    _seed(window)
    menu = find_top_menu(window, "Schema")
    find_action(menu, "Verify XSD").trigger()
    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any(t.startswith("[Schema] VERIFY") for t in texts)


def test_clicking_verify_issue_navigates_to_xsd_line(window):
    _seed(window, _MINIMAL.replace(
        '<xs:attribute name="a" use="optional" type="xs:string"/>',
        '<xs:attribute name="a" use="optional" type="xs:string" label="wrong"/>',
    ))
    window._verify_xsd()
    items = [window.audit_panel.item(i) for i in range(window.audit_panel.count())]
    verify_item = next(i for i in items if "VERIFY line" in i.text())
    line = verify_item.data(Qt.ItemDataRole.UserRole)

    window._on_audit_item_clicked(verify_item)

    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index
    assert stage.xsd_editor.textCursor().blockNumber() + 1 == line


def test_save_auto_verifies_report_only(window):
    _seed(window)
    window._open_edit_xsd()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL)
    window._save_curated_xsd()
    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any(t.startswith("[Schema] VERIFY") for t in texts)


def test_export_copies_curated(window, monkeypatch, tmp_path):
    _seed(window)
    dest = tmp_path / "out.xsd"
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(dest), "")),
    )
    window._export_xsd()
    assert dest.read_text(encoding="utf-8") == _MINIMAL


def test_import_refuses_malformed(window, monkeypatch, tmp_path):
    _seed(window)
    bad = tmp_path / "bad.xsd"
    bad.write_text("<broken", encoding="utf-8")
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(bad), "")),
    )
    criticals = []
    monkeypatch.setattr(
        main_window_module.QMessageBox, "critical",
        staticmethod(lambda *a, **k: criticals.append(a)),
    )
    window._import_xsd()
    assert criticals
    assert curated_xsd_path(window._schema_storage_dir).read_text(encoding="utf-8") == _MINIMAL


def test_import_replaces_with_bak_and_reloads(window, monkeypatch, tmp_path):
    _seed(window)
    window._load_curated_schema()
    incoming = tmp_path / "incoming.xsd"
    incoming.write_text(_MINIMAL.replace('name="a"', 'name="z"'), encoding="utf-8")
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(incoming), "")),
    )
    window._import_xsd()
    path = curated_xsd_path(window._schema_storage_dir)
    assert 'name="z"' in path.read_text(encoding="utf-8")
    assert (path.parent / "curated.xsd.bak").read_text(encoding="utf-8") == _MINIMAL
    assert "z" in window.center_stage.xml_editor.schema_model().paths["Root"]["attributes"]


def test_import_with_dirty_tab_includes_notice(window, monkeypatch, tmp_path):
    """Importing while Edit XSD tab has unsaved edits should include a notice."""
    _seed(window)
    window._open_edit_xsd()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_MINIMAL.replace('name="a"', 'name="dirty"'))
    assert window._xsd_dirty is True

    incoming = tmp_path / "incoming.xsd"
    incoming.write_text(_MINIMAL.replace('name="a"', 'name="imported"'), encoding="utf-8")
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(incoming), "")),
    )
    window._import_xsd()

    # Tab should be reloaded with imported content
    assert stage.xsd_editor.toPlainText() == incoming.read_text(encoding="utf-8")
    assert window._xsd_dirty is False

    # Audit log should mention the tab was replaced
    audit_items = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    import_items = [t for t in audit_items if "Imported curated XSD" in t]
    assert import_items
    assert "(unsaved XSD tab edits were replaced)" in import_items[0]


def test_import_with_warnings_ask_user_decline(window, monkeypatch, tmp_path):
    """Importing a file with non-fatal dialect warnings should ask the user to confirm."""
    _seed(window)
    # Create a file with a non-fatal dialect issue (label on xs:complexType)
    with_warning = tmp_path / "with_warning.xsd"
    with_warning.write_text(_MINIMAL.replace(
        '<xs:complexType name="Root_Type">',
        '<xs:complexType name="Root_Type" label="wrong">'
    ), encoding="utf-8")

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(with_warning), "")),
    )

    # User declines import
    monkeypatch.setattr(
        main_window_module.QMessageBox, "question",
        staticmethod(lambda *a, **k: main_window_module.QMessageBox.StandardButton.No),
    )
    window._import_xsd()

    # Original file should be untouched
    path = curated_xsd_path(window._schema_storage_dir)
    assert path.read_text(encoding="utf-8") == _MINIMAL
    assert not (path.parent / "curated.xsd.bak").exists()


def test_import_with_warnings_ask_user_accept(window, monkeypatch, tmp_path):
    """Accepting import with warnings should proceed and report the issues."""
    _seed(window)
    # Create a file with a non-fatal dialect issue
    with_warning = tmp_path / "with_warning.xsd"
    with_warning.write_text(_MINIMAL.replace(
        '<xs:complexType name="Root_Type">',
        '<xs:complexType name="Root_Type" label="wrong">'
    ), encoding="utf-8")

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(with_warning), "")),
    )

    # User accepts import
    monkeypatch.setattr(
        main_window_module.QMessageBox, "question",
        staticmethod(lambda *a, **k: main_window_module.QMessageBox.StandardButton.Yes),
    )
    window._import_xsd()

    # File should be replaced
    path = curated_xsd_path(window._schema_storage_dir)
    assert 'label="wrong"' in path.read_text(encoding="utf-8")

    # Warnings should be reported in audit panel
    audit_items = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    verify_items = [t for t in audit_items if "VERIFY" in t]
    assert verify_items


def test_import_binary_file_shows_error(window, monkeypatch, tmp_path):
    """Importing a binary or non-UTF-8 file should show an error and preserve curated.xsd."""
    _seed(window)
    binary = tmp_path / "binary.xsd"
    binary.write_bytes(bytes([0xff, 0xfe, 0x00]))

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(binary), "")),
    )

    criticals = []
    monkeypatch.setattr(
        main_window_module.QMessageBox, "critical",
        staticmethod(lambda *a, **k: criticals.append(a)),
    )
    window._import_xsd()

    # Critical error should be shown
    assert criticals
    assert "Import Failed" in criticals[0][1]

    # Original file should be untouched
    path = curated_xsd_path(window._schema_storage_dir)
    assert path.read_text(encoding="utf-8") == _MINIMAL
