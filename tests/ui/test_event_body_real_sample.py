"""Real-sample smoke test for SP2's event-body scan. Skips if the sample is
not present in this checkout."""
from pathlib import Path

import pytest

from pgtp_editor.model.encoding import read_pgtp_text
from pgtp_editor.ui.event_body import event_body_line_ranges

SAMPLE = Path(__file__).resolve().parents[2] / "sample" / "dev_Ferrara.pgtp"


@pytest.mark.skipif(not SAMPLE.exists(), reason="dev_Ferrara.pgtp not present")
def test_real_sample_has_at_least_one_handler_with_body():
    text = read_pgtp_text(str(SAMPLE))
    ranges = event_body_line_ranges(text)
    assert any(r["body"].strip() for r in ranges), "no non-empty handler body found"
