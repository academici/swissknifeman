"""plan_weight — вес обязательного чтения пункта плана (2026.08.07-PLAN-ECONOMY P0.3).

Инструмент воспроизводит ОБЯЗАТЕЛЬНЫЙ ПУТЬ ЧТЕНИЯ исполнителя из
`packages/task/commands/plan-exec.md` §1 буквально и считает его вес в оценочных
токенах поверх ЗАМОРОЖЕННОЙ калибровки P0.1 (`task.token_estimate`, артефакт
`configs/token-estimate-calibration.json`), проверяя каждый обязательный файл против
ИЗМЕРЕННОГО лимита одного чтения P0.2 (`configs/read-limit.json`).

Обязательный путь зависит только от объявленной раскладки. Для layout v1 он остаётся
legacy-путём (`MANDATORY_PATH_LITERALS`):

    1) plans/<PLAN-ID>/plan.md      → роль `plan`
    2) plans/<PLAN-ID>/handoff.md   → роль `handoff`
    3) plans/<PLAN-ID>/phases/Pn.md → роль `phase`
    4) файлы из **Required Reads** пункта, в указанном порядке → роль `required_read`

Для layout v2 (`V2_MANDATORY_PATH_LITERALS`) production path совпадает с пятью executor
slots замороженного `read-path` v1:

    1) plan.md                         → `plan-core`
    2) phases/<Pn>/<Pn>.md             → `phase-context`
    3) phases/<Pn>/<Pn.m>.md           → `item-spec`
    4) bundles/<Pn.m>.json + selections → `item-input-bundle` + `bundle-input`
    5) phases/<Pn>/<Pn.m>.state.md     → `item-state`

Generated bundle/state проходят owning freshness check до использования. `handoff.md`
в layout-v2 executor path не входит.

Две измерительные асимметрии фазы P0 (`research/02-p0-measurement-design.md` §5)
воспроизводятся здесь буквально:

* по ТОКЕНАМ замер идёт СВЕРХУ — оценка `token_estimate` никогда не занижает на корпусе
  прозы планов (граница на плотном ASCII НЕ доказана, D109 — потому и считается
  `dense_ascii_share`, см. ниже);
* по СОСТАВУ файлов замер идёт СНИЗУ — `Required Reads` сегодня проза, часть позиций не
  приводится к пути, и такие позиции в сумму не попадают. Поэтому отчёт НИКОГДА не
  печатает сумму без перечня пробелов: сумма без пробелов — это нижняя оценка, выданная
  за измеренную.

Таксономия пробелов ЗАКРЫТАЯ (`GAP_KINDS`, `research/02-…` §5): `unreadable_root` ·
`unresolved_entry` · `missing_file` · `oversized_file`. «Прочего» не заводится.

`oversized_file` — единственная категория, чей вес ИЗВЕСТЕН и потому ВХОДИТ в сумму:
файл разрешён и прочитан, он лишь нарушает условие приёмки D2(б) (читаться ЦЕЛИКОМ
ОДНИМ вызовом). Три остальные категории веса не имеют по построению — их нечего
суммировать. Позиция `oversized_file` несёт поле `gate` (`size_bytes` | `tokens` |
`both`): P0.4 обязана разделить перечень по гейтам, сведение их в одно число теряет
класс отказа (D107/D108).

Проверка файла против лимита — КОНЪЮНКЦИЯ обоих гейтов (D108,
`research/12-read-limit-design-2026-08-07.md` §5):

    pass(f) = bytes(f) ≤ limits.size_bytes.value  И  est_tokens(f) ≤ limits.tokens.value

Токенная сторона — ОЦЕНКА СВЕРХУ: счётчик среды наблюдаем только в момент срабатывания
капа (`findings/15-…` O6), в CI его нет. Постраничное дочитывание условие НЕ
удовлетворяет и послаблением не является.

`dense_ascii_share` (D109) — доля символов файла, входящих в непрерывные прогоны длиной
≥ `DENSE_ASCII_MIN_RUN` символов из `[0-9A-Za-z+/=]` без пробельных разделителей. Это
ЗАМЕР, а не гейт: порога по нему здесь НЕТ, файл по нему не отбраковывается и
«подозрительным» не помечается — пороги замораживает P0.5 на числах флота P0.4.

**Эвристика резолвинга `Required Reads`** (будущий вход контракта bundle, P3) — «лучшее
усилие», описанное здесь целиком, потому что от него зависит, что попадёт в сумму:

1. Значение поля режется на позиции по нумерации `N)` (`ENTRY_NUMBER_RE`); нумерации нет
   — всё значение считается одной позицией.
2. Кандидаты берутся из ДВУХ источников с РАЗНОЙ силой утверждения:
   * спан в обратных кавычках (`` `…` ``) — ОБЪЯВЛЕННЫЙ путь;
   * голый токен позиции — планы флота до 2026.07 пишут пути без бэктиков
     (`1) packages/skiller/lib/skiller/analyze.py (…)`), терять их значило бы занижать
     вес там, где исполнитель читает файл без раздумий. Голый токен формы
     `каталог/файл.ext` (`_is_strong_path`) считается таким же ОБЪЯВЛЕНИЕМ, всё
     остальное («P4 finding/research») — ДОГАДКОЙ.
3. Токен раскрывается по фигурным скобкам (`core/provider/{registry,artifact,lock}.py` →
   три пути); раскрытие шире `MAX_BRACE_EXPANSION` считается непутевым.
4. Токен признаётся путеподобным (`_is_path_like`), если состоит из допустимых для пути
   символов И несёт `/` либо расширение, начинающееся с БУКВЫ (иначе `P0.1` из прозы
   «P0.1 Completion Notes» ложно выглядел бы файлом).
5. Путеподобный токен разрешается по корням в порядке: абсолютный путь · каталог плана ·
   корень репозитория (первый существующий файл выигрывает).
6. Разница сил утверждения — в классификации промаха: ОБЪЯВЛЕННЫЙ путь, не нашедший
   файла, — это `missing_file` (путь назван, файла нет); ДОГАДКА, не нашедшая файла,
   пробелом отдельного класса не становится и `missing_file` не выдумывает — позиция
   остаётся нерезолвленной. Позиция без единого разрешённого пути и без объявленного
   промаха → `unresolved_entry`.
7. Значение `—` (канонический пустой плейсхолдер протокола) означает, что `Required
   Reads` нет вовсе: позиций ноль, пробела ноль.

Файлы дедуплицируются по разрешённому пути: исполнитель читает файл один раз, и
повторное упоминание `phases/P1.md` в `Required Reads` веса не удваивает.

Артефакты калибровки и лимита ОБЯЗАТЕЛЬНЫ: их отсутствие или невалидность — внятная
ошибка и код возврата ≠ 0. Литеральных дефолтов нет ни для ставок, ни для лимитов.
Инструмент открывает файлы ТОЛЬКО на чтение (D3: чужие планы читаются, но не
изменяются), сети не открывает и учётных данных не читает ни в одном режиме.

Режим `--exact` (D92/D99) — ДИФФЕРЕНЦИАЛЬНЫЙ ХАРНЕСС, а НЕ вызов `count_tokens`:
сверяет оценку сверху с истиной протокола тройного прогона P0.1
(`packages/task/scripts/calibrate-token-estimate.py`, артефакт прогона
`calibration-probe-log.json`) на ЯВНО УКАЗАННЫХ файлах. Существует только для разбора
пограничного случая человеком: прогон ручной, режим печатает предупреждение и НИКОГДА
не участвует в CI. `count_tokens` этим модулем не реализуется и не вызывается ни в
одном режиме (ключа Console у владельца не будет — объявленное свойство среды,
R21/R22 `findings/14-…`).

stdlib-only; `core` (через `task.plan_lint`) достаётся тем же фолбэком `sys.path`, что и
в `plan-lint.py`. Разбор фазовых файлов делегирован `task.plan_lint.parse_phase_md` —
тому же парсеру, которым план читает линтер: второй парсер означал бы второе
определение схемы.
"""
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from task import (plan_admission, plan_bundle, plan_item_state, plan_lint, plan_layout,
                  token_estimate)

