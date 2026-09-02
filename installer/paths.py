"""
paths.py  —  where an installed copy lives, and the Windows folders it writes to.

Everything is per-user. %LOCALAPPDATA% needs no elevation, so installing never
raises a UAC prompt and works on a locked-down work machine.

Desktop and Start Menu are resolved through SHGetKnownFolderPath rather than by
joining onto the home directory: OneDrive folder redirection moves Desktop out
from under %USERPROFILE%, and a hardcoded join then drops the shortcut somewhere
the user never sees. This project's own repo sits inside a redirected OneDrive
tree, so that is not a hypothetical.
"""
import ctypes
import os
from ctypes import wintypes
from pathlib import Path

APP_ID        = "QiGorWallpaperManager"
DISPLAY_NAME  = "QiGor Wallpaper Manager"
PUBLISHER     = "Early Buddhism Meditation Preservation Society"
ABOUT_URL     = "https://github.com/frankksutta/qigor-wallpaper-manager"

ENTRY_NAME    = "qigor_wallpaper_manager.pyw"
LAUNCHER_NAME = "QiGor Wallpaper Manager.cmd"
SHORTCUT_NAME = "QiGor Wallpaper Manager.lnk"
ICON_NAME     = "qigor_wallpaper_manager.ico"
VERSION_FILE  = "version.json"
UNINSTALL_CMD = "Uninstall.cmd"

UNINSTALL_KEY = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
                 "\\" + APP_ID)

# Directories copied from the payload into the install root. Anything else in
# the zip (README.txt, the launcher) is handled by name.
PAYLOAD_DIRS  = ("runtime", "app", "assets", "installer")


# ── Known folders ─────────────────────────────────────────────────────────────

_FOLDERID = {
    "desktop":      "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "programs":     "{A77F5D77-2E2B-44C3-A6A2-ABA601054A51}",
    "localappdata": "{F1B32785-6FBA-4FCF-9D55-7B8E7F157091}",
}

_ENV_FALLBACK = {
    "desktop":      lambda: Path.home() / "Desktop",
    "programs":     lambda: Path(os.environ["APPDATA"]) / "Microsoft" / "Windows"
                            / "Start Menu" / "Programs",
    "localappdata": lambda: Path(os.environ["LOCALAPPDATA"]),
}


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


def guid(s: str) -> _GUID:
    """Parse a '{...}' GUID string into the struct COM calls expect."""
    g = _GUID()
    hr = ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
    if hr != 0:
        raise OSError("CLSIDFromString({}) failed: 0x{:08X}".format(s, hr & 0xFFFFFFFF))
    return g


def known_folder(key: str) -> Path:
    """Resolve a Windows known folder, falling back to the environment."""
    try:
        fid = guid(_FOLDERID[key])
        out = ctypes.c_wchar_p()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(fid), 0, None, ctypes.byref(out))
        if hr == 0:
            try:
                return Path(out.value)
            finally:
                ctypes.windll.ole32.CoTaskMemFree(out)
    except Exception:
        pass
    return _ENV_FALLBACK[key]()


# ── Locations ─────────────────────────────────────────────────────────────────

def install_root() -> Path:
    """Where an installed copy lives. Stable across updates."""
    return known_folder("localappdata") / "Programs" / APP_ID


def start_menu_shortcut() -> Path:
    return known_folder("programs") / SHORTCUT_NAME


def desktop_shortcut() -> Path:
    return known_folder("desktop") / SHORTCUT_NAME


def payload_root() -> Path:
    """
    The folder holding the copy of the app this code belongs to — the extracted
    zip when running the installer, or the install root when running installed.
    """
    return Path(__file__).resolve().parent.parent


def is_installed_copy(root: "Path | None" = None) -> bool:
    """True when `root` is the per-user install location rather than a loose folder."""
    root = root or payload_root()
    try:
        return root.resolve() == install_root().resolve()
    except Exception:
        return False


def bundled_python(root: Path, windowed: bool = True) -> Path:
    """The signed interpreter inside a payload. This path never moves, which is
    what lets the slideshow's scheduled task survive every update."""
    return root / "runtime" / ("pythonw.exe" if windowed else "python.exe")
