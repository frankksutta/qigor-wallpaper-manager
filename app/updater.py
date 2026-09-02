"""
updater.py  —  QiGor Wallpaper Manager

Check GitHub for a newer release, download it, and hand it to the installer.

The whole update is one shape: download the setup zip, extract it to a temp
folder, and have the *staged* copy's interpreter reinstall over this one. A
process can never overwrite the CPython DLLs it is running from, so an in-place
patch could only ever update app/ and would break the moment the bundled Python
version changed. Letting the new copy do the copying handles both cases with a
single code path — and it is the same `installer.core.install()` a first-time
user runs, so there is only one install routine to keep correct.

No GitHub API and no token: the plain releases/latest/download URLs are
unauthenticated, have no rate limit, and redirect to the CDN. Integrity comes
from the SHA-256 published in version.json, which arrives over the same TLS
connection to github.com.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from .constants import (APP_NAME, APP_BUILD, RELEASE_BASE, RELEASE_PAGE,
                        SETUP_ASSET, MANIFEST_ASSET, UPDATE_INTERVAL_HOURS,
                        THEMES, BTN_COLORS, CONSOLE_COLORS)

USER_AGENT = "{}/{} (+{})".format(APP_NAME.replace(" ", ""), APP_BUILD, RELEASE_PAGE)
NET_TIMEOUT = 15


class UpdateError(Exception):
    pass


# ── Talking to GitHub ─────────────────────────────────────────────────────────

def _open(url, timeout=NET_TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_manifest(timeout=NET_TIMEOUT) -> dict:
    """
    Read version.json from the latest release.

    It carries the build number, the setup zip's SHA-256 and size, and the
    release notes — so a check costs one small request and the version does not
    have to be smuggled into a filename or a git tag.
    """
    url = "{}/{}".format(RELEASE_BASE, MANIFEST_ASSET)
    try:
        with _open(url, timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError(
                "The latest release has no {} — it was published without one, "
                "or there are no releases yet.".format(MANIFEST_ASSET))
        raise UpdateError("GitHub returned HTTP {}.".format(e.code))
    except urllib.error.URLError as e:
        raise UpdateError("Could not reach github.com ({}).".format(e.reason))
    except json.JSONDecodeError:
        raise UpdateError("The release manifest is not valid JSON.")


def is_newer(candidate: str, current: str = APP_BUILD) -> bool:
    """Reuse the installer's comparison so both sides agree on ordering."""
    from installer.core import is_newer as _is_newer
    return _is_newer(candidate, current)


def check(timeout=NET_TIMEOUT) -> "dict | None":
    """Return the manifest if it describes a newer build, else None."""
    meta = fetch_manifest(timeout)
    build = str(meta.get("build") or "")
    if not build:
        raise UpdateError("The release manifest has no build number.")
    return meta if is_newer(build) else None


# ── Downloading ───────────────────────────────────────────────────────────────

def download(meta: dict, dest: Path, progress=None,
             cancel: "threading.Event | None" = None) -> Path:
    """
    Fetch the setup zip to `dest` and verify its SHA-256.

    `progress(done_bytes, total_bytes)` is called as it goes; total is 0 when
    the server sends no Content-Length.
    """
    url = meta.get("url") or "{}/{}".format(RELEASE_BASE,
                                            meta.get("asset", SETUP_ASSET))
    want = str(meta.get("sha256") or "").lower().strip()
    dest = Path(dest)

    digest = hashlib.sha256()
    done = 0
    try:
        with _open(url) as r:
            total = int(r.headers.get("Content-Length") or 0)
            with open(dest, "wb") as f:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise UpdateError("Download cancelled.")
                    chunk = r.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except urllib.error.HTTPError as e:
        raise UpdateError("Download failed: HTTP {}.".format(e.code))
    except urllib.error.URLError as e:
        raise UpdateError("Download failed: {}.".format(e.reason))

    got = digest.hexdigest()
    if want and got != want:
        dest.unlink(missing_ok=True)
        raise UpdateError(
            "The download did not match its published checksum, so it was "
            "discarded.\n\nExpected {}…\nGot      {}…".format(want[:16], got[:16]))
    if not want:
        raise UpdateError(
            "The release publishes no checksum for this file, so it cannot be "
            "verified. Update manually from the releases page instead.")
    return dest


