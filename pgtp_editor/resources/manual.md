# PGTP Editor

PGTP Editor is a companion tool for SQL Maestro **PostgreSQL PHP Generator**. It
opens the generator's `.pgtp` project files directly, lets you inspect and edit
them safely, manage captions in bulk, edit event-handler code comfortably, compare
project versions, check the project against a live database, validate structure,
work on your database's own functions and triggers — trying them out in a
throwaway sandbox first — edit your own standalone PHP files and check their
syntax, and drive PHP generation, all without fighting the generator's own UI.

The editor never rewrites your file behind your back: every change you make is one
you asked for, and the on-disk bytes are preserved except where you edit.

---

## Getting Started

### Opening a project

Use **File ▸ Open** and pick a `.pgtp` file. If no local DDL-versioning project
(see *Local DDL-Versioning Projects*) is currently active, a chooser dialog
asks how you want to work with this file: **New Project…** starts one around
it, **Open Project…** attaches it to an existing project, and **Edit
Standalone** opens it plainly with no project involved — today's ordinary
behavior. If a project **is** already active, the chooser is skipped and the
file just opens into that project.

**File ▸ Open Recent** is a submenu of the projects you opened most recently —
up to ten, most recent first, each labelled with its bare file name and showing
its full path as a tooltip. It is rebuilt each time you open the submenu, so an
entry whose file has been moved or deleted meanwhile simply isn't there any
more rather than failing when you click it. With nothing recorded yet the
submenu holds a single greyed-out *(no recent files)* line, so it never looks
broken. Picking an entry goes through exactly the same open path as **File ▸
Open**, chooser dialog and all.

The window has three areas:

- **Left — Project Tree:** the structure of your project (pages, details, columns,
  event handlers). More tabs share this dock: **Contents** (this manual's
  chapters), **Database/XML Coherence** (while that view is on — see
  *Database/XML Coherence*), and **DDL Objects** (while the DDL Explorer is on —
  see *DDL Explorer*).
- **Center — Raw XML / Caption Management / Diff-Merge / Edit XSD / DDL Explorer /
  Manual:** the working area. It opens on **Raw XML**; the other tabs appear when
  you invoke them. Editing an individual function, procedure, or trigger opens
  one more tab per object (see *DDL Explorer*), each PHP file you open adds one
  tab of its own (see *Editing PHP Files*), generating a page, detail, or lookup
  from a database table adds a draft tab (see *Database/XML Coherence*), and a
  live sandbox session adds the **Sandbox SQL** console tab (see *The Sandbox*).
- **Right — Properties:** a read-only inspector for whatever you select in the tree.

When you open a file, the status bar shows a live message such as
`Opening dev_Ferrara.pgtp (312 KB)…` and the pointer becomes a wait cursor
(hourglass) until the project is loaded; it then settles on `Opened: <path>`.
The same busy feedback appears during other slow operations — see *A note on
busy feedback*.

### Saving, closing, reverting

- **File ▸ Save** (Ctrl+S) saves the **active tab**: the project file when you're
  in Raw XML (or any project view), the schema the XSD tab currently holds —
  curated or auto — when that tab is active (see *Schema Tools*), the `.sql`
  file behind an open DDL object editor tab when that tab is active (see *DDL
  Explorer*), or the PHP file behind an open PHP tab (see *Editing PHP Files*).
- **File ▸ Save As** (Ctrl+Shift+S) writes a copy of the **project** to a new
  path — this is unaffected by which tab is active, including a DDL object
  editor tab (which has its own, separate Save As… the first time you save it)
  and a PHP tab (which has no Save As at all).
- **File ▸ Close** (Ctrl+W) closes the project; if you have unsaved changes it
  prompts you to **Save**, **Discard**, or **Cancel**.
- **File ▸ Revert** discards your edits and reloads the last saved version from the
  automatic `.bak` backup written on save. It is **greyed out whenever there is
  no `.bak` to go back to** — before your first save of a freshly opened file,
  and in the project case below where no backup is written at all — so the entry
  is never offered when it has nothing to restore.

The editor writes UTF-8 and preserves your original line endings — it does not
convert line endings or re-encode content on save.

> **When a local DDL-versioning project is open** (see *Local DDL-Versioning
> Projects*) and this `.pgtp` is that project's linked working copy, Save behaves
> a little differently: it writes the working copy and **makes no `.bak`
> backup**, because the working copy itself is the safety net. This applies
> **only** in that situation — an ordinary `.pgtp` opened with no project active
> (or a `.pgtp` that isn't the active project's linked working copy) keeps making
> `.bak` backups exactly as described above. Pushing the working copy's changes
> back to the original file is a separate action, **Deploy .pgtp** — see *Local
> DDL-Versioning Projects*.

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

### Letting the tree follow your edits

**Edit ▸ Auto Parse XML** is a checkable toggle that does that rebuild for you
while you type. It is **off every time you start the editor** and your choice is
deliberately *not* remembered: a background reparse is a convenience you opt
into for a stretch of work, not a mode you should inherit from last week
without noticing.

With it on, the tree is rebuilt about **400 ms after the number of lines in the
Raw XML buffer stops changing** — pressing Enter, pasting a block, joining two
lines. A burst of edits produces one rebuild once things settle, not one per
keystroke. Typing inside a single line changes nothing structural, so it does
not trigger a run; use **Tools ▸ Reparse Raw XML into Tree** when you want a
rebuild right now.

Half-typed XML is expected to be malformed, so **a buffer that isn't well-formed
yet never interrupts you**: you get a transient status-bar note
(*Auto-parse: XML not well-formed yet — tree not updated*) instead of a dialog,
your caret is not moved, and the tree keeps its last good state until the
document parses again. Turning the toggle off also cancels a rebuild that was
already pending, so no stray parse lands after you opted out.

Because a rebuild replaces the tree, the Properties panel goes back to its empty
state after each run — click a node again to inspect it.

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
- **Bookmarks:** click the narrow strip at the left edge of the gutter — or
  double-click the line number itself — to set a bookmark on a line (see
  *Bookmarks*).
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

- **Ctrl+F2** toggles a bookmark on the current line; a tag marker appears in the
  strip.
- With the mouse there are two targets in the gutter, whichever suits you:
  **single-click the narrow bookmark strip** at the gutter's left edge, or
  **double-click anywhere in the line-number area** to the right of the fold
  chevrons. Both toggle that line's bookmark. (A single click in the line-number
  area still does nothing, so the two never fire together.)
- **F2** / **Shift+F2** jump to the next / previous bookmark.
- The **Bookmarks** menu holds the same actions plus **Clear All Bookmarks**.

Both mouse gestures work in **every** editor that has a gutter — the Raw XML
editor, **Edit XSD** / **Edit AutoXSD**, the read-only **DDL Explorer**, an open
**DDL object editor tab**, an open **PHP file tab** (see *Editing PHP Files*),
the **Sandbox SQL** console (see *The Sandbox*), and the **Edit code…** dialog.

**In Caption Mode the Bookmarks menu and its three shortcuts are switched off**
(the menu greys out and **Ctrl+F2** / **F2** / **Shift+F2** stop firing), because
the Raw XML editor they would act on is read-only for as long as that mode
lasts. **The gutter still works**: clicking the bookmark strip or double-clicking
a line number sets and clears bookmarks exactly as usual, since a bookmark is
only a marker over the text and does not depend on being able to edit it. Leaving
Caption Mode restores the menu and the shortcuts.

The **Bookmarks** menu and its shortcuts follow the tab you are working in: with
the **Edit XSD** (or **Edit AutoXSD**) tab active they act on the schema editor,
with the **DDL Explorer** tab, an open **DDL object editor tab**, or an open
**PHP file tab** active they act on that tab's own editor, and on any other tab —
including the **Sandbox SQL** console, whose buffer is a scratch pad rather than
a document — they act on the **Raw XML** editor. Using them never switches tabs
on you — a bookmark is always set or found in the editor you are already looking
at.

The **Edit code…** dialog has the same bookmark strip, but as a separate dialog
it is out of the Bookmarks menu's reach: there you set and clear bookmarks with the
mouse, in the gutter. Each editor keeps its own set, and loading a
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

The **Edit XSD** tab (see *Schema Tools*), the **DDL Explorer** tab, an open
**DDL object editor tab** (see *DDL Explorer*), and an open **PHP file tab** (see
*Editing PHP Files*) each have their own search bar; the shortcuts and the Edit
menu act on whichever tab is active, searching that tab's own document. On a tab
without its own search bar, Find reveals the **Raw XML** tab and searches there.

Because the DDL Explorer buffer is **read-only**, only the searching half applies
there: Find, Find Next and Find All work as usual, while Replace and Replace All
have nothing they can change. A DDL object editor tab and a PHP file tab are the
opposite case: they're fully editable, so **Find, Find Next, Replace, and Replace
All all work** there — only **Find All** stays inert and returns no results, the
one gap carried over from the read-only DDL Explorer's search bar.

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
- A **line-number gutter**, with a bookmark strip at its left edge: click it —
  or double-click the line number — to mark a line while you work through a long
  handler (see *Bookmarks*). There is
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

## Editing PHP Files

Not all of your PHP lives inside the `.pgtp`. The custom include files, helper
libraries, and hand-written pages that sit next to a generated application are
ordinary files on disk, and PGTP Editor opens them as ordinary tabs so you don't
have to leave the app to touch them.

A PHP tab has **no tie to your project at all**: it opens whether or not a
`.pgtp` is loaded, editing it never marks the project as changed, and saving it
never touches the project file. It is a comfortable text editor for one file —
nothing more is promised.

### Opening a PHP file

- **File ▸ Open PHP File…** — the entry sits right below **Open Recent**, above
  the project actions, because it *is* an open gesture. You can **select several
  files at once**; each one opens as its own tab. The dialog offers PHP file
  types first (`.php`, `.phtml`, `.phps`, `.inc`), then common text types, then
  **All files (*)** — the filter is a convenience, not a restriction.
- **Drag files onto the window** — drop one or several and they open the same
  way. Drop onto the tab bar or a dock rather than straight into an editor: an
  editor accepts a dropped file as *pasted text*, which is the text widget's own
  behavior and not something the editor overrides.

The status bar confirms each open with `Opened <path>`. The tab is labelled with
the bare file name plus the familiar `" *"` marker once you edit it, and its
tooltip shows the full path — which is what tells two folders' `index.php` apart.

**Opening a file that is already open focuses the tab you already have** instead
of reloading it from disk. That is deliberate: a second Open must never be able
to throw away edits you haven't saved yet.

A dropped **`.pgtp`** is not treated as text — it goes to the normal project-open
path, chooser dialog and all (see *Getting Started ▸ Opening a project*).

### Why a file is sometimes refused

Dropping a file is a gesture you can make by accident, so a drop is classified
rather than trusted. When something can't be opened, the status bar says which
file and why — never a silent no-op:

