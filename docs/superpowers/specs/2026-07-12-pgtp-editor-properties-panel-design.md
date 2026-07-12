# PGTP Editor — Properties Panel (Properties Sub-project 3 of 3) Design Specification

**Date:** 2026-07-12
**Status:** Approved for planning
**Depends on:** [2026-07-11-pgtp-editor-design.md](2026-07-11-pgtp-editor-design.md) (original shell design, §5.1 "IDE-style docked panels", §5.2 menu bar "☑ Properties Panel"), the completed Real Model sub-project (`pgtp_editor/model/nodes.py`, `pgtp_editor/model/parser.py`), the completed Diff/Merge work that added the `NODE_KIND_ROLE`/`TABLE_NAME_ROLE`/`MODEL_NODE_ROLE` item-data pattern to `pgtp_editor/ui/project_tree.py`, and the **not-yet-merged** XML Editor Foundation sub-project (its design at `pgtp-editor-xmleditor-foundation` worktree's `docs/superpowers/specs/2026-07-12-pgtp-editor-xml-editor-foundation-design.md`, specifically its `XmlEditor` widget shape and `highlight_error_line(line)` method, §4.5 there).

## 1. Context and scope

This is the third and final sub-project of the "Properties" feature area sketched at a high level in the original design spec (§5.1's "Properties" center-stage tab, later moved to an always-visible dock by the "Canvas" sub-project — see `pgtp_editor/ui/main_window.py`'s current `self.properties_dock`). The three sub-projects, in dependency order:

1. **Real Model** (done, merged) — `pgtp_editor/model/nodes.py`, `pgtp_editor/model/parser.py`. Produces the `PageNode`/`DetailNode`/`ColumnNode`/`EventNode` dataclasses this document reads from.
2. **Raw XML display** — never built as its own sub-project. Superseded by the XML Editor Foundation sub-project (a separate, larger feature area, currently implementing in a sibling worktree, not yet merged into this one): once an `XmlEditor` widget exists and shows a project's real file text with syntax highlighting, a separate simpler "just show the text" widget would be redundant. That decision was made and recorded in the XML Editor Foundation sub-project's own design document; this document does not revisit it, only depends on the result.
3. **Properties panel itself** (this document) — the read-only, navigate-only viewer decided during the original "Properties feature" brainstorming ("option A": "shows everything phpgen lets you set on the selected object; click a property to jump to where it's set in the XML; not an editor").

This document covers only sub-project 3.

**Why this document does not implement or modify the XML Editor:** the XML Editor Foundation sub-project is not merged into this worktree's lineage yet, so its `XmlEditor` class does not exist here. This document designs the Properties panel's navigation call against that sub-project's *specified* API (read directly from its design document in the sibling worktree — see §4.2 below for the exact method and naming decision), and states plainly that full end-to-end testing of the navigation call is blocked until that sub-project is merged (§5.3).

## 2. Scope

### 2.1 In scope

- New file `pgtp_editor/ui/properties_panel.py` — `PropertiesPanel(QWidget)`: a header label plus a two-column (`Property`, `Value`) `QTableWidget`, populated per the selected node's kind (§3.2–§3.4).
- A new `inner_sourceline: int | None = None` field on `DetailNode` (`pgtp_editor/model/nodes.py`), populated in `pgtp_editor/model/parser.py`'s `_parse_detail` from the nested `<Page>` element's own `.sourceline` (§3.1).
- Wiring `ProjectTreePanel`'s selection to the panel: adding a `currentItemChanged` connection/signal to `project_tree.py` (confirmed not present today — see §3.5) so selecting a Page/Detail/Column/Event tree item repopulates the panel.
- Replacing `MainWindow`'s current `self.properties_panel = QWidget()` placeholder with a real `PropertiesPanel` instance (§3.6).
- Click-to-navigate: clicking a row in the table (a) calls into the XML Editor's line-navigation API to scroll to and highlight the resolved line, then (b) for attribute-style rows, additionally highlights just the `attr="value"` substring within that line (§3.4).
- Unit tests for row-building logic, kept Qt-free where feasible (§5.1); `pytest-qt` tests for the panel and its click-to-navigate wiring using a stub in place of the real `XmlEditor` (§5.2).

### 2.2 Explicitly out of scope

- Any editing capability. This panel is read-only/navigation-only, per the original "option A" decision — no property value can be changed from this panel, no cell is ever made editable, and no write path back into the `ProjectModel` or the XML exists here.
- The XML Editor's own implementation (syntax highlighting, folding, gutter, etc.). This document only calls into whatever line-navigation method the XML Editor Foundation sub-project exposes (or is specified to expose) — it does not implement, modify, or restate that widget's internals beyond the one method signature it depends on.
- A real PHP/JS parser for the Event "Functions: N" count. It is explicitly a regex-based heuristic, scoped and documented in §3.3.
- Any change to how the Project Tree displays nodes (labels, icons, ordering), Diff/Merge, or Schema Learning. Unrelated to this document. The only change this document makes to `project_tree.py` is adding the selection-changed wiring described in §3.5.
- True end-to-end integration testing of the navigation call against a real `XmlEditor` instance — blocked on the XML Editor Foundation sub-project being merged into this worktree's lineage (§5.3).

## 3. Architecture

### 3.1 Model change: `DetailNode.inner_sourceline`

Confirmed by reading `pgtp_editor/model/nodes.py` and `pgtp_editor/model/parser.py` directly in this worktree: `DetailNode` currently has a single `sourceline: int | None = None`, populated in `_parse_detail` from the outer `<Detail>` element (`detail_el.sourceline`). The nested `<Page>` element's own `sourceline` (`inner_page_el.sourceline`) is read inside `_parse_detail` today only to build `merged_attrib`/`columns`/`events`/`nested_details` — its own line number is discarded.

This sub-project adds a second field and threads that discarded value through:

```python
# pgtp_editor/model/nodes.py
@dataclass
class DetailNode:
    identity: str
    attrib: dict
    sourceline: int | None = None
    inner_sourceline: int | None = None
    details: list["DetailNode"] = field(default_factory=list)
    columns: list[ColumnNode] = field(default_factory=list)
    events: list[EventNode] = field(default_factory=list)
```

```python
# pgtp_editor/model/parser.py, _parse_detail
    return DetailNode(
        identity=identity,
        attrib=merged_attrib,
        sourceline=detail_el.sourceline,
        inner_sourceline=inner_page_el.sourceline,
        details=nested_details,
        columns=columns,
        events=events,
    )
```

This is the only change to `parser.py`/`nodes.py` in this sub-project — everything else in `_parse_detail` (the merge order, the outer-attrs-then-inner-attrs-override rule) is untouched.

**Why two sourcelines, and why the row-building logic in §3.2 splits on `caption` specifically:** empirically, in real `.pgtp` files, the outer `<Detail>` element only ever carries a `caption` attribute; everything else (`tableName`, ability modes, etc.) lives on the nested `<Page>`. This was already independently confirmed during the Real Model sub-project's own implementation notes (see that sub-project's design/plan history) and is re-confirmed here by inspection of `_parse_detail`'s own doc comment: *"Merge Detail's own attributes with the nested Page's attributes: the nested Page carries the substantive data (tableName, caption, ability modes, etc.) while Detail itself typically only carries a caption."* Since `merged_attrib` is built as `dict(detail_el.attrib)` updated by `dict(inner_page_el.attrib)`, a `caption` present on the nested Page would already have overwritten the outer one in the merged dict by the time the Properties panel sees it — but the *line number* that should be used for navigating to that key depends on which element the key actually came from in the source XML, which is exactly why `inner_sourceline` needs to exist as a distinct value rather than being inferred from the merged dict alone.

