#!/usr/bin/env bash
# install.sh — устанавливает CLI maind.
#
# Создаёт симлинк <bin-dir>/maind -> <repo>/bin/maind и каталог состояния ~/.maind
# (projects.json/agents.json — реестры узла, пополняются командами CLI).
#
# Использование:
#   ./install.sh [--bin-dir DIR] [--force] [--with-memory] [--with-service]
#
#   --bin-dir DIR   куда класть симлинк (по умолчанию ~/.local/bin)
#   --force         заменить чужой файл/симлинк без вопроса
#   --with-memory   npm install в корне maind (демон памяти @agentmemory/agentmemory)
#   --with-service  зарегистрировать демон памяти как systemd --user сервис
#                   (maind service install — автозапуск + авто-рестарт)
#
# Полный bootstrap: ./install.sh --with-memory --with-service
# Порты демона настраиваются через .env (см. .env.example), чтобы не конфликтовать
# с другим узлом. graphify (граф кода) — опционален, ставится отдельно.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$REPO_ROOT/bin/maind"
BIN_DIR="$HOME/.local/bin"
FORCE=false
WITH_MEMORY=false
WITH_SERVICE=false

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,18p'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    --with-memory) WITH_MEMORY=true; shift ;;
    --with-service) WITH_SERVICE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ -x "$CLI" ]] || { echo "ERROR: $CLI не найден или не исполняем" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || \
  echo "WARN: python3 не найден — CLI потребует его при запуске" >&2

mkdir -p "$BIN_DIR" "$HOME/.maind"
[[ -f "$HOME/.maind/projects.json" ]] || \
  printf '{\n  "version": 1,\n  "projects": []\n}\n' > "$HOME/.maind/projects.json"
[[ -f "$HOME/.maind/agents.json" ]] || \
  printf '{\n  "version": 1,\n  "agents": []\n}\n' > "$HOME/.maind/agents.json"

LINK="$BIN_DIR/maind"
if [[ -e "$LINK" || -L "$LINK" ]]; then
  current="$(readlink -f "$LINK" 2>/dev/null || true)"
  if [[ "$current" == */bin/maind ]]; then
    : # наш симлинк (возможно, из старого клона) — молча заменяем
  elif [[ "$FORCE" == true ]]; then
    : # явное разрешение
  elif [[ -t 0 ]]; then
    read -r -p "$LINK уже существует и не похож на maind. Заменить? [y/N] " answer
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

# ── опциональный bootstrap демона памяти ─────────────────────────────────────
if [[ "$WITH_MEMORY" == true ]]; then
  if command -v npm >/dev/null 2>&1; then
    echo "Установка демона памяти (npm install в $REPO_ROOT)..."
    ( cd "$REPO_ROOT" && npm install ) || echo "WARN: npm install завершилась с ошибкой"
  else
    echo "WARN: npm не найден — пропускаю установку демона памяти (нужен Node.js)"
  fi
fi

if [[ "$WITH_SERVICE" == true ]]; then
  echo "Регистрация systemd --user сервиса демона памяти..."
  "$CLI" service install || echo "WARN: maind service install не удался (см. вывод выше)"
fi

# ── граф кода (опционально, движок Serena через uvx) ─────────────────────────
command -v uvx >/dev/null 2>&1 || \
  echo "INFO: uvx не найден в PATH — для графа кода (Serena) поставьте uv: https://docs.astral.sh/uv/"

echo ""
echo "Готово. Дальше:"
[[ "$WITH_SERVICE" == true ]] || echo "  maind start --only memory       # поднять память (или: maind service install)"
echo "  maind onboard <path|id>         # подключить проект к экосистеме"
echo "  maind health --cwd              # проверить связь из каталога проекта"
echo "  maind doctor                    # диагностика окружения"
