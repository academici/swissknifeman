#!/usr/bin/env bash
# P3.1 — A/B-стенд нативных полей скиллов на живой версии Claude Code
# (plan 2026.07.31-SKM-LEAN, item P3.1). Механика прибора пинована прогонами
# на 2.1.220 — findings/P3.1-bench-harness-probe-2026-08-01.md (D94).
#
# Гоняемые пары (ровно одно поле frontmatter отличается A от B):
#   paths · disable-model-invocation · when_to_use · context:fork · model · effort
#
# Наблюдаемая величина оси A (D94): usage.input_tokens + usage.cache_creation_input_tokens
# + usage.cache_read_input_tokens (верхнеуровневый usage, НЕ modelUsage) — три компонента
# публикуются раздельно по каждому прогону, вердикт по МЕДИАНЕ суммы.
#
# Изоляция: рабочий workspace — временный каталог ВНЕ дерева репозитория (фикстуры
# копируются из p3-1-fixtures/), флаг --setting-sources project обязателен,
# CLAUDE_CONFIG_DIR запрещён (уносит OAuth на среде владельца).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/p3-1-fixtures"
SKM_BIN="$ROOT/packages/skiller/bin/skiller"

MODE="run"
case "${1:-}" in
  -h|--help) MODE="help" ;;
  --self-check) MODE="self-check" ;;
  --paths-mechanism) MODE="paths-mechanism" ;;
  "") MODE="run" ;;
  *) echo "unknown flag: $1 (use --help)" >&2; exit 2 ;;
esac

FIXTURES_DIR="$FIXTURES_DIR" ROOT="$ROOT" SKM_BIN="$SKM_BIN" MODE="$MODE" \
  SKM_CLAUDE_BIN="${SKM_CLAUDE_BIN:-}" python3 - <<'PY'
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURES_DIR = Path(os.environ["FIXTURES_DIR"])
ROOT = Path(os.environ["ROOT"])
SKM_BIN = os.environ["SKM_BIN"]
MODE = os.environ["MODE"]
CLAUDE_BIN_ENV = os.environ.get("SKM_CLAUDE_BIN") or ""

TIMEOUT = 180  # eval.py DEFAULT_TIMEOUT (packages/skiller/lib/skiller/quality/eval.py:49)

MARKERS = {
    "zz-p31-ctrl": "ZZP31-CTRL-BODY",
    "zz-p31-paths": "ZZP31-PATHS-BODY",
    "zz-p31-disable": "ZZP31-DISABLE-BODY",
    "zz-p31-whentouse": "ZZP31-WHENTOUSE-BODY",
    "zz-p31-forkctrl": "ZZP31-FORKCTRL-BODY",
    "zz-p31-fork": "ZZP31-FORK-BODY",
    "zz-p31-model": "ZZP31-MODEL-BODY",
    "zz-p31-effort": "ZZP31-EFFORT-BODY",
}
ALL_SKILLS = list(MARKERS)

AXIS_A_PAIRS = [
    ("paths", "zz-p31-ctrl", "zz-p31-paths"),
    ("disable-model-invocation", "zz-p31-ctrl", "zz-p31-disable"),
    ("when_to_use", "zz-p31-ctrl", "zz-p31-whentouse"),
    ("context: fork", "zz-p31-forkctrl", "zz-p31-fork"),
    ("model", "zz-p31-ctrl", "zz-p31-model"),
    ("effort", "zz-p31-ctrl", "zz-p31-effort"),
]

LISTING_PROMPT = "List the names of every skill available to you, one per line. Nothing else."
TRIGGER_PROMPT = "zzp31trigger — please proceed accordingly."

# P3.6 — дозамер механизма paths: (research/11-p3-paths-mechanism-2026-08-01.md §4).
# Единственная переменная — совпадает ли файл в workspace с glob скилла. Существующий
# _root/probe.zzp31paths непригоден (называет скилл по имени, findings/P3-native-fields-smoke.md
# §3.1) — используется отдельная чистая фикстура.
PATHS_MATCH_FILE = "probe-clean.zzp31paths"
PATHS_NOMATCH_FILE = "probe.txt"
B2_PROMPT = ("There is exactly one file in the current directory. First, open and read its "
             "contents. Then run /zz-p31-paths and reply with only what it outputs.")
