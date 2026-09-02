"""
shortcuts.py  —  create Windows .lnk files with nothing but ctypes.

Why not PowerShell's `New-Object -ComObject WScript.Shell`, which is the usual
one-liner for this: under Smart App Control, PowerShell drops into Constrained
Language Mode, and CLM blocks exactly that call. The whole point of this
distribution is to work on an enforcing machine, so the shortcut has to be built
through COM directly. `ctypes` is stdlib, needs no wheel, and loads no unsigned
DLL of ours.

Why not pywin32: it would work (unsigned .pyd extensions do import under Smart
App Control), but it is a 10 MB dependency for one COM call.

The vtable is walked by slot index because plain ctypes has no IDL. The slot
numbers below are the documented IShellLinkW / IPersistFile layouts and are
fixed by COM's binary compatibility rules — they cannot change.
"""
import ctypes
from ctypes import POINTER, byref, c_void_p, c_wchar_p, c_long, c_ulong
from pathlib import Path

from .paths import _GUID, guid

_ole32 = ctypes.windll.ole32

CLSCTX_INPROC_SERVER     = 0x1
COINIT_APARTMENTTHREADED = 0x2
SW_SHOWNORMAL            = 1

_CLSID_ShellLink  = "{00021401-0000-0000-C000-000000000046}"
_IID_IShellLinkW  = "{000214F9-0000-0000-C000-000000000046}"
_IID_IPersistFile = "{0000010B-0000-0000-C000-000000000046}"

# IUnknown
_QUERY_INTERFACE = 0
_RELEASE         = 2
# IShellLinkW
_SET_DESCRIPTION       = 7
_SET_WORKING_DIRECTORY = 9
_SET_ARGUMENTS         = 11
_SET_SHOW_CMD          = 15
_SET_ICON_LOCATION     = 17
_SET_PATH              = 20
# IPersistFile
_SAVE = 6


def _call(ptr, slot, *argtypes):
    """Bind vtable slot `slot` on the COM pointer `ptr` as an HRESULT function.

    restype is c_long rather than ctypes.HRESULT on purpose: HRESULT makes
    ctypes raise its own OSError on failure, which loses the name of the call
    that failed and makes the failure much harder to read in a bug report.
    """
    vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
    return ctypes.WINFUNCTYPE(c_long, c_void_p, *argtypes)(vtbl[slot])


def _release(ptr):
    vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
    ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl[_RELEASE])(ptr)


def _check(hr, what):
    if hr < 0:
        raise OSError("{} failed: 0x{:08X}".format(what, hr & 0xFFFFFFFF))


def create_shortcut(link_path, target, arguments="", working_dir=None,
                    icon=None, icon_index=0, description=""):
    """
    Write a .lnk at `link_path` pointing at `target`.

    `link_path`'s parent is created if missing. Raises OSError with the failing
    COM call named if anything goes wrong.
    """
    link_path = Path(link_path)
    link_path.parent.mkdir(parents=True, exist_ok=True)

    # S_FALSE (already initialised) and RPC_E_CHANGED_MODE (the caller picked a
    # different apartment) are both fine — we only need *an* initialised
    # apartment on this thread, not this particular one.
    _ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)

    psl = c_void_p()
    clsid = guid(_CLSID_ShellLink)
    iid   = guid(_IID_IShellLinkW)
    _check(_ole32.CoCreateInstance(byref(clsid), None, CLSCTX_INPROC_SERVER,
                                   byref(iid), byref(psl)),
           "CoCreateInstance(ShellLink)")
    try:
        _check(_call(psl, _SET_PATH, c_wchar_p)(psl, str(target)), "SetPath")
        _check(_call(psl, _SET_SHOW_CMD, ctypes.c_int)(psl, SW_SHOWNORMAL),
               "SetShowCmd")
        if arguments:
            _check(_call(psl, _SET_ARGUMENTS, c_wchar_p)(psl, str(arguments)),
                   "SetArguments")
        if working_dir:
            _check(_call(psl, _SET_WORKING_DIRECTORY, c_wchar_p)(
                psl, str(working_dir)), "SetWorkingDirectory")
        if description:
            # Explorer truncates the tooltip past 260 chars and older shells
            # reject a longer string outright.
            _check(_call(psl, _SET_DESCRIPTION, c_wchar_p)(
                psl, str(description)[:259]), "SetDescription")
        if icon and Path(icon).exists():
            _check(_call(psl, _SET_ICON_LOCATION, c_wchar_p, ctypes.c_int)(
                psl, str(icon), icon_index), "SetIconLocation")

        ppf = c_void_p()
        iid_pf = guid(_IID_IPersistFile)
        _check(_call(psl, _QUERY_INTERFACE, POINTER(_GUID), POINTER(c_void_p))(
            psl, byref(iid_pf), byref(ppf)), "QueryInterface(IPersistFile)")
        try:
            # fRemember=False: we are writing a fresh file, not adopting it as
            # the object's current document.
            _check(_call(ppf, _SAVE, c_wchar_p, ctypes.c_int)(
                ppf, str(link_path), 0), "IPersistFile::Save")
        finally:
            _release(ppf)
    finally:
        _release(psl)

    return link_path


def remove_shortcut(link_path) -> bool:
    """Delete a .lnk if present. Returns True if something was removed."""
    p = Path(link_path)
    try:
        if p.exists():
            p.unlink()
            return True
    except OSError:
        pass
    return False
