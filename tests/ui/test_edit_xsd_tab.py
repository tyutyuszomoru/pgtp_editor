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
from pgtp_editor.ui import xsd_controller as xsd_controller_module
from pgtp_editor.ui import modals

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


def _unseed(window):
    """Remove the curated.xsd the one-time bundled bootstrap seeded during
    MainWindow.__init__, so a test can exercise the truly-absent-file path."""
    path = curated_xsd_path(window._schema_storage_dir)
    if path.exists():
        path.unlink()
    window._xsd_ui.curated_schema = None
    return path


def test_open_edit_xsd_loads_file_into_tab(window):
    _seed(window)
    window._xsd_ui.open()
    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index
    assert stage.tabText(stage.xsd_tab_index) == "Edit XSD"
    assert stage.xsd_editor.toPlainText() == _MINIMAL
    assert window._xsd_ui.dirty is False


def test_editing_marks_dirty_and_save_reparses(window):
    path = _seed(window)
    window._xsd_ui.open()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_MINIMAL.replace('name="a"', 'name="b"'))
    # setPlainText fires textChanged -> dirty
    assert window._xsd_ui.dirty is True
    assert stage.tabText(stage.xsd_tab_index) == "Edit XSD *"
    window._xsd_ui.save()
    assert window._xsd_ui.dirty is False
    assert 'name="b"' in path.read_text(encoding="utf-8")
    model = stage.xml_editor.schema_model()
    assert "b" in model.paths["Root"]["attributes"]


def test_malformed_save_still_writes_and_keeps_last_good(window):
    path = _seed(window)
    window._xsd_ui.open()
    window._xsd_ui.load_curated()
    good_model = window.center_stage.xml_editor.schema_model()
    window.center_stage.xsd_editor.setPlainText("<broken")
    window._xsd_ui.save()
    assert path.read_text(encoding="utf-8") == "<broken"   # text never lost
    assert window.center_stage.xml_editor.schema_model() is good_model


def test_ctrl_s_routes_to_active_tab(window):
    _seed(window)
    window._xsd_ui.open()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    window._save_active_tab()
    assert window._xsd_ui.dirty is False  # saved the XSD, not the project


def test_find_bar_routing(window):
    _seed(window)
    window._xsd_ui.open()
    assert window._find_ui.active_find_bar() is window.center_stage.xsd_find_replace_bar
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)
    assert window._find_ui.active_find_bar() is window.center_stage.find_replace_bar


def test_close_event_xsd_dirty_discard_closes(window, monkeypatch):
    _seed(window)
    window._xsd_ui.open()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    assert window._xsd_ui.dirty is True
    monkeypatch.setattr(window._xsd_ui, "confirm_close", lambda: "discard")
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()


def test_close_event_xsd_dirty_cancel_ignores(window, monkeypatch):
    _seed(window)
    window._xsd_ui.open()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    monkeypatch.setattr(window._xsd_ui, "confirm_close", lambda: "cancel")
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert window._xsd_ui.dirty is True


def test_close_event_xsd_dirty_save_writes_and_closes(window, monkeypatch):
    path = _seed(window)
    window._xsd_ui.open()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL.replace('name="a"', 'name="b"'))
    monkeypatch.setattr(window._xsd_ui, "confirm_close", lambda: "save")
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    assert window._xsd_ui.dirty is False
    assert 'name="b"' in path.read_text(encoding="utf-8")


