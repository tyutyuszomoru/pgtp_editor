from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.settings_index import (
    attribute_kind,
    derived_bitflag_label,
    effective_labels,
    enum_hint,
    is_enum_candidate,
    known_attributes,
    known_values,
    unused_setting_attributes,
    value_note,
)


_MISSING = object()


def _entry(type_="integer", values=None, overflowed=False, kind=_MISSING):
    entry = {
        "type": type_,
        "values": values if values is not None else ["1", "2"],
        "overflowed": overflowed,
        "attr_seen_count": 2,
        "labels": {},
    }
    if kind is not _MISSING:
        entry["kind"] = kind
    return entry


def test_is_enum_candidate_true_for_non_overflowed_non_boolean_with_values():
    assert is_enum_candidate(_entry()) is True


def test_is_enum_candidate_false_when_overflowed():
    assert is_enum_candidate(_entry(overflowed=True, values=None)) is False


def test_is_enum_candidate_false_when_boolean():
    assert is_enum_candidate(_entry(type_="boolean", values=["true", "false"])) is False


def test_is_enum_candidate_false_when_values_empty():
    assert is_enum_candidate(_entry(values=[])) is False


def test_attribute_kind_defaults_to_unclassified_when_no_key():
    assert attribute_kind(_entry()) == "unclassified"


def test_attribute_kind_returns_unclassified_when_kind_is_none():
    assert attribute_kind(_entry(kind=None)) == "unclassified"


def test_attribute_kind_returns_setting():
    assert attribute_kind(_entry(kind="setting")) == "setting"


def test_attribute_kind_returns_content():
    assert attribute_kind(_entry(kind="content")) == "content"


def _model_with(attr_entry, tag_chain="Root/Node", attr="editFormMode"):
    model = Model()
    model.paths[tag_chain] = {
        "attributes": {attr: attr_entry},
        "children": {},
        "instance_count": 1,
        "order": [],
        "order_stable": True,
        "has_text": False,
    }
    return model


def test_enum_hint_setting_with_full_labels():
    entry = _entry(
        values=["1", "2", "3"],
        kind="setting",
    )
    entry["labels"] = {"1": "modal", "2": "new page", "3": "inline"}
    model = _model_with(entry)
    assert (
        enum_hint(model, "Root/Node", "editFormMode")
        == "editFormMode — 1 = modal · 2 = new page · 3 = inline"
    )


def test_enum_hint_setting_with_partial_labels_shows_bare_values():
    entry = _entry(values=["1", "2", "3"], kind="setting")
    entry["labels"] = {"1": "modal", "3": "inline"}
    model = _model_with(entry)
    assert (
        enum_hint(model, "Root/Node", "editFormMode")
        == "editFormMode — 1 = modal · 2 · 3 = inline"
    )


def test_enum_hint_none_for_non_setting():
    entry = _entry(values=["1", "2"], kind="content")
    entry["labels"] = {"1": "modal"}
    model = _model_with(entry)
    assert enum_hint(model, "Root/Node", "editFormMode") is None


def test_enum_hint_none_for_unclassified():
    entry = _entry(values=["1", "2"])
    entry["labels"] = {"1": "modal"}
    model = _model_with(entry)
    assert enum_hint(model, "Root/Node", "editFormMode") is None


def test_enum_hint_none_for_unknown_path():
    entry = _entry(values=["1", "2"], kind="setting")
    model = _model_with(entry)
    assert enum_hint(model, "Root/Missing", "editFormMode") is None


def test_enum_hint_none_for_unknown_attr():
    entry = _entry(values=["1", "2"], kind="setting")
    model = _model_with(entry)
    assert enum_hint(model, "Root/Node", "nope") is None


def test_enum_hint_none_for_overflowed_setting_without_labels():
    entry = _entry(overflowed=True, kind="setting")
    entry["values"] = None
    model = _model_with(entry)
    assert enum_hint(model, "Root/Node", "editFormMode") is None


def test_enum_hint_none_for_boolean_setting_without_labels():
    entry = _entry(type_="boolean", values=["true", "false"], kind="setting")
    model = _model_with(entry)
    assert enum_hint(model, "Root/Node", "editFormMode") is None


def test_enum_hint_candidate_setting_without_labels_shows_bare_values():
    entry = _entry(values=["1", "2"], kind="setting")
    model = _model_with(entry)
    assert enum_hint(model, "Root/Node", "editFormMode") == "editFormMode — 1 · 2"


