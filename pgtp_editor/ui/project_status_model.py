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

# pgtp_editor/ui/project_status_model.py
"""Derive the §18.8 Project Status diagram — which nodes exist, what state each
is in, and which bundled image renders it.

Pure: no Qt, no psycopg, no I/O, no clock, no global state. Importable without a
`QApplication`. The Qt window is a thin painter over `build_diagram`'s result;
every decision it would otherwise have to make (state derivation, the
absence rule, theme-variant filename selection) is made here so it can be
tested without a widget. `asset_path` is the one function that names a location
on disk, and even it only *builds* the `importlib.resources` traversable — it
never reads.

**State names are asset stems.** Each per-family state enum's *value* is the
bundled image's filename stem (`app_standalone`, `sandbox_connected`, …), so
there is no second lookup table to drift out of step with the first. The theme
variant is appended late, by `asset_filename`: light theme takes the plain
stem, dark theme the `_drk` counterpart. Theme is a plain boolean the caller
passes — the app has no OS dark-mode detection, only the explicit **Light
Theme** menu toggle (`ui/theme.py::apply_theme`), and this module must not
reach for global state to rediscover it.

Three places where the spec's state *set* is wider than the asset set, resolved
here as implementation detail (§18.8 authorizes each):

- **Sandbox has 4 backing conditions but 3 icons.** Reachable-but-tools-missing
  renders the same green `sandbox_connected` icon as a fully working sandbox;
  the distinction survives on `ProjectStatusDiagram.sandbox_degradation` for the
  node's click-through text, which is the only place it is meant to surface.
- **`plpgsql_check_state` has 4 values but Sandbox2 has 2 icons.** `"installed"`
  is installed; `"installable"`, `"absent"` and `"unknown"` all mean *not*
  installed, differing only in why, and there is no third icon to say why with.
- **Connectors carry no per-state assets.** §18.8 says connectors "carry state"
  but leaves the state set explicitly unspecified, and only one asset per
  connector exists. Each connector therefore resolves to its single image
  regardless of state; adding stateful connector art is a later, additive change.

The **absence rule** is load-bearing and lives here, not in the widget: when no
sandbox was ever configured, the Sandbox / Sandbox1 / Sandbox2 nodes and the
connectors reaching them are simply *not in the diagram* — the chain ends at the
app node. An inactive capability is absent, never a dead disabled control
(§18.5 carve-out 2, §18.7). A sandbox that IS configured but offline or
tools-missing keeps all three nodes, in their failed state.
"""
from dataclasses import dataclass
from enum import Enum
from importlib.resources import files

from ..db.sandbox import ProjectCapabilityStatus, ProjectTier, SandboxCapabilities, SandboxMode

#: Bundled image extension. Every state stem and connector stem exists twice in
#: `resources/status/`: `<stem>.png` (light) and `<stem>_drk.png` (dark).
ASSET_EXTENSION = ".png"

#: Appended to a stem to reach its dark-theme counterpart.
DARK_SUFFIX = "_drk"


# ---------------------------------------------------------------------------
# Node families and their states -- enum values ARE the asset stems
# ---------------------------------------------------------------------------
class NodeFamily(str, Enum):
    """The five node families, in left-to-right diagram order."""

    QUALITY = "quality"
    APP = "app"
    SANDBOX = "sandbox"
    SANDBOX1 = "sandbox1"
    SANDBOX2 = "sandbox2"


class QualityState(str, Enum):
    """The quality/target database connection's three states.

    `ProjectCapabilityStatus` says nothing about the target connection, so the
    caller derives this from the target profile -- see `quality_state`.
    """

    #: Gray padlock: no target connection configured yet (NOT an auth failure).
    NOT_SET_UP = "quality_connection_not_set_up"
    #: Red: configured, but the connection attempt failed.
    OFFLINE = "quality_offline"
    #: Green: configured and reachable.
    CONNECTION_OK = "quality_connection_ok"


class AppState(str, Enum):
    """The project's tier, and nothing else (§18.8's corrected 3-state model)."""

    #: No project is open at all -- tier 1, which `ProjectTier` cannot express.
    STANDALONE = "app_standalone"
    #: Tier 2: a project is open but has no working sandbox.
    PROJECT_NOT_SETUP = "app_project_not_setup"
    #: Tier 3: a project is open with a working sandbox.
    PROJECT_SETUP = "app_project_setup"


class SandboxState(str, Enum):
    """The sandbox database's live connectivity -- 3 icons over 4 conditions."""

    #: Gray: no sandbox configured for this project. Also the only state that
    #: never renders, because it triggers the absence rule instead.
    NOT_SET_UP = "sandbox_not_set_up"
    #: Green: configured and reachable -- including reachable-but-tools-missing.
    CONNECTED = "sandbox_connected"
    #: Red: configured but currently unreachable.
    OFFLINE = "sandbox_offline"


