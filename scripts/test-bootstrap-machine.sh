#!/usr/bin/env bash
# test-bootstrap-machine.sh — smoke-тесты scripts/bootstrap-machine.sh + роута
# `swissknifeman setup --machine`. Не поднимает демоны/не трогает реальный ~/.claude —
# всё выполняется с изолированным HOME=$(mktemp -d) (Code Guidance P7.1: клин-HOME смоук).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/bootstrap-machine.sh"
SWISSKNIFEMAN="$REPO_ROOT/bin/swissknifeman"

fail=0
ok() { echo "ok - $1"; }
bad() { echo "NOT OK - $1"; fail=1; }

# 1) bash -n
bash -n "$SCRIPT" && ok "bash -n scripts/bootstrap-machine.sh" || bad "bash -n scripts/bootstrap-machine.sh"

# 2) --help выходит 0 и печатает использование
if out="$("$SCRIPT" --help 2>&1)"; then
  [[ "$out" == *"bootstrap-machine.sh"* ]] && ok "--help печатает usage" || bad "--help: нет упоминания скрипта в выводе"
else
  bad "--help вернул ненулевой rc"
fi

# 3) неизвестный флаг — ошибка (rc != 0)
if "$SCRIPT" --bogus-flag >/tmp/bogus.out 2>&1; then
  bad "неизвестный флаг --bogus-flag должен завершаться ошибкой"
else
  ok "неизвестный флаг --bogus-flag завершается ошибкой"
fi

# 4) --dry-run в изолированном HOME не пишет НИЧЕГО на диск (ни файлов, ни каталогов).
#    Post-review фикс: apply-permissions.sh делал `mkdir -p .../auto-approve` ДО
#    проверки DRY_RUN — пофикшено (mkdir перенесён внутрь `if [[ DRY_RUN -eq 0 ]]`),
#    поэтому здесь считаем ЛЮБУЮ запись (-mindepth 1, без -type f).
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT
before_all="$(find "$TMP_HOME" -mindepth 1 2>/dev/null | sort)"
HOME="$TMP_HOME" "$SCRIPT" --dry-run --bin-dir "$TMP_HOME/.local/bin" >/tmp/dry.out 2>&1 || true
after_all="$(find "$TMP_HOME" -mindepth 1 2>/dev/null | sort)"
if [[ "$before_all" == "$after_all" ]]; then
  ok "--dry-run не создаёт файлов в изолированном HOME"
else
  bad "--dry-run создал записи в изолированном HOME (diff): $(diff <(echo "$before_all") <(echo "$after_all") || true)"
fi
grep -q "install.sh" /tmp/dry.out && ok "--dry-run печатает план install.sh" || bad "--dry-run: план install.sh не найден в выводе"
grep -q "MCP-пресеты" /tmp/dry.out && ok "--dry-run печатает ступень MCP-пресетов" || bad "--dry-run: ступень MCP-пресетов не найдена в выводе"

# 5) --skip-projects принимается (не ошибка) в dry-run режиме
if HOME="$TMP_HOME" "$SCRIPT" --dry-run --skip-projects --bin-dir "$TMP_HOME/.local/bin" >/tmp/skip.out 2>&1; then
  grep -q -- "--skip-projects принят" /tmp/skip.out && ok "--skip-projects принимается и отмечен в выводе" || bad "--skip-projects: заметка не найдена в выводе"
else
  bad "--dry-run --skip-projects завершился с ошибкой"
fi

# 6) роут `swissknifeman setup --machine --dry-run` делегирует в bootstrap-machine.sh
if out="$(HOME="$TMP_HOME" "$SWISSKNIFEMAN" setup --machine --dry-run --bin-dir "$TMP_HOME/.local/bin" 2>&1)"; then
  echo "$out" | grep -q "bootstrap-machine" && ok "swissknifeman setup --machine делегирует в bootstrap-machine.sh" || bad "swissknifeman setup --machine: нет признаков делегирования"
else
  bad "swissknifeman setup --machine --dry-run завершился с ошибкой"
fi

# 7) `swissknifeman setup <project>` (без --machine) остаётся маршрутом на maind onboard —
#    проверяем что это НЕ маршрутизируется в bootstrap-machine.sh (rc не важен: без позиционного
#    project'а maind onboard сам завершается ошибкой usage — это его штатное поведение, не наше).
out="$("$SWISSKNIFEMAN" setup --help 2>&1 || true)"
if echo "$out" | grep -q "bootstrap-machine"; then
  bad "setup --help упоминает bootstrap-machine — маршрут без --machine перепутан"
elif echo "$out" | grep -qi "onboard"; then
  ok "setup без --machine маршрутизирован на maind onboard, не на bootstrap-machine.sh"
else
  bad "setup --help: вывод не похож ни на maind onboard usage, ни на bootstrap-machine ($out)"
fi

if (( fail == 0 )); then
  echo "test-bootstrap-machine: все проверки зелёные"
else
  echo "test-bootstrap-machine: ЕСТЬ ПРОВАЛЕННЫЕ ПРОВЕРКИ" >&2
fi
exit "$fail"
