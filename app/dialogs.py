"""
dialogs.py  —  QiGor Wallpaper Manager
AboutDialog, ErrorDialog, _InputDialog, _RenameDialog.
"""
import sys
import tkinter as tk
from tkinter import ttk, scrolledtext

from .constants import APP_NAME, APP_VERSION, THEMES, BTN_COLORS, CONSOLE_COLORS


class AboutDialog(tk.Toplevel):
    """About dialog with banner image and app description."""

    def __init__(self, parent, theme_name, font_size):
        super().__init__(parent)
        self.title(f"About {APP_NAME}")
        t = THEMES.get(theme_name, THEMES["dark"])
        self.configure(bg=t["bg"])
        self.resizable(True, True)
        self.minsize(480, 360)
        self.geometry("560x520")
        self.grab_set()
        fn  = ("Segoe UI", font_size)
        fnb = ("Segoe UI", font_size + 2, "bold")
        fns = ("Segoe UI", font_size - 1)

        ttk.Sizegrip(self).place(relx=1.0, rely=1.0, anchor="se")

        c = BTN_COLORS["primary"]
        tk.Button(self, text="Close", font=fn, width=12,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self.destroy).pack(side=tk.BOTTOM, pady=(4, 14))

        ttk.Separator(self).pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=0)

        body = tk.Frame(self, bg=t["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=(18, 8))

        # ── Banner image ──────────────────────────────────────
        self._about_photo = None
        try:
            from PIL import ImageTk
            from .images import load_bundled_image
            banner = load_bundled_image("qigor_wallpaper_manager_150k.jpg")
            if banner:
                bw, bh = banner.size
                scale = min(1.0, 512 / bw)
                banner = banner.resize((int(bw * scale), int(bh * scale)),
                                       __import__("PIL").Image.LANCZOS)
                self._about_photo = ImageTk.PhotoImage(banner)
                tk.Label(body, image=self._about_photo,
                         bg=t["bg"], relief=tk.FLAT).pack(anchor=tk.CENTER, pady=(0, 10))
        except Exception:
            pass

        tk.Label(body, text=APP_NAME, font=fnb,
                 bg=t["bg"], fg=t["fg"]).pack(anchor=tk.W)
        tk.Label(body, text=f"Version {APP_VERSION}  •  Python {sys.version.split()[0]}",
                 font=fns, bg=t["bg"],
                 fg=CONSOLE_COLORS[theme_name]["dim"]).pack(anchor=tk.W, pady=(2, 12))

        desc = (
            "Windows 11 makes changing your wallpaper surprisingly tedious — "
            "buried inside Settings → Personalization → Background, with no "
            "easy way to use an image you found online.\n\n"
            "This app fixes that. Drag an image file straight from Windows "
            "Explorer, or drag/paste an image address from any web browser, "
            "pick your display style (Fill, Fit, Stretch, Tile, Center, Span), "
            "and set it instantly — no Settings digging required.\n\n"
            "Your wallpaper history is saved so you can re-apply past images "
            "with one click. Save favourite folders and gallery websites for "
            "quick access. Images can be copied to a local store so your "
            "wallpaper never breaks if the original file moves or is deleted.\n\n"
            "── LOCK SCREEN ──────────────────────────────────────────\n\n"
            "The 'Set Lock Screen' button uses the Windows.System.UserProfile."
            "LockScreen PowerShell API (available since Windows 10 version 1607).\n\n"
            "Known limitations and compatibility issues:\n\n"
            "• SPOTLIGHT: If Windows Spotlight is enabled (Settings → "
            "Personalization → Lock screen → 'Windows Spotlight'), it will "
            "override any image you set. Turn it off and set to 'Picture' first.\n\n"
            "• ENTERPRISE / MANAGED PCs: Group Policy or MDM (Intune, "
            "SCCM etc.) can lock the lock screen image. You will see an "
            "Access Denied error. Contact your IT department.\n\n"
            "• WINDOWS EDITIONS: Works on Windows 10 Home, Pro, and "
            "Windows 11 Home/Pro with a local or Microsoft account. "
            "Azure AD / work accounts on Windows 11 Enterprise may be "
            "restricted by policy.\n\n"
            "• REGISTRY FALLBACK: If the PowerShell API fails, the app "
            "tries a registry method which copies the image to "
            "%AppData%\\Microsoft\\Windows\\Themes\\. "
            "This may not take effect until you lock and unlock (Win+L).\n\n"
            "• HIGH-DPI / 4K: Windows automatically scales the lock screen "
            "image to fit your display. A 4K image on a 1080p laptop will "
            "look fine (downscaled). A 720p image on a 4K monitor will "
            "appear soft or pixellated.\n\n"
            "── IMAGE SIZE AND QUALITY ───────────────────────────────\n\n"
            "The preview info bar shows image resolution vs screen resolution "
            "and a quality rating:\n"
            "  ✔ native or better  — image is at least as large as your screen\n"
            "  ≈ slight upscale    — image is 75–100%% of screen size (barely visible)\n"
            "  ⚠ upscaled 2×      — image is 50–75%% of screen (slightly soft)\n"
            "  ⚠⚠ heavily upscaled — image is under 50%% of screen (noticeably blurry)\n\n"
            "For best results on any display, use images at or above your "
            "screen's native resolution. Common targets: 1920×1080 (1080p), "
            "2560×1440 (1440p), 3840×2160 (4K). A 720p or 1080p image on a "
            "4K monitor will be upscaled 2–4× and may look soft."
        )
        txt = scrolledtext.ScrolledText(body, font=fn, wrap=tk.WORD,
                                        bg=t["entry_bg"], fg=t["fg"],
                                        relief=tk.FLAT, height=10)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert(tk.END, desc)
        txt.config(state=tk.DISABLED)

        self.bind("<Escape>", lambda _: self.destroy())
        self.bind("<Return>", lambda _: self.destroy())


class ErrorDialog(tk.Toplevel):
    """Scrollable, copyable error dialog. Use instead of messagebox for long traces."""

    def __init__(self, parent, title, detail, theme_name="dark", font_size=10):
        super().__init__(parent)
        self.title(title)
        t = THEMES.get(theme_name, THEMES["dark"])
        self.configure(bg=t["bg"])
        self.resizable(True, True)
        self.minsize(480, 300)
        self.geometry("640x380")
        self.grab_set()
        fn  = ("Consolas", font_size)
        fnb = ("Segoe UI", font_size, "bold")

        ttk.Sizegrip(self).place(relx=1.0, rely=1.0, anchor="se")

        btn_row = tk.Frame(self, bg=t["bg"])
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(4, 12))
        c = BTN_COLORS["primary"]
        tk.Button(btn_row, text="Copy to Clipboard", font=fnb,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=lambda: (self.clipboard_clear(),
                                   self.clipboard_append(detail))
                  ).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(btn_row, text="Close", font=fnb,
                  bg=t["btn_bg"], fg=t["btn_fg"],
                  command=self.destroy).pack(side=tk.LEFT)

        txt = scrolledtext.ScrolledText(self, font=fn, wrap=tk.WORD,
                                        bg=t["entry_bg"],
                                        fg=CONSOLE_COLORS[theme_name]["red"])
        txt.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 4))
        txt.insert(tk.END, detail)
        txt.config(state=tk.DISABLED)
        self.bind("<Escape>", lambda _: self.destroy())


