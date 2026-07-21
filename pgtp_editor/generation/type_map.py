# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# pgtp_editor/generation/type_map.py
"""Declarative parity rules for synthesizing a <Page>/<Detail>/<Lookup> from a
DB table — the single source of truth for "what attributes does PHP Generator
emit for a new table".

Pure data + tiny helpers. No lxml, no Qt, no I/O. `from_table.py` consumes this
to build elements; parity refinement is a data edit here, not code surgery.

Values are calibrated against a REAL clean-defaults capture
(tests/generation/fixtures/golden_newtable_1.*): a table added to PHP Generator
with no manual edits. That fixture is the parity oracle; keep these rules in sync
with it. Behaviors not represented there (date/time editors) are best-effort and
marked UNVERIFIED.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# -- filter-operator bitmask defaults (observed) ----------------------------
FILTER_OPERATORS_NUMERIC = "1573119"
FILTER_OPERATORS_STRING = "1589247"
FILTER_OPERATORS_BOOLEAN = "1572867"

# Default fractional digits for a numeric column with no explicit scale.
DEFAULT_NUMBER_AFTER_DECIMAL = "4"


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

# Representations where a primary-key column is hidden by default (confirmed by
# the golden_newtable_1 clean capture).
PK_HIDDEN_IN: frozenset[str] = frozenset({"Edit", "Insert", "Compare", "MultiEdit"})


# -- page-level default attributes (from the golden_newtable_1 capture) ------
# Order is load-bearing for serialization. The identity attributes
# (type/tableName/numberByDataSource/fileName/caption/shortCaption) are supplied
# by the builder in that order — numberByDataSource sits right after tableName in
# real PHP Generator output — so they are NOT in this list; these are the shared
# defaults that follow shortCaption.
PAGE_DEFAULTS: list[tuple[str, str]] = [
    ("addSeparator", "false"),
    ("horizontalFilterCondition", ""),
    ("recordsPerPage", "20"),
    ("NavigatorPosition", "3"),
    ("insertAbilityMode", "3"),
    ("viewAbilityMode", "3"),
    ("editAbilityMode", "3"),
    ("multiEditAbility", "3"),
    ("includeAllFieldsForMultiEditByDefault", "false"),
    ("deleteAbilityMode", "3"),
    ("copyAbilityMode", "3"),
    ("deleteSelectedAbilityMode", "3"),
    ("contentEncoding", "UTF-8"),
    ("exportAllRecordsAvailable", "31"),
    ("exportSelectedRecordsAvailable", "31"),
    ("exportSingleRecordFromGridAvailable", "0"),
    ("exportRecordFromViewFormAvailable", "31"),
    ("printAvailable", "13"),
    ("highlightRowOnMouseHover", "true"),
    ("useActionImages", "true"),
    ("showKeyColumnsImagesInGridHeader", "false"),
    ("condensedTable", "true"),
]


@dataclass(frozen=True)
class ColumnPresentationSpec:
    """The parity shape for one column's <ColumnPresentation> body. Nullability
    (canSetNull) is applied by the builder, not carried here, since it depends on
    the column not the type."""

    caption: str
    selected_filter_operators: str
    emit_show_column_filter_false: bool  # add showColumnFilter="false" (all but boolean)
    view_type: str  # ViewProperties/@type
    view_extra: dict[str, str]  # extra <ViewProperties> attrs (e.g. displayType)
    format_type: str | None  # ViewProperties/Format/@type, or None for no <Format>
    format_extra: dict[str, str]  # extra <Format> attrs (insertion order preserved)
    edit_type: str  # EditProperties/@type
    edit_extra: dict[str, str] = field(default_factory=dict)  # extra <EditProperties> attrs


# -- pg data_type sets -------------------------------------------------------
_INTEGER_TYPES = {
    "smallint",
    "integer",
    "int",
    "int2",
    "int4",
    "int8",
    "bigint",
    "serial",
    "bigserial",
    "smallserial",
    "serial2",
    "serial4",
    "serial8",
}
_DECIMAL_TYPES = {
    "numeric",
    "decimal",
    "real",
    "double precision",
    "double",
    "money",
    "float",
    "float4",
    "float8",
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
    ``character varying(30)`` -> ``30``; ``text`` -> ``0``; bare ``character
    varying`` -> ``0``."""
    match = re.search(r"\((\d+)\)", data_type)
    if match and "char" in data_type.lower():
        return match.group(1)
    return "0"


def numeric_scale(data_type: str) -> str:
    """Fractional digits for a numeric/decimal type. ``numeric(10,2)`` -> ``2``;
    bare ``numeric`` (no scale) -> the default (4), matching real phpgen output
    for an unscaled numeric column."""
    match = re.search(r"\(\s*\d+\s*,\s*(\d+)\s*\)", data_type)
    if match:
        return match.group(1)
    return DEFAULT_NUMBER_AFTER_DECIMAL


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

    if base in _INTEGER_TYPES:
        return ColumnPresentationSpec(
            caption=caption,
            selected_filter_operators=FILTER_OPERATORS_NUMERIC,
            emit_show_column_filter_false=True,
            view_type="text",
            view_extra={},
            format_type="number",
            format_extra={"thousandSeparator": ","},
            edit_type="textBox",
            edit_extra={"maxLength": "0"},
        )
    if base in _DECIMAL_TYPES:
        return ColumnPresentationSpec(
            caption=caption,
            selected_filter_operators=FILTER_OPERATORS_NUMERIC,
            emit_show_column_filter_false=True,
            view_type="text",
            view_extra={},
            format_type="number",
            format_extra={
                "numberAfterDecimal": numeric_scale(data_type),
                "decimalSeparator": ".",
                "thousandSeparator": ",",
            },
            edit_type="textBox",
            edit_extra={"maxLength": "0"},
        )
    if base in _BOOLEAN_TYPES:
        return ColumnPresentationSpec(
            caption=caption,
            selected_filter_operators=FILTER_OPERATORS_BOOLEAN,
            emit_show_column_filter_false=False,  # boolean keeps its column filter
            view_type="checkBox",
            view_extra={"displayType": "image"},
            format_type=None,
            format_extra={},
            edit_type="checkBox",
            edit_extra={},
        )
    if base in _DATETIME_TYPES:
        # UNVERIFIED against a real capture — best-effort.
        return ColumnPresentationSpec(
            caption=caption,
            selected_filter_operators=FILTER_OPERATORS_NUMERIC,
            emit_show_column_filter_false=True,
            view_type="text",
            view_extra={},
            format_type=None,
            format_extra={},
            edit_type="date",
            edit_extra={},
        )
    # char/varchar/text and everything unknown -> string textBox
    return ColumnPresentationSpec(
        caption=caption,
        selected_filter_operators=FILTER_OPERATORS_STRING,
        emit_show_column_filter_false=True,
        view_type="text",
        view_extra={},
        format_type=None,
        format_extra={},
        edit_type="textBox",
        edit_extra={"maxLength": maxlength_of(data_type)},
    )
