"""
tooltip.py  —  QiGor Wallpaper Manager
600ms hover tooltip widget.
"""
import tkinter as tk


class Tooltip:
    """600 ms hover tooltip. Usage: Tooltip(widget, 'explanation text')"""
    _delay = 600

    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        self._id = self._win = None
        widget.bind("<Enter>",   self._schedule)
        widget.bind("<Leave>",   self._cancel)
        widget.bind("<Button>",  self._cancel)
        widget.bind("<Destroy>", self._cancel)

    def _schedule(self, _=None):
        self._cancel()
        self._id = self.widget.after(self._delay, self._show)

    def _cancel(self, _=None):
        if self._id:  self.widget.after_cancel(self._id); self._id = None
        if self._win: self._win.destroy(); self._win = None

    def _show(self):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._win = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, justify=tk.LEFT,
                 background="#ffffe0", foreground="#000000",
                 relief=tk.SOLID, borderwidth=1,
                 font=("Segoe UI", 9), wraplength=360, padx=6, pady=4).pack()
