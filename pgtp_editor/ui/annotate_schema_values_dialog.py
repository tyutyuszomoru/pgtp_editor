"""AnnotateSchemaValuesDialog: lets a person browse every learned
(path, attribute, value) triple in the shared per-user schema model
(pgtp_editor.schema_learning.model.Model) and attach a human-readable
label to each observed value. See
docs/superpowers/specs/2026-07-12-pgtp-editor-annotate-schema-values-ui-design.md.

This module only ever reads/writes the `labels` dict on each attribute
entry — it never touches `values`, `type`, `overflowed`, or
`attr_seen_count`, which are owned by the Schema Learning Engine
sub-project (pgtp_editor/schema_learning/model.py).
"""
from __future__ import annotations


def _build_rows(model):
    """Flattens `model.paths` into one row per labelable (path, attribute,
    value) triple. A row is only generated for an attribute entry that is
    still a genuine enum candidate (`overflowed is False` and `values` is
    a non-empty list) and whose `type` is not `"boolean"` (see design spec
    §3.5 for the reasoning behind both exclusions).
    """
    rows = []
    for path in sorted(model.paths):
        attributes = model.paths[path]["attributes"]
        for attr_name in sorted(attributes):
            entry = attributes[attr_name]
            if entry["overflowed"] or not entry["values"]:
                continue
            if entry["type"] == "boolean":
                continue
            labels = entry.get("labels", {})
            for value in sorted(entry["values"]):
                rows.append({
                    "path": path,
                    "attribute": attr_name,
                    "value": value,
                    "label": labels.get(value, ""),
                })
    return rows
