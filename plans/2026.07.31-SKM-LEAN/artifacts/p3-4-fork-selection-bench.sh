#!/usr/bin/env bash
# P3.4 — поштучная проверка на стенде РЕАЛЬНЫХ скиллов, отобранных под context: fork
# (plan 2026.07.31-SKM-LEAN, item P3.4). Тот же контракт изоляции, что у P3.1
# (findings/P3.1-bench-harness-probe-2026-08-01.md, D94), применённый к РЕАЛЬНЫМ файлам
# реестра вместо синтетических фикстур zz-p31-* — отдельный артефакт, p3-1-native-fields-bench.sh
# не трогается (handoff.md Open risks: «стенд не умеет гонять произвольный бакет» —
# режим на реальный бакет заводится явным ТЗ этого item'а, не попутной правкой P3.1).
#
# Изоляция: рабочий workspace — временный каталог ВНЕ дерева репозитория, --setting-sources
# project обязателен, env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION,
# CLAUDE_CONFIG_DIR не используется. Каждый workspace убирается за собой.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SKILLS_ROOT="$ROOT/packages/skiller/skills"

MODE="run"
case "${1:-}" in
  -h|--help) MODE="help" ;;
  "") MODE="run" ;;
  *) echo "unknown flag: $1 (use --help)" >&2; exit 2 ;;
esac

ROOT="$ROOT" SKILLS_ROOT="$SKILLS_ROOT" MODE="$MODE" SKM_CLAUDE_BIN="${SKM_CLAUDE_BIN:-}" \
  python3 - <<'PY'
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ["ROOT"])
SKILLS_ROOT = Path(os.environ["SKILLS_ROOT"])
MODE = os.environ["MODE"]
CLAUDE_BIN_ENV = os.environ.get("SKM_CLAUDE_BIN") or ""
TIMEOUT = 420

CANDIDATES = [
    ("devops", "node-pnpm-preflight"),
    ("devops", "db-test-preflight"),
    ("quality", "refactoring-plan"),
    ("oss-dev", "resolving-merge-conflicts"),
]


def claude_bin():
    if CLAUDE_BIN_ENV:
        p = Path(os.path.expanduser(CLAUDE_BIN_ENV))
        return str(p) if p.exists() else None
    return shutil.which("claude")


def help_text():
    return """p3-4-fork-selection-bench.sh — поштучная проверка REAL-скиллов под context: fork (P3.4)

Кандидаты (bucket/name): devops/node-pnpm-preflight · devops/db-test-preflight ·
quality/refactoring-plan · oss-dev/resolving-merge-conflicts

Флаги:
  --help   эта справка (код 0)
  (нет)    полный прогон: explicit `/name` + авто-триггер по прогону, для КАЖДОГО
           кандидата, печатает exit/result; код 0/1
"""


def deploy_skill(bucket, name, extra=None):
    """Раскладка ФЛОТА — плоско по `name`, bucket отбрасывается (skillset.py:14,38:
    `.claude/skills/<name>/` физические копии, видит Claude), НЕ bucket/name реестра."""
    tmp = Path(tempfile.mkdtemp(prefix="p3-4-bench-"))
    skills_dir = tmp / ".claude" / "skills" / name
    skills_dir.parent.mkdir(parents=True)
    shutil.copytree(SKILLS_ROOT / bucket / name, skills_dir)
    if extra:
        extra(tmp)
    return tmp


def run_claude(ws, prompt, claude):
    cmd = [claude, "-p", prompt, "--output-format", "json", "--setting-sources", "project"]
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env.pop("CLAUDE_CODE_CHILD_SESSION", None)
    print(f"  $ cd {ws} && env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION \\")
    print(f"      {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True,
                           timeout=TIMEOUT, env=env, check=False)
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        data = {}
    return {"returncode": proc.returncode, "data": data if isinstance(data, dict) else {},
            "stderr": proc.stderr}


def run_case(claude, label, bucket, name, prompt, extra=None):
    ws = deploy_skill(bucket, name, extra=extra)
    try:
        res = run_claude(ws, prompt, claude)
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    result = (res["data"].get("result") or "").strip()
    nonempty = len(result) > 0 and "Unknown command" not in result and "Unknown skill" not in result
    print(f"  [{label}] {bucket}/{name} exit={res['returncode']} nonempty={nonempty} "
          f"len(result)={len(result)}")
    print(f"    result[:400]: {result[:400]!r}")
    return {"label": label, "bucket": bucket, "name": name, "exit": res["returncode"],
            "nonempty": nonempty, "result": result}


