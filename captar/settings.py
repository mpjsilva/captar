"""Configurações persistentes e janela de configurações."""

import os
import re

from PySide6.QtCore import QSettings, QStandardPaths, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import cloud


def _pictures_dir():
    path = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.PicturesLocation
    )
    return path or os.path.expanduser("~")


DEFAULTS = {
    "save_dir": _pictures_dir(),
    "format": "png",
    "jpg_quality": 90,
    "name_pattern": "Captar_%Y%m%d_%H%M%S",
    "shortcut_area": "Print",
    "shortcut_full": "Shift+Print",
    "cloud_remote": "",
    "cloud_folder": "Captar",
}


class Settings:
    def __init__(self):
        self._qs = QSettings("Captar", "captar")

    def get(self, key):
        default = DEFAULTS[key]
        value = self._qs.value(key, default)
        return int(value) if isinstance(default, int) else str(value)

    def set(self, key, value):
        self._qs.setValue(key, value)
        self._qs.sync()


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Configurações do Captar")
        self.setMinimumWidth(480)
        self._connect_proc = None

        layout = QVBoxLayout(self)

        # --- Arquivo ---------------------------------------------------
        files = QGroupBox("Arquivo")
        form = QFormLayout(files)

        dir_row = QWidget()
        dir_layout = QHBoxLayout(dir_row)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        self.save_dir = QLineEdit(settings.get("save_dir"))
        browse = QPushButton("Escolher…")
        browse.clicked.connect(self._browse)
        dir_layout.addWidget(self.save_dir)
        dir_layout.addWidget(browse)
        form.addRow("Pasta:", dir_row)

        self.format = QComboBox()
        self.format.addItem("PNG", "png")
        self.format.addItem("JPG", "jpg")
        self.format.setCurrentIndex(0 if settings.get("format") == "png" else 1)
        form.addRow("Formato:", self.format)

        self.quality = QSpinBox()
        self.quality.setRange(10, 100)
        self.quality.setSuffix(" %")
        self.quality.setValue(settings.get("jpg_quality"))
        form.addRow("Qualidade do JPG:", self.quality)
        self.format.currentIndexChanged.connect(self._update_quality)
        self._update_quality()

        self.pattern = QLineEdit(settings.get("name_pattern"))
        self.pattern.setToolTip("%Y ano, %m mês, %d dia, %H hora, %M minuto, %S segundo")
        form.addRow("Nome do arquivo:", self.pattern)
        layout.addWidget(files)

        # --- Atalhos ---------------------------------------------------
        keys = QGroupBox("Atalhos globais")
        keys_form = QFormLayout(keys)
        self.key_area = QKeySequenceEdit(QKeySequence(settings.get("shortcut_area")))
        self.key_area.setMaximumSequenceLength(1)
        self.key_full = QKeySequenceEdit(QKeySequence(settings.get("shortcut_full")))
        self.key_full.setMaximumSequenceLength(1)
        keys_form.addRow("Capturar área:", self.key_area)
        keys_form.addRow("Capturar tela inteira:", self.key_full)
        layout.addWidget(keys)

        # --- Nuvem -----------------------------------------------------
        box = QGroupBox("Nuvem (rclone)")
        cloud_form = QFormLayout(box)
        self.remote = QComboBox()
        cloud_form.addRow("Conta:", self.remote)
        self.folder = QLineEdit(settings.get("cloud_folder"))
        cloud_form.addRow("Pasta na nuvem:", self.folder)

        buttons_row = QWidget()
        buttons_layout = QHBoxLayout(buttons_row)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        for kind, label in cloud.PROVIDERS.items():
            button = QPushButton(f"Conectar {label}")
            button.clicked.connect(lambda _=False, k=kind: self._connect(k))
            button.setEnabled(cloud.available())
            buttons_layout.addWidget(button)
        cloud_form.addRow(buttons_row)
        self.cloud_status = QLabel()
        self.cloud_status.setWordWrap(True)
        cloud_form.addRow(self.cloud_status)
        layout.addWidget(box)
        self._load_remotes()

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.button(QDialogButtonBox.StandardButton.Save).setText("Salvar")
        bbox.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        bbox.accepted.connect(self._save)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _update_quality(self):
        self.quality.setEnabled(self.format.currentData() == "jpg")

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Pasta das capturas",
                                                self.save_dir.text())
        if path:
            self.save_dir.setText(path)

    def _load_remotes(self, select=None):
        current = select or self.settings.get("cloud_remote")
        self.remote.clear()
        remotes = cloud.list_remotes()
        for name, kind in remotes:
            self.remote.addItem(f"{name} ({cloud.PROVIDERS[kind]})", name)
        if not cloud.available():
            self.cloud_status.setText("O rclone não está instalado.")
        elif not remotes:
            self.cloud_status.setText("Nenhuma conta conectada.")
        else:
            self.cloud_status.setText("")
        index = self.remote.findData(current)
        if index >= 0:
            self.remote.setCurrentIndex(index)

    def _connect(self, kind):
        existing = {name for name, _ in cloud.list_remotes()}
        base = re.sub(r"\W", "", cloud.PROVIDERS[kind].lower())
        name, n = f"captar-{base}", 2
        while name in existing:
            name, n = f"captar-{base}{n}", n + 1
        proc = cloud.connect_process(kind, name)
        proc.finished.connect(lambda code, _s: self._connected(code, name, proc))
        self._connect_proc = proc
        self.cloud_status.setText(
            f"Faça o login em {cloud.PROVIDERS[kind]} no navegador que foi aberto…"
        )
        proc.start()

    def _connected(self, code, name, proc):
        self._connect_proc = None
        if code != 0:
            out = bytes(proc.readAll()).decode(errors="replace").strip()
            self._load_remotes()
            self.cloud_status.setText(
                "Falha ao conectar: " + (out.splitlines()[-1] if out else "erro desconhecido")
            )
            return
        self._load_remotes(select=name)
        self.cloud_status.setText("Conta conectada.")

    def _save(self):
        if self.key_area.keySequence() == self.key_full.keySequence() and \
                not self.key_area.keySequence().isEmpty():
            QMessageBox.warning(self, "Captar", "Os dois atalhos são iguais.")
            return
        s = self.settings
        s.set("save_dir", self.save_dir.text().strip() or DEFAULTS["save_dir"])
        s.set("format", self.format.currentData())
        s.set("jpg_quality", self.quality.value())
        s.set("name_pattern", self.pattern.text().strip() or DEFAULTS["name_pattern"])
        s.set("shortcut_area", self.key_area.keySequence().toString())
        s.set("shortcut_full", self.key_full.keySequence().toString())
        s.set("cloud_remote", self.remote.currentData() or "")
        s.set("cloud_folder", self.folder.text().strip())
        self.accept()
