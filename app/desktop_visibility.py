"""Read window geometry without hooks, screen capture, or focus changes."""
import os
import sys


def covers_monitor(window, monitor, tolerance=2):
    return (window[0] <= monitor[0]+tolerance and window[1] <= monitor[1]+tolerance
            and window[2] >= monitor[2]-tolerance and window[3] >= monitor[3]-tolerance)


def mac_fullscreen_window(frontmost_pid, windows, monitors, own_pid=None):
    """CGWindow bounds and CGDisplay bounds share the same coordinate space."""
    if not frontmost_pid or frontmost_pid == (os.getpid() if own_pid is None else own_pid):
        return False
    for window in windows:
        if (window.get('kCGWindowOwnerPID') != frontmost_pid
                or window.get('kCGWindowLayer', 0) != 0
                or window.get('kCGWindowAlpha', 1) <= .05
                or not window.get('kCGWindowIsOnscreen', True)):
            continue
        bounds = window.get('kCGWindowBounds') or {}
        x, y = bounds.get('X', 0), bounds.get('Y', 0)
        width, height = bounds.get('Width', 0), bounds.get('Height', 0)
        if width < 100 or height < 100:
            continue
        frame = (x, y, x+width, y+height)
        if any(covers_monitor(frame, monitor) for monitor in monitors):
            return True
    return False


