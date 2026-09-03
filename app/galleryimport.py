"""
galleryimport.py  —  QiGor Wallpaper Manager
Choosing what to take from a gallery, before anything is downloaded.

Import used to fetch the page whole: every image on it, including the ones
already in the store — which, on a gallery imported once before, is all of
them. The skip was real, but it happened at the far end of a download.

So the list arrives here already narrowed to what the store has not got,
ticked ready to fetch, with the ones you have behind a tick-box rather than
thrown away, and a thumbnail of whatever is highlighted — a filename is not a
picture, and picking wallpaper by filename is guessing.

The dialog downloads nothing into the store. It hands back the URLs it was
told to keep and the folder to keep them in; app.py does the fetching, on the
same worker and the same Cancel button as before.
"""
from __future__ import annotations

import threading

import tkinter as tk
from tkinter import ttk

from .constants import THEMES, BTN_COLORS, CONSOLE_COLORS, mark_role
from . import scaling
from . import gallery
from .tooltip import Tooltip


class ImportDialog(tk.Toplevel):
    """
    Pick images from a gallery. result = (urls, folder_name) or None.

    A Listbox rather than a column of Checkbuttons: an archive.org item runs
    to hundreds of pictures, and hundreds of real widgets is a window that
    takes a visible moment to open and scrolls in steps. The tick is a glyph
    in the line and a set of indices behind it — which also lets a whole
    Shift-selected block be ticked in one press.
    """

    THUMB_DELAY = 300     # ms: arrow-keying past a row should not fetch it

    def __init__(self, parent, theme_name, url, items, folder_prefill=""):
        super().__init__(parent)
        self.title("Import Gallery")
        self.result = None

        self._items   = items
        self._theme   = theme_name
        # Ticked by index into _items, so hiding and showing rows cannot lose
        # a tick. What you have is unticked: taking it again is the exception.
        self._checked = {i for i, it in enumerate(items) if not it["have"]}
        self._have    = sum(1 for it in items if it["have"])
        self._rows    = []       # _items indices, in the order shown

        self._img     = None     # Tk drops an image nothing holds a name for
        self._cache   = {}       # url -> PIL image; a second look is free
        self._current = None     # the item on show, for a resize to redraw
        self._gen     = 0        # supersedes a preview still in flight
        self._pending = None     # the debounce timer
        self._resized = None     # the resize timer

        t = THEMES.get(theme_name, THEMES["dark"])
        self.configure(bg=t["bg"])
        self.transient(parent)
        self.geometry("900x660")
        self.minsize(700, 480)
        self.grab_set()

        fn  = scaling.font("Segoe UI", 10)
        fnb = scaling.font("Segoe UI", 10, "bold")
        fns = scaling.font("Segoe UI", 9)
        self._mono = scaling.font("Consolas", 9)
        dim = CONSOLE_COLORS[theme_name]["dim"]

        ttk.Sizegrip(self).place(relx=1.0, rely=1.0, anchor="se")

        # ── What was found ───────────────────────────────────────────────────
        head = tk.Frame(self, bg=t["bg"])
        head.pack(fill=tk.X, padx=14, pady=(12, 0))
        tk.Label(head, text="Found {} image{} at this gallery".format(
                     len(items), "" if len(items) == 1 else "s"),
                 font=fnb, bg=t["bg"], fg=t["fg"]).pack(anchor=tk.W)
        mark_role(tk.Label(head, text=url, font=fns, bg=t["bg"], fg=dim,
                           anchor=tk.W, justify=tk.LEFT,
                           wraplength=scaling.scaled(820)),
                  "dim").pack(fill=tk.X, pady=(2, 0))
        mark_role(tk.Label(
            head, font=fns, bg=t["bg"], fg=dim, anchor=tk.W, justify=tk.LEFT,
            text=("{} of them {} already in your store, and left out of the "
                  "list below.".format(
                      self._have, "is" if self._have == 1 else "are")
                  if self._have else
                  "None of them are in your store yet.")),
            "dim").pack(fill=tk.X, pady=(2, 8))

        # ── Where they go ────────────────────────────────────────────────────
        frow = tk.Frame(self, bg=t["bg"])
        frow.pack(fill=tk.X, padx=14, pady=(0, 8))
        tk.Label(frow, text="Folder in the image store:", font=fnb,
                 bg=t["bg"], fg=t["fg"]).pack(side=tk.LEFT, padx=(0, 6))
        self._folder = tk.StringVar(value=folder_prefill)
        entry = tk.Entry(frow, textvariable=self._folder, font=self._mono,
                         bg=t["entry_bg"], fg=t["entry_fg"], width=32)
        entry.pack(side=tk.LEFT)
        Tooltip(entry, "The subfolder to save into, named after the gallery.\n"
                       "Clear it to put the images straight into the store.")
        mark_role(tk.Label(frow, text="  (clear it to save straight into the "
                                      "store)",
                           font=fns, bg=t["bg"], fg=dim),
                  "dim").pack(side=tk.LEFT)

        # ── The list, and the picture beside it ──────────────────────────────
        # Every widget from here down is coloured on the spot. The tabs and
        # panels inside the main window are painted by the app's recursive
        # theme pass; a Toplevel built after that pass has run is not, and an
        # unpainted LabelFrame is a light-grey block on the dark theme.
        pane = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED,
                              sashwidth=6, bg="#555555")
        pane.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))

        list_frame = tk.LabelFrame(pane, text="  Take these  ",
                                   bg=t["bg"], fg=t["fg"])
        pane.add(list_frame, stretch="always", minsize=300)

        inner = tk.Frame(list_frame, bg=t["bg"])
        inner.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 2))
        bar = tk.Scrollbar(inner)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        self._list = tk.Listbox(inner, height=10, font=self._mono,
                                yscrollcommand=bar.set,
                                selectmode=tk.EXTENDED, exportselection=False,
                                activestyle="none",
                                bg=t["entry_bg"], fg=t["entry_fg"],
                                selectbackground="#3a6ea5",
                                selectforeground="#ffffff",
                                highlightbackground=t["bg"])
        self._list.pack(fill=tk.BOTH, expand=True)
        bar.config(command=self._list.yview)
        self._list.bind("<<ListboxSelect>>", self._on_select)
        self._list.bind("<Button-1>", self._on_click)
        self._list.bind("<Double-Button-1>", lambda _e: self._toggle())
        # Both keys are handled here and stopped here: a Listbox's own <space>
        # would move the selection instead of ticking, and <Return> would go
        # on to the window's binding and run Import a second time.
        self._list.bind("<space>", self._on_space)
        self._list.bind("<Return>", self._on_return)
        Tooltip(self._list,
                "What Import will download.\n"
                "• Click the ☑ box to tick or untick a line\n"
                "• Click a name to see the picture\n"
                "• Space, or double-click, ticks everything selected\n"
                "• Ctrl-click or Shift-click to take several at once\n"
                "· in store marks an image you already have")

        brow = tk.Frame(list_frame, bg=t["bg"])
        brow.pack(fill=tk.X, padx=4, pady=(0, 4))
        for text, colour, cmd, tip in (
                ("☑ All",  "primary", lambda: self._tick_shown(True),
                 "Tick every line shown."),
                ("☐ None", "primary", lambda: self._tick_shown(False),
                 "Untick every line shown."),
                ("⇄ Invert", "primary", self._invert,
                 "Tick what is unticked, and the other way round.")):
            c = BTN_COLORS[colour]
            b = tk.Button(brow, text=text, font=fns,
                          bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                          command=cmd)
            b.pack(side=tk.LEFT, padx=(0, 4))
            Tooltip(b, tip)

        self._show_have = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(
            brow, variable=self._show_have, command=self._rebuild,
            text="Show the {} already in my store".format(self._have),
            font=fns, bg=t["bg"], fg=t["fg"], selectcolor=t["entry_bg"],
            activebackground=t["bg"],
            state=tk.NORMAL if self._have else tk.DISABLED)
        chk.pack(side=tk.RIGHT)
        Tooltip(chk,
                "List the images the store already holds, dimmed and\n"
                "unticked. Tick one to fetch it again — into a different\n"
                "folder it lands beside the copy you have; into the same\n"
                "one the download skips it.")

        prev_frame = tk.LabelFrame(pane, text="  Preview  ",
                                   bg=t["bg"], fg=t["fg"])
        pane.add(prev_frame, stretch="always", minsize=260)
        self._thumb = tk.Label(prev_frame, relief=tk.SUNKEN, font=fns,
                               bg=t["bg"], fg=t["fg"],
                               text="(click a line to see the picture)")
        self._thumb.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 2))
        # The window and the sash both move; the picture is scaled to the
        # label, so it has to be redrawn when the label changes size.
        self._thumb.bind("<Configure>", self._on_thumb_resize)
        self._info = tk.StringVar(value="")
        mark_role(tk.Label(prev_frame, textvariable=self._info, font=fns,
                           anchor=tk.CENTER, justify=tk.CENTER,
                           bg=t["bg"], fg=dim,
                           wraplength=scaling.scaled(340)),
                  "dim").pack(fill=tk.X, padx=6, pady=(0, 6))

        # ── Count, and the way out ───────────────────────────────────────────
        self._status = tk.StringVar(value="")
        mark_role(tk.Label(self, textvariable=self._status, font=fns,
                           anchor=tk.W, bg=t["bg"], fg=dim),
                  "dim").pack(fill=tk.X, padx=16, pady=(0, 4))

        btn_row = tk.Frame(self, bg=t["bg"])
        btn_row.pack(fill=tk.X, padx=12, pady=(0, 14))
        c = BTN_COLORS["success"]
        self._ok_btn = tk.Button(btn_row, text="⬇ Import", height=2, font=fnb,
                                 bg=c["bg"], fg=c["fg"],
                                 activebackground=c["active"],
                                 command=self._ok)
        self._ok_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Button(btn_row, text="Cancel", height=2, font=fn,
                  bg=t["btn_bg"], fg=t["btn_fg"],
                  command=self._cancel).pack(side=tk.LEFT, fill=tk.X,
                                             expand=True)

        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Return>", lambda _e: self._ok())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._rebuild()
        self._list.focus_set()

    # ── Rows ─────────────────────────────────────────────────────────────────

    def _line(self, i: int) -> str:
        it = self._items[i]
        return "{}  {:>8}  {}{}".format(
            "☑" if i in self._checked else "☐",
            gallery.size_label(it["size"]), it["name"],
            "   · in store" if it["have"] else "")

    def _rebuild(self):
        """Re-list from scratch: which rows are shown has changed."""
        shown = self._show_have.get()
        self._rows = [i for i, it in enumerate(self._items)
                      if shown or not it["have"]]
        dim = CONSOLE_COLORS[self._theme]["dim"]
        self._list.delete(0, tk.END)
        for row, i in enumerate(self._rows):
            self._list.insert(tk.END, self._line(i))
            if self._items[i]["have"]:
                self._list.itemconfig(row, foreground=dim)
        self._update_status()

    def _repaint(self, rows):
        """
        Redraw just these rows, keeping the scroll where the eye left it.

        A Listbox line cannot be edited in place, and re-listing everything to
        change one tick jumps a long list back to the top.
        """
        dim = CONSOLE_COLORS[self._theme]["dim"]
        for row in rows:
            i = self._rows[row]
            self._list.delete(row)
            self._list.insert(row, self._line(i))
            if self._items[i]["have"]:
                self._list.itemconfig(row, foreground=dim)
            self._list.selection_set(row)
        self._update_status()

    def _selected(self) -> list:
        return [r for r in self._list.curselection() if r < len(self._rows)]

    def _toggle(self, rows=None):
        """Tick or untick whole rows — the selection, or the ones named."""
        rows = self._selected() if rows is None else rows
        for row in rows:
            i = self._rows[row]
            if i in self._checked:
                self._checked.discard(i)
            else:
                self._checked.add(i)
        self._repaint(rows)

    def _tick_shown(self, on: bool):
        """All / None, over what is on screen — never over hidden rows."""
        for i in self._rows:
            if on:
                self._checked.add(i)
            else:
                self._checked.discard(i)
        self._keep_view(self._rebuild)

    def _invert(self):
        for i in self._rows:
            if i in self._checked:
                self._checked.discard(i)
            else:
                self._checked.add(i)
        self._keep_view(self._rebuild)

    def _keep_view(self, redraw):
        """Run `redraw`, then put the selection and the scroll back."""
        sel, top = self._selected(), self._list.yview()[0]
        redraw()
        for row in sel:
            self._list.selection_set(row)
        self._list.yview_moveto(top)

    def _update_status(self):
        ticked = [self._items[i] for i in self._checked]
        known = sum(it["size"] for it in ticked)
        self._status.set(
            "{} of {} ticked{}{}".format(
                len(ticked), len(self._items),
                "  •  {} to download".format(gallery.size_label(known))
                if known else "",
                "  •  {} already in your store".format(self._have)
                if self._have else ""))
        self._ok_btn.config(
            text="⬇ Import {}".format(len(ticked)) if ticked else "⬇ Import",
            state=tk.NORMAL if ticked else tk.DISABLED)

    # ── Clicking ─────────────────────────────────────────────────────────────

    def _box_width(self) -> int:
        """How far into the line the tick box reaches, in pixels."""
        return self._mono.measure("☑ ")

    def _on_click(self, event):
        """
        A click on the box is a tick; a click on the name is a look.

        Tk's own binding runs after this one and moves the selection to the
        row, which is why the tick is deferred: it has to be the row the click
        landed on that ends up selected and repainted.
        """
        if event.x > self._box_width():
            return
        row = self._list.nearest(event.y)
        if 0 <= row < len(self._rows):
            self.after_idle(lambda r=row: self._toggle([r]))

    def _on_space(self, _event=None):
        self._toggle()
        return "break"

    def _on_return(self, _event=None):
        self._ok()
        return "break"

    def _on_select(self, _event=None):
        if self._pending is not None:
            try:
                self.after_cancel(self._pending)
            except tk.TclError:
                pass
        self._pending = self.after(self.THUMB_DELAY, self._preview_selected)

    # ── Preview ──────────────────────────────────────────────────────────────

    def _preview_selected(self):
        rows = self._selected()
        if not rows:
            return
        row = self._list.index(tk.ACTIVE)
        if row not in rows:
            row = rows[0]
        it = self._items[self._rows[row]]
        self._gen += 1
        self._current = it
        cached = self._cache.get(it["url"])
        if cached is not None:
            self._paint(it, cached, final=True)
            return
        small = self._cache.get(it["thumb"]) if it["thumb"] else None
        if small is not None:
            self._paint(it, small, final=False)
        else:
            self._thumb.config(image="", text="Loading…")
            self._info.set(self._caption(it, None, final=False))
        threading.Thread(target=self._load, args=(it, self._gen),
                         daemon=True).start()

    def _load(self, it, gen):
        """
        Thumbnail first if the gallery keeps one, then the picture itself.

        The thumbnail is there in a moment and says what the image is; the
        full one is what says whether it is big enough to be wallpaper, so
        both are worth having. If the highlight has moved on by the time the
        thumbnail is in, the expensive half is not started at all.
        """
        try:
            from . import preview as pv
        except ImportError:      # no Pillow
            self._hand_back(gen, it, None, "Pillow not installed", False)
            return

        if it["thumb"] and it["thumb"] not in self._cache:
            try:
                img = pv.fetch_preview_image(it["thumb"])
            except Exception:
                pass             # no thumbnail is not a failure worth showing
            else:
                self._cache[it["thumb"]] = img
                self._hand_back(gen, it, img, "", False)

        if gen != self._gen:
            return
        try:
            img = pv.fetch_preview_image(it["url"])
        except Exception as exc:
            self._hand_back(gen, it, None, str(exc), True)
            return
        self._cache[it["url"]] = img
        self._hand_back(gen, it, img, "", True)

    def _hand_back(self, gen, it, img, err, final):
        def _apply():
            if gen != self._gen:        # a later click won the race
                return
            if img is None:
                self._img = None
                self._thumb.config(image="",
                                   text="Preview failed:\n{}".format(err))
                self._info.set(self._caption(it, None, final=True))
                return
            self._paint(it, img, final)
        try:
            self.after(0, _apply)
        except (tk.TclError, RuntimeError):
            pass                        # the dialog closed under the thread

    def _paint(self, it, img, final):
        try:
            from PIL import ImageTk
        except ImportError:
            self._thumb.config(image="",
                               text="Pillow not installed — no thumbnails.\n"
                                    "pip install pillow")
            return
        w = max(self._thumb.winfo_width() - 12, 80)
        h = max(self._thumb.winfo_height() - 12, 60)
        copy = img.copy()
        copy.thumbnail((w, h))
        self._img = ImageTk.PhotoImage(copy)
        self._thumb.config(image=self._img, text="")
        self._info.set(self._caption(it, img if final else None, final))

    def _on_thumb_resize(self, _event=None):
        if self._current is None:
            return
        if self._resized is not None:
            try:
                self.after_cancel(self._resized)
            except tk.TclError:
                pass
        self._resized = self.after(120, self._reflow)

    def _reflow(self):
        """Redraw the picture at the label's new size — from what is cached,
        never from the network: a drag of the sash is not a reason to fetch."""
        it = self._current
        if it is None:
            return
        full = self._cache.get(it["url"])
        img = full if full is not None else (
            self._cache.get(it["thumb"]) if it["thumb"] else None)
        if img is not None:
            self._paint(it, img, final=full is not None)

    def _caption(self, it, img, final) -> str:
        """
        Name, size, and — once the picture itself is in — its dimensions.

        The thumbnail's own size is never shown as the image's: 412x232 on a
        line that is deciding whether something is wallpaper would be a lie.
        """
        bits = [it["name"]]
        if img is not None:
            bits.append("{}×{}".format(*img.size))
        elif not final:
            bits.append("thumbnail — measuring the full image…")
        if it["size"]:
            bits.append(gallery.size_label(it["size"]))
        if it["have"]:
            bits.append("in your store as {}".format(it["have"]))
        return "  •  ".join(bits)

    # ── Leaving ──────────────────────────────────────────────────────────────

    def _ok(self):
        urls = [self._items[i]["url"]
                for i in range(len(self._items)) if i in self._checked]
        if not urls:
            return
        self.result = (urls, gallery.safe_folder(self._folder.get()))
        self._gen += 1               # nothing in flight may touch the widgets
        self.destroy()

    def _cancel(self):
        self._gen += 1
        self.destroy()
