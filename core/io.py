"""Атомарная запись файлов — общий примитив монорепо.

tmp-файл рядом с целью → `os.replace` (атомарная подмена на одной ФС). Этот паттерн
swissknifeman (`state.save_db`) и maind (`common.atomic_write_json`) скопировали
независимо байт-в-байт; вынесен сюда, чтобы оба пакета писали через один источник
истины и краш в момент записи не оставлял полузаписанного файла. stdlib-only."""
import json
import os
from pathlib import Path


def atomic_write_text(path, text, *, encoding="utf-8"):
    """Пишет текст атомарно: `<name>.tmp` рядом → `os.replace`. Создаёт
    родительские каталоги. Краш в процессе не оставляет битого целевого файла."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, path)


def atomic_write_json(path, data, *, version=None, indent=2):
    """Пишет JSON атомарно c финальным '\\n'. Если version задан и data — dict,
    проставляет data['version']=version первым ключом."""
    if version is not None and isinstance(data, dict):
        rest = {k: v for k, v in data.items() if k != "version"}
        data = {"version": version, **rest}
    atomic_write_text(path, json.dumps(data, indent=indent, ensure_ascii=False) + "\n")
