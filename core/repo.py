"""Поиск корня репозитория/монорепо — общий примитив монорепо.

До вынесения сюда корень определялся пятью расходящимися способами (фикс. `../..`
в bash-лаунчерах, поиск `.git` в registry/validate, поиск `packages/` в Env узла) —
они совпадали лишь потому, что вложенность ровно 2 уровня. Здесь — один источник
истины для Python-сайтов. Обе функции возвращают None, если корень не найден:
ветка standalone-vs-monorepo остаётся явной у вызова. stdlib-only."""
import os
import shutil
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


def sibling_bin(pkg, *, env_var=None, monorepo_root=None, use_path=True):
    """Резолвер лаунчера соседнего пакета монорепо — единый источник для трёх
    исторически разошедшихся копий (skiller.harness_bin, analyst._resolve_maind_bin,
    maind.orchestrate._sibling_bin). Лестница:

      1. env-override `env_var` (если задан и файл существует) — машинно-специфичный путь;
      2. `shutil.which(pkg)` (если use_path) — установленный в PATH лаунчер (~/.local/bin);
      3. `<monorepo_root>/packages/<pkg>/bin/<pkg>` — раскладка монорепо.

    Возвращает `Path` найденного лаунчера или None (ветку «не найдено»/`die` решает
    вызывающий — контракты пакетов расходятся: одни падают, другие деградируют
    graceful). `monorepo_root` — корень для шага 3; None → шаг 3 пропускается.
    stdlib-only."""
    if env_var:
        override = os.environ.get(env_var)
        if override:
            p = Path(os.path.expanduser(override))
            return p if p.exists() else None
    if use_path:
        which = shutil.which(pkg)
        if which:
            return Path(which)
    if monorepo_root is not None:
        cand = Path(monorepo_root) / "packages" / pkg / "bin" / pkg
        if cand.exists():
            return cand
    return None
