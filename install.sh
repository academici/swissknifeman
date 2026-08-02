#!/usr/bin/env bash
# install.sh — зонтичный установщик монорепо.
# Ставит CLI пакетов (skiller, harness, maind), делегируя установку каждого его
# собственному install.sh (там пакетная пост-настройка), плюс корневой
# управляющий слой `swissknifeman` (router + setup-фасад над тремя пакетами).
#
# Использование:
#   ./install.sh [--bin-dir DIR] [--force] [--no-codex-plugins]
#   --bin-dir DIR   куда ставить симлинки (по умолчанию ~/.local/bin)
#   --force         перезаписывать чужие симлинки без вопроса
#   --no-codex-plugins  не устанавливать базовые Codex-плагины core + task
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
FORCE=false
NO_CODEX_PLUGINS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force)   FORCE=true; shift ;;
    --no-codex-plugins) NO_CODEX_PLUGINS=true; shift ;;
    -h|--help) grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,11p'; exit 0 ;;
    *) echo "ERROR: неизвестный аргумент: $1" >&2; exit 1 ;;
  esac
done

mkdir -p "$BIN_DIR"

# Делегируем установку пакетных CLI их собственным install.sh (там пакетная
# пост-настройка: maind — npm/service опции; skiller — topology; harness — stateless).
# `task` в списке НЕТ сознательно: у него нет bin/CLI/install.sh — это plugin-only
# пакет (только slash-команды), доставляется через marketplace/vendor skiller-канал.
fwd=(); $FORCE && fwd+=(--force); fwd+=(--bin-dir "$BIN_DIR")
echo "Установка CLI пакетов (bin-dir: $BIN_DIR):"
failed=()  # пакеты, чей install.sh упал — для итогового статуса (иначе «Готово» врёт)
for pkg in skiller harness maind analyst; do
  inst="$REPO_ROOT/packages/$pkg/install.sh"
  [[ -x "$inst" ]] || continue
  echo "— $pkg:"
  pkg_fwd=("${fwd[@]}")
  if [[ "$pkg" == skiller && "$NO_CODEX_PLUGINS" == true ]]; then
    pkg_fwd+=(--no-codex-plugins)
  fi
  "$inst" "${pkg_fwd[@]}" || { echo "  ($pkg install.sh завершился с ошибкой — проверьте вручную)" >&2; failed+=("$pkg"); }
done

# Корневой управляющий слой: симлинк `swissknifeman` → bin/swissknifeman (router).
# Ставится ПОСЛЕ пакетов — раньше алиас `swissknifeman` ставил skiller; теперь им
# владеет зонтик. Молча заменяем наш прежний симлинк (на skiller/router); чужой —
# только с --force/подтверждением.
ROUTER="$REPO_ROOT/bin/swissknifeman"
LINK="$BIN_DIR/swissknifeman"
if [[ -x "$ROUTER" ]]; then
  if [[ -e "$LINK" || -L "$LINK" ]]; then
    current="$(readlink -f "$LINK" 2>/dev/null || true)"
    if [[ "$current" == */bin/swissknifeman || "$current" == */bin/skiller ]]; then
      : # наш прежний симлинк (router или старый алиас→skiller) — молча заменяем
    elif [[ "$FORCE" == true ]]; then :;
    elif [[ -t 0 ]]; then
      read -r -p "$LINK уже существует и не похож на наш. Заменить? [y/N] " a
      [[ "$a" =~ ^[yY] ]] || { echo "Пропуск swissknifeman."; ROUTER=""; }
    else
      echo "ВНИМАНИЕ: $LINK существует — пропуск (перезапустите с --force)" >&2; ROUTER=""
    fi
  fi
  [[ -n "$ROUTER" ]] && { ln -sfn "$ROUTER" "$LINK"; echo "— swissknifeman: $LINK -> $ROUTER"; }
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "ВНИМАНИЕ: $BIN_DIR не в PATH — добавьте: export PATH=\"$BIN_DIR:\$PATH\"" >&2 ;;
esac

if (( ${#failed[@]} )); then
  echo "ОШИБКА: не установлены пакеты: ${failed[*]} — установка неполна, см. лог выше." >&2
  exit 1
fi
echo "Готово. CLI: swissknifeman (router) · skiller · harness · maind · analyst"
