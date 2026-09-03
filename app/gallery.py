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

What a gallery offers is described as a list of items rather than bare URLs,
because choosing between them needs more than an address: the filename to
save under, the size where the gallery admits one, its own thumbnail where it
keeps one, and whether the store already holds that picture.
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from .wallpaper import IMAGE_EXTS, store_images, store_label

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


def safe_folder(name: str) -> str:
    """
    A typed-in folder name Windows will accept; "" if nothing is left of it.

    Empty is a real answer — it means the store itself — so this cannot fall
    back to a name of its own the way suggest_folder does.
    """
    return _safe(name, "") if name.strip() else ""


def file_name_for(url: str) -> str:
    """The filename to save a downloaded image under."""
    path = urllib.parse.urlparse(url).path
    return _safe(urllib.parse.unquote(Path(path).name), "image.jpg")


def size_label(n: int) -> str:
    """A byte count to read, or "" for the galleries that do not give one."""
    if not n:
        return ""
    if n >= 1_000_000:
        return "{:.1f} MB".format(n / 1_048_576)
    return "{:.0f} KB".format(max(n / 1024, 1))


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


def _item(url: str, thumb: "str | None" = None, size: int = 0) -> dict:
    """One picture a gallery offers. `have` is filled in by mark_present()."""
    return {"url": url, "name": file_name_for(url),
            "thumb": thumb, "size": size, "have": None}


def _archive_thumbs(files: list) -> dict:
    """
    The item's own small copy of each picture, keyed by the picture's name.

    The _thumb.jpg derivatives the picture filter throws away are worth
    keeping hold of here: previewing a highlighted row from a 15 KB thumbnail
    rather than the 2 MB wallpaper is what makes walking a long list bearable.
    A derivative names what it came from in `original` — which is a list for
    some of them, and those are not one picture's thumbnail.
    """
    thumbs = {}
    for f in files:
        if (f.get("source") or "").lower() != "derivative":
            continue
        if "thumb" not in (f.get("format") or "").lower():
            continue
        orig, name = f.get("original"), f.get("name")
        if isinstance(orig, str) and name:
            thumbs.setdefault(orig, name)
    return thumbs


def _archive_size(f: dict) -> int:
    """The file's size in bytes; 0 when the metadata does not say."""
    try:
        return int(f.get("size") or 0)
    except (TypeError, ValueError):
        return 0


def _from_archive(item: str, log) -> list:
    raw = _fetch("https://archive.org/metadata/" + urllib.parse.quote(item))
    data = json.loads(raw.decode("utf-8", "replace"))
    files = data.get("files", [])
    if not files:
        log("archive.org knows no files for “{}”.".format(item), "yellow")
        return []
    base = "https://archive.org/download/" + urllib.parse.quote(item)
    small = _archive_thumbs(files)
    out, thumbs = [], 0
    for f in files:
        if not _is_item_picture(f):
            if Path(f.get("name", "")).suffix.lower() in IMAGE_EXTS:
                thumbs += 1
            continue
        name = f.get("name", "")
        thumb = small.get(name)
        out.append(_item(
            "{}/{}".format(base, urllib.parse.quote(name)),
            thumb="{}/{}".format(base, urllib.parse.quote(thumb))
            if thumb else None,
            size=_archive_size(f)))
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
            found.append(_item(full))
    log("Read {} — {} image link{} on the page.".format(
        url, len(found), "" if len(found) == 1 else "s"), "dim")
    return found


def find_items(url: str, log=lambda *_a: None) -> list:
    """Every image the gallery at `url` offers, in page order, deduplicated."""
    item = archive_item(url)
    found = _from_archive(item, log) if item else _from_html(url, log)
    seen, out = set(), []
    for it in found:
        if it["url"] not in seen:
            seen.add(it["url"])
            out.append(it)
    return out


def find_images(url: str, log=lambda *_a: None) -> list:
    """Just the addresses, for a caller that has no choosing to do."""
    return [it["url"] for it in find_items(url, log)]


def mark_present(items: list) -> int:
    """
    Fill in each item's `have` — where the store already holds it. Returns how
    many that was.

    Filename, case-insensitively, and nothing cleverer: the store is largely
    what this same importer put there, under the name the gallery gave it.
    Comparing the bytes would mean downloading every image to find out it was
    already here, which is the download the whole exercise is avoiding.
    """
    index = {}
    for path in store_images():          # newest first, so the newest wins
        index.setdefault(path.name.lower(), path)
    present = 0
    for it in items:
        hit = index.get(it["name"].lower())
        it["have"] = store_label(hit) if hit is not None else None
        present += hit is not None
    return present


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
