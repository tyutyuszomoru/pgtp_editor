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
            path = [source_page.file_name]
            differences.extend(
                _compare_attributes(source_page, target_page, path=path, node_kind="page")
            )
            differences.extend(_compare_columns(source_page, target_page, path=path))

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
