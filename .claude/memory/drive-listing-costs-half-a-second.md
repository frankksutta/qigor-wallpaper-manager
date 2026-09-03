---
name: drive-listing-costs-half-a-second
description: "Listing any folder on the Google Drive mount costs ~0.5s of latency, and the first emoji in a Tk process ~0.9s — the two things that make these apps slow to start."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6bdc9b61-d049-49ba-9611-50846bf90165
  modified: 2026-09-03T03:33:46.903Z
---

Measured 2026-09-02 while chasing "why does the app take forever to start"
(the wallpaper **sync** tool: 5.3 seconds to a drawn window, fixed in
`4a53b79`).

**Listing a folder on `I:\` costs about half a second**, however few files are
in it. It is latency, not work — counting 67 files in a pack and counting 2
cost the same. Startup was paying it five times on the main thread before the
window appeared (`_refresh_items_view`, `_refresh_reloc_values` twice,
`_refresh_dest_values`, one `_folder_state`). Anything that wants a file count
from a Drive folder must therefore be cached (keyed on the folder's mtime) and
computed on a thread, and no tab should read its folder until you arrive on it.

**The first true emoji (U+1F000+) rendered in a Tk process costs ~0.9s**,
while Windows loads an emoji-capable fallback font — main thread, before
anything can be drawn, unthreadable. In fresh processes at Segoe UI 12 bold:

| what | cost |
|---|---|
| no glyph | 11 ms |
| **the first emoji — any of them** | **850–930 ms** |
| a second, different emoji | 40–56 ms |
| arrows (↓ ↗ ↔ ↻ ⇄ ⇅) | 20–35 ms |
| geometric / APL (▣ ⌕ ⌫ ⧉ ✕ ⟲) | 4–26 ms |
| ♺ U+267A (needs the same fallback) | 425 ms |

This is the same trap as [[tk-startup-cost-emoji]], which measured 716ms for
the main app — but that note's advice ("drop them from the toolbar") is not
enough on its own: **moving or removing one emoji only hands the bill to the
next one**, because the cost is the font load, not the glyph. The whole process
has to be emoji-free. The sync tool now is, with `ICON_APP/FIND/LINK/COPY/BIN`
in one block and a test asserting nothing above U+1F000 creeps back in
(escapes included — it caught one in the comment explaining the rule).

**The wallpaper manager still has its emoji**, and therefore still pays ~0.9s;
frank has now accepted the trade for the sync tool, so the same swap there is
worth offering rather than assuming.

Measuring: wrap methods with a timer and print worst-first, then wrap widget
CLASSES (`tk.Label.__init__` and friends) to find which widget — 17 Labels at
76ms average is what pointed at the one that was 1229ms. And measure a glyph
in a **fresh process**: an in-process probe after the app has built its toolbar
reports 14ms and hides the whole effect. That mistake cost a round trip here.
