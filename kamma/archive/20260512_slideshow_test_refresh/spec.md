# Spec: Slideshow Test Task — status refresh + stale diagnostics

## Overview
Fix the "Test Task" button in the Slideshow dialog so that:
1. The status label refreshes after firing the task (currently stays stale forever).
2. A popup explains if the guard silently blocked the wallpaper change.
3. An overdue warning appears when the task hasn't changed the wallpaper in >2× the configured interval.

Reported: EXE installation set to "Daily" on dad's computer; hasn't rotated in 5 days.
Test Task button fires without error but status still shows "Last ran: 5 days ago."

## What it should do
1. After clicking "Test Task" and the 4 s wait, the status label shows the
   updated "Last ran" time (not the old stale time).
2. If the task ran but the 90%-interval guard blocked the wallpaper change,
   a messagebox explains: last_set timestamp, interval, and that the wallpaper
   will change when the full interval elapses.
3. If the state file's `last_set` is more than 2× the configured interval old,
   the status line appends "⚠ Slideshow overdue — click ▶ Start to re-register."
   and the label is colored yellow.

## Assumptions & uncertainties
- Root cause of the 5-day gap on dad's machine is unknown; cannot reproduce remotely.
  These changes surface the symptom clearly and add diagnostics without guessing
  the underlying scheduler cause.
- `last_set` is updated only on a successful wallpaper set (not on guard skips),
  making it a reliable proxy for "last time wallpaper actually changed."
- schtasks field names are locale-dependent; we use the state file for overdue
  detection (locale-independent) rather than parsing schtasks date output.

## Constraints
- All changes confined to app/slideshow.py.
- No new dependencies.
- Behavior of Start, Stop, Next Now, and Log buttons must remain unchanged.

## How we'll know it's done
- After clicking Test Task, status label updates to a recent time within ~5 s.
- If guard blocked the run, a popup appears with a clear explanation.
- When last_set is >2× interval old and the task is scheduled, a yellow warning
  appears in the status line.

## What's not included
- Fixing the unknown root cause of the 5-day gap.
- Changing the Windows Task Scheduler XML trigger structure.
- Changes outside app/slideshow.py.