- **a folder, or a file that can't be read** — nothing to open.
- **a binary file** (anything with a NUL byte near its start) — opening a JPEG as
  "PHP source" and letting your next Ctrl+S write the mangled result back is data
  loss, not convenience.
- **a file that is not valid UTF-8** — refused for the same reason. Decoding it
  loosely would substitute replacement characters, and the tab's very first save
  would write those over your file. This is stricter than a general-purpose text
  editor, on purpose.

The UTF-8 check applies to **File ▸ Open PHP File…** too. The binary sniff is the
drop path's own guard, since a file you picked in a dialog is an explicit choice.

### Working in a PHP tab

The tab hosts the same editor the **Edit code…** dialog uses, in PHP mode:

- **PHP syntax highlighting** and a **line-number gutter** with the usual
  bookmark strip (see *Bookmarks*).
- **Auto-close** for `()`, `[]`, `{}`, `''`, `""`, **selection-wrap**, and
  **Ctrl+Shift+B** to select the enclosing bracket span.
- Its **own Find/Replace bar** — **Ctrl+F**, **F3**, **Ctrl+R** and
  **Ctrl+Alt+Enter** search and replace in *this file*, not in the Raw XML. (Find
  All is the one inert control here, as in a DDL object editor tab.)
- **Ctrl+Z / Ctrl+Y undo and redo only this tab's own edits.** They never reach
  the project's Raw XML history, exactly as in a DDL object editor tab.
- **No fold chevrons yet.** The gutter has the folding machinery, but nothing
  computes fold regions for PHP in this version, so the chevron column stays
  empty here.

### Saving and closing

- **Ctrl+S** (or **File ▸ Save**) with a PHP tab active writes **that file**,
  straight back to where it came from, in UTF-8 and keeping the line endings the
  buffer holds. The status bar reports `Saved <path>`; if the write fails, a
  **Save Failed** dialog shows the reason and the tab stays marked as changed.
- **There is no Save As for a PHP tab.** **Ctrl+Shift+S** always means the
  `.pgtp` project, whichever tab is active.
- **Closing a tab** with its **✕** prompts **Save**, **Discard**, or **Cancel**
  if it has unsaved edits. A save that fails — or that you cancel — **aborts the
  close**: the tab stays open with your text in it rather than being discarded.

> **Closing the whole application does not prompt for unsaved PHP tabs.** Only
> unsaved schema edits (the **Edit XSD** tab) stop the app from closing; PHP tabs
> and DDL object tabs are alike in this. Save the files you care about before you
> quit.

---

## Checking PHP Syntax

The **Tools** menu can run PHP's own syntax check over the file in front of you —
the same kind of gesture as **Validate Project** one tier down: this file rather
than the whole project. The three entries sit directly under **Validate
Project**.

Everything here is **advisory**. A lint failure never blocks, delays, or undoes a
save: by the time the check runs, your bytes are already on disk.

### Pointing the editor at a PHP executable

The check needs a `php` program to run. **Tools ▸ Locate PHP Linter…** opens a
file picker for it; the path is remembered with your other tool paths, alongside
the PHP Generator executable (see *Generating PHP*), so everything you had to
locate lives in one place. Both a full path and a bare `php` found on your `PATH`
are accepted.

A newly located linter takes effect **immediately, in tabs that are already
open** — nothing needs reopening.

### Running the check

- **Tools ▸ Lint Current File** checks the **active PHP tab's current buffer** —
  including unsaved edits, since it is the text in front of you that matters, not
  the last version on disk.
- **Tools ▸ Lint on Save** is a checkable toggle: with it on, every successful
  save of a PHP tab is followed by a check. Your choice is remembered across
  restarts and applies to tabs that are already open the moment you flip it.

The check runs off the UI thread, so a wedged linter or a slow network share
can't freeze the window; one that never answers is abandoned after ten seconds
and reported as such.

### Reading the results

Results land in the existing **Audit/Problems** panel, each row prefixed
**`[Lint]`** so you can tell them apart from `[Validate]`, `[Check]` and
`[Schema]` lines. **Click a finding to jump to it** — the right PHP tab is
focused and the caret is placed on that line.

**Every attempt produces at least one visible row**, and that is the point: a
silent panel would read as "the file is clean". So you always get a line, whether
the answer is `OK: no syntax errors detected in …`, a numbered finding, or one of
the honest non-answers — no linter configured, the configured linter is missing
or not executable, it timed out, it printed nothing, it printed something
unrecognizable, or no PHP tab was active when you asked. The rows that could not
be tied to a line are inert when clicked rather than sending you somewhere
plausible but wrong.

> **A clean result means "no error found *before this point*", not "no errors".**
> The check is PHP's own `php -l`, which stops at the **first** syntax error in a
> file. When a finding is reported, the panel says so next to it: fix that one
> and check again, because more may follow. And the check is a *syntax* check
> only — no style rules, no `phpcs`, and nothing that inspects what your code
> actually does.

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
  longer match, so you can zero in on a large set quickly. A filtered column keeps a
  **▼** marker in its header, so you can always see which columns are narrowing the grid.
- **Preset filters from the Project Tree** — a **See … in Caption Mode** action (for a
  table, a detail's table, or a single column — see *The Project Tree*) narrows the
  grid to just that scope.
- **Clear all filters** — available from the right-click menu, and from the
  active-filter banner's own **Clear** button. Both clear every filter mechanism at
  once: header filters, the Find/Filter pattern, and any preset filter.

### The active-filter banner

Whenever a preset filter or a **Find/Filter** pattern is narrowing the grid, a banner
appears above it saying what is filtering and how many rows survive, with a **Clear**
button at its right:

- A preset filter from the Project Tree reads, for example,
  `Filtered: Field = wbs_id — showing 3 of 214 rows`.
- A find filter reads, for example,
  `Filtered: Find "ord" (all columns) — showing 12 of 340 rows`. The mode is named
  only when it isn't the default **Normal** one (`regex`, `extended`), and
  `case-sensitive` is added only when you turned **Match case** on. The scope is
  always `all columns`, because the find filter matches a row if *any* of its columns
  matches.
- With both active, **both descriptors are shown**, joined by `·` — e.g.
  `Filtered: Field = wbs_id · Find "ord" (regex, all columns) — showing 2 of 214 rows`.

**Per-column header filters are deliberately not described in the banner** — they
already announce themselves with the **▼** marker on their own column header, which
the find and preset filters have no equivalent of. The banner's **Clear** button, on
the other hand, clears *everything* (header filters included) and the banner then
disappears.

### Find / Filter / Replace

A shared modal drives searching and bulk editing:

- **Mode:** **Normal (plain string)**, **Extended** (escapes like `\n`, `\t`, `\xNN`),
  or **Regular expression**.
- **Match case** toggle.
- **Scope:** **In selection** or **Global**.
- **Find / Filter** narrows the grid; **Replace** applies to the matched set.

### The live Find/Replace bar

Right-click the grid ▸ **Find / Replace bar** opens a modeless bar under the grid
— the caption equivalent of the Raw XML editor's search bar, and the quickest way
to see what a bulk replace would do before you commit to it. It has a **Find**
field, a **Replace with (live)** field, the same **Search Mode** list and **Match
case** toggle as the modal, and **Filter** and **Close** buttons.

**Replace here is live and has no Replace All button.** Every keystroke in either
field, and every change of mode or case sensitivity, immediately recomputes the
proposal and writes it into the **New Value** column of the rows currently in
scope. Nothing in your XML is touched: New Value is still only a proposal, and it
takes the usual explicit apply to turn it into text.

Because the preview is recomputed from scratch rather than piled up, it is fully
reversible while the bar is open — **clearing the Find field puts every row's
previous New Value back**, so a half-typed pattern leaves no debris. An invalid
regular expression is reported on the bar's own inline error line, never as a
dialog, and the preview is rolled back before you see the message.

**Filtering is deliberately not live**: it stays behind the **Filter** button. The
live replace acts on the rows the grid currently shows, so letting the filter
change under your fingers at the same time would make the scope of the proposal
impossible to read. The bar opens seeded with whatever find pattern is already
narrowing the grid.

### Power tools

- **Bulk Transform** — apply a transformation across many captions at once.
- **Unify** (right-click ▸ **Unify: set all inconsistent siblings to this value**) —
  set every other row sharing the selected row's element/attribute to the selected
  row's value, wherever they currently disagree. If any filter is active (a header
  filter, a Find/Filter pattern, or a preset filter from the Project Tree) when you
  invoke it, a prompt first asks **Filtered rows only**, **Entire project**, or
  **Cancel**, so you can choose whether the unify should touch only the rows
  currently visible in the grid or every matching row in the project. With no
  filter active, Unify runs project-wide as before, with no prompt.

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

## Database/XML Coherence

The **Database** menu compares your project's XML against a live PostgreSQL
database and shows both sides together in one view.

### Connecting

**Database ▸ Connection Setup…** collects server, port, database, user, and
password, with a **Test** button. The non-password fields are seeded from the
`.pgtp` project's `<ConnectionOptions>`; a connection you save is remembered and
takes precedence over the project's values next time.

**Connection Setup…** is available only in **projectless mode** — with no local
DDL-versioning project open (see *Local DDL-Versioning Projects*). Once a project
is open, its connection lives in **Project Settings…** (the **Connections** tab —
see *Local DDL-Versioning Projects ▸ Project Settings*) instead, and the menu
action is disabled while that project stays active; it re-enables the moment you
close the project. If something that needs a connection (Database/XML Coherence,
DDL Explorer) finds none configured while a project is open, it points you at Project
Settings via a status-bar message rather than opening the now-meaningless
standalone dialog.

> On Windows, use **`127.0.0.1`** rather than `localhost` — `localhost` can resolve
> to IPv6 first and stall the connection. The check runs off the UI thread with a
> timeout, so an unreachable server reports an error instead of freezing the app.

### Running the check

**Database ▸ Database/XML Coherence** is a checkable toggle (it has no keyboard
shortcut). Turning it on fetches the database schema, compares it against the XML
currently in the Raw XML buffer, and reveals the **Database/XML Coherence** tab in
the left dock. Turning it off hides the tab again. If the fetch fails — or there is
no project text, or no connection configured — the menu entry un-checks itself, so
it never claims a view is open that isn't.

**There is no direction to choose.** The database is always the truth and the XML is
the interface being checked against it, so both sides are shown together, per
relation, in a single tree. The old **Check: XML → Database** and **Check: Database
→ XML** items, and the separate **Table references** tab, are gone: this one view
replaces all three.

The header line above the tree names the connection (`user@host:port/db`) and the
total number of mismatches found. **File ▸ Close** closes the tab and discards its
results, since they belong to the project they were checked against (cancelling the
close, or **File ▸ Revert**, leaves them in place). After **Tools ▸ Reparse Raw XML
into Tree** the open view refreshes against the last database snapshot — no new
query is made — so you can see the effect of an edit right away.

The password is stored with the connection settings and is never written to any log.

### The two branches

The tree has two top-level branches, each showing how many rows in it are flagged.

