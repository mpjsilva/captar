"""Composição do resultado final: recorte da seleção + anotações."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPixmap


def _desktop_origin():
    screens = QGuiApplication.screens()
    return QPointF(
        min(s.geometry().x() for s in screens),
        min(s.geometry().y() for s in screens),
    )


def render(session) -> QImage:
    """Gera a imagem final a partir do estado da sessão."""
    screenshot = session.screenshot
    origin = _desktop_origin()

    screens = QGuiApplication.screens()
    desktop_w = max(s.geometry().x() + s.geometry().width() for s in screens) - origin.x()
    scale = screenshot.width() / desktop_w if desktop_w else 1.0

    selection = session.selection
    if selection is None or selection.isEmpty():
        selection = QRectF(
            origin.x(),
            origin.y(),
            desktop_w,
            max(s.geometry().y() + s.geometry().height() for s in screens)
            - origin.y(),
        )

    source = QRectF(
        (selection.x() - origin.x()) * scale,
        (selection.y() - origin.y()) * scale,
        selection.width() * scale,
        selection.height() * scale,
    )

    result = QImage(
        max(1, int(source.width())),
        max(1, int(source.height())),
        QImage.Format.Format_ARGB32,
    )
    result.fill(Qt.GlobalColor.transparent)

    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.drawImage(
        QRectF(0, 0, result.width(), result.height()),
        screenshot.toImage(),
        source,
    )

    # Anotações: converte da área de trabalho para o espaço do recorte.
    painter.translate(-source.x(), -source.y())
    painter.scale(scale, scale)
    painter.translate(-origin.x(), -origin.y())
    for shape in session.shapes:
        shape.draw(painter)
    painter.end()

    return result
