# Plan: Slideshow Test Task — status refresh + stale diagnostics

## Architecture Decisions
- Extract the inline `_fetch_status` closure from `__init__` into a proper
  `_refresh_status()` instance method so it can be reused from `_on_test_done()`.
- Add module-level `slideshow_is_overdue()` that reads only the state file —
  no schtasks call, locale-independent, fast.
- Add `_on_test_done()` as the single post-wait callback in `_test_task()`,
  replacing the direct `self.after(2500, self._view_log)` call.
- All changes in app/slideshow.py only.

## Phase 1 — Implementation

- [x] Add module-level `slideshow_is_overdue() -> tuple[bool, str]`
  File: app/slideshow.py (after slideshow_last_run_failed, ~line 587)
  Reads state file; returns (True, human-readable description) if
  now - last_set > 2 × interval_min, otherwise (False, "").
  → verify: syntax OK; function present in file.

- [x] Extract `_fetch_status` into `SlideshowDialog._refresh_status()`
  File: app/slideshow.py, SlideshowDialog class
  New method: spins background thread, calls is_scheduled() + query_task_status(),
  then calls slideshow_is_overdue() and appends overdue warning to status string
  if True; colors label yellow when warning present; updates status_var and
  running state via self.after(0, ...).
  Updated __init__ to call `self._refresh_status()` instead of inline _fetch_status.
  → verify: syntax OK; method present.

- [x] Add `_on_test_done()` and update `_test_task()` wait
  File: app/slideshow.py, SlideshowDialog class
  Changed `self.after(2500, self._view_log)` → `self.after(4000, self._on_test_done)`.
  `_on_test_done()`:
    1. Calls self._refresh_status()
    2. Reads log file, filters lines timestamped within last 15 s
    3. If any filtered line contains "Skipping: too soon", shows
       messagebox.showinfo explaining the guard, last_set, and interval
    4. Calls self._view_log()
  → verify: syntax OK; method present.

## Phase 2 — Verification

- [x] Syntax check passed: `python -c "import ast; ast.parse(open('app/slideshow.py', encoding='utf-8').read()); print('OK')"` → OK
