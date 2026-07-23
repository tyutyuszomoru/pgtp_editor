# PGTP Editor

PGTP Editor is a companion tool for SQL Maestro **PostgreSQL PHP Generator**. It
opens the generator's `.pgtp` project files directly, lets you inspect and edit
them safely, manage captions in bulk, edit event-handler code comfortably, compare
project versions, check the project against a live database, validate structure,
and drive PHP generation — all without fighting the generator's own UI.

The editor never rewrites your file behind your back: every change you make is one
you asked for, and the on-disk bytes are preserved except where you edit.

---

## Getting Started

### Opening a project

Use **File ▸ Open** and pick a `.pgtp` file. The window has three areas:

- **Left — Project Tree:** the structure of your project (pages, details, columns,
  event handlers). More tabs share this dock: **Contents** (this manual's
  chapters), **Table references** (when you turn it on from the View menu), and,
  after you run a database check, **Database Check**.
- **Center — Raw XML / Caption Management / Diff-Merge / Manual:** the working
  area. It opens on **Raw XML**; the other tabs appear when you invoke them.
- **Right — Properties:** a read-only inspector for whatever you select in the tree.

When you open a file, the status bar shows a live message such as
`Opening dev_Ferrara.pgtp (312 KB)…` and the pointer becomes a wait cursor
(hourglass) until the project is loaded; it then settles on `Opened: <path>`.
The same busy feedback appears during other slow operations — see *A note on
busy feedback*.

### Saving, closing, reverting

- **File ▸ Save** (Ctrl+S) writes back to the same file.
- **File ▸ Save As** (Ctrl+Shift+S) writes a copy to a new path.
- **File ▸ Close** (Ctrl+W) closes the project; if you have unsaved changes it
  prompts you to **Save**, **Discard**, or **Cancel**.
- **File ▸ Revert** discards your edits and reloads the last saved version from the
  automatic `.bak` backup written on save.

The editor writes UTF-8 and preserves your original line endings — it does not
convert line endings or re-encode content on save.

---

## The Project Tree

The tree mirrors your project: **Pages** contain **Columns**, **Details**, and
**Event Handlers**. **View ▸ Expand All** and **Collapse All** open or fold the
whole tree at once.

- **Single-click** a node to load its **Properties** on the right.
- **Double-click** a node to **jump to it in the Raw XML editor**.

Right-click a node for actions specific to its type:

**Page**
- **Jump to page XML** — place the cursor on the page's opening tag.
- **Select page XML** — select the whole page block.
- **See database table in Caption Mode** — open Caption Management filtered to that
  table's captions.
- **Add Event Handler ▸** — a submenu of every known handler; handlers the page
  already has are greyed out. Choosing one opens the Code Editor on an empty body
  and inserts it wrapped in the correct XML when you save.

**Detail**
- **Jump / Select** the detail block.
- **See database table's Details in Caption Mode.**

**Column**
- **Jump to column visibility** and **Jump to column presentation** — go straight
  to those parts of the column's XML.
- **See column in Caption Mode.**

**Event handler**
- **Edit code…** — open the handler body in the Code Editor.

After hand-editing the Raw XML, **Tools ▸ Reparse Raw XML into Tree** rebuilds the
tree from the current editor text.

---

## Properties

The Properties panel shows the attributes of the selected node. It is a
**read-only inspector** — it never writes to your file, so you can explore freely.
Edit values in the Raw XML editor or the specialized panels.

When you select a **Column**, Properties also shows its **visibility across the
fixed representation lists**: List, View, Edit, Insert, QuickFilter, FilterBuilder,
Print, Export, Compare, and MultiEdit. Each is shown as visible or hidden
(`visible="false"`), so you can tell at a glance where a column appears.

---

## The Raw XML Editor

The **Raw XML** tab is a full text editor over the project file.

- The **current line** is highlighted, and when the cursor is on a tag its
  **matching tag** is highlighted too.
- **Folding:** a chevron in the gutter marks every multi-line element. Click it to
  collapse or expand that block.
- **Bookmarks:** click the narrow strip at the left edge of the gutter to set a
  bookmark on a line (see *Bookmarks*).
- **Event-handler code regions** are shown with a distinct, subdued background and a
  monospace band, so JS/PHP bodies stand out from the surrounding XML. Right-click
  inside a body for **Edit code…** (see *The Code Editor*).
- Right-click a selection for **Find** to search for the selected text.
- Right-click ▸ **Wrap Lines** toggles soft line-wrapping.

### Undo, Redo & History

The editor keeps a rolling history of up to ten XML snapshots.

