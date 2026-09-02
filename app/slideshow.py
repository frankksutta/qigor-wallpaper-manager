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
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path

from .constants import (THEMES, BTN_COLORS, CONSOLE_COLORS, STORE_DIR,
                        WALLPAPER_STYLES, HELPERS_DIR, APP_BUILD,
                        mark_role, paint_role)
from .wallpaper import (find_python_exe, apply_wallpaper,
                         get_current_wallpaper_path)
from .playlists import find as find_playlist, names as playlist_names
from . import playlists
from . import scaling
from .tooltip import Tooltip

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

# Quick-preview rotation, in seconds. Windows Task Scheduler refuses any
# repetition interval under a minute — it rejects PT5S and PT30S outright —
# so the preview is driven by the app's own timer. Everything below that timer
# is the scheduled slideshow's own code, so what you see is what it will do.
PREVIEW_SECONDS = [str(n) for n in range(5, 101, 5)]


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


def get_images_in_folder(folder: Path, recursive: bool = False) -> list:
    """
    The images in `folder`, sorted — names, or paths relative to it when
    recursive.

    os.walk rather than rglob: it does not follow directory junctions, and a
    wallpaper folder is one stray link away from a walk that never ends.
    """
    try:
        if not recursive:
            return sorted(
                f.name for f in folder.iterdir()
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS
            )
        import os
        found = []
        for root, dirs, files in os.walk(folder):
            # Nobody keeps wallpapers in .git or .thumbnails, and everybody
            # has them.
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            rel = Path(root).relative_to(folder)
            for name in files:
                if Path(name).suffix.lower() in IMAGE_EXTS:
                    found.append(name if str(rel) == "." else str(rel / name))
        return sorted(found)
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
            ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST", "/v"],
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





# ── The image pool ───────────────────────────────────────────────

def resolve_pool(state: dict) -> list:
    """
    Every image the slideshow may show, as absolute path strings.

    Both sources are re-read on every rotation rather than frozen into the
    state: images saved to a folder join the rotation on their own, and a
    playlist edited while the slideshow is running takes effect at its next
    fire.
    """
    if state.get("source") == "playlist":
        return playlists.existing_items(state.get("playlist") or "")
    folder = Path(state.get("folder", ""))
    return [str(folder / name)
            for name in get_images_in_folder(folder,
                                             state.get("recursive", False))]


def describe_pool(state: dict) -> str:
    """How to name this slideshow's source in a message."""
    if state.get("source") == "playlist":
        return "playlist “{}”".format(state.get("playlist") or "?")
    return "folder{}:\n{}".format(
        " and its subfolders" if state.get("recursive") else "",
        state.get("folder", "?"))


def advance(state: dict, *, force: bool = False, persist: bool = True,
            log=lambda _m: None):
    """
    Move the rotation on by one image. Returns (image_path or None, error).

    The scheduled runner and the in-app preview both come through here, so a
    preview shows exactly what the slideshow would do — same pool, same
    shuffled queue, same display style. `persist` is what separates them: a
    preview must not write the real rotation's position or its last_set
    timestamp, or the next scheduled fire would take itself for a double-fire
    and skip.

    `state` is mutated in place; it is only written to disk when persist.
    """
    import random
    import datetime as _dt

    interval_min = state.get("interval_min", 10)

    # Guard: skip if the last rotation was less than 90% of the interval ago.
    # Prevents StartWhenAvailable catch-up from double-firing right after a
    # normal on-time fire.  force=True bypasses it — used by "Next Now", and
    # by the preview, which rotates in seconds.
    if not force:
        last_set_str = state.get("last_set", "")
        if last_set_str:
            try:
                last_set    = _dt.datetime.strptime(last_set_str, "%Y-%m-%d %H:%M:%S")
                elapsed_min = (_dt.datetime.now() - last_set).total_seconds() / 60
                threshold   = interval_min * 0.9
                log("Guard: elapsed={:.1f}min  threshold={:.1f}min (90% of {}min)  last_set={}".format(
                    elapsed_min, threshold, interval_min, last_set_str))
                if elapsed_min < threshold:
                    log("Skipping: too soon.")
                    return None, ""
            except Exception as e:
                log("Guard parse error (proceeding): {}".format(e))
        else:
            log("Guard: no last_set yet — proceeding.")
    else:
        log("Force=True, bypassing guard.")

    style   = state.get("style", "Fill")
    shuffle = state.get("shuffle", True)

    if state.get("source") == "playlist":
        name = state.get("playlist") or ""
        if not name:
            log("ERROR: no playlist chosen.")
            return None, "No playlist chosen.\nPick one in the Slideshow tab."
        if find_playlist(name) is None:
            log("ERROR: playlist gone: " + name)
            return None, "Playlist “{}” no longer exists.".format(name)
    else:
        folder = Path(state.get("folder", ""))
        if not folder.exists():
            log("ERROR: folder not found: " + str(folder))
            return None, "Folder not found:\n{}".format(folder)

    pool = resolve_pool(state)
    if not pool:
        log("ERROR: no images in " + describe_pool(state))
        return None, "No images found in {}".format(describe_pool(state))

    queue = state.get("queue", [])
    index = state.get("queue_index", 0)

    if not queue or index >= len(queue) or set(pool) != set(queue):
        log("Rebuilding queue ({} images)".format(len(pool)))
        queue = list(pool)
        if shuffle:
            random.shuffle(queue)
        index = 0

    chosen = None
    for _ in range(len(queue)):
        candidate = Path(queue[index % len(queue)])
        # No modulo on the stored index: it must be allowed to reach
        # len(queue) so the next run's "index >= len(queue)" check rebuilds —
        # and reshuffles — the queue after every full cycle.
        index += 1
        if candidate.exists():
            chosen = candidate
            break
        log("Skipping missing: " + candidate.name)

    if not chosen:
        log("ERROR: all files in queue are missing.")
        return None, "All images in the queue are missing.\nCheck {}".format(
            describe_pool(state))

    apply_wallpaper(str(chosen), style)

    state["queue"]       = queue
    state["queue_index"] = index
    state["last_set"]    = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["last_file"]   = chosen.name
    if persist:
        save_state(state)
    log("Done: {} ({}/{})".format(chosen.name, index, len(queue)))
    return chosen, ""


