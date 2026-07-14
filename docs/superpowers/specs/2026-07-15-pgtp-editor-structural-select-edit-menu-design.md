# Structural-selection Edit-menu entries — Design

**Date:** 2026-07-15

Deferred follow-up from XML Editor sub-project D. The structural-selection commands are today only reachable via editor-focused `QShortcut`s; the user requirement is that every command also appears explicitly in a menu **with its keycombo shown**.

## Goal
Add two **Edit-menu** actions — **"Select Enclosing Block" (Ctrl+Shift+B)** and **"Select Parent Block" (Ctrl+Shift+A)** — that trigger the existing `XmlEditor.select_enclosing_block` / `select_parent_block`, with the shortcut displayed in the menu.

## Design
- `pgtp_editor/ui/xml_editor.py`: **remove** the two `QShortcut`s (`Ctrl+Shift+B` → `select_enclosing_block`, `Ctrl+Shift+A` → `select_parent_block`) currently created in `__init__` (lines ~225–231). The methods `select_enclosing_block` / `select_parent_block` stay unchanged. Removing the editor-owned shortcuts prevents an ambiguous-shortcut conflict with the new menu actions (which become the single owner of those key sequences).
- `pgtp_editor/ui/main_window.py` `_build_edit_menu`: after the Find/Replace group and a separator, add:
  - `"Select Enclosing Block"` with `setShortcut("Ctrl+Shift+B")`, triggered → `self.center_stage.xml_editor.select_enclosing_block`.
  - `"Select Parent Block"` with `setShortcut("Ctrl+Shift+A")`, triggered → `self.center_stage.xml_editor.select_parent_block`.
  These are `WindowShortcut`-context (menu-action default): they operate on the Raw XML editor's cursor regardless of focus, which is harmless when the editor is empty/read-only. Keep them enabled always (structural selection is a read-only operation, fine even in Caption Mode).

## Scope
- In: the two Edit-menu actions + shortcut relocation. Out: any change to the selection logic itself, or new selection commands.

## Testing
- `tests/ui/test_menus.py`: the Edit menu contains "Select Enclosing Block" and "Select Parent Block" with shortcuts `"Ctrl+Shift+B"` / `"Ctrl+Shift+A"` (assert via `find_action(...).shortcut().toString()`); update the `test_edit_menu_contents` label list to include them in their position.
- Behavior: triggering each action calls the corresponding editor method (e.g. load a small XML into the editor, place the cursor, trigger the action, assert the editor's selection matches what the method produces — or assert the action is wired to the method).
- `tests/ui/test_xml_editor.py`: the existing structural-selection *method* tests (calling `select_enclosing_block`/`select_parent_block` directly) remain and still pass. Update/remove any test that asserted the editor owns `Ctrl+Shift+B/A` `QShortcut`s (the shortcuts now live on the Edit-menu actions) — do not weaken the method-behavior tests.
- Full suite green, no timeout, no ambiguous-shortcut warning.