- **Ctrl+Z** undoes and **Ctrl+Y** redoes a step.
- **Edit ▸ History…** opens a jump list of the recent snapshots so you can jump
  straight back to an earlier state. (Snapshots taken when a file is opened or
  reverted are baselines and are not offered as undo targets.)

### Schema-aware editing

PGTP Editor learns the structure of `.pgtp` files from the projects you open and
uses that knowledge to help you edit (see *Schema Tools*).

- **Ctrl+Space** inside an opening tag lists the attributes the schema knows for
  that element; use the arrow keys and **Tab** (or Enter) to insert the chosen one
  as `name=""`. When the attribute has known values, a second list appears so you
  can pick the value too. Type to narrow the list; **Esc** dismisses it.
- **Right-click ▸ Add attribute ▸** lists the *settings* attributes the schema
  knows for the current element that it doesn't already have — a quick way to add a
  recognized setting.
- **Hovering** an attribute value whose meaning has been labelled shows a tooltip
  spelling it out, e.g. `editFormMode — 1 = modal · 2 = new page · 3 = inline`.
- **Ctrl+click** a tag to jump to its matching open/close tag; **Alt+click** to
  jump to the parent element's opening tag. The caret moves and scrolls into
  view; nothing is selected.

---

## Bookmarks

Bookmarks let you mark lines in the Raw XML editor and jump between them. They live
for the current session and are not written to the file.

- **Ctrl+F2** (or clicking the bookmark strip in the gutter) toggles a bookmark on
  the current line; a tag marker appears in the strip.
- **F2** / **Shift+F2** jump to the next / previous bookmark.
- The **Bookmarks** menu holds the same actions plus **Clear All Bookmarks**.

---

## Find, Replace & Find All

The search bar under the Raw XML editor provides:

- **Find** (Ctrl+F) / **Find Next** (F3) for incremental search.
- **Find All** (Ctrl+Shift+F) — lists every match. Results stream in
  **continuously** so a large file stays responsive; a **Stop** button cancels a
  long search, and the status bar reports **"Found N items."**
- **Replace** (Ctrl+R) and **Replace All** (Ctrl+Alt+Enter) — Replace All reports
  how many replacements it made in the status bar.

---

## The Code Editor

PHP Generator's event-handler code is notoriously hard to reach and edit. PGTP
Editor gives it a proper editor — for both **editing existing** handlers and
**inserting new** ones.

### Opening the Code Editor

- From the **Raw XML editor**: put the cursor inside a handler body and choose
  **Edit code…** from the right-click menu (or the affordance shown for code
  regions).
- From the **Project Tree**: right-click an event-handler node ▸ **Edit code…**.

### Editing

The Code Editor is a modal window with:

- **Syntax highlighting** — JavaScript for client-side handlers, PHP for
  server-side handlers.
- **Auto-close** for `()`, `[]`, `{}`, `''`, and `""` — the caret lands between the
  pair, and typing the matching closer "types through" it.
- **Selection-wrap** — with text selected, typing a bracket or quote wraps the
  selection instead of replacing it.
- **Ctrl+Shift+B** — select the enclosing bracket span.
- Standard **Ctrl+C / Ctrl+V / Ctrl+X**.
- **Ctrl+S** saves and closes; **Ctrl+W** cancels.

On save, the code is written back into the handler's XML body (properly escaped),
preserving the rest of the file byte-for-byte.

### Adding a new handler

From a **Page**'s right-click **Add Event Handler ▸** submenu, pick a handler. The
list distinguishes **client-side** handlers (JavaScript, run in the browser) from
**server-side** handlers (PHP, run on the server). Handlers the page already has are
greyed out. Choosing one opens an empty Code Editor; saving inserts a new
`<EventHandlers>` / `<OnXxx enabled="true">` block in the right place.

---

## Caption Management

Caption Management is a dedicated mode for reviewing and editing the visible text
(captions, labels, hints) across your whole project at once.

### Entering and leaving

Enter from the toolbar/menu or from a tree node's **See … in Caption Mode** action.
While in the mode, the **Raw XML** tab stays visible but **read-only**, and a status
indicator shows you're in Caption Mode. Leave the mode with the **Exit** control to
re-enable editing.

### The grid

Each caption is one row with these columns:

- **Changed** — a marker (`*`) on rows you have edited.
- **Line** — the source line in the XML.
- **Breadcrumb** — where the caption lives (page ▸ detail ▸ field).
- **Element**, **Anchor**, **Attribute** — what the caption is attached to.
- **Value** — the current caption. `<NULL>` means an empty caption.
- **New Value** — your edit. Editing here is **non-destructive**: nothing is written
  until you apply, and the original **Value** stays visible for comparison.