def _log_tag(line: str) -> str:
    """The console colour a log line has earned."""
    if "ERROR" in line:     return "red"
    if "Skipping" in line:  return "yellow"
    if "[PREVIEW]" in line: return "cyan"
    if "[SETUP]" in line:   return "magenta"
    if "Done:" in line:     return "green"
    return "dim"


def _trim_log(path: Path, keep: int = 400, limit: int = 1200):
    """
    Hold the log to its last `keep` lines once it passes `limit`.

    It used to be cleared by hand, from a button on the window that showed it.
    That window is gone — the history prints into the app console now — so the
    file looks after itself, once per scheduled fire.
    """
    try:
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) <= limit:
            return
        path.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")
    except OSError:
        pass


# ── Scheduler ───────────────────────────────────────────────────

def _run_next_headless(force: bool = False):
    """
    Headless slideshow advance — called via  exe --next  by Task Scheduler.
    No Python installation required on the target machine.
    Runs entirely within the frozen EXE process.

    force=True bypasses the elapsed-time guard (used by the "Next Now" button).
    """
    import datetime as _dt

    log_file = HELPERS_DIR / "_slideshow_log.txt"
    HELPERS_DIR.mkdir(parents=True, exist_ok=True)

    def log(msg):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "  " + str(msg) + "\n")

    def _toast(title, msg):
        try:
            from winotify import Notification
            Notification(app_id="QiGor Wallpaper Manager",
                         title=title, msg=msg, duration="long").show()
        except Exception:
            pass

    _trim_log(log_file)
    log("--- --next triggered. argv={} force={}".format(sys.argv[1:], force))

    state = load_state()
    if not state:
        log("ERROR: no state file. Configure slideshow in the QiGor app.")
        _toast("Slideshow stopped",
               "No configuration found. Open QiGor and click ▶ Start.")
        return

    _chosen, err = advance(state, force=force, persist=True, log=log)
    if err:
        _toast("Slideshow stopped", err)
        return

    # Query task status so the log shows when the next fire is scheduled
    try:
        r2 = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST", "/v"],
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


def get_expected_runner() -> "str | None":
    """
    Return the path the Task Scheduler task should invoke.
    Priority: frozen EXE > QiGor_Wallpaper_Manager.exe > qigor_wallpaper_manager.pyw.
    Uses specific filenames — never sys.argv[0] (avoids the '-c' launcher bug) and
    never a blind glob (avoids picking up unrelated .pyw files in the project root).
    """
    if getattr(sys, "frozen", False):
        return sys.executable
    pkg_root = Path(__file__).resolve().parent.parent
    for name in ("QiGor_Wallpaper_Manager.exe", "qigor_wallpaper_manager.pyw"):
        candidate = pkg_root / name
        if candidate.exists():
            return str(candidate)
    return None


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
        runner = get_expected_runner()
        if runner is None:
            pkg_root = Path(__file__).resolve().parent.parent
            return False, (
                "Cannot find the application runner.\n\n"
                "Looked for QiGor_Wallpaper_Manager.exe, *.pyw, and *.py in:\n"
                "  {}\n\n"
                "If you have moved or renamed the application, re-run it from its "
                "new location and open Slideshow ▶ Start to re-register the task."
            ).format(pkg_root)
        if runner.lower().endswith(".exe"):
            cmd_exe  = runner
            cmd_args = "--next"
        else:
            from .wallpaper import find_python_exe
            cmd_exe  = find_python_exe()
            cmd_args = '"{}" --next'.format(runner)
        runner_desc = runner

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


def _query_task_fields() -> "dict | None":
    """Run schtasks /query and return a key→value dict, or None if task not found."""
    try:
        r = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST", "/v"],
            capture_output=True, text=True, timeout=8)
        if r.returncode != 0:
            return None
        fields: dict = {}
        for line in r.stdout.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                fields[k.strip().lower()] = v.strip()
        return fields
    except Exception:
        return None


def slideshow_runner_is_stale() -> bool:
    """
    Return True if a slideshow task is scheduled but its registered command path
    doesn't match get_expected_runner() — meaning the EXE or script has moved.
    """
    fields = _query_task_fields()
    if fields is None:
        return False
    expected = get_expected_runner()
    if expected is None:
        return False
    task_to_run = fields.get("task to run", "")
    return expected.lower() not in task_to_run.lower()


