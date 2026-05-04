"""
slideshow.py  —  QiGor Wallpaper Manager
Wallpaper slideshow via Windows Task Scheduler.

A helper script is written to HELPERS_DIR (~/.qigor-wallpaper/helpers/)
and scheduled via schtasks. It runs on a timer, picks the next image,
sets it, updates state, and exits. No persistent background process.

State: ~/.qigor-wallpaper/slideshow_state.json
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path

from .constants import THEMES, BTN_COLORS, CONSOLE_COLORS, STORE_DIR, WALLPAPER_STYLES, HELPERS_DIR, APP_BUILD
from .wallpaper import find_python_exe

TASK_NAME  = "QiGorWallpaperSlideshow"
STATE_FILE = Path.home() / ".qigor-wallpaper" / "slideshow_state.json"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif"}

INTERVAL_OPTIONS = [
    ("1 min",   1),
    ("5 min",   5),
    ("10 min",  10),
    ("15 min",  15),
    ("30 min",  30),
    ("1 hour",  60),
    ("2 hours", 120),
    ("4 hours", 240),
    ("8 hours", 480),
    ("Daily",   1440),
]


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_images_in_folder(folder: Path) -> list:
    try:
        return sorted(
            f.name for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        )
    except Exception:
        return []


def is_scheduled() -> bool:
    try:
        r = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"],
            capture_output=True, text=True, timeout=8)
        return r.returncode == 0
    except Exception:
        return False


def query_task_status() -> str:
    try:
        r = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"],
            capture_output=True, text=True, timeout=8)
        if r.returncode != 0:
            return "Not scheduled."
        lines = {k.strip(): v.strip()
                 for line in r.stdout.splitlines()
                 if ":" in line
                 for k, v in [line.split(":", 1)]}
        return "Task: {}  •  Next: {}  •  Last ran: {}".format(
            lines.get("Status", "?"),
            lines.get("Next Run Time", "?"),
            lines.get("Last Run Time", "Never"))
    except Exception as e:
        return "Could not query task: {}".format(e)


def remove_task() -> bool:
    try:
        r = subprocess.run(
            ["schtasks", "/delete", "/f", "/tn", TASK_NAME],
            capture_output=True, text=True)
        # Remove legacy on-logon catch-up task if present (ignore error if absent)
        subprocess.run(
            ["schtasks", "/delete", "/f", "/tn", TASK_NAME + "_OnLogon"],
            capture_output=True, text=True)
        return r.returncode == 0
    except Exception:
        return False





# ── Helper script writer ──────────────────────────────────────────────────────

def write_slideshow_helper() -> Path:
    """
    Write _wallpaper_slideshow.py to HELPERS_DIR (~/.qigor-wallpaper/helpers/).
    Fixed location independent of EXE — task path never goes stale on relocation.
    """
    HELPERS_DIR.mkdir(parents=True, exist_ok=True)
    script = HELPERS_DIR / "_wallpaper_slideshow.py"

    # STATE_FILE path — use raw string literal in the generated script
    sf_str = str(STATE_FILE).replace("\\", "/")  # forward slashes work on Windows

    lines = [
        '#!/usr/bin/env python',
        '"""Wallpaper slideshow helper - run by Windows Task Scheduler."""',
        'import json, os, random, ctypes, winreg, datetime',
        'from pathlib import Path',
        '',
        'STATE_FILE = Path("' + sf_str + '")',
        'IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif"}',
        'LOG_FILE   = STATE_FILE.parent / "_slideshow_log.txt"',
        '',
        'def log(msg):',
        '    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")',
        '    with open(LOG_FILE, "a", encoding="utf-8") as f:',
        '        f.write(ts + "  " + str(msg) + "\\n")',
        '',
        'def load_state():',
        '    try:',
        '        if STATE_FILE.exists():',
        '            return json.loads(STATE_FILE.read_text(encoding="utf-8"))',
        '    except Exception:',
        '        pass',
        '    return {}',
        '',
        'def save_state(s):',
        '    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)',
        '    STATE_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")',
        '',
        'def get_images(folder):',
        '    try:',
        '        return sorted(f.name for f in Path(folder).iterdir()',
        '                      if f.is_file() and f.suffix.lower() in IMAGE_EXTS)',
        '    except Exception:',
        '        return []',
        '',
        'def set_wallpaper(path, style):',
        '    styles = {',
        '        "Fill":    ("10", "0"),',
        '        "Fit":     ("6",  "0"),',
        '        "Stretch": ("2",  "0"),',
        '        "Tile":    ("0",  "1"),',
        '        "Center":  ("0",  "0"),',
        '        "Span":    ("22", "0"),',
        '    }',
        '    sv, tv = styles.get(style, ("10", "0"))',
        '    try:',
        '        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,',
        '            "Control Panel\\\\Desktop", 0, winreg.KEY_SET_VALUE)',
        '        winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, sv)',
        '        winreg.SetValueEx(key, "TileWallpaper",  0, winreg.REG_SZ, tv)',
        '        winreg.CloseKey(key)',
        '    except Exception as e:',
        '        log("Registry error: " + str(e))',
        '    ctypes.windll.user32.SystemParametersInfoW(20, 0, str(path), 3)',
        '',
        'def main():',
        '    log("Slideshow helper started.")',
        '    state = load_state()',
        '    if not state:',
        '        log("ERROR: no state file. Configure slideshow in QiGor app.")',
        '        return',
        '    # Guard: skip if last rotation was less than 90% of the interval ago.',
        '    interval_min = state.get("interval_min", 10)',
        '    last_set_str = state.get("last_set", "")',
        '    if last_set_str:',
        '        try:',
        '            last_set = datetime.datetime.strptime(last_set_str, "%Y-%m-%d %H:%M:%S")',
        '            elapsed_min = (datetime.datetime.now() - last_set).total_seconds() / 60',
        '            if elapsed_min < interval_min * 0.9:',
        '                log("Skipping: only {:.1f} min since last set (interval={}min).".format(',
        '                    elapsed_min, interval_min))',
        '                return',
        '        except Exception:',
        '            pass',
        '    folder  = Path(state.get("folder", ""))',
        '    style   = state.get("style", "Fill")',
        '    shuffle = state.get("shuffle", True)',
        '    if not folder.exists():',
        '        log("ERROR: folder not found: " + str(folder))',
        '        return',
        '    images = get_images(folder)',
        '    if not images:',
        '        log("ERROR: no images in " + str(folder))',
        '        return',
        '    queue = state.get("queue", [])',
        '    index = state.get("queue_index", 0)',
        '    needs_rebuild = (',
        '        not queue',
        '        or index >= len(queue)',
        '        or set(images) != set(queue)',
        '    )',
        '    if needs_rebuild:',
        '        log("Rebuilding queue (" + str(len(images)) + " images)")',
        '        queue = list(images)',
        '        if shuffle:',
        '            random.shuffle(queue)',
        '        index = 0',
        '    chosen = None',
        '    for _ in range(len(queue)):',
        '        candidate = queue[index % len(queue)]',
        '        full_path = folder / candidate',
        '        index = (index + 1) % len(queue)',
        '        if full_path.exists():',
        '            chosen = full_path',
        '            break',
        '        log("Skipping missing: " + candidate)',
        '    if not chosen:',
        '        log("ERROR: all files in queue are missing.")',
        '        return',
        '    log("Setting: " + chosen.name + " (style=" + style + ")")',
        '    set_wallpaper(chosen, style)',
        '    state["queue"]       = queue',
        '    state["queue_index"] = index',
        '    state["last_set"]    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")',
        '    state["last_file"]   = chosen.name',
        '    save_state(state)',
        '    log("Done. Next index: " + str(index) + "/" + str(len(queue)))',
        '',
        'if __name__ == "__main__":',
        '    main()',
        '',
    ]

    script.write_text("\n".join(lines), encoding="utf-8")
    return script


# ── Scheduler ─────────────────────────────────────────────────────────────────

def _run_next_headless(force: bool = False):
    """
    Headless slideshow advance — called via  exe --next  by Task Scheduler.
    No Python installation required on the target machine.
    Runs entirely within the frozen EXE process.

    force=True bypasses the elapsed-time guard (used by the "Next Now" button).
    """
    import random, ctypes, winreg, datetime as _dt
    from pathlib import Path as _P

    log_file = HELPERS_DIR / "_slideshow_log.txt"
    HELPERS_DIR.mkdir(parents=True, exist_ok=True)

    def log(msg):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "  " + str(msg) + "\n")

    log("--- --next triggered. argv={} force={}".format(sys.argv[1:], force))

    state = load_state()
    if not state:
        log("ERROR: no state file. Configure slideshow in the QiGor app."); return

    interval_min = state.get("interval_min", 10)
    last_set_str = state.get("last_set", "")

    # Guard: skip if last rotation was less than 90% of the interval ago.
    # Prevents StartWhenAvailable catch-up from double-firing right after a
    # normal on-time fire.  force=True bypasses (used by "Next Now" button).
    if not force:
        if last_set_str:
            try:
                last_set    = _dt.datetime.strptime(last_set_str, "%Y-%m-%d %H:%M:%S")
                elapsed_min = (_dt.datetime.now() - last_set).total_seconds() / 60
                threshold   = interval_min * 0.9
                log("Guard: elapsed={:.1f}min  threshold={:.1f}min (90% of {}min)  last_set={}".format(
                    elapsed_min, threshold, interval_min, last_set_str))
                if elapsed_min < threshold:
                    log("Skipping: too soon.")
                    return
            except Exception as e:
                log("Guard parse error (proceeding): {}".format(e))
        else:
            log("Guard: no last_set yet — proceeding.")
    else:
        log("Force=True, bypassing guard.")

    folder  = _P(state.get("folder", ""))
    style   = state.get("style", "Fill")
    shuffle = state.get("shuffle", True)

    if not folder.exists():
        log("ERROR: folder not found: " + str(folder)); return

    images = get_images_in_folder(folder)
    if not images:
        log("ERROR: no images in " + str(folder)); return

    queue = state.get("queue", [])
    index = state.get("queue_index", 0)

    if not queue or index >= len(queue) or set(images) != set(queue):
        log("Rebuilding queue ({} images)".format(len(images)))
        queue = list(images)
        if shuffle:
            random.shuffle(queue)
        index = 0

    chosen = None
    for _ in range(len(queue)):
        candidate = queue[index % len(queue)]
        full_path = folder / candidate
        index = (index + 1) % len(queue)
        if full_path.exists():
            chosen = full_path
            break
        log("Skipping missing: " + candidate)

    if not chosen:
        log("ERROR: all files in queue are missing."); return

    # Apply wallpaper via registry + ctypes
    styles = {
        "Fill": ("10","0"), "Fit": ("6","0"), "Stretch": ("2","0"),
        "Tile": ("0","1"),  "Center": ("0","0"), "Span": ("22","0"),
    }
    sv, tv = styles.get(style, ("10","0"))
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, sv)
        winreg.SetValueEx(key, "TileWallpaper",  0, winreg.REG_SZ, tv)
        winreg.CloseKey(key)
    except Exception as e:
        log("Registry error: " + str(e))
    ctypes.windll.user32.SystemParametersInfoW(20, 0, str(chosen), 3)

    state["queue"]       = queue
    state["queue_index"] = index
    state["last_set"]    = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["last_file"]   = chosen.name
    save_state(state)
    log("Done: {} ({}/{})".format(chosen.name, index, len(queue)))

    # Query task status so the log shows when the next fire is scheduled
    try:
        r2 = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"],
            capture_output=True, text=True, timeout=8)
        if r2.returncode == 0:
            lines = {}
            for line in r2.stdout.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    lines[k.strip()] = v.strip()
            log("Task: Status={}  NextRun={}  LastRun={}".format(
                lines.get("Status", "?"),
                lines.get("Next Run Time", "?"),
                lines.get("Last Run Time", "?")))
        else:
            log("Task query: not found (task may have been removed).")
    except Exception as e:
        log("Task query failed: {}".format(e))


def schedule_task(interval_min: int):
    """
    Schedule  exe --next  via Task Scheduler XML.
    Uses StartWhenAvailable=true so a fire missed while the machine sleeps
    runs as soon as the machine wakes — no separate OnLogon task needed.
    Returns (success: bool, message: str).
    """
    import datetime as _dt
    import xml.sax.saxutils as _sax

    log_file = HELPERS_DIR / "_slideshow_log.txt"
    HELPERS_DIR.mkdir(parents=True, exist_ok=True)

    def _log(msg):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "  [SETUP] " + str(msg) + "\n")

    try:
        if getattr(sys, "frozen", False):
            cmd_exe  = sys.executable
            cmd_args = "--next"
            runner_desc = sys.executable
        else:
            from .wallpaper import find_python_exe
            py   = find_python_exe()
            pyw  = str(Path(sys.argv[0]).resolve())
            cmd_exe  = py
            cmd_args = '"{}" --next'.format(pyw)
            runner_desc = pyw

        start_boundary = (_dt.datetime.now() +
                          _dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")

        xml_body = (
            '<?xml version="1.0" encoding="UTF-16"?>\n'
            '<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
            '  <RegistrationInfo>\n'
            '    <Description>QiGor Wallpaper Slideshow — rotate every {intv} min</Description>\n'
            '  </RegistrationInfo>\n'
            '  <Triggers>\n'
            '    <TimeTrigger>\n'
            '      <Repetition>\n'
            '        <Interval>PT{intv}M</Interval>\n'
            '        <StopAtDurationEnd>false</StopAtDurationEnd>\n'
            '      </Repetition>\n'
            '      <StartBoundary>{start}</StartBoundary>\n'
            '      <Enabled>true</Enabled>\n'
            '    </TimeTrigger>\n'
            '  </Triggers>\n'
            '  <Principals>\n'
            '    <Principal id="Author">\n'
            '      <LogonType>InteractiveToken</LogonType>\n'
            '      <RunLevel>LeastPrivilege</RunLevel>\n'
            '    </Principal>\n'
            '  </Principals>\n'
            '  <Settings>\n'
            '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
            '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
            '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
            '    <StartWhenAvailable>true</StartWhenAvailable>\n'
            '    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>\n'
            '    <AllowStartOnDemand>true</AllowStartOnDemand>\n'
            '    <Enabled>true</Enabled>\n'
            '    <Hidden>false</Hidden>\n'
            '    <RunOnlyIfIdle>false</RunOnlyIfIdle>\n'
            '    <WakeToRun>false</WakeToRun>\n'
            '    <ExecutionTimeLimit>PT2M</ExecutionTimeLimit>\n'
            '    <Priority>7</Priority>\n'
            '  </Settings>\n'
            '  <Actions Context="Author">\n'
            '    <Exec>\n'
            '      <Command>{cmd}</Command>\n'
            '      <Arguments>{args}</Arguments>\n'
            '    </Exec>\n'
            '  </Actions>\n'
            '</Task>'
        ).format(
            intv=interval_min,
            start=start_boundary,
            cmd=_sax.escape(cmd_exe),
            args=_sax.escape(cmd_args),
        )

        tmp_xml = HELPERS_DIR / "_task_create.xml"
        tmp_xml.write_text(xml_body, encoding="utf-16")
        _log("Creating task: interval={}min  StartWhenAvailable=true  runner={}".format(
            interval_min, runner_desc))

        cmd = ["schtasks", "/create", "/f", "/tn", TASK_NAME, "/xml", str(tmp_xml)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        _log("schtasks rc={}  {}".format(r.returncode, (r.stdout or r.stderr or "").strip()))

        try:
            tmp_xml.unlink()
        except Exception:
            pass

        if r.returncode == 0:
            return True, "Scheduled every {} min (StartWhenAvailable=true).\nRunner: {}".format(
                interval_min, runner_desc)

        err = (r.stderr or r.stdout or "unknown error").strip()
        return False, "schtasks failed (code {}):\n{}\n\nCommand:\n{}".format(
            r.returncode, err, " ".join(cmd))

    except Exception:
        import traceback
        return False, "Exception in schedule_task:\n" + traceback.format_exc()


# ── Dialog ────────────────────────────────────────────────────────────────────

class SlideshowDialog(tk.Toplevel):
    """
    Configure and control the wallpaper slideshow.
    result: "started" | "stopped" | "next" | None
    """

    def __init__(self, parent, cfg, theme_name, font_size):
        super().__init__(parent)
        self.title("Wallpaper Slideshow")
        self.result   = None
        self._cfg     = cfg

        t = THEMES.get(theme_name, THEMES["dark"])
        self.configure(bg=t["bg"])
        self.resizable(True, False)
        self.minsize(500, 0)
        self.grab_set()
        fn  = ("Segoe UI", font_size)
        fnb = ("Segoe UI", font_size, "bold")
        fns = ("Segoe UI", font_size - 1)
        dim = CONSOLE_COLORS[theme_name]["dim"]

        state          = load_state()
        saved_folder   = state.get("folder",       str(STORE_DIR))
        saved_interval = state.get("interval_min", 10)
        saved_shuffle  = state.get("shuffle",      True)
        saved_style    = state.get("style",
                                   cfg.get("wallpaper_style") or "Fill")

        ttk.Sizegrip(self).place(relx=1.0, rely=1.0, anchor="se")

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=t["bg"])
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(4, 12))

        c = BTN_COLORS["success"]
        tk.Button(btn_row, text="▶ Start", height=2, font=fnb,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._start).pack(
                      side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        c = BTN_COLORS["primary"]
        tk.Button(btn_row, text="⏭ Next Now", height=2, font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._next_now).pack(
                      side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        c = BTN_COLORS["warning"]
        tk.Button(btn_row, text="📋 Log", height=2, font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._view_log).pack(
                      side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        c = BTN_COLORS["primary"]
        tk.Button(btn_row, text="⚙ Test Task", height=2, font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._test_task).pack(
                      side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        c = BTN_COLORS["danger"]
        tk.Button(btn_row, text="⏹ Stop", height=2, font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._stop).pack(
                      side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        tk.Button(btn_row, text="Close", height=2, font=fn,
                  bg=t["btn_bg"], fg=t["btn_fg"],
                  command=self.destroy).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=t["bg"])
        body.pack(fill=tk.BOTH, padx=16, pady=(14, 6))

        tk.Label(body, text="Wallpaper Slideshow", font=fnb,
                 bg=t["bg"], fg=t["fg"]).pack(anchor=tk.W)
        tk.Label(body, font=fns, bg=t["bg"], fg=dim, wraplength=460,
                 text="Automatically rotates through images in the selected folder "
                      "using Windows Task Scheduler. No background process.").pack(
                          anchor=tk.W, pady=(2, 8))

        # Status label — populated immediately with a placeholder, then updated
        # from a background thread so the dialog opens instantly (schtasks /query
        # can block the main thread for several seconds).
        self._status_var = tk.StringVar(value="Checking scheduler status…")
        self._status_label = tk.Label(body, textvariable=self._status_var, font=fns,
                 bg=t["bg"], fg=CONSOLE_COLORS[theme_name]["yellow"],
                 wraplength=460, justify=tk.LEFT)
        self._status_label.pack(anchor=tk.W, pady=(0, 6))
        self._theme_name = theme_name

        def _fetch_status():
            scheduled = is_scheduled()
            status    = query_task_status()
            color = (CONSOLE_COLORS[theme_name]["green"] if scheduled
                     else CONSOLE_COLORS[theme_name]["yellow"])
            if self.winfo_exists():
                self.after(0, lambda: (
                    self._status_var.set(status),
                    self._status_label.config(fg=color),
                ))
        threading.Thread(target=_fetch_status, daemon=True).start()

        if state.get("last_file"):
            tk.Label(body,
                     text="Last set: {}  ({})".format(
                         state["last_file"], state.get("last_set", "?")),
                     font=fns, bg=t["bg"], fg=dim).pack(anchor=tk.W, pady=(0, 6))

        ttk.Separator(body).pack(fill=tk.X, pady=(0, 8))

        # Folder
        fr = tk.Frame(body, bg=t["bg"])
        fr.pack(fill=tk.X, pady=(0, 4))
        tk.Label(fr, text="Folder:", font=fnb, bg=t["bg"], fg=t["fg"],
                 width=12, anchor=tk.W).pack(side=tk.LEFT)
        self._folder_var = tk.StringVar(value=saved_folder)
        tk.Entry(fr, textvariable=self._folder_var,
                 font=("Consolas", font_size - 1),
                 bg=t["entry_bg"], fg=t["entry_fg"]).pack(
                     side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
        c = BTN_COLORS["primary"]
        tk.Button(fr, text="Browse…", font=fns,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._browse_folder).pack(side=tk.LEFT)

        self._count_var = tk.StringVar()
        self._update_count()
        tk.Label(body, textvariable=self._count_var,
                 font=fns, bg=t["bg"], fg=dim).pack(anchor=tk.W, pady=(0, 6))
        self._folder_var.trace_add("write", lambda *_: self._update_count())

        # Interval
        ir = tk.Frame(body, bg=t["bg"])
        ir.pack(fill=tk.X, pady=(0, 6))
        tk.Label(ir, text="Change every:", font=fnb, bg=t["bg"], fg=t["fg"],
                 width=14, anchor=tk.W).pack(side=tk.LEFT)
        self._interval_var = tk.StringVar()
        interval_labels = [lbl for lbl, _ in INTERVAL_OPTIONS]
        self._interval_var.set(next(
            (lbl for lbl, val in INTERVAL_OPTIONS if val == saved_interval),
            "10 min"))
        ttk.Combobox(ir, textvariable=self._interval_var,
                     values=interval_labels, width=10,
                     state="readonly", font=fn).pack(side=tk.LEFT, padx=4)

        # Style
        sr = tk.Frame(body, bg=t["bg"])
        sr.pack(fill=tk.X, pady=(0, 6))
        tk.Label(sr, text="Display style:", font=fnb, bg=t["bg"], fg=t["fg"],
                 width=14, anchor=tk.W).pack(side=tk.LEFT)
        self._style_var = tk.StringVar(value=saved_style)
        ttk.Combobox(sr, textvariable=self._style_var,
                     values=list(WALLPAPER_STYLES.keys()), width=10,
                     state="readonly", font=fn).pack(side=tk.LEFT, padx=4)

        # Shuffle
        self._shuffle_var = tk.BooleanVar(value=saved_shuffle)
        tk.Checkbutton(
            body,
            text="Shuffle (randomise order, cycle all before repeating)",
            variable=self._shuffle_var,
            font=fn, bg=t["bg"], fg=t["fg"],
            selectcolor=t["entry_bg"],
            activebackground=t["bg"]).pack(anchor=tk.W, pady=(0, 8))

        tk.Label(body, font=fns, bg=t["bg"], fg=dim, wraplength=460,
                 text="Tip: images are added to the pool automatically "
                      "whenever you save a wallpaper to the store.").pack(anchor=tk.W)

        self.bind("<Escape>", lambda _: self.destroy())

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _browse_folder(self):
        d = filedialog.askdirectory(title="Select slideshow folder",
                                    initialdir=self._folder_var.get())
        if d:
            self._folder_var.set(d)

    def _update_count(self):
        folder = Path(self._folder_var.get().strip())
        n = len(get_images_in_folder(folder))
        self._count_var.set(
            "⚠  No images found in this folder." if n == 0
            else "✔  {} image{} found.".format(n, "s" if n != 1 else ""))

    def _get_interval_min(self) -> int:
        label = self._interval_var.get()
        return next((val for lbl, val in INTERVAL_OPTIONS if lbl == label), 10)

    def _save_state_from_ui(self):
        folder = Path(self._folder_var.get().strip())
        state  = load_state()
        if state.get("folder") != str(folder):
            state["queue"]       = []
            state["queue_index"] = 0
        state["folder"]       = str(folder)
        state["interval_min"] = self._get_interval_min()
        state["shuffle"]      = self._shuffle_var.get()
        state["style"]        = self._style_var.get()
        save_state(state)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _start(self):
        folder = Path(self._folder_var.get().strip())
        if not folder.exists():
            messagebox.showerror("Folder not found",
                "Folder does not exist:\n{}".format(folder), parent=self)
            return
        if not get_images_in_folder(folder):
            messagebox.showerror("No images",
                "No image files found in:\n{}".format(folder), parent=self)
            return

        self._save_state_from_ui()
        py_path = find_python_exe()
        ok, msg = schedule_task(self._get_interval_min())
        diag = "Build: {}\nPython: {}\nHelpers dir: {}\nFrozen: {}".format(
            APP_BUILD, py_path, HELPERS_DIR,
            getattr(__import__('sys'), 'frozen', False))

        t = THEMES.get(self._cfg.get("theme"), THEMES["dark"])
        rw = tk.Toplevel(self)
        rw.title("Slideshow Schedule Result")
        rw.geometry("660x220")
        # No grab_set — don't block the main app
        rw.configure(bg=t["bg"])
        txt = scrolledtext.ScrolledText(rw, font=("Consolas", 9),
                                        wrap=tk.WORD, bg=t["entry_bg"], fg=t["fg"])
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt.insert(tk.END, "ok={}\n\n{}\n\n{}\n\nquery: {}".format(
            ok, msg, diag, query_task_status()))
        txt.config(state=tk.DISABLED)
        tk.Button(rw, text="Close", command=rw.destroy,
                  bg=t["btn_bg"], fg=t["btn_fg"]).pack(pady=4)

        if ok:
            self.result = "started"
            self._status_var.set(query_task_status())
            # Auto-close result window after 3s, then close dialog
            rw.after(3000, lambda: (rw.destroy(), self.destroy()))

    def _stop(self):
        if remove_task():
            self.result = "stopped"
            messagebox.showinfo("Stopped",
                "Slideshow task removed.\n"
                "Your current wallpaper stays until you change it.", parent=self)
            self.destroy()
        else:
            messagebox.showinfo("Not Running",
                "No slideshow task was scheduled.", parent=self)

    def _next_now(self):
        folder = Path(self._folder_var.get().strip())
        if not folder.exists():
            messagebox.showerror("Folder not found",
                "Folder does not exist:\n{}".format(folder), parent=self)
            return
        if not get_images_in_folder(folder):
            messagebox.showerror("No images",
                "No image files found in:\n{}".format(folder), parent=self)
            return
        self._save_state_from_ui()
        try:
            _run_next_headless(force=True)
            self.result = "next"
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _test_task(self):
        """Trigger the scheduled task via schtasks /run and then open the log."""
        if not is_scheduled():
            messagebox.showinfo("Not Scheduled",
                "No slideshow task is scheduled.\nClick ▶ Start first.", parent=self)
            return
        r = subprocess.run(
            ["schtasks", "/run", "/tn", TASK_NAME],
            capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "unknown").strip()
            messagebox.showerror("Test Failed",
                "schtasks /run failed:\n{}".format(err), parent=self)
            return
        # Wait a moment for the task process to write its log entry, then show log
        self.after(2500, self._view_log)

    def _view_log(self):
        log_path = HELPERS_DIR / "_slideshow_log.txt"
        if not log_path.exists():
            messagebox.showinfo("No Log",
                "No log file yet.\nExpected: {}".format(log_path), parent=self)
            return
        content = log_path.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            messagebox.showinfo("Log Empty", "Log file is empty.", parent=self)
            return
        t = THEMES.get(self._cfg.get("theme"), THEMES["dark"])
        dlg = tk.Toplevel(self)
        dlg.title("Slideshow Log")
        dlg.geometry("700x400")
        dlg.grab_set()
        dlg.configure(bg=t["bg"])
        txt = scrolledtext.ScrolledText(dlg, font=("Consolas", 9),
                                        wrap=tk.WORD, bg=t["entry_bg"], fg=t["fg"])
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt.insert(tk.END, content)
        txt.see(tk.END)
        txt.config(state=tk.DISABLED)
        c = BTN_COLORS["danger"]
        br = tk.Frame(dlg, bg=t["bg"])
        br.pack(fill=tk.X, padx=8, pady=(0, 8))
        tk.Button(br, text="Clear Log", bg=c["bg"], fg=c["fg"],
                  command=lambda: (log_path.unlink(), dlg.destroy())).pack(side=tk.LEFT)
        tk.Button(br, text="Close", bg=t["btn_bg"], fg=t["btn_fg"],
                  command=dlg.destroy).pack(side=tk.RIGHT)
