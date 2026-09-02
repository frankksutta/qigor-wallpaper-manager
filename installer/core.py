"""
core.py  —  install / uninstall logic, no GUI.

Shared by the interactive installer (install.py), the uninstaller
(uninstall.py), and the in-app updater, which reuses `install()` verbatim: an
update is just a reinstall performed by the *new* copy's interpreter over the
old install root. That is what makes runtime upgrades work at all — nothing can
overwrite the CPython DLLs it is itself running from, so the new runtime has to
be the one doing the copying.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import winreg
from datetime import datetime
from pathlib import Path

from .paths import (APP_ID, DISPLAY_NAME, PUBLISHER, ABOUT_URL, ENTRY_NAME,
                    LAUNCHER_NAME, SHORTCUT_NAME, ICON_NAME, VERSION_FILE,
                    UNINSTALL_CMD, UNINSTALL_KEY, PAYLOAD_DIRS,
                    install_root, start_menu_shortcut, desktop_shortcut,
                    bundled_python)
from .shortcuts import create_shortcut, remove_shortcut

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008

# Scheduled tasks the app registers. Kept here as literals rather than imported
# from app/ so the uninstaller still works when app/ is half-deleted or the
# import raises.
TASK_SLIDESHOW = "QiGorWallpaperSlideshow"
TASK_REMINDER  = "QiGorWallpaperReminder"
# Registered by versions before 0.7.3 and never used since; StartWhenAvailable
# on the main trigger replaced it.
TASK_LEGACY    = ("QiGorWallpaperSlideshow_OnLogon",)
TASK_NAMES     = (TASK_SLIDESHOW, TASK_REMINDER) + TASK_LEGACY


# ── Version metadata ──────────────────────────────────────────────────────────

def read_version(root: Path) -> dict:
    """Read a payload's version.json. Missing or corrupt reads as empty."""
    try:
        return json.loads((Path(root) / VERSION_FILE).read_text("utf-8"))
    except Exception:
        return {}


def version_tuple(s: str) -> tuple:
    """'0.7.4' → (0, 7, 4). Non-numeric tails sort below any number, so a
    release tagged '0.8-rc1' never displaces a released '0.8'."""
    out = []
    for part in str(s or "").split("."):
        digits = ""
        for ch in part:
            if not ch.isdigit():
                break
            digits += ch
        out.append(int(digits) if digits else -1)
    return tuple(out)


