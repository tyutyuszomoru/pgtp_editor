from pgtp_editor.schema_learning.settings_index import (
    attribute_kind,
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
