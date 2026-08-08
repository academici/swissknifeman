#!/usr/bin/env python3
"""Межплановая сверка Files: какие пути трогают items из РАЗНЫХ планов.

Программный гейт этапа B (см. plans/README.md § «Программа: этапы A–D»).
Карта владения поверхностями, выведенная из заголовков фаз и строк Routing, —
догадка; доказательство даёт только пересечение фактических полей `**Files:**`.

Ограничение, которое инструмент называет сам: скелет-item несёт `Files: —`,
поэтому недетализированная фаза в пересечения НЕ попадает и создаёт слепую
зону. Отчёт всегда печатает, сколько items прошли мимо проверки по этой
причине, чтобы «0 конфликтов» нельзя было прочитать как «конфликтов нет».

stdlib-only. Использование:
    python3 plans/cross-plan-files.py                # все живые планы
    python3 plans/cross-plan-files.py <ID> <ID> ...  # только названные
    python3 plans/cross-plan-files.py --strict       # baseline-режим (см. ниже)

`--strict` — baseline/рэтчет-режим (payload D, аудит этапа C Ф9): полный отчёт печатается
всегда; exit 1 только если среди живых пересечений нашлось хотя бы одно НЕ из
`cross-plan-known-intersections.json` (новое или бесхозное). Пересечения, уже зафиксированные
в этом перечне (владелец+порядок названы в ТЗ обоих концов — сверено аудитом этапа C), зелёный
`--strict` не требует их закрытия. Обновление перечня при появлении/закрытии пересечения —
ручное, тем же коммитом, что меняет `Files`.
"""
from __future__ import annotations

import collections
import glob
import importlib
import json
import os
import re
import sys

PLANS_DIR = os.path.dirname(os.path.abspath(__file__))
SKELETON = "СКЕЛЕТ — не детализирован"
ITEM_RE = re.compile(r"^### (P\d+\.\d+)\s+—", re.M)
BACKTICK_RE = re.compile(r"`([^`]+)`")
# голые пути (FOREMAN пишет Files без бэктиков, через `;`)
BARE_RE = re.compile(r"(?<![`\w/])((?:[\w.-]+/)+[\w.-]+)")
STATUS_RE = re.compile(r"^\|\s*Status\s*\|\s*(\S+)", re.M)
ITEM_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(\S+)", re.M)
TERMINAL = ("\U0001f7e2", "\U0001f7e0", "\u26d4")  # Done / Done with deviations / Skipped
KNOWN_INTERSECTIONS_FILE = os.path.join(PLANS_DIR, "cross-plan-known-intersections.json")
# \u043a\u043e\u0440\u043d\u0435\u0432\u044b\u0435 \u043d\u043e\u0441\u0438\u0442\u0435\u043b\u0438 \u0431\u0435\u0437 "/" \u0432 \u043f\u0443\u0442\u0438 (\u04185) \u2014 \u043c\u0430\u0448\u0438\u043d\u043d\u043e\u043c\u0443 \u0433\u0435\u0439\u0442\u0443 \u0438\u043d\u0430\u0447\u0435 \u043d\u0435\u0432\u0438\u0434\u0438\u043c\u044b, \u0441\u043c. plans/README.md
# \u00a7 \u00ab\u0414\u0438\u0441\u0446\u0438\u043f\u043b\u0438\u043d\u0430 \u0441\u043e\u043f\u0440\u043e\u0432\u043e\u0436\u0434\u0435\u043d\u0438\u044f\u00bb / \u00a7 \u00ab\u0410\u0443\u0434\u0438\u0442 \u044d\u0442\u0430\u043f\u0430 C\u00bb \u04247.
ROOT_VISIBLE_FILES = {"CLAUDE.md", "AGENTS.md", "CHANGELOG.md", "config.json"}


def phase_files(plan_id: str) -> list[str]:
    """Resolve phase carriers through task instead of maintaining two glob layouts."""
    task_lib = os.path.join(os.path.dirname(PLANS_DIR), "packages", "task", "lib")
    if task_lib not in sys.path:
        sys.path.insert(0, task_lib)
    plan_dir = os.path.join(PLANS_DIR, plan_id)
    try:
        resolver = importlib.import_module("task.plan_layout")
        return [str(path) for path in resolver.phase_paths(plan_dir).values()]
    except (ImportError, ValueError, OSError):
        return []


def live_plans() -> list[str]:
    out = []
    for path in sorted(glob.glob(os.path.join(PLANS_DIR, "*", "plan.md"))):
        plan_id = os.path.basename(os.path.dirname(path))
        if plan_id in ("archive", "tools"):  # tools/ — легаси-каталог, если остался
            continue
        out.append(plan_id)
    return out


def normalize(token: str) -> str | None:
    """Путь из ячейки Files → нормализованная форма, либо None если это не путь."""
    t = token.strip()
    for cut in (" (", " —"):
        if cut in t:
            t = t.split(cut)[0]
    t = t.strip().rstrip("/")
    if t in ROOT_VISIBLE_FILES:
        return t
    if "/" not in t or t.startswith("http") or t.endswith(":"):
        return None
    # отсекаем обрывки (regex по голому тексту ловит хвосты вроде "code/hooks/..."):
    # первый сегмент обязан существовать в корне репо
    root = os.path.normpath(os.path.join(PLANS_DIR, ".."))
    if not os.path.exists(os.path.join(root, t.split("/")[0])):
        return None
    return t