# --- обязательный путь чтения (`plan-exec.md` §1) ----------------------------------

# Литералы §1 в порядке следования; тест сверяет их с актуальным текстом команды —
# правка `plan-exec.md` обязана ломать тест, а не расходиться с инструментом молча.
MANDATORY_PATH_LITERALS = (
    "plans/<PLAN-ID>/plan.md",
    "plans/<PLAN-ID>/handoff.md",
    "plans/<PLAN-ID>/phases/Pn.md",
    "**Required Reads**",
)
V2_MANDATORY_PATH_LITERALS = (
    "plans/<PLAN-ID>/plan.md",
    "plans/<PLAN-ID>/phases/<Pn>/<Pn>.md",
    "plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.md",
    "plans/<PLAN-ID>/bundles/<Pn.m>.json",
    "plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.state.md",
)
PLAN_EXEC_RELPATH = Path("packages/task/commands/plan-exec.md")

V1_ROLES = ("plan", "handoff", "phase", "required_read")
V2_CARRIER_ROLES = (
    "plan-core", "phase-context", "item-spec", "item-input-bundle", "item-state")
V2_INPUT_ROLE = "bundle-input"
# Backward-compatible public alias used by existing consumers/tests.
ROLES = V1_ROLES

# --- таксономия пробелов (закрытая, research/02 §5) --------------------------------

GAP_UNREADABLE_ROOT = "unreadable_root"
GAP_UNRESOLVED_ENTRY = "unresolved_entry"
GAP_MISSING_FILE = "missing_file"
GAP_OVERSIZED_FILE = "oversized_file"
GAP_KINDS = (GAP_UNREADABLE_ROOT, GAP_UNRESOLVED_ENTRY, GAP_MISSING_FILE, GAP_OVERSIZED_FILE)

GATE_SIZE_BYTES = "size_bytes"
GATE_TOKENS = "tokens"
GATE_BOTH = "both"
GATES = (GATE_SIZE_BYTES, GATE_TOKENS, GATE_BOTH)

# --- dense_ascii_share (D109) ------------------------------------------------------

# The classifier belongs to token_estimate; retaining this public alias avoids a second owner.
DENSE_ASCII_MIN_RUN = token_estimate.DENSE_ASCII_MIN_RUN
dense_ascii_share = token_estimate.dense_ascii_share

# --- резолвинг Required Reads ------------------------------------------------------

ENTRY_NUMBER_RE = re.compile(r"(?:^|\s)(\d{1,2})\)\s")
BACKTICK_SPAN_RE = re.compile(r"`([^`]+)`")
# Пустое поле помечается ровно этим символом — реестр канона держит `plan_lint`.
EMPTY_PLACEHOLDER = plan_lint.EMPTY_PLACEHOLDER
# Обрамляющая пунктуация вокруг голого токена (кавычки-ёлочки, скобки, запятые).
BARE_TOKEN_STRIP = "«»\"'(),;:.…“”[]"
BRACE_GROUP_RE = re.compile(r"\{([^{}]*)\}")
MAX_BRACE_EXPANSION = 64
PATH_TOKEN_RE = re.compile(r"^[A-Za-z0-9._@~/+-]+$")
# Расширение обязано начинаться с БУКВЫ: `.md`/`.py`/`.json` — путь, `P0.1` — проза.
PATH_SUFFIX_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}$")

DEFAULT_READ_LIMIT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "read-limit.json"
)
DEFAULT_CANON_BUDGET_PATH = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "canon-weight-budget.json"
)

# Артефакт прогона дифференциального харнесса P0.1 — единственный источник «истины» для
# `--exact` (тот же путь, что пишет `calibrate-token-estimate.py`); корень берётся от
# раскладки самого модуля, а не от cwd.
DEFAULT_PROBE_LOG_RELPATH = Path(
    "plans/2026.08.07-PLAN-ECONOMY/artifacts/P0/calibration-probe-log-v2.json")
_MONOREPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PROBE_LOG_PATH = _MONOREPO_ROOT / DEFAULT_PROBE_LOG_RELPATH

SCHEMA = "plan-weight-v1"

# Переменные среды, из которых берётся модель текущего окружения для WARNING о
# расхождении с `tokenizer.model_id` калибровки (митигация pre-mortem #1). Ни одна не
# выставлена — предупреждения нет: отсутствие свидетельства не домысливается.
SESSION_MODEL_ENV = ("ANTHROPIC_MODEL", "CLAUDE_MODEL", "CLAUDE_CODE_MODEL")
SESSION_PROVIDER_ENV = ("TOKEN_ESTIMATE_PROVIDER",)


class PlanWeightError(Exception):
    """Невалидный вход инструмента (артефакт, план, аргументы) — fail-closed, exit ≠ 0."""


# --- артефакт лимита ---------------------------------------------------------------

