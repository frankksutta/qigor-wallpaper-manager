"""
ui.py  —  QiGor Wallpaper Manager
All widget construction. Called as build_ui(app) from app.py.
No business logic here — only layout, bindings, and wiring to app methods.
"""
import os
import tkinter as tk
from tkinter import ttk, scrolledtext

from .constants import (APP_NAME, APP_VERSION, THEMES, BTN_COLORS,
                        CONSOLE_COLORS, WALLPAPER_STYLES, STORE_DIR,
                        mark_role)
from . import scaling
from .tooltip import Tooltip
from .slideshow import SlideshowPanel
from .reminder import ReminderPanel
from .playlists import PlaylistPanel
from . import dnd as dnd_mod
from . import imagepanes

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def _build_wallpaper_tab(app, parent):
    """The Wallpaper tab: the shared panes, plus what is specific to wallpaper."""

    def style_pane(left, panes):
        opts_frame = tk.LabelFrame(left, text="  Display Style  ")
        opts_frame.pack(fill=tk.X, pady=(0, 6))

        style_row = tk.Frame(opts_frame)
        style_row.pack(fill=tk.X, padx=6, pady=4)
        tips = {
            "Fill":    "Zoom to fill screen, crop edges if aspect differs.",
            "Fit":     "Fit whole image on screen, letterbox if needed.",
            "Stretch": "Stretch to fill — may distort aspect ratio.",
            "Tile":    "Repeat image in a grid pattern.",
            "Center":  "Show at original size, centered on desktop.",
            "Span":    "Stretch across all monitors (multi-monitor).",
        }
        for s in WALLPAPER_STYLES:
            rb = tk.Radiobutton(style_row, text=s, variable=app._style_var,
                                value=s, font=scaling.font("Segoe UI", 9),
                                command=lambda: (
                                    app.cfg.set("wallpaper_style",
                                                app._style_var.get()),
                                    panes.reflow_preview()))
            rb.pack(side=tk.LEFT, padx=6)
            Tooltip(rb, tips.get(s, s))

    def copy_to_store(row):
        """
        The option that changes what Set Wallpaper does, beside the button.

        It sat in Display Style, which is about how an image is drawn, not
        about whether a copy of it is kept.
        """
        cb = tk.Checkbutton(
            row, text="Copy to image store", variable=app._copy_var,
            font=scaling.font("Segoe UI", 9),
            command=lambda: app.cfg.set("copy_to_store", app._copy_var.get()))
        cb.pack(side=tk.LEFT, padx=(8, 0))
        Tooltip(cb,
                "Nothing is saved to the image store until you apply it:\n"
                "press Set Wallpaper here, or Set Lock Screen on that tab,\n"
                "with an image that is not in the store already.\n\n"
                "Keeping a copy means the wallpaper survives the original "
                "being\nmoved, renamed or deleted.\n\n"
                f"Store: {STORE_DIR}")

    def footer(left, panes):
        app._last_changed_var = tk.StringVar(value="")
        tk.Label(left, textvariable=app._last_changed_var, anchor=tk.W,
                 font=scaling.font("Segoe UI", 9, slant="italic")
                 ).pack(fill=tk.X, padx=2, pady=(0, 4))

    spec = imagepanes.PaneSpec(
        "wallpaper",
        # The app made this var before the UI existed, and _do_task and the
        # entry trace both hold it, so the pane set adopts it rather than
        # making its own.
        pending_var=app._pending_path,
        style_getter=lambda: app._style_var.get(),
        style_pane=style_pane,
        footer=footer,
        show_history=True,
        on_apply=app._start_task,
        browse_title="Select wallpaper image",
        preview_buttons=[
            {"text": "🔍  Preview Selected", "colour": "primary", "height": 1,
             "command": lambda: app._wp_panes.load_preview(),
             "tooltip": "Load and display a preview of the current URL / file.\n"
                        "Preview updates automatically when you drop or paste "
                        "an image.\nRequires Pillow:  pip install pillow"},
            {"text": "🖥  Current Wallpaper", "colour": "warning", "height": 1,
             "command": app._show_current_wallpaper,
             "tooltip": "Preview the wallpaper currently set on your desktop.\n"
                        "Reads the path directly from the Windows registry."},
        ],
        action_rows=[
            [
                {"text": "🖼  Set Wallpaper", "colour": "success",
                 "command": app._start_task, "attr": "apply_btn",
                 "tooltip": "Apply the image as your desktop wallpaper.\n"
                            "If a URL is entered, the image will be downloaded "
                            "first.\nCtrl+R"},
                {"text": "⚙ Wall", "colour": "primary",
                 "command": lambda: os.startfile(
                     "ms-settings:personalization-background"),
                 "tooltip": "Open Windows Settings → Personalization → "
                            "Background.\nSet desktop background to Picture, "
                            "Slideshow, or Spotlight."},
                {"build": copy_to_store},
            ],
            [
                {"text": "👁  Show Desktop", "colour": "primary",
                 "command": app._preview_desktop,
                 "tooltip": "Minimize all windows so you can see the actual "
                            "desktop wallpaper.\n\nWindow layout is saved and "
                            "restored exactly — immune to accidental\nclicks "
                            "corrupting the state unlike Win+D.\n\nA countdown "
                            "overlay auto-restores everything after 10 seconds."},
                {"text": "✖  Cancel D-load", "colour": "cancel",
                 "command": app._cancel_task, "state": tk.DISABLED,
                 "attr": "cancel_btn",
                 "tooltip": "Cancel an image download in progress.  Esc"},
            ],
        ])

    app._wp_panes = imagepanes.build(app, parent, spec)

    # Legacy names. The rest of app.py — _do_task, the shortcuts, the
    # favourites list — reaches for these directly, and the Wallpaper tab is
    # what they have always meant.
    ps = app._wp_panes
    app._h_pane = ps.h_pane
    app._left_canvas, app._left_scroll = ps.left_canvas, ps.left_scroll
    app._right_canvas, app._right_scroll = ps.right_canvas, ps.right_scroll
    app._drop_label = ps.drop_label
    app._url_entry = ps.url_entry
    app._preview_label = ps.preview_label
    app._preview_info_var = ps.preview_info_var
    app._store_listbox = ps.store_listbox
    app._hist_listbox = ps.hist_listbox
    return ps


