"""Barras flutuantes do Captar: ferramentas (vertical) e ações (horizontal)."""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .overlay import (
    TOOL_ARROW,
    TOOL_LINE,
    TOOL_MARKER,
    TOOL_MOVE,
    TOOL_PEN,
    TOOL_RECT,
    TOOL_SELECT,
    TOOL_TEXT,
)

FG = QColor("#eff0f1")
PALETTE = ("#e01b24", "#ff7800", "#f6d32d", "#2ec27e",
           "#3daee9", "#9141ac", "#000000", "#ffffff")
WIDTHS = ((2, "Fina"), (4, "Média"), (8, "Grossa"))

STYLE = (
    "QPushButton { background: transparent; border: none; padding: 4px;"
    " color: #eff0f1; font-weight: bold; }"
    "QPushButton:hover { background: rgba(61,174,233,90); border-radius: 6px; }"
    "QPushButton:checked { background: rgba(61,174,233,150); border-radius: 6px; }"
)


def _icon(kind, color=FG):
    pix = QPixmap(48, 48)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(2, 2)
    pen = QPen(color, 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    if kind == TOOL_SELECT:
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(4, 4, 16, 16)
    elif kind == TOOL_PEN:
        path = QPainterPath(QPointF(4, 18))
        path.cubicTo(8, 4, 12, 22, 20, 6)
        p.drawPath(path)
    elif kind == TOOL_LINE:
        p.drawLine(5, 19, 19, 5)
    elif kind == TOOL_ARROW:
        p.drawLine(5, 19, 17, 7)
        p.setBrush(color)
        p.drawPolygon(QPolygonF([QPointF(20, 4), QPointF(11, 6), QPointF(18, 13)]))
    elif kind == TOOL_RECT:
        p.drawRect(4, 6, 16, 12)
    elif kind == TOOL_MARKER:
        mark = QColor(color)
        mark.setAlpha(140)
        p.setPen(QPen(mark, 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
        p.drawLine(5, 15, 19, 15)
        p.setPen(pen)
        p.drawLine(5, 9, 19, 9)
    elif kind == TOOL_TEXT:
        p.drawLine(6, 6, 18, 6)
        p.drawLine(12, 6, 12, 19)
    elif kind == TOOL_MOVE:
        p.drawLine(12, 3, 12, 21)
        p.drawLine(3, 12, 21, 12)
        for a, b, c in (((9, 6), (12, 3), (15, 6)), ((9, 18), (12, 21), (15, 18)),
                        ((6, 9), (3, 12), (6, 15)), ((18, 9), (21, 12), (18, 15))):
            p.drawPolyline(QPolygonF([QPointF(*a), QPointF(*b), QPointF(*c)]))
    elif kind in ("undo", "redo"):
        path = QPainterPath()
        if kind == "undo":
            path.moveTo(8, 9)
            path.cubicTo(14, 5, 22, 9, 18, 18)
            p.drawPath(path)
            p.drawPolyline(QPolygonF([QPointF(8, 4), QPointF(8, 9), QPointF(13, 9)]))
        else:
            path.moveTo(16, 9)
            path.cubicTo(10, 5, 2, 9, 6, 18)
            p.drawPath(path)
            p.drawPolyline(QPolygonF([QPointF(16, 4), QPointF(16, 9), QPointF(11, 9)]))
    elif kind == "accept":
        p.setPen(QPen(color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(5, 13, 10, 18)
        p.drawLine(10, 18, 19, 6)
    elif kind == "cancel":
        p.setPen(QPen(color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(6, 6, 18, 18)
        p.drawLine(18, 6, 6, 18)
    elif kind == "copy":
        p.drawRect(4, 8, 12, 12)
        p.drawRect(8, 4, 12, 12)
    elif kind == "saveas":
        p.drawRoundedRect(QRectF(4, 4, 16, 16), 2, 2)
        p.drawRect(8, 4, 8, 5)
        p.drawRect(7, 13, 10, 7)
    elif kind == "upload":
        path = QPainterPath()
        path.moveTo(7, 18)
        path.cubicTo(1, 18, 2, 10, 8, 11)
        path.cubicTo(9, 4, 18, 5, 18, 11)
        path.cubicTo(23, 11, 23, 18, 17, 18)
        p.drawPath(path)
        p.drawLine(12, 20, 12, 12)
        p.drawPolyline(QPolygonF([QPointF(9, 15), QPointF(12, 12), QPointF(15, 15)]))
    p.end()
    return QIcon(pix)


def _width_icon(width):
    pix = QPixmap(48, 48)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(FG)
    r = width + 2
    p.drawEllipse(QPointF(24, 24), r, r)
    p.end()
    return QIcon(pix)


class _Panel(QWidget):
    """Base: fundo arredondado escuro, cursor de seta, sem roubar foco."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # O overlay usa cursor de cruz; aqui volta a seta padrão.
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet(STYLE)

    def _button(self, icon=None, tip="", text="", size=34, checkable=False):
        button = QPushButton(text, self)
        if icon is not None:
            button.setIcon(icon)
            button.setIconSize(QSize(22, 22))
        button.setToolTip(tip)
        button.setFixedSize(size, size)
        button.setCheckable(checkable)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 32, 34, 235))
        painter.drawRoundedRect(self.rect(), 8, 8)

    @staticmethod
    def _separator(vertical):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine if vertical else QFrame.Shape.VLine)
        line.setStyleSheet("color: rgba(255,255,255,40);")
        return line


class ToolPanel(_Panel):
    """Barra vertical: ferramentas, cores, espessura, tamanho do texto, desfazer."""

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        def grid():
            g = QGridLayout()
            g.setSpacing(2)
            layout.addLayout(g)
            return g

        tools = grid()
        self._tools = {}
        for i, (tool, tip) in enumerate((
            (TOOL_SELECT, "Selecionar área (S)"),
            (TOOL_MOVE, "Mover/apagar anotação (V, Delete)"),
            (TOOL_PEN, "Lápis (P)"),
            (TOOL_MARKER, "Marca-texto (M)"),
            (TOOL_LINE, "Linha (L) — Shift trava em 45°"),
            (TOOL_ARROW, "Seta (A) — Shift trava em 45°"),
            (TOOL_RECT, "Retângulo (R)"),
            (TOOL_TEXT, "Texto (T)"),
        )):
            button = self._button(_icon(tool), tip, checkable=True)
            button.clicked.connect(lambda _=False, t=tool: session.set_tool(t))
            tools.addWidget(button, i // 2, i % 2)
            self._tools[tool] = button

        layout.addWidget(self._separator(True))

        top = grid()
        # Cor atual (abre o seletor completo) e espessura (alterna).
        self._current = self._button(tip="Outra cor…", size=34)
        self._current.clicked.connect(self._pick_color)
        top.addWidget(self._current, 0, 0)
        self._width_btn = self._button(tip="Espessura (clique para alternar)")
        self._width_btn.clicked.connect(self._cycle_width)
        top.addWidget(self._width_btn, 0, 1)

        palette = grid()
        palette.setSpacing(3)
        self._swatches = {}
        for i, name in enumerate(PALETTE):
            swatch = self._button(tip=name, size=15)
            swatch.clicked.connect(lambda _=False, c=name: session.set_color(c))
            palette.addWidget(swatch, i // 4, i % 4)
            self._swatches[name] = swatch

        layout.addWidget(self._separator(True))

        bottom = grid()
        for col, (label, step, tip) in enumerate((("A+", 2, "Aumentar texto (Ctrl+=)"),
                                                  ("A−", -2, "Diminuir texto (Ctrl+−)"))):
            button = self._button(text=label, tip=tip)
            button.clicked.connect(lambda _=False, s=step: session.change_text_size(s))
            bottom.addWidget(button, 0, col)
        undo = self._button(_icon("undo"), "Desfazer (Ctrl+Z)")
        undo.clicked.connect(session.undo)
        bottom.addWidget(undo, 1, 0)
        redo = self._button(_icon("redo"), "Refazer (Ctrl+Shift+Z)")
        redo.clicked.connect(session.redo)
        bottom.addWidget(redo, 1, 1)

        session.listeners.append(self._on_session)
        self._on_session("tool", session.tool)
        self._on_session("color", session.color)
        self._on_session("width", session.width)

    def _on_session(self, what, value):
        if what == "tool":
            for name, button in self._tools.items():
                button.setChecked(name == value)
        elif what == "color":
            self._current.setStyleSheet(
                f"QPushButton {{ background: {value.name()}; border-radius: 17px;"
                " border: 3px solid #eff0f1; }"
            )
            for name, swatch in self._swatches.items():
                border = "#ffffff" if QColor(name) == value else "rgba(255,255,255,60)"
                swatch.setStyleSheet(
                    f"QPushButton {{ background: {name}; border-radius: 3px;"
                    f" border: 1px solid {border}; padding: 0; }}"
                )
        elif what == "width":
            name = dict(WIDTHS).get(value, str(value))
            self._width_btn.setIcon(_width_icon(value))
            self._width_btn.setToolTip(f"Espessura: {name.lower()} (clique para alternar)")

    def _cycle_width(self):
        widths = [w for w, _ in WIDTHS]
        current = self.session.width
        nxt = widths[(widths.index(current) + 1) % len(widths)] if current in widths else widths[0]
        self.session.set_width(nxt)

    def _pick_color(self):
        color = QColorDialog.getColor(self.session.color, self.window(), "Cor")
        if color.isValid():
            self.session.set_color(color)


class ActionBar(_Panel):
    """Barra horizontal: enviar, salvar como, copiar, salvar, fechar."""

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)
        for kind, tip, action, color in (
            ("upload", "Enviar para a nuvem e copiar link (Ctrl+D)", "upload", FG),
            ("saveas", "Salvar como… (Ctrl+S)", "saveas", FG),
            ("copy", "Copiar imagem (Ctrl+C)", "copy", FG),
            ("accept", "Salvar e copiar (Enter)", "accept", QColor("#2ec27e")),
            ("cancel", "Fechar (Esc)", "cancel", QColor("#e01b24")),
        ):
            button = self._button(_icon(kind, color), tip)
            button.clicked.connect(lambda _=False, a=action: session.finish(a))
            layout.addWidget(button)
