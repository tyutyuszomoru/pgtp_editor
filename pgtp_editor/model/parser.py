# pgtp_editor/model/parser.py
"""Parses a real .pgtp file (XML) into a ProjectModel using lxml.

This is the only module that touches lxml directly. UI code should only
ever read from the ProjectModel/PageNode/DetailNode/ColumnNode/EventNode
data objects in pgtp_editor.model.nodes.
"""
from __future__ import annotations

from lxml import etree

from pgtp_editor.model.nodes import (
    ColumnNode,
    DetailNode,
    EventNode,
    PageNode,
    ProjectModel,
    classify_event_side,
)


class PgtpParseError(Exception):
    """Raised when a .pgtp file cannot be parsed into a ProjectModel."""


def load_project(path) -> ProjectModel:
    """Parse the .pgtp file at `path` and return a ProjectModel.

    Raises PgtpParseError on malformed/unexpected XML so callers (e.g. the
    UI's File -> Open handler) can surface a clear error instead of letting
    an lxml exception bubble up uncaught or silently returning an empty
    project.
    """
    try:
        tree = etree.parse(str(path))
    except (etree.XMLSyntaxError, OSError) as exc:
        raise PgtpParseError(f"Could not parse '{path}': {exc}") from exc

    root = tree.getroot()

    try:
        pages_container = root.find("Presentation/Pages")
        page_elements = [] if pages_container is None else pages_container.findall("Page")
        pages = [_parse_page(page_el, parent_identity=None) for page_el in page_elements]
    except Exception as exc:  # defensive: any unexpected structural surprise
        raise PgtpParseError(f"Could not parse '{path}': {exc}") from exc

    return ProjectModel(pages=pages)


def _parse_page(page_el, parent_identity) -> PageNode:
    file_name = page_el.get("fileName", "") or ""
    identity = _make_identity(parent_identity, file_name)

    columns = _parse_columns(page_el, identity)
    events = _parse_events(page_el, identity)
    details = _parse_details(page_el, identity)

    return PageNode(
        identity=identity,
        attrib=dict(page_el.attrib),
        sourceline=page_el.sourceline,
        details=details,
        columns=columns,
        events=events,
    )


def _parse_details(page_el, parent_identity) -> list[DetailNode]:
    details_container = page_el.find("Details")
    if details_container is None:
        return []

    details = []
    for detail_el in details_container.findall("Detail"):
        details.append(_parse_detail(detail_el, parent_identity))
    return details


def _parse_detail(detail_el, parent_identity) -> DetailNode:
    inner_page_el = detail_el.find("Page")
    if inner_page_el is None:
        raise ValueError(f"Detail element (line {detail_el.sourceline}) has no nested Page")

    table_name = inner_page_el.get("tableName", "") or ""
    identity = _make_identity(parent_identity, table_name)

    columns = _parse_columns(inner_page_el, identity)
    events = _parse_events(inner_page_el, identity)
    nested_details = _parse_details(inner_page_el, identity)

    # Merge Detail's own attributes with the nested Page's attributes: the
    # nested Page carries the substantive data (tableName, caption, ability
    # modes, etc.) while Detail itself typically only carries a caption.
    merged_attrib = dict(detail_el.attrib)
    merged_attrib.update(inner_page_el.attrib)

    return DetailNode(
        identity=identity,
        attrib=merged_attrib,
        sourceline=detail_el.sourceline,
        inner_sourceline=inner_page_el.sourceline,
        details=nested_details,
        columns=columns,
        events=events,
    )


def _parse_columns(container_el, parent_identity) -> list[ColumnNode]:
    columns_container = container_el.find("ColumnPresentations")
    if columns_container is None:
        return []

    columns = []
    for col_el in columns_container.findall("ColumnPresentation"):
        field_name = col_el.get("fieldName", "") or ""
        identity = _make_identity(parent_identity, field_name)
        columns.append(
            ColumnNode(
                identity=identity,
                attrib=dict(col_el.attrib),
                sourceline=col_el.sourceline,
            )
        )
    return columns


def _parse_events(container_el, parent_identity) -> list[EventNode]:
    events_container = container_el.find("EventHandlers")
    if events_container is None:
        return []

    events = []
    for event_el in events_container:
        tag_name = event_el.tag
        identity = _make_identity(parent_identity, tag_name)
        events.append(
            EventNode(
                identity=identity,
                tag_name=tag_name,
                side=classify_event_side(tag_name),
                text=event_el.text or "",
                sourceline=event_el.sourceline,
            )
        )
    return events


def _make_identity(parent_identity, key_part) -> str:
    if parent_identity:
        return f"{parent_identity}/{key_part}"
    return key_part
