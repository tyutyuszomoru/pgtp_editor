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

### The startup launcher

When the editor starts it puts one modal window in front of you — titled **PGTP
Editor**, asking **"What would you like to do?"** — because an empty Raw XML tab
is no guidance at all when the app supports several quite different ways of
working. The launcher shows the app's **three major modes side by side, in one
row**:

| Column | What it is for | Buttons |
|---|---|---|
| **Standalone** | Edit a `.pgtp` with the XML tooling, or a custom PHP file beside it. No project, no sandbox. | **File ▸ Open**, **File ▸ Open PHP File…** |
| **Project** | Work on the quality database through a local sandbox, or converge a deployable `.pgtp` by diff/merge. | **File ▸ New Project…**, **File ▸ Open Project…** |
| **Maintenance** | One-off administrative work on the app's own schema, and where the app itself is configured. Reshapes the window menu bar for this session — see *Maintenance mode*, below. | **Schema ▸ Edit XSD**, **Schema ▸ Import XSD**, **Settings ▸ Software settings…** |

**Every button on the launcher is the menu command it names**, which is why the
buttons are labelled with menu paths such as `File › Open...`. Picking one closes
the launcher and then runs exactly that command — there is no second, slightly
different version of any gesture hiding in here. A button whose menu item cannot
run right now is **greyed out** for the same reason, rather than looking
clickable and doing nothing.

The three columns are deliberately short. **Maintenance is Edit XSD, Import XSD
and Software settings…**: the rest of the **Schema** menu (**Edit AutoXSD**,
**Verify XSD**, **Export XSD** — see *Schema Tools*) and the whole **Generation**
menu are ordinary work you reach from the menus once you are in the app.
Generating your application is development, not maintaining the editor, so no
generation entry is offered here — see *Generating PHP*.

**The third Maintenance button is the whole of the app's configuration**, because
the four settings surfaces the app used to scatter across two menus are now one
command — see *Software Settings*.

- **The launcher always appears.** There is no "don't show this again" any more:
  it was removed together with the setting behind it, because the launcher is
  now where you pick the session's mode, and a mode you can silently skip is a
  trap rather than a convenience.
- **At startup you have to choose — the launcher cannot be dismissed.** There
  is no **Close** button, the window has no **✕**, **Escape** does nothing, and
  **Alt+F4** is ignored. Every way out of it therefore names a mode. That is
  deliberate: the mode is what shapes the session, it is never read from disk,
  and a launcher you could wave away left the app in a *No Mode* state that
  nothing else in the app is designed for.
- **Re-opened later it *is* dismissable.** When you bring the launcher back with
  **File ▸ New Session** (below) there is already a mode to fall back into, so it
  has its **Close** button, its **✕** and its **Escape** again — and closing it
  **keeps the mode the session is already in** rather than clearing it. Either
  way the launcher never quits the editor.
- **File ▸ New Session** brings it back at any time — see *Starting over*, below.

> **The editor does not open a file you pass on the command line, there is no
> shell "open with" integration, and double-clicking a `.pgtp` does not start
> it.** Starting the app always brings you to the launcher. There is also **no
> File ▸ Open Recent** list: this is a project-centric tool, and the launcher —
> not a list of files you happened to touch — is how you pick up work. A `.pgtp` path on the command line is meaningful **only** together
> with `--mcp`, where it names the headless MCP server's default project (see
> *The MCP Server*).

### Starting over — File ▸ New Session

**File ▸ New Session** re-initiates the app into its starting state. It is more
than "show that dialog again": in order, it

1. asks about **unsaved schema edits** (the **Edit XSD** tab),
2. closes every open **DDL object tab** and **PHP file tab**, prompting for each
   one that has unsaved edits,
3. closes the **document** — prompting to **Save**, **Discard** or **Cancel** if
   the `.pgtp` is dirty — and then the **project**,
4. and shows the launcher again.

**It does not clear the session's mode.** The mode stands until you pick a
column, which is what makes this launcher dismissable at all: close it and you
are back in the mode you were already in, with the same menu bar. Picking
**Standalone** or **Project** is what leaves **Maintenance mode** (see
*Maintenance mode*, below).

**Any cancel, at any step, abandons the whole gesture** and leaves your session
exactly as it was — nothing is closed and the launcher does not appear. So you
can always start the gesture to see what it would ask, and back out.

The entry sits in the File menu's last group, just above **Exit**, and has no
keyboard shortcut. (It is the command that used to be called **Show Launcher…**;
if you pinned that to your toolbar, the button still works and now runs **New
Session**.)

### Maintenance mode

Picking the launcher's **Maintenance** column does one extra thing beyond running
the button you pressed: it puts the session into **Maintenance mode**, which
**reshapes the window menu bar** so a one-off administrative task on the app's
own schema and settings is not surrounded by the whole application: most menus
go away, and one — **Settings** — appears.

| Window menu | In Maintenance mode |
|---|---|
| **File** | trimmed to **New Session** and **Exit** |
| **Schema** | whole — it is the mode's entire point |
| **Settings** | **appears** — it exists in this mode and nowhere else |
| **Help** | whole, so the manual (**F1**) is never out of reach |
| **View**, **Database**, **Tools**, **Generation** | hidden |

**Settings is the one menu that goes the other way.** Everything else this mode
does is subtraction; **Settings** is absent in ordinary work and present here,
because it is where the app is *configured* rather than used — configuring it is
exactly what you came to Maintenance mode to do, and a distraction the rest of
the time. It sits between **Generation** and **Help**, and it holds **exactly one
entry**: **Software settings…**, the dialog that now contains everything the app
lets you configure — snippets, the toolbar, the autoformatter and your keyboard
shortcuts (see *Software Settings*).

**Two of those four used to live on View, so they are Maintenance-mode gestures
now.** **Customize Toolbar…** and **Customize Shortcuts…** were reachable at any
time from the **View** menu; they are panes of **Software settings…** today,
which means you enter Maintenance mode to rearrange your toolbar or rebind a key.
That is the trade taken deliberately: the app is *configured* in this mode, and
one launcher button can stand for the whole of "settings" only if settings is one
command.

**Nothing on the Settings menu carries a keyboard shortcut, and nothing on it
ever will.** Hiding a menu does not switch off the keys of the entries inside it
— that is the same rule as the bullet about your own bindings, below — so a
chord here would open a Maintenance-mode dialog while you were in the middle of
ordinary work. These are rare, deliberate gestures, reached by opening the menu.

- **It lasts for the session and nothing else.** Maintenance mode is never
  written to disk and never survives a restart — you cannot inherit a trimmed
  menu bar from last week without noticing.
- **File ▸ New Session is the way out**, which is exactly why the mode keeps it:
  a mode able to hide its own exit would be a trap. **Picking the launcher's
  Standalone or Project column** is what actually leaves the mode and gives you
  the whole menu bar back — closing that launcher instead keeps you in
  Maintenance mode, because dismissal retains the mode you are in (see *Starting
  over*).
- **The Editor menu bar is deliberately untouched.** That is what keeps
  **Deployment ▸ Save XSD** right where it always is, so schema edits are
  saveable without leaving the mode (see *The Deployment Menu*). **Save XSD is
  how you save in Maintenance mode** — there is no File-menu save anywhere in
  the app.
- **Entering the mode clears the surfaces it is not for.** Picking the
  **Maintenance** column closes every **DDL object tab** and **PHP file tab**,
  and hides **both DDL Explorer panels** — the menu bar is not the only thing
  that gets out of the way. A tab with unsaved edits still asks first, and
  **cancelling that prompt keeps the tab but does not undo the mode**: the
  prompt's Cancel means *"keep this document"*, not *"put me back where I was"*.
  Leaving the mode later does not bring anything back, exactly as if you had
  closed the tabs yourself.
- **A toolbar button keeps working**, even when it is pinned to a command this
  mode hides. The filter is the menu bar only, by design; pinning something to
  the toolbar means you wanted it within reach. **This cuts both ways**, and it
  is worth knowing: **Settings ▸ Software settings…** can be pinned to the
  toolbar like any other command, and that button opens the dialog **outside
  Maintenance mode** as well. Hiding here means *"not in your way"*, never
  *"prevented"* — so a menu placement is a statement about where a command
  belongs, not a lock on it.
- **A key you assigned yourself keeps working too — except on the File menu.**
  The two halves of the trim are built differently and behave differently, and
  it is better to know that than to be surprised by it. **File** is trimmed
  entry by entry, so a File command the mode hides is really gone for the
  session: it is not on the menu and its key does nothing. **View**,
  **Database**, **Tools** and **Generation** are hidden *as whole menus*, and
  the commands inside them stay live underneath — so a key you bound to, say,
  **View ▸ Light Theme** in the **Keyboard shortcuts** pane still fires in
  Maintenance mode. That is deliberate and it stays that way: this mode
  exists to tidy the **menu bar**, it leaves the toolbar alone on purpose (see
  *Appearance & Layout ▸ The toolbar*), and a shortcut you deliberately
  assigned is yours to keep. None of the commands ship with a key of their
  own, so nothing fires here unless you bound it yourself.
- **File ▸ Exit stays**, alongside **New Session**. A mode that hid the way out
  of the application would be the same trap one level up, and a File menu with
  no **Exit** reads as a broken app rather than a focused one.

### Hidden because it can't run, versus hidden because you said so

Everywhere else in this app, a missing menu entry means **the command could not
work here**: there is no sandbox to check against, no session open, or the tab in
front of you has no such concept. That is why the app hides things rather than
greying them out — a control you cannot use is noise, and the fix is to acquire
what is missing (open a project, configure a sandbox, switch tabs).

**Maintenance mode is the one exception**, and it is worth knowing about if you
ever look at a trimmed menu bar and wonder whether something is broken. The
commands it hides *work perfectly well* — you could open a project or generate
PHP right now if you could reach them. They are out of the way because **you said
you were doing something else** when you picked the Maintenance column, not
because the app is unable to run them. Nothing is wrong, nothing needs fixing,
and the answer is never a setting: it is **File ▸ New Session**.

A quick way to tell the two apart: ask *"if this were visible and I clicked it
right now, would it do the thing?"* If the honest answer is no, it is hidden
because it cannot run. If the answer is yes, you are in Maintenance mode.

### Opening a project

Use **File ▸ Open** and pick a `.pgtp` file. If no local DDL-versioning project
(see *Local DDL-Versioning Projects*) is currently active, a chooser dialog
asks how you want to work with this file: **New Project…** starts one around
it, **Open Project…** attaches it to an existing project, and **Edit
Standalone** opens it plainly with no project involved — today's ordinary
behavior. If a project **is** already active, the chooser is skipped and the
file just opens into that project.

The window has four areas:

- **Left — Project Tree:** the structure of your project (pages, details, columns,
  event handlers). More tabs share this dock: **Contents** (this manual's
  chapters), **Findings** (navigable results — see *Where Output Appears*),
  **Database/XML Coherence** (while that view is on — see
  *Database/XML Coherence*), and **DDL Objects (Quality)** / **DDL Objects
  (Sandbox)** (while the matching DDL Explorer is on — see *DDL Explorer*).
- **Center — Raw XML / Caption Management / Diff-Merge / Edit XSD / DDL Explorer
  (Quality) / DDL Explorer (Sandbox) /
  Manual:** the working area. It opens on **Raw XML**; the other tabs appear when
  you invoke them. Editing an individual function, procedure, or trigger opens
  one more tab per object (see *DDL Explorer*), each PHP file you open adds one
  tab of its own (see *Editing PHP Files*), generating a page, detail, or lookup
  from a database table adds a draft tab (see *Database/XML Coherence*), and a
  live sandbox session adds the **Sandbox SQL** console tab (see *The Sandbox*).
- **Right — Properties:** a read-only inspector for whatever you select in the tree.
- **Bottom — Activity Log / Messages:** one dock with two tabs, holding the
  session's journal and what the checks reported — see *Where Output Appears*.

A second, narrow **Editor menu bar** sits directly above the center area, holding
the commands that act on the tab in front of you — see *The Two Menu Bars*.

When you open a file, the status bar's busy slot reads
`Opening dev_Ferrara.pgtp (312 KB) 2s`, counting up, and the pointer becomes a
wait cursor (hourglass) until the project is loaded; the slot then goes back to
`Idle` and the **Activity Log** records the open. The same busy feedback appears
during other slow operations — see *A note on busy feedback* and *The Status
Bar*.

### Saving, closing, discarding

**There is no File ▸ Save, no File ▸ Save As…, and no Ctrl+S.** Saving lives on
the Editor menu bar's **Deployment** menu, as a named entry per tab kind — **Save
pgtp** and **Save as new pgtp** while Raw XML is in front, **Save in Project** on
a DDL object tab, **Save XSD**, **Save PHP File**. See *The Deployment Menu* for
the whole table and for why not one of those entries carries a keyboard
shortcut.

- **Deployment ▸ Save pgtp** writes the project file in place; **Deployment ▸
  Save as new pgtp** writes it to a path you pick. Both are on the **Raw XML**
  tab, because that is the tab that holds the `.pgtp`.
- **File ▸ Close** closes the project; if you have unsaved changes it
  prompts you to **Save**, **Discard**, or **Cancel**.
- **File ▸ Discard Changes** throws away the edits you made since the last save
  and **reloads the file from disk**. It asks first, naming the file, and it is
  **greyed out whenever the buffer has no unsaved edits** — so it is never
  offered when there is nothing to discard. (This replaced the old **Revert**,
  which reloaded the `.bak` backup — "undo my last save" — and left the buffer
  dirty. The two are different commands, which is why the word changed with the
  behavior.)

**Pressing Ctrl+S does nothing at all** — no write, no message, no hint. That is
deliberate rather than an oversight: the key used to run a dispatcher that
guessed which tab you meant, and on six kinds of tab it silently wrote the
`.pgtp` instead. A reflex that is right on one tab and wrong on the next is worse
than one that works nowhere, so the key is unbound and every save is a
deliberate, named click. **Ctrl+Shift+S is gone the same way, and so is the
last exception:** the **Edit code…** dialog used to answer Ctrl+S as its OK
button, and no longer does (see *The Code Editor*). **Ctrl+S now does nothing
anywhere in the app, with no carve-outs.**

The editor writes UTF-8 and preserves your original line endings — it does not
convert line endings or re-encode content on save. Saving a `.pgtp` that already
exists copies the previous contents to `<name>.pgtp.bak` first.

> **When a local DDL-versioning project is open** (see *Local DDL-Versioning
> Projects*) and this `.pgtp` is that project's linked working copy, **Save
> pgtp** behaves a little differently: it writes the working copy and **makes no
> `.bak` backup**, because the working copy itself is the safety net. This applies
> **only** in that situation — an ordinary `.pgtp` opened with no project active
> (or a `.pgtp` that isn't the active project's linked working copy) keeps making
> `.bak` backups exactly as described above. Pushing the working copy's changes
> back to the original file is a separate action, **Deployment ▸ Deploy .pgtp**
> — see *Local DDL-Versioning Projects*.

---

## The Two Menu Bars

PGTP Editor has **two menu bars**, one above the other, and the split is the
answer to a simple question: *what does this command act on?*

- The **window menu bar** at the very top — **File · View · Schema · Database ·
  Tools · Generation · Help** — holds the commands that act on **the project or
  the application**: opening files, projects and connections, the schema,
  generation, the panels and the theme. An eighth menu, **Settings**, slots in
  between **Generation** and **Help** **only in Maintenance mode**, and holds a
  single entry, **Software settings…** — see *Getting Started ▸ Maintenance mode*
  and *Software Settings*.
- The **Editor menu bar**, directly above the central working area, holds the
  commands that act on **whichever tab you are looking at**. Its five menus are:

| Menu | Entries |
|---|---|
| **History** | **History…**, **Undo Project Edit**, **Redo Project Edit** — none of the three carries a shortcut |
| **Select** | **Select All** (Ctrl+A), **Select Enclosing Block** (Ctrl+Shift+B), **Expand Selection** (Ctrl+Shift+A), **Shrink Selection** (Ctrl+Shift+Z), and — on an editable editor only — **Sticky Selection** and **Line Selection**, both checkable and neither carrying a key (see *Editing Modes ▸ Sticky selection*) |
| **Parsing** | two faces, by tab: **Auto Parse XML** and **Validate Project** on an ordinary tab; **Check Object in Sandbox** and **Check and rollback** on a DDL object editor tab |
| **Navigation** | **Toggle Bookmark**, **Next Bookmark**, **Previous Bookmark**, **Clear All Bookmarks**, **List All Bookmarks** — plus, only while a comparison is loaded, **Next Difference**, **Previous Difference** and **Apply Changes to Target** (see *Diff / Merge*) |
| **Deployment** | every save and every outward push, **by tab kind** — see *The Deployment Menu* |

Every one of those commands resolves the editor **at the moment you use it**, so
Select, Navigation and the rest always act on the tab in front of you — never on
the Raw XML document behind it.

> **In Maintenance mode the window menu bar is reshaped** — **View**,
> **Database**, **Tools** and **Generation** are hidden, **File** shows only
> **New Session** and **Exit**, and **Settings** appears — while **this** bar is
> left completely alone, which is what keeps **Deployment ▸ Save XSD** available
> there. See *Getting Started ▸ Maintenance mode*.

> **The bookmark menu is called Navigation now.** Its five bookmark entries kept
> their own names; the menu was renamed because it is where jumping around a
> document belongs, not only where bookmarks do — which is also why
> **Compare/Merge**'s three navigation commands joined it (see *Diff / Merge*).

> **There is no Edit menu any more.** It was dissolved rather than emptied:
> Undo / Redo / History… moved to **History** — where the two are now called
> **Undo Project Edit** and **Redo Project Edit**, because they are the
> *project's* undo rather than the menu twin of Ctrl+Z — the two block-selection commands
> to **Select**, **Auto Parse XML** to **Parsing**, and Find and Replace became
> the permanently visible bar in every editor (see *Find, Replace & Find All*).
> Cut / Copy / Paste / Delete and **Preferences…** were never implemented and
> were removed rather than left as entries that answered "not yet implemented".
> The ordinary clipboard keys — **Ctrl+C / Ctrl+X / Ctrl+V** — work in every
> editor as they always did; they simply no longer pretend to need a menu.

**Validate Project moved with it**, from Tools onto **Parsing** — it is XML
validation, so it belongs with the parsing commands. The three PHP-lint entries
stayed on **Tools** (see *Checking PHP Syntax*), because splitting lint across
two bars would recreate exactly the confusion this split exists to remove.

### When the Editor bar changes shape

The bar follows the tab, using the app's usual rule: **a command that cannot
work here is absent, not greyed out.**

- **The whole Editor menu bar is hidden on the Caption Management tab and on the
  Manual tab.** Neither is a text editor, so all five menus would be dead
  weight. Switch to any editor tab and the bar is back.
- **The Deployment menu's entries change with the tab**, and only one group is
  ever shown at a time. On a tab that has nowhere to save and nothing to push,
  the menu is simply empty — see *The Deployment Menu*.
- **The Parsing menu has two faces and shows exactly one**, chosen by the tab in
  front of you — see *Parsing, on a DDL object tab*, below.
- **Select ▸ Expand Selection and Shrink Selection disappear on PHP and
  JavaScript tabs**, and **Ctrl+Shift+A** goes quiet with them. The ladder they
  climb is XML nesting or plpgsql structure; neither exists in PHP or JS, so the
  entries are not offered rather than offered and inert. **Shrink Selection is
  additionally absent in the XML editors** — see *Expanding and shrinking the
  selection*, below, for what each surface offers and why.
- **Select ▸ Sticky Selection and Line Selection are hidden on a read-only
  editor** — either **DDL Explorer** buffer, and the Raw XML editor while
  **Caption Mode** or **Compare/Merge** holds it. They toggle a selection you
  build with the keyboard, and that whole layer is inactive where nothing can be
  typed (see *Editing Modes ▸ Sticky selection*).
- **Select ▸ Select Enclosing Block means the right thing for the language you
  are in**: in an XML editor (Raw XML, Edit XSD, a generated draft fragment) it
  selects the enclosing XML element; in a code editor (PHP tabs, DDL object tabs,
  the DDL Explorer) it selects the innermost balanced bracket pair. It is one
  command with one shortcut, not two competing ones.

### Parsing, on a DDL object tab

**Parsing** holds four commands and shows **two of them at a time**, because
"parsing" means something different depending on what you are editing:

| Active tab | Parsing shows |
|---|---|
| **DDL object editor tab** | **Check Object in Sandbox**, **Check and rollback** |
| **every other tab** | **Auto Parse XML**, **Validate Project** |

A DDL object tab holds SQL, not XML, so the XML pair has nothing to act on
there; and the two sandbox checks are *the linting of the DDL*, which is exactly
what this menu is for. **The two check gestures live here and nowhere else** —
they used to sit on the **Database** menu and were removed from it, so one
gesture has one name and one home (see *The Sandbox ▸ The validation ladder, and
the three ways to run it*).

- **On a DDL object tab with no sandbox configured, Parsing is empty.** The XML
  pair is hidden by the tab kind alone, and the two checks need a sandbox to
  check against. That is the app's usual absent-not-greyed posture, not a
  glitch: fill in the project's sandbox connection (**File ▸ Project Settings… ▸
  Connections**) and the two entries appear. Whether they can then *run* is a
  second question, and the answer is on the refusal itself — see *The Sandbox*.
- **Validate Project is one of the toolbar's five default buttons, so that
  button leaves the toolbar while a DDL object tab is in front.** A toolbar
  button *is* the menu's own command (see *Appearance & Layout ▸ The toolbar*),
  so when the command is hidden the button goes with it. This is accepted and
  intended — switch back to any other tab and it returns.

---

## The Deployment Menu

**Deployment** is the fifth menu on the Editor menu bar, after **History**,
**Select**, **Parsing** and **Navigation**. It is where every **save** and every
**outward push** now lives — the one place to answer *"where does this edit
go?"* — and its contents follow the tab in front of you.

| Active tab | Deployment shows |
|---|---|
| **Raw XML** | **Compare/Merge pgtp**, **Save pgtp**, **Save as new pgtp**, **Deploy .pgtp** |
| **DDL object editor** | **Save in Project**, **Check and commit to sandbox**, **Apply to quality** |
| **Edit XSD / Edit AutoXSD** | **Save XSD** |
| **PHP file** | **Save PHP File** |
| anything else | **nothing** |

**Only one group is ever visible**, so the menu never offers you a save that
belongs to a different tab. The last row is not an oversight: the **Diff /
Merge** tab, **Caption Management**, either **DDL Explorer**, the **Manual**, a
generated **draft fragment** tab and both SQL consoles (**Sandbox SQL** and
**Quality SQL**) genuinely have no save destination and nothing to deploy, so they get no entries at all. (On
Caption Management and the Manual the whole Editor menu bar is hidden anyway —
see *The Two Menu Bars*.)

**Not one entry on this menu has a keyboard shortcut**, and that includes the two
database-touching entries. Two different reasons meet here:

- **The saves are keyless** because the old **Ctrl+S** had to guess which tab you
  meant, and guessed wrong on six of them — writing the `.pgtp` when you were
  looking at the SQL console or a draft fragment. Four named entries wired to
  exactly one writer each cannot make that mistake.
- **Check and commit to sandbox, Apply to quality and Deploy .pgtp are keyless**
  on the app's standing rule that *an irreversible outward effect must not be one
  keystroke away*.

If you use one of them constantly, pin it to the toolbar (**Settings ▸ Software
settings… ▸ Toolbar**). Be aware that such a button **comes and goes with the tab**, exactly
as the menu entry does — that is the honest posture, not a bug.

### What each entry does

- **Compare/Merge pgtp** — compare this `.pgtp` against another one (see *Diff /
  Merge*). It used to live on **Tools ▸ Compare / Merge Two Files…**; comparing
  is a `.pgtp`-level gesture, so it moved to the tab that holds the `.pgtp`.
- **Save pgtp** — write the project file in place. **Save as new pgtp** — write
  it to a path you pick. Neither is affected by anything except which tab is
  active, and both are on Raw XML only.
- **Deploy .pgtp** — push the project's working copy back to its source file. It
  moved here off the **File** menu, because it is meaningful only while the
  `.pgtp` is what you are looking at (see *Local DDL-Versioning Projects*).
- **Save in Project** — write the active DDL object tab's `.sql` file. Touches no
  database, ever (see *DDL Explorer*). On a tab holding a generated `ALTER TABLE`
  statement it always asks where, because that tab has no project file of its own
  — see *DDL Explorer ▸ The tab an Alter Table operation opens*.
- **Check and commit to sandbox** / **Apply to quality** — execute the active DDL
  object tab's buffer against the project's sandbox, or against the quality
  database. Both are confirm-gated and both name the database *and its host*
  before anything runs (see *The Sandbox* and *DDL Explorer*). **Apply to quality
  refuses an ALTER buffer** and states its reason; **Check and commit to sandbox**
  is that tab's run path.
- **Save XSD** — write whichever schema the XSD tab currently holds, curated or
  auto (see *Schema Tools*).
- **Save PHP File** — write the active PHP tab's file back where it came from
  (see *Editing PHP Files*).

