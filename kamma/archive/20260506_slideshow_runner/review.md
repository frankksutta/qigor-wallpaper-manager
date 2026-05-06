## Thread
- **ID:** 20260506_slideshow_runner
- **Objective:** Fix silent slideshow failures: wrong runner detection, stale-task warning, toast on in-app errors

## Files Changed
- `app/slideshow.py` — added `get_expected_runner()`, `_query_task_fields()`, `slideshow_runner_is_stale()`, `slideshow_last_run_failed()`; fixed `schedule_task()` non-frozen branch; added `_toast()` helper and calls at all error exits in `_run_next_headless()`
- `app/app.py` — added `_check_slideshow_runner()` background-thread startup check; updated import

## Findings
No findings.

## Fixes Applied
- Corrected `get_expected_runner()` to use specific filenames (`QiGor_Wallpaper_Manager.exe`, `qigor_wallpaper_manager.pyw`) instead of a blind glob that was picking up `ai_patch_apply_launch.pyw`
- Corrected `slideshow_runner_is_stale()` stale check to use `in` substring match rather than prefix-strip parsing (handles both EXE and pyw task command formats)

## Test Evidence
- `get_expected_runner()` → `qigor_wallpaper_manager.pyw` (correct, not `ai_patch_apply_launch.pyw`) ✓
- `slideshow_runner_is_stale()` → `True` with broken task registered ✓
- `slideshow_last_run_failed()` → `False` (last result was 0) ✓
- `_run_next_headless(force=True)` with fake folder → log shows `ERROR: folder not found`, state restored cleanly ✓
- Toast path confirmed reachable; `winotify` installed and importable ✓

## Verdict
PASSED
- Review date: 2026-05-06
- Reviewer: kamma (inline)
