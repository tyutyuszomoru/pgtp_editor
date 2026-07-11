"""Regression tests: running the full file-level compare flow's underlying
logic (load_project twice + diff_project + DiffMergePanel.show_differences)
against a real sample file and itself must produce a change-list tree with
zero leaf nodes. Mirrors tests/diff/test_differ_integration.py's own
self-diff-is-empty pattern, exercised through the UI-facing code path.

Requires sample/*.pgtp to be present on disk (gitignored).
"""
from pathlib import Path

import pytest

from pgtp_editor.diff.differ import diff_project
from pgtp_editor.model.parser import load_project
from pgtp_editor.ui.diff_merge_panel import DiffMergePanel

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"


def _load_twice(filename):
    path = SAMPLE_DIR / filename
    if not path.exists():
        pytest.skip(f"sample fixture not present on disk: {path}")
    return load_project(path), load_project(path)


def test_dev_ferrara_self_compare_has_no_leaf_differences(qtbot):
    source, target = _load_twice("dev_Ferrara.pgtp")
    differences = diff_project(source, target)

    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    panel.show_differences(differences)

    assert panel._flattened_leaves() == []


def test_sdman_renco_strikes_back_self_compare_has_no_leaf_differences(qtbot):
    source, target = _load_twice("Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp")
    differences = diff_project(source, target)

    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    panel.show_differences(differences)

    assert panel._flattened_leaves() == []
