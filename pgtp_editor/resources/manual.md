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
  chapters), **Table references** (when you turn it on from the View menu),
  **Database Check** (after you run a database check), and **DDL Objects** (while
  the DDL Explorer is on — see *DDL Explorer*).
- **Center — Raw XML / Caption Management / Diff-Merge / Edit XSD / DDL Explorer /
  Manual:** the working area. It opens on **Raw XML**; the other tabs appear when
  you invoke them.
- **Right — Properties:** a read-only inspector for whatever you select in the tree.

When you open a file, the status bar shows a live message such as
`Opening dev_Ferrara.pgtp (312 KB)…` and the pointer becomes a wait cursor
(hourglass) until the project is loaded; it then settles on `Opened: <path>`.
The same busy feedback appears during other slow operations — see *A note on
busy feedback*.

### Saving, closing, reverting

- **File ▸ Save** (Ctrl+S) saves the **active tab**: the project file when you're
  in Raw XML (or any project view), or the schema the XSD tab currently holds —
  curated or auto — when that tab is active (see *Schema Tools*).
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

When a value's meaning is labelled in the curated schema (see *Schema Tools*),
Properties shows the label next to the value — for example `phpDriver: 1 — php-psql`
instead of a bare `1`.

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

PGTP Editor's editing help is driven by a hand-curated XSD schema — the file
`curated.xsd` in the app's data folder (see *Schema Tools* for how to maintain
it).

- **Ctrl+Space** inside an opening tag lists the attributes the schema knows for
  that element; use the arrow keys and **Tab** (or Enter) to insert the chosen one
  as `name=""`. When the attribute has enumerated values in the schema, a second
  list appears so you can pick the value too — each row shows `value = label` when
  the enumeration is labelled, including labels derived for bit-flag sums. An
  attribute with no enumerations completes by name only. Type to narrow the list;
  **Esc** dismisses it.
- **Right-click ▸ Add attribute ▸** lists the attributes the schema knows for the
  current element that it doesn't already have — a quick way to add a recognized
  setting.
- **Hovering** an attribute name or value shows a tooltip spelling out its
  meaning, e.g. `editFormMode — 1 = modal · 2 = new page · 3 = inline`, or the
  attribute's free-form hint text when it has one.
- **Ctrl+L** (or right-click ▸ **Go To XSD**) jumps from the attribute under the
  cursor to its definition in the **Edit XSD** tab (see *Schema Tools*).
- **Ctrl+click** a tag to jump to its matching open/close tag; **Alt+click** to
  jump to the parent element's opening tag. The caret moves and scrolls into
  view; nothing is selected.

---

## Bookmarks

Bookmarks let you mark lines and jump between them. They live for the current
session and are not written to the file.

- **Ctrl+F2** (or clicking the bookmark strip in the gutter) toggles a bookmark on
  the current line; a tag marker appears in the strip.
- **F2** / **Shift+F2** jump to the next / previous bookmark.
- The **Bookmarks** menu holds the same actions plus **Clear All Bookmarks**.

The **Bookmarks** menu and its shortcuts follow the tab you are working in: with
the **Edit XSD** (or **Edit AutoXSD**) tab active they act on the schema editor,
with the **DDL Explorer** tab active they act on its editor, and on any other tab
they act on the **Raw XML** editor. Using them never switches tabs on you — a
bookmark is always set or found in the editor you are already looking at.

The **Edit code…** dialog has the same bookmark strip, but as a separate dialog
it is out of the Bookmarks menu's reach: there you set and clear bookmarks by
clicking the strip in the gutter. Each editor keeps its own set, and loading a
new document into an editor clears its bookmarks.

---

## Find, Replace & Find All

The search bar under the Raw XML editor provides:

- **Find** (Ctrl+F) / **Find Next** (F3) for incremental search.
- **Find All** (Ctrl+Shift+F) — lists every match. Results stream in
  **continuously** so a large file stays responsive; a **Stop** button cancels a
  long search, and the status bar reports **"Found N items."**
