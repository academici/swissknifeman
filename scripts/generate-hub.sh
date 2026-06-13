#!/usr/bin/env bash
# generate-hub.sh — генерирует в целевом проекте корневой «хаб» скиллов:
# приоритеты чтения источников + индекс установленных скиллов + правила поиска.
#
# Источники данных об установленном (объединяются):
#   .claude/settings.local.json / settings.json -> enabledPlugins."<bucket>@swissknifeman"
#   .swissknifeman-manifest.json в .claude/skills | .cursor/skills | .ai/skills
#
# Режимы записи:
#   проект с Laravel Boost (есть boost.json) -> .ai/guidelines/swissknifeman-hub.md
#       (Boost сам вставит фрагмент в CLAUDE.md при `php artisan boost:update`)
#   проект без Boost -> managed-блок в CLAUDE.md между маркерами
#       <!-- swissknifeman:hub:start --> ... <!-- swissknifeman:hub:end -->
#       (контент вне маркеров не изменяется; файл создаётся при отсутствии)
#   --root-files A,B -> тот же managed-блок дополнительно в указанные корневые
#       файлы (например AGENTS.md,GEMINI.md) — для тулз вне Boost. Игнорируется
#       в режиме Boost (там источник — .ai/guidelines/swissknifeman-hub.md).
#
# Использование:
#   ./scripts/generate-hub.sh --target ~/projects/my-app
#   ./scripts/generate-hub.sh --target . --dry-run
#   ./scripts/generate-hub.sh --target . --root-files AGENTS.md,GEMINI.md
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//' | sed -n '2,18p'; exit "${1:-0}"; }

TARGET=""
DRY_RUN=false
ROOT_FILES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --root-files) ROOT_FILES="$2"; shift 2 ;;
    -h|--help) usage 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage 1 ;;
  esac
done

[[ -n "$TARGET" ]] || { echo "Ошибка: --target обязателен" >&2; usage 1; }
[[ -d "$TARGET" ]] || { echo "Ошибка: каталог не найден: $TARGET" >&2; exit 1; }

export SKM_TARGET="$TARGET" SKM_DRY_RUN="$DRY_RUN" SKM_ROOT_FILES="$ROOT_FILES"

python3 - "$REPO_ROOT" <<'PY'
import json, os, sys
from pathlib import Path

root = Path(sys.argv[1])
target = Path(os.path.expanduser(os.environ["SKM_TARGET"])).resolve()
dry_run = os.environ["SKM_DRY_RUN"] == "true"
root_files = [f.strip() for f in os.environ.get("SKM_ROOT_FILES", "").split(",")
              if f.strip()]

START = "<!-- swissknifeman:hub:start -->"
END = "<!-- swissknifeman:hub:end -->"


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


registry = json.loads((root / "skills.json").read_text(encoding="utf-8"))
buckets_meta = json.loads((root / "buckets.json").read_text(encoding="utf-8"))
by_bucket = {}
for s in registry["skills"]:
    by_bucket.setdefault(s["bucket"], []).append(s)

# --- 1. собрать установленное -------------------------------------------------
installed = {}  # bucket -> {skill-name: entry}


def add_skill(entry):
    installed.setdefault(entry["bucket"], {})[entry["name"]] = entry


def add_bucket(bucket):
    for s in by_bucket.get(bucket, []):
        add_skill(s)


# канал marketplace: enabledPlugins."<bucket>@swissknifeman": true
for settings_name in ("settings.local.json", "settings.json"):
    f = target / ".claude" / settings_name
    if not f.exists():
        continue
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        continue
    for key, enabled in (data.get("enabledPlugins") or {}).items():
        if enabled and key.endswith("@swissknifeman"):
            add_bucket(key.split("@", 1)[0])

# канал install.sh: манифесты вендоринга
by_source_path = {}
for s in registry["skills"]:
    # skills/<bucket>/<rel>/SKILL.md -> skills/<bucket>/<rel>
    by_source_path[str(Path(s["path"]).parent)] = s

for rel_root in (".claude/skills", ".cursor/skills", ".ai/skills"):
    mf = target / rel_root / ".swissknifeman-manifest.json"
    if not mf.exists():
        continue
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        continue
    for entry in data.get("skills", []):
        src = entry.get("source_path", "")
        skill = by_source_path.get(src)
        if skill:
            add_skill(skill)

if not installed:
    die("в проекте не найдено установленных скиллов swissknifeman\n"
        "  (нет enabledPlugins в .claude/settings*.json и нет "
        ".swissknifeman-manifest.json) — сначала connect-claude.sh или install.sh")

