"""Pure, Qt-free classification/query helpers over the learned schema
model's per-attribute entries.

An attribute entry is the dict stored at
``Model.paths[path]["attributes"][name]`` — shaped
``{type, values, overflowed, attr_seen_count, labels, [kind]}``. The
``kind`` key is written ONLY by the labeler (see
``pgtp_editor.ui.annotate_schema_values_dialog``); attributes created by
the Schema Learning Engine have no ``kind`` key and are treated as
unclassified. Readers therefore use ``entry.get("kind")``.
"""
from __future__ import annotations


def is_enum_candidate(entry) -> bool:
    """True when the attribute is a labelable enum: non-overflowed, has a
    non-empty ``values`` list, and is not boolean-typed."""
    return (
        not entry["overflowed"]
        and bool(entry.get("values"))
        and entry["type"] != "boolean"
    )


def attribute_kind(entry) -> str:
    """Returns one of ``"unclassified"`` / ``"setting"`` / ``"content"``.
    Missing or ``None`` ``kind`` maps to ``"unclassified"``."""
    return entry.get("kind") or "unclassified"
