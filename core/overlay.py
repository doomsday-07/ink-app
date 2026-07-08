import math
import random
from collections import deque
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QPoint, QPointF, pyqtSignal, QRect, QRectF, QSize, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QCursor, QPixmap, QFont, QPainterPath,
    QPainterPathStroker, QImage, QFontMetrics, QTransform
)

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.canvas import (
    Stroke, BRUSH_PEN, BRUSH_CALLIGRAPHY, BRUSH_SPRAY, BRUSH_MARKER,
    BRUSH_PENCIL, BRUSH_ERASER, ALL_BRUSHES
)
from core.layer import AnnotationLayer


BRUSH_HIGHLIGHTER = "highlighter"
SHAPE_ARROW = "arrow"
SHAPE_RECT = "rect"
SHAPE_CIRCLE = "circle"
TEXT_TOOL = "text"
FILL_TOOL = "fill"
HAND_TOOL = "hand"
MOVE_TOOL = "move"
ROTATE_TOOL = "rotate"
MIRROR_TOOL = "mirror"

TEXTURE_NONE = "none"
TEXTURE_PAPER = "paper"
TEXTURE_GRID = "grid"
TEXTURE_LINES = "lines"
TEXTURE_DOTS = "dots"

ALL_TEXTURES = [TEXTURE_NONE, TEXTURE_PAPER, TEXTURE_GRID, TEXTURE_LINES, TEXTURE_DOTS]

ALL_TOOLS = ALL_BRUSHES + [BRUSH_HIGHLIGHTER, SHAPE_ARROW, SHAPE_RECT, SHAPE_CIRCLE, TEXT_TOOL, FILL_TOOL, HAND_TOOL, MOVE_TOOL, ROTATE_TOOL, MIRROR_TOOL]