**Tables and Views** is rooted in the live database, so it can only ever contain
relations that really exist. Each relation shows its kind — `(T)` table, `(V)` view,
`(M)` materialized view — and carries two groups:

- **Database columns** — every column the database has, with its datatype;
  primary keys are underlined, foreign keys are marked `fk`, and `not null` is
  noted. Columns the XML names but the database lacks appear here too, badged
  **missing in DB**; database columns no page or detail binds are badged **not in
  XML**. A green **✓** marks a coherent row and a red **✗** a flagged one.
  **Calculated columns** (marked `isCalculated="true"` in the XML) are
  generator-computed and have no physical database column by design, so they are
  shown with an orange **~** and are never flagged.
- **References** — where the XML uses this relation. The group is badge-summarized
  by role, and the relation row itself carries the role split
  **`(P3 D1 L2)`** — three page bindings, one detail binding, two column lookups.
  Expand the group for the full breadcrumb of each individual reference.

**Pages** mirrors the XML's own structure recursively: each Page shows its bound
table and its lookup columns, then nests its child Details, each of which does the
same — to whatever depth your document actually has, not a fixed three levels. A
lookup that also carries an on-the-fly insert page is badged **lookup with insert**
rather than a plain lookup, and a Page or Detail with no `tableName` at all is
badged **no table** (structural, not an error).

### Filtering the view

Four checkboxes sit above the tree, and **every ticked one has to hold** — they
combine with AND, so ticking a second box always narrows the result further,
never widens it.

- **Show only mismatches** — the rows needing attention (see below).
- **P>1**, **D>1**, **L>1** — relations the XML uses in **more than one Page**,
  **more than one Detail**, or **more than one Lookup**. The labels are the same
  short form as the `(P3 D1 L2)` role badge the relation rows already print, so
  the checkbox and the number it filters on are recognizably the same thing.
  These are the boxes to reach for when you are about to change a table and want
  to know how many places in the project would feel it.

Whenever anything is filtering, a **banner** above the tree names the active
combination and the row count — for example
`Filtered: mismatches only AND more than one Page (P>1) — showing 7 of 214 rows`
— with a **Clear filters** button that unticks all four at once.

**The order they compose in matters, and it is deliberately not a plain per-row
AND.** The role boxes first narrow *which tables are in scope*; the mismatch
filter then picks the flagged rows within that scope. That way a flagged column
under a table the role filter kept is still shown, instead of vanishing because
the column itself is not a page reference. When the result is empty the panel
says which kind of empty it is: the XML and the database genuinely agree, the
mismatch toggle alone hid everything, or the role boxes are part of what emptied
it — in that last case it points you at **Clear filters** rather than giving you
the wrong advice about the mismatch toggle.

### Show only mismatches

One **Show only mismatches** checkbox filters **both** branches at once, pruning the
tree to the rows needing attention plus the path down to each of them. Three things
are flagged:

- In **Pages**, a Page, Detail, or lookup whose target table or view **does not
  exist in the database** — badged **missing in DB** at that exact reference point.
  This is where a renamed or dropped table surfaces.
- In **Tables and Views**, a real relation the XML references **nowhere at all** —
  no page, no detail, no lookup — badged **unreferenced**.
- Failing **columns**, in either direction — but **never calculated columns**.

Read the toggle as **"things needing attention"**, not strictly "things that are
broken". An unreferenced database table is not an error the way a dangling XML
reference is; it is surfaced on purpose so you can decide. With the filter on and
nothing left to show, the panel says so — and distinguishes "the XML and the
database agree" from "no mismatches match this filter".

### Navigating and fixing

- **Double-click** a Page, Detail, lookup, or reference row to jump to its line in
  the Raw XML editor. Double-clicking a relation or column row instead lists every
  occurrence of its `tableName=`/`fieldName=` token in the Find-all results panel
  and seeds the Find bar, so **F3** steps through them. When there is genuinely
  nothing to find, the status bar says which token it looked for and what that
  means, for example *No `tableName="orders"` in the buffer — the XML does not
  reference orders.* So a real "the XML never mentions this table" (which is what
  an **unreferenced** relation looks like) never reads as a malfunction.
- **Single-click** any row to load the matching node in the **Properties** panel.
  This includes the rows *inside* a relation's **References** group: selecting one
  shows the properties of the page, detail, or column that does the referencing,
  not an empty panel.
- Where the XML names something the database does not have, right-click the row for
  **Rename table in XML…** or **Rename column in XML…** — a project-wide replace,
  after which the check re-runs automatically. Neither is offered for calculated
  columns, since there is nothing database-side to reconcile.

### Creating pages, details, and lookups from a table

**Right-click a relation row** in the **Tables and Views** branch (not a column row)
to synthesize project XML from that table's live schema:

- **Create new page from this table** builds a complete `<Page>` — column
  presentations, captions, and view/edit types derived from the database column
  types.
- **Create new detail from this table…** builds a `<Detail>` fragment: a nested
  page plus a master/foreign-key column map, filled in automatically when the
  table has exactly one foreign key, otherwise left as empty placeholders for you
  to complete.
- **Create new lookup from this table…** builds a `<Lookup>` element — link field
  = the table's single primary key; display field = the first text-like non-key
  column, best effort.

**All three open the result as a draft in a new tab.** Nothing is spliced into
your project's XML and nothing goes to the clipboard: the generated fragment is
yours to read, edit, and copy the parts of it you want into your project by hand.
Generated XML is a starting point, and you should be the one who decides what
lands in your file.

The tab is titled after what it holds and where it came from — *New Page:
customers*, *New Detail: order_items*, *New Lookup: currencies* — so several
drafts open at once stay tellable apart, and its tooltip repeats that it is saved
nowhere. **Every invocation opens a new tab**, so you can generate the same table
twice and compare, rather than having a second attempt overwrite the first. The
tab is a full XML editor with highlighting, so you can rework the fragment before
copying it out — but note that **Ctrl+F still searches the Raw XML tab**, not the
draft, since a draft is a fragment to skim and copy rather than a document to
search. It has **no save path and no unsaved-changes concept at all**, which is why
its **✕** closes it immediately with no prompt — there was never anywhere for the
text to be saved to, so a warning would be about nothing.

If your project already contains that `fileName`, or already references that
table, you get a **status-bar note** saying so — *"rename it in the draft before
pasting"* — and the draft opens regardless. Since nothing is inserted
automatically any more, a name collision is only a problem at the moment you
paste, which the app cannot see; so this is a heads-up and never a block.

These actions work from the schema captured by the last coherence run; if that
schema is no longer available, the status bar asks you to run **Database/XML
Coherence** first.

---

## DDL Explorer

**Database ▸ DDL Explorer** is a checkable toggle that shows your database's
server-side code — every function, procedure, and trigger — inside the editor.
It needs only a database connection: you can use it with **no `.pgtp` file open
at all**. If no connection is configured yet: in projectless mode, **Connection
Setup…** opens automatically — save a connection, then toggle the explorer
again; with a local DDL-versioning project open, a status-bar message points you
at **Project Settings…** instead (see *Database/XML Coherence ▸ Connecting* and *Local
DDL-Versioning Projects*).

Turning it on fetches all routines and triggers from the connected PostgreSQL
database and reveals two tabs at once:

- **Center — DDL Explorer:** every definition in a single **read-only**,
  SQL-highlighted buffer. Each object is preceded by a banner comment (e.g.
  `-- FUNCTION public.foo(integer) --`) so you can always tell where you are.
  The buffer is a live snapshot of the database and cannot be edited.
- **Left dock — DDL Objects:** a tree of the same objects, grouped from two
  angles. Under **Tables**, **every table in the connected schema is listed** —
  tables that own a trigger list those triggers nested underneath them; tables
  with no triggers appear as plain entries. Under **Functions & Procedures**,
  each function or procedure lists the triggers that call it. A trigger
  therefore appears in **both** places — either entry points at the same
  definition. **Click** a routine or trigger to jump the DDL Explorer buffer
  straight to it; **click** a table to see its columns in Properties (see
  *Clicking a table: column properties*, below).

### Reading the DDL Objects tree

Under **Tables**, each table is listed as `schema.table`. A table with
triggers shows a trigger count suffix, e.g. `public.orders  (2)`, with those
triggers nested underneath it exactly as before; a table with no triggers
shows the bare `schema.table` label (no count, since it would only ever be
`0`) and has no children. Widening the branch to every table means it no
longer omits tables that happen to have no trigger of their own.

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

When a **local DDL-versioning project** is open (see *Local DDL-Versioning
Projects*), object rows also carry combinable drift markers after their other
indicators:

- **`*`** — the checked-out local file has edits not yet included in a batch
  deploy.
- **`!`** — the live database has drifted from what was last deployed.
- Both can appear together as **`*!`** — there is no separate third symbol for
  "both."

Both markers are purely informational: they surface disagreement between the
local file, the last deploy, and the live database, but never block anything
by themselves. With no project open, no markers are shown.

### Clicking a table: column properties

Clicking any table node under **Tables** — whether it owns triggers or not —
populates the **Properties** panel (the same right-hand dock the Project Tree
and the coherence view use, see *Properties*) with that table's full column
list. Each column is shown as **two rows**: a compact identity line — the
column name, its data type, and whether it's nullable (`NULL` / `NOT NULL`) —
followed by a detail line with its default value and comment (an unset
default or comment shows as `—`). Subtle alternating shading pairs each
column's two rows together so they read as one record.

This is **display-only**: clicking a table populates Properties but, unlike
clicking a routine or trigger, does **not** jump or scroll the DDL Explorer
buffer, since a whole table has no single line in that buffer to jump to.
Right-clicking a table node offers exactly one action, **Add Trigger…** (see
*Creating a new trigger, function, or procedure*, below) — **Edit …** and
**Check Out for Versioning** remain available only on routine and trigger rows,
because those act on an object's existing definition.

### Working in the DDL tab

The DDL Explorer buffer is read-only, but it is a real editor view with the same
navigation comforts as the Raw XML editor:

- **Line numbers** in the gutter.
- **Folding per DDL object:** a chevron on each object's banner comment line
  collapses that object's body away, leaving the banner visible — handy for
  skimming a long database's worth of definitions.
- **Bookmarks:** click the bookmark strip at the left edge of the gutter (or
  double-click the line number) to mark a line, or use **Ctrl+F2** / **F2** /
  **Shift+F2** and the **Bookmarks** menu —
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

### Editing a single function, procedure, or trigger

Both browsing surfaces double as an entry point into a dedicated, **editable**
tab for one object at a time. Opening and editing such a tab touches no
database — it is a text editor over the object's current definition — and the one
gesture in it that *does* write anywhere, **Apply to Sandbox**, appears only while
a sandbox session is open and only ever writes to the sandbox (see *The
Sandbox*).

- In the **DDL Objects** tree, right-click a routine or trigger row for
  **Edit `<schema>.<name>(<argtypes>)`…** (or **Edit `<schema>.<table>.<name>`…**
  for a trigger). Right-clicking an argument-name child row offers no Edit
  action — only object rows open a tab.
