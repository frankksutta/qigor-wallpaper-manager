"""
remind_headless.py  —  QiGor Wallpaper Manager
Headless reminder toast — called via  exe --remind  by Task Scheduler.
No GUI, no tkinter. Just fires the toast and exits.
"""
import sys
from pathlib import Path

from .constants import HELPERS_DIR, APP_NAME


def show_reminder_toast():
    """Fire a winotify toast notification. Logs result to helpers/."""
    import datetime as _dt

    log_file = HELPERS_DIR / "_remind_log.txt"
    HELPERS_DIR.mkdir(parents=True, exist_ok=True)

    def log(msg):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S") +
                    "  " + str(msg) + "\n")

    # Determine launch path for clicking the toast
    if getattr(sys, "frozen", False):
        launch_path = sys.executable
    else:
        launch_path = str(Path(sys.argv[0]).resolve())

    log("Reminder --remind started. launch={}".format(launch_path))

    try:
        from winotify import Notification, audio
        toast = Notification(
            app_id="Windows PowerShell",   # confirmed working app_id
            title="Wallpaper Reminder",
            msg="Time to freshen your desktop wallpaper \U0001f5bc",
            duration="long",
            launch=launch_path,
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        log("Toast shown OK.")
    except ImportError:
        log("FAILED: winotify not installed.  pip install winotify")
    except Exception as e:
        log("FAILED: " + str(e))
