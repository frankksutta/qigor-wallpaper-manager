"""
app.py  —  QiGor Wallpaper Manager
Main App class. Wires all modules together.
UI construction is in ui.py. Logic modules: wallpaper, preview, dnd, reminder.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from .constants import (APP_NAME, APP_VERSION, APP_BUILD, STORE_DIR, HELPERS_DIR,
                        THEMES, BTN_COLORS, CONSOLE_COLORS, WIN_IMAGE_SOURCES,
                        role_fg)
from . import scaling
from .config import Config
from .tooltip import Tooltip
from .dialogs import AboutDialog, _InputDialog, _RenameDialog
from .slideshow import (slideshow_runner_is_stale,
                        slideshow_last_run_failed)
from .desktop_preview import start_preview


def _get_exe_dir() -> Path:
    """
    Return the directory containing the running app.
    Works correctly in both script mode and PyInstaller frozen EXE.
    - Frozen EXE: sys.executable = path to .exe  → use its parent
    - Script:     sys.argv[0]    = path to .pyw  → use its parent
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(sys.argv[0]).resolve().parent
from . import wallpaper as wp
from . import preview as pv
from . import dnd as dnd_mod

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class App:

    def __init__(self, root: tk.Tk):
        self.root       = root
        self.root.title(f"{APP_NAME}  v{APP_VERSION}  build {APP_BUILD}")
        self.cfg        = Config()
        self.root.geometry(self.cfg.get("window_geometry"))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.minsize(800, 600)

        self.theme_name    = self.cfg.get("theme")
        # Two-phase font sizing. Tk's named fonts are pinned to the 100%
        # baseline first, so every widget is built at a known size and 100%
        # always means "everything matches"; the size the user actually saved
        # is applied once, after build_ui, when every font exists to rescale.
        scaling.adopt_named_fonts()
        self.font_size     = scaling.BASE_SIZE
        self.is_running    = False
        self._cancel_event = threading.Event()
        self._valid: dict  = {}

        self._pending_path  = tk.StringVar(value="")
        self._style_var     = tk.StringVar(value=self.cfg.get("wallpaper_style"))
        self._copy_var      = tk.BooleanVar(value=self.cfg.get("copy_to_store"))
        self._preview_img   = None
        self._preview_raw   = None
        self._dnd_available = False
        # The pane builders append to this while wiring drag-and-drop, so it
        # has to exist before _build_ui runs.
        self._dnd_msgs: list = []

        STORE_DIR.mkdir(parents=True, exist_ok=True)
        HELPERS_DIR.mkdir(parents=True, exist_ok=True)

        self._build_ui()
        # The slideshow tick is set by the panel's own background query — see
        # its on_scheduled. Asking schtasks here as well put a scheduler call
        # on the main thread before the window had even appeared.
        self._mark_tab(self._reminder_panel, bool(self.cfg.get("reminder_set")))
        self.font_size = scaling.apply(self.cfg.get("font_size"))
        self._apply_theme()
        self._bind_shortcuts()

        # Put the window on screen before anything else. Everything in
        # _finish_startup reads the disk, the registry, the scheduler or the
        # network, and none of it is needed to draw the window -- but all of it
        # used to run first, so the app sat there unresponsive until it was
        # done.
        self.root.update_idletasks()
        self.root.after_idle(self._finish_startup)

    def _finish_startup(self):
        """Everything that can wait until the window is up."""
        self._start_clock()
        self._seed_default_favorites()
        self._refresh_history_list()
        self._refresh_store_list()
        self._refresh_favorites_list()
        self._show_last_changed()
        threading.Thread(target=self._check_slideshow_runner, daemon=True).start()
        self._update_ls_btn()
        self._maybe_check_updates()

    # ── UI Construction ───────────────────────────────────────────────────────
    # Full _build_ui is in ui.py and patched in via _build_ui() below.
    # Keep this import-based so ui.py can be edited independently.

    def _build_ui(self):
        from .ui import build_ui
        build_ui(self)

    # ── Keyboard shortcuts ────────────────────────────────────────────────────

    def _bind_shortcuts(self):
        self.root.bind("<Control-r>", lambda _: self._start_task())
        self.root.bind("<Control-R>", lambda _: self._start_task())
        self.root.bind("<Escape>",    lambda _: self._cancel_task())
        self.root.bind("<Control-l>", lambda _: self._clear_log())
        self.root.bind("<Control-L>", lambda _: self._clear_log())
        self.root.bind("<F1>",        lambda _: self._show_about())

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg, tag=""):
        line = f"[{datetime.now().strftime('%H:%M:%S')}]  {msg}\n"
        self.console.insert(tk.END, line, tag if tag else "default")
        if self._autoscroll_var.get():
            self.console.see(tk.END)

    def _log_threadsafe(self, msg, tag=""):
        self.root.after(0, lambda: self._log(msg, tag))

    def _log_separator(self):
        self._log("─" * 52, "dim")

    def _clear_log(self):
        self.console.delete("1.0", tk.END)

    def _on_autoscroll_toggle(self):
        val = self._autoscroll_var.get()
        self.cfg.set("autoscroll", val)
        if val:
            self.console.see(tk.END)

    # ── Status bar & clock ────────────────────────────────────────────────────

    def _set_status(self, msg):
        self.root.after(0, lambda: self.status_var.set(msg))

    def _start_clock(self):
        self._tick_clock()

    def _tick_clock(self):
        self.clock_var.set(datetime.now().strftime("%H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    # ── Progress bar ──────────────────────────────────────────────────────────

    def _progress_start(self):
        self._progress.config(mode="indeterminate", value=0, maximum=100)
        self._progress.start(12)

    def _progress_set(self, value, maximum=100.0):
        if self._progress["mode"] != "determinate":
            self._progress.stop()
            self._progress.config(mode="determinate", maximum=maximum)
        self._progress["value"] = value

    def _progress_stop(self):
        self._progress.stop()
        self._progress.config(value=0)

    # ── Completion banners ────────────────────────────────────────────────────

    @staticmethod
    def _fmt_elapsed(s):
        return f"{int(s//60)}m {int(s%60)}s" if s >= 60 else f"{s:.1f}s"

    def _banner_success(self, label, elapsed):
        self._log_separator()
        self._log(f"✔  {label} — completed in {self._fmt_elapsed(elapsed)}", "green")
        self._log_separator()
        self._set_status(f"✔  {label}  ({self._fmt_elapsed(elapsed)})")

    def _banner_cancelled(self, label, elapsed):
        self._log_separator()
        self._log(f"◼  {label} — cancelled after {self._fmt_elapsed(elapsed)}", "yellow")
        self._log_separator()
        self._set_status(f"◼  {label} — cancelled")

    def _banner_error(self, label, elapsed, detail=""):
        self._log_separator()
        self._log(f"✖  {label} — FAILED after {self._fmt_elapsed(elapsed)}", "red")
        if detail:
            self._log(f"   {detail}", "red")
        self._log_separator()
        self._set_status(f"✖  {label} — error")

    # ── Cancel ────────────────────────────────────────────────────────────────

    def _cancel_task(self):
        if self.is_running:
            self._cancel_event.set()
            self._set_status("Cancelling…")
            self._log("◼  Cancel requested — stopping at next checkpoint…", "yellow")

    def _confirm(self, message, title="Confirm"):
        return messagebox.askyesno(title, message, parent=self.root)

    # ── Apply wallpaper task ──────────────────────────────────────────────────

    def _start_task(self):
        if self.is_running:
            return
        src = self._pending_path.get().strip()
        if not src:
            self._log("⚠  No image selected. Drop a file, paste a URL, or Browse.", "yellow")
            return
        self._cancel_event = threading.Event()
        self.is_running = True
        self._set_running_state(True)
        self._set_status("Applying wallpaper…")
        threading.Thread(target=self._do_task, daemon=True).start()

    def _do_task(self):
        t0    = time.monotonic()
        label = "Set Wallpaper"
        src   = wp.normalize_src(self._pending_path.get().strip())
        style = self._style_var.get()
        copy  = self._copy_var.get()
        try:
            self._log_threadsafe("─" * 52, "dim")
            self._log_threadsafe(f"Source: {src}", "cyan")
            self._log_threadsafe(f"Style:  {style}", "cyan")
            self.root.after(0, self._progress_start)

            if self._cancel_event.is_set(): raise InterruptedError()

            is_url = src.lower().startswith(("http://", "https://"))
            if is_url:
                local_path = wp.download_image(src, self._log_threadsafe,
                                               cancel_event=self._cancel_event)
            else:
                local_path = Path(src)
                if not local_path.exists():
                    raise FileNotFoundError(f"File not found: {local_path}")

            if self._cancel_event.is_set(): raise InterruptedError()

            # Anywhere under the store counts: the store has subfolders
            # now, and a file in one of them does not need copying to the top.
            already_stored = wp.is_in_store(local_path)
            needs_copy = (is_url or copy) and not already_stored
            if needs_copy:
                dest = STORE_DIR / local_path.name
                if dest.exists() and dest.resolve() != local_path.resolve():
                    stem, sfx = local_path.stem, local_path.suffix
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dest = STORE_DIR / f"{stem}_{ts}{sfx}"
                shutil.copy2(str(local_path), str(dest))
                self._log_threadsafe(f"Copied to store: {dest.name}", "magenta")
                local_path = dest
            else:
                if already_stored:
                    self._log_threadsafe("Already in store — no copy needed.", "dim")

            if self._cancel_event.is_set(): raise InterruptedError()

            wp.apply_wallpaper(str(local_path), style)
            self._log_threadsafe(f"✔  Wallpaper set: {local_path.name}", "green")

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            history = self.cfg.get("history") or []
            entry = {"path": str(local_path), "set_at": now_str, "style": style,
                     "original": src}
            history.insert(0, entry)
            history = history[:50]
            self.cfg.set("history", history)
            self.cfg.set("last_changed", now_str)

            elapsed = time.monotonic() - t0
            self.root.after(0, lambda e=elapsed: self._banner_success(label, e))
            self.root.after(0, self._refresh_history_list)
            # Applying with "Copy image to local store" ticked puts a new file
            # in the store, so the pane that lists it has to hear about it.
            self.root.after(0, self._refresh_store_list)
            self.root.after(0, self._show_last_changed)

        except InterruptedError:
            elapsed = time.monotonic() - t0
            self.root.after(0, lambda e=elapsed: self._banner_cancelled(label, e))
        except Exception as exc:
            elapsed = time.monotonic() - t0
            self.root.after(0, lambda e=elapsed, x=str(exc):
                self._banner_error(label, e, x))
        finally:
            self.is_running = False
            self.root.after(0, self._progress_stop)
            self.root.after(0, lambda: self._set_running_state(False))

    def _set_running_state(self, running):
        self.apply_btn.config(state=tk.DISABLED if running else tk.NORMAL)
        self.cancel_btn.config(state=tk.NORMAL if running else tk.DISABLED)

    # ── Browse / file ops ─────────────────────────────────────────────────────

    def active_panes(self):
        """
        The pane set of whichever tab is in front.

        The menu, the shortcuts and the clipboard should act on the tab you
        are looking at, not always on the Wallpaper one.
        """
        ls = getattr(self, "_ls_panes", None)
        try:
            if ls is not None and self._notebook.nametowidget(
                    self._notebook.select()) is self._lock_tab:
                return ls
        except (tk.TclError, AttributeError):
            pass
        return self._wp_panes

    def _browse_image(self):
        self.active_panes().browse()

    def _open_image_picker(self, title="Select image", initial_dir=None):
        return filedialog.askopenfilename(
            title=title,
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.gif *.webp *.tiff *.avif *.heic"),
                ("All files",   "*.*"),
            ],
            initialdir=initial_dir or str(Path.home()),
        )

    def _open_store_folder(self):
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        HELPERS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(STORE_DIR))

    def _show_current_wallpaper(self):
        path = wp.get_current_wallpaper_path()
        if not path:
            self._log("No wallpaper is currently set.", "dim")
            return
        self._log(f"Current wallpaper: {path}", "cyan")
        self._wp_panes.select(path, icon="🖥")

    # ── DnD ───────────────────────────────────────────────────────────────────

    def _post_build_log(self):
        for msg, tag in getattr(self, "_dnd_msgs", []):
            self._log(msg, tag)

    def _place_sizegrip(self):
        sg = ttk.Sizegrip(self.root)
        sg.place(relx=1.0, rely=1.0, anchor="se")
        sg.lift()

    # Drag-and-drop, the clipboard and the URL field all live on the pane
    # sets now (app/imagepanes.py), so both tabs get them from one place.
    # These remain as the names the shortcuts and menus already call.

    def _on_drop_enter(self, event):
        self.active_panes().on_drop_enter(event)

    def _on_drop_leave(self, event):
        self.active_panes().on_drop_leave(event)

    def _on_drop(self, event):
        self.active_panes().on_drop(event)

    def _on_paste(self, event=None):
        self.active_panes().on_paste(event)

    def _on_path_changed(self, *_):
        self._wp_panes.on_path_changed()

    def _auto_preview_from_entry(self):
        self._wp_panes.auto_preview_from_entry()

    def _on_drop_on_add_btn(self, event):
        raw = event.data.strip()
        resolved, warning = dnd_mod.resolve_drop_data(raw)
        if not resolved:
            self._log(f"⚠  Could not resolve dropped item: {raw[:80]}", "yellow")
            return
        try:
            event.widget.config(relief=tk.RAISED)
        except Exception:
            pass
        is_url = resolved.startswith(("http://", "https://"))
        is_dir  = (not is_url) and Path(resolved).is_dir()
        is_file = (not is_url) and Path(resolved).is_file()
        if is_dir:
            self._save_favorite(Path(resolved).name, resolved)
            self._log(f"Favorite folder added: {resolved}", "green")
        elif is_url:
            label = resolved.split("/")[2] if "/" in resolved else resolved[:40]
            dialog = _InputDialog(self.root, "Add URL Favorite",
                                  f"Confirm label for:\n{resolved[:80]}",
                                  self.theme_name,
                                  prefill_label=label, prefill_url=resolved)
            self.root.wait_window(dialog)
            if dialog.result:
                lbl, url = dialog.result
                self._save_favorite(lbl, url)
                self._log(f"Favorite URL added: {url}", "green")
        elif is_file:
            folder = str(Path(resolved).parent)
            self._save_favorite(Path(folder).name, folder)
            self._log(f"Favorite folder added (from file): {folder}", "green")
        else:
            self._log(f"⚠  Cannot add as favorite: {resolved[:80]}", "yellow")

    # ── Preview ───────────────────────────────────────────────────────────────

    def _load_preview(self):
        self._wp_panes.load_preview()

    def _reflow_preview(self, target_label=None):
        self._wp_panes.reflow_preview()

    def _on_preview_resize(self, event):
        self._wp_panes.on_preview_resize(event)

    # ── Image store ───────────────────────────────────────────────────────────

    def _refresh_store_list(self):
        """Re-read the store for every tab that lists it."""
        for attr in ("_wp_panes", "_ls_panes"):
            panes = getattr(self, attr, None)
            if panes is not None:
                panes.refresh_store()
        panel = getattr(self, "_playlist_panel", None)
        if panel is not None:
            panel.refresh_store()

    # ── Playlists ─────────────────────────────────────────────────────────────

    def _show_playlists_tab(self):
        self._select_tab(self._playlist_panel)

    def _use_playlist(self, name):
        """The Playlists tab handing one to the slideshow."""
        self._slideshow_panel.use_playlist(name)
        self._select_tab(self._slideshow_panel)
        self._log(f"Slideshow source set to playlist: {name}", "cyan")
        self._log("   Press ▶ Start on the Slideshow tab to schedule it.", "dim")

    def _on_playlists_changed(self):
        """A playlist was added, renamed or deleted — refresh the chooser."""
        panel = getattr(self, "_slideshow_panel", None)
        if panel is not None:
            panel.refresh_playlists()

    def add_to_playlist(self, paths, name=None):
        """
        Put images in a playlist from anywhere in the app.

        `name` None asks for a new playlist. Returns the playlist's name, or
        None if nothing was added.
        """
        from . import playlists as pl
        from .dialogs import NameDialog
        if not paths:
            return None
        if name is None:
            dlg = NameDialog(self.root, "New Playlist",
                             "Name for the new playlist:", self.theme_name,
                             label="Playlist name:")
            self.root.wait_window(dlg)
            name = dlg.result
            if not name:
                return None
            if not pl.create(name):
                messagebox.showerror(
                    "Playlist exists",
                    f"A playlist called \u201c{name}\u201d already exists.",
                    parent=self.root)
                return None
        items = pl.items(name)
        have  = {i.lower() for i in items}
        added = [p for p in paths if str(p).lower() not in have]
        pl.set_items(name, items + [str(p) for p in added])
        self._log(f"Playlist “{name}”: added {len(added)} image"
                  f"{'' if len(added) == 1 else 's'}.", "green")
        panel = getattr(self, "_playlist_panel", None)
        if panel is not None:
            panel.refresh_playlists(select=name)
        self._on_playlists_changed()
        return name

    def _on_store_select(self, _=None):
        self._wp_panes.on_store_select()

    # ── History ───────────────────────────────────────────────────────────────

    def _refresh_history_list(self):
        history = self.cfg.get("history") or []
        self._hist_listbox.delete(0, tk.END)
        for item in history:
            path  = item.get("path", "")
            set_at = item.get("set_at", "")
            style  = item.get("style", "")
            self._hist_listbox.insert(tk.END,
                f"{set_at}  [{style}]  {Path(path).name}")

    def _on_history_select(self, _=None):
        sel = self._hist_listbox.curselection()
        if not sel:
            return
        history = self.cfg.get("history") or []
        idx = sel[0]
        if idx < len(history):
            item = history[idx]
            path = item.get("path", "")
            self._pending_path.set(path)
            self._style_var.set(item.get("style", "Fill"))
            self._drop_label.config(text=f"📎  {Path(path).name}")
            self._load_preview()

    def _clear_history(self):
        if self._confirm("Clear all wallpaper history?"):
            self.cfg.set("history", [])
            self._refresh_history_list()
            self._log("History cleared.", "yellow")

    def _show_last_changed(self):
        lc = self.cfg.get("last_changed")
        if lc:
            self._last_changed_var.set(f"🕐  Last changed: {lc}")
        else:
            self._last_changed_var.set("🕐  No wallpaper set yet via this app.")

    # ── Favorites ─────────────────────────────────────────────────────────────

    _DEFAULT_FAVORITES = [
        {"label": "lucid24 wallpaper", "location": "https://archive.org/details/lucid24.org-wallpaper-desktop-image"},
        {"label": "lucid24 AN",        "location": "https://lucid24.org/an/index.html"},
        {"label": "lucid24 DN",        "location": "https://lucid24.org/dn/index.html"},
        {"label": "lucid24 KN",        "location": "https://lucid24.org/kn/index.html"},
        {"label": "lucid24 MN",        "location": "https://lucid24.org/mn/index.html"},
        {"label": "lucid24 SN",        "location": "https://lucid24.org/sn/index.html"},
    ]

    def _seed_default_favorites(self):
        favs = self.cfg.get("favorites") or []
        existing_locs = {f["location"]: i for i, f in enumerate(favs)}
        _label_migrations = {
            "Lucid24 — Mandalas":     "lucid24 MN",
            "Lucid24 — Abstract":     "lucid24 AN",
            "Lucid24 — Dark":         "lucid24 DN",
            "Lucid24 — Kaleidoscope": "lucid24 KN",
            "Lucid24 — Symmetry":     "lucid24 SN",
        }
        migrated = 0
        for fav in favs:
            if fav["label"] in _label_migrations:
                fav["label"] = _label_migrations[fav["label"]]
                migrated += 1
        added = 0
        archive_url = self._DEFAULT_FAVORITES[0]["location"]
        if archive_url not in existing_locs:
            favs.insert(0, self._DEFAULT_FAVORITES[0])
            added += 1
            existing_locs = {f["location"]: i for i, f in enumerate(favs)}
        if not self.cfg.get("seeded_favorites"):
            for entry in self._DEFAULT_FAVORITES[1:]:
                if entry["location"] not in existing_locs:
                    favs.append(entry)
                    added += 1
        if migrated or added:
            self.cfg.set("favorites", favs)
            if added:
                self._log(f"Added {added} default gallery favorites.", "dim")
        self.cfg.set("seeded_favorites", True)

    def _refresh_favorites_list(self):
        favs = self.cfg.get("favorites") or []
        self._fav_listbox.delete(0, tk.END)
        for f in favs:
            icon = "🌐" if f.get("location", "").startswith("http") else "📁"
            self._fav_listbox.insert(tk.END,
                f"{icon}  {f['label']}  —  {f['location']}")

    def _add_favorite_folder(self):
        d = filedialog.askdirectory(title="Add folder to favorites",
                                    initialdir=str(Path.home()))
        if not d:
            return
        self._save_favorite(Path(d).name, d)
        self._log(f"Favorite folder added: {d}", "green")

    def _add_favorite_url(self):
        dialog = _InputDialog(self.root, "Add Gallery URL",
                              "Enter a label and URL for a gallery or image page:",
                              self.theme_name)
        self.root.wait_window(dialog)
        if dialog.result:
            label, url = dialog.result
            self._save_favorite(label, url)
            self._log(f"Favorite URL added: {url}", "green")

    def _remove_favorite(self):
        sel = self._fav_listbox.curselection()
        if not sel:
            return
        self._delete_favorite(sel[0])

    def _save_favorite(self, label, location):
        favs = self.cfg.get("favorites") or []
        if any(f["location"] == location for f in favs):
            self._log(f"Already in favorites: {location}", "dim")
            return
        favs.append({"label": label, "location": location})
        self.cfg.set("favorites", favs)
        self._refresh_favorites_list()

    def _open_favorite(self, _=None):
        sel = self._fav_listbox.curselection()
        if not sel:
            return
        favs = self.cfg.get("favorites") or []
        idx = sel[0]
        if idx >= len(favs):
            return
        loc = favs[idx].get("location", "")
        if loc.startswith("http"):
            import webbrowser
            webbrowser.open(loc)
            self._log(f"Opened in browser: {loc}", "cyan")
        else:
            path = self._open_image_picker(
                title=f"Select image from {Path(loc).name}",
                initial_dir=loc)
            if path:
                self._pending_path.set(path)
                self._drop_label.config(text=f"📎  {Path(path).name}")
                self._load_preview()

    def _on_fav_right_click(self, event):
        idx = self._fav_listbox.nearest(event.y)
        if idx < 0:
            return
        self._fav_listbox.selection_clear(0, tk.END)
        self._fav_listbox.selection_set(idx)
        favs = self.cfg.get("favorites") or []
        if idx >= len(favs):
            return
        t = THEMES.get(self.theme_name, THEMES["dark"])
        menu = tk.Menu(self.root, tearoff=0,
                       font=scaling.font("Segoe UI", 9))
        menu.configure(bg=t["btn_bg"], fg=t["fg"],
                       activebackground=BTN_COLORS["primary"]["bg"],
                       activeforeground="#ffffff")
        menu.add_command(label="✏  Rename label…",
                         command=lambda: self._rename_favorite(idx))
        menu.add_command(label="🗑  Delete",
                         command=lambda: self._delete_favorite(idx))
        menu.add_separator()
        loc = favs[idx].get("location", "")
        if loc.startswith("http"):
            menu.add_command(label="🌐  Open in browser",
                             command=lambda: self._open_favorite())
        else:
            menu.add_command(label="📁  Open in Explorer",
                             command=lambda l=loc: os.startfile(l)
                             if Path(l).exists() else None)
        menu.tk_popup(event.x_root, event.y_root)

    def _rename_favorite(self, idx):
        favs = self.cfg.get("favorites") or []
        if idx >= len(favs):
            return
        fav = favs[idx]
        dialog = _RenameDialog(self.root, fav["label"], fav["location"],
                               self.theme_name)
        self.root.wait_window(dialog)
        if dialog.result:
            new_label, new_loc = dialog.result
            old_label = fav["label"]
            favs[idx]["label"]    = new_label
            favs[idx]["location"] = new_loc
            self.cfg.set("favorites", favs)
            self._refresh_favorites_list()
            self._log(f"Updated favorite: '{old_label}' → '{new_label}'  {new_loc}", "cyan")

    def _delete_favorite(self, idx):
        favs = self.cfg.get("favorites") or []
        if idx >= len(favs):
            return
        removed = favs.pop(idx)
        self.cfg.set("favorites", favs)
        self._refresh_favorites_list()
        self._log(f"Removed favorite: {removed['label']}", "yellow")

    def _restore_default_favorites(self):
        favs = self.cfg.get("favorites") or []
        existing_locs = {f["location"] for f in favs}
        added = []
        for entry in self._DEFAULT_FAVORITES:
            if entry["location"] not in existing_locs:
                favs.append(entry)
                added.append(entry["label"])
        if added:
            self.cfg.set("favorites", favs)
            self._refresh_favorites_list()
            self._log(f"Restored {len(added)} default favorite(s): {', '.join(added)}", "green")
        else:
            self._log("All default favorites are already present — nothing to restore.", "dim")

    # ── Lock screen ───────────────────────────────────────────────────────────

    def _set_lock_screen(self):
        # The Lock Screen tab has its own selection now; it used to be able to
        # apply only whatever the Wallpaper tab happened to be holding.
        panes = self._ls_panes
        src = wp.normalize_src(panes.pending.get().strip())
        if not src:
            self._log("⚠  No image selected. Drop or paste an image first.", "yellow")
            return

        # ── If it's a URL, silently download+store first ──────────────────────
        if src.lower().startswith(("http://", "https://")):
            self._log("Downloading image for lock screen…", "cyan")
            try:
                local_path = wp.download_image(src, self._log)
                # copy to store
                dest = STORE_DIR / local_path.name
                if not dest.exists():
                    import shutil as _sh
                    _sh.copy2(str(local_path), str(dest))
                    self._log(f"Saved to store: {dest.name}", "magenta")
                    local_path = dest
                src = str(local_path)
                panes.select(src, label=local_path.name)
            except Exception as e:
                self._log(f"✖  Download failed: {e}", "red")
                return

        path = Path(src)
        if not path.exists():
            self._log(f"⚠  File not found: {path}", "yellow")
            return

        # ── If file is not in store, copy it there silently ───────────────────
        # PersonalizationCSP requires a stable path that won't move/delete
        already_stored = wp.is_in_store(path)
        if not already_stored:
            try:
                import shutil as _sh
                dest = STORE_DIR / path.name
                if dest.exists() and dest.resolve() != path.resolve():
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dest = STORE_DIR / f"{path.stem}_{ts}{path.suffix}"
                _sh.copy2(str(path), str(dest))
                self._log(f"Copied to store for lock screen: {dest.name}", "magenta")
                path = dest
            except Exception as e:
                self._log(f"⚠  Could not copy to store: {e} — using original path.", "yellow")

        spotlight_on, _ = wp.check_spotlight_status()
        msg = (
            "Changing the lock screen requires a one-time Windows\n"
            "permission prompt (UAC).\n\n"
            "What will happen:\n"
            "  1. A small helper program launches (you'll see the UAC prompt)\n"
            "  2. It changes the lock screen and exits immediately\n"
            "  3. This app stays open the whole time\n"
            f"\nImage: {path.name}"
        )
        if not messagebox.askokcancel("Set Lock Screen — Permission Required",
                                      msg, parent=self.root):
            return
        if spotlight_on:
            wp.disable_spotlight(self._log)
        self._log("─" * 52, "dim")
        self._log("Launching lock screen helper (UAC prompt will appear)…", "cyan")
        threading.Thread(target=self._do_set_lock_screen,
                         args=(path,), daemon=True).start()

    def _do_set_lock_screen(self, img_path):
        try:
            # launch_elevated waits for the elevated helper to exit, so the
            # registry check below sees the helper's writes.
            if not wp.launch_elevated("set-lockscreen", str(img_path), self._log_threadsafe):
                return
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP",
                    0, winreg.KEY_READ)
                set_path, _ = winreg.QueryValueEx(key, "LockScreenImagePath")
                winreg.CloseKey(key)
                if Path(set_path).resolve() == img_path.resolve():
                    self._log_threadsafe("─" * 52, "dim")
                    self._log_threadsafe("✔  Lock screen set successfully.", "green")
                    self._log_threadsafe(f"   Image: {img_path.name}", "dim")
                    self._log_threadsafe("   Press Win+L to verify.", "dim")
                else:
                    self._log_threadsafe("⚠  Registry updated but path differs — may need Win+L.", "yellow")
            except Exception:
                self._log_threadsafe("─" * 52, "dim")
                self._log_threadsafe("✔  Helper ran — press Win+L to verify.", "green")
            self.root.after(0, self._update_ls_btn)
        except Exception as e:
            self._log_threadsafe(f"✖  Error: {e}", "red")

    def _release_lock_screen(self):
        if not messagebox.askokcancel(
                "Release Lock Screen Policy",
                "This will remove the managed lock screen policy set by this app.\n\n"
                "A UAC prompt will appear briefly.\n\nContinue?",
                parent=self.root):
            return
        self._log("─" * 52, "dim")
        self._log("Releasing lock screen policy (UAC prompt will appear)…", "cyan")
        threading.Thread(target=self._do_release_lock_screen, daemon=True).start()

    def _do_release_lock_screen(self):
        try:
            if not wp.launch_elevated("release-lockscreen", "", self._log_threadsafe):
                return
            import winreg
            try:
                winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP",
                    0, winreg.KEY_READ)
                self._log_threadsafe("✔  Lock screen values cleared.", "green")
            except FileNotFoundError:
                self._log_threadsafe("✔  Lock screen policy removed completely.", "green")
            self._log_threadsafe("   Settings → Personalization → Lock screen", "dim")
            self._log_threadsafe("   dropdown is now editable.", "dim")
        except Exception as e:
            self._log_threadsafe(f"✖  Error: {e}", "red")

    def _update_ls_btn(self):
        """Update the Personalize/Release button based on whether CSP is set."""
        try:
            # Reuse one Tooltip and update its text — creating a new Tooltip
            # per refresh would leak instances.
            if not hasattr(self, "_ls_pers_tip"):
                self._ls_pers_tip = Tooltip(self._ls_pers_btn, "")
            if wp.csp_is_set():
                c = BTN_COLORS["danger"]
                self._ls_pers_btn.config(
                    text="🔓 Release & Personalize",
                    bg=c["bg"], fg=c["fg"], activebackground=c["active"])
                self._ls_pers_tip.text = (
                    "A custom lock screen image is active.\n"
                    "Click to remove the policy (UAC prompt)\n"
                    "then open Settings → Lock screen.")
            else:
                c = BTN_COLORS["primary"]
                self._ls_pers_btn.config(
                    text="⚙  Personalize Lock Screen",
                    bg=c["bg"], fg=c["fg"], activebackground=c["active"])
                self._ls_pers_tip.text = (
                    "Open Settings → Personalization → Lock screen.")
        except Exception:
            pass

    def _ls_personalize_or_release(self):
        if wp.csp_is_set():
            if not messagebox.askokcancel(
                    "Release & Open Lock Screen Settings",
                    "Click OK to remove the policy (UAC) then open Settings.",
                    parent=self.root):
                return
            threading.Thread(
                target=self._do_release_then_settings, daemon=True).start()
        else:
            self._open_lock_screen_settings()

    def _do_release_then_settings(self):
        try:
            if not wp.launch_elevated("release-lockscreen", "", self._log_threadsafe):
                return
            self._log_threadsafe("✔  Policy removed — opening Settings.", "green")
            self.root.after(0, self._open_lock_screen_settings)
            self.root.after(0, self._update_ls_btn)
        except Exception as e:
            self._log_threadsafe(f"✖  Error: {e}", "red")

    def _open_lock_screen_settings(self):
        for uri in ["ms-settings:lockscreen", "ms-settings:personalization"]:
            try:
                os.startfile(uri)
                self._log("Opened Settings → Personalization → Lock screen.", "dim")
                self.root.after(4000, self._update_ls_btn)
                return
            except Exception:
                continue

    def _show_lock_preview(self):
        """
        Load the image Windows is using now into the Lock tab.

        It becomes that tab's selection, the way "Current Wallpaper" does on
        the Wallpaper tab -- so you can look at it, and re-apply it, without
        hunting for the file. The preview composites it at Fill, which is how
        Windows shows a lock screen.
        """
        path_str, source = wp.find_current_lock_screen_image()
        panes = self._ls_panes
        if not path_str:
            panes.preview_info_var.set("")
            panes.preview_label.config(
                image="", text="No lock screen image found.\n"
                               "Windows may be using a solid colour, "
                               "or access is restricted.")
            self._log("⚠  No lock screen image found.", "yellow")
            return
        self._log(f"Current lock screen: {Path(path_str).name}", "cyan")
        self._log(f"  Source: {source}", "dim")
        panes.select(path_str, icon="🔒")

    # ── Windows Sources menu ──────────────────────────────────────────────────

    def _show_win_sources_menu(self):
        menu = tk.Menu(self.root, tearoff=0,
                       font=scaling.font("Segoe UI", 9))
        t = THEMES.get(self.theme_name, THEMES["dark"])
        menu.configure(bg=t["btn_bg"], fg=t["fg"],
                       activebackground=BTN_COLORS["primary"]["bg"],
                       activeforeground="#ffffff")
        for src in WIN_IMAGE_SOURCES:
            p = src["path"]
            exists = p.exists()
            label = f"{'📁' if exists else '✖'}  {src['label']}"
            if exists:
                menu.add_command(label=label,
                                 command=lambda p=p, s=src: self._open_win_source(p, s))
            else:
                menu.add_command(label=f"{label}  (not found)", state=tk.DISABLED)
        spotlight = WIN_IMAGE_SOURCES[2]["path"]
        if spotlight.exists():
            menu.add_separator()
            menu.add_command(
                label="📋  Copy Spotlight images → Store (rename to .jpg)",
                command=self._copy_spotlight_images)
        btn = self._win_src_btn
        menu.tk_popup(btn.winfo_rootx(),
                      btn.winfo_rooty() + btn.winfo_height())

    def _open_win_source(self, path, src):
        if not path.exists():
            messagebox.showinfo("Not found", f"Directory not found:\n{path}",
                                parent=self.root)
            return
        self._log(f"Opening: {path}", "cyan")
        if "Spotlight" in src["label"]:
            messagebox.showinfo(
                "Spotlight Images",
                "Spotlight images have no file extension.\n\n"
                "To use one:\n1. Copy the file\n2. Rename it to something.jpg\n"
                "3. Drag it into this app\n\n"
                "Or use 'Copy Spotlight images → Store' to auto-rename them all.",
                parent=self.root)
        os.startfile(str(path))

    def _copy_spotlight_images(self):
        copied, skipped = wp.copy_spotlight_images(self._log)
        self._log(f"Spotlight: copied {copied} images, skipped {skipped} thumbnails.", "green")
        if copied:
            os.startfile(str(STORE_DIR))

    # ── Reminder ──────────────────────────────────────────────────────────────

    def _preview_desktop(self):
        """Minimize all windows, show countdown overlay, restore on timer/click."""
        hwnd = int(self.root.wm_frame(), 16)
        start_preview(self.root, hwnd)

    def _check_slideshow_runner(self):
        if slideshow_runner_is_stale():
            self._log_threadsafe(
                "⚠  Slideshow task points to an old location. "
                "Open Slideshow → ▶ Start to update it.", "yellow")
            return
        failed, detail = slideshow_last_run_failed()
        if failed:
            self._log_threadsafe(
                "⚠  Slideshow last run failed ({})."
                "  Open Slideshow → 📋 Log for details.".format(detail), "yellow")

    def _select_tab(self, widget):
        """Bring a tab to the front. The toolbar buttons are now navigation."""
        try:
            self._notebook.select(widget)
        except (tk.TclError, AttributeError):
            pass

    def _mark_tab(self, widget, active: bool):
        """
        Put a ✔ on a tab while its feature is scheduled.

        The toolbar used to carry this on a button that did nothing but select
        the tab next to it. On the tab itself it is in the one place that is
        always visible, whichever tab you are looking at.
        """
        try:
            base = self._notebook.tab(widget, "text").replace("✔", "").rstrip()
            self._notebook.tab(widget, text=base + (" ✔  " if active else "  "))
        except (tk.TclError, AttributeError):
            pass

    def _show_slideshow_tab(self):
        self._select_tab(self._slideshow_panel)

    def _on_tab_changed(self, _event=None):
        """
        Refresh a panel as it comes to the front.

        As dialogs these re-read the scheduler on every open. Built once as
        tabs, a status queried ten minutes ago would otherwise just sit there
        claiming the slideshow is running after it was stopped elsewhere.
        """
        try:
            current = self._notebook.nametowidget(self._notebook.select())
        except (tk.TclError, AttributeError):
            return
        if current is getattr(self, "_slideshow_panel", None):
            # Threaded, and it reports back through on_scheduled to set the
            # tick. It used to be followed by a synchronous schtasks query,
            # which is what made this tab pause before it would draw.
            current._refresh_status()

    def _show_reminder_tab(self):
        self._select_tab(self._reminder_panel)

    def _on_slideshow_result(self, result):
        """Called by the Slideshow tab after an action. Nothing is waited on."""
        if result == "started":
            self._mark_tab(self._slideshow_panel, True)
            self._log("Wallpaper slideshow started.", "green")
        elif result == "stopped":
            self._mark_tab(self._slideshow_panel, False)
            self._log("Wallpaper slideshow stopped.", "yellow")
        elif result == "preview-started":
            self._log("▶  Slideshow preview started — the wallpaper will "
                      "rotate while QiGor is open.", "cyan")
        elif result == "preview-stopped":
            self._log("⏹  Slideshow preview stopped.", "yellow")
        elif result == "next":
            from .slideshow import load_state as ss_load_state
            state = ss_load_state()
            last = state.get("last_file", "")
            if last:
                self._log(f"⏭  Slideshow → {last}", "cyan")
            else:
                self._log("⏭  Slideshow advanced to next image.", "cyan")
            self.root.after(500, self._show_current_wallpaper)

    def _on_reminder_result(self, result):
        """Called by the Reminder tab after an action."""
        if result == "set":
            self.cfg.set("reminder_set", True)
            self._mark_tab(self._reminder_panel, True)
            self._log("Wallpaper reminder scheduled.", "green")
        elif result == "removed":
            self.cfg.set("reminder_set", False)
            self._mark_tab(self._reminder_panel, False)
            self._log("Wallpaper reminder removed.", "yellow")

    def _show_reminder_notification(self):
        msg = "Time to freshen your wallpaper 🖼"
        notified = False
        try:
            from winotify import Notification, audio
            toast = Notification(
                app_id="QiGor Wallpaper Manager",
                title="Wallpaper Reminder",
                msg=msg, duration="short",
                launch=str(_get_exe_dir() / ("QiGor_Wallpaper_Manager.exe" if getattr(sys, "frozen", False) else "qigor_wallpaper_manager.pyw")))
            toast.set_audio(audio.Default, loop=False)
            toast.show()
            notified = True
        except ImportError:
            pass
        except Exception as e:
            self._log(f"Toast notification failed: {e}", "dim")
        self._set_status(f"⏰  {msg}")
        self._log(f"⏰  Reminder: {msg}", "cyan")
        if not notified:
            self._log("   (Install winotify for desktop toast:  pip install winotify)", "dim")

    # ── About ─────────────────────────────────────────────────────────────────

    def _show_about(self):
        AboutDialog(self.root, self.theme_name)

    # ── Updates and installation ──────────────────────────────────────────────

    def _check_updates(self):
        try:
            from .updater import UpdateDialog
        except Exception as e:
            messagebox.showerror("Updates unavailable",
                                 "The updater could not be loaded:\n\n{}".format(e),
                                 parent=self.root)
            return
        UpdateDialog(self).show()

    def _maybe_check_updates(self):
        """Poll GitHub at most once a day, in the background, never blocking startup."""
        try:
            from . import updater
        except Exception:
            return
        if not updater.due_for_check(self.cfg):
            return
        threading.Thread(target=updater.background_check, args=(self,),
                         daemon=True).start()

    def _can_install_to_pc(self) -> bool:
        """
        True only for a loose folder that carries its own runtime — a source
        checkout has nothing to install, and an installed copy is already there.
        """
        try:
            from installer.paths import payload_root, is_installed_copy
            from installer.core import validate_payload
        except Exception:
            return False
        root = payload_root()
        return not is_installed_copy(root) and validate_payload(root) is None

    def _is_installed_copy(self) -> bool:
        try:
            from installer.paths import is_installed_copy
            return is_installed_copy()
        except Exception:
            return False

    def _uninstall(self):
        """
        Open the uninstaller, then close, since it has to remove the folder this
        process is running from. A separate process for the same reason the
        installer is one: it builds its own Tk root.
        """
        from installer.paths import payload_root
        root = payload_root()
        if not messagebox.askokcancel(
                "Uninstall",
                "This closes QiGor and opens the uninstaller.\n\n"
                "You can also reach it any time from\n"
                "Settings ▸ Apps ▸ Installed apps.",
                parent=self.root):
            return
        try:
            subprocess.Popen([sys.executable, str(root / "installer" / "uninstall.py")],
                             cwd=str(Path.home()), close_fds=True)
        except Exception as e:
            messagebox.showerror("Could not start the uninstaller", str(e),
                                 parent=self.root)
            return
        self.root.after(400, self._on_close)

    def _install_to_pc(self):
        """Hand off to the installer window. A separate process, because it
        builds its own Tk root."""
        from installer.paths import payload_root
        root = payload_root()
        try:
            subprocess.Popen([sys.executable, str(root / "installer" / "install.py")],
                             cwd=str(root), close_fds=True)
        except Exception as e:
            messagebox.showerror("Could not start the installer", str(e),
                                 parent=self.root)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        t = THEMES.get(self.theme_name, THEMES["dark"])
        self.root.configure(bg=t["bg"])
        self.console.configure(bg=t["console_bg"], fg=t["console_fg"],
                               insertbackground=t["console_fg"])
        self._status_bar.configure(bg=t["status_bg"])
        for child in self._status_bar.winfo_children():
            try: child.configure(bg=t["status_bg"], fg=t["status_fg"])
            except tk.TclError: pass
        self.theme_btn.config(text="☀" if self.theme_name == "dark" else "🌙")
        self._apply_menu_theme(t)
        self._apply_ttk_theme(t)
        # Colours only. The tags' fonts are the registered Font objects set up
        # in build_ui, and re-stating them here as tuples would freeze the
        # console at whatever size it was when the theme last changed.
        palette = CONSOLE_COLORS[self.theme_name]
        for tag, color in palette.items():
            self.console.tag_configure(tag, foreground=color)
        self.console.tag_configure("default", foreground=t["console_fg"])
        self._apply_theme_recursive(self.root, t)
        # Tagged labels come out of the recursive pass with the right colour for
        # the new theme. The panels still get a nudge: their status lines carry a
        # colour that depends on what the scheduler says, not just on the theme.
        for panel in ("_slideshow_panel", "_reminder_panel",
                      "_playlist_panel"):
            p = getattr(self, panel, None)
            if p is not None and hasattr(p, "retheme"):
                p.retheme(self.theme_name)

    def _apply_menu_theme(self, t):
        """
        Colour the menu bar and its drop-downs.

        Left alone, the menu bar is a bright white strip across the top of a
        dark window -- it does not inherit the theme the way ordinary widgets
        do. Windows draws the bar itself, so how much of this it honours is up
        to the OS; the drop-downs follow reliably.
        """
        for menu in getattr(self, "_menus", []):
            try:
                menu.configure(bg=t["bg"], fg=t["fg"],
                               activebackground="#3a6ea5",
                               activeforeground="#ffffff",
                               borderwidth=0, relief=tk.FLAT)
            except tk.TclError:
                pass

    def _apply_ttk_theme(self, t):
        """
        Colour the ttk widgets — the notebook tabs above all.

        ttk ignores tk colour options entirely, so an untouched Notebook keeps
        its native light styling and the tab strip glows white above a dark
        app. The native Windows themes ("vista", "xpnative") also refuse to
        honour a tab background at all, so this switches to "clam", which does.
        That is a visible change to Combobox and Progressbar too — they become
        flat rather than native — but it is the price of tabs that match the
        theme, and it keeps both themes internally consistent.
        """
        style = ttk.Style()
        try:
            if style.theme_use() != "clam":
                style.theme_use("clam")
        except tk.TclError:
            return
        dim = CONSOLE_COLORS[self.theme_name]["dim"]
        sel_bg, sel_fg = "#3a6ea5", "#ffffff"

        style.configure("TNotebook", background=t["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 6),
                        background=t["btn_bg"], foreground=t["fg"],
                        bordercolor=t["bg"], lightcolor=t["btn_bg"],
                        darkcolor=t["btn_bg"])
        style.map("TNotebook.Tab",
                  background=[("selected", t["bg"]), ("active", t["entry_bg"])],
                  foreground=[("selected", t["fg"])],
                  lightcolor=[("selected", t["bg"])],
                  expand=[("selected", (0, 0, 0, 0))])

        # A readonly Combobox draws its text as *selected* text, so the colours
        # that matter are selectbackground/selectforeground, not foreground.
        # clam's defaults there are pale, which is how the interval and style
        # pickers ended up white-on-light-grey and unreadable.
        style.configure("TCombobox", padding=3,
                        fieldbackground=t["entry_bg"], background=t["btn_bg"],
                        foreground=t["entry_fg"], arrowcolor=t["fg"],
                        bordercolor=t["btn_bg"], lightcolor=t["btn_bg"],
                        darkcolor=t["btn_bg"],
                        selectbackground=t["entry_bg"],
                        selectforeground=t["entry_fg"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", t["entry_bg"]),
                                   ("disabled", t["bg"])],
                  foreground=[("readonly", t["entry_fg"]), ("disabled", dim)],
                  background=[("readonly", t["btn_bg"]), ("active", t["btn_bg"])],
                  selectbackground=[("readonly", t["entry_bg"])],
                  selectforeground=[("readonly", t["entry_fg"])],
                  arrowcolor=[("disabled", dim)])

        # The drop-down list is a plain Tk listbox in a toplevel of its own —
        # ttk styling does not reach it, only the option database does.
        for opt, val in (("*TCombobox*Listbox.background", t["entry_bg"]),
                         ("*TCombobox*Listbox.foreground", t["entry_fg"]),
                         ("*TCombobox*Listbox.selectBackground", sel_bg),
                         ("*TCombobox*Listbox.selectForeground", sel_fg)):
            self.root.option_add(opt, val)

        style.configure("TEntry", fieldbackground=t["entry_bg"],
                        foreground=t["entry_fg"], insertcolor=t["entry_fg"],
                        bordercolor=t["btn_bg"], lightcolor=t["btn_bg"],
                        darkcolor=t["btn_bg"])
        style.configure("TProgressbar", background=sel_bg,
                        troughcolor=t["entry_bg"], bordercolor=t["btn_bg"],
                        lightcolor=sel_bg, darkcolor=sel_bg)
        style.configure("TSeparator", background=t["btn_bg"])
        style.configure("TSizegrip", background=t["bg"])
        style.configure("TScrollbar", background=t["btn_bg"],
                        troughcolor=t["bg"], bordercolor=t["bg"],
                        arrowcolor=t["fg"], lightcolor=t["btn_bg"],
                        darkcolor=t["btn_bg"])

    def _apply_theme_recursive(self, widget, t):
        w = widget
        while w is not None:
            if w is self.console: return
            try: w = w.master
            except Exception: break
        try:
            wtype = widget.winfo_class()
            if wtype == "Frame":
                widget.configure(bg=t["bg"])
            elif wtype == "Labelframe":
                # fg matters: a LabelFrame draws its own title, and left alone
                # that title keeps the system default — near-black text on the
                # dark theme, which is what made every pane heading unreadable.
                widget.configure(bg=t["bg"], fg=t["fg"])
            elif wtype == "Label":
                # Hint text, status lines and the like keep their palette role
                # rather than being flattened to the plain foreground — and the
                # role is re-resolved, so dim reads correctly in both themes.
                widget.configure(bg=t["bg"],
                                 fg=role_fg(widget, self.theme_name, t["fg"]))
            elif wtype == "Entry":
                if self._valid.get(widget, True):
                    widget.configure(bg=t["entry_bg"], fg=t["entry_fg"],
                                     insertbackground=t["entry_fg"])
            elif wtype == "Button":
                if widget.cget("bg") not in {v["bg"] for v in BTN_COLORS.values()}:
                    widget.configure(bg=t["btn_bg"], fg=t["btn_fg"],
                                     activebackground=t["btn_bg"])
            # Radiobutton matters now that the Slideshow and Reminder panels
            # live in tabs: as dialogs they were rebuilt per open and never saw
            # a theme change, so one left unstyled kept its old background as a
            # bright block on the newly-switched panel.
            elif wtype in ("Checkbutton", "Radiobutton"):
                widget.configure(bg=t["bg"], fg=t["fg"],
                                 selectcolor=t["entry_bg"],
                                 activebackground=t["bg"])
            # Listbox was missing, so History and Saved Locations stayed white
            # blocks in the dark theme.
            elif wtype == "Menubutton":
                widget.configure(bg=t["bg"], fg=t["fg"],
                                 activebackground=t["btn_bg"],
                                 activeforeground=t["fg"])
            # The scrolling left column rides on a Canvas, which otherwise
            # keeps SystemButtonFace and shows as a light strip behind the
            # column on the dark theme. Scrollbars are all ttk now -- a plain
            # tk one cannot be themed on Windows, which draws it itself.
            elif wtype == "Canvas":
                widget.configure(bg=t["bg"])
            elif wtype == "Listbox":
                widget.configure(bg=t["entry_bg"], fg=t["entry_fg"],
                                 selectbackground="#3a6ea5",
                                 selectforeground="#ffffff",
                                 highlightbackground=t["bg"])
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._apply_theme_recursive(child, t)

    def _toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.cfg.set("theme", self.theme_name)
        self._apply_theme()

    def _change_font(self, delta):
        """
        Zoom the whole window, not just the console.

        Nothing is reconfigured here beyond the one number: every font in the
        UI is a registered named font, so Tk re-renders each widget itself the
        moment scaling.apply rewrites the sizes.
        """
        self.font_size = scaling.apply(self.font_size + delta)
        self.cfg.set("font_size", self.font_size)
        self._place_sizegrip()

    def _reset_font(self):
        """Back to 100%, where every font matches its designed size."""
        self.font_size = scaling.apply(scaling.BASE_SIZE)
        self.cfg.set("font_size", self.font_size)
        self._place_sizegrip()

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        # A preview rotates the wallpaper on this app's own timer, so closing
        # the window is the only thing that can end one — and it is what puts
        # the wallpaper back if that was asked for.
        panel = getattr(self, "_slideshow_panel", None)
        if panel is not None:
            try:
                panel.stop_preview()
            except tk.TclError:
                pass
        self.cfg.set("window_geometry", self.root.geometry())
        self.root.destroy()