def test_xsd_tab_close_button_no_unsaved_changes_hides_directly(window):
    """BUG-001: clicking the Edit XSD tab's ✕ with no unsaved changes hides
    it and switches to Raw XML without any prompt."""
    _seed(window)
    window._xsd_ui.open()
    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index

    stage.tabCloseRequested.emit(stage.xsd_tab_index)

    assert stage.isTabVisible(stage.xsd_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index


def test_xsd_tab_close_button_dirty_discard_hides_without_saving(window, monkeypatch):
    path = _seed(window)
    window._xsd_ui.open()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    assert window._xsd_ui.dirty is True
    monkeypatch.setattr(window._xsd_ui, "confirm_close", lambda: "discard")

    stage.tabCloseRequested.emit(stage.xsd_tab_index)

    assert stage.isTabVisible(stage.xsd_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index
    assert path.read_text(encoding="utf-8") == _MINIMAL  # discarded, not written


def test_xsd_tab_close_button_dirty_save_writes_and_hides(window, monkeypatch):
    path = _seed(window)
    window._xsd_ui.open()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_MINIMAL.replace('name="a"', 'name="b"'))
    monkeypatch.setattr(window._xsd_ui, "confirm_close", lambda: "save")

    stage.tabCloseRequested.emit(stage.xsd_tab_index)

    assert window._xsd_ui.dirty is False
    assert 'name="b"' in path.read_text(encoding="utf-8")
    assert stage.isTabVisible(stage.xsd_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index


def test_xsd_tab_close_button_dirty_cancel_leaves_tab_open_and_dirty(window, monkeypatch):
    _seed(window)
    window._xsd_ui.open()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    monkeypatch.setattr(window._xsd_ui, "confirm_close", lambda: "cancel")

    stage.tabCloseRequested.emit(stage.xsd_tab_index)

    assert window._xsd_ui.dirty is True
    assert stage.isTabVisible(stage.xsd_tab_index) is True
    assert stage.currentIndex() == stage.xsd_tab_index
    assert stage.tabText(stage.xsd_tab_index) == "Edit XSD *"
    window._xsd_ui.confirm_close = lambda: "discard"  # silence teardown close prompt


def test_xsd_tab_close_button_save_failure_keeps_tab_open(window, monkeypatch):
    """A disk error during the close-time save must not drop the tab or the
    unsaved edits (mirrors closeEvent's same guard)."""
    _seed(window)
    window._xsd_ui.open()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    monkeypatch.setattr(window._xsd_ui, "confirm_close", lambda: "save")

    def _boom(self, *a, **k):
        raise OSError("read-only filesystem")
    monkeypatch.setattr(xsd_controller_module.Path, "write_text", _boom)
    monkeypatch.setattr(
        modals.QMessageBox, "critical", staticmethod(lambda *a, **k: None)
    )

    stage.tabCloseRequested.emit(stage.xsd_tab_index)

    assert window._xsd_ui.dirty is True
    assert stage.isTabVisible(stage.xsd_tab_index) is True
    window._xsd_ui.confirm_close = lambda: "discard"  # silence teardown close prompt


def test_xsd_tab_close_button_works_in_learned_mode(window, monkeypatch):
    """BUG-001's fix must not be curated-mode-only: Edit AutoXSD (mode
    "learned") shares the same xsd_tab_index/xsd_close_requested wiring, so
    the ✕ has to route through the identical dirty-check flow there too."""
    from pgtp_editor.schema_learning.storage import learned_xsd_path

    learned_path = learned_xsd_path(window._schema_storage_dir)
    learned_path.parent.mkdir(parents=True, exist_ok=True)
    learned_path.write_text(_MINIMAL, encoding="utf-8")
    window._xsd_ui.open_auto()
    stage = window.center_stage
    assert window._xsd_ui.mode == "learned"
    assert stage.tabText(stage.xsd_tab_index) == "Edit AutoXSD"
    stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    assert window._xsd_ui.dirty is True
    monkeypatch.setattr(window._xsd_ui, "confirm_close", lambda: "discard")

    stage.tabCloseRequested.emit(stage.xsd_tab_index)

    assert stage.isTabVisible(stage.xsd_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index
    assert learned_path.read_text(encoding="utf-8") == _MINIMAL  # discarded, not written


def test_xsd_tab_close_when_not_current_tab_does_not_steal_focus(window):
    """Regression for CenterStage.hide_edit_xsd's not-current guard, driven
    through the full MainWindow close flow rather than CenterStage directly:
    switching away from the Edit XSD tab before closing it must not force
    focus back onto it or onto Raw XML."""
    _seed(window)
    window._xsd_ui.open()
    stage = window.center_stage
    stage.setCurrentIndex(stage.raw_xml_tab_index)
    assert stage.isTabVisible(stage.xsd_tab_index) is True

    window._xsd_ui.on_close_requested()

    assert stage.isTabVisible(stage.xsd_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index  # already there, unchanged


def test_theme_toggle_does_not_mark_dirty(window):
    """Regression: apply_theme_colors's rehighlight() must not be mistaken
    for a real edit by either editor's dirty tracking (see
    XmlEditor.is_applying_theme)."""
    window.center_stage.xml_editor.apply_theme_colors(True)
    window.center_stage.xml_editor.apply_theme_colors(False)
    window.center_stage.xsd_editor.apply_theme_colors(True)
    window.center_stage.xsd_editor.apply_theme_colors(False)
    assert window._dirty is False
    assert window._xsd_ui.dirty is False


def test_goto_xsd_navigates_to_attribute_line(window):
    _seed(window)
    window._xsd_ui.load_curated()
    window._xsd_ui.goto("Root", "a")
    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index
    line = window._xsd_ui.curated_schema.attribute_lines[("Root", "a")]
    assert stage.xsd_editor.textCursor().blockNumber() + 1 == line


def test_goto_xsd_falls_back_to_element_then_status(window):
    _seed(window)
    window._xsd_ui.load_curated()
    window._xsd_ui.goto("Root", "missing")
    line = window._xsd_ui.curated_schema.element_lines["Root"]
    assert window.center_stage.xsd_editor.textCursor().blockNumber() + 1 == line
    window._xsd_ui.goto("Nope", "x")
    assert "not in the curated XSD" in window.statusBar().currentMessage()


def test_window_carries_goto_xsd_action_with_ctrl_l_shortcut(window):
    matches = [a for a in window.actions() if a.text() == "Go To XSD"]
    assert len(matches) == 1
    assert matches[0].shortcut() == QKeySequence("Ctrl+L")


def test_goto_xsd_at_cursor_navigates_to_attribute_line(window):
    _seed(window)
    window._xsd_ui.load_curated()
    stage = window.center_stage
    stage.xml_editor.setPlainText('<Root a="1"/>')
    cursor = stage.xml_editor.textCursor()
    cursor.setPosition(stage.xml_editor.toPlainText().index('"1"') + 1)
    stage.xml_editor.setTextCursor(cursor)

    window._xsd_ui.goto_at_cursor()

    assert stage.currentIndex() == stage.xsd_tab_index
    line = window._xsd_ui.curated_schema.attribute_lines[("Root", "a")]
    assert stage.xsd_editor.textCursor().blockNumber() + 1 == line


def test_goto_xsd_at_cursor_unresolvable_shows_status_and_stays_put(window):
    _seed(window)
    window._xsd_ui.load_curated()
    stage = window.center_stage
    stage.xml_editor.setPlainText("")

    window._xsd_ui.goto_at_cursor()

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
    window._xsd_ui.verify()
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
    window._xsd_ui.verify()
    items = [window.audit_panel.item(i) for i in range(window.audit_panel.count())]
    verify_item = next(i for i in items if "VERIFY line" in i.text())
    line = verify_item.data(Qt.ItemDataRole.UserRole)

    window._on_audit_item_clicked(verify_item)

    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index
    assert stage.xsd_editor.textCursor().blockNumber() + 1 == line


def test_save_auto_verifies_report_only(window):
    _seed(window)
    window._xsd_ui.open()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL)
    window._xsd_ui.save()
    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any(t.startswith("[Schema] VERIFY") for t in texts)


def test_export_copies_curated(window, monkeypatch, tmp_path):
    _seed(window)
    dest = tmp_path / "out.xsd"
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(dest), "")),
    )
    window._xsd_ui.export()
    assert dest.read_text(encoding="utf-8") == _MINIMAL


