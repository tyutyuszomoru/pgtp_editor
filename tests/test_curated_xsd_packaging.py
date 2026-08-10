"""Guards that the curated XSD the owner maintains is the one that ships (BUG-057).

Two things used to be able to drift apart silently:

1. **Curation vs. package.** The owner hand-curates the schema and saves dated
   snapshots as ``docs/curated_<YYYYMMDD>.xsd``. The file the app actually reads is
   ``pgtp_editor/resources/curated.xsd``. A newer curation that never got promoted
   into ``resources/`` simply had no effect -- nothing failed. The shape chosen
   instead of a build step nobody would remember: ``resources/curated.xsd`` is the
   single home (it is what ships and what the app loads), the newest dated snapshot
   in ``docs/`` is the owner's authoritative drop, and the two must be byte-identical.
   Promoting a new curation is therefore ``cp docs/curated_<date>.xsd
   pgtp_editor/resources/curated.xsd`` -- and forgetting it fails a test here.

2. **Package vs. release.** Both release channels include the file today (the wheel
   through ``[tool.setuptools.package-data]``, the PyInstaller bundle through the
   whole-folder ``--add-data``). The failure mode is asymmetric and silent, exactly
   like the QtSvg exclusion guarded in ``test_build_excludes.py``: with the resource
   missing, ``bundled_curated_xsd_text()`` returns ``None`` and the app quietly seeds
   a stub from the learned model instead of crashing, so completion/hover/Properties
   labels degrade without a single error. A future edit that drops ``resources/*.xsd``
   from package data, or renames the bundle destination, must fail here rather than
   in a release.

The curated file is deliberately NOT a W3C-valid schema (it carries custom ``hint``
and ``label`` attributes the app reads itself), so it is only ever parsed the way the
app parses it -- ``load_curated`` / ``verify_curated`` -- never via
``lxml.etree.XMLSchema``.
"""
import fnmatch
import importlib.util
import inspect
import re
import tomllib
from importlib import resources
from pathlib import Path

from pgtp_editor.schema_learning.settings_index import value_label
from pgtp_editor.schema_learning.storage import bundled_curated_xsd_text
from pgtp_editor.schema_learning.xsd_load import load_curated
from pgtp_editor.schema_learning.xsd_verify import verify_curated

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_CURATED = REPO_ROOT / "pgtp_editor" / "resources" / "curated.xsd"
SNAPSHOT_PATTERN = re.compile(r"^curated_(\d{8})\.xsd$")


def _dated_snapshots() -> list[Path]:
    """The owner's dated curation drops under ``docs/``, oldest first."""
    found = []
    for path in (REPO_ROOT / "docs").glob("curated_*.xsd"):
        match = SNAPSHOT_PATTERN.match(path.name)
        if match:
            found.append((match.group(1), path))
    return [path for _, path in sorted(found)]


