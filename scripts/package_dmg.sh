#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK_DIR="$(cd "${1:?usage: package_dmg.sh <work_dir> <official_app> <out_dmg> [version]}" && pwd)"
OFFICIAL_APP="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
OUT_DMG="$3"
VER="${4:-10.0.0}"
VER_CLEAN="${VER#v}"

echo "== Step 1: Build web-apps =="
(
  cd "$WORK_DIR/web-apps/translation"
  python merge_and_check.py
)
(
  cd "$WORK_DIR/web-apps/build"
  npm install --no-audit --no-fund
  npx grunt --force
)

echo "== Step 2: Build loginpage (addondialog + noconnect + start page) =="
for sub in addondialog noconnect .; do
  (
    cd "$WORK_DIR/desktop-apps/common/loginpage/$sub"
    npm install --no-audit --no-fund
    npm run build
  )
done

echo "== Step 3: Clone official app bundle as overlay base =="
STAGE_DIR="$WORK_DIR/dist"
APP="$STAGE_DIR/ONLYOFFICE.app"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"
cp -a "$OFFICIAL_APP" "$APP"

CONT="$APP/Contents"
RES="$CONT/Resources"
FW="$CONT/Frameworks"

# Overlay updated ascdocumentscore.framework binary
cp -f "$WORK_DIR/core/build/lib/mac_64/ascdocumentscore.framework/Versions/A/ascdocumentscore" \
      "$FW/ascdocumentscore.framework/Versions/A/ascdocumentscore"

# Overlay updated loginpage bundles
cp -f "$WORK_DIR/desktop-apps/common/loginpage/deploy/index.html" "$RES/login/index.html"
cp -f "$WORK_DIR/desktop-apps/common/loginpage/deploy/addon.html" "$RES/login/addon.html"
cp -f "$WORK_DIR/desktop-apps/common/loginpage/deploy/noconnect.html" "$RES/login/noconnect.html"

# Overlay updated web-apps (keep official sdkjs & sdkjs-plugins intact)
rm -rf "$RES/editors/web-apps"
cp -R "$WORK_DIR/web-apps/deploy/web-apps" "$RES/editors/web-apps"
find "$RES/editors/web-apps/apps" -type d \( -name ie -o -name mobile -o -name embed \) -prune -exec rm -rf {} +
cp -f "$WORK_DIR/web-apps/apps/api/documents/index.html.desktop" "$RES/editors/web-apps/apps/api/documents/index.html"
cp -f "$WORK_DIR/desktop-apps/common/loginpage/deploy/noconnect.html" "$RES/editors/webext/noconnect.html" 2>/dev/null || true

echo "== Step 4: Compile & link macOS host executable =="
MACOS_DIR="$WORK_DIR/desktop-apps/macos"
SDK_SYSROOT="$(xcrun --show-sdk-path)"
OBJ_DIR="$WORK_DIR/macos_obj"
rm -rf "$OBJ_DIR"
mkdir -p "$OBJ_DIR"

INC_FILE="$OBJ_DIR/includes.txt"
while IFS= read -r line; do
  if [ "$line" = "-I" ]; then
    echo "-I"
  else
    echo "$WORK_DIR/$line"
  fi
done < "$REPO_ROOT/config/macos_includes.txt" > "$INC_FILE"

SRC_FILE="$OBJ_DIR/srcs.txt"
while IFS= read -r line; do
  echo "$WORK_DIR/$line"
done < "$REPO_ROOT/config/macos_srcs.txt" > "$SRC_FILE"

cat > "$OBJ_DIR/compile_one.sh" <<HELPER
#!/usr/bin/env bash
set -e
s="\$1"
b=\$(basename "\$s")
o="$OBJ_DIR/\${b%.m*}.o"
ARC=(-fobjc-arc)
[[ "\$s" == *PFMoveApplication.m ]] && ARC=(-fno-objc-arc)
lang="objective-c"
[[ "\$s" == *.mm ]] && lang="objective-c++"
xcrun clang -x "\$lang" -arch x86_64 -stdlib=libc++ "\${ARC[@]}" \\
  -mmacosx-version-min=10.12 -isysroot "$SDK_SYSROOT" -O2 -fvisibility=hidden \\
  -DNDEBUG -D_MAC -D_PRODUCT_ONLYOFFICE -D_X86_64_ONLY \\
  "-DURL_WEBAPPS_HELP=@\\"https://download.onlyoffice.com/install/desktop/editors/help/v$VER_CLEAN/apps\\"" \\
  "-DURL_APPCAST_UPDATES=@\\"\\"" \\
  "-DURL_APPCAST_DEV_CHANNEL=@\\"\\"" \\
  -Wno-deprecated-declarations -Wno-nullability-completeness \\
  -Wno-unguarded-availability -Wno-expansion-to-defined -Wno-shorten-64-to-32 \\
  -Wno-deprecated-copy -Wno-unused-variable -Wno-unused-function -Wno-comment \\
  -Wno-parentheses-equality -Wno-bool-conversion -Wno-constant-conversion \\
  -Wno-unused-but-set-variable -Wno-unused-private-field -Wno-inconsistent-missing-override \\
  -Wno-overloaded-virtual -Wno-availability -Wno-deprecated-builtins \\
  -Wno-implicit-const-int-float-conversion -Wno-deprecated-non-prototype \\
  @"$INC_FILE" \\
  -F "$FW" -F "$RES/converter" -F "$MACOS_DIR/Vendor/Sparkle" \\
  -c "\$s" -o "\$o"
