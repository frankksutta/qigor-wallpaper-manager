"""
preview.py  —  QiGor Wallpaper Manager
Image preview fetching, reflow/composite, physical screen size detection.
"""
from __future__ import annotations
import io
import threading
import urllib.request
from pathlib import Path


from .wallpaper import normalize_src

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def get_physical_screen_size(root) -> tuple[int, int]:
    """
    Return true physical pixel dimensions of the primary monitor.
    Uses ctypes GetDeviceCaps to avoid DPI-scaled logical values.
    """
    try:
        import ctypes
        dc = ctypes.windll.user32.GetDC(0)
        DESKTOPHORZRES = 118
        DESKTOPVERTRES = 117
        pw = ctypes.windll.gdi32.GetDeviceCaps(dc, DESKTOPHORZRES)
        ph = ctypes.windll.gdi32.GetDeviceCaps(dc, DESKTOPVERTRES)
        ctypes.windll.user32.ReleaseDC(0, dc)
        if pw > 0 and ph > 0:
            return pw, ph
    except Exception:
        pass
    return root.winfo_screenwidth(), root.winfo_screenheight()


def fetch_preview_image(src: str) -> Image.Image:
    """
    Load a PIL Image from a local path or URL. Returns RGB Image.
    Raises on failure.
    """
    src = normalize_src(src)
    is_url = src.lower().startswith(("http://", "https://"))
    if is_url:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        req = urllib.request.Request(src, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data))
    else:
        img = Image.open(src)
    return img.convert("RGB")


def composite_preview(img: Image.Image, style: str,
                      canvas_w: int, canvas_h: int,
                      screen_w: int, screen_h: int) -> Image.Image:
    """
    Composite img onto a canvas of canvas_w×canvas_h simulating the
    selected wallpaper style. Returns a new PIL Image.
    """
    img_w, img_h = img.size
    canvas = Image.new("RGB", (canvas_w, canvas_h), (30, 30, 30))

    if style == "Fill":
        scale = max(canvas_w / img_w, canvas_h / img_h)
        nw, nh = int(img_w * scale), int(img_h * scale)
        resized = img.resize((nw, nh), Image.LANCZOS)
        x, y = (nw - canvas_w) // 2, (nh - canvas_h) // 2
        canvas.paste(resized.crop((x, y, x + canvas_w, y + canvas_h)), (0, 0))

    elif style == "Fit":
        scale = min(canvas_w / img_w, canvas_h / img_h)
        nw, nh = int(img_w * scale), int(img_h * scale)
        resized = img.resize((nw, nh), Image.LANCZOS)
        canvas.paste(resized, ((canvas_w - nw) // 2, (canvas_h - nh) // 2))

    elif style == "Stretch":
        canvas.paste(img.resize((canvas_w, canvas_h), Image.LANCZOS), (0, 0))

    elif style == "Tile":
        tile_scale = min(1.0,
                         (canvas_w // 3) / img_w,
                         (canvas_h // 3) / img_h)
        tile_w = max(int(img_w * tile_scale), 4)
        tile_h = max(int(img_h * tile_scale), 4)
        tile = img.resize((tile_w, tile_h), Image.LANCZOS)
        for ty in range(0, canvas_h, tile_h):
            for tx in range(0, canvas_w, tile_w):
                canvas.paste(tile, (tx, ty))

    elif style == "Center":
        px_scale_w = canvas_w / screen_w
        px_scale_h = canvas_h / screen_h
        disp_w = min(int(img_w * px_scale_w), canvas_w)
        disp_h = min(int(img_h * px_scale_h), canvas_h)
        if disp_w > 0 and disp_h > 0:
            resized = img.resize((disp_w, disp_h), Image.LANCZOS)
            canvas.paste(resized,
                         ((canvas_w - disp_w) // 2, (canvas_h - disp_h) // 2))

    elif style == "Span":
        canvas.paste(img.resize((canvas_w, canvas_h), Image.LANCZOS), (0, 0))

    else:
        scale = min(canvas_w / img_w, canvas_h / img_h)
        nw, nh = int(img_w * scale), int(img_h * scale)
        resized = img.resize((nw, nh), Image.LANCZOS)
        canvas.paste(resized, ((canvas_w - nw) // 2, (canvas_h - nh) // 2))

    return canvas


def build_quality_label(img_w, img_h, sw, sh, style) -> str:
    if style in ("Fill", "Stretch", "Fit", "Span"):
        fit_ratio = min(img_w / sw, img_h / sh)
        if fit_ratio >= 1.0:   return "✔ native or better"
        if fit_ratio >= 0.75:  return "≈ slight upscale"
        if fit_ratio >= 0.5:   return "⚠ upscaled ~2×"
        return "⚠⚠ heavily upscaled"
    elif style == "Center":
        if img_w <= sw and img_h <= sh:
            return f"covers ~{int(100 * img_w / sw)}% width at 1:1"
        return "larger than screen, cropped"
    return ""
