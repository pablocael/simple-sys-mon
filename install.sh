#!/usr/bin/env bash
# Install simple-sys-mon into the desktop (menu entry + custom icon) for the
# current user. Relocatable: it points the launcher at wherever this repo lives.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
APP_ID="simple-sys-mon"

mkdir -p "$APPS"

# --- icons: scalable SVG + rasterized PNG sizes -----------------------------
install -Dm644 "$DIR/assets/icon.svg" "$ICONS/scalable/apps/$APP_ID.svg"
for size in 16 24 32 48 64 128 256 512; do
    src="$DIR/assets/icons/$APP_ID-$size.png"
    [ -f "$src" ] && install -Dm644 "$src" "$ICONS/${size}x${size}/apps/$APP_ID.png"
done

# --- desktop entry (Exec resolved to this checkout's run.sh) -----------------
cat > "$APPS/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=simple-sys-mon
GenericName=System Monitor
Comment=Lightweight time-series monitor for CPU, RAM, GPU, VRAM, network and disk
Exec=$DIR/run.sh
Icon=$APP_ID
Terminal=false
Categories=System;Monitor;
Keywords=cpu;ram;gpu;vram;network;disk;monitor;
StartupNotify=true
EOF
chmod 644 "$APPS/$APP_ID.desktop"

# --- refresh caches so it shows up immediately ------------------------------
gtk-update-icon-cache -f -t "$ICONS" >/dev/null 2>&1 || true
update-desktop-database "$APPS" >/dev/null 2>&1 || true
for kb in kbuildsycoca6 kbuildsycoca5; do command -v "$kb" >/dev/null 2>&1 && "$kb" >/dev/null 2>&1 || true; done

echo "Installed simple-sys-mon. Look for it in your launcher under 'System'."
echo "  launcher : $DIR/run.sh"
echo "  desktop  : $APPS/$APP_ID.desktop"
echo "Run ./uninstall.sh to remove it."
