"""hub — корневой хаб скиллов в проекте (managed-блок CLAUDE.md / .ai/guidelines).

Генератор живёт здесь (импортируемый и тестируемый), `scripts/generate-hub.sh` —
тонкий лаунчер поверх `python3 -m skiller.hub` (как `bin/skiller`).

ФОРМА БЛОКА ОПРЕДЕЛЯЕТСЯ КАНАЛОМ-ЦЕЛЬЮ, не проектом (2026.07.31-SKM-LEAN D20/P2.5):

  краткая (`short`)  — цель, у которой ЕСТЬ нативный листинг скиллов: `CLAUDE.md`
      Claude Code и Boost-фрагмент `.ai/guidelines/swissknifeman-hub.md` (Boost
      вставляет его в CLAUDE.md — резидентность та же). Клиент и так держит
      резидентно имя+описание каждого доступного скилла (RAG:✅ 2026-07-31
      <https://code.claude.com/docs/en/features-overview> §Skills), поэтому индекс
      в блоке — второй платный экземпляр: он не печатается, остаются приоритеты
      источников, правила поиска и указатель на полный индекс.
  Codex (`AGENTS.md`) — краткая форма; подтверждение через реальный offline
      `codex debug prompt-input` из cwd проекта. Неподтверждённые имена остаются.
  полная (`full`)    — цель БЕЗ нативного листинга: `--root-files GEMINI.md`
      и любые сторонние корневые файлы. Там индекс — единственный носитель
      обнаружения, он остаётся.
  заглушка (`stub`)  — по умолчанию для `CLAUDE.md` и `AGENTS.md`: между маркерами
      только HTML-комментарии (registry stamp + указатель на `--full-index`).
      Скиллы и task-команды подключаются нативно; prose-хаб не дублируется.

`--full-index` возвращает полную форму ВСЕМ целям одной командой (путь отката).
`--hub-legacy-short` — прежняя краткая форма с приоритетами/поиском (без полного индекса).

СВЕРКА ПЕРЕД СОКРАЩЕНИЕМ (обязательна): скилл убирается из блока, только если он
подтверждён в нативном активном наборе проекта ДВУМЯ независимыми условиями —
(1) он есть в наборе измерителя `budget.resolve_active_set` (источник, названный
ТЗ P2.5) И (2) он доставлен КАНАЛОМ, который Claude Code перечисляет нативно
(включённый плагин маркетплейса либо физическая копия в `.claude/skills`).
Второе условие добавлено, потому что `resolve_active_set` моделирует ось
vendor-выборки и НЕ читает `enabledPlugins`: на connect-проекте он отвечает не на
тот вопрос (замер agelto 2026-07-31 — 86 скиллов набора против 20 доставленных
клиентом). Конъюнкция строго сильнее требования ТЗ: всё, что уходит из блока,
лежит и в наборе измерителя, и в нативном канале. Неподтверждённые скиллы
остаются перечисленными отдельным разделом, а расхождение печатается."""
import hashlib
import json
import os
import sys
from pathlib import Path

from .common import HUB_MARKER, MANIFEST, find_monorepo_root, run_cmd

HUB_START = HUB_MARKER
HUB_END = "<!-- swissknifeman:hub:end -->"

FORM_SHORT = "short"
FORM_FULL = "full"
FORM_STUB = "stub"

CLAUDE_TARGET = "CLAUDE.md"
BOOST_TARGET = Path(".ai") / "guidelines" / "swissknifeman-hub.md"
# Раскладки физических копий, где ищется манифест вендоринга (источник индекса).
SCAN_ROOTS = (".claude/skills", ".cursor/skills", ".ai/skills")
# Раскладка, которую Claude Code перечисляет нативно как скиллы ПРОЕКТА.
CLAUDE_SKILLS_DIR = ".claude/skills"
MARKETPLACE_SUFFIX = "@swissknifeman"


def hub_artifacts_exist(target):
    if (target / BOOST_TARGET).is_file():
        return True
    claude_md = target / CLAUDE_TARGET
    return claude_md.is_file() and HUB_MARKER in claude_md.read_text(encoding="utf-8")


