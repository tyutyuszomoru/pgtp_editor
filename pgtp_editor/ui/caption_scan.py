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


def apply_caption_edits(text: str, edits) -> str:
    """Return `text` with each edit's new value written onto its source line.

    `edits` is an iterable of `(entry, new_value)` pairs for CHANGED rows
    only (each `entry` carries the 1-based `line` and the `attribute` name).
    Each edit replaces `attribute="..."` on `text.splitlines(keepends=True)
    [line-1]` with `attribute="<escaped_new_value>"`:

    - The match is anchored with a negative lookbehind on word chars/hyphen so
      the attribute name cannot match the tail of a longer name (critical:
      `caption` must NOT match inside `shortCaption`/`insertFormCaption`).
      count=1 replaces only the first occurrence.
    - The new value is XML-attribute-escaped for a double-quoted attribute
      (& first, then < > "). .pgtp attributes use double quotes.
    - If the pattern does not match on that line (attribute unexpectedly
      absent), the line is left unchanged. Never crashes or corrupts.

    Unedited lines are byte-for-byte unchanged. Relies on the verified .pgtp
    convention that an element's opening tag (all its attributes) is on a
    single line (`sourceline`).
    """
    lines = text.splitlines(keepends=True)
    for entry, new_value in edits:
        index = entry.line - 1
        if not (0 <= index < len(lines)):
            continue  # defensive: line out of range
        lines[index] = _replace_attribute_on_line(lines[index], entry.attribute, new_value)
    return "".join(lines)


def _replace_attribute_on_line(line: str, attribute: str, new_value: str) -> str:
    pattern = re.compile(r'(?<![\w-])' + re.escape(attribute) + r'="[^"]*"')
    replacement = f'{attribute}="{_escape_attribute_value(new_value)}"'
    # re.sub treats backslashes in the replacement specially; pass a function
    # so the (already-escaped) replacement text is inserted verbatim.
    return pattern.sub(lambda _match: replacement, line, count=1)


def _escape_attribute_value(value: str) -> str:
    """Escape `value` for a double-quoted XML attribute. `&` must be escaped
    first so the ampersands introduced by the other replacements are not
    double-escaped."""
    value = value.replace("&", "&amp;")
    value = value.replace("<", "&lt;")
    value = value.replace(">", "&gt;")
    value = value.replace('"', "&quot;")
    return value
