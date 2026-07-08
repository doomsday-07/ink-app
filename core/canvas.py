import math
import random
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPoint, QRect, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QImage, QTabletEvent,
    QMouseEvent, QPaintEvent, QResizeEvent, QPainterPath,
    QRadialGradient, QLinearGradient
)


BRUSH_PEN = "pen"
BRUSH_CALLIGRAPHY = "calligraphy"
BRUSH_SPRAY = "spray"
BRUSH_MARKER = "marker"
BRUSH_PENCIL = "pencil"
BRUSH_ERASER = "eraser"

ALL_BRUSHES = [BRUSH_PEN, BRUSH_CALLIGRAPHY, BRUSH_SPRAY, BRUSH_MARKER, BRUSH_PENCIL, BRUSH_ERASER]


class Stroke:
    def __init__(self, color: QColor, width: float, brush_type: str = BRUSH_PEN,
                 opacity: float = 1.0, points: list[tuple[QPoint, float]] = None):
        self.color = color
        self.width = width
        self.brush_type = brush_type
        self.opacity = opacity
        self.points: list[tuple[QPoint, float]] = points or []

    def add_point(self, point: QPoint, pressure: float = 1.0):
        self.points.append((point, pressure))

    def bounding_rect(self) -> QRect:
        if not self.points:
            return QRect()
        xs = [p.x() for p, _ in self.points]
        ys = [p.y() for p, _ in self.points]
        margin = int(self.width) + 10
        return QRect(min(xs) - margin, min(ys) - margin,
                     max(xs) - min(xs) + 2 * margin,
                     max(ys) - min(ys) + 2 * margin)