### 3.2 Row-building logic per node kind

Row-building is implemented as plain functions taking a model node and returning `list[RowSpec]`, deliberately **not** methods that also touch `QTableWidget`, so this logic is unit-testable without a `QApplication` (§5.1). `PropertiesPanel` itself is the only place that turns this list into actual `QTableWidgetItem`s.

```python
# pgtp_editor/ui/properties_panel.py

@dataclass
class RowSpec:
    property_label: str
    value: str
    target_line: int | None
    attr_name: str | None   # None for rows with no single key="value" to refine onto (§3.4)


def _rows_for_attrib_node(node) -> list[RowSpec]:
    """Shared helper for Page/Column: one row per attrib key."""
    return [
        RowSpec(property_label=key, value=str(value), target_line=node.sourceline, attr_name=key)
        for key, value in node.attrib.items()
    ]
```

- **Page**: `_rows_for_attrib_node(page_node)` — one row per key in `page_node.attrib`, generic and complete (every attribute the model captured, not a curated subset), consistent with the model layer's own "capture everything generically" philosophy (`attrib=dict(page_el.attrib)` in `parser.py`). Every row's `target_line` is `page_node.sourceline`.
- **Column**: `_rows_for_attrib_node(column_node)` — same shape, one row per `column_node.attrib` key, `target_line` is `column_node.sourceline` for every row (a `ColumnPresentation` element has no nested/merged structure the way `Detail` does).
- **Detail**: one row per key in `detail_node.attrib`, but with a **per-row line split**:
  ```python
  def _rows_for_detail(detail_node) -> list[RowSpec]:
      rows = []
      for key, value in detail_node.attrib.items():
          line = detail_node.sourceline if key == "caption" else detail_node.inner_sourceline
          rows.append(RowSpec(property_label=key, value=str(value), target_line=line, attr_name=key))
      return rows
  ```
  The `caption` row's `target_line` is `detail_node.sourceline` (the outer `<Detail>` element's own line); every other row's `target_line` is `detail_node.inner_sourceline` (the nested `<Page>` element's line) — per the empirical justification in §3.1. If `detail_node.inner_sourceline` is `None` (should not happen in practice, since every `DetailNode` is only constructed from a `<Detail>` that itself had a nested `<Page>` — see `_parse_detail`'s own `ValueError` guard — but defensively handled rather than assumed), the row's navigation click falls back to the whole-row-disabled behavior described in §3.4's failure-mode handling (never a crash).
- **Event**: exactly three rows, not attrib-driven (an `EventNode` has no `attrib` dict at all — its data is `tag_name`/`side`/`text`):
  ```python
  def _rows_for_event(event_node) -> list[RowSpec]:
      side_label = "Client" if event_node.side == "C" else "Server"
      return [
          RowSpec("Handler", event_node.tag_name, event_node.sourceline, attr_name=None),
          RowSpec("Side", side_label, event_node.sourceline, attr_name=None),
          RowSpec("Functions", str(_count_functions(event_node.text)), event_node.sourceline, attr_name=None),
      ]
  ```
  All three rows navigate to `event_node.sourceline` (the `<OnXxx>` element's own opening line — there is nothing more specific to navigate to for "Handler"/"Side"/"Functions", since none of the three is a `key="value"` attribute pair; see §3.4 for why `attr_name=None` means these rows skip the column-precise refinement step entirely, not that they don't navigate at all).
- **No selection**: `PropertiesPanel` shows an empty-state message (a `QLabel`, e.g. *"Select a Page, Detail, Column, or Event to see its properties"*) in place of the table — see §3.6 for the exact widget-swap mechanism.

**Header label** shown above the table reflects what's currently selected, built from the same identity fields the Project Tree already displays:
- Page: `f"Page: {page_node.file_name or page_node.identity}"` (e.g. `"Page: development_equipment"`)
- Detail: `f"Detail: {detail_node.table_name}/{detail_node.attrib.get('caption', '')}"` (e.g. `"Detail: pr.attachment/Sub-item"`)
- Column: `f"Column: {column_node.field_name}"`
- Event: `f"Event: {event_node.tag_name}"` (e.g. `"Event: OnPreparePage"`)

### 3.3 The Event "Functions: N" heuristic

**Regex design, grounded against real sample data.** `sample/dev_Ferrara.pgtp` and `sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp` were inspected directly (both already present, gitignored, in this worktree's `sample/` directory) for real `EventHandlers` bodies. Findings that shaped the regex:

- Client-side handlers (`OnEditFormLoaded`, `OnInsertFormLoaded`, `OnPageLoaded`, etc.) are JavaScript and contain both **named** function declarations (`function setLoadingState() {`, `function initLimit() {`) and **anonymous** ones used as callbacks (`setTimeout(function() {`, `.setQueryFunction(function(term) {`, `$('span.subs').each(function() {`) — a single real `OnEditFormLoaded` body in `dev_Ferrara.pgtp` (3579 raw/entity-escaped characters) contains 5 named functions (`setLoadingState`, `setReadyState`, `initLimit`, `onOperationReady`, `initJobcardDeps`) plus roughly 9 anonymous callback functions.
- Server-side handlers (`OnCalculateFields`, `OnCustomDefaultValues`, `OnGetCustomPagePermissions`, etc.) are PHP and are frequently **snippet bodies with zero function declarations at all** — e.g. a real `OnCalculateFields` body is just `if ($fieldName == 'manning') { ... $value = $res[0]['manning']; }`, and a real `OnGetCustomPagePermissions` body is a bare `foreach` loop. "Functions: 0" is a common and correct result for these, not an edge case to special-case away.
- A real `OnGetCustomTemplate` body (18356 characters, PHP-heavy with embedded SQL) contains the substring `functionallocation` (a column name) repeatedly — confirming the regex must not match on a bare substring of the word "function"; it needs a word boundary so `functionallocation` is never miscounted as a function declaration.

**The regex:**

```python
import re

_FUNCTION_DECL_RE = re.compile(r"\bfunction\s*[A-Za-z_$][A-Za-z0-9_$]*\s*\(|\bfunction\s*\(")

def _count_functions(text: str) -> int:
    return len(_FUNCTION_DECL_RE.findall(text or ""))
```

This matches, in one alternation: `function name(` (named — PHP or JS, optional whitespace between `function` and the name, and between the name and `(`, matching real formatting variance like `function ()` seen with a space before the paren in some hand-written callbacks) and `function(`/`function (` (anonymous, zero-or-more identifier characters). `\b` before `function` prevents matching inside a longer identifier like `functionallocation`. Verified directly against the real sample bodies above: the 3579/3572-character `OnEditFormLoaded` bodies each yield double-digit counts (14 and 12 respectively, matching the expected mix of ~5 named + several anonymous callbacks) and the `OnGetCustomTemplate`/`OnCalculateFields`/`OnGetCustomPagePermissions` bodies (no function declarations) yield 0.

**Explicitly documented as an approximate heuristic, not a real parser.** What it will and won't correctly count, stated plainly so no future reader mistakes this for exact:

- **Will count:** any occurrence of the literal token `function` (word-bounded) followed by an optional identifier and an opening parenthesis — this covers the overwhelming majority of real declarations and callbacks observed in the sample data, both named and anonymous, in both PHP and JS.
- **Will not correctly count:** ES6 arrow functions (`const f = (x) => x + 1`) — no `function` keyword appears, so these are invisible to this heuristic entirely. This is an accepted gap: no arrow functions were observed in the real sample data inspected, and adding arrow-function detection would meaningfully complicate the regex (arrow functions have no reliable single-token anchor the way `function` is) for a case that isn't demonstrated to occur in this codebase's actual event-handler bodies.
- **Will not correctly count:** a `function` keyword appearing inside a string literal or a comment (e.g. a code comment that says `// old function() removed` or a string containing the word). The regex has no lexical awareness of strings/comments — this is the same class of imprecision explicitly accepted for the XML Editor Foundation's own `xml_structure.py` scanner (a "lenient, regex-based, best-effort" tool, not a real parser) and is treated the same way here: a rare source of over-counting, not treated as a bug to chase down.
- **Will count each nested/inner function declaration independently** — a function declared inside another function's body is still a `function` token followed by `(`, so it is counted separately, which matches the intuitive reading of "how many function bodies are in this handler," not "how many top-level function statements."
- **Will not distinguish** a function *declaration* from a function *expression assigned to a variable* (`var f = function() {...}`) — both produce the same `function(` token sequence and are both counted, which is the desired behavior here (both are "a function" for the purposes of this count) rather than a limitation worth flagging as a gap.

### 3.4 Click-to-navigate

Each row built by §3.2 carries a `target_line: int | None` and, for attribute-style rows only, an `attr_name: str | None`. `PropertiesPanel` connects `QTableWidget.cellClicked` (row, column) to a handler that looks up the corresponding `RowSpec` (stored alongside the table, e.g. as a `list[RowSpec]` parallel to the currently-populated rows, indexed by row number) and performs, in order:

```python
def _on_row_clicked(self, row: int, _column: int) -> None:
    spec = self._current_rows[row]
    if spec.target_line is None:
        return  # nothing resolvable to navigate to (defensive; see §3.2)
    self._xml_editor.navigate_to_line(spec.target_line)
    if spec.attr_name is not None:
        self._select_attribute_on_line(spec.target_line, spec.attr_name)
```

**(a) Line-level navigation — naming decision.** The XML Editor Foundation sub-project's design (read directly from its spec, §4.5 there) specifies `XmlEditor.highlight_error_line(line: int)`, a method that both scrolls/centers the cursor on the given line (`setTextCursor` + `centerCursor()`) and highlights the whole line via `setExtraSelections`, with an explicit one-shot semantics ("a one-shot indicator for the moment of the fallback... not a persistent marker that survives cursor movement"). That method's name is scoped specifically to the Tier-1 parse-error use case ("error" is in the name, and its doc/design frames it around a `PgtpParseError`'s line), but its *mechanism* — scroll-to-line plus a one-shot full-line highlight distinct from the current-line highlight — is exactly what this panel's click-to-navigate needs, for a use case that has nothing to do with parse errors.

**Decision: this document specifies that the XML Editor Foundation sub-project's `XmlEditor` gains a second, more general public method, `navigate_to_line(line: int) -> None`, and that `highlight_error_line` is reimplemented in terms of it** (`highlight_error_line` becomes a thin wrapper: navigate, then apply the error-colored variant of the highlight; `navigate_to_line` itself uses the same one-shot full-line-highlight mechanism but with a distinct, non-error highlight color, since a property-navigation jump is not an error and should not look like one). This is a small, targeted addition to that sub-project's surface, not a modification of its already-approved internal behavior: the scroll/center/highlight *mechanism* is unchanged, only exposed under a name that isn't error-specific, with a second call site (this panel) using it directly. This decision is recorded here because the Properties panel is the first consumer of that generalized name; the XML Editor Foundation sub-project's own document should be treated as needing this small follow-up addition when the two sub-projects are reconciled, rather than this document inventing an incompatible parallel method. Until that reconciliation happens, `PropertiesPanel`'s navigation code calls `self._xml_editor.navigate_to_line(line)` against whatever object is injected as `self._xml_editor` — a real `XmlEditor` (once merged and extended per this decision) or a stub exposing the same method name (§5.2, for testing today).

**(b) Column-precise refinement, for attribute-style rows only.** The Event panel's "Functions: N" row has `attr_name=None` (there is no single `key="value"` attribute this count corresponds to) and is excluded from this step — only step (a) runs for it. For every other row, after `navigate_to_line` returns, `_select_attribute_on_line` performs a simple, documented search:

```python
def _select_attribute_on_line(self, line: int, attr_name: str) -> None:
    line_text = self._xml_editor.line_text(line)  # 1-based, matching navigate_to_line's convention
    needle = f'{attr_name}="'
    start = line_text.find(needle)
    if start == -1:
        return  # fall back to the line-level highlight already applied by navigate_to_line — never crash, never silently do nothing beyond that
    value_start = start + len(needle)
    end = line_text.find('"', value_start)
    if end == -1:
        return  # malformed/unexpected quoting on this line — same fallback
    self._xml_editor.select_range_on_line(line, start, end + 1)
```

- **Algorithm:** a plain substring search for `f'{attr_name}="'` within the target line's own text, then selecting from that match's start through the closing `"` (inclusive), i.e. the full `attr_name="value"` span. This deliberately does not attempt to parse the line as XML — it is a targeted string search scoped to one already-resolved line, which is exactly precise enough for the stated goal ("the column-precise refinement this whole feature exists to provide") without needing a real XML tokenizer for a single-line lookup.
- **Failure mode, explicitly designed per the requirement "never crash, never silently do nothing":** if `needle` isn't found on the expected line at all (e.g. some edge case in attribute formatting, or if a line-ending/whitespace difference means the attribute isn't rendered exactly as `name="`), or if a closing quote can't be found after the opening one, the method simply returns without raising and without selecting anything further — the line-level highlight from step (a) (already applied by `navigate_to_line` before this method is even called) remains the visible result. This is "fall back to just the line-level highlight," stated exactly as required: nothing is left unhighlighted, nothing throws, and the user still lands on the correct line even in this fallback case.
- **`line_text(line)` and `select_range_on_line(line, start, end)`** are two more small methods this document specifies as needed on `XmlEditor` beyond `navigate_to_line` — `line_text` returns the given 1-based line's plain text (a thin wrapper over `self.document().findBlockByNumber(line - 1).text()`), and `select_range_on_line` sets a character-range selection within that line as an additional/replacement extra-selection alongside the line-level one from `navigate_to_line` (visually: the whole line highlighted faintly, the specific `attr="value"` span highlighted more strongly — the exact visual treatment is an XML Editor Foundation implementation detail, not specified numerically here, matching that sub-project's own stated policy on highlight colors). Like `navigate_to_line`, these are additions this document identifies as needed; they do not exist in the XML Editor Foundation's current design document and should be added there when the two sub-projects are reconciled.

### 3.5 Wiring the Project Tree's selection to the panel

**Confirmed directly by reading `pgtp_editor/ui/project_tree.py` in this worktree:** `NODE_KIND_ROLE`, `TABLE_NAME_ROLE`, and `MODEL_NODE_ROLE` are all already present (`Qt.ItemDataRole.UserRole`, `+1`, `+2` respectively), and every tree item constructed in `populate_from_project`/`_populate_details_and_events` already carries its underlying model node via `setData(0, MODEL_NODE_ROLE, node)` — for Page and Detail items today. **Column and Event items do not currently get `MODEL_NODE_ROLE` set** (`_populate_details_and_events`'s `column_item`/`event_item` construction only sets `NODE_KIND_ROLE`, not `MODEL_NODE_ROLE`) — this sub-project adds that (`column_item.setData(0, MODEL_NODE_ROLE, column)` and `event_item.setData(0, MODEL_NODE_ROLE, event)`), since the Properties panel needs the real `ColumnNode`/`EventNode` object for every selectable kind, not just Page/Detail. This worktree branched from the combined worktree (Real Model + Diff/Merge 1&2 + Schema Learning already merged), so `MODEL_NODE_ROLE` itself did not need to be introduced here — it already exists — only its coverage of Column/Event items needed extending. (Cross-checked against `pgtp-editor-diffmerge-writeback`'s `project_tree.py` for how the role was originally introduced there — same shape, confirming this worktree's copy is the same lineage, not a divergent reimplementation.)

**Confirmed no selection-changed wiring exists today:** neither `ProjectTreePanel.__init__` nor `MainWindow.__init__` connects anything to `QTreeWidget`'s built-in `currentItemChanged`/`itemSelectionChanged` signals — the existing signal wiring on `ProjectTreePanel` is exclusively `customContextMenuRequested` (right-click menus). This sub-project adds a real connection:

```python
# pgtp_editor/ui/project_tree.py, ProjectTreePanel.__init__
        self.currentItemChanged.connect(self._on_current_item_changed)
        self._on_selection_changed = on_selection_changed or (lambda node, kind: None)

    def _on_current_item_changed(self, current, _previous):
        if current is None:
            self._on_selection_changed(None, None)
            return
        node = current.data(0, MODEL_NODE_ROLE)
        kind = current.data(0, NODE_KIND_ROLE)
        self._on_selection_changed(node, kind)
```

`currentItemChanged` (not `itemSelectionChanged`) is chosen because it directly hands both the newly-current item and the previous one, matching the existing codebase's own preference for direct-item-bearing Qt signals over the item-list-based alternative (`itemSelectionChanged` requires a follow-up `self.selectedItems()` call to get anything usable) — and because the Properties panel only ever needs to reflect a single current selection, not a multi-select set (multi-select in this tree is already handled distinctly, for context-menu purposes only, in `menu_for_position`). `on_selection_changed` is added as a new constructor callback parameter on `ProjectTreePanel`, following the exact existing pattern of `on_stub_action`/`on_compare_page`/`on_compare_detail` (all optional callables defaulting to a no-op lambda) rather than a Qt `Signal` — matching this codebase's established convention for `ProjectTreePanel`'s external callback surface (a `Signal` would also work technically, but would be the only place in this file departing from the constructor-callback convention already used three times over).

### 3.6 `MainWindow` wiring

```python
# pgtp_editor/ui/main_window.py
        self.project_tree = ProjectTreePanel(
            on_stub_action=self._not_implemented,
            on_compare_page=self._compare_page_with,
            on_compare_detail=self._compare_detail_with,
            on_selection_changed=self._on_tree_selection_changed,
        )
        ...
        self.properties_panel = PropertiesPanel(xml_editor=self.center_stage.xml_editor)
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setObjectName("properties_dock")
        self.properties_dock.setWidget(self.properties_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

    def _on_tree_selection_changed(self, node, kind):
        self.properties_panel.show_node(node, kind)
```

This replaces the current `self.properties_panel = QWidget()` placeholder exactly, and adds one new handler method plus the `on_selection_changed` callback wiring from §3.5. `self.center_stage` must be constructed before `self.properties_panel` for this ordering to work (today, `self.center_stage = CenterStage()` already runs after the docks are built in `MainWindow.__init__` — this sub-project reorders that: `CenterStage` construction moves earlier, immediately after `self.project_tree`, so `self.center_stage.xml_editor` exists by the time `PropertiesPanel` is constructed). `PropertiesPanel` takes the `XmlEditor` instance (or a stub implementing the same three methods, for tests — see §5.2) as a constructor argument rather than reaching for it via a global/singleton, matching the same dependency-injection-by-constructor style already used for `ProjectTreePanel`'s callbacks.

`PropertiesPanel.show_node(node, kind)` is the single public entry point that repopulates the panel:

```python
class PropertiesPanel(QWidget):
    def __init__(self, xml_editor, parent=None):
        super().__init__(parent)
        self._xml_editor = xml_editor
        self._current_rows: list[RowSpec] = []
        # header QLabel + QStackedWidget-or-equivalent holding the QTableWidget
        # and the empty-state QLabel, per the widget layout described below.
        ...

    def show_node(self, node, kind: str | None) -> None:
        if node is None or kind is None:
            self._show_empty_state()
            return
        builders = {
            "page": (lambda n: _rows_for_attrib_node(n), lambda n: f"Page: {n.file_name or n.identity}"),
            "detail": (_rows_for_detail, lambda n: f"Detail: {n.table_name}/{n.attrib.get('caption', '')}"),
            "column": (lambda n: _rows_for_attrib_node(n), lambda n: f"Column: {n.field_name}"),
            "event": (_rows_for_event, lambda n: f"Event: {n.tag_name}"),
        }
        rows_fn, header_fn = builders[kind]
        self._current_rows = rows_fn(node)
        self._populate_table(header_fn(node), self._current_rows)
```

The empty-state/table swap is implemented as two widgets stacked in a simple layout where one is hidden and the other shown (a `QStackedWidget` with two pages, or an equivalent `setVisible` toggle on a header label + table vs. a single empty-state label — either is a valid implementation detail; this document does not mandate `QStackedWidget` specifically since nothing about the requirements needs its extra machinery over a plain visibility toggle, but either is compatible with the testing strategy in §5.2, which asserts on visible widget state, not on the specific container class used).

## 4. Testing strategy

### 4.1 Unit tests for row-building logic (no `QApplication` required)

Since `_rows_for_attrib_node`, `_rows_for_detail`, `_rows_for_event`, and `_count_functions` are plain functions over the dataclasses in `pgtp_editor.model.nodes`, they are fully unit-testable without Qt:

- **Page/Column rows:** a synthetic `PageNode`/`ColumnNode` with a small `attrib` dict produces exactly one `RowSpec` per key, each with `target_line == node.sourceline`.
- **Detail rows, the caption/inner_sourceline split:** a synthetic `DetailNode` with `sourceline=10`, `inner_sourceline=25`, and `attrib={"caption": "Sub-item", "tableName": "pr.attachment", "viewAbilityMode": "1"}` produces three rows; asserts the `caption` row's `target_line == 10` and both other rows' `target_line == 25` — the exact empirical rule from §3.1/§3.2, tested directly rather than only asserted in prose.
- **Detail rows, missing `inner_sourceline`:** a synthetic `DetailNode` with `inner_sourceline=None` produces rows whose non-`caption` `target_line` is `None`, exercising the defensive fallback path named in §3.2 (never a crash from a `None` line number reaching the row-building stage itself).
- **Event rows:** a synthetic `EventNode` with `side="C"` produces a `"Side"` row valued `"Client"` (not `"C"`); `side="S"` produces `"Server"`. The `"Functions"` row's value is asserted against `_count_functions` directly on a few real extracted sample bodies (§3.3) — hard-coding the expected counts derived during this document's own grounding work (e.g. the 3579-character real `OnEditFormLoaded` body from `dev_Ferrara.pgtp` is expected to yield a double-digit count, verified as 14 during this design's own grounding pass) — as regression fixtures, not just synthetic strings, so the heuristic's behavior against real, messy handler code is pinned down, not only its behavior against clean hand-written test strings.
- **`_count_functions` heuristic, synthetic edge cases:** `"functionallocation"` (the real false-positive substring found in the sample data) yields `0`; `"function foo() {}"` yields `1`; `"function() {}"` (anonymous) yields `1`; `"function () {}"` (anonymous with a space) yields `1`; a string containing `"const f = (x) => x"` (arrow function) yields `0`, documenting the accepted gap from §3.3 as an explicit, asserted test case rather than an undocumented blind spot.

### 4.2 `pytest-qt` tests for `PropertiesPanel`

Using a lightweight stub in place of the real `XmlEditor` (a small test double exposing `navigate_to_line(line)`, `line_text(line)`, `select_range_on_line(line, start, end)` as recording no-ops — i.e. each call appends its arguments to a list the test can assert against), since the real `XmlEditor` does not exist in this worktree yet (§1):

- **Empty state:** `show_node(None, None)` shows the empty-state message and hides the table (or an equivalent visibility assertion matching whatever container mechanism was implemented per §3.6).
- **Page/Column/Detail/Event population:** `show_node` with each kind of synthetic node produces a table with the expected row count, header text, and cell values (including the Event panel's `"Client"`/`"Server"` display substitution and its `"Functions: N"` row).
- **Click-to-navigate, line-level:** clicking a row calls the stub's `navigate_to_line` with the expected line number for that row (exercising the Detail caption/inner_sourceline split concretely: clicking the `caption` row's cell calls `navigate_to_line(detail_node.sourceline)`; clicking any other Detail row's cell calls `navigate_to_line(detail_node.inner_sourceline)`).
- **Click-to-navigate, column-precise refinement:** clicking an attribute row additionally calls the stub's `line_text` then `select_range_on_line` with the expected `(start, end)` span, using a stub `line_text` return value crafted to contain the target attribute in realistic `key="value"` form.
- **Click-to-navigate, refinement failure mode:** a stub `line_text` return value that does **not** contain the expected `attr_name="` substring — asserts `select_range_on_line` is never called (no exception raised, no further call made), confirming the "fall back to just the line-level highlight, never crash, never silently do nothing" requirement from §3.4 holds at the panel's own call site, independent of what the real `XmlEditor` would eventually do with a call it never receives.
- **Event "Functions" row has no refinement:** clicking the Event panel's "Functions: N" row calls `navigate_to_line` but never `line_text`/`select_range_on_line`, confirming `attr_name=None` correctly short-circuits step (b) of §3.4 for that one row.

### 4.3 What remains blocked until the XML Editor Foundation sub-project is merged

The row-building and table-population logic above (§4.1, §4.2) is fully testable today, independent of the XML Editor Foundation sub-project's status, because the navigation call site is exercised against a stub. **What is not testable until that sub-project is merged into this worktree's lineage:** a true integration test asserting that clicking a Properties panel row actually scrolls a real `XmlEditor` instance to the correct line and visibly selects the correct attribute span within real file text. This is an explicit, stated dependency, not an oversight — §3.4 already designs `navigate_to_line`/`line_text`/`select_range_on_line` as small, targeted additions to that sub-project's `XmlEditor` surface; once that sub-project is merged and extended per this document's decision, a follow-up integration test (loading a real sample file, selecting a Detail node in the tree, clicking its `tableName` row, and asserting the real `XmlEditor`'s cursor/selection state) becomes possible and should be added at that time. This document does not fabricate that test against a stub standing in for correctness it cannot actually verify.

## 5. Summary of decisions from brainstorming

- The Properties panel is strictly **read-only and navigate-only** ("option A" from the original brainstorming: shows everything phpgen lets you set on the selected object, clicking jumps to the XML, never edits a value) — this is restated here as the controlling scope decision for every design choice in this document, not merely as background.
- Row-building is generic/complete for Page, Detail, and Column (one row per `attrib` key, no curated subset), matching the model layer's own "capture everything generically" philosophy rather than hand-picking which properties are "important enough" to show.
- The Detail node's per-row navigation-line split (`caption` → `sourceline`, everything else → `inner_sourceline`) is grounded in an empirical, already-independently-confirmed fact about real `.pgtp` files (the outer `<Detail>` element only ever carries a `caption`) — not a guess, and not something this document treats as needing further hedging beyond the defensive `None`-handling already specified.
- The Event panel's third row, "Functions: N", is computed by a regex-based heuristic (`\bfunction\s*[A-Za-z_$][A-Za-z0-9_$]*\s*\(|\bfunction\s*\(`) designed and verified directly against real `EventHandlers` bodies pulled from this worktree's own `sample/` files — not invented against synthetic examples alone. It is explicitly documented as approximate: it will miss arrow functions entirely and can't distinguish a function token appearing in a string/comment from a real declaration, both accepted as reasonable, stated gaps rather than problems to solve here.
- The XML Editor Foundation sub-project's `highlight_error_line(line)` method (not yet merged into this worktree) is judged too error-specific a name to reuse as-is for a non-error navigation use case. This document's concrete decision: the XML Editor Foundation sub-project should expose a more general `navigate_to_line(line)` (with `highlight_error_line` becoming a thin error-colored wrapper around it), plus two small additional methods this panel also needs, `line_text(line)` and `select_range_on_line(line, start, end)`. These are small, targeted additions to that sub-project's already-approved design, not a rework of it, and are called out explicitly as a follow-up needed when the two sub-projects are reconciled.
- `MODEL_NODE_ROLE` already existed in this worktree's `project_tree.py` (inherited from the earlier Diff/Merge work merged into this worktree's lineage) — confirmed directly rather than assumed, and cross-checked against the `pgtp-editor-diffmerge-writeback` worktree's copy for provenance. What this worktree's `project_tree.py` was missing, and what this document adds, is (a) `MODEL_NODE_ROLE` coverage on Column/Event tree items (previously set only for Page/Detail items) and (b) any `currentItemChanged`/`itemSelectionChanged` wiring at all (previously absent entirely — the only existing tree signal wiring was for right-click context menus).
- The click-to-navigate column-precise refinement is a plain substring search (`f'{attr_name}="'` within the resolved line's own text, selecting through the closing quote) — deliberately not a real XML-aware search, since it only ever needs to operate on one already-resolved line. Its failure mode is a silent, graceful fall-back to the line-level highlight already applied — never a crash, never a no-op with no visible result at all.
- Full end-to-end testing of the navigation call requires the real `XmlEditor`, which does not exist in this worktree yet — the row-building/table-population logic is designed to be fully testable independently of it (Qt-free for row-building, `pytest-qt` against a recording stub for the panel itself), with the true integration test explicitly deferred until the XML Editor Foundation sub-project is merged.
