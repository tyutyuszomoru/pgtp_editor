"""Pins down the empirically-measured round-trip fidelity result from
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md
§4: with `etree.tostring(tree, xml_declaration=False, encoding="UTF-8",
pretty_print=False)`, both real sample files round-trip byte-for-byte
except that `&quot;` entities inside element TEXT content (never inside
attribute values) are normalized to a literal `"` by libxml2's serializer.

This test exists so a future lxml upgrade or an accidental change to the
adopted tostring() settings can't silently regress round-trip fidelity
without a test failing.

DEVIATION FROM THE SPEC'S DOCUMENTED RESIDUAL, FOUND WHILE WRITING THIS
TEST: a strict byte-for-byte comparison (as opposed to the spec's own
byte-length-delta-based measurement in §4.3) turned up two additional,
narrow, well-understood residuals beyond the documented `&quot;`-in-text
normalization, in both cases due to standard XML 1.0 parsing rules that
`etree.parse` applies (i.e. these are input-side normalizations baked into
the parsed tree itself, not `tostring()`/serializer artifacts):

1. **Trailing newline after the root element is dropped, in both sample
   files.** Both files end with `</Project>\n` on disk, but
   `tree.getroot()` has `.tail is None` for the root element after
   `etree.parse` -- `ElementTree`-level `tostring()` never emits a root
   element's tail, so the single trailing `\n` after the document element
   is always lost. This is a fixed, 1-byte-per-file residual, harmless for
   this format (no meaningful content lives after the closing root tag).

2. **A literal `\r\n` embedded inside one attribute value in
   `Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp` is normalized to a single
   space.** This is XML 1.0 *mandatory* attribute-value normalization
   (spec section 3.3.3): every literal whitespace character (tab, CR, LF)
   inside a double-quoted attribute value is replaced by a single space
   during parsing. Found in exactly one place in one sample file: a
   `ColumnPresentation/@editorHint` value containing an embedded
   multi-line tooltip string with literal `\r\n` line breaks:
   `"Move the scheduled date by this interval usage: \r\n&quot;- 5
   days&quot; \r\n..."`. This directly contradicts the spec's §4.3 claim
   that the `&quot;`-unescaping residual "never" occurs inside attribute
   values -- that claim is true only for the `&quot;`-unescaping
   phenomenon specifically; it does not mean attribute values are
   otherwise untouched by parsing. This normalization is also
   XML-spec-mandated (not a `libxml2` quirk) and is cosmetically inert for
   this format (the semantic value of the tooltip string is unchanged by
   collapsing an embedded line break to a space).

Both are added to this test's normalization helper below, narrowly scoped
(exact string replacements, not general whitespace collapsing) so this
test still fails loudly if any *other*, unaccounted-for difference appears
in a future lxml version or sample file.
"""
import re
from pathlib import Path

import pytest
from lxml import etree

from pgtp_editor.diff.differ import diff_project
from pgtp_editor.model.parser import load_project

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"

SAMPLE_FILES = [
    SAMPLE_DIR / "dev_Ferrara.pgtp",
    SAMPLE_DIR / "Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp",
]

TOSTRING_KWARGS = dict(xml_declaration=False, encoding="UTF-8", pretty_print=False)


def _require_sample(path):
    if not path.exists():
        pytest.skip(f"sample file not present: {path}")


def _unescape_quot_in_text_content_only(xml_bytes: bytes) -> bytes:
    """Mirror the exact normalization used to characterize the residual
    difference in spec §4.3: replace `&quot;` with a literal `"` only when
    it occurs in element text (i.e. NOT inside a double-quoted attribute
    value). A `&quot;` is "in an attribute value" if it appears between an
    opening `="` and the next unescaped `"` within the same start-tag; this
    regex instead takes the simpler, equivalent-for-this-format approach of
    only touching `&quot;` occurrences that are NOT immediately preceded by
    `="` or immediately followed by `"` closing an attribute -- in practice,
    for this test, we replicate the exact known-good rule from the spec by
    unescaping every `&quot;` that lies OUTSIDE any `<...>` tag span, since
    tag spans are exactly where attribute values live.
    """
    result = bytearray()
    i = 0
    depth_inside_tag = False
    while i < len(xml_bytes):
        ch = xml_bytes[i:i + 1]
        if ch == b"<":
            depth_inside_tag = True
            result += ch
            i += 1
        elif ch == b">":
            depth_inside_tag = False
            result += ch
            i += 1
        elif xml_bytes[i:i + 6] == b"&quot;" and not depth_inside_tag:
            result += b'"'
            i += 6
        else:
            result += ch
            i += 1
    return bytes(result)


# The one known CRLF-embedded-in-an-attribute-value occurrence (see the
# module docstring's item 2). XML 1.0 attribute-value normalization
# collapses each literal CR/LF in this value to a single space during
# parsing; this mirrors that collapse in the "expected" (normalized
# original) bytes so the test can still assert byte-for-byte equality
# beyond this one known, XML-spec-mandated residual.
_CRLF_ATTRIBUTE_REPLACEMENTS = [
    (b"usage: \r\n", b"usage:  "),
    (b"days&quot; \r\n", b"days&quot;  "),
    (b"week&quot;\r\n", b"week&quot; "),
    (b"weeks&quot;\r\n", b"weeks&quot; "),
]


def _normalize_known_residuals(xml_bytes: bytes) -> bytes:
    normalized = _unescape_quot_in_text_content_only(xml_bytes)
    for old, new in _CRLF_ATTRIBUTE_REPLACEMENTS:
        normalized = normalized.replace(old, new)
    # Trailing newline after the root element's closing tag is never
    # emitted by ElementTree-level tostring() (see module docstring item 1).
    if normalized.endswith(b"\n"):
        normalized = normalized[:-1]
    return normalized


@pytest.mark.parametrize("sample_path", SAMPLE_FILES)
def test_reserialize_matches_original_after_normalizing_known_residual(sample_path):
    _require_sample(sample_path)
    original_bytes = sample_path.read_bytes()

    tree = etree.parse(str(sample_path))
    reserialized = etree.tostring(tree, **TOSTRING_KWARGS)

    normalized_original = _normalize_known_residuals(original_bytes)
    assert reserialized == normalized_original


@pytest.mark.parametrize("sample_path", SAMPLE_FILES)
def test_no_xml_declaration_is_emitted(sample_path):
    _require_sample(sample_path)
    tree = etree.parse(str(sample_path))
    reserialized = etree.tostring(tree, **TOSTRING_KWARGS)
    assert not reserialized.startswith(b"<?xml")


@pytest.mark.parametrize("sample_path", SAMPLE_FILES)
def test_zero_difference_no_op_merge_end_to_end(sample_path):
    """A true end-to-end 'no-op merge changes nothing meaningful' test:
    load, reserialize via load_project's own tree (not a bespoke tostring
    call), write to a temp path, reload, and diff against the original --
    expecting an empty difference list. Layers on top of the differ
    engine's own 'diff a file against itself' test."""
    _require_sample(sample_path)
    project = load_project(sample_path)

    reserialized = etree.tostring(project.tree, **TOSTRING_KWARGS)

    reloaded_from_original = load_project(sample_path)
    import tempfile
    import os

    fd, tmp_name = tempfile.mkstemp(suffix=".pgtp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(reserialized)
        reloaded_from_reserialized = load_project(tmp_name)
    finally:
        os.remove(tmp_name)

    differences = diff_project(reloaded_from_original, reloaded_from_reserialized)
    assert differences == []
