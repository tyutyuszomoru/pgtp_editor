# KEYBINDINGS — the register of every chord in PGTP Editor

**This is the single register of every keyboard binding in the app.** Read it before
proposing, assigning or moving any chord, and push back if the chord is taken: name what
holds it and on which surfaces. Do not reason from a menu listing — six different
mechanisms can answer a keystroke here, and a chord bound by any of them is bound.

**It is kept true by a test, not by discipline.** `tests/test_keybindings_ledger.py`
derives the code side by walking the package (AST over `setShortcut` / `QShortcut`, the
`shortcut_registry` tables, the set of surfaces that call `classify_undo_redo_chord`, and
Qt's own binding table) and asserts the ledger and the code agree **in both directions**:
every chord bound in code has a row here, and every row corresponds to something real.
`shortcut_registry.RESERVED_SEQUENCES` was meant to be this register and rotted precisely
because it was a hand transcription — it silently lost `Ctrl+Shift+Z` until BUG-050. A
register nobody verifies is a second document, not a source of truth.

**A chord means the same thing on every system.** Qt's own table does not: its Windows
scheme binds `Ctrl+Y` and `Alt+Backspace` for undo/redo where the Linux/KDE scheme does
not, and the KDE scheme binds `Ctrl+D`, `Ctrl+K`, `Ctrl+U`, `F14`/`F16`/`F18`/`F20` where
Windows binds nothing. Wherever Qt would differ, this app **binds explicitly on both
platforms or suppresses the chord on both** (DEC-015). The measured per-scheme table is
[Appendix A](#appendix-a--qts-own-binding-table-per-scheme); it is measured, not recalled,
and the test re-measures it.

## How to read the table

**Chord** is the canonical spelling `shortcut_registry.normalize_sequence` produces
(`Ctrl+Insert`, not `Ctrl+Ins`; `Escape`, not `Esc`; `Shift+Tab` for Qt's `Key_Backtab`).

**Host mechanism** is one or more of exactly these tokens — the six mechanisms that can
answer a keystroke:

| Token | Meaning |
| --- | --- |
| `QAction` | a `QAction` with `setShortcut` (menu-bar entry, or a window-level action with no menu entry) |
| `QShortcut` | a `QShortcut` instance, on a window, a panel or a dialog |
| `QShortcut(StandardKey)` | a `QShortcut` built from a `QKeySequence.StandardKey`, so its chords come from Qt's per-scheme table |
| `keyPressEvent` | answered inside a widget's own `keyPressEvent` |
| `eventFilter` | answered in an `eventFilter`, claiming the `ShortcutOverride` and answering the `KeyPress` |
| `Qt default` | nothing in this app binds it; Qt's `StandardKey` handling inside the widget answers it |
| `unbound` | nothing answers it anywhere, deliberately |

Context-menu actions are the sixth mechanism. None of them carries a `setShortcut` — that
is DEC-012 working as intended (a gesture with a command form has exactly **one** keyboard
host), so they appear in the Notes column as the chord's *command form*, never as its host.

**Gate** is the classification the policy turns on, as one or more of these tokens:

| Token | Meaning |
| --- | --- |
| `DEC-012` | has a command form (menu-bar **or** context-menu entry) → exactly one keyboard host, the `QAction`-or-single-`QShortcut` named here |
| `DEC-009` | no command form at all → a widget host is legitimate, and only then, for a product reason |
| `DEC-014` | answered inside a widget's key handling → must be reserved, and *every* editing surface states its answer |
| `DEC-015` | platform-conditional in Qt → this app binds or suppresses it on both schemes, never inherits |
| `Qt` | Qt's own widget-internal answer; the app binds nothing |
| `bare-key` | an unmodified key (`Tab`, `Return`, `Escape`, …). Not a rebinding target, so DEC-014's reservation requirement does not reach it; the requirement is enforced for every `Ctrl`/`Alt`/`Meta` chord answered in widget key handling |
| `dead` | deliberately answered by nothing, app-wide |

**Reserved** is `yes` exactly when the chord is a key in `shortcut_registry.RESERVED_SEQUENCES`
— i.e. Customize Shortcuts refuses it as a rebinding target because something it does not
own already answers it. The test asserts this column and that dict are the same set, in
both directions.

**`[qt:Name]`** in Notes points at Appendix A's row for `QKeySequence.StandardKey.Name`.

## The register

| Chord | Command or gesture | Host mechanism | Surfaces it is live on | Gate | Reserved | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `Ctrl+A` | Select All | `QAction`, `Qt default` | window-level (`main_window.py`), acting on `find_controller.active_selection_editor()`; and Qt's own Select All inside every focused text widget | `DEC-012`, `Qt` | no | Rebindable. A *focused* text widget claims the chord via Qt's `ShortcutOverride` before the window action sees it, so the action only fires when focus is elsewhere (e.g. the structure tree) — which is also why it cannot steal `Ctrl+A` from a `QLineEdit`. `[qt:SelectAll]` |
| `Ctrl+C` | Copy | `Qt default`, `QShortcut(StandardKey)` | Qt's built-in copy in every text widget and table; **and** a real host — `caption_management_panel.py` binds `StandardKey.Copy` on the caption grid to `copy_selection` | `Qt`, `DEC-009` | yes | Reserved so no menu command can be retargeted onto it — a window-level shortcut on `Ctrl+C` would take precedence over the widgets and break copy app-wide. The caption grid's host is an implicit `WindowShortcut` (see [Known gaps](#known-gaps)); it only wins where the focused widget does not itself claim Copy (measured: a `QLineEdit` does). `[qt:Copy]` |
| `Ctrl+F` | Focus the current tab's Find field | `QShortcut` | seven hosts, one per surface, all `WidgetWithChildrenShortcut`: `find_replace_bar.py`'s `install_focus_shortcuts` at six sites (`center_stage.py` for the Raw XML tab, the Edit XSD tab and the FQ-006 draft fragment tab; `php_file_tab.py`; `ddl_editor_panel.py`; `ddl_object_editor.py`) plus `caption_management_panel.py`'s own pair | `DEC-009` | yes | Per-tab and never window-level: Qt answers two enabled shortcuts matching one key press by firing **neither**, so one window-level host plus the caption panel's would delete the command from the keyboard. Never two hosts in one focus chain. A no-op on tabs with no bar (Manual, Diff/Merge) rather than yanking focus to Raw XML. `[qt:Find]` |
| `Ctrl+G` | Go to line in XML, from the caption grid | `QShortcut` | `caption_management_panel.py`, on the grid | `DEC-012` | yes | Command form: the click-only context-menu entry *Go to line in XML* on the same panel, deliberately carrying no `setShortcut`. Implicit `WindowShortcut` (see [Known gaps](#known-gaps)): live anywhere in the window while the Caption Management tab is visible, including from inside that panel's Find field — measured. Qt's Windows scheme also binds `Ctrl+G` as Find Next, but nothing in the app uses that standard key, so there is no clash. `[qt:FindNext]` |
| `Ctrl+L` | Go To XSD | `QAction` | window-level (`xsd_controller.py`), no menu entry | `DEC-012` | yes | Invisible to `ToolbarController._walk_menu_actions`, so it can never be pinned to the toolbar and never appears in Customize Shortcuts — which is why it must be reserved rather than merely listed. |
| `Ctrl+R` | Focus the current tab's Replace-with field | `QShortcut` | the same seven hosts as `Ctrl+F` (`find_replace_bar.py`, `caption_management_panel.py`) | `DEC-009` | yes | Qt's KDE scheme binds `Ctrl+R` as Replace, its Windows scheme `Ctrl+H`; no text widget implements the standard key, so the app's chord is the only answer on both. `[qt:Replace]` |
| `Ctrl+Return` | Run, on the Sandbox SQL Console tab | `QShortcut` | `sql_console_panel.py`, `WidgetWithChildrenShortcut` | `DEC-009` | yes | Calls the same `run()` the results panel's Run button calls — one execution path. No menu or context-menu form (a button is not a command form). The sandbox is disposable and `reset()`-able, so this does not reopen "an irreversible outward effect must not be one keystroke away". |
| `Ctrl+S` | — nothing, deliberately | `unbound` | app-wide | `dead` | yes | Every save is a named `Deployment` menu click (FQ-020). The last carve-out, `CodeEditorDialog`'s OK, was removed by owner decision 2026-08-09. Qt's Save standard key is this chord, but nothing in the app uses it. `[qt:Save]` |
| `Ctrl+V` | Paste | `Qt default`, `QShortcut(StandardKey)`, `keyPressEvent` | Qt's built-in paste in every text widget; `caption_management_panel.py` binds `StandardKey.Paste` on the caption grid to `paste_into_new_value`; `xml_editor.py` refuses it with the read-only hint in Caption Mode | `Qt`, `DEC-009` | yes | Reserved for the same reason as `Ctrl+C`. `xml_editor.py` tests it with `event.matches(StandardKey.Paste)` rather than a literal chord, so the refusal follows Qt's table on both schemes. `[qt:Paste]` |
| `Ctrl+X` | Cut | `Qt default` | Qt's built-in cut in every text widget | `Qt` | yes | Nothing in the app binds it; reserved so nothing can. `[qt:Cut]` |
| `Ctrl+Y` | Redo, in the surface that has focus | `QShortcut`, `eventFilter`, `keyPressEvent` | `main_window.py` (window-scoped, routed through the tab-scoped Raw XML snapshot slot) **plus** every editing surface's own key handling: `code_editor.py` (`CodeEditorDialog`), `xml_editor.py`, `php_file_tab.py`, `ddl_object_editor.py`, `ddl_editor_panel.py`, `sql_console_panel.py` | `DEC-014`, `DEC-015` | yes | **Bound by this app on every platform** — Qt binds it only on the Windows scheme, so a redo that leaned on Qt was a dead key on Linux (BUG-056 measured it in the Sandbox SQL Console). The project-wide twin is `History ▸ Redo Project Edit`, a different command with a different scope, and it IS rebindable (BUG-064). `[qt:Redo]` |
| `Ctrl+Z` | Undo, in the surface that has focus | `QShortcut`, `eventFilter`, `keyPressEvent` | as `Ctrl+Y`: `main_window.py` plus all six editing surfaces — `code_editor.py`, `xml_editor.py`, `php_file_tab.py`, `ddl_object_editor.py`, `ddl_editor_panel.py`, `sql_console_panel.py` | `DEC-014`, `DEC-015` | yes | Two *different* operations, so two rows with two reasons — never one "the undo/redo chords" statement. Each surface's answer differs and must: own native stack, a stated read-only refusal, or re-emission into the project's snapshot history. The project-wide twin is `History ▸ Undo Project Edit`, which IS rebindable. `[qt:Undo]` |
| `Ctrl+Insert` | Copy | `Qt default`, `QShortcut(StandardKey)` | as `Ctrl+C` — it is Qt's second chord for the same standard key on both schemes, so the caption grid's `StandardKey.Copy` host (`caption_management_panel.py`) answers it too | `Qt` | no | **Not reserved** — see [Known gaps](#known-gaps). `[qt:Copy]` |
| `Shift+Insert` | Paste | `Qt default`, `QShortcut(StandardKey)` | as `Ctrl+V` — Qt's second chord for the same standard key on both schemes, so the caption grid's `StandardKey.Paste` host (`caption_management_panel.py`) answers it too | `Qt` | no | **Not reserved** — see [Known gaps](#known-gaps). `[qt:Paste]` |
| `Ctrl+Shift+Insert` | Paste, on the Linux/KDE scheme only | `Qt default`, `QShortcut(StandardKey)` | as `Ctrl+V`, and only where Qt binds it: the KDE scheme adds this chord to `StandardKey.Paste`, so the caption grid's host (`caption_management_panel.py`) answers it there and nowhere else | `Qt`, `DEC-015` | no | An inherited platform-conditional chord — the app neither binds nor suppresses it, because it comes from a `StandardKey` host rather than a literal chord. See [Known gaps](#known-gaps). `[qt:Paste]` |
| `Shift+Delete` | Cut | `Qt default` | Qt's built-in cut in every text widget; on the KDE scheme `F20` is a second Cut chord there too | `Qt` | no | Qt's second Cut chord. Nothing in the app binds or reserves it. `[qt:Cut]` |
| `F16` | Copy, on the Linux/KDE scheme only | `Qt default`, `QShortcut(StandardKey)` | as `Ctrl+C`: Qt's KDE scheme adds `F16` to `StandardKey.Copy`, so the caption grid's host (`caption_management_panel.py`) answers it on Linux and not on Windows | `Qt`, `DEC-015` | no | No keyboard the owner uses has an `F13`…`F20` block. Recorded because it is bound, not because it is reachable. `[qt:Copy]` |
| `F18` | Paste, on the Linux/KDE scheme only | `Qt default`, `QShortcut(StandardKey)` | as `Ctrl+V`, KDE scheme only (`caption_management_panel.py`) | `Qt`, `DEC-015` | no | As `F16`. `[qt:Paste]` |
| `Copy` | Copy | `Qt default`, `QShortcut(StandardKey)` | as `Ctrl+C` — the dedicated `Key_Copy` media key is in `StandardKey.Copy` on both schemes, so the caption grid's host (`caption_management_panel.py`) answers it too | `Qt` | no | A real key on multimedia keyboards, not a modifier chord. `[qt:Copy]` |
| `Paste` | Paste | `Qt default`, `QShortcut(StandardKey)` | as `Ctrl+V` — the dedicated `Key_Paste` media key, on both schemes (`caption_management_panel.py`) | `Qt` | no | `[qt:Paste]` |
| `Delete` | Delete the selection or the character after the caret | `Qt default`, `keyPressEvent` | Qt's built-in in every text widget; `xml_editor.py` refuses it with the read-only hint in Caption Mode | `Qt`, `bare-key` | no | `[qt:Delete]` |
| `Ctrl+Alt+C` | Expand `SELECT` into its column list | `keyPressEvent` | `code_editor.py`, and only while `self._language == "sql"` — the DDL object tabs and the Sandbox SQL Console; inert in js/php, where expanding plpgsql into a PHP body would be a bug | `DEC-009` | yes | No menu and no context-menu form at all: this is a widget *behaviour* like auto-close brackets, and it depends on caret state and on the editor's own language, so the widget is its one legitimate host. |
| `Ctrl+Alt+E` | Expand the snippet at the caret | `keyPressEvent` | `code_editor.py`, SQL only, as `Ctrl+Alt+C` | `DEC-009` | yes | Same family, same reason. |
| `Ctrl+Alt+F` | Format Selection | `QShortcut` | three hosts, all `WidgetWithChildrenShortcut` and all disabled without a selection: `xml_editor.py` (Raw XML, Edit XSD, draft fragment tabs — the `xmlfmt` engine), `ddl_object_editor.py` and `sql_console_panel.py` (the SQL engine) | `DEC-012` | yes | One gesture, two engines, dispatched by **host surface** and never by sniffing the text. It HAS a command form — the click-only context-menu action on the DDL object tab and on the console — which is what puts it under DEC-012, not under DEC-009's carve-out (BUG-054, BUG-063: the carve-out was read too wide twice in one day). There is deliberately **no** `Ctrl+Alt+F` branch in any `eventFilter`. |
| `Ctrl+Alt+J` | Write the JOIN a foreign key implies | `QShortcut`, `eventFilter` | `sql_console_panel.py` (`QShortcut`, `WidgetWithChildrenShortcut`) and `ddl_object_editor.py` (`eventFilter` branch) | `DEC-009` | yes | No command form. Hosted on the panel rather than in `CodeEditor` because it needs the injected `SchemaIndex`, which an editor widget may not hold (§18.5 D1). |
| `Ctrl+Shift+A` | Select Parent Block | `QAction` | window-level (`main_window.py`) | `DEC-012` | no | Rebindable. Qt's KDE scheme binds this chord as Deselect; **measured on both schemes, `QPlainTextEdit` does not claim it**, so the action fires with focus inside an editor on Windows and on Linux alike. `[qt:Deselect]` |
| `Ctrl+Shift+B` | Select Enclosing Block | `QAction`, `QShortcut` | `main_window.py`'s menu action (`WindowShortcut` on the MainWindow) and `code_editor.py`'s own `WindowShortcut` inside `CodeEditorDialog`, which has no menu bar to host the action | `DEC-012` | no | Two hosts in two different *windows*, never both active for one key press, so this is not the double-hosting DEC-012 forbids. Stated limitation: the dialog's is a literal chord and does not follow a user rebinding of the menu command (`_apply_shortcut_bindings` only walks menu QActions). |
| `Ctrl+Shift+S` | — nothing, deliberately | `unbound` | app-wide | `dead` | yes | As `Ctrl+S`. `[qt:SaveAs]` |
| `Ctrl+Shift+Space` | Signature help for the call at the caret | `QShortcut`, `eventFilter` | `sql_console_panel.py` (`QShortcut`) and `ddl_object_editor.py` (`eventFilter`) | `DEC-009` | yes | The IDE convention, and one modifier away from the `Ctrl+Space` completion it is the sibling of. Explicit trigger only — nothing on this path is wired to `textChanged`. |
| `Ctrl+Shift+Z` | Claimed, and deliberately **not** redo | `eventFilter`, `keyPressEvent` | all six editing surfaces: `code_editor.py`, `xml_editor.py`, `php_file_tab.py`, `ddl_object_editor.py`, `ddl_editor_panel.py`, `sql_console_panel.py` | `DEC-014`, `DEC-015` | yes | `EDITOR_UNDO_REDO_CHORDS` classifies it `CLAIMED_NOT_UNDO_REDO`. DEC-015 freed it from redo ("Redo is always, on all systems, `Ctrl+Y`"), but Qt binds it as native Redo on **both** schemes, so every surface must actively intercept it or Qt redoes anyway. FQ-034's shrink-selection lands here. This is the row the hand-transcribed register lost (BUG-050). `[qt:Redo]` |
| `Ctrl+Space` | The completion popup | `QShortcut`, `eventFilter`, `keyPressEvent` | `sql_console_panel.py` (`QShortcut`, `WidgetWithChildrenShortcut`), `ddl_object_editor.py` (`eventFilter`), `xml_editor.py` (`keyPressEvent`, attribute completions) | `DEC-009` | yes | Three editor contexts, one host each. No command form. Needs the injected `SchemaIndex` plus the panel's own caret/popup state, and is intrinsically focus-scoped — a window shortcut would fire it for whichever widget happened to be focused. |
| `Alt+Backspace` | Suppressed — answers nothing, on purpose | `eventFilter`, `keyPressEvent` | all six editing surfaces, as `Ctrl+Shift+Z`: `code_editor.py`, `xml_editor.py`, `php_file_tab.py`, `ddl_object_editor.py`, `ddl_editor_panel.py`, `sql_console_panel.py` | `DEC-014`, `DEC-015` | yes | `EDITOR_UNDO_REDO_CHORDS` classifies it `SUPPRESSED`. Qt binds it as native Undo on the **Windows scheme only**, so the interception *is* the behaviour: it is what makes the key dead on Windows too, rather than only on Linux. Owner's rule (2026-08-10): a chord means the same thing on both systems or it is not bound at all — and a legacy Windows-only spelling in no menu, no manual page and no shortcut table is not worth *inventing* on Linux. `[qt:Undo]` |
| `Alt+Shift+Backspace` | Suppressed — answers nothing, on purpose | `eventFilter`, `keyPressEvent` | all six editing surfaces: `code_editor.py`, `xml_editor.py`, `php_file_tab.py`, `ddl_object_editor.py`, `ddl_editor_panel.py`, `sql_console_panel.py` | `DEC-014`, `DEC-015` | yes | As `Alt+Backspace`, for Qt's legacy Windows-scheme Redo. `[qt:Redo]` |
| `F1` | Manual | `QAction` | window-level (`main_window.py`), `Help ▸ Manual` | `DEC-012` | yes | Pinned twice over: reserved as a sequence (nothing else may take it) and reserved as a command (`help.manual` is in `RESERVED_COMMAND_IDS`, so Manual may not leave `F1`), and it is the one menu entry no launch mode may hide. `[qt:HelpContents]` |
| `F2` | Next Bookmark | `QAction` | window-level (`find_controller.py`), `Navigation` menu, acting on `active_bookmark_editor()` | `DEC-012` | no | Rebindable. Gated off with the rest of the bookmark family while Caption Mode is active — via the actions, not just the `QMenu`, because disabling a menu leaves its actions' shortcuts live. |
| `F3` | Find Next | `QAction` | window-level (`main_window.py`), no menu entry, routed through `find_controller.active_find_bar()` | `DEC-012` | yes | Window-level rather than per-tab (unlike `Ctrl+F`/`Ctrl+R`) because nothing else in the app binds `F3`, so there is no ambiguity to avoid. Accepted consequence: with no menu entry it can never be pinned to the toolbar. `[qt:FindNext]` |
| `Ctrl+F2` | Toggle Bookmark | `QAction` | window-level (`find_controller.py`), `Navigation` menu | `DEC-012` | no | Rebindable. |
| `Shift+F2` | Previous Bookmark | `QAction` | window-level (`find_controller.py`), `Navigation` menu | `DEC-012` | no | Rebindable. |
| `Escape` | Return focus to the document; and four narrower answers | `keyPressEvent` | `find_replace_bar.py` (focus back to the editor, the bar stays visible), `caption_management_panel.py` (focus back to the grid), `code_editor.py` (leave tab-stop mode — **only** while a template walk is in progress, so Escape keeps its normal meaning everywhere else), `completion_popup.py` (dismiss the popup), `launcher_dialog.py` (cancel when the launcher is dismissable, swallowed when it is not) | `bare-key` | yes | Reserved: five widgets answer it, so a menu command retargeted onto it would be swallowed by whichever has focus. `Ctrl+W` is *not* how a dialog closes here — `Escape` and the button box are. `[qt:Cancel]` |
| `Return` | Newline with indent; choose the current completion item; activate the focused node | `keyPressEvent`, `Qt default` | `xml_editor.py` (newline with structural indent), `completion_popup.py` (choose the current item), `project_status_panel.py` (activate the focused node, as a click would); plus Qt's own default-button handling in every dialog | `bare-key`, `Qt` | no | `xml_editor.py` also refuses it with the read-only hint in Caption Mode. `[qt:InsertParagraphSeparator]` |
| `Tab` | Next tab stop; choose the current completion item | `keyPressEvent` | `code_editor.py`, **only** while `in_tab_stop_mode` — outside a template walk Tab still inserts a tab character in every editor; `completion_popup.py`, choose the current item | `bare-key` | no | The mode gate is the whole design: a Tab that silently jumped somewhere else would be worse than a tab. |
| `Shift+Tab` | Previous tab stop | `keyPressEvent` | `code_editor.py`, tab-stop mode only (Qt delivers it as `Key_Backtab`) | `bare-key` | no | |
| `Backspace` | Shrink the completion filter by one character | `keyPressEvent` | `completion_popup.py`; `xml_editor.py` refuses it with the read-only hint in Caption Mode | `bare-key` | no | |
| `Up` | Move the completion selection up | `keyPressEvent` | `completion_popup.py` | `bare-key` | no | Passed to the base `QListWidget`, which is what makes the popup navigable while the editor keeps focus. |
| `Down` | Move the completion selection down | `keyPressEvent` | `completion_popup.py` | `bare-key` | no | |
| `Space` | Activate the focused Project Status node | `keyPressEvent` | `project_status_panel.py` | `bare-key` | no | Keyboard equivalent of the node's click. |
| `Ctrl+W` | — nothing | `unbound` | app-wide | `dead` | no | Lost its `File ▸ Close` binding on 2026-08-09 and was deliberately not re-bound anywhere, including in `CodeEditorDialog`. **Not reserved** — see [Known gaps](#known-gaps). `[qt:Close]` |

## Appendix A — Qt's own binding table, per scheme

Qt's `StandardKey` table is **not uniform across platforms**, which is the whole reason
this register exists. Both columns below were **measured** with
`QKeySequence.keyBindings(...)`, printed in Qt's own spelling (the test normalizes before
comparing, so `Ctrl+Ins` and `Ctrl+Insert` are the same row):

- **Windows** — also what the offscreen test platform reports, which is why *the suite
  cannot see a Linux-only dead key*. Assert the app's handler, never Qt's native answer.
- **Linux/KDE** — measured under the `xcb` platform plugin on the owner's Manjaro/KDE
  machine (Qt's `KB_KDE` scheme: note `Ctrl+D`, `Ctrl+K`, `Ctrl+U`, `Ctrl+Shift+A` and the
  `F14`…`F20` block, none of which the Windows scheme binds). A GNOME or bare-X11 desktop
  is a *third* scheme; nothing here may be inferred for it.

| `StandardKey` | Windows scheme | Linux/KDE scheme (measured) | The app's answer |
| --- | --- | --- | --- |
| `Undo` | `Ctrl+Z`, `Alt+Backspace`, `Undo` | `Ctrl+Z`, `F14`, `Undo` | binds `Ctrl+Z` itself on both; **suppresses** `Alt+Backspace` on both. `F14` and the `Undo` media key are left to Qt — Linux-only, and see [Known gaps](#known-gaps) |
| `Redo` | `Ctrl+Y`, `Alt+Shift+Backspace`, `Ctrl+Shift+Z`, `Redo` | `Ctrl+Shift+Z`, `Redo` | binds `Ctrl+Y` itself on both (DEC-015); **suppresses** `Alt+Shift+Backspace`; **intercepts** `Ctrl+Shift+Z` everywhere so Qt's native redo cannot fire |
| `Copy` | `Ctrl+C`, `Ctrl+Insert`, `Copy` | `Ctrl+C`, `Ctrl+Insert`, `F16`, `Copy` | left to Qt inside the widgets; additionally hosted on the caption grid via `StandardKey.Copy`, so that host follows this row per scheme |
| `Cut` | `Ctrl+X`, `Shift+Delete`, `Cut` | `Ctrl+X`, `Shift+Delete`, `F20`, `Cut` | left to Qt inside the widgets |
| `Paste` | `Ctrl+V`, `Shift+Insert`, `Paste` | `Ctrl+V`, `Ctrl+Shift+Insert`, `Shift+Insert`, `F18`, `Paste` | left to Qt inside the widgets; additionally hosted on the caption grid via `StandardKey.Paste` |
| `SelectAll` | `Ctrl+A` | `Ctrl+A` | the same chord as `Select ▸ Select All`; identical on both schemes, so no divergence |
| `Deselect` | *(nothing)* | `Ctrl+Shift+A` | the app binds `Select ▸ Select Parent Block` there; measured on both schemes, `QPlainTextEdit` does not claim the chord, so the action wins |
| `Find` | `Ctrl+F`, `Find` | `Ctrl+F`, `Find` | the app's per-tab focus-Find shortcut is the same chord; no text widget implements the standard key |
| `FindNext` | `F3`, `Ctrl+G` | `F3` | the app binds both chords itself (`F3` window-level, `Ctrl+G` on the caption grid) and uses the standard key nowhere, so the asymmetry is unreachable |
| `FindPrevious` | `Shift+F3`, `Ctrl+Shift+G` | `Shift+F3` | unused by the app |
| `Replace` | `Ctrl+H` | `Ctrl+R` | the app binds `Ctrl+R` itself on both; `Ctrl+H` answers nothing |
| `Save` | `Ctrl+S`, `Save` | `Ctrl+S`, `Save` | deliberately dead app-wide; nothing uses the standard key |
| `SaveAs` | `Ctrl+Shift+S`, `Shift+Save` | `Ctrl+Shift+S`, `Shift+Save` | deliberately dead app-wide |
| `Close` | `Ctrl+F4`, `Ctrl+W`, `Close` | `Ctrl+W`, `Close` | nothing uses the standard key; `Ctrl+W` answers nothing |
| `Delete` | `Delete` | `Delete`, `Ctrl+D` | left to Qt; `Ctrl+D` deletes a character on KDE and does nothing on Windows |
| `DeleteEndOfLine` | *(nothing)* | `Ctrl+K` | left to Qt; Linux-only |
| `DeleteCompleteLine` | *(nothing)* | `Ctrl+U` | left to Qt; Linux-only |
| `DeleteEndOfWord` | `Ctrl+Delete` | `Ctrl+Delete` | left to Qt |
| `DeleteStartOfWord` | `Ctrl+Backspace` | `Ctrl+Backspace` | left to Qt |
| `Cancel` | `Escape`, `Cancel` | `Escape`, `Cancel` | the app answers `Escape` in five widgets |
| `InsertParagraphSeparator` | `Enter`, `Return` | `Enter`, `Return` | the app answers `Return` in three widgets |
| `HelpContents` | `F1`, `Help` | `F1`, `Help` | the app binds `F1` as its own `QAction` |
| `Underline` | `Ctrl+U` | `Ctrl+U` | unused by the app (no rich text anywhere) |

## Known gaps

Found by the sweep that produced this register. **None of them is fixed here** — this
document and its test are a register, not a refactor. They are recorded so the next
keyboard question does not have to re-derive them, and are for `bug-triager` to rule on.

1. **`Ctrl+Insert` and `Shift+Insert` are not in `RESERVED_SEQUENCES`, but they are bound.**
   They are Qt's second chords for Copy and Paste on both schemes, and the caption grid's
   `StandardKey.Copy`/`StandardKey.Paste` shortcuts answer them for real. Customize
   Shortcuts would therefore accept `Ctrl+Insert` as a rebinding target, producing exactly
   the ambiguity `RESERVED_SEQUENCES` exists to prevent: two enabled shortcuts matching one
   key press, and Qt fires **neither**. `Ctrl+C`/`Ctrl+V` are reserved; their aliases are
   not. (`Shift+Delete` for Cut is the same shape, one step safer because nothing in the app
   hosts a Cut shortcut.)
2. **Three shortcuts rely on Qt's implicit `WindowShortcut` default rather than stating a
   scope.** `caption_management_panel.py` sets a context on its `Ctrl+F`/`Ctrl+R` pair
   (`WidgetWithChildrenShortcut`) but not on `StandardKey.Copy`, `StandardKey.Paste` or
   `Ctrl+G` on the same panel, which are therefore window-scoped: measured, `Ctrl+G` fires
   from inside that panel's Find field, and the Copy/Paste pair would fire from anywhere in
   the window that does not itself claim the chord. It is contained today only because the
   panel is a `CenterStage` tab and a hidden tab page's shortcuts do not fire (also
   measured) — an invariant nothing states, and the same shape as BUG-048.
3. **`RESERVED_SEQUENCES`' stated reasons for `Ctrl+C` and `Ctrl+V` are incomplete.** Both
   say "a Qt built-in inside every editor widget"; both also have a real `QShortcut` host on
   the caption grid. The reason text is what the user is shown when the dialog refuses the
   key, so it should name that host.
4. **`Ctrl+W` is dead but unreserved.** It was deliberately unbound app-wide on 2026-08-09
   for the same reason as `Ctrl+S` — total consistency — but only `Ctrl+S`/`Ctrl+Shift+S`
   were written into `RESERVED_SEQUENCES`, so Customize Shortcuts will happily hand `Ctrl+W`
   to a menu command and quietly reverse that decision.
5. **Qt's Linux-only chords reach the editors unfiltered.** On the KDE scheme Qt answers
   `F14` (Undo), `F16`/`F18`/`F20` (Copy/Paste/Cut), `Ctrl+Shift+Insert` (Paste), `Ctrl+D`
   (Delete), `Ctrl+K` (delete to end of line) and `Ctrl+U` (delete line) inside every text
   widget; the Windows scheme binds none of them. `F14`'s native undo is the one that
   matters in principle — it bypasses the app's undo routing entirely, so on Linux it would
   edit the buffer without a journal line, which is what DEC-014's interception exists to
   prevent for `Ctrl+Z`. In practice no keyboard the owner uses has an `F14`…`F20` block, so
   this is a correctness gap rather than a live bug; `Ctrl+D`/`Ctrl+K`/`Ctrl+U` are reachable
   and are plain editing keys that simply do nothing on Windows.