- In the **DDL Explorer** tab's read-only buffer, right-click inside an
  object's body for the same **Edit …** entry. Two overloaded routines get
  distinct wording here since the full signature is in the label, so you can
  tell them apart before opening either.
- Re-invoking Edit on an object that's already open **focuses its existing
  tab** rather than opening a second one.

Both right-click menus also offer **Check Out for Versioning** alongside
**Edit …**. This is the project-aware variant of the same gesture: it requires
a local DDL-versioning project to be open (see *Local DDL-Versioning
Projects*) — if none is, a **"Project Required"** dialog offers
**Create…** / **Open…** / **Cancel** before continuing. Checking out an object
seeds a `ddl/<schema>.<name>.sql` file from the live definition the first
time (or just opens it if it's already checked out — **the local file is
never silently overwritten from the database**), then opens the same editable
tab described below, backed by that file instead of a live, unsaved buffer.
Re-invoking either Edit… or Check Out for Versioning on an object already
checked out and open focuses its existing tab.

The tab that opens is titled with the object's short name — `recalc`, or
`fmt(integer)` when it's one of several overloads, or `orders.trg_audit` for a
trigger — plus the same `" *"` dirty marker the **Edit XSD** tab uses once you
edit it. Its tooltip shows the full qualified name. It is a real, **editable**
SQL editor with the same gutter, bookmarks, folding, and 4-character tab stop
as the read-only DDL Explorer editor, plus its own Find/Replace bar — see
*Find, Replace & Find All* — where, unlike the read-only DDL Explorer, **Replace
actually works**.

**Ctrl+Z and Ctrl+Y in this tab undo and redo only this tab's own edits** —
they never touch the project's Raw XML undo history, even though the same
shortcuts drive the project's snapshot history everywhere else. This is the
one place in the app where Ctrl+Z means something different depending on
which tab is focused.

**Saving** (Ctrl+S, or File ▸ Save, while the tab is active) never touches a
database — it only writes a `.sql` file to disk:

- The **first save** opens a normal **Save As…** file picker, prefilled with a
  sensible filename (`schema.name.sql`, or `schema.table.trigger.sql` for a
  trigger) and, when a local DDL-versioning project is active, starting in
  that project's folder (see *Local DDL-Versioning Projects ▸ File dialogs
  default to the active project's folder*). Cancelling the picker just
  cancels the save — nothing is written and the tab stays dirty.
- The chosen path is **remembered**, so every later Ctrl+S writes silently to
  it for the rest of the session.
- **Ctrl+Shift+S** (File ▸ Save As) is **not** repointed to this tab — it
  always means the `.pgtp` project, whichever tab is active.

A tab opened via **Check Out for Versioning** (above) skips the Save As…
picker entirely — its path is already the checked-out `ddl/*.sql` file, so
every Ctrl+S from the first save onward writes straight to it.

**Closing** the tab (its **✕**, or the app's usual close-tab gesture) prompts
**Save**, **Discard**, or **Cancel** if it has unsaved changes, the same as
**Edit XSD**. Choosing **Save** on a tab that has never been saved runs Save
As…; if you cancel that file picker, the tab **stays open** rather than
closing.

**Format Selection** (**Ctrl+Alt+F**, or right-click ▸ **Format Selection**)
reindents the current text selection in place — the first real user of the
app's SQL formatter. Both are enabled only when you have a selection. If the
selection can't be safely reformatted (for example, an unbalanced
`BEGIN`/`END` split by the selection boundary), nothing changes: the problem
is reported as a `[SQL]`-prefixed line in the Audit panel, and the exact
offending text is underlined in red in the editor until your next edit or
your next format attempt.

Re-running **Database ▸ DDL Explorer** (a fresh fetch) never touches object
tabs you already have open — they are not reloaded, marked, or closed, even if
the live definition changed underneath them; your in-progress edits are never
silently discarded to resync with the database.

**Deploy this edit…** (right-click) asks where this edit should go and then runs
that gesture — it writes nothing of its own. It offers only the destinations that
actually exist right now: **Save (for a future batch deploy)** always, and
**Apply to Sandbox** while a sandbox session is open (see *The Sandbox*). There
is no destination for the real database in this version.

Everything else about this tab — editing, Save, Format Selection — stays purely
local: nothing here touches a database until you explicitly apply to the sandbox.
See *The Sandbox* for what an open sandbox session adds to this tab.

### Creating a new trigger, function, or procedure

Besides editing what the database already has, the DDL Explorer is where you
start a **brand-new** object. Nothing here talks to the database: both dialogs
only collect a few fields and open an editor tab on a generated skeleton, which
you then fill in and save like any other DDL object tab (see *Editing a single
function, procedure, or trigger*, above).

**Add Trigger…** — right-click a **table** node under **Tables** in the DDL
Objects tree. (This is the one context menu a table node has; **Edit …** and
**Check Out for Versioning** still belong to routine and trigger rows only.) The
dialog shows the clicked table as a fixed line — you picked it by right-clicking
it, so it isn't offered again as a field — plus:

- **Name** — the trigger's name.
- **Timing** — **BEFORE**, **AFTER**, or **INSTEAD OF**.
- **Events** — **INSERT**, **UPDATE**, **DELETE** as checkboxes, because
  Postgres combines them with `OR` (`BEFORE INSERT OR UPDATE`). Tick at least
  one; you can tick several.
- **Level** — **FOR EACH ROW** or **FOR EACH STATEMENT**. (Postgres has no
  transaction-level trigger, so none is offered.)
- **Trigger function** — a list of the functions the trigger can attach to. It
  lists **only functions that RETURN trigger**, because a trigger can attach to
  nothing else. If the database has no such function yet, the list is empty, the
  dialog says so plainly, and **OK** stays disabled — create the trigger
  function first (below), then come back.

**New Function/Procedure…** — two ways in: right-click the **Functions &
Procedures** branch in the DDL Objects tree, or use **Database ▸ New
Function/Procedure…**. (A routine isn't scoped to a particular table, so unlike
Add Trigger it earns a menu entry of its own.) Three fields:

- **Name** — plain (`my_function`) or schema-qualified (`pr.my_function`); an
  unqualified name lands in `public`, the same default Postgres itself applies.
- **Kind** — **Function** or **Procedure**.
- **Returns** — an editable list of the common types, so `trigger` is one click,
  while `numeric(10,2)`, `integer[]` or `pr.my_domain` can simply be typed.
  **The Returns row disappears entirely when you pick Procedure**: a Postgres
  procedure has no `RETURNS` clause at all, so a return type there would be a
  syntax error rather than an ignorable extra. The dialog opens on **Function**
  returning `trigger`, since writing a trigger function is the usual first step
  towards a trigger.

Both dialogs validate as you type: **OK** is enabled only when the fields
render, and the reason is shown inline in red rather than as an error box.
Names are quoted safely — mixed case is preserved (`MyFunc` becomes
`"MyFunc"`), and a name containing a space or a quote is **refused with an
inline message** instead of producing broken SQL.

**OK opens a new editor tab holding the generated skeleton** — a
`LANGUAGE plpgsql` body stub for a routine, a complete `CREATE TRIGGER`
statement for a trigger. Creating an object **runs nothing against the
database**; it only gives you correct starting text. Saving works exactly as it
does for any other DDL object tab.

With a **local DDL-versioning project** open (see *Local DDL-Versioning
Projects*), a newly created object is **registered for versioning
automatically**: it shows up as a pending local change (the `*` drift marker) in
the DDL Objects tree and is picked up by the normal deploy flow. Created with no
project open, it is just an editor tab and a file — unversioned, which is a
supported way to work.

### Schema-aware completion in the DDL object editor

Inside an open DDL object editor tab (opened via **Edit …** or **Check Out for
Versioning**, above), **Ctrl+Space** offers name completion drawn from the
same object catalog the DDL Explorer already fetched when you connected — it
never makes an extra database round-trip when you invoke it. This is the same
completion idiom as the Raw XML editor's Ctrl+Space (see *The Raw XML Editor ▸
Schema-aware editing*), applied here to live database names instead of the
`.pgtp` XSD schema. Three contexts are recognized:

- **A schema name (optionally partial).** Ctrl+Space after it offers the
  matching table names in that schema.
- **`NEW.` or `OLD.` inside a trigger function that already has a trigger
  attached to it.** Ctrl+Space offers that trigger's target table's column
  names directly.
- **`NEW.` or `OLD.` inside a trigger function with no trigger currently
  attached to it.** Ctrl+Space tells you plainly that no trigger is defined
  for this function, then opens a **"No Trigger Defined"** picker so you can
  choose which table it belongs to; once chosen, its columns complete as
  usual. This choice is remembered only for the current tab for the rest of
  the session — it is **never saved to disk**, and you're prompted again if
  you reopen the same function in a later session.

This completion is available only in the **editable** DDL object editor tab —
the read-only **DDL Explorer** viewer tab does not offer it.

---

## Local DDL-Versioning Projects

A **local project** is a plain folder on your own machine that gives you a
versioned, file-based home for the DDL objects and the `.pgtp` file you're
working on — checked-out routines and triggers as individual `.sql` files, an
optional local sandbox connection, and (later) git integration. Everything the
app manages here is a plain, readable file: nothing is a black box.

Nothing here is required for ordinary editing. Browsing the DDL Explorer and
plain **Edit …** (see *DDL Explorer*) work with just a database connection, no
project needed. A project becomes relevant only once you want checked-out
`ddl/` files, a versioned `.pgtp` working copy, drift markers, or a deploy.

### The File menu's project actions

Five actions on the **File** menu manage projects, in their own group between the
open actions (**Open…**, **Open Recent**, **Open PHP File…**) and **Save**:

- **New Project…**
- **Open Project…**
- **Close Project** — disabled until a project is open.
- **Project Settings…**
- **Deploy .pgtp**

**No project is ever created silently.** Any action that needs one — Check
Out for Versioning, for example — shows a **"Project Required"** dialog
offering **Create…**, **Open…**, or **Cancel** if none is open yet; choosing
Create or Open runs that flow first and then continues the original action.

### The window title shows the active project

Whenever a local DDL-versioning project is open, the title bar adds
**"— Project: `<folder name>`"**, ahead of the existing `.pgtp` filename and
unsaved-changes `*` marker — for example
`PGTP Editor — Project: acme_billing - dev_Ferrara.pgtp *`. With no project
active, the title shows just the app name and the `.pgtp` filename as before.

### File dialogs default to the active project's folder

While a project is active, every Open/Save-type file dialog in the app —
**File ▸ Open**, **File ▸ Save As**, **Schema ▸ Export XSD**, **Schema ▸
Import XSD**, the source/target file pickers in **Compare / Merge**, and the
first **Save As…** of a DDL object editor tab (see *DDL Explorer*) — starts
in the project's own folder instead of wherever you last browsed. With no
project active, these dialogs behave as before and default to the operating
system's own last-used directory. It's only a starting point in every case:
you can always navigate elsewhere.

