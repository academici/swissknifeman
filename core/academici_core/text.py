"""Текстовые помощники — дословный общий код."""
import re

SLUG_RE = re.compile(r"[^a-z0-9-]")


def sanitize(name):
    """Slug: lower, пробелы/подчёркивания → дефис, прочее убрать, схлопнуть дефисы."""
    name = name.lower().replace(" ", "-").replace("_", "-")
    name = SLUG_RE.sub("", name)
    return re.sub(r"-{2,}", "-", name).strip("-")
