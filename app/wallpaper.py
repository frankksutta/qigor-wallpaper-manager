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

from .constants import WALLPAPER_STYLES, STORE_DIR


# ── Image file extensions we recognise ───────────────────────────────────────
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
              ".tiff", ".tif", ".avif", ".heic", ".svg"}


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
    """Returns (is_on, detail_str)."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
            0, winreg.KEY_READ)
        try:
            rotating, _ = winreg.QueryValueEx(key, "RotatingLockScreenEnabled")
        except FileNotFoundError:
            rotating = 1
        winreg.CloseKey(key)
        is_on = (rotating != 0)
        detail = f"RotatingLockScreenEnabled = {rotating} ({'ON' if is_on else 'OFF'})"
        return is_on, detail
    except Exception as e:
        return False, f"Could not read registry: {e}"


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


def write_lockscreen_helper(img_path=None, mode="set") -> Path:
    """
    Write _lockscreen_helper.py next to the main app.
    mode='set'     — writes PersonalizationCSP with img_path
    mode='release' — deletes PersonalizationCSP entirely
    """
    import sys
    app_dir = Path(sys.argv[0]).resolve().parent
    helper  = app_dir / "_lockscreen_helper.py"
    img_arg = str(img_path) if img_path else ""
    helper.write_text(f'''\
#!/usr/bin/env python
"""Lock screen helper — launched elevated by QiGor Wallpaper Manager.
Writes or deletes PersonalizationCSP registry key and exits."""
import sys, winreg, datetime, os

MODE     = "{mode}"
IMG_PATH = r"{img_arg}"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_lockscreen_helper_log.txt")

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{{datetime.datetime.now():%Y-%m-%d %H:%M:%S}}  {{msg}}\\n")

CSP_ROOT = winreg.HKEY_LOCAL_MACHINE
CSP_PATH = r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\PersonalizationCSP"

def set_lock_screen(path):
    try:
        try:
            key = winreg.OpenKey(CSP_ROOT, CSP_PATH, 0,
                                 winreg.KEY_SET_VALUE | winreg.KEY_CREATE_SUB_KEY)
        except FileNotFoundError:
            key = winreg.CreateKey(CSP_ROOT, CSP_PATH)
        winreg.SetValueEx(key, "LockScreenImagePath",   0, winreg.REG_SZ, path)
        winreg.SetValueEx(key, "LockScreenImageUrl",    0, winreg.REG_SZ, path)
        winreg.SetValueEx(key, "LockScreenImageStatus", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        log(f"SET OK: {{path}}")
    except Exception as e:
        log(f"SET FAILED: {{e}}")
        sys.exit(1)

def release_lock_screen():
    try:
        try:
            key = winreg.OpenKey(CSP_ROOT, CSP_PATH, 0,
                                 winreg.KEY_SET_VALUE | winreg.KEY_CREATE_SUB_KEY)
            for val in ("LockScreenImagePath", "LockScreenImageUrl",
                        "LockScreenImageStatus"):
                try:
                    winreg.DeleteValue(key, val)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except FileNotFoundError:
            pass
        try:
            winreg.DeleteKey(CSP_ROOT,
                r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\PersonalizationCSP")
        except Exception:
            pass
        log("RELEASE OK")
    except Exception as e:
        log(f"RELEASE FAILED: {{e}}")
        sys.exit(1)

if __name__ == "__main__":
    if MODE == "release":
        release_lock_screen()
    else:
        set_lock_screen(IMG_PATH)
''', encoding="utf-8")
    return helper


def launch_helper_elevated(helper: Path, log_fn) -> bool:
    """Launch a .py helper elevated via UAC. Returns True if launched OK."""
    import sys
    py = Path(sys.executable)
    pythonw = py.parent / "pythonw.exe"
    if not pythonw.exists():
        pythonw = py
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", str(pythonw),
        f'"{helper}"', str(helper.parent), 0)
    if ret <= 32:
        if ret == 5:
            log_fn("◼  UAC cancelled.")
        else:
            log_fn(f"✖  Helper launch failed (code {ret}).")
        return False
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
