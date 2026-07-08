from PyQt6.QtCore import QPoint, QPointF
from PyQt6.QtGui import QColor, QFont, QPainterPath, QPixmap
from core.canvas import Stroke


class AnnotationLayer:
    def __init__(self, name: str = "Layer", locked: bool = False):
        self.name = name
        self.visible = True
        self.locked = locked
        self.strokes: list[Stroke] = []
        self.stroke_gens: list[int] = []
        self.rectangles: list[tuple[QPoint, QPoint, QColor, float, float, int]] = []
        self.circles: list[tuple[QPoint, QPoint, QColor, float, float, int]] = []
        self.arrows: list[tuple[QPoint, QPoint, QColor, float, float, int]] = []
        self.text_items: list[tuple[QPoint, str, QFont, QColor, int]] = []
        self.fill_annotations: list[tuple[QPainterPath, QColor, float, int]] = []
        self.raster: QPixmap | None = None
        self.erased_area = QPainterPath()
        self.clip_gen = 0
        self.item_gen = 0
