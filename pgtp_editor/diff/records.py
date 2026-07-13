"""The `Difference` record shape emitted by `pgtp_editor.diff.differ`.

Pure data holder, no logic. Mirrors the model layer's own `@dataclass`
style (see `pgtp_editor/model/nodes.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Difference:
    kind: str  # "added" | "removed" | "changed"
    path: list[str]
    node_kind: str  # "page" | "detail" | "column" | "event"
    #                | "format" | "lookup" | "view_properties" | "edit_properties"
    attribute: str | None
    old_value: Any
    new_value: Any
    ambiguous: bool = False
