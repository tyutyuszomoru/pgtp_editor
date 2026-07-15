"""Pure, Qt-light registry of customizable toolbar commands (Sub-project E).

Data-only so it can be unit-tested without a QApplication. The main window
maps these stable ids to real QActions/slots; the Customize dialog uses the
same id->label pairs. Keep this module free of Qt imports.
"""

# Ordered list of (stable-id, label) for every command the toolbar can host.
AVAILABLE_COMMANDS: list[tuple[str, str]] = [
    ("open", "Open"),
    ("save", "Save"),
    ("undo", "Undo"),
    ("redo", "Redo"),
    ("find", "Find"),
    ("validate", "Validate"),
    ("generate", "Generate"),
]

# The default toolbar layout: all commands, in registry order.
DEFAULT_TOOLBAR_IDS: list[str] = [cid for cid, _label in AVAILABLE_COMMANDS]

_LABELS: dict[str, str] = {cid: label for cid, label in AVAILABLE_COMMANDS}


def available_ids() -> list[str]:
    """All known command ids in registry order."""
    return [cid for cid, _label in AVAILABLE_COMMANDS]


def label_for(command_id: str) -> str | None:
    """Human label for a command id, or None if unknown."""
    return _LABELS.get(command_id)


def valid_ids(ids) -> list[str]:
    """Filter `ids` to known commands, preserving order and dropping unknowns
    and duplicates (keeping the first occurrence)."""
    seen: set[str] = set()
    result: list[str] = []
    for cid in ids or []:
        if cid in _LABELS and cid not in seen:
            seen.add(cid)
            result.append(cid)
    return result