class Sandbox1State(str, Enum):
    """The sandbox's data-fill status (§18.5 D2a)."""

    #: Schema-only, or a with-data sandbox whose clone has not (yet) landed.
    EMPTY = "sandbox1_empty"
    #: Data cloned in via `pg_restore`.
    FILLED = "sandbox1_filled"


class Sandbox2State(str, Enum):
    """Whether `plpgsql_check` is installed in the sandbox -- an install-state
    marker, never a per-routine lint result (that lives in the Audit panel)."""

    INSTALLED = "sandbox2_plpgsql_check_installed"
    NOT_INSTALLED = "sandbox2_plpgsql_check_not_installed"


class ConnectorKind(str, Enum):
    """The three connectors. Values are asset stems; connectors have no
    per-state variants (see the module docstring)."""

    QUALITY_APP = "connector_quality-app"
    APP_SANDBOX = "connector_app-sandbox"
    #: Sandbox -> (sandbox1, sandbox2): one asset that visually splits in two.
    SANDBOX_DB = "connector_sandbox-db"


# ---------------------------------------------------------------------------
# degraded_reason classification -- one predicate, not scattered string tests
# ---------------------------------------------------------------------------
#: `determine_project_tier`'s verbatim reason for "never configured". Compared
#: exactly, as §18.8's absence rule specifies.
NO_SANDBOX_REASON = "no local sandbox configured for this project"

#: `determine_project_tier` formats these two as `f"{prefix} …"`.
_UNREACHABLE_PREFIX = "sandbox unreachable:"
_UNAVAILABLE_PREFIX = "sandbox unavailable:"

#: The external binaries whose absence `determine_project_tier` reports as a
#: `sandbox unavailable:` reason (only ever consulted for `WITH_DATA`).
_CLONE_TOOLS = ("pg_dump", "pg_restore", "psql")


class SandboxDegradation(str, Enum):
    """Why the sandbox is not fully working -- the 4-way backing distinction
    the 3-icon Sandbox node cannot show, kept for the click-through window."""

    #: Nothing wrong: tier 3.
    NONE = "none"
    #: Never configured. Triggers the absence rule.
    NOT_CONFIGURED = "not_configured"
    #: Configured, probe could not reach it.
    UNREACHABLE = "unreachable"
    #: Reachable, but `pg_dump`/`pg_restore` are missing from `PATH`.
    TOOLS_MISSING = "tools_missing"
    #: Degraded for a reason this module does not recognize. Rendered as
    #: `sandbox_offline` -- an unexplained degradation is not claimed healthy.
    OTHER = "other"


def classify_degraded_reason(reason: str | None) -> SandboxDegradation:
    """Bucket `ProjectCapabilityStatus.degraded_reason` into its backing cause.

    `degraded_reason` is human-readable free-ish text, so this is the single
    place that pattern-matches it; everything else keys off the enum. An
    unrecognized non-empty reason yields `OTHER` rather than pretending the
    sandbox is fine.
    """
    if reason is None:
        return SandboxDegradation.NONE
    if reason == NO_SANDBOX_REASON:
        return SandboxDegradation.NOT_CONFIGURED
    if reason.startswith(_UNREACHABLE_PREFIX):
        return SandboxDegradation.UNREACHABLE
    if reason.startswith(_UNAVAILABLE_PREFIX) and any(
        tool in reason for tool in _CLONE_TOOLS
    ):
        return SandboxDegradation.TOOLS_MISSING
    return SandboxDegradation.OTHER


def missing_clone_tools(reason: str | None) -> tuple[str, ...]:
    """The clone tools named in a `TOOLS_MISSING` reason, for the Sandbox
    node's click-through text ("names the missing tool"). Empty for every
    other degradation.
    """
    if classify_degraded_reason(reason) is not SandboxDegradation.TOOLS_MISSING:
        return ()
    return tuple(tool for tool in _CLONE_TOOLS if reason is not None and tool in reason)


# ---------------------------------------------------------------------------
# Per-node state derivation
# ---------------------------------------------------------------------------
def quality_state(configured: bool, probe_error: str | None) -> QualityState:
    """The Quality node's state from the target connection profile.

    `configured` is "a target connection profile exists at all"; `probe_error`
    is the last connection attempt's failure text (None when it succeeded).
    Not-configured wins over any stale error: an unconfigured connection has
    not failed, it has not been tried.
    """
    if not configured:
        return QualityState.NOT_SET_UP
    if probe_error is not None:
        return QualityState.OFFLINE
    return QualityState.CONNECTION_OK


