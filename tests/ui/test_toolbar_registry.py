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
    RENAMED_ID_ALIASES,
    command_id_for,
    menu_path_label,
    normalize_label,
    resolve_ids,
    slugify,
    valid_ids,
)


def test_legacy_commands_content_and_order():
    # FIVE, down from the original seven: `find` retired with FQ-016 (Find lost
    # its menu home when the Edit menu dissolved) and `save` with FQ-020
    # (`File ▸ Save` and `Ctrl+S` are deleted; the four surviving save entries are
    # tab-gated `Deployment` members, so none may be a *default* button).
    assert LEGACY_COMMANDS == [
        ("open", "Open"),
        ("undo", "Undo"),
        ("redo", "Redo"),
        ("validate", "Validate"),
        ("generate", "Generate"),
    ]
    assert "find" not in dict(LEGACY_COMMANDS)
    assert "save" not in dict(LEGACY_COMMANDS)


def test_default_toolbar_ids_are_menu_path_ids_in_legacy_order():
    # `history.*` and `parsing.*` since FQ-016 moved Undo/Redo onto the Editor
    # bar's History menu and Validate Project onto its Parsing menu. An alias
    # left pointing at the old path would ship a default button empty.
    #
    # FIVE buttons since FQ-020, and the app ships with NO save button at all.
    assert DEFAULT_TOOLBAR_IDS == [
        "file.open",
        "history.undo",
        "history.redo",
        "parsing.validate-project",
        "generation.generate-php",
    ]
    assert "edit.find" not in DEFAULT_TOOLBAR_IDS
    assert "file.save" not in DEFAULT_TOOLBAR_IDS


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
#: A stand-in "every live command" set. `file.save` is deliberately NOT in it
#: any more (FQ-020 deleted that command), which is what makes the
#: pinned-Save-degradation test below a real assertion rather than a tautology.
_KNOWN = [
    "file.open",
    "deployment.save-pgtp",
    "history.undo",
    "history.redo",
]


def test_valid_ids_preserves_order_drops_unknowns():
    assert valid_ids(
        ["deployment.save-pgtp", "file.open", "bogus", "history.undo"], _KNOWN
    ) == ["deployment.save-pgtp", "file.open", "history.undo"]


def test_valid_ids_drops_duplicates_keeping_first():
    assert valid_ids(
        [
            "deployment.save-pgtp",
            "deployment.save-pgtp",
            "file.open",
            "file.open",
        ],
        _KNOWN,
    ) == ["deployment.save-pgtp", "file.open"]


def test_valid_ids_empty_and_all_unknown():
    assert valid_ids([], _KNOWN) == []
    assert valid_ids(None, _KNOWN) == []
    assert valid_ids(["x", "y"], _KNOWN) == []


def test_resolve_ids_maps_legacy_ids_so_saved_toolbars_survive():
    """The back-compat guarantee: a toolbar saved before BUG-027 stored
    `undo`/`redo`, which are unknown under the new scheme -- without aliasing
    every existing user's toolbar would silently empty on first launch."""
    assert resolve_ids(["undo", "redo"], _KNOWN) == ["history.undo", "history.redo"]
    # ...and the RETIRED `find` alias resolves to nothing rather than to a
    # dangling id (FQ-016): a pre-FQ-016 saved toolbar simply loses that button.
    assert resolve_ids(["find"], _KNOWN + ["edit.find"]) == []


def test_a_pinned_save_button_is_silently_dropped_not_left_dead():
    """FQ-020's stated degradation for a user who had pinned Save, verified
    rather than assumed: with `File ▸ Save` deleted, both spellings of that id
    resolve to NOTHING -- the button simply disappears on load. No dead button,
    no empty-and-iconless button, no error. The neighbours around it survive, so
    the drop is one button rather than a reset to the default toolbar."""
    assert resolve_ids(["save"], _KNOWN) == []
    # The post-BUG-027 menu-path spelling of the same command, which is what a
    # more recently saved toolbar holds.
    assert resolve_ids(["file.save"], _KNOWN) == []
    # The neighbours around the dropped id survive, so the user loses one button
    # rather than having their toolbar reset.
    assert resolve_ids(["file.open", "save", "undo"], _KNOWN) == [
        "file.open",
        "history.undo",
    ]
    # `Save As…` went the same way, and deliberately gets no alias onto
    # `Deployment ▸ Save as new pgtp` either -- FQ-020 pins the degradation as a
    # silent drop, not a re-point.
    assert resolve_ids(["file.save-as"], _KNOWN) == []


def test_renamed_ids_are_never_inverted_into_the_icon_table():
    """FQ-022's reason for a SECOND table: `ICON_ID_BY_COMMAND` inverts
    `LEGACY_ID_ALIASES`, so a rename row there would hand `icon_id_for` a
    menu-path id where an icon id belongs -- a `KeyError` that
    `_set_action_icon`'s bare except swallows, permanently defeating any later
    default-icon binding for that command."""
    assert not set(RENAMED_ID_ALIASES) & set(LEGACY_ID_ALIASES)
    for old_id, new_id in RENAMED_ID_ALIASES.items():
        assert old_id not in ICON_ID_BY_COMMAND.values()
        assert new_id not in ICON_ID_BY_COMMAND


