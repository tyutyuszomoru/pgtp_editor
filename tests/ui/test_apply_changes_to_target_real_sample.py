"""End-to-end integration test for Apply Changes to Target against a real
sample .pgtp file, per
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md
§9's testing strategy: construct a small deliberate diff between two temp
copies of a real sample file, check some differences, Apply, and verify the
target file changed correctly and a .bak exists with the original content.
"""
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt

from pgtp_editor.model.parser import load_project
from pgtp_editor.ui.main_window import MainWindow

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"
SAMPLE_FILE = SAMPLE_DIR / "dev_Ferrara.pgtp"


def _require_sample():
    if not SAMPLE_FILE.exists():
        pytest.skip(f"sample file not present: {SAMPLE_FILE}")


def test_apply_changes_to_target_against_real_sample_file(qtbot, tmp_path):
    _require_sample()

    # Two independent temp copies: Source will be edited, Target stays as
    # a pristine copy of the real sample so Apply's mutation is checked
    # against a known-real-world XML shape.
    source_path = tmp_path / "source.pgtp"
    target_path = tmp_path / "target.pgtp"
    shutil.copy2(SAMPLE_FILE, source_path)
    shutil.copy2(SAMPLE_FILE, target_path)
    original_target_bytes = target_path.read_bytes()

    # Make one small, deliberate, unambiguous change in Source: alter the
    # first top-level Page's "caption" attribute.
    project = load_project(source_path)
    first_page = project.pages[0]
    original_caption = first_page.attrib.get("caption")
    new_caption = (original_caption or "") + " (edited by test)"
    first_page.element.set("caption", new_caption)
    from lxml import etree

    serialized = etree.tostring(
        project.tree, xml_declaration=False, encoding="UTF-8", pretty_print=False
    )
    source_path.write_bytes(serialized)

    window = MainWindow()
    qtbot.addWidget(window)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(str(source_path), ""), (str(target_path), "")],
    ):
        window._compare_merge_two_files()

    panel = window.center_stage.diff_merge_panel
    leaves = panel._flattened_leaves()
    caption_leaves = [
        leaf for leaf in leaves
        if leaf.data(0, Qt.ItemDataRole.UserRole).attribute == "caption"
        and leaf.data(0, Qt.ItemDataRole.UserRole).path == [first_page.file_name]
    ]
    assert len(caption_leaves) == 1
    caption_leaves[0].setCheckState(0, Qt.CheckState.Checked)

    with patch("pgtp_editor.ui.main_window.QMessageBox.information") as mock_info:
        window._apply_changes_to_target()

    mock_info.assert_called_once()

    bak_path = Path(str(target_path) + ".bak")
    assert bak_path.exists()
    assert bak_path.read_bytes() == original_target_bytes

    merged_project = load_project(target_path)
    merged_first_page = next(
        p for p in merged_project.pages if p.file_name == first_page.file_name
    )
    assert merged_first_page.attrib.get("caption") == new_caption