class _InputDialog(tk.Toplevel):
    """Two-field dialog: label and URL/path. result = (label, url) or None."""

    def __init__(self, parent, title, prompt, theme_name="dark", font_size=10,
                 prefill_label="", prefill_url=""):
        super().__init__(parent)
        self.title(title)
        self.result = None
        t = THEMES.get(theme_name, THEMES["dark"])
        self.configure(bg=t["bg"])
        self.resizable(True, False)
        self.minsize(440, 0)
        self.grab_set()
        fn  = ("Segoe UI", font_size)
        fnb = ("Segoe UI", font_size, "bold")

        ttk.Sizegrip(self).place(relx=1.0, rely=1.0, anchor="se")

        btn_row = tk.Frame(self, bg=t["bg"])
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(4, 12))
        c = BTN_COLORS["success"]
        tk.Button(btn_row, text="Add", height=2, font=fnb,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._ok).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Button(btn_row, text="Cancel", height=2, font=fn,
                  bg=t["btn_bg"], fg=t["btn_fg"],
                  command=self.destroy).pack(side=tk.LEFT, fill=tk.X, expand=True)

        body = tk.Frame(self, bg=t["bg"])
        body.pack(fill=tk.BOTH, padx=16, pady=12)
        tk.Label(body, text=prompt, font=fn, bg=t["bg"], fg=t["fg"],
                 wraplength=400).pack(anchor=tk.W, pady=(0, 8))

        tk.Label(body, text="Label:", font=fnb, bg=t["bg"], fg=t["fg"]).pack(anchor=tk.W)
        self._lbl_var = tk.StringVar(value=prefill_label)
        tk.Entry(body, textvariable=self._lbl_var, font=("Consolas", font_size),
                 bg=t["entry_bg"], fg=t["entry_fg"], width=50).pack(fill=tk.X, pady=(2, 8))

        tk.Label(body, text="URL or folder path:", font=fnb,
                 bg=t["bg"], fg=t["fg"]).pack(anchor=tk.W)
        self._url_var = tk.StringVar(value=prefill_url)
        tk.Entry(body, textvariable=self._url_var, font=("Consolas", font_size),
                 bg=t["entry_bg"], fg=t["entry_fg"], width=50).pack(fill=tk.X, pady=(2, 0))

        self.bind("<Return>", lambda _: self._ok())
        self.bind("<Escape>", lambda _: self.destroy())

    def _ok(self):
        lbl = self._lbl_var.get().strip()
        url = self._url_var.get().strip()
        if lbl and url:
            self.result = (lbl, url)
            self.destroy()


