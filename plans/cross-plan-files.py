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
    python3 plans/cross-plan-files.py --strict       # exit 1 при пересечении
"""
from __future__ import annotations

import collections
import glob
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
    for phase in sorted(glob.glob(os.path.join(PLANS_DIR, plan_id, "phases", "*.md"))):
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


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    strict = "--strict" in sys.argv
    plans = args or live_plans()

    all_owners: dict[str, set[str]] = collections.defaultdict(set)
    blind = 0
    statuses = {p: plan_status(p) for p in plans}
    live = {p for p, st in statuses.items() if st not in TERMINAL}
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

    if strict and shared:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