def app_state(status: ProjectCapabilityStatus | None) -> AppState:
    """The App node's state -- tier only.

    `status is None` means **no project is open**, which is tier 1 and which
    `ProjectCapabilityStatus`/`ProjectTier` deliberately cannot express (the
    enum has no tier-1 member; it models an already-open project). That fact
    has to arrive from outside the probe result, so it arrives as `None`.
    """
    if status is None:
        return AppState.STANDALONE
    if status.tier is ProjectTier.DEVELOPMENT:
        return AppState.PROJECT_SETUP
    return AppState.PROJECT_NOT_SETUP


def sandbox_state(status: ProjectCapabilityStatus) -> SandboxState:
    """The Sandbox node's state -- 3 icons over the 4-way backing distinction.

    Tools-missing renders green, identically to a fully working sandbox; only
    `SandboxDegradation` tells them apart, for the click-through text.
    """
    if status.tier is ProjectTier.DEVELOPMENT:
        return SandboxState.CONNECTED
    degradation = classify_degraded_reason(status.degraded_reason)
    if degradation is SandboxDegradation.NOT_CONFIGURED:
        return SandboxState.NOT_SET_UP
    if degradation is SandboxDegradation.TOOLS_MISSING:
        # Reachable -- the sandbox works, one external binary is absent. Same
        # green icon, per §18.8; the missing tool is named in click-through.
        return SandboxState.CONNECTED
    # UNREACHABLE, OTHER, and a tier-2 status with no reason at all: red.
    return SandboxState.OFFLINE


def sandbox1_state(mode: SandboxMode, data_clone_done: bool) -> Sandbox1State:
    """The Sandbox1 node's data-fill state.

    `SCHEMA_ONLY` is always `EMPTY` -- it never clones data. `WITH_DATA` is
    `FILLED` only once the clone has actually landed (`data_clone_done`).

    No "clone in progress" or "clone failed" asset exists, and §18.8 forbids
    inventing one, so both conditions fall back to `EMPTY`: whatever the clone
    is doing, the data is not in the sandbox yet, and `EMPTY` is the honest
    state of the two available.
    """
    if mode is SandboxMode.WITH_DATA and data_clone_done:
        return Sandbox1State.FILLED
    return Sandbox1State.EMPTY


def collapse_plpgsql_check_state(state: str) -> Sandbox2State:
    """Collapse `SandboxCapabilities.plpgsql_check_state`'s 4 values onto
    Sandbox2's 2 icons: only `"installed"` is installed; `"installable"`,
    `"absent"` and `"unknown"` all mean not installed (extension available but
    not created / not available / probe failed). Any unrecognized value is
    treated as not installed -- this node must never claim an install it has
    not seen.
    """
    return Sandbox2State.INSTALLED if state == "installed" else Sandbox2State.NOT_INSTALLED


def sandbox2_state(capabilities: SandboxCapabilities) -> Sandbox2State:
    """The Sandbox2 node's state from a capability probe."""
    return collapse_plpgsql_check_state(capabilities.plpgsql_check_state)


# ---------------------------------------------------------------------------
# Asset resolution
# ---------------------------------------------------------------------------
def asset_filename(stem: str, dark: bool) -> str:
    """`("app_standalone", dark=True)` -> `"app_standalone_drk.png"`.

    `stem` accepts a bare string or any of this module's state enums (whose
    values are stems), since they are `str` subclasses.
    """
    return f"{stem}{DARK_SUFFIX if dark else ''}{ASSET_EXTENSION}"


def asset_path(filename: str):
    """The bundled `resources/status/` traversable for `filename`.

    Same `importlib.resources` convention as `ui/icons.py` -- resolves inside
    the installed package, so it works from a zip/wheel install too. Builds the
    path only; reading is the caller's (Qt's) business.
    """
    return files("pgtp_editor") / "resources" / "status" / filename


def all_asset_stems() -> tuple[str, ...]:
    """Every stem this module can emit -- all node states plus all connectors.

    The guard for a typo'd stem shipping as a silently missing image: a test
    walks this and asserts both theme variants exist on disk.
    """
    stems: list[str] = []
    for enum_type in (
        QualityState,
        AppState,
        SandboxState,
        Sandbox1State,
        Sandbox2State,
        ConnectorKind,
    ):
        stems.extend(member.value for member in enum_type)
    return tuple(stems)


# ---------------------------------------------------------------------------
# The diagram
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StatusNode:
    """One rendered node: which family, what state, which image file."""

    family: NodeFamily
    state: str
    asset: str


@dataclass(frozen=True)
class StatusConnector:
    """One rendered connector and its (single, stateless) image file."""

    kind: ConnectorKind
    asset: str