class _RenameDialog(tk.Toplevel):
    """Edit label and URL/path for a favorite. result = (label, location) or None."""

    def __init__(self, parent, current_label, current_location,
                 theme_name="dark", font_size=10):
        super().__init__(parent)
        self.title("Edit Favorite")
        self.result = None
        t = THEMES.get(theme_name, THEMES["dark"])
        self.configure(bg=t["bg"])
        self.resizable(True, False)
        self.minsize(480, 0)
        self.grab_set()
        fn  = ("Segoe UI", font_size)
        fnb = ("Segoe UI", font_size, "bold")

        ttk.Sizegrip(self).place(relx=1.0, rely=1.0, anchor="se")

        btn_row = tk.Frame(self, bg=t["bg"])
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(4, 12))
        c = BTN_COLORS["success"]
        tk.Button(btn_row, text="Save", height=2, font=fnb,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._ok).pack(side=tk.LEFT, fill=tk.X,
                                         expand=True, padx=(0, 6))
        tk.Button(btn_row, text="Cancel", height=2, font=fn,
                  bg=t["btn_bg"], fg=t["btn_fg"],
                  command=self.destroy).pack(side=tk.LEFT, fill=tk.X, expand=True)

        body = tk.Frame(self, bg=t["bg"])
        body.pack(fill=tk.BOTH, padx=16, pady=12)

        tk.Label(body, text="Label:", font=fnb,
                 bg=t["bg"], fg=t["fg"]).pack(anchor=tk.W)
        self._lbl_var = tk.StringVar(value=current_label)
        lbl_entry = tk.Entry(body, textvariable=self._lbl_var,
                             font=("Consolas", font_size),
                             bg=t["entry_bg"], fg=t["entry_fg"], width=54)
        lbl_entry.pack(fill=tk.X, pady=(4, 12))
        lbl_entry.select_range(0, tk.END)
        lbl_entry.focus_set()

        tk.Label(body, text="URL or folder path:", font=fnb,
                 bg=t["bg"], fg=t["fg"]).pack(anchor=tk.W)
        self._loc_var = tk.StringVar(value=current_location)
        tk.Entry(body, textvariable=self._loc_var,
                 font=("Consolas", font_size),
                 bg=t["entry_bg"], fg=t["entry_fg"], width=54).pack(
                     fill=tk.X, pady=(4, 0))

        self.bind("<Return>", lambda _: self._ok())
        self.bind("<Escape>", lambda _: self.destroy())

    def _ok(self):
        lbl = self._lbl_var.get().strip()
        loc = self._loc_var.get().strip()
        if lbl and loc:
            self.result = (lbl, loc)
            self.destroy()
