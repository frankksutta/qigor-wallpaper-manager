---
name: installer-release-state
description: "QiGor v0.8.0 ships as an installable zip with a GitHub updater; the whole cycle is tested, but no release has been uploaded yet so updates stay dead until version.json is published."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2a67fce0-3b0b-4a79-9e50-02c6aa86dfbf
  modified: 2026-09-02T00:35:04.452Z
---

As of 2026-09-01 QiGor is a real installable app, not just a portable folder.
`build.pyw` ▸ 📦 Build Installer produces four release assets in the project
root: `QiGor_Wallpaper_Manager_Setup.zip` (~24 MB), `SHA256.txt`,
`version.json`, and `QiGor-Setup.cmd` (a one-double-click web installer that
downloads, verifies and installs, so a recipient never handles the zip).

**All four must go up, zip first.** The in-app updater polls
`releases/latest/download/version.json`, not the GitHub API — that file carries
the build number, SHA-256, size and notes — and `QiGor-Setup.cmd` verifies its
download against `SHA256.txt`. Uploading the zip without `version.json` leaves
every installed copy believing it is current, forever. 🐙 Upload Release sends
all four in order, prunes the obsolete `.exe`/portable-zip assets, and rewrites
the release description from the manifest — so the published version, checksum
and install instructions are generated, never hand-edited. Don't edit the
release body on github.com; change `release_body()` in `build.pyw` or
`RELEASE_NOTES.md` and re-upload, or the next upload silently reverts it.

**Published 2026-09-01: build 0.8.1**, verified by downloading the live
`QiGor-Setup.cmd` and running it end to end. The old PyInstaller `.exe` asset is
deleted from the release.

Verified end to end on 2026-09-01, all from the built zip: silent install →
launch → update handoff → relaunch → uninstall → registry, shortcut, and folder
all gone. The interactive installer, uninstaller, and update windows were
constructed and rendered but never clicked by hand.

Two things worth remembering because they are not obvious from the code:

- **An update is a reinstall.** The staged copy's interpreter waits on the old
  PID and copies over the install root. Nothing can overwrite the CPython DLLs
  it is running from, so this is the only shape that survives a bundled-Python
  bump — and it means one code path, `installer.core.install()`, for both first
  install and update.
- **Paths must stay short.** A test install under a ~250-character path died
  with `STATUS_NAME_TOO_LONG` (0xC0000106) before showing a window, and the
  shell silently truncated the shortcut's icon path at MAX_PATH. The real
  install root, `%LOCALAPPDATA%\Programs\QiGorWallpaperManager`, is ~85 chars
  and fine; loose extraction to a deep folder is not.

Supersedes the portable-zip handoff. Rationale in
[[portable-distribution-decision]], the mechanism being dodged in
[[smart-app-control-constraint]], licensing still open in
[[repo-public-license-pending]].
