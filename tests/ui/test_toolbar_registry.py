"""Sub-project E -- pure toolbar-command identity rules (Qt-free).

BUG-027 widened the toolbar's command universe from a hardcoded seven to every
menu command, so this module no longer owns the command list (see
`MainWindow._all_menu_commands`, covered in test_toolbar.py). What is unit-
tested here is the pure part it kept: menu-path -> stable id, legacy-id
aliasing, and id filtering against a caller-supplied known set.
"""
from pgtp_editor.ui.toolbar_registry import (
    DEFAULT_TOOLBAR_IDS,
    ICON_ID_BY_COMMAND,
    LEGACY_COMMANDS,
    LEGACY_ID_ALIASES,
    command_id_for,
    menu_path_label,
    normalize_label,
    resolve_ids,
    slugify,
    valid_ids,
)


def test_legacy_commands_content_and_order():
    assert LEGACY_COMMANDS == [
        ("open", "Open"),
        ("save", "Save"),
        ("undo", "Undo"),
        ("redo", "Redo"),
        ("find", "Find"),
        ("validate", "Validate"),
        ("generate", "Generate"),
    ]


def test_default_toolbar_ids_are_menu_path_ids_in_legacy_order():
    assert DEFAULT_TOOLBAR_IDS == [
        "file.open",
        "file.save",
        "edit.undo",
        "edit.redo",
        "edit.find",
        "tools.validate-project",
        "generation.generate-php",
    ]


def test_every_legacy_id_has_an_alias():
    assert set(LEGACY_ID_ALIASES) == {cid for cid, _label in LEGACY_COMMANDS}


def test_icon_ids_invert_the_aliases():
    assert ICON_ID_BY_COMMAND == {
        new_id: legacy_id for legacy_id, new_id in LEGACY_ID_ALIASES.items()
    }
    assert ICON_ID_BY_COMMAND["file.open"] == "open"
    assert "file.save-as" not in ICON_ID_BY_COMMAND   # icon-less is normal


# -- label / id derivation -------------------------------------------------
def test_normalize_label_strips_mnemonics_and_ellipsis():
    assert normalize_label("&Save As...") == "Save As"
    assert normalize_label("History…") == "History"
    assert normalize_label("Save") == "Save"
    assert normalize_label("") == ""


def test_slugify_collapses_punctuation():
    assert slugify("Generate PHP...") == "generate-php"
    assert slugify("Deploy .pgtp") == "deploy-pgtp"
    assert slugify("Validate Project") == "validate-project"


def test_command_id_for_joins_the_menu_path():
    assert command_id_for(["File", "Save As..."]) == "file.save-as"
    assert command_id_for(["Tools", "Validate Project"]) == "tools.validate-project"
    assert command_id_for(["File", "Open..."]) == "file.open"


def test_command_id_for_drops_empty_segments():
    assert command_id_for(["File", "", "Save"]) == "file.save"
    assert command_id_for([]) == ""


def test_menu_path_label_is_human_readable():
    assert menu_path_label(["File", "Save As..."]) == "File › Save As"
    assert menu_path_label(["Edit", "Find..."]) == "Edit › Find"


# -- id filtering ----------------------------------------------------------
_KNOWN = ["file.open", "file.save", "edit.find"]


def test_valid_ids_preserves_order_drops_unknowns():
    assert valid_ids(
        ["file.save", "file.open", "bogus", "edit.find"], _KNOWN
    ) == ["file.save", "file.open", "edit.find"]


def test_valid_ids_drops_duplicates_keeping_first():
    assert valid_ids(
        ["file.save", "file.save", "file.open", "file.open"], _KNOWN
    ) == ["file.save", "file.open"]


def test_valid_ids_empty_and_all_unknown():
    assert valid_ids([], _KNOWN) == []
    assert valid_ids(None, _KNOWN) == []
    assert valid_ids(["x", "y"], _KNOWN) == []


def test_resolve_ids_maps_legacy_ids_so_saved_toolbars_survive():
    """The back-compat guarantee: a toolbar saved before BUG-027 stored
    `save`/`find`, which are unknown under the new scheme -- without aliasing
    every existing user's toolbar would silently empty on first launch."""
    assert resolve_ids(["save", "find"], _KNOWN) == ["file.save", "edit.find"]


def test_resolve_ids_passes_through_new_ids_and_still_drops_unknowns():
    assert resolve_ids(["file.open", "nope"], _KNOWN) == ["file.open"]


def test_resolve_ids_deduplicates_a_legacy_and_new_id_for_the_same_command():
    assert resolve_ids(["save", "file.save"], _KNOWN) == ["file.save"]
