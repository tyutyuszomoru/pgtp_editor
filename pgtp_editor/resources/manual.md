# PGTP Editor

PGTP Editor is a companion tool for SQL Maestro **PostgreSQL PHP Generator**. It
opens the generator's `.pgtp` project files directly, lets you inspect and edit
them safely, manage captions in bulk, edit event-handler code comfortably, compare
project versions, validate structure, and drive PHP generation — all without
fighting the generator's own UI.

The editor never rewrites your file behind your back: every change you make is one
you asked for, and the on-disk bytes are preserved except where you edit.

---

## Getting Started

### Opening a project

Use **File ▸ Open** and pick a `.pgtp` file. The window has three areas:

- **Left — Project Tree:** the structure of your project (pages, details, columns,
  event handlers). A second tab, **Contents**, holds this manual's chapters.
- **Center — Raw XML / Caption Management / Diff-Merge / Manual:** the working
  area. It opens on **Raw XML**; the other tabs appear when you invoke them.
- **Right — Properties:** a read-only inspector for whatever you select in the tree.

### Saving

- **File ▸ Save** writes back to the same file.
- **File ▸ Save As** writes a copy to a new path.

The editor writes UTF-8 and preserves your original line endings — it does not
convert line endings or re-encode content on save.

---

## The Project Tree

The tree mirrors your project: **Pages** contain **Columns**, **Details**, and
**Event Handlers**.

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
- **Ctrl+Shift+B** selects the block enclosing the cursor and moves the cursor to
  the **start** of the selection, so you can immediately see where the block begins.
- **Event-handler code regions** are shown with a distinct, subdued background and a
  monospace band, so JS/PHP bodies stand out from the surrounding XML. Right-click
  inside a body for **Edit code…** (see *The Code Editor*).
- Right-click a selection for **Find** to search for the selected text.

---

## Find, Replace & Find All

The search bar under the Raw XML editor provides:

- **Find** / **Find next** for incremental search.
- **Find All** — lists every match. Results stream in **continuously** so a large
  file stays responsive; a **Stop** button cancels a long search, and the status bar
  reports **"Found N items."**
- **Replace** and **Replace All** — Replace All reports how many replacements it
  made in the status bar.

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

## Diff / Merge

**Diff / Merge** compares two `.pgtp` files side by side so you can see what changed
between versions and reconcile them. Open it from the menu, choose the two files,
and review the differences.

---

## Validation

Validation checks your project for structural problems and reports them as a list of
issues with severities (errors and warnings) — for example duplicate top-level page
file names, missing expected attributes, or unexpected children in container
elements. Select an issue to jump to it. Clearing validation removes the results.

---

## Generating PHP

PGTP Editor can drive the PHP Generator command-line to compile your `.pgtp` into
PHP:

1. Set the generator path once (stored for future use).
2. Choose **Generate**. If the project has unsaved changes, you're prompted to
   **Save** or **Save As** first, so the generator always runs against the file on
   disk.

---

## Keyboard Shortcuts

| Shortcut | Where | Action |
|----------|-------|--------|
| **Ctrl+O** | Global | Open a `.pgtp` file |
| **Ctrl+S** | Global | Save |
| **F1** | Global | Open the Manual |
| **Ctrl+Shift+B** | Raw XML / Code Editor | Select enclosing block (caret to start) |
| **Ctrl+F** | Raw XML | Find |
| **Ctrl+R** | Raw XML | Replace |
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
