"""
ui.py  —  QiGor Wallpaper Manager
All widget construction. Called as build_ui(app) from app.py.
No business logic here — only layout, bindings, and wiring to app methods.
"""
import tkinter as tk
from tkinter import ttk, scrolledtext

from .constants import (APP_NAME, APP_VERSION, THEMES, BTN_COLORS,
                        CONSOLE_COLORS, WALLPAPER_STYLES, STORE_DIR)
from .tooltip import Tooltip
from . import dnd as dnd_mod

try:
    from PIL import ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def build_ui(app):
    """Build the entire main window UI onto app (App instance)."""
    root = app.root
    t = THEMES.get(app.theme_name, THEMES["dark"])

    # ── Menu bar ──────────────────────────────────────────────────────────────
    menubar = tk.Menu(root)
    root.config(menu=menubar)
    file_menu = tk.Menu(menubar, tearoff=0)
    menubar.add_cascade(label="File", menu=file_menu)
    file_menu.add_command(label="Browse for Image…", command=app._browse_image)
    file_menu.add_command(label="Clear Log   Ctrl+L", command=app._clear_log)
    file_menu.add_separator()
    file_menu.add_command(label="Exit", command=app._on_close)
    help_menu = tk.Menu(menubar, tearoff=0)
    menubar.add_cascade(label="Help", menu=help_menu)
    help_menu.add_command(label="About   F1", command=app._show_about)

    root.after(0, app._place_sizegrip)

    # ── Status bar (BOTTOM first) ─────────────────────────────────────────────
    app._status_bar = tk.Frame(root, relief=tk.SUNKEN, bd=1)
    app._status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    app.status_var = tk.StringVar(value="Ready")
    tk.Label(app._status_bar, textvariable=app.status_var,
             anchor=tk.W, padx=6).pack(side=tk.LEFT, fill=tk.X, expand=True)
    app.clock_var = tk.StringVar(value="")
    tk.Label(app._status_bar, textvariable=app.clock_var,
             anchor=tk.E, font=("Consolas", 9),
             ).pack(side=tk.RIGHT, padx=(0, 20))

    # ── Progress bar ──────────────────────────────────────────────────────────
    app._progress = ttk.Progressbar(root, orient=tk.HORIZONTAL, mode="indeterminate")
    app._progress.pack(side=tk.BOTTOM, fill=tk.X)

    # ── Toolbar ───────────────────────────────────────────────────────────────
    toolbar = tk.Frame(root)
    toolbar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 4))

    app.theme_btn = tk.Button(toolbar, text="☀", width=3, command=app._toggle_theme)
    app.theme_btn.pack(side=tk.LEFT, padx=(0, 4))
    Tooltip(app.theme_btn, "Toggle dark / light theme.")

    for text, delta in [("A+", +1), ("A-", -1)]:
        btn = tk.Button(toolbar, text=text, width=3,
                        command=lambda d=delta: app._change_font(d))
        btn.pack(side=tk.LEFT, padx=2)
        Tooltip(btn, f"{'Increase' if delta > 0 else 'Decrease'} console font size.")

    c = BTN_COLORS["primary"]
    open_store_btn = tk.Button(toolbar, text="📁 Open Store Folder",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              command=app._open_store_folder)
    open_store_btn.pack(side=tk.LEFT, padx=(8, 2))
    Tooltip(open_store_btn,
            f"Open the wallpaper store folder in Windows Explorer:\n{STORE_DIR}\n\n"
            "Images are copied here when 'Copy to store' is checked.")

    c = BTN_COLORS["warning"]
    win_src_btn = tk.Button(toolbar, text="🪟 Windows Sources ▾",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              command=app._show_win_sources_menu)
    win_src_btn.pack(side=tk.LEFT, padx=(4, 2))
    app._win_src_btn = win_src_btn
    Tooltip(win_src_btn,
            "Open Windows system wallpaper directories:\n"
            "• Your wallpaper store (this app)\n"
            "• Windows cached wallpaper\n"
            "• Spotlight daily images\n"
            "• Built-in Windows wallpapers\n"
            "• Lock screen images")

    c = BTN_COLORS["success"]
    remind_lbl = "⏰ Reminder ✔" if app.cfg.get("reminder_set") else "⏰ Set Reminder"
    app._remind_btn = tk.Button(toolbar, text=remind_lbl,
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              command=app._show_reminder_dialog)
    app._remind_btn.pack(side=tk.LEFT, padx=(4, 2))
    Tooltip(app._remind_btn,
            "Schedule a gentle Windows notification to remind you\n"
            "to change your wallpaper — daily, weekly, or every N days.\n\n"
            "Uses Windows Task Scheduler (no background process).")

    c = BTN_COLORS["primary"]
    slideshow_lbl = getattr(app, "_slideshow_lbl_value", "🖼 Slideshow")
    app._slideshow_btn = tk.Button(toolbar, text=slideshow_lbl,
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              command=app._show_slideshow_dialog)
    app._slideshow_btn.pack(side=tk.LEFT, padx=(4, 2))
    Tooltip(app._slideshow_btn,
            "Auto-rotate wallpapers from your store folder.\n"
            "Uses Windows Task Scheduler — no background process.\n"
            "Images are shuffled and cycle through before repeating.")

    clr_btn = tk.Button(toolbar, text="Clear Log", command=app._clear_log)
    clr_btn.pack(side=tk.RIGHT)
    Tooltip(clr_btn, "Clear the log console.  Ctrl+L")

    about_btn = tk.Button(toolbar, text="About", command=app._show_about)
    about_btn.pack(side=tk.RIGHT, padx=(4, 0))
    Tooltip(about_btn, f"About {APP_NAME}  (F1)")

    # ── Main PanedWindow (vertical) ───────────────────────────────────────────
    app._main_pane = tk.PanedWindow(root, orient=tk.VERTICAL,
                                     sashrelief=tk.RAISED, sashwidth=6,
                                     bg="#555555")
    app._main_pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    # ── Horizontal PanedWindow (left | right) ─────────────────────────────────
    app._h_pane = tk.PanedWindow(app._main_pane, orient=tk.HORIZONTAL,
                                   sashrelief=tk.RAISED, sashwidth=6,
                                   bg="#555555")
    app._main_pane.add(app._h_pane, stretch="always", minsize=300)

    # ─────────────────────────  LEFT COLUMN  ──────────────────────────────────
    left = tk.Frame(app._h_pane)
    app._h_pane.add(left, stretch="always", minsize=320)

    # ── Drop zone ─────────────────────────────────────────────────────────────
    drop_frame = tk.LabelFrame(left,
        text="  Drop image here  —  or paste a web URL  —  or Browse  ")
    drop_frame.pack(fill=tk.X, pady=(0, 6))

    app._drop_label = tk.Label(drop_frame,
        text="🖼  Drag a file from Explorer\n"
             "or drag an image from a browser\n"
             "or paste a URL / image address below",
        height=6, relief=tk.RIDGE, cursor="hand2",
        font=("Segoe UI", 10))
    app._drop_label.pack(fill=tk.X, padx=6, pady=(6, 4))
    app._drop_label.bind("<Button-1>", lambda _: app._browse_image())
    Tooltip(app._drop_label,
            "• Drag an image file from Windows Explorer\n"
            "• Drag an image directly from a browser page\n"
            "• Right-click an image → Copy image address, paste below\n"
            "• Click to open a file browser")

    # ── Drop zone thumbnail (upper-left dead area) ────────────────────────────
    app._drop_thumb_photo = None
    if PIL_AVAILABLE:
        try:
            from .images import load_bundled_image
            thumb = load_bundled_image("qigor_wallpaper_manager_thumb.jpg")
            if thumb:
                app._drop_thumb_photo = ImageTk.PhotoImage(thumb)
                thumb_lbl = tk.Label(drop_frame, image=app._drop_thumb_photo,
                                     bd=0, relief=tk.FLAT, cursor="hand2")
                thumb_lbl.place(x=7, y=6)
                thumb_lbl.bind("<Button-1>", lambda _: app._browse_image())
                Tooltip(thumb_lbl, f"{APP_NAME}  —  click to browse")
        except Exception:
            pass

    # ── DnD registration ──────────────────────────────────────────────────────
    app._dnd_msgs = []
    app._dnd_available = dnd_mod.setup_dnd(
        app._drop_label,
        on_drop=app._on_drop,
        on_enter=app._on_drop_enter,
        on_leave=app._on_drop_leave,
        msg_list=app._dnd_msgs)
    if not app._dnd_available:
        root.bind("<Control-v>", app._on_paste)

    url_row = tk.Frame(drop_frame)
    url_row.pack(fill=tk.X, padx=6, pady=(0, 6))
    tk.Label(url_row, text="URL / Path:", font=("Segoe UI", 9)
             ).pack(side=tk.LEFT, padx=(0, 4))
    app._url_entry = tk.Entry(url_row, textvariable=app._pending_path,
                               font=("Consolas", app.font_size))
    app._url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    Tooltip(app._url_entry,
            "Paste a web URL, image address (right-click → Copy image address),\n"
            "or a local file path.  Press Enter or click Set Wallpaper.\n"
            "Supports http://, https://, file://, and plain paths.")
    app._url_entry.bind("<Return>", lambda _: app._start_task())

    c = BTN_COLORS["primary"]
    browse_btn = tk.Button(url_row, text="Browse…", font=("Segoe UI", 9),
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              command=app._browse_image)
    browse_btn.pack(side=tk.LEFT, padx=(0, 2))
    Tooltip(browse_btn, "Open a file browser to pick an image from disk.")

    # ── Style + options ───────────────────────────────────────────────────────
    opts_frame = tk.LabelFrame(left, text="  Display Style  ")
    opts_frame.pack(fill=tk.X, pady=(0, 6))

    style_row = tk.Frame(opts_frame)
    style_row.pack(fill=tk.X, padx=6, pady=4)
    _style_tips = {
        "Fill":    "Zoom to fill screen, crop edges if aspect differs.",
        "Fit":     "Fit whole image on screen, letterbox if needed.",
        "Stretch": "Stretch to fill — may distort aspect ratio.",
        "Tile":    "Repeat image in a grid pattern.",
        "Center":  "Show at original size, centered on desktop.",
        "Span":    "Stretch across all monitors (multi-monitor).",
    }
    for s in WALLPAPER_STYLES:
        rb = tk.Radiobutton(style_row, text=s, variable=app._style_var, value=s,
                            font=("Segoe UI", 9),
                            command=lambda: (
                                app.cfg.set("wallpaper_style", app._style_var.get()),
                                app._reflow_preview()
                            ))
        rb.pack(side=tk.LEFT, padx=6)
        Tooltip(rb, _style_tips.get(s, s))

    copy_row = tk.Frame(opts_frame)
    copy_row.pack(fill=tk.X, padx=6, pady=(0, 6))
    cb = tk.Checkbutton(copy_row,
        text="Copy image to local store (prevents broken wallpaper if original moves)",
        variable=app._copy_var,
        font=("Segoe UI", 9),
        command=lambda: app.cfg.set("copy_to_store", app._copy_var.get()))
    cb.pack(side=tk.LEFT)
    Tooltip(cb,
            "When checked: copies the image into the wallpaper store folder.\n"
            f"Store: {STORE_DIR}")

    # ── Action buttons ────────────────────────────────────────────────────────
    btn_row = tk.Frame(left)
    btn_row.pack(fill=tk.X, pady=(0, 2))

    c = BTN_COLORS["success"]
    app.apply_btn = tk.Button(btn_row, text="🖼  Set Wallpaper", height=2,
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        command=app._start_task)
    app.apply_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    Tooltip(app.apply_btn,
            "Apply the image as your desktop wallpaper.\n"
            "If a URL is entered, the image will be downloaded first.\nCtrl+R")

    c = BTN_COLORS["cancel"]
    app.cancel_btn = tk.Button(btn_row, text="✖  Cancel", height=2,
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        command=app._cancel_task, state=tk.DISABLED)
    app.cancel_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
    Tooltip(app.cancel_btn, "Cancel a download in progress.  Esc")

    pers_bg_row = tk.Frame(left)
    pers_bg_row.pack(fill=tk.X, pady=(0, 4))
    c = BTN_COLORS["primary"]
    pers_bg_btn = tk.Button(pers_bg_row, text="⚙  Personalize Background",
        font=("Segoe UI", 8),
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        command=lambda: __import__("os").startfile(
            "ms-settings:personalization-background"))
    pers_bg_btn.pack(side=tk.LEFT)
    Tooltip(pers_bg_btn,
            "Open Windows Settings → Personalization → Background.\n"
            "Set desktop background to Picture, Slideshow, or Spotlight.")

    # ── Lock screen ───────────────────────────────────────────────────────────
    lock_frame = tk.LabelFrame(left, text="  Lock Screen  ")
    lock_frame.pack(fill=tk.X, pady=(0, 6))

    lock_row = tk.Frame(lock_frame)
    lock_row.pack(fill=tk.X, padx=6, pady=(6, 4))

    c = BTN_COLORS["warning"]
    app.lock_btn = tk.Button(lock_row, text="🔒  Set Lock Screen", height=2,
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        command=app._set_lock_screen)
    app.lock_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    Tooltip(app.lock_btn,
            "Set the Windows lock screen image.\n\n"
            "A Windows permission (UAC) prompt will appear briefly.\n"
            "The app stays open — a small helper runs the change and exits.")

    cur_ls_btn = tk.Button(lock_row, text="🖥  Current", height=2,
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        command=app._show_current_lock_screen)
    cur_ls_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
    Tooltip(cur_ls_btn, "Preview the image currently set as your lock screen.")

    ls_pers_row = tk.Frame(lock_frame)
    ls_pers_row.pack(fill=tk.X, padx=6, pady=(0, 6))

    c = BTN_COLORS["primary"]
    app._ls_pers_btn = tk.Button(ls_pers_row, text="⚙  Personalize Lock Screen",
        font=("Segoe UI", 8),
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        command=app._ls_personalize_or_release)
    app._ls_pers_btn.pack(side=tk.LEFT)

    # ── Last changed banner ───────────────────────────────────────────────────
    app._last_changed_var = tk.StringVar(value="")
    lc_lbl = tk.Label(left, textvariable=app._last_changed_var,
                      font=("Segoe UI", 9, "italic"), anchor=tk.W)
    lc_lbl.pack(fill=tk.X, padx=2, pady=(0, 4))

    # ── History list ──────────────────────────────────────────────────────────
    hist_frame = tk.LabelFrame(left, text="  History  ")
    hist_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

    hist_hdr = tk.Frame(hist_frame)
    hist_hdr.pack(fill=tk.X, padx=4, pady=(4, 0))
    tk.Label(hist_hdr, text="Recent wallpapers (click to re-apply):",
             font=("Segoe UI", 9)).pack(side=tk.LEFT)
    c = BTN_COLORS["danger"]
    clrhist_btn = tk.Button(hist_hdr, text="Clear History", font=("Segoe UI", 8),
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              command=app._clear_history)
    clrhist_btn.pack(side=tk.RIGHT, padx=4)
    Tooltip(clrhist_btn, "Remove all entries from the history list.\nDoes not delete files from disk.")

    hist_list_frame = tk.Frame(hist_frame)
    hist_list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    scrollbar = tk.Scrollbar(hist_list_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    app._hist_listbox = tk.Listbox(hist_list_frame,
                                    font=("Consolas", app.font_size - 1),
                                    yscrollcommand=scrollbar.set,
                                    selectmode=tk.SINGLE)
    app._hist_listbox.pack(fill=tk.BOTH, expand=True)
    scrollbar.config(command=app._hist_listbox.yview)
    app._hist_listbox.bind("<<ListboxSelect>>", app._on_history_select)
    app._hist_listbox.bind("<Double-Button-1>", lambda _: app._start_task())
    Tooltip(app._hist_listbox,
            "Click to load into the URL/path field and preview.\n"
            "Double-click to apply immediately.")

    # ─────────────────────────  RIGHT COLUMN  ─────────────────────────────────
    right = tk.Frame(app._h_pane)
    app._h_pane.add(right, stretch="always", minsize=260)

    # ── Preview pane ──────────────────────────────────────────────────────────
    prev_frame = tk.LabelFrame(right, text="  Preview  ")
    prev_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

    app._preview_label = tk.Label(prev_frame,
        text="(no image selected)\n\nDrop or paste an image to preview",
        font=("Segoe UI", 9), relief=tk.SUNKEN)
    app._preview_label.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 2))
    app._preview_label.bind("<Configure>", app._on_preview_resize)

    app._preview_info_var = tk.StringVar(value="")
    tk.Label(prev_frame, textvariable=app._preview_info_var,
             font=("Segoe UI", 8), anchor=tk.CENTER,
             ).pack(fill=tk.X, padx=6, pady=(0, 2))

    btn_row_prev = tk.Frame(prev_frame)
    btn_row_prev.pack(pady=(0, 6))

    c = BTN_COLORS["primary"]
    prev_btn = tk.Button(btn_row_prev, text="🔍  Preview Selected",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              font=("Segoe UI", 9), command=app._load_preview)
    prev_btn.pack(side=tk.LEFT, padx=(0, 4))
    Tooltip(prev_btn,
            "Load and display a preview of the current URL / file.\n"
            "Preview updates automatically when you drop or paste an image.\n"
            "Requires Pillow:  pip install pillow")

    c = BTN_COLORS["warning"]
    cur_wp_btn = tk.Button(btn_row_prev, text="🖥  Current Wallpaper",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              font=("Segoe UI", 9), command=app._show_current_wallpaper)
    cur_wp_btn.pack(side=tk.LEFT)
    Tooltip(cur_wp_btn,
            "Preview the wallpaper currently set on your desktop.\n"
            "Reads the path directly from the Windows registry.")

    # ── Favorites ─────────────────────────────────────────────────────────────
    fav_frame = tk.LabelFrame(right, text="  Saved Locations & Galleries  ")
    fav_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

    fav_hdr = tk.Frame(fav_frame)
    fav_hdr.pack(fill=tk.X, padx=4, pady=(4, 0))
    tk.Label(fav_hdr, text="Quick-jump folders & gallery URLs:",
             font=("Segoe UI", 9)).pack(side=tk.LEFT)

    fav_btn_row = tk.Frame(fav_frame)
    fav_btn_row.pack(fill=tk.X, padx=4, pady=2)

    c = BTN_COLORS["primary"]
    add_fol_btn = tk.Button(fav_btn_row, text="+ Add Folder",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              font=("Segoe UI", 8), command=app._add_favorite_folder)
    add_fol_btn.pack(side=tk.LEFT, padx=(0, 4))
    Tooltip(add_fol_btn,
            "Add a folder to favorites.\n"
            "• Click to browse for a folder\n"
            "• Or drag a folder/file/URL onto this button\n"
            "Double-click a saved folder later to browse images inside it.")
    dnd_mod.setup_dnd_on(add_fol_btn, app._on_drop_on_add_btn, app._dnd_available)

    c = BTN_COLORS["warning"]
    add_url_btn = tk.Button(fav_btn_row, text="+ Add URL",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              font=("Segoe UI", 8), command=app._add_favorite_url)
    add_url_btn.pack(side=tk.LEFT, padx=(0, 4))
    Tooltip(add_url_btn,
            "Add a website URL to favorites.\n"
            "• Click to enter a label and URL\n"
            "• Or drag a URL onto this button")
    dnd_mod.setup_dnd_on(add_url_btn, app._on_drop_on_add_btn, app._dnd_available)

    c = BTN_COLORS["danger"]
    rem_btn = tk.Button(fav_btn_row, text="Remove",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              font=("Segoe UI", 8), command=app._remove_favorite)
    rem_btn.pack(side=tk.LEFT, padx=(0, 4))
    Tooltip(rem_btn, "Remove the selected favorite.\nOr right-click any item in the list.")

    c = BTN_COLORS["primary"]
    restore_btn = tk.Button(fav_btn_row, text="↺ Restore Defaults",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              font=("Segoe UI", 8), command=app._restore_default_favorites)
    restore_btn.pack(side=tk.LEFT)
    Tooltip(restore_btn,
            "Re-adds the default lucid24 gallery URLs that may have been deleted.\n"
            "Safe to click any time — only missing defaults are added back.")

    fav_list_frame = tk.Frame(fav_frame)
    fav_list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    fav_scroll = tk.Scrollbar(fav_list_frame)
    fav_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    app._fav_listbox = tk.Listbox(fav_list_frame,
                                   font=("Consolas", app.font_size - 1),
                                   yscrollcommand=fav_scroll.set,
                                   selectmode=tk.SINGLE)
    app._fav_listbox.pack(fill=tk.BOTH, expand=True)
    fav_scroll.config(command=app._fav_listbox.yview)
    app._fav_listbox.bind("<Double-Button-1>", app._open_favorite)
    app._fav_listbox.bind("<Button-3>",        app._on_fav_right_click)
    Tooltip(app._fav_listbox,
            "Saved folders and gallery pages.\n"
            "• Double-click a folder → browse images inside\n"
            "• Double-click a URL → open in browser\n"
            "• Right-click any item → Delete / Rename label")

    # ── Console ───────────────────────────────────────────────────────────────
    console_outer = tk.Frame(app._main_pane)
    app._main_pane.add(console_outer, stretch="never", minsize=60)

    console_hdr = tk.Frame(console_outer)
    console_hdr.pack(fill=tk.X)
    tk.Label(console_hdr, text="Log",
             font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
    app._autoscroll_var = tk.BooleanVar(value=app.cfg.get("autoscroll"))
    tk.Checkbutton(console_hdr, text="Auto-scroll",
                   variable=app._autoscroll_var,
                   command=app._on_autoscroll_toggle,
                   ).pack(side=tk.RIGHT)

    console_frame = tk.LabelFrame(console_outer, text="")
    console_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
    app.console = scrolledtext.ScrolledText(
        console_frame, font=("Consolas", app.font_size), wrap=tk.WORD, height=6)
    app.console.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

    for tag, color in CONSOLE_COLORS["dark"].items():
        weight = "bold" if tag == "bold" else "normal"
        app.console.tag_configure(
            tag, foreground=color,
            font=("Consolas", app.font_size, weight))
    app.console.tag_configure(
        "default", foreground="#d4d4d4",
        font=("Consolas", app.font_size))

    app._log("─" * 52, "dim")
    app._log(f"  {APP_NAME}  v{APP_VERSION}", "bold")
    if not PIL_AVAILABLE:
        app._log("  ⚠  Pillow not found — preview disabled.  pip install pillow", "yellow")
    app._log("─" * 52, "dim")
    root.after(0, app._post_build_log)