def _build_lock_tab(app, parent):
    """
    The Lock Screen tab: the same panes, with a fixed display mode.

    It used to be three buttons and an echo of whatever the Wallpaper tab had
    selected. It now picks its own image, so the two tabs no longer have to
    agree on one.
    """

    def style_pane(left, panes):
        frame = tk.LabelFrame(left, text="  Display Style  ")
        frame.pack(fill=tk.X, pady=(0, 6))
        tk.Label(frame, text="Fill — cropped to cover the whole screen.",
                 anchor=tk.W, font=scaling.font("Segoe UI", 9)
                 ).pack(fill=tk.X, padx=8, pady=(6, 0))
        mark_role(tk.Label(
            frame, anchor=tk.W, justify=tk.LEFT, wraplength=440,
            fg=CONSOLE_COLORS[app.theme_name]["dim"],
            font=scaling.font("Segoe UI", 8),
            text="Windows does not offer a choice here — the lock screen "
                 "image is always scaled to cover the screen and cropped to "
                 "fit. The preview above shows it the same way."
        ), "dim").pack(fill=tk.X, padx=8, pady=(2, 8))

    spec = imagepanes.PaneSpec(
        "lock",
        preview_title="  Lock screen preview  ",
        preview_placeholder="(no image selected)\n\n"
                            "Drop or paste an image, or click “Show Current”",
        # Not adjustable: Windows always covers the screen and crops.
        style_getter=lambda: "Fill",
        style_pane=style_pane,
        on_apply=app._set_lock_screen,
        browse_title="Select lock screen image",
        preview_buttons=[
            {"text": "🔍  Preview Selected", "colour": "primary", "height": 1,
             "command": lambda: app._ls_panes.load_preview(),
             "tooltip": "Load and display a preview of the current URL / file."},
            {"text": "🔒  Show Current", "colour": "success", "height": 1,
             "command": app._show_lock_preview,
             "tooltip": "Show the image Windows is using as the lock screen "
                        "now."},
        ],
        action_rows=[
            [
                {"text": "🔒  Set Lock Screen", "colour": "warning",
                 "bold": True, "size": 10, "attr": "lock_btn",
                 "command": app._set_lock_screen,
                 "tooltip": "Set the Windows lock screen image.\n\n"
                            "A Windows permission (UAC) prompt will appear "
                            "briefly.\nThe app stays open — a small helper runs "
                            "the change and exits."},
                {"text": "⚙ Lock", "colour": "primary", "size": 10,
                 "attr": "_ls_pers_btn",
                 "command": app._ls_personalize_or_release,
                 "tooltip": "Open Settings → Personalization → Lock screen.\n"
                            "If a custom image policy is active, releases it "
                            "first (UAC prompt)\nthen opens Settings so you can "
                            "change the lock screen mode."},
            ],
        ])

    app._ls_panes = imagepanes.build(app, parent, spec)

    # _show_lock_preview and its resize handler predate the shared panes and
    # still speak in these names.
    app._lock_preview_label = app._ls_panes.preview_label
    app._lock_info_var = app._ls_panes.preview_info_var
    return app._ls_panes


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

    _build_wallpaper_tab(app, tab_wallpaper)

    # ── Lock Screen tab ───────────────────────────────────────────────────────
    lock_tab = tk.Frame(app._notebook)
    app._notebook.add(lock_tab, text="  🔒  Lock Screen  ")
    # Kept so active_panes() can tell which tab's selection to act on.
    app._lock_tab = lock_tab
    _build_lock_tab(app, lock_tab)

    # No tkdnd means nothing to drop onto, so the clipboard is the way in.
    # Checked after both tabs, since either one wiring up counts.
    if not app._dnd_available:
        root.bind("<Control-v>", app._on_paste)

    # ── Slideshow and Reminder tabs ───────────────────────────────────────────
    # Built once and kept. As dialogs these were rebuilt from disk on every
    # open; as tabs they hold their state, and their buttons report back
    # through on_result instead of the old wait_window handshake.
    app._slideshow_panel = SlideshowPanel(
        app._notebook, app.cfg, app.theme_name,
        on_result=app._on_slideshow_result,
        on_scheduled=lambda s: app._mark_tab(app._slideshow_panel, s),
        on_edit_playlists=app._show_playlists_tab,
        log=app._log)
    app._notebook.add(app._slideshow_panel, text="  ▶  Slideshow  ")

    # Next to the Slideshow tab, which is the only thing that plays a
    # playlist. Editing one takes effect on the next rotation, so the two
    # tabs get used together.
    app._playlist_panel = PlaylistPanel(
        app._notebook, app.cfg, app.theme_name,
        on_use=app._use_playlist,
        on_change=app._on_playlists_changed,
        log=app._log)
    app._notebook.add(app._playlist_panel, text="  ☰  Playlists  ")

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