def test_import_refuses_malformed(window, monkeypatch, tmp_path):
    _seed(window)
    bad = tmp_path / "bad.xsd"
    bad.write_text("<broken", encoding="utf-8")
    monkeypatch.setattr(
        modals.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(bad), "")),
    )
    criticals = []
    monkeypatch.setattr(
        modals.QMessageBox, "critical",
        staticmethod(lambda *a, **k: criticals.append(a)),
    )
    window._xsd_ui.import_()
    assert criticals
    assert curated_xsd_path(window._schema_storage_dir).read_text(encoding="utf-8") == _MINIMAL


def test_import_replaces_with_bak_and_reloads(window, monkeypatch, tmp_path):
    _seed(window)
    window._xsd_ui.load_curated()
    incoming = tmp_path / "incoming.xsd"
    incoming.write_text(_MINIMAL.replace('name="a"', 'name="z"'), encoding="utf-8")
    monkeypatch.setattr(
        modals.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(incoming), "")),
    )
    window._xsd_ui.import_()
    path = curated_xsd_path(window._schema_storage_dir)
    assert 'name="z"' in path.read_text(encoding="utf-8")
    assert (path.parent / "curated.xsd.bak").read_text(encoding="utf-8") == _MINIMAL
    assert "z" in window.center_stage.xml_editor.schema_model().paths["Root"]["attributes"]


