import sys
import subprocess
import tempfile
import os
from pathlib import Path
from PyQt6.QtWidgets import QWidget, QApplication, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QCursor, QPixmap, QGuiApplication, QScreen


class ScreenSnipOverlay(QWidget):
    """Fullscreen transparent overlay for screen region selection."""

    region_selected = pyqtSignal(QPixmap, QRect)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screen Snip")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

        self._start: QPoint | None = None
        self._end: QPoint | None = None
        self._full_screenshot: QPixmap | None = None
        self._region_rect: QRect | None = None

    def start_capture(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        self._full_screenshot = screen.grabWindow(0)
        self.setGeometry(screen.geometry())
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._full_screenshot:
            painter.drawPixmap(0, 0, self._full_screenshot)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

        if self._start and self._end:
            rect = QRect(self._start, self._end).normalized()
            painter.setClipRect(rect)
            if self._full_screenshot:
                painter.drawPixmap(0, 0, self._full_screenshot)
            painter.setClipping(False)
            painter.setPen(QPen(QColor(33, 150, 243), 2))
            painter.drawRect(rect)

        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawText(self.rect().adjusted(10, 10, -10, -10),
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                         "Drag to select a region. Press Escape to cancel.")

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.pos()
            self._end = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self._start:
            self._end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._start:
            self._end = event.pos()
            rect = QRect(self._start, self._end).normalized()
            if rect.width() > 5 and rect.height() > 5:
                self._region_rect = rect
                cropped = self._full_screenshot.copy(rect)
                self.region_selected.emit(cropped, rect)
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()


class ScreenSnipper:
    """Captures screen regions using macOS native tools or Qt fallback."""

    def __init__(self):
        self._overlay: ScreenSnipOverlay | None = None
        self._callback = None

    def capture_region(self, callback):
        """Capture a screen region. Calls callback(QPixmap, QRect) when done."""
        self._callback = callback
        self._overlay = ScreenSnipOverlay()
        self._overlay.region_selected.connect(self._on_region_selected)
        self._overlay.start_capture()

    def _on_region_selected(self, pixmap: QPixmap, rect: QRect):
        if self._callback:
            self._callback(pixmap, rect)

    @staticmethod
    def capture_full_screen() -> QPixmap | None:
        """Capture the entire screen using macOS screencapture."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name

        try:
            subprocess.run(
                ["screencapture", "-x", tmp_path],
                check=True, timeout=5
            )
            pixmap = QPixmap(tmp_path)
            return pixmap if not pixmap.isNull() else None
        except (subprocess.CalledProcessError, FileNotFoundError):
            screen = QGuiApplication.primaryScreen()
            if screen:
                return screen.grabWindow(0)
            return None
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @staticmethod
    def capture_to_image(qimage_callback):
        """Capture full screen and return QImage via callback."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name

        try:
            subprocess.run(
                ["screencapture", "-x", tmp_path],
                check=True, timeout=5
            )
            from PyQt6.QtGui import QImage
            image = QImage(tmp_path)
            qimage_callback(image)
        except (subprocess.CalledProcessError, FileNotFoundError):
            screen = QGuiApplication.primaryScreen()
            if screen:
                pixmap = screen.grabWindow(0)
                qimage_callback(pixmap.toImage())
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
