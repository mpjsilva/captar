"""Formas de anotação desenhadas sobre a captura.

Todas usam coordenadas lógicas da área de trabalho. Cada forma sabe se
desenhar, se copiar (para desfazer/refazer), se mover e dizer se um ponto
cai sobre ela.
"""

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
)


@dataclass
class Shape:
    color: QColor = field(default_factory=lambda: QColor("#e01b24"))
    width: int = 3

    def draw(self, painter: QPainter) -> None:  # pragma: no cover - base
        raise NotImplementedError

    def clone(self):
        raise NotImplementedError

    def translate(self, delta: QPointF) -> None:
        raise NotImplementedError

    def path(self) -> QPainterPath:
        raise NotImplementedError

    def contains(self, point: QPointF) -> bool:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(10.0, self.width + 8.0))
        return stroker.createStroke(self.path()).contains(point)

    def bounds(self) -> QRectF:
        pad = self.width / 2 + 2
        return self.path().boundingRect().adjusted(-pad, -pad, pad, pad)


@dataclass
class _TwoPoint(Shape):
    start: QPointF = field(default_factory=QPointF)
    end: QPointF = field(default_factory=QPointF)

    def clone(self):
        return type(self)(color=QColor(self.color), width=self.width,
                          start=QPointF(self.start), end=QPointF(self.end))

    def translate(self, delta):
        self.start += delta
        self.end += delta


@dataclass
class Line(_TwoPoint):
    def path(self):
        path = QPainterPath(self.start)
        path.lineTo(self.end)
        return path

    def draw(self, painter):
        pen = QPen(self.color, self.width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(self.start, self.end)


@dataclass
class Arrow(_TwoPoint):
    def path(self):
        path = QPainterPath(self.start)
        path.lineTo(self.end)
        return path

    def draw(self, painter):
        if QLineF(self.start, self.end).length() < 1:
            return
        angle = math.atan2(self.end.y() - self.start.y(),
                           self.end.x() - self.start.x())
        size = max(12.0, self.width * 4.0)
        spread = math.radians(28)
        p1 = QPointF(self.end.x() - size * math.cos(angle - spread),
                     self.end.y() - size * math.sin(angle - spread))
        p2 = QPointF(self.end.x() - size * math.cos(angle + spread),
                     self.end.y() - size * math.sin(angle + spread))
        # A haste para antes da ponta para não engrossar o bico.
        back = QPointF(self.end.x() - size * 0.8 * math.cos(angle),
                       self.end.y() - size * 0.8 * math.sin(angle))
        pen = QPen(self.color, self.width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(self.start, back)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.color)
        painter.drawPolygon(QPolygonF([self.end, p1, p2]))


@dataclass
class Rectangle(_TwoPoint):
    def path(self):
        path = QPainterPath()
        path.addRect(QRectF(self.start, self.end).normalized())
        return path

    def draw(self, painter):
        pen = QPen(self.color, self.width)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(self.start, self.end).normalized())


@dataclass
class Pen(Shape):
    """Traço livre (lápis)."""

    points: list = field(default_factory=list)
    alpha: int = 255

    def clone(self):
        return type(self)(color=QColor(self.color), width=self.width,
                          points=[QPointF(p) for p in self.points],
                          alpha=self.alpha)

    def translate(self, delta):
        self.points = [p + delta for p in self.points]

    def path(self):
        path = QPainterPath()
        if self.points:
            path.moveTo(self.points[0])
            for point in self.points[1:]:
                path.lineTo(point)
        return path

    def draw(self, painter):
        if not self.points:
            return
        color = QColor(self.color)
        color.setAlpha(self.alpha)
        pen = QPen(color, self.width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if len(self.points) == 1:
            painter.drawPoint(self.points[0])
        else:
            painter.drawPath(self.path())


@dataclass
class Marker(Pen):
    """Marca-texto: traço largo e translúcido."""

    alpha: int = 110

    def draw(self, painter):
        if not self.points:
            return
        color = QColor(self.color)
        color.setAlpha(self.alpha)
        pen = QPen(color, self.width * 5)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())

    def contains(self, point):
        stroker = QPainterPathStroker()
        stroker.setWidth(self.width * 5 + 6)
        return stroker.createStroke(self.path()).contains(point)

    def bounds(self):
        pad = self.width * 2.5 + 2
        return self.path().boundingRect().adjusted(-pad, -pad, pad, pad)


@dataclass
class Text(Shape):
    """Caixa de texto: quebra de linha dentro de ``rect``."""

    rect: QRectF = field(default_factory=lambda: QRectF(0, 0, 220, 40))
    text: str = ""
    font_size: int = 24  # em pixels lógicos
    editing: bool = False

    FLAGS = (Qt.TextFlag.TextWordWrap.value
             | Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignTop.value)

    def font(self) -> QFont:
        font = QFont()
        font.setPixelSize(self.font_size)
        font.setBold(True)
        return font

    def clone(self):
        return Text(color=QColor(self.color), width=self.width,
                    rect=QRectF(self.rect), text=self.text,
                    font_size=self.font_size)

    def translate(self, delta):
        self.rect.translate(delta)

    def path(self):
        path = QPainterPath()
        path.addRect(self.rect)
        return path

    def contains(self, point):
        return self.rect.adjusted(-4, -4, 4, 4).contains(point)

    def bounds(self):
        return self.rect.adjusted(-2, -2, 2, 2)

    def draw(self, painter):
        if not self.text or self.editing:
            return
        painter.setFont(self.font())
        painter.setPen(QPen(self.color))
        painter.drawText(self.rect, self.FLAGS, self.text)