def test_import_with_dirty_tab_includes_notice(window, monkeypatch, tmp_path):
    """Importing while Edit XSD tab has unsaved edits should include a notice."""
    _seed(window)
    window._xsd_ui.open()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_MINIMAL.replace('name="a"', 'name="dirty"'))
    assert window._xsd_ui.dirty is True

    incoming = tmp_path / "incoming.xsd"
    incoming.write_text(_MINIMAL.replace('name="a"', 'name="imported"'), encoding="utf-8")
    monkeypatch.setattr(
        modals.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(incoming), "")),
    )
    window._xsd_ui.import_()

    # Tab should be reloaded with imported content
    assert stage.xsd_editor.toPlainText() == incoming.read_text(encoding="utf-8")
    assert window._xsd_ui.dirty is False

    # Audit log should mention the tab was replaced
    audit_items = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    import_items = [t for t in audit_items if "Imported Edit XSD" in t]
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
        modals.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(with_warning), "")),
    )

    # User declines import
    monkeypatch.setattr(
        modals.QMessageBox, "question",
        staticmethod(lambda *a, **k: modals.QMessageBox.StandardButton.No),
    )
    window._xsd_ui.import_()

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
        modals.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(with_warning), "")),
    )

    # User accepts import
    monkeypatch.setattr(
        modals.QMessageBox, "question",
        staticmethod(lambda *a, **k: modals.QMessageBox.StandardButton.Yes),
    )
    window._xsd_ui.import_()

    # File should be replaced
    path = curated_xsd_path(window._schema_storage_dir)
    assert 'label="wrong"' in path.read_text(encoding="utf-8")

    # Warnings should be reported in audit panel
    audit_items = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    verify_items = [t for t in audit_items if "VERIFY" in t]
    assert verify_items


def test_open_edit_xsd_without_file_loads_empty_skeleton(window):
    """First run, before any curated.xsd exists: Edit XSD opens an empty
    xs:schema skeleton instead of erroring on the missing file."""
    _unseed(window)
    window._xsd_ui.open()
    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index
    text = stage.xsd_editor.toPlainText()
    assert text.startswith('<?xml version="1.0"')
    assert "<xs:schema" in text and "</xs:schema>" in text
    assert window._xsd_ui.dirty is False


def test_verify_without_curated_shows_status(window):
    """Verify XSD with a clean tab and no curated.xsd on disk: status
    message, no VERIFY audit lines."""
    _unseed(window)
    window._xsd_ui.verify()
    assert "No Edit XSD file yet." in window.statusBar().currentMessage()
    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert not any(t.startswith("[Schema] VERIFY") for t in texts)


def test_verify_checks_dirty_tab_text_not_saved_file(window):
    """When the Edit XSD tab has unsaved edits, Verify XSD must check the
    live tab text — the thing the user is looking at — not the clean file
    on disk (spec §11)."""
    _seed(window)  # saved file is clean, would verify with no issues
    window._xsd_ui.open()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL.replace(
        '<xs:attribute name="a" use="optional" type="xs:string"/>',
        '<xs:attribute name="a" use="optional" type="xs:string" label="wrong"/>',
    ))
    assert window._xsd_ui.dirty is True
    window._xsd_ui.verify()
    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any("VERIFY line" in t for t in texts)
    window._xsd_ui.confirm_close = lambda: "discard"  # silence teardown close prompt


