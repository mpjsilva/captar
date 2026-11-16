"""Captura de tela via xdg-desktop-portal (funciona em Wayland)."""

import os
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from PySide6.QtGui import QImage, QPixmap  # noqa: E402


class CaptureError(Exception):
    pass


def _portal_screenshot(timeout=30):
    """Pede uma captura ao portal. Retorna o caminho do PNG temporário."""
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


def grab_desktop():
    """Captura todas as telas e devolve um QPixmap.

    O arquivo temporário criado pelo portal é removido após o carregamento.
    """
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
