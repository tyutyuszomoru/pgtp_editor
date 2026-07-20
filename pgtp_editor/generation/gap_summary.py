# pgtp_editor/generation/gap_summary.py
"""Human-readable summary of a re_phpgen gap JSON (for dialog/status display).

Pure module (no Qt). Never raises: any read/parse/shape problem comes back as
an error string the caller can display as-is.
"""
from __future__ import annotations

import json
from pathlib import Path


def summarize_gap_json(path: Path) -> str:
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        summary = report["summary"]
        lines = [
            f"{summary['pages']} pages: {summary['ok']} ok, {summary['diff']} diff, "
            f"{summary['missing_vendor'] + summary['missing_ours']} missing, "
            f"{summary['error']} error",
        ]
        causes = summary.get("causes") or {}
        if causes:
            ranked = sorted(causes.items(), key=lambda kv: -kv[1])
            lines.append("Diff causes: " + ", ".join(f"{k}: {v}" for k, v in ranked))
        if report.get("vendor_older_than_project"):
            lines.append(
                "WARNING: vendor output is older than the project file - "
                "regenerate it from the PHP Generator GUI."
            )
        return "\n".join(lines)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return f"Could not read gap JSON: {exc}"
