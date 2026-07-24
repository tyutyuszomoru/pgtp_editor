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

"""Team schema-sharing configuration: repo URL + deploy-key path, persisted
in the injectable QSettings (same seam as db/config.py). load_sync_config
is the single translation point from settings to a SyncConfig."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
)

from pgtp_editor.schema_learning.storage import team_repo_dir
from pgtp_editor.schema_learning.sync import SyncConfig

SYNC_REPO_URL_KEY = "schema_sync/repo_url"
SYNC_KEY_PATH_KEY = "schema_sync/key_path"


def load_sync_config(settings, base_dir=None):
    """SyncConfig from QSettings, or None when no repo URL is configured."""
    repo_url = (settings.value(SYNC_REPO_URL_KEY, "", type=str) or "").strip()
    if not repo_url:
        return None
    key_path = (settings.value(SYNC_KEY_PATH_KEY, "", type=str) or "").strip() or None
    return SyncConfig(
        repo_url=repo_url, clone_dir=team_repo_dir(base_dir), key_path=key_path
    )


class TeamSyncSettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Team Sync Settings")
        self._settings = settings
        self.repo_url_edit = QLineEdit(settings.value(SYNC_REPO_URL_KEY, "", type=str) or "")
        self.repo_url_edit.setPlaceholderText("git@host:team/pgtp-schema.git")
        self.key_path_edit = QLineEdit(settings.value(SYNC_KEY_PATH_KEY, "", type=str) or "")
        self.key_path_edit.setPlaceholderText(
            "Path to the deploy SSH key (leave empty for local/HTTPS remotes)"
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QFormLayout(self)
        layout.addRow("Repository URL:", self.repo_url_edit)
        layout.addRow("SSH key path:", self.key_path_edit)
        layout.addRow(buttons)

    def accept(self):
        self._settings.setValue(SYNC_REPO_URL_KEY, self.repo_url_edit.text().strip())
        self._settings.setValue(SYNC_KEY_PATH_KEY, self.key_path_edit.text().strip())
        super().accept()
