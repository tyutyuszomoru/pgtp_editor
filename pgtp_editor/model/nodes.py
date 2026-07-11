# pgtp_editor/model/nodes.py
"""Data classes for the parsed .pgtp project model.

These are plain data holders populated by `pgtp_editor.model.parser`.
Nothing here touches lxml directly — that's the parser's job.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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
class ColumnNode:
    identity: str
    attrib: dict
    sourceline: int | None = None

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


@dataclass
class DetailNode:
    identity: str
    attrib: dict
    sourceline: int | None = None
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