Edited rows are colored and marked in **Changed**. Rows with inconsistent values
across the project are highlighted so you can unify them.

### Navigating and editing

- **Ctrl+G** (Go to line) jumps from the selected row to that line in the Raw XML
  editor.
- **Copy / Paste** work across rows, including multi-line selections, so you can move
  values between rows or in and out of a spreadsheet.

### Filtering

- **Header filters** — click a column header to filter by its values, Excel-style.
  A **search box** narrows the checkbox list as you type and unchecks values that no
  longer match, so you can zero in on a large set quickly.
- **Clear all filters** — available from the right-click menu.

### Find / Filter / Replace

A shared modal drives searching and bulk editing:

- **Mode:** **String** (literal), **Extended** (escapes like `\n`), or **Regex**.
- **Match case** toggle.
- **Scope:** **In selection** or **Global**.
- **Find / Filter** narrows the grid; **Replace** applies to the matched set.

### Power tools

- **Bulk Transform** — apply a transformation across many captions at once.
- **Unify** — make inconsistent captions consistent.

---

## Schema Tools

The **Schema** menu exposes the learned model of the `.pgtp` format — the same
knowledge that drives Ctrl+Space completion, the *Add attribute* menu, and value
hovers in the Raw XML editor.

- **Annotate Schema Values…** — review the attributes the engine has seen and mark
  each as a **setting** (a fixed option, e.g. an ability mode) or **content**
  (file-specific data). For settings with a small set of values you can **label**
  each value (for example `1 = modal`, `2 = new page`). Those labels are what
  appear in editor hovers and in the Ctrl+Space value picker.
- **Open XSD** — view the XSD generated from the learned model (read-only).
- **Open XSD Labels (JSON)** — view the labels store behind the annotations
  (read-only).

---

## Database Check

The **Database** menu compares the tables and columns your project references
against a live PostgreSQL database.

### Connecting

**Connection Setup…** collects server, port, database, user, and password, with a
**Test** button. The non-password fields are seeded from the project's
`<ConnectionOptions>`; a connection you save is remembered and takes precedence over
the project's values next time.

> On Windows, use **`127.0.0.1`** rather than `localhost` — `localhost` can resolve
> to IPv6 first and stall the connection. The check runs off the UI thread with a
> timeout, so an unreachable server reports an error instead of freezing the app.

### Checking

- **Check: XML → Database** verifies every table and column the project references
  actually exists in the database. Results appear in the **Database Check** tab in
  the left dock as a tree with green/red ticks. Each table shows its kind —
  `(T)` table, `(V)` view, `(M)` materialized view — and how many times the project
  references it `(×N)`; each column shows its datatype, primary keys are underlined,
  foreign keys are marked `(fk)`, and nullability/defaults are noted. A
  **show-only-mismatches** toggle and a count help you focus. **Double-click** a
  result to jump to its place in the XML. If a table isn't found, you can rename it
  (a project-wide replace) and re-run the check.
- **Check: Database → XML** is the reverse: it lists tables and columns that exist
  in the database but the project doesn't reference.

The password is stored with the connection settings and is never written to any log.

---

## Table References

**View ▸ Find table reference** is a checkable toggle that opens the **Table
references** tab in the left dock. It lists every database table and view your
project references, grouped so you can see where a change to one table's
presentation may need mirroring elsewhere.

- Each **top-level row** is a table/view name with a usage count, e.g.
  `kb.x_objecttype  (3)`.
- Each **child row** is one reference, shown as a breadcrumb of where it lives
  (page ▸ detail ▸ column). Lookup references are labelled **(lookup)**, or
  **(lookup with insert)** when the lookup also has an on-the-fly insert page.

- **Single-click** a reference to load its node in the **Properties** panel — a
  lookup reference selects its owning column.
- **Double-click** a reference to **jump to it in the Raw XML editor**: a lookup
  jumps to its `<Lookup>` line, while a page or detail reference jumps to its own
  opening tag. This makes the tab a second way to scroll through the XML,
  alongside the Project Tree.

Turn the toggle off to hide the tab. The list needs an open project (otherwise a
status-bar message asks you to open one first), and it refreshes to match your
edits after **Tools ▸ Reparse Raw XML into Tree** while the tab is showing.

---

## Diff / Merge

**Diff / Merge** (under **Tools ▸ Compare / Merge Two Files…**) compares two
`.pgtp` files side by side so you can see what changed between versions and
reconcile them. **Next Difference** / **Prev Difference** step through the changes,
and **Apply Changes to Target** writes the reconciled result.

---

## Validation

