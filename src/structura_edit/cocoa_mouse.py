import atexit
import ctypes
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QPointF
from PySide6.QtWidgets import QApplication


class CocoaMouse(QAbstractNativeEventFilter):
    def __init__(self, view):
        super().__init__()
        self.view = view
        self.active = False
        self.pending = QPointF()
        self.started = 0.0
        self.objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        self.graphics = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        self.objc.sel_registerName.argtypes = [ctypes.c_char_p]
        self.objc.sel_registerName.restype = ctypes.c_void_p
        self.objc.objc_getClass.argtypes = [ctypes.c_char_p]
        self.objc.objc_getClass.restype = ctypes.c_void_p
        signature = (ctypes.c_void_p, ctypes.c_void_p)
        self.send_integer = ctypes.CFUNCTYPE(ctypes.c_ulong, *signature)(("objc_msgSend", self.objc))
        self.send_double = ctypes.CFUNCTYPE(ctypes.c_double, *signature)(("objc_msgSend", self.objc))
        self.send_object = ctypes.CFUNCTYPE(ctypes.c_void_p, *signature)(("objc_msgSend", self.objc))
        self.selectors = {name: self.objc.sel_registerName(name.encode()) for name in ("type", "deltaX", "deltaY", "timestamp", "processInfo", "systemUptime")}
        self.process = self.send_object(self.objc.objc_getClass(b"NSProcessInfo"), self.selectors["processInfo"])
        self.associate = self.graphics.CGAssociateMouseAndMouseCursorPosition
        self.associate.argtypes = [ctypes.c_bool]
        self.associate.restype = ctypes.c_int32
        QApplication.instance().installNativeEventFilter(self)
        atexit.register(self.stop)

    def start(self):
        self.pending = QPointF()
        self.started = self.send_double(self.process, self.selectors["systemUptime"])
        self.active = self.associate(False) == 0
        return self.active

    def stop(self):
        if self.active:
            self.associate(True)
        self.active = False
        self.pending = QPointF()

    def sample(self):
        delta, self.pending = self.pending, QPointF()
        return delta

    def nativeEventFilter(self, event_type, message):
        if self.active and bytes(event_type) == b"mac_generic_NSEvent" and self.view.hasFocus() and self.view.window().isActiveWindow():
            event = int(message)
            kind = self.send_integer(event, self.selectors["type"])
            if kind in (5, 6, 7, 27) and self.send_double(event, self.selectors["timestamp"]) > self.started:
                self.pending += QPointF(self.send_double(event, self.selectors["deltaX"]),
                                        self.send_double(event, self.selectors["deltaY"]))
        return False

    def close(self):
        self.stop()
        QApplication.instance().removeNativeEventFilter(self)
        atexit.unregister(self.stop)


def relative_mouse(view):
    if sys.platform == "darwin" and QApplication.platformName() == "cocoa":
        return CocoaMouse(view)
    return None
