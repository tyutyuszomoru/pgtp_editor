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


def enum_hint(model, tag_chain, attr):
    """One-line hover hint for a *setting* attribute at ``tag_chain``.

    Returns e.g. ``"editFormMode — 1 = modal · 2 = new page · 3 = inline"``,
    or ``None`` when the attribute isn't a labeled/labelable setting at that
    path. A hint is produced only when ``attribute_kind == "setting"`` AND the
    entry has either a non-empty ``labels`` dict or is still an enum candidate
    (i.e. there is something to show). For each value, shows ``value = label``
    when a label exists, else the bare ``value``; values are sorted. When
    ``values`` is absent/None (e.g. overflowed) but labels exist, the sorted
    ``labels`` keys are shown instead.
    """
    entry = (
        model.paths.get(tag_chain, {}).get("attributes", {}).get(attr)
    )
    if entry is None:
        return None
    if attribute_kind(entry) != "setting":
        return None

    labels = entry.get("labels") or {}
    if not labels and not is_enum_candidate(entry):
        return None

    values = entry.get("values")
    keys = values if values else sorted(labels)
    parts = []
    for value in sorted(keys):
        label = labels.get(value)
        parts.append(f"{value} = {label}" if label else f"{value}")
    return f"{attr} — " + " · ".join(parts)