def test_resolve_ids_maps_a_renamed_menu_path_so_a_pinned_button_survives():
    """§18.7 renamed `Database ▸ DDL Explorer` to `DDL Explorer (Quality)` when
    it gained a sandbox-scoped sibling. The label IS the id, so without this row
    a user who had pinned the old button would silently lose it."""
    known = ["database.ddl-explorer-quality", "file.open"]
    assert resolve_ids(["database.ddl-explorer"], known) == [
        "database.ddl-explorer-quality"
    ]
    # And the two ids for the one command deduplicate, like the legacy pair does.
    assert resolve_ids(
        ["database.ddl-explorer", "database.ddl-explorer-quality"], known
    ) == ["database.ddl-explorer-quality"]


def test_resolve_ids_passes_through_new_ids_and_still_drops_unknowns():
    assert resolve_ids(["file.open", "nope"], _KNOWN) == ["file.open"]


def test_resolve_ids_deduplicates_a_legacy_and_new_id_for_the_same_command():
    assert resolve_ids(["undo", "history.undo"], _KNOWN) == ["history.undo"]


# -- FQ-004: per-command icon assignments (still pure/Qt-free) ---------------

from pgtp_editor.ui.toolbar_registry import (  # noqa: E402
    ICON_ASSIGNMENTS_SETTINGS_KEY,
    icon_id_for,
    parse_icon_assignments,
    resolve_icon_assignments,
    serialize_icon_assignments,
)

KNOWN_COMMANDS = ["file.open", "file.save", "file.save-as", "history.undo"]
KNOWN_ICONS = ["document-open", "document-save-as", "zoom-in"]


def test_settings_key_is_a_sibling_of_toolbar_ids():
    assert ICON_ASSIGNMENTS_SETTINGS_KEY == "toolbarIconIds"


def test_serialize_round_trips_through_parse():
    mapping = {"file.save-as": "document-save-as", "history.undo": "zoom-in"}
    stored = serialize_icon_assignments(mapping)
    assert stored == ["file.save-as=document-save-as", "history.undo=zoom-in"]
    assert parse_icon_assignments(stored) == mapping


def test_serialize_drops_empty_entries():
    assert serialize_icon_assignments({"": "x", "a": ""}) == []
    assert serialize_icon_assignments(None) == []


def test_parse_tolerates_qsettings_shapes():
    assert parse_icon_assignments(None) == {}
    assert parse_icon_assignments([]) == {}
    # QSettings collapses a one-element list to a bare string on some backends.
    assert parse_icon_assignments("file.open=zoom-in") == {"file.open": "zoom-in"}
    # An already-parsed dict passes through.
    assert parse_icon_assignments({"a": "b"}) == {"a": "b"}
    # Garbage entries are ignored, good ones survive.
    assert parse_icon_assignments(["junk", 7, "a=b"]) == {"a": "b"}


def test_resolve_drops_unknown_command_ids():
    resolved = resolve_icon_assignments(
        {"file.save-as": "zoom-in", "gone.command": "zoom-in"},
        KNOWN_COMMANDS,
        KNOWN_ICONS,
    )
    assert resolved == {"file.save-as": "zoom-in"}


def test_resolve_drops_no_longer_vendored_icons():
    resolved = resolve_icon_assignments(
        {"file.save-as": "was-removed-upstream"}, KNOWN_COMMANDS, KNOWN_ICONS
    )
    assert resolved == {}


def test_resolve_maps_legacy_command_ids_like_resolve_ids_does():
    resolved = resolve_icon_assignments(
        {"open": "zoom-in"}, KNOWN_COMMANDS, KNOWN_ICONS
    )
    assert resolved == {"file.open": "zoom-in"}


def test_resolve_icon_assignments_follows_a_rename_too():
    resolved = resolve_icon_assignments(
        {"database.ddl-explorer": "zoom-in"},
        ["database.ddl-explorer-quality"],
        KNOWN_ICONS,
    )
    assert resolved == {"database.ddl-explorer-quality": "zoom-in"}


def test_resolve_of_nothing_is_empty_back_compat():
    assert resolve_icon_assignments(None, KNOWN_COMMANDS, KNOWN_ICONS) == {}
    assert resolve_icon_assignments({}, KNOWN_COMMANDS, KNOWN_ICONS) == {}


def test_icon_id_for_falls_back_to_the_legacy_default():
    # Back-compat: with no assignments the legacy set keeps its icons and
    # everything else stays icon-less, exactly as before FQ-004.
    for command_id, legacy in ICON_ID_BY_COMMAND.items():
        assert icon_id_for(command_id, {}) == legacy
        assert icon_id_for(command_id, None) == legacy
    assert icon_id_for("file.save-as", {}) is None


def test_icon_id_for_assignment_overrides_a_legacy_default():
    assert icon_id_for("file.save", {"file.save": "zoom-in"}) == "zoom-in"


def test_icon_id_for_assignment_gives_an_iconless_command_an_icon():
    assert icon_id_for("file.save-as", {"file.save-as": "document-save-as"}) == (
        "document-save-as"
    )
