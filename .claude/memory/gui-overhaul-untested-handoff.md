---
name: gui-overhaul-untested-handoff
description: "The 2026-09-01 GUI overhaul (whole-app zoom, tabs, theming) has now been driven button-by-button; source is 0.8.3 and every interactive path the old handoff listed as unproven passes."
metadata:
  node_type: memory
  type: project
  originSessionId: 2a67fce0-3b0b-4a79-9e50-02c6aa86dfbf
  modified: 2026-09-03T10:50:53.831Z
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
- **A background thread's `after()` call does nothing without a mainloop.**
  Every panel here fetches on a thread and marshals back with
  `self.after(0, ...)`, wrapped in `except (tk.TclError, RuntimeError)`. Drive
  the app with bare `update()` calls and that raises and is swallowed, so
  previews stay blank and the tab tick never appears — and it looks exactly
  like a bug you just introduced. It cost time twice. To test anything that
  crosses a thread, run a real `root.mainloop()` and assert from `after()`
  callbacks, then `root.quit()`.
- Tk refuses `event_generate("<Double-Button-1>")` ("Double, Triple, or
  Quadruple modifier not allowed"). Check the binding exists and run its
  script, or call the handler.
- A log window's master is its panel, not root, so `root.winfo_children()`
  misses it. Walk the whole tree.
- **`ImageGrab` + Tk coordinates do not line up on this machine**, and the
  mismatch is silent: the capture looks like a real screenshot with a third of
  the window missing. Two separate causes, both present here. (a) The display
  is 3840x2160 at 150% and Tk is DPI-*unaware*, so Windows stretches the
  window: Tk reports 974px where the pixels are 1461. (b) With
  `all_screens=True` the bbox is measured from the top-left of the *virtual*
  desktop, while Tk measures from the primary monitor - so anything left of or
  above the primary shifts it (67px, here). Fix: call
  `ctypes.windll.shcore.SetProcessDpiAwareness(1)` **before** `tk.Tk()` and
  offset the bbox by `GetSystemMetrics(76/77)`. Awareness changes only how
  large the layout is drawn, not the layout - but every pixel figure measured
  under it is then 1.5x the app's own, so **never take a sizing decision from
  a DPI-aware harness**: a console-height "fix" was written against numbers
  that were all 50% too big and had to be backed out.
- Screenshots: `PrintWindow` with `PW_RENDERFULLCONTENT`, but
  `CreateCompatibleBitmap` must take the **window** DC — a fresh memory DC
  holds a 1×1 monochrome bitmap, so passing it gives 1 bpp and an all-black
  capture — and the bitmap must be selected back *out* before `GetDIBits`.
- **A PrintWindow capture is not proof of what the screen shows.** `⬇`
  (U+2B07) came out as a tofu box on a button in the capture and drew as an
  arrow in every isolated render of the same font object, widget class,
  Toplevel and post-creation `config(text=…)`. Other symbols in the same
  window (`☑ ☐ ⇄ • ×`) captured fine. Don't change a glyph on a capture alone
  — ask frank what he sees. (2026-09-03, the Import picker.)
- **Never judge colours by looking at a capture**; sample the pixels. Reading
  the rendered PNG called a correctly light-themed dialog "dark" twice, and
  called a `#2d2d2d` listbox white. `Image.getpixel` and a mean-brightness
  figure settled both in seconds.
- **ImageGrab still lands in the wrong place with DPI awareness set alone** —
  a grab of `winfo_rootx/y` + `winfo_width/height` returned desktop wallpaper,
  not the button. The offset in the bullet above is needed even DPI-aware;
  PrintWindow is the cheaper path.

Distribution state in [[installer-release-state]], what is still open in [[qigor-open-work]], why startup is slow in [[tk-startup-cost-emoji]].
