"""
wallpaper.py  —  QiGor Wallpaper Manager
Wallpaper apply, image download, lock screen, spotlight, registry helpers.
"""
from __future__ import annotations
import os
import re
import shutil
import sys
import urllib.request
import urllib.parse
import winreg
import ctypes
from datetime import datetime
from pathlib import Path

from .constants import (WALLPAPER_STYLES, STORE_DIR, HELPERS_DIR,
                        LOCKSCREEN_DIR, SPOTLIGHT_DIR)


# ── Image file extensions we recognise ───────────────────────────────────────
# No .svg — Windows cannot use vector images as wallpaper.
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
              ".tiff", ".tif", ".avif", ".heic"}


def find_python_exe() -> str:
    """
    Return the path to pythonw.exe (or python.exe) for running helper scripts.

    When frozen as a PyInstaller EXE, sys.executable is the EXE itself — not
    python.exe. We must find the real Python installation separately.

    Strategy (frozen only):
      1. PATH lookup (skipping Windows Store stub)
      2. Windows registry (PythonCore)
      3. Fallback to "python.exe"
    Script mode: sys.executable is always correct.
    """
    def _is_store_stub(path: str) -> bool:
        return "WindowsApps" in path

    if not getattr(sys, "frozen", False):
        py = Path(sys.executable)
        pw = py.parent / "pythonw.exe"
        return str(pw) if pw.exists() else str(py)

    import shutil as _sh
    for name in ("pythonw.exe", "python.exe"):
        found = _sh.which(name)
        if found and not _is_store_stub(found):
            return found

    try:
        import winreg as _wr
        for root in (_wr.HKEY_CURRENT_USER, _wr.HKEY_LOCAL_MACHINE):
            for base in (
                r"SOFTWARE\Python\PythonCore",
                r"SOFTWARE\WOW6432Node\Python\PythonCore",
            ):
                try:
                    with _wr.OpenKey(root, base) as bk:
                        versions, i = [], 0
                        while True:
                            try: versions.append(_wr.EnumKey(bk, i)); i += 1
                            except OSError: break
                        for ver in sorted(versions, reverse=True):
                            try:
                                with _wr.OpenKey(bk, ver + r"\InstallPath") as ik:
                                    ipath, _ = _wr.QueryValueEx(ik, "")
                                    for name in ("pythonw.exe", "python.exe"):
                                        c = Path(ipath) / name
                                        if c.exists() and not _is_store_stub(str(c)):
                                            return str(c)
                            except OSError:
                                continue
                except OSError:
                    continue
    except Exception:
        pass

    return "python.exe"


def store_images() -> list:
    """
    Every image in the store, newest first, subfolders and all.

    os.walk rather than rglob: it will not follow a directory junction round in
    a circle. Dot-folders are skipped — nobody keeps wallpapers in .git, and
    everybody has one.
    """
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    found = []
    for root, dirs, files in os.walk(STORE_DIR):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            p = Path(root) / name
            if p.suffix.lower() in IMAGE_EXTS:
                found.append(p)

    def _mtime(p):
        try:
            return p.stat().st_mtime
        except OSError:      # deleted between the walk and the sort
            return 0.0

    found.sort(key=_mtime, reverse=True)
    return found


def store_label(path) -> str:
    """
    How a store file is named in a list: bare at the top level, folder/name
    below it — two images called sunset.jpg in different folders have to stay
    tellable apart.
    """
    try:
        return str(Path(path).relative_to(STORE_DIR))
    except ValueError:
        return Path(path).name


def is_in_store(path) -> bool:
    """True if `path` is inside the store, however deep."""
    try:
        Path(path).resolve().relative_to(STORE_DIR.resolve())
        return True
    except (ValueError, OSError):
        return False


def normalize_src(src: str) -> str:
    """Normalize file:// URIs; pass everything else through."""
    if not src:
        return src
    if src.lower().startswith("file:///"):
        return urllib.request.url2pathname(src[7:])
    if src.lower().startswith("file://"):
        return src[7:]
    return src


