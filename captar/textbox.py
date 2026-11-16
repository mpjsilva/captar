"""Caixa de texto editável sobre a captura."""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QTextEdit, QWidget

ACCENT = QColor("#3daee9")

MIN_FONT, MAX_FONT = 10, 96


class _Grip(QWidget):
    """Alça no canto inferior direito que redimensiona a caixa de texto."""

    SIZE = 12

    def __init__(self, box):
        super().__init__(box)
        self.box = box
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self._press = None

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ACCENT)
        painter.drawRect(2, 2, self.SIZE - 4, self.SIZE - 4)

    def mousePressEvent(self, event):
        self._press = (event.globalPosition(), QRectF(self.box.shape.rect))

    def mouseMoveEvent(self, event):
        if self._press is None:
            return
        start, rect = self._press
        delta = event.globalPosition() - start
        min_h = self.box.shape.font_size * 1.4
        rect.setWidth(max(40.0, rect.width() + delta.x()))
        rect.setHeight(max(min_h, rect.height() + delta.y()))
        self.box.shape.rect = rect
        self._press = (event.globalPosition(), QRectF(rect))
        self.box.relayout()

    def mouseReleaseEvent(self, _event):
        self._press = None


class TextBox(QFrame):
    """Caixa de texto editável sobre a captura: arrastar a borda move,
    a alça do canto redimensiona, Ctrl+roda/Ctrl+±/Ctrl+= muda o tamanho."""

    MARGIN = 6
    finished = Signal()

    def __init__(self, overlay, shape):
        super().__init__(overlay)
        self.overlay = overlay
        self.shape = shape
        self._drag = None
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        edit = QTextEdit(self)
        edit.setAcceptRichText(False)
        edit.setFrameShape(QFrame.Shape.NoFrame)
        edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        edit.document().setDocumentMargin(0)
        edit.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        edit.setPlainText(shape.text)
        edit.installEventFilter(self)
        edit.textChanged.connect(self._on_text)
        self.edit = edit
        self.grip = _Grip(self)
        self.apply_style()
        self.relayout()

    # --- Aparência ------------------------------------------------------

    def apply_style(self):
        self.edit.setFont(self.shape.font())
        self.edit.setStyleSheet(
            "QTextEdit { background: transparent;"
            f" color: {self.shape.color.name()}; }}"
        )
        self.edit.document().setDefaultFont(self.shape.font())
        self._fit_height()

    def relayout(self):
        m = self.MARGIN
        rect = self.shape.rect.translated(-self.overlay._origin)
        self.setGeometry(rect.adjusted(-m, -m, m, m).toRect())
        self.edit.setGeometry(m, m, int(rect.width()), int(rect.height()))
        self.grip.move(self.width() - _Grip.SIZE, self.height() - _Grip.SIZE)
        self.update()

    def _fit_height(self):
        """Cresce a caixa para baixo quando o texto não cabe."""
        self.edit.document().setTextWidth(self.shape.rect.width())
        needed = self.edit.document().size().height() + 2
        if needed > self.shape.rect.height():
            self.shape.rect.setHeight(needed)
            self.relayout()

    def _on_text(self):
        self.shape.text = self.edit.toPlainText()
        self._fit_height()

    def change_size(self, step):
        size = max(MIN_FONT, min(MAX_FONT, self.shape.font_size + step))
        if size != self.shape.font_size:
            self.shape.font_size = size
            self.apply_style()

    def paintEvent(self, _event):
        painter = QPainter(self)
        pen = QPen(QColor(255, 255, 255, 170), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QColor(20, 22, 24, 60))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    # --- Interação ------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is self.edit:
            etype = event.type()
            if etype == event.Type.KeyPress:
                key = event.key()
                ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                if key == Qt.Key.Key_Escape or (
                    ctrl and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                ):
                    self.finished.emit()
                    return True
                if ctrl and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                    self.change_size(2)
                    return True
                if ctrl and key == Qt.Key.Key_Minus:
                    self.change_size(-2)
                    return True
            elif etype == event.Type.Wheel and (
                event.modifiers() & Qt.KeyboardModifier.ControlModifier
            ):
                self.change_size(2 if event.angleDelta().y() > 0 else -2)
                return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        self.change_size(2 if event.angleDelta().y() > 0 else -2)

    def mousePressEvent(self, event):
        self._drag = (event.globalPosition(), QPointF(self.shape.rect.topLeft()))

    def mouseMoveEvent(self, event):
        if self._drag is None:
            return
        start, top_left = self._drag
        self.shape.rect.moveTopLeft(top_left + (event.globalPosition() - start))
        self.relayout()

    def mouseReleaseEvent(self, _event):
        self._drag = None
        self.edit.setFocus()