def generate_hub(env, target, *, full_index=False, root_files=()):
    argv = [str(env.root / "scripts" / "generate-hub.sh"), "--target", str(target)]
    if full_index:
        argv.append("--full-index")
    if root_files:
        argv.extend(["--root-files", ",".join(root_files)])
    run_cmd(argv)


# --- источники установленного --------------------------------------------------
def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def enabled_marketplace_buckets(target):
    """Бакеты, включённые каналом marketplace: enabledPlugins."<bucket>@swissknifeman"."""
    names = []
    for settings_name in ("settings.local.json", "settings.json"):
        data = _load_json(Path(target) / ".claude" / settings_name)
        if not isinstance(data, dict):
            continue
        for key, enabled in (data.get("enabledPlugins") or {}).items():
            if enabled and key.endswith(MARKETPLACE_SUFFIX):
                name = key.split("@", 1)[0]
                if name not in names:
                    names.append(name)
    return names


def collect_installed(registry, target):
    """Установленное в проекте: {bucket: {name: entry}} + список найденных каналов.

    Два канала (объединяются, как и раньше): marketplace-плагины по имени бакета
    и манифесты вендоринга в известных раскладках."""
    target = Path(target)
    by_bucket = {}
    for s in registry["skills"]:
        by_bucket.setdefault(s["bucket"], []).append(s)
    by_source_path = {str(Path(s["path"]).parent): s for s in registry["skills"]}

    installed, channels = {}, {"plugins": [], "manifests": []}

    def add_skill(entry):
        installed.setdefault(entry["bucket"], {})[entry["name"]] = entry

    for bucket in enabled_marketplace_buckets(target):
        channels["plugins"].append(bucket)
        for s in by_bucket.get(bucket, []):
            add_skill(s)

    scan_roots = list(SCAN_ROOTS)
    for cfg_rel in (".swissknifeman/config.json", ".swissknife.json"):
        cfg = _load_json(target / cfg_rel)
        sp = cfg.get("skills_path") if isinstance(cfg, dict) else None
        if sp and sp not in scan_roots:
            scan_roots.append(sp)

    for rel_root in scan_roots:
        data = _load_json(target / rel_root / MANIFEST)
        if not isinstance(data, dict):
            continue
        channels["manifests"].append(rel_root)
        for entry in data.get("skills", []):
            skill = by_source_path.get(entry.get("source_path", ""))
            if skill:
                add_skill(skill)
    return installed, channels


def installed_names(installed):
    return {name for bucket in installed.values() for name in bucket}


# --- агенты проекта ------------------------------------------------------------
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


def collect_agents(target, registry_names):
    """Агенты проекта (.claude/agents/*.md) + сверка их `skills:` с реестром.

    Регрессия «скиллы не видны»: нативное поле skills: у субагента молча no-op на
    неизвестном имени, поэтому каждое имя проверяется."""
    agents, unknown = [], set()
    agents_dir = Path(target) / ".claude" / "agents"
    if not agents_dir.is_dir():
        return agents, unknown
    for af in sorted(agents_dir.glob("*.md")):
        a = parse_agent_frontmatter(af)
        a["file"] = af.name
        checked = []
        for sk in a["skills"]:
            bare = sk.split(":", 1)[1] if ":" in sk else sk  # допускаем bucket:name
            ok = bare in registry_names
            if not ok:
                unknown.add(sk)
            checked.append((sk, ok))
        a["skills_checked"] = checked
        agents.append(a)
    return agents, unknown