def apply_wallpaper(path: str, style: str):
    """Write registry keys and call SystemParametersInfo."""
    style_val, tile_val = WALLPAPER_STYLES.get(style, ("10", "0"))
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Control Panel\Desktop", 0,
                         winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, style_val)
    winreg.SetValueEx(key, "TileWallpaper",  0, winreg.REG_SZ, tile_val)
    winreg.CloseKey(key)
    SPI_SETDESKWALLPAPER = 20
    SPIF_UPDATEINIFILE   = 0x01
    SPIF_SENDCHANGE      = 0x02
    ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, path,
        SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)


def download_image(url: str, log_fn, cancel_event=None) -> Path:
    """
    Download a URL to a file in STORE_DIR. Returns Path.
    Never overwrites an existing store file — appends a timestamp instead.
    cancel_event: optional threading.Event; raises InterruptedError when set.
    """
    log_fn(f"Downloading: {url}")
    parsed = urllib.parse.urlparse(url)
    name = Path(parsed.path).name or "wallpaper.jpg"
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    dest = STORE_DIR / name
    if dest.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = STORE_DIR / f"{dest.stem}_{ts}{dest.suffix}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    req = urllib.request.Request(url, headers=headers)
    chunks = []
    with urllib.request.urlopen(req, timeout=30) as resp:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError()
            chunk = resp.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
    data = b"".join(chunks)
    dest.write_bytes(data)
    log_fn(f"Downloaded {len(data)//1024} KB → {dest.name}")
    return dest


