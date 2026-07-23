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

"""Tests for the AnnotatePopover wiring on MainWindow — the Schema menu's
"Annotate Value at Cursor" / "Next Unlabeled Value" entry points and
MainWindow._apply_annotation, which persists the labeler-owned model fields
(labels / notes / kind / enum_mode) and regenerates the XSD.

Uses MainWindow(settings=<temp ini>, schema_storage_dir=tmp_path) so nothing
touches the real user registry or the real per-user schema storage location.
"""
import pytest
from PySide6.QtCore import QSettings

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import schema_model_path, schema_xsd_path
from pgtp_editor.ui.main_window import MainWindow
from tests.ui._menu_helpers import action_labels, find_top_menu


def _ini_settings(tmp_path, name="s.ini"):
    return QSettings(str(tmp_path / name), QSettings.Format.IniFormat)


@pytest.fixture
def window(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    storage_dir = tmp_path / "storage"
    win = MainWindow(settings=settings, schema_storage_dir=storage_dir)
    qtbot.addWidget(win)
    return win


def _seed_model(window):
    model = Model()
    model.paths = {
        "Root": {
            "attributes": {
                "mode": {
                    "type": "integer",
                    "values": ["4"],
                    "overflowed": False,
                    "attr_seen_count": 1,
                    "labels": {},
                }
            },
            "children": {},
            "instance_count": 1,
            "order": [],
            "order_stable": True,
            "has_text": False,
        }
    }
    window.center_stage.xml_editor.set_schema_model(model)
    return model


def test_apply_annotation_persists_all_fields(window):
    _seed_model(window)
    window._apply_annotation("Root", "mode", "4", {
        "label": "pdf",
        "note": "enables <Watermark>",
        "kind": "setting",
        "bitflags": True,
    })
    saved = Model.load(schema_model_path(window._schema_storage_dir))
    entry = saved.paths["Root"]["attributes"]["mode"]
    assert entry["labels"] == {"4": "pdf"}
    assert entry["notes"] == {"4": "enables <Watermark>"}
    assert entry["kind"] == "setting"
    assert entry["enum_mode"] == "bitflags"
    xsd = schema_xsd_path(window._schema_storage_dir).read_text(encoding="utf-8")
    assert "pdf" in xsd
    items = [window.audit_panel.item(i).text()
             for i in range(window.audit_panel.count())]
    assert any(line.startswith("[Schema] LABELED:") for line in items)


def test_apply_annotation_empty_strings_remove_fields(window):
    model = _seed_model(window)
    entry = model.paths["Root"]["attributes"]["mode"]
    entry["labels"]["4"] = "pdf"
    entry["notes"] = {"4": "x"}
    entry["kind"] = "setting"
    entry["enum_mode"] = "bitflags"
    window._apply_annotation("Root", "mode", "4", {
        "label": "", "note": "", "kind": "unclassified", "bitflags": False,
    })
    saved = Model.load(schema_model_path(window._schema_storage_dir))
    entry = saved.paths["Root"]["attributes"]["mode"]
    assert entry["labels"] == {}
    assert "notes" not in entry
    assert "kind" not in entry
    assert "enum_mode" not in entry


def test_schema_menu_has_new_actions(window):
    # find_top_menu (findChildren-based) rather than
    # `action.menu() for action in menuBar().actions()`: the latter's QMenu
    # is only reachable through a just-created QAction wrapper, so an
    # incidental gc pass between statements can free the C++ QMenu out from
    # under it (reproducible even on a bare QMainWindow) -- this codebase's
    # own menu tests all use find_top_menu for that reason.
    schema_menu = find_top_menu(window, "Schema")
    assert schema_menu is not None
    texts = [t for t in action_labels(schema_menu) if t and t != "―"]
    assert "Annotate Value at Cursor" in texts
    assert "Next Unlabeled Value" in texts
    assert "Annotate Schema Values..." not in texts
