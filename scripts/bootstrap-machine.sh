#!/usr/bin/env bash
# bootstrap-machine.sh — идемпотентный machine-bootstrap зонтика (dotfiles-паттерн,
# RAG:✅ 2026-07-12 plans/2026.07.12-CONTEXT-ECONOMY/findings/P0-rag-bootstrap-memory-sync.md).
#
# Тонкий оркестратор: логика — в пакетах (install.sh / harness / maind), скрипт только
# вызывает их CLI в правильном порядке и проверяет rc (единый источник истины — рамка
# репо, дубль логики install/harness/maind здесь = дефект). Повторный запуск безопасен:
# каждая ступень использует merge-only/enable-идемпотентные механизмы пакетов.
#
# Ступени:
#   1) install.sh          — CLI пакетов (skiller/harness/maind/analyst) + симлинк swissknifeman
#   2) harness hooks --global        — файлы хуков в ~/.claude/hooks (один раз на машину)
#   3) harness permissions --global  — глобальный пресет permissions (merge-only)
#   4) MCP-пресеты          — у harness/maind сейчас НЕТ --global механизма (mcp — per-project
#                              .mcp.json через --target); ступень — информационный soft-skip,
#                              чтобы не изобретать свой механизм в обход единого источника истины
#   5) maind service install — демон памяти как systemd --user (мягкая деградация без systemd)
#   6) swissknifeman doctor  — финальная диагностика всех пакетов
#   7) манифест проектов     — clone отсутствующих + `swissknifeman setup <path>` (--projects FILE)
#
# Использование:
#   scripts/bootstrap-machine.sh [--dry-run] [--skip-projects] [--projects FILE] [--bin-dir DIR]
#   --dry-run        печатает план ступеней, ничего не выполняет и не пишет на диск
#   --skip-projects  пропустить ступень 7 (манифест проектов) целиком, даже если --projects задан
#   --projects FILE  per-user манифест проектов (JSON, схема — docs/machine-manifest.example.json):
#                     клонирует отсутствующие репо и вызывает `swissknifeman setup <path>` по
#                     списку; уже клонированные пути НЕ трогает (pull не делает — не портит чужое
#                     рабочее состояние), только повторяет onboard-проверку (идемпотентно)
#   --bin-dir DIR    куда класть симлинки CLI (по умолчанию ~/.local/bin, форвардится в install.sh)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$HOME/.local/bin"
DRY_RUN=false
SKIP_PROJECTS=false
PROJECTS_MANIFEST=""

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,28p'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    --skip-projects) SKIP_PROJECTS=true; shift ;;
    --projects) PROJECTS_MANIFEST="$2"; shift 2 ;;
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

HARNESS="$REPO_ROOT/packages/harness/bin/harness"
MAIND="$REPO_ROOT/packages/maind/bin/maind"
SWISSKNIFEMAN="$REPO_ROOT/bin/swissknifeman"

STATUS=0  # только «жёсткие» сбои (install.sh) поднимают итоговый rc; остальное — WARN+skip

step() { echo; echo "== $* =="; }

# 1) install.sh пакетов + симлинк swissknifeman — единственная ступень, чей сбой
#    считается жёстким (без CLI пакетов дальнейшие ступени бессмысленны).
step "1/7 install.sh (пакеты + симлинк swissknifeman)"
if $DRY_RUN; then
  echo "+ $REPO_ROOT/install.sh --bin-dir $BIN_DIR"
else
  if ! "$REPO_ROOT/install.sh" --bin-dir "$BIN_DIR"; then
    echo "ERROR: install.sh завершился с ошибкой — см. лог выше" >&2
    STATUS=1
  fi
fi

# 2) harness hooks --global — файлы хуков в ~/.claude/hooks (merge-only, один раз на машину)
step "2/7 harness hooks --global"
if [[ -x "$HARNESS" ]]; then
  hargs=(hooks --global); $DRY_RUN && hargs+=(--dry-run)
  "$HARNESS" "${hargs[@]}" || echo "WARN: harness hooks --global завершился с ошибкой — проверьте вручную" >&2
else
  echo "WARN: harness не найден ($HARNESS) — пропуск ступени (переустановите ./install.sh)" >&2
fi

# 3) harness permissions --global — глобальный пресет permissions (merge-only)
step "3/7 harness permissions --global"
if [[ -x "$HARNESS" ]]; then
  pargs=(permissions --global); $DRY_RUN && pargs+=(--dry-run)
  "$HARNESS" "${pargs[@]}" || echo "WARN: harness permissions --global завершился с ошибкой — проверьте вручную" >&2
else
  echo "WARN: harness не найден ($HARNESS) — пропуск ступени" >&2
fi

