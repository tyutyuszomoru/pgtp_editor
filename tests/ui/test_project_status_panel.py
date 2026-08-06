"""§18.8 Project Status window (ui/project_status_panel.py).

The panel is a painter over `project_status_model`'s already-derived diagram, so
these tests never assert *state derivation* (that is the model's own suite) — they
assert the four things the widget alone can get wrong:

1. **Shape.** It renders exactly the nodes the diagram contains, so the absence
   rule (no sandbox ever configured → no sandbox trio) survives into the widget
   instead of being re-decided there.
2. **Click-through.** Each of the five families opens its own window, the
   tools-missing window names the missing tools, and Sandbox1/Sandbox2 are
   two-step: the click opens a window, the *button inside it* fires the action.
3. **No dead controls.** With no callbacks injected, nothing crashes and no
   button is offered for an action nobody can perform.
4. **Theme.** A theme flip swaps every asset to its `_drk` counterpart without
   re-deriving any state.

Nothing here can reach a modal call: the panel opens non-modal `QDialog`s with
`show()` and exposes them as `last_window`, so no `.exec()`/`QMessageBox` is ever
involved.
"""
import pytest
from PySide6.QtCore import QSize

from pgtp_editor.db.sandbox import SandboxCapabilities, SandboxMode, determine_project_tier
from pgtp_editor.ui import project_status_model as psm
from pgtp_editor.ui import project_status_panel
from pgtp_editor.ui.project_status_model import NodeFamily, QualityState, build_diagram
from pgtp_editor.ui.project_status_panel import (
    ProjectStatusPanel,
    _boxed_pixmap,
    _logical_size,
    _scaled_pixmap,
)

pytestmark = pytest.mark.usefixtures("qapp")


# ---------------------------------------------------------------------------
# helpers -- real probe results, same shapes the model's own suite uses
# ---------------------------------------------------------------------------
def _caps(**kwargs) -> SandboxCapabilities:
    defaults = dict(
        server_version=(16, 0),
        pg_dump_path="/usr/bin/pg_dump",
        pg_restore_path="/usr/bin/pg_restore",
    )
    return SandboxCapabilities(**{**defaults, **kwargs})


def _full_diagram(*, dark: bool = True, **kwargs) -> psm.ProjectStatusDiagram:
    """Tier 3: every node renders."""
    status = determine_project_tier(_caps(), SandboxMode.SCHEMA_ONLY)
    return build_diagram(
        status=status, quality=QualityState.CONNECTION_OK, dark=dark, **kwargs
    )


def _no_sandbox_diagram() -> psm.ProjectStatusDiagram:
    status = determine_project_tier(
        _caps(), SandboxMode.SCHEMA_ONLY, sandbox_configured=False
    )
    return build_diagram(status=status, quality=QualityState.CONNECTION_OK)


def _tools_missing_diagram() -> psm.ProjectStatusDiagram:
    status = determine_project_tier(
        _caps(pg_dump_path=None, pg_restore_path=None), SandboxMode.WITH_DATA
    )
    return build_diagram(status=status, quality=QualityState.CONNECTION_OK)


def _installed_diagram() -> psm.ProjectStatusDiagram:
    status = determine_project_tier(
        _caps(installed_extensions=frozenset({"plpgsql_check"})), SandboxMode.SCHEMA_ONLY
    )
    return build_diagram(status=status, quality=QualityState.CONNECTION_OK)


# ---------------------------------------------------------------------------
# shape
# ---------------------------------------------------------------------------
def test_full_diagram_renders_all_five_nodes():
    panel = ProjectStatusPanel(diagram=_full_diagram())
    assert set(panel.node_widgets) == set(NodeFamily)
    for family in NodeFamily:
        widget = panel.node_widget(family)
        assert widget is not None
        assert not widget.icon_label.pixmap().isNull()


def test_sandbox_absent_diagram_renders_only_quality_and_app():
    diagram = _no_sandbox_diagram()
    assert not diagram.sandbox_present  # guard: the model applied the absence rule
    panel = ProjectStatusPanel(diagram=diagram)
    assert set(panel.node_widgets) == {NodeFamily.QUALITY, NodeFamily.APP}
    # Absent, not disabled: there is no sandbox widget to be a dead control.
    assert panel.node_widget(NodeFamily.SANDBOX) is None


