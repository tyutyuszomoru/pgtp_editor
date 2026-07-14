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

# Tags whose captions form the structural breadcrumb context (spec §2.1).
_BREADCRUMB_ANCESTOR_TAGS: frozenset[str] = frozenset(
    {"Page", "Detail", "OnTheFlyInsertPage"}
)


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
    breadcrumb:   structural path from Page/Detail/OnTheFlyInsertPage ancestors
                  (outermost first) plus the element's own label, joined with
                  " → ". Display-only. Defaults to "" so bare constructions
                  (tests, callers pre-Phase-2) still work.
    """

    line: int
    element_tag: str
    anchor: str
    attribute: str
    value: str
    breadcrumb: str = ""


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
        breadcrumb = _build_breadcrumb(element)
        for attribute in CAPTION_ATTRIBUTES:
            if attribute in element.attrib:
                entries.append(
                    CaptionEntry(
                        line=line,
                        element_tag=element.tag,
                        anchor=anchor,
                        attribute=attribute,
                        value=element.attrib[attribute],
                        breadcrumb=breadcrumb,
                    )
                )
    return entries


def _build_breadcrumb(element) -> str:
    """Structural path: each Page/Detail/OnTheFlyInsertPage ancestor's label
    (outermost first), then the element's own label. Joined with ' → '.

    A .pgtp Detail is ``<Detail caption="X"><Page ...>`` where the inner
    ``<Page>`` repeats the level, which would show each Detail twice
    (issue #3). To collapse a Detail and its immediate inner ``<Page>`` into
    ONE level, we SKIP any ``<Page>``/``<OnTheFlyInsertPage>`` ancestor whose
    parent is a ``<Detail>`` — the Detail already represents that level. Top-
    level Pages and each Detail are kept."""
    ancestor_labels: list[str] = []
    for ancestor in element.iterancestors():
        if not (isinstance(ancestor.tag, str) and ancestor.tag in _BREADCRUMB_ANCESTOR_TAGS):
            continue
        if ancestor.tag in ("Page", "OnTheFlyInsertPage"):
            parent = ancestor.getparent()
            if parent is not None and parent.tag == "Detail":
                continue  # the wrapping Detail already represents this level
        ancestor_labels.append(_ancestor_label(ancestor))
    ancestor_labels.reverse()  # iterancestors() is innermost-first
    ancestor_labels.append(_own_label(element))
    return " → ".join(ancestor_labels)


def _ancestor_label(ancestor) -> str:
    """A breadcrumb ancestor's label: caption, else fileName, else tableName,
    else its tag.

    For a Detail we prefer the Detail's OWN caption; if it has none we fall back
    to its immediate inner ``<Page>``'s caption/fileName/tableName (so a
    caption-less Detail still shows a meaningful label — issue #3) before
    resorting to the Detail's own fileName/tableName or tag."""
    caption = ancestor.attrib.get("caption")
    if caption:
        return caption
    if ancestor.tag == "Detail":
        inner_page = ancestor.find("Page")
        if inner_page is not None:
            for attribute in ("caption", "fileName", "tableName"):
                value = inner_page.attrib.get(attribute)
                if value:
                    return value
    for attribute in ("fileName", "tableName"):
        value = ancestor.attrib.get(attribute)
        if value:
            return value
    return ancestor.tag


def _own_label(element) -> str:
    """The element's own breadcrumb label: fieldName for a ColumnPresentation,
    else its caption, else its tag."""
    if element.tag == "ColumnPresentation":
        field_name = element.attrib.get("fieldName")
        if field_name:
            return field_name
    caption = element.attrib.get("caption")
    if caption:
        return caption
    return element.tag


def _resolve_anchor(element) -> str:
    for anchor_attribute in _ANCHOR_ATTRIBUTES:
        value = element.attrib.get(anchor_attribute)
        if value:
            return value
    return element.tag


# ---------------------------------------------------------------------------
# Find / Filter / Replace core (Phase 4). Qt-free and fully unit-tested.
#
# Three search modes, shared by the grid filter and the Replace-All transform:
#   - "normal":   plain substring; find matched literally, replace-all.
#   - "extended": C-style escapes (\n \t \r \0 \xNN and \\) are decoded in BOTH
#                 find and replacement, then treated as a plain substring.
#   - "regular":  Python regex; capture-group refs (\1, \g<name>) honored in the
#                 replacement. Invalid patterns raise ValueError.
# ---------------------------------------------------------------------------

SEARCH_MODES: tuple[str, ...] = ("normal", "extended", "regular")

_EXTENDED_ESCAPE = re.compile(r"\\(x[0-9A-Fa-f]{2}|[nrt0\\])")


def _decode_extended(text: str) -> str:
    """Decode the Extended-mode escape sequences \\n \\t \\r \\0 \\xNN \\\\ in
    `text`, leaving any other backslash sequence untouched (verbatim)."""

    def replace(match: re.Match) -> str:
        token = match.group(1)
        if token == "n":
            return "\n"
        if token == "t":
            return "\t"
        if token == "r":
            return "\r"
        if token == "0":
            return "\0"
        if token == "\\":
            return "\\"
        # token is xNN
        return chr(int(token[1:], 16))

    return _EXTENDED_ESCAPE.sub(replace, text)


def matches(value: str, find: str, mode: str, case_sensitive: bool) -> bool:
    """True iff `find` matches somewhere in `value` under `mode`/`case_sensitive`.

    An empty `find` matches everything (used as a cleared filter). Invalid regex
    in `"regular"` mode raises ValueError with a clear message."""
    if mode not in SEARCH_MODES:
        raise ValueError(f"Unknown search mode: {mode!r}")
    if find == "":
        return True
    if mode == "regular":
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(find, flags)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc
        return pattern.search(value) is not None
    needle = _decode_extended(find) if mode == "extended" else find
    if case_sensitive:
        return needle in value
    return needle.lower() in value.lower()


def apply_find_replace(
    value: str,
    find: str,
    replacement: str,
    mode: str,
    case_sensitive: bool,
) -> str | None:
    """Return `value` with every occurrence of `find` replaced by `replacement`
    under `mode`, or None if `find` does not match `value` (so callers can skip
    unchanged rows).

    - "normal":   plain substring replace-all.
    - "extended": decode escapes in find AND replacement, then plain replace-all.
    - "regular":  regex sub with capture-group refs (\\1, \\g<name>) in the
                  replacement; honors case_sensitive. Invalid regex -> ValueError.
    """
    if mode not in SEARCH_MODES:
        raise ValueError(f"Unknown search mode: {mode!r}")
    if find == "":
        return None  # an empty pattern never "matches" for replacement purposes

    if mode == "regular":
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(find, flags)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc
        if pattern.search(value) is None:
            return None
        try:
            return pattern.sub(replacement, value)
        except re.error as exc:
            raise ValueError(f"Invalid replacement: {exc}") from exc

    needle = find
    repl = replacement
    if mode == "extended":
        needle = _decode_extended(find)
        repl = _decode_extended(replacement)

    if case_sensitive:
        if needle not in value:
            return None
        return value.replace(needle, repl)

    # Case-insensitive plain replace-all: find all match spans on a lowercased
    # copy, then splice the original around them so the untouched parts keep
    # their original casing.
    lowered_value = value.lower()
    lowered_needle = needle.lower()
    start = lowered_value.find(lowered_needle)
    if start == -1:
        return None
    result: list[str] = []
    cursor = 0
    step = len(lowered_needle)
    while start != -1:
        result.append(value[cursor:start])
        result.append(repl)
        cursor = start + step
        start = lowered_value.find(lowered_needle, cursor)
    result.append(value[cursor:])
    return "".join(result)


# ---------------------------------------------------------------------------
# Bulk transform core (Phase 5). Qt-free and fully unit-tested.
#
# `transform_caption(text, kind)` returns a transformed copy of `text` for one
# of the supported `kind`s. Used by the panel's Transform ▸ submenu to rewrite
# the selection's New Value in one click.
# ---------------------------------------------------------------------------

TRANSFORM_KINDS: tuple[str, ...] = (
    "title",
    "upper",
    "lower",
    "sentence",
    "trim",
    "humanize",
)


def transform_caption(text: str, kind: str) -> str:
    """Return `text` transformed under `kind`.

    - "title":    Title Case (``wbs id`` -> ``Wbs Id``).
    - "upper":    UPPERCASE.
    - "lower":    lowercase.
    - "sentence": Sentence case (first char upper, the rest lower).
    - "trim":     strip leading/trailing whitespace (ends only).
    - "humanize": humanize a field-name-like string: split on ``_``, drop a
                  trailing token equal to ``id`` (case-insensitive), Title Case
                  the remaining words, join with spaces
                  (``physical_location_id`` -> ``Physical Location``,
                  ``wbs_id`` -> ``Wbs``, ``criticality_lvl`` ->
                  ``Criticality Lvl``). Deterministic (no dictionary
                  word-splitting): a single run-together token like
                  ``physicallocation`` stays one word (``Physicallocation``).
                  Empty result if the only token was ``id``.
    """
    if kind not in TRANSFORM_KINDS:
        raise ValueError(f"Unknown transform kind: {kind!r}")
    if kind == "title":
        return text.title()
    if kind == "upper":
        return text.upper()
    if kind == "lower":
        return text.lower()
    if kind == "sentence":
        stripped = text.lower()
        return stripped[:1].upper() + stripped[1:]
    if kind == "trim":
        return text.strip()
    # humanize
    tokens = text.split("_")
    if len(tokens) > 1 and tokens[-1].lower() == "id":
        tokens = tokens[:-1]
    return " ".join(token.title() for token in tokens)


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
