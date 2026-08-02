#!/usr/bin/env bash
# Check/apply upstream updates for externally-sourced skills.
# A skill is upstream-tracked when its folder contains upstream.json.
# Skills without upstream.json are self-written and never touched.
#
# body_path (P7.3 thin-navigator, additive): sha/drift is always computed per
# files[].path — that already works for ANY local path, not just "SKILL.md" (see
# strategy=fork, whose files[].path conventionally points at a pristine mirror in
# references/). body_path just names, explicitly, WHICH files[].path entry is "the
# body" when SKILL.md itself has become a hand-written navigator that this script
# must never overwrite. No dedicated sha/drift code path exists (or is needed) for
# it — the generic per-file loop below already does the right thing once the entry
# points at body_path instead of SKILL.md.
#
# Exit codes (total order: 2 > 10 > 11 > 0 — код один, поэтому старший гасит
# младший; машинный потребитель берёт ПОЛНУЮ картину из --json, где блоки
# triage/stale_verdicts присутствуют всегда):
#   0  everything up to date (--check) / all eligible changes applied (--apply)
#   1  usage error or malformed upstream.json
#   2  one or more fetch failures (other results still printed/applied)
#  10  --check only: at least one update/notify/conflict found
#  11  --check only: triage findings in bundle CONTENT (см. блок triage ниже);
#      намеренно НЕ 10 — «апстрим изменился» и «в бандле подозрительный паттерн»
#      разные события, слияние лишило бы оператора возможности их различить
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MODE="check"
FORCE=false
JSON_OUT=false
TIMEOUT=30
SKILLS=()

usage() {
  cat <<'EOF'
Usage: scripts/update-upstreams.sh [--check|--apply] [options]

Modes (default --check):
  --check            Fetch upstreams, compare, report. Never writes to the repo.
                     Дополнительно гоняет ТРИАЖ содержимого бандла (локальный,
                     без сети): грубые паттерны четырёх классов угрозы. Находки →
                     код выхода 11 (не 10). Триаж НЕ является границей доверия —
                     no findings != safe, единственная граница — человеческий
                     аудит бандла (docs/guide/vendored-skills.md). Там же гейт
                     вердикта: AUDIT_MISSING (блока audit нет) и AUDIT_STALE
                     (вердикт вынесен против других байтов; --apply его не гасит).
  --apply            strategy=replace: overwrite local file, record sha256/fetched_at.
                     strategy=notify: record the seen upstream sha (file untouched).
                     strategy=fork: stage upstream as upstream/<name>.incoming and set
                     review_pending=true (mirror + wrapper SKILL.md untouched) for manual port.
                     strategy=merge: on ANY origin drift set merge.review_pending=true
                     (SKILL.md untouched) — composite is re-merged by the agent manually.
  --resolve          strategy=fork: promote staged incoming to the mirror; strategy=merge:
                     record fresh sha256/fetched_at for all origins. Both clear
                     review_pending + set last_review. Run AFTER porting/merging upstream
                     changes into the (wrapper/composite) SKILL.md.

Options:
  --skill PATH       Limit to one skill, e.g. imported/ai-agents (repeatable)
  --force            In --apply, also overwrite files in conflict state
  --json             Machine-readable JSON to stdout (human report to stderr)
  --timeout SEC      Fetch timeout per file (default 30)
  -h, --help         Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) MODE="check"; shift ;;
    --apply) MODE="apply"; shift ;;
    --resolve) MODE="resolve"; shift ;;
    --skill) SKILLS+=("$2"); shift 2 ;;
    --force) FORCE=true; shift ;;
    --json) JSON_OUT=true; shift ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

export UPSTREAM_MODE="$MODE" UPSTREAM_FORCE="$FORCE" UPSTREAM_JSON="$JSON_OUT" \
       UPSTREAM_TIMEOUT="$TIMEOUT" UPSTREAM_SKILLS="${SKILLS[*]:-}"

python3 - "$REPO_ROOT" <<'PY'
import hashlib, json, os, re, shutil, subprocess, sys, time, urllib.request, urllib.error
from datetime import date
from pathlib import Path

root = Path(sys.argv[1])
mode = os.environ["UPSTREAM_MODE"]
force = os.environ["UPSTREAM_FORCE"] == "true"
json_out = os.environ["UPSTREAM_JSON"] == "true"
timeout = int(os.environ["UPSTREAM_TIMEOUT"])
only = set(filter(None, os.environ["UPSTREAM_SKILLS"].split()))

