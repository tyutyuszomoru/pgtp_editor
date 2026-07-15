"""Pure (Qt-free) tests for SP3's ``insert_event_handler`` buffer edit.

Inserts a new ``<OnXxx enabled="true">…</OnXxx>`` into the correct page's
``<EventHandlers>`` (creating it if absent), preserving everything outside the
edit and producing re-parseable XML.
"""
import pytest
from lxml import etree

from pgtp_editor.ui.event_body import insert_event_handler

# A page that already has an <EventHandlers> child with one handler.
WITH_HANDLERS = (
    "<Project>\n"
    "  <Pages>\n"
    '    <Page fileName="equipment">\n'
    "      <EventHandlers>\n"
    '        <OnPreparePage enabled="true">echo &#39;hi&#39;;</OnPreparePage>\n'
    "      </EventHandlers>\n"
    "    </Page>\n"
    "  </Pages>\n"
    "</Project>\n"
)

# A page with NO <EventHandlers> child.
WITHOUT_HANDLERS = (
    "<Project>\n"
    "  <Pages>\n"
    '    <Page fileName="equipment">\n'
    "      <ColumnPresentations>\n"
    '        <ColumnPresentation fieldName="tag"/>\n'
    "      </ColumnPresentations>\n"
    "    </Page>\n"
    "  </Pages>\n"
    "</Project>\n"
)

# An outer page whose nested Detail has its own inner Page + EventHandlers.
# The outer page itself has NO EventHandlers -> a new one must be created as a
# child of the OUTER page, NOT appended to the nested detail's EventHandlers.
NESTED_DETAIL = (
    "<Project>\n"
    "  <Pages>\n"
    '    <Page fileName="equipment">\n'
    "      <Details>\n"
    "        <Detail>\n"
    '          <Page fileName="">\n'
    "            <EventHandlers>\n"
    '              <OnPreparePage enabled="true">nested();</OnPreparePage>\n'
    "            </EventHandlers>\n"
    "          </Page>\n"
    "        </Detail>\n"
    "      </Details>\n"
    "    </Page>\n"
    "  </Pages>\n"
    "</Project>\n"
)


def _page_line(text, file_name):
    """1-based line of the <Page fileName="..."> open tag."""
    for i, line in enumerate(text.splitlines(), start=1):
        if f'fileName="{file_name}"' in line and "<Page" in line:
            return i
    raise AssertionError(f"no <Page fileName={file_name!r}> in fixture")


# ---------------------------------------------------------------------------
# append into an existing <EventHandlers>
# ---------------------------------------------------------------------------

def test_appends_into_existing_event_handlers():
    line = _page_line(WITH_HANDLERS, "equipment")
    result = insert_event_handler(WITH_HANDLERS, line, "OnAfterPageLoad", "alert(1);")
    # Original handler still present.
    assert "OnPreparePage" in result
    # New handler present with enabled="true".
    assert '<OnAfterPageLoad enabled="true">' in result
    assert "</OnAfterPageLoad>" in result
    # Re-parses and the new handler is a child of the page's EventHandlers.
    root = etree.fromstring(result.encode("utf-8"))
    handlers = root.find(".//Page/EventHandlers")
    tags = [child.tag for child in handlers]
    assert "OnPreparePage" in tags
    assert "OnAfterPageLoad" in tags


def test_append_body_round_trips():
    line = _page_line(WITH_HANDLERS, "equipment")
    code = "if (a < b && c > d) { e(); }"
    result = insert_event_handler(WITH_HANDLERS, line, "OnAfterPageLoad", code)
    root = etree.fromstring(result.encode("utf-8"))
    node = root.find(".//OnAfterPageLoad")
    # Stored on its own line(s) between the tags -> body round-trips modulo the
    # surrounding newline/indent (the conventional storage layout).
    assert node.text.strip() == code  # lxml unescapes back to the original


