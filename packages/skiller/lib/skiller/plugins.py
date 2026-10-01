"""plugins — видимость marketplace-плагинов Claude Code в первом ходе.

`skiller budget --first-turn` видит только проектную поверхность; плагин
резидентен в КАЖДОЙ сессии (~449/~450 ток always-on,
 §3), но
измерителем не учитывается. Этот модуль склеивает два вывода чужого CLI —
`claude plugin list --json` (перечисление, CWD-зависимо, недокументированный
флаг) и `claude plugin details <id>` (Always-on-цена, текстовый вывод, своего
`--json` нет) — в одну сводку. Fail-loud: любой сбой даёт `tokens=None`, а не
молчаливый 0 (0 читается как «плагинов нет» и делает измеритель лживым ровно
там, где он должен предупреждать)."""
import json
import re
import subprocess

from .quality.eval import CLAUDE_BIN_ENV, claude_bin

PLUGIN_CALL_TIMEOUT = 15

_ALWAYS_ON_RE = re.compile(r"(?m)^\s*Always-on:\s*~([\d,]+)\s*tok\b")

_details_cache = {}


def _run_claude(argv, *, cwd=None, timeout=PLUGIN_CALL_TIMEOUT):
    """Вызов `claude <argv>`. (ok, stdout|None, detail|None) — detail заполнен
    только на неудаче и называет причину (fail-loud, не молчаливый провал)."""
    claude = claude_bin()
    if claude is None:
        return False, None, f"claude не найден (см. {CLAUDE_BIN_ENV}/PATH)"
    try:
        r = subprocess.run([claude, *argv], cwd=cwd, capture_output=True,
                           text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return False, None, f"claude {' '.join(argv)} — таймаут {timeout}с"
    except OSError as error:
        return False, None, f"claude {' '.join(argv)} — {type(error).__name__}"
    if r.returncode != 0:
        return False, None, f"claude {' '.join(argv)} — код {r.returncode}"
    return True, r.stdout, None


def list_enabled_plugins(target):
    """Enabled-плагины проекта `target`, дедуплицированные по `id` (один `id`
    приходит дважды при разных `scope` — `claude plugin list --json` резолвит
    эффективный набор ПРОЕКТА через `cwd=target`, разбор `enabledPlugins` из
    `settings.json` не делается — отвергнутая D142 конструкция). Возвращает
    (entries, status, detail): status — 'ok'|'n/a'; на 'n/a' detail называет
    причину. Записи несут поле `errors` листинга как есть — классификация
    `broken` против `unparsed` требует ИСХОДА `details` и решается позже, в
    `plugins_summary`, не здесь."""
    ok, stdout, detail = _run_claude(["plugin", "list", "--json"], cwd=str(target))
    if not ok:
        return [], "n/a", [detail]
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return [], "n/a", ["claude plugin list --json — невалидный JSON"]
    if not isinstance(data, list):
        return [], "n/a", ["claude plugin list --json — ожидался список записей"]
    dedup = {}
    for entry in data:
        if not isinstance(entry, dict) or not entry.get("enabled") or not entry.get("id"):
            continue
        dedup.setdefault(entry["id"], entry)
    return list(dedup.values()), "ok", []


def plugin_always_on_tokens(plugin_id, cwd):
    """Always-on цена ОДНОГО плагина — единственная строка `Always-on: ~N tok`
    вывода `claude plugin details <id>`. `details` резолвит local-scope
    плагин ТОЛЬКО под `cwd` его проекта (RAG:✅ 2026-07-31 живой `claude
    2.1.220`: `architect@swissknifeman` — код 1 без `cwd`, код 0 под
    `cwd=memster`) — `cwd` ОБЯЗАТЕЛЬНЫЙ параметр, догадываться о нём внутри
    модуля запрещено. ЗНАЧЕНИЕ цены при этом не меняется между CWD (проверено
    на четырёх плагинах из двух CWD) → успех кэшируется по `id` глобально,
    экономя фан-аут по флоту; неудача (резолвинг ИЛИ разбор) НЕ кэшируется —
    тот же `id` под другим `cwd` в следующем вызове резолвится заново, иначе
    первый же чужой проект отравил бы кэш на весь прогон. Возвращает
    (tokens|None, detail|None); суффикс (`~1.1k`) в замере не наблюдался — при
    несовпадении регэкспа строка уходит в unparsed, множитель не угадывается."""
    if plugin_id in _details_cache:
        return _details_cache[plugin_id]
    ok, stdout, detail = _run_claude(["plugin", "details", plugin_id], cwd=str(cwd))
    if not ok:
        return None, detail
    m = _ALWAYS_ON_RE.search(stdout)
    if not m:
        return None, f"{plugin_id}: строка Always-on не распознана"
    tokens = int(m.group(1).replace(",", ""))
    result = (tokens, None)
    _details_cache[plugin_id] = result
    return result


def plugins_summary(target):
    """Сводка always-on плагинов проекта `target`:
    `{status, entries[], total, partial, unparsed[], broken[], warnings[]}`.
    `entries` — `{id, scope, tokens}` (tokens=None на невзятой цене). `total`
    считает ТОЛЬКО распознанные записи; `partial=True`, если хоть одна не
    распозналась (`unparsed`/`broken` непусты) ИЛИ листинг целиком дал n/a.
    Неполнота — ДВЕ разные природы, не смешиваются в одном списке: `broken[]`
    (`{id, reason}`) — сам листинг объявил плагин сломанным (`errors`) И
    `details` цену не дал; `unparsed[]` — details не распознан БЕЗ объявленной
    поломки (дрейф формата апстрима). Запись с `errors`, ВСЁ-ТАКИ отдавшая
    цену, обычная: учитывается в `total`, `errors` — в `warnings[]`.
    Молчаливого 0 нет ни в одной ветке."""
    plugins, status, list_warnings = list_enabled_plugins(target)
    if status != "ok":
        return {"status": "n/a", "entries": [], "total": None, "partial": True,
               "unparsed": [], "broken": [], "warnings": list_warnings}
    entries = []
    unparsed = []
    broken = []
    warnings = []
    total = 0
    for entry in plugins:
        pid = entry["id"]
        errors = entry.get("errors")
        tokens, error = plugin_always_on_tokens(pid, target)
        entries.append({"id": pid, "scope": entry.get("scope"), "tokens": tokens})
        if tokens is None:
            if errors:
                broken.append({"id": pid, "reason": "; ".join(errors)})
            else:
                unparsed.append(error)
        else:
            total += tokens
            if errors:
                warnings.append(f"{pid}: {'; '.join(errors)}")
    entries.sort(key=lambda e: (e["id"], e["scope"] or ""))
    return {"status": "ok", "entries": entries, "total": total,
           "partial": bool(unparsed or broken), "unparsed": unparsed,
           "broken": broken, "warnings": warnings}
