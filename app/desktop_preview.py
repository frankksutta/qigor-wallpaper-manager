"""
desktop_preview.py  —  QiGor Wallpaper Manager
Desktop preview: snapshot all visible windows, minimize everything,
show a floating countdown widget, then restore exactly as before.

Uses GetWindowPlacement / SetWindowPlacement which captures and restores
maximized/normal/minimized state + exact position in a single call.
Immune to Win+D or accidental clicks corrupting the restore state —
we own the snapshot, Windows can't touch it.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import tkinter as tk
from tkinter import ttk

# ── Win32 constants ───────────────────────────────────────────────────────────
SW_HIDE             = 0
SW_SHOWNORMAL       = 1
SW_SHOWMINIMIZED    = 2
SW_SHOWMAXIMIZED    = 3
SW_RESTORE          = 9
WS_VISIBLE          = 0x10000000
GW_OWNER            = 4

user32 = ctypes.windll.user32

# WINDOWPLACEMENT structure
class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length",           ctypes.c_uint),
        ("flags",            ctypes.c_uint),
        ("showCmd",          ctypes.c_uint),
        ("ptMinPosition",    ctypes.wintypes.POINT),
        ("ptMaxPosition",    ctypes.wintypes.POINT),
        ("rcNormalPosition", ctypes.wintypes.RECT),
    ]


# ── Window enumeration ────────────────────────────────────────────────────────

def _is_real_window(hwnd: int) -> bool:
    """Return True if hwnd is a visible, non-minimized, top-level app window."""
    if not user32.IsWindowVisible(hwnd):
        return False
    # Must have no owner (owned windows are child dialogs etc.)
    if user32.GetWindow(hwnd, GW_OWNER):
        return False
    # Must have WS_VISIBLE style
    style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
    if not (style & WS_VISIBLE):
        return False
    # Skip windows with no title (system/background windows)
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return False
    return True


def _get_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd) + 1
    buf = ctypes.create_unicode_buffer(length)
    user32.GetWindowTextW(hwnd, buf, length)
    return buf.value


def _get_placement(hwnd: int) -> WINDOWPLACEMENT:
    wp = WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(WINDOWPLACEMENT)
    user32.GetWindowPlacement(hwnd, ctypes.byref(wp))
    return wp


def snapshot_windows(exclude_hwnd: int = 0) -> list[dict]:
    """
    Enumerate all real visible windows and capture their placement.
    exclude_hwnd: skip this window (the QiGor main window).
    Returns list of dicts with hwnd, title, placement.
    """
    results = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def _callback(hwnd, _):
        if hwnd == exclude_hwnd:
            return True
        if _is_real_window(hwnd):
            wp = _get_placement(hwnd)
            # Only snapshot windows that are currently visible (not already minimized)
            if wp.showCmd != SW_SHOWMINIMIZED:
                results.append({
                    "hwnd":      hwnd,
                    "title":     _get_title(hwnd),
                    "placement": wp,
                })
        return True

    user32.EnumWindows(_callback, 0)
    return results


def minimize_windows(snapshot: list[dict]):
    """Minimize all windows in the snapshot."""
    for w in snapshot:
        if user32.IsWindow(w["hwnd"]):
            user32.ShowWindow(w["hwnd"], SW_SHOWMINIMIZED)


def restore_windows(snapshot: list[dict]):
    """
    Restore all windows in snapshot to their exact prior placement.
    Silently skips windows that were closed during preview.
    """
    for w in reversed(snapshot):   # restore in reverse order (back to front)
        hwnd = w["hwnd"]
        if not user32.IsWindow(hwnd):
            continue    # window was closed during preview — skip silently
        wp = w["placement"]
        user32.SetWindowPlacement(hwnd, ctypes.byref(wp))


# ── Floating countdown widget ─────────────────────────────────────────────────

COUNTDOWN_SECONDS  = 10
EXTEND_SECONDS     = 10
PULSE_INTERVAL_MS  = 800   # how often the border pulses
TICK_INTERVAL_MS   = 100   # timer resolution


class DesktopPreviewOverlay:
    """
    Small always-on-top floating widget shown during desktop preview.
    Shows countdown, Restore Now button, and +10s extension.
    Pulses its border so user knows it's QiGor, not Windows.
    """

    def __init__(self, root: tk.Tk, snapshot: list[dict],
                 on_restore_callback,
                 countdown: int = COUNTDOWN_SECONDS):
        self._root         = root
        self._snapshot     = snapshot
        self._on_restore   = on_restore_callback
        self._remaining_ms = countdown * 1000
        self._restored     = False
        self._pulse_state  = False

        self._win = win = tk.Toplevel(root)
        win.withdraw()
        win.overrideredirect(True)          # no title bar
        win.attributes("-topmost", True)    # always on top
        win.attributes("-alpha", 0.92)
        win.configure(bg="#1a1a2e")

        # ── Layout ────────────────────────────────────────────────────────────
        pad = tk.Frame(win, bg="#1a1a2e", padx=12, pady=8)
        pad.pack()

        # Title
        tk.Label(pad, text="🖼  QiGor  —  Desktop Preview",
                 font=("Segoe UI", 10, "bold"),
                 bg="#1a1a2e", fg="#d4d4d4").pack(anchor=tk.W)

        # Progress bar
        self._progress_var = tk.DoubleVar(value=100.0)
        self._bar = ttk.Progressbar(pad, variable=self._progress_var,
                                    maximum=100.0, length=260,
                                    mode="determinate")
        self._bar.pack(fill=tk.X, pady=(6, 2))

        # Countdown label
        self._label_var = tk.StringVar()
        self._update_label()
        tk.Label(pad, textvariable=self._label_var,
                 font=("Segoe UI", 9), bg="#1a1a2e",
                 fg="#888888").pack(anchor=tk.CENTER)

        # Buttons
        btn_row = tk.Frame(pad, bg="#1a1a2e")
        btn_row.pack(pady=(8, 2))

        self._restore_btn = tk.Button(
            btn_row, text="▶  Restore Now",
            font=("Segoe UI", 10, "bold"),
            bg="#1a6b2e", fg="#ffffff",
            activebackground="#1e8038",
            relief=tk.FLAT, padx=12, pady=4,
            cursor="hand2",
            command=self._do_restore)
        self._restore_btn.pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            btn_row, text="+{}s".format(EXTEND_SECONDS),
            font=("Segoe UI", 10),
            bg="#0e639c", fg="#ffffff",
            activebackground="#1177bb",
            relief=tk.FLAT, padx=8, pady=4,
            cursor="hand2",
            command=self._extend).pack(side=tk.LEFT)

        # Make draggable
        win.bind("<ButtonPress-1>",   self._drag_start)
        win.bind("<B1-Motion>",       self._drag_move)

        # Position bottom-center above taskbar
        self._position_widget()
        win.deiconify()

        # Start ticking
        self._total_ms = self._remaining_ms
        self._tick()
        self._pulse()

    def _position_widget(self):
        self._win.update_idletasks()
        w = self._win.winfo_reqwidth()
        h = self._win.winfo_reqheight()
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        taskbar_height = 48   # approximate
        x = (sw - w) // 2
        y = sh - h - taskbar_height - 10
        self._win.geometry("+{}+{}".format(x, y))

    def _update_label(self):
        secs = max(0, self._remaining_ms // 1000)
        self._label_var.set("Auto-restoring in {}s".format(secs))

    def _tick(self):
        if self._restored:
            return
        self._remaining_ms -= TICK_INTERVAL_MS
        if self._remaining_ms <= 0:
            self._do_restore()
            return
        # Update progress bar
        pct = (self._remaining_ms / self._total_ms) * 100.0
        self._progress_var.set(pct)
        self._update_label()
        self._win.after(TICK_INTERVAL_MS, self._tick)

    def _pulse(self):
        """Gently flash the widget border to signal it's QiGor, not Windows."""
        if self._restored:
            return
        self._pulse_state = not self._pulse_state
        color = "#0e639c" if self._pulse_state else "#1a1a2e"
        self._win.configure(bg=color)
        self._win.after(PULSE_INTERVAL_MS, self._pulse)

    def _extend(self):
        self._remaining_ms += EXTEND_SECONDS * 1000
        self._total_ms = max(self._total_ms, self._remaining_ms)
        self._update_label()

    def _do_restore(self):
        if self._restored:
            return
        self._restored = True
        try:
            self._win.destroy()
        except Exception:
            pass
        self._on_restore()

    # ── Drag support ──────────────────────────────────────────────────────────
    def _drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_move(self, event):
        x = self._win.winfo_x() + (event.x - self._drag_x)
        y = self._win.winfo_y() + (event.y - self._drag_y)
        self._win.geometry("+{}+{}".format(x, y))


# ── Public entry point ────────────────────────────────────────────────────────

def start_preview(root: tk.Tk, main_hwnd: int):
    """
    Entry point called from App.
    1. Snapshot all visible windows (excluding QiGor).
    2. Minimize everything.
    3. Show the countdown overlay.
    4. On restore: SetWindowPlacement on each saved window, re-show QiGor.
    """
    snapshot = snapshot_windows(exclude_hwnd=main_hwnd)

    # Minimize all captured windows
    minimize_windows(snapshot)

    # Minimize QiGor's own window
    user32.ShowWindow(main_hwnd, SW_SHOWMINIMIZED)

    def on_restore():
        # Restore all snapshotted windows
        restore_windows(snapshot)
        # Restore QiGor
        user32.ShowWindow(main_hwnd, SW_RESTORE)
        user32.SetForegroundWindow(main_hwnd)

    # Show overlay — root needed for Toplevel parent
    DesktopPreviewOverlay(root, snapshot, on_restore)