### Creating a project

**New Project…** opens a dialog with:

- **Name** and **Description** — optional, free text.
- **Project folder** — pick a folder with **Browse…**; that folder *is* the
  project. There's no separate bootstrap step.
- **Local sandbox (optional)** — the Postgres **server** the sandbox should live
  on: **Host**, **Port**, **User**, and **Password**. **There is deliberately no
  "Database:" field.** You never name the sandbox database, because PGTP Editor
  **creates** it itself, with a name it generates
  (`pgtp_sandbox_<project>_<random>`) plus the ownership marker that is the only
  thing making a sandbox safe for the app to write to. An existing database is
  never reused, overwritten, or dropped — the caveat line in the group says as
  much.

  The group's own **Test** button checks something specific: that the connected
  user is a **superuser**, since sandbox provisioning needs `CREATE EXTENSION`.
  It probes the server's `postgres` maintenance database — the exact connection
  the `CREATE DATABASE` will use, since there is no sandbox database to probe
  before one is created. It reports one of:
  - **"Connected — superuser."**
  - **"Connected, but NOT a superuser — sandbox provisioning needs CREATE
    EXTENSION."**
  - if you chose **With data** (below) but `pg_dump`/`pg_restore` aren't on
    your PATH, a message naming the missing one.
  - the raw connection error, if it couldn't connect at all.

  The same group also carries the provisioning choice — **Without data (schema
  only, default)**, the schema-only baseline, or **With data**, which clones the
  target database via `pg_dump`/`pg_restore`. It is a **one-shot** choice, made
  here: cloning happens once, at creation, and refreshing the data later means
  destroying and recreating the sandbox. See *The sandbox is created with the
  project*, below, for what pressing **OK** then actually does.
- **Git (optional — not yet used)** — Server, User, and Checkout branch
  fields. These are captured and saved with the project, but git integration
  isn't built yet: nothing is cloned, committed, or pushed. They're recorded
  now so the intent isn't lost later.

### The sandbox is created with the project

If you filled the **Local sandbox** group in, pressing **OK** doesn't just record
those fields — it **creates and provisions the sandbox**, in the background so the
window stays responsive, and last of all, after the project folder itself is
written. Leaving the group blank simply means the project has no sandbox, which is
a perfectly good way to work (see *Project Status* for what that costs you).

The run does five things:

1. connects to the server's `postgres` maintenance database and
   **`CREATE DATABASE`**s an auto-named `pgtp_sandbox_…` database — Postgres
   forbids creating a database from inside the one being created, which is why
   the maintenance database is used and why no extra "admin connection" field
   exists;
2. **provisions** it: the schema-only baseline taken from the project's **target**
   connection, or a `pg_dump`/`pg_restore` clone if you chose **With data**;
3. installs the **`plpgsql_check`** extension, so the validation ladder's tier 3
   works from the start (see *The Sandbox ▸ The validation ladder, and the three
   ways to run it*);
4. **records the created name** in the project's settings file
   (`.ddlproject/settings.json`), so a later provisioning or reset run reopens
   the same database instead of making a second one; and
5. **leaves the session open.** That is why **Apply to Sandbox**, both check
   gestures (**Database ▸ Check Object Without Applying** and **Database ▸ Check
   Object in Sandbox**) and **Database ▸ Sandbox SQL Console…** are usable
   immediately after you create a project — no separate **Open Sandbox Session**
   needed (see *The Sandbox*).

The status bar confirms with `Created and provisioned sandbox database: <name>`.

**If a generated name is already taken on the server, a different random name is
tried.** An existing database is never reused, never written into, and never
dropped. In the very unlikely case that every generated name is taken, the step
stops with a message saying so, and nothing on the server is touched.

**A sandbox failure never costs you the project.** If creating, provisioning, or
`CREATE EXTENSION` fails, the project is still created — it just has no working
sandbox (a tier-2 *quality project*, see *Project Status*). The exact reason
appears in the Audit panel on a line prefixed **`[Sandbox]`**, and the project
records **no** sandbox database, so nothing later claims a sandbox that isn't
there. Its sandbox *server* details are kept, so you can fix the cause and try
again.

**If the project has no target connection yet** — likely, since you have just
created it — there is nothing to build a baseline from, so the sandbox is created
**empty** and the Audit panel says exactly that, pointing you at **Project
Settings** to set the target and at re-provisioning afterwards. Choosing **With
data** without a target likewise clones nothing and says so; your recorded choice
is left alone, so it still applies once a target exists.

Such a sandbox is perfectly usable — you can apply and check a self-contained
routine in it straight away — but it has **no baseline schema**, so an object that
references your target database's tables will fail to compile there until you give
the project a target connection in **Project Settings…** and re-provision from
**Database ▸ Sandbox Setup…**. That is a real answer from the sandbox, not a
malfunction: the table genuinely isn't there yet.

> Those Audit lines mention re-provisioning from **Sandbox Setup**, and that is
> exactly where to go: **Database ▸ Sandbox Setup…** is always on the menu. Set
> the target connection in **Project Settings…**, then re-provision from there —
> see *The Sandbox ▸ Setting up, re-provisioning and resetting a sandbox*.

### Opening a project

**Open Project…** opens a folder picker showing **folders only** (no files) — pick
an existing project folder. The folder must already be a valid project (it must
carry the `.ddlproject/settings.json` marker written by **New Project…**); picking
any other folder is rejected with a **"Not a Project Folder"** message instead of
silently creating an empty project.

On a successful open, the app compares a checksum of the linked `.pgtp`'s working
copy against its source and reports the result as an Audit-panel line prefixed
`[Project]`:

- **"Source .pgtp checksum recorded (…)."** — first time this comparison ran.
- **"Source .pgtp unchanged since last opened (…)."**
- **"Source .pgtp has changed since this project last saw it (…) — surfaced,
  not auto-resolved."**

If the DDL Explorer's routines and triggers are already loaded, its tree's
drift markers (see *DDL Explorer*) refresh at the same time.

Opening a project also **auto-opens its linked `.pgtp`** into the editor, so you
don't need a separate **File ▸ Open** afterwards:

- If the project already has a linked working copy, it opens automatically (if that
  file is missing from disk, nothing opens — the link is left alone rather than
  re-guessed).
- If the project has no linked `.pgtp` yet but its folder contains exactly one
  `.pgtp` file, that one opens instead.
- If none is found, nothing opens — no error, just an empty editor until you open
  a file yourself.
- If the folder contains **multiple** `.pgtp` files and none is linked yet, the
  app doesn't guess: it reports the finding as an Audit-panel line prefixed
  `[Project]` listing the candidates, and you open the one you want via
  **File ▸ Open**.

### Project Settings

**Project Settings…** opens a dialog exposing everything about the project in
one place, fully editable, saved back to the project's settings file on OK. The
fields are grouped into four tabs:

- **General** — **Name** / **Description**, and the **`.pgtp` link** (the source
  path — the sshfs-mounted original — the working copy path, and the last-known
  source checksum).