# 4) глобальные MCP-пресеты — у harness/maind сейчас нет отдельного --global для mcp
#    (harness mcp — только per-project --target .mcp.json); ничего не выполняем, чтобы не
#    изобретать свой механизм в обход единого источника истины пакетов.
step "4/7 MCP-пресеты"
echo "SKIP: глобального механизма нет — MCP раскатывается per-project (harness mcp --target / maind deploy)"

# 5) демон mAInd (systemd --user) — мягкая деградация, если systemd/user-сессия недоступны
step "5/7 демон mAInd (maind service install)"
if [[ -x "$MAIND" ]]; then
  if $DRY_RUN; then
    echo "+ $MAIND service install"
  else
    "$MAIND" service install || echo "WARN: maind service install недоступен (нет systemd/user-сессии?) — поднимите вручную: maind start --only memory" >&2
  fi
else
  echo "WARN: maind не найден ($MAIND) — пропуск ступени" >&2
fi

# 6) финальная диагностика
step "6/7 swissknifeman doctor"
if $DRY_RUN; then
  echo "+ $SWISSKNIFEMAN doctor"
else
  if [[ -x "$SWISSKNIFEMAN" ]]; then
    "$SWISSKNIFEMAN" doctor || echo "WARN: doctor вернул предупреждения/ошибки — см. вывод выше" >&2
  else
    echo "WARN: $SWISSKNIFEMAN не найден — install.sh не поставил симлинк" >&2
  fi
fi

# 7) манифест проектов — per-user список зависимых репо (docs/machine-manifest.example.json):
#    клонирует отсутствующие, для уже клонированных pull НЕ делает (не трогаем чужое рабочее
#    состояние) — только повторяет `swissknifeman setup <path>` (onboard-проверка, идемпотентно).
step_projects() {
  local manifest="$1"
  if [[ ! -f "$manifest" ]]; then
    echo "ERROR: манифест не найден: $manifest" >&2
    STATUS=1
    return
  fi
  local rows
  if ! rows="$(python3 - "$manifest" <<'PY'
import json, sys

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
except (OSError, ValueError) as exc:
    print(f"невалидный JSON манифеста: {exc}", file=sys.stderr)
    sys.exit(1)

ok = True
for p in data.get("projects", []):
    repo = (p.get("repo") or "").strip()
    dest = (p.get("path") or "").strip()
    if not repo or not dest:
        print(f"запись без обязательных полей repo/path: {p}", file=sys.stderr)
        ok = False
        continue
    print(f"{repo}\x1f{dest}")
sys.exit(0 if ok else 1)
PY
  )"; then
    echo "ERROR: манифест невалиден: $manifest (см. вывод выше)" >&2
    STATUS=1
    return
  fi
  while IFS=$'\x1f' read -r repo dest; do
    [[ -z "$repo" ]] && continue
    dest_expanded="${dest/#\~/$HOME}"
    if $DRY_RUN; then
      if [[ -d "$dest_expanded/.git" ]]; then
        echo "+ (уже клонирован, пропуск clone) $SWISSKNIFEMAN setup $dest_expanded"
      else
        echo "+ git clone $repo $dest_expanded"
        echo "+ $SWISSKNIFEMAN setup $dest_expanded"
      fi
      continue
    fi
    if [[ -d "$dest_expanded/.git" ]]; then
      echo "SKIP clone (уже клонирован, pull не делаем): $dest_expanded"
    else
      mkdir -p "$(dirname "$dest_expanded")"
      if git clone "$repo" "$dest_expanded"; then
        echo "OK clone: $repo -> $dest_expanded"
      else
        echo "WARN: git clone не удался: $repo -> $dest_expanded — пропуск onboard для этого проекта" >&2
        continue
      fi
    fi
    if [[ -x "$SWISSKNIFEMAN" ]]; then
      "$SWISSKNIFEMAN" setup "$dest_expanded" || echo "WARN: swissknifeman setup завершился с ошибкой для $dest_expanded — проверьте вручную" >&2
    else
      echo "WARN: $SWISSKNIFEMAN не найден — пропуск onboard для $dest_expanded" >&2
    fi
  done <<< "$rows"
}

step "7/7 манифест проектов (--projects)"
if $SKIP_PROJECTS; then
  echo "NOTE: --skip-projects принят — ступень пропущена (манифест: ${PROJECTS_MANIFEST:-нет})"
elif [[ -z "$PROJECTS_MANIFEST" ]]; then
  echo "NOTE: --projects не задан — ступень пропущена (пример манифеста: docs/machine-manifest.example.json)"
else
  step_projects "$PROJECTS_MANIFEST"
fi

echo
if (( STATUS == 0 )); then
  echo "bootstrap-machine: готово (см. WARN выше по опциональным ступеням)."
else
  echo "bootstrap-machine: завершено с ошибками на обязательных ступенях (см. ERROR выше)." >&2
fi
exit "$STATUS"
