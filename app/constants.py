"""
constants.py  —  QiGor Wallpaper Manager
All app-wide constants: name, version, styles, paths, themes, colors.
"""
from pathlib import Path

APP_NAME    = "QiGor Wallpaper Manager"
APP_VERSION = "0.7"
APP_SLUG    = "qigor-wallpaper"
RECENT_MAX  = 8

WALLPAPER_STYLES = {
    "Fill":    ("10", "0"),
    "Fit":     ("6",  "0"),
    "Stretch": ("2",  "0"),
    "Tile":    ("0",  "1"),
    "Center":  ("0",  "0"),
    "Span":    ("22", "0"),
}

STORE_DIR   = Path.home() / ".qigor-wallpaper" / "saved_wallpapers"
HELPERS_DIR = Path.home() / ".qigor-wallpaper" / "helpers"

WIN_IMAGE_SOURCES = [
    {
        "label": "My Wallpaper Store",
        "path":  STORE_DIR,
        "tip":   "Images saved by this app. Safe to clean out manually.",
    },
    {
        "label": "Windows Cached Wallpaper",
        "path":  Path.home() / "AppData/Roaming/Microsoft/Windows/Themes/CachedFiles",
        "tip":   "Windows keeps a scaled copy of your last-set wallpaper here.\n"
                 "Useful to recover a wallpaper you forgot to save.",
    },
    {
        "label": "Windows Spotlight (daily images)",
        "path":  Path.home() / "AppData/Local/Packages"
                 "/Microsoft.Windows.ContentDeliveryManager_cw5n1h2txyewy"
                 "/LocalState/Assets",
        "tip":   "Daily rotating Spotlight images.\n"
                 "Files have NO extension — rename to .jpg to use them.\n"
                 "Use the 'Copy Spotlight Images' button to extract them.",
    },
    {
        "label": "Built-in Windows Wallpapers",
        "path":  Path("C:/Windows/Web/Wallpaper"),
        "tip":   "Windows built-in theme wallpapers (Windows Glow, etc.).",
    },
    {
        "label": "Lock Screen Images",
        "path":  Path.home() / "AppData/Local/Microsoft/Windows/SystemData",
        "tip":   "Lock screen images (may require admin to browse).",
    },
]

THEMES = {
    "dark": {
        "bg":         "#1e1e1e",
        "fg":         "#d4d4d4",
        "entry_bg":   "#2d2d2d",
        "entry_fg":   "#ffffff",
        "btn_bg":     "#3a3a3a",
        "btn_fg":     "#ffffff",
        "console_bg": "#0f0f0f",
        "console_fg": "#d4d4d4",
        "status_bg":  "#252526",
        "status_fg":  "#cccccc",
        "invalid_bg": "#4a1a1a",
        "invalid_fg": "#ff8888",
    },
    "light": {
        "bg":         "#f3f3f3",
        "fg":         "#000000",
        "entry_bg":   "#ffffff",
        "entry_fg":   "#000000",
        "btn_bg":     "#e1e1e1",
        "btn_fg":     "#000000",
        "console_bg": "#ffffff",
        "console_fg": "#000000",
        "status_bg":  "#e0e0e0",
        "status_fg":  "#333333",
        "invalid_bg": "#ffe0e0",
        "invalid_fg": "#cc0000",
    },
}

BTN_COLORS = {
    "primary": {"bg": "#0e639c", "fg": "#ffffff", "active": "#1177bb"},
    "success": {"bg": "#1a6b2e", "fg": "#ffffff", "active": "#1e8038"},
    "warning": {"bg": "#7a5c00", "fg": "#ffffff", "active": "#9a7400"},
    "danger":  {"bg": "#7a1c1c", "fg": "#ffffff", "active": "#9e2020"},
    "cancel":  {"bg": "#5a3a00", "fg": "#ffffff", "active": "#7a5000"},
}

CONSOLE_COLORS = {
    "dark": {
        "green":   "#4cff4c",
        "red":     "#ff5555",
        "yellow":  "#ffff55",
        "cyan":    "#55ffff",
        "magenta": "#ff79c6",
        "blue":    "#7aafff",
        "dim":     "#666666",
        "bold":    "#ffffff",
    },
    "light": {
        "green":   "#1a7a1a",
        "red":     "#cc0000",
        "yellow":  "#8a6000",
        "cyan":    "#006b6b",
        "magenta": "#9b1f7a",
        "blue":    "#1a4f9e",
        "dim":     "#999999",
        "bold":    "#111111",
    },
}
