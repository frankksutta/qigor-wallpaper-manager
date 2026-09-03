---
name: qigor-open-work
description: "Where the wallpaper MANAGER stands after 2026-09-03: 9 commits unpushed, 0.8.3 bumped but never built, the new Import picker, and the improvements frank was told about but has not decided on."
metadata: 
  node_type: memory
  type: project
  modified: 2026-09-03T10:50:29.061Z
  originSessionId: 219c014b-fa04-4f9c-81a9-334df20d7a05
---

State at the end of 2026-09-02, when frank shut the machine down mid-stream.
He said there were "more improvements to work on" — so expect to be picking
this up, not starting fresh.

**Nine commits are on local `master` and unpushed** (`9d210b8` …
`f6a2d5f`) as of 2026-09-03 - frank pushed everything up to `cdf36ad`
himself, and the Import picker's two commits followed. Frank asks to commit as he goes and has never asked to push; the
repo is public — offer, don't push unasked. The tree is clean.

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

**2026-09-02, later session: playlists and slideshow preview were built**
(uncommitted at the time of writing; frank has not been asked to commit).
`app/playlists.py` is new — JSON storage at `~/.qigor-wallpaper/playlists.json`
plus the `PlaylistPanel` tab. `slideshow.py` gained `resolve_pool()` and
`advance()`, which the scheduled runner and the new in-app preview both call;
state carries `source` ("folder"/"playlist") and `playlist`. The slideshow
queue now holds absolute paths rather than bare filenames, so the first
scheduled fire after this change reshuffles once — it did, live, at 11:49 on
2026-09-02. Preview cannot use the scheduler: see
[[task-scheduler-minute-floor]].

Frank asked for two changes on top, both done: the preview re-reads shuffle,
style and source at every rotation rather than snapshotting them at ▶ Preview,
and **📋 Log prints into the app console instead of opening a window** — the
last 40 lines, coloured by `_log_tag()`. That window carried the only Clear
Log button, so `_trim_log()` now holds the file to its last 400 lines once it
passes 1200, once per scheduled fire, and `_preview_log()` keeps only
started/stopped/restored/error lines so a preview session cannot bury the
rotation history in a 40-line tail. Frank was offered a Clear button back and
has not asked for one.

Four more commits followed the same afternoon, each from a one-line ask:

- **`7bd3b4e`** — a **Default store** button beside Browse… on the Slideshow
  folder row (nothing led back to `~/.qigor-wallpaper/saved_wallpapers` once
  you had browsed away), and an **Include subfolders** tick-box. The tick-box
  shares the Shuffle row on purpose: the panel had 14px of slack before it
  would show a scrollbar at the default window size. Counting the pool moved
  onto a thread with a generation counter, since it runs on every keystroke in
  the folder box.
- **`f20b2c5`** — the three Image store panes were a flat `iterdir()`, so a
  store sorted into subfolders could not feed a playlist at all. They now use
  `wallpaper.store_images()`, naming nested files `folder/name`. Playlists
  themselves ignore recursion by design — a playlist is a list of files, and
  it already plays them from any depth. `is_in_store()` replaced two copies of
  "is my parent the store", which said no one folder down and would have
  duplicated a nested image on Copy-to-store.
- **`0807be7`** — dropping a gallery URL on **Add URL** was refused.
  `resolve_drop_data()` turns away a URL whose last path segment has no dot,
  which is right for the preview's drop zone and backwards for the favourites
  buttons; `want_image=False` now says which is asking. It hid for so long
  because the shipped archive.org default has dots in its slug.
- **`172ec3d`** — **Import** on the Gallery URLs tab, in new `app/gallery.py`.
  archive.org items go through `https://archive.org/metadata/<id>` rather than
  the details page. **The thumbnail filter is the fiddly part**: an item keeps
  a `_thumb.jpg` derivative beside every image *and* one `__ia_thumb.jpg` tile
  filed as an **original** with format "Item Tile", so `source` alone does not
  sort them — see `_is_item_picture()`. Other pages are scraped for src/href.
  Anything under 25 KB is skipped as a thumbnail, which is why importing
  `lucid24.org/an/index.html` stores nothing: every image link on it is a
  `_128px` preview.

