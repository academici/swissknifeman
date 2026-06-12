#!/usr/bin/env bash
# install.sh — устанавливает CLI swissknifeman.
#
# Создаёт симлинк <bin-dir>/swissknifeman -> <repo>/bin/swissknifeman и каталог
# состояния ~/.swissknifeman (projects.json — карта подключённых проектов,
# пополняется автоматически командами connect/vendor/update).
#
# Использование:
#   ./install.sh [--bin-dir DIR] [--force]
#
#   --bin-dir DIR   куда класть симлинк (по умолчанию ~/.local/bin)
#   --force         заменить чужой файл/симлинк без вопроса
#
# Дальше — из любого потребляющего проекта:
#   swissknifeman connect    # Claude Code (plugin marketplace)
#   swissknifeman vendor     # Cursor и другие агенты (копирование скиллов)
#   swissknifeman update     # обновить подключение текущего проекта
#
# Репозиторий переехал? Просто перезапустите ./install.sh из нового места.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$REPO_ROOT/bin/swissknifeman"
BIN_DIR="$HOME/.local/bin"
FORCE=false

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,18p'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: install.sh теперь устанавливает CLI swissknifeman." >&2
      echo "Вендоринг скиллов в проект: cd <project> && swissknifeman vendor [...]" >&2
      echo "Подключение Claude Code:    cd <project> && swissknifeman connect" >&2
      exit 1 ;;
  esac
done

[[ -x "$CLI" ]] || { echo "ERROR: $CLI не найден или не исполняем" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || \
  echo "WARN: python3 не найден — CLI потребует его при запуске" >&2

mkdir -p "$BIN_DIR" "$HOME/.swissknifeman"
[[ -f "$HOME/.swissknifeman/projects.json" ]] || \
  printf '{\n  "version": 1,\n  "projects": []\n}\n' > "$HOME/.swissknifeman/projects.json"

LINK="$BIN_DIR/swissknifeman"
if [[ -e "$LINK" || -L "$LINK" ]]; then
  current="$(readlink -f "$LINK" 2>/dev/null || true)"
  if [[ "$current" == */bin/swissknifeman ]]; then
    : # наш симлинк (возможно, из старого клона) — молча заменяем
  elif [[ "$FORCE" == true ]]; then
    : # явное разрешение
  elif [[ -t 0 ]]; then
    read -r -p "$LINK уже существует и не похож на swissknifeman. Заменить? [y/N] " answer
    [[ "$answer" =~ ^[yY] ]] || { echo "Отменено."; exit 1; }
  else
    echo "ERROR: $LINK уже существует — перезапустите с --force" >&2
    exit 1
  fi
fi
ln -sfn "$CLI" "$LINK"
echo "Установлено: $LINK -> $CLI"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo "WARN: $BIN_DIR не в PATH. Добавьте:"
    case "$(basename "${SHELL:-bash}")" in
      zsh)  echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc" ;;
      fish) echo "  fish_add_path $BIN_DIR" ;;
      *)    echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc" ;;
    esac ;;
esac

echo "Проверка: swissknifeman doctor"