Each entry acts on **the tab it belongs to and nothing else**. If one is somehow
run while its tab is not in front — from a pinned toolbar button, say — it
**refuses and says why in the Activity Log** (*"Save XSD runs on the Edit XSD tab —
open one first."*, *"Save in Project runs on an open DDL object tab — open one
first."*) instead of writing somewhere plausible but wrong. **Save XSD** is the
one where this matters most: off its tab it would have written an *empty*
`curated.xsd` over your schema, so it now refuses instead.

---

## Where Output Appears

Everything the editor produces for you to read lands on one of **three
surfaces**, and which one it is depends on what kind of answer it is:

| Surface | Where | What lands there | Lifetime |
|---|---|---|---|
| **Findings** | a tab in the **left dock**, beside Project Tree and Contents | navigable hits — **Find All** results and **List All Bookmarks** listings | replaced by the next such run |
| **Messages** | one tab of the **bottom dock** | what a check reported — **Validate Project**, PHP **lint**, the sandbox **Check** ladder, **Verify XSD**, sandbox provisioning outcomes | accumulates, run after run |
| **Activity Log** | the other tab of the **bottom dock** | the session's journal — files opened and saved, database actions, schema learning, project notes, and every transient notice | append-only |

> **Messages is not "results", and the difference matters.** The bottom dock's
> check tab used to be called **Results**, which collided with the **one thing
> in this app that really is a result set** — the grid of rows the **Sandbox SQL
> Console** brings back when you run a query (see *The Sandbox ▸ The Sandbox SQL
> Console*). Two unrelated surfaces answering to one word is how a reference to
> "the Results panel" ends up meaning whichever of the two the reader had in
> mind. So the check tab is **Messages** — it holds lines of text a tool wrote
> for you — and **Results** now means the console's row grid and nothing else.
> A toolbar button you pinned to the old **View ▸ Results** entry still works;
> it follows the rename to **View ▸ Messages**.

> **This replaces the single Audit / Problems dock.** There used to be one list
> holding all of the above, with a reserved text prefix per producer so nine
> kinds of row could share it. *"Click here to go somewhere"*, *"here is what
> the last check found"* and *"here is what this session did"* are three
> different questions, and one list answered none of them well — so the prefixes
> stayed (they still tell you who is speaking) but each one now names a
> **destination** rather than a queue position.

### The Findings tab — where you click to go somewhere

**Findings** holds the rows whose whole purpose is to take you to a line:
`[Find]` rows from **Find All**, and `[Bookmark]` rows from **Navigation ▸ List
All Bookmarks**. **Click a row to jump to it** — the right tab is focused and the
caret is placed on that line.

It sits in the **left dock** rather than at the bottom on purpose: the centre
pane is the editor each hit jumps into, and a results panel there would cover the
very thing you are navigating.

- **It is hidden until it has something to say**, exactly like the **Contents**,
  **Database/XML Coherence** and **DDL Objects** tabs beside it, and it **opens
  and focuses itself** the moment the first navigable row lands. A result you
  asked for should not need a second gesture to be seen.
- **View ▸ Findings** shows it on demand, whether or not anything has landed in
  it yet. It exists so the tab is not reachable *only* as a side effect of
  running something: a session with no navigable operation behind it used to
  make the tab look like something that did not exist.
- **The last operation wins, across kinds.** Run **Find All** and then **List All
  Bookmarks** and the bookmarks replace the finds — both answer *"where do I want
  to go next?"*, and only one such question is live at a time. Re-running the
  same operation likewise replaces its own previous rows.
- **Rows found in a DDL Explorer's read-only buffer navigate like any other.**
  Clicking a `[Find]` or `[Bookmark]` row from either Explorer focuses that
  Explorer's own viewing pane and puts the caret on the line — and it is always
  the *right* one of the two, because the row remembers which Explorer it came
  from rather than guessing from whichever tab you are on. Read-only never meant
  "you cannot go there".
- Rows that genuinely could not be tied to a line (a generated draft tab, a
  finding with no line number) are **listed but inert when clicked**, rather than
  sending you to a plausible-looking wrong place.

### The Messages tab — what the checks found, kept

**Messages** is the bottom dock's other tab, and it **accumulates**. Each run
opens with a separator — a blank line, a **dated header** (`2026-08-10 14:32:07`)
and a dashed rule — and everything before it stays. Validation history is worth
keeping: you can compare what this run said against what the last one said
without having to remember it.

Its rows are clickable in exactly the same way as the Findings tab's, so a
`[Validate]`, `[Lint]` or `[Check]` line with a line number still jumps you
there.

A run that reports into Messages **switches the bottom dock to this tab** so you
see it — but it will not re-open a dock you closed. **View ▸ Messages** brings it
back whenever you want it.

**A few lines land here precisely because they would otherwise be lost.** When
you close a project, the `[Project]` reminders the close produces — most
visibly *"N DDL object(s) have local edits pending a batch deploy"* — are
written to the closing project's activity journal **and** rendered here. Both,
not either: the journal keeps the record inside the project it belongs to, and
the Messages tab is what survives the close, so the reminder is still on screen
when the project it refers to is gone (see *Local DDL-Versioning Projects ▸
Closing a project*).

### The Activity Log tab — what this session did

The **Activity Log** is a journal, not a findings list: one timestamped row per
action, oldest first, reading *timestamp — source, action, a short preview of
what it acted on, and how it ended* —
`2026-08-10 14:32 - Sandbox DB Apply to Sandbox CREATE OR REPLACE FU… success`.

- The **source** is one of **Quality DB**, **Sandbox DB**, **Project files** or
  **Quality files**, so every row says which part of the app is speaking.
- **A failed action is shown in red**, and a row recorded with **no project open
  is italic** — that one lives for the session only and is written nowhere.
- **Click a row to open its full text** in a read-only, syntax-highlighted
  viewer: the error when the action failed (that is why you clicked), the DDL
  otherwise. When a row has both, **right-click** it and pick — **View full
  DDL…** or **View full error…**. A row carrying neither is inert.
- With a project open the journal is kept in the project, as
  `<project folder>/.ddlproject/activity.jsonl` — plain text, beside the
  project's settings, inside the already-gitignored folder. With no project open
  nothing is written to disk.
- Until anything is recorded the tab reads **"No activity recorded yet."**

**Every transient notice the app used to flash on the status bar now lands
here** — *opened this file*, *saved that one*, *no `tableName="orders"` in the
buffer*, *DDL Explorer (Sandbox) failed: …*. See *The Status Bar*, below, for why.

### Reaching them from the View menu

- **View ▸ Activity Log / Messages Panel** is the checkbox for the whole **bottom
  dock**, alongside **Project Tree** and **Properties Panel**. Closing the dock
  with the **✕** on its title bar unchecks the entry, and re-checking it brings
  the dock back. (The dock's own title bar reads **Activity Log / Messages**.)
- **View ▸ Activity Log** and **View ▸ Messages** each **open the bottom dock if
  it is hidden and focus that tab**. They are not checkboxes: a tab is either the
  one in view or it is not, and there is no third state to check.
- **View ▸ Findings** is the same shape one dock over: it un-hides the **left**
  dock, reveals the **Findings** tab and focuses it. Not a checkbox either, and
  like its two siblings it ships with **no keyboard shortcut**.

**A dock layout you saved in an earlier version still applies.** The bottom dock
kept its own identity through the split, so its remembered size, position and
visibility carry straight onto the two-tab panel. In the worst case it falls back
to the default layout — nothing is lost, and every surface stays reachable from
the **View** menu.

---

## The Status Bar

**The status bar is not a message board.** It carries a small set of permanent
slots, each of which always states a defined fact, and nothing scrolls across it:

**mode indicator · busy slot · Quality ● · Sandbox ● · DEBUG**

That is a deliberate reversal. The bar used to be where every transient notice
appeared for a few seconds and then vanished — which meant that at any given
moment it either said something you had already read or nothing at all, and a
message you looked away from was simply gone. **Those notices now go to the
Activity Log** (see *Where Output Appears*), where they are timestamped, kept,
and attributable to a source. If you expected the bar to tell you something and
it did not, the Activity Log tab is where to look.

### The mode indicator

A **colour-coded chip** shows which mode the session is in. It appears **twice,
saying the same thing**: prominently at the right-hand end of the **Main
Toolbar**, and again in the status bar. Both are written from one answer, so they
can never disagree.

- **The colour is the major mode** — the one you picked in the launcher:
  **Standalone mode**, **Project mode** or **Maintenance mode** (see *Getting
  Started ▸ The startup launcher*). **Every label says the word "mode" out
  loud**, because a chip reading a bare *Project* reads like the name of a thing
  rather than a state you are in. The chip has a **No Mode** reading in a neutral
  colour rather than going blank, for the window behind the launcher before you
  have picked — in practice you will not see it, because the startup launcher
  cannot be dismissed without a choice and dismissing a later one keeps the mode
  you are in.
- **A minor mode is appended as text**, after a middle dot — `Project mode ·
  Caption`. The minor modes are the editor sub-states: **Caption** (Caption
  Management), **Compare/Merge**, and **Edit XSD**. Plain editing is the
  *absence* of a minor mode, not a fourth one, so most of the time the chip shows
  the major mode alone. Only one minor mode is ever named; Caption wins over
  Compare/Merge, which wins over Edit XSD.
- **The editing mode of the editor you are typing in is appended last**, after
  another middle dot — `Project mode · Edit mode`, or `Project mode · Command
  mode — press i to type`. That third segment is the keyboard vocabulary the
  **focused** editor is listening in (see *Editing Modes: Edit mode and Command
  mode*), and it is **absent** whenever the focused editor is read-only or is not
  an editor at all. It is per-editor and independent of the other two — a tab
  switch can change it without changing anything else on the chip.
- **The major mode owns the colour** and neither the minor nor the editing mode
  gets one of its own. Three majors times four sub-states would already be a
  twelve-colour vocabulary, which is exactly what a glance-recognizable chip
  cannot be.
- **The colours follow the Light/Dark theme** (see *Appearance & Layout*), so the
  chip stays legible in both.
- **It is passive.** There is no click, no context menu, and no way to change
  mode from it. Mode is set by **picking a launcher column** — at startup, or after
  **File ▸ New Session** brings the launcher back — and the chip only reports it,
  which is what its tooltip says too.

### The busy slot

The slot beside the mode chip answers one question: *is something running right
now?* It reads **`Idle`** when nothing is, and otherwise names the operation with
a **live elapsed-seconds counter** beside it — `Opening dev_Ferrara.pgtp
(312 KB) 4s`, `Validating dev_Ferrara.pgtp 7s`. See *A note on busy feedback*.

If one long operation starts another, the slot keeps showing the **outer** one
and only returns to `Idle` when the last of them has finished, so it can never
claim to be idle while something is still going.

### The two connectivity dots

While a **local DDL-versioning project is open**, two labelled dots report
whether its databases can be reached: **`Quality ●`** and **`Sandbox ●`**.

| Dot | Meaning |
|---|---|
| **green ●** | reachable |
| **red ●** | offline — configured, but it did not answer |
| **white ●** | no connection configured |
| **hollow grey ○** | **not checked yet** |

**The hollow dot is a real state, not a blank.** A project you have just opened,
or a probe still in flight, has not produced an answer yet — and showing that
plainly is better than leaving a gap you would read as "fine" or, worse, keeping
yesterday's green. Each dot's tooltip spells its state out in words.

- **They are polled every 30 seconds, and only while the editor's window is
  active.** Switch to another application and the polling stops; come back and it
  polls **immediately**, so you never read a dot that is up to half a minute
  stale. The check runs off the UI thread, so an unreachable server can't freeze
  the window twice a minute.
- **Green means reachable, not fully capable.** The poll is a single lightweight
  round trip. Whether the sandbox is *usable* — superuser, `pg_dump`/`pg_restore`
  present, `plpgsql_check` installed — is the **Project Status** window's
  question, so a dot can be green while that window still reports a degradation.
- **With no project open there are no dots at all** — absent, not greyed out,
  like every other thing in this app you cannot currently use.

### The DEBUG chip

A red **DEBUG** chip appears at the end of the bar when the editor was started
with debug logging on, and only then — see *Troubleshooting: debug mode*.

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

**Parsing ▸ Auto Parse XML** (on the Editor menu bar — see *The Two Menu
Bars*) is a checkable toggle that does that rebuild for you
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
yet never interrupts you**: the note *Auto-parse: XML not well-formed yet — tree
not updated* goes quietly to the **Activity Log** instead of putting up a dialog,
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
- Right-click ▸ **Format Selection** — or **Ctrl+Alt+F** — re-indents the selected
  XML by element nesting depth, and changes nothing else about it. It needs a
  selection, and it is refused while the buffer is read-only. See *The
  Autoformatter*.

### Undo, Redo & History

The editor keeps a rolling history of up to ten XML snapshots.

- **Ctrl+Z** undoes and **Ctrl+Y** redoes a step. **Redo is Ctrl+Y on every
  platform, and it is the only redo chord** — see *Keyboard Shortcuts ▸ Undo and
  Redo depend on which tab you are in*. These keys drive the project's history
  **only while the Raw XML tab is in front**; every other tab answers them out of
  its own history.
- **History ▸ History…** (on the Editor menu bar, alongside **Undo Project
  Edit** and **Redo Project Edit**) opens a jump list of the recent snapshots so
  you can jump straight back to an earlier state. (Snapshots taken when a file is
  opened or reverted are baselines and are not offered as undo targets.)
- **While the Raw XML buffer is locked read-only** — by **Caption Mode** or by
  **Compare/Merge** — undo, redo and a jump from the list all **refuse and say
  so** in the status bar rather than rewriting the buffer behind the lock.

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

Bookmarks let you mark lines and jump between them. They are never written into
the file itself — a bookmark is a marker over the text, not content. **With a
project open they are remembered between sessions** for the documents that live
in that project (see *Bookmarks that stay put*, below); everywhere else they last
for the session.

- **Ctrl+F2** toggles a bookmark on the current line; a tag marker appears in the
  strip.
- With the mouse there are two targets in the gutter, whichever suits you:
  **single-click the narrow bookmark strip** at the gutter's left edge, or
  **double-click anywhere in the line-number area** to the right of the fold
  chevrons. Both toggle that line's bookmark. (A single click in the line-number
  area still does nothing, so the two never fire together.)
- **F2** / **Shift+F2** jump to the next / previous bookmark.
- The **Navigation** menu — on the **Editor menu bar** above the working area (see
  *The Two Menu Bars*) — holds the same three actions plus **Clear All
  Bookmarks** and **List All Bookmarks**.

Both mouse gestures work in **every** editor that has a gutter — the Raw XML
editor, **Edit XSD** / **Edit AutoXSD**, either read-only **DDL Explorer**, an open
**DDL object editor tab**, an open **PHP file tab** (see *Editing PHP Files*),
the **Sandbox SQL** console (see *The Sandbox*), and the **Edit code…** dialog.

**In Caption Mode the Navigation menu's bookmark entries are switched off** — all
five of them, and with them **Ctrl+F2** / **F2** / **Shift+F2** — because the Raw XML editor
they would act on is read-only for as long as that mode lasts. (While the Caption
Management tab itself is in front, the entire Editor menu bar is hidden anyway;
the five stay disabled even if you step back to Raw XML without leaving the
mode. It is the **entries** that are switched off, not the menu: its
Compare/Merge commands are untouched, because a comparison loaded while you edit
captions is still navigable.) **The gutter still works**: clicking the bookmark strip or double-clicking
a line number sets and clears bookmarks exactly as usual, since a bookmark is
only a marker over the text and does not depend on being able to edit it. Leaving
Caption Mode restores the entries and the shortcuts.

The **Navigation** menu and its shortcuts follow the tab you are working in: with
the **Edit XSD** (or **Edit AutoXSD**) tab active they act on the schema editor,
with either **DDL Explorer** tab, an open **DDL object editor tab**, an open **PHP
file tab**, or a generated **draft tab** active they act on that tab's own
editor, and on any other tab —
including the **Sandbox SQL** console, whose buffer is a scratch pad rather than
a document — they act on the **Raw XML** editor. Using them never switches tabs
on you — a bookmark is always set or found in the editor you are already looking
at.

The **Edit code…** dialog has the same bookmark strip, but as a separate dialog
it is out of the Navigation menu's reach: there you set and clear bookmarks with the
mouse, in the gutter. Each editor keeps its own set.

### Bookmarks that stay put

**When a local DDL-versioning project is open** (see *Local DDL-Versioning
Projects*), bookmarks survive closing and reopening a document, discarding its
changes, and
restarting the app. That covers the three editors whose documents are real files
inside the project:

- the **Raw XML** editor (the project's `.pgtp` working copy),
- every **DDL object tab** (its `ddl/*.sql` file),
- every **PHP file tab** whose file lives inside the project folder.

Nothing is asked of you: a bookmark you set is written out a moment later, and put
back when that document loads again. If a document has since become shorter, the
bookmarks past its new end are quietly left out instead of landing on the wrong
line.

**With no project open, bookmarks behave exactly as they always did** — they live
for the session and are cleared whenever a document is loaded into an editor.
Nothing is written anywhere.

Four editors keep session-only bookmarks even inside a project, because they have
no file in it to remember them against:

- the **Edit XSD** and **Edit AutoXSD** editors — their schema files live with the
  app's own settings, not in your project;
- either read-only **DDL Explorer** buffer, which is a snapshot of a database
  rather than a file;
- **draft tabs** generated from a database table (see *Database/XML Coherence*),
  which are saved nowhere by design;
- the **Edit code…** dialog, which is a window onto a fragment of the XML.

A PHP file you opened from somewhere outside the project folder is in the same
position: there is no project-relative place to record it, so its bookmarks are
session-only.

### List All Bookmarks

**Navigation ▸ List All Bookmarks** writes the **active editor's** bookmarks into
the **Findings** tab in the left dock (see *Where Output Appears*) as one row per
bookmarked line, prefixed **`[Bookmark]`** and showing the line number with a
preview of the text. **Click a row to jump to that line.** The tab opens and
focuses itself — a command whose whole output is rows in a hidden tab would
otherwise look like it did nothing — and it always leaves at least one row
behind, saying *no bookmarks in …* when there are none, so silence never reads as
"clean".

It is the active editor only, like every other bookmark command, and it never
switches tabs on you. Each listing **replaces whatever was in the Findings tab**
— a previous bookmark listing, or a **Find All** result — because the tab answers
one *"where do I want to go next?"* question at a time. The bottom dock's
**Messages** and **Activity Log** tabs are untouched by it.

**It is a snapshot, not a live view.** Toggling a bookmark after you asked for the
list does not update the list — ask again. (Loading a new document does clear the
rows, since the bookmarks they described are gone.)

**Rows from a read-only DDL Explorer buffer jump like any other**, into that
Explorer's own viewing pane — and into the right one of the two, because each row
carries the Explorer it was listed from. Only rows from **draft tabs** are listed
and **do nothing when clicked**: a draft has no click-through route, and sending
you to a plausible-looking line in a different document would be worse than not
moving. The *no bookmarks in …* line names which explorer it read —
**the DDL Explorer (Quality)** or **the DDL Explorer (Sandbox)** — so with both
open you can tell the two listings apart.

---

## Find, Replace & Find All

**The Find/Replace bar is always there.** Every editor tab carries its own bar
under the editor, permanently visible and always in its full form — the **Find**
field with **Find Next** and **Find All**, and the **Replace with** field with
**Replace** and **Replace All**. There is nothing to summon and nothing to
dismiss, so the bar never disagrees with what a menu or a shortcut claims about
it, and the editor's height never jumps as it appears and vanishes.

- **Find Next** (**F3**, or the button) steps to the next match, wrapping around
  the end of the document. **F3 works from anywhere in the editor** — you do not
  have to be in the bar.
- **Find All** lists every match as clickable rows in the **Findings** tab in the
  left dock (see *Where Output Appears*), which opens and focuses itself as the
  first row lands. Matches stream in **continuously** so a large file stays
  responsive; while a run is going the button reads **Stop**, and the count
  (**"Found N items."**) is recorded in the **Activity Log**.
- **Replace** replaces the current match and moves on; **Replace All** replaces
  every match and records how many in the Activity Log.

### Reaching the bar from the keyboard

- **Ctrl+F** puts the cursor in the **Find** field, and **Ctrl+R** in the
  **Replace with** field. They only move focus — the bar is already open. Both
  seed Find from your selection, but **only when the Find field is empty**, so a
  stray selection can never overwrite a term you just typed.
- **Escape returns focus to the editor.** It does not hide the bar; there is no
  hidden state left to restore.
- **Ctrl+F does nothing on a tab that has no bar** — the **Manual** and
  **Diff / Merge** tabs. It used to drag you over to Raw XML and search *that*,
  which was never what anyone meant by pressing Find on another tab.

> **Find All and Replace All no longer have shortcuts.** `Ctrl+Shift+F` and
> `Ctrl+Alt+Return` are gone — use the bar's buttons, which are now always in
> front of you. Both commands are broad and worth a deliberate click: Find All
> fills the Findings tab, and Replace All rewrites the whole document.

### Which document you are searching

Each bar searches **its own tab's document**, and the keys belong to the tab that
owns the bar, so there is never any doubt about where a search landed. The tabs
with their own bar are the **Raw XML** editor, **Edit XSD** / **Edit AutoXSD**
(see *Schema Tools*), both **DDL Explorer** tabs, every open **DDL object editor tab**
(see *DDL Explorer*), every open **PHP file tab** (see *Editing PHP Files*), and
every generated **draft tab** (see *Database/XML Coherence*). The **Caption
Management** tab has its own, differently-shaped bar — see *Caption Management*.

Because a DDL Explorer buffer is **read-only**, only the searching half applies
there: Find, Find Next and Find All work as usual, while Replace and Replace All
have nothing they can change. A DDL object editor tab, a PHP file tab and a draft
tab are fully editable, so every control works there.

**Find All now reports from every tab that has a bar.** It used to be a dead
button on four of them — either DDL Explorer, a DDL object tab, a PHP file tab
and a generated draft fragment — where pressing it did nothing at all. Every one
of those runs now streams its matches into the **Findings** tab like the Raw XML
and Edit XSD bars always did, **and every one of those rows is clickable** —
including the ones found in a **read-only DDL Explorer** buffer, which land in
that Explorer's own viewing pane. The one caveat the Findings tab still states is
the **draft fragment**: a draft has no click-through route, so its rows are
listed but inert, because sending you to a plausible-looking line in another
document would be worse than not moving.

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
- **Ctrl+Shift+B** — select the enclosing bracket span. The dialog has no menu
  bar of its own, so this is the key rather than a **Select** menu entry — and
  for the same reason it is the one place the key **cannot** be changed by
  rebinding **Select ▸ Select Enclosing Block** (see *Keyboard Shortcuts ▸
  Changing a shortcut*).
- Standard **Ctrl+C / Ctrl+V / Ctrl+X**, and the three line-editing keys
  **Ctrl+D** / **Ctrl+K** / **Ctrl+U** (see *Keyboard Shortcuts*).
- **A mode indicator under the editor**, and **Command mode** — this dialog has
  the same **Escape**-entered command vocabulary every other editable editor has
  (see *Editing Modes: Edit mode and Command mode*). It is the one surface where
  **Escape** also leaves that mode, and the chip is how you can tell which mode
  you are in.
- **OK and Cancel are the buttons, plus Return and a double Escape.** This dialog
  used to accept on **Ctrl+S** and cancel on **Ctrl+W** — the last two places
  either chord meant anything. Both are gone: **Ctrl+S** is unbound app-wide
  because saving is a named **Deployment** entry (see *Getting Started ▸ Saving,
  closing, discarding*), and **Ctrl+W** went with it on the same day it stopped
  closing files from the File menu. Nothing became unreachable — press **OK**
  or **Return** to hand the code back, and **Cancel**, the window's close button
  or **Escape twice** (once into Command mode, once to cancel) to drop it.

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

- **File ▸ Open PHP File…** — the entry sits right below **Open…**, above
  the project actions, because it *is* an open gesture. You can **select several
  files at once**; each one opens as its own tab. The dialog offers PHP file
  types first (`.php`, `.phtml`, `.phps`, `.inc`), then common text types, then
  **All files (*)** — the filter is a convenience, not a restriction.
- **Drag files onto the window** — drop one or several and they open the same
  way. Drop onto the tab bar or a dock rather than straight into an editor: an
  editor accepts a dropped file as *pasted text*, which is the text widget's own
  behavior and not something the editor overrides.

The **Activity Log** records each open as `Opened <path>`. The tab is labelled with
the bare file name plus the familiar `" *"` marker once you edit it, and its
tooltip shows the full path — which is what tells two folders' `index.php` apart.

**Opening a file that is already open focuses the tab you already have** instead
of reloading it from disk. That is deliberate: a second Open must never be able
to throw away edits you haven't saved yet.

A dropped **`.pgtp`** is not treated as text — it goes to the normal project-open
path, chooser dialog and all (see *Getting Started ▸ Opening a project*).

### Why a file is sometimes refused

Dropping a file is a gesture you can make by accident, so a drop is classified
rather than trusted. When something can't be opened, the **Activity Log** says
which file and why — never a silent no-op:

- **a folder, or a file that can't be read** — nothing to open.
- **a binary file** (anything with a NUL byte near its start) — opening a JPEG as
  "PHP source" and letting your next save write the mangled result back is data
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
  **Select ▸ Select Enclosing Block** (**Ctrl+Shift+B**) to select the enclosing
  bracket span. **Expand Selection** and **Shrink Selection** are not offered
  here — PHP has no plpgsql structure to climb; see *The Two Menu Bars*.
- Its **own, permanently visible Find/Replace bar** — **Ctrl+F**, **Ctrl+R** and
  **F3** act on *this file*, never on the Raw XML, and Replace All is the bar's
  own button. **Find All** works here too, listing this file's matches in the
  **Findings** tab (see *Find, Replace & Find All*).
- **Ctrl+Z / Ctrl+Y undo and redo only this tab's own edits.** They never reach
  the project's Raw XML history, exactly as in a DDL object editor tab.
- **No fold chevrons yet.** The gutter has the folding machinery, but nothing
  computes fold regions for PHP in this version, so the chevron column stays
  empty here.

### Saving and closing

- **Deployment ▸ Save PHP File** — the only entry the Deployment menu shows while
  a PHP tab is active (see *The Deployment Menu*) — writes **that file**,
  straight back to where it came from, in UTF-8 and keeping the line endings the
  buffer holds. The **Activity Log** records `Saved <path>`; if the write fails, a
  **Save Failed** dialog shows the reason and the tab stays marked as changed.
- **Ctrl+S does nothing here either.** A PHP tab used to have a Ctrl+S of its
  own, and it was removed with all the others: a save key that works on this tab
  and silently writes the wrong file on the next one is worse than no save key at
  all.
- **There is no Save As for a PHP tab** — a PHP tab saves where it came from or
  not at all.
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
the same kind of gesture as **Parsing ▸ Validate Project** one tier down: this
file rather than the whole project. All three entries — **Lint Current File**,
**Lint on Save** and **Locate PHP Linter…** — sit together on **Tools**,
directly under **Manage Captions…**. They deliberately stayed together when
Validate Project moved to the Editor menu bar: splitting the three across two
bars would be worse than either home.

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

Lint findings land in the bottom dock's **Messages** tab (see *Where Output
Appears*),
each row prefixed **`[Lint]`** so you can tell them apart from the `[Validate]`
and `[Check]` lines accumulated beside them. **Click a finding to jump to it** —
the right PHP tab is focused and the caret is placed on that line. Each lint run
opens its own dated block, so a previous run's answer is still there to compare
against.

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

Enter with **Tools ▸ Manage Captions…** or from a tree node's **See … in Caption
Mode** action.
While in the mode, the **Raw XML** tab stays visible but **read-only**, and the
mode indicator — in the toolbar and the status bar alike — appends **· Caption**
to the session's mode, so you can always see why editing is refused (see *The
Status Bar ▸ The mode indicator*). Leave the mode with the **Exit** control to
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

- **Ctrl+G** — or right-click ▸ **Go to line in XML** — jumps from the selected
  row to that line in the Raw XML editor. The chord works **from anywhere in this
  panel, including its Find field**, so you can search for a caption and jump
  straight to its line without leaving the field; it does nothing outside the
  panel. (The context-menu entry deliberately carries no shortcut of its own — one
  gesture, one key.)
- **Copy / Paste** work across rows, including multi-line selections, so you can move
  values between rows or in and out of a spreadsheet. **Ctrl+C** and **Ctrl+V**
  belong to the **grid**; pressed while the cursor is in the Find or Replace field
  they copy and paste that field's text, as they would anywhere else.

### Filtering

- **Header filters** — click a column header to filter by its values, Excel-style.
  A **search box** narrows the checkbox list as you type and unchecks values that no
  longer match, so you can zero in on a large set quickly. A filtered column keeps a
  **▼** marker in its header, so you can always see which columns are narrowing the grid.
- **Preset filters from the Project Tree** — a **See … in Caption Mode** action (for a
  table, a detail's table, or a single column — see *The Project Tree*) narrows the
  grid to just that scope.
- **Clear all filters** — available from the right-click menu, from the
  active-filter banner's own **Clear** button, and from the Find/Replace bar's
  **Clear filter** button. All three clear every filter mechanism at once: header
  filters, the find pattern, and any preset filter.

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

### The live Find/Replace bar

The caption grid has its own **permanently visible** Find/Replace bar under the
grid — the one place caption searching, filtering and bulk replacing happens, and
the quickest way to see what a bulk replace would do before you commit to it. It
carries:

- a **Find** field and a **Replace with (live)** field;
- a **Search Mode** list — **Normal (plain string)**, **Extended** (escapes like
  `\n`, `\t`, `\0`, `\xNN`) or **Regular expression** — and a **Match case**
  toggle;
- **Filter**, which narrows the grid to the matching rows, and **Clear filter**,
  which drops the find filter, every column filter *and* any preset row filter at
  once;
- a **scope** list and **Replace All** (below).

**Ctrl+F** and **Ctrl+R** focus the Find and Replace-with fields while you are in
Caption Management, and **Escape** hands focus back to the grid. Right-click the
grid ▸ **Focus Find / Replace bar** does the same as Ctrl+F. Nothing shows or
hides the bar, because it is always there.

> **The old Tools ▸ Caption Filter… dialog is gone.** It was a second, modal copy
> of everything this bar does, and the two could disagree about what was filtering
> the grid. The bar does all of it, including the project-wide replace the dialog
> was needed for.

**Replace is live.** Every keystroke in either field, and every change of mode or
case sensitivity, immediately recomputes the proposal and writes it into the **New
Value** column of the rows currently in scope. Nothing in your XML is touched: New
Value is still only a proposal, and it takes the usual explicit apply to turn it
into text.

Because the preview is recomputed from scratch rather than piled up, it is fully
reversible — **clearing the Find field puts every row's previous New Value back**,
so a half-typed pattern leaves no debris. An invalid regular expression is
reported on the bar's own inline error line, never as a dialog, and the preview is
rolled back before you see the message.

**Replace All, and its scope.** The list beside the button chooses what Replace All
covers:

- **in filtered results** (the default) — the rows the grid is currently showing,
  which is exactly what the live preview has been proposing all along.
- **in all project** — every caption in the project, including rows the current
  filters hide.

**The scope list only affects Replace All.** Changing it never re-runs the live
preview, so no keystroke can ever propose a rewrite of every caption in the
project; going project-wide is always a button you pressed. Replace All also
*commits* the preview: from then on those New Values are ordinary, hand-editable
proposals rather than a reversible preview.

**Filtering is deliberately not live**: it stays behind the **Filter** button. The
live replace acts on the rows the grid currently shows, so letting the filter
change under your fingers at the same time would make the scope of the proposal
impossible to read. Focusing the bar seeds Find from whatever pattern is already
narrowing the grid — but only when the field is empty, so it never overwrites what
you typed.

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
through the **Schema** menu, which has exactly six entries: **Edit XSD**,
**Edit AutoXSD**, **Verify XSD**, **Export XSD**, **Import XSD**, and
**Restore Bundled Curated Schema…**.

Alongside it, the editor still **auto-learns** from every project you open:
**File ▸ Open** scans the file and writes what it finds to a separate reference
file, `learned.xsd`, announcing discoveries with `[Schema]` lines in the
**Activity Log** (`NEW ELEMENT`, `NEW ATTRIBUTE`, `NEW ATTR VALUE`, …) — they are
a record of what the app learned while opening your file, not a check you asked
for, so they belong in the journal. Learned data **never
appears in completion** — when something new looks worth keeping, open it with
**Schema ▸ Edit AutoXSD** (see *Comparing against the auto-learned schema*),
find it, and add it to `curated.xsd` by hand.

On first run, when you don't yet have a `curated.xsd`, the app **seeds** it by
copying the curated schema bundled with the editor (**Curated v1.3**, a real
hand-commented starting schema). The seed happens only when the file is absent —
`curated.xsd` is hand-owned, so the app never overwrites your edits behind your
back. (If the bundled schema isn't packaged for some reason, the app falls back
to generating a starter schema from your learned data, preserving any value
labels.)

> **There are two `curated.xsd` files, and knowing which is which saves a lot of
> confusion.** One is **bundled inside the application** and never changes; the
> other is **your copy in the app's data folder**, written once at that first-run
> seed and hand-owned from then on. **Everything in the app reads your copy** —
> completion, hover, the *Add attribute* menu, the Properties labels, **Edit
> XSD** — and the bundled one is never re-read once your copy exists. So if your
> copy gets emptied, truncated or broken by a hand edit, the schema feed stops
> even though a pristine schema is sitting inside the app, unused. **Schema ▸
> Restore Bundled Curated Schema…** (below) is the way to put the bundled one
> back.

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
center area — a full editor with its own permanently visible Find/Replace bar
(Find, Find All, Replace, Replace All, and Ctrl+F / Ctrl+R / F3 acting on *this*
document). The tab keeps its own unsaved-changes marker
(`Edit XSD *`), and **Deployment ▸ Save XSD** writes it — the one entry the
Deployment menu offers while this tab is active (see *The Deployment Menu*). It
is only ever the schema: the project's own save entries belong to the Raw XML
tab, so neither can be confused for the other.

Click the tab's **✕** to close it and return to Raw XML. With no unsaved edits
it closes right away; with unsaved edits it prompts you to **Save**,
**Discard**, or **Cancel** first — the same prompt used when switching between
Edit XSD and Edit AutoXSD (below) or closing the app with unsaved schema edits.

Saving the curated schema re-parses it and refreshes completion, hovers, and
Properties labels **immediately**. If the XML is malformed, your text is still
written to disk (nothing you typed is lost), the last good schema stays in
effect, and a `[Schema]` line in the **Activity Log** reports the parse error.

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
enclosing element's type definition, and otherwise tells you in the Activity Log.

### Verifying

**Schema ▸ Verify XSD** checks the schema against the dialect rules — duplicate
enumeration values, `label` in the wrong place, `sums` on the wrong element,
unknown base types, unresolvable type references, and the like. Each finding is a
clickable `[Schema] VERIFY` line in the bottom dock's **Messages** tab that opens
the XSD tab at the offending line, and each run gets its own dated block there
(see *Where Output Appears*). Verify findings are the one kind of `[Schema]` line
that lands in Messages rather than the Activity Log, because they are a check you
asked for. It checks **whichever schema the tab currently holds** —
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
  text and the Activity Log says so; the import's own verification findings land
  in the **Messages** tab like any other Verify run.

### When the schema doesn't load

If your `curated.xsd` cannot be read, the app says so instead of quietly running
without a schema — and it always **names the file it tried**, since that is the
whole question when two copies exist:

- **The file is missing.** A `[Schema]` line in the **Activity Log** gives the
  full path and states that completion, hover and the Properties labels have no
  schema until it is restored, pointing at **Schema ▸ Restore Bundled Curated
  Schema…**.
- **The file is broken, but a schema is still loaded.** This is the mild case —
  you saved half-typed XSD text, and the last good schema stays in effect, so
  completion keeps working. You get one `[Schema]` **Activity Log** line with the
  parse error and the path, and nothing interrupts you.
- **The file is broken and nothing is loaded.** Completion, hover and the
  Properties labels are running against nothing, so besides the Activity Log line
  a **Curated Schema Not Loaded** warning box appears, naming the file, quoting
  the parser's error, and offering both ways back: fix the file in **Schema ▸
  Edit XSD**, or replace it with **Schema ▸ Restore Bundled Curated Schema…**.
  You are told **once** — reopening five more projects with the same broken file
  will not put the box up five more times. The next successful load arms it
  again.

### Restoring the bundled schema

**Schema ▸ Restore Bundled Curated Schema…** — the last entry on the Schema menu,
and the only in-app way back from a `curated.xsd` you broke by hand. It has **no
keyboard shortcut**: it is a deliberate, rare, destructive recovery step.

It asks first, in a **Restore Bundled Curated Schema** box that names the exact
file it will replace, says which bundled version it will write, and warns that
*every hand edit in that file will be DESTROYED*. Say **No** and nothing at all
happens. Say **Yes** and the app copies your current file aside as
`curated.xsd.bak`, writes the bundled schema over it, and re-parses it right away
so completion, hover and the Properties labels come back without a restart. If
the **Edit XSD** tab is open on the curated schema, it is reloaded with the
restored text and its unsaved marker cleared — any unsaved edits in it are
replaced, and the **Activity Log** line recording the restore says so.

This is the one sanctioned exception to "the app never overwrites your
`curated.xsd`": the rule still holds everywhere else, including at startup, and
is broken here only because you asked for it by name and confirmed a prompt that
spelled out the cost. If the build you are running carries no bundled schema at
all, you get a **No Bundled Schema** box instead and your file is left untouched.

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
**DDL Explorer (Quality)**) finds none configured while a project is open, it
points you at Project
Settings with a note in the **Activity Log** rather than opening the
now-meaningless standalone dialog.

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
close, or **File ▸ Discard Changes**, leaves them in place). After **Tools ▸ Reparse Raw XML
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
  occurrence of its `tableName=`/`fieldName=` token in the **Findings** tab (see
  *Where Output Appears*) and seeds the Find bar, so **F3** steps through them.
  When there is genuinely nothing to find, the **Activity Log** says which token
  it looked for and what that
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
tab is a full XML editor with highlighting **and its own Find/Replace bar**, so
you can search and rework the fragment before copying it out. **Find All** works
there and lists its hits in the **Findings** tab, where they are listed but inert
when clicked — a draft has no click-through route (see *Find, Replace & Find
All*). **Ctrl+Z** and **Ctrl+Y** undo and redo your edits to the draft, keystroke
by keystroke, and never reach the project's snapshot history. It has **no save
path and no unsaved-changes concept at all**, which is why
its **✕** closes it immediately with no prompt — there was never anywhere for the
text to be saved to, so a warning would be about nothing.

