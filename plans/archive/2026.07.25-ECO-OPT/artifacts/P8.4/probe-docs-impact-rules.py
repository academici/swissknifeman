#!/usr/bin/env python3
"""Замер триггер-правил docs-impact гейта (2026.07.25-ECO-OPT P8.4, рефайн 2026-07-27).

НЕ реализация гейта — измерительный зонд: прогоняет четыре кандидатных правила триггера
по истории репо и печатает, сколько change-set'ов каждое правило покрасило бы.

  A — любая правка файла-поверхности (форма спеки research/11 §4)
  B — только появление/удаление/переименование файла в поверхности
  C — B + правка интерфейсных путей (bin/ · commands/ · configs/ · install.sh)
  D — C + правка lib/, добавляющая/убирающая символ верхнего уровня (def/class/CONST)

Гранулярности: по коммитам (`--commits N`) и по PR (`--prs N`, merge-коммиты, база —
merge-base родителей). Зачёт доков — карта из ТЗ P8.4 (пакет-скоуп).

Запуск: python3 plans/2026.07.25-ECO-OPT/artifacts/P8.4/probe-docs-impact-rules.py
"""
from __future__ import annotations

import argparse
import re
import subprocess

# --- поверхности (класс изменения) -------------------------------------------------
SURFACE_PKG = re.compile(r"^packages/([^/]+)/(bin|lib|commands|configs)/")
SURFACE_CORE = re.compile(r"^core/.*\.py$")
SURFACE_ROOT = re.compile(r"^(bin/|install\.sh$|scripts/[^/]+\.(sh|py)$)")

# --- НЕ поверхности: исключение .md сужено до ДОК-md (иначе 161 файл commands/configs
#     проглатывается правилом «**/*.md — доки сами») ----------------------------------
NON_SURFACE = [
    re.compile(r"(^|/)tests?/"),
    re.compile(r"^scripts/test-"),
    re.compile(r"^plans/"),
    re.compile(r"^\.github/"),
    re.compile(r"^docs/"),
    re.compile(r"^packages/[^/]+/docs/"),
    re.compile(r"^[^/]+\.md$"),
    re.compile(r"^packages/[^/]+/(CLAUDE|README|CHANGELOG)\.md$"),
    re.compile(r"^packages/skiller/skills/"),
]

INTERFACE = re.compile(r"^(packages/[^/]+/(bin|commands|configs)/|bin/|install\.sh$)")
TOP_SYMBOL = re.compile(r"^[+-](def |class |[A-Z][A-Z0-9_]+ *=)")


def surface(path: str):
    if any(rx.search(path) for rx in NON_SURFACE):
        return None
    m = SURFACE_PKG.match(path)
    if m:
        return "pkg:" + m.group(1)
    if SURFACE_CORE.match(path):
        return "core"
    if SURFACE_ROOT.match(path):
        return "root"
    return None


def credit(path: str):
    m = re.match(r"^packages/([^/]+)/docs/", path)
    if m:
        return "pkg:" + m.group(1)
    if path.startswith("docs/task/"):          # tracked, ручные доки пакета task
        return "pkg:task"
    if path.startswith("docs/core/"):
        return "core"
    if re.match(r"^docs/[^/]+\.md$", path):
        return "root"
    return None


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout


def classify(name_status_lines, diff_getter):
    """→ (need_by_rule, credits): какие классы требуют доков по каждому правилу."""
    need = {k: set() for k in "ABCD"}
    credits = set()
    modified_lib = []
    for line in name_status_lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        status, path = parts[0][0], parts[-1]
        klass = surface(path)
        if klass:
            need["A"].add(klass)
            if status in "ADR":
                for rule in "BCD":
                    need[rule].add(klass)
            elif INTERFACE.match(path):
                need["C"].add(klass)
                need["D"].add(klass)
            elif status == "M":
                modified_lib.append((path, klass))
        got = credit(path)
        if got:
            credits.add(got)
    if modified_lib:
        diff = diff_getter([p for p, _ in modified_lib])
        current = None
        for line in diff.split("\n"):
            if line.startswith("+++ b/"):
                current = line[6:]
            elif current and TOP_SYMBOL.match(line):
                for path, klass in modified_lib:
                    if path == current:
                        need["D"].add(klass)
    return need, credits


def run_commits(limit):
    total = 0
    red = {k: 0 for k in "ABCD"}
    for line in git("log", "--format=%H", "-n", str(limit)).split():
        sha = line
        lines = git("diff-tree", "--no-commit-id", "--name-status", "-M", "-r", sha).split("\n")
        need, credits = classify(
            lines, lambda paths, sha=sha: git("show", "--format=", "--unified=0", sha, "--", *paths)
        )
        if not need["A"]:
            continue
        total += 1
        for rule in "ABCD":
            if need[rule] - credits:
                red[rule] += 1
    return total, red


def run_prs(limit):
    total = 0
    red = {k: 0 for k in "ABCD"}
    rows = [l.split() for l in git("log", "--merges", "--format=%H %P", "-n", str(limit)).strip().split("\n") if l]
    for row in rows:
        if len(row) < 3:
            continue
        merge, first, second = row[0], row[1], row[2]
        base = git("merge-base", first, second).strip()
        lines = git("diff", "--name-status", "-M", base, second).split("\n")
        need, credits = classify(
            lines,
            lambda paths, base=base, head=second: git("diff", "--unified=0", base, head, "--", *paths),
        )
        if not need["A"]:
            continue
        total += 1
        for rule in "ABCD":
            if need[rule] - credits:
                red[rule] += 1
    return total, red


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commits", type=int, default=200)
    ap.add_argument("--prs", type=int, default=14)
    args = ap.parse_args()
    head = git("rev-parse", "--short", "HEAD").strip()
    print(f"дерево: {head}")
    total, red = run_commits(args.commits)
    print(f"коммиты (последние {args.commits}): с тронутой поверхностью = {total}")
    for rule in "ABCD":
        print(f"  правило {rule}: красных {red[rule]} ({red[rule] * 100 // max(total, 1)}%)")
    total, red = run_prs(args.prs)
    print(f"PR (последние {args.prs} merge-коммитов): с тронутой поверхностью = {total}")
    for rule in "ABCD":
        print(f"  правило {rule}: красных {red[rule]} ({red[rule] * 100 // max(total, 1)}%)")


if __name__ == "__main__":
    main()
