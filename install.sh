#!/usr/bin/env bash
# install.sh — зонтичный установщик монорепо academici.
# Ставит единую консоль `academici` + под-команды пакетов (maind, swissknifeman),
# делегируя установку каждого пакетного CLI его собственному install.sh.
#
# Использование:
#   ./install.sh [--bin-dir DIR] [--force]
#   --bin-dir DIR   куда ставить симлинки (по умолчанию ~/.local/bin)
#   --force         перезаписывать чужие симлинки без вопроса
#
# Под-бинарники остаются самостоятельными: academici их не заменяет, а сводит
# в одну точку входа (academici maind ... / academici skm ...).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force)   FORCE=true; shift ;;
    -h|--help) grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,13p'; exit 0 ;;
    *) echo "ERROR: неизвестный аргумент: $1" >&2; exit 1 ;;
  esac
done

mkdir -p "$BIN_DIR"

link_one() {
  local target="$1" name="$2"
  local dest="$BIN_DIR/$name"
  if [[ -L "$dest" || -e "$dest" ]]; then
    local current; current="$(readlink -f "$dest" 2>/dev/null || true)"
    if [[ "$current" == "$target" ]]; then
      echo "  = $name → уже на месте"; return
    fi
    if ! $FORCE; then
      echo "  ! $name существует ($dest) — пропуск (--force для перезаписи)" >&2; return
    fi
  fi
  ln -sfn "$target" "$dest"
  echo "  + $name → $target"
}

echo "Установка academici (bin-dir: $BIN_DIR):"
link_one "$REPO_ROOT/bin/academici" academici

# Делегируем установку пакетных CLI их собственным install.sh (там пакетная
# пост-настройка: maind — npm/service опции; swissknifeman — topology).
echo "Под-пакеты (делегирование их install.sh):"
fwd=(); $FORCE && fwd+=(--force); fwd+=(--bin-dir "$BIN_DIR")
if [[ -x "$REPO_ROOT/packages/swissknifeman/install.sh" ]]; then
  echo "— swissknifeman:"
  "$REPO_ROOT/packages/swissknifeman/install.sh" "${fwd[@]}" || echo "  (swissknifeman install.sh завершился с ошибкой — проверьте вручную)" >&2
fi
if [[ -x "$REPO_ROOT/packages/maind/install.sh" ]]; then
  echo "— maind:"
  "$REPO_ROOT/packages/maind/install.sh" "${fwd[@]}" || echo "  (maind install.sh завершился с ошибкой — проверьте вручную)" >&2
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "ВНИМАНИЕ: $BIN_DIR не в PATH — добавьте: export PATH=\"$BIN_DIR:\$PATH\"" >&2 ;;
esac

echo "Готово. Точка входа: academici help"