# --- нативный активный набор (сверка перед сокращением) -------------------------
def _marketplace_plugin_skills(env, registry):
    """Скиллы, которые НАТИВНО перечисляет клиент по каждому плагину маркетплейса.

    Источник — сгенерированный `.claude-plugin/marketplace.json` умбреллы, то есть
    ровно то, что читает клиент, а НЕ отображение «бакет → реестр», по которому
    строится индекс блока (иначе сверка проверяла бы саму себя). Курируемый плагин
    перечисляет скиллы явно (`skills: [...]`), бакетный отдаёт каталог целиком
    (`source: ./packages/skiller/skills/<bucket>`), пакетный (`./packages/task`)
    офлайн не разворачивается — его скиллы просто не подтверждаются.
    → {plugin: set(names)}; пустой dict, если манифест недоступен."""
    monorepo = find_monorepo_root(env.root)
    if monorepo is None:
        return {}
    data = _load_json(Path(monorepo) / ".claude-plugin" / "marketplace.json")
    if not isinstance(data, dict):
        return {}
    try:
        pkg_prefix = f"./{Path(env.root).relative_to(monorepo).as_posix()}/"
    except ValueError:
        return {}
    by_source_path = {str(Path(s["path"]).parent): s for s in registry["skills"]}
    out = {}
    for plugin in data.get("plugins", []):
        name = plugin.get("name")
        if not name:
            continue
        names = set()
        paths = plugin.get("skills")
        if isinstance(paths, list):
            for p in paths:
                skill = by_source_path.get(str(p).replace(pkg_prefix, "", 1))
                if skill:
                    names.add(skill["name"])
        else:
            source = str(plugin.get("source", ""))
            if source.startswith(pkg_prefix):
                rel = source[len(pkg_prefix):].rstrip("/")
                for src, skill in by_source_path.items():
                    if src == rel or src.startswith(rel + "/"):
                        names.add(skill["name"])
        out[name] = names
    return out


def _project_skill_names(target):
    """Скиллы, физически лежащие в `.claude/skills/<name>/SKILL.md` — их клиент
    перечисляет нативно как скиллы проекта."""
    d = Path(target) / CLAUDE_SKILLS_DIR
    if not d.is_dir():
        return set()
    return {p.name for p in sorted(d.iterdir())
            if p.is_dir() and (p / "SKILL.md").is_file()}


def _codex_installed(env, target, registry, installed, channels, inventory):
    """Scope fallback pointers to Codex selection, never Claude-only extras.

    Explicit native config also covers selected plugins whose cache is missing;
    those need fallback pointers even though native ``plugin list`` omits them.
    Discovery/config failure retains the original conservative inventory.
    """
    if not inventory.get("ok"):
        return installed
    from .native_codex import SUFFIX, _read, codex_home
    selected = set(inventory.get("enabled", ()))
    overrides = {}
    try:
        for path in (codex_home(env) / "config.toml", Path(target) / ".codex/config.toml"):
            _, config = _read(path)
            for identifier, options in config.get("plugins", {}).items():
                if identifier.endswith(SUFFIX) and "enabled" in options:
                    if not isinstance(options["enabled"], bool):
                        raise ValueError("native plugin enabled is not boolean")
                    overrides[identifier[:-len(SUFFIX)]] = options["enabled"]
    except (OSError, ValueError, TypeError, AttributeError) as error:
        inventory["notes"].append(f"Codex selection unavailable; keeping fallback inventory: {error}")
        return installed
    for plugin, enabled in overrides.items():
        if enabled:
            selected.add(plugin)
        else:
            selected.discard(plugin)
    plugin_skills = _marketplace_plugin_skills(env, registry)
    if not plugin_skills and selected:
        inventory["notes"].append("Codex plugin catalog unavailable; keeping fallback inventory")
        return installed
    candidates = set().union(*(plugin_skills.get(plugin, set()) for plugin in selected))
    by_source = {str(Path(skill["path"]).parent): skill["name"] for skill in registry["skills"]}
    for folder in set(channels["manifests"]) | {".agents/skills"}:
        manifest = _load_json(Path(target) / folder / MANIFEST)
        if not isinstance(manifest, dict):
            continue
        for entry in manifest.get("skills", []):
            if isinstance(entry, dict) and entry.get("source_path") in by_source:
                candidates.add(by_source[entry["source_path"]])
    result = {}
    for skill in registry["skills"]:
        if skill["name"] in candidates:
            result.setdefault(skill["bucket"], {})[skill["name"]] = skill
    return result


