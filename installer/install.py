#!/usr/bin/env pythonw
# -*- coding: utf-8 -*-
"""
install.py  —  QiGor Wallpaper Manager installer.

Run by double-clicking Install.cmd, which hands this file to the bundled
runtime\\pythonw.exe. Nothing here is compiled and nothing new is executed: the
only PE image in the whole flow is the Python Software Foundation's own signed
interpreter, which is the entire reason this ships as a zip instead of an EXE.

  install.py                       interactive installer window
  install.py --silent --target D   headless reinstall into D (used by the updater)
     [--wait-pid N]                wait for the old copy to exit first
     [--relaunch]                  start the app when finished
     [--no-desktop]                skip the desktop shortcut
     [--cleanup DIR]               delete DIR on the way out, after this
                                   process exits — normally the temp folder
                                   this very copy was extracted into
"""
import sys
import threading
import traceback
from pathlib import Path

# Run as a plain script (pythonw.exe installer\install.py), so the package root
# is not on sys.path yet and relative imports would fail.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from installer import core                              # noqa: E402
from installer.paths import (DISPLAY_NAME, install_root, payload_root,  # noqa: E402
                             is_installed_copy)

BG      = "#1e1e1e"
FG      = "#d4d4d4"
DIM     = "#888888"
ACCENT  = "#0e639c"
ACCENT2 = "#1177bb"
OK      = "#4ec9b0"
ERR     = "#f48771"
CON_BG  = "#0f0f0f"


# ── Headless ──────────────────────────────────────────────────────────────────

def run_silent(argv) -> int:
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    target   = opt("--target")
    wait_pid = opt("--wait-pid")
    cleanup  = opt("--cleanup")
    lines    = []

    def log(msg):
        lines.append(str(msg))

    try:
        root = core.install(payload_root(),
                            target=Path(target) if target else None,
                            desktop="--no-desktop" not in argv,
                            log=log,
                            wait_pid=int(wait_pid) if wait_pid else None)
    except Exception as e:
        # No console and no window in silent mode, so leave a trail on disk.
        core.note_failure("silent install", e)
        crash = Path.home() / ".qigor-wallpaper" / "install_error.txt"
        crash.parent.mkdir(parents=True, exist_ok=True)
        crash.write_text("\n".join(lines) + "\n\n" + traceback.format_exc(),
                         encoding="utf-8")
        return 1

    if "--relaunch" in argv:
        core.launch(root)
    if cleanup:
        # Queued rather than deleted: this interpreter is running out of the
        # folder being removed, so the delete has to outlive the process.
        core.schedule_delete(Path(cleanup))
    return 0


# ── Interactive ───────────────────────────────────────────────────────────────

