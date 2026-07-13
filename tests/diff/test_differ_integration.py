"""Regression tests: diffing a real sample file against itself must produce
an empty list. This is a strong sanity check that the algorithm doesn't
spuriously report differences from e.g. dict-ordering assumptions or
unstable duplicate-pairing, when there are none.

Also guards the Interface Text Collection sub-project 1 addition: since the
real samples are dense with Format/Lookup/ViewProperties/EditProperties
sub-elements, a self-diff staying empty proves _compare_child_element does
not spuriously fire (e.g. by comparing a present-on-both sub-element as
changed, or crossing Format against ViewProperties). See
docs/superpowers/specs/2026-07-13-pgtp-editor-column-subelements-design.md §5.5.

Requires sample/*.pgtp to be present on disk (gitignored — see Task 10 of
docs/superpowers/plans/2026-07-12-pgtp-editor-differ-engine.md for how to
populate it if missing).
"""
from pathlib import Path

import pytest

from pgtp_editor.model.parser import load_project
from pgtp_editor.diff.differ import diff_project

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"


def _load_twice(filename):
    path = SAMPLE_DIR / filename
    if not path.exists():
        pytest.skip(f"sample fixture not present on disk: {path}")
    return load_project(path), load_project(path)


def test_dev_ferrara_self_diff_is_empty():
    source, target = _load_twice("dev_Ferrara.pgtp")
    assert diff_project(source, target) == []


def test_sdman_renco_strikes_back_self_diff_is_empty():
    source, target = _load_twice("Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp")
    assert diff_project(source, target) == []
