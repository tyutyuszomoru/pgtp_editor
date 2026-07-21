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

"""Pure (Qt-free) load-or-generate helpers backing the Phase 1 schema viewers.

Kept Qt-free so the load/generate logic is unit-tested without a window: the
menu handlers call these to obtain the text, then hand it to a
``SchemaViewerWindow``. Each helper returns ``None`` when the underlying schema
artifact does not exist yet, which the caller renders as a friendly empty
message instead of opening a window.
"""
from __future__ import annotations

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import schema_model_path, schema_xsd_path
from pgtp_editor.schema_learning.xsd_gen import generate_xsd


def open_xsd_text(storage_dir=None) -> str | None:
    """Return the XSD text for the learned schema, or ``None`` if no schema
    exists yet. Prefers a stored ``schema.xsd`` verbatim; otherwise generates
    the XSD on the fly from the stored model JSON."""
    xsd_path = schema_xsd_path(storage_dir)
    if xsd_path.exists():
        return xsd_path.read_text(encoding="utf-8")
    model_path = schema_model_path(storage_dir)
    if model_path.exists():
        return generate_xsd(Model.load(model_path))
    return None


def open_labels_text(storage_dir=None) -> str | None:
    """Return the stored schema model JSON text (pretty as saved), or ``None``
    if no model exists yet."""
    model_path = schema_model_path(storage_dir)
    if model_path.exists():
        return model_path.read_text(encoding="utf-8")
    return None
