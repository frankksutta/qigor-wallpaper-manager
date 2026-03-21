"""
config.py  —  QiGor Wallpaper Manager
JSON-backed settings persisted to ~/.qigor-wallpaper/config.json.
"""
import json
from pathlib import Path
from .constants import APP_SLUG

RECENT_MAX = 8


class Config:
    """JSON-backed settings. set() saves immediately."""

    DEFAULTS = {
        "theme":            "dark",
        "font_size":        10,
        "last_source_dir":  str(Path.home()),
        "last_output_dir":  "",
        "recent_sources":   [],
        "recent_outputs":   [],
        "window_geometry":  "1060x800",
        "autoscroll":       True,
        "wallpaper_style":  "Fill",
        "copy_to_store":    True,
        "history":          [],    # [{path, set_at, style, thumb_b64}]
        "favorites":        [],    # [{label, location}]
        "last_changed":     "",
        "reminder_set":     False,
        "reminder_freq":    "weekly",
        "reminder_dow":     "MON",
        "reminder_ndays":   "7",
        "reminder_hour":    "09",
        "reminder_min":     "00",
        "seeded_favorites": False,
    }

    def __init__(self):
        self._dir  = Path.home() / f".{APP_SLUG}"
        self._file = self._dir / "config.json"
        self.data  = self._load()

    def _load(self):
        try:
            if self._file.exists():
                return {**self.DEFAULTS, **json.loads(self._file.read_text("utf-8"))}
        except Exception:
            pass
        return self.DEFAULTS.copy()

    def save(self):
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def get(self, k):       return self.data.get(k, self.DEFAULTS.get(k))
    def set(self, k, v):    self.data[k] = v; self.save()

    def push_recent(self, key: str, value: str):
        lst = [x for x in self.get(key) if x != value]
        lst.insert(0, value)
        self.set(key, lst[:RECENT_MAX])
