# pgtp_editor/model/parser.py
"""Parses a real .pgtp file (XML) into a ProjectModel using lxml.

This is the only module that touches lxml directly. UI code should only
ever read from the ProjectModel/PageNode/DetailNode/ColumnNode/EventNode
data objects in pgtp_editor.model.nodes.
"""
from __future__ import annotations

import io

from lxml import etree

from pgtp_editor.model.encoding import read_pgtp_bytes
from pgtp_editor.model.nodes import (
    ChildElement,
    ColumnNode,
    DetailNode,
    EventNode,
    PageNode,
    ProjectModel,
    classify_event_side,
)


class PgtpParseError(Exception):
    """Raised when a .pgtp file cannot be parsed into a ProjectModel.

    `line` carries the 1-based line number of the failure when it is known
    (always known for an XML syntax error, via lxml's XMLSyntaxError.lineno;
    never known for a structurally-unexpected-but-well-formed document, since
    there is no single line at fault in that case).
    """

    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.line = line


def load_project(path) -> ProjectModel:
    """Parse the .pgtp file at `path` and return a ProjectModel.

    Raises PgtpParseError on malformed/unexpected XML so callers (e.g. the
    UI's File -> Open handler) can surface a clear error instead of letting
    an lxml exception bubble up uncaught or silently returning an empty
    project.

    Thin wrapper around `_build_project_model`, which does the actual
    element-walking and can also be called directly against an
    already-in-memory tree (e.g. a deep copy made during Apply — see
    pgtp_editor/diff/apply.py and MainWindow._apply_changes_to_target).
    """
    try:
        # Read bytes and repair CESU-8-encoded emoji (see model/encoding.py)
        # before handing to lxml, which otherwise rejects the lone surrogate
        # codepoints such files contain ("Char 0xD83D out of allowed range").
        data = read_pgtp_bytes(path)
        tree = etree.parse(io.BytesIO(data))
    except (etree.XMLSyntaxError, OSError) as exc:
        line = exc.lineno if isinstance(exc, etree.XMLSyntaxError) else None
        raise PgtpParseError(f"Could not parse '{path}': {exc}", line=line) from exc
    return _build_project_model(tree, source_description=str(path))


def load_project_from_text(text: str, source_description: str = "<editor>") -> ProjectModel:
    """Parse an in-memory .pgtp document `text` into a ProjectModel.

    The in-memory sibling of `load_project`: used by the Reparse action to
    feed the raw-XML editor's current contents back into the model without
    round-tripping through a file on disk. Shares `_build_project_model` and
    the same PgtpParseError/line-number handling as `load_project`.

    The text is already a Python str held in the editor, so CESU-8 repair
    (which operates on raw bytes off disk) does not apply — any astral-plane
    characters are already proper Python characters. Encode to UTF-8 bytes so
    lxml parses from a byte stream exactly as `load_project` does.
    """
    try:
        tree = etree.parse(io.BytesIO(text.encode("utf-8")))
    except etree.XMLSyntaxError as exc:
        raise PgtpParseError(
            f"Could not parse {source_description}: {exc}", line=exc.lineno
        ) from exc
    return _build_project_model(tree, source_description=source_description)


def _build_project_model(tree, source_description: str) -> ProjectModel:
    """Walk an already-parsed lxml tree and build a ProjectModel from it,
    retaining a reference to every real lxml element visited.

    Split out of `load_project` so the same walking logic can be re-run
    against an in-memory tree (e.g. a `copy.deepcopy` of a Target's tree
    made during Apply) without writing it to disk and reparsing it.
    """
    root = tree.getroot()

    try:
        pages_container = root.find("Presentation/Pages")
        page_elements = [] if pages_container is None else pages_container.findall("Page")
        pages = [_parse_page(page_el, parent_identity=None) for page_el in page_elements]
    except Exception as exc:  # defensive: any unexpected structural surprise
        raise PgtpParseError(f"Could not parse '{source_description}': {exc}") from exc

    return ProjectModel(pages=pages, tree=tree)


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
        element=page_el,
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
        element=detail_el,
        inner_page_element=inner_page_el,
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
                element=col_el,
                # <Format> is always nested inside <ViewProperties>, never a
                # direct child of <ColumnPresentation> -- see spec §3.2.
                format=_child_element(col_el.find("ViewProperties/Format")),
                lookup=_child_element(col_el.find("Lookup")),
                view_properties=_child_element(col_el.find("ViewProperties")),
                edit_properties=_child_element(col_el.find("EditProperties")),
            )
        )
    return columns


def _child_element(el):
    """Wrap an optional sub-element into a ChildElement, or None if absent.

    `el` is an lxml element or None (the result of an ElementTree.find).
    Absent sub-elements (find returned None) naturally leave the ColumnNode
    field at its None default.
    """
    if el is None:
        return None
    return ChildElement(attrib=dict(el.attrib), sourceline=el.sourceline, element=el)


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
                element=event_el,
            )
        )
    return events


def _make_identity(parent_identity, key_part) -> str:
    if parent_identity:
        return f"{parent_identity}/{key_part}"
    return key_part
