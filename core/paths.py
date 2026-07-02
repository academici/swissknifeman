"""Безопасный containment путей — общий примитив монорепо (защита от traversal/symlink-escape).

До выноса сюда connect/vendor/skillset/doctor/eval дублировали `startswith(resolve()+os.sep)`
и разнились в обработке symlink. Один источник истины: оба варианта fail-closed (ошибка резолва
→ False). stdlib-only."""
from pathlib import Path


def is_within(path, root):
    """`path` лежит ВНУТРИ `root` (или совпадает). Резолвит ОБЕ стороны (снимает symlink →
    защита от traversal/symlink-escape за пределы цели). Для PRUNE (удаление): symlink наружу
    → False (не трогаем чужую цель). Ошибка резолва → False (fail-closed)."""
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False


def state_dir(home, app=None):
    """Зонтичный state-корень `~/.swissknifeman` (или подкаталог пакета
    `~/.swissknifeman/<app>`). Единый источник литерала `.swissknifeman`, который
    skiller (корень, он им владеет) и analyst (подкаталог) копировали по месту.

    maind СЮДА не входит намеренно: его state — `~/.maind` (отдельный node-state узла,
    не зонтичный слой), поэтому его path-property остаётся собственным."""
    base = Path(home) / ".swissknifeman"
    return base / app if app else base


def is_within_lexical(path, root):
    """Containment МЕСТА `path` под `root` БЕЗ резолва symlink самого `path` (родитель
    резолвится). Для INSTALL-гейта: ловит traversal через '../' в имени, но НЕ отвергает
    symlink, лежащий в `path` (install удалит его и заменит копией). Ошибка резолва → False."""
    try:
        base = Path(root).resolve()
        full = Path(path).parent.resolve() / Path(path).name
        return full == base or base in full.parents
    except (OSError, ValueError):
        return False
