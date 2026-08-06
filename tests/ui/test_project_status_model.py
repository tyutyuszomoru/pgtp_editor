"""§18.8 Project Status diagram derivation (ui/project_status_model.py).

Two risks dominate here. First, the diagram's *shape* is state-dependent: the
absence rule removes the sandbox trio entirely when no sandbox was ever
configured, and a configured-but-broken sandbox must keep it -- getting that
backwards produces either dead controls or a silently truncated diagram.
Second, every state resolves to a filename, so a typo'd stem ships as a
missing image with no error; `test_every_asset_exists_on_disk` walks the whole
state space in both themes as the guard against that.

The module is Qt-free by design, so nothing here needs a QApplication.
"""
from importlib.resources import files

import pytest

from pgtp_editor.db.sandbox import (
    ProjectCapabilityStatus,
    ProjectTier,
    SandboxCapabilities,
    SandboxMode,
    determine_project_tier,
)
from pgtp_editor.ui import project_status_model as psm


# ---------------------------------------------------------------------------
# helpers -- build real ProjectCapabilityStatus values, never hand-faked text
# ---------------------------------------------------------------------------
def _caps(**kwargs) -> SandboxCapabilities:
    """A reachable probe result, overridable per test."""
    defaults = dict(
        server_version=(16, 0),
        pg_dump_path="/usr/bin/pg_dump",
        pg_restore_path="/usr/bin/pg_restore",
    )
    return SandboxCapabilities(**{**defaults, **kwargs})


def _status_development() -> ProjectCapabilityStatus:
    return determine_project_tier(_caps(), SandboxMode.SCHEMA_ONLY)


def _status_never_configured() -> ProjectCapabilityStatus:
    return determine_project_tier(
        _caps(), SandboxMode.SCHEMA_ONLY, sandbox_configured=False
    )


def _status_unreachable() -> ProjectCapabilityStatus:
    return determine_project_tier(
        _caps(probe_error="connection refused"), SandboxMode.SCHEMA_ONLY
    )


def _status_tools_missing() -> ProjectCapabilityStatus:
    return determine_project_tier(
        _caps(pg_dump_path=None, pg_restore_path=None), SandboxMode.WITH_DATA
    )


# ---------------------------------------------------------------------------
# degraded_reason classification
# ---------------------------------------------------------------------------
def test_classify_real_degraded_reasons():
    assert (
        psm.classify_degraded_reason(_status_development().degraded_reason)
        is psm.SandboxDegradation.NONE
    )
    assert (
        psm.classify_degraded_reason(_status_never_configured().degraded_reason)
        is psm.SandboxDegradation.NOT_CONFIGURED
    )
    assert (
        psm.classify_degraded_reason(_status_unreachable().degraded_reason)
        is psm.SandboxDegradation.UNREACHABLE
    )
    assert (
        psm.classify_degraded_reason(_status_tools_missing().degraded_reason)
        is psm.SandboxDegradation.TOOLS_MISSING
    )


def test_classify_unrecognized_reason_is_other_not_healthy():
    assert (
        psm.classify_degraded_reason("something new nobody anticipated")
        is psm.SandboxDegradation.OTHER
    )


def test_no_sandbox_reason_matches_the_real_producer_verbatim():
    # The absence rule compares this string exactly; if determine_project_tier
    # ever rewords it, this test is the tripwire.
    assert _status_never_configured().degraded_reason == psm.NO_SANDBOX_REASON


def test_missing_clone_tools_names_the_tools_only_for_tools_missing():
    assert psm.missing_clone_tools(_status_tools_missing().degraded_reason) == (
        "pg_dump",
        "pg_restore",
    )
    assert psm.missing_clone_tools(_status_unreachable().degraded_reason) == ()
    assert psm.missing_clone_tools(None) == ()


