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

"""Tests for the mode-aware Edit-XSD tab: Schema ▸ Edit XSD (curated) vs
Schema ▸ Edit AutoXSD (learned), and mode-aware Save/Verify/Export/Import
(spec §11)."""
import pytest
from PySide6.QtCore import Qt

from tests.ui._menu_helpers import find_action, find_top_menu

from pgtp_editor.schema_learning.storage import curated_xsd_path, learned_xsd_path
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui import xsd_controller as xsd_controller_module
from pgtp_editor.ui import modals

_CURATED = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Root" type="Root_Type"/>
  <xs:complexType name="Root_Type">
    <xs:attribute name="cur" use="optional" type="xs:string"/>
  </xs:complexType>
</xs:schema>
"""

_LEARNED = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Root" type="Root_Type"/>
  <xs:complexType name="Root_Type">
    <xs:attribute name="lrn" use="optional" type="xs:string"/>
  </xs:complexType>
</xs:schema>
"""


@pytest.fixture
def window(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    win = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(win)
    return win


def _seed_curated(window, text=_CURATED):
    path = curated_xsd_path(window._schema_storage_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _seed_learned(window, text=_LEARNED):
    path = learned_xsd_path(window._schema_storage_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _silence_close(window):
    window._xsd_ui.confirm_close = lambda: "discard"


# -- mode + tab title -------------------------------------------------------

def test_edit_xsd_sets_curated_mode_and_title(window):
    _seed_curated(window)
    window._xsd_ui.open()
    stage = window.center_stage
    assert window._xsd_ui.mode == "curated"
    assert stage.currentIndex() == stage.xsd_tab_index
    assert stage.tabText(stage.xsd_tab_index) == "Edit XSD"
    assert stage.xsd_editor.toPlainText() == _CURATED


def test_edit_auto_xsd_sets_learned_mode_and_title(window):
    _seed_learned(window)
    window._xsd_ui.open_auto()
    stage = window.center_stage
    assert window._xsd_ui.mode == "learned"
    assert stage.currentIndex() == stage.xsd_tab_index
    assert stage.tabText(stage.xsd_tab_index) == "Edit AutoXSD"
    assert stage.xsd_editor.toPlainText() == _LEARNED


def test_edit_auto_xsd_absent_loads_skeleton_with_hint(window):
    # no learned.xsd on disk
    window._xsd_ui.open_auto()
    stage = window.center_stage
    assert window._xsd_ui.mode == "learned"
    text = stage.xsd_editor.toPlainText()
    assert text.startswith('<?xml version="1.0"')
    assert "<xs:schema" in text and "</xs:schema>" in text
    assert "No auto-learned schema yet" in window.statusBar().currentMessage()


def test_menu_edit_auto_xsd_wired(window):
    _seed_learned(window)
    menu = find_top_menu(window, "Schema")
    find_action(menu, "Edit AutoXSD").trigger()
    stage = window.center_stage
    assert window._xsd_ui.mode == "learned"
    assert stage.tabText(stage.xsd_tab_index) == "Edit AutoXSD"


def test_dirty_label_uses_learned_mode_base(window):
    _seed_learned(window)
    window._xsd_ui.open_auto()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_LEARNED + "<!-- x -->")
    assert window._xsd_ui.dirty is True
    assert stage.tabText(stage.xsd_tab_index) == "Edit AutoXSD *"
    _silence_close(window)


# -- same-mode re-open preserves edits --------------------------------------

def test_same_mode_reopen_preserves_unsaved_edits(window):
    _seed_learned(window)
    window._xsd_ui.open_auto()
    stage = window.center_stage
    dirty = _LEARNED + "<!-- unsaved -->"
    stage.xsd_editor.setPlainText(dirty)
    # re-open the SAME mode: edits must be kept (no reload from disk)
    window._xsd_ui.open_auto()
    assert stage.xsd_editor.toPlainText() == dirty
    assert window._xsd_ui.dirty is True
    _silence_close(window)


# -- mode switch with unsaved edits: cancel / discard / save ----------------

def test_mode_switch_cancel_keeps_current_mode_and_text(window):
    _seed_curated(window)
    _seed_learned(window)
    window._xsd_ui.open()
    stage = window.center_stage
    dirty = _CURATED + "<!-- unsaved -->"
    stage.xsd_editor.setPlainText(dirty)
    window._xsd_ui.confirm_close = lambda: "cancel"

    window._xsd_ui.open_auto()

    assert window._xsd_ui.mode == "curated"          # switch aborted
    assert stage.xsd_editor.toPlainText() == dirty
    assert window._xsd_ui.dirty is True
    _silence_close(window)


def test_mode_switch_discard_loads_other_mode(window):
    _seed_curated(window)
    _seed_learned(window)
    window._xsd_ui.open()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_CURATED + "<!-- unsaved -->")
    window._xsd_ui.confirm_close = lambda: "discard"

    window._xsd_ui.open_auto()

    assert window._xsd_ui.mode == "learned"
    assert stage.xsd_editor.toPlainText() == _LEARNED  # discarded, loaded learned
    assert window._xsd_ui.dirty is False


def test_mode_switch_save_writes_current_then_loads_other(window):
    curated_path = _seed_curated(window)
    _seed_learned(window)
    window._xsd_ui.open()
    stage = window.center_stage
    edited = _CURATED.replace('name="cur"', 'name="curEdited"')
    stage.xsd_editor.setPlainText(edited)
    window._xsd_ui.confirm_close = lambda: "save"

    window._xsd_ui.open_auto()

    # current (curated) mode saved to disk first...
    assert 'name="curEdited"' in curated_path.read_text(encoding="utf-8")
    # ...then the other (learned) mode loaded
    assert window._xsd_ui.mode == "learned"
    assert stage.xsd_editor.toPlainText() == _LEARNED
    assert window._xsd_ui.dirty is False


def test_mode_switch_save_failure_aborts_switch(window, monkeypatch):
    _seed_curated(window)
    _seed_learned(window)
    window._xsd_ui.open()
    stage = window.center_stage
    dirty = _CURATED + "<!-- unsaved -->"
    stage.xsd_editor.setPlainText(dirty)
    window._xsd_ui.confirm_close = lambda: "save"

    def _boom(self, *a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(xsd_controller_module.Path, "write_text", _boom)
    monkeypatch.setattr(
        modals.QMessageBox, "critical",
        staticmethod(lambda *a, **k: None),
    )

    window._xsd_ui.open_auto()

    # save failed -> dirty stayed true -> switch aborted, curated text kept
    assert window._xsd_ui.mode == "curated"
    assert window._xsd_ui.dirty is True
    assert stage.xsd_editor.toPlainText() == dirty
    _silence_close(window)


# -- mode-aware save --------------------------------------------------------

def test_save_learned_writes_learned_path_and_no_completion_feed(window):
    curated_path = _seed_curated(window)
    learned_path = learned_xsd_path(window._schema_storage_dir)
    window._xsd_ui.load_curated()
    curated_model = window.center_stage.xml_editor.schema_model()

    window._xsd_ui.open_auto()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_LEARNED)
    window._xsd_ui.save()

    assert window._xsd_ui.dirty is False
    assert learned_path.read_text(encoding="utf-8") == _LEARNED
    assert learned_path.name in window.statusBar().currentMessage()
    # learned save must NOT re-feed completion: curated model stays live,
    # and curated.xsd on disk is untouched
    assert window.center_stage.xml_editor.schema_model() is curated_model
    assert "lrn" not in curated_model.paths["Root"]["attributes"]
    assert curated_path.read_text(encoding="utf-8") == _CURATED


def test_save_curated_feeds_completion(window):
    _seed_curated(window)
    window._xsd_ui.open()
    stage = window.center_stage
    stage.xsd_editor.setPlainText(_CURATED.replace('name="cur"', 'name="cur2"'))
    window._xsd_ui.save()
    model = stage.xml_editor.schema_model()
    assert "cur2" in model.paths["Root"]["attributes"]


# -- mode-aware verify / export / import ------------------------------------

def test_verify_learned_targets_learned_file(window):
    _seed_learned(window, _LEARNED.replace(
        '<xs:attribute name="lrn" use="optional" type="xs:string"/>',
        '<xs:attribute name="lrn" use="optional" type="xs:string" label="wrong"/>',
    ))
    window._xsd_ui.open_auto()
    window._xsd_ui.verify()
    items = [window.audit_panel.item(i) for i in range(window.audit_panel.count())]
    verify = [i for i in items if "VERIFY line" in i.text()]
    assert verify
    # the mode tag rides along so a click re-opens the learned schema
    assert verify[0].data(Qt.ItemDataRole.UserRole + 2) == "learned"


def test_clicking_learned_verify_line_opens_learned_tab(window):
    _seed_curated(window)
    _seed_learned(window, _LEARNED.replace(
        '<xs:attribute name="lrn" use="optional" type="xs:string"/>',
        '<xs:attribute name="lrn" use="optional" type="xs:string" label="wrong"/>',
    ))
    window._xsd_ui.open_auto()
    window._xsd_ui.verify()
    items = [window.audit_panel.item(i) for i in range(window.audit_panel.count())]
    verify_item = next(i for i in items if "VERIFY line" in i.text())
    # navigate elsewhere first, then click
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)

    window._on_audit_item_clicked(verify_item)

    stage = window.center_stage
    assert stage.currentIndex() == stage.xsd_tab_index
    assert window._xsd_ui.mode == "learned"