def _measurer_active_names(env, target):
    """Активный набор ИЗМЕРИТЕЛЯ (`budget.resolve_active_set`) — источник, названный
    ТЗ P2.5. Импорт ленивый: budget → vendor → hub, прямой импорт замкнул бы цикл.
    → (names, detail); names=None, если набор не резолвится (тогда не сокращаем)."""
    try:
        from .budget import resolve_active_set
        from .config import load_config
        config = load_config(env, Path(target))
        skills, _meta = resolve_active_set(env, Path(target), config)
        names = {fm_name or Path(d).name for _b, _r, d, fm_name in skills}
        return names, f"{len(names)} скиллов"
    except (Exception, SystemExit) as error:  # noqa: BLE001 — fail-closed, не молча
        return None, f"n/a ({error})"


def native_check(env, target, names):
    """Сверка перед сокращением: какие из `names` подтверждены нативным набором.

    → {confirmed, unconfirmed, native_channel, measurer_detail, notes}."""
    plugin_skills = _marketplace_plugin_skills(env, registry_of(env))
    delivered, plugin_notes = set(), []
    for bucket in enabled_marketplace_buckets(target):
        known = plugin_skills.get(bucket)
        if known is None:
            plugin_notes.append(f"плагин {bucket}@ не найден в marketplace.json")
            continue
        delivered |= known
    project_skills = _project_skill_names(target)
    delivered |= project_skills

    measurer_names, measurer_detail = _measurer_active_names(env, target)
    if measurer_names is None:
        confirmed = set()
        notes = [f"набор измерителя не резолвится — сокращение отключено: {measurer_detail}"]
    else:
        confirmed = set(names) & delivered & measurer_names
        notes = []
    notes.extend(plugin_notes)
    return {
        "confirmed": confirmed,
        "unconfirmed": sorted(set(names) - confirmed),
        "native_channel": sorted(delivered),
        "measurer_detail": measurer_detail,
        "notes": notes,
    }


_REGISTRY_CACHE = {}


def registry_of(env):
    """skills.json реестра (кэш на процесс — сверка и индекс читают один файл)."""
    key = str(env.root)
    if key not in _REGISTRY_CACHE:
        _REGISTRY_CACHE[key] = json.loads(
            (Path(env.root) / "skills.json").read_text(encoding="utf-8"))
    return _REGISTRY_CACHE[key]


# --- сборка markdown ------------------------------------------------------------
def _priority_lines(boost_mode, form):
    where = ("индекс ниже" if form == FORM_FULL
             else "нативный листинг скиллов клиента")
    out = ["## Приоритет источников правил", "",
           "1. Проектные правила и скиллы (`.ai/guidelines/`, `.ai/skills/`, "
           "корневые инструкции проекта) задают локальные соглашения."]
    if boost_mode:
        out.append("2. Laravel Boost: для версионно-специфичных тем (Laravel, Pest, "
                   "Inertia, Livewire, Tailwind, Filament) используй встроенные "
                   "скиллы/гайдлайны Boost — они привязаны к версиям пакетов.")
        out.append(f"3. Скиллы swissknifeman ({where}) — архитектура, структура, "
                   "практики, процессы.")
    else:
        out.append(f"2. Скиллы swissknifeman ({where}) — архитектура, структура, "
                   "практики, процессы. Если в проект добавят Laravel Boost, его "
                   "версионно-специфичные скиллы приоритетнее пересекающихся.")
    out += ["", "Скиллы дополняют инструкции среды и запрос владельца; внутри совместимых правил выбирай более специфичный источник "
                "(проект > Boost > реестр swissknifeman).", ""]
    return out


def _search_lines(form):
    out = ["## Как найти нужный скилл", ""]
    if form == FORM_FULL:
        out.append("1. Определи область задачи и найди бакет в индексе ниже.")
    else:
        out.append("1. Скиллы swissknifeman уже перечислены НАТИВНЫМ листингом "
                   "клиента (имя + описание каждого доступного скилла резидентны "
                   "с начала сессии) — ищи по нему; здесь индекс не дублируется.")
    out += ["2. Выбери скилл по описанию; внутри скилла открывай сниппеты только "
            "по его таблице «когда какой сниппет открывать» — не загружай всё подряд.",
            "3. Открывай архитектурные скиллы при изменении соответствующих контрактов; "
            "обычная правка следует существующей структуре проекта.",
            "4. Устройство системы скиллов в проекте (источник истины, симлинки, "
            "gitignore) — скилл `skills-ssot`."]
    if form == FORM_SHORT:
        out.append("5. Полный индекс с описаниями (если нужен человеку): "
                   "`skiller status` в проекте либо "
                   "`generate-hub.sh --target <проект> --full-index --dry-run`.")
    out.append("")
    return out


