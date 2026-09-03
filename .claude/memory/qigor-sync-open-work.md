---
name: qigor-sync-open-work
description: "Handoff for the wallpaper SYNC tool after 2026-09-02: five tabs, four commits that day, what is open, and the three hazards to know before touching it."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6bdc9b61-d049-49ba-9611-50846bf90165
  modified: 2026-09-03T04:13:32.038Z
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
