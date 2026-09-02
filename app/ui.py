"""
ui.py  —  QiGor Wallpaper Manager
All widget construction. Called as build_ui(app) from app.py.
No business logic here — only layout, bindings, and wiring to app methods.
"""
import tkinter as tk
from tkinter import ttk, scrolledtext

from .constants import (APP_NAME, APP_VERSION, THEMES, BTN_COLORS,
                        CONSOLE_COLORS, WALLPAPER_STYLES, STORE_DIR,
                        mark_role)
from . import scaling
from .tooltip import Tooltip
from .slideshow import SlideshowPanel
from .reminder import ReminderPanel
from . import dnd as dnd_mod

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def _build_lock_tab(app, parent):
    """
    The Windows lock screen controls, in their own tab.

    They act on whatever image is selected on the Wallpaper tab, so that
    selection is echoed here — as two bare buttons in a column they gave no
    clue what they were about to apply.
    """
    dim = CONSOLE_COLORS[app.theme_name]["dim"]

    body = tk.Frame(parent)
    body.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

    tk.Label(body, text="Windows Lock Screen", anchor=tk.W,
             font=scaling.font("Segoe UI", 12, "bold")).pack(fill=tk.X)
    mark_role(tk.Label(body, anchor=tk.W, justify=tk.LEFT, wraplength=640, fg=dim,
             font=scaling.font("Segoe UI", 9),
             text="Sets the image Windows shows before you sign in. This is a "
                  "machine-wide policy, so Windows asks for permission (UAC) "
                  "each time it changes — the app stays open while a small "
                  "helper applies it and exits."
             ), "dim").pack(fill=tk.X, pady=(2, 12))

    sel = tk.LabelFrame(body, text="  Image to apply  ")
    sel.pack(fill=tk.X, pady=(0, 12))
    # Echoed through a second variable so an empty selection says so, rather
    # than leaving a framed blank that looks like the panel failed to load.
    app._lock_sel_var = tk.StringVar()

    def _echo_selection(*_):
        chosen = app._pending_path.get().strip()
        app._lock_sel_var.set(chosen or "(nothing selected yet)")

    app._pending_path.trace_add("write", _echo_selection)
    _echo_selection()

    tk.Label(sel, textvariable=app._lock_sel_var, anchor=tk.W, justify=tk.LEFT,
             wraplength=620, font=scaling.font("Consolas", 9)
             ).pack(fill=tk.X, padx=8, pady=6)
    mark_role(tk.Label(sel, anchor=tk.W, fg=dim, font=scaling.font("Segoe UI", 8),
             text="Chosen on the Wallpaper tab — drop a file, paste a URL, or Browse."
             ), "dim").pack(fill=tk.X, padx=8, pady=(0, 6))

    row = tk.Frame(body)
    row.pack(fill=tk.X)

    c = BTN_COLORS["warning"]
    app.lock_btn = tk.Button(row, text="🔒  Set Lock Screen", height=2,
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        font=scaling.font("Segoe UI", 10, "bold"),
        command=app._set_lock_screen)
    app.lock_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    Tooltip(app.lock_btn,
            "Set the Windows lock screen image.\n\n"
            "A Windows permission (UAC) prompt will appear briefly.\n"
            "The app stays open — a small helper runs the change and exits.")

    c = BTN_COLORS["primary"]
    app._ls_pers_btn = tk.Button(row, text="⚙ Lock", height=2,
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        font=scaling.font("Segoe UI", 10),
        command=app._ls_personalize_or_release)
    app._ls_pers_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    Tooltip(app._ls_pers_btn,
            "Open Settings → Personalization → Lock screen.\n"
            "If a custom image policy is active, releases it first (UAC prompt)\n"
            "then opens Settings so you can change the lock screen mode.")

    c = BTN_COLORS["success"]
    cur_btn = tk.Button(row, text="🔒  Show Current", height=2,
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        font=scaling.font("Segoe UI", 10),
        command=app._show_lock_preview)
    cur_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
    Tooltip(cur_btn,
            "Show the image Windows is using as the lock screen now,\n"
            "in the preview below.")

    prev = tk.LabelFrame(body, text="  Lock screen preview  ")
    prev.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
    app._lock_preview_label = tk.Label(
        prev, relief=tk.SUNKEN, font=scaling.font("Segoe UI", 9),
        text="Click “Show Current” to see the lock screen Windows is using,\n"
             "or set one above.")
    app._lock_preview_label.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 2))
    app._lock_preview_label.bind("<Configure>", app._on_lock_preview_resize)
    app._lock_info_var = tk.StringVar(value="")
    tk.Label(prev, textvariable=app._lock_info_var, anchor=tk.CENTER,
             font=scaling.font("Segoe UI", 8)).pack(fill=tk.X, padx=6, pady=(0, 4))


