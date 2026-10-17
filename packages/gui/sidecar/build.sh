#!/usr/bin/env bash
# Builds the desktop sidecar `gui-backend` (PyInstaller onedir, decisions D9, D26, D28).
# Usage: sidecar/build.sh [--allow-missing] [--out DIR]
#   without PyInstaller: prints GUI_TOOLCHAIN_MISSING: pyinstaller and exits 3;
#   with --allow-missing: prints SKIPPED: GUI_TOOLCHAIN and exits 0 (the build is a step of the owner).
# Result: DIR/gui-backend-<target-triple>/ (default DIR: sidecar/dist) with the executable gui-backend inside.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(dirname "$HERE")"
allow_missing=0
out="$HERE/dist"
while [ $# -gt 0 ]; do
  case "$1" in
    --allow-missing) allow_missing=1 ;;
    --out) shift; out="${1:?--out needs a folder}" ;;
    -h|--help) sed -n '2,7p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "build.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

if ! command -v python3 >/dev/null 2>&1 || ! python3 -m PyInstaller --version >/dev/null 2>&1; then
  echo "GUI_TOOLCHAIN_MISSING: pyinstaller" >&2
  if [ "$allow_missing" -eq 1 ]; then echo "SKIPPED: GUI_TOOLCHAIN (pyinstaller is not installed; build on the owner machine)"; exit 0; fi
  exit 3
fi

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) triple="x86_64-unknown-linux-gnu" ;;
  Linux-aarch64|Linux-arm64) triple="aarch64-unknown-linux-gnu" ;;
  Darwin-x86_64) triple="x86_64-apple-darwin" ;;
  Darwin-arm64|Darwin-aarch64) triple="aarch64-apple-darwin" ;;
  *) echo "build.sh: unsupported platform $(uname -s)-$(uname -m)" >&2; exit 2 ;;
esac

# The locked third-party packages are bundled from their install folder.
"$MODULE_ROOT/bin/gui" deps ensure >/dev/null
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python3 -m PyInstaller --noconfirm --clean --distpath "$work/dist" --workpath "$work/build" "$HERE/gui-backend.spec"
mkdir -p "$out"
rm -rf "$out/gui-backend-$triple"
mv "$work/dist/gui-backend" "$out/gui-backend-$triple"
echo "built: $out/gui-backend-$triple/gui-backend"