def test_enum_hint_overflowed_setting_with_labels_iterates_labels():
    entry = _entry(overflowed=True, kind="setting")
    entry["values"] = None
    entry["labels"] = {"b": "second", "a": "first"}
    model = _model_with(entry)
    assert (
        enum_hint(model, "Root/Node", "editFormMode")
        == "editFormMode — a = first · b = second"
    )


def test_enum_hint_values_sorted():
    entry = _entry(values=["3", "1", "2"], kind="setting")
    entry["labels"] = {}
    model = _model_with(entry)
    assert enum_hint(model, "Root/Node", "editFormMode") == "editFormMode — 1 · 2 · 3"


# --- unused_setting_attributes --------------------------------------------


def _model_with_attrs(attributes, tag_chain="Root/Node"):
    model = Model()
    model.paths[tag_chain] = {
        "attributes": attributes,
        "children": {},
        "instance_count": 1,
        "order": [],
        "order_stable": True,
        "has_text": False,
    }
    return model


def test_unused_setting_attributes_returns_settings_not_present():
    model = _model_with_attrs(
        {
            "editFormMode": _entry(kind="setting"),
            "pageMode": _entry(kind="setting"),
        }
    )
    assert unused_setting_attributes(model, "Root/Node", set()) == [
        "editFormMode",
        "pageMode",
    ]


def test_unused_setting_attributes_excludes_present():
    model = _model_with_attrs(
        {
            "editFormMode": _entry(kind="setting"),
            "pageMode": _entry(kind="setting"),
        }
    )
    assert unused_setting_attributes(model, "Root/Node", {"editFormMode"}) == [
        "pageMode"
    ]


def test_unused_setting_attributes_excludes_content_and_unclassified():
    model = _model_with_attrs(
        {
            "editFormMode": _entry(kind="setting"),
            "caption": _entry(kind="content"),
            "name": _entry(),  # unclassified
        }
    )
    assert unused_setting_attributes(model, "Root/Node", set()) == ["editFormMode"]


def test_unused_setting_attributes_unknown_path_returns_empty():
    model = _model_with_attrs({"editFormMode": _entry(kind="setting")})
    assert unused_setting_attributes(model, "Root/Missing", set()) == []


def test_unused_setting_attributes_sorted():
    model = _model_with_attrs(
        {
            "zeta": _entry(kind="setting"),
            "alpha": _entry(kind="setting"),
            "mid": _entry(kind="setting"),
        }
    )
    assert unused_setting_attributes(model, "Root/Node", set()) == [
        "alpha",
        "mid",
        "zeta",
    ]


# --- known_attributes --------------------------------------------------


def _model_multi(tag_chain, names, kind="setting"):
    model = Model()
    attributes = {
        name: {
            "type": "integer",
            "values": ["1", "2"],
            "overflowed": False,
            "attr_seen_count": 2,
            "labels": {},
            "kind": kind,
        }
        for name in names
    }
    model.paths[tag_chain] = {
        "attributes": attributes,
        "children": {},
        "instance_count": 1,
        "order": [],
        "order_stable": True,
        "has_text": False,
    }
    return model


def test_known_attributes_returns_all_minus_present_sorted():
    model = _model_multi("Root/Node", ["zeta", "alpha", "mid"])
    assert known_attributes(model, "Root/Node", {"mid"}) == ["alpha", "zeta"]


def test_known_attributes_not_filtered_by_kind():
    # unclassified/content attributes are still offered (broad list)
    model = _model_multi("Root/Node", ["a", "b"], kind="content")
    assert known_attributes(model, "Root/Node", set()) == ["a", "b"]


def test_known_attributes_empty_present_returns_all():
    model = _model_multi("Root/Node", ["a", "b"])
    assert known_attributes(model, "Root/Node", []) == ["a", "b"]


def test_known_attributes_unknown_path_returns_empty():
    model = _model_multi("Root/Node", ["a"])
    assert known_attributes(model, "Root/Missing", set()) == []


# --- known_values --------------------------------------------------


def _model_one(entry, tag_chain="Root/Node", attr="editAbilityMode"):
    model = Model()
    model.paths[tag_chain] = {
        "attributes": {attr: entry},
        "children": {},
        "instance_count": 1,
        "order": [],
        "order_stable": True,
        "has_text": False,
    }
    return model


