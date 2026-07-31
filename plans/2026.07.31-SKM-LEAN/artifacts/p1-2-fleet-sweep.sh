#!/usr/bin/env bash
# P1.2 — разовый обход флота: `skiller budget --first-turn --with-plugins` по каждой
# `enabled`-записи `config.json`. Артефакт плана (2026.07.31-SKM-LEAN P1.2), судьба —
# архив плана; не CLI-команда, baseline — замер, а не продуктовая фича (D17).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SKM_BIN="$ROOT/packages/skiller/bin/skiller"
CONFIG="$ROOT/config.json"
OUT="${1:-$ROOT/plans/2026.07.31-SKM-LEAN/findings/P1-fleet-baseline.md}"

SHA="$(git -C "$ROOT" rev-parse --short HEAD)"
STAMP="$(date -u '+%Y-%m-%d %H:%M UTC')"

SKM_BIN="$SKM_BIN" CONFIG="$CONFIG" OUT="$OUT" SHA="$SHA" STAMP="$STAMP" python3 - <<'PY'
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

skm_bin = os.environ["SKM_BIN"]
config_path = os.environ["CONFIG"]
out_path = os.environ["OUT"]
sha = os.environ["SHA"]
stamp = os.environ["STAMP"]

# Implementation Rules §8 — таймаут поднят под факт после P1.4: кэш `details`
# модульный (не переносится между процессами обхода), проект с ~17 плагинами
# платит ~13с (замер на swissknifeman этой сессии) + SessionStart-хуки (10с).
PER_PROJECT_TIMEOUT = 150

with open(config_path) as f:
    config = json.load(f)

projects = [p for p in config.get("projects", []) if p.get("enabled", True) is not False]

BRIEF = {
    "swissknifeman": 10757,
    "agelto": 32611,
    "flexcrm": 29354,
    "botkit": 10843,
    "diabox": 11996,
}

# D80 — первый заход (2026-07-31, до починки P1.4) снял `memster` `plugins Σ` =
# 2946 при `plugins.partial: true` на 22/22 строк; занижение подтверждено
# независимым ручным сравнением (`findings/P1-plugins-cwd-defect-2026-07-31.md`).
# Живёт только как факт этой записи — в git не попал.
PRE_P14_MEMSTER_PLUGINS_TOTAL = 2946

rows = []
measured = 0
skipped = 0
stale = 0

for p in projects:
    pid = p.get("id")
    local = p.get("local_path")
    path = Path(os.path.expanduser(local)).resolve() if local else None
    is_stale_entry = pid == "local-repo"
    if is_stale_entry:
        stale += 1
    if not path or not path.is_dir():
        skipped += 1
        reason = "stale registry entry (local_path не существует)" if is_stale_entry else "local_path не существует"
        rows.append({"id": pid, "path": str(path) if path else local, "na": True, "reason": reason})
        continue
    try:
        r = subprocess.run(
            [skm_bin, "budget", "--first-turn", "--with-plugins", "--target", str(path), "--json"],
            capture_output=True, text=True, timeout=PER_PROJECT_TIMEOUT, check=False)
        if r.returncode != 0:
            skipped += 1
            reason = f"exit {r.returncode}: {r.stderr.strip()[:200]}"
            rows.append({"id": pid, "path": str(path), "na": True, "reason": reason})
            continue
        data = json.loads(r.stdout)
    except subprocess.TimeoutExpired:
        skipped += 1
        rows.append({"id": pid, "path": str(path), "na": True,
                     "reason": f"timeout {PER_PROJECT_TIMEOUT}с"})
        continue
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        skipped += 1
        rows.append({"id": pid, "path": str(path), "na": True,
                     "reason": f"{type(exc).__name__}: {exc}"})
        continue

    measured += 1
    src = data.get("sources", {})
    plugins = data.get("plugins", {})
    rows.append({
        "id": pid, "path": str(path), "na": False,
        "skills": src.get("skills", {}).get("tokens"),
        "agents": src.get("agents", {}).get("tokens"),
        "claude_md": src.get("claude_md", {}).get("tokens"),
        "hooks": src.get("hooks", {}).get("tokens"),
        "mcp": src.get("mcp", {}).get("tokens"),
        "total": data.get("total"),
        "verdict": data.get("verdict"),
        "plugins_total": plugins.get("total"),
        "plugins_partial": plugins.get("partial"),
        "plugins_unparsed": plugins.get("unparsed", []),
        "plugins_broken": plugins.get("broken", []),
        "plugins_warnings": plugins.get("warnings", []),
        "session_total": data.get("session_total"),
        "session_verdict": data.get("session_verdict"),
    })

