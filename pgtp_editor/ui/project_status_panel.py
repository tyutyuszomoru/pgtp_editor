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

# pgtp_editor/ui/project_status_panel.py
"""ProjectStatusPanel: the §18.8 Project Status window — project health drawn as
a node-and-connector diagram.

Reads left to right as a chain that splits at the end::

    [quality] --> [app] --> [sandbox] --> [sandbox1]  (upper)
                                      \\-> [sandbox2]  (lower)

Every node and connector is one bundled SVG from ``resources/status/`` (a light
and a ``_drk`` dark variant each). This module **paints**; it decides nothing.
All state derivation, the absence rule, and theme-variant filename selection
live in the pure `project_status_model`, and this widget only iterates
`ProjectStatusDiagram.nodes` / `.connectors` — which are already in left-to-right
order and already contain **only what renders**. When no sandbox was ever
configured, the sandbox trio is simply not in those lists and the diagram ends at
the app node (absent, never a dead disabled control — §18.5 carve-out 2, §18.7).

**Geometry.** The assets were sliced from one drawing at one scale, so they are
all displayed at the same `ASSET_SCALE` multiple of their own intrinsic size
rather than fitted to a common box. Each asset is then centered into a
transparent padding pixmap of a shared box height, which is what makes every
icon's vertical centre line up across the chain without per-asset fudge factors;
the branch column and the splitting sandbox→db connector are offset from the same
computed centre line. Nothing is ever magnified past its own resolution: the SVG
is *rendered* straight to ``logical × devicePixelRatio`` device pixels and the
pixmap is tagged with that ratio, so the diagram is crisp at any DPI, and a
change of screen ratio rebuilds it rather than stretching stale pixmaps.

**Click-through — two patterns, exactly as §18.8 specifies.**

- *Quality* and *App* open a **one-step** window. Quality's shows connection info
  plus a reconnect action. App's is a deliberate placeholder: §18.8 records its
  contents as unspecified by the owner and forbids inventing them, so it states
  the tier plainly and nothing more (see the ``TODO(§29)``).
- *Sandbox* opens a one-step status/help window. In the tools-missing condition —
  which renders the *same* green ``sandbox_connected`` icon, not a distinct one —
  the window names the missing tool(s) and offers a help affordance.
- *Sandbox1* and *Sandbox2* open a **two-step** status window with an embedded
  action button: "run/redo data clone" and "install the plpgsql_check
  extension". Never a single click that fires the action. When Sandbox2 is
  already installed the window is purely informational — nothing is left to
  install, so no button is offered.

**Nothing here executes anything.** Every action is an injected callback,
defaulting to None, and its affordance is *absent* when not supplied. This widget
opens no connections, runs no DDL, resolves no help topics, and never imports
`MainWindow`. The main session wires `refresh_project_capability_status()` to
`on_refresh`, `install_plpgsql_check(session)` to `on_install_plpgsql_check`, and
the in-app manual (F1 / Help ▸ Manual, §24) to `on_show_help` — the app has no
topic-anchored deep-link mechanism and this widget does not invent one.

Non-modal throughout: the panel is a plain widget (dock it or wrap it in a
window) and every click-through window is a non-modal `QDialog` opened with
``show()``. There is no ``.exec()`` anywhere, and the opened windows are exposed
(`last_window`, `open_windows`) so tests can read them without a modal call.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from math import ceil

from PySide6.QtCore import QByteArray, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .project_status_model import (
    ConnectorKind,
    NodeFamily,
    ProjectStatusDiagram,
    SandboxDegradation,
    StatusConnector,
    StatusNode,
    asset_filename,
    asset_path,
)

#: Logical pixels per unit of an asset's own intrinsic (SVG ``defaultSize``) size.
#: The art came from a single drawing, so one shared factor keeps the diagram's
#: internal proportions truthful — it is *layout*, not magnification: the SVG is
#: rendered at the resulting size, never stretched to it.
#:
#: The value reproduces the sizes the diagram was laid out at when the assets
#: were rasters: those slices were 96 dpi exports of the same millimetre-sized
#: drawing shown at 2×, while Qt reads an SVG's ``mm`` dimensions at 90 dpi — so
#: ``2 × 96/90`` lands the vector render within a pixel of the old layout instead
#: of shrinking the whole diagram by 7%.
ASSET_SCALE = 2.0 * (96.0 / 90.0)

#: `ASSET_SCALE` for an asset that turns out to be a raster rather than a vector
#: (see `_raster_fallback_pixmap`): a 96 dpi export of the same drawing is already
#: 96/90 larger than Qt's reading of the SVG, so it needs only the plain 2×.
_RASTER_ASSET_SCALE = 2.0

#: Fixed node width — captions wrap inside it, so a long state line can never
#: shove the chain out of alignment.
NODE_WIDTH = 116

#: Node padding: above the icon box, between icon and caption, and below.
NODE_TOP_PAD = 8
NODE_GAP = 10
NODE_BOTTOM_PAD = 8

#: Fixed caption block height (name line + wrapped state line).
CAPTION_HEIGHT = 42

#: Minimum vertical gap between the two branch nodes when the splitting
#: connector is shorter than they are tall.
MIN_BRANCH_GAP = 12

#: Human-readable node names, in diagram order.
_NODE_TITLES = {
    NodeFamily.QUALITY: "Quality database",
    NodeFamily.APP: "Project",
    NodeFamily.SANDBOX: "Sandbox",
    NodeFamily.SANDBOX1: "Sandbox data",
    NodeFamily.SANDBOX2: "plpgsql_check",
}

#: Human-readable state lines, keyed by the model's state stem (which is also
#: the asset stem, so there is no second table to drift out of step).
_STATE_CAPTIONS = {
    "quality_connection_not_set_up": "Not configured",
    "quality_offline": "Unreachable",
    "quality_connection_ok": "Connected",
    "app_standalone": "Standalone editor",
    "app_project_not_setup": "Quality project",
    "app_project_setup": "Development project",
    "sandbox_not_set_up": "Not configured",
    "sandbox_connected": "Connected",
    "sandbox_offline": "Unreachable",
    # BUG-035: "Schema only" is now only ever shown once the schema has been
    # SEEN in the sandbox. The two states below are the honest lower rungs
    # that used to be mislabelled as it; neither may contain the word
    # "schema" as a claim.
    "sandbox1_unknown": "Not checked",
    "sandbox1_not_provisioned": "Nothing provisioned",
    "sandbox1_empty": "Schema only",
    "sandbox1_filled": "Data cloned",
    "sandbox2_plpgsql_check_installed": "Installed",
    "sandbox2_plpgsql_check_not_installed": "Not installed",
}

#: The App node's window says the tier plainly — the node caption stays short so
#: it never wraps mid-word, and the full sentence lives here (§18 taxonomy).
_APP_TIER_LINES = {
    "app_standalone": "Tier 1 — standalone editor: no project is open.",
    "app_project_not_setup": (
        "Tier 2 — quality project: a project is open, but it has no working sandbox."
    ),
    "app_project_setup": (
        "Tier 3 — development project: a project is open with a working sandbox."
    ),
}

#: The two node families that hang off the split, upper then lower.
_BRANCH_FAMILIES = (NodeFamily.SANDBOX1, NodeFamily.SANDBOX2)

#: Which connector sits between which pair of chain nodes.
_CHAIN_CONNECTOR_AFTER = {
    NodeFamily.QUALITY: ConnectorKind.QUALITY_APP,
    NodeFamily.APP: ConnectorKind.APP_SANDBOX,
}


def _asset_bytes(filename: str) -> QByteArray | None:
    """Read one bundled asset, or None when it is missing/unreadable.

    Goes through `importlib.resources` bytes rather than a filesystem path so it
    keeps working from a zip/wheel install, exactly like `ui/icons.py`.
    """
    try:
        return QByteArray(asset_path(filename).read_bytes())
    except (OSError, ValueError):
        return None


def _scaled_pixmap(filename: str, dpr: float) -> QPixmap:
    """Render one bundled asset at `ASSET_SCALE` logical size, crisp at `dpr`.

    Vector all the way to the device pixels: the SVG is rendered directly into a
    ``logical × dpr`` image, so there is no upscaling step that could soften it.
    The pixmap is tagged with `dpr`, which is what makes its *logical* size come
    back out at exactly the intended layout size.

    Falls back to loading the file as a raster when it is not valid SVG — one
    bundled asset is a PNG that was saved under an ``.svg`` name, and rendering
    it slightly soft beats dropping the node out of the diagram. Returns a null
    pixmap when the file is missing or unreadable altogether: the caller still
    reserves the box, so a missing asset leaves a gap rather than collapsing the
    diagram's alignment.
    """
    data = _asset_bytes(filename)
    if data is None:
        return QPixmap()
    renderer = QSvgRenderer(data)
    native = renderer.defaultSize() if renderer.isValid() else QSize()
    if not renderer.isValid() or native.isEmpty():
        return _raster_fallback_pixmap(data, dpr)
    logical = QSize(
        max(1, round(native.width() * ASSET_SCALE)),
        max(1, round(native.height() * ASSET_SCALE)),
    )
    device = QSize(
        max(1, round(logical.width() * dpr)), max(1, round(logical.height() * dpr))
    )
    image = QImage(device, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    rendered = QPixmap.fromImage(image)
    rendered.setDevicePixelRatio(dpr)
    return rendered


def _raster_fallback_pixmap(data: QByteArray, dpr: float) -> QPixmap:
    """Last resort for an asset that is not valid SVG: treat it as an image.

    Scaled by `_RASTER_ASSET_SCALE`, which puts a 96 dpi raster slice at the same
    displayed size as the 90 dpi-read vector rendering of the same drawing, so
    the diagram's proportions and alignment do not depend on which asset happens
    to be a raster. This one *does* stretch (smoothly), because a raster has no
    other option — the fix for softness there is a real SVG, not more code.
    """
    source = QPixmap()
    if not source.loadFromData(data):
        return QPixmap()
    logical = QSize(
        max(1, round(source.width() * _RASTER_ASSET_SCALE)),
        max(1, round(source.height() * _RASTER_ASSET_SCALE)),
    )
    device = QSize(
        max(1, round(logical.width() * dpr)), max(1, round(logical.height() * dpr))
    )
    scaled = source.scaled(
        device,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(dpr)
    return scaled


def _logical_size(pixmap: QPixmap) -> QSize:
    """A pixmap's size in layout (logical) pixels, honouring its DPR.

    Deliberately a **ceiling**, not a rounding. Device pixels need not divide
    evenly by a fractional DPR (1.25, 1.5, 1.75 …), and rounding down would hand
    out a box a fraction of a pixel shorter than the art it must hold — shaved
    off the edge, invisible on a chunky icon but fatal on a connector only a few
    pixels tall. A ceiling can only ever leave a sub-pixel of transparent slack.

    This is the *single* definition of "how big is this pixmap in the layout":
    the shared box heights, the pads and the connector labels all come from it,
    so they cannot disagree by a rounding.
    """
    if pixmap.isNull():
        return QSize(0, 0)
    ratio = pixmap.devicePixelRatio() or 1.0
    return QSize(ceil(pixmap.width() / ratio), ceil(pixmap.height() / ratio))


def _padded_box(pixmap: QPixmap, box: QSize) -> QSize:
    """The box `pixmap` is actually padded into: `box`, grown to fit if needed.

    `box` carries the row's shared height, which is what aligns the icons — but
    it is only ever *shared*, never a promise that the art fits inside it. When
    an icon is larger than `box` in either axis, growing the box is the only
    non-destructive answer: the alternative (clamping the centering offset at
    zero) silently crops whatever overflows.
    """
    return box.expandedTo(_logical_size(pixmap))


def _boxed_pixmap(pixmap: QPixmap, box: QSize, dpr: float) -> QPixmap:
    """Center `pixmap` in a transparent `box`-sized (logical) pixmap.

    This is the whole alignment trick: every node's icon label ends up exactly
    the same height, so their optical centres share one line no matter how
    differently proportioned the underlying art is.

    `dpr` is passed in rather than read off `pixmap`: the pad and the icon must
    be sized for one single ratio, and the caller is the only place that knows
    which ratio the whole diagram was built for.
    """
    box = _padded_box(pixmap, box)
    # Ceiling again, for the same reason `_logical_size` uses one: the pad must
    # be at least as many device pixels as the icon it holds, and `round` can
    # land a device pixel short of `box * dpr`.
    device = QSize(max(1, ceil(box.width() * dpr)), max(1, ceil(box.height() * dpr)))
    padded = QPixmap(device)
    padded.setDevicePixelRatio(dpr)
    padded.fill(Qt.GlobalColor.transparent)
    if not pixmap.isNull():
        size = _logical_size(pixmap)
        # `box` fits `size` by construction now, so neither offset can clamp.
        painter = QPainter(padded)
        painter.drawPixmap(
            QPoint((box.width() - size.width()) // 2, (box.height() - size.height()) // 2),
            pixmap,
        )
        painter.end()
    return padded


class _DiagramNode(QFrame):
    """One clickable node: icon over a two-line caption.

    A frame rather than a `QToolButton` because the connectors must align to the
    icon's centre to the pixel, which means owning the vertical metrics instead
    of inheriting a style's button margins. Keyboard-activatable (Space/Return),
    focusable, and it exposes `click()` so tests activate it the same way they
    would a button.
    """

    clicked = Signal()

    def __init__(self, family: NodeFamily, title: str, state_text: str) -> None:
        super().__init__()
        self.family = family
        self._hovered = False
        self.setObjectName(f"statusNode_{family.value}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"{title}: {state_text}")
        self.setToolTip(f"{title} — {state_text}")

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        title_font = QFont(self.title_label.font())
        title_font.setBold(True)
        self.title_label.setFont(title_font)

        self.state_label = QLabel(state_text)
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.state_label.setWordWrap(True)
        state_font = QFont(self.state_label.font())
        state_font.setPointSizeF(max(7.0, state_font.pointSizeF() - 1.0))
        self.state_label.setFont(state_font)
        self._dim(self.state_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, NODE_TOP_PAD, 4, NODE_BOTTOM_PAD)
        layout.setSpacing(0)
        layout.addWidget(self.icon_label)
        layout.addSpacing(NODE_GAP)
        layout.addWidget(self.title_label)
        layout.addWidget(self.state_label, 1)

    def _dim(self, label: QLabel) -> None:
        """Fade a label using the palette's own text colour, so it reads in both
        themes without a hard-coded grey."""
        palette = label.palette()
        color = palette.color(self.foregroundRole())
        color.setAlpha(165)
        palette.setColor(label.foregroundRole(), color)
        label.setPalette(palette)

    def set_pixmap(self, pixmap: QPixmap, box: QSize) -> None:
        self.icon_label.setFixedSize(box)
        self.icon_label.setPixmap(pixmap)
        self.setFixedSize(
            QSize(
                NODE_WIDTH,
                NODE_TOP_PAD + box.height() + NODE_GAP + CAPTION_HEIGHT + NODE_BOTTOM_PAD,
            )
        )

    #: -- interaction ------------------------------------------------------
    def click(self) -> None:
        """Activate the node, as a click or Space would."""
        self.clicked.emit()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Hover wash and focus ring, both derived from the palette highlight so
        they behave under either theme."""
        if self._hovered or self.hasFocus():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            highlight = QColor(self.palette().color(QPalette.ColorRole.Highlight))
            rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
            if self._hovered:
                wash = QColor(highlight)
                wash.setAlpha(34)
                painter.setBrush(wash)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect, 8, 8)
            if self.hasFocus():
                pen_color = QColor(highlight)
                pen_color.setAlpha(190)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(pen_color)
                painter.drawRoundedRect(rect, 8, 8)
            painter.end()
        super().paintEvent(event)


