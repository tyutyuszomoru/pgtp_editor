"""Comparison algorithm: diff_project() walks two ProjectModel trees and
produces a flat list of Difference records. Pure logic — no Qt, no file I/O.

See docs/superpowers/specs/2026-07-12-pgtp-editor-differ-engine-design.md
for the full algorithm description.
"""
from __future__ import annotations

from pgtp_editor.model.nodes import ProjectModel
from pgtp_editor.diff.records import Difference


def diff_project(source: ProjectModel, target: ProjectModel) -> list[Difference]:
    differences: list[Difference] = []

    target_pages_by_file_name = {p.file_name: p for p in target.pages}
    source_file_names = {p.file_name for p in source.pages}

    for source_page in source.pages:
        target_page = target_pages_by_file_name.get(source_page.file_name)
        if target_page is None:
            differences.append(
                Difference(
                    kind="added",
                    path=[source_page.file_name],
                    node_kind="page",
                    attribute=None,
                    old_value=None,
                    new_value=source_page,
                )
            )
        else:
            differences.extend(
                compare_block(
                    source_page,
                    target_page,
                    path=[source_page.file_name],
                    node_kind="page",
                )
            )

    for target_page in target.pages:
        if target_page.file_name not in source_file_names:
            differences.append(
                Difference(
                    kind="removed",
                    path=[target_page.file_name],
                    node_kind="page",
                    attribute=None,
                    old_value=target_page,
                    new_value=None,
                )
            )

    return differences


def compare_block(source_node, target_node, path, node_kind) -> list[Difference]:
    """Compare a matched pair of nodes that share the Page/Detail shape
    (attrib, columns, events, details), emitting Difference records for:
    - attribute differences on this node itself
    - Column diffs (added/removed/changed), scoped to this parent pair
    - EventHandler diffs (added/removed/changed text), scoped to this parent pair
    - child Detail diffs (added/removed/changed), recursing into matched pairs

    `node_kind` is the caller's responsibility ("page" or "detail") since
    this helper itself is shape-agnostic.
    """
    differences: list[Difference] = []
    differences.extend(_compare_attributes(source_node, target_node, path=path, node_kind=node_kind))
    differences.extend(_compare_columns(source_node, target_node, path=path))
    differences.extend(_compare_events(source_node, target_node, path=path))
    differences.extend(_compare_details(source_node, target_node, path=path))
    return differences


def _detail_identity_key(detail) -> tuple:
    return (detail.table_name, detail.attrib.get("caption"))


def _compare_attributes(source_node, target_node, path, node_kind) -> list[Difference]:
    """Compare source_node.attrib vs target_node.attrib, emitting one
    Changed record per differing attribute key. Covers keys present on
    either side (a key missing on one side counts as differing from
    whatever value the other side has, defaulting the missing side to
    None)."""
    differences: list[Difference] = []
    all_keys = set(source_node.attrib.keys()) | set(target_node.attrib.keys())
    for key in sorted(all_keys):
        source_value = source_node.attrib.get(key)
        target_value = target_node.attrib.get(key)
        if source_value != target_value:
            differences.append(
                Difference(
                    kind="changed",
                    path=list(path),
                    node_kind=node_kind,
                    attribute=key,
                    old_value=target_value,
                    new_value=source_value,
                    ambiguous=False,
                )
            )
    return differences


def _compare_columns(source_node, target_node, path) -> list[Difference]:
    """Diff Columns (children) of a matched Page/Detail pair, matched by
    fieldName, scoped to this parent pair only."""
    differences: list[Difference] = []

    target_columns_by_field_name = {c.field_name: c for c in target_node.columns}
    source_field_names = {c.field_name for c in source_node.columns}

    for source_column in source_node.columns:
        target_column = target_columns_by_field_name.get(source_column.field_name)
        column_path = path + [source_column.field_name]
        if target_column is None:
            differences.append(
                Difference(
                    kind="added",
                    path=column_path,
                    node_kind="column",
                    attribute=None,
                    old_value=None,
                    new_value=source_column,
                )
            )
        else:
            differences.extend(
                _compare_attributes(source_column, target_column, path=column_path, node_kind="column")
            )

    for target_column in target_node.columns:
        if target_column.field_name not in source_field_names:
            differences.append(
                Difference(
                    kind="removed",
                    path=path + [target_column.field_name],
                    node_kind="column",
                    attribute=None,
                    old_value=target_column,
                    new_value=None,
                )
            )

    return differences


