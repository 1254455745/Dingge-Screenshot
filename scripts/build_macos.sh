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
hdiutil create -volname "定格截图" -srcfolder "dist/定格截图.app" -ov -format UDZO "dist/定格截图-macOS.dmg"

echo "macOS app: dist/定格截图.app"
echo "macOS zip: dist/定格截图-macOS.zip"
echo "macOS dmg: dist/定格截图-macOS.dmg"