- **Replace** (Ctrl+R) and **Replace All** (Ctrl+Alt+Enter) — Replace All reports
  how many replacements it made in the status bar.

The **Edit XSD** tab (see *Schema Tools*) and the **DDL Explorer** tab (see *DDL
Explorer*) each have their own search bar; the shortcuts and the Edit menu act on
whichever tab is active, searching that tab's own document. On a tab without its
own search bar, Find reveals the **Raw XML** tab and searches there.

Because the DDL Explorer buffer is **read-only**, only the searching half applies
there: Find, Find Next and Find All work as usual, while Replace and Replace All
have nothing they can change.

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
- A **line-number gutter**, with a bookmark strip at its left edge: click it to
  mark a line while you work through a long handler (see *Bookmarks*). There is
  nothing to fold in a code body, so the gutter shows no fold chevrons here.
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

PGTP Editor's knowledge of the `.pgtp` format lives in one hand-edited file:
**`curated.xsd`** in the app's data folder. It is the **official schema** and the
*only* source feeding Ctrl+Space completion, the *Add attribute* menu, hover
hints, and the value labels in the Properties panel. You maintain it yourself
through the **Schema** menu, which has exactly five entries: **Edit XSD**,
**Edit AutoXSD**, **Verify XSD**, **Export XSD**, and **Import XSD**.

Alongside it, the editor still **auto-learns** from every project you open:
**File ▸ Open** scans the file and writes what it finds to a separate reference
file, `learned.xsd`, announcing discoveries with `[Schema]` lines in the Audit
panel (`NEW ELEMENT`, `NEW ATTRIBUTE`, `NEW ATTR VALUE`, …). Learned data **never
appears in completion** — when something new looks worth keeping, open it with
**Schema ▸ Edit AutoXSD** (see *Comparing against the auto-learned schema*),
find it, and add it to `curated.xsd` by hand.

On first run, when you don't yet have a `curated.xsd`, the app **seeds** it by
copying the curated schema bundled with the editor (**Curated v1.2**, a real
hand-commented starting schema). The seed happens only when the file is absent —
`curated.xsd` is hand-owned, so the app never overwrites your edits behind your
back. (If the bundled schema isn't packaged for some reason, the app falls back
to generating a starter schema from your learned data, preserving any value
labels.)

### The XSD dialect

`curated.xsd` is plain XSD plus three small extensions of ours:

- **`label="…"` on `<xs:enumeration>`** — the value's display meaning, e.g.
  `<xs:enumeration value="1" label="php-psql"/>`. Completion shows the row as
  `value = label`; hover and Properties show the label too.
- **`sums="true"` on `<xs:attribute>`** — for bit-flag attributes whose values
  add up (3 = 1+2). Label only the atomic values (1, 2, 4, 8, …); every
  combination completes with a derived label automatically — with 1 = `A` and
  4 = `C`, the value 5 shows as `A+C`. An explicit enumeration row for a
  composite value overrides its derived label.
- **`hint="…"` on `<xs:attribute>`** — for free-form attributes with a meaning
  worth describing but no fixed value set: no enumerations, hover shows the hint,
  and completion offers no value list.

Curation is ordinary editing: **delete an enumeration row** to remove a junk
value from completion; an attribute with no enumerations at all completes by
name only.

### Editing the schema (the Edit XSD tab)

**Schema ▸ Edit XSD** opens `curated.xsd` in a dedicated editor tab in the
center area — a full editor with its own find/replace bar (Find, Find All,
Replace, all the usual shortcuts). The tab keeps its own unsaved-changes marker
(`Edit XSD *`), and **Ctrl+S saves whichever tab is active** — the project from
Raw XML, the schema from the XSD tab.

Click the tab's **✕** to close it and return to Raw XML. With no unsaved edits
it closes right away; with unsaved edits it prompts you to **Save**,
**Discard**, or **Cancel** first — the same prompt used when switching between
Edit XSD and Edit AutoXSD (below) or closing the app with unsaved schema edits.

