"""Real-sample smoke test for the caption scan/apply core.

Skips if the gitignored sample file is not present on disk (as in CI /
fresh worktrees). Qt-free -- exercises only the pure core against real data.
"""
from pathlib import Path

import pytest

from pgtp_editor.model.encoding import read_pgtp_text
from pgtp_editor.ui.caption_scan import CAPTION_ATTRIBUTES, apply_caption_edits, scan_captions

SAMPLE = Path(__file__).resolve().parents[2] / "sample" / "dev_Ferrara.pgtp"


def _require_sample():
    if not SAMPLE.exists():
        pytest.skip(f"sample fixture not present on disk: {SAMPLE}")


def test_scan_real_sample_finds_caption_rows():
    _require_sample()
    text = read_pgtp_text(str(SAMPLE))
    entries = scan_captions(text)
    assert entries, "expected at least one caption-like attribute in the sample"
    # Every emitted row names a known caption attribute and sits on a real line.
    for entry in entries:
        assert entry.attribute in CAPTION_ATTRIBUTES
        assert entry.line >= 1
        # The scanned value is exactly what sits (decoded) on that source line;
        # confirm the attribute name literally appears on the reported line.
        source_line = text.splitlines()[entry.line - 1]
        assert f"{entry.attribute}=" in source_line


def test_apply_then_rescan_reflects_change_on_real_sample():
    _require_sample()
    text = read_pgtp_text(str(SAMPLE))
    entries = scan_captions(text)
    target = entries[0]
    new_value = target.value + " [EDITED]"

    edited = apply_caption_edits(text, [(target, new_value)])
    rescanned = scan_captions(edited)

    # The same (line, attribute) row now carries the edited value, and the
    # edited text still parses (rescan is non-empty).
    assert rescanned, "edited text must still be well-formed and scan non-empty"
    match = next(
        e for e in rescanned if e.line == target.line and e.attribute == target.attribute
    )
    assert match.value == new_value