def _agents_lines(agents, unknown_skills):
    if not agents:
        return []
    out = [f"## Агенты проекта ({len(agents)})", "",
           "Роли в `.claude/agents/`. Преднагруженные скиллы — поле `skills:` "
           "(⚠ = имя не найдено в реестре, preload молча не сработает).", "",
           "| Агент | Назначение | Преднагруженные скиллы |", "|---|---|---|"]
    for a in agents:
        sk = ", ".join((f"⚠ {n}" if not ok else n)
                       for n, ok in a["skills_checked"]) or "—"
        desc = (a["description"] or "").replace("|", "\\|").replace("\n", " ")
        if len(desc) > 120:
            desc = desc[:117] + "…"
        out.append(f"| `{a['name'] or a['file']}` | {desc} | {sk} |")
    out.append("")
    if unknown_skills:
        out.append("> ⚠ **Несостыковка:** имена в `skills:` не найдены в реестре: "
                   + ", ".join("`" + u + "`" for u in sorted(unknown_skills))
                   + ". Проверь имена или подключи нужный бакет — иначе preload молча "
                     "не сработает.")
        out.append("")
    return out


def _index_lines(installed, buckets_meta, title, note=""):
    total = sum(len(v) for v in installed.values())
    out = [f"## {title} ({total})", ""]
    if note:
        out += [note, ""]
    for bucket in sorted(installed):
        desc = buckets_meta.get(bucket, {}).get("description", "")
        out.append(f"### {bucket}" + (f" — {desc}" if desc else ""))
        out.append("")
        for name in sorted(installed[bucket]):
            out.append(f"- **{name}** — {installed[bucket][name].get('description', '')}")
        out.append("")
    return out


def build_stub_markdown(*, reg_sha, reg_count):
    """Comment-only hub: no resident prose; discovery stays native (plugins/skills/commands)."""
    return "\n".join([
        "<!-- swissknifeman hub: stub — скиллы и task-команды подключаются нативно; "
        "индекс и правила приоритета здесь не дублируются. -->",
        f"<!-- swissknifeman:registry sha={reg_sha} skills={reg_count} -->",
        "<!-- Полный индекс: `skiller status` или generate-hub.sh --target <dir> --full-index. -->",
        "",
    ])


def build_hub_markdown(*, installed, buckets_meta, agents, unknown_skills, reg_sha,
                       reg_count, boost_mode, form, unconfirmed=()):
    """Markdown блока в заданной ФОРМЕ. Краткая форма не печатает индекс, кроме
    скиллов, не подтверждённых нативным набором (они остаются перечисленными)."""
    if form == FORM_STUB:
        return build_stub_markdown(reg_sha=reg_sha, reg_count=reg_count)
    lines = ["# Swissknifeman: хаб скиллов", "",
             "<!-- Сгенерировано scripts/generate-hub.sh из реестра swissknifeman. -->",
             "<!-- НЕ редактируйте вручную: перегенерация затрёт правки. -->",
             f"<!-- swissknifeman:registry sha={reg_sha} skills={reg_count} -->", ""]
    lines += _priority_lines(boost_mode, form)
    lines += _search_lines(form)
    lines += _agents_lines(agents, unknown_skills)
    if form == FORM_FULL:
        lines += _index_lines(installed, buckets_meta, "Установленные скиллы")
    else:
        residual = {b: {n: e for n, e in skills.items() if n in set(unconfirmed)}
                    for b, skills in installed.items()}
        residual = {b: s for b, s in residual.items() if s}
        if residual:
            lines += _index_lines(
                residual, buckets_meta, "Скиллы вне нативного листинга",
                "> Эти скиллы установлены swissknifeman, но не подтверждены в "
                "нативном активном наборе проекта — перечислены поимённо, чтобы "
                "не потерять обнаружение.")
    return "\n".join(lines).rstrip() + "\n"


