"""Captura de tela: xdg-desktop-portal no Linux (Wayland) e Qt no Windows."""

import os
import sys

from PySide6.QtCore import QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPixmap


class CaptureError(Exception):
    pass


def _portal_screenshot(timeout=30):
    """Pede uma captura ao portal. Retorna o caminho do PNG temporário."""
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    loop = GLib.MainLoop()
    result = {}

    def on_response(_conn, _sender, _path, _iface, _sig, params):
        result["value"] = params.unpack()
        loop.quit()

    try:
        reply = bus.call_sync(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot",
            "Screenshot",
            GLib.Variant(
                "(sa{sv})",
                ("", {"interactive": GLib.Variant("b", False)}),
            ),
            None,
            Gio.DBusCallFlags.NONE,
            10000,
            None,
        )
    except GLib.Error as exc:
        raise CaptureError(f"Portal indisponível: {exc.message}") from exc

    handle = reply.unpack()[0]
    bus.signal_subscribe(
        "org.freedesktop.portal.Desktop",
        "org.freedesktop.portal.Request",
        "Response",
        handle,
        None,
        Gio.DBusSignalFlags.NONE,
        on_response,
    )

    GLib.timeout_add_seconds(timeout, loop.quit)
    loop.run()

    value = result.get("value")
    if not value:
        raise CaptureError("O portal não respondeu a tempo.")
    status, options = value
    if status != 0:
        raise CaptureError("Captura cancelada ou negada pelo portal.")
    uri = options.get("uri")
    if not uri:
        raise CaptureError("O portal não retornou nenhum arquivo.")
    return uri.replace("file://", "")


def _qt_screenshot():
    """Compõe todos os monitores numa imagem só (Windows).

    A imagem usa a maior escala (DPI) entre as telas, para que a área de
    trabalho lógica caiba nela com a mesma proporção usada pelo overlay.
    """
    screens = QGuiApplication.screens()
    if not screens:
        raise CaptureError("Nenhuma tela encontrada.")
    left = min(s.geometry().x() for s in screens)
    top = min(s.geometry().y() for s in screens)
    right = max(s.geometry().x() + s.geometry().width() for s in screens)
    bottom = max(s.geometry().y() + s.geometry().height() for s in screens)
    scale = max(s.devicePixelRatio() for s in screens)

    image = QImage(round((right - left) * scale), round((bottom - top) * scale),
                   QImage.Format.Format_RGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for screen in screens:
        grab = screen.grabWindow(0)
        if grab.isNull():
            continue
        geo = screen.geometry()
        target = QRectF((geo.x() - left) * scale, (geo.y() - top) * scale,
                        geo.width() * scale, geo.height() * scale)
        painter.drawPixmap(target, grab, QRectF(grab.rect()))
    painter.end()
    return QPixmap.fromImage(image)


def grab_desktop():
    """Captura todas as telas e devolve um QPixmap.

    O arquivo temporário criado pelo portal é removido após o carregamento.
    """
    if sys.platform == "win32":
        return _qt_screenshot()
    path = _portal_screenshot()
    try:
        image = QImage(path)
        if image.isNull():
            raise CaptureError("Não foi possível ler a imagem capturada.")
        return QPixmap.fromImage(image)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
