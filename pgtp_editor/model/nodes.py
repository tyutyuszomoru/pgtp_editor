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

# pgtp_editor/model/nodes.py
"""Data classes for the parsed .pgtp project model.

These are plain data holders populated by `pgtp_editor.model.parser`.
Nothing here touches lxml directly — that's the parser's job.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lxml import etree

# Authoritative list of client-side event handler tag names, sourced from
# the phpgen GUI's own event-type list (see project memory:
# pgtp_event_handler_classification.md). Anything not in this set is
# classified server-side ("S").
CLIENT_SIDE_EVENT_NAMES = {
    "OnBeforePageLoad",
    "OnAfterPageLoad",
    "OnInsertFormLoaded",
    "OnEditFormLoaded",
    "OnInsertFormEditorValueChanged",
    "OnEditFormEditorValueChanged",
    "OnInsertFormValidate",
    "OnEditFormValidate",
    "OnCalculateControlValues",
}


def classify_event_side(tag_name: str) -> str:
    """Classify an event handler tag name as client ("C") or server ("S").

    Real sample files may have handler tags with an internal suffix variant
    (e.g. `CustomDrawRow_SimpleHandler`). Normalize by stripping any such
    suffix (everything from the first underscore onward) before matching
    against the canonical client-side list. Anything unrecognized defaults
    to server-side.
    """
    base_name = tag_name.split("_", 1)[0]
    return "C" if base_name in CLIENT_SIDE_EVENT_NAMES else "S"


@dataclass
class ChildElement:
    """A single-occurrence optional presentation child of a ColumnPresentation
    (one of <Format>, <Lookup>, <ViewProperties>, <EditProperties>).

    Holds only the child's own attributes plus a reference to the retained
    real lxml element (for future write-back). Does not descend into the
    child's own children: a <Format> nested inside a <ViewProperties> is
    captured separately as ColumnNode.format (see parser._parse_columns),
    not by walking into ColumnNode.view_properties.
    """
    attrib: dict
    sourceline: int | None = None
    element: "etree._Element | None" = None


@dataclass(frozen=True)
class RepresentationVisibility:
    """A column's visibility within one representation list of a Page's
    <Columns> block (List/View/Edit/Insert/QuickFilter/FilterBuilder/Print/
    Export/Compare/MultiEdit).

    visible:    True if shown, False if the entry carries visible="false",
                None if the column has no <Column> entry in this (present)
                representation ("not listed").
    sourceline: the <Column> entry's 1-based source line (for navigation);
                None when visible is None.
    """
    name: str
    visible: bool | None = None
    sourceline: int | None = None


@dataclass
class ColumnNode:
    identity: str
    attrib: dict
    sourceline: int | None = None
    element: "etree._Element | None" = None
    format: "ChildElement | None" = None
    lookup: "ChildElement | None" = None
    view_properties: "ChildElement | None" = None
    edit_properties: "ChildElement | None" = None
    representations: list["RepresentationVisibility"] = field(default_factory=list)

    @property
    def field_name(self) -> str | None:
        return self.attrib.get("fieldName")


@dataclass
class EventNode:
    identity: str
    tag_name: str
    side: str
    text: str
    sourceline: int | None = None
    element: "etree._Element | None" = None


@dataclass
class DetailNode:
    identity: str
    attrib: dict
    sourceline: int | None = None
    element: "etree._Element | None" = None
    inner_page_element: "etree._Element | None" = None
    inner_sourceline: int | None = None
    details: list["DetailNode"] = field(default_factory=list)
    columns: list[ColumnNode] = field(default_factory=list)
    events: list[EventNode] = field(default_factory=list)

    @property
    def table_name(self) -> str | None:
        return self.attrib.get("tableName")


@dataclass
class PageNode:
    identity: str
    attrib: dict
    sourceline: int | None = None
    element: "etree._Element | None" = None
    details: list[DetailNode] = field(default_factory=list)
    columns: list[ColumnNode] = field(default_factory=list)
    events: list[EventNode] = field(default_factory=list)

    @property
    def file_name(self) -> str | None:
        return self.attrib.get("fileName")

    @property
    def table_name(self) -> str | None:
        return self.attrib.get("tableName")


@dataclass
class ProjectModel:
    pages: list[PageNode] = field(default_factory=list)
    tree: "etree._ElementTree | None" = None
