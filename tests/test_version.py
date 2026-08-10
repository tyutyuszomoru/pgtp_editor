# tests/test_version.py
"""`FQ-260810164455` -- ONE importable app version, and no second literal."""
import re
from pathlib import Path

import pytest

from pgtp_editor import version as version_module
from pgtp_editor.version import (
    DISTRIBUTION_NAME,
    UNKNOWN_VERSION,
    __version__,
    app_version,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _pyproject_literal() -> str:
    """The one literal, read the crude way a test should: independently of the
    module under test."""
    text = PYPROJECT.read_text(encoding="utf-8")
    body = text.split("[project]", 1)[1].split("\n[", 1)[0]
    found = re.search(r'^version\s*=\s*"([^"]+)"', body, re.MULTILINE)
    assert found is not None, "pyproject.toml lost its [project] version line"
    return found.group(1)


def test_the_app_version_is_importable_and_non_empty():
    assert isinstance(__version__, str)
    assert __version__.strip()


def test_the_app_version_IS_the_pyproject_literal():
    """The guard against the drift this feature exists to kill: `pyproject.toml`
    is the single literal, and `installer.iss` scans that same line."""
    assert __version__ == _pyproject_literal()
    assert app_version() == _pyproject_literal()


def test_there_is_no_second_version_literal_in_version_py():
    """A hardcoded default would recreate the two copies. The only version-shaped
    string this module may contain is the "unknown" sentinel."""
    source = Path(version_module.__file__).read_text(encoding="utf-8")
    # Strip the docstring, which legitimately names other versions while
    # explaining what they are.
    body = source.split('"""', 2)[-1]
    assert not re.search(r'=\s*["\']\d+\.\d+', body), (
        "version.py assigns a version literal; it must read pyproject/metadata"
    )


def test_the_not_installed_path_falls_through_to_metadata(monkeypatch):
    """No `pyproject.toml` reachable -- an installed wheel, or a frozen bundle
    whose metadata PyInstaller collected."""
    monkeypatch.setattr(
        version_module, "_pyproject_path", lambda: Path("/nonexistent/pyproject.toml")
    )
    monkeypatch.setattr(version_module, "_metadata_version", lambda: "9.9.9")
    assert version_module.app_version() == "9.9.9"


def test_neither_source_answers_gives_the_HONEST_sentinel(monkeypatch):
    """Nothing to read and nothing installed: an explicit "unknown" rather than a
    plausible lie. A literal default was rejected precisely because it looks right
    while being wrong."""
    monkeypatch.setattr(
        version_module, "_pyproject_path", lambda: Path("/nonexistent/pyproject.toml")
    )
    monkeypatch.setattr(version_module, "_metadata_version", lambda: None)
    assert version_module.app_version() == UNKNOWN_VERSION
    assert UNKNOWN_VERSION == "unknown"
    assert not re.match(r"^\d", UNKNOWN_VERSION), "the sentinel must not look like a version"


def test_a_foreign_pyproject_is_not_read_as_ours(monkeypatch, tmp_path):
    """The file is located by position, so it must also be identified by name --
    otherwise a nested layout could report some other project's version."""
    foreign = tmp_path / "pyproject.toml"
    foreign.write_text('[project]\nname = "something-else"\nversion = "7.7.7"\n')
    monkeypatch.setattr(version_module, "_pyproject_path", lambda: foreign)
    monkeypatch.setattr(version_module, "_metadata_version", lambda: None)
    assert version_module.app_version() == UNKNOWN_VERSION


def test_the_distribution_name_matches_pyproject():
    text = PYPROJECT.read_text(encoding="utf-8")
    assert f'name = "{DISTRIBUTION_NAME}"' in text


def test_the_metadata_reader_never_raises_when_nothing_is_installed(monkeypatch):
    """`PackageNotFoundError` is the expected miss, not an error to propagate."""
    import importlib.metadata as md

    def boom(_name):
        raise md.PackageNotFoundError(DISTRIBUTION_NAME)

    monkeypatch.setattr(md, "version", boom)
    assert version_module._metadata_version() is None


@pytest.mark.parametrize(
    "other, what",
    [
        ("pgtp_editor/mcp/server.py", "SERVER_VERSION"),
        ("pgtp_editor/schema_learning/storage.py", "CURATED_BUNDLED_VERSION"),
        ("pgtp_editor/db/schema_snapshot.py", "SNAPSHOT_VERSION"),
    ],
)
def test_the_other_version_numbers_are_left_alone(other, what):
    """FIVE version numbers exist and only one is the app's. `SERVER_VERSION`'s
    decoupling from the app release is an OWNER RULING -- this asserts nobody
    "fixed" these into `version.py` as drift."""
    source = (REPO_ROOT / other).read_text(encoding="utf-8")
    assert what in source
    assert "pgtp_editor.version" not in source


def test_the_frozen_build_collects_the_metadata_it_will_need():
    """The frozen case is the one `importlib.metadata` is least likely to answer,
    and a frozen bundle ships no `pyproject.toml` -- so the build embeds the
    distribution metadata rather than `version.py` carrying a literal."""
    build = (REPO_ROOT / "optimized_build.py").read_text(encoding="utf-8")
    assert "--copy-metadata" in build
    assert "DISTRIBUTION_NAME" in build