def test_clicking_verify_issue_with_dirty_tab_preserves_edits(window):
    """Clicking a VERIFY audit line while the Edit XSD tab holds unsaved
    edits must navigate WITHOUT reloading curated.xsd over the user's
    text (XsdController.open's dirty guard)."""
    _seed(window)
    window._xsd_ui.open()
    dirty_text = _MINIMAL.replace(
        '<xs:attribute name="a" use="optional" type="xs:string"/>',
        '<xs:attribute name="a" use="optional" type="xs:string" label="wrong"/>',
    )
    window.center_stage.xsd_editor.setPlainText(dirty_text)
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)
    window._xsd_ui.verify()
    items = [window.audit_panel.item(i) for i in range(window.audit_panel.count())]
    verify_item = next(i for i in items if "VERIFY line" in i.text())

    window._on_audit_item_clicked(verify_item)

    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index
    assert stage.xsd_editor.toPlainText() == dirty_text  # edits NOT clobbered
    assert window._xsd_ui.dirty is True
    line = verify_item.data(Qt.ItemDataRole.UserRole)
    assert stage.xsd_editor.textCursor().blockNumber() + 1 == line
    window._xsd_ui.confirm_close = lambda: "discard"  # silence teardown close prompt


def test_export_without_curated_shows_status_and_no_dialog(window, monkeypatch):
    _unseed(window)
    dialog_calls = []
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: dialog_calls.append(a) or ("", "")),
    )
    window._xsd_ui.export()
    assert "No Edit XSD file yet." in window.statusBar().currentMessage()
    assert not dialog_calls


def test_export_with_dirty_tab_shows_save_first_and_no_dialog(window, monkeypatch):
    _seed(window)
    window._xsd_ui.open()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    assert window._xsd_ui.dirty is True
    dialog_calls = []
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: dialog_calls.append(a) or ("", "")),
    )
    window._xsd_ui.export()
    assert "save it first" in window.statusBar().currentMessage()
    assert not dialog_calls
    window._xsd_ui.confirm_close = lambda: "discard"  # silence teardown close prompt


def test_export_cancelled_dialog_is_noop(window, monkeypatch, tmp_path):
    _seed(window)
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: ("", "")),
    )
    criticals = []
    monkeypatch.setattr(
        modals.QMessageBox, "critical",
        staticmethod(lambda *a, **k: criticals.append(a)),
    )
    window._xsd_ui.export()
    assert not criticals


def test_export_copy_oserror_shows_critical(window, monkeypatch, tmp_path):
    _seed(window)
    dest = tmp_path / "out.xsd"
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(dest), "")),
    )
    def _boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(xsd_controller_module.shutil, "copyfile", _boom)
    criticals = []
    monkeypatch.setattr(
        modals.QMessageBox, "critical",
        staticmethod(lambda *a, **k: criticals.append(a)),
    )
    window._xsd_ui.export()
    assert criticals
    assert "Export Failed" in criticals[0][1]
    assert not dest.exists()


def test_import_write_oserror_shows_critical_and_keeps_dirty(window, monkeypatch, tmp_path):
    """If replacing curated.xsd fails at write time, the user sees a
    critical dialog and the tab's dirty state is NOT cleared."""
    _seed(window)
    window._xsd_ui.open()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    assert window._xsd_ui.dirty is True

    incoming = tmp_path / "incoming.xsd"
    incoming.write_text(_MINIMAL.replace('name="a"', 'name="z"'), encoding="utf-8")
    monkeypatch.setattr(
        modals.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(incoming), "")),
    )
    real_write_text = xsd_controller_module.Path.write_text
    target = curated_xsd_path(window._schema_storage_dir)
    def _guarded_write(self, *a, **k):
        if self == target:
            raise OSError("permission denied")
        return real_write_text(self, *a, **k)
    monkeypatch.setattr(xsd_controller_module.Path, "write_text", _guarded_write)
    criticals = []
    monkeypatch.setattr(
        modals.QMessageBox, "critical",
        staticmethod(lambda *a, **k: criticals.append(a)),
    )
    window._xsd_ui.import_()

    assert criticals
    assert "Import Failed" in criticals[0][1]
    assert window._xsd_ui.dirty is True  # not cleared by a failed import
    assert target.read_text(encoding="utf-8") == _MINIMAL  # untouched
    window._xsd_ui.confirm_close = lambda: "discard"  # silence teardown close prompt


