"""Атомарная запись файлов — общий примитив монорепо.

tmp-файл рядом с целью → `os.replace` (атомарная подмена на одной ФС). Этот паттерн
swissknifeman (`state.save_db`) и maind (`common.atomic_write_json`) скопировали
независимо байт-в-байт; вынесен сюда, чтобы оба пакета писали через один источник
истины и краш в момент записи не оставлял полузаписанного файла. stdlib-only."""
import json
import os
from pathlib import Path
from typing import Callable, Optional


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


def atomic_write_text(path, text, *, encoding="utf-8"):
    """Пишет текст атомарно: `<name>.tmp` рядом → `os.replace`. Создаёт
    родительские каталоги. Краш в процессе не оставляет битого целевого файла; при
    ошибке записи/замены подчищает и осиротевший `.tmp` (иначе он копится на диске
    в долгоживущих процессах, напр. при `No space left`)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_json(path, data, *, version=None, indent=2):
    """Пишет JSON атомарно c финальным '\\n'. Если version задан и data — dict,
    проставляет data['version']=version первым ключом."""
    if version is not None and isinstance(data, dict):
        rest = {k: v for k, v in data.items() if k != "version"}
        data = {"version": version, **rest}
    atomic_write_text(path, json.dumps(data, indent=indent, ensure_ascii=False) + "\n")
