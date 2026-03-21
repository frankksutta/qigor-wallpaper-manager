#!/usr/bin/env python
"""Lock screen helper — launched elevated by QiGor Wallpaper Manager.
Writes or deletes PersonalizationCSP registry key and exits."""
import sys, winreg, datetime, os

MODE     = "set"
IMG_PATH = r"C:\Users\my4nt\.qigor-wallpaper\saved_wallpapers\9siv-evam-2k.png"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_lockscreen_helper_log.txt")

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")

CSP_ROOT = winreg.HKEY_LOCAL_MACHINE
CSP_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP"

def set_lock_screen(path):
    try:
        try:
            key = winreg.OpenKey(CSP_ROOT, CSP_PATH, 0,
                                 winreg.KEY_SET_VALUE | winreg.KEY_CREATE_SUB_KEY)
        except FileNotFoundError:
            key = winreg.CreateKey(CSP_ROOT, CSP_PATH)
        winreg.SetValueEx(key, "LockScreenImagePath",   0, winreg.REG_SZ, path)
        winreg.SetValueEx(key, "LockScreenImageUrl",    0, winreg.REG_SZ, path)
        winreg.SetValueEx(key, "LockScreenImageStatus", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        log(f"SET OK: {path}")
    except Exception as e:
        log(f"SET FAILED: {e}")
        sys.exit(1)

def release_lock_screen():
    try:
        try:
            key = winreg.OpenKey(CSP_ROOT, CSP_PATH, 0,
                                 winreg.KEY_SET_VALUE | winreg.KEY_CREATE_SUB_KEY)
            for val in ("LockScreenImagePath", "LockScreenImageUrl",
                        "LockScreenImageStatus"):
                try:
                    winreg.DeleteValue(key, val)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except FileNotFoundError:
            pass
        try:
            winreg.DeleteKey(CSP_ROOT,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP")
        except Exception:
            pass
        log("RELEASE OK")
    except Exception as e:
        log(f"RELEASE FAILED: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if MODE == "release":
        release_lock_screen()
    else:
        set_lock_screen(IMG_PATH)
