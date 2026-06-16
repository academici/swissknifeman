#!/usr/bin/env bash
# validate.sh — структурные проверки узла maind (CI + локально).
# Проверяет: компиляцию Python, синтаксис bash, валидность JSON-конфигов,
# наличие ключевых файлов, и гоняет тесты (scripts/test.sh).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
fail=0
err() { echo "  FAIL: $*" >&2; fail=1; }

echo "[1/5] python compile"
python3 -m compileall -q lib tests || err "py_compile"

echo "[2/5] bash syntax"
for f in bin/maind install.sh scripts/*.sh; do
  bash -n "$f" || err "bash -n $f"
done

echo "[3/5] JSON конфиги"
for f in .maind.example.json package.json \
         .claude-plugin/plugin.json .claude-plugin/marketplace.json .mcp.json; do
  [[ -f "$f" ]] && { python3 -m json.tool "$f" >/dev/null || err "битый JSON: $f"; }
done

echo "[4/5] обязательные файлы"
for f in bin/maind lib/maind/__init__.py lib/maind/cli.py \
         config/memory/iii-config.yaml .maind.example.json .env.example \
         .claude-plugin/plugin.json .claude-plugin/marketplace.json .mcp.json \
         commands/maind.md commands/onboard.md commands/sync.md \
         README.md LICENSE; do
  [[ -e "$f" ]] || err "нет файла: $f"
done
grep -q '^workers:' config/memory/iii-config.yaml || err "iii-config.yaml без workers:"

echo "[5/5] тесты"
scripts/test.sh

echo ""
if [[ "$fail" -eq 0 ]]; then echo "validate: OK"; else echo "validate: ПРОВАЛ" >&2; exit 1; fi