Saving the curated schema re-parses it and refreshes completion, hovers, and
Properties labels **immediately**. If the XML is malformed, your text is still
written to disk (nothing you typed is lost), the last good schema stays in
effect, and a `[Schema]` line in the Audit panel reports the parse error.

### Comparing against the auto-learned schema (Edit AutoXSD)

**Schema ▸ Edit AutoXSD** opens the auto-learned discovery schema
(`learned.xsd`) in the **same** center-stage editor tab. The tab title changes
to **Edit AutoXSD** so you can always tell which schema you're looking at, and it
keeps its own unsaved marker (`Edit AutoXSD *`). This lets you analyse and
compare what auto-learning has discovered against your curated schema, so you can
decide what's worth hand-adding to `curated.xsd`.

**Save, Verify, Export, and Import all act on the schema the tab currently
holds** — the curated schema or the auto schema, whichever is open. Saving the
auto schema writes `learned.xsd` but does **not** re-feed completion (the
auto-learned schema never feeds completion); only saving the curated schema
refreshes completion.

Switching between **Edit XSD** and **Edit AutoXSD** while you have unsaved edits
prompts you to **Save**, **Discard**, or **Cancel** first. Re-opening the same
schema keeps your unsaved edits and just reveals the tab. **Go To XSD**
(Ctrl+L, below) always switches to the curated schema, whichever schema was
last open.

### Go To XSD

To see (or fix) the schema behind an attribute you're looking at, put the cursor
on it in the Raw XML editor and press **Ctrl+L**, or right-click ▸ **Go To XSD**.
This always opens the **curated** schema (the **Edit XSD** tab, switching away
from Edit AutoXSD if that was open) with that attribute's
`<xs:attribute name="…">` definition
selected; if the attribute isn't defined there yet, it falls back to the
enclosing element's type definition, and otherwise tells you in the status bar.

### Verifying

**Schema ▸ Verify XSD** checks the schema against the dialect rules — duplicate
enumeration values, `label` in the wrong place, `sums` on the wrong element,
unknown base types, unresolvable type references, and the like. Each finding is a
clickable `[Schema] VERIFY` line in the Audit panel that opens the XSD tab
at the offending line. It checks **whichever schema the tab currently holds** —
curated or auto. Verification also runs automatically (report-only) every time
you save the tab. When the tab has unsaved edits, Verify checks the tab's live
text; otherwise it checks the active schema's saved file.

### Sharing the schema

Team sharing is plain file exchange. Both actions target **whichever schema the
XSD tab currently holds** — the curated schema, or the auto schema when the tab
is in **Edit AutoXSD**.

- **Schema ▸ Export XSD** — Save-As a copy of the active schema to give to a
  teammate. (If the tab has unsaved changes, save it first.)
- **Schema ▸ Import XSD** — replace the active schema with a file you received.
  The incoming file is **verified first**: malformed XML is refused outright, and
  dialect warnings are shown so you can decide whether to import anyway. Your
  current schema is backed up alongside it (e.g. `curated.xsd.bak`) and the file
  is replaced. When you imported the curated schema, it is re-parsed and
  completion refreshes immediately; importing the auto schema does not touch
  completion. If the tab had unsaved edits, they are replaced by the imported
  text and the Audit panel says so.

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
  the left dock as a tree: a green **✓** marks a match and a red **✗** a mismatch.
  Each table shows its kind — `(T)` table, `(V)` view, `(M)` materialized view — and
  how many times the project references it `(×N)`; each column shows its datatype,
  primary keys are underlined, foreign keys are marked `(fk)`, and
  nullability/defaults are noted. **Calculated columns** (marked
  `isCalculated="true"` in the XML) are generator-computed and have no physical
  database column by design, so they are shown with an orange **~** instead of a red
  ✗ — they don't count as mismatches. A **Show only mismatches** checkbox and a
  mismatch count in the header help you focus; calculated columns are excluded from
  both (the filter hides them entirely). **Double-click** a result — including a
  calculated column — to jump to its place in the XML. If a table or column isn't
  found, right-click it for **Rename table/column in XML…** (a project-wide
  replace) and re-run the check; the action isn't offered for calculated columns,
  since there is nothing database-side to reconcile.