If your project already contains that `fileName`, or already references that
table, you get an **Activity Log note** saying so — *"rename it in the draft before
pasting"* — and the draft opens regardless. Since nothing is inserted
automatically any more, a name collision is only a problem at the moment you
paste, which the app cannot see; so this is a heads-up and never a block.

These actions work from the schema captured by the last coherence run; if that
schema is no longer available, the Activity Log asks you to run **Database/XML
Coherence** first.

---

## DDL Explorer

The DDL Explorer shows a database's schema and server-side code — every table,
view and materialized view, and every function, procedure and trigger — inside
the editor. There are **two** of them, one per
database you work against, and each is a checkable toggle on the **Database**
menu:

- **Database ▸ DDL Explorer (Quality)** browses the quality database — the
  target connection your project (or your standalone `.pgtp`) is checked
  against. This is the explorer you author in.
- **Database ▸ DDL Explorer (Sandbox)** browses the open project's own sandbox,
  so you can see what is actually in the database you have been applying your
  edits to. It is **browse-only**, and it appears only when a project with a
  sandbox is open — see *The Sandbox Explorer, and how it differs*, below.

The Quality explorer needs only a database connection: you can use it with **no
`.pgtp` file open at all**. If no connection is configured yet: in projectless
mode, **Connection Setup…** opens automatically — save a connection, then toggle
the explorer again; with a local DDL-versioning project open, an **Activity Log**
note points you at **Project Settings…** instead (see *Database/XML Coherence ▸
Connecting* and *Local DDL-Versioning Projects*).

Turning either one on fetches that database's whole object set — tables, views
and materialized views as well as every routine and trigger — and reveals **its
own** two tabs at once, both labelled with the database they show, so two open
explorers are never confusable:

- **Center — DDL Explorer (Quality)** / **DDL Explorer (Sandbox)**: every
  object's DDL in a single **read-only**,
  SQL-highlighted buffer. Each object is preceded by a banner comment (e.g.
  `-- FUNCTION public.foo(integer) --`, `-- TABLE pr.orders --`) so you can
  always tell where you are.
  The buffer is a live snapshot of the database and cannot be edited — see
  *What the read-only buffer holds*, below, for what is in it and which part of
  it is reconstructed rather than original.
- **Left dock — DDL Objects (Quality)** / **DDL Objects (Sandbox)**: a tree of
  the same objects, grouped from two
  angles, with a **name-filter bar above it** (*Filtering the object tree by
  name*, below). Under **Tables**, **every table, view and materialized view in
  the connected schema is listed** —
  tables that own a trigger list those triggers nested underneath them; tables
  with no triggers appear as plain entries. Every table also carries
  **`Columns  (N)`**, **`Constraints  (N)`** and **`Indexes  (N)`** groups.
  Under **Functions & Procedures**,
  each function or procedure lists the triggers that call it. A trigger
  therefore appears in **both** places — either entry points at the same
  definition. **Click any item that has DDL** — a table, a view, a column, a
  constraint, an index, a routine, a trigger — to jump **that explorer's own**
  DDL buffer straight to it.

Everything from here up to *The Sandbox Explorer, and how it differs* describes
both trees and both buffers. The sections after that one — editing objects,
creating them, and altering a table — belong to the Quality explorer alone.

### Reading the DDL Objects tree

Under **Tables**, each table is listed as `schema.table`. A table with
triggers shows a trigger count suffix, e.g. `public.orders  (2)`, with those
triggers nested underneath it exactly as before; a table with no triggers
shows the bare `schema.table` label (no count, since it would only ever be
`0`) and has no children. Views and materialized views are listed in the same
branch and read the same way. Widening the branch to every relation means it no
longer omits tables that happen to have no trigger of their own.

Under each table, after its triggers, sit up to three collapsible groups:

- **`Columns  (N)`** — one row per column, written as `name (type)`, for example
  `note (text)`. They are listed in the table's own declared column order, the
  same order the Properties panel uses, so the two surfaces show one table the
  same way round.
- **`Constraints  (N)`** — one row per named constraint, `name [kind]`, where the
  kind marker is **`[PK]`** primary key, **`[FK]`** foreign key, **`[U]`** unique,
  **`[C]`** check or **`[X]`** exclusion.
- **`Indexes  (N)`** — one row per index, `name [U|I] (method)` — **`[U]`** for a
  unique index, **`[I]`** for an ordinary one — for example
  `idx_orders_code [U] (btree)`.

Each group node is only a container: it clicks nowhere and has no right-click
menu, and a group with nothing in it is not shown at all rather than appearing as
an empty `(0)` folder. The column rows also carry *which column* into the **Alter
Table ▸** dialogs when you right-click one (see *Altering a table's columns*,
below). Constraint and index rows are navigational only — right-clicking one
offers nothing but **Reload DDL**.

**In the Quality tree the selected row is highlighted in red** instead of the
ordinary blue, and it stays red whether or not the tree has focus. That is a
marking and nothing more — it changes no behaviour — but it is the tree whose
right-click gestures reach the **real** database, so it is the one that looks
like it. The **Sandbox** tree keeps the normal selection colour, and the
difference between the two is the point. The red follows the Light/Dark theme
like every other colour in the app (see *Appearance & Layout*).

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
Projects*), object rows in the **Quality** tree also carry combinable drift
markers after their other indicators:

- **`*`** — the checked-out local file has edits not yet included in a batch
  deploy.
- **`!`** — the live database has drifted from what was last deployed.
- Both can appear together as **`*!`** — there is no separate third symbol for
  "both."

Both markers are purely informational: they surface disagreement between the
local file, the last deploy, and the live database, but never block anything
by themselves. With no project open, no markers are shown.

### Filtering the object tree by name

A long database's tree is long. The row of controls **above the tree**, in the
left dock, narrows it to the objects whose **name** you are after:

- the **input** (placeholder `Filter object names…`),
- a **match-mode dropdown** — **Contains** (the default), **Starts with**,
  **Doesn't contain**, **Doesn't start with**, **Ends with**,
- a **`Filter`** button and a **`Clear Filter`** button.

Nothing filters while you type: the tree changes when you press **`Filter`** — or
**Return** in the input, which does exactly the same thing. **`Clear Filter`**
empties the box and brings every row back. Pressing `Filter` on an empty box is
not a filter either; it clears, which is why the two negative modes cannot hide
the whole tree by accident.

**Matching is case-insensitive** (there is no Match-case toggle) and it matches
the **bare object name** — `pr.orders`, `pr.recalc`, `pr.orders.trg_audit` — never
the decorated label. The `[F]` / `[P]` / `[T]` routine markers, a trigger's
`[B][D]`, a table's `  (2)` trigger count and the `*` / `!` drift markers are all
invisible to it, so typing `d` finds names containing a *d* rather than every
DELETE trigger.

Non-matching objects are **hidden**, not greyed out. The ancestors of a match
stay visible and expand themselves, so a hit never hides under a collapsed
branch; a matched object shows its **whole subtree** — its columns, constraints,
indexes and triggers — because you asked for the object, not for a filtered view
of its insides.

A filter always announces itself in the banner under the bar:

- `Filtered: name contains “ord” — 7 of 214 objects` while something matches;
- `No objects match the active filter — use “Clear Filter” to see everything.`
  when nothing does — an empty tree always says why it is empty.

**The filter survives a reload.** Re-introspecting an explorer (*Reloading an
explorer*, below) rebuilds the tree and then re-applies the active filter,
including to rows that have only just arrived — the banner is what keeps that
from being a surprise.

> **This bar filters the TREE; the Find bar searches the TEXT.** The DDL Explorer
> has two find-shaped affordances and they answer different questions. This one
> lives in the **left dock above the DDL Objects tree**, says `Filter` /
> `Clear Filter`, and hides tree rows. The **Find/Replace bar** lives in the
> **center tab below the read-only buffer**, says `Find Next` / `Find All`, and
> moves the caret through the DDL text (see *Working in the DDL tab*). Filtering
> the tree never touches the buffer, and finding in the buffer never hides a row.
>
> **The filter has no keyboard shortcut**, deliberately: **Ctrl+F** in this tab
> already belongs to the Find bar over the text pane, and one chord cannot mean
> both. Return in the filter input is as close as it gets.

### Clicking a table: navigation and column properties

Clicking any table node under **Tables** — whether it owns triggers or not —
does **two** things. It jumps that explorer's DDL buffer to the table's
`CREATE TABLE` (see *What the read-only buffer holds*, below), **and** it
populates the **Properties** panel (the same right-hand dock the Project Tree
and the coherence view use, see *Properties*) with that table's full column
list. Each column is shown as **two rows**: a compact identity line — the
column name, its data type, and whether it's nullable (`NULL` / `NOT NULL`) —
followed by a detail line with its default value and comment (an unset
default or comment shows as `—`). Subtle alternating shading pairs each
column's two rows together so they read as one record.

**Clicking one of the table's own column rows does the same two things**, except
that the jump lands on **that column's own line** inside the `CREATE TABLE`
rather than on the table's banner, and Properties shows the owning table's full
column list — so you can inspect a column without collapsing the group you are
working in.

A constraint row jumps to its inline `CONSTRAINT` line, and an index row to its
`CREATE INDEX` statement; an index that only exists to back a PRIMARY KEY,
UNIQUE or EXCLUDE constraint jumps to **that constraint's** line, because that is
the only place it appears in the text (see *What the read-only buffer holds*).

