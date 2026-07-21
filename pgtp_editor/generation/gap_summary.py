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
