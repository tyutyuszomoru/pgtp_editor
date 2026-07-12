"""Tests for CESU-8 emoji repair (pgtp_editor/model/encoding.py) and its
integration into load_project. Uses a synthetic CESU-8 fixture built in-test
so it does not depend on the gitignored real sample files.
"""
from pgtp_editor.model.encoding import (
    read_pgtp_text,
    repair_cesu8_surrogate_pairs,
)
from pgtp_editor.model.parser import load_project

# U+1F441 (eye) as CESU-8: high surrogate D83D + low surrogate DC41, each
# written as a separate 3-byte UTF-8-looking sequence. This is exactly the
# malformed encoding real vendor files contain (e.g. caption="👁 All Materials").
EYE_CESU8 = b"\xed\xa0\xbd\xed\xb1\x81"
EYE_UTF8 = "\U0001F441".encode("utf-8")  # the correct 4-byte encoding

CESU8_PGTP = (
    b'<Project>\n'
    b'  <Presentation>\n'
    b'    <Pages>\n'
    b'      <Page fileName="materials" tableName="pr.material" '
    b'caption="' + EYE_CESU8 + b' All Materials"/>\n'
    b'    </Pages>\n'
    b'  </Presentation>\n'
    b'</Project>\n'
)


def test_repair_converts_cesu8_pair_to_real_utf8():
    repaired = repair_cesu8_surrogate_pairs(EYE_CESU8 + b" rest")
    assert repaired == EYE_UTF8 + b" rest"
    # And the repaired bytes decode to the actual emoji.
    assert repaired.decode("utf-8") == "\U0001F441 rest"


def test_repair_is_a_noop_on_clean_bytes():
    clean = b'<Page caption="plain ascii, no emoji"/>'
    assert repair_cesu8_surrogate_pairs(clean) is clean or \
        repair_cesu8_surrogate_pairs(clean) == clean
    # Multibyte-but-valid UTF-8 (already-correct emoji) is left untouched too.
    valid = "café 👁".encode("utf-8")
    assert repair_cesu8_surrogate_pairs(valid) == valid


def test_load_project_parses_a_cesu8_file_and_preserves_the_emoji(tmp_path):
    path = tmp_path / "cesu8.pgtp"
    path.write_bytes(CESU8_PGTP)

    project = load_project(path)

    page = project.pages[0]
    assert page.file_name == "materials"
    # The emoji survived the repair and is present in the parsed caption,
    # not stripped to " All Materials".
    assert page.attrib["caption"] == "\U0001F441 All Materials"


def test_read_pgtp_text_repairs_and_decodes_cesu8(tmp_path):
    path = tmp_path / "cesu8.pgtp"
    path.write_bytes(CESU8_PGTP)

    text = read_pgtp_text(path)

    assert "\U0001F441 All Materials" in text
    # No lone surrogate remains in the decoded text.
    assert "\ud83d" not in text
