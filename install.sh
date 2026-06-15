#!/usr/bin/env bash
# =============================================================================
# install.sh — install the built Keryx Wallet so it appears in the app menu
# and shows the correct icon in the taskbar (fixes the generic "gear" icon).
#
# Run AFTER building with ./build_executable.sh (which produces dist/keryx-wallet).
#
#   chmod +x install.sh
#   ./install.sh
#
# Installs to /opt/keryx-wallet, the icon into the hicolor theme, and the
# .desktop entry so GNOME/Wayland matches the window to the icon.
# =============================================================================
set -euo pipefail

if [ ! -f dist/keryx-wallet ]; then
    echo "dist/keryx-wallet not found. Run ./build_executable.sh first."
    exit 1
fi

echo "-- installing to /opt/keryx-wallet (sudo) --"
sudo mkdir -p /opt/keryx-wallet
sudo cp dist/keryx-wallet /opt/keryx-wallet/keryx-wallet
sudo cp assets/keryx.png /opt/keryx-wallet/keryx.png

# Install icon into the icon theme at multiple sizes so it's crisp everywhere.
echo "-- installing icons --"
for s in 48 128 256; do
    sudo mkdir -p "/usr/share/icons/hicolor/${s}x${s}/apps"
    sudo cp "assets/keryx-${s}.png" \
        "/usr/share/icons/hicolor/${s}x${s}/apps/keryx-emblem.png"
done

# Install the .desktop entry. Icon=keryx-emblem now resolves via the icon theme.
echo "-- installing desktop entry --"
sudo tee /usr/share/applications/keryx-wallet.desktop >/dev/null << 'DESKTOP'
[Desktop Entry]
Type=Application
Name=Keryx Wallet
Comment=Desktop wallet for the Keryx network
Exec=/opt/keryx-wallet/keryx-wallet
Icon=keryx-emblem
Terminal=false
Categories=Finance;Network;
StartupWMClass=keryx-wallet
DESKTOP

# Refresh caches so the icon/entry appear without a logout.
echo "-- refreshing desktop caches --"
sudo update-desktop-database /usr/share/applications 2>/dev/null || true
sudo gtk-update-icon-cache /usr/share/icons/hicolor 2>/dev/null || true

echo ""
echo "SUCCESS. Keryx Wallet installed."
echo "If the taskbar still shows a generic icon, log out and back in once so"
echo "GNOME re-reads the desktop database."
