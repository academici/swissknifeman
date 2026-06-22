#!/usr/bin/env bash
# docs-sync — собрать зонтичный сайт из per-package доков.
# Источник истины — packages/<pkg>/docs (каждый пакет владеет своими доками);
# сюда копируются сборочные копии docs/<pkg>/ (gitignored). VitePress видит их как
# реальные файлы в srcDir → корректный роутинг и относительные ссылки (симлинки
# VitePress резолвит в реальные пути вне srcDir — ломает маршруты, поэтому копия).
# Запускается перед `vitepress build|dev` (см. packages/skiller/package.json).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sync_pkg() {
  local src="$ROOT/packages/$1/docs" dst="$ROOT/docs/$1"
  [ -d "$src" ] || { echo "  нет $src — пропуск"; return; }
  rm -rf "$dst"; mkdir -p "$dst"
  cp -r "$src/." "$dst/"
  rm -rf "$dst/.vitepress"   # вложенный per-package vitepress в агрегате не нужен
  echo "  docs/$1 ← packages/$1/docs"
}
echo "docs-sync:"
sync_pkg skiller
sync_pkg harness
sync_pkg maind   # внутренние ссылки maind-доков относительные → работают и standalone, и в агрегате