@dataclass(frozen=True)
class ProjectStatusDiagram:
    """Everything the §18.8 window needs, from one call.

    `nodes` and `connectors` are in left-to-right diagram order and contain
    **only what renders** -- the absence rule has already removed the sandbox
    trio when no sandbox was ever configured, so the widget layer iterates
    rather than deciding. `sandbox_degradation` / `missing_tools` /
    `degraded_reason` carry the detail no icon shows, for click-through text.
    """

    nodes: tuple[StatusNode, ...]
    connectors: tuple[StatusConnector, ...]
    dark: bool
    sandbox_degradation: SandboxDegradation
    missing_tools: tuple[str, ...] = ()
    degraded_reason: str | None = None

    @property
    def sandbox_present(self) -> bool:
        """Whether the sandbox trio renders at all."""
        return self.node(NodeFamily.SANDBOX) is not None

    def node(self, family: NodeFamily) -> StatusNode | None:
        """The rendered node for `family`, or None when it is absent."""
        for node in self.nodes:
            if node.family is family:
                return node
        return None

    def assets(self) -> tuple[str, ...]:
        """Every image filename this diagram renders, nodes then connectors."""
        return tuple(node.asset for node in self.nodes) + tuple(
            connector.asset for connector in self.connectors
        )


def build_diagram(
    *,
    status: ProjectCapabilityStatus | None,
    quality: QualityState,
    sandbox_mode: SandboxMode = SandboxMode.SCHEMA_ONLY,
    data_clone_done: bool = False,
    dark: bool = True,
) -> ProjectStatusDiagram:
    """Derive the whole diagram from one capability probe plus the caller's
    out-of-band facts.

    Arguments:
        status: the probe result for the open project, or **None when no
            project is open at all** -- tier 1, which `ProjectCapabilityStatus`
            cannot represent (see `app_state`).
        quality: the Quality node's state, derived by the caller from the
            target connection profile (`quality_state`), which the project
            capability probe says nothing about.
        sandbox_mode: the project's recorded `ProjectSettings.sandbox_mode`.
        data_clone_done: whether D2a's clone has actually landed in the
            sandbox. Only consulted for `WITH_DATA`.
        dark: the app's current theme -- True selects the `_drk` assets. A
            plain boolean, passed in: this module reads no Qt and no globals.

    The sandbox trio (Sandbox, Sandbox1, Sandbox2) and the connectors reaching
    it are omitted entirely when no project is open or when no sandbox was ever
    configured; a configured-but-broken sandbox keeps all three.
    """
    degraded_reason = status.degraded_reason if status is not None else None
    degradation = (
        classify_degraded_reason(degraded_reason)
        if status is not None
        else SandboxDegradation.NOT_CONFIGURED
    )

    nodes = [
        StatusNode(NodeFamily.QUALITY, quality.value, asset_filename(quality.value, dark)),
    ]
    app = app_state(status)
    nodes.append(StatusNode(NodeFamily.APP, app.value, asset_filename(app.value, dark)))
    connectors = [
        StatusConnector(
            ConnectorKind.QUALITY_APP,
            asset_filename(ConnectorKind.QUALITY_APP.value, dark),
        )
    ]

    # Absence rule: no project open, or a sandbox that was never configured,
    # means the sandbox half of the diagram does not exist -- not that it is
    # drawn disabled.
    if status is not None and degradation is not SandboxDegradation.NOT_CONFIGURED:
        sandbox = sandbox_state(status)
        fill = sandbox1_state(sandbox_mode, data_clone_done)
        check = sandbox2_state(status.capabilities)
        nodes.extend(
            (
                StatusNode(
                    NodeFamily.SANDBOX, sandbox.value, asset_filename(sandbox.value, dark)
                ),
                StatusNode(
                    NodeFamily.SANDBOX1, fill.value, asset_filename(fill.value, dark)
                ),
                StatusNode(
                    NodeFamily.SANDBOX2, check.value, asset_filename(check.value, dark)
                ),
            )
        )
        connectors.extend(
            (
                StatusConnector(
                    ConnectorKind.APP_SANDBOX,
                    asset_filename(ConnectorKind.APP_SANDBOX.value, dark),
                ),
                StatusConnector(
                    ConnectorKind.SANDBOX_DB,
                    asset_filename(ConnectorKind.SANDBOX_DB.value, dark),
                ),
            )
        )

    return ProjectStatusDiagram(
        nodes=tuple(nodes),
        connectors=tuple(connectors),
        dark=dark,
        sandbox_degradation=degradation,
        missing_tools=missing_clone_tools(degraded_reason),
        degraded_reason=degraded_reason,
    )