def test_switching_diagram_replaces_the_nodes():
    panel = ProjectStatusPanel(diagram=_full_diagram())
    panel.set_diagram(_no_sandbox_diagram())
    assert set(panel.node_widgets) == {NodeFamily.QUALITY, NodeFamily.APP}
    panel.set_diagram(_full_diagram())
    assert set(panel.node_widgets) == set(NodeFamily)


def test_no_diagram_renders_an_empty_state_without_crashing():
    panel = ProjectStatusPanel()
    assert panel.node_widgets == {}
    assert "Not probed" in panel.summary_label.text()


def test_icons_are_aligned_on_one_centre_line():
    """Every chain node's icon box is the same height, which is what makes the
    connectors line up; a per-asset height would break the diagram silently.

    And no box may be *smaller* than the art it holds: `_boxed_pixmap` used to
    clamp the centering offset at zero, which silently cropped an icon that
    overflowed its box (BUG-029, the "cut" half). The box fitting the icon in
    both axes is what makes that clamp unreachable.
    """
    diagram = _full_diagram()
    panel = ProjectStatusPanel(diagram=diagram)
    chain = [NodeFamily.QUALITY, NodeFamily.APP, NodeFamily.SANDBOX]
    heights = {panel.node_widget(f).icon_label.height() for f in chain}
    assert len(heights) == 1

    for node in diagram.nodes:
        icon = _scaled_pixmap(node.asset, panel._rendered_dpr)
        assert not icon.isNull(), node.asset
        box = panel.node_widget(node.family).icon_label.size()
        pad = panel.node_widget(node.family).icon_label.pixmap()
        for measured in (box, _logical_size(pad)):
            assert measured.width() >= _logical_size(icon).width(), node.asset
            assert measured.height() >= _logical_size(icon).height(), node.asset


def test_a_box_smaller_than_its_icon_grows_instead_of_cropping():
    """The clamp's failure mode, forced directly: a box one pixel too small in
    each axis must produce a pad that still contains the whole icon."""
    icon = _scaled_pixmap("quality_connection_ok.svg", 1.0)
    assert not icon.isNull()
    size = _logical_size(icon)
    pad = _boxed_pixmap(icon, size - QSize(1, 1), 1.0)
    assert _logical_size(pad).width() >= size.width()
    assert _logical_size(pad).height() >= size.height()


def test_a_pixmap_built_at_another_dpr_still_is_not_clipped():
    """The build-vs-paint DPR mismatch: an icon rendered for a 2x screen padded
    into a box measured for a 1x one. Pad and icon are sized from one threaded
    `dpr` now, so nothing overflows."""
    icon = _scaled_pixmap("sandbox_connected.svg", 2.0)
    box = _logical_size(_scaled_pixmap("sandbox_connected.svg", 1.0))
    pad = _boxed_pixmap(icon, box, 2.0)
    assert pad.width() >= icon.width()
    assert pad.height() >= icon.height()
    assert _logical_size(pad).width() >= _logical_size(icon).width()
    assert _logical_size(pad).height() >= _logical_size(icon).height()


def test_a_high_dpi_panel_clips_no_icon_and_rebuilds_on_a_ratio_change(monkeypatch):
    """Same guarantee through the whole widget at a stubbed 2x ratio — plus the
    ratio-change hook: a diagram rendered for 1x re-renders for 2x rather than
    leaving a pad and an icon sized for two different screens."""
    diagram = _full_diagram()
    panel = ProjectStatusPanel(diagram=diagram)
    assert panel._rendered_dpr == pytest.approx(1.0)
    boxes_at_1x = {f: panel.node_widget(f).icon_label.size() for f in NodeFamily}

    monkeypatch.setattr(ProjectStatusPanel, "_current_dpr", lambda self: 2.0)
    panel._on_device_pixel_ratio_changed()
    assert panel._rendered_dpr == pytest.approx(2.0)

    for node in diagram.nodes:
        icon = _logical_size(_scaled_pixmap(node.asset, 2.0))
        box = panel.node_widget(node.family).icon_label.size()
        assert box.width() >= icon.width(), node.asset
        assert box.height() >= icon.height(), node.asset
        # The ratio buys sharpness, never a different layout.
        assert box == boxes_at_1x[node.family], node.asset