class DrawingCanvas(QWidget):
    stroke_finished = pyqtSignal()
    stroke_started = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._strokes: list[Stroke] = []
        self._current_stroke: Stroke | None = None
        self._undo_stack: list[list[Stroke]] = []
        self._redo_stack: list[list[Stroke]] = []

        self._pen_color = QColor(0, 0, 0)
        self._pen_width = 3.0
        self._current_tool = BRUSH_PEN
        self._eraser_width = 20.0
        self._opacity = 1.0
        self._drawing = False
        self._transparent = False

        self._background_color = QColor(255, 255, 255)
        self._canvas_image: QImage | None = None

    def set_pen_color(self, color: QColor):
        self._pen_color = color

    def set_pen_width(self, width: float):
        self._pen_width = width

    def set_current_tool(self, tool: str):
        self._current_tool = tool

    def set_opacity(self, opacity: float):
        self._opacity = max(0.0, min(1.0, opacity))

    def set_transparent(self, enabled: bool):
        self._transparent = enabled
        self.update()

    def set_eraser_mode(self, enabled: bool):
        self._current_tool = BRUSH_ERASER if enabled else BRUSH_PEN

    def set_eraser_width(self, width: float):
        self._eraser_width = width

    def clear(self):
        self._save_undo_state()
        self._strokes.clear()
        self._canvas_image = None
        self.update()

    def undo(self):
        if self._undo_stack:
            self._redo_stack.append(list(self._strokes))
            self._strokes = self._undo_stack.pop()
            self.update()

    def redo(self):
        if self._redo_stack:
            self._undo_stack.append(list(self._strokes))
            self._strokes = self._redo_stack.pop()
            self.update()

    def _save_undo_state(self):
        self._undo_stack.append(list(self._strokes))
        self._redo_stack.clear()

    def get_strokes_copy(self) -> list[Stroke]:
        return list(self._strokes)

    def export_as_image(self) -> QImage:
        if not self._strokes:
            return QImage(1, 1, QImage.Format.Format_ARGB32)
        combined = QRect()
        for stroke in self._strokes:
            combined = combined.united(stroke.bounding_rect())
        padding = 20
        combined.adjust(-padding, -padding, padding, padding)
        combined = combined.intersected(self.rect())
        image = QImage(combined.size(), QImage.Format.Format_ARGB32)
        image.fill(self._background_color)
        painter = QPainter(image)
        painter.translate(-combined.topLeft())
        self._render_strokes(painter)
        painter.end()
        return image

    def _render_strokes(self, painter: QPainter):
        for stroke in self._strokes:
            self._render_brush(painter, stroke)

    def _render_brush(self, painter: QPainter, stroke: Stroke):
        if len(stroke.points) < 1:
            return
        bt = stroke.brush_type
        if bt == BRUSH_ERASER:
            self._render_pen(painter, stroke, eraser=True)
        elif bt == BRUSH_PEN:
            self._render_pen(painter, stroke)
        elif bt == BRUSH_CALLIGRAPHY:
            self._render_calligraphy(painter, stroke)
        elif bt == BRUSH_SPRAY:
            self._render_spray(painter, stroke)
        elif bt == BRUSH_MARKER:
            self._render_marker(painter, stroke)
        elif bt == BRUSH_PENCIL:
            self._render_pencil(painter, stroke)
        else:
            self._render_pen(painter, stroke)

    def _render_pen(self, painter: QPainter, stroke: Stroke, eraser: bool = False):
        color = QColor(255, 255, 255) if eraser else stroke.color
        for i in range(1, len(stroke.points)):
            p0, pressure0 = stroke.points[i - 1]
            p1, pressure1 = stroke.points[i]
            effective_width = stroke.width * max(pressure1, 0.3)
            pen = QPen(color, effective_width, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setOpacity(stroke.opacity)
            painter.drawLine(p0, p1)
        painter.setOpacity(1.0)

    def _render_calligraphy(self, painter: QPainter, stroke: Stroke):
        if len(stroke.points) < 2:
            return
        painter.setOpacity(stroke.opacity)
        for i in range(1, len(stroke.points)):
            p0, pressure0 = stroke.points[i - 1]
            p1, pressure1 = stroke.points[i]
            dx = p1.x() - p0.x()
            dy = p1.y() - p0.y()
            angle = math.atan2(dy, dx) if (dx != 0 or dy != 0) else 0.0
            nib_angle = math.pi / 4
            width_factor = abs(math.sin(angle - nib_angle))
            effective_width = stroke.width * (0.2 + 0.8 * width_factor) * max(pressure1, 0.3)
            pen = QPen(stroke.color, effective_width, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(p0, p1)
        painter.setOpacity(1.0)

    def _render_spray(self, painter: QPainter, stroke: Stroke):
        painter.setPen(Qt.PenStyle.NoPen)
        color = QColor(stroke.color)
        for i in range(len(stroke.points)):
            point, pressure = stroke.points[i]
            radius = stroke.width * 2
            density = int(8 + 16 * pressure)
            for _ in range(density):
                rx = point.x() + random.uniform(-radius, radius)
                ry = point.y() + random.uniform(-radius, radius)
                dot_size = random.uniform(0.5, 2.0)
                c = QColor(color)
                c.setAlphaF(stroke.opacity * random.uniform(0.3, 0.8))
                painter.setBrush(c)
                painter.drawEllipse(QPointF(rx, ry), dot_size, dot_size)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _render_marker(self, painter: QPainter, stroke: Stroke):
        if len(stroke.points) < 2:
            return
        painter.setOpacity(stroke.opacity * 0.5)
        for i in range(1, len(stroke.points)):
            p0, pressure0 = stroke.points[i - 1]
            p1, pressure1 = stroke.points[i]
            effective_width = stroke.width * max(pressure1, 0.3)
            pen = QPen(stroke.color, effective_width, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.BevelJoin)
            painter.setPen(pen)
            painter.drawLine(p0, p1)
        painter.setOpacity(1.0)

    def _render_pencil(self, painter: QPainter, stroke: Stroke):
        if len(stroke.points) < 2:
            return
        for i in range(1, len(stroke.points)):
            p0, pressure0 = stroke.points[i - 1]
            p1, pressure1 = stroke.points[i]
            effective_width = stroke.width * max(pressure1, 0.3) * 0.6
            alpha = 0.4 + 0.6 * pressure1
            c = QColor(stroke.color)
            c.setAlphaF(stroke.opacity * alpha)
            pen = QPen(c, effective_width, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(p0, p1)
        painter.setOpacity(1.0)

    def _get_point(self, event) -> tuple[QPoint, float]:
        pos = event.position() if hasattr(event, 'position') else event.pos()
        point = QPoint(int(pos.x()), int(pos.y()))
        pressure = getattr(event, 'pressure', lambda: 1.0)()
        if pressure <= 0:
            pressure = 1.0
        return point, pressure

    def _make_stroke(self, point, pressure):
        if self._current_tool == BRUSH_ERASER:
            color = QColor(255, 255, 255)
            width = self._eraser_width
            brush = BRUSH_ERASER
        else:
            color = QColor(self._pen_color)
            width = self._pen_width
            brush = self._current_tool
        stroke = Stroke(color, width, brush, self._opacity)
        stroke.add_point(point, pressure)
        return stroke

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drawing = True
            self._save_undo_state()
            point, pressure = self._get_point(event)
            self._current_stroke = self._make_stroke(point, pressure)
            self.stroke_started.emit()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drawing and self._current_stroke:
            point, pressure = self._get_point(event)
            self._current_stroke.add_point(point, pressure)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._drawing:
            self._drawing = False
            if self._current_stroke and len(self._current_stroke.points) > 1:
                self._strokes.append(self._current_stroke)
            self._current_stroke = None
            self.stroke_finished.emit()
            self.update()

    def tabletEvent(self, event: QTabletEvent):
        if event.type() == event.Type.TabletPress:
            self._drawing = True
            self._save_undo_state()
            point = QPoint(int(event.position().x()), int(event.position().y()))
            pressure = event.pressure()
            self._current_stroke = self._make_stroke(point, pressure)
            self.stroke_started.emit()
            event.accept()
            self.update()
        elif event.type() == event.Type.TabletMove:
            if self._current_stroke:
                point = QPoint(int(event.position().x()), int(event.position().y()))
                self._current_stroke.add_point(point, event.pressure())
                event.accept()
                self.update()
        elif event.type() == event.Type.TabletRelease:
            if self._current_stroke and len(self._current_stroke.points) > 1:
                self._strokes.append(self._current_stroke)
            self._current_stroke = None
            self._drawing = False
            self.stroke_finished.emit()
            event.accept()
            self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._transparent:
            painter.fillRect(self.rect(), self._background_color)
        self._render_strokes(painter)
        if self._current_stroke and len(self._current_stroke.points) >= 1:
            self._render_brush(painter, self._current_stroke)
        painter.end()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
