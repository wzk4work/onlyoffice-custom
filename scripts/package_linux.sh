#!/usr/bin/env bash
# Repackage official ONLYOFFICE linux artifacts with our patched binaries.
#
# Usage: package_linux.sh <work_dir> <official_dir> <out_dir> <version> <plat> <arch>
#   <official_dir> : dir containing official.deb, official.rpm, official.AppImage, official.tar.xz
#   <plat>         : linux_64 | linux_arm64
#   <arch>         : x86_64 | aarch64   (used for appimagetool download + naming)
set -euo pipefail

WORK_DIR="$(cd "${1:?usage}" && pwd)"
OFFICIAL_DIR="$(cd "${2:?usage}" && pwd)"
OUT_DIR="$3"; VER="${4#v}"; PLAT="$5"; ARCH="$6"
mkdir -p "$OUT_DIR"
EX="$WORK_DIR/pkg_extract"
rm -rf "$EX"; mkdir -p "$EX"

find_appdir() {  # locate dir holding the DesktopEditors binary inside a tree
  dirname "$(find "$1" -type f -name "DesktopEditors" | head -n1)"
}

overlay_app() {  # $1 = target app dir: push rebuilt binaries + web assets
  local appdir="$1"
  echo "   -> overlay $appdir"
  cp -f "$WORK_DIR"/core/build/lib/"$PLAT"/libascdocumentscore.so* "$appdir/" 2>/dev/null || \
    cp -f "$WORK_DIR"/core/build/lib/"$PLAT"/*ascdocumentscore*.so* "$appdir/" || true
  cp -f "$WORK_DIR"/core/build/lib/"$PLAT"/libqtascdocumentscore.so* "$appdir/" 2>/dev/null || true

  local exe
  exe="$(find "$WORK_DIR/desktop-apps/win-linux" "$WORK_DIR/core/build/bin" -type f -name "DesktopEditors" 2>/dev/null | head -n1)"
  [ -n "$exe" ] && cp -f "$exe" "$appdir/DesktopEditors"

  cp -f "$WORK_DIR/desktop-apps/common/loginpage/deploy/index.html" "$appdir/index.html"
  cp -f "$WORK_DIR/desktop-apps/common/loginpage/deploy/noconnect.html" "$appdir/editors/webext/noconnect.html"
  rm -rf "$appdir/editors/web-apps"
  cp -R "$WORK_DIR/web-apps/deploy/web-apps" "$appdir/editors/web-apps"
  find "$appdir/editors/web-apps/apps" -type d \( -name ie -o -name mobile -o -name embed \) -prune -exec rm -rf {} +
  cp -f "$WORK_DIR/web-apps/apps/api/documents/index.html.desktop" "$appdir/editors/web-apps/apps/api/documents/index.html"
  chmod +x "$appdir/DesktopEditors"
}

echo "== Step 1: extract official deb & overlay =="
DEB_TREE="$EX/deb"
dpkg-deb -x "$OFFICIAL_DIR/official.deb" "$DEB_TREE"
dpkg-deb -e "$OFFICIAL_DIR/official.deb" "$DEB_TREE/DEBIAN"
APPDIR="$(find_appdir "$DEB_TREE")"
[ -n "$APPDIR" ] || { echo "ERROR: app dir not found in deb"; exit 1; }
overlay_app "$APPDIR"

echo "== Step 2: repack deb =="
( cd "$DEB_TREE" && find . -path ./DEBIAN -prune -o -type f -print0 | xargs -0 md5sum > DEBIAN/md5sums )
OUT_DEB="$OUT_DIR/onlyoffice-desktopeditors-${VER}-custom_$( [ "$ARCH" = x86_64 ] && echo amd64 || echo arm64 ).deb"
dpkg-deb --root-owner-group -b "$DEB_TREE" "$OUT_DEB"
sha256sum "$OUT_DEB" | tee "$OUT_DEB.sha256"

echo "== Step 3: repack rpm =="
RPM_TREE="$EX/rpm"
mkdir -p "$RPM_TREE"
( cd "$RPM_TREE" && rpm2cpio "$OFFICIAL_DIR/official.rpm" | cpio -idm --quiet )
RPM_APPDIR="$(find_appdir "$RPM_TREE")"
[ -n "$RPM_APPDIR" ] || { echo "ERROR: app dir not found in rpm"; exit 1; }
rsync -a --delete "$APPDIR/" "$RPM_APPDIR/"

REL_PREFIX="/${RPM_APPDIR#"$RPM_TREE"}"
RPM_NAME="$(rpm -qp --queryformat '%{NAME}' "$OFFICIAL_DIR/official.rpm" 2>/dev/null || echo onlyoffice-desktopeditors)"
RPM_VER="$(rpm -qp --queryformat '%{VERSION}' "$OFFICIAL_DIR/official.rpm" 2>/dev/null || echo "$VER")"
RPM_REL="$(rpm -qp --queryformat '%{RELEASE}' "$OFFICIAL_DIR/official.rpm" 2>/dev/null || echo 1)"
rpm -qpR "$OFFICIAL_DIR/official.rpm" 2>/dev/null | grep -v "^rpmlib(" | sed 's/^/Requires: /' > "$EX/requires.txt" || true
rpm -qp --scripts "$OFFICIAL_DIR/official.rpm" > "$EX/rpm_scripts.txt" 2>/dev/null || true

TOPDIR="$EX/rpmbuild"; mkdir -p "$TOPDIR"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
OUT_RPM="$OUT_DIR/onlyoffice-desktopeditors-${VER}-custom.$( [ "$ARCH" = x86_64 ] && echo x86_64 || echo aarch64 ).rpm"
{
  echo "%define debug_package %{nil}"
  echo "%global _build_id_links none"
  echo "Name: $RPM_NAME"
  echo "Version: $RPM_VER"
  echo "Release: ${RPM_REL}.custom"
  echo "Summary: ONLYOFFICE Desktop Editors (custom build)"
  echo "License: AGPL-3.0"
  echo "AutoReqProv: no"
  cat "$EX/requires.txt"
  echo ""
  echo "%description"
  echo "ONLYOFFICE Desktop Editors custom build."
  echo ""
  echo "%install"
  echo "cp -a $RPM_TREE/. %{buildroot}/"
  echo ""
  echo "%files"
  echo "/"
} > "$TOPDIR/SPECS/pkg.spec"
rpmbuild -bb --define "_topdir $TOPDIR" --target "$ARCH-redhat-linux" "$TOPDIR/SPECS/pkg.spec"
find "$TOPDIR/RPMS" -name "*.rpm" -exec cp {} "$OUT_RPM" \;
sha256sum "$OUT_RPM" | tee "$OUT_RPM.sha256"

echo "== Step 4: repack AppImage =="
AI_TREE="$EX/appimage"
mkdir -p "$AI_TREE"
chmod +x "$OFFICIAL_DIR/official.AppImage" || true
( cd "$AI_TREE" && "$OFFICIAL_DIR/official.AppImage" --appimage-extract >/dev/null )
AI_ROOT="$AI_TREE/squashfs-root"
AI_APPDIR="$(find_appdir "$AI_ROOT")"
[ -n "$AI_APPDIR" ] || { echo "ERROR: app dir not found in AppImage"; exit 1; }
rsync -a --delete "$APPDIR/" "$AI_APPDIR/"

TOOL_ARCH="$ARCH"
APPIMAGETOOL="$EX/appimagetool-$TOOL_ARCH.AppImage"
curl -fL --retry 3 -o "$APPIMAGETOOL" \
  "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${TOOL_ARCH}.AppImage"
chmod +x "$APPIMAGETOOL"
OUT_AI="$OUT_DIR/DesktopEditors-${VER}-custom-${ARCH}.AppImage"
ARCH="$TOOL_ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" "$AI_ROOT" "$OUT_AI"
sha256sum "$OUT_AI" | tee "$OUT_AI.sha256"

echo "== Step 5: repack tar.xz =="
TAR_TREE="$EX/tar"
mkdir -p "$TAR_TREE"
tar -xJf "$OFFICIAL_DIR/official.tar.xz" -C "$TAR_TREE"
TAR_APPDIR="$(find_appdir "$TAR_TREE")"
[ -n "$TAR_APPDIR" ] || { echo "ERROR: app dir not found in tar"; exit 1; }
rsync -a --delete "$APPDIR/" "$TAR_APPDIR/"
OUT_TAR="$OUT_DIR/onlyoffice-desktopeditors-${VER}-custom-${ARCH}.tar.xz"
( cd "$TAR_TREE" && tar -cJf "$OUT_TAR" . )
sha256sum "$OUT_TAR" | tee "$OUT_TAR.sha256"

ls -lh "$OUT_DIR"
echo "LINUX PACKAGES READY: $OUT_DIR"