def test_connector_label_is_never_shorter_than_its_art():
    """Connector art is only a few pixels tall, so a label pinned a hair short of
    the pixmap crops the whole line, not an edge."""
    panel = ProjectStatusPanel(diagram=_full_diagram())
    for asset in ("connector_quality-app.svg", "connector_app-sandbox.svg",
                  "connector_sandbox-db.svg"):
        pixmap = _scaled_pixmap(asset, 1.0)
        assert not pixmap.isNull(), asset
        label = panel._make_connector(pixmap)
        assert label.width() >= _logical_size(pixmap).width(), asset
        assert label.height() >= _logical_size(pixmap).height(), asset


def test_icons_are_rendered_at_device_resolution_not_upscaled():
    """The "very low resolution" half of BUG-029: the art is *rendered* from its
    vector source straight to `logical x dpr` device pixels, so there is no
    magnification of a small raster to soften it."""
    for dpr in (1.0, 2.0):
        pixmap = _scaled_pixmap("quality_connection_ok.svg", dpr)
        assert not pixmap.isNull()
        assert pixmap.devicePixelRatio() == pytest.approx(dpr)
        logical = _logical_size(pixmap)
        assert pixmap.width() == round(logical.width() * dpr)
        assert pixmap.height() == round(logical.height() * dpr)
    # Doubling the ratio really buys device pixels (a fixed-size raster upscale
    # would have given the same device size at both ratios).
    assert (
        _scaled_pixmap("quality_connection_ok.svg", 2.0).width()
        == 2 * _scaled_pixmap("quality_connection_ok.svg", 1.0).width()
    )


@pytest.mark.parametrize("stem", psm.all_asset_stems())
@pytest.mark.parametrize("dark", [False, True])
def test_every_bundled_asset_actually_renders(stem, dark):
    """The model's suite proves the files exist; this proves Qt can turn each one
    into pixels. An unreadable asset is a silent gap in the diagram."""
    pixmap = _scaled_pixmap(psm.asset_filename(stem, dark), 1.0)
    assert not pixmap.isNull(), psm.asset_filename(stem, dark)


# ---------------------------------------------------------------------------
# click-through
# ---------------------------------------------------------------------------
def test_every_node_opens_its_own_window():
    panel = ProjectStatusPanel(diagram=_full_diagram())
    seen = []
    panel.node_activated.connect(seen.append)
    for family in NodeFamily:
        panel.node_widget(family).click()
        assert panel.last_window is not None
        assert panel.last_window.family is family
    assert seen == [family.value for family in NodeFamily]
    assert len(panel.open_windows) == len(NodeFamily)


def test_quality_window_shows_connection_info_and_reconnect():
    calls = []
    panel = ProjectStatusPanel(
        diagram=_full_diagram(),
        on_reconnect_quality=lambda: calls.append("reconnect"),
        quality_summary="quality@db.example:5432/appdb",
    )
    panel.node_widget(NodeFamily.QUALITY).click()
    window = panel.last_window
    assert "quality@db.example" in window.body_text
    assert window.action_button is not None
    window.action_button.click()
    assert calls == ["reconnect"]


def test_app_window_is_a_placeholder_with_no_action():
    """§18.8 leaves the App action window's contents unspecified and forbids
    inventing them, so it states the tier and offers nothing else."""
    panel = ProjectStatusPanel(diagram=_full_diagram())
    panel.node_widget(NodeFamily.APP).click()
    window = panel.last_window
    assert "Tier 3" in window.body_text
    assert "development project" in window.body_text
    assert window.action_button is None


def test_tools_missing_window_names_the_missing_tools_and_offers_help():
    helped = []
    diagram = _tools_missing_diagram()
    assert diagram.sandbox_degradation is psm.SandboxDegradation.TOOLS_MISSING
    panel = ProjectStatusPanel(diagram=diagram, on_show_help=lambda: helped.append(1))
    # Deliberately the same green icon as a healthy sandbox (§18.8).
    assert panel.node_widget(NodeFamily.SANDBOX).icon_label.pixmap() is not None
    assert diagram.node(NodeFamily.SANDBOX).state == "sandbox_connected"
    panel.node_widget(NodeFamily.SANDBOX).click()
    window = panel.last_window
    for tool in diagram.missing_tools:
        assert tool in window.body_text
    assert window.help_button is not None
    window.help_button.click()
    assert helped == [1]


