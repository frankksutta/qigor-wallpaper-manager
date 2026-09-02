# QiGor Wallpaper Manager

Change your Windows wallpaper without digging four clicks deep into Settings.
Drag an image in, drop a URL from your browser, or browse your files — the
wallpaper changes immediately, and every image you set is saved to a local store
and kept in a visual history you can go back through in one click.

It also runs a better slideshow than the built-in one. Windows Slideshow is
locked to a single folder, has no shuffle memory (it can show the same image
twice in a row), and stops the moment you touch any wallpaper setting. QiGor
shuffles your whole collection and guarantees every image plays once before any
repeats, runs through Task Scheduler so nothing sits in memory, and keeps working
across reboots.

Windows 11, or Windows 10 version 1803 and later. No Python installation needed —
one is bundled.

---

## Install

**1. Download [`QiGor-Setup.cmd`](https://github.com/frankksutta/qigor-wallpaper-manager/releases/latest/download/QiGor-Setup.cmd)** from the
[latest release](https://github.com/frankksutta/qigor-wallpaper-manager/releases/latest).

Your browser will probably warn you about it, because it is a script. Choose
**Keep** / **Keep anyway**.

**2. Unblock it.** Windows marks everything downloaded from the internet as
blocked. Right-click `QiGor-Setup.cmd` → **Properties** → at the bottom of the
General tab, tick the **Unblock** checkbox → **OK**.

> If there is no Unblock checkbox, the file is not blocked and you can skip this.

**3. Double-click `QiGor-Setup.cmd`.** A console window opens and does the rest:
downloads the current release, checks it against the published SHA-256, unpacks
it, and opens the installer.

It reads the ~1 KB version manifest before the 24 MB installer, so if you already
have the latest build it tells you and downloads nothing further — worth knowing
on a metered connection. Run it as `QiGor-Setup.cmd /force` to reinstall anyway.

If you skipped step 2 you will instead get **"Windows protected your PC"**.
Click **More info → Run anyway**, or go back and unblock the file.

**4. Click Install.** It installs for your user account only, so Windows never
asks for an administrator password. You get a Start Menu entry, an optional
desktop shortcut, and an entry in Settings ▸ Apps. Nothing is left over — the
downloaded files are deleted when setup finishes.

Installs to `%LOCALAPPDATA%\Programs\QiGorWallpaperManager`. Your settings and
saved wallpapers live in `%USERPROFILE%\.qigor-wallpaper`.

### Coming from an older version?

Just install. The installer takes over the slideshow and reminder schedules from
whatever copy was running them, keeping your intervals, and tells you where the
old folder is so you can delete it.

### Doing it by hand instead

Download `QiGor_Wallpaper_Manager_Setup.zip`, right-click it → **Extract All**,
and run `Install.cmd` from the extracted folder. Extract somewhere short like
`C:\Tools\` — past roughly 200 characters Windows fails to load the bundled DLLs.
Verify the download against `SHA256.txt` if you like:

```
certutil -hashfile QiGor_Wallpaper_Manager_Setup.zip SHA256
```

You can also just run `QiGor Wallpaper Manager.cmd` from the extracted folder
without installing. If you do, don't move the folder afterwards — the scheduled
task records its full path.

---

## Updates

The app checks GitHub once a day and offers the new version when there is one.
**Help ▸ Check for Updates** does it on demand, and the automatic check can be
turned off in that same window. Downloads are verified against their published
checksum before anything is replaced.

## Uninstall

Any of these — they all run the same uninstaller:

- **Settings ▸ Apps ▸ Installed apps ▸ QiGor Wallpaper Manager ▸ Uninstall**
- **Help ▸ Uninstall QiGor…** inside the app
- `Uninstall.cmd` in the install folder
- `winget uninstall "QiGor Wallpaper Manager"`

It stops the slideshow and reminder tasks first, and asks a running copy to close
before removing anything, so it can never half-delete itself. Your settings and
saved wallpapers are kept unless you tick the box to remove them.

Every install and uninstall is appended to
`%USERPROFILE%\.qigor-wallpaper\install_log.txt`, so you can always read what
happened even if a window closed before you finished reading it.

---

## Why a zip and a script, and not a Setup.exe

Because an unsigned `.exe` does not reliably run on Windows 11 any more, and
there is no way to fix that from inside the build.

Smart App Control gates PE images — `.exe`, `.dll`, `.sys`, `.msi` — and allows
one only if it is signed by a publisher Windows already trusts or if Microsoft's
reputation service returns a positive verdict for that exact file hash. An
unsigned build has neither. A previous release of this app ran fine for three
weeks and was then blocked 168 times in 27 hours without anything about it
changing, because the verdict is a cloud decision keyed to the file hash — so it
is non-deterministic and resets on every rebuild. Unlike SmartScreen, Smart App
Control gives the user no "run anyway".

So this project ships **no executable of its own at all**. The release is the
official python.org embeddable CPython distribution plus plain `.py` source.
Every program that actually runs — `pythonw.exe`, the Python DLLs, the Tcl/Tk
DLLs — is signed by the Python Software Foundation, and the installer, updater
and uninstaller are ordinary readable Python. The launchers are `.cmd` files, run
by a Microsoft-signed `cmd.exe`, and `QiGor-Setup.cmd` uses only `curl`, `tar`
and `certutil` from System32.

The one step this costs you is unblocking the downloaded script — which, unlike
Smart App Control, you are allowed to do.

The retired PyInstaller build and the full account of what went wrong are kept in
[`obsolete_exe_build/`](obsolete_exe_build/README.md).

---

## Building from source

Needs a standard python.org install of the same CPython version you want to ship,
with `tkinter` (the embeddable distribution has none, so it is grafted in from
the full install).

```
python build.pyw
```

Click **📦 Build Installer**. It downloads and caches the embeddable runtime,
grafts in tkinter, pip-installs the dependencies, and writes four release assets
to the project root:

| file | what it is |
|---|---|
| `QiGor_Wallpaper_Manager_Setup.zip` | the app, runtime and installer |
| `SHA256.txt` | digest of the zip, checked by `QiGor-Setup.cmd` |
| `version.json` | build number, checksum, size and notes — what the in-app updater reads |
| `QiGor-Setup.cmd` | the one-click web installer |

**🐙 Upload Release** publishes all four, zip first. All four must go up together:
without `version.json` no installed copy ever learns that a new build exists.

The version comes from `APP_BUILD` in `app/constants.py` — the single source of
truth. Bump it before building.

Release notes come from `RELEASE_NOTES.md` if present, otherwise from the last
few commit subjects.

---

## Licence

Not chosen yet, so default copyright applies for now. If you want to reuse any of
this, open an issue and ask.
