"""
scaling.py  —  QiGor Wallpaper Manager

One registry of every font the UI uses, so A+ / A− rescales the whole window —
every panel, label, button, entry, menu and dialog — instead of only the
console. Ported from the approach in qigor_wallpaper_sync, which took it from
lucid24_deploy.pyw.

How it works: Tk re-renders any widget whose ``-font`` is a *named font* the
instant that font's size changes, so a zoom needs no widget walk and no
bookkeeping at the call sites. Every font is therefore created through
``font()``, which records it here next to the size it should have at 100%;
``apply()`` then rewrites the whole registry in one pass.

Three things this depends on, all easy to get wrong later:

* Sizes handed to ``font()`` are **100% sizes**, never current ones. The zoom
  ratio is applied here and only here. Passing a scaled size compounds it.
* The registry keeps **strong references on purpose**. Tkinter does not — a
  widget stores only the font's Tcl name — so a Font that gets garbage
  collected takes its widget's font down with it.
* ``adopt_named_fonts()`` must run **before any widget is built**. It is what
  makes menus, ttk widgets and every widget with no explicit font scale for
  free, and Tk reads those at construction time.
"""
import tkinter as tk
import tkinter.font as tkfont

BASE_SIZE = 10      # the 100% size; every size below is relative to this one
MIN_SIZE  = 7
MAX_SIZE  = 20
FLOOR_PX  = 6       # never render smaller than this, whatever the ratio

# Tk's built-in named fonts. Menu bars, ttk widgets, and any widget that never
# specifies a font all resolve through these.
_NAMED = ("TkDefaultFont", "TkTextFont", "TkFixedFont", "TkHeadingFont",
          "TkMenuFont", "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont",
          "TkTooltipFont")

_registry = []                    # [(Font, size_at_100_percent), ...]
_cache    = {}                    # (family, size, weight, slant) -> Font
_state    = {"size": BASE_SIZE}


def current_size() -> int:
    """The size the UI is displaying at right now."""
    return _state["size"]


def ratio() -> float:
    return _state["size"] / BASE_SIZE


def scaled(size: int) -> int:
    """A 100% size expressed at the current zoom — for the handful of places
    that need a number rather than a font, such as a wraplength in pixels."""
    return max(FLOOR_PX, round(size * ratio()))


def font(family: str, size: int = BASE_SIZE, weight: str = "normal",
         slant: str = "roman") -> tkfont.Font:
    """
    Create a font and register it for zooming. `size` is its size at 100%.

    Pass the returned object as ``font=`` — not a tuple. A tuple is a one-off
    snapshot that Tk never revisits, which is exactly how the old A+/A− ended
    up moving only the console.

    Identical requests share one Font. Dialogs rebuild their widgets on every
    open, and without sharing the registry would grow by a handful of fonts
    each time the About box was opened.
    """
    key = (family, size, weight, slant)
    f = _cache.get(key)
    if f is not None:
        try:
            f.cget("size")        # still attached to a live interpreter?
        except tk.TclError:
            f = None              # a previous root was destroyed; rebuild
    if f is None:
        f = tkfont.Font(family=family, size=scaled(size),
                        weight=weight, slant=slant)
        _cache[key] = f
        _registry.append((f, size))
    return f


def adopt_named_fonts():
    """Pin Tk's named fonts to the baseline and register them. Call once, on
    the root window, before building anything."""
    for name in _NAMED:
        try:
            f = tkfont.nametofont(name)
            f.configure(size=BASE_SIZE)
            _registry.append((f, BASE_SIZE))
        except tk.TclError:
            pass


def apply(size: int) -> int:
    """Rescale everything registered. Returns the size actually applied, which
    is `size` clamped to [MIN_SIZE, MAX_SIZE]."""
    _state["size"] = max(MIN_SIZE, min(MAX_SIZE, int(size)))
    r = ratio()
    dead = []
    for i, (f, base) in enumerate(_registry):
        try:
            f.configure(size=max(FLOOR_PX, round(base * r)))
        except tk.TclError:
            dead.append(i)        # font outlived its interpreter
    for i in reversed(dead):
        f, _ = _registry.pop(i)
        for key, cached in list(_cache.items()):
            if cached is f:
                del _cache[key]
    return _state["size"]
