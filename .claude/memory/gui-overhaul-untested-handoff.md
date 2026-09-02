---
name: gui-overhaul-untested-handoff
description: "The 2026-09-01 GUI overhaul (whole-app zoom, tabs, theming) has now been driven button-by-button; source is 0.8.3 and every interactive path the old handoff listed as unproven passes."
metadata:
  node_type: memory
  type: project
  originSessionId: 2a67fce0-3b0b-4a79-9e50-02c6aa86dfbf
  modified: 2026-09-02T04:05:00.000Z
---

Four commits on 2026-09-01 built the overhaul (`27b463f` zoom, `540f6f2`
Slideshow/Reminder as tabs, `bb1fe29` contrast + Lock Screen tab, `4b02a63`
pane headings). `f19cd2c` on 2026-09-02 closed it out.

**`APP_BUILD` is now 0.8.3**, so the source no longer collides with the
published 0.8.2. The copy at `%LOCALAPPDATA%\Programs\QiGorWallpaperManager` is
still the old 0.8.2 without the GUI work — run from source to see the new UI.
Nothing has been built or uploaded at 0.8.3 yet; see
[[installer-release-state]] for what a release needs.

**All of it has now been exercised.** 16 buttons across the Slideshow and
Reminder tabs, both menubutton drop-downs, the favourites context menu, the
frequency radios and every combobox value — plus the log windows, the update
window and About, each opened and dismissed through its own Close button. Zero
failures, no leaked grabs, no orphaned Toplevels. The `_finish()`-instead-of-
`destroy()` conversion is sound.

**`f4fc0cd` fixed the one the sweep could not see: File and Help opened no
menus at all.** Both were created as children of root and handed over with
`-menu`; Tk accepts that and everything looks right, but **a Menubutton can
only post a menu that is its own descendant**, so the click did nothing — no
menu, no error, nothing in a `.pyw`. Each menu is now built as a child of its
own Menubutton. The lesson for testing: `menu.post()` works from any
parentage and `menu.invoke(i)` runs the entries regardless, so checking the
menus proves nothing about the buttons. Only pressing the Menubutton exercises
the descendant rule — click it and watch for a `#32768` window.

Three bugs that only showed up by doing it, the first two fixed in `f19cd2c`:

- **Dim hint text was never dim.** `_apply_theme_recursive` painted every Label
  with the plain foreground, and `_apply_theme()` runs at the end of
  `App.__init__` — so this was not a toggle problem and a restart did not help,
  contrary to what this note used to say. A widget now records its palette role
  (`mark_role`/`role_fg`/`paint_role` in `constants.py`) and the pass
  re-resolves it, so dim also switches to the light palette's dim.
- **The Reminder tab's Day / Every-N row was orphaned** below the separator at
  the foot of the panel, because `_on_freq_change` runs last in `__init__` and
  `pack()` appends. It packs `before=` the At-time row now.

Known cosmetic nit, deliberately left: the wrapped hint paragraphs in both
panels are centre-justified (Tk's `Label` default), which reads oddly against
the left-aligned rows. One `justify=tk.LEFT` per label; frank has not asked.

Driving the GUI from a script, the things that cost the most time:

- **Never `menu.post()` or `tk_popup()`** — a Windows menu enters its own modal
  loop nothing scripted can dismiss, and `after` timers do not run inside it.
  Stub both to recorders and call `menu.invoke(i)` on the entries instead. But
  that stub is exactly what hid `f4fc0cd`: to test that a *button* opens a
  menu, click it, then look for a visible `#32768` window from a **separate
  thread** (threads keep running inside the modal loop; the main thread does
  not). A click that returns instantly means no menu; a click that blocks
  means it opened. Nothing in-process can dismiss it, so expect that probe to
  end in a timeout and click one button per run.
- **The app waits on some dialogs** (`root.wait_window`), which starts a nested
  loop that `update()` outside it can never escape. A repeating `root.after`
  watchdog that closes any mapped Toplevel does get to run in there. Skip
  `.popdown` windows — those are combobox lists, not dialogs.
- A log window's master is its panel, not root, so `root.winfo_children()`
  misses it. Walk the whole tree.
- Screenshots: `PrintWindow` with `PW_RENDERFULLCONTENT`, but
  `CreateCompatibleBitmap` must take the **window** DC — a fresh memory DC
  holds a 1×1 monochrome bitmap, so passing it gives 1 bpp and an all-black
  capture — and the bitmap must be selected back *out* before `GetDIBits`.

Distribution state in [[installer-release-state]].