class InstallerWindow:

    def __init__(self, root):
        import tkinter as tk

        self.tk   = tk
        self.root = root
        self.src  = payload_root()
        self.dst  = install_root()
        self.busy = False
        self.done = False

        root.title("Install {}".format(DISPLAY_NAME))
        root.configure(bg=BG)
        root.geometry("620x480")
        root.minsize(560, 420)

        icon = self.src / "assets" / "qigor_wallpaper_manager_icon.png"
        try:
            if icon.exists():
                self._icon = tk.PhotoImage(file=str(icon))
                root.iconphoto(True, self._icon)
        except Exception:
            pass

        pad = dict(padx=22)
        tk.Label(root, text=DISPLAY_NAME, bg=BG, fg=FG,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(18, 0), **pad)

        meta = core.read_version(self.src)
        sub  = "Version {}".format(meta.get("build") or meta.get("version") or "—")
        if meta.get("runtime"):
            sub += "   •   bundled Python {}".format(meta["runtime"])
        tk.Label(root, text=sub, bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 12), **pad)

        note, note_fg = self._existing_install_note(meta)
        tk.Label(root, text=note, bg=BG, fg=note_fg, font=("Segoe UI", 9),
                 wraplength=560, justify="left").pack(anchor="w", **pad)

        box = tk.Frame(root, bg=BG)
        box.pack(fill="x", pady=(10, 4), **pad)
        tk.Label(box, text="Install to:", bg=BG, fg=FG,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(box, text=str(self.dst), bg=BG, fg=DIM,
                 font=("Consolas", 9), anchor="w").pack(fill="x")

        self.v_desktop  = tk.BooleanVar(value=True)
        self.v_launch   = tk.BooleanVar(value=True)
        for var, text in ((self.v_desktop, "Create a desktop shortcut"),
                          (self.v_launch,  "Open the app when finished")):
            tk.Checkbutton(root, text=text, variable=var, bg=BG, fg=FG,
                           selectcolor=CON_BG, activebackground=BG,
                           activeforeground=FG, highlightthickness=0,
                           font=("Segoe UI", 10)).pack(anchor="w", **pad)

        self.console = tk.Text(root, bg=CON_BG, fg=FG, font=("Consolas", 9),
                               relief="flat", height=9, wrap="word",
                               insertbackground=FG)
        self.console.pack(fill="both", expand=True, pady=(12, 8), **pad)
        self.console.tag_config("ok",  foreground=OK)
        self.console.tag_config("err", foreground=ERR)
        self.console.configure(state="disabled")

        bar = tk.Frame(root, bg=BG)
        bar.pack(fill="x", pady=(0, 16), **pad)
        self.btn = tk.Button(bar, text="Install", bg=ACCENT, fg="#ffffff",
                             activebackground=ACCENT2, activeforeground="#ffffff",
                             font=("Segoe UI", 11, "bold"), relief="flat",
                             width=16, height=1, cursor="hand2",
                             command=self.on_primary)
        self.btn.pack(side="right")
        tk.Button(bar, text="Close", bg="#3a3a3a", fg=FG, relief="flat",
                  activebackground="#4a4a4a", font=("Segoe UI", 10),
                  width=10, command=root.destroy).pack(side="right", padx=(0, 8))

        err = core.validate_payload(self.src)
        if err:
            self.log(err, "err")
            self.log("Extract the whole zip first, then run Install.cmd from "
                     "inside the extracted folder.")
            self.btn.configure(state="disabled")
        elif is_installed_copy(self.src):
            self.log("This is already the installed copy — nothing to do.", "ok")
            self.log("Use Settings ▸ Apps to remove it, or Uninstall.cmd "
                     "in this folder.")
            self.btn.configure(state="disabled")

    def _existing_install_note(self, payload_meta):
        """
        Say plainly what this install will do to what is already there.

        A reinstall silently replacing a newer build with an older one is the
        one case worth calling out in colour — it is easy to reach by opening an
        old download twice.
        """
        installed = core.read_version(self.dst) if self.dst.exists() else {}
        if not installed:
            return ("Installs for your user account only — no administrator "
                    "password needed."), DIM

        have = installed.get("build") or "?"
        new  = payload_meta.get("build") or "?"
        if have == new:
            return ("Version {} is already installed. Installing again will "
                    "repair it, keeping your settings.".format(have)), DIM
        if core.is_newer(new, have):
            return ("Upgrading the installed version {} to {}. Your settings, "
                    "history, slideshow and reminder are kept.".format(have, new)), DIM
        return ("Warning: version {} is installed and is NEWER than the {} in "
                "this folder. Installing will roll it back.".format(have, new)), ERR

    # ── log ───────────────────────────────────────────────────────────────────

    def log(self, msg, tag=""):
        def write():
            self.console.configure(state="normal")
            self.console.insert("end", str(msg) + "\n", tag)
            self.console.see("end")
            self.console.configure(state="disabled")
        self.root.after(0, write)

    # ── actions ───────────────────────────────────────────────────────────────

    def on_primary(self):
        if self.done:
            self.root.destroy()
            return
        if self.busy:
            return
        self.busy = True
        self.btn.configure(state="disabled", text="Installing…")
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        try:
            root = core.install(self.src, desktop=self.v_desktop.get(),
                                log=self.log)
        except Exception as e:
            path = core.note_failure("install", e)
            self.log("")
            self.log("Install failed: {}".format(e), "err")
            self.log("")
            self.log("Written to {}".format(path))
            self.root.after(0, lambda: self.btn.configure(
                state="normal", text="Retry"))
            self.busy = False
            return

        self.log("You can delete this extracted folder now.", "ok")
        self.busy = True
        self.done = True
        self.root.after(0, lambda: self.btn.configure(state="normal", text="Done"))
        if self.v_launch.get():
            core.launch(root)
            self.root.after(900, self.root.destroy)


def run_gui() -> int:
    import tkinter as tk
    root = tk.Tk()
    InstallerWindow(root)
    root.mainloop()
    return 0


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(run_silent(sys.argv) if "--silent" in sys.argv else run_gui())
