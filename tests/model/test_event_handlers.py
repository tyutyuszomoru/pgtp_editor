from pgtp_editor.model.event_handlers import EVENT_HANDLERS, language_for_side


def test_event_handlers_has_forty_entries():
    assert len(EVENT_HANDLERS) == 40


def test_event_handlers_side_split_is_nine_client_thirtyone_server():
    clients = [tag for tag, side in EVENT_HANDLERS if side == "C"]
    servers = [tag for tag, side in EVENT_HANDLERS if side == "S"]
    assert len(clients) == 9
    assert len(servers) == 31


def test_event_handlers_entries_are_tag_side_pairs_with_valid_sides():
    for entry in EVENT_HANDLERS:
        assert isinstance(entry, tuple) and len(entry) == 2
        tag, side = entry
        assert isinstance(tag, str) and tag
        assert side in ("C", "S")


def test_event_handlers_tags_are_unique():
    tags = [tag for tag, _ in EVENT_HANDLERS]
    assert len(tags) == len(set(tags))


def test_event_handlers_includes_specific_handlers_with_correct_sides():
    mapping = dict(EVENT_HANDLERS)
    assert mapping["OnPreparePage"] == "S"
    assert mapping["OnAfterPageLoad"] == "C"
    assert mapping["OnBeforePageLoad"] == "C"
    assert mapping["OnAfterDeleteRecord"] == "S"


def test_language_for_side_client_is_js():
    assert language_for_side("C") == "js"


def test_language_for_side_server_is_php():
    assert language_for_side("S") == "php"
