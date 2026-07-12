"""resolve_path(project, path) walks a ProjectModel down a path of identity
segments (matching Difference.path's shape — see
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-viewer-ui-design.md
§3.3-3.4) to find the PageNode/DetailNode a Detail-level comparison request
is pointing at. Pure logic — no Qt, mirrors differ.py's own per-level
matching rules rather than re-deriving them.
"""
from __future__ import annotations

from dataclasses import dataclass

from pgtp_editor.model.nodes import DetailNode, PageNode, ProjectModel


@dataclass
class ResolutionError:
    segment_index: int
    message: str


def resolve_path(project: ProjectModel, path: list[str]) -> "PageNode | DetailNode | ResolutionError":
    """Walk `project` down `path` (a list of identity segments matching
    Difference.path's shape, per spec §3.3): path[0] is a top-level Page's
    file_name, path[1:] are "tableName/caption" Detail segments each scoped
    to their immediate parent's .details only.

    Returns the resolved PageNode (len(path) == 1) or DetailNode
    (otherwise) on success, or a ResolutionError naming the first
    unresolvable segment on failure.
    """
    page = next((p for p in project.pages if p.file_name == path[0]), None)
    if page is None:
        return ResolutionError(
            segment_index=0,
            message=f"no Page named '{path[0]}'",
        )

    current = page
    for index, segment in enumerate(path[1:], start=1):
        table_name, _, caption = segment.partition("/")
        match = next(
            (
                d for d in current.details
                if d.table_name == table_name and d.attrib.get("caption") == caption
            ),
            None,
        )
        if match is None:
            resolved_prefix = "/".join(path[:index])
            return ResolutionError(
                segment_index=index,
                message=(
                    f"no Detail matching (tableName='{table_name}', caption='{caption}') "
                    f"under {resolved_prefix}"
                ),
            )
        current = match

    return current
