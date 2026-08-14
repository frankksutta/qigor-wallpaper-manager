---
name: portable-build-untested-handoff
description: "The 📦 Build Portable feature in build.pyw was added 2026-08-01 and verified by script, but never exercised through the real GUI — plus where its build artifacts live."
metadata: 
  node_type: memory
  type: project
  originSessionId: 81d39a3a-eefb-404c-a939-36d2369a642c
  modified: 2026-08-02T10:46:11.981Z
---

As of 2026-08-01 the portable-zip build in `build.pyw` is **implemented and
script-verified, but never clicked in the real GUI**. Uncommitted at that point:
`build.pyw` (+271/−16) and `.gitignore`.

What was already proven, by driving `App._do_build_portable` with a console stub:
- zip extracts and the `.cmd` launcher starts the GUI (window title confirmed)
- headless `--next` sets the wallpaper and honours the 90% guard
- zero Smart App Control blocks; both shipped `.exe` files are PSF-signed
- 23 MB zipped, ~9 s with the runtime cached

What was never done: opening the build tool and pressing the button, so the
threading/`_lock`/`_unlock` path and the tooltip/layout of the 5-button row are
unexercised.

Artifact locations (all outside git):
- deliverable: `QiGor_Wallpaper_Manager_Portable.zip` in the project root (gitignored)
- staging: `~/.qigor-wallpaper/portable_build/` — deliberately outside OneDrive,
  because 1443 files re-syncing per build is painful. `Clean` removes it.
- runtime cache: `~/.qigor-wallpaper/embed_cache/python-3.13.11-embed-amd64.zip`

Two constraints baked into the design, both documented in the generated
`README.txt`: the scheduled task stores the folder's absolute path, so moving the
folder silently stops the slideshow until Slideshow ▸ Start re-registers it; and
extraction paths beyond roughly 200 characters break Windows DLL loading with a
`_tkinter` ImportError.

See [[portable-distribution-decision]] for why this route was chosen and
[[smart-app-control-constraint]] for the behaviour it works around.
