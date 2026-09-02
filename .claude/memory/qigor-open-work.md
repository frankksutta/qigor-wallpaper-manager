---
name: qigor-open-work
description: "Where QiGor stands after the 2026-09-02 UI session: 9 commits sitting unpushed, 0.8.3 bumped but never built, and the improvements frank was told about but has not decided on."
metadata:
  node_type: memory
  type: project
  modified: 2026-09-02T06:30:00.000Z
---

State at the end of 2026-09-02, when frank shut the machine down mid-stream.
He said there were "more improvements to work on" — so expect to be picking
this up, not starting fresh.

**Nine commits are on local `master` and unpushed** (`f19cd2c` … `ac75f5c`).
Frank asked to commit, not to push, and the repo is public — offer, don't
push unasked. Nothing is uncommitted; the tree was clean.

**0.8.3 is bumped in `app/constants.py` but has never been built or
uploaded.** Every UI change from this session is source-only: the installed
copy is still the released 0.8.2 and will not see any of it. A release needs
📦 Build Installer then 🐙 Upload Release, all four assets — details in
[[installer-release-state]].

What changed this session, so the shape is clear before reading the diffs:
the Wallpaper tab was split by purpose (preview + controls left, selector +
store + history right); Gallery URLs became its own last tab; an Image store
pane lists the saved files; both image tabs are now built from
`app/imagepanes.py` (`PaneSpec` describes a tab's differences, `PaneSet` holds
its own widgets and the shared picking behaviour), which is what let the Lock
Screen tab stop borrowing the Wallpaper tab's selection.

**Raised with frank, still undecided — do not just do these:**

- **Emoji in the toolbar cost ~0.7s of startup.** Removing them is the only
  real fix left; he has not been asked to give them up. See
  [[tk-startup-cost-emoji]].
- **Hint paragraphs are centre-justified** in the Slideshow and Reminder
  panes (Tk `Label` default with `wraplength`), which reads oddly against the
  left-aligned rows beside them. One `justify=tk.LEFT` per label.
- **The Lock Screen tab has no History pane.** Nothing records lock-screen
  changes, so there is nothing to list. `PaneSpec.show_history` is the flag;
  it needs a new config key to back it.
- **"Image store" now names two things** — the toolbar button that opens the
  folder in Explorer, and the pane that lists it. Frank chose the pane's name
  knowing that. Renaming either is his call.
- **The hero image is 54x30**, sized to the toolbar buttons so the toolbar
  does not grow. A wide banner crop of the 1000x558 original would fill the
  empty toolbar space for ~10px of height; full size costs ~54px and forces
  the Wallpaper tab's left column to show its scrollbar.

**All three scrollbars render light grey on the dark theme** and cannot be
fixed the obvious way: Windows draws `tk.Scrollbar` itself and ignores its
colour options, and `ttk.Scrollbar` under the `clam` theme came out beige
(#dcdad5) rather than the configured colours. Measured at the widgets' real
coordinates — an earlier reading that said ttk worked was a mis-aimed pixel
sample. Left alone rather than guessed at.

Testing this GUI: [[gui-overhaul-untested-handoff]]. Startup cost:
[[tk-startup-cost-emoji]]. Distribution: [[installer-release-state]].
