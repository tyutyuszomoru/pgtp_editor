# pgtp_editor/diff/apply.py
"""Applies checked Difference records to a Target ProjectModel's retained
real lxml tree. See
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md
§5 for the full per-kind/per-node_kind behavior this module implements.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    if diff.kind == "changed" and diff.attribute is not None:
        _apply_changed_attribute(target, diff)
    else:
        raise _ApplyError(f"unsupported difference (kind={diff.kind!r}, node_kind={diff.node_kind!r})")


def _apply_changed_attribute(target: ProjectModel, diff: Difference) -> None:
    if diff.node_kind not in ("page", "detail"):
        raise _ApplyError(f"attribute changes are only supported for page/detail in this task (got {diff.node_kind!r})")

    resolved = resolve_path(target, diff.path)
    if isinstance(resolved, ResolutionError):
        raise _ApplyError(resolved.message)

    element = resolved.element
    if diff.new_value is None:
        element.attrib.pop(diff.attribute, None)
    else:
        element.set(diff.attribute, diff.new_value)