# --- запись ---------------------------------------------------------------------
def upsert_block(out, block):
    """Вставить/обновить managed-блок между маркерами; контент вне маркеров не
    трогается; файл создаётся при отсутствии."""
    if out.exists():
        text = out.read_text(encoding="utf-8")
        if HUB_START in text and HUB_END in text:
            head, rest = text.split(HUB_START, 1)
            _, tail = rest.split(HUB_END, 1)
            return head + block + tail.lstrip("\n")
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return text + sep + block
    return block


def target_form(name, *, boost_mode=False, full_index=False, legacy_short=False):
    """Форма блока по КАНАЛУ-ЦЕЛИ (D20). `--full-index` возвращает полную всем."""
    if full_index:
        return FORM_FULL
    if legacy_short:
        if boost_mode:
            return FORM_SHORT
        return FORM_SHORT if name in (CLAUDE_TARGET, "AGENTS.md") else FORM_FULL
    if boost_mode:
        return FORM_STUB
    return FORM_STUB if name in (CLAUDE_TARGET, "AGENTS.md") else FORM_FULL


def run(env, target, *, dry_run=False, root_files=(), full_index=False, legacy_short=False,
        out=print):
    """Сгенерировать и записать хаб. → dict со сводкой (для тестов и отчётов)."""
    target = Path(os.path.expanduser(str(target))).resolve()
    registry = registry_of(env)
    buckets_meta = json.loads(
        (Path(env.root) / "buckets.json").read_text(encoding="utf-8"))

    installed, channels = collect_installed(registry, target)
    # Гейт КАНАЛЬНЫЙ, не индексный: раздача есть — блок пишем, даже если индекс
    # пуст (краткой форме он не нужен; полная форма при пустом индексе получает
    # WARNING ниже). Раздачи нет вовсе — писать нечего.
    if not (channels["plugins"] or channels["manifests"]):
        out("ERROR: в проекте не найдено раздачи скиллов swissknifeman\n"
            "  (нет enabledPlugins в .claude/settings*.json и нет "
            f"{MANIFEST}) — сначала connect-claude.sh или install.sh",
            file=sys.stderr)
        raise SystemExit(1)

    agents, unknown_skills = collect_agents(
        target, {s["name"] for s in registry["skills"]})
    reg_sha = hashlib.sha256(
        (Path(env.root) / "skills.json").read_bytes()).hexdigest()[:12]

    boost_mode = (target / "boost.json").exists()
    names = installed_names(installed)
    targets = ([str(BOOST_TARGET)] if boost_mode
               else [CLAUDE_TARGET] + [f for f in root_files if f != CLAUDE_TARGET])
    forms = {name: target_form(name, boost_mode=boost_mode, full_index=full_index,
                               legacy_short=legacy_short)
             for name in targets}

    if not names and channels["plugins"]:
        out("WARNING: индекс пуст: включённые плагины ("
            + ", ".join(channels["plugins"]) + ") не разворачиваются в бакеты "
            "реестра — их скиллы перечисляет только нативный листинг клиента",
            file=sys.stderr)

    check = None
    if any(form == FORM_SHORT and name != "AGENTS.md" for name, form in forms.items()) and names:
        check = native_check(env, target, names)
        for note in check["notes"]:
            out(f"WARNING: сверка нативного набора: {note}", file=sys.stderr)
        out(f"Сверка перед сокращением: подтверждено {len(check['confirmed'])} "
            f"из {len(names)} (набор измерителя: {check['measurer_detail']})")
        if check["unconfirmed"]:
            out(f"Не подтверждены нативным набором ({len(check['unconfirmed'])}), "
                "остаются перечисленными: " + ", ".join(check["unconfirmed"]))
    unconfirmed = check["unconfirmed"] if check else sorted(names)

    codex_check = None
    codex_installed = installed
    if forms.get("AGENTS.md") == FORM_SHORT:
        from .native_codex import native_inventory
        codex_check = native_inventory(env, target)
        codex_installed = _codex_installed(env, target, registry, installed, channels, codex_check)
        for note in codex_check["notes"]:
            out(f"WARNING: {note}; AGENTS.md сохраняет неподтверждённые скиллы", file=sys.stderr)

    rendered = {}
    for name, form in forms.items():
        remaining = (sorted(installed_names(codex_installed) - codex_check["names"])
                     if name == "AGENTS.md" and codex_check is not None else unconfirmed)
        rendered[name] = build_hub_markdown(
            installed=codex_installed if name == "AGENTS.md" else installed,
            buckets_meta=buckets_meta, agents=agents,
            unknown_skills=unknown_skills, reg_sha=reg_sha,
            reg_count=len(registry["skills"]), boost_mode=boost_mode, form=form,
            unconfirmed=remaining)
        if form == FORM_FULL and not names:
            out(f"WARNING: {name}: полная форма при пустом индексе — канал без "
                "нативного листинга остаётся без обнаружения", file=sys.stderr)

    written = []
    for name, hub_md in rendered.items():
        out_path = target / name
        if boost_mode:
            if dry_run:
                out(f"[dry-run] записал бы {out_path} "
                    f"({len(hub_md.splitlines())} строк)")
                out(hub_md)
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(hub_md, encoding="utf-8")
                out(f"Хаб записан: {out_path}")
                out("Обнаружен Laravel Boost: выполните `php artisan boost:update`, "
                    "чтобы фрагмент попал в CLAUDE.md/AGENTS.md.")
        else:
            block = f"{HUB_START}\n{hub_md}{HUB_END}\n"
            new_text = upsert_block(out_path, block)
            if dry_run:
                out(f"[dry-run] обновил бы managed-блок в {out_path} "
                    f"(форма: {forms[name]}, {len(hub_md.splitlines())} строк)")
                out(block)
            else:
                out_path.write_text(new_text, encoding="utf-8")
                out(f"Хаб записан: {out_path} (форма: {forms[name]}, managed-блок "
                    "между маркерами swissknifeman:hub)")
        written.append(name)

    total = len(names)
    out(f"Скиллов в индексе: {total}, бакетов: {len(installed)}")
    out("Формы целей: " + ", ".join(f"{n}={forms[n]}" for n in targets))
    if agents:
        out(f"Агентов проиндексировано: {len(agents)}")
    if unknown_skills:
        out("WARNING: skills: у агентов не найдены в реестре (preload no-op): "
            + ", ".join(sorted(unknown_skills)), file=sys.stderr)
    return {"forms": forms, "written": written, "rendered": rendered,
            "installed": installed, "check": check, "codex_check": codex_check, "channels": channels}


