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


def compare_block(source_node, target_node, path, node_kind, ambiguous=False) -> list[Difference]:
    """Compare a matched pair of nodes that share the Page/Detail shape
    (attrib, columns, events, details), emitting Difference records for:
    - attribute differences on this node itself
    - Column diffs (added/removed/changed), scoped to this parent pair
    - EventHandler diffs (added/removed/changed text), scoped to this parent pair
    - child Detail diffs (added/removed/changed), recursing into matched pairs

    `node_kind` is the caller's responsibility ("page" or "detail") since
    this helper itself is shape-agnostic. `ambiguous` is True when this pair
    itself was matched via the duplicate-(tableName, caption)-sibling
    positional-pairing fallback (see _compare_details) and propagates to
    every Difference record produced for this node and its descendants,
    since none of them can be trusted as confidently as an unambiguous match.
    """
    differences: list[Difference] = []
    differences.extend(
        _compare_attributes(source_node, target_node, path=path, node_kind=node_kind, ambiguous=ambiguous)
    )
    differences.extend(_compare_columns(source_node, target_node, path=path, ambiguous=ambiguous))
    differences.extend(_compare_events(source_node, target_node, path=path, ambiguous=ambiguous))
    differences.extend(_compare_details(source_node, target_node, path=path, ambiguous=ambiguous))
    return differences


def _detail_identity_key(detail) -> tuple[str | None, str | None]:
    return (detail.table_name, detail.attrib.get("caption"))


def _compare_attributes(source_node, target_node, path, node_kind, ambiguous=False) -> list[Difference]:
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
                    ambiguous=ambiguous,
                )
            )
    return differences


def _compare_columns(source_node, target_node, path, ambiguous=False) -> list[Difference]:
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
                    ambiguous=ambiguous,
                )
            )
        else:
            differences.extend(
                _compare_attributes(
                    source_column, target_column, path=column_path, node_kind="column", ambiguous=ambiguous
                )
            )
            for source_child, target_child, node_kind, tag_name in (
                (source_column.format, target_column.format, "format", "Format"),
                (source_column.lookup, target_column.lookup, "lookup", "Lookup"),
                (
                    source_column.view_properties,
                    target_column.view_properties,
                    "view_properties",
                    "ViewProperties",
                ),
                (
                    source_column.edit_properties,
                    target_column.edit_properties,
                    "edit_properties",
                    "EditProperties",
                ),
            ):
                differences.extend(
                    _compare_child_element(
                        source_child,
                        target_child,
                        path=column_path,
                        node_kind=node_kind,
                        tag_name=tag_name,
                        ambiguous=ambiguous,
                    )
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
                    ambiguous=ambiguous,
                )
            )

    return differences


