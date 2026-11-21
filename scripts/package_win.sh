#!/usr/bin/env bash
# Repackage official ONLYOFFICE Windows zip with our patched binaries.
#
# Usage: package_win.sh <work_dir> <official_zip> <out_dir> <version> <plat> <arch> <native>
#   <plat>   : win_64 | win_arm64
#   <arch>   : x64 | arm64            (naming only)
#   <native> : 1 = overlay rebuilt dlls/exe; 0 = web assets only (arm64)
set -euo pipefail

WORK_DIR="$(cd "${1:?usage}" && pwd)"
OFFICIAL_ZIP="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
OUT_DIR="$3"; VER="${4#v}"; PLAT="$5"; ARCH="$6"; NATIVE="${7:-1}"
mkdir -p "$OUT_DIR"
EX="$WORK_DIR/pkg_extract_win"
rm -rf "$EX"; mkdir -p "$EX"

echo "== Extract official zip =="
unzip -q "$OFFICIAL_ZIP" -d "$EX/root"
APPDIR="$(dirname "$(find "$EX/root" -type f -name "editors.exe" | head -n1)")"
if [ ! -d "$APPDIR" ]; then
  APPDIR="$(dirname "$(find "$EX/root" -type f -name "DesktopEditors.exe" | head -n1)")"
fi
[ -d "$APPDIR" ] || { echo "ERROR: app dir not found in zip"; exit 1; }
echo "   app dir: $APPDIR"

if [ "$NATIVE" = "1" ]; then
  echo "== Overlay rebuilt binaries =="
  cp -f "$WORK_DIR"/core/build/lib/"$PLAT"/ascdocumentscore.dll "$APPDIR/ascdocumentscore.dll"
  cp -f "$WORK_DIR"/core/build/lib/"$PLAT"/qtascdocumentscore.dll "$APPDIR/qtascdocumentscore.dll"
  EXE="$(find "$WORK_DIR/desktop-apps/win-linux" "$WORK_DIR/core/build/bin" -type f -name "DesktopEditors.exe" 2>/dev/null | head -n1)"
  [ -n "$EXE" ] && cp -f "$EXE" "$APPDIR/editors.exe"
else
  echo "== Overlay-only mode (no native rebuild) =="
fi

echo "== Overlay web assets =="
cp -f "$WORK_DIR/desktop-apps/common/loginpage/deploy/index.html" "$APPDIR/index.html"
cp -f "$WORK_DIR/desktop-apps/common/loginpage/deploy/noconnect.html" "$APPDIR/editors/webext/noconnect.html"
rm -rf "$APPDIR/editors/web-apps"
cp -R "$WORK_DIR/web-apps/deploy/web-apps" "$APPDIR/editors/web-apps"
find "$APPDIR/editors/web-apps/apps" -type d \( -name ie -o -name mobile -o -name embed \) -prune -exec rm -rf {} +
cp -f "$WORK_DIR/web-apps/apps/api/documents/index.html.desktop" "$APPDIR/editors/web-apps/apps/api/documents/index.html"

echo "== Rezip =="
OUT_ZIP="$OUT_DIR/DesktopEditors-${VER}-custom_${ARCH}.zip"
( cd "$EX/root" && 7z a -tzip "$OUT_ZIP" ./* ) >/dev/null
sha256sum "$OUT_ZIP" | tee "$OUT_ZIP.sha256"

ls -lh "$OUT_DIR"
echo "WINDOWS PACKAGE READY: $OUT_ZIP"
