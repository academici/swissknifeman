#!/usr/bin/env bash
# validate.sh — структурные проверки пакета harness (CI + локально).
# Проверяет: компиляцию Python, синтаксис bash (CLI/install/scripts/хуки),
# валидность JSON (плагин + пресеты settings/mcp), наличие ключевых файлов,
# frontmatter slash-команд, и гоняет тесты (scripts/test.sh).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
fail=0
err() { echo "  FAIL: $*" >&2; fail=1; }

echo "[1/10] python compile"
python3 -m compileall -q lib tests || err "py_compile"

echo "[2/10] вендоринг _usage.py (SCHEMA=2 run-report)"
MONOREPO_ROOT_USAGE="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
USAGE_DST="configs/claude-code/hooks/run-report/_usage.py"
if [[ -n "$MONOREPO_ROOT_USAGE" && -f "$MONOREPO_ROOT_USAGE/core/usage.py" ]]; then
  cmp -s "$MONOREPO_ROOT_USAGE/core/usage.py" "$USAGE_DST" \
    || err "вендоренный _usage.py разошёлся с core/usage.py — запусти scripts/sync-usage.sh"
else
  [[ -f "$USAGE_DST" ]] || err "нет $USAGE_DST (standalone-раскладка без core/ — ожидается вендоренная копия)"
fi

echo "[3/10] bash syntax"
for f in bin/harness install.sh scripts/*.sh; do
  bash -n "$f" || err "bash -n $f"
done
# хук-скрипты конфигов (auto-approve / notify / memory) — синтакс-проверка
while IFS= read -r -d '' sh; do
  bash -n "$sh" || err "bash -n $sh"
done < <(find configs/claude-code -name '*.sh' -print0)
# Python-хуки конфигов (agent-router — первый Python-хук репо) — компиляция
while IFS= read -r -d '' py; do
  python3 -m py_compile "$py" || err "py_compile $py"
done < <(find configs/claude-code -name '*.py' -print0)

echo "[4/10] JSON (плагин + пресеты)"
python3 - <<'PY' || err "битый JSON"
import glob, json, sys
bad = []
for f in [".claude-plugin/plugin.json"] + sorted(glob.glob("configs/claude-code/**/*.json", recursive=True)):
    try:
        json.load(open(f, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        bad.append(f"{f}: {e}")
for b in bad:
    print("  FAIL:", b, file=sys.stderr)
sys.exit(1 if bad else 0)
PY

echo "[5/10] обязательные файлы"
for f in bin/harness lib/harness/__init__.py lib/harness/cli.py \
         scripts/apply-permissions.sh configs/claude-code/settings.base.json \
         .claude-plugin/plugin.json commands/harness.md \
         README.md LICENSE CLAUDE.md; do
  [[ -e "$f" ]] || err "нет файла: $f"
done

echo "[6/10] slash-команды (frontmatter)"
python3 - <<'PY' || err "битый frontmatter в commands/*.md"
import glob, sys
bad = []
for f in sorted(glob.glob("commands/*.md")):
    lines = open(f, encoding="utf-8").read().replace("\r\n", "\n").splitlines()
    if not lines or lines[0].strip() != "---":
        bad.append(f"{f}: нет открывающего ---"); continue
    fm, closed = {}, False
    for ln in lines[1:]:
        if ln.strip() == "---":
            closed = True; break
        if ":" in ln:
            k, v = ln.split(":", 1); fm[k.strip()] = v.strip()
    if not closed:
        bad.append(f"{f}: frontmatter не закрыт"); continue
    if not fm.get("description"):
        bad.append(f"{f}: пустой/нет description")
for b in bad:
    print("  FAIL:", b, file=sys.stderr)
sys.exit(1 if bad else 0)
PY

echo "[7/10] импорт пакета + тесты"
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
[ -d "$MONOREPO_ROOT/core" ] || MONOREPO_ROOT=""
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}" python3 -c "import harness.cli" \
  || err "lib/harness не импортируется"
# целостность agent-packs: все files[].src на месте, нет остаточных {{...}} при
# рендере с дефолтами, у каждого {{TOKEN}} есть interview-id (do_doctor).
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}" python3 -c "
import sys
from harness.agentpacks import do_doctor
from harness.common import Env
sys.exit(do_doctor(Env('$REPO_ROOT', 'validate')))" || err "agent-packs integrity"
scripts/test.sh || err "тесты"

echo "[8/11] generated provider instructions reference"
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}" \
  python3 scripts/generate-provider-instructions.py --check \
  || err "generated provider instructions reference"

echo "[9/11] реестр ролей ревью"
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}" python3 -m harness.reviewroles --check \
  || err "реестр ролей ревью (role-bindings.json)"

# гейт дрейфа инструкций (2026.07.29-HARNESS-AGNOSTIC P1.5): двенадцать управляемых
# проекций CLAUDE.md/AGENTS.md обязаны оставаться `clean`. Красный шаг = незакрытая
# работа канона (фрагменты/каталог), а не повод сузить проверку.
echo "[10/11] дрейф инструкций (12 проекций)"
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}" python3 -m harness.instructions --check \
  || err "дрейф инструкций (harness instructions check)"

# гейт политики исполнения (2026.07.29-HARNESS-AGNOSTIC P4.3, D48): валидатор читает
# JSON через `core.safe_load_json` — в standalone-раскладке (нет монорепо-корня с
# core/) шаг деградирует в пропуск с предупреждением, по образцу соседних секций.
echo "[11/11] политика исполнения (execution-policy)"
if [[ -n "$MONOREPO_ROOT" ]]; then
  PYTHONPATH="$REPO_ROOT/lib:$MONOREPO_ROOT" python3 -m harness.execpolicy --check \
    || err "политика исполнения (execution-policy)"
else
  echo "  политика исполнения: core/ не найден (standalone-раскладка) — гейт пропущен"
fi

echo ""
if [[ "$fail" -eq 0 ]]; then echo "validate: OK"; else echo "validate: ПРОВАЛ" >&2; exit 1; fi
