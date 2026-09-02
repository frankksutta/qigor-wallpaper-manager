---
name: tk-startup-cost-emoji
description: "QiGor's ~1.9s startup is mostly Windows resolving a font for the first emoji glyph in Tk (716ms, one-time, main thread) — not app logic, and not fixable by threading."
metadata:
  node_type: memory
  type: project
  modified: 2026-09-02T06:30:00.000Z
---

Measured 2026-09-02 while chasing "long pause before the app starts". Profiling
blamed `tk.Button` creation — 36 buttons, 1.0s — but buttons in isolation cost
0.002s for 36. The real cost is per-*glyph*, paid the first time Tk has to
render an emoji:

| what | cost |
|---|---|
| plain ASCII button | 0.8 ms |
| **first emoji button (📁)** | **716 ms** |
| same emoji again | 0.2 ms |
| each further new emoji | 7–29 ms |

So the toolbar's first two emoji buttons (`📁 Image store`, `☀`) accounted for
830ms of a 1.0s build. It is Windows loading an emoji-capable fallback font,
inside Tk, on the main thread, once per process.

**This cannot be threaded away.** Tk is single-threaded; calling into it from
another thread is unsafe, and `after()` from a background thread is the only
legal route back. The only real levers are:

- drop emoji from the toolbar button labels (frank has not been asked to give
  them up — offer, don't decide), or
- build and map the window in stages so it appears before the emoji render.

**Do not go looking for this in app logic again.** As of `ac75f5c` nothing on
the main thread queries the scheduler, reads the registry or touches the
network before the window is drawn — that all moved to `App._finish_startup`
on `after_idle`. Verified by stubbing `schtasks` at 1.2s/call: the window still
drew in 1.9s and selecting the Slideshow tab blocked for 25ms.

**Never call `schtasks` on the main thread.** That is what regressed the
Slideshow tab: the panel's query was threaded in `daa9e91`, then `4b02a63`
(tab tick markers) added a second, synchronous `is_scheduled()` beside it in
both `_on_tab_changed` and `App.__init__`. The panel now reports through its
`on_scheduled` callback from the query it was already running. If a tab needs
scheduler state, take it from there — do not ask again.

Measuring on this machine is misleading: `schtasks /query` returns in 0.02s
here even verbose and even for a task that exists, so frank's multi-second
pause never reproduced locally. Stub the call slow to prove a fix.

Testing lessons for this GUI are in [[gui-overhaul-untested-handoff]].