# ---------------------------------------------------------------------------
# App node -- 3 states, tier only
# ---------------------------------------------------------------------------
def test_app_state_standalone_needs_no_project_at_all():
    # Tier 1 is not a ProjectTier member; it arrives as None.
    assert psm.app_state(None) is psm.AppState.STANDALONE


def test_app_state_maps_the_two_tier_members():
    assert psm.app_state(_status_development()) is psm.AppState.PROJECT_SETUP
    assert psm.app_state(_status_unreachable()) is psm.AppState.PROJECT_NOT_SETUP
    assert psm.app_state(_status_never_configured()) is psm.AppState.PROJECT_NOT_SETUP


def test_app_state_ignores_why_tier_three_was_missed():
    # The App node answers "what tier?" and nothing else -- three different
    # degradation causes must all render the same icon.
    states = {
        psm.app_state(status)
        for status in (
            _status_never_configured(),
            _status_unreachable(),
            _status_tools_missing(),
        )
    }
    assert states == {psm.AppState.PROJECT_NOT_SETUP}


# ---------------------------------------------------------------------------
# Sandbox node -- 3 icons over 4 backing conditions
# ---------------------------------------------------------------------------
def test_sandbox_state_development_is_green():
    assert psm.sandbox_state(_status_development()) is psm.SandboxState.CONNECTED


def test_sandbox_state_never_configured_is_gray():
    assert psm.sandbox_state(_status_never_configured()) is psm.SandboxState.NOT_SET_UP


def test_sandbox_state_unreachable_is_red():
    assert psm.sandbox_state(_status_unreachable()) is psm.SandboxState.OFFLINE


def test_sandbox_state_tools_missing_renders_green_not_a_fourth_state():
    # §18.8: tools-missing is a backing condition, NOT a 4th icon -- it shares
    # the green connection-ok icon, with the detail only in click-through.
    status = _status_tools_missing()
    assert status.tier is ProjectTier.QUALITY  # genuinely degraded...
    assert psm.sandbox_state(status) is psm.SandboxState.CONNECTED  # ...still green
    assert (
        psm.classify_degraded_reason(status.degraded_reason)
        is psm.SandboxDegradation.TOOLS_MISSING
    )


def test_sandbox_state_unknown_degradation_is_red_not_green():
    status = ProjectCapabilityStatus(
        tier=ProjectTier.QUALITY,
        capabilities=_caps(),
        degraded_reason="a reason from the future",
    )
    assert psm.sandbox_state(status) is psm.SandboxState.OFFLINE


def test_sandbox_node_has_exactly_three_visual_states():
    assert len(psm.SandboxState) == 3


# ---------------------------------------------------------------------------
# Sandbox1 -- data fill
# ---------------------------------------------------------------------------
def test_sandbox1_unverified_schema_is_unknown_never_a_definite_state():
    """BUG-035: "could not check" must never be reported as "not there" -- and
    certainly never as "Schema only"."""
    for data in psm.SandboxFact:
        assert (
            psm.sandbox1_state(psm.SandboxFact.UNKNOWN, data) is psm.Sandbox1State.UNKNOWN
        )


def test_sandbox1_verified_absent_schema_is_not_provisioned():
    for data in psm.SandboxFact:
        assert (
            psm.sandbox1_state(psm.SandboxFact.ABSENT, data)
            is psm.Sandbox1State.NOT_PROVISIONED
        )


def test_sandbox1_schema_only_needs_a_schema_that_was_actually_seen():
    assert (
        psm.sandbox1_state(psm.SandboxFact.PRESENT, psm.SandboxFact.ABSENT)
        is psm.Sandbox1State.EMPTY
    )
    # Unverified data resolves DOWNWARD: never a claim that a clone landed.
    assert (
        psm.sandbox1_state(psm.SandboxFact.PRESENT, psm.SandboxFact.UNKNOWN)
        is psm.Sandbox1State.EMPTY
    )


def test_sandbox1_is_filled_only_from_data_actually_found():
    assert (
        psm.sandbox1_state(psm.SandboxFact.PRESENT, psm.SandboxFact.PRESENT)
        is psm.Sandbox1State.FILLED
    )


