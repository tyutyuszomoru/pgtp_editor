# Code Editor for event-handler JS/PHP — Design

**Date:** 2026-07-15

Event-handler code (JS on client events, PHP on server events) is buried and hard to edit in phpgenerator. This adds a dedicated code-editing experience. Built as three sequential sub-projects on one branch (`worktree-pgtp-editor-code-editor`), tested together. Decisions locked: **distinct inline styling + edit affordance** (not a true embedded sub-editor); **reuse/create `<EventHandlers>`, list all known handlers, grey out those already present**; language chosen by event side.

## Shared conventions
- Headless offscreen + `--timeout=60`. The code-editor dialog + all context menus must be **non-blocking / method-drivable** — NO test may call `.exec()` or hit an un-patched modal. Keep pure logic (highlighting rules, autoclose transforms, event-list, text span find/replace) in Qt-free (or QWidget-free) helpers where practical and unit-test them.
- Model: `EventNode{tag_name, side ("C"/"S"), text, sourceline, element}`; `PageNode.events`, `DetailNode.events`. `classify_event_side(tag)` → "C"/"S". `CLIENT_SIDE_EVENT_NAMES` (9) already in `model/nodes.py`.
- Full suite green after each SP. Not merged until all three + review pass.

## Authoritative event-handler list (for the insert picker)
Add `pgtp_editor/model/event_handlers.py` with an ordered list `EVENT_HANDLERS: list[tuple[str, str]]` = (tag_name, side) covering all 40:
- **Client (9, side "C"):** OnBeforePageLoad, OnAfterPageLoad, OnInsertFormLoaded, OnEditFormLoaded, OnInsertFormEditorValueChanged, OnEditFormEditorValueChanged, OnInsertFormValidate, OnEditFormValidate, OnCalculateControlValues.
- **Server (31, side "S"):** OnBeforePageExecute, OnPreparePage, OnGetCustomPagePermissions, OnGetCustomRecordPermissions, OnAddEnvironmentVariables, OnPageLoaded, OnPrepareColumnFilter, OnPrepareFilterBuilder, OnGetSelectionFilters, OnGetCustomFormLayout, OnGetCustomColumnGroup, OnCustomCompareValues, OnFileUpload, OnGetCustomExportOptions, OnCustomHTMLHeader, OnGetCustomTemplate, OnCustomRenderColumn, OnCustomRenderPrintColumn, OnCustomRenderExportColumn, OnCustomDrawRow, OnExtendedCustomDrawRow, OnCustomRenderTotals, OnCustomDefaultValues, OnCalculateFields, OnGetFieldValue, OnBeforeInsertRecord, OnBeforeUpdateRecord, OnBeforeDeleteRecord, OnAfterInsertRecord, OnAfterUpdateRecord, OnAfterDeleteRecord.
`language_for_side(side)` → "js" if "C" else "php". Keep Qt-free.

---

## SP1 — `CodeEditor` widget + `CodeEditorDialog` (`pgtp_editor/ui/code_editor.py`, new)

