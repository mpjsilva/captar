"""Envio para a nuvem via rclone (Google Drive, OneDrive e Dropbox)."""

import os
import shutil
import subprocess
import sys

# No Windows, não abrir janela de console para o rclone.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

from PySide6.QtCore import QObject, QProcess, Signal

# Tipos de remote do rclone aceitos pelo Captar.
PROVIDERS = {
    "drive": "Google Drive",
    "onedrive": "OneDrive",
    "dropbox": "Dropbox",
}

# Opções extras na criação do remote (escopo mínimo no Google Drive:
# o Captar só enxerga os arquivos que ele mesmo enviou).
_CREATE_OPTIONS = {
    "drive": ["scope=drive.file"],
    "onedrive": [],
    "dropbox": [],
}


def available():
    return shutil.which("rclone") is not None


def list_remotes():
    """Remotes configurados no rclone cujo tipo é suportado: [(nome, tipo)]."""
    if not available():
        return []
    try:
        out = subprocess.run(
            ["rclone", "listremotes", "--long"],
            capture_output=True, text=True, timeout=10, check=False,
            creationflags=_NO_WINDOW,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    remotes = []
    for line in out.splitlines():
        if ":" not in line:
            continue
        name, kind = line.split(":", 1)
        kind = kind.strip()
        if kind in PROVIDERS:
            remotes.append((name.strip(), kind))
    return remotes


def connect_process(kind, name):
    """QProcess que cria o remote e abre o navegador para o login."""
    proc = QProcess()
    proc.setProgram("rclone")
    proc.setArguments(["config", "create", name, kind, *_CREATE_OPTIONS[kind]])
    proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
    return proc


class Uploader(QObject):
    """Envia um arquivo e obtém o link público (rclone copyto + rclone link)."""

    finished = Signal(str)  # link
    failed = Signal(str)

    def __init__(self, path, remote, folder, parent=None):
        super().__init__(parent)
        name = os.path.basename(path)
        folder = folder.strip("/ ")
        self._path = path
        self._target = f"{remote}:{folder}/{name}" if folder else f"{remote}:{name}"
        self._proc = None

    def start(self):
        self._run(["copyto", self._path, self._target], self._on_copied)

    def _run(self, args, callback):
        proc = QProcess(self)
        proc.setProgram("rclone")
        proc.setArguments(args)
        proc.finished.connect(lambda code, _status: callback(code, proc))
        proc.errorOccurred.connect(
            lambda _err: self.failed.emit("Não foi possível executar o rclone.")
        )
        self._proc = proc
        proc.start()

    @staticmethod
    def _error(proc):
        text = bytes(proc.readAllStandardError()).decode(errors="replace").strip()
        return text.splitlines()[-1] if text else "erro desconhecido"

    def _on_copied(self, code, proc):
        if code != 0:
            self.failed.emit(f"Falha no envio: {self._error(proc)}")
            return
        self._run(["link", self._target], self._on_link)

    def _on_link(self, code, proc):
        if code != 0:
            self.failed.emit(f"Enviado, mas sem link: {self._error(proc)}")
            return
        link = bytes(proc.readAllStandardOutput()).decode().strip()
        self.finished.emit(link.splitlines()[-1] if link else "")