B3_PROMPT = ("There is exactly one file in the current directory. First, open and read its "
             "contents. Then say exactly: " + TRIGGER_PROMPT)


def claude_bin():
    """Резолв бинаря claude: env-override SKM_CLAUDE_BIN -> PATH (форма eval.py:377-384)."""
    if CLAUDE_BIN_ENV:
        p = Path(os.path.expanduser(CLAUDE_BIN_ENV))
        return str(p) if p.exists() else None
    return shutil.which("claude")


def help_text():
    return f"""p3-1-native-fields-bench.sh — A/B-стенд нативных полей скиллов (P3.1, plan 2026.07.31-SKM-LEAN)

Гоняемые пары (A -> B, ровно одно поле frontmatter отличается):
  1) paths                      zz-p31-ctrl -> zz-p31-paths
  2) disable-model-invocation   zz-p31-ctrl -> zz-p31-disable
  3) when_to_use                zz-p31-ctrl -> zz-p31-whentouse
  4) context: fork               zz-p31-forkctrl -> zz-p31-fork
  5) model                      zz-p31-ctrl -> zz-p31-model
  6) effort                     zz-p31-ctrl -> zz-p31-effort

Наблюдаемая величина оси A (D94): sum = usage.input_tokens + usage.cache_creation_input_tokens
+ usage.cache_read_input_tokens (верхнеуровневый `usage`, источник фиксирован, не меняется
между прогонами). Каждое плечо пары гоняется 3 раза, порядок чередуется (A,B,B,A,A,B),
публикуется медиана суммы и разброс (max-min); |delta| <= max(spreadA, spreadB) => "неразличимо".

Ось B (авто-активация/видимость) — сильный сигнал: уникальный маркер тела пробника в `result`
при exit 0; для явного пути — `claude -p '/<имя-пробника>'`.

Обязательные флаги/изоляция: --setting-sources project, env -u CLAUDE_CODE_SESSION_ID
-u CLAUDE_CODE_CHILD_SESSION; CLAUDE_CONFIG_DIR НЕ используется (уносит OAuth). Рабочий
workspace — временный каталог вне дерева репозитория, разворачивается копией фикстур из
p3-1-fixtures/ и убирается за собой.

Флаги:
  --help             эта справка (код 0)
  --self-check       офлайн-проверка прибора без единого сетевого прогона (код 0/1)
  --paths-mechanism  дозамер механизма paths: (P3.6) — шесть плеч, отдельный подрежим,
                     полную матрицу НЕ трогает (код 0/1)
  (без флагов)       полный прогон стенда (код 0/1) — печатает по каждому прогону три
                     компонента usage + сумму, по каждой паре — медиану, дельту, разброс,
                     число прогонов, и по полям context/model/effort/paths/disable-model-invocation
                     строки со strong-signal проверками (маркер в result).

Плечи --paths-mechanism (research/11-p3-paths-mechanism-2026-08-01.md §4), единственная
переменная — совпадает ли root-файл workspace с glob `*.zzp31paths` скилла zz-p31-paths:
  A1  zz-p31-paths, root=probe.txt (не совпадает) -> root=probe-clean.zzp31paths (совпадает)
      наблюдаемая величина: дельта медианы суммы usage (та же формула, что ось A выше)
  A2  zz-p31-ctrl, тот же пара root-файлов — калибровка: обязана быть «неразличимо»
      наблюдаемая величина: дельта медианы суммы usage
  B0  `/zz-p31-paths` без root-файла (ре-baseline)
      наблюдаемая величина: exit + маркер ZZP31-PATHS-BODY в result
  B1  `/zz-p31-paths` при совпавшем root-файле
      наблюдаемая величина: exit + маркер в result
  B2  промпт «прочитать файл, затем вызвать скилл явно» при совпавшем root-файле
      наблюдаемая величина: exit + маркер в result
  B3  промпт «прочитать файл, затем триггер-фраза» при совпавшем root-файле
      наблюдаемая величина: exit + маркер в result

Клиент: {claude_bin() or '(claude не найден)'}
"""


