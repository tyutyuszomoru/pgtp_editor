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

# pgtp_editor/diff/apply.py
"""Applies checked Difference records to a Target ProjectModel's retained
real lxml tree. See
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md
§5 for the full per-kind/per-node_kind behavior this module implements.
"""
from __future__ import annotations

import copy

from dataclasses import dataclass
from typing import Any

from lxml import etree

from pgtp_editor.diff.records import Difference
from pgtp_editor.diff.resolve import ResolutionError, resolve_path
from pgtp_editor.model.nodes import ProjectModel


@dataclass
class ApplyFailure:
    difference: Difference
    message: str


@dataclass
class ApplyResult:
    applied: list[Difference]
    failed: list[ApplyFailure]


def apply_differences(target: ProjectModel, differences: list[Difference]) -> ApplyResult:
    """Mutate target's retained lxml tree in place for each Difference in
    `differences` (already filtered to just the checked/Apply-selected
    ones by the caller -- see DiffMergePanel.checked_differences).

    This function applies whatever list it is handed -- it does not filter
    out ambiguous=True differences itself (that gate is main_window.py's
    responsibility) and it does not roll back partial mutations on failure
    (the caller is responsible for only serializing target.tree if
    ApplyResult.failed is empty, by operating on a disposable deep copy --
    see the design spec §7.3).
    """
    applied: list[Difference] = []
    failed: list[ApplyFailure] = []

    for diff in differences:
        try:
            _apply_one(target, diff)
        except _ApplyError as exc:
            failed.append(ApplyFailure(difference=diff, message=str(exc)))
        else:
            applied.append(diff)

    return ApplyResult(applied=applied, failed=failed)


class _ApplyError(Exception):
    """Internal-only: raised by _apply_one, caught by apply_differences."""


def _apply_one(target: ProjectModel, diff: Difference) -> None:
    if diff.kind == "added":
        _apply_added(target, diff)
    elif diff.kind == "removed":
        _apply_removed(diff)
    elif diff.kind == "changed" and diff.node_kind == "event" and diff.attribute is None:
        _apply_changed_event_text(target, diff)
    elif diff.kind == "changed" and diff.attribute is not None:
        _apply_changed_attribute(target, diff)
    else:
        raise _ApplyError(f"unsupported difference (kind={diff.kind!r}, node_kind={diff.node_kind!r})")


def _apply_added(target: ProjectModel, diff: Difference) -> None:
    if diff.node_kind == "page":
        _apply_added_page(target, diff)
    elif diff.node_kind == "detail":
        _apply_added_detail(target, diff)
    elif diff.node_kind == "column":
        _apply_added_column(target, diff)
    elif diff.node_kind == "event":
        _apply_added_event(target, diff)
    else:
        raise _ApplyError(f"unsupported node_kind for added: {diff.node_kind!r}")


def _apply_added_page(target: ProjectModel, diff: Difference) -> None:
    pages_container = target.tree.getroot().find("Presentation/Pages")
    if pages_container is None:
        raise _ApplyError("Target has no Presentation/Pages container to add a Page under")
    new_element = copy.deepcopy(diff.new_value.element)
    pages_container.append(new_element)


def _resolve_parent_for_add(target: ProjectModel, path: list[str]):
    parent_path = path[:-1]
    if not parent_path:
        raise _ApplyError("cannot add a top-level node without a parent path segment")
    parent_result = resolve_path(target, parent_path)
    if isinstance(parent_result, ResolutionError):
        raise _ApplyError(parent_result.message)
    return parent_result


def _container_element_for_parent(parent_node, container_tag: str):
    """The element a Detail/Column/Event child should be appended under is
    scoped to the parent's own substantive-data element: for a PageNode
    that's `.element` itself; for a DetailNode it's `.inner_page_element`
    (the nested <Page>, which is where _parse_columns/_parse_events/
    _parse_details already read children from -- see parser.py)."""
    host_element = getattr(parent_node, "inner_page_element", None) or parent_node.element
    container = host_element.find(container_tag)
    if container is None:
        container = etree.SubElement(host_element, container_tag)
    return container


