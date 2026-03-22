"""
reminder.py  —  QiGor Wallpaper Manager
_ReminderDialog and Windows Task Scheduler integration.
"""
from __future__ import annotations
import subprocess
import sys
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path

from .constants import THEMES, BTN_COLORS, CONSOLE_COLORS
from .wallpaper import find_python_exe


class _ReminderDialog(tk.Toplevel):
    """
    Dialog to schedule a Windows Task Scheduler task that fires a
    winotify toast reminder to change the wallpaper.
    result: "set" | "removed" | None
    """
    TASK_NAME = "QiGorWallpaperReminder"

    def __init__(self, parent, cfg, theme_name, font_size, app_dir):
        super().__init__(parent)
        self.title("Wallpaper Change Reminder")
        self.result = None
        self._cfg   = cfg
        self._app_dir = Path(app_dir)
        self._app     = str(self._app_dir / (
            "QiGor_Wallpaper_Manager.exe"
            if (self._app_dir / "QiGor_Wallpaper_Manager.exe").exists()
            else "qigor_wallpaper_manager.pyw"
        ))
        self._theme = theme_name
        t = THEMES.get(theme_name, THEMES["dark"])
        self.configure(bg=t["bg"])
        self.resizable(True, False)
        self.minsize(480, 0)
        self.grab_set()
        fn  = ("Segoe UI", font_size)
        fnb = ("Segoe UI", font_size, "bold")
        fns = ("Segoe UI", font_size - 1)
        dim = CONSOLE_COLORS[theme_name]["dim"]

        saved_freq  = cfg.get("reminder_freq")  or "weekly"
        saved_dow   = cfg.get("reminder_dow")   or "MON"
        saved_ndays = cfg.get("reminder_ndays") or "7"
        saved_hour  = cfg.get("reminder_hour")  or "09"
        saved_min   = cfg.get("reminder_min")   or "00"

        ttk.Sizegrip(self).place(relx=1.0, rely=1.0, anchor="se")

        btn_row = tk.Frame(self, bg=t["bg"])
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(4, 12))

        c = BTN_COLORS["success"]
        tk.Button(btn_row, text="Schedule Reminder", height=2, font=fnb,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._schedule).pack(side=tk.LEFT, fill=tk.X,
                                               expand=True, padx=(0, 4))
        c = BTN_COLORS["primary"]
        tk.Button(btn_row, text="🔔 Test Toast Now", height=2, font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._test_toast).pack(side=tk.LEFT, fill=tk.X,
                                                 expand=True, padx=(0, 4))
        c = BTN_COLORS["warning"]
        tk.Button(btn_row, text="📋 Check Log", height=2, font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._show_log).pack(side=tk.LEFT, fill=tk.X,
                                               expand=True, padx=(0, 4))
        c = BTN_COLORS["danger"]
        tk.Button(btn_row, text="Remove Reminder", height=2, font=fn,
                  bg=c["bg"], fg=c["fg"], activebackground=c["active"],
                  command=self._remove).pack(side=tk.LEFT, fill=tk.X,
                                             expand=True, padx=(0, 4))
        tk.Button(btn_row, text="Cancel", height=2, font=fn,
                  bg=t["btn_bg"], fg=t["btn_fg"],
                  command=self.destroy).pack(side=tk.LEFT, fill=tk.X, expand=True)

        body = tk.Frame(self, bg=t["bg"])
        body.pack(fill=tk.BOTH, padx=16, pady=(14, 6))

        tk.Label(body, font=fnb, bg=t["bg"], fg=t["fg"],
                 text="Schedule a gentle wallpaper change reminder").pack(anchor=tk.W)
        tk.Label(body, font=fns, bg=t["bg"], fg=dim, wraplength=440,
                 text="A quiet Windows notification will appear in the bottom-right corner "
                      "at your chosen time. It auto-dismisses after ~5 seconds and sits "
                      "in Action Center — won't interrupt your work.").pack(
                          anchor=tk.W, pady=(2, 6))

        task_status = self._query_task_status()
        status_color = CONSOLE_COLORS[theme_name]["green"] if "Ready" in task_status \
                       else CONSOLE_COLORS[theme_name]["yellow"]
        tk.Label(body, text=task_status, font=fns, bg=t["bg"], fg=status_color,
                 wraplength=440, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))

        freq_row = tk.Frame(body, bg=t["bg"])
        freq_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(freq_row, text="Remind me:", font=fnb,
                 bg=t["bg"], fg=t["fg"], width=12, anchor=tk.W).pack(side=tk.LEFT)
        self._freq_var = tk.StringVar(value=saved_freq)
        for val, lbl in [("daily", "Every day"), ("weekly", "Every week"),
                          ("custom", "Every N days")]:
            tk.Radiobutton(freq_row, text=lbl, variable=self._freq_var, value=val,
                           font=fn, bg=t["bg"], fg=t["fg"],
                           selectcolor=t["entry_bg"], activebackground=t["bg"],
                           command=self._on_freq_change).pack(side=tk.LEFT, padx=6)

        dow_row = tk.Frame(body, bg=t["bg"])
        tk.Label(dow_row, text="Day:", font=fnb,
                 bg=t["bg"], fg=t["fg"], width=12, anchor=tk.W).pack(side=tk.LEFT)
        self._dow_var = tk.StringVar(value=saved_dow)
        self._dow_combo = ttk.Combobox(dow_row, textvariable=self._dow_var,
                                       values=["MON","TUE","WED","THU","FRI","SAT","SUN"],
                                       width=6, state="readonly", font=fn)
        self._dow_combo.pack(side=tk.LEFT, padx=4)
        self._dow_row = dow_row

        cust_row = tk.Frame(body, bg=t["bg"])
        tk.Label(cust_row, text="Every:", font=fnb,
                 bg=t["bg"], fg=t["fg"], width=12, anchor=tk.W).pack(side=tk.LEFT)
        self._ndays_var = tk.StringVar(value=saved_ndays)
        tk.Entry(cust_row, textvariable=self._ndays_var, width=4,
                 font=fn, bg=t["entry_bg"], fg=t["entry_fg"]).pack(side=tk.LEFT, padx=4)
        tk.Label(cust_row, text="days", font=fn,
                 bg=t["bg"], fg=t["fg"]).pack(side=tk.LEFT)
        self._cust_row = cust_row

        time_row = tk.Frame(body, bg=t["bg"])
        time_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(time_row, text="At time:", font=fnb,
                 bg=t["bg"], fg=t["fg"], width=12, anchor=tk.W).pack(side=tk.LEFT)
        self._hour_var = tk.StringVar(value=saved_hour)
        self._min_var  = tk.StringVar(value=saved_min)
        ttk.Combobox(time_row, textvariable=self._hour_var,
                     values=[f"{h:02d}" for h in range(24)],
                     width=4, state="readonly", font=fn).pack(side=tk.LEFT, padx=4)
        tk.Label(time_row, text=":", font=fnb, bg=t["bg"], fg=t["fg"]).pack(side=tk.LEFT)
        ttk.Combobox(time_row, textvariable=self._min_var,
                     values=["00","15","30","45"],
                     width=4, state="readonly", font=fn).pack(side=tk.LEFT, padx=4)

        ttk.Separator(body).pack(fill=tk.X, pady=(8, 6))
        winotify_ok = self._check_winotify()
        if winotify_ok:
            dep_color = CONSOLE_COLORS[theme_name]["green"]
            dep_text  = "✔  winotify installed — toast notifications ready."
        else:
            dep_color = CONSOLE_COLORS[theme_name]["yellow"]
            dep_text  = ("⚠  winotify not installed — toast will not appear.\n\n"
                         "Fix:  open a command prompt and run:\n"
                         "      pip install winotify\n\n"
                         "You can still schedule the task now; install winotify before\n"
                         "the reminder fires and it will work.")
        tk.Label(body, text=dep_text, font=fns, bg=t["bg"], fg=dep_color,
                 wraplength=440, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 4))

        self._on_freq_change()
        self.bind("<Escape>", lambda _: self.destroy())

    def _check_winotify(self):
        try:
            import winotify
            return True
        except ImportError:
            return False

    def _query_task_status(self):
        try:
            r = subprocess.run(
                ["schtasks", "/query", "/tn", self.TASK_NAME, "/fo", "LIST"],
                capture_output=True, text=True, timeout=8)
            if r.returncode != 0:
                return "Task not scheduled yet."
            lines = {k.strip(): v.strip()
                     for line in r.stdout.splitlines()
                     if ":" in line
                     for k, v in [line.split(":", 1)]}
            status   = lines.get("Status", "?")
            next_run = lines.get("Next Run Time", "?")
            last_run = lines.get("Last Run Time", "Never")
            last_res = lines.get("Last Result",   "?")
            run_as   = lines.get("Run As User",   "?")
            result_note = " ✔" if last_res == "0" else f" ✖ (code {last_res})"
            return (f"Task status: {status}  •  Run as: {run_as}\n"
                    f"Next run: {next_run}\n"
                    f"Last run: {last_run}{result_note if last_run != 'Never' else ''}")
        except Exception as e:
            return f"Could not query task: {e}"

    def _on_freq_change(self):
        freq = self._freq_var.get()
        if freq == "weekly":
            self._dow_row.pack(fill=tk.X, pady=(0, 8))
            self._cust_row.pack_forget()
        elif freq == "custom":
            self._dow_row.pack_forget()
            self._cust_row.pack(fill=tk.X, pady=(0, 8))
        else:
            self._dow_row.pack_forget()
            self._cust_row.pack_forget()

    def _python_exe(self):
        return find_python_exe()

    def _write_notifier_script(self):
        app_dir = self._app_dir
        script  = app_dir / "_wallpaper_remind.py"
        script.write_text(f'''\
#!/usr/bin/env python
"""Wallpaper change reminder — run by Windows Task Scheduler."""
import os, sys, datetime
APP_PATH = r"{self._app}"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_remind_log.txt")

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{{datetime.datetime.now():%Y-%m-%d %H:%M:%S}}  {{msg}}\\n")

def show_toast():
    log(f"Script started. USER={{os.environ.get('USERNAME','?')}} SESSION={{os.environ.get('SESSIONNAME','?')}}")
    try:
        from winotify import Notification, audio
        n = Notification(
            app_id   = "Windows PowerShell",
            title    = "Wallpaper Reminder",
            msg      = "Time to freshen your desktop wallpaper \\U0001f5bc",
            duration = "long",
            launch   = APP_PATH,
        )
        n.set_audio(audio.Default, loop=False)
        n.show()
        log("Toast shown OK.")
    except ImportError:
        log("FAILED: winotify not installed. Run: pip install winotify")
    except Exception as e:
        log(f"FAILED: {{e}}")

if __name__ == "__main__":
    show_toast()
''', encoding="utf-8")
        return script

    def _build_schtasks_cmd(self, notifier_script):
        freq     = self._freq_var.get()
        t_str    = f"{self._hour_var.get()}:{self._min_var.get()}"
        pythonw  = self._python_exe()
        username = __import__("os").environ.get("USERNAME", "")
        tr = f'"{pythonw}" "{notifier_script}"'
        base = ["schtasks", "/create", "/f",
                "/tn", self.TASK_NAME,
                "/tr", tr,
                "/st", t_str,
                "/rl", "LIMITED",
                "/it",
                "/ru", username]
        if freq == "daily":
            base += ["/sc", "DAILY", "/mo", "1"]
        elif freq == "weekly":
            base += ["/sc", "WEEKLY", "/d", self._dow_var.get(), "/mo", "1"]
        else:
            try:
                n = max(1, int(self._ndays_var.get()))
            except ValueError:
                n = 7
            base += ["/sc", "DAILY", "/mo", str(n)]
        return base

    def _save_settings(self):
        self._cfg.set("reminder_freq",  self._freq_var.get())
        self._cfg.set("reminder_dow",   self._dow_var.get())
        self._cfg.set("reminder_ndays", self._ndays_var.get())
        self._cfg.set("reminder_hour",  self._hour_var.get())
        self._cfg.set("reminder_min",   self._min_var.get())

    def _schedule(self):
        try:
            notifier = self._write_notifier_script()
        except Exception as e:
            messagebox.showerror("Error writing notifier",
                f"Could not write helper script:\n{e}", parent=self)
            return
        cmd = self._build_schtasks_cmd(notifier)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self._save_settings()
                self.result = "set"
                query = subprocess.run(
                    ["schtasks", "/query", "/tn", self.TASK_NAME, "/fo", "LIST"],
                    capture_output=True, text=True)
                detail = query.stdout.strip() if query.returncode == 0 else ""
                messagebox.showinfo("Reminder Scheduled",
                    f"Task scheduled — use 'Test Toast Now' to verify.\n\n"
                    f"Script: {notifier}\n"
                    f"Python: {self._python_exe()}\n\n"
                    f"{detail}", parent=self)
                self.destroy()
            else:
                messagebox.showerror("Scheduler Error",
                    f"schtasks command:\n{' '.join(cmd)}\n\n"
                    f"Error:\n{result.stderr or result.stdout}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _test_toast(self):
        try:
            notifier = self._write_notifier_script()
            pythonw  = self._python_exe()
            subprocess.Popen(
                [pythonw, str(notifier)],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            time.sleep(3)
            err_log = self._app_dir / "_remind_error.txt"
            if err_log.exists():
                err = err_log.read_text(encoding="utf-8", errors="replace").strip()
                err_log.unlink()
                messagebox.showerror("Toast Failed",
                    f"The notifier ran but hit an error:\n\n{err}\n\n"
                    f"Python used: {pythonw}\nScript: {notifier}", parent=self)
            else:
                messagebox.showinfo("Test Fired",
                    "Notifier ran — did a toast appear?\n\n"
                    "Check the bottom-right corner or Action Center (bell icon).\n\n"
                    f"Python: {pythonw}\nScript: {notifier}", parent=self)
        except Exception as e:
            messagebox.showerror("Test Failed", str(e), parent=self)

    def _show_log(self):
        log_path = self._app_dir / "_remind_log.txt"
        if not log_path.exists():
            messagebox.showinfo("Reminder Log",
                f"No log file found yet.\nExpected:\n{log_path}", parent=self)
            return
        content = log_path.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            messagebox.showinfo("Reminder Log", "Log file is empty.", parent=self)
            return
        t = THEMES.get(self._theme, THEMES["dark"])
        dlg = tk.Toplevel(self)
        dlg.title("Reminder Run Log")
        dlg.geometry("700x400")
        dlg.grab_set()
        dlg.configure(bg=t["bg"])
        txt = scrolledtext.ScrolledText(dlg, font=("Consolas", 9), wrap=tk.WORD,
                                        bg=t["entry_bg"], fg=t["fg"])
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt.insert(tk.END, content)
        txt.config(state=tk.DISABLED)
        c = BTN_COLORS["danger"]
        br = tk.Frame(dlg, bg=t["bg"])
        br.pack(fill=tk.X, padx=8, pady=(0, 8))
        tk.Button(br, text="Clear Log", bg=c["bg"], fg=c["fg"],
                  command=lambda: (log_path.unlink(), dlg.destroy())).pack(side=tk.LEFT)
        tk.Button(br, text="Close", bg=t["btn_bg"], fg=t["btn_fg"],
                  command=dlg.destroy).pack(side=tk.RIGHT)

    def _remove(self):
        try:
            subprocess.run(
                ["schtasks", "/delete", "/f", "/tn", self.TASK_NAME],
                capture_output=True, text=True)
            self.result = "removed"
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