def slideshow_last_run_failed() -> "tuple[bool, str]":
    """
    Return (failed, detail) where failed=True means the last scheduled run exited
    with a non-zero code. Task Scheduler never notifies the user of failures, so
    this is the only way to surface silent breakage on startup.
    """
    fields = _query_task_fields()
    if fields is None:
        return False, ""
    last_run = fields.get("last run time", "").strip()
    if last_run.lower() in ("", "never", "n/a"):
        return False, ""
    result_str = fields.get("last result", "0").strip()
    try:
        code = int(result_str, 0)
    except ValueError:
        return False, ""
    # Benign scheduler codes, not failures:
    #   0        = success
    #   267009   = 0x41301 task is currently running
    #   267011   = 0x41303 task has not yet run
    if code in (0, 267009, 267011):
        return False, ""
    return True, "exit code {} at {}".format(result_str, last_run)


def slideshow_is_overdue() -> "tuple[bool, str]":
    """
    Return (overdue, description) based on the state file.
    overdue=True when now - last_set > 2 × interval_min, meaning the scheduled
    task likely stopped firing on its own.
    """
    import datetime as _dt
    state = load_state()
    last_set_str = state.get("last_set", "")
    interval_min = state.get("interval_min", 10)
    if not last_set_str:
        return False, ""
    try:
        last_set    = _dt.datetime.strptime(last_set_str, "%Y-%m-%d %H:%M:%S")
        elapsed_min = (_dt.datetime.now() - last_set).total_seconds() / 60
        if elapsed_min > interval_min * 2:
            hours = elapsed_min / 60
            return True, "last set {:.0f}h ago (interval {}min)".format(
                hours, interval_min)
    except Exception:
        pass
    return False, ""


# ── Panel ─────────────────────────────────────────────────────────────────────

