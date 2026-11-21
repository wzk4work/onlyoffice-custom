#!/usr/bin/env bash
# Build web-apps (grunt) + loginpage (vite single-file bundles).
# Usage: build_web.sh <work_dir>
set -euo pipefail
WORK_DIR="$(cd "${1:?usage: build_web.sh <work_dir>}" && pwd)"

echo "== Build web-apps =="
(
  cd "$WORK_DIR/web-apps/translation"
  python merge_and_check.py
)
(
  cd "$WORK_DIR/web-apps/build"
  # dev deps (grunt-mocha -> phantomjs-prebuilt) have no linux/arm64 binary and
  # are only used by test tasks we never run — install prod deps only.
  npm install --omit=dev --no-audit --no-fund
  npx grunt --force
)

echo "== Build loginpage (addondialog + noconnect + start page) =="
for sub in addondialog noconnect .; do
  (
    cd "$WORK_DIR/desktop-apps/common/loginpage/$sub"
    npm install --no-audit --no-fund
    npm run build
  )
done

echo "WEB BUILD OK"
