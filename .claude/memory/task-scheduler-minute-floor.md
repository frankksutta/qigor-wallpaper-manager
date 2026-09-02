---
name: task-scheduler-minute-floor
description: "Windows Task Scheduler rejects any repetition interval under one minute — measured, not assumed — which is why QiGor's slideshow preview runs on a Tk timer instead."
metadata: 
  node_type: memory
  type: reference
  modified: 2026-09-02T19:03:00.378Z
  originSessionId: 9641bd5b-99f1-45d2-bd5f-d294ab70dce8
---

Probed on this machine on 2026-09-02 by registering and deleting a throwaway
task for each value:

| `<Interval>` | `schtasks /create` |
|---|---|
| `PT5S`   | ERROR: value ... out of range  `(3,55):Interval:PT5S` |
| `PT30S`  | ERROR: same |
| `PT1M30S`| SUCCESS |
| `PT100S` | SUCCESS |

So the floor is one minute, and above it sub-minute components are fine —
`PT100S` is accepted as 1m40s. Frank asked for a 5–100 second slideshow
preview "using the same mechanism, scheduled windows tasks"; only the 60s and
100s ends of that range are schedulable at all, and even those could not fire
sooner than the task's StartBoundary, which `schedule_task()` sets a minute
out. A preview that takes a minute to show its first image is not a preview.

That is why `SlideshowPanel._preview_tick` is a 1-second `after` loop: it
calls the *same* `slideshow.advance()` the scheduled runner calls, with
`persist=False` so the real rotation's `queue_index`/`last_set` are untouched.
The mechanism is shared even though the trigger cannot be.

Related: [[qigor-open-work]], [[tk-startup-cost-emoji]].