def test_sandbox1_state_takes_no_sandbox_mode_at_all():
    """The whole point of BUG-035: the configured mode is a radio button, not a
    fact about the sandbox, so it must not be reachable from this derivation."""
    names = psm.sandbox1_state.__code__.co_varnames[
        : psm.sandbox1_state.__code__.co_argcount
    ]
    assert names == ("schema_present", "data_present")


# ---------------------------------------------------------------------------
# Sandbox2 -- the 4 -> 2 collapse
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value, expected",
    [
        ("installed", psm.Sandbox2State.INSTALLED),
        ("installable", psm.Sandbox2State.NOT_INSTALLED),
        ("absent", psm.Sandbox2State.NOT_INSTALLED),
        ("unknown", psm.Sandbox2State.NOT_INSTALLED),
    ],
)
def test_plpgsql_check_four_values_collapse_onto_two_icons(value, expected):
    assert psm.collapse_plpgsql_check_state(value) is expected


def test_plpgsql_check_unrecognized_value_never_claims_installed():
    assert psm.collapse_plpgsql_check_state("weird") is psm.Sandbox2State.NOT_INSTALLED


def test_sandbox2_state_reads_the_real_capability_property():
    installed = _caps(installed_extensions=frozenset({"plpgsql_check"}))
    installable = _caps(available_extensions=frozenset({"plpgsql_check"}))
    unknown = _caps(probe_error="boom")
    assert installed.plpgsql_check_state == "installed"
    assert psm.sandbox2_state(installed) is psm.Sandbox2State.INSTALLED
    assert psm.sandbox2_state(installable) is psm.Sandbox2State.NOT_INSTALLED
    assert psm.sandbox2_state(_caps()) is psm.Sandbox2State.NOT_INSTALLED  # absent
    assert psm.sandbox2_state(unknown) is psm.Sandbox2State.NOT_INSTALLED


# ---------------------------------------------------------------------------
# Quality node
# ---------------------------------------------------------------------------
def test_quality_state_three_states():
    assert psm.quality_state(False, None) is psm.QualityState.NOT_SET_UP
    assert psm.quality_state(True, "timeout") is psm.QualityState.OFFLINE
    assert psm.quality_state(True, None) is psm.QualityState.CONNECTION_OK


def test_quality_not_configured_wins_over_a_stale_error():
    assert psm.quality_state(False, "timeout") is psm.QualityState.NOT_SET_UP


# ---------------------------------------------------------------------------
# Theme suffix selection
# ---------------------------------------------------------------------------
def test_asset_filename_theme_suffix():
    assert psm.asset_filename("app_standalone", dark=False) == "app_standalone.svg"
    assert psm.asset_filename("app_standalone", dark=True) == "app_standalone_drk.svg"


def test_asset_filename_accepts_state_enums_directly():
    assert (
        psm.asset_filename(psm.SandboxState.CONNECTED.value, dark=True)
        == "sandbox_connected_drk.svg"
    )


def test_build_diagram_dark_flag_drives_every_asset():
    for dark in (False, True):
        diagram = psm.build_diagram(
            status=_status_development(),
            quality=psm.QualityState.CONNECTION_OK,
            dark=dark,
        )
        assert diagram.dark is dark
        assert diagram.assets()  # non-empty
        for asset in diagram.assets():
            assert asset.endswith("_drk.svg") is dark, asset


