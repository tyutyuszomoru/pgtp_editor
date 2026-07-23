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

from PySide6.QtCore import QSettings

from pgtp_editor.ui.team_sync_dialog import (
    SYNC_KEY_PATH_KEY,
    SYNC_REPO_URL_KEY,
    TeamSyncSettingsDialog,
    load_sync_config,
)


def _settings(tmp_path):
    return QSettings(str(tmp_path / "test.ini"), QSettings.Format.IniFormat)


def test_load_sync_config_none_when_unconfigured(tmp_path):
    assert load_sync_config(_settings(tmp_path), tmp_path) is None


def test_load_sync_config_builds_config(tmp_path):
    settings = _settings(tmp_path)
    settings.setValue(SYNC_REPO_URL_KEY, "git@host:team/schema.git")
    settings.setValue(SYNC_KEY_PATH_KEY, "C:/keys/deploy.pem")
    config = load_sync_config(settings, tmp_path)
    assert config.repo_url == "git@host:team/schema.git"
    assert config.key_path == "C:/keys/deploy.pem"
    assert config.clone_dir == tmp_path / "team_schema_repo"


def test_dialog_persists_on_accept(tmp_path, qtbot):
    settings = _settings(tmp_path)
    dialog = TeamSyncSettingsDialog(settings)
    qtbot.addWidget(dialog)
    dialog.repo_url_edit.setText("git@host:team/schema.git")
    dialog.key_path_edit.setText("k.pem")
    dialog.accept()
    assert settings.value(SYNC_REPO_URL_KEY) == "git@host:team/schema.git"
    assert settings.value(SYNC_KEY_PATH_KEY) == "k.pem"
