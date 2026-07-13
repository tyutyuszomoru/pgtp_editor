# pgtp_editor/ui/caption_scan.py
"""Pure, Qt-free scan/apply core for Caption Management.

`scan_captions(text)` parses the frozen Raw XML text with lxml and emits one
CaptionEntry per caption-like attribute (in the fixed CAPTION_ATTRIBUTES
order) on every element that carries one. `apply_caption_edits(text, edits)`
writes edited values back onto their exact source lines, byte-for-byte
preserving every unedited line. Both functions are Qt-free and fully
unit-tested; the riskiest correctness (attribute-boundary-safe replacement,
XML attribute escaping) lives here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

# The caption-like attributes collected by the scan, in the fixed emission
# order (spec §3). A line carrying several of these yields one row per
# attribute in this order.
CAPTION_ATTRIBUTES: tuple[str, ...] = (
    "caption",
    "shortCaption",
    "headerHint",
    "insertFormCaption",
    "groupName",
)

# Anchor resolution: prefer fieldName (columns), then fileName (pages), then
# tableName (details), else the element tag. Used for the Anchor column and
# inconsistency highlighting only -- never for write-back.
_ANCHOR_ATTRIBUTES: tuple[str, ...] = ("fieldName", "fileName", "tableName")


@dataclass(frozen=True)
class CaptionEntry:
    """One caption-like attribute found on one element.

    line:         1-based source line of the element's opening tag
                  (lxml `sourceline`). All attributes of a .pgtp element
                  share this single line (opening tags are single-line).
    element_tag:  the element's tag, e.g. "Page", "ColumnPresentation".
    anchor:       human-readable context/coherence key (fieldName, else
                  fileName, else tableName, else the tag). Display + grouping
                  only; not used for write-back.
    attribute:    one of CAPTION_ATTRIBUTES.
    value:        the decoded (unescaped) current value, as lxml returns it.
    """

    line: int
    element_tag: str
    anchor: str
    attribute: str
    value: str


def scan_captions(text: str) -> list[CaptionEntry]:
    """Return every caption-like attribute in `text`, in document order then
    CAPTION_ATTRIBUTES order. Returns [] if `text` is not well-formed XML
    (caption mode is only entered on a parsed project; this is defensive)."""
    try:
        root = etree.fromstring(text.encode("utf-8"))
    except etree.XMLSyntaxError:
        return []

    entries: list[CaptionEntry] = []
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue  # skip comments / processing instructions
        line = element.sourceline
        if line is None:
            continue  # defensive; not expected for parsed elements
        anchor = _resolve_anchor(element)
        for attribute in CAPTION_ATTRIBUTES:
            if attribute in element.attrib:
                entries.append(
                    CaptionEntry(
                        line=line,
                        element_tag=element.tag,
                        anchor=anchor,
                        attribute=attribute,
                        value=element.attrib[attribute],
                    )
                )
    return entries


def _resolve_anchor(element) -> str:
    for anchor_attribute in _ANCHOR_ATTRIBUTES:
        value = element.attrib.get(anchor_attribute)
        if value:
            return value
    return element.tag