report = sys.stderr if json_out else sys.stdout
results = {"checked": 0, "updates": [], "drift": [], "conflicts": [],
           "notify": [], "applied": [], "noted": [], "failures": [],
           "triage": [], "stale_verdicts": [], "reference_only": []}

# Дословная оговорка (P5.1). Печатается в ОБА канала: человеческий и --json
# (отдельным ключом, а не только прозой) — чтобы «скан зелёный» нельзя было
# процитировать как «бандлы безопасны» ни человеку, ни машине.
TRIAGE_DISCLAIMER = (
    "no findings != safe: триаж — паттерновый скан, а НЕ граница доверия. "
    "Пустой результат не означает, что бандл безопасен: RAG:v 2026-06 CSA/Trail of Bits "
    "«AI Agent Skill Scanners: Bypassed Across the Board» — сканеры обходятся "
    "(whitespace inflation, precompiled bytecode, archive indirection, social engineering "
    "LLM-ступени), вывод дословно «Don't outsource trust to a scanner». Единственная "
    "граница — человеческий аудит ВСЕХ файлов бандла (docs/guide/vendored-skills.md)."
)


def skill_id(skill_dir):
    """Bucket-relative id: imported/ai-agents, devops/docker/php, generate-skill."""
    rel = skill_dir.relative_to(root)
    parts = rel.parts
    return "/".join(parts[1:]) if parts[0] == "skills" else str(rel)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


_HAS_GH = shutil.which("gh") is not None and \
    os.environ.get("UPSTREAM_NO_GH", "") != "1"
_RAW_RE = re.compile(
    r"^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$")


def _normalize(raw):
    return raw.decode("utf-8").replace("\r\n", "\n").encode("utf-8")


def fetch_gh(owner, repo, ref, path):
    """Точечный fetch одного файла через GitHub CLI: один файл, авто-аутентификация
    (gh auth), уважает rate-limit — экономит контекст против полной загрузки.
    Возвращает bytes или возбуждает исключение (caller откатится на urllib)."""
    out = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/contents/{path}",
         "-f", f"ref={ref}", "-q", ".content"],
        capture_output=True, text=True, timeout=timeout, check=True)
    import base64
    return _normalize(base64.b64decode(out.stdout))


