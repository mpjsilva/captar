"""Captar - captura de tela com anotações para KDE Plasma Wayland.

O Captar fica residente na bandeja do sistema e captura quando recebe os
atalhos globais (Print Screen: área; Shift+Print: tela inteira),
registrados no kglobalaccel do KDE.
"""

import os
import sys
import tempfile
from datetime import datetime

from PySide6.QtCore import (  # noqa: E402
    QBuffer,
    QByteArray,
    QLockFile,
    QMimeData,
    QObject,
    QProcess,
    QRectF,
    QStandardPaths,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (  # noqa: E402
    QAction,
    QCursor,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QKeySequence,
)
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QFileDialog,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from . import __version__, cloud, shortcuts, updater  # noqa: E402
from .capture import CaptureError, grab_desktop  # noqa: E402
from .overlay import Overlay, Session  # noqa: E402
from .render import render  # noqa: E402
from .settings import Settings, SettingsDialog  # noqa: E402
from .toolbar import ActionBar, ToolPanel  # noqa: E402

ACTION_AREA = "capture"
ACTION_FULL = "capture-full"


def _acquire_lock():
    """Evita duas instâncias: o overlay de uma apareceria na captura da outra."""
    directory = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.RuntimeLocation
    ) or os.path.expanduser("~")
    os.makedirs(directory, exist_ok=True)
    lock = QLockFile(os.path.join(directory, "captar.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        return None
    return lock


def _copy_to_clipboard(image):
    """Publica a imagem no clipboard do Wayland.

    O Qt só anuncia image/png no Wayland quando o QMimeData traz os bytes
    PNG explicitamente; setImage() sozinho não é visível para outros apps.
    """
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    mime = QMimeData()
    mime.setData("image/png", data)
    mime.setImageData(image)
    QGuiApplication.clipboard().setMimeData(mime)


def _copy_text(text):
    QGuiApplication.clipboard().setText(text)


class Tray(QSystemTrayIcon):
    capture_requested = Signal()
    full_requested = Signal()
    folder_requested = Signal()
    settings_requested = Signal()
    check_requested = Signal()
    update_requested = Signal()
    quit_requested = Signal()

    def __init__(self, icon_path, parent=None):
        super().__init__(QIcon(icon_path), parent)
        self.setToolTip(f"Captar {__version__} — clique para capturar (Print Screen)")
        menu = QMenu()
        for label, signal in (
            ("Capturar área", self.capture_requested),
            ("Capturar tela inteira", self.full_requested),
            (None, None),
            ("Abrir pasta das capturas", self.folder_requested),
            ("Configurações…", self.settings_requested),
            ("Verificar atualizações", self.check_requested),
            (None, None),
            ("Sair", self.quit_requested),
        ):
            if label is None:
                menu.addSeparator()
                continue
            action = QAction(label, menu)
            action.triggered.connect(signal.emit)
            menu.addAction(action)
        self.update_action = QAction("Atualizar", menu)
        self.update_action.triggered.connect(self.update_requested.emit)
        self.update_action.setVisible(False)
        menu.insertAction(menu.actions()[0], self.update_action)
        self._menu = menu
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.capture_requested.emit()


def _place(panels, rect, overlay):
    """Barra vertical à direita da seleção, barra horizontal embaixo
    (alinhada à direita). Sem seleção: centradas."""
    tools, actions = panels
    for panel in panels:
        if panel.parent() is not overlay:
            panel.setParent(overlay)
        panel.adjustSize()
    geo = overlay.rect()
    gap = 8
    if rect is None or rect.isEmpty():
        tools.move(geo.width() - tools.width() - 24,
                   (geo.height() - tools.height()) // 2)
        actions.move((geo.width() - actions.width()) // 2,
                     geo.height() - actions.height() - 40)
    else:
        local = QRectF(rect).translated(-overlay._origin)
        # Vertical: direita, senão esquerda, senão dentro.
        x = int(local.right()) + gap
        if x + tools.width() > geo.width():
            x = int(local.left()) - tools.width() - gap
            if x < 0:
                x = int(local.right()) - tools.width() - gap
        y = int(local.bottom()) - tools.height()
        y = max(gap, min(y, geo.height() - tools.height() - gap))
        tools.move(x, y)
        # Horizontal: embaixo, senão em cima, senão dentro.
        ax = int(local.right()) - actions.width()
        ay = int(local.bottom()) + gap
        if ay + actions.height() > geo.height():
            ay = int(local.top()) - actions.height() - gap
            if ay < 0:
                ay = int(local.bottom()) - actions.height() - gap
        ax = max(gap, min(ax, geo.width() - actions.width() - gap))
        actions.move(ax, ay)
    for panel in panels:
        panel.show()
        panel.raise_()


class CaptarApp(QObject):
    def __init__(self, app, icon_path):
        super().__init__()
        self.app = app
        self.icon_path = icon_path
        self.settings = Settings()
        self.busy = False
        self._session = None
        self._overlays = []
        self._panels = None
        self._last_path = None
        self._uploads = []
        self._settings_dialog = None

        self.tray = None
        self.shortcut = shortcuts.create()
        self.shortcut.activated.connect(self._on_shortcut)
        self.shortcut.failed.connect(self._on_shortcut_failed)
        self._shortcut_error = None
        self._register_shortcuts()

        self.tray = Tray(icon_path, self)
        self.tray.capture_requested.connect(self.capture)
        self.tray.full_requested.connect(self.capture_full)
        self.tray.folder_requested.connect(self.open_folder)
        self.tray.settings_requested.connect(self.open_settings)
        self.tray.quit_requested.connect(self.quit)
        self.tray.messageClicked.connect(self._on_message_clicked)
        self.tray.check_requested.connect(lambda: self.check_updates(manual=True))
        self.tray.update_requested.connect(self.install_update)

        self._message_action = None  # "folder" ou "update"
        self._manual_check = False
        self._installer = None
        self.updater = updater.Updater(self)
        self.updater.available.connect(self._on_update_available)
        self.updater.up_to_date.connect(self._on_up_to_date)
        self.updater.failed.connect(self._on_update_failed)
        self.updater.downloaded.connect(self._on_update_downloaded)
        # Verifica 20 s após iniciar e depois a cada 6 horas.
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(6 * 3600 * 1000)
        self._update_timer.timeout.connect(self.check_updates)
        QTimer.singleShot(20000, self.check_updates)
        self._update_timer.start()

        self._watchdog = QTimer(self)
        self._watchdog.setInterval(300)
        self._watchdog.timeout.connect(self._check_overlays)
        self._watchdog.start()

    def start(self):
        self.tray.show()
        if self._shortcut_error:
            QTimer.singleShot(1500, lambda: self._notify(self._shortcut_error, warn=True))

    def quit(self):
        self._teardown()
        self.tray.hide()
        self.app.quit()

    # --- Avisos ---------------------------------------------------------

    def _notify(self, text, warn=False):
        icon = (QSystemTrayIcon.MessageIcon.Warning if warn
                else QSystemTrayIcon.MessageIcon.Information)
        self._message_action = "folder"
        self.tray.showMessage("Captar", text, icon, 5000)

    # --- Atualização ----------------------------------------------------

    def check_updates(self, manual=False):
        if not manual and not self.settings.get("auto_update"):
            return
        self._manual_check = manual
        if manual:
            self._notify("Verificando atualizações…")
        self.updater.check()

    def _on_update_available(self, version, _notes):
        self.tray.update_action.setText(f"Atualizar para a versão {version}")
        self.tray.update_action.setVisible(True)
        self._notify(f"Nova versão {version} disponível. Clique para atualizar.")
        self._message_action = "update"

    def _on_up_to_date(self):
        if self._manual_check:
            self._notify(f"O Captar {__version__} já é a versão mais recente.")

    def _on_update_failed(self, message):
        if self._manual_check or self._installer is not None:
            self._notify(message, warn=True)

    def install_update(self):
        version = self.updater.version
        if not version:
            self.check_updates(manual=True)
            return
        if updater.package_format() is None:
            QDesktopServices.openUrl(QUrl(
                f"https://github.com/{updater.REPO}/releases/tag/v{version}"))
            return
        answer = QMessageBox.question(
            None, "Atualizar o Captar",
            f"Instalar o Captar {version}?\nO sistema vai pedir a sua senha.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._installer = "download"
        self._notify(f"Baixando o Captar {version}…")
        self.updater.download()

    def _on_shortcut_failed(self, message):
        if self.tray is None:
            self._shortcut_error = message  # avisa quando a bandeja existir
        else:
            self._notify(message, warn=True)

    def _on_update_downloaded(self, path):
        if path.lower().endswith(".exe"):
            # Instalador Inno Setup: fecha o Captar, instala e reabre sozinho.
            QProcess.startDetached(path, updater.install_command(path)[1:])
            self.quit()
            return
        proc = QProcess(self)
        proc.setProgram(updater.install_command(path)[0])
        proc.setArguments(updater.install_command(path)[1:])
        proc.finished.connect(lambda code, _s: self._on_installed(code, path))
        self._installer = proc
        proc.start()

    def _on_installed(self, code, path):
        self._installer = None
        try:
            os.remove(path)
            os.rmdir(os.path.dirname(path))
        except OSError:
            pass
        if code != 0:
            self._notify("A atualização não foi instalada.", warn=True)
            return
        # Reabre a versão nova depois que esta instância liberar a trava.
        QProcess.startDetached("sh", ["-c", "sleep 2; exec captar"])
        self.quit()

    def _on_message_clicked(self):
        if self._message_action == "update":
            self._message_action = None
            self.install_update()
            return
        if self._last_path and os.path.exists(self._last_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self._last_path)))

    def open_folder(self):
        directory = self.settings.get("save_dir")
        os.makedirs(directory, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(directory))

    # --- Configurações --------------------------------------------------

    def _register_shortcuts(self):
        self.shortcut.register({
            ACTION_AREA: self.settings.get("shortcut_area"),
            ACTION_FULL: self.settings.get("shortcut_full"),
        })

    def open_settings(self):
        if self._settings_dialog is not None:
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        dialog = SettingsDialog(self.settings)
        self._settings_dialog = dialog
        dialog.accepted.connect(self._register_shortcuts)
        dialog.finished.connect(lambda _r: setattr(self, "_settings_dialog", None))
        dialog.show()

    # --- Arquivos -------------------------------------------------------

    def _file_name(self):
        pattern = self.settings.get("name_pattern")
        try:
            name = datetime.now().strftime(pattern)
        except ValueError:
            name = datetime.now().strftime("Captar_%Y%m%d_%H%M%S")
        return f"{name}.{self.settings.get('format')}"

    def _write(self, image, path):
        fmt = "JPG" if path.lower().endswith((".jpg", ".jpeg")) else "PNG"
        quality = self.settings.get("jpg_quality") if fmt == "JPG" else -1
        if fmt == "JPG":
            image = image.convertToFormat(image.Format.Format_RGB32)
        if not image.save(path, fmt, quality):
            raise OSError(f"Não foi possível salvar em {path}")
        self._last_path = path
        return path

    def _save(self, image):
        directory = self.settings.get("save_dir")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, self._file_name())
        base, ext = os.path.splitext(path)
        n = 2
        while os.path.exists(path):
            path, n = f"{base}_{n}{ext}", n + 1
        return self._write(image, path)

    def _save_as(self, image):
        directory = self.settings.get("save_dir")
        default = os.path.join(directory, self._file_name())
        path, _ = QFileDialog.getSaveFileName(
            None, "Salvar captura como", default,
            "Imagem PNG (*.png);;Imagem JPG (*.jpg *.jpeg)",
        )
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".png"
        try:
            self._write(image, path)
        except OSError as exc:
            self._notify(str(exc), warn=True)
        else:
            self._notify(f"Salvo em {path}")

    def _upload(self, image):
        remote = self.settings.get("cloud_remote")
        valid = {name for name, _ in cloud.list_remotes()}
        if not cloud.available():
            self._notify("Instale o rclone para enviar para a nuvem.", warn=True)
            return
        if remote not in valid:
            self._notify("Conecte uma conta de nuvem nas configurações.", warn=True)
            self.open_settings()
            return
        tmp = os.path.join(tempfile.gettempdir(), "captar")
        os.makedirs(tmp, exist_ok=True)
        path = os.path.join(tmp, self._file_name())
        try:
            self._write(image, path)
        except OSError as exc:
            self._notify(str(exc), warn=True)
            return
        uploader = cloud.Uploader(path, remote, self.settings.get("cloud_folder"), self)
        self._uploads.append(uploader)

        def done(link, ok):
            self._uploads.remove(uploader)
            try:
                os.remove(path)
            except OSError:
                pass
            if ok and link:
                _copy_text(link)
                self._notify(f"Link copiado: {link}")
            elif ok:
                self._notify("Enviado para a nuvem.")
            else:
                self._notify(link, warn=True)

        uploader.finished.connect(lambda link: done(link, True))
        uploader.failed.connect(lambda msg: done(msg, False))
        self._notify("Enviando para a nuvem…")
        uploader.start()

    # --- Captura --------------------------------------------------------

    def _on_shortcut(self, action):
        if action == ACTION_AREA:
            self.capture()
        elif action == ACTION_FULL:
            self.capture_full()

    def _grab(self):
        try:
            return grab_desktop()
        except CaptureError as exc:
            self._notify(str(exc), warn=True)
            return None

    def capture_full(self):
        """Tela inteira: salva e copia direto, sem editor."""
        if self.busy:
            return
        self.busy = True
        try:
            screenshot = self._grab()
            if screenshot is None:
                return
            image = screenshot.toImage()
            _copy_to_clipboard(image)
            try:
                path = self._save(image)
            except OSError as exc:
                self._notify(str(exc), warn=True)
            else:
                self._notify(f"Tela inteira salva e copiada: {path}")
        finally:
            self.busy = False

    def capture(self):
        if self.busy:
            return
        self.busy = True
        screenshot = self._grab()
        if screenshot is None:
            self.busy = False
            return
        self._show_overlays(screenshot)

    def _on_finish(self, action, session):
        image = None
        if action != "cancel":
            try:
                image = render(session)
            except Exception as exc:  # pragma: no cover - defensivo
                self._notify(f"Falha ao renderizar: {exc}", warn=True)
        self.busy = False
        self._teardown()
        if image is None:
            return
        if action in ("accept", "copy"):
            _copy_to_clipboard(image)
        if action == "accept":
            try:
                path = self._save(image)
            except OSError as exc:
                self._notify(str(exc), warn=True)
            else:
                self.tray.setToolTip(f"Captar — salvo em {path}")
                self._notify(f"Salvo e copiado: {os.path.basename(path)}")
        elif action == "copy":
            self._notify("Imagem copiada.")
        elif action == "saveas":
            # Depois que as sobreposições fecharam, para o diálogo aparecer.
            QTimer.singleShot(0, lambda: self._save_as(image))
        elif action == "upload":
            self._upload(image)

    def _show_overlays(self, screenshot):
        session = Session(screenshot, on_finish=self._on_finish)
        self._session = session

        overlays = []
        for screen in QGuiApplication.screens():
            overlay = Overlay(session, screen)
            overlay.selection_changed.connect(
                lambda rect, ov=overlay: self._on_selection(rect, ov)
            )
            overlay.showFullScreen()
            overlays.append(overlay)
        self._overlays = overlays

        cursor_screen = QGuiApplication.screenAt(QCursor.pos()) or \
            QGuiApplication.primaryScreen()
        canonical = overlays[0]
        for overlay in overlays:
            if overlay.screen is cursor_screen:
                canonical = overlay
        canonical.raise_()
        canonical.activateWindow()
        canonical.setFocus()

        self._panels = (ToolPanel(session), ActionBar(session))
        _place(self._panels, None, canonical)
        canonical.setFocus()

    def _on_selection(self, rect, overlay):
        """Reposiciona as barras acompanhando a seleção."""
        if self._panels is None:
            return
        target = overlay
        if rect is not None and not rect.isEmpty():
            screen = QGuiApplication.screenAt(rect.center().toPoint())
            for candidate in self._overlays:
                if candidate.screen is screen:
                    target = candidate
                    break
        _place(self._panels, rect, target)

    def _check_overlays(self):
        if not self.busy or not self._overlays:
            return
        if not any(o.isVisible() for o in self._overlays):
            self.busy = False
            self._teardown()

    def _teardown(self):
        if self._panels is not None:
            for panel in self._panels:
                panel.close()
                panel.deleteLater()
            self._panels = None
        for overlay in self._overlays:
            overlay.close()
            overlay.deleteLater()
        self._overlays = []
        self._session = None


def _icon_path():
    candidates = [
        os.path.join(getattr(sys, "_MEIPASS", ""), "captar.svg"),
        "/usr/share/icons/hicolor/scalable/apps/captar.svg",
        os.path.join(os.path.dirname(__file__), "..", "captar.svg"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    return ""


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("Captar")
    app.setOrganizationName("Captar")
    app.setDesktopFileName("captar")
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("Captar: bandeja do sistema indisponível.", file=sys.stderr)
        return 1

    lock = _acquire_lock()
    if lock is None:
        print("Captar: já está em execução.", file=sys.stderr)
        return 0

    controller = CaptarApp(app, _icon_path())
    controller.start()

    code = app.exec()
    lock.unlock()
    return code


def main():
    sys.exit(run())


if __name__ == "__main__":
    main()
