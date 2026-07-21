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

"""Tier-2 structural-sanity validation for PGTP projects.

Qt-free, pure-lxml. Runs a small set of deliberately low-false-positive
structural checks over an open project and returns a flat list of
`ValidationIssue`s ordered by source line. Consumed on demand by the
Tools -> Validate Project action, which renders each issue into the Audit
panel (click-to-navigate via the issue's line).

Three checks (see the design doc):
  1. Duplicate ``Page@fileName`` (ERROR) -- the one hard rule. Every
     top-level ``<Page>`` (a direct child of ``<Pages>``) with a non-empty
     ``fileName`` must be unique; each colliding ``<Page>`` is reported so all
     locations are visible. Nested ``<Detail>`` pages legitimately reuse their
     master page's ``fileName`` and are excluded.
  2. Missing required attributes (WARNING) -- a top-level ``<Page>`` (direct
     child of ``<Pages>``) missing/empty ``fileName`` or ``tableName``; every
     ``<ColumnPresentation>`` missing/empty ``fieldName``.
  3. Unexpected child of a known container (WARNING) -- ``<Pages>`` may only
     contain ``<Page>``; ``<Details>`` only ``<Detail>``;
     ``<ColumnPresentations>`` only ``<ColumnPresentation>``.
"""
from __future__ import annotations

from dataclasses import dataclass

# Known containers -> the single element tag they may legally contain.
_CONTAINER_ALLOWED_CHILD = {
    "Pages": "Page",
    "Details": "Detail",
    "ColumnPresentations": "ColumnPresentation",
}


@dataclass(frozen=True)
class ValidationIssue:
    """A single structural finding.

    severity: ``"error"`` or ``"warning"``.
    message:  human-readable description.
    line:     the offending element's lxml ``sourceline`` (for navigation),
              or ``None`` when no line is available.
    """

    severity: str
    message: str
    line: int | None = None


def _is_element(node) -> bool:
    """True for real element nodes, False for comments / PIs.

    lxml comment and processing-instruction nodes have a *callable* ``.tag``;
    real elements have a ``str`` tag.
    """
    return isinstance(node.tag, str)


def _attr(element, name: str) -> str:
    """Return a stripped attribute value, treating absent/whitespace as empty."""
    return (element.get(name) or "").strip()


def validate_project(project) -> list[ValidationIssue]:
    """Run all Tier-2 checks and return issues ordered by source line.

    Returns ``[]`` for a falsy project or one whose ``tree`` is None.
    Issues are sorted by line (a stable sort preserving per-check emission
    order within a line); issues with ``line is None`` sort last.
    """
    if project is None or getattr(project, "tree", None) is None:
        return []
    root = project.tree.getroot()
    if root is None:
        return []

    issues: list[ValidationIssue] = []
    issues.extend(_check_duplicate_filenames(root))
    issues.extend(_check_missing_attrs(root))
    issues.extend(_check_unexpected_children(root))

    # Stable sort by line; None lines last. Python's sort is stable, so the
    # relative emission order of same-line issues is preserved.
    issues.sort(key=lambda i: (i.line is None, i.line if i.line is not None else 0))
    return issues


def _check_duplicate_filenames(root) -> list[ValidationIssue]:
    by_name: dict[str, list] = {}
    for page in root.iter("Page"):
        if not _is_element(page):
            continue
        # Only top-level pages (direct children of <Pages>) generate files, so
        # the uniqueness rule applies only to them. Nested <Detail> pages
        # legitimately reuse their master page's fileName.
        parent = page.getparent()
        if parent is None or parent.tag != "Pages":
            continue
        file_name = _attr(page, "fileName")
        if file_name:
            by_name.setdefault(file_name, []).append(page)

    issues: list[ValidationIssue] = []
    for file_name, elements in by_name.items():
        if len(elements) > 1:
            for element in elements:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        message=f'duplicate Page fileName "{file_name}"',
                        line=element.sourceline,
                    )
                )
    return issues


def _check_missing_attrs(root) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for element in root.iter():
        if not _is_element(element):
            continue
        tag = element.tag
        if tag == "Page":
            parent = element.getparent()
            if parent is not None and parent.tag == "Pages":
                if not _attr(element, "fileName"):
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            message="Page missing fileName",
                            line=element.sourceline,
                        )
                    )
                if not _attr(element, "tableName"):
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            message="Page missing tableName",
                            line=element.sourceline,
                        )
                    )
        elif tag == "ColumnPresentation":
            if not _attr(element, "fieldName"):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        message="ColumnPresentation missing fieldName",
                        line=element.sourceline,
                    )
                )
    return issues


def _check_unexpected_children(root) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for element in root.iter():
        if not _is_element(element):
            continue
        allowed = _CONTAINER_ALLOWED_CHILD.get(element.tag)
        if allowed is None:
            continue
        for child in element:
            if not _is_element(child):
                continue  # skip comments / PIs
            if child.tag != allowed:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        message=f"unexpected <{child.tag}> inside <{element.tag}>",
                        line=child.sourceline,
                    )
                )
    return issues
