"""
images.py  —  QiGor Wallpaper Manager
Loads bundled image assets from the assets/ folder.
Handles both script mode and PyInstaller frozen EXE correctly.
"""
import sys
from pathlib import Path


def _assets_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets"
    return Path(sys.argv[0]).resolve().parent / "assets"


def load_bundled_image(filename):
    """Load an image from assets/. Returns PIL Image (RGB) or None."""
    try:
        from PIL import Image
        p = _assets_dir() / filename
        if p.exists():
            return Image.open(str(p)).convert("RGB")
    except Exception:
        pass
    return None
