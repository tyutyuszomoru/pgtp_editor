# pgtp_editor/generation/runner.py
"""Invoke the SQL Maestro PostgreSQL PHP Generator CLI.

Two pieces:
- `build_generate_command`: a PURE function assembling the exact argument
  vector. This holds the load-bearing correctness and is fully unit-tested.
- `GeneratorRunner`: a thin QProcess wrapper (added in a later task) that runs
  the command asynchronously, streaming merged stdout/stderr line-by-line so
  the UI never freezes. It is injectable into MainWindow so tests use a fake
  and never spawn a real process.

The confirmed CLI shape is:
    PgPHPGeneratorPro.exe "<project.pgtp>" -output "<output-folder>" -generate
"""
from __future__ import annotations


def build_generate_command(executable: str, pgtp_path: str, output_folder: str) -> list[str]:
    """Return the argument vector for a non-interactive generation run.

    Returned as a list (not a shell string) so QProcess.start(program, args)
    handles quoting -- paths with spaces need no manual escaping here.
    """
    return [executable, pgtp_path, "-output", output_folder, "-generate"]
