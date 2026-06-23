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
import hashlib, json, os, sys
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

# Пути для поиска манифеста: фиксированные дефолты + skills_path из конфига
# vendor-режима (.swissknifeman/config.json), чтобы находить нестандартные
# раскладки вроде .agents/skills (sync пишет туда манифест).
scan_roots = [".claude/skills", ".cursor/skills", ".ai/skills"]
for cfg_rel in (".swissknifeman/config.json", ".swissknife.json"):
    cfg_file = target / cfg_rel
    if not cfg_file.is_file():
        continue
    try:
        sp = json.loads(cfg_file.read_text(encoding="utf-8")).get("skills_path")
    except (json.JSONDecodeError, OSError):
        sp = None
    if sp and sp not in scan_roots:
        scan_roots.append(sp)

for rel_root in scan_roots:
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

# --- 1b. агенты проекта + сверка их skills: с реестром ------------------------
# Регрессия «скиллы не видны»: нативное поле skills: у субагента молча no-op на
# неизвестном имени. Индексируем .claude/agents/*.md в хаб и проверяем каждое имя.
registry_names = {s["name"] for s in registry["skills"]}


def parse_agent_frontmatter(path):
    """name + description (скаляры) + skills (inline [..] или блок-список)."""
    fm = {"name": "", "description": "", "skills": []}
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    lines_ = text.splitlines()
    if not lines_ or lines_[0].strip() != "---":
        return fm
    list_key = None
    for line in lines_[1:]:
        if line.strip() == "---":
            break
        stripped = line.strip()
        if list_key and line[:1] in (" ", "\t") and stripped.startswith("- "):
            fm[list_key].append(stripped[2:].strip().strip('"').strip("'"))
            continue
        list_key = None
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            if key in ("name", "description"):
                fm[key] = value.strip('"').strip("'")
            elif key == "skills":
                if value.startswith("["):
                    fm["skills"] = [v.strip().strip('"').strip("'")
                                    for v in value.strip("[]").split(",") if v.strip()]
                elif value == "":
                    list_key = "skills"  # дальше блок-список
    return fm


agents = []
unknown_skills = set()
agents_dir = target / ".claude" / "agents"
if agents_dir.is_dir():
    for af in sorted(agents_dir.glob("*.md")):
        a = parse_agent_frontmatter(af)
        a["file"] = af.name
        checked = []
        for sk in a["skills"]:
            bare = sk.split(":", 1)[1] if ":" in sk else sk  # допускаем bucket:name
            ok = bare in registry_names
            if not ok:
                unknown_skills.add(sk)
            checked.append((sk, ok))
        a["skills_checked"] = checked
        agents.append(a)

# freshness-штамп: хэш реестра — doctor сверяет его с текущим, ловя дрейф «реестр
# изменился, хаб не перегенерён».
reg_sha = hashlib.sha256((root / "skills.json").read_bytes()).hexdigest()[:12]
reg_count = len(registry["skills"])

# --- 2. собрать markdown хаба ---------------------------------------------------
boost_mode = (target / "boost.json").exists()
total = sum(len(v) for v in installed.values())

lines = []
lines.append("# Swissknifeman: хаб скиллов")
lines.append("")
lines.append("<!-- Сгенерировано scripts/generate-hub.sh из реестра swissknifeman. -->")
lines.append("<!-- НЕ редактируйте вручную: перегенерация затрёт правки. -->")
lines.append(f"<!-- swissknifeman:registry sha={reg_sha} skills={reg_count} -->")
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
if agents:
    lines.append(f"## Агенты проекта ({len(agents)})")
    lines.append("")
    lines.append("Роли в `.claude/agents/`. Преднагруженные скиллы — поле `skills:` "
                 "(⚠ = имя не найдено в реестре, preload молча не сработает).")
    lines.append("")
    lines.append("| Агент | Назначение | Преднагруженные скиллы |")
    lines.append("|---|---|---|")
    for a in agents:
        sk = ", ".join((f"⚠ {n}" if not ok else n)
                       for n, ok in a["skills_checked"]) or "—"
        desc = (a["description"] or "").replace("|", "\\|").replace("\n", " ")
        if len(desc) > 120:
            desc = desc[:117] + "…"
        lines.append(f"| `{a['name'] or a['file']}` | {desc} | {sk} |")
    lines.append("")
    if unknown_skills:
        lines.append("> ⚠ **Несостыковка:** имена в `skills:` не найдены в реестре: "
                     + ", ".join("`" + u + "`" for u in sorted(unknown_skills))
                     + ". Проверь имена или подключи нужный бакет — иначе preload молча "
                       "не сработает.")
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
if agents:
    print(f"Агентов проиндексировано: {len(agents)}")
if unknown_skills:
    print("WARNING: skills: у агентов не найдены в реестре (preload no-op): "
          + ", ".join(sorted(unknown_skills)), file=sys.stderr)
PY
