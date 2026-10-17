#!/usr/bin/env bash
# Desktop smoke (D9, D26): spawn-to-READY of the bundled sidecar, limit 20 s.
# Usage: desktop/scripts/smoke.sh [--allow-missing] [--sidecar PATH]
#   without cargo or a built sidecar: prints GUI_TOOLCHAIN_MISSING: <what> and exits 3;
#   with --allow-missing: prints SKIPPED: GUI_TOOLCHAIN (<what>) and exits 0 (a step of the owner, not a verified build).
#   with a sidecar executable (--sidecar, or sidecar/dist/gui-backend-<triple>/gui-backend): starts it, writes the
#   handshake line to its stdin, waits for `GUI_READY` and prints the elapsed time; exit 1 over 20 s or without READY.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(dirname "$(dirname "$HERE")")"
allow_missing=0
sidecar=""
limit=20
while [ $# -gt 0 ]; do
  case "$1" in
    --allow-missing) allow_missing=1 ;;
    --sidecar) shift; sidecar="${1:?--sidecar needs a path}" ;;
    -h|--help) sed -n '2,8p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "smoke.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

missing=()
command -v cargo >/dev/null 2>&1 || missing+=("cargo")
if [ -z "$sidecar" ]; then
  for candidate in "$MODULE_ROOT"/sidecar/dist/gui-backend-*/gui-backend; do
    if [ -x "$candidate" ]; then sidecar="$candidate"; break; fi
  done
fi
if [ -z "$sidecar" ] || [ ! -x "$sidecar" ]; then missing+=("built sidecar gui-backend"); fi

if [ "${#missing[@]}" -gt 0 ]; then
  what="$(IFS=,; echo "${missing[*]}")"
  echo "GUI_TOOLCHAIN_MISSING: $what" >&2
  if [ "$allow_missing" -eq 1 ]; then echo "SKIPPED: GUI_TOOLCHAIN ($what is missing; build and run on the owner machine)"; exit 0; fi
  exit 3
fi

secret="$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("="))')"
port="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
work="$(mktemp -d)"
trap 'kill "${pid:-0}" 2>/dev/null || true; rm -rf "$work"' EXIT
mkfifo "$work/in"
start="$(date +%s.%N)"
"$sidecar" <"$work/in" >"$work/out" 2>"$work/err" &
pid=$!
exec 3>"$work/in"
printf '{"v":1,"secret":"%s","port":%s,"shell_version":"smoke"}\n' "$secret" "$port" >&3
elapsed=""
while [ "$(python3 -c "import time;print(int(time.time()-$start))")" -lt "$limit" ]; do
  if grep -q '^GUI_READY ' "$work/out" 2>/dev/null; then
    elapsed="$(python3 -c "import time;print(round(time.time()-$start,2))")"
    break
  fi
  kill -0 "$pid" 2>/dev/null || break
  sleep 0.2
done
exec 3>&-
if [ -z "$elapsed" ]; then echo "smoke.sh: no GUI_READY within ${limit}s" >&2; exit 1; fi
echo "smoke: GUI_READY after ${elapsed}s (limit ${limit}s)"
