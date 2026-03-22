#!/usr/bin/env python
"""Wallpaper slideshow helper - run by Windows Task Scheduler."""
import json, os, random, ctypes, winreg, datetime
from pathlib import Path

STATE_FILE = Path("C:/Users/my4nt/.qigor-wallpaper/slideshow_state.json")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif"}
LOG_FILE   = STATE_FILE.parent / "_slideshow_log.txt"

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(ts + "  " + str(msg) + "\n")

def load_state():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def save_state(s):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")

def get_images(folder):
    try:
        return sorted(f.name for f in Path(folder).iterdir()
                      if f.is_file() and f.suffix.lower() in IMAGE_EXTS)
    except Exception:
        return []

def set_wallpaper(path, style):
    styles = {
        "Fill":    ("10", "0"),
        "Fit":     ("6",  "0"),
        "Stretch": ("2",  "0"),
        "Tile":    ("0",  "1"),
        "Center":  ("0",  "0"),
        "Span":    ("22", "0"),
    }
    sv, tv = styles.get(style, ("10", "0"))
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            "Control Panel\\Desktop", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, sv)
        winreg.SetValueEx(key, "TileWallpaper",  0, winreg.REG_SZ, tv)
        winreg.CloseKey(key)
    except Exception as e:
        log("Registry error: " + str(e))
    ctypes.windll.user32.SystemParametersInfoW(20, 0, str(path), 3)

def main():
    log("Slideshow helper started.")
    state = load_state()
    if not state:
        log("ERROR: no state file. Configure slideshow in QiGor app.")
        return
    folder  = Path(state.get("folder", ""))
    style   = state.get("style", "Fill")
    shuffle = state.get("shuffle", True)
    if not folder.exists():
        log("ERROR: folder not found: " + str(folder))
        return
    images = get_images(folder)
    if not images:
        log("ERROR: no images in " + str(folder))
        return
    queue = state.get("queue", [])
    index = state.get("queue_index", 0)
    needs_rebuild = (
        not queue
        or index >= len(queue)
        or set(images) != set(queue)
    )
    if needs_rebuild:
        log("Rebuilding queue (" + str(len(images)) + " images)")
        queue = list(images)
        if shuffle:
            random.shuffle(queue)
        index = 0
    chosen = None
    for _ in range(len(queue)):
        candidate = queue[index % len(queue)]
        full_path = folder / candidate
        index = (index + 1) % len(queue)
        if full_path.exists():
            chosen = full_path
            break
        log("Skipping missing: " + candidate)
    if not chosen:
        log("ERROR: all files in queue are missing.")
        return
    log("Setting: " + chosen.name + " (style=" + style + ")")
    set_wallpaper(chosen, style)
    state["queue"]       = queue
    state["queue_index"] = index
    state["last_set"]    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["last_file"]   = chosen.name
    save_state(state)
    log("Done. Next index: " + str(index) + "/" + str(len(queue)))

if __name__ == "__main__":
    main()
