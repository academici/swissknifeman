"""core — общий stdlib-only фундамент пакетов монорепо.

Здесь живут дословные дубли, которые исторически копировались между
swissknifeman/maind/brain байт-в-байт: вывод (die/warn/now_iso/confirm), slug
(sanitize) и базовый Env (общее ядро root/cmd/home). Плюс примитивы, которые оба
пакета успели скопировать независимо с расходящимся поведением и которые сведены
сюда к одному источнику истины: атомарная запись (atomic_write_text/json) и поиск
корня репо/монорепо (find_repo_root/find_monorepo_root). Доменные надстройки —
прочие path-property, parse_args/parse_flags, HTTP, frontmatter — остаются в
common.py каждого пакета (они расходятся по контракту и не дословны).

Импортируется как пакет `core` (PYTHONPATH = корень монорепо; см. bin-лаунчеры).
Без сторонних зависимостей."""
from .env import HOME, BaseEnv
from .io import atomic_write_json, atomic_write_text
from .repo import find_monorepo_root, find_repo_root
from .term import confirm, die, now_iso, warn
from .text import sanitize

__all__ = [
    "HOME", "BaseEnv", "die", "warn", "now_iso", "confirm", "sanitize",
    "atomic_write_text", "atomic_write_json",
    "find_repo_root", "find_monorepo_root",
]
