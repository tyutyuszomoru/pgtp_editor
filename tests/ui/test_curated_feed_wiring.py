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

"""Tests for the curated.xsd feeding pipeline on MainWindow: startup load,
bootstrap, and learned-only enrichment (spec §11).

These use MainWindow(schema_storage_dir=tmp_path) so the schema model/XSD
are written to an isolated per-test directory, never the real user's
AppData location.
"""
import pytest

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import (
    CURATED_BUNDLED_VERSION,
    bundled_curated_xsd_text,
    curated_xsd_path,
    learned_xsd_path,
    schema_model_path,
)
from pgtp_editor.ui import xsd_controller as xsd_controller_module
from pgtp_editor.ui.main_window import MainWindow


def _unseed(window):
    """Drop the curated.xsd that MainWindow.__init__ seeds from the bundled
    resource, plus the live schema, so a test can exercise a clean slate."""
    path = curated_xsd_path(window._schema_storage_dir)
    if path.exists():
        path.unlink()
    window._xsd_ui.curated_schema = None

_CURATED = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Root" type="Root_Type"/>
  <xs:complexType name="Root_Type">
    <xs:attribute name="phpDriver" use="optional">
      <xs:simpleType><xs:restriction base="xs:integer">
        <xs:enumeration value="0" label="pdo"/>
      </xs:restriction></xs:simpleType>
    </xs:attribute>
  </xs:complexType>
</xs:schema>
"""


@pytest.fixture
def window(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    win = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(win)
    return win


def _seed_curated(window):
    path = curated_xsd_path(window._schema_storage_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_CURATED, encoding="utf-8")


def test_load_curated_schema_feeds_editor(window):
    _seed_curated(window)
    assert window._xsd_ui.load_curated() is True
    model = window.center_stage.xml_editor.schema_model()
    assert model.paths["Root"]["attributes"]["phpDriver"]["labels"] == {"0": "pdo"}


def test_malformed_curated_keeps_last_good(window):
    _seed_curated(window)
    window._xsd_ui.load_curated()
    curated_xsd_path(window._schema_storage_dir).write_text("<broken", encoding="utf-8")
    assert window._xsd_ui.load_curated() is False
    model = window.center_stage.xml_editor.schema_model()
    assert model is not None  # last good schema stayed live
    items = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any("Curated XSD has XML errors" in line for line in items)


def test_init_seeds_curated_from_bundled_and_audits_version(window):
    """MainWindow.__init__ runs the one-time bootstrap: with the app-bundled
    Curated v1.2 resource present, curated.xsd is seeded by copying it
    verbatim and an audit line names the bundled schema + version."""
    path = curated_xsd_path(window._schema_storage_dir)
    assert path.exists()
    assert path.read_text(encoding="utf-8") == bundled_curated_xsd_text()
    items = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any(
        "bundled" in line.lower() and CURATED_BUNDLED_VERSION in line for line in items
    )
    # and the seeded file feeds completion (curated schema is live)
    assert window._xsd_ui.curated_schema is not None


def test_bootstrap_seeds_from_bundled_when_curated_absent(window):
    _unseed(window)
    window._xsd_ui.ensure_bootstrap()
    path = curated_xsd_path(window._schema_storage_dir)
    assert path.exists()
    assert path.read_text(encoding="utf-8") == bundled_curated_xsd_text()


def test_bootstrap_is_noop_when_curated_exists(window):
    _seed_curated(window)  # a hand-owned curated.xsd already on disk
    before = curated_xsd_path(window._schema_storage_dir).read_text(encoding="utf-8")
    window._xsd_ui.ensure_bootstrap()
    after = curated_xsd_path(window._schema_storage_dir).read_text(encoding="utf-8")
    assert after == before  # never overwrites an existing curated.xsd


def test_bootstrap_falls_back_to_learned_model_when_no_bundled(window, monkeypatch):
    """When the bundled resource is unavailable but a learned schema_model.json
    exists, bootstrap still generates curated.xsd from that model (old path)."""
    _unseed(window)
    monkeypatch.setattr(xsd_controller_module, "bundled_curated_xsd_text", lambda: None)
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model_path = schema_model_path(window._schema_storage_dir)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(model_path)

    window._xsd_ui.ensure_bootstrap()

    text = curated_xsd_path(window._schema_storage_dir).read_text(encoding="utf-8")
    assert "<xs:schema" in text and 'name="a"' in text
    items = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any("Bootstrapped curated.xsd" in line for line in items)


def test_bootstrap_noop_when_no_bundled_and_no_model(window, monkeypatch):
    _unseed(window)
    monkeypatch.setattr(xsd_controller_module, "bundled_curated_xsd_text", lambda: None)
    assert not schema_model_path(window._schema_storage_dir).exists()
    window._xsd_ui.ensure_bootstrap()
    assert not curated_xsd_path(window._schema_storage_dir).exists()


def test_enrichment_writes_learned_only_and_keeps_curated_feed(window, tmp_path):
    _seed_curated(window)
    window._xsd_ui.load_curated()
    sample = tmp_path / "sample.pgtp"
    sample.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<PGTPProject><New thing="x"/></PGTPProject>',
        encoding="utf-8",
    )
    window._xsd_ui.enrich_from_file(str(sample))
    assert learned_xsd_path(window._schema_storage_dir).exists()
    # completion feed still the curated model — learned attrs are NOT offered
    model = window.center_stage.xml_editor.schema_model()
    assert "PGTPProject/New" not in model.paths


def test_first_run_enrichment_bootstraps_and_feeds_editor(window, tmp_path, monkeypatch):
    """End-to-end first run with NO bundled resource available: no curated.xsd
    and no learned model exist yet. Enriching from an opened project must learn
    the model, bootstrap curated.xsd from it (one-time seed via the learned
    fallback path), and feed the editor's completion model from that fresh
    curated.xsd (spec §11)."""
    monkeypatch.setattr(xsd_controller_module, "bundled_curated_xsd_text", lambda: None)
    _unseed(window)
    assert not curated_xsd_path(window._schema_storage_dir).exists()
    assert not schema_model_path(window._schema_storage_dir).exists()
    assert window._xsd_ui.curated_schema is None

    sample = tmp_path / "sample.pgtp"
    sample.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<PGTPProject phpDriver="0"><Page name="orders"/></PGTPProject>',
        encoding="utf-8",
    )
    window._xsd_ui.enrich_from_file(str(sample))

    # bootstrap fired: curated.xsd now exists, seeded from the learned model
    curated = curated_xsd_path(window._schema_storage_dir)
    assert curated.exists()
    assert "<xs:schema" in curated.read_text(encoding="utf-8")
    items = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any("Bootstrapped curated.xsd" in line for line in items)

    # and the editor got fed from it — completion knows the learned structure
    assert window._xsd_ui.curated_schema is not None
    model = window.center_stage.xml_editor.schema_model()
    assert "phpDriver" in model.paths["PGTPProject"]["attributes"]
    assert "PGTPProject/Page" in model.paths


def test_second_enrichment_does_not_replace_live_curated_schema(window, tmp_path):
    """Once a curated schema is live, enrichment only writes learned.xsd —
    it never re-feeds the editor (curated.xsd is the exclusive source and is
    only re-parsed on save/import)."""
    _seed_curated(window)
    window._xsd_ui.load_curated()
    schema_before = window._xsd_ui.curated_schema

    sample = tmp_path / "sample.pgtp"
    sample.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<PGTPProject><Fresh attr="1"/></PGTPProject>',
        encoding="utf-8",
    )
    window._xsd_ui.enrich_from_file(str(sample))

    assert window._xsd_ui.curated_schema is schema_before