def _load_build_module():
    spec = importlib.util.spec_from_file_location(
        "optimized_build", REPO_ROOT / "optimized_build.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_dated_curation_snapshot_is_tracked():
    # The snapshot used to be untracked, so `git clean` would have destroyed the
    # only copy of the newest curation. Guard that at least one exists and is not
    # empty -- git-tracking itself is what makes it survive.
    snapshots = _dated_snapshots()
    assert snapshots, (
        "No docs/curated_<YYYYMMDD>.xsd snapshot found. The owner's authoritative "
        "curation lives there and must be committed, not left untracked."
    )
    assert snapshots[-1].stat().st_size > 0


def test_shipped_curated_xsd_is_identical_to_the_newest_snapshot():
    newest = _dated_snapshots()[-1]
    assert SHIPPED_CURATED.read_bytes() == newest.read_bytes(), (
        f"{SHIPPED_CURATED.relative_to(REPO_ROOT)} differs from the newest curation "
        f"snapshot {newest.relative_to(REPO_ROOT)}. The snapshot is the owner's "
        f"authoritative curation and the resources file is what actually ships, so a "
        f"new snapshot must be promoted: copy it over "
        f"{SHIPPED_CURATED.relative_to(REPO_ROOT)} (and keep the "
        f"'<!-- PGTP Editor curated schema vX.Y -->' marker line in both)."
    )


def test_curated_xsd_is_covered_by_wheel_package_data():
    # The pip/wheel channel: setuptools only ships non-Python files listed here.
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    globs = pyproject["tool"]["setuptools"]["package-data"]["pgtp_editor"]
    assert any(fnmatch.fnmatch("resources/curated.xsd", pattern) for pattern in globs), (
        "No [tool.setuptools.package-data] glob for \"pgtp_editor\" matches "
        "resources/curated.xsd, so a wheel/pip install would omit the curated schema "
        f"and the app would silently fall back to a generated stub. Globs: {globs}"
    )


def test_curated_xsd_is_covered_by_the_frozen_bundle():
    # The PyInstaller/Inno channel: the whole resources folder is added under a
    # destination that must keep files("pgtp_editor") resolving inside the bundle.
    build = _load_build_module()
    assert build.RESOURCES_SRC == SHIPPED_CURATED.parent
    assert build.RESOURCES_DEST == "pgtp_editor/resources"
    assert "curated.xsd" in build.REQUIRED_RESOURCE_FILES
    src = inspect.getsource(build.build)
    assert "RESOURCES_SRC" in src
    assert "--add-data" in src
    assert "REQUIRED_RESOURCE_FILES" in src, (
        "optimized_build.build() no longer checks REQUIRED_RESOURCE_FILES, so a "
        "clean checkout missing curated.xsd would build a silently degraded bundle."
    )


def test_installed_layout_resolves_the_curated_xsd():
    # The resolver contract bundled_curated_xsd_text() depends on: the resource must
    # be reachable through files("pgtp_editor"), the same shape manual.md uses.
    resource = resources.files("pgtp_editor") / "resources" / "curated.xsd"
    assert resource.is_file()
    text = bundled_curated_xsd_text()
    assert text is not None
    assert "<!-- PGTP Editor curated schema v" in text


def test_shipped_curated_xsd_parses_the_way_the_app_parses_it():
    # Not a W3C-valid schema by design -- assert against the app's own loader and
    # verifier, so a broken curation can never reach a release.
    text = bundled_curated_xsd_text()
    schema = load_curated(text)
    assert schema.model.paths
    assert [issue.message for issue in verify_curated(text) if issue.fatal] == []


def test_shipped_curated_xsd_keeps_the_hand_authored_labels_and_hints():
    # The curated dialect's whole point: labels feed the Properties panel and hints
    # feed hover. A curation refresh that dropped them would parse fine and go
    # unnoticed, so assert both survive at a known path.
    text = bundled_curated_xsd_text()
    assert 'hint="' in text
    schema = load_curated(text)
    page = "Project/Presentation/Pages/Page"
    # Both *AbilityMode siblings must resolve (BUG-002 lost editAbilityMode once and
    # the 2026-08-07 curation had lost it again).
    assert value_label(schema.model, page, "editAbilityMode", "3") == "Modal window"
    assert value_label(schema.model, page, "viewAbilityMode", "3") == "Modal window"


def test_shipped_curated_xsd_keeps_detail_view_date_time_kind():
    # A hand-edit in the 2026-08-07 curation had truncated this attribute's name to
    # "d", which parses cleanly and only shows up as a missing Properties entry.
    schema = load_curated(bundled_curated_xsd_text())
    chain = (
        "Project/Presentation/Pages/Page/Details/Detail/Page/ColumnPresentations/"
        "ColumnPresentation/ViewProperties"
    )
    attributes = schema.model.paths[chain]["attributes"]
    assert "dateTimeKind" in attributes
    assert "d" not in attributes


def test_no_attribute_is_nested_inside_another_attribute():
    # Structural guard for the other hand-edit class seen in the 2026-08-07 curation:
    # a missing </xs:attribute> nests the next xs:attribute inside the previous one.
    # The file stays well-formed XML, but the swallowed attribute disappears from
    # completion with no error anywhere.
    import xml.etree.ElementTree as ET

    xs = "{http://www.w3.org/2001/XMLSchema}attribute"
    root = ET.fromstring(SHIPPED_CURATED.read_text(encoding="utf-8"))
    nested = [
        (outer.get("name"), inner.get("name"))
        for outer in root.iter(xs)
        for inner in outer.iter(xs)
        if inner is not outer
    ]
    assert nested == [], (
        f"xs:attribute nested inside xs:attribute in curated.xsd: {nested}. "
        "A missing </xs:attribute> close tag swallows the following attribute."
    )