session_totals = [r["session_total"] for r in rows if not r["na"] and r.get("session_total") is not None]

def pct(data, q):
    if not data:
        return None
    s = sorted(data)
    k = (len(s) - 1) * q
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)

buckets = {"OK": 0, "ELEVATED": 0, "WARN": 0}
for r in rows:
    if not r["na"] and r.get("session_verdict"):
        buckets[r["session_verdict"]] = buckets.get(r["session_verdict"], 0) + 1

measured_rows = [r for r in rows if not r["na"]]
# Implementation Rules §9 (D81) — триггер эскалации считает ДОЛЮ строк с
# НЕОБЪЯСНЁННОЙ неполнотой (непустой unparsed). `broken` (сам листинг объявил
# плагин сломанным, сегодня — известный `brain@brain`) триггером НЕ является.
unparsed_rows = [r for r in measured_rows if r.get("plugins_unparsed")]
broken_rows = [r for r in measured_rows if r.get("plugins_broken")]
unparsed_ratio = (len(unparsed_rows) / len(measured_rows)) if measured_rows else 0.0

KNOWN_BROKEN_IDS = {"brain@brain"}
unknown_broken = sorted({
    entry["id"] for r in broken_rows for entry in r["plugins_broken"]
    if entry["id"] not in KNOWN_BROKEN_IDS
})

lines = []
lines.append("# P1-fleet-baseline — резидентный первый ход по флоту")
lines.append("")
lines.append(f"Якорь: swissknifeman `{sha}`, снято {stamp}. Измеритель: "
             f"`skiller budget --first-turn --with-plugins` (после починки P1.4 — "
             f"`cwd`-резолвинг local-scope, тысячный разделитель, класс `broken` "
             f"отделён от `unparsed`). Хуковая составляющая (SessionStart живьём, "
             f"таймаут 10с на проект) средо-зависима — побайтовая воспроизводимость "
             f"между прогонами НЕ гарантируется.")
lines.append("")
lines.append(f"Записей реестра (enabled): {len(projects)} · измерено: {measured} · "
             f"пропущено (n/a): {skipped} · из них stale (`id: local-repo`): {stale}")
lines.append("")
lines.append("## Таблица по флоту")
lines.append("")
lines.append("| id | skills | agents | claude_md | hooks | mcp | total | verdict | "
             "plugins Σ | session_total | session_verdict |")
lines.append("|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|:--|")
for r in rows:
    if r["na"]:
        lines.append(f"| {r['id']} | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | "
                     f"n/a ({r['reason']}) |")
        continue
    note = ""
    if r.get("plugins_unparsed"):
        note += " ⚠unparsed"
    if r.get("plugins_broken"):
        note += " ⛔broken"
    lines.append(
        f"| {r['id']} | {r['skills']} | {r['agents']} | {r['claude_md']} | {r['hooks']} | "
        f"{r['mcp']} | {r['total']} | {r['verdict']} | {r['plugins_total']}{note} | "
        f"{r['session_total']} | {r['session_verdict']} |")
lines.append("")
lines.append("Каждое `n/a` — причина в той же строке таблицы (см. столбец `n/a (...)`).")
lines.append("")
lines.append(f"Доля строк с необъяснённой неполнотой (`unparsed`, if-then-триггер D81): "
             f"{len(unparsed_rows)}/{len(measured_rows)} "
             f"({unparsed_ratio * 100:.0f}%). Порог эскалации — четверть измеренных строк.")
lines.append("")
lines.append("## Записи класса `broken`")
lines.append("")
if broken_rows:
    lines.append("Сам листинг объявил плагин сломанным (`errors`) — известный дефект "
                 "ЧУЖОГО репозитория, не дрейф формата этого измерителя.")
    lines.append("")
    lines.append("| проект | plugin id | причина |")
    lines.append("|:--|:--|:--|")
    for r in broken_rows:
        for entry in r["plugins_broken"]:
            reason = " ".join(entry["reason"].split())
            lines.append(f"| {r['id']} | {entry['id']} | {reason} |")