class _MacDesktop:
    """Small Objective-C/CoreGraphics bridge using system frameworks only."""
    def __init__(self):
        import ctypes as c
        import plistlib
        self.c, self.plistlib = c, plistlib
        self.appkit = c.CDLL('/System/Library/Frameworks/AppKit.framework/AppKit')
        self.objc = c.CDLL('/usr/lib/libobjc.A.dylib')
        self.objc.objc_getClass.argtypes = [c.c_char_p]
        self.objc.objc_getClass.restype = c.c_void_p
        self.objc.sel_registerName.argtypes = [c.c_char_p]
        self.objc.sel_registerName.restype = c.c_void_p
        self.msg = c.CFUNCTYPE(c.c_void_p, c.c_void_p, c.c_void_p)(('objc_msgSend', self.objc))
        self.msg_int = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_void_p)(('objc_msgSend', self.objc))
        self.msg_bool = c.CFUNCTYPE(c.c_bool, c.c_void_p, c.c_void_p)(('objc_msgSend', self.objc))
        self.msg_long = c.CFUNCTYPE(c.c_long, c.c_void_p, c.c_void_p)(('objc_msgSend', self.objc))
        self.msg_count = c.CFUNCTYPE(c.c_ulong, c.c_void_p, c.c_void_p)(('objc_msgSend', self.objc))
        self.msg_index = c.CFUNCTYPE(c.c_void_p, c.c_void_p, c.c_void_p, c.c_ulong)(('objc_msgSend', self.objc))
        self.msg_flags = c.CFUNCTYPE(None, c.c_void_p, c.c_void_p, c.c_ulong)(('objc_msgSend', self.objc))
        self.msg_set_bool = c.CFUNCTYPE(None, c.c_void_p, c.c_void_p, c.c_bool)(('objc_msgSend', self.objc))
        self.msg_arg = c.CFUNCTYPE(c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p)(('objc_msgSend', self.objc))
        self.msg_date = c.CFUNCTYPE(c.c_void_p, c.c_void_p, c.c_void_p, c.c_double)(('objc_msgSend', self.objc))
        self.cg = c.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        self.cf = c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.cg.CGWindowListCopyWindowInfo.argtypes = [c.c_uint32, c.c_uint32]
        self.cg.CGWindowListCopyWindowInfo.restype = c.c_void_p
        self.cf.CFPropertyListCreateData.argtypes = [c.c_void_p, c.c_void_p, c.c_long, c.c_ulong, c.POINTER(c.c_void_p)]
        self.cf.CFPropertyListCreateData.restype = c.c_void_p
        self.cf.CFDataGetLength.argtypes = [c.c_void_p]
        self.cf.CFDataGetLength.restype = c.c_long
        self.cf.CFDataGetBytePtr.argtypes = [c.c_void_p]
        self.cf.CFDataGetBytePtr.restype = c.c_void_p
        self.cf.CFRelease.argtypes = [c.c_void_p]
        self.cf.CFRelease.restype = None
        class Point(c.Structure):
            _fields_ = [('x', c.c_double), ('y', c.c_double)]
        class Size(c.Structure):
            _fields_ = [('width', c.c_double), ('height', c.c_double)]
        class Rect(c.Structure):
            _fields_ = [('origin', Point), ('size', Size)]
        self.cg.CGDisplayBounds.argtypes = [c.c_uint32]
        self.cg.CGDisplayBounds.restype = Rect
        self.cg.CGGetActiveDisplayList.argtypes = [c.c_uint32, c.POINTER(c.c_uint32), c.POINTER(c.c_uint32)]
        self.cg.CGGetActiveDisplayList.restype = c.c_int32

    def sel(self, name):
        return self.objc.sel_registerName(name.encode('ascii'))

    def pool(self):
        return self.msg(self.objc.objc_getClass(b'NSAutoreleasePool'), self.sel('new'))

    def workspace(self):
        return self.msg(self.objc.objc_getClass(b'NSWorkspace'), self.sel('sharedWorkspace'))

    def bundle_ids(self):
        pool = self.pool()
        try:
            # NSWorkspace refreshes its application list when the main run loop runs.
            # The opt-in monitor has no Qt event loop of its own.
            date = self.msg_date(self.objc.objc_getClass(b'NSDate'), self.sel('dateWithTimeIntervalSinceNow:'), .001)
            loop = self.msg(self.objc.objc_getClass(b'NSRunLoop'), self.sel('mainRunLoop'))
            self.msg_arg(loop, self.sel('runUntilDate:'), date)
            apps = self.msg(self.workspace(), self.sel('runningApplications'))
            result = set()
            for index in range(self.msg_count(apps, self.sel('count'))):
                app = self.msg_index(apps, self.sel('objectAtIndex:'), index)
                bundle = self.msg(app, self.sel('bundleIdentifier'))
                raw = self.msg(bundle, self.sel('UTF8String')) if bundle else None
                if raw:
                    result.add(self.c.string_at(raw).decode('utf-8'))
            return result
        finally:
            self.msg(pool, self.sel('drain'))

    def frontmost_pid(self):
        pool = self.pool()
        try:
            app = self.msg(self.workspace(), self.sel('frontmostApplication'))
            return self.msg_int(app, self.sel('processIdentifier')) if app else None
        finally:
            self.msg(pool, self.sel('drain'))

    def windows(self):
        # Window metadata only: no screen pixels or accessibility access.
        values = self.cg.CGWindowListCopyWindowInfo(1 | 16, 0)
        if not values:
            return []
        data, error = None, self.c.c_void_p()
        try:
            data = self.cf.CFPropertyListCreateData(None, values, 200, 0, self.c.byref(error))
            if not data:
                return []
            raw = self.c.string_at(self.cf.CFDataGetBytePtr(data), self.cf.CFDataGetLength(data))
            return self.plistlib.loads(raw)
        finally:
            if data:
                self.cf.CFRelease(data)
            if error.value:
                self.cf.CFRelease(error)
            self.cf.CFRelease(values)

    def monitors(self):
        displays = (self.c.c_uint32 * 32)()
        count = self.c.c_uint32()
        if self.cg.CGGetActiveDisplayList(32, displays, self.c.byref(count)) != 0:
            return []
        result = []
        for identifier in displays[:count.value]:
            bounds = self.cg.CGDisplayBounds(identifier)
            x, y = bounds.origin.x, bounds.origin.y
            result.append((x, y, x+bounds.size.width, y+bounds.size.height))
        return result

    def configure_window(self, view_id):
        # QWidget.winId() is the Cocoa NSView*, not an NSWindow*.
        if not view_id:
            return
        window = self.msg(int(view_id), self.sel('window'))
        if window:
            behavior = self.msg_count(window, self.sel('collectionBehavior'))
            self.msg_flags(window, self.sel('setCollectionBehavior:'), (behavior & ~2 & ~128) | 1 | 256)
            # Tool windows are NSPanel instances, which otherwise may disappear
            # as soon as another app receives focus. This touches only our panel.
            self.msg_set_bool(window, self.sel('setHidesOnDeactivate:'), False)

    def window_status(self, view_id):
        if not view_id:
            return {}
        window = self.msg(int(view_id), self.sel('window'))
        if not window:
            return {}
        return {
            'windowNumber': self.msg_long(window, self.sel('windowNumber')),
            'isVisible': bool(self.msg_bool(window, self.sel('isVisible'))),
            'isOnActiveSpace': bool(self.msg_bool(window, self.sel('isOnActiveSpace'))),
            'hidesOnDeactivate': bool(self.msg_bool(window, self.sel('hidesOnDeactivate'))),
            'level': self.msg_long(window, self.sel('level')),
        }