def test_known_values_pairs_sorted_with_labels():
    entry = {
        "type": "integer",
        "values": ["3", "0", "2"],
        "overflowed": False,
        "attr_seen_count": 3,
        "labels": {"0": "none", "3": "full"},
    }
    model = _model_one(entry)
    assert known_values(model, "Root/Node", "editAbilityMode") == [
        ("0", "none"),
        ("2", None),
        ("3", "full"),
    ]


def test_known_values_empty_when_overflowed():
    entry = {
        "type": "string",
        "values": ["a", "b"],
        "overflowed": True,
        "attr_seen_count": 9,
        "labels": {},
    }
    model = _model_one(entry)
    assert known_values(model, "Root/Node", "editAbilityMode") == []


def test_known_values_empty_when_no_values():
    entry = {
        "type": "string",
        "values": [],
        "overflowed": False,
        "attr_seen_count": 0,
        "labels": {},
    }
    model = _model_one(entry)
    assert known_values(model, "Root/Node", "editAbilityMode") == []


def test_known_values_missing_labels_key_gives_none_labels():
    # A legacy/partial entry without a "labels" key still yields pairs, all
    # labels None.
    entry = {
        "type": "integer",
        "values": ["2", "1"],
        "overflowed": False,
        "attr_seen_count": 2,
    }
    model = _model_one(entry)
    assert known_values(model, "Root/Node", "editAbilityMode") == [
        ("1", None),
        ("2", None),
    ]


def test_known_values_empty_for_unknown_attr():
    entry = {
        "type": "integer",
        "values": ["1"],
        "overflowed": False,
        "attr_seen_count": 1,
        "labels": {},
    }
    model = _model_one(entry)
    assert known_values(model, "Root/Node", "missing") == []


# --- derived_bitflag_label, effective_labels, value_note ------------------


def _entry_attr(values, labels=None, **extra):
    entry = {
        "type": "integer",
        "values": values,
        "overflowed": values is None,
        "attr_seen_count": 1,
        "labels": labels or {},
    }
    entry.update(extra)
    return entry


def test_derived_bitflag_label_composes_atomic_labels():
    labels = {"1": "A", "2": "B", "4": "C"}
    assert derived_bitflag_label("3", labels) == "A+B"
    assert derived_bitflag_label("5", labels) == "A+C"
    assert derived_bitflag_label("6", labels) == "B+C"
    assert derived_bitflag_label("7", labels) == "A+B+C"


def test_derived_bitflag_label_missing_bit_returns_none():
    assert derived_bitflag_label("3", {"1": "A"}) is None


def test_derived_bitflag_label_rejects_non_numeric_and_nonpositive():
    assert derived_bitflag_label("x", {"1": "A"}) is None
    assert derived_bitflag_label("0", {"1": "A"}) is None
    assert derived_bitflag_label("-2", {"2": "B"}) is None


def test_effective_labels_plain_mode_returns_labels_copy():
    entry = _entry_attr(["1", "2"], labels={"1": "A"})
    result = effective_labels(entry)
    assert result == {"1": "A"}
    result["1"] = "mutated"
    assert entry["labels"]["1"] == "A"  # a copy, not the stored dict


def test_effective_labels_bitflags_derives_composites_explicit_wins():
    entry = _entry_attr(
        ["1", "2", "3", "5"],
        labels={"1": "A", "2": "B", "5": "custom"},
        enum_mode="bitflags",
    )
    assert effective_labels(entry) == {
        "1": "A",
        "2": "B",
        "3": "A+B",       # derived
        "5": "custom",    # explicit overrides derived "A+?" (4 unlabeled anyway)
    }


def test_effective_labels_bitflags_overflowed_uses_label_keys():
    entry = _entry_attr(None, labels={"1": "A", "2": "B"}, enum_mode="bitflags")
    assert effective_labels(entry) == {"1": "A", "2": "B"}


def test_value_note_reads_notes_dict():
    entry = _entry_attr(["4"], notes={"4": "enables the <Watermark> child tag"})
    assert value_note(entry, "4") == "enables the <Watermark> child tag"
    assert value_note(entry, "1") is None
    assert value_note(_entry_attr(["4"]), "4") is None