- **Check: Database → XML** is the reverse: it lists tables and columns that exist
  in the database but the project doesn't reference.

Results are tied to the project they were checked against: **File ▸ Close** closes
the **Database Check** tab and discards its results (cancelling the close, or
**File ▸ Revert**, leaves them in place). Running a check on the next project
brings the tab back as usual.

The password is stored with the connection settings and is never written to any log.

### Creating pages, details, and lookups from a table

After a **Check: Database → XML** run, **right-click a table or view row** (not a
column row) in the results tree to synthesize project XML from that table's live
schema:

- **Create new page from this table** builds a complete `<Page>` — column
  presentations, captions, and view/edit types derived from the database column
  types — and inserts it into the Raw XML buffer just before `</Pages>`, then
  switches to the Raw XML tab with the new page selected. If the project already
  has a page for that table (or a page with the same `fileName`), a confirmation
  asks whether to create another one anyway with a de-duplicated `fileName`.
- **Create new detail from this table…** builds a `<Detail>` fragment (a nested
  page plus a master/foreign-key column map, filled in automatically when the
  table has exactly one foreign key, otherwise left as empty placeholders) and
  **copies it to the clipboard** — paste it into the `<Details>` block of the
  target page.
- **Create new lookup from this table…** builds a `<Lookup>` element (link field
  = the table's single primary key; display field = the first text-like non-key
  column, best effort) and **copies it to the clipboard** — paste it into the
  target column.

These actions are offered only in the **Database → XML** direction, because they
need the schema captured by the last check; if that schema is no longer available,
the status bar asks you to run a Database check first.

---

## DDL Explorer

**Database ▸ DDL Explorer** is a checkable toggle that shows your database's
server-side code — every function, procedure, and trigger — inside the editor.
It needs only a database connection: you can use it with **no `.pgtp` file open
at all**. If no connection is configured yet, **Connection Setup…** opens
automatically; save a connection, then toggle the explorer again.

Turning it on fetches all routines and triggers from the connected PostgreSQL
database and reveals two tabs at once:

- **Center — DDL Explorer:** every definition in a single **read-only**,
  SQL-highlighted buffer. Each object is preceded by a banner comment (e.g.
  `-- FUNCTION public.foo(integer) --`) so you can always tell where you are.
  The buffer is a live snapshot of the database and cannot be edited.
- **Left dock — DDL Objects:** a tree of the same objects, grouped from two
  angles. Under **Tables**, each table lists the triggers defined on it; under
  **Functions & Procedures**, each function or procedure lists the triggers that
  call it. A trigger therefore appears in **both** places — either entry points
  at the same definition. **Click** any object to jump the DDL Explorer buffer
  straight to it.

### Reading the DDL Objects tree

Routines under **Functions & Procedures** are listed by their fully-qualified
`schema.name`, followed by a marker telling you what kind of routine it is:

- **`[F]`** — a plain function.
- **`[P]`** — a procedure.
- **`[T]`** — a trigger function, i.e. a function that returns `trigger`.

A routine's **input arguments are listed as child rows**, one per argument, in
the form `name (type)`. A routine that takes no arguments carries an empty pair
of parentheses on its own row instead — for example
`public.dont_delete_standards() [T]`. Argument rows are labels only: clicking
one doesn't navigate anywhere.

Triggers are shown by their composite name `schema.table.triggername`, followed
by bracketed indicators — the timing first, then one per event:

- Timing: **`[B]`** before, **`[A]`** after, **`[I]`** instead of.
- Events: **`[I]`** insert, **`[U]`** update, **`[D]`** delete, **`[T]`** truncate.

So a BEFORE DELETE trigger reads `[B][D]`, and an AFTER INSERT OR UPDATE trigger
reads `[A][I][U]`. The label is identical in both branches of the tree, so you
recognize the same trigger whether you found it under its table or under the
function it calls.

### Working in the DDL tab

The DDL Explorer buffer is read-only, but it is a real editor view with the same
navigation comforts as the Raw XML editor:

- **Line numbers** in the gutter.
- **Folding per DDL object:** a chevron on each object's banner comment line
  collapses that object's body away, leaving the banner visible — handy for
  skimming a long database's worth of definitions.
- **Bookmarks:** click the bookmark strip at the left edge of the gutter to mark
  a line, or use **Ctrl+F2** / **F2** / **Shift+F2** and the **Bookmarks** menu —
  while this tab is active they act on its editor (see *Bookmarks*).
- **Find:** this tab has its own search bar, so **Ctrl+F**, **F3** and
  **Ctrl+Shift+F** search the DDL buffer itself instead of bouncing you to Raw
  XML. Replace (**Ctrl+R**, **Ctrl+Alt+Enter**) is inert here, since the buffer
  is read-only.

Clicking an object in the DDL Objects tree scrolls it to the **top** of the DDL
Explorer tab, so the whole definition is visible below its banner. (The Raw XML
editor centers its jump targets instead.) Tab indentation in this tab is shown
4 characters wide, which keeps `pg_get_functiondef`'s tab-indented bodies
readable.

Close the explorer with the **✕** on the DDL Explorer tab or by unchecking
**Database ▸ DDL Explorer** — both hide the two tabs together, and the menu
checkbox always reflects whether the explorer is currently visible. The status
bar reports how many routines and triggers were loaded; if the fetch fails, it
shows the error and the toggle unchecks itself.

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

- **View ▸ Light Theme** is a checkable toggle between the editor's two themes:
  checked applies the light theme, unchecked applies the dark theme. Both are the
  editor's own color schemes and look the same on every platform — the app does
  not follow your operating system's light/dark setting. Toolbar icons re-tint to
  stay legible in either theme, and your choice is remembered across restarts.
- The **View** menu toggles each panel: **Project Tree**, **Properties Panel**,
  **Audit/Problems Panel**, and **Raw XML Panel**. Each checkbox always reflects
  whether its panel is currently visible — closing a panel with the ✕ on its own
  title bar unchecks the menu entry too, and re-checking it brings the panel
  back. **View ▸ Find table reference** toggles the **Table references** tab
  (see *Table References*).
- **View ▸ Customize Toolbar…** chooses which actions appear on the icon toolbar.
- Your window size and position, dock layout, theme, and toolbar arrangement are
  remembered between sessions.

---

## Keyboard Shortcuts

| Shortcut | Where | Action |
|----------|-------|--------|
| **Ctrl+O** | Global | Open a `.pgtp` file |
| **Ctrl+S** | Global | Save the active tab (project, or the open schema from the XSD tab) |
| **Ctrl+Shift+S** | Global | Save As |
| **Ctrl+W** | Global | Close project |
| **F1** | Global | Open the Manual |
| **Ctrl+F2** | Active editor tab | Toggle bookmark |
| **F2** / **Shift+F2** | Active editor tab | Next / previous bookmark |
| **Ctrl+Z** / **Ctrl+Y** | Raw XML | Undo / redo (snapshot history) |
| **Ctrl+Space** | Raw XML | Attribute / value completion |
| **Ctrl+L** | Raw XML | Go To XSD (attribute's definition in the Edit XSD tab) |
| **Ctrl+click** | Raw XML (mouse) | Jump to matching open/close tag |
| **Alt+click** | Raw XML (mouse) | Jump to parent tag start |
| **Ctrl+Shift+B** | Raw XML / Code Editor | Select enclosing block (caret to start) |
| **Ctrl+Shift+A** | Raw XML | Select parent block |
| **Ctrl+F** | Raw XML / Edit XSD / DDL Explorer | Find |
| **F3** | Raw XML / Edit XSD / DDL Explorer | Find next |
| **Ctrl+Shift+F** | Raw XML / Edit XSD / DDL Explorer | Find all |
| **Ctrl+R** | Raw XML / Edit XSD | Replace (not in the read-only DDL Explorer) |
| **Ctrl+Alt+Enter** | Raw XML / Edit XSD | Replace all (not in the read-only DDL Explorer) |
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
