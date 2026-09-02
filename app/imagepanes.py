"""
imagepanes.py  —  QiGor Wallpaper Manager
The image-picking layout shared by the Wallpaper and Lock Screen tabs.

Both tabs do the same job: preview an image, choose one — by dropping it,
pasting a URL, browsing, or picking from the local store — and then act on it.
Only the acting differs. So the columns and the choosing live here once, and
each tab passes a PaneSpec describing what is different about it.

A PaneSet is one tab's own widgets plus that shared behaviour, which is what
lets the two tabs hold independent selections: the Lock Screen tab used to
have no selector of its own and could only apply whatever the Wallpaper tab
had chosen.
"""
from __future__ import annotations

import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog

from .constants import (THEMES, BTN_COLORS, CONSOLE_COLORS, STORE_DIR,
                        mark_role)
from . import scaling
from . import wallpaper as wp
from . import preview as pv
from . import dnd as dnd_mod
from .tooltip import Tooltip

try:
    from PIL import ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


DROP_HINT = ("🖼  Drag a file from Explorer\n"
             "or drag an image from a browser\n"
             "or paste a URL / image address below")

DROP_TOOLTIP = ("• Drag an image file from Windows Explorer\n"
                "• Drag an image directly from a browser page\n"
                "• Right-click an image → Copy image address, paste below\n"
                "• Or use Browse… to pick a file")


class PaneSpec:
    """
    What one tab wants that the other does not.

    Everything here has a default that suits the Wallpaper tab, so the Lock
    Screen tab only has to say how it differs.
    """

    def __init__(self, key, *, pending_var=None,
                 preview_title="  Preview  ",
                 preview_placeholder="(no image selected)\n\n"
                                     "Drop or paste an image to preview",
                 style_pane=None, style_getter=None,
                 preview_buttons=(), action_rows=(), footer=None,
                 show_history=False, on_apply=None,
                 browse_title="Select image",
                 left_minsize=320, right_minsize=260):
        self.key = key
        self.pending_var = pending_var
        self.preview_title = preview_title
        self.preview_placeholder = preview_placeholder
        # style_pane(parent, panes) builds whatever sits under the preview;
        # style_getter() names the display mode the preview composites with.
        self.style_pane = style_pane
        self.style_getter = style_getter
        # preview_buttons sit inside the preview frame; action_rows below it.
        self.preview_buttons = preview_buttons
        self.action_rows = action_rows
        self.footer = footer
        self.show_history = show_history
        self.on_apply = on_apply
        self.browse_title = browse_title
        self.left_minsize = left_minsize
        self.right_minsize = right_minsize


def _scrolling_column(pane, minsize):
    """
    Add a column to `pane` whose contents scroll if they must.

    pack stops handing out space once it runs short, and it drops the widgets
    at the foot of a column silently — nothing on screen says they exist. That
    needs no resizing, only A+: at the window's own 800x600 minimum one press
    was enough to lose Set Wallpaper. The scrollbar appears only when the
    column really does not fit.

    Returns (canvas, scrollbar, body); pack children into body.
    """
    outer = tk.Frame(pane)
    pane.add(outer, stretch="always", minsize=minsize)

    canvas = tk.Canvas(outer, highlightthickness=0, bd=0)
    bar = tk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    body = tk.Frame(canvas)
    win = canvas.create_window((0, 0), window=body, anchor="nw")

    def _fit(_event=None):
        """
        Keep the body the width of the canvas, and at least its height.

        Matching the canvas height when there is room lets the expanding pane
        fill the column as it always did; going taller when there is not is
        what makes the rest reachable rather than merely absent.
        """
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        need = body.winfo_reqheight()
        canvas.itemconfigure(win, width=cw, height=max(ch, need))
        canvas.configure(scrollregion=(0, 0, cw, max(ch, need)))
        # A scrollbar with nothing to scroll is just clutter.
        if need > ch:
            if not bar.winfo_ismapped():
                bar.pack(side=tk.RIGHT, fill=tk.Y)
        elif bar.winfo_ismapped():
            bar.pack_forget()
            canvas.yview_moveto(0)

    canvas.bind("<Configure>", _fit)
    body.bind("<Configure>", _fit)

    def _wheel(event):
        if bar.winfo_ismapped():
            canvas.yview_scroll(-1 * (event.delta // 120), "units")

    # Bound on enter/leave rather than with a bare bind_all, which would steal
    # the wheel from the console and the listboxes.
    canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _wheel))
    canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
    return canvas, bar, body