def _apply_added_detail(target: ProjectModel, diff: Difference) -> None:
    parent_node = _resolve_parent_for_add(target, diff.path)
    details_container = _container_element_for_parent(parent_node, "Details")
    new_element = copy.deepcopy(diff.new_value.element)
    details_container.append(new_element)


def _apply_added_column(target: ProjectModel, diff: Difference) -> None:
    parent_node = _resolve_parent_for_add(target, diff.path)
    columns_container = _container_element_for_parent(parent_node, "ColumnPresentations")
    new_element = copy.deepcopy(diff.new_value.element)
    columns_container.append(new_element)


def _apply_added_event(target: ProjectModel, diff: Difference) -> None:
    parent_node = _resolve_parent_for_add(target, diff.path)
    events_container = _container_element_for_parent(parent_node, "EventHandlers")
    new_element = copy.deepcopy(diff.new_value.element)
    events_container.append(new_element)


def _apply_removed(diff: Difference) -> None:
    """A whole-subtree removed record: diff.old_value is itself the
    Target-side node carrying its own retained .element -- no resolve_path
    lookup is needed at all, since the node object *is* the thing to
    remove. For a Detail, removing the outer <Detail> element also removes
    everything nested under it (including the inner <Page>) in one call.
    """
    node = diff.old_value
    element = node.element
    parent = element.getparent()
    if parent is None:
        raise _ApplyError("cannot remove an element with no parent (already detached)")
    parent.remove(element)


def _apply_changed_attribute(target: ProjectModel, diff: Difference) -> None:
    if diff.node_kind in ("page", "detail"):
        resolved = resolve_path(target, diff.path)
        if isinstance(resolved, ResolutionError):
            raise _ApplyError(resolved.message)
        element = _target_element_for_attribute(resolved, diff.attribute)
    elif diff.node_kind == "column":
        element = _find_column_element(target, diff.path)
    else:
        raise _ApplyError(f"unsupported node_kind for attribute change: {diff.node_kind!r}")

    if diff.new_value is None:
        element.attrib.pop(diff.attribute, None)
    else:
        element.set(diff.attribute, diff.new_value)


def _find_column_element(target: ProjectModel, path: list[str]):
    parent_result = resolve_path(target, path[:-1])
    if isinstance(parent_result, ResolutionError):
        raise _ApplyError(parent_result.message)

    field_name = path[-1]
    match = next((c for c in parent_result.columns if c.field_name == field_name), None)
    if match is None:
        raise _ApplyError(f"no Column with fieldName '{field_name}' under {'/'.join(path[:-1])}")
    return match.element


def _find_event_element(target: ProjectModel, path: list[str]):
    parent_result = resolve_path(target, path[:-1])
    if isinstance(parent_result, ResolutionError):
        raise _ApplyError(parent_result.message)

    tag_name = path[-1]
    match = next((e for e in parent_result.events if e.tag_name == tag_name), None)
    if match is None:
        raise _ApplyError(f"no Event with tag_name '{tag_name}' under {'/'.join(path[:-1])}")
    return match.element


def _apply_changed_event_text(target: ProjectModel, diff: Difference) -> None:
    element = _find_event_element(target, diff.path)
    element.text = diff.new_value


def _target_element_for_attribute(resolved, attribute: str):
    """Return the real lxml element a given attribute key should be
    mutated on. A PageNode/ColumnNode/EventNode has exactly one real
    element. A DetailNode has two (the outer <Detail> and the nested
    <Page>) -- per spec §5.1, prefer whichever real element already
    carries that attribute key, checking inner_page_element first (since
    _parse_detail's merge order lets the nested Page's own attributes win
    in the merged view), and defaulting to inner_page_element (the
    substantive-data element) if the key exists on neither yet.
    """
    if getattr(resolved, "inner_page_element", None) is None:
        return resolved.element

    if attribute in resolved.inner_page_element.attrib:
        return resolved.inner_page_element
    if attribute in resolved.element.attrib:
        return resolved.element
    return resolved.inner_page_element
