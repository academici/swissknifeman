#!/usr/bin/env bash
# install.sh installs the skiller CLI (formerly swissknifeman).
#
# It creates <bin-dir>/skiller -> <repo>/bin/skiller and the ~/.swissknifeman
# state directory. connect/vendor/update maintain projects.json.
#
# The umbrella install.sh owns the `swissknifeman` alias, so rerunning this
# installer never replaces the root router. Standalone installs expose `skiller` only.
#
# Usage:
#   ./install.sh [--bin-dir DIR] [--force] [--codex-plugin NAME] [--no-codex-plugins]
#
#   --bin-dir DIR   link destination (default: ~/.local/bin)
#   --force         replace a foreign file or link without prompting
#   --codex-plugin  install additional Codex plugin NAME (repeatable)
#   --no-codex-plugins  skip the base core and task Codex plugins
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
CODEX_PLUGIN_EXTRAS=()
CODEX_PLUGINS_ENABLED=true
CODEX_PLUGIN_EXPLICIT=false
MARKETPLACE="swissknifeman"

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,18p'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    --codex-plugin)
      CODEX_PLUGIN_EXTRAS+=("$2")
      CODEX_PLUGIN_EXPLICIT=true
      shift 2 ;;
    --no-codex-plugins) CODEX_PLUGINS_ENABLED=false; shift ;;
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

# Базовые `core` + `task` — машинный bootstrap Codex: после установки зонтика
# TASK-команды должны работать в любом проекте без ручного link/plugin add.
# Список берём из декларативной CORE-политики, не дублируем его в shell.
# Профильные плагины остаются явными: их глобальная установка здесь раздула бы
# все Codex-сессии независимо от проекта.
if [[ "$CODEX_PLUGINS_ENABLED" == false && "$CODEX_PLUGIN_EXPLICIT" == false ]]; then
  echo "Codex plugins: пропуск (--no-codex-plugins)"
elif ! command -v codex >/dev/null 2>&1; then
  if [[ "$CODEX_PLUGIN_EXPLICIT" == true ]]; then
    echo "ERROR: codex CLI not found — native install was not attempted" >&2
    exit 1
  fi
  echo "INFO: codex CLI не найден — базовые Codex-плагины не установлены"
else
  MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." && pwd)"
  [[ -f "$MONOREPO_ROOT/.agents/plugins/marketplace.json" ]] || {
    echo "ERROR: Codex marketplace not generated: $MONOREPO_ROOT/.agents/plugins/marketplace.json" >&2
    exit 1
  }

  policy_plugins=""
  if [[ "$CODEX_PLUGINS_ENABLED" == true ]]; then
    policy_plugins="$(
      PYTHONPATH="$REPO_ROOT/lib:$MONOREPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        python3 - <<'PY'
from skiller.config import CORE_PLUGIN, DEFAULT_COMMAND_PLUGINS

for plugin in (CORE_PLUGIN, *DEFAULT_COMMAND_PLUGINS):
    print(plugin)
PY
    )" || {
      echo "ERROR: не удалось прочитать базовые плагины из skiller.config" >&2
      exit 1
    }
  fi

  CODEX_PLUGINS=()
  declare -A seen_codex_plugins=()
  while IFS= read -r plugin; do
    [[ -n "$plugin" && -z "${seen_codex_plugins[$plugin]:-}" ]] || continue
    CODEX_PLUGINS+=("$plugin")
    seen_codex_plugins["$plugin"]=1
  done <<< "$policy_plugins"
  for plugin in "${CODEX_PLUGIN_EXTRAS[@]}"; do
    [[ -n "$plugin" && -z "${seen_codex_plugins[$plugin]:-}" ]] || continue
    CODEX_PLUGINS+=("$plugin")
    seen_codex_plugins["$plugin"]=1
  done

  codex plugin marketplace add "$MONOREPO_ROOT"
  for plugin in "${CODEX_PLUGINS[@]}"; do
    codex plugin add "$plugin@$MARKETPLACE"
  done
  echo "Codex plugins installed: ${CODEX_PLUGINS[*]}"
fi
