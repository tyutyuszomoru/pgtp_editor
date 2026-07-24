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

from pathlib import Path

from PySide6.QtCore import QStandardPaths

_MODEL_FILENAME = "schema_model.json"
_XSD_FILENAME = "schema.xsd"
_TEAM_REPO_DIRNAME = "team_schema_repo"


def _app_data_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


def schema_model_path(base_dir: Path | None = None) -> Path:
    return (base_dir or _app_data_dir()) / _MODEL_FILENAME


def schema_xsd_path(base_dir: Path | None = None) -> Path:
    return (base_dir or _app_data_dir()) / _XSD_FILENAME


def team_repo_dir(base_dir: Path | None = None) -> Path:
    """Local clone location of the team schema-sharing repo (a transport
    cache, not a source of truth — see CONSOLIDATED_SPEC §11)."""
    return (base_dir or _app_data_dir()) / _TEAM_REPO_DIRNAME
