#!/usr/bin/env bash
# Отчёт покрытия переводов скиллов: для каждого skills/**/SKILL.md проверяет
# наличие соседа SKILL.<lang>.md. Переводы gitignored, агент их НЕ грузит
# (канон — SKILL.md). Не вызывается из `skiller registry` — отдельный тулинг.
# Usage:
#   scripts/check-translations.sh [--lang en] [--generate-stubs]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO_ROOT" "$@" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
args = sys.argv[2:]
lang, gen = "en", False
i = 0
while i < len(args):
    a = args[i]
    if a == "--lang" and i + 1 < len(args):
        lang = args[i + 1]; i += 2; continue
    if a == "--generate-stubs":
        gen = True; i += 1; continue
    print(f"unknown arg: {a}", file=sys.stderr); sys.exit(2)

skills_root = root / "skills"
originals = sorted(skills_root.rglob("SKILL.md"))
suffix = f"SKILL.{lang}.md"
missing = orphaned = 0

# Осиротевшие: перевод без канона рядом.
for tr in sorted(skills_root.rglob(suffix)):
    if not (tr.parent / "SKILL.md").is_file():
        print(f"⚠️  ORPHANED: {tr.relative_to(root)}")
        orphaned += 1

for orig in originals:
    tr = orig.parent / suffix
    if tr.is_file():
        continue
    print(f"❌ MISSING [{lang}]: {tr.relative_to(root)}")
    missing += 1
    if gen:
        body = orig.read_text(encoding="utf-8")
        stub = (f"> 🌐 Перевод для человека ({lang}). Агент использует SKILL.md, "
                f"не этот файл.\n> TODO: перевести.\n\n---\n\n{body}")
        tr.write_text(stub, encoding="utf-8")
        print(f"   ✅ stub: {tr.relative_to(root)}")

print(f"\nИтого: {len(originals)} скиллов · {missing} без перевода [{lang}] "
      f"· {orphaned} осиротевших")
PY
