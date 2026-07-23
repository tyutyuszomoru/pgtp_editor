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

"""Qt-free model-to-model semantic merge for team schema sharing.

Folds one learned schema Model into another: engine-owned fields merge
additively (mirroring Model.merge_element's semantics across whole models),
labeler-owned fields (labels / notes / kind / enum_mode) merge by union with
NEVER-SILENT conflict surfacing — where both sides disagree, the base value
is kept and a Conflict record is returned for the caller (MainWindow's
Merge Team Models dialog, or Fetch Team Master's audit report) to resolve.

instance_count / attr_seen_count are SUMMED so that "required" (seen count
== instance count) survives a merge only when the attribute was required on
BOTH sides.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from .model import ENUM_MAX_VALUES
from .types import combine_type

LABELER_DICT_FIELDS = ("labels", "notes")
LABELER_SCALAR_FIELDS = ("kind", "enum_mode")


@dataclass
class Conflict:
    path: str
    attr: str
    field: str          # "labels" | "notes" | "kind" | "enum_mode"
    value: str | None   # dict key for labels/notes; None for scalar fields
    base: str
    incoming: str


def merge_models(base, incoming):
    """Fold ``incoming`` into ``base`` in place; return the conflicts."""
    conflicts: list[Conflict] = []
    for path, inc_entry in incoming.paths.items():
        if path not in base.paths:
            base.paths[path] = copy.deepcopy(inc_entry)
            continue
        _merge_element_entry(path, base.paths[path], inc_entry, conflicts)
    return conflicts


def apply_resolution(model, conflict, use_incoming):
    """Apply one user decision for ``conflict`` to ``model`` (the merge
    base). ``use_incoming=False`` is a no-op — the base value was kept."""
    if not use_incoming:
        return
    entry = model.paths[conflict.path]["attributes"][conflict.attr]
    if conflict.field in LABELER_DICT_FIELDS:
        entry.setdefault(conflict.field, {})[conflict.value] = conflict.incoming
    else:
        entry[conflict.field] = conflict.incoming


def _merge_element_entry(path, base_entry, inc_entry, conflicts):
    base_entry["instance_count"] += inc_entry["instance_count"]
    base_entry["has_text"] = base_entry["has_text"] or inc_entry["has_text"]

    for tag, inc_child in inc_entry["children"].items():
        child = base_entry["children"].get(tag)
        if child is None:
            # Shallow copy is safe: child entries are flat dicts of bools only
            base_entry["children"][tag] = dict(inc_child)
            base_entry["order"].append(tag)
        else:
            child["ever_absent"] = child["ever_absent"] or inc_child["ever_absent"]
            child["ever_multiple"] = (
                child["ever_multiple"] or inc_child["ever_multiple"]
            )
    if not inc_entry["order_stable"]:
        base_entry["order_stable"] = False
    common = set(base_entry["order"]) & set(inc_entry["order"])
    if [t for t in base_entry["order"] if t in common] != [
        t for t in inc_entry["order"] if t in common
    ]:
        base_entry["order_stable"] = False

    for attr, inc_attr in inc_entry["attributes"].items():
        base_attr = base_entry["attributes"].get(attr)
        if base_attr is None:
            base_entry["attributes"][attr] = copy.deepcopy(inc_attr)
            continue
        _merge_attribute_entry(path, attr, base_attr, inc_attr, conflicts)


def _merge_attribute_entry(path, attr, base_attr, inc_attr, conflicts):
    base_attr["type"] = combine_type(base_attr["type"], inc_attr["type"])
    base_attr["attr_seen_count"] += inc_attr["attr_seen_count"]

    if inc_attr["overflowed"]:
        base_attr["overflowed"] = True
        base_attr["values"] = None
    elif not base_attr["overflowed"]:
        merged = list(base_attr["values"])
        for value in inc_attr["values"]:
            if value not in merged:
                merged.append(value)
        if len(merged) > ENUM_MAX_VALUES:
            base_attr["overflowed"] = True
            base_attr["values"] = None
        else:
            base_attr["values"] = merged

    for field in LABELER_DICT_FIELDS:
        inc_dict = inc_attr.get(field) or {}
        if not inc_dict:
            continue
        base_dict = base_attr.setdefault(field, {})
        for value, inc_text in inc_dict.items():
            base_text = base_dict.get(value)
            if base_text is None:
                base_dict[value] = inc_text
            elif base_text != inc_text:
                conflicts.append(
                    Conflict(path, attr, field, value, base_text, inc_text)
                )

    for field in LABELER_SCALAR_FIELDS:
        inc_val = inc_attr.get(field)
        if inc_val is None:
            continue
        base_val = base_attr.get(field)
        if base_val is None:
            base_attr[field] = inc_val
        elif base_val != inc_val:
            conflicts.append(Conflict(path, attr, field, None, base_val, inc_val))