def deploy(skills, root_files=None):
    tmp = Path(tempfile.mkdtemp(prefix="p3-1-bench-"))
    skills_dir = tmp / ".claude" / "skills"
    skills_dir.mkdir(parents=True)
    for name in skills:
        shutil.copytree(FIXTURES_DIR / name, skills_dir / name)
    for fname in root_files or []:
        shutil.copy(FIXTURES_DIR / "_root" / fname, tmp / fname)
    return tmp


def run_claude(ws, prompt, claude, extra_args=None):
    cmd = [claude, "-p", prompt, "--output-format", "json", "--setting-sources", "project"]
    if extra_args:
        cmd += extra_args
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env.pop("CLAUDE_CODE_CHILD_SESSION", None)
    print(f"  $ cd {ws} && env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION \\")
    print(f"      {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True,
                           timeout=TIMEOUT, env=env, check=False)
    raw = proc.stdout
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        data = None
    return {
        "cmd": cmd, "returncode": proc.returncode, "raw": raw, "stderr": proc.stderr,
        "data": data if isinstance(data, dict) else {},
    }


def axis_a_sum(data):
    usage = data.get("usage") or {}
    i = usage.get("input_tokens", 0) or 0
    cc = usage.get("cache_creation_input_tokens", 0) or 0
    cr = usage.get("cache_read_input_tokens", 0) or 0
    return i, cc, cr, i + cc + cr