class SlideshowPanel(tk.Frame):
    """
    Configure and control the wallpaper slideshow.

    A tab rather than a modal window. As a Toplevel it sat on top of the
    console, which is where the app reports what the slideshow just did, and
    every open rebuilt its state from disk. `on_result` replaces the old
    wait_window/result handshake, since nothing waits on a tab.
    """

    # How much of the rotation history 📋 Log prints. The file keeps more —
    # it is named in the header line — but a console is for the recent past.
    LOG_TAIL = 40

    def __init__(self, parent, cfg, theme_name, on_result=None,
                 on_scheduled=None, on_edit_playlists=None, log=None):
        super().__init__(parent)
        self.result   = None
        self._on_result = on_result
        # Writes into the app's console. The panel had no way to reach it, so
        # the rotation history could only be shown in a window of its own.
        self._console_log = log or (lambda *_a, **_k: None)
        # Opens the Playlists tab. The panel offers the playlists as a source
        # but does not own them, so it asks the app to switch tabs.
        self._on_edit_playlists = on_edit_playlists
        # Quick preview: a timer of this panel's own, and a copy of the
        # settings for it to walk. Never the state on disk — see advance().
        self._preview_after   = None
        self._previewing      = False
        self._preview_state   = {}
        self._preview_restore = None
        self._preview_n       = 0
        self._preview_left    = 0
        self._preview_last    = ""
        # Counting the pool can walk a whole tree now, so it runs off the main
        # thread; the generation number drops results the user has typed past.
        self._count_gen       = 0
        # Reports whether a task is registered, from the background query the
        # panel already runs. Without it the app asked schtasks a second time
        # on the main thread just to put a tick on the tab.
        self._on_scheduled = on_scheduled
        self._cfg     = cfg

        t = THEMES.get(theme_name, THEMES["dark"])
        self.configure(bg=t["bg"])
        fn  = scaling.font("Segoe UI", 10)
        fnb = scaling.font("Segoe UI", 10, "bold")
        fns = scaling.font("Segoe UI", 9)
        dim = CONSOLE_COLORS[theme_name]["dim"]

        state          = load_state()
        saved_folder   = state.get("folder",       str(STORE_DIR))
        saved_interval = state.get("interval_min", 10)
        saved_shuffle  = state.get("shuffle",      True)
        saved_style    = state.get("style",
                                   cfg.get("wallpaper_style") or "Fill")
        saved_source   = state.get("source",   "folder")
        saved_recurse  = state.get("recursive", False)
        saved_playlist = state.get("playlist", "")
        saved_psecs    = str(cfg.get("slideshow_preview_secs") or 10)
        saved_restore  = bool(cfg.get("slideshow_preview_restore"))

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=t["bg"])
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(4, 12))

        c = BTN_COLORS["success"]
        self._btn_start = tk.Button(btn_row, text="▶ Start", height=2, font=fnb,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._start)
        self._btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        Tooltip(self._btn_start,
                "Schedule the slideshow.\n"
                "If already running, applies any changed settings\n"
                "(folder, interval, style) and resets the timer.")

        c = BTN_COLORS["primary"]
        btn_next = tk.Button(btn_row, text="⏭ Next Now", height=2, font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._next_now)
        btn_next.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        Tooltip(btn_next,
                "Switch to the next wallpaper immediately,\n"
                "bypassing the schedule timer.")

        c = BTN_COLORS["warning"]
        btn_log = tk.Button(btn_row, text="📋 Log", height=2, font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._view_log)
        btn_log.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        Tooltip(btn_log,
                "Print the rotation history into the log console below:\n"
                "timestamps, guard decisions, previews, and any errors.\n"
                "The last {} lines; the file holds more.".format(self.LOG_TAIL))

        c = BTN_COLORS["primary"]
        self._btn_test = tk.Button(btn_row, text="⚙ Test Task", height=2, font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._test_task, state="disabled")
        self._btn_test.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        Tooltip(self._btn_test,
                "Fire the Windows scheduled task right now\n"
                "to confirm the scheduler is working, then open the log.\n"
                "(Only available while the slideshow is running.)")

        c = BTN_COLORS["danger"]
        self._btn_stop = tk.Button(btn_row, text="⏹ Stop", height=2, font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._stop, state="disabled")
        self._btn_stop.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        Tooltip(self._btn_stop,
                "Remove the scheduled task — stops automatic rotation.\n"
                "Your current wallpaper stays as-is.\n"
                "(Only available while the slideshow is running.)")


        # ── Body ──────────────────────────────────────────────────────────────
        # Imported here, not at the top of the module: imagepanes reaches
        # Pillow, and `--next` loads this module on a timer to move one
        # wallpaper along without ever building a widget.
        from .imagepanes import scrollable
        # It scrolls: the panel has since grown a source picker and a preview
        # block, and pack drops the rows at the foot of a short window
        # silently — nothing on screen says they are there.
        self._scroll_canvas, self._scroll_bar, scroll_body = scrollable(self)
        body = tk.Frame(scroll_body, bg=t["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(14, 6))

        tk.Label(body, text="Wallpaper Slideshow", font=fnb,
                 bg=t["bg"], fg=t["fg"]).pack(anchor=tk.W)
        mark_role(tk.Label(body, font=fns, bg=t["bg"], fg=dim, wraplength=460,
                 justify=tk.LEFT,
                 text="Automatically rotates through a folder, or through a "
                      "playlist you have built, using Windows Task Scheduler. "
                      "No background process."),
                  "dim").pack(anchor=tk.W, pady=(2, 8))

        # Status label — populated immediately with a placeholder, then updated
        # from a background thread so the dialog opens instantly (schtasks /query
        # can block the main thread for several seconds).
        self._status_var = tk.StringVar(value="Checking scheduler status…")
        self._status_label = mark_role(tk.Label(body,
                 textvariable=self._status_var, font=fns,
                 bg=t["bg"], fg=CONSOLE_COLORS[theme_name]["yellow"],
                 wraplength=460, justify=tk.LEFT), "yellow")
        self._status_label.pack(anchor=tk.W, pady=(0, 6))
        self._theme_name = theme_name

        self._refresh_status()

        if state.get("last_file"):
            mark_role(tk.Label(body,
                     text="Last set: {}  ({})".format(
                         state["last_file"], state.get("last_set", "?")),
                     font=fns, bg=t["bg"], fg=dim),
                     "dim").pack(anchor=tk.W, pady=(0, 6))

        ttk.Separator(body).pack(fill=tk.X, pady=(0, 8))

        # Where the images come from
        sr0 = tk.Frame(body, bg=t["bg"])
        sr0.pack(fill=tk.X, pady=(0, 4))
        tk.Label(sr0, text="Play from:", font=fnb, bg=t["bg"], fg=t["fg"],
                 width=12, anchor=tk.W).pack(side=tk.LEFT)
        self._source_var = tk.StringVar(value=saved_source)
        for label, value, tip in (
                ("Folder", "folder",
                 "Rotate through every image in the folder below.\n"
                 "Images saved there later join the rotation on their own."),
                ("Playlist", "playlist",
                 "Rotate through a playlist you built on the Playlists tab.")):
            rb = tk.Radiobutton(sr0, text=label, variable=self._source_var,
                                value=value, font=fn,
                                bg=t["bg"], fg=t["fg"],
                                selectcolor=t["entry_bg"],
                                activebackground=t["bg"],
                                command=self._on_source_change)
            rb.pack(side=tk.LEFT, padx=(4, 4))
            Tooltip(rb, tip)

        self._playlist_var = tk.StringVar(value=saved_playlist)
        self._playlist_combo = ttk.Combobox(
            sr0, textvariable=self._playlist_var, values=playlist_names(),
            width=20, state="readonly", font=fn)
        self._playlist_combo.pack(side=tk.LEFT, padx=(2, 4))
        self._playlist_combo.bind("<<ComboboxSelected>>",
                                  lambda _e: self._update_count())
        Tooltip(self._playlist_combo,
                "Which playlist to rotate through.\n"
                "A playlist is read fresh on every change, so editing one\n"
                "changes a running slideshow from its next image on.")

        c = BTN_COLORS["primary"]
        edit_btn = tk.Button(sr0, text="Edit…", font=fns,
                             bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                             command=self._edit_playlists)
        edit_btn.pack(side=tk.LEFT)
        Tooltip(edit_btn, "Open the Playlists tab to build or change one.")

        # Folder
        fr = tk.Frame(body, bg=t["bg"])
        fr.pack(fill=tk.X, pady=(0, 4))
        tk.Label(fr, text="Folder:", font=fnb, bg=t["bg"], fg=t["fg"],
                 width=12, anchor=tk.W).pack(side=tk.LEFT)
        self._folder_var = tk.StringVar(value=saved_folder)
        self._folder_entry = tk.Entry(fr, textvariable=self._folder_var,
                 font=scaling.font("Consolas", 9),
                 bg=t["entry_bg"], fg=t["entry_fg"])
        self._folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True,
                                padx=(4, 4))
        c = BTN_COLORS["primary"]
        self._browse_btn = tk.Button(fr, text="Browse…", font=fns,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._browse_folder)
        self._browse_btn.pack(side=tk.LEFT, padx=(0, 4))
        c = BTN_COLORS["warning"]
        self._store_btn = tk.Button(fr, text="Default store", font=fns,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._use_default_store)
        self._store_btn.pack(side=tk.LEFT)
        Tooltip(self._store_btn,
                "Back to the folder QiGor saves images to:\n"
                "{}\n\n"
                "This is where “Copy to image store” puts them, and what the "
                "Image store\npanes list — one press to return after browsing "
                "somewhere else.".format(STORE_DIR))

        # Filled in by the _on_source_change() at the foot of __init__: the
        # count now depends on the source picker above and on the controls
        # built below this line.
        self._count_var = tk.StringVar()
        mark_role(tk.Label(body, textvariable=self._count_var,
                 font=fns, bg=t["bg"], fg=dim),
                 "dim").pack(anchor=tk.W, pady=(0, 6))
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

        # Shuffle, and how deep a folder goes
        cbs = tk.Frame(body, bg=t["bg"])
        cbs.pack(fill=tk.X, pady=(0, 8))
        self._shuffle_var = tk.BooleanVar(value=saved_shuffle)
        shuffle_cb = tk.Checkbutton(
            cbs,
            text="Shuffle (randomise order, cycle all before repeating)",
            variable=self._shuffle_var,
            font=fn, bg=t["bg"], fg=t["fg"],
            selectcolor=t["entry_bg"],
            activebackground=t["bg"])
        shuffle_cb.pack(side=tk.LEFT)
        Tooltip(shuffle_cb,
                "Play in random order, showing every image once\n"
                "before any of them comes round again.")

        self._recursive_var = tk.BooleanVar(value=saved_recurse)
        self._recursive_cb = tk.Checkbutton(
            cbs, text="Include subfolders",
            variable=self._recursive_var,
            command=self._update_count,
            font=fn, bg=t["bg"], fg=t["fg"],
            selectcolor=t["entry_bg"],
            activebackground=t["bg"])
        self._recursive_cb.pack(side=tk.LEFT, padx=(12, 0))
        Tooltip(self._recursive_cb,
                "Take the images in the folder's subfolders too,\n"
                "however deep they go.\n\n"
                "Only applies to a folder — a playlist is a list of\n"
                "images, wherever each of them happens to live.")

        mark_role(tk.Label(body, font=fns, bg=t["bg"], fg=dim, wraplength=460,
                 justify=tk.LEFT,
                 text="Tip: a folder picks up new images as you save them; "
                      "a playlist only ever holds what you put in it."),
                  "dim").pack(anchor=tk.W)

        # ── Quick preview ─────────────────────────────────────────────────────
        ttk.Separator(body).pack(fill=tk.X, pady=(8, 6))

        tk.Label(body, text="Quick preview", font=fnb,
                 bg=t["bg"], fg=t["fg"]).pack(anchor=tk.W)
        mark_role(tk.Label(body, font=fns, bg=t["bg"], fg=dim, wraplength=460,
                 justify=tk.LEFT,
                 text="The same rotation, seconds apart, so you can see a "
                      "folder or playlist without waiting for the schedule. "
                      "QiGor drives this one itself, so it runs only while "
                      "the app is open."),
                  "dim").pack(anchor=tk.W, pady=(2, 4))

        pr = tk.Frame(body, bg=t["bg"])
        pr.pack(fill=tk.X, pady=(0, 4))
        tk.Label(pr, text="Every:", font=fnb, bg=t["bg"], fg=t["fg"],
                 width=12, anchor=tk.W).pack(side=tk.LEFT)
        self._psecs_var = tk.StringVar(value=saved_psecs)
        if saved_psecs not in PREVIEW_SECONDS:
            self._psecs_var.set("10")
        ttk.Combobox(pr, textvariable=self._psecs_var, values=PREVIEW_SECONDS,
                     width=5, state="readonly", font=fn).pack(side=tk.LEFT,
                                                              padx=(4, 4))
        tk.Label(pr, text="seconds", font=fn, bg=t["bg"],
                 fg=t["fg"]).pack(side=tk.LEFT, padx=(0, 10))

        c = BTN_COLORS["primary"]
        self._btn_preview = tk.Button(pr, text="▶ Preview", font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._start_preview)
        self._btn_preview.pack(side=tk.LEFT, padx=(0, 4))
        Tooltip(self._btn_preview,
                "Start rotating now, at the interval on the left.\n"
                "Changing that interval mid-preview takes effect\n"
                "at the next image.\n\n"
                "Not a scheduled task: Windows will not repeat one\n"
                "more often than once a minute. This runs on QiGor's\n"
                "own timer and leaves the scheduled slideshow's place\n"
                "in its queue untouched.")

        c = BTN_COLORS["danger"]
        self._btn_preview_stop = tk.Button(pr, text="⏹ Stop preview", font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._stop_preview, state="disabled")
        self._btn_preview_stop.pack(side=tk.LEFT)
        Tooltip(self._btn_preview_stop,
                "End the preview. The scheduled slideshow,\n"
                "if one is running, is unaffected either way.")

        self._restore_var = tk.BooleanVar(value=saved_restore)
        self._restore_cb = tk.Checkbutton(
            body,
            text="Put the wallpaper back when the preview stops",
            variable=self._restore_var,
            font=fn, bg=t["bg"], fg=t["fg"],
            selectcolor=t["entry_bg"],
            activebackground=t["bg"])
        self._restore_cb.pack(anchor=tk.W, pady=(2, 2))

        self._preview_var = tk.StringVar(value="")
        self._preview_status = mark_role(tk.Label(
            body, textvariable=self._preview_var, font=fns, anchor=tk.W,
            justify=tk.LEFT, bg=t["bg"], fg=dim), "dim")
        self._preview_status.pack(anchor=tk.W, pady=(0, 6))

        self._on_source_change()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _finish(self, result):
        """Tell the app what happened. Nothing closes — this is a tab."""
        self.result = result
        if self._on_result:
            self._on_result(result)

    def retheme(self, theme_name):
        """Re-apply the colours this panel owns after the app repaints it."""
        self._theme_name = theme_name
        self._refresh_status()

    def _set_running_state(self, running: bool):
        """Enable/disable buttons that only make sense when the task is (not) running."""
        state = "normal" if running else "disabled"
        self._btn_stop.config(state=state)
        self._btn_test.config(state=state)

    def _refresh_status(self):
        """Refresh the status label from a background thread."""
        theme_name = self._theme_name

        def _fetch():
            # The status carries a palette role, not a resolved colour: the user
            # can flip the theme while this schtasks query is still running.
            scheduled = is_scheduled()
            status    = query_task_status()
            if scheduled:
                overdue, _desc = slideshow_is_overdue()
                if overdue:
                    status_str = status + "\n⚠ Slideshow overdue — click ▶ Start to re-register."
                    role = "yellow"
                else:
                    status_str = status
                    role = "green"
            else:
                status_str = status
                role = "yellow"
            # Dialog may be destroyed while the schtasks query was running —
            # both scheduling the callback and the callback itself must cope.
            def _apply(s=scheduled, st=status_str, r=role):
                try:
                    self._status_var.set(st)
                    paint_role(self._status_label, r, self._theme_name)
                    self._set_running_state(s)
                    if self._on_scheduled is not None:
                        self._on_scheduled(s)
                except tk.TclError:
                    pass
            try:
                self.after(0, _apply)
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=_fetch, daemon=True).start()

    def refresh_playlists(self):
        """The Playlists tab changed something — re-read the names."""
        try:
            names = playlist_names()
            self._playlist_combo.config(values=names)
            if self._playlist_var.get() not in names:
                self._playlist_var.set(names[0] if names else "")
            self._update_count()
        except tk.TclError:
            pass

    def use_playlist(self, name):
        """Point the slideshow at `name`. Called from the Playlists tab."""
        self.refresh_playlists()
        self._playlist_var.set(name)
        self._source_var.set("playlist")
        self._on_source_change()

    def _edit_playlists(self):
        if self._on_edit_playlists is not None:
            self._on_edit_playlists()

    def _on_source_change(self):
        """Grey out whichever source is not in use, and recount."""
        by_playlist = self._source_var.get() == "playlist"
        for w in (self._folder_entry, self._browse_btn, self._store_btn,
                  self._recursive_cb):
            w.config(state="disabled" if by_playlist else "normal")
        self._playlist_combo.config(
            state="readonly" if by_playlist else "disabled")
        self._update_count()

    def _state_from_ui(self) -> dict:
        """What the controls currently say, in the shape advance() wants."""
        folder = self._folder_var.get().strip()
        return {
            "folder":       str(Path(folder)) if folder else "",
            "source":       self._source_var.get(),
            "playlist":     self._playlist_var.get(),
            "recursive":    self._recursive_var.get(),
            "interval_min": self._get_interval_min(),
            "shuffle":      self._shuffle_var.get(),
            "style":        self._style_var.get(),
        }

    def _check_pool(self) -> bool:
        """Complain, once, about whatever would stop a rotation working."""
        ui = self._state_from_ui()
        if ui["source"] == "playlist":
            if not ui["playlist"]:
                messagebox.showerror(
                    "No playlist",
                    "Choose a playlist, or build one on the Playlists tab.",
                    parent=self)
                return False
        elif not Path(ui["folder"]).exists():
            messagebox.showerror(
                "Folder not found",
                "Folder does not exist:\n{}".format(ui["folder"]), parent=self)
            return False
        if not resolve_pool(ui):
            messagebox.showerror(
                "No images",
                "No image files found in {}".format(describe_pool(ui)),
                parent=self)
            return False
        return True

    def _use_default_store(self):
        """Point the folder back at the store this app saves into."""
        self._folder_var.set(str(STORE_DIR))

    def _browse_folder(self):
        d = filedialog.askdirectory(title="Select slideshow folder",
                                    initialdir=self._folder_var.get())
        if d:
            self._folder_var.set(d)

    def _update_count(self):
        """
        Say how big the pool is — from a thread, since "Include subfolders"
        can send it walking a whole tree, and this runs on every keystroke in
        the folder box.
        """
        ui = self._state_from_ui()
        if ui["source"] == "playlist" and not ui["playlist"]:
            self._count_var.set(
                "⚠  No playlist yet — build one on the Playlists tab.")
            return
        if ui["source"] == "playlist":
            where = "playlist “{}”".format(ui["playlist"])
        elif ui["recursive"]:
            where = "this folder and its subfolders"
        else:
            where = "this folder"

        self._count_gen += 1
        gen = self._count_gen

        def _work():
            n = len(resolve_pool(ui))

            def _apply():
                # The folder box may have moved on while this was counting.
                if gen != self._count_gen:
                    return
                self._count_var.set(
                    "⚠  No images found in {}.".format(where) if n == 0
                    else "✔  {} image{} in {}.".format(
                        n, "s" if n != 1 else "", where))
            try:
                self.after(0, _apply)
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=_work, daemon=True).start()

    def _get_interval_min(self) -> int:
        label = self._interval_var.get()
        return next((val for lbl, val in INTERVAL_OPTIONS if lbl == label), 10)

    def _save_state_from_ui(self):
        ui    = self._state_from_ui()
        state = load_state()
        # A different pool means the shuffled queue describes images that are
        # no longer being shown; it has to be rebuilt rather than resumed.
        if any(state.get(k) != ui[k]
               for k in ("folder", "source", "playlist", "recursive")):
            state["queue"]       = []
            state["queue_index"] = 0
        state.update(ui)
        save_state(state)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _start(self):
        if not self._check_pool():
            return
        # Two things rotating the wallpaper at once reads as a bug. The
        # scheduled slideshow is the one that was just asked for.
        if self._previewing:
            self._stop_preview()

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
        txt = scrolledtext.ScrolledText(rw, font=scaling.font("Consolas", 9),
                                        wrap=tk.WORD, bg=t["entry_bg"], fg=t["fg"])
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt.insert(tk.END, "ok={}\n\n{}\n\n{}\n\nquery: {}".format(
            ok, msg, diag, query_task_status()))
        txt.config(state=tk.DISABLED)
        tk.Button(rw, text="Close", command=rw.destroy,
                  bg=t["btn_bg"], fg=t["btn_fg"]).pack(pady=4)

        if ok:
            self._status_var.set(query_task_status())
            self._set_running_state(True)
            self._finish("started")

            # Dismiss the result window after 3s. Only that window — the panel
            # stays put, and the user may have closed the window already.
            def _auto_close():
                try:
                    rw.destroy()
                except tk.TclError:
                    pass
            rw.after(3000, _auto_close)

    def _stop(self):
        if remove_task():
            self._set_running_state(False)
            self._refresh_status()
            messagebox.showinfo("Stopped",
                "Slideshow task removed.\n"
                "Your current wallpaper stays until you change it.", parent=self)
            self._finish("stopped")
        else:
            messagebox.showinfo("Not Running",
                "No slideshow task was scheduled.", parent=self)

    def _next_now(self):
        if not self._check_pool():
            return
        self._save_state_from_ui()
        try:
            _run_next_headless(force=True)
            self._finish("next")
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    # ── Quick preview ─────────────────────────────────────────────────────────

    def _preview_secs(self) -> int:
        try:
            return max(1, int(self._psecs_var.get()))
        except (ValueError, tk.TclError):
            return 10

    # What a preview is allowed to write. It rotates every few seconds, and
    # advance() narrates every one of them — a minute of previewing would bury
    # the scheduled history that 📋 Log exists to show.
    _PREVIEW_LOG_KEEPS = ("started", "stopped", "restored", "could not",
                          "ERROR", "Skipping missing")

    def _preview_log(self, msg):
        """Into the slideshow's own log, so 📋 Log shows previews too."""
        import datetime as _dt
        text = str(msg)
        if not any(k in text for k in self._PREVIEW_LOG_KEEPS):
            return
        try:
            HELPERS_DIR.mkdir(parents=True, exist_ok=True)
            with open(HELPERS_DIR / "_slideshow_log.txt", "a",
                      encoding="utf-8") as f:
                f.write(_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        + "  [PREVIEW] " + text + "\n")
        except OSError:
            pass

    def preview_running(self) -> bool:
        return self._previewing

    def _start_preview(self):
        if self._previewing or not self._check_pool():
            return
        self._cfg.set("slideshow_preview_secs", self._preview_secs())
        self._cfg.set("slideshow_preview_restore", self._restore_var.get())
        # A copy of the settings with a queue of its own. Sharing the saved
        # queue would leave the scheduled rotation wherever the preview
        # stopped, and skipping the images it had already shown.
        self._preview_state = dict(self._state_from_ui(),
                                   queue=[], queue_index=0)
        # Restored at the panel's current display style: the registry keeps
        # the old style but this app has never had a reason to read it back.
        self._preview_restore = (get_current_wallpaper_path()
                                 if self._restore_var.get() else None)
        self._previewing   = True
        self._preview_n    = 0
        self._preview_left = 0
        self._preview_last = ""
        self._btn_preview.config(state="disabled")
        self._btn_preview_stop.config(state="normal")
        self._preview_log("started — every {}s from {}".format(
            self._preview_secs(),
            describe_pool(self._preview_state).replace("\n", " ")))
        self._finish("preview-started")
        self._preview_tick()

    def _preview_tick(self):
        """One second of the preview: count down, and rotate at zero."""
        self._preview_after = None
        if not self._previewing:
            return
        if self._preview_left <= 0:
            # Re-read the controls each time round: shuffle, style, and the
            # source itself follow what is set above, the way the interval
            # already did. Only the queue and the place in it belong to the
            # preview — and advance() rebuilds those by itself as soon as the
            # pool underneath them changes.
            self._preview_state.update(self._state_from_ui())
            chosen, err = advance(self._preview_state, force=True,
                                  persist=False, log=self._preview_log)
            if err:
                self._stop_preview()
                messagebox.showerror("Preview stopped", err, parent=self)
                return
            self._preview_n   += 1
            self._preview_last = chosen.name if chosen else "?"
            self._preview_left = self._preview_secs()
        self._preview_var.set(
            "▶  Previewing — {}  ({} shown)  •  next in {}s".format(
                self._preview_last, self._preview_n, max(self._preview_left, 0)))
        self._preview_left -= 1
        try:
            self._preview_after = self.after(1000, self._preview_tick)
        except tk.TclError:
            self._previewing = False

    def _stop_preview(self):
        if not self._previewing:
            return
        self._previewing = False
        if self._preview_after is not None:
            try:
                self.after_cancel(self._preview_after)
            except (tk.TclError, ValueError):
                pass
            self._preview_after = None
        try:
            self._btn_preview.config(state="normal")
            self._btn_preview_stop.config(state="disabled")
        except tk.TclError:
            pass
        put_back = ""
        # The tick-box is read again here, not only at the start: seeing an
        # image you want to keep is a good reason to untick it mid-preview.
        if self._preview_restore and self._restore_var.get():
            try:
                apply_wallpaper(self._preview_restore, self._style_var.get())
                put_back = "  •  wallpaper put back"
                self._preview_log(
                    "restored " + Path(self._preview_restore).name)
            except Exception as e:
                self._preview_log("could not restore the wallpaper: {}".format(e))
        self._preview_restore = None
        self._preview_log("stopped after {} image(s).".format(self._preview_n))
        try:
            self._preview_var.set("Preview stopped after {} image{}.{}".format(
                self._preview_n, "" if self._preview_n == 1 else "s", put_back))
        except tk.TclError:
            pass
        self._finish("preview-stopped")

    def stop_preview(self):
        """Public: the app closing ends a preview."""
        self._stop_preview()

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
        # Wait for the task process to start, run, and write its log entry.
        # 4 s gives frozen EXEs on slower machines enough time to complete.
        self.after(4000, self._on_test_done)

    def _on_test_done(self):
        """Called after the test-task wait: refresh status, check guard, open log."""
        import datetime as _dt
        self._refresh_status()

        # Check whether the guard blocked the run in the last 15 seconds.
        log_path = HELPERS_DIR / "_slideshow_log.txt"
        if log_path.exists():
            try:
                cutoff = _dt.datetime.now() - _dt.timedelta(seconds=15)
                recent_skipped = False
                for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if "Skipping: too soon" not in line:
                        continue
                    try:
                        if _dt.datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S") >= cutoff:
                            recent_skipped = True
                            break
                    except Exception:
                        pass
                if recent_skipped:
                    state    = load_state()
                    interval = state.get("interval_min", 10)
                    last_set = state.get("last_set", "?")
                    messagebox.showinfo(
                        "Task Fired — Wallpaper Unchanged",
                        "The task ran but the guard skipped the wallpaper change.\n\n"
                        "Last set:  {}\n"
                        "Interval:  {} min  (guard threshold: {:.0f} min)\n\n"
                        "The wallpaper will change automatically once the full "
                        "interval has elapsed.".format(last_set, interval, interval * 0.9),
                        parent=self)
            except Exception:
                pass

        self._view_log()

    def _view_log(self):
        """
        Print the recent rotation history into the app's console.

        It used to open a window of its own — which landed on top of the
        console at the moment the console was reporting what the slideshow had
        just done. That is the same thing that made these panels stop being
        dialogs; the log had no reason to stay one.
        """
        log_path = HELPERS_DIR / "_slideshow_log.txt"
        if not log_path.exists():
            self._console_log(
                "No slideshow log yet — expected: {}".format(log_path), "dim")
            return
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self._console_log(
                "Could not read the slideshow log: {}".format(exc), "red")
            return
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            self._console_log("The slideshow log is empty.", "dim")
            return
        shown = lines[-self.LOG_TAIL:]
        self._console_log("─" * 52, "dim")
        self._console_log("Slideshow log — {}{} line{}".format(
            "last {} of ".format(len(shown)) if len(shown) < len(lines) else "",
            len(lines), "" if len(lines) == 1 else "s"), "bold")
        self._console_log("   {}".format(log_path), "dim")
        for line in shown:
            self._console_log("   " + line, _log_tag(line))
        self._console_log("─" * 52, "dim")
