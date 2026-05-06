# Spec — Slideshow runner resolution fix

## Overview
`schedule_task()` in `app/slideshow.py` has two bugs that silently break the slideshow:

1. **Wrong runner when not frozen:** when the app runs as a `.pyw` script (`sys.frozen=False`),
   the task is created with `pythonw.exe <script> --next` instead of the EXE. Developers who
   switch between the pyw and EXE versions silently end up with a mismatched scheduler task.

2. **Broken script path via `-c`:** when `sys.argv[0]` is `-c` (launched via `python -c "..."`),
   `Path("-c").resolve()` produces `<cwd>/-c` — a non-existent file. The task registers
   successfully but every run fails with exit code 2 (file not found). This broke the slideshow
   on 2026-05-04 13:46; the wallpaper has been stuck since then.

Additionally, if the user moves or updates the EXE to a new path after initial setup, the
existing scheduled task silently fails forever — no warning is shown.

## What it should do

### get_expected_runner() — shared resolution logic
Priority order:
1. If `sys.frozen`: return `sys.executable`
2. Else look for `QiGor_Wallpaper_Manager.exe` in `Path(__file__).resolve().parent.parent`
3. Else glob `*.pyw` then `*.py` in same directory, return first match
4. Return `None` if nothing found

### schedule_task() — use get_expected_runner()
- Call `get_expected_runner()`
- If `None` → return `(False, "Cannot find the application runner…<user-readable message>…")`
- If ends with `.exe` → `cmd_exe = runner, cmd_args = "--next"` (frozen-style)
- Else → `cmd_exe = pythonw, cmd_args = '"<runner>" --next'`
- Log `[SETUP] Runner: <runner>` before calling schtasks

### slideshow_runner_is_stale() — startup stale check
- Query `schtasks /query /tn QiGorWallpaperSlideshow /fo LIST /v`
- Parse "Task To Run" line to extract the registered command path
- Compare (case-insensitive) to `get_expected_runner()`
- Return `True` if scheduled and paths differ

### app.py startup check
- After `_show_last_changed()`, run `slideshow_runner_is_stale()` in a background thread
- If stale → log yellow warning: "⚠ Slideshow task points to an old location. Open Slideshow → ▶ Start to update it."

## Assumptions & uncertainties
- EXE name is `QiGor_Wallpaper_Manager.exe` (confirmed from app.py line ~1047)
- Project root = `Path(__file__).resolve().parent.parent`
- `schtasks /query /fo LIST /v` "Task To Run" line has the exe path as first token
- Frozen path (`sys.frozen=True`) is correct and unchanged

## Constraints
- `schedule_task()` and new helpers in `app/slideshow.py` only
- Startup check: one background-thread log call added to `app/app.py`
- No new files, no UI widget changes

## How we'll know it's done
- Re-create task via Slideshow → ▶ Start → schtasks shows real EXE or .pyw path (not `\-c`)
- Stale check: if task "Task To Run" doesn't match current runner → yellow warning in console on startup

## What's not included
- Sleep/wake trigger changes (log showed sleep recovery already worked)
- Auto-repair of stale task (user must click ▶ Start — intentional, avoids surprise)
- UI widget changes
