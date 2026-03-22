#!/usr/bin/env python
"""Wallpaper change reminder — run by Windows Task Scheduler."""
import os, sys, datetime
APP_PATH = r"C:\Users\my4nt\OneDrive\lucid24\py_tools\mp4_movie_and_image_tools\qigor_wallpaper\QiGor_Wallpaper_Manager.exe"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_remind_log.txt")

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")

def show_toast():
    log(f"Script started. USER={os.environ.get('USERNAME','?')} SESSION={os.environ.get('SESSIONNAME','?')}")
    try:
        from winotify import Notification, audio
        n = Notification(
            app_id   = "Windows PowerShell",
            title    = "Wallpaper Reminder",
            msg      = "Time to freshen your desktop wallpaper \U0001f5bc",
            duration = "long",
            launch   = APP_PATH,
        )
        n.set_audio(audio.Default, loop=False)
        n.show()
        log("Toast shown OK.")
    except ImportError:
        log("FAILED: winotify not installed. Run: pip install winotify")
    except Exception as e:
        log(f"FAILED: {e}")

if __name__ == "__main__":
    show_toast()
