"""Atalhos globais: kglobalaccel (KDE/Linux) ou RegisterHotKey (Windows).

As duas classes têm a mesma interface: ``register({ação: "Shift+Print"})``
e os sinais ``activated(ação)`` e ``failed(mensagem)``.
"""

import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Qt, Signal
from PySide6.QtGui import QKeySequence

COMPONENT = "captar"
FRIENDLY = {
    "capture": "Capturar área",
    "capture-full": "Capturar tela inteira",
}


def create():
    return WinShortcut() if sys.platform == "win32" else KdeShortcut()


def _combo(text):
    seq = QKeySequence(text)
    return None if seq.isEmpty() else seq[0]


# --- KDE ------------------------------------------------------------------


class KdeShortcut(QObject):
    """Registra as ações no kglobalaccel e escuta globalShortcutPressed."""

    activated = Signal(str)
    failed = Signal(str)

    # Flags do kglobalaccel: SetPresent | NoAutoloading (o Captar manda no atalho).
    FLAGS = 2 | 4

    def __init__(self):
        super().__init__()
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib

        self._Gio, self._GLib = Gio, GLib
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self._sub = None

    def _call(self, method, signature, args):
        return self._bus.call_sync(
            "org.kde.kglobalaccel", "/kglobalaccel", "org.kde.KGlobalAccel",
            method, self._GLib.Variant(signature, args), None,
            self._Gio.DBusCallFlags.NONE, 5000, None,
        )

    def register(self, keys):
        ok = True
        for name, text in keys.items():
            action = [COMPONENT, name, "Captar", FRIENDLY[name]]
            combo = _combo(text)
            code = combo.toCombined() if combo is not None else 0
            try:
                self._call("doRegister", "(as)", (action,))
                self._call("setShortcut", "(asaiu)",
                           (action, [code] if code else [], self.FLAGS))
            except self._GLib.Error as exc:
                print(f"Captar: kglobalaccel: {exc.message}", file=sys.stderr)
                ok = False
        if not ok:
            self.failed.emit("Atalhos globais indisponíveis (kglobalaccel).")
        if self._sub is None and ok:
            self._sub = self._bus.signal_subscribe(
                "org.kde.kglobalaccel", "org.kde.kglobalaccel.Component",
                "globalShortcutPressed", f"/component/{COMPONENT}", None,
                self._Gio.DBusSignalFlags.NONE, self._on_pressed,
            )

    def _on_pressed(self, _conn, _sender, _path, _iface, _sig, params):
        component, shortcut, _timestamp = params.unpack()
        if component == COMPONENT:
            self.activated.emit(shortcut)


# --- Windows --------------------------------------------------------------

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000

_VK_SPECIAL = {
    Qt.Key.Key_Print: 0x2C,
    Qt.Key.Key_Pause: 0x13,
    Qt.Key.Key_Insert: 0x2D,
    Qt.Key.Key_Delete: 0x2E,
    Qt.Key.Key_Home: 0x24,
    Qt.Key.Key_End: 0x23,
    Qt.Key.Key_PageUp: 0x21,
    Qt.Key.Key_PageDown: 0x22,
    Qt.Key.Key_Space: 0x20,
    Qt.Key.Key_Escape: 0x1B,
    Qt.Key.Key_Tab: 0x09,
    Qt.Key.Key_ScrollLock: 0x91,
}


def _vk(key):
    value = key.value if hasattr(key, "value") else int(key)
    if Qt.Key.Key_A.value <= value <= Qt.Key.Key_Z.value:
        return value
    if Qt.Key.Key_0.value <= value <= Qt.Key.Key_9.value:
        return value
    if Qt.Key.Key_F1.value <= value <= Qt.Key.Key_F24.value:
        return 0x70 + (value - Qt.Key.Key_F1.value)
    return _VK_SPECIAL.get(key)


def _mods(modifiers):
    mods = MOD_NOREPEAT
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        mods |= MOD_SHIFT
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        mods |= MOD_CONTROL
    if modifiers & Qt.KeyboardModifier.AltModifier:
        mods |= MOD_ALT
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        mods |= MOD_WIN
    return mods


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            import ctypes.wintypes

            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self._callback(int(msg.wParam))
                return True, 0
        return False, 0


class WinShortcut(QObject):
    """RegisterHotKey na thread da interface; WM_HOTKEY chega pelo filtro nativo."""

    activated = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        import ctypes

        self._user32 = ctypes.windll.user32
        self._ids = {}  # id -> ação
        self._filter = _HotkeyFilter(self._on_hotkey)
        QCoreApplication.instance().installNativeEventFilter(self._filter)

    def register(self, keys):
        for hotkey_id in list(self._ids):
            self._user32.UnregisterHotKey(None, hotkey_id)
        self._ids.clear()
        failed = []
        for index, (name, text) in enumerate(keys.items(), start=1):
            combo = _combo(text)
            if combo is None:
                continue
            vk = _vk(combo.key())
            if vk is None or not self._user32.RegisterHotKey(
                    None, index, _mods(combo.keyboardModifiers()), vk):
                failed.append(text)
                continue
            self._ids[index] = name
        if failed:
            self.failed.emit(
                "Atalho em uso por outro programa: " + ", ".join(failed)
                + ". No Windows 11, desligue \"Usar a tecla Print Screen para "
                "abrir a captura de tela\" em Configurações › Acessibilidade › "
                "Teclado, ou escolha outro atalho."
            )

    def _on_hotkey(self, hotkey_id):
        name = self._ids.get(hotkey_id)
        if name:
            self.activated.emit(name)
