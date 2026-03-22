"""
wallpaper.py  —  QiGor Wallpaper Manager
Wallpaper apply, image download, lock screen, spotlight, registry helpers.
"""
from __future__ import annotations
import re
import shutil
import threading
import time
import urllib.request
import urllib.parse
import winreg
import ctypes
import os
from datetime import datetime
from pathlib import Path

from .constants import WALLPAPER_STYLES, STORE_DIR, HELPERS_DIR


# ── Image file extensions we recognise ───────────────────────────────────────
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
              ".tiff", ".tif", ".avif", ".heic", ".svg"}



import sys


def find_python_exe() -> str:
    """
    Return the path to pythonw.exe (or python.exe) for running helper scripts.

    When frozen as a PyInstaller EXE, sys.executable is the EXE itself — not
    python.exe. We must find the real Python installation separately.

    Strategy (frozen only):
      1. PATH lookup
      2. Windows registry (PythonCore)
      3. Fallback to "python.exe"
    Script mode: sys.executable is always correct.
    """
    if not getattr(sys, "frozen", False):
        py = Path(sys.executable)
        pw = py.parent / "pythonw.exe"
        return str(pw) if pw.exists() else str(py)

    # Frozen — find real Python
    import shutil as _sh
    for name in ("pythonw.exe", "python.exe"):
        found = _sh.which(name)
        if found:
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
                                        if c.exists():
                                            return str(c)
                            except OSError:
                                continue
                except OSError:
                    continue
    except Exception:
        pass

    return "python.exe"


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


def download_image(url: str, log_fn) -> Path:
    """Download a URL to a temp file in STORE_DIR. Returns Path."""
    log_fn(f"Downloading: {url}")
    parsed = urllib.parse.urlparse(url)
    name = Path(parsed.path).name or "wallpaper.jpg"
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    dest = STORE_DIR / name
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
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


def launch_elevated(mode: str, img_path: str, log_fn) -> bool:
    """
    Re-launch THIS EXE (or pyw) elevated via UAC with --set-lockscreen or
    --release-lockscreen. No external Python or helper script needed.
    """
    if getattr(sys, "frozen", False):
        exe = sys.executable
        args = '"--{}" "{}"'.format(mode, img_path) if img_path else '"--{}"'.format(mode)
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, args, str(Path(exe).parent), 0)
    else:
        from .wallpaper import find_python_exe  # noqa — self ref ok
        py  = find_python_exe()
        pyw = str(Path(sys.argv[0]).resolve())
        args = '"{}" "--{}" "{}"'.format(pyw, mode, img_path) if img_path \
               else '"{}" "--{}"'.format(pyw, mode)
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", py, args, str(Path(pyw).parent), 0)

    if ret <= 32:
        if ret == 5:
            log_fn("◼  UAC cancelled.")
        else:
            log_fn("✖  Elevation failed (code {}).".format(ret))
        return False
    return True


# Keep old name as alias so callers don't break
def write_lockscreen_helper(img_path=None, mode="set"):
    """Deprecated — returns None. Elevation now done via launch_elevated()."""
    return None


def launch_helper_elevated(helper, log_fn) -> bool:
    """Deprecated alias — calls launch_elevated() instead."""
    mode = "release-lockscreen" if helper is None else "set-lockscreen"
    return launch_elevated(mode, "", log_fn)


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

    # 2. Windows Themes cached wallpaper paths (Picture mode)
    cached_paths = [
        Path.home() / "AppData/Local/Microsoft/Windows/SystemData",
        Path.home() / "AppData/Roaming/Microsoft/Windows/Themes/CachedFiles",
    ]
    # SystemData has per-user lock screen in subdirs
    system_data = Path.home() / "AppData/Local/Microsoft/Windows/SystemData"
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
    spotlight_dir = (Path.home() /
        "AppData/Local/Packages"
        "/Microsoft.Windows.ContentDeliveryManager_cw5n1h2txyewy"
        "/LocalState/Assets")
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
