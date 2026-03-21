#!/usr/bin/env pythonw
# -*- coding: utf-8 -*-
"""
qigor_wallpaper_manager.pyw  —  QiGor Wallpaper Manager v0.7
Entry point only. All logic lives in app/.
"""
import os
import sys
import ctypes as _ct
from pathlib import Path

# ── Ensure app/ package is importable ────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))

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

# ── Create root window ────────────────────────────────────────────────────────
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
