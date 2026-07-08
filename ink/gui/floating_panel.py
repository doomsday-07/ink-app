from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QPushButton, QSlider
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, pyqtSignal, QThread
from PyQt6.QtGui import QColor, QPainter, QMouseEvent, QPaintEvent, QCursor

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.canvas import DrawingCanvas
from core.recognizer import HandwritingRecognizer
from core.accessibility import (
    _inject_via_clipboard, activate_app, is_accessibility_enabled,
    FocusedAppTracker, get_focused_element_for_pid, inject_via_ax,
    simulate_backspace, simulate_space
)


class FloatingPanel(QWidget):
    text_recognized = pyqtSignal(str)
    text_injected = pyqtSignal(bool)
    panel_closed = pyqtSignal()

    TITLE_BAR_HEIGHT = 28
    STATUS_HEIGHT = 22
    SETTINGS_HEIGHT = 50
    RESIZE_HANDLE = 14

    def __init__(self, recognizer: HandwritingRecognizer, parent=None, tracker: FocusedAppTracker = None):
        super().__init__(parent)
        self._recognizer = recognizer
        self._language = "en"
        self._auto_recognize = True
        self._recognition_delay = 500
        self._dragging = False
        self._drag_offset = QPoint(0, 0)
        self._panel_opacity = 0.92
        self._target_pid = None
        self._tracker = tracker
        self._target_element = None
        self._resizing = False
        self._resize_start_pos = QPoint(0, 0)
        self._resize_start_geo = QRect()
        self._settings_open = False
        self._panel_w = 360
        self._panel_h = 180

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self._panel_w, self._panel_h)
        self.setWindowOpacity(self._panel_opacity)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_bar = QWidget()
        title_bar.setFixedHeight(self.TITLE_BAR_HEIGHT)
        title_bar.setObjectName("titleBar")
        title_bar.setStyleSheet(
            "#titleBar { background-color: #2d2d2d; border-top-left-radius: 8px; border-top-right-radius: 8px; }"
        )
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(8, 2, 4, 2)

        title_label = QLabel("Ink")
        title_label.setStyleSheet("color: #bbbbbb; font-size: 11px; font-weight: bold;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        btn_settings = QToolButton()
        btn_settings.setText("\u2699")
        btn_settings.setFixedSize(22, 22)
        btn_settings.setStyleSheet(
            "QToolButton { color: #bbbbbb; background: transparent; border: none; font-size: 13px; }"
            "QToolButton:hover { color: white; }"
        )
        btn_settings.clicked.connect(self._toggle_settings_popup)
        title_layout.addWidget(btn_settings)

        btn_close = QToolButton()
        btn_close.setText("\u2715")
        btn_close.setFixedSize(22, 22)
        btn_close.setStyleSheet(
            "QToolButton { color: #bbbbbb; background: transparent; border: none; font-size: 13px; }"
            "QToolButton:hover { color: #ff5555; }"
        )
        btn_close.clicked.connect(self._on_close)
        title_layout.addWidget(btn_close)

        layout.addWidget(title_bar)

        self._settings_bar = self._create_settings_bar()
        self._settings_bar.hide()
        layout.addWidget(self._settings_bar)

        self._canvas = DrawingCanvas()
        self._canvas.setMinimumSize(100, 60)
        self._canvas.set_transparent(True)
        self._canvas.setStyleSheet(
            "background-color: transparent; border-radius: 4px; margin: 2px;"
        )
        self._canvas.stroke_finished.connect(self._on_stroke_finished)
        self._canvas.stroke_started.connect(self._capture_target_element)
        layout.addWidget(self._canvas, 1)

        status_bar = QWidget()
        status_bar.setFixedHeight(self.STATUS_HEIGHT)
        status_bar.setObjectName("statusBar")
        status_bar.setStyleSheet(
            "#statusBar { background-color: #2d2d2d; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; }"
        )
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(8, 1, 8, 1)

        self._status_label = QLabel("Write here \u2026")
        self._status_label.setStyleSheet("color: #999999; font-size: 10px;")
        status_layout.addWidget(self._status_label)
        status_layout.addStretch()

        btn_clear = QPushButton("Clear")
        btn_clear.setFixedSize(44, 18)
        btn_clear.setStyleSheet(
            "QPushButton { background: #444; color: #bbb; border: none; border-radius: 3px; font-size: 9px; }"
            "QPushButton:hover { background: #555; }"
        )
        btn_clear.clicked.connect(lambda: self._canvas.clear())
        status_layout.addWidget(btn_clear)

        btn_undo = QPushButton("Undo")
        btn_undo.setFixedSize(44, 18)
        btn_undo.setStyleSheet(
            "QPushButton { background: #444; color: #bbb; border: none; border-radius: 3px; font-size: 9px; }"
            "QPushButton:hover { background: #555; }"
        )
        btn_undo.clicked.connect(lambda: self._canvas.undo())
        status_layout.addWidget(btn_undo)

        btn_space = QPushButton("Space")
        btn_space.setFixedSize(50, 18)
        btn_space.setStyleSheet(
            "QPushButton { background: #444; color: #bbb; border: none; border-radius: 3px; font-size: 9px; }"
            "QPushButton:hover { background: #555; }"
        )
        btn_space.clicked.connect(self._on_space_clicked)
        status_layout.addWidget(btn_space)

        btn_backspace = QPushButton("\u232b")
        btn_backspace.setFixedSize(36, 18)
        btn_backspace.setStyleSheet(
            "QPushButton { background: #444; color: #bbb; border: none; border-radius: 3px; font-size: 9px; }"
            "QPushButton:hover { background: #555; }"
        )
        btn_backspace.clicked.connect(self._on_backspace_clicked)
        status_layout.addWidget(btn_backspace)

        layout.addWidget(status_bar)

        self._recognition_timer = QTimer(self)
        self._recognition_timer.setSingleShot(True)
        self._recognition_timer.timeout.connect(self._trigger_recognition)

        self._auto_clear_timer = QTimer(self)
        self._auto_clear_timer.setSingleShot(True)
        self._auto_clear_timer.timeout.connect(lambda: self._canvas.clear())

    def _create_settings_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("settingsBar")
        bar.setFixedHeight(self.SETTINGS_HEIGHT)
        bar.setStyleSheet("#settingsBar { background-color: #383838; }")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(6)

        lbl = QLabel("Delay:")
        lbl.setStyleSheet("color: #bbb; font-size: 10px;")
        row.addWidget(lbl)

        self._delay_slider = QSlider(Qt.Orientation.Horizontal)
        self._delay_slider.setRange(100, 2000)
        self._delay_slider.setSingleStep(100)
        self._delay_slider.setValue(self._recognition_delay)
        self._delay_slider.setFixedWidth(120)
        self._delay_slider.valueChanged.connect(self._on_delay_slider_changed)
        row.addWidget(self._delay_slider)

        self._delay_value_label = QLabel(f"{self._recognition_delay}ms")
        self._delay_value_label.setStyleSheet("color: #999; font-size: 10px;")
        self._delay_value_label.setFixedWidth(50)
        row.addWidget(self._delay_value_label)

        row.addStretch()

        self._auto_recog_cb = QToolButton()
        self._auto_recog_cb.setText("Auto")
        self._auto_recog_cb.setCheckable(True)
        self._auto_recog_cb.setChecked(self._auto_recognize)
        self._auto_recog_cb.setFixedHeight(20)
        self._auto_recog_cb.setStyleSheet(
            "QToolButton { color: #bbb; background: #555; border: none; border-radius: 3px; font-size: 10px; padding: 2px 8px; }"
            "QToolButton:checked { background: #4CAF50; color: white; }"
        )
        self._auto_recog_cb.clicked.connect(self._on_auto_recog_toggled)
        row.addWidget(self._auto_recog_cb)

        return bar

    def _toggle_settings_popup(self):
        if self._settings_open:
            self._settings_bar.hide()
            self._settings_open = False
            self._panel_h -= self.SETTINGS_HEIGHT
        else:
            self._settings_bar.show()
            self._settings_open = True
            self._panel_h += self.SETTINGS_HEIGHT
        self.setFixedSize(self._panel_w, self._panel_h)

    def _on_delay_slider_changed(self, value: int):
        self._recognition_delay = value
        self._delay_value_label.setText(f"{value}ms")

    def _on_auto_recog_toggled(self, checked: bool):
        self._auto_recognize = checked

    def _on_space_clicked(self):
        target_pid = None
        if self._tracker:
            target_pid = self._tracker.get_last_focused_pid()
        elif self._target_pid:
            target_pid = self._target_pid
        if target_pid:
            activate_app(target_pid)
        simulate_space()

    def _on_backspace_clicked(self):
        target_pid = None
        if self._tracker:
            target_pid = self._tracker.get_last_focused_pid()
        elif self._target_pid:
            target_pid = self._target_pid
        if target_pid:
            activate_app(target_pid)
        simulate_backspace()

    def set_language(self, language: str):
        self._language = language

    def set_auto_recognize(self, enabled: bool):
        self._auto_recognize = enabled
        if hasattr(self, '_auto_recog_cb'):
            self._auto_recog_cb.setChecked(enabled)

    def set_recognition_delay(self, delay_ms: int):
        self._recognition_delay = delay_ms
        if hasattr(self, '_delay_slider'):
            self._delay_slider.setValue(delay_ms)

    def set_panel_opacity(self, opacity: float):
        self._panel_opacity = opacity
        self.setWindowOpacity(opacity)

    def set_ocr_engine(self, engine: str):
        self._recognizer.set_engine(engine)

    def set_tracker(self, tracker: FocusedAppTracker):
        self._tracker = tracker

    def _capture_target_element(self):
        pid = None
        if self._tracker:
            pid = self._tracker.get_last_focused_pid()
        elif self._target_pid:
            pid = self._target_pid
        if pid:
            self._target_pid = pid
            self._target_element = get_focused_element_for_pid(pid)

    def _on_stroke_finished(self):
        if self._auto_recognize:
            self._recognition_timer.start(self._recognition_delay)

    def _trigger_recognition(self):
        image = self._canvas.export_as_image()
        if image.isNull() or image.width() <= 1:
            return
        self._status_label.setText("Recognizing \u2026")
        self._worker = _PanelRecognitionWorker(self._recognizer, image, self._language)
        self._worker.finished.connect(self._on_recognition_done)
        self._worker.error.connect(self._on_recognition_error)
        self._worker.start()

    def _on_recognition_done(self, text: str):
        import time as _time
        if not text.strip():
            self._status_label.setText("No text recognized")
            return
        self._status_label.setText(f"\u2192 {text[:50]}{'...' if len(text) > 50 else ''}")
        self.text_recognized.emit(text)
        success = False
        if self._target_element:
            success = inject_via_ax(self._target_element, text)
        if not success:
            target_pid = None
            if self._tracker:
                target_pid = self._tracker.get_last_focused_pid()
            elif self._target_pid:
                target_pid = self._target_pid
            if target_pid:
                activate_app(target_pid)
                _time.sleep(0.15)
            success = _inject_via_clipboard(text)
        self.text_injected.emit(success)
        if success:
            self._status_label.setText(f"\u2713 Sent: {text[:45]}")
            self._auto_clear_timer.start(300)
        else:
            self._status_label.setText(f"\u26a0 Copied: {text[:45]}")

    def _on_recognition_error(self, error: str):
        self._status_label.setText(f"Error: {error[:50]}")

    def _hit_resize_handle(self, pos: QPoint) -> str:
        r = self.rect()
        x, y = pos.x(), pos.y()
        at_right = x >= r.right() - self.RESIZE_HANDLE
        at_bottom = y >= r.bottom() - self.RESIZE_HANDLE
        if at_right and at_bottom:
            return "corner"
        if at_right:
            return "right"
        if at_bottom:
            return "bottom"
        return ""

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(40, 40, 40, 220))
        painter.drawRoundedRect(self.rect(), 8, 8)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            handle = self._hit_resize_handle(pos)
            if handle:
                self._resizing = True
                self._resize_handle_type = handle
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geo = self.geometry()
                event.accept()
                return
            if pos.y() < self.TITLE_BAR_HEIGHT:
                self._dragging = True
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._resizing:
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            g = QRect(self._resize_start_geo)
            if self._resize_handle_type in ("corner", "right"):
                g.setRight(g.right() + delta.x())
            if self._resize_handle_type in ("corner", "bottom"):
                g.setBottom(g.bottom() + delta.y())
            if g.width() >= 220 and g.height() >= 120:
                self._panel_w = g.width()
                self._panel_h = g.height()
                self.setFixedSize(self._panel_w, self._panel_h)
            event.accept()
        elif self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            handle = self._hit_resize_handle(event.position().toPoint())
            if handle == "corner":
                self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
            elif handle == "right":
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif handle == "bottom":
                self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._resizing = False
            event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._on_close()
        elif event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._canvas.undo()
        elif event.key() == Qt.Key.Key_Space:
            self._on_space_clicked()
        elif event.key() == Qt.Key.Key_Backspace:
            self._on_backspace_clicked()
        else:
            super().keyPressEvent(event)

    def _on_close(self):
        self.hide()
        self.panel_closed.emit()


class _PanelRecognitionWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, recognizer: HandwritingRecognizer, image, language: str = "en"):
        super().__init__()
        self.recognizer = recognizer
        self.image = image
        self.language = language

    def run(self):
        try:
            text = self.recognizer.recognize_from_qimage(self.image, self.language)
            self.finished.emit(text)
        except Exception as e:
            self.error.emit(str(e))
