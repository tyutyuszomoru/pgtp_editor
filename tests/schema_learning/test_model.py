from pgtp_editor.schema_learning.model import Model


def test_new_path_emits_new_element_and_new_attribute_events():
    model = Model()
    events = model.merge_element("Root", {"a": "1", "b": "x"}, {}, False)

    kinds = [e["kind"] for e in events]
    assert "new_element" in kinds
    assert kinds.count("new_attribute") == 2

    entry = model.paths["Root"]
    assert entry["instance_count"] == 1
    assert entry["attributes"]["a"]["type"] == "integer"
    assert entry["attributes"]["a"]["values"] == ["1"]
    assert entry["attributes"]["b"]["type"] == "string"


def test_repeat_instance_same_value_emits_no_new_events():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    events = model.merge_element("Root", {"a": "1"}, {}, False)

    assert events == []
    assert model.paths["Root"]["instance_count"] == 2
    assert model.paths["Root"]["attributes"]["a"]["attr_seen_count"] == 2


def test_new_distinct_value_emits_new_value_event():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    events = model.merge_element("Root", {"a": "2"}, {}, False)

    assert [e["kind"] for e in events] == ["new_value"]
    assert model.paths["Root"]["attributes"]["a"]["values"] == ["1", "2"]


def test_type_widens_when_a_non_matching_value_appears():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.merge_element("Root", {"a": "hello"}, {}, False)

    assert model.paths["Root"]["attributes"]["a"]["type"] == "string"


def test_enum_overflows_past_ten_distinct_values():
    model = Model()
    events = []
    for i in range(11):
        events = model.merge_element("Root", {"a": str(i)}, {}, False)

    attr = model.paths["Root"]["attributes"]["a"]
    assert attr["overflowed"] is True
    assert attr["values"] is None
    assert any(e["kind"] == "enum_overflow" for e in events)


def test_overflowed_attribute_never_emits_new_value_again():
    model = Model()
    for i in range(11):
        model.merge_element("Root", {"a": str(i)}, {}, False)

    events = model.merge_element("Root", {"a": "not-seen-before"}, {}, False)
    assert events == []


def test_missing_attribute_flips_required_to_optional():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.merge_element("Root", {"a": "2"}, {}, False)
    events = model.merge_element("Root", {}, {}, False)

    assert any(e["kind"] == "now_optional" and e["attr"] == "a" for e in events)
    assert model.paths["Root"]["attributes"]["a"]["attr_seen_count"] == 2
    assert model.paths["Root"]["instance_count"] == 3


def test_optional_attribute_missing_again_emits_no_further_event():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.merge_element("Root", {}, {}, False)
    events = model.merge_element("Root", {}, {}, False)

    assert events == []


def test_child_seen_in_every_instance_is_required_single():
    model = Model()
    model.merge_element("Root", {}, {"A": 1}, False)
    model.merge_element("Root", {}, {"A": 1}, False)

    child = model.paths["Root"]["children"]["A"]
    assert child["ever_absent"] is False
    assert child["ever_multiple"] is False


def test_child_missing_in_some_instance_is_marked_ever_absent():
    model = Model()
    model.merge_element("Root", {}, {"A": 1, "B": 1}, False)
    model.merge_element("Root", {}, {"A": 1}, False)

    assert model.paths["Root"]["children"]["B"]["ever_absent"] is True
    assert model.paths["Root"]["children"]["A"]["ever_absent"] is False


def test_child_appearing_only_later_is_retroactively_ever_absent():
    model = Model()
    model.merge_element("Root", {}, {"A": 1}, False)
    model.merge_element("Root", {}, {"A": 1, "B": 1}, False)

    assert model.paths["Root"]["children"]["B"]["ever_absent"] is True


def test_child_appearing_multiple_times_in_one_instance_is_ever_multiple():
    model = Model()
    model.merge_element("Root", {}, {"A": 3}, False)

    assert model.paths["Root"]["children"]["A"]["ever_multiple"] is True


def test_order_stable_when_consistent():
    model = Model()
    model.merge_element("Root", {}, {"A": 1, "B": 1}, False)
    model.merge_element("Root", {}, {"A": 1, "B": 1}, False)

    assert model.paths["Root"]["order_stable"] is True
    assert model.paths["Root"]["order"] == ["A", "B"]


