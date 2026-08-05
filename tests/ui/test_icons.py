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
from pgtp_editor.ui.toolbar_registry import LEGACY_COMMANDS


# BUG-027: icons are keyed by the LEGACY command ids (the seven with vendored
# SVGs), not by the menu-path ids the toolbar now stores -- `_set_action_icon`
# maps one to the other via `ICON_ID_BY_COMMAND`.
ALL_IDS = [command_id for command_id, _label in LEGACY_COMMANDS]


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


# -- FQ-004: the enumerable catalog over the widened vendored pack -----------


def test_catalog_matches_the_vendored_svgs_on_disk():
    on_disk = sorted(
        entry.name[: -len(".svg")]
        for entry in _breeze_dir().iterdir()
        if entry.name.endswith(".svg")
    )
    catalog = icons.icon_catalog()
    assert [icon_id for icon_id, _filename, _label in catalog] == on_disk
    # The picker is pointless over a handful of icons -- FQ-004 vendored a
    # curated common-action subset, so guard the floor.
    assert len(catalog) >= 60


def test_catalog_entries_all_resolve_to_a_real_readable_svg():
    breeze = _breeze_dir()
    for icon_id, filename, label in icons.icon_catalog():
        assert filename == f"{icon_id}.svg"
        assert (breeze / filename).is_file(), filename
        assert label and label[0].isupper()
        text = icons.load_svg_text(icon_id)
        assert "<svg" in text
        # Every offered icon must be recolorable by the existing pipeline.
        assert "currentColor" in text or "232629" in text


def test_catalog_is_sorted_and_free_of_duplicates():
    ids = icons.catalog_ids()
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))


def test_catalog_still_contains_the_legacy_seven_unchanged():
    ids = set(icons.catalog_ids())
    for filename in icons.ACTION_ICON_FILES.values():
        assert filename[: -len(".svg")] in ids


def test_human_name_for_reads_like_a_label():
    assert icons.human_name_for("document-save-as") == "Document Save As"
    assert icons.human_name_for("zoom-in") == "Zoom In"


def test_catalog_filename_unknown_id_is_none():
    assert icons.catalog_filename("no-such-icon") is None


def test_search_catalog_filters_by_term_and_is_case_insensitive():
    all_ids = icons.catalog_ids()
    zoom = [entry[0] for entry in icons.search_catalog("ZOOM")]
    assert zoom, "expected the vendored subset to include zoom-* icons"
    assert all("zoom" in icon_id for icon_id in zoom)
    assert len(zoom) < len(all_ids)


def test_search_catalog_requires_every_term():
    both = [entry[0] for entry in icons.search_catalog("document save")]
    assert "document-save-as" in both
    assert "document-open" not in both


def test_search_catalog_empty_query_returns_everything():
    assert icons.search_catalog("") == icons.icon_catalog()
    assert icons.search_catalog("   ") == icons.icon_catalog()


def test_search_catalog_no_match_is_empty():
    assert icons.search_catalog("zzzz-not-an-icon") == []


def test_load_svg_text_accepts_a_catalog_id_as_well_as_a_legacy_id():
    # Legacy id and its catalog id name the same artwork.
    assert icons.load_svg_text("open") == icons.load_svg_text("document-open")


def test_themed_icon_renders_a_newly_vendored_catalog_icon(qapp):
    """A newly vendored icon goes through the SAME pipeline as the legacy
    seven -- non-null, and genuinely tinted to the requested color."""
    icon = icons.themed_icon("document-save-as", QColor("#ff0000"))
    assert isinstance(icon, QIcon)
    assert not icon.isNull()
    image = icon.pixmap(22, 22).toImage()
    assert _has_opaque_pixels(image)
    assert _colored_pixels(image, QColor("#ff0000")) > 0
    assert _colored_pixels(image, QColor("#0000ff")) == 0


def test_every_catalog_icon_renders_non_null(qapp):
    for icon_id in icons.catalog_ids():
        assert not icons.themed_icon(icon_id, QColor("#ff0000")).isNull(), icon_id