- **Connections** — **Target connection** and **Sandbox connection**, both
  connection profiles in full, including their password fields. The sandbox
  group's **Database** field here holds the name the app generated and created
  when the project was made (see *The sandbox is created with the project*) — it
  is shown so you can see which database you are working against, not so you can
  point the sandbox at one of your own; a database PGTP Editor didn't create is
  refused when a session is opened. Each group has
  its own **Test** button (see *Testing the project's connections*, below). The
  Sandbox connection group also carries the sandbox provisioning mode —
  **Without data (schema only)** or **With data**. Changing that mode here does
  not re-clone anything; it takes effect the next time the sandbox is
  reset or recreated. The same choice is offered — and acted on straight away —
  in **Database ▸ Sandbox Setup…** (see *The Sandbox*); both write the one
  recorded setting, so they can never disagree.
- **Git** — the same Server / User / Checkout branch fields as New Project.
- **Deploy manifest** — a table, one row per DDL object, of its `ddl/` path,
  its last-deployed content hash, and its deployed-commit-id (if any), with
  **Add Row** / **Remove Selected Row** buttons.

### Testing the project's connections

On the **Connections** tab, the **Target connection** and **Sandbox
connection** groups each have a **Test** button with a status line beside it,
so you can verify connection details you just edited — after a database move
or a password rotation, say — instead of saving blind and finding out later.

Both buttons test the values **currently typed in the fields**, not the
last-saved settings, so you can check a change before committing to it with
**OK**. Testing never saves anything by itself, and the result is shown only
on that inline status line: no dialog, no Audit-panel entry. The test runs in
the background, so an unreachable host can't freeze the dialog; the button is
disabled until the result comes back.

The two buttons deliberately do **different** checks, because the two
connections have different success conditions:

- **Target connection ▸ Test** is a plain connectivity check — the same one
  the standalone Connection Setup dialog performs (see *Database/XML
  Coherence ▸ Connecting*). It shows **"Testing connection…"**, then the outcome in green
  on success or in red with the driver's error message on failure.
- **Sandbox connection ▸ Test** is stricter: it checks for a **superuser**,
  not merely that the connection works, because setting up a sandbox needs
  `CREATE EXTENSION`. It is the same check as the **New Project…** dialog's
  sandbox Test button — the only difference being what it connects to: here the
  sandbox database the project already has, there the server's `postgres`
  maintenance database, since no sandbox exists yet at that point. It reports, in
  this order:
  - the raw connection error, in red, if it couldn't probe at all;
  - **"Connected, but NOT a superuser — sandbox provisioning needs CREATE
    EXTENSION."**, in red;
  - if the mode is **With data** but `pg_dump`/`pg_restore` aren't on your
    PATH, a red message naming the missing one;
  - otherwise **"Connected — superuser."**, in green.

A plain "it connects" test on the sandbox would be misleading — it would give
a green light to a connection that logs in fine as a non-superuser and then
fails at provisioning time. That is why the sandbox test is the stricter one.

### Where project settings live

A project's settings are one JSON file at `<project folder>/.ddlproject/settings.json`
— plaintext, including the password fields. The project folder's `.gitignore`
gets a `.ddlproject/` entry added automatically so this file is never
accidentally committed. Keeping it plaintext and local to the folder (rather
than in the app's global settings) means the project folder is self-contained
and portable — you can copy, back up, or hand off the whole folder and it
still works.

### Checking out DDL objects

See *DDL Explorer ▸ Editing a single function, procedure, or trigger* for the
**Check Out for Versioning** gesture itself and the drift markers (`*`/`!`)
this adds to the DDL Objects tree.

### The .pgtp file as a checked-out artifact

The first time you open a `.pgtp` file while a project is active, the app
copies it into the project folder as a **working copy** and remembers the
link — this happens automatically, with no extra step. (If no project was
active yet, **File ▸ Open**'s chooser — see *Getting Started ▸ Opening a
project* — is how you make one active for this file: pick **New Project…** or
**Open Project…** there instead of **Edit Standalone**.) From then on:

- Ordinary **Save** (Ctrl+S) writes to this working copy and makes **no
  `.bak` backup** — the working copy itself is the safety net. See *Getting
  Started ▸ Saving, closing, reverting* for how this compares to plain,
  project-less `.pgtp` saves, which are unaffected.
- Pushing your edits back to the original file (on the shared/quality server)
  is the separate, explicit **Deploy .pgtp** action — reachable any time from
  the File menu.
- Closing the project (**Close Project**) also offers this as a yes/no
  prompt if the working copy has changes not yet pushed. Declining just
  closes the project without pushing; nothing is lost.

### Closing a project

**Close Project** always succeeds — closing never forces anything. Along the
way it reminds you, via Audit-panel lines, of anything left informational and
unresolved:

- If the `.pgtp` working copy has unpushed changes, it offers to **Deploy
  .pgtp** (see above) — a yes/no prompt, not a requirement.
- If there are DDL objects with local edits not yet included in a batch
  deploy, it adds an Audit-panel line noting how many — it does not open any
  deploy flow automatically.

---

## The Sandbox

A project's **sandbox** is a throwaway local PostgreSQL database where you can
run a routine before anyone else has to live with it: apply your edit there,
validate it, poke at it with ad-hoc SQL, and only then decide what to do with it.
Nothing in this chapter can reach your real database.

The sandbox is a **local DDL-versioning project** concept, so everything below
requires a project to be open. The usual way one comes into being is **File ▸ New
Project…**: fill in that dialog's *Local sandbox* group and the app creates the
database itself, auto-named, provisions it, installs `plpgsql_check`, and leaves
the session open (see *Local DDL-Versioning Projects ▸ The sandbox is created with
the project*). **Database ▸ Sandbox Setup…** is the other way in, and the only way
back: it can create a sandbox for a project that has none, re-provision one whose
first attempt failed, re-clone, and reset — see *Setting up, re-provisioning and
resetting a sandbox*, below. The sandbox's connection details and the created
database's name are visible and editable in **File ▸ Project Settings… ▸
Connections**.

### Opening and closing a sandbox session

- **Database ▸ Open Sandbox Session** connects to the project's sandbox.
- **Database ▸ Close Sandbox Session** releases that connection.

Only one of the two is ever in the menu, and **Open Sandbox Session appears only
when the open project actually has a sandbox host configured** — an entry you
cannot use is left out rather than greyed out. The Sandbox SQL console and both
Check entries appear and disappear the same way, which is why the Database menu
looks different depending on whether a session is open. **Sandbox Setup… is the
one exception and is always there** — it is the gesture that can bring a sandbox
into existence, so it must be reachable when there isn't one.

**Opening a project connects nothing.** A session is a real connection to a real
database, so it is always something you asked for; the app never opens one, and
never creates or fills a sandbox, as a side effect of opening an *existing*
project. Creating a **new** one is the single exception, and only because you
asked for it there: filling in **New Project…**'s sandbox group creates the
sandbox and hands you an open session straight away. **So when you come back to a
project later, nothing is connected: Database ▸ Open Sandbox Session is how you
pick the sandbox back up.**

The outcome lands in the Audit panel as a `[Sandbox]` line, and a refusal always
says which refusal it was: the sandbox is unreachable, the user is not a
superuser, `pg_dump`/`pg_restore` are missing from your `PATH` (only for a **With
data** sandbox), no sandbox is configured — or the connected database is **not one
PGTP Editor created**. That last guard is deliberate and absolute: a sandbox must
both be named `pgtp_sandbox_…` *and* carry the ownership comment the app writes
when it creates one, because a database name alone can be faked. Pointing the
sandbox connection at a database you made by hand is refused rather than written
to.

Closing the session (or closing the project) takes every sandbox-only affordance
with it, including the Sandbox SQL console tab — a console that can only refuse
is worse than no console.

### Setting up, re-provisioning and resetting a sandbox

**Database ▸ Sandbox Setup…** is the sandbox's own control panel: creating a
sandbox database, (re-)provisioning it from the target, re-running a data clone,
resetting it, installing `plpgsql_check`, and seeing what has been applied to it.

**It is the one entry in this chapter that is always on the menu** — not hidden
when there is no session, and not hidden when there is no sandbox at all. Every
other sandbox gesture disappears when you cannot use it, but this is the gesture
that can *create* a sandbox, so hiding it whenever a sandbox is missing would put
it out of reach exactly when you need it. The dialog is non-modal, so a long
provisioning run doesn't lock the window, and you can keep working while it goes.

Inside, the same "no dead controls" rule applies one level down: **a button whose
operation cannot run now is not shown, and a sentence explaining why stands where
it would have been.** So the dialog looks different depending on what your project
has, and it always tells you which link in the chain is missing.

**Sandbox state**, at the top, is a plain reading of what is actually there: the
sandbox connection, the project tier and what (if anything) is degrading it,
whether the database is one PGTP Editor created, the recorded with-data /
without-data mode, and whether `plpgsql_check` is installed — plus, when it is
not, the sentence saying what tier 3 will consequently report. **Re-check
sandbox** probes again on demand. The group also carries the standing caveat
about the schema-only baseline: it reproduces schemas, types, tables (columns
only), views, routines, and triggers, but **not** extensions, sequences,
constraints, defaults, or data — so findings that lean on those are unreliable.

**Sandbox actions** offers, as your situation allows:

- **Without data (schema only)** / **With data (clone the target's rows)** — the
  provisioning mode. It is chosen here and recorded in the project's settings, and
  a later **Reset sandbox** re-runs *the same* mode.
- **Provision sandbox** — build the configured sandbox database from the project's
  target. Needs an open project (the mode has to be recorded somewhere) and a
  target connection to build from; without either, the reason is stated instead.
- **Create a sandbox database for me** — with an editable name beside it, which
  must look like `pgtp_sandbox_…`. This exists because PGTP Editor only ever
  writes to a sandbox it created itself: if your project points at a database that
  isn't one, this is how you get one that is, and it is provisioned in the same
  step.
- **Open sandbox session** — offered here too when none is open, so you don't have
  to go back to the menu.
- **Re-run data clone** — only for a **With data** sandbox. For a schema-only one
  the dialog says so plainly rather than showing a button that would clone
  nothing.
- **Reset sandbox** — drop everything the app put in the sandbox and provision it
  again in its recorded mode.
- **Install plpgsql_check** — a one-click `CREATE EXTENSION`, offered only when it
  can actually succeed. When it can't, the refusal you get is the real reason
  (typically that `CREATE EXTENSION` needs a superuser, so it is a question for
  your DBA), not a generic failure.

**Provision, Create, Re-run data clone, and Reset are destructive, and each asks
once** — one confirmation naming what is about to happen, and declining says so
and stops before anything is touched. Every outcome, success or failure, is
reported at the bottom of the dialog in the words the operation itself used;
nothing is swallowed.

**Working set** lists what has been applied to this sandbox — kind, schema,
object, table, and when it was applied — which is the sandbox's own record of what
it currently holds. It needs a live session to be read; without one, the dialog
says that rather than showing an empty table you might read as "nothing applied".

### The validation ladder, and the three ways to run it

Validating a routine in the sandbox climbs a four-rung ladder, and the Audit panel
gets **one `[Check]` line per rung, always** — never one summary line that quietly
hides a rung nobody managed to check:

- **tier 0 — syntax.** PostgreSQL's own parser is the syntax checker, reached by
  actually executing the definition, so this tier reports what tier 2 found rather
  than duplicating it. If tier 2 did not run, tier 0 says plainly that there is no
  offline syntax checker to fall back on.
- **tier 1 — the extra-warnings lint** (`plpgsql.extra_warnings`). It speaks only
  through PostgreSQL's notice channel, so a run where that channel wasn't live
  reports **unavailable**, never "passed" — an empty warning list from a run that
  couldn't hear warnings is indistinguishable from a clean routine.
- **tier 2 — compile.** Whether the definition actually compiled. A rejected
  definition is a *finding*, not an error in the checker: the check worked and the
  answer is "this does not compile".
- **tier 3 — semantic analysis** by the `plpgsql_check` extension. Without that
  extension in the sandbox this tier reports unavailable **with the reason** — the
  extension is absent, available but not created, or its state could not be
  determined, and those are three different answers. Install it from
  **Database ▸ Sandbox Setup…** or from the **plpgsql_check** node in the Project
  Status window.

Three gestures run this ladder, and they differ in **what they touch**, not in how
thorough they are:

| Gesture | Where | Runs | Changes the sandbox? |
|---|---|---|---|
| **Apply to Sandbox** | button + right-click menu in a DDL object editor tab | tiers 0, 1, 2 and — when `plpgsql_check` is installed — tier 3, all over your buffer | **yes** — commits |
| **Database ▸ Check Object Without Applying** | menu | the identical run, on the identical buffer | **no** — rolled back |
| **Database ▸ Check Object in Sandbox** | menu | tier 3 over what the sandbox already holds; tier 2 reports bookkeeping only | **no** — reads only |

So: **Apply gives you the full verdict** as part of applying; **Check Object
Without Applying gives you the same verdict and changes nothing**; and **Check
Object in Sandbox asks the sandbox about the state it is already in**.

The reason to pick the probe over Apply is not that it checks more — it checks
exactly the same things. It is that it leaves the sandbox as it was. Use it when
you want to know whether an edit would compile before letting it become what the
sandbox holds; use Apply when you have decided this version is the one the sandbox
should have.

None of the three has a keyboard shortcut. See *Keyboard Shortcuts*.

### Applying an object to the sandbox

While a session is open, every open **DDL object editor tab** (see *DDL Explorer*)
grows an **Apply to Sandbox** button under the editor, and the same entry in the
tab's right-click menu. It commits the tab's current text to the sandbox database,
records it in the sandbox's working set, and runs the whole validation ladder over
it — the DDL, the bookkeeping and the checks all in one transaction, so the sandbox
can never hold a definition without the record of what it holds.

- It is **never a keyboard shortcut**. An irreversible outward effect should not
  be one keystroke away, so applying is always a deliberate click or menu pick.
- It always asks first, and the confirmation **names both the object and the
  database** it is about to write to — you never confirm a nameless destination.
- The sandbox is **stateful**: your edit stays there until you apply something
  else. Applying is not a test that cleans up after itself.
- An empty buffer is refused outright rather than applied as an empty definition.
- The outcome — the headline, all four tier lines, any caveats, and every
  individual finding — is reported as `[Check]` lines in the Audit panel. A
  cancelled apply says so and applies nothing.

**Apply gives you the ladder's verdict; you do not have to check afterwards.** The
report you get names what compiled, what the lint said, what `plpgsql_check` found,
and what could not be checked at all.

**An apply that did not commit says so, in as many words.** If PostgreSQL rejects
any part of it, the whole transaction is rolled back and the Audit line reads
*"… was NOT applied to sandbox database …; the transaction did not commit."* — and
the buffer is **not** marked as applied. This matters: the sandbox does not hold
that text, and anything claiming otherwise afterwards would be a lie about what is
in your sandbox. The tier that produced the rejection is named alongside it, so you
know which rung failed.

The apply runs off the UI thread, so a slow `plpgsql_check` pass can't freeze the
window; the status line says the apply is under way and the full report lands when
it finishes.

**There is no "Apply to Target"** in this version — nothing here can write to your
real database, and the button is absent rather than disabled.

### Checking an object without applying it

**Database ▸ Check Object Without Applying** runs the ladder over the **active DDL
object editor tab** exactly as **Apply to Sandbox** would — tier 2 really compiles
your buffer, tier 1 really lints it, tier 3 really calls `plpgsql_check` — and then
**rolls the whole thing back**. The sandbox is left untouched, nothing is added to
its working set, and the buffer is not marked as applied.

This is the gesture that answers *"would this compile?"* without making it so. It
is deliberately built from the same machinery as the apply: a probe that diverged
from the real thing would be validating something other than what you are about to
run.

Exactly one object per run — the tab you are looking at. If no DDL object tab is
active, the status bar says so and nothing happens.

### Checking an object in the sandbox

**Database ▸ Check Object in Sandbox** is the read-only one: it examines the
sandbox **as it already stands** and writes nothing at all, not even a transaction
it later rolls back.

Because nothing new is applied in this run, the rungs that are *about* applying
have nothing to compile, and they say so instead of reporting a stale "passed":

- **tier 2 compiles nothing.** What it can honestly report is the bookkeeping
  fact — that the sandbox already holds this object, and when it was applied. If
  the sandbox has no record of it, it says that too and tells you to apply it
  first.
- **tier 0** mirrors that same answer, since it is PostgreSQL's parser reporting
  through tier 2.
- **tier 1 is unavailable** here: the lint only speaks while a definition is being
  compiled, and nothing is.
- **tier 3 really runs**, over the version in the sandbox.

**If your buffer has changed since it was applied, the report carries a
stale-buffer caveat**: the findings describe the version in the sandbox, not the
text in front of you. When you want the verdict on the text you are looking at,
use **Check Object Without Applying** or **Apply to Sandbox** — both compile your
buffer; this one does not.

Both Check entries are present whenever a sandbox session is open, and they stay
present even when the `plpgsql_check` extension is missing. That is on purpose: a
tier that could not run is a **reported outcome**, not a reason to hide the
gesture. The report always says what it could *not* check, so a check that could
not run can never be mistaken for a clean one.

For a trigger, the ladder needs to know which function the trigger calls; that is
read from the `EXECUTE FUNCTION …` clause in your buffer. If it can't be read, the
run says tier 3 was unavailable for that reason instead of guessing a function.

### Clicking a Check finding

Whichever of the three gestures produced them, findings arrive in the Audit panel
as their own lines, separately from the narrative tier lines, each tagged
**ERROR**, **WARNING**, or **INFO** and naming the line it was found on — for
example *[Check] ERROR line 12: …*.

**Click a finding to jump to it:** the object's tab is focused and the caret is
placed on that line. A finding whose line could not be determined is shown
**without a line number and does nothing when clicked** — deliberately inert,
because sending you to a plausible-looking wrong line is worse than not moving.

Findings only navigate while the object's tab is still open; a finding for a tab
you have since closed does nothing rather than reopening a document you dismissed.

### The Sandbox SQL Console

**Database ▸ Sandbox SQL Console…** opens the **Sandbox SQL** tab in the center
area: a SQL editor on top, a results grid below it. Like the other sandbox
gestures the menu entry exists only while a session is open, and there is only
ever **one** console — invoking the command again focuses the tab you already
have.

**It is sandbox-only by construction.** This console cannot run anything against
your production or quality database — not behind a confirmation, not behind a
preference, and there is deliberately no setting that would let it. It only ever
knows about the sandbox session.

- **Ctrl+Return runs**, and so does the **Run** button. This is the one execution
  gesture in the app that carries a shortcut, because the sandbox is disposable
  and there is no real database within this console's reach.
- Run sends **your selection if you have one, otherwise the whole buffer**.
- **Row limit** — a spin box above the editor, 1000 rows by default. There is no
  "unlimited" setting on purpose. A result cut off at the cap is reported as
  **TRUNCATED**, naming the cap, so a partial answer is never presented as a
  complete one.
- The **status strip** above the grid gives you the row count and the elapsed
  time, or the driver's own status and affected-row count for a statement that
  returns no result set, or the database's error message — an error never shows up
  as a silently empty grid. `NULL` values in the grid are dimmed and italic, so
  they can't be confused with an empty string or the text `NULL`.
- **Ctrl+Space** completes schema and table names (from the catalog the DDL
  Explorer already fetched), and **Ctrl+Alt+F** reformats the selection, exactly
  as in a DDL object editor tab.
- The console holds no document, so there is nothing to save and no unsaved
  prompt when it closes. Losing the session clears the results but leaves your
  typed SQL alone.

**Run in Sandbox Console** (right-click, in a DDL object editor tab, with text
selected) sends that selection over to the console and focuses it — and
**executes nothing**. There is exactly one place SQL runs, and pressing Run there
is your decision, not a side effect of copying something over. A second push
appends below the first rather than overwriting it.

---

## Project Status

**Database ▸ Project Status…** opens a separate **Project Status** window that
shows, at a glance, how much of the working setup is actually in place. It reads
left to right as a chain that splits at the end:

**Quality database → Project → Sandbox → Sandbox data / plpgsql_check**

Above the diagram a one-line summary states the tier and anything degrading it;
below it, the reminder **"Click a node for details and actions."** A
**Re-check** button sits in the top-right corner.

**Opening the window re-probes.** It is never a stale cached reading: a sandbox
that died since you opened the project shows as unreachable here, and invoking
the menu entry again probes again rather than just raising the window.
**Re-check** does the same on demand. Closing the window is never final —
**Database ▸ Project Status…** brings it back, re-probed, as often as you like.

The diagram follows the app's Light/Dark theme automatically (see *Appearance &
Layout*) and is drawn as vector artwork, so it stays sharp on a high-resolution
display and at any interface scale.

### The nodes

- **Quality database** — the target/production connection this project works
  against: **Not configured**, **Unreachable**, or **Connected**. **Connected
  means the app actually reached it**, not merely that a connection profile
  exists — a configured connection whose server is down reads *Unreachable*
  here. Not configured is its own state, distinct from a failed login: an
  unconfigured connection has not failed, it has not been tried.
- **Project** — which tier you are working in: **Standalone editor** (no project
  open), **Quality project** (a project is open but has no working sandbox), or
  **Development project** (a project is open with a working sandbox).
- **Sandbox** — the project's local sandbox database: **Connected**,
  **Unreachable**, or **Not configured**. A sandbox that is reachable but whose
  `pg_dump`/`pg_restore` tools are missing from your `PATH` reads **Connected —
  tools missing**: the database itself is fine, only data cloning is blocked.
- **Sandbox data** — what the sandbox database actually contains. This is
  **measured against the real sandbox**, not read back from the with-data /
  without-data choice you made when the project was created: that choice is what
  you *asked for*, and reporting it as what you *got* is how an empty sandbox used
  to claim it held a schema. There are **four** states:
  - **Not checked** — the sandbox could not be inspected (unreachable, or the
    inspection failed). This is the absence of an answer, not a report that the
    sandbox is empty. Re-check once it is reachable.
  - **Nothing provisioned** — inspected, reachable, and nothing of yours was found
    in it: no tables, views, or routines yet.
  - **Schema only** — the schema is there; no data was found.
  - **Data cloned** — a copy of the quality database's data is there. This is a
    positive claim and is never made without having seen the data, so an
    inspection that couldn't confirm data reads as *Schema only* rather than
    guessing upward.

  > **The first three states currently share one icon.** *Not checked* and
  > *Nothing provisioned* were added to stop the node claiming a schema it had
  > never seen, and their artwork has not been drawn yet, so both borrow the
  > *Schema only* picture. **Only the caption tells them apart** — read the
  > caption, not the icon, until the real icons land. The caption and the
  > click-through text are always the honest ones.
- **plpgsql_check** — whether the `plpgsql_check` extension is **Installed** in
  the sandbox or **Not installed**.

**If no sandbox is configured at all** — including when no project is open — the
Sandbox, Sandbox data, and plpgsql_check nodes are **simply absent** and the
chain ends at the Project node. They are not drawn greyed out: an inactive
capability is left out rather than shown as a dead control. A sandbox that *is*
configured but offline keeps all three nodes, in their failed state.

### Clicking a node

**Every node is clickable** (also with the keyboard: Tab to it, then Space or
Enter). Each opens its own small, non-modal window that you can leave open while
you work:

- **Quality database** — the connection's status and details, and a
  **Reconnect** action.
- **Project** — states the tier plainly. This window is deliberately minimal for
  now; its fuller contents are not yet designed.
- **Sandbox** — the sandbox's status and connection details. In the
  tools-missing case it **names the missing tool** and notes that schema-only
  work is unaffected, alongside an **Open help** button.
- **Sandbox data** — explains the current fill state in words, and offers **Run
  data clone now** (or **Redo data clone**, when data is already there) to clone
  the quality database's rows into the sandbox.
- **plpgsql_check** — explains whether the extension is installed, and when it is
  not, offers **Install the plpgsql_check extension**. Once it *is* installed the
  window is purely informational: re-running the install would do nothing, so no
  button is shown.

Both of those two need a **live sandbox session**, because that is what they run
through. Without one the button is simply not there — you get the explanation and
no dead control. Open a session from **Database ▸ Open Sandbox Session** (or from
**Sandbox Setup…**) and click the node again.

**Cloning data is destructive and asks first**, with the same one confirmation
**Sandbox Setup…** uses; declining changes nothing.

An action is never a single click on the node itself: you always land in the
node's window first and press the button there. Running one closes that window
and re-probes, so the diagram can't keep claiming the state from before you
acted.

> This window is a **report with a few one-step actions**, not the sandbox's
> control panel. The fuller set — provisioning, re-provisioning, resetting, the
> with-data/without-data choice and the working-set list — lives in **Database ▸
> Sandbox Setup…** (see *The Sandbox*), and connecting to the sandbox is its own
> gesture on the Database menu. Everything the diagram reports is measured against
> the real thing, not assumed from what you configured.

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

This checks the **project's structure**. For the syntax of a PHP file you have
open in a tab, see *Checking PHP Syntax* — the same menu, one tier down.

---

## Generating PHP

The **Generation** menu drives the PHP Generator command-line to compile your
`.pgtp` into PHP:

1. **Locate PHP Generator Executable…** once (the path is stored for future use).
2. **Generate PHP…** — if the project has unsaved changes, you're prompted to
   **Save** or **Save As** first, so the generator always runs against the file on
   disk. The output-folder picker that follows is prefilled — with the open
   **local DDL-versioning project's folder** if one is active (see *Local
   DDL-Versioning Projects*), otherwise with the project's declared
   `outputPath` if it has one, otherwise with the current project file's own
   folder — but it's only a prefill: you can always choose a different folder.
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
  back.
- **View ▸ Expand All** / **Collapse All** open or fold the whole Project Tree.
- **View ▸ Customize Toolbar…** chooses which commands appear on the toolbar and
  what icon each one carries (see *The toolbar*, below).
- Your window size and position, dock layout, theme, and toolbar arrangement are
  remembered between sessions.

### The toolbar

The **Main Toolbar** shows each command as an icon with its label beside it. Out of
the box it carries seven commands — **File ▸ Open**, **File ▸ Save**, **Edit ▸ Undo**,
**Edit ▸ Redo**, **Edit ▸ Find**, **Tools ▸ Validate Project**, and **Generation ▸
Generate PHP** — but it is not limited to them.

**View ▸ Customize Toolbar…** opens a two-list dialog: **Available** on the left,
**On Toolbar** on the right, with **Add →**, **← Remove**, **Up**, **Down**, and
**Choose Icon…** between them, and **OK** / **Cancel** at the bottom.

- The Available list offers **every command in the menu bar**, listed by its menu
  path — `File › Save As`, `Schema › Verify XSD`, `Database › DDL Explorer`, and so
  on — in the order the menus themselves present them. Anything you can invoke from
  a menu you can put on the toolbar.
- Commands already on the toolbar stay visible in the Available list but appear
  **greyed out**, so you can see the whole command set at once and still can't add
  the same command twice.
- Two things are deliberately left out: menu **separators**, and the **File ▸ Open
  Recent** submenu, whose entries change from session to session and so can't be
  pinned.
- **Up** / **Down** reorder the On-Toolbar list; **OK** applies the arrangement and
  remembers it for future sessions, **Cancel** discards your changes.

**Out of the box most commands have no icon** — only the original seven ship with
one — and that is fine: a toolbar button shows its label beside its icon, so an
icon-less command simply reads as text. An icon is never a precondition for putting
a command on the toolbar. But you can give any button one yourself — see
*Choosing a button's icon*, below.

A toolbar button *is* the menu item, not a copy of it. It therefore shares that
menu item's enabled state (a command disabled in the menu is disabled on the
toolbar), its checked state for toggles such as **Database ▸ DDL Explorer** or
**View ▸ Light Theme**, and its keyboard shortcut — the button and the menu entry
can never drift apart. Toolbars you arranged in an earlier version of the editor
are carried over unchanged.

