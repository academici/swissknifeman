"""Атомарная запись файлов — общий примитив монорепо.

tmp-файл рядом с целью → `os.replace` (атомарная подмена на одной ФС). Этот паттерн
swissknifeman (`state.save_db`) и maind (`common.atomic_write_json`) скопировали
независимо байт-в-байт; вынесен сюда, чтобы оба пакета писали через один источник
истины и краш в момент записи не оставлял полузаписанного файла. stdlib-only."""
import copy
import json
import os
import shutil
from datetime import date
from pathlib import Path
from typing import Callable, Optional


def backup_file(path, *, suffix=".bak"):
    """Копия `<path><suffix>`, если файл существует. Возвращает путь бэкапа или None.

    Единый источник merge-only-бэкапа: раньше `maind.common.backup_file` +
    россыпь инлайновых `shutil.copy2(path, f'{path}.bak')` в harness.settings /
    skiller.connect / skiller.topology. `suffix` параметризует хвост (`.bak` по
    умолчанию; `.json.bak` у topology). stdlib-only."""
    path = Path(path)
    if not path.exists():
        return None
    bak = path.with_name(path.name + suffix)
    shutil.copy2(path, bak)
    return bak


def safe_load_json(path, default=None, *, on_error: Optional[Callable] = None):
    """Читает JSON с graceful-восстановлением. Несуществующий/битый файл →
    `default` (если задан on_error — он вызывается с исключением до возврата).

    Единый источник истины вместо россыпи `json.loads(path.read_text())` с
    разнобоем обработки ошибок. Для БД с бэкапом битого файла см. доменные
    обёртки (например maind.common.load_json_db). stdlib-only."""
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        if on_error is not None:
            on_error(e)
        return default


def read_ndjson_iter(path):
    """Генератор безопасного построчного разбора ndjson/jsonl: пустые/битые строки и
    не-dict записи пропускаются, errors='replace' — битый байт не роняет чтение.
    Несуществующий файл — пустой генератор.

    Основа read_ndjson(list) и потоковых потребителей, которым материализация всего
    файла в память не нужна (напр. большой общемашинный лог со всех проектов,
    растущий без ротации)."""
    path = Path(path)
    if not path.is_file():
        return
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except (ValueError, TypeError):
                continue
            if isinstance(rec, dict):
                yield rec


def read_ndjson(path):
    """Разбор ndjson/jsonl-файла в список dict'ов; см. read_ndjson_iter."""
    return list(read_ndjson_iter(path))


def load_json_db(path, default, *, max_version=None):
    """JSON-«БД» с восстановлением: нет файла → deepcopy(default); БИТЫЙ файл → бэкап
    `<name>.corrupt.<date>` + warn + deepcopy(default); version > max_version → die.

    Единый источник истины вместо дословных копий в skiller.state.load_db и
    maind.common.load_json_db (расходились в имени бэкапа и тексте ошибки). `default` НЕ
    мутируется (возвращается deepcopy). die/warn — из core.term (лениво, без цикла импорта).
    stdlib-only."""
    from .term import die, warn
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(default)
    try:
        db = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        backup = path.with_name(f"{path.name}.corrupt.{date.today().isoformat()}")
        path.rename(backup)
        warn(f"{path} повреждён → сохранён в {backup.name} (начинаю заново)")
        return copy.deepcopy(default)
    if max_version is not None and isinstance(db, dict) and db.get("version", 1) > max_version:
        die(f"{path} записан более новой версией — обновите репозиторий (git pull) и "
            f"перезапустите установку")
    return db


def assert_safe_replace_target(path):
    """Отказывает, если существующая `path` — НЕ безопасная цель для `os.replace`:
    symlink, не-регулярный файл (сокет/FIFO/устройство) или жёсткая ссылка (`st_nlink != 1`).
    Несуществующая цель — норма (не отказывает). Один `lstat`, обход/резолв цепочки
    симлинков и рекурсивные проверки родителей НЕ производятся (containment —
    задача `core.paths`).

    Без этой проверки `os.replace` тихо заменял бы саму symlink-цель, отвязывая её от
    реального файла (P8.7, перенос raytsystem: дубль ручных проверок в
    `packages/maind/lib/maind/provider_deploy.py` — `plan_project_carrier`,
    `_rollback_project_carrier`, `_d108_rollback_operation_error`,
    `plan_exact_artifact_adoption`; перевод их на этот хелпер — roadmap-кандидат,
    не выполняется этим item'ом)."""
    path = Path(path)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if os.path.islink(path):
        raise OSError(f"{path}: небезопасная цель для атомарной замены — символьная ссылка")
    if not os.path.isfile(path):
        raise OSError(f"{path}: небезопасная цель для атомарной замены — не регулярный файл")
    if st.st_nlink != 1:
        raise OSError(
            f"{path}: небезопасная цель для атомарной замены — st_nlink={st.st_nlink} "
            f"(жёсткая ссылка)"
        )


def atomic_write_text(path, text, *, encoding="utf-8", mode=None, check_target=True):
    """Пишет текст атомарно: `<name>.tmp` рядом → `os.replace`. Создаёт
    родительские каталоги. Краш в процессе не оставляет битого целевого файла; при
    ошибке записи/замены подчищает и осиротевший `.tmp` (иначе он копится на диске
    в долгоживущих процессах, напр. при `No space left`).

    mode (напр. 0o600) — права доступа целевого файла; ставятся на `.tmp` ДО замены,
    чтобы итоговый файл НИКОГДА не существовал с дефолтными (umask) правами. Нужно для
    файлов с секретами (config узла): иначе короткое окно world-readable.

    check_target=False отключает `assert_safe_replace_target` (см. docstring) для
    ОДНОГО точечного вызова — только если пакет монорепо ЛЕГАЛЬНО пишет через
    symlink-цель (законный выход, не глобальное отключение)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        if mode is not None:
            os.chmod(tmp, mode)
        if check_target:
            assert_safe_replace_target(path)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_json(path, data, *, version=None, indent=2, mode=None, check_target=True):
    """Пишет JSON атомарно c финальным '\\n'. Если version задан и data — dict,
    проставляет data['version']=version первым ключом. mode/check_target — см.
    atomic_write_text (напр. 0o600 для конфигов с секретами)."""
    if version is not None and isinstance(data, dict):
        rest = {k: v for k, v in data.items() if k != "version"}
        data = {"version": version, **rest}
    atomic_write_text(path, json.dumps(data, indent=indent, ensure_ascii=False) + "\n",
                      mode=mode, check_target=check_target)
