import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from core.accessibility import request_accessibility_permission, open_accessibility_settings, FocusedAppTracker
from core.recognizer import HandwritingRecognizer
from gui.floating_panel import FloatingPanel

try:
    import Quartz
    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False

try:
    from Cocoa import NSApp, NSApplication
    HAS_COCOA = True
except ImportError:
    HAS_COCOA = False


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Ink")
    app.setOrganizationName("InkApp")

    if HAS_COCOA:
        NSApp.setActivationPolicy_(0)  # Regular (shows in dock temporarily)

    request_accessibility_permission()

    if HAS_COCOA:
        QTimer.singleShot(2000, lambda: NSApp.setActivationPolicy_(1))

    recognizer = HandwritingRecognizer()
    tracker = FocusedAppTracker()
    tracker.start()

    panel = FloatingPanel(recognizer, tracker=tracker)
    panel.set_recognition_delay(500)
    panel.set_auto_recognize(True)

    from PyQt6.QtGui import QGuiApplication
    screen = QGuiApplication.primaryScreen().geometry()
    panel_geo = panel.geometry()
    x = screen.width() - panel_geo.width() - 20
    y = screen.height() - panel_geo.height() - 60
    panel.move(x, y)

    panel.hide()

    def toggle_panel():
        if panel.isVisible():
            panel.hide()
        else:
            from Cocoa import NSWorkspace
            ws = NSWorkspace.sharedWorkspace()
            front = ws.frontmostApplication()
            if front and front.processIdentifier() != os.getpid():
                tracker.set_last_focused_pid(front.processIdentifier())
            panel.show()
            panel.raise_()
            panel.activateWindow()

    monitors = []
    if HAS_QUARTZ:
        def shortcut_handler(event):
            try:
                flags = event.modifierFlags()
                is_cmd = bool(flags & Quartz.NSCommandKeyMask)
                is_shift = bool(flags & Quartz.NSShiftKeyMask)
                keycode = event.keyCode()
                if is_cmd and is_shift and keycode == 34:
                    QTimer.singleShot(0, toggle_panel)
            except Exception:
                pass

        global_monitor = Quartz.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            Quartz.NSKeyDownMask | Quartz.NSSystemDefinedMask,
            shortcut_handler,
        )
        monitors.append(global_monitor)

        local_monitor = Quartz.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            Quartz.NSKeyDownMask | Quartz.NSSystemDefinedMask,
            shortcut_handler,
        )
        monitors.append(local_monitor)

    ret = app.exec()

    for m in monitors:
        Quartz.NSEvent.removeMonitor_(m)
    tracker.stop()

    sys.exit(ret)


if __name__ == "__main__":
    main()
