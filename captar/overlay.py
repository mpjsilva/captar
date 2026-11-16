"""Sobreposição de seleção/anotação: uma janela por monitor.

No Wayland uma janela não pode cobrir vários monitores, então criamos uma
janela em tela cheia por tela, todas desenhando o mesmo estado (Session).
"""

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

from .shapes import Arrow, Line, Marker, Pen, Rectangle, Text
from .textbox import MAX_FONT, MIN_FONT, TextBox

TOOL_SELECT = "select"
TOOL_PEN = "pen"
TOOL_LINE = "line"
TOOL_ARROW = "arrow"
TOOL_RECT = "rect"
TOOL_MARKER = "marker"
TOOL_TEXT = "text"
TOOL_MOVE = "move"

TOOL_KEYS = {
    Qt.Key.Key_S: TOOL_SELECT,
    Qt.Key.Key_P: TOOL_PEN,
    Qt.Key.Key_L: TOOL_LINE,
    Qt.Key.Key_A: TOOL_ARROW,
    Qt.Key.Key_R: TOOL_RECT,
    Qt.Key.Key_M: TOOL_MARKER,
    Qt.Key.Key_T: TOOL_TEXT,
    Qt.Key.Key_V: TOOL_MOVE,
}

DIM_COLOR = QColor(0, 0, 0, 140)
ACCENT = QColor("#3daee9")
HANDLE = 8
MAG_ZOOM = 8
MAG_PIXELS = 15  # região ampliada: 15 × 15 pixels


class Session:
    """Estado compartilhado entre as sobreposições de cada monitor."""

    def __init__(self, screenshot: QPixmap, on_finish=None):
        self.screenshot = screenshot
        self.image = screenshot.toImage()
        self.shapes = []
        self.undo_stack = []
        self.redo_stack = []
        self.tool = TOOL_SELECT
        self.color = QColor("#e01b24")
        self.width = 4
        self.text_size = 24
        self.selection = None  # QRectF em coordenadas lógicas da área de trabalho
        self.picked = None  # forma escolhida com a ferramenta Mover
        self.on_finish = on_finish
        self.listeners = []
        self._overlays = []
        self._finished = False

        screens = QGuiApplication.screens()
        left = min(s.geometry().x() for s in screens)
        top = min(s.geometry().y() for s in screens)
        right = max(s.geometry().x() + s.geometry().width() for s in screens)
        self.origin = QPointF(left, top)
        width = right - left
        self.scale = screenshot.width() / width if width else 1.0

    # --- Observadores --------------------------------------------------

    def _notify(self, what, value):
        for listener in list(self.listeners):
            listener(what, value)

    def set_tool(self, tool):
        for overlay in self._overlays:
            overlay.close_text_editor()
        self.tool = tool
        if tool != TOOL_MOVE:
            self.picked = None
        self._notify("tool", tool)
        self.refresh()

    def set_color(self, color):
        self.color = QColor(color)
        if self.picked is not None and not isinstance(self.picked, Text):
            self.checkpoint()
            self.picked.color = QColor(color)
        for overlay in self._overlays:
            overlay.recolor_text(self.color)
        self._notify("color", self.color)
        self.refresh()

    def set_width(self, width):
        self.width = width
        if self.picked is not None and not isinstance(self.picked, Text):
            self.checkpoint()
            self.picked.width = width
        self._notify("width", width)
        self.refresh()

    def change_text_size(self, step):
        self.text_size = max(MIN_FONT, min(MAX_FONT, self.text_size + step))
        for overlay in self._overlays:
            overlay.resize_text(step)

    # --- Desfazer / refazer --------------------------------------------

    def _snapshot(self):
        return [shape.clone() for shape in self.shapes]

    def checkpoint(self):
        """Guarda o estado atual antes de uma alteração."""
        self.undo_stack.append(self._snapshot())
        del self.undo_stack[:-100]
        self.redo_stack.clear()

    def undo(self):
        for overlay in self._overlays:
            overlay.close_text_editor()
        if self.undo_stack:
            self.redo_stack.append(self._snapshot())
            self.shapes = self.undo_stack.pop()
            self.picked = None
            self.refresh()

    def redo(self):
        for overlay in self._overlays:
            overlay.close_text_editor()
        if self.redo_stack:
            self.undo_stack.append(self._snapshot())
            self.shapes = self.redo_stack.pop()
            self.picked = None
            self.refresh()

    def delete_picked(self):
        if self.picked is not None and self.picked in self.shapes:
            self.checkpoint()
            self.shapes.remove(self.picked)
            self.picked = None
            self.refresh()

    # --- Janelas -------------------------------------------------------

    def add_overlay(self, overlay):
        self._overlays.append(overlay)

    def refresh(self):
        for overlay in self._overlays:
            overlay.update()

    def finish(self, action):
        if self._finished:
            return
        self._finished = True
        for overlay in self._overlays:
            overlay.close_text_editor()
        self.picked = None
        for overlay in self._overlays:
            overlay.close()
        if self.on_finish is not None:
            self.on_finish(action, self)


