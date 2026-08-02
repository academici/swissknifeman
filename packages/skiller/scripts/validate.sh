#!/usr/bin/env bash
# Validate repository structure: SKILL.md frontmatter, upstream.json,
# profiles/*.json, skills.json, snippet manifests.
# Used locally and by .github/workflows/validate.yml.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO_ROOT" <<'PY'
import json, re, sys
from pathlib import Path

root = Path(sys.argv[1])  # корень пакета (skills/, lib/, buckets.json)
# marketplace.json — в корне монорепо; source-пути плагинов относительны корня репо.
# (Канон — core.repo.find_repo_root; здесь самодостаточный дубль: heredoc гоняется
#  до установки PYTHONPATH на core — осознанно не импортируем.)
def _repo_root(p):
    for cand in (p, *p.parents):
        if (cand / ".git").exists():
            return cand
    return p
repo_root = _repo_root(root)
errors = []
warnings = []

# --- CLAUDE.md line-count (токен-экономия; WARN, не fail) ------------------
# CLAUDE.md резидентен КАЖДУЮ сессию (Anthropic target ≤200 строк). Мягкий гейт по
# монорепо: root + packages/*/CLAUDE.md. Root — зонтичный гид, может легитимно расти →
# держим warning, не блок.
CLAUDE_MD_MAX_LINES = 200
for _cmd_md in [repo_root / "CLAUDE.md", *sorted((repo_root / "packages").glob("*/CLAUDE.md"))]:
    if _cmd_md.is_file():
        _n = len(_cmd_md.read_text(encoding="utf-8", errors="replace").splitlines())
        if _n > CLAUDE_MD_MAX_LINES:
            warnings.append(f"{_cmd_md.relative_to(repo_root)}: {_n} строк "
                            f"(> {CLAUDE_MD_MAX_LINES}) — CLAUDE.md резидентен каждую сессию, "
                            "вынеси детали в docs/скиллы (токен-экономия)")