def git_conflict_repo(tmp):
    """Готовит реальный конфликт merge в workspace: main правит строку 1, feature — ту же строку.
    Identity-env ОБЯЗАН быть на КАЖДОМ git-вызове, включая merge (git резолвит identity до
    конфликта на некоторых версиях, иначе rc=128 «unable to auto-detect email» и MERGE_HEAD
    не создаётся вовсе — найдено этим прогоном, см. findings/P3-fork-selection.md)."""
    git_env = {**os.environ, "GIT_AUTHOR_NAME": "p3-4-bench",
               "GIT_AUTHOR_EMAIL": "p3-4-bench@example.invalid",
               "GIT_COMMITTER_NAME": "p3-4-bench",
               "GIT_COMMITTER_EMAIL": "p3-4-bench@example.invalid",
               "HOME": str(tmp)}

    def sh(*args, check=True):
        r = subprocess.run(["git", *args], cwd=str(tmp), capture_output=True, text=True, env=git_env)
        if check and r.returncode != 0:
            raise RuntimeError(f"git {args} failed: {r.stderr}")
        return r

    (tmp / "greeting.txt").write_text("hello from main\n", encoding="utf-8")
    sh("init", "-q", "-b", "main")
    sh("add", "greeting.txt")
    sh("commit", "-q", "-m", "base")
    sh("checkout", "-q", "-b", "feature")
    (tmp / "greeting.txt").write_text("hello from feature\n", encoding="utf-8")
    sh("commit", "-q", "-am", "feature edit")
    sh("checkout", "-q", "main")
    (tmp / "greeting.txt").write_text("hello from main, edited\n", encoding="utf-8")
    sh("commit", "-q", "-am", "main edit")
    sh("merge", "feature", "-q", check=False)  # ожидаемый конфликт, rc=1 — не check
    if not (tmp / ".git" / "MERGE_HEAD").exists():
        raise RuntimeError("git_conflict_repo: MERGE_HEAD not created — fixture broken")


def self_check():
    ok = True
    c = claude_bin()
    if c:
        print(f"[ok] claude найден: {c}")
    else:
        print("[FAIL] claude не найден"); ok = False
    for bucket, name in CANDIDATES:
        f = SKILLS_ROOT / bucket / name / "SKILL.md"
        if f.is_file() and "context: fork" in f.read_text(encoding="utf-8"):
            print(f"[ok] {bucket}/{name}: context: fork на месте")
        else:
            print(f"[FAIL] {bucket}/{name}: context: fork отсутствует"); ok = False
    return ok


def full_run():
    claude = claude_bin()
    if not claude:
        print("🔴 claude недоступен как процесс", file=sys.stderr)
        return False
    proc = subprocess.run([claude, "--version"], capture_output=True, text=True, check=False)
    print(f"claude --version -> {proc.stdout.strip()}")
    if not self_check():
        return False

    report = []

    print("\n=== devops/node-pnpm-preflight ===")
    report.append(run_case(claude, "explicit", "devops", "node-pnpm-preflight",
                            "/node-pnpm-preflight"))
    report.append(run_case(claude, "auto", "devops", "node-pnpm-preflight",
                            "I'm about to run a git commit and the commitlint hook needs pnpm — "
                            "make sure Node/pnpm are ready first."))

    print("\n=== devops/db-test-preflight ===")
    report.append(run_case(claude, "explicit", "devops", "db-test-preflight",
                            "/db-test-preflight"))
    report.append(run_case(claude, "auto", "devops", "db-test-preflight",
                            "I'm about to run the Postgres test suite (php artisan test) and "
                            "tests fail on DB connection — check the test DB first."))

    print("\n=== quality/refactoring-plan ===")
    report.append(run_case(claude, "explicit", "quality", "refactoring-plan",
                            "/refactoring-plan"))
    report.append(run_case(claude, "auto", "quality", "refactoring-plan",
                            "I need to plan a safe refactor of a tangled billing module using "
                            "the Mikado method, with atomic steps and a rollback plan."))

    print("\n=== oss-dev/resolving-merge-conflicts (реальный git-конфликт в workspace) ===")
    report.append(run_case(claude, "explicit", "oss-dev", "resolving-merge-conflicts",
                            "/resolving-merge-conflicts", extra=git_conflict_repo))
    report.append(run_case(claude, "auto", "oss-dev", "resolving-merge-conflicts",
                            "I'm in the middle of a git merge and greeting.txt has a conflict — "
                            "help me resolve it.", extra=git_conflict_repo))

    print("\n=== JSON report ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    all_nonempty = all(r["nonempty"] for r in report)
    return all_nonempty


if MODE == "help":
    print(help_text())
    sys.exit(0)
else:
    ok = full_run()
    sys.exit(0 if ok else 1)
PY
