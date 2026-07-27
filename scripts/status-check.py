#!/usr/bin/env python3
"""Проверка docs/status.md: зрелость из словаря, непустой Evidence, известный пакет, без дублей.

Ревалидация послойная (P8.5): читает ОДИН файл docs/status.md + os.path.isdir по названным
пакетам; обход docs/**, парсинг VitePress-конфига и запуск CLI пакетов не производятся.
"""
import os
import re
import sys

# Осознанный дубль словаря — держать в синхроне с plan-protocol § Statuses
# (packages/skiller/skills/general/plan-protocol/SKILL.md), образец дисциплины — validate.sh
# против core.project.PROJECT_TYPES.
MATURITY_VALUES = {"available", "experimental", "behind-gate", "disabled", "superseded"}

# Имя пакета в матрице -> каталог, существование которого проверяется относительно корня репо.
PACKAGE_DIRS = {
    "swissknifeman (router)": ".",
    "skiller": "packages/skiller",
    "harness": "packages/harness",
    "maind": "packages/maind",
    "analyst": "packages/analyst",
    "task": "packages/task",
    "core": "core",
}

ROW_RE = re.compile(r"^\|(.+)\|$")


def parse_rows(text):
    rows = []
    in_matrix = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.strip() == "## Матрица":
            in_matrix = True
            continue
        if in_matrix and line.startswith("## "):
            break
        if not in_matrix:
            continue
        m = ROW_RE.match(line.rstrip())
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) != 4:
            continue
        if cells[0] == "Пакет":
            continue
        if set(cells[0]) <= {"-", ":"}:
            continue
        rows.append((lineno, *cells))
    return rows


def check(path, repo_root):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    rows = parse_rows(text)
    errors = []
    seen = set()
    for lineno, package, capability, maturity, evidence in rows:
        if maturity not in MATURITY_VALUES:
            errors.append(f"строка {lineno}: «Зрелость» = «{maturity}» не из словаря")
        if not evidence:
            errors.append(f"строка {lineno}: Evidence пуст")
        pkg_dir = PACKAGE_DIRS.get(package)
        if pkg_dir is None:
            errors.append(f"строка {lineno}: пакет «{package}» неизвестен")
        elif not os.path.isdir(os.path.join(repo_root, pkg_dir)):
            errors.append(f"строка {lineno}: каталог пакета «{package}» не найден")
        key = (package, capability)
        if key in seen:
            errors.append(f"строка {lineno}: дубль ({package}, {capability})")
        seen.add(key)
    return rows, errors


def main(argv):
    if len(argv) != 2:
        print("использование: status-check.py <path/to/status.md>", file=sys.stderr)
        return 2
    path = argv[1]
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rows, errors = check(path, repo_root)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print(f"status-check: {len(rows)} строк(и), 0 ошибок")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