### `CodeEditor(QPlainTextEdit)`
- Monospace font; construct with `language` ("js"|"php").
- **Syntax highlighting:** a `QSyntaxHighlighter` (`_CodeHighlighter`) with per-language keyword sets (JS keywords; PHP keywords + `$var`), plus strings (`'…'`, `"…"`), line comments (`//`, `#` for PHP) + block comments (`/* … */`), and numbers. Keep the keyword lists as Qt-free module constants (unit-test the token/keyword lists exist and are non-trivial); the highlighter itself is exercised via a widget test that it applies formats.
- **Auto-close (keyPressEvent):** typing an opener inserts its pair with the caret between: `(`→`()`, `{`→`{}`, `[`→`[]`, `'`→`''`, `"`→`""`. Typing a closer (`) } ] ' "`) when the next char is that same closer → **type-through** (move past, don't insert). This mirrors the XmlEditor's existing auto-close approach — reuse its "editor-inserted char" tracking idea.
- **Selection-wrap:** when there is a non-empty selection and an opener OR quote is typed, **wrap** the selection: insert the opener before and its close after, keeping the selection (do NOT replace it). e.g. select `foo`, press `(` → `(foo)` with `foo` still selected. Works for `( ) [ ] { }` (opener wraps with its pair) and quotes (`'`/`"` wrap with same char).
- **Ctrl+Shift+B bracket-select:** select the contents of the innermost bracket pair `() [] {}` enclosing the cursor (and, on repeat, expand outward — optional). Provide a pure helper `enclosing_bracket_span(text, pos)` returning the inner `[start,end)` (or the pair-inclusive span — pick one, document, test) and select it. Caret-at-start on the resulting selection (consistent with the XML editor's convention).
- Standard `Ctrl+C/V/X` come from `QPlainTextEdit` — verify they work (a test).

### `CodeEditorDialog(QDialog)`
- Hosts a `CodeEditor` + OK/Cancel buttons + a title showing the handler name + language.
- `set_code(text)`, `code()`; signals `saved = Signal(str)` and `cancelled = Signal()`.
- **Ctrl+S** → `save()` (emit `saved(code())`, then close/accept). **Ctrl+W** → `cancel()` (emit `cancelled`, close/reject without saving). Wire as `QShortcut`s (WindowShortcut on the dialog).
- Built so tests drive `set_code`/`code`/`save`/`cancel` and the shortcuts' slots directly — never call `.exec()` in a test.

### Tests
Pure: event-list completeness (40, correct sides), `language_for_side`, `enclosing_bracket_span` (nested, unbalanced, cursor outside), autoclose transform helper. Widget (pytest-qt, no `.exec()`): typing `(` inserts `()` caret-between; typing `)` before `)` types through; selection + `(` wraps; selection + `"` wraps; Ctrl+Shift+B selects the bracket span; Ctrl+S emits `saved` with current code; Ctrl+W emits `cancelled`; copy/paste round-trips; highlighter applies at least one format to a keyword.

---

## SP2 — XML-editor integration (`xml_editor.py` + `main_window.py`)

### Distinct styling of code regions
In the XmlEditor, visually mark the text **between `<OnXxx …>` and `</OnXxx>`** (event-handler bodies): a distinct background + monospace font, via the existing syntax highlighter (extend it to detect being inside an event-handler element and apply a code block format) or `QTextEdit.setExtraSelections`/block formats. Keep it read-only-safe (works in Caption Mode too). A pure/testable helper `event_body_line_ranges(text) -> list[(start_line, end_line, tag, side)]` scans for `<OnXxx>`…`</OnXxx>` spans (the known handler tags) so the styling + the "which handler is under the cursor" lookup share one source of truth.

### Edit affordance → open the modal
Add an affordance to edit the handler under the cursor: a gutter marker on event-body lines and/or an editor context-menu action **"Edit code…"** (shown when the cursor is inside an event body). Triggering it: determine the enclosing handler span (`event_body_line_ranges` + cursor line), open `CodeEditorDialog` with that handler's current body text and `language_for_side(side)`. On `saved(new_code)`: replace the text **between** that handler's open and close tags in the raw buffer with `new_code` (a pure `replace_event_body(text, start_line, new_code) -> str` that finds the `<OnXxx …>`/`</OnXxx>` on/after start_line and swaps the inner content, preserving the tags/attributes and indentation), set it into the editor buffer, and (since the editor may be read-only in Caption Mode) do the write via the buffer regardless. MainWindow owns the dialog lifecycle + write-back.

### Tests
Pure: `event_body_line_ranges` finds each handler span with side; `replace_event_body` swaps only the inner text, keeps tags/attributes, handles multi-line bodies and an empty body. UI: "Edit code" opens the dialog prefilled with the handler body + correct language; saving writes the new body into the buffer (assert the raw text); cursor outside any handler → no "Edit code" action. No `.exec()` in tests.

---

## SP3 — Tree integration (`project_tree.py` + `main_window.py`)

### Edit-code on event nodes
Event nodes (the "(E)" rows) get an **edit-code affordance** (a right-click "Edit code…" and/or a small icon): opens `CodeEditorDialog` with the EventNode's `text` + `language_for_side(node.side)`; on save, write the new body back into the buffer at the node's span (reuse `replace_event_body` keyed to `node.sourceline`) via an injected `on_edit_event_code(node)` callback wired in MainWindow.

### Page right-click → Insert Event Handler
Add to the Page menu (built in SP D earlier): **"Add Event Handler ▸"** submenu listing all `EVENT_HANDLERS` (grouped or flat), with handlers already present on that page **disabled/greyed-out** (compare against the page's existing event tag_names). Choosing one → open an empty `CodeEditorDialog` (`language_for_side(side)`); on save → insert into the buffer: if the page's element has no `<EventHandlers>`, create one (in the conventional position — as a child of the page/inner-page element) and add `<OnXxx enabled="true">\n<new code>\n</OnXxx>`; if it exists, append the new handler inside it. A pure `insert_event_handler(text, page_start_line, tag, side, code) -> str` does the buffer edit (locate the page element's span, find/create `<EventHandlers>`, insert the handler with proper indentation). Wire via injected `on_add_event_handler(node, tag)` (the earlier "Add Event Handler" stub becomes this submenu).

### Tests
Pure: `insert_event_handler` creates `<EventHandlers>` when absent and wraps the handler; appends when present; correct `enabled="true"`; indentation sane; result re-parses. UI: event-node "Edit code" opens the dialog with the node body + language and writes back on save; Page "Add Event Handler" submenu lists all handlers with existing ones disabled; picking one opens the editor and, on save, inserts the handler into the buffer. Real-sample smoke (skip if absent): opening an existing handler's code from `dev_Ferrara` shows non-empty code with the right language.

## Risks / notes
- `replace_event_body`/`insert_event_handler` are the risky text-manipulation pieces — keep them pure + heavily unit-tested; they must preserve everything outside the edited span byte-for-byte and produce re-parseable XML.
- After a write-back/insert, the model/tree are stale until the existing **Reparse** action runs; that's acceptable (consistent with caption apply). Optionally trigger a reparse after insert so the new handler appears in the tree — nice-to-have, note it.
- XML/PHP escaping: handler bodies live as element text; `<`, `&` in code must be XML-escaped when written into the buffer (or wrapped in CDATA if the originals use CDATA — check the sample; if bodies are plain escaped text, escape `<`/`&`). Verify against the real sample how bodies are stored and match that.
