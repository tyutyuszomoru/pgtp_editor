# pgtp_editor/generation/type_map.py
"""Declarative parity rules for synthesizing a <Page>/<Detail>/<Lookup> from a
DB table — the single source of truth for "what attributes does PHP Generator
emit for a new table".

Pure data + tiny helpers. No lxml, no Qt, no I/O. `from_table.py` consumes this
to build elements; parity refinement is a data edit here, not code surgery.

Baseline values are derived from the observed sample corpus (see the design
spec, 2026-07-19-create-from-db-table-design.md). Byte-exact parity with a
freshly-added-table .pgtp is tuned by editing the maps below.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# -- filter-operator bitmask defaults (observed) ----------------------------
FILTER_OPERATORS_NUMERIC = "1573119"
FILTER_OPERATORS_STRING = "1589247"


# -- the 10 fixed representation lists, in order ----------------------------
REPRESENTATION_NAMES: list[str] = [
    "List",
    "View",
    "Edit",
    "Insert",
    "QuickFilter",
    "FilterBuilder",
    "Print",
    "Export",
    "Compare",
    "MultiEdit",
]

# Representations where a primary-key column is hidden by default.
PK_HIDDEN_IN: frozenset[str] = frozenset({"Edit", "Insert", "Compare", "MultiEdit"})


# -- page-level default attributes (observed dominant values) ---------------
# Order is load-bearing for serialization (matches sample opening tags). The
# identity attributes (type/tableName/fileName/caption/shortCaption/groupName)
# are supplied by the builder; these are the shared defaults.
PAGE_DEFAULTS: list[tuple[str, str]] = [
    ("numberByDataSource", "0"),
    ("addSeparator", "false"),
    ("horizontalFilterCondition", ""),
    ("recordsPerPage", "20"),
    ("NavigatorPosition", "3"),
    ("insertAbilityMode", "3"),
    ("viewAbilityMode", "3"),
    ("editAbilityMode", "2"),
    ("multiEditAbility", "3"),
    ("includeAllFieldsForMultiEditByDefault", "false"),
    ("deleteAbilityMode", "3"),
    ("copyAbilityMode", "3"),
    ("contentEncoding", "UTF-8"),
    ("exportAllRecordsAvailable", "31"),
    ("exportSelectedRecordsAvailable", "31"),
    ("exportSingleRecordFromGridAvailable", "0"),
    ("exportRecordFromViewFormAvailable", "31"),
    ("printAvailable", "13"),
    ("useActionImages", "true"),
    ("showKeyColumnsImagesInGridHeader", "false"),
]


@dataclass(frozen=True)
class ColumnPresentationSpec:
    """The parity shape for one column's <ColumnPresentation> body."""

    caption: str
    selected_filter_operators: str
    view_type: str  # ViewProperties/@type
    format_type: str | None  # ViewProperties/Format/@type, or None for no <Format>
    format_extra: dict[str, str]  # extra <Format> attributes (e.g. decimalSeparator)
    edit_type: str  # EditProperties/@type
    edit_extra: dict[str, str]  # extra <EditProperties> attributes (e.g. maxLength)


# -- pg data_type → editor/view rules ---------------------------------------
_NUMERIC_TYPES = {
    "smallint",
    "integer",
    "int",
    "int2",
    "int4",
    "int8",
    "bigint",
    "numeric",
    "decimal",
    "real",
    "double precision",
    "double",
    "money",
    "serial",
    "bigserial",
}
_BOOLEAN_TYPES = {"boolean", "bool"}
_DATETIME_TYPES = {
    "date",
    "time",
    "time without time zone",
    "time with time zone",
    "timestamp",
    "timestamp without time zone",
    "timestamp with time zone",
    "timestamptz",
}


def _base_type(data_type: str) -> str:
    """Normalize a pg pretty type to its base name: lowercased, modifier and
    array suffix stripped. ``character varying(30)`` -> ``character varying``."""
    base = data_type.strip().lower()
    base = re.sub(r"\(.*?\)", "", base)  # drop (n) / (p,s) modifier
    base = base.replace("[]", "").strip()
    return base


def maxlength_of(data_type: str) -> str:
    """Extract the length modifier of a char/varchar type as a string, else "0".
    ``character varying(30)`` -> ``30``; ``text`` -> ``0``."""
    match = re.search(r"\((\d+)\)", data_type)
    if match and "char" in data_type.lower():
        return match.group(1)
    return "0"


def humanize(name: str) -> str:
    """Field/table name -> default caption: split on '_', title-case each word.
    ``objecttype_id`` -> ``Objecttype Id``; ``tag`` -> ``Tag``."""
    parts = [p for p in name.split("_") if p]
    if not parts:
        return name
    return " ".join(word[:1].upper() + word[1:] for word in parts)


def column_spec(name: str, data_type: str) -> ColumnPresentationSpec:
    """Map a column to its parity <ColumnPresentation> shape."""
    base = _base_type(data_type)
    caption = humanize(name)

    if base in _NUMERIC_TYPES:
        return ColumnPresentationSpec(
            caption=caption,
            selected_filter_operators=FILTER_OPERATORS_NUMERIC,
            view_type="text",
            format_type="number",
            format_extra={"decimalSeparator": "."},
            edit_type="textBox",
            edit_extra={"maxLength": "0"},
        )
    if base in _BOOLEAN_TYPES:
        return ColumnPresentationSpec(
            caption=caption,
            selected_filter_operators=FILTER_OPERATORS_NUMERIC,
            view_type="checkBox",
            format_type=None,
            format_extra={},
            edit_type="checkBox",
            edit_extra={},
        )
    if base in _DATETIME_TYPES:
        return ColumnPresentationSpec(
            caption=caption,
            selected_filter_operators=FILTER_OPERATORS_NUMERIC,
            view_type="text",
            format_type=None,
            format_extra={},
            edit_type="date",
            edit_extra={},
        )
    # char/varchar/text and everything unknown -> string textBox
    return ColumnPresentationSpec(
        caption=caption,
        selected_filter_operators=FILTER_OPERATORS_STRING,
        view_type="text",
        format_type=None,
        format_extra={},
        edit_type="textBox",
        edit_extra={"maxLength": maxlength_of(data_type)},
    )