### Choosing a button's icon

Each row in the **On Toolbar** list shows the icon that button will actually
carry — the one you assigned, or the command's built-in default. To change it,
select the row and press **Choose Icon…**, or just **double-click the row**.

The **Choose Icon** dialog is a grid of the roughly 106 Breeze icons bundled with
the editor, with a **search box** at the top: type any part of an icon's name
(`save`, `database`, `arrow up`) to narrow the grid. Every term you type has to
match, so `document save` finds the save-related document icons only. Double-click
a cell to pick it and close the dialog, or select it and press **OK**.

- The first cell is always **Default**, which **clears** the assignment: the button
  falls back to its built-in icon, or to no icon at all if it has none.
- **Any** button can be given an icon — including the seven that already ship with
  one, whose default you simply override.
- The icon is shown **only on the toolbar**. The matching menu entry keeps its plain
  text appearance, so decorating a button never changes how the menus look.
- The preview in the dialog is tinted the same way the real button is, so what you
  see is what you get under both the light and the dark theme.

Your icon choices are saved with the toolbar arrangement when you press **OK** and
survive across restarts. Removing a button from the toolbar drops its icon
assignment with it, and an assignment naming an icon or a command that no longer
exists is quietly discarded rather than breaking the toolbar.

---

## Keyboard Shortcuts

