import ctypes
import ctypes.util
import time
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer

try:
    import Quartz
    from Quartz import (
        CGEventTapCreate, CGEventTapEnable, CGEventTapListRemove,
        CGEventMaskBit, CFMachPortCreateRunLoopSource, CFRunLoopGetCurrent,
        CFRunLoopAddSource, CFRunLoopRunInMode, kCFRunLoopDefaultMode,
        CGEventGetLocation, CGEventGetIntegerValueField,
        kCGEventTabletProximity, kCGEventLeftMouseDown, kCGEventLeftMouseUp,
        kCGEventLeftMouseDragged, kCGTabletPointEventDeviceID,
        kCGTabletPointEventX, kCGTabletPointEventY, kCGTabletPointEventPressure,
        kCGEventTabletProximityEnterProximity, kCGEventFieldTabletEventPointDeviceID,
        kCGHIDEventTap, kCGSessionEventTap,
        kCGEventFlagMaskAlternate, kCGEventFlagMaskCommand,
        CGEventGetFlags, CGEventSourceCreate, kCGEventSourceStateHIDSystemState,
        CGEventCreateKeyboardEvent, CGEventSetFlags, CGEventPost,
    )
    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False

try:
    from ApplicationServices import (
        AXIsProcessTrusted, AXIsProcessTrustedWithOptions,
        AXUIElementCreateSystemWide, AXUIElementCopyAttributeValue,
        kAXFocusedApplicationAttribute, kAXFocusedUIElementAttribute,
        kAXRoleAttribute, AXUIElementCreateApplication,
    )
    HAS_AX = True
except ImportError:
    HAS_AX = False


class TabletMonitor(QObject):
    stylus_proximity_changed = pyqtSignal(bool)
    stylus_position_changed = pyqtSignal(float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._tap = None
        self._run_loop_source = None
        self._thread: _TapThread | None = None

    def start(self) -> bool:
        if self._active:
            return True
        if not HAS_QUARTZ:
            return False
        if not AXIsProcessTrusted():
            opts = {AXIsProcessTrustedCheckOptionPrompt: True}
            AXIsProcessTrustedWithOptions(opts)
            return False

        mask = (
            CGEventMaskBit(kCGEventTabletProximity) |
            CGEventMaskBit(kCGEventLeftMouseDown) |
            CGEventMaskBit(kCGEventLeftMouseUp) |
            CGEventMaskBit(kCGEventLeftMouseDragged)
        )

        self._tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            0,
            mask,
            _tablet_event_callback,
            None,
        )

        if self._tap is None:
            return False

        self._run_loop_source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._thread = _TapThread(self._tap, self._run_loop_source, self)
        self._thread.proximity_changed.connect(self.stylus_proximity_changed.emit)
        self._thread.position_changed.connect(self.stylus_position_changed.emit)
        self._thread.start()
        self._active = True
        return True

    def stop(self):
        if self._thread:
            self._thread.stop()
            self._thread = None
        self._tap = None
        self._run_loop_source = None
        self._active = False

    def is_active(self) -> bool:
        return self._active


def _tablet_event_callback(proxy, event_type, event, user_info):
    try:
        if event_type == kCGEventTabletProximity:
            enter = CGEventGetIntegerValueField(event, kCGEventTabletProximityEnterProximity)
            _active_proximity[0] = bool(enter)
        elif event_type in (kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGEventLeftMouseDragged):
            flags = CGEventGetFlags(event)
            if flags & kCGEventFlagMaskCommand or flags & kCGEventFlagMaskAlternate:
                return event
            device_id = CGEventGetIntegerValueField(event, kCGTabletPointEventDeviceID)
            if device_id != 0:
                loc = CGEventGetLocation(event)
                x = loc.x
                y = loc.y
                pressure = CGEventGetIntegerValueField(event, kCGTabletPointEventPressure) / 255.0
                _last_position[0] = (x, y, pressure)
                _active_proximity[0] = True
    except Exception:
        pass
    return event


_active_proximity = [False]
_last_position = [(0.0, 0.0, 0.0)]


class _TapThread(QThread):
    proximity_changed = pyqtSignal(bool)
    position_changed = pyqtSignal(float, float, float)

    def __init__(self, tap, run_loop_source, parent=None):
        super().__init__(parent)
        self._tap = tap
        self._run_loop_source = run_loop_source
        self._running = True

    def run(self):
        rl = CFRunLoopGetCurrent()
        CFRunLoopAddSource(rl, self._run_loop_source, kCFRunLoopDefaultMode)
        CGEventTapEnable(self._tap, True)
        while self._running:
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.1, False)
            if _active_proximity[0]:
                self.proximity_changed.emit(True)
                x, y, p = _last_position[0]
                if x != 0 or y != 0:
                    self.position_changed.emit(x, y, p)
            elif _active_proximity[0] is False and self.proximity_changed.receivers() > 0:
                self.proximity_changed.emit(False)

    def stop(self):
        self._running = False
        self.wait(1000)