def test_order_unstable_when_relative_order_changes():
    model = Model()
    model.merge_element("Root", {}, {"A": 1, "B": 1}, False)
    model.merge_element("Root", {}, {"B": 1, "A": 1}, False)

    assert model.paths["Root"]["order_stable"] is False


def test_has_text_flag_sticky_once_true():
    model = Model()
    model.merge_element("Root", {}, {}, True)
    model.merge_element("Root", {}, {}, False)

    assert model.paths["Root"]["has_text"] is True


def test_secret_named_attribute_never_captures_values():
    model = Model()
    events1 = model.merge_element("Root", {"password": "hunter2"}, {}, False)

    attr = model.paths["Root"]["attributes"]["password"]
    assert attr["overflowed"] is True
    assert attr["values"] is None
    assert not any(e["kind"] in ("new_value", "enum_overflow") for e in events1)

    events2 = model.merge_element("Root", {"password": "other"}, {}, False)
    attr = model.paths["Root"]["attributes"]["password"]
    assert attr["overflowed"] is True
    assert attr["values"] is None
    assert not any(e["kind"] in ("new_value", "enum_overflow") for e in events2)


def test_secret_name_matching_is_case_insensitive_substring():
    model = Model()
    model.merge_element(
        "Root",
        {"Password": "a", "DB_PASSWORD": "b", "authToken": "c"},
        {},
        False,
    )

    for attr_name in ("Password", "DB_PASSWORD", "authToken"):
        attr = model.paths["Root"]["attributes"][attr_name]
        assert attr["overflowed"] is True
        assert attr["values"] is None


def test_non_secret_attribute_still_gets_normal_enum_tracking():
    model = Model()
    model.merge_element("Root", {"name": "x"}, {}, False)
    model.merge_element("Root", {"name": "y"}, {}, False)

    attr = model.paths["Root"]["attributes"]["name"]
    assert attr["overflowed"] is False
    assert attr["values"] == ["x", "y"]


def test_secret_named_attribute_still_emits_new_attribute_event():
    model = Model()
    events = model.merge_element("Root", {"password": "hunter2"}, {}, False)

    assert any(e["kind"] == "new_attribute" and e["attr"] == "password" for e in events)


# --- labels field: new tests for this sub-project ---


def test_freshly_created_attribute_entry_has_empty_labels():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)

    assert model.paths["Root"]["attributes"]["a"]["labels"] == {}


def test_secret_attribute_entry_also_has_empty_labels():
    model = Model()
    model.merge_element("Root", {"password": "hunter2"}, {}, False)

    assert model.paths["Root"]["attributes"]["password"]["labels"] == {}


def test_labels_round_trip_through_to_dict_from_dict_and_save_load(tmp_path):
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.paths["Root"]["attributes"]["a"]["labels"]["1"] = "Full export"

    restored = Model.from_dict(model.to_dict())
    assert restored.paths["Root"]["attributes"]["a"]["labels"] == {"1": "Full export"}

    save_path = tmp_path / "model.json"
    model.save(save_path)
    loaded = Model.load(save_path)
    assert loaded.paths["Root"]["attributes"]["a"]["labels"] == {"1": "Full export"}


def test_merge_element_never_alters_existing_labels_across_repeated_merges():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.paths["Root"]["attributes"]["a"]["labels"]["1"] = "One"

    # Merge several more times, including a new distinct value, and confirm
    # the previously-set label survives untouched.
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.merge_element("Root", {"a": "2"}, {}, False)

    assert model.paths["Root"]["attributes"]["a"]["labels"] == {"1": "One"}


def test_labels_survive_enum_overflow_even_though_values_becomes_none():
    model = Model()
    model.merge_element("Root", {"a": "0"}, {}, False)
    model.paths["Root"]["attributes"]["a"]["labels"]["0"] = "Zero label"

    for i in range(1, 11):
        model.merge_element("Root", {"a": str(i)}, {}, False)

    attr = model.paths["Root"]["attributes"]["a"]
    assert attr["overflowed"] is True
    assert attr["values"] is None
    assert attr["labels"] == {"0": "Zero label"}
