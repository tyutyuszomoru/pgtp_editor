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
    matched_target_file_names: set[str] = set()

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
            matched_target_file_names.add(source_page.file_name)

    for target_page in target.pages:
        if target_page.file_name not in matched_target_file_names and target_page.file_name not in {
            p.file_name for p in source.pages
        }:
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
