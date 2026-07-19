# Debug Mode (`--debug` diagnostic logging) — Design

**Date:** 2026-07-19
**Component:** new module `pgtp_editor/debuglog.py`, `pgtp_editor/main.py`
(activation), `pgtp_editor/ui/main_window.py` (status chip, Help menu item,
seam logs), seam log lines across existing modules.

## Goal

Launching the app with `--debug` produces a greatly detailed diagnostic log —
detailed enough that a user can hand the file over after something misbehaves
and the fault can be located from the log alone. In normal mode a lightweight
always-on error log still captures crashes that happen outside debug sessions.

Chosen mechanism: **auto-trace + seams** — NOT a manual rewrite of every
function. A Python-level tracer logs every `pgtp_editor` function
call/return/exception automatically (including functions written in the
future); hand-written log lines exist only at ~15 semantic seams. Working code
is not restructured.

## Non-goals (YAGNI)

- Log viewer UI, remote upload/telemetry, log-level configuration UI.
- Event-loop stall profiler / performance metrics.
- Tracing third-party code (Qt internals, lxml, psycopg) — only `pgtp_editor`
  frames are traced; third-party failures surface as exceptions and seam logs.

## 1. Activation & files

- `python -m pgtp_editor.main --debug` — parsed with `argparse` in `main.py`.
  Setting the environment variable `PGTP_EDITOR_DEBUG=1` is equivalent (for
  shortcuts that can't pass args). Unknown args keep failing as argparse
  normally does.
- `main.py` calls `debuglog.setup(debug=<flag>)` **before** creating
  `QApplication`, so even startup crashes are captured.
- Log directory: `%LOCALAPPDATA%\MDS\PGTP Editor\logs\` (created on demand;
  falls back to `~/.pgtp_editor/logs` if `LOCALAPPDATA` is unset — non-Windows
  dev environments). Resolved by pure function `debuglog.log_dir()`.
  - `errors.log` — always-on, `WARNING` and above, `RotatingFileHandler`
    (3 backups × 1 MB).
  - `debug_YYYYMMDD_HHMMSS.log` — created per `--debug` session, full detail,
    not rotated (one file per session; old sessions are the user's to delete).
- Debug-mode startup: the resolved debug-log path is printed to stderr and
  shown once in the status bar; a permanent "DEBUG" label sits in the status
  bar for the whole session.
- **Help ▸ Open Log Folder** (both modes): opens `log_dir()` via
  `QDesktopServices.openUrl`; guarded by an injectable seam (`opener=`) so
  tests never launch a real Explorer window.

## 2. Captured content

### Always (both modes)

- **Session header** (first lines of every log session): app version, Python
  version, PySide6/Qt versions, platform string, settings file path, log dir,
  argv, debug flag.
- **Uncaught exceptions** with full traceback from:
  - the main thread — `sys.excepthook`;
  - worker threads — `threading.excepthook`;
  - Qt slots — Qt/PySide swallows exceptions raised inside slots after
    printing; our `sys.excepthook` replacement is registered so PySide's
    slot-exception path (which routes through `sys.excepthook`) logs the full
    traceback before returning control. The app does not abort on a logged
    slot exception in either mode (current PySide behavior preserved).
- **Qt messages**: `qInstallMessageHandler` forwards
  qDebug/qInfo/qWarning/qCritical to the Python logging tree (qFatal is logged
  then follows Qt's abort).
- **Python warnings**: `logging.captureWarnings(True)`.

### Debug mode adds

**(a) Auto-trace** — `sys.monitoring` (Python 3.12+; project runs 3.13),
registered on `sys.monitoring.PROFILER_ID` (fail gracefully per §5 if the
slot is already in use), events `PY_START`, `PY_RETURN`, `RAISE`:

- Scope filter: only code objects whose `co_filename` is inside the
  `pgtp_editor` package directory are traced (pure predicate
  `_is_traced(code)` — cached per code object via
  `sys.monitoring.DISABLE` for out-of-scope/excluded code, so the steady-state
  overhead of non-traced frames is near zero).
- **Exclusion list** of flooding hot paths, matched by `(module suffix,
  qualname prefix)` pairs — initial list (extended during implementation as
  flooding is observed):
  - `ui.xml_editor`: `paintEvent`, `_EditorGutter.*`, `_draw_*`,
    `line_number_area_*`, `highlightBlock`, `_matching_tag*`, `blockCount*`,
    `updateRequest*`
  - `ui.syntax` / highlighter classes: `highlightBlock`, `rehighlight*`
  - `model.line_index`: everything (hot loops)
  - event-filter/paint plumbing: `eventFilter`, `sizeHint`
- Trace line contents: direction marker (`>` call, `<` return, `!` raise),
  depth indentation (per-thread depth counter), `module.qualname`, definition
  line number; raises include `repr(exc)`. **Function arguments and return
  values are NOT logged** (cost/size; exceptions carry the diagnostic value).
- The tracer writes through a dedicated `TRACE` logging level (numeric 5)
  into the debug file handler only.

**(b) Seam logs** — plain `logging.getLogger(__name__)` INFO/DEBUG lines at
the semantic seams, stating what the app is doing in domain terms. The seam
set (~15, final list fixed during implementation):

| Seam | Content |
|---|---|
| File open / save / save-as / revert / close | path, size, outcome |
| Parse / reparse | ok/fail + error summary |
| Undo/redo snapshot push/restore | label, history depth |
| DB connect / test / check start+end | host/port/db/user (NO password), direction, duration, result counts |
| DB rename apply | attribute, old→new, replacement count |
| Generation | full command line, working dir, return code, duration |
| Schema enrich | file, paths/attributes counts |
| Diff/Merge apply | files, hunk counts |
| Caption apply | rows changed |
| Theme / toolbar / dock changes | new state |
| Dialog open/close (non-modal drivers) | dialog name |

### Redaction

The DB password never reaches any log: seam logs format `ConnectionParams`
through a `redacted()` helper (password replaced by `***`); auto-trace never
logs arguments, so no incidental leak path exists. A pure unit test locks
this in.

## 3. Log format

Plain text, greppable, one event per line:

```
14:02:11.482 INFO  [gui ] db: check XML→DB started project=demo.pgtp host=127.0.0.1 db=demo user=mds
14:02:11.483 TRACE [gui ]   > ui.main_window.MainWindow._run_db_check :1231
14:02:11.490 TRACE [pool]     > db.introspect.fetch_schema :88
14:02:11.702 TRACE [pool]     ! db.introspect.run_queries OperationalError('connection timeout')
14:02:11.703 ERROR [gui ] uncaught in Qt slot: Traceback (most recent call last): ...
```

`%(asctime)s.%(msecs)03d LEVEL [thread] message` — thread names shortened
(`gui` for the main thread, pool workers by their QThreadPool/threading name).

## 4. Module boundaries

- **`pgtp_editor/debuglog.py`** — the only new module; owns: `setup(debug)`,
  `log_dir()`, the TRACE level registration, the `sys.monitoring` tracer
  (install/uninstall), exclusion predicate, excepthook installs, Qt message
  handler, `redacted()`. Importable and testable without a QApplication
  (Qt handler install is skipped gracefully when Qt isn't loaded yet and
  re-invoked by `main.py` after app creation).
- `main.py` — argparse (`--debug`), env-var check, `debuglog.setup()` call
  ordering.
- `main_window.py` — status-bar DEBUG chip, Help ▸ Open Log Folder, seam log
  lines (as are the other modules': each seam is a one-line addition at an
  existing method, not a restructure).

## 5. Failure safety

- If tracer installation fails (`sys.monitoring` tool slot taken, unexpected
  platform), the app starts anyway and logs one WARNING; seam + error logging
  still work.
- If the log directory can't be created, logging falls back to stderr only
  (never crashes the app for logging's sake).
- Logging handlers use `delay=True` so no file is touched until first record.

## 6. Testing

Pure/unit (no Qt): `log_dir()` fallback logic; exclusion predicate decisions
(hot path excluded, normal path traced, non-pgtp_editor file ignored);
`redacted()` never contains the password; TRACE level registered once.

Integration (offscreen Qt, tmp log dir via monkeypatched `log_dir`):
- `setup(debug=True)` creates the session file; `setup(debug=False)` creates
  only the rotating error handler config (no debug file).
- A raised-and-caught synthetic uncaught exception through the installed
  excepthook lands in `errors.log` with the traceback.
- With the tracer active, calling a small real `pgtp_editor` function writes
  `>`/`<` lines; calling an excluded one writes nothing.
- Qt message handler: `qWarning("boo")` lands in the log.
- `main.py` arg parsing: `--debug` and `PGTP_EDITOR_DEBUG=1` both yield
  debug=True (parse seam tested without launching the app).
- Seam-log smoke: opening a project file in a test MainWindow writes the
  `file: open` INFO line.
- No modals anywhere; Open Log Folder uses the `opener=` seam.

Suite-wide guard: `setup()` is NOT auto-invoked on import, so the existing
1200+ tests are untouched unless a test opts in.

## 7. Delivery

One feature branch in a worktree off `main`; TDD; feature-tester agent run at
completion (per testing policy) with a `docs/TEST_LOG.md` entry; two-stage
review; `--no-ff` merge. Manual gets a short "Troubleshooting / debug mode"
section documenting the flag, the env var, and Help ▸ Open Log Folder.