else:
    lines.append("Нет записей класса `broken` среди измеренных строк.")
lines.append("")
if unknown_broken:
    lines.append(f"**Новый факт:** `broken` у плагина(ов), которых нет в известном перечне "
                 f"`findings/P1-plugins-cwd-defect-2026-07-31.md` §5 — {', '.join(unknown_broken)}. "
                 f"Не подшито к известному `brain@brain`, называется отдельно (Code Guidance).")
    lines.append("")
lines.append("## Сводная статистика (по измеренным строкам)")
lines.append("")
lines.append(f"Число строк, по которым считаны перцентили: {len(session_totals)} "
             f"(`session_total`, плагин-инклюзивный).")
if session_totals:
    lines.append("")
    lines.append(f"- min: {min(session_totals)}")
    lines.append(f"- медиана: {statistics.median(session_totals):.0f}")
    lines.append(f"- p75: {pct(session_totals, 0.75):.0f}")
    lines.append(f"- p90: {pct(session_totals, 0.90):.0f}")
    lines.append(f"- max: {max(session_totals)}")
lines.append("")
lines.append(f"Распределение по действующим порогам (`session_verdict`, "
             f"n={sum(buckets.values())}): OK={buckets['OK']} · "
             f"ELEVATED={buckets['ELEVATED']} · WARN={buckets['WARN']}")
lines.append("")
lines.append("## До/после починки P1.4 (контрольный проект `memster`)")
lines.append("")
memster = by_id_lookup = next((r for r in rows if r["id"] == "memster" and not r["na"]), None)
if memster is not None:
    after = memster["plugins_total"]
    delta = (after - PRE_P14_MEMSTER_PLUGINS_TOTAL) if after is not None else None
    lines.append(f"Первый заход (до починки P1.4, дефектный, отброшен D80, живёт только как "
                 f"факт этой записи — в git не попал): `plugins Σ` = "
                 f"{PRE_P14_MEMSTER_PLUGINS_TOTAL} при `plugins.partial: true` на 22/22 "
                 f"измеренных строк того прогона.")
    lines.append("")
    lines.append(f"Этот прогон (после починки P1.4): `plugins Σ` = {after}"
                 + (f" (дельта {delta:+d})" if delta is not None else "") + ".")
else:
    lines.append("`memster` не измерен этим прогоном (см. таблицу выше, столбец `n/a`) — "
                 "сравнение до/после недоступно.")
lines.append("")
lines.append("## Бриф → замер → дельта (пять чисел из `brief/00-brief.md`)")
lines.append("")
lines.append("`total` (проектная поверхность, БЕЗ плагинов) сравнивается с числом брифа — "
             "брифовые замеры не несли `--with-plugins`.")
lines.append("")
lines.append("| id | бриф | замер (`total`) | дельта | замер (`session_total`) |")
lines.append("|:--|--:|--:|--:|--:|")
by_id = {r["id"]: r for r in rows if not r["na"]}
for bid, bval in BRIEF.items():
    r = by_id.get(bid)
    if r is None:
        lines.append(f"| {bid} | {bval} | n/a | n/a | n/a |")
        continue
    delta = r["total"] - bval
    lines.append(f"| {bid} | {bval} | {r['total']} | {delta:+d} | {r['session_total']} |")
lines.append("")
lines.append("Расхождения объясняются дрейфом измеряемых проектов между сессией брифа и "
             "этим прогоном (состав скиллов/MCP/агентов меняется независимо от плана) и "
             "тем, что `total` брифа не включал marketplace-плагины (P1.1) — не подгонкой.")
lines.append("")
lines.append("## Границы этого замера")
lines.append("")
lines.append("Файл — сырьё для P1.3 (порог) и не выбирает вариант A/B/C. Read-only по "
             "отношению к измеряемым репозиториям; реестр (4 stale-записи `local-repo`) "
             "этим item'ом не чистится (D15).")

Path(out_path).write_text("\n".join(lines) + "\n")
print(f"измерено: {measured} / пропущено: {skipped} / stale: {stale} / всего: {len(projects)}")
print(f"unparsed ratio: {unparsed_ratio*100:.1f}% ({len(unparsed_rows)}/{len(measured_rows)})")
if unparsed_ratio > 0.25:
    print("ESCALATION-TRIGGER: unparsed ratio > 25%", file=sys.stderr)
    sys.exit(2)
PY
