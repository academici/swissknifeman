"""Поиск корня репозитория/монорепо — общий примитив монорепо.

До вынесения сюда корень определялся пятью расходящимися способами (фикс. `../..`
в bash-лаунчерах, поиск `.git` в registry/validate, поиск `packages/` в Env узла) —
они совпадали лишь потому, что вложенность ровно 2 уровня. Здесь — один источник
истины для Python-сайтов. Обе функции возвращают None, если корень не найден:
ветка standalone-vs-monorepo остаётся явной у вызова. stdlib-only."""
from pathlib import Path


def find_repo_root(start):
    """Граница git: ближайший каталог с `.git` вверх от start (включительно).
    None, если не найден (standalone-раскладка — решает вызывающий)."""
    start = Path(start)
    for cand in (start, *start.parents):
        if (cand / ".git").exists():
            return cand
    return None


def find_monorepo_root(start, *, markers=("packages", "core")):
    """Корень монорепо: ближайший каталог вверх от start, где есть ЛЮБОЙ из
    markers-каталогов (`packages/`/`core/`). None, если не найден."""
    start = Path(start)
    for cand in (start, *start.parents):
        if any((cand / m).is_dir() for m in markers):
            return cand
    return None
