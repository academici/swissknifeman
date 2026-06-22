#!/usr/bin/env bash
# install.sh — зонтичный установщик монорепо.
# Ставит CLI пакетов (skiller, harness, maind), делегируя установку каждого его
# собственному install.sh (там пакетная пост-настройка). Это независимые CLI в
# PATH — единой консоли-обёртки пока нет (корневой управляющий слой — Фаза 2).
#
# Использование:
#   ./install.sh [--bin-dir DIR] [--force]
#   --bin-dir DIR   куда ставить симлинки (по умолчанию ~/.local/bin)
#   --force         перезаписывать чужие симлинки без вопроса
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force)   FORCE=true; shift ;;
    -h|--help) grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,11p'; exit 0 ;;
    *) echo "ERROR: неизвестный аргумент: $1" >&2; exit 1 ;;
  esac
done

mkdir -p "$BIN_DIR"

# Делегируем установку пакетных CLI их собственным install.sh (там пакетная
# пост-настройка: maind — npm/service опции; skiller — topology; harness — stateless).
fwd=(); $FORCE && fwd+=(--force); fwd+=(--bin-dir "$BIN_DIR")
echo "Установка CLI пакетов (bin-dir: $BIN_DIR):"
if [[ -x "$REPO_ROOT/packages/skiller/install.sh" ]]; then
  echo "— skiller:"
  "$REPO_ROOT/packages/skiller/install.sh" "${fwd[@]}" || echo "  (skiller install.sh завершился с ошибкой — проверьте вручную)" >&2
fi
if [[ -x "$REPO_ROOT/packages/harness/install.sh" ]]; then
  echo "— harness:"
  "$REPO_ROOT/packages/harness/install.sh" "${fwd[@]}" || echo "  (harness install.sh завершился с ошибкой — проверьте вручную)" >&2
fi
if [[ -x "$REPO_ROOT/packages/maind/install.sh" ]]; then
  echo "— maind:"
  "$REPO_ROOT/packages/maind/install.sh" "${fwd[@]}" || echo "  (maind install.sh завершился с ошибкой — проверьте вручную)" >&2
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "ВНИМАНИЕ: $BIN_DIR не в PATH — добавьте: export PATH=\"$BIN_DIR:\$PATH\"" >&2 ;;
esac

echo "Готово. CLI: skiller (алиас swissknifeman) · harness · maind"
