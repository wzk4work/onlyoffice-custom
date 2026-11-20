#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK_DIR="${1:-$REPO_ROOT/work}"

for sub in desktop-sdk desktop-apps web-apps; do
  echo "== Applying $sub.patch =="
  git -C "$WORK_DIR/$sub" apply --3way --whitespace=nowarn "$REPO_ROOT/patches/$sub.patch"
done
echo "All patches applied successfully."
