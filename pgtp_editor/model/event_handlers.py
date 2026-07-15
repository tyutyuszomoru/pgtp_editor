"""Authoritative list of PHP Generator event-handler tags and their side.

Qt-free. Drives the "insert event handler" picker (SP3) and the language
choice for the code editor (SP1). Each entry is ``(tag_name, side)`` where
``side`` is ``"C"`` (client, JavaScript) or ``"S"`` (server, PHP). The order
is the spec's order: the 9 client handlers first, then the 31 server handlers.
"""
from __future__ import annotations

# 9 client-side (JS) handlers.
_CLIENT_HANDLERS: list[str] = [
    "OnBeforePageLoad",
    "OnAfterPageLoad",
    "OnInsertFormLoaded",
    "OnEditFormLoaded",
    "OnInsertFormEditorValueChanged",
    "OnEditFormEditorValueChanged",
    "OnInsertFormValidate",
    "OnEditFormValidate",
    "OnCalculateControlValues",
]

# 31 server-side (PHP) handlers.
_SERVER_HANDLERS: list[str] = [
    "OnBeforePageExecute",
    "OnPreparePage",
    "OnGetCustomPagePermissions",
    "OnGetCustomRecordPermissions",
    "OnAddEnvironmentVariables",
    "OnPageLoaded",
    "OnPrepareColumnFilter",
    "OnPrepareFilterBuilder",
    "OnGetSelectionFilters",
    "OnGetCustomFormLayout",
    "OnGetCustomColumnGroup",
    "OnCustomCompareValues",
    "OnFileUpload",
    "OnGetCustomExportOptions",
    "OnCustomHTMLHeader",
    "OnGetCustomTemplate",
    "OnCustomRenderColumn",
    "OnCustomRenderPrintColumn",
    "OnCustomRenderExportColumn",
    "OnCustomDrawRow",
    "OnExtendedCustomDrawRow",
    "OnCustomRenderTotals",
    "OnCustomDefaultValues",
    "OnCalculateFields",
    "OnGetFieldValue",
    "OnBeforeInsertRecord",
    "OnBeforeUpdateRecord",
    "OnBeforeDeleteRecord",
    "OnAfterInsertRecord",
    "OnAfterUpdateRecord",
    "OnAfterDeleteRecord",
]

EVENT_HANDLERS: list[tuple[str, str]] = [
    *[(tag, "C") for tag in _CLIENT_HANDLERS],
    *[(tag, "S") for tag in _SERVER_HANDLERS],
]


def language_for_side(side: str) -> str:
    """Return the editor language for an event side: ``"js"`` for client
    (``"C"``), ``"php"`` for server (``"S"``)."""
    return "js" if side == "C" else "php"
