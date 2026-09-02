#!/usr/bin/env pythonw
# -*- coding: utf-8 -*-
"""
uninstall.py  —  remove an installed QiGor Wallpaper Manager.

Reached from Settings ▸ Apps (the registered UninstallString points here) or by
running Uninstall.cmd in the install folder.

  uninstall.py            confirmation window
  uninstall.py --silent   no window
     [--purge]            also delete settings and saved wallpapers
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from installer import core                                          # noqa: E402
from installer.paths import DISPLAY_NAME, payload_root              # noqa: E402

BG, FG, DIM, CON_BG = "#1e1e1e", "#d4d4d4", "#888888", "#0f0f0f"
DANGER, DANGER2, OK = "#7a1c1c", "#9e2020", "#4ec9b0"

SETTINGS_DIR = Path.home() / ".qigor-wallpaper"


class UninstallWindow:

    def __init__(self, root):
        import tkinter as tk

        self.root   = root
        self.target = payload_root()
        self.done   = False

        root.title("Uninstall {}".format(DISPLAY_NAME))
        root.configure(bg=BG)
        root.geometry("600x420")
        root.minsize(540, 380)

        pad = dict(padx=22)
        tk.Label(root, text="Uninstall {}".format(DISPLAY_NAME), bg=BG, fg=FG,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(18, 6), **pad)

        meta = core.read_version(self.target)
        tk.Label(root, text="Version {}   •   {}".format(
                     meta.get("build", "?"), self.target),
                 bg=BG, fg=DIM, font=("Consolas", 9), wraplength=540,
                 justify="left").pack(anchor="w", pady=(0, 12), **pad)

        tk.Label(root,
                 text=("This removes the program, its shortcuts, and the "
                       "slideshow and reminder scheduled tasks."),
                 bg=BG, fg=FG, font=("Segoe UI", 10), wraplength=540,
                 justify="left").pack(anchor="w", **pad)

        self.v_purge = tk.BooleanVar(value=False)
        tk.Checkbutton(root, variable=self.v_purge, bg=BG, fg=FG,
                       selectcolor=CON_BG, activebackground=BG,
                       activeforeground=FG, highlightthickness=0,
                       font=("Segoe UI", 10),
                       text="Also delete my settings, history, and saved wallpapers"
                       ).pack(anchor="w", pady=(12, 0), **pad)
        tk.Label(root, text="      {}".format(SETTINGS_DIR), bg=BG, fg=DIM,
                 font=("Consolas", 8)).pack(anchor="w", **pad)

        self.console = tk.Text(root, bg=CON_BG, fg=FG, font=("Consolas", 9),
                               relief="flat", height=7, wrap="word")
        self.console.pack(fill="both", expand=True, pady=(14, 8), **pad)
        self.console.tag_config("ok", foreground=OK)
        self.console.configure(state="disabled")

        bar = tk.Frame(root, bg=BG)
        bar.pack(fill="x", pady=(0, 16), **pad)
        self.btn = tk.Button(bar, text="Uninstall", bg=DANGER, fg="#ffffff",
                             activebackground=DANGER2, activeforeground="#ffffff",
                             font=("Segoe UI", 11, "bold"), relief="flat",
                             width=16, cursor="hand2", command=self.on_primary)
        self.btn.pack(side="right")
        self.cancel = tk.Button(bar, text="Keep it", bg="#3a3a3a", fg=FG,
                                relief="flat", activebackground="#4a4a4a",
                                font=("Segoe UI", 10), width=10,
                                command=root.destroy)
        self.cancel.pack(side="right", padx=(0, 8))

    def log(self, msg, tag=""):
        def write():
            self.console.configure(state="normal")
            self.console.insert("end", str(msg) + "\n", tag)
            self.console.see("end")
            self.console.configure(state="disabled")
        self.root.after(0, write)

    def on_primary(self):
        if self.done:
            self.root.destroy()
            return
        self.btn.configure(state="disabled", text="Removing…")
        self.cancel.configure(state="disabled")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            core.uninstall(self.target, remove_settings=self.v_purge.get(),
                           log=self.log)
        except RuntimeError as e:
            # Nothing has been removed at this point, so the retry is safe.
            self.log("")
            self.log(str(e))
            self.root.after(0, lambda: (
                self.btn.configure(state="normal", text="Try again"),
                self.cancel.configure(state="normal")))
            return
        self.done = True
        self.log("This window closes in a moment.", "ok")
        # The folder deletion is queued in a detached cmd that waits a few
        # seconds; this process has to be gone by then, because the runtime it
        # is executing from is inside the folder being removed.
        self.root.after(1500, self.root.destroy)


if __name__ == "__main__":
    if "--silent" in sys.argv:
        # This is what winget and Settings run via QuietUninstallString, so a
        # refusal has to come back as a non-zero exit rather than a window.
        try:
            core.uninstall(payload_root(),
                           remove_settings="--purge" in sys.argv,
                           log=lambda *_: None)
        except RuntimeError:
            sys.exit(1)
        sys.exit(0)
    import tkinter as tk
    win = tk.Tk()
    UninstallWindow(win)
    win.mainloop()
