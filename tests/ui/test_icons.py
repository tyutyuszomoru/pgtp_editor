"""Breeze toolbar icon loading + recoloring (icons.py).

The critical risk is QtSvg not resolving Breeze's ``fill:currentColor`` /
``.ColorScheme-Text { color:#232629 }`` mechanism, so these tests prove that
recoloring substitutes a literal fill AND that the rendered pixmap actually
takes the requested color.
"""
from importlib.resources import files

import pytest
from PySide6.QtGui import QColor, QIcon

from pgtp_editor.ui import icons
from pgtp_editor.ui.toolbar_registry import DEFAULT_TOOLBAR_IDS


ALL_IDS = DEFAULT_TOOLBAR_IDS


def _breeze_dir():
    return files("pgtp_editor") / "resources" / "icons" / "breeze"


def test_action_icon_files_covers_every_toolbar_id():
    for command_id in ALL_IDS:
        assert command_id in icons.ACTION_ICON_FILES
        assert icons.ACTION_ICON_FILES[command_id].endswith(".svg")


def test_all_vendored_svgs_and_license_present():
    breeze = _breeze_dir()
    for filename in icons.ACTION_ICON_FILES.values():
        assert (breeze / filename).is_file(), filename
    assert (breeze / "LICENSE-LGPL-3.0.txt").is_file()


def test_load_svg_text_reads_vendored_svg():
    text = icons.load_svg_text("open")
    assert "<svg" in text
    assert "currentColor" in text  # unmodified upstream still has the mechanism


def test_load_svg_text_unknown_id_raises_keyerror():
    with pytest.raises(KeyError):
        icons.load_svg_text("nope")


def test_recolor_svg_substitutes_both_mechanisms():
    original = icons.load_svg_text("open")
    recolored = icons.recolor_svg(original, "#ff0000")
    assert "currentColor" not in recolored
    assert "#232629" not in recolored.lower()
    assert "#ff0000" in recolored.lower()


def test_recolor_svg_handles_uppercase_hex_in_style():
    svg = (
        '<svg><style>.ColorScheme-Text { color:#232629; }</style>'
        '<path style="fill:currentColor"/></svg>'
    )
    recolored = icons.recolor_svg(svg, "#00ff00")
    assert "currentColor" not in recolored
    assert "232629" not in recolored
    assert recolored.lower().count("#00ff00") >= 2


def test_themed_icon_returns_non_null_icon(qapp):
    icon = icons.themed_icon("open", QColor("#ff0000"))
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def _render_image(command_id, color):
    icon = icons.themed_icon(command_id, QColor(color))
    pixmap = icon.pixmap(22, 22)
    assert not pixmap.isNull()
    return pixmap.toImage()


def _has_opaque_pixels(image):
    return any(
        QColor(image.pixelColor(x, y)).alpha() > 0
        for x in range(image.width())
        for y in range(image.height())
    )


def _colored_pixels(image, want, tol=60):
    """Count pixels close to `want` (a QColor) among opaque pixels."""
    n = 0
    for x in range(image.width()):
        for y in range(image.height()):
            px = QColor(image.pixelColor(x, y))
            if px.alpha() == 0:
                continue
            if (
                abs(px.red() - want.red()) <= tol
                and abs(px.green() - want.green()) <= tol
                and abs(px.blue() - want.blue()) <= tol
            ):
                n += 1
    return n


@pytest.mark.parametrize("command_id", ["open", "save"])
def test_themed_icon_renders_requested_color(qapp, command_id):
    """QtSvg recoloring genuinely works: red request -> red pixels, blue
    request -> blue pixels, on the SAME icon id (so the color is not baked in)."""
    red_image = _render_image(command_id, "#ff0000")
    assert _has_opaque_pixels(red_image)
    assert _colored_pixels(red_image, QColor("#ff0000")) > 0

    blue_image = _render_image(command_id, "#0000ff")
    assert _has_opaque_pixels(blue_image)
    assert _colored_pixels(blue_image, QColor("#0000ff")) > 0

    # Prove the recolor actually took effect: the red render has essentially no
    # blue pixels, and vice-versa.
    assert _colored_pixels(red_image, QColor("#0000ff")) == 0
    assert _colored_pixels(blue_image, QColor("#ff0000")) == 0


def test_themed_icon_accepts_hex_string(qapp):
    icon = icons.themed_icon("open", "#123456")
    assert not icon.isNull()