# --- core-policy.json (декларативная CORE-политика, источник config.py) --------
_core_policy_path = root / "configs" / "core-policy.json"
if _core_policy_path.is_file():
    try:
        _cp = json.loads(_core_policy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as _e:
        errors.append(f"configs/core-policy.json: невалидный JSON: {_e}")
        _cp = None
    if isinstance(_cp, dict):
        for _sk in _cp.get("skills", []):
            if not (root / "skills" / _sk / "SKILL.md").is_file():
                errors.append(f"core-policy.json skills[]: '{_sk}' — нет skills/{_sk}/SKILL.md")
        for _ex in _cp.get("default_exclude", []):
            if not (root / "skills" / _ex / "SKILL.md").is_file():
                warnings.append(f"core-policy.json default_exclude[]: '{_ex}' — "
                                f"нет skills/{_ex}/SKILL.md")
else:
    warnings.append("configs/core-policy.json отсутствует — config.py на встроенном фолбэке")

UPSTREAM_SOURCES = {"github", "http", "file"}
# replace = зеркало (автонакат); notify = адаптированная копия (только сообщать);
# fork = форк с нашими правками (обёртка + pristine-зеркало в files[].path; на дрейфе
#        review_pending=true блокирует распространение — ручной перенос, потом --resolve);
# merge = композит из ≥2 внешних источников (origins[]: base + supplement/«suggest»),
#        собранный в единый скилл; синк РУЧНОЙ под управлением агента (на дрейфе любого
#        origin merge.review_pending=true блокирует — агент пере-мерджит, потом --resolve).
UPSTREAM_STRATEGIES = {"replace", "notify", "fork", "merge"}
# Роли источников в composite-скилле (strategy=merge): base — взят за основу;
# supplement — дополняющий источник-«suggest» (что из него вмерджено — в note/suggest).
ORIGIN_ROLES = {"base", "supplement"}
# P5.11 (ветка (B) OQ-6): человеческий вердикт по бандлу — машинно читаемая запись
# рядом со скиллом, а не строка в таблице внутри плана. verdict — что увидел
# читавший; kind различает бандл, который не вендорит НИЧЕГО (все files[].path
# пусты — провенанс-ССЫЛКИ на внешние спеки), от вендоренного: знаменатель
# «N вендоренных бандлов» иначе неоднороден, а якорь вердикта у такого бандла
# бессмысленен по конструкции. См. docs/guide/vendored-skills.md.
AUDIT_VERDICTS = {"clean", "attention", "risk"}
UPSTREAM_KINDS = {"reference-only"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Допустимые значения enum-полей frontmatter + формат версии (semver).
RISK_VALUES = {"read", "draft", "write", "external"}
ADAPTER_VALUES = {"claude", "cursor", "fable"}
LEVEL_VALUES = {"core", "foundation", "extension"}  # опц. поле level (иерархия)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
# Внутрискилловые относительные ссылки (snippets/…, references/…) в теле SKILL.md —
# должны резолвиться. ../ и .agents/.claude (раскладка проекта-потребителя) и
# прозовые URL'ы НЕ проверяем (ложные срабатывания на upstream/imported).
INTRA_LINK_RE = re.compile(r"\]\((snippets/[^)#]+|references/[^)#]+)\)")
# lean SKILL.md: тело — точка входа, детали в references/snippets (progressive disclosure).
# Мягкий порог: тело сверх него → warn (не error), подсказка вынести детали.
# См. docs/guide/skill-taxonomy.md.
LEAN_MAX_BODY_LINES = 150
# Кириллица в загружаемом каноне SKILL.md. EN-канон дешевле RU у токенайзера Claude и
# именно он попадает в контекст; русский держим в SKILL.ru.md. Жёсткий гейт на frontmatter
# `description` (резидентный ⊕ tier-0 — постоянный налог в КАЖДОМ запросе).
CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
# Пороги гейта СОВОКУПНОЙ записи листинга (резидентный tier-0, P3.2 рэтчет,
# пере-базировано на объединённое поле P3.5): first-party кап записи листинга —
# 1 536 симв (`name` + `description` + `when_to_use`, см. budget.py `_listing_entry_tokens`/
# `_listing_entry_chars` — та же формула `(description + " " + when_to_use).strip()`).
# DESC_WARN_MAX/DESC_ERROR_MAX — консервативный ВНУТРЕННИЙ запас под этим капом (не сам кап):
# DESC_ERROR_MAX — жёсткий потолок, без исключений (burn-down не спасает выше него).
# DESC_WARN_MAX — целевая норма; скиллы между WARN и ERROR легальны только если внесены в
# burn-down (унаследованный долг), иначе — error (новый долг запрещён). См.
# scripts/desc-burndown.txt. Считается ПО СУММЕ `description` + `when_to_use` — перенос
# триггер-фразы между полями эту сумму не меняет (§4 findings/P3-native-fields-context-cost).
DESC_WARN_MAX = 300
DESC_ERROR_MAX = 450
# Нижняя граница качества СОВОКУПНОЙ записи листинга как ТРИГГЕРА (P3.5, рэтчет по образцу
# верхней — см. desc-trigger-burndown.txt): запись обязана отвечать «когда звать», не только
# «что это» — фраза ищется в `description` + `when_to_use` вместе (та же сумма, что у гейта
# длины выше), а не в одном `description`, иначе перенос фразы в `when_to_use` при переносе
# создал бы ложный новый долг. Регулярка — набор устойчивых маркеров условия применения (не
# жанра скилла).
DESC_TRIGGER_RE = re.compile(
    r"(use when|activate|use for|use to|when you|whenever|trigger|use this)", re.I
)

def _load_burndown_file(repo_root_pkg, filename):
    """scripts/<filename> → set('bucket/name'), комменты(#)/пустые строки игнор.
    Общий загрузчик для desc-burndown.txt и desc-trigger-burndown.txt (тот же формат)."""
    p = repo_root_pkg / "scripts" / filename
    if not p.is_file():
        return set()
    out = set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        out.add(ln)
    return out

DESC_BURNDOWN = _load_burndown_file(root, "desc-burndown.txt")
DESC_BURNDOWN_SEEN = set()
DESC_BY_KEY = {}  # 'bucket/name' -> len(description + " " + when_to_use), протухшая запись ниже
TRIG_BURNDOWN = _load_burndown_file(root, "desc-trigger-burndown.txt")
TRIG_BURNDOWN_SEEN = set()
TRIG_HAS_TRIGGER_BY_KEY = {}  # 'bucket/name' -> bool(триггер в description+when_to_use), протухшая запись ниже


def _collect_block_scalar(lines, start):
    """Отступные строки YAML-блок-скаляра начиная с lines[start] → (строки, next_i).
    Пустые сохраняются как переносы; хвостовые обрезаются (clip-чомп). Зеркалит
    lib/skiller/common.py::_collect_block_scalar (gate должен читать как generate)."""
    block, i = [], start
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "---":
            break
        if ln.strip() == "":
            block.append("")
        elif ln.startswith((" ", "\t")):
            block.append(ln.strip())
        else:
            break
        i += 1
    while block and block[-1] == "":
        block.pop()
    return block, i


def parse_frontmatter(path):
    """Frontmatter первого ---блока, или None если блока нет/не закрыт.

    Собирает YAML-блок-скаляры (`key: |` / `key: >` + опц. чомп) и срезает BOM
    (utf-8-sig) — ИНАЧЕ `description: >` даёт gate только маркер '>', и кириллица/
    длина реального (блочного) описания не проверяются = ложно-зелёный. Читает так же,
    как generate-путь lib/skiller/common.py::parse_frontmatter (осознанный
    самодостаточный дубль: heredoc гоняется до PYTHONPATH на core, не импортируем)."""
    lines = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm, i, terminated = {}, 1, False
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            terminated = True
            break
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            if value[:1] in ("|", ">") and all(c in "+-0123456789" for c in value[1:]):
                block, i = _collect_block_scalar(lines, i + 1)
                fm[key] = (" " if value[0] == ">" else "\n").join(block)
                continue
            fm[key] = value.strip('"').strip("'")
        i += 1
    return fm if terminated else None  # unterminated block → None


def parse_inline_list(value):
    """Inline YAML list ('[a, "b", c]') -> list of strings; anything else -> []."""
    value = (value or "").strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    items = [i.strip().strip('"').strip("'") for i in value[1:-1].split(",")]
    return [i for i in items if i]


def load_upstream(skill_dir):
    f = skill_dir / "upstream.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{f.relative_to(root)}: invalid JSON: {e}")
        return {}


# --- 1. SKILL.md frontmatter ---------------------------------------------
skill_files = sorted(root.glob("skills/**/SKILL.md"))
meta_skill = root / "generate-skill/generate-skill/SKILL.md"
if meta_skill.exists():
    skill_files.append(meta_skill)

for skill_md in skill_files:
    rel = skill_md.relative_to(root)
    skill_dir = skill_md.parent
    upstream = load_upstream(skill_dir)
    fm = parse_frontmatter(skill_md)

    if fm is None:
        if upstream is not None and upstream.get("strategy") == "replace":
            errors.append(
                f"{rel}: no frontmatter and upstream strategy=replace — "
                f"frontmatter-less upstreams must use strategy=notify"
            )
        else:
            errors.append(f"{rel}: missing frontmatter block")
        continue

    required = ["name", "description"] if upstream is not None \
        else ["name", "bucket", "version", "description"]
    for field in required:
        if not fm.get(field):
            errors.append(f"{rel}: missing required frontmatter field: {field}")

    # --- 1·токены: description — EN-канон (резидентный ⊕ tier-0), без кириллицы, не раздут ---
    desc = fm.get("description", "")
    if CYRILLIC_RE.search(desc):
        errors.append(f"{rel}: frontmatter description содержит кириллицу — SKILL.md это "
                      f"EN-канон (резидентный tier-0 в КАЖДОМ запросе); русский держи в SKILL.ru.md")
    if CYRILLIC_RE.search(fm.get("name", "")):
        errors.append(f"{rel}: frontmatter name содержит кириллицу (имя скилла — EN-kebab)")
    # СОВОКУПНАЯ запись листинга (P3.5) — та же формула, что budget.py
    # `_listing_entry_tokens`/`_listing_entry_chars`: `description` + `when_to_use` одной
    # строкой (пустой when_to_use не меняет результат). Гейты длины/триггера ниже читают
    # ИМЕННО её, не голый `desc`, — иначе перенос фразы в `when_to_use` рвёт оба гейта.
    listing_text = (desc + " " + fm.get("when_to_use", "")).strip()
    # ключ бакета — из ПУТИ (не frontmatter): upstream-скиллы часто без поля `bucket`.
    _desc_parts = rel.parts
    _desc_bn = _desc_parts[1] if _desc_parts[0] == "skills" and len(_desc_parts) > 2 else None
    _desc_nm = fm.get("name", "").strip('"').strip("'") or skill_dir.name
    _desc_key = f"{_desc_bn}/{_desc_nm}" if _desc_bn and _desc_nm else None
    if _desc_key:
        DESC_BY_KEY[_desc_key] = len(listing_text)
    if len(listing_text) > DESC_ERROR_MAX:
        errors.append(f"{rel}: запись листинга (description+when_to_use) {len(listing_text)} симв "
                      f"(> {DESC_ERROR_MAX} hard-потолок) — сократи (триггеры можно ужать), "
                      f"burn-down не спасает выше {DESC_ERROR_MAX}, см. skiller budget")
    elif len(listing_text) > DESC_WARN_MAX:
        if _desc_key and _desc_key in DESC_BURNDOWN:
            DESC_BURNDOWN_SEEN.add(_desc_key)
            warnings.append(f"{rel}: запись листинга (description+when_to_use) "
                            f"{len(listing_text)} симв (> {DESC_WARN_MAX}) — унаследованный долг "
                            f"в scripts/desc-burndown.txt (легально, но сокращай при следующей "
                            f"правке)")
        else:
            errors.append(f"{rel}: запись листинга (description+when_to_use) "
                          f"{len(listing_text)} симв (> {DESC_WARN_MAX}) и НЕ в "
                          f"scripts/desc-burndown.txt — новый долг запрещён (рэтчет P3.2): "
                          f"сократи запись до <= {DESC_WARN_MAX} симв или добавь в "
                          f"desc-burndown.txt с обоснованием")

    # --- 1·триггер: запись листинга отвечает «когда звать» (P3.5 рэтчет, upstream пропускаем) ---
    if _desc_key and upstream is None:
        has_trigger = bool(DESC_TRIGGER_RE.search(listing_text))
        TRIG_HAS_TRIGGER_BY_KEY[_desc_key] = has_trigger
        if not has_trigger:
            if _desc_key in TRIG_BURNDOWN:
                TRIG_BURNDOWN_SEEN.add(_desc_key)
                warnings.append(f"{rel}: description+when_to_use без триггерной фразы (use "
                                f"when/activate/use for/…) — унаследованный долг в "
                                f"scripts/desc-trigger-burndown.txt (легально, но чини при "
                                f"следующей правке)")
            else:
                errors.append(f"{rel}: description+when_to_use без триггерной фразы (use "
                              f"when/activate/use for/use to/when you/whenever/trigger/use "
                              f"this) и НЕ в scripts/desc-trigger-burndown.txt — новый долг "
                              f"запрещён (рэтчет P3.5): опиши, КОГДА звать скилл (в description "
                              f"или when_to_use), или добавь в desc-trigger-burndown.txt с "
                              f"обоснованием")

    # --- 1a. enum / semver / bucket-vs-dir / declared snippets / intra-links ---
    parts = rel.parts
    path_bucket = parts[1] if parts[0] == "skills" and len(parts) > 2 else None

    risk = fm.get("risk", "")
    if risk and risk not in RISK_VALUES:
        errors.append(f"{rel}: risk '{risk}' не из {sorted(RISK_VALUES)}")

    level = fm.get("level", "")
    if level and level not in LEVEL_VALUES:
        errors.append(f"{rel}: level '{level}' не из {sorted(LEVEL_VALUES)}")

    bad_adapters = [a for a in parse_inline_list(fm.get("adapters", ""))
                    if a not in ADAPTER_VALUES]
    if bad_adapters:
        errors.append(f"{rel}: неизвестные adapters {bad_adapters} "
                      f"(допустимо {sorted(ADAPTER_VALUES)})")

    # version/bucket — только для локальных (upstream-скиллы держат минимальный frontmatter)
    if upstream is None:
        ver = fm.get("version", "")
        if ver and not SEMVER_RE.match(ver):
            errors.append(f"{rel}: version '{ver}' не semver (\\d+.\\d+.\\d+)")
        fm_bucket = fm.get("bucket", "")
        if path_bucket and fm_bucket and fm_bucket != path_bucket:
            errors.append(f"{rel}: frontmatter bucket '{fm_bucket}' != каталог "
                          f"'{path_bucket}'")

    # объявленные в frontmatter сниппеты должны существовать на диске
    for snip in parse_inline_list(fm.get("snippets", "")):
        if not (skill_dir / "snippets" / snip).exists():
            errors.append(f"{rel}: snippets[{snip}] объявлен, но файла нет на диске")

    # внутрискилловые ссылки snippets/… references/… в теле — должны резолвиться
    body = skill_md.read_text(encoding="utf-8")
    for m in INTRA_LINK_RE.finditer(body):
        tgt = m.group(1).split("#")[0]
        if not (skill_dir / tgt).exists():
            errors.append(f"{rel}: битая ссылка на {tgt} (файла нет)")

    # lean SKILL.md: тело (без frontmatter) сверх порога → мягкий warn.
    # upstream-скиллы (imported/external) пропускаем — их объём интенциональный (адаптированная
    # копия внешнего документа), lean-стандарт распространяется на АВТОРСКИЕ local-скиллы.
    lines = body.splitlines()
    body_start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body_start = i + 1
                break
    body_lines = len([ln for ln in lines[body_start:] if ln.strip()])
    if body_lines > LEAN_MAX_BODY_LINES and load_upstream(skill_dir) is None:
        warnings.append(f"{rel}: тело SKILL.md {body_lines} непустых строк "
                        f"(> {LEAN_MAX_BODY_LINES}) — вынеси детали в references/snippets "
                        f"(lean SKILL.md, docs/guide/skill-taxonomy.md)")

# --- 1b. desc-burndown.txt — протухшие записи (one-way рэтчет, P3.2/P3.5) -----------
# Запись легальна, только пока: скилл существует И его запись листинга
# (description+when_to_use) всё ещё > DESC_WARN_MAX. Иначе — протухла (скилл
# удалён/переименован, либо уже сокращён до нормы) — убери строку.
for _bn_key in sorted(DESC_BURNDOWN):
    if _bn_key not in DESC_BY_KEY:
        warnings.append(f"scripts/desc-burndown.txt: '{_bn_key}' — протухшая запись (скилла нет "
                        f"в реестре под этим bucket/name), убери строку")
    elif DESC_BY_KEY[_bn_key] <= DESC_WARN_MAX:
        warnings.append(f"scripts/desc-burndown.txt: '{_bn_key}' — протухшая запись (запись "
                        f"листинга уже {DESC_BY_KEY[_bn_key]} симв <= {DESC_WARN_MAX}), убери "
                        f"строку")

# --- 1b·триггер. desc-trigger-burndown.txt — протухшие записи (one-way рэтчет, P3.5) -----
# Запись легальна, только пока: скилл существует И его запись листинга
# (description+when_to_use) всё ещё без триггера.
for _tb_key in sorted(TRIG_BURNDOWN):
    if _tb_key not in TRIG_HAS_TRIGGER_BY_KEY:
        warnings.append(f"scripts/desc-trigger-burndown.txt: '{_tb_key}' — протухшая запись "
                        f"(скилла нет в реестре под этим bucket/name), убери строку")
    elif TRIG_HAS_TRIGGER_BY_KEY[_tb_key]:
        warnings.append(f"scripts/desc-trigger-burndown.txt: '{_tb_key}' — протухшая запись "
                        f"(description+when_to_use уже несёт триггерную фразу), убери строку")

# --- 1c. CORE-девятка — обязательные секции тела (P8.8, рэтчет) ------------
# Сплошной гейт по всем скиллам неисполним (замер: активационную секцию несут
# 38/160). Сужено до резидентных CORE_SKILLS (core-policy.json::skills, 9 шт.).
# (б) секция ссылок — ERROR без исключений (долг нулевой, 9/9 проходят).
# (а) активационная секция — ERROR с рэтчетом skill-sections-burndown.txt (та
# же механика, что desc-burndown.txt выше): запись легальна, пока скилл
# существует И секции у него всё ещё нет.
CORE_ACTIVATION_RE = re.compile(r"(?i)^\s*\d*\.?\s*(when\b|activate\b)")
CORE_LINKS_RE = re.compile(r"(?i)^\s*\d*\.?\s*(links|references|related skills|related)\s*$")
HEADING2_RE = re.compile(r"^##[^#](.*)$", re.MULTILINE)

def _load_sections_burndown(repo_root_pkg):
    """scripts/skill-sections-burndown.txt → set('bucket/name'); тот же формат,
    что desc-burndown.txt."""
    p = repo_root_pkg / "scripts" / "skill-sections-burndown.txt"
    if not p.is_file():
        return set()
    out = set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        out.add(ln)
    return out

SECTIONS_BURNDOWN = _load_sections_burndown(root)
SECTIONS_BURNDOWN_SEEN = set()

_core_policy_skills = []
if _core_policy_path.is_file():
    try:
        _csp = json.loads(_core_policy_path.read_text(encoding="utf-8"))
        if isinstance(_csp, dict):
            _core_policy_skills = _csp.get("skills", []) or []
    except json.JSONDecodeError:
        pass  # уже ERROR от core-policy.json-проверки выше

for _core_key in _core_policy_skills:
    _core_skill_md = root / "skills" / _core_key / "SKILL.md"
    if not _core_skill_md.is_file():
        continue  # уже ERROR от core-policy.json-проверки выше
    _core_headings = [m.group(1).strip()
                      for m in HEADING2_RE.finditer(_core_skill_md.read_text(encoding="utf-8"))]
    has_activation = any(CORE_ACTIVATION_RE.match(h) for h in _core_headings)
    has_links = any(CORE_LINKS_RE.match(h) for h in _core_headings)
    if not has_links:
        errors.append(f"skills/{_core_key}/SKILL.md: нет секции ссылок "
                      f"(##Links/References/Related skills/Related) — CORE-скилл")
    if not has_activation:
        if _core_key in SECTIONS_BURNDOWN:
            SECTIONS_BURNDOWN_SEEN.add(_core_key)
            warnings.append(f"skills/{_core_key}/SKILL.md: нет активационной секции и скилл "
                            f"в scripts/skill-sections-burndown.txt (унаследованный долг)")
        else:
            errors.append(f"skills/{_core_key}/SKILL.md: нет активационной секции и скилла "
                          f"нет в skill-sections-burndown.txt")

for _sb_key in sorted(SECTIONS_BURNDOWN):
    if _sb_key not in _core_policy_skills:
        warnings.append(f"scripts/skill-sections-burndown.txt: '{_sb_key}' — протухшая "
                        f"запись (скилла нет в CORE-девятке core-policy.json), убери строку")
    elif _sb_key not in SECTIONS_BURNDOWN_SEEN:
        warnings.append(f"scripts/skill-sections-burndown.txt: '{_sb_key}' — протухшая "
                        f"запись (скилл уже несёт активационную секцию), убери строку")

# --- 2. upstream.json -----------------------------------------------------
for up_file in sorted(root.glob("skills/**/upstream.json")) + \
        sorted((root / "generate-skill").glob("**/upstream.json")):
    rel = up_file.relative_to(root)
    skill_dir = up_file.parent
    if not (skill_dir / "SKILL.md").exists():
        errors.append(f"{rel}: upstream.json without sibling SKILL.md")
    try:
        data = json.loads(up_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{rel}: invalid JSON: {e}")
        continue

    if data.get("schema_version") != 1:
        errors.append(f"{rel}: schema_version must be 1")
    if data.get("source") not in UPSTREAM_SOURCES:
        errors.append(f"{rel}: source must be one of {sorted(UPSTREAM_SOURCES)}")
    if data.get("strategy") not in UPSTREAM_STRATEGIES:
        errors.append(f"{rel}: strategy must be one of {sorted(UPSTREAM_STRATEGIES)}")
    # fork: форк-скилл с локальными правками. review_pending=true — апстрим разошёлся с
    # зеркалом, нужна ручная доработка → ГЕЙТ: блокируем валидацию (и тем самым registry/релиз),
    # пока агент не перенесёт дифф и не сделает update-upstreams.sh --resolve.
    if data.get("strategy") == "fork":
        rp = data.get("review_pending")
        if rp is not None and not isinstance(rp, bool):
            errors.append(f"{rel}: review_pending must be a boolean")
        if rp is True:
            errors.append(
                f"{rel}: review_pending=true — upstream форка разошёлся с зеркалом; "
                f"сверь diff и перенеси правки в SKILL.md, затем "
                f"scripts/update-upstreams.sh --resolve --skill <id>")
        lr = data.get("last_review", "")
        if lr and not DATE_RE.match(lr):
            errors.append(f"{rel}: last_review must be YYYY-MM-DD or empty")
    # merge: композит из ≥2 внешних источников. origins[] фиксирует провенанс с
    # ролями (base — взят за основу; supplement/«suggest» — что дополнительно
    # вмерджено). Синк ручной: на дрейфе любого origin merge.review_pending=true
    # блокирует валидацию (и registry/релиз), пока агент не пере-мерджит и не
    # снимет гейт (scripts/update-upstreams.sh --resolve).
    if data.get("strategy") == "merge":
        origins = data.get("origins")
        if not isinstance(origins, list) or len(origins) < 2:
            errors.append(f"{rel}: strategy=merge требует origins[] из ≥2 источников "
                          f"(base + ≥1 supplement)")
            origins = []
        roles = []
        for k, org in enumerate(origins):
            if not isinstance(org, dict):
                errors.append(f"{rel}: origins[{k}] must be an object")
                continue
            for key in ("repo", "role", "url", "sha256", "fetched_at"):
                if not org.get(key):
                    errors.append(f"{rel}: origins[{k}] missing key: {key}")
            role = org.get("role", "")
            if role and role not in ORIGIN_ROLES:
                errors.append(f"{rel}: origins[{k}].role '{role}' не из "
                              f"{sorted(ORIGIN_ROLES)}")
            roles.append(role)
            of = org.get("fetched_at", "")
            if of and not DATE_RE.match(of):
                errors.append(f"{rel}: origins[{k}].fetched_at must be YYYY-MM-DD")
        if origins and roles.count("base") != 1:
            errors.append(f"{rel}: strategy=merge требует РОВНО один origin role=base")
        if origins and "supplement" not in roles:
            errors.append(f"{rel}: strategy=merge требует ≥1 origin role=supplement")
        merge = data.get("merge") or {}
        if not isinstance(merge, dict):
            errors.append(f"{rel}: merge must be an object")
            merge = {}
        rp = merge.get("review_pending")
        if rp is not None and not isinstance(rp, bool):
            errors.append(f"{rel}: merge.review_pending must be a boolean")
        if rp is True:
            errors.append(
                f"{rel}: merge.review_pending=true — один из origins разошёлся с "
                f"зеркалом; пере-мерджи источники в SKILL.md, затем "
                f"scripts/update-upstreams.sh --resolve --skill <id>")
        mlr = merge.get("last_review", "")
        if mlr and not DATE_RE.match(mlr):
            errors.append(f"{rel}: merge.last_review must be YYYY-MM-DD or empty")
    elif data.get("origins") is not None:
        errors.append(f"{rel}: origins[] допустим только при strategy=merge")
    if data.get("source") == "file":
        warnings.append(f"{rel}: source=file is for local fixtures/tests only")

    files = data.get("files")
    if not isinstance(files, list) or not files:
        errors.append(f"{rel}: files must be a non-empty array")
        continue
    for i, entry in enumerate(files):
        for key in ("path", "url", "sha256", "fetched_at"):
            if key not in entry:
                errors.append(f"{rel}: files[{i}] missing key: {key}")
        path = entry.get("path", "")
        if path:
            target = (skill_dir / path).resolve()
            if not str(target).startswith(str(skill_dir.resolve())):
                errors.append(f"{rel}: files[{i}].path escapes skill dir: {path}")
            elif not target.exists():
                errors.append(f"{rel}: files[{i}].path does not exist: {path}")
        fetched = entry.get("fetched_at", "")
        if fetched and not DATE_RE.match(fetched):
            errors.append(f"{rel}: files[{i}].fetched_at must be YYYY-MM-DD or empty")

    # body_path (P7.3, thin-navigator): опционально — путь (относительно skill_dir),
    # где реально лежит апстримное тело, когда SKILL.md стал локально написанным
    # навигатором, а НЕ зеркалом апстрима (см. update-upstreams.sh, docs/guide/
    # upstream-sync.md). Аддитивное поле; отсутствие = тело в SKILL.md (back-compat).
    # Он ДОЛЖЕН совпадать с одной из files[].path — иначе update-upstreams.sh не
    # будет считать sha/дрейф по заявленному телу (тихая дыра в отслеживании).
    body_path = data.get("body_path")
    if body_path is not None:
        if not isinstance(body_path, str) or not body_path:
            errors.append(f"{rel}: body_path must be a non-empty string")
        else:
            bp_target = (skill_dir / body_path).resolve()
            if not str(bp_target).startswith(str(skill_dir.resolve())):
                errors.append(f"{rel}: body_path escapes skill dir: {body_path}")
            elif not bp_target.exists():
                errors.append(f"{rel}: body_path does not exist: {body_path}")
            tracked_paths = {f.get("path") for f in files if isinstance(f, dict)}
            if body_path not in tracked_paths:
                errors.append(
                    f"{rel}: body_path '{body_path}' is not tracked in files[] — "
                    f"update-upstreams.sh would not check its sha/drift")
            # strategy=replace autowrites files[].path on --apply (unlike fork/merge,
            # which only stage an incoming copy for manual review) — a stray SKILL.md
            # entry there would silently clobber the hand-authored navigator.
            if data.get("strategy") == "replace" and "SKILL.md" in tracked_paths \
                    and body_path != "SKILL.md":
                errors.append(
                    f"{rel}: body_path set (thin-navigator) but files[] also tracks "
                    f"SKILL.md under strategy=replace — update-upstreams.sh --apply "
                    f"would overwrite the hand-authored navigator; drop the SKILL.md "
                    f"files[] entry")

    # --- audit: человеческий вердикт по бандлу (P5.11, ветка (B) OQ-6) --------
    # ОТСУТСТВИЕ блока ловит НЕ этот гейт, а триаж-ступень update-upstreams.sh
    # --check (находка AUDIT_MISSING): «бандла без вердикта не бывает» — правило
    # раздачи, а не структурная поломка файла. Здесь проверяется ФОРМА записи:
    # молчаливый attention неотличим от опечатки, вердикт без адреса читавшего
    # бессмысленен, а вердикт без собственного якоря не может протухнуть.
    entry_paths = [entry.get("path", "") for entry in files if isinstance(entry, dict)]
    ref_only = bool(entry_paths) and not any(entry_paths)
    kind = data.get("kind")
    if kind is not None and kind not in UPSTREAM_KINDS:
        errors.append(f"{rel}: kind must be one of {sorted(UPSTREAM_KINDS)}")
    elif kind == "reference-only" and not ref_only:
        errors.append(f"{rel}: kind=reference-only, но files[] несёт локальные "
                      f"зеркала (непустой path) — признак машинный, не мнение")
    elif kind is None and ref_only:
        errors.append(f"{rel}: все files[].path пусты (бандл не вендорит ничего) — "
                      f"объяви kind: \"reference-only\", иначе класс машинно "
                      f"неотличим от вендоренного")

    audit = data.get("audit")
    if audit is not None and not isinstance(audit, dict):
        errors.append(f"{rel}: audit must be an object")
    elif isinstance(audit, dict):
        verdict = audit.get("verdict")
        if verdict not in AUDIT_VERDICTS:
            errors.append(f"{rel}: audit.verdict must be one of "
                          f"{sorted(AUDIT_VERDICTS)}")
        at = audit.get("at", "")
        if not at or not DATE_RE.match(at):
            errors.append(f"{rel}: audit.at must be YYYY-MM-DD (дата чтения бандла)")
        if not audit.get("by"):
            errors.append(f"{rel}: audit.by missing — адрес читавшего бандл "
                          f"(<PLAN-ID> <item> либо дата ручного чтения); запись "
                          f"без адреса ничего не значит")
        if verdict in ("attention", "risk") and not audit.get("note"):
            errors.append(f"{rel}: audit.note обязателен при verdict={verdict} — "
                          f"молчаливый вердикт неотличим от опечатки")
        if ref_only:
            if "upstream_sha" in audit:
                errors.append(f"{rel}: audit.upstream_sha при kind=reference-only "
                              f"обязан быть опущен — якорить нечего, зеркал нет")
        elif not SHA256_RE.match(audit.get("upstream_sha", "")):
            errors.append(f"{rel}: audit.upstream_sha must be a sha256 hex digest — "
                          f"без собственного якоря вердикт не может протухнуть "
                          f"(update-upstreams.sh: AUDIT_STALE)")

# --- 3. profiles/*.json ---------------------------------------------------
# Канон таксономии — core.project.PROJECT_TYPES; здесь самодостаточный дубль
# (heredoc гоняется до PYTHONPATH на core — осознанно не импортируем; держать
#  в синхроне с core/project.py). Ссылки на пресеты/паки/mcp живут в пакете
# harness — проверяем только если он на месте (монорепо), иначе graceful skip.
PROJECT_TYPE_IDS = {
    "obsidian-vault", "laravel-project", "php-package", "dart-flutter",
    "python-backend", "node-frontend", "node-package", "standalone",
}
AA_MODES = {"strict", "permissive", "bypass", "off"}
MEM_MODES = {"file", "federation", "agentmemory", "maind", "off"}
MODEL_TIERS = {"inherit", "opus", "sonnet", "haiku"}
hc_dir = repo_root / "packages" / "harness" / "configs" / "claude-code"
profile_names = set()
profiles_dir = root / "profiles"
if profiles_dir.is_dir():
    for prof in sorted(profiles_dir.glob("*.json")):
        rel = prof.relative_to(root)
        try:
            data = json.loads(prof.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            errors.append(f"{rel}: invalid JSON: {e}")
            continue
        profile_names.add(prof.stem)
        if data.get("name") != prof.stem:
            errors.append(f"{rel}: name must match filename ({prof.stem})")
        buckets = data.get("buckets")
        if not isinstance(buckets, list) or not buckets:
            errors.append(f"{rel}: buckets must be a non-empty array")
        elif buckets != ["*"]:
            for b in buckets:
                if not (root / "skills" / b).is_dir():
                    errors.append(f"{rel}: unknown bucket: {b}")
        # --- расширенные опц. ключи: agent_pack/presets/mcp/hooks/model_tiers ---
        pack = data.get("agent_pack")
        if pack is not None and not isinstance(pack, (str, list)):
            errors.append(f"{rel}: agent_pack must be a string or list")
        packs = [pack] if isinstance(pack, str) else (pack if isinstance(pack, list) else [])
        if hc_dir.is_dir():
            for pk in packs:
                if not (hc_dir / "agent-packs" / str(pk) / "pack.json").exists():
                    errors.append(f"{rel}: agent_pack '{pk}' — нет pack.json в harness")
            for preset in data.get("harness_presets", []) or []:
                if not (hc_dir / f"settings.{preset}.json").exists():
                    errors.append(f"{rel}: harness_preset '{preset}' — нет settings.{preset}.json")
            for srv in data.get("mcp", []) or []:
                if not (hc_dir / "mcp" / f"{srv}.json").exists():
                    errors.append(f"{rel}: mcp '{srv}' — нет mcp/{srv}.json")
        hooks = data.get("hooks") or {}
        if not isinstance(hooks, dict):
            errors.append(f"{rel}: hooks must be an object")
        else:
            aa = hooks.get("auto_approve")
            if aa is not None and aa not in AA_MODES:
                errors.append(f"{rel}: hooks.auto_approve '{aa}' не из {sorted(AA_MODES)}")
            mem = hooks.get("memory")
            if mem is not None and mem not in MEM_MODES:
                errors.append(f"{rel}: hooks.memory '{mem}' не из {sorted(MEM_MODES)}")
        tiers = data.get("model_tiers") or {}
        if not isinstance(tiers, dict):
            errors.append(f"{rel}: model_tiers must be an object")
        else:
            for role, tier in tiers.items():
                if tier not in MODEL_TIERS:
                    errors.append(f"{rel}: model_tiers.{role} '{tier}' "
                                  f"не из {sorted(MODEL_TIERS)}")
    # --- 3b. покрытие: каждый id таксономии имеет profiles/<id>.json ---
    missing = PROJECT_TYPE_IDS - profile_names
    if missing:
        errors.append(f"profiles/: нет профилей для типов {sorted(missing)} "
                      f"(см. core.project.PROJECT_TYPES)")

# --- 4. skills.json -------------------------------------------------------
reg = root / "skills.json"
if reg.exists():
    try:
        json.loads(reg.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"skills.json: invalid JSON: {e}")
else:
    errors.append("skills.json not found")

# --- 5. snippet manifests -------------------------------------------------
for manifest in sorted(root.glob("skills/**/snippets/index.json")):
    rel = manifest.relative_to(root)
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{rel}: invalid JSON: {e}")
        continue
    for s in data.get("snippets", []):
        f = manifest.parent / s.get("file", "")
        if not f.exists():
            errors.append(f"{rel}: missing snippet: {s.get('file')}")

# --- 5b. evals/ (поведенческие тесты скиллов) -------------------------------
# Структурная проверка имеющихся evals.json/pressure.json/triggers.json (если
# заведены) + сводка покрытия. Глубокая семантика (типы ассершенов, прогон) — в
# lib/skiller/eval.py + tests/test_eval.py; здесь только мягкий гейт формата.
# Покрытие — ОДНОЙ строкой (не per-skill warning), чтобы не зашумлять вывод.
def _check_cases(node, where, key):
    cases = node.get(key)
    if not isinstance(cases, list) or not cases:
        errors.append(f"{where}: '{key}' должен быть непустым массивом")
        return
    ids = set()
    for k, c in enumerate(cases):
        w = f"{where}.{key}[{k}]"
        if not isinstance(c, dict):
            errors.append(f"{w}: кейс должен быть объектом"); continue
        cid = c.get("id")
        if cid is None:
            errors.append(f"{w}: нет id")
        elif cid in ids:
            errors.append(f"{w}: дубликат id {cid!r}")
        else:
            ids.add(cid)
        if not c.get("prompt"):
            errors.append(f"{w}: нет непустого prompt")
        for j, a in enumerate(c.get("assertions", []) or []):
            if not isinstance(a, dict) or not a.get("type") or "value" not in a:
                errors.append(f"{w}.assertions[{j}]: нужен объект с type+value")

local_total = local_with_evals = 0
for skill_md in sorted(root.glob("skills/*/*/SKILL.md")):
    sd = skill_md.parent
    if (sd / "upstream.json").exists():
        continue                       # eval-стандарт — на авторские (не upstream)
    local_total += 1
    ev = sd / "evals" / "evals.json"
    if ev.exists():
        local_with_evals += 1
for ev_file in sorted(root.glob("skills/*/*/evals/evals.json")):
    rel = ev_file.relative_to(root)
    try:
        data = json.loads(ev_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{rel}: invalid JSON: {e}"); continue
    if not isinstance(data, dict) or not data.get("skill"):
        errors.append(f"{rel}: нужен объект с полем skill")
    else:
        _check_cases(data, str(rel), "cases")
for pr_file in sorted(root.glob("skills/*/*/evals/pressure.json")):
    rel = pr_file.relative_to(root)
    try:
        data = json.loads(pr_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{rel}: invalid JSON: {e}"); continue
    if not isinstance(data, dict) or not data.get("skill"):
        errors.append(f"{rel}: нужен объект с полем skill")
    else:
        _check_cases(data, str(rel), "scenarios")
for tr_file in sorted(root.glob("skills/*/*/evals/triggers.json")):
    rel = tr_file.relative_to(root)
    try:
        data = json.loads(tr_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{rel}: invalid JSON: {e}"); continue
    for key in ("should_trigger", "should_not"):
        v = data.get(key) if isinstance(data, dict) else None
        if not isinstance(v, list) or not v:
            errors.append(f"{rel}: '{key}' должен быть непустым массивом")

# --- 5c. Pressure-кейсы обязательны при evals.json + покрытие triggers[] (P8.8) --
# Долг нулевой (замер: 4/4 evals.json уже несут pressure.json) ⇒ ERROR без рэтчета.
# triggers[]-покрытие — WARNING (поле новое, у существующих сценариев его пока нет).
for skill_md in sorted(root.glob("skills/*/*/SKILL.md")):
    sd = skill_md.parent
    if (sd / "upstream.json").exists():
        continue
    ev_p8 = sd / "evals" / "evals.json"
    if not ev_p8.exists():
        continue
    rel_sd = sd.relative_to(root)
    pr_p8 = sd / "evals" / "pressure.json"
    if not pr_p8.exists():
        errors.append(f"{rel_sd}: есть evals.json, нет pressure.json")
        continue
    try:
        pr_p8_data = json.loads(pr_p8.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        continue  # уже ERROR от 5b выше
    p8_scenarios = pr_p8_data.get("scenarios") if isinstance(pr_p8_data, dict) else None
    if not isinstance(p8_scenarios, list) or not p8_scenarios:
        errors.append(f"{rel_sd}: есть evals.json, pressure.json без сценариев")
        continue
    tr_p8 = sd / "evals" / "triggers.json"
    if not tr_p8.exists():
        continue
    try:
        tr_p8_data = json.loads(tr_p8.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        continue  # уже ERROR от 5b выше
    should_trigger = tr_p8_data.get("should_trigger") if isinstance(tr_p8_data, dict) else None
    if not isinstance(should_trigger, list):
        continue
    covered = set()
    for _sc in p8_scenarios:
        if isinstance(_sc, dict):
            covered.update(t for t in (_sc.get("triggers") or []) if isinstance(t, str))
    for q in should_trigger:
        if q not in covered:
            warnings.append(f"{rel_sd}: should_trigger {q!r} не покрыт ни одним "
                            f"pressure-сценарием (поле triggers[])")

# --- 5d. Тонкие проекции не дублируют канон (P8.8, D50/D89) -----------------
# Пары «проекция↔канон» из publication-lock.json (repository-bootstrap), при
# его отсутствии — configs/repository-bootstrap-skills.json. Проекции есть,
# источника нет ⇒ ERROR (противоречивое состояние); ни проекций, ни источника
# ⇒ проверка молча пропускается (standalone-раскладка пакета).
PROJECTION_MAX_BODY_LINES = 15
_proj_lock = root / "adapters" / "repository-bootstrap" / "publication-lock.json"
_proj_lock_fallback = root / "configs" / "repository-bootstrap-skills.json"
_proj_glob = list(repo_root.glob(".claude/skills/*/SKILL.md")) + \
             list(repo_root.glob(".agents/skills/*/SKILL.md"))
if _proj_glob:
    _proj_source = _proj_lock if _proj_lock.is_file() else (
        _proj_lock_fallback if _proj_lock_fallback.is_file() else None)
    if _proj_source is None:
        errors.append(f"проекции ({len(_proj_glob)}) есть, но нет объявленного источника "
                      f"пар (adapters/repository-bootstrap/publication-lock.json или "
                      f"configs/repository-bootstrap-skills.json)")
    else:
        try:
            _proj_data = json.loads(_proj_source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as _pe:
            errors.append(f"{_proj_source.relative_to(repo_root)}: invalid JSON: {_pe}")
            _proj_data = {}
        _proj_records = _proj_data.get("records", []) if isinstance(_proj_data, dict) else []
        for _pr in _proj_records:
            _p_target = _pr.get("target")
            _p_canon = _pr.get("canonical_en")
            if not _p_target or not _p_canon:
                continue
            _p_path = repo_root / _p_target
            if not _p_path.is_file():
                continue  # проекция не сгенерена — вне scope P8.8 (не гейт генератора)
            _p_text = _p_path.read_text(encoding="utf-8")
            _p_lines = _p_text.splitlines()
            _p_start = 0
            if _p_lines and _p_lines[0].strip() == "---":
                for _i in range(1, len(_p_lines)):
                    if _p_lines[_i].strip() == "---":
                        _p_start = _i + 1
                        break
            _p_body = [ln for ln in _p_lines[_p_start:] if ln.strip()]
            if len(_p_body) > PROJECTION_MAX_BODY_LINES:
                errors.append(f"{_p_target}: тело {len(_p_body)} строк "
                              f"(> {PROJECTION_MAX_BODY_LINES}) — проекция дублирует "
                              f"канон {_p_canon}")
            if _p_canon not in _p_text:
                errors.append(f"{_p_target}: нет ссылки на канон {_p_canon}")
            _p_canon_path = repo_root / _p_canon
            if _p_canon_path.is_file():
                _p_canon_headings = {m.group(1).strip() for m in
                                     HEADING2_RE.finditer(_p_canon_path.read_text(encoding="utf-8"))}
                _p_proj_headings = {m.group(1).strip() for m in HEADING2_RE.finditer(_p_text)}
                _p_dup = _p_canon_headings & _p_proj_headings
                if _p_dup:
                    errors.append(f"{_p_target}: проекция воспроизводит заголовки канона "
                                  f"{sorted(_p_dup)} — тело <проекция> дублирует канон {_p_canon}")

# --- 6. buckets.json --------------------------------------------------------
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
bucket_dirs = sorted(d.name for d in (root / "skills").iterdir() if d.is_dir())
bucket_meta = {}
meta_file = root / "buckets.json"
if not meta_file.exists():
    errors.append("buckets.json not found")
else:
    try:
        bucket_meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"buckets.json: invalid JSON: {e}")
        bucket_meta = {}
    for b in bucket_dirs:
        if b not in bucket_meta:
            errors.append(f"buckets.json: missing entry for bucket: {b}")
    for b, meta in bucket_meta.items():
        # Alias-бакет (P7.5, слияния бакетов — механизм без применения, D14): метаданные-
        # запись БЕЗ skills/<bucket>, `alias_of` указывает на целевой бакет. Не orphan.
        is_alias = isinstance(meta, dict) and meta.get("alias_of")
        if b not in bucket_dirs and not is_alias:
            errors.append(f"buckets.json: entry without skills/ dir: {b}")
        if is_alias and meta["alias_of"] not in bucket_dirs:
            errors.append(f"buckets.json: {b}: alias_of указывает на несуществующий "
                          f"бакет: {meta['alias_of']}")
        if not (isinstance(meta, dict) and meta.get("description")):
            errors.append(f"buckets.json: {b}: description must be non-empty")


# --- 6b. presets/*.json (именованные кластеры скиллов) ----------------------
# Пресет = группа скиллов для vendor-выборки: {name, description, extends?,
# buckets?, include?}. resolve_skillset раскрывает presets → buckets/include.
# Проверяем: name==файл (kebab), непустой description, extends/buckets/include
# резолвятся, циклов в extends нет. Каталог опционален (graceful skip).
presets_dir = root / "presets"
if presets_dir.is_dir():
    skill_names, skill_paths = set(), set()
    for skill_md in skill_files:
        fm = parse_frontmatter(skill_md) or {}
        nm = (fm.get("name", "") or "").strip().strip('"').strip("'")
        if nm:
            skill_names.add(nm)
        parts = skill_md.parent.relative_to(root).parts
        if len(parts) >= 3 and parts[0] == "skills":
            skill_paths.add("/".join(parts[1:]))  # bucket/rel
    preset_names = {p.stem for p in presets_dir.glob("*.json")}
    preset_extends = {}
    for pf in sorted(presets_dir.glob("*.json")):
        rel = pf.relative_to(root)
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            errors.append(f"{rel}: invalid JSON: {e}")
            continue
        if data.get("name") != pf.stem:
            errors.append(f"{rel}: name must match filename ({pf.stem})")
        if not KEBAB_RE.match(pf.stem):
            errors.append(f"{rel}: preset name must be kebab-case")
        if not data.get("description"):
            errors.append(f"{rel}: description must be non-empty")
        ext = data.get("extends", []) or []
        if not isinstance(ext, list):
            errors.append(f"{rel}: extends must be a list")
            ext = []
        for parent in ext:
            if parent not in preset_names:
                errors.append(f"{rel}: extends unknown preset '{parent}'")
        preset_extends[pf.stem] = [e for e in ext if e in preset_names]
        for b in data.get("buckets", []) or []:
            if b not in bucket_dirs:
                errors.append(f"{rel}: unknown bucket '{b}'")
        for tok in data.get("include", []) or []:
            if tok not in skill_names and tok not in skill_paths:
                errors.append(f"{rel}: include '{tok}' не резолвится в скилл "
                              f"(нужно имя или bucket/rel)")
    # циклы в extends (iterative DFS, white/grey/black)
    PW, PG, PB = 0, 1, 2
    pcol = {n: PW for n in preset_extends}
    for pstart in sorted(preset_extends):
        if pcol[pstart] != PW:
            continue
        pstack = [(pstart, iter(preset_extends.get(pstart, [])))]
        pcol[pstart] = PG
        ppath = [pstart]
        while pstack:
            pnode, pit = pstack[-1]
            padv = False
            for pdep in pit:
                if pcol.get(pdep) == PG:
                    cyc = ppath[ppath.index(pdep):] + [pdep]
                    errors.append(f"presets: extends cycle: {' -> '.join(cyc)}")
                elif pcol.get(pdep) == PW:
                    pcol[pdep] = PG
                    ppath.append(pdep)
                    pstack.append((pdep, iter(preset_extends.get(pdep, []))))
                    padv = True
                    break
            if not padv:
                pcol[pnode] = PB
                ppath.pop()
                pstack.pop()


# --- 7. plugin manifests (.claude-plugin/) ----------------------------------
def expected_skills_dirs(plugin_root):
    """Same algorithm as sync.sh: parents of skill dirs, ./-prefixed."""
    dirs = set()
    for skill_md in plugin_root.rglob("SKILL.md"):
        rel = skill_md.parent.parent.relative_to(plugin_root)
        dirs.add("./" if str(rel) == "." else f"./{rel.as_posix()}")
    return sorted(dirs)


STALE_HINT = "run 'skiller registry' (or ./sync.sh --update-registry)"
# P1.2 (D31): a private/source-only bucket (repository-bootstrap) never gets an ordinary
# `.claude-plugin/plugin.json` — `publication.py`'s catalog builder excludes it from unit
# construction outright, so validating one here would demand an artifact the generator never
# produces. Same `private_source_only` flag `skillset.py`/`publication.py` already read.
plugin_roots = {b: root / "skills" / b for b in bucket_dirs
               if not (isinstance(bucket_meta.get(b), dict)
                       and bucket_meta[b].get("private_source_only"))}
plugin_roots["generate-skill"] = root / "generate-skill"
# Management plugin (командное лицо CLI, без скиллов) — валидируем как обычный плагин,
# если каталог есть; registry.py добавляет его в marketplace.json синхронно.
if (root / "skm" / ".claude-plugin" / "plugin.json").exists():
    plugin_roots["skm"] = root / "skm"

# Соседние пакеты монорепо (packages/<name>, кроме swissknifeman) — командные/MCP-плагины
# без skills-поля; их plugin.json — источник истины, registry добавляет их в marketplace.
# Здесь только собираем их имена для match-проверки (полная валидация — в их пакете).
sibling_plugin_names = []
pkgs_dir = repo_root / "packages"
if root != repo_root and pkgs_dir.is_dir():
    for pkg in sorted(pkgs_dir.iterdir()):
        if not pkg.is_dir() or pkg.name == root.name:
            continue
        pj = pkg / ".claude-plugin" / "plugin.json"
        if pj.exists():
            try:
                sibling_plugin_names.append(
                    json.loads(pj.read_text(encoding="utf-8")).get("name", pkg.name))
            except json.JSONDecodeError as e:
                errors.append(f"packages/{pkg.name}/.claude-plugin/plugin.json: invalid JSON: {e}")

for plugin_name, plugin_root in sorted(plugin_roots.items()):
    pj = plugin_root / ".claude-plugin" / "plugin.json"
    rel = pj.relative_to(root)
    if not pj.exists():
        errors.append(f"{rel}: missing ({STALE_HINT})")
        continue
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{rel}: invalid JSON: {e}")
        continue
    if data.get("name") != plugin_name:
        errors.append(f"{rel}: name must be '{plugin_name}'")
    if not KEBAB_RE.match(data.get("name", "")):
        errors.append(f"{rel}: name must be kebab-case")
    if not data.get("description"):
        errors.append(f"{rel}: description must be non-empty")
    declared = data.get("skills", [])
    declared = [declared] if isinstance(declared, str) else declared
    if sorted(declared) != expected_skills_dirs(plugin_root):
        errors.append(f"{rel}: stale skills dirs ({STALE_HINT})")

mp_file = repo_root / ".claude-plugin" / "marketplace.json"
if not mp_file.exists():
    errors.append(f".claude-plugin/marketplace.json: missing ({STALE_HINT})")
else:
    try:
        mp = json.loads(mp_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f".claude-plugin/marketplace.json: invalid JSON: {e}")
        mp = {}
    if mp:
        if mp.get("name") != "swissknifeman":
            errors.append(".claude-plugin/marketplace.json: name must be 'swissknifeman'")
        if not mp.get("owner", {}).get("name"):
            errors.append(".claude-plugin/marketplace.json: owner.name must be set")
        entries = mp.get("plugins", [])
        names = [p.get("name", "") for p in entries]
        if len(names) != len(set(names)):
            errors.append(".claude-plugin/marketplace.json: duplicate plugin names")
        # Курируемые (не-бакетные) плагины: каталога-плагина на диске НЕТ — плагин ссылается на
        # скиллы из РАЗНЫХ бакетов через skills[] (source:"./"). Имя мирроит config.CORE_PLUGIN;
        # сами пути skills[] проверяем на существование ниже. (Дубль имени — stdlib-only heredoc.)
        curated_plugin_names = ["core"]
        expected_names = list(plugin_roots) + sibling_plugin_names + curated_plugin_names
        if sorted(names) != sorted(expected_names):
            errors.append(
                f".claude-plugin/marketplace.json: plugins must match dirs on disk "
                f"({STALE_HINT})")
        for p in entries:
            src = p.get("source", "")
            # source-пути относительны корня репо (./packages/skiller/... или ./ для curated)
            if not (repo_root / src).is_dir():
                errors.append(
                    f".claude-plugin/marketplace.json: {p.get('name')}: "
                    f"source dir not found: {src}")
            if not p.get("description"):
                errors.append(
                    f".claude-plugin/marketplace.json: {p.get('name')}: "
                    f"description must be non-empty")
            # курируемый плагин: каждый путь skills[] (от корня репо) должен существовать
            if p.get("name") in curated_plugin_names:
                for sk in (p.get("skills") or []):
                    if not (repo_root / sk).is_dir():
                        errors.append(
                            f".claude-plugin/marketplace.json: {p.get('name')}: "
                            f"skills path not found: {sk} ({STALE_HINT})")

# --- 7b. no skills nested inside a skill dir ---------------------------------
# Claude Code discovers a dir with SKILL.md as a leaf skill; SKILL.md deeper
# inside it is silently invisible to plugin discovery.
for skill_md in skill_files:
    d = skill_md.parent
    nested = [p for p in d.rglob("SKILL.md") if p != skill_md]
    for p in nested:
        errors.append(
            f"{p.relative_to(root)}: nested inside skill "
            f"'{d.relative_to(root)}' — invisible to plugin discovery; "
            f"flatten it (e.g. '{d.name}-{p.parent.name}' next to '{d.name}')")

# --- 8. skill-name uniqueness ------------------------------------------------
# Plugin namespace flattens per plugin: dup inside a bucket = error.
# Across buckets namespacing keeps it legal, but vendoring modes collide: warn.
by_bucket = {}
for skill_md in skill_files:
    fm = parse_frontmatter(skill_md) or {}
    name = fm.get("name", "")
    if not name:
        continue
    bucket = skill_md.relative_to(root).parts[1] \
        if skill_md.relative_to(root).parts[0] == "skills" else "generate-skill"
    by_bucket.setdefault(bucket, {}).setdefault(name, []).append(
        str(skill_md.relative_to(root)))
seen_names = {}
for bucket, names in sorted(by_bucket.items()):
    for name, paths in sorted(names.items()):
        if len(paths) > 1:
            errors.append(
                f"duplicate skill name '{name}' in bucket '{bucket}': "
                f"{', '.join(paths)}")
        seen_names.setdefault(name, []).append(bucket)
for name, in_buckets in sorted(seen_names.items()):
    if len(in_buckets) > 1:
        warnings.append(
            f"skill name '{name}' appears in buckets {', '.join(in_buckets)} — "
            f"legal with plugin namespaces, collides in vendoring modes")

# --- 9. dependency graph (requires / produces_for) ---------------------------
# Edge names are frontmatter `name` values. Cycles are checked over `requires`
# only: an `A requires B` + `B produces_for A` pair is a normal complementary
# link, not a cycle.
graph_requires = {}
graph_produces = {}
name_to_rel = {}
for skill_md in skill_files:
    rel = skill_md.relative_to(root)
    fm = parse_frontmatter(skill_md) or {}
    name = fm.get("name", "").strip().strip('"').strip("'")
    if not name:
        continue
    name_to_rel.setdefault(name, str(rel))
    for key, store in (("requires", graph_requires), ("produces_for", graph_produces)):
        raw = fm.get(key, "").strip()
        deps = parse_inline_list(raw)
        if raw and raw != "[]" and not deps:
            warnings.append(
                f"{rel}: {key} is set but not an inline list ('{raw}') — "
                f"use '[a, b]' syntax; multiline YAML lists are not parsed")
        store[name] = deps

all_names = set(graph_requires) | set(graph_produces)
for name in sorted(all_names):
    src = name_to_rel[name]
    for key, store in (("requires", graph_requires), ("produces_for", graph_produces)):
        for dep in store.get(name, []):
            if dep == name:
                errors.append(f"{src}: {key} references itself")
            elif dep not in all_names:
                errors.append(f"{src}: {key} unknown skill '{dep}'")

# Cycle detection over `requires` (iterative DFS, white/grey/black colouring)
WHITE, GREY, BLACK = 0, 1, 2
colour = {n: WHITE for n in all_names}
for start in sorted(all_names):
    if colour[start] != WHITE:
        continue
    stack = [(start, iter(graph_requires.get(start, [])))]
    colour[start] = GREY
    path = [start]
    while stack:
        node, it = stack[-1]
        advanced = False
        for dep in it:
            if dep not in all_names:
                continue
            if colour[dep] == GREY:
                cycle = path[path.index(dep):] + [dep]
                errors.append(f"requires cycle: {' -> '.join(cycle)}")
            elif colour[dep] == WHITE:
                colour[dep] = GREY
                path.append(dep)
                stack.append((dep, iter(graph_requires.get(dep, []))))
                advanced = True
                break
        if not advanced:
            colour[node] = BLACK
            path.pop()
            stack.pop()

# --- 10. internal project skills (.claude/skills/) ---------------------------
# Внутренние скиллы разработки реестра: НЕ экспортируются и НЕ попадают в
# skills.json — линтуются мягко (только name+description, без полей реестра).
registry_names = set(seen_names)
# Локальные dev-скиллы могут жить и в .claude/skills пакета, и в КОРНЕ МОНОРЕПО
# (перенесены туда ради видимости из корня). Линтуем оба места (standalone-safe).
_skill_roots = [root]
_mono = root.parent.parent          # packages/<pkg> → корень монорепо
if _mono != root and (_mono / ".claude" / "skills").is_dir():
    _skill_roots.append(_mono)
_internal_skills = []
for _sr in _skill_roots:
    for _p in sorted(_sr.glob(".claude/skills/*/SKILL.md")):
        _internal_skills.append((_sr, _p))
for _sr, skill_md in _internal_skills:
    rel = skill_md.relative_to(_sr)
    fm = parse_frontmatter(skill_md)
    if fm is None:
        errors.append(f"{rel}: missing frontmatter block")
        continue
    name = fm.get("name", "").strip().strip('"').strip("'")
    if not name or not fm.get("description"):
        errors.append(f"{rel}: internal skill needs name + description")
        continue
    if not KEBAB_RE.match(name):
        errors.append(f"{rel}: name must be kebab-case")
    if name != skill_md.parent.name:
        errors.append(f"{rel}: name '{name}' must match dir '{skill_md.parent.name}'")
    if name in registry_names:
        warnings.append(
            f"{rel}: internal skill name '{name}' collides with a registry skill")

# --- 10b. slash-команды плагина skm (frontmatter) ----------------------------
# Командное лицо CLI: каждый skm/commands/*.md должен иметь frontmatter с
# непустым description (иначе команда без подписи в меню Claude Code).
for cmd_md in sorted(root.glob("skm/commands/*.md")):
    rel = cmd_md.relative_to(root)
    fm = parse_frontmatter(cmd_md)
    if fm is None:
        errors.append(f"{rel}: missing/unterminated frontmatter block")
    elif not fm.get("description"):
        errors.append(f"{rel}: slash-команда без непустого description")

# --- 10c. agent `skills:` references resolve to registry skills --------------
# Агенты бакетов (skills/<bucket>/agents/*.md) предзагружают скиллы нативным
# полем `skills: [bucket:name, ...]` (Claude Code subagent preload). Каждый
# namespaced-элемент обязан указывать на реальный скилл реестра — иначе CC
# тихо пропускает его с warning в debug-лог.
registry_bn = set()
for skill_md in skill_files:
    fm = parse_frontmatter(skill_md)
    if not fm:
        continue
    b = (fm.get("bucket", "") or "").strip().strip('"').strip("'")
    n = (fm.get("name", "") or "").strip().strip('"').strip("'")
    if b and n:
        registry_bn.add(f"{b}:{n}")
for agent_md in sorted(root.glob("skills/*/agents/*.md")):
    rel = agent_md.relative_to(root)
    fm = parse_frontmatter(agent_md)
    if not fm:
        continue
    for entry in parse_inline_list(fm.get("skills", "")):
        if ":" not in entry:
            warnings.append(
                f"{rel}: skills-элемент '{entry}' без namespace (нужно bucket:name)")
        elif entry not in registry_bn:
            errors.append(
                f"{rel}: skills-элемент '{entry}' не резолвится в скилл реестра")

# --- report ----------------------------------------------------------------
for w in warnings:
    print(f"WARN: {w}")
for e in errors:
    print(f"ERROR: {e}")

if local_total:
    pct = 100 * local_with_evals // local_total
    print(f"evals coverage: {local_with_evals}/{local_total} локальных скиллов "
          f"имеют evals/ ({pct}%) — eval-first для новых (skiller eval <skill>)")

checked = len(skill_files)
if errors:
    print(f"\n{checked} skills checked — {len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1)
print(f"{checked} skills checked — all valid ({len(warnings)} warning(s))")
PY

# --- 11. CLI + shell scripts ---------------------------------------------------
[[ -x "$REPO_ROOT/bin/skiller" ]] || {
  echo "ERROR: bin/skiller missing or not executable" >&2; exit 1; }
for sh in "$REPO_ROOT/bin/skiller" "$REPO_ROOT/install.sh" \
          "$REPO_ROOT/sync.sh" "$REPO_ROOT"/scripts/*.sh; do
  bash -n "$sh" || { echo "ERROR: bash -n failed: $sh" >&2; exit 1; }
done
# Пресеты/хуки Claude Code вынесены в пакет harness (см. packages/harness);
# их bash-проверка — в packages/harness/scripts/validate.sh.
echo "CLI + shell scripts: syntax OK"

# --- 12. lib/skiller package + unit/integration tests --------------------------
[[ -d "$REPO_ROOT/lib/skiller" ]] || {
  echo "ERROR: lib/skiller package missing" >&2; exit 1; }
# MONOREPO_ROOT (на два уровня выше пакета) — чтобы импортировался пакет `core`;
# опционально: в standalone-раскладке каталога core нет, путь не добавляется.
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
[ -d "$MONOREPO_ROOT/core" ] || MONOREPO_ROOT=""
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}" python3 -c "import skiller.cli" || {
  echo "ERROR: lib/skiller fails to import" >&2; exit 1; }
"$REPO_ROOT/scripts/test.sh" || { echo "ERROR: tests failed" >&2; exit 1; }

# --- 12b. registry drift-gate (skills.json/_index.md/манифесты vs источники) ----
# Пересобирает реестр В ПАМЯТИ и сверяет с закоммиченными артефактами. Ловит тихий
# дрейф (правка SKILL.md/buckets.json/соседних plugin.json без `skiller registry`) —
# раньше validate лишь json.loads'ил skills.json, не проверяя свежесть. Гейт для CI.
"$REPO_ROOT/bin/skiller" registry --check || {
  echo "ERROR: реестр устарел относительно источников — прогони: skiller registry" >&2; exit 1; }

# --- 13. bucket-path drift lint (после раскола php/frontend) --------------------
# Ловит протухшие ссылки `php/<skill>` / `frontend/<skill>` в телах скиллов и доках
# пакета, где <skill> по skills.json уже живёт в другом бакете (laravel-*/frontend-*).
# Защищает от регресса свода путей (аудит). Только within-package (skiller); корневые
# docs/ — зонтичные, вне scope пакета.
python3 - "$REPO_ROOT" <<'PY'
import json, re, sys, pathlib
root = pathlib.Path(sys.argv[1])
sj = root / "skills.json"
if not sj.is_file():
    print("bucket-path lint: skills.json нет — пропуск"); sys.exit(0)
skills = json.loads(sj.read_text(encoding="utf-8"))
skills = skills["skills"] if isinstance(skills, dict) else skills
name2bucket = {}
for s in skills:
    name2bucket.setdefault(s.get("name"), s.get("bucket"))
pat = re.compile(r'\b(php|frontend)/([a-z0-9][a-z0-9-]+)\b')
GENERATED = {"_index.md", "graph.md", "budget.md"}
stale = []
for base in ("skills", "docs"):
    for f in (root / base).rglob("*.md"):
        if f.name in GENERATED:
            continue
        for ln, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in pat.finditer(line):
                cur = name2bucket.get(m.group(2))
                if cur and cur != m.group(1):
                    stale.append(f"{f.relative_to(root)}:{ln}: {m.group(0)} → {cur}/{m.group(2)}")
if stale:
    print(f"ERROR: протухшие bucket-пути после раскола ({len(stale)}):", file=sys.stderr)
    for s in stale[:40]:
        print("  " + s, file=sys.stderr)
    sys.exit(1)
print("bucket-path drift: нет протухших php/<skill>|frontend/<skill> ссылок")
PY

# --- 14. двуязычная свежесть (SKILL.ru.md → SKILL.md) ---------------------------
# Гейт: RU-источник правлен, EN-канон не регенерён (или нет ru-source-sha256). Без
# claude (чистая sha-сверка) — безопасно в CI. Чинить: regen SKILL.md + check-translations --stamp.
"$REPO_ROOT/scripts/check-translations.sh" --strict || {
  echo "ERROR: протухшие переводы SKILL.ru.md→SKILL.md (regen + check-translations.sh --stamp)" >&2
  exit 1; }

# --- 15. CORE резидентный бюджет (ЖЁСТКИЙ гейт) --------------------------------
# ⊕ tier-0 CORE_SKILLS грузится в КАЖДЫЙ запрос — гейт против тихого роста ядра выше
# target (resident_budget_target в core-policy.json). --strict = ненулевой код при
# превышении. Раньше здесь был `|| true` (soft, вопреки этому же комменту) — честно
# сделан реальным гейтом (D3): коммент обещал strict — теперь он и работает.
bash "$REPO_ROOT/bin/skiller" budget --check-core --strict || {
  echo "ERROR: CORE резидентный бюджет превышен — сократи описания/скиллы ядра (skiller budget)" >&2
  exit 1; }

# --- 16. канон каркаса: таблица «пак → версия» vs pack.json (гейт свежести) ------
# `docs/agent-framework/framework-overview.md` объявлен ВХОДОМ следующего прогона
# framework-audit — и один раз уже отстал от дерева на 36 дней: аудитор получил семь
# «🔜 в работе» при готовой реализации и добросовестно предложил построить уже стоящее
# (docs/audits/2026-07-29-harness-agnostic — мета-находка). Ручное напоминание «обнови
# обзор» этот класс отказа не поймало, поэтому свежесть входа держит машина.
# Проверка того же класса, что drift-гейт реестра (§12b): ни сети, ни git-истории, ни
# календарных порогов — сверка ОБЪЯВЛЕННЫХ версий с `pack.json` каждого пака.
# В standalone-раскладке (пакет без соседнего `harness`) гейт деградирует в явный пропуск.
_AGENT_PACKS_DIR="$(cd "$REPO_ROOT/../harness/configs/claude-code/agent-packs" 2>/dev/null && pwd || true)"
python3 - "$REPO_ROOT" "${_AGENT_PACKS_DIR:-}" <<'PY'
import json, re, sys, pathlib

root = pathlib.Path(sys.argv[1])
packs_dir = sys.argv[2]
overview = root / "docs" / "agent-framework" / "framework-overview.md"

if not packs_dir:
    print("канон каркаса: packages/harness/configs/claude-code/agent-packs не найден "
          "(standalone-раскладка) — гейт свежести пропущен")
    sys.exit(0)
if not overview.is_file():
    print("канон каркаса: docs/agent-framework/framework-overview.md нет — "
          "гейт свежести пропущен")
    sys.exit(0)

# Формат якоря закрыт (P3.1): заголовок «| Пак | Версия |», разделитель, строки
# «| <пак> | <x.y.z> |». Эвристик нет — что не легло в форму, то ERROR с фиксом.
HEADER = re.compile(r"^\|\s*Пак\s*\|\s*Версия\s*\|\s*$")
SEP = re.compile(r"^\|[\s:|-]+\|\s*$")
ROW = re.compile(r"^\|\s*([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*\|\s*(\d+\.\d+\.\d+)\s*\|\s*$")

errors = []
declared = {}
in_table = False
for ln, line in enumerate(overview.read_text(encoding="utf-8").splitlines(), 1):
    if HEADER.match(line):
        in_table = True
        continue
    if not in_table:
        continue
    if SEP.match(line):
        continue
    if not line.startswith("|"):
        in_table = False
        continue
    m = ROW.match(line)
    if not m:
        errors.append(f"docs/agent-framework/framework-overview.md:{ln}: строка таблицы "
                      f"«пак → версия» не в формате `| <пак> | <x.y.z> |`: {line.strip()}")
        continue
    declared[m.group(1)] = m.group(2)

if not declared and not errors:
    errors.append("docs/agent-framework/framework-overview.md: нет таблицы «пак → версия» "
                  "(заголовок `| Пак | Версия |`) — она машинный якорь гейта свежести")

actual = {}
for pj in sorted(pathlib.Path(packs_dir).glob("*/pack.json")):
    name = pj.parent.name
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"agent-packs/{name}/pack.json: невалидный JSON: {e}")
        continue
    version = data.get("version")
    if not isinstance(version, str):
        errors.append(f"agent-packs/{name}/pack.json: нет строкового поля version")
        continue
    actual[name] = version

for name in sorted(actual):
    if name not in declared:
        errors.append(f"пак `{name}` не объявлен в каноне — обнови таблицу в "
                      f"`framework-overview.md`: `{name}` `{actual[name]}`")
    elif declared[name] != actual[name]:
        errors.append(f"пак `{name}`: канон объявляет `{declared[name]}`, pack.json несёт "
                      f"`{actual[name]}` — обнови таблицу в `framework-overview.md`: "
                      f"`{name}` `{actual[name]}`")
for name in sorted(declared):
    if name not in actual:
        errors.append(f"строка `{name}` в каноне лишняя (пака нет в "
                      f"packages/harness/configs/claude-code/agent-packs) — убери строку из "
                      f"таблицы в `framework-overview.md`")

if errors:
    print(f"ERROR: канон каркаса отстал от дерева ({len(errors)}) — "
          f"`framework-overview.md` объявлен входом следующего аудита:", file=sys.stderr)
    for e in errors:
        print("  " + e, file=sys.stderr)
    sys.exit(1)

print(f"канон каркаса: таблица «пак → версия» совпадает с pack.json ({len(actual)} паков)")
PY

# --- 17. WARN: листинг обнаружения профилей против фолбэк-бюджета Codex (P3.4) ---
# Гейт WARN, не ERROR (D26/D29): структурный перебор — известная проблема состава раздачи,
# не гигиены, красный CI её не чинит (см. budget.py CODEX_LISTING_FALLBACK_CHARS). Профиль,
# чей листинг превышает фолбэк-бюджет Codex 8 000 симв, печатает число и профиль; решение
# (сужение/skillOverrides/принятая деградация) — roadmap/, не этот скрипт (D29/OQ-7).
# Python сам зовёт CLI сабпроцессом (а не читает его stdout через pipe в `python3 -
# <<heredoc`) — конфликт: heredoc и pipe одновременно кормят один stdin, второй молча
# теряется (питон читает СВОЙ скрипт из heredoc, а не JSON из pipe).
python3 - "$REPO_ROOT" <<'PY'
import json, subprocess, sys

repo_root = sys.argv[1]
result = subprocess.run(["bash", f"{repo_root}/bin/skiller", "budget",
                        "--profiles", "--json"], capture_output=True, text=True)
try:
    rows = json.loads(result.stdout)
except json.JSONDecodeError:
    print("листинг обнаружения Codex: пропущен (--profiles --json не отдал валидный вывод)")
    sys.exit(0)

over = [r for r in rows if r["codex"]["over"]]
if over:
    print(f"WARN: {len(over)} профил(ей) листинга превышают фолбэк-бюджет обнаружения "
          f"Codex (8 000 симв) — структурный перебор, см. roadmap/ "
          f"(D29/OQ-7, 2026.07.29-HARNESS-AGNOSTIC P3.4):")
    for r in over:
        c = r["codex"]
        print(f"  {r['profile']}: {c['raw']} симв (×{c['raw'] / c['budget']:.1f})")
else:
    print("листинг обнаружения Codex: все профили укладываются в фолбэк-бюджет 8 000 симв")
PY

# --- 18. Codex publication consumer-acceptance (P5.5) -----------------------
# Изолированный round-trip живым `codex` CLI: marketplace add → plugin list/add →
# clean-consumer discovery в temp CODEX_HOME — то, чего НЕ проверяет статическая
# схема (`test_codex_publication.py`). Azguard, 2026-07-21: пакетный GREEN был,
# consumer path — нет. Явное различение skip/GREEN/RED в выводе — "гейт не
# прогонялся" и "гейт прошёл" не одно и то же (roadmap/codex-publication-consumer-
# acceptance.md). Тест сам предполагает монорепо-раскладку (sibling packages/task) —
# та же граница портируемости, что у остального пакета tests/ этого гейта.
if [ ! -d "$REPO_ROOT/../task" ]; then
  echo "SKIP: Codex publication consumer-acceptance гейт — нет sibling packages/task (standalone-раскладка skiller вне монорепо)"
elif ! command -v codex >/dev/null 2>&1; then
  echo "SKIP: Codex publication consumer-acceptance гейт — бинарь 'codex' не найден в PATH (гейт НЕ прогонялся, не считать за GREEN)"
else
  codex_version="$(codex --version 2>/dev/null || echo unknown)"
  _MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
  _codex_gate_log="$(mktemp)"
  if (cd "$REPO_ROOT" && PYTHONPATH="$REPO_ROOT/lib:$REPO_ROOT${_MONOREPO_ROOT:+:$_MONOREPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}" \
      python3 -m unittest tests.test_codex_consumer_acceptance -v) > "$_codex_gate_log" 2>&1; then
    echo "Codex publication consumer-acceptance: GREEN (codex ${codex_version})"
  else
    cat "$_codex_gate_log" >&2
    echo "ERROR: Codex publication consumer-acceptance гейт красный (codex ${codex_version})" >&2
    rm -f "$_codex_gate_log"
    exit 1
  fi
  rm -f "$_codex_gate_log"
fi
