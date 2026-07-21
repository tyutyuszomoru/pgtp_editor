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

# pgtp_editor/db/config.py
"""Connection parameters: seeded from the project XML, persisted in QSettings.

`ConnectionParams` is a simple frozen dataclass (port kept as a string for the
line edit's convenience). The password is NEVER taken from the XML — it is
stored obfuscated there — it comes only from saved settings or the user.

QSettings is the injectable `self._settings` from MainWindow; tests pass a
temp-file `QSettings(ini)` so nothing touches the real user registry.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings

_GROUP = "db"
_FIELDS = ("host", "port", "database", "user", "password")


@dataclass(frozen=True)
class ConnectionParams:
    host: str = ""
    port: str = ""
    database: str = ""
    user: str = ""
    password: str = ""


def connection_from_tree(tree) -> ConnectionParams | None:
    """Read the first ``<ConnectionOptions>`` element from the project tree.

    Maps ``host``/``port``/``database`` directly and ``login`` → ``user``. The
    password is always blank (the XML stores it obfuscated; we never use it).
    Returns None when there is no tree or no such element.
    """
    if tree is None:
        return None
    try:
        root = tree.getroot()
    except AttributeError:
        return None
    if root is None:
        return None
    element = next(iter(root.iter("ConnectionOptions")), None)
    if element is None:
        return None
    return ConnectionParams(
        host=element.get("host", ""),
        port=element.get("port", ""),
        database=element.get("database", ""),
        user=element.get("login", ""),
        password="",
    )


def load_connection(settings: QSettings) -> ConnectionParams | None:
    """Return the saved connection, or None if none has been stored (no host)."""
    settings.beginGroup(_GROUP)
    try:
        values = {name: settings.value(name, "", type=str) for name in _FIELDS}
    finally:
        settings.endGroup()
    if not values["host"]:
        return None
    return ConnectionParams(**values)


def save_connection(settings: QSettings, params: ConnectionParams) -> None:
    """Persist every field (including the password, in plain text) under ``db/``."""
    settings.beginGroup(_GROUP)
    try:
        for name in _FIELDS:
            settings.setValue(name, getattr(params, name))
    finally:
        settings.endGroup()
    settings.sync()


def seed_params(tree, settings: QSettings) -> ConnectionParams:
    """Build the params to pre-fill the Connection Setup dialog.

    Saved settings take precedence: once the user has saved a connection, those
    values win (e.g. a host corrected from ``localhost`` to ``127.0.0.1`` sticks
    across reopens and is what the checks use). Only fields with no saved value
    fall back to the project's ``<ConnectionOptions>``, then blank. The password
    comes only from saved settings (else blank). Tolerates ``tree=None``.
    """
    saved = load_connection(settings)
    from_tree = connection_from_tree(tree)

    def pick(name: str) -> str:
        if saved is not None and getattr(saved, name):
            return getattr(saved, name)
        if from_tree is not None and getattr(from_tree, name):
            return getattr(from_tree, name)
        return ""

    return ConnectionParams(
        host=pick("host"),
        port=pick("port"),
        database=pick("database"),
        user=pick("user"),
        password=saved.password if saved is not None else "",
    )