def _build_gallery_tab(app, parent):
    """
    Saved folders and gallery URLs, on their own tab.

    This was a panel in the right-hand column, splitting that space with the
    preview. A tab gives the list room to be a list, and the preview the rest.
    """
    fav_frame = tk.Frame(parent)
    fav_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

    fav_hdr = tk.Frame(fav_frame)
    fav_hdr.pack(fill=tk.X, padx=4, pady=(4, 0))
    tk.Label(fav_hdr, text="Quick-jump folders & gallery URLs:",
             font=scaling.font("Segoe UI", 9)).pack(side=tk.LEFT)

    fav_btn_row = tk.Frame(fav_frame)
    fav_btn_row.pack(fill=tk.X, padx=4, pady=2)

    c = BTN_COLORS["primary"]
    add_fol_btn = tk.Button(fav_btn_row, text="+ Add Folder",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              font=scaling.font("Segoe UI", 8), command=app._add_favorite_folder)
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
              font=scaling.font("Segoe UI", 8), command=app._add_favorite_url)
    add_url_btn.pack(side=tk.LEFT, padx=(0, 4))
    Tooltip(add_url_btn,
            "Add a website URL to favorites.\n"
            "• Click to enter a label and URL\n"
            "• Or drag a URL onto this button")
    dnd_mod.setup_dnd_on(add_url_btn, app._on_drop_on_add_btn, app._dnd_available)

    c = BTN_COLORS["danger"]
    rem_btn = tk.Button(fav_btn_row, text="Remove",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              font=scaling.font("Segoe UI", 8), command=app._remove_favorite)
    rem_btn.pack(side=tk.LEFT, padx=(0, 4))
    Tooltip(rem_btn, "Remove the selected favorite.\nOr right-click any item in the list.")

    c = BTN_COLORS["primary"]
    restore_btn = tk.Button(fav_btn_row, text="↺ Restore Defaults",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              font=scaling.font("Segoe UI", 8), command=app._restore_default_favorites)
    restore_btn.pack(side=tk.LEFT)
    Tooltip(restore_btn,
            "Re-adds the default lucid24 gallery URLs that may have been deleted.\n"
            "Safe to click any time — only missing defaults are added back.")

    fav_list_frame = tk.Frame(fav_frame)
    fav_list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    fav_scroll = tk.Scrollbar(fav_list_frame)
    fav_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    app._fav_listbox = tk.Listbox(fav_list_frame,
                                   font=scaling.font("Consolas", 9),
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


def _scrolling_column(app, minsize):
    """
    Add a column to the horizontal pane whose contents scroll if they must.

    pack stops handing out space once it runs short, and it drops the widgets
    at the foot of a column silently -- nothing on screen says they exist.
    That needs no resizing, only A+: at the window's own 800x600 minimum one
    press was enough to lose Set Wallpaper. Both columns get this because both
    now carry controls you cannot do without -- Browse... on the right is the
    only way to a file dialog.

    Returns (canvas, scrollbar, body); pack children into body.
    """
    outer = tk.Frame(app._h_pane)
    app._h_pane.add(outer, stretch="always", minsize=minsize)

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
        -- Preview on the left, History on the right -- fill the column as it
        always did; going taller when there is not is what makes the rest
        reachable rather than merely absent.
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
    # the wheel from the console and the two listboxes.
    canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _wheel))
    canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
    return canvas, bar, body