# ── Applying ──────────────────────────────────────────────────────────────────

def _staged_payload(extract_dir: Path) -> Path:
    """
    The zip holds one top-level folder; return it, tolerating a flat zip.
    """
    entries = [p for p in extract_dir.iterdir()]
    dirs    = [p for p in entries if p.is_dir()]
    if len(dirs) == 1 and not any(p.is_file() for p in entries):
        return dirs[0]
    return extract_dir


def target_root() -> Path:
    """
    Where to install the update.

    An installed copy updates itself in place at the per-user install root; a
    portable folder that was never installed updates the folder it is running
    from, so "check for updates" works either way.
    """
    from installer.paths import install_root, payload_root, is_installed_copy
    root = payload_root()
    return install_root() if is_installed_copy(root) else root


def apply(zip_path: Path, log=None) -> None:
    """
    Extract the setup zip and hand off to the staged installer.

    Returns once the handoff process is running. The caller must then close the
    app promptly: the installer waits for this PID to exit before it starts
    copying, and relaunches afterwards.
    """
    from installer.core import validate_payload, CREATE_NO_WINDOW, DETACHED_PROCESS

    def say(m):
        if log:
            log(m)

    stage = Path(tempfile.mkdtemp(prefix="qigor-update-"))
    say("Extracting to {}".format(stage))
    try:
        with zipfile.ZipFile(zip_path) as z:
            _safe_extract(z, stage)
    except zipfile.BadZipFile:
        shutil.rmtree(stage, ignore_errors=True)
        raise UpdateError("The downloaded file is not a valid zip archive.")

    payload = _staged_payload(stage)
    err = validate_payload(payload)
    if err:
        shutil.rmtree(stage, ignore_errors=True)
        raise UpdateError("The downloaded release looks incomplete. " + err)

    # The zip has served its purpose now that it is unpacked, and this is the
    # last moment anything can delete it — after the handoff this process exits.
    # Only ever the private temp folder download() was given, never whatever
    # directory a caller happened to pass a zip from.
    dl_dir = Path(zip_path).parent
    if (dl_dir.name.startswith("qigor-dl-")
            and dl_dir.parent == Path(tempfile.gettempdir())):
        shutil.rmtree(dl_dir, ignore_errors=True)

    target = target_root()
    runner = payload / "runtime" / "pythonw.exe"
    cmd = [str(runner), str(payload / "installer" / "install.py"),
           "--silent", "--target", str(target),
           "--wait-pid", str(os.getpid()), "--relaunch",
           # It cannot delete the folder it is running from while it runs, so
           # it queues the removal for after it exits.
           "--cleanup", str(stage)]
    say("Handing off to the staged installer…")
    subprocess.Popen(cmd, cwd=str(payload), close_fds=True,
                     creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW)


def _safe_extract(z: zipfile.ZipFile, dest: Path):
    """
    Extract with path traversal refused.

    The archive comes from our own release, but it arrived over the network and
    an archive that writes outside its destination is the one thing a zip can
    do that a plain download cannot.
    """
    dest = dest.resolve()
    for member in z.infolist():
        out = (dest / member.filename).resolve()
        if not str(out).startswith(str(dest)):
            raise UpdateError(
                "The archive contains an entry outside the extraction folder "
                "({}) and was rejected.".format(member.filename))
    z.extractall(dest)


# ── Scheduling the background check ───────────────────────────────────────────

def due_for_check(cfg) -> bool:
    if not cfg.get("update_check_enabled"):
        return False
    last = cfg.get("update_last_check")
    if not last:
        return True
    try:
        return datetime.now() - datetime.fromisoformat(last) > timedelta(
            hours=UPDATE_INTERVAL_HOURS)
    except ValueError:
        return True


def background_check(app):
    """
    Poll once, quietly. Any failure is logged and forgotten — a missing network
    is not something to interrupt someone's desktop over.
    """
    try:
        meta = check()
    except UpdateError as e:
        app.root.after(0, lambda: app._log("Update check skipped: {}".format(e), "dim"))
        return
    except Exception:
        return

    app.cfg.set("update_last_check", datetime.now().isoformat(timespec="seconds"))
    if not meta:
        return
    if meta.get("build") == app.cfg.get("update_skip_build"):
        return
    app.root.after(0, lambda: UpdateDialog(app, meta).show())


