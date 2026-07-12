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
LOCAL_HOME=""
trap 'rm -rf "$TMP_HOME" "${LOCAL_HOME:-}"' EXIT
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

# 8) --projects: невалидный манифест (нет обязательного поля path) — ступень явно падает.
BAD_HOME="$(mktemp -d)"
BAD_MANIFEST="$BAD_HOME/manifest.json"
cat > "$BAD_MANIFEST" <<'EOF'
{"version": 1, "projects": [{"repo": "https://example.invalid/repo.git"}]}
EOF
if HOME="$BAD_HOME" "$SCRIPT" --dry-run --projects "$BAD_MANIFEST" --bin-dir "$BAD_HOME/.local/bin" >/tmp/badmanifest.out 2>&1; then
  bad "невалидный манифест (без path) должен завершаться ошибкой"
else
  grep -q "манифест невалиден" /tmp/badmanifest.out && ok "невалидный манифест — явная ошибка" || bad "невалидный манифест: нет диагностики в выводе"
fi
rm -rf "$BAD_HOME"

# 9) --projects + --dry-run: план печатает git clone/setup, ничего не пишет на диск
#    (кроме манифеста, который создали мы сами).
PROJ_HOME="$(mktemp -d)"
GOOD_MANIFEST="$PROJ_HOME/manifest.json"
cat > "$GOOD_MANIFEST" <<EOF
{"version": 1, "projects": [{"repo": "https://example.invalid/repo.git", "path": "~/dest/example-repo", "profile": ""}]}
EOF
before_proj="$(find "$PROJ_HOME" -mindepth 1 2>/dev/null | sort)"
HOME="$PROJ_HOME" "$SCRIPT" --dry-run --projects "$GOOD_MANIFEST" --bin-dir "$PROJ_HOME/.local/bin" >/tmp/dryprojects.out 2>&1 || true
after_proj="$(find "$PROJ_HOME" -mindepth 1 2>/dev/null | sort)"
if [[ "$before_proj" == "$after_proj" ]]; then
  ok "--projects --dry-run не пишет файлов (кроме манифеста, созданного тестом)"
else
  bad "--projects --dry-run создал записи на диске: $(diff <(echo "$before_proj") <(echo "$after_proj") || true)"
fi
grep -q "git clone https://example.invalid/repo.git" /tmp/dryprojects.out && ok "--projects --dry-run печатает план git clone" || bad "--projects --dry-run: план clone не найден в выводе"
rm -rf "$PROJ_HOME"

# 10) --projects (реальный прогон, без сети — локальный git-репозиторий как fixture):
#     RUN1 клонирует отсутствующий репозиторий; RUN2 (повторный прогон) НЕ делает повторный
#     clone/pull — рабочая копия идемпотентна (Code Guidance P7.2: манифест-шаг идемпотентен).
LOCAL_HOME="$(mktemp -d)"
SRC_REPO="$LOCAL_HOME/src-repo"
mkdir -p "$SRC_REPO"
git init -q "$SRC_REPO"
git -C "$SRC_REPO" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
LOCAL_MANIFEST="$LOCAL_HOME/manifest.json"
cat > "$LOCAL_MANIFEST" <<EOF
{"version": 1, "projects": [{"repo": "$SRC_REPO", "path": "~/dest/local-repo", "profile": ""}]}
EOF
HOME="$LOCAL_HOME" "$SCRIPT" --projects "$LOCAL_MANIFEST" --bin-dir "$LOCAL_HOME/.local/bin" >/tmp/run1.out 2>&1 || true
DEST_REPO="$LOCAL_HOME/dest/local-repo"
if [[ -d "$DEST_REPO/.git" ]]; then
  ok "--projects клонирует отсутствующий репозиторий из манифеста"
else
  bad "--projects: репозиторий из манифеста не клонирован ($DEST_REPO не найден)"
fi
commits_after_run1="$(git -C "$DEST_REPO" log --oneline 2>/dev/null | wc -l | tr -d ' ')"
HOME="$LOCAL_HOME" "$SCRIPT" --projects "$LOCAL_MANIFEST" --bin-dir "$LOCAL_HOME/.local/bin" >/tmp/run2.out 2>&1 || true
commits_after_run2="$(git -C "$DEST_REPO" log --oneline 2>/dev/null | wc -l | tr -d ' ')"
grep -q "SKIP clone" /tmp/run2.out && ok "повторный прогон --projects пропускает clone уже склонированного" || bad "повторный прогон --projects: нет SKIP clone в выводе"
if [[ "$commits_after_run1" == "$commits_after_run2" ]]; then
  ok "повторный прогон --projects не меняет git-историю клона (pull не делает)"
else
  bad "повторный прогон --projects изменил git-историю клона (был бы pull) — commits: $commits_after_run1 -> $commits_after_run2"
fi

# 11) --skip-projects побеждает даже при заданном --projects (ступень явно пропущена).
HOME="$LOCAL_HOME" "$SCRIPT" --dry-run --skip-projects --projects "$LOCAL_MANIFEST" --bin-dir "$LOCAL_HOME/.local/bin" >/tmp/skipwins.out 2>&1 || true
grep -q -- "--skip-projects принят" /tmp/skipwins.out && ok "--skip-projects побеждает --projects (ступень пропущена)" || bad "--skip-projects: ступень манифеста не была явно пропущена"

if (( fail == 0 )); then
  echo "test-bootstrap-machine: все проверки зелёные"
else
  echo "test-bootstrap-machine: ЕСТЬ ПРОВАЛЕННЫЕ ПРОВЕРКИ" >&2
fi
exit "$fail"
