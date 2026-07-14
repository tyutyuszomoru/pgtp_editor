"""Integration test running the schema-learning engine end-to-end against
the two real .pgtp sample files checked into this worktree's sample/
directory (gitignored, not tracked, but present on disk for local dev and
CI alike).

This drives walk_document + Model.merge_element directly — no UI, no
MainWindow — mirroring exactly what _enrich_schema_from_file does inside
pgtp_editor/ui/main_window.py.
"""
from pathlib import Path

import defusedxml.ElementTree as ET
import pytest

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.parser import walk_document
from pgtp_editor.schema_learning.xsd_gen import generate_xsd

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"
SAMPLE_FILES = [
    SAMPLE_DIR / "dev_Ferrara.pgtp",
    SAMPLE_DIR / "Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp",
]


def _require_samples():
    for path in SAMPLE_FILES:
        if not path.exists():
            pytest.skip(f"sample fixture not present: {path}")


def test_both_real_sample_files_merge_into_one_model_without_raising():
    _require_samples()

    model = Model()
    for path in SAMPLE_FILES:
        for elem_path, attrib, child_tag_counts, has_text in walk_document(str(path)):
            model.merge_element(elem_path, attrib, child_tag_counts, has_text)

    assert len(model.paths) > 10


def test_generated_xsd_from_real_samples_is_well_formed_xml():
    _require_samples()

    model = Model()
    for path in SAMPLE_FILES:
        for elem_path, attrib, child_tag_counts, has_text in walk_document(str(path)):
            model.merge_element(elem_path, attrib, child_tag_counts, has_text)

    xsd_text = generate_xsd(model)

    ET.fromstring(xsd_text)  # raises if malformed
