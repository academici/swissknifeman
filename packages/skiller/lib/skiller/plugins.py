"""plugins — видимость marketplace-плагинов Claude Code в первом ходе (P1.1).

`skiller budget --first-turn` видит только проектную поверхность; плагин
резидентен в КАЖДОЙ сессии (~449/~450 ток always-on,
`plans/2026.07.31-SKM-LEAN/findings/P1-plugin-cli-probe-2026-07-31.md` §3), но
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

_ALWAYS_ON_RE = re.compile(r"(?m)^\s*Always-on:\s*~(\d+)\s*tok\b")

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
    (entries, status, warnings): status — 'ok'|'n/a'; warnings — диагностики
    апстрима из ключа `errors` записей листинга."""
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
    warnings = []
    for entry in data:
        if not isinstance(entry, dict) or not entry.get("enabled") or not entry.get("id"):
            continue
        if entry.get("errors"):
            warnings.append(f"{entry['id']}: {'; '.join(entry['errors'])}")
        dedup.setdefault(entry["id"], entry)
    return list(dedup.values()), "ok", warnings


def plugin_always_on_tokens(plugin_id):
    """Always-on цена ОДНОГО плагина — единственная строка `Always-on: ~N tok`
    вывода `claude plugin details <id>`. `details` описывает ПЛАГИН, не
    проект, и от CWD не зависит → кэш по `id` в пределах прогона (фан-аут по
    флоту иначе платит проект×плагин вместо уникальных плагинов). Возвращает
    (tokens|None, detail|None); суффикс (`~1.1k`) в замере не наблюдался — при
    несовпадении регэкспа строка уходит в unparsed, множитель не угадывается."""
    if plugin_id in _details_cache:
        return _details_cache[plugin_id]
    ok, stdout, detail = _run_claude(["plugin", "details", plugin_id])
    if not ok:
        result = (None, detail)
    else:
        m = _ALWAYS_ON_RE.search(stdout)
        result = ((int(m.group(1)), None) if m else
                 (None, f"{plugin_id}: строка Always-on не распознана"))
    _details_cache[plugin_id] = result
    return result


def plugins_summary(target):
    """Сводка always-on плагинов проекта `target`:
    `{status, entries[], total, partial, unparsed[], warnings[]}`. `entries` —
    `{id, scope, tokens}` (tokens=None на нераспознанной цене). `total` считает
    ТОЛЬКО распознанные записи; `partial=True`, если хоть одна не распозналась
    ИЛИ листинг целиком дал n/a. Молчаливого 0 нет ни в одной ветке."""
    plugins, status, list_warnings = list_enabled_plugins(target)
    if status != "ok":
        return {"status": "n/a", "entries": [], "total": None, "partial": True,
               "unparsed": [], "warnings": list_warnings}
    entries = []
    unparsed = []
    total = 0
    for entry in plugins:
        pid = entry["id"]
        tokens, error = plugin_always_on_tokens(pid)
        entries.append({"id": pid, "scope": entry.get("scope"), "tokens": tokens})
        if tokens is None:
            unparsed.append(error)
        else:
            total += tokens
    entries.sort(key=lambda e: (e["id"], e["scope"] or ""))
    return {"status": "ok", "entries": entries, "total": total,
           "partial": bool(unparsed), "unparsed": unparsed, "warnings": list_warnings}
