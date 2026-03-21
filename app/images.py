"""
images.py  —  QiGor Wallpaper Manager
Loads bundled image assets from the assets/ folder next to this package.
"""
import sys
from pathlib import Path

# assets/ sits alongside the app/ package directory
_ASSETS_DIR = Path(sys.argv[0]).resolve().parent / "assets"


def load_bundled_image(filename):
    """Load an image from assets/. Returns PIL Image (RGB) or None."""
    try:
        from PIL import Image
        p = _ASSETS_DIR / filename
        if p.exists():
            return Image.open(str(p)).convert("RGB")
    except Exception:
        pass
    return None