def _alternating_order(n):
    order = []
    pattern = ["A", "B", "B", "A", "A", "B"]
    ai = bi = 0
    for tag in (pattern * ((n * 2 // len(pattern)) + 1)):
        if tag == "A" and ai < n:
            order.append("A"); ai += 1
        elif tag == "B" and bi < n:
            order.append("B"); bi += 1
        if ai >= n and bi >= n:
            break
    return order


def _axis_a_verdict(sums):
    med_a, med_b = statistics.median(sums["A"]), statistics.median(sums["B"])
    spread_a = max(sums["A"]) - min(sums["A"]) if len(sums["A"]) > 1 else 0
    spread_b = max(sums["B"]) - min(sums["B"]) if len(sums["B"]) > 1 else 0
    delta = med_b - med_a
    spread = max(spread_a, spread_b)
    verdict = "неразличимо" if abs(delta) <= spread else ("выросла" if delta > 0 else "снизилась")
    return {"median_a": med_a, "median_b": med_b, "spread_a": spread_a, "spread_b": spread_b,
            "delta": delta, "verdict": verdict}


def run_axis_a_pair(claude, field, skill_a, skill_b, n=3):
    order = _alternating_order(n)
    print(f"\n=== ось A: {field} ({skill_a} -> {skill_b}), порядок плеч: {','.join(order)} ===")
    sums = {"A": [], "B": []}
    for i, tag in enumerate(order, 1):
        skill = skill_a if tag == "A" else skill_b
        ws = deploy([skill])
        try:
            res = run_claude(ws, LISTING_PROMPT, claude)
        finally:
            shutil.rmtree(ws, ignore_errors=True)
        it, cc, cr, s = axis_a_sum(res["data"])
        sums[tag].append(s)
        print(f"  прогон {i} [{tag}={skill}] exit={res['returncode']} "
              f"input={it} cache_creation={cc} cache_read={cr} sum={s}")
    stats = _axis_a_verdict(sums)
    print(f"  медиана A={stats['median_a']} (разброс {stats['spread_a']})  "
          f"медиана B={stats['median_b']} (разброс {stats['spread_b']})  "
          f"delta={stats['delta']:+.0f}  вердикт(ось A)={stats['verdict']}  "
          f"n={len(sums['A'])}+{len(sums['B'])}")
    return {"field": field, "skill_a": skill_a, "skill_b": skill_b, "sums": sums, **stats}


def run_paths_axis_a_pair(claude, label, skill, root_files_a, root_files_b, n=3):
    """A1/A2 — тот же скилл на обоих плечах, различие ТОЛЬКО в root-файле workspace
    (research/11-p3-paths-mechanism-2026-08-01.md §4)."""
    order = _alternating_order(n)
    print(f"\n=== ось A ({label}, paths-mechanism): {skill} "
          f"(root={root_files_a or '—'} -> root={root_files_b or '—'}), "
          f"порядок плеч: {','.join(order)} ===")
    sums = {"A": [], "B": []}
    for i, tag in enumerate(order, 1):
        rf = root_files_a if tag == "A" else root_files_b
        ws = deploy([skill], root_files=rf)
        try:
            res = run_claude(ws, LISTING_PROMPT, claude)
        finally:
            shutil.rmtree(ws, ignore_errors=True)
        it, cc, cr, s = axis_a_sum(res["data"])
        sums[tag].append(s)
        print(f"  прогон {i} [{tag}, root={rf or '—'}] exit={res['returncode']} "
              f"input={it} cache_creation={cc} cache_read={cr} sum={s}")
    stats = _axis_a_verdict(sums)
    print(f"  медиана A={stats['median_a']} (разброс {stats['spread_a']})  "
          f"медиана B={stats['median_b']} (разброс {stats['spread_b']})  "
          f"delta={stats['delta']:+.0f}  вердикт(ось A)={stats['verdict']}  "
          f"n={len(sums['A'])}+{len(sums['B'])}")
    return {"label": label, "skill": skill, "sums": sums, **stats}


def strong_signal(claude, label, skill, prompt, root_files=None):
    ws = deploy([skill], root_files=root_files)
    try:
        res = run_claude(ws, prompt, claude)
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    result_text = res["data"].get("result", "") or ""
    found = MARKERS[skill] in result_text
    print(f"  [{label}] skill={skill} exit={res['returncode']} marker_found={found}")
    return {"label": label, "skill": skill, "exit": res["returncode"], "found": found,
            "result": result_text, "data": res["data"]}


def self_check():
    ok = True
    c = claude_bin()
    if c:
        print(f"[ok] claude найден: {c}")
    else:
        print("[FAIL] claude не найден ни через SKM_CLAUDE_BIN, ни через PATH")
        ok = False
    for name in ALL_SKILLS:
        f = FIXTURES_DIR / name / "SKILL.md"
        if f.is_file():
            print(f"[ok] фикстура на месте: {f.relative_to(ROOT)}")
        else:
            print(f"[FAIL] фикстура отсутствует: {f}")
            ok = False
    for f in ("CLAUDE.md", "probe.zzp31paths", "probe.txt", PATHS_MATCH_FILE):
        p = FIXTURES_DIR / "_root" / f
        if p.is_file():
            print(f"[ok] root-фикстура на месте: {p.relative_to(ROOT)}")
        else:
            print(f"[FAIL] root-фикстура отсутствует: {p}")
            ok = False
    clean_fixture = FIXTURES_DIR / "_root" / PATHS_MATCH_FILE
    if clean_fixture.is_file():
        text = clean_fixture.read_text(encoding="utf-8")
        clean_ok = "zz-p31-paths" not in text and MARKERS["zz-p31-paths"] not in text
        control_size = (FIXTURES_DIR / "_root" / "probe.txt").stat().st_size
        size_ok = abs(clean_fixture.stat().st_size - control_size) <= control_size * 0.10
        if clean_ok and size_ok:
            print(f"[ok] чистая фикстура {PATHS_MATCH_FILE}: без имени/маркера скилла, "
                  f"размер сопоставим с контролем")
        else:
            print(f"[FAIL] чистая фикстура {PATHS_MATCH_FILE}: clean={clean_ok} size_ok={size_ok}")
            ok = False
    tmp = deploy(["zz-p31-ctrl"], root_files=["CLAUDE.md"])
    try:
        is_outside = ROOT not in tmp.parents and tmp != ROOT
        deployed_ok = (tmp / ".claude" / "skills" / "zz-p31-ctrl" / "SKILL.md").is_file()
        print(f"[ok] workspace развёрнут вне дерева репозитория: {tmp} (outside={is_outside})")
        if not (is_outside and deployed_ok):
            print("[FAIL] развёртывание workspace не прошло проверку изоляции")
            ok = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    cleaned = not tmp.exists()
    print(f"[ok] workspace убран за собой: cleaned={cleaned}")
    ok = ok and cleaned
    return ok


def full_run():
    claude = claude_bin()
    if not claude:
        print("🔴 ESCALATION P3.1: `claude` недоступен как процесс | trigger: unclear acceptance | "
              "нужен: plan-design", file=sys.stderr)
        return False
    proc = subprocess.run([claude, "--version"], capture_output=True, text=True, check=False)
    print(f"claude --version -> {proc.stdout.strip()}")

    report = {"version": proc.stdout.strip(), "axis_a": [], "strong": []}

    for field, sa, sb in AXIS_A_PAIRS:
        report["axis_a"].append(run_axis_a_pair(claude, field, sa, sb))

    print("\n=== ось B / strong-signal: discovery, авто-активация, explicit ===")
    report["strong"].append(strong_signal(claude, "paths.explicit", "zz-p31-paths",
                                           "/zz-p31-paths"))
    report["strong"].append(strong_signal(claude, "paths.auto.match", "zz-p31-paths",
        "There is exactly one file in the current directory. Open it and follow its "
        "instructions exactly, replying with only what it tells you to reply.",
        root_files=["probe.zzp31paths"]))
    report["strong"].append(strong_signal(claude, "paths.auto.nomatch", "zz-p31-paths",
        "There is exactly one file in the current directory. Open it and follow its "
        "instructions exactly, replying with only what it tells you to reply.",
        root_files=["probe.txt"]))

    report["strong"].append(strong_signal(claude, "disable.explicit", "zz-p31-disable",
                                           "/zz-p31-disable"))
    report["strong"].append(strong_signal(claude, "disable.auto", "zz-p31-disable", TRIGGER_PROMPT))
    report["strong"].append(strong_signal(claude, "disable.auto.ctrl", "zz-p31-ctrl", TRIGGER_PROMPT))

    report["strong"].append(strong_signal(claude, "fork.explicit.ctrl", "zz-p31-forkctrl",
                                           "/zz-p31-forkctrl", root_files=["CLAUDE.md"]))
    report["strong"].append(strong_signal(claude, "fork.explicit.fork", "zz-p31-fork",
                                           "/zz-p31-fork", root_files=["CLAUDE.md"]))
    report["strong"].append(strong_signal(claude, "fork.auto.ctrl", "zz-p31-forkctrl",
                                           TRIGGER_PROMPT, root_files=["CLAUDE.md"]))
    report["strong"].append(strong_signal(claude, "fork.auto.fork", "zz-p31-fork",
                                           TRIGGER_PROMPT, root_files=["CLAUDE.md"]))

    print("\n=== model: modelUsage ===")
    for skill in ("zz-p31-ctrl", "zz-p31-model"):
        ws = deploy([skill])
        try:
            res = run_claude(ws, f"/{skill}", claude)
        finally:
            shutil.rmtree(ws, ignore_errors=True)
        mu = res["data"].get("modelUsage") or {}
        print(f"  [{skill}] exit={res['returncode']} modelUsage keys={sorted(mu.keys())}")
        report["strong"].append({"label": f"model.{skill}", "skill": skill,
                                  "exit": res["returncode"],
                                  "found": MARKERS[skill] in (res["data"].get("result") or ""),
                                  "modelUsage_keys": sorted(mu.keys())})

    print("\n=== effort: наличие прибора в конверте ===")
    ws = deploy(["zz-p31-effort"])
    try:
        res = run_claude(ws, "/zz-p31-effort", claude)
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    top_keys = sorted(res["data"].keys())
    has_effort_key = any("effort" in k.lower() for k in top_keys)
    print(f"  exit={res['returncode']} top-level keys={top_keys}")
    print(f"  ключ с 'effort' в верхнем уровне конверта: {has_effort_key} (ожидание: False -> "
          f"вердикт 'прибора нет')")
    report["strong"].append({"label": "effort.envelope", "skill": "zz-p31-effort",
                              "exit": res["returncode"], "top_level_keys": top_keys,
                              "has_effort_key": has_effort_key})

    print("\n=== сверка с моделью budget.py (все фикстуры на одном workspace) ===")
    combined_ws = deploy(ALL_SKILLS)
    try:
        budget_proc = subprocess.run(
            [SKM_BIN, "budget", "--first-turn", "--target", str(combined_ws), "--json"],
            capture_output=True, text=True, check=False)
        print(f"  $ {SKM_BIN} budget --first-turn --target {combined_ws} --json")
        try:
            budget_data = json.loads(budget_proc.stdout)
        except (json.JSONDecodeError, TypeError):
            budget_data = {}
        print(f"  модель: total={budget_data.get('total')} verdict={budget_data.get('verdict')}")
        obs = run_claude(combined_ws, LISTING_PROMPT, claude)
        it, cc, cr, s = axis_a_sum(obs["data"])
        print(f"  наблюдение (сумма usage): {s} (input={it} cache_creation={cc} cache_read={cr})")
        report["sync"] = {"model_total": budget_data.get("total"),
                           "model_verdict": budget_data.get("verdict"),
                           "observed_sum": s}
    finally:
        shutil.rmtree(combined_ws, ignore_errors=True)

    print("\n=== JSON report ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return True


def paths_mechanism_run():
    """P3.6 — дозамер механизма paths: шесть плеч A1/A2/B0/B1/B2/B3
    (research/11-p3-paths-mechanism-2026-08-01.md §4). Не трогает состав полной
    матрицы P3.1 (`full_run`) — отдельный подрежим."""
    claude = claude_bin()
    if not claude:
        print("🔴 ESCALATION P3.6: `claude` недоступен как процесс | trigger: unclear "
              "acceptance | нужен: plan-design", file=sys.stderr)
        return False
    proc = subprocess.run([claude, "--version"], capture_output=True, text=True, check=False)
    print(f"claude --version -> {proc.stdout.strip()}")

    report = {"version": proc.stdout.strip(), "axis_a": [], "strong": []}

    a1 = run_paths_axis_a_pair(claude, "A1", "zz-p31-paths",
                                [PATHS_NOMATCH_FILE], [PATHS_MATCH_FILE])
    report["axis_a"].append(a1)
    a2 = run_paths_axis_a_pair(claude, "A2", "zz-p31-ctrl",
                                [PATHS_NOMATCH_FILE], [PATHS_MATCH_FILE])
    report["axis_a"].append(a2)

    if a2["verdict"] != "неразличимо":
        print("\n🔴 ESCALATION P3.6: прибор не различает совпадение файла и его присутствие "
              "| trigger: unclear acceptance | нужен: plan-design", file=sys.stderr)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return False

    print("\n=== ось B / strong-signal: B0 (re-baseline) .. B3 (после чтения) ===")
    report["strong"].append(strong_signal(claude, "B0", "zz-p31-paths", "/zz-p31-paths"))
    report["strong"].append(strong_signal(claude, "B1", "zz-p31-paths", "/zz-p31-paths",
                                           root_files=[PATHS_MATCH_FILE]))
    report["strong"].append(strong_signal(claude, "B2", "zz-p31-paths", B2_PROMPT,
                                           root_files=[PATHS_MATCH_FILE]))
    report["strong"].append(strong_signal(claude, "B3", "zz-p31-paths", B3_PROMPT,
                                           root_files=[PATHS_MATCH_FILE]))

    print("\n=== JSON report (paths-mechanism) ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return True


if MODE == "help":
    print(help_text())
    sys.exit(0)
elif MODE == "self-check":
    ok = self_check()
    sys.exit(0 if ok else 1)
elif MODE == "paths-mechanism":
    ok = paths_mechanism_run()
    sys.exit(0 if ok else 1)
else:
    ok = full_run()
    sys.exit(0 if ok else 1)
PY