USAGE = """generate-hub.sh — корневой «хаб» скиллов в проекте.

  --target <dir>        целевой проект (обязателен)
  --dry-run             ничего не писать, показать блок
  --root-files A,B      дополнительные корневые файлы (AGENTS.md,GEMINI.md)
  --full-index          полная форма (с индексом) ВСЕМ целям — путь отката
  --hub-legacy-short    краткая форма с приоритетами (до stub по умолчанию)
"""


def main(argv=None):
    """argv: [repo_root, *args] — как у `python3 -m skiller`."""
    from .common import Env
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(USAGE, file=sys.stderr)
        return 2
    root, args = argv[0], argv[1:]
    target, dry_run, root_files, full_index, legacy_short = "", False, [], False, False
    while args:
        arg = args.pop(0)
        if arg == "--target" and args:
            target = args.pop(0)
        elif arg == "--dry-run":
            dry_run = True
        elif arg == "--full-index":
            full_index = True
        elif arg == "--hub-legacy-short":
            legacy_short = True
        elif arg == "--root-files" and args:
            root_files = [f.strip() for f in args.pop(0).split(",") if f.strip()]
        elif arg in ("-h", "--help"):
            print(USAGE)
            return 0
        else:
            print(f"Неизвестный аргумент: {arg}", file=sys.stderr)
            print(USAGE, file=sys.stderr)
            return 1
    if not target:
        print("Ошибка: --target обязателен", file=sys.stderr)
        return 1
    if not Path(os.path.expanduser(target)).is_dir():
        print(f"Ошибка: каталог не найден: {target}", file=sys.stderr)
        return 1
    run(Env(root, "generate-hub"), target, dry_run=dry_run,
        root_files=root_files, full_index=full_index, legacy_short=legacy_short)
    return 0


if __name__ == "__main__":
    sys.exit(main())
