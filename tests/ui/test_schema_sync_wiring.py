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

"""Wiring tests for MainWindow's Publish / Fetch Team Master / Merge Team
Models actions (Task 13). Uses MainWindow(settings=<temp ini>,
schema_storage_dir=tmp_path) so nothing touches the real user registry or
the real per-user schema storage location. `run_async` is monkeypatched to
a synchronous stand-in and every `sync` call is monkeypatched -- never any
real git/network in these tests."""
import pytest
from PySide6.QtCore import QSettings

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import schema_model_path
from pgtp_editor.schema_learning.sync import SyncConfig, SyncError
from pgtp_editor.ui import main_window as main_window_module
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.team_sync_dialog import SYNC_REPO_URL_KEY


def _ini_settings(tmp_path, name="s.ini"):
    return QSettings(str(tmp_path / name), QSettings.Format.IniFormat)


@pytest.fixture
def window(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    storage_dir = tmp_path / "storage"
    win = MainWindow(settings=settings, schema_storage_dir=storage_dir)
    qtbot.addWidget(win)
    return win


@pytest.fixture(autouse=True)
def synchronous_run_async(monkeypatch):
    def fake_run_async(fn, on_result, on_error=None, pool=None):
        try:
            value = fn()
        except Exception as exc:  # mirror the real seam's catch-all
            if on_error is not None:
                on_error(exc)
            return None
        on_result(value)
        return None

    monkeypatch.setattr(main_window_module, "run_async", fake_run_async)


def _audit_lines(window):
    return [window.audit_panel.item(i).text()
            for i in range(window.audit_panel.count())]


def test_publish_unconfigured_shows_status_only(window):
    window._publish_my_annotations()
    assert not any("[Schema] Publish" in line for line in _audit_lines(window))


def test_publish_reports_success(window, monkeypatch):
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")
    model_path = schema_model_path(window._schema_storage_dir)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    Model().save(model_path)
    monkeypatch.setattr(
        main_window_module.sync, "publish_model",
        lambda config, path, username=None: "models/alice.json",
    )
    window._publish_my_annotations()
    assert "[Schema] Published annotations as models/alice.json" in _audit_lines(window)


def test_publish_failure_reports_audit_line(window, monkeypatch):
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")
    model_path = schema_model_path(window._schema_storage_dir)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    Model().save(model_path)
    def boom(config, path, username=None):
        raise SyncError("no network")
    monkeypatch.setattr(main_window_module.sync, "publish_model", boom)
    window._publish_my_annotations()
    assert any("[Schema] Sync failed: no network" in line
               for line in _audit_lines(window))


def test_fetch_master_merges_into_local_model(window, monkeypatch, tmp_path):
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")
    remote = Model()
    remote.paths = {"Root": {
        "attributes": {"a": {"type": "integer", "values": ["1"],
                             "overflowed": False, "attr_seen_count": 1,
                             "labels": {"1": "A"}}},
        "children": {}, "instance_count": 1, "order": [],
        "order_stable": True, "has_text": False,
    }}
    master_file = tmp_path / "master.json"
    remote.save(master_file)
    monkeypatch.setattr(
        main_window_module.sync, "fetch_master", lambda config: master_file
    )
    window._fetch_team_master()
    local = Model.load(schema_model_path(window._schema_storage_dir))
    assert local.paths["Root"]["attributes"]["a"]["labels"] == {"1": "A"}
    assert any("Fetched team master" in line for line in _audit_lines(window))
