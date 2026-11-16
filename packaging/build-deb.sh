#!/bin/sh
# Gera captar_<versão>_all.deb na raiz do projeto (requer dpkg-deb).
set -e
cd "$(dirname "$0")/.."
V=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' captar/__init__.py)
R=$(mktemp -d)
trap 'rm -rf "$R"' EXIT

install -Dm755 bin/captar "$R/usr/bin/captar"
mkdir -p "$R/usr/share/captar"
cp -r captar "$R/usr/share/captar/"
find "$R/usr/share/captar" -name __pycache__ -type d -exec rm -rf {} +
install -Dm644 captar.desktop "$R/usr/share/applications/captar.desktop"
install -Dm644 captar-autostart.desktop "$R/etc/xdg/autostart/captar.desktop"
install -Dm644 captar.svg "$R/usr/share/icons/hicolor/scalable/apps/captar.svg"
install -Dm644 LICENSE "$R/usr/share/doc/captar/copyright"

mkdir -p "$R/DEBIAN"
SIZE=$(du -sk "$R/usr" "$R/etc" | awk '{s+=$1} END {print s}')
cat > "$R/DEBIAN/control" <<CTL
Package: captar
Version: $V
Architecture: all
Maintainer: mpjsilva <mpjsilva@users.noreply.github.com>
Installed-Size: $SIZE
Depends: python3, python3-gi, python3-pyside6.qtcore, python3-pyside6.qtgui, python3-pyside6.qtwidgets, xdg-desktop-portal, pkexec | policykit-1
Recommends: rclone, kglobalacceld, xdg-desktop-portal-kde
Section: graphics
Priority: optional
Homepage: https://github.com/mpjsilva/captar
Description: Captura de tela com anotações para KDE Plasma Wayland
 Fica na bandeja do sistema; o Print Screen escurece as telas, permite
 recortar uma área e anotar com lápis, linha, seta, retângulo,
 marca-texto e texto. Salva, copia ou envia para Google Drive, OneDrive
 ou Dropbox via rclone. Atualiza sozinho pelas releases do GitHub.
CTL
cat > "$R/DEBIAN/conffiles" <<CTL
/etc/xdg/autostart/captar.desktop
CTL

dpkg-deb --root-owner-group --build "$R" "captar_${V}_all.deb"
