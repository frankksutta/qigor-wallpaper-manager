---
name: gui-overhaul-untested-handoff
description: "The 2026-09-01 GUI overhaul (whole-app zoom, tabs, theming) is committed and pushed but never clicked by hand — and its source build number collides with the already-published 0.8.2."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2a67fce0-3b0b-4a79-9e50-02c6aa86dfbf
  modified: 2026-09-02T05:36:59.659Z
---

Four commits on 2026-09-01 after the 0.8.2 release — `27b463f` whole-app zoom,
`540f6f2` Slideshow/Reminder as tabs, `bb1fe29` contrast + Lock Screen tab,
`4b02a63` pane headings + lock preview + tab ✔ markers. All pushed to
`origin/master`.

**The trap: `APP_BUILD` is still `0.8.2`, and 0.8.2 is already published and
installed.** Source 0.8.2 and released 0.8.2 are different programs. Bump to
0.8.3 before the next 📦 Build Installer, or the updater will not offer it and
the two builds become impossible to tell apart. The copy installed at
`%LOCALAPPDATA%\Programs\QiGorWallpaperManager` is the *old* 0.8.2 without any
of the GUI work — run from source to see the new UI.

**Verified only programmatically.** Widget construction, tab order and
selection, theme toggle in both directions, zoom across 102 widgets, dialog
construction at 160%, and window screenshots via `PrintWindow`. Nothing was
ever clicked. The interactive paths that remain unproven: every button inside
the Slideshow and Reminder tabs (they were converted from modal Toplevels to
Frames, so `_finish()` replaced `self.destroy()` throughout), the Menubutton
drop-downs, and the combobox popup lists.

Known open issue, deliberately left: **dim hint text inside the Slideshow and
Reminder tabs flattens to normal brightness after a theme toggle**, until
restart. `_apply_theme_recursive` paints every Label with the plain foreground;
about 7 labels own a semantic colour and would need tracking individually. The
same root cause as the LabelFrame heading bug fixed in `4b02a63`, but that one
was a one-line fix and this is not.

Screenshotting the app: use `PrintWindow` with `PW_RENDERFULLCONTENT` on the
app's own HWND. `ImageGrab` of screen coordinates is wrong here — a background
process cannot pull its window to the front on Windows, so the capture silently
grabs whatever else is on screen.

Distribution state in [[installer-release-state]].