class AnnotationOverlay(QWidget):
    annotation_captured = pyqtSignal(QPixmap)
    closed = pyqtSignal()

    TITLE_BAR_HEIGHT = 32
    RESIZE_HANDLE = 12

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Doodle")
        self.setMinimumSize(640, 480)
        self.resize(960, 720)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

        self._screenshot: QPixmap | None = None
        self._tool = BRUSH_PEN
        self._color = QColor(255, 0, 0)
        self._width = 3.0
        self._opacity = 1.0

        self._current_stroke: Stroke | None = None
        self._drawing = False
        self._selected_text_idx = -1
        self._dragging_text = False
        self._text_drag_offset = QPoint(0, 0)
        self._shape_start: QPoint | None = None
        self._shape_end: QPoint | None = None

        self._dragging = False
        self._drag_offset = QPoint(0, 0)
        self._resizing = False
        self._resize_start = QPoint(0, 0)
        self._resize_initial = QRect()

        self._resizing_text = False
        self._resize_text_start_font: QFont | None = None
        self._resize_text_start_pos = QPoint(0, 0)
        self._resize_text_handle = -1

        self._text_press_timer = QTimer(self)
        self._text_press_timer.setSingleShot(True)
        self._text_press_timer.setInterval(500)
        self._text_press_timer.timeout.connect(self._on_text_long_press)
        self._text_press_pos = QPoint(0, 0)
        self._text_press_idx = -1

        self._zoom = 1.0
        self._pan_offset = QPoint(0, 0)
        self._panning = False
        self._pan_start = QPoint(0, 0)

        self._moving = False
        self._move_start = QPoint(0, 0)
        self._move_offset = QPoint(0, 0)

        self._rotating = False
        self._rotate_start = QPoint(0, 0)
        self._rotate_angle = 0.0
        self._rotate_start_angle = 0.0
        self._rotate_transform = None
        self._rotate_total_angle = 0.0
        self._rotate_view = None

        self._barrier_version = 0

        self._fill_cache_version = 0
        self._fill_cache: dict[int, QPixmap] = {}

        self._mirroring = False
        self._mirror_axis = "horizontal"

        self._texture = TEXTURE_NONE
        self._texture_color = QColor(200, 200, 200)

        self._layers: list[AnnotationLayer] = [AnnotationLayer("Background", locked=True)]
        self._active_layer_idx = 0
        self._undo_stack: list[tuple[int, list, list, list, list, list]] = []
        self._redo_stack: list[tuple[int, list, list, list, list, list]] = []

    @property
    def _current(self) -> AnnotationLayer:
        return self._layers[self._active_layer_idx]

    # ── Layer management ──────────────────────────────────────────────

    def add_layer(self, name: str = None) -> int:
        idx = len(self._layers)
        if name is None:
            name = f"Layer {idx}"
        self._layers.append(AnnotationLayer(name, locked=False))
        if self._screenshot:
            pix = QPixmap(self._screenshot.size())
            pix.fill(QColor(0, 0, 0, 0))
            if self._screenshot.devicePixelRatio() > 1.0:
                pix.setDevicePixelRatio(self._screenshot.devicePixelRatio())
            self._layers[-1].raster = pix
        return idx

    def remove_layer(self, idx: int):
        if idx <= 0 or idx >= len(self._layers):
            return
        del self._layers[idx]
        if self._active_layer_idx >= len(self._layers):
            self._active_layer_idx = len(self._layers) - 1
        elif self._active_layer_idx >= idx:
            self._active_layer_idx = max(0, self._active_layer_idx - 1)
        self._selected_text_idx = -1
        self.update()

    def switch_to_layer(self, idx: int):
        if 0 <= idx < len(self._layers):
            self._active_layer_idx = idx
            self._selected_text_idx = -1
            self.update()

    def rename_layer(self, idx: int, name: str):
        if 0 <= idx < len(self._layers):
            self._layers[idx].name = name

    def get_layer_count(self) -> int:
        return len(self._layers)

    def get_active_layer(self) -> int:
        return self._active_layer_idx

    def get_layer_names(self) -> list[str]:
        return [l.name for l in self._layers]

    def get_layer_visible(self, idx: int) -> bool:
        if 0 <= idx < len(self._layers):
            return self._layers[idx].visible
        return False

    def set_layer_visible(self, idx: int, visible: bool):
        if 0 <= idx < len(self._layers):
            self._layers[idx].visible = visible
            self.update()

    def get_layer_locked(self, idx: int) -> bool:
        if 0 <= idx < len(self._layers):
            return self._layers[idx].locked
        return True

    def set_layer_locked(self, idx: int, locked: bool):
        if 0 <= idx < len(self._layers):
            self._layers[idx].locked = locked

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self, screenshot: QPixmap = None):
        if screenshot is not None:
            self._screenshot = screenshot
        self.show()

    def show_overlay(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _capture_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            self._screenshot = screen.grabWindow(0)
            self.update()

    def set_tool(self, tool: str):
        self._tool = tool
        if tool == HAND_TOOL:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def set_color(self, color: QColor):
        self._color = color

    def set_width(self, width: float):
        self._width = width

    def set_opacity(self, opacity: float):
        self._opacity = max(0.0, min(1.0, opacity))

    def set_zoom(self, zoom: float):
        self._zoom = max(0.5, min(2.0, zoom))
        self.update()

    def set_texture(self, texture: str):
        if texture in ALL_TEXTURES:
            self._texture = texture
            self.update()

    def _widget_to_logical(self, p: QPoint) -> QPoint:
        return QPoint(
            int((p.x() - self._pan_offset.x()) / self._zoom),
            int((p.y() - self._pan_offset.y()) / self._zoom)
        )

    def _logical_center(self) -> QPointF:
        c = self.rect().center()
        return QPointF(
            (c.x() - self._pan_offset.x()) / self._zoom,
            (c.y() - self._pan_offset.y()) / self._zoom
        )

    # ── Painting ──────────────────────────────────────────────────────

    def _render_texture(self, painter: QPainter):
        if self._texture == TEXTURE_NONE:
            return
        
        rect = self.rect()
        painter.setPen(Qt.PenStyle.NoPen)
        
        if self._texture == TEXTURE_PAPER:
            painter.setBrush(QColor(245, 245, 240))
            painter.drawRect(rect)
            painter.setBrush(QColor(235, 235, 230))
            for y in range(0, rect.height(), 4):
                if y % 8 == 0:
                    painter.drawRect(0, y, rect.width(), 2)
        
        elif self._texture == TEXTURE_GRID:
            painter.setBrush(QColor(250, 250, 250))
            painter.drawRect(rect)
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            grid_size = 20
            for x in range(0, rect.width(), grid_size):
                painter.drawLine(x, 0, x, rect.height())
            for y in range(0, rect.height(), grid_size):
                painter.drawLine(0, y, rect.width(), y)
        
        elif self._texture == TEXTURE_LINES:
            painter.setBrush(QColor(255, 255, 255))
            painter.drawRect(rect)
            painter.setPen(QPen(QColor(180, 210, 240), 1))
            line_height = 24
            for y in range(line_height, rect.height(), line_height):
                painter.drawLine(0, y, rect.width(), y)
        
        elif self._texture == TEXTURE_DOTS:
            painter.setBrush(QColor(250, 250, 250))
            painter.drawRect(rect)
            painter.setBrush(QColor(200, 200, 200))
            dot_spacing = 20
            dot_radius = 2
            for x in range(dot_spacing, rect.width(), dot_spacing):
                for y in range(dot_spacing, rect.height(), dot_spacing):
                    painter.drawEllipse(QPoint(x, y), dot_radius, dot_radius)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.save()
        painter.translate(self._pan_offset)
        painter.scale(self._zoom, self._zoom)

        if self._screenshot:
            painter.drawPixmap(0, 0, self._screenshot)
        else:
            self._render_texture(painter)

        for layer in self._layers:
            if not layer.visible:
                continue
            if self._rotate_transform is not None and layer is self._current and self._rotate_view is not None:
                painter.save()
                painter.setTransform(self._rotate_transform, True)
                painter.drawPixmap(0, 0, self._rotate_view)
                painter.restore()
            else:
                self._render_layer_annotations(painter, layer)

        if not self._current.locked:
            if self._drawing and self._current_stroke:
                self._render_brush(painter, self._current_stroke)

            if self._drawing and self._shape_start and self._shape_end:
                painter.setOpacity(self._opacity)
                pen = QPen(self._color, self._width, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                rect = QRect(self._shape_start, self._shape_end).normalized()
                if self._tool == SHAPE_RECT:
                    painter.drawRect(rect)
                elif self._tool == SHAPE_CIRCLE:
                    painter.drawEllipse(rect)
                elif self._tool == SHAPE_ARROW:
                    self._draw_arrow(painter, self._shape_start, self._shape_end,
                                     self._color, self._width, self._opacity)
                painter.setOpacity(1.0)

        if self._tool == TEXT_TOOL and self._selected_text_idx >= 0:
            if self._selected_text_idx < len(self._current.text_items):
                pos, text, font, color, gen = self._current.text_items[self._selected_text_idx]
                fm = QFontMetrics(font)
                br = fm.tightBoundingRect(text)
                text_rect = QRect(pos.x() + br.x() - 4, pos.y() + br.y() - 4, br.width() + 8, br.height() + 8)
                painter.save()
                painter.setPen(QPen(QColor(66, 133, 244), 1, Qt.PenStyle.SolidLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(text_rect)
                
                hs = 6
                half = hs // 2
                handle_positions = [
                    (text_rect.left(), text_rect.top()),
                    (text_rect.center().x(), text_rect.top()),
                    (text_rect.right(), text_rect.top()),
                    (text_rect.left(), text_rect.center().y()),
                    (text_rect.right(), text_rect.center().y()),
                    (text_rect.left(), text_rect.bottom()),
                    (text_rect.center().x(), text_rect.bottom()),
                    (text_rect.right(), text_rect.bottom()),
                ]
                painter.setPen(QPen(QColor(66, 133, 244), 1))
                painter.setBrush(QColor(255, 255, 255))
                for hx, hy in handle_positions:
                    painter.drawRect(QRect(hx - half, hy - half, hs, hs))
                
                circle_r = 8
                cx = text_rect.right() + 10
                cy = text_rect.top() - 10
                painter.setPen(QPen(QColor(200, 200, 200), 1))
                painter.setBrush(QColor(50, 50, 50))
                painter.drawEllipse(QPoint(cx, cy), circle_r, circle_r)
                painter.setPen(QPen(QColor(255, 80, 80), 2))
                cross_h = 5
                painter.drawLine(cx - cross_h, cy - cross_h, cx + cross_h, cy + cross_h)
                painter.drawLine(cx + cross_h, cy - cross_h, cx - cross_h, cy + cross_h)
                
                painter.restore()

        painter.restore()
        painter.end()

    def _render_layer_annotations(self, painter: QPainter, layer: AnnotationLayer):
        erased = not layer.erased_area.isEmpty()
        if erased:
            full_area = QPainterPath()
            full_area.addRect(QRectF(self.rect()))
            visible = full_area.subtracted(layer.erased_area)

        items = []

        if len(self._fill_cache) > 50:
            self._fill_cache.clear()

        for fill_entry in getattr(layer, 'fill_annotations', []):
            fill_path, color, opacity, gen = fill_entry
            cache_key = id(fill_entry)
            cached = self._fill_cache.get(cache_key)
            if cached is not None:
                pixmap, ox, oy = cached
            else:
                br = fill_path.boundingRect()
                x, y = int(br.x()), int(br.y())
                w, h = max(int(br.width()) + 1, 1), max(int(br.height()) + 1, 1)
                pixmap = QPixmap(w, h)
                pixmap.fill(Qt.GlobalColor.transparent)
                p = QPainter(pixmap)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.translate(-x, -y)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                p.drawPath(fill_path)
                p.end()
                self._fill_cache[cache_key] = (pixmap, x, y)
                ox, oy = x, y
            items.append((gen, 'fill', pixmap, opacity, ox, oy))

        for i, stroke in enumerate(layer.strokes):
            if stroke.brush_type == BRUSH_ERASER:
                continue
            gen = layer.stroke_gens[i] if i < len(layer.stroke_gens) else 0
            items.append((gen, 'stroke', stroke))

        for start, end, color, width, opacity, gen in layer.rectangles:
            items.append((gen, 'rect', start, end, color, width, opacity))

        for start, end, color, width, opacity, gen in layer.circles:
            items.append((gen, 'circle', start, end, color, width, opacity))

        for start, end, color, width, opacity, gen in layer.arrows:
            items.append((gen, 'arrow', start, end, color, width, opacity))

        for pos, text, font, color, gen in layer.text_items:
            items.append((gen, 'text', pos, text, font, color))

        items.sort(key=lambda x: x[0])

        for item in items:
            gen, typ = item[0], item[1]
            is_erased = erased and gen < layer.clip_gen
            if is_erased:
                painter.save()
                painter.setClipPath(visible)

            if typ == 'fill':
                _, _, pixmap, opacity, ox, oy = item
                painter.setOpacity(opacity)
                painter.drawPixmap(ox, oy, pixmap)
                painter.setOpacity(1.0)
            elif typ == 'stroke':
                self._render_brush(painter, item[2])
            elif typ == 'rect':
                _, _, start, end, color, width, opacity = item
                painter.setOpacity(opacity)
                pen = QPen(color, width, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRect(start, end).normalized())
                painter.setOpacity(1.0)
            elif typ == 'circle':
                _, _, start, end, color, width, opacity = item
                painter.setOpacity(opacity)
                pen = QPen(color, width, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QRect(start, end).normalized())
                painter.setOpacity(1.0)
            elif typ == 'arrow':
                _, _, start, end, color, width, opacity = item
                self._draw_arrow(painter, start, end, color, width, opacity)
            elif typ == 'text':
                _, _, pos, text, font, color = item
                painter.setFont(font)
                painter.setPen(QPen(color))
                painter.drawText(pos, text)

            if is_erased:
                painter.restore()


    # ── Brush renderers ───────────────────────────────────────────────

    def _render_brush(self, painter: QPainter, stroke: Stroke):
        bt = stroke.brush_type
        if bt == BRUSH_PEN:
            self._render_pen(painter, stroke)
        elif bt == BRUSH_CALLIGRAPHY:
            self._render_calligraphy(painter, stroke)
        elif bt == BRUSH_SPRAY:
            self._render_spray(painter, stroke)
        elif bt == BRUSH_MARKER:
            self._render_marker(painter, stroke)
        elif bt == BRUSH_PENCIL:
            self._render_pencil(painter, stroke)
        elif bt == BRUSH_ERASER:
            self._render_eraser(painter, stroke)
        elif bt == BRUSH_HIGHLIGHTER:
            self._render_highlighter(painter, stroke)
        else:
            self._render_pen(painter, stroke)

    def _render_pen(self, painter: QPainter, stroke: Stroke):
        if len(stroke.points) < 2:
            return
        painter.setOpacity(stroke.opacity)
        pen = QPen(stroke.color, stroke.width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        last_w = -1
        for i in range(1, len(stroke.points)):
            p0, _ = stroke.points[i - 1]
            p1, pressure1 = stroke.points[i]
            w = stroke.width * max(pressure1, 0.3)
            if w != last_w:
                pen.setWidthF(w)
                painter.setPen(pen)
                last_w = w
            painter.drawLine(p0, p1)
        painter.setOpacity(1.0)

    def _render_calligraphy(self, painter: QPainter, stroke: Stroke):
        if len(stroke.points) < 2:
            return
        painter.setOpacity(stroke.opacity)
        for i in range(1, len(stroke.points)):
            p0, _ = stroke.points[i - 1]
            p1, pressure1 = stroke.points[i]
            dx = p1.x() - p0.x()
            dy = p1.y() - p0.y()
            angle = math.atan2(dy, dx) if (dx != 0 or dy != 0) else 0.0
            nib_angle = math.pi / 4
            wf = abs(math.sin(angle - nib_angle))
            w = stroke.width * (0.2 + 0.8 * wf) * max(pressure1, 0.3)
            pen = QPen(stroke.color, w, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(p0, p1)
        painter.setOpacity(1.0)

    def _render_spray(self, painter: QPainter, stroke: Stroke):
        painter.setPen(Qt.PenStyle.NoPen)
        for point, pressure in stroke.points:
            radius = stroke.width * 2
            density = int(8 + 16 * pressure)
            for _ in range(density):
                rx = point.x() + random.uniform(-radius, radius)
                ry = point.y() + random.uniform(-radius, radius)
                ds = random.uniform(0.5, 2.0)
                c = QColor(stroke.color)
                c.setAlphaF(stroke.opacity * random.uniform(0.3, 0.8))
                painter.setBrush(c)
                painter.drawEllipse(QPointF(rx, ry), ds, ds)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _render_marker(self, painter: QPainter, stroke: Stroke):
        if len(stroke.points) < 2:
            return
        painter.setOpacity(stroke.opacity * 0.5)
        pen = QPen(stroke.color, stroke.width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.BevelJoin)
        last_w = -1
        for i in range(1, len(stroke.points)):
            p0, _ = stroke.points[i - 1]
            p1, pressure1 = stroke.points[i]
            w = stroke.width * max(pressure1, 0.3)
            if w != last_w:
                pen.setWidthF(w)
                painter.setPen(pen)
                last_w = w
            painter.drawLine(p0, p1)
        painter.setOpacity(1.0)

    def _render_pencil(self, painter: QPainter, stroke: Stroke):
        if len(stroke.points) < 2:
            return
        c = QColor(stroke.color)
        for i in range(1, len(stroke.points)):
            p0, _ = stroke.points[i - 1]
            p1, pressure1 = stroke.points[i]
            w = stroke.width * max(pressure1, 0.3) * 0.6
            c.setAlphaF(stroke.opacity * (0.4 + 0.6 * pressure1))
            pen = QPen(c, w, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(p0, p1)
        painter.setOpacity(1.0)

    def _render_eraser(self, painter: QPainter, stroke: Stroke):
        if self._screenshot is None or len(stroke.points) < 2:
            return
        path = QPainterPath()
        path.moveTo(QPointF(stroke.points[0][0]))
        for p, _ in stroke.points[1:]:
            path.lineTo(QPointF(p))
        stroker = QPainterPathStroker()
        stroker.setWidth(max(stroke.width, 2.0))
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        shape = stroker.createStroke(path)
        painter.save()
        painter.setClipPath(shape)
        painter.drawPixmap(0, 0, self._screenshot)
        painter.restore()

    def _render_highlighter(self, painter: QPainter, stroke: Stroke):
        if len(stroke.points) < 2:
            return
        painter.setOpacity(0.35)
        for i in range(1, len(stroke.points)):
            p0, _ = stroke.points[i - 1]
            p1, pressure1 = stroke.points[i]
            w = stroke.width * max(pressure1, 0.5)
            pen = QPen(stroke.color, w, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.BevelJoin)
            painter.setPen(pen)
            painter.drawLine(p0, p1)
        painter.setOpacity(1.0)

    def _draw_arrow(self, painter: QPainter, start: QPoint, end: QPoint,
                    color: QColor, width: float, opacity: float):
        painter.setOpacity(opacity)
        pen = QPen(color, width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(start, end)
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        arrow_len = 15
        arrow_angle = 0.4
        p1 = QPoint(
            int(end.x() - arrow_len * math.cos(angle - arrow_angle)),
            int(end.y() - arrow_len * math.sin(angle - arrow_angle))
        )
        p2 = QPoint(
            int(end.x() - arrow_len * math.cos(angle + arrow_angle)),
            int(end.y() - arrow_len * math.sin(angle + arrow_angle))
        )
        painter.drawLine(end, p1)
        painter.drawLine(end, p2)
        painter.setOpacity(1.0)

    # ── Barrier mask (shared across all layers) ───────────────────────

    def _build_barrier_mask(self, w: int, h: int) -> bytearray:
        mask_img = QImage(w, h, QImage.Format.Format_Grayscale8)
        mask_img.fill(255)
        mp = QPainter(mask_img)
        mp.setRenderHint(QPainter.RenderHint.Antialiasing)
        ratio = self._screenshot.devicePixelRatio() if self._screenshot else 1.0
        if ratio > 1.0:
            mp.scale(ratio, ratio)

        for layer in self._layers:
            if not layer.visible:
                continue
            self._draw_layer_barriers(mp, layer)

        mp.end()

        ptr = mask_img.bits()
        ptr.setsize(mask_img.sizeInBytes())
        stride = mask_img.bytesPerLine()
        raw = bytearray(ptr)

        if stride == w:
            return raw

        packed = bytearray(w * h)
        for row in range(h):
            src_off = row * stride
            dst_off = row * w
            packed[dst_off:dst_off + w] = raw[src_off:src_off + w]
        return packed

    def _draw_layer_barriers(self, mp: QPainter, layer: AnnotationLayer):
        pen = QPen(QColor(0, 0, 0), 1, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

        for i, stroke in enumerate(layer.strokes):
            if stroke.brush_type == BRUSH_ERASER:
                continue
            gen = layer.stroke_gens[i] if i < len(layer.stroke_gens) else 0
            if gen < layer.clip_gen:
                continue
            pts = [p for p, _ in stroke.points]
            if len(pts) < 2:
                continue
            pen.setWidthF(max(stroke.width * 1.5, 2.0))
            mp.setPen(pen)
            for j in range(1, len(pts)):
                mp.drawLine(pts[j - 1], pts[j])

        barrier_pen = QPen(QColor(0, 0, 0), 1, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        for start, end, color, width, opacity, gen in layer.rectangles:
            if gen < layer.clip_gen:
                continue
            barrier_pen.setWidthF(max(width * 1.5, 2.0))
            mp.setPen(barrier_pen)
            mp.drawRect(QRect(start, end).normalized())

        for start, end, color, width, opacity, gen in layer.circles:
            if gen < layer.clip_gen:
                continue
            barrier_pen.setWidthF(max(width * 1.5, 2.0))
            mp.setPen(barrier_pen)
            mp.drawEllipse(QRect(start, end).normalized())

        for start, end, color, width, opacity, gen in layer.arrows:
            if gen < layer.clip_gen:
                continue
            barrier_pen.setWidthF(max(width * 1.5, 2.0))
            mp.setPen(barrier_pen)
            mp.drawLine(start, end)
            angle = math.atan2(end.y() - start.y(), end.x() - start.x())
            arrow_len = 15
            arrow_angle = 0.4
            p1 = QPoint(
                int(end.x() - arrow_len * math.cos(angle - arrow_angle)),
                int(end.y() - arrow_len * math.sin(angle - arrow_angle))
            )
            p2 = QPoint(
                int(end.x() - arrow_len * math.cos(angle + arrow_angle)),
                int(end.y() - arrow_len * math.sin(angle + arrow_angle))
            )
            mp.drawLine(end, p1)
            mp.drawLine(end, p2)

    # ── Fill ──────────────────────────────────────────────────────────

    _barrier_cache: bytearray | None = None
    _barrier_cache_key: tuple = (0, 0, 0)

    def _build_barrier_for_fill(self, w: int, h: int) -> bytearray:
        key = (w, h, self._barrier_version, len(self._current.strokes),
               len(self._current.rectangles), len(self._current.circles),
               len(self._current.arrows), len(self._current.fill_annotations))
        if self._barrier_cache is not None and self._barrier_cache_key == key:
            return self._barrier_cache

        mask_img = QImage(w, h, QImage.Format.Format_Grayscale8)
        mask_img.fill(255)
        mp = QPainter(mask_img)
        self._draw_layer_barriers(mp, self._current)
        mp.end()

        ptr = mask_img.bits()
        ptr.setsize(mask_img.sizeInBytes())
        stride = mask_img.bytesPerLine()
        raw = bytearray(ptr)

        if stride == w:
            self._barrier_cache = raw
        else:
            packed = bytearray(w * h)
            for row in range(h):
                src_off = row * stride
                dst_off = row * w
                packed[dst_off:dst_off + w] = raw[src_off:src_off + w]
            self._barrier_cache = packed
        self._barrier_cache_key = key
        return self._barrier_cache

    def _visited_to_fill_path(self, visited, w: int, h: int, ratio: float = 1.0) -> QPainterPath:
        path = QPainterPath()
        inv = 1.0 / ratio if ratio > 1.0 else 1.0
        if hasattr(visited, 'shape'):
            for y in range(h):
                row = visited[y]
                x = 0
                while x < w:
                    if row[x]:
                        start = x
                        while x < w and row[x]:
                            x += 1
                        path.addRect(QRectF(start * inv, y * inv, (x - start) * inv, inv))
                    else:
                        x += 1
        else:
            for y in range(h):
                x = 0
                while x < w:
                    if visited[y * w + x]:
                        start = x
                        while x < w and visited[y * w + x]:
                            x += 1
                        path.addRect(QRectF(start * inv, y * inv, (x - start) * inv, inv))
                    else:
                        x += 1
        return path

    def _flood_fill(self, click_pos: QPoint):
        if self._screenshot is None:
            return

        import numpy as np

        w, h = self._screenshot.width(), self._screenshot.height()
        x, y = click_pos.x(), click_pos.y()
        if x < 0 or x >= w or y < 0 or y >= h:
            return

        barrier = self._build_barrier_for_fill(w, h)
        if barrier[y * w + x] < 128:
            return

        barrier_arr = np.frombuffer(barrier, dtype=np.uint8).reshape(h, w)
        fillable = (barrier_arr >= 128)

        visited = np.zeros((h, w), dtype=bool)

        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if visited[cy, cx] or not fillable[cy, cx]:
                continue

            lx = cx
            while lx > 0 and fillable[cy, lx - 1] and not visited[cy, lx - 1]:
                lx -= 1

            rx = cx
            while rx < w - 1 and fillable[cy, rx + 1] and not visited[cy, rx + 1]:
                rx += 1

            visited[cy, lx:rx + 1] = True

            for ny in (cy - 1, cy + 1):
                if ny < 0 or ny >= h:
                    continue
                mask = fillable[ny, lx:rx + 1] & ~visited[ny, lx:rx + 1]
                indices = np.where(mask)[0] + lx
                if len(indices) > 1:
                    diffs = np.diff(indices)
                    needs_push = np.concatenate(([True], diffs > 1))
                    for fx in indices[needs_push]:
                        stack.append((fx, ny))
                elif len(indices) == 1:
                    stack.append((indices[0], ny))

        fill_path = self._visited_to_fill_path(visited, w, h)
        if fill_path.isEmpty():
            return

        if not hasattr(self._current, 'fill_annotations'):
            self._current.fill_annotations = []
        self._current.item_gen += 1
        self._current.fill_annotations.append((fill_path, QColor(self._color), self._opacity, self._current.item_gen))
        self._fill_cache_version += 1

    # ── Mouse handlers ────────────────────────────────────────────────

    def _make_stroke(self, point, pressure):
        return Stroke(QColor(self._color), self._width, self._tool, self._opacity, [(point, pressure)])

    def _find_text_at(self, pos):
        for i, (p, text, font, color, gen) in enumerate(self._current.text_items):
            fm = QFontMetrics(font)
            br = fm.tightBoundingRect(text)
            rect = QRect(p.x() + br.x() - 4, p.y() + br.y() - 4, br.width() + 8, br.height() + 8)
            if rect.contains(pos):
                return i
        return -1

    def _get_text_handle_rect(self, idx: int) -> QRect:
        if idx < 0 or idx >= len(self._current.text_items):
            return QRect()
        pos, text, font, color, gen = self._current.text_items[idx]
        br = QFontMetrics(font).boundingRect(text)
        text_rect = QRect(pos, br.size()).adjusted(-4, -4, 4, 4)
        hs = 6
        return QRect(text_rect.right() - hs, text_rect.bottom() - hs, hs, hs)

    def _get_text_delete_rect(self, idx: int) -> QRect:
        if idx < 0 or idx >= len(self._current.text_items):
            return QRect()
        pos, text, font, color, gen = self._current.text_items[idx]
        fm = QFontMetrics(font)
        br = fm.tightBoundingRect(text)
        text_rect = QRect(pos.x() + br.x() - 4, pos.y() + br.y() - 4, br.width() + 8, br.height() + 8)
        cx = text_rect.right() + 10
        cy = text_rect.top() - 10
        return QRect(cx - 12, cy - 12, 24, 24)

    def _find_text_handle_at(self, pos) -> int:
        if self._selected_text_idx < 0 or self._selected_text_idx >= len(self._current.text_items):
            return -1
        p, text, font, color, gen = self._current.text_items[self._selected_text_idx]
        fm = QFontMetrics(font)
        br = fm.tightBoundingRect(text)
        text_rect = QRect(p.x() + br.x() - 4, p.y() + br.y() - 4, br.width() + 8, br.height() + 8)
        
        hs = 6
        handle_positions = [
            (text_rect.left(), text_rect.top()),      # 0: top-left
            (text_rect.center().x(), text_rect.top()), # 1: top-center
            (text_rect.right(), text_rect.top()),      # 2: top-right
            (text_rect.left(), text_rect.center().y()),# 3: middle-left
            (text_rect.right(), text_rect.center().y()),# 4: middle-right
            (text_rect.left(), text_rect.bottom()),    # 5: bottom-left
            (text_rect.center().x(), text_rect.bottom()),# 6: bottom-center
            (text_rect.right(), text_rect.bottom()),   # 7: bottom-right
        ]
        
        for i, (hx, hy) in enumerate(handle_positions):
            handle_rect = QRect(hx - hs, hy - hs, hs * 2, hs * 2)
            if handle_rect.contains(pos):
                return i
        return -1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            logical_pos = self._widget_to_logical(pos)
            self._drawing = True

            if self._current.locked:
                if self._tool == TEXT_TOOL:
                    self._drawing = False
                    idx = self._find_text_at(logical_pos)
                    if idx >= 0:
                        self._selected_text_idx = idx
                        self._dragging_text = True
                        self._text_drag_offset = logical_pos - self._current.text_items[idx][0]
                    self.update()
                else:
                    self._drawing = False
                return

            if self._tool in ALL_BRUSHES:
                self._current_stroke = self._make_stroke(logical_pos, 1.0)
            elif self._tool in (SHAPE_ARROW, SHAPE_RECT, SHAPE_CIRCLE):
                self._shape_start = logical_pos
                self._shape_end = logical_pos
            elif self._tool == HAND_TOOL:
                self._panning = True
                self._pan_start = pos
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            elif self._tool == MOVE_TOOL:
                self._push_undo()
                self._moving = True
                self._move_start = logical_pos
                self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
            elif self._tool == ROTATE_TOOL:
                self._rotating = True
                self._rotate_start = logical_pos
                center = self._logical_center()
                self._rotate_start_angle = math.atan2(
                    logical_pos.y() - center.y(), logical_pos.x() - center.x()
                )
                self._push_undo()
                self._rotate_transform = QTransform()
                self._rotate_total_angle = 0.0
                self._build_rotate_view()
            elif self._tool == MIRROR_TOOL:
                self._mirroring = True
                self._push_undo()
                self._mirror_layer(self._current)
                self.update()
            elif self._tool == TEXT_TOOL:
                self._drawing = False
                delete_rect = self._get_text_delete_rect(self._selected_text_idx)
                if self._selected_text_idx >= 0 and not delete_rect.isEmpty() and delete_rect.contains(logical_pos):
                    self.delete_selected_text()
                    return
                handle_idx = self._find_text_handle_at(logical_pos)
                if self._selected_text_idx >= 0 and handle_idx >= 0:
                    self._resizing_text = True
                    self._resize_text_handle = handle_idx
                    self._resize_text_start_font = self._current.text_items[self._selected_text_idx][2]
                    self._resize_text_start_pos = logical_pos
                    return
                idx = self._find_text_at(logical_pos)
                if idx >= 0:
                    self._selected_text_idx = idx
                    self._text_press_idx = idx
                    self._text_press_pos = logical_pos
                    self._text_press_timer.start()
                    self._dragging_text = True
                    self._text_drag_offset = logical_pos - self._current.text_items[idx][0]
                else:
                    self._push_undo()
                    self._selected_text_idx = -1
                    self._add_text(logical_pos)
            elif self._tool == FILL_TOOL:
                self._drawing = False
                self._push_undo()
                self._flood_fill(logical_pos)
            self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        logical_pos = self._widget_to_logical(pos)
        if self._panning:
            delta = pos - self._pan_start
            self._pan_offset += delta
            self._pan_start = pos
            self.update()
        elif self._moving:
            delta = logical_pos - self._move_start
            self._move_layer(self._current, delta)
            self._move_start = logical_pos
            self.update()
        elif self._rotating:
            if self._rotate_transform is None:
                return
            center = self._logical_center()
            current_angle = math.atan2(
                logical_pos.y() - center.y(), logical_pos.x() - center.x()
            )
            total_angle = math.degrees(current_angle - self._rotate_start_angle)
            self._rotate_total_angle = total_angle
            cx, cy = center.x(), center.y()
            t = QTransform()
            t.translate(cx, cy)
            t.rotate(-total_angle)
            t.translate(-cx, -cy)
            self._rotate_transform = t
            self.update()
        elif self._resizing_text and self._selected_text_idx >= 0:
            p, text, font, color, gen = self._current.text_items[self._selected_text_idx]
            orig_br = QFontMetrics(self._resize_text_start_font).boundingRect(text)
            orig_w = max(orig_br.width(), 1)
            orig_h = max(orig_br.height(), 1)
            dx = logical_pos.x() - self._resize_text_start_pos.x()
            dy = logical_pos.y() - self._resize_text_start_pos.y()
            
            handle = self._resize_text_handle
            if handle in (0, 2, 5, 7):  # corners: proportional
                scale = max(0.3, 1.0 + (dx + dy) / max(orig_w, orig_h))
            elif handle in (1, 6):  # top/bottom edges: height only
                scale = max(0.3, 1.0 + dy / orig_h)
            else:  # left/right edges: width only
                scale = max(0.3, 1.0 + dx / orig_w)
            
            new_size = max(4, int(self._resize_text_start_font.pointSize() * scale))
            new_font = QFont(self._resize_text_start_font)
            new_font.setPointSize(new_size)
            self._current.text_items[self._selected_text_idx] = (p, text, new_font, color, gen)
            self.update()
        elif self._dragging_text and self._selected_text_idx >= 0:
            p, text, font, color, gen = self._current.text_items[self._selected_text_idx]
            self._current.text_items[self._selected_text_idx] = (logical_pos - self._text_drag_offset, text, font, color, gen)
            self.update()
        elif self._drawing and not self._current.locked:
            if self._tool in ALL_BRUSHES and self._current_stroke:
                self._current_stroke.add_point(logical_pos, 1.0)
            elif self._tool in (SHAPE_ARROW, SHAPE_RECT, SHAPE_CIRCLE):
                self._shape_end = logical_pos
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._panning:
                self._panning = False
                self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
                return
            if self._moving:
                self._moving = False
                self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
                return
            if self._rotating:
                self._rotating = False
                if self._rotate_transform is not None and self._rotate_total_angle != 0.0:
                    self._rotate_layer(self._current, self._rotate_total_angle)
                self._rotate_transform = None
                self._rotate_total_angle = 0.0
                self._rotate_view = None
                self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
                return
            if self._resizing_text:
                self._resizing_text = False
                self._resize_text_start_font = None
                self._resize_text_handle = -1
                return
            if self._dragging_text:
                self._text_press_timer.stop()
                self._dragging_text = False
                return
            if not self._drawing or self._current.locked:
                self._drawing = False
                return
            self._drawing = False
            self._push_undo()
            if self._tool in ALL_BRUSHES and self._current_stroke:
                if len(self._current_stroke.points) > 1:
                    self._current.item_gen += 1
                    self._current.strokes.append(self._current_stroke)
                    self._current.stroke_gens.append(self._current.item_gen)
                    if self._current_stroke.brush_type == BRUSH_ERASER:
                        self._rebuild_layer_erased_area(self._current)
                        self._current.clip_gen = self._current.item_gen
                self._current_stroke = None
            elif self._tool == SHAPE_RECT and self._shape_start and self._shape_end:
                self._current.item_gen += 1
                self._current.rectangles.append(
                    (self._shape_start, self._shape_end, QColor(self._color),
                     self._width, self._opacity, self._current.item_gen))
                self._shape_start = None
                self._shape_end = None
            elif self._tool == SHAPE_ARROW and self._shape_start and self._shape_end:
                self._current.item_gen += 1
                self._current.arrows.append(
                    (self._shape_start, self._shape_end, QColor(self._color),
                     self._width, self._opacity, self._current.item_gen))
                self._shape_start = None
                self._shape_end = None
            elif self._tool == SHAPE_CIRCLE and self._shape_start and self._shape_end:
                self._current.item_gen += 1
                self._current.circles.append(
                    (self._shape_start, self._shape_end, QColor(self._color),
                     self._width, self._opacity, self._current.item_gen))
                self._shape_start = None
                self._shape_end = None
            self.update()

    def _rebuild_layer_erased_area(self, layer: AnnotationLayer):
        layer.erased_area = QPainterPath()
        for stroke in layer.strokes:
            if stroke.brush_type != BRUSH_ERASER or len(stroke.points) < 2:
                continue
            path = QPainterPath()
            path.moveTo(QPointF(stroke.points[0][0]))
            for p, _ in stroke.points[1:]:
                path.lineTo(QPointF(p))
            stroker = QPainterPathStroker()
            stroker.setWidth(max(stroke.width, 2.0))
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            layer.erased_area = layer.erased_area.united(stroker.createStroke(path))

    def _move_layer(self, layer: AnnotationLayer, delta: QPoint):
        for stroke in layer.strokes:
            stroke.points = [(QPoint(p.x() + delta.x(), p.y() + delta.y()), pressure) for p, pressure in stroke.points]

        layer.rectangles = [
            (QPoint(s.x() + delta.x(), s.y() + delta.y()), QPoint(e.x() + delta.x(), e.y() + delta.y()), c, w, o, g)
            for s, e, c, w, o, g in layer.rectangles
        ]
        layer.circles = [
            (QPoint(s.x() + delta.x(), s.y() + delta.y()), QPoint(e.x() + delta.x(), e.y() + delta.y()), c, w, o, g)
            for s, e, c, w, o, g in layer.circles
        ]
        layer.arrows = [
            (QPoint(s.x() + delta.x(), s.y() + delta.y()), QPoint(e.x() + delta.x(), e.y() + delta.y()), c, w, o, g)
            for s, e, c, w, o, g in layer.arrows
        ]
        layer.text_items = [
            (QPoint(p.x() + delta.x(), p.y() + delta.y()), t, f, c, g)
            for p, t, f, c, g in layer.text_items
        ]
        if hasattr(layer, 'fill_annotations'):
            new_fills = []
            for f, c, o, g in layer.fill_annotations:
                t = QPainterPath(f)
                t.translate(delta.x(), delta.y())
                new_fills.append((t, c, o, g))
            layer.fill_annotations = new_fills
            self._fill_cache.clear()
        self._barrier_version += 1

    def _build_rotate_view(self):
        if self._screenshot is None:
            self._rotate_view = None
            return
        w = int(self._screenshot.width())
        h = int(self._screenshot.height())
        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._render_layer_annotations(p, self._current)
        p.end()
        self._rotate_view = pixmap

    def _rotate_layer(self, layer: AnnotationLayer, angle: float):
        import math
        lc = self._logical_center()
        cx = lc.x()
        cy = lc.y()
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        def rotate_point(p):
            dx = p.x() - cx
            dy = p.y() - cy
            return QPoint(int(cx + dx * cos_a - dy * sin_a), int(cy + dx * sin_a + dy * cos_a))

        for s in layer.strokes:
            s.points = [(rotate_point(p), pr) for p, pr in s.points]
        layer.arrows = [
            (rotate_point(s), rotate_point(e), c, w, o, g)
            for s, e, c, w, o, g in layer.arrows
        ]
        layer.text_items = [
            (rotate_point(p), t, f, c, g)
            for p, t, f, c, g in layer.text_items
        ]
        if hasattr(layer, 'fill_annotations'):
            from PyQt6.QtGui import QTransform
            rot = QTransform(cos_a, sin_a, 0, -sin_a, cos_a, 0,
                             cx * (1 - cos_a) + cy * sin_a,
                             cy * (1 - cos_a) - cx * sin_a, 1)
            new_fills = []
            for f, c, o, g in layer.fill_annotations:
                new_fills.append((rot.map(f), c, o, g))
            layer.fill_annotations = new_fills
            self._fill_cache_version += 1
        self._barrier_version += 1

    def _mirror_layer(self, layer: AnnotationLayer):
        cx = int(self._logical_center().x())

        def mirror_point(p):
            return QPoint(2 * cx - p.x(), p.y())

        for s in layer.strokes:
            s.points = [(mirror_point(p), pr) for p, pr in s.points]
        layer.rectangles = [
            (mirror_point(s), mirror_point(e), c, w, o, g)
            for s, e, c, w, o, g in layer.rectangles
        ]
        layer.circles = [
            (mirror_point(s), mirror_point(e), c, w, o, g)
            for s, e, c, w, o, g in layer.circles
        ]
        layer.arrows = [
            (mirror_point(s), mirror_point(e), c, w, o, g)
            for s, e, c, w, o, g in layer.arrows
        ]
        layer.text_items = [
            (mirror_point(p), t, f, c, g)
            for p, t, f, c, g in layer.text_items
        ]
        if hasattr(layer, 'fill_annotations'):
            from PyQt6.QtGui import QTransform
            mir = QTransform(-1, 0, 0, 0, 1, 0, 2 * cx, 0, 1)
            new_fills = []
            for f, c, o, g in layer.fill_annotations:
                new_fills.append((mir.map(f), c, o, g))
            layer.fill_annotations = new_fills
            self._fill_cache_version += 1
        self._barrier_version += 1

    # ── Text ──────────────────────────────────────────────────────────

    def _add_text(self, pos: QPoint, edit_idx: int = -1):
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(None, "Add Text" if edit_idx < 0 else "Edit Text",
                                        "Enter annotation text:")
        if ok and text:
            font = QFont("Arial", 14)
            if edit_idx >= 0:
                p, _, _, c, gen = self._current.text_items[edit_idx]
                self._current.text_items[edit_idx] = (p, text, font, c, gen)
            else:
                self._current.item_gen += 1
                self._current.text_items.append((pos, text, font, QColor(self._color), self._current.item_gen))

    def _on_text_long_press(self):
        if self._text_press_idx >= 0 and self._text_press_idx < len(self._current.text_items):
            self._selected_text_idx = self._text_press_idx
            self._resizing_text = True
            self._resize_text_handle = 7
            self._resize_text_start_font = self._current.text_items[self._text_press_idx][2]
            self._resize_text_start_pos = self._text_press_pos
            self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._tool == TEXT_TOOL:
            logical_pos = self._widget_to_logical(event.pos())
            for i, (p, text, font, color, gen) in enumerate(self._current.text_items):
                fm = QFontMetrics(font)
                br = fm.tightBoundingRect(text)
                rect = QRect(p.x() + br.x() - 4, p.y() + br.y() - 4, br.width() + 8, br.height() + 8)
                if rect.contains(logical_pos):
                    self._add_text(p, edit_idx=i)
                    return

    # ── Keyboard ──────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key.Key_Escape:
            self.close()
            self.closed.emit()
        elif key == Qt.Key.Key_Z and mods & Qt.KeyboardModifier.ControlModifier:
            self._undo()
        elif key == Qt.Key.Key_Z and mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            self._redo()
        elif key == Qt.Key.Key_Delete and self._tool == TEXT_TOOL:
            self.delete_selected_text()
        elif key == Qt.Key.Key_P:
            self._tool = BRUSH_PEN
        elif key == Qt.Key.Key_C:
            self._tool = BRUSH_CALLIGRAPHY
        elif key == Qt.Key.Key_S:
            self._tool = BRUSH_SPRAY
        elif key == Qt.Key.Key_M:
            self._tool = BRUSH_MARKER
        elif key == Qt.Key.Key_E:
            self._tool = BRUSH_ERASER
        elif key == Qt.Key.Key_H:
            self._tool = BRUSH_HIGHLIGHTER
        elif key == Qt.Key.Key_A:
            self._tool = SHAPE_ARROW
        elif key == Qt.Key.Key_R:
            self._tool = SHAPE_RECT
        elif key == Qt.Key.Key_O:
            self._tool = SHAPE_CIRCLE
        elif key == Qt.Key.Key_T:
            self._tool = TEXT_TOOL
        elif key == Qt.Key.Key_B:
            self._tool = BRUSH_PENCIL
        elif key == Qt.Key.Key_I:
            self._tool = FILL_TOOL
        elif key == Qt.Key.Key_G:
            self._tool = HAND_TOOL
        elif key == Qt.Key.Key_V:
            self._tool = MOVE_TOOL
        elif key == Qt.Key.Key_X:
            self._tool = MIRROR_TOOL

    # ── Undo / Redo ────────────────────────────────────────────────────

    def _push_undo(self):
        c = self._current
        self._undo_stack.append((
            self._active_layer_idx,
            list(c.strokes),
            list(c.stroke_gens),
            list(c.rectangles),
            list(c.arrows),
            list(c.circles),
            list(c.text_items) if hasattr(c, 'text_items') else [],
            list(c.fill_annotations) if hasattr(c, 'fill_annotations') else [],
        ))
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _undo(self):
        c = self._current
        if c.locked:
            return
        if not self._undo_stack:
            return
        self._redo_stack.append((
            self._active_layer_idx,
            list(c.strokes),
            list(c.stroke_gens),
            list(c.rectangles),
            list(c.arrows),
            list(c.circles),
            list(c.text_items),
            list(c.fill_annotations) if hasattr(c, 'fill_annotations') else [],
        ))
        state = self._undo_stack.pop()
        layer_idx = state[0]
        layer = self._layers[layer_idx]
        layer.strokes = state[1]
        layer.stroke_gens = state[2]
        layer.rectangles = state[3]
        layer.arrows = state[4]
        layer.circles = state[5]
        layer.text_items = state[6]
        layer.fill_annotations = state[7]
        self._barrier_version += 1
        self._fill_cache_version += 1
        self._selected_text_idx = -1
        self.update()

    def _redo(self):
        c = self._current
        if c.locked:
            return
        if not self._redo_stack:
            return
        self._undo_stack.append((
            self._active_layer_idx,
            list(c.strokes),
            list(c.stroke_gens),
            list(c.rectangles),
            list(c.arrows),
            list(c.circles),
            list(c.text_items),
            list(c.fill_annotations) if hasattr(c, 'fill_annotations') else [],
        ))
        state = self._redo_stack.pop()
        layer_idx = state[0]
        layer = self._layers[layer_idx]
        layer.strokes = state[1]
        layer.stroke_gens = state[2]
        layer.rectangles = state[3]
        layer.arrows = state[4]
        layer.circles = state[5]
        layer.text_items = state[6]
        layer.fill_annotations = state[7]
        self._barrier_version += 1
        self._fill_cache_version += 1
        self._selected_text_idx = -1
        self.update()

    def clear_current_layer(self):
        c = self._current
        if c.locked:
            return
        self._push_undo()
        c.strokes.clear()
        c.stroke_gens.clear()
        c.rectangles.clear()
        c.arrows.clear()
        c.circles.clear()
        c.text_items.clear()
        c.fill_annotations.clear()
        self._fill_cache_version += 1
        self._selected_text_idx = -1
        self.update()

    def delete_selected_text(self):
        if self._selected_text_idx >= 0 and self._selected_text_idx < len(self._current.text_items):
            self._push_undo()
            self._current.text_items.pop(self._selected_text_idx)
            self._selected_text_idx = -1
            self.update()

    # ── Capture ───────────────────────────────────────────────────────

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def _capture_and_emit(self):
        if self._screenshot is None:
            return
        result = QPixmap(self._screenshot.size())
        result.fill(QColor(0, 0, 0, 0))
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(0, 0, self._screenshot)

        for layer in self._layers:
            if not layer.visible:
                continue
            self._render_layer_to_painter(painter, layer)

        painter.end()
        self.annotation_captured.emit(result)

    def _render_layer_to_painter(self, painter: QPainter, layer: AnnotationLayer):
        for fill_path, color, opacity, gen in getattr(layer, 'fill_annotations', []):
            painter.setOpacity(opacity)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPath(fill_path)
        painter.setOpacity(1.0)

        for stroke in layer.strokes:
            if stroke.brush_type != BRUSH_ERASER:
                self._render_brush(painter, stroke)

        for start, end, color, width, opacity, _ in layer.rectangles:
            painter.setOpacity(opacity)
            pen = QPen(color, width, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRect(start, end).normalized())

        for start, end, color, width, opacity, _ in layer.circles:
            painter.setOpacity(opacity)
            pen = QPen(color, width, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRect(start, end).normalized())

        for start, end, color, width, opacity, _ in layer.arrows:
            self._draw_arrow(painter, start, end, color, width, opacity)

        for pos, text, font, color, _ in layer.text_items:
            painter.setFont(font)
            painter.setPen(QPen(color))
            painter.drawText(pos, text)

        painter.setOpacity(1.0)