class PaneSet:
    """One tab's image-picking widgets, and the behaviour they share."""

    def __init__(self, app, spec: PaneSpec):
        self.app = app
        self.spec = spec
        self.key = spec.key
        self.pending = (spec.pending_var if spec.pending_var is not None
                        else tk.StringVar(value=""))
        self.store_files: list = []
        self.preview_raw = None
        self.preview_img = None
        self._path_after = None
        self._resize_after = None
        # filled in by build()
        self.drop_label = None
        self.url_entry = None
        self.preview_label = None
        self.preview_info_var = None
        self.store_listbox = None
        self.hist_listbox = None
        self.left_canvas = self.left_scroll = None
        self.right_canvas = self.right_scroll = None

    # ── Selection ────────────────────────────────────────────────────────────

    def style(self) -> str:
        """The display mode the preview should composite with."""
        if self.spec.style_getter is not None:
            return self.spec.style_getter()
        return "Fill"

    def select(self, value, label=None, icon="📎"):
        """Adopt an image: remember it, name it on the drop label, preview it."""
        self.pending.set(value)
        if self.drop_label is not None:
            name = label if label is not None else Path(value).name
            self.drop_label.config(text="{}  {}".format(icon, name))
        self.load_preview()

    def browse(self):
        path = self.app._open_image_picker(
            title=self.spec.browse_title,
            initial_dir=self.app.cfg.get("last_source_dir") or str(Path.home()))
        if path:
            self.app.cfg.set("last_source_dir", str(Path(path).parent))
            self.select(path)

    def on_drop_enter(self, _event=None):
        self.drop_label.config(bg=CONSOLE_COLORS[self.app.theme_name]["cyan"],
                               fg="#000000")

    def on_drop_leave(self, _event=None):
        t = THEMES.get(self.app.theme_name, THEMES["dark"])
        self.drop_label.config(bg=t["bg"], fg=t["fg"])

    def on_drop(self, event):
        self.on_drop_leave()
        raw = event.data.strip()
        self.app._log(f"Drop received: {raw[:120]}", "dim")
        resolved, warning = dnd_mod.resolve_drop_data(raw)
        if warning:
            self.app._log(f"⚠  {warning}", "yellow")
            self.drop_label.config(
                text="⚠  Got a page URL, not an image URL.\n"
                     "Right-click the image → Copy image address\n"
                     "then paste it in the URL box below.")
            return
        if resolved:
            name = (Path(resolved).name if not resolved.startswith("http")
                    else resolved.split("?")[0].split("/")[-1] or resolved[:50])
            self.app._log(f"Resolved: {resolved}", "cyan")
            self.select(resolved, label=name)
        else:
            self.app._log(f"⚠  Could not resolve dropped data: {raw[:120]}",
                          "yellow")
            self.drop_label.config(
                text="⚠  Could not read dropped item.\n"
                     "Try: right-click image → Copy image address\n"
                     "then paste in the URL box below.")

    def on_paste(self, _event=None):
        try:
            text = self.app.root.clipboard_get().strip()
            if text:
                self.select(text, label=text[:60])
        except Exception:
            pass

    def on_path_changed(self, *_):
        """Debounce typing in the URL field before previewing it."""
        if self._path_after is not None:
            try:
                self.app.root.after_cancel(self._path_after)
            except Exception:
                pass
        self._path_after = self.app.root.after(700, self.auto_preview_from_entry)

    def auto_preview_from_entry(self):
        src = self.pending.get().strip()
        if src and len(src) > 5:
            name = src.split("/")[-1].split("\\")[-1] or src[:40]
            self.drop_label.config(text=f"📎  {name[:60]}")
            self.load_preview()

    # ── Preview ──────────────────────────────────────────────────────────────

    def load_preview(self):
        if self.preview_label is None:
            return
        if not PIL_AVAILABLE:
            self.preview_label.config(
                text="Pillow not installed.\npip install pillow", image="")
            return
        src = wp.normalize_src(self.pending.get().strip())
        if not src:
            return
        self.preview_label.config(text="Loading…", image="")
        threading.Thread(target=self._fetch_preview, args=(src,),
                         daemon=True).start()

    def _fetch_preview(self, src):
        try:
            self.preview_raw = pv.fetch_preview_image(src)
            self.app.root.after(0, self.reflow_preview)
        except Exception as exc:
            self.preview_raw = None
            self.app.root.after(0, lambda: self.preview_info_var.set(""))
            self.app.root.after(0, lambda: self.preview_label.config(
                image="", text=f"Preview failed:\n{exc}"))

    def reflow_preview(self, _event=None):
        """Re-composite the preview at the label's current size."""
        img = self.preview_raw
        if img is None or self.preview_label is None:
            return
        lbl = self.preview_label
        pw, ph = lbl.winfo_width(), lbl.winfo_height()
        if pw < 10 or ph < 10:
            self.app.root.after(100, self.reflow_preview)
            return
        sw, sh = pv.get_physical_screen_size(self.app.root)
        img_w, img_h = img.size
        style = self.style()
        screen_ratio = sw / sh
        if pw / ph > screen_ratio:
            canvas_h = ph - 4
            canvas_w = int(canvas_h * screen_ratio)
        else:
            canvas_w = pw - 4
            canvas_h = int(canvas_w / screen_ratio)
        canvas_w, canvas_h = max(canvas_w, 4), max(canvas_h, 4)
        composite = pv.composite_preview(img, style, canvas_w, canvas_h, sw, sh)
        photo = ImageTk.PhotoImage(composite)
        self.preview_img = photo
        lbl.config(image=photo, text="")
        img_mp = (img_w * img_h) / 1_000_000
        scr_mp = (sw * sh) / 1_000_000
        quality = pv.build_quality_label(img_w, img_h, sw, sh, style)
        self.preview_info_var.set(
            f"image: {img_w}×{img_h} ({img_mp:.1f}MP)  •  "
            f"screen: {sw}×{sh} ({scr_mp:.1f}MP)  •  "
            f"{style}  •  {quality}")

    def on_preview_resize(self, _event=None):
        if self.preview_raw is None:
            return
        if self._resize_after is not None:
            try:
                self.app.root.after_cancel(self._resize_after)
            except Exception:
                pass
        self._resize_after = self.app.root.after(80, self.reflow_preview)

    # ── Image store ──────────────────────────────────────────────────────────

    def refresh_store(self):
        """
        Re-read the store folder, newest first.

        The paths are kept beside the list: the listbox holds bare filenames,
        which are what you want to read, and are not enough to open a file.
        """
        self.store_files = []
        try:
            STORE_DIR.mkdir(parents=True, exist_ok=True)
            files = [p for p in STORE_DIR.iterdir()
                     if p.is_file() and p.suffix.lower() in wp.IMAGE_EXTS]
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            self.store_files = files
        except OSError as exc:
            self.app._log(f"Could not read the image store: {exc}", "red")
        if self.store_listbox is None:
            return
        self.store_listbox.delete(0, tk.END)
        for path in self.store_files:
            self.store_listbox.insert(tk.END, path.name)
        if not self.store_files:
            # An empty box looks like a failure to load; say which it is.
            self.store_listbox.insert(tk.END, "(no images saved yet)")

    def on_store_select(self, _=None):
        sel = self.store_listbox.curselection()
        if not sel or not self.store_files:
            return
        idx = sel[0]
        if idx >= len(self.store_files):     # the placeholder line
            return
        self.select(str(self.store_files[idx]))

    def apply(self):
        """Whatever this tab's primary action is."""
        if self.spec.on_apply is not None:
            self.spec.on_apply()


