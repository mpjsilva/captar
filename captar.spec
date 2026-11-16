Name:           captar
Version:        2.0.0
Release:        1%{?dist}
Summary:        Captura de tela com anotações para KDE Plasma Wayland
License:        MIT
URL:            https://github.com/jamerson/captar
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
Requires:       python3
Requires:       python3-pyside6
Requires:       python3-gobject
Requires:       xdg-desktop-portal
Requires:       kf6-kglobalaccel
Recommends:     rclone

%description
Captar é uma ferramenta de captura de tela feita para o KDE Plasma no
Wayland. Fica residente na bandeja do sistema, esmaece todas as telas ao
receber o atalho Print Screen, permite recortar uma área e anotar o
resultado com setas, retângulos e caixas de texto.

%prep
%autosetup

%build

%install
install -d %{buildroot}%{_bindir}
install -d %{buildroot}%{_datadir}/captar
install -d %{buildroot}%{_datadir}/applications
install -d %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
install -d %{buildroot}%{_sysconfdir}/xdg/autostart

install -m 0755 bin/captar %{buildroot}%{_bindir}/captar
cp -r captar %{buildroot}%{_datadir}/captar/
find %{buildroot}%{_datadir}/captar -name '__pycache__' -type d -exec rm -rf {} +
install -m 0644 captar.desktop %{buildroot}%{_datadir}/applications/captar.desktop
install -m 0644 captar-autostart.desktop %{buildroot}%{_sysconfdir}/xdg/autostart/captar.desktop
install -m 0644 captar.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/captar.svg

%files
%license LICENSE
%{_bindir}/captar
%{_datadir}/captar
%{_datadir}/applications/captar.desktop
%{_sysconfdir}/xdg/autostart/captar.desktop
%{_datadir}/icons/hicolor/scalable/apps/captar.svg

%changelog
* Mon Nov 16 2026 Jamerson <jamerson@localhost> - 2.0.0-1
- Seleção ajustável: alças, mover, setas do teclado e tamanho em pixels
- Barra vertical de ferramentas e barra horizontal de ações (estilo Lightshot)
- Novas ferramentas: lápis, linha, marca-texto e mover/apagar anotação
- Espessura do traço, paleta e cor personalizada
- Desfazer/refazer completos (Ctrl+Z, Ctrl+Shift+Z)
- Lupa com coordenadas e cor do pixel
- Salvar como (Ctrl+S), aviso na bandeja e abrir pasta
- Envio para Google Drive, OneDrive ou Dropbox via rclone com link copiado
- Configurações: pasta, PNG/JPG, nome do arquivo e atalhos
- Captura da tela inteira (Shift+Print)

* Mon Nov 16 2026 Jamerson <jamerson@localhost> - 1.3.0-1
- Caixa de texto multilinha, redimensionável e movível
- Reeditar texto com clique (ferramenta Texto) ou duplo clique
- Trocar cor e tamanho do texto durante a edição; cor personalizada

* Mon Nov 16 2026 Jamerson <jamerson@localhost> - 1.2.0-1
- Caixa de texto editável direto na tela
- Cursor vira seta sobre a barra de ferramentas

* Mon Nov 16 2026 Jamerson <jamerson@localhost> - 1.1.0-1
- App residente na bandeja com atalho global Print Screen
- Ctrl+C copia a imagem resultante
- Barra de ferramentas acompanha a seleção

* Mon Nov 16 2026 Jamerson <jamerson@localhost> - 1.0.0-1
- Versão inicial
