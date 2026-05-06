# Plan — Slideshow runner resolution fix
# Thread: 20260506_slideshow_runner

## Architecture Decisions
- Extract `get_expected_runner()` so `schedule_task()` and `slideshow_runner_is_stale()` share
  identical resolution logic — no duplication, no drift.
- Resolve runner from `Path(__file__)` (package-relative), never `sys.argv[0]`.
- EXE beats pyw so dev and prod tasks stay identical.
- Stale check is read-only (query + log); no auto-repair to avoid surprising the user.
- Background thread for startup check mirrors existing pattern (schtasks can block ~2–5s).

## Affected files
- `app/slideshow.py` — add `get_expected_runner()`, `slideshow_runner_is_stale()`, fix `schedule_task()`
- `app/app.py` — add one background-thread stale check after `_show_last_changed()`

---

## Phase 1 — Fix schedule_task() + extract get_expected_runner()

- [x] Add `get_expected_runner() -> str | None` in `app/slideshow.py` (above `schedule_task()`):
  - If frozen: return `sys.executable`
  - Else: `pkg_root = Path(__file__).resolve().parent.parent`
  - Check `pkg_root / "QiGor_Wallpaper_Manager.exe"` — return if exists
  - Glob `*.pyw` in pkg_root, return first sorted match if any
  - Glob `*.py` in pkg_root, return first sorted match if any
  - Return `None` if nothing found
  → verify: function returns a real path (not None, not ending in `-c`) when called from the
    dev environment

- [x] Rewrite non-frozen branch of `schedule_task()` to use `get_expected_runner()`:
  - Call `get_expected_runner()`
  - If `None`: return `(False, "Cannot find the application …")`
  - If runner ends with `.exe`: use frozen-style command (`cmd_exe=runner, cmd_args="--next"`)
  - Else: use script-style (`cmd_exe=pythonw, cmd_args='"<runner>" --next'`)
  - Log `[SETUP] Runner: <runner>` before calling schtasks
  → verify: after clicking ▶ Start in Slideshow dialog, `schtasks /query /tn QiGorWallpaperSlideshow /fo LIST /v`
    shows a real file path in "Task To Run", not `\-c`

## Phase 2 — Startup stale-task check

- [x] Add `slideshow_runner_is_stale() -> bool` in `app/slideshow.py`:
  - Run `schtasks /query /tn QiGorWallpaperSlideshow /fo LIST /v` (timeout 8s)
  - If returncode != 0: return False (task not scheduled)
  - Parse "Task To Run" line; extract everything before " --next" as the registered path
  - Compare registered path to `get_expected_runner()` (case-insensitive, strip quotes)
  - Return True if they differ; False if they match or runner is None
  → verify: function returns True when task "Task To Run" is the broken `\-c` path

- [x] In `app/app.py` `__init__`, after `self._show_last_changed()`:
  - Import `slideshow_runner_is_stale` at top of file (alongside existing slideshow import)
  - Spawn background thread: if `slideshow_runner_is_stale()` → `self._log_threadsafe(…, "yellow")`
  → verify: on app startup with current broken task, yellow warning appears in console