def test_export_learned_defaults_to_learned_filename(window, monkeypatch, tmp_path):
    _seed_learned(window)
    window._xsd_ui.open_auto()
    captured = {}
    dest = tmp_path / "exported.xsd"

    def _fake_save(parent, title, default_name, filt):
        captured["default"] = default_name
        return (str(dest), "")
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName",
        staticmethod(_fake_save),
    )
    window._xsd_ui.export()
    assert captured["default"] == "learned.xsd"
    assert dest.read_text(encoding="utf-8") == _LEARNED


def test_import_learned_backs_up_and_no_completion_feed(window, monkeypatch, tmp_path):
    _seed_curated(window)
    learned_path = _seed_learned(window)
    window._xsd_ui.load_curated()
    curated_model = window.center_stage.xml_editor.schema_model()
    window._xsd_ui.open_auto()

    incoming = tmp_path / "incoming.xsd"
    incoming.write_text(_LEARNED.replace('name="lrn"', 'name="lrn2"'), encoding="utf-8")
    monkeypatch.setattr(
        modals.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(incoming), "")),
    )
    window._xsd_ui.import_()

    assert 'name="lrn2"' in learned_path.read_text(encoding="utf-8")
    assert (learned_path.parent / "learned.xsd.bak").read_text(encoding="utf-8") == _LEARNED
    # learned import must not re-feed completion
    assert window.center_stage.xml_editor.schema_model() is curated_model
    assert "lrn2" not in curated_model.paths["Root"]["attributes"]
    # FQ-028: `[Schema]` import narration is journalled, not listed.
    audit = window.activity_panel.row_texts()
    assert any("Imported Edit AutoXSD" in t for t in audit)
