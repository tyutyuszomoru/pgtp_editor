# Find All streaming + Stop, and Replace All count — Design

**Date:** 2026-07-13

## 1. Purpose

Today Find All is synchronous: `search.find_all_matches` scans the whole document, then `MainWindow._populate_find_all_results` appends every result to the Audit panel at once. On a large file with a very common term (e.g. `fieldName`) this blocks the UI until the entire scan and population complete, with no feedback and no way to abort.

This sub-project makes Find All **stream** (results appear as they are found), **stoppable** (a Stop control that keeps whatever was already found), and adds **live/final status-bar counts**. It also adds a status-bar count message to Replace All.

## 2. Scope

**In scope**
- A lazy generator `search.iter_matches(text, term)`; `find_all_matches` reimplemented on top of it (behaviour identical).
- Chunked, `QTimer`-driven Find All in `MainWindow` that streams results into the Audit panel a batch at a time, yielding to the event loop between batches.
- The find bar's **"Find All" button toggles to "Stop"** while a run is active; clicking Stop ends the run, keeping results found so far.
- Status bar: live `Finding "term"… found N` during the run, then `Found N item(s)` on completion or `Find All stopped — found N item(s)` when stopped.
- Replace All: a `N replacement(s) for "term"` status-bar message (works from both the bar button and the Edit-menu action).

**Out of scope**
- Threading/multiprocessing (single-threaded chunking only — the recommended approach).
- Any change to matching semantics (still plain case-insensitive substring, non-overlapping).
- Progress bar / percentage (unknown total; a running count is enough).
- Result caps or truncation.

## 3. Design

### 3.1 Search core (`pgtp_editor/ui/search.py`)
Add a generator that yields `Match` objects one at a time using the existing non-overlapping scan, and make the list function delegate to it (single scan implementation, DRY):

```python
def iter_matches(text, term):
    # same scan as find_all_matches, but yields lazily
    ...

def find_all_matches(text, term):
    return list(iter_matches(text, term))
```

`iter_matches("", term)` / `iter_matches(text, "")` yield nothing. Laziness matters: the driver must be able to pull one batch, hand control back to the event loop, and resume — without the generator having scanned the whole document up front.

### 3.2 Chunked driver (`pgtp_editor/ui/main_window.py`)
`_populate_find_all_results(term)` becomes the *start* of a streaming run:
1. Cancel any in-flight run (stop + drop its timer) so a re-trigger can't leave two timers running.
2. Clear prior `[Find]` entries, snapshot the editor text once, create `search.iter_matches(text, term)`.
3. Flip the bar to running (`set_find_all_running(True)`), show `Finding "term"…`.
4. Start a `QTimer` at 0 ms whose `timeout` calls `_find_all_step`.

`_find_all_step()` processes up to `_FIND_ALL_BATCH` (200) matches per tick: pull `next()` from the iterator, append a `[Find] line N: preview` item (line number on `UserRole`), increment the count. On `StopIteration` → finish (not stopped). If the stop flag is set → finish (stopped). After each full batch, update the live status count and return to the event loop (keeps the UI responsive and lets a queued Stop click be processed).

`_finish_find_all(stopped)` stops/clears the timer, appends the `[Find] N match(es) for "term"` summary line, flips the bar back (`set_find_all_running(False)`), and shows the final status (`Found N item(s)` or `Find All stopped — found N item(s)`).

`_stop_find_all()` just sets the stop flag; the next `_find_all_step` tick observes it and finishes. This is what the bar's Stop click invokes.

Because the text is snapshotted at start and iteration is over that snapshot string, edits cannot corrupt an in-flight run (and Raw XML is the active surface either way).

### 3.3 FindReplaceBar (`pgtp_editor/ui/find_replace_bar.py`)
- New injected callbacks `on_stop_find_all` and `on_status`, each defaulting to a no-op, with `set_on_stop_find_all` / `set_on_status` setters (keeps the bar decoupled from MainWindow, matching the existing `on_find_all` pattern).
- `_find_all_running` flag + `set_find_all_running(running)` toggling the button label **"Find All" ↔ "Stop"** (driver-controlled, since only the driver knows the true start/finish).
- `find_all()`: when running → call `on_stop_find_all()`; otherwise the existing term-guard → `on_find_all(term)`.
- `replace_all()`: compute the match count, perform the existing single-undo rewrite, then report `N replacement(s) for "term"` (including `0`) via `on_status`.

### 3.4 Wiring
In `MainWindow.__init__`, alongside the existing `set_on_find_all`, wire `set_on_stop_find_all(self._stop_find_all)` and `set_on_status(self.statusBar().showMessage)`. Initialise the Find-All run state (`_find_all_timer=None`, `_find_all_iter=None`, `_find_all_stop=False`, `_find_all_count=0`, `_find_all_term=""`).

## 4. Error handling / edge cases
- Empty term → no run (unchanged).
- Re-triggering Find All from the menu while a run is active → the previous run is cancelled cleanly before the new one starts (no orphaned timer).
- Stop before the first batch → 0 results kept, summary `0 match(es)`, status `Find All stopped — found 0 item(s)`.
- Stop mid-run → all results found so far are kept, summary and status reflect the partial count.

## 5. Testing
- **search:** `iter_matches` parity with `find_all_matches` on varied inputs; empty term/text; that it is a generator and yields lazily (e.g. `itertools.islice` returns the first K without exhausting a large input).
- **FindReplaceBar (pytest-qt):** `set_find_all_running` toggles the button text; `find_all()` calls `on_find_all` when idle and `on_stop_find_all` when running; `replace_all()` fires the `on_status` count message (including the 0-match case).
- **MainWindow (pytest-qt):**
  - Completion via `qtbot.waitUntil(lambda: not bar._find_all_running)`: assert result items + summary present and final status `Found N item(s)`.
  - Deterministic stop: start the run, stop its timer, drive `_find_all_step()` once manually to process a batch, call `_stop_find_all()`, drive one more step to finish — assert partial results kept, bar reverted, status starts with `Find All stopped`.
  - Live-count status string after a batch.
- All new UI tests must patch any modal they could reach (none expected here); the suite's `--timeout` guard will catch a hang.
