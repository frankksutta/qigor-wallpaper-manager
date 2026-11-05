#!/usr/bin/env pythonw
# -*- coding: utf-8 -*-
"""
build.pyw  —  QiGor Wallpaper Manager
Build tool: installer zip, GitHub release upload, git source sync.

Place this file in the project root (same folder as qigor_wallpaper_manager.pyw).
Expected layout:
  qigor_wallpaper/
    build.pyw                       ← this file
    qigor_wallpaper_manager.pyw     ← entry point
    app/                            ← application package
    installer/                      ← install / uninstall / shortcuts
    assets/                         ← images and icon

There is deliberately no EXE build here any more. A frozen single-file EXE is an
unsigned PE image, which is exactly what Smart App Control gates, and its verdict
is a cloud reputation decision keyed to the file hash — so it can flip without
warning and there is no user override. The old PyInstaller tool is kept for
reference in obsolete_exe_build/, whose README has the full account.

The release ships instead as a zip of the python.org embeddable CPython plus
plain source: every executable image in it is already signed by the Python
Software Foundation.

GitHub release structure:
  frankksutta/qigor-wallpaper-manager
    ├── Source code (git push)
    └── Releases
          └── latest tag
                ├── QiGor_Wallpaper_Manager_Setup.zip   ← the download
                └── version.json                        ← what the updater reads
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
import tkinter as tk

APP_NAME    = "QiGor Wallpaper Manager — Build Tool"
APP_VERSION = "1.0"

SCRIPT_DIR   = Path(__file__).parent.resolve()
ENTRY_PY     = SCRIPT_DIR / "qigor_wallpaper_manager.pyw"
ICON_FILE    = SCRIPT_DIR / "assets" / "qigor_wallpaper_manager.ico"

# ── Installer build ───────────────────────────────────────────────────────────
# Ships embeddable CPython + plain source. Every executable image in the folder
# is Python Software Foundation signed, so Smart App Control has nothing to
# gate — unlike an unsigned PyInstaller EXE, whose fate depends on a cloud
# reputation verdict that can flip per build. See obsolete_exe_build/README.md.
SETUP_NAME     = "QiGor Wallpaper Manager"      # top-level folder inside the zip
# Staging lives outside the project: it is ~1,500 files, and this project sits
# in a OneDrive folder that would otherwise re-sync all of them every build.
SETUP_STAGE    = Path.home() / ".qigor-wallpaper" / "setup_build"
SETUP_ZIP      = SCRIPT_DIR / "QiGor_Wallpaper_Manager_Setup.zip"
MANIFEST_JSON  = SCRIPT_DIR / "version.json"    # uploaded beside the zip
SHA_TXT        = SCRIPT_DIR / "SHA256.txt"      # plain digest, for the .cmd
WEB_SETUP_CMD  = SCRIPT_DIR / "QiGor-Setup.cmd"  # one-click download+install
# Upload order matters. The zip goes first because version.json and SHA256.txt
# both describe it, and QiGor-Setup.cmd downloads it — publishing any of those
# ahead of the zip advertises a file that briefly 404s.
RELEASE_ASSETS = (SETUP_ZIP, SHA_TXT, MANIFEST_JSON, WEB_SETUP_CMD)
# Assets from the retired distribution models, pruned on every upload. Named
# explicitly rather than "anything not in RELEASE_ASSETS": deleting a published
# download because the build tool did not recognise it is not a decision this
# should ever make on its own.
OBSOLETE_ASSETS = ("QiGor_Wallpaper_Manager.exe",
                   "QiGor_Wallpaper_Manager_Portable.zip")
EMBED_CACHE    = Path.home() / ".qigor-wallpaper" / "embed_cache"
SETUP_DEPS     = ["pillow", "tkinterdnd2", "winotify"]  # winotify: the Reminder toast
# Copied into the zip verbatim. installer/ is what makes the zip installable;
# without it the folder still runs, it just cannot install itself.
SETUP_SRC_DIRS = ("app", "installer", "assets")
# Must match installer.paths.APP_ID — QiGor-Setup.cmd reads the installed
# version.json from this folder to decide whether a download is needed.
INSTALL_DIR_NAME = "QiGorWallpaperManager"

# Legacy PyInstaller leavings — still cleaned up so an old checkout tidies itself.
LEGACY_ARTIFACTS = (SCRIPT_DIR / "build",
                    SCRIPT_DIR / "dist",
                    SCRIPT_DIR / "qigor_wallpaper_manager.spec",
                    Path.home() / ".qigor-wallpaper" / "portable_build")

GITHUB_USER  = "frankksutta"
GITHUB_REPO  = "qigor-wallpaper-manager"
GITHUB_API   = "https://api.github.com"
RELEASE_TAG  = "latest"
RELEASE_NAME = "QiGor Wallpaper Manager — Latest"


def read_app_versions() -> tuple:
    """
    Parse APP_VERSION and APP_BUILD from app/constants.py so the release
    manifest always matches the source — no hardcoded duplicates here.
    Returns (version_str, build_str), e.g. ("0.8", "0.8.0").
    """
    ver = build = None
    try:
        text = (SCRIPT_DIR / "app" / "constants.py").read_text(encoding="utf-8")
        m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', text, re.M)
        if m:
            ver = m.group(1)
        m = re.search(r'^APP_BUILD\s*=\s*"([^"]+)"', text, re.M)
        if m:
            build = m.group(1)
    except Exception:
        pass
    return ver or "0.0", build or ver or "0.0"


def release_body(man: dict) -> str:
    """
    The text of the GitHub release page, built from the manifest.

    Generated rather than edited by hand so it cannot drift: the version, the
    checksum and the install route on the page are always the ones belonging to
    the assets that were just uploaded.

    The unblock step is the honest cost of shipping no executable of our own, so
    it is step 2 rather than a footnote — a user who hits "Windows protected your
    PC" with no warning assumes the download is broken and gives up.
    """
    size_mb = (man.get("size") or 0) / 1e6
    return (
        "**QiGor Wallpaper Manager {build}** — Windows 11, or Windows 10 "
        "version 1803 and later. No Python installation needed.\n"
        "\n"
        "## Install\n"
        "\n"
        "**1. Download `{cmd}`** from Assets below. Your browser will warn you "
        "about it because it is a script — choose **Keep**.\n"
        "\n"
        "**2. Unblock it.** Windows blocks anything downloaded from the "
        "internet. Right-click `{cmd}` → **Properties** → tick the **Unblock** "
        "box at the bottom of the General tab → **OK**.\n"
        "\n"
        "**3. Double-click `{cmd}`.** It downloads this release, checks it "
        "against the published SHA-256, unpacks it, and opens the installer.\n"
        "\n"
        "> Skipped step 2? You will get **\"Windows protected your PC\"** "
        "instead. Click **More info → Run anyway**, or go back and unblock the "
        "file.\n"
        "\n"
        "**4. Click Install.** It installs for your user account only, so "
        "Windows never asks for an administrator password. You get a Start Menu "
        "entry, an optional desktop shortcut, and an Uninstall entry in "
        "Settings ▸ Apps. The downloaded files are deleted when setup "
        "finishes.\n"
        "\n"
        "Already running an older copy? Just install. It takes over the "
        "slideshow and reminder schedules, keeping your intervals, and tells "
        "you where the old folder is so you can delete it.\n"
        "\n"
        "<details>\n"
        "<summary>Prefer to unpack it yourself</summary>\n"
        "\n"
        "Download `{zipname}`, right-click it → **Extract All**, and run "
        "`Install.cmd` from the extracted folder. Extract somewhere short like "
        "`C:\\Tools\\` — past roughly 200 characters Windows fails to load the "
        "bundled DLLs.\n"
        "\n"
        "Check it against `SHA256.txt` first if you like:\n"
        "\n"
        "```\n"
        "certutil -hashfile {zipname} SHA256\n"
        "```\n"
        "</details>\n"
        "\n"
        "## What's new\n"
        "\n"
        "{notes}\n"
        "\n"
        "## Why a script and not a Setup.exe\n"
        "\n"
        "Smart App Control gates every `.exe`, and allows one only if it is "
        "signed by a publisher Windows already trusts or if Microsoft's "
        "reputation service returns a positive verdict for that exact file "
        "hash. An unsigned build has neither, and it gives you no \"run "
        "anyway\". An earlier release of this app ran fine for three weeks and "
        "was then blocked 168 times in 27 hours without anything about it "
        "changing.\n"
        "\n"
        "So this ships **no executable of its own at all** — it is the official "
        "python.org embeddable CPython plus plain readable Python source. "
        "Everything that actually runs is signed by the Python Software "
        "Foundation or by Microsoft. The one step it costs you is unblocking a "
        "downloaded script, which — unlike Smart App Control — you are allowed "
        "to do.\n"
        "\n"
        "## Files\n"
        "\n"
        "| file | what it is |\n"
        "| --- | --- |\n"
        "| `{cmd}` | start here — downloads, verifies and installs |\n"
        "| `{zipname}` | the app itself, {size:.1f} MB |\n"
        "| `SHA256.txt` | checksum of the zip |\n"
        "| `version.json` | what the in-app updater reads |\n"
        "\n"
        "---\n"
        "Build {build} · bundled Python {runtime} · sha256 `{sha}`\n"
    ).format(build=man.get("build", "?"),
             runtime=man.get("runtime", "?"),
             sha=man.get("sha256", ""),
             size=size_mb,
             cmd=WEB_SETUP_CMD.name,
             zipname=SETUP_ZIP.name,
             notes=(man.get("notes") or "").strip() or "No notes were published.")


def web_setup_cmd(size_mb: float = 24.0) -> str:
    """
    The text of QiGor-Setup.cmd — a standalone one-click web installer.

    It is a batch file rather than anything compiled for the same reason the
    release is a zip: a batch file is not a PE image, so Smart App Control has
    nothing to gate, and everything it invokes (cmd, curl, tar, certutil) is a
    Microsoft-signed binary already in System32. curl and tar have shipped with
    Windows since 10 version 1803, so nothing has to be installed first.

    It never leaves a zip lying around for the user to manage: download,
    verify, unpack and install all happen under %TEMP%, which is wiped on the
    way out. And it reads the ~1 KB manifest before the 24 MB zip, so someone
    already on the current build — or on a metered connection — is told so
    without paying for the download to find out.
    """
    return (
        "@echo off\r\n"
        "setlocal\r\n"
        "title QiGor Wallpaper Manager - Setup\r\n"
        "\r\n"
        'set "BASE=https://github.com/{user}/{repo}/releases/latest/download"\r\n'
        'set "ZIPNAME={zipname}"\r\n'
        'set "WORK=%TEMP%\\qigor-setup"\r\n'
        'set "PAYLOAD=%WORK%\\x\\{payload}"\r\n'
        'set "INSTALLED=%LOCALAPPDATA%\\Programs\\{appid}\\version.json"\r\n'
        "\r\n"
        ":: Full paths, never a bare name on PATH. Git for Windows puts its own\r\n"
        ":: GNU tar ahead of System32 on PATH, and GNU tar cannot read a zip at\r\n"
        ":: all - it reports \"this does not look like a tar archive\", or treats\r\n"
        ":: C:\\... as a remote host. Pinning System32 also guarantees these are\r\n"
        ":: the Microsoft-signed binaries, which is the point of the exercise.\r\n"
        'set "CURL=%SystemRoot%\\System32\\curl.exe"\r\n'
        'set "TAR=%SystemRoot%\\System32\\tar.exe"\r\n'
        'set "HASH=%SystemRoot%\\System32\\certutil.exe"\r\n'
        "\r\n"
        "echo(\r\n"
        "echo   QiGor Wallpaper Manager\r\n"
        "echo   -----------------------\r\n"
        "echo   Installs the latest release for your user account.\r\n"
        "echo   No administrator password is needed.\r\n"
        "echo(\r\n"
        "\r\n"
        'if not exist "%CURL%" goto :nohelper\r\n'
        'if not exist "%TAR%" goto :nohelper\r\n'
        'if not exist "%HASH%" goto :nohelper\r\n'
        "\r\n"
        'if exist "%WORK%" rmdir /s /q "%WORK%"\r\n'
        'mkdir "%WORK%\\x" >nul 2>&1\r\n'
        'if not exist "%WORK%\\x" goto :fail\r\n'
        "\r\n"
        ":: The manifest is about a kilobyte. Reading it before the zip means a\r\n"
        ":: machine that is already current never pays for a {size:.0f} MB download\r\n"
        ":: just to be told it had the file already.\r\n"
        "echo   Checking the latest version...\r\n"
        '"%CURL%" -L --fail --silent --show-error -o "%WORK%\\version.json" "%BASE%/version.json"\r\n'
        "if errorlevel 1 goto :dlfail\r\n"
        'call :readbuild "%WORK%\\version.json" NEWVER\r\n'
        "if not defined NEWVER goto :fail\r\n"
        'set "HAVE="\r\n'
        'if exist "%INSTALLED%" call :readbuild "%INSTALLED%" HAVE\r\n'
        "\r\n"
        'if /i "%~1"=="/force" goto :download\r\n'
        "if not defined HAVE (\r\n"
        "    echo   Latest version is %NEWVER%. Nothing is installed yet.\r\n"
        "    goto :download\r\n"
        ")\r\n"
        'if not "%HAVE%"=="%NEWVER%" (\r\n'
        "    echo   Installed %HAVE%  -  latest is %NEWVER%. Updating.\r\n"
        "    goto :download\r\n"
        ")\r\n"
        "echo(\r\n"
        "echo   You already have version %HAVE%, and that is the latest one.\r\n"
        "echo   Nothing needs downloading.\r\n"
        "echo(\r\n"
        'set "ANS=n"\r\n'
        'set /p "ANS=  Reinstall it anyway? That downloads {size:.0f} MB. [y/N] "\r\n'
        'if /i not "%ANS%"=="y" goto :uptodate\r\n'
        "echo(\r\n"
        "\r\n"
        ":download\r\n"
        "echo   Downloading the installer...\r\n"
        '"%CURL%" -L --fail --progress-bar -o "%WORK%\\%ZIPNAME%" "%BASE%/%ZIPNAME%"\r\n'
        "if errorlevel 1 goto :dlfail\r\n"
        "echo   Downloading the checksum...\r\n"
        '"%CURL%" -L --fail --silent --show-error -o "%WORK%\\SHA256.txt" "%BASE%/SHA256.txt"\r\n'
        "if errorlevel 1 goto :dlfail\r\n"
        "\r\n"
        'set "WANT="\r\n'
        'for /f "usebackq tokens=1" %%h in ("%WORK%\\SHA256.txt") do '
        'if not defined WANT set "WANT=%%h"\r\n'
        'set "GOT="\r\n'
        # certutil's output goes to a file rather than straight into for /f:
        # cmd cannot run a command that *starts* with a quoted path inside
        # for /f, and it fails there with a bare "The filename, directory name,
        # or volume label syntax is incorrect".
        '"%HASH%" -hashfile "%WORK%\\%ZIPNAME%" SHA256 > "%WORK%\\hash.txt" 2>&1\r\n'
        # The digest is on the second line, spaced on older Windows builds and
        # unspaced on newer ones; stripping spaces covers both.
        'for /f "usebackq skip=1 delims=" %%h in ("%WORK%\\hash.txt") do '
        'if not defined GOT set "GOT=%%h"\r\n'
        "if not defined GOT goto :fail\r\n"
        'set "GOT=%GOT: =%"\r\n'
        'if /i not "%GOT%"=="%WANT%" goto :badhash\r\n'
        "echo   Checksum verified.\r\n"
        "\r\n"
        "echo   Extracting...\r\n"
        '"%TAR%" -xf "%WORK%\\%ZIPNAME%" -C "%WORK%\\x"\r\n'
        "if errorlevel 1 goto :fail\r\n"
        'if not exist "%PAYLOAD%\\runtime\\pythonw.exe" goto :fail\r\n'
        "\r\n"
        "echo   Starting the installer...\r\n"
        # Called directly, not via start, so cmd waits for the window to close
        # before wiping the folder it is running from.
        '"%PAYLOAD%\\runtime\\pythonw.exe" "%PAYLOAD%\\installer\\install.py"\r\n'
        'set "RC=%errorlevel%"\r\n'
        'rmdir /s /q "%WORK%" >nul 2>&1\r\n'
        'if not "%RC%"=="0" goto :installfail\r\n'
        "echo(\r\n"
        "echo   Setup finished. This window closes by itself.\r\n"
        "timeout /t 8 /nobreak >nul 2>&1\r\n"
        "exit /b 0\r\n"
        "\r\n"
        ":: Read \"build\" out of a version.json into the variable named by %%2.\r\n"
        ":readbuild\r\n"
        "setlocal\r\n"
        'set "V="\r\n'
        'for /f "usebackq tokens=2 delims=:," %%a in (`findstr /c:"\\"build\\"" "%~1"`) do '
        'if not defined V set "V=%%a"\r\n'
        'set "V=%V: =%"\r\n'
        'set "V=%V:"=%"\r\n'
        'endlocal & set "%~2=%V%"\r\n'
        "goto :eof\r\n"
        "\r\n"
        ":uptodate\r\n"
        'rmdir /s /q "%WORK%" >nul 2>&1\r\n'
        "echo   Nothing was downloaded and nothing was changed.\r\n"
        "echo   To reinstall regardless, run this again as:  %~nx0 /force\r\n"
        "goto :end\r\n"
        "\r\n"
        ":installfail\r\n"
        "echo(\r\n"
        "echo   The installer did not finish (code %RC%).\r\n"
        "echo   What happened was written to:\r\n"
        "echo     %USERPROFILE%\\.qigor-wallpaper\\install_log.txt\r\n"
        "goto :end\r\n"
        "\r\n"
        ":nohelper\r\n"
        "echo(\r\n"
        "echo   This needs curl.exe, tar.exe and certutil.exe from System32,\r\n"
        "echo   which ship with Windows 10 version 1803 and later, and with\r\n"
        "echo   Windows 11. At least one of them was not found.\r\n"
        "echo(\r\n"
        "echo   Download the zip by hand instead, extract it, and run Install.cmd:\r\n"
        "echo   %BASE%/%ZIPNAME%\r\n"
        "goto :end\r\n"
        "\r\n"
        ":dlfail\r\n"
        "echo(\r\n"
        "echo   The download failed. Check your internet connection and retry.\r\n"
        "echo   You can also download it by hand:\r\n"
        "echo   %BASE%/%ZIPNAME%\r\n"
        "goto :end\r\n"
        "\r\n"
        ":badhash\r\n"
        "echo(\r\n"
        "echo   The download did not match its published checksum and was\r\n"
        "echo   discarded. Nothing was installed.\r\n"
        "echo     expected %WANT%\r\n"
        "echo     got      %GOT%\r\n"
        "goto :end\r\n"
        "\r\n"
        ":fail\r\n"
        "echo(\r\n"
        "echo   Setup could not unpack the download.\r\n"
        "goto :end\r\n"
        "\r\n"
        ":end\r\n"
        'rmdir /s /q "%WORK%" >nul 2>&1\r\n'
        "echo(\r\n"
        "pause\r\n"
        "exit /b 1\r\n"
    ).format(user=GITHUB_USER, repo=GITHUB_REPO, appid=INSTALL_DIR_NAME,
             zipname=SETUP_ZIP.name, payload=SETUP_NAME, size=size_mb)


# ── Config ────────────────────────────────────────────────────────────────────

# ── Tooltip ───────────────────────────────────────────────────────────────────

class Tooltip:
    """600ms hover tooltip."""
    _delay = 600

    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        self._id = self._win = None
        widget.bind("<Enter>",   self._schedule)
        widget.bind("<Leave>",   self._cancel)
        widget.bind("<Button>",  self._cancel)
        widget.bind("<Destroy>", self._cancel)

    def _schedule(self, _=None):
        self._cancel()
        self._id = self.widget.after(self._delay, self._show)

    def _cancel(self, _=None):
        if self._id:  self.widget.after_cancel(self._id); self._id = None
        if self._win: self._win.destroy(); self._win = None

    def _show(self):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._win = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+{}+{}".format(x, y))
        tk.Label(tw, text=self.text, justify=tk.LEFT,
                 background="#ffffe0", foreground="#000000",
                 relief=tk.SOLID, borderwidth=1,
                 font=("Segoe UI", 9), wraplength=380, padx=6, pady=4).pack()


class Config:
    def __init__(self):
        self._dir  = Path.home() / ".qigor-wallpaper" / "build_config.json"
        self._defaults = {
            "theme":           "dark",
            "font_size":       10,
            "window_geometry": "960x780",
            "github_token":    "",
            "deploy_dir":      "",
        }
        self._data = self._load()

    def _load(self):
        try:
            if self._dir.exists():
                return {**self._defaults,
                        **json.loads(self._dir.read_text(encoding="utf-8"))}
        except Exception:
            pass
        return self._defaults.copy()

    def save(self):
        self._dir.parent.mkdir(parents=True, exist_ok=True)
        self._dir.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def get(self, k):       return self._data.get(k, self._defaults.get(k))
    def set(self, k, v):    self._data[k] = v; self.save()


# ── Theme ─────────────────────────────────────────────────────────────────────

DARK = dict(bg="#1e1e1e", fg="#d4d4d4", entry_bg="#2d2d2d", entry_fg="#ffffff",
            console_bg="#0d0d0d", console_fg="#d4d4d4", btn_bg="#3a3a3a", btn_fg="#ffffff")
LIGHT = dict(bg="#f3f3f3", fg="#1e1e1e", entry_bg="#ffffff", entry_fg="#000000",
             console_bg="#ffffff", console_fg="#1e1e1e", btn_bg="#e1e1e1", btn_fg="#000000")

LOG_COLORS_DARK = {
    "header":  "#569cd6",
    "success": "#4ec9b0",
    "error":   "#f48771",
    "warning": "#dcdcaa",
    "info":    "#d4d4d4",
    "path":    "#ce93d8",
    "cmd":     "#fdd835",
    "dim":     "#555555",
    "ok":      "#4ec9b0",
    "section": "#569cd6",
    "time":    "#b5cea8",
}
LOG_COLORS_LIGHT = {
    "header":  "#0277bd",
    "success": "#2e7d32",
    "error":   "#c62828",
    "warning": "#e65100",
    "info":    "#1e1e1e",
    "path":    "#6a1b9a",
    "cmd":     "#f57f17",
    "dim":     "#999999",
    "ok":      "#2e7d32",
    "section": "#0277bd",
    "time":    "#388e3c",
}

BTNS = {
    "setup":    dict(bg="#4527a0", fg="#fff", abg="#5e35b1", text="📦  Build Installer",
                     tip="Build the installable zip: embeddable CPython, plain source,\n"
                         "and the installer that puts it in %LOCALAPPDATA% with\n"
                         "shortcuts and a Settings ▸ Apps entry.\n"
                         "Recipients need no Python and no admin rights, and Smart\n"
                         "App Control does not block it — every .exe/.dll is PSF-signed.\n"
                         "First run downloads ~11 MB of CPython (then cached).\n"
                         "Output: QiGor_Wallpaper_Manager_Setup.zip + version.json"),
    "github":   dict(bg="#1565c0", fg="#fff", abg="#1976d2", text="🐙  Upload Release",
                     tip="Upload the setup zip and version.json to the GitHub Release.\n"
                         "version.json is what the in-app updater reads, so both must\n"
                         "go up together or clients will not see the new build.\n"
                         "Creates the repo and 'latest' release tag if they don't exist.\n"
                         "Requires a GitHub token with 'repo' scope."),
    "clean":    dict(bg="#7a1c1c", fg="#fff", abg="#9e2020", text="🧹  Clean",
                     tip="Remove the staging tree and any leftover PyInstaller\n"
                         "artifacts (build/, dist/, *.spec).\n"
                         "Safe to run any time. Does not delete the zip output."),
    "releases": dict(bg="#00695c", fg="#fff", abg="#00796b", text="🔗  View Release",
                     tip="Open the GitHub releases page in your browser.\n"
                         "github.com/{}/{}/releases/latest".format(
                             GITHUB_USER, GITHUB_REPO)),
}


# ── GitHub API ────────────────────────────────────────────────────────────────

class GitHubUploader:
    """
    Handles GitHub releases API:
      - ensure repo exists
      - get or create 'latest' release
      - delete + re-upload release asset (the .exe)
    """
    def __init__(self, token, user, repo, log_fn):
        self.token = token
        self.user  = user
        self.repo  = repo
        self.log   = log_fn

    def _req(self, method, path, data=None, binary=False, extra_headers=None):
        url = "{}{}".format(GITHUB_API, path)
        h = {
            "Authorization": "token {}".format(self.token),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if extra_headers:
            h.update(extra_headers)
        body = None
        if data is not None:
            body = data if binary else json.dumps(data).encode()
            if not binary:
                h["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=h, method=method)
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read().decode()
                return (json.loads(raw) if raw.strip() else {}), r.status
        except urllib.error.HTTPError as e:
            try:
                raw = e.read().decode()
                return (json.loads(raw) if raw.strip() else {}), e.code
            except Exception:
                return {}, e.code

    def ensure_repo(self) -> bool:
        _, status = self._req("GET", "/repos/{}/{}".format(self.user, self.repo))
        if status == 200:
            self.log("✅  Repo exists: {}/{}".format(self.user, self.repo), "success")
            return True
        self.log("Creating repo {}/{}...".format(self.user, self.repo), "info")
        res, status = self._req("POST", "/user/repos", {
            "name": self.repo,
            "description": "QiGor Wallpaper Manager — Windows wallpaper tool",
            "private": False,
            # No auto_init: it would create a 'main' branch with a README and
            # make it the default, orphaning the 'master' branch we push to.
            "auto_init": False,
            "has_issues": True,
            "has_wiki": False,
        })
        if status in (200, 201):
            self.log("✅  Repo created.", "success")
            return True
        self.log("❌  Failed to create repo: {}".format(
            res.get("message", "unknown")), "error")
        return False

    def get_or_create_release(self):
        """Returns (release_id, upload_url) or (None, None)."""
        res, status = self._req(
            "GET", "/repos/{}/{}/releases/tags/{}".format(
                self.user, self.repo, RELEASE_TAG))
        if status == 200:
            self.log("✅  Release '{}' found.".format(RELEASE_TAG), "success")
            return res["id"], res.get("upload_url", "").split("{")[0]

        self.log("Creating release '{}'...".format(RELEASE_TAG), "info")
        res, status = self._req(
            "POST", "/repos/{}/{}/releases".format(self.user, self.repo), {
                "tag_name":   RELEASE_TAG,
                "name":       RELEASE_NAME,
                # A placeholder only. set_body() rewrites this from the manifest
                # once the assets are up, so the page can never describe a build
                # or an install route that is no longer the current one.
                "body":       "Publishing…",
                "draft":      False,
                "prerelease": False,
            })
        if status in (200, 201):
            self.log("✅  Release created.", "success")
            return res["id"], res.get("upload_url", "").split("{")[0]
        self.log("❌  Failed: {}".format(res.get("message", "unknown")), "error")
        return None, None

    def set_body(self, release_id, body: str) -> bool:
        """Rewrite the release description. Called after every upload so the
        published instructions always match the build that is actually up."""
        res, status = self._req(
            "PATCH", "/repos/{}/{}/releases/{}".format(
                self.user, self.repo, release_id),
            {"name": RELEASE_NAME, "body": body})
        if status == 200:
            self.log("✅  Release notes updated.", "success")
            return True
        self.log("⚠   Could not update the release notes: {}".format(
            res.get("message", "unknown")), "warning")
        return False

    def delete_asset(self, release_id, name) -> bool:
        """True only if an asset by that name existed and was removed."""
        res, status = self._req(
            "GET", "/repos/{}/{}/releases/{}/assets".format(
                self.user, self.repo, release_id))
        if status != 200:
            return False
        for a in res:
            if a["name"] == name:
                self.log("  🗑  Removing existing: {}".format(name), "dim")
                dres, dstatus = self._req("DELETE",
                    "/repos/{}/{}/releases/assets/{}".format(
                        self.user, self.repo, a["id"]))
                if dstatus != 204:
                    self.log("  ⚠  Could not delete old asset ({}): {}".format(
                        dstatus, dres.get("message", "unknown")), "warning")
                    return False
                return True
        return False

    def upload_asset(self, upload_url, file_path: Path, asset_name: str) -> bool:
        mb = file_path.stat().st_size / (1024 * 1024)
        self.log("  ⬆  {}  ({:.1f} MB)...".format(asset_name, mb), "info")
        with open(file_path, "rb") as f:
            data = f.read()
        req = urllib.request.Request(
            "{}?name={}".format(upload_url, asset_name),
            data=data, method="POST",
            headers={
                "Authorization": "token {}".format(self.token),
                "Content-Type":  "application/octet-stream",
                "Accept":        "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            })
        try:
            with urllib.request.urlopen(req) as r:
                res = json.loads(r.read().decode())
                url = res.get("browser_download_url", "uploaded")
                self.log("  ✅  {}".format(url), "success")
                return True
        except urllib.error.HTTPError as e:
            self.log("  ❌  Upload failed ({}): {}".format(
                e.code, e.read().decode()[:200]), "error")
            return False


# ── App ───────────────────────────────────────────────────────────────────────

class App:

    def __init__(self, root: tk.Tk):
        self.root    = root
        self.root.title(APP_NAME)
        self.cfg     = Config()
        self.root.geometry(self.cfg.get("window_geometry"))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._theme  = self.cfg.get("theme")
        self._fsize  = self.cfg.get("font_size")
        self._busy   = False
        self._build_ui()
        self._apply_theme()
        self.root.after(200, self._preflight)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Toolbar
        tb = tk.Frame(self.root)
        tb.pack(fill=tk.X, padx=6, pady=4)
        self._tb = tb

        self._theme_btn = tk.Button(tb, text="☀ Light",
                                    command=self._toggle_theme,
                                    relief=tk.FLAT, padx=8)
        self._theme_btn.pack(side=tk.LEFT)
        Tooltip(self._theme_btn, "Toggle dark / light theme.")

        afont = tk.Button(tb, text="A+", relief=tk.FLAT, padx=6,
                  command=lambda: self._chg_font(1))
        afont.pack(side=tk.LEFT)
        Tooltip(afont, "Increase console font size.")

        afont2 = tk.Button(tb, text="A−", relief=tk.FLAT, padx=6,
                  command=lambda: self._chg_font(-1))
        afont2.pack(side=tk.LEFT)
        Tooltip(afont2, "Decrease console font size.")

        clr = tk.Button(tb, text="Clear Log", relief=tk.FLAT, padx=8,
                  command=self._clear_log)
        clr.pack(side=tk.RIGHT)
        Tooltip(clr, "Clear the output console.")

        content = tk.Frame(self.root)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=2)

        # ── Build config panel ────────────────────────────────────────────────
        cf = tk.LabelFrame(content, text="  Build Configuration  ")
        cf.pack(fill=tk.X, pady=(0, 4))
        self._info = {}
        for key, label in [
            ("entry",    "Entry point:"),
            ("icon",     "Icon file:"),
            ("output",   "Output zip:"),
            ("workdir",  "Working dir:"),
        ]:
            row = tk.Frame(cf)
            row.pack(fill=tk.X, padx=6, pady=1)
            tk.Label(row, text=label, font=("Segoe UI", 9, "bold"),
                     width=14, anchor=tk.W).pack(side=tk.LEFT)
            lbl = tk.Label(row, text="...", font=("Consolas", 9), anchor=tk.W)
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._info[key] = lbl

        # ── GitHub token ──────────────────────────────────────────────────────
        gf = tk.LabelFrame(content,
                           text="  GitHub Token  (write access — stored in ~/.qigor-wallpaper/)  ")
        gf.pack(fill=tk.X, pady=(0, 4))
        tok_row = tk.Frame(gf)
        tok_row.pack(fill=tk.X, padx=6, pady=4)
        self._token_var = tk.StringVar(value=self.cfg.get("github_token"))
        self._tok_entry = tk.Entry(tok_row, textvariable=self._token_var,
                                   font=("Consolas", self._fsize), show="*")
        self._tok_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        Tooltip(self._tok_entry,
                "GitHub Personal Access Token.\n"
                "• Classic token (ghp_…): needs the 'repo' scope.\n"
                "• Fine-grained token (github_pat_…): needs access to this repo\n"
                "  plus 'Contents: Read and write' permission.\n"
                "Create/edit at: github.com/settings/tokens\n"
                "Stored in ~/.qigor-wallpaper/build_config.json")
        self._show_tok = tk.BooleanVar(value=False)
        tk.Checkbutton(tok_row, text="Show", variable=self._show_tok,
                       command=lambda: self._tok_entry.config(
                           show="" if self._show_tok.get() else "*")
                       ).pack(side=tk.LEFT, padx=(8, 0))

        # ── Action buttons ────────────────────────────────────────────────────
        bf = tk.Frame(content)
        bf.pack(fill=tk.X, pady=6)
        self._btns = {}
        for key, cmd in [
            ("setup",  self._start_setup),
            ("github", self._start_github),
            ("clean",  self._clean),
        ]:
            b = BTNS[key]
            btn = tk.Button(bf, text=b["text"],
                            bg=b["bg"], fg=b["fg"],
                            activebackground=b["abg"], activeforeground="#fff",
                            font=("Segoe UI", 11, "bold"), height=2,
                            relief=tk.FLAT, cursor="hand2", command=cmd)
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            Tooltip(btn, b["tip"])
            self._btns[key] = btn

        # View Release — outside self._btns so it stays enabled during builds
        b = BTNS["releases"]
        self._releases_btn = tk.Button(bf, text=b["text"],
                            bg=b["bg"], fg=b["fg"],
                            activebackground=b["abg"], activeforeground="#fff",
                            font=("Segoe UI", 11, "bold"), height=2,
                            relief=tk.FLAT, cursor="hand2",
                            command=self._view_release)
        self._releases_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        Tooltip(self._releases_btn, b["tip"])

        # ── Git source sync ───────────────────────────────────────────────────
        gitsf = tk.LabelFrame(content,
            text="  Source → GitHub  ({}/{})  ".format(GITHUB_USER, GITHUB_REPO))
        gitsf.pack(fill=tk.X, pady=(0, 4))
        git_row = tk.Frame(gitsf)
        git_row.pack(pady=4)
        self._git_btns = []
        for label, cmd, tip in [
            ("1 – Setup",   self._git_setup,
             "First-time setup: git init, create .gitignore, initial commit,\n"
             "add GitHub remote, and create the repo via API if needed.\n"
             "Safe to re-run — skips steps already done."),
            ("2 – Commit",  self._git_commit,
             "Stage all changes (git add -A) and create a timestamped commit.\n"
             "Shows what changed before committing."),
            ("3 – Push",    self._git_push,
             "Push committed changes to GitHub (git push -u origin main).\n"
             "Requires the repo to exist and token to have push access."),
            ("4 – Status",  self._git_status,
             "Show git remote, last 5 commits, and any uncommitted changes."),
        ]:
            b = tk.Button(git_row, text=label, width=16, height=2,
                          font=("Segoe UI", 10, "bold"), command=cmd,
                          relief=tk.FLAT, cursor="hand2")
            b.pack(side=tk.LEFT, padx=6)
            Tooltip(b, tip)
            self._git_btns.append(b)

        # ── Console ───────────────────────────────────────────────────────────
        console_frame = tk.LabelFrame(content, text="  Output  ")
        console_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.console = scrolledtext.ScrolledText(
            console_frame, font=("Consolas", self._fsize), wrap=tk.WORD)
        self.console.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # ── Status bar ────────────────────────────────────────────────────────
        sb = tk.Frame(self.root, relief=tk.SUNKEN, bd=1)
        sb.pack(fill=tk.X)
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(sb, textvariable=self._status_var, anchor=tk.W,
                 font=("Segoe UI", 9)).pack(
                     side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Sizegrip(sb).pack(side=tk.RIGHT)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        t = DARK if self._theme == "dark" else LIGHT
        colors = LOG_COLORS_DARK if self._theme == "dark" else LOG_COLORS_LIGHT
        self.root.configure(bg=t["bg"])
        self._tb.configure(bg=t["bg"])
        self.console.configure(bg=t["console_bg"], fg=t["console_fg"],
                               insertbackground=t["console_fg"])
        for tag, fg in colors.items():
            bold = tag in ("header", "section", "success", "error")
            self.console.tag_configure(
                tag, foreground=fg,
                font=("Consolas", self._fsize, "bold" if bold else "normal"))
        self.console.tag_configure(
            "dim", foreground=colors["dim"],
            font=("Consolas", self._fsize))
        self._theme_btn.config(
            text="☀ Light" if self._theme == "dark" else "🌙 Dark",
            bg=t["bg"], fg=t["fg"])
        for w in self._tb.winfo_children():
            if w is not self._theme_btn:
                try: w.configure(bg=t["bg"], fg=t["fg"])
                except Exception: pass

    def _toggle_theme(self):
        self._theme = "light" if self._theme == "dark" else "dark"
        self.cfg.set("theme", self._theme)
        self._apply_theme()

    def _chg_font(self, d):
        self._fsize = max(7, min(20, self._fsize + d))
        self.console.config(font=("Consolas", self._fsize))
        self.cfg.set("font_size", self._fsize)
        self._apply_theme()

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg, tag="info"):
        def _do():
            ts = datetime.now().strftime("%H:%M:%S")
            self.console.insert(tk.END, "[{}]  ".format(ts), "dim")
            self.console.insert(tk.END, "{}\n".format(msg), tag)
            self.console.see(tk.END)
        self.root.after(0, _do)

    def _log_raw(self, msg, tag="dim"):
        def _do():
            self.console.insert(tk.END, "{}\n".format(msg), tag)
            self.console.see(tk.END)
        self.root.after(0, _do)

    def _section(self, title):
        self._log("", "info")
        self._log("═" * 56, "header")
        self._log("  {}".format(title), "header")
        self._log("═" * 56, "header")

    def _clear_log(self):
        self.console.delete("1.0", tk.END)

    def _status(self, m):
        self.root.after(0, lambda: self._status_var.set(m))

    # ── Busy lock ─────────────────────────────────────────────────────────────

    def _lock(self, label="⏳ Working…"):
        self._busy = True
        for b in list(self._btns.values()) + self._git_btns:
            b.config(state=tk.DISABLED)
        self._status(label)

    def _unlock(self):
        self._busy = False
        for key, b in self._btns.items():
            b.config(state=tk.NORMAL, text=BTNS[key]["text"])
        for b in self._git_btns:
            b.config(state=tk.NORMAL)
        self._status("Ready")

    def _thread(self, fn):
        if self._busy:
            messagebox.showwarning("Busy", "An operation is already running.")
            return
        self._lock()
        def runner():
            try:
                fn()
            except Exception as e:
                import traceback
                self._log("UNEXPECTED ERROR: {}".format(e), "error")
                self._log(traceback.format_exc(), "error")
            finally:
                self.root.after(0, self._unlock)
        threading.Thread(target=runner, daemon=True).start()

    # ── Preflight ─────────────────────────────────────────────────────────────

    def _preflight(self):
        self._info["entry"].config(text=str(ENTRY_PY))
        self._info["icon"].config(text=str(ICON_FILE))
        self._info["output"].config(text=str(SETUP_ZIP))
        self._info["workdir"].config(text=str(SCRIPT_DIR))

        self._section("QiGor Wallpaper Manager — Build Tool  v{}".format(APP_VERSION))

        # Entry point
        if ENTRY_PY.exists():
            self._log("✅  Entry point: {}  ({} KB)".format(
                ENTRY_PY.name, ENTRY_PY.stat().st_size // 1024), "success")
        else:
            self._log("❌  Entry point not found: {}".format(ENTRY_PY), "error")

        # app/ package
        app_dir = SCRIPT_DIR / "app"
        if app_dir.exists():
            py_count = len(list(app_dir.glob("*.py")))
            self._log("✅  app/ package: {} modules".format(py_count), "success")
        else:
            self._log("❌  app/ directory not found!", "error")

        # installer/ package — without it the zip runs but cannot install itself
        inst_dir = SCRIPT_DIR / "installer"
        needed   = ("core.py", "install.py", "uninstall.py", "paths.py",
                    "shortcuts.py")
        missing  = [n for n in needed if not (inst_dir / n).exists()]
        if inst_dir.exists() and not missing:
            self._log("✅  installer/ package: {} modules".format(
                len(list(inst_dir.glob("*.py")))), "success")
        elif inst_dir.exists():
            self._log("❌  installer/ is incomplete — missing {}".format(
                ", ".join(missing)), "error")
        else:
            self._log("❌  installer/ directory not found — the zip would not "
                      "be installable", "error")

        # assets/
        assets_dir = SCRIPT_DIR / "assets"
        if assets_dir.exists():
            count = len(list(assets_dir.iterdir()))
            self._log("✅  assets/: {} files".format(count), "success")
        else:
            self._log("⚠   assets/ directory not found — images won't be bundled", "warning")

        # Icon — lives in assets/, regenerated automatically at build time
        if ICON_FILE.exists():
            self._log("✅  Icon: {}  ({} KB)".format(
                ICON_FILE.name, ICON_FILE.stat().st_size // 1024), "success")
        else:
            self._log("ℹ   Icon not found in assets/ — will be generated at build time", "info")

        # Existing zip
        if SETUP_ZIP.exists():
            mb    = SETUP_ZIP.stat().st_size / (1024 * 1024)
            mtime = datetime.fromtimestamp(
                SETUP_ZIP.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            self._log("ℹ   Existing zip: {:.1f} MB, built {}".format(mb, mtime), "info")

        # tkinter source — the embeddable distribution ships none, so a full
        # python.org install has to be present to graft it from.
        self._log("", "info")
        host = Path(sys.base_prefix)
        if (host / "DLLs" / "_tkinter.pyd").exists() and (host / "tcl").exists():
            self._log("✅  tkinter available to graft from {}".format(host), "success")
        else:
            self._log("❌  This interpreter has no tkinter to graft — build from a "
                      "standard python.org install ({})".format(host), "error")

        # tkinterdnd2
        try:
            import tkinterdnd2  # noqa
            self._log("✅  tkinterdnd2 found", "success")
        except ImportError:
            self._log("⚠   tkinterdnd2 not installed here — it is pip-installed "
                      "into the zip regardless, so this only affects running "
                      "from source.  pip install tkinterdnd2", "warning")

        # git
        git = shutil.which("git")
        self._log("{}  git: {}".format(
            "✅" if git else "⚠ ", git or "not found — install Git for Windows"),
            "success" if git else "warning")

        ver, build = read_app_versions()
        self._log("", "info")
        self._log("Ready.  Version {}  build {} — click 📦 Build Installer.".format(
            ver, build), "info")
        self._log("", "info")

    # ── Icon generation ───────────────────────────────────────────────────────

    def _regen_icon(self):
        """Generate assets/qigor_wallpaper_manager.ico from the bundled source JPG.
        Called automatically at the start of every build. Takes ~0.1s."""
        try:
            from PIL import Image
        except ImportError:
            self._log("⚠   Pillow not installed — skipping icon generation (pip install pillow)", "warning")
            return False

        src = SCRIPT_DIR / "assets" / "qigor_wallpaper_manager_150k.jpg"
        if not src.exists():
            self._log("⚠   Icon source image not found: {}".format(src), "warning")
            return False

        import io, struct
        img = Image.open(str(src))
        # Crop gorilla face area
        cx, cy, half = 490, 160, 220
        w, h = img.size
        cx = min(cx, w - half)
        cy = min(cy, h - half)
        crop = img.crop((cx - half, cy - half, cx + half, cy + half))

        sizes = [256, 128, 64, 48, 32, 16]
        entries = []
        for s in sizes:
            resized = crop.resize((s, s), Image.LANCZOS).convert("RGBA")
            buf = io.BytesIO()
            resized.save(buf, format="PNG")
            entries.append((s, buf.getvalue()))

        count      = len(entries)
        header     = struct.pack("<HHH", 0, 1, count)
        data_start = 6 + count * 16
        dir_bytes  = b""
        for s, data in entries:
            dir_bytes += struct.pack("<BBBBHHII",
                s if s < 256 else 0,
                s if s < 256 else 0,
                0, 0, 1, 32,
                len(data), data_start)
            data_start += len(data)

        with open(ICON_FILE, "wb") as f:
            f.write(header + dir_bytes)
            for _, data in entries:
                f.write(data)

        self._log("✅  Icon: {}  ({} KB)".format(
            ICON_FILE.name, ICON_FILE.stat().st_size // 1024), "success")
        self._info["icon"].config(text=str(ICON_FILE))
        return True

    # ── Build installer zip ───────────────────────────────────────────────────

    def _start_setup(self):
        if not ENTRY_PY.exists():
            messagebox.showerror("Missing",
                "Entry point not found:\n{}".format(ENTRY_PY))
            return
        self._thread(self._do_build_setup)

    def _fetch_embeddable(self, pyver):
        """Return the cached embeddable CPython zip for pyver, downloading once."""
        EMBED_CACHE.mkdir(parents=True, exist_ok=True)
        name = "python-{}-embed-amd64.zip".format(pyver)
        dest = EMBED_CACHE / name
        if dest.exists() and dest.stat().st_size > 1_000_000:
            self._log("✅  Cached runtime: {}  ({:.1f} MB)".format(
                name, dest.stat().st_size / 1e6), "success")
            return dest
        url = "https://www.python.org/ftp/python/{}/{}".format(pyver, name)
        self._log("⬇   {}".format(url), "info")
        self._status("Downloading embeddable CPython…")
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                with open(dest, "wb") as f:
                    shutil.copyfileobj(r, f)
        except Exception as e:
            dest.unlink(missing_ok=True)
            self._log("❌  Download failed: {}".format(e), "error")
            self._log("    Check that python.org publishes an embeddable build "
                      "for {}.".format(pyver), "warning")
            return None
        self._log("✅  Downloaded ({:.1f} MB)".format(
            dest.stat().st_size / 1e6), "success")
        return dest

    def _release_notes(self) -> str:
        """
        Notes shown in the app's update dialog.

        The CHANGELOG.md section headed `## <APP_BUILD>` — the changelog keeps
        every release, and this is the slice for the one being built. With no
        such section, warn (the version was likely not bumped, or the notes not
        written) and fall back to recent commit subjects.
        """
        build = read_app_versions()[1]
        log_file = SCRIPT_DIR / "CHANGELOG.md"
        if log_file.exists():
            text = log_file.read_text(encoding="utf-8")
            m = re.search(r"^## +{}\b[^\n]*\n(.*?)(?=^## |\Z)".format(
                re.escape(build)), text, re.M | re.S)
            if m and m.group(1).strip():
                return m.group(1).strip()
        self._log("⚠   CHANGELOG.md has no section for {} — did you bump "
                  "APP_BUILD and write the notes? Using commit subjects "
                  "instead.".format(build), "warning")
        out, rc = self._git_out("log", "-8", "--pretty=• %s")
        return out.strip() if rc == 0 else ""

    def _do_build_setup(self):
        t0 = time.monotonic()
        self._section("BUILD INSTALLER ZIP")

        from installer.core import write_launchers, clear_readonly

        pyver = "{}.{}.{}".format(*sys.version_info[:3])
        tag   = "python{}{}".format(sys.version_info.major, sys.version_info.minor)
        host  = Path(sys.base_prefix)
        app_ver, app_build = read_app_versions()

        self._log("App version     : {}  build {}".format(app_ver, app_build), "info")
        self._log("Runtime version : CPython {}  (matched to this interpreter)".format(pyver), "info")
        self._log("tkinter source  : {}".format(host), "info")
        self._log("Bundled deps    : {}".format(", ".join(SETUP_DEPS)), "info")
        self._log("", "info")

        # The embeddable distribution ships no tkinter at all, so it has to be
        # grafted in from a full install. Fail early if the pieces aren't there.
        graft = {
            "_tkinter.pyd": host / "DLLs" / "_tkinter.pyd",
            "Lib/tkinter":  host / "Lib" / "tkinter",
            "tcl/":         host / "tcl",
        }
        missing = [k for k, v in graft.items() if not v.exists()]
        if missing:
            self._log("❌  Cannot graft tkinter — missing from this install:", "error")
            for k in missing:
                self._log("      {}   ({})".format(k, graft[k]), "error")
            self._log("    A standard python.org install is needed as the source.",
                      "warning")
            return

        embed_zip = self._fetch_embeddable(pyver)
        if embed_zip is None:
            return

        # ── Stage the runtime ─────────────────────────────────────────────────
        out = SETUP_STAGE / SETUP_NAME
        rt  = out / "runtime"
        if SETUP_STAGE.exists():
            # A read-only folder copied in from OneDrive makes rmtree fail on
            # the directory itself, and ignore_errors would leave a half-wiped
            # staging tree that the next copytree then trips over.
            clear_readonly(SETUP_STAGE)
            shutil.rmtree(SETUP_STAGE, ignore_errors=True)
        rt.mkdir(parents=True)

        self._status("Extracting runtime…")
        own_pth = "{}._pth".format(tag)
        with zipfile.ZipFile(embed_zip) as z:
            for m in z.namelist():
                if m != own_pth:        # ours replaces the shipped one
                    z.extract(m, rt)
        self._log("✅  Runtime extracted", "success")

        self._status("Grafting tkinter…")
        for b in ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll", "zlib1.dll"):
            src = host / "DLLs" / b
            if src.exists():
                shutil.copy2(src, rt / b)
        shutil.copytree(host / "Lib" / "tkinter", rt / "Lib" / "tkinter")

        # Only the Tcl/Tk runtime libraries. The full tcl/ tree also carries
        # build tooling (nmake/) including an unsigned mingw helper .exe — never
        # executed here, and precisely the sort of stray binary that makes
        # antivirus heuristics flag a distributed zip.
        (rt / "tcl").mkdir(exist_ok=True)
        kept = []
        for d in sorted((host / "tcl").iterdir()):
            if d.is_dir() and (d.name == "tcl8" or
                               d.name.startswith(("tcl8.", "tk8."))):
                shutil.copytree(d, rt / "tcl" / d.name)
                kept.append(d.name)
        self._log("✅  tkinter + Tcl/Tk grafted in  (tcl/: {})".format(
            ", ".join(kept)), "success")

        # `import site` is the only import form CPython 3.13 accepts in a ._pth
        # ("unsupported 'import' line" otherwise) — and it is what makes the
        # sitecustomize below run. ".." puts the app folder on sys.path, which
        # is what lets `import app` and `import installer` resolve.
        (rt / own_pth).write_text(
            "{}.zip\n.\nLib\nLib\\site-packages\n..\nimport site\n".format(tag),
            encoding="utf-8")

        # Tcl cannot locate its library folder in this layout, so point it there
        # on every launch — including Task Scheduler runs, which never go
        # through the .cmd launcher and so inherit no environment from it.
        sp = rt / "Lib" / "site-packages"
        sp.mkdir(parents=True, exist_ok=True)
        (sp / "sitecustomize.py").write_text(
            '"""Portable runtime bootstrap — locate the bundled Tcl/Tk."""\n'
            "import os\n"
            "from pathlib import Path\n"
            "_rt = Path(__file__).resolve().parents[2]\n"
            'for _var, _pat in (("TCL_LIBRARY", "tcl8.*"), ("TK_LIBRARY", "tk8.*")):\n'
            "    for _d in sorted((_rt / 'tcl').glob(_pat)):\n"
            "        if _d.is_dir():\n"
            "            os.environ.setdefault(_var, str(_d))\n"
            "            break\n",
            encoding="utf-8")

        # ── Dependencies ──────────────────────────────────────────────────────
        self._status("Installing dependencies…")
        self._log("Installing {}…".format(", ".join(SETUP_DEPS)), "info")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--target", str(sp)] + SETUP_DEPS,
            capture_output=True, text=True, cwd=str(SCRIPT_DIR),
            creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode != 0:
            self._log("❌  pip failed:\n{}".format(
                (r.stderr or r.stdout or "")[:600]), "error")
            return
        self._log("✅  Dependencies installed", "success")

        # ── App source — plain, unobfuscated ──────────────────────────────────
        self._regen_icon()
        for d in SETUP_SRC_DIRS:
            src = SCRIPT_DIR / d
            if not src.exists():
                self._log("❌  Missing source folder: {}".format(src), "error")
                return
            shutil.copytree(src, out / d,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copy2(ENTRY_PY, out / ENTRY_PY.name)
        if ICON_FILE.exists():
            shutil.copy2(ICON_FILE, out / ICON_FILE.name)
        self._log("✅  Source + installer + assets copied  ({})".format(
            ", ".join(SETUP_SRC_DIRS)), "success")

        # ── Launchers ─────────────────────────────────────────────────────────
        # The run launcher comes from installer.core so that the shipped copy and
        # the one written at install time can never drift apart. Uninstall.cmd is
        # withheld: it only makes sense once something has been installed.
        write_launchers(out, include_uninstaller=False)
        # The guard matters: double-clicking Install.cmd from inside Explorer's
        # zip preview extracts only that one file to a temp folder, so runtime\
        # is not beside it and `start` would fail with no message at all.
        (out / "Install.cmd").write_text(
            "@echo off\r\n"
            'if exist "%~dp0runtime\\pythonw.exe" (\r\n'
            '    start "" "%~dp0runtime\\pythonw.exe" "%~dp0installer\\install.py" %*\r\n'
            "    exit /b 0\r\n"
            ")\r\n"
            "echo(\r\n"
            "echo   QiGor Wallpaper Manager - installer\r\n"
            "echo(\r\n"
            "echo   This folder is not fully extracted, so the bundled Python\r\n"
            "echo   runtime is missing and the installer cannot start.\r\n"
            "echo(\r\n"
            "echo   If you ran Install.cmd while still looking inside the .zip,\r\n"
            "echo   Windows extracted only that one file. Close this window,\r\n"
            'echo   right-click the .zip, choose "Extract All...", and run\r\n'
            "echo   Install.cmd from the extracted folder.\r\n"
            "echo(\r\n"
            "pause\r\n"
            "exit /b 1\r\n",
            encoding="ascii")
        self._log("✅  Install.cmd + run launcher written", "success")

        # ── Payload manifest ──────────────────────────────────────────────────
        # Copied into the install root, where the updater and the uninstaller
        # both read it to know what is installed.
        payload_meta = {
            "version":  app_ver,
            "build":    app_build,
            "runtime":  pyver,
            "asset":    SETUP_ZIP.name,
            "built_at": datetime.now().isoformat(timespec="seconds"),
        }
        (out / "version.json").write_text(
            json.dumps(payload_meta, indent=2), encoding="utf-8")

        (out / "README.txt").write_text(
            "QiGor Wallpaper Manager  v{ver}  (build {build})\n"
            "{rule}\n\n"
            "INSTALL\n"
            "  Double-click  Install.cmd\n"
            "  It installs for your user account only, so Windows never asks for\n"
            "  an administrator password. You get a Start Menu entry, an optional\n"
            "  desktop shortcut, and an entry in Settings > Apps.\n"
            "  Installs to: %LOCALAPPDATA%\\Programs\\QiGorWallpaperManager\n"
            "  You can delete this extracted folder afterwards.\n"
            "  If you were already running an older copy, the installer takes\n"
            "  over its slideshow and reminder schedules and tells you where the\n"
            "  old folder is, so you can delete that too.\n\n"
            "NEXT TIME, SKIP THE ZIP\n"
            "  QiGor-Setup.cmd on the releases page does all of this in one\n"
            "  double-click: it downloads the current release, checks it against\n"
            "  the published checksum, and runs this installer.\n\n"
            "OR JUST RUN IT\n"
            "  Double-click  \"{name}.cmd\"  to run without installing.\n"
            "  A console window blinks for a moment, then the app opens.\n\n"
            "UPDATES\n"
            "  The app checks GitHub for a new release once a day and offers to\n"
            "  install it. Help > Check for Updates does it on demand, and the\n"
            "  automatic check can be switched off in that same window.\n\n"
            "UNINSTALL\n"
            "  Settings > Apps > QiGor Wallpaper Manager > Uninstall,\n"
            "  or run Uninstall.cmd in the installed folder.\n"
            "  It stops the slideshow and reminder tasks first. Your settings and\n"
            "  saved wallpapers in %USERPROFILE%\\.qigor-wallpaper\\ are kept unless\n"
            "  you tick the box to remove them.\n\n"
            "WHAT IS IN HERE\n"
            "  runtime\\    CPython {py} - the official python.org embeddable build\n"
            "  app\\        application source\n"
            "  installer\\  install, uninstall, and shortcut creation\n"
            "  assets\\     images and icon\n"
            "  You do not need Python installed. Nothing is written outside the\n"
            "  install folder except your settings, in %USERPROFILE%\\.qigor-wallpaper\\\n\n"
            "WHY A ZIP AND NOT A SETUP.EXE\n"
            "  Windows 11's Smart App Control blocks unsigned .exe files based on a\n"
            "  cloud reputation score, with no way for you to override it. Every\n"
            "  program that actually runs here - pythonw.exe, the Python DLLs, the\n"
            "  Tcl/Tk DLLs - is signed by the Python Software Foundation, so there\n"
            "  is nothing for Smart App Control to block. The installer itself is\n"
            "  ordinary Python source you can read.\n\n"
            "IF YOU RUN IT WITHOUT INSTALLING\n"
            "  Do not move the folder after starting the slideshow: the Windows\n"
            "  scheduled task records the full path. Reopen the app and use\n"
            "  Slideshow > Start to re-register it at the new location. Installing\n"
            "  avoids this, because the install folder never moves.\n"
            "  Keep the path short - beyond roughly 200 characters Windows fails to\n"
            "  load the DLLs and the app dies with a '_tkinter' import error.\n".format(
                ver=app_ver, build=app_build, py=pyver, name=SETUP_NAME,
                rule="=" * 62),
            encoding="utf-8")
        self._log("✅  README.txt + version.json written", "success")

        # ── Zip ───────────────────────────────────────────────────────────────
        self._status("Compressing…")
        SETUP_ZIP.unlink(missing_ok=True)
        files = [f for f in sorted(out.rglob("*")) if f.is_file()]
        with zipfile.ZipFile(SETUP_ZIP, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=6) as z:
            for f in files:
                z.write(f, str(Path(SETUP_NAME) / f.relative_to(out)))

        # ── Release manifest ──────────────────────────────────────────────────
        # Uploaded next to the zip. The updater fetches only this file to decide
        # whether anything needs downloading, and takes the checksum from it.
        self._status("Hashing…")
        digest = hashlib.sha256()
        with open(SETUP_ZIP, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        manifest = dict(payload_meta)
        manifest["sha256"] = digest.hexdigest()
        manifest["size"]   = SETUP_ZIP.stat().st_size
        manifest["notes"]  = self._release_notes()
        MANIFEST_JSON.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # The same digest again as one plain line. QiGor-Setup.cmd verifies the
        # download in batch, where picking a value out of JSON is fragile.
        SHA_TXT.write_text("{}  {}\n".format(manifest["sha256"], SETUP_ZIP.name),
                           encoding="ascii")
        WEB_SETUP_CMD.write_text(
            web_setup_cmd(manifest["size"] / 1e6), encoding="ascii")
        self._log("✅  SHA256.txt + QiGor-Setup.cmd written", "success")

        raw     = sum(f.stat().st_size for f in files)
        mb      = SETUP_ZIP.stat().st_size / 1e6
        elapsed = time.monotonic() - t0
        self._log("", "info")
        self._log("═" * 56, "header")
        self._log("  ✅  INSTALLER BUILD COMPLETE  —  {:.0f}s".format(elapsed), "success")
        self._log("  📦  {:.1f} MB zipped   (from {:.1f} MB, {} files)".format(
            mb, raw / 1e6, len(files)), "success")
        self._log("  🔒  sha256 {}…".format(manifest["sha256"][:24]), "success")
        for p in RELEASE_ASSETS:
            self._log("  📄  {}".format(p), "path")
        self._log("═" * 56, "header")
        self._log("", "info")
        self._log("Test it: open the staging folder below and run Install.cmd", "info")
        self._log("  {}".format(out), "path")
        self._log("Then click 🐙 Upload Release to publish. All four assets go up "
                  "together — version.json is what tells installed copies a new "
                  "build exists, and SHA256.txt is what QiGor-Setup.cmd verifies "
                  "the download against.", "info")
        self._status("Installer build complete!  {:.1f} MB".format(mb))

    # ── GitHub release upload ─────────────────────────────────────────────────

    def _start_github(self):
        token = self._token_var.get().strip()
        if not token:
            messagebox.showerror("No Token",
                "Enter your GitHub Personal Access Token.\n\n"
                "Create one at: github.com/settings/tokens\n"
                "Required scope: repo")
            return
        missing = [p for p in RELEASE_ASSETS if not p.exists()]
        if missing:
            messagebox.showerror("Nothing to upload",
                "Build output is missing:\n\n  {}\n\n"
                "Run 📦 Build Installer first — it writes both the zip and "
                "version.json.".format("\n  ".join(str(p) for p in missing)))
            return
        self.cfg.set("github_token", token)
        self._thread(self._do_github)

    def _do_github(self):
        self._section("UPLOAD TO GITHUB RELEASE")
        token = self._token_var.get().strip()

        def gh_log(msg, tag="info"):
            self.root.after(0, lambda m=msg, t=tag: self._log(m, t))

        up = GitHubUploader(token, GITHUB_USER, GITHUB_REPO, gh_log)

        self._log("Target: github.com/{}/{}".format(GITHUB_USER, GITHUB_REPO), "info")
        man = {}
        try:
            man = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
            self._log("Publishing build {}  ({:.1f} MB, sha256 {}…)".format(
                man.get("build"), man.get("size", 0) / 1e6,
                str(man.get("sha256"))[:16]), "info")
        except Exception:
            self._log("⚠   version.json is unreadable — clients will not see "
                      "this release.", "warning")
        self._log("", "info")

        if not up.ensure_repo():
            return

        release_id, upload_url = up.get_or_create_release()
        if not release_id:
            return

        assets = [(p, p.name) for p in RELEASE_ASSETS]
        ok = True
        for path, name in assets:
            self._status("Uploading {}…".format(name))
            up.delete_asset(release_id, name)
            if not up.upload_asset(upload_url, path, name):
                ok = False

        for name in OBSOLETE_ASSETS:
            if up.delete_asset(release_id, name):
                self._log("🗑  Removed obsolete asset: {}".format(name), "warning")

        if ok:
            self._status("Updating release notes…")
            up.set_body(release_id, release_body(man))
            self._log("", "info")
            self._log("═" * 56, "header")
            self._log("  ✅  UPLOAD COMPLETE", "success")
            for _, name in assets:
                dl_url = ("https://github.com/{}/{}/releases/latest/"
                          "download/{}".format(GITHUB_USER, GITHUB_REPO,
                                               urllib.parse.quote(name)))
                self._log("  🔗  {}".format(dl_url), "success")
            self._log("═" * 56, "header")
            self._status("Uploaded!")
        else:
            self._log("❌  Upload failed — the token lacks write access.", "error")
            if token.startswith("github_pat_"):
                self._log("Fine-grained token detected. It needs:", "warning")
                self._log("  • Repository access: include {}/{}".format(
                    GITHUB_USER, GITHUB_REPO), "warning")
                self._log("  • Permissions → Contents: Read and write", "warning")
                self._log("Edit it at: github.com/settings/personal-access-tokens", "warning")
            else:
                self._log("Classic token: enable the 'repo' scope at "
                          "github.com/settings/tokens", "warning")

    # ── Git source sync ───────────────────────────────────────────────────────

    def _git(self, *args):
        cmd = ["git"] + list(args)
        self._log("  $ {}".format(" ".join(cmd)), "dim")
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(SCRIPT_DIR),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.root.after(0,
                        lambda l=line: self._log("    {}".format(l), "dim"))
            proc.wait()
            return proc.returncode
        except FileNotFoundError:
            self._log("git not found — install Git for Windows.", "error")
            return -1

    def _git_out(self, *args):
        try:
            r = subprocess.run(
                ["git"] + list(args), cwd=str(SCRIPT_DIR),
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            return r.stdout.strip(), r.returncode
        except FileNotFoundError:
            return "", -1

    def _git_setup(self):  self._thread(self._do_git_setup)
    def _git_commit(self): self._thread(self._do_git_commit)
    def _git_push(self):   self._thread(self._do_git_push)
    def _git_status(self): self._thread(self._do_git_status)

    def _do_git_setup(self):
        self._section("GIT SETUP")
        token    = self._token_var.get().strip()
        repo_url = "https://github.com/{}/{}".format(GITHUB_USER, GITHUB_REPO)
        git_dir  = SCRIPT_DIR / ".git"

        # Create GitHub repo via API if needed
        if token:
            def gh_log(msg, tag="info"):
                self.root.after(0, lambda m=msg, t=tag: self._log(m, t))
            up = GitHubUploader(token, GITHUB_USER, GITHUB_REPO, gh_log)
            up.ensure_repo()
        else:
            self._log("⚠   No token — skipping remote repo creation.", "warning")

        if git_dir.exists():
            self._log("Git repo already exists.", "info")
            # Always verify/fix the remote — this is the most common issue
            existing, _ = self._git_out("remote", "get-url", "origin")
            if existing:
                if existing.strip() != repo_url:
                    self._log("Updating remote URL to: {}".format(repo_url), "info")
                    self._git("remote", "set-url", "origin", repo_url)
                else:
                    self._log("✅  Remote origin already correct.", "success")
            else:
                self._log("Adding remote: {}".format(repo_url), "info")
                self._git("remote", "add", "origin", repo_url)
            branch, _ = self._git_out("rev-parse", "--abbrev-ref", "HEAD")
            self._log("✅  Ready. Branch: {}  →  click '3 – Push'.".format(
                branch or "master"), "success")
            return

        # Fresh init
        gi = SCRIPT_DIR / ".gitignore"
        if not gi.exists():
            gi.write_text(
                "# Build artifacts\nbuild/\ndist/\n*.spec\n\n"
                "# Generated EXE\n*.exe\n\n"
                "# Python cache\n*.pyc\n__pycache__/\n\n"
                "# Scratch files\n_slideshow_debug.txt\n"
                "_wallpaper_slideshow.py\n_wallpaper_remind.py\n"
                "_lockscreen_helper.py\n",
                encoding="utf-8")
            self._log("Created .gitignore", "info")

        self._git("init")
        self._git("add", "-A")
        rc = self._git("commit", "-m",
                       "Initial commit — QiGor Wallpaper Manager v{}".format(
                           read_app_versions()[0]))
        if rc != 0:
            self._log("Commit failed — set git user.name / user.email first:", "error")
            self._log("  git config --global user.name 'Your Name'", "warning")
            self._log("  git config --global user.email 'you@example.com'", "warning")
            return

        self._git("remote", "add", "origin", repo_url)
        branch, _ = self._git_out("rev-parse", "--abbrev-ref", "HEAD")
        self._log("", "info")
        self._log("✅  Setup complete!  Branch: {}".format(branch or "master"), "success")
        self._log("Click '3 – Push' to publish.", "info")

    def _do_git_commit(self):
        self._section("GIT COMMIT")
        out, _ = self._git_out("status", "--short")
        if not out:
            self._log("Nothing changed — working tree is clean.", "warning")
            return
        self._log("Changes:\n{}".format(out), "info")
        self._git("add", "-A")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        rc = self._git("commit", "-m", "Update {}".format(stamp))
        if rc == 0:
            self._log("✅  Committed. Click '3 – Push' to publish.", "success")
        else:
            self._log("Commit failed.", "error")

    def _do_git_push(self):
        self._section("GIT PUSH")
        # Detect the actual current branch name
        branch, rc = self._git_out("rev-parse", "--abbrev-ref", "HEAD")
        if rc != 0 or not branch:
            branch = "master"
        self._log("Branch: {}".format(branch), "info")
        self._log("Pushing to github.com/{}/{}...".format(
            GITHUB_USER, GITHUB_REPO), "info")
        rc = self._git("push", "-u", "origin", branch)
        if rc == 0:
            self._log("✅  Push complete!", "success")
            self._log("  https://github.com/{}/{}".format(
                GITHUB_USER, GITHUB_REPO), "success")
        else:
            self._log("Push failed — see output above.", "error")
            self._log("Common causes:", "warning")
            self._log("  • Token doesn't have repo push access", "warning")
            self._log("  • Remote URL incorrect — check '4 – Status'", "warning")

    def _do_git_status(self):
        self._section("GIT STATUS")
        out, _ = self._git_out("remote", "-v")
        self._log("Remote:  {}".format(out or "none"), "info")
        out, _ = self._git_out("log", "--oneline", "-5")
        self._log("Last 5 commits:\n{}".format(out or "  (none)"), "info")
        out, _ = self._git_out("status", "--short")
        if out:
            self._log("Uncommitted changes:\n{}".format(out), "warning")
        else:
            self._log("Working tree is clean.", "success")

    def _view_release(self):
        import webbrowser
        webbrowser.open("https://github.com/{}/{}/releases/latest".format(
            GITHUB_USER, GITHUB_REPO))

    # ── Clean ─────────────────────────────────────────────────────────────────

    def _clean(self):
        removed = []
        for p in (SETUP_STAGE,) + LEGACY_ARTIFACTS:
            pp = Path(p)
            if pp.exists():
                if pp.is_dir():
                    shutil.rmtree(pp, ignore_errors=True)
                else:
                    pp.unlink()
                removed.append(pp.name)
        if removed:
            self._log("🧹  Removed: {}".format(", ".join(removed)), "info")
        else:
            self._log("Nothing to clean.", "info")

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        if self._busy:
            if not messagebox.askokcancel("Busy", "Operation running. Exit anyway?"):
                return
        self.cfg.set("window_geometry", self.root.geometry())
        self.cfg.set("github_token", self._token_var.get().strip())
        self.root.destroy()


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
