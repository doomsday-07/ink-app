import os
import subprocess
import time
from typing import Optional

try:
    import ApplicationServices as AX
    import Cocoa
    import Quartz
    HAS_AX = True
except ImportError:
    HAS_AX = False


def is_accessibility_available() -> bool:
    return HAS_AX


def is_accessibility_enabled() -> bool:
    if not HAS_AX:
        return False
    return AX.AXIsProcessTrusted()


def request_accessibility_permission():
    if not HAS_AX:
        return False
    opts = {AX.kAXTrustedCheckOptionPrompt: True}
    return AX.AXIsProcessTrustedWithOptions(opts)


def open_accessibility_settings():
    subprocess.run([
        "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    ])


def get_focused_app_pid() -> Optional[int]:
    if not HAS_AX:
        return None
    try:
        ws = Cocoa.NSWorkspace.sharedWorkspace()
        front_app = ws.frontmostApplication()
        if front_app is None:
            return None
        return front_app.processIdentifier()
    except Exception:
        return None


def get_focused_ui_element(pid: int = None):
    if not HAS_AX:
        return None
    if pid is None:
        pid = get_focused_app_pid()
    if pid is None:
        return None
    app_element = AX.AXUIElementCreateApplication(pid)
    result = AX.AXUIElementCopyAttributeValue(app_element, AX.kAXFocusedUIElementAttribute, None)
    if result[0] != AX.kAXErrorSuccess or result[1] is None:
        return None
    return result[1]


def get_element_role(element) -> Optional[str]:
    if not HAS_AX or element is None:
        return None
    result = AX.AXUIElementCopyAttributeValue(element, AX.kAXRoleAttribute, None)
    if result[0] != AX.kAXErrorSuccess or result[1] is None:
        return None
    return str(result[1])


def get_element_value(element) -> Optional[str]:
    if not HAS_AX or element is None:
        return None
    result = AX.AXUIElementCopyAttributeValue(element, AX.kAXValueAttribute, None)
    if result[0] != AX.kAXErrorSuccess or result[1] is None:
        return None
    return str(result[1])


def set_element_value(element, value: str) -> bool:
    if not HAS_AX or element is None:
        return False
    result = AX.AXUIElementSetAttributeValue(element, AX.kAXValueAttribute, value)
    return result == AX.kAXErrorSuccess


def is_text_field(element) -> bool:
    if not HAS_AX or element is None:
        return False
    role = get_element_role(element)
    return role in ("AXTextField", "AXTextArea", "AXComboBox", "AXSearchField", "AXSecureTextField")


def activate_app(pid: int):
    if not HAS_AX or pid is None:
        return
    try:
        app_element = AX.AXUIElementCreateApplication(pid)
        AX.AXUIElementPerformAction(app_element, "AXRaise")
    except Exception:
        pass
    try:
        ws = Cocoa.NSWorkspace.sharedWorkspace()
        for app in ws.runningApplications():
            if app.processIdentifier() == pid:
                app.activateWithOptions_(
                    Cocoa.NSApplicationActivateIgnoringOtherApps
                )
                break
    except Exception:
        pass


def inject_text(text: str, method: str = "auto") -> bool:
    if not text:
        return False
    pid = get_focused_app_pid()
    if pid is None:
        return _inject_via_clipboard(text)
    return _inject_via_clipboard(text, target_pid=pid)


def _inject_via_clipboard(text: str, target_pid: int = None) -> bool:
    try:
        pasteboard = Cocoa.NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(text, Cocoa.NSPasteboardTypeString)
        time.sleep(0.05)
        return _simulate_paste(target_pid)
    except Exception:
        return False


def _simulate_paste(target_pid: int = None) -> bool:
    try:
        if target_pid is not None:
            activate_app(target_pid)
            time.sleep(0.1)
        source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        key_down = Quartz.CGEventCreateKeyboardEvent(source, 9, True)
        key_up = Quartz.CGEventCreateKeyboardEvent(source, 9, False)
        Quartz.CGEventSetFlags(key_down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventSetFlags(key_up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_down)
        time.sleep(0.03)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_up)
        return True
    except Exception:
        return False


def get_focused_element_for_pid(pid: int):
    if not HAS_AX or pid is None:
        return None
    try:
        app_element = AX.AXUIElementCreateApplication(pid)
        result = AX.AXUIElementCopyAttributeValue(app_element, AX.kAXFocusedUIElementAttribute, None)
        if result[0] != AX.kAXErrorSuccess or result[1] is None:
            return None
        return result[1]
    except Exception:
        return None


def inject_via_ax(element, text: str) -> bool:
    if not HAS_AX or element is None:
        return False
    try:
        current = get_element_value(element)
        if current and current.strip():
            text = current + " " + text
        result = AX.AXUIElementSetAttributeValue(element, AX.kAXValueAttribute, text)
        if result == AX.kAXErrorSuccess:
            return True
    except Exception:
        pass
    return False


def simulate_backspace():
    if not HAS_AX:
        return
    try:
        source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        key_down = Quartz.CGEventCreateKeyboardEvent(source, 51, True)
        key_up = Quartz.CGEventCreateKeyboardEvent(source, 51, False)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_up)
    except Exception:
        pass


def simulate_space():
    if not HAS_AX:
        return
    try:
        source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        key_down = Quartz.CGEventCreateKeyboardEvent(source, 49, True)
        key_up = Quartz.CGEventCreateKeyboardEvent(source, 49, False)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_up)
    except Exception:
        pass


class FocusedAppTracker:
    def __init__(self):
        self._last_focused_pid: Optional[int] = None
        self._my_pid = os.getpid()
        self._timer = None

    def start(self):
        if self._timer is not None or not HAS_AX:
            return
        self._poll()
        from PyQt6.QtCore import QTimer
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll)
        self._timer.start(150)

    def stop(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _poll(self):
        try:
            ws = Cocoa.NSWorkspace.sharedWorkspace()
            front = ws.frontmostApplication()
            if front:
                pid = front.processIdentifier()
                if pid != self._my_pid:
                    self._last_focused_pid = pid
        except Exception:
            pass

    def get_last_focused_pid(self) -> Optional[int]:
        if self._last_focused_pid is not None:
            return self._last_focused_pid
        return get_focused_app_pid()

    def set_last_focused_pid(self, pid: int):
        self._last_focused_pid = pid