def test_healthy_sandbox_window_offers_no_help_button():
    panel = ProjectStatusPanel(diagram=_full_diagram(), on_show_help=lambda: None)
    panel.node_widget(NodeFamily.SANDBOX).click()
    assert panel.last_window.help_button is None


def test_sandbox1_is_two_step_clone_action():
    calls = []
    panel = ProjectStatusPanel(
        diagram=_full_diagram(), on_run_data_clone=lambda: calls.append("clone")
    )
    panel.node_widget(NodeFamily.SANDBOX1).click()
    window = panel.last_window
    # Step one opened a window; the click alone must not have fired anything.
    assert calls == []
    assert window.action_button.text() == "Run data clone now"
    window.action_button.click()
    assert calls == ["clone"]


def test_sandbox1_offers_redo_when_data_is_already_cloned():
    panel = ProjectStatusPanel(
        diagram=_full_diagram(
            sandbox_schema_present=psm.SandboxFact.PRESENT,
            sandbox_data_present=psm.SandboxFact.PRESENT,
        ),
        on_run_data_clone=lambda: None,
    )
    panel.node_widget(NodeFamily.SANDBOX1).click()
    assert panel.last_window.action_button.text() == "Redo data clone"


def test_sandbox1_never_says_schema_unless_a_schema_was_seen():
    """BUG-035: the reported symptom was the literal word "schema" appearing for
    a sandbox that had none. Neither the caption nor the detail line may claim
    one in the unknown or not-provisioned states."""
    for schema_fact in (psm.SandboxFact.UNKNOWN, psm.SandboxFact.ABSENT):
        for data_fact in psm.SandboxFact:
            panel = ProjectStatusPanel(
                diagram=_full_diagram(
                    sandbox_schema_present=schema_fact, sandbox_data_present=data_fact
                )
            )
            state = panel.diagram.node(NodeFamily.SANDBOX1).state
            caption = panel.node_widget(NodeFamily.SANDBOX1).state_label.text()
            assert "schema" not in caption.lower(), (state, caption)
            panel.node_widget(NodeFamily.SANDBOX1).click()
            body = panel.last_window.body_text
            assert "holds the schema" not in body.lower(), (state, body)


def test_sandbox1_unknown_says_it_could_not_check_not_that_it_is_empty():
    panel = ProjectStatusPanel(
        diagram=_full_diagram(sandbox_schema_present=psm.SandboxFact.UNKNOWN)
    )
    assert panel.diagram.node(NodeFamily.SANDBOX1).state == "sandbox1_unknown"
    assert panel.node_widget(NodeFamily.SANDBOX1).state_label.text() == "Not checked"
    panel.node_widget(NodeFamily.SANDBOX1).click()
    body = panel.last_window.body_text.lower()
    assert "could not be inspected" in body
    assert "not a report that it is empty" in body


def test_sandbox1_not_provisioned_says_nothing_is_there_yet():
    panel = ProjectStatusPanel(
        diagram=_full_diagram(sandbox_schema_present=psm.SandboxFact.ABSENT)
    )
    node = panel.diagram.node(NodeFamily.SANDBOX1)
    assert node.state == "sandbox1_not_provisioned"
    # Interim art reuse (documented in the model): the node must still RENDER.
    assert node.asset == "sandbox1_empty_drk.svg"
    assert not panel.node_widget(NodeFamily.SANDBOX1).icon_label.pixmap().isNull()
    assert (
        panel.node_widget(NodeFamily.SANDBOX1).state_label.text() == "Nothing provisioned"
    )


def test_every_sandbox1_state_has_a_caption_and_a_detail_line():
    for state in psm.Sandbox1State:
        assert state.value in project_status_panel._STATE_CAPTIONS, state
        assert state.value in ProjectStatusPanel._SANDBOX1_LINES, state


def test_sandbox2_offers_install_only_when_not_installed():
    calls = []
    panel = ProjectStatusPanel(
        diagram=_full_diagram(), on_install_plpgsql_check=lambda: calls.append("install")
    )
    assert (
        panel.diagram.node(NodeFamily.SANDBOX2).state
        == "sandbox2_plpgsql_check_not_installed"
    )
    panel.node_widget(NodeFamily.SANDBOX2).click()
    window = panel.last_window
    assert calls == []  # two-step: opening is not acting
    assert "plpgsql_check" in window.action_button.text()
    window.action_button.click()
    assert calls == ["install"]