# ── Construction ─────────────────────────────────────────────────────────────

def build(app, parent, spec: PaneSpec) -> PaneSet:
    """
    Build one tab's two columns and return its PaneSet.

    Left  — the preview, then whatever acts on it.
    Right — picking an image: the selector, the local store, and (on the
            Wallpaper tab) the history of what has been applied.
    """
    panes = PaneSet(app, spec)

    h_pane = tk.PanedWindow(parent, orient=tk.HORIZONTAL,
                            sashrelief=tk.RAISED, sashwidth=6, bg="#555555")
    h_pane.pack(fill=tk.BOTH, expand=True)
    panes.h_pane = h_pane

    panes.left_canvas, panes.left_scroll, left = _scrolling_column(
        h_pane, spec.left_minsize)
    panes.right_canvas, panes.right_scroll, right = _scrolling_column(
        h_pane, spec.right_minsize)

    _build_preview(app, left, panes)
    if spec.style_pane is not None:
        spec.style_pane(left, panes)
    _build_actions(app, left, panes)
    if spec.footer is not None:
        spec.footer(left, panes)

    _build_selector(app, right, panes)
    _build_store(app, right, panes)
    if spec.show_history:
        _build_history(app, right, panes)

    return panes


def _build_preview(app, left, panes):
    spec = panes.spec
    prev_frame = tk.LabelFrame(left, text=spec.preview_title)
    prev_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

    panes.preview_label = tk.Label(prev_frame, text=spec.preview_placeholder,
                                   font=scaling.font("Segoe UI", 9),
                                   relief=tk.SUNKEN)
    panes.preview_label.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 2))
    panes.preview_label.bind("<Configure>", panes.on_preview_resize)

    panes.preview_info_var = tk.StringVar(value="")
    mark_role(tk.Label(prev_frame, textvariable=panes.preview_info_var,
                       anchor=tk.CENTER, font=scaling.font("Segoe UI", 8)),
              "dim").pack(fill=tk.X, padx=6, pady=(0, 2))

    if spec.preview_buttons:
        row = tk.Frame(prev_frame)
        row.pack(pady=(0, 6))
        _buttons(app, row, spec.preview_buttons, fill=False)
    panes.preview_frame = prev_frame


