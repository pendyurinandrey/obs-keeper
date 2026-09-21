"""macOS-only helper: bring the app to the front.

A menu-bar click does not make a Python process the active application, so ``raise_()`` /
``activateWindow()`` alone may leave the window behind other apps. Failures are ignored: this is
a nicety on top of Qt's own activation.
"""

import ctypes
import ctypes.util
import sys


def activate_app() -> None:
    if sys.platform != "darwin":
        return
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        c_void_p = ctypes.c_void_p

        def sel(name: bytes):
            return objc.sel_registerName(name)

        get_object = ctypes.CFUNCTYPE(c_void_p, c_void_p, c_void_p)(("objc_msgSend", objc))
        responds = ctypes.CFUNCTYPE(ctypes.c_bool, c_void_p, c_void_p, c_void_p)(("objc_msgSend", objc))
        call = ctypes.CFUNCTYPE(None, c_void_p, c_void_p)(("objc_msgSend", objc))
        call_bool = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, ctypes.c_bool)(("objc_msgSend", objc))

        app = get_object(objc.objc_getClass(b"NSApplication"), sel(b"sharedApplication"))
        if responds(app, sel(b"respondsToSelector:"), sel(b"activate")):  # macOS 14+
            call(app, sel(b"activate"))
        else:
            call_bool(app, sel(b"activateIgnoringOtherApps:"), True)
    except Exception:  # noqa: BLE001 - purely cosmetic
        pass
