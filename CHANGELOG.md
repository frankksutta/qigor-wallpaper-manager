# Changelog

Newest first. Each release gets a `## <build>` heading matching `APP_BUILD` in
`app/constants.py`; the build tool copies that section into `version.json`, and
it is what the app's update dialog shows. Write a new section before building —
the build warns if there isn't one for the current version.

## 0.8.5 — 2026-11-04

The wallpaper reminder works again.

- **Fixed:** the scheduled reminder and **Test Toast Now** showed nothing in any copy installed from 0.8.1 on. The library that draws the notification was never put into QiGor's own Python, so each reminder failed quietly; the Reminder tab's log said so. It is bundled now, and a reminder you already scheduled starts working after this update without being set up again.

## 0.8.4 — 2026-09-03

The slideshow stops being one folder at a time.

- **Playlists.** Name a set of images from your store — one for work, one for the weekend — and point the slideshow at that instead of a whole folder. The new Playlists tab has your store on one side and the playlist on the other, with a thumbnail of whatever you click. Changes save as you make them, and a playlist the slideshow is already using picks them up at its next image.
- **Quick preview.** See how a folder or playlist looks without waiting out the interval: the same rotation, 5 to 100 seconds apart, running while QiGor is open. It leaves the scheduled slideshow's place in its queue exactly where it was, and can put your wallpaper back when it stops.
- **Subfolders, and they count by default.** A slideshow folder now includes everything below it, however deep, so a collection sorted into themes — or a store with a folder per imported gallery — plays as one. Untick **Include subfolders** for the old behaviour; if you do, and the folder itself holds no images, QiGor says how many are in its subfolders rather than calling the folder empty. The image store understands its own subfolders too, and a **Default store** button brings the folder box back home after you have browsed elsewhere.
- **Import a gallery.** Select a gallery URL and press Import: QiGor reads the page, works out which of its images you do not already have, and shows you that list with a picture of whichever line you click. Tick what you want — All, None and Invert are there for a long gallery — and the ones already in your store stay behind a tick-box rather than being downloaded again. The folder is named after the gallery and yours to change. Thumbnails are left behind and Esc stops it. Archive.org galleries are read from their file list rather than scraped, so nothing extra comes along, and their own thumbnails make the preview instant.
- **The slideshow log prints into the log console** instead of opening a window over it, coloured by what each line says. It keeps itself trimmed, so there is nothing left to clear.
- **Fixed:** dropping a gallery link on *Add URL* said it could not resolve the item and added nothing. It now saves the page, and names the favourite after the gallery rather than after the website.

## 0.8.3 — 2026-09-02

First cut of playlists, quick preview, subfolders and gallery Import, all reworked in 0.8.4 (subfolders on by default; Import gained its picker). See 0.8.4.

## 0.8.2 — 2026-09-01

- `QiGor-Setup.cmd` checks the published version first and transfers about a kilobyte — not the whole installer — if you already have the latest build.
- Uninstall from Help ▸ Uninstall inside the app, or with `winget uninstall`, as well as from Settings ▸ Apps.
- Every install and uninstall is written to `%USERPROFILE%\.qigor-wallpaper\install_log.txt`, so a window that closes too fast is no longer the end of the story.

## 0.8.1 — 2026-09-01

QiGor is now a proper installed app rather than a folder you keep somewhere.

- Installs to your user account, with a Start Menu entry, an optional desktop shortcut, and an Uninstall entry in Settings ▸ Apps. No administrator password.
- `QiGor-Setup.cmd` downloads, verifies and installs in one double-click, so there is no zip to unpack or keep track of.
- Built-in updates: QiGor checks once a day, shows what changed, and verifies the download against a published checksum before replacing anything.
- Upgrading from an older copy takes over its slideshow and reminder schedules, keeping your intervals, and tells you where the old folder is.
- Uninstalling asks a running copy to close first, so it can never half-remove itself.
- No unsigned `.exe` anywhere, so Smart App Control has nothing to block. Everything that runs is signed by the Python Software Foundation or by Microsoft.

## Before 0.8.1

Shipped as a PyInstaller `.exe`; no release notes were kept. See `git log`.
