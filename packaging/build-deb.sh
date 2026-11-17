#!/bin/sh
# Gera captar_<versão>_amd64.deb na raiz do projeto (requer dpkg-deb e pip).
#
# O PySide6 vai embutido (/usr/share/captar/lib) porque várias distribuições
# (Ubuntu 24.04, Debian 12, Mint…) não o oferecem nos repositórios.
set -e
cd "$(dirname "$0")/.."
V=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' captar/__init__.py)
PYSIDE=6.8.3
CACHE=${XDG_CACHE_HOME:-$HOME/.cache}/captar-build
R=$(mktemp -d)
trap 'rm -rf "$R"' EXIT

# --- PySide6 embutido (abi3: serve para qualquer Python >= 3.9) ----------
mkdir -p "$CACHE"
pip3 download -q --only-binary=:all: --no-deps \
    --platform manylinux_2_28_x86_64 --python-version 3.9 -d "$CACHE" \
    "PySide6-Essentials==$PYSIDE" "shiboken6==$PYSIDE"
LIB="$R/usr/share/captar/lib"
mkdir -p "$LIB"
for w in "$CACHE"/PySide6_Essentials-$PYSIDE-*.whl "$CACHE"/shiboken6-$PYSIDE-*.whl; do
    python3 -m zipfile -e "$w" "$LIB"
done
rm -rf "$LIB"/*.dist-info
# Só o que o Captar usa: Core, Gui, Widgets, DBus, Svg, Network e as
# integrações de X11/Wayland.
KEEP='Core|Gui|Widgets|DBus|Svg|SvgWidgets|Network|OpenGL|XcbQpa|WaylandClient|WaylandEglClientHwIntegration|WlShellIntegration|EglFSDeviceIntegration|EglFsKmsSupport'
P="$LIB/PySide6"
for f in "$P"/Qt/lib/libQt6*.so*; do
    n=$(basename "$f" | sed -E 's/libQt6([A-Za-z0-9]+)\.so.*/\1/')
    echo "$n" | grep -qxE "$KEEP" || rm -f "$f"
done
for f in "$P"/Qt*.abi3.so "$P"/Qt*.pyi; do
    n=$(basename "$f" | sed -E 's/^Qt([A-Za-z0-9]+)\..*/\1/')
    echo "$n" | grep -qxE "$KEEP" || rm -f "$f"
done
( cd "$P" && rm -rf Qt/qml Qt/libexec Qt/metatypes Qt/translations examples glue \
    typesystems include scripts lupdate* assistant* designer* linguist* rcc uic \
    qml* Qt/plugins/qmltooling Qt/plugins/qmllint Qt/plugins/qmlls \
    Qt/plugins/sqldrivers Qt/plugins/designer Qt/plugins/help \
    Qt/plugins/wayland-graphics-integration-server )
find "$LIB" -name __pycache__ -type d -exec rm -rf {} +

# --- Captar ---------------------------------------------------------------
install -Dm755 bin/captar "$R/usr/bin/captar"
cp -r captar "$R/usr/share/captar/"
find "$R/usr/share/captar/captar" -name __pycache__ -type d -exec rm -rf {} +
install -Dm644 captar.desktop "$R/usr/share/applications/captar.desktop"
install -Dm644 captar-autostart.desktop "$R/etc/xdg/autostart/captar.desktop"
install -Dm644 captar.svg "$R/usr/share/icons/hicolor/scalable/apps/captar.svg"
install -Dm644 LICENSE "$R/usr/share/doc/captar/copyright"

mkdir -p "$R/DEBIAN"
SIZE=$(du -sk "$R/usr" "$R/etc" | awk '{s+=$1} END {print s}')
cat > "$R/DEBIAN/control" <<CTL
Package: captar
Version: $V
Architecture: amd64
Maintainer: mpjsilva <mpjsilva@users.noreply.github.com>
Installed-Size: $SIZE
Depends: python3 (>= 3.9), python3-gi, gir1.2-glib-2.0, xdg-desktop-portal, pkexec | policykit-1, libegl1, libgl1, libfontconfig1, libfreetype6, libdbus-1-3, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xkb1, libwayland-client0, libwayland-cursor0, libwayland-egl1
Recommends: rclone, kglobalacceld
Section: graphics
Priority: optional
Homepage: https://github.com/mpjsilva/captar
Description: Captura de tela com anotações para Wayland
 Fica na bandeja do sistema; o Print Screen escurece as telas, permite
 recortar uma área e anotar com lápis, linha, seta, retângulo,
 marca-texto e texto. Salva, copia ou envia para Google Drive, OneDrive
 ou Dropbox via rclone. Atualiza sozinho pelas releases do GitHub.
CTL
cat > "$R/DEBIAN/conffiles" <<CTL
/etc/xdg/autostart/captar.desktop
CTL

dpkg-deb -Zxz --root-owner-group --build "$R" "captar_${V}_amd64.deb"
