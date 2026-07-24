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
from PySide6.QtWidgets import QDialog

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import schema_model_path
from pgtp_editor.schema_learning.sync import SyncConfig, SyncError
from pgtp_editor.ui import main_window as main_window_module
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.merge_conflicts_dialog import MergeConflictsDialog
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


def _labeled_model(label_text):
    model = Model()
    model.paths = {"Root": {
        "attributes": {"a": {"type": "integer", "values": ["1"],
                             "overflowed": False, "attr_seen_count": 1,
                             "labels": {"1": label_text}}},
        "children": {}, "instance_count": 1, "order": [],
        "order_stable": True, "has_text": False,
    }}
    return model


def test_publish_without_local_model_shows_status_and_skips_sync(window, monkeypatch):
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")
    calls = []
    monkeypatch.setattr(
        main_window_module.sync, "publish_model",
        lambda *args, **kwargs: calls.append(args),
    )
    window._publish_my_annotations()
    assert calls == []
    assert "No schema learned yet" in window.statusBar().currentMessage()
    assert not any("[Schema]" in line for line in _audit_lines(window))


def test_fetch_conflict_keeps_local_label_and_reports(window, monkeypatch, tmp_path):
    """Spec §11: Fetch merges the master into the LOCAL model; on a label
    conflict the local value wins and the conflict is surfaced (never
    silent) as a CONFLICT audit line."""
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")
    local_path = schema_model_path(window._schema_storage_dir)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    _labeled_model("local label").save(local_path)
    master_file = tmp_path / "master.json"
    _labeled_model("master label").save(master_file)
    monkeypatch.setattr(
        main_window_module.sync, "fetch_master", lambda config: master_file
    )
    window._fetch_team_master()
    saved = Model.load(local_path)
    assert saved.paths["Root"]["attributes"]["a"]["labels"] == {"1": "local label"}
    lines = _audit_lines(window)
    assert any("Fetched team master" in line for line in lines)
    assert any(
        "CONFLICT (kept local)" in line
        and 'local="local label"' in line
        and 'master="master label"' in line
        for line in lines
    )


def test_fetch_failure_leaves_local_model_untouched(window, monkeypatch):
    """Spec §11 failure behavior: no network / bad key leaves the local
    model untouched and reports via a [Schema] audit line."""
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")
    local_path = schema_model_path(window._schema_storage_dir)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    _labeled_model("precious").save(local_path)
    before = local_path.read_bytes()

    def boom(config):
        raise SyncError("no network")

    monkeypatch.setattr(main_window_module.sync, "fetch_master", boom)
    window._fetch_team_master()
    assert local_path.read_bytes() == before
    lines = _audit_lines(window)
    assert any("[Schema] Sync failed: no network" in line for line in lines)
    assert not any("Fetched team master" in line for line in lines)


def test_fetch_without_master_yet_reports_sync_failure(window, monkeypatch):
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")
    monkeypatch.setattr(
        main_window_module.sync, "fetch_master", lambda config: None
    )
    window._fetch_team_master()
    assert any(
        "no master.json in the team repo yet" in line
        for line in _audit_lines(window)
    )


def test_merge_accept_applies_resolution_and_pushes(window, monkeypatch, tmp_path):
    """Accepting the conflict dialog with 'use incoming' selected must fold
    the incoming label into the pushed master."""
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")
    alice_path = tmp_path / "alice.json"
    bob_path = tmp_path / "bob.json"
    _labeled_model("Foo").save(alice_path)
    _labeled_model("Bar").save(bob_path)
    monkeypatch.setattr(
        main_window_module.sync, "team_model_paths",
        lambda config: [alice_path, bob_path],
    )

    def fake_exec(self):
        self.choice_combo(0).setCurrentIndex(1)  # take bob's "Bar"
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MergeConflictsDialog, "exec", fake_exec)
    pushed = []

    def fake_push(config, master):
        pushed.append(master)
        return True

    monkeypatch.setattr(main_window_module.sync, "push_master", fake_push)
    window._merge_team_models()
    assert len(pushed) == 1
    assert pushed[0].paths["Root"]["attributes"]["a"]["labels"]["1"] == "Bar"
    lines = _audit_lines(window)
    assert "[Schema] Merged team models into master and pushed." in lines
    assert any("Fetch Team Master" in line for line in lines)


def test_merge_with_no_user_models_reports_and_skips_push(window, monkeypatch):
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")
    monkeypatch.setattr(
        main_window_module.sync, "team_model_paths", lambda config: []
    )
    pushed = []
    monkeypatch.setattr(
        main_window_module.sync, "push_master",
        lambda config, master: pushed.append(master),
    )
    window._merge_team_models()
    assert pushed == []
    assert "[Schema] Merge: no models/*.json in the team repo yet." in _audit_lines(window)


def test_merge_conflict_shows_each_side_source_not_bare_master(window, monkeypatch, tmp_path):
    """Regression for the finding: master is empty, alice's label for value
    "1" is adopted with no conflict, then bob disagrees with alice -- the
    conflict dialog must attribute the base side to "alice", not "master",
    since alice's label (not master's) is what bob actually collides with."""
    window._settings.setValue(SYNC_REPO_URL_KEY, "x:/repo.git")

    def _labeled_model(label_text):
        model = Model()
        model.paths = {"Root": {
            "attributes": {"a": {"type": "integer", "values": ["1"],
                                 "overflowed": False, "attr_seen_count": 1,
                                 "labels": {"1": label_text}}},
            "children": {}, "instance_count": 1, "order": [],
            "order_stable": True, "has_text": False,
        }}
        return model

    alice_path = tmp_path / "alice.json"
    bob_path = tmp_path / "bob.json"
    _labeled_model("Foo").save(alice_path)
    _labeled_model("Bar").save(bob_path)

    monkeypatch.setattr(
        main_window_module.sync, "team_model_paths",
        lambda config: [alice_path, bob_path],
    )

    captured_dialogs = []

    def fake_exec(self):
        captured_dialogs.append(self)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(MergeConflictsDialog, "exec", fake_exec)

    push_calls = []
    monkeypatch.setattr(
        main_window_module.sync, "push_master",
        lambda config, master: push_calls.append(master),
    )

    window._merge_team_models()

    assert len(captured_dialogs) == 1
    combo = captured_dialogs[0].choice_combo(0)
    assert combo.itemText(0) == "alice: Foo"
    assert combo.itemText(1) == "bob: Bar"
    assert not push_calls
    assert "[Schema] Merge aborted — nothing was pushed." in _audit_lines(window)