def test_save_write_oserror_shows_critical_and_keeps_dirty(window, monkeypatch):
    _seed(window)
    window._xsd_ui.open()
    window.center_stage.xsd_editor.setPlainText(_MINIMAL + "<!-- x -->")
    assert window._xsd_ui.dirty is True
    def _boom(self, *a, **k):
        raise OSError("read-only filesystem")
    monkeypatch.setattr(xsd_controller_module.Path, "write_text", _boom)
    criticals = []
    monkeypatch.setattr(
        modals.QMessageBox, "critical",
        staticmethod(lambda *a, **k: criticals.append(a)),
    )
    window._xsd_ui.save()
    assert criticals
    assert "Save Failed" in criticals[0][1]
    assert window._xsd_ui.dirty is True
    window._xsd_ui.confirm_close = lambda: "discard"  # silence teardown close prompt


def test_import_binary_file_shows_error(window, monkeypatch, tmp_path):
    """Importing a binary or non-UTF-8 file should show an error and preserve curated.xsd."""
    _seed(window)
    binary = tmp_path / "binary.xsd"
    binary.write_bytes(bytes([0xff, 0xfe, 0x00]))

    monkeypatch.setattr(
        modals.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(binary), "")),
    )

    criticals = []
    monkeypatch.setattr(
        modals.QMessageBox, "critical",
        staticmethod(lambda *a, **k: criticals.append(a)),
    )
    window._xsd_ui.import_()

    # Critical error should be shown
    assert criticals
    assert "Import Failed" in criticals[0][1]

    # Original file should be untouched
    path = curated_xsd_path(window._schema_storage_dir)
    assert path.read_text(encoding="utf-8") == _MINIMAL


def test_load_curated_schema_binary_file_returns_false_and_keeps_last_good(window):
    """A curated.xsd that is binary/non-UTF-8 must not crash
    XsdController.load_curated: it should audit-log the failure, return False, and
    keep whatever schema was last successfully loaded (spec §11)."""
    path = _seed(window)
    window._xsd_ui.load_curated()
    good_model = window.center_stage.xml_editor.schema_model()

    path.write_bytes(bytes([0xff, 0xfe, 0x00]))
    result = window._xsd_ui.load_curated()

    assert result is False
    assert window.center_stage.xml_editor.schema_model() is good_model
    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any("Curated XSD has XML errors" in t and "keeping last good schema" in t for t in texts)


def test_open_edit_xsd_binary_file_shows_status_and_does_not_open(window):
    """A binary/non-UTF-8 curated.xsd must not crash XsdController.open: it
    should show a status-bar message and leave the tab untouched instead of
    switching to it with garbage content."""
    path = _seed(window)
    path.write_bytes(bytes([0xff, 0xfe, 0x00]))

    window._xsd_ui.open()

    stage = window.center_stage
    assert stage.currentIndex() != stage.xsd_tab_index
    assert "Could not read curated.xsd" in window.statusBar().currentMessage()


def test_verify_xsd_binary_file_shows_status_and_no_verify_lines(window):
    """A binary/non-UTF-8 curated.xsd must not crash XsdController.verify: it should
    show a status-bar message and produce no VERIFY audit lines."""
    path = _seed(window)
    path.write_bytes(bytes([0xff, 0xfe, 0x00]))

    window._xsd_ui.verify()

    assert "Could not read curated.xsd" in window.statusBar().currentMessage()
    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert not any(t.startswith("[Schema] VERIFY") for t in texts)
