#!/usr/bin/env bash
# install.sh — устанавливает CLI skiller (бывш. swissknifeman).
#
# Создаёт симлинк <bin-dir>/skiller -> <repo>/bin/skiller и каталог состояния
# ~/.swissknifeman (projects.json — карта подключённых проектов, пополняется
# автоматически командами connect/vendor/update).
#
# Алиас `swissknifeman` ставит ЗОНТИЧНЫЙ install.sh (корневой router-слой), а не
# этот пакет — чтобы re-run skiller install не затирал router. При standalone-
# установке только skiller алиаса `swissknifeman` не будет (используйте `skiller`).
#
# Использование:
#   ./install.sh [--bin-dir DIR] [--force] [--codex-plugin NAME]
#
#   --bin-dir DIR   куда класть симлинк (по умолчанию ~/.local/bin)
#   --force         заменить чужой файл/симлинк без вопроса
#   --codex-plugin  явно добавить этот marketplace в Codex и установить NAME
#
# Дальше — из любого потребляющего проекта:
#   skiller connect    # Claude Code (plugin marketplace)
#   skiller vendor     # Cursor и другие агенты (копирование скиллов)
#   skiller update     # обновить подключение текущего проекта
#   skiller topology   # карта локальной среды (init|show) — предлагается при установке
#
# Репозиторий переехал? Просто перезапустите ./install.sh из нового места.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$REPO_ROOT/bin/skiller"
BIN_DIR="$HOME/.local/bin"
FORCE=false
CODEX_PLUGIN=""
MARKETPLACE="swissknifeman"

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,18p'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    --codex-plugin) CODEX_PLUGIN="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: install.sh теперь устанавливает CLI skiller." >&2
      echo "Вендоринг скиллов в проект: cd <project> && skiller vendor [...]" >&2
      echo "Подключение Claude Code:    cd <project> && skiller connect" >&2
      exit 1 ;;
  esac
done

[[ -x "$CLI" ]] || { echo "ERROR: $CLI не найден или не исполняем" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || \
  echo "WARN: python3 не найден — CLI потребует его при запуске" >&2

mkdir -p "$BIN_DIR" "$HOME/.swissknifeman"
[[ -f "$HOME/.swissknifeman/projects.json" ]] || \
  printf '{\n  "version": 1,\n  "projects": []\n}\n' > "$HOME/.swissknifeman/projects.json"

# Ставим симлинк, молча заменяя СВОЙ (старый клон или прежнее имя swissknifeman);
# чужой файл не трогаем без --force/подтверждения.
install_link() {  # $1 — имя в BIN_DIR
  local link="$BIN_DIR/$1"
  if [[ -e "$link" || -L "$link" ]]; then
    local current; current="$(readlink -f "$link" 2>/dev/null || true)"
    if [[ "$current" == */bin/skiller || "$current" == */bin/swissknifeman ]]; then
      : # наш симлинк (возможно, из старого клона/имени) — молча заменяем
    elif [[ "$FORCE" == true ]]; then
      : # явное разрешение
    elif [[ -t 0 ]]; then
      read -r -p "$link уже существует и не похож на skiller. Заменить? [y/N] " answer
      [[ "$answer" =~ ^[yY] ]] || { echo "Отменено."; exit 1; }
    else
      echo "ERROR: $link уже существует — перезапустите с --force" >&2
      exit 1
    fi
  fi
  ln -sfn "$CLI" "$link"
  echo "Установлено: $link -> $CLI"
}

install_link skiller          # основной CLI (алиас swissknifeman — зонтичный install.sh)

# Карта локальной среды (~/.swissknifeman/topology.json) — машинно-специфична
# (пути к Brain-волту, swissknifeman и базе проектов), поэтому создаётся
# интерактивно, а не сидится молча. Предлагаем настроить сразу при наличии TTY.
if [[ ! -f "$HOME/.swissknifeman/topology.json" && -t 0 ]]; then
  read -r -p "Настроить карту локальной среды (skiller topology init)? [y/N] " ans
  [[ "$ans" =~ ^[yY] ]] && "$CLI" topology init || true
fi

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

echo "Проверка: skiller doctor"

# Native Codex state is outside a project distribution transaction.  It is only
# touched by this explicit install flag; normal install/update/doctor never call
# `codex plugin`.  The marketplace root is the monorepo root, where P3.3 emits
# `.agents/plugins/marketplace.json`.
if [[ -n "$CODEX_PLUGIN" ]]; then
  MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." && pwd)"
  [[ -f "$MONOREPO_ROOT/.agents/plugins/marketplace.json" ]] || {
    echo "ERROR: Codex marketplace not generated: $MONOREPO_ROOT/.agents/plugins/marketplace.json" >&2
    exit 1
  }
  command -v codex >/dev/null 2>&1 || {
    echo "ERROR: codex CLI not found — native install was not attempted" >&2
    exit 1
  }
  codex plugin marketplace add "$MONOREPO_ROOT"
  codex plugin add "$CODEX_PLUGIN@$MARKETPLACE"
  echo "Codex plugin installed explicitly: $CODEX_PLUGIN@$MARKETPLACE"
fi