def _handles(rect: QRectF):
    """Alças de redimensionamento: id -> centro."""
    cx, cy = rect.center().x(), rect.center().y()
    l, t, r, b = rect.left(), rect.top(), rect.right(), rect.bottom()
    return {
        "tl": QPointF(l, t), "t": QPointF(cx, t), "tr": QPointF(r, t),
        "l": QPointF(l, cy), "r": QPointF(r, cy),
        "bl": QPointF(l, b), "b": QPointF(cx, b), "br": QPointF(r, b),
    }


_HANDLE_CURSORS = {
    "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
    "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
    "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
    "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
}

_DRAW_TOOLS = {
    TOOL_LINE: Line,
    TOOL_ARROW: Arrow,
    TOOL_RECT: Rectangle,
}


class Overlay(QWidget):
    selection_changed = Signal(object)

    def __init__(self, session: Session, screen):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.session = session
        self.screen = screen
        self._mode = None  # new-sel, move-sel, resize-sel, draw, move-shape
        self._press_pos = None
        self._press_rect = None
        self._handle = None
        self._active_shape = None
        self._editor = None
        self._cursor = None  # posição do mouse (área de trabalho) para a lupa

        geometry = screen.geometry()
        self._origin = QPointF(geometry.x(), geometry.y())

        self.setScreen(screen)
        self.setGeometry(geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        session.add_overlay(self)

    # --- Conversões de coordenadas -------------------------------------

    def _to_desktop(self, pos) -> QPointF:
        return QPointF(pos.x() + self._origin.x(), pos.y() + self._origin.y())

    def _to_local(self, point: QPointF) -> QPointF:
        return QPointF(point.x() - self._origin.x(), point.y() - self._origin.y())

    def _local_rect(self, rect: QRectF) -> QRectF:
        return rect.translated(-self._origin)

    def _source_rect(self, local: QRectF) -> QRectF:
        """Converte um retângulo local (px lógicos) para px da imagem."""
        s = self.session
        top_left = self._to_desktop(local.topLeft())
        return QRectF(
            (top_left.x() - s.origin.x()) * s.scale,
            (top_left.y() - s.origin.y()) * s.scale,
            local.width() * s.scale,
            local.height() * s.scale,
        )

    # --- Pintura --------------------------------------------------------

    def paintEvent(self, _event):
        session = self.session
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        screen_rect = QRectF(0, 0, self.width(), self.height())

        painter.drawPixmap(screen_rect, session.screenshot,
                           self._source_rect(screen_rect))
        painter.fillRect(screen_rect, DIM_COLOR)

        sel = session.selection
        local = None
        if sel is not None and not sel.isEmpty():
            local = self._local_rect(sel)
            visible = local.intersected(screen_rect)
            if not visible.isEmpty():
                painter.drawPixmap(visible, session.screenshot,
                                   self._source_rect(visible))

        painter.save()
        painter.translate(-self._origin.x(), -self._origin.y())
        if sel is not None and not sel.isEmpty():
            painter.setClipRect(sel)
        for shape in session.shapes:
            shape.draw(painter)
        if self._active_shape is not None:
            self._active_shape.draw(painter)
        painter.setClipping(False)
        if session.picked is not None and session.picked in session.shapes:
            pen = QPen(ACCENT, 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(session.picked.bounds())
        painter.restore()

        if local is not None and local.intersects(screen_rect):
            self._paint_selection_frame(painter, local)

        if self._show_magnifier():
            self._paint_magnifier(painter)

    def _paint_selection_frame(self, painter, local):
        painter.setPen(QPen(ACCENT, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(local)
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(ACCENT, 1))
        for center in _handles(local).values():
            painter.drawRect(QRectF(center.x() - HANDLE / 2, center.y() - HANDLE / 2,
                                    HANDLE, HANDLE))

        # Tamanho em pixels reais da imagem.
        s = self.session
        label = f"{round(local.width() * s.scale)} × {round(local.height() * s.scale)}"
        font = QFont()
        font.setPixelSize(12)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        box = QRectF(0, 0, metrics.horizontalAdvance(label) + 12, metrics.height() + 6)
        box.moveBottomLeft(QPointF(local.left(), local.top() - 4))
        if box.top() < 0:
            box.moveTopLeft(QPointF(local.left() + 4, local.top() + 4))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 22, 24, 210))
        painter.drawRoundedRect(box, 4, 4)
        painter.setPen(QColor("#eff0f1"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)

    def _show_magnifier(self):
        return (
            self._cursor is not None
            and self.session.tool == TOOL_SELECT
            and self._mode in (None, "new-sel", "resize-sel")
            and (self._mode is not None or self.session.selection is None
                 or self.session.selection.isEmpty())
        )

    def _paint_magnifier(self, painter):
        s = self.session
        pos = self._cursor
        px = int((pos.x() - s.origin.x()) * s.scale)
        py = int((pos.y() - s.origin.y()) * s.scale)
        half = MAG_PIXELS // 2
        size = MAG_PIXELS * MAG_ZOOM

        local = self._to_local(pos)
        box = QRectF(local.x() + 20, local.y() + 20, size, size)
        if box.right() + 4 > self.width():
            box.moveRight(local.x() - 20)
        if box.bottom() + 44 > self.height():
            box.moveBottom(local.y() - 64)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.fillRect(box, QColor("#000000"))
        painter.drawImage(box, s.image,
                          QRectF(px - half, py - half, MAG_PIXELS, MAG_PIXELS))
        center = QRectF(box.x() + half * MAG_ZOOM, box.y() + half * MAG_ZOOM,
                        MAG_ZOOM, MAG_ZOOM)
        painter.setPen(QPen(QColor(61, 174, 233, 120), MAG_ZOOM))
        painter.drawLine(QLineF(box.left(), center.center().y(),
                                center.left() - MAG_ZOOM / 2, center.center().y()))
        painter.drawLine(QLineF(center.right() + MAG_ZOOM / 2, center.center().y(),
                                box.right(), center.center().y()))
        painter.drawLine(QLineF(center.center().x(), box.top(),
                                center.center().x(), center.top() - MAG_ZOOM / 2))
        painter.drawLine(QLineF(center.center().x(), center.bottom() + MAG_ZOOM / 2,
                                center.center().x(), box.bottom()))
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(center)
        painter.setPen(QPen(ACCENT, 1))
        painter.drawRect(box)

        if s.image.valid(px, py):
            color = QColor(s.image.pixel(px, py))
            info = f"{px}, {py}   {color.name().upper()}"
        else:
            color, info = QColor("#000000"), f"{px}, {py}"
        font = QFont()
        font.setPixelSize(12)
        painter.setFont(font)
        bar = QRectF(box.left(), box.bottom() + 2, max(size, 180), 40)
        painter.fillRect(bar, QColor(20, 22, 24, 230))
        painter.fillRect(QRectF(bar.left() + 6, bar.top() + 12, 16, 16), color)
        painter.setPen(QColor("#eff0f1"))
        painter.drawText(bar.adjusted(28, 0, 0, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, info)
        painter.restore()

    # --- Acertos --------------------------------------------------------

    def _handle_at(self, pos):
        sel = self.session.selection
        if sel is None or sel.isEmpty():
            return None
        for name, center in _handles(sel).items():
            if QLineF(center, pos).length() <= HANDLE:
                return name
        return None

    def _shape_at(self, pos):
        for shape in reversed(self.session.shapes):
            if shape.contains(pos):
                return shape
        return None

    def _text_at(self, pos):
        for shape in reversed(self.session.shapes):
            if isinstance(shape, Text) and shape.contains(pos):
                return shape
        return None

    def _update_cursor(self, pos):
        tool = self.session.tool
        cursor = Qt.CursorShape.CrossCursor
        if tool == TOOL_SELECT:
            handle = self._handle_at(pos)
            sel = self.session.selection
            if handle:
                cursor = _HANDLE_CURSORS[handle]
            elif sel is not None and sel.contains(pos):
                cursor = Qt.CursorShape.SizeAllCursor
        elif tool == TOOL_MOVE:
            cursor = (Qt.CursorShape.SizeAllCursor if self._shape_at(pos)
                      else Qt.CursorShape.ArrowCursor)
        elif tool == TOOL_TEXT:
            cursor = Qt.CursorShape.IBeamCursor
        self.setCursor(cursor)

    # --- Eventos --------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        session = self.session
        pos = self._to_desktop(event.position())
        tool = session.tool

        # Clique fora da caixa de texto em edição: conclui o texto.
        if self._editor is not None:
            self.close_text_editor()
            return

        self._press_pos = pos
        if tool == TOOL_TEXT:
            hit = self._text_at(pos)
            self._open_text_editor(hit or self._new_text(pos))
        elif tool == TOOL_SELECT:
            sel = session.selection
            handle = self._handle_at(pos)
            if handle:
                self._mode, self._handle = "resize-sel", handle
                self._press_rect = QRectF(sel)
            elif sel is not None and sel.contains(pos):
                self._mode = "move-sel"
                self._press_rect = QRectF(sel)
            else:
                self._mode = "new-sel"
                session.selection = QRectF(pos, pos)
        elif tool == TOOL_MOVE:
            session.picked = self._shape_at(pos)
            if session.picked is not None:
                session.checkpoint()
                self._mode = "move-shape"
        elif tool in (TOOL_PEN, TOOL_MARKER):
            cls = Pen if tool == TOOL_PEN else Marker
            self._active_shape = cls(color=QColor(session.color),
                                     width=session.width, points=[pos])
            self._mode = "draw"
        elif tool in _DRAW_TOOLS:
            self._active_shape = _DRAW_TOOLS[tool](
                color=QColor(session.color), width=session.width,
                start=pos, end=pos)
            self._mode = "draw"
        session.refresh()

    def mouseMoveEvent(self, event):
        session = self.session
        pos = self._to_desktop(event.position())
        self._cursor = pos
        mode = self._mode
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if mode == "new-sel":
            session.selection = QRectF(self._press_pos, pos).normalized()
            self.selection_changed.emit(session.selection)
        elif mode == "move-sel":
            session.selection = self._press_rect.translated(pos - self._press_pos)
            self.selection_changed.emit(session.selection)
        elif mode == "resize-sel":
            session.selection = self._resized(pos)
            self.selection_changed.emit(session.selection)
        elif mode == "move-shape" and session.picked is not None:
            session.picked.translate(pos - self._press_pos)
            self._press_pos = pos
        elif mode == "draw" and self._active_shape is not None:
            shape = self._active_shape
            if isinstance(shape, Pen):
                shape.points.append(pos)
            else:
                shape.end = self._constrain(shape.start, pos) if shift else pos
        elif mode is None:
            self._update_cursor(pos)
            if not self._show_magnifier():
                return
        session.refresh()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        session = self.session
        mode, self._mode = self._mode, None
        if mode in ("new-sel", "move-sel", "resize-sel"):
            sel = session.selection
            if sel is not None and (sel.width() < 3 or sel.height() < 3):
                session.selection = None
            self.selection_changed.emit(session.selection)
        elif mode == "draw" and self._active_shape is not None:
            shape, self._active_shape = self._active_shape, None
            if self._worth_keeping(shape):
                session.checkpoint()
                session.shapes.append(shape)
        session.refresh()
        self._update_cursor(self._to_desktop(event.position()))

    def leaveEvent(self, _event):
        self._cursor = None
        self.update()

    @staticmethod
    def _worth_keeping(shape):
        if isinstance(shape, Pen):
            return len(shape.points) >= 1
        return QLineF(shape.start, shape.end).length() >= 3

    @staticmethod
    def _constrain(start, pos):
        """Com Shift: linhas em múltiplos de 45°."""
        line = QLineF(start, pos)
        angle = round(line.angle() / 45.0) * 45.0
        line.setAngle(angle)
        return line.p2()

    def _resized(self, pos):
        rect = QRectF(self._press_rect)
        delta = pos - self._press_pos
        h = self._handle
        if "l" in h:
            rect.setLeft(rect.left() + delta.x())
        if "r" in h:
            rect.setRight(rect.right() + delta.x())
        if "t" in h:
            rect.setTop(rect.top() + delta.y())
        if "b" in h:
            rect.setBottom(rect.bottom() + delta.y())
        return rect.normalized()

    # --- Texto ----------------------------------------------------------

    def mouseDoubleClickEvent(self, event):
        """Duplo clique num texto existente abre a edição (qualquer ferramenta)."""
        hit = self._text_at(self._to_desktop(event.position()))
        if hit is not None:
            self._active_shape = None
            self._mode = None
            self.session.set_tool(TOOL_TEXT)
            self._open_text_editor(hit)

    def _new_text(self, pos):
        size = self.session.text_size
        shape = Text(
            color=QColor(self.session.color),
            rect=QRectF(pos.x(), pos.y() - size * 0.7, 240, size * 1.4),
            font_size=size,
        )
        self.session.checkpoint()
        shape.new = True
        self.session.shapes.append(shape)
        return shape

    def _open_text_editor(self, shape):
        self.close_text_editor()
        if not getattr(shape, "new", False):
            self.session.checkpoint()
        shape.editing = True
        box = TextBox(self, shape)
        box.finished.connect(self.close_text_editor)
        box.show()
        box.edit.setFocus()
        cursor = box.edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        box.edit.setTextCursor(cursor)
        self._editor = box
        self.session.refresh()

    def close_text_editor(self):
        box = self._editor
        if box is None:
            return
        self._editor = None
        shape = box.shape
        shape.editing = False
        shape.new = False
        shape.text = box.edit.toPlainText().rstrip()
        if not shape.text.strip() and shape in self.session.shapes:
            self.session.shapes.remove(shape)
            # Texto vazio não conta como alteração.
            if self.session.undo_stack:
                self.session.undo_stack.pop()
        box.hide()
        box.deleteLater()
        self.setFocus()
        self.session.refresh()

    def recolor_text(self, color):
        if self._editor is not None:
            self._editor.shape.color = QColor(color)
            self._editor.apply_style()
            self._editor.edit.setFocus()

    def resize_text(self, step):
        if self._editor is not None:
            self._editor.change_size(step)
            self._editor.edit.setFocus()

    # --- Teclado --------------------------------------------------------

    def keyPressEvent(self, event):
        key = event.key()
        session = self.session
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if key == Qt.Key.Key_Escape:
            session.finish("cancel")
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            session.finish("accept")
        elif ctrl and key == Qt.Key.Key_C:
            session.finish("copy")
        elif ctrl and key == Qt.Key.Key_S:
            session.finish("saveas")
        elif ctrl and key == Qt.Key.Key_D:
            session.finish("upload")
        elif ctrl and key == Qt.Key.Key_Z:
            session.redo() if shift else session.undo()
        elif ctrl and key == Qt.Key.Key_Y:
            session.redo()
        elif ctrl and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            session.change_text_size(2)
        elif ctrl and key == Qt.Key.Key_Minus:
            session.change_text_size(-2)
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            session.delete_picked()
        elif not ctrl and key in TOOL_KEYS:
            session.set_tool(TOOL_KEYS[key])
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._nudge(key, shift)

    def _nudge(self, key, shift):
        """Setas movem a seleção 1 px; com Shift, aumentam/diminuem."""
        sel = self.session.selection
        if sel is None:
            return
        dx = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(key, 0)
        dy = {Qt.Key.Key_Up: -1, Qt.Key.Key_Down: 1}.get(key, 0)
        if shift:
            sel = sel.adjusted(0, 0, dx, dy)
        else:
            sel = sel.translated(dx, dy)
        if sel.width() >= 3 and sel.height() >= 3:
            self.session.selection = sel
            self.selection_changed.emit(sel)
            self.session.refresh()
