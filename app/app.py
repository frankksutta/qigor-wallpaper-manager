"""
app.py  —  QiGor Wallpaper Manager
Main App class. Wires all modules together.
UI construction is in ui.py. Logic modules: wallpaper, preview, dnd, reminder.
"""
from __future__ import annotations
import os
import re
import queue
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from .constants import (APP_NAME, APP_VERSION, STORE_DIR, THEMES,
                        BTN_COLORS, CONSOLE_COLORS, WIN_IMAGE_SOURCES)
from .config import Config
from .tooltip import Tooltip
from .dialogs import AboutDialog, ErrorDialog, _InputDialog, _RenameDialog
from .reminder import _ReminderDialog
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
        self.root.title(f"{APP_NAME}  v{APP_VERSION}")
        self.cfg        = Config()
        self.root.geometry(self.cfg.get("window_geometry"))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.minsize(800, 600)

        self.theme_name    = self.cfg.get("theme")
        self.font_size     = self.cfg.get("font_size")
        self.is_running    = False
        self._cancel_event = threading.Event()
        self._valid: dict  = {}

        self._pending_path  = tk.StringVar(value="")
        self._style_var     = tk.StringVar(value=self.cfg.get("wallpaper_style"))
        self._copy_var      = tk.BooleanVar(value=self.cfg.get("copy_to_store"))
        self._preview_img   = None
        self._preview_raw   = None
        self._dnd_available = False

        self._pending_path.trace_add("write", self._on_path_changed)

        STORE_DIR.mkdir(parents=True, exist_ok=True)

        self._build_ui()
        self._apply_theme()
        self._bind_shortcuts()
        self._start_clock()
        self._seed_default_favorites()
        self._refresh_history_list()
        self._refresh_favorites_list()
        self._show_last_changed()
        self.root.after(0, self._refresh_spotlight_ui)

        if "--remind" in sys.argv:
            self.root.after(800, self._show_reminder_notification)

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
                local_path = wp.download_image(src, self._log_threadsafe)
            else:
                local_path = Path(src)
                if not local_path.exists():
                    raise FileNotFoundError(f"File not found: {local_path}")

            if self._cancel_event.is_set(): raise InterruptedError()

            already_stored = Path(str(local_path)).resolve().parent.resolve() \
                             == STORE_DIR.resolve()
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

    def _browse_image(self):
        path = self._open_image_picker(
            title="Select wallpaper image",
            initial_dir=self.cfg.get("last_source_dir") or str(Path.home()))
        if path:
            self.cfg.set("last_source_dir", str(Path(path).parent))
            self._pending_path.set(path)
            self._drop_label.config(text=f"📎  {Path(path).name}")
            self._load_preview()

    def _open_image_picker(self, title="Select image", initial_dir=None):
        try:
            return self._com_file_picker(title, initial_dir)
        except Exception:
            return filedialog.askopenfilename(
                title=title,
                filetypes=[
                    ("Image files", "*.jpg *.jpeg *.png *.bmp *.gif *.webp *.tiff *.avif *.heic"),
                    ("All files",   "*.*"),
                ],
                initialdir=initial_dir or str(Path.home()),
            )

    def _com_file_picker(self, title, initial_dir=None):
        import ctypes
        CLSID_FileOpenDialog = "{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}"
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        try:
            import comtypes
            import comtypes.client
            from comtypes.shell import IFileOpenDialog, FOS_FORCEFILESYSTEM, FOS_FILEMUSTEXIST
            dialog = comtypes.client.CreateObject(
                CLSID_FileOpenDialog,
                interface=comtypes.shell.IFileOpenDialog)
            dialog.SetTitle(title)
            opts = dialog.GetOptions()
            dialog.SetOptions(opts | FOS_FORCEFILESYSTEM | FOS_FILEMUSTEXIST)
            filters = [
                ("Image files (jpg, png, bmp, gif, webp, tiff)",
                 "*.jpg;*.jpeg;*.png;*.bmp;*.gif;*.webp;*.tiff;*.tif;*.avif;*.heic"),
                ("All files", "*.*"),
            ]
            dialog.SetFileTypes(filters)
            dialog.SetFileTypeIndex(1)
            if initial_dir and Path(initial_dir).exists():
                from comtypes.shell import SHCreateItemFromParsingName, IShellItem
                folder_item = SHCreateItemFromParsingName(
                    str(initial_dir), None, IShellItem)
                dialog.SetFolder(folder_item)
            hr = dialog.Show(int(self.root.winfo_id()))
            if hr != 0:
                return None
            result = dialog.GetResult()
            return result.GetDisplayName(0x80058000)
        except Exception:
            raise
        finally:
            ole32.CoUninitialize()

    def _open_store_folder(self):
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(STORE_DIR))

    def _show_current_wallpaper(self):
        path = wp.get_current_wallpaper_path()
        if not path:
            self._log("No wallpaper is currently set.", "dim")
            return
        self._log(f"Current wallpaper: {path}", "cyan")
        self._pending_path.set(path)
        self._drop_label.config(text=f"🖥  {Path(path).name}")
        self._load_preview()

    # ── DnD ───────────────────────────────────────────────────────────────────

    def _post_build_log(self):
        for msg, tag in getattr(self, "_dnd_msgs", []):
            self._log(msg, tag)

    def _place_sizegrip(self):
        sg = ttk.Sizegrip(self.root)
        sg.place(relx=1.0, rely=1.0, anchor="se")
        sg.lift()

    def _on_drop_enter(self, event):
        t = THEMES.get(self.theme_name, THEMES["dark"])
        self._drop_label.config(bg=CONSOLE_COLORS[self.theme_name]["cyan"],
                                fg="#000000")

    def _on_drop_leave(self, event):
        t = THEMES.get(self.theme_name, THEMES["dark"])
        self._drop_label.config(bg=t["bg"], fg=t["fg"])

    def _on_drop(self, event):
        t = THEMES.get(self.theme_name, THEMES["dark"])
        self._drop_label.config(bg=t["bg"], fg=t["fg"])
        raw = event.data.strip()
        self._log(f"Drop received: {raw[:120]}", "dim")
        resolved, warning = dnd_mod.resolve_drop_data(raw)
        if warning:
            self._log(f"⚠  {warning}", "yellow")
            self._drop_label.config(
                text="⚠  Got a page URL, not an image URL.\n"
                     "Right-click the image → Copy image address\n"
                     "then paste it in the URL box below.")
            return
        if resolved:
            self._pending_path.set(resolved)
            name = Path(resolved).name if not resolved.startswith("http") \
                   else resolved.split("?")[0].split("/")[-1] or resolved[:50]
            self._drop_label.config(text=f"📎  {name}")
            self._log(f"Resolved: {resolved}", "cyan")
            self._load_preview()
        else:
            self._log(f"⚠  Could not resolve dropped data: {raw[:120]}", "yellow")
            self._drop_label.config(
                text="⚠  Could not read dropped item.\n"
                     "Try: right-click image → Copy image address\n"
                     "then paste in the URL box below.")

    def _on_paste(self, event=None):
        try:
            text = self.root.clipboard_get().strip()
            if text:
                self._pending_path.set(text)
                self._drop_label.config(text=f"📎  {text[:60]}")
                self._load_preview()
        except Exception:
            pass

    def _on_path_changed(self, *_):
        if hasattr(self, "_path_after"):
            self.root.after_cancel(self._path_after)
        self._path_after = self.root.after(700, self._auto_preview_from_entry)

    def _auto_preview_from_entry(self):
        src = self._pending_path.get().strip()
        if src and len(src) > 5:
            name = src.split("/")[-1].split("\\")[-1] or src[:40]
            self._drop_label.config(text=f"📎  {name[:60]}")
            self._load_preview()

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
                                  self.theme_name, self.font_size,
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
        if not PIL_AVAILABLE:
            self._preview_label.config(
                text="Pillow not installed.\npip install pillow", image="")
            return
        src = wp.normalize_src(self._pending_path.get().strip())
        if not src:
            return
        self._preview_label.config(text="Loading…", image="")
        threading.Thread(target=self._fetch_preview, args=(src,), daemon=True).start()

    def _fetch_preview(self, src):
        try:
            img = pv.fetch_preview_image(src)
            self._preview_raw = img
            self.root.after(0, self._reflow_preview)
        except Exception as exc:
            self._preview_raw = None
            self.root.after(0, lambda: self._preview_info_var.set(""))
            self.root.after(0, lambda: self._preview_label.config(
                image="", text=f"Preview failed:\n{exc}"))

    def _reflow_preview(self, target_label=None):
        img = getattr(self, "_preview_raw", None)
        if img is None:
            return
        lbl = target_label or self._preview_label
        pw = lbl.winfo_width()
        ph = lbl.winfo_height()
        if pw < 10 or ph < 10:
            self.root.after(100, lambda: self._reflow_preview(target_label))
            return
        sw, sh = pv.get_physical_screen_size(self.root)
        img_w, img_h = img.size
        style = self._style_var.get()
        screen_ratio = sw / sh
        if pw / ph > screen_ratio:
            canvas_h = ph - 4
            canvas_w = int(canvas_h * screen_ratio)
        else:
            canvas_w = pw - 4
            canvas_h = int(canvas_w / screen_ratio)
        canvas_w = max(canvas_w, 4)
        canvas_h = max(canvas_h, 4)
        canvas = pv.composite_preview(img, style, canvas_w, canvas_h, sw, sh)
        photo = ImageTk.PhotoImage(canvas)
        self._preview_img = photo
        lbl.config(image=photo, text="")
        img_mp = (img_w * img_h) / 1_000_000
        scr_mp = (sw * sh) / 1_000_000
        quality = pv.build_quality_label(img_w, img_h, sw, sh, style)
        info = (f"image: {img_w}×{img_h} ({img_mp:.1f}MP)  •  "
                f"screen: {sw}×{sh} ({scr_mp:.1f}MP)  •  "
                f"{style}  •  {quality}")
        self._preview_info_var.set(info)

    def _on_preview_resize(self, event):
        if getattr(self, "_preview_raw", None) is not None:
            if hasattr(self, "_resize_after"):
                self.root.after_cancel(self._resize_after)
            self._resize_after = self.root.after(80, self._reflow_preview)

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
                              self.theme_name, self.font_size)
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
        menu = tk.Menu(self.root, tearoff=0)
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
                               self.theme_name, self.font_size)
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
        src = wp.normalize_src(self._pending_path.get().strip())
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
                self._pending_path.set(src)
                self._drop_label.config(text=f"📎  {local_path.name}")
            except Exception as e:
                self._log(f"✖  Download failed: {e}", "red")
                return

        path = Path(src)
        if not path.exists():
            self._log(f"⚠  File not found: {path}", "yellow")
            return

        # ── If file is not in store, copy it there silently ───────────────────
        # PersonalizationCSP requires a stable path that won't move/delete
        already_stored = path.resolve().parent.resolve() == STORE_DIR.resolve()
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
        )
        if spotlight_on:
            msg += ("\n⚠  Windows Spotlight is currently ON.\n"
                    "   It will be automatically turned OFF.\n")
        msg += f"\nImage: {path.name}"
        if not messagebox.askokcancel("Set Lock Screen — Permission Required",
                                      msg, parent=self.root):
            return
        if spotlight_on:
            wp.disable_spotlight(self._log)
            self._refresh_spotlight_ui()
        self._log("─" * 52, "dim")
        self._log("Launching lock screen helper (UAC prompt will appear)…", "cyan")
        threading.Thread(target=self._do_set_lock_screen,
                         args=(path,), daemon=True).start()

    def _do_set_lock_screen(self, img_path):
        try:
            helper = wp.write_lockscreen_helper(img_path, mode="set")
            self._log_threadsafe(f"  Helper script: {helper.name}", "dim")
            if not wp.launch_helper_elevated(helper, self._log_threadsafe):
                return
            time.sleep(2)
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
            self.root.after(0, self._refresh_spotlight_ui)
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
            helper = wp.write_lockscreen_helper(mode="release")
            if not wp.launch_helper_elevated(helper, self._log_threadsafe):
                return
            time.sleep(2)
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

    def _refresh_spotlight_ui(self):
        try:
            is_on, detail = wp.check_spotlight_status()
            csp    = wp.csp_is_set()
            green  = CONSOLE_COLORS[self.theme_name]["green"]
            yellow = CONSOLE_COLORS[self.theme_name]["yellow"]
            dim    = CONSOLE_COLORS[self.theme_name]["dim"]

            # Spotlight line — show detail so user can see why it's on/off
            if is_on:
                self._spotlight_var.set("⚠  Lock screen Spotlight: ON")
                self._spotlight_lbl.config(fg=yellow)
            else:
                # If CSP is set by this app, Spotlight is effectively suppressed
                if csp:
                    self._spotlight_var.set("✔  Lock screen: custom image active")
                else:
                    self._spotlight_var.set("✔  Lock screen Spotlight: OFF")
                self._spotlight_lbl.config(fg=green)

            # CSP status line
            if csp:
                self._spotlight_status_lbl.config(
                    text="Custom image active (managed policy)", fg=dim)
            else:
                self._spotlight_status_lbl.config(
                    text="No policy — Windows has full control", fg=dim)
            if csp:
                c = BTN_COLORS["danger"]
                self._ls_pers_btn.config(
                    text="🔓 Release & Personalize",
                    bg=c["bg"], fg=c["fg"], activebackground=c["active"])
                Tooltip(self._ls_pers_btn,
                        "A custom lock screen image is active.\n"
                        "Click to remove the policy (UAC prompt)\n"
                        "then open Settings → Lock screen.")
            else:
                c = BTN_COLORS["primary"]
                self._ls_pers_btn.config(
                    text="⚙  Personalize Lock Screen",
                    bg=c["bg"], fg=c["fg"], activebackground=c["active"])
                Tooltip(self._ls_pers_btn,
                        "Open Settings → Personalization → Lock screen.\n"
                        "No managed policy is active.")
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
            helper = wp.write_lockscreen_helper(mode="release")
            if not wp.launch_helper_elevated(helper, self._log_threadsafe):
                return
            time.sleep(2)
            self._log_threadsafe("✔  Policy removed — opening Settings.", "green")
            self.root.after(0, self._open_lock_screen_settings)
            self.root.after(0, self._refresh_spotlight_ui)
        except Exception as e:
            self._log_threadsafe(f"✖  Error: {e}", "red")

    def _open_lock_screen_settings(self):
        for uri in ["ms-settings:lockscreen", "ms-settings:personalization"]:
            try:
                os.startfile(uri)
                self._log("Opened Settings → Personalization → Lock screen.", "dim")
                self.root.after(4000, self._refresh_spotlight_ui)
                return
            except Exception:
                continue

    def _show_current_lock_screen(self):
        path_str, source = wp.find_current_lock_screen_image()
        if not path_str:
            self._log("⚠  No lock screen image found.", "yellow")
            self._log("   Windows may be using a solid colour, or access is restricted.", "dim")
            return
        self._log(f"Current lock screen: {Path(path_str).name}", "cyan")
        self._log(f"  Source: {source}", "dim")
        spotlight_on, _ = wp.check_spotlight_status()
        if spotlight_on:
            self._log("  ⚠  Spotlight is ON — this image may rotate daily.", "yellow")
        if not PIL_AVAILABLE:
            return
        try:
            img = Image.open(path_str).convert("RGB")
            self._preview_raw = img
            self.root.after(0, self._reflow_preview)
            self._preview_info_var.set(
                f"Lock screen  •  {img.width}×{img.height}  •  {source}")
        except Exception as e:
            self._log(f"⚠  Could not open image for preview: {e}", "yellow")
            self._log(f"   Path: {path_str}", "dim")

    # ── Windows Sources menu ──────────────────────────────────────────────────

    def _show_win_sources_menu(self):
        menu = tk.Menu(self.root, tearoff=0)
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

    def _show_reminder_dialog(self):
        dialog = _ReminderDialog(self.root, self.cfg, self.theme_name, self.font_size,
                                 app_path=str(Path(sys.argv[0]).resolve()))
        self.root.wait_window(dialog)
        if dialog.result == "set":
            self.cfg.set("reminder_set", True)
            self._remind_btn.config(text="⏰ Reminder ✔")
            self._log("Wallpaper reminder scheduled.", "green")
        elif dialog.result == "removed":
            self.cfg.set("reminder_set", False)
            self._remind_btn.config(text="⏰ Set Reminder")
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
                launch=f'pythonw "{str(Path(sys.argv[0]).resolve())}"')
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
        AboutDialog(self.root, self.theme_name, self.font_size)

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
        palette = CONSOLE_COLORS[self.theme_name]
        for tag, color in palette.items():
            weight = "bold" if tag == "bold" else "normal"
            self.console.tag_configure(tag, foreground=color,
                font=("Consolas", self.font_size, weight))
        self.console.tag_configure("default", foreground=t["console_fg"],
            font=("Consolas", self.font_size))
        self._apply_theme_recursive(self.root, t)

    def _apply_theme_recursive(self, widget, t):
        w = widget
        while w is not None:
            if w is self.console: return
            try: w = w.master
            except Exception: break
        try:
            wtype = widget.winfo_class()
            if wtype in ("Frame", "Labelframe"):
                widget.configure(bg=t["bg"])
            elif wtype == "Label":
                widget.configure(bg=t["bg"], fg=t["fg"])
            elif wtype == "Entry":
                if self._valid.get(widget, True):
                    widget.configure(bg=t["entry_bg"], fg=t["entry_fg"],
                                     insertbackground=t["entry_fg"])
            elif wtype == "Button":
                if widget.cget("bg") not in {v["bg"] for v in BTN_COLORS.values()}:
                    widget.configure(bg=t["btn_bg"], fg=t["btn_fg"],
                                     activebackground=t["btn_bg"])
            elif wtype == "Checkbutton":
                widget.configure(bg=t["bg"], fg=t["fg"],
                                 selectcolor=t["entry_bg"],
                                 activebackground=t["bg"])
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._apply_theme_recursive(child, t)

    def _toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.cfg.set("theme", self.theme_name)
        self._apply_theme()

    def _change_font(self, delta):
        self.font_size = max(7, min(20, self.font_size + delta))
        self.console.config(font=("Consolas", self.font_size))
        self.cfg.set("font_size", self.font_size)
        palette = CONSOLE_COLORS[self.theme_name]
        for tag in list(palette.keys()) + ["default"]:
            weight = "bold" if tag == "bold" else "normal"
            self.console.tag_configure(
                tag, font=("Consolas", self.font_size, weight))

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        self.cfg.set("window_geometry", self.root.geometry())
        self.root.destroy()