def _buttons(app, row, specs, fill=True):
    """Build a row of buttons from plain dicts, so a tab only lists them."""
    for btn in specs:
        c = BTN_COLORS[btn.get("colour", "primary")]
        widget = tk.Button(
            row, text=btn["text"], height=btn.get("height", 2),
            bg=c["bg"], fg=c["fg"], activebackground=c["active"],
            font=scaling.font("Segoe UI", btn.get("size", 9),
                              *(("bold",) if btn.get("bold") else ())),
            state=btn.get("state", "normal"),
            command=btn["command"])
        last = btn is specs[-1]
        if fill:
            widget.pack(side=tk.LEFT, fill=tk.X, expand=True,
                        padx=(0, 0) if last else (0, 4))
        else:
            widget.pack(side=tk.LEFT, padx=(0, 0) if last else (0, 4))
        if btn.get("tooltip"):
            Tooltip(widget, btn["tooltip"])
        if btn.get("attr"):
            setattr(app, btn["attr"], widget)


def _build_actions(app, left, panes):
    """One frame per row of buttons, exactly as the spec lists them."""
    for row_spec in panes.spec.action_rows:
        row = tk.Frame(left)
        row.pack(fill=tk.X, pady=(0, 4))
        _buttons(app, row, row_spec)


def _build_selector(app, right, panes):
    frame = tk.LabelFrame(right, text="  Image Selector  ")
    frame.pack(fill=tk.X, pady=(0, 6))

    panes.drop_label = tk.Label(
        frame, text=DROP_HINT,
        # No cursor="hand2" and no <Button-1>: clicking here used to open a
        # file browser, which is a whole Explorer window for a stray click on
        # what is meant to be a drop target. Browse... is the way in.
        height=5, relief=tk.RIDGE, font=scaling.font("Segoe UI", 10))
    panes.drop_label.pack(fill=tk.X, padx=6, pady=(6, 4))
    Tooltip(panes.drop_label, DROP_TOOLTIP)

    ok = dnd_mod.setup_dnd(panes.drop_label,
                           on_drop=panes.on_drop,
                           on_enter=panes.on_drop_enter,
                           on_leave=panes.on_drop_leave,
                           msg_list=app._dnd_msgs)
    # Either tab wiring up is enough for the app to treat dropping as working.
    app._dnd_available = bool(getattr(app, "_dnd_available", False) or ok)

    url_row = tk.Frame(frame)
    url_row.pack(fill=tk.X, padx=6, pady=(0, 6))
    tk.Label(url_row, text="URL / Path:",
             font=scaling.font("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))

    panes.url_entry = tk.Entry(url_row, textvariable=panes.pending,
                               font=scaling.font("Consolas", 9))
    c = BTN_COLORS["primary"]
    browse_btn = tk.Button(url_row, text="Browse…",
                           bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                           font=scaling.font("Segoe UI", 9),
                           command=panes.browse)
    # Browse... first and anchored right: left-to-right, the label and entry
    # claimed the row's width and this fell off the end. It is the only way to
    # a file dialog now, so it cannot be the thing that gets squeezed out.
    browse_btn.pack(side=tk.RIGHT, padx=(4, 2))
    panes.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    Tooltip(browse_btn, "Pick an image file from disk.")
    panes.pending.trace_add("write", panes.on_path_changed)
    panes.selector_frame = frame


def _build_store(app, right, panes):
    frame = tk.LabelFrame(right, text="  Image store  ")
    frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

    hdr = tk.Frame(frame)
    hdr.pack(fill=tk.X, padx=4, pady=(4, 0))
    tk.Label(hdr, text="Saved images (click to select):",
             font=scaling.font("Segoe UI", 9)).pack(side=tk.LEFT)

    c = BTN_COLORS["primary"]
    refresh = tk.Button(hdr, text="⟳ Refresh",
                        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                        font=scaling.font("Segoe UI", 8),
                        command=panes.refresh_store)
    refresh.pack(side=tk.RIGHT, padx=4)
    Tooltip(refresh,
            "Re-read the store folder.\n"
            "The list also refreshes itself whenever this app saves an image.")

    list_frame = tk.Frame(frame)
    list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    bar = tk.Scrollbar(list_frame)
    bar.pack(side=tk.RIGHT, fill=tk.Y)
    # height=3 is a floor, not a size: it expands to fill whatever the column
    # has spare.
    panes.store_listbox = tk.Listbox(list_frame, height=3,
                                     font=scaling.font("Consolas", 9),
                                     yscrollcommand=bar.set,
                                     selectmode=tk.SINGLE)
    panes.store_listbox.pack(fill=tk.BOTH, expand=True)
    bar.config(command=panes.store_listbox.yview)
    panes.store_listbox.bind("<<ListboxSelect>>", panes.on_store_select)
    panes.store_listbox.bind("<Double-Button-1>", lambda _: panes.apply())
    Tooltip(panes.store_listbox,
            "Images saved in your local store.\n"
            "• Click to load one into the field above and preview it\n"
            "• Double-click to apply it\n"
            "Newest first.")
    panes.store_frame = frame


def _build_history(app, right, panes):
    frame = tk.LabelFrame(right, text="  History  ")
    frame.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

    hdr = tk.Frame(frame)
    hdr.pack(fill=tk.X, padx=4, pady=(4, 0))
    tk.Label(hdr, text="Recent wallpapers (click to re-apply):",
             font=scaling.font("Segoe UI", 9)).pack(side=tk.LEFT)

    c = BTN_COLORS["danger"]
    clear = tk.Button(hdr, text="Clear History",
                      bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                      font=scaling.font("Segoe UI", 8),
                      command=app._clear_history)
    clear.pack(side=tk.RIGHT, padx=4)
    Tooltip(clear, "Forget every entry in the history list.")

    list_frame = tk.Frame(frame)
    list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    bar = tk.Scrollbar(list_frame)
    bar.pack(side=tk.RIGHT, fill=tk.Y)
    panes.hist_listbox = tk.Listbox(list_frame, height=3,
                                    font=scaling.font("Consolas", 9),
                                    yscrollcommand=bar.set,
                                    selectmode=tk.SINGLE)
    panes.hist_listbox.pack(fill=tk.BOTH, expand=True)
    bar.config(command=panes.hist_listbox.yview)
    panes.hist_listbox.bind("<<ListboxSelect>>", app._on_history_select)
    panes.hist_listbox.bind("<Double-Button-1>", lambda _: panes.apply())
    Tooltip(panes.hist_listbox,
            "Click to load into the URL/path field and preview.\n"
            "Double-click to apply immediately.")
    panes.hist_frame = frame