# ---------------------------------------------------------------------------
# The diagram -- shape, order, absence rule
# ---------------------------------------------------------------------------
def test_diagram_full_shape_for_a_working_project():
    diagram = psm.build_diagram(
        status=_status_development(),
        quality=psm.QualityState.CONNECTION_OK,
        sandbox_schema_present=psm.SandboxFact.PRESENT,
        sandbox_data_present=psm.SandboxFact.PRESENT,
    )
    assert [node.family for node in diagram.nodes] == [
        psm.NodeFamily.QUALITY,
        psm.NodeFamily.APP,
        psm.NodeFamily.SANDBOX,
        psm.NodeFamily.SANDBOX1,
        psm.NodeFamily.SANDBOX2,
    ]
    assert [connector.kind for connector in diagram.connectors] == [
        psm.ConnectorKind.QUALITY_APP,
        psm.ConnectorKind.APP_SANDBOX,
        psm.ConnectorKind.SANDBOX_DB,
    ]
    assert diagram.sandbox_present
    assert diagram.sandbox_degradation is psm.SandboxDegradation.NONE
    assert diagram.node(psm.NodeFamily.SANDBOX1).state == "sandbox1_filled"


def test_absence_rule_never_configured_hides_the_sandbox_trio():
    diagram = psm.build_diagram(
        status=_status_never_configured(), quality=psm.QualityState.CONNECTION_OK
    )
    assert [node.family for node in diagram.nodes] == [
        psm.NodeFamily.QUALITY,
        psm.NodeFamily.APP,
    ]
    assert [connector.kind for connector in diagram.connectors] == [
        psm.ConnectorKind.QUALITY_APP
    ]
    assert not diagram.sandbox_present
    assert diagram.node(psm.NodeFamily.SANDBOX) is None
    assert diagram.node(psm.NodeFamily.SANDBOX1) is None
    assert diagram.node(psm.NodeFamily.SANDBOX2) is None
    # Absent, not shown-in-a-gray-state: the gray sandbox icon never renders.
    assert psm.SandboxState.NOT_SET_UP.value not in [node.state for node in diagram.nodes]
    assert diagram.sandbox_degradation is psm.SandboxDegradation.NOT_CONFIGURED


@pytest.mark.parametrize("factory", [_status_unreachable, _status_tools_missing])
def test_absence_rule_a_broken_but_configured_sandbox_still_renders(factory):
    diagram = psm.build_diagram(status=factory(), quality=psm.QualityState.CONNECTION_OK)
    assert diagram.sandbox_present
    assert diagram.node(psm.NodeFamily.SANDBOX1) is not None
    assert diagram.node(psm.NodeFamily.SANDBOX2) is not None
    assert psm.ConnectorKind.SANDBOX_DB in [c.kind for c in diagram.connectors]


def test_diagram_no_project_open_is_standalone_and_sandboxless():
    diagram = psm.build_diagram(status=None, quality=psm.QualityState.NOT_SET_UP)
    assert diagram.node(psm.NodeFamily.APP).state == "app_standalone"
    assert not diagram.sandbox_present
    assert diagram.degraded_reason is None


def test_diagram_carries_click_through_detail_for_tools_missing():
    diagram = psm.build_diagram(
        status=_status_tools_missing(), quality=psm.QualityState.CONNECTION_OK
    )
    # Green icon, but the window can still name the missing tools.
    assert diagram.node(psm.NodeFamily.SANDBOX).state == "sandbox_connected"
    assert diagram.missing_tools == ("pg_dump", "pg_restore")
    assert "pg_dump" in diagram.degraded_reason


def test_diagram_node_state_and_asset_agree():
    diagram = psm.build_diagram(
        status=_status_unreachable(), quality=psm.QualityState.OFFLINE, dark=True
    )
    for node in diagram.nodes:
        # Aliased states (BUG-035's two new Sandbox1 rungs, which have no art
        # yet) resolve to the file that exists; every other state is identity.
        assert node.asset == f"{psm.resolve_asset_stem(node.state)}_drk.svg"
    for connector in diagram.connectors:
        assert connector.asset == f"{connector.kind.value}_drk.svg"


# ---------------------------------------------------------------------------
# The asset sweep -- the guard against a typo'd stem
# ---------------------------------------------------------------------------
def test_asset_path_uses_the_bundled_resources_dir():
    path = psm.asset_path("app_standalone.svg")
    assert path.is_file()
    assert (files("pgtp_editor") / "resources" / "status").is_dir()