def build_ui(app):
    """Build the entire main window UI onto app (App instance)."""
    root = app.root
    t = THEMES.get(app.theme_name, THEMES["dark"])

    # ── Menu bar ──────────────────────────────────────────────────────────────
    # The font has to be set explicitly. On Windows a Menu resolves its default
    # into a concrete spec when it is created — cget returns "{Segoe UI} 9",
    # not the name "TkMenuFont" — so later changes to that named font never
    # reach it, and the menu bar would be the one thing A+/A− left behind.
    # 9 is what Windows uses, so 100% still looks native.
    # Not root.config(menu=...): Windows draws a real menu bar itself and
    # ignores Tk's colours for it, so a native bar stays a bright white strip
    # across the top of the dark theme — the one thing in the window that
    # refused to follow it. Two Menubuttons in an ordinary Frame pop the same
    # menus, take the theme, and scale with A+/A−.
    menu_font = scaling.font("Segoe UI", 9)

    menu_strip = tk.Frame(root)
    menu_strip.pack(side=tk.TOP, fill=tk.X)

    def _drop_down(label):
        """A Menubutton in the strip, plus the menu it posts."""
        mbtn = tk.Menubutton(menu_strip, text=label, font=menu_font,
                             padx=10, pady=3, relief=tk.FLAT)
        mbtn.pack(side=tk.LEFT)
        # The menu must be a CHILD of its own menubutton. Parented anywhere
        # else — root included — Tk accepts the -menu option and the widget
        # looks right, but the click quietly does nothing: no menu, no error,
        # and under pythonw no console for one to appear in either.
        menu = tk.Menu(mbtn, tearoff=0, font=menu_font)
        mbtn.config(menu=menu)
        return menu

    file_menu = _drop_down("File")
    file_menu.add_command(label="Browse for Image…", command=app._browse_image)
    file_menu.add_command(label="Clear Log   Ctrl+L", command=app._clear_log)
    file_menu.add_separator()
    file_menu.add_command(label="Exit", command=app._on_close)

    help_menu = _drop_down("Help")
    help_menu.add_command(label="Check for Updates…", command=app._check_updates)
    # Only offered when running from a loose folder — an installed copy has
    # nowhere left to install itself to.
    if app._can_install_to_pc():
        help_menu.add_command(label="Install on this PC…",
                              command=app._install_to_pc)
    # Settings ▸ Apps is the standard route, but people look for the uninstaller
    # in the app they want rid of, so offer it here too.
    if app._is_installed_copy():
        help_menu.add_command(label="Uninstall QiGor…", command=app._uninstall)
    help_menu.add_separator()
    help_menu.add_command(label="About   F1", command=app._show_about)

    # Kept so a theme toggle can repaint the drop-downs; Tk gives no way to
    # enumerate the menus belonging to a window.
    app._menus = [file_menu, help_menu]

    root.after(0, app._place_sizegrip)

    # ── Status bar (BOTTOM first) ─────────────────────────────────────────────
    app._status_bar = tk.Frame(root, relief=tk.SUNKEN, bd=1)
    app._status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    app.status_var = tk.StringVar(value="Ready")
    tk.Label(app._status_bar, textvariable=app.status_var,
             anchor=tk.W, padx=6).pack(side=tk.LEFT, fill=tk.X, expand=True)
    app.clock_var = tk.StringVar(value="")
    tk.Label(app._status_bar, textvariable=app.clock_var,
             anchor=tk.E, font=scaling.font("Consolas", 9),
             ).pack(side=tk.RIGHT, padx=(0, 20))

    # ── Progress bar ──────────────────────────────────────────────────────────
    # determinate at rest: an idle *indeterminate* bar draws its slider parked
    # at the left edge under the clam theme, which reads as a stray blue block
    # across the bottom of the window. _progress_start switches it over.
    app._progress = ttk.Progressbar(root, orient=tk.HORIZONTAL,
                                    mode="determinate", value=0)
    app._progress.pack(side=tk.BOTTOM, fill=tk.X)

    # ── Toolbar ───────────────────────────────────────────────────────────────
    toolbar = tk.Frame(root)
    toolbar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 4))

    app.theme_btn = tk.Button(toolbar, text="☀", width=3, command=app._toggle_theme)
    app.theme_btn.pack(side=tk.LEFT, padx=(0, 4))
    Tooltip(app.theme_btn, "Toggle dark / light theme.")

    # A− / reset / A+, in that order, matching qigor_wallpaper_sync. These zoom
    # the whole window — every panel, label, button, entry, menu and dialog —
    # not only the console.
    zoom_btn = tk.Button(toolbar, text="A-", width=3,
                         command=lambda: app._change_font(-1))
    zoom_btn.pack(side=tk.LEFT, padx=(2, 2))
    Tooltip(zoom_btn, "Make everything smaller.\n"
                      "Scales the whole window, not just the console.")

    reset_btn = tk.Button(toolbar, text="⟲", width=3, command=app._reset_font)
    reset_btn.pack(side=tk.LEFT, padx=2)
    Tooltip(reset_btn, f"Reset zoom to 100% ({scaling.BASE_SIZE} pt) — the size "
                       "every panel was designed at.")

    zoom_in_btn = tk.Button(toolbar, text="A+", width=3,
                            command=lambda: app._change_font(+1))
    zoom_in_btn.pack(side=tk.LEFT, padx=2)
    Tooltip(zoom_in_btn, "Make everything bigger.\n"
                         "Scales the whole window, not just the console.")

    c = BTN_COLORS["primary"]
    open_store_btn = tk.Button(toolbar, text="📁 Image store",
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

    # ── Hero image, right end of the toolbar ──────────────────────────────────
    # It used to sit in the drop zone, over the dead space at its top-left.
    # Scaled to the height of the buttons beside it so the toolbar does not
    # grow: a full-size 150x84 here would cost the left column ~50px of the
    # height it needs to fit without a scrollbar.
    app._hero_photo = None
    if PIL_AVAILABLE:
        try:
            from .images import load_bundled_image
            hero = load_bundled_image("qigor_wallpaper_manager_thumb.jpg")
            if hero:
                toolbar.update_idletasks()
                bar_h = max([b.winfo_reqheight() for b in toolbar.winfo_children()]
                            or [28])
                w = max(1, round(hero.width * bar_h / hero.height))
                hero = hero.resize((w, bar_h), Image.LANCZOS)
                app._hero_photo = ImageTk.PhotoImage(hero)
                hero_lbl = tk.Label(toolbar, image=app._hero_photo,
                                    bd=0, relief=tk.FLAT)
                hero_lbl.pack(side=tk.RIGHT, padx=(8, 0))
                Tooltip(hero_lbl, APP_NAME)
        except Exception:
            pass

    # Reminder and Slideshow are tabs of their own now, and each carries its
    # own ✔ when active — a button that only selected the tab beside it was
    # saying the same thing twice. About lives on the Help menu (and F1), and
    # Clear Log moved down beside the log it clears.

    # ── Main PanedWindow (vertical) ───────────────────────────────────────────
    app._main_pane = tk.PanedWindow(root, orient=tk.VERTICAL,
                                     sashrelief=tk.RAISED, sashwidth=6,
                                     bg="#555555")
    app._main_pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    # Wallpaper / Slideshow / Reminder. The console is added to the paned window
    # *below* the notebook rather than inside it, so switching tabs never hides
    # the log — which is the whole reason Slideshow and Reminder stopped being
    # modal windows: they covered the console at the exact moment it was
    # reporting what they had just done.
    app._notebook = ttk.Notebook(app._main_pane)
    app._main_pane.add(app._notebook, stretch="always", minsize=300)

    tab_wallpaper = tk.Frame(app._notebook)
    app._tab_wallpaper = tab_wallpaper
    app._notebook.add(tab_wallpaper, text="  🖼  Wallpaper  ")

    # ── Horizontal PanedWindow (left | right) ─────────────────────────────────
    app._h_pane = tk.PanedWindow(tab_wallpaper, orient=tk.HORIZONTAL,
                                   sashrelief=tk.RAISED, sashwidth=6,
                                   bg="#555555")
    app._h_pane.pack(fill=tk.BOTH, expand=True)

    # ─────────────────────────  LEFT COLUMN  ──────────────────────────────────
    # The preview, and the controls that act on it.
    app._left_canvas, app._left_scroll, left = _scrolling_column(app, 320)

    # ── Preview pane ──────────────────────────────────────────────────────────
    prev_frame = tk.LabelFrame(left, text="  Preview  ")
    prev_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

    app._preview_label = tk.Label(prev_frame,
        text="(no image selected)\n\nDrop or paste an image to preview",
        font=scaling.font("Segoe UI", 9), relief=tk.SUNKEN)
    app._preview_label.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 2))
    app._preview_label.bind("<Configure>", app._on_preview_resize)

    app._preview_info_var = tk.StringVar(value="")
    tk.Label(prev_frame, textvariable=app._preview_info_var,
             font=scaling.font("Segoe UI", 8), anchor=tk.CENTER,
             ).pack(fill=tk.X, padx=6, pady=(0, 2))

    btn_row_prev = tk.Frame(prev_frame)
    btn_row_prev.pack(pady=(0, 6))

    c = BTN_COLORS["primary"]
    prev_btn = tk.Button(btn_row_prev, text="🔍  Preview Selected",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              font=scaling.font("Segoe UI", 9), command=app._load_preview)
    prev_btn.pack(side=tk.LEFT, padx=(0, 4))
    Tooltip(prev_btn,
            "Load and display a preview of the current URL / file.\n"
            "Preview updates automatically when you drop or paste an image.\n"
            "Requires Pillow:  pip install pillow")

    c = BTN_COLORS["warning"]
    cur_wp_btn = tk.Button(btn_row_prev, text="🖥  Current Wallpaper",
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              font=scaling.font("Segoe UI", 9), command=app._show_current_wallpaper)
    cur_wp_btn.pack(side=tk.LEFT, padx=(0, 4))
    Tooltip(cur_wp_btn,
            "Preview the wallpaper currently set on your desktop.\n"
            "Reads the path directly from the Windows registry.")

    # "Current Lock Screen" used to sit here too. It now lives on the Lock
    # Screen tab, which brings you back here to look at the result — three
    # buttons no longer fit this row and the third was being clipped.

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
                            font=scaling.font("Segoe UI", 9),
                            command=lambda: (
                                app.cfg.set("wallpaper_style", app._style_var.get()),
                                app._reflow_preview()
                            ))
        rb.pack(side=tk.LEFT, padx=6)
        Tooltip(rb, _style_tips.get(s, s))

    copy_row = tk.Frame(opts_frame)
    copy_row.pack(fill=tk.X, padx=6, pady=(0, 6))
    cb = tk.Checkbutton(copy_row,
        text="Copy image to local store",
        variable=app._copy_var,
        font=scaling.font("Segoe UI", 9),
        command=lambda: app.cfg.set("copy_to_store", app._copy_var.get()))
    cb.pack(side=tk.LEFT)
    Tooltip(cb,
            "Prevents a broken wallpaper if the original file is moved,\n"
            "renamed or deleted.\n\n"
            "When checked: copies the image into the wallpaper store folder.\n"
            f"Store: {STORE_DIR}")

    # ── Action row 1: Set Wallpaper | ⚙ Wall ────────────────────────────────
    btn_row1 = tk.Frame(left)
    btn_row1.pack(fill=tk.X, pady=(0, 2))

    c = BTN_COLORS["success"]
    app.apply_btn = tk.Button(btn_row1, text="🖼  Set Wallpaper", height=2,
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        command=app._start_task)
    app.apply_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    Tooltip(app.apply_btn,
            "Apply the image as your desktop wallpaper.\n"
            "If a URL is entered, the image will be downloaded first.\nCtrl+R")

    c = BTN_COLORS["primary"]
    pers_bg_btn = tk.Button(btn_row1, text="⚙ Wall", height=2,
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        command=lambda: __import__("os").startfile(
            "ms-settings:personalization-background"))
    pers_bg_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
    Tooltip(pers_bg_btn,
            "Open Windows Settings → Personalization → Background.\n"
            "Set desktop background to Picture, Slideshow, or Spotlight.")

    # Lock screen now has its own tab — see _build_lock_tab.

    # ── Action row 3: Show Desktop | Cancel D-load ───────────────────────────
    btn_row3 = tk.Frame(left)
    btn_row3.pack(fill=tk.X, pady=(0, 6))

    c = BTN_COLORS["primary"]
    show_desk_btn = tk.Button(btn_row3, text="👁  Show Desktop", height=2,
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        command=app._preview_desktop)
    show_desk_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    Tooltip(show_desk_btn,
            "Minimize all windows so you can see the actual desktop wallpaper.\n\n"
            "Window layout is saved and restored exactly — immune to accidental\n"
            "clicks corrupting the state unlike Win+D.\n\n"
            "A countdown overlay auto-restores everything after 10 seconds.\n"
            "Click \'Restore Now\' or \'+10s\' to control the timer.\n\n"
            "Other ways to show desktop:\n"
            "  Win+D         — toggle (flaky if you click anything)\n"
            "  Win+M         — minimize all  (Win+Shift+M to restore)\n"
            "  Click taskbar bottom-right corner — toggle")

    c = BTN_COLORS["cancel"]
    app.cancel_btn = tk.Button(btn_row3, text="✖  Cancel D-load", height=2,
        bg=c["bg"], fg=c["fg"], activebackground=c["active"],
        command=app._cancel_task, state=tk.DISABLED)
    app.cancel_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
    Tooltip(app.cancel_btn, "Cancel an image download in progress.  Esc")

    # ── Last changed banner ───────────────────────────────────────────────────
    app._last_changed_var = tk.StringVar(value="")
    lc_lbl = tk.Label(left, textvariable=app._last_changed_var,
                      font=scaling.font("Segoe UI", 9, slant="italic"), anchor=tk.W)
    lc_lbl.pack(fill=tk.X, padx=2, pady=(0, 4))

    # ─────────────────────────  RIGHT COLUMN  ─────────────────────────────────
    # Picking an image, and the images picked before: the selector, with
    # History under it. History used to sit at the foot of the left column, a
    # long way from the field its entries load into.
    app._right_canvas, app._right_scroll, right = _scrolling_column(app, 260)

    # ── Image Selector ────────────────────────────────────────────────────────
    drop_frame = tk.LabelFrame(right,
        text="  Image Selector  ")
    drop_frame.pack(fill=tk.X, pady=(0, 6))

    app._drop_label = tk.Label(drop_frame,
        text="🖼  Drag a file from Explorer\n"
             "or drag an image from a browser\n"
             "or paste a URL / image address below",
        # 3 lines of text in a 5-line box: still a generous drop target, but
        # the column now fits the default window without a scrollbar.
        # No cursor="hand2" and no <Button-1>: clicking here used to open a
        # file browser, which is a whole Explorer window for a stray click on
        # what is meant to be a drop target. Browse... is the way in.
        height=5, relief=tk.RIDGE,
        font=scaling.font("Segoe UI", 10))
    app._drop_label.pack(fill=tk.X, padx=6, pady=(6, 4))
    Tooltip(app._drop_label,
            "• Drag an image file from Windows Explorer\n"
            "• Drag an image directly from a browser page\n"
            "• Right-click an image → Copy image address, paste below\n"
            "• Or use Browse… to pick a file")

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
    tk.Label(url_row, text="URL / Path:", font=scaling.font("Segoe UI", 9)
             ).pack(side=tk.LEFT, padx=(0, 4))
    app._url_entry = tk.Entry(url_row, textvariable=app._pending_path,
                               font=scaling.font("Consolas", 10))
    # Packed after Browse... below, so it takes only the space that is left.
    Tooltip(app._url_entry,
            "Paste a web URL, image address (right-click → Copy image address),\n"
            "or a local file path.  Press Enter or click Set Wallpaper.\n"
            "Supports http://, https://, file://, and plain paths.")
    app._url_entry.bind("<Return>", lambda _: app._start_task())

    c = BTN_COLORS["primary"]
    browse_btn = tk.Button(url_row, text="Browse…", font=scaling.font("Segoe UI", 9),
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              command=app._browse_image)
    # Browse... first and anchored right: left-to-right, the label and entry
    # claimed the row's width and this fell off the end. It is the only way to
    # a file dialog now, so it cannot be the thing that gets squeezed out.
    browse_btn.pack(side=tk.RIGHT, padx=(4, 2))
    app._url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    Tooltip(browse_btn, "Open a file browser to pick an image from disk.")

    # ── History list, under the selector it feeds ─────────────────────────────
    hist_frame = tk.LabelFrame(right, text="  History  ")
    hist_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

    hist_hdr = tk.Frame(hist_frame)
    hist_hdr.pack(fill=tk.X, padx=4, pady=(4, 0))
    tk.Label(hist_hdr, text="Recent wallpapers (click to re-apply):",
             font=scaling.font("Segoe UI", 9)).pack(side=tk.LEFT)
    c = BTN_COLORS["danger"]
    clrhist_btn = tk.Button(hist_hdr, text="Clear History", font=scaling.font("Segoe UI", 8),
              bg=c["bg"], fg=c["fg"], activebackground=c["active"],
              command=app._clear_history)
    clrhist_btn.pack(side=tk.RIGHT, padx=4)
    Tooltip(clrhist_btn, "Remove all entries from the history list.\nDoes not delete files from disk.")

    hist_list_frame = tk.Frame(hist_frame)
    hist_list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    scrollbar = tk.Scrollbar(hist_list_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    # height=3 is a floor, not a size: it still expands to fill whatever the
    # column has spare, so at any normal window size this looks unchanged. Tk's
    # default of 10 lines made the column *ask* for more height than the window
    # has, which kept the scrollbar up even with room to spare.
    app._hist_listbox = tk.Listbox(hist_list_frame, height=3,
                                    font=scaling.font("Consolas", 9),
                                    yscrollcommand=scrollbar.set,
                                    selectmode=tk.SINGLE)
    app._hist_listbox.pack(fill=tk.BOTH, expand=True)
    scrollbar.config(command=app._hist_listbox.yview)
    app._hist_listbox.bind("<<ListboxSelect>>", app._on_history_select)
    app._hist_listbox.bind("<Double-Button-1>", lambda _: app._start_task())
    Tooltip(app._hist_listbox,
            "Click to load into the URL/path field and preview.\n"
            "Double-click to apply immediately.")

    # ── Lock Screen tab ───────────────────────────────────────────────────────
    lock_tab = tk.Frame(app._notebook)
    app._notebook.add(lock_tab, text="  🔒  Lock Screen  ")
    _build_lock_tab(app, lock_tab)

    # ── Slideshow and Reminder tabs ───────────────────────────────────────────
    # Built once and kept. As dialogs these were rebuilt from disk on every
    # open; as tabs they hold their state, and their buttons report back
    # through on_result instead of the old wait_window handshake.
    app._slideshow_panel = SlideshowPanel(app._notebook, app.cfg, app.theme_name,
                                          on_result=app._on_slideshow_result)
    app._notebook.add(app._slideshow_panel, text="  ▶  Slideshow  ")

    app._reminder_panel = ReminderPanel(app._notebook, app.cfg, app.theme_name,
                                        on_result=app._on_reminder_result)
    app._notebook.add(app._reminder_panel, text="  ⏰  Reminder  ")

    # ── Gallery URLs tab ──────────────────────────────────────────────────────
    gallery_tab = tk.Frame(app._notebook)
    app._notebook.add(gallery_tab, text="  🌐  Gallery URLs  ")
    _build_gallery_tab(app, gallery_tab)

    app._notebook.bind("<<NotebookTabChanged>>", app._on_tab_changed)

    # ── Console ───────────────────────────────────────────────────────────────
    console_outer = tk.Frame(app._main_pane)
    app._main_pane.add(console_outer, stretch="never", minsize=60)

    console_hdr = tk.Frame(console_outer)
    console_hdr.pack(fill=tk.X)
    tk.Label(console_hdr, text="Log",
             font=scaling.font("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
    clr_btn = tk.Button(console_hdr, text="Clear Log", command=app._clear_log,
                        font=scaling.font("Segoe UI", 8), padx=6)
    clr_btn.pack(side=tk.RIGHT, padx=(8, 0))
    Tooltip(clr_btn, "Clear the log console.  Ctrl+L")

    app._autoscroll_var = tk.BooleanVar(value=app.cfg.get("autoscroll"))
    tk.Checkbutton(console_hdr, text="Auto-scroll",
                   variable=app._autoscroll_var,
                   command=app._on_autoscroll_toggle,
                   ).pack(side=tk.RIGHT)

    console_frame = tk.LabelFrame(console_outer, text="")
    console_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
    # Held on the app: the theme code and A+/A- both need these same objects,
    # and a tag given a font *tuple* would never follow a zoom.
    app._font_console      = scaling.font("Consolas", scaling.BASE_SIZE)
    app._font_console_bold = scaling.font("Consolas", scaling.BASE_SIZE, "bold")
    app.console = scrolledtext.ScrolledText(
        console_frame, font=app._font_console, wrap=tk.WORD, height=6)
    app.console.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

    for tag, color in CONSOLE_COLORS["dark"].items():
        app.console.tag_configure(
            tag, foreground=color,
            font=app._font_console_bold if tag == "bold" else app._font_console)
    app.console.tag_configure(
        "default", foreground="#d4d4d4", font=app._font_console)

    app._log("─" * 52, "dim")
    app._log(f"  {APP_NAME}  v{APP_VERSION}", "bold")
    if not PIL_AVAILABLE:
        app._log("  ⚠  Pillow not found — preview disabled.  pip install pillow", "yellow")
    app._log("─" * 52, "dim")
    root.after(0, app._post_build_log)