def test_append_preserves_everything_outside():
    line = _page_line(WITH_HANDLERS, "equipment")
    result = insert_event_handler(WITH_HANDLERS, line, "OnAfterPageLoad", "x();")
    assert result.startswith("<Project>\n  <Pages>\n")
    assert result.endswith("  </Pages>\n</Project>\n")
    # The pre-existing handler line is untouched.
    assert "<OnPreparePage enabled=\"true\">echo &#39;hi&#39;;</OnPreparePage>" in result


# ---------------------------------------------------------------------------
# create <EventHandlers> when absent
# ---------------------------------------------------------------------------

def test_creates_event_handlers_when_absent():
    line = _page_line(WITHOUT_HANDLERS, "equipment")
    result = insert_event_handler(WITHOUT_HANDLERS, line, "OnPreparePage", "go();")
    assert "<EventHandlers>" in result
    assert "</EventHandlers>" in result
    assert '<OnPreparePage enabled="true">' in result
    root = etree.fromstring(result.encode("utf-8"))
    handlers = root.find(".//Page/EventHandlers")
    assert handlers is not None
    assert [c.tag for c in handlers] == ["OnPreparePage"]


def test_created_handler_is_child_of_page_not_sibling():
    line = _page_line(WITHOUT_HANDLERS, "equipment")
    result = insert_event_handler(WITHOUT_HANDLERS, line, "OnPreparePage", "go();")
    root = etree.fromstring(result.encode("utf-8"))
    page = root.find(".//Page")
    # EventHandlers is a direct child of Page (not of ColumnPresentations etc).
    child_tags = [c.tag for c in page]
    assert "EventHandlers" in child_tags
    # Pre-existing ColumnPresentations preserved.
    assert "ColumnPresentations" in child_tags


def test_create_body_round_trips_and_reparses():
    line = _page_line(WITHOUT_HANDLERS, "equipment")
    code = "if (x < 1 && y > 2) z('a & b');"
    result = insert_event_handler(WITHOUT_HANDLERS, line, "OnPreparePage", code)
    root = etree.fromstring(result.encode("utf-8"))
    assert root.find(".//OnPreparePage").text.strip() == code


# ---------------------------------------------------------------------------
# enabled="true" attribute
# ---------------------------------------------------------------------------

def test_enabled_attribute_present_on_new_handler():
    line = _page_line(WITH_HANDLERS, "equipment")
    result = insert_event_handler(WITH_HANDLERS, line, "OnAfterPageLoad", "y();")
    root = etree.fromstring(result.encode("utf-8"))
    node = root.find(".//OnAfterPageLoad")
    assert node.get("enabled") == "true"


# ---------------------------------------------------------------------------
# correct page: nested detail must not steal the insert
# ---------------------------------------------------------------------------

def test_insert_into_outer_page_creates_own_event_handlers_not_nested():
    line = _page_line(NESTED_DETAIL, "equipment")
    result = insert_event_handler(NESTED_DETAIL, line, "OnAfterPageLoad", "outer();")
    root = etree.fromstring(result.encode("utf-8"))
    outer_page = root.find(".//Pages/Page")
    # The outer page now has its OWN EventHandlers holding the new handler.
    outer_handlers = outer_page.find("EventHandlers")
    assert outer_handlers is not None
    assert [c.tag for c in outer_handlers] == ["OnAfterPageLoad"]
    # The nested detail's inner-page EventHandlers is untouched (still only
    # its OnPreparePage).
    nested_handlers = outer_page.find("Details/Detail/Page/EventHandlers")
    assert [c.tag for c in nested_handlers] == ["OnPreparePage"]


def test_nested_detail_body_untouched():
    line = _page_line(NESTED_DETAIL, "equipment")
    result = insert_event_handler(NESTED_DETAIL, line, "OnAfterPageLoad", "outer();")
    assert 'nested();' in result
    root = etree.fromstring(result.encode("utf-8"))
    assert root.find(".//Details//OnPreparePage").text == "nested();"


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

def test_no_page_at_line_raises():
    # Line 2 has no element opening on it -> no page span to target.
    text = "<Project></Project>\n\n"
    with pytest.raises(ValueError):
        insert_event_handler(text, 2, "OnPreparePage", "x();")