**Tools ▸ Validate Project** checks your project for structural problems and
reports them as a list of issues with severities (errors and warnings) — for
example duplicate top-level page file names, missing expected attributes, or
unexpected children in container elements. Select an issue to jump to it; clearing
validation removes the results.

---

## Generating PHP

The **Generation** menu drives the PHP Generator command-line to compile your
`.pgtp` into PHP:

1. **Locate PHP Generator Executable…** once (the path is stored for future use).
2. **Generate PHP…** — if the project has unsaved changes, you're prompted to
   **Save** or **Save As** first, so the generator always runs against the file on
   disk.
3. **Open Output Folder** opens the generated output in your file browser.

---

## A note on busy feedback

Some operations take a moment on a large project. While one runs, PGTP Editor
shows a wait cursor (hourglass) and a live status-bar message so you can tell it
is working rather than frozen:

- **Opening a file:** `Opening <name> (<size>)…`, e.g. `Opening dev_Ferrara.pgtp (312 KB)…`.
- **Tools ▸ Validate Project:** `Validating <name>…`.
- **Tools ▸ Reparse Raw XML into Tree:** `Reparsing…`.
- **Generation ▸ Generate PHP…:** `Generating PHP…`.

This is purely a visual cue. The window is still unresponsive to input for the
duration of the operation — there is no progress bar and nothing to cancel — it
simply reads as busy instead of stalled.

---

## Appearance & Layout

- **View ▸ Light Theme** toggles between the light and dark themes.
- The **View** menu toggles each panel: **Project Tree**, **Properties Panel**,
  **Audit/Problems Panel**, and **Raw XML Panel**. **View ▸ Find table reference**
  toggles the **Table references** tab (see *Table References*).
- **View ▸ Customize Toolbar…** chooses which actions appear on the icon toolbar.
- Your window size and position, dock layout, theme, and toolbar arrangement are
  remembered between sessions.

---

## Keyboard Shortcuts

| Shortcut | Where | Action |
|----------|-------|--------|
| **Ctrl+O** | Global | Open a `.pgtp` file |
| **Ctrl+S** | Global | Save |
| **Ctrl+Shift+S** | Global | Save As |
| **Ctrl+W** | Global | Close project |
| **F1** | Global | Open the Manual |
| **Ctrl+F2** | Raw XML | Toggle bookmark |
| **F2** / **Shift+F2** | Raw XML | Next / previous bookmark |
| **Ctrl+Z** / **Ctrl+Y** | Raw XML | Undo / redo (snapshot history) |
| **Ctrl+Space** | Raw XML | Attribute / value completion |
| **Ctrl+click** | Raw XML (mouse) | Jump to matching open/close tag |
| **Alt+click** | Raw XML (mouse) | Jump to parent tag start |
| **Ctrl+Shift+B** | Raw XML / Code Editor | Select enclosing block (caret to start) |
| **Ctrl+Shift+A** | Raw XML | Select parent block |
| **Ctrl+F** | Raw XML | Find |
| **F3** | Raw XML | Find next |
| **Ctrl+Shift+F** | Raw XML | Find all |
| **Ctrl+R** | Raw XML | Replace |
| **Ctrl+Alt+Enter** | Raw XML | Replace all |
| **Ctrl+F** | Caption Mode | Open Find/Filter |
| **Ctrl+R** | Caption Mode | Open Replace |
| **Ctrl+G** | Caption Mode | Go to line in Raw XML |
| **Ctrl+S** | Code Editor | Save code and close |
| **Ctrl+W** | Code Editor | Cancel |
| **Ctrl+C / Ctrl+V / Ctrl+X** | Editors | Copy / Paste / Cut |

In Caption Mode, **Ctrl+F** and **Ctrl+R** are rebound to the caption
Find/Filter/Replace tools for as long as the mode is active; they return to the Raw
XML editor's Find/Replace when you leave the mode.

---

## The Manual

You're reading it. Open it any time with **F1** or **Help ▸ Manual**.

- The manual renders in the center **Manual** tab.
- The **Contents** tab in the left dock lists every chapter. Click a chapter to
  scroll the manual straight to it.

---

## Troubleshooting: debug mode

Launch the editor with `python -m pgtp_editor.main --debug` (or set the
environment variable `PGTP_EDITOR_DEBUG=1`) to record a full diagnostic log
of the session. A red **DEBUG** badge appears in the status bar and the log
file path is shown at startup. Even without debug mode, errors are always
recorded to a small `errors.log`. **Help ▸ Open Log Folder** opens the folder
containing both logs — attach the newest `debug_*.log` when reporting a
problem.
