"""Real-sample smoke test for SP2's event-body scan. Skips if the sample is
not present in this checkout."""
from pathlib import Path

import pytest

from lxml import etree

from pgtp_editor.model.encoding import read_pgtp_text
from pgtp_editor.ui.event_body import event_body_line_ranges, insert_event_handler

SAMPLE = Path(__file__).resolve().parents[2] / "sample" / "dev_Ferrara.pgtp"


@pytest.mark.skipif(not SAMPLE.exists(), reason="dev_Ferrara.pgtp not present")
def test_real_sample_has_at_least_one_handler_with_body():
    text = read_pgtp_text(str(SAMPLE))
    ranges = event_body_line_ranges(text)
    assert any(r["body"].strip() for r in ranges), "no non-empty handler body found"


@pytest.mark.skipif(not SAMPLE.exists(), reason="dev_Ferrara.pgtp not present")
def test_real_sample_insert_into_first_page_reparses():
    """Smoke: inserting a handler into the first <Page> of the real sample
    produces re-parseable XML with the new handler present."""
    text = read_pgtp_text(str(SAMPLE))
    # Find the first <Page ...> open-tag line.
    page_line = None
    for i, line in enumerate(text.splitlines(), start=1):
        if "<Page" in line:
            page_line = i
            break
    assert page_line is not None, "no <Page> in the real sample"

    result = insert_event_handler(text, page_line, "OnAfterPageLoad", "console.log('x');")
    root = etree.fromstring(result.encode("utf-8"))
    assert root.find(".//OnAfterPageLoad") is not None
