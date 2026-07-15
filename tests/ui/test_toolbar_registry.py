"""Sub-project E -- pure toolbar-command registry unit tests (Qt-free)."""
from pgtp_editor.ui.toolbar_registry import (
    AVAILABLE_COMMANDS,
    DEFAULT_TOOLBAR_IDS,
    available_ids,
    label_for,
    valid_ids,
)


def test_available_commands_content_and_order():
    assert AVAILABLE_COMMANDS == [
        ("open", "Open"),
        ("save", "Save"),
        ("undo", "Undo"),
        ("redo", "Redo"),
        ("find", "Find"),
        ("validate", "Validate"),
        ("generate", "Generate"),
    ]


def test_default_toolbar_ids_content_and_order():
    assert DEFAULT_TOOLBAR_IDS == [
        "open",
        "save",
        "undo",
        "redo",
        "find",
        "validate",
        "generate",
    ]


def test_available_ids_matches_registry_order():
    assert available_ids() == [cid for cid, _label in AVAILABLE_COMMANDS]


def test_label_for_known_and_unknown():
    assert label_for("open") == "Open"
    assert label_for("generate") == "Generate"
    assert label_for("nope") is None


def test_valid_ids_preserves_order_drops_unknowns():
    assert valid_ids(["save", "open", "bogus", "find"]) == ["save", "open", "find"]


def test_valid_ids_drops_duplicates_keeping_first():
    assert valid_ids(["save", "save", "open", "open"]) == ["save", "open"]


def test_valid_ids_empty_and_all_unknown():
    assert valid_ids([]) == []
    assert valid_ids(["x", "y"]) == []
