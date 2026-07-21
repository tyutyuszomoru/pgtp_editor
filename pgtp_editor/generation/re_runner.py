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

# pgtp_editor/generation/re_runner.py
"""Pure command builders for the re_phpgen CLI (panGen / rePHPgen actions).

Subprocess-boundary counterpart of runner.build_generate_command: pure
functions over paths, fully unit-testable; commands are executed by the same
injectable GeneratorRunner the vendor generation uses. The caller must run the
subprocess with cwd=<re_phpgen_root> and PYTHONPATH=<root>\\src so
`-m re_phpgen` resolves even without the package installed in the venv.

CLI exit codes (implemented in the re_phpgen repo's cli.py): 0 = ran fine
(diffs are data, not failure), 1 = pangen wrote 0 of >0 pages, 2 = operational
failure (bad project/paths, vendor==ours, IO errors).
"""
from __future__ import annotations

import sys
from pathlib import Path

PANGEN_SUBFOLDER = "_pangen"


def pangen_output_dir(output_folder: str) -> str:
    """Our generator's output: a sibling subfolder, so the manually generated
    vendor .php baseline in the output folder itself is never overwritten."""
    return str(Path(output_folder) / PANGEN_SUBFOLDER)


def resolve_re_phpgen_python(root: str) -> str:
    """The re_phpgen repo's venv python if present, else the editor's own."""
    venv_python = Path(root) / "venv" / "Scripts" / "python.exe"
    return str(venv_python) if venv_python.is_file() else sys.executable


def validate_re_phpgen_root(root: str) -> bool:
    """True when `root` looks like the re_phpgen repo (has src/re_phpgen)."""
    return (Path(root) / "src" / "re_phpgen").is_dir()


def build_pangen_command(python: str, pgtp_path: str, output_folder: str) -> list[str]:
    return [python, "-m", "re_phpgen", "pangen", pgtp_path,
            "--out", pangen_output_dir(output_folder)]


def build_analyze_command(python: str, pgtp_path: str,
                          output_folder: str, json_path: str) -> list[str]:
    return [python, "-m", "re_phpgen", "analyze", pgtp_path,
            "--vendor", output_folder,
            "--ours", pangen_output_dir(output_folder),
            "--json", json_path]
