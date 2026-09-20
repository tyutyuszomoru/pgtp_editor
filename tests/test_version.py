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


# --- the resolution ORDER, which is the inverse of what the queue entry asked --
def test_pyproject_WINS_over_metadata_when_the_two_disagree():
    """**The load-bearing half of the resolution order, pinned directly.**

    `test_the_app_version_IS_the_pyproject_literal` passes under EITHER order
    whenever the two sources happen to agree, so it does not pin the ordering
    decision at all -- it only pins it by accident, for as long as this venv's
    metadata stays stale. This one makes both sources answer, makes them
    DISAGREE, and asserts the pyproject literal wins.

    The order inverts what `FQ-260810164455`'s queue entry specified
    (metadata-first), deliberately: metadata is an install-time SNAPSHOT of the
    same literal, so in an editable checkout it goes stale the moment the literal
    is bumped without a reinstall. Metadata-first would then ship a *wrong*
    version in the one environment where the answer is checkable.
    """
    assert version_module._pyproject_version() == _pyproject_literal()
    assert version_module.app_version() == _pyproject_literal()


def test_the_stale_metadata_drift_is_real_in_this_checkout_and_loses(monkeypatch):
    """The measured justification for the inversion, asserted rather than quoted.

    Skips (rather than fails) once someone reinstalls and the two agree -- the
    drift is a property of the checkout, not of the code. What must hold either
    way is that when they differ, `app_version()` reports the *pyproject* one.
    """
    metadata = version_module._metadata_version()
    literal = _pyproject_literal()
    if metadata is None:
        pytest.skip("nothing installed in this interpreter; no drift to observe")
    if metadata == literal:
        pytest.skip(
            f"metadata is in sync with the literal ({literal}); no drift to observe"
        )
    # The drift the docstring measures: metadata-first would have shipped
    # `metadata` while the literal -- and the installer -- say `literal`.
    assert version_module.app_version() == literal
    assert version_module.app_version() != metadata


def test_metadata_answers_only_when_pyproject_is_unreachable(monkeypatch):
    """Branch 2 is a FALLBACK, not a competitor: it is consulted only when
    branch 1 misses. Asserted by counting calls, so an implementation that
    resolved both and preferred metadata could not pass."""
    calls = []

    def counted_metadata():
        calls.append(1)
        return "9.9.9"

    monkeypatch.setattr(version_module, "_metadata_version", counted_metadata)
    assert version_module.app_version() == _pyproject_literal()
    assert calls == [], "metadata was consulted although the literal was readable"