| Shortcut | Where | Action |
|----------|-------|--------|
| **Ctrl+O** | Global | Open a `.pgtp` file |
| **Ctrl+S** | Global | Save the active tab (the project, the open schema from the XSD tab, a DDL object editor tab's `.sql` file, or a PHP file tab's file) |
| **Ctrl+Shift+S** | Global | Save As — always the `.pgtp` project, whichever tab is active |
| **Ctrl+W** | Global | Close project |
| **F1** | Global | Open the Manual |
| **Ctrl+F2** | Active editor tab | Toggle bookmark (disabled in Caption Mode) |
| **F2** / **Shift+F2** | Active editor tab | Next / previous bookmark (disabled in Caption Mode) |
| **Ctrl+Z** / **Ctrl+Y** | Raw XML | Undo / redo (snapshot history) |
| **Ctrl+Z** / **Ctrl+Y** | DDL object editor tab / PHP file tab | Undo / redo (that tab's own history only — never the project's) |
| **Ctrl+Space** | Raw XML | Attribute / value completion |
| **Ctrl+Space** | DDL object editor tab | Schema-aware name completion (schema/table names, or `NEW.`/`OLD.` column names) |
| **Ctrl+Space** | Sandbox SQL console | Schema / table name completion |
| **Ctrl+L** | Raw XML | Go To XSD (attribute's definition in the Edit XSD tab) |
| **Ctrl+click** | Raw XML (mouse) | Jump to matching open/close tag |
| **Alt+click** | Raw XML (mouse) | Jump to parent tag start |
| **Ctrl+Shift+B** | Raw XML / Code Editor / PHP file tab | Select enclosing block (caret to start) |
| **Ctrl+Shift+A** | Raw XML | Select parent block |
| **Ctrl+F** | Raw XML / Edit XSD / DDL Explorer / DDL object editor tab / PHP file tab | Find |
| **F3** | Raw XML / Edit XSD / DDL Explorer / DDL object editor tab / PHP file tab | Find next |
| **Ctrl+Shift+F** | Raw XML / Edit XSD / DDL Explorer / DDL object editor tab / PHP file tab | Find all (inert in the DDL Explorer, DDL object editor and PHP file tabs) |
| **Ctrl+R** | Raw XML / Edit XSD / DDL object editor tab / PHP file tab | Replace (not in the read-only DDL Explorer) |
| **Ctrl+Alt+Enter** | Raw XML / Edit XSD / DDL object editor tab / PHP file tab | Replace all (not in the read-only DDL Explorer) |
| **Ctrl+Alt+F** | DDL object editor tab / Sandbox SQL console | Format Selection (reindent the current selection) |
| **Ctrl+Return** | Sandbox SQL console | Run the selection, or the whole buffer, against the sandbox |
| **Ctrl+F** | Caption Mode | Open Find/Filter |
| **Ctrl+R** | Caption Mode | Open Replace |
| **Ctrl+G** | Caption Mode | Go to line in Raw XML |
| **Ctrl+S** | Code Editor | Save code and close |
| **Ctrl+W** | Code Editor | Cancel |
| **Ctrl+C / Ctrl+V / Ctrl+X** | Editors | Copy / Paste / Cut |

In Caption Mode, **Ctrl+F** and **Ctrl+R** are rebound to the caption
Find/Filter/Replace tools for as long as the mode is active; they return to the Raw
XML editor's Find/Replace when you leave the mode.

**Nothing that reaches a database from a DDL object tab has a shortcut, on
purpose** — not **Apply to Sandbox**, not **Deploy this edit…**, and not either
check gesture (**Database ▸ Check Object in Sandbox** and **Database ▸ Check Object
Without Applying**), so a write to a database is never one keystroke away.
**Ctrl+Return** in the Sandbox SQL console is the one exception, because that
console can only ever reach the disposable sandbox (see *The Sandbox*).

The other commands added recently are shortcut-free too: **Edit ▸ Auto Parse XML**,
**Database ▸ Sandbox Setup…**, **Database ▸ Project Status…** and **Tools ▸ Start
MCP Server** are all menu-only. If you use one often, put it on the toolbar (see
*Appearance & Layout ▸ The toolbar*).

In **Caption Mode** the **Bookmarks** menu and **Ctrl+F2** / **F2** / **Shift+F2**
are disabled for as long as the mode lasts, because the Raw XML editor they act on
is read-only there; the gutter still sets bookmarks (see *Bookmarks*).

---

## The Manual

You're reading it. Open it any time with **F1** or **Help ▸ Manual**.

- The manual renders in the center **Manual** tab.
- The **Contents** tab in the left dock lists every chapter. Click a chapter to
  scroll the manual straight to it.

---

## The MCP Server

PGTP Editor can also run as an **MCP server** — a read-only service that lets an
AI assistant (or any MCP client) ask questions about a `.pgtp` project and about a
database, using the editor's own parsing and introspection instead of guessing at
the XML.

**It is off unless you turn it on**, and there are two ways to run it.

### From inside the editor

**Tools ▸ Start MCP Server** is a checkable toggle. It is **unchecked at every
startup** and your choice is not remembered between sessions — turning it on is a
per-session decision you make deliberately, and no stored preference can start a
server behind your back. Unchecking it stops the server again; the checkbox always
tells you whether one is running, and if a start fails the reason appears in the
status bar and the checkbox snaps back rather than claiming a server that isn't
there.

The point of running it in-app is that **it answers from the project you have
open**. A tool call that does not name a file is answered from the editor's live
model — including edits you have not saved yet, once they have been parsed into the
tree (see *The Project Tree ▸ Letting the tree follow your edits*). A call that
*does* name some other `.pgtp` still loads that file from disk as usual.

The server talks over standard input/output on a background thread, so the window
stays responsive and nothing new opens on screen.

### Headless, instead of the GUI

- `python -m pgtp_editor.main --mcp` — optionally followed by a `.pgtp` path.
- `python -m pgtp_editor.mcp` — the same server, in the module form MCP client
  configurations expect; it also accepts an optional `.pgtp` path.

No window opens. Naming a `.pgtp` file makes it the **default project** for tool
calls that don't name one — a convenience only; a call may always name its own
file. A path that doesn't exist, or can't be read, is reported and the server
refuses to start, rather than answering every later question with the same error.

### The tools

Six tools are offered, and **all six only read**:

- **read_project** — the project's pages plus the tables and views each one
  references.
- **list_pages** — the project's pages.
- **get_node** — one page, detail, column, or event handler with its attributes,
  by the identity the other tools report.
- **diff_projects** — the differences between two `.pgtp` files (added, removed,
  changed).
- **list_db_tables** — a database's tables, views, and materialized views with
  their columns.
- **list_db_routines** — a database's functions, procedures, and triggers with
  their source.

The two database tools take connection parameters with the call; the password is
used to connect and is never echoed back. Nothing an MCP client asks for can
change your project file or your database.

---

## Troubleshooting: debug mode

Launch the editor with `python -m pgtp_editor.main --debug` (or set the
environment variable `PGTP_EDITOR_DEBUG=1`) to record a full diagnostic log
of the session. A red **DEBUG** badge appears in the status bar and the log
file path is shown at startup. Even without debug mode, errors are always
recorded to a small `errors.log`. **Help ▸ Open Log Folder** opens the folder
containing both logs — attach the newest `debug_*.log` when reporting a
problem.
