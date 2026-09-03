---
name: qigor-sync-open-work
description: "Handoff for the wallpaper SYNC tool after 2026-09-03: five restyled tabs, the ttk clam switch they needed, what is open, and the three hazards to know before touching it."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6bdc9b61-d049-49ba-9611-50846bf90165
  modified: 2026-09-03T04:20:00.000Z
---

Handoff written at frank's request at the end of **2026-09-02**: "more
improvements tomorrow". This covers `qigor_wallpaper_sync/` only — the
wallpaper *manager* is [[qigor-open-work]].

## What it is now

`qigor_wallpaper_sync/` is **its own git repository with no remote**, ignored
by the outer public repo (see the note at the foot of the outer `.gitignore`).
So its commits are never part of the manager's unpushed pile, and there is
nowhere to push them. Five commits exist; four are from 2026-09-02:

| | |
|---|---|
| `3ae071d` | **New Images** tab — file a downloaded picture into a pack |
| `fd1fec9` | finish a half-done move; `gdrive.py`, no drive letters written down |
| `0e3bdef` | match the Drive **account** too, not just the folder |
| `6ad624f` | one window for both names; the move pane |
| `3a86759` | **Move** is a tab, moves are complete, `recycle.py` |
| `4a53b79` | startup 5.3s → 1.4s |
| `3e3b985` | the GUI drivers and profilers moved into `tests/` |
| `3f2b4be` | **2026-09-03**: the tab strip, and the ttk theme swap it needed |

Tabs: **Sync / Folders / New Images / Move / Upload setup**. Pure-data modules
with no tkinter: `sync_core`, `ia_client`, `svault_client`, `new_images`,
`gdrive`, `recycle`. The README is long and current — read it before the code;
every non-obvious decision is in it with the measurement that justified it.

## Three hazards

1. **`ia_client.delete_files` really deletes from archive.org**, and the Move
   tab calls it. `configured_status()` is TRUE on this machine because the
   vault is unlocked, so **any test that exercises a move must stub it** —
   `tests/drive_items.py` does. The library's `debug=True` prepares a delete
   request and sends nothing, which is how the call shape was checked against
   a real item.
2. **frank uses these tools while a session runs.** On 2026-09-02 he added
   two pictures to the real `I:` pack mid-session and his config changed under
   the session twice. Never assume the config or the pack is what you last
   saw; copy his config to a temp dir for any live check (see
   `tests/profile_startup.py`).
3. **Listing a folder on `I:` costs ~0.5s** and **the first emoji in the
   process costs ~0.9s** — the two reasons startup was five seconds. Full
   numbers and the rules that follow from them:
   [[drive-listing-costs-half-a-second]].

## Testing

    python tests\test_sync.py            248 checks, offline
    python tests\test_sync.py --live     265, also hits archive.org read-only
    python tests\drive_new_images.py     104 checks, drives a real window
    python tests\drive_items.py           92 checks, Folders + Move
    python tests\profile_startup.py      where startup time goes
    python tests\profile_widgets.py      which widget class costs it

They were in the session scratchpad until `3e3b985` and are now in the repo,
paths relative. A modal dialog can only be driven by `after` timers scheduled
**before** it opens — its `wait_window` nested loop is unreachable from
outside. More Tk-driving lessons: [[gui-overhaul-untested-handoff]].

## 2026-09-03: the tab strip

Frank's ask: "the tabs need better visual separation, they just read like one
long runon sentence right now. active tab color too subtle, inactive tabs
color too subtle." Done in `3f2b4be`.

**The app is on ttk's `clam` theme now, and had to be.** On Windows ttk starts
on `vista`, where a Notebook tab is drawn by the OS from a bitmap:
`-background` is accepted and then ignored. Probed by setting a tab to bright
orange and reading the pixel back - `#f9f9f9` under vista, `#000000` under
alt/default/xpnative, `#f38020` under clam. `_init_ttk_theme` switches once
before any widget exists, because `theme_use` resets every style setting.

Two clam facts worth not rediscovering: its `Notebook.tab` element has no
`-borderwidth` (only background/bordercolor/lightcolor/darkcolor), so there is
**no gap to be had between tabs** - separation is strip-vs-chip contrast, a
per-tab border and padding, all three; and it draws the **selected tab two
pixels shorter** than its neighbours, undone by mapping `padding` for the
selected state. Raise the *horizontal* padding too and every tab to the right
jumps sideways on each switch.

The switch fixed an unreported bug: vista ignored Treeview
`-fieldbackground`, so on the dark theme the empty part of every list was a
white void under the rows. Scrollbars went dark at the same time.

`tests/drive_tabs.py` (36 checks) asserts none of this from the source - it
photographs the strip and counts runs of colour. It is the first test here
that reads the screen, and three things it had to learn are in its docstring:
do NOT make the window DPI-aware (production is not; measure the
logical-to-physical ratio instead), scan 11px below the notebook top rather
than through the labels (a scan through the middle returns 275 runs of glyph
antialiasing), and never drive a screen-reading test from a CHAIN of `after()`
callbacks - blocking to let Windows draw means `update()` re-enters the next
one. It needs the dialog recorders or it hangs on the Move tab.

## Open, and frank's call

- **The manager still has its emoji** and still pays ~0.9s for them. The sync
  tool's swap (`ICON_APP/FIND/LINK/COPY/BIN`, one block) is the template.
  Offered, not decided.
- **The Move tab asks archive.org which files are published** when you arrive
  on it — one metadata request per item per session. Offered to make it
  on-demand only; he has not answered.
- **`recycle.py` has no restore button.** The bin is an ordinary folder and
  the README says to drag files back. If he wants Restore, the index already
  records the origin folder, the item and the original mtime for exactly that.
- **`DRIVE_ACCOUNT = "frankk@4nt.org"`** is hardcoded beside `DRIVE_REL`, at
  his instruction. It is a *preference*, not a requirement — another account's
  Drive is still used if it is the only one holding the folder.
- `new_images.py` imports Pillow at module scope, ~170ms of the remaining
  1.4s startup. Deferring it into the two functions that need it is the last
  easy win; not done because `PIL_AVAILABLE` is read in three places.
