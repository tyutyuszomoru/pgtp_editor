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

"""Pure, Qt-free query helpers over the curated-XSD schema model's
per-attribute entries (spec §11, the curated-XSD pivot).

An attribute entry is the dict stored at
``Model.paths[path]["attributes"][name]``, hand-authored in curated.xsd and
loaded verbatim — shaped
``{type, values, overflowed, attr_seen_count, labels, use, [hint], [sums]}``.
There is no ``kind`` classification any more: every attribute the curated
schema records at a path is completion-worthy. Two dialect markers replace
it:

- ``hint`` — a free-form string attribute (e.g. a file path). It has no
  value list; ``known_values`` returns ``[]`` and ``enum_hint`` shows the
  hint text directly.
- ``sums`` — a bit-flag-style attribute whose enumerated values are atomic
  powers that combine additively. The atomic, labeled, positive-integer
  values in ``values`` are combined into every non-empty subset sum, each
  labeled with the '+'-join of its atoms' labels; explicit ``labels`` rows
  (e.g. a hand-written composite) always win over a derived one.

Attributes with neither marker are plain enumerations: ``values`` lists the
known values and ``labels`` maps some/all of them to display labels.
"""
from __future__ import annotations


# Above this many labeled atomic values, the 2^n subset-sum derivation
# becomes a combinatorial blow-up (2^17 = 131072+ rows). Derivation is
# skipped entirely and only explicit ``labels`` rows are returned; see
# derived_sums_labels below and the matching xsd_verify rule that flags
# a ``sums`` attribute exceeding this at authoring time.
SUMS_MAX_ATOMS = 16


def derived_sums_labels(entry):
    """All combination labels for a sums attribute. Atoms = the labeled,
    positive-integer enumeration values; every non-empty subset's sum gets a
    '+'-joined label in ascending atomic order. On duplicate sums the first
    (smallest-atoms) subset wins; explicit enumeration labels overlay LAST,
    so a hand-written composite row always wins (spec §11).

    If the number of labeled atoms exceeds SUMS_MAX_ATOMS, derivation is
    skipped (2^n subsets would be combinatorially explosive) and only the
    explicit ``labels`` are returned."""
    labels = entry.get("labels") or {}
    atoms = []
    for value in entry.get("values") or []:
        label = labels.get(value)
        if label is None:
            continue
        try:
            number = int(value)
        except ValueError:
            continue
        if number > 0:
            atoms.append((number, label))
    if len(atoms) > SUMS_MAX_ATOMS:
        return dict(labels)
    atoms.sort()
    result = {}
    for mask in range(1, 1 << len(atoms)):
        total = 0
        parts = []
        for index, (number, label) in enumerate(atoms):
            if mask & (1 << index):
                total += number
                parts.append(label)
        result.setdefault(str(total), "+".join(parts))
    result.update(labels)
    return result


def effective_labels(entry):
    """The labels to display for an attribute entry: explicit labels, plus
    derived combination labels when the attribute is marked sums."""
    if entry.get("sums"):
        return derived_sums_labels(entry)
    return dict(entry.get("labels") or {})


def _value_sort_key(value):
    try:
        return (0, int(value), value)
    except ValueError:
        return (1, 0, value)


def known_values(model, tag_chain, attr):
    """Sorted ``(value, label)`` pairs for the value-completion popup.
    ``[]`` for an unknown attribute or a hint attribute (free-form — no
    value list, spec §11). For sums attributes the universe is every derived
    combination (2^n − 1 rows)."""
    entry = model.paths.get(tag_chain, {}).get("attributes", {}).get(attr)
    if entry is None or entry.get("hint"):
        return []
    labels = effective_labels(entry)
    universe = set(labels) if entry.get("sums") else set(entry.get("values") or [])
    if not universe:
        return []
    return [(v, labels.get(v)) for v in sorted(universe, key=_value_sort_key)]


def enum_hint(model, tag_chain, attr):
    """One-line hover hint: the hint text for free-form attributes, else the
    value = label list (derived sums labels included)."""
    entry = model.paths.get(tag_chain, {}).get("attributes", {}).get(attr)
    if entry is None:
        return None
    hint = entry.get("hint")
    if hint:
        return f"{attr} — {hint}"
    pairs = known_values(model, tag_chain, attr)
    if not pairs:
        return None
    parts = [f"{v} = {l}" if l else f"{v}" for v, l in pairs]
    return f"{attr} — " + " · ".join(parts)


def value_label(model, tag_chain, attr, value):
    """The display label for one concrete value, or None (Properties panel)."""
    entry = model.paths.get(tag_chain, {}).get("attributes", {}).get(attr)
    if entry is None:
        return None
    return effective_labels(entry).get(value)


def known_attributes(model, tag_chain, present_attrs) -> list[str]:
    """Sorted attribute names the curated schema knows at ``tag_chain`` that
    the element does not already carry. An attribute is completion-worthy iff
    it exists in curated.xsd — there is no kind filter (spec §11)."""
    attributes = model.paths.get(tag_chain, {}).get("attributes", {})
    present = set(present_attrs)
    return sorted(name for name in attributes if name not in present)


def unused_setting_attributes(model, tag_chain, present_attrs) -> list[str]:
    """Alias of known_attributes, kept for the Add-attribute submenu call
    site (the old kind filter is gone with the curated-XSD pivot)."""
    return known_attributes(model, tag_chain, present_attrs)
