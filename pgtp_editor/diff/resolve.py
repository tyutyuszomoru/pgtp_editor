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