_mac_desktop = None


def _get_mac_desktop():
    global _mac_desktop
    if _mac_desktop is None:
        _mac_desktop = _MacDesktop()
    return _mac_desktop


def mac_running_bundle_ids():
    if sys.platform != 'darwin':
        return set()
    return _get_mac_desktop().bundle_ids()


def _cocoa_windows_available():
    try:
        from PySide6.QtGui import QGuiApplication
    except ImportError:
        return False
    application = QGuiApplication.instance()
    return application is not None and application.platformName() == 'cocoa'


def configure_macos_window(win_id):
    # Offscreen Qt platforms use synthetic IDs that are not Objective-C objects.
    if sys.platform == 'darwin' and win_id and _cocoa_windows_available():
        try:
            _get_mac_desktop().configure_window(win_id)
        except (OSError, ValueError, RuntimeError):
            pass


def mac_window_status(win_id):
    """Inspect this Qt window's NSWindow flags, never other desktop content."""
    if sys.platform == 'darwin' and win_id and _cocoa_windows_available():
        try:
            return _get_mac_desktop().window_status(win_id)
        except (OSError, ValueError, RuntimeError):
            pass
    return {}


class FullscreenDetector:
    def __init__(self):
        self.user32 = None
        self.mac = None
        if sys.platform == 'darwin':
            try:
                self.mac = _get_mac_desktop()
            except (OSError, ValueError, RuntimeError):
                pass
            return
        if sys.platform != 'win32':
            return
        import ctypes
        from ctypes import wintypes as w
        self.ctypes, self.w = ctypes, w
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        u = self.user32
        u.GetForegroundWindow.restype = w.HWND
        u.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        u.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
        u.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
        u.IsWindowVisible.argtypes = [w.HWND]
        u.IsIconic.argtypes = [w.HWND]
        u.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
        u.MonitorFromWindow.restype = w.HANDLE
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('cbSize', w.DWORD), ('rcMonitor', w.RECT), ('rcWork', w.RECT), ('dwFlags', w.DWORD)]
        self.MonitorInfo = MonitorInfo
        u.GetMonitorInfoW.argtypes = [w.HANDLE, ctypes.POINTER(MonitorInfo)]

    def active(self):
        if self.mac is not None:
            try:
                return mac_fullscreen_window(self.mac.frontmost_pid(), self.mac.windows(), self.mac.monitors())
            except (OSError, ValueError, RuntimeError):
                return False
        if self.user32 is None:
            return False
        c, w, u = self.ctypes, self.w, self.user32
        hwnd = u.GetForegroundWindow()
        if not hwnd or not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
            return False
        pid = w.DWORD()
        u.GetWindowThreadProcessId(hwnd, c.byref(pid))
        if pid.value == os.getpid():
            return False
        name = c.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, name, len(name))
        if name.value in ('Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'):
            return False
        rect, info = w.RECT(), self.MonitorInfo()
        info.cbSize = c.sizeof(info)
        if not u.GetWindowRect(hwnd, c.byref(rect)) or not u.GetMonitorInfoW(u.MonitorFromWindow(hwnd, 2), c.byref(info)):
            return False
        try:
            c.windll.dwmapi.DwmGetWindowAttribute(w.HWND(hwnd), 9, c.byref(rect), c.sizeof(rect))
        except OSError:
            pass
        m = info.rcMonitor
        return covers_monitor((rect.left,rect.top,rect.right,rect.bottom), (m.left,m.top,m.right,m.bottom))
