from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.settings_index import (
    attribute_kind,
    enum_hint,
    is_enum_candidate,
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