**Testing all of this lives in the scratchpad, not the repo** — seven scripts
(`test_logic`, `test_store_nested`, `test_drop_url`, `test_gallery`,
`drive_gui`, `drive_log_shuffle`, `drive_import`, plus theme/zoom and 800x600
smoke tests). They redirect `STORE_DIR`, `PLAYLIST_FILE` and `STATE_FILE` to
temp dirs and restore the favourites list, because frank uses the app while
the session runs — his slideshow was switched to playlist "a" mid-session and
the tests had to prove they had not touched it. Ask before rewriting them into
the repo; frank has not asked for a test suite.

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

**All three scrollbars render light grey on the dark theme.** The earlier
conclusion here — that `ttk.Scrollbar` under `clam` came out beige (#dcdad5)
and could not be coloured — **was wrong**, and the sync tool disproved it on
2026-09-03. That beige is simply clam's unset default. It takes a colour when
asked by the right style name: `Vertical.TScrollbar` / `Horizontal.TScrollbar`,
configuring `background` (the thumb), `troughcolor`, `bordercolor`,
`arrowcolor`, `lightcolor` and `darkcolor` — `TScrollbar` alone does not
reach the orientation-specific style. Verified by pixel: thumb, trough and
arrows all came back exactly as set.

`tk.Scrollbar` really is undyeable — Windows draws it — so the fix is to move
the three to `ttk.Scrollbar` along with `ttk.Style().theme_use("clam")`. That
switch drags every other ttk widget onto clam and each then needs a colour
stated in both themes; the sync tool's `_init_ttk_theme` and `apply_theme` are
the worked example, and its README carries the reasoning. It also fixes the
same white-void-under-the-rows Treeview bug this app will have. Offered, not
done — it is a whole-app look change.

**The wallpaper SYNC tool is a different app in the same folder** and has its
own handoff: [[qigor-sync-open-work]]. Four commits there on 2026-09-02 (five
tabs now, a recycle bin, and startup cut from 5.3s to 1.4s). It is its own git
repository with no remote, ignored by this one, so none of its commits are
part of the unpushed pile above.

Two things from that work that bear on THIS app:

- **`2f9e164` fixed its Windows paths.** The five image sources were built
  from `Path.home() / "AppData/..."` plus one literal `C:/Windows`;
  `app/constants.py` now resolves `APPDATA` / `LOCALAPPDATA` / `WINDIR` from
  the environment, names the four Windows folders once each, and
  `wallpaper.py` imports them instead of keeping a second copy of two of the
  spellings. The installer was already doing this properly. No Google Drive
  code exists in this app at all - that was checked, twice.
- **The emoji still cost this app ~0.9s of startup**, and removing one does
  not help: whichever glyph renders first pays the font load. The sync tool
  went emoji-free and started in a quarter of the time; the numbers and the
  cheap replacement glyphs are in [[drive-listing-costs-half-a-second]].
  **Offer that swap here; do not just do it.**

**frank exercises new features live while a session runs** - watch for his
config and the real files changing underneath you.

**2026-09-03: the Import picker** (`c4aba8b`, one commit, still 0.8.3 and
still unbuilt — the release pile is now 9 commits). Frank's ask, in his
words: Import "just downloads everything, including things you already have".
It now checks the store first and opens `app/galleryimport.py` — a filtered,
ticked list with All / None / Invert and a preview of the highlighted row.
`gallery.py` returns items (url, name, size, thumb, have) rather than URLs;
`find_images()` is kept as a wrapper. Two things worth not rediscovering: an
archive.org derivative names its source in `original` (a **list** for some,
which are not one picture's thumbnail), which is what makes the preview 8 KB
instead of 2 MB; and the app's `_apply_theme_recursive` never reaches a
Toplevel built after it has run, so a dialog must colour every widget itself
or its LabelFrames are light-grey blocks on the dark theme.

**One cosmetic thing to ask frank, unresolved:** the `⬇` (U+2B07) on the new
Import button renders as a **box in PrintWindow captures** of the dialog,
while every isolated render of the same font object, widget class, Toplevel
and post-creation `config(text=…)` draws the arrow correctly. The gallery
tab's existing Import button uses the same codepoint, so if it is a box on
screen both need swapping — `↓` captured cleanly everywhere. It was left as
it is rather than changed on a capture artifact.

Testing this GUI: [[gui-overhaul-untested-handoff]]. Startup cost:
[[tk-startup-cost-emoji]]. Distribution: [[installer-release-state]].
