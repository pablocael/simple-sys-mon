#!/usr/bin/env bash
# Remove the simple-sys-mon desktop entry and icons for the current user.
set -euo pipefail

APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
APP_ID="simple-sys-mon"

rm -f "$APPS/$APP_ID.desktop"
rm -f "$ICONS/scalable/apps/$APP_ID.svg"
for size in 16 24 32 48 64 128 256 512; do
    rm -f "$ICONS/${size}x${size}/apps/$APP_ID.png"
done

gtk-update-icon-cache -f -t "$ICONS" >/dev/null 2>&1 || true
update-desktop-database "$APPS" >/dev/null 2>&1 || true
for kb in kbuildsycoca6 kbuildsycoca5; do command -v "$kb" >/dev/null 2>&1 && "$kb" >/dev/null 2>&1 || true; done

echo "Removed simple-sys-mon desktop entry and icons."
