# Source: anonymized production project
"""
Валидация инвариантов параметров детали БЕЗ запуска Blender.

Запуск:
    python models/part/check.py        # обычный Python, без bpy

Каждая проверка печатает [ OK ] или [ FAIL ]. При добавлении нового параметра
в config.py — добавляй сюда соответствующий инвариант. Ненулевой exit при FAIL.
"""

import os
import sys

# Корень проекта в путь, чтобы импорт работал без установки пакета.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models.part.config import (  # noqa: E402
    model_config as m,
    shell_config as sh,
    joint_config as jt,
    thread_config as th,
    joint_outer_radius,
)

_failures: list[str] = []

# Минимальная печатаемая толщина стенки под FDM/SLA, мм.
MIN_WALL = 0.8
# Допуск стыковки радиусов соседних сегментов, мм (float не сравниваем точно).
TOL = 0.5


def ok(msg: str) -> None:
    print(f"  [ OK ] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    _failures.append(msg)


def check(condition: bool, msg_ok: str, msg_fail: str) -> None:
    ok(msg_ok) if condition else fail(msg_fail)


# ── Высоты и единицы ─────────────────────────────────────────────────────────
print("\n── Высоты ───────────────────────────────────────────────────────────────")

check(
    sh.height > 0,
    f"Высота сегмента положительна: {sh.height:.1f} мм",
    f"Высота сегмента ≤ 0: {sh.height:.1f} мм",
)
check(
    sh.height < m.height,
    f"Сегмент ниже модели: {sh.height:.1f} < {m.height:.1f} мм",
    f"Сегмент не ниже модели: {sh.height:.1f} ≥ {m.height:.1f} мм",
)
check(
    abs(sh.profile_knots[-1][0] - sh.height) < TOL,
    f"Последний узел профиля z ≈ height ({sh.height:.1f} мм)",
    f"Последний узел z={sh.profile_knots[-1][0]} ≠ height={sh.height}",
)

# ── Стыковка радиусов (float — по допуску, не точно) ─────────────────────────
print("\n── Стыковка радиусов ────────────────────────────────────────────────────")

r_knot_bottom = sh.profile_knots[0][1]
r_knot_top = sh.profile_knots[-1][1]
check(
    abs(r_knot_bottom - sh.radius_bottom) <= TOL,
    f"Нижний узел r={r_knot_bottom} совпадает с radius_bottom={sh.radius_bottom} (±{TOL})",
    f"Нижний узел r={r_knot_bottom} ≠ radius_bottom={sh.radius_bottom} (допуск {TOL} мм)",
)
check(
    abs(r_knot_top - sh.radius_top) <= TOL,
    f"Верхний узел r={r_knot_top} совпадает с radius_top={sh.radius_top} (±{TOL})",
    f"Верхний узел r={r_knot_top} ≠ radius_top={sh.radius_top} (допуск {TOL} мм)",
)

# ── Толщина стенки (печать FDM/SLA) ──────────────────────────────────────────
print("\n── Толщина стенки ───────────────────────────────────────────────────────")

check(
    m.wall >= MIN_WALL,
    f"Стенка wall={m.wall} ≥ MIN_WALL={MIN_WALL} мм: печатаема",
    f"Стенка wall={m.wall} < MIN_WALL={MIN_WALL} мм: слишком тонкая для печати",
)
check(
    jt.wall >= MIN_WALL,
    f"Стенка посадки joint.wall={jt.wall} ≥ {MIN_WALL} мм",
    f"Стенка посадки joint.wall={jt.wall} < {MIN_WALL} мм: слишком тонкая",
)

# ── Посадка (joint) ──────────────────────────────────────────────────────────
print("\n── Посадка ──────────────────────────────────────────────────────────────")

r_seat = jt.seat_inner_diameter * 0.5
r_joint_outer = joint_outer_radius(jt)
check(
    r_joint_outer > r_seat,
    f"Папа r_outer={r_joint_outer:.2f} > r_seat={r_seat:.2f}: стенка посадки есть",
    f"Папа r_outer={r_joint_outer:.2f} ≤ r_seat={r_seat:.2f}: нулевая стенка",
)
check(
    jt.clearance > 0,
    f"clearance={jt.clearance} мм > 0: посадка собирается с зазором",
    f"clearance={jt.clearance} мм ≤ 0: папа не войдёт в маму",
)
check(
    jt.depth <= sh.height,
    f"Глубина посадки depth={jt.depth} ≤ высота сегмента {sh.height} мм",
    f"depth={jt.depth} > height={sh.height}: посадка выходит за деталь",
)

# ── Резьба (зазор vs профиль; параметры — навык blender/threading) ───────────
print("\n── Резьба ───────────────────────────────────────────────────────────────")

check(
    th.depth > th.clearance,
    f"thread depth={th.depth} > clearance={th.clearance}: зубец выступает над зазором",
    f"thread depth={th.depth} ≤ clearance={th.clearance}: зубец полностью в зазоре",
)
check(
    th.pitch > 0 and th.turns >= 1,
    f"Резьба корректна: pitch={th.pitch} мм, turns={th.turns}",
    f"Некорректная резьба: pitch={th.pitch}, turns={th.turns}",
)

# ── Итог ─────────────────────────────────────────────────────────────────────
print("\n── Итог ─────────────────────────────────────────────────────────────────")
if _failures:
    print(f"\n  {len(_failures)} ошибок:\n")
    for f_ in _failures:
        print(f"    • {f_}")
    sys.exit(1)
print("\n  Все проверки пройдены.\n")
