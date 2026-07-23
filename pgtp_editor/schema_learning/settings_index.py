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

"""Pure, Qt-free classification/query helpers over the learned schema
model's per-attribute entries.

An attribute entry is the dict stored at
``Model.paths[path]["attributes"][name]`` — shaped
``{type, values, overflowed, attr_seen_count, labels, [kind]}``. The
``kind`` key is written ONLY by the labeler (see the annotation popover
``pgtp_editor.ui.annotate_popover``, wired via MainWindow); attributes
created by the Schema Learning Engine have no ``kind`` key and are treated
as unclassified. Readers therefore use ``entry.get("kind")``.
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


def derived_bitflag_label(value, labels):
    """Derived display label for a bit-flag composite ``value``.

    ``labels`` maps value-strings to labels; only the atomic power-of-two
    bits need labels (1, 2, 4, 8, ...). The composite's label is the '+'-join
    of its set bits' labels in ascending bit order (5 -> "A+C" from 1="A",
    4="C"). Returns None when ``value`` is not a positive integer or any set
    bit lacks a label — callers then fall back to showing the bare value.
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    parts = []
    bit = 1
    remaining = number
    while remaining:
        if remaining & 1:
            label = labels.get(str(bit))
            if label is None:
                return None
            parts.append(label)
        remaining >>= 1
        bit <<= 1
    return "+".join(parts)


def effective_labels(entry):
    """The labels to DISPLAY for an attribute entry: a copy of the explicit
    ``labels`` plus, when ``enum_mode == "bitflags"``, derived composite
    labels for every known value (explicit labels always win). The value
    universe is the union of engine-observed ``values`` and label keys, so
    derivation works even after enum overflow (``values`` is None)."""
    labels = entry.get("labels") or {}
    if entry.get("enum_mode") != "bitflags":
        return dict(labels)
    universe = set(entry.get("values") or []) | set(labels)
    result = {}
    for value in universe:
        explicit = labels.get(value)
        if explicit is not None:
            result[value] = explicit
            continue
        derived = derived_bitflag_label(value, labels)
        if derived is not None:
            result[value] = derived
    return result


def value_note(entry, value):
    """The labeler's free-text note for ``value`` (structural consequences,
    e.g. "enables the <Watermark> child tag"), or None."""
    return (entry.get("notes") or {}).get(value)


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


def known_attributes(model, tag_chain, present_attrs) -> list[str]:
    """Sorted names of every attribute the schema records at ``tag_chain`` that
    the element does not already carry.

    Unlike ``unused_setting_attributes`` this is NOT filtered by kind — the full
    set the model has observed for the element is offered (the broad list the
    XSD shows). ``present_attrs`` is a collection of names already on the tag.
    An unknown ``tag_chain`` yields ``[]``.
    """
    attributes = model.paths.get(tag_chain, {}).get("attributes", {})
    present = set(present_attrs)
    return sorted(name for name in attributes if name not in present)


def known_values(model, tag_chain, attr) -> list[tuple[str, str | None]]:
    """Sorted ``(value, label)`` pairs for an attribute's known value set at
    ``tag_chain`` — the same values ``enum_hint`` renders. ``label`` is
    ``labels.get(value)`` or ``None``.

    Returns ``[]`` when the attribute is unknown at the path, its entry is
    ``overflowed``, or it has no ``values`` (nothing reliable to offer). Not
    filtered by kind, so any enumerated attribute chains into the value picker.
    """
    entry = model.paths.get(tag_chain, {}).get("attributes", {}).get(attr)
    if entry is None or entry.get("overflowed") or not entry.get("values"):
        return []
    labels = entry.get("labels") or {}
    return [(value, labels.get(value)) for value in sorted(entry["values"])]


def unused_setting_attributes(model, tag_chain, present_attrs) -> list[str]:
    """Sorted names of *setting* attributes known at ``tag_chain`` that the
    element does not already carry.

    ``present_attrs`` is a collection of attribute names already on the
    element. Returns the sorted list of attribute names whose
    ``attribute_kind == "setting"`` and whose name is not in
    ``present_attrs``. An unknown ``tag_chain`` yields ``[]``.
    """
    attributes = model.paths.get(tag_chain, {}).get("attributes", {})
    present = set(present_attrs)
    return sorted(
        name
        for name, entry in attributes.items()
        if attribute_kind(entry) == "setting" and name not in present
    )
