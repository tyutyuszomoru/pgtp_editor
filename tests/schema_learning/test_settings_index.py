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

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.settings_index import (
    derived_sums_labels,
    effective_labels,
    enum_hint,
    known_attributes,
    known_values,
    unused_setting_attributes,
    value_label,
)


def _entry(values, labels=None, **extra):
    entry = {
        "type": "integer",
        "values": values,
        "overflowed": False,
        "attr_seen_count": 1,
        "labels": labels or {},
        "use": "optional",
    }
    entry.update(extra)
    return entry


def _model(attrs, chain="Root"):
    model = Model()
    model.paths = {chain: {
        "attributes": attrs, "children": {}, "instance_count": 1,
        "order": [], "order_stable": True, "has_text": False,
    }}
    return model


def test_derived_sums_labels_all_combinations():
    entry = _entry(["1", "2", "4"], labels={"1": "A", "2": "B", "4": "C"}, sums=True)
    assert derived_sums_labels(entry) == {
        "1": "A", "2": "B", "4": "C",
        "3": "A+B", "5": "A+C", "6": "B+C", "7": "A+B+C",
    }


def test_derived_sums_explicit_row_overrides():
    entry = _entry(["1", "2", "3"], labels={"1": "A", "2": "B", "3": "both"}, sums=True)
    assert derived_sums_labels(entry)["3"] == "both"


def test_derived_sums_skips_unlabeled_and_non_numeric_atoms():
    entry = _entry(["1", "2", "x"], labels={"1": "A", "x": "odd"}, sums=True)
    result = derived_sums_labels(entry)
    assert result["1"] == "A"
    assert "3" not in result          # 2 unlabeled -> not an atom
    assert result["x"] == "odd"       # explicit non-numeric label survives


def test_known_values_sums_offers_all_combinations_numerically_sorted():
    model = _model({"pp": _entry(["1", "2", "4"], labels={"1": "A", "2": "B", "4": "C"}, sums=True)})
    values = known_values(model, "Root", "pp")
    assert values == [
        ("1", "A"), ("2", "B"), ("3", "A+B"), ("4", "C"),
        ("5", "A+C"), ("6", "B+C"), ("7", "A+B+C"),
    ]


def test_known_values_plain_and_hint():
    model = _model({
        "phpDriver": _entry(["0", "1"], labels={"0": "pdo", "1": "php-psql"}),
        "loc": _entry([], hint="Path to localization file"),
    })
    assert known_values(model, "Root", "phpDriver") == [("0", "pdo"), ("1", "php-psql")]
    assert known_values(model, "Root", "loc") == []
    assert known_values(model, "Root", "missing") == []


def test_enum_hint_variants():
    model = _model({
        "phpDriver": _entry(["0", "1"], labels={"0": "pdo", "1": "php-psql"}),
        "loc": _entry([], hint="Path to localization file"),
        "bare": _entry([]),
    })
    assert enum_hint(model, "Root", "phpDriver") == "phpDriver — 0 = pdo · 1 = php-psql"
    assert enum_hint(model, "Root", "loc") == "loc — Path to localization file"
    assert enum_hint(model, "Root", "bare") is None


def test_known_and_unused_attributes_no_kind_filter():
    model = _model({"a": _entry(["1"]), "b": _entry([])})
    assert known_attributes(model, "Root", {"a"}) == ["b"]
    assert unused_setting_attributes(model, "Root", {"a"}) == ["b"]
    assert known_attributes(model, "Nope", set()) == []


def test_value_label_uses_effective_labels():
    model = _model({"pp": _entry(["1", "2"], labels={"1": "A", "2": "B"}, sums=True)})
    assert value_label(model, "Root", "pp", "3") == "A+B"
    assert value_label(model, "Root", "pp", "9") is None
    assert value_label(model, "Root", "missing", "1") is None


def test_effective_labels_plain_is_copy():
    entry = _entry(["1"], labels={"1": "A"})
    result = effective_labels(entry)
    result["1"] = "mutated"
    assert entry["labels"]["1"] == "A"
