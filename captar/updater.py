"""Atualização automática a partir das releases do GitHub.

Consulta a release mais recente de mpjsilva/captar, baixa o pacote do
mesmo formato do instalado (.rpm no Fedora, .deb no Debian/Ubuntu) e
instala com ``pkexec dnf``/``pkexec apt-get`` (o sistema pede a senha).
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, Signal

from . import __version__

REPO = "mpjsilva/captar"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
INSTALLED_DIR = "/usr/share/captar"


def _parse(version):
    parts = []
    for piece in version.lstrip("vV").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def is_newer(remote, local=__version__):
    return _parse(remote) > _parse(local)


def package_format():
    """'exe', 'deb', 'rpm' ou None (rodando pelo código-fonte)."""
    if sys.platform == "win32":
        return "exe" if getattr(sys, "frozen", False) else None
    here = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if here != INSTALLED_DIR:
        return None
    if os.path.exists("/var/lib/dpkg/info/captar.list") and shutil.which("apt-get"):
        return "deb"
    if shutil.which("dnf"):
        return "rpm"
    return None


def _request(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={
        "Accept": accept,
        "User-Agent": "captar-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return urllib.request.urlopen(req, timeout=30)


class Updater(QObject):
    """Verifica e baixa em segundo plano; os sinais chegam na thread da GUI."""

    available = Signal(str, str)  # versão, notas
    up_to_date = Signal()
    downloaded = Signal(str)  # caminho do .rpm
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._release = None
        self._busy = False

    @property
    def version(self):
        return self._release["tag_name"].lstrip("v") if self._release else ""

    def check(self):
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        try:
            with _request(API) as resp:
                release = json.load(resp)
        except urllib.error.HTTPError as exc:
            msg = f"GitHub respondeu {exc.code} ao verificar atualizações."
            self._busy = False
            self.failed.emit(msg)
            return
        except (OSError, ValueError) as exc:
            self._busy = False
            self.failed.emit(f"Falha ao verificar atualizações: {exc}")
            return
        self._busy = False
        tag = release.get("tag_name", "")
        if tag and is_newer(tag) and self._asset(release):
            self._release = release
            self.available.emit(tag.lstrip("v"), release.get("body") or "")
        else:
            self.up_to_date.emit()

    @staticmethod
    def _asset(release):
        suffix = {"deb": "_all.deb", "exe": "-setup-x64.exe"}.get(
            package_format(), ".noarch.rpm")
        for asset in release.get("assets", []):
            if asset.get("name", "").endswith(suffix):
                return asset
        return None

    def download(self):
        if self._release is None or self._busy:
            return
        self._busy = True
        threading.Thread(target=self._download, daemon=True).start()

    def _download(self):
        asset = self._asset(self._release)
        directory = tempfile.mkdtemp(prefix="captar-update-")
        path = os.path.join(directory, os.path.basename(asset["name"]))
        try:
            with _request(asset["url"], accept="application/octet-stream") as resp, \
                    open(path, "wb") as fh:
                shutil.copyfileobj(resp, fh)
        except (OSError, urllib.error.HTTPError) as exc:
            self._busy = False
            self.failed.emit(f"Falha ao baixar a atualização: {exc}")
            return
        self._busy = False
        self.downloaded.emit(path)


def install_command(path):
    """Comando que instala o pacote pedindo a senha pelo polkit."""
    if path.lower().endswith(".exe"):
        return [path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
    if path.endswith(".deb"):
        return ["pkexec", "apt-get", "install", "-y", path]
    return ["pkexec", "dnf", "install", "-y", path]