def get_current_wallpaper_path() -> str | None:
    """Read current wallpaper path from Windows registry."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Control Panel\Desktop", 0, winreg.KEY_READ)
        path, _ = winreg.QueryValueEx(key, "Wallpaper")
        winreg.CloseKey(key)
        return path or None
    except Exception:
        return None


# ── Lock screen ───────────────────────────────────────────────────────────────

def check_spotlight_status() -> tuple[bool, str]:
    """
    Returns (is_on, detail_str).
    Checks three registry locations — any one being Spotlight = return True.

    1. HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager
         RotatingLockScreenEnabled  DWORD  1=on
    2. HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Lock Screen\\Creative
         (key existing at all = Spotlight Creative is active on some builds)
    3. HKCU\\Software\\Policies\\Microsoft\\Windows\\Personalization
         LockScreenType  DWORD  2=Spotlight
    """
    reasons = []

    # Check 1: ContentDeliveryManager rotating lock screen flag
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
            0, winreg.KEY_READ)
        try:
            rotating, _ = winreg.QueryValueEx(key, "RotatingLockScreenEnabled")
            if rotating != 0:
                reasons.append(f"RotatingLockScreenEnabled={rotating}")
        except FileNotFoundError:
            # Key missing = default ON on most systems
            reasons.append("RotatingLockScreenEnabled=missing(default ON)")
        winreg.CloseKey(key)
    except Exception:
        pass

    # Check 2: Lock Screen Creative subkey (present when Spotlight is active)
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Lock Screen\Creative",
            0, winreg.KEY_READ)
        winreg.CloseKey(key)
        reasons.append("LockScreen\\Creative key exists")
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # Check 3: Policy LockScreenType=2
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Policies\Microsoft\Windows\Personalization",
            0, winreg.KEY_READ)
        try:
            ls_type, _ = winreg.QueryValueEx(key, "LockScreenType")
            if ls_type == 2:
                reasons.append(f"LockScreenType={ls_type}(Spotlight)")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception:
        pass

    is_on = len(reasons) > 0
    detail = ", ".join(reasons) if reasons else "all checks = OFF"
    return is_on, detail


def disable_spotlight(log_fn):
    """Turn off Windows Spotlight for the lock screen."""
    try:
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
            0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "RotatingLockScreenEnabled",        0, winreg.REG_DWORD, 0)
        winreg.SetValueEx(key, "RotatingLockScreenOverlayEnabled", 0, winreg.REG_DWORD, 0)
        winreg.SetValueEx(key, "SoftLandingEnabled",               0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        log_fn("✔  Spotlight disabled via registry.")
        log_fn("   (Settings → Personalization → Lock screen will now show 'Picture')")
    except PermissionError:
        log_fn("⚠  Could not disable Spotlight — registry access denied.")
    except Exception as e:
        log_fn(f"⚠  Could not disable Spotlight: {e}")


def enable_spotlight(log_fn):
    """Re-enable Windows Spotlight for the lock screen."""
    try:
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
            0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "RotatingLockScreenEnabled",        0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "RotatingLockScreenOverlayEnabled", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "SoftLandingEnabled",               0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        log_fn("✔  Spotlight re-enabled.")
    except Exception as e:
        log_fn(f"⚠  Could not enable Spotlight: {e}")


def csp_is_set() -> bool:
    """Return True if PersonalizationCSP lock screen key exists."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP",
            0, winreg.KEY_READ)
        winreg.QueryValueEx(key, "LockScreenImagePath")
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _set_lockscreen_headless(img_path: str):
    """
    Runs elevated (via UAC re-launch with --set-lockscreen).
    Writes PersonalizationCSP registry key.
    """
    import datetime as _dt
    log_file = HELPERS_DIR / "_lockscreen_helper_log.txt"
    HELPERS_DIR.mkdir(parents=True, exist_ok=True)

    def log(msg):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "  " + msg + "\n")

    CSP_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP"
    log("SET called: " + img_path)
    try:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CSP_PATH, 0,
                                 winreg.KEY_SET_VALUE | winreg.KEY_CREATE_SUB_KEY)
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, CSP_PATH)
        winreg.SetValueEx(key, "LockScreenImagePath",   0, winreg.REG_SZ, img_path)
        winreg.SetValueEx(key, "LockScreenImageUrl",    0, winreg.REG_SZ, img_path)
        winreg.SetValueEx(key, "LockScreenImageStatus", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        log("SET OK")
    except Exception as e:
        log("SET FAILED: " + str(e))
        import sys; sys.exit(1)


def _release_lockscreen_headless():
    """
    Runs elevated (via UAC re-launch with --release-lockscreen).
    Deletes PersonalizationCSP registry key.
    """
    import datetime as _dt
    log_file = HELPERS_DIR / "_lockscreen_helper_log.txt"
    HELPERS_DIR.mkdir(parents=True, exist_ok=True)

    def log(msg):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "  " + msg + "\n")

    CSP_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP"
    log("RELEASE called")
    try:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CSP_PATH, 0,
                                 winreg.KEY_SET_VALUE | winreg.KEY_CREATE_SUB_KEY)
            for val in ("LockScreenImagePath", "LockScreenImageUrl", "LockScreenImageStatus"):
                try: winreg.DeleteValue(key, val)
                except FileNotFoundError: pass
            winreg.CloseKey(key)
        except FileNotFoundError:
            pass
        try:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, CSP_PATH)
        except Exception:
            pass
        log("RELEASE OK")
    except Exception as e:
        log("RELEASE FAILED: " + str(e))
        import sys; sys.exit(1)


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize",         ctypes.c_uint32),
        ("fMask",          ctypes.c_ulong),
        ("hwnd",           ctypes.c_void_p),
        ("lpVerb",         ctypes.c_wchar_p),
        ("lpFile",         ctypes.c_wchar_p),
        ("lpParameters",   ctypes.c_wchar_p),
        ("lpDirectory",    ctypes.c_wchar_p),
        ("nShow",          ctypes.c_int),
        ("hInstApp",       ctypes.c_void_p),
        ("lpIDList",       ctypes.c_void_p),
        ("lpClass",        ctypes.c_wchar_p),
        ("hkeyClass",      ctypes.c_void_p),
        ("dwHotKey",       ctypes.c_uint32),
        ("hIconOrMonitor", ctypes.c_void_p),
        ("hProcess",       ctypes.c_void_p),
    ]


