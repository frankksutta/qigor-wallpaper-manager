"""
gallery.py  —  QiGor Wallpaper Manager
Pull the images off a gallery page and into the local store.

Two ways in, because one page is not like another:

  archive.org  — the item's metadata endpoint lists its files exactly, and
                 says which of them are the thumbnails it keeps beside every
                 image. Scraping the details page instead would drag in the
                 site's own logos and a _thumb.jpg for each picture.
  anything else — read the HTML and take the links that end in an image.

Nothing here touches Tk: the app calls it from a worker thread and does the
talking itself.
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from .wallpaper import IMAGE_EXTS

UA         = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TIMEOUT    = 30
PAGE_LIMIT = 8_000_000    # a gallery page; nothing bigger is one
# Under this, it is the thumbnail the gallery shows, not the wallpaper behind
# it. A 128px preview runs 5-15 KB; a wallpaper runs into the hundreds.
MIN_BYTES  = 25_000
CHUNK      = 65_536


def _fetch(url: str, limit: int = PAGE_LIMIT) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read(limit)


# ── Naming ───────────────────────────────────────────────────────────────────

def url_label(url: str) -> str:
    """
    A first guess at what to call a URL.

    The host alone made every archive.org gallery read "archive.org"; the last
    part of the path is what actually names one.
    """
    parts = urllib.parse.urlparse(url)
    tail = [p for p in parts.path.split("/") if p]
    if tail:
        name = urllib.parse.unquote(tail[-1])
        # index.html names nothing; the folder above it does.
        if name.lower().startswith("index.") and len(tail) > 1:
            name = urllib.parse.unquote(tail[-2])
        if name:
            return name[:60]
    return parts.netloc or url[:40]


def _safe(name: str, fallback: str) -> str:
    """A name Windows will accept, or `fallback` if nothing is left of it."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or fallback


def suggest_folder(url: str) -> str:
    """The subfolder to offer for this gallery, from the URL's own basename."""
    return _safe(url_label(url), "gallery")


def file_name_for(url: str) -> str:
    """The filename to save a downloaded image under."""
    path = urllib.parse.urlparse(url).path
    return _safe(urllib.parse.unquote(Path(path).name), "image.jpg")


# ── Finding ──────────────────────────────────────────────────────────────────

def archive_item(url: str) -> "str | None":
    """The archive.org item id in `url`, if it names one."""
    parts = urllib.parse.urlparse(url)
    host = parts.netloc.lower().split(":")[0]
    if host != "archive.org" and not host.endswith(".archive.org"):
        return None
    bits = [b for b in parts.path.split("/") if b]
    if len(bits) >= 2 and bits[0] in ("details", "download", "metadata", "embed"):
        return urllib.parse.unquote(bits[1])
    return None


def _is_item_picture(f: dict) -> bool:
    """
    One of the item's own pictures, rather than something archive.org made.

    It keeps a _thumb.jpg beside every image — a "derivative", format "JPEG
    Thumb" — and one __ia_thumb.jpg tile for the item itself, which is filed
    as an *original* with format "Item Tile", so source alone is not enough.
    """
    name = f.get("name", "")
    if Path(name).suffix.lower() not in IMAGE_EXTS:
        return False
    if name.startswith("__ia"):
        return False
    if (f.get("source") or "").lower() == "derivative":
        return False
    fmt = (f.get("format") or "").lower()
    return "thumb" not in fmt and "tile" not in fmt


def _from_archive(item: str, log) -> list:
    raw = _fetch("https://archive.org/metadata/" + urllib.parse.quote(item))
    data = json.loads(raw.decode("utf-8", "replace"))
    files = data.get("files", [])
    if not files:
        log("archive.org knows no files for “{}”.".format(item), "yellow")
        return []
    out, thumbs = [], 0
    for f in files:
        if not _is_item_picture(f):
            if Path(f.get("name", "")).suffix.lower() in IMAGE_EXTS:
                thumbs += 1
            continue
        name = f.get("name", "")
        out.append("https://archive.org/download/{}/{}".format(
            urllib.parse.quote(item), urllib.parse.quote(name)))
    log("archive.org item “{}”: {} image{}{}.".format(
        item, len(out), "" if len(out) == 1 else "s",
        ", {} thumbnail{} ignored".format(thumbs, "" if thumbs == 1 else "s")
        if thumbs else ""), "dim")
    return out


def _from_html(url: str, log) -> list:
    body = _fetch(url).decode("utf-8", "replace")
    found = []
    for m in re.finditer(r'(?:src|href)\s*=\s*["\']([^"\'>]+)["\']', body, re.I):
        raw = html.unescape(m.group(1).strip())
        if not raw or raw.startswith(("data:", "javascript:", "#", "mailto:")):
            continue
        full = urllib.parse.urljoin(url, raw)
        if not full.lower().startswith(("http://", "https://")):
            continue
        ext = Path(urllib.parse.urlparse(full).path).suffix.lower()
        if ext in IMAGE_EXTS:
            found.append(full)
    log("Read {} — {} image link{} on the page.".format(
        url, len(found), "" if len(found) == 1 else "s"), "dim")
    return found


def find_images(url: str, log=lambda *_a: None) -> list:
    """Every image the gallery at `url` offers, in page order, deduplicated."""
    item = archive_item(url)
    found = _from_archive(item, log) if item else _from_html(url, log)
    seen, out = set(), []
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ── Fetching ─────────────────────────────────────────────────────────────────

def download(urls: list, dest: Path, log=lambda *_a: None,
             cancel=None, progress=None) -> tuple:
    """
    Fetch each URL into `dest`. Returns (saved, skipped, failed).

    Raises InterruptedError if `cancel` is set — the app's Cancel button and
    Esc both reach this the same way an image download does.
    """
    dest.mkdir(parents=True, exist_ok=True)
    saved = skipped = failed = 0
    used = set()
    total = len(urls)

    for i, url in enumerate(urls, 1):
        if cancel is not None and cancel.is_set():
            raise InterruptedError()
        name = file_name_for(url)
        # Two links can end in the same filename; the second is not the first.
        if name.lower() in used:
            stem, sfx = Path(name).stem, Path(name).suffix
            n = 2
            while "{}_{}{}".format(stem, n, sfx).lower() in used:
                n += 1
            name = "{}_{}{}".format(stem, n, sfx)
        used.add(name.lower())

        if progress is not None:
            progress(i, total, name)

        target = dest / name
        if target.exists():
            log("·  {} is already in the store.".format(name), "dim")
            skipped += 1
            continue

        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                declared = int(resp.headers.get("Content-Length") or 0)
                if 0 < declared < MIN_BYTES:
                    log("·  {} skipped — {} KB, a thumbnail.".format(
                        name, declared // 1024), "dim")
                    skipped += 1
                    continue
                chunks = []
                while True:
                    if cancel is not None and cancel.is_set():
                        raise InterruptedError()
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    chunks.append(chunk)
            data = b"".join(chunks)
            if len(data) < MIN_BYTES:
                log("·  {} skipped — {} KB, a thumbnail.".format(
                    name, len(data) // 1024), "dim")
                skipped += 1
                continue
            target.write_bytes(data)
            saved += 1
            log("✔  {}  ({} KB)".format(name, len(data) // 1024), "green")
        except InterruptedError:
            raise
        except Exception as exc:
            failed += 1
            log("✖  {}: {}".format(name, exc), "red")

    return saved, skipped, failed