class NodeWindow(QDialog):
    """A node's click-through window: some lines of text, at most one action.

    Non-modal (`show()`, never `.exec()`). `body_text` and `action_button` /
    `help_button` are the read seams — the panel keeps a reference to the last
    window it opened so a test can assert on its contents directly.
    """

    def __init__(self, parent: QWidget, family: NodeFamily, title: str) -> None:
        super().__init__(parent)
        self.family = family
        self.setObjectName(f"statusWindow_{family.value}")
        self.setModal(False)
        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMinimumWidth(380)

        self._lines: list[str] = []
        self.action_button: QPushButton | None = None
        self.help_button: QPushButton | None = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 14)
        self._layout.setSpacing(10)

        heading = QLabel(title)
        heading_font = QFont(heading.font())
        heading_font.setBold(True)
        heading.setFont(heading_font)
        self._layout.addWidget(heading)

        self._body = QVBoxLayout()
        self._body.setSpacing(6)
        self._layout.addLayout(self._body)
        self._layout.addStretch(1)

        self._buttons = QHBoxLayout()
        self._buttons.setSpacing(8)
        # Leading stretch: actions align right, under the Close button, instead
        # of stretching across the whole window.
        self._buttons.addStretch(1)
        self._layout.addLayout(self._buttons)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.close)
        self._layout.addWidget(close_box)

    def add_line(self, text: str) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._body.addWidget(label)
        self._lines.append(text)

    def add_action(self, text: str, callback: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.setDefault(True)
        button.clicked.connect(callback)
        self._buttons.addWidget(button)
        self.action_button = button
        return button

    def add_help(self, text: str, callback: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(callback)
        self._buttons.addWidget(button)
        self.help_button = button
        return button

    @property
    def body_text(self) -> str:
        """Every body line, newline-joined — the assertion surface for tests."""
        return "\n".join(self._lines)


class ProjectStatusPanel(QWidget):
    """The §18.8 Project Status window.

    Constructor kwargs (all optional; every action's affordance is *absent* when
    its callback is None, never shown disabled):

    ``diagram``
        The initial `ProjectStatusDiagram`. May be None — the panel then renders
        its empty state until `set_diagram` or `refresh` supplies one.
    ``on_refresh``
        Called when the panel is first shown and by `refresh()`: §18.8 requires
        opening this window to trigger a **fresh** capability probe, not a
        passive read of a cached result. Wire it to
        `MainWindow.refresh_project_capability_status()`. It may return a new
        `ProjectStatusDiagram` to re-render immediately, or None and let the
        caller push one later via `set_diagram`.
    ``on_reconnect_quality``
        The Quality window's reconnect action.
    ``on_run_data_clone``
        Sandbox1's embedded button (§18.5 D2a).
    ``on_install_plpgsql_check``
        Sandbox2's embedded button — `install_plpgsql_check(session)`. Offered
        only in the not-installed state.
    ``on_show_help``
        The Sandbox window's help affordance for the tools-missing condition.
        Wire it to the in-app manual (F1 / Help ▸ Manual); this widget resolves
        no topics and builds no deep-link mechanism.
    ``quality_summary`` / ``sandbox_summary``
        Connection detail lines for the respective windows, supplied by the
        caller (this widget reads no connection profile itself).
    """

    #: Emitted with the activated node's family value, for main-session wiring.
    node_activated = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        diagram: ProjectStatusDiagram | None = None,
        on_refresh: Callable[[], ProjectStatusDiagram | None] | None = None,
        on_reconnect_quality: Callable[[], None] | None = None,
        on_run_data_clone: Callable[[], None] | None = None,
        on_install_plpgsql_check: Callable[[], None] | None = None,
        on_show_help: Callable[[], None] | None = None,
        quality_summary: str = "",
        sandbox_summary: str = "",
    ) -> None:
        super().__init__(parent)
        self._diagram = diagram
        self._on_refresh = on_refresh
        self._on_reconnect_quality = on_reconnect_quality
        self._on_run_data_clone = on_run_data_clone
        self._on_install_plpgsql_check = on_install_plpgsql_check
        self._on_show_help = on_show_help
        self._quality_summary = quality_summary
        self._sandbox_summary = sandbox_summary
        self._refreshed_on_show = False
        #: The device pixel ratio the current pixmaps were rendered for, and the
        #: window whose ratio changes we are already listening to.
        self._rendered_dpr = 0.0
        self._dpr_window = None

        #: Live node widgets by family — the click seam for tests and wiring.
        self.node_widgets: dict[NodeFamily, _DiagramNode] = {}
        #: Every window this panel has opened and not yet dropped, newest last.
        self.open_windows: list[NodeWindow] = []

        self.title_label = QLabel("Project status")
        title_font = QFont(self.title_label.font())
        title_font.setBold(True)
        title_font.setPointSizeF(title_font.pointSizeF() + 1.0)
        self.title_label.setFont(title_font)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)

        self.refresh_button = QPushButton("Re-check")
        self.refresh_button.clicked.connect(self.refresh)
        # No dead controls: without a probe callback there is nothing to re-check.
        self.refresh_button.setVisible(on_refresh is not None)

        header = QHBoxLayout()
        header.setSpacing(10)
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(self.title_label)
        header_text.addWidget(self.summary_label)
        header.addLayout(header_text, 1)
        header.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignTop)

        #: The diagram lives inside a scroll area so a narrow dock never clips
        #: it — the art is fixed-size by design.
        self.diagram_widget = QWidget()
        self.diagram_widget.setObjectName("projectStatusDiagram")
        #: The art row, vertically centered in whatever height the dock gives us.
        self._diagram_row = QWidget()
        self._diagram_layout = QHBoxLayout(self._diagram_row)
        self._diagram_layout.setContentsMargins(20, 18, 20, 18)
        self._diagram_layout.setSpacing(2)
        outer_diagram = QVBoxLayout(self.diagram_widget)
        outer_diagram.setContentsMargins(0, 0, 0, 0)
        outer_diagram.setSpacing(0)
        outer_diagram.addStretch(1)
        outer_diagram.addWidget(self._diagram_row)
        outer_diagram.addStretch(1)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.diagram_widget)
        self.scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.hint_label = QLabel("Click a node for details and actions.")
        self.hint_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.scroll_area, 1)
        layout.addWidget(self.hint_label)

        self.setMinimumSize(QSize(420, 320))
        self._rebuild()

    # -- public API ---------------------------------------------------------

    @property
    def diagram(self) -> ProjectStatusDiagram | None:
        """The diagram currently rendered."""
        return self._diagram

    def set_diagram(self, diagram: ProjectStatusDiagram | None) -> None:
        """Re-render from a freshly derived diagram. The only way state enters
        this widget — it never derives state itself."""
        self._diagram = diagram
        self._rebuild()

    def set_dark(self, dark: bool) -> None:
        """Re-render in the given theme (True = the ``_drk`` assets).

        Takes the same boolean the **Light Theme** menu toggle already tracks
        (inverted): ``panel.set_dark(not light)``. It re-resolves the current
        diagram's asset filenames rather than re-deriving state, so a theme
        switch cannot silently change what the diagram claims — and it adds no
        second theme-detection mechanism.
        """
        if self._diagram is None or self._diagram.dark == dark:
            self._diagram = (
                None if self._diagram is None else replace(self._diagram, dark=dark)
            )
            self._rebuild()
            return
        self._diagram = replace(
            self._diagram,
            dark=dark,
            nodes=tuple(
                StatusNode(node.family, node.state, asset_filename(node.state, dark))
                for node in self._diagram.nodes
            ),
            connectors=tuple(
                StatusConnector(
                    connector.kind, asset_filename(connector.kind.value, dark)
                )
                for connector in self._diagram.connectors
            ),
        )
        self._rebuild()

    def set_light_theme(self, light: bool) -> None:
        """Convenience mirror of `MainWindow._light_theme_action.isChecked()`."""
        self.set_dark(not light)

    def set_connection_summaries(
        self, quality: str | None = None, sandbox: str | None = None
    ) -> None:
        """Supply the connection detail lines the click-through windows show."""
        if quality is not None:
            self._quality_summary = quality
        if sandbox is not None:
            self._sandbox_summary = sandbox

    def refresh(self) -> None:
        """Trigger a fresh capability probe through the injected callback.

        §18.8: opening this window is itself a probe trigger. When the callback
        returns a diagram it is rendered at once; when it returns None the caller
        is expected to push one via `set_diagram`.
        """
        if self._on_refresh is None:
            return
        result = self._on_refresh()
        if isinstance(result, ProjectStatusDiagram):
            self.set_diagram(result)

    def node_widget(self, family: NodeFamily) -> _DiagramNode | None:
        """The rendered widget for `family`, or None when the node is absent."""
        return self.node_widgets.get(family)

    @property
    def last_window(self) -> NodeWindow | None:
        """The most recently opened click-through window."""
        return self.open_windows[-1] if self.open_windows else None

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """First show triggers the on-open re-probe seam."""
        super().showEvent(event)
        self._watch_device_pixel_ratio()
        if self._diagram is not None and self._rendered_dpr != self._current_dpr():
            # Shown for the first time on a screen whose ratio differs from the
            # one the constructor saw (an unparented widget reports 1.0).
            self._rebuild()
        if not self._refreshed_on_show:
            self._refreshed_on_show = True
            self.refresh()

    # -- device pixel ratio -------------------------------------------------

    def _current_dpr(self) -> float:
        """The ratio the diagram should be rendered for right now.

        One seam, read in one place (`_rebuild`) and threaded down from there —
        so the pad and the icon it holds are never sized for two ratios.
        """
        return self.devicePixelRatioF() or 1.0

    def _watch_device_pixel_ratio(self) -> None:
        """Listen for the top-level window's ratio changing under us.

        The pixmaps are *rendered* at one ratio, so a move to a differently
        scaled screen cannot be absorbed by the layout — pad and icon would have
        been sized for two different ratios, and the vector art would be shown at
        the wrong resolution. Re-rendering is the only correct response, and it is
        cheap (this diagram is five icons and three connectors).
        """
        handle = self.window().windowHandle()
        if handle is None or handle is self._dpr_window:
            return
        self._dpr_window = handle
        for name in ("devicePixelRatioChanged", "screenChanged"):
            signal = getattr(handle, name, None)
            if signal is not None:
                signal.connect(self._on_device_pixel_ratio_changed)

    def _on_device_pixel_ratio_changed(self, *_args) -> None:
        """Re-render at the new ratio — but only when it really changed, so a
        plain screen move (same scaling) costs nothing."""
        if self._diagram is not None and self._rendered_dpr != self._current_dpr():
            self._rebuild()

    # -- rendering ----------------------------------------------------------

    def _clear_diagram(self) -> None:
        self.node_widgets.clear()
        while self._diagram_layout.count():
            item = self._diagram_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _rebuild(self) -> None:
        """Lay the whole diagram out from scratch for the current diagram."""
        self._clear_diagram()
        self._update_summary()
        diagram = self._diagram
        if diagram is None:
            self._diagram_layout.addStretch(1)
            placeholder = QLabel("No project status has been probed yet.")
            placeholder.setWordWrap(True)
            self._diagram_layout.addWidget(placeholder, 0, Qt.AlignmentFlag.AlignCenter)
            self._diagram_layout.addStretch(1)
            return

        dpr = self._current_dpr()
        self._rendered_dpr = dpr
        node_pixmaps = {
            node.family: _scaled_pixmap(node.asset, dpr) for node in diagram.nodes
        }
        connector_pixmaps = {
            connector.kind: _scaled_pixmap(connector.asset, dpr)
            for connector in diagram.connectors
        }

        chain = [node for node in diagram.nodes if node.family not in _BRANCH_FAMILIES]
        branches = [node for node in diagram.nodes if node.family in _BRANCH_FAMILIES]

        chain_box_h = max(
            [_logical_size(node_pixmaps[node.family]).height() for node in chain] or [1]
        )
        branch_box_h = max(
            [_logical_size(node_pixmaps[node.family]).height() for node in branches]
            or [1]
        )
        chain_centre = NODE_TOP_PAD + chain_box_h / 2
        branch_height = (
            NODE_TOP_PAD + branch_box_h + NODE_GAP + CAPTION_HEIGHT + NODE_BOTTOM_PAD
        )

        split = next(
            (c for c in diagram.connectors if c.kind is ConnectorKind.SANDBOX_DB), None
        )
        split_pixmap = connector_pixmaps.get(ConnectorKind.SANDBOX_DB, QPixmap())
        split_h = _logical_size(split_pixmap).height()

        if branches:
            # Space the two branch nodes so the splitting connector spans exactly
            # from the upper node's icon centre to the lower node's, then centre
            # the chain on the midpoint between them.
            branch_gap = max(MIN_BRANCH_GAP, round(split_h - branch_height))
            upper_centre = NODE_TOP_PAD + branch_box_h / 2
            lower_centre = branch_height + branch_gap + upper_centre
            branch_mid = (upper_centre + lower_centre) / 2
        else:
            branch_gap = MIN_BRANCH_GAP
            branch_mid = chain_centre

        chain_top = max(0.0, branch_mid - chain_centre)
        branch_top = max(0.0, chain_centre - branch_mid)
        centre_line = chain_top + chain_centre

        self._diagram_layout.addStretch(1)
        for node in chain:
            widget = self._make_node(node, node_pixmaps[node.family], chain_box_h, dpr)
            self._diagram_layout.addWidget(
                self._offset(widget, chain_top), 0, Qt.AlignmentFlag.AlignTop
            )
            kind = _CHAIN_CONNECTOR_AFTER.get(node.family)
            pixmap = connector_pixmaps.get(kind) if kind is not None else None
            if pixmap is not None and not pixmap.isNull():
                self._diagram_layout.addWidget(
                    self._offset(
                        self._make_connector(pixmap),
                        centre_line - _logical_size(pixmap).height() / 2,
                    ),
                    0,
                    Qt.AlignmentFlag.AlignTop,
                )

        if branches:
            if split is not None and not split_pixmap.isNull():
                self._diagram_layout.addWidget(
                    self._offset(
                        self._make_connector(split_pixmap),
                        branch_top + branch_mid - split_h / 2,
                    ),
                    0,
                    Qt.AlignmentFlag.AlignTop,
                )
            column = QWidget()
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(0, 0, 0, 0)
            column_layout.setSpacing(branch_gap)
            for node in branches:
                column_layout.addWidget(
                    self._make_node(
                        node, node_pixmaps[node.family], branch_box_h, dpr
                    )
                )
            column_layout.addStretch(1)
            self._diagram_layout.addWidget(
                self._offset(column, branch_top), 0, Qt.AlignmentFlag.AlignTop
            )
        self._diagram_layout.addStretch(1)

    def _offset(self, widget: QWidget, top: float) -> QWidget:
        """Wrap `widget` in a container that pushes it `top` logical pixels down —
        how the chain, the branch column and the splitting connector are all
        aligned to one computed centre line."""
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addSpacing(max(0, round(top)))
        layout.addWidget(widget)
        layout.addStretch(1)
        return holder

    def _make_node(
        self, node: StatusNode, pixmap: QPixmap, box_h: int, dpr: float
    ) -> _DiagramNode:
        """One node widget. `dpr` is the ratio the whole diagram was rendered at —
        threaded in from `_rebuild` rather than re-read off `pixmap`, so the pad
        and the icon can never be sized for two different ratios."""
        widget = _DiagramNode(
            node.family, _NODE_TITLES[node.family], self._state_caption(node)
        )
        # The label gets the box the pad was *actually* built at: if the art
        # exceeded the row's shared height, `_boxed_pixmap` grew the pad instead
        # of cropping, and a smaller fixed size here would crop it right back.
        box = _padded_box(pixmap, QSize(NODE_WIDTH - 8, box_h))
        widget.set_pixmap(_boxed_pixmap(pixmap, box, dpr), box)
        widget.clicked.connect(lambda family=node.family: self._on_node_clicked(family))
        self.node_widgets[node.family] = widget
        return widget

    def _make_connector(self, pixmap: QPixmap) -> QLabel:
        """A connector's label. Sized to at least the pixmap's logical extent —
        `_logical_size` rounds *up* for exactly this reason: some connector art is
        only a few pixels tall, so a size pinned a hair short of it would crop the
        whole line rather than an edge."""
        label = QLabel()
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFixedSize(_logical_size(pixmap))
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        return label

    def _state_caption(self, node: StatusNode) -> str:
        text = _STATE_CAPTIONS.get(node.state, node.state)
        if (
            node.family is NodeFamily.SANDBOX
            and self._diagram is not None
            and self._diagram.sandbox_degradation is SandboxDegradation.TOOLS_MISSING
        ):
            # Same green icon as a healthy sandbox (§18.8) — the caption is the
            # first place the difference is allowed to show.
            return "Connected — tools missing"
        return text

    def _update_summary(self) -> None:
        diagram = self._diagram
        if diagram is None:
            self.summary_label.setText("Not probed yet.")
            return
        app = diagram.node(NodeFamily.APP)
        parts = [_STATE_CAPTIONS.get(app.state, app.state)] if app is not None else []
        if not diagram.sandbox_present:
            parts.append("no sandbox configured")
        elif diagram.sandbox_degradation is SandboxDegradation.TOOLS_MISSING:
            tools = ", ".join(diagram.missing_tools) or "external tools"
            parts.append(f"sandbox reachable, missing {tools}")
        elif diagram.degraded_reason:
            parts.append(diagram.degraded_reason)
        self.summary_label.setText(" — ".join(parts))

    # -- click-through ------------------------------------------------------

    def _on_node_clicked(self, family: NodeFamily) -> None:
        self.node_activated.emit(family.value)
        builders = {
            NodeFamily.QUALITY: self._quality_window,
            NodeFamily.APP: self._app_window,
            NodeFamily.SANDBOX: self._sandbox_window,
            NodeFamily.SANDBOX1: self._sandbox1_window,
            NodeFamily.SANDBOX2: self._sandbox2_window,
        }
        builder = builders.get(family)
        if builder is None:
            return
        window = builder()
        self.open_windows.append(window)
        window.show()

    def _new_window(self, family: NodeFamily, title: str) -> NodeWindow:
        return NodeWindow(self, family, title)

    def _node_state(self, family: NodeFamily) -> str:
        node = self._diagram.node(family) if self._diagram is not None else None
        return node.state if node is not None else ""

    def _state_line(self, family: NodeFamily) -> str:
        state = self._node_state(family)
        return f"Status: {_STATE_CAPTIONS.get(state, state or 'unknown')}"

    def _quality_window(self) -> NodeWindow:
        """One-step action window: connection info plus a reconnect action."""
        window = self._new_window(NodeFamily.QUALITY, "Quality database")
        window.add_line(self._state_line(NodeFamily.QUALITY))
        window.add_line(self._quality_summary or "No connection details available.")
        if self._on_reconnect_quality is not None:
            window.add_action("Reconnect", self._wrap_action(self._on_reconnect_quality))
        return window

    def _app_window(self) -> NodeWindow:
        """One-step window, deliberately minimal.

        TODO(§29): the App node's action-window contents are **not specified by
        the owner** and §18.8 explicitly forbids inventing them. This states the
        tier plainly and offers no action; flesh it out only once the owner's
        pass lands.
        """
        window = self._new_window(NodeFamily.APP, "Project")
        state = self._node_state(NodeFamily.APP)
        window.add_line(_APP_TIER_LINES.get(state, self._state_line(NodeFamily.APP)))
        window.add_line(
            "This window will grow project-tier actions once their contents are "
            "specified."
        )
        return window

    def _sandbox_window(self) -> NodeWindow:
        """One-step status/help window; names the missing tools when that is the
        condition, and offers the injected help affordance."""
        window = self._new_window(NodeFamily.SANDBOX, "Sandbox")
        window.add_line(self._state_line(NodeFamily.SANDBOX))
        window.add_line(self._sandbox_summary or "No connection details available.")
        diagram = self._diagram
        if diagram is not None and diagram.sandbox_degradation is (
            SandboxDegradation.TOOLS_MISSING
        ):
            tools = ", ".join(diagram.missing_tools) or "required command-line tools"
            noun = "tool is" if len(diagram.missing_tools) == 1 else "tools are"
            window.add_line(
                f"The sandbox database is reachable, but the following {noun} not on "
                f"PATH: {tools}. Data cloning needs them; schema-only work is "
                f"unaffected."
            )
            if self._on_show_help is not None:
                window.add_help("Open help", self._wrap_action(self._on_show_help))
        elif diagram is not None and diagram.degraded_reason:
            window.add_line(diagram.degraded_reason)
        return window

    #: Sandbox1's detail sentence, one per verified state (BUG-035). Keyed by
    #: state stem so it cannot drift from `_STATE_CAPTIONS`. The `unknown` and
    #: `not_provisioned` lines say what was (not) established — they never
    #: describe a schema the panel has not been told exists.
    _SANDBOX1_LINES = {
        "sandbox1_unknown": (
            "The sandbox database could not be inspected, so what it holds is "
            "unknown — this is not a report that it is empty. Re-check once the "
            "sandbox is reachable."
        ),
        "sandbox1_not_provisioned": (
            "The sandbox database is reachable but nothing has been provisioned "
            "into it yet — no tables, views or routines of your own were found."
        ),
        "sandbox1_empty": (
            "The sandbox holds the schema only — no data was found in it."
        ),
        "sandbox1_filled": "The sandbox holds a copy of the quality database's data.",
    }

    def _sandbox1_window(self) -> NodeWindow:
        """Two-step status + embedded clone action (never a one-click trigger)."""
        window = self._new_window(NodeFamily.SANDBOX1, "Sandbox data")
        state = self._node_state(NodeFamily.SANDBOX1)
        window.add_line(self._state_line(NodeFamily.SANDBOX1))
        window.add_line(
            self._SANDBOX1_LINES.get(
                state, "The sandbox's contents have not been established."
            )
        )
        if self._on_run_data_clone is not None:
            window.add_action(
                "Redo data clone" if state == "sandbox1_filled" else "Run data clone now",
                self._wrap_action(self._on_run_data_clone),
            )
        return window

    def _sandbox2_window(self) -> NodeWindow:
        """Two-step status + install action — offered only when not installed.

        §18.8: once the extension is installed nothing meaningful is left to do
        (re-running ``CREATE EXTENSION IF NOT EXISTS`` is a no-op), so the
        installed state's window is purely informational.
        """
        window = self._new_window(NodeFamily.SANDBOX2, "plpgsql_check")
        installed = self._node_state(NodeFamily.SANDBOX2) == (
            "sandbox2_plpgsql_check_installed"
        )
        window.add_line(self._state_line(NodeFamily.SANDBOX2))
        if installed:
            window.add_line(
                "The plpgsql_check extension is installed in the sandbox database; "
                "routine audits can run there."
            )
            return window
        window.add_line(
            "The plpgsql_check extension is not installed in the sandbox database, "
            "so routine audits cannot run there yet."
        )
        if self._on_install_plpgsql_check is not None:
            window.add_action(
                "Install the plpgsql_check extension",
                self._wrap_action(self._on_install_plpgsql_check),
            )
        return window

    def _wrap_action(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Run an injected action, then close its window and re-probe — the
        diagram must not keep claiming the pre-action state."""

        def run() -> None:
            callback()
            window = self.last_window
            if window is not None:
                window.close()
            self.refresh()

        return run
