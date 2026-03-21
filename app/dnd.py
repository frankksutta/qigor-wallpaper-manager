"""
dnd.py  —  QiGor Wallpaper Manager
Drag-and-drop setup and drop data resolution.
Handles three drop types browsers and Explorer produce:
  DND_FILES — file path(s) from Windows Explorer
  DND_TEXT  — plain text URL dragged from browser address/image
  *         — catch-all for uri-list (browser image drag)
"""
from __future__ import annotations
import re
import urllib.request
import urllib.parse
from pathlib import Path

from .wallpaper import IMAGE_EXTS


def setup_dnd(widget, on_drop, on_enter, on_leave, msg_list: list):
    """
    Register tkinterdnd2 drop handlers on widget.
    msg_list is populated with (msg, tag) tuples for deferred logging.
    Returns True if DnD is available.
    """
    try:
        from tkinterdnd2 import DND_ALL
        widget.drop_target_register(DND_ALL)
        widget.dnd_bind("<<Drop>>",      on_drop)
        widget.dnd_bind("<<DropEnter>>", on_enter)
        widget.dnd_bind("<<DropLeave>>", on_leave)
        msg_list.append(("Drag-and-drop ready (tkinterdnd2).", "dim"))
        return True
    except Exception as e:
        msg_list.append(("⚠  Drag-and-drop unavailable.", "yellow"))
        msg_list.append((f"   Reason: {e}", "dim"))
        msg_list.append(("   Fix: run the app via  TkinterDnD.Tk()  (already handled in entry point).", "dim"))
        msg_list.append(("   Or reinstall:  pip install tkinterdnd2", "dim"))
        return False


def setup_dnd_on(widget, handler, dnd_available: bool):
    """Register DnD on a specific widget (e.g. Add Folder / Add URL buttons)."""
    if not dnd_available:
        return
    try:
        from tkinterdnd2 import DND_ALL
        import tkinter as tk
        widget.drop_target_register(DND_ALL)
        widget.dnd_bind("<<Drop>>", handler)
        widget.dnd_bind("<<DropEnter>>",
            lambda e, w=widget: w.config(relief=tk.SUNKEN))
        widget.dnd_bind("<<DropLeave>>",
            lambda e, w=widget: w.config(relief=tk.RAISED))
    except Exception:
        pass


def resolve_drop_data(raw: str) -> tuple[str | None, str | None]:
    """
    Returns (resolved_str, warning_str).
    resolved_str — usable URL or absolute path, or None
    warning_str  — human-readable problem, or None
    """
    items = []
    if raw.startswith("{"):
        items = re.findall(r'\{([^}]+)\}', raw)
        if not items:
            items = [raw.strip("{}")]
    else:
        items = [x.strip() for x in raw.splitlines()
                 if x.strip() and not x.startswith("#")]

    if not items:
        return None, "Empty drop payload."

    candidate = items[0]

    # file:// URI → local path
    if candidate.lower().startswith("file:///"):
        candidate = urllib.request.url2pathname(candidate[7:])
    elif candidate.lower().startswith("file://"):
        candidate = candidate[7:]

    # Local path that exists → always good
    if Path(candidate).exists():
        return candidate, None

    # Web URL
    if candidate.lower().startswith(("http://", "https://")):
        path_part = urllib.parse.urlparse(candidate).path.lower()
        ext = Path(path_part).suffix
        if ext in IMAGE_EXTS:
            return candidate, None
        if "." not in Path(path_part).name:
            return None, (
                f"The dropped URL looks like a page, not an image:\n"
                f"  {candidate[:100]}\n"
                "Right-click the image on the page → 'Copy image address'\n"
                "and paste that URL into the box below.")
        return candidate, None

    if __import__("os").path.isabs(candidate):
        return candidate, None

    return None, f"Unrecognised drop format: {candidate[:80]}"
