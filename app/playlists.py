"""
playlists.py  —  QiGor Wallpaper Manager
Named sets of images, built from the image store, that the slideshow can
rotate through instead of a whole folder.

Storage: ~/.qigor-wallpaper/playlists.json

    {"playlists": [{"name": "Mountains", "items": ["C:\\...\\a.jpg", ...]}]}

Items are absolute paths, not bare filenames: a playlist is a chosen set of
images, and the point of choosing is that it survives whatever else lands in
the store folder afterwards. A missing file is kept in the list and marked,
rather than dropped — a disconnected drive should not silently empty a
playlist.

The data half of this module deliberately knows nothing about Tk, so the
headless `--next` runner can resolve a playlist without building a UI.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

from .constants import THEMES, BTN_COLORS, CONSOLE_COLORS, mark_role
from . import scaling
from . import wallpaper as wp
from .tooltip import Tooltip

# Pillow and the preview code are pulled in by the panel when it first needs
# them: the headless `--next` runner imports this module for existing_items()
# alone, and reading a JSON file should not cost an image library.

PLAYLIST_FILE = Path.home() / ".qigor-wallpaper" / "playlists.json"


# ── Storage ───────────────────────────────────────────────────────────────────

def load() -> list:
    """Every playlist, in the order they were created. Never raises."""
    try:
        if PLAYLIST_FILE.exists():
            data = json.loads(PLAYLIST_FILE.read_text(encoding="utf-8"))
            lists = data.get("playlists", [])
            return [{"name": str(p.get("name", "")),
                     "items": [str(i) for i in p.get("items", [])]}
                    for p in lists if p.get("name")]
    except Exception:
        pass
    return []


def save(lists: list):
    PLAYLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLAYLIST_FILE.write_text(
        json.dumps({"playlists": lists}, indent=2), encoding="utf-8")


def names() -> list:
    return [p["name"] for p in load()]


def find(name: str) -> "dict | None":
    for p in load():
        if p["name"] == name:
            return p
    return None


def items(name: str) -> list:
    p = find(name)
    return list(p["items"]) if p else []


def existing_items(name: str) -> list:
    """Only the items still on disk — what the slideshow can actually show."""
    return [i for i in items(name) if Path(i).is_file()]


def set_items(name: str, new_items: list) -> bool:
    lists = load()
    for p in lists:
        if p["name"] == name:
            p["items"] = [str(i) for i in new_items]
            save(lists)
            return True
    return False


def create(name: str) -> bool:
    name = name.strip()
    lists = load()
    if not name or any(p["name"].lower() == name.lower() for p in lists):
        return False
    lists.append({"name": name, "items": []})
    save(lists)
    return True


def duplicate(name: str, new_name: str) -> bool:
    new_name = new_name.strip()
    lists = load()
    src = next((p for p in lists if p["name"] == name), None)
    if src is None or not new_name:
        return False
    if any(p["name"].lower() == new_name.lower() for p in lists):
        return False
    lists.append({"name": new_name, "items": list(src["items"])})
    save(lists)
    return True


def rename(old: str, new: str) -> bool:
    new = new.strip()
    lists = load()
    if not new or not any(p["name"] == old for p in lists):
        return False
    if any(p["name"].lower() == new.lower() and p["name"] != old for p in lists):
        return False
    for p in lists:
        if p["name"] == old:
            p["name"] = new
    save(lists)
    return True


def delete(name: str) -> bool:
    lists = load()
    kept = [p for p in lists if p["name"] != name]
    if len(kept) == len(lists):
        return False
    save(kept)
    return True


# ── Panel ─────────────────────────────────────────────────────────────────────

class PlaylistPanel(tk.Frame):
    """
    Build playlists out of the image store.

    Left is everything saved locally, right is the playlist being edited, and
    the buttons between them move images across. Every edit is written to disk
    as it is made — there is no Save button to forget, and the slideshow reads
    the file fresh on every rotation, so a playlist it is already using picks
    up the change on its next fire.
    """

    def __init__(self, parent, cfg, theme_name, on_use=None, on_change=None,
                 log=None):
        super().__init__(parent)
        self._cfg        = cfg
        self._theme_name = theme_name
        # on_use hands a playlist to the Slideshow tab; on_change tells it the
        # set of playlists moved under it. Both are the app's business, not
        # this panel's — it has no reference to the slideshow at all.
        self._on_use     = on_use
        self._on_change  = on_change
        self._log        = log or (lambda *_a, **_k: None)

        self._current    = None      # name of the playlist being edited
        self._items      = []        # its paths, in order
        self._store      = []        # Paths in the image store
        self._thumb_img  = None
        self._thumb_src  = None

        t = THEMES.get(theme_name, THEMES["dark"])
        self.configure(bg=t["bg"])
        fn  = scaling.font("Segoe UI", 10)
        fnb = scaling.font("Segoe UI", 10, "bold")
        fns = scaling.font("Segoe UI", 9)
        dim = CONSOLE_COLORS[theme_name]["dim"]

        # ── Heading ──────────────────────────────────────────────────────────
        head = tk.Frame(self, bg=t["bg"])
        head.pack(fill=tk.X, padx=12, pady=(10, 0))
        tk.Label(head, text="Playlists", font=fnb,
                 bg=t["bg"], fg=t["fg"]).pack(anchor=tk.W)
        mark_role(tk.Label(
            head, font=fns, bg=t["bg"], fg=dim, wraplength=680,
            justify=tk.LEFT,
            text="A playlist is a chosen set of images from your store. The "
                 "slideshow can rotate through one instead of a whole folder. "
                 "Changes are saved as you make them."),
            "dim").pack(anchor=tk.W, pady=(2, 8))

        # ── Playlist chooser ─────────────────────────────────────────────────
        row = tk.Frame(self, bg=t["bg"])
        row.pack(fill=tk.X, padx=12, pady=(0, 6))
        tk.Label(row, text="Playlist:", font=fnb, bg=t["bg"],
                 fg=t["fg"]).pack(side=tk.LEFT, padx=(0, 6))

        self._name_var = tk.StringVar(value="")
        self._name_combo = ttk.Combobox(row, textvariable=self._name_var,
                                        values=[], width=26,
                                        state="readonly", font=fn)
        self._name_combo.pack(side=tk.LEFT)
        self._name_combo.bind("<<ComboboxSelected>>", self._on_pick_playlist)
        Tooltip(self._name_combo, "The playlist these buttons edit.")

        for text, colour, cmd, tip in (
                ("＋ New",    "success", self._new,
                 "Create an empty playlist."),
                ("✏ Rename",  "primary", self._rename,
                 "Rename the selected playlist.\n"
                 "The slideshow follows the new name if it is using it."),
                ("⧉ Copy",    "primary", self._duplicate,
                 "Copy the selected playlist under a new name."),
                ("🗑 Delete", "danger",  self._delete,
                 "Delete the selected playlist.\n"
                 "The images themselves are left alone.")):
            c = BTN_COLORS[colour]
            b = tk.Button(row, text=text, font=fns,
                          bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                          command=cmd)
            b.pack(side=tk.LEFT, padx=(6, 0))
            Tooltip(b, tip)

        c = BTN_COLORS["success"]
        self._use_btn = tk.Button(row, text="▶ Use for slideshow", font=fns,
                                  bg=c["bg"], fg=c["fg"],
                                  activebackground=c["active"],
                                  command=self._use)
        self._use_btn.pack(side=tk.RIGHT)
        Tooltip(self._use_btn,
                "Point the slideshow at this playlist and open that tab.\n"
                "The slideshow only starts when you press ▶ Start there.")

        # ── The two lists ────────────────────────────────────────────────────
        pane = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED,
                              sashwidth=6, bg="#555555")
        pane.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))

        store_frame = tk.LabelFrame(pane, text="  Image store  ")
        pane.add(store_frame, stretch="always", minsize=220)
        list_frame = tk.Frame(store_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 2))
        bar = tk.Scrollbar(list_frame)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        self._store_list = tk.Listbox(list_frame, height=6,
                                      font=scaling.font("Consolas", 9),
                                      yscrollcommand=bar.set,
                                      selectmode=tk.EXTENDED,
                                      exportselection=False)
        self._store_list.pack(fill=tk.BOTH, expand=True)
        bar.config(command=self._store_list.yview)
        self._store_list.bind("<<ListboxSelect>>",
                              lambda _e: self._preview_from(self._store_list,
                                                            self._store_paths()))
        self._store_list.bind("<Double-Button-1>", lambda _e: self._add())
        Tooltip(self._store_list,
                "Every image saved in your store, newest first —\n"
                "subfolders included, shown as folder/name.\n"
                "• Click to see it below\n"
                "• Double-click, or press Add →, to put it in the playlist\n"
                "• Ctrl-click or Shift-click to take several at once")

        srow = tk.Frame(store_frame)
        srow.pack(fill=tk.X, padx=4, pady=(0, 4))
        for text, colour, cmd, tip in (
                ("Add →",     "primary", self._add,
                 "Add the selected images to the playlist."),
                ("Add all →", "primary", self._add_all,
                 "Add every image in the store that is not already in the "
                 "playlist."),
                ("⟳",         "primary", self.refresh_store,
                 "Re-read the store folder.")):
            c = BTN_COLORS[colour]
            b = tk.Button(srow, text=text, font=fns,
                          bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                          command=cmd)
            b.pack(side=tk.LEFT, padx=(0, 4))
            Tooltip(b, tip)

        pl_frame = tk.LabelFrame(pane, text="  In this playlist  ")
        pane.add(pl_frame, stretch="always", minsize=220)
        list_frame = tk.Frame(pl_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 2))
        bar = tk.Scrollbar(list_frame)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        self._pl_list = tk.Listbox(list_frame, height=6,
                                   font=scaling.font("Consolas", 9),
                                   yscrollcommand=bar.set,
                                   selectmode=tk.EXTENDED,
                                   exportselection=False)
        self._pl_list.pack(fill=tk.BOTH, expand=True)
        bar.config(command=self._pl_list.yview)
        self._pl_list.bind("<<ListboxSelect>>",
                           lambda _e: self._preview_from(self._pl_list,
                                                         self._items))
        self._pl_list.bind("<Double-Button-1>", lambda _e: self._remove())
        Tooltip(self._pl_list,
                "The playlist, in rotation order.\n"
                "Shuffle in the Slideshow tab overrides this order.\n"
                "• Double-click to take an image out\n"
                "• ⚠ marks a file that is no longer on disk")

        prow = tk.Frame(pl_frame)
        prow.pack(fill=tk.X, padx=4, pady=(0, 4))
        for text, colour, cmd, tip in (
                ("↑",        "primary", lambda: self._move(-1),
                 "Move the selection one place earlier."),
                ("↓",        "primary", lambda: self._move(1),
                 "Move the selection one place later."),
                ("← Remove", "danger",  self._remove,
                 "Take the selected images out of the playlist.\n"
                 "The files stay in your store."),
                ("Clear",    "danger",  self._clear,
                 "Empty the playlist.")):
            c = BTN_COLORS[colour]
            b = tk.Button(prow, text=text, font=fns,
                          bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                          command=cmd)
            b.pack(side=tk.LEFT, padx=(0, 4))
            Tooltip(b, tip)

        # ── Thumbnail of whatever is highlighted ─────────────────────────────
        # Curating a playlist by filename alone means opening another tab to
        # find out what a name refers to.
        thumb_wrap = tk.Frame(self, bg=t["bg"], height=150)
        thumb_wrap.pack(fill=tk.X, padx=12, pady=(0, 4))
        thumb_wrap.pack_propagate(False)
        self._thumb_label = tk.Label(
            thumb_wrap, text="(click an image to see it here)",
            font=fns, relief=tk.SUNKEN)
        self._thumb_label.pack(fill=tk.BOTH, expand=True)

        self._status_var = tk.StringVar(value="")
        mark_role(tk.Label(self, textvariable=self._status_var, font=fns,
                           anchor=tk.W, bg=t["bg"], fg=dim),
                  "dim").pack(fill=tk.X, padx=14, pady=(0, 8))

        self.refresh_playlists()
        self.refresh_store()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def retheme(self, theme_name):
        self._theme_name = theme_name

    def _store_paths(self) -> list:
        return [str(p) for p in self._store]

    def _notify_change(self):
        if self._on_change is not None:
            self._on_change()

    def _selected(self, listbox) -> list:
        return [i for i in listbox.curselection()]

    def _ask_name(self, title, prompt, prefill=""):
        from .dialogs import NameDialog
        dlg = NameDialog(self, title, prompt, self._theme_name,
                         prefill=prefill, label="Playlist name:")
        self.wait_window(dlg)
        return dlg.result

    # ── Playlist list ────────────────────────────────────────────────────────

    def refresh_playlists(self, select=None):
        """Re-read playlists.json and show `select` (or keep what was shown)."""
        all_names = names()
        self._name_combo.config(values=all_names)
        want = select or self._current
        if want not in all_names:
            want = all_names[0] if all_names else None
        self._current = want
        self._name_var.set(want or "")
        self._load_items()

    def _load_items(self):
        self._items = items(self._current) if self._current else []
        self._render_items()

    def _render_items(self):
        self._pl_list.delete(0, tk.END)
        for path in self._items:
            p = Path(path)
            self._pl_list.insert(
                tk.END, ("   " if p.is_file() else "⚠  ") + wp.store_label(p))
        if self._current is None:
            self._pl_list.insert(tk.END, "(no playlists yet — click ＋ New)")
            self._status_var.set(
                "No playlists yet. ＋ New makes one, then add images from the "
                "store on the left.")
            return
        if not self._items:
            self._pl_list.insert(tk.END, "(empty — add images from the left)")
        missing = sum(1 for i in self._items if not Path(i).is_file())
        self._status_var.set(
            "“{}”  •  {} image{}{}".format(
                self._current, len(self._items),
                "" if len(self._items) == 1 else "s",
                "  •  ⚠ {} missing from disk".format(missing) if missing else ""))

    def _save_items(self):
        if self._current is None:
            return
        set_items(self._current, self._items)
        self._render_items()
        self._notify_change()

    def _on_pick_playlist(self, _event=None):
        self._current = self._name_var.get() or None
        self._load_items()

    def _new(self):
        name = self._ask_name("New Playlist", "Name for the new playlist:")
        if not name:
            return
        if not create(name):
            messagebox.showerror("Playlist exists",
                                 "A playlist called “{}” already exists.".format(name),
                                 parent=self)
            return
        self._log("Playlist created: {}".format(name), "green")
        self.refresh_playlists(select=name)
        self._notify_change()

    def _rename(self):
        if not self._require_playlist():
            return
        old = self._current
        name = self._ask_name("Rename Playlist", "New name for “{}”:".format(old),
                              prefill=old)
        if not name or name == old:
            return
        if not rename(old, name):
            messagebox.showerror("Cannot rename",
                                 "A playlist called “{}” already exists.".format(name),
                                 parent=self)
            return
        self._log("Playlist renamed: {} → {}".format(old, name), "cyan")
        self.refresh_playlists(select=name)
        # The slideshow may have been pointed at the old name.
        self._notify_change()

    def _duplicate(self):
        if not self._require_playlist():
            return
        name = self._ask_name("Copy Playlist",
                              "Name for the copy of “{}”:".format(self._current),
                              prefill="{} copy".format(self._current))
        if not name:
            return
        if not duplicate(self._current, name):
            messagebox.showerror("Cannot copy",
                                 "A playlist called “{}” already exists.".format(name),
                                 parent=self)
            return
        self._log("Playlist copied: {} → {}".format(self._current, name), "cyan")
        self.refresh_playlists(select=name)
        self._notify_change()

    def _delete(self):
        if not self._require_playlist():
            return
        name = self._current
        if not messagebox.askyesno(
                "Delete Playlist",
                "Delete the playlist “{}”?\n\n"
                "The {} image{} in it stay in your store — only the list "
                "goes.".format(name, len(self._items),
                               "" if len(self._items) == 1 else "s"),
                parent=self):
            return
        delete(name)
        self._log("Playlist deleted: {}".format(name), "yellow")
        self._current = None
        self.refresh_playlists()
        self._notify_change()

    def _use(self):
        if not self._require_playlist():
            return
        if not self._items:
            messagebox.showinfo(
                "Playlist is empty",
                "Add some images to “{}” before the slideshow can use "
                "it.".format(self._current), parent=self)
            return
        if self._on_use is not None:
            self._on_use(self._current)

    def _require_playlist(self) -> bool:
        if self._current is None:
            messagebox.showinfo("No playlist",
                                "Create a playlist first — click ＋ New.",
                                parent=self)
            return False
        return True

    # ── Image store ──────────────────────────────────────────────────────────

    def refresh_store(self):
        self._store = []
        try:
            self._store = wp.store_images()
        except OSError as exc:
            self._log("Could not read the image store: {}".format(exc), "red")
        self._store_list.delete(0, tk.END)
        for path in self._store:
            self._store_list.insert(tk.END, wp.store_label(path))
        if not self._store:
            self._store_list.insert(tk.END, "(no images saved yet)")

    # ── Editing ──────────────────────────────────────────────────────────────

    def _add(self):
        if not self._require_playlist():
            return
        chosen = [str(self._store[i]) for i in self._selected(self._store_list)
                  if i < len(self._store)]
        if not chosen:
            return
        have = {i.lower() for i in self._items}
        added = [c for c in chosen if c.lower() not in have]
        self._items.extend(added)
        self._save_items()
        if added:
            self._log("Playlist “{}”: added {} image{}.".format(
                self._current, len(added), "" if len(added) == 1 else "s"),
                "green")

    def _add_all(self):
        if not self._require_playlist():
            return
        have = {i.lower() for i in self._items}
        added = [str(p) for p in self._store if str(p).lower() not in have]
        if not added:
            return
        self._items.extend(added)
        self._save_items()
        self._log("Playlist “{}”: added {} image{}.".format(
            self._current, len(added), "" if len(added) == 1 else "s"), "green")

    def _remove(self):
        if not self._require_playlist() or not self._items:
            return
        idxs = [i for i in self._selected(self._pl_list) if i < len(self._items)]
        if not idxs:
            return
        for i in sorted(idxs, reverse=True):
            del self._items[i]
        self._save_items()

    def _clear(self):
        if not self._require_playlist() or not self._items:
            return
        if not messagebox.askyesno(
                "Clear Playlist",
                "Remove all {} image{} from “{}”?".format(
                    len(self._items), "" if len(self._items) == 1 else "s",
                    self._current), parent=self):
            return
        self._items = []
        self._save_items()

    def _move(self, delta):
        """Shift the selection one place, keeping it selected."""
        if not self._require_playlist() or not self._items:
            return
        idxs = sorted(i for i in self._selected(self._pl_list)
                      if i < len(self._items))
        if not idxs:
            return
        # Walk from the edge the block is moving towards, so a multi-row
        # selection keeps its shape instead of collapsing onto itself.
        order = idxs if delta < 0 else list(reversed(idxs))
        moved = []
        for i in order:
            j = i + delta
            if j < 0 or j >= len(self._items) or j in moved:
                moved.append(i)
                continue
            self._items[i], self._items[j] = self._items[j], self._items[i]
            moved.append(j)
        self._save_items()
        self._pl_list.selection_clear(0, tk.END)
        for i in moved:
            self._pl_list.selection_set(i)
        self._pl_list.see(moved[0])

    # ── Thumbnail ────────────────────────────────────────────────────────────

    def _preview_from(self, listbox, paths):
        sel = listbox.curselection()
        if not sel or sel[0] >= len(paths):
            return
        self._show_thumb(paths[sel[0]])

    def _show_thumb(self, path_str):
        try:
            from PIL import ImageTk
            from . import preview as pv
        except ImportError:
            self._thumb_label.config(
                text="Pillow not installed — no thumbnails.\npip install pillow",
                image="")
            return
        if not Path(path_str).is_file():
            self._thumb_img = None
            self._thumb_label.config(
                image="", text="⚠  Missing:\n{}".format(Path(path_str).name))
            return
        self._thumb_src = path_str
        self._thumb_label.config(text="Loading…", image="")

        def _work(src=path_str):
            try:
                img = pv.fetch_preview_image(src)
            except Exception as exc:
                img, err = None, str(exc)
            else:
                err = ""

            def _apply():
                # A later click may have won the race while this one loaded.
                if self._thumb_src != src:
                    return
                if img is None:
                    self._thumb_img = None
                    self._thumb_label.config(
                        image="", text="Preview failed:\n{}".format(err))
                    return
                h = max(self._thumb_label.winfo_height() - 8, 60)
                copy = img.copy()
                copy.thumbnail((h * 4, h))
                self._thumb_img = ImageTk.PhotoImage(copy)
                self._thumb_label.config(image=self._thumb_img, text="")
            try:
                self.after(0, _apply)
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=_work, daemon=True).start()
