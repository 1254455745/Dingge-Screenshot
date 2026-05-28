#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3)"
  fi
fi

"$PYTHON_BIN" -m pip install -r requirements.txt -r requirements-build.txt

"$PYTHON_BIN" scripts/create_dmg_background.py

rm -rf build dist

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --windowed \
  --name "定格截图" \
  --icon "assets/app.icns" \
  --add-data "assets:assets" \
  --osx-bundle-identifier "com.anzhen.dinggescreenshot" \
  "定格截图.py"

codesign --force --deep --sign - "dist/定格截图.app"
ditto -c -k --sequesterRsrc --keepParent "dist/定格截图.app" "dist/定格截图-macOS.zip"

DMG_ROOT="dist/dmg-root"
DMG_RW="dist/定格截图-macOS-rw.dmg"
DMG_FINAL="dist/定格截图-macOS.dmg"
rm -rf "$DMG_ROOT"
mkdir -p "$DMG_ROOT"
mkdir -p "$DMG_ROOT/.background"
cp -R "dist/定格截图.app" "$DMG_ROOT/"
ln -s /Applications "$DMG_ROOT/Applications"
cp "assets/dmg-background.png" "$DMG_ROOT/.background/"

hdiutil create -volname "定格截图" -srcfolder "$DMG_ROOT" -ov -format UDRW -fs HFS+ "$DMG_RW"

MOUNT_POINT=""
cleanup_dmg_mount() {
  if [[ -n "$MOUNT_POINT" && -d "$MOUNT_POINT" ]]; then
    hdiutil detach "$MOUNT_POINT" -quiet || true
  fi
}
trap cleanup_dmg_mount EXIT

ATTACH_OUTPUT="$(hdiutil attach "$DMG_RW" -readwrite -noverify)"
MOUNT_POINT="$(printf "%s\n" "$ATTACH_OUTPUT" | awk '/\/Volumes\// {print substr($0, index($0, "/Volumes/")); exit}')"
sleep 1

osascript <<APPLESCRIPT
tell application "Finder"
  tell disk "定格截图"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set bounds of container window to {120, 120, 840, 560}

    set theViewOptions to the icon view options of container window
    set arrangement of theViewOptions to not arranged
    set icon size of theViewOptions to 100
    set background picture of theViewOptions to (POSIX file "$MOUNT_POINT/.background/dmg-background.png")

    set position of item "定格截图.app" of container window to {190, 236}
    set position of item "Applications" of container window to {530, 236}

    update without registering applications
    delay 1
    close
  end tell
end tell
APPLESCRIPT

sync
hdiutil detach "$MOUNT_POINT" -quiet
trap - EXIT
hdiutil convert "$DMG_RW" -format UDZO -imagekey zlib-level=9 -o "$DMG_FINAL" -ov

rm -f "$DMG_RW"
rm -rf "$DMG_ROOT"

echo "macOS app: dist/定格截图.app"
echo "macOS zip: dist/定格截图-macOS.zip"
echo "macOS dmg: $DMG_FINAL"