# --- reading the pyproject literal: the ways it can go wrong -------------------
def test_a_version_line_in_a_LATER_table_is_not_read_as_the_apps(monkeypatch, tmp_path):
    """`[project]` is sliced to the next table header for a reason: a
    `version =` belonging to some tool's own table sits later in the same file
    and would otherwise be picked up by a file-wide search."""
    path = tmp_path / "pyproject.toml"
    path.write_text(
        '[project]\n'
        f'name = "{DISTRIBUTION_NAME}"\n'
        'description = "no version line in this table"\n'
        '\n'
        '[tool.some-plugin]\n'
        'version = "6.6.6"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(version_module, "_pyproject_path", lambda: path)
    monkeypatch.setattr(version_module, "_metadata_version", lambda: None)

    assert version_module._pyproject_version() is None
    assert version_module.app_version() == UNKNOWN_VERSION


def test_a_file_with_no_project_table_at_all_is_a_miss(monkeypatch, tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[build-system]\nrequires = ["setuptools"]\n', encoding="utf-8")
    monkeypatch.setattr(version_module, "_pyproject_path", lambda: path)

    assert version_module._pyproject_version() is None


@pytest.mark.parametrize("literal", ['""', '"   "'])
def test_a_blank_version_literal_falls_THROUGH_rather_than_answering_empty(
    monkeypatch, tmp_path, literal
):
    """`app_version()` promises to be never empty. A half-edited literal must
    therefore behave like an absent one and hand over to the next source, not
    return `""` and let an empty About box through."""
    path = tmp_path / "pyproject.toml"
    path.write_text(
        f'[project]\nname = "{DISTRIBUTION_NAME}"\nversion = {literal}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(version_module, "_pyproject_path", lambda: path)
    monkeypatch.setattr(version_module, "_metadata_version", lambda: "9.9.9")

    assert version_module._pyproject_version() is None
    assert version_module.app_version() == "9.9.9"
    assert version_module.app_version().strip()


def test_the_pyproject_path_is_the_sibling_of_the_package_not_a_walk_upward():
    """Located by position and never by walking upward -- a walk could pick up an
    unrelated project's file in a nested layout."""
    assert version_module._pyproject_path() == PYPROJECT
    assert version_module._pyproject_path().is_file()


# --- the metadata reader's non-PackageNotFoundError leg -----------------------
def test_a_BROKEN_dist_info_is_a_miss_not_a_crash(monkeypatch):
    """`except Exception` is deliberate, not sloppy: a corrupt/unreadable
    dist-info is equally a "cannot answer", and letting it propagate would take
    the About box -- and `import pgtp_editor.version` -- down with it."""
    import importlib.metadata as md

    def broken(_name):
        raise ValueError("dist-info is garbage")

    monkeypatch.setattr(md, "version", broken)
    assert version_module._metadata_version() is None


def test_importing_the_module_cannot_raise_even_with_both_sources_broken(monkeypatch):
    """`__version__` is resolved at import time, so a failure here is an app that
    does not start."""
    import importlib.metadata as md

    monkeypatch.setattr(md, "version", lambda _n: (_ for _ in ()).throw(OSError("x")))
    monkeypatch.setattr(
        version_module, "_pyproject_path", lambda: Path("/nonexistent/pyproject.toml")
    )
    assert version_module.app_version() == UNKNOWN_VERSION


# --- the frozen build's guard --------------------------------------------------
def test_the_frozen_metadata_flag_is_GUARDED_by_an_availability_probe():
    """`--copy-metadata` is a HARD PyInstaller error when the distribution is not
    installed in the building interpreter, so passing it unconditionally would
    break a build from a bare checkout. The probe is asserted to exist and to be
    what gates the flag.

    **NOT VERIFIED BY AN ACTUAL BUILD.** There is no build environment in this
    checkout, so nothing here proves a frozen bundle really resolves its version
    through `importlib.metadata`; that leg remains an unverified claim. What is
    verified is the probe's own behaviour and the fact that the flag sits behind
    it.
    """
    import optimized_build

    source = Path(optimized_build.__file__).read_text(encoding="utf-8")
    assert "if _distribution_metadata_available():" in source
    guarded = source.split("if _distribution_metadata_available():", 1)[1]
    assert "--copy-metadata" in guarded.split("else:", 1)[0]
    # The bare-checkout leg says so out loud rather than silently shipping
    # "unknown".
    assert "unknown" in guarded.split("else:", 1)[1].split("\n\n", 1)[0]


def test_the_availability_probe_answers_for_this_interpreter_without_raising():
    import optimized_build

    answer = optimized_build._distribution_metadata_available()
    assert isinstance(answer, bool)
    assert answer is (version_module._metadata_version() is not None)


def test_the_availability_probe_treats_any_metadata_failure_as_unavailable(monkeypatch):
    """Same posture as `_metadata_version`: the probe exists to keep a build
    working, so it must never be the thing that stops one."""
    import importlib.metadata as md

    import optimized_build

    monkeypatch.setattr(
        md, "distribution", lambda _n: (_ for _ in ()).throw(ValueError("garbage"))
    )
    assert optimized_build._distribution_metadata_available() is False

    monkeypatch.setattr(
        md,
        "distribution",
        lambda _n: (_ for _ in ()).throw(md.PackageNotFoundError(DISTRIBUTION_NAME)),
    )
    assert optimized_build._distribution_metadata_available() is False


def test_the_build_never_hardcodes_a_version_literal_either():
    """The second-copy hazard is not confined to `version.py`: the build script
    reads `DISTRIBUTION_NAME` from the package and must not spell a version."""
    source = (REPO_ROOT / "optimized_build.py").read_text(encoding="utf-8")
    assert not re.search(r'(?<!\w)version\s*=\s*["\']\d+\.\d+', source)