def fetch(url):
    """Return CRLF-normalized UTF-8 bytes. Raises on failure.

    Для GitHub raw-URL и доступного `gh` тянет через `gh api .../contents`
    (авто-аутентификация, rate-limit). Иначе/при сбое — urllib с GITHUB_TOKEN."""
    m = _RAW_RE.match(url)
    if m and _HAS_GH:
        try:
            return fetch_gh(*m.groups())
        except Exception:
            pass  # gh недоступен/ошибка — тихий откат на urllib ниже
    headers = {"User-Agent": "swissknifeman-upstream-sync"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token and url.startswith("https://raw.githubusercontent.com/"):
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            break
        except urllib.error.HTTPError as e:
            if attempt == 1 and (e.code == 429 or 500 <= e.code < 600):
                time.sleep(2)
                continue
            raise
    return _normalize(raw)  # UnicodeDecodeError -> caller reports [fail]


def line(tag, sid, fname, msg):
    print(f"[{tag}]".ljust(11) + sid.ljust(28) + fname.ljust(22) + " " + msg, file=report)


# --- discover ---------------------------------------------------------------
configs = sorted(root.glob("skills/**/upstream.json"))
meta = root / "generate-skill/upstream.json"
if meta.exists():
    configs.append(meta)

if only:
    configs = [c for c in configs if skill_id(c.parent) in only]
    missing = only - {skill_id(c.parent) for c in configs}
    if missing:
        print(f"ERROR: no upstream.json for skill(s): {', '.join(sorted(missing))}",
              file=sys.stderr)
        sys.exit(1)

# --- validate configs before any fetching ------------------------------------
parsed = []
for cfg in configs:
    sid = skill_id(cfg.parent)
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"ERROR: {cfg.relative_to(root)}: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    if data.get("schema_version") != 1 \
            or data.get("strategy") not in ("replace", "notify", "fork", "merge") \
            or not isinstance(data.get("files"), list) or not data["files"]:
        print(f"ERROR: {cfg.relative_to(root)}: malformed (run scripts/validate.sh)",
              file=sys.stderr)
        sys.exit(1)
    # body_path (P7.3 thin-navigator): если задан, ОБЯЗАН совпадать с path одной из
    # files[]-записей — иначе заявленное «тело» на деле не отслеживается ни sha, ни
    # дрейфом (тихая дыра). Не файловая проверка (существование/escape — validate.sh),
    # только структурная: files[] реально трекает то, что body_path объявляет телом.
    bp = data.get("body_path")
    if bp is not None and bp not in {f.get("path") for f in data["files"]}:
        print(f"ERROR: {cfg.relative_to(root)}: body_path '{bp}' not in files[].path "
              f"(run scripts/validate.sh)", file=sys.stderr)
        sys.exit(1)
    parsed.append((cfg, sid, data))

# --- triage: содержательный скан бандла (P5.1) --------------------------------
# ЧТО ЭТО. Ступень читает ЛОКАЛЬНОЕ содержимое бандла (все файлы рядом с
# upstream.json, кроме него самого) и ищет грубые паттерны четырёх классов угрозы.
# Сеть не нужна: дрейф ловит основной цикл, триаж — содержимое.
#
# ЧЕМ ЭТО НЕ ЯВЛЯЕТСЯ. Границей доверия. Первопартийного сканера скиллов у
# Anthropic нет, её предписание — «thoroughly audit it before use», то есть
# ЧЕЛОВЕЧЕСКОЕ чтение всех файлов бандла
# (https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills).
# CSA/Trail of Bits (2026-06) показали обход ClawHub/Cisco/skills.sh простыми
# приёмами; вывод дословно «Don't outsource trust to a scanner»
# (https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-agent-skill-scanner-bypass-20260610-csa/).
# Поэтому: набор ПАТТЕРНОВЫЙ (не IOC — публичного IOC-листа именно по Agent Skills
# нет), LLM-ступень и YARA не вводятся (первая названа CSA обходимой social
# engineering'ом, вторая — внешняя зависимость, запрещена root.engineering-invariants).
#
# ПРОВЕНАНС ПРАВИЛ. Набор выведен из разового человеческого аудита 56 вендоренных
# бандлов (P5.1, plans/archive/2026.07.31-SKM-LEAN/findings/P5-vendored-audit.md), а не
# придуман до чтения: правило PRM_REMOTE_INSTRUCTIONS существует ровно потому, что
# аудит нашёл живой носитель этого паттерна. Источники паттернов — docs/reference.md.
#
# Каждое правило несёт класс угрозы; правило без названного класса не добавляется.
TRIAGE_RULES = [
    # --- Класс 1: prompt injection ------------------------------------------
    # Скрытая инструкция внутри доверенного артефакта (проза, комментарий, фенс):
    # «skill-based prompt injection». Источник класса: Anthropic engineering post +
    # heeler.com/resource/introducing-agent-skills-security-...
    ("INJ_IGNORE", "prompt-injection",
     r"(?i)ignore\s+(?:all\s+|the\s+)*(?:previous|prior|preceding|above)\s+"
     r"(?:instructions|prompts|rules)",
     "инструкция «забудь предыдущие указания» — классический перехват"),
    ("INJ_DISREGARD", "prompt-injection",
     r"(?i)disregard\s+(?:all\s+|the\s+)*(?:previous|prior|above|your)\s+"
     r"(?:instructions|rules|system|prompt)",
     "инструкция «проигнорируй свои правила» — перехват через синоним"),
    ("INJ_HIDE_FROM_USER", "prompt-injection",
     r"(?i)(?:do not|don't|never)\s+(?:tell|inform|show|reveal|mention)\s+"
     r"(?:the\s+)?user",
     "требование скрыть действие от пользователя — признак скрытого поведения"),
    ("INJ_ROLE_OVERRIDE", "prompt-injection",
     r"(?i)(?:you\s+are\s+now\s+\w|new\s+system\s+prompt\s*:|system\s+override\s*:)",
     "подмена роли/системного промпта прямо в теле скилла"),
    ("INJ_INVISIBLE_CHAR", "prompt-injection",
     "[​-‏⁠-⁤‪-‮﻿]",
     "невидимые/форматирующие символы — носитель текста, скрытого от читателя"),

    # --- Класс 2: data exfiltration -----------------------------------------
    # Правила конъюнктивные (доступ к секрету И сетевой выход в одной строке):
    # одинокое упоминание `.env` — норма для доков и даёт шум, а не сигнал.
    ("EXF_SUSPECT_HOST", "data-exfiltration",
     r"(?i)https?://[^\s\"'`)<>]*"
     r"(?:webhook\.site|\.ngrok\.|ngrok\.io|pastebin\.com|transfer\.sh|0x0\.st|"
     r"requestbin|burpcollaborator|oast\.|interact\.sh)",
     "эфемерный/туннельный приёмник данных — типовой сток эксфильтрации"),
    ("EXF_CRED_TO_NET", "data-exfiltration",
     r"(?i)(?:~/\.ssh/id_|\.aws/credentials|\.netrc|/etc/(?:passwd|shadow)|"
     r"API_KEY|SECRET_KEY|PRIVATE_KEY)[^\n]{0,120}"
     r"(?:curl|wget|requests\.(?:post|put)|fetch\(|axios\.(?:post|put)|nc\s+-)",
     "чтение секрета и сетевой вызов в одной строке — выгрузка учётных данных"),
    ("EXF_ENV_DUMP", "data-exfiltration",
     r"(?i)(?:printenv|\benv\b)\s*\|\s*(?:curl|wget|nc\b|base64)",
     "дамп окружения, уходящий в сеть или в кодировку — сбор env-переменных"),

    # --- Класс 3: malicious code execution ----------------------------------
    ("EXE_PIPE_TO_SHELL", "code-execution",
     r"(?i)(?:curl|wget)\s[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z|k)?sh\b",
     "remote code execution: удалённый payload сразу в интерпретатор"),
    ("EXE_B64_EXEC", "code-execution",
     r"(?i)(?:eval|exec)\s*\(\s*(?:base64|b64decode|atob|codecs\.decode)|"
     r"base64\s+(?:-d|--decode)[^\n]{0,60}\|\s*(?:ba)?sh\b",
     "исполнение base64-обфусцированного кода — сокрытие полезной нагрузки"),
    ("EXE_OBFUSC_BLOB", "code-execution",
     r"[A-Za-z0-9+/]{240,}={0,2}",
     "длинный base64-подобный блоб — носитель скрытого кода/данных"),

    # --- Класс 4: over-permissive tool use ----------------------------------
    ("PRM_TOOL_WILDCARD", "over-permissive-tools",
     r"(?im)^\s*allowed[-_]tools\s*:.*(?:\*|Bash\s*\()",
     "скилл требует прав шире назначения (wildcard/Bash в allowed-tools)"),
    ("PRM_PERMISSION_BYPASS", "over-permissive-tools",
     r"(?i)--dangerously-skip-permissions|bypassPermissions",
     "обход гейта разрешений агента"),
    # Найдено аудитом P5.1 на живом бандле: скилл предписывает СХОДИТЬ В СЕТЬ и
    # применить полученное КАК ПРАВИЛА. Канал инструкций тогда живёт вне бандла,
    # sha256 его не покрывает, версия не пинована — ровно rug-pull-класс, который
    # CSA рекомендует закрывать пиновкой версий.
    ("PRM_REMOTE_INSTRUCTIONS", "over-permissive-tools",
     # RU-ветка обязательна не для симметрии: у 55 из 56 бандлов рядом лежит
     # переведённый SKILL.ru.md, и англоязычное правило на нём молчит — гейт
     # рапортовал бы чистоту ровно на половине раздаваемой поверхности.
     r"(?i)(?:(?:fetch|load|download|retrieve)[^\n]{0,80}"
     r"(?:latest|fresh|current)[^\n]{0,60}(?:guidelines|rules|instructions)"
     r"|fetched\s+(?:content|guidelines|file)[^\n]{0,80}"
     r"(?:contains|are)\s+(?:all\s+)?the\s+(?:rules|instructions)"
     r"|(?:получ|загруз|скача)\w*[^\n]{0,80}(?:актуальн|свеж)\w*[^\n]{0,60}"
     r"(?:правил|инструкц|указан)\w*"
     r"|(?:загруженн|полученн)\w*\s+(?:контент|содержимое|файл)[^\n]{0,80}"
     r"(?:содержит|несёт)[^\n]{0,40}(?:правил|инструкц)\w*)",
     "исполняемые инструкции подтягиваются из сети — вне покрытия sha256"),
]

TRIAGE_COMPILED = [(code, cls, re.compile(rx), why)
                   for code, cls, rx, why in TRIAGE_RULES]


def triage_bundle(skill_dir, sid):
    """Прогнать правила по ВСЕМ локальным файлам бандла. Возвращает список находок.

    Бинарные/нечитаемые файлы не пропускаются молча: они попадают в находку
    класса `unreadable` — «не смогли прочитать» и «чисто» не одно и то же."""
    found = []
    for path in sorted(p for p in skill_dir.rglob("*") if p.is_file()):
        if path.name == "upstream.json":
            continue
        rel = str(path.relative_to(skill_dir))
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            found.append({"skill": sid, "file": rel, "rule": "BIN_UNREADABLE",
                          "class": "unreadable", "hits": 1,
                          "why": f"файл не прочитан как UTF-8 ({e.__class__.__name__}) — "
                                 f"содержимое НЕ проверено"})
            continue
        for code, cls, rx, why in TRIAGE_COMPILED:
            hits = len(rx.findall(text))
            if hits:
                found.append({"skill": sid, "file": rel, "rule": code,
                              "class": cls, "hits": hits, "why": why})
    return found


# --- вердикт человека: носитель и его гейт (P5.11, ветка (B) OQ-6) ------------
# ЗАЧЕМ. Триаж выше — паттерновый скан, границей доверия остаётся ЧЕЛОВЕЧЕСКИЙ
# аудит бандла (TRIAGE_DISCLAIMER). Разовый аудит без машинного носителя
# обесценивается структурно: «не проверяли» и «чисто» машинно неотличимы, а
# отметка «вердикт протух» была ПРОИЗВОДНОЙ от дрейфа и умирала от первого же
# --apply (граница названа в блоке stale_verdicts ниже). Носитель — аддитивный
# блок `audit` в upstream.json рядом с бандлом: он переживает план (плановый файл
# смертен, скилл раздаётся дальше) и не заводит связи «skiller читает plans/**».
# Провенанс правила и разбор веток — docs/guide/vendored-skills.md,
# plans/archive/2026.07.31-SKM-LEAN (P5.11, D107/D109/D110).
#
# ТРИ РАЗНЫХ СОБЫТИЯ — три разных сигнала (тот же принцип, по которому код 11 не
# слит с 10): «апстрим сдвинулся» (updates/notify) · «вердикта нет НИКОГДА не
# было» (AUDIT_MISSING) · «вердикт вынесен против ДРУГИХ байтов» (AUDIT_STALE).
#
# ЯКОРЬ. audit.upstream_sha хранится ОТДЕЛЬНО от files[].sha256 и не обновляется
# ни --apply, ни --resolve — именно поэтому отметка переживает применение
# апстрима. Описывает он те байты, против которых вынесен вердикт: sha256
# НАЗВАННОГО тела (body_path), когда бандл его называет, иначе — свёртку всей
# провенансной базы (пары path:sha256 из files[]/origins[]).
AUDIT_VERDICTS = ("clean", "attention", "risk")


def is_reference_only(data):
    """Бандл, который не вендорит НИЧЕГО: все files[].path пусты — записи являются
    провенанс-ССЫЛКАМИ на внешние спеки, локальных зеркал нет. Признак машинный
    (не мнение); для такого бандла якорить вердикт не к чему, и гейт этого не
    требует — иначе правило врало бы на классе, ради честности которого заведено."""
    files = data.get("files") or []
    return bool(files) and all(not e.get("path") for e in files)


def audit_anchor(data):
    """Байты, против которых вынесен вердикт. None — якорить нечего (reference-only)."""
    if is_reference_only(data):
        return None
    body_path = data.get("body_path")
    if body_path:
        for entry in data.get("files", []):
            if entry.get("path") == body_path:
                return entry.get("sha256", "")
    entries = list(data.get("files", [])) + list(data.get("origins", []))
    base = "".join(f"{e.get('path', '')}:{e.get('sha256', '')}\n"
                   for e in sorted(entries, key=lambda x: x.get("path", "")))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def audit_findings(sid, data):
    """Находки гейта вердикта. Форма — та же, что у триажа (код 11, --json)."""
    audit = data.get("audit")
    if not isinstance(audit, dict):
        return [{"skill": sid, "file": "upstream.json", "rule": "AUDIT_MISSING",
                 "class": "unaudited", "hits": 1,
                 "why": "человеческого вердикта по бандлу нет — «не проверяли» и "
                        "«чисто» это не одно и то же; прочитай бандл целиком и "
                        "запиши блок audit (docs/guide/vendored-skills.md)"}]
    anchor = audit_anchor(data)
    if anchor is None:
        return []
    stored = audit.get("upstream_sha", "")
    if stored == anchor:
        return []
    verdict = audit.get("verdict", "?")
    at = audit.get("at", "?")
    seen = f"{stored[:8]}.." if stored else "якорь не записан"
    return [{"skill": sid, "file": "upstream.json", "rule": "AUDIT_STALE",
             "class": "stale-verdict", "hits": 1,
             "why": f"вердикт '{verdict}' от {at} вынесен против других байтов "
                    f"({seen} -> {anchor[:8]}..) — перечитай бандл и обнови блок "
                    f"audit; отметка НЕ гаснет от --apply"}]


# --- process -----------------------------------------------------------------
today = date.today().isoformat()

if mode == "check":
    for cfg, sid, data in parsed:
        if is_reference_only(data):
            results["reference_only"].append(sid)
        for finding in triage_bundle(cfg.parent, sid) + audit_findings(sid, data):
            results["triage"].append(finding)
            line("triage", sid, finding["file"],
                 f"{finding['rule']} ({finding['class']}) x{finding['hits']} — "
                 f"{finding['why']}")

for cfg, sid, data in parsed:
    skill_dir = cfg.parent
    strategy = data["strategy"]
    changed = False

    # --- merge: композит из origins[] (base + supplement). Дрейф ЛЮБОГО источника →
    #     ручной agent-merge: --check сообщает, --apply поднимает merge.review_pending
    #     (гейт в validate.sh), --resolve фиксирует свежие sha и снимает флаг. Зеркало
    #     одним файлом не перезаписывается — композит склеивает агент вручную. ---
    if strategy == "merge":
        mp = data.setdefault("merge", {})
        for k, org in enumerate(data.get("origins", [])):
            results["checked"] += 1
            label = org.get("repo", f"origin{k}")
            role = org.get("role", "?")
            try:
                remote = fetch(org["url"])
            except Exception as e:
                code = getattr(e, "code", None)
                err = f"HTTP {code}" if code else str(e)
                line("fail", sid, label, f"fetch failed: {err}")
                results["failures"].append({"skill": sid, "file": label, "error": err})
                continue
            remote_sha = sha256_bytes(remote)
            stored = org.get("sha256", "")
            if mode == "resolve":
                org["sha256"] = remote_sha
                org["fetched_at"] = today
                changed = True
                line("resolved", sid, label, f"origin sha обновлён ({role})")
            elif remote_sha == stored:
                line("ok", sid, label, f"up-to-date (merge/{role})")
            else:
                what = "baseline missing" if not stored \
                    else f"origin changed ({stored[:8]}.. -> {remote_sha[:8]}..)"
                if mode == "apply":
                    mp["review_pending"] = True
                    changed = True
                    line("staged", sid, label,
                         f"{what}; merge.review_pending=true — пере-мерджи "
                         f"источники в SKILL.md вручную, затем --resolve")
                    results["noted"].append({"skill": sid, "file": label,
                                             "new_sha": remote_sha, "url": org["url"]})
                else:  # check
                    line("notify", sid, label,
                         f"{what}; strategy=merge — ручной agent-merge")
                    results["notify"].append({"skill": sid, "file": label,
                                              "old_sha": stored, "new_sha": remote_sha})
        if mode == "resolve" and changed:
            mp["review_pending"] = False
            mp["last_review"] = today

    for entry in ([] if strategy == "merge" else data["files"]):
        fname = entry["path"]
        local_path = skill_dir / fname
        stored = entry.get("sha256", "")
        results["checked"] += 1

        # Запись с пустым path — провенанс-ССЫЛКА (url ведёт на спеку/доку, чужой
        # код не вендорится), а не локальное зеркало. Схема такую запись допускает
        # (path без minLength), и она живёт в реестре (skills/voice-ai/voice-ai).
        # Раньше `skill_dir / ""` резолвился в САМ КАТАЛОГ и `read_bytes()` ронял
        # весь прогон IsADirectoryError'ом — тихая яма, гасившая --check целиком.
        # Сверять по sha тут нечего: сообщаем явно и идём дальше (не «ok»).
        if not fname:
            line("ref", sid, "(no mirror)",
                 f"reference-only provenance, sha не сверяется: {entry['url']}")
            continue

        # --- fork --resolve: продвинуть заранее заготовленный incoming в зеркало и снять
        #     флаг. Сеть не нужна (работаем с уже скачанным upstream/<name>.incoming). ---
        if mode == "resolve":
            if strategy != "fork":
                line("skip", sid, fname, "--resolve применим только к strategy=fork")
                continue
            incoming_path = skill_dir / "upstream" / \
                f"{Path(fname).stem}.incoming{Path(fname).suffix}"
            if not incoming_path.exists():
                line("skip", sid, fname, "нет staged incoming (сначала --apply)")
                continue
            new_bytes = incoming_path.read_bytes()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = local_path.with_suffix(local_path.suffix + ".tmp")
            tmp.write_bytes(new_bytes); os.replace(tmp, local_path)
            entry["sha256"] = sha256_bytes(new_bytes)
            entry["fetched_at"] = today
            data["review_pending"] = False
            data["last_review"] = today
            incoming_path.unlink()
            changed = True
            line("resolved", sid, fname, "зеркало обновлено, review_pending снят")
            results["applied"].append({"skill": sid, "file": fname,
                                        "new_sha": entry["sha256"], "resolved": True})
            continue

        try:
            remote = fetch(entry["url"])
        except Exception as e:
            code = getattr(e, "code", None)
            err = f"HTTP {code}" if code else str(e)
            line("fail", sid, fname, f"fetch failed: {err}")
            results["failures"].append({"skill": sid, "file": fname, "error": err})
            continue

        remote_sha = sha256_bytes(remote)
        local_sha = sha256_bytes(local_path.read_bytes()) if local_path.exists() else ""

        def record():
            entry["sha256"] = remote_sha
            entry["fetched_at"] = today

        def write_local():
            tmp = local_path.with_suffix(local_path.suffix + ".tmp")
            tmp.write_bytes(remote)
            os.replace(tmp, local_path)

        if strategy == "fork":
            # Зеркало (= files[].path, pristine-копия апстрима) и обёртку SKILL.md НЕ трогаем.
            # На дрейфе кладём свежий апстрим в upstream/<name>.incoming и поднимаем флаг —
            # агент сверяет diff, переносит изменения в обёртку, затем --resolve.
            incoming_path = skill_dir / "upstream" / \
                f"{Path(fname).stem}.incoming{Path(fname).suffix}"
            if remote_sha == stored:
                line("ok", sid, fname, "up-to-date (fork)")
            else:
                what = "baseline missing" if not stored \
                    else f"upstream changed ({stored[:8]}.. -> {remote_sha[:8]}..)"
                if mode == "apply":
                    incoming_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = incoming_path.with_suffix(incoming_path.suffix + ".tmp")
                    tmp.write_bytes(remote); os.replace(tmp, incoming_path)
                    data["review_pending"] = True
                    changed = True
                    line("staged", sid, fname,
                         f"{what}; incoming staged + review_pending=true — "
                         f"перенеси правки в SKILL.md, затем --resolve")
                    results["noted"].append({"skill": sid, "file": fname, "new_sha": remote_sha,
                                             "incoming": str(incoming_path.relative_to(root)),
                                             "url": entry["url"]})
                else:  # check
                    line("notify", sid, fname,
                         f"{what}; strategy=fork — нужна ручная доработка")
                    results["notify"].append({"skill": sid, "file": fname,
                                              "old_sha": stored, "new_sha": remote_sha})
            continue

        if strategy == "notify":
            if remote_sha == stored:
                line("ok", sid, fname, "up-to-date")
            else:
                what = "baseline missing" if not stored \
                    else f"upstream changed ({stored[:8]}.. -> {remote_sha[:8]}..)"
                if mode == "apply":
                    record(); changed = True
                    line("noted", sid, fname,
                         f"{what}; sha recorded, file untouched — review manually: {entry['url']}")
                    results["noted"].append({"skill": sid, "file": fname,
                                             "new_sha": remote_sha, "url": entry["url"]})
                else:
                    line("notify", sid, fname, f"{what}; strategy=notify, review manually")
                    results["notify"].append({"skill": sid, "file": fname,
                                              "old_sha": stored, "new_sha": remote_sha})
            continue

        # strategy == replace
        local_clean = (local_sha == stored) or not stored or not local_path.exists()
        upstream_new = remote_sha != stored
        in_sync = local_path.exists() and local_sha == remote_sha

        if in_sync:
            if remote_sha != stored:  # content matches but sha never recorded
                if mode == "apply":
                    record(); changed = True
                    line("noted", sid, fname, "sha recorded (content already in sync)")
                    results["noted"].append({"skill": sid, "file": fname, "new_sha": remote_sha})
                else:
                    line("update", sid, fname, "sha not recorded yet (content in sync)")
                    results["updates"].append({"skill": sid, "file": fname,
                                               "old_sha": stored, "new_sha": remote_sha})
            else:
                line("ok", sid, fname, "up-to-date")
        elif upstream_new and local_clean:
            if mode == "apply":
                write_local(); record(); changed = True
                line("applied", sid, fname, f"replaced ({remote_sha[:8]}..)")
                results["applied"].append({"skill": sid, "file": fname, "new_sha": remote_sha})
            else:
                line("update", sid, fname,
                     f"upstream changed ({stored[:8] or 'none'}.. -> {remote_sha[:8]}..)")
                results["updates"].append({"skill": sid, "file": fname,
                                           "old_sha": stored, "new_sha": remote_sha})
        elif upstream_new and not local_clean:
            if mode == "apply" and force:
                write_local(); record(); changed = True
                line("applied", sid, fname, f"replaced with --force ({remote_sha[:8]}..)")
                results["applied"].append({"skill": sid, "file": fname,
                                           "new_sha": remote_sha, "forced": True})
            else:
                line("conflict", sid, fname,
                     "local drift + upstream change (use --apply --force)")
                results["conflicts"].append({"skill": sid, "file": fname})
        else:  # upstream unchanged, local edited
            line("drift", sid, fname, "local modified since last fetch")
            results["drift"].append({"skill": sid, "file": fname})

    if changed:
        tmp = cfg.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        os.replace(tmp, cfg)

# --- вердикт протух (P5.1, D65) ----------------------------------------------
# Разовый человеческий аудит бандла записан ПРОТИВ КОНКРЕТНЫХ БАЙТОВ: колонка
# `audited_at` таблицы вердиктов несёт тот самый sha256, который в момент аудита
# лежал в files[].sha256. Значит дрейф относительно записанного sha И ЕСТЬ дрейф
# относительно audited_at: вердикт больше не описывает то, что лежит в дереве.
# Без этой отметки разовый аудит перестаёт что-либо значить после первого же
# обновления апстримов, а --check продолжает рапортовать одну лишь целостность.
#
# ГРАНИЦА (названа, а не сымитирована): после `--apply` свежий sha записывается в
# upstream.json, дрейф исчезает — и отметка вместе с ним, хотя человеческий вердикт
# остался протухшим. Скрипт не читает таблицу вердиктов (она живёт в плане/доках,
# кросс-пакетной связи здесь быть не должно), поэтому «протух» detectable только до
# --apply. Процедура: --check → перечитать помеченные бандлы → обновить таблицу.
#
# P5.11: механизм НЕ удалён, но сужен до бандлов БЕЗ блока `audit` — то есть ровно
# до тех, кого ловит AUDIT_MISSING и у кого собственного якоря нет. У бандла с
# блоком `audit` протухание считает AUDIT_STALE по своему якорю (переживает
# --apply), и два источника одной отметки не смешиваются: причина печатается
# различимо, а `reason` в --json называет механизм поимённо.
if mode == "check":
    _audited = {sid for _cfg, sid, data in parsed if isinstance(data.get("audit"), dict)}
    _drifted = {e["skill"] for key in ("updates", "drift", "conflicts", "notify")
                for e in results[key]} - _audited
    for sid in sorted(_drifted):
        results["stale_verdicts"].append(
            {"skill": sid, "reason": "bytes drifted from audited_at (derived: "
                                     "no audit block — see AUDIT_MISSING)"})
        line("stale", sid, "(verdict)",
             "байты разошлись с audited_at — человеческий вердикт бандла ПРОТУХ, "
             "перечитай бандл перед тем, как считать его проверенным "
             "(производная отметка: блока audit у бандла нет)")

# --- summary -----------------------------------------------------------------
s = results
print(f"Summary: {s['checked']} checked | {len(s['updates'])} update | "
      f"{len(s['drift'])} drift | {len(s['conflicts'])} conflict | "
      f"{len(s['notify'])} notify | {len(s['applied'])} applied | "
      f"{len(s['noted'])} noted | {len(s['failures'])} failed", file=report)
if mode == "check":
    print(f"Triage: {len(s['triage'])} finding(s) in "
          f"{len({f['skill'] for f in s['triage']})} bundle(s) | "
          f"{len(s['stale_verdicts'])} stale verdict(s) | "
          f"{len(s['reference_only'])} reference-only bundle(s)", file=report)
    print(f"NOTE: {TRIAGE_DISCLAIMER}", file=report)

if (s["applied"] or s["noted"]) and not json_out:
    print("Run ./sync.sh --update-registry to refresh skills.json", file=report)

if json_out:
    # Оговорка — ОТДЕЛЬНЫМ ключом, а не только прозой в человеческом канале:
    # машинный потребитель обязан видеть её так же, как оператор.
    if mode == "check":
        results["triage_disclaimer"] = TRIAGE_DISCLAIMER
    print(json.dumps(results, indent=2, ensure_ascii=False))

if s["failures"]:
    sys.exit(2)
if mode == "check" and (s["updates"] or s["notify"] or s["conflicts"]):
    sys.exit(10)
if mode == "apply" and s["conflicts"] and not force:
    sys.exit(10)
# Триаж — СВОЙ код (11), не 10: «апстрим изменился» и «в бандле подозрительный
# паттерн» — разные события. 10 старше 11 только потому, что код один скаляр;
# полная картина обоих всегда есть в --json.
if mode == "check" and s["triage"]:
    sys.exit(11)
sys.exit(0)
PY
