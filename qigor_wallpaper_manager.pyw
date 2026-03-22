#!/usr/bin/env pythonw
# -*- coding: utf-8 -*-
"""
qigor_wallpaper_manager.pyw  —  QiGor Wallpaper Manager v0.7
Entry point. Handles both GUI mode and headless helper modes.

Headless modes (no GUI, called by Task Scheduler or UAC elevation):
  --next                        advance slideshow to next image
  --remind                      show wallpaper reminder toast
  --set-lockscreen "path"       set lock screen image (runs elevated)
  --release-lockscreen          remove PersonalizationCSP (runs elevated)
"""
import os
import sys
import ctypes as _ct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Headless modes — handle before any GUI or lock file ───────────────────────
if "--next" in sys.argv:
    from app.slideshow import _run_next_headless
    _run_next_headless()
    sys.exit(0)

if "--remind" in sys.argv:
    from app.remind_headless import show_reminder_toast
    show_reminder_toast()
    sys.exit(0)

if "--set-lockscreen" in sys.argv:
    from app.wallpaper import _set_lockscreen_headless
    idx = sys.argv.index("--set-lockscreen")
    path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
    _set_lockscreen_headless(path)
    sys.exit(0)

if "--release-lockscreen" in sys.argv:
    from app.wallpaper import _release_lockscreen_headless
    _release_lockscreen_headless()
    sys.exit(0)

from app.constants import APP_NAME, APP_VERSION, APP_SLUG

# ── Single-instance enforcement ───────────────────────────────────────────────
_lock_dir  = Path.home() / f".{APP_SLUG}"
_lock_dir.mkdir(parents=True, exist_ok=True)
_lock_file = _lock_dir / "instance.lock"

try:
    _lock_fd = open(_lock_file, "w")
    import msvcrt
    msvcrt.locking(_lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
    _lock_fd.write(str(os.getpid()))
    _lock_fd.flush()
except (IOError, OSError):
    _hwnd = 0
    for _title in [f"{APP_NAME}  v{APP_VERSION}",
                   f"{APP_NAME}  v{APP_VERSION}  [Administrator]"]:
        _hwnd = _ct.windll.user32.FindWindowW(None, _title)
        if _hwnd:
            break
    if _hwnd:
        _ct.windll.user32.ShowWindow(_hwnd, 9)
        _ct.windll.user32.SetForegroundWindow(_hwnd)
    sys.exit(0)

# ── GUI mode ──────────────────────────────────────────────────────────────────
import tkinter as tk
try:
    from tkinterdnd2 import TkinterDnD
    root = TkinterDnD.Tk()
except Exception:
    root = tk.Tk()

from app.app import App
App(root)
root.mainloop()

# ── Release lock on clean exit ────────────────────────────────────────────────
try:
    import msvcrt
    msvcrt.locking(_lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
    _lock_fd.close()
    _lock_file.unlink(missing_ok=True)
except Exception:
    pass
