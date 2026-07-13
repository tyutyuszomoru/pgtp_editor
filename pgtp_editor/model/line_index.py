# pgtp_editor/model/line_index.py
"""Resolve a 1-based source line number to the nearest enclosing model node.

Pure and Qt-free: operates only on the ProjectModel dataclasses in
pgtp_editor.model.nodes. Used by the editor->tree click-sync (MainWindow)
to turn an editor click position into the tree node to select.
"""
from __future__ import annotations

from dataclasses import dataclass

from pgtp_editor.model.nodes import ProjectModel


@dataclass
class _Entry:
    node: object          # PageNode | DetailNode | ColumnNode | EventNode
    depth: int
    start: int            # 1-based start line (node.sourceline)
    end: int | None       # 1-based inclusive end line; filled in a second pass


def _flatten(project: ProjectModel) -> list[_Entry]:
    """Walk the model in document order, emitting one _Entry per node with
    its depth and start line. Order within a container matches the tree's
    own display/emit order (nested Details, then Columns, then Events) — but
    correctness depends only on start lines being monotonic in document order,
    which they are because the parser reads them straight off lxml's
    document-order .sourceline. A Detail's range starts at its OUTER
    sourceline (the <Detail> open tag), never inner_sourceline."""
    entries: list[_Entry] = []

    def visit_container(node, depth: int) -> None:
        # A Page or Detail: its own children are details, columns, events.
        for detail in getattr(node, "details", []):
            entries.append(_Entry(detail, depth + 1, detail.sourceline, None))
            visit_container(detail, depth + 1)
        for column in getattr(node, "columns", []):
            entries.append(_Entry(column, depth + 1, column.sourceline, None))
        for event in getattr(node, "events", []):
            entries.append(_Entry(event, depth + 1, event.sourceline, None))

    for page in project.pages:
        entries.append(_Entry(page, 0, page.sourceline, None))
        visit_container(page, 0)

    # Drop any node whose start line is unknown (sourceline is None) — it
    # cannot participate in a line-range lookup. In practice sourceline is
    # always populated by the parser off a real lxml element.
    entries = [e for e in entries if e.start is not None]
    # Sort strictly by document position (start line). Ties should not occur
    # for distinct elements (each element opens on its own line in real
    # .pgtp files); a stable sort preserves emit order if they ever did.
    entries.sort(key=lambda e: e.start)
    return entries


def _assign_end_lines(entries: list[_Entry], total_lines: int | None = None) -> None:
    """Each entry's end line is one before the start of the next entry (in
    document order) at the SAME OR SHALLOWER depth — i.e. the next entry that
    is not a descendant of this one. The last such node runs to the end of
    the document (or, when unknown, to a large sentinel)."""
    n = len(entries)
    for i, entry in enumerate(entries):
        end = None
        for j in range(i + 1, n):
            if entries[j].depth <= entry.depth:
                end = entries[j].start - 1
                break
        if end is None:
            end = total_lines if total_lines is not None else 10**9
        entry.end = end


def node_at_line(project, line: int):
    """Return the deepest node whose [start, end] line range contains `line`,
    or None if `line` falls above the first node / outside any node's range
    (e.g. the file header or DataSources area the model does not cover)."""
    if project is None:
        return None
    entries = _flatten(project)
    _assign_end_lines(entries)
    # Deepest-first: among all entries whose range contains `line`, return the
    # one with the greatest depth. Because ranges of deeper nodes are nested
    # strictly inside their ancestors', the deepest containing entry is the
    # nearest enclosing node.
    best = None
    for entry in entries:
        if entry.start <= line <= entry.end:
            if best is None or entry.depth > best.depth:
                best = entry
    return best.node if best is not None else None
