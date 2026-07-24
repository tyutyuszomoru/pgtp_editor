# Busy activity indicator — design

## Goal

Give the user an immediate visual clue that a slow operation is running, so the
app reads as "working" rather than "hung". When an operation blocks the GUI
thread (file open, schema enrichment, validate, reparse, generation), show a
sticky status-bar message naming the activity (and, for file open, the file name
and size) plus a wait cursor (hourglass), forced to paint *before* the blocking
work begins.

This is a **cosmetic** indicator (Approach C). It does NOT move work off the GUI
thread — the window is still unresponsive to input during the operation. It only
makes the in-progress state visible.

## Placement / reuse (from the spec-maintainer gate)

- Belongs in the App-shell status-bar area (CONSOLIDATED_SPEC §7), touching the
  file-open flow and §11 schema enrichment.
- Extends the existing **status-bar messaging convention**: an in-progress
  message with a gerund + ellipsis and no timeout while working, then a terminal
  message with a timeout when done (the Database Check and Find All flows are the
  precedents).
- Progress lives in the **status bar**, not the Audit panel. The Audit panel is
  reserved for `[Prefix]` *result* records (`[Schema]`, `[Validate]`, `[Find]`,
  `[PHP]`); this feature adds no Audit prefix.
- Deliberately does NOT use `run_async` / threads (that was Approach A, declined)
  and adds no `QProgressBar` / `QProgressDialog`.

## Architecture

One new tiny UI helper plus call-site wrapping. No changes to `db/`,
`model/`, `schema_learning/`, or `generation/` core logic.

### 1. `pgtp_editor/ui/busy.py` — `busy_status` context manager

```python
@contextmanager
def busy_status(status_bar, message): ...
```

On enter:
1. `status_bar.showMessage(message)` (sticky — no timeout).
2. `QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)` (the hourglass).
3. `QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)`
   — forces the message + cursor to paint immediately, before the blocking work.
   `ExcludeUserInputEvents` prevents re-entrancy from queued clicks/keys (e.g. a
   double-clicked Open triggering a second open mid-operation).

On exit (via `finally`, so it runs even if the block raises):
4. `QApplication.restoreOverrideCursor()`.

The context manager does NOT set the terminal message — the caller does that
after the block, keeping each operation's existing completion message intact.

Kept tiny and Qt-only, mirroring the ethos of `ui/async_task.py`.

### 2. `pgtp_editor/ui/busy.py` — `format_size(num_bytes)` helper

Formats a byte count for humans: `"312 KB"`, `"1.4 MB"`, `"984 bytes"`. Pure
function, unit-tested independently.

### 3. Call-site wrapping in `pgtp_editor/ui/main_window.py`

Each long operation wraps only its heavy region in `busy_status`; the existing
terminal status message stays after the block. Messages use gerund + `…`.

| Operation | Method | Busy message | Terminal (unchanged) |
|-----------|--------|--------------|----------------------|
| File open | `open_project_file` | `Opening {name} ({size})…` | existing `Opened: {path}` |
| Validate | `_validate_project` | `Validating {name}…` | existing validation result |
| Reparse | `_reparse_raw_xml` | `Reparsing…` | existing `Reparsed raw XML into tree` |
| Generation | generation handler(s) using `self._generator_runner.run(...)` | `Generating PHP…` | existing completion/gap message |

- `{name}` is `Path(path).name` (matching the Save/Revert message style).
- `{size}` is `format_size(os.path.getsize(path))`; if the size can't be read,
  omit the ` ({size})` suffix (never crash the open over a stat failure).
- **Schema enrichment** is part of file open (`_enrich_schema_from_file` is
  called inside `open_project_file`), so wrapping the open region covers the
  slowest part — no separate wrapping needed. The enrichment's own `[Schema]`
  Audit result lines are unaffected.

## Data flow

```
user triggers op
  → status_bar.showMessage("<gerund> …")   (sticky)
  → setOverrideCursor(WaitCursor)
  → processEvents(ExcludeUserInputEvents)   ← message + hourglass paint now
  → [blocking work runs; window frozen to input]
  → restoreOverrideCursor()                 (finally)
  → status_bar.showMessage("<done>", <timeout>)
```

## Error handling / edge cases

- **Exception in the block:** `restoreOverrideCursor()` runs in `finally`; the
  operation's existing error handling (e.g. `_handle_parse_failure`) proceeds
  normally afterward.
- **Dialog inside the operation:** if an operation shows a user-facing dialog on
  a failure path (e.g. the parse-failure `QMessageBox` in `open_project_file`),
  the cursor must be restored *before* the dialog so no hourglass sits over a
  modal. Structure the wrapping so the dialog-showing path is outside the
  `busy_status` block (e.g. wrap the `load_project` + populate region; on
  `PgtpParseError`, exit the block before `_handle_parse_failure`).
- **`os.path.getsize` failure:** omit the size suffix; still show
  `Opening {name}…`.
- **Nested/overlapping cursors:** every `setOverrideCursor` is paired with
  exactly one `restoreOverrideCursor` via the context manager, so the override
  stack stays balanced.

## Testing

- `tests/ui/test_busy.py` (new):
  - `format_size` for bytes / KB / MB boundaries.
  - `busy_status` sets the message and an override cursor on enter, and restores
    the cursor on normal exit.
  - `busy_status` restores the cursor even when the wrapped block raises.
- `tests/ui/` (extend existing op tests): opening a file sets an
  `Opening …`-style message (assert via a status-bar spy) and still ends at the
  existing `Opened:` message; validate/reparse set their busy message. Patch any
  modal Qt calls; offscreen platform.
- `feature-tester` + `docs/TEST_LOG.md` gate; `manual-maintainer` after (the
  status messages are a minor user-visible surface).

## Out of scope

- Moving work off the GUI thread / true responsiveness (Approach A, declined).
- Progress bars, percentages, or cancellation.
- A persistent busy widget in the status bar (uses the transient message
  channel only).