@pytest.mark.parametrize("stem", psm.all_asset_stems())
@pytest.mark.parametrize("dark", [False, True])
def test_every_asset_exists_on_disk(stem, dark):
    """Both theme variants of every stem exist -- and hold actual image bytes.

    Existence alone let a 0-byte or half-written export pass as a shipped asset,
    so this also sniffs the content. The assets are SVG (`ASSET_EXTENSION`), but
    the check accepts a raster magic number too: one bundled file
    (`sandbox_offline.svg`) is a PNG the owner saved under an `.svg` name, and the
    panel renders it through a raster fallback rather than dropping the node.
    Whether a file *renders* is Qt's business and is asserted in
    `tests/ui/test_project_status_panel.py::test_every_bundled_asset_actually_renders`;
    this module stays Qt-free.
    """
    filename = psm.asset_filename(stem, dark)
    assert filename.endswith(psm.ASSET_EXTENSION), filename
    path = psm.asset_path(filename)
    assert path.is_file(), filename
    head = path.read_bytes()[:512]
    assert head, f"{filename} is empty"
    is_svg = b"<svg" in head
    is_raster = head.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8"))
    assert is_svg or is_raster, f"{filename} is not image data"


def test_all_asset_stems_covers_every_family_and_connector():
    stems = psm.all_asset_stems()
    assert len(stems) == len(set(stems))  # no duplicates
    # 3 quality + 3 app + 3 sandbox + 2 sandbox1 (4 states, 2 drawn) +
    # 2 sandbox2 + 3 connectors
    assert len(stems) == 16
    for family in ("quality_", "app_", "sandbox_", "sandbox1_", "sandbox2_", "connector_"):
        assert any(stem.startswith(family) for stem in stems), family


def test_every_aliased_stem_names_a_real_state_and_a_drawn_target():
    """BUG-035's interim aliases must point *from* a real state *to* real art —
    an alias to a stem that does not exist would ship as a blank node, which is
    the failure mode the alias table exists to avoid."""
    vocabulary = set(psm.all_state_stems())
    drawn = set(psm.all_asset_stems())
    for alias, target in psm.ASSET_STEM_ALIASES.items():
        assert alias in vocabulary, alias
        assert target in drawn, target
        assert alias not in drawn, f"{alias} is aliased yet also demanded as a file"


def test_state_vocabulary_is_wider_than_the_drawn_asset_set():
    """Guards the alias mechanism itself: if someone deletes an alias without
    adding art, `all_asset_stems` starts demanding the missing file and the
    on-disk sweep fails loudly instead of a node silently going blank."""
    assert set(psm.all_asset_stems()) < set(psm.all_state_stems())
    assert "sandbox1_unknown" not in psm.all_asset_stems()
    assert "sandbox1_not_provisioned" not in psm.all_asset_stems()


def test_every_diagram_the_model_can_build_resolves_to_real_files():
    """The full state-space sweep: every reachable diagram, both themes."""
    statuses = [
        None,
        _status_development(),
        _status_never_configured(),
        _status_unreachable(),
        _status_tools_missing(),
        determine_project_tier(
            _caps(installed_extensions=frozenset({"plpgsql_check"})),
            SandboxMode.SCHEMA_ONLY,
        ),
        determine_project_tier(_caps(probe_error="boom"), SandboxMode.WITH_DATA),
    ]
    seen = 0
    for status in statuses:
        for quality in psm.QualityState:
            for schema_fact in psm.SandboxFact:
                for data_fact in psm.SandboxFact:
                    for dark in (False, True):
                        diagram = psm.build_diagram(
                            status=status,
                            quality=quality,
                            sandbox_schema_present=schema_fact,
                            sandbox_data_present=data_fact,
                            dark=dark,
                        )
                        for asset in diagram.assets():
                            assert psm.asset_path(asset).is_file(), asset
                            seen += 1
    assert seen > 0