def plan_status(plan_id: str) -> str:
    text = open(os.path.join(PLANS_DIR, plan_id, "plan.md"), encoding="utf-8").read()
    m = STATUS_RE.search(text)
    return m.group(1) if m else "?"


def collect(plan_id: str):
    """→ (owners: path -> {item}, skeleton_items: int, sized_items: int)"""
    owners: dict[str, set[str]] = collections.defaultdict(set)
    skeleton = sized = 0
    for phase in sorted(phase_files(plan_id)):
        text = open(phase, encoding="utf-8").read()
        is_skeleton = SKELETON in text
        blocks = ITEM_RE.split(text)
        # blocks: [преамбула, id, тело, id, тело, ...]
        for i in range(1, len(blocks), 2):
            item, body = blocks[i], blocks[i + 1]
            files_line = ""
            for line in body.splitlines():
                if line.startswith("**Files:**"):
                    files_line = line
                    break
            raw = BACKTICK_RE.findall(files_line) + BARE_RE.findall(files_line)
            paths = {p for p in (normalize(x) for x in raw) if p}
            # пути внутри собственного каталога плана конфликтом не являются
            paths = {p for p in paths if not p.startswith(f"plans/{plan_id}/")}
            if not paths and is_skeleton:
                skeleton += 1
                continue
            sized += 1
            st = ITEM_STATUS_RE.search(body)
            closed = bool(st and st.group(1) in TERMINAL)
            tag = f"{plan_id}:{item}" + (" [закрыт]" if closed else "")
            for p in paths:
                owners[p].add(tag)
    return owners, skeleton, sized


def load_known_intersections() -> set[str]:
    if not os.path.exists(KNOWN_INTERSECTIONS_FILE):
        return set()
    with open(KNOWN_INTERSECTIONS_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    return set(data["paths"])


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    strict = "--strict" in sys.argv
    plans = args or live_plans()

    all_owners: dict[str, set[str]] = collections.defaultdict(set)
    blind = 0
    statuses = {p: plan_status(p) for p in plans}
    live = {p for p, st in statuses.items() if st not in TERMINAL}
    json_mode = "--json" in sys.argv
    if json_mode:
        for plan_id in plans:
            owners, skeleton, _sized = collect(plan_id)
            blind += skeleton
            for path, items in owners.items():
                all_owners[path] |= items
        shared = {}
        for path, items in all_owners.items():
            open_plans = {i.split(":")[0] for i in items if "[закрыт]" not in i}
            if len(open_plans & live) > 1:
                shared[path] = sorted(items)
        print(json.dumps({"plans": plans, "shared": shared, "blind_items": blind}, ensure_ascii=False))
        return 0
    print(f"Сверка Files по {len(plans)} планам\n")
    for plan_id in plans:
        owners, skeleton, sized = collect(plan_id)
        blind += skeleton
        mark = "живой" if plan_id in live else "ТЕРМИНАЛЬНЫЙ (историч.)"
        print(f"  {plan_id} [{statuses[plan_id]} {mark}]: items с Files {sized} · скелетов без Files {skeleton} · путей {len(owners)}")
        for path, items in owners.items():
            all_owners[path] |= items

    shared, historical = {}, {}
    for path, items in all_owners.items():
        owners_p = {i.split(":")[0] for i in items}
        if len(owners_p) < 2:
            continue
        # живой конфликт = ОТКРЫТЫЕ items из ≥2 незакрытых планов
        open_plans = {i.split(":")[0] for i in items if "[закрыт]" not in i}
        if len(open_plans & live) > 1:
            shared[path] = items
        else:
            historical[path] = items
    print(f"\nПутей всего: {len(all_owners)}")
    print(f"ЖИВЫХ пересечений (≥2 незакрытых планов): {len(shared)}")
    print(f"исторических (пересечение только с терминальным планом): {len(historical)}")
    if blind:
        print(
            f"СЛЕПАЯ ЗОНА: {blind} items — скелеты без Files. "
            "Пустой список пересечений НЕ означает отсутствие конфликтов, "
            "пока эти items не детализированы."
        )
    print()
    for path in sorted(shared):
        print(f"  {path}")
        for item in sorted(shared[path]):
            print(f"      {item}")
    if not shared:
        print("  (живых пересечений не найдено)")

    if not strict:
        return 0

    known = load_known_intersections()
    uncovered = {p: items for p, items in shared.items() if p not in known}
    print(f"\n--strict (baseline-режим): известных пересечений в перечне {len(known)}")
    if uncovered:
        print(f"НЕПОКРЫТЫЕ (новые/бесхозные) пересечения: {len(uncovered)}")
        for path in sorted(uncovered):
            print(f"  {path}")
            for item in sorted(uncovered[path]):
                print(f"      {item}")
        return 1
    print("Все живые пересечения покрыты перечнем — новых/бесхозных нет.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