def launch_elevated(mode: str, img_path: str, log_fn) -> bool:
    """
    Re-launch THIS EXE (or pyw) elevated via UAC with --set-lockscreen or
    --release-lockscreen, and WAIT for the helper to finish (including the
    time the user spends on the UAC prompt) so callers can verify the
    registry immediately after this returns True.
    """
    if getattr(sys, "frozen", False):
        exe  = sys.executable
        args = '"--{}" "{}"'.format(mode, img_path) if img_path else '"--{}"'.format(mode)
        workdir = str(Path(exe).parent)
    else:
        exe = find_python_exe()
        pyw = str(Path(sys.argv[0]).resolve())
        args = '"{}" "--{}" "{}"'.format(pyw, mode, img_path) if img_path \
               else '"{}" "--{}"'.format(pyw, mode)
        workdir = str(Path(pyw).parent)

    SEE_MASK_NOCLOSEPROCESS = 0x40
    shell32  = ctypes.WinDLL("shell32",  use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    info = _SHELLEXECUTEINFOW()
    info.cbSize       = ctypes.sizeof(info)
    info.fMask        = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb       = "runas"
    info.lpFile       = exe
    info.lpParameters = args
    info.lpDirectory  = workdir
    info.nShow        = 0

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        err = ctypes.get_last_error()
        if err == 1223:     # ERROR_CANCELLED — user declined the UAC prompt
            log_fn("◼  UAC cancelled.")
        else:
            log_fn("✖  Elevation failed (error {}).".format(err))
        return False

    if info.hProcess:
        kernel32.WaitForSingleObject(info.hProcess, 120_000)   # 2 min max
        kernel32.CloseHandle(info.hProcess)
    return True


def find_current_lock_screen_image() -> tuple[str | None, str]:
    """
    Find the currently active lock screen image from all possible sources.
    Returns (path_str_or_None, source_description).
    Checks in priority order:
    1. PersonalizationCSP (set by this app via UAC helper)
    2. Windows Themes cached file (Win10/11 Picture mode)
    3. Spotlight asset cache (most recent large file)
    """
    # 1. PersonalizationCSP — set by this app
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP",
            0, winreg.KEY_READ)
        path, _ = winreg.QueryValueEx(key, "LockScreenImagePath")
        winreg.CloseKey(key)
        if path and Path(path).exists():
            return path, "custom image set by this app (PersonalizationCSP)"
    except Exception:
        pass

    # 2. SystemData has per-user lock screen images in subdirs (Picture mode)
    system_data = LOCKSCREEN_DIR
    if system_data.exists():
        try:
            candidates = []
            for f in system_data.rglob("*"):
                if f.is_file() and f.stat().st_size > 50_000:
                    candidates.append(f)
            if candidates:
                newest = max(candidates, key=lambda f: f.stat().st_mtime)
                return str(newest), "Windows lock screen image (SystemData)"
        except Exception:
            pass

    # 3. Spotlight asset cache
    spotlight_dir = SPOTLIGHT_DIR
    if spotlight_dir.exists():
        try:
            big = [f for f in spotlight_dir.iterdir()
                   if f.is_file() and not f.suffix and f.stat().st_size > 100_000]
            if big:
                newest = max(big, key=lambda f: f.stat().st_mtime)
                return str(newest), "Windows Spotlight (daily rotating image)"
        except Exception:
            pass

    return None, "no lock screen image found"


def copy_spotlight_images(log_fn):
    """Copy all Spotlight assets to STORE_DIR, renaming to .jpg."""
    from .constants import WIN_IMAGE_SOURCES
    src_dir = WIN_IMAGE_SOURCES[2]["path"]
    if not src_dir.exists():
        return 0, 0
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    copied = skipped = 0
    for f in src_dir.iterdir():
        if f.is_file() and not f.suffix:
            if f.stat().st_size < 100_000:
                skipped += 1
                continue
            dest = STORE_DIR / f"spotlight_{f.name}.jpg"
            if not dest.exists():
                shutil.copy2(str(f), str(dest))
                copied += 1
    return copied, skipped
