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

from pgtp_editor.schema_learning.merge import Conflict, apply_resolution, merge_models
from pgtp_editor.schema_learning.model import ENUM_MAX_VALUES, Model


def _model(paths):
    model = Model()
    model.paths = paths
    return model


def _element(attributes=None, instance_count=1, children=None, order=None):
    return {
        "attributes": attributes or {},
        "children": children or {},
        "instance_count": instance_count,
        "order": order or [],
        "order_stable": True,
        "has_text": False,
    }


def _attr(values, labels=None, seen=1, **extra):
    entry = {
        "type": "integer",
        "values": values,
        "overflowed": values is None,
        "attr_seen_count": seen,
        "labels": labels or {},
    }
    entry.update(extra)
    return entry


def test_superset_merge_is_conflict_free_and_additive():
    base = _model({"Root": _element({"a": _attr(["1"], labels={"1": "A"})})})
    incoming = _model({
        "Root": _element({
            "a": _attr(["1", "2"], labels={"1": "A", "2": "B"}),
            "b": _attr(["x"]),
        }),
        "Root/New": _element({}),
    })
    conflicts = merge_models(base, incoming)
    assert conflicts == []
    entry = base.paths["Root"]["attributes"]["a"]
    assert sorted(entry["values"]) == ["1", "2"]
    assert entry["labels"] == {"1": "A", "2": "B"}
    assert "b" in base.paths["Root"]["attributes"]
    assert "Root/New" in base.paths


def test_label_conflict_keeps_base_and_reports():
    base = _model({"Root": _element({"a": _attr(["4"], labels={"4": "pdf"})})})
    incoming = _model({"Root": _element({"a": _attr(["4"], labels={"4": "PDF export"})})})
    conflicts = merge_models(base, incoming)
    assert conflicts == [
        Conflict("Root", "a", "labels", "4", "pdf", "PDF export")
    ]
    assert base.paths["Root"]["attributes"]["a"]["labels"]["4"] == "pdf"


def test_apply_resolution_takes_incoming():
    base = _model({"Root": _element({"a": _attr(["4"], labels={"4": "pdf"})})})
    conflict = Conflict("Root", "a", "labels", "4", "pdf", "PDF export")
    apply_resolution(base, conflict, use_incoming=True)
    assert base.paths["Root"]["attributes"]["a"]["labels"]["4"] == "PDF export"
    apply_resolution(base, conflict, use_incoming=False)  # no-op
    assert base.paths["Root"]["attributes"]["a"]["labels"]["4"] == "PDF export"


def test_required_survives_only_when_required_on_both_sides():
    base = _model({"Root": _element({"a": _attr(["1"], seen=5)}, instance_count=5)})
    incoming = _model({"Root": _element({"a": _attr(["1"], seen=2)}, instance_count=3)})
    merge_models(base, incoming)
    entry = base.paths["Root"]
    attr = entry["attributes"]["a"]
    assert entry["instance_count"] == 8
    assert attr["attr_seen_count"] == 7
    assert attr["attr_seen_count"] != entry["instance_count"]  # optional now


def test_values_union_overflow():
    base = _model({"Root": _element({"a": _attr([str(i) for i in range(ENUM_MAX_VALUES)])})})
    incoming = _model({"Root": _element({"a": _attr(["x", "y"])})})
    merge_models(base, incoming)
    attr = base.paths["Root"]["attributes"]["a"]
    assert attr["overflowed"] is True
    assert attr["values"] is None


def test_kind_and_enum_mode_conflicts():
    base = _model({"Root": _element({"a": _attr(["1"], kind="setting")})})
    incoming = _model({"Root": _element({"a": _attr(["1"], kind="content", enum_mode="bitflags")})})
    conflicts = merge_models(base, incoming)
    assert conflicts == [
        Conflict("Root", "a", "kind", None, "setting", "content")
    ]
    # enum_mode was unset on base -> adopted, no conflict
    assert base.paths["Root"]["attributes"]["a"]["enum_mode"] == "bitflags"


def test_merge_does_not_alias_incoming():
    """Verify that merge deep-copies incoming paths/attributes, not aliases."""
    base = _model({})
    incoming = _model({
        "Root": _element({"a": _attr(["x"], labels={"x": "label_x"})})
    })
    merge_models(base, incoming)

    # Mutate the incoming model's entry
    incoming.paths["Root"]["attributes"]["a"]["values"].append("y")
    incoming.paths["Root"]["attributes"]["a"]["labels"]["x"] = "mutated_label"

    # Assert base copies are unaffected
    assert base.paths["Root"]["attributes"]["a"]["values"] == ["x"]
    assert base.paths["Root"]["attributes"]["a"]["labels"]["x"] == "label_x"


def test_children_flags_or_and_order_append():
    """Test merging child flags with OR logic and order list merging."""
    # Scenario 1: children flags merge with OR, order appends new tags
    base = _model({
        "Root": _element(
            children={"A": {"ever_absent": False, "ever_multiple": False}},
            order=["A"]
        )
    })
    incoming = _model({
        "Root": _element(
            children={
                "A": {"ever_absent": True, "ever_multiple": False},
                "B": {"ever_absent": False, "ever_multiple": True}
            },
            order=["A", "B"]
        )
    })
    conflicts = merge_models(base, incoming)
    assert conflicts == []

    # Child A flags merged with OR
    assert base.paths["Root"]["children"]["A"]["ever_absent"] is True
    assert base.paths["Root"]["children"]["A"]["ever_multiple"] is False
    # Child B added
    assert "B" in base.paths["Root"]["children"]
    assert base.paths["Root"]["children"]["B"]["ever_multiple"] is True
    # Order appended
    assert base.paths["Root"]["order"] == ["A", "B"]
    # order_stable unchanged (no conflict)
    assert base.paths["Root"]["order_stable"] is True

    # Scenario 2: order conflict flips order_stable to False
    base2 = _model({
        "Root": _element(
            children={"A": {"ever_absent": False, "ever_multiple": False},
                      "B": {"ever_absent": False, "ever_multiple": False}},
            order=["A", "B"]
        )
    })
    incoming2 = _model({
        "Root": _element(
            children={"A": {"ever_absent": False, "ever_multiple": False},
                      "B": {"ever_absent": False, "ever_multiple": False}},
            order=["B", "A"]
        )
    })
    merge_models(base2, incoming2)

    # order_stable flipped because common children have different order
    assert base2.paths["Root"]["order_stable"] is False


def test_notes_conflict_detected_like_labels():
    """Test that notes field conflicts are detected and tracked like labels."""
    base = _model({
        "Root": _element({"a": _attr(["1"], notes={"1": "base note"})})
    })
    incoming = _model({
        "Root": _element({"a": _attr(["1"], notes={"1": "incoming note"})})
    })
    conflicts = merge_models(base, incoming)

    # One conflict for the notes field
    assert conflicts == [
        Conflict("Root", "a", "notes", "1", "base note", "incoming note")
    ]
    # Base value is kept
    assert base.paths["Root"]["attributes"]["a"]["notes"]["1"] == "base note"