def is_newer(candidate: str, current: str) -> bool:
    a, b = version_tuple(candidate), version_tuple(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


# ── Payload validation ────────────────────────────────────────────────────────

def validate_payload(payload: Path) -> "str | None":
    """Return an error string if `payload` is not a usable app folder."""
    payload = Path(payload)
    checks = [
        (payload / "runtime" / "pythonw.exe", "the bundled Python runtime"),
        (payload / "app" / "app.py",          "the application package"),
        (payload / ENTRY_NAME,                "the entry point"),
    ]
    for path, what in checks:
        if not path.exists():
            return "This folder is missing {} ({}).".format(what, path.name)
    return None


# ── Process helpers ───────────────────────────────────────────────────────────

INSTANCE_LOCK = Path.home() / ".qigor-wallpaper" / "instance.lock"
LOG_FILE      = Path.home() / ".qigor-wallpaper" / "install_log.txt"


def _tee(log, what: str):
    """
    Wrap a log callable so everything it prints is also appended to disk.

    The installer window can be closed and the setup console closes itself the
    moment it finishes, so without a file there is no way to find out
    afterwards what happened — least of all for a failure the user only half
    saw go past.
    """
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handle = open(LOG_FILE, "a", encoding="utf-8")
        handle.write("\n===== {}  {} =====\n".format(
            datetime.now().isoformat(timespec="seconds"), what))
    except OSError:
        return log            # a log we cannot write is not worth failing over

    def tee(msg=""):
        try:
            handle.write(str(msg) + "\n")
            handle.flush()
        except OSError:
            pass
        log(msg)
    return tee


def note_failure(what: str, detail) -> Path:
    """Record an aborted install or uninstall, and return the log's path so the
    caller can tell the user where to look."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("{}  {} FAILED: {}\n".format(
                datetime.now().isoformat(timespec="seconds"), what, detail))
    except OSError:
        pass
    return LOG_FILE


def is_running() -> bool:
    """
    True if a copy of the app is running.

    Asks the same question the app asks itself at startup — can byte 0 of
    instance.lock be locked — rather than trusting the PID written in the file.
    A crashed instance leaves the PID behind but not the lock, and treating that
    stale number as "still running" would block every install until the user
    found and deleted a file they have never heard of.

    The PID is deliberately never read back. It is written at byte 0, which is
    the byte the running instance has locked, so reading it raises the very same
    "permission denied" the lock attempt does — and letting that bubble into a
    catch-all would report "nothing is running", the one wrong answer that
    actually costs something.
    """
    import msvcrt
    if not INSTANCE_LOCK.exists():
        return False
    try:
        with open(INSTANCE_LOCK, "a+") as f:   # "a+" never truncates the PID
            f.seek(0)
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            return False
    except OSError:
        # Cannot tell. Assume it is running: a refused install is recoverable,
        # a half-deleted one is not.
        return True


def close_running(log=print, timeout: float = 20.0) -> bool:
    """
    Ask a running copy to close, and wait for it. True if nothing is running by
    the end.

    WM_CLOSE rather than a kill: the app releases its lock, saves its window
    geometry and settings on the way out, and a killed instance would leave the
    lock file held until Windows reaped the handle.
    """
    import ctypes

    if not is_running():
        return True
    log("  QiGor is open — asking it to close…")

    title_prefix = DISPLAY_NAME + "  v"
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    def _enum(hwnd, _lparam):
        n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value.startswith(title_prefix):
                found.append(hwnd)
        return 1

    ctypes.windll.user32.EnumWindows(_enum, 0)
    for hwnd in found:
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_running():
            log("  closed.")
            return True
        time.sleep(0.4)
    return False


STILL_RUNNING_HINT = (
    "Close the QiGor Wallpaper Manager window and try again.\n\n"
    "If no QiGor window is open, a previous run left its lock behind — "
    "delete this file and retry:\n  {}".format(INSTANCE_LOCK))


def schedule_delete(path: Path, delay: int = 4):
    """
    Remove a folder from a detached cmd, once this process has exited.

    Used wherever the folder to delete is the one this interpreter is running
    out of — the uninstaller, and the staged installer clearing its own
    extraction. cwd is forced to the home directory because rmdir refuses to
    remove any process's working directory, and cmd.exe is Microsoft-signed, so
    it runs under Smart App Control without issue.
    """
    subprocess.Popen(
        'cmd /c timeout /t {} /nobreak >nul & rmdir /s /q "{}"'.format(delay, path),
        cwd=str(Path.home()), close_fds=True,
        creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW)


def sweep_temp(exclude: "Path | None" = None, log=None):
    """
    Delete leftovers from earlier updates.

    Each update extracts ~50 MB into %TEMP% and the copy that did the work
    cannot delete the folder it is running from, so without a sweep they
    accumulate one per update until Storage Sense happens to notice.
    """
    keep = str(Path(exclude).resolve()).lower() if exclude else None
    root = Path(tempfile.gettempdir())
    for pattern in ("qigor-update-*", "qigor-dl-*"):
        for stray in root.glob(pattern):
            if not stray.is_dir():
                continue
            here = str(stray.resolve()).lower()
            if keep and (keep == here or keep.startswith(here + os.sep)):
                continue                  # the payload we are installing from
            clear_readonly(stray)
            shutil.rmtree(stray, ignore_errors=True)
            if log and not stray.exists():
                log("  cleaned up {}".format(stray.name))


def wait_for_pid(pid: int, timeout: float = 30.0) -> bool:
    """Block until process `pid` exits. True if it is gone, False on timeout."""
    import ctypes
    SYNCHRONIZE = 0x00100000
    h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not h:
        return True                     # already gone, or not ours to wait on
    try:
        # WAIT_OBJECT_0 == 0; WAIT_TIMEOUT == 0x102
        return ctypes.windll.kernel32.WaitForSingleObject(
            h, int(timeout * 1000)) == 0
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def _retry(fn, attempts=12, delay=0.5, log=None, what=""):
    """
    Retry a filesystem operation that can lose a race with a running copy.

    The slideshow fires on a timer and briefly opens the runtime, so a copy can
    hit a sharing violation through no fault of the user. Six seconds covers a
    slideshow tick comfortably.
    """
    last = None
    for i in range(attempts):
        try:
            return fn()
        except OSError as e:
            last = e
            if i == 0 and log:
                log("    {} is in use — waiting…".format(what or "target"))
            time.sleep(delay)
    raise last


def clear_readonly(root: Path):
    """
    Strip the read-only attribute from a tree before writing into it.

    Windows refuses RemoveDirectory on a read-only *directory* and refuses to
    overwrite a read-only file, both with a bare ERROR_ACCESS_DENIED that reads
    like a lock and is not one. shutil.copytree copies the attribute along with
    the files, and OneDrive sets it on folders as a matter of course — so
    without this, one read-only folder anywhere upstream of a build quietly
    makes every future update fail. One pass is cheaper than defending each
    individual copy, and it is only a chmod per entry.
    """
    root = Path(root)
    if not root.exists():
        return
    for path in [root] + list(root.rglob("*")):
        try:
            if not (path.stat().st_mode & stat.S_IWRITE):
                path.chmod(path.stat().st_mode | stat.S_IWRITE)
        except OSError:
            pass


def _replace_dir(src: Path, dst: Path, log=print, what=""):
    """
    Put a fresh copy of `src` at `dst`, replacing whatever is there.

    The old directory is removed outright when it can be, and renamed aside when
    it cannot — a genuinely locked file must not be allowed to abort an update
    and leave the install half-written. Leftovers are swept on the next run.
    """
    if dst.exists():
        try:
            _retry(lambda: shutil.rmtree(dst), log=log, what=what)
        except OSError:
            aside = dst.with_name("{}.old-{}".format(dst.name, os.getpid()))
            log("    {} is locked — moving it aside".format(what or dst.name))
            dst.rename(aside)
    _retry(lambda: shutil.copytree(
        src, dst, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")),
        log=log, what=what)


def sweep_old(target: Path, log=None):
    """Delete directories a previous update had to rename aside."""
    for leftover in target.glob("*.old-*"):
        if leftover.is_dir():
            clear_readonly(leftover)
            shutil.rmtree(leftover, ignore_errors=True)
            if log and not leftover.exists():
                log("  cleaned up {}".format(leftover.name))


# ── Install ───────────────────────────────────────────────────────────────────

def install(payload: Path, target: "Path | None" = None, desktop: bool = True,
            log=print, wait_pid: "int | None" = None) -> Path:
    """
    Copy `payload` into `target` (default: the per-user install root), create
    shortcuts, and register the uninstall entry. Returns the install root.

    Re-running over an existing install is the upgrade path and is safe.
    """
    payload = Path(payload).resolve()
    target  = Path(target).resolve() if target else install_root()
    log = _tee(log, "install {} → {}".format(payload.name, target))

    err = validate_payload(payload)
    if err:
        raise RuntimeError(err)
    if payload == target:
        raise RuntimeError("Source and destination are the same folder.")

    if wait_pid:
        log("Waiting for the running copy to close…")
        wait_for_pid(wait_pid)

    # Copying over a running install fails on the Python DLLs it has open, and
    # _retry's few seconds will not outlast someone who simply left the window
    # open. Ask it to close instead.
    if not close_running(log=log):
        raise RuntimeError(
            "QiGor is still running and would not close.\n\n" + STILL_RUNNING_HINT)

    meta = read_version(payload)
    log("Installing {} {} to:".format(DISPLAY_NAME, meta.get("build", "")))
    log("  " + str(target))
    target.mkdir(parents=True, exist_ok=True)
    clear_readonly(target)
    sweep_old(target, log=log)
    sweep_temp(exclude=payload, log=log)

    # app/ and installer/ are replaced wholesale so a module deleted upstream
    # does not linger and get imported. runtime/ is merged instead: it is 1,400
    # files that rarely change, and deleting it first would leave the install
    # unrunnable if the copy failed halfway.
    for name in PAYLOAD_DIRS:
        src = payload / name
        if not src.exists():
            continue
        log("  {}\\".format(name))
        if name == "runtime":
            _retry(lambda s=src, d=target / name: shutil.copytree(
                s, d, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")),
                log=log, what=name)
        else:
            _replace_dir(src, target / name, log=log, what=name)

    for name in (ENTRY_NAME, ICON_NAME, VERSION_FILE, "README.txt"):
        src = payload / name
        if src.exists():
            _retry(lambda s=src, n=name: shutil.copy2(s, target / n),
                   log=log, what=name)

    # Leave the install writable, so the next update is not blocked by an
    # attribute inherited from wherever this payload was built.
    clear_readonly(target)

    write_launchers(target)
    log("  launchers + uninstaller")

    stamp = dict(meta)
    stamp["installed_at"]   = datetime.now().isoformat(timespec="seconds")
    stamp["install_root"]   = str(target)
    (target / VERSION_FILE).write_text(
        json.dumps(stamp, indent=2), encoding="utf-8")

    made = create_app_shortcuts(target, desktop=desktop, log=log)
    register_uninstall(target, stamp, log=log)
    adopted = migrate_scheduled_tasks(target, log=log)

    log("")
    log("Installed. {} shortcut{} created.".format(made, "" if made == 1 else "s"))

    # Name the folder the old copy ran from. Not deleted — it may hold something
    # the user still wants, and that call is theirs, not the installer's.
    old_roots = {str(root) for _, root in adopted if root}
    for root in sorted(old_roots):
        log("")
        log("The slideshow was running from an older copy at:")
        log("  {}".format(root))
        log("It now runs from this install. You can delete that old folder.")
    return target


def write_launchers(target: Path, include_uninstaller: bool = True):
    """
    Write the .cmd entry points. The build tool calls this too, with
    include_uninstaller=False, so a freshly extracted zip does not offer to
    uninstall something that was never installed.

    These are batch files, not PowerShell: batch is interpreted by a
    Microsoft-signed cmd.exe and is not subject to WDAC script enforcement,
    whereas PowerShell drops to Constrained Language Mode under Smart App
    Control. `start ""` returns immediately so the console only blinks.
    """
    (target / LAUNCHER_NAME).write_text(
        "@echo off\r\n"
        'start "" "%~dp0runtime\\pythonw.exe" "%~dp0{}" %*\r\n'.format(ENTRY_NAME),
        encoding="ascii")
    if include_uninstaller:
        (target / UNINSTALL_CMD).write_text(
            "@echo off\r\n"
            'start "" "%~dp0runtime\\pythonw.exe" "%~dp0installer\\uninstall.py" %*\r\n',
            encoding="ascii")


def create_app_shortcuts(target: Path, desktop: bool = True, log=print) -> int:
    """
    Point shortcuts straight at runtime\\pythonw.exe rather than at the .cmd —
    a .cmd shortcut flashes a console window on every launch.
    """
    pyw  = bundled_python(target)
    entry = target / ENTRY_NAME
    icon  = target / ICON_NAME
    if not icon.exists():
        icon = target / "assets" / ICON_NAME
    args = '"{}"'.format(entry)

    made = 0
    wanted = [start_menu_shortcut()]
    if desktop:
        wanted.append(desktop_shortcut())
    for link in wanted:
        try:
            create_shortcut(link, pyw, arguments=args, working_dir=target,
                            icon=icon, description=DISPLAY_NAME)
            log("  shortcut: {}".format(link.parent))
            made += 1
        except OSError as e:
            log("  ! could not create {}: {}".format(link.name, e))
    return made


def register_uninstall(target: Path, meta: dict, log=print):
    """Add the Settings ▸ Apps entry. HKCU, so no elevation is needed."""
    try:
        size_kb = sum(f.stat().st_size for f in target.rglob("*")
                      if f.is_file()) // 1024
    except OSError:
        size_kb = 0
    uninstall_cmd = '"{}" "{}"'.format(bundled_python(target),
                                       target / "installer" / "uninstall.py")
    icon = target / ICON_NAME
    values = {
        "DisplayName":     DISPLAY_NAME,
        "DisplayVersion":  meta.get("build") or meta.get("version") or "",
        "Publisher":       PUBLISHER,
        "InstallLocation": str(target),
        "DisplayIcon":     str(icon if icon.exists() else bundled_python(target)),
        "UninstallString": uninstall_cmd,
        # What Settings and `winget uninstall` use for a non-interactive
        # removal. Without it winget falls back to UninstallString and leaves a
        # confirmation window the user never asked for sitting on the desktop.
        "QuietUninstallString": uninstall_cmd + " --silent",
        "URLInfoAbout":    ABOUT_URL,
        "InstallDate":     datetime.now().strftime("%Y%m%d"),
    }
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
            for name, val in values.items():
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
            for name, val in (("EstimatedSize", size_kb),
                              ("NoModify", 1), ("NoRepair", 1)):
                winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, val)
        log("  registered in Settings ▸ Apps")
    except OSError as e:
        log("  ! could not register uninstall entry: {}".format(e))


# ── Adopting tasks left behind by an older copy ───────────────────────────────

def _decode_schtasks(raw: bytes) -> str:
    """
    Decode schtasks output, whose encoding is not dependable.

    It writes UTF-8 with no BOM on current Windows but UTF-16 on other builds
    and locales, and a UTF-8 buffer that happens to be an even number of bytes
    decodes as UTF-16 *without raising* — into mojibake. So the encoding is
    picked by whether the result actually looks like the XML that was asked
    for, never by whether the decode succeeded.
    """
    order = (("utf-16", "utf-8-sig", "mbcs")
             if raw[:2] in (b"\xff\xfe", b"\xfe\xff")
             else ("utf-8-sig", "utf-16", "mbcs"))
    fallback = ""
    for encoding in order:
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        if "<?xml" in text or "<Task" in text:
            return text
        fallback = fallback or text
    return fallback


def _run_schtasks(args) -> "tuple[int, str]":
    r = subprocess.run(["schtasks"] + list(args), capture_output=True,
                       creationflags=CREATE_NO_WINDOW)
    return r.returncode, _decode_schtasks(r.stdout or b"")


def _task_action(xml: str) -> "tuple[str, str]":
    """Pull (Command, Arguments) out of a task definition."""
    cmd = re.search(r"<Command>(.*?)</Command>", xml, re.S)
    arg = re.search(r"<Arguments>(.*?)</Arguments>", xml, re.S)
    return (cmd.group(1).strip() if cmd else "",
            arg.group(1).strip() if arg else "")


def _split_arguments(arguments: str) -> "tuple[str, str]":
    """
    Split a task's Arguments into (script path, trailing flags).

    Two shapes exist in the wild: the frozen EXE took bare flags ("--next"),
    while script mode passes the .pyw quoted first. Both have to survive the
    rewrite, because the flags are what select the headless mode.
    """
    m = re.match(r'\s*"([^"]+)"\s*(.*)', arguments, re.S)
    if m:
        return m.group(1), m.group(2).strip()
    return "", arguments.strip()


def _old_root_of(command: str, script: str) -> "Path | None":
    """The folder an existing task is running the app out of."""
    for candidate in (script, command):
        if candidate:
            try:
                return Path(candidate).resolve().parent
            except OSError:
                continue
    return None


def migrate_scheduled_tasks(target: Path, log=print) -> list:
    """
    Re-point slideshow and reminder tasks that still run an older copy.

    Installing does not otherwise touch tasks — on an ordinary upgrade the task
    already points at target\\runtime\\pythonw.exe, which never moves, and
    rewriting it would be pure risk. But someone coming from the old frozen EXE
    or a loose portable folder has a task aimed somewhere else entirely, and
    leaving it means the slideshow silently keeps driving the old copy, or fails
    every ten minutes once that copy is deleted. Task Scheduler never surfaces
    either outcome.

    The whole task XML is reused and only the Exec action rewritten, so the
    interval, trigger and every other setting the user chose are preserved
    rather than guessed at.

    Returns [(task_name, old_root_or_None), …] for the ones actually adopted.
    """
    adopted = []
    new_cmd   = str(bundled_python(target))
    new_entry = str(Path(target) / ENTRY_NAME)

    for name in TASK_LEGACY:
        rc, _ = _run_schtasks(["/query", "/tn", name])
        if rc == 0:
            _run_schtasks(["/delete", "/f", "/tn", name])
            log("  removed obsolete task: {}".format(name))

    for name in (TASK_SLIDESHOW, TASK_REMINDER):
        rc, xml = _run_schtasks(["/query", "/tn", name, "/xml"])
        if rc != 0 or "<Task" not in xml:
            continue

        command, arguments = _task_action(xml)
        if not command:
            continue
        if str(target).lower() in command.lower():
            continue                      # already ours — an ordinary upgrade

        script, flags = _split_arguments(arguments)
        old_root = _old_root_of(command, script)
        new_args = '"{}"{}'.format(new_entry, " " + flags if flags else "")

        # Lambda replacements, not strings: these paths are full of backslashes
        # and re.sub reads \U in a replacement string as an escape sequence.
        patched = re.sub(r"<Command>.*?</Command>",
                         lambda _m: "<Command>{}</Command>".format(
                             _xml_escape(new_cmd)),
                         xml, count=1, flags=re.S)
        patched = re.sub(r"<Arguments>.*?</Arguments>",
                         lambda _m: "<Arguments>{}</Arguments>".format(
                             _xml_escape(new_args)),
                         patched, count=1, flags=re.S)
        if "<Arguments>" not in patched:
            # The EXE-era task had no Arguments element at all; add one.
            patched = patched.replace(
                "</Command>",
                "</Command>\n      <Arguments>{}</Arguments>".format(
                    _xml_escape(new_args)), 1)

        tmp = Path(tempfile.gettempdir()) / "_qigor_migrate_{}.xml".format(name)
        try:
            tmp.write_text(patched, encoding="utf-16")
            rc, out = _run_schtasks(["/create", "/f", "/tn", name,
                                     "/xml", str(tmp)])
        finally:
            tmp.unlink(missing_ok=True)

        if rc == 0:
            adopted.append((name, old_root))
            log("  adopted scheduled task: {}".format(name))
        else:
            log("  ! could not re-point {} — open Slideshow ▸ Start to fix it"
                .format(name))

    return adopted


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def launch(target: Path):
    """Start the installed app, detached, so the installer can exit."""
    subprocess.Popen([str(bundled_python(target)), str(Path(target) / ENTRY_NAME)],
                     cwd=str(target), close_fds=True,
                     creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW)


# ── Uninstall ─────────────────────────────────────────────────────────────────

def stop_scheduled_tasks(log=print) -> int:
    removed = 0
    for name in TASK_NAMES:
        try:
            r = subprocess.run(["schtasks", "/delete", "/f", "/tn", name],
                               capture_output=True, text=True,
                               creationflags=CREATE_NO_WINDOW)
            if r.returncode == 0:
                log("  removed scheduled task: {}".format(name))
                removed += 1
        except Exception:
            pass
    return removed


def uninstall(target: "Path | None" = None, remove_settings: bool = False,
              log=print):
    """
    Remove shortcuts, tasks, and the registry entry, then delete the install
    folder from a detached cmd.exe.

    The folder cannot delete itself while this interpreter is running out of it,
    which is why the last step is handed to cmd: it waits two seconds for this
    process to exit, then removes the tree. cmd.exe is Microsoft-signed, so it
    runs under Smart App Control without issue.
    """
    target = Path(target).resolve() if target else install_root()
    log = _tee(log, "uninstall {}".format(target))

    log("Removing {}…".format(DISPLAY_NAME))

    # Before anything is removed, not after. A running instance holds the Python
    # DLLs open, so the folder deletion below would half-succeed — and by then
    # the Settings ▸ Apps entry that leads back here would already be gone,
    # leaving a wreck with no supported way to finish removing it.
    if not close_running(log=log):
        raise RuntimeError(
            "QiGor is still running and would not close. Nothing has been "
            "removed.\n\n" + STILL_RUNNING_HINT)

    stop_scheduled_tasks(log=log)

    for link in (start_menu_shortcut(), desktop_shortcut()):
        if remove_shortcut(link):
            log("  removed shortcut: {}".format(link.name))

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
        log("  removed Settings ▸ Apps entry")
    except OSError:
        pass

    if remove_settings:
        settings = Path.home() / ".qigor-wallpaper"
        try:
            shutil.rmtree(settings, ignore_errors=True)
            log("  removed settings and saved wallpapers: {}".format(settings))
        except OSError:
            pass

    sweep_temp(exclude=Path(__file__).resolve().parent.parent, log=log)

    if target.exists():
        # rmdir /s /q refuses read-only entries just as rmtree does.
        clear_readonly(target)
        log("  scheduling removal of {}".format(target))
        schedule_delete(target)

    log("")
    log("Uninstalled.")