# ── Dialog ────────────────────────────────────────────────────────────────────

class UpdateDialog(tk.Toplevel):
    """
    One window for the whole flow: what's new → download with progress →
    restart. `meta` is the release manifest, or None to check on open.
    """

    def __init__(self, app, meta: "dict | None" = None):
        super().__init__(app.root)
        self.app    = app
        self.meta   = meta
        self.cancel = threading.Event()
        self.zip    = None
        self.busy   = False

        t = THEMES.get(app.theme_name, THEMES["dark"])
        dim = CONSOLE_COLORS[app.theme_name]["dim"]
        fs  = app.font_size
        self.t, self.dim = t, dim

        self.title("Updates — {}".format(APP_NAME))
        self.configure(bg=t["bg"])
        self.geometry("560x420")
        self.minsize(500, 380)
        self.transient(app.root)
        self.grab_set()

        pad = dict(padx=20)
        self._head = tk.Label(self, text="Checking for updates…", bg=t["bg"],
                              fg=t["fg"], font=("Segoe UI", 14, "bold"),
                              anchor="w")
        self._head.pack(fill="x", pady=(18, 4), **pad)

        self._sub = tk.Label(self, text="Installed build {}".format(APP_BUILD),
                             bg=t["bg"], fg=dim, font=("Segoe UI", fs - 1),
                             anchor="w")
        self._sub.pack(fill="x", **pad)

        self._notes = tk.Text(self, bg=t["console_bg"], fg=t["console_fg"],
                              font=("Segoe UI", fs), relief="flat", wrap="word",
                              height=8, padx=10, pady=8)
        self._notes.pack(fill="both", expand=True, pady=(14, 8), **pad)
        self._notes.configure(state="disabled")

        self._bar = ttk.Progressbar(self, mode="determinate", maximum=1000)
        self._pct = tk.Label(self, text="", bg=t["bg"], fg=dim,
                             font=("Segoe UI", fs - 1), anchor="w")

        self._auto = tk.BooleanVar(value=bool(app.cfg.get("update_check_enabled")))
        tk.Checkbutton(self, text="Check for updates automatically",
                       variable=self._auto, command=self._toggle_auto,
                       bg=t["bg"], fg=t["fg"], selectcolor=t["console_bg"],
                       activebackground=t["bg"], activeforeground=t["fg"],
                       highlightthickness=0, font=("Segoe UI", fs - 1)
                       ).pack(anchor="w", pady=(0, 6), **pad)

        bar = tk.Frame(self, bg=t["bg"])
        bar.pack(fill="x", pady=(0, 16), **pad)
        c = BTN_COLORS["primary"]
        self._ok = tk.Button(bar, text="Close", bg=c["bg"], fg=c["fg"],
                             activebackground=c["active"], relief="flat",
                             font=("Segoe UI", fs, "bold"), width=18,
                             cursor="hand2", command=self._primary)
        self._ok.pack(side="right")
        self._alt = tk.Button(bar, text="Not now", bg=t["btn_bg"], fg=t["btn_fg"],
                              relief="flat", font=("Segoe UI", fs), width=12,
                              command=self.destroy)
        self._alt.pack(side="right", padx=(0, 8))
        self._alt.pack_forget()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── public ────────────────────────────────────────────────────────────────

    def show(self):
        if self.meta:
            self._render_available()
        else:
            threading.Thread(target=self._do_check, daemon=True).start()
        return self

    # ── helpers ───────────────────────────────────────────────────────────────

    def _set_notes(self, text):
        self._notes.configure(state="normal")
        self._notes.delete("1.0", "end")
        self._notes.insert("1.0", text)
        self._notes.configure(state="disabled")

    def _toggle_auto(self):
        self.app.cfg.set("update_check_enabled", bool(self._auto.get()))

    def _on_close(self):
        self.cancel.set()
        self.destroy()

    # ── states ────────────────────────────────────────────────────────────────

    def _do_check(self):
        try:
            meta = check()
        except UpdateError as e:
            self.after(0, lambda: self._render_error(str(e)))
            return
        except Exception as e:
            self.after(0, lambda: self._render_error(str(e)))
            return
        self.app.cfg.set("update_last_check",
                         datetime.now().isoformat(timespec="seconds"))
        if meta is None:
            self.after(0, self._render_current)
        else:
            self.meta = meta
            self.after(0, self._render_available)

    def _render_current(self):
        self._head.configure(text="You're up to date")
        self._sub.configure(text="Installed build {} — the newest published "
                                 "release.".format(APP_BUILD))
        self._set_notes("Nothing to install.\n\nReleases are published at:\n{}"
                        .format(RELEASE_PAGE))
        self._ok.configure(text="Close", command=self.destroy)

    def _render_error(self, msg):
        self._head.configure(text="Could not check for updates")
        self._sub.configure(text="Installed build {}".format(APP_BUILD))
        self._set_notes("{}\n\nYou can always download the latest release "
                        "yourself:\n{}".format(msg, RELEASE_PAGE))
        self._ok.configure(text="Close", command=self.destroy)

    def _render_available(self):
        m = self.meta
        size = m.get("size") or 0
        self._head.configure(text="Version {} is available".format(m.get("build")))
        self._sub.configure(text="You have build {}{}".format(
            APP_BUILD,
            "   •   download {:.0f} MB".format(size / 1e6) if size else ""))
        notes = (m.get("notes") or "").strip() or "No release notes were published."
        if m.get("runtime"):
            notes += "\n\nBundled Python: {}".format(m["runtime"])
        self._set_notes(notes)
        self._ok.configure(text="Download and install", command=self._primary)
        self._alt.pack(side="right", padx=(0, 8))

    def _render_progress(self):
        self._bar.pack(fill="x", pady=(0, 2), padx=20)
        self._pct.pack(fill="x", padx=20)
        self._ok.configure(text="Cancel", command=self._on_close)
        self._alt.pack_forget()

    # ── the actual work ───────────────────────────────────────────────────────

    def _primary(self):
        if self.busy or not self.meta:
            self.destroy()
            return
        self.busy = True
        self._head.configure(text="Downloading version {}…".format(
            self.meta.get("build")))
        self._render_progress()
        threading.Thread(target=self._do_download, daemon=True).start()

    def _do_download(self):
        tmp = Path(tempfile.mkdtemp(prefix="qigor-dl-")) / SETUP_ASSET

        def progress(done, total):
            if total:
                self.after(0, lambda: self._bar.configure(
                    value=int(done / total * 1000)))
                self.after(0, lambda: self._pct.configure(
                    text="{:.1f} MB of {:.1f} MB".format(done / 1e6, total / 1e6)))
            else:
                self.after(0, lambda: self._pct.configure(
                    text="{:.1f} MB".format(done / 1e6)))

        try:
            download(self.meta, tmp, progress=progress, cancel=self.cancel)
        except UpdateError as e:
            shutil.rmtree(tmp.parent, ignore_errors=True)
            self.busy = False
            self.after(0, lambda: self._render_error(str(e)))
            return

        self.after(0, lambda: self._finish(tmp))

    def _finish(self, zip_path: Path):
        self._head.configure(text="Ready to install")
        self._pct.configure(text="Verified.")
        self._set_notes(
            "QiGor will close, install version {}, and reopen.\n\n"
            "If the slideshow is running it keeps its schedule — the "
            "scheduled task points at a path that does not move.".format(
                self.meta.get("build")))
        self._ok.configure(text="Install and restart",
                           command=lambda: self._install(zip_path))
        self._alt.configure(text="Later", command=self.destroy)
        self._alt.pack(side="right", padx=(0, 8))
        self.busy = False

    def _install(self, zip_path: Path):
        self._ok.configure(state="disabled", text="Installing…")
        try:
            apply(zip_path, log=lambda m: self.app._log(m, "dim"))
        except UpdateError as e:
            self._ok.configure(state="normal")
            self._render_error(str(e))
            return
        # The staged installer is waiting on this PID before it copies.
        self.app.root.after(300, self.app.root.destroy)