HELPER
chmod +x "$OBJ_DIR/compile_one.sh"
tr '\n' '\0' < "$SRC_FILE" | xargs -0 -P 4 -n 1 "$OBJ_DIR/compile_one.sh"

xcrun clang++ -arch x86_64 -stdlib=libc++ -mmacosx-version-min=10.12 -isysroot "$SDK_SYSROOT" \
  -o "$CONT/MacOS/ONLYOFFICE" "$OBJ_DIR"/*.o \
  -F "$FW" -F "$RES/converter" -F "$MACOS_DIR/Vendor/Sparkle" \
  -framework Cocoa -framework Foundation -framework AppKit -framework WebKit \
  -framework QuartzCore -framework Carbon \
  -framework Security -weak_framework QuickLookUI \
  -framework Sparkle -framework ascdocumentscore -framework ooxmlsignature \
  -framework "Chromium Embedded Framework" \
  -rpath "@executable_path/../Frameworks" -rpath "@loader_path/../Frameworks" \
  -rpath "@executable_path/../Resources/converter" -rpath "@loader_path/../Resources/converter" \
  -headerpad_max_install_names

install_name_tool -change \
  "@executable_path/../Frameworks/Chromium Embedded Framework.framework/Chromium Embedded Framework" \
  "@rpath/Chromium Embedded Framework.framework/Chromium Embedded Framework" \
  "$CONT/MacOS/ONLYOFFICE" 2>/dev/null || true

echo "== Step 5: Update Info.plist & localized strings =="
PL="$CONT/Info.plist"
plutil -replace CFBundleName -string "ONLYOFFICE" "$PL"
plutil -replace CFBundleDisplayName -string "ONLYOFFICE" "$PL"
plutil -replace CFBundleShortVersionString -string "$VER_CLEAN" "$PL"
plutil -replace SUEnableAutomaticChecks -bool NO "$PL"
plutil -remove SUFeedURL "$PL" 2>/dev/null || true

for loc in zh-Hans-CN.lproj zh-Hant-TW.lproj; do
  for sf in "$MACOS_DIR/ONLYOFFICE/$loc"/*.strings "$MACOS_DIR/ONLYOFFICE/$loc"/*.stringsdict; do
    [ -f "$sf" ] || continue
    dst="$RES/$loc/$(basename "$sf")"
    cp -f "$sf" "$dst"
    plutil -convert binary1 "$dst"
  done
done

echo "== Step 6: Ad-hoc codesign & verify =="
ENT="$MACOS_DIR/ONLYOFFICE/Resources/ONLYOFFICE-x86_64/ONLYOFFICE.entitlements"
for h in editors_helper.app "editors_helper (GPU).app" "editors_helper (Renderer).app"; do
  codesign --force --options runtime --entitlements "$ENT" --sign - "$FW/$h"
done
codesign --force --deep --options runtime --sign - "$FW/Chromium Embedded Framework.framework"
codesign --force --options runtime --sign - "$FW/ascdocumentscore.framework/Versions/Current"
codesign --force --options runtime --sign - "$FW/hunspell.framework/Versions/Current"
codesign --force --deep --options runtime --sign - "$FW/Sparkle.framework"
codesign --force --options runtime --entitlements "$ENT" --sign - "$RES/converter/x2t"
codesign --force --options runtime --entitlements "$ENT" --sign - "$CONT/MacOS/ONLYOFFICE"
codesign --force --options runtime --entitlements "$ENT" --sign - "$APP"
codesign --verify --strict "$APP"

echo "== Step 7: Create DMG =="
DMG_SRC="$WORK_DIR/dmg_stage"
rm -rf "$DMG_SRC" "$OUT_DMG"
mkdir -p "$DMG_SRC"
cp -a "$APP" "$DMG_SRC/ONLYOFFICE.app"
ln -s /Applications "$DMG_SRC/Applications"
mkdir -p "$(dirname "$OUT_DMG")"
hdiutil create -volname "ONLYOFFICE" -srcfolder "$DMG_SRC" -ov -format UDZO "$OUT_DMG"
ls -lh "$OUT_DMG"
echo "DMG READY: $OUT_DMG"