In the **Quality** tree, right-clicking a table node offers **Add Trigger…**
(see *Creating a new trigger, function, or procedure*, below), **Create Table…**
and the **Alter Table ▸** submenu (see *Altering a table's columns*, below). A column row
offers the **Alter Table ▸** submenu alone. **Edit DDL** remains available only on
routine and trigger rows, because it acts on an object's existing definition. The
**Sandbox** tree offers none of these — its right-click menu holds **Reload DDL**
and nothing else (see *The Sandbox Explorer, and how it differs*).

### What the read-only buffer holds

The DDL Explorer buffer holds **every object kind**, in the same order the tree
is grouped: the **relations first** — tables, views and materialized views,
by schema and name — then the **routines and triggers**. Each object is preceded
by its banner comment (`-- TABLE pr.orders --`, `-- VIEW pr.v_open --`,
`-- FUNCTION pr.recalc(integer) --`, `-- TRIGGER pr.trg_audit ON orders --`),
which is what a tree click jumps to and what folding collapses.

- A **table** renders as one `CREATE TABLE` with its columns and its constraints
  **inline**, followed by the standalone `CREATE INDEX` statements and any
  `COMMENT ON TABLE` / `COMMENT ON COLUMN`.
- A **view** or **materialized view** renders as `CREATE VIEW` /
  `CREATE MATERIALIZED VIEW` with the database's own definition of it, exactly as
  PostgreSQL hands it back.
- **No `ALTER` statement appears anywhere in the buffer.** A constraint has no
  statement of its own here; it is a line inside its table's `CREATE TABLE`, and
  that line is where the tree's constraint rows jump.
- **An index that exists only to back a PRIMARY KEY, UNIQUE or EXCLUDE constraint
  gets no `CREATE INDEX`** — PostgreSQL will not let you `DROP INDEX` such an
  index anyway, and the constraint that owns it is already printed. Its tree row
  therefore jumps to that constraint's line, which is the only place it exists in
  this text.

> **A `CREATE TABLE` here is RECONSTRUCTED, not the original statement.**
> PostgreSQL keeps no stored text for a table the way it does for a function, so
> the editor builds the statement from the catalog — columns, constraints,
> indexes and comments — and says so in two SQL-comment lines above every table.
> The first reads `NOTE: reconstructed by PGTP Editor from pg_catalog (columns,
> constraints, indexes, comments)`; the second, `this is NOT the original CREATE
> statement, and it does not cover table inheritance or partitioning.`
>
> Read that as written, and read it as a **drawn boundary rather than a to-do**:
> **table inheritance and partitioning are not reproduced**, so their absence
> from the text is not evidence of their absence from the database. Nothing is
> ever guessed — a partitioned table renders as the columns and constraints that
> were actually read, never with an invented `PARTITION BY`. The notice sits per
> table rather than once at the top of the buffer, because a tree click drops you
> into the middle of the text and a notice you scrolled past is a notice you
> never saw.
>
> **Identity and generated columns are reconstructed**, and the notice no longer
> lists them: an identity column renders its `GENERATED ALWAYS AS IDENTITY` /
> `GENERATED BY DEFAULT AS IDENTITY` clause, and a stored generated column its
> `GENERATED ALWAYS AS (…) STORED`. A **`SERIAL` column renders the way the
> catalog holds it** — `integer … DEFAULT nextval('…'::regclass)`, never the word
> `SERIAL`. That is deliberate: `SERIAL` is shorthand for *integer + sequence +
> ownership*, so writing it back would mean guessing which sequence feeds the
> column, and the spelling you see names the actual one. What is *not* emitted is
> that sequence's own `CREATE SEQUENCE`, which is a separate catalog object.
>
> **Views carry no such notice**, and that is deliberate: their body comes back
> from the database verbatim, so there is nothing incomplete to warn about.

Because these objects are here to be **read**, right-clicking inside one of them
in the **Quality** buffer does not offer **Edit DDL** — instead it shows a
greyed-out line saying why, e.g. *"Tables are read-only here — change one with
Alter Table ▸"*, with the matching sentence for a view, a materialized view, a
column, a constraint or an index. A refusal you can read beats a menu entry that
silently isn't there. In the browse-only **Sandbox** buffer neither the entry nor
the sentence appears, since nothing there is editable in the first place (see
*The Sandbox Explorer, and how it differs*).

### Working in the DDL tab

A DDL Explorer buffer is read-only, but it is a real editor view with the same
navigation comforts as the Raw XML editor:

- **Line numbers** in the gutter.
- **Folding per DDL object:** a chevron on each object's banner comment line
  collapses that object's body away, leaving the banner visible — handy for
  skimming a long database's worth of definitions.
- **Bookmarks:** click the bookmark strip at the left edge of the gutter (or
  double-click the line number) to mark a line, or use **Ctrl+F2** / **F2** /
  **Shift+F2** and the **Navigation** menu —
  while this tab is active they act on its editor (see *Bookmarks*).
- **Find:** this tab has its own always-visible Find/Replace bar **below the
  buffer**, so **Ctrl+F**,
  **F3** and its **Find All** button search the DDL buffer itself instead of
  bouncing you to Raw XML. The replace half (**Ctrl+R** and the **Replace** /
  **Replace All** buttons) is inert here, since the buffer is read-only. This is
  the bar that searches **text**; the one above the tree in the left dock filters
  **rows** (see *Filtering the object tree by name*).
- **Undo says why it cannot run:** **Ctrl+Z** and **Ctrl+Y** answer here with
  *"this buffer is read only — there is nothing to undo here"*.
  They are deliberately caught by this tab, because a read-only editor that let
  them past would have them fall through to the window and revert the **Raw XML
  project buffer** — a document you are not even looking at.
- **Ctrl+Shift+R re-introspects this explorer** — see *Reloading an explorer*,
  below.

Clicking an object in a DDL Objects tree scrolls it to the **top** of that
tree's own DDL Explorer tab, so the whole definition is visible below its
banner — a click in the Sandbox tree never moves the Quality buffer, and the
other way round. (The Raw XML editor centers its jump targets instead.) Tab
indentation in this tab is shown
4 characters wide, which keeps `pg_get_functiondef`'s tab-indented bodies
readable.

Close an explorer with the **✕** on its DDL Explorer tab or by unchecking its
own **Database ▸ DDL Explorer (Quality)** / **(Sandbox)** entry — either gesture
hides that explorer's two tabs together, and the menu checkbox always reflects
whether that explorer is currently visible. The **Activity Log**
records how many routines and triggers were loaded, naming which explorer
loaded them; if the fetch fails, it records the error and that toggle unchecks
itself.

### Reloading an explorer

An explorer's buffer and tree are a snapshot taken when it was opened, so after
you apply something to a database — or somebody else changes it — what you are
reading is out of date. **Reloading re-introspects the database**; you no longer
have to close the explorer and open it again.

Three gestures do it, and all three do exactly the same thing:

- **Ctrl+Shift+R**, with the caret in an explorer's read-only viewing pane. The
  chord is **per explorer**: it reloads the one you are looking at, which is why
  it lives on the pane rather than on the window — the caret is what says *which*
  explorer you mean.
- **Right-click ▸ Reload DDL**, offered **anywhere** in either explorer's viewing
  pane and **anywhere** in either **DDL Objects** tree — on any row, on a branch
  root, and on the blank space below the last row. It is a property of the
  connection the tab was filled from, not of the row you clicked, so it never has
  a reason to be absent.
- **Database ▸ Reload DDL**, which reloads the **Quality** explorer. A menu entry
  cannot say which of the two explorers it means, so this one is quality-scoped
  by definition; reload the sandbox from its own pane or tree.

**Nothing of yours is lost.** A reload replaces the read-only buffer, the tree,
its drift markers and the completion catalog. **Open, editable DDL object tabs
keep their documents** and their unsaved-changes markers — a reload never reloads,
marks or closes them, exactly as re-running the explorer toggle never did.

**It really re-reads the database**, rather than redrawing what was already
fetched — serving the gesture from the cache would answer it with the very data
the gesture exists to replace. So it costs a round trip, and a failure reports
itself the same way opening the explorer does.

**Reload DDL carries no keyboard shortcut of its own on the menu or in either
context menu.** `Ctrl+Shift+R` on the viewing pane is the gesture's one keyboard
host — the app's standing rule that a gesture has exactly one — which is also why
the chord cannot be reassigned to something else (see *Keyboard Shortcuts ▸ What
cannot be rebound, and why*).

### The Sandbox Explorer, and how it differs

The quality database is easy to look at; the sandbox you have been applying your
edits to used to be invisible. **Database ▸ DDL Explorer (Sandbox)** closes that
gap: it browses the open project's sandbox with the same tree, the same read-only
buffer, and the same navigation as the Quality explorer, so you can read back
what your applies actually left in there.

**Both explorers can be open at the same time**, side by side in the tab bar,
and they are wholly independent: each fetches over its own connection, each
tree navigates only its own buffer, and closing one leaves the other exactly as
it was. The two object sets are genuinely allowed to differ — that difference is
usually the very thing you opened the Sandbox explorer to see.

**Opening it does not need a sandbox session.** Browsing is a read, and reads
are not gated — a session is about *writing* to the sandbox (see *The Sandbox*).
So this explorer works even when the project's session could not be opened, and
losing a session never closes it. If the sandbox cannot be reached — it was destroyed, or its server is down — the
toggle springs back and the **Activity Log** says *DDL Explorer (Sandbox) failed*
followed by the database's own reason, rather than leaving you with an empty
tree that reads as an empty database.

**The entry is there only when it means something.** With no project open, or
with a project that has no sandbox configured, **DDL Explorer (Sandbox)** is not
on the Database menu at all — absent rather than greyed out, like every other
gesture in the app you cannot use. It appears the moment such a project opens,
and also when you give a project a sandbox later by filling in the sandbox
connection in **File ▸ Project Settings… ▸
Connections**. Closing the project takes the entry away again **and hides its two
tabs with it** — a tree still showing a closed project's sandbox would be
describing something you are no longer working on.

**The sandbox tree is browse-only.** It has no **Edit DDL**, none of the
creation entries (**Add Trigger…**, **Create Table…**, **New
Function/Procedure…**), and no **Alter Table ▸** submenu; right-clicking anywhere in it offers **Reload DDL**
alone, and the sandbox buffer's right-click menu has the reading commands plus
**Reload DDL** but no **Edit DDL** either. Reload is the one exception on purpose:
it only *re-reads* this database, and this is the explorer whose contents you most
want to re-read after applying something (see *Reloading an explorer*). The column
operations are left out
for the strongest form of that reason: they are schema *mutations*, and this
explorer exists to look at a sandbox, never to reshape one from the tree. That is the point of the surface
rather than a gap in it: editing and creating are how you change what will
eventually be deployed, and that pipeline runs through your project and the
quality database. The sandbox is where you **check** that work — a definition
you picked up from the sandbox would be a copy of your own experiment, not of
what the quality database has, and treating it as the thing you are editing
would quietly re-base your project's idea of what has been deployed. So you
author in the Quality explorer and read the results here.

Everything that only *reads* still works: clicking any object navigates the
sandbox buffer, clicking a table also fills the **Properties** panel
with its columns, the name-filter bar above the tree filters this tree the same
way, and the buffer's own Find bar, bookmarks, folding and
**Ctrl+Shift+R** reload behave exactly as in the Quality one. Its buffer holds
the same object kinds — tables, views, matviews, routines, triggers — under the
same reconstruction rules (see *What the read-only buffer holds*). Right-clicking
inside a table's DDL here shows no **Edit DDL** entry **and** no read-only
explanation: in a browse-only explorer there is no editing gesture to explain
away.

**The sandbox tree's selection stays the ordinary colour.** Only the Quality
tree's selection band turns red, precisely because that is the tree whose
gestures reach the real database (see *Reading the DDL Objects tree*).

**The sandbox tree shows no `*` / `!` drift markers**, and that is deliberate
too. Those markers mean *"this differs from what was last deployed to
quality"* — a statement about the quality lane. Printing them on sandbox rows
would be showing you quality's drift against a sandbox object, which is a
comparison nobody asked for. The Sandbox tree therefore stays unmarked, and the
markers keep their one meaning in the one tree where it holds (see *Reading the
DDL Objects tree*).

For the same reason, browsing the sandbox never repoints anything the quality
lane owns: the **Ctrl+Space** completion catalog in your open DDL object tabs
keeps describing the quality database (see *Schema-aware completion in the DDL
object editor*).

### Editing a single function, procedure, or trigger

Both of the **Quality** explorer's browsing surfaces double as an entry point
into a dedicated, **editable**
tab for one object at a time. Opening and editing such a tab touches no
database — it is a text editor over the object's current definition. The gestures
in it that *do* reach a database are the two **Run on …** entries on the
**Deployment** menu, which are there for every DDL object tab and state their
reason rather than running when their destination cannot be reached (see *The
Deployment Menu*). Neither entry point exists in the Sandbox
explorer (see *The Sandbox Explorer, and how it differs*).

- In the **DDL Objects (Quality)** tree, right-click a routine or trigger row for
  **Edit DDL**. The row you clicked already names the object, so the entry
  doesn't repeat it. Right-clicking an argument-name child row offers no Edit
  action — only object rows open a tab.
- In the **DDL Explorer (Quality)** tab's read-only buffer, right-click inside a
  routine's or trigger's body for **Edit DDL: `<schema>.<name>(<argtypes>)`** — or
  **Edit
  DDL: `<schema>.<table>.<name>`** for a trigger. There your click landed
  somewhere in a wall of definitions, so the entry spells out which object it
  caught, and two overloads of one name read differently, so you can tell them
  apart before opening either. A click inside a table's, view's, column's,
  constraint's or index's DDL answers with a greyed-out reason instead (see
  *What the read-only buffer holds*).

**There is one editing gesture, and what you can do with the tab it opens comes
from whether a project is open** — never from which words you clicked. (The
second entry this menu used to carry, *Check Out for Versioning*, is gone: it
asked you to choose between two gestures whose only real difference was your
project state.)

- **With a local DDL-versioning project open** (see *Local DDL-Versioning
  Projects*), **Edit DDL checks the object out.** It writes the live definition
  into the project's `ddl/<schema>.<name>.sql` — or
  `ddl/<schema>.<table>.<trigger>.sql` for a trigger — if that file isn't there
  yet, and opens your existing local copy if it is: **your local file is never
  overwritten from the database.** The object joins the project's deploy
  manifest, so the drift markers (`*` / `!`) start tracking it, and **Save in
  Project** writes straight to that file with no dialog.
- **With no project open**, the tab holds the live definition and the first
  **Save in Project** asks you where to put it (see *Saving*, below). You are **not** nagged about the
  missing project: editing one object with just a database connection is a
  supported way to work, so there is no "Project Required" prompt in the way of
  every edit.

**Re-invoking Edit DDL on an object that is already open focuses the existing
tab** rather than opening a second one. There is exactly one tab per object,
ever.

> **One consequence is worth stating, because it otherwise looks like a bug.**
> If you open an object with no project and *then* open a project, that tab keeps
> its "ask me where to save" behavior, and **Edit DDL** on the same object just
> focuses it — it is not promoted to a checked-out file. To get that object under
> versioning, close its tab and open it again.

**Undoing a checkout: right-click ▸ Discard local change.** Beside **Edit DDL**
in the **DDL Objects (Quality)** tree, an object that is currently checked out
also offers **Discard local change**. It appears **only** for an object that
actually has a local working copy — on anything else it is simply not there,
rather than present and dead.

It throws the checkout away, all of it at once: the object's `ddl/*.sql` file is
deleted, its last-deployed reference is dropped (so the `*` / `!` drift markers
stop tracking it), its editable tab is closed, and the object goes back to
not-checked-out. **Any unsaved edits in that tab are thrown away** — you are not
offered a Save first, because throwing those edits away is the whole point of the
gesture. A Yes/No confirmation names the file before anything happens, so nothing
is destroyed by one click.

**It never touches the database.** Unlike **Apply to quality**, this is purely
local: the live object stays exactly as it is, and the confirmation says so in as
many words. It also touches only the object you right-clicked — two overloads of
one name share a folder, and only the one you picked is discarded. Every outcome,
including a cancel, is recorded as a `[Project]` line in the **Activity Log**.

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
shortcuts drive the project's snapshot history on the Raw XML tab. Which history
those keys reach depends on the tab in front of you, and the full routing is in
*Keyboard Shortcuts ▸ Undo and Redo depend on which tab you are in*.

**Saving** is **Deployment ▸ Save in Project**, while this tab is active (see
*The Deployment Menu*). It never touches a database — it only writes a `.sql`
file to disk — and there is **no keyboard shortcut** for it. **Where it writes
depends on how the tab was opened.** A checked-out tab — one you opened with a
project active — already knows its file: every save, from the first one, writes
straight to that `ddl/*.sql` and no dialog appears. In every other case:

- The **first save** opens a normal **Save As…** file picker, prefilled with a
  sensible filename (`schema.name.sql`, or `schema.table.trigger.sql` for a
  trigger) and, when a local DDL-versioning project is active, starting in
  that project's folder (see *Local DDL-Versioning Projects ▸ File dialogs
  default to the active project's folder*). Cancelling the picker just
  cancels the save — nothing is written and the tab stays dirty.
- The chosen path is **remembered**, so every later **Save in Project** writes
  silently to it for the rest of the session.
- **Save as new pgtp** is the `.pgtp`'s own Save As and lives on the Raw XML tab;
  it can never be aimed at this one.

**A brand-new object you created yourself always goes through Save As…**, even
with a project open: it has no live definition to check out, so there is no
checked-out file for Save to aim at. See *Creating a new trigger, function, or
procedure*, below.

**Closing** the tab (its **✕**, or the app's usual close-tab gesture) prompts
**Save**, **Discard**, or **Cancel** if it has unsaved changes, the same as
**Edit XSD**. Choosing **Save** on a tab that has never been saved runs Save
As…; if you cancel that file picker, the tab **stays open** rather than
closing.

**Format Selection** (**Ctrl+Alt+F**, or right-click ▸ **Format Selection**)
reindents the current text selection in place, using the app's SQL formatter.
Both are enabled only when you have a selection. If the
selection can't be safely reformatted (for example, an unbalanced
`BEGIN`/`END` split by the selection boundary), nothing changes: the problem
is reported as a `[SQL]`-prefixed line in the **Activity Log**, and the exact
offending text is underlined in red in the editor until your next edit or
your next format attempt.

> **A `BEGIN TRANSACTION` / `BEGIN WORK` block is not an unbalanced block, and is
> no longer treated as one.** Those `BEGIN`s are transaction control, not a
> plpgsql block, so they need no `END` to close them and a selection containing
> one formats normally — as do `BEGIN ISOLATION LEVEL …`, `BEGIN READ ONLY` and
> `BEGIN DEFERRABLE`, where PostgreSQL lets the noise word be left out. The
> formatter used to count them as unclosed blocks and refuse perfectly valid SQL.

**What it does to your SQL — keyword casing, which
clauses start a new line, the indent unit — is configurable**; see *The
Autoformatter*.

**This tab also carries the five schema-aware editing gestures** — **Ctrl+Space**
completion, **Ctrl+Alt+E**, **Ctrl+Alt+C**, **Ctrl+Alt+J** and
**Ctrl+Shift+Space** — see *Schema-aware completion and gestures in the SQL
editors*, at the end of this chapter.

Re-fetching the explorer — by re-running **Database ▸ DDL Explorer (Quality)** or
by **Reload DDL** (see *Reloading an explorer*) — never touches object
tabs you already have open. They are not reloaded, marked, or closed, even if
the live definition changed underneath them; your in-progress edits are never
silently discarded to resync with the database.

**Where an edit can go: the three destinations.** With this tab active, the
**Deployment** menu names all three of them outright — **Save in Project**,
**Check and commit to sandbox**, **Apply to quality** — and those are the only
places they are offered. None of the three has a keyboard shortcut.

- **Save in Project** writes a file and touches no database (above).
- **Check and commit to sandbox** commits the buffer to the project's sandbox and
  runs the whole validation ladder over it. It needs a live sandbox session, which
  the app opens for you when the project opens — see *The Sandbox ▸ Applying an
  object to the sandbox*.
- **Apply to quality** executes the buffer against the **real** quality database.
  It works with a local project open **and** with no project at all — open a
  `.pgtp`, edit an object, push the fix — as long as a quality connection can be
  resolved. Working without a project, the connection derived from the `.pgtp`
  carries no password (passwords are never read from the XML), so you are asked
  for it once; the answer is kept **for this session only** and written nowhere.

**Apply to quality is guarded, in this order, and refuses out loud rather than
silently:**

1. **A changed signature warns and asks — it no longer refuses.** PostgreSQL
   identifies a routine by schema, name and argument types, so `CREATE OR
   REPLACE` on a buffer you have renamed or whose arguments you have changed does
   **not** replace the object you checked out: it **creates a second object and
   leaves the old one live**. The dialog names both identities — *"You checked out
   `x`, but the buffer creates `y`"* — says that consequence in as many words, and
   then offers to run your SQL anyway. If you say yes, **both objects exist
   afterwards, and dropping the old one is your job** — this editor has no gesture
   that drops an object in the target. So the dialog **hands you the statement to
   run yourself**, spelled out in full (`DROP FUNCTION pr.recalc(integer);`), and
   names where to run it: the **Quality SQL Console** (**Database ▸ Quality SQL
   Console…**), which does reach the target database — see *The Quality SQL
   Console*. Saying no cancels and applies nothing, naming both signatures in the
   `[Check]` line.

   This used to be a hard refusal with no way through, which was worse than it
   sounds: **Check and commit to sandbox** has no such guard and happily ran the
   renamed buffer, so the same edit worked in the sandbox and looked like it had
   succeeded against quality while doing nothing but printing one line you had no
   reason to read. The other branches of the check *are* still hard refusals. A
   buffer whose signature cannot be parsed at all — an `ALTER`, a bare statement,
   an incomplete argument list — is refused with what it would have needed and
   points you at **Deployment ▸ Check and commit to sandbox**, where trying things
   is free. A live identity that could not be read because the database did not
   answer is refused too: an unreachable database never counts as a cleared check.
2. **The buffer must have a green sandbox validation.** Actual findings block.
   What could not be *checked* — no sandbox result for this exact text, a missing
   extension — can be overridden, but only through a dialog that **enumerates
   what was not verified**; there is no generic "proceed anyway".
3. **The confirmation names the object, the database and the host**, and says
   plainly that the apply runs in a transaction but has **no revert snapshot**: a
   successful-but-wrong apply cannot be undone from inside the app.

An empty buffer is refused. Every outcome — applied, rolled back, refused,
cancelled — lands as a `[Check]` line in the **Messages** tab (see *Where Output
Appears*), and an apply that did not commit says so in as many words. The
**Activity Log** keeps its own row for the attempt, with the full DDL and the
full error one click away.

**The tab itself offers no apply affordance — the Deployment menu is the one
place.** There is no row of buttons under the editor and no apply entry in the
right-click menu; the tab's context menu holds only what is genuinely tab-local,
**Format Selection** and **Run in Sandbox Console** (see *Schema-aware completion
and gestures in the SQL editors*), neither of which reaches a database of its
own. One gesture therefore has exactly one name, in exactly one place — the same
name on the menu entry, on its confirmation dialog, on its `[Check]` line and in
the status bar.

**A destination that is not available says so, with what would bring it back.**
Choosing **Check and commit to sandbox** with no reachable sandbox answers *"the
project's sandbox could not be reached, or none is set up yet"* and points at
**File ▸ Project Settings… ▸ Connections**; **Apply to quality** with no
resolvable target names both places a target can come from. Neither is a silent
no-op.

### Creating a new trigger, function, or procedure

Besides editing what the database already has, the DDL Explorer is where you
start a **brand-new** object. Nothing here talks to the database: both dialogs
only collect a few fields and open an editor tab on a generated skeleton, which
you then fill in and save like any other DDL object tab (see *Editing a single
function, procedure, or trigger*, above).

**Add Trigger…** — right-click a **table** or a **view** node under **Tables** in
the DDL Objects tree. (It sits at the top of that node's menu, with the other
creation entry **Create Table…** beside it and the **Alter Table ▸** submenu below
both, because creating a new object is a different act from changing this one;
**Edit DDL** still belongs to routine and trigger rows only.)

**What is offered follows the relation kind**, because PostgreSQL's rules do:

- On a **table**, the timings are **BEFORE** and **AFTER**.
- On a **view**, the only timing is **INSTEAD OF** — which is the standard way to
  make a view updatable, and squarely what this app is for.
- On a **materialized view** the entry is present but **disabled, carrying its
  reason**: *"Materialized views cannot have triggers — PostgreSQL supports none
  on them."* A stated refusal beats a command that vanishes, especially where the
  sibling kinds on the very same branch do offer it.

The
dialog shows the clicked relation as a fixed line — you picked it by right-clicking
it, so it isn't offered again as a field — labelled for what it is, **Table:**,
**View:** or **Materialized view:**. Then:

- **Name** — the trigger's name.
- **Timing** — the timings legal for that relation kind, and no others, so a view
  can never be handed a `BEFORE INSERT` the server would reject.
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
database**; it only gives you correct starting text. Saving works as it does in
any projectless DDL object tab: **the first Save in Project asks you where to put
the file**, even with a project open. A new object has no live definition to check
out, and seeding a checked-out file from a skeleton would tell your project that
a definition had been deployed when no database has ever held it.

With a **local DDL-versioning project** open (see *Local DDL-Versioning
Projects*), a newly created object is nonetheless **registered for versioning
automatically**: it shows up as a pending local change (the `*` drift marker) in
the DDL Objects tree and is picked up by the normal deploy flow. Created with no
project open, it is just an editor tab and a file — unversioned, which is a
supported way to work.

### Altering a table's columns

The DDL Explorer can also **change an existing table**. In the **DDL Objects
(Quality)** tree, right-click a table node — or one of its column rows under
**`Columns  (N)`** — and open the **Alter Table ▸** submenu. It gathers everything
that is **scoped to the table you clicked**, in five groups separated by a line:

- **eight column operations** — the table below.
- **four constraint operations** — **Add Constraint…**, **Add Foreign Key…**,
  **Drop Constraint…**, **Rename Constraint…** — which have a section of their own
  (*Constraints and foreign keys*, next).
- **two index operations** — **Create Index…** and **Drop Index…** (*Indexes,
  comments, and creating or dropping a table*, after that).
- **one comment entry**, and this is the single place the two entry points differ:
  a **table node** offers **Set Table Comment…**, a **column row** offers **Set
  Column Comment…**. The entry always names the thing you actually right-clicked,
  so it can never quietly retarget your click a level up or down.
- **Drop Table…**, alone at the bottom — the one entry that removes the object the
  whole menu is about, kept a separator away from a mis-click on **Drop Index…**.

That is **sixteen entries from either entry point**, differing only in which
comment entry is offered. The grouping is there because "what are this table's
columns?", "…its constraints?", "…its indexes?", "what does it say about itself?"
and "does it exist at all?" are five different questions, and sixteen
undifferentiated entries would read as one long list.

> **The submenu's title names the commonest case, not the generated verb.** Most
> of these emit `ALTER TABLE`, but **Create Index…**, **Drop Index…**, the comment
> entries and **Drop Table…** emit `CREATE INDEX`, `DROP INDEX`, `COMMENT ON …`
> and `DROP TABLE`. They live here because they are scoped to this table, which is
> the question you are answering when you right-click one — and the tab each one
> opens is titled after the statement it actually holds, never after the route you
> took (see *The tab an Alter Table operation opens*).

**Create Table… is the one operation that is not on the submenu**, because it is
not scoped to the clicked table: it creates a new one. It sits at the **top level**
of a table node's menu, beside **Add Trigger…** and above **Alter Table ▸**, and
also on the **Tables** branch root itself — see *Indexes, comments, and creating or
dropping a table*.

The eight column operations are:

| Entry | What it generates |
|---|---|
| **Add Column…** | `ALTER TABLE … ADD COLUMN …` |
| **Drop Column…** | `ALTER TABLE … DROP COLUMN …` |
| **Rename Column…** | `ALTER TABLE … RENAME COLUMN … TO …` |
| **Change Column Type…** | `ALTER TABLE … ALTER COLUMN … TYPE …` |
| **Set NOT NULL…** | `ALTER TABLE … ALTER COLUMN … SET NOT NULL` |
| **Drop NOT NULL…** | `ALTER TABLE … ALTER COLUMN … DROP NOT NULL` |
| **Set DEFAULT…** | `ALTER TABLE … ALTER COLUMN … SET DEFAULT …` |
| **Drop DEFAULT…** | `ALTER TABLE … ALTER COLUMN … DROP DEFAULT` |

> **Generating executes nothing.** Every entry here opens a dialog, and confirming
> that dialog does exactly one thing: it puts the generated statement into an
> ordinary, editable tab. No connection is opened, nothing is sent to any
> database, and nothing about your table changes. **Running the statement is a
> separate, explicit gesture** you make afterwards, from the **Deployment** menu.
> That separation is the whole safety model: you always read the DDL — and can
> edit it — before anything can execute it.

**Where the click lands is the dialog's starting point, not a cage.** Right-click
a **column** row and that column is pre-selected; right-click the **table** node
and you get the same operations with no column pre-selected (the dropdown simply
starts at the table's first column). Either way the dialog states where it
came from on a read-only **From:** line, and both the **Table:** and **Column:**
dropdowns stay changeable — so a dialog you opened from the wrong row is a
correction, not a cancel-and-retry. The dropdowns are filled from the schema the
explorer already fetched; the dialogs never talk to the database themselves.

**Views and materialized views have no Alter Table ▸ submenu**, on the relation
node or on a column. Nearly every entry emits `ALTER TABLE` or `DROP TABLE`, which
the server would refuse on a view, so the submenu is not offered rather than
offered and broken. A handful of its entries *do* have legal view spellings —
`COMMENT ON VIEW`, an index on a materialized view — but the generators behind
them write `TABLE`, so they would still produce the wrong statement; a
view-shaped action set is a separate feature this one does not claim to be. A
view's node still offers the two creation entries at its top level — **Add
Trigger…** (offering **INSTEAD OF** only) and **Create Table…**; on a
**materialized view**'s node, **Create Table…** is the same, while **Add
Trigger…** is replaced by the disabled line saying PostgreSQL supports no
triggers on materialized views (see *Creating a new trigger, function, or
procedure*). A view's **column** row offers no editing gesture at
all (just **Reload DDL**, which is offered everywhere). For the same
kind of reason the whole submenu is **absent in the Sandbox explorer**, which is
browse-only (see *The Sandbox Explorer, and how it differs*).

**The dialogs validate as you type.** **OK** stays disabled until the statement
actually renders, and the reason is shown inline in red — an empty column name, an
empty `USING` clause, an unbalanced parenthesis — rather than as an error box after
the fact. Identifiers are quoted safely, and one that cannot be quoted is refused
inline instead of producing broken SQL.

Two entries are worth a word of their own:

- **Add Column…** collects a **Name**, a **Datatype** (an editable list of common
  types — anything else, `numeric(10,2)`, `integer[]`, `pr.my_domain`, can simply
  be typed), a **Nullable** checkbox, and an optional **Comment**. **A comment
  produces two statements in the tab** — the `ALTER TABLE … ADD COLUMN …;` first,
  then a `COMMENT ON COLUMN …;` — because `ALTER TABLE` has no comment clause.
  That is correct output, not a duplicate: both statements belong to the one
  change and are run together. Leave the field blank and only the first statement
  is generated. Note also that unticking **Nullable** on a table that already has
  rows only succeeds if the column gets a default or the table is empty — that is
  PostgreSQL's rule, and you will hear about it when you run the statement, not
  when you generate it.
- **Change Column Type…** offers an optional **USING:** field, and this is the one
  place the generated DDL genuinely needs your help. PostgreSQL will only change a
  column's type on its own when a suitable cast exists; on real data a change like
  `text` → `integer` **fails outright without a `USING` clause**. Supply the
  conversion expression there — for example `trim(code)::integer` — and it is
  emitted as `… TYPE integer USING trim(code)::integer`. Leave it empty and no
  `USING` clause is generated at all.

**Drop Column…** deliberately generates **no `CASCADE`**: dropping a column that a
view or a constraint depends on will fail loudly, which is the safer default. If
you really want the cascade, type the word into the tab yourself.

### Constraints and foreign keys

The second group of the **Alter Table ▸** submenu holds four constraint
operations. They open from the same two places as the column entries — a table
node or one of its column rows — carry the same click context, and generate text
into the same kind of editable tab: **nothing here runs against a database
either.**

| Entry | What it generates |
|---|---|
| **Add Constraint…** | `ALTER TABLE … ADD CONSTRAINT … PRIMARY KEY / UNIQUE / CHECK / EXCLUDE …` |
| **Add Foreign Key…** | `ALTER TABLE … ADD CONSTRAINT … FOREIGN KEY … REFERENCES …` |
| **Drop Constraint…** | `ALTER TABLE … DROP CONSTRAINT …` |
| **Rename Constraint…** | `ALTER TABLE … RENAME CONSTRAINT … TO …` |

> **There is no "Drop Foreign Key", and that is deliberate.** In PostgreSQL a
> foreign key **is** a constraint, and `ALTER TABLE … DROP CONSTRAINT` is the
> identical statement for every type. A second entry would have generated exactly
> the same SQL under another name. So **Drop Constraint…** is where a foreign key
> goes too — its picker shows each constraint's type, which is how you tell a
> `FOREIGN KEY` from a `CHECK` before dropping it.

**Add Constraint… covers four types, and changes shape with the one you pick.**
The **Type:** dropdown offers **PRIMARY KEY**, **UNIQUE**, **CHECK** and
**EXCLUDE**:

- **PRIMARY KEY** and **UNIQUE** are defined by a **column list**, so you get a
  multi-column picker: one dropdown to start with, a **"+"** to add another row
  and a **"−"** to take one away. **Row order is kept exactly as you arrange it**,
  because a key's column order is semantic. The last row can never be removed —
  no constraint here can be built from zero columns, so that is not offered as a
  state.
- **CHECK** and **EXCLUDE** are defined by an **expression**, so the column picker
  is hidden and an **Expression:** field takes its place — `qty > 0` for a CHECK,
  an element list such as `room WITH =, during WITH &&` for an EXCLUDE. Their
  content simply cannot be expressed as a list of columns, which is why the field
  replaces the picker rather than sitting next to it. **EXCLUDE** additionally
  shows a **Using method:** dropdown (`gist` first, then `btree`, `spgist`,
  `hash`), since an exclusion constraint is built on an index method.

**A constraint name is required**, in both Add dialogs. Postgres would happily
invent one if you left it out — and an invented `orders_qty_check1` is precisely
what makes the **Drop Constraint…** and **Rename Constraint…** pickers unreadable
a month later, when you are trying to find the constraint you mean among a list of
machine-generated names. One field now, to keep those lists legible.

**Add Foreign Key…** collects the constraint name, the **Local column(s)** (the
same "+" picker), a **References table:** dropdown, the **Referenced column(s)**
(a second picker of its own), and optional **ON DELETE:** / **ON UPDATE:**
actions — `NO ACTION`, `RESTRICT`, `CASCADE`, `SET NULL`, `SET DEFAULT`, or
**(none)**, which emits no clause at all. **Changing the referenced table
repopulates its column list** on the spot, so the two halves can never come to
describe different tables. Leaving an action on **(none)** keeps the generated
text quiet about a choice you did not make; Postgres treats it as `NO ACTION`
either way.

**Drop Constraint… and Rename Constraint…** both start from a picker of the
table's **existing named constraints**, each shown with its type and columns —
`fk_customer — FOREIGN KEY (customer_id)`. The list follows the **Table:**
dropdown, so re-picking a table re-reads its constraints. What reaches the
generated SQL is always the bare constraint name, never the descriptive label.

**Drop Constraint… warns, it does not refuse.** Pick the table's **primary key**
and a plain (not red) note appears saying that dropping it also drops the index
behind it, and that Postgres will refuse while another table's foreign key still
references it. Pick any other **UNIQUE** or **EXCLUDE** constraint and the note
says its index goes with it. **OK stays enabled in both cases**, on purpose:
whether some other table still depends on this constraint is a question only the
database can answer at the moment you run the statement, and refusing here would
block the perfectly legitimate "drop the primary key, then add a different one"
you came for. Generating the DDL changes nothing — see the note above.

### Indexes, comments, and creating or dropping a table

Six further operations round out the set: **Create Index…**, **Drop Index…**,
**Set Table Comment…**, **Set Column Comment…**, **Create Table…** and **Drop
Table…**. Each obeys the same rules as everything else in this chapter — the lists
are filled from the schema the explorer already fetched, the dialogs never open a
connection, **OK** stays disabled until the statement actually renders, and
confirming one only puts text into an editable tab.

**Where they are.** In the **DDL Objects (Quality)** tree:

- **Create Index…**, **Drop Index…** and **Drop Table…** are on the **Alter
  Table ▸** submenu of a table node or one of its column rows, in the third and
  fifth groups (see *Altering a table's columns*).
- The comment entry is on that same submenu, and follows your click: **Set Table
  Comment…** from a table node, **Set Column Comment…** from a column row.
- **Create Table…** is *not* on the submenu. It is a top-level entry — beside
  **Add Trigger…** on a table or view node, and on a matview node too (since what
  you create is a table regardless of what you clicked, even where **Add
  Trigger…** itself is refused there), and on the **Tables** branch
  root itself, which is the "make a new one of the kind this branch lists" gesture
  the **Functions & Procedures** root already had. Opened from a node, the new
  table's name is pre-seeded with that node's schema so it lands where you
  clicked; opened from the branch root, which names no schema, the name field
  starts empty.

None of these appears in the **Sandbox** explorer, which is browse-only (see *The
Sandbox Explorer, and how it differs*).

**Create Index…** asks for an index name, one or more columns (the same "+"
picker, order preserved), a **Unique** toggle and a **Method:** dropdown —
`btree` (the default and the right answer for almost every index), `hash`,
`gist`, `spgist`, `gin`, `brin`. The method is always spelled out in the
generated `USING …`, so the statement says what it means instead of relying on
you knowing Postgres's default. The index name is a **bare** name, not
`schema.name`: an index is created in its table's schema, and Postgres rejects a
dotted name in `CREATE INDEX`. The columns are **columns, not expressions** — an
expression index such as `((lower(email)))` has its own parenthesisation rules, so
`lower(email)` is refused here rather than quoted into an index on a column that
does not exist; type it into the tab afterwards.

> **`CONCURRENTLY` is never generated.** It cannot run inside a transaction
> block, and applying generated DDL runs everything in one transaction — a
> checkbox for it would produce text that fails on the way it is meant to be run.
> If you want it, type the word into the tab and run it yourself.

**Drop Index…** is the one entry here that is not about a table: an index is named
in its own right, as `schema.index_name`, and there is no `DROP INDEX … ON table`
in PostgreSQL. So you pick the index itself from a list showing what each one is —
`idx_orders_code — UNIQUE btree (code)`.

> **The list deliberately hides indexes that exist only to back a constraint**,
> and tells you it did. Postgres builds an implicit index for every PRIMARY KEY,
> UNIQUE and EXCLUDE constraint, and then **refuses `DROP INDEX` on it** — the
> constraint has to go instead. Offering those rows would offer a statement that
> cannot succeed; dropping them silently would leave you wondering where the
> unique index you can plainly see in the explorer went. So a plain note names
> each one it left out, with the constraint that owns it, and points you at
> **Drop Constraint…** — remove the constraint and its index goes with it.

**Set Table Comment… / Set Column Comment…** are one dialog in two flavours — the
table's comment, or one column's — chosen by which entry the submenu offered you,
which in turn follows the row you right-clicked rather than a field inside the
dialog.
The existing comment is offered for editing, which is the difference between
changing a description and retyping it from memory. **Leaving the box empty
removes the comment:** it generates `COMMENT ON … IS NULL`, which is the only
spelling PostgreSQL has for "no comment", and an empty box is the only way you
can ask for it. The dialog says so under the field, because "take that comment
off" is a legitimate thing to want rather than an error.

**Create Table…** is a small column builder: one row per column with a **Name**, a
**Type** (the same editable list of common types the column dialogs use — anything
else can simply be typed), a **Nullable** checkbox, an optional **Default**, and a
**PK** checkbox marking it as part of the primary key. **"+"** adds a row, **"−"**
removes one, and the last row cannot be removed. Row order is the created table's
column order. The primary key is emitted unnamed (`PRIMARY KEY ("id")`), because
Postgres's auto-name for it — `orders_pkey` — is the one auto-name that is both
predictable and what everybody already uses.

> **That is everything Create Table… expresses, on purpose.** No foreign keys, no
> `UNIQUE` or `CHECK` constraints, no indexes, no identity/generated columns, and
> no partitioning, inheritance or tablespace. There is no hidden checkbox for them
> — those are exactly what the constraint and index operations above add to the
> table once it exists, and the generated `CREATE TABLE` is editable text before
> anything runs. A builder that tried to cover the whole of `CREATE TABLE` would
> have to guess at how its own fields interact, which is the one outcome this
> whole feature exists to avoid.

**Drop Table…** asks nothing beyond which table, and **there is no "are you
sure?"** — no confirmation dialog, no typing the table's name to unlock the
button. That is the same safety model as every other operation here, stated where
you are most likely to expect a scary prompt: **generating `DROP TABLE` executes
nothing.** The statement lands in an editable tab you can read, change or simply
close, and running it is a separate, explicit gesture. Putting the friction at
generation time would put it where nothing happens and leave it absent where
something does. No `CASCADE` is generated either, so PostgreSQL will refuse
loudly if a view or another table's foreign key depends on the table.

### The tab an Alter Table operation opens

The tab you get is the same editable SQL editor a DDL object tab uses — gutter,
bookmarks, folding, its own Find/Replace bar, **Ctrl+Z / Ctrl+Y** scoped to this
tab alone. It is titled with the statement it holds, e.g. **`ALTER orders`**, plus
the usual `" *"` marker once you edit it; its tooltip — and everything else that
names it, confirmations and `[Check]` lines alike — reads
**`ALTER TABLE pr.orders`**, because that is what it is, rather than dressing a
table up as an object it is not.

**Each generation gets its own tab.** Two ALTERs on the same table are two
different statements, so the second one never quietly replaces the first.

**It behaves differently from an object tab, deliberately, and you will notice:**

- **Deployment ▸ Save in Project opens a Save As… prompt**, every time until you
  name a file, prefilled as `alter_<schema>_<table>.sql` (`alter_pr_orders.sql`).
  An ALTER tab is never *checked out* and never joins the project's deploy
  manifest — no `*` / `!` drift marker will ever speak for it. **The why in one
  line:** an ALTER is a *mutation of* a table, not an object with its own source
  file, so there is no `ddl/<object>.sql` it could be the contents of; writing one
  would put a change where the project expects a definition.
- **Deployment ▸ Apply to quality refuses an ALTER buffer, and says why.** That
  gesture's first precondition reads the object's signature out of the buffer and
  compares it with the live catalog, and an `ALTER TABLE` declares no such
  signature — so the refusal lands as a `[Check]` line saying the signature could
  not be determined and pointing at the reviewable deployment-script path. **The
  intended run path for an ALTER is Deployment ▸ Check and commit to sandbox**:
  try the change where trying things is free.
- **`plpgsql_check` — tier 3 of the validation ladder — does not run here**, by
  design. An ALTER creates no function for it to analyse, so there is nothing for
  that tier to say. Tiers 0, 1 and 2 do run. A check report on an ALTER tab with
  tier 3 absent is the expected shape, not a failure (see *The Sandbox ▸ The
  validation ladder, and the three ways to run it*).

### Schema-aware completion and gestures in the SQL editors

Writing SQL against a database the editor has already introspected should not
mean retyping what it knows. Five keys put that knowledge at the caret:

| Key | What it does |
|---|---|
| **Ctrl+Space** | Completion popup for the name you are typing |
| **Ctrl+Alt+E** | Expand the word before the caret into its plpgsql snippet |
| **Ctrl+Alt+C** | Expand a bare `SELECT` into the column list it implies |
| **Ctrl+Alt+J** | Write the `JOIN … ON …` a foreign key already implies |
| **Ctrl+Shift+Space** | Show the signature of the call the caret is inside |

**They work in the app's editable SQL surfaces only: an open DDL object editor
tab, the Sandbox SQL Console and the Quality SQL Console** (see *The Sandbox ▸
The Sandbox SQL Console* and *The Quality SQL Console*). Each of them is handed
the database catalog the **Quality** explorer already fetched when you connected.
Everywhere else
these keys are not offered — the Raw XML editor, a PHP tab and the **Edit code…**
dialog hold no SQL and have no schema to answer with, and either read-only **DDL
Explorer** buffer cannot be written into (asking anyway there says exactly that:
*"this buffer is read-only"*).

Nothing on this path touches the database. The catalog was fetched once, when
you connected; invoking a gesture never makes a round-trip of its own, and a
browse of the **sandbox** never replaces it — what you complete against is the
database an edit is headed for.

**Every one of these is explicit.** None of them fires as you type; each answers
the key you pressed and nothing else.

**Ctrl+Space — completion.** The same completion idiom as the Raw XML editor's
Ctrl+Space (see *The Raw XML Editor ▸ Schema-aware editing*), applied to live
database names instead of the `.pgtp` XSD schema. It recognizes:

- **Nothing typed yet, or a partial schema name** — the schema names it knows.
- **`schema.`** — the tables in that schema, schema-qualified, narrowed as you
  type more.
- **`schema.table.`** — that table's columns. This is the cascade's third step:
  `hr.` gives you `hr.jobcard`, and `hr.jobcard.` gives you its columns.
- **`alias.`, where the caret's own `FROM` clause binds that alias** — the
  columns of the table it names, so `FROM hr.jobcard jc … jc.` completes. When
  the table was written without a schema (`FROM jobcard j`), nothing here
  guesses a search path; it falls back to reading the text as a plain dotted
  path.
- **`local.`, where the routine you are in declares that local as a
  `%ROWTYPE`** — a `rec hr.jobcard%ROWTYPE` offers `hr.jobcard`'s columns. This
  one is a DDL object tab's; a console buffer is a script being sent rather than
  a routine being edited, so its declarations are not read there.
- **`NEW.` or `OLD.` inside a trigger function that already has a trigger
  attached to it** — that trigger's target table's column names directly. (A
  console buffer is not a trigger body, so row variables resolve to nothing
  there.)
- **`NEW.` or `OLD.` inside a trigger function with no trigger currently
  attached to it** — you are told plainly that no trigger is defined for this
  function, then a **"No Trigger Defined"** picker opens so you can choose which
  table it belongs to; once chosen, its columns complete as usual. That choice
  lives in the current tab for the rest of the session, is **never saved to
  disk**, and is asked again if you reopen the same function later.

**A column row says more than a column name.** Each one reads as the name, then
whatever that column actually carries — its type, `PK`, `→ hr.dept.id` for a
foreign key, `NOT NULL`, its default, its comment — separated by `·`, so you can
tell `id integer` from `id text` at the moment of choosing. Attributes are shown
only when they apply: a nullable column simply says nothing about nullability, so
the ordinary row stays short and the unusual one stands out. **Only the name is
inserted** — the extra text is there to be read, never to land in your buffer.

**Ctrl+Alt+E and Ctrl+Alt+C — the two expansions.**
**Ctrl+Alt+E** expands the word immediately before the caret into its plpgsql
snippet — eight are shipped with the app and **the set is yours to edit** (see
*Snippets*). **Ctrl+Alt+C** expands a bare `SELECT` at the caret into the column
list the statement's own `FROM` implies — the schema-fed flavour of the same
mechanism.

Both are applied as **one undo step**, so a single **Ctrl+Z** takes the whole
expansion back however many pieces it was assembled from. When the expanded text
has placeholders to fill in, **Tab** and **Shift+Tab** walk them; the last one
drops you out and Tab goes back to inserting a tab.

They are SQL-only by design: the snippet set is plpgsql, and an expansion that
dropped plpgsql into a PHP body would be a bug, so in a PHP or JavaScript editor
these keys are left completely alone.

**Ctrl+Alt+J — the JOIN a foreign key implies.**
Put the caret in a `FROM` clause and press **Ctrl+Alt+J**: the editor reads the
tables already in scope, looks at the foreign keys they declare, and writes the
`JOIN … ON …` those keys imply.

- **When exactly one join is possible it is written straight in**, as a single
  undo step, like any other expansion.
- **When several are possible you are offered them, not guessed at.** The same
  completion popup opens, one row per candidate showing the `ON` clause it would
  write, and **nothing is written until you pick one**. Escape leaves the buffer
  untouched.

**Ctrl+Shift+Space — signature help.**
With the caret inside a call, it shows what that routine
expects, as a transient tooltip at the caret. **It inserts nothing** — it is a
question, not an edit.

The tooltip is two lines, or three:

1. the routine's signature;
2. `→` and the parameter you are currently filling in, which is the one thing a
   bare signature line does not tell you;
3. only when the name has more than one overload, which of them you are being
   shown (`(2 of 3 overloads)`). With a single signature that line is left off
   rather than saying *1 of 1*.

**When a gesture has nothing to offer, it says so.** None of these ever fails
silently. The reason arrives in two
places at once: a **tooltip at the caret**, where you are already looking,
because it is answering a key you just pressed — and a **`[SQL]` row in the
Activity Log**, which is still readable a minute later. The reason is specific
(*"'foo' is not a snippet"*, *"writing a JOIN needs a database schema, and this
editor has none"*, *"this buffer is read-only"*), never a generic beep.

---

## Software Settings

**Settings ▸ Software settings… is the one place the app is configured.** It is a
single dialog with a category list down the left and the settings for the
selected category on the right, and it holds **four** panes:

| Pane | What it configures |
|---|---|
| **Snippets** | The trigger words **Ctrl+Alt+E** expands in a SQL editor, and their bodies — see *Snippets*. |
| **Toolbar** | Which commands sit on the Main Toolbar, in which order, with which icons — see *Appearance & Layout ▸ The toolbar*. |
| **Autoformatter** | How **Format Selection** rewrites SQL/plpgsql and XML — see *The Autoformatter*. |
| **Keyboard shortcuts** | The key bound to each menu command, and the keys the app pins — see *Keyboard Shortcuts ▸ Changing a shortcut*. |

**Those four used to be four separate menu entries and no longer are.** **View ▸
Customize Toolbar…**, **View ▸ Customize Shortcuts…**, **Settings ▸ Edit
Snippets…** and **Settings ▸ Autoformatter settings…** are **gone** — not
duplicated, not kept as second doors. Each is the same dialog you already knew,
re-hosted as a pane, with the same controls, the same buttons and the same
behaviour; only the way in changed.

**There are two ways in, and both are the same command.** **Settings ▸ Software
settings…** — the **Settings** menu's only entry — and the third button in the
launcher's **Maintenance** column, which reads `Settings › Software settings`.

**Which makes toolbar and shortcut customization Maintenance-mode gestures.** The
**Settings** menu exists only in Maintenance mode (see *Getting Started ▸
Maintenance mode*), so rearranging your toolbar or rebinding a key now means
entering that mode first, where before you could do it at any time from **View**.
That is deliberate: this is configuring the app rather than using it. As with any
other command, a **toolbar button** you pin to it opens the dialog outside
Maintenance mode too.

**The dialog is non-modal and there is only ever one of it.** It stays beside
your work — which is what lets the **Keyboard shortcuts** pane be open while you
try a key — and asking for it again brings the existing window to the front
rather than opening a second one editing the same settings.

**Each pane keeps its own OK and Cancel, and the dialog itself only has Close.**
That is the one thing worth reading twice:

- A pane's **OK** saves exactly what it always saved, immediately. A pane's
  **Cancel** discards exactly what it always discarded.
- After either, that pane **reloads itself from what is now stored**, so you are
  never looking at a stale scratch copy of something that has moved on.
- **Closing the dialog is never a save.** There is no dialog-level OK, because
  there is no dialog-level state — the four panes disagree about what "apply"
  means and each one is right about itself. Close the window with edits sitting
  unapplied in a pane and they are gone, exactly as closing any one of those four
  dialogs always did.

**Colours are not in here.** Syntax-highlight colours and the app's colour scheme
are not settings this dialog offers, and it says nothing about them; the theme is
still **View ▸ Light Theme** (see *Appearance & Layout*).

---

## Snippets

A **snippet** is a trigger word you type in a SQL editor and expand with
**Ctrl+Alt+E**: type `if`, press the chord, and the word is replaced by a whole
`IF … THEN … END IF;` skeleton with the caret already on the condition. Eight
are shipped with the app, and **the set is yours** — you can edit them, add your
own, delete ours, and send the lot to a colleague.

Expansion works in the editable SQL surfaces only — an open **DDL object editor
tab**, the **Sandbox SQL Console** and the **Quality SQL Console** — for the reasons given in *DDL
Explorer ▸ Schema-aware completion and gestures in the SQL editors*. The whole
expansion is **one undo step**: a single **Ctrl+Z** takes it back.

### The shipped set

| Trigger word | What it inserts |
|---|---|
| `case` | a `CASE WHEN … THEN … ELSE … END` expression |
| `if` | `IF … THEN … END IF;` |
| `ifelse` | `IF … THEN … ELSIF … THEN … ELSE … END IF;` |
| `forloop` | `FOR … IN SELECT … LOOP … END LOOP;` |
| `begin` | `BEGIN … EXCEPTION WHEN … THEN … END;` |
| `raise` | a `RAISE NOTICE` line |
| `cursor` | a cursor declaration |
| `trigfn` | a whole trigger-function skeleton, `$$` body and `RETURN NEW;` included |

**Trigger words are matched without regard to case**, so `case`, `Case` and
`CASE` are one and the same snippet — which is also why two of them can never
coexist in your set.

### Placeholders, and walking them with Tab

A snippet body is ordinary text plus a small placeholder syntax. There are only
four pieces of it:

| In the body | What it means |
|---|---|
| `{{1}}`, `{{2}}`, `{{3}}` … | a spot to fill in, visited in numeric order |
| `{{1:condition}}` | the same, with placeholder text that is inserted and gets selected when the walk reaches it, so you can type straight over it |
| `{{0}}` | where the caret finally lands. Always visited last |
| `{{{{` | a literal `{{`, for the rare body that needs one |

After an expansion that left placeholders, **Tab** jumps to the next one and
selects it, **Shift+Tab** goes back, and **Escape** leaves the walk — from then
on **Tab** inserts a tab character again, as it always does. Clicking elsewhere
or leaving the editor also ends the walk.

`{{n}}` was chosen over the more familiar `$1` because this is a *PostgreSQL*
editor: `$1` is a positional parameter and `$$` opens a routine body, so a
`$`-based syntax would need escaping in the most common snippet of all — the
trigger-function skeleton. Braces never occur doubled in SQL, so `{{` collides
with nothing. Anything else between braces is left exactly as you wrote it: a
malformed body degrades to plain text rather than failing.

### Editing them — the Snippets pane

**Settings ▸ Software settings… ▸ Snippets** is the editor. The **Settings** menu
exists **only in Maintenance mode** (see *Getting Started ▸ Maintenance mode*),
because this is configuring the app rather than using it. (There is no
**Settings ▸ Edit Snippets…** entry any more — the dialog became a pane of
**Software settings…**; see *Software Settings*.)

The settings window is **not modal** — it stays beside your work, so you can copy
a body out of the SQL you are looking at — and there is only ever one of it:
asking again while it is open just brings it to the front.

It has one table and one body pane:

- **Trigger word** — what you type before pressing Ctrl+Alt+E. Editable.
- **Description** — a one-line note for your own benefit. Editable.
- **Origin** — **built-in**, **built-in, edited**, or **yours**. Read-only, and
  it re-derives itself as you type: change a shipped snippet's body and its row
  turns to *built-in, edited* on the spot. The column exists because your store
  holds the *whole* set (below), so nothing else would tell our rows from yours.
- **Body of the selected snippet** — the pane underneath, holding the template
  in the syntax above. Bodies are multi-line by nature, which is why they live
  in a pane of their own instead of a squashed table cell.

Underneath sit **Add**, **Delete**, **Restore Built-ins**, **Export…** and
**Import…**, and then **OK** / **Cancel**.

- **Add** appends a row with a real, typeable trigger word (`newsnippet`, then
  `newsnippet2`…) rather than an empty cell, so you never meet a complaint
  before you have done anything.
- **Delete** removes the selected row — **including a built-in**. A deleted
  built-in stays gone until you ask for it back, which is exactly what the next
  button is for.
- **Restore Built-ins** appends every shipped snippet your set no longer has,
  and tells you which. **It never touches a row you already have** — a built-in
  you *edited* is your snippet now, and putting our version back over it would
  be the silent overwrite this feature exists to avoid. When nothing is missing
  it says so.
- **OK** saves. **Cancel** changes nothing at all — not on disk and not in your
  editors. Both are this pane's own buttons; the settings window's **Close** is
  neither of them and saves nothing (see *Software Settings*).

**A saved set is live immediately**, in every SQL editor that is open and in
every one you open afterwards. Nothing needs restarting.

Two things stop OK, and both are about the trigger word, because that is the
only field the expansion looks up: a **blank** one could never be typed, and a
**duplicated** one would make the body you get depend on row order. The
complaint appears inline, beside the rows it is about. **Bodies are never
validated** — a half-written template is a perfectly good thing to save and come
back to.

### Sharing them — Export and Import

- **Export…** writes the rows **as they currently stand**, edits included, to a
  file you pick. You do not have to save first.
- **Import…** reads such a file into the rows in front of you.

**Import never overwrites anything without asking.** Trigger words that are new
to you are added silently; trigger words you already have are **collisions**,
and you are asked about them by name:

- **Yes** replaces your versions with the imported ones, **in place**, so your
  ordering survives.
- **No** keeps every one of yours and still imports the new ones — so a
  colleague's file is useful even when half of it clashes.
- **Cancel** changes nothing.

Collisions are matched **without regard to case**, so an incoming `CASE` collides
with your `case`. Nothing is ever removed by an import.

**An import lands in the dialog's rows, not on disk.** You can look at what
arrived, undo a bad one by pressing **Cancel**, and only **OK** makes any of it
permanent. A file that cannot be read, or that is not a valid snippet file, is
**refused with the reason** and leaves your rows untouched.

### Where the store lives, and what follows from it

Your snippets are one file, **`snippets.json`**, in the application's per-user
data folder — the same folder that already holds `generator_config.json` and the
learned schema. It is plain, indented JSON, meant to be opened and edited by
hand if you would rather.

**It is deliberately not part of your project.** A snippet is a typing shortcut,
not a property of a schema, and a `.pgtp` is a movable artifact that other
people receive — so personal typing habits stay out of it, and crossing between
people is always something you did on purpose.

**The store file *is* the export file.** Export writes the same format the store
uses, so "send your snippets to a colleague" can equally well be done by mailing
`snippets.json` itself; the buttons are a convenience over a format that was
already shareable.

**The file holds the whole set, not just your changes.** That is what makes it
readable and hand-editable — what you see in it is exactly what the editors
expand — and it has one consequence worth knowing: **snippets added in a later
version of the app will not appear for you once you have a store of your own.**
They are not missing, they simply were not in the set the day your file was
written. **Restore Built-ins** is how you pick them up.

**A store the app cannot read is never written over.** If the file is corrupt or
malformed, the editor opens **read-only** — the reason is shown at the top, the
buttons and **OK** are disabled — and the **shipped defaults stay in force** in
your SQL editors, with a `[Snippets]` line in the **Activity Log** naming the
file and the problem. Read-only here does not mean "you have no snippets"; it
means your file may be one typo away from being fine, and overwriting it is the
one mistake you could not undo. Fix or move the file by hand, then restart the
application.

---

## The Autoformatter

**Format Selection** is the app's one formatting gesture — **Ctrl+Alt+F**, or
**Format Selection** on the editor's right-click menu, always over a selection you
made. It never runs by itself: there is no format-on-save, no format-as-you-type,
and no auto-format mode anywhere in the app.

**One gesture, two engines, chosen by the surface you are in** — never by guessing
at what the selected text looks like:

| Where you press it | What formats the selection |
|---|---|
| a **DDL object editor tab**, either **SQL Console** (Sandbox or Quality) | the SQL / plpgsql formatter |
| the **Raw XML** editor, **Edit XSD** / **Edit AutoXSD**, a generated **draft fragment** tab | the XML indenter |

That split is deliberate. A dispatcher that sniffed the text would eventually
guess wrong on a selection that is legitimately both — `<x>select 1</x>` — so the
tab you are in decides, and the answer never surprises you.

The XML side **changes indentation only**: it re-indents by element nesting depth
and rewrites nothing else. The SQL side re-indents and, if you ask it to, recases
keywords and breaks lines at clause keywords.

### Configuring it — the Autoformatter pane

**Settings ▸ Software settings… ▸ Autoformatter** holds the controls. The
**Settings** menu exists **only in Maintenance mode** (see *Getting Started ▸
Maintenance mode*), because this is configuring the app rather than using it, and
like everything else on that menu the entry carries **no keyboard shortcut**.
(There is no **Settings ▸ Autoformatter settings…** entry any more — see
*Software Settings*.)

> **A saved configuration applies in every mode**, even though the dialog is only
> reachable from Maintenance mode. The hosts of the gesture re-read your settings
> each time you press **Ctrl+Alt+F**, so a change is live immediately, in every
> editor that is already open, with nothing to restart. (And a toolbar button you
> pin to **Software settings…** opens the dialog outside Maintenance mode too —
> see *Appearance & Layout ▸ The toolbar*.)

**The defaults are byte-identical to the formatter this app always had.** Nothing
about your formatting changes until you change something here — the shipped
keyword-case setting is *Leave as typed*, and every clause rule ships as the
formatter's existing behavior. **Restore Defaults** puts that starting point back.

The dialog is three groups plus the buttons, and **every control is bounded** — a
combo, a spin box, a checkbox. There is deliberately no free-text rule box
anywhere: you cannot express a rule the formatter could not apply repeatably.

- **SQL / plpgsql**
  - **Keyword case:** — **Leave as typed** (the default), **UPPERCASE** or
    **lowercase**. It applies to **keywords only**. Identifiers, type names,
    function names, literals, strings and comments are never recased: the
    formatter works offline with no knowledge of your schema, and a quoted
    PostgreSQL identifier is case-sensitive, so recasing one would change what it
    means.
  - **One indent level:** — **Spaces** with a width, or **Tab**. Picking Tab
    greys the width out, because a tab has no width to choose.
  - **Start a new line at a JOIN phrase** — governs the whole phrase (`left outer
    join …`), never one prefix word of it. Off keeps it on the `FROM` item's line.
- **Line breaks per clause keyword** — one row per clause keyword the formatter
  knows, with a **New line** checkbox and an **Extra indent (levels)** spin box.
  The list is generated from the formatter itself, so it always matches what the
  engine can act on. **The breaks the formatter needs to stay correct are not
  listed** and cannot be switched off: after a `--` comment and after `;`, the
  `DECLARE` header, and the block keywords.
- **XML / XSD** — **One indent level (spaces):**, for the XML indenter. Two by
  default, because two spaces is the `.pgtp` file's own indentation unit.

**OK saves**, and saving *is* applying — there is nothing else to press. **OK**
and **Cancel** are this pane's own; the settings window's **Close** is neither.
**Cancel** changes nothing, on disk or in your editors. Your configuration is
stored with the app's other per-user settings, beside your theme, toolbar
arrangement and shortcut overrides — it is **not** part of any project, because a
formatting preference is personal and a `.pgtp` is an artifact you hand to other
people.

---

## Local DDL-Versioning Projects

A **local project** is a plain folder on your own machine that gives you a
versioned, file-based home for the DDL objects and the `.pgtp` file you're
working on — checked-out routines and triggers as individual `.sql` files, an
optional local sandbox connection, and (later) git integration. Everything the
app manages here is a plain, readable file: nothing is a black box.

Nothing here is required for ordinary editing. Browsing the **DDL Explorer
(Quality)** and **Edit DDL** (see *DDL Explorer*) work with just a database
connection, no
project needed — with none open, Edit DDL simply hands you an editable tab that
saves wherever you tell it to. A project becomes relevant only once you want checked-out
`ddl/` files, a versioned `.pgtp` working copy, drift markers, a deploy — or the
second, sandbox-scoped explorer, which is a project's sandbox by definition and
so is offered only while such a project is open.

### The File menu's project actions

Four actions on the **File** menu manage projects, in their own group below the
open actions (**Open…**, **Open PHP File…**):

- **New Project…**
- **Open Project…**
- **Close Project** — disabled until a project is open.
- **Project Settings…**

The fifth used to be **Deploy .pgtp**. It now lives on **Deployment ▸ Deploy
.pgtp**, where it appears only while the Raw XML tab is in front — pushing the
`.pgtp` is meaningful only when the `.pgtp` is what you are looking at (see *The
Deployment Menu*).

**No project is ever created silently.** An action that can only mean something
inside a project — **Project Settings…**, for instance — shows a **"Project
Required"** dialog offering **Create…**, **Open…**, or **Cancel** if none is
open yet; choosing Create or Open runs that flow first and then continues the
original action.

**Editing a DDL object is deliberately not one of those actions.** The DDL
Explorer's **Edit DDL** never raises that dialog: with no project it quietly gives
you a plain editable tab, because working on a single routine with just a
database connection is a supported mode, not a mistake to be corrected.

### The window title shows the active project

Whenever a local DDL-versioning project is open, the title bar adds
**"— Project: `<folder name>`"**, ahead of the existing `.pgtp` filename and
unsaved-changes `*` marker — for example
`PGTP Editor — Project: acme_billing - dev_Ferrara.pgtp *`. With no project
active, the title shows just the app name and the `.pgtp` filename as before.

### File dialogs default to the active project's folder

While a project is active, every Open/Save-type file dialog in the app —
**File ▸ Open**, **Deployment ▸ Save as new pgtp**, **Schema ▸ Export XSD**,
**Schema ▸ Import XSD**, the file pickers in **Compare/Merge pgtp**, and the
first **Save As…** of a DDL object editor tab (see *DDL Explorer*) — starts
in the project's own folder instead of wherever you last browsed. With no
project active, these dialogs behave as before and default to the operating
system's own last-used directory. It's only a starting point in every case:
you can always navigate elsewhere.

### Installing PostgreSQL and plpgsql_check (Windows)

Before a project's sandbox can do anything, your machine needs a local
**PostgreSQL** server, and the sandbox check ladder's **tier 3 static analysis**
(see *The Sandbox ▸ The validation ladder*) needs the **`plpgsql_check`**
extension *available on that server*. The app runs `CREATE EXTENSION IF NOT
EXISTS plpgsql_check` for you when it provisions a sandbox — but it cannot
install the server itself or the extension's files, so this is a **one-time
setup you do up front**, before or while you fill in a project's sandbox
connection. These steps are for **Windows** and take the simplest route, with no
compiler.

**1. Install PostgreSQL — use version 16.** Download the official installer from
[postgresql.org/download/windows](https://www.postgresql.org/download/windows/)
and run it (it bundles pgAdmin and the command-line tools). **Choose PostgreSQL
16**, not 17 or 18 — the ready-made `plpgsql_check` file in step 2 is built for
versions 15 and 16, and matching versions is what keeps this compiler-free.
During setup, **remember the `postgres` superuser password**: the sandbox
connection you give the project must be a superuser, because `CREATE EXTENSION`
requires it.

**2. Add `plpgsql_check` — a drop-in file, nothing to build.** The extension's
author publishes precompiled Windows files, so you never touch a compiler:

- Download **`plpgsql_check-2.5.4-x64.zip`** from
  [pgsql.cz/files/plpgsql_check-2.5.4-x64.zip](https://pgsql.cz/files/plpgsql_check-2.5.4-x64.zip)
  (it covers PostgreSQL 15 and 16) and extract it.
- Copy three items into your PostgreSQL install (default location
  `C:\Program Files\PostgreSQL\16\`):

  | From the zip | Copy into | Note |
  |---|---|---|
  | `plpgsql_check-16.dll` | `…\PostgreSQL\16\lib\` | **rename it to `plpgsql_check.dll`** — drop the `-16` |
  | `plpgsql_check.control` | `…\PostgreSQL\16\share\extension\` | |
  | `plpgsql_check--*.sql` | `…\PostgreSQL\16\share\extension\` | copy all the `.sql` files |

That makes the extension *available* to the server. You do **not** need to edit
`postgresql.conf` or touch `shared_preload_libraries` — the app uses
`plpgsql_check` in its function-call mode, which only needs the extension created
in the database.

**3. Enable it — easiest is to let the app do it.** Once you have a project with
a sandbox, open **File ▸ Project Status…**, click the **plpgsql_check** node, and
press **Install the plpgsql_check extension** (see *Project Status ▸ Clicking a
node*). That runs the `CREATE EXTENSION` for you against the sandbox — and the
app already does it automatically the first time it provisions a sandbox, so
often there is nothing left to do. To enable it by hand instead, connect to the
sandbox database as the superuser and run:

```sql
CREATE EXTENSION IF NOT EXISTS plpgsql_check;
```

> **If you install PostgreSQL 17 or 18** there is no ready-made file, and the
> only way to get `plpgsql_check` is to build it from source. Avoid that — install
> **PostgreSQL 16** and use the drop-in file above.

### Creating a project

**New Project…** opens a dialog with:

- **Name** and **Description** — optional, free text.
- **Project folder** — pick a folder with **Browse…**; that folder *is* the
  project. There's no separate bootstrap step.
- **Project .pgtp (optional)** — pick the `.pgtp` this project is a checkout of,
  with its own **Browse…**. Attaching one copies it into the project as its
  working copy and links it, exactly as opening a `.pgtp` while the project is
  active would; **and the file is opened into the editor as soon as the project
  is created**, so you land on your project rather than on an empty window.
  Leave it empty for a project with no `.pgtp` — you can still attach one later
  by opening it. If the copy fails, the project is still created, with **no**
  `.pgtp` link at all and a `[Project]` line saying why: a recorded link pointing
  at nothing is worse than no link.
- **Quality (target) server** — **hidden until you attach a `.pgtp`**, because
  with no `.pgtp` there is nothing to fill it from. Attaching one reveals it and
  fills **Host**, **Port**, **Database** and **User** from the file's own
  connection settings. **The Password is the one field you supply**: it is never
  read out of the XML. **Test** checks the connection. This is the quality /
  staging database the DDL Explorer and the database checks read while the
  project is open.
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
  target database via `pg_dump`/`pg_restore`. Cloning happens once, here, as
  part of creating the sandbox; you can change the recorded mode later in
  **Project Settings ▸ Connections** and press **Provision sandbox** to rebuild
  the sandbox in it, or refresh the rows alone from the **Project Status**
  window's *Sandbox data* node. See *The sandbox is created with the project*,
  below, for what pressing **OK** then actually does.
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
5. **leaves the session open.** That is why **Deployment ▸ Check and commit to
   sandbox**, both check gestures (**Parsing ▸ Check Object in Sandbox** and
   **Parsing ▸ Check and rollback**) and **Database ▸ Sandbox SQL Console…** are usable
   immediately after you create a project. Opening that project again later is
   the same story: the session comes back up by itself (see *The Sandbox*).

The **Activity Log** confirms with `Created and provisioned sandbox database:
<name>`.

**The run narrates itself while it runs.** Provisioning creates a database, takes
a baseline, installs an extension and probes the server, which against a real
server is seconds to minutes — so the **Messages** tab says
`[Sandbox] provision: started` the moment the work is dispatched and then keeps
one line ticking — `[Sandbox] provision: .`, then `..`, then `...` — once a
second until the run finishes, restarting the count after ten so a long run does
not draw a hundred-character line. It is a single line rewritten in place,
it is not clickable (a heartbeat has nowhere to navigate to), and the final
`[Sandbox]` outcome line lands under it as usual. A project created with the
**Local sandbox** group left blank builds no database, so it is not narrated
either.

**Creating a project never reports a connection error of its own.** The
automatic session (see *The Sandbox ▸ The sandbox session opens itself*) waits
until the sandbox database has actually been created and named — that name is
the last thing provisioning produces — so nothing is dialled before there is
something to dial.

**If a generated name is already taken on the server, a different random name is
tried.** An existing database is never reused, never written into, and never
dropped. In the very unlikely case that every generated name is taken, the step
stops with a message saying so, and nothing on the server is touched.

**A sandbox failure never costs you the project.** If creating, provisioning, or
`CREATE EXTENSION` fails, the project is still created — it just has no working
sandbox (a tier-2 *quality project*, see *Project Status*). The exact reason
appears in the **Messages** tab on a line prefixed **`[Sandbox]`**, and the project
records **no** sandbox database, so nothing later claims a sandbox that isn't
there. Its sandbox *server* details are kept, so you can fix the cause and try
again.

**If the project has no target connection yet** — likely, since you have just
created it — there is nothing to build a baseline from, so the sandbox is created
**empty** and the **Messages** tab says exactly that, pointing you at **Project
Settings** to set the target and at re-provisioning afterwards. Choosing **With
data** without a target likewise clones nothing and says so; your recorded choice
is left alone, so it still applies once a target exists.

Such a sandbox is perfectly usable — you can apply and check a self-contained
routine in it straight away — but it has **no baseline schema**, so an object that
references your target database's tables will fail to compile there until it is
re-provisioned against a target connection. That is a real answer from the
sandbox, not a malfunction: the table genuinely isn't there yet.

> **An empty sandbox is fixable in place.** Set the target connection in **File
> ▸ Project Settings… ▸ Connections**, then press **Provision sandbox** in that
> same tab's **Sandbox provisioning** group — the sandbox is rebuilt from the
> target you just supplied. See *The Sandbox ▸ Provisioning, resetting and
> creating a sandbox database*. (One `[Sandbox]` line still tells you
> re-provisioning is unreachable with a project open. That sentence is out of
> date; the group described here is where it now lives.)

### Opening a project

**Open Project…** opens a folder picker showing **folders only** (no files) — pick
an existing project folder. The folder must already be a valid project (it must
carry the `.ddlproject/settings.json` marker written by **New Project…**); picking
any other folder is rejected with a **"Not a Project Folder"** message instead of
silently creating an empty project.

On a successful open, the app compares a checksum of the linked `.pgtp`'s working
copy against its source and reports the result in the **Activity Log**, on a line
prefixed `[Project]`:

- **"Source .pgtp checksum recorded (…)."** — first time this comparison ran.
- **"Source .pgtp unchanged since last opened (…)."**
- **"Source .pgtp has changed since this project last saw it (…) — surfaced,
  not auto-resolved."**

If the **Quality** explorer's routines and triggers are already loaded, its
tree's drift markers (see *DDL Explorer*) refresh at the same time.

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
  app doesn't guess: it reports the finding in the **Activity Log** on a line
  prefixed `[Project]` listing the candidates, and you open the one you want via
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
  **Without data (schema only)** or **With data** — and, under it, the
  **Sandbox provisioning** group with the three gestures that build a sandbox:
  **Provision sandbox**, **Reset sandbox**, and **Create a sandbox database for
  me**. Changing the mode re-clones nothing by itself: it takes effect the next
  time you press **Provision sandbox**. See *The Sandbox ▸ Provisioning,
  resetting and creating a sandbox database* for the whole group.
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
on that inline status line: no dialog, no Messages or Activity Log entry. The test runs in
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

There is no separate check-out command: **while a project is open, the Quality
explorer's Edit DDL *is* the checkout** — see *DDL Explorer ▸ Editing a
single function, procedure, or trigger* for what it writes into `ddl/`, and for
the drift markers (`*`/`!`) it puts on the **DDL Objects (Quality)** tree. The
Sandbox explorer has no Edit DDL and checks nothing out, on purpose — see *DDL
Explorer ▸ The Sandbox Explorer, and how it differs*.

### The .pgtp file as a checked-out artifact

The first time you open a `.pgtp` file while a project is active, the app
copies it into the project folder as a **working copy** and remembers the
link — this happens automatically, with no extra step. (If no project was
active yet, **File ▸ Open**'s chooser — see *Getting Started ▸ Opening a
project* — is how you make one active for this file: pick **New Project…** or
**Open Project…** there instead of **Edit Standalone**.) From then on:

- Ordinary **Deployment ▸ Save pgtp** writes to this working copy and makes **no
  `.bak` backup** — the working copy itself is the safety net. See *Getting
  Started ▸ Saving, closing, discarding* for how this compares to plain,
  project-less `.pgtp` saves, which are unaffected.
- Pushing your edits back to the original file (on the shared/quality server)
  is the separate, explicit **Deployment ▸ Deploy .pgtp** action — on the Raw
  XML tab, any time.
- Closing the project (**Close Project**) also offers this as a yes/no
  prompt if the working copy has changes not yet pushed. Declining just
  closes the project without pushing; nothing is lost.

### Closing a project

**Close Project** always succeeds — closing never forces anything. Along the
way it reminds you, via `[Project]` lines, of anything left informational and
unresolved:

- If the `.pgtp` working copy has unpushed changes, it offers to **Deploy
  .pgtp** (see above) — a yes/no prompt, not a requirement.
- If there are DDL objects with local edits not yet included in a batch
  deploy, it notes how many — *"N DDL object(s) have local edits pending a
  batch deploy."* — and does not open any deploy flow automatically.

**A close-time reminder goes to two places, and that is deliberate.** It is
journalled into the closing project's own `activity.jsonl`, where it belongs to
the project it is about, **and** it is rendered in the bottom dock's
**Messages** tab (see *Where Output Appears*). The Activity Log is replaced when
the project changes, so a reminder written only there would be wiped off screen
by the very close that produced it — you would be told something at the exact
moment you could no longer read it. Messages accumulates and survives the close,
so the reminder is still in front of you afterwards.

---

## The Sandbox

A project's **sandbox** is a throwaway local PostgreSQL database where you can
run a routine before anyone else has to live with it: apply your edit there,
validate it, poke at it with ad-hoc SQL, and only then decide what to do with it.
Nothing in this chapter can reach your real database.

The sandbox is a **local DDL-versioning project** concept, so everything below
requires a project to be open. **The usual way a sandbox comes into being is
File ▸ New Project….** Fill in that dialog's *Local sandbox* group and the app
creates the database itself, auto-named, provisions it, installs
`plpgsql_check`, and leaves the session open (see *Local DDL-Versioning Projects ▸
The sandbox is created with the project*).

**Everything about a sandbox afterwards lives in File ▸ Project Settings… ▸
Connections** — the connection details, the created database's name, the
with-data/without-data mode, and the three gestures that build one: **Provision
sandbox**, **Reset sandbox** and **Create a sandbox database for me**. So a
project that came up without a working sandbox is fixable in place, and a
project that never had one can be given one. See *Provisioning, resetting and
creating a sandbox database*, below.

### The sandbox session opens itself

**Open a project that has a sandbox and the session is already there.** Applying
an object, checking one, and the Sandbox SQL console just work; there is no
"open a session first" step, and **there is no Open Sandbox Session or Close
Sandbox Session entry on the Database menu any more** — both were deleted, not
merely hidden. Creating a project with **New Project…**'s sandbox group filled in
hands you an open session the same way (see *Local DDL-Versioning Projects ▸ The
sandbox is created with the project*).

**There is no explicit close, either.** The session is released when you close
the project, or when you open another one. Nothing else drops it, and nothing
asks you to.

**Opening the session is best effort, and it never delays or fails a project
open.** It is not modal, it never puts a dialog in your way, and if it cannot
connect you simply have no session — exactly the state the app already knew how
to describe. The outcome lands in the **Messages** tab as a `[Sandbox]` line, and a
refusal always says which refusal it was: the sandbox is unreachable, the user is
not a superuser, `pg_dump`/`pg_restore` are missing from your `PATH` (only for a
**With data** sandbox), no sandbox is configured — or the connected database is
**not one PGTP Editor created**. That last guard is deliberate and absolute: a
sandbox must both be named `pgtp_sandbox_…` *and* carry the ownership comment the
app writes when it creates one, because a database name alone can be faked.
Pointing the sandbox connection at a database you made by hand is refused rather
than written to.

**With no session, the gestures that need one still say so.** They are not
hidden: **Parsing ▸ Check Object in Sandbox**, **Parsing ▸ Check and rollback**,
**Database ▸ Sandbox SQL Console…** and the Project Status window's two sandbox
buttons are all there whenever a sandbox is *configured*, and using one states
the reason it cannot run — *"no sandbox session is open — the project's sandbox
could not be reached, or none is set up yet (check its connection in Project
Settings)"* — over an **Open** button that retries the connection. **That button
is the only manual way to open a session in the app.** The other two ways back
are correcting the sandbox connection in **File ▸ Project Settings… ▸
Connections**, when the configuration itself is what is wrong, and simply closing
and reopening the project, which retries the automatic open.

**The refusal points at Project Settings because that is where the remedy is.**
Both halves of it have one: if the connection is wrong, correct it there; if
*"none is set up yet"* is the case, the same tab's **Sandbox provisioning**
group is where you build one (see the next section).

**Database ▸ DDL Explorer (Sandbox)** stands apart from all of this: it only
*reads* the sandbox, so it needs a configured sandbox but no session at all, and
it comes and goes with the project (see *DDL Explorer ▸ The Sandbox Explorer, and
how it differs*).

### Provisioning, resetting and creating a sandbox database

Building a sandbox lives in **File ▸ Project Settings… ▸ Connections**, in the
**Sandbox provisioning** group directly under the sandbox connection's fields
and its **Without data (schema only)** / **With data** radios. There is no
**Database ▸ Sandbox Setup…** any more — that dialog was deleted and its three
gestures moved here, next to the connection and the mode they act on. The
dialog is non-modal, so a long provisioning run doesn't lock the window and you
can keep working while it goes.

The group offers three things, as your situation allows:

- **Provision sandbox** — build the configured sandbox database from the
  project's **target** database. This is what a changed mode takes effect on.
- **Create a sandbox database for me** — a name field with the button beside it.
  PGTP Editor only ever writes to a sandbox it created itself, so if your
  project points at a database that isn't one, this is how you get one that is;
  the name must look like `pgtp_sandbox_…`, and the new database is provisioned
  in the same step. When the configured database really is a foreign one, the
  refusal's own sentence stands above this row, so you can see what you are
  answering.
- **Reset sandbox** — drop every application schema in the sandbox and build it
  again. Shown only while a session is live.

**An action that cannot run is absent, with the reason in its place** — the same
posture as the rest of the app, one level down. So the group changes shape with
what you have typed above it and what the project has: *"No sandbox server is
configured yet…"* while the sandbox connection is blank, *"Provisioning builds
the sandbox from the project's target database, but no target connection is
configured on this tab."* while there is nothing to build from, and *"No sandbox
session is open…"* where **Reset** would be. Nothing here is ever greyed out.

> **A mode change lands on Provision, not on Reset.** **Reset sandbox** re-runs
> whichever mode the sandbox was *created* with, not the radio you have just
> ticked — so switching to **With data** and pressing **Reset** gives you the
> schema-only sandbox again. The dialog says so in two places (under the radios,
> and under the Reset button, which names the mode it would actually re-run).
> **To make a mode change real, press Provision sandbox.**

**Each of the three is destructive, and each asks exactly once.** The
confirmation is the operation's own warning, not a generic "are you sure":
*"Provisioning rebuilds the sandbox database's schemas from the target database.
Anything already applied to the sandbox is lost."* for **Provision** and for
**Create a sandbox database for me** (which provisions in the same step), and
*"Resetting drops every application schema in the sandbox database (DROP SCHEMA
… CASCADE) and re-provisions it. Anything already applied to the sandbox is
lost."* for **Reset**. So you always read what is about to happen before it does. Declining says so and touches nothing. Every
outcome, success or failure, is reported in the group's own status line in the
words the operation used; nothing is swallowed.

**With Without data (schema only) chosen, the group also states that baseline's
limits**, where you are choosing it rather than buried in a release note: it
reproduces schemas, types, tables (columns only), views, routines and triggers,
but **not** extensions, sequences, constraints, defaults or data — so findings
that lean on any of those are unreliable.

**Provisioning writes the settings first.** The mode you picked (and the name a
"create one for me" chose) is saved to the project's settings file the moment
the operation starts, not when you press **OK** — so the app never describes the
previous sandbox while working against the new one, even if you leave the dialog
open or cancel out of it afterwards.

Two neighbouring sandbox actions live elsewhere, and deliberately are not
duplicated here: **run or redo the data clone**, and **install `plpgsql_check`**,
are buttons on the **Project Status** window's *Sandbox data* and *plpgsql_check*
nodes (see *Project Status ▸ Clicking a node*).

> **The sandbox's applied working set has no viewer in this version.** The
> sandbox records what has been applied to it, and the app reads that record —
> tier 2 of a **Check Object in Sandbox** run reports it for one object — but the
> table that listed the whole set went with the deleted dialog. Ask about one
> object with a Check, or query the sandbox directly in **Database ▸ Sandbox SQL
> Console…**.

### The validation ladder, and the three ways to run it

Validating a routine in the sandbox climbs a four-rung ladder, and the
**Messages** tab (see *Where Output Appears*) gets **one `[Check]` line per rung,
always** —
never one summary line that quietly hides a rung nobody managed to check. Because
Messages accumulates, the previous run's ladder is still above this one, under its
own dated header:

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
  determined, and those are three different answers. Install it from the
  **plpgsql_check** node in the **Project Status** window — the one place that
  install button lives. On a fresh machine the extension has to be made available
  to the PostgreSQL server first; see *Local DDL-Versioning Projects ▸ Installing
  PostgreSQL and plpgsql_check (Windows)*.

**On a tab holding a generated `ALTER TABLE` statement, tier 3 is absent
altogether** — not unavailable, not failed: an ALTER creates no function for
`plpgsql_check` to analyse, so that rung was never going to run. The other three
tiers work as usual (see *DDL Explorer ▸ The tab an Alter Table operation opens*).

Three gestures run this ladder, and they differ in **what they touch**, not in how
thorough they are:

| Gesture | Where | Runs | Changes the sandbox? |
|---|---|---|---|
| **Deployment ▸ Check and commit to sandbox** | the Deployment menu, on a DDL object editor tab | tiers 0, 1, 2 and — when `plpgsql_check` is installed — tier 3, all over your buffer | **yes** — commits |
| **Parsing ▸ Check and rollback** | the Editor menu bar, on a DDL object editor tab | the identical run, on the identical buffer | **no** — rolled back |
| **Parsing ▸ Check Object in Sandbox** | the Editor menu bar, on a DDL object editor tab | tier 3 over what the sandbox already holds; tier 2 reports bookkeeping only | **no** — reads only |

**The three names say exactly what each one does to the sandbox**, which is the
only thing that distinguishes them: one **checks and commits**, one **checks and
rolls back**, one **checks what is already in there**. Each gesture has one name
and uses it everywhere — on its menu entry, on its confirmation dialog, on its
`[Check]` lines and in the status bar.

**Both Parsing checks live on the Editor menu bar's Parsing menu and nowhere
else** — they are the linting of the DDL in front of you, and Parsing is the
per-tab menu. They used to be on the **Database** menu and are gone from it (see
*The Two Menu Bars ▸ Parsing, on a DDL object tab*).

So: **Check and commit to sandbox gives you the full verdict** as part of
applying; **Check and rollback gives you the same verdict and changes nothing**;
and **Check Object in Sandbox asks the sandbox about the state it is already
in**.

The reason to pick **Check and rollback** over **Check and commit to sandbox** is
not that it checks more — it checks exactly the same things. It is that it leaves
the sandbox as it was. Use it when you want to know whether an edit would compile
before letting it become what the sandbox holds; use the committing one when you
have decided this version is the one the sandbox should have.

None of the three has a keyboard shortcut. See *Keyboard Shortcuts*.

### Applying an object to the sandbox

**Deployment ▸ Check and commit to sandbox** is on the Editor menu bar for every
open **DDL object editor tab** (see *The Deployment Menu*), and that menu is the
**only** place it is offered — there is no button under the editor and no
right-click entry for it. Without a session the menu entry stays put and
says why it cannot run instead of applying anything. It commits the tab's current text to the sandbox database,
records it in the sandbox's working set, and runs the whole validation ladder over
it — the DDL, the bookkeeping and the checks all in one transaction, so the sandbox
can never hold a definition without the record of what it holds.

- It is **never a keyboard shortcut**. An irreversible outward effect should not
  be one keystroke away, so applying is always a deliberate menu pick.
- It always asks first, and the confirmation **names the object and the database
  — with its host** — it is about to write to; you never confirm a nameless
  destination.
- The sandbox is **stateful**: your edit stays there until you apply something
  else. Applying is not a test that cleans up after itself.
- An empty buffer is refused outright rather than applied as an empty definition.
- The outcome — the headline, all four tier lines, any caveats, and every
  individual finding — is reported as `[Check]` lines in the **Messages** tab. A
  cancelled apply says so and applies nothing. The apply itself also gets one
  **Activity Log** row, from the **Sandbox DB** source, carrying the full DDL and
  any full error text a click away.

**It gives you the ladder's verdict; you do not have to check afterwards.** The
report you get names what compiled, what the lint said, what `plpgsql_check` found,
and what could not be checked at all.

**An apply that did not commit says so, in as many words.** If PostgreSQL rejects
any part of it, the whole transaction is rolled back and the `[Check]` line reads
*"… was NOT applied to sandbox database …; the transaction did not commit."* — and
the buffer is **not** marked as applied. This matters: the sandbox does not hold
that text, and anything claiming otherwise afterwards would be a lie about what is
in your sandbox. The tier that produced the rejection is named alongside it, so you
know which rung failed.

The apply runs off the UI thread, so a slow `plpgsql_check` pass can't freeze the
window; the status bar's busy slot counts the seconds while the apply is under
way (see *The Status Bar*) and the full report lands when it finishes.

**Writing to the real database is a different gesture, on the same menu.**
**Deployment ▸ Apply to quality** executes a DDL object tab's buffer against the
quality database, behind its own hard preconditions — including a green sandbox
validation for exactly that text. It is described where it belongs, in *DDL
Explorer ▸ Editing a single function, procedure, or trigger*. Nothing else in
this chapter can reach anything but the sandbox.

### Checking an object and rolling back

**Parsing ▸ Check and rollback** runs the ladder over the **active DDL
object editor tab** exactly as **Check and commit to sandbox** would — tier 2 really
compiles your buffer, tier 1 really lints it, tier 3 really calls `plpgsql_check` — and then
**rolls the whole thing back**. The sandbox is left untouched, nothing is added to
its working set, and the buffer is not marked as applied.

This is the gesture that answers *"would this compile?"* without making it so. Its
name says both halves — it really **checks**, and it then really **rolls back**.
It is deliberately built from the same machinery as the apply: a probe that diverged
from the real thing would be validating something other than what you are about to
run.

Exactly one object per run — the tab you are looking at, which is also the only
tab that shows the entry at all.

### Checking an object in the sandbox

**Parsing ▸ Check Object in Sandbox** is the read-only one: it examines the
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

**It answers in one line, in a dialog, before you read anything else.** This
gesture is clicked to ask a question one bit wide — *am I in line with the
sandbox?* — so it states the verdict outright instead of leaving you to infer it
from the absence of a caveat. The box is titled **Check Object in Sandbox** and
says one of exactly four things:

| The answer | What it means |
|---|---|
| *"… matches what the sandbox holds."* | your buffer and the sandbox agree |
| *"… does NOT match what the sandbox holds."* | they have diverged — the detail line says since when |
| *"The sandbox does not hold … at all."* | it has never been applied there. Not the same as "differs" |
| *"Whether the sandbox holds … could not be determined."* | the comparison itself could not be made |

Under the headline sits the ladder's own wording for *why*, so the dialog and the
`[Check]` lines can never tell you two different stories. **The dialog is in
addition to the Audit output, never instead of it** — the **Messages** tab still
gets the whole ladder with every finding clickable.

**If your buffer has changed since it was applied, the report carries a
stale-buffer caveat**: the findings describe the version in the sandbox, not the
text in front of you. When you want the verdict on the text you are looking at,
use **Check and rollback** or **Check and commit to sandbox** — both compile your
buffer; this one does not.

Both Check entries are present whenever a **DDL object tab is in front and the
project has a sandbox configured** — whether or not a session is open, and whether
or not the `plpgsql_check` extension is installed. That is on purpose: a tier that
could not run is a **reported outcome**, not a reason to hide the gesture, and a
missing session is a reason the app can state rather than an absence you would
have to guess at (see *The sandbox session opens itself*). The report always says
what it could *not* check, so a check that could not run can never be mistaken for
a clean one.

For a trigger, the ladder needs to know which function the trigger calls; that is
read from the `EXECUTE FUNCTION …` clause in your buffer. If it can't be read, the
run says tier 3 was unavailable for that reason instead of guessing a function.

**A trigger function can be checked too.** `plpgsql_check` refuses to analyse
anything returning `trigger` without knowing which table it fires on, so for a
`CREATE FUNCTION … RETURNS trigger` buffer the editor looks up the trigger that
calls that function and hands the ladder that trigger's table — the same lookup
the editor's `NEW.` / `OLD.` completion uses. (Checking one used to stop with the
server's own *"missing trigger relation"* complaint.) Two honest limits remain:
if that table is not in the sandbox, tier 3 reports unavailable and names the
missing relation, and a trigger function **no trigger calls yet** has no relation
to bind — none is invented, so tier 3 cannot run for it until a trigger attaches
to it.

### Clicking a Check finding

Whichever of the three gestures produced them, findings arrive in the
**Messages** tab as their own lines, in the same run block as the narrative tier lines, each tagged
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
area: a SQL editor on top, and below it the **Results** grid — the rows your
query actually brought back. This grid is the one thing in the app the word
*results* refers to; the bottom dock's check tab is **Messages** (see *Where
Output Appears*). Like the other sandbox
gestures the menu entry is there whenever the project has a sandbox configured;
without a live session it opens no console and states why, over the **Open**
button that retries the connection (see *The sandbox session opens itself*).
There is only ever **one** console — invoking the command again focuses the tab
you already have.

**This console is sandbox-only by construction.** It cannot be pointed at your
production or quality database — not behind a confirmation, not behind a
preference, and there is deliberately no setting that would let it. It only ever
knows about the sandbox session. Ad-hoc SQL against the quality database has its
own separate tab with its own rules; see *The Quality SQL Console*.

- **Ctrl+Return runs**, and so does the **Run** button. It is live on both SQL
  consoles and nowhere else. Here it is safe because the sandbox is disposable —
  reset it and anything a statement did is gone.
- **Each statement of a Run commits as it goes**, on its own. There is no commit
  gesture and nothing to roll back: that is what a disposable database is for.
  (The Quality SQL Console does the opposite — nothing there is durable until you
  press **Commit**.)
- Run sends **your selection if you have one, otherwise the whole buffer**.
- **Row limit** — a spin box above the editor, 1000 rows by default. There is no
  "unlimited" setting on purpose. A result cut off at the cap is reported as
  **TRUNCATED**, naming the cap, so a partial answer is never presented as a
  complete one.
- The **status strip** above the grid gives you the row count and the elapsed
  time, or the driver's own status and affected-row count for a statement that
  returns no result set, or the database's error message — an error never shows up
  as a silently empty grid. **The strip is coloured for the two states you must
  not miss:** a failed statement is red, and a **TRUNCATED** result — or a refusal
  such as an empty statement — is amber. Both colours follow the Light/Dark theme.
  `NULL` values in the grid are dimmed and italic, so
  they can't be confused with an empty string or the text `NULL`.
- **Ctrl+Alt+F** reformats the selection, exactly as in a DDL object editor tab.
- **The console is the second home of the schema-aware editing gestures** —
  **Ctrl+Space** completion, **Ctrl+Alt+E**, **Ctrl+Alt+C**, **Ctrl+Alt+J** and
  **Ctrl+Shift+Space** all behave here as they do in a DDL object tab, off the
  same already-fetched **Quality** catalog. The one difference is `NEW.` /
  `OLD.`: a row variable only means something inside a trigger function body,
  and a console buffer is not one, so it resolves to nothing here. See *DDL
  Explorer ▸ Schema-aware completion and gestures in the SQL editors* for what
  each gesture does.
- The console holds no document, so there is nothing to save and no unsaved
  prompt when it closes. Losing the session clears the Results grid but leaves
  your typed SQL alone.

**Run in Sandbox Console** (right-click, in a DDL object editor tab, with text
selected) sends that selection over to the console and focuses it — and
**executes nothing**. SQL runs in the console and only there, and pressing Run is
your decision, not a side effect of copying something over. A second push
appends below the first rather than overwriting it.

---

## The Quality SQL Console

**Database ▸ Quality SQL Console…** opens the **Quality SQL** tab — the same
editor-over-results console as the sandbox one, but pointed at the **quality
(production) database**, with full read/write SQL. Everything the previous
chapter says about the editor, the **Run** button, the **Row limit** and
**Statement timeout** spin boxes, the coloured status strip, the results grid and
the schema-aware gestures is true here too. What follows is what is **different**,
and the differences are the whole point of the tab.

**The entry is absent until a quality target is configured.** It uses the same
test as the **Apply to quality** deploy gesture, so the two can never disagree
about whether there is a target. If a target exists but you decline the password
question, the command refuses at the gesture — *"Quality SQL Console… needs the
quality database's password; nothing was opened."* — and creates no tab at all. A
console that would refuse every Run is worse than no console. As with the sandbox
console there is only ever **one** quality console: invoking the command again
focuses the tab you already have. Both consoles can be open at the same time.

**A red banner across the top says what this tab is:** *"QUALITY — every Run here
targets the production database. Nothing is durable until you press Commit."* It
is painted in the same red as the **Quality** DDL Explorer's selection band, so
that colour means one thing everywhere in the app.

### Run, then Commit — where the two consoles part company

| | Sandbox SQL Console | Quality SQL Console |
|---|---|---|
| A Run goes to | this project's disposable sandbox | the quality (production) database |
| When it becomes permanent | **as it goes** — each statement of a Run commits on its own | **only when you press Commit** — the whole Run waits in one open transaction |
| Taking it back | reset the sandbox | **Roll Back**, any time before you commit |

**Commit** and **Roll Back** sit on the controls row beside the row limit and the
timeout, and they are enabled only while there is something outstanding. Between
a Run and your answer, a banner states the position: *"UNCOMMITTED — 3 statements
ran inside an open transaction. Press Commit to make them durable in the quality
database, or Roll Back to discard them."* **Commit** answers with what it did —
*"COMMITTED — 3 statements are now durable in the quality database."* — and
**Roll Back** with *"Rolled back — 3 statements were discarded (you rolled it
back)."*

**Ctrl+Return runs; it does not commit.** The chord is live on this console
exactly as on the sandbox one, and it only ever opens or extends the uncommitted
transaction. **Commit deliberately has no keyboard shortcut** — no chord, no menu
entry, no mnemonic, and it is not the button **Return** presses. That is the
design, not an omission: the reason a Run may be one keystroke away is that the
*commit* is the point of no return, so the commit is a click you have to mean.

**A failed Run is rolled back at once, and says so.** PostgreSQL aborts the whole
transaction at the first failing statement, so the console stops there, discards
the transaction and reports *"The run failed, so the whole transaction was rolled
back: NOTHING was committed."* **Commit** is not offered on an aborted
transaction — a button that cannot work would only be a lie — so only **Roll
Back** stays available.

**Four situations throw an uncommitted Run away, and each one tells you:**

- **Closing the tab** asks first, naming how many statements would be lost and
  what each answer does. Answering no **keeps the tab open** — this is the only
  way an uncommitted run can be protected, since a tab's **✕** is otherwise
  unconditional.
- **Closing the window** asks the same question, in the same words, and can be
  cancelled the same way.
- **Losing the connection** is terminal and cannot be asked about: the server has
  already rolled everything back. The console states the durability fact first —
  *"The connection to the quality database was lost, so the server rolled the run
  back: NOTHING was committed."* — and both buttons go dead, because neither
  gesture has anything left to act on. Re-open the console to start a new
  transaction.
- **The quality target ceasing to resolve** (you removed or changed it in
  **Project Settings**) rolls the transaction back and closes the tab **without
  asking**, reporting the reason — you did not initiate this, and there is no
  longer a database to commit to.

**Only a commit is journalled.** A Run against quality has changed nothing
durable yet, so it produces no **Activity Log** entry; the commit does, as a
`ran` line on the **Quality DB** source carrying the SQL. Every outcome —
committed, rolled back, refused — is also stated in the status bar.

**What it shares with the sandbox console, including the rough edge:** the
per-statement **Statement timeout** applies here too and is the *only* way a
long-running statement ends early — **there is still no Cancel button**, and the
app says so rather than offering one that would not work. Object-changing
statements are confirmed before they run, with wording that names the quality
database and reminds you that nothing becomes durable until you commit; the
*"don't ask again"* checkbox on that dialog is scoped to this quality session
only, and the tab-close question never offers it.

---

## Project Status

**File ▸ Project Status…** opens a separate **Project Status** window that
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
**File ▸ Project Status…** brings it back, re-probed, as often as you like.

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
  button is shown. (The button can only install the extension into the database
  once the extension's files are present on the PostgreSQL server — on a fresh
  machine, set that up first: see *Local DDL-Versioning Projects ▸ Installing
  PostgreSQL and plpgsql_check (Windows)*.)

Both of those two need a **live sandbox session**, because that is what they run
through. With a sandbox configured the button is there whether or not a session
is up: pressing it without one states the reason and offers an **Open** button
that opens the session (see *The Sandbox ▸ The sandbox session opens itself*),
after which you press the node's button again. With **no** sandbox configured at
all there is nothing to run against, so the button is simply not there — you get
the explanation and no dead control.

**Cloning data is destructive and asks first**, with the same one confirmation
the sandbox's own provisioning gestures use; declining changes nothing. A clone
is only ever attempted for a **With data** sandbox — for a schema-only one the
run refuses and says so, because that choice is recorded, not toggled per run.

An action is never a single click on the node itself: you always land in the
node's window first and press the button there. Running one closes that window
and re-probes, so the diagram can't keep claiming the state from before you
acted.

> This window is a **report with a few one-step actions**, not the sandbox's
> control panel. Provisioning, resetting and creating a sandbox database live in
> **File ▸ Project Settings… ▸ Connections** (see *The Sandbox ▸ Provisioning,
> resetting and creating a sandbox database*); the data clone and the
> `plpgsql_check` install are these two buttons and are deliberately not
> duplicated there. Everything the diagram reports is measured against the real
> thing, not assumed from what you configured.

---

## Diff / Merge

**Deployment ▸ Compare/Merge pgtp** — on the Raw XML tab (see *The Deployment
Menu*) — compares two `.pgtp` files side by side in the **Diff / Merge** tab, so
you can see what changed between versions and reconcile them. **Navigation ▸ Next
Difference** / **Previous Difference** step through the changes. The **Exit
Compare/Merge Mode** button at the bottom of the panel leaves the comparison and
gives you the Raw XML editor back. While the comparison is on, the mode indicator
reads **· Compare/Merge** (see *The Status Bar ▸ The mode indicator*), which is
what tells you the mode outlives stepping away to another tab.

The entry point used to be **Tools ▸ Compare / Merge Two Files…**; comparing is a
`.pgtp`-level gesture, so it moved to the tab that holds the `.pgtp`.

### The three Compare/Merge commands on Navigation

**Navigation ▸ Next Difference**, **Previous Difference** and **Apply Changes to
Target** are the comparison's own commands, and they sit at the bottom of the
**Navigation** menu, below its five bookmark entries (see *The Two Menu Bars*).
None of the three carries a keyboard shortcut. They moved off **Tools**, where
stepping through a comparison sat oddly among project-wide tools; **Prev
Difference** was relabelled **Previous Difference** to match **Previous Bookmark**
two entries above it.

**They are visible only while a comparison is loaded**, and they follow the
**mode**, not the tab — so they stay on the menu if you step away to read the Raw
XML mid-comparison, and they go when you leave Compare/Merge. The five bookmark
entries above them are per-*editor* rather than per-mode and are always there, so
the menu itself is never hidden. **Caption Mode disables the bookmark five and
leaves these three alone**: a comparison loaded while you are editing captions is
still navigable.

### Applying the changes you picked

Every difference in the change list carries a **checkbox**, unticked to begin
with. **Navigation ▸ Apply Changes to Target** writes **exactly the ones you
ticked** into the target file — nothing else, and never everything by default.

- **A backup comes first.** The target is copied to `<name>.pgtp.bak` before
  anything is written.
- **It is all-or-nothing.** If any ticked difference cannot be applied — usually
  because the target changed since the comparison was run — **nothing is
  written**, and the dialog lists which ones failed and why. The comparison stays
  loaded so you can untick them and try again.
- **Ambiguous differences are refused, by name.** A difference matched by
  position among duplicate siblings is marked **⚠** in the list; tick one and
  Apply stops and names it, rather than guessing which sibling you meant. Untick
  it, or verify the pairing yourself in the detail view first.
- **Ticking nothing** is answered with *"No differences are checked to apply."*
  and changes nothing.
- **On success the comparison ends**: Compare/Merge mode is left and the
  just-written target is reloaded into the Raw XML editor, so what you are looking
  at afterwards is the merged file itself. The **Activity Log** records the merge
  either way — including the per-difference detail of a failed one, one click away.

---

## Validation

**Parsing ▸ Validate Project** — on the Editor menu bar, beside **Auto Parse
XML** (see *The Two Menu Bars*) — checks your project for structural problems and
reports them as `[Validate]` rows with severities (errors and warnings) in the
bottom dock's **Messages** tab (see *Where Output Appears*) — for
example duplicate top-level page file names, missing expected attributes, or
unexpected children in container elements. **Click an issue to jump to it.** Each
run opens its own dated block and the previous run's issues stay above it, so you
can see what your last edit actually fixed.

This checks the **project's structure**. For the syntax of a PHP file you have
open in a tab, see *Checking PHP Syntax* — one tier down, on the **Tools** menu.

---

## Generating PHP

The **Generation** menu drives the PHP Generator command-line to compile your
`.pgtp` into PHP:

1. **Locate PHP Generator Executable…** once (the path is stored for future use).
2. **Generate PHP…** — if the project has unsaved changes, a dialog offers
   **Save**, **Save As** or **Cancel** first, so the generator always runs
   against the file on disk. (Those are buttons in that prompt, not menu
   entries — saving from a menu is **Deployment ▸ Save pgtp**.) The
   output-folder picker that follows is prefilled — with the open
   **local DDL-versioning project's folder** if one is active (see *Local
   DDL-Versioning Projects*), otherwise with the project's declared
   `outputPath` if it has one, otherwise with the current project file's own
   folder — but it's only a prefill: you can always choose a different folder.
3. **Open Output Folder** opens the generated output in your file browser.

---

## A note on busy feedback

Some operations take a moment on a large project. While one runs, PGTP Editor
shows a wait cursor (hourglass) and names the operation in the status bar's
**busy slot**, with a counter ticking up beside it, so you can tell it is working
rather than frozen:

- **Opening a file:** `Opening <name> (<size>) 2s`, e.g. `Opening dev_Ferrara.pgtp (312 KB) 2s`.
- **Parsing ▸ Validate Project:** `Validating <name> 1s`.
- **Tools ▸ Reparse Raw XML into Tree:** `Reparsing 1s`.
- **Generation ▸ Generate PHP…:** `Generating PHP 5s`.

When nothing is running the slot reads **`Idle`** — it is a permanent element and
always states something (see *The Status Bar*). The same announcement is also
recorded in the **Activity Log**, because *"is something running right now?"* and
*"what ran?"* are different questions.

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
  **Activity Log / Messages Panel** (the bottom dock), and **Raw XML Panel**. Each
  checkbox always reflects whether its panel is currently visible — closing a
  panel with the ✕ on its own title bar unchecks the menu entry too, and
  re-checking it brings the panel back. In among them, **View ▸ Activity Log**,
  **View ▸ Messages** and **View ▸ Findings** are not toggles: each opens the dock
  its tab lives in if needed and focuses that tab (see *Where Output Appears*).
- **View ▸ Expand All** / **Collapse All** open or fold the whole Project Tree.
- **The toolbar and your shortcuts are customized in Settings ▸ Software
  settings…**, in its **Toolbar** and **Keyboard shortcuts** panes — one picks a
  command's button and icon, the other picks its key (see *Software Settings*,
  *The toolbar* below, and *Keyboard Shortcuts ▸ Changing a shortcut*). **The
  View menu no longer carries either**: `Customize Toolbar…` and `Customize
  Shortcuts…` moved into that one dialog, which lives on the Maintenance-only
  **Settings** menu.
- **Keyboard focus is visible.** Move focus with **Tab** and the button or tab
  bar that has it is outlined, so you can always tell what **Space** or
  **Return** would press. It follows the theme in both the light and the dark
  scheme.
- Your window size and position, dock layout, theme, toolbar arrangement, and
  keyboard-shortcut changes are remembered between sessions.
- **Dialogs open at a size that shows their contents.** **Project Settings…**,
  the **Project Status** window and **New
  Function/Procedure…** all open large enough for their fields, tables and
  OK/Cancel buttons to be visible without dragging a corner first. They remain
  **freely resizable and shrinkable** — this is only the size they start at.

### The toolbar

The **Main Toolbar** shows each command as an icon with its label beside it. Out of
the box it carries five commands — **File ▸ Open**, **History ▸ Undo Project
Edit**, **History ▸ Redo Project Edit**, **Parsing ▸ Validate Project**, and
**Generation ▸ Generate PHP** — but it is not limited to them. (The two History
buttons kept their icons and their command through the rename; a toolbar you
arranged before it is carried over untouched.)

Two commands that used to ship on it are gone, each for the same reason: there is
no menu command left to pin. **Find** is now a permanent bar in every editor
rather than a menu entry, and **Save** is four named per-tab entries on the
**Deployment** menu rather than one tab-following command — so **the app ships
with no save button**. Both icons stay in the icon catalog and can be assigned to
any button you like. If you want a save button, pin whichever **Deployment** entry
you actually use, accepting that it comes and goes with the tab (see *The
Deployment Menu*).

**Settings ▸ Software settings… ▸ Toolbar** is where you arrange it: a two-list
pane with **Available** on the left, **On Toolbar** on the right, **Add →**,
**← Remove**, **Up**, **Down** and **Choose Icon…** between them, and **OK** /
**Cancel** at the bottom. (This is the dialog that used to be **View ▸ Customize
Toolbar…**; that entry is gone — see *Software Settings*.)

- The Available list offers **every command on either menu bar**, listed by its
  menu path — `Deployment › Save pgtp`, `Schema › Verify XSD`,
  `Database › DDL Explorer (Quality)`,
  `Navigation › List All Bookmarks`, and so on — in the order the menus themselves
  present them. Anything you can invoke from a menu, on the window bar or the
  Editor bar, you can put on the toolbar. The **Deployment** menu's entries are
  all listed, whichever tab you happen to be on when you open the dialog.
- Commands already on the toolbar stay visible in the Available list but appear
  **greyed out**, so you can see the whole command set at once and still can't add
  the same command twice.
- Only menu **separators** are left out — every actual command is offered.
- **Up** / **Down** reorder the On-Toolbar list; **OK** applies the arrangement and
  remembers it for future sessions, **Cancel** discards your changes.

**Out of the box most commands have no icon** — only those five ship with one — and
that is fine: a toolbar button shows its label beside its icon, so an
icon-less command simply reads as text. An icon is never a precondition for putting
a command on the toolbar. But you can give any button one yourself — see
*Choosing a button's icon*, below.

A toolbar button *is* the menu item, not a copy of it. It therefore shares that
menu item's enabled state (a command disabled in the menu is disabled on the
toolbar), its checked state for toggles such as **Database ▸ DDL Explorer
(Quality)** or
**View ▸ Light Theme**, and its keyboard shortcut — including one you assigned
yourself in the **Keyboard shortcuts** pane, since the button and the menu entry
can never drift apart. Toolbars you arranged in an earlier version of the editor
are carried over unchanged — including a **DDL Explorer** button you pinned
before the command was renamed to **DDL Explorer (Quality)**, a **Check Object in
Sandbox** button pinned while it still lived on the **Database** menu, and
buttons for the three commands that were renamed to say what they do: **Run on
sandbox** → **Check and commit to sandbox**, **Run on quality** → **Apply to
quality**, and **Check Object Without Applying** → **Check and rollback**. A
button for a command that no longer exists at all — **Deploy this edit…**,
**Open Sandbox Session**, **Close Sandbox Session** and **Sandbox Setup…** are
the current examples — is quietly dropped instead of sitting there doing nothing.

Because a button *is* its menu command, a button also **disappears while its
command is hidden**. That now includes the default **Validate Project** button,
which steps off the toolbar while a DDL object tab is in front (see *The Two Menu
Bars ▸ Parsing, on a DDL object tab*).

**Maintenance mode is the one thing that does *not* reach the toolbar.** A button
pinned to a command that mode hides from the menu bar — **Generate PHP**, say —
**stays on the toolbar and keeps working** (see *Getting Started ▸ Maintenance
mode*). That is deliberate: the mode is about getting the whole application out
of your way, and something you pinned yourself is something you meant to keep
within reach.

**The same holds in reverse, and it is the one place a menu location does not
predict the behaviour.** `Settings › Software settings` is offered in the
Available list like any other command even though the **Settings** menu itself
exists only in Maintenance mode — and a button you pin to it opens that dialog
**outside** that mode too (see *Software Settings*). Hiding a menu means *"not in
your way"*, never *"prevented"*, so pinning is how you say you want it anyway.
It is also how you keep the toolbar and shortcut panes one click away without
entering Maintenance mode.

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
- **Any** button can be given an icon — including the five that already ship with
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

## Editing Modes: Edit mode and Command mode

Every editable editor in this app listens in one of **two keyboard
vocabularies**, and the one it is listening in right now is called its **editing
mode**:

- **Edit mode** — ordinary Windows-style typing. Letters type letters, the mouse
  selects, **Ctrl+C** / **Ctrl+X** / **Ctrl+V** copy, cut and paste. This is
  where every editor starts, always.
- **Command mode** — a vim command vocabulary, entered with **Escape**. Letters
  are commands rather than text: `w` moves a word, `dd` deletes a line, `42j`
  goes forty-two lines down.

**This is not a vim fan feature.** The editors need advanced editing *operations*
whatever they are spelled as — go to an absolute line, move a **relative** number
of lines, delete or change or yank by word, by line, by motion — and none of them
exists anywhere else in the app, nor has a menu equivalent. The real choice was
never *"vim or no vim"*: it was **adopt a vocabulary that already exists, or
invent a keymap of our own**. Windows editors offer nothing to copy here, so
there was nothing to be consistent with, and the case that settles it is `42j` —
**a count applied to a motion is a grammar, not a command**, and no menu entry
and no invented Ctrl-chord can express it.

**There is no setting, no toggle and nothing stored.** Command mode is always
available and never turned on; it is a passing runtime state of one editor, so
there is nothing to configure, nothing in your preferences, and nothing that
survives a restart or even a tab switch. **The Edit-mode editor gains nothing
from any of this** — every advanced operation lives in Command mode only, and no
parallel keymap ever appears in ordinary typing.

### Entering and leaving Command mode

**Escape enters Command mode**, in the editor that has focus and only when that
editor is editable. Any of the **insert-entry** keys — `i` `a` `I` `A` `o` `O`
`s` `S` `cc` `C`, and also `v` and `V` — puts you back into Edit mode, as does a
`c{motion}` change, which by definition lands you typing. (`v` and `V` switch on
a **sticky selection** on their way out — see *Sticky selection*, below.)

**In Command mode the caret is a coloured block sitting *on* a character**,
rather than the thin bar between characters you get while typing. That is the
second thing telling you which vocabulary the editor is listening in, and it is
right where you are looking. It follows the theme, so it reads in both the light
and the dark scheme, and it is drawn only while the mode holds. The caret being
*on* a character is also why `$` and `l` stop on the line's last character
instead of past it — the one exception is straight after a `c`, which lands you
in Edit mode with an ordinary bar again.

**It belongs to one editor and it is transient.** Each tab is independent, and
**losing focus drops that editor straight back to Edit mode** — switching tabs,
clicking into another widget, opening the completion popup, running a `:`
command that opens a dialog. Coming back **never resurrects it**: there is no
memory anywhere of which tab was in Command mode. A half-typed command (`42d`)
is discarded at the same moment, and so is any command left pending when the
document is replaced under you.

**On a read-only editor, Escape does nothing and the whole layer is inactive.**
The read-only **DDL Explorer** buffers, the Raw XML editor while **Caption Mode**
or **Compare/Merge** holds it, the Activity Log's payload viewer: none of them
has an editing mode at all, so there is no *"motions work but deletes refuse"*
half-state to learn. If a mode turns the buffer read-only while you are in
Command mode, you are dropped back to Edit mode there and then.

**The mouse stays fully live in both modes, and never changes the mode.** Click,
drag-select, scroll and the context menu all behave identically; a click that
silently moved you out of a mode would make the indicator lie about a state you
never asked to leave. The **arrow keys**, **Home**, **End**, **Page Up** and
**Page Down** likewise move the caret in Command mode exactly as they do in Edit
mode.

**Escape in Command mode stays in Command mode.** If a count or an operator is
half-typed it is thrown away and you stay; if nothing is pending, nothing at all
happens. (The one exception is the **Edit code…** dialog — see the last section
of this chapter.)

### The mode indicator is your way back

If you press **Escape** by reflex and find that letters have stopped typing, the
thing that tells you so is the **mode indicator** (see *The Status Bar ▸ The mode
indicator*). It reads:

> **Command mode — press i to type**

**That indicator and its exit hint are the entire safety net, deliberately.**
There is no first-time dialog, no timeout, no opt-out and no warning beep —
just a chip that always says which vocabulary the editor is listening in, and
which says the way out inside its own label. It is shown twice for a main-window
editor (the Main Toolbar and the status bar) and once, on its own, inside the
**Edit code…** dialog.

**A command that cannot run says why, at the caret.** Every refusal below appears
as a small tooltip beside the caret, and — in the surfaces that report to it — as
a `[SQL]` line in the **Activity Log**. Nothing in Command mode fails silently
except **Tab**, and *Counts, and the three refusals that are not bugs* below says
why that one is the exception.

### The command set

This is the whole v1 vocabulary. Anything not on this list resets whatever was
half-typed and does nothing.

**Motions** — with an optional count before them (`5w`, `42j`):

| Keys | Move to |
|---|---|
| `h` `j` `k` `l` | left, down, up, right |
| `w` `b` `e` | next word start, previous word start, next word end |
| `0` `^` `$` | start of line, first non-blank of the line, end of line |
| `gg` `G` | first line, last line |
| `42G` | line 42 — an **absolute** line number |
| `f` `t` `F` `T` + a character | forward to / just before, backward to / just after that character, **on this line only** |
| `%` | the bracket matching the next one on this line |
| `{` `}` | the previous / next blank line |

**Operators** — `d` delete, `c` change (delete, then drop into Edit mode), `y`
yank (copy). Each takes a motion (`dw`, `c$`, `y}`), a **text object** (`daw`,
`ciw`, `yiw`), or is **doubled** to act on whole lines (`dd`, `cc`, `yy`).

**Text objects** — `aw` and `iw`, the two word objects, usable after any operator:

| Keys | What it takes |
|---|---|
| `aw` | the word under the caret **and its trailing whitespace** — *a word*. With nothing trailing (the last word on the line) it takes the **leading** whitespace instead, and from a gap it takes the gap plus the word after it |
| `iw` | the word under the caret and nothing else — *inner word*. From a gap it takes just the gap |

So `daw` deletes a word and the space after it, `ciw` replaces a word in place,
and `yiw` copies one. **Counts compose and multiply** exactly as they do with
motions: `3daw` takes three words with their spacing, and `2d3iw` is six.

**They never cross a line.** A word object is line-local, so a `daw` on the last
word of a line can never quietly join it to the next one; and a count that asks
for more than the line holds **refuses** — with a message beside the caret —
rather than taking what it can, which is the same rule `42j` follows.

**Shorthands**, which are just operator-plus-motion pairs spelled shorter:

| Key | Same as |
|---|---|
| `x` / `X` | delete the character after / before the caret |
| `D` / `C` | delete / change to the end of the line |
| `Y` | yank the whole line |
| `s` / `S` | change the character / the whole line |

**Other commands:**

| Key | What it does |
|---|---|
| `i` `a` `I` `A` `o` `O` | back to Edit mode — at the caret, after it, at the first non-blank, at the end of the line, on a new line below, on a new line above |
| `v` `V` | switch **sticky selection** (character-wise / line-wise) on, then back to Edit mode — **there is still no visual mode**, see below |
| `p` / `P` | paste after / at the caret |
| `r` + a character | replace the character under the caret with it |
| `u` | undo — the same undo the tab's own **Ctrl+Z** does |
| **Ctrl+R** | redo, **in Command mode only** |
| `/` | open this tab's **Find** field |
| `n` | find next |
| `:` | open the command line (see below) |

**Counts multiply, and they may sit on either side of an operator.** `3w` moves
three words, `2d3w` is the same as `d6w`, and `42G` and `G` are genuinely
different commands (`G` alone is the last line; `42G` is line 42).

**Three keys that would otherwise edit the buffer are given their vim meanings**
rather than being swallowed: **Backspace** acts as `h`, **Return** as `j` and
**Delete** as `x`.

### Counts, and the three refusals that are not bugs

Three deliberate behaviours look wrong the first time and are not:

- **`N` — search backwards — refuses, and says why.** `n` and `/` drive the app's
  own **Find** bar rather than a second search engine of their own, and that bar
  searches **forwards only**. Rather than invent a backwards search that exists
  nowhere else in the app, `N` states *"the Find bar searches forwards only —
  there is no backwards search to run"*. On a tab with no Find bar at all (the
  **Sandbox SQL Console**, the **Quality SQL Console**, the **Edit code…**
  dialog) `/` and `n` say that instead.
- **A count that overshoots refuses rather than clamping.** `42j` in a ten-line
  buffer does **not** quietly land you on the last line; it answers *"there are
  only 9 lines below the caret"* and leaves the caret where it was. Silently
  doing something near what you asked for is how you stop trusting the count at
  all. The same holds for `42G` in a shorter document, for `w` at the end of the
  buffer, for `f` with no such character on the line, and for `%` with no bracket
  to match — and for a **text object** with too few words left on the line, or
  none under the caret at all.
- **Tab is swallowed and answers nothing.** In Command mode, **Tab** and
  **Shift+Tab** do nothing at all — inserting a tab character would be an edit
  from a mode whose whole point is that letters are not text, and vim has no Tab
  command to borrow. This is the one key that is consumed without an explanation;
  the indicator is what tells you why nothing happened.

### Selecting, deleting and pasting — and what is deliberately absent

**There is still no visual mode**, and that is worth saying to anyone who expects
one: `v` and `V` do not put the editor into a third mode. They switch on **sticky
selection** (below) and drop you into **Edit mode**, where you select the Windows
way — with the mouse, with **Shift** plus a motion key, or with the sticky
selection they just started.

You have three ways to operate on a range:

1. **In Command mode**, operator plus motion or text object — `d}`, `y2w`, `cc`,
   `daw`.
2. **In Edit mode**, select however you like and use **Ctrl+C**, **Ctrl+X** or
   **Delete**.
3. **Select first, then use an operator on it.** With something selected, a
   Command-mode `d`, `c` or `y` acts on **the selection** and runs at once
   instead of waiting for a motion. That works for any selection — sticky, mouse
   or **Shift**-arrow — and it is what makes `v`, extend, **Escape**, `d` read
   the way a vim user expects.

One thing to keep straight: you have to be **in Command mode** for an operator to
be an operator. A `d` typed straight after a mouse selection while you are still
in Edit mode is the letter `d`, and it replaces what you selected.

**There is one clipboard — the system one — and no registers.** `y` and `Y` write
it, and so does **every delete**, which is what makes `dd` then `p` move a line.
It is the same clipboard **Ctrl+C** uses, so text moves freely between Command
mode, Edit mode and other applications. Two consequences follow directly and are
accepted rather than worked around:

- **`dd` clobbers your clipboard.** If you had something on it, it is gone. (What
  the delete took is recoverable with `u`.)
- **There is no linewise paste.** `p` and `P` paste **plain text, inline**,
  exactly as **Ctrl+V** does — so `yy` followed by `p` inserts the line's text at
  the caret rather than opening a new line for it. The two differ only in where
  the caret is: `p` pastes after it, `P` at it.

### Sticky selection

**Sticky selection is "keep selecting as I move", without holding Shift.** Turn
it on and every caret movement extends the selection from where you started,
until something ends the gesture. It comes in two granularities, and they are one
state rather than two — turning either on turns the other off:

- **Sticky Selection** — character-wise. `v`, or **Select ▸ Sticky Selection**.
- **Line Selection** — line-wise: the selection always covers whole lines. `V`,
  or **Select ▸ Line Selection**.

**Two ways in, one behaviour.** Pressing `v` or `V` in Command mode switches it
on and returns you to Edit mode; the two **Select** menu entries do exactly the
same thing and are **checkable**, so the menu always shows whether it is on.
Neither entry carries a keyboard shortcut — `v` and `V` are already the keys for
it, and one command gets one key.

**Both entries are hidden on a read-only editor** — either **DDL Explorer**
buffer, or the Raw XML editor while **Caption Mode** or **Compare/Merge** holds
it — because the whole Command-mode layer is inactive there and the toggle would
change nothing. Use **Shift** plus a motion key, or the mouse, to select in those.

**What extends it:** the **arrow keys**, **Home**, **End**, **Page Up** and
**Page Down** in Edit mode, and any Command-mode motion (`w`, `}`, `42G`) if you
press **Escape** and keep moving.

**What ends it:**

- an operator consuming it — `d`, `c` or `y` in Command mode, which acts on the
  selection and runs immediately;
- **typing a printable character**, which replaces the selection and resumes
  ordinary typing;
- a **mouse click**, since you are selecting by hand now;
- the editor **losing focus**, or its document being replaced.

It is transient editor state, like Command mode itself: nothing is stored,
nothing survives a tab switch, and there is no setting for it.

### Searching, and the colon command line

`/` focuses this tab's **Find** field and `n` runs its **Find next** — the same
bar, the same highlighting and the same results you get from **Ctrl+F**. There is
no second search anywhere in this app.

`:` opens a small command line **over the editor**, and **its vocabulary is the
app's own menu tree**. Typing matches against the full menu path, so `:deployqual`
finds **Deployment › Apply to quality** and **Enter** triggers exactly the menu
entry it names — the same command, with the same confirmations and the same
refusals. Nothing here is a separate command language, so it stays in step with
the menus by construction. **Escape** closes the line and returns you to Command
mode with the buffer untouched.

The one non-menu verb is **`:set`**, and it has exactly two options: **`:set
wrap`** and **`:set nowrap`**, which are the command form of the editors' own
*Wrap Lines* toggle. Anything else is refused by name. `:set` may only reach a
setting the app already has — the command line is not a place to invent one.

### Chords that change meaning in Command mode

Four keys behave differently depending on which mode the focused editor is in.
Apart from these — and **Escape** and **Tab**, above — everything in *Keyboard
Shortcuts* means the same thing in both modes.

| Chord | In Edit mode | In Command mode |
|---|---|---|
| **Ctrl+R** | focus this tab's **Replace with** field | **redo** |
| **Ctrl+D** | delete the character after the caret | **nothing** — consumed, reserved for a later scrolling command |
| **Ctrl+K** | delete from the caret to the end of the line | **nothing**, as above |
| **Ctrl+U** | delete the whole line | **nothing**, as above |

**Ctrl+Y is redo everywhere, in both modes, on both platforms** — it did not
move and it is not mode-dependent. `Ctrl+R` is redo *in addition*, and only while
Command mode holds, which is also why **Replace-focus is unavailable on that
editor** until you leave Command mode. If **Ctrl+R** ever seems dead, the mode
indicator is telling you why.

### The Edit code… dialog is the one surface that differs

The **Edit code…** dialog (see *The Code Editor*) has Command mode too, and
carries **its own mode indicator** under the editor — the same chip, showing the
editing mode and nothing else, because a dialog has no workflow mode to report.

Two things are different there, both on purpose:

- **Escape is a two-press cancel.** The first **Escape** enters Command mode; a
  second **Escape**, with nothing half-typed, **cancels the dialog**. That is how
  you close it from the keyboard: Command mode had taken away this dialog's only
  keyboard cancel, since **Ctrl+S** and **Ctrl+W** do nothing anywhere in the
  app. **Return** still accepts, and **Cancel** is still one click away. At the
  other five editing surfaces **Escape** in Command mode simply stays put; this
  dialog is the single exception, and it is a modal, which is why.
- **`:` is unavailable, and says so.** The command line's vocabulary *is* the
  menu tree, and this dialog is deliberately menu-less — so pressing `:` answers
  *"the ':' command line lists this window's menu commands, and this dialog has
  no menus"* rather than opening an empty command line you could type nothing
  useful into.

---

## Keyboard Shortcuts

**The keys below are the defaults, not fixed bindings.** Every shortcut that
belongs to a **menu command** can be rebound, cleared or put back — see
*Changing a shortcut*, below — so once you have customized something, these tables
tell you what that command *shipped* with rather than what it answers to today.
A short, reasoned list of keys cannot be changed at all; they are named in *What
cannot be rebound, and why*, at the end of this chapter.

**This reference is organised by *where you are*, not by chord, and that is not
tidiness — it is accuracy.** The same key genuinely means different things in
different surfaces: **Ctrl+Shift+B** selects an XML element in one editor and a
bracket pair in another, **Tab** inserts a tab everywhere except during a
template walk, and the SQL gestures are live in two places and inert in the rest.
A single flat chord-to-action list would have to state one of those as *the*
answer, and would be wrong most of the time it was read. Find your surface first;
then read the chord.

The app's editors come in **two families**, and most of the differences below
follow from which one you are in:

- **XML editors** — **Raw XML**, **Edit XSD** / **Edit AutoXSD**, and a generated
  **draft fragment** tab.
- **Code editors** — a **DDL object** tab, either **DDL Explorer**, a **PHP file**
  tab, either **SQL Console** (Sandbox or Quality), and the **Edit code…** dialog.

**Everything in this chapter describes an editor in Edit mode** — ordinary typing,
which is where every editor starts. Press **Escape** in an editable editor and it
switches to **Command mode**, where letters are commands and three of the chords
below change meaning; that vocabulary has its own chapter, *Editing Modes: Edit
mode and Command mode*.

**Everywhere in the app**

| Shortcut | Action |
|---|---|
| **F1** | Open the Manual (**Help ▸ Manual**). Reachable in every mode, including Maintenance mode |
| **Ctrl+C** / **Ctrl+X** / **Ctrl+V** | Copy / cut / paste. The editors' own built-ins; no menu command claims them. **Ctrl+Insert**, **Shift+Insert** and **Shift+Delete** are the older spelling of the same three and work everywhere too, and **Ctrl+Shift+Insert** is a second paste the app binds itself in every editor |
| **Ctrl+D** / **Ctrl+K** / **Ctrl+U** | Delete the character after the caret / to the end of the line / the whole line. See *Three line-editing keys*, below |
| **Escape** | Enter **Command mode** in the editor you are typing in — after three narrower meanings have had their turn. See *Editing Modes* and *What Escape means where*, below |
| **Ctrl+S** / **Ctrl+Shift+S** | **Nothing — deliberately unbound.** Every save is a named entry on **Deployment** (see below) |
| **Ctrl+O** / **Ctrl+W** | **Nothing.** Both were unbound rather than moved, and both are free for you to assign (see below) |
| **Ctrl+Shift+Z** | **Select ▸ Shrink Selection.** It is **not** a redo chord — every editing surface catches it, and in the SQL editors it steps the selection inward (see *Expanding and shrinking the selection*, below) |
| **Alt+Backspace** / **Alt+Shift+Backspace** | **Nothing.** Suppressed in every editor, on both platforms (see *Undo and Redo*, below) |

**On any editor tab**

These come from the **Editor menu bar**, so they follow the tab in front of you
and act on it — never on the Raw XML document behind it.

| Shortcut | Command | Notes |
|---|---|---|
| **Ctrl+A** | **Select ▸ Select All** | Select the whole document. See *Ctrl+A is a special case*, below |
| **Ctrl+Shift+B** | **Select ▸ Select Enclosing Block** | One command, two structural meanings — see *One chord, two meanings*, below |
| **Ctrl+Shift+A** | **Select ▸ Expand Selection** | One structural unit outward per press, repeatable. Everywhere except PHP / JS tabs, where the entry is hidden and the chord goes quiet with it |
| **Ctrl+Shift+Z** | **Select ▸ Shrink Selection** | Back inward, one step per press. **SQL editors only**; not rebindable — see *Expanding and shrinking the selection*, below |
| **Ctrl+F2** | **Navigation ▸ Toggle Bookmark** | Disabled for as long as **Caption Mode** lasts |
| **F2** / **Shift+F2** | **Navigation ▸ Next / Previous Bookmark** | Disabled for as long as **Caption Mode** lasts |
| **Ctrl+F** | *(no menu entry)* | Focus this tab's **Find** field |
| **Ctrl+R** | *(no menu entry)* | Focus this tab's **Replace with** field — **in Edit mode**. In Command mode this chord is redo instead (see *Editing Modes*) |
| **F3** | *(no menu entry)* | Find next in this tab's bar — and it works with the caret still in the **editor**, which is the whole point of it |
| **Escape** | *(no menu entry)* | In a Find/Replace bar: return focus to the document. The bar is never hidden. With the caret in the editor: enter **Command mode** |

**Ctrl+F / Ctrl+R belong to the tab, not to the window.** Six surfaces own their
own pair — Raw XML, Edit XSD, a draft fragment tab, a PHP tab, a DDL object tab
and either DDL Explorer — plus **Caption Management**, which has a seventh. Each
pair is live only while its own surface has focus, which is why Find in the
caption grid can never search the Raw XML by accident. **Four surfaces have no
Find/Replace bar at all** — the **Manual** tab, the **Diff / Merge** tab and both
**SQL Consoles** — so **Ctrl+F**, **Ctrl+R** and **F3** do nothing there.

**Three line-editing keys, in every editor**

| Shortcut | Action |
|---|---|
| **Ctrl+D** | Delete the character **after** the caret — or the selection, when there is one |
| **Ctrl+K** | Delete from the caret to the end of the line. Pressed with the caret already at the end of a line it takes the newline instead, joining the next line up, which is what makes repeated presses useful. At the very end of the document it does nothing |
| **Ctrl+U** | Delete the whole line, as **one** undo step — one **Ctrl+Z** brings it back. With a selection it deletes exactly the selection |

**The app implements these three itself, identically on Windows and on Linux.**
They are not the system's: the KDE desktop binds them inside every text box and
Windows binds nothing at all, which would have made the same key do two different
things on two machines. All three are live in every editing surface — the XML
editors and the code editors alike — and on the read-only **DDL Explorer** they
state *"this buffer is read-only"* rather than doing nothing. In **Command mode**
all three are inert (see *Editing Modes ▸ Chords that change meaning*).

**In an XML editor** (Raw XML, Edit XSD / Edit AutoXSD, a draft fragment tab)

| Shortcut | Action |
|---|---|
| **Ctrl+Space** | Attribute / value completion, from the schema |
| **Ctrl+Shift+B** | Select the innermost enclosing **XML element**, `<` through `>` |
| **Ctrl+Shift+A** | **Expand Selection** — one nesting level up, repeatable |
| **Ctrl+L** | **Go To XSD** — jump to the definition of the attribute at the caret, in the Edit XSD tab |
| **Ctrl+Alt+F** | **Format Selection** — re-indent the selected XML by element depth. Needs a selection (see *The Autoformatter*) |
| **Ctrl+Z** / **Ctrl+Y** | Undo / redo, routed by tab — see the undo table below |
| **Return** | Newline, indented to match the line you left |
| **<** | Auto-closes: types `<>` and leaves the caret between them |
| **>** | Closes the tag you just opened, when there is one to close |
| **Ctrl+click** | Jump to the matching open/close tag |
| **Alt+click** | Jump to the parent element's opening tag |

**In a code editor** (DDL object tab, either DDL Explorer, PHP tab, Sandbox SQL
Console, **Edit code…** dialog)

| Shortcut | Action |
|---|---|
| **Ctrl+Shift+B** | Select the innermost balanced **bracket pair** — `()`, `[]` or `{}` |
| **an opener or a quote** | Auto-closes; with a selection it **wraps** the selection instead of replacing it |
| **a closer the editor inserted** | Types *through* it rather than inserting a second one |
| **Tab** | Insert a tab character — **except** during a template walk, below |
| **Ctrl+Alt+E** | Expand the word before the caret into its plpgsql snippet. **SQL buffers only** |
| **Ctrl+Alt+C** | Expand a bare `SELECT` into the column list its `FROM` implies. **SQL buffers only** |
| **Ctrl+Shift+R** | **Reload DDL** — re-introspect this explorer. **Either DDL Explorer's viewing pane only**, and it reloads the one the caret is in (see *DDL Explorer ▸ Reloading an explorer*) |

**The set Ctrl+Alt+E expands is editable** — eight snippets ship with the app and
you can change, add to or replace them in **Settings ▸ Software settings… ▸
Snippets** (see *Snippets*). The chord itself stays what it is; only what it
inserts changes.

**Ctrl+Alt+E and Ctrl+Alt+C are SQL-only by design.** The snippet set is plpgsql,
so in a **PHP** tab or a `js` **Edit code…** dialog these keys are untouched — an
expansion that dropped plpgsql into a PHP body would be a bug, not a convenience.
In the read-only **DDL Explorer** they are live but state **"this buffer is
read-only"** rather than doing nothing; and where no schema is wired,
**Ctrl+Alt+C** answers *"expanding a SELECT needs a database schema, and this
editor has none"*. A gesture that cannot run always says why (see *DDL Explorer ▸
Schema-aware completion and gestures in the SQL editors*).

**While a template walk is in progress** (after an expansion that left
placeholders)

| Shortcut | Action |
|---|---|
| **Tab** | Jump to the next placeholder, selecting it |
| **Shift+Tab** | Jump to the previous placeholder |
| **Escape** | Leave the walk. **Tab** is a tab character again |

Nothing else changes while the walk is on, and the walk also ends when you click
anywhere or the editor loses focus. Outside a walk these three keys are exactly
what they always were.

**What Escape means where.** One key, several answers, and the first one that
applies wins:

1. the **completion popup** is open → close it, inserting nothing;
2. the caret is in a **Find/Replace bar** field, or the caption bar → return
   focus to the document (or to the caption grid). The bar is never hidden;
3. a **template walk** is in progress → leave the walk;
4. the caret is in an **editable editor** → enter **Command mode**; or, already
   in Command mode, discard a half-typed command and stay there (see *Editing
   Modes*);
5. the caret is in a **read-only** editor → nothing at all;
6. the **Edit code… dialog** with nothing pending → cancel the dialog. That is
   the second of its two Escape presses, and the only surface where Escape leaves
   Command mode.

**In a DDL object tab or either SQL Console — and only there**

These five need to know your database's schema, so they are live in exactly the
surfaces that have one wired and **inert in the other three code editors**
(the DDL Explorer, a PHP tab, the **Edit code…** dialog).

| Shortcut | Action |
|---|---|
| **Ctrl+Space** | Schema-aware name completion — the `schema.table.column` cascade, a `FROM`-clause alias, a `%ROWTYPE` local, or `NEW.`/`OLD.` columns |
| **Ctrl+Alt+J** | Write the `JOIN … ON …` a foreign key implies (one candidate is applied, several are offered) |
| **Ctrl+Shift+Space** | Signature help for the call at the caret — a tooltip, inserting nothing |
| **Ctrl+Alt+F** | **Format Selection** — reindent the current selection with the SQL formatter. Needs a selection. (Not one of the five: the same chord formats **XML** in the XML editors — see *The Autoformatter*) |
| **Ctrl+Return** | *(SQL Consoles only)* Run the selection, or the whole buffer — against the sandbox in the Sandbox console, and into an **uncommitted** transaction in the Quality console, where it never commits (see *The Quality SQL Console*) |

**While the completion popup is open**

The popup is its own small widget with its own keys, so these override whatever
the editor underneath would have done:

| Shortcut | Action |
|---|---|
| **Tab**, **Return** / **Enter** | Insert the highlighted item. (This is the popup's Tab, not the template walk's) |
| **Up** / **Down** | Move through the list |
| any printable character | Narrow the list |
| **Backspace** | Widen it again |
| **Escape** | Close the popup, inserting nothing |

**In Caption Management**

| Shortcut | Action |
|---|---|
| **Ctrl+F** / **Ctrl+R** | Focus the caption bar's **Find** / **Replace with** field |
| **Escape** | Return focus from the bar to the **grid** |
| **Ctrl+G** | Go to the current row's line in the Raw XML — and it works from inside the **Find** field too, so you can search for a caption and jump straight to its line without leaving the field |
| **Ctrl+C** / **Ctrl+V** | Copy the selection out of the grid / paste into the New value column. Both belong to the **grid**: pressed while the cursor is in the Find or Replace field they copy and paste that field's text, as they would anywhere else |

**In the Edit code… dialog** (and the Activity Log's read-only payload viewer)

**The dialog has no menu bar**, so every menu-borne chord above is simply absent
in it. What it does answer is what the editor widget itself handles, plus Qt's
own dialog defaults:

| Shortcut | Action |
|---|---|
| **Ctrl+Shift+B** | Bracket-select. The dialog carries this one chord itself, which is the only reason it works here — and the only reason it does not follow a rebinding (see *The Code Editor ▸ Editing*) |
| **Return** | OK (Qt's default for the dialog's button box) |
| **Escape** | **Press once** to enter **Command mode**; **press again**, with nothing half-typed, to **Cancel**. See *Editing Modes ▸ The Edit code… dialog is the one surface that differs* |
| **Ctrl+S** / **Ctrl+W** | **Nothing.** This dialog was the last carve-out for either chord and no longer answers them |

The dialog also carries **its own mode indicator**, under the editor, showing
which editing mode that editor is in and nothing else. **The `:` command line
does not work here** — its vocabulary is the menu tree and this dialog has none,
so it says so.

**The Activity Log's payload viewer is the read-only twin of this dialog**, so
the editing-mode layer is inactive in it and **one Escape closes it**, as it
always did.

**Undo and Redo depend on which tab you are in**

**Ctrl+Z** and **Ctrl+Y** are one pair of keys over several different histories,
and the tab decides which one. **Redo is Ctrl+Y on every platform and there is no
second redo chord** — see *Ctrl+Shift+Z is not redo*, below.

**History ▸ Undo Project Edit** and **History ▸ Redo Project Edit** on the Editor
menu bar are a different command, which is why they are named apart from the keys.
They always drive the **project's** snapshot history, whatever tab is in front: a
chord means *"undo here"* and is answered by the surface you are in, while clicking
one of these means *"undo the project, wherever I am"*. **Neither carries a
keyboard shortcut at all** — the pair could not share a key with Ctrl+Z without
losing that distinction. (You may still assign them one yourself in the
**Keyboard shortcuts** pane, where they are ordinary rebindable menu commands.)

| Where | **Ctrl+Z** / **Ctrl+Y** undoes |
|---|---|
| **Raw XML** | the **project's** snapshot history (the same one **History…** navigates) |
| **Edit XSD / Edit AutoXSD** | that tab's own editing history — never the project's |
| **DDL object tab** | that tab's own editing history. One **Ctrl+Z** takes back a whole template expansion, however many pieces it was built from |
| **PHP file tab** | that tab's own editing history |
| **Sandbox SQL Console**, **Quality SQL Console** | that editor's own editing history |
| **a draft fragment tab** | that tab's own editing history, keystroke by keystroke. A draft has no snapshot history and no save path, so there is nothing else for the keys to mean |
| **DDL Explorer** (either) | nothing — the buffer is read-only, and the key says so: *"this buffer is read only — there is nothing to undo here"* |

**The read-only Explorer answers rather than staying silent, and that is a
safety fix, not a courtesy.** Because a read-only editor never claims those keys
for itself, **Ctrl+Z** used to fall through to the window and quietly revert the
**Raw XML project buffer** — a different document than the one on screen. The
Explorer now claims the chord and states the reason above instead.

**Undo Project Edit and Redo Project Edit refuse out loud, too.** While the Raw
XML buffer is held read-only — by **Caption Mode**, or by **Compare/Merge**'s
data-loss lock — the two entries stay clickable rather than greyed, and clicking
one puts its reason in the status bar: *"Raw XML is read only in … — project
history cannot change it."* Jumping to a snapshot from **History…** is held by
the same lock. An entry that states why it will not run beats one that has
silently vanished (see *Compare / Merge* and *Caption Management*).

**Ctrl+Shift+Z is not redo, anywhere in this app.** It used to be a second redo
chord and is not one any more: **redo is Ctrl+Y, on every platform, and nothing
else**. One operation with two spellings meant one of them was always the one a
given surface had forgotten to wire, and on one platform the "second" redo was a
dead key.

The chord now belongs to **Select ▸ Shrink Selection** (see *Expanding and
shrinking the selection*, below) — but the reason it can only ever be that, and
never a rebindable command of your choosing, is the same reason it stopped being
redo. Qt itself binds `Ctrl+Shift+Z` as its own native redo inside every text
widget, on both Windows and Linux, so **every editing surface in the app catches
the chord before Qt can**, which is the only way to stop Qt's redo from firing
behind the app's back and editing a buffer without a history entry. In the SQL
editors that catch now runs shrink; in the XML editors and on a PHP tab it still
runs nothing, on purpose. It stays reserved either way: a command retargeted onto
it would be swallowed by whichever editor has focus (see *What cannot be rebound,
and why*).

The read-only **DDL Explorer** is worth one extra word: `Ctrl+Shift+Z` shrinks the
selection there like in any other SQL editor — read-only makes no difference to
selecting — and it does **not** print the *"nothing to undo here"* sentence it
prints for **Ctrl+Z** / **Ctrl+Y**. The chord is not asking for an undo, so
answering it with an undo's reason would be a wrong reason, which is worse than
none.

**Alt+Backspace and Alt+Shift+Backspace are suppressed in the same way.** Qt binds
them as native undo and redo on **Windows only**, and a chord has to mean the same
thing on both systems or not be bound at all. Rather than invent them on Linux —
they appear in no menu, no shortcut table and nowhere in this manual — every
editing surface consumes them and runs nothing, so the two keys are equally dead
on both platforms. They are reserved for the same reason `Ctrl+Shift+Z` is.

**Ctrl+A is a special case, and the reason is worth knowing.** Select-all always
worked in every editor; the **Select** menu only made it findable. While the caret
is in a text field or an editor, **that widget still handles Ctrl+A itself** —
Qt lets a text control claim the standard editing chords before the window's menu
action ever sees them. So the menu command's own shortcut fires only when focus is
somewhere else, such as the project tree, and it then acts on the active editor.
The practical consequences: the command cannot steal **Ctrl+A** from a text field,
and it works in the read-only buffers too. **Select All is also not gated in
Caption Mode**, unlike Find and Replace, because selecting text mutates nothing.

**One chord, two meanings: Ctrl+Shift+B.** **Select ▸ Select Enclosing Block** is
a single command that asks the editor in front of you what "the enclosing block"
means. In an **XML editor** the answer is the innermost XML element; in a **code
editor** it is the innermost balanced bracket pair, because SQL and PHP have no
tags to enclose. It is one command with one key, not two competing ones.

### Expanding and shrinking the selection

**Ctrl+Shift+A grows the selection outward one structural unit per press, and
Ctrl+Shift+Z steps it back inward.** Press **Ctrl+Shift+A** with the caret in a
plpgsql routine and it selects the word you are on; press it again for the
enclosing bracket group (its contents first, then the brackets too); again for the
clause; again for the statement; then once for **each** enclosing block, so an
`IF` inside a `FOR` inside a `BEGIN` is three more presses; and finally the whole
`BEGIN … END` body. Inside a `CASE` the current `WHEN … THEN` branch is a rung of
its own before the whole `CASE`. **Ctrl+Shift+Z** walks back down the same steps.

The point is **identifying** structure fast: selecting a `CASE` to delete it, a
`LOOP` to reindent it, or a statement to comment it out, without a mouse.

- **Not every rung exists everywhere, and that is deliberate.** Where there is no
  clause keyword to anchor on — a bare assignment, a `RAISE NOTICE` — there is
  simply no clause rung, and the press that would have taken it goes straight to
  the statement. A rung may be missing; a rung that fires and changes nothing
  never happens, because then you could not tell whether the ladder advanced or
  ended.
- **At the top, Ctrl+Shift+A does nothing** rather than announcing anything.
  Selecting changes no text, so there is nothing to report.
- **Strings, comments and quoted names are one rung each** — there is no structure
  to climb inside a literal — while a `$$ … $$` routine body is climbed *into*,
  because that body is the plpgsql this ladder exists for. A bracket inside a
  string is not a bracket here.
- **Ctrl+Shift+Z after a mouse selection, or after any edit, still works** — it
  selects the largest structural unit lying wholly inside what is currently
  selected, and does nothing when nothing is. So the key always moves the
  selection inward, whether or not you got there with **Ctrl+Shift+A**.

**Which surfaces offer which half:**

| Where | Expand Selection (Ctrl+Shift+A) | Shrink Selection (Ctrl+Shift+Z) |
|---|---|---|
| DDL object tabs, either **DDL Explorer**, either **SQL Console** | yes — the full plpgsql ladder | yes |
| **Raw XML**, **Edit XSD**, generated draft fragment tabs | yes — one XML nesting level per press, as before | no — the entry is not offered |
| **PHP** / **JavaScript** tabs, the **Edit code…** dialog for event code | no | no |

**Read-only makes no difference to either**, in the DDL Explorer or in Caption
Mode: selecting text mutates nothing, exactly as with **Select All**.

**Shrink Selection is the one Select command you cannot rebind.** Its menu entry
carries no shortcut of its own: **Ctrl+Shift+Z** is caught inside every editor's
own key handling, which is what stops Qt from treating it as a second redo (see
*Ctrl+Shift+Z is not redo*, above), and a key caught there cannot also be a
window command. So **Ctrl+Shift+A** can be moved through the **Keyboard
shortcuts** pane while **Ctrl+Shift+Z** cannot, and cannot be given to anything
else either. The pairing was worth the asymmetry; the asymmetry is real.

**Select Parent Block was renamed.** It is now **Expand Selection**, on the same
key, because the command means the same thing in the SQL editors as in the XML
ones. A toolbar button or a custom shortcut you saved under the old name still
works.

**Ctrl+S and Ctrl+Shift+S are unbound app-wide, and that is stated here rather
than merely left out of the table.** Every save is a named entry on the Editor
bar's **Deployment** menu — **Save pgtp** / **Save as new pgtp** on Raw XML,
**Save in Project** on a DDL object tab, **Save XSD**, **Save PHP File** (see
*The Deployment Menu*). Pressing the old keys produces **no write, no message and
no hint**: the dispatcher behind them had to guess which tab you meant and got it
wrong on six of them, and one reflex that is right here and silently wrong there
is worse than none. **There is no carve-out left** — the **Edit code…** dialog
was the last one, and it no longer answers Ctrl+S either (see *The Code
Editor*). Neither key can be handed to a different command — see *What cannot be
rebound, and why* — so the reflex cannot come back through the side door.

**Two chords were deleted and are not coming back as chords:** **Ctrl+Shift+F**
(Find All) and **Ctrl+Alt+Return** (Replace All). Both commands are buttons on the
now-permanent Find/Replace bar, which is in front of you whenever they apply — and
both are broad enough to deserve a deliberate click (see *Find, Replace & Find
All*).

**File ▸ Open... has no shortcut any more.** **Ctrl+O** used to open a `.pgtp`,
and it was unbound rather than moved: this app opens `.pgtp` files, PHP files,
projects, XSDs and database objects, so one **Ctrl+O** has to pick a winner among
five kinds of "open" — and whichever it picks is a guess about which one you
meant. Opening is also a once-per-session act the launcher already puts one click
away (see *Getting Started ▸ The startup launcher*). Pressing **Ctrl+O** now does
nothing, and the chord is genuinely **free**: if you want it back on a particular
open, assign it yourself in the **Keyboard shortcuts** pane.

**Ctrl+W is in exactly the same position.** It used to close the project from
the File menu and to cancel the **Edit code…** dialog; both bindings were
removed, for the same reason — this app has `.pgtp` tabs, PHP tabs, DDL object
tabs, the XSD tab and console tabs, so one **Ctrl+W** would have to pick a
winner among five kinds of "close". It now does nothing anywhere, and like
**Ctrl+O** it is **free** for you to assign to whichever close you actually
mean. (Unlike **Ctrl+S**, neither chord is reserved.)

**No entry on the Deployment menu carries a shortcut** — not one of the nine.
**Compare/Merge pgtp**, **Save pgtp**, **Save as new pgtp**, **Deploy .pgtp**,
**Save in Project**, **Check and commit to sandbox**, **Apply to quality**, **Save
XSD** and **Save PHP File** are all menu-only, the saves because a keystroke save
is exactly the wrong-target hazard described above, and the pushes because *an
irreversible outward effect must not be one keystroke away*.

**Nothing that reaches a database from a DDL object tab has a shortcut, on
purpose** — not **Check and commit to sandbox**, not **Apply to quality**, and not
either check gesture (**Parsing ▸ Check Object in Sandbox** and **Parsing ▸ Check
and rollback**), so a write to a database is never one keystroke away.
**Ctrl+Return** in the two SQL consoles is the one exception, and it holds the
rule rather than breaking it. In the **Sandbox** console it can only ever reach
the disposable sandbox (see *The Sandbox*). In the **Quality** console it reaches
production — but it runs into an **uncommitted** transaction, and the gesture
that makes anything durable, **Commit**, is a button with no shortcut, no menu
entry and no mnemonic. The irreversible step is still never one keystroke away
(see *The Quality SQL Console*).

The other commands added recently are shortcut-free too: **File ▸ New
Session**, **File ▸ Discard Changes**, **File ▸ Project Status…** (which lives on
**File**, directly under **Project Settings…**, and not on **Database** where it
used to sit), **Parsing ▸ Auto Parse XML**, **Parsing ▸
Validate Project**, **History ▸ History…**, **History ▸ Undo Project Edit**,
**History ▸ Redo Project Edit**, **Navigation ▸ Clear All Bookmarks**,
**Navigation ▸ List All Bookmarks**, all three of **Navigation**'s Compare/Merge
entries, **View ▸ Activity Log**, **View ▸
Messages**, **View ▸ Findings**, **Database ▸ DDL Explorer (Quality)**,
**Database ▸ DDL Explorer (Sandbox)**, **Database ▸ Reload DDL**,
**Database ▸ Sandbox SQL Console…**, **Database ▸ Quality SQL Console…**,
**Settings ▸ Software settings…** and
**Tools ▸ Start MCP Server** are all menu-only. If you use one often, put it on
the toolbar (see *Appearance & Layout ▸ The toolbar*).

**Select ▸ Sticky Selection and Select ▸ Line Selection are keyless for a
different reason** — not because a key would be dangerous, but because they
already have one. `v` and `V` in Command mode are those commands, and one command
gets exactly one keyboard host, so the menu entries carry nothing (see *Editing
Modes ▸ Sticky selection*).

**Database ▸ Reload DDL is the interesting one of those**, because a keyboard
gesture for it *does* exist: **Ctrl+Shift+R**, hosted on the DDL Explorer's
viewing pane, where the caret says which of the two explorers you mean. A menu
entry cannot say that, and one gesture gets exactly one keyboard host — so the
menu entry and both right-click forms are deliberately keyless (see *DDL Explorer
▸ Reloading an explorer*).

**The Settings menu contributes no chords at all, by rule.** It exists only in
Maintenance mode, and hiding a menu does not switch off the keys of the entries
inside it — so a shortcut on its one entry, **Settings ▸ Software settings…**,
would open that dialog in the middle of ordinary work and make nonsense of where
the command lives. Nothing on that menu ships with a key. The **Keyboard
shortcuts** pane will still let you assign one, because it lists every menu
command in the app — but a key you assign there behaves exactly as described: it
fires in any mode (see *Software Settings*).

**Ten keys have no menu-bar entry at all** — **F3**, **Ctrl+L**, **Ctrl+Alt+F**,
**Ctrl+Return**, **Ctrl+Space**, **Ctrl+G**, and the four SQL editor gestures
**Ctrl+Alt+E**, **Ctrl+Alt+C**, **Ctrl+Alt+J** and **Ctrl+Shift+Space** (see
*DDL Explorer ▸ Schema-aware completion and gestures in the SQL editors*). Some
of them do have a right-click form; none has a menu-bar command. That
is why you can neither put them on the toolbar nor rebind them: a toolbar button
*is* a menu item and the rebinding dialog lists menu commands, and these have no
menu-bar entry to be either. **Ctrl+Shift+R** is locked for a near-identical
reason with the opposite starting point — its command *is* on the menu bar, but
the chord itself is hosted on a panel. All of them are still **listed** in the
**Keyboard shortcuts** pane, as greyed rows saying why they are locked — a key
you can see and cannot take is better than one that is simply missing from the
list.

In **Caption Mode** the **Navigation** menu's five bookmark entries — and
**Ctrl+F2** / **F2** /
**Shift+F2** with them — are disabled for as long as the mode lasts, because the Raw
XML editor they act on is read-only there; the gutter still sets bookmarks (see
*Bookmarks*). **Select ▸ Select All is deliberately not gated**, because selecting
text mutates nothing. While the Caption Management tab itself is in front, the
Editor menu bar is hidden entirely (see *The Two Menu Bars*).

**Maintenance mode hides menus; it does not disable their keys.** The mode trims
the window menu bar down to **File**, **Schema**, **Settings** and **Help** (see
*Getting Started ▸ Maintenance mode*), and hiding means *"not in your way"*, never
*"prevented"* — a command whose menu is hidden keeps working, from the toolbar and
from its keyboard shortcut. In practice this changes nothing you can feel, because
**none of the menus the mode hides ships with a shortcut**: every default chord in
this chapter belongs either to the Editor menu bar, which the mode leaves entirely
alone, to **Help ▸ Manual**, which no mode may put out of reach, or to an editor
widget. It matters only if *you* have assigned a chord to a command on **View**,
**Database**, **Tools** or **Generation** — that chord stays live in Maintenance
mode even though its menu is gone.

### Changing a shortcut — the Keyboard shortcuts pane

**Settings ▸ Software settings… ▸ Keyboard shortcuts** lists every menu command
in the app with the key it currently answers to, and lets you change it. It is
the pane directly under **Toolbar** and is its sibling: the same set of commands,
customized on its other axis — one picks a command's icon and place on the
toolbar, this one picks its key. (It used to be **View ▸ Customize Shortcuts…**;
that entry is gone, and reaching this pane means entering Maintenance mode — see
*Software Settings*.)

The pane is one table with three columns:

- **Command** — the command's menu path, exactly as the **Toolbar** pane spells it
  (`File › Discard Changes`, `Deployment › Save pgtp`, `Navigation › List All
  Bookmarks`).
- **Shortcut** — the key it answers to right now. Blank means the command has no
  key, which is the normal state for most of them.
- **Note** — `default: Ctrl+F2` (or `default: (none)`) on any row you have moved
  off what it shipped with, so you can always see what a reset would give you
  back. Reserved rows use it to say why they are locked.

Under the table sit a **New shortcut** capture field and four buttons:

- **Assign** — select a command's row, press the chord you want in the capture
  field, then press Assign.
- **Clear** — leave the selected command with no key at all. That is a real
  state, not a broken one; the command stays on its menu.
- **Reset to Default** — put the selected command back on the key it shipped
  with. This genuinely works even after several rebindings, because the app
  captures each command's original key once, at startup, before any of your
  changes are applied, and never overwrites that record.
- **Restore All Defaults** — the same thing for the whole list at once.

**OK applies your changes immediately** — the new keys work in the window you are
already in, with nothing to restart — and remembers them for future sessions,
beside your toolbar arrangement. **Cancel changes nothing**, neither in the
running window nor on disk. Both belong to this pane; the settings window's
**Close** is neither, and closing it saves nothing (see *Software Settings*).

**Assigning a key another command already holds takes it from that command.**
Before you commit, a line under the table names the current holder (*"Ctrl+F2 is
already bound to Navigation › Toggle Bookmark. Assigning it here will clear that
binding."*), and
after you commit it says whose binding was cleared. The loser is left **unbound**
— its row stays, it simply has no key.

That may look aggressive, and it is deliberate: **two commands sharing one chord
is ambiguous, and Qt then fires neither of them**. A double binding does not mean
"the first one wins"; it means *both* commands silently vanish from the keyboard.
Stealing is what prevents that, so a key always has exactly one owner.

**A key held by something that is not a menu command is refused, not stolen.**
The pane can only change menu commands, so it has no way to release a key that
a window-level shortcut, a per-tab Find field or an editor widget's own key
handling answers to — and stealing what it cannot release would produce exactly
the ambiguity above. The refusal appears on the same line as the warnings, naming
the reason, and nothing is changed.

**The list is the whole command universe, not what happens to be visible.** A
command hidden by **Maintenance mode**, or by the per-tab filtering that shapes
the Editor menu bar and the **Deployment** menu, still has a row here — so you can
rebind **Save PHP File** with no PHP tab open, and the list never changes shape
depending on which tab you happened to be looking at.

Your overrides are stored with the app's other settings and pruned sensibly on
load: an override for a command that no longer exists is quietly dropped, one made
against a command that has since been renamed follows the rename, and a command
you never customized always follows whatever default a later version of the editor
gives it.

> **One caveat: the Edit code… dialog keeps Ctrl+Shift+B.** Rebinding **Select ▸
> Select Enclosing Block** moves the command everywhere it is a menu command —
> every editor tab, XML and code alike, including PHP tabs, DDL object tabs, both
> DDL Explorers and both SQL Consoles. The one place your new key does not
> reach is the menu-less **Edit code…** dialog, which carries **Ctrl+Shift+B**
> itself precisely because it has no menu bar and therefore no command to rebind
> (see *The Code Editor ▸ Editing*). There the chord stays what it shipped as.

### What cannot be rebound, and why

The dialog shows the pinned keys as **greyed, read-only rows** rather than leaving
them out, so you can see that the key exists and why it is locked instead of
hunting for a row that was never there. None of these is arbitrary:

| Reserved | Why |
|---|---|
| **Ctrl+S** / **Ctrl+Shift+S** | Deliberately unbound app-wide since saving moved to the **Deployment** menu (see *Getting Started ▸ Saving, closing, discarding*). Letting another command take them would bring the old reflex back by the side door. |
| **Ctrl+Z** / **Ctrl+Y** | Undo and Redo in whichever surface has focus: a window-scoped shortcut *plus* every editor's own key handling, and not a menu command, so there is no row to move them from. **Ctrl+Y** is bound by this app on every platform rather than inherited from the system, because Qt binds it only on Windows. The project-scoped twins — **History ▸ Undo Project Edit** and **History ▸ Redo Project Edit** — are ordinary menu commands and **are** rebindable. |
| **Ctrl+Shift+Z** | **Not redo** (see *Undo and Redo*, above) and not free either: every editing surface catches it so Qt's own native redo cannot fire, so a command moved onto it would be swallowed by whichever editor has focus. It answers **Select ▸ Shrink Selection**, which is therefore the one **Select** command you cannot rebind — see *Expanding and shrinking the selection*. |
| **Alt+Backspace** / **Alt+Shift+Backspace** | Qt binds them as undo and redo on the **Windows** scheme only, so every editing surface consumes them and runs nothing — that suppression is what makes the keyboard identical on both platforms. A command retargeted here would be swallowed the same way. |
| **Ctrl+F** / **Ctrl+R** | They focus the **current tab's** Find and Replace fields, and each tab's bar owns its own pair. A window-level menu shortcut on either key would be ambiguous against them, and neither would fire. **Ctrl+R** is additionally redo while an editor is in **Command mode** (see *Editing Modes*), which is one more thing no menu command could share it with. |
| **Ctrl+D** / **Ctrl+K** / **Ctrl+U** | The three line-editing gestures, implemented by the app inside every editing surface so that they mean the same thing on Windows and on Linux. A menu command retargeted onto one of them would be swallowed by whichever editor has focus — and would break the gesture app-wide. |
| **Escape** | Returns focus from a Find/Replace bar to the document, leaves a template walk where one is in progress, closes the completion popup — and enters **Command mode** in an editable editor. Six meanings answered by six different widgets; a menu command pointed here would be swallowed by whichever one has focus. |
| **F3**, **Ctrl+L**, **Ctrl+Alt+F**, **Ctrl+Return**, **Ctrl+Space**, **Ctrl+G** | Window-level, per-panel or context-menu commands with no menu-bar entry at all — the same reason they cannot be put on the toolbar. |
| **Ctrl+Shift+R** | **Reload DDL**. The command *does* have a menu entry — **Database ▸ Reload DDL** — but the chord's one host is a shortcut on the DDL Explorer's viewing pane, because the caret is what says which of the two explorers to re-introspect. There is no menu row holding this key for the dialog to move, and a command pointed here would be swallowed by whichever explorer buffer has focus. |
| **Ctrl+Alt+E**, **Ctrl+Alt+C**, **Ctrl+Alt+J**, **Ctrl+Shift+Space** | The four SQL editor gestures. Each is answered by the editor or its panel rather than by a menu command, so the dialog has no row it could move — and a menu command retargeted onto one of them would fight for the key and neither would fire. **Ctrl+Alt+J** and **Ctrl+Space** are answered by the *panel* specifically, because they need the database schema and no editor widget is allowed to hold one — that is the same rule that keeps an editor from ever talking to a database. |
| **Ctrl+C** / **Ctrl+X** / **Ctrl+V**, and **Ctrl+Insert** / **Shift+Insert** / **Ctrl+Shift+Insert** / **Shift+Delete** | Copy, cut and paste are the editors' **own** built-ins, and the Insert/Delete group is the older spelling of the same three — every text field and table in the app answers both spellings, and **Ctrl+Shift+Insert** is a paste the app binds itself in every editor so that it exists on both platforms. A window-level shortcut on any of them would outrank the editor and break copy, cut or paste everywhere in the app. **Ctrl+C** and **Ctrl+V** are additionally the caption grid's own copy and paste. |
| **F1**, and **Help ▸ Manual** itself | The universal convention, and **Help ▸ Manual** is the one entry no mode may put out of reach — including Maintenance mode (see *Getting Started ▸ Maintenance mode*). It is the only case locked from both ends: nothing else may take **F1**, and Manual may not leave it, so its row is present but read-only. |

**Software settings… is itself an ordinary menu command**, so it appears in this
pane's own list, can be given a key, and can be pinned to the toolbar like
anything else — with the caveat above that a key on it fires in every mode.

---

## The Manual

You're reading it. Open it any time with **F1** or **Help ▸ Manual**.

- The manual renders in the center **Manual** tab.
- The **Contents** tab in the left dock lists every chapter. Click a chapter to
  scroll the manual straight to it.

---

## About, and which version is which

**Help ▸ About** shows the box with the app's identity, its licence, its authors
and its credits. Beside it sit **Help ▸ Manual** and **Help ▸ Open Log Folder**
(see *Troubleshooting: debug mode*).

**Two version numbers appear in that box, and each one says what it versions** —
because two unlabelled numbers a few lines apart is exactly how they get read as
one:

- **"PGTP Editor version …"** — this application's own release. It is read from
  the project's own `pyproject.toml` first, and only falls back to the installed
  package metadata, rather than being typed anywhere, so it cannot go stale. That
  order is deliberate and not the obvious one: in a development install the
  package metadata goes stale while `pyproject.toml` does not, so trusting
  metadata first would show the wrong version in the one place anyone can check
  it. Where the version genuinely cannot be determined it reads **`unknown`**,
  which is a word and not a number, so it can never be mistaken for a release.
- **".pgtp project format version 22.8 — SQL Maestro's format version, not this
  application's"** — the **vendor's** file format this editor targets, i.e. which
  PHP Generator for PostgreSQL projects it understands. It moves when SQL Maestro
  changes the format, and has nothing to do with the line above it.

Nothing else in the app reports either number, and the two never track each
other.

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
**Activity Log** and the checkbox snaps back rather than claiming a server that
isn't there.

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

Launch the editor with `python -m pgtp_editor --debug` (or set the
environment variable `PGTP_EDITOR_DEBUG=1`) to record a full diagnostic log
of the session. A red **DEBUG** chip appears in the status bar (see *The Status
Bar*) and the log file's path is recorded in the **Activity Log** at
startup. Even without debug mode, errors are always
recorded to a small `errors.log`. **Help ▸ Open Log Folder** opens the folder
containing both logs — attach the newest `debug_*.log` when reporting a
problem.

**`python -m pgtp_editor` starts the editor**, with or without `--debug`. The
longer `python -m pgtp_editor.main` is the same thing and keeps working. An
installed copy also puts a **`pgtp-editor`** command on your path, which is the
shortest way to start it — on Windows it launches without dragging a console
window along, so it is also what a Start-menu or desktop shortcut should point
at. All three forms are the same program and take the same arguments, including
`--debug`. For the headless MCP server, stay with a `python -m …` form so the
process keeps its standard input and output (see *The MCP Server ▸ Headless,
instead of the GUI*).