def _compare_child_element(
    source_child, target_child, path, node_kind, tag_name, ambiguous=False
) -> list[Difference]:
    """Compare one optional sub-element slot (Format/Lookup/ViewProperties/
    EditProperties) of a matched column pair, bracket-per-bracket,
    value-per-value.

    `source_child`/`target_child` are each a ChildElement or None.
    `path` is the enclosing column's path; `node_kind` is the sub-element
    kind ("format"/"lookup"/"view_properties"/"edit_properties"); `tag_name`
    is the XML tag used as the trailing path segment ("Format" etc.).

    - present on source only -> one `added` record (whole ChildElement)
    - present on target only -> one `removed` record (whole ChildElement)
    - present on both        -> one `changed` record per differing attrib key
    - absent on both         -> nothing
    Mirrors _compare_attributes / _compare_columns exactly, threading
    `ambiguous`.
    """
    child_path = path + [tag_name]

    if source_child is not None and target_child is None:
        return [
            Difference(
                kind="added",
                path=child_path,
                node_kind=node_kind,
                attribute=None,
                old_value=None,
                new_value=source_child,
                ambiguous=ambiguous,
            )
        ]
    if source_child is None and target_child is not None:
        return [
            Difference(
                kind="removed",
                path=child_path,
                node_kind=node_kind,
                attribute=None,
                old_value=target_child,
                new_value=None,
                ambiguous=ambiguous,
            )
        ]
    if source_child is None and target_child is None:
        return []

    differences: list[Difference] = []
    all_keys = set(source_child.attrib.keys()) | set(target_child.attrib.keys())
    for key in sorted(all_keys):
        source_value = source_child.attrib.get(key)
        target_value = target_child.attrib.get(key)
        if source_value != target_value:
            differences.append(
                Difference(
                    kind="changed",
                    path=child_path,
                    node_kind=node_kind,
                    attribute=key,
                    old_value=target_value,
                    new_value=source_value,
                    ambiguous=ambiguous,
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


def _compare_events(source_node, target_node, path, ambiguous=False) -> list[Difference]:
    """Diff EventHandlers (children) of a matched Page/Detail pair, matched
    by base handler name (after suffix normalization), scoped to this
    parent pair only.

    Real sample data (see dev_Ferrara.pgtp's `r_jcop` page) can carry two
    distinct, legitimately-different sibling events whose tag names both
    normalize to the same base name (e.g. `CustomDrawRow` and
    `CustomDrawRow_SimpleHandler` both normalize to `CustomDrawRow`) --
    not a data error, just two handlers sharing a base name. A naive
    one-slot-per-base-name dict would silently collapse them and compare
    the wrong pair (discovered via the self-diff integration test: it
    produced a spurious Changed record when diffing a file against
    itself). This mirrors _compare_details' duplicate-sibling handling:
    group by base name, pair positionally within each group, and mark
    every record from a group of size > 1 on either side as ambiguous=True
    so it surfaces for manual review rather than being silently trusted.
    """
    differences: list[Difference] = []

    target_events_by_base_name: dict[str, list] = {}
    for target_event in target_node.events:
        target_events_by_base_name.setdefault(_event_base_name(target_event.tag_name), []).append(target_event)

    source_events_by_base_name: dict[str, list] = {}
    for source_event in source_node.events:
        source_events_by_base_name.setdefault(_event_base_name(source_event.tag_name), []).append(source_event)

    all_base_names = set(source_events_by_base_name.keys()) | set(target_events_by_base_name.keys())

    for base_name in all_base_names:
        source_group = source_events_by_base_name.get(base_name, [])
        target_group = target_events_by_base_name.get(base_name, [])
        group_is_ambiguous = ambiguous or len(source_group) > 1 or len(target_group) > 1

        for i in range(max(len(source_group), len(target_group))):
            source_event = source_group[i] if i < len(source_group) else None
            target_event = target_group[i] if i < len(target_group) else None

            if source_event is not None and target_event is not None:
                if source_event.text != target_event.text:
                    differences.append(
                        Difference(
                            kind="changed",
                            path=path + [source_event.tag_name],
                            node_kind="event",
                            attribute=None,
                            old_value=target_event.text,
                            new_value=source_event.text,
                            ambiguous=group_is_ambiguous,
                        )
                    )
            elif source_event is not None:
                differences.append(
                    Difference(
                        kind="added",
                        path=path + [source_event.tag_name],
                        node_kind="event",
                        attribute=None,
                        old_value=None,
                        new_value=source_event,
                        ambiguous=group_is_ambiguous,
                    )
                )
            else:
                differences.append(
                    Difference(
                        kind="removed",
                        path=path + [target_event.tag_name],
                        node_kind="event",
                        attribute=None,
                        old_value=target_event,
                        new_value=None,
                        ambiguous=group_is_ambiguous,
                    )
                )

    return differences


def _compare_details(source_node, target_node, path, ambiguous=False) -> list[Difference]:
    """Diff child Details of a matched Page/Detail pair, matched by
    (tableName, caption), scoped to this parent pair only. Recurses into
    matched pairs via compare_block.

    If more than one sibling Detail on either side shares the same
    (tableName, caption) key, the extras are paired positionally (1st extra
    with 1st extra, 2nd with 2nd, etc.) and every Difference record produced
    from that group -- including all descendants found via recursion -- is
    marked ambiguous=True, per the design spec's duplicate-sibling handling.
    A group of size 1 on both sides is the normal, unambiguous case and is
    not affected by the `ambiguous` flag introduced here (unless the caller
    itself already passed ambiguous=True, e.g. because this Detail pair is
    nested inside an outer ambiguous group).
    """
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
        group_is_ambiguous = ambiguous or len(source_group) > 1 or len(target_group) > 1

        for i in range(max(len(source_group), len(target_group))):
            source_detail = source_group[i] if i < len(source_group) else None
            target_detail = target_group[i] if i < len(target_group) else None
            detail_path = path + [f"{key[0]}/{key[1]}"]

            if source_detail is not None and target_detail is not None:
                differences.extend(
                    compare_block(
                        source_detail,
                        target_detail,
                        path=detail_path,
                        node_kind="detail",
                        ambiguous=group_is_ambiguous,
                    )
                )
            elif source_detail is not None:
                differences.append(
                    Difference(
                        kind="added",
                        path=detail_path,
                        node_kind="detail",
                        attribute=None,
                        old_value=None,
                        new_value=source_detail,
                        ambiguous=group_is_ambiguous,
                    )
                )
            else:
                differences.append(
                    Difference(
                        kind="removed",
                        path=detail_path,
                        node_kind="detail",
                        attribute=None,
                        old_value=target_detail,
                        new_value=None,
                        ambiguous=group_is_ambiguous,
                    )
                )

    return differences
