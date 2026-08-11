#!/usr/bin/env bash
# docs-sync — собрать зонтичный сайт из per-package доков.
# Источник истины — packages/<pkg>/docs (каждый пакет владеет своими доками);
# сюда копируются сборочные копии docs/<pkg>/ (gitignored). VitePress видит их как
# реальные файлы в srcDir → корректный роутинг и относительные ссылки (симлинки
# VitePress резолвит в реальные пути вне srcDir — ломает маршруты, поэтому копия).
# Запускается перед `vitepress build|dev` (см. packages/skiller/package.json).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="write"
if [ "${1:-}" = "--check" ]; then
  MODE="check"
elif [ "$#" -gt 0 ]; then
  echo "usage: $0 [--check]" >&2
  exit 2
fi

sync_pkg() {
  local src="$ROOT/packages/$1/docs" dst="$ROOT/docs/$1"
  [ -d "$src" ] || { echo "  нет $src — пропуск"; return; }
  if [ "$MODE" = "check" ]; then
    local tmp
    tmp="$(mktemp -d)"
    cp -r "$src/." "$tmp/"
    rm -rf "$tmp/.vitepress"
    if ! diff -qr "$tmp" "$dst" >/dev/null; then
      echo "  docs/$1 устарел; запустите bash scripts/docs-sync.sh" >&2
      rm -rf "$tmp"
      return 1
    fi
    rm -rf "$tmp"
    echo "  docs/$1 свеж"
    return
  fi
  rm -rf "$dst"
  mkdir -p "$dst"
  cp -r "$src/." "$dst/"
  rm -rf "$dst/.vitepress"   # вложенный per-package vitepress в агрегате не нужен
  echo "  docs/$1 ← packages/$1/docs"
}
echo "docs-sync:"
sync_pkg skiller
sync_pkg harness
sync_pkg maind   # внутренние ссылки maind-доков относительные → работают и standalone, и в агрегате
sync_pkg analyst # continuous learning; внутренние ссылки относительные (standalone + агрегат)
sync_pkg task
