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


def _apply_filters(rows, text_filter, unlabeled_only):
    """Re-run on every keystroke in the text filter box and every toggle
    of the "Show only unlabeled" checkbox. `text_filter` matches
    case-insensitively against `path` and `attribute` only — not `value`
    or `label` (see design spec §4.2: matching against values too would
    risk false-positive matches when a value string happens to contain
    the filter text). `unlabeled_only` keeps rows where `label == ""`.
    """
    lowered = text_filter.lower()
    result = []
    for row in rows:
        if lowered and lowered not in row["path"].lower() and lowered not in row["attribute"].lower():
            continue
        if unlabeled_only and row["label"] != "":
            continue
        result.append(row)
    return result