def _event_base_name(tag_name: str) -> str:
    """Strip the suffix-variant portion of an event tag name, matching
    the exact normalization rule in pgtp_editor.model.nodes.classify_event_side
    (split on the first underscore, keep the left side). Duplicated here as a
    one-line expression rather than imported, because classify_event_side
    itself returns "C"/"S", not the base name in isolation — see Task 6's
    note in the differ-engine plan for the rationale."""
    return tag_name.split("_", 1)[0]


def _compare_events(source_node, target_node, path) -> list[Difference]:
    """Diff EventHandlers (children) of a matched Page/Detail pair, matched
    by base handler name (after suffix normalization), scoped to this
    parent pair only."""
    differences: list[Difference] = []

    target_events_by_base_name = {_event_base_name(e.tag_name): e for e in target_node.events}
    source_base_names = {_event_base_name(e.tag_name) for e in source_node.events}

    for source_event in source_node.events:
        base_name = _event_base_name(source_event.tag_name)
        target_event = target_events_by_base_name.get(base_name)
        event_path = path + [source_event.tag_name]
        if target_event is None:
            differences.append(
                Difference(
                    kind="added",
                    path=event_path,
                    node_kind="event",
                    attribute=None,
                    old_value=None,
                    new_value=source_event,
                )
            )
        elif source_event.text != target_event.text:
            differences.append(
                Difference(
                    kind="changed",
                    path=event_path,
                    node_kind="event",
                    attribute=None,
                    old_value=target_event.text,
                    new_value=source_event.text,
                )
            )

    for target_event in target_node.events:
        base_name = _event_base_name(target_event.tag_name)
        if base_name not in source_base_names:
            differences.append(
                Difference(
                    kind="removed",
                    path=path + [target_event.tag_name],
                    node_kind="event",
                    attribute=None,
                    old_value=target_event,
                    new_value=None,
                )
            )

    return differences


def _compare_details(source_node, target_node, path) -> list[Difference]:
    """Diff child Details of a matched Page/Detail pair, matched by
    (tableName, caption), scoped to this parent pair only. Recurses into
    matched pairs via compare_block."""
    differences: list[Difference] = []

    target_details_by_key: dict[tuple, list] = {}
    for target_detail in target_node.details:
        target_details_by_key.setdefault(_detail_identity_key(target_detail), []).append(target_detail)

    source_details_by_key: dict[tuple, list] = {}
    for source_detail in source_node.details:
        source_details_by_key.setdefault(_detail_identity_key(source_detail), []).append(source_detail)

    all_keys = set(source_details_by_key.keys()) | set(target_details_by_key.keys())

    for key in all_keys:
        source_group = source_details_by_key.get(key, [])
        target_group = target_details_by_key.get(key, [])

        for i in range(max(len(source_group), len(target_group))):
            source_detail = source_group[i] if i < len(source_group) else None
            target_detail = target_group[i] if i < len(target_group) else None

            if source_detail is not None and target_detail is not None:
                detail_path = path + [f"{key[0]}/{key[1]}"]
                differences.extend(
                    compare_block(source_detail, target_detail, path=detail_path, node_kind="detail")
                )
            elif source_detail is not None:
                differences.append(
                    Difference(
                        kind="added",
                        path=path + [f"{key[0]}/{key[1]}"],
                        node_kind="detail",
                        attribute=None,
                        old_value=None,
                        new_value=source_detail,
                    )
                )
            else:
                differences.append(
                    Difference(
                        kind="removed",
                        path=path + [f"{key[0]}/{key[1]}"],
                        node_kind="detail",
                        attribute=None,
                        old_value=target_detail,
                        new_value=None,
                    )
                )

    return differences