def test_sandbox2_installed_window_is_informational_only():
    installed = _installed_diagram()
    assert (
        installed.node(NodeFamily.SANDBOX2).state == "sandbox2_plpgsql_check_installed"
    )
    panel = ProjectStatusPanel(
        diagram=installed, on_install_plpgsql_check=lambda: pytest.fail("no action")
    )
    panel.node_widget(NodeFamily.SANDBOX2).click()
    assert panel.last_window.action_button is None


def test_nodes_activate_from_the_keyboard():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    panel = ProjectStatusPanel(diagram=_full_diagram())
    widget = panel.node_widget(NodeFamily.QUALITY)
    widget.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
    )
    assert panel.last_window is not None


# ---------------------------------------------------------------------------
# no dead controls
# ---------------------------------------------------------------------------
def test_without_callbacks_no_window_offers_a_button():
    panel = ProjectStatusPanel(diagram=_tools_missing_diagram())
    assert panel.refresh_button.isHidden()
    for family in NodeFamily:
        panel.node_widget(family).click()
        window = panel.last_window
        assert window.action_button is None
        assert window.help_button is None


def test_refresh_without_callback_is_a_no_op():
    panel = ProjectStatusPanel(diagram=_full_diagram())
    panel.refresh()  # must not raise
    assert set(panel.node_widgets) == set(NodeFamily)


# ---------------------------------------------------------------------------
# theme
# ---------------------------------------------------------------------------
def test_theme_flip_swaps_every_asset():
    panel = ProjectStatusPanel(diagram=_full_diagram(dark=True))
    assert all(asset.endswith("_drk.svg") for asset in panel.diagram.assets())
    states_before = [node.state for node in panel.diagram.nodes]

    panel.set_dark(False)
    assert not any(asset.endswith("_drk.svg") for asset in panel.diagram.assets())
    assert panel.diagram.dark is False
    # State is never re-derived by a theme change, only the filenames change.
    assert [node.state for node in panel.diagram.nodes] == states_before
    assert set(panel.node_widgets) == set(NodeFamily)

    panel.set_light_theme(False)
    assert all(asset.endswith("_drk.svg") for asset in panel.diagram.assets())


def test_set_dark_with_no_diagram_is_safe():
    panel = ProjectStatusPanel()
    panel.set_dark(False)
    assert panel.diagram is None


# ---------------------------------------------------------------------------
# the on-open re-probe seam
# ---------------------------------------------------------------------------
def test_showing_the_panel_triggers_a_fresh_probe():
    """§18.8: opening this window is itself a probe trigger, not a passive read
    of a cached result."""
    calls = []

    def probe():
        calls.append("probe")
        return _no_sandbox_diagram()

    panel = ProjectStatusPanel(diagram=_full_diagram(), on_refresh=probe)
    assert calls == []
    panel.show()
    assert calls == ["probe"]
    # The returned diagram is rendered immediately.
    assert set(panel.node_widgets) == {NodeFamily.QUALITY, NodeFamily.APP}
    panel.hide()
    panel.show()
    assert calls == ["probe"]  # only the first show re-probes
    panel.close()


def test_refresh_button_reprobes_and_a_none_return_keeps_the_diagram():
    calls = []
    panel = ProjectStatusPanel(diagram=_full_diagram(), on_refresh=lambda: calls.append(1))
    panel.refresh_button.click()
    assert calls == [1]
    assert set(panel.node_widgets) == set(NodeFamily)


def test_action_reprobes_after_running():
    """An action must not leave the diagram claiming the pre-action state."""
    calls = []
    panel = ProjectStatusPanel(
        diagram=_full_diagram(),
        on_install_plpgsql_check=lambda: calls.append("install"),
        on_refresh=lambda: (calls.append("probe"), _installed_diagram())[1],
    )
    panel.node_widget(NodeFamily.SANDBOX2).click()
    panel.last_window.action_button.click()
    assert calls == ["install", "probe"]
    assert (
        panel.diagram.node(NodeFamily.SANDBOX2).state
        == "sandbox2_plpgsql_check_installed"
    )