def load_read_limit(path=None):
    """Читает и валидирует `configs/read-limit.json` (форма — `research/12-…` §3).

    Читаются ОБА поля (`limits.size_bytes.value`, `limits.tokens.value`); отсутствие
    любого из двух = невалидный артефакт (D107). Литеральных дефолтов нет."""
    path = Path(path) if path is not None else DEFAULT_READ_LIMIT_PATH
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanWeightError(f"артефакт лимита чтения не читается: {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PlanWeightError(f"артефакт лимита чтения — невалидный JSON: {path}: {exc}") from exc

    limits = data.get("limits")
    if not isinstance(limits, dict):
        raise PlanWeightError(f"артефакт лимита чтения: нет секции «limits»: {path}")
    values = {}
    for gate in (GATE_SIZE_BYTES, GATE_TOKENS):
        node = limits.get(gate)
        if not isinstance(node, dict) or "value" not in node:
            raise PlanWeightError(
                f"артефакт лимита чтения: нет гейта «limits.{gate}.value» — среда несёт ДВА "
                f"независимых гейта, один скалярный лимит обязан соврать (D107): {path}")
        value = node["value"]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise PlanWeightError(
                f"артефакт лимита чтения: limits.{gate}.value обязано быть целым > 0, "
                f"получено {value!r}: {path}")
        values[gate] = value
    return {"path": str(path), "artifact": data,
            "size_bytes": values[GATE_SIZE_BYTES], "tokens": values[GATE_TOKENS]}


def session_model_id(explicit=None):
    """Модель текущего окружения: явный аргумент, иначе первая выставленная переменная
    из `SESSION_MODEL_ENV`. Ничего не выставлено — `None` (свидетельство отсутствия)."""
    if explicit:
        return explicit
    for name in SESSION_MODEL_ENV:
        value = os.environ.get(name)
        if value:
            return value
    return None


def session_provider_id(explicit=None):
    if explicit:
        return explicit
    for name in SESSION_PROVIDER_ENV:
        value = os.environ.get(name)
        if value:
            return value
    return None


# --- измерение файла ---------------------------------------------------------------

def measure_file(path, *, role, artifact, limits, model_id=None):
    """Одна запись файла обязательного пути: байты, оценка токенов СВЕРХУ, доля плотного
    ASCII и результат КОНЪЮНКЦИИ обоих гейтов (D108).

    Файл читается байтами и декодируется utf-8 с заменой сбойных последовательностей:
    обязательный путь бывает и не-текстовым (`.json`-артефакты, скрипты), а замер обязан
    дать число, а не исключение — вес всё равно считается по декодированному тексту."""
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    est = token_estimate.estimate_text(text, artifact=artifact, session_model_id=model_id)
    size_ok = len(raw) <= limits["size_bytes"]
    tokens_ok = est <= limits["tokens"]
    return {
        "path": str(path),
        "role": role,
        "bytes": len(raw),
        "chars": len(text),
        "est_tokens": est,
        "dense_ascii_share": dense_ascii_share(text),
        "gates": {GATE_SIZE_BYTES: size_ok, GATE_TOKENS: tokens_ok},
        "passes": size_ok and tokens_ok,
    }


def measure_bytes(raw, *, path, role, artifact, limits, model_id=None):
    """Measure one digest-qualified selection without pretending it is a whole file."""
    text = raw.decode("utf-8", errors="replace")
    est = token_estimate.estimate_text(text, artifact=artifact, session_model_id=model_id)
    size_ok = len(raw) <= limits["size_bytes"]
    tokens_ok = est <= limits["tokens"]
    return {
        "path": str(path),
        "role": role,
        "bytes": len(raw),
        "chars": len(text),
        "est_tokens": est,
        "dense_ascii_share": dense_ascii_share(text),
        "gates": {GATE_SIZE_BYTES: size_ok, GATE_TOKENS: tokens_ok},
        "passes": size_ok and tokens_ok,
    }


def measure_document(path, measurer):
    """Measure one UTF-8 instruction carrier in tokens and physical lines."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PlanWeightError(f"document is not readable: {path}: {exc}") from exc
    text = raw.decode("utf-8", errors="replace")
    return {
        "path": str(path),
        "bytes": len(raw),
        "lines": len(text.splitlines()),
        "est_tokens": token_estimate.estimate_text(
            text, artifact=measurer.artifact, session_model_id=measurer.model_id),
    }


def load_canon_budget(path):
    """Load the D93 two-threshold canon budget; malformed policy fails closed."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanWeightError(f"canon budget is not readable JSON: {path}: {exc}") from exc
    required = ("canon_path", "baseline", "warning_fraction", "regression_percent",
                "vendor_line_guidance", "exceptions")
    missing = [key for key in required if key not in data]
    if missing:
        raise PlanWeightError(f"canon budget lacks required keys {missing}: {path}")
    baseline = data["baseline"]
    if not isinstance(baseline, dict) or not isinstance(baseline.get("est_tokens"), int):
        raise PlanWeightError(f"canon budget baseline.est_tokens must be an integer: {path}")
    warning = data["warning_fraction"]
    regression = data["regression_percent"]
    if (not isinstance(warning, (int, float)) or isinstance(warning, bool)
            or not 0 < warning < 1):
        raise PlanWeightError(f"canon budget warning_fraction must be between 0 and 1: {path}")
    if (not isinstance(regression, (int, float)) or isinstance(regression, bool)
            or regression < 0):
        raise PlanWeightError(f"canon budget regression_percent must be non-negative: {path}")
    exceptions = data["exceptions"]
    if not isinstance(exceptions, list):
        raise PlanWeightError(f"canon budget exceptions must be a list: {path}")
    for entry in exceptions:
        if not isinstance(entry, dict) or not entry.get("expires_at"):
            raise PlanWeightError(f"every canon budget exception needs expires_at: {path}")
        try:
            date.fromisoformat(entry["expires_at"])
        except (TypeError, ValueError) as exc:
            raise PlanWeightError(
                f"invalid canon budget exception expiry {entry.get('expires_at')!r}: {path}") from exc
    return data


def evaluate_canon_budget(budget_path, measurer, *, today=None):
    """Evaluate hard cap, warning threshold, regression allowance, and dated exceptions."""
    budget_path = Path(budget_path)
    budget = load_canon_budget(budget_path)
    canon_path = Path(budget["canon_path"])
    if not canon_path.is_absolute():
        canon_path = _MONOREPO_ROOT / canon_path
    current = measure_document(canon_path, measurer)
    baseline = budget["baseline"]
    hard_cap = measurer.limits["tokens"]
    warning_at = int(hard_cap * budget["warning_fraction"])
    regression_limit = int(
        baseline["est_tokens"] * (1 + budget["regression_percent"] / 100))
    today = today or date.today()
    active = [entry for entry in budget["exceptions"]
              if date.fromisoformat(entry["expires_at"]) >= today]
    cap_exceeded = current["est_tokens"] > hard_cap
    regression_exceeded = current["est_tokens"] > regression_limit
    has_justification = bool((budget.get("regression_justification") or "").strip())
    failures = []
    if cap_exceeded and not active:
        failures.append("hard_cap")
    if regression_exceeded and not has_justification and not active:
        failures.append("regression")
    return {
        "schema": "canon-weight-v1",
        "budget_path": str(budget_path),
        "current": current,
        "baseline": baseline,
        "hard_cap_tokens": hard_cap,
        "warning_threshold_tokens": warning_at,
        "warning": current["est_tokens"] >= warning_at,
        "regression_limit_tokens": regression_limit,
        "regression_justification": budget.get("regression_justification", ""),
        "vendor_line_guidance": budget["vendor_line_guidance"],
        "active_exceptions": active,
        "failures": failures,
        "passes": not failures,
    }


def violated_gate(file_record):
    """Какой из двух гейтов нарушен: `size_bytes` | `tokens` | `both`; `None` — оба ок."""
    gates = file_record["gates"]
    if gates[GATE_SIZE_BYTES] and gates[GATE_TOKENS]:
        return None
    if not gates[GATE_SIZE_BYTES] and not gates[GATE_TOKENS]:
        return GATE_BOTH
    return GATE_SIZE_BYTES if not gates[GATE_SIZE_BYTES] else GATE_TOKENS


# --- резолвинг Required Reads ------------------------------------------------------

def split_entries(value):
    """Значение поля `Required Reads` → список позиций по нумерации `N)`. Нумерации нет
    — всё значение считается ОДНОЙ позицией (а не выбрасывается). Канонический пустой
    плейсхолдер `—` означает отсутствие Required Reads, а не нерезолвленную позицию."""
    text = " ".join((value or "").split())
    if not text or text == EMPTY_PLACEHOLDER:
        return []
    marks = [m for m in ENTRY_NUMBER_RE.finditer(text)]
    if not marks:
        return [text]
    entries = []
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        entry = text[start:end].strip().rstrip(".").strip()
        if entry:
            entries.append(entry)
    return entries


def expand_braces(token):
    """`a/{x,y}.py` → `['a/x.py', 'a/y.py']`. Раскрытие шире `MAX_BRACE_EXPANSION`
    возвращает исходный токен нетронутым (он тогда не путеподобен и уйдёт в пробел)."""
    m = BRACE_GROUP_RE.search(token)
    if not m:
        return [token]
    head, tail = token[:m.start()], token[m.end():]
    out = []
    for alt in m.group(1).split(","):
        alt = alt.strip()
        if not alt:
            continue
        out.extend(expand_braces(head + alt + tail))
        if len(out) > MAX_BRACE_EXPANSION:
            return [token]
    return out or [token]


def _is_path_like(token):
    if not token or not PATH_TOKEN_RE.match(token) or token.endswith("/"):
        return False
    return "/" in token or bool(PATH_SUFFIX_RE.search(token))


def _is_strong_path(token):
    """`каталог/файл.ext` — форма, которую прозой не спутать: и разделитель каталогов,
    и расширение, начинающееся с буквы."""
    return _is_path_like(token) and "/" in token and bool(PATH_SUFFIX_RE.search(token))


def path_candidates(entry):
    """Путеподобные кандидаты позиции в порядке появления: `[(токен, объявлен)]`, где
    `объявлен` — был ли токен в обратных кавычках. ОБЪЯВЛЕННЫЙ путь — утверждение автора
    плана (промах = `missing_file`); голый токен — догадка резолвера (промах молчит,
    позиция остаётся нерезолвленной)."""
    candidates, seen = [], set()

    def take(raw, declared):
        for token in expand_braces(raw.strip()):
            if _is_path_like(token) and token not in seen:
                seen.add(token)
                candidates.append((token, declared))

    for span in BACKTICK_SPAN_RE.findall(entry):
        take(span, True)
    for word in BACKTICK_SPAN_RE.sub(" ", entry).split():
        token = word.strip(BARE_TOKEN_STRIP)
        # Голый токен вида `каталог/файл.ext` — такое же объявление пути, как в бэктиках
        # (форма планов флота до 2026.07); голый токен без расширения («P4
        # finding/research») остаётся догадкой, промах которой пробела не выдумывает.
        take(token, _is_strong_path(token))
    return candidates


def resolve_candidate(token, roots):
    """Первый существующий файл по корням в порядке `roots`; `None` — не найден."""
    p = Path(token)
    if p.is_absolute():
        return p if p.is_file() else None
    for root in roots:
        if root is None:
            continue
        cand = Path(root) / token
        if cand.is_file():
            return cand
    return None


# --- измерение пункта / плана ------------------------------------------------------

def repo_root_for(plan_dir):
    """Корень репозитория плана: ближайший предок каталога `plans/` (архивные планы
    `plans/archive/<ID>` дают тот же корень). Каталог вне `plans/` — родитель плана."""
    plan_dir = Path(plan_dir).resolve()
    for anc in plan_dir.parents:
        if anc.name == "plans":
            return anc.parent
    return plan_dir.parent


class Measurer:
    """Общий контекст замера: артефакты, кэш измеренных файлов (plan.md меряется один раз
    на весь план, а не на каждый пункт), модель окружения."""

    def __init__(self, *, calibration_path=None, read_limit_path=None, model_id=None, provider_id=None):
        try:
            self.artifact = token_estimate.load_artifact(calibration_path)
        except token_estimate.TokenEstimateArtifactError as exc:
            raise PlanWeightError(str(exc)) from exc
        self.limits = load_read_limit(read_limit_path)
        self.model_id = session_model_id(model_id)
        self.provider_id = session_provider_id(provider_id)
        self._cache = {}
        self.warned_model = False
        target = self.artifact["calibration_target"]
        if ((self.model_id and self.model_id != target["requested_model_id"])
                or (self.provider_id and self.provider_id != target["provider"])):
            # WARNING, не блокер (митигация pre-mortem #1): оценка остаётся годной,
            # но её якорь снят под другой моделью — потребитель обязан это видеть.
            print(f"WARNING: plan_weight: калибровка снята под "
                  f"«{target['provider']}/{target['requested_model_id']}», окружение — "
                  f"«{self.provider_id}/{self.model_id}»: оценка может быть неточной", file=sys.stderr)
            self.warned_model = True

    def file(self, path, role):
        key = str(Path(path).resolve())
        cached = self._cache.get(key)
        if cached is None:
            cached = measure_file(path, role=role, artifact=self.artifact,
                                  limits=self.limits,
                                  # WARNING печатает Measurer один раз, не каждый файл.
                                  model_id=None)
            self._cache[key] = cached
        record = dict(cached)
        record["role"] = role
        return record

    def selected(self, raw, *, path, role):
        return measure_bytes(raw, path=path, role=role, artifact=self.artifact,
                             limits=self.limits, model_id=None)


def measure_item(plan_dir, item_id, fields, measurer, *, phase_file=None, repo_root=None,
                 rel_to=None):
    """Вес обязательного пути ОДНОГО пункта, dispatched by declared plan layout.

    Возвращает запись с `files` (разрешённое, с весами) и `gaps` (закрытая таксономия).
    Сумма `weight_tokens` считается по разрешённому подмножеству — перечень пробелов
    печатается ВСЕГДА рядом с ней (иначе это нижняя оценка, выданная за измеренную)."""
    plan_dir = Path(plan_dir)
    repo_root = Path(repo_root) if repo_root is not None else repo_root_for(plan_dir)
    files, gaps, seen = [], [], set()

    root_readable = repo_root.is_dir() and os.access(repo_root, os.R_OK)
    if not root_readable:
        gaps.append({"kind": GAP_UNREADABLE_ROOT, "path": str(repo_root),
                     "detail": "корень репозитория плана недоступен на чтение — "
                               "позиции Required Reads от корня не резолвятся"})

    def add(path, role, entry=None, *, raw=None, selector=None, display_suffix=""):
        resolved_path = Path(path).resolve()
        selector_key = json.dumps(selector or {"kind": "whole_file"}, sort_keys=True)
        key = (str(resolved_path), selector_key)
        if key in seen:
            return False
        seen.add(key)
        try:
            record = (measurer.file(path, role) if raw is None else
                      measurer.selected(raw, path=path, role=role))
        except OSError as exc:
            gaps.append({"kind": GAP_MISSING_FILE, "path": _rel(path, rel_to), "role": role,
                         "entry": entry, "detail": f"файл не читается: {exc}"})
            return False
        record["path"] = f"{_rel(record['path'], rel_to)}{display_suffix}"
        files.append(record)
        gate = violated_gate(record)
        if gate is not None:
            gaps.append({"kind": GAP_OVERSIZED_FILE, "path": record["path"], "role": role,
                         "entry": entry, "gate": gate,
                         "bytes": record["bytes"], "est_tokens": record["est_tokens"],
                         "detail": f"файл не проходит гейт «{gate}» лимита одного чтения "
                                   f"(D2б: обязательная единица должна читаться ОДНИМ вызовом)"})
        return True

    def add_carrier(path, role):
        path = Path(path)
        if path.is_file():
            add(path, role)
        else:
            gaps.append({"kind": GAP_MISSING_FILE, "path": _rel(path, rel_to), "role": role,
                         "entry": None,
                         "detail": "обязательный файл раскладки плана отсутствует"})

    roots = [plan_dir] + ([repo_root] if root_readable else [])
    layout_version = plan_layout.layout_version(plan_dir)
    if layout_version == "v1":
        # Legacy branch is intentionally unchanged: plan → handoff → phase → Required Reads.
        layout = [(plan_dir / "plan.md", "plan"), (plan_dir / "handoff.md", "handoff")]
        if phase_file is not None:
            layout.append((Path(phase_file), "phase"))
        for path, role in layout:
            add_carrier(path, role)

        entries = split_entries(_field(fields, "Required Reads"))
        for entry in entries:
            hits = 0
            declared_misses = 0
            for token, declared in path_candidates(entry):
                resolved = resolve_candidate(token, roots)
                if resolved is not None:
                    hits += 1
                    add(resolved, "required_read", entry=_preview(entry))
                    continue
                if declared:
                    declared_misses += 1
                    gaps.append({"kind": GAP_MISSING_FILE, "path": token,
                                 "role": "required_read", "entry": _preview(entry),
                                 "detail": "путь назван, но файла нет ни под каталогом плана, "
                                           "ни под корнем репозитория"})
            if hits == 0 and declared_misses == 0:
                gaps.append({"kind": GAP_UNRESOLVED_ENTRY, "entry": _preview(entry),
                             "detail": "позиция не приводится к существующему пути — "
                                       "прозой названный вход резолверу недоступен"})
    else:
        try:
            plan_core = plan_layout.plan_core_path(plan_dir)
            item_spec = plan_layout.carrier_path(plan_dir, "item-spec", item_id=item_id)
            bundle_path = plan_layout.carrier_path(plan_dir, "bundle", item_id=item_id)
            state_path = plan_layout.carrier_path(plan_dir, "item-state", item_id=item_id)
        except plan_layout.PlanLayoutError as exc:
            raise PlanWeightError(str(exc)) from exc

        add_carrier(plan_core, "plan-core")
        add_carrier(Path(phase_file) if phase_file is not None else
                    plan_layout.phase_path(plan_dir, item_id.split(".")[0]), "phase-context")
        add_carrier(item_spec, "item-spec")
        add_carrier(bundle_path, "item-input-bundle")

        bundle_fresh = bundle_path.is_file()
        if bundle_fresh:
            try:
                plan_bundle.build(plan_dir, item_id, check=True)
            except plan_bundle.BundleError as exc:
                bundle_fresh = False
                gaps.append({"kind": GAP_UNRESOLVED_ENTRY,
                             "path": _rel(bundle_path, rel_to),
                             "role": "item-input-bundle", "entry": None,
                             "detail": f"generated bundle не byte-fresh: {exc}"})
        if bundle_fresh:
            try:
                bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                bundle = None
                gaps.append({"kind": GAP_UNRESOLVED_ENTRY,
                             "path": _rel(bundle_path, rel_to),
                             "role": "item-input-bundle", "entry": None,
                             "detail": f"generated bundle не читается: {exc}"})
            for unit in bundle.get("entries", ()) if bundle else ():
                source = resolve_candidate(unit["path"], roots)
                if source is None:
                    gaps.append({"kind": GAP_MISSING_FILE, "path": unit["path"],
                                 "role": V2_INPUT_ROLE, "entry": unit.get("declaration_ref"),
                                 "detail": "digest-qualified bundle input отсутствует"})
                    continue
                try:
                    source_raw = source.read_bytes()
                    selected = plan_bundle._selected_bytes(source_raw, unit["selector"], source)
                except (OSError, plan_bundle.BundleError) as exc:
                    gaps.append({"kind": GAP_UNRESOLVED_ENTRY,
                                 "path": _rel(source, rel_to), "role": V2_INPUT_ROLE,
                                 "entry": unit.get("declaration_ref"),
                                 "detail": f"bundle selection не читается: {exc}"})
                    continue
                if (hashlib.sha256(source_raw).hexdigest() != unit["sha256"]
                        or hashlib.sha256(selected).hexdigest() != unit["selected_sha256"]):
                    gaps.append({"kind": GAP_UNRESOLVED_ENTRY,
                                 "path": _rel(source, rel_to), "role": V2_INPUT_ROLE,
                                 "entry": unit.get("declaration_ref"),
                                 "detail": "bundle source/selection digest mismatch"})
                    continue
                selector = unit["selector"]
                suffix = ("" if selector["kind"] == "whole_file" else
                          f"#section:{selector['anchor']}")
                add(source, V2_INPUT_ROLE, entry=unit.get("declaration_ref"), raw=selected,
                    selector=selector, display_suffix=suffix)

        state_fresh = state_path.is_file()
        if state_fresh:
            try:
                plan_item_state.build_states(plan_dir, item_id=item_id, check=True)
            except plan_item_state.ItemStateError as exc:
                gaps.append({"kind": GAP_UNRESOLVED_ENTRY,
                             "path": _rel(state_path, rel_to), "role": "item-state",
                             "entry": None,
                             "detail": f"generated item state не byte-fresh: {exc}"})
        add_carrier(state_path, "item-state")

    weight = sum(f["est_tokens"] for f in files)
    input_roles = {"required_read", V2_INPUT_ROLE}
    floor = sum(f["est_tokens"] for f in files if f["role"] not in input_roles)
    return {
        "item_id": item_id,
        "status": _field(fields, "Status"),
        "files": files,
        "gaps": gaps,
        "weight_tokens": weight,
        "weight_bytes": sum(f["bytes"] for f in files),
        "floor_tokens": floor,
        "required_reads_tokens": weight - floor,
        "resolved_files": len(files),
        "gap_counts": {kind: sum(1 for g in gaps if g["kind"] == kind) for kind in GAP_KINDS},
    }


def _field(fields, name):
    """Значение item-поля. `plan_lint._parse_fields` отдаёт `(значение, строка)`; тесты и
    прямые вызовы вправе передать голую строку — обе формы читаются одинаково."""
    value = fields.get(name, "")
    if isinstance(value, tuple):
        value = value[0]
    return value or ""


def _preview(text, limit=96):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _rel(path, rel_to):
    if rel_to is None:
        return str(path)
    try:
        return str(Path(path).resolve().relative_to(Path(rel_to).resolve()))
    except ValueError:
        return str(path)


def measure_plan(plan_dir, measurer, *, only_item=None):
    """Замер всех пунктов плана (или одного, `only_item`). Разбор фазовых файлов —
    `task.plan_lint.parse_phase_md`: тот же парсер, которым план читает линтер."""
    plan_dir = Path(plan_dir)
    if not (plan_dir / "plan.md").is_file():
        raise PlanWeightError(f"не каталог плана (нет plan.md): {plan_dir}")
    repo_root = repo_root_for(plan_dir)
    diag = plan_lint.Diagnostics()  # диагностика линтера здесь не наша работа — гасится
    meta, _ = plan_lint.parse_plan_md(plan_dir / "plan.md", diag)
    plan_id = (meta or {}).get("Plan ID", (plan_dir.name, None))[0] or plan_dir.name

    items = []
    specs = {}
    try:
        phase_files = plan_layout.phase_paths(plan_dir)
    except plan_layout.PlanLayoutError as exc:
        raise PlanWeightError(str(exc)) from exc
    layout = plan_layout.layout_version(plan_dir)
    for phase_id, phase_path in phase_files.items():
        parsed = plan_lint.parse_phase_md(phase_path, phase_id, diag, layout=layout)
        if parsed is None:
            continue
        for item_id, occurrences in parsed["items"].items():
            occurrence = occurrences[0]
            fields = {k: v for k, v in occurrence["fields"].items()}
            record = measure_item(plan_dir, item_id, fields, measurer,
                                  phase_file=phase_path, repo_root=repo_root, rel_to=repo_root)
            record["phase_id"] = phase_id
            record["title"] = occurrence["title"]
            items.append(record)
            specs[item_id] = {
                "required_read_entries": split_entries(_field(fields, "Required Reads")),
                "deliverables": _field(fields, "Deliverables"),
            }

    if only_item is not None and not any(item["item_id"] == only_item for item in items):
        raise PlanWeightError(f"пункт {only_item} не найден в {plan_dir}")

    admission = None
    if layout == "v2":
        admission = plan_admission.classify(plan_dir, items, specs)
    selected_items = ([item for item in items if item["item_id"] == only_item]
                      if only_item is not None else items)
    if admission is not None and only_item is not None:
        admission = dict(admission)
        admission["counts"] = {
            state: sum(item["admission_state"] == state for item in selected_items)
            for state in plan_admission.STATES
        }
        admission["gap_counts"] = {}
        for item in selected_items:
            for gap in item["admission_gaps"]:
                code = gap["code"]
                admission["gap_counts"][code] = admission["gap_counts"].get(code, 0) + 1
        admission["ready_failed"] = sum(
            item["admission_state"] == plan_admission.STATE_READY
            and item["admission_pass"] is False for item in selected_items)
    gaps_total = sum(len(i["gaps"]) for i in selected_items)
    return {
        "plan_id": plan_id,
        "plan_dir": _rel(plan_dir, repo_root),
        "repo_root": str(repo_root),
        "items": selected_items,
        "totals": {
            "items": len(selected_items),
            "gaps": gaps_total,
            "gap_counts": {kind: sum(i["gap_counts"][kind] for i in selected_items)
                           for kind in GAP_KINDS},
            "max_item_weight_tokens": max((i["weight_tokens"] for i in selected_items), default=0),
            "min_item_weight_tokens": min((i["weight_tokens"] for i in selected_items), default=0),
            "max_floor_tokens": max((i["floor_tokens"] for i in selected_items), default=0),
            "admission": admission,
        },
    }


def sweep(roots, measurer):
    """Замер по нескольким корням (`plans/` либо конкретные `plans/<ID>`) — вход P0.4.
    Корень — учётная единица верхнего уровня (`roots[]`, D110): каждый корень входа
    получает закрытый статус `resolved`/`unreadable`/`missing`, недоступный корень НЕ
    роняет прогон и не уносит остальные (`OSError` вокруг резолвинга перехватывается).
    План, который не удалось разобрать, попадает в `errors` (носитель исхода ПЛАНА,
    не корня) и НЕ роняет прогон: сводка обязана назвать и то, что не измерено."""
    plans, errors, roots_out = [], [], []
    for root in roots:
        try:
            discovered = plan_lint.discover_plan_dirs(Path(root))
        except OSError as exc:
            roots_out.append({"root": str(root), "status": "unreadable", "discovered": 0,
                               "measured": 0, "failed": 0, "detail": str(exc)})
            continue
        if discovered is None:
            roots_out.append({"root": str(root), "status": "missing", "discovered": 0,
                               "measured": 0, "failed": 0,
                               "detail": "корень не существует или не каталог"})
            continue
        measured = failed = 0
        for plan_dir in discovered:
            try:
                plans.append(measure_plan(plan_dir, measurer))
                measured += 1
            except (PlanWeightError, OSError) as exc:
                errors.append({"root": str(root), "plan_dir": str(plan_dir), "error": str(exc)})
                failed += 1
        roots_out.append({"root": str(root), "status": "resolved", "discovered": len(discovered),
                           "measured": measured, "failed": failed, "detail": None})
    return {
        "roots": roots_out,
        "plans": plans,
        "errors": errors,
        "totals": {
            "plans": len(plans),
            "items": sum(p["totals"]["items"] for p in plans),
            "gaps": sum(p["totals"]["gaps"] for p in plans),
            "gap_counts": {kind: sum(p["totals"]["gap_counts"][kind] for p in plans)
                           for kind in GAP_KINDS},
            "roots": {
                "total": len(roots_out),
                "resolved": sum(1 for r in roots_out if r["status"] == "resolved"),
                "unreadable": sum(1 for r in roots_out if r["status"] == "unreadable"),
                "missing": sum(1 for r in roots_out if r["status"] == "missing"),
            },
        },
    }


def envelope(measurer, payload):
    """Стабильная обёртка машинного вывода (`--json`) — ключи не зависят от содержимого."""
    art = measurer.artifact
    out = {
        "schema": SCHEMA,
        "calibration": {
            "version": art["version"],
            "target": art["calibration_target"],
            "safety_multiplier": art["safety_multiplier"],
        },
        "limits": {GATE_SIZE_BYTES: measurer.limits["size_bytes"],
                   GATE_TOKENS: measurer.limits["tokens"],
                   "path": measurer.limits["path"]},
        "session_model_id": measurer.model_id,
        "session_provider_id": measurer.provider_id,
        "dense_ascii_min_run": DENSE_ASCII_MIN_RUN,
    }
    out.update(payload)
    return out


# --- режим --exact (дифференциальный харнесс P0.1, D92) ----------------------------

EXACT_WARNING = (
    "WARNING: --exact — РУЧНОЙ режим разбора пограничного случая, вне CI: истина берётся "
    "из артефакта прогона дифференциального харнесса P0.1 (протокол тройного прогона), "
    "сети инструмент не открывает и `count_tokens` не вызывает")


def load_probe_log(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise PlanWeightError(f"артефакт прогона харнесса не читается: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PlanWeightError(f"артефакт прогона харнесса — невалидный JSON: {path}: {exc}") from exc
    probes = data.get("accepted_samples", data.get("probes"))
    if not isinstance(probes, list):
        raise PlanWeightError(f"артефакт прогона харнесса: нет списка «probes»: {path}")
    return data


def exact_compare(paths, measurer, probe_log_path):
    """Сверка оценки СВЕРХУ с истиной прогона харнесса на явно указанных файлах.
    Файл без записи в артефакте прогона называется прямо («истины нет»), а не молча
    пропускается: пробел в доказательстве — тоже результат замера."""
    import hashlib

    log = load_probe_log(probe_log_path)
    by_sha, by_path = {}, {}
    for rec in log.get("accepted_samples", log["probes"]):
        if rec.get("rejected") or rec.get("true_tokens") is None:
            continue
        sha = rec.get("sample_sha256", rec.get("sha256"))
        if sha:
            by_sha[sha] = rec
        source_path = rec.get("source_path", rec.get("path"))
        if source_path:
            by_path[str(Path(source_path).resolve())] = rec

    rows = []
    for path in paths:
        p = Path(path)
        if not p.is_file():
            rows.append({"path": str(p), "error": "файла нет"})
            continue
        text = p.read_bytes().decode("utf-8", errors="replace")
        est = token_estimate.estimate_text(text, artifact=measurer.artifact)
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        rec = by_sha.get(sha) or by_path.get(str(p.resolve()))
        row = {"path": str(p), "est_tokens": est, "sha256": sha,
               "dense_ascii_share": dense_ascii_share(text)}
        if rec is None:
            row["truth"] = None
            row["match"] = None
            row["note"] = ("истины нет в артефакте прогона харнесса — файл не входил в "
                           "корпус P0.1 либо изменился с момента прогона")
        else:
            truth = float(rec["true_tokens"])
            row["truth"] = truth
            row["match"] = "sha256" if sha in by_sha else "path"
            row["true_over_estimate"] = (truth / est) if est else None
            row["understated"] = bool(est < truth)
        rows.append(row)
    return {"probe_log": str(probe_log_path), "files": rows,
            "understated": sum(1 for r in rows if r.get("understated"))}


# --- человекочитаемый вывод --------------------------------------------------------

def _fmt_item(record, limits):
    lines = [f"  {record['item_id']} — {record.get('title', '')}".rstrip(),
             f"    вес: {record['weight_tokens']} токенов оценкой сверху "
             f"({record['weight_bytes']} байт, файлов {record['resolved_files']}); "
             f"пол раскладки: {record['floor_tokens']}, Required Reads: "
             f"{record['required_reads_tokens']}"]
    over = [g for g in record["gaps"] if g["kind"] == GAP_OVERSIZED_FILE]
    if over:
        lines.append(f"    сверх лимита одного чтения "
                     f"({limits['size_bytes']} байт / {limits['tokens']} токенов): {len(over)}")
    # Перечень пробелов печатается ВСЕГДА — сумма без него была бы нижней оценкой,
    # выданной за измеренную (research/02 §5).
    if record["gaps"]:
        lines.append(f"    пробелы ({len(record['gaps'])}):")
        for gap in record["gaps"]:
            gate = f" gate={gap['gate']}" if gap.get("gate") else ""
            target = gap.get("path") or gap.get("entry") or ""
            lines.append(f"      [{gap['kind']}{gate}] {target}")
    else:
        lines.append("    пробелы: нет")
    if "admission_state" in record:
        verdict = ("pass" if record["admission_pass"] is True else
                   "fail" if record["admission_pass"] is False else "deferred")
        producer = (f"; producer={record['producer_item']}"
                    if record.get("producer_item") else "")
        lines.append(f"    admission: {record['admission_state']} — {verdict}{producer}")
        for gap in record.get("admission_gaps", []):
            target = gap.get("path") or gap.get("entry") or gap.get("detail") or ""
            lines.append(f"      [{gap['code']}] {target}")
    return lines


def _print_plan(plan, limits):
    print(f"план {plan['plan_id']} ({plan['plan_dir']}) — пунктов {plan['totals']['items']}, "
          f"пробелов {plan['totals']['gaps']}")
    for record in plan["items"]:
        for line in _fmt_item(record, limits):
            print(line)
    counts = plan["totals"]["gap_counts"]
    print(f"  итого: макс. вес пункта {plan['totals']['max_item_weight_tokens']} токенов, "
          f"мин. {plan['totals']['min_item_weight_tokens']}, макс. пол "
          f"{plan['totals']['max_floor_tokens']}; пробелы по категориям: "
          + ", ".join(f"{k}={counts[k]}" for k in GAP_KINDS))


# --- CLI ---------------------------------------------------------------------------

def _add_common_options(parser, suppress):
    """Общие опции — и до подкоманды, и после неё (`plan <dir> --json` — форма Validation
    P0.3). У подкоманд дефолты подавлены: иначе argparse затирал бы ими значение,
    заданное ДО подкоманды."""
    import argparse

    flag_default = argparse.SUPPRESS if suppress else False
    opt_default = argparse.SUPPRESS if suppress else None
    parser.add_argument("--json", action="store_true", default=flag_default,
                        help="машинный вывод (стабильные ключи)")
    parser.add_argument("--calibration", default=opt_default,
                        help="путь к артефакту калибровки P0.1 (по умолчанию — configs/)")
    parser.add_argument("--read-limit", default=opt_default,
                        help="путь к артефакту лимита чтения P0.2 (по умолчанию — configs/)")
    parser.add_argument("--session-model", default=opt_default,
                        help="модель текущего окружения для WARNING о расхождении с калибровкой")


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="plan-weight",
        description="Вес обязательного чтения пункта плана (plan-exec.md §1) в оценочных "
                    "токенах, с проверкой каждого файла против обоих гейтов лимита чтения "
                    "и закрытой таксономией пробелов.")
    _add_common_options(parser, suppress=False)
    parser.add_argument("--exact", nargs="+", metavar="FILE", default=None,
                        help="РУЧНОЙ режим (вне CI): сверить оценку с истиной прогона "
                             "дифференциального харнесса P0.1 на указанных файлах")
    parser.add_argument("--probe-log", default=None,
                        help="артефакт прогона харнесса P0.1 для --exact")
    parser.add_argument("--file", default=None,
                        help="измерить один документ (токены и строки)")

    common = argparse.ArgumentParser(add_help=False)
    _add_common_options(common, suppress=True)

    sub = parser.add_subparsers(dest="cmd")
    p_item = sub.add_parser("item", help="вес одного пункта", parents=[common])
    p_item.add_argument("plan_dir")
    p_item.add_argument("item_id")
    p_plan = sub.add_parser("plan", help="вес каждого пункта плана", parents=[common])
    p_plan.add_argument("plan_dir")
    p_sweep = sub.add_parser("sweep", help="замер по корням планов (вход P0.4)", parents=[common])
    p_sweep.add_argument("roots", nargs="+")
    p_canon = sub.add_parser("canon", help="D93: двухпороговый гейт веса канона",
                             parents=[common])
    p_canon.add_argument("--budget", default=str(DEFAULT_CANON_BUDGET_PATH))

    args = parser.parse_args(argv)
    if args.exact is None and args.file is None and args.cmd is None:
        parser.error("нужна подкоманда item|plan|sweep|canon либо режим --file/--exact")

    try:
        measurer = Measurer(calibration_path=args.calibration,
                            read_limit_path=args.read_limit,
                            model_id=args.session_model)
        if args.exact is not None:
            print(EXACT_WARNING, file=sys.stderr)
            probe_log = args.probe_log or DEFAULT_PROBE_LOG_PATH
            payload = exact_compare(args.exact, measurer, probe_log)
            if args.json:
                print(json.dumps(envelope(measurer, {"exact": payload}),
                                 ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"истина: {payload['probe_log']}")
                for row in payload["files"]:
                    if row.get("error"):
                        print(f"  {row['path']}: {row['error']}")
                    elif row["truth"] is None:
                        print(f"  {row['path']}: оценка {row['est_tokens']} — {row['note']}")
                    else:
                        print(f"  {row['path']}: оценка {row['est_tokens']}, истина "
                              f"{row['truth']:.0f}, истина/оценка "
                              f"{row['true_over_estimate']:.3f}"
                              + ("  ← ЗАНИЖЕНИЕ" if row["understated"] else ""))
            return 0

        if args.file is not None:
            payload = measure_document(args.file, measurer)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"{payload['path']}: {payload['est_tokens']} tokens, "
                      f"{payload['lines']} lines")
            return 0

        if args.cmd == "canon":
            payload = evaluate_canon_budget(args.budget, measurer)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                before = payload["baseline"]
                current = payload["current"]
                print(f"canon before: {before['est_tokens']} tokens, {before['lines']} lines "
                      f"@ {before['git_anchor']}")
                print(f"canon after: {current['est_tokens']} tokens, {current['lines']} lines "
                      f"@ working-tree")
                print(f"hard cap: {payload['hard_cap_tokens']} tokens; warning: "
                      f"{payload['warning_threshold_tokens']} tokens; regression limit: "
                      f"{payload['regression_limit_tokens']} tokens")
                print(f"vendor guidance: under {payload['vendor_line_guidance']} lines "
                      f"(independent guidance; current {current['lines']})")
                if payload["active_exceptions"]:
                    expiries = ", ".join(e["expires_at"] for e in payload["active_exceptions"])
                    print(f"active dated exception(s), expiry: {expiries}")
                if payload["warning"]:
                    print("WARNING: canon reached the warning threshold", file=sys.stderr)
                if payload["failures"]:
                    print("ERROR: canon budget failed: "
                          + ", ".join(payload["failures"]), file=sys.stderr)
            return 0 if payload["passes"] else 3

        if args.cmd == "sweep":
            payload = sweep(args.roots, measurer)
            if args.json:
                print(json.dumps(envelope(measurer, payload), ensure_ascii=False,
                                 indent=2, sort_keys=True))
            else:
                for root in payload["roots"]:
                    if root["status"] in ("unreadable", "missing"):
                        print(f"НЕ ИЗМЕРЕН: {root['root']}: {root['detail']}")
                    elif root["status"] == "resolved" and root["discovered"] == 0:
                        print(f"БЕЗ ПЛАНОВ: {root['root']}")
                for plan in payload["plans"]:
                    _print_plan(plan, measurer.limits)
                for err in payload["errors"]:
                    print(f"НЕ ИЗМЕРЕН: {err['plan_dir']}: {err['error']}")
                counts = payload["totals"]["gap_counts"]
                root_counts = payload["totals"]["roots"]
                print(f"итого: планов {payload['totals']['plans']}, пунктов "
                      f"{payload['totals']['items']}, пробелов {payload['totals']['gaps']} ("
                      + ", ".join(f"{k}={counts[k]}" for k in GAP_KINDS) + "), корней "
                      f"{root_counts['total']} (resolved={root_counts['resolved']}, "
                      f"unreadable={root_counts['unreadable']}, missing={root_counts['missing']})")
            return 0

        only = args.item_id if args.cmd == "item" else None
        plan = measure_plan(args.plan_dir, measurer, only_item=only)
        if args.json:
            print(json.dumps(envelope(measurer, plan), ensure_ascii=False,
                             indent=2, sort_keys=True))
        else:
            _print_plan(plan, measurer.limits)
        return 0
    except PlanWeightError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