# --- 2. собрать markdown хаба ---------------------------------------------------
boost_mode = (target / "boost.json").exists()
total = sum(len(v) for v in installed.values())

lines = []
lines.append("# Swissknifeman: хаб скиллов")
lines.append("")
lines.append("<!-- Сгенерировано scripts/generate-hub.sh из реестра swissknifeman. -->")
lines.append("<!-- НЕ редактируйте вручную: перегенерация затрёт правки. -->")
lines.append("")
lines.append("## Приоритет источников правил")
lines.append("")
lines.append("1. Проектные правила и скиллы (`.ai/guidelines/`, `.ai/skills/`, "
             "корневые инструкции проекта) — высший приоритет.")
if boost_mode:
    lines.append("2. Laravel Boost: для версионно-специфичных тем (Laravel, Pest, "
                 "Inertia, Livewire, Tailwind, Filament) используй встроенные "
                 "скиллы/гайдлайны Boost — они привязаны к версиям пакетов.")
    lines.append("3. Скиллы swissknifeman (индекс ниже) — архитектура, структура, "
                 "практики, процессы.")
else:
    lines.append("2. Скиллы swissknifeman (индекс ниже) — архитектура, структура, "
                 "практики, процессы. Если в проект добавят Laravel Boost, его "
                 "версионно-специфичные скиллы приоритетнее пересекающихся.")
lines.append("")
lines.append("Конфликт правил: побеждает более специфичный источник "
             "(проект > Boost > реестр swissknifeman).")
lines.append("")
lines.append("## Как найти нужный скилл")
lines.append("")
lines.append("1. Определи область задачи и найди бакет в индексе ниже.")
lines.append("2. Выбери скилл по описанию; внутри скилла открывай сниппеты только "
             "по его таблице «когда какой сниппет открывать» — не загружай всё подряд.")
lines.append("3. Структурные вопросы нового кода решай в порядке: структура "
             "(`laravel-structure`) -> взаимодействие (`dependency-injection`) -> "
             "реализация (профильный скилл).")
lines.append("4. Устройство системы скиллов в проекте (источник истины, симлинки, "
             "gitignore) — скилл `skills-ssot`.")
lines.append("")
lines.append(f"## Установленные скиллы ({total})")
lines.append("")
for bucket in sorted(installed):
    meta = buckets_meta.get(bucket, {})
    desc = meta.get("description", "")
    lines.append(f"### {bucket}" + (f" — {desc}" if desc else ""))
    lines.append("")
    for name in sorted(installed[bucket]):
        entry = installed[bucket][name]
        lines.append(f"- **{name}** — {entry.get('description', '')}")
    lines.append("")

hub_md = "\n".join(lines).rstrip() + "\n"

# --- 3. записать ----------------------------------------------------------------
if boost_mode:
    out = target / ".ai" / "guidelines" / "swissknifeman-hub.md"
    if dry_run:
        print(f"[dry-run] записал бы {out} ({len(hub_md.splitlines())} строк)")
        print(hub_md)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(hub_md, encoding="utf-8")
        print(f"Хаб записан: {out}")
        print("Обнаружен Laravel Boost: выполните `php artisan boost:update`, "
              "чтобы фрагмент попал в CLAUDE.md/AGENTS.md.")
else:
    block = f"{START}\n{hub_md}{END}\n"

    def upsert_block(out):
        """Вставить/обновить managed-блок между маркерами; контент вне маркеров
        не трогается; файл создаётся при отсутствии."""
        if out.exists():
            text = out.read_text(encoding="utf-8")
            if START in text and END in text:
                head, rest = text.split(START, 1)
                _, tail = rest.split(END, 1)
                return head + block + tail.lstrip("\n")
            sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
            return text + sep + block
        return block

    # CLAUDE.md по умолчанию + любые --root-files (AGENTS.md, GEMINI.md, …)
    targets = ["CLAUDE.md"] + [f for f in root_files if f != "CLAUDE.md"]
    for name in targets:
        out = target / name
        new_text = upsert_block(out)
        if dry_run:
            print(f"[dry-run] обновил бы managed-блок в {out}")
        else:
            out.write_text(new_text, encoding="utf-8")
            print(f"Хаб записан: {out} (managed-блок между маркерами swissknifeman:hub)")
    if dry_run:
        print(block)

print(f"Скиллов в индексе: {total}, бакетов: {len(installed)}")
PY
